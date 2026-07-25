# #98 — Conversion ROUNDS → TOURS des durées d'effet (réconciliation des call-sites)

**Artefact natif** : `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` **@181058af0**.

```
count = 0
foreach id in BC.Player.TurnOrder:                  # this+0xa0 = BattleConfiguration ; +0x30 -> +0x18
    player = StateExtensions.GetPlayer(state, id)   # this+0x38 = match.state
    comp   = player.GetComponent<PlayerComponent>()
    if comp+0x20 != 2:                              # 2 = Environment -> NON compté
        count += 1
return count * rounds
```

`BattleQuery..ctor @1810727b0` : `+0x38 = state`, `+0xa0 = param_3` ; l'appelant unique est
`IdunRunner..ctor @180e38500` (`BattleQuery..ctor(match.state, bc)`) → **`+0xa0` = la
`BattleConfiguration`**. Le seed BC du projet expose `Player.Players = {11: PlayerType 0,
12: PlayerType 1, 13: PlayerType 2 (Environment)}` et `Player.TurnOrder = [11, 12, 13]` ⇒ dans
**tout duel standard, le facteur vaut 2**.

## Les 4 étages, mesurés séparément

| Étage | Ce qui est mesuré | Résultat |
|---|---|---|
| **E1 — valeur de config** | `StaticBattleRules.Effect.DefaultAmountOfRounds @181559ff0` | `Pinned 1065` = **1 round**, `Ice 17` / `Fire 5` / `Contaminated 1244` = **2 rounds**, `79` = 3 |
| **E2 — unité / facteur** | `ConvertRoundsToTurns` = `count(TurnOrder, PlayerType != 2)` ; observable via `observeBattle.counts.player` | `counts.player = 3` → **facteur 2** |
| **E3 — tick de décrément** | `RefreshEffects @180e6bf70`, appelé par `EndTurnOperation.Execute @180e6b3c0` | **1 décrément par tour de joueur** (donc 2 par round à 2 joueurs). Le port fait déjà exactement ça (`EndTurnOperation` → `EffectsState.on_turn_end` sur toutes les unités) — **étage CONFORME, non touché** |
| **E4 — instant de lecture** | `decisionView.effects[].remaining` = `EffectComponent.RemainingTurns @+0x64` (brut) | Mesure **PRE-tick** obligatoire : voir le piège ci-dessous |

### Le piège E4 (la raison pour laquelle le bug a survécu si longtemps)

En **1v1 strict**, le cast est l'action de la **seule** unité du camp → `AddFlagsAfterAbilityExecution`
→ `FinishUnitTurn` → le moteur **clôt le tour** → `EndTurnOperation` → `RefreshEffects` décrémente
**avant** qu'on relise `decisionView`. La valeur lue est `durée_posée − 1`, ce qui **mime exactement
l'identité rounds = turns**.

Preuve directe (probe `probe_9899_e4.py`, runner 1v1 `templSwordBrother` vs `tyranTyrantGuard`) :

```
AVANT cast : currentPlayer=3  mes unites vivantes=1
APRES cast : ok=True currentPlayer=4  remaining(1162)=1
VERDICT : tour CHANGE (tick auto) -> lecture POST-TICK
```

Avec **2 unités côté joueur** (l'autre non activée), le tour ne bascule pas et la même pose donne
`remaining = 2`. C'est ce faux datapoint qui avait été gravé dans `turns_from_rounds` (« count = 1
dans nos runners, PROUVÉ par test_effect_stun_live ») **et** dans `fire.py` (« le feu = 2 turns →
CORRECT ») : les deux affirmations sont RÉFUTÉES.

## Les deux voies natives converties — et la troisième qui ne l'est PAS

`AddEffectOperation.Execute @180e48940` (cascade `lVar14`, mirror exact) :

1. `param_6.NullableA.HasValue` → la valeur **telle quelle** (l'appelant l'a déjà convertie) ;
2. sinon `DefaultAmountOfRounds(type).HasValue` → **`ConvertRoundsToTurns(rounds)`** (slot d'interface
   `0x1b`, `FUN_180003b40(0x1b, …, battleQuery, rounds)`) ;
