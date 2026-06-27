"""Scoring de MOUVEMENT — repositionnement pur (le profil natif « MovementSuggestion », §1.5).

RE (ghidra gqfc5mff6c) des `IdunBattle.AI.Utilities.*Utility.<EvaluateMovementInSteps>`. Le
score d'une tuile de mouvement = **SOMME pondérée** de termes géométriques, chacun = (poids BC)
× (terme géométrique). Les 4 termes de position RE'd :

  MinDistanceToClosestEnemy : wMin × min_d(tile, enemies)              PerTileDistance = -100
  MaxDistanceToEnemies      : Σ_e [ Wfar - (Wfar-Wclose)/d_e ]         ClosestEnemy 10, FarthestEnemy 100
  MaxDistanceToUnitTile     : Wfar - (Wfar-Wclose)/d_origin            ClosestTile 400, FarthestTile 700  (DOMINANT)
  Elevation                 : 10·elev (+10 si plus haute, -5 si plus basse)   (OMIS : pas de data tuile)

Forme commune RE'd des 2 termes `MaxDistance*` (cf. les deux MoveNext) :
    f(d) = Wfar - (Wfar - Wclose) / max(d, 1)        # f(1)=Wclose, f(∞)→Wfar (rendements décroissants)
  - `MaxDistanceToEnemies`  : d = dist hex tuile→chaque ennemi, SOMMÉ sur tous les ennemis.
  - `MaxDistanceToUnitTile` : d = dist hex tuile→tuile d'ORIGINE de l'unité (= avant de bouger).

Le terme DOMINANT est `MaxDistanceToUnitTile` (700 >> 100) : l'IA récompense surtout d'ENGAGER
son mouvement (s'éloigner de la tuile d'origine), modulé ensuite par la proximité au plus proche
ennemi (MinDist, -100) et l'éloignement global aux ennemis (MaxDistToEnemies).

L'assignation Wfar/Wclose (étiquette des sous-clés) + le SET ACTIF exact sont *agreement-driven*
(le harnais `engine_validate.py` les confirme/corrige). On compare l'ARGMAX (la tuile choisie),
pas la valeur d'utilité exacte → l'arithmétique Fix64 n'a pas à être répliquée (cf. doc §6).

cf. docs/rl/playbook-engine.md §1.5 + §7.
"""
from __future__ import annotations

import os

import hexgeo
from .weights import Weights
from .utilities import tile_composite

# MaxDistanceToUnitTile : DÉSACTIVÉ par défaut — CONFIRMÉ par ghidra (pas seulement A/B).
# `UtilitiesDatabase.InitializeUtilities._composedUtilityLookup` (RE gqfc5mff6c, doc §13.3) :
#   MovementSuggestion(32) = [Tile(7), TileDistance(33)]   ← le décideur de MOVE PUR
#   UnitMovementFromTemporary(5) = [UnitMovement(6), MaxDistanceToUnitTile(17)]   ← SEUL porteur du terme 17
# ⇒ MaxDistanceToUnitTile n'est JAMAIS dans le move pur ; il ne s'applique qu'aux moves « depuis une
# tuile temporaire ». La formule RE'd (MaxDistanceToUnitTileUtility.<d__2>.MoveNext @1810fdeb0) =
#   A - (A-B)/d  avec A=FarthestTile(700), B=ClosestTile(400), réf = tuile COURANTE de l'entité —
# elle est donc CORRECTE, mais hors-périmètre du move pur. Le défaut `off` est ainsi JUSTIFIÉ (l'A/B
# qui trouvait `off ≥ far` mesurait cette absence). Terme gardé GATÉ pour le futur port du décideur
# UnitMovementFromTemporary. cf. docs/rl/playbook-engine.md §13.3. Piloté par ENGINE_UNITTILE_MODE :
#   "off" (défaut) : terme désactivé (hors MovementSuggestion — ghidra)
#   "far"          : Wfar=FarthestTile(700), Wclose=ClosestTile(400) → s'éloigner de la tuile courante
#   "near"         : Wfar=ClosestTile(400),  Wclose=FarthestTile(700) → rester près
_UNITTILE_MODE = os.environ.get("ENGINE_UNITTILE_MODE", "off").lower()


def _maxdist_term(d: int, w_close: float, w_far: float) -> float:
    """Forme RE'd commune `MaxDistanceToEnemies` / `MaxDistanceToUnitTile` :
    f(d) = w_far - (w_far - w_close)/d ; f(1)=w_close, f(∞)→w_far."""
    d = max(int(d), 1)
    return w_far - (w_far - w_close) / d


