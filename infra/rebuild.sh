#!/usr/bin/env bash
# Applique le code généré (depot/<vm>) sur une VM cible, depuis bs-gitlab, avec
# le runner CI et le coffre. Même chemin que la future CI.
#
#   infra/rebuild.sh bs-logistique 192.168.103.210
set -euo pipefail
cd "$(dirname "$0")/.."
vm="$1"; target="$2"
key="${ADMIN_KEY:-$HOME/.ssh/id_blackstart_admin}"
forge="${FORGE_IP:-192.168.103.203}"
ssh_forge() { ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$key" "claude@$forge" "$@"; }

tar -C depot -czf - "$vm" | ssh_forge "sudo rm -rf /var/lib/forgejo-runner/depot/$vm && sudo install -d -o runner -g runner /var/lib/forgejo-runner/depot && sudo tar -C /var/lib/forgejo-runner/depot -xzf - && sudo chown -R runner:runner /var/lib/forgejo-runner/depot/$vm"
ssh_forge "sudo -u runner bash -c 'cd /var/lib/forgejo-runner/depot/$vm && start=\$(date +%s) && export ANSIBLE_HOST_KEY_CHECKING=False ANSIBLE_NOCOLOR=1 ANSIBLE_PYTHON_INTERPRETER=/usr/bin/python3 COFFRE=/srv/coffre/$vm && ansible-playbook -i $target, -u claude playbook.yml > ansible.log 2>&1 && { [ ! -f restauration.yml ] || ansible-playbook -i $target, -u claude restauration.yml >> ansible.log 2>&1; }; rc=\$?; grep -E \"^(TASK|fatal|PLAY RECAP|$target)\" ansible.log | grep -B1 -E \"fatal|$target\" | tail -12; echo \"ansible : code \$rc en \$(( \$(date +%s) - start )) s\"; exit \$rc'"
