"""SquigMinePlaybook -- face DECISION de `1201` (`orksRukkatrukk`, MACHINE OF WAR)."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import (NCContext, NonComparablePlaybook, eligible_target_tiles, native_priority,
                    occupant_team_by_pos)


class SquigMinePlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.SquigMinePlaybook$$EvaluateNonComparable`
    (id `0x4b1` = 1201, `orksRukkatrukk` -- Rukkatrukk Squigbuggy, Orks, MACHINE OF WAR).

    Base `IdunBattle.AI.Playbook.NonComparablePlaybook`1` -- LUE dans
    `data/symbols/<build>/frida/classes.tsv` ; le corps de ctor est etiquete
    `ComparablePlaybook<T>$$.ctor` par ghidra (gshared DEDUPLIQUE, piege #487-r1 / #945 / #957) et
    relaie `Playbook<T>$$.ctor(this, 0x4b1)`.

    CORPS NATIF, lu VERBATIM :

        bucket = new Bucket(0, Nullable(MIN_UTILITY), <MI>)       # .cctor = Fix64(1)
        targets = BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition)
        if (targets == null) throw
        foreach (target in targets) {
            util = Fix64.op_Implicit(1)
            if (!TileExtensions$$IsFreeTile(target, state@+0x20, true, null, false)) continue
            n = battleQuery@+0x28.<slot itf 0x7f = GetAdjacentEnemies>(target, caster, false).Count
            util = util + Fix64.op_Implicit(n)
            bucket.AddAction(BasePlaybook$$GenerateAction(casterPosition, target, util))
        }
        return bucket

    => **utilite = 1 + (nombre d'ennemis ADJACENTS a la tuile de pose de la mine)**.

    TROIS lectures ANCREES :

    1. **LE SLOT `0x7f` EST `GetAdjacentEnemies`, PAS `GetNumAttackTargetsInPosition`.**
       `data/symbols/<build>/metadata/interface_slots.tsv` : `IBattleQuery 127 GetAdjacentEnemies 3`
       -- arite 3, ce que le call-site respecte (`(target, caster, false)`). Les slots 125/126/128
       sont TROIS autres surcharges du meme nom ; c'est l'arite qui tranche, comme pour les trois
       `GetSurroundingUnits` de `GrotTankPlaybook`. La lecture « slot 0x7f =
       `GetNumAttackTargetsInPosition` » qui vit dans `_base._get_num_attack_targets_in_position`
       est celle de `TheQuickeningPlaybook`, un AUTRE call-site avec une AUTRE arite : ne pas la
       recopier ici.

    2. **LE DOMAINE EST LA TUILE** : `target` est passe a `IsFreeTile` puis a `GetAdjacentEnemies`
       comme ancre spatiale. La cible EMISE est donc l'entite-tuile (`ctx.tile_id_by_pos`), comme
       `AberrantHypermorph` / `GrotTank` / `MasterOfTheTutelaries`.

    3. **LE GATE `IsFreeTile` EST DANS LE PLAYBOOK**, en plus du masque de ciblage : le `continue`
       tombe AVANT tout comptage, donc une tuile occupee n'est jamais proposee -- pas meme avec
       l'utilite plancher 1.

    PORTEUR : `orksRukkatrukk`, `traits = ['MachineOfWar']` -> `DefaultMachineTactic`, qui pose
    `@tactic+0x60 = GetDefaultActiveAbilityActionGenerators(this)` : les MEMES generateurs
    NonComparable par tier que le tactic unite. Corollaires mirrores : `ctx.origin is None`,
    `ctx.reach_nc == []` (une MoW est hors-plateau et ne bouge JAMAIS), donc `to = None` et
    l'enumeration part de `fromHere` -- exactement le patron de `ThriceBlessedConflagrationPlaybook`
    (1187, l'autre MoW portee). Heriter `_PlanTargetPlaybook` rendrait la feuille MORTE : son
    sweep boucle sur `ctx.reach_nc`, vide ici.

    `PRIORITY` = **-100** (`AbilityPriority.Late`) : 1201 SURCHARGE `get_Priority`, et c'est l'une
    des TROIS surcharges dont les OCTETS du corps natif sont cites dans `NATIVE_PRIORITY`
    (`SquigMinePlaybook.get_Priority` = `b8 9c ff ff ff c3` = `mov eax,0xFFFFFF9C` = -100). Elle
    est donc evaluee APRES tous les tiers superieurs -- dont `1200 SquigLaunchas` (tier 1000), la
    seconde active du MEME porteur : sur `orksRukkatrukk`, SquigMine ne passe que si SquigLaunchas
    n'a produit aucune action.

    RESIDU NOMME -- `IsFreeTile` : le port teste l'OCCUPATION (`occupant_team_by_pos`, tire
    d'`observeBattle.units` vivantes) et la marchabilite (`walkable_by_pos`). Le natif,
    `IdunBattle.Entities.TileExtensions$$IsFreeTile(tile, state, <b1>, null, <b2>)`, consulte
    l'ECS : il ecarte aussi les entites-objet non projetees comme unites. Sens de l'ecart : le
    port ecarte MOINS que le natif (degradation PERMISSIVE), jamais plus. Canaux muets
    (`obs_units` vide, `walkable_by_pos` vide) -> aucun refus, statu quo."""

    ABILITY_ID = int(ActiveAbilityType.SquigMine)      # 1201 = 0x4b1
    MIN_UTILITY = 1.0                                  # `...SquigMinePlaybook$$.cctor` = Fix64(1)
    PRIORITY = native_priority(int(ActiveAbilityType.SquigMine))   # -100 = AbilityPriority.Late

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        from_here, union = eligible_target_tiles(ctx, self.ABILITY_ID)
        tiles = from_here or union
        if not tiles:
            return []
        occ = occupant_team_by_pos(ctx)
        wk = ctx.walkable_by_pos or {}
        neigh = bq.neigh_map(ctx)
        epos = [(p[0], p[1]) for p in (ctx.epos or []) if p and p[0] is not None]
        best = None                                    # (tuile, utilite)
        for t in tiles:
            # `TileExtensions$$IsFreeTile` -- cf. RESIDU NOMME de la docstring.
            if t in occ:
                continue
            if wk and wk.get(t) is False:
                continue
            u = 1.0 + float(bq.count_adjacent(t, epos, ctx.elev_by_pos, neigh))
            if best is None or u > best[1]:            # strict > : 1re tuile du max gagne
                best = (t, u)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        tile, u = best
        tid = (ctx.tile_id_by_pos or {}).get(tile)
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] SquigMine tile={tile} u={u:.1f}", file=sys.stderr)
        return [{"target": (tid if tid is not None else tile), "ability": self.ABILITY_ID,
                 "to": None, "pred": u}]
