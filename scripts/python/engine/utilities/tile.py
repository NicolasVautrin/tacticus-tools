"""Tile(7) composite — les 29 leaf-utilities de tuile, UNE CLASSE `*Utility` par feuille (nom NATIF).

`Tile(7)` (composite scoré par `Weight[Tile=7]` dans `CalculateUtilityFromTilePrediction`) = SOMME de
29 feuilles. La plupart sont SITUATIONNELLES (terrain spécial / trait de l'unité / effet présent) → =0
sur une bataille basique plate. Chaque feuille = une CLASSE `IdunBattle.AI.Utilities.*Utility` dont
`evaluate(self, tile, meta, ctx, wt)` PORTE le corps de son `*Utility.<EvaluateMovementInSteps>d__N.MoveNext`
(ghidra gqfc5mff6c) + poids BC `Utilities.Default`. Le composite Tile(7) = INSTANCE `ComposedUtility`
(Tile est un UtilityType, pas une classe). `tile_composite` = wrapper mince pour les appelants existants.

⚠ DÉPENDANCE DONNÉE : beaucoup de feuilles consomment une METADATA PAR TUILE / PAR UNITÉ que
`aiMovableTiles` n'expose pas (col/row seulement). Chaque feuille lit deux dicts optionnels et rend 0
quand la donnée manque — c'est EXACTEMENT la dégradation native (la condition de gate ne tient pas) :

`meta` (PAR TUILE candidate) — clés consommées :
  elevation, elevation_max, elevation_min : int            (Elevation 8 — via tileMeta) [ACTIF]
  steppable : {is_enemy, is_decoy} | None                  (SteppableUnit 19)
  effects : [effect_name]                                  (TileEffects 9 — noms d'effets SUR la tuile)
  is_temporary : bool                                      (TemporaryTile 13 — via tileMeta) [ACTIF]
  is_territory : bool                                      (CapturePoint 24 — via tileMeta.isTerritory)
  occupant_is_powerup : bool                               (PowerUp 26)
  tile_effect_type_ids : [int]                             (Contaminated 1244 / MoltenForm 5,10 / DespoiledGround 1476)
  effect_target_ids : [int]                                (EnvEndBombardment 1359/1360)
  pending_summons : [{type_id:int, owner_is_enemy:bool}]   (TilePendingBlockableSummon 1094)
  door : {linked:bool, closed:bool}                        (SummonDislikeDoorOpening 29 / HeroLikeDoorOpening 30)
  hero_door_nearest_cost : int                             (HeroLikeDoorOpening 30 branche B)
  phantasm_friendly_adjacent / ghost_friendly_adjacent : bool      (Phantasm 60 / Echoes 58)
  attract_mechanicals_neighbor : bool                      (DoctrinaImperatives 57)
  decoy_gate : bool, decoy_friend_count : int              (DecoysAndMisdirection 64)
  ability_friend_counts : {ability_id:int -> count}        (KustomForceField 1102 / Defender 1155 / Savior 1120)
  movetowards_hexdist : {ability_id:int -> hexdist}        (BioMinefield 1315 / MasterOfTheTutelaries 1096)
  neighbor_effect_names : {adjacent|surrounding1|ranged2 -> [effect_name]}   (UnitEffects 10/11/12)

`ctx` (PAR UNITÉ/DÉCISION, constant sur toutes les tuiles d'une décision) — clés consommées :
  unit_traits : [int]                 (2 summon, 5, 13, 16 hero, 26, 1006, 1019, 2026 …)
  unit_triggered_abilities : [int]    (1120 SaviorProtocols, 1221 MoltenForm …)
  unit_faction : int                  (9 T'au-style, 15 GSC-style …)
  unit_has_ranged_weapon : bool ; unit_is_ai : bool ; player_door_mode : int ; contaminated_excluded : bool

Statut de portage (cf. docs/rl/playbook-engine.md §13.8/§13.14) :
- ACTIVES (metadata dispo) : Elevation(8), SteppableUnit(19), TileEffects(9, partiel), TemporaryTile(13).
- PORTÉES FIDÈLE mais DORMANTES (gate sur metadata non encore plombée → 0) : les 22 autres `*Utility`.
- NON portées comme simples leaves : RangedAdjacentEnemy(15)=0 dans Default ; TriggeredAbilities(2)/
  NonOwner(4)/UnitSpecificBehaviours(3) = dispatchers vers le moteur Playbook par-ability (séparé).
"""
from __future__ import annotations

