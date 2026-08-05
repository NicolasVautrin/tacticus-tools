# case-482-r3 — archiver l'empreinte AVANT que le binaire disparaisse

> **Numéro.** Résidu `#482-r3`, ouvert par la fiche `case-482-empreinte-structurelle-par-fonction.md`.

`#482` a livré une **empreinte structurelle par fonction** : elle répond à « ce symbole a-t-il
le même corps entre deux builds ? ». Rien ne la déclenchait, et surtout rien ne garantissait
qu'elle soit encore **calculable** demain.

## 1. Le critère, avant la méthode — et il n'est pas celui qu'on croit

L'intuition dit : *détecter le changement de build, puis archiver le sortant*. Le signal
naturel est la divergence entre le hash installé et `data/symbols/CURRENT`.

**MESURÉ : ce signal arrive structurellement trop tard.** État du disque au moment de la
tranche :

| | contenu |
|---|---|
| `AppData/Local/tacticus/games/` | `rnca9r7q6c` seul, plus un `.temp` **vide** |
| `data/symbols/` | `gqfc5mff6c` **et** `rnca9r7q6c` |

La divergence sur `gqfc5mff6c` était parfaitement détectable — et son `GameAssembly.dll`
avait **déjà disparu** quand elle l'est devenue. Un dispositif branché sur la divergence
n'aurait rien pu archiver. C'est la forme exacte de la perte du gameconfig de `gqfc5mff6c`,
déjà documentée : « on ne saura **jamais** ce que cette mise à jour a changé dans les données ».

Le critère exploitable est donc l'**inverse**, et il ne parle pas du build sortant :

> **« le build COURANT a-t-il DÉJÀ son empreinte archivée ? »**

Il se vérifie à tout instant, il se **répare** tant que le `.dll` est là, et quand le build
devient sortant son empreinte est déjà au chaud. **On n'archive pas le passé : on archive le
présent pour qu'il survive.**

## 2. Où l'archive vit — `data/`, tranché par le chiffre

`data/symbols/<HASH>/fingerprints/functions.tsv`, versionné.

- **C'est une ENTRÉE**, pas une sortie de run : produite une fois, jamais re-dérivable après la
  disparition du binaire, relue pendant des mois. Même statut que `ghidra/functions.tsv` et
  `gameconfig.json`, dans le même répertoire.
- **`logs/` meurt** — ce n'est pas une crainte, c'est la mesure : `logs/fingerprints/` était
  **absent de l'arbre principal** au début de cette tranche. Les deux empreintes calculées par
  #482, dont celle d'un build dont le `.dll` n'existe plus, avaient disparu avec le worktree de
  leur auteur.
- **Volume** : 20,57 Mo brut, **6,96 Mo** en objet git (zlib). Un `.gz` versionné coûterait
  6,29 Mo — **9,6 % de gain** contre la perte du `grep`, du diff textuel et de la lecture
  humaine. Refusé sur ce chiffre. Pour comparaison, le même répertoire porte déjà
  `frida/methods.tsv` (21,9 Mo) et `gameconfig.json` (18,0 Mo) ; `.git` fait 199 Mo.
- `.gitattributes` couvre déjà `data/symbols/**/*.tsv text eol=lf` — rien à ajouter.
- `probe_273 --only-scan` étape 0c **passe** : le premier segment sous `data/` est `symbols`,
  qui est une entrée versionnée.

## 3. Le déclencheur — un axe de plus sur une garde qui tourne déjà seule

**Axe 6 de `symbols_sync.py`**, exécuté par le hook `SessionStart` (`scripts/hooks/session-start.ps1`,
budget 15 s). C'est le foyer juste : cette garde surveille déjà les artefacts de build, elle se
déclenche toute seule, et elle porte la discipline tri-état.

Le dosage n'est pas uniforme, et c'est voulu :

| état | effet |
|---|---|
| `DISCORDANTE` | **LÈVE** (rc 1) — artefact incohérent, comme l'axe 2 |
| `RECUPERABLE_PE` / `RECUPERABLE_GHIDRA` | **PARLE** — action bornée (~70 s, une fois), le message s'éteint dès qu'elle est faite |
| `PERDUE` | **imprimé**, ne lève pas — aucune action ne peut l'éteindre, et une alarme inextinguible désarme un garde-fou |
| `INDETERMINEE` / `SANS_TABLE` | **parle** en disant ce qui n'a pas été mesuré |

## 4. Le tri-état, qui est le cœur du capteur

Deux sondes portent sur des répertoires **hors du dépôt** : `games/` et `ghidra-projects/`.
Chacune rend `True` / `False` / `None`, et `None` veut dire **PAS MESURÉ**.

La distinction porte un verdict lourd : `PERDUE` autorise à nettoyer un projet Ghidra. Le
rendre sur un répertoire simplement illisible ferait **détruire du matériel irremplaçable**.
`probe_482r3` étage 3 est écrit pour ça, et l'étage 7 (contre-épreuve) le vérifie en cassant
le capteur.

## 5. Ce qui a été archivé — et ce qui ne pouvait pas l'être

| build | binaire | projet Ghidra | verdict |
|---|---|---|---|
| `rnca9r7q6c` | présent | présent | **archivé** depuis le PE — 154 176 fonctions |
| `gqfc5mff6c` | **disparu** | présent | **archivé** via `--depuis-ghidra` — 143 030 fonctions |
| `kqkbjqfb6c` | **disparu** | présent | **archivé** — table extraite d'abord (145 486 fonctions, 121 933 en `$$`) |
| `tacticus` | — | présent | **hors pipeline** : c'est un `libil2cpp.so` **ANDROID** |

