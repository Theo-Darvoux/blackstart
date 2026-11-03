#!/usr/bin/env python3
"""Test métier de bout en bout de la PME fictive, chronométré.

1. Le DNS interne résout logistique.<domaine> vers le proxy.
2. Le logiciel répond via le proxy et sa base est joignable.
3. Une commande de test est créée via le proxy.
4. La commande est relue et a le statut « confirmée » (mail parti).
5. Le mail de confirmation est arrivé dans la boîte IMAP « commandes ».
6. Avec --nettoyer claude@IP : la commande de test est supprimée et son stock
   rendu (une seule requête SQL par SSH, par référence exacte), pour ne pas
   laisser de fausse commande en production ni dans la copie qui y bascule.

Les IP viennent de pme/pme.env et peuvent être surchargées (sandbox).
Le mot de passe IMAP vient de pme/secrets/secrets.env.

Usage :
    banc/test-metier.py [--proxy IP] [--mail IP] [--dns IP] [--json resultat.json] [--nettoyer claude@IP]
"""

import argparse
import imaplib
import json
import os
import random
import re
import socket
import ssl
import struct
import subprocess
import sys
import time
import urllib.request
import uuid

HERE = os.path.dirname(os.path.realpath(__file__))
PME = os.path.join(HERE, "..", "pme")


def read_env(path):
    env = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k] = v.strip().strip('"')
    except FileNotFoundError:
        pass
    return env


