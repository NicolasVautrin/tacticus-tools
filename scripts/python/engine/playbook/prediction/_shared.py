"""Socle PARTAGE de la prediction de degat : bloc d'imports (vocabulaire commun aux 3 modules du package),
constantes de module (`RANGED_IN_MELEE_PCT`, `_PROFILE_INDEX`) et les 6 helpers d'ASSEMBLAGE des modifiers
(positionnels + defenseur + auras) consommes par `normal_attack` ET `abilities` (et importes directement par
`playbook/fury_of_the_ancients.py`, `playbook/psyker.py`, les probes).

`normal_attack.py` et `abilities.py` font `from ._shared import *` (recupere tout le vocabulaire non-underscore)
+ un import explicite des helpers/constantes underscore dont ils ont besoin. cf. `__init__.py`."""
from __future__ import annotations

import gameconfig as GC
import hexgeo
from engine.dsl import nodes as dsl   # facade DSLFactory (construction des noeuds)
from engine import weights as _weights
from engine.entities.abilities.active_ability import (
    active_ability_for, makes_damage_predictions, FrenziedFiringAbility, SavageEchoesAbility,
    _PROFILE_BY_INDEX)
from engine.entities.abilities.ability_configuration import AbilityConfiguration
from engine.entities.effects import (
    aura_attack_bonus_from_allies, aura_hits_malus_for_defense,
    aura_attack_damage_malus_from_enemies, aura_attack_damage_bonus_from_allies,
    aura_defense_damage_malus_from_units,
    calculate_attacker_modifiers_for_prediction, build_defender_modifiers_from_effects,
    hits_bonus_from_effects, hits_malus_from_defender_effects, additional_hit_groups,
    aura_additional_hits_from_allies)
from engine.entities.effects.loki.hits import LIGHT_COVER_TILE_ID
from engine.entities.rarity import Rarity as _Rarity   # `idun.meta.Rarity` (#1042-r1)
from engine.entities.effects.loki.damage_reduction import (   # #1042-r1 -- un seul foyer de nommage
    CTX_WISDOM_TARGET_IDS_OF as _WOTA_CTX_TARGET_IDS,
    CTX_TERTIARY_ABILITY_STATE_OF as _MYTHIC_CTX_ABILITY_STATE)
# #1036-r1/-r2 : memes trois cles pour les DEUX faces des deux mythiques de MoW -- un seul foyer
# de nommage (cf. `runner/damage_model.py`, qui importe les MEMES constantes).
from engine.entities.effects.loki.extra_damage_aura import (
    CTX_ATT_EFFECT_NAMES as _GUARDIAN_CTX_ATT_EFFECTS,
    CTX_OWNER_IS_MACHINE as _CABAL_CTX_OWNER_IS_MACHINE,
    CTX_CABAL_VALID_ADJACENT_TO_ATT as _CABAL_CTX_VALID_ADJACENT)
from engine.entities.effects.loki.obsessive_annunciation import (   # #954 -- un seul foyer de nommage
    CTX_ADJACENT_ENEMY_IDS_OF as _OA_CTX_ADJ_ENEMY_IDS)
from engine.entities.effects.loki.extra_damage_aura import (   # #1025-r1 -- meme foyer de nommage
    CTX_TGT_ADJACENT_UNIT_PROFILES as _MG_CTX_TGT_ADJ_PROFILES)
from engine.entities.traits import attacker_bonus_hits, target_hit_multiplier
from engine.entities.traits.factory import TraitFactory
from engine.entities.traits.unit_trait import UnitTrait, entity_trait_names
from engine.entities.damage_trait import DamageTrait
from engine.entities.stats import StatType, StatPart, ARMOR_STAT_TYPES
from engine.services.damage_prediction import get_attack_prediction
from engine.services.min_max_damage import MinMaxDamage
from engine.services.damage_modifiers import (
    ELEVATION_BONUS_PCT, EFFECT_NO_ELEVATION, add_modifier, DamageModifiers,
    calculate_elevation_bonus_modifier, calculate_ranged_in_melee_reduction,
    calculate_trench_reduction,
    TRENCH_PCT, _TRENCH_IGNORED_PROFILES)
from engine.services.battle_query import select_weapon_pierce, are_tiles_adjacent
from engine.battle_query import is_charging as bq_is_charging, newly_adjacent_ids
# #1019 -- `AdjacentUnits(Target@<+0x60>, 1, 3)` du noeud `IsValidAttackForBonus` de
# `WayOfTheShortBladeEffect` : adjacence NATIVE (liste stockee + porte `|dElev| < 2`), #943-r7.
from engine.battle_query import is_adjacent as bq_is_adjacent
from engine.entities.pathfinding import board as _pf_board
from engine.entities.effects.magnitude import ability_var
from engine.dsl.base import _round_fix64
from fractions import Fraction
from engine.services.attack_hits_formula import attack_hits_with_modifiers
from engine.playbook.probable_damage_event import ProbableDamageEvent

import json as _json
from ...runner.components import _TELEPORT_MOVE_EFFECTS
from engine.entities.effects import defender_effect_block_sources
from engine.entities.pathfinding.walk_pathfinder import get_path_node_counts_by_pos
_DMG_CFG: dict = _json.loads(_weights.DEFAULT_BC.read_text(encoding="utf-8")).get("Damage", {}) \
    if _weights.DEFAULT_BC.exists() else {}
# Feuilles positionnelles de IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction (PAS des effets) :
# ELEVATION : le builder PREDICTION IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction l'INCLUT, INLINEE (read-L1161-1192 : gate !HasEffect(0x423)
# attaquant ET cible + GetMainTile(cible) + `target.elev < attackTile.elev` -> +config.ElevationBonus) —
# AUCUN appel a la feuille IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier (inlining), d'ou le faux verdict xref #67 « pas d'elevation en
# prediction » (REFUTE #98 : aiPredict u80 (6,6) elev2>1 = x2.25 = CrushingStrike(1.5) x Elevation(1.5) ;
# tuile candidate (5,7) elev egale = x1.0 EXACT -> evaluee a la TUILE CANDIDATE). Cf.
# `_add_positional_and_defender_mods`. RangedInMelee/defenseur aussi dans le preview (10/11).
# RANGED_IN_MELEE_PCT : config native = pourcentage NEGATIF (ReductionPercentage=-50) ; le port passe la
# MAGNITUDE a calculate_ranged_in_melee_reduction (kind PercentDecrease -> add_modifier flippe le signe ->
# x0.5 ; IdunBattle.Core.Services.DamageCalculations$$GetMultiplierFromDamageBonus value<1 -> 1-|value|/100, decompile confirme). RangedInMelee
# = PREDICTION-only (trait 0xb jamais assigne, #161). TRENCH_PCT / _TRENCH_IGNORED_PROFILES deplaces en
# services.damage_modifiers (source unique partagee PREDICTION+COMBAT, #181).
RANGED_IN_MELEE_PCT: int = abs(int(_DMG_CFG.get("RangedInMeleeReductionPercentage", -50)))  # IdunBattle.Core.Services.DamageCalculations$$CalculateRangedInMeleeReduction
_PROFILE_INDEX = {name: idx for idx, name in _PROFILE_BY_INDEX.items()}


def _entity_traits(scene, uid) -> frozenset:
    """`IdunBattle.Entities.UnitExtensions$$HasTrait(unit, …)` cote face PREDICTION : le substrat de
    traits d'une ENTITE de la `Scene` -- FOYER UNIQUE, pendant exact de
    `runner.damage_model.target_trait_names` cote COMBAT (#267-r1).

    Le natif n'a QU'UN SEUL substrat de traits, et il est porte par l'entite : chaque gate lu au
    decompile (build `rnca9r7q6c`) resout le composant puis interroge ses trois collections --

      * `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor` ->
        `HasTrait(defender, 0x3f5)` (MkXGravis, `hit_multiplier` 2 hors crit) ;
      * `IdunBattle.AI.Playbook.Loki.HellfireShellsPlaybook$$MakeDamagePredictions` ->
        `HasTrait(target, 0x3f9)` (BigTarget, +`extraHit`) ;
      * les gates DSL (`BeastSlayer_ExtraDmgEffect$$CreateDamageModifier` =
        `HasTrait(target, 0x405 Vehicle) | HasTrait(target, 0x3f9 BigTarget)`,
        `ConquerorImperativeEffect$$CreateDamageModifier`, `LordOfTheHost_ExtraDamageEffect$$
        CreateEffectDamageBonusForAttack`, `DestroyTheWitch_ExtraDamageEffect$$
        CreateEffectDamageBonusForAttack`, `InfernalPacts_AdditionalHitsEffect$$CreateAdditionalHits`)
        passent par `IdunBattle.Entities.Triggers.HasTraitTrigger$$Evaluate`, qui resout l'entite du
        selecteur puis appelle **le meme** `UnitExtensions$$HasTrait`.

    et `UnitExtensions$$HasTrait` delegue a `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` :

        HasTrait(t) == !retires(+0x50).Contains(t)
                       && ( permanents(+0x40).Contains(t) || temporaires(+0x48).Contains(t) )

    AUCUNE lecture de gameconfig sur ce chemin. Ces sites relisaient pourtant
    `gameconfig.unit(visualId).traits`, alors que #267 pose deja la MESURE
    (`combatSnapshot.units[].traits`) sur `ctx.traits` des tables de prediction et que
    `_target_damage_limits` la consomme : la face PREDICTION lisait donc la mesure sur une partie de
    ses gates et le kit sur l'autre -- une incoherence INTERNE a une meme face. L'ecart va dans les
    DEUX sens (mesure : 5 unites du seed BC ont MOINS de traits que leur kit, 48 en ont PLUS), plus
    tout `IdunBattle.Operations.AddTraitOperation$$Execute` accorde en bataille, que le kit ne peut
    pas porter par construction.

    TRI-ETAT, herite de `entity_trait_names` / `scene._seed_measured_traits` : `ctx.traits_measured`
    vrai -> la MESURE telle quelle (grande-alliance comprise, `frozenset()` si la mesure est vide) ;
    faux (canal absent/`null`, ctx issu d'un spawn offline) -> la RECONSTRUCTION anterieure
    (kit + pseudo-trait de grande-alliance), jamais un vide silencieux ; `ctx` absent (uid hors des
    tables, ligne sans `StatsComponent`) -> la BORNE statique `unit_trait_names(visualId)`.
    `uid is None` -> `frozenset()` (appelant sans cible)."""
    if uid is None:
        return frozenset()
    return entity_trait_names(scene.ctx(uid), scene.vis_by_id.get(uid))


def _entity_rarity(scene, uid):
    """#999-r3-r1 -- `BaseUnitComponent.Rarity` (+0x74) d'une entite de la `Scene`, foyer de lecture
    face PREDICTION. Pendant exact de `runner.damage_model._unit_rarity` cote COMBAT.

    C'est le champ que les trois gates natifs de rarete lisent apres
    `IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent` --
    `IdunBattle.Entities.Triggers.HasRarityTrigger$$ShouldTrigger`,
    `IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select`,
    `IdunBattle.Entities.UnitExtensions$$HasRarity`. Les DEUX faces sont seedees par le MEME foyer
    (`UnitContext.from_snapshot`, #999-r3) : la face DECISION y arrive par
    `playbook.scene._hydrate_static_unit`, la face COMBAT par `runner.snapshot`.

    TRI-ETAT STRICT, MEME convention que `_unit_rarity` : `None` = NON MESURE (uid hors des tables,
    ligne sans contexte de stats, capteur muet) -> le lecteur FERME son gate. JAMAIS `Rarity.Common`
    en repli, qui accorderait un gate de rarete a toute unite non mesuree."""
    if uid is None:
        return None
    return getattr(scene.ctx(uid), "rarity", None)


