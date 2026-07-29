"""`IdunBattle.AI.Utilities` — DISPATCHER (`UtilitiesDatabase.GetUtility` + `Playbook.GetMovementUtility`)
+ utilites de MOUVEMENT propres (DislikeStartingTiles).

Les feuilles/composites Tile (7) et Damage (34) vivent dans `engine.utilities.{tile,damage}` (POUR EVITER
LES CYCLES D'IMPORT : `engine.playbook.base` les tire tres tot ; les heberger sous `engine.ai` creerait
un cycle via `engine.ai.context` -> `engine.playbook.scene`). Ce module les REFERENCE et les enregistre.

Doctrine « 1:1 classe native -> classe Python » : une CLASSE `*Utility` par utilite (BaseUtility/
ComposedUtility dans `engine.utilities.base`). `get_movement_utility` = `Playbook<T>.IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetMovementUtility` = `ComposedUtility.EvaluateMovement(UtilitiesDatabase.GetUtility(type), caster@pos)`.

SIGNATURE : chaque sous-systeme a la sienne (tile: `(tile,meta,ctx,wt)` ; damage: `(pred,max_hp,wt)` ;
mouvement: `(ctx,pos)`). `get_movement_utility` dispatch en connaissance de cause (Tile via l'adaptateur
`(ctx,pos)->tile` = `base.tile_utility` ; DislikeStartingTiles direct `(ctx,pos)`)."""
from __future__ import annotations

from engine.utilities.base import BaseUtility, ComposedUtility          # noqa: F401 (re-export)
from engine.utilities.tile import TILE_UTILITY, TILE_LEAVES
from engine.utilities.damage import DAMAGE_UTILITY
from engine.utilities.move import MIN_DIST_UTILITY, UNIT_MOVEMENT
from engine.utilities.heal import HEAL_UTILITY
from engine.utilities.repair import REPAIR_UTILITY
from engine.utilities.effect import ADDED_EFFECT_UTILITY
from engine.utilities.utility_type import UtilityType


class DislikeStartingTilesUtility(BaseUtility):
    """`IdunBattle.AI.Utilities.DislikeStartingTilesUtility` (`UtilityType.DislikeStartingTiles=27`,
    dump.cs gqfc5mff6c). `IdunBattle.AI.Utilities.DislikeStartingTilesUtility$$EvaluateMovementInSteps` (`<…>IdunBattle.AI.Utilities.DislikeStartingTilesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`) : penalite
    si l'empreinte de `pos` chevauche l'empreinte de DEBUT-DE-TOUR de l'unite (biais a quitter le spawn).
    Mirror du decompile (#R30 -- corps RELU en entier) :

        util  = Fix64.FromInt(0);
        start = EntityExtensions.GetTurnStartPosition(unit, state);      // Nullable<UnitPosition>
        n     = UnitExtensions.GetFeetCount(unit, state);
        tiles = new List<TileEntity> { case.UnitPosition.MainTile };     // UnitPosition$$get_MainTile
        if (n == 7) tiles.AddRange(battleQuery.GetAdjacentTiles(tiles, false, true, true));
        if (start.HasValue && start.Value.ContainsAnyOf(tiles))
            util += BaseUtility.GetUtilityValue(query, DislikeStartingTiles);
        return util;

    Deux points que la paraphrase « pos == origine » manquait :
      * l'empreinte candidate part de la MAIN TILE de la `UnitPosition` (= `feet[0]`), et **n'est
        etendue QUE si `GetFeetCount == 7`** (l'anneau des voisins). Une unite a **3** pieds n'etend
        RIEN ici : le natif ne teste que sa main tile. C'est un quirk, pas un oubli ;
      * le test final est un CHEVAUCHEMENT d'ensembles (`ContainsAnyOf`) entre l'empreinte de depart
        et l'empreinte candidate, pas une egalite de tuiles.
    Pour une unite a 1 pied les deux formulations coincident exactement (`{pos} inter {origin}`), donc
    le comportement du cas nominal est inchange.

    DATA-GAP RESTANT (no-op cite, doctrine « pas d'invention ») : le poids
    `GetUtilityValue(DislikeStartingTiles)` n'est pas identifie dans les weights BC charges -> `_WEIGHT`
    reste 0.0. Le trou `GetFeetCount`, lui, est COMBLE (substrat #R30).
    ATTENTION (validateur R2) : ce terme n'est PAS neutre. Il PENALISE l'origine (0 ailleurs) = c'est le
    TIE-BREAKER natif origine-vs-move qui pousse l'unite HORS de sa tuile de depart. Le tier NonComparable
    (`get_Priority`, cf. NATIVE_PRIORITY) et le CENTRE marque restent inchanges, MAIS le no-op
    (_WEIGHT=0) neutralise ce tie-breaker
    -> biais du port a RESTER sur place au lieu de bouger (couple au trou#6 R1 : origine evaluee en dernier
    cote natif). A confirmer live : si le poids BC DislikeStartingTiles est != 0, cabler `_WEIGHT`."""
    UTILITY_TYPE = int(UtilityType.DislikeStartingTilesUtility)  # 28

    def candidate_footprint(self, ctx, pos) -> list:
        """`tiles` du corps natif : `[UnitPosition.MainTile]`, etendu de l'ANNEAU des voisins SI ET
        SEULEMENT SI `GetFeetCount(unit) == 7`. `ctx.feet_count` = le compte porte par l'appelant
        (absent -> 1, le cas nominal) ; `ctx.neigh_by_pos` fournit le voisinage natif."""
        tiles = [pos]
        if int(getattr(ctx, "feet_count", 1) or 1) != 7:
            return tiles
        neigh = getattr(ctx, "neigh_by_pos", None) or {}
        for n in (neigh.get(pos) or ()):               # GetAdjacentTiles(tiles, false, true, true)
            if n not in tiles:
                tiles.append(n)
        return tiles

    def evaluate(self, ctx, pos) -> float:
        _WEIGHT = 0.0  # TODO cabler BaseUtility.GetUtilityValue(query, DislikeStartingTiles) [poids BC] (R2)
        # `start.Value.ContainsAnyOf(tiles)` : chevauchement de l'empreinte de DEBUT DE TOUR
        # (`ctx.start_feet`, defaut = la seule `ctx.origin`) avec l'empreinte candidate.
        start = getattr(ctx, "start_feet", None)
        if not start:
            origin = getattr(ctx, "origin", None)
            start = [origin] if origin is not None else []
        if not start:
            return 0.0
        footprint = self.candidate_footprint(ctx, pos)
        return _WEIGHT if any(s in footprint for s in start) else 0.0


