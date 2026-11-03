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
echo "mail : OK"
