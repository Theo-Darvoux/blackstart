# Marché et sources

Recherches rapides du 2 novembre 2026, à vérifier sur les sources primaires avant tout rendu. Certaines sources sont secondaires ou commerciales.

## Faits relevés

### ETI

- France : 6 218 ETI en 2021 (Insee, secteurs marchands non agricoles et non financiers) : https://www.insee.fr/fr/statistiques/7678536
- 6 800 ETI en 2022 selon le ministère de l'Économie : https://www.entreprises.gouv.fr/files/files/Publications/2025/Th%C3%A9mas/20250516-thema-29-ETI.pdf
- Coût moyen déclaré d'une cyberattaque : 13 M€ pour une ETI et 466 k€ pour une TPE/PME, selon une enquête de l'ANSSI auprès du CLUSIF citée par le Sénat : https://www.senat.fr/rap/l24-393/l24-393-syn.pdf . Chiffre déclaratif, toutes ETI confondues.

### NIS2 et loi Résilience

- Non transposée en France en octobre 2026 ; retirée de l'ordre du jour de l'Assemblée les 7 et 9 octobre : https://www.myrasecurity.com/fr/savoir/nis2-loi-resilience/
- Environ 15 000 entités concernées, et saisine de la CJUE contre la France : https://www.silicon.fr/cybersecurite-1371/nis2-ce-quil-faut-attendre-du-projet-de-loi-examine-a-lassemblee-nationale-229520 et https://nis-solutions.eu/countries/france/
- L'ANSSI envisagerait une conformité complète fin 2028 : https://aocsi.fr/blog/loi-resilience-transposition-nis2
- ReCyF publié par l'ANSSI le 17 mars 2026 : https://nis2-pro.fr/loi-resilience

### Secteurs voisins

- Programme CaRE, volet continuité et reprise d'activité doté de 45 M€ pour la santé : https://esante.gouv.fr/espace-presse/ouverture-du-guichet-de-depot-de-lappel-financement-du-programme-care-dedie-la-strategie-de-continuite-et-de-reprise-dactivite
- Près de 1 500 collectivités et organismes visés par le projet de loi : https://www.senat.fr/rap/l24-393/l24-393-syn.pdf

### Sauvegardes et reprise (sources ajoutées le 5 nov.)

- Sophos, *The Impact of Compromised Backups on Ransomware Outcomes* (enquête Vanson Bourne début 2024, 2 974 répondants) : 94 % des victimes de rançongiciel disent que l'attaquant a tenté de compromettre leurs sauvegardes ; 57 % des tentatives réussissent ; 26 % des victimes aux sauvegardes compromises se rétablissent en une semaine, contre 46 % ; coût médian de reprise 3 M$ contre 375 k$ : https://www.sophos.com/en-us/blog/the-impact-of-compromised-backups-on-ransomware-outcomes
- Veeam, *Ransomware Trends Report 2025* (communiqué du 23 avril 2025, 1 300 organisations) : 69 % touchées en un an ; 10 % récupèrent plus de 90 % de leurs données, 57 % moins de la moitié : https://www.veeam.com/company/press-release/veeam-report-finds-close-to-70-percent-of-organizations-still-under-cyber-attack-despite-improved-defenses.html
- Veeam : 1,7 Md$ de revenus récurrents annuels en septembre 2024, valorisation de 15 Md$ (GeekWire, déc. 2024) : https://www.geekwire.com/2024/veeam-software-which-recently-relocated-its-hq-to-the-seattle-area-reaches-15b-valuation/
- Marchés de référence : DRaaS 13,7 Md$ (2025) → 24,1 Md$ (2030), Mordor Intelligence ; IaC 1,3 Md$ (2025) → 6,9 Md$ (2034), Fortune Business Insights ; cybersécurité France 9,1 Md$ (2025), Mordor Intelligence. Estimations de cabinets, très variables selon le périmètre.
- Chiffres retirés faute de source : « coût d'1 h d'arrêt d'une ETI : 10–50 k€ », « 5–6 % des ETI utilisent l'IA défensive (OCDE) », « < 5 % des PME assurées », « 160 000 PME de plus de 50 salariés ».