**`ghidra_tacticus` n'est pas un build Tacticus PC.** Mesuré : 382 405 fonctions, **0 en `$$`**,
VA à 7 chiffres (pas d'`ImageBase` 0x180000000). La fiche #482 et le brief de cette tranche le
citaient comme « extractible par la même voie » — il ne l'est pas.

Ce constat a produit **une garde réelle** : `charger_depuis_blocs` refuse désormais toute image
dont `image.meta:language` n'est pas `x86:LE:64*`. `empreinter_build` désassemble en x86-64 **en
dur** ; sur de l'ARM64 capstone **ne lève pas** — il rend des instructions plausibles et fausses,
donc une empreinte silencieusement fausse. Le refus porte sur la **preuve**, jamais sur le
silence : une langue absente (vieux dumps) ne bloque pas.

## 6. Deux outils neufs, et pourquoi le second existe

| fichier | rôle |
|---|---|
| `scripts/python/build_fingerprint_archive.py` | le **capteur** : état d'archivage par build, tri-état. Zéro import lourd (il tourne au `SessionStart`) |
| `fingerprint_functions.py archiver` | **produit** l'archive, choisit sa source seule (PE d'abord, Ghidra en rattrapage), refuse d'écrire sans sha256 |
| `scripts/ghidra/GhidraDumpFunctionSymbols.java` | extrait `<VA>\t<symbole>` d'un projet en `-readOnly` |
| `scripts/python/probe_482r3_archive_empreinte.py` | la **garde**, 7 étages |

`GhidraDumpFunctionSymbols.java` existe parce que `ghidra_symbols.py dump` passe par ghidra-mcp :
**~1 h 15** pour 154 176 symboles, entièrement en allers-retours HTTP paginés, et il exige que le
serveur serve **ce** projet — or il sert le build courant. Un build archivé lui est donc
inaccessible sans couper le service. En headless `-readOnly`, l'extraction a pris **~3 min** et
n'a dérangé personne (projets distincts, verrous distincts).

Il **compte les formes dans son en-tête** (`avec$$=`, `FUN_=`) : c'est ce qui a permis de trancher
`kqkbjqfb6c` (appariable) contre `tacticus` (0 en `$$`) sans ouvrir les fichiers. Une table en
notation pointée ne s'apparie pas — incident du 2026-07-29, 0,43 % de symboles communs.

## 7. L'archive répare un étage qui n'était mesuré nulle part

`probe_482` étage 4 (auto-diff) cherchait `logs/fingerprints/<build>.tsv` — un chemin **gitignoré**.
Il se déclarait **NON MESURÉ dans tout checkout frais**, arbre principal compris. Le défaut vise
maintenant l'archive versionnée : **117 539 symboles appariés, 0 changement**. `probe_482` passe de
4 étages mesurés à **5**.

Le défaut de `--pe` portait un hash de build **en dur** (`rnca9r7q6c`) ; il est dérivé de
`installed_dll()`, sans quoi il aurait rendu `NON MESURÉ` sur une installation présente dès la
prochaine mise à jour.

## 8. Politique de conservation des projets Ghidra — ce qui change, ce qui ne change pas

`NE-PAS-SUPPRIMER.md` disait : sans le projet, « impossible de répondre à *cette méthode a-t-elle
changé de comportement entre les deux builds ?* ». **Ce n'est plus vrai pour la DÉTECTION** —
l'archive répond, et elle tient dans 20 Mo versionnés contre 4 Go hors dépôt.

**Ça ne change rien pour l'EXPLICATION.** Le projet reste la seule source du décompilé, des xrefs,
et de `fingerprint_functions enqueter` (qui a besoin des octets). L'archive dit **QUOI** a changé ;
le projet seul dit **COMMENT**. La règle reste donc : ne jamais supprimer un projet dont le `.dll`
a disparu. Ce qui baisse, c'est le coût d'une perte accidentelle — on garderait la liste des
11 186 corps changés.

## 9. Ce qui n'est PAS mesuré

- **La suppression par le vrai lanceur Tacticus** : elle ne se provoque pas. La simulation de
  l'étage 5 supprime le binaire à la main sur un arbre synthétique.
- **Le coût réel** dans la simulation : 3 fonctions contre ~150 000 (~70 s) en vrai.
- **Le hook lui-même** : `probe_482r3` confronte `axe6_archive_empreinte`, pas l'exécution
  PowerShell de `session-start.ps1`.
- **Les 1 160 changements à corps partagé** (`#482-r2`) et les `FUN_*` (`#482-r4`) restent hors
  appariement — inchangé par cette tranche.

## 10. Résidus

- **`#482-r5`** — `data/symbols/kqkbjqfb6c/` est **partiel** : il porte `BUILD`, `ghidra/functions.tsv`
  et `fingerprints/`, mais **pas** les tables `frida/` (le dump Frida exige le jeu qui tourne, et
  ce build n'existe plus). Conséquence mesurée : son sha256 n'est croisé par **aucune** seconde
  source, et le capteur le **dit** (`sha256 NON CROISE`). Aucun outil ne s'en plaint aujourd'hui ;
  reste à décider si un répertoire partiel doit porter une marque explicite.
- **`#482-r6`** — `ghidra_tacticus` (Android, `libil2cpp.so`) est conservé sans que rien ne dise
  à quoi il sert ni s'il est encore utile. Le qualifier ou le décrire dans `NE-PAS-SUPPRIMER.md`.
