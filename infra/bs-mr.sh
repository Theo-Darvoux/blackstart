#!/usr/bin/env bash
# Génère le code de reconstruction d'une VM dans le dépôt client de la forge,
# le pousse sur la branche reconstruction/<vm> et ouvre la merge request si
# elle n'existe pas. Les décisions humaines sont lues dans decisions/<vm>.json
# de la branche (rien = toutes en attente).
#
#   infra/bs-mr.sh bs-logistique "message de commit"
#   BS_OLLAMA=http://192.168.103.204:11434 infra/bs-mr.sh bs-logistique   (avec propositions du modèle)
#   BS_NOUVELLE_MR=1 infra/bs-mr.sh bs-logistique   (démo : ferme la MR ouverte, repart de main, ouvre une MR neuve)
set -euo pipefail
cd "$(dirname "$0")/.."
vm="$1"; msg="${2:-Reconstruction de $vm : code généré}"
repo=forge/pme-infra; branch="reconstruction/$vm"
ref="inventaires/$vm-vierge.json"; cur="inventaires/$vm-pieges.content.json"
# bs-logistique porte les pièges du banc ; bs-mail et bs-proxy, l'état après installation des services.
[ -f "$cur" ] || cur="inventaires/$vm-services.content.json"
refinv="${cur%.content.json}.json"

git -C "$repo" fetch -q origin
# Démo : une merge request neuve à chaque passage, sinon les rapports de CI de toutes les
# répétitions s'empilent dans la même. L'ancienne est fermée (pas supprimée) AVANT de
# réécrire la branche, pour que sa CI ne se relance pas sur le nouveau commit.
if [ -n "${BS_NOUVELLE_MR:-}" ]; then
    python3 -I - "$branch" <<'FERMER'
import sys
sys.path.insert(0, "infra")
from forge import Forge
f = Forge()
for p in f.call("GET", "/repos/pme/infra/pulls?state=open"):
    if p["head"]["ref"] == sys.argv[1]:
        f.call("POST", f"/repos/pme/infra/issues/{p['number']}/comments",
               {"body": "Fermée : une nouvelle démo repart d'un audit neuf dans une nouvelle merge request."})
        f.call("PATCH", f"/repos/pme/infra/pulls/{p['number']}", {"state": "closed"})
        print(f"merge request n° {p['number']} fermée (démo précédente)")
FERMER
    git -C "$repo" checkout -q -B "$branch" origin/main
elif git -C "$repo" rev-parse -q --verify "origin/$branch" >/dev/null; then
    git -C "$repo" checkout -q -B "$branch" "origin/$branch"
else
    git -C "$repo" checkout -q -B "$branch" origin/main
fi
[ -f "$repo/decisions/$vm.json" ] || echo '{}' > "$repo/decisions/$vm.json"
# Inventaire de référence de la CI (sans contenu de fichiers) : toujours celui
# de l'audit qui a produit le code, sinon la comparaison juge une copie neuve
# contre un original périmé.
mkdir -p "$repo/inventaires" && cp "$refinv" "$repo/inventaires/$vm.json"
# Démo « premier audit » : BS_A_ZERO=1 efface les décisions humaines sur les
# éléments inconnus (les 5 restent en attente). Les décisions sur les données
# (data:*, prises après une CI) sont gardées.
if [ -n "${BS_A_ZERO:-}" ]; then
    python3 -I -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p))
json.dump({k: v for k, v in d.items() if k.startswith("data:")}, open(p, "w"), indent=2, ensure_ascii=False)' \
        "$repo/decisions/$vm.json"
fi
# Propositions du modèle local (bs-ia) pour les inconnus : indicatives, mises en
# cache dans decisions/<vm>.propositions.json (rappel seulement si les preuves changent).
props="$repo/decisions/$vm.propositions.json"
# BS_SANS_CACHE=1 : le modèle répond en direct même si les preuves n'ont pas changé (démo).
[ -n "${BS_SANS_CACHE:-}" ] && rm -f "$props"
# BS_CACHE_PREPARE=F : propositions calculées pendant la préparation de la démo (même audit,
# mêmes preuves). bs-classify ne les reprend que si l'empreinte des preuves est identique.
[ -n "${BS_CACHE_PREPARE:-}" ] && [ -f "$BS_CACHE_PREPARE" ] && cp "$BS_CACHE_PREPARE" "$props"
if [ -n "${BS_OLLAMA:-}" ]; then
    python3 -I classement/bs-classify "$ref" "$cur" --proposer "$BS_OLLAMA" --propositions "$props"
fi
python3 -I generation/bs-generate "$ref" "$cur" "$repo/$vm" --decisions "$repo/decisions/$vm.json" --propositions "$props"
git -C "$repo" add -A
if git -C "$repo" diff --cached --quiet; then
    echo "rien de nouveau à pousser"
else
    git -C "$repo" commit -q -m "$msg

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
    git -C "$repo" push -q ${BS_NOUVELLE_MR:+--force} -u origin "$branch" 2>&1 | sed 's/[0-9a-f]\{40\}/<jeton>/g'
    git -C "$repo" log --oneline -1
fi
python3 -I - "$vm" "$branch" <<'EOF'
import sys
sys.path.insert(0, "infra")
from forge import Forge
vm, branch = sys.argv[1], sys.argv[2]
f = Forge()
prs = [p for p in f.call("GET", "/repos/pme/infra/pulls?state=open") if p["head"]["ref"] == branch]
body = ("Code Ansible généré par Black Start depuis l'inventaire de l'audit. "
        "La CI reconstruit la VM en sandbox, restaure les données et compare avec l'original.\n\n"
        + open(f"forge/pme-infra/{vm}/DECISIONS.md", encoding="utf-8").read())
if prs:
    f.call("PATCH", f"/repos/pme/infra/pulls/{prs[0]['number']}", {"body": body})
    print(f"merge request existante, description à jour : {prs[0]['html_url']}")
else:
    pr = f.call("POST", "/repos/pme/infra/pulls", {
        "title": f"Reconstruction de {vm} depuis le code",
        "head": branch, "base": "main", "body": body})
    print(f"merge request ouverte : {pr['html_url']}")
EOF
