// Convertit les livrables de Black Start en PDF dans livrables/.
// Usage (depuis la racine du dépôt) : node livrables/source/convertir.mjs [nom…]
// Sans argument, convertit tout. Noms : oral, affiche, landing, rapport, analyse-marche.
//
// Dépendances : Node ≥ 22 (WebSocket natif) et un Chromium headless, lancé en --no-sandbox comme
// Playwright (pages locales du dépôt uniquement).
//   CHROME=/chemin/vers/chrome   (sinon : Chromium de Playwright dans ~/.cache/ms-playwright)
//   MARKED=/chemin/vers/node_modules/marked   (pour analyse-marche ; sinon : paquet « marked »)
import { spawn } from "node:child_process";
import { mkdtempSync, readdirSync, readFileSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { tmpdir, homedir } from "node:os";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const RACINE = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const SORTIE = join(RACINE, "livrables");

function trouverChrome() {
  if (process.env.CHROME) return process.env.CHROME;
  const base = join(homedir(), ".cache", "ms-playwright");
  for (const d of existsSync(base) ? readdirSync(base).sort().reverse() : []) {
    for (const rel of ["chrome-headless-shell-linux64/chrome-headless-shell", "chrome-linux64/chrome", "chrome-linux/chrome"]) {
      const p = join(base, d, rel);
      if (existsSync(p)) return p;
    }
  }
  for (const p of ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]) if (existsSync(p)) return p;
  throw new Error("Chromium introuvable : définir CHROME");
}

// --- CDP minimal -----------------------------------------------------------
async function lancer() {
  const profil = mkdtempSync(join(tmpdir(), "bs-pdf-"));
  const proc = spawn(trouverChrome(), [
    "--headless", "--no-sandbox", "--remote-debugging-port=0", `--user-data-dir=${profil}`,
    "--no-first-run", "--hide-scrollbars", "--font-render-hinting=none", "about:blank",
  ], { stdio: ["ignore", "ignore", "pipe"] });
  const wsUrl = await new Promise((ok, ko) => {
    let buf = "";
    proc.stderr.on("data", d => { buf += d; const m = buf.match(/ws:\/\/\S+/); if (m) ok(m[0]); });
    proc.on("exit", c => ko(new Error("Chromium s'est arrêté : " + c + "\n" + buf)));
  });
  const ws = new WebSocket(wsUrl);
  await new Promise(ok => ws.addEventListener("open", ok));
  let id = 0; const attente = new Map(); const ecoute = [];
  ws.addEventListener("message", ev => {
    const m = JSON.parse(ev.data);
    if (m.id && attente.has(m.id)) { const { ok, ko } = attente.get(m.id); attente.delete(m.id); m.error ? ko(new Error(JSON.stringify(m.error))) : ok(m.result); }
    else ecoute.forEach(f => f(m));
  });
  const envoyer = (method, params = {}, sessionId) => new Promise((ok, ko) => {
    const i = ++id; attente.set(i, { ok, ko }); ws.send(JSON.stringify({ id: i, method, params, sessionId }));
  });
  const evenement = (nom, sessionId) => new Promise(ok => {
    const f = m => { if (m.method === nom && m.sessionId === sessionId) { ecoute.splice(ecoute.indexOf(f), 1); ok(m.params); } };
    ecoute.push(f);
  });
  const fermer = () => { ws.close(); proc.kill(); rmSync(profil, { recursive: true, force: true }); };
  return { envoyer, evenement, fermer };
}

