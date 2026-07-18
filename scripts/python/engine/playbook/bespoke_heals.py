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

import hexgeo
import gameconfig as _gc
from engine import battle_query as bq
from engine.predict import heal_amount_config, predict_heal_effective, heal_utility
from engine.entities.effects.magnitude import ability_var  # #15 : GetVariableForLevel (CultDemagogue nrOfSummons)
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


class CultDemagoguePlaybook:
    """`CultDemagoguePlaybook.EvaluateInternal @1811278c0` (id 0x49b=1179, Isaak genesPrimus). COMPARABLE
    BESPOKE (ctor @1811280f0 = `ComparablePlaybook(0x49b)` -> classe COMPARABLE, PAS NonComparable ;
    override TOTAL d'`EvaluateInternal`, AUCUNE `MakeDamagePredictions` -> ne va PAS dans noncomparable.py).
    Cible = un ENNEMI (<=2 hex) ; cast EN PLACE (pas de sweep : régime Comparable, position caster fixée).

    Utilité (par cible éligible) :
      u = 1 + min(#tuiles_libres autour CASTER r2, nrOfSummons[lvl]) * W
            + (#decoys + #neophytes AMIS autour CIBLE r2) * W
    W = `Utilities.Default.ActiveAbilities.CultDemagogue_FriendlyDecoysAndNeophytes` = 20 (MÊME poids pour
    les DEUX termes, DAT_18327dcc8 unique). MIN_UTILITY = `Fix64.FromInt(1)` = 1 (cctor @181128080).
    Helpers natifs (VA) :
    - `PossibleTilesForDecoys @1811ce650` = `CanAddUnit(SurroundingTiles(caster, range=GetNumberConstant
      (0x44)=2))` -> tuiles LIBRES placeables <=2 hex du CASTER. `.Count`.
    - `GetDecoyAmount @1811ce240` = `GetVariableForLevel(0x4f)` = `nrOfSummons` (4->8 selon niveau, NON
      rarity-scaled). i2 : « up to 8 decoys ».
    - `FriendlyDecoysAroundTarget @1811ce0f0` / `FriendlyNeophytesAroundTarget @1811ce190` =
      `SurroundingEnemies(range=2 autour de la CIBLE)` filtré `UnitsWithId(genesSmnDecoy / genesSmnNeophyte)`
      -> les alliés du CASTER de ce visualId à <=2 hex de la cible. Count via `SelectUniqueUnits` (le param
      3 = mode SelectUnit, PAS un cap sur le count).
    L'ÉLIGIBILITÉ (ennemi <=2 hex) est déléguée à `ability_targets` (le RPC applique
    `CultDemagogueAbility.GetDynamicInvalidTargetReason @1811ce290`). Terme 1 = CONSTANT sur les cibles
    (dépend du caster) -> n'affecte PAS l'argmax de cible, seulement la magnitude vs autres abilities."""

    ABILITY_ID = int(ActiveAbilityType.CultDemagogue)  # 1179
    W_KEY = "CultDemagogue_FriendlyDecoysAndNeophytes"   # cat ActiveAbilities ; W=20 (seed-bc)
    MIN_UTILITY = 1.0
    _RANGE = 2                             # constants.range (GetNumberConstant 0x44)
    _DECOY_VID = "genesSmnDecoy"           # constants.unitId
    _NEOPHYTE_VID = "genesSmnNeophyte"     # constants.unitId_2

    def generate_candidates(self, ctx) -> list:
        me = ctx.me
        if me is None or ctx.ability_targets is None:
            return []
        # cibles ennemies éligibles (RPC applique GetDynamicInvalidTargetReason @1811ce290 : ennemi <=2 hex).
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        tgt_ids = set()
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):
                    if t.get("kind") == "unit" and t.get("targetId") is not None:
                        tgt_ids.add(t["targetId"])
        if not tgt_ids:
            return []
        w = ctx.wt.sub("ActiveAbilities", self.W_KEY)          # 20
        lvl = ctx.heal_config(ctx.uid)["active"]               # niveau ACTIF du caster
        decoy_amt = int(ability_var("CultDemagogue", "nrOfSummons", lvl) or 0)
        # Terme 1 (CONSTANT sur les cibles) : min(#tuiles libres <=2 du CASTER, nrOfSummons).
        term1 = min(self._free_tiles_around(ctx, ctx.origin), decoy_amt) * w
        # decoys/neophytes AMIS positionnés (pour le terme 2, par cible).
        team = me.get("team")
        summons = [(u["pos"]["col"], u["pos"]["row"]) for u in ctx.units
                   if u.get("team") == team and u.get("alive") and u.get("pos")
                   and u["pos"].get("col") is not None
                   and u.get("visualId") in (self._DECOY_VID, self._NEOPHYTE_VID)]
        pos_by_id = {u.get("id"): u.get("pos") for u in ctx.units}
        best = None   # (target, util)
        for tid in tgt_ids:
            tp = pos_by_id.get(tid)
            if not tp or tp.get("col") is None:
                continue
            tpos = (tp["col"], tp["row"])
            n_around = sum(1 for s in summons if hexgeo.distance(tpos, s) <= self._RANGE)
            util = 1.0 + term1 + n_around * w
            if best is None or util > best[1]:            # argmax strict (Bucket keep-first au tie)
                best = (tid, util)
        if ctx.debug:
            import sys
            print(f"    [dbg CultDemagogue u{ctx.uid}] W={w} decoyAmt={decoy_amt} term1={term1} "
                  f"tgts={sorted(tgt_ids)} best={best}", file=sys.stderr)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        return [{"target": best[0], "ability": self.ABILITY_ID, "to": None,
                 "pred": best[1], "full": best[1]}]

    def _free_tiles_around(self, ctx, center) -> int:
        """`PossibleTilesForDecoys @1811ce650` : `CanAddUnit(SurroundingTiles(center, range=2))` = tuiles
        LIBRES placeables à <=2 hex du CASTER (center=origine). Occupation LIVE = epos u fpos u origine
        (frais), PAS l'occupantUnitId caché du boardGraph (cf. can_add_unit #116)."""
        if center is None:
            return 0
        occ = set(ctx.epos or []) | set(ctx.fpos or [])
        occ.add(center)
        return sum(1 for T in (ctx.walkable_by_pos or {})
                   if T != center and hexgeo.distance(center, T) <= self._RANGE
                   and bq.can_add_unit(T, ctx.walkable_by_pos, occ))


# Registry des self-cast/ENEMY-target bespoke Comparable (dispatché par id d'ability présente sur le caster).
# NB : CultDemagogue cible un ENNEMI (pas self) mais partage le même régime bespoke Comparable (override
# EvaluateInternal, hors du plan `evals`) et le même dispatch _bespoke_candidates.
BESPOKE_SELFCAST: dict = {
    BloodChalicePlaybook.ABILITY_ID: BloodChalicePlaybook(),
    MomentShacklePlaybook.ABILITY_ID: MomentShacklePlaybook(),
    CultDemagoguePlaybook.ABILITY_ID: CultDemagoguePlaybook(),
}
