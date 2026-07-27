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
  elevation : int ; elevation_max, elevation_min : int     (Elevation 8 — tuile via tileMeta ; max/min sur le
                                                            BOARD ENTIER, cf. LoadRelevantTileElevations) [ACTIF]
  steppable : {is_enemy, is_decoy} | None                  (SteppableUnit 19)
  effects : [effect_name]                                  (TileEffects 9 — effets DYNAMIQUES (Loop1) + covers
                                                            HÉBERGÉS par le terrain (Loop2 : DryBush->LightCover)) [ACTIF]
  is_temporary : bool                                      (TemporaryTile 13 — via tileMeta) [ACTIF]
  is_territory : bool                                      (CapturePoint 24 — via tileMeta.isTerritory) [ACTIF #175,
                                                            mais 0 tuile territoire hors ruleset Territories]
  occupant_is_powerup : bool                               (PowerUp 26)
  tile_effect_type_ids : [int]                             (Contaminated 1244 / MoltenForm 5,10 / DespoiledGround 1476)
                                                           [ACTIF #175 — via tileMeta.effects[].effectType]
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
  unit_traits : [int]                 (2 summon, 5, 13 object, 16 hero, 26/1006/2026 grande-alliance,
                                       1019 daemon …) [ACTIF #175 — `unit_trait_ids(visualId)`]
  unit_triggered_abilities : [int]    (1120 SaviorProtocols, 1221 MoltenForm, 1181 GuardianOrganism …)
  unit_faction : int                  (9 T'au-style, 15 GSC-style …)
  friend_positions : [(col,row)]      (allies vivants self-exclu = ctx.fpos — TriggeredAbilities(2))
  unit_has_ranged_weapon : bool ; unit_is_ai : bool ; player_door_mode : int ; contaminated_excluded : bool
Il porte AUSSI des CARTES par-position (`elev_by_pos`, `neigh_by_pos`, `is_territory_by_pos`,
`tile_effect_type_ids_by_pos`) : la carte est constante sur la décision, la valeur lue dépend de la
tuile — `apply_tile_attributes` en dérive les deux clés `meta` correspondantes.

Statut de portage (cf. docs/rl/playbook-engine.md §13.8/§13.14 et docs/rl/case-175-tile-unit-traits.md) :
- ACTIVES (metadata dispo) : Elevation(8), SteppableUnit(19), TileEffects(9, partiel), TemporaryTile(13),
  TriggeredAbilities(2) (dispatcher playbook, case-36 — via ctx.unit_triggered_abilities/friend_positions),
  DespoiledGround(28) et MoltenForm(23) (#175 — `ctx.unit_traits` + `meta.tile_effect_type_ids`).
- PORTÉES FIDÈLE mais DORMANTES (gate sur metadata non encore plombée → 0) : les autres `*Utility`.
  ⚠ #175 : leur ctx de TRAIT est désormais peuplé — ce qui reste manquant est la metadata PAR TUILE
  (`occupant_is_powerup`, `door`, `attract_mechanicals_neighbor`, `movetowards_hexdist`, …), qu'AUCUN
  RPC ne remonte à ce jour. `is_territory` fait exception : il est plombé, mais vaut `False` partout
  tant que la BC n'est pas en ruleset Territories (mesuré : 0 tuile territoire sur les seeds arène).
- NON portées comme simples leaves : RangedAdjacentEnemy(15)=0 dans Default ; TriggeredAbilitiesNonOwner(4)/
  UnitSpecificBehaviours(3) = dispatchers restants du moteur Playbook (séparé).
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

# Terrain STATIQUE (`tileDefId` de la BC) -> effets de cover HÉBERGÉS que la feuille TileEffects(9) somme.
# `TileEffectsUtility.<d__1>.IdunBattle.AI.Utilities.TileEffectsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` a DEUX boucles sur la tuile candidate : Loop1 = effets
# DYNAMIQUES (EffectsOwnedComponent, ex. Fire/Ice ; = `meta.effects` via tileMeta) ; **Loop2 = abilities
# HÉBERGÉES sur la tuile** (collection `DAT_1831b9908`, `Unit.get_Id` = `AbilityType`, poids
# `Default.TileEffects.<AbilityName>`). Le +9 LightCover d'une DryBush vient de LOOP2 (verdict re-expert :
# `LightCoverAbility` IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility$$CreateBehaviour est une `Abilities.Tiles.Loki.*` hébergée par le terrain DryBush, PAS un
# effet dynamique — une DryBush VIDE rend +9). Offline la seule source de cover statique = le terrain
# (`tileDefId`, boardGraph). DryBush->LightCover VALIDÉ L3 (909 s4 (3,2)=+9 EXACT, pas +DryBush_DefenseBonus
# => DryBush n'héberge que LightCover pour cette feuille). cf. docs/rl/terrain-effects.md §2 + case-37.
# ⚠ INCOMPLET, et on sait par quoi : `Swamp` héberge lui aussi une ability de tuile
# (`ThornsBlockMovementAbility`, description localisée `SwampBlockMovement` — cf. case-198 §RE et
# case-102 « Swamp = BlockEnteringUnits(0) + Thorns_DefenseReduction(0xb) »), donc Loop2 devrait y
# sommer `Default.TileEffects.Thorns_DefenseReduction` (-25). MESURÉ live sur le tri de placement des
# summons (case-130 SS5) — mais PAS ajouté ici : cette table alimente AUSSI le contexte de DÉGÂT
# (`runner/damage_model.py::tile_effects_context`, où une Swamp porte déjà ces noms comme effets
# DYNAMIQUES) et le scoring de MOUVEMENT ; l'y poser sans valider ces deux fronts est hors périmètre.
# Le site qui l'a mesuré le porte donc localement (`runner/operations/spawn.py`) — unification au backlog.
TERRAIN_TILE_EFFECTS: dict[str, tuple] = {
    "DryBush": ("LightCover",),
}


def terrain_tile_effects(terrain: str | None) -> list:
    """Noms d'effets de cover HÉBERGÉS par le terrain statique (`tileDefId`) — sommés par TileEffects(9)
    via son Loop2 (tile-hosted abilities). Vide si le terrain n'héberge aucun cover à poids BC."""
    return list(TERRAIN_TILE_EFFECTS.get(terrain or "", ()))


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
    """`ElevationUtility` (IdunBattle.AI.Utilities.ElevationUtility$$.ctor ; UtilityType.Elevation=8) ; `<d__8>.IdunBattle.AI.Utilities.ElevationUtility.u003CEvaluateMovementInStepsu003Ed__8$$MoveNext` :
        u = Multiplier × elev  (+ HighestElevation si elev == max) (+ LowestElevation si elev == min)
    BC : Multiplier=10, HighestElevation=10, LowestElevation=-5. `meta` requis (élévation tuile + max/min).
    ⚠ `elevation_max`/`elevation_min` = min/max sur le BOARD ENTIER, PAS le candidate-set : le natif
    `IdunBattle.AI.Utilities.ElevationUtility$$LoadRelevantTileElevations` (one-shot, garde this+0x68) énumère la collection de TOUS les
    tiles du board (composant board-singleton sur le World `this+0x10`, éléments = TileComponent, elev@+0x18)
    et calcule min@this+0x64 (seed 10) / max@this+0x60 (seed 0). Verdict re-expert (case-37) : ni unité, ni
    reachable, ni candidate-set. => la harness alimente min/max sur `elev_by_pos` COMPLET (tileMeta = board)."""
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
    """`SteppableUnitUtility` (IdunBattle.AI.Utilities.SteppableUnitUtility$$.ctor ; UtilityType.SteppableUnit=19) ; `<d__10>.IdunBattle.AI.Utilities.SteppableUnitUtility.u003CEvaluateMovementInStepsu003Ed__10$$MoveNext` :
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
    """`TileEffectsUtility` (IdunBattle.AI.Utilities.TileEffectsUtility$$.ctor ; UtilityType.TileEffects=9) ; `<d__1>.IdunBattle.AI.Utilities.TileEffectsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` :
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
    """`TemporaryTileUtility` (IdunBattle.AI.Utilities.TemporaryTileUtility$$.ctor ; UtilityType.TemporaryTile=13) ; `<d__1>.IdunBattle.AI.Utilities.TemporaryTileUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` :
    u = 0 ; si la tuile candidate est TEMPORAIRE → u -= Fix64(10000) (CONSTANTE, pas un poids BC ; le natif
    lit `tileData+0x2c` IsTemporary). L'IA évite fortement les tuiles temporaires. `meta.is_temporary`."""
    UTILITY_TYPE = int(UtilityType.TemporaryTile)  # 13

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if (meta or {}).get("is_temporary"):
            return TEMPORARY_TILE_PENALTY
        return 0.0


class AUnitEffectsUtility(BaseUtility):
    """`AUnitEffectsUtility` (IdunBattle.AI.Utilities.AUnitEffectsUtility$$.ctor, TypeDefIndex 12150) — base ABSTRAITE ; `IdunBattle.AI.Utilities.AUnitEffectsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` = le
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
    """`CapturePointTileUtility` (IdunBattle.AI.Utilities.CapturePointTileUtility$$.ctor ; UtilityType.CapturePoint=24) ; IdunBattle.AI.Utilities.CapturePointTileUtility.u003CEvaluateMovementInStepsu003Ed__3$$MoveNext : sur tuile
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
    """`PowerUpTileUtility` (IdunBattle.AI.Utilities.PowerUpTileUtility$$.ctor ; UtilityType.PowerUp=26) ; IdunBattle.AI.Utilities.PowerUpTileUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext : -300 si l'occupant de la
    tuile EstPowerUp ET flag(trait 2||13). `meta.occupant_is_powerup` + `ctx.unit_traits`."""
    UTILITY_TYPE = int(UtilityType.PowerUp)  # 26

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not (meta or {}).get("occupant_is_powerup"):
            return 0.0
        if not (_has(ctx, "unit_traits", 2) or _has(ctx, "unit_traits", 13)):
            return 0.0
        return wt.sub("PowerUp", "summons_dislike_tiles_with_powerups")


class ContaminatedUtility(BaseUtility):
    """`ContaminatedUtility` (IdunBattle.AI.Utilities.ContaminatedUtility$$.ctor ; UtilityType.Contaminated=25) ; IdunBattle.AI.Utilities.ContaminatedUtility.u003CEvaluateMovementInStepsu003Ed__4$$MoveNext : -25 si la tuile porte
    un effet type 1244 (0x4dc) ET l'unité n'est pas exclue. `meta.tile_effect_type_ids` + `ctx.contaminated_excluded`."""
    UTILITY_TYPE = int(UtilityType.Contaminated)  # 25

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if 1244 not in _eff_ids(meta, "tile_effect_type_ids"):
            return 0.0
        if (ctx or {}).get("contaminated_excluded"):
            return 0.0
        return wt.sub("Contaminated", "AffectedUnit")


class MoltenForm_TilesUtility(BaseUtility):
    """`MoltenForm_TilesUtility` (IdunBattle.AI.Utilities.MoltenForm_TilesUtility$$.ctor ; UtilityType.MoltenForm=23) ; IdunBattle.AI.Utilities.MoltenForm_TilesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext : si l'unité a la
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
    """`TilePendingBlockableSummonUtility` (IdunBattle.AI.Utilities.TilePendingBlockableSummonUtility$$.ctor ; UtilityType.TilePendingBlockableSummon=14) ; IdunBattle.AI.Utilities.TilePendingBlockableSummonUtility.u003CEvaluateMovementInStepsu003Ed__3$$MoveNext :
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
    """`EnvEndBombardmentUtility` (IdunBattle.AI.Utilities.EnvEndBombardmentUtility$$.ctor ; UtilityType.EnvEndBombardment=31) ; IdunBattle.AI.Utilities.EnvEndBombardmentUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext : tuile ciblée
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
    """`DespoiledGroundUtility` (IdunBattle.AI.Utilities.DespoiledGroundUtility$$.ctor ; UtilityType.DespoiledGround=28) ; IdunBattle.AI.Utilities.DespoiledGroundUtility.u003CEvaluateMovementInStepsu003Ed__5$$MoveNext : si tuile
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
    """`SummonDislikeDoorOpeningUtility` (IdunBattle.AI.Utilities.SummonDislikeDoorOpeningUtility$$.ctor ; UtilityType.SummonDislikeDoorOpening=29) ; IdunBattle.AI.Utilities.SummonDislikeDoorOpeningUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext :
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
    """`HeroDoorOpeningUtility` (IdunBattle.AI.Utilities.HeroDoorOpeningUtility$$.ctor ; UtilityType.HeroLikeDoorOpening=30) ; IdunBattle.AI.Utilities.HeroDoorOpeningUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext : UNIQUEMENT
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
    """`Phantasm_AvoidFriendlyPhantasmUtility` (IdunBattle.AI.Utilities.Phantasm_AvoidFriendlyPhantasmUtility$$.ctor ; UtilityType.Phantasm_AvoidFriendlyPhantasm=60) ;
    IdunBattle.AI.Utilities.Phantasm_AvoidFriendlyPhantasmUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext : -40 si la tuile porte l'effet Phantasm 1279 (0x4ff) ET un phantasme AMI est adjacent.
    `meta.phantasm_friendly_adjacent`."""
    UTILITY_TYPE = int(UtilityType.Phantasm_AvoidFriendlyPhantasm)  # 60

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not (meta or {}).get("phantasm_friendly_adjacent"):
            return 0.0
        return wt.sub("Phantasm_AvoidFriendlyPhantasm", "Phantasm_AvoidFriendlyPhantasm")


class EchoesFromTheWarp_FriendliesAvoidGhostUtility(BaseUtility):
    """`EchoesFromTheWarp_FriendliesAvoidGhostUtility` (IdunBattle.AI.Utilities.EchoesFromTheWarp_FriendliesAvoidGhostUtility$$.ctor ; UtilityType.=58) ; IdunBattle.AI.Utilities.EchoesFromTheWarp_FriendliesAvoidGhostUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext : +10 si
    la tuile POSSÈDE (owner) l'effet ghost 1284 (0x504) ET le ghost ami est adjacent. `meta.ghost_friendly_adjacent`."""
    UTILITY_TYPE = int(UtilityType.EchoesFromTheWarp_FriendliesAvoidGhost)  # 58

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not (meta or {}).get("ghost_friendly_adjacent"):
            return 0.0
        return wt.sub("EchoesFromTheWarp_FriendliesAvoidGhost", "GhostTile")


class AttractMechanicalsUtility(BaseUtility):
    """`AttractMechanicalsUtility` (IdunBattle.AI.Utilities.AttractMechanicalsUtility$$.ctor ; UtilityType.DoctrinaImperatives_AttractMechanicals=57) ;
    IdunBattle.AI.Utilities.AttractMechanicalsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext : +10 si l'unité a le trait 5 ET un voisin (autour de la tuile) a l'active ability 1118
    (0x45e). `ctx.unit_traits` + `meta.attract_mechanicals_neighbor`."""
    UTILITY_TYPE = int(UtilityType.DoctrinaImperatives_AttractMechanicals)  # 57

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not _has(ctx, "unit_traits", 5):
            return 0.0
        if not (meta or {}).get("attract_mechanicals_neighbor"):
            return 0.0
        return wt.sub("DoctrinaImperatives_AttractMechanicals", "Marshal_AttractMechanicals")


class AttractToDecoysUtility(BaseUtility):
    """`AttractToDecoysUtility` (IdunBattle.AI.Utilities.AttractToDecoysUtility$$.ctor ; UtilityType.DecoysAndMisdirection_AttractToDecoys=64) ;
    IdunBattle.AI.Utilities.AttractToDecoysUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext : +75 PAR ami avec triggered ability 1304 (0x518), gate : unité faction 15 ET tuile avec une
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
    """`KustomForceFieldUtility` (IdunBattle.AI.Utilities.KustomForceFieldUtility$$.ctor ; UtilityType.KustomForceField=20) ; base ATriggeredAbilityUtility.d__3
    IdunBattle.AI.Utilities.ATriggeredAbilityUtility.u003CEvaluateMovementInStepsu003Ed__3$$MoveNext : +20 × count(amis ADJACENTS R1 avec triggered ability 1102). `meta.ability_friend_counts[1102]`."""
    UTILITY_TYPE = int(UtilityType.KustomForceField)  # 20

    def evaluate(self, tile, meta, ctx, wt) -> float:
        return _ability_count(meta, 1102) * wt.sub("KustomForceField", "AdjacentFriendly")


class DefenderOfTheGreaterGoodUtility(BaseUtility):
    """`DefenderOfTheGreaterGoodUtility` (IdunBattle.AI.Utilities.DefenderOfTheGreaterGoodUtility$$.ctor ; UtilityType.DefenderOfTheGreaterGood=21) ; IdunBattle.AI.Utilities.ATriggeredAbilityUtility.u003CEvaluateMovementInStepsu003Ed__3$$MoveNext :
    +25 × count(amis R1, ou R2 si faction 9, avec ability 1155). Gate : arme à distance.
    `ctx.unit_has_ranged_weapon` + `meta.ability_friend_counts[1155]`."""
    UTILITY_TYPE = int(UtilityType.DefenderOfTheGreaterGood)  # 21

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not (ctx or {}).get("unit_has_ranged_weapon"):
            return 0.0
        return _ability_count(meta, 1155) * wt.sub("DefenderOfTheGreaterGood", "PerUnitWithAbilityInRange")


class SaviorProtocolsUtility(BaseUtility):
    """`SaviorProtocolsUtility` (IdunBattle.AI.Utilities.SaviorProtocolsUtility$$.ctor ; UtilityType.SaviorProtocols=22) ; IdunBattle.AI.Utilities.ATriggeredAbilityUtility.u003CEvaluateMovementInStepsu003Ed__3$$MoveNext : +20 × count(amis
    ADJACENTS R1 avec ability 1120). Gate : faction 9 ET n'a pas l'ability 1120. `ctx.unit_faction/
    unit_triggered_abilities` + `meta.ability_friend_counts[1120]`."""
    UTILITY_TYPE = int(UtilityType.SaviorProtocols)  # 22

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if (ctx or {}).get("unit_faction") != 9 or _has(ctx, "unit_triggered_abilities", 1120):
            return 0.0
        return _ability_count(meta, 1120) * wt.sub("SaviorProtocols", "PerUnitWithAbilityInRange")


class MoveTowardsUnitUtility(BaseUtility):
    """`MoveTowardsUnitUtility` (IdunBattle.AI.Utilities.MoveTowardsUnitUtility$$.ctor ; base) ; `IdunBattle.AI.Utilities.MoveTowardsUnitUtility.u003CEvaluateMovementInStepsu003Ed__15$$MoveNext` : score = poids("PerTileDistance")
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
    """`BioMinefield_MoveTowardsTargetUtility` (IdunBattle.AI.Utilities.BioMinefield_MoveTowardsTargetUtility$$.ctor ; UtilityType.=61) : -100 × hexdist(candidate,
    cible ability/effet 1315). Pas de gate trait."""
    UTILITY_TYPE = int(UtilityType.BioMinefield_MoveTowardsTarget)  # 61
    _CAT = "BioMinefield_MoveTowardsTarget"
    _ABILITY_ID = int(EffectType.BioMinefield_Target)  # 1315 (effet marqueur de cible ; #158, absent d'ActiveAbilityType)
    _TRAIT_GATE = None


class MasterOfTheTutelaries_MoveTowardsTargetUtility(MoveTowardsUnitUtility):
    """`MasterOfTheTutelaries_MoveTowardsTargetUtility` (IdunBattle.AI.Utilities.MasterOfTheTutelaries_MoveTowardsTargetUtility$$.ctor ; UtilityType.=62) : -20 × hexdist(candidate,
    cible 1096). Gate trait : l'unité a 2026 ou 1019."""
    UTILITY_TYPE = int(UtilityType.MasterOfTheTutelaries_MoveTowardsTarget)  # 62
    _CAT = "MasterOfTheTutelaries_MoveTowardsTarget"
    _ABILITY_ID = int(ActiveAbilityType.MasterOfTheTutelaries)  # 1096 (#158 : nom classe matche Active, PAS EffectType.KustomForceField/Triggered.SoulHunger)
    _TRAIT_GATE = {2026, 1019}


class TriggeredAbilitiesUtility(BaseUtility):
    """`TriggeredAbilitiesUtility` (`.IdunBattle.AI.Utilities.TriggeredAbilitiesUtility$$.ctor` ; UtilityType.TriggeredAbilities=2) ;
    `<EvaluateMovementInSteps>IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext` : DISPATCHER — itère les abilities DE L'UNITÉ
    QUI BOUGE (`case.unit@0x10` → AbilitiesComponent), `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook(abilityType)` (singleton par type, null → skip), Σ des `CalculateMovementUtilityInSteps` (famille
    `AdjacentUnitPreferenceTriggeredAbilityPlaybook` : `engine/playbook/adjacent_unit_preference.py`).
    `ctx.unit_triggered_abilities` (kit passif du mover — `triggered_ability_ids(visualId)`) +
    `ctx.friend_positions` (allies vivants self-exclu = `ctx.fpos`). Cf. case-36 (909 s4/s19 : 30/90)."""
    UTILITY_TYPE = int(UtilityType.TriggeredAbilities)  # 2

    def evaluate(self, tile, meta, ctx, wt) -> float:
        ab_ids = (ctx or {}).get("unit_triggered_abilities") or ()
        if not ab_ids:
            return 0.0
        # Import paresseux : utilities.tile est importé par engine.playbook.base — l'import module-level
        # inverse (tile -> playbook) bouclerait. Chaque playbook lit SES clés du ctx par-décision
        # (AdjacentUnitPreference : friend_positions ; Fury 1247 : enemies/scene/… — #32) : pas de
        # gate global sur friends ici (le natif dispatche inconditionnellement, la feuille dégrade
        # à 0 dans le playbook).
        from ..playbook.adjacent_unit_preference import load_playbook
        total = 0.0
        for ab in ab_ids:
            pb = load_playbook(ab)
            if pb is not None:
                total += pb.calculate_movement_utility_in_steps(tile, ctx, wt)
        return total

    def evaluate_attack_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                 target_uid: int, attack_tile) -> float:
        """Face ATTACK du dispatcher — `<EvaluateAttackInSteps>IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateAttackInStepsInternalu003Ed__3$$MoveNext` (feuille 2
        du composite Damage(34), #45-s18) : itère les abilities déclenchées de l'ATTAQUANT (kit
        COMPLET passifs+traits = AbilitiesComponent), `PlaybookDatabase.LoadPlaybook`, Σ des
        `ITriggeredAbilityPlaybook.CalculateAttackUtilityInSteps` (vslot 3 — registre attack
        `engine/playbook/psyker.py`, ce build : PsykerExtraAttack 1013 seul). `ctx` = AiDecisionContext
        (scene/wt/hpmax/normal_ids), PAS le dict tile-leaf de la face move."""
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return 0.0
        from ..entities.triggered_ability_type import kit_triggered_ability_ids
        from ..playbook.psyker import load_attack_playbook
        total = 0.0
        for ab in kit_triggered_ability_ids(sc.vis_by_id.get(attacker_uid)):
            pb = load_attack_playbook(ab)
            if pb is not None:
                total += pb.calculate_attack_utility_in_steps(ctx, attacker_uid, ability_id,
                                                              target_uid, attack_tile)
        return total


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
    # --- Dispatcher playbook PORTÉ (case-36) : abilities déclenchées de l'unité qui bouge ---
    2:  ("TriggeredAbilities", TriggeredAbilitiesUtility()),   # face attack : cf. fonction ci-dessous
    # --- NON portées comme simples leaves ---
    15: ("RangedAdjacentEnemy", None),       # =0 dans le profil Default (BC HasAdjacentEnemy absent)
    # 3/4 = dispatchers vers le moteur Playbook (LoadPlaybookNonOwner / behaviours par-unité).
    # NonOwner(4) RE COMPLETE (#57i) : feuille `TriggeredAbilitiesNonOwnerUtility` (IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility$$.ctor ;
    # `<EvaluateMovementInSteps>IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.u003CEvaluateMovementInStepsu003Ed__0$$MoveNext` ; enum `<IterateAbilities>d__3.MoveNext
    # IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.u003CIterateAbilitiesu003Ed__3$$MoveNext` = pour CHAQUE unite non-self, `IdunBattle.AI.PlaybookDatabase$$LoadPlaybookNonOwner` puis yield
    # (playbook, entity) si `AppliesToFriendly(slot4) || IsFriend` ; famille `AdjacentToOwnerNonOwner
    # Playbook<T>.<...>IdunBattle.AI.Playbook.AdjacentToOwnerNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext` : tuile adjacente au PORTEUR -> `GetUtilityValue`
    # IdunBattle.AI.Playbook.TriggeredAbilityNonOwnerPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GetUtilityValue = config `Default.TriggeredAbilitiesNonOwner[<cle>]`). Les 25 cles NonOwner sont des
    # abilities LEGENDAIRES precises (FirstAmongTraitors/ShieldOfFaith/HaywireMine/NornCrown/...) ->
    # la feuille yield 0 tant qu'AUCUNE unite ne PORTE une de ces abilities. Ce N'ETAIT PAS la source
    # des miss #57i (S14 12345 u87 / S16 2468 u79 : aucun ennemi ne porte de NonOwner) -> le vrai trou
    # etait la branche ENNEMIS de la feuille (2) TriggeredAbilities (voir adjacent_unit_preference.py).
    # A porter (feuille propre) quand un case montre une unite portant une ability NonOwner decisive.
    4:  ("TriggeredAbilitiesNonOwner", None),
    3:  ("UnitSpecificBehaviours", None),
}


# Composite Tile(7) = INSTANCE `ComposedUtility` (PAS de classe `TileUtility` : Tile est un UtilityType,
# le composite est un ComposedUtility enregistre a 7). `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromTilePrediction`
# = Σ feuilles (ordre runtime TILE_LEAF_IDS, feuilles non portees ecartees). Carte plate ≈ 0.
TILE_UTILITY = ComposedUtility(
    [TILE_LEAVES[i][1] for i in TILE_LEAF_IDS if TILE_LEAVES.get(i, (None, None))[1] is not None],
    utility_type=UtilityType.Tile)


def tile_composite(tile, meta: dict | None, ctx: dict, wt: Weights) -> float:
    """Composite Tile(7) = `TILE_UTILITY.evaluate` (Σ des feuilles portées). Wrapper mince pour les
    appelants existants (`engine.playbook.base.tile_utility`, `engine.move`). `meta` absent ⇒ ≈0."""
    return TILE_UTILITY.evaluate(tile, meta or {}, ctx, wt)


def _adjacent_units(ctx, uid):
    """{pos,traits} des AMIS (ctrl, self-exclu) et ENNEMIS (non-ctrl) vivants positionnés — mirror des
    query natives `GetAdjacentFriends`/`GetAdjacentEnemies` du corps AdjacentUnitPreference (#57i). Les
    traits (gameconfig) alimentent les filtres `FilterAdjacent*` (ex. FabricatorClaw = Mechanical=5).
    getattr-tolerant : un contexte sans `units` (NCContext) rend deux listes vides -> feuille silencieuse."""
    import gameconfig as GC
    friends, enemies = [], []
    for u in (getattr(ctx, "units", None) or []):
        pos = u.get("pos")
        if not (u.get("alive") and pos):
            continue
        rec = {"pos": (pos["col"], pos["row"]),
               "traits": frozenset(((GC.unit(u.get("visualId")) or {}).get("traits")) or ())}
        if u.get("ctrl"):
            if u.get("id") != uid:
                friends.append(rec)
        else:
            enemies.append(rec)
    return friends, enemies


def tile_leaf_ctx(ctx) -> dict:
    """Dict `ctx` PAR-DÉCISION des feuilles Tile(7) depuis l'`AiDecisionContext` — feuille
    TriggeredAbilities(2) (case-36) : kit passif du mover (dispatcher `IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext` sur l'Abilities-
    Component) + allies vivants self-exclu (adjacence R1/R2 de la tuile candidate). Vit ICI (module
    des feuilles) car consommé par les DEUX chemins natifs de la Composed Tile(7) : le sweep MOVE
    (`engine.move` via action_generators) ET le terme Tile(7) de l'ATTAQUE (`playbook.base.
    tile_utility` — case-49 : le natif émet la MÊME `ComposedUtility` sous `Loki_NormalAttackPlaybook`,
    L3 s14 31337). Import ici = pas de cycle (action_generators importe playbook.base).

    #32 : clés supplémentaires pour la famille `TriggeredAbilityPlaybook<T>` (Fury 1247 : ennemis
    adjacents à la tuile + prédiction de dégât) — `uid`/`enemies`/`elev_by_pos`/`neigh_by_pos`/
    `scene`/`hpmax_by_id`. getattr-tolérant : NCContext (via get_movement_utility/NovaShield) n'a
    ni `me` ni `hpmax_by_id` -> kit vide = feuille silencieuse (comportement pré-case-49) ; ses
    champs partagés (enemies/elev/scene) passent tels quels."""
    from ..entities.triggered_ability_type import triggered_ability_ids   # lazy : évite tout cycle
    from ..entities.traits.unit_trait import unit_trait_ids               # lazy : idem
    me = getattr(ctx, "me", None) or {}
    uid = getattr(ctx, "uid", None)
    friend_units, enemy_units = _adjacent_units(ctx, uid)
    return {"unit_triggered_abilities": triggered_ability_ids(me.get("visualId")),
            # IDS `UnitTrait` du MOVER — l'argument que les 7 feuilles à gate de trait passent à
            # `IdunBattle.Entities.UnitExtensions$$HasTrait(case.unit@+0x10, <traitId>)` (le `case`
            # porte l'unité qui évalue la tuile : `CapturePointTileUtility.<d__3>`, `PowerUpTile
            # Utility.<d__2>`, `DespoiledGroundUtility.<d__5>`, `SummonDislikeDoorOpeningUtility
            # .<d__2>`, `HeroDoorOpeningUtility.<d__2>`, `AttractMechanicalsUtility.<d__1>`,
            # `MoveTowardsUnitUtility.<d__15>`). Source = `unit_trait_ids` (kit gameconfig +
            # pseudo-trait de grande-alliance) — cf. sa docstring pour les DEUX collections natives
            # non observables offline (traits retirés / accordés en bataille).
            "unit_traits": unit_trait_ids(me.get("visualId")),
            "friend_positions": ctx.fpos,
            # {pos,traits} vivants self-exclu — branches AMIS(B1)/ENNEMIS(B2) de AdjacentUnitPreference
            # (#57i : traits pour les filtres, ex. FabricatorClaw garde les amis Mechanical).
            "friend_units": friend_units,
            "enemy_units": enemy_units,
            "uid": uid,
            "enemies": getattr(ctx, "enemies", None) or [],
            "elev_by_pos": getattr(ctx, "elev_by_pos", None),
            "neigh_by_pos": getattr(ctx, "neigh_by_pos", None),
            # Cartes PAR-POSITION des attributs de TUILE que `tileMeta` remonte déjà et que les deux
            # constructeurs de `meta` jetaient (cf. `apply_tile_attributes`). Même statut que
            # `elev_by_pos`/`neigh_by_pos` ci-dessus : la CARTE est constante sur la décision, la
            # valeur lue dépend de la tuile candidate.
            "is_territory_by_pos": getattr(ctx, "is_territory_by_pos", None),
            "tile_effect_type_ids_by_pos": getattr(ctx, "tile_effect_type_ids_by_pos", None),
            "scene": getattr(ctx, "scene", None),
            "hpmax_by_id": getattr(ctx, "hpmax_by_id", None) or {}}


def apply_tile_attributes(meta: dict, pos, leaf_ctx: dict | None) -> dict:
    """Complète le `meta` PAR-TUILE avec les deux attributs de tuile que le RPC `tileMeta` remonte
    DÉJÀ et que les deux constructeurs de `meta` (`engine.move` et `engine.playbook.base.
    tile_utility`) jetaient — sans eux, les feuilles qui les gatent restent muettes quoi qu'on
    mette dans `ctx` :

    - `is_territory` <- `tileMeta.isTerritory` = `TileComponent+0x2e`, l'octet EXACT que lit
      `IdunBattle.Entities.TileExtensions$$IsTerritoryTile` (appelé par
      `IdunBattle.AI.Utilities.CapturePointTileUtility.u003CEvaluateMovementInStepsu003Ed__3$$MoveNext`
      sur `case.position.MainTile`) ;
    - `tile_effect_type_ids` <- `tileMeta.effects[].effectType` = `EffectComponent+0x58`, le champ
      que `IdunBattle.AI.Utilities.DespoiledGroundUtility.u003CEvaluateMovementInStepsu003Ed__5$$MoveNext`
      compare à `0x5c4` en énumérant l'`EffectsOwnedComponent` de la tuile (même substrat pour
      `ContaminatedUtility` 0x4dc et `MoltenForm_TilesUtility` 5/10).

    Écrit en place et rend `meta` (les clés absentes des cartes ne sont PAS posées : une carte non
    fournie laisse la feuille dégrader à 0, comme aujourd'hui)."""
    lc = leaf_ctx or {}
    terr = lc.get("is_territory_by_pos")
    if terr is not None and pos in terr:
        meta["is_territory"] = bool(terr[pos])
    tids = lc.get("tile_effect_type_ids_by_pos")
    if tids:
        ids = tids.get(pos)
        if ids:
            meta["tile_effect_type_ids"] = ids
    return meta


def triggered_abilities_attack_utility(ctx, attacker_uid: int, ability_id: int,
                                       target_uid: int, attack_tile) -> float:
    """Feuille TriggeredAbilities(2) FACE ATTACK du composite Damage(34) (#45-s18) — entrée des deux
    scoreurs de paire (`playbook.base.calculate_action_utility` + stages `_formula_pair_utility`).
    Le natif évalue les 13 feuilles Damage DANS `ForDamagePrediction`, PAR DamageEvent -> ce terme
    s'ajoute au `damage_composite` de l'event et suit son `prob x signe` (à appliquer PAR L'APPELANT,
    comme pour le composite). `attack_tile` = tuile caster du case (sweep de position)."""
    return _TRIG_AB_UTILITY.evaluate_attack_in_steps(ctx, attacker_uid, ability_id,
                                                     target_uid, attack_tile)


_TRIG_AB_UTILITY: TriggeredAbilitiesUtility = TILE_LEAVES[2][1]
