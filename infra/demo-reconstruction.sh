#!/usr/bin/env bash
# Parcours complet de la démo, chronométré : sandbox neuve -> code généré ->
# données restaurées -> test métier -> comparaison avec l'original.
#
#   infra/demo-reconstruction.sh [vmid] [ip]      (défaut : 1650 192.168.103.210)
set -euo pipefail
cd "$(dirname "$0")/.."
vmid="${1:-1650}"; ip="${2:-192.168.103.210}"; vm=bs-logistique; sbx=sbx-logistique
key="$HOME/.ssh/id_blackstart_admin"
out="banc/resultats/demo-$(date +%Y%m%d-%H%M)"
mkdir -p "$out"
t0=$(date +%s); lap() { echo "== [$(( $(date +%s) - t0 )) s] $*"; }

lap "sandbox : destruction de l'ancienne si présente"
python3 -I infra/sandbox.py destroy "$vmid" 2>/dev/null || true
lap "sandbox : création ($sbx, $vmid, $ip)"
python3 -I infra/sandbox.py create "$sbx" "$vmid" "$ip"
lap "reconstruction depuis le code généré + restauration des données"
infra/rebuild.sh "$vm" "$ip"
t_rebuild=$(( $(date +%s) - t0 ))
lap "test métier dans la sandbox"
banc/test-metier.py --app "$ip:8000" --isole --json "$out/test-metier.json"
lap "collecte sur la copie et comparaison avec l'original"
scp -q -o BatchMode=yes -o IdentitiesOnly=yes -i "$key" collecte/bs-collect collecte/install-on-vm.sh "claude@$ip:"
ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$key" "claude@$ip" \
    "sudo install -o root -g root -m 0755 bs-collect /usr/local/sbin/bs-collect && sudo bash install-on-vm.sh '$(cat ~/.ssh/id_blackstart.pub)' >/dev/null && rm bs-collect install-on-vm.sh"
ssh -T -i ~/.ssh/id_blackstart -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new "bs-collect@$ip" > "inventaires/$sbx.json"
collecte/bs-compare --identity "inventaires/$vm-pieges.json" "inventaires/$sbx.json" --json "$out/comparaison.json" || true
lap "terminé : reconstruction en $t_rebuild s, résultats dans $out"
