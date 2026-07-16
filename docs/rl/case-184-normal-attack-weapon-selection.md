# Case #184 — bloodMephiston normal-attack over-prediction (~1.49x) = POSITIONAL weapon-selection, not a per-unit AttackRangeType

**Status: original hypothesis REFUTED twice. The true cause is a POSITION/ADJACENCY-semantics gap in the
prediction weapon-selection (which tile `AreUnitsInMelee` keys on), NOT a hit-count/range-type gap and NOT
a captureable per-unit `AttackRangeType`. Handed to `fable-solver` for end-to-end re-diagnosis.**

## Symptom
Seed 2024, board MC1_67, attacker `bloodMephiston` (u89, Psyker/RapidAssault/Terrifying): prediction
over-predicts its normal attack by a uniform ~1.493x across targets. Root delta = HIT COUNT: engine 3 hits
(melee weapon) vs oracle 2 hits (ranged weapon); base per-hit ([806,1210], Psychic) and RapidAssault x1.25
are correct. `3/2 = 1.5` (~1.493 with rounding). decisionView tgt 81 = `2 x [806,1210] x 1.25 = (2016,3024)`.

## REFUTATION 1 (task title): NOT "attacker -33% modifier missing"
worldExecutions (u91) uses the same normal path and is BIT-EXACT with RapidAssault applied. So no missing
attacker modifier. The gap is which WEAPON the normal attack selects (3-hit melee vs 2-hit ranged).

## REFUTATION 2 (this session): NOT a per-unit `AttackRangeType` (capture is impossible AND uninformative)
Measured LIVE (probe over seeds 2024/500/42, decisionView kind=normal): **every** unit's normal attack is
`Loki_NormalAttack` (ActiveAbilityType id **69**); a few summons use `FeederTendrils_NormalAttack` (1120).
gameconfig `ability("Loki_NormalAttack").attackRangeType = None` for all. Distribution over 559 gameconfig
abilities: 396 None / 84 Ranged / 69 Melee / 10 Normal — the non-None ones are the SPECIAL abilities, never
the normal attack.

Tracing the native (`BattleQuery.GetAttackWeaponForDefaultNormalAttack @18105ea60`, decompiled):
1. `rangeType = GetAbilityAttackRangeType(GetNormalAttackType(unit))`. `GetNormalAttackType @180ed1910`
   returns the ability TYPE int (component NormalAttackType@0x28). `GetAbilityAttackRangeType @181059fe0`
   takes a `Nullable<AbilityOrEffect>` built from that type ALONE (no unit context) and looks the config up
   in `battleQuery+0x48` keyed BY TYPE. => for a fixed type (69) it is a **CONSTANT across all units**.
2. Dispatch: 1 Melee -> FindMeleeWeapon ; 2 Ranged -> FindRangedWeapon (even adjacent) ; 3 MeleeOrRanged ->
   melee iff `!HasFlag(0x15) && AreUnitsInMelee`, else ranged ; 0 -> ranged.
3. Since most units DO melee-when-adjacent and worldExecutions is bit-exact with the current adaptive port,
   the constant `GetAbilityAttackRangeType(69)` must be **3 = MeleeOrRanged** => the port's adaptive rule is
   already STRUCTURALLY CORRECT. A per-unit range type does not exist and cannot differentiate bloodMephiston.

Why the capture attempt returned `None` everywhere: `GetActives(comp)` yields `Components.ActiveAbility`
RECORDS (ctor @180f8fba0: fields AbilityName@0x44, state@0x4c/0x54, flags@0x28/0x40 — stop ~0x54), NOT the
`Abilities.AActiveAbility` BEHAVIOR whose `GetAttackRangeType @180fb1030` reads config@0x60->+0x20. The
record has no behavior/config. The authoritative value is only reachable by invoking `GetAbilityAttackRangeType`
with a hand-built `Nullable<AbilityOrEffect>` (painful in Frida) — and it would be a useless constant anyway.
=> capture path fully abandoned; the speculative frida capture + offline `range_type` gate were REVERTED
(they were inert: rangeType read `None` -> fallback = current behavior; nothing shipped).

