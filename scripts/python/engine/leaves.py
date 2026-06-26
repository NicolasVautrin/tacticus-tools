"""Leaves NonComparable — registre `abilityType → scoreur` (heuristique entière dans la leaf, §1.3).

Une leaf NonComparable (summon/buff/mouvement-spécial) énumère ses candidats (tuiles/cibles via
`abilityTargets`) et les score par une heuristique PROPRE à l'ability (pas la somme pondérée des
Comparable). RE'd une par une (ghidra), agreement-driven. cf. docs/rl/playbook-engine.md §1.3 + §10.

Forme d'un scoreur : `score(tile, ctx) -> float` où ctx porte au moins `enemy_positions`.

⚠ SÉLECTION : ces leaves vivent dans le bucket-tree natif (catégorie/priorité propre), PAS dans
l'argmax-utilité plat des attaques (leur utilité ~0-6 n'est PAS comparable au barème kill ~100).
Le harnais teste une RÈGLE DE TIR empirique (cf. engine_validate) ; l'ordre exact des catégories du
bucket-tree reste à RE (item Phase 2b).
"""
from __future__ import annotations

import hexgeo

# ActiveAbilityType des leaves NonComparable portées.
ABERRANT_HYPERMORPH = 1166


def _adjacent_enemy_count(tile: tuple, ctx: dict) -> float:
    """`AberrantHypermorphPlaybook.GetUtility` (RE) : utilité d'une tuile de spawn = NOMBRE
    d'ennemis ADJACENTS (hex-dist 1) à la tuile. L'IA invoque là où le summon engage le plus
    d'ennemis. (`FUN_180007c20(0x7e,…)` = get-adjacent-enemies, `FUN_180002560` = .Count.)"""
    c = (tile[0], tile[1])
    enemies = ctx.get("enemy_positions") or []
    return float(sum(1 for e in enemies if hexgeo.distance(c, e) == 1))


# Registre : abilityType -> (scoreur, kind). kind="summon" pilote la règle de tir du harnais.
LEAVES: dict[int, dict] = {
    ABERRANT_HYPERMORPH: {"score": _adjacent_enemy_count, "kind": "summon",
                          "name": "AberrantHypermorph"},
}


def is_leaf(ability_id: int) -> bool:
    return ability_id in LEAVES


def score_leaf(ability_id: int, tile: tuple, ctx: dict) -> float:
    fn = LEAVES.get(ability_id, {}).get("score")
    return fn(tile, ctx) if fn else 0.0


def best_leaf_tile(ability_id: int, tiles: list, ctx: dict) -> tuple:
    """argmax du scoreur de la leaf parmi les tuiles candidates. ((col,row)|None, util|None)."""
    best = None
    bu = None
    for t in tiles:
        c = (t.get("col"), t.get("row")) if isinstance(t, dict) else (t[0], t[1])
        if c[0] is None:
            continue
        s = score_leaf(ability_id, c, ctx)
        if bu is None or s > bu:
            best, bu = c, s
    return best, bu
