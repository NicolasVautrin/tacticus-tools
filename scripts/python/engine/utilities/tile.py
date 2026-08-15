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
  elevation : int ; elevation_max, elevation_min : int     (Elevation 9 — tuile via tileMeta ; max/min sur le
                                                            BOARD ENTIER, cf. LoadRelevantTileElevations) [ACTIF]
  steppable : {is_friend, is_enemy, is_decoy, triggered} | None   (SteppableUnit 20) [ACTIF #241 —
                                                            occupant `Steppable` de la tuile, via
                                                            `apply_tile_attributes`]
  effects : [effect_name]                                  (TileEffects 10 — effets DYNAMIQUES (Loop1) + covers
                                                            HÉBERGÉS par le terrain (Loop2 : DryBush->LightCover)) [ACTIF]
  is_temporary : bool                                      (TemporaryTile 14 — via tileMeta) [ACTIF]
  is_territory : bool                                      (CapturePoint 25 — via tileMeta.isTerritory) [ACTIF #175,
                                                            mais 0 tuile territoire hors ruleset Territories]
  occupant_is_powerup : bool                               (PowerUp 27)
  tile_effect_type_ids : [int]                             (Contaminated 1244 / MoltenForm 5,10 / DespoiledGround 1476)
                                                           [ACTIF #175 — via tileMeta.effects[].effectType]
  effect_target_ids : [int]                                (EnvEndBombardment 1359/1360)
  pending_summons : [{type_id:int, owner_is_enemy:bool}]   (TilePendingBlockableSummon 1094)
  door : {linked:bool, closed:bool}                        (SummonDislikeDoorOpening 30 / HeroLikeDoorOpening 31)
  hero_door_nearest_cost : int                             (HeroLikeDoorOpening 31 branche B)
  phantasm_friendly_adjacent / ghost_friendly_adjacent : bool      (Phantasm 60 / Echoes 58)
  attract_mechanicals_neighbor : bool                      (DoctrinaImperatives_AttractMechanicals)
                                                           [ACTIF #477-r31 — un AMI adjacent (self
                                                            exclu) portant `DoctrinaImperatives`,
                                                            via `apply_tile_attributes`]
  decoy_gate : bool, decoy_friend_count : int              (DecoysAndMisdirection 64) [ACTIF #241 —
                                                            occupant steppable NON ennemi + compte
                                                            des amis porteurs de 1304]
  ability_friend_counts : {ability_id:int -> count}        (KustomForceField 1102 / Defender 1155 / Savior 1120)
                                                           [ACTIF #175-r — `_ability_friend_counts`,
                                                            via `apply_tile_attributes`]
  movetowards_pathdist : {identifiant:int -> Count}        (BioMinefield 1315 / MasterOfTheTutelaries 1096)
                                                           [ACTIF #175-r1 — `_movetowards_pathdist_by_pos`,
                                                            via `apply_tile_attributes`. Count = NOEUDS du
                                                            `GetPath(PathfinderType.IgnoreTerrain, …)`,
                                                            extrémités INCLUSES. L'ancien nom
                                                            `movetowards_hexdist` MENTAIT — ce n'a jamais
                                                            été une distance hex.]
  neighbor_effect_names : {adjacent|surrounding1|ranged2 -> [effect_name]}   (UnitEffects 10/11/12)

