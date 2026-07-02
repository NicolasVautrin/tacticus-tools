"""Leaves NonComparable — registre `abilityType → scoreur` (heuristique entière dans la leaf, §1.3).

Une leaf NonComparable (summon/buff/attaque-effet) énumère ses candidats (tuiles/cibles via
`abilityTargets` ou le plan natif) et les score par une heuristique PROPRE à l'ability (pas la somme
pondérée des Comparable). RE'd une par une (ghidra). cf. docs/rl/playbook-engine.md §1.3 + §10.

SÉLECTION NATIVE (RE'd — remplace l'ancienne « règle de tir empirique » et l'ancien wiring
flat-argmax) : `ABaseAiActorTactic.InitAbilityTypeLists @1810ed540` répartit chaque ability
par la nature de son playbook :
  - `IsComparable`  -> liste FINALE (tactic+0x38) : attaque normale, PlasmaCannon, heals, Dakka…
  - NonComparable   -> dict par `get_Priority` (tactic+0x40) : First 1000 / Early 100 / Normal 0 /
                       Late -100 / Last -1000 (enum AbilityPriority ; défaut @1802B15B0 = 0).
`GetDefaultActiveAbilityActionGenerators @1810ed0c0` crée les generators DANS CET ORDRE
(1000, 100, 0, -100, -1000, FINALE, puis MovementGenerator) et le tactic prend le PREMIER
generator qui rend une action ⇒ une ability NonComparable qui « tire » (utilité >= MIN_UTILITY
de son cctor, gate `Bucket.AddAction @1813fbcc0` : `util >= min`, remplacement STRICT `>`)
GAGNE TOUJOURS sur les Comparable, quelle que soit l'utilité de l'attaque (prouvé seed777
step7 FightingRetreat u=2 vs attaque ~30, step14 summon u>=1 vs attaque 61). Au sein du tier :
argmax STRICT (tie -> premier énuméré), utilité = heuristique BRUTE (PAS de terme Tile7 —
`CalculateActionUtility`/Tile7 est un chemin Comparable-only). Aucun des playbooks portés
n'override `get_Priority` -> tous tier Normal(0).
"""
from __future__ import annotations

import hexgeo

# ActiveAbilityType des leaves NonComparable portées.
ABERRANT_HYPERMORPH = 1166
FIGHTING_RETREAT = 1081


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Registre unifié des abilities NonComparable portées (tier Normal 0). `min` = MIN_UTILITY du
# cctor du playbook (gate AddAction `util >= min`). `kind` pilote le calcul du harnais :
#   adjacent_count      -> utilité = base + (#ennemis adjacents à la TUILE d'attaque) x weight ;
#                          (cible, tuile) = ranked du plan natif (ability d'ATTAQUE).
#   target_hp           -> utilité = PV COURANTS de la cible (GetStat(5)=Health) ; idem plan.
#   self_adjacent_combo -> utilité = |ennemis adj| + (si >0) |alliés adj - self| balayée sur les
#                          tuiles atteignables (origine incluse) ; cible = SELF.
#   summon              -> utilité = #ennemis adjacents à la tuile de SPAWN (abilityTargets
#                          kind="tile") ; cible = None (l'id natif = l'unité spawnée, post-exec).
# ─────────────────────────────────────────────────────────────────────────────────────────────
NONCOMP: dict[int, dict] = {
    1129: {"name": "BloodyFury", "kind": "adjacent_count", "base": 1, "weight": 10, "min": 1},
    # BloodyFuryPlaybook.EvaluateNonComparable @181122be0 = 1 + (#adjacents) x 10
    # (cctor @181123340 : MIN_UTILITY=1, ADJACENT_ENEMIES_UTILITY=10, PROBABILITY_PER_HIT=20).
    1183: {"name": "VexillaMagnifica", "kind": "target_hp", "min": 1},
    # VexillaMagnificaPlaybook.EvaluateNonComparable @18117f6f0 = FromInt(GetStat(cible,5=Health)) ;
    # debuff (dmgReductionPct) sur l'ENNEMI le plus haut-PV ; skip si déjà affecté (HasEffect 0x48a)
    # [filtre TODO]. cctor @18117fa30 : MIN_UTILITY=1.
    FIGHTING_RETREAT: {"name": "FightingRetreat", "kind": "self_adjacent_combo", "min": 2},
    # FightingRetreatPlaybook.EvaluateNonComparable @181131ff0 :
    #   A = GetAdjacentEnemies(tile, player)      [BattleQuery slot 124]
    #   B = GetAdjacentFriends(tile, player)-self [slot 128 ; sans filtre de trait]
    #   u = |A| + (|A| > 0 ? |B| : 0) ; cible = SELF. cctor @1811323b0 : MIN_UTILITY=2.
    ABERRANT_HYPERMORPH: {"name": "AberrantHypermorph", "kind": "summon", "min": 1},
    # AberrantHypermorphPlaybook (RE) : utilité d'une tuile de spawn = #ennemis adjacents
    # (`FUN_180007c20(0x7e=slot 126 GetAdjacentEnemies)`). cctor @181119cd0 : MIN_UTILITY=1.
}
# NB RadBombardmentPlaybook (1116) N'EST PAS porté : EvaluateNonComparable @181154130 =
# #ennemis dans le blast GetAffectedTiles (min 2, cctor @1811545f0) — nécessite la géométrie
# du blast offline. Sur seed777 le natif ne le tire jamais (u<2) -> l'omission = même issue ;
# LIMITE CONNUE : un état à >=2 ennemis dans le blast serait un miss moteur.


