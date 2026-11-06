#!/usr/bin/env python3
"""Console Black Start de la démo (scénario B accéléré), servie depuis le poste de démo.

    infra/salle/serveur.py --par Théo            puis http://localhost:8080 en plein écran (F11)

La page est une console produit : vue d'ensemble de la machine, parc, inventaire consultable,
décisions, merge request et CI, bascule. Chaque action lancée devient une « opération » découpée
en pas expliqués (quoi, sur quelle machine, résultat), affichée dans le panneau Activité.

Avant l'oral (10 min avant) : Laboratoire → « Préparer ». Vérifie les VM, repose les pièges à
chaud si besoin, charge le modèle, préchauffe la sandbox (clone neuf du template) et calcule les
propositions du modèle sur l'audit du moment : pendant la démo, plus rien n'attend.

Devant le jury, depuis la vue d'ensemble :
  1. « Lancer l'audit »        : collecte en lecture seule, classement, propositions du modèle,
                                 code, merge request, CI bloquée, garde-fou de bascule ;
  2. Décisions → « Valider »   : une décision et une raison par inconnu, CI verte suivie pas à pas ;
  3. Bascule → « Basculer »    : coupure chronométrée, test métier complet sur la production.
Après l'oral : Laboratoire → « Remettre en état » (retour à l'original, pièges reposés).

Intégrer une autre machine (parcours client, hors démo) : Machines → « Ajouter une machine ». Elle est
déclarée dans parc/parc.json ; sa fiche donne le script d'installation de l'accès de collecte
(/installer/bs-collect-installer.sh), puis « Vérifier l'accès » et « Lancer le premier audit ».

Rien n'est simulé : chaque pas lance les scripts du prototype (bs-collect, bs-classify, bs-mr.sh,
bs-decider.py, CI Forgejo, bascule.py). Les durées affichées sont celles mesurées en direct.
"""

import argparse
import concurrent.futures
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ICI = os.path.dirname(os.path.realpath(__file__))
RACINE = os.path.realpath(os.path.join(ICI, "..", ".."))
sys.path.insert(0, os.path.join(RACINE, "infra"))
from forge import Forge  # noqa: E402

# Registre du parc de l'entreprise : machines déclarées, périmètre autorisé, image de référence,
# plateforme sur site. Les machines s'ajoutent depuis la console (Machines → Ajouter une machine).
PARC_FICHIER = os.environ.get("BS_PARC") or os.path.join(RACINE, "parc", "parc.json")
PARC_CFG = json.load(open(PARC_FICHIER, encoding="utf-8"))
_PF = PARC_CFG.get("plateforme", {})

# Machine dont la reprise complète se joue en direct dans la console (scénario de démo).
VM, IP, SBX, SBX_VMID, SBX_IP = "bs-logistique", "192.168.103.200", "sbx-logistique", 1650, "192.168.103.210"
FORGE_IP = _PF.get("forge", {}).get("ip", "192.168.103.203")
IA = _PF.get("modele", {}).get("url", "http://192.168.103.204:11434")
MODELE = _PF.get("modele", {}).get("modele", "qwen3.6:35b")
DEPOT = os.path.join(RACINE, "forge", "pme-infra")
INV = os.path.join(RACINE, "inventaires")
CACHE_PREPARE = os.path.join(INV, f"{VM}.propositions-preparees.json")
DECISIONS_DEMO = os.path.join(RACINE, "infra", "demo", f"decisions-{VM}.json")
RAISONS_DEMO = os.path.join(RACINE, "infra", "demo", f"raisons-{VM}.json")  # une raison préparée par choix
CLE_ADMIN = os.path.expanduser("~/.ssh/id_blackstart_admin")
CLE_COLLECTE = os.path.expanduser("~/.ssh/id_blackstart")
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=5"]

# Machines du laboratoire vérifiées par « Préparer » (IP, nom, rôle, zone) ; compte d'administration claude.
PARC = [("192.168.103.200", "bs-logistique", "Logiciel de logistique + PostgreSQL", "production"),
        ("192.168.103.201", "bs-mail", "Postfix + Dovecot", "production"),
        ("192.168.103.202", "bs-proxy", "Proxy web Nginx + DNS", "production"),
        ("192.168.103.203", "bs-gitlab", "Forge Forgejo + CI", "black start"),
        ("192.168.103.204", "bs-ia", f"Modèle local {MODELE}, sans GPU", "black start")]

