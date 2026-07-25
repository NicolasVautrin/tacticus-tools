"""MasterOfTheTutelariesPlaybook — decision NC du summon Pink Horror (Abraxas, #202-C)."""
from __future__ import annotations

import hexgeo
from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


class MasterOfTheTutelariesPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.MasterOfTheTutelariesPlaybook$$EvaluateNonComparable` (IdunBattle.AI.Playbook.Loki.MasterOfTheTutelariesPlaybook$$.ctor,
    IdunBattle.AI.Playbook.Loki.MasterOfTheTutelariesPlaybook$$.cctor : `MIN_UTILITY = Fix64(1)`). DECOMPILE (slots IBattleQuery resolus via le dump
    vtable #38b `data/_probe38b_vtable.json` : 0x49=`IdunBattle.Core.Services.BattleQuery$$GetNearestEnemy`,
    0x52=`IdunBattle.Core.Services.BattleQuery$$GetFreeAdjacentTiles(target)`, 0x6b=`IdunBattle.Core.Services.BattleQuery$$GetDistance`,
    0x72=`IdunBattle.Core.Services.BattleQuery$$GetUnitsAtDistance`) :

        bucket = Bucket(min = Fix64(1))
        targets = GetEligibleTargetsSelectable(unit, MainTile(position))   # tuiles de SPAWN (ring-1 libre)
        for (tgtEntity, tgtPos) in targets:
            nFree = GetFreeAdjacentTiles(tgtEntity).Count                  # slot 0x52 (ring-1 ∩ CanAddUnit de ST)
            nE2   = Count(GetUnitsAtDistance(GetMainTile(unit), 2),        # slot 0x72 : ring EXACT dist==2
                          x => IsEnemy(unit, x))                           # lambda DisplayClass6_0 IdunBattle.AI.Playbook.Loki.MasterOfTheTutelariesPlaybook.u003Cu003Ec__DisplayClass6_0$$u003CEvaluateNonComparableu003Eb__0
            if (nFree > 2 && nE2 > 0):
                u = 1 + max(nE2-1, 0)*10 + max(nFree-3, 0)*10
                near = GetNearestEnemy(unit)                               # slot 0x49
                if (GetDistance(GetMainTile(near), tgtPos) == 2): u += 100 # slot 0x6b
                bucket.AddAction(GenerateAction(position, tgtPos, u))

    Lectures ANCREES (fideles au decompile, a verrouiller a l'oracle `ncEvaluate`) :
    - `nE2` est calcule sur `EntityExtensions.GetMainTile(unit)` = la tuile REELLE du caster —
      PAS la position balayee => CONSTANT sur tout le sweep. `GetUnitsAtDistance` = ring EXACT
      (`IdunBattle.Core.Services.BattleQuery$$GetTilesAtDistance` filtre dist==R, cf. battle_query.py:170) : un ennemi ADJACENT
      ne compte PAS (nE2=0 avec un seul ennemi au contact -> PAS de cast).
    - `nFree(ST)` = tuiles libres adjacentes a la TUILE DE SPAWN candidate, occupation = board COURANT
      (le caster reste a l'origine pendant le sweep) — gate STRICT nFree >= 3.
    - `IdunBattle.Core.Services.BattleQuery$$GetNearestEnemy` : parcourt GetAllAliveUnits, garde si `d < best` OU
      (`AreUnitsInMelee(pos, x)` ET best pas-en-melee) — la priorite MELEE supplante la distance
      (un ennemi hex-dist 1 avec |dElev|>=2 n'est PAS en melee). Tie = 1er enumere (ordre natif
      GetAllAliveUnits ≈ ordre d'ids offline, residu documente).
    - Les tuiles de spawn eligibles par position T = abilityTargets kind="tile" filtre
      dist(T, ST)==1 (meme technique que AberrantHypermorphPlaybook — l'RPC rend l'UNION sur
      toutes les tuiles de move).
    Cible emise = la TUILE de spawn (id via ctx.tile_id_by_pos) — c'est le targetId natif du cast."""
    ABILITY_ID = int(ActiveAbilityType.MasterOfTheTutelaries)   # 1096
    MIN_UTILITY = 1.0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        spawn_tiles = self._eligible_spawn_tiles(ctx)
        if not spawn_tiles or ctx.origin is None:
            return []
        # nE2 : ennemis a distance hex EXACTEMENT 2 de la tuile REELLE (constant sur le sweep).
        n_e2 = sum(1 for p in (ctx.epos or [])
                   if hexgeo.distance(ctx.origin, (p[0], p[1])) == 2)
        if n_e2 <= 0:
            return []                                        # gate nE2 > 0 (commun a tous les candidats)
        near_tile = self._nearest_enemy_tile(ctx)
        occ = {(u.get("col"), u.get("row")) for u in (ctx.obs_units or [])
               if not u.get("isDead") and u.get("col") is not None}
        if not occ:
            occ = set(ctx.epos or []) | set(ctx.fpos or []) | {ctx.origin}
        best = None                                          # (target_tile, position, util)
        for T in ctx.reach_nc:                               # positions candidates (ordre movable natif)
            for ST in spawn_tiles:
                if hexgeo.distance(T, ST) != 1:
                    continue                                 # spawn = hex libre ADJACENT a la position T
                n_free = bq.adjacent_addable_count(ST, ctx.neigh_by_pos, ctx.walkable_by_pos,
                                                   occ - {ST}, ctx.elev_by_pos)
                if n_free <= 2:
                    continue                                 # gate nFree > 2
                u = 1.0 + max(n_e2 - 1, 0) * 10 + max(n_free - 3, 0) * 10
                if near_tile is not None and hexgeo.distance(near_tile, ST) == 2:
                    u += 100.0                               # GetDistance(nearestEnemyTile, ST) == 2
                if best is None or u > best[2]:              # strict > : 1er max du sweep gagne
                    best = (ST, T, u)
        if best is None or best[2] < self.MIN_UTILITY:
            return []
        st, t, u = best
        tid = (ctx.tile_id_by_pos or {}).get(st)
        return [{"target": (tid if tid is not None else st), "ability": self.ABILITY_ID,
                 "to": (t if t != ctx.origin else None), "pred": u}]

    def _eligible_spawn_tiles(self, ctx: NCContext) -> list[tuple]:
        """Mirror `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` pour un cast TILE-target : union des
        tuiles de spawn legales via l'RPC abilityTargets (kind="tile") — meme voie que
        AberrantHypermorphPlaybook."""
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        tiles: list[tuple] = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == self.ABILITY_ID:
                    tiles = [(t["tile"].get("col"), t["tile"].get("row"))
                             for t in (a.get("targets") or [])
                             if t.get("kind") == "tile" and t.get("tile")
                             and t["tile"].get("col") is not None]
        return tiles

    def _nearest_enemy_tile(self, ctx: NCContext) -> "tuple | None":
        """Mirror `IdunBattle.Core.Services.BattleQuery$$GetNearestEnemy` : parcourt les unites vivantes ; garde si
        `dist < best` OU (en-MELEE et best pas-en-melee). Melee = hex-adjacent AVEC porte d'elevation
        (`AreUnitsInMelee` ~ `is_adjacent`). Ordre d'enumeration natif (GetAllAliveUnits) approxime
        par l'ordre de `ctx.enemies`/`ctx.epos` (tie residu, a verrouiller a l'oracle)."""
        if ctx.origin is None:
            return None
        best = None
        best_d = None
        best_melee = False
        for p in (ctx.epos or []):
            pk = (p[0], p[1])
            d = hexgeo.distance(ctx.origin, pk)
            melee = bq.is_adjacent(ctx.origin, pk, ctx.elev_by_pos)
            if best_d is None or d < best_d or (melee and not best_melee):
                best, best_d, best_melee = pk, d, melee
        return best
