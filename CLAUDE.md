# Black Start : contexte pour Claude Code

Projet du Challenge Projets d'Entreprendre 2026 (IMT-BS, Télécom SudParis, ENSIIE).
Le nom « Black Start » est proposé et reste à confirmer par l'équipe.

**Pitch :** quand tout s'arrête, Black Start prouve que votre entreprise sait repartir.

## À lire, dans cet ordre

1. `docs/01-projet.md` : problème, cible, solution, offre et décisions prises.
2. `docs/02-attendus-challenge.md` : dates, rendus, barème et consignes du jury.
3. `docs/03-spec-prototype.md` : périmètre, architecture et critères de réussite.
4. `docs/04-marche-et-sources.md` : faits sourcés, hypothèses et limites.
5. `docs/05-mesures.md` : chiffres mesurés du prototype, avec leur source (à citer dans les rendus).
6. `TODO.md` : planning de l'équipe, état au lundi 2 novembre 2026 à 17h14.
7. `docs/Attendus_du_Challenge.pdf` : support officiel, qui fait foi.

## Priorités

Échéances : executive summary sur Moodle **jeudi 5 novembre avant 9h**, gel du prototype jeudi midi, oral **vendredi 6 novembre**.

Le prototype est le critère le plus lourd (8 points sur 20). Il doit produire une démo réelle et des mesures réelles. Une démo simple qui marche vaut mieux qu'une architecture complète qui ne marche pas.

## Règles de travail

- **Ne jamais inventer** d'entretien, de citation, de marque d'intérêt, de client ou de résultat de mesure. Un chiffre non mesuré est présenté comme une hypothèse.
- **Citer les sources** de tout fait externe. Revérifier ce qui évolue, surtout NIS2 et la loi Résilience, avant de l'écrire dans un rendu.
- **Ne pas livrer un contenu générique.** Le support officiel prévient : « Travail basique réalisé via IA = mauvaise note ». Appuyer le dossier sur les entretiens et les mesures de l'équipe.
- **Rester dans le laboratoire.** Ne rien exécuter sur une production, ni sur l'infrastructure MiNET sans accord explicite. Les actions destructives ne visent que les VM de démo, et uniquement après confirmation.
- **Protéger les secrets.** Ne jamais commiter de secret. Les secrets sont masqués avant tout passage au modèle.
- **L'IA ne modifie pas directement la production simulée.** Elle agit dans la sandbox et propose ses changements par merge request.
- **Déterminisme d'abord.** Collecte et tests sont des scripts ; le modèle interprète, propose et rédige.
- **Questions d'équipe.** Si une décision change le fond du projet, la cible ou le périmètre, la poser à Théo au lieu de la trancher.

## Informations confirmées par Théo (2 novembre 2026)

