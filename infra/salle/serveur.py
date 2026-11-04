#!/usr/bin/env python3
"""Console Black Start de la démo (scénario B accéléré), servie depuis le poste de démo.

    infra/salle/serveur.py --par Théo            puis http://localhost:8080 en plein écran (F11)

La page est une console produit : vue d'ensemble de la machine, parc, inventaire consultable,
décisions, merge request et CI, bascule. Chaque action lancée devient une « opération » découpée
en pas expliqués (quoi, sur quelle machine, résultat), affichée dans le panneau Activité.

Avant l'oral (10 min avant) : Laboratoire → « Préparer ». Vérifie les VM, repose les pièges à
chaud si besoin, charge le modèle, préchauffe la sandbox (clone neuf du template) et calcule les
propositions du modèle sur l'audit du moment : pendant la démo, plus rien n'attend.

Devant le jury, depuis la vue d'ensemble :
  1. « Lancer l'audit »        : collecte en lecture seule, classement, propositions du modèle,
                                 code, merge request, CI bloquée, garde-fou de bascule ;
  2. Décisions → « Valider »   : une décision et une raison par inconnu, CI verte suivie pas à pas ;
  3. Bascule → « Basculer »    : coupure chronométrée, test métier complet sur la production.
Après l'oral : Laboratoire → « Remettre en état » (retour à l'original, pièges reposés).

Rien n'est simulé : chaque pas lance les scripts du prototype (bs-collect, bs-classify, bs-mr.sh,
bs-decider.py, CI Forgejo, bascule.py). Les durées affichées sont celles mesurées en direct.
"""

import argparse
import concurrent.futures
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ICI = os.path.dirname(os.path.realpath(__file__))
RACINE = os.path.realpath(os.path.join(ICI, "..", ".."))
sys.path.insert(0, os.path.join(RACINE, "infra"))
from forge import Forge  # noqa: E402

VM, IP, SBX, SBX_VMID, SBX_IP = "bs-logistique", "192.168.103.200", "sbx-logistique", 1650, "192.168.103.210"
FORGE_IP, IA = "192.168.103.203", "http://192.168.103.204:11434"
MODELE = "qwen3.6:35b"
DEPOT = os.path.join(RACINE, "forge", "pme-infra")
INV = os.path.join(RACINE, "inventaires")
CACHE_PREPARE = os.path.join(INV, f"{VM}.propositions-preparees.json")
DECISIONS_DEMO = os.path.join(RACINE, "infra", "demo", f"decisions-{VM}.json")
RAISONS_DEMO = os.path.join(RACINE, "infra", "demo", f"raisons-{VM}.json")  # une raison préparée par choix
CLE_ADMIN = os.path.expanduser("~/.ssh/id_blackstart_admin")
CLE_COLLECTE = os.path.expanduser("~/.ssh/id_blackstart")
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=5"]

# Machines affichées dans le parc (IP, nom, rôle, zone).
PARC = [("192.168.103.200", "bs-logistique", "Logiciel de logistique + PostgreSQL", "production"),
        ("192.168.103.201", "bs-mail", "Postfix + Dovecot", "production"),
        ("192.168.103.202", "bs-proxy", "Proxy web Nginx + DNS", "production"),
        ("192.168.103.203", "bs-gitlab", "Forge Forgejo + CI", "black start"),
        ("192.168.103.204", "bs-ia", f"Modèle local {MODELE}, sans GPU", "black start")]

POSTE = "poste Black Start"
M_ORIG, M_FORGE, M_IA, M_SBX = f"{VM} · {IP}", f"forge · {FORGE_IP}", "bs-ia · 192.168.103.204", f"{SBX} · {SBX_IP}"

# Étapes de ci-verifier.sh, dans l'ordre : clé, libellé, explication à l'écran.
ETAPES_CI = [
    ("sandbox", "Sandbox isolée",
     "Une VM neuve, clonée d'une Debian vierge, coupée de l'entreprise par un pare-feu."),
    ("reconstruction", "Reconstruction depuis le code",
     "Ansible applique le code de la merge request. Personne au clavier."),
    ("restauration", "Restauration des données",
     "Les données (base PostgreSQL, fichiers EDI) reviennent de la dernière sauvegarde restic."),
    ("redemarrage", "Redémarrage",
     "La copie redémarre : une configuration qui ne survit pas à un redémarrage ferait échouer la preuve."),
    ("collecte", "Audit de la copie",
     "La même collecte en lecture seule que sur l'original, cette fois sur la copie."),
    ("comparaison", "Comparaison avec l'original",
     "Chaque différence entre la copie et l'original doit être justifiée, sinon la CI est rouge."),
    ("test_metier", "Test métier",
     "Une vraie commande est créée, relue puis supprimée dans le logiciel de la copie."),
]