def move_utility(tile: tuple, origin: tuple | None, enemy_positions: list, wt: Weights,
                 ranged: bool = False) -> float:
    """Utilité d'une tuile de mouvement (somme des termes de position, §1.5)."""
    if not enemy_positions:
        return 0.0
    c = (tile[0], tile[1])
    dists = [hexgeo.distance(c, e) for e in enemy_positions]
    mind = min(dists)

    # 1) MinDistanceToClosestEnemy : wMin (-100) × min_d  → tire VERS l'ennemi le plus proche.
    u = wt.sub("MinDistanceToClosestEnemy", "PerTileDistance") * mind

    # 2) MaxDistanceToEnemies : Σ_e f(d_e)  (ClosestEnemy=Wclose, FarthestEnemy=Wfar).
    we_close = wt.sub("MaxDistanceToEnemies", "ClosestEnemy")
    we_far = wt.sub("MaxDistanceToEnemies", "FarthestEnemy")
    for d in dists:
        u += _maxdist_term(d, we_close, we_far)

    # 3) MaxDistanceToUnitTile : f(d_origin)  — terme DOMINANT (400/700). Assignation
    #    Wfar/Wclose A/B (cf. _UNITTILE_MODE) car ambiguë sans le DAT→string.
    if origin is not None and _UNITTILE_MODE != "off":
        do = hexgeo.distance(c, (origin[0], origin[1]))
        wc = wt.sub("MaxDistanceToUnitTile", "ClosestTile")
        wf = wt.sub("MaxDistanceToUnitTile", "FarthestTile")
        if _UNITTILE_MODE == "near":
            wc, wf = wf, wc
        u += _maxdist_term(do, wc, wf)

    # 4) RangedAdjacentEnemy (profil MovementSuggestion) : pénalise une unité RANGED qui finit
    #    adjacente à un ennemi (HasAdjacentEnemy = -50).
    if ranged and mind <= 1:
        u += wt.movement_sub("RangedAdjacentEnemy", "HasAdjacentEnemy")

    return u


def best_move(tiles: list, origin: tuple | None, enemy_positions: list, wt: Weights,
              ranged: bool = False) -> tuple:
    """argmax `move_utility` parmi les tuiles atteignables. Renvoie ((col,row)|None, util|None).
    Tie-break STABLE (première tuile insérée à utilité égale — cf. select.choose_action)."""
    best = None
    bu = None
    for t in tiles:
        c = (t["col"], t["row"])
        s = move_utility(c, origin, enemy_positions, wt, ranged)
        if bu is None or s > bu:
            best, bu = c, s
    return best, bu


def best_move_faithful(tiles: list, elev_by_pos: dict, enemy_positions: list, wt: Weights,
                       steppable_by_pos: dict | None = None,
                       pathdist_by_pos: dict | None = None,
                       is_temporary_by_pos: dict | None = None) -> tuple:
    """Move scoring FIDÈLE — décideur **UnitMovement(6) = Tile(7) + MinDistanceToClosestEnemy(16)**
    (composition LUE runtime, doc §13.8/13.11). `U(tuile) = tile_composite(Tile(7)) + wMin×d`.
    PAS de `MaxDistanceToEnemies` (dans AUCUN composite) ni `MaxDistanceToUnitTile` (seulement
    UnitMovementFromTemporary).

    ⚠ `d` = distance de CHEMIN (pathfinding), PAS hex (RE `GetMinDistanceToEnemy`, doc §13.12) :
    si `pathdist_by_pos` (RPC `pathDistToEnemies`) est fourni, on l'utilise ; sinon fallback hex
    (approximation). `elev_by_pos` = `{(col,row): elevation}` (RPC tileMeta) ; max/min sur les
    tuiles candidates (= `LoadRelevantTileElevations`). `is_temporary_by_pos` = `{(col,row): bool}`
    (tileMeta.isTemporary) → leaf TemporaryTile(13) (-10000 sur tuile temporaire). Renvoie ((col,row)|None, util).
    """
    if not enemy_positions:
        return None, None
    coords = [(t["col"], t["row"]) for t in tiles]
    elevs = [elev_by_pos.get(c) for c in coords]
    elevs = [e for e in elevs if e is not None]
    emax, emin = (max(elevs), min(elevs)) if elevs else (None, None)
    wmin = wt.sub("MinDistanceToClosestEnemy", "PerTileDistance")
    tile_off = os.environ.get("ENGINE_TILE_OFF") == "1"   # diagnostic : MinDist seul (Tile=0)
    best = None
    bu = None
    for c in coords:
        e = elev_by_pos.get(c)
        meta: dict = {"elevation": e, "elevation_max": emax, "elevation_min": emin} \
            if e is not None else {}
        if steppable_by_pos and c in steppable_by_pos:
            meta["steppable"] = steppable_by_pos[c]
        if is_temporary_by_pos and c in is_temporary_by_pos:
            meta["is_temporary"] = is_temporary_by_pos[c]
        # MinDist : distance CHEMIN si dispo (fidèle), sinon hex (fallback approx).
        pd = pathdist_by_pos.get(c) if pathdist_by_pos else None
        mind = pd if (pd is not None and pd >= 0) else min(hexgeo.distance(c, ep)
                                                           for ep in enemy_positions)
        tile_u = 0.0 if tile_off else tile_composite(c, meta, {}, wt)
        u = tile_u + wmin * mind
        if bu is None or u > bu:
            best, bu = c, u
    return best, bu
