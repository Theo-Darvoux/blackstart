#!/usr/bin/env python3
"""Client minimal de l'API Proxmox pour Black Start (bibliothèque standard).

Lit infra/secrets/proxmox.env (jeton limité au pool « blackstart ») et vérifie
le certificat de luna avec infra/secrets/pve-root-ca.pem. Le secret du jeton
n'est jamais affiché.

    infra/pve.py get /version
    infra/pve.py get /pools/blackstart
"""

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
SECRETS = os.environ.get("BS_SECRETS", os.path.join(HERE, "secrets"))


def load_env(path=os.path.join(SECRETS, "proxmox.env")):
    env = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env


class PVE:
    def __init__(self):
        self.env = load_env()
        self.base = self.env["PVE_URL"].rstrip("/") + "/api2/json"
        self.node = self.env["PVE_NODE"]
        self.tls = ssl.create_default_context(cafile=os.path.join(SECRETS, "pve-root-ca.pem"))
        # La CA générée par Proxmox en 2022 n'a pas d'extension keyUsage, ce que
        # Python >= 3.13 refuse en mode strict. Chaîne et nom d'hôte restent vérifiés.
        self.tls.verify_flags &= ~ssl.VERIFY_X509_STRICT
        self.auth = f"PVEAPIToken={self.env['PVE_TOKEN_ID']}={self.env['PVE_TOKEN_SECRET']}"

    def call(self, method, path, params=None, timeout=60):
        url = self.base + path
        data = None
        if params and method == "GET":
            url += "?" + urllib.parse.urlencode(params)
        elif params:
            data = urllib.parse.urlencode(params, doseq=True).encode()
        req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": self.auth})
        try:
            with urllib.request.urlopen(req, context=self.tls, timeout=timeout) as resp:
                return json.loads(resp.read().decode()).get("data")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"{method} {path} -> HTTP {exc.code} {exc.reason}: {body[:300]}") from None

    def get(self, path, **params):
        # Lecture seule, donc rejouable : on réessaie si le réseau (VPN) coupe la connexion.
        for essai in range(4):
            try:
                return self.call("GET", path, params)
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                if essai == 3:
                    raise
                time.sleep(2 * (essai + 1))

    def post(self, path, **params):
        return self.call("POST", path, params)

    def put(self, path, **params):
        return self.call("PUT", path, params)

    def delete(self, path, **params):
        return self.call("DELETE", path + ("?" + urllib.parse.urlencode(params) if params else ""))

    def wait_task(self, upid, timeout=600):
        """Attend la fin d'une tâche Proxmox (clone, démarrage…)."""
        path = f"/nodes/{self.node}/tasks/{urllib.parse.quote(upid, safe='')}/status"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            st = self.get(path)
            if st.get("status") == "stopped":
                if st.get("exitstatus") != "OK":
                    raise RuntimeError(f"tâche {upid} : {st.get('exitstatus')}")
                return st
            time.sleep(2)
        raise TimeoutError(f"tâche {upid} toujours en cours après {timeout} s")


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("get",):
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    print(json.dumps(PVE().get(sys.argv[2]), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
