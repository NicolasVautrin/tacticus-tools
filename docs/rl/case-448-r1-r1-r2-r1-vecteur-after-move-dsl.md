# case-448-r1-r1-r2-r1 — le vecteur after-move appartient à l'OPERATION

`#448-r1-r1-r2-r1`, nommé par la PR #571 : « les feuilles DSL qui déplacent une unité ne jouent pas
le vecteur after-move ». **Fermé.** Le fermer ACTIVE le second bras d'`IsLikeFlying` livré par #571,
qui était fidèle mais INERTE côté port — plus personne ne consommait `last_movement_steps` sur ce
chemin.

---

## 1. Le critère binaire, et sa réponse

**Où le natif joue-t-il le vecteur after-move, et pour QUELLES voies de déplacement ?**

`IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers` a **DEUX xrefs CODE dans tout le
binaire**, toutes deux dans `IdunBattle.Operations.MoveUnitOperation$$Execute` :

| site | contexte | `movementSteps` passé |
|---|---|---|
| `MoveUnitOperation$$Execute+0x9de` | branche « `position.Count == 0` **et** `options+0x15` (`allowNullTargetPosition`) » — le natif retire l'unité de ses tuiles (slot `RemoveUnitFromTiles`) puis joue le vecteur et **retourne** | `0` |
| `MoveUnitOperation$$Execute+0x1111` | branche RÉELLE, entre les DEUX `RefreshEffects({trigger = 7, effectEntity = null})` | `IsLikeFlying ? GetDistance(path.First, path.Last) : path.Count` |

⇒ **le vecteur appartient à l'Operation, pas à l'appelant.** C'est aussi la bonne réponse à la
frontière #149 : au-dessus du `.Execute` d'une feuille = déclaratif, en dessous = impératif. Un
vecteur joué par l'Operation **émerge** pour toute feuille DSL de mouvement ; aucune liste de
feuilles n'est énumérée à la main.

Le port, lui, ne le jouait que depuis `MovementHandler.visit_MoveUnitMessage` — le mouvement JOUEUR
ordinaire. Tout déplacement issu d'une feuille DSL était **muet**.

## 2. Le corps du vecteur, et ses DEUX gates

```csharp
// EvaluateAfterMoveTriggers(unit, position, previousPosition, movementSteps, isInterimStep, trig)
publish On(0x24 = UnitPositionChanged_1);
if (isInterimStep) return;                       // <- LA COUPURE
publish On(4    = UnitAfterMove);                //    OVERWATCH
publish On(0x1d = UnitPositionChanged_2);
```

`isInterimStep` est le **nom LU** dans la signature IL2CPP du 6e paramètre ; il vaut l'octet
`MoveUnitOptions+0x14` aux deux call-sites. Un pas INTERMÉDIAIRE ne déclenche donc **ni l'overwatch
ni `On(0x1d)`**.

Et, dans `Execute`, autour de l'appel :

```csharp
if (options+0x10 == 0) newlyAdded = UnitFlagsComponent.Add(UnitFlag.ArrivedAtFinalTile = 1);
... EvaluateAfterMoveTriggers(..., isInterimStep = options+0x14, ...) ...
if (newlyAdded) publish On(0x1c = ArrivedAtFinalTile);
```

**Corroboration indépendante du mapping de l'octet `+0x14`** : la case-doc de `TheBetrayer` (#149)
avait déjà écrit « `param_6` = options[4] du nœud `MoveUnit` (**behaviour +0x80**) = flag SUPPRESS,
défaut 0 = overwatch ACTIF ». Or `MoveUnitBehaviour+0x80` est exactement le sélecteur que
`MoveUnitBehaviour$$Execute` empaquette dans `MoveUnitOptions+0x14`. Deux lectures indépendantes,
même résultat.

## 3. `MoveUnitBehaviourOptions` → `MoveUnitOptions` : la table d'empaquetage

`IdunBattle.Entities.Behaviours.MoveUnitBehaviour$$.ctor` range les 0x40 octets des options du
behaviour aux champs `+0x60..+0x98` de l'objet, et `$$Execute` les convertit :

