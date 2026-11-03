#!/usr/bin/env bash
# Prépare une VM Debian 13 pour la collecte Black Start. À lancer en root sur
# la VM, après avoir copié bs-collect dans /usr/local/sbin/bs-collect.
#
#   sudo bash install-on-vm.sh 'ssh-ed25519 AAAA... commentaire'
#
# Commandes complètes depuis le poste : voir collecte/README.md.
#
# Résultat : un compte `bs-collect` qui ne peut lancer qu'une chose par SSH,
# la collecte (commande forcée), et qui n'a droit à root que pour elle (sudoers).
set -euo pipefail

pubkey="${1:?usage: install-on-vm.sh 'ssh-ed25519 AAAA... commentaire'}"
bin=/usr/local/sbin/bs-collect
wrapper=/usr/local/sbin/bs-collect-ssh

[ -f "$bin" ] || { echo "copier d'abord bs-collect dans $bin" >&2; exit 1; }
chown root:root "$bin"
chmod 0755 "$bin"

missing=()
for pkg in python3 iproute2; do
    dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if [ "${#missing[@]}" -gt 0 ]; then
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}"
fi

id bs-collect >/dev/null 2>&1 || \
    useradd --system --home-dir /var/lib/bs-collect --create-home --shell /bin/sh bs-collect

cat > "$wrapper" <<'EOF'
#!/bin/sh
# Commande forcée du compte bs-collect : seule la collecte est acceptée.
case "${SSH_ORIGINAL_COMMAND:-}" in
    ""|bs-collect) exec sudo -n /usr/local/sbin/bs-collect ;;
    "bs-collect --with-content") exec sudo -n /usr/local/sbin/bs-collect --with-content ;;
    *) echo "bs-collect : commande refusée" >&2; exit 1 ;;
esac
EOF
chown root:root "$wrapper"
chmod 0755 "$wrapper"

install -d -m 0700 -o bs-collect -g bs-collect /var/lib/bs-collect/.ssh
printf 'restrict,command="%s" %s\n' "$wrapper" "$pubkey" > /var/lib/bs-collect/.ssh/authorized_keys
chown bs-collect:bs-collect /var/lib/bs-collect/.ssh/authorized_keys
chmod 0600 /var/lib/bs-collect/.ssh/authorized_keys

tmp="$(mktemp)"
echo 'bs-collect ALL=(root) NOPASSWD: /usr/local/sbin/bs-collect "", /usr/local/sbin/bs-collect --with-content' > "$tmp"
visudo -cf "$tmp" >/dev/null
install -m 0440 -o root -g root "$tmp" /etc/sudoers.d/bs-collect
rm -f "$tmp"

ip="$(hostname -I | awk '{print $1}')"
echo "OK : collecte prête. Depuis votre poste : ssh bs-collect@$ip > inventaires/$ip.json"