from ..weights import Weights
from .base import BaseUtility, ComposedUtility
from .utility_type import UtilityType
from ..entities.effect_type import EffectType
from ..entities.active_ability_type import ActiveAbilityType

# UtilityType des 29 feuilles de Tile(7) (ordre runtime). name = catégorie BC `Default.<name>`.
# #158 : ids bruts -> membres `UtilityType` nommés (l'ordre est la sequence runtime native ; value-preserving,
# IntEnum -> clés `TILE_LEAVES[i]` inchangées).
TILE_LEAF_IDS = [
    UtilityType.Elevation, UtilityType.TemporaryTile, UtilityType.TileEffects,           # 8, 13, 9
    UtilityType.UnitEffectsAdjacent, UtilityType.UnitEffectsSurrounding, UtilityType.UnitEffectsRanged,  # 10, 11, 12
    UtilityType.RangedAdjacentEnemy, UtilityType.SteppableUnit, UtilityType.CapturePoint,  # 15, 19, 24
    UtilityType.TriggeredAbilities, UtilityType.TriggeredAbilitiesNonOwner, UtilityType.UnitSpecificBehaviours,  # 2, 4, 3
    UtilityType.KustomForceField, UtilityType.DefenderOfTheGreaterGood, UtilityType.SaviorProtocols,  # 20, 21, 22
    UtilityType.TilePendingBlockableSummon, UtilityType.PowerUp, UtilityType.DoctrinaImperatives_AttractMechanicals,  # 14, 26, 57
    UtilityType.Phantasm_AvoidFriendlyPhantasm, UtilityType.EchoesFromTheWarp_FriendliesAvoidGhost, UtilityType.Contaminated,  # 60, 58, 25
    UtilityType.MoltenForm, UtilityType.BioMinefield_MoveTowardsTarget, UtilityType.MasterOfTheTutelaries_MoveTowardsTarget,  # 23, 61, 62
    UtilityType.DecoysAndMisdirection_AttractToDecoys, UtilityType.DespoiledGround, UtilityType.SummonDislikeDoorOpening,  # 64, 28, 29
    UtilityType.HeroLikeDoorOpening, UtilityType.EnvEndBombardment,                       # 30, 31
]

# Pénalité constante (Fix64) appliquée aux tuiles temporaires — RE'd, PAS un poids BC.
TEMPORARY_TILE_PENALTY = -10000.0


# ── Helpers PARTAGES (petites primitives réutilisées par plusieurs feuilles) ─────────────────────────
def _has(ctx: dict, key: str, val: int) -> bool:
    """True si `ctx[key]` (itérable d'ids) contient `val`."""
    s = (ctx or {}).get(key)
    return bool(s) and val in set(s)


def _eff_ids(meta: dict, key: str) -> set:
    return set((meta or {}).get(key) or ())


def _ability_count(meta: dict, ability_id: int) -> int:
    """count d'amis (dans le rayon propre à la leaf) ayant l'ability `ability_id`."""
    counts = (meta or {}).get("ability_friend_counts") or {}
    return int(counts.get(ability_id) or counts.get(str(ability_id)) or 0)


# ── Classes `IdunBattle.AI.Utilities.*Utility` (une par feuille ; corps DANS la méthode) ─────────────
class ElevationUtility(BaseUtility):
    """`ElevationUtility` (@1810efa20 ; UtilityType.Elevation=8) ; `<d__8>.MoveNext @1811019a0` :
        u = Multiplier × elev  (+ HighestElevation si elev == max) (+ LowestElevation si elev == min)
    BC : Multiplier=10, HighestElevation=10, LowestElevation=-5. `meta` requis (élévation tuile + max/min)."""
    UTILITY_TYPE = int(UtilityType.Elevation)  # 8

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not meta or "elevation" not in meta:
            return 0.0
        elev = meta["elevation"]
        u = wt.sub("Elevation", "Multiplier") * elev
        if meta.get("elevation_max") is not None and elev == meta["elevation_max"]:
            u += wt.sub("Elevation", "HighestElevation")
        if meta.get("elevation_min") is not None and elev == meta["elevation_min"]:
            u += wt.sub("Elevation", "LowestElevation")
        return u


