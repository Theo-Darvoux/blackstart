#!/usr/bin/env bash
# bs-proxy : Nginx (reverse proxy vers le logiciel de logistique) + Unbound
# (zone DNS interne de la PME).
set -euo pipefail
d="$1"; source "$d/pme.env"
export DEBIAN_FRONTEND=noninteractive

apt-get -qq update
apt-get -qq install -y nginx unbound >/dev/null

cat > /etc/nginx/sites-available/logistique <<EOF
server {
    listen 80;
    server_name logistique.$DOMAIN;
    client_max_body_size 5m;

    location / {
        proxy_pass http://$LOGISTIQUE_IP:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_read_timeout 30s;
    }
}
EOF
ln -sf /etc/nginx/sites-available/logistique /etc/nginx/sites-enabled/logistique
nginx -t -q

{
    echo "server:"
    echo "    interface: 0.0.0.0"
    echo "    access-control: 127.0.0.0/8 allow"
    echo "    access-control: $SUBNET allow"
    echo "    local-zone: \"$DOMAIN.\" static"
    echo "    local-data: \"$DOMAIN. IN MX 10 mail.$DOMAIN.\""
    echo "    local-data: \"mail.$DOMAIN. IN A $MAIL_IP\""
    echo "    local-data: \"proxy.$DOMAIN. IN A $PROXY_IP\""
    echo "    local-data: \"logistique.$DOMAIN. IN A $PROXY_IP\""
    echo "    local-data: \"app.$DOMAIN. IN A $LOGISTIQUE_IP\""
    echo "forward-zone:"
    echo "    name: \".\""
    for ns in $UPSTREAM_DNS; do echo "    forward-addr: $ns"; done
} > /etc/unbound/unbound.conf.d/pme.conf
unbound-checkconf >/dev/null

systemctl enable --quiet nginx unbound
systemctl restart nginx unbound
echo "proxy : OK"
