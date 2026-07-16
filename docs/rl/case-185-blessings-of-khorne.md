# Case #185 — BlessingsOfKhorne (Azkor) dmg% reduction/bonus scaled by melee-defeats

**Status: CAPTURE LIVE + PORT PREDICTION FAITS ; DEUX faces VALIDEES BIT-EXACT live (N=1).**
Le residu FLAT ~+217 qui bloquait la face ATTACK etait **BeaconOfRage** (passive 1236 d'Azkor,
PAS un canal BoK) — RE + porte #189 (cf. §BeaconOfRage ci-dessous) ; re-confront session 22 :
ATK engine=(1608,2302) == oracle BIT-EXACT (BoK x1.03 et flat BeaconOfRage composent ensemble).
Le residu « POSITIONNEL » x0.36 (iter-4) est AUSSI RESOLU (#190) : ce n'etait PAS du terrain
(hypothese REFUTEE par mesure — tout Grass, elev egales, toggles no-elev/no-board inertes) mais
**OverwhelmingWrath_RangeDmgReduction** (1301), l'effet TRANSIENT (rem=1) de l'active d'Azkor :
-64% au degat RANGED recu (1-0.64 = 0.36 exact) ; expire a son tour suivant, d'ou le MATCH du meme
couple a iter-5. Porte (loki.py::OverwhelmingWrathRangeDmgReductionEffect) ; re-confront session 22 :
iter-4 engine=(532,798) == oracle BIT-EXACT, PLUS AUCUNE divergence sur le run. Carriers = trait
1046 = TOUTE la faction World Eaters (11 unites : Azkor worldEightbound, Kharn, Wrask, Macer +
bosses LHE).

## Capture live (#185, hooks — VALIDEE session 21)

- `UnitComponent.DefeatedByMeleeAttack` @+0x178 (dump live gqfc5mff6c ; = le byte-gate du selecteur
  `UnitsDefeatedByMeleeAttackSelector.IsValidUnit @180f00b40`, ecrit par `KillUnitOperation.Execute
  @180e76470` param wasMelee) + `UnitComponent.DeathReason` @+0x108 = `Nullable<DamageSource>` →
  killer via l'ENTRY NATIVE `DamageSource.get_KillerId @180e65a10` (appel direct `(this, 0)`,
  PAS runtime_invoke qui unboxerait +0x10 ; layout du Nullable resolu PAR REFLEXION champ
  hasValue/value − 0x10 boxed-header). Surface : `decisionView.units[].defeatedByMelee/killerId`
  (`match-state.ts::readUnitDeathMeta`, lu sur le SQUAD → fiable sur les corpses).
- Probe : 6 corpses, polarite coherente (custoTrajann melee kill → True ; blackObliterator/
  astraPrimarisPsy ranged kills → False), killerId = vrais ids, zero faux-positif vivants,
  deterministe inter-runs.

## Port prediction (fait)

- `engine/entities/effects/loki.py::BlessingsOfKhorneModifiersEffect` (EffectType 0x4ee=1262, nom
  capte "BlessingsOfKhorne" — confirme live sur Azkor) : DEF `x(1−0.08·N)` gated Psychic ; ATK
  `x(1+0.03·N)` OwnerIsCaster seul (tous profils). `N = min(melee_defeats, 8)` dans l'effet
  (cap = ConfigConst 0x43 du config-owner).
- `Scene.melee_defeats()` = `Count(NormalUnits(UnitsDefeatedByMeleeAttack(AllUnits)))` : units
  dv (squads kind-1, `NormalUnits @180df7770 = Units(set, kind=1)`) avec `defeatedByMelee && !alive`
  (isDead mirror IsValidUnit — une ressuscitee ne compte plus). `_seed_battle_counters()` pousse le
  compte sur les instances (duck-typing attr `melee_defeats`) dans les DEUX constructeurs.
- TalismanOfRage (1460, self-kills double-comptes) : INERTE-PAR-ROSTER (0 carrier au gameconfig
  courant, verifie unit_map) — non code ; killerId DEJA capte pour le jour ou un carrier apparait.
- Runner offline (`from_state`) : pas de tracking death-cause → N=0 (degradation fidele) ;
  tracking runner-side = suite possible.

## Validation live (confront, session 21, seed 777 MC1_67)

