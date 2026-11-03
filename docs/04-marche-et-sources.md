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

- **SAM indicatif :** 6 200 ETI × 25 % de cibles pertinentes × 40 k€ par an ≈ 62 M€ par an.
- **Lecture du seuil du jury :** à 40 k€ par client, 700 à 800 k€ de CA correspondent à environ 20 clients en année 5.

Remplacer le 25 % par le nombre d'ETI des secteurs visés (données Insee) et le 40 k€ par les budgets entendus en entretien. Un TAM et un SOM restent à construire.

## Preuves encore manquantes

Aucune donnée d'entretien n'est disponible dans ce dossier. Objectifs : 6 vrais échanges d'ici mercredi et des marques d'intérêt écrites. Questions : dernier test de reprise complet, durée réelle, part Linux/Windows, budget, déclencheur d'achat.

Seuils de lecture proposés, à ajuster à ce volume d'entretiens : une majorité sans test de reconstruction complet depuis un an, au moins une marque d'intérêt écrite, et une part Linux suffisante sur les applications critiques.
