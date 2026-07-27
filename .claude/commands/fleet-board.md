---
description: Telemetrie CONTEXTE de la flotte d'agents -- jauges d'occupation, vitesse hors socle, echeance de saturation
---

Lance depuis la racine du repo :

```
python scripts/python/fleet_board.py $ARGUMENTS
```

Passe `--open` pour ouvrir la page dans le navigateur, `--all` pour inclure les agents terminés.
Sans argument : table console + écriture de `logs/fleet-board.html` (gitignoré).

**Puis republie l'artefact partagé**, pour que le lien ne soit jamais périmé — il y a DEUX boards,
et régénérer le fichier local ne met pas à jour celui de claude.ai :

- outil `Artifact`, `file_path` = le HTML qui vient d'être écrit (`logs/fleet-board.html`, ou le
  chemin passé via `-o`) ;
- `url` = `https://claude.ai/code/artifact/5572fbd1-7257-4444-9bac-f451d8fd9037` — **toujours cette
  URL**, sinon une nouvelle est créée à chaque fois et l'ancienne se fige ;
  (l'URL précédente `9c22449f-…` est MORTE : un `/login` a rebasculé sur un compte qui ne possède
  pas l'artefact, et un artefact ne se récupère pas — il se republie, donc le lien change.)
- `favicon` = `🛩️` (le garder stable : l'utilisateur retrouve son onglet à son icône).

Puis **rends compte en quelques lignes**, sans recopier la table entière — elle est déjà à l'écran.
Ce qui vaut d'être dit :

- **qui doit atterrir en premier** : l'agent dont l'échéance de saturation est la plus proche ;
- **un agent dont la vitesse s'est effondrée** par rapport aux autres — souvent le signe qu'il tourne
  en rond ou attend un runner, pas qu'il travaille lentement ;
- **le nombre d'agents en vol vs le plafond** (15 depuis le 2026-07-27), et s'il reste des slots.

Rappels de lecture, pour ne pas mal interpréter les chiffres :

- La colonne `contexte` est l'**occupation de la fenêtre** (`input + cache_creation + cache_read` de
  la dernière requête), **pas** la somme des tokens facturés — celle-ci compte N fois le même
  contexte relu et vaut ~40× plus.
- `tok/min` **retranche le socle système** (~55 K : prompt, outils, `CLAUDE.md`, brief). Sans cette
  soustraction un agent lancé il y a deux minutes afficherait une vitesse énorme sans avoir rien lu.
- **Trois états, et aucun ne se lit sur le verrou du worktree.** « En vol » = a écrit dans son
  transcript il y a moins de 15 min. « EN ATTENTE » = silencieux **mais son worktree existe encore**
  — arrêté, reprenable par `SendMessage` avec son contexte intact. « Fini » = plus de worktree,
  masqué sauf `--all`.
  Ne pas revenir au `git worktree lock` : il n'est posé qu'au **lancement**, jamais par une reprise
  via `SendMessage` — le critère devient donc aveugle dès la première reprise, et il l'est
  *silencieusement* (tout le monde s'affiche « fini »). Mesure du 2026-07-27 : 0 verrou sur 15 agents
  dont 8 travaillaient.
- L'état « EN ATTENTE » dit « worktree conservé », **pas** « travail à reprendre » : un agent dont la
  PR est déjà mergée y figure aussi, en attendant son nettoyage. Pour trancher, regarder si sa
  branche est déjà dans `origin/master`.

Pour rafraîchir : relancer la commande, puis recharger l'onglet. La page ne peut pas se recalculer
seule — elle est publiée sur claude.ai, sandboxée, et les transcripts sont des fichiers locaux.
