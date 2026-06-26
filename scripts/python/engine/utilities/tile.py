"""Tile(7) composite — les 29 leaf-utilities de tuile (membership LUE runtime, doc §13.8).

`Tile(7)` (composite scoré par `Weight[Tile=7]` dans `CalculateUtilityFromTilePrediction`) = SOMME de
29 feuilles. La plupart sont SITUATIONNELLES (terrain spécial / trait de l'unité / effet présent) → =0
sur une bataille basique plate. Chaque feuille = `f(tile, meta, ctx, wt) -> float`, portée depuis son
`*Utility.<EvaluateMovementInSteps>d__N.MoveNext` (ghidra gqfc5mff6c) + poids BC `Utilities.Default`.

⚠ DÉPENDANCE DONNÉE : beaucoup de feuilles consomment une METADATA PAR TUILE (élévation, effets de
statut, occupant steppable) que `aiMovableTiles` n'expose pas (col/row seulement). On consomme un dict
`meta` optionnel `{ "elevation": int, "elevation_max": int, "elevation_min": int, "effects": [names],
"steppable": {"is_enemy": bool, "is_decoy": bool} | None }` — ABSENT ⇒ la feuille rend 0 (dégradation
fidèle : ces termes SONT 0 sans la donnée). Le plumbing (enrichir la donnée tuile) est séparé.

Statut de portage (incrémental, agreement-driven) :
- PORTÉES (formule RE'd) : Elevation(8), SteppableUnit(19), TileEffects(9, partiel).
- STUB=0 (situationnel, à RE/plomber) : les 26 autres — listées dans `TILE_LEAVES` avec leur catégorie.
cf. docs/rl/playbook-engine.md §13.8/13.9.
"""
from __future__ import annotations

from ..weights import Weights

# UtilityType des 29 feuilles de Tile(7) (ordre runtime). name = catégorie BC `Default.<name>`.
TILE_LEAF_IDS = [8, 13, 9, 10, 11, 12, 15, 19, 24, 2, 4, 3, 20, 21, 22, 14, 26, 57, 60, 58, 25, 23,
                 61, 62, 64, 28, 29, 30, 31]


def elevation(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """Elevation(8) FIDÈLE (`ElevationUtility.<d__8>.MoveNext` @1811019a0) :
        u = Multiplier × elev  (+ HighestElevation si elev == max parmi tuiles pertinentes)
                               (+ LowestElevation  si elev == min)
    BC : Multiplier=10, HighestElevation=10, LowestElevation=-5. `meta` requis (élévation tuile + max/min)."""
    if not meta or "elevation" not in meta:
        return 0.0
    elev = meta["elevation"]
    u = wt.sub("Elevation", "Multiplier") * elev
    if meta.get("elevation_max") is not None and elev == meta["elevation_max"]:
        u += wt.sub("Elevation", "HighestElevation")
    if meta.get("elevation_min") is not None and elev == meta["elevation_min"]:
        u += wt.sub("Elevation", "LowestElevation")
    return u


def steppable_unit(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """SteppableUnit(19) FIDÈLE (`SteppableUnitUtility.<d__10>.MoveNext` @1810f9850) : si une unité
    STEPPABLE (summon/decoy) est sur la tuile → poids selon ami/ennemi × summon/decoy.
    BC : EnemySteppableUnit=50, FriendlySteppableUnit=-50, FriendlyDecoy=-50, EnemyDecoy=1.
    (Les 2 abilities triggered 0x4d/0x72 = cas spéciaux non portés ; rares.) `meta.steppable` requis."""
    st = (meta or {}).get("steppable")
    if not st:
        return 0.0
    is_enemy = st.get("is_enemy")
    if st.get("is_decoy"):
        return wt.sub("SteppableUnit", "EnemyDecoy" if is_enemy else "FriendlyDecoy")
    return wt.sub("SteppableUnit", "EnemySteppableUnit" if is_enemy else "FriendlySteppableUnit")


def tile_effects(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """TileEffects(9) PARTIEL (`TileEffectsUtility.<d__1>.MoveNext` @1810fbe50) : somme des poids BC
    `Default.TileEffects.<EffectName>` pour chaque effet de statut présent SUR la tuile (le natif
    multiplie les status-effects par un facteur de durée ; non porté → poids brut). `meta.effects` requis.
    BC TileEffects : Shrub_BonusDefense 25, FirstAidHeal 20, Thorns_DefenseReduction -25, SpiderWeb -25,
    Fire -25, Ice -25, … (cf. wt.category('TileEffects'))."""
    effs = (meta or {}).get("effects") or []
    if not effs:
        return 0.0
    cat = wt.category("TileEffects")
    return float(sum(cat.get(e, 0) for e in effs if isinstance(cat.get(e), (int, float))))


# Registry : UtilityType -> (name, fn|None). fn=None => STUB situationnel (=0, à RE/plomber).
# Les feuilles trait-gated rendent 0 tant que la condition (trait/effet/terrain) n'est pas plombée.
TILE_LEAVES: dict[int, tuple] = {
    8:  ("Elevation", elevation),
    19: ("SteppableUnit", steppable_unit),
    9:  ("TileEffects", tile_effects),
    # --- STUBS (situationnels, =0 sur bataille basique ; portage incrémental) ---
    13: ("TemporaryTile", None), 10: ("UnitEffectsAdjacent", None),
    11: ("UnitEffectsSurrounding", None), 12: ("UnitEffectsRanged", None),
    15: ("RangedAdjacentEnemy", None),       # =0 dans le profil Default (BC HasAdjacentEnemy=0)
    24: ("CapturePoint", None), 2: ("TriggeredAbilities", None),
    4: ("TriggeredAbilitiesNonOwner", None), 3: ("UnitSpecificBehaviours", None),
    20: ("KustomForceField", None), 21: ("DefenderOfTheGreaterGood", None),
    22: ("SaviorProtocols", None), 14: ("TilePendingBlockableSummon", None),
    26: ("PowerUp", None), 57: ("DoctrinaImperatives_AttractMechanicals", None),
    60: ("Phantasm_AvoidFriendlyPhantasm", None), 58: ("EchoesFromTheWarp_FriendliesAvoidGhost", None),
    25: ("Contaminated", None), 23: ("MoltenForm", None),
    61: ("BioMinefield_MoveTowardsTarget", None), 62: ("MasterOfTheTutelaries_MoveTowardsTarget", None),
    64: ("DecoysAndMisdirection_AttractToDecoys", None), 28: ("DespoiledGround", None),
    29: ("SummonDislikeDoorOpening", None), 30: ("HeroLikeDoorOpening", None),
    31: ("EnvEndBombardment", None),
}


def tile_composite(tile, meta: dict | None, ctx: dict, wt: Weights) -> float:
    """Composite Tile(7) = somme des 29 feuilles portées (les stubs rendent 0). `meta` = metadata
    par tuile (élévation/effets/steppable) ; absent ⇒ seules les feuilles sans donnée contribuent (≈0)."""
    m = meta or {}
    total = 0.0
    for uid in TILE_LEAF_IDS:
        fn = TILE_LEAVES.get(uid, (None, None))[1]
        if fn is not None:
            total += fn(tile, m, ctx, wt)
    return total
