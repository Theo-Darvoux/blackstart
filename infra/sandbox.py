#!/usr/bin/env python3
"""Sandbox Black Start : VM jetables clonées du template, isolées de la PME.

    infra/sandbox.py create sbx-logistique 1650 192.168.103.210
    infra/sandbox.py status
    infra/sandbox.py destroy 1650

Étapes de `create` :
  1. clone complet du template 226 dans le pool « blackstart » ;
  2. interface réseau coupée (link_down) : le template a l'IP .171 en dur ;
  3. pare-feu Proxmox de la VM : entrée depuis le poste et bs-gitlab seulement ;
     sortie vers bs-gitlab, le DNS et Internet (apt), jamais vers le reste du
     réseau 192.168.103.0/24 (donc ni le vrai bs-mail ni le vrai proxy) ;
  4. démarrage, puis par l'agent QEMU : IP, hostname, nouvelles clés SSH,
     nouveau machine-id, compte « claude » avec la clé d'administration ;
  5. interface rétablie, redémarrage, attente du SSH.

Garde-fous : seules les VMID 1650 à 1659 nommées « sbx-* » peuvent être
créées ou détruites ; les IP doivent être dans PVE_SANDBOX_IPS.
"""

import argparse
import base64
import ipaddress
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from pve import PVE  # noqa: E402

VMID_RANGE = range(1650, 1660)
TEMPLATE_IP = "192.168.103.171"
GITLAB_IP = "192.168.103.203"
WORKSTATION_SRC = "192.168.103.121"   # adresse NAT du VPN MiNET, vue par les VM
DNS = ["192.168.103.54", "192.168.103.55"]
LAN = "192.168.103.0/24"
ADMIN_KEY = os.path.expanduser(os.environ.get("BS_ADMIN_KEY", "~/.ssh/id_blackstart_admin"))
ADMIN_PUB = ADMIN_KEY + ".pub"
CLAUDE_PUB = os.path.join(os.path.dirname(os.path.realpath(__file__)), "admin-claude.pub")  # clé de Claude Code
RUNNER_PUB = os.path.join(os.path.dirname(os.path.realpath(__file__)), "runner-ci.pub")  # runner CI de bs-gitlab


def log(msg, t0=[time.monotonic()]):
    print(f"[{time.monotonic() - t0[0]:6.1f} s] {msg}", flush=True)


def check_guard(pve, vmid, name=None, ip=None):
    if vmid not in VMID_RANGE:
        sys.exit(f"refusé : VMID {vmid} hors de la plage sandbox {VMID_RANGE.start}-{VMID_RANGE.stop - 1}")
    if name is not None and not name.startswith("sbx-"):
        sys.exit(f"refusé : le nom {name} doit commencer par sbx-")
    if ip is not None:
        lo, hi = pve.env["PVE_SANDBOX_IPS"].split("-")
        first = ipaddress.IPv4Address(lo)
        last = ipaddress.IPv4Address(lo.rsplit(".", 1)[0] + "." + hi)
        if not first <= ipaddress.IPv4Address(ip) <= last:
            sys.exit(f"refusé : {ip} hors de la plage sandbox {first}-{last}")


def vm_path(pve, vmid):
    return f"/nodes/{pve.node}/qemu/{vmid}"


