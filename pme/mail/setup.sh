#!/usr/bin/env bash
# bs-mail : Postfix (SMTP) + Dovecot (IMAP) pour le domaine de la PME.
# Aucun envoi vers l'extérieur : tout ce qui ne va pas vers @$DOMAIN est rejeté.
set -euo pipefail
d="$1"; source "$d/pme.env"; source "$d/secrets/secrets.env"
export DEBIAN_FRONTEND=noninteractive

echo "postfix postfix/main_mailer_type select Internet Site" | debconf-set-selections
echo "postfix postfix/mailname string $DOMAIN" | debconf-set-selections
apt-get -qq update
apt-get -qq install -y postfix dovecot-imapd >/dev/null

postconf -e \
    "myhostname = mail.$DOMAIN" \
    "mydomain = $DOMAIN" \
    "myorigin = $DOMAIN" \
    "mydestination = mail.$DOMAIN, $DOMAIN, localhost" \
    "mynetworks = 127.0.0.0/8 $LOGISTIQUE_IP/32" \
    "inet_interfaces = all" \
    "inet_protocols = ipv4" \
    "smtpd_relay_restrictions = permit_mynetworks, reject_unauth_destination" \
    "default_transport = error:5.7.1 envoi externe desactive (laboratoire)" \
    "relay_transport = error:5.7.1 envoi externe desactive (laboratoire)"

# Boîte qui reçoit les confirmations de commande.
id commandes >/dev/null 2>&1 || useradd --create-home --shell /usr/sbin/nologin commandes
echo "commandes:$IMAP_PASSWORD" | chpasswd
grep -q '^expedition:' /etc/aliases || echo "expedition: commandes" >> /etc/aliases
newaliases

systemctl enable --quiet postfix dovecot
systemctl restart postfix dovecot

# --- sauvegarde des boîtes (ajoutée le 3 novembre) ------------------------------
# Même serveur et même compte SFTP que la logistique, dépôt restic séparé.
# L'état de Postfix et Dovecot (files d'attente, verrous) n'est pas sauvegardé :
# il se régénère, et le restaurer sur une installation neuve casserait les services.
apt-get -qq install -y restic >/dev/null
install -d -m 0700 /root/.ssh /etc/restic
install -m 0600 "$d/secrets/sauvegarde_ed25519" /root/.ssh/id_sauvegarde
grep -q "$SAUVEGARDE_IP" /root/.ssh/known_hosts 2>/dev/null || \
    ssh-keyscan -q -t ed25519 "$SAUVEGARDE_IP" >> /root/.ssh/known_hosts
printf 'Host %s\n    User sauvegarde\n    IdentityFile /root/.ssh/id_sauvegarde\n    IdentitiesOnly yes\n' \
    "$SAUVEGARDE_IP" > /root/.ssh/config
printf '%s\n' "$RESTIC_MAIL_PASSWORD" > /etc/restic/mail.pass
chmod 0600 /etc/restic/mail.pass
printf 'RESTIC_REPOSITORY=sftp:%s:/srv/sauvegardes/mail\nRESTIC_PASSWORD_FILE=/etc/restic/mail.pass\n' \
    "$SAUVEGARDE_IP" > /etc/restic/mail.env
install -m 0755 "$d/mail/sauvegarde-mail" /usr/local/sbin/sauvegarde-mail
echo "45 2 * * * root /usr/local/sbin/sauvegarde-mail" > /etc/cron.d/sauvegarde-mail
set -a; . /etc/restic/mail.env; set +a
restic cat config >/dev/null 2>&1 || restic init --quiet
/usr/local/sbin/sauvegarde-mail
echo "mail : OK"