class SteppableUnitUtility(BaseUtility):
    """`SteppableUnitUtility` (@1810f1d50 ; UtilityType.SteppableUnit=19) ; `<d__10>.MoveNext @1810f9850` :
    si une unité STEPPABLE (summon/decoy) est sur la tuile → poids ami/ennemi × summon/decoy.
    BC : EnemySteppableUnit=50, FriendlySteppableUnit=-50, FriendlyDecoy=-50, EnemyDecoy=1. `meta.steppable`."""
    UTILITY_TYPE = int(UtilityType.SteppableUnit)  # 19

    def evaluate(self, tile, meta, ctx, wt) -> float:
        st = (meta or {}).get("steppable")
        if not st:
            return 0.0
        is_enemy = st.get("is_enemy")
        if st.get("is_decoy"):
            return wt.sub("SteppableUnit", "EnemyDecoy" if is_enemy else "FriendlyDecoy")
        return wt.sub("SteppableUnit", "EnemySteppableUnit" if is_enemy else "FriendlySteppableUnit")


class TileEffectsUtility(BaseUtility):
    """`TileEffectsUtility` (@1810f2980 ; UtilityType.TileEffects=9) ; `<d__1>.MoveNext @1810fbe50` :
    Σ des poids BC `Default.TileEffects.<EffectName>` pour chaque effet présent SUR la tuile (le natif
    multiplie les status-effects par un facteur de durée ; non porté → poids brut). `meta.effects` requis."""
    UTILITY_TYPE = int(UtilityType.TileEffects)  # 9

    def evaluate(self, tile, meta, ctx, wt) -> float:
        effs = (meta or {}).get("effects") or []
        if not effs:
            return 0.0
        cat = wt.category("TileEffects")
        return float(sum(cat.get(e, 0) for e in effs if isinstance(cat.get(e), (int, float))))


class TemporaryTileUtility(BaseUtility):
    """`TemporaryTileUtility` (@1810f2180 ; UtilityType.TemporaryTile=13) ; `<d__1>.MoveNext @1810faed0` :
    u = 0 ; si la tuile candidate est TEMPORAIRE → u -= Fix64(10000) (CONSTANTE, pas un poids BC ; le natif
    lit `tileData+0x2c` IsTemporary). L'IA évite fortement les tuiles temporaires. `meta.is_temporary`."""
    UTILITY_TYPE = int(UtilityType.TemporaryTile)  # 13

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if (meta or {}).get("is_temporary"):
            return TEMPORARY_TILE_PENALTY
        return 0.0


class AUnitEffectsUtility(BaseUtility):
    """`AUnitEffectsUtility` (@1810ee350, TypeDefIndex 12150) — base ABSTRAITE ; `MoveNext @1810fb260` = le
    corps PARTAGE : Σ sur les amis du voisinage `_ZONE`, Σ sur leurs effets, poids[EffectType.ToString()]
    dans la catégorie BC `_CAT`. Voisinages : Adjacent/Surrounding=R1, Ranged=R2 (minus self, amis). Les 3
    sous-classes CONCRETES (12151/12152/12153) ne different QUE par `_CAT`/`_ZONE`. `meta.neighbor_effect_names`."""
    _CAT: str = ""
    _ZONE: str = ""

    def evaluate(self, tile, meta, ctx, wt) -> float:
        names = ((meta or {}).get("neighbor_effect_names") or {}).get(self._ZONE) or []
        if not names:
            return 0.0
        c = wt.category(self._CAT)
        return float(sum(c.get(n, 0) for n in names if isinstance(c.get(n), (int, float))))


class UnitEffectsAdjacentUtility(AUnitEffectsUtility):
    """`UnitEffectsAdjacentUtility` (TypeDefIndex 12151 ; UtilityType.UnitEffectsAdjacent=10)."""
    UTILITY_TYPE = int(UtilityType.UnitEffectsAdjacent)  # 10
    _CAT = "UnitEffectsAdjacent"
    _ZONE = "adjacent"


