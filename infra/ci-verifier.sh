#!/usr/bin/env bash
# Vérification d'une merge request de reconstruction, lancée par la CI Forgejo
# sur bs-gitlab (compte runner). Même parcours que infra/demo-reconstruction.sh :
# sandbox neuve -> code de la branche -> données restaurées -> test métier ->
# comparaison avec l'inventaire de référence de l'original.
#
#   /opt/blackstart/infra/ci-verifier.sh bs-logistique /chemin/du/depot
# Code de sortie 1 s'il reste un écart non justifié : la merge request est bloquée.
set -uo pipefail
vm="$1"; repo="$(cd "$2" && pwd)"
T="${BS_TOOL:-/opt/blackstart}"
vmid="${SBX_VMID:-1650}"; ip="${SBX_IP:-192.168.103.210}"; sbx="sbx-${vm#bs-}"
out="$repo/.rapport"; mkdir -p "$out"
export BS_SECRETS="${BS_SECRETS:-/etc/blackstart}" BS_ADMIN_KEY="${BS_ADMIN_KEY:-$HOME/.ssh/id_ed25519}"
export ANSIBLE_HOST_KEY_CHECKING=False ANSIBLE_NOCOLOR=1 ANSIBLE_PYTHON_INTERPRETER=/usr/bin/python3 COFFRE="/srv/coffre/$vm"
SSH=(ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -i "$BS_ADMIN_KEY")
t0=$(date +%s); declare -A dur
step() { local name="$1"; shift; local t=$(date +%s); echo "== $name"; "$@"; local rc=$?; dur[$name]=$(( $(date +%s) - t )); echo "   ($name : ${dur[$name]} s, code $rc)"; return $rc; }
fail() { echo "ÉCHEC : $*"; printf '{"etape_en_echec": "%s"}\n' "$*" > "$out/echec.json"; exit 2; }

step sandbox bash -c "python3 -I '$T/infra/sandbox.py' destroy $vmid >/dev/null 2>&1; python3 -I '$T/infra/sandbox.py' create '$sbx' $vmid $ip" || fail "création de la sandbox"
step reconstruction bash -c "cd '$repo/$vm' && ansible-playbook -i $ip, -u claude playbook.yml > '$out/ansible.log' 2>&1 && tail -3 '$out/ansible.log'" || fail "playbook de reconstruction (voir ansible.log)"
step restauration bash -c "cd '$repo/$vm' && ansible-playbook -i $ip, -u claude restauration.yml >> '$out/ansible.log' 2>&1 && grep -o 'base [^\"]*' '$out/ansible.log' | tail -1" || fail "restauration des données (voir ansible.log)"
step redemarrage bash -c "${SSH[*]} claude@$ip 'sudo systemctl reboot' >/dev/null 2>&1; sleep 10; for i in \$(seq 1 60); do curl -fsS -o /dev/null http://$ip:8000/health 2>/dev/null && exit 0; sleep 3; done; echo 'app injoignable après redémarrage'; exit 1" || fail "l'app ne redémarre pas (configuration qui ne survit pas à un redémarrage)"
step test_metier python3 -I "$T/banc/test-metier.py" --app "$ip:8000" --isole --nettoyer "claude@$ip" --json "$out/test-metier.json" || fail "test métier"
step collecte bash -c "scp -q -o BatchMode=yes -o IdentitiesOnly=yes -i '$BS_ADMIN_KEY' '$T/collecte/bs-collect' '$T/collecte/install-on-vm.sh' claude@$ip: && ${SSH[*]} claude@$ip \"sudo install -o root -g root -m 0755 bs-collect /usr/local/sbin/bs-collect && sudo bash install-on-vm.sh '\$(cat $BS_ADMIN_KEY.pub)' >/dev/null && rm bs-collect install-on-vm.sh\" && ssh -T -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -i '$BS_ADMIN_KEY' bs-collect@$ip > '$out/$sbx.json'" || fail "collecte sur la copie"
just=(); [ -f "$repo/$vm/justifications.json" ] && just=(--justify "$repo/$vm/justifications.json")
step comparaison bash -c "python3 -I '$T/collecte/bs-compare' --identity '$repo/inventaires/$vm.json' '$out/$sbx.json' ${just[*]} --json '$out/comparaison.json' > '$out/comparaison.txt'; rc=\$?; head -3 '$out/comparaison.txt'; exit \$rc"
rc=$?
total=$(( $(date +%s) - t0 ))
printf '{"vm": "%s", "sandbox": "%s", "ip": "%s", "total_s": %d, "sandbox_s": %d, "reconstruction_s": %d, "restauration_s": %d, "redemarrage_s": %d, "test_metier_s": %d, "collecte_s": %d, "comparaison_s": %d}\n' \
  "$vm" "$sbx" "$ip" "$total" "${dur[sandbox]}" "${dur[reconstruction]}" "${dur[restauration]}" "${dur[redemarrage]}" "${dur[test_metier]}" "${dur[collecte]}" "${dur[comparaison]}" > "$out/chronos.json"
echo "== total : $total s ; écarts non justifiés : $([ $rc -eq 0 ] && echo 0 || echo 'oui (voir rapport)')"
exit $rc
