# #448-r3-r1 — l'étage était entré depuis, et le probe ne pouvait pas le voir

**Statut** : RÉSOLU. `test_448_r2b_stormboyz_teleporting_in_live.py` = **12 passed** (9 avant, dont
3 rouges). Sur le sujet de la tranche, **le port était juste** : la garde décrivait un port périmé,
et le probe qui aurait dû le montrer ne mesurait rien en ligne de commande. Le seul changement de
comportement livré est **ailleurs** — un `NameError` que `master` portait depuis le jour même et que
le re-jeu APRÈS REBASE a fait apparaître (§8).

## 1. Les trois rouges, et ce qu'ils accusaient

Sur `master` propre, trois gardes rougissaient en accusant le port d'avoir perdu deux mécanismes :

```
E-MOVING  : 1140 deja retire PENDANT le pas -- T1 fire trop tot
FINISH-a  : le port a RETIRE 1140 sur une unite HORS PLATEAU -- gate `HasTile` perdu
FINISH-a  : le port a repose l'unite -- il n'a pourtant PAS le Fallback
```

Les deux derniers disent l'**inverse** de ce que le probe décrit — signature d'un étage entré
depuis. C'en était un, et il est daté.

## 2. La cause — DEUX abilities portées le 2026-08-03, une garde écrite le 2026-08-01