class UnitEffectsSurroundingUtility(AUnitEffectsUtility):
    """`UnitEffectsSurroundingUtility` (TypeDefIndex 12152 ; UtilityType.UnitEffectsSurrounding=11)."""
    UTILITY_TYPE = int(UtilityType.UnitEffectsSurrounding)  # 11
    _CAT = "UnitEffectsSurrounding"
    _ZONE = "surrounding1"


class UnitEffectsRangedUtility(AUnitEffectsUtility):
    """`UnitEffectsRangedUtility` (TypeDefIndex 12153 ; UtilityType.UnitEffectsRanged=12)."""
    UTILITY_TYPE = int(UtilityType.UnitEffectsRanged)  # 12
    _CAT = "UnitEffectsRanged"
    _ZONE = "ranged2"


class CapturePointTileUtility(BaseUtility):
    """`CapturePointTileUtility` (@1810ee7f0 ; UtilityType.CapturePoint=24) ; @1811000a0 : sur tuile
    TERRITOIRE (flag tile+0x2e = HasTrait(2 summon)||HasTrait(13)) → flag(summon) →
    summons_dislike_capture_points(-300) ; sinon heroes_on_capture_points(+300). `meta.is_territory` + `ctx.unit_traits`."""
    UTILITY_TYPE = int(UtilityType.CapturePoint)  # 24

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not (meta or {}).get("is_territory"):
            return 0.0
        flag = _has(ctx, "unit_traits", 2) or _has(ctx, "unit_traits", 13)
        key = "summons_dislike_capture_points" if flag else "heroes_on_capture_points"
        return wt.sub("CapturePoint", key)


class PowerUpTileUtility(BaseUtility):
    """`PowerUpTileUtility` (@1810f15b0 ; UtilityType.PowerUp=26) ; @1810fd130 : -300 si l'occupant de la
    tuile EstPowerUp ET flag(trait 2||13). `meta.occupant_is_powerup` + `ctx.unit_traits`."""
    UTILITY_TYPE = int(UtilityType.PowerUp)  # 26

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not (meta or {}).get("occupant_is_powerup"):
            return 0.0
        if not (_has(ctx, "unit_traits", 2) or _has(ctx, "unit_traits", 13)):
            return 0.0
        return wt.sub("PowerUp", "summons_dislike_tiles_with_powerups")


class ContaminatedUtility(BaseUtility):
    """`ContaminatedUtility` (@1810ee930 ; UtilityType.Contaminated=25) ; @181100670 : -25 si la tuile porte
    un effet type 1244 (0x4dc) ET l'unité n'est pas exclue. `meta.tile_effect_type_ids` + `ctx.contaminated_excluded`."""
    UTILITY_TYPE = int(UtilityType.Contaminated)  # 25

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if 1244 not in _eff_ids(meta, "tile_effect_type_ids"):
            return 0.0
        if (ctx or {}).get("contaminated_excluded"):
            return 0.0
        return wt.sub("Contaminated", "AffectedUnit")


class MoltenForm_TilesUtility(BaseUtility):
    """`MoltenForm_TilesUtility` (@1810f08d0 ; UtilityType.MoltenForm=23) ; @1810fd300 : si l'unité a la
    triggered ability 1221 (0x4c5) → +25 si tuile effet type 5 (ResistFireTiles) ; -25 si type 10
    (AvoidHealingTiles). `ctx.unit_triggered_abilities` + `meta.tile_effect_type_ids`."""
    UTILITY_TYPE = int(UtilityType.MoltenForm)  # 23

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not _has(ctx, "unit_triggered_abilities", 1221):
            return 0.0
        ids = _eff_ids(meta, "tile_effect_type_ids")
        u = 0.0
        if 5 in ids:
            u += wt.sub("MoltenForm", "MoltenForm_ResistFireTiles")
        if 10 in ids:
            u += wt.sub("MoltenForm", "MoltenForm_AvoidHealingTiles")
        return u


