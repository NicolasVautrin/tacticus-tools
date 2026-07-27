# O3 — effets de TUILE : la DYNAMIQUE (expiration + transition d'entrée)

Build `gqfc5mff6c`. Le SEED des effets de tuile est clos depuis `case-102` (merge `c5d9e8d`) : un état
offline rechargé porte les mêmes effets de tuile que le live, durées comprises. Ce qui manquait, c'est
la suite : **un effet de tuile ne mourait jamais, et une unité qui entrait sur une tuile de couverture
n'y gagnait rien**. Les deux faces sont portées ici.

---

## 1. RE — qui fait vivre et mourir un effet, côté natif

### 1.1 Le tick de durée ne connaît pas les unités

`IdunBattle.Operations.EndTurnOperation$$RefreshEffects(op, state, buffer)` n'itère **pas**
`GetAllUnits` (que son appelant `IdunBattle.Operations.EndTurnOperation$$Execute` utilise ailleurs,
et que Ghidra nomme explicitement). Il énumère une **collection générique d'entités-EFFET** : la
boucle lit directement un `EffectComponent` sur chaque élément, et le MÊME MethodInfo alimente
`IdunBattle.Entities.EntityExtensions$$GetEffectsBySourceUnit` (qui y lit `SourceUnitId @+0x10` et
`EffectType @+0x58`), `idun.Ui.TileInfoBarData$$Create` et
`idun.Idun.Source.IdunMeta.View.Hud.Screens.DebugSettingsScreen.BattleDebugPopup$$RefreshEntities`.

> **Conséquence structurante : il n'existe AUCUNE distinction porteur-unité / porteur-tuile dans le
> tick de durée.** Un feu posé sur une tuile et un Stun posé sur une unité vieillissent par le même
> code, au même moment.

Le corps de la boucle :

```
if (ec->Removed @+0x5f == 0 && ec->HasTurns @+0x5d != 0) {
    EffectComponent$$RemoveOneTurn(ec);          // if (0 < ec->Duration @+0x64) ec->Duration -= 1
    ... events 0x16 (UpdateEffectTurns) / 0x15 ...
}
```

`IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn` est donc **clampé à 0** : le compteur
ne descend jamais en négatif.

### 1.2 À zéro, l'entité-effet est RETIRÉE