# Intégration d'une machine : accès de collecte vérifié et premier audit, hors Git (inventaires/ est ignoré).
DOSSIER_PARC = os.path.join(INV, "parc")
KNOWN_HOSTS = os.path.join(DOSSIER_PARC, "known_hosts")  # empreintes des serveurs, enregistrées à la 1re vérification
SSH_COLLECTE = ["ssh", "-T", "-i", CLE_COLLECTE, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=6", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "StrictHostKeyChecking=yes"]
NOM_MACHINE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
CRITICITES = ("critique", "importante", "secondaire")
_PARC_ECRITURE = threading.Lock()

POSTE = "poste Black Start"
M_ORIG, M_FORGE, M_IA, M_SBX = f"{VM} · {IP}", f"forge · {FORGE_IP}", "bs-ia · 192.168.103.204", f"{SBX} · {SBX_IP}"

# Étapes de ci-verifier.sh, dans l'ordre : clé, libellé, explication à l'écran.
ETAPES_CI = [
    ("sandbox", "Sandbox isolée",
     "Une VM neuve, clonée d'une Debian vierge, coupée de l'entreprise par un pare-feu."),
    ("reconstruction", "Reconstruction depuis le code",
     "Ansible applique le code de la merge request. Personne au clavier."),
    ("restauration", "Restauration des données",
     "Les données (base PostgreSQL, fichiers EDI) reviennent de la dernière sauvegarde restic."),
    ("redemarrage", "Redémarrage",
     "La copie redémarre : une configuration qui ne survit pas à un redémarrage ferait échouer la preuve."),
    ("collecte", "Audit de la copie",
     "La même collecte en lecture seule que sur l'original, cette fois sur la copie."),
    ("comparaison", "Comparaison avec l'original",
     "Chaque différence entre la copie et l'original doit être justifiée, sinon la CI est rouge."),
    ("test_metier", "Test métier",
     "Une vraie commande est créée, relue puis supprimée dans le logiciel de la copie."),
]


RAPPORT_CONSOLE = os.path.join(INV, "rapport-console.html")  # rapport de reprise régénéré par la console
_PARC = {"t": 0, "donnees": None}
_PARC_VERROU = threading.Lock()


def lire_json(chemin):
    try:
        return json.load(open(chemin, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def lire_parc():
    with _PARC_ECRITURE:
        return json.load(open(PARC_FICHIER, encoding="utf-8"))


def ecrire_parc(cfg):
    with _PARC_ECRITURE:
        with open(PARC_FICHIER + ".new", "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(PARC_FICHIER + ".new", PARC_FICHIER)


def dans_perimetre(ip, cfg=None):
    """(vrai, "") si Black Start a le droit de se connecter à cette adresse, sinon (faux, motif)."""
    import ipaddress
    cfg = cfg or lire_parc()
    p = cfg.get("perimetre", {})
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False, f"« {ip} » n'est pas une adresse IPv4 valide"
    if ip in p.get("exclues", {}):
        return False, f"{ip} est exclue du périmètre ({p['exclues'][ip]})"
    if not any(a in ipaddress.ip_network(r, strict=False) for r in p.get("reseaux", [])):
        return False, f"{ip} est hors des réseaux autorisés ({', '.join(p.get('reseaux', [])) or 'aucun'})"
    return True, ""


_CACHE_FICHIERS = {}


def selon_fichiers(chemins, calcul):
    """Résultat de `calcul()`, recalculé seulement si l'un des fichiers a changé."""
    cle = (tuple(chemins), calcul.__name__)
    sig = tuple(os.stat(c).st_mtime_ns if os.path.exists(c) else 0 for c in chemins)
    if _CACHE_FICHIERS.get(cle, (None,))[0] != sig:
        _CACHE_FICHIERS[cle] = (sig, calcul())
    return _CACHE_FICHIERS[cle][1]


def cle_collecte():
    """Clé publique de la plateforme, autorisée sur chaque serveur pour le seul compte bs-collect."""
    def calcul():
        pub = open(CLE_COLLECTE + ".pub", encoding="utf-8").read().strip()
        emp = subprocess.run(["ssh-keygen", "-lf", CLE_COLLECTE + ".pub"], capture_output=True, text=True).stdout.split()
        return {"publique": pub, "type": pub.split()[0], "empreinte": emp[1] if len(emp) > 1 else "",
                "commentaire": pub.split()[2] if len(pub.split()) > 2 else ""}
    return selon_fichiers([CLE_COLLECTE + ".pub"], calcul)


INSTALLATEUR = "bs-collect-installer.sh"
SOURCES_INSTALLATEUR = [os.path.join(RACINE, "collecte", "bs-collect"), os.path.join(RACINE, "collecte", "install-on-vm.sh")]


def installateur():
    """Script autonome à lancer en root sur un serveur de l'entreprise : copie le collecteur (vérifié par
    son empreinte), crée le compte bs-collect restreint à la collecte et autorise la clé de la plateforme.
    Déterministe : même collecteur et même clé, même script, même empreinte SHA-256."""
    import base64
    import hashlib

    def calcul():
        col, ins = (open(p, "rb").read() for p in SOURCES_INSTALLATEUR)
        cle = cle_collecte()
        version = re.search(rb'VERSION = "([^"]+)"', col)
        b64 = lambda b: "\n".join(base64.b64encode(b).decode()[i:i + 76] for i in range(0, len(base64.b64encode(b)), 76))
        script = f"""#!/bin/bash
# Black Start : installation de l'accès de collecte en lecture seule.
#
# À lancer en root sur le serveur à auditer :   sudo bash {INSTALLATEUR}
#
# Ce script fait trois choses, et rien d'autre :
#   1. il copie le collecteur bs-collect {version.group(1).decode() if version else ''} dans /usr/local/sbin
#      (empreinte SHA-256 vérifiée avant installation) ;
#   2. il crée le compte système bs-collect, qui ne peut lancer que la collecte : commande forcée
#      dans authorized_keys, sudo limité à /usr/local/sbin/bs-collect, pas de terminal ;
#   3. il autorise la clé de la plateforme Black Start pour ce seul compte :
#      {cle['empreinte']} ({cle['commentaire']}).
#
# La collecte lit la machine sans la modifier. Elle n'emporte jamais /etc/shadow, les clés privées
# ni les fichiers lisibles par root seul.
#
# Révoquer l'accès à tout moment :
#   sudo userdel -r bs-collect && sudo rm -f /usr/local/sbin/bs-collect /usr/local/sbin/bs-collect-ssh /etc/sudoers.d/bs-collect
set -euo pipefail
[ "$(id -u)" = 0 ] || {{ echo "à lancer en root : sudo bash $0" >&2; exit 1; }}
[ -r /etc/debian_version ] || {{ echo "système non pris en charge : Debian requis" >&2; exit 1; }}
command -v sudo >/dev/null || {{ echo "sudo est requis (apt install sudo)" >&2; exit 1; }}
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

base64 -d > "$tmp/bs-collect" <<'BS_COLLECT'
{b64(col)}
BS_COLLECT
echo "{hashlib.sha256(col).hexdigest()}  $tmp/bs-collect" | sha256sum -c --quiet
install -o root -g root -m 0755 "$tmp/bs-collect" /usr/local/sbin/bs-collect

base64 -d > "$tmp/install-on-vm.sh" <<'BS_INSTALL'
{b64(ins)}
BS_INSTALL
echo "{hashlib.sha256(ins).hexdigest()}  $tmp/install-on-vm.sh" | sha256sum -c --quiet
bash "$tmp/install-on-vm.sh" '{cle['publique']}' >/dev/null

echo
echo "Accès de collecte Black Start installé sur $(hostname)."
echo "Empreinte de ce serveur, à comparer avec celle affichée par la console après « Vérifier l'accès » :"
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub | awk '{{print "  " $2}}'
"""
        return {"script": script, "sha256": hashlib.sha256(script.encode()).hexdigest(), "taille": len(script.encode()),
                "collecteur": version.group(1).decode() if version else None,
                "collecteur_sha256": hashlib.sha256(col).hexdigest()}
    return selon_fichiers(SOURCES_INSTALLATEUR + [CLE_COLLECTE + ".pub"], calcul)


def reference_info(cfg):
    ref = cfg.get("reference", {})
    chemin = os.path.join(RACINE, ref.get("fichier", ""))

    def calcul():
        d = lire_json(chemin)
        if not d:
            return dict(ref, disponible=False)
        return dict(ref, disponible=True, os=d["meta"]["os_release"].get("PRETTY_NAME"), date=d["meta"]["collected_at"],
                    paquets=len(d["packages"]["installed"]), noyau=d["meta"].get("kernel"))
    return selon_fichiers([chemin], calcul)


def resume_integration(vm):
    """Premier audit d'une machine intégrée depuis la console (classement complet, pour l'affichage)."""
    return lire_json(os.path.join(DOSSIER_PARC, f"{vm}.classement.json"))


def parc(force=False):
    """Le parc de l'entreprise tel que la console le montre : les machines déclarées dans le registre
    (parc/parc.json), avec leur accès de collecte et leur premier audit, enrichies de leur état de
    reprise réel quand elles sont suivies par le rapport (rapport/vms.json). La partie rapport, qui
    interroge la forge, est gardée 60 s ; le registre est relu à chaque appel."""
    try:
        r, err = rapport_parc(force), None
    except Exception as exc:  # forge, fichiers : affiché tel quel, rien d'inventé
        traceback.print_exc()
        r, err = {"date": time.time(), "forge": _PF.get("forge", {}).get("url"), "machines": []}, str(exc)
    cfg = lire_parc()
    # Après « Réinitialiser les données », une machine sans vérification postérieure sur la forge repart comme
    # une machine à intégrer : son ancien audit (rapport/vms.json), ses décisions et son score ne sont plus montrés.
    remise = lire_json(REMISE)
    suivies = {m["vm"]: m for m in r["machines"] if not (remise and m.get("forge") is None)}
    machines = []
    for d in cfg.get("machines", []):
        m = dict(suivies.pop(d["vm"], {}), **d)
        m["rapport"] = "verdict" in m
        m["acces"] = lire_json(os.path.join(DOSSIER_PARC, f"{d['vm']}.acces.json"))
        m["integration"] = resume_integration(d["vm"])
        machines.append(m)
    for m in suivies.values():  # suivie par le rapport mais absente du registre : montrée quand même
        machines.append(dict(m, rapport=True, acces=None, integration=None))
    try:
        cle = cle_collecte()
        inst = {k: v for k, v in installateur().items() if k != "script"}
    except OSError as exc:
        cle, inst = {"erreur": str(exc)}, {"erreur": str(exc)}
    return {"date": r["date"], "forge": r["forge"], "rapport_erreur": err, "demo": VM,
            "organisation": cfg.get("organisation"), "description": cfg.get("description"),
            "perimetre": cfg.get("perimetre", {}), "reference": reference_info(cfg),
            "plateforme": cfg.get("plateforme", {}), "adresses_connues": cfg.get("adresses_connues", {}),
            "cle": cle, "installateur": dict(inst, nom=INSTALLATEUR), "machines": machines,
            "references": references_disponibles(), "par": ETAT.par, "remise": lire_json(REMISE)}


def ajouter_machine(corps):
    """Déclare une machine dans le registre. Aucune connexion n'est faite à ce stade."""
    vm = str(corps.get("vm", "")).strip().lower()
    ip = str(corps.get("ip", "")).strip()
    role = str(corps.get("role", "")).strip()
    crit = corps.get("criticite") or "importante"
    if not NOM_MACHINE.match(vm):
        raise ValueError("nom invalide : lettres minuscules, chiffres et tirets (2 à 41 caractères)")
    if not role:
        raise ValueError("indiquer le rôle de la machine (ce qu'elle rend comme service)")
    if crit not in CRITICITES:
        raise ValueError("criticité inconnue")
    cfg = lire_parc()
    ok, motif = dans_perimetre(ip, cfg)
    if not ok:
        raise ValueError(motif)
    pf = cfg.get("plateforme", {})
    for m in cfg.get("machines", []):
        if m["vm"] == vm:
            raise ValueError(f"{vm} est déjà dans le parc")
        if m["ip"] == ip:
            raise ValueError(f"{ip} est déjà l'adresse de {m['vm']}")
    if ip in [x.get("ip") for x in pf.values()]:
        raise ValueError(f"{ip} est une machine de la plateforme Black Start")
    entree = {"vm": vm, "ip": ip, "role": role[:160], "criticite": crit,
              "ajoutee_le": time.strftime("%Y-%m-%d"), "ajoutee_par": ETAT.par}
    cfg.setdefault("machines", []).append(entree)
    ecrire_parc(cfg)
    return entree


def retirer_machine(corps):
    """Retire du registre une machine ajoutée depuis la console (pas celles suivies par le rapport)."""
    vm = str(corps.get("vm", ""))
    cfg = lire_parc()
    suivies = {v["vm"] for v in (lire_json(os.path.join(RACINE, "rapport", "vms.json")) or {}).get("vms", [])}
    if vm == VM or vm in suivies:
        raise ValueError(f"{vm} a des preuves de reprise : elle reste dans le parc")
    avant = len(cfg.get("machines", []))
    cfg["machines"] = [m for m in cfg.get("machines", []) if m["vm"] != vm]
    if len(cfg["machines"]) == avant:
        raise ValueError(f"{vm} n'est pas dans le parc")
    ecrire_parc(cfg)
    for suffixe in (".acces.json", ".classement.json", ".content.json"):
        try:
            os.remove(os.path.join(DOSSIER_PARC, vm + suffixe))
        except FileNotFoundError:
            pass


def references_disponibles():
    """Images de référence relevées sur la plateforme (Debian neuves) : inventaires/*-vierge.json."""
    out = []
    for p in sorted(os.listdir(INV)):
        if p.endswith("-vierge.json"):
            d = lire_json(os.path.join(INV, p)) or {}
            meta = d.get("meta", {})
            out.append({"fichier": f"inventaires/{p}", "os": meta.get("os_release", {}).get("PRETTY_NAME"),
                        "date": meta.get("collected_at"), "machine": meta.get("hostname"),
                        "paquets": len(d.get("packages", {}).get("installed", []))})
    return out


def regler(corps):
    """Modifie les réglages de l'entreprise (organisation, périmètre, image de référence, adresses connues).
    La plateforme (forge, modèle, sandbox) reste fixée à l'installation."""
    import ipaddress
    cfg = lire_parc()
    org = str(corps.get("organisation", cfg.get("organisation", ""))).strip()
    if not org or len(org) > 80:
        raise ValueError("nom de l'organisation : 1 à 80 caractères")
    cfg["organisation"], cfg["description"] = org, str(corps.get("description", cfg.get("description", ""))).strip()[:160]
    if "reseaux" in corps:
        reseaux = []
        for r in corps["reseaux"]:
            r = str(r).strip()
            if not r:
                continue
            try:
                reseaux.append(str(ipaddress.ip_network(r, strict=False)))
            except ValueError:
                raise ValueError(f"réseau invalide : « {r} » (exemple : 192.168.10.0/24)")
        if not reseaux:
            raise ValueError("au moins un réseau autorisé")
        cfg.setdefault("perimetre", {})["reseaux"] = reseaux
    for cle, dest in (("exclues", ("perimetre", "exclues")), ("adresses_connues", (None, "adresses_connues"))):
        if cle in corps:
            d = {}
            for ip, lib in (corps[cle] or {}).items():
                ip = str(ip).strip()
                if not ip:
                    continue
                try:
                    ipaddress.ip_address(ip)
                except ValueError:
                    raise ValueError(f"adresse invalide : « {ip} »")
                d[ip] = str(lib).strip()[:80] or "sans libellé"
            (cfg.setdefault(dest[0], {}) if dest[0] else cfg)[dest[1]] = d
    if "reference" in corps:
        f = corps["reference"].get("fichier")
        if f not in [r["fichier"] for r in references_disponibles()]:
            raise ValueError("image de référence inconnue")
        cfg["reference"] = {"nom": str(corps["reference"].get("nom") or "Debian neuve").strip()[:120], "fichier": f}
    hors = [m["vm"] for m in cfg.get("machines", []) if not dans_perimetre(m["ip"], cfg)[0]]
    if hors:
        raise ValueError("ces machines sortiraient du périmètre : " + ", ".join(hors) + " (modifier leur adresse d'abord)")
    ecrire_parc(cfg)
    return {"ok": True}


def modifier_machine(corps):
    """Rôle, criticité, et adresse IP pour une machine pas encore suivie par le rapport (l'accès est alors
    à revérifier : l'empreinte et l'audit concernaient l'ancienne adresse)."""
    vm = str(corps.get("vm", ""))
    cfg = lire_parc()
    m = next((x for x in cfg.get("machines", []) if x["vm"] == vm), None)
    if not m:
        raise ValueError(f"{vm} n'est pas dans le parc")
    role, crit = str(corps.get("role", m["role"])).strip(), corps.get("criticite", m.get("criticite"))
    if not role:
        raise ValueError("indiquer le rôle de la machine")
    if crit not in CRITICITES:
        raise ValueError("criticité inconnue")
    m["role"], m["criticite"] = role[:160], crit
    ip = str(corps.get("ip", m["ip"])).strip()
    if ip != m["ip"]:
        suivies = {v["vm"] for v in (lire_json(os.path.join(RACINE, "rapport", "vms.json")) or {}).get("vms", [])}
        if vm == VM or vm in suivies:
            raise ValueError(f"l'adresse de {vm} est celle de ses preuves de reprise : elle ne se change pas ici")
        ok, motif = dans_perimetre(ip, cfg)
        if not ok:
            raise ValueError(motif)
        if any(x["ip"] == ip for x in cfg["machines"] if x is not m):
            raise ValueError(f"{ip} est déjà utilisée dans le parc")
        m["ip"] = ip
        for suffixe in (".acces.json", ".classement.json", ".content.json"):
            try:
                os.remove(os.path.join(DOSSIER_PARC, vm + suffixe))
            except FileNotFoundError:
                pass
    ecrire_parc(cfg)
    return m


_JOIN = {"t": 0, "d": None}


def joignabilite():
    """État réel de chaque machine, sans s'y connecter : port SSH ouvert ou non (TCP), forge (API) et
    modèle (modèles chargés en mémoire). Gardé 10 s."""
    import ipaddress
    import socket
    import urllib.error
    if _JOIN["d"] and time.time() - _JOIN["t"] < 10:
        return _JOIN["d"]
    cfg = lire_parc()
    pf = cfg.get("plateforme", {})
    def valide(ip):
        try:
            return bool(ipaddress.ip_address(ip))
        except ValueError:
            return False
    ips = {ip for ip in {m["ip"] for m in cfg.get("machines", [])} | {x.get("ip") for x in pf.values()} | {SBX_IP} if ip and valide(ip)}

    def sonde(ip):
        if not dans_perimetre(ip, cfg)[0]:
            return ip, {"ok": None, "erreur": "hors périmètre"}
        t = time.time()
        try:
            with socket.create_connection((ip, 22), timeout=1.5):
                return ip, {"ok": True, "ms": round((time.time() - t) * 1000)}
        except OSError as exc:
            return ip, {"ok": False, "erreur": "délai dépassé" if isinstance(exc, socket.timeout) else "refusé"}

    def http(url):
        try:
            return json.loads(urllib.request.urlopen(url, timeout=3).read() or b"{}")
        except urllib.error.HTTPError:  # répond, mais demande une authentification
            return {}
        except Exception:
            return None
    with concurrent.futures.ThreadPoolExecutor(12) as ex:
        hotes = dict(ex.map(sonde, sorted(ips)))
        fv = ex.submit(http, pf.get("forge", {}).get("url", "") + "/api/v1/version")
        mp = ex.submit(http, pf.get("modele", {}).get("url", "") + "/api/ps")
        fv, mp = fv.result(), mp.result()
    d = {"date": time.time(), "hotes": hotes,
         "forge": {"ok": fv is not None, "version": (fv or {}).get("version")},
         "modele": {"ok": mp is not None, "charges": [m.get("name") for m in (mp or {}).get("models", [])]}}
    _JOIN.update(t=time.time(), d=d)
    return d


def rapport_parc(force=False):
    """Comme lire_rapport_parc, mais sans faire attendre la page : passé 60 s, l'ancienne lecture est rendue
    tout de suite et la forge relue en arrière-plan (sauf « Actualiser », qui attend la nouvelle)."""
    if force or not _PARC["donnees"]:
        return lire_rapport_parc(True)
    if time.time() - _PARC["t"] > 60 and not _PARC.get("relecture"):
        _PARC["relecture"] = True

        def relire():
            try:
                lire_rapport_parc(True)
            except Exception:
                traceback.print_exc()
            finally:
                _PARC["relecture"] = False
        threading.Thread(target=relire, daemon=True).start()
    return _PARC["donnees"]


def lire_rapport_parc(force=False):
    """État de reprise de chaque machine suivie par le rapport, tiré des résultats réels par rapport/bs-rapport
    (classement, décisions, rapports de la CI sur la forge, bascules), et la page de rapport
    régénérée au passage. Lecture seule ; gardé 60 s."""
    with _PARC_VERROU:
        if force or not _PARC["donnees"] or time.time() - _PARC["t"] > 60:
            chemin = os.path.join(RACINE, "rapport", "bs-rapport")
            loader = importlib.machinery.SourceFileLoader("bs_rapport", chemin)
            br = importlib.util.module_from_spec(importlib.util.spec_from_loader("bs_rapport", loader))
            loader.exec_module(br)
            cfg = br.load(os.path.join(RACINE, "rapport", "vms.json"))
            try:
                vms = br.collect(cfg, False, (lire_json(REMISE) or {}).get("date"))
            except SystemExit as exc:  # classement introuvable : on le dit
                raise RuntimeError(str(exc))
            with open(RAPPORT_CONSOLE + ".new", "w", encoding="utf-8") as fh:
                fh.write(br.render(cfg, vms, False))
            os.replace(RAPPORT_CONSOLE + ".new", RAPPORT_CONSOLE)
            machines = []
            for v in vms:
                code, lib = br.verdict(v)
                r = br.risques(v)
                machines.append(dict(v, verdict={"code": code, "lib": lib}, suivi=re.sub(r"<[^>]+>", "", br.suivi(v) or ""),
                                     risques={"total": r["total"], "parts": [list(p) for p in r["parts"]]}))
            _PARC.update(t=time.time(), donnees={"date": time.time(), "forge": cfg["forge"], "machines": machines})
        return _PARC["donnees"]


def charger_classify():
    chemin = os.path.join(RACINE, "classement", "bs-classify")
    loader = importlib.machinery.SourceFileLoader("bs_classify", chemin)
    spec = importlib.util.spec_from_loader("bs_classify", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


ETAT_FICHIER = os.path.join(INV, "etat-console.json")  # parcours de la démo, relu au redémarrage de la console


class Etat:
    """État de la console, diffusé en entier à la page à chaque changement (Server-Sent Events).
    Toute modification d'un dict partagé se fait sous `verrou` (la sérialisation aussi).
    Il est aussi écrit sur disque (au plus une fois par seconde) et relu au démarrage : un redémarrage de la
    console ne doit pas lui faire oublier qu'une machine a été auditée, prouvée ou basculée."""

    def __init__(self, par, relire=True):
        self.verrou = threading.Condition()  # verrou réentrant : publier() peut s'appeler dessous
        self.version = 0
        self.occupe = False
        self.par = par
        self.op = None
        self.d = {}
        self.reinitialiser()
        if relire:
            self.relire()
        self._ecrit = self.version
        threading.Thread(target=self._sauvegarde, daemon=True).start()

    def relire(self):
        try:
            d = json.load(open(ETAT_FICHIER, encoding="utf-8"))
        except (OSError, ValueError):
            return
        # Une opération en cours au moment de l'arrêt ne reprendra pas : on le dit au lieu de la laisser tourner.
        for o in d.get("operations") or []:
            if o.get("etat") == "en_cours":
                o.update(etat="ko", fin=o.get("fin") or time.time(), erreur="interrompue : la console a redémarré")
                for pas in o.get("pas") or []:
                    if pas.get("etat") == "en_cours":
                        pas.update(etat="ko", resultat="interrompu : la console a redémarré")
        with self.verrou:
            self.d.update({k: v for k, v in d.items() if k in self.d and k not in ("par", "erreur")})
            for k in ("erreur_titre", "erreur_vers", "erreur_details", "erreur_cles"):
                self.d.pop(k, None)
        self.publier()

    def _sauvegarde(self):
        while True:
            time.sleep(1)
            if self.version == self._ecrit:
                continue
            with self.verrou:
                v, corps = self.version, json.dumps(self.d, ensure_ascii=False, default=str)
            try:
                with open(ETAT_FICHIER + ".new", "w", encoding="utf-8") as fh:
                    fh.write(corps)
                os.replace(ETAT_FICHIER + ".new", ETAT_FICHIER)
                self._ecrit = v
            except OSError:
                traceback.print_exc()

    def reinitialiser(self):
        with self.verrou:
            garde = {k: self.d.get(k) for k in ("preparation", "parc", "operations")}
            self.d = {"phase": "accueil", "par": self.par, "t0": None, "t_fin": None, "erreur": None,
                      "preparation": garde["preparation"] or {"etat": "a_faire", "date": None},
                      "parc": garde["parc"] or {}, "operations": garde["operations"] or [],
                      "audit": None, "ia": None, "code": None, "mr": None, "ci1": None, "refus": None,
                      "decisions": None, "ci2": None, "bascule": None, "journal": []}
        self.publier()

    def publier(self):
        with self.verrou:
            self.version += 1
            self.verrou.notify_all()

    def maj(self, **kw):
        with self.verrou:
            self.d.update(kw)
        self.publier()

    def journal(self, ligne):
        ligne = ligne.rstrip()
        if not ligne:
            return
        with self.verrou:
            self.d["journal"] = (self.d["journal"] + [[time.time(), ligne]])[-200:]
        self.publier()

    def instantane(self):
        with self.verrou:
            # page : version de index.html, pour qu'un onglet resté sur une ancienne page se recharge seul.
            return self.version, json.dumps(dict(self.d, maintenant=time.time(), occupe=self.occupe,
                                                 page=os.stat(os.path.join(ICI, "index.html")).st_mtime),
                                            ensure_ascii=False)


ETAT: Etat


class Operation:
    """Action lancée depuis la console, découpée en pas annoncés d'avance : la page montre ce qui
    va se passer, ce qui se passe (machine, explication) et ce qui s'est passé (résultat)."""

    def __init__(self, cle, titre, pas):
        self.d = {"id": f"{cle}-{time.time():.3f}", "cle": cle, "titre": titre, "debut": time.time(),
                  "fin": None, "etat": "en_cours",
                  "pas": [{"cle": c, "titre": t, "explication": e, "machine": m, "etat": "avenir",
                           "debut": None, "fin": None, "resultat": None} for c, t, e, m in pas]}
        with ETAT.verrou:
            ETAT.d["operations"] = (ETAT.d["operations"] + [self.d])[-15:]
            ETAT.op = self
        ETAT.publier()

    def _pas(self, cle):
        return next(p for p in self.d["pas"] if p["cle"] == cle)

    def etat(self, cle):
        return self._pas(cle)["etat"]

    def debut(self, cle, t=None):
        with ETAT.verrou:
            p = self._pas(cle)
            if p["etat"] == "avenir":
                p.update(etat="en_cours", debut=t or time.time())
        ETAT.publier()

    def fin(self, cle, resultat=None, etat="ok", t=None):
        """etat : ok, ko (erreur), bloque (garde-fou qui a joué son rôle), saute."""
        with ETAT.verrou:
            p = self._pas(cle)
            t = t or time.time()
            p.update(etat=etat, debut=p["debut"] or t, fin=t, resultat=resultat if resultat is not None else p["resultat"])
        ETAT.publier()

    def resultat(self, cle, texte):
        with ETAT.verrou:
            self._pas(cle)["resultat"] = texte
        ETAT.publier()

    def terminer(self, etat="ok", erreur=None):
        with ETAT.verrou:
            t = time.time()
            for p in self.d["pas"]:
                if p["etat"] == "en_cours":
                    p.update(etat="ko" if etat == "ko" else "ok", fin=t,
                             resultat=(erreur if etat == "ko" else p["resultat"]))
            self.d.update(etat=etat, fin=t, erreur=erreur)
        ETAT.publier()


def lancer(cmd, env=None, sur_ligne=None, cwd=RACINE):
    """Lance une commande, envoie chaque ligne à la sortie technique de la page, rend (code, sortie)."""
    e = dict(os.environ, **(env or {}))
    p = subprocess.Popen(cmd, cwd=cwd, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         bufsize=1)
    lignes = []
    for ligne in p.stdout:
        ligne = re.sub(r"[0-9a-f]{40}", "<jeton>", ligne.rstrip("\n"))
        lignes.append(ligne)
        if not ligne.startswith(("remote:", "    ")):
            ETAT.journal(ligne)
        if sur_ligne:
            sur_ligne(ligne)
    return p.wait(), "\n".join(lignes)


def ssh_ok(ip):
    return subprocess.run(SSH + ["-i", CLE_ADMIN, f"claude@{ip}", "true"], capture_output=True).returncode == 0


def collecter():
    """Deux collectes en parallèle (sans et avec contenu des fichiers), en lecture seule."""
    def une(avec_contenu):
        nom = f"{VM}-pieges" + (".content" if avec_contenu else "")
        # Délais : une machine qui disparaît en cours de collecte fait échouer l'étape au lieu de la bloquer.
        cmd = ["ssh", "-T", "-i", CLE_COLLECTE, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
               "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=4", f"bs-collect@{IP}"]
        if avec_contenu:
            cmd += ["bs-collect", "--with-content"]
        with open(os.path.join(INV, nom + ".json.new"), "wb") as fh:
            rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE).returncode
        if rc:
            raise RuntimeError(f"collecte {nom} en échec (code {rc})")
        os.replace(os.path.join(INV, nom + ".json.new"), os.path.join(INV, nom + ".json"))
    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        list(ex.map(une, (False, True)))


def classer():
    bc = charger_classify()
    ref = json.load(open(os.path.join(INV, f"{VM}-vierge.json"), encoding="utf-8"))
    cur = json.load(open(os.path.join(INV, f"{VM}-pieges.content.json"), encoding="utf-8"))
    items, ips = bc.run(ref, cur)
    return bc, ref, cur, items, ips


def resume_inventaire(cur):
    """Ce que la collecte a relevé, en chiffres lisibles."""
    pk = cur["packages"]
    return (f"{len(pk['installed'])} paquets, {len(cur['systemd']['units'])} services et unités, "
            f"{len(cur['users']['users'])} comptes, {len(cur['processes'])} processus, "
            f"{len(cur['listening'])} ports ouverts")


def statut_commit(sha):
    try:
        return Forge().call("GET", f"/repos/pme/infra/commits/{sha}/status").get("state")
    except Exception:  # forge lente ou VPN coupé : on réessaie
        return None


def attendre_ci(sha, cle, sur_progression=None):
    """Attend l'état final de la CI du commit ; met à jour ETAT[cle]. Avec `sur_progression`, lit
    le journal de progression de ci-verifier.sh sur la forge et le passe à cette fonction."""
    t0 = time.time()
    etapes = {k: {"cle": k, "libelle": lib, "explication": ex, "debut": None, "fin": None, "duree": None,
                  "code": None} for k, lib, ex in ETAPES_CI}
    while time.time() - t0 < 1200:
        st = statut_commit(sha)
        info = dict(ETAT.d.get(cle) or {}, etat=st or "en file", debut=t0, sha=sha[:7])
        if sur_progression:
            r = subprocess.run(SSH + ["-i", CLE_ADMIN, f"claude@{FORGE_IP}", f"cat /srv/bs-ci/{VM}.log"],
                               capture_output=True, text=True)
            lignes = r.stdout.splitlines()
            if lignes and lignes[0].split()[1:3] == ["debut_ci", sha]:
                for l in lignes[1:]:
                    m = l.split()
                    if len(m) >= 3 and m[2] in etapes:
                        if m[1] == "debut":
                            etapes[m[2]]["debut"] = float(m[0])
                        elif m[1] == "fin":
                            etapes[m[2]].update(fin=float(m[0]), duree=int(m[3]), code=int(m[4]))
                    elif len(m) >= 2 and m[1] == "echec":
                        info["echec"] = " ".join(m[2:])
                info["demarree"] = float(lignes[0].split()[0])
            info["etapes"] = [dict(etapes[k]) for k, _, _ in ETAPES_CI]
            sur_progression(info)
        ETAT.maj(**{cle: info})
        if st in ("success", "failure", "error"):
            info.update(fin=time.time(), duree=round(time.time() - t0))
            ETAT.maj(**{cle: info})
            return st
        time.sleep(2)
    raise TimeoutError("CI trop longue")


def rapport_ci(numero):
    """Données brutes du dernier rapport de CI publié sur la merge request (ci-rapport.py)."""
    for _ in range(10):
        coms = Forge().call("GET", f"/repos/pme/infra/issues/{numero}/comments")
        for c in reversed(coms or []):
            m = re.search(r"<!-- bs-verif (.*) -->", c.get("body", ""))
            if m:
                return json.loads(m.group(1).replace("\\u002d", "-"))
        time.sleep(2)
    return None


# « Garder » qu'aucun code ne sait appliquer. generation/bs-generate reproduit les fichiers (depuis le coffre), les
# sysctl, et recrée en service systemd un processus lancé à la main dont la ligne de commande est relevée ; un port
# est gardé avec le processus qui l'ouvre. Sans ligne de commande ou sans processus connu, rien à générer : l'écart
# resterait non justifié et la CI rouge à coup sûr.
def garder_impossible(cle, cur, liees):
    if cle.startswith("process:"):
        connu = any(p.get("cmdline") and f"process:{p.get('exe') or p['name']}@{p['user']}@"
                    f"{re.sub(r'^session-[0-9]+[.]scope$', 'session.scope', p.get('unit') or '-')}" == cle
                    for p in (cur or {}).get("processes", []))
        return None if connu else ("la ligne de commande de ce processus n'a pas été relevée : impossible d'en faire "
                                   "un service. Relancer l'audit pendant qu'il tourne.")
    if cle.startswith("listen:") and not any(l.startswith("process:") for l in liees):
        return "aucun processus connu n'ouvre ce port : rien à recréer. Relancer l'audit pendant qu'il est ouvert."
    return None


def liens_decisions(cles):
    """Éléments en attente qui vont ensemble et doivent recevoir la même décision : un port en écoute et le
    processus qui l'ouvre (même PID dans l'inventaire du dernier audit). Clés construites comme collecte/bs-compare.
    Renvoie {clé: [clés liées]}, groupes complets (un processus qui ouvre deux ports lie les trois)."""
    try:
        cur = json.load(open(os.path.join(INV, f"{VM}-pieges.content.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    cles, voisins = set(cles), {}
    for c in cles:
        if not c.startswith("listen:"):
            continue
        proto, reste = c[len("listen:"):].split(":", 1)
        addr, port = reste.rsplit(":", 1)
        pids = {p for l in cur.get("listening", []) if l.get("proto") == proto and str(l.get("port")) == port
                and (l.get("address") == addr or addr == "<ip-locale>") for p in l.get("pids", [])}
        for p in cur.get("processes", []):
            if p.get("pid") in pids:
                unit = re.sub(r"^session-\d+\.scope$", "session.scope", p.get("unit") or "-")
                k = f"process:{p.get('exe') or p['name']}@{p['user']}@{unit}"
                if k in cles and k != c:
                    voisins.setdefault(c, set()).add(k)
                    voisins.setdefault(k, set()).add(c)
    groupes = {}
    for c in voisins:
        vus, pile = {c}, [c]
        while pile:
            for v in voisins.get(pile.pop(), ()):
                if v not in vus:
                    vus.add(v)
                    pile.append(v)
        groupes[c] = sorted(vus - {c})
    return groupes


def cartes_decision():
    """Éléments en attente, avec le constat, la proposition du modèle et une raison préparée pour
    chaque choix possible (infra/demo/) : c'est la personne qui clique qui décide. Chaque carte dit aussi
    quels éléments vont avec elle (même décision imposée) et si « Garder » est applicable."""
    attente = json.load(open(os.path.join(DEPOT, VM, "attente.json"), encoding="utf-8"))
    pp = os.path.join(DEPOT, "decisions", f"{VM}.propositions.json")
    props = json.load(open(pp, encoding="utf-8")).get("propositions", {}) if os.path.exists(pp) else {}
    demo = json.load(open(DECISIONS_DEMO, encoding="utf-8")) if os.path.exists(DECISIONS_DEMO) else {}
    raisons = json.load(open(RAISONS_DEMO, encoding="utf-8")) if os.path.exists(RAISONS_DEMO) else {}
    liens = liens_decisions(a["cle"] for a in attente)
    try:
        cur = json.load(open(os.path.join(INV, f"{VM}-pieges.content.json"), encoding="utf-8"))
    except (OSError, ValueError):
        cur = None
    cartes = []
    for a in attente:
        r = dict(raisons.get(a["cle"]) or {})
        d = demo.get(a["cle"])
        if d and d.get("decision") not in r:
            r[d["decision"]] = d["raison"]
        impossible = garder_impossible(a["cle"], cur, liens.get(a["cle"], []))
        cartes.append({"cle": a["cle"], "constat": a["raison"], "proposition": props.get(a["cle"]), "raisons": r,
                       "liees": liens.get(a["cle"], []), "garder_impossible": impossible})
    # Un élément qu'on ne peut pas garder empêche de garder ceux qui vont avec lui.
    par_cle = {c["cle"]: c for c in cartes}
    for c in cartes:
        if not c["garder_impossible"]:
            bloquant = next((l for l in c["liees"] if (par_cle.get(l) or {}).get("garder_impossible")), None)
            if bloquant:
                c["garder_impossible"] = f"va avec {bloquant}, qui ne peut pas être gardé."
    return cartes


# ---------------------------------------------------------------- opérations

def preparer():
    # Après une bascule, la copie (sandbox) sert la production et l'original est éteint : préchauffer la
    # sandbox la détruirait, et les pièges seraient posés sur la copie. On remet en état d'abord.
    import sandbox as sbm
    from pve import PVE
    if sbm.en_production(PVE(), SBX_VMID):
        raise RuntimeError(f"La copie de {VM} sert la production depuis la bascule et l'original est éteint : "
                           "« Remettre en état » d'abord, puis « Préparer ».")
    op = Operation("preparer", "Préparation du laboratoire", [
        ("machines", "Machines joignables",
         "Connexion SSH d'administration aux 5 VM de la démo.", "bs-* · .200 à .204"),
        ("pieges", "Pièges de l'entreprise en place",
         "Deux pièges « à chaud » (réglage noyau, relais :9100) disparaissent à chaque redémarrage : "
         "on les repose si besoin.", M_ORIG),
        ("modele", "Modèle local chargé en mémoire",
         f"{MODELE} met 3 à 5 min à se charger sans GPU : on le charge avant l'oral.", M_IA),
        ("propositions", "Propositions du modèle calculées",
         "Audit à blanc et appel au modèle sur les inconnus ; la démo réutilise ces réponses si les "
         "preuves n'ont pas changé.", M_IA),
        ("sandbox", "Sandbox préchauffée",
         "Un clone neuf de la Debian vierge attend la CI, pour ne pas payer ~75 s de clonage en direct.",
         "luna · API Proxmox"),
    ])
    ETAT.maj(preparation={"etat": "en_cours", "date": None})

    op.debut("machines")
    with concurrent.futures.ThreadPoolExecutor(5) as ex:
        ok = dict(zip([ip for ip, *_ in PARC], ex.map(ssh_ok, [ip for ip, *_ in PARC])))
    ETAT.maj(parc={"date": time.time(), "joignable": ok})
    ko = [ip for ip, v in ok.items() if not v]
    if ko:
        raise RuntimeError("VM injoignables : démarrer " + ", ".join(ko))
    op.fin("machines", "5 VM sur 5 répondent")

    op.debut("pieges")
    r = subprocess.run(SSH + ["-i", CLE_ADMIN, f"claude@{IP}", "ss -Htln 'sport = :9100' | grep -q ."])
    if r.returncode:
        rc, _ = lancer([os.path.join(RACINE, "pme", "deploy.sh"), "pieges"])
        if rc:
            raise RuntimeError("pme/deploy.sh pieges en échec")
        op.fin("pieges", "reposés (la VM avait redémarré depuis la dernière démo)")
    else:
        op.fin("pieges", "déjà en place")

    def modele():
        op.debut("modele")
        ps = urllib.request.urlopen(f"{IA}/api/ps", timeout=5).read().decode()
        if f'"{MODELE}"' not in ps:
            op.resultat("modele", "chargement en cours (3 à 5 min)")
            req = urllib.request.Request(f"{IA}/api/generate", data=json.dumps(
                {"model": MODELE, "prompt": "ok", "stream": False, "think": False, "keep_alive": -1,
                 "options": {"num_predict": 1}}).encode())
            urllib.request.urlopen(req, timeout=600).read()
            op.fin("modele", f"{MODELE} chargé")
        else:
            op.fin("modele", f"{MODELE} déjà en mémoire")

        op.debut("propositions")
        collecter()
        bc, ref, cur, items, _ = classer()
        cache = json.load(open(CACHE_PREPARE, encoding="utf-8")) if os.path.exists(CACHE_PREPARE) else None
        doc = bc.proposer(items, ref, cur, IA, MODELE, cache)
        json.dump(doc, open(CACHE_PREPARE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        op.fin("propositions", f"{len(doc['propositions'])} propositions "
               + ("déjà calculées sur les mêmes preuves" if doc is cache else f"en {doc['duree_s']} s"))

    def sandbox():
        op.debut("sandbox")
        sb = os.path.join(RACINE, "infra", "sandbox.py")
        import sandbox as sbm
        from pve import PVE
        pve = PVE()
        vm = next((v for v in pve.get("/cluster/resources", type="vm") if v.get("vmid") == SBX_VMID), None)
        desc = pve.get(f"/nodes/{pve.node}/qemu/{SBX_VMID}/config").get("description", "") if vm else ""
        if vm and vm.get("status") == "running" and sbm.NEUVE in desc:
            op.fin("sandbox", f"{SBX} ({SBX_IP}) neuve, prête")
            return
        op.resultat("sandbox", "clone neuf en cours (environ 75 s)")
        if vm:
            subprocess.run([sys.executable, "-I", sb, "destroy", str(SBX_VMID)], capture_output=True)
        r = subprocess.run([sys.executable, "-I", sb, "create", SBX, str(SBX_VMID), SBX_IP, "--neuve"],
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("sandbox non créée : " + (r.stdout[-200:] + r.stderr[-200:]).strip())
        op.fin("sandbox", f"{SBX} ({SBX_IP}) neuve, prête")

    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        for f in [ex.submit(modele), ex.submit(sandbox)]:
            f.result()
    op.terminer()
    ETAT.maj(preparation={"etat": "ok", "date": time.time()})


def audit():
    op = Operation("audit", f"Audit de {VM}", [
        ("collecte", "Collecte en lecture seule",
         "Connexion SSH avec le compte bs-collect, qui ne peut rien modifier. Relevé des paquets, services, "
         "fichiers modifiés, comptes, tâches planifiées, ports ouverts et réglages du noyau.", M_ORIG),
        ("classement", "Classement des écarts",
         "Chaque différence avec une Debian 13 neuve reçoit une règle et une preuve : compris, secret, "
         "donnée, bruit ou inconnu.", POSTE),
        ("ia", "Avis du modèle local sur les inconnus",
         "Seuls les inconnus partent au modèle, avec leurs preuves et les secrets masqués. "
         "Le modèle propose, un humain décide.", M_IA),
        ("code", "Génération du code de reconstruction",
         "Ansible pour tout ce qui est compris, secrets envoyés au coffre, données confiées à la sauvegarde. "
         "Les inconnus ne sont jamais appliqués.", POSTE),
        ("mr", "Merge request sur la forge",
         "Une merge request neuve dans le dépôt de l'entreprise. Rien n'atteint la production sans relecture.",
         M_FORGE),
        ("ci1", "Contrôle automatique (CI)",
         "La CI refuse de reconstruire une machine tant qu'un inconnu n'a pas été tranché.", M_FORGE),
        ("garde", "Garde-fou de bascule",
         "On tente de basculer la production maintenant : le garde-fou exige une CI verte.", POSTE),
    ])
    ETAT.maj(phase="audit", t0=time.time(), t_fin=None)

    op.debut("collecte")
    t = time.time()
    collecter()
    bc, ref, cur, items, ips = classer()
    op.fin("collecte", resume_inventaire(cur))

    op.debut("classement")
    comptes = {}
    for i in items:
        comptes[i["statut"]] = comptes.get(i["statut"], 0) + 1
    ETAT.maj(audit={"duree": round(time.time() - t, 1), "total": len(items), "comptes": comptes,
                    "elements": [{"cle": i["key"], "statut": i["statut"], "ecart": i["ecart"], "raison": i["raison"]}
                                 for i in items],
                    "ip_en_dur": [{"fichier": h["path"], "ligne": h["line"], "ip": h["ip"]} for h in ips],
                    "machine": {"nom": cur["meta"]["hostname"], "os": cur["meta"]["os_release"].get("PRETTY_NAME"),
                                "noyau": cur["meta"]["kernel"], "resume": resume_inventaire(cur)},
                    "date": cur["meta"]["collected_at"]})
    op.fin("classement", f"{len(items)} écarts : {comptes.get('inconnu', 0)} inconnus, {comptes.get('secret', 0)} secrets, "
           f"{comptes.get('donnee', 0)} données, {comptes.get('compris', 0)} compris, {comptes.get('ignore', 0)} bruit"
           + (f" · {len(ips)} adresses IP écrites en dur" if ips else ""))

    ETAT.maj(phase="ia", ia={"etat": "en_cours", "modele": MODELE, "debut": time.time()})
    op.debut("ia")
    t = time.time()
    infos = {}

    def sur_ligne(l):
        m = re.match(r"propositions de (\S+) : (\d+) \((cache|[\d.]+ s)\)", l)
        if m:
            ETAT.maj(ia={"etat": "ok", "modele": m.group(1), "nombre": int(m.group(2)),
                         "cache": m.group(3) == "cache", "duree": round(time.time() - t, 1)})
            op.fin("ia", f"{m.group(2)} propositions" + (" (calculées à la préparation, mêmes preuves)"
                                                           if m.group(3) == "cache" else f" en {m.group(3)}"))
            op.debut("code")
        if l.startswith('{"vm"'):
            infos["code"] = json.loads(l)
            c = infos["code"]
            op.fin("code", f"{c.get('taches')} tâches Ansible, {c.get('coffre')} secrets au coffre")
            op.debut("mr")
        m = re.search(r"(http://\S+/pulls/(\d+))", l)
        if m:
            infos["mr"] = {"url": m.group(1), "numero": int(m.group(2))}
            op.fin("mr", f"merge request n° {m.group(2)} " + ("mise à jour" if "existante" in l else "ouverte"))
    rc, sortie = lancer([os.path.join(RACINE, "infra", "bs-mr.sh"), VM,
                         f"Premier audit de {VM} : inconnus en attente de décision"],
                        env={"BS_A_ZERO": "1", "BS_NOUVELLE_MR": "1", "BS_OLLAMA": IA, "BS_CACHE_PREPARE": CACHE_PREPARE},
                        sur_ligne=sur_ligne)
    if rc:
        raise RuntimeError("bs-mr.sh en échec")
    sha = subprocess.run(["git", "-C", DEPOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    pp = os.path.join(DEPOT, "decisions", f"{VM}.propositions.json")
    if os.path.exists(pp):  # provenance affichée : durée réelle de l'appel au modèle, date, jetons
        doc = json.load(open(pp, encoding="utf-8"))
        ETAT.maj(ia=dict(ETAT.d["ia"] or {}, duree_modele=doc.get("duree_s"), date_modele=doc.get("date"),
                         jetons=doc.get("jetons"), empreinte=doc.get("empreinte"), sans_preuve=doc.get("sans_preuve", []),
                         nombre=len(doc.get("propositions", {})), propositions=doc.get("propositions", {})))
    for k in ("ia", "code", "mr"):  # sortie inattendue de bs-mr.sh : pas laissé « en cours »
        if op.etat(k) in ("avenir", "en_cours"):
            op.fin(k)
    ETAT.maj(phase="ci1", code=dict(infos.get("code", {}), duree=round(time.time() - t, 1)),
             mr=dict(infos.get("mr", {}), sha=sha[:7], branche=f"reconstruction/{VM}"),
             decisions={"cartes": cartes_decision(), "sans_preuve": (ETAT.d["ia"] or {}).get("sans_preuve", [])})

    op.debut("ci1")
    st = attendre_ci(sha, "ci1")
    n = len(ETAT.d["decisions"]["cartes"])
    ETAT.maj(ci1=dict(ETAT.d["ci1"], attente=n))
    if st == "success":
        op.fin("ci1", f"verte en {ETAT.d['ci1']['duree']} s")
        op.fin("garde", "inutile : la CI est déjà verte", "saute")
    else:
        op.fin("ci1", f"merge bloqué : {n} décisions humaines en attente (réponse en {ETAT.d['ci1']['duree']} s)",
               "bloque")
        ETAT.maj(phase="refus")
        op.debut("garde")
        rc, sortie = lancer([sys.executable, "-I", os.path.join(RACINE, "infra", "bascule.py"), "vers-copie"])
        motif = next((l for l in sortie.splitlines() if l.startswith("refusé")), sortie.splitlines()[-1] if sortie else "")
        ETAT.maj(refus={"refusee": rc != 0, "motif": motif, "ci": st})
        op.fin("garde", motif or "refusée", "bloque" if rc else "ok")
    op.terminer()


LIB_CHOIX = {"reproduire": "Garder", "ne pas reproduire": "Retirer", "accepter": "Accepter la perte"}


def libelle(cle):
    """Nom lisible d'un élément d'inventaire, pour les messages : « le port 9100/tcp », « le processus … »."""
    genre, _, reste = cle.partition(":")
    if genre == "listen":
        proto, _, rest = reste.partition(":")
        return f"le port {rest.rsplit(':', 1)[-1]}/{proto}"
    if genre == "process":
        exe, user, unit = (reste.split("@") + ["", ""])[:3]
        return f"le processus {exe} ({user}{', lancé à la main' if unit == 'session.scope' else ''})"
    if genre == "sysctl":
        return f"le réglage noyau {reste}"
    if genre in ("file", "data"):
        return reste
    return cle


class DecisionsRefusees(ValueError):
    """Décisions refusées avant tout envoi : chaque problème en clair, et les éléments à montrer dans la page."""
    def __init__(self, problemes, cles):
        super().__init__(" ".join(problemes))
        self.problemes, self.cles = problemes, sorted(set(cles))


def controler_decisions(cartes, choix):
    """Ce qui empêche d'envoyer les décisions : choix ou raison manquants, « Garder » qu'aucun code ne sait
    appliquer, éléments liés (un port et le processus qui l'ouvre) qui ne reçoivent pas la même décision."""
    problemes, cles, vus = [], [], set()
    for c in cartes:
        k, ch = c["cle"], choix.get(c["cle"]) or {}
        d = ch.get("decision")
        if d not in LIB_CHOIX:
            problemes.append(f"Aucune décision pour {libelle(k)}.")
            cles.append(k)
            continue
        if not (ch.get("raison") or "").strip():
            problemes.append(f"Raison manquante pour {libelle(k)} (« {LIB_CHOIX[d]} »).")
            cles.append(k)
        if d == "reproduire" and c.get("garder_impossible"):
            problemes.append(f"Impossible de garder {libelle(k)} : {c['garder_impossible']}")
            cles.append(k)
        for l in c.get("liees", []):
            dl = (choix.get(l) or {}).get("decision")
            if frozenset((k, l)) in vus or dl not in LIB_CHOIX or dl == d:
                continue
            vus.add(frozenset((k, l)))
            port, proc = (k, l) if k.startswith("listen:") else (l, k)
            problemes.append(f"Choix contradictoires : {libelle(port)} est sur « {LIB_CHOIX[choix[port]['decision']]} », "
                             f"{libelle(proc)}, qui l'ouvre, est sur « {LIB_CHOIX[choix[proc]['decision']]} ». "
                             "Le port n'existe que si son processus tourne : choisir la même décision pour les deux.")
            cles += [k, l]
    return problemes, cles


def decider(choix):
    cartes = ETAT.d["decisions"]["cartes"]
    # Même contrôle que la page, au cas où elle serait restée sur une version ancienne : rien ne part à la CI.
    problemes, cles = controler_decisions(cartes, choix)
    if problemes:
        raise DecisionsRefusees(problemes, cles)
    op = Operation("decider", f"Décisions et preuve de reconstruction de {VM}", [
        ("signature", "Décisions signées",
         f"Chaque inconnu reçoit une décision, une raison et le nom de {ETAT.par}. Elles sont versionnées "
         "avec le code.", POSTE),
        ("code", "Code régénéré, merge request à jour",
         "Le code de reconstruction tient compte des décisions ; la CI repart sur le nouveau commit.", M_FORGE),
        ("file", "Prise en charge par la CI",
         "Le runner de la forge récupère la merge request et lance la vérification.", M_FORGE),
    ] + [(k, lib, ex, M_SBX) for k, lib, ex in ETAPES_CI])
    op.debut("signature")
    fichier = os.path.join(INV, f"decisions-salle-{VM}.json")
    json.dump({k: {"decision": v["decision"], "raison": v["raison"].strip()} for k, v in choix.items()},
              open(fichier, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    ETAT.maj(phase="ci2", decisions=dict(ETAT.d["decisions"], prises=choix, date=time.time()))
    nb = {}
    for v in choix.values():
        nb[v["decision"]] = nb.get(v["decision"], 0) + 1
    lib = {"reproduire": "garder", "ne pas reproduire": "retirer", "accepter": "accepter la perte"}
    op.fin("signature", ", ".join(f"{n} « {lib.get(d, d)} »" for d, n in nb.items()) + f", signées {ETAT.par}")

    op.debut("code")
    rc, _ = lancer([sys.executable, "-I", os.path.join(RACINE, "infra", "bs-decider.py"), VM, "--par", ETAT.par,
                    "--depuis", fichier])
    if rc:
        raise RuntimeError("bs-decider.py en échec")
    sha = subprocess.run(["git", "-C", DEPOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    op.fin("code", f"commit {sha[:7]} poussé sur reconstruction/{VM}")
    op.debut("file")

    def progression(info):
        if info.get("demarree") and op.etat("file") == "en_cours":
            op.fin("file", "vérification lancée")
        for e in info.get("etapes", []):  # horodatage de la CI elle-même, pas celui du sondage
            if e["fin"]:
                if op.etat(e["cle"]) in ("avenir", "en_cours"):
                    op.debut(e["cle"], e["debut"])
                    op.fin(e["cle"], None, "ok" if e["code"] == 0 else "ko", e["fin"])
            elif e["debut"]:
                op.debut(e["cle"], e["debut"])
    st = attendre_ci(sha, "ci2", sur_progression=progression)
    brut = rapport_ci(ETAT.d["mr"]["numero"]) if (ETAT.d.get("mr") or {}).get("numero") else None
    if brut:
        cmp_, s, tm = (brut.get("comparaison") or {}).get("summary"), brut.get("sauvegarde"), brut.get("test_metier")
        if cmp_:
            op.resultat("comparaison", f"{cmp_.get('differences')} écarts comparés, "
                                       f"{cmp_.get('unjustified')} non justifié(s)")
        if s:
            op.resultat("restauration", f"instantané {s.get('instantane')}, vieux de {s.get('age_h')} h")
        if tm:
            op.resultat("test_metier", "commande créée, relue et supprimée" if tm.get("ok") else "rouge")
        if brut.get("echec"):
            op.resultat("comparaison", f"échec : {brut['echec']}")
    ETAT.maj(ci2=dict(ETAT.d["ci2"], rapport=brut), phase="preuve" if st == "success" else "ci2")
    if st != "success":
        # La cause lisible, tirée du rapport de la CI : ce qui bloque, pas le code de retour.
        brut = brut or {}
        bloquants = (brut.get("comparaison") or {}).get("bloquants") or []
        tm = brut.get("test_metier")
        if brut.get("echec"):
            motif = brut["echec"]
        elif bloquants:
            motif = (f"{len(bloquants)} écart{'s' if len(bloquants) > 1 else ''} sans justification entre la copie "
                     f"et l'original ({', '.join(bloquants[:3])}{'…' if len(bloquants) > 3 else ''})")
        elif tm and not tm.get("ok"):
            motif = "le test métier est rouge sur la copie"
        else:
            motif = "la vérification s'est arrêtée en erreur" if st == "error" else f"vérification « {st} »"
        raise RuntimeError(f"{motif[0].upper()}{motif[1:]}. La bascule reste bloquée.")
    op.terminer()


def basculer():
    op = Operation("basculer", f"Bascule de {VM} vers la copie prouvée", [
        ("verif", "Vérification de la preuve",
         "La bascule n'est permise que si la CI de la merge request est verte.", M_FORGE),
        ("arret", "Arrêt de l'original",
         "L'original est éteint, pas détruit : il reste disponible pour un retour arrière. Le service est coupé.",
         M_ORIG),
        ("identite", "La copie prend l'identité de production",
         f"Adresse {IP} et nom {VM} sur la copie reconstruite.", M_SBX),
        ("demarrage", "Isolation levée, redémarrage",
         "Le pare-feu de la sandbox est retiré, la copie redémarre et doit répondre en HTTP.", f"copie · {IP}"),
        ("test", "Test métier sur la production",
         "Une commande traverse le proxy, le DNS et le serveur de mail réels de l'entreprise.", f"copie · {IP}"),
    ])
    ETAT.maj(phase="bascule", bascule={"debut": time.time(), "lignes": [], "tests": [], "coupure": None})
    b = ETAT.d["bascule"]
    op.debut("verif")
    suite = [("éteint, gardé", "verif", "arret"), ("copie : IP et nom", "arret", "identite"),
             ("isolation levée", "identite", "demarrage"), ("test métier complet", "demarrage", "test")]

    def sur_ligne(l):
        with ETAT.verrou:
            m = re.match(r"\[\s*([\d.]+) s\] (.*)", l)
            if m:
                b["lignes"].append({"t": float(m.group(1)), "texte": m.group(2)})
                if "éteint, gardé" in l:
                    b["coupure_debut"] = time.time()
                c = re.search(r"coupure du service : ([\d.]+) s", l)
                if c:
                    b["coupure"] = float(c.group(1))
                    b["retabli"] = time.time()
            m = re.match(r"\s+(OK|ÉCHEC|KO|ECHEC)\s+(.+?) \(([\d.]+) s\) : (.*)", l)
            if m:
                b["tests"].append({"ok": m.group(1) == "OK", "etape": m.group(2), "duree": float(m.group(3)),
                                   "detail": m.group(4)})
            if l.startswith("TOUT VERT"):
                b["vert"] = l
        if "vérification CI" in l:
            st = l.rsplit(":", 1)[-1].strip()
            op.resultat("verif", "CI verte" if st == "success" else f"CI : {st}")
        for motif, avant, apres in suite:
            if motif in l:
                op.fin(avant)
                op.debut(apres)
        if "coupure du service" in l:
            op.fin("test", f"vert · coupure totale {b['coupure']} s".replace(".", ","))
        if "test métier ROUGE" in l:
            op.fin("test", "rouge : « Remettre en état » pour revenir à l'original", "ko")
        if l.startswith("refusé"):
            op.fin("verif", l, "bloque")
        ETAT.publier()
    rc, _ = lancer([sys.executable, "-I", os.path.join(RACINE, "infra", "bascule.py"), "vers-copie"], sur_ligne=sur_ligne)
    if op.etat("verif") == "bloque":  # garde-fou : rien n'a été coupé
        ETAT.maj(phase="preuve", bascule=None)
        raise RuntimeError(op._pas("verif")["resultat"])
    with ETAT.verrou:
        b.update(fin=time.time(), ok=rc == 0)
    ETAT.maj(phase="fini", t_fin=time.time())
    d = ETAT.d
    res = {"total_s": round(d["t_fin"] - d["t0"]) if d["t0"] else None, "coupure_s": b.get("coupure"),
           "audit_s": d["audit"] and d["audit"]["duree"],
           "ia": d["ia"] and {k: v for k, v in d["ia"].items() if k != "propositions"},
           "code_s": d["code"] and d["code"].get("duree"),
           "ci_rouge_s": d["ci1"] and d["ci1"].get("duree"), "ci_verte_s": d["ci2"] and d["ci2"].get("duree"),
           "ci_verte_etapes": d["ci2"] and {e["cle"]: e["duree"] for e in d["ci2"].get("etapes", [])},
           "decisions_s": d["decisions"] and d["decisions"].get("date") and d["ci1"]
           and round(d["decisions"]["date"] - d["ci1"]["fin"]), "mr": d["mr"], "par": ETAT.par}
    sortie = os.path.join(RACINE, "banc", "resultats", time.strftime("demo-salle-%Y%m%d-%H%M.json"))
    json.dump(res, open(sortie, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    ETAT.journal(f"résultats : {os.path.relpath(sortie, RACINE)}")
    if rc:
        raise RuntimeError("test métier rouge après bascule : Laboratoire → « Remettre en état »")
    op.terminer()


def remettre():
    op = Operation("remettre", "Remise en état du laboratoire", [
        ("retour", "Retour à l'original",
         "La copie est éteinte, l'original rallumé : la production revient à son état d'avant la démo.",
         "luna · API Proxmox"),
        ("pieges", "Pièges reposés",
         "Les pièges à chaud ont disparu au redémarrage : on les remet pour la prochaine démo.", M_ORIG),
    ])
    ETAT.maj(phase="remise")
    op.debut("retour")
    rc, _ = lancer([sys.executable, "-I", os.path.join(RACINE, "infra", "bascule.py"), "retour"])
    if rc:
        raise RuntimeError("retour arrière en échec")
    op.fin("retour", f"{VM} d'origine rallumée")
    op.debut("pieges")
    rc, _ = lancer([os.path.join(RACINE, "pme", "deploy.sh"), "pieges"])
    op.fin("pieges", "en place" if rc == 0 else "échec de pme/deploy.sh pieges", "ok" if rc == 0 else "ko")
    op.terminer("ok" if rc == 0 else "ko")
    ETAT.d["preparation"] = {"etat": "a_faire", "date": None}
    ETAT.reinitialiser()


REMISE = os.path.join(INV, "remise-a-zero.json")  # date avant laquelle la forge et les bascules ne sont plus lues


def reinitialiser_donnees():
    """Laboratoire → « Réinitialiser les données » : la console repart comme avant le premier audit, sans rien
    supprimer. Audits et accès vérifiés du parc, journal des actions et décisions de la salle sont déplacés dans
    inventaires/archives/<date>/ ; la merge request ouverte est fermée (rouvrable sur la forge) ; les vérifications
    de la forge et les bascules antérieures ne sont plus lues (REMISE, à supprimer pour les réafficher).
    Le registre du parc, les décisions versionnées, les VM et la préparation ne changent pas."""
    import shutil
    archive = os.path.join(INV, "archives", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(os.path.join(archive, "parc"), exist_ok=True)
    deplaces = 0
    for nom in sorted(os.listdir(DOSSIER_PARC)) if os.path.isdir(DOSSIER_PARC) else []:
        if nom.endswith((".acces.json", ".classement.json", ".content.json")):
            os.replace(os.path.join(DOSSIER_PARC, nom), os.path.join(archive, "parc", nom))
            deplaces += 1
    with _JOURNAL_VERROU:
        for chemin in (JOURNAL, os.path.join(INV, f"decisions-salle-{VM}.json")):
            if os.path.exists(chemin):
                os.replace(chemin, os.path.join(archive, os.path.basename(chemin)))
    if os.path.exists(ETAT_FICHIER):
        shutil.copy2(ETAT_FICHIER, os.path.join(archive, os.path.basename(ETAT_FICHIER)))
    fermees, err = [], None
    try:
        f = Forge()
        for p in f.call("GET", "/repos/pme/infra/pulls?state=open"):
            f.call("PATCH", f"/repos/pme/infra/pulls/{p['number']}", {"state": "closed"})
            fermees.append(p["number"])
    except Exception as exc:  # forge injoignable : le reste est fait, on le dit
        err = str(exc)
    remise = {"date": time.time(), "par": ETAT.par, "archive": os.path.relpath(archive, RACINE), "mr_fermees": fermees}
    with open(REMISE, "w", encoding="utf-8") as fh:
        json.dump(remise, fh, indent=2, ensure_ascii=False)
    with ETAT.verrou:
        ETAT.d["operations"] = []
        ETAT.op = None
    ETAT.reinitialiser()
    _PARC.update(t=0, donnees=None)
    detail = (f"{deplaces} fichiers d'audit archivés dans {remise['archive']}, "
              + (f"MR fermée{'s' if len(fermees) > 1 else ''} : {', '.join(f'n° {n}' for n in fermees)}" if fermees
                 else "aucune MR ouverte") + (f" ; forge injoignable : {err}" if err else ""))
    tracer("reinitialiser", "laboratoire", detail, "ko" if err else "ok")
    return dict(remise, erreur=err)


def reafficher_historique():
    """Annule le masquage : la forge et les bascules sont relues en entier. Les fichiers archivés restent où ils sont."""
    try:
        os.remove(REMISE)
    except FileNotFoundError:
        pass
    _PARC.update(t=0, donnees=None)
    tracer("reafficher", "laboratoire", "historique de la forge et des bascules réaffiché")
    return {}


def machine_du_parc(vm):
    m = next((x for x in lire_parc().get("machines", []) if x["vm"] == vm), None)
    if not m:
        raise ValueError(f"{vm} n'est pas dans le parc")
    return m


def verifier_acces(corps):
    """Vérifie l'accès de collecte d'une machine déclarée : périmètre, identité du serveur, connexion,
    restriction du compte, collecte d'essai. Ne modifie rien sur la machine."""
    m = machine_du_parc(str(corps.get("vm", "")))
    vm, ip = m["vm"], m["ip"]
    cible = f"{vm} · {ip}"
    op = Operation("acces", f"Vérification de l'accès à {vm}", [
        ("perimetre", "Adresse dans le périmètre autorisé",
         "Black Start ne se connecte qu'aux réseaux déclarés à l'installation de la plateforme.", POSTE),
        ("empreinte", "Identité du serveur",
         "Empreinte de la clé d'hôte SSH : enregistrée à la première vérification, puis exigée à chaque connexion.", cible),
        ("connexion", "Connexion avec le compte bs-collect",
         "Clé de la plateforme, sans mot de passe. Le compte n'existe que si le script d'installation a été lancé.", cible),
        ("restriction", "Compte limité à la collecte",
         "On demande au serveur une autre commande (id) : il doit la refuser.", cible),
        ("essai", "Collecte d'essai",
         "Collecte en lecture seule, sans le contenu des fichiers : système, paquets, services.", cible),
    ])
    op.d["vm"] = vm
    os.makedirs(DOSSIER_PARC, exist_ok=True)
    res = {"etat": "ko", "date": time.time(), "par": ETAT.par, "ip": ip}

    def echec(pas, motif):
        op.fin(pas, motif, "ko")
        res["erreur"] = motif
        json.dump(res, open(os.path.join(DOSSIER_PARC, f"{vm}.acces.json"), "w", encoding="utf-8"), ensure_ascii=False)
        raise RuntimeError(motif)

    op.debut("perimetre")
    ok, motif = dans_perimetre(ip)
    if not ok:
        echec("perimetre", motif)
    op.fin("perimetre", f"{ip} autorisée")

    op.debut("empreinte")
    scan = subprocess.run(["ssh-keyscan", "-T", "5", "-t", "ed25519", ip], capture_output=True, text=True).stdout
    lignes = [l for l in scan.splitlines() if l and not l.startswith("#")]
    if not lignes:
        echec("empreinte", f"{ip} ne répond pas en SSH (port 22) : machine éteinte, pare-feu ou mauvaise adresse")
    emp = subprocess.run(["ssh-keygen", "-lf", "-"], input=lignes[0] + "\n", capture_output=True, text=True).stdout.split()
    res["empreinte"] = emp[1] if len(emp) > 1 else "?"
    connue = subprocess.run(["ssh-keygen", "-F", ip, "-f", KNOWN_HOSTS], capture_output=True, text=True).stdout \
        if os.path.exists(KNOWN_HOSTS) else ""
    connue = [l for l in connue.splitlines() if l and not l.startswith("#")]
    # Type et clé seulement : une ligne peut porter une marque (« bascule-copie », infra/bascule.py), et
    # l'adresse peut avoir deux empreintes admises pendant une bascule (l'original éteint et la copie).
    if connue and lignes[0].split()[1:3] not in [l.split()[1:3] for l in connue]:
        echec("empreinte", f"l'empreinte de {ip} a changé depuis la dernière vérification ({res['empreinte']}) : "
                           "serveur réinstallé ou usurpé. Vérifier sur le serveur avant de retirer l'ancienne empreinte.")
    if not connue:
        with open(KNOWN_HOSTS, "a", encoding="utf-8") as fh:
            fh.write(lignes[0] + "\n")
    op.fin("empreinte", f"{res['empreinte']}" + ("" if connue else " · enregistrée (première connexion)"))
    res["empreinte_nouvelle"] = not connue

    op.debut("connexion")
    r = subprocess.run(SSH_COLLECTE + [f"bs-collect@{ip}", "id"], capture_output=True, text=True, timeout=30)
    if "commande refusée" in r.stderr:
        op.fin("connexion", "clé de la plateforme acceptée")
        op.debut("restriction")
        op.fin("restriction", "« id » refusée : seule la collecte est permise")
    elif r.returncode == 0:
        op.fin("connexion", "clé de la plateforme acceptée")
        op.debut("restriction")
        echec("restriction", "le compte bs-collect accepte d'autres commandes que la collecte : relancer le script "
                             "d'installation pour remettre la commande forcée")
    elif "Permission denied" in r.stderr:
        echec("connexion", "connexion refusée : le script d'installation n'a pas été lancé sur ce serveur, "
                           "ou une autre clé y est autorisée")
    else:
        echec("connexion", "connexion impossible : " + (r.stderr.strip().splitlines() or ["sans message"])[-1])

    op.debut("essai")
    t = time.time()
    r = subprocess.run(SSH_COLLECTE + [f"bs-collect@{ip}"], capture_output=True, timeout=300)
    try:
        inv = json.loads(r.stdout)
    except ValueError:
        echec("essai", "la collecte n'a pas rendu d'inventaire : " + r.stderr.decode(errors="replace").strip()[-200:])
    meta = inv["meta"]
    res.update(etat="ok", duree_s=round(time.time() - t, 1), hostname=meta["hostname"],
               os=meta["os_release"].get("PRETTY_NAME"), noyau=meta.get("kernel"), collecteur=meta.get("collector_version"),
               paquets=len(inv["packages"]["installed"]), services=len(inv["systemd"].get("units", [])),
               ports=len(inv.get("listening", [])), illisible=len(inv.get("unreadable", [])))
    json.dump(res, open(os.path.join(DOSSIER_PARC, f"{vm}.acces.json"), "w", encoding="utf-8"), ensure_ascii=False)
    op.fin("essai", f"{res['os']}, {res['paquets']} paquets, {res['ports']} ports ouverts, en {fr_s(res['duree_s'])}"
           + (f" · le serveur se nomme « {meta['hostname']} »" if meta["hostname"] != vm else ""))
    op.terminer()


def fr_s(s):
    return f"{s:.1f} s".replace(".", ",")


def premier_audit(corps):
    """Premier audit d'une machine intégrée : collecte avec contenu (lecture seule), comparaison avec
    l'image de référence, classement de chaque écart. Résultat dans inventaires/parc/ (hors Git)."""
    m = machine_du_parc(str(corps.get("vm", "")))
    vm, ip = m["vm"], m["ip"]
    acces = lire_json(os.path.join(DOSSIER_PARC, f"{vm}.acces.json")) or {}
    if acces.get("etat") != "ok":
        raise RuntimeError(f"accès de collecte à {vm} non vérifié : Vérifier l'accès d'abord")
    cfg = lire_parc()
    ref_cfg = cfg.get("reference", {})
    cible = f"{vm} · {ip}"
    op = Operation("integrer", f"Premier audit de {vm}", [
        ("collecte", "Collecte en lecture seule",
         "Paquets, services, fichiers modifiés, comptes, tâches planifiées, ports, réglages du noyau, avec le "
         "contenu des petits fichiers de configuration. Il reste sur la plateforme, jamais dans Git.", cible),
        ("comparaison", "Comparaison avec l'image de référence",
         f"Ce qui distingue {vm} de : {ref_cfg.get('nom', 'la référence')}. L'identité propre à chaque machine "
         "(nom, adresse, clés d'hôte) est écartée par règle.", POSTE),
        ("classement", "Classement des écarts",
         "Chaque écart reçoit un statut et la règle qui l'a classé : compris, secret, donnée, bruit ou inconnu.", POSTE),
    ])
    op.d["vm"] = vm
    op.debut("collecte")
    t = time.time()
    brut = os.path.join(DOSSIER_PARC, f"{vm}.content.json")
    fd = os.open(brut + ".new", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        r = subprocess.run(SSH_COLLECTE + [f"bs-collect@{ip}", "bs-collect --with-content"], stdout=fh,
                           stderr=subprocess.PIPE, timeout=600)
    if r.returncode:
        os.remove(brut + ".new")
        raise RuntimeError("collecte en échec : " + r.stderr.decode(errors="replace").strip()[-200:])
    os.replace(brut + ".new", brut)
    cur = json.load(open(brut, encoding="utf-8"))
    duree_collecte = round(time.time() - t, 1)
    op.fin("collecte", resume_inventaire(cur) + f", en {fr_s(duree_collecte)}")

    op.debut("comparaison")
    ref = lire_json(os.path.join(RACINE, ref_cfg.get("fichier", "")))
    if not ref:
        raise RuntimeError(f"image de référence introuvable : {ref_cfg.get('fichier')}")
    bc = charger_classify()
    bcmp = bc.load_compare()
    items, ips = bc.run(ref, cur, [bcmp.DEFAULT_RULES, os.path.join(RACINE, "collecte", "regles", "reference.json")])
    op.fin("comparaison", f"{len(items)} écarts avec {ref_cfg.get('nom', 'la référence')}")

    op.debut("classement")
    comptes = {}
    for i in items:
        comptes[i["statut"]] = comptes.get(i["statut"], 0) + 1
    # IP écrites en dur : on écarte les fichiers d'identité justifiés par règle (passerelle et DNS de l'interface).
    ignores = {i["key"].partition(":")[2] for i in items if i["statut"] == "ignore"}
    ips = [h for h in ips if h["path"] not in ignores]
    doc = {"vm": vm, "date": time.time(), "par": ETAT.par, "duree_s": round(time.time() - t, 1),
           "duree_collecte_s": duree_collecte, "reference": ref_cfg, "collecte": cur["meta"]["collected_at"],
           "machine": {"nom": cur["meta"]["hostname"], "os": cur["meta"]["os_release"].get("PRETTY_NAME"),
                       "noyau": cur["meta"]["kernel"], "resume": resume_inventaire(cur)},
           "total": len(items), "comptes": comptes,
           "elements": [{"cle": i["key"], "statut": i["statut"], "ecart": i["ecart"], "raison": i["raison"]} for i in items],
           "ip_en_dur": [{"fichier": h["path"], "ligne": h["line"], "ip": h["ip"]} for h in ips]}
    with open(os.path.join(DOSSIER_PARC, f"{vm}.classement.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
    op.fin("classement", f"{comptes.get('inconnu', 0)} inconnus, {comptes.get('secret', 0)} secrets, "
           f"{comptes.get('donnee', 0)} données, {comptes.get('compris', 0)} compris, {comptes.get('ignore', 0)} bruit"
           + (f" · {len(ips)} adresses IP écrites en dur" if ips else ""))
    op.terminer()


ACTIONS = {"preparer": preparer, "audit": audit, "decider": decider, "basculer": basculer, "remettre": remettre,
           "acces": verifier_acces, "integrer": premier_audit}
AVEC_CORPS = {"acces", "integrer"}


# Journal des actions : qui a fait quoi, quand, sur quelle machine, avec quel résultat (hors Git).
JOURNAL = os.path.join(INV, "journal-actions.jsonl")
_JOURNAL_VERROU = threading.Lock()
# Pas dont le résultat résume l'opération dans le journal.
RESUME_OP = {"audit": ["classement", "ci1"], "decider": ["signature", "test_metier"], "basculer": ["test"],
             "acces": ["essai"], "integrer": ["classement"], "remettre": ["retour"], "preparer": []}


def tracer(action, cible, detail="", resultat="ok"):
    with _JOURNAL_VERROU:
        with open(JOURNAL, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"date": time.time(), "par": ETAT.par, "action": action, "cible": cible,
                                 "detail": detail, "resultat": resultat}, ensure_ascii=False) + "\n")


def lire_journal(n=300):
    try:
        lignes = open(JOURNAL, encoding="utf-8").read().splitlines()[-n:]
    except OSError:
        return []
    out = []
    for l in reversed(lignes):
        try:
            out.append(json.loads(l))
        except ValueError:
            pass
    return out


# Bandeau d'erreur de la console : titre lisible et, s'il y a lieu, vue où voir le détail ([vue, libellé du lien]).
ERREURS = {
    "decider": ("Preuve de reconstruction refusée", ["ci", "Voir la preuve"]),
    "audit": ("Audit interrompu", None),
    "basculer": ("Bascule interrompue", ["bascule", "Voir la bascule"]),
    "preparer": ("Préparation incomplète", ["labo", "Voir le laboratoire"]),
    "remettre": ("Remise en état incomplète", ["labo", "Voir le laboratoire"]),
}


def executer(nom, corps):
    ETAT.op = None
    cible = corps.get("vm") if nom in AVEC_CORPS else ("laboratoire" if nom == "preparer" else VM)
    try:
        if nom == "decider":
            ACTIONS[nom](corps.get("choix", {}))
        elif nom in AVEC_CORPS:
            ACTIONS[nom](corps)
        else:
            ACTIONS[nom]()
        if ETAT.op:
            res = [p["resultat"] for p in ETAT.op.d["pas"] if p["cle"] in RESUME_OP.get(nom, []) and p["resultat"]]
            tracer(ETAT.op.d["titre"], cible, " · ".join(res), "ok")
    except Exception as exc:  # affiché dans l'opération et en bandeau, détail dans le terminal
        traceback.print_exc()
        titre, vers = ERREURS.get(nom, (None, None))
        details, cles = getattr(exc, "problemes", None), getattr(exc, "cles", None)
        if isinstance(exc, DecisionsRefusees):  # refus avant la CI : rien n'a été envoyé
            titre, vers = "Décisions non envoyées : rien n'est parti à la CI", ["decisions", "Corriger les décisions"]
        ETAT.maj(erreur=str(exc), erreur_titre=titre or (ETAT.op.d["titre"] if ETAT.op else "Opération en échec"),
                 erreur_vers=vers, erreur_details=details, erreur_cles=cles)
        if ETAT.op and ETAT.op.d["etat"] == "en_cours":
            ETAT.op.terminer("ko", str(exc))
        if nom == "preparer":
            ETAT.maj(preparation={"etat": "ko", "date": None})
        tracer(ETAT.op.d["titre"] if ETAT.op else nom, cible, str(exc), "ko")
    finally:
        ETAT.occupe = False
        ETAT.publier()


def tracer_registre(nom, corps, avant, apres):
    """Une ligne de journal par changement du registre, avec ce qui a changé."""
    vm = corps.get("vm", "")
    if nom == "parc/ajouter":
        m = next((x for x in apres["machines"] if x["vm"] == str(vm).strip().lower()), {})
        tracer("Machine déclarée", m.get("vm", vm), f"{m.get('ip')} · {m.get('role')} · {m.get('criticite')}")
    elif nom == "parc/retirer":
        tracer("Machine retirée du parc", vm)
    elif nom == "parc/modifier":
        a = next((x for x in avant["machines"] if x["vm"] == vm), {})
        b = next((x for x in apres["machines"] if x["vm"] == vm), {})
        champs = {"role": "rôle", "criticite": "criticité", "ip": "adresse"}
        diff = [f"{lib} : {a.get(k)} → {b.get(k)}" for k, lib in champs.items() if a.get(k) != b.get(k)]
        if diff:
            tracer("Machine modifiée", vm, " · ".join(diff))
    else:
        noms = {"organisation": "organisation", "description": "description", "perimetre": "périmètre",
                "reference": "image de référence", "adresses_connues": "adresses connues"}
        diff = [lib for k, lib in noms.items() if avant.get(k) != apres.get(k)]
        if diff:
            tracer("Paramètres modifiés", "plateforme", ", ".join(diff))


class Page(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def envoyer(self, code, corps, type_="application/json; charset=utf-8"):
        b = corps.encode() if isinstance(corps, str) else corps
        try:
            self.send_response(code)
            self.send_header("Content-Type", type_)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError):
            # La page a été rechargée ou fermée avant la réponse (première lecture de la forge, lente) : sans effet.
            self.close_connection = True

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.envoyer(200, open(os.path.join(ICI, "index.html"), "rb").read(), "text/html; charset=utf-8")
        elif self.path == "/etat":
            self.envoyer(200, ETAT.instantane()[1])
        elif self.path.split("?")[0] == "/parc":
            try:
                self.envoyer(200, json.dumps(parc("force" in self.path), ensure_ascii=False, default=str))
            except Exception as exc:  # forge, fichiers : affiché tel quel, rien d'inventé
                traceback.print_exc()
                self.envoyer(500, json.dumps({"erreur": str(exc)}, ensure_ascii=False))
        elif self.path == "/installer/" + INSTALLATEUR:
            self.send_response(200)
            corps = installateur()["script"].encode()
            self.send_header("Content-Type", "text/x-shellscript; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{INSTALLATEUR}"')
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)
        elif self.path.split("?")[0] == "/journal":
            self.envoyer(200, json.dumps(lire_journal(), ensure_ascii=False))
        elif self.path.split("?")[0] == "/joignabilite":
            self.envoyer(200, json.dumps(joignabilite(), ensure_ascii=False))
        elif self.path.split("?")[0] == "/rapport":
            # Rapport de reprise imprimable (A4), rendu dans la page à partir de /parc.
            self.envoyer(200, open(os.path.join(ICI, "rapport.html"), "rb").read(), "text/html; charset=utf-8")
        elif self.path.split("?")[0] == "/rapport-court":
            try:
                parc("force" in self.path)
                self.envoyer(200, open(RAPPORT_CONSOLE, "rb").read(), "text/html; charset=utf-8")
            except Exception as exc:
                traceback.print_exc()
                self.envoyer(500, f"<p>Rapport indisponible : {exc}</p>", "text/html; charset=utf-8")
        elif self.path == "/flux":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            vu = -1
            try:
                while True:
                    with ETAT.verrou:
                        if ETAT.version == vu:
                            ETAT.verrou.wait(timeout=1)
                    v, s = ETAT.instantane()
                    if v != vu:
                        self.wfile.write(f"data: {s}\n\n".encode())
                        vu = v
                    else:
                        self.wfile.write(b": battement\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
        else:
            self.envoyer(404, '{"erreur": "inconnu"}')

    def do_POST(self):
        nom = self.path.strip("/").removeprefix("action/")
        n = int(self.headers.get("Content-Length") or 0)
        corps = json.loads(self.rfile.read(n) or b"{}")
        if nom in ("parc/ajouter", "parc/retirer", "parc/reglages", "parc/modifier"):
            avant = lire_parc()
            try:
                res = {"parc/ajouter": ajouter_machine, "parc/retirer": retirer_machine, "parc/reglages": regler,
                       "parc/modifier": modifier_machine}[nom](corps)
            except ValueError as exc:
                return self.envoyer(400, json.dumps({"erreur": str(exc)}, ensure_ascii=False))
            tracer_registre(nom, corps, avant, lire_parc())
            return self.envoyer(200, json.dumps(res or {}, ensure_ascii=False))
        if nom in ("labo/reinitialiser", "labo/reafficher"):
            if ETAT.occupe:
                return self.envoyer(409, '{"erreur": "une opération tourne"}')
            try:
                res = (reinitialiser_donnees if nom == "labo/reinitialiser" else reafficher_historique)()
            except OSError as exc:
                traceback.print_exc()
                return self.envoyer(500, json.dumps({"erreur": str(exc)}, ensure_ascii=False))
            return self.envoyer(200, json.dumps(res, ensure_ascii=False))
        if nom == "reinitialiser":
            if ETAT.occupe:
                return self.envoyer(409, '{"erreur": "une opération tourne"}')
            ETAT.reinitialiser()
            return self.envoyer(200, "{}")
        if nom not in ACTIONS:
            return self.envoyer(404, '{"erreur": "action inconnue"}')
        if ETAT.occupe:
            return self.envoyer(409, '{"erreur": "une opération tourne déjà"}')
        ETAT.occupe = True
        ETAT.maj(erreur=None, erreur_titre=None, erreur_vers=None, erreur_details=None, erreur_cles=None)
        threading.Thread(target=executer, args=(nom, corps), daemon=True).start()
        self.envoyer(202, "{}")


def main():
    global ETAT
    ap = argparse.ArgumentParser(description="Console Black Start de la démo.")
    ap.add_argument("--par", required=True, help="nom de la personne qui décide pendant la démo")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--oublier", action="store_true",
                    help="repartir d'un parcours vide au lieu de relire inventaires/etat-console.json")
    args = ap.parse_args()
    ETAT = Etat(args.par, relire=not args.oublier)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Page)
    srv.daemon_threads = True
    print(f"console Black Start : http://localhost:{args.port}  (Ctrl+C pour arrêter)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
