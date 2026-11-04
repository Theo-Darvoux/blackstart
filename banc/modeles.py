#!/usr/bin/env python3
"""Banc des modèles locaux sur la vraie tâche : proposer un statut pour les
inconnus de bs-logistique, avec exactement la requête de bs-classify --proposer.

Pour chaque modèle : un passage à froid (chargement compris), puis deux
passages chargés (stabilité : même entrée, même sortie ?). Compare ensuite les
propositions aux décisions humaines de infra/demo/decisions-bs-logistique.json.

    banc/modeles.py --url http://192.168.103.204:11434 qwen3.6:35b gemma4:26b \
        --json banc/resultats/modeles-<date>.json
"""

import argparse
import importlib.machinery
import importlib.util
import json
import os
import time
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..")
HUMAIN = {"reproduire": "reproduire", "ne pas reproduire": "ne_pas_reproduire"}


def charger_classify():
    loader = importlib.machinery.SourceFileLoader("bs_classify", os.path.join(ROOT, "classement", "bs-classify"))
    spec = importlib.util.spec_from_loader("bs_classify", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def appel(url, body, timeout=1800):
    req = urllib.request.Request(url.rstrip("/") + "/api/chat", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        rep = json.load(r)
    rep["_mur_s"] = time.monotonic() - t0
    return rep


def decharger(url, modele):
    body = {"model": modele, "keep_alive": 0, "messages": []}
    try:
        appel(url, body, timeout=120)
    except Exception:  # déjà déchargé : sans importance
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("modeles", nargs="+")
    ap.add_argument("--url", default="http://192.168.103.204:11434")
    ap.add_argument("--json")
    args = ap.parse_args()
    bc = charger_classify()
    ref = json.load(open(os.path.join(ROOT, "inventaires", "bs-logistique-vierge.json"), encoding="utf-8"))
    cur = json.load(open(os.path.join(ROOT, "inventaires", "bs-logistique-pieges.content.json"), encoding="utf-8"))
    items, _ = bc.run(ref, cur)
    ctx = bc.Context(cur)
    lot = [p for p in (bc.preuves(i, ref, cur, ctx) for i in items if i["statut"] == "inconnu") if
           not (p["cle"].startswith("file:") and "fichier" not in p)]
    humain = {k: HUMAIN.get(d["decision"], d["decision"]) for k, d in json.load(
        open(os.path.join(ROOT, "infra", "demo", "decisions-bs-logistique.json"), encoding="utf-8")).items()}
    resultats = []
    for modele in args.modeles:
        body = {"model": modele, "stream": False, "think": False, "format": bc.SCHEMA,
                "options": {"temperature": 0, "seed": 1},
                "messages": [{"role": "system", "content": bc.SYSTEME},
                             {"role": "user", "content": "Serveur : bs-logistique. Éléments inconnus et preuves :\n"
                                                         + json.dumps(lot, ensure_ascii=False, indent=1)}]}
        decharger(args.url, modele)
        passages = []
        for nom in ("froid", "chargé 1", "chargé 2"):
            rep = appel(args.url, body)
            try:
                props = {x["cle"]: x for x in json.loads(rep["message"]["content"])["propositions"]}
                valide = True
            except (ValueError, KeyError, TypeError):
                props, valide = {}, False
            accord = sum(1 for p in lot if props.get(p["cle"], {}).get("statut") == humain.get(p["cle"]))
            contra = sum(1 for p in lot if props.get(p["cle"], {}).get("statut") not in (None, "a_verifier", humain.get(p["cle"])))
            ps = {"passage": nom, "total_s": round(rep["_mur_s"], 1),
                  "chargement_s": round(rep.get("load_duration", 0) / 1e9, 1),
                  "entree_jetons": rep.get("prompt_eval_count"),
                  "entree_tok_s": round(rep.get("prompt_eval_count", 0) / max(rep.get("prompt_eval_duration", 1) / 1e9, 1e-9), 1),
                  "sortie_jetons": rep.get("eval_count"),
                  "sortie_tok_s": round(rep.get("eval_count", 0) / max(rep.get("eval_duration", 1) / 1e9, 1e-9), 2),
                  "json_valide": valide, "propositions": len(props), "identiques_humain": accord,
                  "contradictions": contra,
                  "statuts": {k: (props.get(k, {}).get("statut"), props.get(k, {}).get("risque")) for k in (p["cle"] for p in lot)},
                  "brut": props}
            passages.append(ps)
            print(f"{modele:<14} {nom:<9} total {ps['total_s']:>6} s, chargement {ps['chargement_s']:>5} s, "
                  f"sortie {ps['sortie_jetons']} jetons à {ps['sortie_tok_s']} tok/s, JSON {'ok' if valide else 'INVALIDE'}, "
                  f"accord {accord}/{len(lot)}, contradictions {contra}", flush=True)
        stable = passages[1]["statuts"] == passages[2]["statuts"]
        resultats.append({"modele": modele, "passages": passages, "stable_entre_passages_charges": stable})
        print(f"{modele:<14} stable entre les deux passages chargés : {'oui' if stable else 'NON'}", flush=True)
        for k, (st, ri) in passages[1]["statuts"].items():
            print(f"   {k:<50} {st} ({ri})   humain : {humain.get(k)}", flush=True)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"date": time.strftime("%Y-%m-%d %H:%M"), "url": args.url, "elements": [p["cle"] for p in lot],
                       "decisions_humaines": humain, "resultats": resultats}, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
