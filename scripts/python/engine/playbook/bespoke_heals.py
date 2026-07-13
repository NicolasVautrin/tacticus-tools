"""Playbooks Comparable BESPOKE self-cast (RE ghidra gqfc5mff6c) — chacun OVERRIDE le scoring générique
(`ComparablePlaybook<T>.EvaluateInternal @181408980`) par une utilité PROPRE (PAS `HEAL_PLAYBOOK.score`).
Identifiés par ID (pas `"Heal" in name` : leur nom n'a pas "Heal"). Self-cast / position-swept comme les
NonComparable heals (mais régime Comparable) -> candidate generators appelés par `ComparableAbilityGenerator`.

- `BloodChalicePlaybook`  (id 0x497=1175 ; bloodSanguinary/Nicodemus).
- `MomentShacklePlaybook` (id 0x4a0=1184 ; custoTrajann/Trajann).

(SpiritLeech(1104) = per-ENEMY attack + lifesteal -> régime `_best_attack`/registry, PAS ici.)

Poids `GetUtilityValue` résolus OFFLINE depuis `BattleConfiguration.Utilities.Default.ActiveAbilities`
(clés-strings du dump `stringliteral.json`, cf. `weights.Weights.sub`) :
  BloodChalice_AdjacentDamagedNonMechanicalFriend = 50
  MomentShackle_AdjacentEnemy                     = 25
"""
from __future__ import annotations

import gameconfig as _gc
from engine import battle_query as bq
from engine.predict import heal_amount_config, predict_heal_effective, heal_utility
from engine.entities.active_ability_type import ActiveAbilityType  # #158 : ABILITY_ID -> enum (abilities ACTIVES, cat W_KEY=ActiveAbilities)

_TRAITS_CACHE: dict = {}


def _traits(visual_id) -> list:
    """Traits gameconfig d'une unité par visualId (cache). Pour la porte `IsMechanical` de BloodChalice."""
    if not visual_id:
        return []
    if visual_id in _TRAITS_CACHE:
        return _TRAITS_CACHE[visual_id]
    uid = _gc.resolve_unit_id(visual_id)
    u = _gc.unit(uid) if uid else None
    t = (u or {}).get("traits") or []
    _TRAITS_CACHE[visual_id] = t
    return t


class BloodChalicePlaybook:
    """`BloodChalicePlaybook.EvaluateInternal @1811224c0` (id 0x497=1175, bloodSanguinary/Nicodemus).

    Utilité BESPOKE (override total, PAS la HealUtility générique) = `count(alliés non-mécaniques
    ADJACENTS au caster, PV% < seuil) × W`. Self-cast AoE (cible = MainTile du caster ; `GenerateAction
    (this, casterTile, ...)`). Position-swept par le générateur.
    - Cibles (`GetTargets`) : `IsAffectedByHealType` = ami NON-mécanique ; PV% via `GetStat(Health, 1)`
      (FillUpStatComponent.GetStatPart(1) = round(cur/max×100)).
    - seuil = `AbilityConfiguration.GetNumberConstant(0x4f)` = config `healthPct` = 50.
    - W = `Utilities.Default.ActiveAbilities.BloodChalice_AdjacentDamagedNonMechanicalFriend` = 50.
    - MIN_UTILITY = `Fix64.FromInt(1)` = 1 (cctor @181122b10) -> gate `count>=1` (1×50=50>1).
    - `ShouldExecute @1811228b0` : `Σ(seuil − PV%)` sur amis non-méca > 0 (>=1 ami sous le seuil)."""

    ABILITY_ID = int(ActiveAbilityType.BloodChalice)  # 1175
    W_KEY = "BloodChalice_AdjacentDamagedNonMechanicalFriend"   # cat ActiveAbilities
    MIN_UTILITY = 1.0

    def generate_candidates(self, ctx) -> list:
        me = ctx.me
        if me is None:
            return []
        team = me.get("team")
        w = ctx.wt.sub("ActiveAbilities", self.W_KEY)          # 50
        thr = int(((_gc.ability("BloodChalice") or {}).get("constants") or {}).get("healthPct") or 50)
        obs_by_sq = {u.get("squadId"): u for u in ctx.obs_units}
        # amis VIVANTS non-mécaniques (self exclu) positionnés + PV% courant
        allies = []
        for u in ctx.units:
            if u.get("id") == ctx.uid or u.get("team") != team or not u.get("alive"):
                continue
            p = u.get("pos")
            if not p or p.get("col") is None:
                continue
            if "Mechanical" in _traits(u.get("visualId")):
                continue
            ob = obs_by_sq.get(u.get("id")) or {}
            mx = int(ob.get("hpMax") or 0)
            cur = int(ob.get("hp") or 0)
            pct = round(cur / mx * 100) if mx > 0 else 100
            allies.append(((p["col"], p["row"]), pct))
        best = None   # (T, util)
        for T in ctx.reach_nc:   # origine d'abord -> keep-first au tie (Bucket.AddAction #76)
            count = sum(1 for pos, pct in allies
                        if pct < thr and bq.is_adjacent(T, pos, ctx.elev_by_pos))  # AdjacentUnits (#45)
            util = count * w
            if util < self.MIN_UTILITY:
                continue
            if best is None or util > best[1]:   # strict > : 1er max garde
                best = (T, util)
        if ctx.debug:
            import sys
            print(f"    [dbg BloodChalice u{ctx.uid}] W={w} thr={thr} best={best}", file=sys.stderr)
        if best is None:
            return []
        T, util = best
        target = ctx.tile_id_by_pos.get(T, ctx.uid)   # self-cast AoE = MainTile-id
        return [{"target": target, "ability": self.ABILITY_ID,
                 "to": (T if T != ctx.origin else None), "pred": util, "full": util}]


