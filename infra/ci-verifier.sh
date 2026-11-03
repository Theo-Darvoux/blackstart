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
# Âge des données restaurées = perte maximale à la bascule. La sauvegarde est
# en retard si l'instantané est plus vieux que le dernier passage prévu du cron
# qui lance « restic backup » (vu le 3 novembre : cron sans /usr/sbin dans le
# PATH, aucune sauvegarde depuis le déploiement). Sans cron quotidien lisible :
# seuil BS_RPO_MAX_H (défaut 26 h).
python3 -I - "$out/ansible.log" "$out/sauvegarde.json" "${BS_RPO_MAX_H:-26}" "$repo/$vm/files" <<'PY' || true
import datetime as dt, glob, json, os, re, sys
log, sortie, max_h, files = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
hits = re.findall(r"([0-9a-f]{8})\s+(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", open(log, errors="replace").read())
if not hits:
    sys.exit(0)
sid, date = hits[-1]
snap, now = dt.datetime.strptime(date, "%Y-%m-%d %H:%M:%S"), dt.datetime.now()
attendu, tache = None, None
for f in glob.glob(os.path.join(files, "etc/cron.d/*")) + glob.glob(os.path.join(files, "var/spool/cron/crontabs/*")):
    for line in open(f, errors="replace"):
        m = re.match(r"\s*(\d+)\s+(\d+)\s+\*\s+\*\s+\*\s+(?:\S+\s+)?(/\S+)", line)
        script = m and os.path.join(files, m.group(3).lstrip("/"))
        if m and os.path.isfile(script) and "restic backup" in open(script, errors="replace").read():
            t = now.replace(hour=int(m.group(2)), minute=int(m.group(1)), second=0, microsecond=0)
            attendu, tache = (t if t <= now else t - dt.timedelta(days=1)), line.strip()
age = (now - snap).total_seconds() / 3600
retard = snap < attendu - dt.timedelta(minutes=1) if attendu else age > max_h
json.dump({"instantane": sid, "date": date, "age_h": round(age, 1), "max_h": max_h, "trop_vieux": retard,
           "dernier_passage_prevu": attendu and attendu.strftime("%Y-%m-%d %H:%M"), "tache": tache}, open(sortie, "w"),
          ensure_ascii=False)
print(f"   données restaurées : instantané {sid} du {date}, âge {age:.1f} h"
      + (f" ; EN RETARD sur le passage prévu du {attendu:%Y-%m-%d %H:%M}" if retard and attendu else ""))
PY
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
