# Executive Summary — Black Start

**Équipe n° 16 — Challenge Projets d'Entreprendre 2026**  
IMT-BS / Télécom SudParis / ENSIIE  
**Membres :** Théo (MiNET 1), Titouan (MiNET 2), Benjamin (Ingé 3), Maxime (Ingé 4), Glenn (Manager)  
**Coaching :** rue Étoile | **Démo :** VM sur `luna.minet.lan` (Proxmox) | **Forge :** Forgejo sur `bs-gitlab` (192.168.103.203)

---

## 1. Problème : les sauvegardes existent, la reprise non

Trop d'ETI industrielles et logistiques dépendent de serveurs configurés à la main, peu documentés, que plus personne n'ose toucher. Elles ont des sauvegardes, mais **aucune preuve** qu'elles sauraient redémarrer après une panne, un rançongiciel ou le départ de l'administrateur.

- **Coût moyen déclaré d'une cyberattaque pour une ETI : 13 M€** (enquête ANSSI/CLUSIF citée par le Sénat, 2024).
- **6 800 ETI en France** (ministère de l'Économie, 2022), dont une fraction significative en logistique/industrie avec parc on-premise ou hybride.
- **NIS2 / loi Résilience** : ~15 000 entités concernées, conformité complète visée fin 2028 (ANSSI) — mais la directive ne garantit pas la capacité technique de reprise.

**Ce que le marché vend aujourd'hui :**
- Sauvegarde et restauration vérifiée (Veeam, Rubrik…) — *ne teste pas le processus métier*.
- IaC depuis l'existant (Firefly, ControlMonkey, formae) — *ciblé cloud/K8s, pas l'intérieur des VM on-premise*.
- Cabinets de PRA / ESN — *intervention humaine, non répétable, coûteux*.

**Notre différenciation :** la **preuve de bout en bout** — repartir des sauvegardes existantes, reconstruire ce qui doit l'être, vérifier que le métier fonctionne (commande logistique, envoi mail, résolution DNS).

---

## 2. Solution : Black Start, la preuve de reprise automatisée

**Promesse :** « Vos sauvegardes existent. Nous prouvons que votre activité peut réellement repartir, et nous corrigeons ce qui l'en empêche. »

### Le prototype fonctionne (mesures réelles, labo MiNET, 3 nov. 2026)

| Indicateur | Résultat | Source |
|------------|----------|--------|
| **Reconstruction vérifiée** (VM neuve → code → données → redémarrage → test métier → comparaison) | **233–258 s** (≈ 4 min) | CI Forgejo, MR n° 2–5 |
| **Coupure de service à la bascule** vers la copie vérifiée | **27–29 s** (3 mesures) | `banc/resultats/bascule-*.json` |
| **Détection des pièges du banc** (crons oubliés, config modifiée, binaire `/opt`, IP en dur, sauvegarde mensuelle…) | **10 / 10** | `banc/resultats/mesure-20261103-1015.json` |
| **Classement `bs-logistique`** | 175 écarts : 139 compris, 19 ignorés, 7 secrets, 4 données, **6 inconnus** (5 réels) | `classement/bs-classify` |
| **Modèle local (Qwen 3.6 35B, Ollama, 10 cœurs, 24 Go, sans GPU)** | Proposition 5 inconnus en **78–91 s**, 6,5 tok/s | Journal prototype |
| **Accord modèle / décision humaine** | **0 / 5** identique — le modèle formule la question, ne décide pas | Journal prototype |

### Architecture en 4 niveaux

| Niveau | Question | Action | Rôle de GitLab |
|--------|----------|--------|----------------|
| 1. **Prouver** | Peut-on redémarrer, et en combien de temps ? | Restauration en sandbox isolée, tests métier, rapport + chrono | Quasi nul |
| 2. **Combler** | Que manque-t-il ? | Dépendances, secrets, étapes manuelles, VM non reproductibles | Documentation versionnée |
| 3. **Reconstruire** | Peut-on repartir d'un système sain ? | VM critiques recréées depuis le code, données issues des backups | **Central** |
| 4. **Maintenir** | Est-ce encore vrai ce mois-ci ? | Test de reprise régulier, détection de dérive | **Central** |

### Parcours pour une VM (démo scénario B)

1. **Collecte lecture seule** (script déterministe, compte `bs-collect`, secrets masqués avant tout envoi).
2. **Classement** : chaque élément → *Compris / Donnée / Secret / Ignoré / Inconnu* (preuves déterministes ; IA propose un statut indicatif).
3. **Validation humaine** des inconnus (interface web, 5 inconnus réels sur `bs-logistique`).
4. **Génération** Ansible + CI/CD dans une branche GitLab → reconstruction en sandbox isolée (`sbx-*`, pare-feu d'isolation).
5. **Vérification** : même collecte sur la copie, comparaison inventaires + test métier (création commande logistique).
6. **Rapport d'écarts + Merge Request** → relecture admin → **bascule** (DNS, proxy, base, mail réel) en **< 30 s** — retour arrière possible en **~31 s**.

**Garanties :** aucun secret n'atteint le modèle ni Git (testé) ; la bascule est refusée si la CI n'est pas verte (vérifié en démo) ; les « inconnus » ne sont jamais appliqués sans décision humaine.

---

## 3. Business Model : cabinet de conseil équipé de son propre outil

| Offre | Description | Cible | Tarification (hypothèses, à valider) |
|-------|-------------|-------|--------------------------------------|
| **Audit** | 1 semaine lecture seule → cartographie + score de reconstructibilité sur 5–10 apps critiques | DSI / RSSI | ~15–25 k€ |
| **Migration** | Reconstruction des VM critiques au forfait (code + tests + bascule) | DSI / RSSI | ~30–60 k€ / VM |
| **Abonnement** | Détection de dérive, test de reconstruction mensuel, rapport de reprise | DSI / RSSI | ~2–5 k€ / mois / app |

**Déclencheurs d'achat validés par hypothèses :** audit client, renouvellement cyberassurance, incident récent, test de reprise imposé. NIS2 = argument secondaire.

**Cible principale :** ETI françaises industrielles/logistiques (petit service IT, parc on-premise/hybride). Acheteur : DSI ou RSSI, dirigeant sponsor. Canal secondaire : infogérants.

**Concurrence détaillée (3+ acteurs) :**
- **Firefly** (cloud resilience, 23 M$ levés 2024) — ne couvre pas l'intérieur des VM on-premise.
- **ControlMonkey** (Terraform from existing, 7 M$ seed 2025) — orienté cloud/IaC, pas preuve métier.
- **formaé** (IaC open source, découverte existant) — pas de sandbox, pas de test métier, pas de bascule.
- *Indirects :* Veeam/Rubrik (restauration seule), ESN/cabinets PRA (humain, non répétable), agents de code généralistes (accès SSH, pas de garantie).

**Hypothèse SAM :** 6 200 ETI × 25 % secteurs pertinents × 40 k€/an ≈ **62 M€/an** (à affiner post-entretiens : Insee secteurs visés + budgets réels).

**Objectif jury :** **700–800 k€ CA en année 5** ≈ 20 clients à 40 k€/an.

---

## 4. Go-to-Market & Planning 5 ans (macro)

| Année | Focus | Effectif visé | Jalons |
|-------|-------|---------------|--------|
| **1** (2027) | Produit + premiers clients | 3 consultants + 2 ingénieurs | 3 audits payants, 1 migration, MVP abonnement |
| **2** | Répétabilité + partenariats infogérants | +2 consultants | 10 clients abonnement, CA ~300 k€ |
| **3** | Industrialisation outil (Windows/AD, observation longue eBPF) | +3 consultants, +1 ingénieur | CA ~500 k€ |
| **4** | Scale commercial, offre packagée | +5 consultants | CA ~650 k€ |
| **5** | **Objectif : 700–800 k€ CA**, équipe ~15 | | Rentabilité, levée possible pour accélérer |

**Acquisition :** prospection ciblée (DSI/RSSI ETI logistique/industrie), webinaires « test de reprise réel », contenu technique (blog, démo), partenariats infogérants. CAC visé < 6 mois de marge.

---

## 5. Finance & Besoins

**Modèle :** revenus récurrents (abonnement) + projets (audit/migration). Marge brute visée > 70 % sur l'abonnement, > 50 % sur les projets.

**Besoins année 1–2 (estimation) :**
- Salaires (5 puis 7–8) : ~400–600 k€/an
- Infra (labo, cloud CI, GPU éventuel) : ~30 k€/an
- Commercial / marketing : ~50 k€/an
- **Besoin de trésorerie ~500–600 k€ sur 18–24 mois**

**Sources envisagées :** amorçage (business angels, BPI French Tech Grant), puis levée Seed en année 2–3 si traction. Pas de dilution prématurée : l'outil réduit le coût de livraison, pas le besoin d'expertise.

---

## 6. Enjeux RSE (impact mesurable)

| Positif | Négatif (atténuation) |
|---------|----------------------|
| **Résilience économique** : évite arrêts prolongés (coût médian cyberattaque ETI 13 M€) | **Conso électrique** : modèle local (Qwen 35B, 10 cœurs, 24 Go) ~200 W en inférence ; sandbox éphémère |
| **Transmission du savoir** : code versionné, décisions tracées, moins de dépendance aux personnes | **Matériel** : VM de démo sur serveur existant (Dell R630, pas d'achat neuf) |
| **Souveraineté** : modèle local interchangeable (Devstral option souveraine testée), pas de cloud obligatoire | **Données** : secrets jamais sortis, masqués avant modèle, coffre sur forge isolée |
| **Emploi qualifié** : consultants + ingénieurs en France | — |

**Indicateur suivi :** kWh / reconstruction (mesuré sur le labo), % de VM reconstruites sans intervention manuelle non documentée.

---

## 7. Vision long terme

Devenir **la référence de la preuve de reprise** pour les ETI françaises : l'outil qui transforme « on a des backups » en « on a testé, ça repart en 4 minutes, et on le refait tous les mois ». Étendre au Windows/AD, aux équipements réseau, à l'observation longue (eBPF/auditd) — mais **sans jamais promettre 100 %** : « Tout ce qui n'est pas expliqué vous est signalé, et ce qui a été reconstruit a été testé. »

---

**Prototype gelé jeudi 5 novembre midi. Démo vivante vendredi 6 novembre (bâtiment F). Vidéo de secours enregistrée.**