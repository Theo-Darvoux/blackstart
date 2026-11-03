#!/usr/bin/env bash
# bs-logistique : logiciel de logistique (Flask + Gunicorn) sur PostgreSQL,
# avec sauvegarde quotidienne de la base vers le serveur de sauvegarde (restic/SFTP).
set -euo pipefail
d="$1"; source "$d/pme.env"; source "$d/secrets/secrets.env"
export DEBIAN_FRONTEND=noninteractive

apt-get -qq update
apt-get -qq install -y postgresql python3-flask python3-psycopg gunicorn restic curl >/dev/null

# --- base de données ---------------------------------------------------------
runuser -u postgres -- psql -qtAc "SELECT 1 FROM pg_roles WHERE rolname = 'logistique'" | grep -q 1 || \
    runuser -u postgres -- psql -q -c "CREATE ROLE logistique LOGIN"
runuser -u postgres -- psql -q -c "ALTER ROLE logistique PASSWORD '$DB_PASSWORD'"
runuser -u postgres -- psql -qtAc "SELECT 1 FROM pg_database WHERE datname = 'logistique'" | grep -q 1 || \
    runuser -u postgres -- createdb -O logistique logistique
PGPASSWORD="$DB_PASSWORD" psql -q -h 127.0.0.1 -U logistique logistique -f "$d/logistique/app/schema.sql"

# --- application ----------------------------------------------------------------
id logistique >/dev/null 2>&1 || \
    useradd --system --home-dir /opt/logistique --shell /usr/sbin/nologin logistique
install -d -m 0755 /opt/logistique /opt/logistique/app
install -m 0644 "$d/logistique/app/logistique.py" /opt/logistique/app/logistique.py

install -d -m 0750 -o root -g logistique /etc/logistique
cat > /etc/logistique/logistique.conf <<EOF
[base]
dsn = host=127.0.0.1 dbname=logistique user=logistique password=$DB_PASSWORD

[mail]
smtp_host = $MAIL_IP
smtp_port = 25
expediteur = logistique@$DOMAIN
destinataire = commandes@$DOMAIN
EOF
chown root:logistique /etc/logistique/logistique.conf
chmod 0640 /etc/logistique/logistique.conf

cat > /etc/systemd/system/logistique.service <<'EOF'
[Unit]
Description=Logiciel de logistique
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
User=logistique
Group=logistique
WorkingDirectory=/opt/logistique/app
Environment=LOGISTIQUE_CONF=/etc/logistique/logistique.conf
ExecStart=/usr/bin/gunicorn --bind 0.0.0.0:8000 --workers 2 --access-logfile - logistique:app
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --quiet logistique
systemctl restart logistique

# --- sauvegarde ------------------------------------------------------------------
install -d -m 0700 /root/.ssh /etc/restic
install -m 0600 "$d/secrets/sauvegarde_ed25519" /root/.ssh/id_sauvegarde
grep -q "$SAUVEGARDE_IP" /root/.ssh/known_hosts 2>/dev/null || \
    ssh-keyscan -q -t ed25519 "$SAUVEGARDE_IP" >> /root/.ssh/known_hosts
cat > /root/.ssh/config <<EOF
Host $SAUVEGARDE_IP
    User sauvegarde
    IdentityFile /root/.ssh/id_sauvegarde
    IdentitiesOnly yes
EOF
printf '%s\n' "$RESTIC_PASSWORD" > /etc/restic/logistique.pass
chmod 0600 /etc/restic/logistique.pass
cat > /etc/restic/logistique.env <<EOF
RESTIC_REPOSITORY=sftp:$SAUVEGARDE_IP:/srv/sauvegardes/logistique
RESTIC_PASSWORD_FILE=/etc/restic/logistique.pass
EOF

cat > /usr/local/sbin/sauvegarde-logistique <<'EOF'
#!/bin/sh
# Sauvegarde quotidienne de la base logistique vers le serveur de sauvegarde.
set -eu
set -a; . /etc/restic/logistique.env; set +a
mkdir -p /var/backups/logistique
runuser -u postgres -- pg_dump -Fc logistique > /var/backups/logistique/logistique.dump
restic backup --quiet --tag logistique /var/backups/logistique
restic forget --quiet --keep-daily 7 --keep-weekly 4 --prune
EOF
chmod 0755 /usr/local/sbin/sauvegarde-logistique
echo "30 2 * * * root /usr/local/sbin/sauvegarde-logistique" > /etc/cron.d/sauvegarde-logistique

set -a; . /etc/restic/logistique.env; set +a
restic cat config >/dev/null 2>&1 || restic init --quiet
/usr/local/sbin/sauvegarde-logistique

for i in $(seq 1 20); do
    curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break
    sleep 1
done
curl -fsS http://127.0.0.1:8000/health
echo
echo "logistique : OK"