class TilePendingBlockableSummonUtility(BaseUtility):
    """`TilePendingBlockableSummonUtility` (@1810f2d70 ; UtilityType.TilePendingBlockableSummon=14) ; @181100250 :
    Σ sur les summons en attente de type 1094 (0x446) sur la tuile : +25 si owner ENNEMI, -25 si AMI.
    `meta.pending_summons=[{type_id,owner_is_enemy}]`."""
    UTILITY_TYPE = int(UtilityType.TilePendingBlockableSummon)  # 14

    def evaluate(self, tile, meta, ctx, wt) -> float:
        ps = (meta or {}).get("pending_summons") or []
        we = wt.sub("TilePendingBlockableSummon", "EnemySummon")
        wf = wt.sub("TilePendingBlockableSummon", "FriendlySummon")
        return float(sum((we if e.get("owner_is_enemy") else wf)
                         for e in ps if e.get("type_id") == 1094))


class EnvEndBombardmentUtility(BaseUtility):
    """`EnvEndBombardmentUtility` (@1810efb60 ; UtilityType.EnvEndBombardment=31) ; @1810fe4c0 : tuile ciblée
    par l'effet 1359 (0x54f) → -30 ; sinon par 1360 (0x550) → -60 (×2). `meta.effect_target_ids`."""
    UTILITY_TYPE = int(UtilityType.EnvEndBombardment)  # 31

    def evaluate(self, tile, meta, ctx, wt) -> float:
        ids = _eff_ids(meta, "effect_target_ids")
        w = wt.sub("EnvEndBombardment", "EnvEndBombardment_TileToAvoid")
        if 1359 in ids:
            return w
        if 1360 in ids:
            return w * 2
        return 0.0


class DespoiledGroundUtility(BaseUtility):
    """`DespoiledGroundUtility` (@1810ef280 ; UtilityType.DespoiledGround=28) ; @181100ac0 : si tuile
    tile-effect type 1476 (0x5c4) → trait 2026 (Chaos) → ChaosAffectedUnit(-5) ; trait 26 ou 1006
    (Imperial/Xenos) → ImperialAndXenosAffectedUnit(-25). `meta.tile_effect_type_ids` + `ctx.unit_traits`."""
    UTILITY_TYPE = int(UtilityType.DespoiledGround)  # 28

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if 1476 not in _eff_ids(meta, "tile_effect_type_ids"):
            return 0.0
        if _has(ctx, "unit_traits", 2026):
            return wt.sub("DespoiledGround", "ChaosAffectedUnit")
        if _has(ctx, "unit_traits", 26) or _has(ctx, "unit_traits", 1006):
            return wt.sub("DespoiledGround", "ImperialAndXenosAffectedUnit")
        return 0.0


class SummonDislikeDoorOpeningUtility(BaseUtility):
    """`SummonDislikeDoorOpeningUtility` (@1810f2050 ; UtilityType.SummonDislikeDoorOpening=29) ; @1810fce30 :
    -50 si l'unité est "affected" (AI-controlled OU human+trait 2) ET la tuile est une PORTE FERMÉE.
    `meta.door={linked,closed}` + `ctx.unit_is_ai/unit_traits`."""
    UTILITY_TYPE = int(UtilityType.SummonDislikeDoorOpening)  # 29

    def evaluate(self, tile, meta, ctx, wt) -> float:
        door = (meta or {}).get("door") or {}
        if not (door.get("linked") and door.get("closed")):
            return 0.0
        affected = bool((ctx or {}).get("unit_is_ai")) or _has(ctx, "unit_traits", 2)
        if not affected:
            return 0.0
        return wt.sub("SummonDislikeDoorOpening", "Dislike")


class HeroDoorOpeningUtility(BaseUtility):
    """`HeroDoorOpeningUtility` (@1810efdc0 ; UtilityType.HeroLikeDoorOpening=30) ; @1810fe100 : UNIQUEMENT
    unité hero (trait 16). PAS de poids BC (constantes). branche A (player flag==0) : -50 si la tuile est
    une porte fermée. branche B (flag!=0) : (10 - cost)*10, cost = min coût CHEMIN vers la porte fermée la
    plus proche. `ctx.player_door_mode` + `meta.door` + `meta.hero_door_nearest_cost`."""
    UTILITY_TYPE = int(UtilityType.HeroLikeDoorOpening)  # 30

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not _has(ctx, "unit_traits", 16):
            return 0.0
        if (ctx or {}).get("player_door_mode", 0) == 0:
            door = (meta or {}).get("door") or {}
            return -50.0 if (door.get("linked") and door.get("closed")) else 0.0
        cost = (meta or {}).get("hero_door_nearest_cost")
        if cost is None:
            return 0.0
        return (10 - cost) * 10.0


