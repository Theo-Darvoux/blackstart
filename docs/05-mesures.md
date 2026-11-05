# Mesures du prototype

Chiffres mesurés sur le laboratoire, état au mardi 3 novembre 2026 vers 12h30. Chaque ligne donne sa source pour qu'on puisse la revérifier. Un chiffre absent de cette fiche n'est pas mesuré : il se présente comme une hypothèse.

**Labo :** PME fictive de 3 VM Debian 13 (`bs-logistique`, `bs-mail`, `bs-proxy`) montée par l'équipe sur `luna.minet.lan` (Dell R630, 2 × Xeon E5-2660 v3, sans GPU), plus la forge Forgejo et sa CI sur `bs-gitlab`. Les pièges (P1 à P10) ont été posés par l'équipe, qui en connaissait les réponses.

## Reprise de `bs-logistique`

| Mesure | Valeur | Conditions | Source |
| --- | --- | --- | --- |
| Reconstruction vérifiée en CI (VM neuve → code → données restaurées → redémarrage → test métier → comparaison) | **214 à 262 s** (≈ 4 min) sur 12 passages complets depuis l'ajout du redémarrage (10 verts, 2 bloqués par les décisions en attente). **Chiffre de référence des rendus : 3 min 34 s (214 s)**, passage du 5 nov. à 02h02 (MR n° 13, VM vide : sandbox 74 s, reconstruction 85 s, restauration 9 s, redémarrage 22 s, test métier 1 s, collecte 23 s ; 37 écarts, 0 non justifié) | sandbox isolée, détail : création de la VM 71 à 95 s, Ansible 89 à 93 s, restauration 10 s, redémarrage 30 s, test métier 10 à 11 s, collecte 21 à 26 s | rapports de CI des MR n° 2 à 5, 7, 8, 11 et 13 sur la forge (`pme/infra`) |
| Même parcours sans l'étape de redémarrage | 211 à 217 s | MR n° 1, 2 novembre | rapports de CI de la MR n° 1 |
| Coupure du service à la bascule vers la copie vérifiée | **27,3 s (2 fois), 27,4 s, 27,5 s, 27,7 s (2 fois), 28,2 s, 29,4 s** (8 bascules) | de l'arrêt de l'original jusqu'au test métier complet vert (DNS, proxy, base, création de commande, mail réel reçu) ; aucun geste manuel | `banc/resultats/bascule-20261102-2225.json`, `bascule-20261103-0923.json`, `bascule-20261103-0932.json`, `bascule-20261103-1233.json`, `bascule-20261103-1549.json`, `bascule-20261103-1620.json`, `bascule-20261103-1630.json`, `bascule-20261103-1650.json` |
| Retour arrière vers l'original | 24,6 s et 31,2 s (2 fois) le 3 nov., 35 s le 2 nov. | les écritures faites sur la copie pendant la bascule sont perdues | sortie de `infra/bascule.py retour`, journal du prototype |
| Bascule refusée si la CI n'est pas verte | refus vérifié | MR n° 3, CI en cours | journal du prototype, 3 nov. 09h |
| Perte de données maximale à la bascule | âge de la dernière sauvegarde : mesuré à 0,2 h lors de la MR n° 5 ; jusqu'à 24 h par construction (sauvegarde quotidienne à 02h30, non mesuré) | la copie repart du dernier instantané restic | rapport de CI de la MR n° 5 (« Données restaurées ») |
| Démo de l'oral, salle de contrôle (`infra/salle`) | **3 min 19 s** (199 s) : audit 9 s, IA + code + MR 2 s (propositions calculées à la préparation : 68,7 s), CI rouge 2 s (refus immédiat, 5 décisions en attente), décisions 7 s (rejouées par script), CI verte 149 s (sandbox préchauffée 0 s, reconstruction 86 s, restauration 10 s, redémarrage 22 s, audit de la copie 26 s, test métier 1 s), bascule 27,5 s de coupure | MR n° 12, 3 nov. 16h20 ; décisions cliquées en direct : compter le temps de lecture et de décision. Répétitions suivantes avec décisions cliquées à la main : 4 min 18 s (258 s, décisions 53 s) à 16h30, 8 min 31 s (511 s, décisions 299 s) à 16h50 | `banc/resultats/demo-salle-20261103-1620.json`, `demo-salle-20261103-1630.json`, `demo-salle-20261103-1650.json` |
| Démo complète du scénario B, en répétition | **9 min 43 s** (583 s) : préparation 1 s, audit en direct 9 s, propositions du modèle + MR 70 s, CI rouge 222 s, décisions 2 s (rejouées), CI verte 221 s, bascule 27,3 s de coupure, retour 29 s ; 1re répétition (12h55) : ≈ 11 min | MR n° 12, 3 nov. 15h50 ; décisions tapées en direct : compter en plus le temps de décision | `banc/resultats/demo-b-20261103-1550.json`, `demo-b-20261103-1255.json` |

## Audit et classement

