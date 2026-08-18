"""MasterOfTheTutelariesPlaybook — decision NC du summon Pink Horror (Abraxas, #202-C)."""
from __future__ import annotations

import hexgeo
from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import (NCContext, NonComparablePlaybook, eligible_target_tiles,
                    tiles_in_native_order)


class MasterOfTheTutelariesPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.MasterOfTheTutelariesPlaybook$$EvaluateNonComparable` (IdunBattle.AI.Playbook.Loki.MasterOfTheTutelariesPlaybook$$.ctor,
    IdunBattle.AI.Playbook.Loki.MasterOfTheTutelariesPlaybook$$.cctor : `MIN_UTILITY = Fix64(1)`). DECOMPILE.

    ⚠ SLOTS RE-DERIVES AU RUNTIME le 2026-08-03 sur `rnca9r7q6c`
    (`probe_433_r4_r2_adjacency_foyer.py --step slots`, qui delegue a `probe_27_4g_battlequery_slots`).
    Les quatre numeros ecrits ici venaient du dump `#38b` du build PRECEDENT et etaient TOUS
    DECALES D'UN CRAN -- une citation recopiee designait donc la methode VOISINE (0x52 et 0x53 sont
    DEUX surcharges de `GetFreeAdjacentTiles`, mais 0x72 est `GetAngleBetweenVectors`, pas
    `GetUnitsAtDistance`) : 0x4a=`IdunBattle.Core.Services.BattleQuery$$GetNearestEnemy`,
    0x53=`IdunBattle.Core.Services.BattleQuery$$GetFreeAdjacentTiles(target)`,
    0x6c=`IdunBattle.Core.Services.BattleQuery$$GetDistance`,
    0x73=`IdunBattle.Core.Services.BattleQuery$$GetUnitsAtDistance`.

        bucket = Bucket(min = Fix64(1))
        targets = GetEligibleTargetsSelectable(unit, MainTile(position))   # tuiles de SPAWN (ring-1 libre)
        for (tgtEntity, tgtPos) in targets:
            nFree = GetFreeAdjacentTiles(tgtEntity).Count                  # slot 0x53 (ring-1 ∩ CanAddUnit de ST)
            nE2   = Count(GetUnitsAtDistance(GetMainTile(unit), 2),        # slot 0x73 : ring EXACT dist==2
                          x => IsEnemy(unit, x))                           # lambda DisplayClass6_0 IdunBattle.AI.Playbook.Loki.MasterOfTheTutelariesPlaybook.u003Cu003Ec__DisplayClass6_0$$u003CEvaluateNonComparableu003Eb__0
            if (nFree > 2 && nE2 > 0):
                u = 1 + max(nE2-1, 0)*10 + max(nFree-3, 0)*10
                near = GetNearestEnemy(unit, <Nullable position VIDE>)     # slot 0x4a
                if (GetDistance(GetMainTile(near), tgtPos) == 2): u += 100 # slot 0x6c
                bucket.AddAction(GenerateAction(position, tgtPos, u))

    Lectures ANCREES (fideles au decompile, a verrouiller a l'oracle `ncEvaluate`) :
    - `nE2` est calcule sur `EntityExtensions.GetMainTile(unit)` = la tuile REELLE du caster —
      PAS la position balayee => CONSTANT sur tout le sweep. `GetUnitsAtDistance` = ring EXACT
      (`IdunBattle.Core.Services.BattleQuery$$GetTilesAtDistance` filtre dist==R, cf. battle_query.py:170) : un ennemi ADJACENT
      ne compte PAS (nE2=0 avec un seul ennemi au contact -> PAS de cast).
    - `nFree(ST)` = tuiles libres adjacentes a la TUILE DE SPAWN candidate, occupation = board COURANT
      (le caster reste a l'origine pendant le sweep) — gate STRICT nFree >= 3.
    - `IdunBattle.Core.Services.BattleQuery$$GetNearestEnemy` : parcourt GetAllAliveUnits, filtre
      `IsEnemy && !IsIrrelevantObject`, garde si `d < best` OU (`AreEntitiesAdjacent(pos, x)` ET
      best pas-en-melee) — la priorite MELEE supplante la distance (un ennemi hex-dist 1 avec
      |dElev|>=2 n'est PAS adjacent, donc pas prioritaire). Tie = 1er enumere (ordre natif
      GetAllAliveUnits ≈ ordre d'ids offline, residu documente).
    - Les tuiles de spawn eligibles par position T = abilityTargets kind="tile" RE-PROJETE sur T
      par le selecteur (meme technique que AberrantHypermorphPlaybook — l'RPC rend l'UNION sur
      toutes les tuiles de move ; substrat de la re-projection : cf. `generate_candidates`).
    Cible emise = la TUILE de spawn (id via ctx.tile_id_by_pos) — c'est le targetId natif du cast."""
    ABILITY_ID = int(ActiveAbilityType.MasterOfTheTutelaries)   # 1096
    MIN_UTILITY = 1.0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """La contrainte « ring-1 » vient du SELECTEUR, et son substrat est la LISTE STOCKEE.

        `IdunBattle.AI.Playbook.Loki.MasterOfTheTutelariesPlaybook$$EvaluateNonComparable` (relu)
        ne filtre RIEN par distance : il enumere `GetEligibleTargetsSelectable(caster,
        MainTile(position))`. Et
        `IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$.ctor` recopie
        le MEME `TargetingRange` statique +0x30 et les MEMES rules 0x1040 que
        `IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$.ctor` (lu
        separement, pas deduit par symetrie) : `onlyAdjacent = RangedBool.True` detourne
        `IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange` vers le slot 0x51 =
        `IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles` ->
        `IdunBattle.Core.Services.BattleQuery$$IterateAdjacentTiles`, c'est-a-dire la liste STOCKEE
        du `ConnectivityComponent` PUIS la porte `|dElev| < 2` -- jamais le balayage cube de
        `GetSurroundingTiles`. Chaine detaillee : `AberrantHypermorphPlaybook.generate_candidates`
        (#616).

        La re-projection de l'union sur T EST donc `is_adjacent(T, ST)` ; l'ancien
        `hexgeo.distance(T, ST) == 1` ne portait aucun des deux etages (ecart PERMISSIF).
        ⚠ Les deux autres comparaisons de ce corps sont des RING-2 (`nE2`, le bonus de 100) : elles
        mirrorent `GetUnitsAtDistance`/`GetDistance`, qui passent par `GetTilesAtDistance` --
        geometriques par construction, elles ne se branchent PAS (#614 §1).

        ⚠ **L'ORDRE DES TUILES DE SPAWN EST DERIVE PAR POSITION** (`#971-r4`). Ce corps balayait
        l'ordre de l'UNION du RPC (`abilityTargets.targets`, l'agregat sur toutes les tuiles de
        move), **qui n'est celui d'AUCUNE position** -- exactement l'ecart mesure et ferme sur
        `IronkinSteeljackPlaybook` (#971, `MC1_67`/4242 : 11 classes natives contre 10 portees,
        deux positions retenant la MEME tuile cote port et DEUX tuiles distinctes cote natif, a
        utilite EGALE). Le foyer partage `_base.tiles_in_native_order` rend `fromHere` a l'ORIGINE
        (la reponse par-position du RPC) et, ailleurs, l'ordre de `ctx.neigh_by_pos[T]` -- la liste
        d'adjacence STOCKEE que parcourt la chaine native. La transposition est legitime parce que
        `...MasterOfTheTutelariesAbility$$.ctor`, `...GrotTankAbility$$.ctor` et
        `...IronkinSteeljackAbility$$.ctor` sont IDENTIQUES OCTET POUR OCTET (relus le 2026-08-18 :
        `TargetingOptions..ctor(&opts, 0, <TargetingRange statics>+0x30, 1, 0x1040, 0, 0)` puis
        `AActiveAbility..ctor(this, &opts, 2)`), donc la chaine d'enumeration est la MEME.

        Et l'ordre du selecteur est bien celui que `Bucket$$AddAction` consomme : le corps de
        `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` (relu) empile ses
        `AbilityEntities` dans l'ordre EXACT de la liste que rend `IBattleQuery` slot 0x42 =
        `GetValidTargets(caster, UnitPosition(possibleCasterTile), abilityType)`, apres un
        `idun.shared.extensions.ListExtensions$$Remove` qui filtre EN PLACE (donc preserve l'ordre)
        -- aucun tri, aucun `OrderedSet` intermediaire."""
        from_here, union = eligible_target_tiles(ctx, self.ABILITY_ID)
        spawn_tiles = from_here or union
        if not spawn_tiles or ctx.origin is None:
            return []
        eligibles = set(from_here) | set(union)
        # nE2 : ennemis a distance hex EXACTEMENT 2 de la tuile REELLE (constant sur le sweep).
        n_e2 = sum(1 for p in (ctx.epos or [])
                   if hexgeo.distance(ctx.origin, (p[0], p[1])) == 2)
        if n_e2 <= 0:
            return []                                        # gate nE2 > 0 (commun a tous les candidats)
        near_tile = self._nearest_enemy_tile(ctx)
        # #969-r3 : les DEUX substrats ne portent que la MAIN TILE -> expansion PAR PIED dans le
        # foyer `bq.occupied_positions` (`base` = l'univers choisi ici, jamais elargi).
        occ = {(u.get("col"), u.get("row")) for u in (ctx.obs_units or [])
               if not u.get("isDead") and u.get("col") is not None}
        occ = bq.occupied_positions(ctx, base=occ) if occ else bq.occupied_positions(ctx)
        neigh = bq.neigh_map(ctx)
        best = None                                          # (target_tile, position, util)
        for T in ctx.reach_nc:                               # positions candidates (ordre movable natif)
            # `#971-r4` : ordre PAR POSITION (fromHere a l'origine, voisinage STOCKE ailleurs),
            # jamais l'ordre de l'UNION -- a utilite EGALE, `AddAction` est keep-first, donc
            # l'ORDRE **est** la decision.
            for ST in tiles_in_native_order(ctx, T, from_here, union, eligibles):
                if not bq.is_adjacent(T, ST, ctx.elev_by_pos, neigh):
                    continue                                 # spawn = hex ADJACENT a T au sens du SELECTEUR
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

    # `_eligible_spawn_tiles` A ETE SUPPRIME (#971-r4). Il ne lisait que la vue `targets` du RPC --
    # l'UNION sur toutes les tuiles de move -- alors que `GetEligibleTargetsSelectable` interroge
    # `GetValidTargets(caster, UnitPosition(P), abilityType)` **PAR POSITION**. Le foyer commun
    # `_base.eligible_target_tiles` rend les DEUX vues (`fromHere` + union), et
    # `_base.tiles_in_native_order` en derive l'ordre par position. Garder les deux voies aurait
    # laisse un second lecteur de la seule union, donc un second ordre -- exactement le fork que
    # ce residu existait pour fermer.

    def _nearest_enemy_tile(self, ctx: NCContext) -> "tuple | None":
        """Mirror `IdunBattle.Core.Services.BattleQuery$$GetNearestEnemy`, VERBATIM :

            best = null ; bestD = int.MaxValue ; bestAdj = false
            tiles = position.HasValue ? position.Value : GetUnitPosition(caster)
            foreach (u in GetAllAliveUnits(null))
                if (!UnitExtensions.IsEnemy(caster, u, state))       continue
                if (UnitExtensions.IsIrrelevantObject(u))            continue
                d   = BattleQuery.GetDistance(tiles, u)
                adj = BattleQuery.AreEntitiesAdjacent(tiles, u)
                if (d < bestD || (adj && !bestAdj)) { best = u ; bestAdj = adj ; bestD = d }
            return best

        LE TERME « EN MELEE » EST `AreEntitiesAdjacent`, PAS `IterateAdjacentTiles` (#433-r4-r2).
        Le decompile appelle `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent`
        DIRECTEMENT -- pas `$$AreUnitsInMelee` (qui est de toute facon un passe-plat d'une ligne
        vers la meme fonction). Or `AreEntitiesAdjacent` delegue a
        `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` : `(|dElev| < 2) & (t1 == t2 ||
        IsNeighbour(t1, t2))`, COURT-CIRCUIT D'IDENTITE compris. Le foyer mirror est donc
        `battle_query.are_entities_adjacent` et NON `battle_query.is_adjacent`, qui mirrore
        `TileQuery$$IterateAdjacentTiles` -- une primitive DIFFERENTE, qui ne rend jamais la tuile
        source (#433-r1 §4 la designe explicitement comme contre-exemple : l'ALIGNER, elle, ferait
        compter chaque unite comme sa propre voisine).

        ECART OBSERVABLE DU RE-POINTAGE : AUCUN, et par COMPOSITION. Les deux foyers ne different
        que par le court-circuit d'identite, atteint ssi les deux operandes designent la MEME tuile
        -- ici la tuile du caster et celle d'un ennemi VIVANT distinct, que l'occupation exclusive
        du plateau rend disjointes. La porte d'elevation, elle, etait deja portee des deux cotes
        (`is_adjacent` la porte, et `are_entities_adjacent` la lui delegue). Le re-pointage est
        pose par FIDELITE, pas parce qu'un regime l'exige.

        RESIDUS NOMMES, non traites ici : le filtre `IsIrrelevantObject` n'est pas porte (ordre
        `ctx.epos`) ; le natif compare des EMPREINTES (`GetUnitPosition(caster)` x `GetTiles(u)`)
        la ou le port compare deux tuiles principales (#419-r1-tr10-r2) ; l'ordre d'enumeration
        natif (`GetAllAliveUnits`) est approxime par l'ordre de `ctx.epos` (tie residu).

        PASSE-PLAT vers le foyer UNIQUE `battle_query.get_nearest_enemy` (#971-r1) -- ce corps
        etait l'un des TROIS mirrors du meme natif. `position=None` **EST** le `Nullable` VIDE de
        ce call-site : l'ancre retombe donc sur `GetUnitPosition(caster)` = `ctx.origin`, ce que
        ce corps ecrivait a la main. Ce playbook ne veut que la TUILE -> `[1]`."""
        near = bq.get_nearest_enemy(ctx)     # `GetNearestEnemy(unit, <Nullable position VIDE>)`
        return None if near is None else near[1]
