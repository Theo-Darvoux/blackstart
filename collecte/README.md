# Collecte

`bs-collect` inventorie une VM Debian en lecture seule et écrit un inventaire JSON sur la sortie standard. C'est un script fixe, sans IA. Il n'utilise que la bibliothèque standard de Python 3, présent sur Debian 13.

## Ce qui est relevé

| Section | Contenu |
|---|---|
| `packages` | Paquets installés, paquets demandés explicitement (`apt-mark showmanual`), paquets bloqués, choix `update-alternatives` |
| `modified_files` | Fichiers de paquets modifiés (`dpkg --verify`), avec hash et IP codées en dur |
| `unowned` | Fichiers hors paquet sous `/etc`, `/opt`, `/usr/local`, `/usr/bin`, `/usr/sbin`, `/usr/lib/systemd` ; bruit connu mis à part dans `ignored`, avec sa règle |
| `data` | Dossiers de données (`/var/lib`, `/srv`, `/home`…) : taille et nombre de fichiers, pas le contenu |
| `users` | Comptes et groupes (jamais `/etc/shadow`) |
| `network`, `listening` | Adresses, routes, sockets en écoute avec leur processus |
| `processes` | Processus, exécutable, paquet propriétaire, unité systemd |
| `systemd` | Unités, fichiers d'unité et leur état, timers, unités en échec |
| `cron` | `/etc/crontab`, `/etc/cron.*`, crontabs des utilisateurs, nombre de tâches `at` |
| `kernel` | Modules chargés, sysctl configurés et valeurs effectives d'une liste surveillée |
| `mounts`, `firewall`, `containers` | Montages réels, règles nftables/iptables, conteneurs Docker/Podman |
| `limits` | Ce que le script ne peut pas voir par construction |
| `unreadable` | Ce que le script n'a pas pu lire pendant cette exécution |

Chaque ligne de texte d'un fichier collecté est aussi scannée à la recherche d'adresses IPv4 (`ip_literals`), en signalant celles qui sont l'adresse de la VM elle-même.

## Secrets

- Par défaut, l'inventaire ne contient que des métadonnées et des hash, pas le contenu des fichiers.
- `--with-content` embarque le texte des petits fichiers (64 Kio max) modifiés ou hors paquet. L'inventaire devient alors sensible : il passe par le masquage avant tout envoi au modèle, et ne va jamais dans Git (`inventaires/` est ignoré).
- Même avec `--with-content`, ces contenus ne sont jamais embarqués (`content_withheld`, seul le hash reste) : `/etc/shadow`, `/etc/gshadow`, tout fichier non lisible par tous (par exemple `/etc/sssd/sssd.conf`), les clés SSH d'hôte, les fichiers `.key` et tout fichier contenant `PRIVATE KEY`.
- Les lignes de commande des processus et les crontabs sont copiées telles quelles et peuvent contenir un mot de passe.

## Installer sur une VM de démo

Les VM sont sur `luna.minet.lan`. Ces commandes sont à lancer depuis votre poste, pas par Claude Code. Les noms des VM ne sont pas résolus par DNS : remplacer `VM` par l'IP de la VM (`192.168.103.200` pour `bs-logistique`, voir `CLAUDE.md`).

La connexion root est fermée : on passe par le compte `psders` et `sudo`. `-t` permet à `sudo` de demander le mot de passe.

```sh
scp collecte/bs-collect collecte/install-on-vm.sh psders@VM:
ssh -t psders@VM "sudo install -o root -g root -m 0755 bs-collect /usr/local/sbin/bs-collect \
  && sudo bash install-on-vm.sh '$(cat ~/.ssh/id_ed25519.pub)' \
  && rm bs-collect install-on-vm.sh"
```

Le script crée le compte `bs-collect`. Par SSH, ce compte ne peut lancer que la collecte (commande forcée dans `authorized_keys`). Par `sudo`, il ne peut lancer que `bs-collect` (fichier `/etc/sudoers.d/bs-collect`).

## Collecter

`-T` évite le message `PTY allocation request failed` (le compte n'a pas droit au terminal). `IdentitiesOnly` évite `Too many authentication failures` quand l'agent SSH a plusieurs clés.

```sh
mkdir -p inventaires
ssh -T -i ~/.ssh/id_blackstart -o IdentitiesOnly=yes bs-collect@VM > inventaires/VM.json
ssh -T -i ~/.ssh/id_blackstart -o IdentitiesOnly=yes bs-collect@VM bs-collect --with-content > inventaires/VM.content.json
```

## Mettre à jour le collecteur sur une VM

```sh
scp collecte/bs-collect psders@VM:
ssh -t psders@VM "sudo install -o root -g root -m 0755 bs-collect /usr/local/sbin/bs-collect && rm bs-collect"
```

## Tester sans VM

```sh
collecte/tests/docker-smoke.sh
```

Le test monte un conteneur Debian 13 jetable avec les cinq pièges du banc : cron oublié, configuration modifiée, binaire dans `/opt`, sauvegarde mensuelle et IP codée en dur. Il y ajoute une fausse clé privée. Il vérifie que chaque piège est détecté et que la clé n'apparaît pas dans l'inventaire. Le conteneur n'a pas systemd : la section `systemd` doit être signalée dans `unreadable`. Elle n'est testée que sur une vraie VM.

## Comparer deux inventaires

```sh
collecte/bs-compare A.json B.json [--identity] [--justify regles.json] [--json rapport.json] [--show-justified]
```

`bs-compare` ramène chaque inventaire à des clés (`pkg:nginx`, `file:/etc/hosts`, `listen:tcp:0.0.0.0:80`, `cron:/var/spool/cron/crontabs/root`…). Il ignore les champs volatils : date de collecte, PID, horaires des timers, processus de la collecte elle-même. Chaque écart est classé `absent-de-B`, `ajouté-dans-B` ou `différent`.

- Un écart est **justifié** si une règle d'un fichier de `regles/` correspond à sa clé. La raison est reprise dans le rapport.
- `regles/volatil.json` est toujours chargé : sessions utilisateur, copies automatiques de `/var/backups`…
- `regles/identite.json` est chargé avec `--identity`, quand A et B sont deux machines distinctes : IP, hostname, clés d'hôte.
- Le code de sortie est **1 s'il reste un écart non justifié** : la CI doit alors bloquer la merge request.
- Les `REMARQUE` (nombre de fichiers d'un dossier de données, nombre de processus identiques) sont affichées sans être bloquantes.

Deux usages :

```sh
# Vérifier une reconstruction : tout écart non justifié bloque.
collecte/bs-compare --identity inventaires/bs-logistique.json inventaires/sbx-logistique.json

# Voir ce que l'admin a ajouté depuis le template : les lignes « ajouté-dans-B » et « différent ».
collecte/bs-compare --identity inventaires/bs-mail-vierge.json inventaires/bs-logistique.json
```

## Suite prévue

- Classer chaque élément ajouté depuis le template (compris, donnée, secret, ignoré, inconnu).
