# Executive summary : Black Start

**Challenge Projets d'Entreprendre 2026 · Équipe n° 16 · Projet : Black Start**

- Théo Darvoux, Télécom SudParis
- Titouan Jouanot-Goupil, Télécom SudParis
- Benjamin Mora, ENSIIE
- Maxime Theret, ENSIIE
- Glenn Aaron, IMT-BS

**Vos sauvegardes existent. Nous prouvons que votre entreprise sait repartir.** Black Start reconstruit les serveurs critiques d'une entreprise sur une base saine, depuis du code et ses sauvegardes existantes, puis prouve par un test métier que l'activité repart. Chaque reprise est chronométrée.

## 1. Le problème

Dans beaucoup d'ETI, les serveurs critiques (logistique, messagerie, DNS) ont été configurés à la main, sont peu documentés et plus personne n'ose y toucher. L'entreprise a des sauvegardes, mais rarement la preuve qu'elle saurait redémarrer, ni en combien de temps.

- Après un rançongiciel, l'image restaurée ramène la porte dérobée de l'attaquant.
- Après une panne, la VM démarre, mais l'entrepôt n'expédie toujours aucune commande.
- Après un départ, sans inventaire ni code, la reprise dépend de quelques personnes.

**13 M€** : coût moyen déclaré d'une cyberattaque pour une ETI (466 k€ pour une TPE ou une PME). Enquête de l'ANSSI auprès du CLUSIF, citée par le Sénat, rapport n° 393 (2024-2025). Chiffre déclaratif.

Les sauvegardes sont visées : chez 94 % des victimes de rançongiciel, l'attaquant s'en est pris aux sauvegardes, avec succès dans 57 % des cas ; seules 26 % de ces victimes se rétablissent en une semaine, contre 46 % quand les sauvegardes sont intactes (Sophos, 2024, 2 974 répondants). La reprise reste partielle : 10 % des organisations attaquées récupèrent plus de 90 % de leurs données (Veeam, avril 2025, 1 300 organisations).

## 2. Marché et cible

**Cible :** ETI françaises industrielles et logistiques, petit service informatique, parc Linux on-premise ou hybride. **Acheteur :** DSI ou RSSI, dirigeant en sponsor. **Utilisateur :** l'admin système, qui relit les merge requests. **Partenaires :** infogérants, ESN.

| | Valeur | Calcul |
|---|---|---|
| TAM | 374 M€/an | 6 800 ETI × 55 k€ |
| SAM | 52 M€/an | ~2 600 ETI industrielles et logistiques × 40 % avec un parc Linux (hypothèse) = ~1 040 ETI × 50 k€ |
| SOM, année 5 | 2,07 M€ | 45 clients, ~4 % du SAM |

**Déclencheurs :** renouvellement de la cyberassurance, audit d'un client, incident récent, départ de l'admin. **Cadre juridique :** NIS2 vise ~15 000 entités en France ; la loi Résilience qui la transpose n'est pas votée (retirée de l'ordre du jour de l'Assemblée en octobre 2026), conformité visée fin 2028 par l'ANSSI. Argument secondaire, pas moteur de la vente.

Sources : ministère de l'Économie (2022), Insee Première n° 2084 (2025), Silicon.fr, Myra Security, AOCSI. Part Linux et budgets : hypothèses de l'équipe.

## 3. Concurrence

| Acteur | Ce qu'il fait | Ce qui manque |
|---|---|---|
| Veeam (sauvegarde, 1,7 Md$ de revenus récurrents en 2024) | Restauration vérifiée, large base installée | Ni audit du contenu des VM, ni reconstruction depuis le code |
| Firefly (IaC cloud, 23 M$ levés en 2024) | Codifie le cloud et le rend résilient | Cloud surtout, pas de preuve métier |
| ControlMonkey (IaC cloud, 7 M$ seed en janv. 2025) | Terraform généré depuis l'existant | Ne lit pas l'intérieur des VM |
| ESN, cabinets PRA | Exercices de reprise, présence terrain | Manuel, ponctuel, coûteux |

**Enseignement :** le cloud est bien couvert. Personne ne prouve, de bout en bout et de façon répétable, la reprise métier d'une VM on-premise. C'est notre créneau, et l'argument du modèle local : aucune donnée ne sort de chez le client.

## 4. La solution

Un cabinet outillé : l'outil traite les cas courants, l'ingénieur les exceptions. Quatre niveaux : **prouver** (reprise en sandbox, test métier, chrono), **combler** (secrets, dépendances, gestes manuels, sauvegardes absentes), **reconstruire** (VM recréée depuis le code, données issues des sauvegardes), **maintenir** (test de reprise régulier, détection de dérive).

1. **Collecte** (script, sans IA) : inventaire en lecture seule de la VM, secrets masqués, comparé à celui d'une Debian vierge de même version. Chaque différence (paquet ajouté, fichier modifié, service activé, tâche planifiée, port ouvert…) est un **écart** : ce que l'admin a fait à la main, et que la reconstruction doit reproduire ou écarter.
2. **Classement** (règles) : chaque écart est compris, donnée, secret, ignoré ou inconnu, avec sa preuve.
3. **Décision** (humain) : le modèle local formule la question ; l'admin tranche chaque inconnu.
4. **Code** : Ansible et intégration continue, proposés en merge request.
5. **Preuve** (sandbox isolée) : VM neuve, données restaurées, même collecte, comparaison, test métier.
6. **Bascule** (chronométrée) : refusée si la vérification est rouge, retour arrière possible.

