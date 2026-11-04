"""Assemble source/deck.src.html -> ../black-start-oral.html (autonome : polices et images en base64).
Usage : python3 source/build.py (depuis oral/ ou ailleurs)."""
import base64, os, re, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir, os.pardir)  # blackstart-context/
OUT = os.path.join(HERE, os.pardir, "black-start-oral.html")
FONT_URL = ("https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600"
            "&family=IBM+Plex+Mono:wght@400;500&display=swap")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def fonts_css():
    cache = os.path.join(HERE, "fonts.css")
    if not os.path.exists(cache):
        css = get(FONT_URL).decode()
        # garder latin et latin-ext seulement
        blocs = re.findall(r"/\* ([a-z-]+) \*/\s*(@font-face \{.*?\})", css, re.S)
        out = []
        for sub, bloc in blocs:
            if sub not in ("latin", "latin-ext"):
                continue
            url = re.search(r"url\((https://[^)]+)\)", bloc).group(1)
            data = base64.b64encode(get(url)).decode()
            out.append(bloc.replace(url, "data:font/woff2;base64," + data))
        with open(cache, "w", encoding="utf-8") as f:
            f.write("\n".join(out))
    with open(cache, encoding="utf-8") as f:
        css = f.read()
    clash = b64(os.path.join(ROOT, "identite", "source", "clash-display-700.ttf"))
    css += ("\n@font-face{font-family:'Clash Display';font-weight:700;font-style:normal;"
            f"src:url(data:font/ttf;base64,{clash}) format('truetype');}}")
    return css


def img(m):
    nom = m.group(1)
    for ext, mime in ((".jpg", "image/jpeg"), (".png", "image/png")):
        p = os.path.join(HERE, "img", nom + ext)
        if os.path.exists(p):
            return f"data:{mime};base64,{b64(p)}"
    raise SystemExit(f"image manquante : {nom}")


def svg(m):
    with open(os.path.join(ROOT, "identite", m.group(1) + ".svg"), encoding="utf-8") as f:
        return f.read()


with open(os.path.join(HERE, "deck.src.html"), encoding="utf-8") as f:
    html = f.read()
html = html.replace("%%FONTS%%", fonts_css())
html = re.sub(r"%%IMG:([\w-]+)%%", img, html)
html = re.sub(r"%%SVG:([\w-]+)%%", svg, html)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print(f"{os.path.normpath(OUT)} : {os.path.getsize(OUT) / 1e6:.2f} Mo")