class UtilitiesDatabase:
    """`IdunBattle.Core.Services.UtilitiesDatabase` — registre `UtilityType -> BaseUtility` (peuple par
    `IdunBattle.Core.Services.UtilitiesDatabase$$InitializeUtilities`). `IdunBattle.Core.Services.UtilitiesDatabase$$GetUtility` = lookup par type (None si non porte)."""
    _BY_TYPE: dict = {}

    @classmethod
    def register(cls, util: BaseUtility) -> BaseUtility:
        cls._BY_TYPE[util.UTILITY_TYPE] = util
        return util

    @classmethod
    def get_utility(cls, utility_type: int) -> "BaseUtility | None":
        return cls._BY_TYPE.get(utility_type)


# Enregistrement (composites + feuilles + mouvement) — reproduit `IdunBattle.Core.Services.UtilitiesDatabase$$InitializeUtilities`.
UtilitiesDatabase.register(TILE_UTILITY)      # Tile = 7
UtilitiesDatabase.register(DAMAGE_UTILITY)    # Damage = 34
UtilitiesDatabase.register(UNIT_MOVEMENT)     # UnitMovement = 6 (Tile + MinDistanceToClosestEnemy)
UtilitiesDatabase.register(MIN_DIST_UTILITY)  # MinDistanceToClosestEnemy = 16
UtilitiesDatabase.register(HEAL_UTILITY)      # Heal = 44
UtilitiesDatabase.register(REPAIR_UTILITY)    # RepairedAmount = 47
UtilitiesDatabase.register(ADDED_EFFECT_UTILITY)  # AddedTileEffects = 45
_DISLIKE_STARTING_TILES = UtilitiesDatabase.register(DislikeStartingTilesUtility())  # 27
for _name, _inst in TILE_LEAVES.values():     # feuilles Tile (8, 9, 13, 19, …)
    if _inst is not None:
        UtilitiesDatabase.register(_inst)
for _child in DAMAGE_UTILITY.children:        # feuilles Damage (35, 36, 37)
    UtilitiesDatabase.register(_child)


def get_movement_utility(ctx, pos, utility_type: int) -> float:
    """`Playbook<T>.IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetMovementUtility` = `ComposedUtility.EvaluateMovement(
    UtilitiesDatabase.GetUtility(utility_type), caster@pos)`. Dispatch par signature de sous-systeme.
    0.0 si l'utilite de mouvement n'est pas (encore) resolue pour ce type."""
    if utility_type == UtilityType.Tile:
        # Tile(7) : l'eval MOUVEMENT passe par l'adaptateur (ctx,pos)->(tile,meta,{},wt) = base.tile_utility
        # (import LAZY pour eviter tout cycle). Carte plate ~0.
        if getattr(ctx, "wt", None) is None or getattr(ctx, "elev_by_pos", None) is None:
            return 0.0
        from engine.playbook.base import tile_utility
        return tile_utility(ctx, pos)
    if utility_type == UtilityType.DislikeStartingTilesUtility:
        return _DISLIKE_STARTING_TILES.evaluate(ctx, pos)
    return 0.0
