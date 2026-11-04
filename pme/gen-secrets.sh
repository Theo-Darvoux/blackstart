#!/usr/bin/env bash
# Génère les secrets de la PME fictive dans pme/secrets/ (ignoré par Git).
# Ce dossier joue le rôle du coffre : sans lui, les sauvegardes restic sont
# illisibles. Ne pas le régénérer une fois la PME installée.
set -euo pipefail
dir="$(cd "$(dirname "$0")" && pwd)/secrets"
gen() { python3 -c 'import secrets; print(secrets.token_urlsafe(24))'; }
if [ -f "$dir/secrets.env" ]; then
    # Coffre déjà là : on n'y touche pas, on ajoute seulement les secrets apparus depuis.
    for k in RESTIC_MAIL_PASSWORD; do
        grep -q "^$k=" "$dir/secrets.env" || { (umask 077; echo "$k=$(gen)" >> "$dir/secrets.env"); echo "secret ajouté : $k" >&2; }
    done
    exit 0
fi
umask 077
mkdir -p "$dir"
gen() { python3 -c 'import secrets; print(secrets.token_urlsafe(24))'; }
cat > "$dir/secrets.env" <<EOF
DB_PASSWORD=$(gen)
IMAP_PASSWORD=$(gen)
RESTIC_PASSWORD=$(gen)
RESTIC_MAIL_PASSWORD=$(gen)
EOF
ssh-keygen -q -t ed25519 -N "" -C "sauvegarde-logistique" -f "$dir/sauvegarde_ed25519"
echo "Secrets générés dans $dir" >&2