class Phantasm_AvoidFriendlyPhantasmUtility(BaseUtility):
    """`Phantasm_AvoidFriendlyPhantasmUtility` (@1810f1470 ; UtilityType.Phantasm_AvoidFriendlyPhantasm=60) ;
    @1810fb020 : -40 si la tuile porte l'effet Phantasm 1279 (0x4ff) ET un phantasme AMI est adjacent.
    `meta.phantasm_friendly_adjacent`."""
    UTILITY_TYPE = int(UtilityType.Phantasm_AvoidFriendlyPhantasm)  # 60

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not (meta or {}).get("phantasm_friendly_adjacent"):
            return 0.0
        return wt.sub("Phantasm_AvoidFriendlyPhantasm", "Phantasm_AvoidFriendlyPhantasm")


class EchoesFromTheWarp_FriendliesAvoidGhostUtility(BaseUtility):
    """`EchoesFromTheWarp_FriendliesAvoidGhostUtility` (@1810cfa30 ; UtilityType.=58) ; @1810e3750 : +10 si
    la tuile POSSÈDE (owner) l'effet ghost 1284 (0x504) ET le ghost ami est adjacent. `meta.ghost_friendly_adjacent`."""
    UTILITY_TYPE = int(UtilityType.EchoesFromTheWarp_FriendliesAvoidGhost)  # 58

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not (meta or {}).get("ghost_friendly_adjacent"):
            return 0.0
        return wt.sub("EchoesFromTheWarp_FriendliesAvoidGhost", "GhostTile")


class AttractMechanicalsUtility(BaseUtility):
    """`AttractMechanicalsUtility` (@1810ccea0 ; UtilityType.DoctrinaImperatives_AttractMechanicals=57) ;
    @1810e3af0 : +10 si l'unité a le trait 5 ET un voisin (autour de la tuile) a l'active ability 1118
    (0x45e). `ctx.unit_traits` + `meta.attract_mechanicals_neighbor`."""
    UTILITY_TYPE = int(UtilityType.DoctrinaImperatives_AttractMechanicals)  # 57

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not _has(ctx, "unit_traits", 5):
            return 0.0
        if not (meta or {}).get("attract_mechanicals_neighbor"):
            return 0.0
        return wt.sub("DoctrinaImperatives_AttractMechanicals", "Marshal_AttractMechanicals")


class AttractToDecoysUtility(BaseUtility):
    """`AttractToDecoysUtility` (@1810ccf60 ; UtilityType.DecoysAndMisdirection_AttractToDecoys=64) ;
    @1810e2ef0 : +75 PAR ami avec triggered ability 1304 (0x518), gate : unité faction 15 ET tuile avec une
    unité steppable (trait 27) NON ennemie. `ctx.unit_faction` + `meta.decoy_gate` + `meta.decoy_friend_count`."""
    UTILITY_TYPE = int(UtilityType.DecoysAndMisdirection_AttractToDecoys)  # 64

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if (ctx or {}).get("unit_faction") != 15:
            return 0.0
        if not (meta or {}).get("decoy_gate"):
            return 0.0
        n = (meta or {}).get("decoy_friend_count") or 0
        return n * wt.sub("DecoysAndMisdirection_AttractToDecoys",
                          "DecoysAndMisdirection_FriendlyGSCLikeDecoys")


class KustomForceFieldUtility(BaseUtility):
    """`KustomForceFieldUtility` (@1810cffe0 ; UtilityType.KustomForceField=20) ; base ATriggeredAbilityUtility.d__3
    @1810e4160 : +20 × count(amis ADJACENTS R1 avec triggered ability 1102). `meta.ability_friend_counts[1102]`."""
    UTILITY_TYPE = int(UtilityType.KustomForceField)  # 20

    def evaluate(self, tile, meta, ctx, wt) -> float:
        return _ability_count(meta, 1102) * wt.sub("KustomForceField", "AdjacentFriendly")