`EndTurnOperation$$RefreshEffects` se termine en enfilant une `RefreshEffects` (slot 0x2f du buffer
d'opérations, raison `6`). `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` ouvre sur :

```
if (ec->Removed @+0x5f != 0) return ;                              // déjà retirée
...
if (EffectComponent$$ShouldBeRemoved(ec))                          // HasTurns && Duration == 0
        -> RefreshEffectsOperation$$DeactivateEffect(...) + retrait   (branche de sortie)
else    -> ShouldBeActive(...) ? ActivateEffect : DeactivateEffect    (branche nominale)
```

`IdunBattle.Entities.Components.EffectComponent$$ShouldBeRemoved` = `HasTurns @+0x5d && Duration @+0x64 == 0`.
**À zéro, l'effet n'existe plus** : ni gate de présence, ni trigger.

### 1.3 La couverture se pose à l'ENTRÉE sur la tuile

`IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility` est une ability portée par le
**tile-def** (terrain `DryBush` sur ce build) :

```
CreateTrigger   = ( On(0x19=MatchInit) | On(0x33=UnitAdded) | On(0x24=UnitPositionChanged_1)
                  | On(0x2e=UnitRevived) | On(0x2f=UnitResurrected) )
                  & NOT AmountIsZero( UnitsThatNeedEffect )
CreateBehaviour = AddEffect( 0x3f5 = 1013 LightCover, AbilityStateReference, UnitsThatNeedEffect )
UnitsThatNeedEffect = UnitsWithoutTraits( EntitiesWithoutEffects( Units(coverPatch@0x148, 1, 3),
                                                                 [0x3f5] ),
                                          <liste statique du cctor>, 3 )
.cctor : List.Add(0x3f9) ; List.Add(0x405) ; List.Add(0)
         = UnitTrait BigTarget(1017) / Vehicle(1029) / Mounted(0)
```

`On(0x24 = UnitPositionChanged_1)` est le **premier** des trois events qu'émet
`IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers` (`0x24` → `0x4` → `0x1d`) et le
premier de ceux d'`IdunBattle.Operations.DisplaceUnitOperation$$EventAndAbilitiesAndEffects`
(`0x24` → `0x23` → `0x1d`). C'est le vecteur de la transition d'ENTRÉE — marche **et** poussée.

La surcharge `AddEffect` à 4 arguments ne passe **aucun** nœud de durée : la cascade de
`IdunBattle.Operations.AddEffectOperation$$Execute` tombe sur `DefaultAmountOfRounds(1013)` = NULL
(1013 est hors du switch de `StaticBattleRules.Effect$$DefaultAmountOfRounds`) → durée `0` =
**PERMANENT**. C'est exactement ce que rend le capteur live (`remaining = 0`).

**La SORTIE n'est PAS un retrait**, et c'est déjà porté (A3) : le natif conserve l'effet et le
neutralise au calcul, par le gate `AreEqual(Tiles(coverPatch@0x148), Tiles(target@0x178))` de
`IdunBattle.Entities.Effects.Loki.LightCoverEffect$$CreateEffectHitsBonusForAttack`. Ground truth
live (`test_lightcover_gate_live.py`) : hors-cover, `LightCover` est toujours présent et la réduction
tombe. Le résidu O3 énonçait ce gate comme non porté — il l'est depuis `d9d0e6c`.

---

## 2. Ce que le port faisait

### 2.1 Expiration — le décrément avait lieu, le RETRAIT non

Contrairement à ce qu'affirmait `case-102` §5.3, `EndTurnOperation.execute`
(`runner/operations/turnflow.py`) balaye **toutes** les clés de `state.effects.by_unit`, ids
d'entité-tuile compris : les timers de tuile étaient bien décrémentés. Le trou était ailleurs, et
double :

1. `EffectsState.on_turn_end` décrémentait **sans plancher** → `remaining_turns` partait en négatif ;
2. **rien ne retirait l'instance**. `BaseEffect.expired` (`remaining_turns <= 0`) n'est lu que par
   `EffectsState.active_effects` et `refresh_stat_modifier_effects`. Les deux lecteurs de PRÉSENCE —
   `EffectsState.has_effect` et `dispatch.collect_effect_triggers` — ne filtrent que `consumed`.

Pour une UNITÉ, `active_effects` masquait la moitié du problème (les contributions de dégât
s'arrêtaient), mais les gates `has_effect` (Pinned, Cursed, Protector…) et les effet-triggers
continuaient. Pour une TUILE, `has_effect` est le **seul** chemin de lecture : le feu brûlait pour
toujours et re-tickait son DoT à chaque tour.

Mesure du port avant fix, `FireEffect` (5) posé `remaining = 2`, 6 ticks de fin de tour :

```
(remaining, has_effect) = [(1,True), (0,True), (-1,True), (-2,True), (-3,True), (-4,True)]
```

### 2.2 Transition d'entrée — rien

`after_move_triggers` documentait `On(0x24=UnitPositionChanged_1)` comme « aucun consommateur porté »
et ne l'émettait pas ; `displace_triggers` le déclarait « flaggé ». Seul le SEED connaissait les
unités déjà à couvert. Une unité qui courait se mettre dans un buisson pendant le runner-sim
continuait donc d'encaisser tous ses coups ranged.

---

## 3. Le port

| Face | Fichier | Mirror |
|---|---|---|
| Décrément clampé + retrait à 0 | `engine/entities/effects_state.py` (`on_turn_end`) | `EffectComponent$$RemoveOneTurn` + `EffectComponent$$ShouldBeRemoved` → branche retrait de `RefreshEffectsOperation$$RefreshEffect` |
| Pose de la couverture à l'entrée | `engine/runner/operations/triggers/tiles.py` (`light_cover_on_enter`, `LIGHT_COVER_EXCLUDED_TRAITS`) | `LightCoverAbility$$CreateTrigger` / `$$CreateBehaviour` / `$$UnitsThatNeedEffect` / `$$.cctor` |
| Vecteur `On(0x24)` | `engine/runner/operations/triggers/dispatch.py` (`after_move_triggers`, `displace_triggers`) | `MoveUnitOperation$$EvaluateAfterMoveTriggers` / `DisplaceUnitOperation$$EventAndAbilitiesAndEffects` |

La marque de retrait offline est `consumed` — la seule que **tous** les lecteurs honorent. Le gate
d'entrée du tick devient `!consumed && remaining_turns is not None`, mirror de
`!Removed @+0x5f && HasTurns @+0x5d` ; un effet permanent (`remaining_turns is None`, capté
`remaining = 0`) n'est jamais touché.

`light_cover_on_enter` est appelé **directement** (comme `dry_bush_fire_spread` et `first_aid_heal`)
et non via le registre d'effet-triggers : une tile-ability est portée par le tile-def, pas par un
effet — elle n'a rien à y faire. La tuile de cover est identifiée par son `tileDefId`
(`LIGHT_COVER_TILE_ID = "DryBush"`, déjà la source unique côté `entities/effects/loki/hits.py`).

---

## 4. Validation

Chaque garde a été vue **ROUGE** contre le comportement d'avant (monkeypatch de l'ancien corps) avant
d'être vue verte. Fichier : `scripts/python/tests/engine/runner/test_tile_effect_dynamics_live.py`.

| Test | Ce qu'il exerce | Avant → après |
|---|---|---|
| `test_tile_effect_timer_expires_and_is_removed_offline` | tick pur : `Fire(rem=2)` sur une tuile + un permanent témoin | `[(1,T),(0,T),(-1,T),(-2,T),(-3,T),(-4,T)]` → `[(1,T),(0,F),(0,F),(0,F),(0,F),(0,F)]` |
| `test_tile_fire_expires_at_the_same_turn_as_live` | **confrontation live** : Vindicta allume la tuile, on avance les DEUX côtés du même nombre de tours sans rien faire d'autre | offline n'expirait jamais → extinction au **même tour** que le natif (`rem0=2`, trace `[(1, 1, True), (2, None, False)]`) |
| `test_light_cover_is_placed_when_entering_cover_live` | **confrontation live** : une unité entre sur DryBush, le même move est rejoué offline | live `LightCover`, offline rien → live `LightCover`, offline `LightCover` (permanent) |
| `test_light_cover_is_not_placed_on_excluded_trait_live` | **généralisation live** : `orksWarboss` (BigTarget) entre sur DryBush | le natif ne pose rien (`live effects=['BigTarget_AdjacentEffect']`) et le port non plus ; un port sans le gate du cctor pose l'effet → ROUGE |
| `test_entering_cover_reduces_incoming_ranged_hits_offline` | **composition** pose + gate A3 : `necroDestroyer` 6 coups ranged contre une cible qui entre à couvert | `6` coups → `4` coups (oracle `globalValues.lightCoverHitReduction = 2`, plancher `min=Direct(1)` non saturé) |

**Non-régression rejouée** (25 tests, 1 xfail pré-existant, **0 skip**) :
`test_lightcover_gate_live` (3), `test_load_state_tile_effects_live` (3),
`test_env_fire_tile_migration_live` (3), `test_effect_stun_live` + `test_effect_duration_rounds_live`
+ `test_runner_move_live` (8+1 xfail), `test_suppressive_fire_live` + `test_runner_attack_live` +
`test_thebetrayer_rage_duration_live` (6), `test_rad_saturation_live` +
`test_anvil_shield_stun_live` + `test_lord_of_tempests_ice_live` (11).

---

## 5. Ce qui n'est PAS couvert

1. **Les quatre autres events de `LightCoverAbility$$CreateTrigger`** — `MatchInit(0x19)`,
   `UnitAdded(0x33)`, `UnitRevived(0x2e)`, `UnitResurrected(0x2f)`. `MatchInit` est couvert de fait
   par le seed (`load_state` capte les unités déjà à couvert). Restent **le spawn/summon sur une
   tuile de cover** et **le revive/resurrect sur une tuile de cover** : `AddUnitOperation` /
   `ReviveUnitOperation` n'émettent pas ces events dans le port. Même forme que le vecteur porté ici
   (un appel à `light_cover_on_enter` au bon endroit), non fait faute de scénario confrontable monté.
2. **Les autres tile-abilities écoutant l'entrée.** `ThornsBlockMovementAbility` (Swamp) a son propre
   chemin (`apply_tile_defense_on_move`, #198) ; `BrokenIceAbility`, `ShrubBonusDefenseAbility` et le
   pickup de power-up (#B2) restent hors port. Ce commit ne construit **pas** d'infra générique de
   tile-ability-trigger : il porte l'ability nommée, comme les deux précédentes.
3. **`DespoiledGround` (1476)** — explicitement hors périmètre (cf. §6).
4. **Ordre exact du retrait vs les autres étapes de `EndTurnOperation`.** Le natif retire dans une
   opération `RefreshEffects` **enfilée** après le tick ; le port marque `consumed` inline dans le
   tick. Aucun observable ne les distingue aujourd'hui (le retrait précède de toute façon le
   `StartTurn` suivant), mais un consommateur qui lirait l'état *entre* le tick et le refresh verrait
   une différence.
5. **`ChangeEffectTurnsOperation` mis à 0.** `IdunBattle.Operations.ChangeEffectTurnsOperation$$Execute`
   peut poser `Duration = 0` hors fin de tour ; le natif le fait suivre d'un `RefreshEffectOptions(0,
   4, 0, 0, 0)` qui déclenchera le retrait. Côté port, l'instance ne sera marquée `consumed` qu'au
   prochain `on_turn_end`. Fenêtre non exercée par un scénario connu.

---

## 6. Réconciliation avec la tâche #85 (« Infra effets de TUILE mutables »)

**Réduite, pas fermée.** #85 visait `DespoiledGround` (volet 2 de `LetTheGalaxyBurn`) + 2 artefacts.
Ce commit livre la brique de CYCLE DE VIE qui manquait — un effet de tuile à timer vieillit, meurt et
disparaît des gates et des triggers, exactement comme côté natif — et le vecteur d'entrée `On(0x24)`.
`DespoiledGround` reste bloqué sur **deux** manques qui lui sont propres et qui ne sont pas touchés
ici (`case-222` §2) :

- le vecteur **`On(0x10 = DamageDealt)`** n'existe pas dans le dispatch porté, alors que
  `FleshMetalGuns_TileEffectAbility` s'y accroche (`On(0x10) & OwnerIsCaster & HasEffect(Self, 0x4c5)`) ;
- la **classe d'effet 1476** n'est pas portée (seule sa durée l'est : `_DEFAULT_ROUNDS[0x5c4] = 2`,
  `runner/operations/effects.py`).

Ce que #85 gagne : une fois ces deux maillons posés, le `DespoiledGround` ainsi placé **expirera
correctement** — ce qui n'aurait pas été le cas avant ce commit.