def charger_classify():
    chemin = os.path.join(RACINE, "classement", "bs-classify")
    loader = importlib.machinery.SourceFileLoader("bs_classify", chemin)
    spec = importlib.util.spec_from_loader("bs_classify", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class Etat:
    """État de la console, diffusé en entier à la page à chaque changement (Server-Sent Events).
    Toute modification d'un dict partagé se fait sous `verrou` (la sérialisation aussi)."""

    def __init__(self, par):
        self.verrou = threading.Condition()  # verrou réentrant : publier() peut s'appeler dessous
        self.version = 0
        self.occupe = False
        self.par = par
        self.op = None
        self.d = {}
        self.reinitialiser()

    def reinitialiser(self):
        with self.verrou:
            garde = {k: self.d.get(k) for k in ("preparation", "parc", "operations")}
            self.d = {"phase": "accueil", "par": self.par, "t0": None, "t_fin": None, "erreur": None,
                      "preparation": garde["preparation"] or {"etat": "a_faire", "date": None},
                      "parc": garde["parc"] or {}, "operations": garde["operations"] or [],
                      "audit": None, "ia": None, "code": None, "mr": None, "ci1": None, "refus": None,
                      "decisions": None, "ci2": None, "bascule": None, "journal": []}
        self.publier()

    def publier(self):
        with self.verrou:
            self.version += 1
            self.verrou.notify_all()

    def maj(self, **kw):
        with self.verrou:
            self.d.update(kw)
        self.publier()

    def journal(self, ligne):
        ligne = ligne.rstrip()
        if not ligne:
            return
        with self.verrou:
            self.d["journal"] = (self.d["journal"] + [[time.time(), ligne]])[-200:]
        self.publier()

    def instantane(self):
        with self.verrou:
            return self.version, json.dumps(dict(self.d, maintenant=time.time(), occupe=self.occupe),
                                            ensure_ascii=False)


ETAT: Etat


class Operation:
    """Action lancée depuis la console, découpée en pas annoncés d'avance : la page montre ce qui
    va se passer, ce qui se passe (machine, explication) et ce qui s'est passé (résultat)."""

    def __init__(self, cle, titre, pas):
        self.d = {"id": f"{cle}-{time.time():.3f}", "cle": cle, "titre": titre, "debut": time.time(),
                  "fin": None, "etat": "en_cours",
                  "pas": [{"cle": c, "titre": t, "explication": e, "machine": m, "etat": "avenir",
                           "debut": None, "fin": None, "resultat": None} for c, t, e, m in pas]}
        with ETAT.verrou:
            ETAT.d["operations"] = (ETAT.d["operations"] + [self.d])[-15:]
            ETAT.op = self
        ETAT.publier()

    def _pas(self, cle):
        return next(p for p in self.d["pas"] if p["cle"] == cle)

    def etat(self, cle):
        return self._pas(cle)["etat"]

    def debut(self, cle, t=None):
        with ETAT.verrou:
            p = self._pas(cle)
            if p["etat"] == "avenir":
                p.update(etat="en_cours", debut=t or time.time())
        ETAT.publier()

    def fin(self, cle, resultat=None, etat="ok", t=None):
        """etat : ok, ko (erreur), bloque (garde-fou qui a joué son rôle), saute."""
        with ETAT.verrou:
            p = self._pas(cle)
            t = t or time.time()
            p.update(etat=etat, debut=p["debut"] or t, fin=t, resultat=resultat if resultat is not None else p["resultat"])
        ETAT.publier()

    def resultat(self, cle, texte):
        with ETAT.verrou:
            self._pas(cle)["resultat"] = texte
        ETAT.publier()

    def terminer(self, etat="ok", erreur=None):
        with ETAT.verrou:
            t = time.time()
            for p in self.d["pas"]:
                if p["etat"] == "en_cours":
                    p.update(etat="ko" if etat == "ko" else "ok", fin=t,
                             resultat=(erreur if etat == "ko" else p["resultat"]))
            self.d.update(etat=etat, fin=t, erreur=erreur)
        ETAT.publier()


def lancer(cmd, env=None, sur_ligne=None, cwd=RACINE):
    """Lance une commande, envoie chaque ligne à la sortie technique de la page, rend (code, sortie)."""
    e = dict(os.environ, **(env or {}))
    p = subprocess.Popen(cmd, cwd=cwd, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         bufsize=1)
    lignes = []
    for ligne in p.stdout:
        ligne = re.sub(r"[0-9a-f]{40}", "<jeton>", ligne.rstrip("\n"))
        lignes.append(ligne)
        if not ligne.startswith(("remote:", "    ")):
            ETAT.journal(ligne)
        if sur_ligne:
            sur_ligne(ligne)
    return p.wait(), "\n".join(lignes)


def ssh_ok(ip):
    return subprocess.run(SSH + ["-i", CLE_ADMIN, f"claude@{ip}", "true"], capture_output=True).returncode == 0


def collecter():
    """Deux collectes en parallèle (sans et avec contenu des fichiers), en lecture seule."""
    def une(avec_contenu):
        nom = f"{VM}-pieges" + (".content" if avec_contenu else "")
        cmd = ["ssh", "-T", "-i", CLE_COLLECTE, "-o", "IdentitiesOnly=yes", f"bs-collect@{IP}"]
        if avec_contenu:
            cmd += ["bs-collect", "--with-content"]
        with open(os.path.join(INV, nom + ".json.new"), "wb") as fh:
            rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE).returncode
        if rc:
            raise RuntimeError(f"collecte {nom} en échec (code {rc})")
        os.replace(os.path.join(INV, nom + ".json.new"), os.path.join(INV, nom + ".json"))
    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        list(ex.map(une, (False, True)))


