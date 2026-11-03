#!/usr/bin/env python3
"""Mesure du banc de pièges : combien de pièges l'inventaire fait-il ressortir ?

Compare l'inventaire vierge d'une VM à son inventaire courant (même machine,
sans --identity), puis vérifie chaque piège du corrigé banc/pieges.json.

Usage :
    banc/mesure.py inventaires/bs-logistique-vierge.json inventaires/bs-logistique.json [--json resultat.json]
"""

import argparse
import collections
import fnmatch
import importlib.machinery
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))


def load_compare():
    path = os.path.join(HERE, "..", "collecte", "bs-compare")
    loader = importlib.machinery.SourceFileLoader("bs_compare", path)
    spec = importlib.util.spec_from_loader("bs_compare", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def ip_found(inv, path, ip):
    for f in inv["modified_files"] + inv["unowned"]["files"]:
        if f["path"] == path:
            return any(h["ip"] == ip for h in f.get("ip_literals", []))
    return False


def main():
    ap = argparse.ArgumentParser(description="Mesure du banc de pièges.")
    ap.add_argument("vierge")
    ap.add_argument("courant")
    ap.add_argument("--pieges", default=os.path.join(HERE, "pieges.json"))
    ap.add_argument("--json", help="écrire le résultat dans ce fichier")
    args = ap.parse_args()

    bc = load_compare()
    a = json.load(open(args.vierge, encoding="utf-8"))
    b = json.load(open(args.courant, encoding="utf-8"))
    corrige = json.load(open(args.pieges, encoding="utf-8"))
    diffs, _ = bc.compare(bc.flatten(a), bc.flatten(b), bc.load_rules([bc.DEFAULT_RULES]))
    unjustified = [d for d in diffs if not d["justified"]]
    keys = {d["key"] for d in unjustified}

    results = []
    for p in corrige["pieges"]:
        if "ip_literal" in p:
            ok = ip_found(b, p["ip_literal"]["path"], p["ip_literal"]["ip"])
            evidence = [f"ip_literals:{p['ip_literal']['path']}:{p['ip_literal']['ip']}"] if ok else []
        else:
            evidence = sorted(k for pat in p["cles"] for k in keys if fnmatch.fnmatchcase(k, pat))
            ok = bool(evidence)
        results.append({"id": p["id"], "nom": p["nom"], "spec": p["spec"], "detecte": ok, "preuves": evidence})

    by_cat = collections.Counter(d["key"].split(":", 1)[0] for d in unjustified)
    n = len(results)
    det = sum(r["detecte"] for r in results)
    spec = [r for r in results if r["spec"]]
    det_spec = sum(r["detecte"] for r in spec)

    print(f"Banc de pièges : {args.vierge} -> {args.courant}")
    for r in results:
        mark = "DÉTECTÉ" if r["detecte"] else "MANQUÉ "
        print(f"  {mark} {r['id']:<4} {r['nom']}" + (f"  [{', '.join(r['preuves'])}]" if r["preuves"] else ""))
    print(f"Détection : {det}/{n} ({100 * det / n:.0f} %) ; pièges de la spec : {det_spec}/{len(spec)}")
    print(f"Écarts non justifiés à relire : {len(unjustified)} "
          f"({', '.join(f'{k} {v}' for k, v in by_cat.most_common())})")

    if args.json:
        out = {"vierge": args.vierge, "courant": args.courant,
               "collecte_courante": b["meta"]["collected_at"], "resultats": results,
               "detection": {"detectes": det, "total": n, "spec_detectes": det_spec, "spec_total": len(spec)},
               "ecarts_non_justifies": len(unjustified), "par_categorie": dict(by_cat)}
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
    sys.exit(0 if det == n else 1)


if __name__ == "__main__":
    main()
