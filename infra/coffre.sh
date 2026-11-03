#!/usr/bin/env bash
# Remplit le coffre de bs-gitlab (/srv/coffre/<vm>, lisible par le runner CI
# seulement) avec les fichiers secrets et les artefacts « inconnus » listés par
# bs-generate (coffre.txt), lus sur la VM d'origine. Les secrets passent par un
# tube SSH : ils ne sont jamais écrits sur le poste ni dans Git.
#
#   infra/coffre.sh 192.168.103.200 bs-logistique depot/bs-logistique/coffre.txt [chemin...]
set -euo pipefail
src_ip="$1"; vm="$2"; list="$3"; shift 3
key="${ADMIN_KEY:-$HOME/.ssh/id_blackstart_admin}"
forge="${FORGE_IP:-192.168.103.203}"
ssh_vm() { ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$key" "claude@$1" "${@:2}"; }

paths=$( { grep -v '^#' "$list"; printf '%s\n' "$@"; } | sed '/^$/d' | sort -u)
echo "== coffre de $vm : $(echo "$paths" | wc -l) chemins depuis $src_ip" >&2
ssh_vm "$src_ip" "sudo tar -C / -cpzf - $(echo "$paths" | sed 's#^/##' | tr '\n' ' ')" \
  | ssh_vm "$forge" "sudo install -d -m 0700 -o runner -g runner /srv/coffre /srv/coffre/$vm && sudo tar -C /srv/coffre/$vm --no-same-owner -xzf - && sudo chown -R runner:runner /srv/coffre/$vm && sudo chmod -R u+rwX,go-rwx /srv/coffre/$vm && sudo find /srv/coffre/$vm -type f | sed 's#^/srv/coffre/$vm##'"