class DefenderOfTheGreaterGoodUtility(BaseUtility):
    """`DefenderOfTheGreaterGoodUtility` (@1810cf570 ; UtilityType.DefenderOfTheGreaterGood=21) ; @1810e4160 :
    +25 × count(amis R1, ou R2 si faction 9, avec ability 1155). Gate : arme à distance.
    `ctx.unit_has_ranged_weapon` + `meta.ability_friend_counts[1155]`."""
    UTILITY_TYPE = int(UtilityType.DefenderOfTheGreaterGood)  # 21

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not (ctx or {}).get("unit_has_ranged_weapon"):
            return 0.0
        return _ability_count(meta, 1155) * wt.sub("DefenderOfTheGreaterGood", "PerUnitWithAbilityInRange")


class SaviorProtocolsUtility(BaseUtility):
    """`SaviorProtocolsUtility` (@1810e0b90 ; UtilityType.SaviorProtocols=22) ; @1810e4160 : +20 × count(amis
    ADJACENTS R1 avec ability 1120). Gate : faction 9 ET n'a pas l'ability 1120. `ctx.unit_faction/
    unit_triggered_abilities` + `meta.ability_friend_counts[1120]`."""
    UTILITY_TYPE = int(UtilityType.SaviorProtocols)  # 22

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if (ctx or {}).get("unit_faction") != 9 or _has(ctx, "unit_triggered_abilities", 1120):
            return 0.0
        return _ability_count(meta, 1120) * wt.sub("SaviorProtocols", "PerUnitWithAbilityInRange")


class MoveTowardsUnitUtility(BaseUtility):
    """`MoveTowardsUnitUtility` (@1810f0ff0 ; base) ; `MoveNext @1810f9b40` : score = poids("PerTileDistance")
    × hexdist(candidate, cible) ; cible = unité ayant l'ability/effet `_ABILITY_ID`. distance = HEX (cube ;
    fournie par `meta.movetowards_hexdist[_ABILITY_ID]`). `_TRAIT_GATE` (None = pas de gate). Corps PARTAGE
    par les 2 sous-classes (BioMinefield, MasterOfTheTutelaries) qui parametrent `_CAT`/`_ABILITY_ID`/`_TRAIT_GATE`."""
    _CAT: str = ""
    _ABILITY_ID: int = -1
    _TRAIT_GATE: "set | None" = None

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if self._TRAIT_GATE is not None:
            if not (set((ctx or {}).get("unit_traits") or ()) & self._TRAIT_GATE):
                return 0.0
        dd = (meta or {}).get("movetowards_hexdist") or {}
        d = dd.get(self._ABILITY_ID)
        if d is None:
            d = dd.get(str(self._ABILITY_ID))
        if d is None:
            return 0.0
        return d * wt.sub(self._CAT, "PerTileDistance")


class BioMinefield_MoveTowardsTargetUtility(MoveTowardsUnitUtility):
    """`BioMinefield_MoveTowardsTargetUtility` (@1810ee5e0 ; UtilityType.=61) : -100 × hexdist(candidate,
    cible ability/effet 1315). Pas de gate trait."""
    UTILITY_TYPE = int(UtilityType.BioMinefield_MoveTowardsTarget)  # 61
    _CAT = "BioMinefield_MoveTowardsTarget"
    _ABILITY_ID = int(EffectType.BioMinefield_Target)  # 1315 (effet marqueur de cible ; #158, absent d'ActiveAbilityType)
    _TRAIT_GATE = None


class MasterOfTheTutelaries_MoveTowardsTargetUtility(MoveTowardsUnitUtility):
    """`MasterOfTheTutelaries_MoveTowardsTargetUtility` (@1810f0130 ; UtilityType.=62) : -20 × hexdist(candidate,
    cible 1096). Gate trait : l'unité a 2026 ou 1019."""
    UTILITY_TYPE = int(UtilityType.MasterOfTheTutelaries_MoveTowardsTarget)  # 62
    _CAT = "MasterOfTheTutelaries_MoveTowardsTarget"
    _ABILITY_ID = int(ActiveAbilityType.MasterOfTheTutelaries)  # 1096 (#158 : nom classe matche Active, PAS EffectType.KustomForceField/Triggered.SoulHunger)
    _TRAIT_GATE = {2026, 1019}


