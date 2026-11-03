#!/usr/bin/env bash
# Test rapide de bs-collect dans un conteneur Debian 13 jetable, avec les
# pièges du banc de test. Pas de systemd dans le conteneur : la section
# systemd doit apparaître dans `unreadable`, pas faire planter le script.
#
# Usage : collecte/tests/docker-smoke.sh [fichier_de_sortie.json]
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
out="${1:-$(mktemp --suffix=.json)}"

docker run --rm -i -v "$here/bs-collect:/usr/local/sbin/bs-collect:ro" debian:trixie bash -s > "$out" <<'EOF'
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get -qq update >/dev/null
apt-get -qq install -y --no-install-recommends python3 iproute2 nginx cron nftables >/dev/null 2>&1

# Piège 1 : fichier de configuration modifié
sed -i 's/worker_connections 768/worker_connections 2048/' /etc/nginx/nginx.conf
# Piège 2 : IP codée en dur
sed -i 's|^\s*location / {|location / {\n\t\tproxy_pass http://10.42.0.17:8069;|' /etc/nginx/sites-available/default
# Piège 3 : binaire dans /opt
mkdir -p /opt/logistique && cp /usr/bin/true /opt/logistique/export-edi && chmod 755 /opt/logistique/export-edi
# Piège 4 : cron oublié dans la crontab de root
mkdir -p /var/spool/cron/crontabs
printf '*/15 * * * * /opt/logistique/export-edi --push\n' > /var/spool/cron/crontabs/root
chmod 600 /var/spool/cron/crontabs/root
# Piège 5 : sauvegarde mensuelle
printf '#!/bin/sh\npg_dump logistique > /srv/backup/logistique.sql\n' > /etc/cron.monthly/backup-logistique
chmod 755 /etc/cron.monthly/backup-logistique
# Secret : ne doit jamais apparaître en clair
mkdir -p /etc/ssl/private && printf -- '-----BEGIN PRIVATE KEY-----\nSECRETSECRET\n-----END PRIVATE KEY-----\n' > /etc/nginx/demo.pem
mkdir -p /etc/sssd && printf '[domain/x]\nldap_default_authtok = SECRETSECRET\n' > /etc/sssd/sssd.conf && chmod 600 /etc/sssd/sssd.conf

nginx >/dev/null 2>&1 || true
/usr/local/sbin/bs-collect --with-content
EOF

echo "Inventaire : $out ($(wc -c < "$out") octets)" >&2

python3 - "$out" <<'PY'
import json, sys
inv = json.load(open(sys.argv[1]))
raw = open(sys.argv[1]).read()
checks = {
    "nginx.conf modifié détecté": any(f["path"] == "/etc/nginx/nginx.conf" for f in inv["modified_files"]),
    "IP 10.42.0.17 relevée": any(h["ip"] == "10.42.0.17" for f in inv["modified_files"] + inv["unowned"]["files"] for h in f.get("ip_literals", [])),
    "binaire /opt détecté": any(f["path"] == "/opt/logistique/export-edi" for f in inv["unowned"]["files"]),
    "cron root détecté": any(f["path"] == "/var/spool/cron/crontabs/root" and f.get("entries") for f in inv["cron"]["files"]),
    "sauvegarde mensuelle détectée": any(f["path"] == "/etc/cron.monthly/backup-logistique" for f in inv["cron"]["files"]),
    "secret non embarqué": "SECRETSECRET" not in raw,
    "port 80 en écoute": any(l["port"] == 80 for l in inv["listening"]),
    "systemd signalé illisible": any(u["section"] == "systemd" for u in inv["unreadable"]),
}
for name, ok in checks.items():
    print(("OK   " if ok else "ÉCHEC"), name)
print(f"{len(inv['unowned']['files'])} fichiers hors paquet, {len(inv['unowned']['ignored'])} ignorés, "
      f"{len(inv['modified_files'])} modifiés, {len(inv['unreadable'])} illisibles")
sys.exit(0 if all(checks.values()) else 1)
PY