## TRUE cause (leading hypothesis for fable)
Both engine and oracle use the SAME adaptive rule (rangeType=3). They disagree only on the POSITION/ADJACENCY
fed to it:
- Engine `make_normal_attack_predictions` (prediction.py:235) keys `is_adjacent = are_tiles_adjacent(attack_pos,
  t_pos, scene.board)` on the CANDIDATE attack tile. For the bloodMephiston sample this was TRUE -> melee 3-hit.
- Oracle `aiPlaybookPredict` for bloodMephiston (measured "from current tile") gave `appliedHits=2` -> it
  evaluated bloodMephiston as NOT in melee -> ranged 2-hit.
So the divergence is WHICH tile the melee/ranged choice keys on (candidate attack-tile vs current/main-tile),
and/or a faithful `AreUnitsInMelee` vs the port's `are_tiles_adjacent` (multi-tile target / main-tile semantics).

## HARD CONSTRAINT — the naive fix regresses (measured, 7 seeds MC1_67)
Keying weapon-select on the attacker's CURRENT position instead of the candidate tile gives 63/74 vs baseline
68/74 (net -5): it fixes bloodMephiston but REGRESSES **seed 500 att91** (+3 red) and **seed 42 att89** (+2 red)
— those MeleeOrRanged units DO melee from a candidate-adjacent tile the oracle chose. So the fix is NOT "always
use current position": it must faithfully mirror WHICH tile the native prediction keys `AreUnitsInMelee` on,
per-sample. This is the flip-flop to resolve.

## Where to look (fable)
- `DamagePrediction.PredictNormalAttack @181037cd0` — builds `AbilityEntities` with the caster tile; find
  whether the melee/ranged weapon choice inside the prediction formula `FUN_180031370` (NOT yet decompiled)
  keys `AreUnitsInMelee` on the candidate CasterTile (param_4) or the unit's current/main tile.
- `AreUnitsInMelee @1810584d0` — its exact adjacency semantics (multi-tile positions, main-tile).
- `DamagePredictionQuery.GetAllPredictions @181090f50` -> how the candidate `UnitPosition` is threaded.
- Reconcile against BOTH the bloodMephiston sample (oracle ranged) and seed 500/42 att91/att89 (oracle melee).
- Port site: `engine/services/battle_query.py::get_attack_weapon_for_default_normal_attack` /
  `select_weapon_pierce` (shared prediction+runner) + `engine/playbook/prediction.py:235` (attack_pos source)
  + the `predict_samples` harness (verify it feeds the SAME attack_pos the oracle evaluated for that sample).

## Adjacent gap exposed (separate task #185, do not conflate)
On target 79 `worldEightbound` (Azkor) the oracle applies x0.70 to bloodMephiston's Psychic attack =
**BlessingsOfKhorne** (trait 1046, `CreateEffectDamageMalusForDefense @180f34c50`, multiplier
`GetMultiplierBasedOnDefeatedInMelee @180f34ea0` = min(count melee-defeated-in-battle, cap)). UNPORTED, and
capture-gated (needs a per-unit "defeated-by-melee" battle-history flag, `UnitsDefeatedByMeleeAttackSelector.
IsValidUnit @180f00b40` reads a component flag @0x178). Tracked separately as #185.

## Anchors (VAs, gqfc5mff6c)
GetAttackWeaponForDefaultNormalAttack @18105ea60 ; GetAbilityAttackRangeType @181059fe0 (type-keyed, constant) ;
GetNormalAttackType @180ed1910 ; SelectAbilityAttackRangeTypeFromMultiple @1810712b0 ; AttackRangeTypeExtensions.
Overrides @18157c200 ; AActiveAbility.GetAttackRangeType @180fb1030 (=*(inst+0x60)+0x20, behavior-only) ;
Components.ActiveAbility.ctor @180f8fba0 (record layout) ; DamagePrediction.PredictNormalAttack @181037cd0 ;
AreUnitsInMelee @1810584d0 ; weapon-select formula FUN_180031370 (TODO decompile).
