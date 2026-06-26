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

# MaxDistanceToUnitTile : DÉSACTIVÉ par défaut. A/B agreement-driven (seeds 777 + 2024,
# trajectoire native déterministe) : interprété comme « distance à la tuile d'ORIGINE de
# l'unité », ce terme est au mieux neutre (777 : far==off) et au pire NUISIBLE (2024 step10 :
# far envoie u84 sprinter dans un coin à ~6hex de la cible native ; off → ~1hex). `off` domine
# donc `far` sur les 2 seeds. Conclusion : la *tuile de référence* RE'd (mon hypothèse =
# tuile courante de l'unité) est FAUSSE — c'est probablement une autre tuile (formation alliée /
# tuile-cible), pas l'origine. Terme gardé GATÉ (réactivable via env) une fois la vraie référence
# RE'd. cf. docs/rl/playbook-engine.md §7. Piloté par ENGINE_UNITTILE_MODE :
#   "off" (défaut) : terme désactivé (validé ≥ far)
#   "far"          : Wfar=FarthestTile(700), Wclose=ClosestTile(400) → récompense de s'éloigner de l'origine
#   "near"         : Wfar=ClosestTile(400),  Wclose=FarthestTile(700) → récompense de rester près (777 : pire)
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
