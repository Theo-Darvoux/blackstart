# Le projet

## Équipe

Cinq personnes : quatre ingénieurs, dont deux de MiNET (le FAI étudiant de Télécom SudParis et IMT-BS), et une personne manager/communication. Le Challenge demande un prototype, pas un produit déployé. Le discours doit toutefois présenter le lancement d'une vraie start-up sur 5 ans.

Avant ce projet, l'équipe portait « Relais », un outil de transmission vérifiée des accès numériques. Il a été remplacé.

## Problème

Beaucoup d'entreprises dépendent de serveurs configurés à la main et peu documentés, que plus personne n'ose toucher. Elles ont souvent des sauvegardes, mais rarement la preuve qu'elles sauraient redémarrer après une panne, une cyberattaque ou le départ d'un administrateur.

Cette formulation reste à prouver par les entretiens.

Une restauration réussie ne suffit pas :

- après un rançongiciel, l'image restaurée peut contenir une porte dérobée ou une faille encore ouverte ;
- une VM qui démarre ne prouve pas que l'entrepôt peut expédier une commande ;
- sans inventaire ni code, la reprise dépend encore de quelques personnes.

## Cible

**Cible principale :** ETI françaises industrielles et logistiques, avec un petit service informatique et un parc on-premise ou hybride.

- **Acheteur :** DSI ou RSSI, avec le dirigeant comme sponsor possible.
- **Utilisateur :** administrateur système ou équipe d'exploitation.
- **Canal possible ensuite :** infogérants.

Pourquoi cette cible : taille du segment, coût élevé d'un arrêt, budget et interlocuteur identifiables, et cohérence avec une démo logistique.

**Principal risque :** ces entreprises utilisent probablement beaucoup de Windows et d'Active Directory, alors que le prototype vise Linux. À vérifier en entretien. Si Linux est trop minoritaire, ajuster la cible ; les éditeurs de logiciels français sont une piste à vérifier.

Cibles écartées pour commencer : hôpitaux (cycles d'achat longs malgré le programme CaRE), collectivités (marchés publics, budgets serrés), PME (budget plus faible et souvent personne pour relire les merge requests).

## Positionnement

Le produit ne vend ni un backup ni GitLab. Il vend la **preuve de bout en bout** : repartir des sauvegardes existantes, reconstruire ce qui doit l'être, puis vérifier que le processus métier fonctionne.

Phrase commerciale : « Vos sauvegardes existent. Nous prouvons que votre activité peut réellement repartir, et nous corrigeons ce qui l'en empêche. »

Le nom vient du « black start », le redémarrage d'un réseau électrique après une panne totale, sans aide extérieure. Faire confirmer cette analogie par une source avant de l'utiliser à l'oral.

## Solution, en quatre niveaux

| Niveau | Question | Action | Rôle de GitLab |
|---|---|---|---|
| 1. Prouver | Peut-on redémarrer, et en combien de temps ? | Restauration en sandbox isolée, tests métier, rapport et chrono | Aucun ou presque |
| 2. Combler | Que manque-t-il ? | Dépendances, secrets, étapes manuelles et VM non reproductibles | Documentation versionnée |
| 3. Reconstruire proprement | Peut-on repartir d'un système sain ? | VM critiques recréées depuis le code, données issues des backups | Central |
| 4. Maintenir | Est-ce encore vrai ce mois-ci ? | Test de reprise régulier et détection de dérive | Central |

## Déroulé pour une VM

Déroulé tel que le prototype le réalise (et tel que le présentent le deck et l'executive summary) :

1. **Collecte :** un script fixe inventorie la VM en lecture seule et masque les secrets.
2. **Classement :** des règles déterministes classent chaque écart (compris, donnée, secret, ignoré, inconnu), avec une preuve.
3. **Décision :** le modèle local formule une proposition pour chaque inconnu ; l'admin tranche.
4. **Code :** Ansible et la CI/CD sont générés (de façon déterministe dans le prototype) dans une branche, en merge request.
5. **Preuve :** la CI reconstruit la VM dans la sandbox depuis le code et les sauvegardes, relance la même collecte, compare et passe le test métier. Tout écart non justifié, ou toute décision en attente, bloque la merge request.
6. **Bascule :** la nouvelle VM remplace l'ancienne seulement si la CI est verte ; l'ancienne reste disponible pour revenir en arrière.

Piste non réalisée dans le prototype : en cas d'écart, laisser l'IA corriger et relancer, avec une limite de tentatives avant de passer la main à un humain.

Certains cas restent manuels : logiciels métier sous licence, secrets à ressaisir, grosses bases de données et services dont personne ne connaît le comportement attendu.

## Modèle économique

Cabinet de conseil équipé de son propre outil. L'outil traite les cas courants et les consultants les exceptions.

1. **Audit :** en une semaine de lecture seule, cartographie et score de reconstructibilité sur 5 à 10 applications critiques.
2. **Migration :** reconstruction des VM critiques, au forfait.
3. **Abonnement :** détection de dérive, test de reconstruction régulier et rapport de reprise.

Déclencheurs d'achat à valider : audit d'un client, renouvellement de cyberassurance, incident récent, test de reprise. NIS2 sert d'argument secondaire, pas de moteur unique.

Les prix ne sont pas fixés. Le support officiel attend au moins 700 à 800 k€ de chiffre d'affaires après 5 ans.

## Décisions prises

- **Pas de « mode turbo » :** l'IA agit librement en sandbox, mais seulement par merge request vers la production.
- **Modèle local et interchangeable :** `qwen3.6:35b` retenu (sur CPU, sans GPU) ; `gemma4:26b` comparé et écarté (2 contradictions sur 5). Devstral reste une option souveraine, non testée. Kimi est écarté car trop lourd.
- **Audit des pipelines GitLab :** au mieux un produit d'appel gratuit, pas un second produit.
- **Réseau :** switchs et routeurs limités à la sauvegarde et à la lecture de configuration.
- **Promesse honnête :** ne jamais annoncer « 100 % détecté ». Dire : « Tout ce qui n'est pas expliqué vous est signalé, et ce qui a été reconstruit a été testé. »
- **Pistes rejetées :** l'outil de planning sous contraintes (marché occupé, moins aligné avec l'équipe) et le simple test de backups (terrain déjà couvert par les éditeurs).
