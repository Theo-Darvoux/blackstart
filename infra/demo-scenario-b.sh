#!/usr/bin/env bash
# Démo « premier audit » de bs-logistique (scénario B), chronométrée :
#   0. préparation : VM joignables, pièges à chaud présents, modèle chargé ;
#   1. audit en direct (collecte en lecture seule de l'original) ;
#   2. classement, propositions du modèle, code généré, merge request ;
#   3. CI : rouge tant que les inconnus ne sont pas tranchés ;
#   4. tentative de bascule : refusée ;
#   5. décision humaine sur chaque inconnu (proposition du modèle à l'écran) ;
#   6. CI : verte ;
#   7. bascule vers la copie vérifiée (coupure mesurée), puis retour.
#
#   infra/demo-scenario-b.sh --par Théo                    (démo : décisions tapées en direct)
#   infra/demo-scenario-b.sh --par Théo --repetition       (décisions lues dans infra/demo/)
#   options : --cache (pas d'appel au modèle si les preuves n'ont pas changé)
#             --sans-bascule (s'arrêter à la CI verte)
#             --preparer (étape 0 seulement, à lancer 10 min avant)
# Résultats : banc/resultats/demo-b-<date>.json
set -euo pipefail
cd "$(dirname "$0")/.."
vm=bs-logistique; ip=192.168.103.200; ia=192.168.103.204
OLLAMA="http://$ia:11434"; MODELE=qwen3.6:35b
repo=forge/pme-infra; key="$HOME/.ssh/id_blackstart_admin"
par=""; repetition=""; cache=""; bascule=1; preparer_seul=""
while [ $# -gt 0 ]; do
    case "$1" in
        --par) par="$2"; shift ;;
        --repetition) repetition=1 ;;
        --cache) cache=1 ;;
        --sans-bascule) bascule="" ;;
        --preparer) preparer_seul=1 ;;
        *) echo "option inconnue : $1" >&2; exit 2 ;;
    esac
    shift
done
[ -n "$par$preparer_seul" ] || { echo "usage : $0 --par <nom> [--repetition] [--cache] [--sans-bascule] | --preparer" >&2; exit 2; }

t0=$(date +%s); declare -A dur; tic=0
lap() { echo; echo "== [$(( $(date +%s) - t0 )) s] $*"; }
debut() { tic=$(date +%s); }
fin() { dur[$1]=$(( $(date +%s) - tic )); }
SSH=(ssh -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=5 -i "$key")

ci_attendre() {  # attend l'état final de la CI d'un commit ; progression sur stderr, état sur stdout
    python3 -I - "$1" <<'PY'
import sys, time
sys.path.insert(0, "infra")
from forge import Forge
f, sha, t0 = Forge(), sys.argv[1], time.time()
st = None
while time.time() - t0 < 1200:
    try:
        st = f.call("GET", f"/repos/pme/infra/commits/{sha}/status").get("state")
    except Exception as exc:  # coupure du VPN ou forge lente : on réessaie, la CI continue sans nous
        print(f"\r   forge injoignable ({type(exc).__name__}), nouvel essai...", end="", file=sys.stderr, flush=True)
        time.sleep(10)
        continue
    if st in ("success", "failure", "error"):
        break
    print(f"\r   CI {sha[:7]} : {st or 'en file'} ({time.time() - t0:.0f} s)", end="", file=sys.stderr, flush=True)
    time.sleep(10)
print(f"\r   CI {sha[:7]} : {st} après {time.time() - t0:.0f} s          ", file=sys.stderr)
print(st)
PY
}

lap "0. préparation"
debut
for h in 200 201 202 203 204; do
    "${SSH[@]}" "claude@192.168.103.$h" true 2>/dev/null && echo "   192.168.103.$h joignable" \
        || { echo "   192.168.103.$h INJOIGNABLE : démarrer la VM (bs-ia n'a pas de démarrage automatique)"; exit 1; }
done
if "${SSH[@]}" "claude@$ip" "ss -Htln 'sport = :9100' | grep -q ."; then
    echo "   pièges à chaud présents"
else
    echo "   pièges à chaud absents (redémarrage ?) : pme/deploy.sh pieges"
    pme/deploy.sh pieges 2>&1 | tail -1
