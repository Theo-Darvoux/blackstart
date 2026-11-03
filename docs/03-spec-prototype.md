# Spécification du prototype

Les choix marqués « proposé » n'ont pas été validés par l'équipe et peuvent changer.

## Objectif de la démo

Sur la mini-infrastructure d'une PME fictive :

1. On détruit ou on chiffre la VM du logiciel de logistique.
2. On la reconstruit proprement depuis Git.
3. On restaure les données depuis le backup.
4. On passe une commande de test de bout en bout.
5. Les tests passent au vert et le chrono s'affiche.

Si la démo ne passe pas de bout en bout mercredi à 18h, réduire à une seule VM fiable. Une vidéo de secours est obligatoire, et la démo doit pouvoir tourner sans le réseau de la salle.

## Périmètre

**Inclus :** trois VM Linux (mail SMTP/IMAP, reverse proxy + DNS, logiciel de logistique), sandbox isolée, collecte, masquage des secrets, classement, génération Ansible et CI/CD, tests de comparaison, interface de rapport, mesures sur banc de pièges.

**Exclu :** Windows et Active Directory, automatisation de la configuration réseau, passage en production réelle, comparaison poussée des modèles.

Briques proposées : Debian, Proxmox si disponible, Postfix + Dovecot, Nginx + Unbound ou BIND, Odoo Community ou une petite application maison pour la logistique, Ansible, GitLab CI, restic ou un dump de base pour le backup. Pour le modèle, Qwen léger via Ollama ou llama.cpp : garder le premier qui tient la démo sur la machine disponible.

## Architecture

```text
VM source ──lecture seule──> collecte (script fixe) ──> inventaire JSON
                                                          │
                                         masquage des secrets
                                                          │
                                  classement + modèle local
                                                          │
                     validation de l'usage par l'admin (interface)
                                                          │
                     Ansible + CI/CD dans une branche GitLab
                                                          │
         sandbox isolée : VM vierge + code + données du backup
                                                          │
                collecte + tests sur l'originale et la copie
                                                          │
                 rapport d'écarts + merge request + score
```

La sandbox doit être isolée, pour qu'un clone n'envoie pas de vrais mails ni n'écrive dans une vraie base.

## Collecte

Le script est déterministe, sans IA. Le compte SSH est en lecture seule, avec les commandes root limitées par `sudoers`.

**À froid, si le temps le permet :** snapshot de la VM et montage en lecture seule avec libguestfs. **Ne pas s'y bloquer :** commencer par SSH.

**État du disque :**
- `apt-mark showmanual` : paquets demandés explicitement ;
- `debsums` ou `dpkg --verify` : fichiers modifiés par rapport aux paquets ;
- fichiers n'appartenant à aucun paquet, hors bruit connu (caches, logs).

**État en fonctionnement :** processus, `ss -tulpn`, montages, pare-feu, `sysctl`, modules, conteneurs, services systemd, crontabs et timers. osquery peut en fournir une partie.

**Observation longue, hors démo si le temps manque :** connexions et tâches via auditd ou eBPF. À présenter dans la roadmap.

Le rapport doit afficher ce que le script n'a pas pu lire.

## Classement

Chaque élément reçoit un statut. L'IA peut proposer un statut, mais les preuves restent déterministes.

| Statut | Exemple | Traitement |
|---|---|---|
| Compris | Configuration Nginx modifiée | Intégré à Ansible |
| Donnée | `/var/lib/mysql` | Sauvegarde et restauration |
| Secret | Clé privée TLS | Coffre, jamais envoyé au modèle |
| Ignoré | Logs, cache | Exclu, règle documentée |
| Inconnu | Binaire dans `/opt` | Décision humaine obligatoire |

## Vérification

Relancer **la même collecte** sur la copie, puis comparer les inventaires et les comportements : ports, réponses HTTP, requêtes SQL, DNS, envoi et réception de mail, tâches planifiées. Tout écart non justifié bloque la merge request. Ajouter le test métier : une commande créée dans le logiciel de logistique.

## Banc de pièges et mesures

Pièges à cacher : cron oublié, fichier de configuration modifié, binaire dans `/opt`, sauvegarde mensuelle, IP codée en dur.

Mesures à relever pour le jury : taux de détection, faux positifs, temps de reconstruction, temps de relecture humaine, et consommation électrique si possible pour le volet RSE.

Limites à assumer : tâches annuelles, processus lancés à la main, dépendances implicites, logiciels opaques. Les pièges manqués alimentent la roadmap.

## Interface

Une page web suffit, avec :

- la liste des VM et le score de reconstructibilité ;
- l'usage proposé par l'IA, à confirmer ou corriger ;
- les éléments par statut, avec les inconnus en évidence ;
- le rapport d'écarts et le lien vers la merge request ;
- le chrono et l'état des tests pendant la démo.

Le mode de calcul du score doit être simple et explicable devant le jury.

## Répartition

| Rôle | Responsabilités |
|---|---|
| Théo | Collecte, tests, mesures, roadmap, gel du prototype |
| MiNET 2 | VM, sandbox, sauvegardes, reconstruction, vidéo de secours |
| Ingé 3 | Secrets, classement, modèle local, génération Ansible et CI/CD |
| Ingé 4 | Interface, concurrence, RSE, renfort finance et slides |
| Manager | Rendez-vous, marché, offre, go-to-market, finance, résumé |

## Critères de réussite

- [ ] La VM de logistique est détruite puis reconstruite depuis Git sans intervention manuelle non documentée.
- [ ] Les données sont restaurées depuis le backup.
- [ ] La commande de test passe sur la VM reconstruite.
- [ ] Les pièges sont détectés ou signalés comme inconnus, et les ratés sont mesurés.
- [ ] Aucun secret n'atteint le modèle ni Git, vérifié par un test.
- [ ] Le prototype peut être relancé de zéro et tient dans le temps de l'oral (prévoir un chemin accéléré si la reconstruction est longue).
- [ ] La vidéo de secours est enregistrée.
