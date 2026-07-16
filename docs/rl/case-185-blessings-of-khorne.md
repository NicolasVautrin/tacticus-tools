# Case #185 — BlessingsOfKhorne (Azkor) dmg% reduction/bonus scaled by melee-defeats

**Status: offline RE COMPLETE + numeric constants read from gameconfig. PORT deferred: the
scaling count `N` = "normal units defeated by melee this battle" is a battle-history metric the
engine does not track (prediction path) — same capture blocker as #184, to be batched into the
NEXT reinject. Carrier = `worldEightbound` (Azkor). Spun off from case-184 (bloodMephiston Psychic
normal attack was reduced x~0.70 vs Azkor).**

## Carrier
`worldEightbound` (Azkor, lineup) traits = `[Hero, BlessingsOfKhorne, Daemon, Resilient,
Terrifying, Unstoppable]`. Active `OverwhelmingWrath` (1141), passive `BeaconOfRage` (1236). The
trait BlessingsOfKhorne materializes the effect `BlessingsOfKhorne_ModifiersEffect` (two DSL
value-modifications: a DEFENSE malus and an ATTACK bonus, both scaled by the same multiplier).

- `UnitTrait.BlessingsOfKhorne = 1046` (carrier trait id — what the task calls "trait 1046").
- `TriggeredAbilityType.BlessingsOfKhorne = 1216` (= `0x4c0`, the effect's config-owner id).

## The two value-modifications (decompiled)

### DEFENSE malus — `CreateEffectDamageMalusForDefense @180f34c50`
`ForPercentDecrease`, magnitude = `ConfigConst(key 0x4c = DmgPctReduction) x GetMultiplierBasedOnDefeatedInMelee`,
gated by `op_BitwiseAnd(get_OwnerIsTarget, DamageProfileIs(0xd = Psychic))`.
=> when the carrier is the TARGET of an incoming **Psychic** attack, incoming damage is reduced by
`DmgPctReduction% x mult`. This is the case-184 symptom (bloodMephiston Psychic normal attack on Azkor).

### ATTACK bonus — `CreateEffectDamageBonusForAttack @180f34ae0`
`ForPercentIncrease`, magnitude = `ConfigConst(key 0xf = ExtraDmgPct) x GetMultiplierBasedOnDefeatedInMelee`,
gated by `get_OwnerIsCaster` ALONE (NO `DamageProfileIs` filter).
=> when the carrier is the CASTER, ALL its outgoing damage (every profile) is increased by
`ExtraDmgPct% x mult`. **This is a SECOND gap** (the carrier's own attacks are buffed too), not just
the defense reduction the task title names.

## The multiplier — `GetMultiplierBasedOnDefeatedInMelee @180f34ea0`
```
set   = NormalUnits(UnitsDefeatedByMeleeAttack(AllUnits))     // normal units defeated by melee this battle
base  = Count(set)                                            // GLOBAL — any killer, both teams
self  = If(ActorHasTriggeredAbility(owner@0x148, 1460=TalismanOfRage),
           Count(Filter(set, AreEqual(Killer@0x180, owner@0x148))),   // owner's OWN melee kills
           0)                                                          // else literal 0 (arg @0xb8)
mult  = Min(Sum(base, self), ConfigConst(key 0x43 = MaxDefeatedUnits, owner 0x4c0=BlessingsOfKhorne))
```
- **base count is GLOBAL**: every normal unit that died to a melee attack this battle (either team),
  NOT just the carrier's kills.
- **self-kill bonus** (double-counting the carrier's own melee kills) fires ONLY if the carrier has
  TriggeredAbility **1460 = TalismanOfRage**. Azkor has `BeaconOfRage` (1236), NOT TalismanOfRage —
  so for Azkor this branch is **INERT**: `mult = Min(base, 8)`.
- `ConfigConst` signature reconciled = `ConfigConst(battleQuery, constantKey, configOwnerId, flag)`:
  malus `(0x4c, ownerId@param2+0x60)`, bonus `(0xf, ownerId@param2+0x60)`, cap `(0x43, 0x4c0=1216)`.

## Numeric constants (read offline from gameconfig `globalValues.traitVariables`)
| gameconfig var | RE key | value | role |
|---|---|---|---|
| `blessingsOfKhorneDmgPctReduction` | 0x4c | **8** | defense: -8% Psychic per melee-defeat |
| `blessingsOfKhorneExtraDmgPct` | 0xf | **3** | attack: +3% own-damage (all profiles) per melee-defeat |
| `blessingsOfKhorneMaxDefeatedUnits` | 0x43 | **8** | cap on `mult` |

**Resolved formulas** (`N = min(count_melee_defeats [+ TalismanOfRage self-kills], 8)`):
- DEFENSE (Psychic incoming, owner=target): `dmg *= (1 - 0.08*N)` — max **-64%** at N>=8.
- ATTACK (owner=caster, ALL profiles): `dmg *= (1 + 0.03*N)` — max **+24%** at N>=8.

The case-184 note "x0.70" was ROUNDED: with an 8%/kill step the exact factor is `1 - 0.08*N`
(integer N) => N=3 -> x0.76, N=4 -> x0.68. Exact N (hence the exact factor) is pinned live at
reinject via the captured count.

Psychic profile (`damageProfiles.Psychic`) = `PiercingRatio 100, Traits [NoBlocking]` (fully
armor-piercing, unblockable) — consistent with the observed reduction acting on a raw Psychic hit.

## The capture blocker (why PORT is deferred — same as #184)
`N` needs "which dead units were defeated by a melee attack" (+ killer, for TalismanOfRage carriers).
`UnitsDefeatedByMeleeAttackSelector.IsValidUnit @180f00b40` keys on a per-unit **component bool @0x178**
(the "defeated-by-melee" marker; component resolved via the game's GetComponent, class ref
`DAT_1831c3090`), plus a summon/health refinement (`HasFlag 9 / 0x14 / 0xe`, `HealthComponent.IsDead`).
The engine's captured `actorStats` has only `totalAttacksMade/totalTurnsWithAttacksMade`
(@+0x20/+0x30) — no defeated-by-melee marker and no per-death killer. So:

- **Prediction path** (oracle/aiPlaybookPredict against a live-captured scene): needs a NEW frida
  capture — per dead unit `defeatedByMelee` (@0x178) + `killerId` — surfaced in decisionView/
  combatSnapshot. **Reinject-gated. Batch with #184's reinject.**
- **Runner path** (full sim): the runner itself applies damage and kills units, so it CAN track
  `defeated_by_melee` + `killer` per death with NO capture. This path is independently portable and
  live-validatable (no reinject), but is a larger change (death-cause tracking + effect materialization).

## Port sites (when unblocked)
- Defender/attacker modifier build — same place Trench (#181) and the defender-modifier layer live
  (`engine/.../damage_modifiers` / `build_defender_modifiers_from_effects`): add a BlessingsOfKhorne
  materialization keyed on `N`.
- `N` source: `count(dead NORMAL units with defeated_by_melee) [+ if carrier has TalismanOfRage 1460:
  count(those killed by carrier)]`, capped at 8.
- Live confirm (needs #184 fixed so the normal-attack weapon-select is right AND the reinject
  capture): bloodMephiston Psychic normal on Azkor -> `x(1 - 0.08*N)` with N = melee-defeats so far.

## Anchors (VAs, gqfc5mff6c)
BlessingsOfKhorne_ModifiersEffect.CreateEffectDamageMalusForDefense @180f34c50 (defense, Psychic-gated) ;
CreateEffectDamageBonusForAttack @180f34ae0 (attack, OwnerIsCaster, all-profile) ;
GetMultiplierBasedOnDefeatedInMelee @180f34ea0 ; UnitsDefeatedByMeleeAttackSelector.IsValidUnit
@180f00b40 (per-unit @0x178 defeated-by-melee flag, class ref DAT_1831c3090) ;
DSLFactory.ConfigConst / UnitsDefeatedByMeleeAttack / NormalUnits / Killer / AreEqual / Filter /
ActorHasTriggeredAbility / If / Sum / Count / Min. Constants: DmgPctReduction key 0x4c = 8,
ExtraDmgPct key 0xf = 3, MaxDefeatedUnits key 0x43 = 8 ; TalismanOfRage = 1460 (0x5b4) ;
BlessingsOfKhorne trait 1046 / config-owner 1216 (0x4c0) ; Psychic DamageProfileIs arg = 0xd.