**Garde-fous :** l'IA ne modifie jamais la production sans merge request relue ; aucun inconnu n'est reproduit sans décision humaine ; les secrets vont dans un coffre, jamais au modèle ni dans Git. Promesse : *tout ce qui n'est pas expliqué vous est signalé, et ce qui a été reconstruit a été testé.*

## 5. Le prototype : des chiffres mesurés

Banc de test : une PME fictive de 3 serveurs Debian (logiciel de logistique avec sa base, messagerie, proxy et DNS) montée par l'équipe sur un hyperviseur Proxmox, avec forge Git et intégration continue. Mesures du 2 au 5 novembre 2026.

- **3 min 34 s** de la VM vide au service vérifié par le test métier (passage du 5 novembre ; 214 à 262 s sur 12 passages en CI).
- **28 s** de coupure à la bascule vers la copie vérifiée (27,3 à 29,4 s, 8 bascules, aucun geste manuel).
- **10/10** pièges détectés (posés par l'équipe).
- **176 écarts** classés sur la VM de logistique, dont 139 reproduits par le code ; **5 décisions** laissées à l'humain.
- **3 serveurs sur 3** reconstruits et vérifiés en CI (messagerie en 206 s, proxy et DNS en 144 s) ; la logistique est basculée, avec retour arrière en 25 à 35 s.
- **Démo de l'oral en 3 min 19 s.** À la main, la même VM demande 16 à 32 h (estimation de l'équipe, issue de son expérience à MiNET).
- **IA locale, sur CPU, sans GPU** (Qwen 3.6 35B) : 68 à 69 s pour proposer un statut aux 5 inconnus ; 1 avis identique à la décision humaine, 4 « à vérifier », 0 contradiction. Le modèle pose la question, l'humain décide.
- **Limites :** pièges écrits par nous, Linux seulement, un seul hyperviseur.

## 6. Business model

| Offre | Prix | Contenu |
|---|---|---|
| Audit (porte d'entrée) | 15–25 k€ | 1 semaine en lecture seule, score de reconstructibilité sur 5 à 10 applications critiques |
| Migration (forfait) | 30–60 k€ par VM | Reconstruction des VM critiques depuis le code, bascule chronométrée |
| Abonnement (récurrent) | 2–5 k€ par mois et par application | Test de reprise régulier, détection de dérive, rapport de reprise |

## 7. Go-to-market

| Phase | Canal | Coût d'acquisition |
|---|---|---|
| A1–A2 | Réseau direct : conférences cyber, IMT Alumni | ~2 k€ |
| A1–A2 | Démos en direct et contenu technique | ~0,5 k€ |
| A3–A4 | Infogérants, commission de 20 % | 0 € fixe |
| A5 | Commercial dédié, salons sectoriels | ~3 k€ |

Cycle de 4 à 8 semaines du contact à la signature. LTV/CAC visé > 10. Roadmap : tout le parc Linux d'un client pilote (A1), observation longue par eBPF (A2), Windows et Active Directory (A3), Europe : DACH, Benelux (A5).

## 8. Prévisionnel sur 5 ans

| k€ | A1 · 2027 | A2 | A3 | A4 | A5 · 2031 |
|---|---:|---:|---:|---:|---:|
| Clients sous abonnement | 3 | 10 | 20 | 32 | 45 |
| CA audit + migration | 225 | 450 | 675 | 810 | 990 |
| CA abonnement | 72 | 240 | 480 | 768 | 1 080 |
| **Chiffre d'affaires** | **297** | **690** | **1 155** | **1 578** | **2 070** |
| Charges | 360 | 465 | 710 | 965 | 1 265 |
| Résultat | −63 | 225 | 445 | 613 | 805 |
| Effectif | 5 | 5 | 7 | 9 | 12 |

Hypothèses (bas des fourchettes) : 5, 10, 15, 18, 22 nouveaux clients par an, chacun à 15 k€ d'audit + 30 k€ (1 VM), puis 2 k€/mois ; salaires chargés 60 à 80 k€.

## 9. Financement

- **Pré-seed, 2027 : 50–100 k€** (Bourse French Tech, i-Lab, love money) pour finaliser l'outil et signer les premiers clients pilotes.
- **Seed, 2028 : 0,5–1 M€** (fonds cyber, France 2030) pour les consultants, le 2e commercial et le 2e développeur de l'outil.
- **Série A, 2030 : 3–5 M€** (fonds de croissance) pour Windows et AD, l'équipe commerciale et l'Europe.

**Pourquoi lever si le prévisionnel est rentable dès l'année 2 ?** Le pré-seed couvre la perte de l'année 1 (−63 k€). Ensuite, la levée sert à prendre de l'avance : Windows et AD avant la conformité NIS2 (fin 2028), recrutements avant la demande, trésorerie des projets payés à 60 jours.

## 10. Enjeux RSE, chiffrés

| Positif (mesuré) | Négatif (estimé) |
|---|---|
| 28 s de coupure à la bascule, au lieu d'un arrêt prolongé | ≈ 0,6 Wh par test de reprise (3 min 34 s de VM, 1 cœur Xeon à 10,5 W) |
| 0 octet de donnée client envoyé hors de son infrastructure (modèle local) | ≈ 2 Wh de calcul IA par audit (69 s sur un processeur de 105 W) |
| 139/176 écarts reproduits par le code, le reste au coffre, aux sauvegardes ou à l'humain : la reprise ne dépend plus d'une personne | 48 Go de mémoire réservés en permanence au modèle ; serveur existant, sans achat de matériel |

**Notre vision :** faire de la preuve de reprise un contrôle aussi régulier qu'une sauvegarde : « nous avons testé, l'activité repart en quelques minutes, et nous le vérifions chaque mois », d'abord pour les ETI françaises, puis en Europe.
