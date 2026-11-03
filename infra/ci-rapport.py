#!/usr/bin/env python3
"""Rédige le rapport de vérification (Markdown) à partir des fichiers produits
par ci-verifier.sh, et le publie en commentaire de la merge request si un
jeton et un numéro sont fournis.

    ci-rapport.py <dossier .rapport> [--depot pme/infra --pr 3 --api URL --jeton-env VAR]
"""

import argparse
import json
import os
import sys
import urllib.request


def load(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def render(d):
    chronos = load(os.path.join(d, "chronos.json")) or {}
    test = load(os.path.join(d, "test-metier.json"))
    cmp_ = load(os.path.join(d, "comparaison.json"))
    echec = load(os.path.join(d, "echec.json"))
    lines = []
    if echec:
        lines.append(f"## ❌ Vérification interrompue : {echec['etape_en_echec']}\n")
    elif cmp_ and cmp_["summary"]["unjustified"] == 0:
        lines.append("## ✅ Reconstruction vérifiée : aucun écart non justifié\n")
    elif cmp_:
        lines.append(f"## ⛔ Merge bloqué : {cmp_['summary']['unjustified']} écart(s) non justifié(s)\n")
    if chronos:
        lines.append(f"Sandbox `{chronos.get('sandbox')}` ({chronos.get('ip')}), parcours complet en **{chronos.get('total_s')} s** "
                     f"(sandbox {chronos.get('sandbox_s')} s, reconstruction {chronos.get('reconstruction_s')} s, "
                     f"restauration {chronos.get('restauration_s')} s, redémarrage {chronos.get('redemarrage_s')} s, test métier {chronos.get('test_metier_s')} s, "
                     f"collecte {chronos.get('collecte_s')} s).\n")
    if test:
        lines.append(f"**Test métier** : {'vert' if test['ok'] else 'ROUGE'} en {test['duree_s']} s\n")
        lines += [f"- {'✅' if s['ok'] else '❌'} {s['etape']} : {s['detail']}" for s in test["etapes"]]
        lines.append("")
    if cmp_:
        s = cmp_["summary"]
        lines.append(f"**Comparaison avec l'original** : {s['differences']} écarts, {s['unjustified']} non justifiés, "
                     f"{s['justified']} justifiés.\n")
        bad = [x for x in cmp_["differences"] if not x["justified"]]
        if bad:
            lines.append("| Écart bloquant | Type |\n| --- | --- |")
            lines += [f"| `{x['key']}` | {x['kind']} |" for x in bad]
            lines.append("\nPour débloquer : décider de chaque élément dans `decisions/<vm>.json` "
                         "(`reproduire`, `ne pas reproduire` ou `accepter`, avec une raison et un nom).\n")
        human = [x for x in cmp_["differences"] if x["justified"] and "décision humaine" in (x["justified"] or "")]
        if human:
            lines.append("<details><summary>Écarts acceptés par décision humaine</summary>\n")
            lines += [f"- `{x['key']}` : {x['justified']}" for x in human]
            lines.append("\n</details>\n")
    # Données brutes pour la page de rapport (rapport/bs-rapport), invisibles dans la forge.
    brut = {"chronos": chronos, "test_metier": test, "echec": echec,
            "comparaison": cmp_ and {"summary": cmp_["summary"],
                                     "bloquants": [x["key"] for x in cmp_["differences"] if not x["justified"]]}}
    lines.append("<!-- bs-verif " + json.dumps(brut, ensure_ascii=False).replace("--", "\\u002d\\u002d") + " -->")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dossier")
    ap.add_argument("--depot")
    ap.add_argument("--pr", type=int)
    ap.add_argument("--api", default="http://192.168.103.203:3000/api/v1")
    ap.add_argument("--jeton-env", default="FORGE_TOKEN")
    args = ap.parse_args()
    md = render(args.dossier)
    open(os.path.join(args.dossier, "rapport.md"), "w", encoding="utf-8").write(md)
    print(md)
    token = os.environ.get(args.jeton_env)
    if args.depot and args.pr and token:
        req = urllib.request.Request(f"{args.api}/repos/{args.depot}/issues/{args.pr}/comments",
                                     data=json.dumps({"body": md}).encode(), method="POST",
                                     headers={"Authorization": f"token {token}", "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=20)
            print("rapport publié sur la merge request", file=sys.stderr)
        except Exception as exc:  # le rapport reste dans les journaux de la CI
            print(f"publication impossible : {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
