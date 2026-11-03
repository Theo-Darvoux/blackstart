#!/usr/bin/env python3
"""Client minimal de l'API Forgejo du labo (bibliothèque standard).

Lit infra/secrets/forge.env. Au premier appel, crée un jeton d'API pour le
compte admin (authentification par mot de passe) et l'ajoute au fichier.
Le jeton et le mot de passe ne sont jamais affichés.
"""

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
ENV = os.path.join(HERE, "secrets", "forge.env")


def load_env():
    env = {}
    for line in open(ENV, encoding="utf-8"):
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            env[k] = v
    return env


class Forge:
    def __init__(self):
        self.env = load_env()
        self.base = f"http://{self.env.get('FORGE_IP', '192.168.103.203')}:3000/api/v1"
        self.user = self.env["FORGE_ADMIN"]
        if "FORGE_TOKEN" not in self.env:
            self._create_token()

    def _create_token(self):
        basic = base64.b64encode(f"{self.user}:{self.env['FORGE_ADMIN_PASSWORD']}".encode()).decode()
        body = {"name": "claude-code", "scopes": ["all"]}
        req = urllib.request.Request(f"{self.base}/users/{self.user}/tokens", data=json.dumps(body).encode(),
                                     method="POST", headers={"Authorization": f"Basic {basic}",
                                                             "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            token = json.loads(resp.read())["sha1"]
        with open(ENV, "a", encoding="utf-8") as fh:
            fh.write(f"FORGE_TOKEN={token}\n")
        self.env["FORGE_TOKEN"] = token

    def call(self, method, path, body=None, ok=(200, 201, 204)):
        # Les lectures sont rejouables : on réessaie si le réseau (VPN) coupe la connexion.
        for essai in range(4 if method == "GET" else 1):
            try:
                return self._call(method, path, body, ok)
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                if essai == 3 or method != "GET":
                    raise
                time.sleep(2 * (essai + 1))

    def _call(self, method, path, body, ok):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"token {self.env['FORGE_TOKEN']}",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            if exc.code in ok:
                return None
            raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {exc.read().decode(errors='replace')[:300]}") from None

    def git_url(self, repo):
        """URL HTTP du dépôt avec le jeton (pour git, jamais affichée)."""
        host = self.base.split("//")[1].split("/")[0]
        return f"http://{self.user}:{self.env['FORGE_TOKEN']}@{host}/{repo}.git"


if __name__ == "__main__":
    f = Forge()
    print(json.dumps(f.call("GET", sys.argv[1] if len(sys.argv) > 1 else "/version"), indent=2, ensure_ascii=False))
