# PME fictive (mise en scène de la démo)

Ces scripts installent la PME fictive sur les VM de luna. Ils jouent le rôle de l'admin qui a tout configuré à la main il y a des années.

**L'outil Black Start ne doit jamais lire ce dossier ni `banc/pieges.json`.** Ce sont les réponses du banc de mesure.

## Architecture

| VM | IP | Services |
|---|---|---|
| `bs-logistique` | 192.168.103.200 | Logiciel de logistique : Flask et Gunicorn sur le port 8000, PostgreSQL, sauvegarde restic quotidienne à 2h30 |
| `bs-mail` | 192.168.103.201 | Postfix (SMTP 25) et Dovecot (IMAPS 993), domaine `pme.test`, aucun envoi vers l'extérieur |
| `bs-proxy` | 192.168.103.202 | Nginx (`logistique.pme.test` vers `.200:8000`) et Unbound (zone `pme.test`) |
| `bs-gitlab` | 192.168.103.203 | Dans le labo, sert aussi de serveur de sauvegarde : compte SFTP `sauvegarde`, dépôt restic `/srv/sauvegardes/logistique` |

Parcours d'une commande : le client passe par le proxy, puis l'app, qui écrit en base. L'app envoie ensuite un mail SMTP à `commandes@pme.test`, lisible en IMAP.

## Installer

```sh
pme/deploy.sh mail
pme/deploy.sh proxy
pme/deploy.sh sauvegarde
pme/deploy.sh logistique
pme/deploy.sh pieges
```

Chaque script est idempotent. `deploy.sh` passe par le compte `claude` (clé `~/.ssh/id_blackstart_admin`) et n'envoie à chaque VM que les secrets dont elle a besoin.

## Secrets

`pme/secrets/` est généré par `gen-secrets.sh` et ignoré par Git. Il joue le rôle du coffre de la PME : mots de passe PostgreSQL, IMAP et restic, plus la clé SFTP de sauvegarde. Il ne faut pas le régénérer, sinon les sauvegardes restic existantes deviennent illisibles.

À montrer au jury : le mot de passe restic n'existe que sur `bs-logistique` et dans ce coffre. Si la VM est détruite et qu'il n'y a pas de coffre, la sauvegarde devient inutilisable.

## Pièges (`pieges/setup.sh`, corrigé dans `banc/pieges.json`)

Tous sont posés sur `bs-logistique` :

| ID | Piège | Spec |
|---|---|---|
| P1 | Cron oublié dans la crontab de root (`export-edi` toutes les 10 min) | oui |
| P2 | `/etc/security/limits.conf` modifié (fichier de paquet) | oui |
| P3 | Binaire opaque `/opt/etiquettes/bin/zpl-print` | oui |
| P4 | Archivage mensuel `/etc/cron.d/archive-mensuelle` vers `/srv/archives` : hors restic, et il purge la base | oui |
| P5 | IP du serveur mail en dur dans `/etc/logistique/logistique.conf` | oui |
| P6 | `vm.swappiness=10` réglé à chaud, non persisté | non |
| P7 | Timer annuel `inventaire-annuel.timer` (31 décembre) | non |
| P8 | Relais HTTP sur le port 9100 lancé à la main (disparaît au redémarrage) | non |
| P9 | Compte `prestataire` avec une clé SSH et un droit sudo | non |
| P10 | `edi.transporteur.test` ajouté dans `/etc/hosts` | non |

## Tests

```sh
banc/test-metier.py                     # test métier de bout en bout, chronométré
banc/mesure.py inventaires/bs-logistique-vierge.json inventaires/bs-logistique-pieges.json
```