`9fc0deca` (#448-r1) a porté les deux triggered que le probe et le test déclarent NON PORTÉES :

| symbole natif | événement | ce qu'il fait | site Python |
|---|---|---|---|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.StormboyzStrike_MissAbility` | `On(0x1f = PreUnitMove)` | `RemoveEffect(Caster@Sel+0x48, Nullable(0x474))`, **HORS du `If(Maybe(chance))`** | `triggers/loki/stormboyz_strike.py::stormboyz_strike_miss_tree` |
| `IdunBattleLogic.Abilities.Triggered.Loki.StormboyzStrike_FallbackAbility` | `On(0x28 = UnitFinishedTurn)` | `MoveUnitBehaviour(Caster, First(SortTilesByUtility(CanAddUnit(AllTiles), …), 1))` — **repose l'unité** | `…::stormboyz_strike_fallback_tree` |

Conséquences, exactement les trois symptômes :

* **le Miss retire `1140` au pre-move**, donc T1 (`On(0x04) & OwnerIsActor`) n'a plus rien à
  retirer et `1140` est déjà absent à l'entrée du vecteur after-move ;
* **le Fallback repose l'unité** ; comme les abilities sont évaluées **avant** les effets
  (`dispatch/core.py::evaluate_trigger_operation` concatène `collect_triggered_abilities` puis
  `collect_effect_triggers`), T3 voit ensuite `HasTile(Owner)` **VRAI** et retire.

Le natif, lui, n'a pas bougé : c'est exactement ce que le probe écrivait déjà de LUI (« côté natif
c'est ELLE qui retire 1140 dès le pre-move »). Les assertions exigeaient donc du port qu'il
**s'écarte** du natif. `test_448_r1_stormboyz_port_live.py` §L4 le disait déjà noir sur blanc — il
n'a jamais été confronté à `#448-r2b`.

## 3. Pourquoi personne ne l'a vu : le probe rendait VERT en CLI

Lancé directement, `probe_448_r2b_stormboyz_teleporting_in.py` rendait **0 échec** sur les deux
montages ; sous pytest, **3 rouges**. Même code, même seed, même board.

**Cause** : `load_state` ne seede `UnitContext.passive_abilities` (canal RPC `unitAbilityStates`)
que si le **transport ambiant** est lié (`snapshot.bind_live_rpc`, #363). Sans lui,
`collect_triggered_abilities` retombe sur `gameconfig.unit(<greffon>).passiveAbilities` — qui ne
porte évidemment **pas** l'ability GREFFÉE. **Aucune** des trois classes de `StormboyzStrike`
n'était montée côté port : le probe comparait un port **amputé** au natif, et toutes ses assertions
NÉGATIVES (« 1140 n'est plus là », « aucun `*_Moving` ») passaient à vide. `tests/conftest.py::live_session`
lie l'ambiant — d'où l'écart.

Mesure, en rebranchant le transport puis en le débranchant (`--mutate-nograft`) :

| régime | classes montées côté port | échecs du probe |
|---|---|---|
| transport lié (nominal) | `Fallback`, `Miss`, `Teleport` | **0** |
| transport non lié (l'état d'avant) | *(aucune)* | **12** |

## 4. Ce que la garde mesure MAINTENANT

Six volets, dont trois neufs. Le principe est le même que #448-r3 : on **attribue** à un étage au
lieu de constater un état.

* **E-PORTED** *(neuf)* — le registre a-t-il mordu ? Les trois classes doivent être montées. C'est
  l'anti-tautologie que l'absence a coûté : toutes les autres assertions sont des négatifs.
* **E-PREMOVE** *(neuf)* — `1140` est **là** à l'entrée du vecteur `On(0x1f)`, **parti** à sa
  sortie, et le vecteur a **rendu** le résultat du Miss. Côté natif, le retrait de `1140` dans la
  cascade **précède** le `ChangePosition` (index `[5,6]` contre `9` sur `MC1_67`, `[4,5]` contre `8`
  sur `C3_26`) — un retrait par T1 serait après. Même borne que #448-r3 emploie pour `1036`.
* **CONFRONT-MOVE** — terme à terme, **position comparée à l'identique**. C'est l'alignement PRNG
  (`dumpRng` → `state.rng`) qui le permet : le Miss tire `Maybe(20)` puis, si le hex est raté,
  `PickRandomly(CanAddUnit(AdjacentTiles(<dest>)), 1)`. Les deux montages exercent les deux bras —
  `MC1_67` **dévie** (port et natif tous deux en `(2,4)` pour une destination `(3,4)`), `C3_26` **ne
  dévie pas** (les deux en `(4,0)`). Le seuil mou « distance 0 ou 1 » d'avant acceptait un vrai
  désaccord de port du moment qu'il restait adjacent.
* **T3-GATE** *(neuf)* — le bras **FAUX** du gate `HasTile(Owner)`, que le geste n'atteint plus
  (le Fallback repose l'unité avant que T3 soit évalué). On l'isole en **retirant le Fallback du
  registre** : `matches()` de T3 rend `False`, et le vecteur `On(0x28)` laisse `1140` en place,
  l'unité hors plateau. Volet **PORT-SEUL** assumé : le natif ne peut pas produire ce régime.
* **T3-POSITIF** *(neuf)* — cf. §5.
* **FINISH** — port et natif terme à terme sur le geste nominal (`(1,3)` = `(1,3)` sur `MC1_67`,
  `(0,4)` = `(0,4)` sur `C3_26`), `1140` absent des deux côtés.

## 5. Ce que la réparation a trouvé : une contre-épreuve PÉRIMÉE PAR UN CANAL REDONDANT

`--mutate` (vider `EFFECT_TRIGGERS[1140]` = retirer les quatre `Triggered()` propres de l'effet)
laissait le probe corrigé **ENTIÈREMENT VERT**. Ce n'est pas un défaut de la garde : sur le geste
nominal, **les quatre triggers propres de `1140` sont devenus observationnellement INERTES**,
masqués par le kit qui les entoure —

| trigger | pourquoi il ne décide plus rien |
|---|---|
| T1 `On(0x04)` | le Miss a déjà retiré `1140` au `On(0x1f)` |
| T2 `On(0x2a)` | aucun cast n'est légal hors plateau (`abilityTargets.fromHere` vide, mesuré) |
| T3 `On(0x28)` | le `MoveUnitBehaviour` du Fallback **ré-émet `On(0x1f)`**, donc le Miss retire là AUSSI |
| T4 `On(0x1f)` | branche `Nothing()` (le `Nullable<EffectType>` est vide) |

D'où **T3-POSITIF**, le seul régime qui rend la main à T3 : l'unité **posée** (là où le NATIF l'a
posée — la sortie observée du Fallback, pas une position inventée) et **aucun mouvement** dans le
vecteur, donc pas de `On(0x1f)` et pas de Miss. `--mutate` y rougit désormais.

⚠ **Le retrait du Fallback est load-bearing dans ce bras aussi**, et ça s'est mesuré : avec lui, le
`MoveUnitBehaviour` déplaçait l'unité de `(1,3)` à `(0,3)` et le Miss retirait `1140` — la
contre-épreuve restait verte sur une tuile qui n'était même plus celle qu'on venait de poser.

## 6. Contre-épreuves jouées (une garde qu'on ne sait pas faire échouer ne garde rien)

| mutation | attendu | obtenu |
|---|---|---|
| `--mutate-nograft` (transport ambiant délié) | E-PORTED rouge | **12 échecs**, E-PORTED en tête |
| `--mutate-hastile` (gate `HasTile` → `True`) | T3-GATE rouge | **2 échecs**, les deux lectures du gate |
| `--mutate` (`EFFECT_TRIGGERS[1140]` vidé) | T3-POSITIF rouge | **1 échec** — `1140` survit |
| `StormboyzStrikeMissAbility` retirée du registre (mutant sur `registry.py`, vérifié aux octets : 86 070 → 86 018) | le fichier de test rouge | **5 failed / 7 passed** |
| `probe_448_r3 --mutate` (foyer touché par cette tranche) | détecte | détecte — `[E-MOVING] [1035]` |

## 7. Ce qui n'est PAS couvert

* **T2** (`On(0x2a = PreUnitAbility)`) reste non exercé par un geste : sous `1140` l'unité est hors
  plateau, sans portée ni ligne de vue, et `abilityTargets.fromHere` est vide des deux côtés. Le
  trigger est porté parce qu'il est dans l'`ArraySet` natif, pas parce qu'un geste l'exerce.
* Les volets **T3-GATE** et **T3-POSITIF** sont **PORT-SEULS** : le natif ne peut produire ni l'un
  ni l'autre (le Fallback y est toujours là). Ce sont des gardes de non-régression d'étage, pas des
  confrontations.
* Le **flux PRNG** lui-même (nombre de tirages) n'est pas assertionné ici — c'est l'objet de
  `test_448_r1_stormboyz_port_live.py` §L5/L6, qui le fait bit-exact sur deux bras. Ce fichier n'en
  consomme que l'**alignement**.
* `FullThrottle$$CreateTrigger` reste non porté (résidu nommé de `case-448-r1` §6.3).

## 8. Ce que le RE-JEU APRÈS REBASE a trouvé : `master` levait au chargement d'état

Le rebase sur `origin/master` (22 commits d'avance) était propre, et pourtant `test_448_r2_teleporting_in_live.py`
est passé de **4 passed** à **4 errors** :

```
engine/entities/effects/loki/status.py:382 in get_stat_modification_stat
    return StatType.FIXED_ARMOR
NameError: name 'StatType' is not defined
```

**Cause, datée** : `630fb33e` (#270-r1-r1-r3, 2026-08-05 16:07) a converti des littéraux en membres
d'enum — `return 16` → `return StatType.FIXED_ARMOR` — dans **huit** `get_stat_modification_stat`
de deux modules où `StatType` n'était importé **que dans le corps de quelques autres méthodes**.
Aucun des huit n'avait l'import.

**Ce que ça coûtait** : le lecteur est `entities/effects/__init__.py::effect_stat_modifications` ←
`stat_modifications_by_source` ← `UnitContext.from_snapshot` ← `snapshot.load_state`. **Toute
bataille dont une unité porte l'un de ces effets faisait lever le CHARGEMENT D'ÉTAT** —
`ContagionsOfNurgle_ArmorReduction`, `Contaminated`, `StandVigil_ExtraArmor`, `ThrillSeekers`, plus
quatre effets de `hits.py`.

**Correctif** : import module-level dans les deux fichiers (2 lignes). **Garde** :
`probe_448_r3_r1_noms_non_resolvables.py` + `tests/engine/test_448_r3_r1_noms_non_resolvables_offline.py`
— un CLIQUET (`manquants == 0`), pas un seuil, parce que #270 rouvre ce gisement à chaque tranche.

### L'instrument lui-même s'est trompé DEUX FOIS, et c'est mesuré

| version du balayage | ce qu'elle rendait | la faute |
|---|---|---|
| bindings module par `ast.walk(tree.body)` | **0 site** sur un fichier qui LÈVE | descend dans les corps de méthodes ⇒ un import LOCAL compte comme binding MODULE |
| fonctions par `ast.walk(tree)` | **85** sites | juge les fonctions IMBRIQUÉES avec la seule portée module, en ignorant les imports de leur parente |
| sans résolution des `import *` | **75** sites | `from ._shared import *` ⇒ `GC`, `AbilityConfiguration`, `ProbableDamageEvent` invisibles |
| sans filtre PEP 563 | **22** sites, tous des `Optional` | une annotation sous `from __future__ import annotations` n'est **jamais évaluée** |
| version livrée | **0** site, **0** fichier indéterminé, sur 406 | — |

Un `import *` non résolu ne rend pas un vert : le fichier est compté **INDÉTERMINÉ** et ses
fonctions ne sont pas jugées (tri-état, même discipline que `host_inputs.py`).

**Contre-épreuves** : le mutant synthétique (méthode sans import, sœur avec import) est détecté ;
et **retirer l'import réel de `status.py` remet exactement les 4 sites** — vérifié aux octets.

## 9. Résidu ouvert — `#448-r3-r1-r1`

**Un probe qui GREFFE et ne lie pas le transport ambiant mesure un port amputé, et rend VERT.**
Recensement du 2026-08-05 sur `scripts/python` : **20** fichiers combinent une greffe/relique
(`graft_passive_ability`, `graft_active_ability`, `write_grafted_seed_bc`, `equip_relic`,
`write_relic_seed_bc`) et un `load_state`. Les **tests** sont couverts par
`tests/conftest.py::live_session` ; **sept probes** ne lient rien :

```
probe_366_r1_stormboyz_strike.py          probe_448_r1_r1_r1_flying_movement_steps.py
probe_425_tile_effect_channel.py          probe_448_r1_r1_r2_fly_override.py
probe_447_bit51_native.py                 probe_478_cleave_additional_targets.py
probe_448_r2b_stormboyz_teleporting_in.py  <- CORRIGÉ par cette tranche
```

Ce compte est un **plancher**, pas un inventaire : le critère ne voit que les greffes faites *dans
le fichier lui-même*, et il ne dit rien des probes qui reçoivent un seed BC déjà greffé par un
appelant. À re-dériver, jamais à citer.

## 10. Reproduction

```
python scripts/python/probe_448_r3_r1_noms_non_resolvables.py
python scripts/python/probe_448_r3_r1_noms_non_resolvables.py --mutate
python -m pytest scripts/python/tests/engine/test_448_r3_r1_noms_non_resolvables_offline.py
python scripts/python/probe_448_r2b_stormboyz_teleporting_in.py
python scripts/python/probe_448_r2b_stormboyz_teleporting_in.py --mutate
python scripts/python/probe_448_r2b_stormboyz_teleporting_in.py --mutate-hastile
python scripts/python/probe_448_r2b_stormboyz_teleporting_in.py --mutate-nograft
python -m pytest scripts/python/tests/engine/runner/test_448_r2b_stormboyz_teleporting_in_live.py
```