def _weapon_pierce(scene, att_id, is_adjacent, dist=None):
    """Arme + percage de l'attaque normale — DELEGUE au service PARTAGE `battle_query.select_weapon_pierce`
    (MEME port que le combat/runner ; `is_adjacent` = adjacence HEX native, `dist` = distance HEX pour la
    porte de portee ranged #188, cf. `make_normal_attack_predictions`). Renvoie
    `(pierce, is_ranged, weapon_hits, profile_name)`."""
    return select_weapon_pierce(scene.ctx(att_id), is_adjacent, dist)


def _should_apply_ranged_in_melee(scene, att_id, attack_pos) -> bool:
    """`IdunBattle.Core.Services.DamageCalculations$$ShouldApplyRangedInMelee` : le natif gate la reduction RangedInMelee sur
    `HasTrait(ATTAQUANT, UnitTrait.Ranged=0xb=11)` (param_4=0 dans le chemin prediction
    `IdunBattle.Core.Services.DamageCalculations$$CalculateRangedInMeleeReduction`) — PAS sur le `is_ranged` de l'ability. Or ce trait
    n'est porte par AUCUNE unite : absent de gameconfig (0 unite) ET de la BC `Units[].Traits` — c'est un
    trait RUNTIME jamais assigne en pratique (`IdunBattle.Entities.UnitExtensions$$IsRanged` = HasTrait(0xb) OR HasRangedWeapon se
    reduit donc a HasRangedWeapon, la branche trait etant morte). CONSEQUENCE : le natif N'APPLIQUE JAMAIS
    RangedInMelee en prediction. On mirror le gate EXACT (HasTrait), donc sans le trait Ranged -> False.
    L'ancien gate `is_ranged` de l'appelant SUR-appliquait la ×0.5 aux casters HYBRIDES tirant une ability
    ranged en melee (#161 : Neurothrope/SpiritLeech = ×2 faux). Si un jour une unite porte le trait Ranged,
    la suite (ennemi melee-able adjacent) s'active fidelement.

    Suite (native, quand HasTrait) : depuis `attack_pos`, existe-t-il un ENNEMI melee-able ADJACENT ?
    (any-enemy, boucle sur les tuiles adjacentes) — ennemi (team != attaquant) + vivant +
    `CanMeleeAttackOverElevationDifference` (|Delta elev|<2). Adjacence HEX via `are_tiles_adjacent`.

    ⚠ CE MODULE PORTE LE **TROISIEME** MIRROR DU MEME NATIF (#287-r11-r2-r1-r2), et le corps a
    TROIS gardes avant sa boucle, pas deux. La troisieme --
    `if (UnitExtensions.HasFlag(attacker, 0x1c = UnitFlag.IngoreRangedInMelee)) return false;` --
    est portee par les deux autres mirrors (`runner.abilities.targeting.should_apply_ranged_in_melee`
    et `runner.abilities.loki.mv71._should_apply_ranged_in_melee_from_tile`) et NON portee ici,
    pour une raison MESUREE et non par omission : son unique poseur dans tout le binaire est
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour`,
    qui le pose sur le DRONE **a l'interieur** de sa chaine DSL (`AddFlag & UseActiveAbility &
    RemoveFlag`) -- un instant que la face PREDICTION n'observe jamais. Il est de plus PRECEDE ici
    par le gate `HasTrait(0xb Ranged)`, dont le retour negatif court-circuite deja tout le corps.
    Point d'ancrage si un second poseur apparait : une table de plus dans la `Scene`, alimentee du
    MEME canal (`combatSnapshot.units[].unitFlags` publie DEJA toutes les valeurs de l'enum).
    ⚠ Ce mirror-ci omet AUSSI `!TileExtensions.HasSteppableUnit(adj)` et
    `UnitExtensions.IsTargetable(u)`, deux conjonctions que les deux autres portent : ecart NOMME,
    inerte tant que le gate `HasTrait` l'est."""
    ctx = scene.ctx(att_id)
    traits = getattr(ctx, "traits", None) or ()
    if UnitTrait.Ranged.name not in traits:        # HasTrait(attaquant, 0xb) — absent partout => inerte (#161)
        return False
    if attack_pos is None:
        return False
    att_team = scene.team(att_id)
    a_elev = scene.elev_by_pos.get(attack_pos) if scene.elev_by_pos else None
    for uid, epos in scene.pos_by_id.items():
        if uid == att_id or epos is None or scene.team(uid) == att_team:
            continue
        if (scene.hp(uid) or 0) <= 0:                      # IsAlive
            continue
        if are_tiles_adjacent(attack_pos, epos, scene.board) is not True:
            continue
        if a_elev is not None and scene.elev_by_pos:       # CanMeleeAttackOverElevationDifference
            e_elev = scene.elev_by_pos.get(epos)
            if e_elev is not None and abs(a_elev - e_elev) >= 2:
                continue
        return True
    return False