| `MoveUnitBehaviourOptions` | champ `MoveUnitBehaviour` | → `MoveUnitOptions` | rôle dans `Execute` | défaut sélecteur nul |
|---|---|---|---|---|
| `+0x00` | `+0x60` | `+0x00` | (non lu par le port) | 0 |
| `+0x08` | `+0x68` | `+0x08` | `Nullable<PathfinderType>` (#448-r1-r1-r2) | vide |
| `+0x10` | `+0x70` | `+0x11` **inversé** | gate de `SetMovedFlag` | VRAI → octet **0** → flag POSÉ |
| `+0x18` | `+0x78` | `+0x10` **inversé** | gate de `Add(ArrivedAtFinalTile)` + `On(0x1c)` | FAUX → octet **1** → flag **NON posé** |
| `+0x20` | `+0x80` | `+0x14` | **`isInterimStep`** | 0 |
| `+0x28` | `+0x88` | `+0x15` | `allowNullTargetPosition` | 0 |
| `+0x30` | `+0x90` | `+0x13` | arg d'`IsAllowedToMove` | 0 |
| `+0x38` | `+0x98` | `+0x16` | gate de `RecordTilesMoved` | 0 |

Les deux premiers passent par le MÊME `CONCAT11(sel@+0x18, sel@+0x10) ^ 0x101` — **leurs défauts
DIFFÈRENT (VRAI et FAUX)**, ce qui rend l'inversion non-devinable et vérifiable : un move DSL à
options nulles **pose `Moved`** mais **ne pose PAS `ArrivedAtFinalTile`**. Le mapping de `+0x15`
est corroboré par un second usage dans le même `Execute` (le sélecteur `+0x28` y sert aussi de gate
local « liste de tuiles vide autorisée »), ce qui valide toute la chaîne `CONCAT`.

`IdunBattleLogic.Entities.DSLBehaviors$$FlyUnit` alloue un `MoveUnitBehaviourOptions` de 0x40 octets
ZÉRO et n'y écrit QUE `+0x08 = Nullable(3 = Fly)` ⇒ ses six sélecteurs sont nuls ⇒ vecteur COMPLET,
sans `On(0x1c)`.

## 4. La FACE INVERSE — les déplacements que le natif traite SANS vecteur

Le piège symétrique (brancher trop, côté permissif) est réel, et la réponse est LUE :
`IOperationProcessor` porte **DEUX slots distincts**.

| slot | méthode | arité | qui l'appelle | vecteur ? |
|---|---|---|---|---|
| `0x65` | `MoveUnit(unit, unitPosition, triggeringAbilityOrEffect, options)` → `Core.Services.OperationProcessor$$MoveUnit` → `MoveUnitOperation$$Execute` | 4 args | `MoveUnitBehaviour$$Execute` (toutes les feuilles DSL), la lambda de `Visit(CheatMoveUnitMessage)`, le mouvement joueur | **OUI** |
| `0x7e` | `SetUnitPosition(unit, position, <octet>)` → `IdunBattle.Operations.SetUnitPositionOperation$$Execute` | 3 args | `DisplaceUnitOperation$$Execute` (push/pull), `$$SwitchPosition`, `ReviveUnitOperation$$SetRevivePosition`, et `MoveUnitOperation$$Execute` lui-même pour écrire la position | **NON** |

`SetUnitPositionOperation$$Execute` écrit les tuiles, le `TileContentComponent` et la « position
précédente du tour », puis `VerifyTerritoryCapture`. Il **n'émet AUCUN event** : ni pre-move, ni
`KillSteppableUnits`, ni `SetMovedFlag`, ni after-move. (Le 3e argument est un gate de
`ResetPreviousTile` : `0` au push, `1` au switch.)

Le fait que le slot `0x7e` prenne 3 arguments n'est pas déduit : le thunk d'invocation
(`FUN_180009770`) charge son 3e argument par `movzx r9d, byte [rsp+0x28]` — un OCTET — et fait un
`jmp` vers la cible. `MoveUnitOperation$$Execute` l'appelle lui-même pour poser la position, ce qui
exclut structurellement que ce soit `MoveUnit` (récursion infinie).

**`IdunBattle.Operations.FleeOperation$$Execute` n'appelle NI l'un NI l'autre** : son déplacement
n'est pas porté du tout (le port en fait une approximation best-effort).

### Ce que cela CORRIGE dans les justifications portées

`record_tiles=False` au push et `set_moved=False` au switch étaient attribués aux octets
`+0x16` / `+0x11` d'un `MoveUnitOptions` que ces call-sites **ne passent pas**. Les VALEURS restent
justes (le natif n'y fait ni l'un ni l'autre), la RAISON était mal nommée. Corrigé dans les
docstrings.

## 5. Le port, call-site par call-site

`MoveUnitOperation` gagne trois paramètres. Deux sont des octets d'options natifs
(`is_interim_step` = `+0x14`, `arrive_at_final_tile` = `+0x10` inversé) ; le troisième,
`emit_after_move`, **n'est pas un octet** — il enregistre le fait, PORT-LEVEL, que le call-site
mirroite `SetUnitPositionOperation$$Execute` (le port utilise `MoveUnitOperation` comme stand-in à
ces sites, écart PRÉEXISTANT et non touché par cette tranche).

| call-site du port | artefact natif | vecteur |
|---|---|---|
| `MovementHandler.visit_MoveUnitMessage` | `Visit(MoveUnitMessage)` → slot `MoveUnit`, options nulles | COMPLET, `On(0x1c)` inclus |
| `behaviours/movement.py::FlyUnit` | `DSLBehaviors$$FlyUnit` | COMPLET **sans** `On(0x1c)` |
| `behaviours/movement.py::MoveUnit` | `DSLBehaviors$$MoveUnit` (ThunderousAssault, TheBetrayer, HarlequinsPanoply) | idem |
| `triggers/genestealer.py` (Hypersensory) | `...MoveAndSpawnDecoy$$CreateBehaviour`, call-site de `DSLBehaviors$$MoveUnit` | idem — la mention « PAS after-move » qui y figurait est **RÉFUTÉE** |
| `abilities/loki/quickening.py` (×2) | `TheQuickeningAbility$$GetMoveInBehaviour` / `$$GetMoveOutBehaviour`, call-sites de `DSLBehaviors$$MoveUnit` | idem |
| `operations/summon_ai.py` | move d'IA = même chemin que `MoveUnitMessage` | COMPLET (et `movement_steps` désormais RENSEIGNÉ — il était `None`) |
| `operations/displace.py` push / pull / switch ×2 | `SetUnitPosition` | **AUCUN** |
| `operations/behaviour.py` flee | ni l'un ni l'autre | **AUCUN** |

`triggers/loki/betrayer.py` : l'`Emit("BetrayerAfterMove")` explicite est **retiré**. Sa propre
docstring prescrivait ce retrait « le jour où l'INCRÉMENT 1b repliera `EvaluateAfterMoveTriggers`
dans l'Operation ». Le payload de trace est préservé : la feuille `MoveUnit` publie désormais
`after_move` dans son `ectx.emit`.

Deux probes appelaient `after_move_triggers` juste après un `MoveUnitOperation` — doublon supprimé
(`probe_230_load_state_turn_state.py`, `probe_366r1_echoes_revive.py`).

XREFS exhaustives des deux factories DSL, relevées dans cette tranche : `DSLBehaviors$$MoveUnit` =
**30 call-sites CODE**, `DSLBehaviors$$FlyUnit` = **8** (7 abilities).

## 6. La mesure LIVE — discriminant énoncé AVANT

`FullThrottleAbility$$CreateTrigger` = `On(0x24) & OwnerIsActor & MovementSteps() >= 3`, behaviour
`If(Maybe(30), Kill(Caster))`. C'est le SEUL lecteur de `movementSteps` du binaire.

Montage #571 rejoué (`probe_448_r1_r1_r2_fly_override.py --seeds 777 --rounds 40 --want 3`) :
`FullThrottle` greffé sur `spaceHound` (Tjark, HERO du pool, ni `Flying` ni `Burrow`), qui caste
`1090 GrapnelLauncher` — dont le `If` final est `FlyUnit(Caster, <tuile d'origine de la cible>)`.

| bras | essais | morts |
|---|---|---|
| **A** — vol à `d >= 3` (gate VRAI) | **7** | **1** |
| **B** — vol à `d < 3` (gate FAUX) | **2** | **0** |

Une mort **EXIGE** que le gate ait été évalué, donc que le natif ait publié `On(0x24)` **sur un
déplacement joué par une feuille DSL**. Le port d'avant rendait `0` par construction (aucun vecteur
sur ce chemin), quel que soit `d`. Cumulé avec la mesure #571 (5/26 au bras A) : **6 morts / 33 vols**.

### Les gardes, et leurs contre-épreuves JOUÉES

* `test_448_r1_r1_r2_r1_dsl_after_move_offline.py` (16 tests) — la séquence aux QUATRE combinaisons
  de gates, le fait que l'Operation joue le vecteur, que le handler ne le double pas, que la relance
  après override ne le joue qu'une fois ; et le relevé **AST** (jamais un comptage de chaîne) des
  kwargs de chaque `MoveUnitOperation(...)` par module.
  **Contre-épreuve** : `emit_after_move` forcé à False → **3 tests rouges**.
* `test_448_r1_r1_r2_r1_dsl_after_move_live.py` (3 tests) — trois bras sur le même état greffé :
  DSL (`FlyUnit`), TÉMOIN (mouvement ordinaire), INVERSE (`emit_after_move=False`).
  **Contre-épreuve** : l'état PRÉ-tranche restauré (vecteur retiré de l'Operation *et* rendu au
  handler) → **le SEUL bras DSL rougit**, témoin et inverse verts. La garde mord exactement sur son
  gisement.