| Mesure | Valeur | Conditions | Source |
| --- | --- | --- | --- |
| Détection des pièges du banc | **10 / 10** (dont les 5 de la spec) | inventaire de `bs-logistique` après pièges, recollecté le 3 nov. | `banc/resultats/mesure-20261103-1015.json` |
| Écarts relevés entre le template et `bs-logistique` | **176** classés : 139 compris (reproduits par le code), 21 ignorés avec une règle, 7 secrets (coffre), 3 données (sauvegarde), 6 inconnus (175 avant la recollecte de 16h42 le 3 nov. : 19 ignorés, 4 données) | dont 5 inconnus réels à trancher par un humain ; le 6e (`/etc/postgresql/17/main/conf.d`) est un artefact de collecte, sans preuve | `classement/bs-classify` sur `inventaires/bs-logistique-pieges.content.json` (recompté le 5 nov.) |
| `bs-mail` | 96 écarts, 0 inconnu, 1 IP écrite en dur ; sauvegarde restic des boîtes ajoutée le 3 nov. (`/var/mail`, `/home/commandes`) | reconstruite en CI en **206 à 207 s** avec la boîte restaurée (instantané de 13h23), test métier vert (SMTP, distribution, IMAPS), 0 écart non justifié ; **reconstruction prouvée** (MR n° 9 fusionnée, état de Postfix et Dovecot régénérable, perte acceptée par Théo) | `classement/bs-classify`, rapport de CI de la MR n° 9 |
| `bs-proxy` | 57 écarts, 0 inconnu, 5 IP écrites en dur ; 3 dossiers de données régénérables, perte acceptée par Théo | **reconstruction prouvée** en CI en **144 s** : test métier vert (DNS, nginx, configuration), 0 écart non justifié ; MR n° 10 fusionnée | `classement/bs-classify`, rapport de CI de la MR n° 10 |
| IP d'autres machines écrites en dur dans `bs-logistique` | 3 | | `classement/bs-classify` |
| Code de reconstruction généré | 52 tâches Ansible, 7 chemins vers le coffre, 0 inconnu appliqué sans décision | après les décisions humaines | sortie de `generation/bs-generate` |

## Modèle local

| Mesure | Valeur | Conditions | Source |
| --- | --- | --- | --- |
| Proposition d'un statut pour les 5 inconnus | **68 à 69 s** une fois le modèle chargé, 272 à 275 s à froid | `qwen3.6:35b` (Ollama) sur `bs-ia`, 10 cœurs, 48 Go, sans GPU ; 555 jetons en sortie, JSON valide à chaque passage. Avant le passage de luna à 128 Go (VM à 24 Go) : 70 à 91 s | `banc/resultats/modeles-20261103-1156.json`, `modeles-20261103-1210-qwen-rechargement.json` |
| Vitesse de génération | 8,2 jetons/s (`qwen3.6:35b`), 7,2 jetons/s (`gemma4:26b`) | | mêmes fichiers |
| Chargement du modèle en mémoire | 188 à 191 s (`qwen3.6:35b`), 140 s (`gemma4:26b`) | d'où le modèle gardé chargé en permanence | mêmes fichiers |
| Reproductibilité | même entrée → même sortie, y compris après rechargement du modèle ; mais la sortie a changé quand la VM est passée de 24 à 48 Go | température 0, graine fixe | mêmes fichiers, journal du prototype |
| Accord avec les décisions humaines | `qwen3.6:35b` : **1 / 5** identique, 4 « à vérifier », 0 contradiction. `gemma4:26b` : 1 / 5 identique, 2 « à vérifier », **2 contradictions** (propose de reproduire le relais HTTP lancé à la main en root) | preuves stables ; avant normalisation, changer un seul numéro de session faisait changer 3 propositions sur 5 | mêmes fichiers, journal du prototype, 3 nov. 10h15 |
| Données envoyées au modèle | uniquement des faits de l'inventaire, secrets masqués ; jamais le contenu d'un fichier fermé, ni `pme/`, ni les réponses du banc | | `classement/bs-classify --preuves` |

## Ce que le prototype a trouvé sans que ce soit un piège

- **Sauvegarde nocturne jamais exécutée.** Le cron de 02h30 échouait (« runuser: not found », `/usr/sbin` absent du PATH de cron), sans alerte, faute de serveur mail. Seules les 2 sauvegardes faites à la main au déploiement existaient. Trouvé le 3 novembre en expliquant un écart de commandes entre la copie et l'original ; corrigé le jour même. Depuis, la CI compare la date de l'instantané au dernier passage prévu du cron et alerte en cas de retard. Source : journal du prototype, 3 nov. 10h00 et 10h30.
- **Export EDI vers le transporteur jamais exécuté** (même cause : `runuser` hors du PATH de cron, piège P1). Le script sortait en code 0 sans rien produire. Corrigé le 3 novembre, et `/srv/edi` ajouté à la sauvegarde restic. Source : journal du prototype, 3 nov. ~13h.
- **Mots de passe des comptes non restaurés.** La reconstruction recréait les comptes sans leur mot de passe (boîte IMAP de `bs-mail` inaccessible). Corrigé : empreinte reprise du `/etc/shadow` du coffre. Source : journal du prototype, 3 nov. ~13h30.
- **Commande de test emportée en production.** La copie gardait la commande créée par le test de la CI. Corrigé : chaque test supprime sa commande et rend le stock. Source : journal du prototype, 3 nov. 09h45 et 10h30.

## Limites à dire

- Les 3 VM sont reconstruites et vérifiées en CI ; seule `bs-logistique` est basculée. `bs-proxy` n'a pas de sauvegarde (données régénérables, perte acceptée) ; `bs-mail` n'en a que depuis le 3 novembre.
- Les pièges ont été écrits par l'équipe : 10/10 mesure l'outil sur des cas connus, pas sur une vraie PME. Des pièges à l'aveugle restent à poser.
- En sandbox, le mail ne peut pas sortir : l'envoi du mail est vérifié à la bascule, pas en CI.
- Le modèle formule la question à poser pour chaque inconnu ; il ne classe pas de façon fiable. La décision reste humaine.
- Toutes les mesures viennent d'un seul hyperviseur, dont une barrette mémoire a eu une erreur le 3 novembre à 03h16.

## Estimations (non mesurées)

- **Reconstruction à la main de `bs-logistique` : 16 à 32 h** (inventaire, écriture du code, test, écarts). Estimation de l'équipe, d'après son expérience du déploiement de services à MiNET. Non mesurée : à présenter comme une estimation.
