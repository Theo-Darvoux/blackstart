"""Logo Black Start : symbole « marche » + mot-symbole en tracés (Clash Display 700, ITF Free Font License).
Idée : un interrupteur dont l'anneau est un chrono : tout est noir (le black-out), sauf le premier quart
qui repart en vert depuis la barre. Le produit prouve la reprise et la chronomètre.
Palette : nuit #07090A, clair #E8F2EC, vert phosphore #3DFF8A (sur fond sombre),
vert foncé #0E9F55 (sur fond clair, pour rester lisible).  Usage : uv run --with fonttools python source/logo.py
"""
import math
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen

ICI = Path(__file__).parent
SORTIE = ICI.parent
INK, BONE, VERT, VERT_FONCE = "#07090A", "#E8F2EC", "#3DFF8A", "#0E9F55"
font = TTFont(ICI / "clash-display-700.ttf")
gs, cmap = font.getGlyphSet(), font.getBestCmap()
UPM = font["head"].unitsPerEm
TRACK = 0.02  # interlettrage en em

def mot(texte, x, base, taille):
    """Renvoie (chemin SVG, avance) pour un mot posé sur la ligne de base."""
    s = taille / UPM
    pen = SVGPathPen(gs)
    cur = x
    for ch in texte:
        g = gs[cmap[ord(ch)]]
        if ch != " ":
            g.draw(TransformPen(pen, (s, 0, 0, -s, cur, base)))
        cur += g.width * s + TRACK * taille
    return pen.getCommands(), cur - x - TRACK * taille

def cap_height(taille):
    bp = BoundsPen(gs); gs[cmap[ord("H")]].draw(bp)
    return bp.bounds[3] * taille / UPM

def symbole(cx, cy, r, ep, encre, accent, coupe=0.16):
    """Anneau ouvert en haut (ouverture ±38°), barre verticale, et le premier quart de
    l'anneau en vert : le chrono de reprise qui démarre depuis l'interrupteur."""
    def pt(deg):  # 0° = midi, sens horaire
        a = math.radians(deg)
        return cx + r * math.sin(a), cy - r * math.cos(a)
    g = math.degrees(coupe * ep / r)  # petite coupure entre l'arc vert et l'arc noir
    a0, a1, a2 = 38, 128, 322
    def arc(d0, d1, col):
        (x1, y1), (x2, y2) = pt(d0), pt(d1)
        large = 1 if (d1 - d0) > 180 else 0
        return (f'<path d="M{x1:.2f} {y1:.2f} A{r:.2f} {r:.2f} 0 {large} 1 {x2:.2f} {y2:.2f}" '
                f'fill="none" stroke="{col}" stroke-width="{ep:.2f}"/>')
    bar = f'<rect x="{cx-ep/2:.2f}" y="{cy-r-ep*0.9:.2f}" width="{ep:.2f}" height="{r+ep*0.9:.2f}" fill="{encre}"/>'
    return arc(a0, a1 - g, accent) + arc(a1 + g, a2, encre) + bar

def svg(w, h, corps, fond=None, titre="Black Start"):
    bg = f'<rect width="{w}" height="{h}" fill="{fond}"/>' if fond else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{titre}">'
            f'<title>{titre}</title>{bg}{corps}</svg>\n')

def horizontal(encre, accent, fond=None):
    T = 100; ch = cap_height(T)
    r, ep = ch * 0.53, ch * 0.21          # bas de l'anneau sur la ligne de base
    base = 0
    sym = symbole(r + ep / 2, base - r - ep / 2, r, ep, encre, accent)
    x0 = 2 * (r + ep / 2) + ch * 0.42
    p1, w1 = mot("BLACK", x0, base, T)
    p2, w2 = mot("START", x0 + w1 + T * 0.24, base, T)
    W = x0 + w1 + T * 0.24 + w2
    top = base - 2 * r - ep * 1.4         # haut de la barre
    corps = f'<g transform="translate(0 {-top:.2f})">{sym}<path d="{p1}" fill="{encre}"/><path d="{p2}" fill="{accent}"/></g>'
    return svg(round(W, 1), round(base - top, 1), corps, fond)

def carre(encre, accent, fond):
    S = 512; r, ep = 150, 62
    return svg(S, S, symbole(S / 2, S / 2 + 38, r, ep, encre, accent), fond)

(SORTIE / "logo-black-start.svg").write_text(horizontal(INK, VERT_FONCE))
(SORTIE / "logo-black-start-sombre.svg").write_text(horizontal(BONE, VERT))
(SORTIE / "symbole-black-start.svg").write_text(carre(INK, VERT_FONCE, BONE))
(SORTIE / "symbole-black-start-sombre.svg").write_text(carre(BONE, VERT, INK))
print("ok")
