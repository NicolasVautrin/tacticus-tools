---
description: Telemetrie CONTEXTE de la flotte d'agents -- jauges d'occupation, vitesse hors socle, echeance de saturation
---

Lance depuis la racine du repo :

```
python scripts/python/fleet_board.py $ARGUMENTS
```

Passe `--open` pour ouvrir la page dans le navigateur, `--all` pour inclure les agents terminés.
Sans argument : table console + écriture de `logs/fleet-board.html` (gitignoré).

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
- « En vol » se lit sur le **verrou** du worktree : un agent terminé garde le sien jusqu'au nettoyage.

Pour rafraîchir : relancer la commande, puis recharger l'onglet. La page ne peut pas se recalculer
seule — elle est publiée sur claude.ai, sandboxée, et les transcripts sont des fichiers locaux.