def agent_exec(pve, vmid, script, timeout=300):
    """Lance un script bash dans la VM par l'agent QEMU et renvoie sa sortie."""
    res = pve.post(f"{vm_path(pve, vmid)}/agent/exec", command=["/bin/bash", "-c", script])
    pid = res["pid"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = pve.get(f"{vm_path(pve, vmid)}/agent/exec-status", pid=pid)
        if st.get("exited"):
            out = st.get("out-data", "") + st.get("err-data", "")
            if st.get("exitcode", 1) != 0:
                raise RuntimeError(f"script en échec (code {st.get('exitcode')}) : {out[-800:]}")
            return out
        time.sleep(1)
    raise TimeoutError("script de l'agent trop long")


def wait_agent(pve, vmid, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            pve.post(f"{vm_path(pve, vmid)}/agent/ping")
            return
        except RuntimeError:
            time.sleep(3)
    raise TimeoutError("l'agent QEMU ne répond pas")


def wait_ssh(ip, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=5",
                            "-o", "StrictHostKeyChecking=accept-new", "-i", ADMIN_KEY, f"claude@{ip}", "true"],
                           capture_output=True)
        if r.returncode == 0:
            return
        time.sleep(3)
    raise TimeoutError(f"pas de SSH sur {ip}")


def firewall(pve, vmid):
    base = f"{vm_path(pve, vmid)}/firewall"
    for rule in sorted(pve.get(f"{base}/rules") or [], key=lambda r: r["pos"], reverse=True):
        pve.delete(f"{base}/rules/{rule['pos']}")
    rules = [  # dans l'ordre d'évaluation
        dict(type="in", action="ACCEPT", source=WORKSTATION_SRC, comment="poste de démo (NAT VPN)"),
        dict(type="in", action="ACCEPT", source=GITLAB_IP, comment="forge et runner CI"),
        dict(type="out", action="ACCEPT", dest=GITLAB_IP, comment="Git, restic/SFTP"),
        dict(type="out", action="ACCEPT", dest=",".join(DNS), proto="udp", dport="53", comment="DNS"),
        dict(type="out", action="ACCEPT", dest=",".join(DNS), proto="tcp", dport="53", comment="DNS"),
        # REJECT plutôt que DROP : même isolation, mais la copie apprend tout de suite que
        # la machine est injoignable (nginx répond 502 au lieu d'attendre 60 s).
        dict(type="out", action="REJECT", dest=LAN, comment="isolation : rien vers la PME"),
    ]
    # Proxmox insère chaque nouvelle règle en tête : on les crée à l'envers.
    for r in reversed(rules):
        pve.post(f"{base}/rules", enable=1, **r)
    pve.put(f"{base}/options", enable=1, policy_in="DROP", policy_out="ACCEPT", log_level_in="nolog")


def bootstrap_script(name, ip):
    keys = []
    for path in (ADMIN_PUB, RUNNER_PUB, CLAUDE_PUB):
        if os.path.exists(path):
            k = open(path, encoding="utf-8").read().strip()
            if k not in keys:
                keys.append(k)
    pub = "\n".join(keys) + "\n"
    pub_b64 = base64.b64encode(pub.encode()).decode()
    return f"""set -euo pipefail
sed -i 's#address {TEMPLATE_IP}/24#address {ip}/24#' /etc/network/interfaces
grep -q 'address {ip}/24' /etc/network/interfaces
hostnamectl set-hostname {name}
sed -i -e '/^127.0.1.1/d' -e 's/^{TEMPLATE_IP}.*/{ip}\\t{name}/' /etc/hosts
rm -f /etc/ssh/ssh_host_* && ssh-keygen -A >/dev/null
rm -f /etc/machine-id /var/lib/dbus/machine-id && systemd-machine-id-setup >/dev/null
ln -sf /etc/machine-id /var/lib/dbus/machine-id
id claude >/dev/null 2>&1 || useradd -m -s /bin/bash claude
install -d -m 700 -o claude -g claude /home/claude/.ssh
echo {pub_b64} | base64 -d > /home/claude/.ssh/authorized_keys
chown claude:claude /home/claude/.ssh/authorized_keys && chmod 600 /home/claude/.ssh/authorized_keys
echo 'claude ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/claude && chmod 440 /etc/sudoers.d/claude
visudo -cq
echo bootstrap-ok
"""


NEUVE = "[neuve]"  # sandbox préchauffée : clone neuf du template, jamais utilisé
EN_PRODUCTION = "en production depuis"  # posé par infra/bascule.py vers-copie : la copie sert la production


def en_production(pve, vmid):
    """Vrai si la sandbox est la copie qui sert la production après une bascule : elle ne se détruit pas."""
    try:
        return EN_PRODUCTION in (pve.get(f"{vm_path(pve, vmid)}/config").get("description") or "")
    except Exception:
        return False


def create(pve, name, vmid, ip, neuve=False):
    check_guard(pve, vmid, name, ip)
    if any(v.get("vmid") == vmid for v in pve.get("/cluster/resources", type="vm")):
        sys.exit(f"VMID {vmid} déjà utilisée : infra/sandbox.py destroy {vmid} d'abord")
    tpl = pve.env["PVE_TEMPLATE"]
    log(f"clonage du template {tpl} -> {vmid} {name}")
    upid = pve.post(f"/nodes/{pve.node}/qemu/{tpl}/clone", newid=vmid, name=name, full=1,
                    storage=pve.env["PVE_STORAGE"], pool="blackstart",
                    description="Sandbox Black Start, jetable (infra/sandbox.py)" + (f" {NEUVE}" if neuve else ""))
    pve.wait_task(upid, timeout=900)
    log("interface coupée, pare-feu d'isolation")
    pve.put(f"{vm_path(pve, vmid)}/config", net0=f"virtio,bridge={pve.env['PVE_BRIDGE']},firewall=1,link_down=1")
    firewall(pve, vmid)
    log("démarrage")
    pve.wait_task(pve.post(f"{vm_path(pve, vmid)}/status/start"))
    wait_agent(pve, vmid)
    log("configuration par l'agent QEMU (IP, hostname, clés, machine-id, compte claude)")
    out = agent_exec(pve, vmid, bootstrap_script(name, ip))
    if "bootstrap-ok" not in out:
        raise RuntimeError(out)
    log("interface rétablie, redémarrage")
    cfg = pve.get(f"{vm_path(pve, vmid)}/config")
    pve.put(f"{vm_path(pve, vmid)}/config", net0=cfg["net0"].replace(",link_down=1", ""))
    pve.wait_task(pve.post(f"{vm_path(pve, vmid)}/status/reboot"))
    subprocess.run(["ssh-keygen", "-R", ip], capture_output=True)
    wait_ssh(ip)
    log(f"prête : ssh -i {ADMIN_KEY} claude@{ip}")


def prendre(pve, name, vmid, ip):
    """Prend la sandbox préchauffée si elle est neuve (clone du template jamais utilisé,
    marqué [neuve] à la création), en retirant la marque : elle ne sert qu'une fois.
    Code 1 sinon : l'appelant la recrée."""
    check_guard(pve, vmid, name, ip)
    vm = next((v for v in pve.get("/cluster/resources", type="vm") if v.get("vmid") == vmid), None)
    if not vm or vm.get("name") != name or vm.get("status") != "running":
        log(f"pas de sandbox préchauffée {name} ({vmid}) en marche")
        return 1
    desc = pve.get(f"{vm_path(pve, vmid)}/config").get("description", "")
    if NEUVE not in desc:
        log(f"{name} ({vmid}) déjà utilisée : pas de réemploi")
        return 1
    subprocess.run(["ssh-keygen", "-R", ip], capture_output=True)  # clés d'hôte neuves depuis la dernière sandbox
    try:
        wait_ssh(ip, timeout=15)
    except TimeoutError:
        log(f"{name} ({vmid}) injoignable en SSH")
        return 1
    pve.put(f"{vm_path(pve, vmid)}/config", description=desc.replace(f" {NEUVE}", "").replace(NEUVE, ""))
    log(f"sandbox préchauffée prise : {name} ({vmid}), clone neuf du template")
    return 0


def destroy(pve, vmid):
    check_guard(pve, vmid)
    vms = {v["vmid"]: v for v in pve.get("/cluster/resources", type="vm")}
    if vmid not in vms:
        sys.exit(f"VMID {vmid} absente")
    name = vms[vmid].get("name", "")
    check_guard(pve, vmid, name)
    if en_production(pve, vmid):
        sys.exit(f"refusé : {vmid} {name} sert la production depuis une bascule ; infra/bascule.py retour d'abord")
    if vms[vmid].get("status") == "running":
        log(f"arrêt de {vmid} {name}")
        pve.wait_task(pve.post(f"{vm_path(pve, vmid)}/status/stop"))
    log(f"suppression de {vmid} {name}")
    pve.wait_task(pve.delete(vm_path(pve, vmid), purge=1, **{"destroy-unreferenced-disks": 1}))
    log("supprimée")


def status(pve):
    for v in sorted(pve.get("/pools/blackstart")["members"], key=lambda m: m.get("vmid", 0)):
        print(f"{v.get('vmid'):>5} {v.get('name', ''):<16} {v.get('status', ''):<8} "
              f"{v.get('maxmem', 0) // 2**20} Mo")


def main():
    ap = argparse.ArgumentParser(description="VM sandbox Black Start sur luna.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("name")
    c.add_argument("vmid", type=int)
    c.add_argument("ip")
    c.add_argument("--neuve", action="store_true", help="préchauffée : marquée pour un seul réemploi par la CI")
    p = sub.add_parser("prendre", help="réemployer la sandbox préchauffée (code 1 si absente ou déjà utilisée)")
    p.add_argument("name")
    p.add_argument("vmid", type=int)
    p.add_argument("ip")
    d = sub.add_parser("destroy")
    d.add_argument("vmid", type=int)
    sub.add_parser("status")
    args = ap.parse_args()
    pve = PVE()
    if args.cmd == "create":
        create(pve, args.name, args.vmid, args.ip, args.neuve)
    elif args.cmd == "prendre":
        sys.exit(prendre(pve, args.name, args.vmid, args.ip))
    elif args.cmd == "destroy":
        destroy(pve, args.vmid)
    else:
        status(pve)


if __name__ == "__main__":
    main()