## Concurrence à creuser

Le jury veut au moins 3 acteurs détaillés.

| Acteur | Ce qui a été relevé | Source |
|---|---|---|
| Firefly | Codification et résilience du cloud ; 23 M$ levés en 2024 | https://techcrunch.com/2024/05/29/after-co-founders-murder-at-the-hands-of-hamas-cloud-startup-firefly-raises-23m et https://firefly.ai/llms.txt |
| ControlMonkey | Terraform automatisé depuis l'existant ; 7 M$ en seed, janvier 2025 | https://www.cbinsights.com/company/controlmonkey/financials |
| formae | IaC open source avec découverte et codification de l'existant | https://scuttle.klotz.me/bookmarks/klotz/iac |
| VMShift (Mechanized AI) | Conversion de VM en conteneurs par IA | https://builtincalgary.org/company/mechanized-ai |

**À vérifier, non sourcé ici :** Veeam et les éditeurs de sauvegarde, dont les restaurations automatiques vérifiées sont connues mais n'ont pas été recherchées pour ce dossier.

Autres concurrents indirects : agents de code généralistes avec accès SSH, ESN, cabinets de PRA, éditeurs de sauvegarde.

**Hypothèse de différenciation :** ces acteurs couvrent surtout le cloud et Kubernetes, ou la restauration seule. L'intérieur des VM on-premise et la preuve métier de bout en bout semblent moins couverts. Ce tour d'horizon n'est pas exhaustif.

## Modèles locaux

- Comparatif Qwen, Kimi et Gemma : https://www.dsebastien.net/kimi-k2-6-qwen-and-gemma-4-local-ai-is-catching-up/
- Kimi K3 (2 800 milliards de paramètres) trop lourd pour ce cas : https://shop.zimaspace.com/blogs/tech-ai-hub/open-models-vs-frontier-ai-local-ai-good-enough-2026
- LLM de code locaux, dont Devstral : https://chatboq.com/blogs/best-local-llm-for-coding

Prévoir une réponse sur l'origine chinoise de Qwen, même exécuté en local. Vérifier la licence et le matériel réel.

## Hypothèses, à remplacer

Ces chiffres sont des suppositions de travail, pas des faits :

Chiffres retenus le 3 novembre dans `analyse-marche-blackstart.md`, repris tels quels par le deck, la landing et l'executive summary :

- **TAM :** 6 800 ETI × 55 k€ de budget résilience ≈ 374 M€ par an (55 k€ : hypothèse).
- **SAM :** ~2 600 ETI industrielles et logistiques × 40 % avec un parc Linux (hypothèse) ≈ 1 040 ETI × 50 k€ ≈ 52 M€ par an. 2 100 ETI industrielles : Insee Première n° 2084, déc. 2025, données 2023 (https://www.insee.fr/fr/statistiques/8673351). 500 ETI de transport et d'entreposage : estimation, 7,4 % des effectifs des ETI (Insee, Ésane 2021, https://www.insee.fr/fr/statistiques/7678536) appliqués aux 6 800 ETI.
- **SOM année 5 :** 45 clients sous abonnement (~4 % du SAM), 2,07 M€ de CA (prévisionnel de l'analyse de marché, tarifs du 5 nov. : audit 15–25 k€, migration 30–60 k€ par VM, abonnement 2–5 k€ par mois et par application).

Ancienne hypothèse, abandonnée : 6 200 ETI × 25 % × 40 k€ ≈ 62 M€. Remplacer la part Linux et les budgets par ce qu'entendent les entretiens.

## Preuves encore manquantes

Aucune donnée d'entretien n'est disponible dans ce dossier. Objectifs : 6 vrais échanges d'ici mercredi et des marques d'intérêt écrites. Questions : dernier test de reprise complet, durée réelle, part Linux/Windows, budget, déclencheur d'achat.

Seuils de lecture proposés, à ajuster à ce volume d'entretiens : une majorité sans test de reconstruction complet depuis un an, au moins une marque d'intérêt écrite, et une part Linux suffisante sur les applications critiques.
