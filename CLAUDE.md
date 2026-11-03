# Black Start : contexte pour Claude Code

Projet du Challenge Projets d'Entreprendre 2026 (IMT-BS, Télécom SudParis, ENSIIE).
Le nom « Black Start » est proposé et reste à confirmer par l'équipe.

**Pitch :** quand tout s'arrête, Black Start prouve que votre entreprise sait repartir.

## À lire, dans cet ordre

1. `docs/01-projet.md` : problème, cible, solution, offre et décisions prises.
2. `docs/02-attendus-challenge.md` : dates, rendus, barème et consignes du jury.
3. `docs/03-spec-prototype.md` : périmètre, architecture et critères de réussite.
4. `docs/04-marche-et-sources.md` : faits sourcés, hypothèses et limites.
5. `TODO.md` : planning de l'équipe, état au lundi 2 novembre 2026 à 17h14.
6. `docs/Attendus_du_Challenge.pdf` : support officiel, qui fait foi.

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
  | 1603 | `bs-ia` | 192.168.103.204/24 | Modèle local : Ollama + `qwen3.6:35b` (1 socket × 10 cœurs host, nœud NUMA 1 `preferred`, 24 Go, 80 Go, sans GPU, sans onboot). API `:11434` ouverte au poste (.121) et à la forge seulement (pare-feu Proxmox). SSH autorisé par Théo le 3 novembre |

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
- `rapport/bs-rapport` : page de rapport de reprise (score, preuve CI, bascule, décisions) générée depuis les résultats réels ; config `rapport/vms.json`, sortie `rapport/sortie/index.html`, `--fragment` pour l'artifact publié (https://claude.ai/artifact/4BYpgZ3ms6AnwWwUXMjemH). Formule du score à valider par l'équipe.
- `infra/bs-decider.py <vm> --par <nom> [--depuis F]` : décision humaine sur chaque inconnu, proposition du modèle affichée, puis `bs-mr.sh` (code régénéré, MR à jour, CI). Démo « premier audit » : `BS_A_ZERO=1 BS_OLLAMA=http://192.168.103.204:11434 infra/bs-mr.sh bs-logistique` remet les décisions sur les inconnus à zéro ; décisions de Théo gardées dans `infra/demo/decisions-bs-logistique.json`.
- `infra/bascule.py vers-copie|retour` : bascule de production vers la copie vérifiée (refuse si la CI de la dernière MR n'est pas verte), mesure la coupure dans `banc/resultats/bascule-*.json`.
- `banc/` : test métier de bout en bout (`test-metier.py`), mesure du banc de pièges (`mesure.py`), résultats dans `banc/resultats/`.
- `inventaires/` (ignoré par Git) : `*-vierge.json` = état du template, référence à ne pas écraser ; `*-services.json` = après installation des services ; `bs-logistique-pieges.json` = après les pièges.
