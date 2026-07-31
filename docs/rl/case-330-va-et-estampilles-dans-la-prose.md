# #330 — VA absolues et estampilles de build dans la prose : la mesure

> Build de référence : `rnca9r7q6c` (= `data/symbols/CURRENT` au moment de la mesure).
> **Re-dériver plutôt que citer ces chiffres** : `python scripts/python/probe_330_prose_va_and_build_stamps.py`.

Tâche de **mesure**, pas de correction. Déclencheur : un catalogue DSL a été trouvé **par
hasard** portant en titre un build antérieur et 17 VA absolues, sans bandeau de péremption ;
un second agent y avait lu 12 primitives « manquantes » qui étaient en fait portées. Le
document n'était pas seulement périmé, il induisait activement en erreur. Il a été supprimé
au commit `687d72c7`. Un fichier corrigé ne dit rien de la population — d'où ce chiffre.

## 1. La cause racine se lisait AVANT de compter

`scripts/python/probe_va_in_code_vs_prose.py` est le garde-fou des VA. Il ne collectait que
des `*.py` (`p.rglob("*.py")`). Lancé sur `docs`, il imprimait :

    fichiers Python scannes : 0

    AUCUNE occurrence dans du code executable : migration sans risque de casse.

**Un VERT sur un répertoire jamais regardé.** La migration de build #251 n'avait donc aucun
moyen de voir ce gisement — le fichier supprimé ne pouvait pas être le seul, et ne l'était pas.

Un **second faux vert, préexistant et plus large**, a été trouvé en jouant le contrôle de la
mutation : l'exclusion `--exclude .claude\worktrees` était testée sur le chemin **absolu**.
Lancé depuis un worktree d'agent (`<repo>/.claude/worktrees/agent-xxx/`), le motif matchait la
racine elle-même et le probe s'excluait **intégralement** — `0 fichier scanné`, verdict vert,
sur tout le code Python. C'est-à-dire dans le cas nominal, celui de tout agent. Après
correction, la même invocation scanne **1157** fichiers et rend **80** littéraux exécutables.

## 2. Population — `docs/` + `.claude/`

Fichiers de prose scannés : **361** (`.md`, `.txt`, `.tsv`). Occurrences de VA absolues
(`0x18xxxxxxx` / `@18xxxxxxx`) : **4617** dans **144** fichiers.

Les VA **relatives** ne sont pas comptées : le motif exige 9 chiffres hexa ouverts par `18`,
ce qu'un offset de champ (`+0xa8`), un slot de vtable ou une RVA calculée depuis l'image base
n'a jamais.

| Ventilation | Occurrences | Sort |
| --- | ---: | --- |
| **MIGRABLE** | **4580** | → `<symbole>[+0x<offset>]` |
| PLACEHOLDER (`FUN_`) | 5 | **reste en VA** — le symbole n'est que l'adresse déguisée |
| HORS CODE (données / slot `methodPointers`) | 15 | **reste en VA** — aucune fonction ne la couvre |
| `0x180000000` (image base) | 17 | hors sujet — ce n'est pas une citation |

Soit **4580 migrables / 20 légitimement en VA / 17 hors sujet**.

Les 20 qui restent en VA, listées (`--list-placeholders`) plutôt que maquillées :

- **15 slots `methodPointers`** — adresses de **données**, pas de code, au-delà de la dernière
  fonction nommée : `case-220/votann.md` (4, qui écrit explicitement « son slot methodPointers »),
  `case-222-maillons-de-pose.md` (4), `playbook/journal.md` (3), `playbook/playbooks.md` (3),
  `case-108-murderous-swing.md` (1).
- **5 placeholders `FUN_`** — `case-66-revive-in-place.md` (4, même adresse),
  `case-49-gauntlets-unobscured.md` (1).

### Répartition par famille de document

| Famille | Citations | dont périmées avérées |
| --- | ---: | ---: |
| **RÉFÉRENCE** (lu comme état courant) | 1613 | **1511** |
| CASE-DOC (compte rendu daté, figé avec son cas) | 2987 | 2767 |

Le gisement **actionnable** est la colonne RÉFÉRENCE : c'est le profil exact du fichier
supprimé. Têtes de file : `runner-engine.md` (201), `playbook/prediction.md` (177),
`dsl-effect-nodes.md` (141), `playbook/journal.md` (130), `terrain-effects.md` (96),
`stat-system.md` (88), `dsl-wave2-specs.md` (83), `playbook/playbooks.md` (77),
`genestealer-cults.md` (73), `solving-playbook.md` (65) — 32 fichiers RÉFÉRENCE au total.

### `.claude/` est sain côté VA

**0 VA migrable.** Les 4 occurrences y sont toutes `0x180000000`, l'image base
(`skills/tacticus-re-port/SKILL.md` ×2, `agents/opus-solver.md`, `agents/re-expert.md`).

### Hors périmètre demandé

Le reste du dépôt (racine, `frida/`, `hooks-legacy/`…) : **1** occurrence sur 6 fichiers de
prose. Le gisement est concentré dans `docs/`.

## 3. Fraîcheur — et le piège qui attend la migration

| Fraîcheur | Occurrences |
| --- | ---: |
| À jour (début de fonction du build courant) | 167 |
| **PÉRIMÉE AVÉRÉE** | **4278** |
| Indéterminée (offset interne ou orpheline) | 155 |

« Périmée avérée » = la VA est une adresse de **début de fonction exacte** dans un build
antérieur, et **pas** dans le build courant. Elle vient donc démontrablement de l'ancien build.

