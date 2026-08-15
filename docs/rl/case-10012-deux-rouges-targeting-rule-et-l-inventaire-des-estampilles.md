# #10012 — les deux rouges de `test_targeting_rule_inventory.py`, et l'inventaire des estampilles de build

Build qui fait foi : `t6dpr4k06g` (migration depuis `rnca9r7q6c`). Décompilé relu sur ce build.

Deux rouges de `master` (2 F / 19 P), plus une question de portée : **combien d'autres artefacts
portent une estampille de build que la migration a périmée en silence ?**

---

## 1. Rouge A — le refus INVENTÉ accusait le MOTEUR ; la faute était à l'ORACLE

`test_le_port_ne_rend_jamais_une_permission_qui_ne_soit_pas_un_refus_natif` désignait
`AllowIgnoreForcedAttackTarget`. **Le port ne l'a jamais rendu comme code de refus** : il l'ÉCRIT
dans un masque, et c'est la dérivation qui comptait un `int(TR.<X>)` *n'importe où* sous un `return`.

Le décompilé tranche dans les deux sens, sur le build courant :

| sens | symbole | ce qu'il fait du bit 40 |
|---|---|---|
| ÉCRITURE | `IdunBattle.Entities.Abilities.AActiveAbility$$GetTargetingOptionsForContinue` | `uVar1 = <rules @+0x28> \| 0x10000000000` puis `forceMeleeTarget = 1` |
| LECTURE | `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (7 args) | `if ((rules >> 0x28 & 1) == 0) { … GetOnlyTargets(caster) … }` → **désarme** le taunt |

- L'écriture est le **seul** `movabs 1<<40` du binaire côté `IdunBattle` :
  `probe_429r1_bit_readers_scan.py --bit 40` rend 11 sites filtrés, **10 `shr r64,40`** (des tests)
  et **1 `movabs`** (celui-ci). Contre-épreuve intégrée du scanner : verte (bit 38 →
  `AActiveAbility$$CanContinueOnDeadTarget`).
- Aucun des ~30 `rule = <littéral>` que la cascade passe à
  `IdunBattle.Core.Services.TargetingRuleExtensions$$GenericBrokenTargetingRule` ne vaut
  `0x10000000000` ; quand le taunt rompt, le code rendu est `0x800000` =
  `TargetIsAllowedForCaster`.

⇒ `AllowIgnoreForcedAttackTarget` **n'est pas une seconde exception native** : c'est une PERMISSION
pure. La liste d'exceptions du test reste à UNE entrée (`AllowNullCasterTile`). C'est le **critère**
qui est resserré.

### Le correctif : la POSITION DE VALEUR, pas une liste d'exclusion

`probe_429_targeting_rule_inventory._tr_reason_codes` ne `walk` plus le sous-arbre : il **descend**
depuis `Return.value` par les seuls nœuds valeur-transparents — `IfExp` (`body`/`orelse`, **jamais**
`test`) et `BoolOp`. Un `int(TR.X)` opérande d'un `|`, argument d'appel ou indice n'est pas ce que le
`return` REND. **Ancrage natif** : un refus natif porte UNE règle, jamais une combinaison.

Mesure value-preserving, sur les sites `(nom, fichier, ligne)` :

| | ancien critère | nouveau |
|---|---|---|
| sites | 117 | 116 |
| `ancien \ nouveau` | — | `('AllowIgnoreForcedAttackTarget', 'targeting.py', 681)`, **et rien d'autre** |
| `nouveau \ ancien` | — | **vide** |

Le rapport GATE (46 règles, 30 portées) est **inchangé** : la fausse positive ne portait que sur
l'axe PERMISSION.

### Ce qui empêche le resserrement de faire disparaître un site en silence

Un filtre **dit ce qu'il filtre** : `rules_dropped_by_value_position()` nomme les écartés
`(nom, fichier, fonction porteuse)`, le rapport les imprime, et
`test_les_ecartes_de_la_position_de_valeur_sont_NOMMES` les met sous cliquet **dans les deux sens** —
un écarté NEUF rougit (il doit être LU), un écarté DISPARU rougit aussi (sinon le resserrement ne
serait plus exercé par du code réel et le test deviendrait vacant).

Quatre contre-épreuves intégrées, sur du code **synthétique** (`_port_modules` substitué, aucun
fichier du dépôt touché) : la permission rendue en position de valeur rougit toujours ; la
composition de masque **et** le `test` d'un `IfExp` sont écartés ET nommés ; les cinq formes
réellement employées par le port sont conservées ; le `return` d'une closure est attribué à la
fonction la **plus interne** et compté une seule fois.

`test_targeting_rule_inventory.py` : 21 tests (2 F / 19 P) → **26 tests, 26 passed**.

---

## 2. Rouge B — l'estampille du mirror : **rien n'a bougé**, et c'est une mesure

`engine/runner/abilities/targeting_rule.py` déclarait sortir de `data/symbols/rnca9r7q6c/…`.
Re-généré par `gen_targeting_rule.py` depuis le build courant.

**Diff des deux dumps, membre par membre, AVANT régénération** :

| | `rnca9r7q6c` | `t6dpr4k06g` |
|---|---|---|
| membres | 60 | 60 |
| ordre de déclaration | identique | identique |
| noms (différence symétrique) | ∅ | ∅ |
| valeurs renumérotées | 0 | 0 |

Le seul octet qui change dans le fichier généré est le hash. `probe_targeting_rule_bits.py` : 58 bits
simples concordants sur les TROIS sources.

C'est exactement ce que la docstring du test annonçait : « la coïncidence des noms est un accident de
ce build, pas une propriété ». Le cran d'estampille est **le seul** qui ait vu la migration.

---

## 3. La portée — NON, ce n'est pas « ces deux familles et rien d'autre »

Balayage des fichiers **suivis** hors `data/symbols/`, par hash de build ≠ `CURRENT` : 1 419 fichiers
citent un build périmé, l'écrasante majorité en **prose historique légitime** (une case-doc datée dit
un fait exact). Le tri utile n'est pas « où un hash est écrit » mais **« quel artefact est DÉRIVÉ d'un
build et déclare lequel »**. Trois familles neuves en sortent, plus un angle mort du recenseur.

### `#330-r3` — DEUX recenseurs Python sont aveugles au build COURANT

