#!/usr/bin/env python3
"""Décision humaine sur les éléments inconnus d'une VM, avec la proposition du
modèle sous les yeux. Écrit decisions/<vm>.json sur la branche de la merge
request, puis relance infra/bs-mr.sh (code régénéré, poussé, MR à jour, CI).

    infra/bs-decider.py bs-logistique --par Théo
    infra/bs-decider.py bs-logistique --par Théo --depuis infra/demo/decisions-bs-logistique.json

Le modèle propose, l'humain tranche : aucune décision n'est prise sans une
réponse et une raison tapées (ou lues dans --depuis, fichier écrit par un humain).
"""

import argparse
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..")
REPO = os.path.join(ROOT, "forge", "pme-infra")
CHOIX = {"r": "reproduire", "n": "ne pas reproduire", "a": "accepter"}
STATUT = {"reproduire": "reproduire", "ne_pas_reproduire": "ne pas reproduire", "donnee": "donnée",
          "a_verifier": "à vérifier"}


def charger_classify():
    path = os.path.join(ROOT, "classement", "bs-classify")
    loader = importlib.machinery.SourceFileLoader("bs_classify", path)
    spec = importlib.util.spec_from_loader("bs_classify", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser(description="Trancher les inconnus d'une VM, proposition du modèle à l'appui.")
    ap.add_argument("vm")
    ap.add_argument("--par", required=True, help="nom de la personne qui décide")
    ap.add_argument("--depuis", help="décisions déjà écrites par un humain (JSON clé -> {decision, raison})")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # texte dans l'ordre avant la sortie de bs-mr.sh
    vm = args.vm
    branche = f"reconstruction/{vm}"
    if subprocess.run(["git", "-C", REPO, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True,
                      text=True).stdout.strip() != branche:
        sys.exit(f"le dépôt {REPO} n'est pas sur {branche} : lancer d'abord infra/bs-mr.sh {vm}")
    subprocess.run(["git", "-C", REPO, "pull", "-q", "--ff-only"], check=True)
    ref = json.load(open(os.path.join(ROOT, "inventaires", f"{vm}-vierge.json"), encoding="utf-8"))
    cur_path = os.path.join(ROOT, "inventaires", f"{vm}-pieges.content.json")
    if not os.path.exists(cur_path):
        cur_path = os.path.join(ROOT, "inventaires", f"{vm}-services.content.json")
    cur = json.load(open(cur_path, encoding="utf-8"))
    items, _ = charger_classify().run(ref, cur)
    chemin = os.path.join(REPO, "decisions", f"{vm}.json")
    decided = json.load(open(chemin, encoding="utf-8")) if os.path.exists(chemin) else {}
    pp = os.path.join(REPO, "decisions", f"{vm}.propositions.json")
    props = json.load(open(pp, encoding="utf-8")).get("propositions", {}) if os.path.exists(pp) else {}
    ecrites = json.load(open(args.depuis, encoding="utf-8")) if args.depuis else {}
    # Décisions en attente : celles que bs-generate a listées (inconnus, données sans sauvegarde),
    # sinon les inconnus du classement.
    att_path = os.path.join(REPO, vm, "attente.json")
    if os.path.exists(att_path):
        raisons = {a["cle"]: a["raison"] for a in json.load(open(att_path, encoding="utf-8"))}
        attente = [{"key": k, "raison": r} for k, r in raisons.items() if k not in decided]
    else:
        attente = [i for i in items if i["statut"] == "inconnu" and i["key"] not in decided
                   and (i["key"] in props or not props)]
    if not attente:
        sys.exit("aucun inconnu en attente de décision")
    print(f"{vm} : {len(attente)} élément(s) à trancher. Le modèle propose ; vous décidez.\n")
    nouvelles = {}
    for n, i in enumerate(attente, 1):
        k = i["key"]
        print(f"[{n}/{len(attente)}] {k}\n  constat : {i['raison']}")
        p = props.get(k)
        if p:
            print(f"  modèle  : {STATUT.get(p['statut'], p['statut'])}, risque {p['risque']} : {p['raison']}\n"
                  f"  question: {p['question']}")
        if args.depuis:
            d = ecrites.get(k)
            if not d:
                print("  -> pas de décision écrite : reste en attente\n")
                continue
            choix, raison = d["decision"], d["raison"]
            print(f"  décision: {choix} ({raison})\n")
        else:
            rep = ""
            while rep not in ("r", "n", "a", "p"):
                rep = input("  décision [r]eproduire / [n]e pas reproduire / [a]ccepter (données) / [p]asser : ").strip().lower()[:1]
            if rep == "p":
                print()
                continue
            choix = CHOIX[rep]
            raison = ""
            while not raison:
                raison = input("  raison : ").strip()
            print()
        nouvelles[k] = {"decision": choix, "par": args.par, "raison": raison}
    if not nouvelles:
        sys.exit("aucune décision prise")
    decided.update(nouvelles)
    with open(chemin, "w", encoding="utf-8") as fh:
        json.dump(decided, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    msg = f"Décisions humaines sur {vm} ({len(nouvelles)}, par {args.par})"
    subprocess.run([os.path.join(ROOT, "infra", "bs-mr.sh"), vm, msg], check=True)


if __name__ == "__main__":
    main()
