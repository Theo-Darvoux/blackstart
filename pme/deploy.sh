#!/usr/bin/env bash
# Installe un rôle de la PME fictive sur sa VM, par SSH (compte claude + sudo).
#
#   pme/deploy.sh mail|proxy|sauvegarde|logistique|pieges
#
# Ordre conseillé : mail, proxy, sauvegarde, logistique, puis pieges.
# Chaque script est idempotent : on peut le relancer.
set -euo pipefail
cd "$(dirname "$0")"
source ./pme.env
./gen-secrets.sh 2>/dev/null || true

role="${1:?usage: deploy.sh mail|proxy|sauvegarde|logistique|pieges}"
case "$role" in
    mail)       ip=$MAIL_IP;       needs="IMAP_PASSWORD"; keys=() ;;
    proxy)      ip=$PROXY_IP;      needs="";              keys=() ;;
    sauvegarde) ip=$SAUVEGARDE_IP; needs="";              keys=(sauvegarde_ed25519.pub) ;;
    logistique) ip=$LOGISTIQUE_IP; needs="DB_PASSWORD RESTIC_PASSWORD"; keys=(sauvegarde_ed25519) ;;
    pieges)     ip=$LOGISTIQUE_IP; needs="";              keys=() ;;
    *) echo "rôle inconnu : $role" >&2; exit 2 ;;
esac

# On n'envoie à chaque VM que les secrets dont elle a besoin.
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
cp -r pme.env "$role" "$stage/"
mkdir -m 700 "$stage/secrets"
: > "$stage/secrets/secrets.env"
for k in $needs; do grep "^$k=" secrets/secrets.env >> "$stage/secrets/secrets.env"; done
for f in "${keys[@]}"; do cp "secrets/$f" "$stage/secrets/"; done

key="${ADMIN_KEY:-$HOME/.ssh/id_blackstart_admin}"
echo "== $role sur $ip" >&2
tar -C "$stage" -czf - . | ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$key" "claude@$ip" \
    'd=$(mktemp -d) && tar -xzf - -C "$d" && sudo bash "$d/'"$role"'/setup.sh" "$d"; rc=$?; sudo rm -rf "$d"; exit $rc'
