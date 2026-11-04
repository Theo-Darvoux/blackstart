#!/usr/bin/env bash
# Serveur de sauvegarde de la PME : un compte SFTP qui reçoit le dépôt restic
# du logiciel de logistique. La clé ne permet que SFTP.
set -euo pipefail
d="$1"
pub="$(cat "$d/secrets/sauvegarde_ed25519.pub")"

id sauvegarde >/dev/null 2>&1 || \
    useradd --system --home-dir /srv/sauvegardes --create-home --shell /bin/sh sauvegarde
install -d -m 0700 -o sauvegarde -g sauvegarde /srv/sauvegardes/.ssh /srv/sauvegardes/logistique /srv/sauvegardes/mail
printf 'restrict,command="/usr/lib/openssh/sftp-server" %s\n' "$pub" > /srv/sauvegardes/.ssh/authorized_keys
chown sauvegarde:sauvegarde /srv/sauvegardes/.ssh/authorized_keys
chmod 0600 /srv/sauvegardes/.ssh/authorized_keys
echo "sauvegarde : OK"
