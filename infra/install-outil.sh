#!/usr/bin/env bash
# Installe (ou met à jour) l'outil Black Start sur bs-gitlab dans /opt/blackstart,
# et ses secrets Proxmox dans /etc/blackstart (lisibles par le runner CI seul).
set -euo pipefail
cd "$(dirname "$0")/.."
key="${ADMIN_KEY:-$HOME/.ssh/id_blackstart_admin}"
forge="${FORGE_IP:-192.168.103.203}"
ssh_forge() { ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$key" "claude@$forge" "$@"; }

tar -czf - collecte/bs-collect collecte/bs-compare collecte/install-on-vm.sh collecte/regles \
    classement/bs-classify generation/bs-generate generation/modeles \
    infra/pve.py infra/sandbox.py infra/ci-verifier.sh infra/ci-rapport.py infra/runner-ci.pub infra/admin-claude.pub \
    banc/test-metier.py \
  | ssh_forge 'sudo rm -rf /opt/blackstart.new && sudo install -d /opt/blackstart.new && sudo tar -C /opt/blackstart.new --no-same-owner -xzf - && sudo chmod -R a+rX /opt/blackstart.new && sudo rm -rf /opt/blackstart && sudo mv /opt/blackstart.new /opt/blackstart && sudo find /opt/blackstart -type f | wc -l'
tar -C infra/secrets -czf - proxmox.env pve-root-ca.pem \
  | ssh_forge 'sudo install -d -m 0700 -o runner -g runner /etc/blackstart && sudo tar -C /etc/blackstart --no-same-owner -xzf - && sudo chown -R runner:runner /etc/blackstart && sudo chmod 0600 /etc/blackstart/proxmox.env /etc/blackstart/pve-root-ca.pem && echo "secrets Proxmox installés pour le runner"'