## 7. Non-régression jouée (2026-08-04)

| fichier | verdict |
|---|---|
| 10 fichiers offline de la zone (full throttle, flying steps/tiles, grapnel, tiles-moved call-sites, triggered-move-anchor, overwatch, kill-unit) | **155 passed** |
| `test_448_r1_r1_full_throttle_live` / `test_overwatch_live` / `test_thebetrayer_take_turn_migration_live` / `test_the_quickening_live` | 3 / 1 / 2 / 1 passed |
| `test_hypersensory_moveandspawndecoy_live` / `test_thunderous_assault_push_live` / `test_arcaneshield_vector_live` / `test_camo_cloak_seed_move_live` | 5 / 2 / 7 / 7 passed |
| `test_448_r1_r1_r1_flying_movement_steps_live` / `test_448_r1_r1_r1_r1_flying_tiles_moved_live` / `test_spiritual_leader_live` / `test_runner_move_live` | 5 / 8 / 5 / (2 + 1 xfail) passed |
| `test_harlequins_panoply_live` / `test_lion_helm_overwatch_aura_live` / `test_tiles_moved_combat_live` / `test_overwatch_single_shot_per_activation_live` | 10 / 3 / 8 / 1 passed |
| `test_443r1_savior_protocols_move_term_live` / `test_443r2_only_active_overwatch_live` / `test_cursed_plague_bell_extramove_live` | 5 / 7 / 4 passed |