**Le piège : sur ces 4278, les 4278 résolvent, contre la table COURANTE, sur un symbole
DIFFÉRENT de celui qu'elles désignaient.** Migrer ce lot avec `ghidra_symbols.py whereis` —
qui lit le build chargé — produirait **4278 citations fausses mais d'apparence propre.**
C'est strictement pire que l'état actuel : une VA périmée se démasque en ne résolvant sur
rien de cohérent ; un symbole faux, lui, se lit comme une vérité.

Exemple rendu par le probe (l'adresse elle-même n'est pas recopiée ici — ce document ne
grossit pas le gisement qu'il mesure ; `--top` la réaffiche à la demande). La première VA de
`docs/rl/agent-port-tips.md:18` désignait `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`
dans son build d'origine ; contre la table courante, la même adresse tombe sur
`...FearedInterrogatorEffectVisuals$$Receive…` — une fonction de **visuels**. Rien n'avertit
le lecteur.

**Une migration de ce lot doit résoudre chaque VA contre la table du build D'ORIGINE**
(`data/symbols/<build>/ghidra/functions.tsv`), pas contre la courante. `probe_330` le fait :
il essaie toutes les tables, correspondance exacte de début de fonction d'abord.

## 4. Estampilles de build

**208** estampilles d'en-tête ou déclaratives portant un hash ≠ `rnca9r7q6c`, dans **154**
fichiers — **57** en RÉFÉRENCE, 151 en CASE-DOC. Cinq builds distincts y apparaissent, dont
deux qui ne sont plus sur disque du tout. S'y ajoutent 126 mentions en corps, majoritairement
légitimes (un document de migration parle forcément des deux builds).

Ce gisement était **déjà nommé** au backlog, non chiffré — #283-r2 : « Décider AUSSI de
l'estampille de build des docstrings (« RE décompilé ghidra, build … ») : plusieurs annoncent
un build qui n'est plus installé, gisement distinct non traité. » L'apport de #330 est le
chiffre, la ventilation, et la cause racine.

**L'arbitrage pour les CASE-DOC est déjà rendu** et vaut aussi ici : `case-254b-b` §7 — « on ne
rétro-corrige pas un compte rendu produit par un autre build ». Une case-doc qui écrit « RE
faite contre `gqfc5mff6c` » énonce un fait exact et daté. Ce qui reste à trancher est le sort
des **documents de RÉFÉRENCE**, lus comme l'état courant.

### Corrigé dans cette passe

Les deux estampilles de `.claude/` qui se prétendaient **au présent** (chaque agent les charge) :

- `skills/tacticus/SKILL.md` — chemin d'exe figé sur un build de deux migrations en arrière ;
  un agent qui le suit ne trouve pas le binaire. Remplacé par `<HASH>` + comment le lire.
- `skills/tacticus-orchestration/SKILL.md` — le commentaire disait littéralement
  « build courant (…) » en nommant un build qui ne l'est plus. Remplacé par
  `cat data/symbols/CURRENT`.

### À arbitrer par l'orchestrateur — fichiers `!include`-és dans `CLAUDE.md`

Non touchés ici, leur amendement revient à l'orchestrateur :

- `.claude/skills/tacticus/references/runner.md:124` — « Inventaire terrain (scan des 779
  dumps, build `gqfc5mff6c`) ». C'est une **mesure datée**, pas une estampille qui se prétend
  courante : le comptage de boards peut être encore juste. À re-dériver plutôt qu'à réécrire.

## 5. Cliquets

| Cliquet | État | Vérifié par mutation |
| --- | --- | --- |
| `probe_va_in_code_vs_prose.py` refuse de conclure sur une racine sans `.py` (sortie 2) | **ARMÉ** | oui, dans les deux sens |
| `probe_330 … --fail-on-header-stamp` sur `.claude/` | **ARMÉ, vert** | oui, dans les deux sens |
| `probe_330 … --fail-on-header-stamp` sur `docs/` | **non armé** — rouge à 208 | — |

Vérifications jouées, pas déduites :

- `probe_va_in_code_vs_prose.py docs` → sortie **2**, et il énumère désormais ce qu'il n'a pas
  regardé (345 fichiers : 341 `.md`, 3 `.tsv`, 1 `.json`). Contrôle : `scripts/python` →
  sortie **0**, 1157 fichiers, 80 littéraux exécutables. Contrôle d'une racine inexistante
  (`engine`, qui vit sous `scripts/python/`) → sortie **2** ; l'ancien code y répondait
  « migration sans risque de casse ».
- Cliquet estampilles sur `.claude/` : vert (sortie 0) ; réintroduction de l'estampille
  supprimée → **rouge (sortie 1)**, avec le fichier et la ligne ; retrait → vert.

## 6. Ce qui n'est PAS couvert

- **Aucune migration de VA n'est faite.** Le lot de 4580 reste entier ; il exige l'arbitrage
  du §3 (lire la table du build d'origine) et de connaître, pour chaque fichier, le build
  contre lequel il a été écrit — ce que l'estampille donne quand elle existe.
- **`migrate_va_to_symbol.py` n'a pas été exercé sur de la prose.** Il est token-aware pour le
  Python ; son comportement sur `.md` n'est pas mesuré ici.
- **La distinction « référence vivante » / « case-doc » est syntaxique** (`case-*.md` ou un
  répertoire `case-<N>/`). Elle classe bien le corpus observé, mais ne remplace pas un
  jugement sur un document précis.
- **Les VA en commentaires TypeScript** (`frida/hooks/*.ts`) ne sont dans le périmètre d'aucun
  des deux probes : `probe_va_in_code_vs_prose` ne lit que du `.py`, `probe_330` que de la
  prose. Angle mort restant, non chiffré.
- La borne d'étendue d'une fonction est la distance au symbole **suivant** — un majorant
  (du padding peut s'y glisser). Elle sert à écarter les adresses de données, pas à mesurer
  finement une taille de fonction.
