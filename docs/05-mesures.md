# Mesures du prototype

Chiffres mesurés sur le laboratoire, état au mardi 3 novembre 2026 vers 10h30. Chaque ligne donne sa source pour qu'on puisse la revérifier. Un chiffre absent de cette fiche n'est pas mesuré : il se présente comme une hypothèse.

**Labo :** PME fictive de 3 VM Debian 13 (`bs-logistique`, `bs-mail`, `bs-proxy`) montée par l'équipe sur `luna.minet.lan` (Dell R630, 2 × Xeon E5-2660 v3, sans GPU), plus la forge Forgejo et sa CI sur `bs-gitlab`. Les pièges (P1 à P10) ont été posés par l'équipe, qui en connaissait les réponses.

## Reprise de `bs-logistique`

| Mesure | Valeur | Conditions | Source |
| --- | --- | --- | --- |
| Reconstruction vérifiée en CI (VM neuve → code → données restaurées → redémarrage → test métier → comparaison) | **233 à 258 s** (≈ 4 min) sur 7 passages complets depuis l'ajout du redémarrage (6 verts, 1 bloqué par les décisions en attente) | sandbox isolée, détail : création de la VM 71 à 95 s, Ansible 89 à 93 s, restauration 10 s, redémarrage 30 s, test métier 10 à 11 s, collecte 21 à 26 s | rapports de CI des MR n° 2 à 5 sur la forge (`pme/infra`) |
| Même parcours sans l'étape de redémarrage | 211 à 217 s | MR n° 1, 2 novembre | rapports de CI de la MR n° 1 |
| Coupure du service à la bascule vers la copie vérifiée | **27,4 s, 28,2 s, 29,4 s** (3 bascules) | de l'arrêt de l'original jusqu'au test métier complet vert (DNS, proxy, base, création de commande, mail réel reçu) ; aucun geste manuel | `banc/resultats/bascule-20261102-2225.json`, `bascule-20261103-0923.json`, `bascule-20261103-0932.json` |
| Retour arrière vers l'original | 31,2 s (2 fois le 3 nov.), 35 s (2 nov.) | les écritures faites sur la copie pendant la bascule sont perdues | sortie de `infra/bascule.py retour`, journal du prototype |
| Bascule refusée si la CI n'est pas verte | refus vérifié | MR n° 3, CI en cours | journal du prototype, 3 nov. 09h |
| Perte de données maximale à la bascule | âge de la dernière sauvegarde : mesuré à 0,2 h lors de la MR n° 5 ; jusqu'à 24 h par construction (sauvegarde quotidienne à 02h30, non mesuré) | la copie repart du dernier instantané restic | rapport de CI de la MR n° 5 (« Données restaurées ») |

## Audit et classement

| Mesure | Valeur | Conditions | Source |
| --- | --- | --- | --- |
| Détection des pièges du banc | **10 / 10** (dont les 5 de la spec) | inventaire de `bs-logistique` après pièges, recollecté le 3 nov. | `banc/resultats/mesure-20261103-1015.json` |
| Écarts relevés entre le template et `bs-logistique` | 175 classés : 139 compris (reproduits par le code), 19 ignorés avec une règle, 7 secrets (coffre), 4 données (sauvegarde), 6 inconnus | dont 5 inconnus réels à trancher par un humain ; le 6e (`/etc/postgresql/17/main/conf.d`) est un artefact de collecte, sans preuve | `classement/bs-classify` sur `inventaires/bs-logistique-pieges.content.json` |
| `bs-mail` | 96 écarts, 0 inconnu, 1 IP écrite en dur | non reconstruite | `classement/bs-classify` |
| `bs-proxy` | 57 écarts, 0 inconnu, 5 IP écrites en dur | non reconstruite | `classement/bs-classify` |
| IP d'autres machines écrites en dur dans `bs-logistique` | 3 | | `classement/bs-classify` |
| Code de reconstruction généré | 52 tâches Ansible, 7 chemins vers le coffre, 0 inconnu appliqué sans décision | après les décisions humaines | sortie de `generation/bs-generate` |

## Modèle local

| Mesure | Valeur | Conditions | Source |
| --- | --- | --- | --- |
| Proposition d'un statut pour les 5 inconnus | **78 à 91 s** (4 passages) | `qwen3.6:35b` (Ollama) sur `bs-ia`, 10 cœurs, 24 Go, sans GPU, modèle déjà chargé ; ~1 000 jetons en entrée, ~500 en sortie, JSON valide à chaque fois | `forge/pme-infra/decisions/bs-logistique.propositions.json`, journal du prototype |
| Vitesse de génération | 6,5 jetons/s | | journal du prototype, 3 nov. 03h50 |
| Chargement du modèle en mémoire | 192 à 283 s | d'où le modèle gardé chargé en permanence | journal du prototype |
| Accord avec les décisions humaines | **0 / 5** identique, 4 « à vérifier », 1 contradiction (swappiness) | preuves stables ; avant normalisation, changer un seul numéro de session faisait changer 3 propositions sur 5 | journal du prototype, 3 nov. 10h15 |
| Données envoyées au modèle | uniquement des faits de l'inventaire, secrets masqués ; jamais le contenu d'un fichier fermé, ni `pme/`, ni les réponses du banc | | `classement/bs-classify --preuves` |

## Ce que le prototype a trouvé sans que ce soit un piège

- **Sauvegarde nocturne jamais exécutée.** Le cron de 02h30 échouait (« runuser: not found », `/usr/sbin` absent du PATH de cron), sans alerte, faute de serveur mail. Seules les 2 sauvegardes faites à la main au déploiement existaient. Trouvé le 3 novembre en expliquant un écart de commandes entre la copie et l'original ; corrigé le jour même. Depuis, la CI compare la date de l'instantané au dernier passage prévu du cron et alerte en cas de retard. Source : journal du prototype, 3 nov. 10h00 et 10h30.
- **Commande de test emportée en production.** La copie gardait la commande créée par le test de la CI. Corrigé : chaque test supprime sa commande et rend le stock. Source : journal du prototype, 3 nov. 09h45 et 10h30.

## Limites à dire

- Une seule VM est reconstruite et basculée (`bs-logistique`). `bs-mail` et `bs-proxy` sont auditées, pas reconstruites.
- Les pièges ont été écrits par l'équipe : 10/10 mesure l'outil sur des cas connus, pas sur une vraie PME. Des pièges à l'aveugle restent à poser.
- En sandbox, le mail ne peut pas sortir : l'envoi du mail est vérifié à la bascule, pas en CI.
- Le modèle formule la question à poser pour chaque inconnu ; il ne classe pas de façon fiable. La décision reste humaine.
- Toutes les mesures viennent d'un seul hyperviseur, dont une barrette mémoire a eu une erreur le 3 novembre à 03h16.
