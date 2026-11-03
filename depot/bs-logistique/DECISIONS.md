# Décisions humaines pour bs-logistique

Ces éléments ne sont pas reproduits automatiquement. Tant qu'ils ne sont pas tranchés, la comparaison bloque la merge request.

## En attente de décision

| Élément | Pourquoi |
| --- | --- |
| `file:/etc/sudoers.d/prestataire` | droit sudo ajouté hors paquet : à valider avant de le reproduire |
| `file:/opt/etiquettes/bin/zpl-print` | binaire hors paquet : origine, licence et rôle à confirmer par un humain |
| `listen:tcp:0.0.0.0:9100` | port ouvert par un processus hors service systemd (lancé à la main ?) |
| `process:/usr/bin/python3.13@root@session.scope` | processus lancé depuis une session interactive : disparaît au redémarrage |
| `sysctl:vm.swappiness` | valeur modifiée à chaud, absente des fichiers sysctl : perdue au prochain redémarrage |

## Adresses IP écrites en dur

| Fichier | Ligne | IP |
| --- | --- | --- |
| `/etc/hosts` | 8 | 192.168.103.202 |
| `/etc/logistique/logistique.conf` | 5 | 192.168.103.201 |
| `/etc/restic/logistique.env` | 1 | 192.168.103.203 |

## Trous de la sauvegarde d'origine (comblés par la restauration)

- `data:/root/.ssh` : la clé d'accès au dépôt restic n'existe que sur la VM, hors sauvegarde : reprise depuis le coffre
- `data:/var/lib/postgresql` : pg_dump ne contient pas les rôles PostgreSQL : recréés depuis la chaîne de connexion

## Volontairement non copiés

- `/etc/group` : base des comptes : produite par les tâches de comptes
- `/etc/gshadow` : base des comptes : produite par les tâches de comptes
- `/etc/passwd` : base des comptes : produite par les tâches de comptes
- `/etc/shadow` : base des comptes : produite par les tâches de comptes
- `/etc/subgid` : base des comptes : produite par les tâches de comptes
- `/etc/subuid` : base des comptes : produite par les tâches de comptes