def _prediction_is_charging(scene, att_id, attack_pos, tgt_id) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$IsCharging(caster, target)` evalue DEPUIS LA TUILE
    CANDIDATE — face PREDICTION du gate porte par `AvalancheOfMuscle_ExtraDamage` (1025),
    `FeederTendrils_ExtraDamage` (1197) et `BlackRage_ExtraDamage` (1343). Case-r32.

    Le predicat lit `UnitComponent.ChargedUnitIds@+0x190`, que seul
    `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` alimente. La chaine display evalue une
    UnitPosition HYPOTHETIQUE (`GetUnitPositionAtTile`), donc la liste pertinente est

        charges DEJA acquises ce tour   UNION   ce que le pas CANDIDAT ajouterait

    -- exactement ce que produirait un `UpdateCharging` applique a la simulation, qui PART de la
    liste reelle. Le predicat lui-meme reste le FOYER PARTAGE `battle_query.is_charging` (aucun fork),
    et le volet geometrique le mirror `battle_query.newly_adjacent_ids`.

    LES DEUX TERMES SONT MESURES NECESSAIRES (`probe_r32_ischarging_prediction.py`, `astraBullgryn`
    L50 mult 180 %, `aiPlaybookPredict(col,row)`) :
      * terme CANDIDAT -- caster a distance 2, tour NEUF (liste reelle vide), tuile candidate
        adjacente : natif **12032**, offline avec le terme **12032**, sans lui **9636** (= 4 x 599).
        La prediction native SIMULE donc bien le pas.
      * terme REEL -- caster ayant DEJA charge ce tour, tuile candidate == sa tuile courante (aucun
        pas) : natif **12032** ; sans ce terme le port rendait **9636**. La prediction native lit donc
        AUSSI la liste acquise.

    Consequences, toutes voulues :
      * aucun pas et aucune charge acquise -> FAUX ;
      * tuile candidate qui amene AU CONTACT d'une cible qui ne l'etait pas -> VRAI ;
      * tuile candidate atteinte alors que la cible etait DEJA adjacente ET non chargee -> FAUX
        (c'est le cas que l'ancien proxy `has_moved` accordait a tort).

    ETAT RECHARGE -- la limite d'outillage qui vivait ici est LEVEE (#230). `scene.charged_by_id`
    n'est toujours peuple que par `Scene.from_state`, mais l'ECS que celui-ci lit porte desormais la
    liste REELLE : le capteur `combatSnapshot` expose `UnitComponent+0x190` (`f790ff4`) et
    `snapshot._load_unit_turn_state` la seede au chargement. La capture doit etre prise
    MI-ACTIVATION -- `FinishUnitTurnOperation$$Execute` vide la liste a chaque fin d'activation, donc
    une capture prise ENTRE deux tours la voit vide, et c'est CORRECT. Mesure de fermeture
    (`probe_r32_ischarging_prediction.py`, ligne `B' SEED` : prediction depuis la tuile courante d'un
    caster qui vient de charger, etat RECHARGE et AUCUN pas rejoue) -- natif **12032**, offline
    **12032**, bornes forcees 12032 / 9636 (donc probant)."""
    if tgt_id is None:
        return False
    cur = scene.pos(att_id)
    pos = attack_pos or cur
    charged = set(scene.charged(att_id))                     # terme REEL (charges deja acquises)
    # #433-r4-r1-r4-r2-r1 : les DEUX termes lisent le substrat NATIF (liste stockee du
    # `ConnectivityComponent` + porte `|dElev| < 2`), pas la couronne hex -- `UpdateCharging` passe
    # par `GetAdjacentUnits` -> `IterateAdjacentTiles`, et `IsCharging` par
    # `MovementUtil$$AreTilesAdjacent` -> `ConnectivityComponent$$IsNeighbour`, qui lit la MEME liste.
    if pos != cur:
        others = {uid: p for uid, p in (scene.pos_by_id or {}).items() if uid != att_id}
        charged |= newly_adjacent_ids(cur, pos, others,      # terme CANDIDAT (le pas hypothetique)
                                      scene.elev_by_pos, scene.neigh_by_pos)
    return bq_is_charging(pos, scene.pos(tgt_id), tgt_id, charged,
                          scene.elev_by_pos, scene.neigh_by_pos)


def prediction_has_moved(scene, att_id, attack_pos) -> bool | None:
    """`HasFlag(Self, UnitFlag.Moved = 0)` TEL QUE LA PREDICTION NATIVE LE VOIT — foyer UNIQUE de la
    face prediction (gates no-move de `HeavyWeapon_ExtraDmgEffect` et `CrushingStrikeEffect`).

    Le predicat natif n'est PAS calcule par le predicteur : `HasFlagAbilityTrigger$$ShouldTrigger`
    interroge `UnitFlagsComponent$$Has` sur l'ECS, et
    `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` ne
    substitue QUE la POSITION (`AbilityEntities+0x40`, tuile de l'attaquant prise du parametre alors
    que celle de la CIBLE est re-derivee par `GetMainTile`) -- aucun flag n'y est maquille. Ce que la
    prediction voit vient donc de DEUX termes, tous deux mesures :

      1. **le flag REEL**, `HasFlag(u, Moved)` -- l'unite a deja bouge ce tour ;
      2. **la tuile SIMULEE**. Une prediction depuis une tuile autre que la tuile courante passe par
         `IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile`, qui appelle le
         MEME `IdunBattle.Entities.UnitExtensions$$SetMovedFlag` que `MoveUnitOperation$$Execute`
         avant d'executer l'action, puis RESTAURE (`UnitFlagsComponent$$Remove(0)` et `Remove(0xc)`
         si l'`Add` avait rendu « etait absent »).

    Le choix entre les deux voies est lu verbatim dans
    `SimulateEffectsOperation.u003Cu003Ec__DisplayClass5_0u003C...u003E$$u003CExecuteu003Eb__0` :

        if (UnitPosition.op_Equality(EntityExtensions.GetUnitPosition(state, unit), simulatedPos))
            DoActionInSimulatedOnSameTile(...)   // AUCUN SetMovedFlag
        else
            DoActionInSimulatedTile(...)         // SetMovedFlag

    d'ou `has_moved = (attack_pos != position courante) OR HasFlag(u, Moved)`.

    MESURE (`probe_266_moved_prediction.py`, `admecDestroyer` HeavyWeapon vs `orksNob`, board MC1_67,
    oracle `pairUtility` = `ComparablePlaybook$$CalculateUtilityFromPredictions` natif) : depuis la
    tuile COURANTE d'un caster non deplace, utilite **3.2296** ; depuis les DIX-SEPT autres tuiles du
    movable set en portee, **2.6676** a l'identique quelles que soient l'elevation (1/2/3) et la
    distance (1/2/3) -- ni l'une ni l'autre n'est le discriminant. Apres un deplacement REEL, la
    tuile courante rend **2.6676** elle aussi : le flag reel ferme le meme gate que la simulation.

    TRI-ETAT du terme 1 : `scene.has_moved` rend `None` quand `combatSnapshot.unitFlags` n'a PAS ete
    mesure (hook anterieur a O5). On rend alors `None` plutot que `False` -- l'appelant garde le
    comportement anterieur au lieu de se voir affirmer « n'a pas bouge »."""
    if attack_pos is not None and attack_pos != scene.pos(att_id):
        return True                                  # voie `DoActionInSimulatedTile` -> SetMovedFlag
    return scene.has_moved(att_id)


_TMT_CACHE = "_tiles_moved_path_counts"      # memo par (Scene, unite) — la Scene est refaite au pas
# Mirror de `IdunBattle.Operations.MoveUnitOperation$$UnitNeedsAccurateNumTilesMovedInSimulation` =
# `HasTriggeredAbility(unit, 0x5f9 ModifiedExoarmour) || HasTriggeredAbility(unit, 0x4de SmashaEad)`.
# Pour toute AUTRE unite, `GetNumTilesMovedForSimulation` ne calcule AUCUN chemin et rend 0 — d'ou ce
# court-circuit, qui est autant de la fidelite que de l'economie (un Dijkstra par unite et par pas).
# Le substrat d'ENTITE cote port est l'effet que le passif POSE (meme temoin que le seed, cf.
# `BaseEffect.seed_witness_effect`) : le kit gameconfig dirait ce que l'unite possede en theorie.
# `SmashaEad` (0x4de) n'est PAS ici : son port (`SmashaEadExtraDamageEffect`) bake la condition
# « a traverse >= 2 hexes » dans la MATERIALISATION de l'effet et ne lit pas ce canal — l'inscrire
# ferait tourner le pathfinding pour rien. RESIDU NOMME : le jour ou ce port passera au canal
# `tiles_moved_this_turn`, ajouter son effet ici.
_TILES_MOVED_CARRIER_EFFECTS = ("ModifiedExoarmour_ExtraDmg",)


def _needs_accurate_tiles_moved(scene, att_id) -> bool:
    """`MoveUnitOperation$$UnitNeedsAccurateNumTilesMovedInSimulation`, cote port."""
    st = getattr(scene, "eff_state", None)
    return st is not None and any(st.has_effect(att_id, name=n)
                                  for n in _TILES_MOVED_CARRIER_EFFECTS)


def _walk_path_counts_from(scene, att_id) -> dict:
    """`{(col,row) -> Count}` du `WalkPathfinder` depuis la position REELLE de `att_id` — le `path`
    que `IdunBattle.Operations.MoveUnitOperation$$CalculatePaths` demande a
    `IPathfinders.GetPath(GetPathfinderTypeForUnit(unit), unit, startTile, endTile, maxRange)`.

    FOYER PARTAGE avec la face MOUVEMENT du meme passif (#304,
    `playbook/modified_exoarmour.py::path_node_counts`) : MEME fonction
    `entities.pathfinding.walk_pathfinder.get_path_node_counts_by_pos`, MEME convention `Count` =
    NOEUDS (extremites incluses). Seul le SUBSTRAT differe (la `Scene` ici, le `tile_leaf_ctx`
    la-bas), comme partout ailleurs entre les deux faces.

    RESIDUS, tous PERMISSIFS et nommes :
      * le natif compte sur `connectedPath` (`BattleQuery$$GetConnectedPathTo` ->
        `MovementQuery$$GetConnectedPathTo`), qui est le `path` du pathfinder DENSIFIE : il
        re-insere les tuiles intermediaires entre deux noeuds consecutifs distants de plus de 1
        (teleporteurs/sauts). Sur un chemin de marche ordinaire les deux listes ont la MEME longueur.
      * `block_entering_positions` n'est pas derivable de la Scene (`tile_effects_by_pos` porte des
        NOMS, la table de blocage des ids `EffectType`) -> vide : un chemin peut passer par une tuile
        que le natif facturerait `10000 - elevation`, donc etre plus COURT. Mesure par tuile
        disponible : `probe_312_votan_prediction_gap.py` (colonne `bouge`).
      * `IsTemporary(to)` : meme residu que la face MOUVEMENT (aucune source offline)."""
    hit = getattr(scene, "_scene_cache", None)
    if hit is not None and _TMT_CACHE in hit and att_id in hit[_TMT_CACHE]:
        return hit[_TMT_CACHE][att_id]
    sp = scene.pos(att_id)
    board = scene.board
    counts: dict = {}
    if sp is not None and board is not None:
        # FOYER UNIQUE du substrat de graphe, PARTAGE avec la face COMBAT
        # (`runner/operations/movement.py::_num_tiles_moved`) : `Board.walk_maps_by_pos`.
        neigh, walk, elev = board.walk_maps_by_pos()
        # `WalkPathfinder$$UnitIsBlockedByEnemyUnit` : occupant ENNEMI VIVANT non `Steppable`.
        team = scene.team(att_id)
        blocking = set()
        for uid, p in (scene.pos_by_id or {}).items():
            if uid == att_id or p is None or (scene.hp(uid) or 0) <= 0:
                continue
            if team is not None and scene.team(uid) == team:
                continue                                   # un ami ne BLOQUE pas le passage
            if "Steppable" in (getattr(scene.ctx(uid), "traits", None) or ()):
                continue                                   # HasTrait(occ, 0x1b) -> ne bloque pas
            blocking.add((p[0], p[1]))
        counts = get_path_node_counts_by_pos((sp[0], sp[1]), neigh_by_pos=neigh,
                                             walkable_by_pos=walk, elev_by_pos=elev,
                                             blocking_positions=blocking)
    try:
        cache = getattr(scene, "_scene_cache", None)
        if cache is None:
            cache = {}
            object.__setattr__(scene, "_scene_cache", cache)
        cache.setdefault(_TMT_CACHE, {})[att_id] = counts
    except Exception:                                       # Scene figee -> pas de memo
        pass
    return counts


def prediction_tiles_moved_this_turn(scene, att_id, attack_pos) -> int:
    """`TilesMovedThisTurn(Self)` TEL QUE LA PREDICTION NATIVE LE VOIT (case-322) — le pendant de
    `prediction_has_moved` sur l'axe COMPTEUR, et il a la MEME structure a deux termes :

      1. **le compteur REEL du tour** (`ActorStatisticsComponent+0xf0`, ecrit par
         `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved`) ;
      2. **le pas SIMULE**. Une prediction depuis une tuile autre que la tuile courante passe par
         `IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile`, et
         `IdunBattle.Operations.MoveUnitOperation$$Execute` en mode simulation appelle
         `RecordTilesMoved(unit, BattleQuery.GetNumTilesMoved(connectedPath))` — un `+=`, d'ou la
         SOMME et non un remplacement. `GetNumTilesMoved` = `Count - 1` (extremites incluses ->
         aretes), la meme convention decrementee que #304.

    ⚠ Le natif ne calcule ce chemin QUE pour un porteur de `HasTriggeredAbility(0x5f9)` ou
    `(0x4de)` (`MoveUnitOperation$$UnitNeedsAccurateNumTilesMovedInSimulation`) — pour toute autre
    unite `GetNumTilesMovedForSimulation` rend **0**. Ce gate est ici implicite et sans effet
    observable : le seul consommateur porte (`ModifiedExoarmour_ExtraDmg`) n'existe que sur un
    porteur de 0x5f9, et le calcul n'est declenche que par lui.

    TERME 1 — `scene.tiles_moved_this_turn` (case-322-r2). Que ce soit bien le compteur REEL, et
    non un compteur pollue par les tuiles candidates deja evaluees, est LU au decompile :
    `IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile` SAUVEGARDE
    `ActorStatisticsComponent+0xec` et `+0xf0` AVANT l'action simulee et les RESTAURE APRES (le
    pendant `$$DoActionInSimulatedOnSameTile` ne touche pas le composant du tout). Une prediction
    depuis la tuile COURANTE rend donc le compteur reel NU, et chaque prediction depuis une autre
    tuile repart du meme reel.

    TRI-ETAT : `None` = compteur **non mesure** -> on garde le seul terme « pas simule », soit le
    comportement strictement anterieur a ce cablage. Deux regimes le renseignent :
      * OFFLINE (`Scene.from_state`) : l'ECS du runner, qui TIENT le compteur depuis #322-r1
        (`runner/operations/movement.py::MoveUnitOperation.execute`) -> la face DECISION lit ce que
        la face COMBAT a ecrit, comme #267 (traits) et #266 (flag `Moved`) ;
      * LIVE (`Scene.from_predictor_sctx`) : le capteur `actorStats`. RESIDU NOMME — tant que le
        hook ne publie pas `+0xf0`, la table reste vide et ce terme vaut `None`."""
    real = scene.tiles_moved_this_turn(att_id) or 0        # terme 1 — `None` (non mesure) -> 0
    cur = scene.pos(att_id)
    if attack_pos is None or cur is None or tuple(attack_pos) == tuple(cur):
        return real                # `DoActionInSimulatedOnSameTile` : AUCUN MoveUnitOperation
    if not _needs_accurate_tiles_moved(scene, att_id):
        return real                # `GetNumTilesMovedForSimulation` rend 0 sans meme pathfinder
    n = _walk_path_counts_from(scene, att_id).get((attack_pos[0], attack_pos[1]))
    return real + (int(n) - 1 if n else 0)      # `IsNullOrEmpty(path)` -> 0


def prediction_has_teleported(scene, att_id, attack_pos) -> bool:
    """`HasFlag(Self, UnitFlag.Teleported = 0xc)` tel que la prediction native le voit -- la branche
    qui RE-AUTORISE le +25% de `HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier`
    (`... & (!HasFlag(Moved) | HasFlag(Teleported))`). Pendant prediction du `att_ctx
    ["has_teleported"]` que `runner.damage_model.attacker_modifiers` threade cote COMBAT.

    Mirror de `IdunBattle.Entities.UnitExtensions$$SetMovedFlag` applique a la tuile simulee :

        added = UnitFlagsComponent.Add(unit, Moved)          # rend « etait ABSENT »
        if added and (IsOwnerOfEffect|IsTargetOfEffect(unit, 0x40c|0x40b|0x4d9|0x4d6)):
            UnitFlagsComponent.Add(unit, Teleported)

    -> le flag vaut le flag REEL, plus l'ajout que la simulation ferait si (a) elle passe par
    `DoActionInSimulatedTile` et (b) `Moved` n'etait pas deja pose et (c) l'unite porte un des quatre
    effets de teleport. NON VALIDE LIVE (aucun porteur connu cumule `HeavyWeapon` et
    `TeleportStrike`/`FearOfTheUnseen`) -- mirror du decompile, comme la branche COMBAT (case-101
    SS 5.4)."""
    if scene.has_teleported(att_id):
        return True
    sim_move = attack_pos is not None and attack_pos != scene.pos(att_id)
    if not sim_move or scene.has_moved(att_id) or scene.eff_state is None:
        return False                                 # `added` faux -> le natif ne re-teste rien
    return any(scene.eff_state.has_effect(att_id, effect_type=t) for t in _TELEPORT_MOVE_EFFECTS)


def _add_positional_and_defender_mods(mods, scene, att_id, tgt_id, is_melee, attack_pos, t_pos,
                                      damage_profile=None, is_normal_attack: bool = True):
    """Ajoute au `mods` les feuilles NON-effet du builder natif `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction (positionnelles, geometrie) + les modifiers DEFENSEUR. Le pipeline natif
    `CalculateDamagePredictionScenario` les applique a TOUT degat (normal ET special) APRES percage/armure.
      • ElevationBonus (`IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier`, surplomb +50%).
      • RangedInMelee (`IdunBattle.Core.Services.DamageCalculations$$CalculateRangedInMeleeReduction`, ranged adjacent a un ennemi → ×0.5).
      • Trench (`IdunBattle.Core.Services.DamageCalculations$$CalculateTrenchReduction`, −50%) : reduction PAR DEFAUT si la cible porte l'effet
        Trench, SUPPRIMEE quand l'attaquant est lui-meme sur une tuile Trench ET voisin hex de la cible
        (#177 : polarite tranchee + 3 mesures live ; `board.terrain_at`=#124, residus CASE3/IndirectFire #182).
      • DEFENSEUR (`CalculateDefenderModifiersForPrediction` : effets de la CIBLE reduisant le degat recu)."""
    # ELEVATION (#98 — RENVERSE le verdict #67 « pas d'elevation en prediction ») : le builder PREDICTION
    # IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction (qui FIRE bien 33x par tour de decision, mesure modifier-observe) l'applique INLINEE
    # (read-L1161-1192, aucun appel a IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier -> le xref-check #67 ne pouvait pas la voir) :
    #   if attackTile && !HasEffect(att,0x423) && !HasEffect(tgt,0x423) && GetMainTile(tgt):
    #       if tgt.elev < attackTile.elev : bonus = Nullable(config.ElevationBonus)   # -> Add (%-list)
    # Evaluee a la TUILE CANDIDATE `attack_pos` (mirror local_588) vs la tuile REELLE de la cible.
    # GROUND TRUTH #98 (u80 darkaTerminator seed777 r1) : aiPredict (6,6) elev2>1 not-moved = x2.25
    # = CrushingStrike(1.5) x Elevation(1.5) EXACT ([11940,17907] = port x2.25) ; candidates (5,7)/(5,6)/
    # (6,8) elev1=1 = x1.0 EXACT. Les contre-cas historiques #67 (u90 : dmg identique tuiles elev2/elev3 ;
    # u88 : elev2>1 sans bonus) sont a re-verifier avec la methode artefact-aware (#96 : le cache aiPredict
    # collisionne par (unit,cible,tuile) et peut servir une valeur d'une autre ability/etat) — anomalies
    # tracees dans docs/rl/playbook/prediction.md, PAS une raison de forker le port du builder lu.
    if scene.elev_by_pos and attack_pos and t_pos:
        a_elev = scene.elev_by_pos.get(tuple(attack_pos))
        t_elev = scene.elev_by_pos.get(tuple(t_pos))
        if a_elev is not None and t_elev is not None:
            att_effects_ = scene.effects(att_id)
            tgt_effects_ = scene.effects(tgt_id)
            no_elev = any(e.effect_type == EFFECT_NO_ELEVATION for e in att_effects_) \
                or any(e.effect_type == EFFECT_NO_ELEVATION for e in tgt_effects_)
            eb = calculate_elevation_bonus_modifier(a_elev, t_elev, ELEVATION_BONUS_PCT, no_elev)
            if eb is not None:
                add_modifier(mods, eb)
    is_ranged = not is_melee
    if is_ranged and _should_apply_ranged_in_melee(scene, att_id, attack_pos):     # trait 0xb + adjacence
        eb = calculate_ranged_in_melee_reduction(True, RANGED_IN_MELEE_PCT)
        if eb is not None:
            add_modifier(mods, eb)
    tgt_effects = scene.effects(tgt_id)
    # Trench (IdunBattle.Core.Services.DamageCalculations$$CalculateTrenchReduction) : gate COMPLET dans la fonction nommee (main gate +
    # sous-branche IsTrench(attackerTile), #177 polarite tranchee + 3 mesures live board C2_19). attackerTile
    # = attack_pos, tuile cible = t_pos (GetMainTile(cible)=sa position), board threade (#183 : plus latent).
    # Gate IndirectFire(0x3ed) PORTE ; seul residu = CASE3 ligne-toute-Trench (delegate @LAB_181004bb9 non-RE'd, #182).
    att_ctx_traits = getattr(scene.ctx(att_id), "traits", None) or ()
    eb = calculate_trench_reduction(
        attack_pos, t_pos,
        any(getattr(e, "name", None) == "Trench" for e in tgt_effects),        # HasEffect(cible, Trench 0x423)
        UnitTrait.IndirectFire.name in att_ctx_traits,                         # HasTrait(att, IndirectFire 0x3ed)
        bool(damage_profile) and damage_profile in _TRENCH_IGNORED_PROFILES,   # IgnoreTrenchReduction
        scene.board, TRENCH_PCT)
    if eb is not None:
        add_modifier(mods, eb)
    # attacker_ctx : identite + niveau/mult du Neurothrope SOURCE (gate + magnitude Neuroparasite). L'attaquant
    # ETANT le source (AreEqual), extraDmg s'indexe sur SON ablvl x SON multiplier.
    # `is_normal_attack` propage au gate `IsNormalAttack` des malus defenseur (ex. MartialKatah -20% #105 :
    # reduit UNIQUEMENT les attaques normales, no-op sur les speciales config-based).
    # #61bis tranche 3 : FACTION de l'attaquant threadee pour les malus defenseur gates par faction —
    # Markerlight (1122) : `OwnerIsTarget & HasFaction(actor, 9=T'au) & IsRangedAttack ->
    # ForPercentIncrease(MarkerlightDmgBonusPct=15)` (`IdunBattle.Entities.Effects.Loki.MarkerlightEffect$$CreateDamageModifier`). MEME source
    # que le combat (`damage_model.defender_modifiers` : `_faction(visual_id)` gameconfig).
    from engine.ai.action_generators import _faction as _fac
    att_ctx = {"id": att_id, "ability_level": scene.ablvl_by_id.get(att_id), "multiplier": scene.mult(att_id),
               "is_normal_attack": is_normal_attack,
               "faction": _fac(scene.vis_by_id.get(att_id))}
    # R9 : les TROIS noeuds DSL natifs restants portes sur `caster@0x160` — `IsUnit(caster)`,
    # `AreFriends(caster, <noeud entite>)`, `HasTrait(caster, …)`. MEMES CLES / MEME SEMANTIQUE que la
    # face COMBAT (`damage_model.defender_modifiers`) : elargir un seul cote recreerait le fork
    # « ce que le moteur fait != ce que la prediction annonce ». La SOURCE differe par necessite
    # (Scene cold-refreshee ici, ECS live la-bas), exactement comme `defense_stat` (#197).
    #  * `is_unit`    : `dv.units` est `EntityType.Unit`-only par construction -> l'attaquant present
    #    dans `scene.vis_by_id` EST une unite (les MoW ont leur canal separe, cf. Scene.from_state).
    #  * `team`/`team_by_id` : `scene.team(att_id)` / `scene.team_by_id` (le meme dict que la formule
    #    de COUPS thread deja sous ce nom).
    #  * `traits`     : substrat d'ENTITE de l'attaquant (`_entity_traits`) — MEME source que le
    #    `att_ctx["traits"] = target_trait_names(state, attacker_id)` du combat (#267-r1).
    att_ctx["is_unit"] = scene.vis_by_id.get(att_id) is not None
    att_ctx["team"] = scene.team(att_id)
    att_ctx["team_by_id"] = scene.team_by_id
    att_ctx["traits"] = _entity_traits(scene, att_id)
    # #999-r3-r1 : `HasRarity(Caster@<DSLSelectors+0x48>, idun.meta.Rarity.Mythic = 5)`. MEME cle,
    # MEME semantique et MEME convention de nommage que la face COMBAT
    # (`damage_model.defender_modifiers` : sans prefixe = l'ATTAQUANT). Consommateur :
    # `HyperCorrosiveAcid_ExtraDamagePctEffect` (1448) -- effet SANS `$$CreateTargetSelector`, donc
    # servi par ce canal-ci (les effets de la CIBLE) et pas par l'aura. TRI-ETAT -> gate FERME.
    att_ctx["rarity"] = _entity_rarity(scene, att_id)
    # `IsTurnOf(Owner@0x148)` (case-366-r1) : SEULE cle de ce contexte portee sur l'OWNER de l'effet
    # (= la CIBLE `tgt_id`) et non sur le caster -- parce que le noeud natif, lui, porte sur l'Owner.
    # `scene.is_turn_of` LIT `dv.units[].ctrl` (= `IsControlledByCurrentPlayer` invoque natif) ; la
    # face COMBAT pose la MEME cle depuis l'ECS (`damage_model._owner_turn_flag`). `None` (non
    # mesure) -> cle ABSENTE, le gate consommateur se tait.
    _toc = scene.is_turn_of(tgt_id)
    if _toc is not None:
        att_ctx["is_turn_of_owner"] = _toc
    # `GetNumAdjacentTauntedEnemies()` (#911) : DEUXIEME cle de ce contexte portee sur l'OWNER de
    # l'effet (= la CIBLE `tgt_id`), pour la MEME raison qu'`is_turn_of_owner` juste au-dessus -- le
    # gate de `DaemonicPatrons_DmgReduction` (1465) est `get_OwnerIsTarget`, donc son compte est
    # celui du DEFENSEUR. Face COMBAT : la meme cle, posee depuis l'ECS par `damage_model`.
    _adt = scene.adjacent_taunted_enemies(tgt_id)
    if _adt is not None:
        att_ctx["adjacent_taunted_enemies"] = int(_adt)
    # #932 -- les TROIS noeuds de `IdunBattle.Entities.Effects.Loki.DeathwingEffect$$
    # GetDoubleEffectCondition` sur la face DEFENSE (`isDefense: true`), ou l'entite comparee est
    # l'ACTEUR (l'attaquant) et l'Owner est la CIBLE `tgt_id` :
    #   `HasTrait(Actor@+0x40, 0x7ea = Chaos)`  -> `grand_alliance` (celle de l'ATTAQUANT ; elle
    #      n'est PAS dans `traits` -- le trait d'alliance est derive du `GrandAllianceId` par
    #      `idun.Idun.Source.Shared.GrandAlliance$$GetTrait` et ajoute par le BattleConfiguration) ;
    #   `AreEnemies(Actor@+0x40, Owner@+0x30)`  -> `team` (deja posee) + `owner_team` ;
    #   `AmountIsGreaterThanZero(UnitsFromFaction(AdjacentFriends(Owner), DarkAngels))`
    #                                           -> `adjacent_dark_angels_friends` du DEFENSEUR.
    # TROISIEME et QUATRIEME cles de ce contexte portees sur l'OWNER de l'effet, comme
    # `is_turn_of_owner` et `adjacent_taunted_enemies`. MEMES cles que la face COMBAT
    # (`damage_model.defender_modifiers`) -- pas de fork.
    att_ctx["grand_alliance"] = (GC.unit(scene.vis_by_id.get(att_id)) or {}).get("GrandAllianceId")
    _own_team = scene.team(tgt_id)
    if _own_team is not None:
        att_ctx["owner_team"] = _own_team
    _ada = scene.adjacent_dark_angels_friends(tgt_id)
    if _ada is not None:
        att_ctx["adjacent_dark_angels_friends"] = int(_ada)
    # `IsAdjacent(Caster@DSLSelectors+0x48, Owner@DSLSelectors+0x30, 3)` -- les DEUX arguments d'un
    # noeud GEOMETRIQUE que ce contexte ne portait pas encore. `owner_pos` est la CINQUIEME cle
    # portee sur l'OWNER de l'effet (= la CIBLE `tgt_id`), meme convention qu'`owner_team` juste
    # au-dessus ; `att_pos` est la TUILE CANDIDATE de l'attaquant (`attack_pos`), pas sa tuile
    # courante -- c'est elle que le natif evalue pour une decision balayee. MEMES cles que la face
    # COMBAT (`damage_model.defender_modifiers`). Consommateur :
    # `TerrorsLament_DamageReduction`, dont le trigger porte sur la geometrie ATTAQUANT <-> PORTEUR.
    # Cle absente (position inconnue) -> le gate se FERME cote effet (conjonction).
    att_ctx["att_pos"] = attack_pos
    att_ctx["owner_pos"] = t_pos
    # STAT-MODS DEFENSE de la CIBLE (#194/#197) : moitie DEFENSE de `CalculateDefenderModifiersForPrediction
    # IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` (DefenseComponent stat 3 IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction+0x436 → `IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications`
    # negate=1 → `1±v/100`). Ex. tuile Thorns −50 → +50 → ×1.5 (GROUND TRUTH C2_19). PORTEE DANS la fonction
    # partagee (plus de fold separe ici) → l'entree sort via `def_mods.pct_list` et est recopiee ci-dessous,
    # EXACTEMENT comme avant (composition %-list commutative sans arrondi intermediaire, #98) : #194 bit-exact
    # preserve, et le COMBAT/runner l'obtient par la MEME fonction (fin du fork #197). `scene.defense_stat` =
    # capture combatSnapshot refreshee par-pas (None/no-mod → inerte).
    def_mods = build_defender_modifiers_from_effects(tgt_effects, is_melee, damage_profile,
                                                     attacker_ctx=att_ctx,
                                                     defense_stat=scene.defense_stat(tgt_id))
    # #446-r2 : la face DEFENSEUR entre desormais dans `pct_list_defender`, PAS dans `pct_list`.
    # Le natif ne fusionne JAMAIS les deux faces : `CalculateBaseDamageWithAllModifiers` les
    # consomme separement, et intercale un `Fix64.Round(., AwayFromZero)` INCONDITIONNEL entre
    # elles (`CalculateBaseDamageWithModifiers`, slot 0x10, appele une fois par face). La phrase
    # « composition %-list commutative sans arrondi intermediaire (#98) » ci-dessus valait pour
    # DEUX entrees de la MEME face -- elle ne vaut pas d'une face a l'autre. Mesure : #446-r2.
    # #437-r1-r1-r1 : `def_mods` porte SES DEUX faces separement (routage `add_modifier` sur
    # `EffectBonus.native_face`). Ce site les RECOPIE chacune dans la sienne au lieu de tout
    # verser cote defenseur -- cf. le commentaire jumeau dans
    # `AttackDamageOperation._apply_defender_flat_reductions`.
    for mult, cap in def_mods.pct_list:
        mods.pct_list.append((mult, cap))
    for mult, cap in def_mods.pct_list_defender:
        mods.pct_list_defender.append((mult, cap))
    # #462-r4a : le `Multiplier@0x30` du DEFENSEUR (= les MODIFICATIONS DE STAT, seules a y entrer)
    # a son etage PROPRE, le DERNIER de `CalculateBaseDamageWithAllModifiers`, precede d'un `Round`.
    # Les %-list ci-dessus, elles, se composent AVEC celles de l'attaquant sans arrondi entre.
    if def_mods.multiplicative != 1.0:
        mods.multiplicative *= def_mods.multiplicative
    if def_mods.multiplicative_defender != 1.0:
        mods.multiplicative_defender *= def_mods.multiplicative_defender
    # ADDITIF defenseur (ForAddition, ex. Neuroparasite +extraDmg x niveau) — le %-list SEUL etait fusionne,
    # l'additif defenseur etait DROPPE. PLACEMENT = MEME slot @+0x10 que l'additif ATTAQUANT #75 : ajoute a la
    # base PRE-percage, puis traverse percage et est scale ×%-list UNE fois (le natif ajoute l'additif @+0x10
    # a la base int AVANT `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`, qui NE re-consomme PAS @+0x10 —
    # cf. `attacker_additive_pre=True` dans `predict_attack_raw`/`calculate_damage_prediction_scenario`). Donc
    # on AJOUTE l'additif BRUT (SANS pre-scale) : le chemin attacker_additive_pre applique deja le %-list ×M.
    # #121 (CONFIRME LIVE 2026-07-12, Neurothrope u82 -> custoTrajann level 1, A=1696 M=1.064) : ORACLE
    # contribution = 1804 = A*M (natif single-scale) ; le pre-scale ×M produisait A*M^2 = 1920 (port sur-pred
    # +116) -> RETIRE. Reproduit les 2 separateurs #88 (RangedSpecialist ON M=1.33 -> A*M=2256 ; OFF M=1 ->
    # 1696) : l'ancien pre-scale ×M compensait le PLACEMENT POST-%-list de `apply_all_modifiers` (additif apres
    # %-list, non scale) ; #70/#111 a bascule la prediction sur attacker_additive_pre (additif pre-percage,
    # %-list re-applique) -> le pre-scale devint un DOUBLE-comptage. != flat_reductions (Nightshroud ci-dessous,
    # #120) qui n'est PAS pre-scale non plus. Combat : def additive=0 (parasite non materialise) -> inerte.
    if def_mods.additive:
        mods.additive += def_mods.additive
    # Reductions DYNAMIQUES CAPEES defenseur (GuardianOrganism -min(pct%×dmg, cap)) — appliquees post-mods
    # dans apply_all_modifiers (CurrentDamage). Le %-list SEUL etait fusionne (comme l'additif, cf. #86a).
    if def_mods.capped_reductions:
        mods.capped_reductions.extend(def_mods.capped_reductions)
    # Reductions PLATES CONSTANTES defenseur (Nightshroud_DmgReduction ForSubtraction = ConfigVar(0x12)=
    # dmgReduction×mult, ex. 499 @{lvl50,mult180}) — additif DEFENSEUR sur le slot @+0x10 : soustrait de la
    # BASE **PRE-percage** (comme l'additif attaquant #75), donc DILUE par percage/armure PUIS scale ×%-list
    # UNE fois (mirror CBDWAM IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers : le natif ajoute l'additif @+0x10 a la base int AVANT Calculate
    # BaseDamageWithAllModifiers, CBDWAM ne le re-consomme pas). CONFIRME LIVE : le config 499 dilue par le
    # facteur percage/armure (~0.31 vs custoTrajann) -> ~155/coup de degat sante = oracle [1620,2744] (le
    # residu apparent "155" N'EST PAS la valeur config mais 499 traversant l'armure). PAS de pre-scale ×M
    # (!= l'additif Neuroparasite ci-dessus qui compense le placement post-%-list du COMBAT) : le chemin
    # attacker_additive_pre scale deja ×%-list une fois.
    if def_mods.flat_reductions:
        mods.additive -= sum(def_mods.flat_reductions)
    # (moitie DEFENSE stat-mods #194/#197 : DESORMAIS foldee DANS build_defender_modifiers_from_effects
    # ci-dessus → transite via def_mods.pct_list, plus de fold separe ici — fin du fork prediction/combat.)
    # AURAS-DEFENSE state-wide (#184) : effets EffectWithTarget possedes par d'AUTRES unites dont le
    # TargetSelector projette sur la CIBLE du coup — boucle « TOUS les EffectWithTarget actifs × leurs
    # cibles » de `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` (cf. case-68), qui ne se reduit PAS
    # aux effets portes par la cible. Ex. DaughterOfTheAbyss (Atlacoya) : -dmgReductionPct% (33 @L50)
    # Psychic aux AMIS rayon 2 (racine du ~1.49x bloodMephiston seed 2024 : 1003×1.25×3×0.67 = 2016,3024
    # natif vs 3006,4515 port) ; +extraDmgPct% aux Psykers ENNEMIS rayon 2. Cibles/positions REELLES
    # (la cible ne bouge pas pendant la prediction) ; porteurs vivants uniquement.
    # #267-r1 : traits de la CIBLE = substrat d'ENTITE, MEME source que le `tgt_traits` de
    # `damage_model._apply_ally_attack_damage_auras` cote combat (`target_trait_names`).
    _tgt_traits_names = _entity_traits(scene, tgt_id)
    # #999-r3-r1-r1 -- univers BOARD-WIDE (`scene.effect_carrier_ids`), pas `scene.pos_by_id` : le
    # natif n'ecarte AUCUN porteur par sa position, et l'ancienne base excluait structurellement
    # toute MACHINE OF WAR (hors-plateau). `scene.pos(uid)` rend `None` pour elles -> les auras
    # POSITIONNELLES se taisent d'elles-memes chez leurs lecteurs (`if not op: return None`), seules
    # entrent celles dont le `$$CreateTargetSelector` ne lit aucune position. Pendant EXACT de la
    # face COMBAT (`damage_model.defender_modifiers`).
    _def_carriers = [(uid, scene.pos(uid), scene.team(uid), scene.effects(uid))
                     for uid in scene.effect_carrier_ids(exclude=tgt_id)
                     if scene.hp(uid) is None or (scene.hp(uid) or 0) > 0]
    for _eb in aura_defense_damage_malus_from_units(
            _def_carriers, {"tgt_id": tgt_id, "t_pos": t_pos, "tgt_team": scene.team(tgt_id),
                            "tgt_traits": _tgt_traits_names, "damage_profile": damage_profile,
                            # #999-r3-r1 -- RARETE de la CIBLE (le BENEFICIAIRE de ce canal : la
                            # boucle native ecrit `AbilityEntities+0x18 (Owner) <- CHAQUE CIBLE du
                            # selecteur` et le trigger est `get_OwnerIsTarget`). Consommateur :
                            # `ContemptuousDisregard_DamageReductionEffect` (1443). MEME cle et MEME
                            # semantique que la face COMBAT (`damage_model.defender_modifiers`) --
                            # pas de fork. TRI-ETAT -> gate FERME sur `None`.
                            "tgt_rarity": _entity_rarity(scene, tgt_id),
                            # #366-r1 (`PsychicStalk_ExtraAttackDamage`) : le gate du trigger porte
                            # sur le CASTER (`IsUnit(caster@0x160)`) et sur la TUILE de la cible
                            # (`EntitiesWithAnyEffect(Tiles(Target@0x178), Fire)`), pas sur le
                            # porteur de l'effet. MEMES cles, MEME semantique que la face COMBAT
                            # (`damage_model.defender_modifiers`) -- pas de fork.
                            "att_id": att_id, "att_is_unit": att_ctx.get("is_unit"),
                            # `IsAdjacent(Caster@+0x48, Owner@+0x30, 3)`,
                            # `AreEnemies(Owner@+0x30, Caster@+0x48, 0)` et `IsMeleeAttack` --
                            # MEMES cles et MEME semantique que la face COMBAT
                            # (`damage_model.defender_modifiers`), pas de fork. Consommateur :
                            # `TerrorsLament_DamageReduction`, dont le trigger porte sur
                            # l'ATTAQUANT et le PORTEUR, jamais sur la cible.
                            "att_pos": attack_pos, "att_team": scene.team(att_id),
                            "is_melee": is_melee,
                            # #952 : le TROISIEME conjoint du gate d'`HuntersBeyondDeathEffect` sur
                            # l'attaquant -- `HasTrait(Caster@+0x48, 0x3ea = Psyker)`. MEME nom et
                            # MEME source que la face COMBAT ; les deux autres conjoints
                            # (`att_pos`, `att_team`) etaient DEJA la, poses par #950.
                            "att_traits": att_ctx.get("traits"),
                            # #959 -- `HasFaction(Caster@+0x48, 0x14 = LeaguesOfVotann, 3)`, second
                            # membre du `op_BitwiseOr` de
                            # `PredictiveGuidance_MeleeEffect$$BonusCondition`. MEME cle et MEME
                            # source (`FactionId` du gameconfig) que la face COMBAT
                            # (`damage_model.defender_modifiers`) -- pas de fork. Le premier membre
                            # (`IsMechanical`) se lit dans `att_traits`, deja pose par #952.
                            # Le KIT est la bonne source : `FactionId` est une donnee de
                            # CONFIGURATION (aucun equivalent d'entite), comme `GrandAllianceId`
                            # ligne ~528 -- contrairement aux TRAITS (#267-r1).
                            "att_faction": (GC.unit(scene.vis_by_id.get(att_id))
                                            or {}).get("FactionId"),
                            # #959 -- `UnitsWith[out]Flag(<aura>, 0 = UnitFlag.Moved, 3)`, le noeud
                            # qui PARTITIONNE melee et distance. Il porte sur la CIBLE, qui ne bouge
                            # PAS pendant une prediction : le terme « tuile simulee » de
                            # `prediction_has_moved` ne s'applique donc pas ici, on lit le flag REEL
                            # SEUL (`scene.has_moved`, tri-etat -- `None` = non mesure -> gate
                            # FERME cote effet).
                            "tgt_has_moved": scene.has_moved(tgt_id),
                            # #954 -- le `CreateTargetSelector` d'`ObsessiveAnnunciation_ExtraDmg`
                            # (`AdjacentEnemies(Owner@+0x30, unique: true, UnitSelectionType 3)`).
                            # CALLABLE et PAR PORTEUR : la boucle native ecrit
                            # `AbilityEntities+0x18 (Owner) <- CHAQUE CIBLE de l'effet`, donc
                            # `get_OwnerIsTarget` y demande une APPARTENANCE. MEME cle, MEME
                            # semantique et MEME foyer d'adjacence (`playbook/adjacency.py`) que la
                            # face COMBAT (`damage_model.defender_modifiers`) -- pas de fork.
                            _OA_CTX_ADJ_ENEMY_IDS: scene.adjacent_enemy_ids,
                            # #1025-r1 -- `HasRarity( Caster@<DSLSelectors+0x48>, 5 = Mythic )`,
                            # 2e conjoint du trigger de `MoreGitzOverEre_ExtraDamagePct` : le
                            # BENEFICIAIRE de ce canal est la CIBLE, mais CE gate porte sur
                            # l'ATTAQUANT. MEME cle, MEME resolveur (`_entity_rarity`) et MEME
                            # tri-etat que la face COMBAT (`damage_model.defender_modifiers`) --
                            # pas de fork. `None` = non mesure -> gate FERME.
                            "att_rarity": _entity_rarity(scene, att_id),
                            # #1025-r1 -- `IsNormalAttack`, 4e conjoint du meme trigger
                            # (<< normal melee attacks >>). MEME donnee que le `is_normal_attack`
                            # deja threade dans le ctx d'aura ATTAQUE de ce module.
                            "is_normal_attack": is_normal_attack,
                            # #1025-r1 -- `AdjacentUnits(<la CIBLE>, unique, 3)` enrichi de
                            # `(team, visual_id, rarity)` : substrat des DEUX branches du
                            # `$$CreateTargetSelector` de `MoreGitzOverEre_ExtraDamagePct`. MEME
                            # cle, MEME forme et MEME foyer d'adjacence
                            # (`playbook/adjacency.py`) que la face COMBAT
                            # (`damage_model._adjacent_unit_profiles`) -- pas de fork. La CIBLE
                            # est FIXE pour cet appel -> valeur pre-calculee, pas un callable.
                            _MG_CTX_TGT_ADJ_PROFILES: _adjacent_unit_profiles(scene, tgt_id),
                            # #1042-r1 -- le `$$CreateTargetSelector` de
                            # `WisdomOfTheAncients_DamageReductionEffect` (1445), CALLABLE et PAR
                            # PORTEUR pour la meme raison que la cle ci-dessus. MEME cle, MEME
                            # semantique et MEME foyer d'adjacence NATIVE que la face COMBAT
                            # (`damage_model.wisdom_of_the_ancients_target_ids`) -- pas de fork.
                            _WOTA_CTX_TARGET_IDS:
                                lambda oid: wisdom_of_the_ancients_target_ids(scene, oid),
                            # #1038-r1 / #1042-r1 -- `GetAbilityState(effet)` des deux auras
                            # MYTHIQUES de MoW (1443, 1445) : l'etat **TERTIAIRE** de la SOURCE,
                            # `1..4 / 100`. MEME cle et MEME semantique que la face COMBAT
                            # (`damage_model._tertiary_ability_state_fn`, foyer #357) ; le substrat
                            # est ici `Scene.trigstate_by_id` (capteur `unitAbilityStates`, MEME
                            # payload que les quatre seeds voisins). TRI-ETAT : `(None, None)` =
                            # non mesure -> l'effet est INERTE, jamais une magnitude devinee.
                            _MYTHIC_CTX_ABILITY_STATE: scene.triggered_ability_state,
                            "tile_effects_by_pos": scene.tile_effects_by_pos}):
        # #446-r2 : ces auras sortent de la boucle `EffectWithTarget` de
        # `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` --
        # face DEFENSEUR, donc `pct_list_defender` (cf. le merge ci-dessus). `add_modifier` sur un
        # accumulateur JETABLE puis transfert : le routage reste dans `add_modifier`, pas duplique.
        _tmp = DamageModifiers()
        add_modifier(_tmp, _eb)
        # #437-r1-r1-r1 : `add_modifier` a deja route sur la face NATIVE de l'effet -- on recopie
        # chaque face dans la sienne. `DaughterOfTheAbyss_ExtraDamagePct` sort de cette boucle
        # AURA-defense mais son natif implemente `CreateEffectDamageBonusForAttack`, donc il
        # atterrit dans `_tmp.pct_list` et doit rester cote ATTAQUANT.
        mods.pct_list.extend(_tmp.pct_list)
        mods.pct_list_defender.extend(_tmp.pct_list_defender)
        mods.multiplicative *= _tmp.multiplicative              # #462-r4a (canal `Multiplier@0x30`)
        mods.multiplicative_defender *= _tmp.multiplicative_defender
        mods.additive += _tmp.additive
        mods.extra_pierce += _tmp.extra_pierce
        mods.armor_penetration += _tmp.armor_penetration
        mods.ignore_armor = mods.ignore_armor or _tmp.ignore_armor
        mods.capped_reductions.extend(_tmp.capped_reductions)
        # #950-r2 : les reductions PLATES d'une aura se CONSOMMENT ici, exactement comme celles de
        # la patte SELF quinze lignes plus haut (`mods.additive -= sum(def_mods.flat_reductions)`).
        # Elles etaient VERSEES dans `mods.flat_reductions` -- un bac que le pipeline de PREDICTION
        # ne vide JAMAIS : seuls le COMBAT
        # (`AttackDamageOperation._apply_defender_flat_reductions`) et la patte SELF le font. La
        # perte etait donc SILENCIEUSE, et n'affectait que les auras a reduction PLATE.
        #
        # C'est le MEME placement que la patte SELF parce que c'est la MEME boucle native : le port
        # scinde en deux pattes (Owner == cible / Owner != cible) un univers que
        # `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`
        # parcourt d'un seul tenant (effets x cibles, BOARD-WIDE, sans scope) et verse dans UN seul
        # accumulateur. Deux pattes du port, un accumulateur natif -> une seule consommation.
        #
        # MESURE (#950-r2, `TerrorsLament_DamageReduction` sur le carre aura/away de #950, build
        # `rnca9r7q6c`) : sur la tuile candidate d'ou l'attaquant est adjacent a Jain Zar, oracle
        # natif (2045, 5055) contre port (6030, 9040) -- ecart +3985 sur les DEUX bornes, soit
        # exactement `5 coups x 797` de `ConfigVar(0x12 = dmgReduction)`. Les quatre autres tuiles
        # et les six du temoin concordaient deja a l'unite.
        if _tmp.flat_reductions:
            mods.additive -= sum(_tmp.flat_reductions)
        mods.details.extend(_tmp.details)


def _target_damage_limits(scene, tgt_id, damage_profile: str | None = None):
    """Champs STATIQUES cible pour `apply_trait_damage_limits_to_damage` (#56, `ApplyTraitDamageLimits
    ToDamage IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage`). Derivables offline : **Resilient** (trait gameconfig + hp/hpmax → cape le
    degat a `HP-1`) et **member-cap Swarm** (#57d : `nrOfMembers` gameconfig de la cible + hpmax =
    repartition native `IdunBattle.Core.Services.DamageCalculations$$GetGroupUnitMemberHealth` ; skip si le profil de L'ATTAQUE a
    `DamageTrait.HitsMultipleMembers` (2) = Blast — d'ou `damage_profile` threade par l'appelant).
    Valide bit-exact 1357 s16 (u139 5 hits 1197/1795 vs necroSmnSwarm 5×444 : caps 442,444,444,444
    puis dernier membre NON cappe → [2971,3569] == natif). Les autres sous-limites restent des **NO-OP
    documentes** (defaults conservateurs) faute d'input offline : Impervious (charge runtime non captee
    par combatSnapshot), boss-cap (`HasTriggeredAbility(0x5d4)` non verifie offline).

    #264 -- les TRAITS viennent du substrat d'ENTITE (`entity_trait_names(scene.ctx(tgt), vis)`),
    pas d'une relecture du kit gameconfig par visualId : PENDANT EXACT du meme changement cote
    COMBAT (`operations/damage.py::_target_limits`). Elargir un seul cote recreerait le fork « ce que
    le moteur fait != ce que la prediction annonce ». MESURE (2026-07-30) : `necroOverlord` porte
    `Resilient` au gameconfig et NE le porte PAS en bataille (son `BC.Units[].Traits` ne le contient
    pas -- les deux blocs different, cf. `snapshot._load_unit_traits`) : les deux faces le capaient a
    `HP-1`, c.-a-d. annoncaient
    et executaient un kill IMPOSSIBLE la ou le natif tue. `nrOfMembers` reste gameconfig (c'est
    `NumberOfMembersComponent`, pas un trait)."""
    gu = GC.unit(scene.vis_by_id.get(tgt_id)) or {}
    utraits = _entity_traits(scene, tgt_id)      # #267-r1 : FOYER unique du substrat de traits
    hpmax = scene.hpmax(tgt_id) or 0
    _dp_traits = (GC.damage_profile(damage_profile) or {}).get("Traits") or [] if damage_profile else []
    return {
        "target_has_resilient": "Resilient" in utraits,
        "target_has_impervious": "Impervious" in utraits,
        "impervious_stat_current": None,             # charge Impervious non captee offline -> no-op (TODO)
        "member_count": int(gu.get("nrOfMembers") or 1),   # NumberOfMembersComponent (IdunBattle.Core.Services.DamagePrediction$$ApplyGroupUnitDamageLimit lit le composant)
        "member_total_hp": hpmax,
        "profile_has_hits_multiple_members": DamageTrait.HitsMultipleMembers.name in _dp_traits,
        "max_health": hpmax,
        "target_has_boss_cap": False,                # HasTriggeredAbility(0x5d4) non verifie offline -> no-op (TODO)
        "boss_cap_const": 0,
    }


def prediction_block_damage(scene, uid) -> "int | None":
    """`StatAmount(<unit>, 0x8 = StatType.BlockDamage, 0x0 = StatPart.Current)` cote PREDICTION --
    pendant EXACT de `runner/damage_model.py::_unit_stat` (#919).

    Consommateur porte : `IconOfObstinacy_ExtraDamageEffect`, dont la magnitude est
    `ConfigVar(extraDmg) + PercentageOf(StatAmount(Owner@DSLSelectors+0x30, BlockDamage), chance)` --
    la PREMIERE aura de degat dont le montant lit une STAT DU PORTEUR.

    TRI-ETAT : `None` = pas de contexte de stats pour cette unite -> le consommateur OMET le terme
    `%` et le dit, il ne le remplace pas par 0 (un 0 rabattu ferait disparaitre le terme en
    silence)."""
    c = scene.ctx(uid) if uid is not None else None
    if c is None:
        return None
    return int(c.get_stat(int(StatType.BLOCK_DAMAGE), int(StatPart.CURRENT)) or 0)


def _friend_heroes_adjacent_to(scene, tgt_id, team):
    """#1019 -- face PREDICTION du foyer `damage_model._friend_heroes_adjacent_to` :
    `UnitsWithTrait( Friends(Owner, AdjacentUnits(Target@<+0x60>, 1, 3), 3), 0x10 = Hero, 3 )`,
    COMPTE. MEMES trois criteres (equipe du beneficiaire, trait `Hero`, adjacence NATIVE), MEME
    tri-etat : `None` = question NON POSEE (pas de cible / pas de position / equipe inconnue),
    jamais `0` -- le lecteur FERME son gate sur `None`."""
    if tgt_id is None or team is None:
        return None
    tp = scene.pos(tgt_id)
    if not tp:
        return None
    elev = _pf_board.elevations_by_pos(scene.board)
    neigh = _pf_board.adjacent_neigh_by_pos(scene.board)
    n = 0
    for uid in scene.pos_by_id:
        if uid == tgt_id:
            continue                                       # AdjacentUnits exclut l'origine
        if scene.team(uid) != team or (scene.hp(uid) or 0) <= 0:
            continue                                       # Friends(Owner, ...)
        if UnitTrait.Hero.name not in (_entity_traits(scene, uid) or frozenset()):
            continue                                       # UnitsWithTrait(0x10 = Hero)
        if bq_is_adjacent(tp, scene.pos(uid), elev, neigh):
            n += 1
    return n


def _adjacent_unit_profiles(scene, uid):
    """#1025-r1 -- face PREDICTION du foyer `damage_model._adjacent_unit_profiles` :
    `AdjacentUnits( <uid>, unique: true, OnlyAliveAndTargetable = 3 )` enrichi de
    `(team, visual_id, rarity, is_hero)` par voisin, le substrat des branches des
    `$$CreateTargetSelector` de
    `IdunBattle.Entities.Effects.Loki.MoreGitzOverEre_ExtraDamagePctEffect` et
    `IdunBattle.Entities.Effects.Loki.OnMyPosition_ExtraDamagePctEffect` (#1024-r2).

    L'adjacence vient de `Scene.adjacent_unit_ids` (foyer PARTAGE `playbook/adjacency.py`, donc
    liste STOCKEE + porte d'elevation + multi-tuiles), MEME substrat que la face COMBAT. Le filtre
    `Friends(Owner, ...)` du natif est relatif au PORTEUR de l'effet -> il est rejoue dans la
    classe d'effet, pas ici.

    `is_hero` = `HeroUnits( <univers>, 3 )`, que `IdunBattleLogic.Entities.DSLSelectors$$HeroUnits`
    rend LITTERALEMENT par `UnitsWithTrait(entities, 0x10 = UnitTrait.Hero, selectionType)` --
    branche B de 1444 seulement. MEME foyer de traits (`_entity_traits`) et MEME lecture que
    `_friend_heroes_adjacent_to` ci-dessus (#1019).

    `None` = NON MESURE (pas de cible, ou `adjacent_unit_ids` sans equipe/position) -> le gate se
    FERME. Un tuple VIDE est une MESURE : << aucun voisin >>."""
    if uid is None:
        return None
    ids = scene.adjacent_unit_ids(uid)
    if ids is None:
        return None
    return tuple((int(i), scene.team(i), scene.vis_by_id.get(i), _entity_rarity(scene, i),
                  UnitTrait.Hero.name in (_entity_traits(scene, i) or frozenset()))
                 for i in sorted(ids))


def _wisdom_valid_adjacent_friends(scene, uid, elev, neigh) -> "frozenset":
    """`ValidCharacter( AdjacentFriends(<uid>, unique = true, 3) )` -- face PREDICTION du foyer
    `runner.damage_model._wisdom_valid_adjacent_friends` (un noeud natif, deux substrats).

        AdjacentFriends(u, unique, sel) = Friends( reference = u,
                                                   Units(AdjacentTiles(u), unique, sel) - u,
                                                   sel )
        ValidCharacter(x)               = UnitsWithRarity(x, idun.meta.Rarity.Mythic = 5, 3)

    MEMES criteres (equipe du sujet, rarete `Mythic`, vivant, adjacence NATIVE `bq_is_adjacent` --
    liste stockee + porte d'elevation, jamais `hexgeo.distance == 1`). Ensemble VIDE quand `uid` n'a
    pas de position : c'est le comportement natif (`AdjacentTiles` d'une entite hors-plateau), et
    c'est ce qui fait taire la branche `A` du selecteur sur une MACHINE OF WAR."""
    up = scene.pos(uid)
    team = scene.team(uid)
    if not up or team is None:
        return frozenset()
    out = set()
    for oid in scene.pos_by_id:
        if oid == uid:
            continue                                       # `op_Subtraction unit`
        if scene.team(oid) != team or (scene.hp(oid) or 0) <= 0:
            continue                                       # `Friends(reference = unit, ...)` + sel 3
        if _entity_rarity(scene, oid) != _Rarity.Mythic:
            continue                                       # `ValidCharacter`
        if bq_is_adjacent(up, scene.pos(oid), elev, neigh):
            out.add(int(oid))
    return frozenset(out)


def wisdom_of_the_ancients_target_ids(scene, owner_id) -> "frozenset | None":
    """`IdunBattle.Entities.Effects.Loki.WisdomOfTheAncients_DamageReductionEffect$$
    CreateTargetSelector` EVALUE pour `owner_id` -- face PREDICTION du foyer
    `runner.damage_model.wisdom_of_the_ancients_target_ids` (#1042-r1). MEME arbre, MEME tri-etat :

        A = ValidCharacter( AdjacentFriends(Owner@<+0x30>, unique = true, 3) )
        B = ValidCharacter( Friends(of = Owner@<+0x30>, entities = AllUnits@<+0x20>, 3) )
        F = Filter( B, AmountIsGreaterThanZero(
                           UnitsWithTrait( ValidCharacter( AdjacentFriends(<element courant>,
                                                                          unique = true, 3) ),
                                           UnitTrait.Hero = 0x10, 3 ) ) )
        return ConditionalSelector( IsMachine(Owner), ifTrue = F, ifFalse = Unique(A + F) )

    Le `ConditionalSelector` est une EQUIVALENCE cote port (`IsMachine(Owner)` => pas de tuile =>
    `A = {}` => `Unique(A + F) == F`) : cf. la docstring de
    `entities/effects/loki/damage_reduction.py::WisdomOfTheAncientsDamageReductionEffect`, qui porte
    la mesure et nomme le garde.

    `None` = question NON POSEE (porteur sans equipe), jamais un `frozenset()` invente."""
    team = scene.team(owner_id) if owner_id is not None else None
    if team is None:
        return None
    elev = _pf_board.elevations_by_pos(scene.board)
    neigh = _pf_board.adjacent_neigh_by_pos(scene.board)
    out = set(_wisdom_valid_adjacent_friends(scene, int(owner_id), elev, neigh))   # A
    for uid in scene.pos_by_id:
        if uid == owner_id or uid in out:
            continue                                       # `Unique`
        if scene.team(uid) != team or (scene.hp(uid) or 0) <= 0:
            continue                                       # B : `Friends(Owner, AllUnits(), 3)`
        if _entity_rarity(scene, uid) != _Rarity.Mythic:
            continue                                       # B : `ValidCharacter`
        # F : `AmountIsGreaterThanZero( UnitsWithTrait(ValidCharacter(AdjacentFriends(uid)), Hero) )`
        for vid in _wisdom_valid_adjacent_friends(scene, int(uid), elev, neigh):
            if UnitTrait.Hero.name in (_entity_traits(scene, vid) or frozenset()):
                out.add(int(uid))
                break
    return frozenset(out)
def _cabal_valid_adjacent_to(scene, unit_id, team):
    """#1036-r2 -- face PREDICTION du foyer `damage_model._cabal_valid_adjacent_to` :
    `AmountIsGreaterThanZero( ValidCharacter( AdjacentFriends(<element courant @DSLSelectors+0x68>,
    unique = true, OnlyAliveAndTargetable) ) )`, le filtre `F` du selecteur de
    `CabalOfSorcerers_ExtraDamagePctEffect`, rendu comme un COMPTE.

    MEMES criteres que la face COMBAT (equipe, vivant, `Rarity.Mythic`, `Psyker` ET `Hero`,
    adjacence NATIVE) et MEME tri-etat : `None` = question NON POSEE, jamais `0`."""
    if unit_id is None or team is None:
        return None
    up = scene.pos(unit_id)
    if not up:
        return None
    elev = _pf_board.elevations_by_pos(scene.board)
    neigh = _pf_board.adjacent_neigh_by_pos(scene.board)
    n = 0
    for uid in scene.pos_by_id:
        if uid == unit_id:
            continue                                       # AdjacentUnits exclut l'origine
        if scene.team(uid) != team or (scene.hp(uid) or 0) <= 0:
            continue                                       # AdjacentFriends -> meme equipe, vivant
        if _entity_rarity(scene, uid) != _Rarity.Mythic:
            continue                                       # UnitsWithRarity(..., Mythic = 5)
        traits = _entity_traits(scene, uid) or frozenset()
        if UnitTrait.Psyker.name not in traits or UnitTrait.Hero.name not in traits:
            continue                                       # UnitsWithTraits([Psyker, Hero]) = ET
        if bq_is_adjacent(up, scene.pos(uid), elev, neigh):
            n += 1
    return n


def _effect_names_of(scene, uid):
    """#1036-r1 -- noms des effets NON CONSOMMES de l'entite, face PREDICTION.

    Substrat d'`EntitiesWithAnyEffect(..., effectTarget = EffectTargetType.Both)` dont le
    call-site passe `onlyActive = 0` : le store BRUT `EffectsState.by_unit`, filtre sur le seul
    `consumed` -- PAS `scene.effects(uid)` (qui applique le flag `IsActive` et la
    `CreateActiveCondition`). MEME semantique que la face COMBAT
    (`damage_model._target_effect_names`), donc pas de fork.

    TRI-ETAT : `None` = NON MESURE (pas d'unite, pas de store) -> le gate se FERME."""
    if uid is None:
        return None
    by_unit = getattr(getattr(scene, "eff_state", None), "by_unit", None)
    if by_unit is None:
        return None
    return frozenset(n for n in (getattr(e, "name", None)
                                 for e in (by_unit.get(int(uid)) or [])
                                 if not getattr(e, "consumed", False)) if n)


def _apply_ally_attack_dmg_bonus(mods, scene, att_id, att_pos, is_melee, tgt_armor_reduced, carriers=None,
                                 tgt_id=None, is_normal_attack=None, damage_profile=None):
    """AURA ALLIEE +degat FLAT projetee sur l'ATTAQUANT par les effets `create_aura_attack_damage_bonus_for_ally`
    de ses ALLIES a portee (canal cote SOURCE) : `BeaconOfRage_FriendlyExtraDamage` (#191 : +50% rage aux amis
    Chaos adjacents en melee), `ConquerorImperative` (#23 : +extraDmg aux amis Mechanical ring-1 vs cible a
    armure reduite), `LordOfTheHost_ExtraDamage` (#57c : +extraDmg melee aux amis RapidAssault/Flying rayon 2
    de Dante) et `Doom_extraDmg` (#57c : +extraDmg aux attaques des amis d'Eldryon CONTRE la cible doomee a
    exactement 2 hexes — gate cote CIBLE, d'ou tgt_id/t_pos/tgt_team dans le ctx). Le +extraDmg de Conqueror
    s'applique a TOUTES les attaques (aucun IsNormalAttack) -> appele par la NORMALE ET la SPECIALE
    (`is_normal_attack` threade pour les gates qui distinguent, ex. la branche non-Aeldari de Doom).
    `carriers` (8-tuple de la normale) reutilisable ; sinon construit un 4-tuple (uid,pos,team,effets). Le ctx
    est keye sur l'ATTAQUANT (+ cible), les gates lisant le sous-ensemble pertinent. Symetrique combat de
    `damage_model._apply_ally_attack_damage_auras`."""
    if carriers is None:
        # #999-r3-r1-r1 -- univers BOARD-WIDE, cf. `_def_carriers` ci-dessus et la docstring de
        # `Scene.effect_carrier_ids`. Une MoW alliee porteuse d'une aura ATTAQUE (1442, 1449, 1494,
        # 1548) n'entrait dans AUCUN carrier faute de position.
        carriers = [(uid, scene.pos(uid), scene.team(uid), scene.effects(uid))
                    for uid in scene.effect_carrier_ids(exclude=att_id)
                    if scene.hp(uid) is None or (scene.hp(uid) or 0) > 0]
    # `att_gu` reste le KIT : `GrandAllianceId` / `FactionId` / `weapons` sont des donnees de
    # CONFIGURATION (aucun equivalent d'entite), contrairement aux TRAITS (#267-r1).
    att_gu = GC.unit(scene.vis_by_id.get(att_id)) or {}
    ctx = {"att_id": att_id, "att_pos": att_pos, "att_team": scene.team(att_id),
           "att_grand_alliance": att_gu.get("GrandAllianceId"),
           "att_faction": att_gu.get("FactionId"),
           # #267-r1 : traits de l'ATTAQUANT = substrat d'ENTITE — pendant exact du
           # `"att_traits": target_trait_names(state, att_id)` de
           # `damage_model._apply_ally_attack_damage_auras`.
           "att_traits": _entity_traits(scene, att_id),
           # UnitsWithRangedAttacks (selector SpotterReworked IdunBattle.Entities.Effects.Loki.SpotterReworked_ExtraDamageEffect$$CreateTargetSelector) = UNION {arme ranged au kit}
           # + {diff elevation <= 2 vs tuile porteur} (IdunBattleLogic.Entities.DSLFactory$$UnitsWithRangedAttacks) -> board pour le terme elevation
           "att_has_ranged_weapon": any(w.get("Range") for w in (att_gu.get("weapons") or ())),
           "board": scene.board,
           "is_melee": is_melee, "target_armor_reduced": tgt_armor_reduced,
           "is_normal_attack": is_normal_attack,
           # DefenderOfTheGreaterGood_ExtraDmg (#220, aura Tau) : gate !DamageProfileIs(Psychic) IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraDmgEffect$$CreateDamageModifier.
           "damage_profile": damage_profile,
           "tgt_id": tgt_id,
           "t_pos": scene.pos(tgt_id) if tgt_id is not None else None,
           "tgt_team": scene.team(tgt_id) if tgt_id is not None else None,
           # Traits de la CIBLE -- gate `HasTrait(Target@0x178, ...)` des auras dont la condition
           # porte sur la cible : `DestroyTheWitch_ExtraDamage` (aura melee vs **Psyker**,
           # IdunBattle.Entities.Effects.Loki.DestroyTheWitch_ExtraDamageEffect$$CreateEffectDamageBonusForAttack).
           # Symetrique du `tgt_traits` que l'agregateur DEFENSE passait deja. #267-r1 : substrat
           # d'ENTITE (le `target_traits=target_trait_names(...)` que le combat threade deja ici).
           # `None` (appelant sans cible) reste DISTINCT de `frozenset()` : ces gates rendent None
           # au lieu de conclure « la cible n'a pas le trait ».
           "tgt_traits": _entity_traits(scene, tgt_id) if tgt_id is not None else None,
           # #1019 -- cf. `_friend_heroes_adjacent_to` ci-dessus (foyer PREDICTION). TRI-ETAT.
           "friend_heroes_adjacent_to_target": _friend_heroes_adjacent_to(
               scene, tgt_id, scene.team(att_id)),
           # `PsychicStalk_FriendlyChaosExtraDamage` (#366-r1, effet 1435) : son conjoint
           # `GetTargetIsOnFireTileCondition` lit `EntitiesWithAnyEffect(Tiles(Target@0x60), Fire)`.
           # MEME cle / MEME forme `{(col,row): [noms]}` que celle deja threadee a l'agregateur
           # DEFENSE ci-dessus et que la face COMBAT (`_apply_ally_attack_damage_auras`).
           "tile_effects_by_pos": scene.tile_effects_by_pos,
           # #919 -- `StatAmount(Owner@DSLSelectors+0x30, BlockDamage, Current)` de
           # `IconOfObstinacy_ExtraDamageEffect$$GetCurrentExtraDamage`. MAP par PORTEUR : c'est
           # `aura_attack_damage_bonus_from_allies` qui pose `owner_id` dans son ctx par-carrier, et
           # l'effet re-cle avec. MEME cle et MEME semantique que la face COMBAT
           # (`damage_model._apply_ally_attack_damage_auras`) -- pas de fork.
           "owner_stat_block_damage": {c[0]: prediction_block_damage(scene, c[0]) for c in carriers},
           # #926 -- `TotalAttacksMade(EffectSource)` de
           # `IdunBattle.Entities.Effects.Loki.FirstAmongTraitors_ExtraDmgEffect$$CurrentDamageBonus`.
           # MAP par PORTEUR (l'agregateur pose `owner_id` dans son ctx par-carrier). Le canal est
           # `Scene.total_attacks_made` = le capteur live `actorStats.totalAttacksMade`, c.-a-d.
           # exactement le champ `ActorStatisticsComponent+0x20` que la face COMBAT lit par
           # `components.unit_total_attacks_made` -- MEME cle, MEME semantique, pas de fork.
           "owner_total_attacks_made": {c[0]: scene.total_attacks_made(c[0]) for c in carriers},
           # #999-r3-r1 -- RARETE de l'ATTAQUANT (le BENEFICIAIRE de ce canal : `get_OwnerIsCaster`
           # apres que la boucle native a ecrit `AbilityEntities+0x18 (Owner) <- CHAQUE CIBLE du
           # selecteur`), donc l'etage `UnitsWithRarity(...)` d'un `$$CreateTargetSelector` se lit
           # ICI. Consommateur : `BlightedLandEffect` (1442). MEME cle et MEME semantique que la face
           # COMBAT (`damage_model._apply_ally_attack_damage_auras`) -- pas de fork. TRI-ETAT.
           # ⚠ La cle jumelle `tile_effects_by_pos` porte DEJA tout le plateau cote PREDICTION
           # (`scene.tile_effects_by_pos`), la ou le COMBAT a du y ajouter la tuile de l'attaquant.
           "att_rarity": _entity_rarity(scene, att_id),
           # #1036-r1 -- `EntitiesWithAnyEffect(<les allies du porteur>, [NanoscarabRepairProtocols],
           # effectTarget = Both)` du selecteur de `GuardianConstruct_ExtraDamagePctEffect`, lu sur
           # l'ATTAQUANT (le BENEFICIAIRE de ce canal). MEME cle et MEME semantique
           # (`onlyActive: false` -> store BRUT) que la face COMBAT. TRI-ETAT.
           _GUARDIAN_CTX_ATT_EFFECTS: _effect_names_of(scene, att_id),
           # #1036-r2 -- `IsMachine(Owner)` du `ConditionalSelector` de
           # `CabalOfSorcerers_ExtraDamagePctEffect`, MAP par PORTEUR (l'agregateur re-cle par
           # `owner_id`). Cote DECISION la nature d'entite vient de `Scene.is_machine` (les
           # `casterId` de `decisionView.mows`, mirror d'`EntityType.Machine = 6`) -- MEME cle et
           # MEME semantique que la face COMBAT (`components.is_machine_of_war`).
           _CABAL_CTX_OWNER_IS_MACHINE: {c[0]: scene.is_machine(c[0]) for c in carriers},
           # #1036-r2 -- cf. `_cabal_valid_adjacent_to` ci-dessus (le filtre `F`). TRI-ETAT.
           _CABAL_CTX_VALID_ADJACENT: _cabal_valid_adjacent_to(scene, att_id, scene.team(att_id))}
    for eb in aura_attack_damage_bonus_from_allies(carriers, ctx):
        add_modifier(mods, eb)


def defender_prediction_block_amount(scene, tgt_id, damage_profile: str | None = None) -> int:
    """Amount de BLOCK du defenseur pour le scenario `list[0]@0x50` de la prediction (#54A) —
    mirror des entrees `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances` consommees par le scenario block
    (`IdunBattle.Core.Services.DamagePrediction$$CalculateDamagePredictionScenario`) : scalaire GetStat(7/8)
    (blockChance/blockDamage) + sources multi-value des EFFETS du defenseur (Daemon_ExtraBlock
    25 %/50 %×Attack courant, BeastSlayer_ExtraBlock…). Approximation documentee : sources
    multiples SOMMEES (un seul cas mesure, mono-source Daemon — 1357 s15). 0 = pas de block
    → liste native vide → WillBeKill/WillBeOverkill retombent sur les scalaires raw.

    #69 : GATE `NoBlocking` (DamageTrait 0) du PROFIL de degat — mirror du gate COMBAT
    `AttackDamageOperation._block_sources` (`runner/operations/damage.py`) ET du skip natif de la
    PREDICTION : `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` fait `DamageProfile.HasTrait(profile,
    0=NoBlocking)` (IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x2bec) et SKIP toute la boucle de construction du scenario block
    (`param_1[10]`, list[0]@0x50) quand le flag est pose (`if (blockList != 0 && (char)HasTrait == 0)
    {...}`). Un profil `Psychic` (Traits=['NoBlocking'], PiercingRatio 100 ; wiki « Cannot be
    blocked ») bypasse donc le block en PREDICTION comme en COMBAT -> amount 0 -> `_with_block` no-op
    -> block_raw_min reste None -> WillBeKill/WillBeOverkill retombent sur le scalaire raw (== natif :
    liste block vide). Sans ce gate, la prediction sur-comptait le block d'une attaque Psychic
    (kill-prediction IA faussee ; residu documente case-65-noblocking-block-bypass §« Non couvert »)."""
    if damage_profile is not None:
        if DamageTrait.NoBlocking.name in ((GC.damage_profile(damage_profile) or {}).get("Traits") or []):
            return 0        # profil NoBlocking -> block bypasse (mirror IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x2bec + _block_sources)
    amt = 0
    tctx = scene.ctx(tgt_id)
    if tctx is not None and int(tctx.block_chance or 0) > 0:
        amt += int(tctx.block_damage or 0)
    # #1015-r1 : `scene.hpmax` = `combatSnapshot.healthMax` = `GetStat(e, Health = 5, StatPart = 2)`
    # -- EXACTEMENT le `StatAmount(Owner, 0x5, 0x2)` que lit `BeastSnaggaAbility$$CreateBehaviour`
    # pour l'amount de sa source de block. `None` (unite hors table) -> 0 -> source inerte.
    for bs in defender_effect_block_sources(scene.effects(tgt_id), scene.armor(tgt_id),
                                            defender_attack=scene.attack_current(tgt_id),
                                            defender_max_health=int(scene.hpmax(tgt_id) or 0)):
        amt += int(bs.amount or 0)
    return amt
