#!/usr/bin/env python3
"""Bascule de production : la copie reconstruite et vérifiée remplace l'original.

    infra/bascule.py vers-copie      # original éteint (gardé), copie sur l'IP de production
    infra/bascule.py retour          # copie éteinte, original rallumé

Garde-fou : refuse si la dernière vérification CI de la merge request n'est pas
verte (--force pour passer outre, à n'utiliser qu'en répétition).
L'original n'est jamais supprimé : le retour arrière prend une minute.
"""

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from forge import Forge  # noqa: E402
from pve import PVE  # noqa: E402
import sandbox  # noqa: E402

ORIG_VMID, ORIG_IP, ORIG_NAME = 1600, "192.168.103.200", "bs-logistique"
COPY_VMID, COPY_IP = 1650, "192.168.103.210"
REPO, BRANCH = "pme/infra", "reconstruction/bs-logistique"
KEY = os.path.expanduser("~/.ssh/id_blackstart_admin")
HERE = os.path.dirname(os.path.realpath(__file__))


def log(msg, t0=[time.monotonic()]):
    print(f"[{time.monotonic() - t0[0]:6.1f} s] {msg}", flush=True)


def ssh(ip, cmd):
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=5",
                           "-o", "StrictHostKeyChecking=accept-new", "-i", KEY, f"claude@{ip}", cmd],
                          capture_output=True, text=True)


def ci_green():
    """État CI de la dernière merge request de reconstruction (ouverte ou fusionnée) :
    c'est elle qui a construit la copie actuelle de la sandbox."""
    f = Forge()
    prs = [p for p in f.call("GET", f"/repos/{REPO}/pulls?state=all&limit=50")
           if BRANCH in (p["head"]["ref"], p["head"].get("label")) and (p["state"] == "open" or p["merged"])]
    if not prs:
        return "aucune merge request", "-"
    pr = max(prs, key=lambda p: p["number"])
    sha = pr["head"]["sha"]
    st = f.call("GET", f"/repos/{REPO}/commits/{sha}/status")
    return st.get("state"), f"MR n° {pr['number']}, {sha[:7]}"


def power(pve, vmid, action):
    path = f"/nodes/{pve.node}/qemu/{vmid}"
    status = pve.get(f"{path}/status/current")["status"]
    if action == "stop" and status == "running":
        pve.wait_task(pve.post(f"{path}/status/shutdown", timeout=60, forceStop=1), timeout=180)
    elif action == "start" and status != "running":
        pve.wait_task(pve.post(f"{path}/status/start"))


def wait_http(url, host, timeout=120):
    import urllib.request
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(url, headers={"Host": host})
            with urllib.request.urlopen(req, timeout=5) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(3)
    raise TimeoutError(url)


def vers_copie(force):
    state, sha = ci_green()
    log(f"vérification CI de la merge request ({sha}) : {state}")
    if state != "success" and not force:
        sys.exit("refusé : la reconstruction n'est pas vérifiée (CI non verte)")
    pve = PVE()
    # Sandbox préchauffée pas encore prise par la CI : clone vierge, pas la copie vérifiée.
    if sandbox.NEUVE in pve.get(f"/nodes/{pve.node}/qemu/{COPY_VMID}/config").get("description", ""):
        sys.exit("refusé : la sandbox est un clone neuf que la CI n'a pas encore reconstruit")
    log(f"original {ORIG_NAME} ({ORIG_VMID}) éteint, gardé pour le retour arrière")
    t_coupure = time.monotonic()
    power(pve, ORIG_VMID, "stop")
    # La sandbox est recréée à chaque CI : sa clé d'hôte change, on oublie l'ancienne.
    subprocess.run(["ssh-keygen", "-R", COPY_IP], capture_output=True)
    log("copie : IP et nom de production")
    script = (f"sudo sed -i 's#address {COPY_IP}/24#address {ORIG_IP}/24#' /etc/network/interfaces && "
              f"sudo sed -i 's#^{COPY_IP}\\t.*#{ORIG_IP}\\t{ORIG_NAME}#' /etc/hosts && "
              f"sudo hostnamectl set-hostname {ORIG_NAME} && grep -q 'address {ORIG_IP}/24' /etc/network/interfaces")
    r = ssh(COPY_IP, script)
    if r.returncode != 0:
        sys.exit(f"échec de la reconfiguration : {r.stderr.strip()}")
    log("copie : isolation levée (pare-feu de la VM désactivé), redémarrage")
    path = f"/nodes/{pve.node}/qemu/{COPY_VMID}"
    pve.put(f"{path}/firewall/options", enable=0)
    pve.put(f"{path}/config", description=f"bs-logistique reconstruite par Black Start, en production depuis le {time.strftime('%Y-%m-%d %H:%M')}")
    pve.wait_task(pve.post(f"{path}/status/reboot"))
    subprocess.run(["ssh-keygen", "-R", ORIG_IP], capture_output=True)
    sandbox.wait_ssh(ORIG_IP)
    wait_http(f"http://{ORIG_IP}:8000/health", f"logistique.pme.test")
    log("test métier complet (proxy, DNS, mail réel)")
    res = os.path.join(HERE, "..", "banc", "resultats", time.strftime("bascule-%Y%m%d-%H%M.json"))
    rc = subprocess.run([sys.executable, "-I", os.path.join(HERE, "..", "banc", "test-metier.py"), "--json", res,
                         "--nettoyer", f"claude@{ORIG_IP}"]).returncode
    # Le nettoyage de la commande de test se fait service déjà rétabli : hors coupure.
    try:
        nettoyage = sum(e["duree_s"] for e in json.load(open(res))["etapes"] if e["etape"].startswith("Nettoyage"))
    except (OSError, ValueError, KeyError):
        nettoyage = 0
    coupure = round(time.monotonic() - t_coupure - nettoyage, 1)
    log(f"bascule terminée, coupure du service : {coupure} s" if rc == 0
        else "bascule faite mais test métier ROUGE : envisager « retour »")
    try:
        d = json.load(open(res, encoding="utf-8"))
        d.update({"bascule": {"coupure_s": coupure, "ci": f"{state} ({sha})", "force": force,
                              "date": time.strftime("%Y-%m-%d %H:%M"), "geste_manuel": False}})
        json.dump(d, open(res, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except (OSError, ValueError):
        pass
    sys.exit(rc)


def retour():
    pve = PVE()
    log(f"copie ({COPY_VMID}) éteinte")
    power(pve, COPY_VMID, "stop")
    log(f"original {ORIG_NAME} ({ORIG_VMID}) rallumé")
    power(pve, ORIG_VMID, "start")
    subprocess.run(["ssh-keygen", "-R", ORIG_IP], capture_output=True)
    sandbox.wait_ssh(ORIG_IP)
    log("retour arrière terminé")


def main():
    ap = argparse.ArgumentParser(description="Bascule de production vers la copie reconstruite, ou retour.")
    ap.add_argument("sens", choices=["vers-copie", "retour"])
    ap.add_argument("--force", action="store_true", help="ignorer l'état de la CI (répétition seulement)")
    args = ap.parse_args()
    vers_copie(args.force) if args.sens == "vers-copie" else retour()


if __name__ == "__main__":
    main()
