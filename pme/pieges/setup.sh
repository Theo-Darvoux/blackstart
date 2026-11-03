#!/usr/bin/env bash
# Pièges du banc de mesure, posés sur bs-logistique après l'installation des
# services. Chacun imite une modification faite à la main et jamais documentée.
# Le corrigé est dans banc/pieges.json. Ne jamais montrer ce fichier ni le
# corrigé à l'outil Black Start.
set -euo pipefail
d="$1"; source "$d/pme.env"

# P1 : cron oublié dans la crontab de root (export EDI vers le transporteur)
install -d -m 0755 /opt/logistique/bin /srv/edi/sortant
cat > /opt/logistique/bin/export-edi <<'EOF'
#!/bin/sh
# Export EDI des commandes confirmées vers le transporteur (prestataire, 2023)
out=/srv/edi/sortant/$(date +%Y%m%d%H%M).csv
runuser -u postgres -- psql -At -F';' logistique -c \
  "SELECT ref, client, sku, quantite FROM commandes WHERE statut = 'confirmée' AND cree_le > now() - interval '10 minutes'" > "$out"
[ -s "$out" ] || rm -f "$out"
/opt/etiquettes/bin/zpl-print < /dev/null > /dev/null 2>&1 || true
EOF
chmod 0755 /opt/logistique/bin/export-edi
line='*/10 * * * * /opt/logistique/bin/export-edi'
{ crontab -l 2>/dev/null | grep -vF "$line" || true; echo "$line"; } | crontab -

# P2 : fichier de configuration d'un paquet modifié (limits.conf, paquet libpam-modules)
grep -q '^logistique soft nofile' /etc/security/limits.conf || \
    echo 'logistique soft nofile 65535' >> /etc/security/limits.conf

# P3 : binaire opaque dans /opt (« pilote d'étiqueteuse » fourni par un éditeur)
install -d -m 0755 /opt/etiquettes/bin
install -m 0755 /usr/bin/base64 /opt/etiquettes/bin/zpl-print

# P4 : sauvegarde mensuelle (archivage des commandes de plus d'un an, hors restic)
cat > /usr/local/sbin/archive-commandes <<'EOF'
#!/bin/sh
# Archive mensuelle des commandes de plus d'un an, puis purge de la base.
set -eu
mkdir -p /srv/archives
f=/srv/archives/commandes-$(date +%Y%m).csv
runuser -u postgres -- psql -At -F';' logistique -c "SELECT * FROM commandes WHERE cree_le < now() - interval '1 year'" > "$f"
gzip -f "$f"
runuser -u postgres -- psql -q logistique -c "DELETE FROM commandes WHERE cree_le < now() - interval '1 year'"
EOF
chmod 0755 /usr/local/sbin/archive-commandes
echo "0 4 1 * * root /usr/local/sbin/archive-commandes" > /etc/cron.d/archive-mensuelle

# P5 : IP codée en dur. Déjà présente : smtp_host = $MAIL_IP dans
# /etc/logistique/logistique.conf. Rien à poser ici.

# P6 : réglage noyau fait à chaud, jamais persisté
sysctl -qw vm.swappiness=10

# P7 : tâche annuelle (timer systemd du 31 décembre)
cat > /etc/systemd/system/inventaire-annuel.service <<'EOF'
[Unit]
Description=Inventaire annuel des stocks

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'mkdir -p /srv/archives && runuser -u postgres -- psql -At logistique -c "SELECT sku, stock FROM produits" > /srv/archives/inventaire-$(date +%%Y).txt'
EOF
cat > /etc/systemd/system/inventaire-annuel.timer <<'EOF'
[Unit]
Description=Inventaire annuel des stocks (31 décembre)

[Timer]
OnCalendar=*-12-31 23:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --quiet --now inventaire-annuel.timer

# P8 : processus lancé à la main et laissé tourner (relais HTTP pour le transporteur)
if ! ss -Htln 'sport = :9100' | grep -q .; then
    setsid -f python3 -m http.server 9100 --directory /srv/edi/sortant > /var/log/relais-transporteur.log 2>&1 < /dev/null
fi

# P9 : compte de prestataire créé à la main, avec un droit sudo
id prestataire >/dev/null 2>&1 || useradd --create-home --shell /bin/bash prestataire
install -d -m 0700 -o prestataire -g prestataire /home/prestataire/.ssh
if [ ! -s /home/prestataire/.ssh/authorized_keys ]; then
    tmp="$(mktemp -d)"
    ssh-keygen -q -t ed25519 -N "" -C "prestataire@edi" -f "$tmp/k"
    install -m 0600 -o prestataire -g prestataire "$tmp/k.pub" /home/prestataire/.ssh/authorized_keys
    rm -rf "$tmp"
fi
echo 'prestataire ALL=(root) NOPASSWD: /usr/bin/systemctl restart logistique' > /etc/sudoers.d/prestataire
chmod 0440 /etc/sudoers.d/prestataire
visudo -cq

# P10 : dépendance implicite dans /etc/hosts (nom du transporteur)
grep -q 'edi.transporteur.test' /etc/hosts || echo "$PROXY_IP edi.transporteur.test" >> /etc/hosts

echo "pieges : OK (10 pièges posés)"