3. sinon `0` = **permanent**.

Et le nœud DSL `TurnsFromRounds(n)` (`DSLFactory.TurnsFromRounds @180dfec50` →
`TurnsFromRoundsFormula.Calculate @180f26a50`) appelle **le même** slot `0x1b`.

⇒ **converties** : la durée par défaut (branche 2) et tout `TurnsFromRounds(n)` explicite.
⇒ **NON converties** : les durées passées en `Nullable<int>(n)` ou en nœud `Direct(n)@0xc0` — elles
sont **déjà en TOURS**. Les convertir les **doublerait** : c'est le risque n°1 d'une réconciliation
faite en aveugle.

## Port

- `engine/runner/abilities/base.py` : **`convert_rounds_to_turns(state, rounds)`** (mirror 1:1).
  `turns_from_rounds` reste, mais documenté comme **identité LEGACY, à ne plus utiliser pour une durée**.
- `engine/runner/state.py` : `State.turn_order_player_count` (le facteur).
- `engine/runner/snapshot.py` : seed depuis `observeBattle.counts.player − 1` (l'Environment est
  l'unique joueur `PlayerType == 2` de toute BC). `None` → identité : les états construits à la main
  dans les tests unitaires gardent leur comportement.
- `engine/runner/abilities/behaviours/effects.py` : `_resolve_duration(state, duration_rounds,
  duration_turns)` — **deux canaux explicites**, `duration_turns` prioritaire.
- `engine/runner/operations/effects.py` : la branche `DefaultAmountOfRounds` est convertie.

## Inventaire des call-sites (chacun tranché au décompilé)

### CONVERTIS — le natif passe `TurnsFromRounds(n)`

| Call-site | Artefact natif | rounds | avant → après (facteur 2) |
|---|---|---|---|
| `strike.py` ThunderousAssault `Stunned` | `ExecuteBehaviour @1812158b0` | 1 | 1 → **2** (live = 2) |
| `stormcaller.py` `Stunned` (Flying) | `ExecuteBehaviour @18120cc20` | 1 | 1 → 2 |
| `splash.py` CrushingClaws `Taunted` | `ExecuteBehaviour @1811cd5e0` | 1 | 1 → 2 |
| `summon.py` GetEmRuntz `Taunted` | `ExecuteBehaviour @1811e2210` | 1 | 1 → 2 |
| `strike.py` CordClaw `1250` | `ExecuteBehaviour @1811ccbf0` | 2 | 2 → **4** |
| `effect_triggers.py` `Contaminated_Unit 0x4dd` | `ContaminatedEffect.AddEffectBehavior @180f39e30` (`AddDynamicStatModifierEffect(…, TurnsFromRounds(1))`) | 1 | 1 → 2 |
| `mv71.py` `Markerlight` | `Sum(TurnsFromRounds(1), Direct(1))` @181108900 | 1 (+1) | 2 → **3** |
| `arcane_shield.py` `CreateShield` (bouclier) | `CreateBehaviour @180e16b40` | 1 | 1 → 2 |

### DURÉE PAR DÉFAUT (`duration_rounds=None`) — converties dans `AddEffectOperation`

`Pinned` (SuppressiveFire, CrushingClaws, admec, splash), `Ice` (AnvilShield, LordOfTempests,
Stormcaller, GreatFrostAxe), `Contaminated` de tuile (RadSaturation), `ValkyrieStrike 1022`,
`MasterAnnihilator 1249`, `FleshmetalGuns 1067/1212/1221`, `Protector`/`Conqueror`…
Seuls les types **présents dans la table** `DefaultAmountOfRounds` changent (les autres → 0 = permanent,
inchangé).

### NON CONVERTIS — le natif passe `Direct(n)@0xc0` / `Nullable<int>(n)` (déjà en TOURS)

| Call-site | Artefact natif | canal |
|---|---|---|
| `orks.py` Waaagh 1099/1100/1101 | `GetBuffBehaviour @18122b900`, durée `df@0xc0` | `duration_turns=1` |
| `summon.py` MasterOfTheTutelaries 1197 | `ExecuteBehaviour @1811f30c0`, durée `df@0xc0` (**résidu « nœud non résolu » FERMÉ**) | `duration_turns=1` |
| `weaver_of_fate.py` 1185 | `CreateBehaviour @1811acb90`, `Nullable<int>(1)` | `duration_override=1` |
| `genestealer.py` Decoys 1379 | `CreateBehaviour @180e1fe30`, `df@0xc0` | `duration_override=1` |
| `genestealer.py` Hypersensory 1407 | `CreateBehaviour @180f878f0`, `df@0xc0` | `duration_override=1` |
| `strike.py` BlackRage 1342/1343/… | durée `0` | inchangé (permanent) |

### Corrections de CANAL (le port passait `1` là où le natif ne passe RIEN)

| Call-site | Décompilé | correction |
|---|---|---|
| `fire.py` `on_fire_damage_tree` | `AddEffect(factory, 5, stateRef, Tiles(target))` @1811c3a60 — **4 args, aucun nœud durée** | `duration_rounds=None` → `DefaultAmountOfRounds(5)=2` → **4 tours**. Avant : `1` — et le port divergeait de son PROPRE autre chemin de pose du même effet (`SetOnFire`, qui n'override rien) |
| `act_of_faith.py` | `AddEffect(factory, 0x3f9, stateRef, self@0x148, 0, 0)` @181219a70 — slot durée NULL, `DefaultAmountOfRounds(0x3f9)` absent | `duration_rounds=None` → **permanent** (les stacks sont retirés par `ActOfFaith_RemoveEffectAbility @181219eb0`, déjà porté). Avant : `1` → les stacks s'évaporaient au 1er tick |

## Résidu explicite

**`betrayer.py` (TheBetrayer 0x4f3)** — `CreateBehaviour @1811a4a00` passe une struct d'options
**zéro** (durée par défaut) et `DefaultAmountOfRounds(0x4f3)` est absent ⇒ le natif pose un effet
**PERMANENT**. Le port **garde 1 tour** (`duration_turns=1`, valeur historique **gelée**) : aucun
vecteur de retrait de `0x4f3` n'est identifié (ni `TheBetrayer_TakeTurnAbility.CreateBehaviour
@1811a4f70`, ni les autres membres du kit), donc passer en permanent ferait rejouer Kharn à **chaque**
tour indéfiniment — régression fonctionnelle non mesurée. À instruire séparément (trouver le
`RemoveEffect(0x4f3)` natif, ou mesurer live le cycle de la rage).

La docstring de `betrayer_add_effect_tree` portait l'ancienne lecture (« `local_588[0] = 1` est la
durée ») : **réfutée** (c'est le NIVEAU, `EffectComponent.Level @+0x68`, cf.
`IncreaseEffectLevelOperation.Execute @180e73cb0`) — corrigée sur place.

## Validation live

| Mesure | Live (natif) | Port | Voie |
|---|---|---|---|
| `Stunned 1162` (ThunderousAssault) | **2** | 2 | `TurnsFromRounds(1)` |
| `Pinned 1065` (SuppressiveFire) | **2** | 2 | `DefaultAmountOfRounds = 1 round` |
| `Ice 17` (AnvilShield, blocage 100 %) | **4** | 4 | `DefaultAmountOfRounds = 2 rounds` — **généralisation sur une autre durée** |
| facteur | `counts.player = 3` → 2 | 2 | — |

Tests : `tests/engine/runner/test_effect_duration_rounds_live.py` (5 cas : facteur seedé, les deux
voies live, séparation des canaux offline, cascade `AddEffectOperation` offline) ;
`test_effect_stun_live.py` **durci** (2 unités côté joueur ⇒ lecture PRE-tick assertée, oracle
`ConvertRoundsToTurns(DefaultAmountOfRounds)`, nombre de ticks du cycle de vie lu du natif) ;
`test_lot_pose_live.py::test_anvil_shield_…` (durée d'Ice live == offline).