**ROUGE PRÉEXISTANT, non introduit par cette tranche** : `test_437_overwatch_consumes_armour_live.py`
(2 failed / 2 passed). Vérifié en RÉTABLISSANT `scripts/python/engine` au commit de base
(`d51f25f0`, le merge de #571) et en rejouant : **chiffres IDENTIQUES au point près** — natif
`384720`, port `384721` (écart **1**), bras muté `395173` des deux côtés. Le fichier n'est pas au
ledger #462. Résidu à ouvrir séparément.

## 8. Ce que la tranche ne porte PAS, nommément

* **Aucun call-site du port ne pose `is_interim_step=True`** — le paramètre est porté (c'est la face
  inverse du vecteur, et l'omettre serait permissif) mais aucune feuille DSL portée n'a son sélecteur
  `MoveUnitBehaviourOptions+0x20` non nul. Il servira au premier port qui en aura un.
* **Les options du 3e call-site `MoveUnit` porté** (`HarlequinsPanoplyAbility$$CreateBehaviour`) ne
  sont pas re-lues ici : la constante `_DSL_ARRIVE_AT_FINAL_TILE` lui est appliquée par défaut de
  feuille, pas par mesure. (Celles de ThunderousAssault et de TheBetrayer l'ont été par les tranches
  qui les ont portées ; celles de `FlyUnit` dans cette tranche-ci.)
* **`TheQuickening`** : le port fait l'échange DIRECT (une Operation par unité) là où le natif fait
  lift-off + move-in — il joue donc UN vecteur par unité quand le natif en joue deux (celui du
  lift-off part avec `movementSteps = 0` par la branche « position VIDE »). Sous-comptage assumé,
  même sens que le résidu `#347-r1`.
* **Le port utilise `MoveUnitOperation` comme stand-in de `SetUnitPositionOperation`** aux quatre
  sites de déplacement forcé : il y exécute donc aussi les pre-move triggers, `KillSteppableUnits`,
  `UpdateCharging` et le refresh d'auras, que le natif n'y fait pas. Écart PRÉEXISTANT ; cette
  tranche l'a seulement empêché de s'aggraver d'un vecteur.
* **`path`** n'est toujours pas matérialisé dans `MoveUnitOperation` (`#448-r1-r1-r2-r2`), ni la
  branche « position VIDE » du vecteur (le port n'a pas de mouvement vers une `UnitPosition` vide).
* **`On(0x1c)` sur un move DSL** est désormais NON émis. Aucun consommateur porté
  (`SpiritualLeaderAbility`, `ArcaneShieldAbility`) n'en dépendait — ils ne le recevaient de toute
  façon pas, puisque le vecteur entier était muet sur ce chemin.

## 9. Reproduction

    python -m pytest scripts/python/tests/engine/runner/test_448_r1_r1_r2_r1_dsl_after_move_offline.py
    python -m pytest scripts/python/tests/engine/runner/test_448_r1_r1_r2_r1_dsl_after_move_live.py
    python scripts/python/probe_448_r1_r1_r2_fly_override.py --seeds 777 --rounds 40 --want 3 --out <ABSOLU>