def _adjacent_count(tile: tuple, positions: list) -> int:
    return sum(1 for p in (positions or []) if hexgeo.distance((tile[0], tile[1]), p) == 1)


def noncomp_attack_utility(ability_id: int, tile: tuple | None, enemy_positions: list,
                           target_hp: int | None = None) -> float | None:
    """Utilité NonComparable d'une ability d'ATTAQUE évaluée à la TUILE d'attaque (post-move).
    `adjacent_count` = base + (#ennemis adjacents) x weight ; `target_hp` = PV courants de la
    cible (GetStat(5)). None si l'ability n'a pas ce kind."""
    spec = NONCOMP.get(ability_id)
    if not spec:
        return None
    kind = spec.get("kind")
    if kind == "target_hp":
        return float(target_hp) if target_hp and target_hp > 0 else None
    if kind != "adjacent_count" or tile is None:
        return None
    return float(spec["base"] + _adjacent_count(tile, enemy_positions) * spec["weight"])


def fighting_retreat_utility(tile: tuple, enemy_positions: list, friend_positions: list) -> float:
    """`FightingRetreatPlaybook.EvaluateNonComparable @181131ff0` : u = |ennemis adjacents à la
    tuile| + (si > 0) |alliés adjacents à la tuile| (self déjà exclu de `friend_positions` ; le
    natif fait `B.Remove(self)` car le caster PEUT être adjacent à sa tuile candidate)."""
    a = _adjacent_count(tile, enemy_positions)
    if a == 0:
        return 0.0
    return float(a + _adjacent_count(tile, friend_positions))


def summon_utility(tile: tuple, enemy_positions: list) -> float:
    """AberrantHypermorph : #ennemis adjacents à la tuile de spawn."""
    return float(_adjacent_count(tile, enemy_positions))


def noncomp_spec(ability_id: int) -> dict | None:
    return NONCOMP.get(ability_id)


def is_noncomp(ability_id: int) -> bool:
    return ability_id in NONCOMP


def is_summon(ability_id: int) -> bool:
    return (NONCOMP.get(ability_id) or {}).get("kind") == "summon"


# ── Compat (anciens noms consommés par engine_validate ; à purger avec le refactor du harnais) ──
LEAVES = {k: v for k, v in NONCOMP.items() if v.get("kind") == "summon"}
NONCOMP_ATTACK = {k: v for k, v in NONCOMP.items() if v.get("kind") in ("adjacent_count", "target_hp")}


def is_noncomp_attack(ability_id: int) -> bool:
    return ability_id in NONCOMP_ATTACK


def is_leaf(ability_id: int) -> bool:
    return ability_id in LEAVES