`ctx` (PAR UNITÉ/DÉCISION, constant sur toutes les tuiles d'une décision) — clés consommées :
  unit_traits : [int]                 (2 summon, 5, 13 object, 16 hero, 26/1006/2026 grande-alliance,
                                       1019 daemon …) [ACTIF #175 — `unit_trait_ids(visualId)`]
  unit_triggered_abilities : [int]    (1120 SaviorProtocols, 1221 MoltenForm, 1181 GuardianOrganism …)
  unit_faction : int                  (valeur `UnitFaction` du mover : 9 Tau, 15 Genestealers …)
                                      [ACTIF #241 — `faction_value(visualId)` = `FactionId` gameconfig
                                       -> enum, le pendant du `System.Enum.ToString` de `HasFaction`]
  friend_positions : [(col,row)]      (allies vivants self-exclu = ctx.fpos — TriggeredAbilities(2))
  unit_has_ranged_weapon : bool ; unit_is_ai : bool ; player_door_mode : int
  ⚠ `contaminated_excluded` A DISPARU (#175-e) : la clé n'était peuplée par AUCUN des trois
    constructeurs de `ctx`, et sa FORME était fausse. L'exclusion native n'est pas un booléen
    par-décision mais `effectsDatabase.GetEffect(<type>).EntityIsImmuneToEffect(case.unit)`, dérivé
    des seuls `unit_traits` (cf. `_entity_is_immune_to_effect`).
  is_spawning : bool                  (`IdunBattle.AI.Utilities.UtilityMovementCase$$get_IsSpawning`
                                       = `case.unit == null && case.parent != null` — le call-site SUMMON
                                       `SortTilesByUtilityForSummon` n'a PAS de sujet, cf. case-205)
Il porte AUSSI des CARTES par-position (`elev_by_pos`, `neigh_by_pos`, `is_territory_by_pos`,
`tile_effect_type_ids_by_pos`) : la carte est constante sur la décision, la valeur lue dépend de la
tuile — `apply_tile_attributes` en dérive les deux clés `meta` correspondantes.

Statut de portage (cf. docs/rl/playbook-engine.md §13.8/§13.14 et docs/rl/case-175-tile-unit-traits.md) :
- ACTIVES (metadata dispo) : Elevation(9), TileEffects(10, partiel), TemporaryTile(14),
  TriggeredAbilities(2) (dispatcher playbook, case-36 — via ctx.unit_triggered_abilities/friend_positions),
  DespoiledGround(29) et MoltenForm(24) (#175 — `ctx.unit_traits` + `meta.tile_effect_type_ids`),
  UnitEffects 10/11/12 (N13 — `meta.neighbor_effect_names`), SteppableUnit(20) et
  DecoysAndMisdirection_AttractToDecoys(65) (#241 — occupant steppable de la tuile, cf. case-241),
  DoctrinaImperatives_AttractMechanicals (#477-r31 — un AMI adjacent porteur de
  `ActiveAbilityType.DoctrinaImperatives`, dérivé de `ctx.friend_units[].active`, cf. case-477r31).
- PORTÉES FIDÈLE mais DORMANTES (gate sur metadata non encore plombée → 0) : les autres `*Utility`.
  ⚠ #175 : leur ctx de TRAIT est désormais peuplé — ce qui reste manquant est la metadata PAR TUILE
  (`occupant_is_powerup`, `door`), qu'AUCUN RPC ne remonte à ce jour.
  ⚠ #175-r1 : `movetowards_pathdist` FIGURAIT dans cette liste, et à tort — comme
  `attract_mechanicals_neighbor` avant elle. Elle n'a jamais demandé de RPC neuf : la distance est
  celle d'`ignore_terrain_pathfinder` (déjà portée et confrontée) et l'identification de la cible ne
  lit que `unit_parent_id`, `unit_active_abilities` et l'`EffectComponent` (type + `SourceUnitId`),
  que `decisionView.units[].effects` publie DÉJÀ. Les deux feuilles 62/63 sont ACTIVES depuis.
  ⚠ #477-r31 : `attract_mechanicals_neighbor` FIGURAIT dans cette liste, et à tort — elle n'a jamais
  demandé de RPC neuf, seulement `ctx.friend_units[].active` (posé par #477-r29). « Aucun RPC ne le
  remonte » se re-dérive, ne se recopie pas : ici la phrase a survécu à sa cause pendant une tranche
  entière. `is_territory` fait exception dans l'autre sens : il est plombé, mais vaut `False` partout
  tant que la BC n'est pas en ruleset Territories (mesuré : 0 tuile territoire sur les seeds arène).
- NON portées comme simples leaves : RangedAdjacentEnemy(16)=0 dans Default ;
  UnitSpecificBehaviours(3) = dispatcher restant du moteur Playbook (séparé).
  TriggeredAbilitiesNonOwner(4) est PORTÉE depuis #271 (`engine/playbook/non_owner.py`).
"""
from __future__ import annotations

from ..weights import Weights
from .base import BaseUtility, ComposedUtility
from .decider import UtilityBucket, UtilityDefinition, calculate_utility
from .leading_the_charge import LEADING_THE_CHARGE_CHARGE_TILE
from .ramming_speed import RAMMING_SPEED_MOST_ADJACENT_ENEMIES
from .utility_type import UtilityType
from ..entities.effect_type import EffectType
from ..entities.active_ability_type import ActiveAbilityType
# Enums natifs purs (aucun import `engine` -> aucun cycle) : les feuilles SteppableUnit(20) et
# DecoysAndMisdirection_AttractToDecoys(65) citent leurs litteraux par leur MEMBRE d'enum (#241).
from ..entities.triggered_ability_type import TriggeredAbilityType
from ..entities.traits.unit_trait import UnitTrait
from ..entities.unit_faction import UnitFaction, faction_value
from ..entities.traits.unit_trait import entity_trait_ids
from ..entities.traits.unit_trait import entity_trait_ids, entity_trait_names
from ..entities.traits.unit_trait import entity_trait_names
from ..entities.triggered_ability_type import entity_triggered_ability_ids
from ..entities.triggered_ability_type import kit_triggered_ability_ids
from ..entities.triggered_ability_type import triggered_ability_ids
# #477-r29 : le pendant ACTIF du precedent -- ce qu'`IdunBattle.Entities.UnitExtensions$$
# HasActiveAbility` interroge (l'`ActiveAbilityComponent`), lu par le predicat de
# `RadSaturationPlaybook` sur les AMIS ADJACENTS et sur le MOVER lui-meme.
from ..entities.active_abilities import entity_active_ability_ids
# `IdunBattle.Entities.TileExtensions$$GetSteppableUnit` -- foyer UNIQUE (#477-r35), re-exporte
# plus bas sous son ancien nom `_steppable_occupant` pour les appelants existants.
from ..entities.tile_extensions import get_steppable_unit
from .. import battle_query as _bq
from ..weights import load as _load_weights

# UtilityType des 29 feuilles de Tile(7) (ordre runtime). name = catégorie BC `Default.<name>`.
# #158 : ids bruts -> membres `UtilityType` nommés (l'ordre est la sequence runtime native).
# #254 : les clés de `TILE_LEAVES` sont désormais des MEMBRES elles aussi. L'ancienne note « value-
# preserving, IntEnum -> clés TILE_LEAVES[i] inchangées » ne vaut PLUS : une MAJ de build peut
# renuméroter l'enum (elle l'a fait), et seul un appariement membre<->membre y survit.
TILE_LEAF_IDS = [
    UtilityType.Elevation, UtilityType.TemporaryTile, UtilityType.TileEffects,           # 8, 13, 9
    UtilityType.UnitEffectsAdjacent, UtilityType.UnitEffectsSurrounding, UtilityType.UnitEffectsRanged,  # 10, 11, 12
    UtilityType.RangedAdjacentEnemy, UtilityType.SteppableUnit, UtilityType.CapturePoint,  # 15, 19, 24
    UtilityType.TriggeredAbilities, UtilityType.TriggeredAbilitiesNonOwner, UtilityType.UnitSpecificBehaviours,  # 2, 4, 3
    UtilityType.KustomForceField, UtilityType.DefenderOfTheGreaterGood, UtilityType.SaviorProtocols,  # 20, 21, 22
    UtilityType.TilePendingBlockableSummon, UtilityType.PowerUp, UtilityType.DoctrinaImperatives_AttractMechanicals,  # 14, 26, 57
    UtilityType.Phantasm_AvoidFriendlyPhantasm, UtilityType.EchoesFromTheWarp_FriendliesAvoidGhost, UtilityType.Contaminated,  # 60, 58, 25
    UtilityType.MoltenForm, UtilityType.BioMinefield_MoveTowardsTarget, UtilityType.MasterOfTheTutelaries_MoveTowardsTarget,  # 24, 62, 63
    # ⚠ Les ordinaux en commentaire de CETTE liste sont DECALES DE -1 sur plusieurs lignes (relus
    # dans `data/symbols/<build>/frida/enums.tsv` du build courant a l'occasion de #175-r1 : les
    # trois de la ligne ci-dessus valaient « 23, 61, 62 » pour 24/62/63). Les valeurs EXECUTABLES,
    # elles, sont des membres d'enum -- donc justes : seuls les commentaires mentent. Le glissement
    # n'est PAS corrige ligne a ligne ici (hors perimetre, fichier partage) ; il est SIGNALE.
    UtilityType.DecoysAndMisdirection_AttractToDecoys, UtilityType.DespoiledGround, UtilityType.SummonDislikeDoorOpening,  # 64, 28, 29
    UtilityType.HeroLikeDoorOpening, UtilityType.EnvEndBombardment,                       # 30, 31
]

# Pénalité constante (Fix64) appliquée aux tuiles temporaires — RE'd, PAS un poids BC.
TEMPORARY_TILE_PENALTY = -10000.0

# ── FOYER UNIQUE « terrain STATIQUE (`tileDefId` de la BC) -> noms sommés par la feuille TileEffects(10) »
# `TileEffectsUtility.<d__1>.IdunBattle.AI.Utilities.TileEffectsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` a DEUX boucles sur la tuile candidate, et
# elles n'ont NI la même source NI le même espace de noms (relu au décompilé, case-155) :
#
#   Loop1 — `GetComponent<EffectsOwnedComponent>(mainTile)` puis, par effet possédé,
#           `name = ((EffectType)EffectComponent+0x58).ToString()` ; poids `Default.TileEffects.<EffectType>`,
#           MULTIPLIÉ par `TileEffectsUtility$$GetStatusEffectMultiplier` UNIQUEMENT si
#           `StaticBattleRules.Effect$$IsTileStatusEffect` (sinon poids BRUT). C'est le canal des effets
#           DYNAMIQUES portés par l'ENTITÉ-TUILE (Fire/Ice… ET Thorns, cf. plus bas).
#   Loop2 — collection `DAT_1831b9908` de la tuile, `Unit.get_Id(ability)` -> `ActiveAbilityType.ToString()` ;
#           poids `Default.TileEffects.<AbilityName>`, SANS multiplicateur. C'est le canal des abilities
#           HÉBERGÉES par le terrain.
#
# `TERRAIN_HOSTED_ABILITIES` = Loop2. Le +9 LightCover d'une DryBush en vient (verdict re-expert :
# `IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility$$CreateBehaviour` = `AddEffect(0x3f5,
# state, UnitsThatNeedEffect())` -> l'effet est posé sur les UNITÉS, la TUILE n'en porte aucun ; une
# DryBush VIDE rend quand même +9, donc le poids ne peut venir que de Loop2). VALIDÉ L3 (909 s4 (3,2)=+9
# EXACT, pas +DryBush_DefenseBonus => DryBush n'héberge que LightCover pour cette feuille).
# cf. docs/rl/terrain-effects.md §2 + case-37.
TERRAIN_HOSTED_ABILITIES: dict[str, tuple] = {
    "DryBush": ("LightCover",),
}

# `TERRAIN_TILE_OWNED_EFFECTS` = REPLI STATIQUE de Loop1, PAS une seconde table de terrain-effects.
# `IdunBattleLogic.Entities.Abilities.Tiles.ThornsBlockMovementAbility$$CreateBehaviour` (l'ability
# hébergée par `Swamp`, description localisée `SwampBlockMovement`) =
#     `AddBlockEnteringUnitsEffect(0) & AddStaticStatModifierEffectToOwner(0xb, 3, Direct(const 0x14))`
# — le second POSE l'effet `Thorns_DefenseReduction` (0xb) **sur la tuile elle-même** (« ToOwner »). Une
# Swamp porte donc ce nom dans son `EffectsOwnedComponent` (MESURÉ live C1_02, case-102 : Swamp =
# `BlockEnteringUnits`(0) + `Thorns_DefenseReduction`(0xb)) et c'est **Loop1**, pas Loop2, qui en somme
# le `Default.TileEffects.Thorns_DefenseReduction` = -25 (aucune clé BC `SwampBlockMovement` /
# `ThornsBlockMovement` n'existe -> `HasUtilityValue` est FAUX pour Loop2 sur une Swamp).
# ⇒ le canal JUSTE est le canal dynamique. Ce repli n'existe que parce que `load_state(tiles=…)` est
# OPT-IN (case-102 §5.1) : un état non hydraté ne porte aucun effet de tuile, et la Swamp perdrait son
# -25 alors que le natif l'a TOUJOURS (l'ability de terrain le pose au setup de la bataille).
# `terrain_tile_effects` ne l'ajoute donc QUE si le canal dynamique ne l'a pas déjà rendu — jamais en
# double. `BlockEnteringUnits` n'y figure pas EXPRÈS : aucun poids `Default.TileEffects` ne le nomme
# (Loop1 le rejette sur `HasUtilityValue`), et le faire entrer dans les listes offline réveillerait le
# gate pathfinding non porté (#131, cf. case-102 §5.4).
TERRAIN_TILE_OWNED_EFFECTS: dict[str, tuple] = {
    "Swamp": ("Thorns_DefenseReduction",),
}


def terrain_tile_effects(terrain: str | None, dynamic=None) -> list:
    """Noms que le TERRAIN statique (`tileDefId`) apporte à la feuille TileEffects(10), en COMPLÉMENT du
    canal dynamique de l'appelant :

      * toujours — les abilities HÉBERGÉES (Loop2) : `TERRAIN_HOSTED_ABILITIES` ;
      * en repli — les effets que l'ability hébergée pose SUR LA TUILE (Loop1 :
        `TERRAIN_TILE_OWNED_EFFECTS`), et seulement ceux que `dynamic` ne porte PAS déjà.

    `dynamic` = les noms d'effets que l'appelant a lus sur l'entité-tuile (`state.effects.by_unit[tid]`,
    `tileMeta`/`ctx.effects_by_pos`, `scene.tile_effects_by_pos`). Le passer est ce qui rend le repli
    INOFFENSIF : sans lui un état hydraté compterait le -25 de la Swamp DEUX fois. Tous les call-sites
    qui disposent du canal dynamique DOIVENT le passer."""
    out = list(TERRAIN_HOSTED_ABILITIES.get(terrain or "", ()))
    have = set(dynamic or ())
    out += [n for n in TERRAIN_TILE_OWNED_EFFECTS.get(terrain or "", ()) if n not in have]
    return out


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


def _subject_trait_names(ctx: dict) -> tuple:
    """Les NOMS de traits du SUJET, dérivés des IDS que porte `ctx["unit_traits"]`.

    Même substrat, autre forme : `entity_trait_ids` est LUI-MÊME dérivé d'`entity_trait_names`
    (`engine/entities/traits/unit_trait.py`), donc la conversion est totale — aucun id ne peut
    sortir de l'enum. LOUDER-ON-BUG, comme le foyer d'autorité : un id hors enum LÈVE plutôt que
    de disparaître du gate."""
    return tuple(UnitTrait(int(t)).name for t in ((ctx or {}).get("unit_traits") or ()))


def _entity_is_immune_to_effect(effect_type, ctx: dict) -> bool:
    """`effectsDatabase.GetEffect(<effectType>).EntityIsImmuneToEffect(case.unit)` — les DEUX étages,
    mirror 1:1 (#175-e), lus dans
    `IdunBattle.AI.Utilities.DespoiledGroundUtility.u003CEvaluateMovementInStepsu003Ed__5$$MoveNext`
    et `IdunBattle.AI.Utilities.ContaminatedUtility.u003CEvaluateMovementInStepsu003Ed__4$$MoveNext`,
    qui l'appellent tous deux JUSTE APRÈS le gate `case.unit == null` et AVANT d'énumérer les effets
    de la tuile :

        IEffect eff = this.<+0x60>.GetEffect(<effectType>);     // IEffectsDatabase slot 0
        if (eff.EntityIsImmuneToEffect(case.unit)) yield break; // IEffect slot 40

    Les deux slots sont LUS, pas déduits : `IEffectsDatabase` n'a qu'UNE méthode
    (`GetEffect`, slot 0, 1 argument) et `IEffect` slot 40 = `EntityIsImmuneToEffect` (1 argument) —
    `data/symbols/<build>/metadata/interface_slots.tsv` + `global-metadata.dat`. Le champ `+0x60` est
    le paramètre `effectsDatabase` du `.ctor` des DEUX utilities (type DÉCLARÉ lu dans
    `frida/methods.tsv`).

    Le 2e étage est le foyer DÉJÀ PORTÉ `EffectFactory.effect_def(...).entity_is_immune_to_effect`
    (mirror d'`EffectsDatabase.Get` + du virtuel par classe) — le MÊME que consulte le gate de pose
    `IdunBattle.Operations.AddEffectOperation$$Execute`. Le rebrancher ici plutôt que de recâbler un
    prédicat de traits dans la feuille est ce qui évite un fork : c'est un seul nœud natif.

    IMPORT DIFFÉRÉ, classe **PORTEUR** (mesure : `python -c "import engine.entities.effects.factory"`
    dans un process FRAIS charge `engine.utilities.tile` — 102 modules `engine.*` —, donc hisser
    fermerait un cycle). Forme B (`import <module>` puis attribut) : un binding de module reste
    substituable, contrairement au `from X import nom`."""
    from ..entities.effects import factory as _fx
    return bool(_fx.EffectFactory.effect_def(int(effect_type), effect_type.name)
                .entity_is_immune_to_effect(_subject_trait_names(ctx)))


# ── Classes `IdunBattle.AI.Utilities.*Utility` (une par feuille ; corps DANS la méthode) ─────────────
class ElevationUtility(BaseUtility):
    """`ElevationUtility` (IdunBattle.AI.Utilities.ElevationUtility$$.ctor ; UtilityType.Elevation=9) ; `<d__8>.IdunBattle.AI.Utilities.ElevationUtility.u003CEvaluateMovementInStepsu003Ed__8$$MoveNext` :
        u = Multiplier × elev  (+ HighestElevation si elev == max) (+ LowestElevation si elev == min)
    BC : Multiplier=10, HighestElevation=10, LowestElevation=-5. `meta` requis (élévation tuile + max/min).
    ⚠ `elevation_max`/`elevation_min` = min/max sur le BOARD ENTIER, PAS le candidate-set : le natif
    `IdunBattle.AI.Utilities.ElevationUtility$$LoadRelevantTileElevations` (one-shot, garde this+0x68) énumère la collection de TOUS les
    tiles du board (composant board-singleton sur le World `this+0x10`, éléments = TileComponent, elev@+0x18)
    et calcule min@this+0x64 (seed 10) / max@this+0x60 (seed 0). Verdict re-expert (case-37) : ni unité, ni
    reachable, ni candidate-set. => la harness alimente min/max sur `elev_by_pos` COMPLET (tileMeta = board)."""
    UTILITY_TYPE = int(UtilityType.Elevation)  # 9

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
    """`SteppableUnitUtility` (IdunBattle.AI.Utilities.SteppableUnitUtility$$.ctor ; UtilityType.SteppableUnit=20) ; `<d__10>.IdunBattle.AI.Utilities.SteppableUnitUtility.u003CEvaluateMovementInStepsu003Ed__10$$MoveNext` :

        if (!TileExtensions.GetSteppableUnit(case.position.MainTile, ctx, out u))  return 0;
        if      (UnitExtensions.HasTriggeredAbility(u, 0x4d))  key = "SpikyStingOnMovementTile";
        else if (UnitExtensions.HasTriggeredAbility(u, 0x72))  key = "Landmine";
        else if (UnitExtensions.HasTrait(u, 0x41d))                        // UnitTrait.Decoy = 1053
             key = UnitExtensions.IsFriend(u, case.unit, ctx) ? "FriendlyDecoy" : "EnemyDecoy";
        else key = UnitExtensions.IsEnemy(u, case.unit, ctx) ? "EnemySteppableUnit"
                                                            : "FriendlySteppableUnit";
        return GetUtilityValue(key);

    `IdunBattle.Entities.TileExtensions$$GetSteppableUnit` = l'OCCUPANT de la tuile
    (`IdunBattle.Entities.UnitExtensions$$GetUnit` -> `TileContentComponent.IsFilled`, UNE entite par
    tuile) qui porte le trait `0x1b` = `UnitTrait.Steppable` (27) -- pas le trait `Decoy` : n'importe
    quel summon steppable (decoy GSC, mine haywire) arme la feuille.

    Les 5 cles sont LUES (#241, `probe_212_bc_key_literals.py` sur ce symbole), pas devinees. BC
    `Utilities.Default.SteppableUnit` : EnemySteppableUnit=50, FriendlySteppableUnit=-50,
    FriendlyDecoy=-50, EnemyDecoy=1. Les DEUX premieres branches sont mirrorees mais rendent 0 sur
    cette BC : `SpikyStingOnMovementTile` et `Landmine` n'y figurent PAS -- `GetUtilityValue` d'une
    cle absente rend `Fix64.FromInt(0)` (+ un log), exactement ce que fait `Weights.sub`. Elles
    restent portees parce qu'elles COURT-CIRCUITENT les suivantes : un steppable porteur de
    `TriggeredAbilityType.SpikySting` (77) / `LandMine` (114) vaut 0, pas -50.

    ⚠ Le natif n'utilise PAS le meme predicat des deux cotes : `IsFriend` pour la branche Decoy,
    `IsEnemy` pour l'autre. Ils sont complementaires tant que `case.unit != null` (les deux comparent
    `GetCurrentPlayer(a).id` a `GetCurrentPlayer(b).id`), d'ou les deux booleens distincts dans
    `meta.steppable` -- si `case.unit` etait nul, les deux rendraient False et les cles seraient
    `EnemyDecoy` / `FriendlySteppableUnit`. `meta.steppable` est pose par `apply_tile_attributes`."""
    UTILITY_TYPE = int(UtilityType.SteppableUnit)  # 20

    def evaluate(self, tile, meta, ctx, wt) -> float:
        st = (meta or {}).get("steppable")
        if not st:
            return 0.0
        trig = set(st.get("triggered") or ())
        if int(TriggeredAbilityType.SpikySting) in trig:            # 0x4d
            return wt.sub("SteppableUnit", "SpikyStingOnMovementTile")
        if int(TriggeredAbilityType.LandMine) in trig:              # 0x72
            return wt.sub("SteppableUnit", "Landmine")
        if st.get("is_decoy"):
            return wt.sub("SteppableUnit", "FriendlyDecoy" if st.get("is_friend") else "EnemyDecoy")
        return wt.sub("SteppableUnit",
                      "EnemySteppableUnit" if st.get("is_enemy") else "FriendlySteppableUnit")


class TileEffectsUtility(BaseUtility):
    """`TileEffectsUtility` (IdunBattle.AI.Utilities.TileEffectsUtility$$.ctor ; UtilityType.TileEffects=10) ; `<d__1>.IdunBattle.AI.Utilities.TileEffectsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` :
    Σ des poids BC `Default.TileEffects.<EffectName>` pour chaque effet présent SUR la tuile (le natif
    multiplie les status-effects par un facteur de durée ; non porté → poids brut). `meta.effects` requis."""
    UTILITY_TYPE = int(UtilityType.TileEffects)  # 10

    def evaluate(self, tile, meta, ctx, wt) -> float:
        effs = (meta or {}).get("effects") or []
        if not effs:
            return 0.0
        cat = wt.category("TileEffects")
        return float(sum(cat.get(e, 0) for e in effs if isinstance(cat.get(e), (int, float))))


class TemporaryTileUtility(BaseUtility):
    """`TemporaryTileUtility` (IdunBattle.AI.Utilities.TemporaryTileUtility$$.ctor ; UtilityType.TemporaryTile=14) ; `<d__1>.IdunBattle.AI.Utilities.TemporaryTileUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` :
    u = 0 ; si la tuile candidate est TEMPORAIRE → u -= Fix64(10000) (CONSTANTE, pas un poids BC ; le natif
    lit `tileData+0x2c` IsTemporary). L'IA évite fortement les tuiles temporaires. `meta.is_temporary`."""
    UTILITY_TYPE = int(UtilityType.TemporaryTile)  # 14

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
    """`UnitEffectsAdjacentUtility` (TypeDefIndex 12151 ; UtilityType.UnitEffectsAdjacent=11)."""
    UTILITY_TYPE = int(UtilityType.UnitEffectsAdjacent)  # 11
    _CAT = "UnitEffectsAdjacent"
    _ZONE = "adjacent"


class UnitEffectsSurroundingUtility(AUnitEffectsUtility):
    """`UnitEffectsSurroundingUtility` (TypeDefIndex 12152 ; UtilityType.UnitEffectsSurrounding=12)."""
    UTILITY_TYPE = int(UtilityType.UnitEffectsSurrounding)  # 12
    _CAT = "UnitEffectsSurrounding"
    _ZONE = "surrounding1"


class UnitEffectsRangedUtility(AUnitEffectsUtility):
    """`UnitEffectsRangedUtility` (TypeDefIndex 12153 ; UtilityType.UnitEffectsRanged=13)."""
    UTILITY_TYPE = int(UtilityType.UnitEffectsRanged)  # 13
    _CAT = "UnitEffectsRanged"
    _ZONE = "ranged2"


class CapturePointTileUtility(BaseUtility):
    """`CapturePointTileUtility` (IdunBattle.AI.Utilities.CapturePointTileUtility$$.ctor ; UtilityType.CapturePoint=25) ; IdunBattle.AI.Utilities.CapturePointTileUtility.u003CEvaluateMovementInStepsu003Ed__3$$MoveNext : sur tuile
    TERRITOIRE (flag tile+0x2e = HasTrait(2 summon)||HasTrait(13)) → flag(summon) →
    summons_dislike_capture_points(-300) ; sinon heroes_on_capture_points(+300). `meta.is_territory` + `ctx.unit_traits`.

    ⚠ case-205 — le gate natif n'est PAS `HasTrait(unit,2) || HasTrait(unit,13)` seul : le décompilé
    ouvre sur `if (case.unit == null) { if (case.parent != null) flag = TRUE; }`, c'est-à-dire
    `IdunBattle.AI.Utilities.UtilityMovementCase$$get_IsSpawning` INLINÉ. Sujet ABSENT + parent présent
    (le call-site `SortTilesByUtilityForSummon`) ⇒ le natif traite la tuile comme évaluée POUR UN SUMMON,
    donc `summons_dislike_capture_points`, et NON 0."""
    UTILITY_TYPE = int(UtilityType.CapturePoint)  # 25

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not (meta or {}).get("is_territory"):
            return 0.0
        flag = (bool((ctx or {}).get("is_spawning"))          # `case.unit == null && case.parent != null`
                or _has(ctx, "unit_traits", int(UnitTrait.Summon))      # HasTrait(unit, 2)
                or _has(ctx, "unit_traits", int(UnitTrait.Object)))     # HasTrait(unit, 13)
        key = "summons_dislike_capture_points" if flag else "heroes_on_capture_points"
        return wt.sub("CapturePoint", key)


class PowerUpTileUtility(BaseUtility):
    """`PowerUpTileUtility` (IdunBattle.AI.Utilities.PowerUpTileUtility$$.ctor ; UtilityType.PowerUp=27) ; IdunBattle.AI.Utilities.PowerUpTileUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext : -300 si l'occupant de la
    tuile EstPowerUp ET flag(trait 2||13). `meta.occupant_is_powerup` + `ctx.unit_traits`.
    Même gate que `CapturePointTileUtility`, `IsSpawning` INLINÉ compris (case-205) : sujet ABSENT +
    parent présent ⇒ flag TRUE."""
    UTILITY_TYPE = int(UtilityType.PowerUp)  # 27

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not (meta or {}).get("occupant_is_powerup"):
            return 0.0
        if not (bool((ctx or {}).get("is_spawning"))
                or _has(ctx, "unit_traits", int(UnitTrait.Summon))       # HasTrait(unit, 2)
                or _has(ctx, "unit_traits", int(UnitTrait.Object))):     # HasTrait(unit, 13)
            return 0.0
        return wt.sub("PowerUp", "summons_dislike_tiles_with_powerups")


class ContaminatedUtility(BaseUtility):
    """`ContaminatedUtility` (IdunBattle.AI.Utilities.ContaminatedUtility$$.ctor ; UtilityType.Contaminated=26) ; IdunBattle.AI.Utilities.ContaminatedUtility.u003CEvaluateMovementInStepsu003Ed__4$$MoveNext : -25 si la tuile porte
    un effet type 1244 (0x4dc) ET l'unité n'est pas IMMUNISÉE contre lui. `meta.tile_effect_type_ids`.

    Corps natif remis en C# depuis le décompilé (#175-e), dans SON ordre :

        if (case.unit == null) yield break;                                  // régime SPAWN
        if (effectsDatabase.GetEffect(Contaminated).EntityIsImmuneToEffect(case.unit)) yield break;
        foreach (e in EffectsOwnedComponent(case.Position.MainTile))
            if (EffectComponent(e).EffectType == 0x4dc) { u += GetUtilityValue("AffectedUnit"); break; }

    DEUX gates manquaient, et les deux sont dans la MÊME instruction du natif :

    * `case.unit == null` (`if (case+0x10 == 0) -> return false`, l'état 0 de la SM). La sœur
      `DespoiledGroundUtility` le portait déjà (case-205) ; celle-ci non — en régime SPAWN elle
      versait donc son -25 là où le natif n'émet AUCUN step.
    * l'IMMUNITÉ. `ctx.contaminated_excluded`, le nom que le port lui donnait, n'était peuplé par
      AUCUN des trois constructeurs de `ctx` : le gate était mort. Sa forme aussi était fausse —
      ce n'est pas un booléen par-décision mais l'appel à DEUX étages `_entity_is_immune_to_effect`,
      dont le second est le virtuel `ContaminatedEffect$$EntityIsImmuneToEffect`
      (`ContagionsOfNurgle` | `IsMechanical` | `HasTrait(Immune) && CanBeImmuneTo(=true)`)."""
    UTILITY_TYPE = int(UtilityType.Contaminated)  # 26

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if (ctx or {}).get("is_spawning"):            # `if (case.unit == null) yield break;`
            return 0.0
        if _entity_is_immune_to_effect(EffectType.Contaminated, ctx):    # IEffect slot 40
            return 0.0
        if int(EffectType.Contaminated) not in _eff_ids(meta, "tile_effect_type_ids"):   # 0x4dc
            return 0.0
        return wt.sub("Contaminated", "AffectedUnit")


class MoltenForm_TilesUtility(BaseUtility):
    """`MoltenForm_TilesUtility` (IdunBattle.AI.Utilities.MoltenForm_TilesUtility$$.ctor ; UtilityType.MoltenForm=24) ; IdunBattle.AI.Utilities.MoltenForm_TilesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext : si l'unité a la
    triggered ability 1221 (0x4c5) → +25 si tuile effet type 5 (ResistFireTiles) ; -25 si type 10
    (AvoidHealingTiles). `ctx.unit_triggered_abilities` + `meta.tile_effect_type_ids`."""
    UTILITY_TYPE = int(UtilityType.MoltenForm)  # 24

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not _has(ctx, "unit_triggered_abilities", int(TriggeredAbilityType.MoltenForm)):  # 0x4c5
            return 0.0
        ids = _eff_ids(meta, "tile_effect_type_ids")
        u = 0.0
        if int(EffectType.Fire) in ids:                    # tile-effect 5 (ResistFireTiles)
            u += wt.sub("MoltenForm", "MoltenForm_ResistFireTiles")
        if int(EffectType.FirstAidHeal) in ids:            # tile-effect 10 (AvoidHealingTiles)
            u += wt.sub("MoltenForm", "MoltenForm_AvoidHealingTiles")
        return u


class TilePendingBlockableSummonUtility(BaseUtility):
    """`TilePendingBlockableSummonUtility` (IdunBattle.AI.Utilities.TilePendingBlockableSummonUtility$$.ctor ; UtilityType.TilePendingBlockableSummon=15) ; IdunBattle.AI.Utilities.TilePendingBlockableSummonUtility.u003CEvaluateMovementInStepsu003Ed__3$$MoveNext :
    Σ sur les summons en attente de type 1094 (0x446) sur la tuile : +25 si owner ENNEMI, -25 si AMI.
    `meta.pending_summons=[{type_id,owner_is_enemy}]`."""
    UTILITY_TYPE = int(UtilityType.TilePendingBlockableSummon)  # 15

    def evaluate(self, tile, meta, ctx, wt) -> float:
        ps = (meta or {}).get("pending_summons") or []
        we = wt.sub("TilePendingBlockableSummon", "EnemySummon")
        wf = wt.sub("TilePendingBlockableSummon", "FriendlySummon")
        return float(sum((we if e.get("owner_is_enemy") else wf)
                         for e in ps
                         if e.get("type_id") == int(EffectType.CallRipperSwarms_PendingSummon)))


class EnvEndBombardmentUtility(BaseUtility):
    """`EnvEndBombardmentUtility` (IdunBattle.AI.Utilities.EnvEndBombardmentUtility$$.ctor ; UtilityType.EnvEndBombardment=32) ; IdunBattle.AI.Utilities.EnvEndBombardmentUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext : tuile ciblée
    par l'effet 1359 (0x54f) → -30 ; sinon par 1360 (0x550) → -60 (×2). `meta.effect_target_ids`."""
    UTILITY_TYPE = int(UtilityType.EnvEndBombardment)  # 32

    def evaluate(self, tile, meta, ctx, wt) -> float:
        ids = _eff_ids(meta, "effect_target_ids")
        w = wt.sub("EnvEndBombardment", "EnvEndBombardment_TileToAvoid")
        if int(EffectType.EnvEndBombardment_Incoming) in ids:      # 0x54f
            return w
        if int(EffectType.EnvEndBombardment) in ids:               # 0x550
            return w * 2
        return 0.0


class DespoiledGroundUtility(BaseUtility):
    """`DespoiledGroundUtility` (IdunBattle.AI.Utilities.DespoiledGroundUtility$$.ctor ; UtilityType.DespoiledGround=29) ; IdunBattle.AI.Utilities.DespoiledGroundUtility.u003CEvaluateMovementInStepsu003Ed__5$$MoveNext : si tuile
    tile-effect type 1476 (0x5c4) → trait 2026 (Chaos) → ChaosAffectedUnit(-5) ; trait 26 ou 1006
    (Imperial/Xenos) → ImperialAndXenosAffectedUnit(-25). `meta.tile_effect_type_ids` + `ctx.unit_traits`.
    Première instruction du corps natif : `if (case.unit == null) yield break;` — sujet ABSENT ⇒ AUCUN
    step émis, donc 0 (case-205).

    ⚠ SECONDE instruction, non portée jusqu'à #175-e : le gate d'IMMUNITÉ, à DEUX étages —
    `effectsDatabase.GetEffect(DespoiledGround).EntityIsImmuneToEffect(case.unit)` ⇒ `yield break`.
    Il vient AVANT l'énumération des effets de la tuile, et il MORD : `DespoiledGroundEffect` ne
    surcharge PAS `EntityIsImmuneToEffect` (c'est le corps générique) mais surcharge bien
    `get_CanBeImmuneTo` à **true**, si bien que le prédicat vaut `HasTrait(case.unit, Immune)`.
    Sans lui, le port SUR-PÉNALISE toute unité immunisée (-5 Chaos / -25 Imperial-Xenos là où le
    natif rend 0). Détail de la lecture : `_entity_is_immune_to_effect` et la docstring de
    `engine/entities/effects/loki/status.py::DespoiledGroundEffect`."""
    UTILITY_TYPE = int(UtilityType.DespoiledGround)  # 29

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if (ctx or {}).get("is_spawning"):            # `if (case.unit == null) yield break;`
            return 0.0
        if _entity_is_immune_to_effect(EffectType.DespoiledGround, ctx):    # IEffect slot 40
            return 0.0
        if int(EffectType.DespoiledGround) not in _eff_ids(meta, "tile_effect_type_ids"):  # 0x5c4
            return 0.0
        if _has(ctx, "unit_traits", int(UnitTrait.Chaos)):                        # 2026
            return wt.sub("DespoiledGround", "ChaosAffectedUnit")
        if _has(ctx, "unit_traits", int(UnitTrait.Imperial)) \
                or _has(ctx, "unit_traits", int(UnitTrait.Xenos)):                # 26 / 1006
            return wt.sub("DespoiledGround", "ImperialAndXenosAffectedUnit")
        return 0.0


class SummonDislikeDoorOpeningUtility(BaseUtility):
    """`SummonDislikeDoorOpeningUtility` (IdunBattle.AI.Utilities.SummonDislikeDoorOpeningUtility$$.ctor ; UtilityType.SummonDislikeDoorOpening=30) ; IdunBattle.AI.Utilities.SummonDislikeDoorOpeningUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext :
    -50 si l'unité est "affected" (AI-controlled OU human+trait 2) ET la tuile est une PORTE FERMÉE.
    `meta.door={linked,closed}` + `ctx.unit_is_ai/unit_traits`.

    ⚠ case-205 — le gate natif complet est `case.parent != null || !IsControlledByHumanPlayer(case.unit)
    || HasTrait(case.unit, 2)` : le test de PARENT vient EN PREMIER et court-circuite le reste. Sur tous
    les call-sites portés, `parent != null` ⟺ `SortTilesByUtilityForSummon` (les call-sites de charge
    passent un `ownerSel` NUL), donc `ctx.is_spawning` le reproduit exactement."""
    UTILITY_TYPE = int(UtilityType.SummonDislikeDoorOpening)  # 30

    def evaluate(self, tile, meta, ctx, wt) -> float:
        door = (meta or {}).get("door") or {}
        if not (door.get("linked") and door.get("closed")):
            return 0.0
        affected = (bool((ctx or {}).get("is_spawning"))          # `case.parent != null`
                    or bool((ctx or {}).get("unit_is_ai"))
                    or _has(ctx, "unit_traits", int(UnitTrait.Summon)))   # HasTrait(unit, 2)
        if not affected:
            return 0.0
        return wt.sub("SummonDislikeDoorOpening", "Dislike")


class HeroDoorOpeningUtility(BaseUtility):
    """`HeroDoorOpeningUtility` (IdunBattle.AI.Utilities.HeroDoorOpeningUtility$$.ctor ; UtilityType.HeroLikeDoorOpening=31) ; IdunBattle.AI.Utilities.HeroDoorOpeningUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext : UNIQUEMENT
    unité hero (trait 16). PAS de poids BC (constantes). branche A (player flag==0) : -50 si la tuile est
    une porte fermée. branche B (flag!=0) : (10 - cost)*10, cost = min coût CHEMIN vers la porte fermée la
    plus proche. `ctx.player_door_mode` + `meta.door` + `meta.hero_door_nearest_cost`.
    Gate natif en tête : `if (case.unit == null || !HasTrait(case.unit, 0x10)) yield return 0;` — sujet
    ABSENT ⇒ 0 (case-205)."""
    UTILITY_TYPE = int(UtilityType.HeroLikeDoorOpening)  # 31

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if (ctx or {}).get("is_spawning"):            # `case.unit == null`
            return 0.0
        if not _has(ctx, "unit_traits", int(UnitTrait.Hero)):     # HasTrait(case.unit, 0x10)
            return 0.0
        if (ctx or {}).get("player_door_mode", 0) == 0:
            door = (meta or {}).get("door") or {}
            return -50.0 if (door.get("linked") and door.get("closed")) else 0.0
        cost = (meta or {}).get("hero_door_nearest_cost")
        if cost is None:
            return 0.0
        return (10 - cost) * 10.0


class Phantasm_AvoidFriendlyPhantasmUtility(BaseUtility):
    """`Phantasm_AvoidFriendlyPhantasmUtility` (IdunBattle.AI.Utilities.Phantasm_AvoidFriendlyPhantasmUtility$$.ctor ; UtilityType.Phantasm_AvoidFriendlyPhantasm=61) ;
    IdunBattle.AI.Utilities.Phantasm_AvoidFriendlyPhantasmUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext : -40 si la tuile porte l'effet Phantasm 1279 (0x4ff) ET un phantasme AMI est adjacent.
    `meta.phantasm_friendly_adjacent`."""
    UTILITY_TYPE = int(UtilityType.Phantasm_AvoidFriendlyPhantasm)  # 61

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not (meta or {}).get("phantasm_friendly_adjacent"):
            return 0.0
        return wt.sub("Phantasm_AvoidFriendlyPhantasm", "Phantasm_AvoidFriendlyPhantasm")


class EchoesFromTheWarp_FriendliesAvoidGhostUtility(BaseUtility):
    """`EchoesFromTheWarp_FriendliesAvoidGhostUtility` (IdunBattle.AI.Utilities.EchoesFromTheWarp_FriendliesAvoidGhostUtility$$.ctor ; UtilityType.=58) ; IdunBattle.AI.Utilities.EchoesFromTheWarp_FriendliesAvoidGhostUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext : +10 si
    la tuile POSSÈDE (owner) l'effet ghost 1284 (0x504) ET le ghost ami est adjacent. `meta.ghost_friendly_adjacent`."""
    UTILITY_TYPE = int(UtilityType.EchoesFromTheWarp_FriendliesAvoidGhost)  # 59

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not (meta or {}).get("ghost_friendly_adjacent"):
            return 0.0
        return wt.sub("EchoesFromTheWarp_FriendliesAvoidGhost", "GhostTile")


class AttractMechanicalsUtility(BaseUtility):
    """`AttractMechanicalsUtility` (IdunBattle.AI.Utilities.AttractMechanicalsUtility$$.ctor ;
    UtilityType.DoctrinaImperatives_AttractMechanicals) ;
    `IdunBattle.AI.Utilities.AttractMechanicalsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext`,
    relu ligne a ligne sur le build courant (#477-r31) :

        x = Fix64(0);
        if (case.Unit == null)                            yield break;        // aucun yield
        if (!UnitExtensions.HasTrait(case.Unit, 5))       yield return x;     // Mechanical
        units = query.<slot 0x7a = GetAdjacentUnits, 4 args>(case.MovementTile, case.Unit, 0, 0);
        if (Enumerable.Any(units, f => HasActiveAbility(f, 0x45e) && f != case.Unit))
            x += GetUtilityValue("Marshal_AttractMechanicals");               // BC = 10
        yield return x;

    `0x45e` = 1118 = `ActiveAbilityType.DoctrinaImperatives`, l'ACTIVE du Skitarii Marshal
    (`admecMarshall`). Le litteral BC est RESOLU (`probe_212_bc_key_literals.py --symbol ...`) :
    `Utilities.Default.DoctrinaImperatives_AttractMechanicals.Marshal_AttractMechanicals` = 10.

    ⚠ `Any`, pas `Count` : le terme vaut **+10 AU PLUS UNE FOIS**, quel que soit le nombre de
    Marshals adjacents -- c'est ce qui le distingue du `+10 x n` de `RadSaturationPlaybook`.

    ⚠ LE CAMP : **les AMIS**, pas les deux camps -- cf. `_attract_mechanicals_neighbor`, qui porte
    la lecture du filtre (`friendsOf = case.Unit` dans `CountOrGetUnitsOnTiles`). Le nom du slot
    (`GetAdjacentUnits`) ne dit PAS le camp ; les arguments si.

    Gate + donnee : `ctx.unit_traits` + `meta.attract_mechanicals_neighbor`."""
    UTILITY_TYPE = int(UtilityType.DoctrinaImperatives_AttractMechanicals)
    #: FOYER UNIQUE des deux moities de la cle BC, pour que le probe et la garde citent la MEME
    #: chose que le code evalue (une chaine recopiee ailleurs ne suit pas un renommage de build).
    WEIGHT_CATEGORY = "DoctrinaImperatives_AttractMechanicals"
    WEIGHT_KEY = "Marshal_AttractMechanicals"

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not _has(ctx, "unit_traits", int(UnitTrait.Mechanical)):    # HasTrait(case.Unit, 5)
            return 0.0
        if not (meta or {}).get("attract_mechanicals_neighbor"):       # Enumerable.Any(...)
            return 0.0
        return wt.sub(self.WEIGHT_CATEGORY, self.WEIGHT_KEY)


class AttractToDecoysUtility(BaseUtility):
    """`AttractToDecoysUtility` (IdunBattle.AI.Utilities.AttractToDecoysUtility$$.ctor ; UtilityType.DecoysAndMisdirection_AttractToDecoys=65) ;
    IdunBattle.AI.Utilities.AttractToDecoysUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext :

        if (case.unit == null)                                       yield break;
        if (!UnitExtensions.HasFaction(case.unit, 0xf))              yield break;  // Genestealers
        if (!TileExtensions.HasSteppableUnit(case.CasterTile, ctx))  yield break;
        if (TileExtensions.GetSteppableUnit(case.CasterTile, ctx, out u)
            && UnitExtensions.IsEnemy(u, case.unit, ctx))            yield break;
        foreach (u in ctx.GetAllAliveUnits())                                      // slot 0x88
            if (UnitExtensions.IsFriend(u, case.unit, ctx)
                && UnitExtensions.HasTriggeredAbility(u, 0x518))                   // 1304
                yield return GetUtilityValue("DecoysAndMisdirection_FriendlyGSCLikeDecoys");  // 75

    Trois faits que le nom des cles ne dit pas, et qui sont LUS au decompile (#241) :

    * le gate de tuile porte sur `Steppable` (27), PAS sur `Decoy` (1053) -- il suffit qu'un summon
      steppable non ennemi soit sur la tuile candidate ;
    * la boucle de comptage n'a AUCUN filtre de position : c'est `GetAllAliveUnits` (le slot 0x88 de
      l'interface de query, identifie par `IdunBattle.Entities.Selectors.AllAliveUnitsSelector$$Select`
      et `IdunBattle.AI.Playbook.BasePlaybook$$GetAllEnemies`), donc TOUTE la bataille -- le compte
      est CONSTANT sur la decision, seul le gate varie par tuile ;
    * `IsFriend(u, case.unit)` compare les playerId : le MOVER LUI-MEME satisfait le predicat, donc il
      compte s'il porte 1304 (aucune exclusion de self, contrairement aux feuilles `AUnitEffects*`).

    `HasFaction` compare `System.Enum.ToString(UnitFaction)` au `FactionComponent+0x30` (une CHAINE) ;
    le pendant offline est le `FactionId` gameconfig, converti en valeur d'enum par
    `engine.entities.unit_faction`. `ctx.unit_faction` + `meta.decoy_gate` + `meta.decoy_friend_count`
    (les deux `meta` sont poses par `apply_tile_attributes`)."""
    UTILITY_TYPE = int(UtilityType.DecoysAndMisdirection_AttractToDecoys)  # 65

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if (ctx or {}).get("unit_faction") != int(UnitFaction.Genestealers):   # HasFaction(.., 0xf)
            return 0.0
        if not (meta or {}).get("decoy_gate"):
            return 0.0
        n = (meta or {}).get("decoy_friend_count") or 0
        return n * wt.sub("DecoysAndMisdirection_AttractToDecoys",
                          "DecoysAndMisdirection_FriendlyGSCLikeDecoys")


class KustomForceFieldUtility(BaseUtility):
    """`KustomForceFieldUtility` (IdunBattle.AI.Utilities.KustomForceFieldUtility$$.ctor ; UtilityType.KustomForceField=21) ; base ATriggeredAbilityUtility.d__3
    IdunBattle.AI.Utilities.ATriggeredAbilityUtility.u003CEvaluateMovementInStepsu003Ed__3$$MoveNext : +20 × count(amis ADJACENTS R1 avec triggered ability 1102). `meta.ability_friend_counts[1102]`."""
    UTILITY_TYPE = int(UtilityType.KustomForceField)  # 21

    def evaluate(self, tile, meta, ctx, wt) -> float:
        return (_ability_count(meta, int(TriggeredAbilityType.KustomForceField))
                * wt.sub("KustomForceField", "AdjacentFriendly"))


class DefenderOfTheGreaterGoodUtility(BaseUtility):
    """`DefenderOfTheGreaterGoodUtility` (IdunBattle.AI.Utilities.DefenderOfTheGreaterGoodUtility$$.ctor ; UtilityType.DefenderOfTheGreaterGood=22) ; IdunBattle.AI.Utilities.ATriggeredAbilityUtility.u003CEvaluateMovementInStepsu003Ed__3$$MoveNext :
    +25 × count(amis R1, ou R2 si faction 9, avec ability 1155). Gate : arme à distance.
    `ctx.unit_has_ranged_weapon` + `meta.ability_friend_counts[1155]`."""
    UTILITY_TYPE = int(UtilityType.DefenderOfTheGreaterGood)  # 22

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if not (ctx or {}).get("unit_has_ranged_weapon"):
            return 0.0
        return (_ability_count(meta, int(TriggeredAbilityType.DefenderOfTheGreaterGood))
                * wt.sub("DefenderOfTheGreaterGood", "PerUnitWithAbilityInRange"))


class SaviorProtocolsUtility(BaseUtility):
    """`SaviorProtocolsUtility` (IdunBattle.AI.Utilities.SaviorProtocolsUtility$$.ctor ; UtilityType.SaviorProtocols=23) ; IdunBattle.AI.Utilities.ATriggeredAbilityUtility.u003CEvaluateMovementInStepsu003Ed__3$$MoveNext : +20 × count(amis
    ADJACENTS R1 avec ability 1120). Gate : faction 9 ET n'a pas l'ability 1120. `ctx.unit_faction/
    unit_triggered_abilities` + `meta.ability_friend_counts[1120]`."""
    UTILITY_TYPE = int(UtilityType.SaviorProtocols)  # 23

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if (ctx or {}).get("unit_faction") != int(UnitFaction.Tau) \
                or _has(ctx, "unit_triggered_abilities", int(TriggeredAbilityType.SaviorProtocols)):
            return 0.0
        return (_ability_count(meta, int(TriggeredAbilityType.SaviorProtocols))
                * wt.sub("SaviorProtocols", "PerUnitWithAbilityInRange"))


class MoveTowardsUnitUtility(BaseUtility):
    """`MoveTowardsUnitUtility` (IdunBattle.AI.Utilities.MoveTowardsUnitUtility$$.ctor ; base) ; `IdunBattle.AI.Utilities.MoveTowardsUnitUtility.u003CEvaluateMovementInStepsu003Ed__15$$MoveNext` : score = poids("PerTileDistance")
    × hexdist(candidate, cible) ; cible = unité ayant l'ability/effet `_ABILITY_ID`. distance = HEX (cube ;
    fournie par `meta.movetowards_hexdist[_ABILITY_ID]`). `_TRAIT_GATE` (None = pas de gate). Corps PARTAGE
    par les 2 sous-classes (BioMinefield, MasterOfTheTutelaries) qui parametrent `_CAT`/`_ABILITY_ID`/`_TRAIT_GATE`.

    ⚠⚠ **LE NOM `movetowards_hexdist` MENT, ET LE CLASSEMENT « derivable OFFLINE des positions,
    sans RPC » DE `case-175` §4 EST REFUTE (#175-r).** La distance n'est PAS hexagonale :
    `IdunBattle.AI.Utilities.MoveTowardsUnitUtility$$GetMinDistanceToTarget`, relu au decompile,
    fait

        min = null;                                                  // Nullable<int>
        foreach (tile in EntityExtensions.IterateTiles(target, State))
            { p = this.<+0x28>.<IPathfinders slot 4 = GetPath, 5 params>(1, unit, unitTile, tile, 0);
              if (p != null && p.<+0x18> < min) min = p.<+0x18>; }
        return min;

    ⚠ **RE-LU ET CORRIGE (#175-r1, build `rnca9r7q6c`) -- la version precedente de ce paragraphe se
    trompait sur les TROIS points qui commandent le port :**

      1. **Le service n'est PAS `MovementQuery`** : `this+0x28` porte l'interface du champ
         `MovementQuery+0x20`, et `data/symbols/<build>/metadata/interface_slots.tsv` la nomme --
         `IPathfinders`, dont le slot 4 est la surcharge `GetPath` a **5** parametres. Elle est
         dispatchee par `IdunBattle.Entities.Pathfinding.Pathfinders$$GetPath` vers `IPathfinder`
         slot 3 = `IdunBattle.Entities.Pathfinding.BasePathfinder$$FindPath`.
      2. **Le litteral `1` est `PathfinderType.IgnoreTerrain`, pas `Walk`** (mirror
         `engine/entities/distance_type.py` / `enums.tsv` : `0=Walk, 1=IgnoreTerrain, 2=Beeline`).
         Donc « murs et occupants compris » etait FAUX :
         `IdunBattle.Entities.Pathfinding.IgnoreTerrainPathfinder$$IsValidPathNode` teste
         `IsWalkable(next) && |dElev| <= 1` et **aucun occupant** -- l'occupance n'entre que par le
         COUT (`WeightCost = 10 + IsFilled`).
      3. **`+0x18` est `List<T>._size`, c.-a-d. `Count`** (meme lecture que
         `IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo` sur le meme retour), et
         `BasePathfinder$$FindPath` rend la liste extremites INCLUSES : **`Count == aretes + 1`**.
         Un off-by-one y coute une tuile entiere de poids (-100 pour BioMinefield).

    ⚠ **Et la boucle `IterateTiles` DEGENERE a UNE iteration ici** : l'appelant passe
    `EntityExtensions$$GetMainTile(target, State)`, donc une TileEntity, et la branche « l'entite EST
    une tuile » de `EntityExtensions.u003CIterateTilesu003Ed__17$$MoveNext` fait `yield entity; break`.
    Ce n'est PAS un min sur une empreinte (ce regime-la est celui de
    `MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy`, qui passe l'UNITE).

    La CIBLE ne se derive pas non plus d'une position : `<EvaluateMovementInSteps>d__15` balaie
    `Query.<slot 0x89 = GetAllAliveUnits>(null)` puis, selon que `UnitIdentifierAbilityOrEffect()`
    porte une ABILITY ou un EFFET, teste `HasActiveAbility`/`HasTriggeredAbility` ou resout les
    porteurs de l'effet ; puis DEUX voies, tranchees par `get_EffectSourceMustBeParent()` :
      * EFFET + `EffectSourceMustBeParent` -> `GetParent(case.Unit)` puis le **PREMIER** porteur dont
        `EffectComponent.SourceUnitId == parent.Id` (`break`) ;
      * sinon -> le **DERNIER** match de `get_Friends() ? IsFriend : IsEnemy` (la boucle n'a **pas**
        de `break` : l'ordre de `GetAllAliveUnits` MORD ici, contrairement aux sites ou seule une
        egalite en depend).
    Et `get_OnlyUnitsWithAny()` ne rend pas 0 quand il refuse : l'iterateur **ne yielde RIEN**
    (numeriquement equivalent a 0 dans la somme composite).

    ETAT DU PORT : **PRODUIT depuis #175-r1** -- `apply_tile_attributes` pose
    `meta["movetowards_pathdist"]` (cle RENOMMEE : l'ancienne `movetowards_hexdist` mentait, et le
    renommage se fait AVEC le producteur, comme annonce). Le producteur est
    `_movetowards_pathdist_by_pos` ; la distance vient de
    `engine.entities.pathfinding.ignore_terrain_pathfinder.get_path_node_counts_by_pos`, jumeau en
    domaine POSITION du moteur `Board` deja confronte (180/180 contre `pathDistToEnemies`).

    LES TROIS VIRTUELS QUI PARAMETRENT LE CORPS, et leur valeur PAR SOUS-CLASSE. Ils sont LUS dans
    les DECLARATIONS Il2CppDumper (`sources_win`), corroborees par les tailles d'instance de
    `data/symbols/<build>/frida/classes.tsv` -- `MoveTowardsUnitUtility` = 112 (0x70), donc le
    `+0x70` ecrit par CHAQUE `.ctor` est un champ **DE LA SOUS-CLASSE**, pas un champ partage :

      | classe | taille | `+0x70` | `+0x78` |
      |---|--:|---|---|
      | `BioMinefield_MoveTowardsTargetUtility` | 120 | `EffectSourceMustBeParent = true` | -- |
      | `MasterOfTheTutelaries_MoveTowardsTargetUtility` | 128 | `Friends = true` | `OnlyUnitsWithAny = [Chaos, Daemon]` |

    Ce qu'une sous-classe n'override PAS retombe sur le backing field de la base, JAMAIS ecrit :
    `Friends = false` et `OnlyUnitsWithAny = null` pour BioMinefield, `EffectSourceMustBeParent =
    false` pour MasterOfTheTutelaries. Lire `+0x70` comme un champ unique ferait croire les deux
    drapeaux vrais des deux cotes."""
    _CAT: str = ""
    _ABILITY_ID: int = -1
    _TRAIT_GATE: "set | None" = None
    #: Quel des TROIS `Nullable` de l'`AbilityOrEffect` rendu par `UnitIdentifierAbilityOrEffect()`
    #: est renseigne (`IdunBattle.Core.AbilityOrEffect` : `_activeAbility@+0x00`,
    #: `_triggeredAbility@+0x08`, `_effect@+0x10`). LU dans le `.ctor` : le `mov edx, <imm>` qui
    #: precede l'appel a la surcharge d'`op_Implicit`, et c'est la SURCHARGE qui nomme la famille
    #: (`set_ActiveAbility` vs `set_Effect`), jamais l'ordinal.
    _IDENTIFIER_KIND: str = "active"
    #: `get_Friends()` -- la CIBLE est-elle cherchee parmi les AMIS (sinon les ennemis) ?
    _FRIENDS: bool = False
    #: `get_EffectSourceMustBeParent()` -- branche EFFET seulement.
    _EFFECT_SOURCE_MUST_BE_PARENT: bool = False

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if self._TRAIT_GATE is not None:
            if not (set((ctx or {}).get("unit_traits") or ()) & self._TRAIT_GATE):
                return 0.0
        dd = (meta or {}).get("movetowards_pathdist") or {}
        d = dd.get(self._ABILITY_ID)
        if d is None:
            d = dd.get(str(self._ABILITY_ID))
        if d is None:
            return 0.0
        return d * wt.sub(self._CAT, "PerTileDistance")


class BioMinefield_MoveTowardsTargetUtility(MoveTowardsUnitUtility):
    """`BioMinefield_MoveTowardsTargetUtility` (IdunBattle.AI.Utilities.BioMinefield_MoveTowardsTargetUtility$$.ctor ; UtilityType.=62) : -100 × pathdist(candidate,
    cible effet 1315). Pas de gate trait.

    Parametres LUS au `.ctor` (#175-r1) et pas encore consommes par le port, faute de producteur :
    `UnitIdentifierAbilityOrEffect` est pose par `set_Effect` (donc la famille est bien
    `EffectType`, ce que le nom de classe ne prouvait pas), et **`EffectSourceMustBeParent = true**`
    (champ `+0x70` de CETTE classe) -> la cible est le porteur de 1315 dont
    `EffectComponent.SourceUnitId` est le PARENT du mover, PREMIER match. `GetParent == null` -> 0.

    ⚠ La branche EFFET part de `IBattleQuery.<slot 192 = GetActiveEffects>(1315, null)` (slot LU
    dans `data/symbols/<build>/metadata/interface_slots.tsv`), donc des effets **ACTIFS** -- et elle
    n'exclut PAS `case.Unit` de ses candidats, contrairement a la branche ABILITY. Le re-test
    `GetOwnedEffect(u, State, 1315)`, lui, ne filtre PAS sur l'activite (relu : il itere
    l'`EffectsOwnedComponent` et compare `EffectComponent.EffectType@+0x58`, rien d'autre)."""
    UTILITY_TYPE = int(UtilityType.BioMinefield_MoveTowardsTarget)  # 62
    _CAT = "BioMinefield_MoveTowardsTarget"
    _ABILITY_ID = int(EffectType.BioMinefield_Target)  # 1315 (effet marqueur de cible ; #158, absent d'ActiveAbilityType)
    _TRAIT_GATE = None
    _IDENTIFIER_KIND = "effect"          # `set_Effect(0x523 = 1315)`, LU au `.ctor`
    _FRIENDS = False                     # non override -> backing field de la base, jamais ecrit
    _EFFECT_SOURCE_MUST_BE_PARENT = True  # `+0x70` de CETTE classe (taille 120 vs base 112)


class MasterOfTheTutelaries_MoveTowardsTargetUtility(MoveTowardsUnitUtility):
    """`MasterOfTheTutelaries_MoveTowardsTargetUtility` (IdunBattle.AI.Utilities.MasterOfTheTutelaries_MoveTowardsTargetUtility$$.ctor ; UtilityType.=63) : -20 × pathdist(candidate,
    cible 1096). Gate trait : l'unité a 2026 ou 1019.

    ⚠ Le champ `+0x70` vaut `1` dans les DEUX sous-classes et n'y designe PAS la meme chose (#175-r1,
    tranche par les noms de champs du dump, jamais par l'offset) : ici c'est **`Friends = true`** --
    la cible est un AMI porteur de l'ACTIVE 1096 (l'invocateur), DERNIER match du balayage
    `GetAllAliveUnits` ; chez `BioMinefield` c'est `EffectSourceMustBeParent`. Ecrire « ennemi » par
    symetrie avec l'autre feuille inverserait le signe du gradient sans rien casser de visible.
    L'identifiant est pose par `set_ActiveAbility` (famille `ActiveAbilityType`, LU au `.ctor`)."""
    UTILITY_TYPE = int(UtilityType.MasterOfTheTutelaries_MoveTowardsTarget)  # 63
    _CAT = "MasterOfTheTutelaries_MoveTowardsTarget"
    _ABILITY_ID = int(ActiveAbilityType.MasterOfTheTutelaries)  # 1096 (#158 : nom classe matche Active, PAS EffectType.KustomForceField/Triggered.SoulHunger)
    # #270-r1-r1 : le champ s'appelle `_TRAIT_GATE` et la docstring dit « Gate trait » -- ce sont
    # des `UnitTrait` (2026 = Chaos, 1019 = Daemon), pas des ids d'ability.
    _TRAIT_GATE = {UnitTrait.Chaos,      # 2026 = 0x7ea, LU dans le `.ctor` (List<UnitTrait> @+0x78)
                   UnitTrait.Daemon}     # 1019 = 0x3fb, idem
    _IDENTIFIER_KIND = "active"          # `set_ActiveAbility(0x448 = 1096)`, LU au `.ctor`
    _FRIENDS = True                      # `+0x70` de CETTE classe (taille 128 vs base 112)
    _EFFECT_SOURCE_MUST_BE_PARENT = False  # non override -> backing field de la base, jamais ecrit


class TriggeredAbilitiesUtility(BaseUtility):
    """`TriggeredAbilitiesUtility` (`.IdunBattle.AI.Utilities.TriggeredAbilitiesUtility$$.ctor` ; UtilityType.TriggeredAbilities=2) ;
    `<EvaluateMovementInSteps>IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext` : DISPATCHER — itère les abilities DE L'UNITÉ
    QUI BOUGE (`case.unit@0x10` → AbilitiesComponent), `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook(abilityType)` (singleton par type, null → skip), Σ des `CalculateMovementUtilityInSteps` (famille
    `AdjacentUnitPreferenceTriggeredAbilityPlaybook` : `engine/playbook/adjacent_unit_preference.py`).
    `ctx.unit_triggered_abilities` (kit DÉCLENCHÉ du mover) + `ctx.friend_positions` (allies vivants
    self-exclu = `ctx.fpos`). Cf. case-36 (909 s4/s19 : 30/90).

    ⚠ SOURCE DU KIT — les trois producteurs du `ctx` lisent tous l'`AbilitiesComponent` RÉEL depuis
    #456-r1, plus le kit gameconfig par `visualId` : `tile_leaf_ctx` par `ctx.live_triggered_ability_ids`
    (#304), `runner_tile_leaf_ctx` et `scene_tile_leaf_ctx` par le substrat d'ENTITÉ
    `entity_triggered_ability_ids(UnitContext)` (seedé par `snapshot._load_triggered_abilities`).
    Sans canal, les trois retombent sur le gameconfig — tri-état, pas dégradation silencieuse.

    ⚠ case-205 — tout le corps natif est gardé par `if (case.unit != null) { … }` ; sujet ABSENT ⇒ le
    seul step émis est le `u = Fix64.FromInt(0)` initial. C'est le régime du call-site SUMMON
    (`SortTilesByUtilityForSummon`), et c'est bien **0** — pas un dispatch sur une unité de repli."""
    UTILITY_TYPE = int(UtilityType.TriggeredAbilities)  # 2

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if (ctx or {}).get("is_spawning"):            # `if (case.unit != null)` du natif — sujet ABSENT
            return 0.0
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
                                 target_uid: int, attack_tile, prediction=None) -> float:
        """Face ATTACK du dispatcher — `<EvaluateAttackInSteps>IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateAttackInStepsInternalu003Ed__3$$MoveNext` (feuille 2
        du composite Damage(35), #45-s18) : itère les abilities déclenchées de l'ATTAQUANT (kit
        COMPLET passifs+traits = AbilitiesComponent), `PlaybookDatabase.LoadPlaybook`, Σ des
        `ITriggeredAbilityPlaybook.CalculateAttackUtilityInSteps` (vslot 3 — registre attack
        `engine/playbook/psyker.py`). `ctx` = AiDecisionContext (scene/wt/hpmax/normal_ids), PAS le
        dict tile-leaf de la face move.

        #419 — SOURCE DU KIT : le decompile du dispatcher lit `case.unit@+0x10` -> GetComponent ->
        `+0x18` (la Collection) -> `GetEnumerator`, puis pour chaque item `LoadPlaybook(type)`. C'est
        LITTERALEMENT l'`AbilitiesComponent` ECS, **la meme collection que la face MOVE** — et cette
        face-la la lit deja en live depuis #304. La face ATTACK, elle, ne lisait que le kit
        gameconfig+traits : elle etait donc AVEUGLE a tout ce que la bataille monte et que le
        gameconfig ignore, au premier rang **les abilities de RELIQUE**
        (`UnitConfiguration.TertiaryAbility`, 5e chemin de registration #357). Symptome : un
        playbook attack de relique entre au registre et reste INERTE, sans erreur ni test rouge —
        le patron « porte + non cable » que #419 recense. Le repli reste ENTIER quand la lecture
        live est vide (RPC indisponible, entite absente, contexte OFFLINE `rid` faux -> `[]`) :
        c'est exactement la degradation retenue par #304 pour la face move.

        #438 -- `prediction` = `case.DamagePrediction` (`UtilityAttackCase@+0x28`,
        `Nullable<DamagePredictionResult>`). Le natif passe le CASE ENTIER a chaque playbook ; le
        port l'eclate en composants, et ce composant-la manquait. `None` mirror
        `HasValue == false` : c'est le regime des cases `ForEffect`/`ForHealPrediction`/
        `ForRepairPrediction`, ou tout playbook qui lit la prediction rend 0. SEUL
        `BarbedOvipositorPlaybook` la consomme a ce jour ; les autres l'acceptent et l'ignorent,
        comme leurs corps natifs qui ne lisent pas ce champ du case."""
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return 0.0
        from ..playbook.psyker import load_attack_playbook
        total = 0.0
        kit = list(kit_triggered_ability_ids(sc.vis_by_id.get(attacker_uid)))
        _live_fn = getattr(ctx, "live_triggered_ability_ids", None)
        if callable(_live_fn) and attacker_uid is not None:
            _live = list(_live_fn(attacker_uid) or ())
            if _live:
                kit = _live                 # l'AbilitiesComponent REEL, tel que le natif l'itere
        for ab in kit:
            pb = load_attack_playbook(ab)
            if pb is not None:
                total += pb.calculate_attack_utility_in_steps(ctx, attacker_uid, ability_id,
                                                              target_uid, attack_tile,
                                                              prediction=prediction)
        return total


class TriggeredAbilitiesNonOwnerUtility(BaseUtility):
    """`TriggeredAbilitiesNonOwnerUtility` (`IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility$$.ctor` ;
    UtilityType.TriggeredAbilitiesNonOwner=4) — le dispatcher JUMEAU de `TriggeredAbilities(2)`,
    mais pris À L'ENVERS : ce sont les abilities déclenchées des **AUTRES** unités qui pèsent la
    tuile candidate du mover. Poids dans la catégorie SÉPARÉE
    `Utilities.Default.TriggeredAbilitiesNonOwner`. Concrets : `engine/playbook/non_owner.py`.

    `IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.u003CEvaluateMovementInStepsu003Ed__0$$MoveNext` :

        Fix64 total = 0;
        if (case.unit == null && case.parent == null) { yield 0; return; }
        foreach ((playbook, owner) in IterateAbilities(case))
            total += playbook.CalculateMovementUtilityInSteps(case, owner);   // Σ des steps
        yield total;

    `IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.u003CIterateAbilitiesu003Ed__3$$MoveNext` :
    pour CHAQUE `TriggeredAbility` de la bataille, `case.unit == ability.Owner` ⇒ skip (self exclu),
    `IdunBattle.AI.PlaybookDatabase$$LoadPlaybookNonOwner(ability.Type)` (null ⇒ skip), puis
    `<slot 4> || IsFriend(case.unit ?? case.parent, ability.Owner)` ⇒ yield `(playbook, owner)`.

    ⚠ Le pré-gate `<slot 4>` est PORTÉ, et c'est une donnée **PAR CLASSE** — pas une constante de
    famille. Le slot a un NOM : `get_ShouldIncludingEnemiesWhenCalculate`, 5ᵉ méthode d'
    `IdunBattle.AI.Playbook.ITriggeredAbilityNonOwnerPlaybook`, LUE dans le `global-metadata.dat`
    (#477-r37). Sur les **28** concrets, **DEUX** la surchargent — `HaywireMineNonOwnerPlaybook`
    (face MOVE) et `NoHidingFromTheWatchersNonOwnerPlaybook` (face ATTACK), les deux à `true` ; les
    26 autres héritent le `false` de la base. Le gate ne se réduit donc PAS à `IsFriend` : pour ces
    deux classes il yielde AUSSI les porteurs ENNEMIS. Il est appliqué ICI, là où le natif le met
    (dans `IterateAbilities`), pas dans les corps de playbook.
    ⚠ Cette ligne a énoncé le contraire (« vaut `false` — aucune classe ne le surcharge », héritée de
    #433-r4-r3) pendant que le code ci-dessous portait DÉJÀ la valeur par classe : la citation
    contredisait son propre foyer. Coût mesuré de cette lecture-là quand elle était armée : `-30`
    manquants sur la tuile minée du montage `haywire` (branche ENNEMI de 1531 structurellement
    inatteignable). Ne jamais la re-généraliser. Entrée VERSIONNÉE + cliquet :
    `data/symbols/<build>/metadata/non_owner_slot4.tsv`, `probe_477r37_slot4_et_faces_restantes.py`
    étape 0a (3 sources, chacune DIT son angle mort). Chaîne de lecture complète : docstring de tête
    de `engine/playbook/non_owner.py`.

    ⚠ RÉGIME SPAWN (`case.unit == null`, `case.parent != null` — call-site
    `SortTilesByUtilityForSummon`, case-205) : le natif **ITÈRE QUAND MÊME**. Relu au décompilé
    (#271-r3) — `<EvaluateMovementInSteps>d__0` ne rend `Fix64.Zero` que si `case.unit == null`
    **ET** `case.parent == null` (`if (case+0x10 != 0 || case+0x30 != 0)` avant l'itération), et
    `<IterateAbilities>d__3` prend alors le PARENT pour sujet de `IsFriend` **et désarme
    l'exclusion de self** (son `continue` est gardé par `case.unit != null`).
    Cette feuille court-circuitait sur `is_spawning`, ce qui était un écart CHIFFRÉ : trois corps
    du registre ne lisent JAMAIS `case.unit` et yieldent donc dans ce régime —
    `PsychicFortressNonOwnerPlaybook` (20), `BookOfFateNonOwnerPlaybook` (5) et la BRANCHE SPAWN de
    `MawClawsOfThyraxNonOwnerPlaybook` (5). Les 16 autres portent `if (case.unit == null) yield
    break` : leur 0 vient désormais de LEUR corps (mirror fidèle), plus d'un court-circuit en
    amont — le gate `is_spawning` de chaque playbook est devenu LOAD-BEARING.
    Le substrat du régime est `_spawn_leaf_ctx` (amis/ennemis campés sur le PARENT, SANS
    self-exclusion). Rayon de souffle mesuré avant de le peupler : **0** feuille sur 27."""
    UTILITY_TYPE = int(UtilityType.TriggeredAbilitiesNonOwner)  # 4

    def evaluate(self, tile, meta, ctx, wt) -> float:
        ctx = ctx or {}
        from ..playbook.non_owner import load_playbook_non_owner
        total = 0.0
        # `friend_units`/`enemy_units` sont SELF-EXCLUS quand il y a un SUJET : c'est exactement le
        # `if (case.unit == ability.Owner) continue` du natif. En régime SPAWN ils ne le sont PAS,
        # parce que ce `continue` est gardé par `case.unit != null` — le PARENT est donc lui-même un
        # porteur candidat, et c'est `_spawn_leaf_ctx` qui porte cette différence, pas cette boucle.
        # Les DEUX listes sont parcourues (le
        # natif itère TOUTES les TriggeredAbility de la bataille, pas seulement celles des amis),
        # puis le PRÉ-GATE `<slot 4> || IsFriend(sujet, owner)` écarte les porteurs non amis — SAUF
        # pour les classes dont le `<slot 4>` vaut `true`, qui gardent AUSSI les ennemis (#477-r37).
        # `is_friend` reste passé aux playbooks : `KustomForceFieldReworkedNonOwnerPlaybook` le
        # RE-TESTE dans son propre corps natif, et le port mirrore ce corps.
        for units, is_friend in ((ctx.get("friend_units") or (), True),
                                 (ctx.get("enemy_units") or (), False)):
            for u in units:
                for ab in (u.get("triggered") or ()):
                    pb = load_playbook_non_owner(ab)
                    if pb is None:
                        continue
                    # PRE-GATE `playbook.<slot 4> || IsFriend(sujet, owner)`. Le `<slot 4>` se lit
                    # SUR LE PLAYBOOK, jamais sur la famille : il vaut `true` pour
                    # `HaywireMineNonOwnerPlaybook` (corps `return 1`) et `false` pour toutes les
                    # autres. Avant #477-r35 le dispatcher ecartait TOUS les porteurs ennemis d'un
                    # bloc, avant meme de charger le playbook -- ce qui rendait structurellement
                    # inatteignable la branche ENNEMI de 1531. MESURE : -30 manquants sur la tuile
                    # minee du montage `haywire`.
                    # Acces DIRECT, jamais `getattr(..., False)` : `TriggeredAbilityNonOwnerPlaybook`
                    # declare `SLOT_4 = False`, donc TOUTE classe de la famille le porte (mesure :
                    # 22 classes du module, 2 bases + 20 concretes) et le defaut serait mort. Un
                    # objet ETRANGER a la famille doit LEVER ici, pas se faire silencieusement
                    # traiter comme un `false`. Le `<slot 4>` des 28 concrets du binaire est LU et
                    # VERSIONNE (#477-r37) ; le cliquet confronte le port au binaire classe par
                    # classe (`probe_477r37_slot4_et_faces_restantes.py` etape 0a).
                    if not (pb.SLOT_4 or is_friend):
                        continue          # `!<slot 4> && !IsFriend` = IsInvalidEntityForPlaybook
                    total += pb.calculate_movement_utility_in_steps(tile, u, is_friend, ctx, wt)
        return total

    def evaluate_attack_in_steps(self, ctx, caster_uid: int, caster_tile, target_uid: int) -> float:
        """Face ATTACK du dispatcher — `IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.u003CEvaluateAttackInStepsu003Ed__1$$MoveNext`,
        feuille 4 du composite `Damage(35)` (#271-r4). Corps natif, LU :

            Fix64 total = 0;
            foreach ((playbook, owner) in IterateAbilities(case.<+0x10>))   // surcharge (IEntity)
                total += playbook.<slot 1>(case, owner);
            yield total;

        DEUX écarts avec la face MOVE, tous deux LUS et load-bearing :

        * **AUCUN gate de nullité du sujet.** `<EvaluateMovementInSteps>d__0` ouvre sur
          `if (case.unit == null && case.parent == null) { yield 0; return; }` ; cette face-ci
          n'a rien. Il n'y a donc pas de régime SPAWN à écarter ici — un `UtilityAttackCase` a
          toujours un caster.
        * **Le SUJET est le CASTER** (`case+0x10`, écrit par `UtilityAttackCase$$.ctor`), là où la
          face MOVE prend `case.unit ?? case.parent`.

        Et `<IterateAbilities>d__4` (la surcharge `(IEntity)`) diffère de `d__3` sur un seul point,
        lui aussi load-bearing : **l'exclusion de self est INCONDITIONNELLE**
        (`if (ta.Owner == subject) continue`), là où `d__3` la garde par `case.unit != null`. Le
        caster ne pèse donc JAMAIS ses propres abilities non-owner.

        Le pré-gate `<slot 4> || IsFriend(subject, owner)` est le MÊME, et il est appliqué ICI —
        là où le natif le met. `NoHidingFromTheWatchersNonOwnerPlaybook` est la seule classe ATTACK
        dont le `<slot 4>` vaut `true` : sans lui sa branche ENNEMI serait structurellement
        inatteignable (son corps ouvre sur `if (IsFriend(...)) yield break`).

        `ctx` = l'`AiDecisionContext` (comme la face ATTACK de la feuille 2), PAS le dict tile-leaf
        de la face MOVE. La source du kit déclenché est `ctx.live_triggered_ability_ids(owner)` —
        l'`AbilitiesComponent` ECS, celui que le natif itère — avec repli sur le kit gameconfig
        quand le canal live est muet (même degradation que la feuille 2, #419)."""
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return 0.0
        from ..playbook.non_owner_attack import load_playbook_non_owner_attack
        _live_fn = getattr(ctx, "live_triggered_ability_ids", None)
        my_team = sc.team(caster_uid)
        total = 0.0
        for u in (sc.units or []):
            owner = u.get("id")
            if owner is None:
                continue
            owner = int(owner)
            # `if (ta.Owner == subject) continue` — INCONDITIONNEL dans `<IterateAbilities>d__4`.
            if owner == int(caster_uid):
                continue
            if sc.pos(owner) is None:        # unité sans tuile : hors du cache d'abilities vivantes
                continue
            kit = list(kit_triggered_ability_ids(sc.vis_by_id.get(owner)))
            if callable(_live_fn):
                _live = list(_live_fn(owner) or ())
                if _live:
                    kit = _live              # l'AbilitiesComponent REEL, tel que le natif l'itère
            if not kit:
                continue
            # `UnitExtensions.IsFriend(subject, ta.Owner, State)` — même camp que le CASTER.
            is_friend = (sc.team(owner) == my_team)
            for ab in kit:
                pb = load_playbook_non_owner_attack(ab)
                if pb is None:
                    continue
                # PRE-GATE `playbook.<slot 4> || IsFriend`. Accès DIRECT, jamais
                # `getattr(..., False)` : toute classe de la famille porte `SLOT_4`, donc le défaut
                # serait mort et un objet ETRANGER doit LEVER ici (même règle que la face MOVE).
                if not (pb.SLOT_4 or is_friend):
                    continue      # `!<slot 4> && !IsFriend` = IsInvalidEntityForPlaybook
                total += pb.calculate_attack_utility_in_steps(ctx, int(caster_uid), caster_tile,
                                                              int(target_uid), owner, is_friend,
                                                              ctx.wt)
        return total

    def evaluate_repair_in_steps(self, ctx, caster_uid: int, target_uid: int, fill_hp,
                                 target_max_hp, caster_is_boss: bool = False) -> float:
        """Face REPAIR du dispatcher — `IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.u003CEvaluateRepairInStepsu003Ed__2$$MoveNext`,
        feuille 4 du composite `Repair(47)` (#271-r7). Corps natif, LU :

            Fix64 total = 0;
            foreach ((playbook, owner) in IterateAbilities(case.<+0x10>))   // surcharge (IEntity)
                total += playbook.<slot 2>(case, owner);
            yield total;

        C'est le JUMEAU EXACT de la face ATTACK ci-dessus — mêmes DEUX écarts avec la face MOVE
        (aucun gate de nullité du sujet ; le SUJET est le CASTER `case+0x10`), même
        `<IterateAbilities>d__4` à exclusion de self INCONDITIONNELLE, même pré-gate
        `<slot 4> || IsFriend`. Seul le slot appelé change (2 au lieu de 1), et donc le REGISTRE.

        ⚠ Le composite `Repair(47)` a **TROIS** membres (`RepairedAmount(48)`,
        `TriggeredAbilities(2)`, `TriggeredAbilitiesNonOwner(4)`, lus par
        `probe_271r4_composition_map.py`). Le port n'en sommait qu'UN. Cette méthode en câble un
        SECOND ; la feuille 2 (face repair du dispatcher OWNER) reste non portée — écart NOMMÉ.

        `fill_hp` / `target_max_hp` / `caster_is_boss` sont ce que la feuille `RepairedAmount(48)`
        lit du `UtilityAttackCase` (`+0xdc` = le `fillUp` de la `RepairPredictionResult`), et que le
        seul corps concret RE-ÉMET. Le port les passe donc jusqu'au playbook plutôt que de
        reconstruire un case."""
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return 0.0
        from ..playbook.non_owner_repair import load_playbook_non_owner_repair
        _live_fn = getattr(ctx, "live_triggered_ability_ids", None)
        my_team = sc.team(caster_uid)
        total = 0.0
        for u in (sc.units or []):
            owner = u.get("id")
            if owner is None:
                continue
            owner = int(owner)
            # `if (ta.Owner == subject) continue` — INCONDITIONNEL dans `<IterateAbilities>d__4`.
            if owner == int(caster_uid):
                continue
            if sc.pos(owner) is None:        # unité sans tuile : hors du cache d'abilities vivantes
                continue
            kit = list(kit_triggered_ability_ids(sc.vis_by_id.get(owner)))
            if callable(_live_fn):
                _live = list(_live_fn(owner) or ())
                if _live:
                    kit = _live              # l'AbilitiesComponent REEL, tel que le natif l'itère
            if not kit:
                continue
            is_friend = (sc.team(owner) == my_team)
            for ab in kit:
                pb = load_playbook_non_owner_repair(ab)
                if pb is None:
                    continue
                # PRE-GATE `playbook.<slot 4> || IsFriend`. Accès DIRECT (même règle que les deux
                # autres faces) : toute classe de la famille porte `SLOT_4`.
                if not (pb.SLOT_4 or is_friend):
                    continue      # `!<slot 4> && !IsFriend` = IsInvalidEntityForPlaybook
                total += pb.calculate_repair_utility_in_steps(
                    ctx, int(caster_uid), int(target_uid), owner, is_friend, fill_hp,
                    target_max_hp, caster_is_boss, getattr(ctx, "wt", None))
        return total


# ── Registry : UtilityType -> (name, instance|None). None => délégué/non-portable comme simple leaf. ──
#
# CLES = MEMBRES `UtilityType`, JAMAIS des litteraux (#254). Elles etaient numeriques ; #158 avait
# note « value-preserving, IntEnum -> cles TILE_LEAVES[i] inchangees » — hypothese devenue FAUSSE a
# la MAJ de build : `#252 fe5b9245` a re-derive l'enum (`AttackTile` INSERE en 8, 59 membres decales
# de +1), si bien que `TILE_LEAF_IDS` (des membres) indexait ce dict (des litteraux ANCIENS) et
# rendait la MAUVAISE feuille pour 26 des 29 entrees -- silencieusement : `TILE_UTILITY` sommait
# `TileEffectsUtility` la ou l'ordre runtime demandait `Elevation`, et les feuilles `SteppableUnit`
# / `DecoysAndMisdirection_AttractToDecoys` (#241) disparaissaient du composite. Avec des MEMBRES des
# deux cotes, une renumerotation future est sans effet sur l'appariement.
TILE_LEAVES: dict[int, tuple] = {
    # --- ACTIVES (metadata dispo aujourd'hui) ---
    UtilityType.Elevation:  ("Elevation", ElevationUtility()),
    UtilityType.SteppableUnit: ("SteppableUnit", SteppableUnitUtility()),
    UtilityType.TileEffects:  ("TileEffects", TileEffectsUtility()),
    UtilityType.TemporaryTile: ("TemporaryTile", TemporaryTileUtility()),  # RÉELLE (meta.is_temporary via tileMeta)
    # --- PORTÉES FIDÈLE, DORMANTES (gate sur metadata par-tuile/unité non encore plombée → 0) ---
    UtilityType.UnitEffectsAdjacent: ("UnitEffectsAdjacent", UnitEffectsAdjacentUtility()),
    UtilityType.UnitEffectsSurrounding: ("UnitEffectsSurrounding", UnitEffectsSurroundingUtility()),
    UtilityType.UnitEffectsRanged: ("UnitEffectsRanged", UnitEffectsRangedUtility()),
    UtilityType.CapturePoint: ("CapturePoint", CapturePointTileUtility()),
    UtilityType.PowerUp: ("PowerUp", PowerUpTileUtility()),
    UtilityType.Contaminated: ("Contaminated", ContaminatedUtility()),
    UtilityType.MoltenForm: ("MoltenForm", MoltenForm_TilesUtility()),
    UtilityType.TilePendingBlockableSummon: ("TilePendingBlockableSummon", TilePendingBlockableSummonUtility()),
    UtilityType.EnvEndBombardment: ("EnvEndBombardment", EnvEndBombardmentUtility()),
    UtilityType.DespoiledGround: ("DespoiledGround", DespoiledGroundUtility()),
    UtilityType.SummonDislikeDoorOpening: ("SummonDislikeDoorOpening", SummonDislikeDoorOpeningUtility()),
    UtilityType.HeroLikeDoorOpening: ("HeroLikeDoorOpening", HeroDoorOpeningUtility()),
    UtilityType.Phantasm_AvoidFriendlyPhantasm: ("Phantasm_AvoidFriendlyPhantasm", Phantasm_AvoidFriendlyPhantasmUtility()),
    UtilityType.EchoesFromTheWarp_FriendliesAvoidGhost: ("EchoesFromTheWarp_FriendliesAvoidGhost", EchoesFromTheWarp_FriendliesAvoidGhostUtility()),
    UtilityType.DoctrinaImperatives_AttractMechanicals: ("DoctrinaImperatives_AttractMechanicals", AttractMechanicalsUtility()),
    UtilityType.DecoysAndMisdirection_AttractToDecoys: ("DecoysAndMisdirection_AttractToDecoys", AttractToDecoysUtility()),
    UtilityType.KustomForceField: ("KustomForceField", KustomForceFieldUtility()),
    UtilityType.DefenderOfTheGreaterGood: ("DefenderOfTheGreaterGood", DefenderOfTheGreaterGoodUtility()),
    UtilityType.SaviorProtocols: ("SaviorProtocols", SaviorProtocolsUtility()),
    UtilityType.BioMinefield_MoveTowardsTarget: ("BioMinefield_MoveTowardsTarget", BioMinefield_MoveTowardsTargetUtility()),
    UtilityType.MasterOfTheTutelaries_MoveTowardsTarget: ("MasterOfTheTutelaries_MoveTowardsTarget", MasterOfTheTutelaries_MoveTowardsTargetUtility()),
    # --- Dispatchers playbook PORTÉS : (2) abilities du mover (case-36), (4) abilities des AUTRES (#271) ---
    UtilityType.TriggeredAbilities: ("TriggeredAbilities", TriggeredAbilitiesUtility()),   # face attack : cf. fonction ci-dessous
    # NonOwner(4) : RE complète depuis #57i, PORTÉE depuis #271 (`engine/playbook/non_owner.py`).
    # Les 25 clés NonOwner sont des abilities précises (FirstAmongTraitors/ShieldOfFaith/HaywireMine/
    # NornCrown/KustomForceFieldReworked/...) -> la feuille rend 0 tant qu'AUCUNE unité de la
    # bataille ne PORTE une ability dont le playbook NonOwner est au registre. Ce N'ÉTAIT PAS la
    # source des miss #57i (S14 12345 u87 / S16 2468 u79 : aucun ennemi ne portait de NonOwner).
    UtilityType.TriggeredAbilitiesNonOwner: ("TriggeredAbilitiesNonOwner", TriggeredAbilitiesNonOwnerUtility()),
    # --- NON portées comme simples leaves ---
    UtilityType.RangedAdjacentEnemy: ("RangedAdjacentEnemy", None),  # =0 dans le profil Default (BC HasAdjacentEnemy absent)
    # 3 = dispatcher restant du moteur Playbook (behaviours par-unité).
    UtilityType.UnitSpecificBehaviours: ("UnitSpecificBehaviours", None),
}

# CLIQUET (#254) : la cle de chaque entree DOIT etre `UtilityType.<name>` de l'entree. C'est ce qui
# a saute a la MAJ de build, sans bruit ; l'assertion le rend impossible a re-introduire.
_MISKEYED = [(int(k), n) for k, (n, _i) in TILE_LEAVES.items()
             if int(getattr(UtilityType, n, -1)) != int(k)]
assert not _MISKEYED, (
    "TILE_LEAVES mal keye (cle, name) : %r -- une cle doit valoir UtilityType.<name>, sinon "
    "TILE_LEAF_IDS (des MEMBRES) selectionne la mauvaise feuille" % _MISKEYED)
del _MISKEYED


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


# ── `TileDistance(34)` : la SŒUR de `Tile(7)` dans le composite `MovementSuggestion(33)` (#201) ──────
class TileDistanceUtility(BaseUtility):
    """`IdunBattle.AI.Utilities.TileDistanceUtility` (`IdunBattle.AI.Utilities.TileDistanceUtility$$.ctor` ;
    UtilityType.TileDistance=34). Mirror 1:1 de
    `IdunBattle.AI.Utilities.TileDistanceUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` +
    `IdunBattle.AI.Utilities.TileDistanceUtility$$DistanceTo`, remis en C# depuis le décompilé :

        IEnumerator<Fix64> EvaluateMovementInSteps(UtilityMovementCase c) {
            if (c.units != null)      yield return DistanceTo(c, c.units);   // case+0x10
            else if (c.owner != null) yield return DistanceTo(c, c.owner);   // case+0x30
            else                      yield return Fix64.FromInt(0);
        }
        Fix64 DistanceTo(UtilityMovementCase c, IEntity caseUnit) {
            ITile from = caseUnit.GetMainTile(this.entities);   // this+0x10 = entities
            ITile to   = c.position.MainTile;                   // case+0x18 = UnitPosition(tuile candidate)
            int d = this.battleQuery.<slot 0x6c = GetDistance>(from, to);   // this+0x20 = battleQuery
            return Fix64.FromInt(-d) / Fix64.FromInt(10);
        }

    Trois points que le décompilé TRANCHE et qu'il ne faut pas deviner :

    * **AUCUN poids BC.** Le corps ne lit ni `HasUtilityValue` ni `GetUtilityValue` : le facteur `-1/10`
      est une CONSTANTE de code (à l'inverse d'`ElevationUtility`, dont le 10 vient de
      `Utilities.Default.Elevation.Multiplier`). Rien à câbler dans `Weights`.
    * **SIGNE NÉGATIF** : plus la candidate est loin de l'unité, PIRE elle est.
    * **DISTANCE HEX, pas coût de chemin** : le slot `0x6b` du `battleQuery` retombe sur
      `IdunBattle.Core.Services.MovementQuery$$GetDistance`, qui prend le MIN sur les paires de
      `IdunBattle.Utils.Hex.CubeCoordinate$$Distance` des tuiles des deux entités. Pour deux entités
      mono-tuile (`GetMainTile` en amont) = `hexgeo.distance` exactement.

    ⚠ **ORDRE DE GRANDEUR — c'est le cœur du comportement** : sur un pool de charge (`move_range` = 2)
    `d ∈ {1, 2}`, donc ce terme vaut `{-0.1, -0.2}`. Il ne peut JAMAIS renverser un écart de `Tile(7)`,
    dont les feuilles sont à valeurs entières (Elevation 10/niveau, TileEffects ±9/−25, playbooks
    10/30/…). Sa fonction est donc EXACTEMENT de **départager les ex æquo de `Tile(7)`** — et sur un
    plateau plat, où `Tile(7)` est constant, il départage TOUT : le classement devient « la plus proche
    de l'unité d'abord ». C'est ce régime-là que le collapse historique de `_vigilance_move_dest_tile`
    reproduisait ; ce que le collapse rendait FAUX, c'est le régime inverse (`Tile(7)` départage → il
    DOMINE, cf. `docs/rl/case-201-movement-suggestion-tiledistance.md`).

    `ctx["self_pos"]` = la position de `case.unit` (l'unité passée au sélecteur = `dc.unit`), posée
    par `runner_tile_leaf_ctx`/`tile_leaf_ctx`.

    ⚠ **LA BRANCHE DE REPLI EST DÉSORMAIS PORTÉE, PARCE QU'UN CALL-SITE L'EXERCE (#1080).** Cette
    docstring écrivait que `else if (c.owner != null) DistanceTo(c, c.owner)` n'était atteignable
    que par `SortTilesByUtilityForSummon`, « or ses six occurrences passent toutes
    `UtilityDefinition(7 = Tile)` ». Ce n'est plus vrai :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.CallInReinforcementsAbility$$CreateBehaviour`
    bâtit sa définition À LA MAIN — `UtilityDefinition(UtilityBucket([ WeightedUtility(0x1b = 27
    PowerUp), WeightedUtility(0x22 = 34 TileDistance) ]))` — et la passe à
    `SortTilesByUtilityForSummon(tiles, <cette définition>, Owner@<DSLSelectors+0x30>)`. Le régime
    `case.unit == null && case.parent != null` évalue donc bien `TileDistance(34)`, et c'est LUI qui
    porte le « in a nearby free edge hex » de l'i2 : sans le repli, le tri serait constant sur tout
    le bord du plateau et le summon tomberait n'importe où. `ctx["parent_pos"]` est la clé posée par
    `_spawn_leaf_ctx` pour ce seul usage (clé NEUVE, aucune autre feuille ne la lit).

    Les DEUX positions absentes → 0.0 : c'est la branche `else yield Fix64.FromInt(0)` du natif."""
    UTILITY_TYPE = int(UtilityType.TileDistance)  # 34

    def evaluate(self, tile, meta, ctx, wt) -> float:
        c = ctx or {}
        # `if (c.units != null) DistanceTo(c, c.units)` -- le sujet PRIME sur le parent, comme dans
        # le `MoveNext` natif (le `else if` n'est atteint que si `case+0x10` est nul).
        from_pos = c.get("self_pos")
        if from_pos is None:
            from_pos = c.get("parent_pos")         # `else if (c.owner != null) DistanceTo(c, c.owner)`
        if from_pos is None or tile is None:
            return 0.0
        import hexgeo as _hex                      # lazy : utilities <- hexgeo (module top-level)
        d = _hex.distance((from_pos[0], from_pos[1]), (tile[0], tile[1]))
        return -float(d) / 10.0


# Composite `MovementSuggestion(33)` = INSTANCE `ComposedUtility` de DEUX enfants, exactement comme
# `Tile(7)` est une instance de 29 : la carte de composition vit dans
# `IdunBattle.Core.Services.UtilitiesDatabase$$InitializeUtilities`, qui remplit le
# `Dictionary<UtilityType, UtilityType[]>` de `UtilitiesDatabase+0x58`. L'entrée `0x21` y reçoit un
# tableau de DEUX éléments écrits l'un après l'autre : `[0] = 7` (Tile) puis `[1] = 0x22` (TileDistance).
# `IdunBattle.Core.Services.UtilitiesDatabase$$GetUtility` mappe ensuite chaque sous-type par
# `IdunBattle.Core.Services.UtilitiesDatabase.u003Cu003Ec__DisplayClass16_0$$u003CGetUtilityu003Eb__0`
# (= `GetUtility(sousType, MÊME collection)`) et, `Count > 1`, construit un `ComposedUtility`.
# `IdunBattle.AI.Utilities.ComposedUtility.u003CEvaluateMovementInStepsu003Ed__8$$MoveNext` somme les
# enfants SANS pondération (`Fix64.op_Addition` nu) — le seul poids de la chaîne est le
# `WeightedUtility.Weight = 1` du bucket, appliqué au composite ENTIER.
MOVEMENT_SUGGESTION_UTILITY = ComposedUtility(
    [TILE_UTILITY, TileDistanceUtility()], utility_type=UtilityType.MovementSuggestion)

# Mirror de `UtilitiesDatabase$$GetUtility` réduit aux types que les call-sites portés demandent.
# La surcharge INT de `SortTilesByUtility` construit `UtilityDefinition(<literal>)` ->
# `Buckets[0].Utilities[0] = WeightedUtility(<literal>, weight=1)`, et l'utilité résolue est
# l'entrée de cette table. Un call-site peut aussi bâtir la définition À LA MAIN, avec PLUSIEURS
# `WeightedUtility` dans le même bucket (`RammingSpeedAbility$$GetTileToMoveTo`, #353-r1) : la table
# est alors interrogée UNE FOIS PAR TERME, et `UtilityDecider.CalculateUtility` en fait la somme
# pondérée (`engine/utilities/decider.py`).
UTILITY_BY_TYPE: dict[int, BaseUtility] = {
    int(UtilityType.Tile): TILE_UTILITY,                                # 7  — SkyStrike/HeroicFusillade/…
    int(UtilityType.MovementSuggestion): MOVEMENT_SUGGESTION_UTILITY,   # 32 — VigilanceEternal
    # 54 — 2e terme du bucket de `RammingSpeedAbility$$GetTileToMoveTo` (#353-r1). FEUILLE, pas
    # composite : `UtilitiesDatabase$$InitializeUtilities` ne compose que les types qui ont une
    # entrée dans son `Dictionary<UtilityType, UtilityType[]>` ; 54 n'en a pas, `GetUtility` rend
    # donc directement l'instance de la classe.
    int(UtilityType.RammingSpeed_MostAdjacentEnemies): RAMMING_SPEED_MOST_ADJACENT_ENEMIES,
    # 67 — 2e terme du bucket de `LeadingTheChargeAbility$$GetMoveTile` (#508). FEUILLE, pas
    # composite : meme critere que 54 ci-dessus — `UtilitiesDatabase$$InitializeUtilities` ne
    # compose que les types qui ont une entree dans son `Dictionary<UtilityType, UtilityType[]>`,
    # et 67 n'en a pas, donc `GetUtility` rend directement l'instance de la classe.
    int(UtilityType.LeadingTheCharge_ChargeTile): LEADING_THE_CHARGE_CHARGE_TILE,
    # 27 et 34 — les DEUX termes du bucket bâti à la main par
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.CallInReinforcementsAbility$$CreateBehaviour`
    # (`WeightedUtility[2] = [ WeightedUtility(0x1b), WeightedUtility(0x22) ]` -> UN `UtilityBucket`
    # -> UN `UtilityDefinition`), #1080. FEUILLES, pas composites : même critère que 54 et 67
    # ci-dessus — `UtilitiesDatabase$$InitializeUtilities` ne compose que les types présents dans
    # son `Dictionary<UtilityType, UtilityType[]>`, et ni 27 ni 34 n'y a d'entrée (34 n'est qu'un
    # ÉLÉMENT du tableau de 0x21 = MovementSuggestion, pas une clé).
    # Les deux classes existaient déjà — elles vivaient uniquement DANS les composites `Tile(7)` et
    # `MovementSuggestion(33)` ; ce qui manquait était l'entrée de premier niveau, sans laquelle
    # `utilities_database` rend `None` et `UtilityDecider.CalculateUtility` LÈVE.
    int(UtilityType.PowerUp): PowerUpTileUtility(),
    int(UtilityType.TileDistance): TileDistanceUtility(),
}


def utilities_database(utility_type: int) -> BaseUtility | None:
    """`IdunBattle.Core.Services.UtilitiesDatabase$$GetUtility(utilityType)` réduit aux types que
    les call-sites portés demandent (`UTILITY_BY_TYPE`). `None` = type non porté — l'appelant
    (`UtilityDecider.CalculateUtility`) LÈVE plutôt que de rendre 0 en silence."""
    return UTILITY_BY_TYPE.get(int(utility_type))


# ── FOYER UNIQUE du sélecteur `IdunBattle.Entities.Selectors.SortTilesByUtilitySelector` ─────────────
_SORT_WEIGHTS: Weights | None = None


def sort_tiles_by_utility(state, tiles, wt: Weights | None = None, unit_id: int | None = None,
                          utility_type: int = int(UtilityType.Tile),
                          parent_id: int | None = None,
                          utility_definition: UtilityDefinition | None = None,
                          leaf_ctx: dict | None = None) -> list:
    """`IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select` — FOYER UNIQUE.

    Le natif, remis en C# depuis le décompilé :

        dc.tiles  = this.tiles.SelectTiles(entities)          // IList<IEntity>
        dc.unit   = this.unit.<Select*>(entities, 0)          // IEntity SINGULIER, null si rien
        dc.parent = this.parent?.<Select*>(entities, 0)       // IEntity, null si le sélecteur est nul
        dc.dict   = new Dictionary<Tile, Fix64>()
        foreach (tile in dc.tiles)
            dc.dict[tile] = UtilityDecider.CalculateUtility(this.utilitiesDatabase, tile,
                                                            this.definition.Buckets[0], dc.<Select>b__1)
        return dc.tiles.OrderBy(dc.<Select>b__0).ToList()      // b__0 = Fix64.op_UnaryNegation(dict[t])

    `<Select>b__0` rend l'OPPOSÉ de l'utilité -> **tri DÉCROISSANT**, et `OrderBy` LINQ est **STABLE**
    : l'ordre du SÉLECTEUR SOURCE tranche les égalités (carte plate = toutes les utilités à 0).
    **ZÉRO tirage** — le tri ne touche pas le PRNG.

    Chaîne de l'utilité, lue au décompilé :
      * `IdunBattleLogic.Entities.DSLFactory$$SortTilesByUtility` a DEUX surcharges — celle qui prend un
        `int` construit `IdunBattleLogic.AI.Utilities.UtilityDefinition$$.ctor(utilityType)` et délègue à
        celle qui prend l'objet ; `IdunBattleLogic.Entities.DSLFactory$$SortTilesByUtilityForSummon` fait
        pareil en fixant le sélecteur d'unités à `IdunBattle.Entities.Selectors.AllAliveMachinesSelector` ;
      * `UtilityDefinition..ctor(utilityType)` = `Buckets = [ new UtilityBucket(utilityType, null) ]`,
        `UtilityBucket..ctor` = `[ new WeightedUtility(utilityType, null) ]` et
        `IdunBattleLogic.AI.Utilities.WeightedUtility$$.ctor` met `Weight = weight ?? Fix64.FromInt(1)`
        -> **poids 1** ;
      * `IdunBattleLogic.AI.Utilities.UtilityDecider$$CalculateUtility` = Σ `Weight × Σ steps` de
        `<>c__DisplayClass8_0.<Select>b__1(tile, utility)` =
        `utility.EvaluateMovementInSteps(new UtilityMovementCase(dc.unit, tile, null, null, dc.parent))`
        (signature du ctor : `unit, movementPosition, closestEnemy, abilityType, parent`).

    `utility_type` = le littéral d'utilité du call-site, résolu par `UTILITY_BY_TYPE` (mirror de
    `IdunBattle.Core.Services.UtilitiesDatabase$$GetUtility`). La plupart des call-sites portés passent
    `UtilityDefinition(7 = Tile)` -> composite `Tile(7)` = `TILE_UTILITY` (29 feuilles).
    `IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$ExecuteBehaviour` passe
    `UtilityDefinition(0x20 = MovementSuggestion)` -> composite `[Tile(7), TileDistance(34)]` (#201,
    carte de composition relue dans `UtilitiesDatabase$$InitializeUtilities`). Les DEUX passent
    désormais par ici — le contournement « ce call-site ne passe pas par le foyer » est LEVÉ.

    `utility_definition` (#353-r1) = la définition BÂTIE À LA MAIN par le call-site, quand il
    n'emprunte PAS la surcharge int. Elle prime sur `utility_type`.
    `IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$GetTileToMoveTo` est le
    premier call-site porté dans ce cas : il alloue un `WeightedUtility[2]`
    (`[ WeightedUtility(7 = Tile, null), WeightedUtility(0x36 = 54
    RammingSpeed_MostAdjacentEnemies, null) ]`), l'enveloppe dans UN `UtilityBucket(…, null)` puis
    dans un `UtilityDefinition`. Le scalaire `utility_type` ne peut pas exprimer ce bucket — d'où ce
    paramètre. La composition (somme PONDÉRÉE, poids par défaut 1, quatre sentinelles de
    court-circuit non portées) est lue au décompilé dans `engine/utilities/decider.py`, jamais
    supposée depuis le nom « bucket ».

    `unit_id` = le sélecteur d'unités `dc.unit` du natif (`caster@0x160` sur les call-sites de
    charge). Il est passé au `UtilityMovementCase`, donc les feuilles GATÉES SUR L'UNITÉ le voient :
    `runner_tile_leaf_ctx` en dérive le `ctx` par-décision.

    `parent_id` = le sélecteur `parent` du natif (`dc.parent`), 4ᵉ argument de
    `IdunBattleLogic.Entities.DSLFactory$$SortTilesByUtilityForSummon(tiles, utilityType, parent)`.
    **`unit_id=None` + `parent_id` renseigné EST le call-site SUMMON** : case-205 a établi au décompilé
    que son `dc.unit` vaut **`null`** — et non « un ENSEMBLE d'unités » comme le supposait le résidu
    #165b §4. Le sélecteur d'unités que `SortTilesByUtilityForSummon` construit est bien un
    `IdunBattle.Entities.Selectors.AllAliveMachinesSelector`, mais avec son provider (`+0x18`) **NUL** ;
    et `IdunBattle.AI.Utilities.UtilityMovementCase` porte deux accesseurs dédiés à ce cas —
    `get_IsSpawning` (= `unit == null && parent != null`) et `get_UnitOrParent` (= `unit ?? parent`).
    Le ctx produit porte donc `is_spawning=True` et AUCUNE clé de sujet : chaque feuille applique sa
    propre dégradation NOMMÉE (0 pour `TriggeredAbilities(2)`/`DespoiledGround(29)`/
    `HeroLikeDoorOpening(31)`, `IsSpawning` INLINÉ ⇒ « traité comme un summon » pour `CapturePoint(25)`/
    `PowerUp(27)`/`SummonDislikeDoorOpening(30)`).

    ⚠ case-165b — cette clé n'est PAS cosmétique : sur `SkyStrikeAbility$$ExecuteBehaviour`
    (`adeptCelestine`, passif `GeminaeSuperia` 1048) la feuille `TriggeredAbilities(2)` ajoute
    `10 × |CanAddUnit(AdjacentTiles(tuile))|`. Ce terme est CONSTANT en plein plateau (6 voisins
    libres partout) et ne départage donc rien — mais au BORD il vaut jusqu'à 50 points d'écart et
    RENVERSE le classement d'`ElevationUtility`. Mesuré `MC1_67`, cible `necroWarden` @(6,7) :
    natif (5,7) e1 [5 voisins libres] et non (6,6) e2 [3 voisins libres] ; le MÊME couple de tuiles,
    chargé par `bloodIntercessor` (qui n'a PAS GeminaeSuperia), donne (6,6) — cf. `_how_move_dest_tile`.

    Restent ACTIVES sans `unit_id` les feuilles purement TUILE que le board porte —
    `ElevationUtility` (8) et `TileEffectsUtility` (9, covers HÉBERGÉS par le terrain statique).
    C'est cette réduction, MESURÉE et non supposée, que `probe_130_placement_sort_rng.py`
    (dont `--discriminate`) valide.

    `elevation_max`/`elevation_min` sont pris sur le **BOARD ENTIER** (mirror
    `IdunBattle.AI.Utilities.ElevationUtility$$LoadRelevantTileElevations`, verdict case-37 : ni
    l'unité, ni le reachable, ni le candidate-set).

    Les effets de la tuile candidate sont lus comme partout ailleurs (#155) : canal DYNAMIQUE
    `state.effects.by_unit[tileId]` = Loop1 de `TileEffectsUtility` (l'entité-tuile porte ses effets
    exactement comme une unité, case-102), puis `terrain_tile_effects(terrain, dynamique)` pour Loop2
    + le repli statique du Loop1 non hydraté. Le 2ᵉ argument est OBLIGATOIRE : sans lui le -25 de la
    Swamp serait compté DEUX fois.

    `leaf_ctx` (#383) = le dict PAR-DÉCISION des feuilles, FOURNI par l'appelant au lieu d'être
    dérivé d'un `State` de runner. `None` (défaut) = comportement inchangé (`runner_tile_leaf_ctx`).
    Il existe car ce foyer a désormais TROIS substrats d'état, et un seul est un `State` :
    `runner_tile_leaf_ctx` (runner ECS), `tile_leaf_ctx` (AiDecisionContext) et
    `scene_tile_leaf_ctx` (la `Scene` de PRÉDICTION, seule chose que
    `playbook.prediction.make_damage_predictions` reçoit). Le foyer de TRI reste unique.

    Rend une NOUVELLE liste ; `state.board`/`tiles` vides -> copie inchangée."""
    board = getattr(state, "board", None)
    if board is None or not tiles:
        return list(tiles)
    global _SORT_WEIGHTS
    if wt is None:
        if _SORT_WEIGHTS is None:
            _SORT_WEIGHTS = _load_weights()
        wt = _SORT_WEIGHTS
    definition = (utility_definition if utility_definition is not None
                  else UtilityDefinition.from_utility_type(int(utility_type)))
    bucket = definition.bucket          # `Buckets[0]` — le SEUL que `Select` lit (Length==0 -> throw)
    elevs = [t.get("elevation") for t in board.by_id.values() if t.get("elevation") is not None]
    emax = max(elevs) if elevs else None
    emin = min(elevs) if elevs else None
    fx = getattr(state, "effects", None)
    if leaf_ctx is None:
        leaf_ctx = runner_tile_leaf_ctx(state, unit_id, parent_id)

    def _u(t) -> float:
        info = board.by_id.get(t) or {}
        terr = board.tile_def_id(t)
        effs: list = []
        if fx is not None:                             # Loop1 : effets DYNAMIQUES de l'entite-tuile
            effs += [e.name for e in fx.by_unit.get(int(t), []) if not e.consumed and e.name]
        effs += terrain_tile_effects(terr, effs)       # Loop2 + repli Loop1 non hydrate (#155)
        meta = {"elevation": info.get("elevation"), "elevation_max": emax, "elevation_min": emin,
                "effects": effs}
        # #175-r — ce foyer est le TROISIEME constructeur de `meta` du composite `Tile(7)`, et le
        # SEUL qui n'appelait pas `apply_tile_attributes`. Les deux autres (`engine.move` et
        # `engine.playbook.base.tile_utility`) le font depuis #175. Consequence MESUREE : sur ce
        # chemin — le selecteur DSL `SortTilesByUtilitySelector`, donc TOUS les call-sites de charge
        # ET le sweep de tuile de spawn d'un summon — les feuilles gatees sur un attribut de tuile
        # rendaient 0 SANS EXCEPTION, quoi que porte le `leaf_ctx`. Le natif, lui, evalue le MEME
        # `ComposedUtility` avec le MEME `UtilityMovementCase` sur les trois chemins : c'est UNE
        # composition, pas trois. Les cartes que `runner_tile_leaf_ctx` ne publie pas
        # (`is_territory_by_pos`, `tile_effect_type_ids_by_pos`) restent absentes -> les feuilles
        # correspondantes degradent a 0 comme avant, exactement comme sur les deux autres chemins.
        apply_tile_attributes(meta, board.coord(t), leaf_ctx)
        # ⚠ Le 1er argument est la POSITION (col,row), pas l'id de tuile : c'est le contrat des DEUX
        # autres constructeurs de composite (`engine.move`, `playbook.base.tile_utility`) et celui
        # qu'attendent les playbooks de la feuille TriggeredAbilities(2) (`hexgeo`/`battle_query`).
        # Inerte tant que `leaf_ctx` était vide (aucune feuille active ne lit `tile`), décisif dès
        # que `unit_id` est fourni. `TileDistance(34)` (composite 32) le lit TOUJOURS.
        #
        # `case` = le `UtilityMovementCase(dc.unit, tile, null, null, dc.parent)` du natif, réduit à
        # ce que les feuilles portées consomment ; `dc.unit`/`dc.parent` sont déjà dans `leaf_ctx`.
        case = (board.coord(t), meta)
        return calculate_utility(utilities_database, case, bucket,
                                 lambda cse, u: u.evaluate(cse[0], cse[1], leaf_ctx, wt))

    util = {t: _u(t) for t in tiles}
    return sorted(tiles, key=lambda t: -util[t])   # b__0 = op_UnaryNegation -> DÉCROISSANT, stable


def first_tile_by_utility(state, tiles, wt: Weights | None = None, unit_id: int | None = None,
                          utility_type: int = int(UtilityType.Tile),
                          parent_id: int | None = None,
                          utility_definition: UtilityDefinition | None = None,
                          leaf_ctx: dict | None = None):
    """`First(SortTilesByUtility(<tiles>, <unit>, <definition>, <parent>), 1)` — la MEILLEURE tuile
    au sens de la définition demandée, égalités tranchées par l'ordre du sélecteur source (tri
    stable). `unit_id` = `dc.unit`, `parent_id` = `dc.parent`, `utility_type` = le littéral du
    call-site, `utility_definition` = la définition bâtie à la main quand il y en a une
    (cf. `sort_tiles_by_utility`).
    Rend l'id de tuile, ou None si `tiles` est vide (le `MoveUnit`/`Spawn` en aval est alors no-op)."""
    ranked = sort_tiles_by_utility(state, tiles, wt, unit_id, utility_type, parent_id,
                                   utility_definition, leaf_ctx)
    return ranked[0] if ranked else None


def _est_vivante(e) -> bool:
    """Filtre d'unite des deux regimes du ctx runner : une entite SANS `UnitComponent` passe
    (tuile, objet), une unite morte non."""
    from ..runner.components import UnitComponent
    uc = e.get_component(UnitComponent)
    return uc is None or bool(uc.alive)


def _unit_record(e, uid: int, pc, fx) -> dict:
    """L'enregistrement `{pos, vis, id, triggered, active, traits, effects, hp, hp_max}` d'un voisin.

    FOYER UNIQUE des deux regimes (sujet present / SPAWN) : deux constructions separees
    finiraient par diverger de forme, et une feuille lisant une cle absente d'un seul des deux
    rendrait 0 sans erreur.

    #456-r1 -- `triggered`/`active`/`traits` sortent du substrat d'ENTITE (`UnitContext`, seede par
    `snapshot._load_triggered_abilities`), plus du kit gameconfig par `visualId` : c'est ce que
    `HasTrait`/`HasActiveAbility` interrogent. Relique, greffe et abilities derivees d'un TRAIT y
    etaient invisibles.

    #983 -- `hp`/`hp_max` (`HealthComponent`, le substrat de `StatType.Health`). Consommateur :
    `IdunBattle.Entities.UnitExtensions$$IsDamagedUnit` =
    `GetStat(u, StatType.Health = 5, StatPart.Missing = 4) > 0`, terme du corps PROPRE de
    `IdunBattle.AI.Playbook.SanguinaryPriestPlaybook`. TRI-ETAT : composant absent -> `None` des
    deux cotes, JAMAIS `0` -- un `0` de PV se lirait comme une unite morte, et un `0` de maximum
    ferait passer toute unite pour intacte."""
    from ..runner.components import HealthComponent, StatsComponent, UnitComponent
    uc = e.get_component(UnitComponent)
    sc = e.get_component(StatsComponent)
    hc = e.get_component(HealthComponent)
    vis = uc.visual_id if uc is not None else None
    cx = sc.ctx if sc is not None else None
    _fx = (fx.by_unit.get(int(uid), []) if fx else [])
    return {"pos": (pc.col, pc.row), "vis": vis, "id": uid,
            "triggered": tuple(entity_triggered_ability_ids(cx, vis)),
            "active": tuple(entity_active_ability_ids(cx, vis)),
            "traits": entity_trait_names(cx, vis),
            "hp": (hc.hp if hc is not None else None),
            "hp_max": (hc.hp_max if hc is not None else None),
            # #443-r1 / #433-r4-r3-r2 : `IdunBattle.Entities.UnitExtensions$$GetParent(u, state,
            # root: false)` -- le lien enfant -> SUMMONER (`ChildComponent.ParentId`) du VOISIN, et
            # non plus du seul sujet. `ECogSupportPlaybook` (1487, face OWNER) teste
            # `GetParent(<voisin>, State, root: false) == case.unit` : sans le parent de CHAQUE
            # voisin il compterait tous les amis adjacents au lieu des seuls summons du porteur.
            # `None` = pas de parent OU pas mesure, comme `unit_parent_id` du sujet.
            "parent": _parent_id_of(e),
            "effects": tuple(ef.name for ef in _fx if not ef.consumed and ef.name),
            # #175-r1 -- le substrat que `_unit_record` JETAIT : `EffectComponent.EffectType@+0x58`
            # et `SourceUnitId@+0x10`. `MoveTowardsUnitUtility.<EvaluateMovementInSteps>d__15` les
            # lit tous les deux (`GetActiveEffects(type)` puis, sur le porteur retenu,
            # `GetOwnedEffect(u, State, type)` -> `SourceUnitId == GetParent(case.Unit).Id`), et le
            # champ `effects` ci-dessus, qui ne garde que le NOM, ne peut porter ni l'un ni l'autre.
            # MEME forme dans les TROIS jumeaux de `leaf_ctx`, cf. `_owned_effect_records`.
            "owned_effects": _owned_effect_records(_fx)}


def _parent_id_of(e) -> "int | None":
    """`IdunBattle.Entities.UnitExtensions$$GetParent(u, state, root: false)` reduit a l'ID --
    `ChildComponent.ParentId`, que le port materialise sur `UnitComponent.parent_id` (cf.
    `engine/runner/components.py::parent_of`, meme substrat).

    ⚠ Le natif fait `state.GetEntity(ParentId)` : un summoner RETIRE de l'etat y rend `null`. Ce
    port rend l'ID BRUT, et l'ecart est INERTE pour son unique consommateur -- le predicat
    `GetParent(<voisin>) == case.unit` : `case.unit` est le sujet du sweep, donc present dans
    l'etat par construction, et une egalite d'ID implique alors que la resolution aurait reussi.

    TRI-ETAT : `None` = pas de parent OU pas mesure, comme `unit_parent_id` du sujet et comme
    `Scene.parent`."""
    from ..runner.components import UnitComponent
    uc = e.get_component(UnitComponent)
    return getattr(uc, "parent_id", None) if uc is not None else None


def _owned_effect_records(effs) -> tuple:
    """`({"type": int|None, "source": int|None, "active": bool}, ...)` -- l'`EffectsOwnedComponent`
    d'une unite, reduit aux TROIS champs de l'`EffectComponent` que les feuilles lisent.

    FOYER UNIQUE des trois jumeaux de `leaf_ctx` : deux constructions separees finiraient par
    diverger de forme, et une feuille lisant une cle absente d'un seul des trois rendrait 0 sans
    erreur (c'est exactement ce que `_unit_record` documente pour lui-meme).

    Les effets CONSOMMES sont ecartes, comme pour le champ `effects` : ils ne sont plus dans
    l'`EffectsOwnedComponent` natif."""
    out = []
    for ef in (effs or ()):
        if getattr(ef, "consumed", False):
            continue
        out.append({"type": getattr(ef, "effect_type", None),
                    "source": getattr(ef, "source", None),
                    "active": bool(getattr(ef, "active", True))})
    return tuple(out)


def _board_maps(state) -> tuple:
    """`(elev_by_pos, neigh_by_pos, walkable_by_pos)` du board. FOYER partage par les deux regimes
    de `runner_tile_leaf_ctx` (sujet present / SPAWN) : les cartes ne dependent d'aucun sujet.
    `neigh_by_pos` est dans l'ordre NATIF (`board.neighbours_native`)."""
    board = getattr(state, "board", None)
    elev_by_pos, neigh_by_pos, walkable_by_pos = {}, {}, {}
    if board is not None:
        for tid, t in board.by_id.items():
            p = (t["col"], t["row"])
            elev_by_pos[p] = t.get("elevation")
            walkable_by_pos[p] = bool(t.get("walkable"))
            neigh_by_pos[p] = [board.coord(n) for n in board.neighbours_native(tid)]
    return elev_by_pos, neigh_by_pos, walkable_by_pos


def _spawn_leaf_ctx(state, parent_id: int) -> dict:
    """Regime SPAWN (`case.unit == null && case.parent != null`) -- call-site
    `IdunBattleLogic.Entities.DSLFactory$$SortTilesByUtilityForSummon` (case-205).

    ⚠ **Ce ctx portait `{"is_spawning": True}` SEUL, et c'etait un ecart CHIFFRE** (#271-r3). Le
    natif n'arrete PAS l'evaluation quand le sujet manque :
    `IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.u003CEvaluateMovementInStepsu003Ed__0$$MoveNext`
    ne rend `Fix64.Zero` que si `case.unit == null` **ET** `case.parent == null` ; sinon il itere.
    Et `...u003CIterateAbilitiesu003Ed__3$$MoveNext` prend alors le PARENT pour sujet
    (`subject = case.unit ?? case.parent`) et **N'EXCLUT PLUS le porteur de lui-meme** -- son
    `continue` est garde par `case.unit != null`. Trois corps du registre yieldent dans ce regime,
    parce qu'ils ne lisent JAMAIS `case.unit` (relus au decompile, pas deduits) :
    `PsychicFortress` (20), `BookOfFate` (5) et la BRANCHE SPAWN de `MawClawsOfThyrax` (5).

    Ce que ce ctx produit, et ce qu'il NE produit PAS :
      * `friend_units`/`enemy_units` -- TOUTES les unites vivantes et positionnees, camp calcule
        par rapport au PARENT, **sans self-exclusion** (le parent y figure : c'est exactement le
        `continue` que le natif desarme). C'est la seule difference de FORME avec le regime a
        sujet, et elle est LOAD-BEARING ;
      * les cartes du board (`elev_by_pos`, `neigh_by_pos`, `walkable_by_pos`) ;
      * **AUCUNE cle de sujet** (`uid`, `self_pos`, `unit_traits`, `unit_faction`,
        `unit_triggered_abilities`, `unit_parent_id`, ...) : il n'y a PAS de sujet, et les
        fabriquer depuis le parent ferait mordre des gates que le natif laisse tomber.

    ⚠ RAYON DE SOUFFLE MESURE avant d'ajouter ces cles : sur les 27 feuilles portees de `Tile(7)`
    x 9 tuiles candidates, **0** change de valeur -- toutes les autres gatent soit sur
    `is_spawning`, soit sur une cle de sujet (qui reste absente), soit lisent leur voisinage dans
    `meta` et non dans le `ctx`. Ajouter ce substrat ne reveille donc QUE la feuille 4."""
    from ..runner.components import OwnerComponent, PositionComponent
    par = state.get_entity(parent_id)
    if par is None:
        return {"is_spawning": True}        # parent introuvable : rien a camper, on ne devine pas
    poc = par.get_component(OwnerComponent)
    par_team = poc.team if poc is not None else None
    fx = getattr(state, "effects", None)
    friends, enemies, fpos = [], [], []
    for uid, e in state.entities.items():
        pc = e.get_component(PositionComponent)
        # MEME filtre que le regime a sujet (vivante ET positionnee) -- mais AUCUNE exclusion de
        # self : le natif ne saute le porteur que `if (case.unit != null && case.unit == ta.Owner)`.
        if pc is None or not _est_vivante(e):
            continue
        rec = _unit_record(e, uid, pc, fx)
        oc = e.get_component(OwnerComponent)
        if oc is not None and par_team is not None and oc.team == par_team:
            friends.append(rec)
            fpos.append(rec["pos"])
        else:
            enemies.append(rec)
    elev_by_pos, neigh_by_pos, walkable_by_pos = _board_maps(state)
    ppc = par.get_component(PositionComponent)
    out = {"is_spawning": True,
           "friend_units": friends, "enemy_units": enemies, "friend_positions": fpos,
           "elev_by_pos": elev_by_pos, "neigh_by_pos": neigh_by_pos,
           "walkable_by_pos": walkable_by_pos}
    # `parent_pos` = `case.parent` du `UtilityMovementCase`, pour la SEULE branche de repli de
    # `TileDistanceUtility` (`else if (c.owner != null) DistanceTo(c, c.owner)`), atteinte depuis
    # #1080 par `CallInReinforcementsAbility$$CreateBehaviour`. CLÉ NEUVE et DISTINCTE de
    # `self_pos` : la fabriquer sous le nom du SUJET ferait mordre les gates que le natif laisse
    # tomber en régime spawn (cf. le bloc « AUCUNE cle de sujet » ci-dessus). Aucune autre feuille
    # ne la lit ; rayon de souffle nul par construction.
    if ppc is not None:
        out["parent_pos"] = (ppc.col, ppc.row)
    return out


def runner_tile_leaf_ctx(state, unit_id: int | None, parent_id: int | None = None) -> dict:
    """Dict `ctx` PAR-DÉCISION des feuilles `Tile(7)`, construit depuis un `State` de RUNNER —
    jumeau de `tile_leaf_ctx` (qui, lui, part d'un `AiDecisionContext` côté DÉCISION).

    C'est le port de `dc.units` / `dc.owner` de
    `IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select` : le natif les met dans le
    `UtilityMovementCase(dc.units, tile, null, null, dc.owner)` que chaque feuille reçoit, donc les
    feuilles gatées sur l'unité (`TriggeredAbilities(2)`, `CapturePoint(25)`, `PowerUp(27)`,
    `DespoiledGround(29)`, `HeroLikeDoorOpening(31)`, …) le VOIENT. Tant que ce dict était vide,
    elles rendaient toutes 0 — c'était le « non couvert » de case-165, et la cause du résidu §4.

    `unit_id is None` = `case.unit == null`. Deux régimes, distingués par le PARENT (case-205) :
      * `parent_id` renseigné → `{"is_spawning": True}` — le call-site `SortTilesByUtilityForSummon`.
        Aucune clé de sujet n'est produite (il n'y a PAS de sujet), et `is_spawning` est ce que les
        feuilles lisent là où le natif inline
        `IdunBattle.AI.Utilities.UtilityMovementCase$$get_IsSpawning` ;
      * `parent_id` nul → `{}` (ni sujet ni parent : aucune feuille gatée ne peut rien rendre).

    Clés produites (mêmes noms/formes que `tile_leaf_ctx`) : `unit_triggered_abilities`,
    `unit_traits`, `unit_faction`, `uid`, `unit_parent_id`, `self_pos`, `friend_units`/`enemy_units`
    (`{pos, vis, id, triggered, traits, effects}`, self exclu), `friend_positions`, `elev_by_pos`,
    `neigh_by_pos` (ordre NATIF `board.neighbours_native`), `walkable_by_pos`.

    #456-r1 — `unit_triggered_abilities` et le `triggered` des voisins sortent désormais du substrat
    d'ENTITÉ (`UnitContext.triggered_abilities` = l'`AbilitiesComponent`, seedé depuis
    `unitAbilityStates` par `snapshot._load_triggered_abilities`), plus du kit gameconfig par
    `visualId`. Sans canal (`load_state` sans transport ambiant) le repli gameconfig est intact.

    NON produites, donc feuilles muettes ici (résidus nommés, mêmes que côté décision) : `scene` /
    `hpmax_by_id` / `enemies` (→ `FuryOfTheAncientsPlaybook` rend 0), `is_territory_by_pos` et
    `tile_effect_type_ids_by_pos` (le `meta` de ce foyer ne les porte pas non plus)."""
    from ..runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                     StatsComponent, UnitComponent)
    if unit_id is None:
        # `case.unit == null` : PAS de sujet. `is_spawning` = `get_IsSpawning` = unit null ET parent
        # non nul -- c'est la signature EXACTE du call-site SortTilesByUtilityForSummon (case-205).
        if parent_id is None:
            return {}                       # ni sujet ni parent : aucune feuille ne peut rien rendre
        return _spawn_leaf_ctx(state, parent_id)
    me = state.get_entity(unit_id)
    if me is None:
        return {}
    mpc = me.get_component(PositionComponent)
    muc = me.get_component(UnitComponent)
    moc = me.get_component(OwnerComponent)
    msc = me.get_component(StatsComponent)
    mhc = me.get_component(HealthComponent)          # #983 -- PV du MOVER, cf. `self_hp` plus bas
    my_team = moc.team if moc is not None else None
    my_vis = muc.visual_id if muc is not None else None
    fx = getattr(state, "effects", None)
    friends, enemies, fpos = [], [], []
    for uid, e in state.entities.items():
        pc = e.get_component(PositionComponent)
        # `if (case.unit == ability.Owner) continue` : le sujet est self-EXCLU. C'est la seule
        # difference avec le regime SPAWN, ou le natif desarme ce `continue` (cf. `_spawn_leaf_ctx`).
        if pc is None or not _est_vivante(e) or uid == unit_id:
            continue
        # Kit DECLENCHE/ACTIF/traits du voisin : foyer unique `_unit_record` -- feuilles
        # SteppableUnit(20)/AttractToDecoys(64), noeud `!ActorHasTriggeredAbility(Target, 1120)` de
        # `SaviorProtocolsPlaybook`, predicat `HasActiveAbility(f, DoctrinaImperatives)` de
        # `RadSaturationPlaybook` (#477-r29).
        rec = _unit_record(e, uid, pc, fx)
        oc = e.get_component(OwnerComponent)
        if oc is not None and my_team is not None and oc.team == my_team:
            friends.append(rec)
            fpos.append(rec["pos"])
        else:
            enemies.append(rec)
    elev_by_pos, neigh_by_pos, walkable_by_pos = _board_maps(state)
    from ..runner.components import parent_of
    _par = parent_of(state, unit_id)
    return {# #456-r1 : substrat d'ENTITE, exactement comme `unit_traits` juste en dessous -- le
            # dispatcher natif itere l'`AbilitiesComponent`, pas le kit gameconfig par visualId.
            # Ce foyer-la etait reste sur le gameconfig alors que la face DECISION avait ete
            # recablee sur le canal live par #304 ; il en resultait un kit FAUX DANS LES DEUX SENS
            # (mesure : 3 unites sur 4 divergentes, dont une ou le port iterait un id que la
            # bataille n'avait pas monte).
            "unit_triggered_abilities": entity_triggered_ability_ids(
                msc.ctx if msc is not None else None, my_vis),
            # #477-r29 : kit ACTIF du MOVER. `GetAdjacentFriends(tile, case.Unit)` n'exclut PAS
            # `case.Unit` (cf. `playbook/friends_in_range.py`), et l'unite est encore SUR SON ORIGINE
            # pendant tout le sweep : elle entre donc dans son propre voisinage des que l'origine est
            # ring-1 de la tuile candidate, et le predicat la teste comme les autres.
            "unit_active_abilities": entity_active_ability_ids(
                msc.ctx if msc is not None else None, my_vis),
            # #225 : substrat d'ENTITE (cf. `entity_trait_ids`) -- le sujet peut s'etre vu accorder
            # un trait EN BATAILLE (`AddTrait`), que le kit gameconfig par visualId ignore.
            "unit_traits": entity_trait_ids(msc.ctx if msc is not None else None, my_vis),
            "uid": unit_id,
            # #443-r1 : `IdunBattle.Entities.UnitExtensions$$GetParent(case.Unit, state)` -- le lien
            # enfant -> SUMMONER (`ChildComponent.ParentId`), que lit la face MOVE de
            # `SaviorProtocolsPlaybook`. A NE PAS confondre avec le parametre `parent_id` de cette
            # fonction, qui est le `dc.parent` du call-site SUMMON (case-205) : ici c'est le parent
            # DU SUJET, la un sujet de remplacement quand `case.unit` est nul.
            # `parent_of` resout l'ENTITE (`state.GetEntity(ParentId)`), pas l'id brut : un summoner
            # retire de l'etat rend `None`, comme le `GetParent` natif -- et le test `== u` du corps
            # est alors faux, ce qui est bien le comportement voulu.
            "unit_parent_id": (_par.id if _par is not None else None),
            # `HasFaction(case.unit, <UnitFaction>)` cote offline (#241) — cf. `tile_leaf_ctx`.
            "unit_faction": faction_value(my_vis),
            # `get_IsSpawning` = `unit == null && parent != null` : ici le sujet EXISTE -> False.
            "is_spawning": False,
            "self_pos": (mpc.col, mpc.row) if mpc is not None else None,
            # PV du MOVER (#983) -- pendant de `self_pos` sur l'axe des PV, et pour la MEME raison :
            # `SanguinaryPriestPlaybook` ne fait AUCUN `RemoveAll(u.Id == case.Unit.Id)`, donc le
            # mover entre dans son propre `GetAdjacentUnits(tile, friendsOf: case.Unit)` -- `IsFriend`
            # n'ecarte pas l'egalite. Sans ces deux cles son terme DAMAGED serait sous-compte de 1
            # des que son origine tombe en ring-1 de la tuile candidate. TRI-ETAT (cf. `_unit_record`).
            "self_hp": (mhc.hp if mhc is not None else None),
            "self_hp_max": (mhc.hp_max if mhc is not None else None),
            # EFFETS du MOVER (#922) -- pendant EXACT de `self_pos` sur l'axe des effets, et pour la
            # MEME raison : les corps qui ne font aucun `RemoveAll(u.Id == case.Unit.Id)` voient le
            # mover dans leur propre voisinage (il est encore SUR SON ORIGINE pendant tout le sweep).
            # `IntoxicatingElixirPlaybook` filtre ce voisinage PAR EFFET, donc sans cette cle il
            # sous-compterait de 1 des que le porteur est lui-meme debuffe -- regime COURANT chez
            # les Emperor's Children, que `ThrillSeekers` met en `Thrilled` a leur propre attaque.
            # MEME forme que le champ `effects` d'un voisin (`_unit_record`) : noms non consommes.
            "self_effects": tuple(ef.name for ef in ((fx.by_unit.get(int(unit_id), []) if fx else []))
                                  if not ef.consumed and ef.name),
            # #175-r1 -- pendant de `self_effects` sur l'axe (type, source). La branche EFFET de
            # `MoveTowardsUnitUtility.<d__15>` (`GetActiveEffects` -> `FirstOrDefault(allUnits)`)
            # n'exclut PAS `case.Unit` : le mover est un porteur candidat comme les autres, la ou
            # la branche ABILITY, elle, l'ecarte explicitement (`u.Id != case.Unit.Id`).
            "self_owned_effects": _owned_effect_records(
                fx.by_unit.get(int(unit_id), []) if fx else []),
            "friend_units": friends, "enemy_units": enemies, "friend_positions": fpos,
            "elev_by_pos": elev_by_pos, "neigh_by_pos": neigh_by_pos,
            "walkable_by_pos": walkable_by_pos}


class _SceneTileEffect:
    """Effet de TUILE vu par `sort_tiles_by_utility` (Loop1 de `TileEffectsUtility`) — duck-type
    minimal (`.name`, `.consumed`) de ce que le canal runner range dans `EffectsState.by_unit`
    indexé par id de TUILE (l'entité-tuile porte ses effets comme une unité, case-102). Le canal
    de la face PRÉDICTION est `Scene.tile_effects_by_pos` (`tileMeta.effects[].name`), indexé par
    POSITION : cette classe n'existe que pour le re-présenter sous la MÊME forme, sans dupliquer
    la logique de `sort_tiles_by_utility`."""
    __slots__ = ("name", "consumed")

    def __init__(self, name: str):
        self.name, self.consumed = name, False


class SceneTileState:
    """Adaptateur `Scene` -> l'objet d'état que `sort_tiles_by_utility` interroge (`.board` et
    `.effects.by_unit[tileId]`).

    Il ne peut PAS être la `Scene` elle-même : `Scene.effects` est une MÉTHODE (`effects(uid)`),
    alors que le foyer de tri attend l'`EffectsState` (attribut `.by_unit`). Passer la `Scene` nue
    ferait donc lever `getattr(state, "effects")` sur une bound method — dégradation silencieuse
    exactement du genre que ce dépôt bannit.

    `by_unit` est construit UNE FOIS depuis `Scene.tile_effects_by_pos` (canal `tileMeta`, DYNAMIQUE)
    croisé avec `Scene.board` pour passer de la POSITION à l'id de tuile. Carte absente -> dict vide
    -> le foyer retombe sur le seul `terrain_tile_effects` (repli statique déjà en place)."""
    __slots__ = ("board", "effects")

    class _Effects:
        __slots__ = ("by_unit",)

        def __init__(self, by_unit):
            self.by_unit = by_unit

    def __init__(self, scene):
        self.board = getattr(scene, "board", None)
        by_unit: dict = {}
        fx = getattr(scene, "tile_effects_by_pos", None)
        if fx and self.board is not None:
            for pos, names in fx.items():
                if not names:
                    continue
                tid = self.board.id_at(pos[0], pos[1])
                if tid is None:
                    continue
                by_unit[int(tid)] = [_SceneTileEffect(n) for n in names if n]
        self.effects = SceneTileState._Effects(by_unit)


def scene_tile_leaf_ctx(scene, unit_id: int | None) -> dict:
    """Dict `ctx` PAR-DÉCISION des feuilles `Tile(7)`, construit depuis la `Scene` de PRÉDICTION —
    TROISIÈME jumeau de `runner_tile_leaf_ctx` (State de runner) et `tile_leaf_ctx`
    (AiDecisionContext). MÊMES clés, MÊME sémantique d'absence.

    Il existe parce que `playbook.prediction.make_damage_predictions` ne reçoit QUE la `Scene` : le
    batch EXPLOSION de `IdunBattle.AI.Playbook.Loki.RammingSpeedPlaybook$$MakeDamagePredictions`
    (#383) appelle `RammingSpeedAbility$$GetTileToMoveTo`, donc le foyer de tri, donc ce `ctx`. Sans
    lui la feuille `RammingSpeed_MostAdjacentEnemies` (54) rendrait 0 partout et le bucket
    dégénérerait en `Tile(7)` seul — MESURÉ changeant la tuile en #353-r1 (le port livré rend (5,7),
    `Tile(7)` seul rend (3,7)), donc un voisinage FAUX et des events FAUX.

    Le tri ami/ennemi est celui de `runner_tile_leaf_ctx` — l'ÉQUIPE du sujet (`case.unit`), pas le
    `ctrl` de la face décision : `RammingSpeed_MostAdjacentEnemies` compte
    `BattleQuery$$GetAdjacentEnemies(tuile, case.unit, false)`, qui résout le camp par
    `OwnerComponent.get_CurrentPlayerEntityId(case.unit)`. Un caster du camp adverse (régime courant
    de `aiPlaybookPredict`) inverserait les deux listes si on lisait `ctrl`.

    `unit_id is None` -> `{}` (pas de sujet ; ce foyer n'a pas de call-site SUMMON côté prédiction,
    donc jamais le régime `is_spawning` de case-205)."""
    if unit_id is None:
        return {}
    units = list(getattr(scene, "units", None) or [])
    my_team = scene.team(unit_id)
    my_vis = (scene.vis_by_id or {}).get(unit_id)
    eff = getattr(scene, "eff_state", None)
    fx_by_unit = getattr(eff, "by_unit", None) or {}

    def _effect_names(uid):
        return tuple(e.name for e in fx_by_unit.get(int(uid), []) if not e.consumed and e.name)

    def _owned(uid):
        return _owned_effect_records(fx_by_unit.get(int(uid), []))

    friends, enemies, fpos = [], [], []
    for u in units:
        uid = u.get("id")
        p = u.get("pos") or {}
        if uid is None or uid == unit_id or not u.get("alive") or p.get("col") is None:
            continue
        vis = u.get("visualId")
        rec = {"pos": (p["col"], p["row"]), "vis": vis, "id": uid,
               # #456-r1 : substrat d'ENTITE (cf. `runner_tile_leaf_ctx`) -- `Scene.ctx(uid)` EST le
               # `UnitContext` que `snapshot._load_triggered_abilities` seede (meme objet, cf.
               # `Scene.from_state`), donc ce jumeau se ferme par le MEME foyer, sans canal propre.
               "triggered": tuple(entity_triggered_ability_ids(scene.ctx(uid), vis)),
               # #477-r29 : cf. `runner_tile_leaf_ctx` -- predicat de `RadSaturationPlaybook`.
               "active": tuple(entity_active_ability_ids(scene.ctx(uid), vis)),
               "traits": entity_trait_names(scene.ctx(uid), vis),
               # #983 -- cf. `_unit_record` : substrat d'`UnitExtensions$$IsDamagedUnit`. `Scene.hp`
               # et `Scene.hpmax` lisent le MEME `HealthComponent` (`Scene.from_state`), et rendent
               # deja `None` sur un id hors tables -- le tri-etat est donc porte par le foyer.
               "hp": scene.hp(uid), "hp_max": scene.hpmax(uid),
               # #433-r4-r3-r2 / #175-r1 -- cf. `_unit_record`, meme role et meme forme dans les
               # TROIS jumeaux. `Scene.parent` collapse « pas de parent » et « pas mesure ».
               "parent": scene.parent(uid),
               "effects": _effect_names(uid),
               "owned_effects": _owned(uid)}
        if my_team is not None and u.get("team") == my_team:
            friends.append(rec)
            fpos.append(rec["pos"])
        else:
            enemies.append(rec)
    board = getattr(scene, "board", None)
    elev_by_pos, neigh_by_pos, walkable_by_pos = {}, {}, {}
    if board is not None:
        for tid, t in board.by_id.items():
            pp = (t["col"], t["row"])
            elev_by_pos[pp] = t.get("elevation")
            walkable_by_pos[pp] = bool(t.get("walkable"))
            neigh_by_pos[pp] = [board.coord(n) for n in board.neighbours_native(tid)]
    return {"unit_triggered_abilities": entity_triggered_ability_ids(scene.ctx(unit_id), my_vis),
            # #477-r29 : cf. `runner_tile_leaf_ctx` -- le mover compte pour lui-meme.
            "unit_active_abilities": entity_active_ability_ids(scene.ctx(unit_id), my_vis),
            "unit_traits": entity_trait_ids(scene.ctx(unit_id), my_vis),
            "uid": unit_id,
            # #433-r4-r3-r3 : `IdunBattle.Entities.UnitExtensions$$GetParent(case.Unit, state,
            # root: false)` -- le lien enfant -> SUMMONER (`ChildComponent.ParentId`). Ce TROISIEME
            # jumeau etait le SEUL des trois a ne pas le poser, alors que le canal existe des deux
            # cotes depuis #378 (`Scene.parent` : `combatSnapshot.units[].parentId` en live,
            # `UnitComponent.parent_id` offline) : les deux feuilles qui le GATENT rendaient donc 0
            # sur la face PREDICTION seule -- `savior_protocols.py` (bonus PARENT) et
            # `playbook/non_owner.py` (gate `GetParent(case.unit) != owner`, dont depend le terme
            # `EcogSupport`). MEME semantique d'absence que les deux autres producteurs : `None` =
            # pas de parent OU pas mesure (`Scene.parent` collapse les deux, cf. sa docstring), et
            # les deux lecteurs se taisent alors -- degradation PARTIELLE, jamais un zero global.
            "unit_parent_id": scene.parent(unit_id),
            "unit_faction": faction_value(my_vis),
            "is_spawning": False,
            "self_pos": scene.pos(unit_id),
            # PV du MOVER (#983) -- cf. `runner_tile_leaf_ctx`, meme role et meme raison.
            "self_hp": scene.hp(unit_id), "self_hp_max": scene.hpmax(unit_id),
            # EFFETS du MOVER (#922) -- cf. `runner_tile_leaf_ctx`, meme role et meme forme.
            "self_effects": tuple(_effect_names(unit_id)),
            # #175-r1 -- cf. `runner_tile_leaf_ctx`.
            "self_owned_effects": _owned(unit_id),
            "friend_units": friends, "enemy_units": enemies, "friend_positions": fpos,
            "elev_by_pos": (getattr(scene, "elev_by_pos", None) or elev_by_pos),
            "neigh_by_pos": neigh_by_pos, "walkable_by_pos": walkable_by_pos,
            "scene": scene,
            "hpmax_by_id": dict(getattr(scene, "hpmax_by_id", None) or {})}


def _adjacent_units(ctx, uid):
    """{pos,traits,effects} des AMIS (ctrl, self-exclu) et ENNEMIS (non-ctrl) vivants positionnés —
    mirror des query natives `GetAdjacentFriends`/`GetAdjacentEnemies` du corps AdjacentUnitPreference
    (#57i). Les traits (gameconfig) alimentent les filtres `FilterAdjacent*` (ex. FabricatorClaw =
    Mechanical=5) ; les `effects` (noms bruts du `EffectsOwnedComponent`, cf. decisionView) alimentent
    la famille `AUnitEffectsUtility` (feuilles 10/11/12, cf. `apply_tile_attributes`).
    getattr-tolerant : un contexte sans `units` (NCContext) rend deux listes vides -> feuille silencieuse.

    #225 -- les traits sortent du substrat d'ENTITE (`Scene.ctx(id).traits` = le `UnitContext` que le
    leaf DSL `AddTrait` mute), et non plus du kit gameconfig par visualId. Identique au bit pres tant
    qu'aucun trait n'a ete accorde en bataille (`UnitContext.from_snapshot` seede exactement
    `gameconfig.unit(vis).traits`) ; sur le chemin OFFLINE (`Scene.from_state`) c'est le meme objet que
    `StatsComponent.ctx`, donc le trait accorde y est VU. `scene` absente / id hors tables -> borne
    statique (`entity_trait_names(None, vis)`).

    #241 -- chaque enregistrement porte aussi son `id` et son kit DECLENCHE (`triggered`), la donnee
    que reclament les deux feuilles à occupant steppable : `AttractToDecoysUtility` (64) compte les
    amis porteurs de `DecoysAndMisdirection` (1304) sur `GetAllAliveUnits`, et `SteppableUnitUtility`
    (19) teste `SpikySting`/`LandMine` sur l'occupant. La source est la lecture live du
    `TriggeredAbilityComponent` (`ctx.live_triggered_kits()`, UN seul `unitAbilityStates` pour toute
    la bataille), avec repli sur le kit gameconfig quand elle ne rend rien pour cette entite.

    #433-r4-r3-r1-r3 -- LE REMPLACEMENT, ET POURQUOI L'UNION MENTAIT ICI AUSSI. Ce producteur etait
    le DERNIER des trois jumeaux a UNIONNER les deux substrats. Le MOVER est passe au remplacement
    par #304 et les deux autres jumeaux (`runner_tile_leaf_ctx`, `scene_tile_leaf_ctx`) par #456-r1,
    tous deux sur la meme mesure : une union ne peut qu'AJOUTER, donc elle REINTRODUIT un passif que
    la bataille n'a PAS monte. Les VOISINS, eux, sont restes en union -- et le defaut se voyait
    exactement la ou un montage ECARTE le kit du gameconfig, c'est-a-dire sur une GREFFE.
    MESURE (2026-08-03, re-mesuree LIVE le 2026-08-15 sur `t6dpr4k06g`, montage #433-r4-r3-r1 :
    `graft_passive_ability('astraBullgryn', 'WatchedOver', replace=True)`) :

        kit greffon -- port = [1028, 1524, 1030]    AbilitiesComponent NATIF = [1524, 1030]

    `1028` = `AvalancheOfMuscle`, le passif de kit que la greffe a justement REMPLACE dans
    `BC.Units[].PassiveAbilities`. Le port le voyait quand meme, par cette union.
    Sans effet sur le verdict de #433-r4-r3-r1 (son A/B n'ampute que l'ability mesuree, et 1028
    n'est a aucun registre non-owner), mais tout montage par greffe qui compterait les termes EN
    BLOC sur-estimerait le port. Le repli gameconfig reste ENTIER quand la lecture live est vide
    (RPC indisponible, entite absente, contexte OFFLINE sans pont) : c'est le seul regime que le
    motif d'union protegeait, et il est preserve tel quel."""
    scene = getattr(ctx, "scene", None)
    _kits_fn = getattr(ctx, "live_triggered_kits", None)
    live_kits = _kits_fn() if callable(_kits_fn) else {}
    # #983 -- cf. `_unit_record`. `hp` vient de `decisionView.units[].hp` (le meme champ que
    # `AiDecisionContext.hp_cur_by_id`), `hp_max` de `observeBattle` via `ctx.hpmax_by_id`. TRI-ETAT :
    # une table absente rend `None` par voisin, JAMAIS 0 -- un maximum a 0 ferait passer toute unite
    # pour intacte, et `IsDamagedUnit` se tairait partout sans que rien ne le signale.
    _hpmax = getattr(ctx, "hpmax_by_id", None)
    friends, enemies = [], []
    for u in (getattr(ctx, "units", None) or []):
        pos = u.get("pos")
        if not (u.get("alive") and pos):
            continue
        _uctx = scene.ctx(u.get("id")) if scene is not None else None
        # #433-r4-r3-r1-r3 : REMPLACEMENT, pas union (cf. la docstring). Meme forme que le MOVER
        # dans `tile_leaf_ctx` -- la lecture live FAIT AUTORITE des qu'elle rend quelque chose pour
        # cette entite, sinon on garde le kit gameconfig.
        _trig = list(triggered_ability_ids(u.get("visualId")))
        _live = list(live_kits.get(u.get("id")) or ())
        if _live:
            _trig = _live                   # l'AbilitiesComponent REEL, tel que le natif l'itere
        rec = {"pos": (pos["col"], pos["row"]),
               # `vis` — id d'unite du voisin, l'argument du noeud `UnitsWithId(sel, <unitId>)`
               # (GeminaeSuperiaPlaybook, case-165b). Meme cle que cote runner.
               "vis": u.get("visualId"),
               "id": u.get("id"),
               "triggered": tuple(_trig),
               # #477-r29 : kit ACTIF du voisin -- l'argument du predicat de `RadSaturationPlaybook`
               # (`HasActiveAbility(f, 0x45e = DoctrinaImperatives)`). Meme substrat d'ENTITE que
               # `traits` juste en dessous (`Scene.ctx(id).active_abilities`, seede par
               # `playbook.scene._seed_measured_actives`), avec repli kit gameconfig.
               "active": tuple(entity_active_ability_ids(_uctx, u.get("visualId"))),
               "traits": entity_trait_names(_uctx, u.get("visualId")),
               "hp": u.get("hp"),
               "hp_max": (_hpmax.get(u.get("id")) if isinstance(_hpmax, dict) else None),
               # #433-r4-r3-r2 / #175-r1 -- cf. `_unit_record`, meme role et meme forme dans les
               # TROIS jumeaux.
               "parent": (scene.parent(u.get("id")) if scene is not None else None),
               "effects": tuple(e.get("name") if isinstance(e, dict) else e
                                for e in (u.get("effects") or ())),
               # Canal `decisionView.units[].effects` : le hook publie DEJA `effectType`, `source`
               # (`EffectComponent.SourceUnitId@+0x10`) et `active` par effet
               # (`frida/hooks/game/effects.ts::EffectInfo`) -- la reserve « `decisionView` publie-t-il
               # un `source` ? non verifie » de `case-175r` §3 est LEVEE, il le publie.
               # ⚠ Canal ACTIF-ONLY par defaut (`readEffectsByUnit` droppe les inactifs sauf
               # `includeInactive`) : le champ `active` y vaut donc `True` sur toutes les entrees
               # que la face DECISION voit. C'est la MEME borne que le champ `effects` ci-dessus.
               "owned_effects": tuple(
                   {"type": e.get("effectType"), "source": e.get("source"),
                    "active": bool(e.get("active", True))}
                   for e in (u.get("effects") or ()) if isinstance(e, dict))}
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
    me = getattr(ctx, "me", None) or {}
    uid = getattr(ctx, "uid", None)
    _scene = getattr(ctx, "scene", None)
    _me_ctx = _scene.ctx(uid) if (_scene is not None and uid is not None) else None
    friend_units, enemy_units = _adjacent_units(ctx, uid)
    mp = me.get("pos") or {}
    self_pos = (mp["col"], mp["row"]) if mp.get("col") is not None else None
    # Kit DECLENCHE du mover. Le natif itere l'AbilitiesComponent ECS (donc passifs de kit +
    # abilities accordees par TRAIT + RELIQUES) ; `triggered_ability_ids` ne connait que les
    # `passiveAbilities` du gameconfig.
    #
    # #304 -- la lecture live du `TriggeredAbilityComponent` (`ctx.live_triggered_ability_ids`, RPC
    # `unitAbilityStates`) FAIT AUTORITE des qu'elle rend quelque chose pour cette entite : c'est
    # LITTERALEMENT la collection que `IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.
    # u003CEvaluateMovementInStepsu003Ed__2$$MoveNext` itere. L'UNION anterieure (N13) ne pouvait
    # qu'AJOUTER, jamais retirer -- elle REINTRODUISAIT donc un passif que la bataille n'a PAS.
    # MESURE (#304, fixture `MDA_FIXTURE`, re-jouee apres rebase sur `ae87046f`) :
    #   seed BC `PassiveAbilities: []` -> live `[1486]`, gameconfig `[1529]`, union `[1529, 1486]`,
    #                                     AbilitiesComponent natif `[1486]`  <- l'union MENT
    #   seed BC kit REEL              -> live `[1529, 1486]`, gameconfig `[1529]`, union idem
    # La 2e ligne est ce qui rend le remplacement SUR : dans le regime normal la lecture live est un
    # SUR-ENSEMBLE du gameconfig (`1486` n'est pas un `passiveAbilities`), donc remplacement == union
    # et le gain de N13 (abilities accordees par TRAIT / RELIQUE) est intact. L'ecart de la 1re ligne
    # etait INVISIBLE tant qu'aucun playbook n'etait enregistre pour 1529 -- c'est le port de #304
    # qui l'a rendu observable.
    # Le repli gameconfig reste ENTIER quand la lecture live est vide (RPC indisponible, entite
    # absente, contexte OFFLINE `rid` faux -> `[]`, cf. la docstring de l'accesseur) : c'est le seul
    # regime que le motif N13 protegeait, et il est preserve tel quel.
    kit = list(triggered_ability_ids(me.get("visualId")))
    _live_fn = getattr(ctx, "live_triggered_ability_ids", None)
    if callable(_live_fn) and uid is not None:
        _live = list(_live_fn(uid) or ())
        if _live:
            kit = _live                     # l'AbilitiesComponent REEL, tel que le natif l'itere
    return {"unit_triggered_abilities": kit,
            # #477-r29 : kit ACTIF du MOVER -- `GetAdjacentFriends(tile, case.Unit)` n'exclut pas
            # `case.Unit`, qui est encore sur son origine pendant le sweep (cf.
            # `runner_tile_leaf_ctx`).
            "unit_active_abilities": entity_active_ability_ids(_me_ctx, me.get("visualId")),
            # Face DECISION : le `case.unit` est TOUJOURS le mover (le sweep part d'une unite
            # existante), donc jamais le regime `IsSpawning` du call-site SUMMON (case-205).
            "is_spawning": False,
            # IDS `UnitTrait` du MOVER — l'argument que les 7 feuilles à gate de trait passent à
            # `IdunBattle.Entities.UnitExtensions$$HasTrait(case.unit@+0x10, <traitId>)` (le `case`
            # porte l'unité qui évalue la tuile : `CapturePointTileUtility.<d__3>`, `PowerUpTile
            # Utility.<d__2>`, `DespoiledGroundUtility.<d__5>`, `SummonDislikeDoorOpeningUtility
            # .<d__2>`, `HeroDoorOpeningUtility.<d__2>`, `AttractMechanicalsUtility.<d__1>`,
            # `MoveTowardsUnitUtility.<d__15>`). Source = `entity_trait_ids` (#225) : le substrat
            # d'ENTITE — kit gameconfig seedé dans `UnitContext.traits` + traits ACCORDÉS EN BATAILLE
            # par le leaf DSL `AddTrait` + pseudo-trait de grande-alliance. `Scene` absente / uid hors
            # tables -> borne statique par visualId (comportement antérieur).
            "unit_traits": entity_trait_ids(_me_ctx, me.get("visualId")),
            # Valeur d'enum `UnitFaction` du MOVER -- l'argument que les feuilles a gate de faction
            # passent a `IdunBattle.Entities.UnitExtensions$$HasFaction(case.unit, <UnitFaction>)`
            # (`AttractToDecoysUtility` 0xf=Genestealers, `SaviorProtocolsUtility` 9=Tau). Le natif
            # compare `System.Enum.ToString(UnitFaction)` au `FactionComponent+0x30` ; le substrat
            # offline est le `FactionId` gameconfig (#241). visualId inconnu -> None -> gate ferme.
            "unit_faction": faction_value(me.get("visualId")),
            "friend_positions": ctx.fpos,
            # {pos,traits} vivants self-exclu — branches AMIS(B1)/ENNEMIS(B2) de AdjacentUnitPreference
            # (#57i : traits pour les filtres, ex. FabricatorClaw garde les amis Mechanical).
            "friend_units": friend_units,
            "enemy_units": enemy_units,
            "uid": uid,
            # #443-r1 : `IdunBattle.Entities.UnitExtensions$$GetParent(case.Unit, state)` -- le lien
            # enfant -> SUMMONER que lit la face MOVE de `SaviorProtocolsPlaybook`. Canal `Scene.
            # parent` (#378, `combatSnapshot.units[].parentId` en live, `UnitComponent.parent_id`
            # offline). `Scene` absente -> None -> le seul terme PARENT se tait, le terme FRIEND
            # reste verse (degradation PARTIELLE et nommee, pas un zero global).
            "unit_parent_id": (getattr(_scene, "parent", lambda _u: None)(uid)
                               if (_scene is not None and uid is not None) else None),
            # Origine de l'unite qui evalue. Les corps `friends_in_range.py` (AstartesBanner 1106,
            # KardiocoreGalvanus 1457) comptent les amis AUTOUR de la tuile candidate SANS exclure
            # `case.unit` : l'unite est encore SUR SON ORIGINE pendant tout le sweep, elle compte
            # donc pour elle-meme des que cette origine tombe dans le voisinage evalue (N13).
            "self_pos": self_pos,
            # PV du MOVER (#983) -- pendant de `self_pos` sur l'axe des PV, meme raison
            # (cf. `runner_tile_leaf_ctx`). Substrats : `decisionView.units[].hp` du mover et
            # `observeBattle` via `ctx.hpmax_by_id`, exactement ceux que `_adjacent_units` lit.
            "self_hp": me.get("hp"),
            "self_hp_max": ((getattr(ctx, "hpmax_by_id", None) or {}).get(uid)
                            if isinstance(getattr(ctx, "hpmax_by_id", None), dict) else None),
            # EFFETS du MOVER (#922) -- pendant de `self_pos` sur l'axe des effets, meme raison
            # (cf. `runner_tile_leaf_ctx`). Substrat : le canal `decisionView.effects` du mover,
            # exactement celui que `_adjacent_units` lit pour ses voisins.
            # ⚠ CANAL ACTIF-ONLY (#100) : `decisionView` ne publie que les effets ACTIFS, la ou le
            # selecteur natif `EntitiesWithAnyEffect` ne filtre PAS sur l'activite. Ecart NOMME,
            # commun a toute la face DECISION (le champ `effects` des voisins a la meme borne).
            "self_effects": tuple(e.get("name") if isinstance(e, dict) else e
                                  for e in (me.get("effects") or ())),
            # #175-r1 -- cf. `runner_tile_leaf_ctx`. MEME canal (et MEME borne actif-only) que le
            # champ `owned_effects` des voisins, cf. `_adjacent_units`.
            "self_owned_effects": tuple(
                {"type": e.get("effectType"), "source": e.get("source"),
                 "active": bool(e.get("active", True))}
                for e in (me.get("effects") or ()) if isinstance(e, dict)),
            "enemies": getattr(ctx, "enemies", None) or [],
            "elev_by_pos": getattr(ctx, "elev_by_pos", None),
            "neigh_by_pos": getattr(ctx, "neigh_by_pos", None),
            # Gate STATIQUE de placement `CanAddUnit` (`battle_query.can_add_unit`) — la carte que
            # consomme le noeud `CanAddUnit(AdjacentTiles(tuile))` du `GeminaeSuperiaPlaybook`
            # (case-165b). Meme statut que les deux cartes ci-dessus : constante sur la decision,
            # valeur lue dependante de la tuile candidate. Absente -> `can_add_unit` degrade en
            # permissif (borne SUP), comportement deja en vigueur pour HammerOfWrath.
            "walkable_by_pos": getattr(ctx, "walkable_by_pos", None),
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

    - `neighbor_effect_names` <- les EFFETS PORTES par les AMIS du voisinage de la tuile candidate,
      la donnee que consomme la famille `AUnitEffectsUtility` (feuilles 10/11/12). Les trois
      `GetSourceUnits` concrets donnent les trois voisinages, TOUS `MINUS` le selecteur de l'unite
      qui evalue (`IdunBattle.DSL.TargetsSelector$$op_Subtraction`), donc self EXCLU :
        * `IdunBattle.AI.Utilities.UnitEffectsAdjacentUtility$$GetSourceUnits`
          = `IdunBattleLogic.Entities.DSLFactory$$AdjacentFriends(..., 1)`   -> ring-1
            (`IterateAdjacentTiles` -> porte d'elevation `|Delta| < 2`, cf. `battle_query.is_adjacent`)
        * `IdunBattle.AI.Utilities.UnitEffectsSurroundingUtility$$GetSourceUnits`
          = `IdunBattleLogic.Entities.DSLFactory$$SurroundingFriends(..., 1, 1, 3)` -> DISQUE r=1
        * `IdunBattle.AI.Utilities.UnitEffectsRangedUtility$$GetSourceUnits`
          = `IdunBattleLogic.Entities.DSLFactory$$SurroundingFriends(..., 2, 1, 3)` -> DISQUE r=2
      Le corps partage `IdunBattle.AI.Utilities.AUnitEffectsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext`
      itere ces unites, puis leur `EffectsOwnedComponent`, prend `EffectType.ToString()` de chaque
      effet et somme `HasUtilityValue(nom) ? GetUtilityValue(nom) : 0` dans la categorie BC de la
      sous-classe. Ces trois feuilles etaient PORTEES mais DORMANTES : `meta.neighbor_effect_names`
      n'etait plombe par AUCUN appelant (residu N13, `C4_09`/31337 pas 22 : `PathOfCommand_ExtraDmg`
      porte par l'Autarch a 2 hex valait +10 natif, 0 cote port).
      ⚠ Les 2e/3e arguments litteraux de `SurroundingFriends` (1, 3) ne sont pas resolus : le
      voisinage MESURE (disque hex plein, r=2, self exclu) suffit a reproduire la mesure.

    - `steppable` / `decoy_gate` / `decoy_friend_count` <- l'OCCUPANT STEPPABLE de la tuile candidate
      (#241). Meme statut que `neighbor_effect_names` ci-dessus : deux feuilles PORTEES mais INERTES,
      faute d'appelant qui plombe leur metadonnee.
        * `SteppableUnitUtility` (19) et `AttractToDecoysUtility` (64) appellent toutes deux
          `IdunBattle.Entities.TileExtensions$$GetSteppableUnit(tuile, ctx, out u)` =
          `IdunBattle.Entities.UnitExtensions$$GetUnit` (l'occupant, UNE entite par tuile via
          `TileContentComponent.IsFilled`) filtre sur le trait `0x1b` = `UnitTrait.Steppable`.
        * `decoy_gate` = le gate de la feuille `DecoysAndMisdirection_AttractToDecoys` : occupant steppable PRESENT et
          `!UnitExtensions.IsEnemy(u, case.unit, ctx)` -- ni le trait `Decoy` ni la faction de
          l'occupant n'y interviennent.
        * `decoy_friend_count` = le compte de sa boucle : amis du mover (self INCLUS -- `IsFriend`
          compare les playerId) portant `TriggeredAbilityType.DecoysAndMisdirection` (1304), sur
          `GetAllAliveUnits`, SANS filtre de position. Il est donc CONSTANT sur la decision ; il vit
          dans le `meta` parce que c'est la feuille qui le lit, pas parce qu'il depend de la tuile.
      Consequence mesuree AVANT ce cablage (case-212 §7.1) : sur toute tuile candidate occupee par un
      decoy ami, `X_natif - X_port` valait exactement **+25** = `FriendlyDecoy(-50)` +
      `DecoysAndMisdirection_FriendlyGSCLikeDecoys(+75)`, sur les deux montages (`MC1_67`/777 et
      `C4_09`/31337) -- le port EGALISAIT des tuiles que le natif separe de 25.

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
    friends = lc.get("friend_units")
    if friends:
        import hexgeo as _hex
        elev = lc.get("elev_by_pos")
        neigh = _bq.neigh_map(lc)
        adj, sur1, rng2 = [], [], []
        for u in friends:
            p, effs = u.get("pos"), (u.get("effects") or ())
            if not (p and effs):
                continue
            d = _hex.distance((pos[0], pos[1]), (p[0], p[1]))
            if _bq.is_adjacent(pos, p, elev, neigh):
                adj.extend(effs)
            if d <= 1:
                sur1.extend(effs)
            if d <= 2:
                rng2.extend(effs)
        if adj or sur1 or rng2:
            meta["neighbor_effect_names"] = {"adjacent": adj, "surrounding1": sur1,
                                             "ranged2": rng2}
    occ = _steppable_occupant(pos, lc)
    if occ is not None:
        meta["steppable"] = occ                                   # feuille SteppableUnit(20)
        if not occ["is_enemy"]:                                   # feuille AttractToDecoys(64)
            meta["decoy_gate"] = True
            meta["decoy_friend_count"] = _attract_to_decoys_friend_count(lc)
    if lc.get("friend_units") is not None:                        # feuille DoctrinaImperatives(#477-r31)
        meta["attract_mechanicals_neighbor"] = _attract_mechanicals_neighbor(pos, lc)
        # feuilles KustomForceField(21) / DefenderOfTheGreaterGood(22) / SaviorProtocols(23) (#175-r)
        meta["ability_friend_counts"] = _ability_friend_counts(pos, lc)
    # feuilles BioMinefield_MoveTowardsTarget(62) / MasterOfTheTutelaries_MoveTowardsTarget(63)
    # (#175-r1) -- `GetMinDistanceToTarget` mesure depuis `case.MovementPosition.MainTile`, donc
    # depuis la TUILE CANDIDATE : la valeur DEPEND de `pos`, la carte n'en depend pas.
    if lc.get("uid") is not None:                                 # `case.Unit != null`
        dd = {}
        for ident, carte in _movetowards_pathdist_by_pos(lc).items():
            d = carte.get((pos[0], pos[1]))
            if d is not None:            # `GetPath` -> null == cible injoignable -> `min` reste null
                dd[ident] = d
        if dd:
            meta["movetowards_pathdist"] = dd
    return meta


#: Les TROIS feuilles de la famille `ATriggeredAbilityUtility`, et l'id d'ability que chacune
#: cherche -- le champ `<utility>+0x60` que `$$GetUnitsWithAbility` passe a
#: `IdunBattleLogic.Entities.DSLSelectors$$UnitsWithTriggeredAbility`. Ce sont EXACTEMENT les trois
#: clefs que `_ability_count` lit dans `meta["ability_friend_counts"]`.
_ATRIGGERED_ABILITY_LEAVES = (int(TriggeredAbilityType.KustomForceField),            # 1102
                              int(TriggeredAbilityType.DefenderOfTheGreaterGood),    # 1155
                              int(TriggeredAbilityType.SaviorProtocols))             # 1120


def _ability_friend_counts(pos, lc: dict) -> dict:
    """`{ability_id: n}` que somment les feuilles 21/22/23 — `n` est le `Count` du selecteur DSL que
    chaque concret rend, et le corps PARTAGE
    `IdunBattle.AI.Utilities.ATriggeredAbilityUtility.u003CEvaluateMovementInStepsu003Ed__3$$MoveNext`
    en fait `Fix64.FromInt(n) x GetUtilityPerUnit()` :

        if (!this.AppliesTo(case))  yield Fix64.Zero;
        else yield Fix64.FromInt(Count(this.GetUnitsWithUtilityForMove(case))) x GetUtilityPerUnit();

    Le SELECTEUR commun est
    `IdunBattle.AI.Utilities.ATriggeredAbilityUtility$$GetFriendsAdjacentToMovementTile` :

        Friends(Entity(case.unit), AdjacentUnits(Entity(case.MovementTile), 1, 3), 3)
            op_Subtraction Entity(case.unit)

    -- les AMIS du mover ADJACENTS a la TUILE CANDIDATE, **self EXCLU** (`op_Subtraction`), puis
    `UnitsWithTriggeredAbility(<+0x60>)`. `AdjacentUnits` passe par `IterateAdjacentTiles`, donc
    porte d'elevation `|delta| < 2` -> `battle_query.is_adjacent`, jamais `hexgeo.distance == 1`.

    UNE seule feuille s'ecarte de ce voisinage, et il faut le lire, pas le deviner --
    `IdunBattle.AI.Utilities.DefenderOfTheGreaterGoodUtility$$GetUnitsWithUtilityForMove` :

        sel = GetFriendsAdjacentToMovementTile(case);                       // ring-1, self EXCLU
        if (case.unit != null && HasFaction(case.unit, 9 = UnitFaction.Tau))
            sel = SurroundingFriends(Entity(case.unit), Entity(case.MovementTile), 2, 1, 3);
        return UnitsWithTriggeredAbility(sel, <+0x60>);

    DEUX ecarts, tous deux LOAD-BEARING : le voisinage devient le **DISQUE hex de rayon 2** (donc
    `battle_query.is_surrounding`, SANS porte d'elevation), et surtout la branche Tau **NE
    SOUSTRAIT PAS `case.unit`** -- le mover s'y compte LUI-MEME s'il porte 1155. Le `- Entity(
    case.unit)` n'existe que dans `GetFriendsAdjacentToMovementTile`, et cette branche-la le
    remplace au lieu de le composer.

    Les gates propres a chaque feuille (`HasRangedWeapon` pour 22, `HasFaction(Tau) && !Has
    TriggeredAbility(1120)` pour 23) restent dans les `evaluate` : cote natif ils vivent dans le
    MEME `GetUnitsWithUtilityForMove`, qui rend `None()` quand ils ne passent pas -- soit un compte
    de 0, soit exactement ce que rend un `evaluate` qui court-circuite. On ne les duplique pas ici.

    `friend_units` est deja self-exclu par construction du `ctx` : il porte donc DIRECTEMENT
    l'ensemble du selecteur commun. Le `self_pos` n'est re-injecte que pour la branche Tau."""
    elev = lc.get("elev_by_pos")
    neigh = _bq.neigh_map(lc)
    friends = lc.get("friend_units") or ()
    tau = (lc.get("unit_faction") == int(UnitFaction.Tau))       # HasFaction(case.unit, 9)
    mine = set(lc.get("unit_triggered_abilities") or ())
    sp = lc.get("self_pos")
    out: dict = {}
    for ab in _ATRIGGERED_ABILITY_LEAVES:
        disque = tau and ab == int(TriggeredAbilityType.DefenderOfTheGreaterGood)
        n = 0
        for u in friends:
            p = u.get("pos")
            if not p or ab not in set(u.get("triggered") or ()):
                continue
            if _bq.is_surrounding(pos, (p[0], p[1]), 2, True) if disque \
                    else _bq.is_adjacent(pos, p, elev, neigh):
                n += 1
        # branche Tau de la feuille 22 : `SurroundingFriends` ne retire PAS `case.unit`, et
        # `friend_units` l'a deja retire -> on le re-injecte, comme `_attract_to_decoys_friend_count`.
        if disque and ab in mine and sp and _bq.is_surrounding(pos, (sp[0], sp[1]), 2, True):
            n += 1
        if n:
            out[ab] = n
    return out


#: Les DEUX feuilles `MoveTowardsUnitUtility` du composite. Le producteur ci-dessous lit LEURS
#: attributs (`_IDENTIFIER_KIND`, `_ABILITY_ID`, `_FRIENDS`, `_EFFECT_SOURCE_MUST_BE_PARENT`,
#: `_TRAIT_GATE`) : chacun mirrore UN virtuel de la sous-classe, donc le corps PARTAGE reste ecrit
#: une seule fois -- exactement comme le natif, ou `<EvaluateMovementInSteps>d__15` est unique.
_MOVETOWARDS_LEAVES = (BioMinefield_MoveTowardsTargetUtility(),
                       MasterOfTheTutelaries_MoveTowardsTargetUtility())

#: Cle de MEMO posee sur le `leaf_ctx`. Elle porte `(signature, carte)` : la signature est
#: l'ensemble des cibles RESOLUES, donc un `leaf_ctx` reutilise apres deplacement d'une unite
#: recalcule au lieu de servir une carte perimee.
_MOVETOWARDS_MEMO = "_movetowards_pathdist_memo"


def _movetowards_candidate_units(lc: dict) -> list:
    """`IBattleQuery.<slot 137 = GetAllAliveUnits>(null)` du point de vue du `leaf_ctx` --
    `[(enregistrement, is_friend)]`.

    Les deux listes du ctx sont SELF-EXCLUES quand il y a un sujet ; le natif, lui, balaie TOUTES
    les unites vivantes. Le sujet est donc RE-INJECTE, et ca n'est pas cosmetique : la branche
    EFFET de `<EvaluateMovementInSteps>d__15` n'ecarte PAS `case.Unit` (c'est la branche ABILITY
    qui porte le `u.Id != case.Unit.Id`), donc le mover est un porteur candidat comme un autre.

    ⚠ L'ORDRE n'est PAS celui de `GetAllAliveUnits`, et il MORD : la branche ABILITY retient le
    DERNIER match (aucun `break`) et la branche EFFET le PREMIER. Residu assume et NOMME -- il ne
    se voit qu'a partir de DEUX porteurs simultanes du meme identifiant."""
    out = [(u, True) for u in (lc.get("friend_units") or ())]
    out += [(u, False) for u in (lc.get("enemy_units") or ())]
    uid = lc.get("uid")
    if uid is not None:
        out.append(({"id": uid, "pos": lc.get("self_pos"),
                     "active": lc.get("unit_active_abilities") or (),
                     "owned_effects": lc.get("self_owned_effects") or ()}, True))
    return out


def _movetowards_target_pos(lc: dict, leaf) -> "tuple | None":
    """La CIBLE de `IdunBattle.AI.Utilities.MoveTowardsUnitUtility.u003CEvaluateMovementInStepsu003Ed__15$$MoveNext`,
    reduite a sa POSITION (le natif en prend `EntityExtensions$$GetMainTile`). `None` = le natif
    ne yielde rien, ou yielde `0` -- les deux valent 0 dans la somme du composite.

    Le corps natif, remis en C# depuis le decompile :

        if (case == null || case.Unit == null) yield return 0;
        traits = this.OnlyUnitsWithAny;                       // vslot, `List<UnitTrait>` ou null
        if (traits != null && !HasAnyTrait(this, case.Unit, traits)) yield break;   // RIEN
        all   = query.<slot 137 = GetAllAliveUnits>(null);
        ident = this.UnitIdentifierAbilityOrEffect();         // AbilityOrEffect
        list  = new List<IEntity>();
        if (ident.Effect.HasValue)
            foreach (comp in query.<slot 192 = GetActiveEffects>(ident.Effect.Value, null)
                                  .Select(e => e.GetComponent<EffectComponent>())) {
                u = all.FirstOrDefault(x => x.Id == comp.OwnerId);      // `<>c__DisplayClass15_0.b__1`
                if (u != null) list.Add(u); }
        else
            foreach (u in all) {
                if (u.Id != case.Unit.Id && ident.ActiveAbility.HasValue
                        && UnitExtensions.HasActiveAbility(u, ident.ActiveAbility.Value)) list.Add(u);
                else if (ident.TriggeredAbility.HasValue
                        && UnitExtensions.HasTriggeredAbility(u, ident.TriggeredAbility.Value)) list.Add(u); }
        IEntity target = null;
        if (ident.Effect.HasValue && this.EffectSourceMustBeParent) {
            parent = UnitExtensions.GetParent(case.Unit, State, root: false);
            int? pid = parent?.Id;
            if (!pid.HasValue) yield return 0;
            foreach (u in list) {
                eff = EntityExtensions.GetOwnedEffect(u, State, ident.Effect.Value);
                if (eff == null) continue;
                c = eff.GetComponent<EffectComponent>();
                if (c == null) continue;
                if (c.SourceUnitId == pid.Value) { target = u; break; } }        // PREMIER
        } else {
            foreach (u in list)
                if (this.Friends ? IsFriend(u, case.Unit, State) : IsEnemy(u, case.Unit, State))
                    target = u; }                                                // DERNIER
        if (target != null) { ... }

    ⚠ La branche `TriggeredAbility` est atteignable ET son `else if` n'est PAS imbrique sous le
    `u.Id != case.Unit.Id` -- relu deux fois, le saut sur egalite d'id tombe DANS le test declenche.
    Aucune des deux sous-classes ne pose cet identifiant (`AbilityOrEffect` n'en porte qu'UN a la
    fois : ses trois setters LEVENT si un autre est deja renseigne), donc la branche est morte
    ici ; elle est ecrite pour qu'une 3e sous-classe ne la re-deduise pas."""
    uid = lc.get("uid")
    if uid is None:
        return None                                       # `case.Unit == null` -> yield 0
    if leaf._TRAIT_GATE is not None:                      # `OnlyUnitsWithAny` -> yield break
        if not (set(lc.get("unit_traits") or ()) & leaf._TRAIT_GATE):
            return None
    ident = leaf._ABILITY_ID
    cands = []
    if leaf._IDENTIFIER_KIND == "effect":
        for u, fr in _movetowards_candidate_units(lc):
            # `GetActiveEffects(type)` : le porteur est retenu par un effet ACTIF de ce type.
            if any(e.get("type") == ident and e.get("active")
                   for e in (u.get("owned_effects") or ())):
                cands.append((u, fr))
    else:
        for u, fr in _movetowards_candidate_units(lc):
            if u.get("id") is None or int(u["id"]) == int(uid):     # `u.Id != case.Unit.Id`
                continue
            if ident in set(u.get("active") or ()):                 # `HasActiveAbility`
                cands.append((u, fr))
    target = None
    if leaf._IDENTIFIER_KIND == "effect" and leaf._EFFECT_SOURCE_MUST_BE_PARENT:
        pid = lc.get("unit_parent_id")
        if pid is None:                                   # `GetParent(case.Unit) == null` -> 0
            return None
        for u, _fr in cands:
            # `GetOwnedEffect(u, State, type)` -- le PREMIER effet possede de ce type, SANS filtre
            # d'activite (relu : il ne compare que `EffectComponent.EffectType@+0x58`).
            own = next((e for e in (u.get("owned_effects") or ()) if e.get("type") == ident), None)
            if own is None:
                continue
            if own.get("source") is not None and int(own["source"]) == int(pid):
                target = u
                break                                     # PREMIER match
    else:
        for u, fr in cands:
            # `IsFriend` / `IsEnemy` -- la partition amis/ennemis du ctx, comme partout ailleurs
            # dans ce module (elle ne distingue pas le camp NEUTRE, ecart deja nomme).
            if bool(fr) == bool(leaf._FRIENDS):
                target = u                                # DERNIER match, aucun `break`
    if target is None:
        return None
    p = target.get("pos")
    return (p[0], p[1]) if p else None


def _movetowards_pathdist_by_pos(lc: dict) -> dict:
    """`{identifiant -> {(col,row) -> Count}}` -- `GetMinDistanceToTarget` pour TOUTES les tuiles
    candidates en une passe, par feuille.

        // IdunBattle.AI.Utilities.MoveTowardsUnitUtility$$GetMinDistanceToTarget
        int? min = null;
        foreach (tile in EntityExtensions.IterateTiles(target, State)) {
            p = <this+0x28 : IPathfinders>.<slot 4 = GetPath, 5 params>(
                    1 /* PathfinderType.IgnoreTerrain */, unit, unitTile, tile, null);
            if (p != null && (!min.HasValue || p.<+0x18> < min.Value)) min = p.<+0x18>; }
        return min;

    Quatre points LUS, et chacun changerait le chiffre :
      1. le service est `IPathfinders` (slot 4 = la surcharge `GetPath` a 5 parametres, table
         `data/symbols/<build>/metadata/interface_slots.tsv`), pas `MovementQuery` ;
      2. le litteral `1` est `PathfinderType.IgnoreTerrain` -- aucun test d'occupant, l'occupance
         n'entre que par le COUT (`WeightCost = 10 + IsFilled`) ;
      3. `+0x18` est `List<T>._size`, extremites INCLUSES : `Count == aretes + 1` ;
      4. la boucle `IterateTiles` DEGENERE a une iteration -- l'appelant passe
         `EntityExtensions$$GetMainTile(target, State)`, donc une `TileEntity`, et la branche
         « l'entite EST une tuile » de `<IterateTiles>d__17` fait `yield entity; break`. Ce n'est
         PAS un min sur une empreinte multi-tuiles.

    `unitTile` est `case.MovementPosition.MainTile` (`UtilityMovementCase.MovementPosition@+0x18`,
    champ LU dans la declaration Il2CppDumper) : la TUILE CANDIDATE, pas l'origine du mover. La
    carte se calcule donc une fois par CIBLE, depuis la cible, et se lit par tuile."""
    sig = tuple((leaf._ABILITY_ID, _movetowards_target_pos(lc, leaf))
                for leaf in _MOVETOWARDS_LEAVES)
    memo = lc.get(_MOVETOWARDS_MEMO)
    if memo is not None and memo[0] == sig:
        return memo[1]
    from ..entities.pathfinding.ignore_terrain_pathfinder import get_path_node_counts_by_pos
    out: dict = {}
    if any(tp is not None for _ident, tp in sig):
        # `TileContentComponent.IsFilled(to)` du `WeightCost` -- un COUT, jamais un gate.
        occ = [u["pos"] for u in (list(lc.get("friend_units") or ())
                                  + list(lc.get("enemy_units") or ())) if u.get("pos")]
        sp = lc.get("self_pos")
        if sp:
            occ.append((sp[0], sp[1]))
        neigh = _bq.neigh_map(lc)
        for ident, tp in sig:
            if tp is None:
                continue
            out[ident] = get_path_node_counts_by_pos(
                tp, neigh_by_pos=neigh, walkable_by_pos=lc.get("walkable_by_pos"),
                elev_by_pos=lc.get("elev_by_pos"), occupied_positions=occ)
    lc[_MOVETOWARDS_MEMO] = (sig, out)
    return out


def _attract_mechanicals_neighbor(pos, lc: dict) -> bool:
    """`Enumerable.Any(...)` de `IdunBattle.AI.Utilities.AttractMechanicalsUtility.
    u003CEvaluateMovementInStepsu003Ed__1$$MoveNext`, relu ligne a ligne (#477-r31) :

        units = query.<slot 0x7a = GetAdjacentUnits, 4 args>(case.MovementTile, case.Unit, 0, 0)
        Enumerable.Any(units, <>c__DisplayClass1_0.<EvaluateMovementInSteps>b__0)

    et le predicat `IdunBattle.AI.Utilities.AttractMechanicalsUtility.u003Cu003Ec__DisplayClass1_0$$
    u003CEvaluateMovementInStepsu003Eb__0` :

        return UnitExtensions.HasActiveAbility(f, 0x45e) && f != case.Unit;

    ⚠ **LE CAMP EST UN ARGUMENT, PAS UNE PROPRIETE DU SLOT.** Le nom `GetAdjacentUnits` designe
    l'ensemble AVANT filtrage ; la signature reelle est
    `GetAdjacentUnits(from, friendsOf, enemiesOf, ignoreSteppables)` (lue dans
    `frida/methods.tsv`, pas dans les noms de parametres de ghidra), et le call-site passe
    `friendsOf = case.Unit`, `enemiesOf = null`. Le foyer terminal
    `IdunBattle.Core.Services.BattleQuery$$CountOrGetUnitsOnTiles` fait alors :

        if (friendsOf != null && !UnitExtensions.IsFriend(u, friendsOf, ctx))  continue;
        if (enemiesOf != null && !UnitExtensions.IsEnemy(u, enemiesOf, ctx))   continue;

    ⇒ **cette feuille compte les AMIS**, exactement comme le `GetAdjacentFriends` (slot `0x83`,
    arite 2) de `RadSaturationPlaybook` -- lequel n'est d'ailleurs qu'un
    `GetUnitsOnTiles(..., friendsOf=<entite JOUEUR de unit>, enemiesOf=null, ...)`. Les deux
    feuilles interrogent le MEME ensemble ; ce qui les separe est le gate de trait, le predicat
    (self exclu ici) et l'agregation (`Any` ici, `Count` la-bas).

    SELF. `f != case.Unit` exclut le mover, qui EST dans l'ensemble tant qu'il occupe son origine
    a ring-1 de la tuile candidate. `friend_units` etant deja self-exclu, l'iteration ci-dessous
    reproduit l'ensemble FILTRE -- et c'est le mirror de l'exclusion, pas une coincidence : la
    feuille voisine `RadSaturationPlaybook`, elle, n'ecrit AUCUN `f != case.Unit` et doit donc
    rajouter `self_pos` a la main (cf. `engine/playbook/rad_saturation.py`).

    ADJACENCE. `GetAdjacentUnits` passe par `IterateAdjacentTiles(from, onlyEmptyOrSteppable=false,
    onlyWalkableTiles=true, allowTemporary=true)` : liste de voisinage STOCKEE + porte d'elevation
    `|delta| < 2` -- c'est `battle_query.is_adjacent`, pas `hexgeo.distance == 1`.

    `ignoreSteppables = false` : les occupants steppables COMPTENT (aucun filtre de trait)."""
    elev = lc.get("elev_by_pos")
    neigh = _bq.neigh_map(lc)
    di = int(ActiveAbilityType.DoctrinaImperatives)                # 0x45e = 1118
    for u in (lc.get("friend_units") or ()):
        p = u.get("pos")
        if p and _bq.is_adjacent(pos, p, elev, neigh) and di in (u.get("active") or ()):
            return True
    return False


#: `IdunBattle.Entities.TileExtensions$$GetSteppableUnit` -- FOYER DEPLACE dans
#: `engine.entities.tile_extensions` par #477-r35, et re-exporte ici sous son ancien nom pour les
#: appelants
#: (`apply_tile_attributes` et la garde `test_steppable_decoy_tile_leaves_live`). Le deplacement
#: n'est pas cosmetique : `engine.playbook.non_owner` en a besoin pour la face `1531 HaywireMine`,
#: et il ne peut pas importer CE module (c'est `tile` qui importe `non_owner`, pas l'inverse). Une
#: seconde lecture du meme natif aurait pu diverger sans que rien ne le dise.
#: ⚠ DEUX emplacements ont ete essayes et MESURES avant `engine/entities/` : `engine/battle_query.py`
#: (casse `python -c "import engine.battle_query"`) puis `engine/tile_extensions.py` a la racine
#: (casse son propre import isole, par une arete RETOUR qui passe par CE fichier). La chaine
#: complete est dans la docstring d'`engine/entities/tile_extensions.py`, et le garde est
#: `probe_477r35_import_isole.py`. L'import est au NIVEAU MODULE (ci-dessus), jamais differe :
#: un differe aurait retarde le cycle au lieu de le supprimer.
_steppable_occupant = get_steppable_unit


def _attract_to_decoys_friend_count(lc: dict) -> int:
    """Le compte de la boucle de `IdunBattle.AI.Utilities.AttractToDecoysUtility.u003CEvaluate
    MovementInStepsu003Ed__1$$MoveNext` : nombre d'unites de `GetAllAliveUnits` qui sont
    `IsFriend(u, case.unit, ctx)` ET `HasTriggeredAbility(u, 0x518)` (1304
    `TriggeredAbilityType.DecoysAndMisdirection`). Un `yield return <poids>` par unite retenue ->
    l'appelant somme, donc le terme vaut `75 x n`.

    AUCUN filtre de position ni d'adjacence dans le natif, et AUCUNE exclusion de self : le mover
    compte pour lui-meme s'il porte 1304. `friend_units` est self-exclu, d'ou le `+1` explicite.

    ⚠ Ecart de substrat assume : `friend_units` ne retient que les amis vivants ET POSITIONNES,
    la ou `GetAllAliveUnits` ne filtre que sur la vie. Une unite vivante sans position (non
    deployee) manquerait au compte -- aucune n'est observable sur les montages de runner."""
    ab = int(TriggeredAbilityType.DecoysAndMisdirection)          # 0x518
    n = 1 if ab in set(lc.get("unit_triggered_abilities") or ()) else 0
    for u in (lc.get("friend_units") or ()):
        if ab in set(u.get("triggered") or ()):
            n += 1
    return n


def triggered_abilities_attack_utility(ctx, attacker_uid: int, ability_id: int,
                                       target_uid: int, attack_tile, prediction=None) -> float:
    """Feuille TriggeredAbilities(2) FACE ATTACK du composite Damage(35) (#45-s18) — entrée des deux
    scoreurs de paire (`playbook.base.calculate_action_utility` + stages `_formula_pair_utility`).
    Le natif évalue les 13 feuilles Damage DANS `ForDamagePrediction`, PAR DamageEvent -> ce terme
    s'ajoute au `damage_composite` de l'event et suit son `prob x signe` (à appliquer PAR L'APPELANT,
    comme pour le composite). `attack_tile` = tuile caster du case (sweep de position).

    #438 — `prediction` = `case.DamagePrediction` de l'event courant. Le case natif que ces
    appelants mirrorent est construit par `IdunBattle.AI.Utilities.UtilityAttackCase$$ForDamagePrediction`
    (caster, casterPosition, target, **damagePrediction**, abilityType) : la prédiction EST dans le
    case, un appelant qui l'a sous la main doit donc la passer. La laisser à `None` mirror un case
    SANS prédiction — régime natif légitime, mais faux ici, et silencieux."""
    return _TRIG_AB_UTILITY.evaluate_attack_in_steps(ctx, attacker_uid, ability_id,
                                                     target_uid, attack_tile,
                                                     prediction=prediction)


def triggered_abilities_non_owner_attack_utility(ctx, attacker_uid: int, target_uid: int,
                                                 attack_tile) -> float:
    """Feuille TriggeredAbilitiesNonOwner(4) FACE ATTACK du composite Damage(35) (#271-r4) —
    pendant EXACT de `triggered_abilities_attack_utility` sur l'autre feuille de dispatch.

    La MEMBERSHIP est MESURÉE, pas supposée : `probe_271r4_composition_map.py` lit la carte de
    composition d'`IdunBattle.Core.Services.UtilitiesDatabase$$InitializeUtilities` et rend pour
    `Damage(35)` **13** membres, dont `TriggeredAbilities` ET `TriggeredAbilitiesNonOwner`. Ce
    terme s'ajoute donc au `damage_composite` de l'event et suit son `prob x signe`, exactement
    comme la feuille 2 — à appliquer PAR L'APPELANT.

    Le corps natif ne prend PAS de `prediction` (aucun des trois playbooks ATTACK ne lit
    `case.DamagePrediction`), d'où l'absence du paramètre ici : l'ajouter suggérerait un canal que
    le natif n'ouvre pas."""
    return _TRIG_AB_NON_OWNER_UTILITY.evaluate_attack_in_steps(ctx, attacker_uid, attack_tile,
                                                               target_uid)


def triggered_abilities_non_owner_repair_utility(ctx, repairer_uid: int, target_uid: int,
                                                 fill_hp, target_max_hp,
                                                 caster_is_boss: bool = False) -> float:
    """Feuille TriggeredAbilitiesNonOwner(4) FACE REPAIR du composite `Repair(47)` (#271-r7) —
    TROISIÈME et dernier pendant de `triggered_abilities_non_owner_attack_utility`.

    La MEMBERSHIP est MESURÉE (`probe_271r4_composition_map.py`) : `Repair(47)` a **3** membres —
    `RepairedAmount(48)`, `TriggeredAbilities(2)`, `TriggeredAbilitiesNonOwner(4)`. Le port ne
    sommait que le premier ; ce terme câble le troisième. La feuille 2 (face repair du dispatcher
    OWNER) reste NON portée — écart nommé, pas un oubli.

    ⚠ Contrairement aux deux autres faces, ce terme ne lit AUCUNE clé BC : son unique corps concret
    (`VoltagheistFieldPlaybook`) RE-ÉMET la feuille `RepairedAmount(48)`. Le terme est donc un
    DOUBLEMENT de `repair_utility(fill_hp, target_max_hp)`, pas un poids — et il compense
    exactement le `×0.5` que `VoltagheistField_RepairReductionEffect` applique à la MAGNITUDE."""
    return _TRIG_AB_NON_OWNER_UTILITY.evaluate_repair_in_steps(ctx, repairer_uid, target_uid,
                                                               fill_hp, target_max_hp,
                                                               caster_is_boss)


_TRIG_AB_UTILITY: TriggeredAbilitiesUtility = TILE_LEAVES[UtilityType.TriggeredAbilities][1]
_TRIG_AB_NON_OWNER_UTILITY: TriggeredAbilitiesNonOwnerUtility = \
    TILE_LEAVES[UtilityType.TriggeredAbilitiesNonOwner][1]