def classer():
    bc = charger_classify()
    ref = json.load(open(os.path.join(INV, f"{VM}-vierge.json"), encoding="utf-8"))
    cur = json.load(open(os.path.join(INV, f"{VM}-pieges.content.json"), encoding="utf-8"))
    items, ips = bc.run(ref, cur)
    return bc, ref, cur, items, ips


def resume_inventaire(cur):
    """Ce que la collecte a relevé, en chiffres lisibles."""
    pk = cur["packages"]
    return (f"{len(pk['installed'])} paquets, {len(cur['systemd']['units'])} services et unités, "
            f"{len(cur['users']['users'])} comptes, {len(cur['processes'])} processus, "
            f"{len(cur['listening'])} ports ouverts")


def statut_commit(sha):
    try:
        return Forge().call("GET", f"/repos/pme/infra/commits/{sha}/status").get("state")
    except Exception:  # forge lente ou VPN coupé : on réessaie
        return None


def attendre_ci(sha, cle, sur_progression=None):
    """Attend l'état final de la CI du commit ; met à jour ETAT[cle]. Avec `sur_progression`, lit
    le journal de progression de ci-verifier.sh sur la forge et le passe à cette fonction."""
    t0 = time.time()
    etapes = {k: {"cle": k, "libelle": lib, "explication": ex, "debut": None, "fin": None, "duree": None,
                  "code": None} for k, lib, ex in ETAPES_CI}
    while time.time() - t0 < 1200:
        st = statut_commit(sha)
        info = dict(ETAT.d.get(cle) or {}, etat=st or "en file", debut=t0, sha=sha[:7])
        if sur_progression:
            r = subprocess.run(SSH + ["-i", CLE_ADMIN, f"claude@{FORGE_IP}", f"cat /srv/bs-ci/{VM}.log"],
                               capture_output=True, text=True)
            lignes = r.stdout.splitlines()
            if lignes and lignes[0].split()[1:3] == ["debut_ci", sha]:
                for l in lignes[1:]:
                    m = l.split()
                    if len(m) >= 3 and m[2] in etapes:
                        if m[1] == "debut":
                            etapes[m[2]]["debut"] = float(m[0])
                        elif m[1] == "fin":
                            etapes[m[2]].update(fin=float(m[0]), duree=int(m[3]), code=int(m[4]))
                    elif len(m) >= 2 and m[1] == "echec":
                        info["echec"] = " ".join(m[2:])
                info["demarree"] = float(lignes[0].split()[0])
            info["etapes"] = [dict(etapes[k]) for k, _, _ in ETAPES_CI]
            sur_progression(info)
        ETAT.maj(**{cle: info})
        if st in ("success", "failure", "error"):
            info.update(fin=time.time(), duree=round(time.time() - t0))
            ETAT.maj(**{cle: info})
            return st
        time.sleep(2)
    raise TimeoutError("CI trop longue")


def rapport_ci(numero):
    """Données brutes du dernier rapport de CI publié sur la merge request (ci-rapport.py)."""
    for _ in range(10):
        coms = Forge().call("GET", f"/repos/pme/infra/issues/{numero}/comments")
        for c in reversed(coms or []):
            m = re.search(r"<!-- bs-verif (.*) -->", c.get("body", ""))
            if m:
                return json.loads(m.group(1).replace("\\u002d", "-"))
        time.sleep(2)
    return None


def cartes_decision():
    """Éléments en attente, avec le constat, la proposition du modèle et une raison préparée pour
    chaque choix possible (infra/demo/) : c'est la personne qui clique qui décide."""
    attente = json.load(open(os.path.join(DEPOT, VM, "attente.json"), encoding="utf-8"))
    pp = os.path.join(DEPOT, "decisions", f"{VM}.propositions.json")
    props = json.load(open(pp, encoding="utf-8")).get("propositions", {}) if os.path.exists(pp) else {}
    demo = json.load(open(DECISIONS_DEMO, encoding="utf-8")) if os.path.exists(DECISIONS_DEMO) else {}
    raisons = json.load(open(RAISONS_DEMO, encoding="utf-8")) if os.path.exists(RAISONS_DEMO) else {}
    cartes = []
    for a in attente:
        r = dict(raisons.get(a["cle"]) or {})
        d = demo.get(a["cle"])
        if d and d.get("decision") not in r:
            r[d["decision"]] = d["raison"]
        cartes.append({"cle": a["cle"], "constat": a["raison"], "proposition": props.get(a["cle"]), "raisons": r})
    return cartes


