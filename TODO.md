# Planning de l'équipe

État au lundi 2 novembre 2026 à 17h14. La version vivante est la to-do list partagée de l'équipe, à laquelle Claude Code n'a pas accès : se fier à ce que dit Théo si les deux divergent.

Mise à jour du mardi 3 novembre vers 10h30 par Claude Code : seules les tâches du prototype sont cochées, d'après le travail fait et mesuré (détail dans le journal du prototype). Les autres tâches n'ont pas été vérifiées.

## Lundi 2 novembre, soir (cochées par l'équipe)

- [x] Valider le projet, le nom et le pitch en une phrase — Équipe
- [x] Relever le numéro d'équipe, la salle et le créneau de jury — Manager
- [x] Lister 30 contacts et envoyer les demandes de rendez-vous — Manager + Théo
- [x] Écrire le guide d'entretien de 15 minutes — Manager
- [x] Figer le périmètre et l'architecture du prototype — Théo + MiNET 2
- [x] Réserver la machine de démo — MiNET 2

## Mardi 3 novembre

- [ ] **Obligatoire :** coaching 9h–12h30 et 13h30–17h30 ; faire trancher la cible et l'offre — Équipe
- [ ] **Obligatoire :** atelier Business model et acquisition, 9h–10h, Amphi Étoile — Manager + Ingé 4
- [ ] **Obligatoire :** atelier Enjeux RSE, 13h30–14h30, Amphi Étoile — Manager + Ingé 4
- [x] Monter les trois VM de la PME fictive, avec les pièges — MiNET 2 (fait : `pme/`, 10 pièges)
- [x] Mettre en place la sandbox isolée et les sauvegardes — MiNET 2 (fait : `infra/sandbox.py`, restic ; cron de sauvegarde réparé le 3 nov.)
- [x] Écrire la collecte en lecture seule — Théo (`collecte/bs-collect`)
- [x] Masquer les secrets et classer chaque élément — Ingé 3 (`classement/bs-classify`)
- [x] Faire tourner un modèle local sur la machine de démo — Ingé 3 (`bs-ia`, `qwen3.6:35b`, 5 propositions en ~90 s)
- [x] Maquetter l'écran de rapport et le score de reprise — Ingé 4 (`rapport/bs-rapport` : verdict, reprise mesurée, points à risque)
- [ ] Mener les premiers entretiens et relancer les contacts — Manager + Ingé 4
- [ ] Chiffrer TAM, SAM et SOM et décrire le persona — Manager
- [ ] Faire le schéma de concurrence et détailler au moins 3 acteurs — Ingé 4
- [ ] Décrire la chaîne de valeur et le cadre juridique — Manager

## Prototype : reste à faire avant le gel (jeudi midi)

- [ ] Vérifier que la sauvegarde de 02h30 a bien tourné par cron dans la nuit du 3 au 4 novembre (nouvel instantané restic) — Claude Code
- [ ] Script de démo chronométré du scénario B (~10 min en direct : audit + propositions 1,5 min, deux CI de ~4 min, décision, bascule 27 à 29 s) — Théo + Claude Code
- [ ] Fiche des chiffres mesurés, avec leur source, pour l'executive summary — Claude Code
- [ ] Afficher l'âge de la sauvegarde sur la page de rapport et republier l'artifact — Claude Code
- [ ] Optionnel : MR de reconstruction pour `bs-mail` et `bs-proxy` ; ajouter `/srv/edi` à la sauvegarde restic — Claude Code
- [ ] Avant chaque démo : `pme/deploy.sh pieges` si `bs-logistique` a redémarré ; modèle chargé sur `bs-ia` (3 à 5 min) ; supprimer `decisions/bs-logistique.propositions.json` pour un appel en direct — Théo
- [ ] Pièges à l'aveugle — MiNET 2
- [ ] `git init` puis commit de `blackstart-context` (Claude Code ne commite pas hors forge) — Théo
- [ ] Signaler à MiNET la clé d'hôte du template partagée avec `swarm-blueblood` — Théo
- [ ] Faire vérifier la barrette A2 de luna par MiNET (erreurs UEFI0058/UEFI0107 du 3 nov.) ; pas de forte charge d'ici là — Théo

À dire au jury : le modèle formule la question à poser pour chaque inconnu ; il ne classe pas. Sur des preuves stables, ses propositions ne rejoignent les décisions humaines sur aucun des 5 inconnus de `bs-logistique` (4 « à vérifier », 1 contradiction).

## Mercredi 4 novembre

- [ ] **Obligatoire :** atelier Finance et Pitch — Équipe (équipes 1–47 : 9h–10h ; équipes 48–94 : 10h15–11h15)
- [ ] **Obligatoire :** coaching 9h–12h30 et 13h30–17h30, hors atelier — Équipe
- [ ] **GO / NO-GO, midi :** confirmer la cible et l'offre avec les entretiens — Équipe
- [x] Générer le code Ansible et la CI/CD dans une branche GitLab — Ingé 3 + Théo (Forgejo sur `bs-gitlab`, MR n° 1 à 5)
- [x] Reconstruire la VM de logistique depuis Git et le backup — MiNET 2 (CI verte en ~4 min)
- [x] Écrire les tests de comparaison et la commande de test — Théo (`bs-compare`, `banc/test-metier.py`)
- [x] Brancher l'interface sur les vrais résultats — Ingé 4
- [x] Mesurer le prototype sur les pièges — Théo + Ingé 3 (détection 10/10)
- [ ] **GO / NO-GO, 18h :** la démo passe de bout en bout, sinon réduire à une VM — Théo + MiNET 2 (scénario B répété de bout en bout le 3 nov. sur `bs-logistique` ; décision à prendre par l'équipe)
- [ ] Fixer l'offre et les prix : audit, reconstruction, abonnement — Manager
- [ ] Construire le prévisionnel sur 5 ans, au moins 700 à 800 k€ de CA en année 5 — Manager + Ingé 4
- [ ] Définir la stratégie de financement — Manager
- [ ] Écrire le go-to-market et le planning à 5 ans — Manager
- [ ] Chiffrer l'impact RSE positif et négatif — Ingé 4
- [ ] Écrire l'état de l'art et la roadmap technique — Théo
- [ ] Obtenir des marques d'intérêt écrites de professionnels — Manager
- [ ] Finaliser l'executive summary de 2 pages le soir — Manager + Théo

## Jeudi 5 novembre

- [ ] **Rendu, avant 9h :** déposer l'executive summary sur Moodle — Manager
- [ ] Geler le prototype à midi — Théo
- [ ] Réaliser les slides en suivant la grille — Manager + Ingé 4
- [ ] Scénariser la démo — Théo + MiNET 2 (scénario B choisi : premier audit, MR, CI rouge, décision humaine, CI verte, bascule ; reste le script chronométré)
- [ ] Enregistrer une vidéo de secours — MiNET 2
- [ ] Répartir la parole entre les 5 membres — Équipe
- [ ] Répéter chronométré devant un coach (open coaching facultatif, 10h–17h, rue Étoile) — Équipe
- [ ] Préparer les questions du jury avec l'autotest — Équipe

## Vendredi 6 novembre

- [ ] Tester la démo et la vidéo de secours avant le passage — MiNET 2
- [ ] **Rendu :** oral, 9h–17h30, bâtiment F, selon le planning des jurys — Équipe

## Lundi 9 novembre, si lauréats

- [ ] Préparer le pitch de 3 minutes avec 2 ou 3 slides — Manager + Théo
- [ ] **Finale :** pitch à 18h, Amphi 10, vote de la salle — Équipe