`probe_330_prose_va_and_build_stamps.BUILD_RE` = `(?<![a-z0-9])([a-z0-9]{8}6c)(?![a-z0-9])` : le
suffixe `6c` est **en dur**, et `t6dpr4k06g` finit par `6g`.
`BUILD_RE.search(current_build())` rend `None`.

> ⚠ **La même régularité accidentelle a déjà tué un capteur, et `#10011` l'a mesuré** :
> `/^[a-z0-9]{8}6c$/` en dur dans `frida/hooks/il2cpp/build-pin.ts` → `build: null`, **11 refus**
> de `pinnedAddress`, et un `test_le_natif_suit_le_PORT` **VERT sur zéro assertion évaluée**
> (`case-10011-suffixe-de-hash-et-verdicts-a-vide.md` §1). Ce résidu-ci est le **foyer PYTHON** de
> la même faute : re-vérifié après le merge de `#10011`, `probe_330.BUILD_RE` vaut toujours
> `[a-z0-9]{8}6c`. Deux foyers mesurés pour une seule cause — c'est ce qui rend la dérivation de
> la forme du jeton (plutôt qu'un second suffixe deviné) non négociable.

**Le même littéral de regex vit dans DEUX foyers, et le code le dit** : `probe_431_build_literals.py:78`
porte la même `BUILD_RE`, commentée « Même forme que `probe_330.BUILD_RE` — les deux comptes doivent
rester comparables ». Ils se réparent donc ensemble ; les séparer garantirait la divergence.

Chiffrage sur le dépôt entier (fichiers suivis, hors `data/symbols/`) :

| | mesure |
|---|---|
| occurrences **vues** par `BUILD_RE` (suffixe `6c`) | **2 903** |
| occurrences du **build courant**, invisibles | **176**, dans **67 fichiers** |
| … dans le périmètre propre de `probe_330` (`docs` + `.claude`, `.md/.txt/.tsv`) | **60**, dans **17 fichiers** |

⚠ **Le pire est côté `probe_431`, dont c'est le métier.** Son cliquet rend `rc=1` sur **3
RESOLUTIONs** — `probe_547_ledger_sans_verdict_non_vert.py:128`, `probe_988_ancres_utilite_playbook.py:47`,
`tests/engine/test_963r4_areenemies_null_operand_offline.py:149`, toutes marquées `[rnca9r7q6c PERIME]`.
Mais ses candidats **dérivent** de `BUILD_RE` : une résolution codée en dur sur `t6dpr4k06g` serait
invisible, donc le cliquet passerait au **VERT en GAGNANT** le gisement qu'il existe pour tenir. Un
recenseur qui perd sa cible en même temps que le build change est pire qu'absent — il rassure.

Second volet, le PÉRIMÈTRE de `probe_330` : `PROSE_EXT`/`DEFAULT_ROOTS` excluent `frida/hooks/**` et
`scripts/python/**`, donc les deux familles ci-dessous lui sont **structurellement** hors de portée.

Le remède n'est pas d'ajouter `6g` (ce serait deviner le suffixe suivant) mais de dériver la forme du
jeton des noms de répertoire réellement observés sous `data/symbols/` et `data/dumps/`.

**Méthode du balayage** — la première passe (motifs de forme + contexte `build|hash|symbols`) a rendu
**547 fichiers**, illisible : le motif « suffixe `6c` » capte toute prose citant un build. Ce qui a
rendu la mesure exploitable est d'**exclure les lignes de commentaire et de docstring** et de ne
garder que l'**exécutable** — 547 → **20 fichiers**, dont exactement **deux** portent une regex de
forme du hash (les deux ci-dessus). Les 18 autres sont des `len()`/`startswith()` sans rapport
(longueurs de listes, préfixes de chemins).

### `#330-r4` — le CONTENU est gardé, l'ESTAMPILLE ne l'est par RIEN (8 fichiers)

`probe_252_hook_name_tables.py` rend « toutes les tables figées collent au build `t6dpr4k06g` »
(6 tables, 0 faux) et `probe_313` « 38 mirrors en bijection avec `t6dpr4k06g` » — **pendant que** :

| artefact | estampille déclarée | générateur |
|---|---|---|
| `frida/hooks/data/{ability,effect-type,event-trigger-type,triggered-ability,utility-type}-names.ts` | `data/symbols/rnca9r7q6c/frida/enums.tsv` | `regen_hook_name_tables.py` |
| `frida/hooks/data/targeting-rule-names.ts` | `data/dumps/kqkbjqfb6c/dump.cs` — **source supprimée** | **aucun** (refus explicite, `regen_hook_name_tables.py` §34) |
| `scripts/python/enum_maps.py` | `data/symbols/rnca9r7q6c/frida/enums.tsv` | `regen_enum_maps.py` |
| `scripts/python/engine/entities/active_ability_type.py` | idem | `regen_enum_mirrors.py` |

L'accord contenu ↔ build est un **accident de cette migration** : `regen_enum_mirrors.py` et
`regen_enum_maps.py` en simulation rendent **0 ajouté / 0 retiré / 0 renommé** partout (30 mirrors,
6 tables). Les deux régénérateurs **réécrivent** bien la ligne de source avec `current_build()`
(`regen_hook_name_tables.py:136`, `regen_enum_maps.py:83`) : la correction est un re-jeu, jamais une
réécriture de champ.

### `#330-r5` — les scans `docs/rl/dsl-usage/*.tsv`, où le contenu n'est gardé par RIEN

Ligne 2 des trois fichiers : `# schema_version=1.0  build=rnca9r7q6c  binary=GameAssembly.dll
scan_complete=true`. Estampille **machine**, qu'aucun cliquet ne confronte à `CURRENT`. La différence
avec `#330-r4` est décisive : là-bas une bijection membre à membre rattrape le contenu ; ici c'est un
**scan d'instructions du binaire**, qu'un déplacement de code périme sans qu'aucune bijection le
voie — l'estampille est le seul signal disponible.

### Ce qui N'EST PAS un résidu, et pourquoi

- **Adresses épinglées** (`frida/hooks/features/scorer-damage-trace.ts`, `modifier-observe.ts`) :
  elles DÉCLARENT leur build et `frida/hooks/il2cpp/build-pin.ts` **refuse** en le disant quand il ne
  correspond pas (#431). Toutes sont désormais périmées — ces hooks refusent de s'attacher,
  bruyamment. C'est le dispositif qui fonctionne, pas un trou. ⚠ **À une nuance près, tranchée par
  `#10011` pendant cette tranche** : la même régularité `6c` y rendait `installedBuild()` nul, donc
  les 11 refus étaient corrects **pour la mauvaise raison**, et personne ne les lisait. Le foyer TS
  est réparé ; les deux foyers Python (`#330-r3`) ne le sont pas.
- **`scripts/declencheurs-empreinte.tsv`** (44 lignes citant `data/symbols/<build>/`, **0** sur le
  build courant) et **`scripts/ratchets-457-footprints.json`** (137 références à
  `data/symbols/rnca9r7q6c/…`) : artefacts **générés**, dont l'en-tête prescrit déjà la
  régénération, et dont les cliquets (`probe_457 --measure-missing`, `probe_486r15`) sont
  **suspendus**. Observation chiffrée, pas résidu : je n'ai pas établi que le témoin périmé change
  le verdict du cliquet, et ouvrir un résidu sur une prémisse non mesurée est le vice que
  `feedback_residue_premise_may_be_false` nomme.
- **La prose historique** (`docs/rl/case-*.md`, commentaires « mesuré sur `rnca9r7q6c` ») : déjà
  couverte par `#330-r1`/`#330-r2`, et une case-doc datée n'est pas une estampille qui ment.