# ---------------------------------------------------------------- opérations

def preparer():
    op = Operation("preparer", "Préparation du laboratoire", [
        ("machines", "Machines joignables",
         "Connexion SSH d'administration aux 5 VM de la démo.", "bs-* · .200 à .204"),
        ("pieges", "Pièges de l'entreprise en place",
         "Deux pièges « à chaud » (réglage noyau, relais :9100) disparaissent à chaque redémarrage : "
         "on les repose si besoin.", M_ORIG),
        ("modele", "Modèle local chargé en mémoire",
         f"{MODELE} met 3 à 5 min à se charger sans GPU : on le charge avant l'oral.", M_IA),
        ("propositions", "Propositions du modèle calculées",
         "Audit à blanc et appel au modèle sur les inconnus ; la démo réutilise ces réponses si les "
         "preuves n'ont pas changé.", M_IA),
        ("sandbox", "Sandbox préchauffée",
         "Un clone neuf de la Debian vierge attend la CI, pour ne pas payer ~75 s de clonage en direct.",
         "luna · API Proxmox"),
    ])
    ETAT.maj(preparation={"etat": "en_cours", "date": None})

    op.debut("machines")
    with concurrent.futures.ThreadPoolExecutor(5) as ex:
        ok = dict(zip([ip for ip, *_ in PARC], ex.map(ssh_ok, [ip for ip, *_ in PARC])))
    ETAT.maj(parc={"date": time.time(), "joignable": ok})
    ko = [ip for ip, v in ok.items() if not v]
    if ko:
        raise RuntimeError("VM injoignables : démarrer " + ", ".join(ko))
    op.fin("machines", "5 VM sur 5 répondent")

    op.debut("pieges")
    r = subprocess.run(SSH + ["-i", CLE_ADMIN, f"claude@{IP}", "ss -Htln 'sport = :9100' | grep -q ."])
    if r.returncode:
        rc, _ = lancer([os.path.join(RACINE, "pme", "deploy.sh"), "pieges"])
        if rc:
            raise RuntimeError("pme/deploy.sh pieges en échec")
        op.fin("pieges", "reposés (la VM avait redémarré depuis la dernière démo)")
    else:
        op.fin("pieges", "déjà en place")

    def modele():
        op.debut("modele")
        ps = urllib.request.urlopen(f"{IA}/api/ps", timeout=5).read().decode()
        if f'"{MODELE}"' not in ps:
            op.resultat("modele", "chargement en cours (3 à 5 min)")
            req = urllib.request.Request(f"{IA}/api/generate", data=json.dumps(
                {"model": MODELE, "prompt": "ok", "stream": False, "think": False, "keep_alive": -1,
                 "options": {"num_predict": 1}}).encode())
            urllib.request.urlopen(req, timeout=600).read()
            op.fin("modele", f"{MODELE} chargé")
        else:
            op.fin("modele", f"{MODELE} déjà en mémoire")

        op.debut("propositions")
        collecter()
        bc, ref, cur, items, _ = classer()
        cache = json.load(open(CACHE_PREPARE, encoding="utf-8")) if os.path.exists(CACHE_PREPARE) else None
        doc = bc.proposer(items, ref, cur, IA, MODELE, cache)
        json.dump(doc, open(CACHE_PREPARE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        op.fin("propositions", f"{len(doc['propositions'])} propositions "
               + ("déjà calculées sur les mêmes preuves" if doc is cache else f"en {doc['duree_s']} s"))

    def sandbox():
        op.debut("sandbox")
        sb = os.path.join(RACINE, "infra", "sandbox.py")
        import sandbox as sbm
        from pve import PVE
        pve = PVE()
        vm = next((v for v in pve.get("/cluster/resources", type="vm") if v.get("vmid") == SBX_VMID), None)
        desc = pve.get(f"/nodes/{pve.node}/qemu/{SBX_VMID}/config").get("description", "") if vm else ""
        if vm and vm.get("status") == "running" and sbm.NEUVE in desc:
            op.fin("sandbox", f"{SBX} ({SBX_IP}) neuve, prête")
            return
        op.resultat("sandbox", "clone neuf en cours (environ 75 s)")
        if vm:
            subprocess.run([sys.executable, "-I", sb, "destroy", str(SBX_VMID)], capture_output=True)
        r = subprocess.run([sys.executable, "-I", sb, "create", SBX, str(SBX_VMID), SBX_IP, "--neuve"],
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("sandbox non créée : " + (r.stdout[-200:] + r.stderr[-200:]).strip())
        op.fin("sandbox", f"{SBX} ({SBX_IP}) neuve, prête")

    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        for f in [ex.submit(modele), ex.submit(sandbox)]:
            f.result()
    op.terminer()
    ETAT.maj(preparation={"etat": "ok", "date": time.time()})


def audit():
    op = Operation("audit", f"Audit de {VM}", [
        ("collecte", "Collecte en lecture seule",
         "Connexion SSH avec le compte bs-collect, qui ne peut rien modifier. Relevé des paquets, services, "
         "fichiers modifiés, comptes, tâches planifiées, ports ouverts et réglages du noyau.", M_ORIG),
        ("classement", "Classement des écarts",
         "Chaque différence avec une Debian 13 neuve reçoit une règle et une preuve : compris, secret, "
         "donnée, bruit ou inconnu.", POSTE),
        ("ia", "Avis du modèle local sur les inconnus",
         "Seuls les inconnus partent au modèle, avec leurs preuves et les secrets masqués. "
         "Le modèle propose, un humain décide.", M_IA),
        ("code", "Génération du code de reconstruction",
         "Ansible pour tout ce qui est compris, secrets envoyés au coffre, données confiées à la sauvegarde. "
         "Les inconnus ne sont jamais appliqués.", POSTE),
        ("mr", "Merge request sur la forge",
         "Une merge request neuve dans le dépôt de l'entreprise. Rien n'atteint la production sans relecture.",
         M_FORGE),
        ("ci1", "Contrôle automatique (CI)",
         "La CI refuse de reconstruire une machine tant qu'un inconnu n'a pas été tranché.", M_FORGE),
        ("garde", "Garde-fou de bascule",
         "On tente de basculer la production maintenant : le garde-fou exige une CI verte.", POSTE),
    ])
    ETAT.maj(phase="audit", t0=time.time(), t_fin=None)

    op.debut("collecte")
    t = time.time()
    collecter()
    bc, ref, cur, items, ips = classer()
    op.fin("collecte", resume_inventaire(cur))

    op.debut("classement")
    comptes = {}
    for i in items:
        comptes[i["statut"]] = comptes.get(i["statut"], 0) + 1
    ETAT.maj(audit={"duree": round(time.time() - t, 1), "total": len(items), "comptes": comptes,
                    "elements": [{"cle": i["key"], "statut": i["statut"], "ecart": i["ecart"], "raison": i["raison"]}
                                 for i in items],
                    "ip_en_dur": [{"fichier": h["path"], "ligne": h["line"], "ip": h["ip"]} for h in ips],
                    "machine": {"nom": cur["meta"]["hostname"], "os": cur["meta"]["os_release"].get("PRETTY_NAME"),
                                "noyau": cur["meta"]["kernel"], "resume": resume_inventaire(cur)},
                    "date": cur["meta"]["collected_at"]})
    op.fin("classement", f"{len(items)} écarts : {comptes.get('inconnu', 0)} inconnus, {comptes.get('secret', 0)} secrets, "
           f"{comptes.get('donnee', 0)} données, {comptes.get('compris', 0)} compris, {comptes.get('ignore', 0)} bruit"
           + (f" · {len(ips)} adresses IP écrites en dur" if ips else ""))

    ETAT.maj(phase="ia", ia={"etat": "en_cours", "modele": MODELE, "debut": time.time()})
    op.debut("ia")
    t = time.time()
    infos = {}

    def sur_ligne(l):
        m = re.match(r"propositions de (\S+) : (\d+) \((cache|[\d.]+ s)\)", l)
        if m:
            ETAT.maj(ia={"etat": "ok", "modele": m.group(1), "nombre": int(m.group(2)),
                         "cache": m.group(3) == "cache", "duree": round(time.time() - t, 1)})
            op.fin("ia", f"{m.group(2)} propositions" + (" (calculées à la préparation, mêmes preuves)"
                                                           if m.group(3) == "cache" else f" en {m.group(3)}"))
            op.debut("code")
        if l.startswith('{"vm"'):
            infos["code"] = json.loads(l)
            c = infos["code"]
            op.fin("code", f"{c.get('taches')} tâches Ansible, {c.get('coffre')} secrets au coffre")
            op.debut("mr")
        m = re.search(r"(http://\S+/pulls/(\d+))", l)
        if m:
            infos["mr"] = {"url": m.group(1), "numero": int(m.group(2))}
            op.fin("mr", f"merge request n° {m.group(2)} " + ("mise à jour" if "existante" in l else "ouverte"))
    rc, sortie = lancer([os.path.join(RACINE, "infra", "bs-mr.sh"), VM,
                         f"Premier audit de {VM} : inconnus en attente de décision"],
                        env={"BS_A_ZERO": "1", "BS_NOUVELLE_MR": "1", "BS_OLLAMA": IA, "BS_CACHE_PREPARE": CACHE_PREPARE},
                        sur_ligne=sur_ligne)
    if rc:
        raise RuntimeError("bs-mr.sh en échec")
    sha = subprocess.run(["git", "-C", DEPOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    pp = os.path.join(DEPOT, "decisions", f"{VM}.propositions.json")
    if os.path.exists(pp):  # provenance affichée : durée réelle de l'appel au modèle, date, jetons
        doc = json.load(open(pp, encoding="utf-8"))
        ETAT.maj(ia=dict(ETAT.d["ia"] or {}, duree_modele=doc.get("duree_s"), date_modele=doc.get("date"),
                         jetons=doc.get("jetons"), empreinte=doc.get("empreinte"), sans_preuve=doc.get("sans_preuve", []),
                         nombre=len(doc.get("propositions", {})), propositions=doc.get("propositions", {})))
    for k in ("ia", "code", "mr"):  # sortie inattendue de bs-mr.sh : pas laissé « en cours »
        if op.etat(k) in ("avenir", "en_cours"):
            op.fin(k)
    ETAT.maj(phase="ci1", code=dict(infos.get("code", {}), duree=round(time.time() - t, 1)),
             mr=dict(infos.get("mr", {}), sha=sha[:7], branche=f"reconstruction/{VM}"),
             decisions={"cartes": cartes_decision(), "sans_preuve": (ETAT.d["ia"] or {}).get("sans_preuve", [])})

    op.debut("ci1")
    st = attendre_ci(sha, "ci1")
    n = len(ETAT.d["decisions"]["cartes"])
    ETAT.maj(ci1=dict(ETAT.d["ci1"], attente=n))
    if st == "success":
        op.fin("ci1", f"verte en {ETAT.d['ci1']['duree']} s")
        op.fin("garde", "inutile : la CI est déjà verte", "saute")
    else:
        op.fin("ci1", f"merge bloqué : {n} décisions humaines en attente (réponse en {ETAT.d['ci1']['duree']} s)",
               "bloque")
        ETAT.maj(phase="refus")
        op.debut("garde")
        rc, sortie = lancer([sys.executable, "-I", os.path.join(RACINE, "infra", "bascule.py"), "vers-copie"])
        motif = next((l for l in sortie.splitlines() if l.startswith("refusé")), sortie.splitlines()[-1] if sortie else "")
        ETAT.maj(refus={"refusee": rc != 0, "motif": motif, "ci": st})
        op.fin("garde", motif or "refusée", "bloque" if rc else "ok")
    op.terminer()


def decider(choix):
    cartes = ETAT.d["decisions"]["cartes"]
    manquantes = [c["cle"] for c in cartes if not (choix.get(c["cle"]) or {}).get("raison", "").strip()
                  or (choix.get(c["cle"]) or {}).get("decision") not in ("reproduire", "ne pas reproduire", "accepter")]
    if manquantes:
        raise ValueError("décision ou raison manquante : " + ", ".join(manquantes))
    op = Operation("decider", f"Décisions et preuve de reconstruction de {VM}", [
        ("signature", "Décisions signées",
         f"Chaque inconnu reçoit une décision, une raison et le nom de {ETAT.par}. Elles sont versionnées "
         "avec le code.", POSTE),
        ("code", "Code régénéré, merge request à jour",
         "Le code de reconstruction tient compte des décisions ; la CI repart sur le nouveau commit.", M_FORGE),
        ("file", "Prise en charge par la CI",
         "Le runner de la forge récupère la merge request et lance la vérification.", M_FORGE),
    ] + [(k, lib, ex, M_SBX) for k, lib, ex in ETAPES_CI])
    op.debut("signature")
    fichier = os.path.join(INV, f"decisions-salle-{VM}.json")
    json.dump({k: {"decision": v["decision"], "raison": v["raison"].strip()} for k, v in choix.items()},
              open(fichier, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    ETAT.maj(phase="ci2", decisions=dict(ETAT.d["decisions"], prises=choix, date=time.time()))
    nb = {}
    for v in choix.values():
        nb[v["decision"]] = nb.get(v["decision"], 0) + 1
    lib = {"reproduire": "garder", "ne pas reproduire": "retirer", "accepter": "accepter la perte"}
    op.fin("signature", ", ".join(f"{n} « {lib.get(d, d)} »" for d, n in nb.items()) + f", signées {ETAT.par}")

    op.debut("code")
    rc, _ = lancer([sys.executable, "-I", os.path.join(RACINE, "infra", "bs-decider.py"), VM, "--par", ETAT.par,
                    "--depuis", fichier])
    if rc:
        raise RuntimeError("bs-decider.py en échec")
    sha = subprocess.run(["git", "-C", DEPOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    op.fin("code", f"commit {sha[:7]} poussé sur reconstruction/{VM}")
    op.debut("file")

    def progression(info):
        if info.get("demarree") and op.etat("file") == "en_cours":
            op.fin("file", "vérification lancée")
        for e in info.get("etapes", []):  # horodatage de la CI elle-même, pas celui du sondage
            if e["fin"]:
                if op.etat(e["cle"]) in ("avenir", "en_cours"):
                    op.debut(e["cle"], e["debut"])
                    op.fin(e["cle"], None, "ok" if e["code"] == 0 else "ko", e["fin"])
            elif e["debut"]:
                op.debut(e["cle"], e["debut"])
    st = attendre_ci(sha, "ci2", sur_progression=progression)
    brut = rapport_ci(ETAT.d["mr"]["numero"]) if (ETAT.d.get("mr") or {}).get("numero") else None
    if brut:
        cmp_, s, tm = (brut.get("comparaison") or {}).get("summary"), brut.get("sauvegarde"), brut.get("test_metier")
        if cmp_:
            op.resultat("comparaison", f"{cmp_.get('differences')} écarts comparés, "
                                       f"{cmp_.get('unjustified')} non justifié(s)")
        if s:
            op.resultat("restauration", f"instantané {s.get('instantane')}, vieux de {s.get('age_h')} h")
        if tm:
            op.resultat("test_metier", "commande créée, relue et supprimée" if tm.get("ok") else "rouge")
        if brut.get("echec"):
            op.resultat("comparaison", f"échec : {brut['echec']}")
    ETAT.maj(ci2=dict(ETAT.d["ci2"], rapport=brut), phase="preuve" if st == "success" else "ci2")
    if st != "success":
        raise RuntimeError(f"CI {st} : pas de bascule")
    op.terminer()


def basculer():
    op = Operation("basculer", f"Bascule de {VM} vers la copie prouvée", [
        ("verif", "Vérification de la preuve",
         "La bascule n'est permise que si la CI de la merge request est verte.", M_FORGE),
        ("arret", "Arrêt de l'original",
         "L'original est éteint, pas détruit : il reste disponible pour un retour arrière. Le service est coupé.",
         M_ORIG),
        ("identite", "La copie prend l'identité de production",
         f"Adresse {IP} et nom {VM} sur la copie reconstruite.", M_SBX),
        ("demarrage", "Isolation levée, redémarrage",
         "Le pare-feu de la sandbox est retiré, la copie redémarre et doit répondre en HTTP.", f"copie · {IP}"),
        ("test", "Test métier sur la production",
         "Une commande traverse le proxy, le DNS et le serveur de mail réels de l'entreprise.", f"copie · {IP}"),
    ])
    ETAT.maj(phase="bascule", bascule={"debut": time.time(), "lignes": [], "tests": [], "coupure": None})
    b = ETAT.d["bascule"]
    op.debut("verif")
    suite = [("éteint, gardé", "verif", "arret"), ("copie : IP et nom", "arret", "identite"),
             ("isolation levée", "identite", "demarrage"), ("test métier complet", "demarrage", "test")]

    def sur_ligne(l):
        with ETAT.verrou:
            m = re.match(r"\[\s*([\d.]+) s\] (.*)", l)
            if m:
                b["lignes"].append({"t": float(m.group(1)), "texte": m.group(2)})
                if "éteint, gardé" in l:
                    b["coupure_debut"] = time.time()
                c = re.search(r"coupure du service : ([\d.]+) s", l)
                if c:
                    b["coupure"] = float(c.group(1))
                    b["retabli"] = time.time()
            m = re.match(r"\s+(OK|ÉCHEC|KO|ECHEC)\s+(.+?) \(([\d.]+) s\) : (.*)", l)
            if m:
                b["tests"].append({"ok": m.group(1) == "OK", "etape": m.group(2), "duree": float(m.group(3)),
                                   "detail": m.group(4)})
            if l.startswith("TOUT VERT"):
                b["vert"] = l
        if "vérification CI" in l:
            st = l.rsplit(":", 1)[-1].strip()
            op.resultat("verif", "CI verte" if st == "success" else f"CI : {st}")
        for motif, avant, apres in suite:
            if motif in l:
                op.fin(avant)
                op.debut(apres)
        if "coupure du service" in l:
            op.fin("test", f"vert · coupure totale {b['coupure']} s".replace(".", ","))
        if "test métier ROUGE" in l:
            op.fin("test", "rouge : « Remettre en état » pour revenir à l'original", "ko")
        if l.startswith("refusé"):
            op.fin("verif", l, "bloque")
        ETAT.publier()
    rc, _ = lancer([sys.executable, "-I", os.path.join(RACINE, "infra", "bascule.py"), "vers-copie"], sur_ligne=sur_ligne)
    if op.etat("verif") == "bloque":  # garde-fou : rien n'a été coupé
        ETAT.maj(phase="preuve", bascule=None)
        raise RuntimeError(op._pas("verif")["resultat"])
    with ETAT.verrou:
        b.update(fin=time.time(), ok=rc == 0)
    ETAT.maj(phase="fini", t_fin=time.time())
    d = ETAT.d
    res = {"total_s": round(d["t_fin"] - d["t0"]) if d["t0"] else None, "coupure_s": b.get("coupure"),
           "audit_s": d["audit"] and d["audit"]["duree"],
           "ia": d["ia"] and {k: v for k, v in d["ia"].items() if k != "propositions"},
           "code_s": d["code"] and d["code"].get("duree"),
           "ci_rouge_s": d["ci1"] and d["ci1"].get("duree"), "ci_verte_s": d["ci2"] and d["ci2"].get("duree"),
           "ci_verte_etapes": d["ci2"] and {e["cle"]: e["duree"] for e in d["ci2"].get("etapes", [])},
           "decisions_s": d["decisions"] and d["decisions"].get("date") and d["ci1"]
           and round(d["decisions"]["date"] - d["ci1"]["fin"]), "mr": d["mr"], "par": ETAT.par}
    sortie = os.path.join(RACINE, "banc", "resultats", time.strftime("demo-salle-%Y%m%d-%H%M.json"))
    json.dump(res, open(sortie, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    ETAT.journal(f"résultats : {os.path.relpath(sortie, RACINE)}")
    if rc:
        raise RuntimeError("test métier rouge après bascule : Laboratoire → « Remettre en état »")
    op.terminer()


def remettre():
    op = Operation("remettre", "Remise en état du laboratoire", [
        ("retour", "Retour à l'original",
         "La copie est éteinte, l'original rallumé : la production revient à son état d'avant la démo.",
         "luna · API Proxmox"),
        ("pieges", "Pièges reposés",
         "Les pièges à chaud ont disparu au redémarrage : on les remet pour la prochaine démo.", M_ORIG),
    ])
    ETAT.maj(phase="remise")
    op.debut("retour")
    rc, _ = lancer([sys.executable, "-I", os.path.join(RACINE, "infra", "bascule.py"), "retour"])
    if rc:
        raise RuntimeError("retour arrière en échec")
    op.fin("retour", f"{VM} d'origine rallumée")
    op.debut("pieges")
    rc, _ = lancer([os.path.join(RACINE, "pme", "deploy.sh"), "pieges"])
    op.fin("pieges", "en place" if rc == 0 else "échec de pme/deploy.sh pieges", "ok" if rc == 0 else "ko")
    op.terminer("ok" if rc == 0 else "ko")
    ETAT.d["preparation"] = {"etat": "a_faire", "date": None}
    ETAT.reinitialiser()


ACTIONS = {"preparer": preparer, "audit": audit, "decider": decider, "basculer": basculer, "remettre": remettre}


def executer(nom, corps):
    ETAT.op = None
    try:
        if nom == "decider":
            ACTIONS[nom](corps.get("choix", {}))
        else:
            ACTIONS[nom]()
    except Exception as exc:  # affiché dans l'opération et en bandeau, détail dans le terminal
        traceback.print_exc()
        ETAT.maj(erreur=f"{nom} : {exc}")
        if ETAT.op and ETAT.op.d["etat"] == "en_cours":
            ETAT.op.terminer("ko", str(exc))
        if nom == "preparer":
            ETAT.maj(preparation={"etat": "ko", "date": None})
    finally:
        ETAT.occupe = False
        ETAT.publier()


class Page(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def envoyer(self, code, corps, type_="application/json; charset=utf-8"):
        b = corps.encode() if isinstance(corps, str) else corps
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.envoyer(200, open(os.path.join(ICI, "index.html"), "rb").read(), "text/html; charset=utf-8")
        elif self.path == "/etat":
            self.envoyer(200, ETAT.instantane()[1])
        elif self.path == "/flux":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            vu = -1
            try:
                while True:
                    with ETAT.verrou:
                        if ETAT.version == vu:
                            ETAT.verrou.wait(timeout=1)
                    v, s = ETAT.instantane()
                    if v != vu:
                        self.wfile.write(f"data: {s}\n\n".encode())
                        vu = v
                    else:
                        self.wfile.write(b": battement\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
        else:
            self.envoyer(404, '{"erreur": "inconnu"}')

    def do_POST(self):
        nom = self.path.strip("/").removeprefix("action/")
        n = int(self.headers.get("Content-Length") or 0)
        corps = json.loads(self.rfile.read(n) or b"{}")
        if nom == "reinitialiser":
            if ETAT.occupe:
                return self.envoyer(409, '{"erreur": "une opération tourne"}')
            ETAT.reinitialiser()
            return self.envoyer(200, "{}")
        if nom not in ACTIONS:
            return self.envoyer(404, '{"erreur": "action inconnue"}')
        if ETAT.occupe:
            return self.envoyer(409, '{"erreur": "une opération tourne déjà"}')
        ETAT.occupe = True
        ETAT.maj(erreur=None)
        threading.Thread(target=executer, args=(nom, corps), daemon=True).start()
        self.envoyer(202, "{}")


def main():
    global ETAT
    ap = argparse.ArgumentParser(description="Console Black Start de la démo.")
    ap.add_argument("--par", required=True, help="nom de la personne qui décide pendant la démo")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    ETAT = Etat(args.par)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Page)
    srv.daemon_threads = True
    print(f"console Black Start : http://localhost:{args.port}  (Ctrl+C pour arrêter)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