- **Projet :** Black Start, nom confirmé. **Équipe n° 16** (salle de coaching : rue Étoile).
- **Équipe :** MiNET 1 = Théo, MiNET 2 = Titouan, Ingé 3 = Benjamin, Ingé 4 = Maxime, Manager = Glenn.
- **Machine de démo :** autant de VM Debian 13 que nécessaire sur `luna.minet.lan`. C'est l'infrastructure MiNET : Claude Code ne s'y connecte pas (ni `ssh`, ni `scp`, ni `rsync`) ; il fournit les commandes et Théo les lance.
- **Forge :** Forgejo sur `bs-gitlab` (http://192.168.103.203:3000). Exception accordée par Théo : Claude Code peut y committer, pousser, créer dépôts et merge requests. Partout ailleurs, la règle globale reste (ni commit ni push).
- **Entretiens :** aucun mené pour l'instant. Aucun chiffre ni verbatim d'entretien ne doit apparaître dans un rendu tant qu'il n'existe pas.
- **`../pitch.txt` :** idée abandonnée (passation des accès, ancien « Relais »). Ne pas l'utiliser.

- **Hyperviseur :** `luna.minet.lan` tourne sous Proxmox.
- **VM créées** (préfixe `bs-`, VMID 16xx). Réseau `192.168.103.0/24` (MiNET). Claude Code y a accès en SSH (règle globale), mais se limite aux 5 VM ci-dessous et aux sandbox `sbx-*` (`192.168.103.210` à `.219`) ; jamais en SSH sur luna (**`192.168.103.59`**, `luna.minet.lan`, `luna.minet.net`) ni sur les autres machines du réseau (DNS `.54`/`.55`, passerelle `.250`, `.171`…). Luna n'est joignable que par l'API Proxmox avec le jeton `blackstart@pve!claude` (`infra/pve.py`, secrets dans `infra/secrets/proxmox.env`), limité au pool `blackstart`, expiration le 10 novembre 2026. Les noms ne sont pas résolus par DNS : toujours désigner une VM par son IP dans les commandes et les scripts.

  | VMID | Nom | IP | Rôle |
  |---|---|---|---|
  | 1600 | `bs-logistique` | 192.168.103.200/24 | Logiciel de logistique (VM détruite puis reconstruite en démo) |
  | 1601 | `bs-mail` | 192.168.103.201/24 | Postfix + Dovecot |
  | 1602 | `bs-proxy` | 192.168.103.202/24 | Nginx + DNS |
  | 1690 | `bs-gitlab` | 192.168.103.203/24 | GitLab + runner |
  | 1603 | `bs-ia` | 192.168.103.204/24 | Modèle local : Ollama + `qwen3.6:35b` (1 socket × 10 cœurs host, nœud NUMA 1 `preferred`, 48 Go depuis le passage de luna à 128 Go le 3 nov., 80 Go de disque, sans GPU, sans onboot). API `:11434` ouverte au poste (.121) et à la forge seulement (pare-feu Proxmox). SSH autorisé par Théo le 3 novembre |

  Une Debian 13 vierge de référence existe déjà sous un autre nom (nom à préciser). Les copies reconstruites en sandbox s'appelleront `sbx-*`.

  Les VM sont des clones du template MiNET `debian13-template` (ifupdown, sssd, DNS MiNET `192.168.103.54`/`.55`). Au clonage, IP, hostname, clés d'hôte SSH et machine-id restent ceux du template (`192.168.103.171`) : tout nouveau clone doit être corrigé avant usage. Accès : compte `psders` + `sudo` (pas de root SSH) ; collecte par le compte `bs-collect` avec la clé `~/.ssh/id_blackstart` ; administration par Claude Code avec le compte `claude` (sudo sans mot de passe) et la clé `~/.ssh/id_blackstart_admin`.

Restent inconnus : ressources de `luna.minet.lan` (CPU, RAM, GPU).

## Code

- `collecte/` : collecte déterministe en lecture seule d'une VM Debian (`bs-collect`) et comparaison de deux inventaires (`bs-compare`). Voir `collecte/README.md`.
- `pme/` : mise en scène de la PME fictive (services, sauvegardes, pièges). Voir `pme/README.md`. **Ne jamais donner ce dossier ni `banc/pieges.json` au modèle de l'outil** : ce sont les réponses du banc.
- `classement/bs-classify` : classe les écarts référence → courant (compris, donnée, secret, ignoré, inconnu) avec une règle et une preuve par élément ; liste les IP d'autres machines écrites en dur. `--preuves` montre ce qui partirait au modèle ; `--proposer http://192.168.103.204:11434 --propositions F` lui fait proposer un statut par inconnu (indicatif, mis en cache ; `BS_OLLAMA=… infra/bs-mr.sh <vm>` l'affiche dans `DECISIONS.md`).
- `infra/forge/` : installation de Forgejo + runner sur `bs-gitlab` (secrets dans `infra/secrets/`, ignoré par Git).
- `generation/bs-generate` : inventaire `--with-content` + classement → `depot/<vm>/` (playbook Ansible, `restauration.yml`, `DECISIONS.md`, `coffre.txt`). Déterministe ; les « inconnus » ne sont jamais appliqués.
- `infra/sandbox.py` (VM `sbx-*`, VMID 1650–1659, IP .210–.219, pare-feu d'isolation), `infra/coffre.sh` (secrets vers `/srv/coffre/<vm>` sur `bs-gitlab`, lisible par le runner seul), `infra/rebuild.sh` (Ansible depuis `bs-gitlab`), `infra/demo-reconstruction.sh` (parcours complet chronométré, ~212 s).
- **Journal du prototype** (Claude Docs, à tenir à jour au fil du travail) : https://claude.ai/artifact/WkkoWpocFpR39CXRbhL8tS
- `rapport/bs-rapport` : page de rapport de reprise générée depuis les résultats réels, calquée sur la diapo « Le livrable » (refaite le 4 nov.) : 4 blocs verdict, chrono, risques, preuve pour la 1re VM de `vms.json`, puis une ligne par VM du parc. Preuve retenue : dernière vérification CI verte partie d'une VM vide, toutes MR de la branche confondues ; une vérification plus récente non verte est signalée. Capture de la diapo : `oral/source/img/rapport.jpg` ; config `rapport/vms.json`, sortie `rapport/sortie/index.html`, `--fragment` pour l'artifact publié (https://claude.ai/artifact/4BYpgZ3ms6AnwWwUXMjemH).
- `infra/bs-decider.py <vm> --par <nom> [--depuis F]` : décision humaine sur chaque inconnu, proposition du modèle affichée, puis `bs-mr.sh` (code régénéré, MR à jour, CI). Démo « premier audit » : `BS_A_ZERO=1 BS_OLLAMA=http://192.168.103.204:11434 infra/bs-mr.sh bs-logistique` remet les décisions sur les inconnus à zéro ; décisions de Théo gardées dans `infra/demo/decisions-bs-logistique.json`. La console pré-remplit la raison selon le bouton cliqué (« Garder » = `reproduire`, « Retirer » = `ne pas reproduire`) depuis `infra/demo/raisons-bs-logistique.json`, une raison par choix.
- `infra/demo-scenario-b.sh --par <nom> [--repetition] [--cache] [--sans-bascule] | --preparer` : démo chronométrée du scénario B (audit en direct, MR, CI rouge, refus de bascule, décisions, CI verte, bascule, retour), résultats dans `banc/resultats/demo-b-*.json`.
- **Démo de l'oral : `infra/salle/serveur.py --par Théo`** puis http://localhost:8080 en plein écran (F11). Console produit (refaite le 3 nov.) : menu Vue d'ensemble (plan de reprise en 4 lignes, action suivante), Inventaire (176 écarts filtrables, règle et proposition du modèle par élément), Décisions, Merge request (CI 1 bloquée, CI 2 pas à pas), Bascule, Parc (dont IP écrites en dur), Laboratoire (coulisses). Panneau Activité : chaque action est une opération découpée en pas annoncés d'avance (explication, machine, durée, résultat ; classe `Operation` de `serveur.py`), sortie brute des scripts repliée. Laboratoire → « Préparer » 10 min avant (VM, pièges, modèle chargé, sandbox préchauffée `--neuve`, propositions du modèle calculées dans `inventaires/bs-logistique.propositions-preparees.json`), puis Vue d'ensemble → « Lancer l'audit », Décisions → « Valider », Bascule (touche → = action principale de la vue) : audit → MR → CI rouge immédiate → bascule refusée → décisions cliquées dans la page → CI verte suivie étape par étape (lue dans `/srv/bs-ci/<vm>.log` sur bs-gitlab) → bascule chronométrée. Laboratoire → « Remettre en état » après l'oral (retour + pièges). Résultats dans `banc/resultats/demo-salle-*.json`. Mesuré le 3 nov. : 3 min 19 s de bout en bout (décisions rejouées en 7 s). `#capture-<vue>` dans l'URL (ex. `#capture-inventaire`) : état lu une fois, pour les captures d'écran.
- Console en produit client (5 nov.) : accueil = Tableau de bord du parc (statut de reprise, reconstructibilité, reconstruction, données, coupure, dernière preuve par machine ; `bs-logistique` suit la reprise jouée en direct, `bs-mail`/`bs-proxy` leur dernière preuve sur la forge), fiches `#m-bs-mail` / `#m-bs-proxy`, Rapport de reprise intégré, export CSV de l'audit. Données via `/parc` et `/rapport` de `serveur.py` (lecture seule, fonctions de `rapport/bs-rapport`, cache 60 s, page régénérée dans `inventaires/rapport-console.html`). Opérations Préparer/Remettre visibles dans Activité seulement depuis le Laboratoire.
- Intégration d'une machine (5 nov.) : registre du parc `parc/parc.json` (organisation, périmètre autorisé `reseaux`/`exclues`, image de référence, plateforme, machines déclarées ; lu par `serveur.py`, `BS_PARC=` pour un autre fichier). Console : Machines → « Ajouter une machine » (nom, IP dans le périmètre, rôle, criticité), puis fiche `#m-<vm>` : script `/installer/bs-collect-installer.sh` généré (collecteur + `install-on-vm.sh` + clé `id_blackstart.pub`, empreintes vérifiées, déterministe ; testé en conteneur Debian 13), « Vérifier l'accès » (périmètre, empreinte d'hôte enregistrée dans `inventaires/parc/known_hosts` puis exigée, `id` refusé, collecte d'essai), « Lancer le premier audit » (collecte avec contenu, comparaison à l'image de référence avec `collecte/regles/reference.json`, classement), résultats dans `inventaires/parc/<vm>.*`. La preuve de reconstruction d'une nouvelle machine n'est pas déclenchable depuis la console (sauvegarde, test métier, MR : prestation de migration). Vue Paramètres : périmètre, clé, script, référence, plateforme. `rapport/vms.json` reste la liste des machines suivies par le rapport.
- Console, 5 nov. au soir : Paramètres modifiables (organisation, périmètre, image de référence, adresses connues ; `POST /parc/reglages`, refuse un périmètre qui exclurait une machine déclarée ; plateforme et accès en lecture seule) ; fiche machine → « Modifier » (rôle, criticité, IP seulement hors machines prouvées ; `POST /parc/modifier`) ; Infrastructure lit l'état réel via `/joignabilite` (port 22 en TCP, API Forgejo, modèles chargés dans Ollama ; 10 s de cache, 20 s de rafraîchissement). Rapport de reprise refait : `infra/salle/rapport.html` servi à `/rapport?vm=parc|<vm>` (A4, couverture, synthèse, points d'attention, une section par machine avec déroulé, test métier, sauvegarde, décisions, historique des vérifications tiré de `forge_state()["historique"]` de `rapport/bs-rapport`, méthode, sources, validation signée) ; l'ancienne page reste à `/rapport-court`. La lecture de la forge pour `/parc` se fait en arrière-plan passé 60 s. Adresse locale prévue : http://blackstart.local (ligne dans `/etc/hosts` et redirection 80 → 8080, posées par Théo).
- Console, 5 nov. ~23h : mise en page sans cadres (titres, filets, tableaux pleine largeur) ; menu = Tableau de bord, une entrée par machine, Rapport, Infrastructure, Journal, Paramètres, Laboratoire ; chaque machine a une fiche à onglets (bs-logistique : Résumé `#ensemble`, Audit `#inventaire`, Décisions, Preuve `#ci`, Bascule, Accès ; autres : `#m-<vm>`, `#m-<vm>~preuve|decisions|acces|audit`) ; panneau Activité toujours visible à droite (le tiroir a été essayé puis retiré : écran vide à droite) ; dépendances IP dans Infrastructure ; âge de la preuve (« il y a 2 jours ») ; score « non prouvée » pour une machine sans preuve ; Journal des actions (`/journal`, `inventaires/journal-actions.jsonl` : opérations de la console et changements du parc ou des paramètres, avec auteur et résultat). Rapport : points d'attention en tableau.
- Laboratoire → « Réinitialiser les données » (6 nov., `POST /action/labo/reinitialiser`) : archive dans `inventaires/archives/<date>/` les audits et accès du parc, le journal des actions, `decisions-salle-*.json` et une copie de `etat-console.json` ; vide l'état et l'Activité ; ferme les MR ouvertes de `pme/infra` ; écrit `inventaires/remise-a-zero.json`, date avant laquelle `rapport/bs-rapport` (`collect(..., depuis)`) ignore les MR, vérifications et bascules ; une machine de `rapport/vms.json` sans vérification postérieure est montrée par `/parc` comme une machine à intégrer (ni ancien audit, ni décisions, ni score). Rien n'est supprimé sur la forge. « Réafficher l'historique » (`labo/reafficher`) retire cette date ; les fichiers archivés se remettent à la main.
- CI accélérée (3 nov.) : refus immédiat si `attente.json` n'est pas vide (pas de reconstruction, ~2 s) ; `sandbox.py prendre` réemploie une seule fois une sandbox préchauffée marquée `[neuve]`, et `bascule.py` refuse une sandbox encore `[neuve]` ; Ansible en pipelining avec `profile_tasks`.
- `infra/bascule.py vers-copie|retour` : bascule de production vers la copie vérifiée (refuse si la CI de la dernière MR n'est pas verte), mesure la coupure dans `banc/resultats/bascule-*.json`.
- `banc/` : test métier de bout en bout (`test-metier.py`), mesure du banc de pièges (`mesure.py`), résultats dans `banc/resultats/`.
- `infra/bs-mr.sh` copie aussi `inventaires/<vm>-pieges.json` dans `forge/pme-infra/inventaires/<vm>.json` (référence de la comparaison en CI). La CI écrit l'âge de l'instantané restic restauré et alerte s'il est plus vieux que le dernier passage prévu du cron de sauvegarde.
- CI : seule la VM de la branche `reconstruction/<vm>` est vérifiée ; test de santé et test métier selon le rôle (`banc/test-metier.py --role mail|proxy --cible IP`) ; collecte avant le test métier ; `attente.json` (décisions en attente, dont les données sans sauvegarde) bloque la MR. Pare-feu des sandbox : REJECT vers le LAN.
- Après un redémarrage (ou une bascule) de `bs-logistique`, les pièges à chaud (P6 swappiness, P8 relais :9100) disparaissent : `pme/deploy.sh pieges` les repose avant un audit.
- `inventaires/` (ignoré par Git) : `*-vierge.json` = état du template, référence à ne pas écraser ; `*-services.json` = après installation des services ; `bs-logistique-pieges.json` = après les pièges.