class MomentShacklePlaybook:
    """`MomentShacklePlaybook @18114c9d0` (id 0x4a0=1184, custoTrajann/Trajann). Comparable.

    Utilité = HealUtility(SELF-heal) + CalculateCasterPositionUtility, sommées par
    `CalculateActionUtility @181406ee0`. Cible = SOI (self-heal). Position-swept.
    - Self-heal : `MakeHealPredictions @18114c7f0` -> `GetHealAmount = ConfigVar(0x20)` = `hpToHeal[level]`
      (MomentShackle config a `hpToHeal`) -> `GenerateHealPredictions` -> `PredictHeal @181037180`
      (`min(healAmount, missing_self)`, #79) -> `HealUtility` = `effective/(maxHP+1)×100`. POSITION-INDÉP.
    - Position : `CalculateCasterPositionUtility @18114c6e0` = `count(ennemis ADJACENTS au caster@T) × W`.
      W = `Utilities.Default.ActiveAbilities.MomentShackle_AdjacentEnemy` = 25.
    - MIN_UTILITY = `Fix64.FromInt(1)` = 1 (cctor @18114c960). Position-swept, origine-préférée (#76)."""

    ABILITY_ID = int(ActiveAbilityType.MomentShackle)  # 1184
    W_KEY = "MomentShackle_AdjacentEnemy"   # cat ActiveAbilities
    MIN_UTILITY = 1.0

    def generate_candidates(self, ctx) -> list:
        me = ctx.me
        if me is None:
            return []
        w = ctx.wt.sub("ActiveAbilities", self.W_KEY)   # 25
        # self-heal magnitude = hpToHeal[activeLevel] (ConfigVar(0x20)) ; None -> saturation (défensif)
        hc = ctx.heal_config(ctx.uid)
        heal_amt = heal_amount_config("MomentShackle", hc["active"], hc["passive"], hc["multiplier"])
        ob = next((u for u in ctx.obs_units if u.get("squadId") == ctx.uid), None) or {}
        smax = int(ob.get("hpMax") or 0)
        scur = int(ob.get("hp") or 0)
        eff = max(0, smax - scur) if heal_amt is None else predict_heal_effective(heal_amt, scur, smax)
        self_heal_u = heal_utility(eff, smax, is_friend=True, is_boss=False)   # POSITION-INDÉPENDANT
        best = None   # (T, util)
        for T in ctx.reach_nc:   # origine d'abord -> keep-first au tie (#76)
            adj_enemies = sum(1 for e in ctx.epos if bq.is_adjacent(T, e, ctx.elev_by_pos))
            util = self_heal_u + adj_enemies * w
            if util < self.MIN_UTILITY:
                continue
            if best is None or util > best[1]:   # strict >
                best = (T, util)
        if ctx.debug:
            import sys
            print(f"    [dbg MomentShackle u{ctx.uid}] W={w} healAmt={heal_amt} selfHealU={self_heal_u:.2f} "
                  f"best={best}", file=sys.stderr)
        if best is None:
            return []
        T, util = best
        return [{"target": ctx.uid, "ability": self.ABILITY_ID,   # SELF-target (self-heal)
                 "to": (T if T != ctx.origin else None), "pred": util, "full": util}]


# Registry des self-cast bespoke Comparable (dispatché par id d'ability présente sur le caster).
BESPOKE_SELFCAST: dict = {
    BloodChalicePlaybook.ABILITY_ID: BloodChalicePlaybook(),
    MomentShacklePlaybook.ABILITY_ID: MomentShacklePlaybook(),
}