Roster : bloodMephiston+custoTrajann vs worldEightbound+worldJakhal+worldTerminator ; AI-driven.
- Azkor effects captes = `['BlessingsOfKhorne', 'Daemon_ExtraBlock', 'Terrifying_ExtraDefense']`.
- **N=1, meph→Azkor (Psychic, DEF face) : engine=(2325,3489) == oracle aiPlaybookPredict=(2325,3489)
  — BIT-EXACT.**
- N=1, Azkor→meph (ATK face) : session 21 oracle=(1608,2302) vs engine=(1390,2086) = residu FLAT
  ~+217 (min/max ratios 1.157/1.104 ≠ scalaire → additif) → PAS le canal %-BoK. **RESOLU #189 =
  BeaconOfRage non porte** ; apres port, re-confront session 22 (meme seed/roster, iter-5 N=1
  rage=1) : **engine=(1608,2302) == oracle=(1608,2302) BIT-EXACT** (et DEF re-MATCH au meme run).
- iter-4 (positions distantes) meph→Azkor : oracle=(532,798) = engine x0.36 (scalaire pur).
  **RESOLU #190 — pas positionnel du tout** : decomposition live (dump geometrie + toggles) =
  meph (1,4) → Azkor (3,4) dist 2 (ranged), tout Grass, elev 3=3, Trench→None, toggles
  no-elev/no-board strictement inertes ; le facteur = **OverwhelmingWrath_RangeDmgReduction (1301,
  rem=1)** sur Azkor : -64% degat RANGED recu (`CreateDamageDefenseModifier @180f5d6e0` =
  ForPercentDecrease(OwnerIsTarget & IsRangedAttack, ConfigVar(0x46=dmgReductionPct)), famille
  ADamageDefenseModifierAbilityEffect(0x475=1141), dmgReductionPct 24→64 plateau L36+, hors
  rarityBonus). Apres port : iter-4 engine=(532,798) == oracle BIT-EXACT, aucune divergence
  restante sur le run (l'effet jumeau 1300 PendingAttack = attaque differee, tache #193).

## #189 — BeaconOfRage (le residu FLAT, resolu)

`BeaconOfRage_ExtraDamageEffect` (EffectType 0x512=1298, nom capte "BeaconOfRage_ExtraDamage",
AbilityOrEffect 0x4d4=1236 = la passive BeaconOfRage d'Azkor) :
- `CreateEffectDamageBonusForAttack @180f33130` : `ForAddition(get_OwnerIsCaster,
  Multiply(ConfigVar(8=extraDmg, GetAbilityState), EffectLevel(effet)))` — FLAT additif (AUCUN
  ForPercent*), tous profils, normale ET speciale ; meme canal additif que SmashaEad (#69).
- Rage = EffectLevel de l'instance = `min(TotalTimesAttacked, nrOfAttacks=8)` —
  `ABeaconOfRageAbility.GetCurrentSelfEffectLevel @180e12fa0` = `Min(TotalTimesAttacked(unit),
  ConfigConst(0x59))`, ecrit par `GetUpdateSelfEffectBehaviour @180e13230` (AddEffect(0x512) si
  absent & level>0, puis SetEffectLevel) → **capte tel quel** dans `decisionView.effects[].level`
  (Level @0x68, deja dans la capture — port SANS reinject).
- Magnitude : `extraDmg[abilityLevel passif]` (gameconfig BeaconOfRage.variables, 1→315 sur 65
  niveaux, HORS variablesAffectedByRarityBonus → pas de scaling multiplier) × rage. i2 : « For
  each time he was attacked in battle, up to a maximum of 8 times, Azkor deals +315 Damage ».
- Port : `engine/entities/effects/loki.py::BeaconOfRageExtraDamageEffect` + factory
  "BeaconOfRage_ExtraDamage". Smoke 11/11 ; live BIT-EXACT (ci-dessus).
- Variante `BeaconOfRage_FriendlyExtraDamage` (0x513=1299) : 50% du bonus (`PercentageOf(...,
  0x32=50)` @180f33370) aux attaques MELEE des amis Chaos adjacents (selector @180f335b0), active
  SSI le porteur a >=1 kill (`GetCurrentFriendEffectLevel @180e12f10 = If(UnitsDefeatedAmount>0,
  selfLevel, 0)`, behaviour @180e13040 effet 0x513) — NON portee, tache #191.

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
