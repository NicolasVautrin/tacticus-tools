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


# ─────────────────────────────────────────────────────────────────────────────────────────────
# NonComparable ATTACK abilities — playbook SANS `MakeDamagePredictions` dont `EvaluateNonComparable`
# score par une HEURISTIQUE DE COMPTE d'ennemis, mais SUR L'ÉCHELLE de `damage_composite` (grâce au poids
# du cctor). Elles entrent donc dans le MÊME argmax plat (bucket tier-0, `ChooseAction` flat-default) que
# les attaques Comparable — PAS dans la règle-de-tir fallback des summons. utility = base + count x weight.
# cf. architecture.md (bucket-tree, within-tier flat argmax) + [[project_playbook_engine]].
# ─────────────────────────────────────────────────────────────────────────────────────────────
NONCOMP_ATTACK: dict[int, dict] = {
    # kind="adjacent_count" : utilité = base + (#ennemis adjacents à la TUILE d'attaque) x weight.
    1129: {"name": "BloodyFury", "kind": "adjacent_count", "base": 1, "weight": 10},
    # BloodyFuryPlaybook.EvaluateNonComparable @181122be0 = 1 + (#adjacents) x 10 (W=10 cctor @181123340).
    # NB AberrantHypermorph (1166, summon) N'EST PAS ici : sa tuile est une tuile de SPAWN (vide, via
    # abilityTargets kind="tile"), PAS une tuile d'attaque du plan -> chemin dédié (leaves.py LEAVES + 1ter) ;
    # son utilité = FromInt(#ennemis adjacents au spawn), poids brut 1 (cctor @181119cd0 = seuil 1, sans poids
    # -> échelle basse : ne bat le dégât que si aucune bonne attaque). Wiring flat-argmax spawn-tile = TODO.
    # kind="target_hp" : utilité = PV COURANTS de la cible (GetStat(5)=Health) -> DOMINE (échelle ~milliers).
    1183: {"name": "VexillaMagnifica", "kind": "target_hp"},
    # VexillaMagnificaPlaybook.EvaluateNonComparable @18117f6f0 = FromInt(GetStat(cible,5=Health)) ; debuff
    # (dmgReductionPct) sur l'ENNEMI le plus haut-PV ; skip si déjà affecté (HasEffect 0x48a) [filtre TODO].
}


def noncomp_attack_utility(ability_id: int, tile: tuple | None, enemy_positions: list,
                           target_hp: int | None = None) -> float | None:
    """Utilité NonComparable d'une ability d'ATTAQUE (playbook sans MakeDamagePredictions) évaluée à la
    TUILE d'attaque (post-move). `adjacent_count` = base + (#ennemis adjacents à `tile`) x weight (poids
    cctor -> échelle damage_composite) ; `target_hp` = PV courants de la cible (GetStat(5), échelle ~milliers
    -> domine). None si l'ability n'est pas NonComparable."""
    spec = NONCOMP_ATTACK.get(ability_id)
    if not spec:
        return None
    kind = spec.get("kind")
    if kind == "target_hp":
        return float(target_hp) if target_hp and target_hp > 0 else None
    if tile is None:
        return None
    cnt = sum(1 for e in (enemy_positions or []) if hexgeo.distance(tile, e) == 1)
    return float(spec["base"] + cnt * spec["weight"])


def is_noncomp_attack(ability_id: int) -> bool:
    return ability_id in NONCOMP_ATTACK


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