# ── Registry : UtilityType -> (name, instance|None). None => délégué/non-portable comme simple leaf. ──
TILE_LEAVES: dict[int, tuple] = {
    # --- ACTIVES (metadata dispo aujourd'hui) ---
    8:  ("Elevation", ElevationUtility()),
    19: ("SteppableUnit", SteppableUnitUtility()),
    9:  ("TileEffects", TileEffectsUtility()),
    13: ("TemporaryTile", TemporaryTileUtility()),   # RÉELLE (meta.is_temporary via tileMeta)
    # --- PORTÉES FIDÈLE, DORMANTES (gate sur metadata par-tuile/unité non encore plombée → 0) ---
    10: ("UnitEffectsAdjacent", UnitEffectsAdjacentUtility()),
    11: ("UnitEffectsSurrounding", UnitEffectsSurroundingUtility()),
    12: ("UnitEffectsRanged", UnitEffectsRangedUtility()),
    24: ("CapturePoint", CapturePointTileUtility()),
    26: ("PowerUp", PowerUpTileUtility()),
    25: ("Contaminated", ContaminatedUtility()),
    23: ("MoltenForm", MoltenForm_TilesUtility()),
    14: ("TilePendingBlockableSummon", TilePendingBlockableSummonUtility()),
    31: ("EnvEndBombardment", EnvEndBombardmentUtility()),
    28: ("DespoiledGround", DespoiledGroundUtility()),
    29: ("SummonDislikeDoorOpening", SummonDislikeDoorOpeningUtility()),
    30: ("HeroLikeDoorOpening", HeroDoorOpeningUtility()),
    60: ("Phantasm_AvoidFriendlyPhantasm", Phantasm_AvoidFriendlyPhantasmUtility()),
    58: ("EchoesFromTheWarp_FriendliesAvoidGhost", EchoesFromTheWarp_FriendliesAvoidGhostUtility()),
    57: ("DoctrinaImperatives_AttractMechanicals", AttractMechanicalsUtility()),
    64: ("DecoysAndMisdirection_AttractToDecoys", AttractToDecoysUtility()),
    20: ("KustomForceField", KustomForceFieldUtility()),
    21: ("DefenderOfTheGreaterGood", DefenderOfTheGreaterGoodUtility()),
    22: ("SaviorProtocols", SaviorProtocolsUtility()),
    61: ("BioMinefield_MoveTowardsTarget", BioMinefield_MoveTowardsTargetUtility()),
    62: ("MasterOfTheTutelaries_MoveTowardsTarget", MasterOfTheTutelaries_MoveTowardsTargetUtility()),
    # --- NON portées comme simples leaves ---
    15: ("RangedAdjacentEnemy", None),       # =0 dans le profil Default (BC HasAdjacentEnemy absent)
    # 2/3/4 = dispatchers vers le moteur Playbook PAR-ABILITY (LoadPlaybook/LoadPlaybookNonOwner ;
    # somme des playbooks par unit/ability/behaviour) — workstream Playbook séparé, pas un simple
    # terme de tuile. Restent 0 ici (cf. §13.14 + project_playbook_engine).
    2:  ("TriggeredAbilities", None),
    4:  ("TriggeredAbilitiesNonOwner", None),
    3:  ("UnitSpecificBehaviours", None),
}


# Composite Tile(7) = INSTANCE `ComposedUtility` (PAS de classe `TileUtility` : Tile est un UtilityType,
# le composite est un ComposedUtility enregistre a 7). `CalculateUtilityFromTilePrediction @181408740`
# = Σ feuilles (ordre runtime TILE_LEAF_IDS, feuilles non portees ecartees). Carte plate ≈ 0.
TILE_UTILITY = ComposedUtility(
    [TILE_LEAVES[i][1] for i in TILE_LEAF_IDS if TILE_LEAVES.get(i, (None, None))[1] is not None],
    utility_type=UtilityType.Tile)


def tile_composite(tile, meta: dict | None, ctx: dict, wt: Weights) -> float:
    """Composite Tile(7) = `TILE_UTILITY.evaluate` (Σ des feuilles portées). Wrapper mince pour les
    appelants existants (`engine.playbook.base.tile_utility`, `engine.move`). `meta` absent ⇒ ≈0."""
    return TILE_UTILITY.evaluate(tile, meta or {}, ctx, wt)