fi
if curl -fsS -m 5 "$OLLAMA/api/ps" | grep -q "\"$MODELE\""; then
    echo "   modèle $MODELE déjà chargé"
else
    echo "   chargement du modèle $MODELE (3 à 5 min)..."
    curl -fsS -m 600 "$OLLAMA/api/generate" -d "{\"model\":\"$MODELE\",\"prompt\":\"ok\",\"stream\":false,\"think\":false,\"options\":{\"num_predict\":1}}" >/dev/null
    echo "   modèle chargé"
fi
fin preparation
[ -n "$preparer_seul" ] && exit 0

lap "1. audit en direct de $vm ($ip), lecture seule"
debut
ssh -T -i ~/.ssh/id_blackstart -o IdentitiesOnly=yes "bs-collect@$ip" > "inventaires/$vm-pieges.json.new"
ssh -T -i ~/.ssh/id_blackstart -o IdentitiesOnly=yes "bs-collect@$ip" bs-collect --with-content > "inventaires/$vm-pieges.content.json.new"
mv "inventaires/$vm-pieges.json.new" "inventaires/$vm-pieges.json"
mv "inventaires/$vm-pieges.content.json.new" "inventaires/$vm-pieges.content.json"
fin audit
python3 -I classement/bs-classify "inventaires/$vm-vierge.json" "inventaires/$vm-pieges.content.json" | head -1

lap "2. classement, propositions du modèle, code généré, merge request"
debut
sans_cache=1; [ -n "$cache" ] && sans_cache=""
BS_SANS_CACHE="$sans_cache" BS_A_ZERO=1 BS_OLLAMA="$OLLAMA" \
    infra/bs-mr.sh "$vm" "Premier audit de $vm : inconnus en attente de décision" 2>&1 | grep -v "^remote\|^    "
fin mr
sha1=$(git -C "$repo" rev-parse HEAD)

lap "3. CI de la merge request (attendue : rouge, inconnus non tranchés)"
debut; etat1=$(ci_attendre "$sha1"); fin ci_rouge

lap "4. tentative de bascule"
python3 -I infra/bascule.py vers-copie || echo "   (refus attendu)"

lap "5. décision humaine sur chaque inconnu"
debut
if [ -n "$repetition" ]; then
    python3 -I infra/bs-decider.py "$vm" --par "$par" --depuis "infra/demo/decisions-$vm.json" 2>&1 | grep -v "^remote\|^    "
else
    python3 -I infra/bs-decider.py "$vm" --par "$par"
fi
fin decision
sha2=$(git -C "$repo" rev-parse HEAD)

lap "6. CI après décisions (attendue : verte)"
debut; etat2=$(ci_attendre "$sha2"); fin ci_verte
[ "$etat2" = success ] || { echo "   CI non verte ($etat2) : pas de bascule"; bascule=""; }

coupure=null
if [ -n "$bascule" ]; then
    lap "7. bascule vers la copie vérifiée"
    debut; python3 -I infra/bascule.py vers-copie; fin bascule
    coupure=$(python3 -c "import glob,json; f=sorted(glob.glob('banc/resultats/bascule-*.json'))[-1]; print(json.load(open(f))['bascule']['coupure_s'])")
    [ -n "$repetition" ] || read -r -p "   Entrée pour revenir à l'original... " _
    debut; python3 -I infra/bascule.py retour; fin retour
fi

total=$(( $(date +%s) - t0 ))
out="banc/resultats/demo-b-$(date +%Y%m%d-%H%M).json"
etapes=$(for k in "${!dur[@]}"; do printf '%s=%s\n' "$k" "${dur[$k]}"; done)
python3 -I - "$out" "$total" "$coupure" "$repetition" "$etat1" "$etat2" "$etapes" <<'PY'
import json, sys
out, total, coupure, rep, e1, e2, etapes = sys.argv[1:8]
d = {"total_s": int(total), "coupure_s": None if coupure == "null" else float(coupure), "repetition": bool(rep),
     "ci_avant_decisions": e1, "ci_apres_decisions": e2,
     "etapes_s": {k: int(v) for k, v in (l.split("=") for l in etapes.split())}}
json.dump(d, open(out, "w"), indent=2, ensure_ascii=False)
print(json.dumps(d, ensure_ascii=False))
PY
lap "terminé en $total s, résultats dans $out"
