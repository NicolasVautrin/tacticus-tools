# #480-r11 — `git worktree remove` désenregistre AVANT d'échouer, et laisse un orphelin

**Statut : FERMÉ.** Cliquet `probe_480r11_worktree_orphelin.py` (banque, `probe_480r11`).
Résidu ouvert : aucun.

## 1. Le fait, DÉMONTRÉ (pas cité)

Reproduit dans un dépôt git synthétique (`probe_480r11` étape 1, tmpdir système), avec un fichier
ignoré dont le chemin fait **314 caractères** :

| | `core.longpaths` absent | `core.longpaths true` |
| --- | --- | --- |
| `git worktree remove --force` | **rc=255**, `Filename too long` | **rc=0** |
| répertoire | **reste sur disque** | supprimé |
| entrée admin (`git worktree list`) | **DÉJÀ RETIRÉE** | retirée |
| `.git/worktrees/<id>` | **n'existe plus** | n'existe plus |

Le mode de panne est le pire possible : git retire l'entrée administrative **avant** d'échouer sur
les fichiers. Il en résulte un répertoire que git ne connaît plus, et un `remove` ultérieur rend
`rc=128` — l'orphelin n'est même plus reprenable par l'outil qui l'a créé.

**La cause est la CONFIG DE GIT, pas l'OS.** `LongPathsEnabled = 1` côté Windows, et l'énumération
PowerShell des 5 109 entrées se fait **sans une seule erreur**. La contre-épreuve (b) de l'étape 1
le tranche : le même montage, `core.longpaths true`, se supprime proprement.

## 2. Le gisement était EXCLUSIF — mesuré, pas supposé

Sur les 8 worktrees présents le 2026-08-07 (0 erreur d'énumération, 0 point de reparse) :

```
agent-a6a80fb64f037855f    total= 4185  >260=  217  dont 457-pycache=  217  hors=   0
les 7 autres               total= 0..4815  >260=    0
```

**217 chemins au-delà de 260, tous dans le miroir de bytecode de `probe_457`, aucun ailleurs.**

La cause est le **double ré-encodage** : `sys.pycache_prefix` concatène au préfixe le chemin
**absolu** de chaque source. Le miroir vivant sous `<worktree>/logs/ratchets/457-pycache`, le
chemin du worktree s'écrivait **deux fois**. L'écart mesuré le confirme exactement :

```
arbre principal       214 caracteres
worktree d'agent      298 caracteres      ecart = 2 x len("\.claude\worktrees\agent-<id>")
```

## 3. Ce qui a été livré

**(a) La config — ce qui est versionnable est le CONSTAT, pas la config.** Git ne lit aucune
configuration depuis l'arbre (ce serait une faille : un dépôt cloné exécuterait la config de son
auteur). L'étape 0 du cliquet mesure `core.longpaths`, dit **où** il est posé, et nomme la commande
de réparation. Elle signale explicitement `local` seul — perdu au prochain clone, invisible de toute
relecture, et c'est l'état qui était en place.

**(b) La cause — le miroir sort du checkout.** `probe_457._pycache_prefix()` rend désormais
`<tmp>/t457pyc`. Le point n'est **pas** la longueur du nouveau chemin : c'est que
`git worktree remove` n'a plus **aucun** chemin long à supprimer, quelle que soit la profondeur du
miroir. Contrepartie assumée — le miroir ne meurt plus avec le worktree — reprise par
`purger_miroirs_morts()`, appelée au début de chaque mesure : elle retire les sous-arbres dont la
**source** n'existe plus (critère : l'absence, jamais un âge). Profondeur 8, pour 6 niveaux utiles
(`<miroir>/Users/…/.claude/worktrees/agent-<id>`) ; la valeur 6 a **rougi** sur le montage à 7
niveaux du probe, ce qui est la raison de la marge.

**(c) Le critère — `livraison.etat_des_worktrees`.** Trois états, tri-état inclus :

```
ENREGISTRE   déclaré par `git worktree list --porcelain`
ORPHELIN     répertoire présent, entrée admin disparue      <- ce que l'échec laisse
DANGLING     entrée admin présente, répertoire disparu      <- `git worktree prune` la ramasse
mesure=False git muet -> listes vides qui NE VALENT PAS constat
```

`fleet_board` s'en sert : l'état « EN ATTENTE — reprenable par `SendMessage` » exige désormais
l'**enregistrement**, et les orphelins sont **nommés** dans un bandeau dédié au lieu d'être
silencieusement reclassés « fini ». Effet mesuré : 3 agents annoncés reprenables ne le sont plus,
et le sont dits tels.

Deux angles morts trouvés en écrivant, tous deux corrigés :

- la racine du gisement est **dérivée du porcelain** (git rend l'arbre principal en premier) —
  sans quoi une mesure lancée **depuis un worktree** ne voyait rien, ce qui est le cas normal ;
- `etat_de` ne se prononce **que sur son périmètre** (`.claude/worktrees/agent-*`). Sans cette
  borne, `probe_467` est devenu **ROUGE** : ses scènes synthétiques vivent sous `%TEMP%` et
  étaient classées ORPHELIN, faisant perdre l'état `attente` que ce probe garde précisément.

## 4. Le danger annoncé, LEVÉ par la mesure

`agent-a6a80fb64f037855f` (78,5 Mo) n'a **aucune branche**, ni locale ni distante : son contenu
n'existait plus qu'à cet endroit. Le critère de récupérabilité retenu n'est pas la branche mais le
**blob** — une branche dit où est le contenu *commité*, jamais ce qui ne l'est pas. Chaque fichier
est haché et confronté à la base d'objets (`hash-object --stdin-paths` | `cat-file --batch-check`,
deux process) :

```
1 805 fichiers hors bytecode  ->  47 blobs INCONNUS de git  ->  47 sous `logs/`, 0 hors
```

**Aucun travail source inédit.** C'est un résidu de suppression partielle : `.git` absent, la
plupart des répertoires déjà effacés. `--diagnostic` reproduit ce verdict et **ne supprime rien**.

⚠ Un « 0 fichier » y est rendu **VIDE**, pas « intégralement connu » : sur zéro fichier, la seconde
formule serait vraie par vacuité et se lirait comme une vérification.

## 5. Ce qui n'est PAS couvert

- **Les orphelins ne sont pas nettoyés.** Le probe diagnostique ; la suppression reste un geste
  humain. Trois subsistent au 2026-08-08 (deux coquilles vides, un de 29,8 Mo dont le contenu est
  établi comme sans travail perdu).
- **`git worktree prune` n'est joué nulle part.** La porte DANGLING est *détectée* (0 au moment de
  la mesure), pas *ramassée*. Le brancher demanderait de trancher qui le joue, et quand.
- **`core.longpaths` reste à poser sur chaque clone.** Le cliquet le dit ; il ne peut pas le faire.