def dns_a(server, name, timeout=3):
    """Requête DNS A minimale (UDP), sans dépendance."""
    tid = random.randint(0, 0xFFFF)
    qname = b"".join(bytes([len(p)]) + p.encode() for p in name.rstrip(".").split(".")) + b"\0"
    query = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0) + qname + struct.pack(">HH", 1, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        s.sendto(query, (server, 53))
        data, _ = s.recvfrom(4096)
    ancount = struct.unpack(">H", data[6:8])[0]
    pos, ips = len(query), []
    for _ in range(ancount):
        while True:  # nom : pointeur (2 octets) ou suite de labels
            if data[pos] >= 0xC0:
                pos += 2
                break
            if data[pos] == 0:
                pos += 1
                break
            pos += data[pos] + 1
        rtype, _, _, rdlen = struct.unpack(">HHIH", data[pos:pos + 10])
        pos += 10
        if rtype == 1 and rdlen == 4:
            ips.append(socket.inet_ntoa(data[pos:pos + 4]))
        pos += rdlen
    return ips


def http(method, url, host, body=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Host": host, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode())


def main():
    env = read_env(os.path.join(PME, "pme.env"))
    secrets = read_env(os.path.join(PME, "secrets", "secrets.env"))
    ap = argparse.ArgumentParser(description="Test métier de bout en bout.")
    ap.add_argument("--proxy", default=env.get("PROXY_IP"))
    ap.add_argument("--mail", default=env.get("MAIL_IP"))
    ap.add_argument("--dns", default=env.get("PROXY_IP"), help="serveur DNS interne (Unbound)")
    ap.add_argument("--domain", default=env.get("DOMAIN", "pme.test"))
    ap.add_argument("--mail-timeout", type=int, default=30)
    ap.add_argument("--app", help="appeler l'app directement (ex. 192.168.103.210:8000), sans proxy ni DNS")
    ap.add_argument("--isole", action="store_true",
                    help="VM en sandbox : le mail ne peut pas partir, le statut attendu est « mail en échec »")
    ap.add_argument("--json", help="écrire le résultat dans ce fichier")
    ap.add_argument("--nettoyer", metavar="COMPTE@IP",
                    help="supprimer ensuite la commande de test sur la VM du logiciel (SSH + psql)")
    args = ap.parse_args()

    host = f"logistique.{args.domain}"
    base = f"http://{args.app or args.proxy}"
    ref = f"BST-{uuid.uuid4().hex[:8].upper()}"
    steps, ctx = [], {}
    t0 = time.monotonic()

    def step(name, fn):
        t = time.monotonic()
        try:
            detail = fn()
            ok = True
        except Exception as exc:  # le rapport doit dire quelle étape casse et pourquoi
            detail, ok = f"{type(exc).__name__}: {exc}", False
        steps.append({"etape": name, "ok": ok, "duree_s": round(time.monotonic() - t, 2), "detail": detail})
        print(f"  {'OK   ' if ok else 'ÉCHEC'} {name} ({steps[-1]['duree_s']} s) : {detail}")
        return ok

    def s_dns():
        ips = dns_a(args.dns, host)
        if args.proxy not in ips:
            raise AssertionError(f"{host} -> {ips}, attendu {args.proxy}")
        return f"{host} -> {', '.join(ips)}"

    def s_health():
        status, body = http("GET", f"{base}/health", host)
        if body.get("base") != "ok":
            raise AssertionError(body)
        return f"HTTP {status}, {body['commandes']} commandes en base"

    def s_create():
        status, body = http("POST", f"{base}/api/commandes", host,
                            {"client": "Test Black Start", "sku": "CART-60", "quantite": 1, "ref": ref},
                            timeout=25 if args.isole else 10)  # sans SMTP, l'app attend 10 s le mail
        ctx["id"] = body["id"]
        return f"HTTP {status}, commande n° {body['id']} ({ref}), statut {body['statut']}"

    def s_read():
        _, body = http("GET", f"{base}/api/commandes/{ctx['id']}", host)
        if args.isole:
            if body["statut"] != "mail en échec":
                raise AssertionError(f"statut {body['statut']} : un mail serait-il sorti de la sandbox ?")
            return f"statut {body['statut']} (attendu : la sandbox bloque SMTP)"
        if body["statut"] != "confirmée":
            raise AssertionError(f"statut {body['statut']}")
        return f"statut {body['statut']}"

    def s_mail():
        if "IMAP_PASSWORD" not in secrets:
            raise AssertionError("IMAP_PASSWORD absent de pme/secrets/secrets.env")
        tls = ssl.create_default_context()
        tls.check_hostname = False
        tls.verify_mode = ssl.CERT_NONE  # certificat auto-signé du labo
        deadline = time.monotonic() + args.mail_timeout
        with imaplib.IMAP4_SSL(args.mail, 993, ssl_context=tls, timeout=10) as imap:
            imap.login("commandes", secrets["IMAP_PASSWORD"])
            while True:
                imap.select("INBOX", readonly=True)
                _, data = imap.search(None, "SUBJECT", f'"{ref}"')
                if data[0].split():
                    return f"mail « Commande {ref} confirmée » reçu"
                if time.monotonic() > deadline:
                    raise AssertionError(f"aucun mail pour {ref} après {args.mail_timeout} s")
                time.sleep(1)

    def s_clean():
        if not re.fullmatch(r"BST-[0-9A-F]{8}", ref):
            raise AssertionError(f"référence inattendue {ref}")
        sql = ("WITH c AS (DELETE FROM commandes WHERE ref = '%s' AND client = 'Test Black Start' "
               "RETURNING sku, quantite), s AS (UPDATE produits p SET stock = p.stock + c.quantite FROM c "
               "WHERE p.sku = c.sku RETURNING 1) SELECT (SELECT count(*) FROM c), (SELECT count(*) FROM s)") % ref
        key = os.path.expanduser(os.environ.get("BS_ADMIN_KEY", "~/.ssh/id_blackstart_admin"))
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=5",
                            "-o", "StrictHostKeyChecking=accept-new", "-i", key, args.nettoyer,
                            f'sudo -u postgres psql -d logistique -qAt -v ON_ERROR_STOP=1 -c "{sql}"'],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0 or r.stdout.strip() != "1|1":
            raise AssertionError(f"code {r.returncode}, sortie {r.stdout.strip()!r} {r.stderr.strip()[-200:]}")
        return f"commande {ref} supprimée, stock rendu"

    steps_list = [("DNS interne", s_dns), ("Logiciel et base", s_health), ("Création de commande", s_create),
                  ("Relecture de la commande", s_read), ("Mail de confirmation", s_mail)]
    if args.app:
        steps_list = [s for s in steps_list if s[0] != "DNS interne"]
    if args.isole:
        steps_list = [s for s in steps_list if s[0] != "Mail de confirmation"]
    print(f"Test métier : {'app ' + args.app if args.app else 'proxy ' + args.proxy}"
          f"{' (sandbox isolée)' if args.isole else ''}, mail {args.mail}, DNS {args.dns}")
    all_ok = True
    for name, fn in steps_list:
        if not step(name, fn):
            all_ok = False
            if name in ("Logiciel et base", "Création de commande"):
                break  # les étapes suivantes dépendent de celle-ci
    if args.nettoyer and "id" in ctx:  # même si une étape après la création a échoué
        all_ok = step("Nettoyage de la commande de test", s_clean) and all_ok
    total = round(time.monotonic() - t0, 2)
    print(("TOUT VERT" if all_ok else "ÉCHEC") + f" en {total} s")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"ok": all_ok, "duree_s": total, "ref": ref, "etapes": steps}, fh, indent=2, ensure_ascii=False)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