async function imprimer(cdp, { url, largeur, hauteur, prep, pdf, pageUnique, sortie }) {
  const { targetId } = await cdp.envoyer("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await cdp.envoyer("Target.attachToTarget", { targetId, flatten: true });
  const s = (m, p) => cdp.envoyer(m, p, sessionId);
  await s("Page.enable");
  await s("Emulation.setDeviceMetricsOverride", { width: largeur, height: hauteur, deviceScaleFactor: 1, mobile: false });
  await s("Emulation.setEmulatedMedia", { media: "screen", features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  const charge = cdp.evenement("Page.loadEventFired", sessionId);
  await s("Page.navigate", { url });
  await charge;
  const evaluer = expr => s("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true }).then(r => r.result.value);
  await evaluer("document.fonts.ready.then(() => new Promise(r => setTimeout(r, 1500)))");
  if (prep) await evaluer(`(async () => { ${prep} })()`);
  await evaluer("document.fonts.ready.then(() => new Promise(r => setTimeout(r, 800)))");
  const options = { printBackground: true, preferCSSPageSize: true, marginTop: 0, marginBottom: 0, marginLeft: 0, marginRight: 0, ...pdf };
  let data;
  if (pageUnique) {
    // Une seule page aussi haute que le contenu ; la mise en page d'impression peut dépasser
    // un peu la hauteur mesurée à l'écran : agrandir jusqu'à n'avoir qu'une page.
    let h = await evaluer("Math.ceil(Math.max(document.documentElement.scrollHeight, document.body.scrollHeight))");
    await evaluer("(() => { const st = document.createElement('style'); st.id = 'bs-page'; document.head.append(st); })()");
    for (let essai = 0; essai < 12; essai++) {
      await evaluer(`document.getElementById('bs-page').textContent = '@page{size:${largeur}px ${h}px;margin:0}'`);
      ({ data } = await s("Page.printToPDF", options));
      const pages = (Buffer.from(data, "base64").toString("latin1").match(/\/Type\s*\/Page\b/g) || []).length;
      if (pages <= 1) break;
      h += 40;
    }
  } else ({ data } = await s("Page.printToPDF", options));
  writeFileSync(sortie, Buffer.from(data, "base64"));
  await cdp.envoyer("Target.closeTarget", { targetId });
  console.log("  " + sortie.replace(RACINE + "/", "") + "  " + Math.round(Buffer.from(data, "base64").length / 1024) + " Ko");
}

const fichier = rel => pathToFileURL(join(RACINE, rel)).href;
const COULEURS = "*{-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}";
const injecter = css => `const st = document.createElement('style'); st.textContent = ${JSON.stringify(css)}; document.head.append(st);`;

// --- Livrables -------------------------------------------------------------
const LIVRABLES = {
  // Diaporama : une diapo 1920 × 1080 par page, toutes les étapes visibles, sans le HUD.
  oral: () => ({
    url: fichier("oral/black-start-oral.html"), largeur: 1920, hauteur: 1080,
    sortie: join(SORTIE, "black-start-oral.pdf"),
    prep: `document.body.classList.remove('ov');
      document.querySelectorAll('[data-b]').forEach(e => e.classList.add('vu'));
      ${injecter(COULEURS + `
        @page{size:1920px 1080px;margin:0}
        html,body{height:auto!important;overflow:visible!important;background:none!important}
        #stage{position:static!important;transform:none!important;width:1920px!important;height:auto!important;margin:0!important}
        .slide{display:flex!important;position:relative!important;inset:auto!important;width:1920px;height:1080px;break-after:page;break-inside:avoid}
        .slide:last-of-type{break-after:auto}
        #hud{display:none!important}`)}`,
  }),
  // Affiche A4 en vectoriel (source HTML de 794 × 1123 px).
  affiche: () => ({
    url: fichier("identite/affiche/source/affiche.html"), largeur: 794, hauteur: 1123,
    sortie: join(SORTIE, "affiche-black-start.pdf"),
    prep: injecter(COULEURS + "@page{size:794px 1123px;margin:0}"),
  }),
  // Pages web : une seule page continue, rendu écran.
  landing: () => ({
    url: fichier("landing/index.html"), largeur: 1440, hauteur: 900, pageUnique: true,
    sortie: join(SORTIE, "landing-black-start.pdf"),
    prep: `document.querySelectorAll('.fade-up').forEach(e => e.classList.add('visible'));
      document.querySelectorAll('.hero-stats,.etapes-grid,.cta-final').forEach(e => e.classList.add('in'));
      document.documentElement.classList.add('pret');
      ${injecter(COULEURS + "*,*::before,*::after{transition:none!important;animation:none!important}")}`,
  }),
  rapport: () => ({
    url: fichier("rapport/sortie/index.html"), largeur: 1280, hauteur: 900, pageUnique: true,
    sortie: join(SORTIE, "rapport-de-reprise.pdf"),
    prep: injecter(COULEURS + "*,*::before,*::after{transition:none!important;animation:none!important}"),
  }),
  // Markdown → HTML (marked) → A4.
  "analyse-marche": async () => {
    let marked;
    try { marked = (await import(process.env.MARKED ? pathToFileURL(join(process.env.MARKED, "lib/marked.esm.js")).href : "marked")).marked; }
    catch { throw new Error("paquet « marked » introuvable : définir MARKED=/chemin/node_modules/marked"); }
    let md = readFileSync(join(RACINE, "analyse-marche-blackstart.md"), "utf8");
    const ENCADRES = { NOTE: "Note", TIP: "À retenir", IMPORTANT: "Important", WARNING: "Attention", CAUTION: "Prudence" };
    md = md.replace(/^> \[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*\n> ?/gm, (_, t) => `> **${ENCADRES[t]}.** `);
    // Blocs mermaid rendus dans la page ; formules $$…$$ rendues par KaTeX.
    marked.use({ renderer: { code({ text, lang }) { if (lang === "mermaid") {
      // Graphique de CA : barres vert clair, ligne MRR verte (« la ligne verte » du texte).
      if (/^xychart/.test(text)) text = `%%{init: {"themeVariables": {"xyChart": {"plotColorPalette": "#9FD8B5, #0E9F55"}}}}%%\n` + text;
      return `<pre class="mermaid">${text.replace(/</g, "&lt;")}</pre>`; } return false; } } });
    const titre = (md.match(/^# (.+)$/m) || [, "Analyse de marché"])[1];
    const html = `<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>${titre}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600;700&family=IBM+Plex+Mono&display=swap">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"></script>
<style>${COULEURS}
@page{size:A4;margin:18mm 16mm 18mm 16mm}
body{font-family:"IBM Plex Sans",sans-serif;font-size:10.5pt;line-height:1.5;color:#07090A;margin:0}
h1{font-size:22pt;margin:0 0 4pt;border-bottom:3px solid #0E9F55;padding-bottom:6pt}
h2{font-size:15pt;margin:18pt 0 6pt;color:#0A7A41;break-after:avoid}
h3{font-size:12pt;margin:12pt 0 4pt;break-after:avoid}
table{border-collapse:collapse;width:100%;margin:8pt 0;font-size:9.5pt;break-inside:avoid}
th,td{border:1px solid #CBD5CF;padding:4pt 6pt;text-align:left;vertical-align:top}
th{background:#DCEFE3}
blockquote{margin:8pt 0;padding:6pt 10pt;border-left:4px solid #0E9F55;background:#EEF3EF}
blockquote p{margin:0}
code{font-family:"IBM Plex Mono",monospace;font-size:9pt;background:#EEF3EF;padding:0 3px}
hr{border:0;border-top:1px solid #CBD5CF;margin:14pt 0}
a{color:#0A7A41}
pre.mermaid{text-align:center;margin:10pt 0;break-inside:avoid;background:none}
pre.mermaid svg{max-width:100%;max-height:120mm}
pre{white-space:pre-wrap;font-family:"IBM Plex Mono",monospace;font-size:9pt;background:#EEF3EF;padding:6pt 8pt}
.katex-display{margin:6pt 0}
</style></head><body>${marked.parse(md)}</body></html>`;
    const tmp = join(mkdtempSync(join(tmpdir(), "bs-md-")), "analyse.html");
    writeFileSync(tmp, html);
    return {
      url: pathToFileURL(tmp).href, largeur: 900, hauteur: 1200,
      prep: `renderMathInElement(document.body, { delimiters: [{ left: "$$", right: "$$", display: true }], throwOnError: false });
        mermaid.initialize({ startOnLoad: false, theme: "base", fontFamily: "IBM Plex Sans",
          themeVariables: { primaryColor: "#DCEFE3", primaryBorderColor: "#0E9F55", primaryTextColor: "#07090A", lineColor: "#47524E" } });
        await mermaid.run({ querySelector: "pre.mermaid" });`,
      sortie: join(SORTIE, "analyse-marche-blackstart.pdf"),
      pdf: { displayHeaderFooter: true, headerTemplate: "<span></span>",
        footerTemplate: `<div style="font:8pt 'IBM Plex Sans',sans-serif;color:#8A9892;width:100%;text-align:center">Black Start · Analyse de marché · <span class="pageNumber"></span>/<span class="totalPages"></span></div>`,
        marginTop: 0.7, marginBottom: 0.7, marginLeft: 0.63, marginRight: 0.63, preferCSSPageSize: false, paperWidth: 8.27, paperHeight: 11.69 },
    };
  },
};

const noms = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(LIVRABLES);
const cdp = await lancer();
try {
  for (const n of noms) {
    if (!LIVRABLES[n]) throw new Error("livrable inconnu : " + n + " (connus : " + Object.keys(LIVRABLES).join(", ") + ")");
    await imprimer(cdp, await LIVRABLES[n]());
  }
} finally { cdp.fermer(); }
