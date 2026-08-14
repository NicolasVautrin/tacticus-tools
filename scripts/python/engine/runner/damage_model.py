"""Plage de tirage de dégât calculée PAR LE RUNNER depuis son ECS (stats + effets).

Le but du chantier : un runner AUTONOME (fidèle ET modifiable). Cette couche assemble,
depuis les composants ECS (`StatsComponent` + `State.effects`), les entrées de la chaîne
de dégât VALIDÉE (`engine.services.damage_prediction.get_attack_prediction`) — au lieu de
relire l'oracle live. Elle expose la **plage BRUTE d'un coup** (pré-armure, pré-perçage,
mono-coup) = le `HitDamage` que `AttackDamageOperation.ExecuteHit` tire.

Découpage volontaire (couche stats+effets uniquement) :
  • base PAR COUP = `stat Attack` (StatAmountFormula(Attack)) → spread BC (CalculateDamageSpread).
  • × MODIFIERS attaquant bâtis depuis les EFFETS actifs (post-perçage §17.7 ; pré-perçage = id
    ici car armure/perçage = 0). Effets pré-tirage (ex. +ExtraDmg sur le stat) déjà cuits dans
    `ctx.attack`.
  • PAS de hits / arme / perçage / armure / cible : ce sont des paliers DAMAGE séparés. La plage
    d'UN coup est indépendante d'eux (perçage/armure s'appliquent APRÈS le tirage).

Validé par agrément : plage runner == plage `aiPredict` (pré-armure) PAR COUP, sur les unités
(`tests/engine/runner/test_runner_stats_effects_live.py`).
"""
from __future__ import annotations

from fractions import Fraction
from typing import Optional, Tuple

# Foyer d'arrondi PARTAGE (`IdunBattle.DSL.AAmountFormula$$RoundFix64Result`), pas un round local.
# Import de NIVEAU MODULE : classe GRATUITE, mesuree -- `engine.dsl.base` charge seul dans un
# process frais SANS tirer `engine.runner.damage_model`, donc hisser ne ferme aucun cycle. Meme
# forme que les trois sites qui le consomment deja (`ai/action_generators.py`,
# `playbook/prediction/_shared.py`, `playbook/spirit_leech.py`) ; aucun patcheur ne le vise.
from ..dsl.base import _round_fix64
from .state import State
from .components import (StatsComponent, HealthComponent, OwnerComponent, PositionComponent,
                         UnitComponent, unit_has_moved, unit_has_teleported,
                         unit_has_used_active_ability,
                         unit_tiles_moved_this_turn, unit_state_for_effects,
                         unit_turns_with_attacks_made, unit_total_attacks_made,
                         adjacent_taunted_enemies_count,
                         adjacent_dark_angels_friends_count,
                         enmity_adjacent_units_count,
                         enmity_adjacent_dark_angels_friends_count,
                         close_combat_weakness_adjacent_enemies_count,
                         adjacent_enemy_ids,
                         # #1073 : le PREMIER disjoint de `SynapticInsight_ExtraHits`, ancre sur la
                         # CIBLE du coup (et non sur le porteur, contrairement a ses voisins).
                         synaptic_insight_adjacent_tyranid,
                         # #1036-r2 : `IsMachine(Owner)` du `ConditionalSelector` de
                         # `CabalOfSorcerers_ExtraDamagePctEffect` -- mirror d'`EntityType.Machine`.
                         is_machine_of_war)
# #1015-r1 : meme foyer de nommage pour les DEUX faces du terme geometrique de
# `CloseCombatWeakness_ReduceDmg_Effect$$NearbyEnemiesCondition`.
from ..entities.effects.loki.close_combat_weakness import (
    CTX_ADJACENT_ENEMIES as _CCW_CTX_ADJACENT_ENEMIES)
# #948 : les cles du contexte per-coup d'`EnmityForTheUnworthy` viennent de la classe d'effet --
# un seul foyer de nommage pour les DEUX faces (COMBAT ici, PREDICTION dans `playbook/`).
from ..entities.effects.loki.enmity_for_the_unworthy import (
    CTX_ADJACENT_UNITS as _ENMITY_CTX_UNITS, CTX_ADJACENT_DA as _ENMITY_CTX_DA)
from ..entities.effects.loki.skullsmasher import CTX_OWNER_HEALTH as _SKULLSMASHER_CTX_HEALTH
# #1011 : memes deux cles pour les DEUX faces de `NornCrownEffect` -- un seul foyer de nommage.
from ..entities.effects.loki.norn_crown import (
    CTX_TGT_EFFECT_NAMES as _NORN_CTX_TGT_EFFECTS,
    CTX_TEAM_SYNAPSE_POSITIONS as _NORN_CTX_SYNAPSE)
from ..entities.effects.loki.obsessive_annunciation import (
    CTX_ADJACENT_ENEMY_IDS_OF as _OA_CTX_ADJ_ENEMY_IDS)
# #1073 : la cle du PREMIER disjoint de `SynapticInsight_ExtraHits` -- MEME foyer de nommage pour
# les DEUX faces (cf. `playbook/prediction/normal_attack.py`).
from ..entities.effects.loki.synaptic_insight import (
    CTX_ADJACENT_TYRANID as _SI_CTX_ADJACENT_TYRANID)
# #1025-r1 : la cle du substrat d'adjacence de `MoreGitzOverEre_ExtraDamagePct` -- MEME foyer de
# nommage pour les DEUX faces (cf. `playbook/prediction/_shared.py`).
from ..entities.effects.loki.extra_damage_aura import (
    CTX_TGT_ADJACENT_UNIT_PROFILES as _MG_CTX_TGT_ADJ_PROFILES)
# #1042-r1 : le `$$CreateTargetSelector` de `WisdomOfTheAncients_DamageReductionEffect` (1445),
# re-evalue PAR PORTEUR -- un seul foyer de nommage pour les DEUX faces (cf. `prediction/_shared`).
from ..entities.effects.loki.damage_reduction import (
    CTX_WISDOM_TARGET_IDS_OF as _WOTA_CTX_TARGET_IDS,
    CTX_TERTIARY_ABILITY_STATE_OF as _MYTHIC_CTX_ABILITY_STATE)
# #1036-r1/-r2 : memes trois cles pour les DEUX faces des deux mythiques de MoW -- un seul foyer
# de nommage, comme `norn_crown` ci-dessus.
from ..entities.effects.loki.extra_damage_aura import (
    CTX_ATT_EFFECT_NAMES as _GUARDIAN_CTX_ATT_EFFECTS,
    CTX_OWNER_IS_MACHINE as _CABAL_CTX_OWNER_IS_MACHINE,
    CTX_CABAL_VALID_ADJACENT_TO_ATT as _CABAL_CTX_VALID_ADJACENT)
from ..entities.stats import StatType, ARMOR_STAT_TYPES
from ..services.damage_prediction import get_attack_prediction, apply_pierce_and_modifiers
from ..services.battle_query import (
    get_attack_weapon_for_default_normal_attack,
    select_weapon_pierce as _bq_select_weapon_pierce,
    are_tiles_adjacent)
from ..entities.effects import (
    aura_defense_damage_malus_from_units, aura_fixed_armor_bonus_for_defense,
    aura_attack_damage_bonus_from_allies,
    build_attacker_modifiers_from_effects, build_defender_modifiers_from_effects,
    hits_bonus_from_effects,
    piercing_bonus_from_effects,        # #1052 : `CasterEffectPierceAddition` de l'AllIsDust
)
from ..entities.traits.combat import GetStuckInTrait, min_distance
from ..entities.effects.magnitude import trait_var
from ..battle_query import is_charging as _bq_is_charging
# #1019 -- `AdjacentUnits(Target@<+0x60>, 1, 3)` du noeud `IsValidAttackForBonus` de
# `WayOfTheShortBladeEffect` : l'adjacence NATIVE (liste stockee + porte `|dElev| < 2`), pas une
# couronne hex nue -- meme foyer que `#943-r7`.
from ..battle_query import is_adjacent as _bq_is_adjacent
from ..entities.effect_type import EffectType
from ..entities.effects.loki.dark_angels_passives import grand_alliance_of
from ..entities.effects.magnitude import bc_effect_config
from ..entities.pathfinding.board import adjacent_neigh_by_pos, elevations_by_pos
from ..entities.rarity import Rarity   # `idun.meta.Rarity` -- `UnitsWithRaritySelector$$Select`
#                                        (#1042-r1) et `UnitsWithRarity` (#1036-r2)
from ..entities.traits.unit_trait import UnitTrait
from ..services.damage_config import resolve_damage_field
from ..services.damage_modifiers import (add_modifier, calculate_elevation_bonus_modifier,
                                             ELEVATION_BONUS_PCT, EFFECT_NO_ELEVATION)
from ..services.damage_modifiers import (add_modifier, calculate_trench_reduction,
                                             _TRENCH_IGNORED_PROFILES)
from ..services.damage_modifiers import add_modifier
from ..services.static_battle_rules import is_tile_status_effect
from ..utilities.tile import terrain_tile_effects
from .components import PersistentDataComponent
from .components import charged_unit_ids

_BIG_HP = 1 << 30          # santé cible « infinie » → scenario sans overkill/cap


def select_weapon(ctx, dist: Optional[int], is_adjacent: Optional[bool] = None):
    """Arme de l'attaque normale par PORTÉE — DÉLÈGUE au service PARTAGÉ
    `battle_query.get_attack_weapon_for_default_normal_attack` (foyer natif BattleQuery ; MÊME port que
    la prédiction). `dist` = distance HEX RÉELLE attaquant->cible. Renvoie le dict d'arme (ou None).

    `is_adjacent` DÉCOUPLÉ de `dist` (#419-r1-tr14-r1-r1) : le natif les lit sur DEUX canaux distincts
    — `BattleQuery$$AreEntitiesAdjacent` (adjacence hex élévation-gatée, empreintes complètes) pour
    choisir la branche mêlée, et la distance rendue par le service de mouvement pour la porte
    `dist <= Range` de `FindRangedWeapon`. Les rabattre l'un sur l'autre (`dist <= 1`) obligeait
    l'appelant à passer une distance BINAIRE (1 ou 2), donc à ne jamais pouvoir dépasser la portée
    d'une arme : `None` garde ce comportement historique pour les appelants qui n'ont que `dist`."""
    w, _ranged = get_attack_weapon_for_default_normal_attack(
        ctx.visual_id,
        is_adjacent=(is_adjacent if is_adjacent is not None else (dist is not None and dist <= 1)),
        prefer_hits=ctx.normal_hits, dist=dist)
    return w


def select_weapon_pierce(ctx, dist: Optional[int], effect_bonus: int = 0,
                         is_adjacent: Optional[bool] = None) -> Tuple[int, bool, int]:
    """Arme + perçage par PORTÉE — DÉLÈGUE au service PARTAGÉ `battle_query.select_weapon_pierce`
    (un service natif = UN port, prédiction ET combat l'appellent). `dist` = distance HEX RÉELLE ;
    `is_adjacent` découplé (cf. `select_weapon`), `None` -> `dist <= 1` comme avant.
    Renvoie `(pierce, is_ranged, whits)` (le profil est fourni séparément par `select_weapon`).
    `effect_bonus` = Σ des `EffectBonus` de perçage de l'attaquant (`BaseEffect$$PiercingBonusForAttack`),
    sommé DANS le clamp natif unique (cf. la docstring du service). Défaut 0 = inchangé."""
    adj = is_adjacent if is_adjacent is not None else (dist is not None and dist <= 1)
    pierce, is_ranged, whits, _prof = _bq_select_weapon_pierce(ctx, adj, dist,
                                                              effect_bonus=effect_bonus)
    return pierce, is_ranged, whits


def resolve_one_hit(roll: int, pierce: int, armor: int, mods=None) -> int:
    """Réduction d'UN coup tiré = **BASE COMMUNE** avec la prédiction : délègue à
    `apply_pierce_and_modifiers` (la fn par-valeur que la prédiction applique à ses bornes).
    Combat = même fn sur la valeur TIRÉE ⇒ dégâts identiques à la prédiction par construction."""
    return apply_pierce_and_modifiers(roll, pierce, armor, mods)


def target_trait_names(state: State, target_id: int) -> "frozenset[str]":
    """Noms de traits gameconfig de la CIBLE (via `StatsComponent.ctx.traits`) — pour les conditions
    target-trait des bonus ATTAQUANT (ex. BeastSlayer vs BigTarget/Vehicle ; mirror `HasTrait(target,…)`).
    frozenset vide si indispo (cible sans StatsComponent)."""
    e = state.get_entity(target_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    return frozenset(getattr(sc.ctx, "traits", None) or []) if sc is not None else frozenset()


def defender_armor_reduced(state: State, target_id: int) -> bool:
    """Gate `HasNegativeModifier(cible, {ARMOR=4, FIXED_ARMOR=16})` de `ConquerorImperative.CreateDamageModifier`
    (IdunBattle.Entities.Effects.Loki.ConquerorImperativeEffect$$CreateDamageModifier ; trigger `IdunBattle.Entities.Triggers.HasNegativeModifier$$ShouldTrigger`) : la CIBLE a-t-elle >=1 modification per-source NEGATIVE
    sur l'une des 2 stats d'armure = « armure REDUITE » ? DELEGUE a `UnitStats.has_negative_modifier` (foyer du
    check, mirror natif). False si la cible n'a pas de StatsComponent. Consomme par le canal +extraDmg de Conqueror
    (self face, incr. C) au site de resolution `attacker_modifiers` (combat) — symetrique de la prediction."""
    e = state.get_entity(target_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None or sc.ctx is None:
        return False
    return sc.ctx.stats.has_negative_modifier(ARMOR_STAT_TYPES)


def defender_fixed_armor(state: State, target_id: int) -> int:
    """FixedArmor(16) EFFECTIVE du DÉFENSEUR = `GetStat(16)` [effet-inclusif : inclut le stat-mod EAGER self
    de ProtectorImperative sur SON porteur, incr. A] + AURA +FixedArmor projetée par un ALLIÉ ADJACENT porteur
    (`create_aura_fixed_armor_bonus_for_defense` : `ProtectorImperative` reach = self + `AdjacentFriends(1)` ∩
    `UnitsWithTrait(5=Mechanical)`, IdunBattle.Entities.Effects.Loki.ConquerorImperativeEffect$$CreateTargetSelector). Le porteur (self) est déjà couvert par `GetStat` → l'aura
    n'ajoute QUE pour un défenseur allié-adjacent DISTINCT du porteur (auto-exclusion def==owner ⇒ pas de
    double-compte). RÉ-ÉVALUÉ PAR ADJACENCE ici (site de résolution armure), mirror du natif
    DynamicStatModifierEffect dont la ValueModification atteint TOUTES ses cibles-sélecteur.

    FOYER UNIQUE de résolution de l'armure défenseur pour le COMBAT (appelé par TOUS les vecteurs de dégât :
    normale/ability/splash + DoT tuile) — 1 service natif = 1 port (check-own-port), pas de fork. (La PRÉDICTION
    IA est PRÉ-armure — armor=0 — donc non concernée : l'armure n'entre pas dans la décision.) Court-circuit
    non-Mechanical : un bénéficiaire non-Mechanical n'a jamais d'aura Protector → renvoie la base direct."""
    e = state.get_entity(target_id)
    tsc = e.get_component(StatsComponent) if e is not None else None
    base = int(tsc.ctx.stat(StatType.FIXED_ARMOR)) if tsc is not None else 0
    if state.effects is None or e is None:
        return base
    toc = e.get_component(OwnerComponent)
    tpc = e.get_component(PositionComponent)
    if toc is None or tpc is None:
        return base
    def_traits = target_trait_names(state, target_id)
    if "Mechanical" not in def_traits:
        return base                                       # bénéficiaire non-Mechanical -> aucune aura Protector
    carriers = []
    for uid, ent in state.entities.items():
        if uid == target_id:
            continue
        oc = ent.get_component(OwnerComponent)
        pc = ent.get_component(PositionComponent)
        if oc is None or pc is None or oc.team != toc.team:
            continue                                      # Friends du porteur = même équipe que le défenseur
        # VIVANTS SEULEMENT (#57m, #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r1) : `AdjacentFriends(1)` est
        # une OCCUPATION DE TUILE (`IdunBattleLogic.Entities.DSLFactory$$AdjacentUnits` =
        # `Units(AdjacentTiles(.)) - .`) -- un mort n'est plus sur le board, donc ne projette aucune
        # aura. Ce balayage etait le SEUL des six du port sans gate de vivacite : ses cinq freres
        # (`build_hits_board`, `_crit_carriers`, `collect_additional_hit_groups`,
        # `_apply_ally_attack_damage_auras`, la boucle porteurs de `defender_modifiers`) en portent
        # un depuis #57m. Il tenait par une PROPRIETE DU CAPTEUR, pas par un gate :
        # `KillUnitOperation$$Execute` appelle TROIS fois `RemoveEffects(killed, <step>)`, donc
        # `decisionView.units[].effects` est vide pour un mort et le `if not effs: continue` qui
        # suit l'ecartait. Un etat construit HORS capture (greffe, seed synthetique) viole cette
        # propriete sans erreur.
        _uc = ent.get_component(UnitComponent)
        if _uc is not None and not _uc.alive:
            continue
        effs = state.effects.active_effects(uid, unit_state_for_effects(state, uid))
        if not effs:
            continue
        sc = ent.get_component(StatsComponent)
        lvl = int(getattr(sc.ctx, "active_ability_level", 0) or 0) if sc is not None else 0
        mult = int(getattr(sc.ctx, "ability_variables_multiplier", 100) or 100) if sc is not None else 100
        carriers.append((uid, (pc.col, pc.row), oc.team, mult, lvl, effs))
    if not carriers:
        return base
    aura = aura_fixed_armor_bonus_for_defense(
        carriers, {"def_id": target_id, "def_pos": (tpc.col, tpc.row),
                   "def_team": toc.team, "def_traits": def_traits})
    return base + int(aura)


def _unit_gameconfig(state: State, unit_id: int) -> Optional[dict]:
    """Kit gameconfig de l'unité (résolu par `visual_id`) — partagé par les gates des auras ALLIÉES
    côté source (grande-alliance BeaconOfRage, `UnitsWithRangedAttacks` SpotterReworked). None si
    l'unité ou son visual_id est introuvable."""
    import gameconfig as GC
    e = state.get_entity(unit_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    vid = getattr(sc.ctx, "visual_id", None) if (sc is not None and sc.ctx is not None) else None
    if vid is None:
        return None
    return GC.unit(vid)


def _unit_visual_id(state: State, unit_id: Optional[int]) -> Optional[str]:
    """`visual_id` de l'unite -- substrat de `DSLSelectors$$UnitsWithVisualId`, dont
    `IdunBattle.Entities.Selectors.UnitsFromFactionSelector` et ses voisins comparent la chaine.

    MEME lecture que `_unit_gameconfig` ci-dessus (`StatsComponent.ctx.visual_id`), avec repli sur
    `UnitComponent.visual_id` : un summon SPAWNE en cours de bataille porte son `visual_id` sur le
    composant d'unite avant que son `ctx` de stats soit renseigne. `None` = NON MESURE."""
    e = state.get_entity(int(unit_id)) if unit_id is not None else None
    if e is None:
        return None
    sc = e.get_component(StatsComponent)
    vid = getattr(sc.ctx, "visual_id", None) if (sc is not None and sc.ctx is not None) else None
    if vid is None:
        uc = e.get_component(UnitComponent)
        vid = getattr(uc, "visual_id", None) if uc is not None else None
    return str(vid) if vid else None


def _grand_alliance(state: State, unit_id: int) -> Optional[str]:
    """`GrandAllianceId` gameconfig de l'unité (résolu par `visual_id`) — gate grande-alliance des auras
    ALLIÉES cote source (ex. `BeaconOfRage_FriendlyExtraDamage` : Chaos). Lit DIRECTEMENT le champ
    GrandAllianceId (== la valeur que la prédiction passe, `GC.unit(vis).GrandAllianceId`), analogue de
    `_faction_id` (triggers/base). None si l'unité ou son visual_id est introuvable."""
    return (_unit_gameconfig(state, unit_id) or {}).get("GrandAllianceId")


def marked_effect_types_for_target(state: State, att_id: int, target_id: Optional[int]) -> frozenset:
    """`HasEffect(Target@0x178, <EffectType>, targetType = EffectTargetType.Both)` — l'ensemble des
    EffectTypes dont la CIBLE du coup est une **cible-selecteur** d'un effet porte par l'ATTAQUANT.

    Certains effets natifs ne se materialisent JAMAIS sur la cible : ils vivent sur leur porteur et leur
    `CreateTargetSelector` designe a la demande les entites « marquees » (verifie live sur
    `FearedInterrogator_Target` 1295 : liste chez `darkaAsmodai`, ABSENT de `decisionView.effects` des
    ennemis marques). Le gate `HasEffect(Target, ...)` de leur effet frere doit donc RE-EVALUER le
    selecteur, exactement comme les canaux d'aura le font pour la geometrie.

    Interface duck-typed `marks_target(state, owner_id, target_id) -> bool` (seuls les effets concernes
    la portent, meme regime que `TARGETING_OPTIONS`) -> `frozenset()` strict pour tout le reste."""
    if target_id is None or state.effects is None:
        return frozenset()
    out = set()
    for e in (state.effects.by_unit.get(int(att_id)) or []):
        if e.consumed or e.expired or not e.active:
            continue
        fn = getattr(e, "marks_target", None)
        if fn is None:
            continue
        if fn(state, int(att_id), int(target_id)):
            out.add(int(e.effect_type) if e.effect_type is not None else e.name)
    return frozenset(out)


def _friend_heroes_adjacent_to(state: State, target_id: Optional[int],
                               team) -> Optional[int]:
    """#1019 -- `UnitsWithTrait( Friends(Owner, AdjacentUnits(Target@<+0x60>, 1, 3), 3), 0x10, 3 )`,
    COMPTE. Foyer UNIQUE cote COMBAT du noeud discriminant d'`IdunBattle.Entities.Effects.Loki.
    WayOfTheShortBladeEffect$$IsValidAttackForBonus` ; la face PREDICTION a le sien
    (`playbook/prediction/_shared.py`), sur les memes trois criteres.

    TRI-ETAT : `None` quand la question n'a PAS ETE POSEE (aucune cible, cible sans position,
    equipe inconnue) -- jamais `0`, qui voudrait dire « mesure, et vide ». Le lecteur
    (`WayOfTheShortBladeDamageBuffEffect`) FERME son gate sur `None`.

    L'adjacence est celle du natif (`battle_query.is_adjacent` : liste stockee du
    `ConnectivityComponent` + porte `|dElev| < 2`), pas `hexgeo.distance == 1` (#271/#943-r7).
    `AdjacentUnits` exclut l'origine, donc la cible elle-meme n'est jamais comptee -- et elle est
    de toute facon dans l'autre camp sur tous les chemins cables."""
    if target_id is None or team is None:
        return None
    tp = _unit_pos(state, target_id)
    if not tp:
        return None
    elev = elevations_by_pos(state.board)
    neigh = adjacent_neigh_by_pos(state.board)
    n = 0
    for uid, ent in state.entities.items():
        if uid == target_id:
            continue                                       # AdjacentUnits exclut l'origine
        oc = ent.get_component(OwnerComponent)
        pc = ent.get_component(PositionComponent)
        if oc is None or pc is None or oc.team != team:
            continue                                       # Friends(Owner, ...)
        hc = ent.get_component(HealthComponent)
        if hc is not None and hc.hp is not None and hc.hp <= 0:
            continue
        if UnitTrait.Hero.name not in (target_trait_names(state, uid) or frozenset()):
            continue                                       # UnitsWithTrait(0x10 = Hero)
        if _bq_is_adjacent(tp, (pc.col, pc.row), elev, neigh):
            n += 1
    return n


def _wisdom_valid_adjacent_friends(state: State, uid: int, elev, neigh) -> "frozenset":
    """`ValidCharacter( AdjacentFriends(<uid>, unique = true, 3) )` -- le noeud natif que
    `IdunBattle.Entities.Effects.Loki.WisdomOfTheAncients_DamageReductionEffect$$CreateTargetSelector`
    INLINE deux fois (une fois sur `Owner@<DSLSelectors+0x30>`, une fois sur l'element courant du
    `Filter`). Foyer COMBAT ; la face PREDICTION a le sien
    (`playbook/prediction/_shared.py::_wisdom_valid_adjacent_friends`), sur les MEMES criteres.

        AdjacentFriends(u, unique, sel) = Friends( reference = u,
                                                   Units(AdjacentTiles(u), unique, sel) - u,
                                                   sel )
        ValidCharacter(x)               = UnitsWithRarity(x, idun.meta.Rarity.Mythic = 5, 3)

    L'adjacence est celle du natif (`battle_query.is_adjacent` : liste stockee du
    `ConnectivityComponent` + porte `|dElev| < 2`), pas `hexgeo.distance == 1` (#271/#943-r7) --
    MEME foyer que `_friend_heroes_adjacent_to` (#1019).

    Ensemble VIDE quand `uid` n'a pas de position : c'est le comportement NATIF (`AdjacentTiles`
    d'une entite hors-plateau ne rend rien), et c'est ce qui fait que la branche `A` du selecteur
    se tait d'elle-meme sur une MACHINE OF WAR."""
    up = _unit_pos(state, uid)
    if not up:
        return frozenset()
    uoc = state.get_entity(uid)
    uoc = uoc.get_component(OwnerComponent) if uoc is not None else None
    if uoc is None or uoc.team is None:
        return frozenset()
    out = set()
    for oid, ent in state.entities.items():
        if oid == uid:
            continue                                       # `op_Subtraction unit`
        oc = ent.get_component(OwnerComponent)
        pc = ent.get_component(PositionComponent)
        if oc is None or pc is None or oc.team != uoc.team:
            continue                                       # `Friends(reference = unit, ...)`
        hc = ent.get_component(HealthComponent)
        if hc is not None and hc.hp is not None and hc.hp <= 0:
            continue                                       # `UnitSelectionType.OnlyAliveAndTargetable`
        if _unit_rarity(state, oid) != Rarity.Mythic:
            continue                                       # `ValidCharacter` = UnitsWithRarity(Mythic)
        if _bq_is_adjacent(up, (pc.col, pc.row), elev, neigh):
            out.add(int(oid))
    return frozenset(out)


def wisdom_of_the_ancients_target_ids(state: State, owner_id: int) -> "Optional[frozenset]":
    """`IdunBattle.Entities.Effects.Loki.WisdomOfTheAncients_DamageReductionEffect$$
    CreateTargetSelector` EVALUE pour le porteur `owner_id` -- foyer COMBAT (#1042-r1).

        A = ValidCharacter( AdjacentFriends(Owner@<+0x30>, unique = true, 3) )
        B = ValidCharacter( Friends(of = Owner@<+0x30>, entities = AllUnits@<+0x20>, 3) )
        F = Filter( B, AmountIsGreaterThanZero(
                           UnitsWithTrait( ValidCharacter( AdjacentFriends(<element courant>,
                                                                          unique = true, 3) ),
                                           UnitTrait.Hero = 0x10, 3 ) ) )
        return ConditionalSelector( IsMachine(Owner), ifTrue = F, ifFalse = Unique(A + F) )

    Le `ConditionalSelector` n'est PAS porte, et c'est une EQUIVALENCE : `IsMachine(Owner)` VRAI
    implique `EntityType.Machine`, donc AUCUN `PositionComponent` (c'est le discriminant meme de
    `MachineComponent`), donc `AdjacentTiles(Owner)` vide, donc `A = {}` et `Unique(A + F) == F`.
    Le detail et le garde executable vivent dans la docstring de
    `entities/effects/loki/damage_reduction.py::WisdomOfTheAncientsDamageReductionEffect`.

    ⚠ `Friends` ne retire PAS le sujet, donc `B` peut contenir le porteur lui-meme ; c'est FIDELE
    (`UnitExtensions$$IsFriend(u, u)` est VRAI) et sans effet observable ici -- l'agregateur
    `aura_defense_damage_malus_from_units` n'appelle jamais un porteur sur lui-meme.

    TRI-ETAT : `None` quand la question n'a PAS ETE POSEE (porteur absent ou sans equipe), jamais
    un `frozenset()` invente qui se lirait << mesure, et personne >>."""
    ent = state.get_entity(int(owner_id)) if owner_id is not None else None
    ooc = ent.get_component(OwnerComponent) if ent is not None else None
    if ooc is None or ooc.team is None:
        return None
    elev = elevations_by_pos(state.board)
    neigh = adjacent_neigh_by_pos(state.board)
    # A -- vide des que le porteur n'a pas de tuile (toute MACHINE OF WAR).
    out = set(_wisdom_valid_adjacent_friends(state, int(owner_id), elev, neigh))
    for uid, e in state.entities.items():
        if uid == owner_id:
            continue
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        if oc is None or pc is None or oc.team != ooc.team:
            continue                                       # B : `Friends(Owner, AllUnits(), 3)`
        hc = e.get_component(HealthComponent)
        if hc is not None and hc.hp is not None and hc.hp <= 0:
            continue                                       # `UnitSelectionType.OnlyAliveAndTargetable`
        if _unit_rarity(state, uid) != Rarity.Mythic:
            continue                                       # B : `ValidCharacter`
        if uid in out:
            continue                                       # deja pris par A (`Unique`)
        # F : `AmountIsGreaterThanZero( UnitsWithTrait(ValidCharacter(AdjacentFriends(uid)), Hero) )`
        for vid in _wisdom_valid_adjacent_friends(state, int(uid), elev, neigh):
            if UnitTrait.Hero.name in (target_trait_names(state, vid) or frozenset()):
                out.add(int(uid))
                break
    return frozenset(out)
def _cabal_valid_adjacent_to(state: State, unit_id: Optional[int], team) -> Optional[int]:
    """#1036-r2 -- `AmountIsGreaterThanZero( ValidCharacter( AdjacentFriends(<element courant
    @DSLSelectors+0x68>, unique = true, OnlyAliveAndTargetable) ) )`, le filtre `F` du
    `$$CreateTargetSelector` de `CabalOfSorcerers_ExtraDamagePctEffect` -- rendu comme un COMPTE
    (le natif ecrit `AmountIsGreaterThanZero`, pas un booleen). L'ELEMENT COURANT du filtre est le
    BENEFICIAIRE, c.-a-d. l'ATTAQUANT sur ce canal.

    `ValidCharacter(x) = UnitsWithTraits(UnitsWithRarity(x, Mythic), [Psyker, Hero])` :
    INTERSECTION des deux traits (`TargetsSelector$$op_BitwiseAnd`), rarete lue sur
    `BaseUnitComponent.Rarity` (+0x74, `_unit_rarity`).

    TRI-ETAT : `None` quand la question n'a PAS ETE POSEE (pas d'unite, pas de position, equipe
    inconnue) -- jamais `0`. Le lecteur FERME son gate sur `None`. MEME forme et MEME discipline
    que `_friend_heroes_adjacent_to` (#1019) ci-dessus ; la face PREDICTION a son jumeau
    (`playbook/prediction/_shared.py`), sur les memes criteres."""
    if unit_id is None or team is None:
        return None
    up = _unit_pos(state, unit_id)
    if not up:
        return None
    elev = elevations_by_pos(state.board)
    neigh = adjacent_neigh_by_pos(state.board)
    n = 0
    for uid, ent in state.entities.items():
        if uid == unit_id:
            continue                                       # AdjacentUnits exclut l'origine
        oc = ent.get_component(OwnerComponent)
        pc = ent.get_component(PositionComponent)
        if oc is None or pc is None or oc.team != team:
            continue                                       # AdjacentFriends -> meme equipe
        hc = ent.get_component(HealthComponent)
        if hc is not None and hc.hp is not None and hc.hp <= 0:
            continue                                       # OnlyAliveAndTargetable
        if _unit_rarity(state, uid) != Rarity.Mythic:
            continue                                       # UnitsWithRarity(..., Mythic = 5)
        traits = target_trait_names(state, uid) or frozenset()
        if UnitTrait.Psyker.name not in traits or UnitTrait.Hero.name not in traits:
            continue                                       # UnitsWithTraits([Psyker, Hero]) = ET
        if _bq_is_adjacent(up, (pc.col, pc.row), elev, neigh):
            n += 1
    return n


def _apply_ally_attack_damage_auras(state: State, att_id: int, mods, is_ranged: Optional[bool],
                                    target_armor_reduced: Optional[bool],
                                    damage_profile: Optional[str] = None,
                                    target_id: Optional[int] = None,
                                    target_traits=None,
                                    is_overwatch: bool = False) -> None:
    """AURA ALLIÉE +dégât FLAT projetée sur l'ATTAQUANT par les effets `create_aura_attack_damage_bonus_for_ally`
    de ses ALLIÉS à portée (canal AURA côté SOURCE : l'effet vit sur le porteur et se projette sur ses amis quand
    EUX attaquent). `ConquerorImperative` (#23) : +extraDmg aux amis Mechanical ring-1 vs cible à armure réduite ;
    `BeaconOfRage_FriendlyExtraDamage` (#191) : +50% rage aux amis Chaos adjacents en mêlée. Mirror COMBAT du même
    wiring que la PRÉDICTION (`aura_attack_damage_bonus_from_allies`, prediction.py) — le natif applique le
    DamageModifier à TOUTES les cibles-sélecteur dans les deux faces. Carriers = tous les autres VIVANTS de
    l'ÉQUIPE de l'attaquant avec effets actifs ; le gate (équipe/trait/adjacence/grande-alliance/is_melee/
    target_armor_reduced) vit dans le `create_aura_`. No-op sans carrier concerné."""
    if state.effects is None:
        return
    ae = state.get_entity(att_id)
    aoc = ae.get_component(OwnerComponent) if ae is not None else None
    apc = ae.get_component(PositionComponent) if ae is not None else None
    if aoc is None or apc is None:
        return
    carriers = []
    for uid, ent in state.entities.items():
        if uid == att_id:
            continue                                      # AdjacentFriends exclut le bénéficiaire lui-même
        oc = ent.get_component(OwnerComponent)
        pc = ent.get_component(PositionComponent)
        if oc is None or oc.team != aoc.team:
            continue                                      # Friends du porteur = même équipe que l'attaquant
        hc = ent.get_component(HealthComponent)
        if hc is not None and hc.hp is not None and hc.hp <= 0:
            continue                                      # porteur mort -> aura éteinte
        effs = state.effects.active_effects(uid, unit_state_for_effects(state, uid))
        if effs:
            # #999-r3-r1-r1 -- `owner_pos = None` pour un porteur SANS `PositionComponent`, et il
            # ENTRE quand meme. Le natif ne filtre RIEN par position :
            # `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction`
            # et son jumeau DEFENSE iterent une `List<KeyValuePair<entite, List<effet>>>` de
            # l'ETAT, BOARD-WIDE. Le `pc is None -> continue` d'avant etait un ARTEFACT du port, et
            # il ecartait STRUCTURELLEMENT toute MACHINE OF WAR (`snapshot._load_machines` ne pose
            # ni position ni sante : une MoW est hors-plateau, le natif n'en a pas non plus).
            # Il tenait a lui seul les SIX `PARTIEL` de `kit-coverage.md` (1442, 1443, 1445, 1449,
            # 1494, 1548). Les auras POSITIONNELLES ne changent pas de verdict pour autant : leurs
            # lecteurs ouvrent tous par `op, ap = c.get("owner_pos"), c.get("att_pos")` puis
            # `if not op or not ap: return None` (ou `_hex_distance(None, ...) is None`) -- elles
            # se TAISENT, comme sur n'importe quelle cle absente. Seules entrent les auras dont le
            # `$$CreateTargetSelector` ne lit AUCUNE position (`Friends(Owner, AllUnits, 3)`,
            # `UnitsWithRarity`, `UnitsOnTilesWithEffect`), c.-a-d. exactement celles que le natif
            # accorde a une MoW.
            carriers.append((uid, ((pc.col, pc.row) if pc is not None else None), oc.team, effs))
    # #919 -- `IconOfObstinacy_ExtraDmg` est la PREMIERE aura dont la magnitude lit une STAT DU
    # PORTEUR (`StatAmount(Owner@DSLSelectors+0x30, 0x8 = BlockDamage, 0x0 = Current)`), et non une
    # variable de config seule. Le ctx d'aura ne publiait que `owner_{id,pos,team}` : sans cette
    # cle, la patte `%` serait NON LISIBLE, donc omise (degradation nommee, cf. la classe d'effet).
    # MAP par porteur (l'agregateur re-cle par `owner_id`) et ADDITIVE : aucune classe existante ne
    # la lit, aucun comportement existant ne bouge.
    owner_block_damage = {uid: _unit_stat(state, uid, int(StatType.BLOCK_DAMAGE))
                          for (uid, _p, _t, _e) in carriers}
    # #926 -- `FirstAmongTraitors_ExtraDmg` est la PREMIERE aura dont la magnitude lit un COMPTEUR
    # DU PORTEUR (`TotalAttacksMade(EffectSource)` = `ActorStatisticsComponent+0x20` d'Abaddon), et
    # non une stat ni une variable de config seule. MEME forme que `owner_stat_block_damage`
    # ci-dessus : map PAR PORTEUR, l'agregateur re-cle par `owner_id`. Le lecteur est le foyer
    # unique `components.unit_total_attacks_made` (mirror `TotalAttacksMadeFormula$$Calculate`).
    owner_total_attacks = {uid: unit_total_attacks_made(state, uid)
                           for (uid, _p, _t, _e) in carriers}
    if not carriers:
        return
    is_melee = (not is_ranged) if is_ranged is not None else None
    att_gu = _unit_gameconfig(state, att_id) or {}
    # #1019 -- `AmountIsGreaterThanZero( UnitsWithTrait( Friends(Owner, AdjacentUnits(Target)),
    # 0x10 = Hero ) )`, le noeud DISCRIMINANT d'`IdunBattle.Entities.Effects.Loki.
    # WayOfTheShortBladeEffect$$IsValidAttackForBonus` (« against enemies that are adjacent to a
    # friendly Character »). Le ctx d'aura ne publiait AUCUN canal sur le voisinage de la CIBLE :
    # sans cette cle le gate serait FERME en permanence, donc l'effet inerte. Cle SCALAIRE (un
    # COMPTE, pas un booleen -- le natif ecrit `AmountIsGreaterThanZero`), ADDITIVE : aucune classe
    # existante ne la lit. `None` = NON MESURE (pas de cible / pas de position), jamais rendu 0.
    friend_heroes_adj = _friend_heroes_adjacent_to(state, target_id, aoc.team)
    ctx = {"att_id": att_id, "att_pos": (apc.col, apc.row), "att_team": aoc.team,
           "att_traits": target_trait_names(state, att_id),
           "att_grand_alliance": att_gu.get("GrandAllianceId"),
           # DefenderOfTheGreaterGood_ExtraDmg (#220, aura Tau) : tier T'au range-2 = UnitsFromFaction(9)
           # IdunBattleLogic.Entities.Abilities.Triggered.Loki.DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector -> att_faction (FactionId) ; gate !DamageProfileIs(Psychic) IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraDmgEffect$$CreateDamageModifier -> damage_profile.
           "att_faction": att_gu.get("FactionId"),
           "damage_profile": damage_profile,
           # UnitsWithRangedAttacks (selector SpotterReworked IdunBattle.Entities.Effects.Loki.SpotterReworked_ExtraDamageEffect$$CreateTargetSelector) = UNION {arme ranged au kit}
           # + {diff elevation <= 2 vs tuile porteur} (IdunBattleLogic.Entities.DSLFactory$$UnitsWithRangedAttacks) -> board pour le terme elevation
           "att_has_ranged_weapon": any(w.get("Range") for w in (att_gu.get("weapons") or ())),
           "board": state.board,
           # LionHelm_ExtraDmg (#passifs DA) : `IsOverwatchAttack` du gate d'aura — MEME flag que celui
           # deja threade jusqu'a `Hailstrike_ExtraPierce` (`AttackDamageOperation.execute(is_overwatch=)`).
           "is_overwatch": bool(is_overwatch),
           "is_melee": is_melee, "target_armor_reduced": target_armor_reduced,
           # CIBLE du coup — les auras dont le gate natif porte sur la CIBLE (`HasTrait(Target@0x178,
           # …)`) en ont besoin : `DestroyTheWitch_ExtraDamage` (aura melee vs **Psyker**,
           # IdunBattle.Entities.Effects.Loki.DestroyTheWitch_ExtraDamageEffect$$CreateEffectDamageBonusForAttack).
           # Symetrique du ctx de l'agregateur DEFENSE (`aura_defense_damage_malus_from_units`), qui
           # portait deja `tgt_traits`. None (appelant sans cible) -> ces gates rendent None.
           "tgt_id": target_id,
           "tgt_traits": target_traits,
           "t_pos": _unit_pos(state, target_id),
           "tgt_team": _unit_team(state, target_id),
           # #1019 -- cf. `_friend_heroes_adjacent_to` ci-dessus. TRI-ETAT (`None` = non mesure).
           "friend_heroes_adjacent_to_target": friend_heroes_adj,
           # #919 -- cf. la construction de la map ci-dessus. Cle par PORTEUR ; l'effet la resout
           # avec le `owner_id` que l'agregateur pose dans son ctx par-carrier.
           "owner_stat_block_damage": owner_block_damage,
           # #926 -- `TotalAttacksMade(EffectSource)` de `FirstAmongTraitors_ExtraDmgEffect`. MEME
           # cle et MEME semantique que la face PREDICTION (`_shared._apply_ally_attack_dmg_bonus`,
           # qui la remplit par `scene.total_attacks_made`) -- pas de fork.
           "owner_total_attacks_made": owner_total_attacks,
           # #1011 -- les TROIS canaux de `NornCrownEffect` (relique de `tyranNeurothrope`).
           # 1. `HasEffect(Target@DSLSelectors+0x60, 0x4c2 = 1218 Neuroparasite, onlyActive: false,
           #    6 = Both)` : les noms d'effets NON CONSOMMES de la CIBLE. `onlyActive: false` ->
           #    aucune lecture d'`IsActive`, donc `by_unit` et pas `active_effects` (le MEME
           #    substrat que `_neuroparasite_instance` du trigger de pose). Tri-etat : cible
           #    absente / pas de store d'effets -> `None`, et le gate se TAIT.
           _NORN_CTX_TGT_EFFECTS: _target_effect_names(state, target_id),
           # 2. `IsInTeamSynapseRange(It@+0x68, Owner@+0x30)` -> `IsInAuraRangeTrigger(0x41c)` ->
           #    `BattleQuery$$GetInRangeAuraAmount`, qui balaye les unites de l'EQUIPE portant le
           #    trait rendu par `SynapseEffect$$GetTrait` (`return 0x7e8` = 2024 `Synapse`) et
           #    compare `GetDistance(unit, target)` a la portee de l'aura. La map est par EQUIPE
           #    parce que le natif prend l'equipe COURANTE du selecteur `team`, pas le porteur.
           _NORN_CTX_SYNAPSE: _team_synapse_positions(state),
           # 3. `GetAbilityState(effect)` (#357) : le couple (niveau, multiplicateur) sous lequel
           #    l'ability est MONTEE sur le porteur -- TERTIAIRE pour une relique EQUIPEE. MEME cle
           #    et MEME foyer que le canal CRIT (`AttackDamageOperation._crit_board`), donc les deux
           #    canaux d'une meme relique ne peuvent pas diverger de niveau.
           _MYTHIC_CTX_ABILITY_STATE: _tertiary_ability_state_fn(state),
           # #1012-r1 -- `UnitsWithVisualId( ConfigConstString(<TriggeredAbilityConfigId 0x60d>, 0),
           # 1 = UnitSelectionType.OnlyAlive )`, le noeud DISCRIMINANT du `CreateTargetSelector`
           # d'`IdunBattle.Entities.Effects.Loki.HeadwoppasKillchoppaEffect` (les Ork Boyz de
           # Gulgortz). Le ctx d'aura ne publiait AUCUN canal d'IDENTITE de l'attaquant : sans cette
           # cle le gate serait ferme en permanence, donc la face AURA inerte. `None` = NON MESURE
           # (unite ou `visual_id` introuvable), jamais une chaine vide -- l'effet se tait alors.
           "att_visual_id": _unit_visual_id(state, att_id),
           # #999-r3-r1 -- RARETE de l'ATTAQUANT, `BaseUnitComponent.Rarity` (+0x74). Le
           # BENEFICIAIRE de ce canal est l'attaquant (`get_OwnerIsCaster` apres que la boucle
           # native a ecrit `AbilityEntities+0x18 (Owner) <- CHAQUE CIBLE du selecteur`), donc un
           # etage `UnitsWithRarity(...)` du `$$CreateTargetSelector` se lit ICI, sur `att_id`.
           # Consommateur : `BlightedLandEffect` (1442), dont le selecteur est
           # `UnitsOnTilesWithEffect(UnitsWithRarity(Friends(Owner, AllUnits, 3), Mythic, 3),
           # Contaminated)`. MEME cle et MEME semantique que la face PREDICTION
           # (`playbook/prediction/_shared.py::_apply_ally_attack_dmg_bonus`) -- pas de fork.
           # TRI-ETAT (`None` = non mesure -> le gate se FERME), cf. `_unit_rarity`.
           "att_rarity": _unit_rarity(state, att_id),
           # #1036-r1 -- `EntitiesWithAnyEffect(<les allies du porteur>, effectTypes =
           # [NanoscarabRepairProtocols], effectTarget = Both = 6)` de
           # `GuardianConstruct_ExtraDamagePctEffect$$CreateTargetSelector`. Le 4e argument du
           # call-site d'`EntityExtensions$$HasOneOfEffects` est ZERO (`onlyActive = false`), donc
           # le substrat est le store BRUT `by_unit` filtre sur le seul `consumed` -- MEME foyer et
           # MEME semantique que le `tgt_effect_names` de `NornCrownEffect` (#1011), interroge ici
           # sur l'ATTAQUANT (le BENEFICIAIRE de ce canal). TRI-ETAT : `None` = NON MESURE.
           _GUARDIAN_CTX_ATT_EFFECTS: _target_effect_names(state, att_id),
           # #1036-r2 -- `IsMachine(Owner)` du `ConditionalSelector` de
           # `CabalOfSorcerers_ExtraDamagePctEffect` : `IsMachineTrigger$$ShouldTrigger` ->
           # `EntityExtensions$$IsMachine`, dont le corps entier est `<EntityType> == 6`
           # (`$$IsUnit` compare a 1, `$$IsMachinePlatform` a 7). Cote port, la PRESENCE d'un
           # `MachineComponent` (`components.is_machine_of_war`). MAP par PORTEUR, comme
           # `owner_stat_block_damage` : l'agregateur re-cle par l'`owner_id` de son ctx par-carrier.
           _CABAL_CTX_OWNER_IS_MACHINE: {uid: is_machine_of_war(state.get_entity(uid))
                                         for (uid, _p, _t, _e) in carriers},
           # #1036-r2 -- cf. `_cabal_valid_adjacent_to` ci-dessus (le filtre `F`). TRI-ETAT.
           _CABAL_CTX_VALID_ADJACENT: _cabal_valid_adjacent_to(state, att_id, aoc.team)}
    # `PsychicStalk_FriendlyChaosExtraDamage` (#366-r1, effet 1435) -- PATTE AURA : son conjoint
    # `GetTargetIsOnFireTileCondition` lit `EntitiesWithAnyEffect(Tiles(Target@0x60), Fire)`, donc
    # les effets de la MAIN TILE de la cible. MEME canal / MEME forme `{(col,row): [noms]}` que
    # celui deja monte pour l'agregateur DEFENSE (`defender_modifiers`) et pour
    # `LetTheGalaxyBurnEffect`. Cible absente -> cle absente -> le gate se tait.
    # #999-r3-r1 -- la MAIN TILE de l'ATTAQUANT entre dans la MEME cle. `BlightedLandEffect` (1442)
    # ferme son selecteur par `UnitsOnTilesWithEffect(<les allies Mythiques>, Contaminated)` : le
    # noeud lit la tuile de l'element courant du selecteur, c.-a-d. du BENEFICIAIRE, qui sur ce canal
    # est l'ATTAQUANT -- pas la cible. Les deux entrees COEXISTENT (positions distinctes par
    # construction : l'attaquant n'occupe pas la tuile de sa cible), donc aucun lecteur existant ne
    # change de verdict -- ils indexent tous par une position explicite (`t_pos`). La face PREDICTION
    # n'a rien a ajouter : `scene.tile_effects_by_pos` porte DEJA tout le plateau.
    _aura_tiles = [p for p in (ctx["t_pos"], ctx["att_pos"]) if p is not None]
    if _aura_tiles:
        ctx["tile_effects_by_pos"] = tile_status_effects_by_pos(state, _aura_tiles)
    for eb in aura_attack_damage_bonus_from_allies(carriers, ctx):
        add_modifier(mods, eb)


def _target_effect_names(state: State, target_id: Optional[int]):
    """Noms des effets NON CONSOMMES portes par la CIBLE du coup -- substrat de
    `IdunBattleLogic.Entities.DSLTriggers$$HasEffect(entity, effectType, onlyActive, targetType)`
    quand `onlyActive = false` (#1011, `NornCrownEffect`).

    `onlyActive: false` -> aucune lecture d'`IsActive`, donc le store BRUT `by_unit` filtre sur le
    seul `consumed`, PAS `active_effects` : c'est exactement le substrat que lit deja
    `runner/operations/triggers/loki/neuroparasite.py::_neuroparasite_instance`, dont le gate natif
    porte le meme `onlyActive: 0`.

    ⚠ La cle `tgt_effect_names` est HOMONYME de celle du ctx d'`additional_hits` / de la face
    PREDICTION, qui la batissent depuis les effets ACTIFS : le nom est le meme, la SEMANTIQUE est
    plus large ici, et c'est ce que demande le litteral natif. Les deux dicts sont disjoints.

    ⚠ Le parametre est un id d'ENTITE quelconque, pas seulement la cible du coup : #1036-r1
    l'interroge sur l'ATTAQUANT (cle `att_effect_names`), pour le meme noeud natif a `onlyActive:
    false` (`EntitiesWithAnyEffect(..., effectTarget = Both)` du selecteur de
    `GuardianConstruct_ExtraDamagePctEffect`). Le nom du parametre garde l'appelant d'origine.

    TRI-ETAT : `None` = NON MESURE (pas de cible, ou pas de store d'effets) -> le gate se TAIT."""
    eff = getattr(state, "effects", None)
    if eff is None or target_id is None:
        return None
    return frozenset(n for n in (getattr(e, "name", None)
                                 for e in (eff.by_unit.get(int(target_id)) or [])
                                 if not getattr(e, "consumed", False)) if n)


def _team_synapse_positions(state: State):
    """`{team: ((col, row), ...)}` des unites VIVANTES portant le trait `Synapse` -- substrat de
    `IdunBattleLogic.Entities.DSLTriggers$$IsInTeamSynapseRange(target, team)` (#1011).

    Le natif descend `IsInAuraRangeTrigger(state, query, 0x41c = 1052 Synapse_Effect, target, team)`
    -> `IBattleQuery` slot 148 `IsInTeamAuraRange` -> `BattleQuery$$GetInRangeAuraAmount`, qui :
      * resout l'implementation d'EFFET de `0x41c` (`IdunBattle.Entities.Effects.Loki.SynapseEffect`)
        et lit son `$$GetTrait`, dont le corps ENTIER est `return 0x7e8` (= 2024 `UnitTrait.Synapse`)
        -- c'est bien le TRAIT qui est teste (`UnitExtensions$$HasTrait`), pas la presence de l'effet ;
      * ne retient que les unites dont `EntityExtensions$$GetCurrentTeamId` vaut l'equipe demandee ;
      * compare `BattleQuery$$GetDistance(unit, target)` a la portee de l'aura
        (`SynapseEffect$$GetNextTurnRange` = `Direct(2)`).
    La comparaison de distance reste chez le consommateur (`norn_crown._in_team_synapse_range`) :
    seule la POSITION des emetteurs depend de l'etat.

    Traits lus sur le substrat d'ENTITE (`target_trait_names`, #264), pas sur le kit gameconfig."""
    out: dict = {}
    for uid, ent in state.entities.items():
        oc = ent.get_component(OwnerComponent)
        pc = ent.get_component(PositionComponent)
        if oc is None or pc is None:
            continue
        hc = ent.get_component(HealthComponent)
        if hc is not None and hc.hp is not None and hc.hp <= 0:
            continue
        if UnitTrait.Synapse.name not in target_trait_names(state, int(uid)):
            continue
        out.setdefault(oc.team, []).append((pc.col, pc.row))
    return {t: tuple(ps) for t, ps in out.items()}


def _tertiary_ability_state_fn(state: State):
    """`(owner_id, ability_name) -> (level, multiplier)` -- mirror de
    `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState`, delegue au foyer UNIQUE
    `runner/operations/triggers/base.py::triggered_ability_state` (#357). MEME cle et MEME
    semantique que le canal CRIT (`AttackDamageOperation._crit_board`), qui l'expose deja.

    Import DIFFERE et PORTEUR (classe MESUREE : charger `engine.runner.operations.triggers.base`
    seul dans un process frais fait atterrir `engine.runner.damage_model` dans `sys.modules`, donc
    hisser fermerait un cycle). MEME forme que les trois sites existants
    (`operations/damage.py`, `operations/repair.py`, `abilities/base.py`)."""
    from .operations.triggers.base import triggered_ability_state
    return lambda oid, ability: triggered_ability_state(state, int(oid), ability)


def _unit_pos(state: State, unit_id: Optional[int]):
    """`(col,row)` de l'unité, ou None (unité absente / sans position — ex. MoW hors-plateau)."""
    if unit_id is None:
        return None
    e = state.get_entity(int(unit_id))
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _adjacent_unit_profiles(state: State, unit_id: Optional[int]):
    """#1025-r1 -- `AdjacentUnits( <unit_id>, unique: true, OnlyAliveAndTargetable = 3 )`, enrichi
    de `(team, visual_id, rarity, is_hero)` par voisin : le substrat des branches des
    `$$CreateTargetSelector` de `IdunBattle.Entities.Effects.Loki.MoreGitzOverEre_ExtraDamagePctEffect`
    et `IdunBattle.Entities.Effects.Loki.OnMyPosition_ExtraDamagePctEffect` (#1024-r2).

    Rend un tuple de `(uid, team, visual_id, rarity, is_hero)`. Les QUATRE champs sont ceux que les
    etages natifs comparent, et aucun n'est derivable des autres :
      * `team`       -> `Friends( Owner@+0x30, ..., 3 )`, commun a toutes les branches. Le filtre est
                        relatif au PORTEUR de l'effet, connu du seul agregateur d'aura -> il est
                        rejoue dans la classe d'effet, pas ici ;
      * `visual_id`  -> `UnitsWithVisualId( VisualUnitIdFromUnitId(<constants.unitId>), 1 )`
                        (branche A des deux effets : le Squig pour 1449, le Cadian Guardsman
                        pour 1444) ;
      * `rarity`     -> `UnitsWithRarity( ..., 5 = idun.meta.Rarity.Mythic, 3 )` (branche B) ;
      * `is_hero`    -> `HeroUnits( <univers>, 3 )`, que
                        `IdunBattleLogic.Entities.DSLSelectors$$HeroUnits` rend LITTERALEMENT par
                        `UnitsWithTrait(entities, 0x10 = UnitTrait.Hero, selectionType)` -- present
                        dans la branche B de 1444 SEULEMENT, absent de celle de 1449. MEME lecture
                        de trait que `_friend_heroes_adjacent_to` ci-dessus (#1019), meme foyer
                        `target_trait_names`.

    L'ADJACENCE elle-meme vient du pont `components.adjacent_unit_ids`, qui donne son
    `AbilityEntities` a l'arbre DSL de la classe d'effet (doctrine #149) -- donc la LISTE STOCKEE
    avec la porte d'elevation, pas un `hexgeo.distance == 1`.

    `None` = NON MESURE (pas d'unite, pas d'equipe, pas de position, pas de plateau) -> le gate se
    FERME cote effet. Un tuple VIDE, lui, est une MESURE : << aucun voisin >>."""
    if unit_id is None:
        return None
    from .components import adjacent_unit_ids
    ids = adjacent_unit_ids(state, int(unit_id))
    if ids is None:
        return None
    return tuple((int(i), _unit_team(state, i), _unit_visual_id(state, i), _unit_rarity(state, i),
                  UnitTrait.Hero.name in (target_trait_names(state, int(i)) or frozenset()))
                 for i in sorted(ids))


def _unit_hp_and_max(state: State, unit_id: Optional[int]):
    """`(hp, hp_max)` de l'unite, ou `(None, None)`. Substrat du noeud `HealthPctIsBelowOrEqual`
    (`IdunBattle.Entities.Conditions.StatPercentageIsBelowOrEqualAbilityTrigger$$ShouldTrigger` :
    `GetStat(5 = HEALTH, Current) / GetStat(5, Maximum)`), threade dans `att_ctx` sous `tgt_hp` /
    `tgt_hp_max` pour les bonus dont la MAGNITUDE depend des PV de la CIBLE du coup --
    `LightOfSanguinius` (1376) DOUBLE sa reduction sous `healthPct` (#510).
    Le PV COURANT vit dans `HealthComponent` (mute par les degats) : `get_stat(Health, Current)`
    rendrait le PV du snapshot, cf. `bloodangels._regenerate_precondition`."""
    if unit_id is None:
        return (None, None)
    e = state.get_entity(int(unit_id))
    hc = e.get_component(HealthComponent) if e is not None else None
    return (hc.hp, hc.hp_max) if hc is not None else (None, None)


def _unit_team(state: State, unit_id: Optional[int]):
    """Équipe de l'unité, ou None."""
    if unit_id is None:
        return None
    e = state.get_entity(int(unit_id))
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _unit_rarity(state: State, unit_id: Optional[int]):
    """#999-r3-r1 -- `BaseUnitComponent.Rarity` (+0x74) de l'unite, foyer de lecture COMBAT.

    C'est LE champ que lisent, apres `IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent`,
    les trois gates natifs de rarete : `IdunBattle.Entities.Triggers.HasRarityTrigger$$ShouldTrigger`,
    `IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select` et
    `IdunBattle.Entities.UnitExtensions$$HasRarity`. Meme forme et meme place qu'`_unit_team` /
    `_unit_pos` ci-dessus, et MEME substrat que la cle `rarity` du dict d'unite DSL
    (`runner/abilities/behaviours/context._unit_dict`) : les deux voies lisent `StatsComponent.ctx
    .rarity`, seedee par le foyer unique `UnitContext.from_snapshot` (#999-r3, capteur #1039).

    TRI-ETAT STRICT : `None` = NON MESURE (entite absente, pas de `StatsComponent` -- un CADAVRE --,
    ou capteur muet). JAMAIS `Rarity.Common` en repli : `0` est une rarete parfaitement plausible, et
    un repli ferait basculer tous les gates de rarete en PERMISSIF sans que personne ne le voie.
    Le lecteur FERME son gate sur `None` (degradation RESTRICTIVE nommee, cf. `entities/rarity.py`)."""
    if unit_id is None:
        return None
    e = state.get_entity(int(unit_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    return getattr(getattr(sc, "ctx", None), "rarity", None)


def _unit_stat(state: State, unit_id: Optional[int], stat_type: int) -> Optional[int]:
    """`IdunBattle.Entities.UnitExtensions$$GetStat(unit, statType, Current, null)` -- lecture de la
    stat COURANTE (effet-inclusif) via le `UnitContext` du porteur. `None` = pas de contexte de
    stats : le lecteur DIT qu'il n'a pas mesure au lieu de rendre 0 (un 0 rabattu ferait disparaitre
    silencieusement un terme `%`). #919."""
    if unit_id is None:
        return None
    e = state.get_entity(int(unit_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None) if sc is not None else None
    if ctx is None:
        return None
    return int(ctx.get_stat(int(stat_type), 0) or 0)      # `StatPart.Current`


def _owner_turn_flag(state: State, unit_id: Optional[int]) -> Optional[bool]:
    """`IdunBattle.Entities.Triggers.IsTurnOfUnitTrigger$$ShouldTrigger` pour un selecteur SINGLETON :
    `OwnerComponent.CurrentPlayerEntityId(unit) == TurnComponent.CurrentPlayerId(state)`.

    Face COMBAT du canal `att_ctx["is_turn_of_owner"]` (cf. `entities/effects/base.py::
    is_turn_of_owner`) ; la face DECISION lit le MEME predicat par `decisionView.units[].ctrl`
    (`IsControlledByCurrentPlayer`, invoque natif). `None` si l'une des deux lectures manque --
    non mesure, jamais un booleen devine."""
    if unit_id is None:
        return None
    cur = getattr(state, "current_player_id", None)
    if cur is None:
        return None
    e = state.get_entity(int(unit_id))
    oc = e.get_component(OwnerComponent) if e is not None else None
    if oc is None or oc.player is None:
        return None
    return int(oc.player) == int(cur)


def _positional_att_ctx(state: State, unit_id: int) -> Optional[dict]:
    """Contexte POSITIONNEL `{att_pos, tile_effects_by_pos}` pour les bonus attaquant à magnitude
    position-dépendante (#35 — LordOfTempests `IdunBattle.Entities.Effects.Loki.LordOfTempests_ExtraDamageEffect$$GetHexesIncreasingDamage` : Count(Ice
    ring-1 de la position d'attaque)). Côté COMBAT runner la position d'attaque = la position
    COURANTE de l'attaquant (il a déjà bougé avant de taper). `tile_effects_by_pos` = centre +
    ring-1 : noms d'effets DYNAMIQUES posés sur la tuile (`state.effects.by_unit[tile_id]`, même
    lecture que le PickTile MV71) + covers hébergés par le terrain. None si board/position absents
    → les bonus positionnels rendent None (comportement historique, fidèle : pas de count devinable)."""
    board = getattr(state, "board", None)
    if board is None:
        return None
    e = state.get_entity(unit_id)
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is None:
        return None
    pos = (pc.col, pc.row)
    ctid = board.id_at(pos[0], pos[1])
    if ctid is None:
        return None
    tfx: dict = {}
    for tid in (ctid, *board.neighbours(ctid)):
        p = board.coord(tid)
        if p is None:
            continue
        names: list = []
        if state.effects is not None:                            # effets dynamiques posés SUR la tuile (Ice/Fire…)
            names += [x.name for x in state.effects.by_unit.get(int(tid), [])
                      if not x.consumed and x.name]
        names += terrain_tile_effects(board.terrain_at(p[0], p[1]), names)   # #155 : `names` = canal dyn.
        tfx[tuple(p)] = names
    return {"att_pos": pos, "tile_effects_by_pos": tfx}


def tile_status_effects_by_pos(state: State, positions) -> Optional[dict]:
    """`{(col,row): [noms]}` des **status-effects DYNAMIQUES portes par la TUILE** aux positions
    demandees — mirror runner de la lecture native `IdunBattleLogic.Entities.DSLFactory$$HasTileStatusEffect` (la tuile est une
    ENTITE qui porte ses effets : `state.effects.by_unit[tile_entity_id]`, ids de tuile disjoints des
    ids d'unite, cf. `TileEffectTrigger`). Alimente le contexte CIBLE de la formule de coups
    (`IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`, gate `TargetHasTileEffect`).

    ⚠ N'inclut PAS `terrain_tile_effects` (les covers HEBERGES par le terrain, DryBush -> LightCover) :
    ceux-la sont poses sur les UNITES qui se tiennent sur la tuile (`LightCoverAbility
    .IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility$$UnitsThatNeedEffect`), pas sur la tuile — et le canal PREDICTION equivalent
    (`scene.tile_effects_by_pos` = `tileMeta.effects`) ne les liste pas non plus. Les DEUX facades
    lisent donc la MEME chose. Board/effets absents -> None (contexte inconnu, le gate no-op).

    ⚠ FILTRE `is_tile_status_effect` (#102) : une tuile porte des effets qui ne sont PAS des STATUS
    (mesure live C1_02 : `BlockEnteringUnits`/`Thorns_DefenseReduction` sur les Swamp,
    `Melta_ExtraDmg`). Le natif ne les compte pas — `IdunBattle.Entities.TileExtensions$$HasTileStatusEffect`
    ne retient que les EffectType du set `StaticBattleRules.Effect$$IsTileStatusEffect`. Tant que
    `load_state` ne seedait pas les effets de tuile, la liste offline ne contenait que ce que le
    runner avait pose lui-meme (Fire/Ice, tous des status) et l'absence de filtre etait INVISIBLE ;
    depuis le seed (#102) elle porte la VRAIE liste native, donc le filtre devient OBLIGATOIRE."""
    board = getattr(state, "board", None)
    if board is None or state.effects is None:
        return None
    out: dict = {}
    for p in positions:
        if p is None:
            continue
        tid = board.id_at(p[0], p[1])
        if tid is None:
            continue
        out[tuple(p)] = [x.name for x in state.effects.by_unit.get(int(tid), [])
                         if not x.consumed and x.name and is_tile_status_effect(x.effect_type)]
    return out


def battle_query_is_charging(state: State, caster_id: int, target_id: int) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$IsCharging(caster, target)` cote COMBAT — pont ECS vers
    le foyer `engine.battle_query.is_charging` (le predicat lui-meme y vit, cf. sa docstring).

    Ne fait QUE lire l'ECS et deleguer : positions (`PositionComponent`) + la liste
    `UnitComponent.ChargedUnitIds@+0x190` via `components.charged_unit_ids`. Aucune re-implementation
    du predicat ici — la face PREDICTION appelle le MEME foyer avec la liste qu'un pas CANDIDAT
    produirait (`battle_query.newly_adjacent_ids`).

    ⚠ #433-r4-r1-r4-r2-r1 : ce pont ne passait NI l'elevation NI le voisinage, alors que le terme
    `AreEntitiesAdjacent` du natif porte les deux --
    `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(t1, t2)` vaut
    `(|dElev| < 2) & (t1 == t2 || ConnectivityComponent(t1).IsNeighbour(t2))`, et
    `IdunBattle.Entities.Components.ConnectivityComponent$$IsNeighbour` lit la liste STOCKEE
    (`this[+0x10].Contains(id)`). Les deux canaux se DERIVENT du board (tri-etat), jamais ne se
    posent au call-site : `state.board` absent -> repli geometrique nomme d'`is_adjacent`, le
    comportement d'avant. La face PREDICTION (`_shared._prediction_is_charging`) derive les MEMES
    canaux de sa `Scene` -- une seule des deux branchee ferait diverger un natif unique."""

    def _pos(uid):
        e = state.get_entity(uid)
        pc = e.get_component(PositionComponent) if e is not None else None
        return (pc.col, pc.row) if pc is not None else None

    board = getattr(state, "board", None)
    return _bq_is_charging(_pos(caster_id), _pos(target_id), target_id,
                           charged_unit_ids(state, int(caster_id)),
                           elevations_by_pos(board), adjacent_neigh_by_pos(board))


def attacker_modifiers(state: State, unit_id: int, hp: Optional[int], is_ranged: Optional[bool] = None,
                       target_traits=None, target_id: Optional[int] = None,
                       is_normal_attack: bool = True, damage_profile: Optional[str] = None,
                       trigger_ability_type: Optional[int] = None,
                       is_overwatch: bool = False,
                       ability_type: Optional[int] = None):
    """`DamageModifiers` de l'attaquant depuis ses EFFETS actifs (None-safe). `is_ranged` = nature du coup
    (propagée aux bonus gated `IsRangedAttack`, ex. HeavyWeapon_ExtraDmg). `has_moved` (#60/#101) = l'unité
    a-t-elle BOUGE ce tour — LU SUR LE FLAG NATIF `UnitFlag.Moved` du `UnitFlagsComponent` (`unit_has_moved`,
    posé par `set_moved_flag` dans `MoveUnitOperation`) -> gate no-move : HeavyWeapon_ExtraDmg s'ANNULE si
    l'unité a bougé (verdict RE cluster #60 : le combat lisait has_moved=None -> bonus TOUJOURS appliqué,
    FAUX ; #101 : le set PARALLÈLE `state.moved_this_turn` n'était jamais alimenté sur un état rechargé par
    `load_state` ni lisible par les autres lecteurs du flag -> +25% fantôme, mesuré ×1.25 exact sur 2 seeds
    HarvesterOfSouls). `target_id`
    (incr. C) = la CIBLE du coup -> calcule le gate `HasNegativeModifier(cible armure)` (`defender_armor_reduced`)
    pour la contribution +extraDmg de ConquerorImperative ; None (chemin sans cible) -> gate None (inerte).
    `is_normal_attack` (#217) = nature du VECTEUR côté ATTAQUANT (symétrique du #112 défenseur) : False =
    attaque d'ABILITY (`execute_ability_attack`) -> gate les bonus attaquant normal-only (LordOfTempests
    snowball : MESURÉ live probe_217 B — cast Stormcaller avec effet actif + 3 hexes glacés ring-1 ->
    natif +0, offline-sans-gate +extraDmg x 3 x 3 hits ; le natif NE l'applique PAS aux attaques d'ability).
    Défaut True = attaque normale / normal-like (le smite Psyker porte le KIND 1013 = attaque-normale).
    `trigger_ability_type` (#47) = l'ABILITY DÉCLENCHANTE du coup (AbilityOrEffect numérique, mirror du
    champ du contexte d'attaque natif lu par `IdunBattleLogic.Entities.DSLFactory$$TriggeringAbilityIs`) — threadé dans `att_ctx`
    pour les amounts conditionnels par-ability (HeavyWeapon_ExtraDmg IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier : `ConditionalAmount(
    TriggeringAbilityIs(0x3ec=1004) ? base x2 : base)`). None (attaque normale/caller historique) =
    clé absente -> branche base.
    Les AURAS ALLIÉES +dégât (incr. C2 : `create_aura_attack_damage_bonus_for_ally` des alliés à portée,
    Conqueror/BeaconOfRage) sont ajoutées ici (`_apply_ally_attack_damage_auras`) — mirror combat de la prédiction."""
    active = (state.effects.active_effects(unit_id, unit_state_for_effects(state, unit_id))
              if state.effects is not None else [])
    has_moved = unit_has_moved(state, unit_id)
    tar = defender_armor_reduced(state, target_id) if target_id is not None else None
    # #35 : att_ctx POSITIONNEL (att_pos + effets de tuile ring-1 lus de l'ECS) — nourrit les bonus
    # position-dépendants (LordOfTempests : +extraDmg x Count(Ice ring-1)) côté COMBAT, symétrique de
    # la prédiction (qui le lit du tileMeta frais). Seul consommateur d'att_ctx à ce jour ; les unités
    # sans effet positionnel sont inchangées (les autres bonus ignorent att_ctx).
    att_ctx = _positional_att_ctx(state, unit_id)
    # `TilesMovedThisTurn(Self)` (case-322-r1) — `IdunBattle.Entities.Formulas.
    # TilesMovedThisTurnFormula$$Calculate` = `ActorStatisticsComponent+0xf0`, alimente par
    # `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved` que `MoveUnitOperation` appelle a
    # chaque pas JOUE (`components.record_tiles_moved`) et remis a zero par `EndTurnOperation`.
    # Consommateur porte : `ModifiedExoarmour_ExtraDmgEffect` (magnitude `V x n`, Kimm).
    # THREADE INCONDITIONNELLEMENT : cote COMBAT la valeur est MESUREE, donc la cle est toujours
    # posee -- le tri-etat `None = non threade` de `effects.base.tiles_moved_this_turn` ne concerne
    # plus que les appelants HORS runner. Une unite sans `UnitComponent` rend 0, comme un composant
    # natif frais. ⚠ Le contexte est PER-COUP : il porte la position ET le compteur, exactement
    # comme l'`AbilityEntities` natif que `BaseEffect$$DamageBonusForAttack` recoit.
    att_ctx = dict(att_ctx or {})
    att_ctx["tiles_moved_this_turn"] = unit_tiles_moved_this_turn(state, unit_id)
    # #911 : `GetNumAdjacentTauntedEnemies()` de la base native `ADaemonicPatronsEffect`. MEME
    # regime que `tiles_moved_this_turn` ci-dessus -- sur ce canal l'OWNER de chaque effet parcouru
    # EST l'attaquant (l'agregateur n'itere que ses effets), donc la cle porte bien le compte DU
    # PORTEUR, ce qu'exige le gate `get_OwnerIsCaster` de `DaemonicPatrons_ExtraDamage` (1464).
    # Foyer unique `components.adjacent_taunted_enemies_count` ; tri-etat conserve (`None` = le
    # porteur n'a ni equipe ni tuile), jamais un 0 invente.
    att_ctx["adjacent_taunted_enemies"] = adjacent_taunted_enemies_count(state, unit_id)
    # #932 : `UnitsFromFaction(AdjacentFriends(Owner@+0x30, 1, 3), DarkAngels, 3)` -- le SECOND
    # disjoint de `IdunBattle.Entities.Effects.Loki.DeathwingEffect$$GetDoubleEffectCondition`.
    # MEME regime que `adjacent_taunted_enemies` ci-dessus : sur ce canal l'OWNER de chaque effet
    # parcouru EST l'attaquant (l'agregateur n'itere que SES effets), ce qu'exige le
    # `get_OwnerIsActor` du trigger de `CreateEffectDamageBonusForAttack`. Foyer unique
    # `components.adjacent_dark_angels_friends_count` ; tri-etat conserve (`None` = le porteur n'a
    # ni equipe ni tuile), jamais un 0 invente -- il fermerait le disjoint en silence.
    att_ctx["adjacent_dark_angels_friends"] = adjacent_dark_angels_friends_count(state, unit_id)
    # #948 : les DEUX compteurs de `EnmityForTheUnworthy` (`darkaCompanion` << Forcas >>) --
    # `AdjacentUnitsAmount` (TOUTES les unites adjacentes, amies ET ennemies) et
    # `AdjacentFriendlyDarkaUnitsAmount` (les amis DARK ANGELS), tous deux passes par
    # `NonSteppableOrObjectUnits`. MEME regime que les trois cles ci-dessus : sur ce canal l'OWNER de
    # chaque effet parcouru EST l'attaquant (l'agregateur n'itere que SES effets), ce qu'exige le
    # `get_OwnerIsCaster` des deux `CreateEffectDamageBonusForAttack`. Foyers uniques
    # `components.enmity_adjacent_units_count` / `..._dark_angels_friends_count` ; tri-etat conserve
    # (`None` = le porteur n'a ni equipe ni tuile), jamais un 0 invente -- il eteindrait le bonus en
    # silence. ⚠ DISTINCTS d'`adjacent_dark_angels_friends` juste au-dessus (#932) : l'arbre
    # d'Enmity porte en plus l'etage `NonSteppableOrObjectUnits`.
    att_ctx[_ENMITY_CTX_UNITS] = enmity_adjacent_units_count(state, unit_id)
    att_ctx[_ENMITY_CTX_DA] = enmity_adjacent_dark_angels_friends_count(state, unit_id)
    # #1015-r1 : `HasAdjacentEnemies(Caster@+0x48, CasterTile@+0x50, includeObjects: false,
    # includeSteppables: false)` -- le terme GEOMETRIQUE de
    # `CloseCombatWeakness_ReduceDmg_Effect$$NearbyEnemiesCondition`. MEME regime que les quatre
    # cles ci-dessus : sur ce canal l'OWNER de chaque effet parcouru EST l'attaquant, et le
    # `Caster@+0x48` du noeud designe cette meme unite. Foyer unique
    # `components.close_combat_weakness_adjacent_enemies_count` ; tri-etat conserve (`None` = le
    # porteur n'a ni equipe ni tuile), jamais un 0 invente -- il eteindrait le malus en silence.
    att_ctx[_CCW_CTX_ADJACENT_ENEMIES] = close_combat_weakness_adjacent_enemies_count(state, unit_id)
    # #932 : `AreEnemies(Target@+0x60, Owner@+0x30, 0)` a besoin des DEUX equipes. `tgt_team` est
    # deja posee plus bas (branche `target_id`), il manquait celle du PORTEUR -- qui, sur ce canal,
    # EST l'attaquant. MEME cle et MEME semantique que le ctx du canal AURA
    # (`_apply_ally_attack_damage_auras`) et que le `_crit_board`, pas de vocabulaire neuf.
    att_ctx["att_team"] = _unit_team(state, unit_id)
    # #509 : `TotalTurnsWithAttacksMade(Owner)` — `IdunBattle.Entities.Formulas.
    # TotalTurnsWithAttacksMadeFormula$$Calculate` = `ActorStatisticsComponent+0x30`. MEME regime que
    # `tiles_moved_this_turn` juste au-dessus : la valeur est MESUREE cote COMBAT, donc la cle est
    # TOUJOURS posee (une unite sans `UnitComponent` rend 0, comme un composant natif frais). Sur ce
    # canal l'OWNER de chaque effet parcouru EST l'attaquant (l'agregateur n'itere que ses effets) —
    # c'est la meme equivalence que celle qui rend `get_OwnerIsCaster` implicitement vrai ici.
    # Consommateur porte : `MartialInspiration_ExtraDamageEffect` (magnitude `extraDmgPct x n`).
    att_ctx["turns_with_attacks_made"] = unit_turns_with_attacks_made(state, unit_id)
    # #919 : `StatAmount(Owner@DSLSelectors+0x30, 0x8 = BlockDamage, 0x0 = Current)` de
    # `IconOfObstinacy_ExtraDamageEffect$$GetCurrentExtraDamage`. MEME convention que les trois cles
    # ci-dessus : sur CE canal l'OWNER de chaque effet parcouru EST l'attaquant (l'agregateur
    # n'itere que SES effets), donc la valeur du porteur est celle de `unit_id`. Tri-etat conserve
    # (`None` = pas de contexte de stats), jamais un 0 rabattu -- un 0 ferait disparaitre le terme
    # `%` en silence au lieu de le declarer non mesure.
    att_ctx["owner_block_damage"] = _unit_stat(state, unit_id, int(StatType.BLOCK_DAMAGE))
    # #953 : `StatAmount(Owner@DSLSelectors+0x30, StatType.Health = 5, {Missing = 4, Maximum = 2})`
    # de `IdunBattle.Entities.Effects.Loki.Skullsmasher_ExtraDamageEffect$$GetMissingHealthSteps`.
    # MEME convention que les cinq cles ci-dessus : sur CE canal l'OWNER de chaque effet parcouru
    # EST l'attaquant (l'agregateur n'itere que SES effets), donc le couple porte bien les PV DU
    # PORTEUR. Substrat = `HealthComponent` (le MEME foyer `_unit_hp_and_max` que `tgt_hp` /
    # `HealthPctIsBelowOrEqual` et que `unit_health_of` du canal CRIT) : `GetStat(Health, Current)`
    # rendrait le PV du SNAPSHOT, pas celui qui vient d'etre entame. Tri-etat `(None, None)`
    # conserve -- un 0 rabattu ferait passer un porteur a PV pleins pour un porteur exsangue.
    att_ctx[_SKULLSMASHER_CTX_HEALTH] = _unit_hp_and_max(state, unit_id)
    # #509 : `CurrentAbilityIs(<AbilityOrEffect>)` — l'ability COURANTE du coup
    # (`AbilityEntities+0x60`, lu par `AbilityTypeSelector.CurrentAbilitySelector$$Select`), a NE PAS
    # confondre avec `trigger_ability_type` ci-dessous, qui mirror `TriggeringAbilityIs`
    # (`AbilityEntities+0x98`) : ce sont DEUX champs natifs distincts, ecrits a des moments
    # differents (cf. `operations/triggers/base.py::TriggerEvent.triggering_ability`).
    # Le canal PERCAGE portait deja le sien (`ability_pierce_effect_bonus` -> `ctx["ability_type"]`,
    # gate de `GravitonRifle_ExtraPierce`) ; celui-ci est son pendant sur l'axe DEGAT.
    # `None` (attaque normale / appelant historique) = cle absente -> tout gate `CurrentAbilityIs`
    # est FERME, jamais « inconnu = vrai ».
    if ability_type is not None:
        att_ctx["ability_type"] = int(ability_type)
    # #1005 -- l'`AbilityState` **TERTIAIRE** de l'attaquant (la RELIQUE equipee). Un effet de
    # relique resout son `ConfigVar` contre l'etat que l'`AddEffect` natif lui a passe, et cet etat
    # n'est PAS celui des passifs : MESURE (`unitAbilityStates`, `bloodMephiston` / `Vitarus`)
    # `level = 1, mult = 100` contre `level = 50, mult = 180` pour ses passifs. Sans ces trois
    # cles, `Vitarus.extraDmg` serait lu clampe (`[10] = 728`) au lieu d'`[1] = 490`. Foyer de
    # lecture : `entities/effects/base.py::relic_ability_state`. Cles ABSENTES quand l'attaquant
    # n'a pas de relique -> les deux effets concernes retombent sur leurs champs, en le disant.
    _ae = state.get_entity(int(unit_id))
    _asc = _ae.get_component(StatsComponent) if _ae is not None else None
    _actx = getattr(_asc, "ctx", None)
    if getattr(_actx, "tertiary_ability", None):
        att_ctx["att_tertiary_ability"] = str(_actx.tertiary_ability)
        att_ctx["att_tertiary_level"] = getattr(_actx, "tertiary_ability_level", None)
        att_ctx["att_tertiary_mult"] = getattr(_actx, "tertiary_ability_variables_multiplier", None)
    # Branche `| HasFlag(Self@0x148, 0xc = Teleported)` du trigger de
    # `IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier` : le +25%
    # ranged survit a un deplacement qui etait un TELEPORT. Threade dans `att_ctx` (le contexte
    # per-coup, comme `is_charging`/`trigger_ability_type`) et non en parametre nomme : `has_moved`
    # est PARTAGE par tous les effets, alors que cette branche n'appartient QU'A HeavyWeapon
    # (`CrushingStrikeEffect$$CreateActiveCondition` = `!HasFlag(Self, 0)` seul). La face PREDICTION
    # threade la MEME cle, calculee par `prediction.prediction_has_teleported` (#266).
    if has_moved:
        att_ctx = dict(att_ctx or {})
        att_ctx["has_teleported"] = unit_has_teleported(state, unit_id)
    if trigger_ability_type is not None:
        # #47 : l'ability déclenchante vit dans le MÊME contexte que la position (mirror AbilityEntities
        # — un seul struct de contexte per-coup côté natif, cf. IdunBattle.Entities.Effects.BaseEffect$$DamageBonusForAttack).
        # ⚠ ATTAQUANT SANS POSITION (MACHINE OF WAR hors-plateau, case-mow-offboard-cast : ni Position ni
        # Health) -> `_positional_att_ctx` rend None faute de tuile. Le contexte natif porte NÉANMOINS
        # l'ability déclenchante (elle ne dépend PAS de la position) : on matérialise un ctx minimal
        # (copie défensive quand il existe) au lieu de crasher sur `None[...]`. Découvert par le 1ᵉʳ
        # attaquant sans position de la famille ATTACK (HadesAutocannons 1147, blackForgefiend).
        att_ctx = dict(att_ctx or {})
        att_ctx["trigger_ability_type"] = int(trigger_ability_type)
    # Gates portant sur la CIBLE et re-evalues depuis l'ECS (meme regime que `target_armor_reduced`) :
    #  * `marked_effect_types` = `HasEffect(Target, <EffectType>, Both)` pour les effets-MARQUEUR non
    #    materialises sur la cible (FearedInterrogator_Target 1295) ;
    #  * `tgt_grand_alliance`  = `HasTrait(Target, 0x7ea = 2026 Chaos)` (derive de `GrandAllianceId`,
    #    comme les gates Imperial/Chaos de RitesOfBattle/BeaconOfRage).
    if target_id is not None:
        att_ctx = dict(att_ctx or {})
        att_ctx["marked_effect_types"] = marked_effect_types_for_target(state, unit_id, target_id)
        att_ctx["tgt_grand_alliance"] = grand_alliance_of(state, target_id)
        # `Target@DSLSelectors+0x60` lu en IDENTITE, pas en position : le gate
        # `AreEqual(Target@0x60, BondedEntityFromEffect(Effect@0x38))` de
        # `IdunBattle.Entities.Effects.Loki.HolyDuel_ExtraDmgEffect$$CreateEffectDamageBonusForAttack`
        # compare deux ENTITES. Le contexte portait deja ce meme noeud sous trois autres lectures
        # (`t_pos`, `tgt_team`, `tgt_hp`) ; il lui manquait l'id. MEME cle et MEME semantique que le
        # canal AURA (`_apply_ally_attack_damage_auras`) et que l'axe COUPS
        # (`attack_hits_context`) -- pas de nouveau vocabulaire.
        att_ctx["tgt_id"] = int(target_id)
        # `PsychicStalk_FriendlyChaosExtraDamage` (#366-r1, effet 1435) -- PATTE SELF du slot
        # `CreateEffectDamageBonusForAttack` : ses trois conjoints non-relationnels portent sur
        # l'ATTAQUANT (`HasTrait(Caster@0x48, 0x7ea = Chaos)`), sur la TUILE DE LA CIBLE
        # (`EntitiesWithAnyEffect(Tiles(Target@0x60), Fire)`) et sur le PROFIL du coup
        # (`DamageProfileIs([Flame, Psychic])`). MEMES CLES / MEME semantique que le ctx du canal
        # AURA (`_apply_ally_attack_damage_auras`) et que la face PREDICTION -- pas de fork.
        att_ctx["att_grand_alliance"] = grand_alliance_of(state, unit_id)
        att_ctx["damage_profile"] = damage_profile
        _t_pos = _unit_pos(state, target_id)
        att_ctx["t_pos"] = _t_pos
        att_ctx["tgt_team"] = _unit_team(state, target_id)
        # #1025-r1 -- RARETE de la CIBLE DU COUP, `BaseUnitComponent.Rarity` (+0x74). Sur CE canal
        # (`create_effect_damage_bonus_for_attack`, la boucle des effets de l'ATTAQUANT) le noeud
        # `HasRarity(Target@<DSLSelectors+0x60>, ...)` porte sur le DEFENSEUR -- symetrique exact de
        # l'`attacker_ctx["rarity"]` du canal DEFENSE, qui porte sur `Caster@<DSLSelectors+0x48>`.
        # Consommateur : `ElectrochaffBackups_DamageReductionPct` (1446), dont le
        # `$$CreateDamageModifier` est `ForPercentDecrease(get_OwnerIsCaster & HasRarity(Target,
        # Mythic) & AreFriends(Target, EffectSource), ConfigVar(0x46))`.
        # TRI-ETAT (`None` = non mesure -> le gate se FERME), cf. `_unit_rarity`. MEME cle et MEME
        # semantique cote PREDICTION (`prediction/normal_attack.py`, `prediction/abilities.py`,
        # les six playbooks d'attaque) -- pas de fork.
        att_ctx["tgt_rarity"] = _unit_rarity(state, target_id)
        # #1025-r1 -- `AreFriends(Target@<DSLSelectors+0x60>, EffectSource(Effect@<DSLSelectors
        # +0x38>), 0, false)` : le membre DROIT est la SOURCE de l'effet (`EffectComponent.SourceUnit
        # @+0x10` = `self.source` cote port), qui n'est NI l'attaquant NI la cible -- elle ne peut
        # donc se resoudre que par une table. MEME cle et MEME idiome que l'`attacker_ctx` du canal
        # DEFENSE (`defender_modifiers`), qui la pose deja pour le meme noeud vu de l'autre bord.
        att_ctx["team_by_id"] = {int(uid): oc.team
                                 for uid, e in state.entities.items()
                                 for oc in (e.get_component(OwnerComponent),) if oc is not None}
        # `HealthPctIsBelowOrEqual(Target@0x60, ConfigConst(0x4f = healthPct))` -- le gate de
        # DOUBLEMENT de `LightOfSanguinius_DamageReductionEffect$$CreateDamageModifier` (#510) porte
        # sur les PV de la CIBLE DU COUP, pas sur ceux du porteur de l'effet. MEMES cles, MEME
        # semantique cote PREDICTION (`prediction/normal_attack.py`, `prediction/abilities.py`).
        att_ctx["tgt_hp"], att_ctx["tgt_hp_max"] = _unit_hp_and_max(state, target_id)
        # `Tiles` = `IdunBattle.Entities.Selectors.UnitsMainTilesSelector` -> la MAIN TILE de la
        # cible. `_positional_att_ctx` n'a rempli que le centre + ring-1 de l'ATTAQUANT : on
        # COMPLETE (setdefault) la position de la cible sans jamais ECRASER une entree deja posee
        # (elle porte, elle, les covers de terrain que `LordOfTempests` compte).
        if _t_pos is not None:
            _tfx = dict(att_ctx.get("tile_effects_by_pos") or {})
            for _p, _names in (tile_status_effects_by_pos(state, [_t_pos]) or {}).items():
                _tfx.setdefault(tuple(_p), _names)
            att_ctx["tile_effects_by_pos"] = _tfx
        # `IsCharging` (case-r32) = `BattleQuery$$IsCharging(caster, target)` : adjacence ET
        # `ChargedUnitIds@+0x190.Contains(target.Id)`. C'est le gate des trois effets extra-degat
        # de charge (AvalancheOfMuscle 1025, FeederTendrils 1197, BlackRage 1343). La liste est
        # remplie par `MoveUnitOperation$$UpdateCharging` (unites NOUVELLEMENT adjacentes du pas)
        # et videe par `FinishUnitTurnOperation$$Execute` -> portee « ce tour ». Il REMPLACE le
        # proxy `has_moved`, qui sur-accordait : un caster qui bouge vers une cible DEJA adjacente
        # avant son pas a `Moved` VRAI et `IsCharging` FAUX (mesure : +599/coup de trop).
        # ⚠ `has_moved` reste threade tel quel — il porte l'AUTRE predicat natif, `HasFlag(Moved)`
        # (HeavyWeapon_ExtraDmg, CrushingStrike) : les deux existent, ne pas les confondre.
        att_ctx["is_charging"] = battle_query_is_charging(state, unit_id, target_id)
        # #1011 -- PATTE SELF de `NornCrownEffect` : le PORTEUR de la relique est dans son propre
        # selecteur (`AreFriends` n'ecarte pas l'egalite), donc les MEMES trois canaux que le canal
        # AURA (`_apply_ally_attack_damage_auras`) doivent etre lisibles ici -- MEMES CLES, MEME
        # semantique, pas de fork. L'attaquant EST le porteur sur ce canal, d'ou `att_*`.
        # ⚠ MESURE #1011 : le porteur n'entre dans la bulle Synapse QUE s'il existe un AUTRE
        # emetteur `Synapse` a portee (`GetSurroundingUnits(..., includeCenter: false)`), donc ces
        # clefs ne suffisent pas a allumer le bonus -- elles le rendent EVALUABLE.
        # `setdefault` sur `att_pos` : `_positional_att_ctx` a pu y poser la tuile d'attaque EVALUEE
        # (qui n'est pas forcement la tuile courante) -- on ne l'ECRASE jamais.
        att_ctx["att_id"] = int(unit_id)
        att_ctx.setdefault("att_pos", _unit_pos(state, unit_id))
        att_ctx["att_team"] = _unit_team(state, unit_id)
        att_ctx.setdefault("att_traits", target_trait_names(state, unit_id))
        att_ctx[_NORN_CTX_TGT_EFFECTS] = _target_effect_names(state, target_id)
        att_ctx[_NORN_CTX_SYNAPSE] = _team_synapse_positions(state)
        att_ctx.setdefault("tertiary_ability_state_of", _tertiary_ability_state_fn(state))
    mods = build_attacker_modifiers_from_effects(active, is_ranged, is_normal_attack=is_normal_attack,
                                                 has_moved=has_moved, target_traits=target_traits,
                                                 target_armor_reduced=tar, att_ctx=att_ctx)
    _apply_ally_attack_damage_auras(state, unit_id, mods, is_ranged, tar,
                                    damage_profile=damage_profile,
                                    target_id=target_id, target_traits=target_traits,
                                    is_overwatch=is_overwatch)
    return mods, active


def defender_modifiers(state: State, unit_id: int, hp: Optional[int],
                       is_melee: Optional[bool] = None, damage_profile: Optional[str] = None,
                       attacker_id: Optional[int] = None, is_normal_attack: Optional[bool] = None):
    """`DamageModifiers` de réduction du DÉFENSEUR (cible) depuis ses EFFETS actifs (symétrique attaquant ;
    `CalculateDefenderModifiersForPrediction`). Renvoie (mods, active_effects). None-safe (mods vide → no-op).

    `is_melee`/`damage_profile` = nature du coup, propagés aux malus GATÉS (mirror de la prédiction, #59) :
    `IsMeleeAttack` (ex. Terrifying_ExtraDefense : `if not is_melee: return None`) et `DamageProfileIs`
    (ex. TerminatorArmour : PAS de réduction si profil ∈ Psychic/DirectDamage). None (défaut, ex. chemins
    ability non encore câblés) = comportement historique (les malus gatés IsMeleeAttack ne s'appliquent pas ;
    TerminatorArmour s'applique quel que soit le profil) — INERTE pour une cible sans effet de défense gaté.
    `attacker_id` = identité du coup, propagée aux malus gated sur l'attaquant (ex. Neuroparasite : bonus
    RESERVE au Neurothrope source). ⚠ Le niveau/mult SOURCE (magnitude Neuroparasite) N'EST PAS résolu ici
    (le runner ne matérialise pas encore le parasite -> ability_level absent -> Neuroparasite INERTE en combat,
    cf. tâche runner-side ; la contribution PREDICTION est complète).
    `is_normal_attack` (#112) = nature du VECTEUR : True=attaque normale, False=spéciale config-based. Threadé
    dans l'att_ctx -> gate `IsNormalAttack` des malus défenseur (ex. MartialKatah_DmgReduction -20% #105 :
    réduit UNIQUEMENT les attaques normales reçues par son porteur, no-op sur les spéciales). Symétrique de la
    prédiction (`_add_positional_and_defender_mods`). None (caller historique) => ctx sans flag => gate no-op."""
    active = (state.effects.active_effects(unit_id, unit_state_for_effects(state, unit_id))
              if state.effects is not None else [])
    att_ctx = None
    # `IsTurnOf(Owner@0x148)` (case-366-r1) : sur ce canal `Owner` = le PORTEUR de l'effet, donc la
    # CIBLE `unit_id`. Le natif compare `OwnerComponent.CurrentPlayerEntityId` a
    # `TurnComponent.CurrentPlayerId` (`IsTurnOfUnitTrigger$$ShouldTrigger`) : on LIT les deux
    # (`OwnerComponent.player` de l'ECS, `State.current_player_id` = mirror `GetCurrentPlayerId`).
    # Une des deux inconnues -> cle ABSENTE (non mesure), jamais un booleen devine.
    _toc = _owner_turn_flag(state, unit_id)
    if _toc is not None:
        att_ctx = {"is_turn_of_owner": _toc}
    # #911 : `GetNumAdjacentTauntedEnemies()` -- MEME convention que `is_turn_of_owner` juste
    # au-dessus : sur ce canal `Owner` est le PORTEUR de l'effet, donc `unit_id` (la CIBLE du coup).
    # C'est ce qu'exige le gate `get_OwnerIsTarget` de `DaemonicPatrons_DmgReduction` (1465).
    # Cle POSEE seulement si le compte est mesure -- absente = « non mesure », jamais un 0 invente.
    _adt = adjacent_taunted_enemies_count(state, unit_id)
    if _adt is not None:
        att_ctx = dict(att_ctx or {})
        att_ctx["adjacent_taunted_enemies"] = _adt
    # #932 : TROISIEME cle de ce contexte portee sur l'OWNER de l'effet (= la CIBLE `unit_id`), pour
    # la MEME raison qu'`is_turn_of_owner` et `adjacent_taunted_enemies` ci-dessus -- le trigger de
    # `DeathwingEffect$$CreateEffectDamageMalusForDefense` est `get_OwnerIsTarget`, donc son
    # compteur d'amis Dark Angels adjacents est celui du DEFENSEUR. `owner_team` est le membre DROIT
    # d'`AreEnemies(Actor@+0x40, Owner@+0x30, 0)` : le membre GAUCHE est deja `team` (l'attaquant),
    # posee plus bas. Cles ABSENTES quand la mesure n'aboutit pas -> disjoint FERME cote effet.
    _ada = adjacent_dark_angels_friends_count(state, unit_id)
    if _ada is not None:
        att_ctx = dict(att_ctx or {})
        att_ctx["adjacent_dark_angels_friends"] = _ada
    _own_team = _unit_team(state, unit_id)
    if _own_team is not None:
        att_ctx = dict(att_ctx or {})
        att_ctx["owner_team"] = _own_team
    # `IsAdjacent(Caster@DSLSelectors+0x48, Owner@DSLSelectors+0x30, 3)` -- les DEUX arguments d'un
    # noeud GEOMETRIQUE que ce contexte ne portait pas encore. `owner_pos` est la CINQUIEME cle
    # portee sur l'OWNER de l'effet (= la CIBLE `unit_id`), meme convention qu'`owner_team`
    # ci-dessus ; `att_pos` est posee plus bas avec les autres cles du CASTER. MEMES cles que la face
    # PREDICTION (`playbook/prediction/_shared.py`) -- pas de fork. Position inconnue -> cle a None
    # -> le gate se FERME. DEUX consommateurs, arrives par deux tranches et sur le MEME couple :
    #   * `TerrorsLament_DamageReduction` (#950) -- `IsAdjacent(Caster, Owner, 3)` ;
    #   * `HuntersBeyondDeathEffect` (#952) -- `NOT AmountIsGreater(MinDistance(EffectSource,
    #     Caster@+0x48), Direct(2))`, ou le porteur EST la source (`AddEffect(..., source = Owner,
    #     targets = Owner)`). Le second n'a rien eu a ajouter ici : le premier avait deja pose les
    #     deux bouts sous ces noms-la.
    _own_pos = _unit_pos(state, unit_id)
    if _own_pos is not None:
        att_ctx = dict(att_ctx or {})
        att_ctx["owner_pos"] = _own_pos
    if attacker_id is not None or is_normal_attack is not None:
        att_ctx = dict(att_ctx or {})
        att_ctx.update({"id": attacker_id, "is_normal_attack": is_normal_attack})
        # FACTION de l'attaquant (gate `HasFaction(actor, ...)` des malus défenseur, ex. Markerlight
        # IdunBattle.Entities.Effects.Loki.MarkerlightEffect$$CreateDamageModifier : +15% aux attaques RANGED d'un attaquant T'AU sur la cible marquée). FactionId
        # gameconfig par visualId (même résolveur `_faction` que `entities_from_state`) ; lazy import
        # (garde anti-circulaire). Attaquant introuvable → clé absente → gates faction no-op (fidèle).
        if attacker_id is not None:
            _ae = state.get_entity(attacker_id)
            _auc = _ae.get_component(UnitComponent) if _ae is not None else None
            if _auc is not None:
                from ..ai.action_generators import _faction
                att_ctx["faction"] = _faction(_auc.visual_id)
            # ── Nœuds DSL natifs portes sur `caster@0x160` (l'ATTAQUANT du coup) : `IsUnit(caster)`,
            # `AreFriends(caster, <noeud entite>)` et `HasTrait(caster, …)`. Contexte PARTAGE avec la
            # PREDICTION (`playbook/prediction/_shared.py`), MEMES cles, MEME semantique — le fork
            # combat/prediction est ce que plusieurs residus de l'inventaire decrivent.
            #  * `is_unit`     = `IdunBattleLogic.Entities.DSLFactory$$IsUnit(caster@0x160)` : l'attaquant
            #    est une ENTITE-UNITE (presence d'un `UnitComponent`), pas une tuile/entite-effet.
            #  * `team`        = equipe de l'attaquant (`OwnerComponent.team`) = membre GAUCHE d'
            #    `IdunBattleLogic.Entities.DSLFactory$$AreFriends` (-> `IdunBattle.Entities.Triggers.
            #    AreEntityFriendsAbilityTrigger$$ShouldTrigger` = `battleQuery.AreFriends(a, b)`).
            #  * `team_by_id`  = {unit_id: team} — le membre DROIT d'`AreFriends` n'est PAS toujours
            #    l'attaquant (`EffectSource(Effect@0x150)` = le POSEUR de l'effet, cf. Chronometron) :
            #    sans resolveur d'equipe par entite, ce gate est INCALCULABLE. Meme cle/forme que le
            #    `team_by_id` deja threade par `attack_hits_context` (axe COUPS).
            #  * `traits`      = noms de traits gameconfig de l'attaquant (`StatsComponent.ctx.traits`),
            #    lus par `HasTrait(caster, …)` / `IsMechanical(caster)`.
            att_ctx["is_unit"] = _auc is not None
            _aoc = _ae.get_component(OwnerComponent) if _ae is not None else None
            att_ctx["team"] = _aoc.team if _aoc is not None else None
            att_ctx["traits"] = target_trait_names(state, attacker_id)
            # #999-r3-r1 : `HasRarity(Caster@<DSLSelectors+0x48>, idun.meta.Rarity.Mythic = 5)` --
            # SIXIEME noeud de ce contexte porte sur le CASTER, meme convention de nommage que
            # `team`/`traits`/`faction` (sans prefixe = l'ATTAQUANT, prefixe `owner_` = le porteur).
            # Consommateur : `HyperCorrosiveAcid_ExtraDamagePctEffect` (1448), dont le
            # `$$CreateEffectDamageBonusForAttack` est `get_OwnerIsTarget & (AreFriends(Caster,
            # EffectSource) & HasRarity(Caster, Mythic) & HasTrait(Caster, 0x10 = Hero))` -- l'effet
            # n'a AUCUN `$$CreateTargetSelector`, donc son Owner EST son porteur et le canal est
            # celui-ci, pas l'aura. MEME cle et MEME semantique que la face PREDICTION
            # (`playbook/prediction/_shared.py`). TRI-ETAT : `None` -> gate FERME.
            att_ctx["rarity"] = _unit_rarity(state, attacker_id)
            # #952 : POSITION de l'attaquant -- membre DROIT du `MinDistance(EffectSource,
            # Caster@+0x48)`. Meme nommage que le couple `team`/`owner_team` juste au-dessus :
            # sans prefixe = l'ATTAQUANT, prefixe `owner_` = le porteur de l'effet.
            _apc = _ae.get_component(PositionComponent) if _ae is not None else None
            att_ctx["pos"] = (_apc.col, _apc.row) if _apc is not None else None
            # #932 : `HasTrait(Actor@DSLSelectors+0x40, 0x7ea)` -- la grande-alliance de l'ATTAQUANT.
            # Elle N'EST PAS dans `traits` juste au-dessus : le trait d'alliance est DERIVE du
            # `GrandAllianceId` par `idun.Idun.Source.Shared.GrandAlliance$$GetTrait` et ajoute par
            # le BattleConfiguration, pas par le kit gameconfig. MEME resolveur et MEME semantique
            # que `tgt_grand_alliance` / `att_grand_alliance` de la face ATTAQUANT.
            att_ctx["grand_alliance"] = grand_alliance_of(state, attacker_id)
            att_ctx["team_by_id"] = {int(uid): oc.team
                                     for uid, e in state.entities.items()
                                     for oc in (e.get_component(OwnerComponent),) if oc is not None}
            # `IsAdjacent(Caster@DSLSelectors+0x48, …)` : la TUILE de l'attaquant. En COMBAT le
            # caster a deja bouge quand `Execute` tourne, donc sa position ECS EST sa tuile
            # d'attaque -- MEME lecture que `_apply_ally_attack_damage_auras` (`PositionComponent`).
            att_ctx["att_pos"] = _unit_pos(state, attacker_id)
            # #462-r4b-r1-r1 -- NIVEAU + MULTIPLICATEUR de l'ATTAQUANT, la MAGNITUDE d'un additif
            # defenseur indexe sur la SOURCE. `IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$
            # CreateEffectDamageMalusForDefense` = `ForAddition(OwnerIsTarget & AreEqual(BondedEntity,
            # damageSource) & DamageProfileIs(0xd), Multiply(ConfigVar(8 = extraDmg, GetAbilityState(
            # effect)), EffectLevel(Effect)))` : le `ConfigVar` s'indexe sur l'`AbilityState` de la
            # SOURCE, et le gate `AreEqual` FAIT de l'attaquant cette source -- d'ou une magnitude
            # lue sur l'ATTAQUANT. La PREDICTION posait deja ces deux cles
            # (`playbook/prediction/_shared.py` : `scene.ablvl_by_id.get(att_id)` / `scene.mult(
            # att_id)`, eux-memes `int(ctx.passive_ability_level or 0)` / `int(ctx.
            # ability_variables_multiplier or 100)`) ; le COMBAT ne les posait PAS, donc
            # `create_effect_damage_malus_for_defense` y retournait None sur `src_lvl is None` --
            # l'effet etait MATERIALISE et pourtant INERTE. Meme fork prediction/combat que
            # #462-r4b-r1 vient de fermer sur l'axe PLACEMENT, reste ouvert sur l'axe MAGNITUDE.
            # MESURE (`probe_462_r4b_r1_r1_defender_additive_carriers.py --neuro`, Neurothrope ->
            # blackPossession, parasite niveau 1, `RangedSpecialist` M=1.33) : natif 4448, port 2192,
            # ecart 2256 = `extraDmg[50] x 1.8 = 1696` x 1.33 -- EXACTEMENT le separateur #88 que la
            # face PREDICTION avait mesure le 2026-07-12. On lit la MEME source que la Scene
            # (`StatsComponent.ctx`), donc les deux faces s'indexent desormais a l'identique.
            # Consommateur UNIQUE de ces deux cles dans tout `engine/` : `NeuroparasiteEffect`.
            _asc = _ae.get_component(StatsComponent) if _ae is not None else None
            _actx = _asc.ctx if _asc is not None else None
            if _actx is not None:
                att_ctx["ability_level"] = int(_actx.passive_ability_level or 0)
                att_ctx["multiplier"] = int(_actx.ability_variables_multiplier or 100)
            # #1052 -- LES TROIS TERMES DE PERCAGE QUE LIT `AllIsDustEffect$$CreatePiercingBonusFor
            # Attack` SUR LE CASTER. Memes cles / meme semantique sur la face PREDICTION
            # (`playbook/prediction/_shared.py`), comme tout ce contexte.
            #  * `extra_pierce`     = `StatAmount(Caster@+0x48, 0x1a = ExtraPierce, 0x5 = Modification)` ;
            #  * `extra_pierce_dir` = `StatAmount(Caster@+0x48, 0x15 = ExtraPierceMelee | 0x16 =
            #    ExtraPierceRanged, 0x5 = Modification)` -- la branche du `If(IsMeleeAttack, .., ..)`
            #    de `$$GetPierceStatModifier`. `is_melee` non threade -> cle ABSENTE (le `If` natif
            #    n'a pas de branche « inconnu ») ;
            #  * `effect_pierce_addition` = `CasterEffectPierceAddition(excludedEffectType = 0x4a5)`
            #    = la somme des `BaseEffect$$PiercingBonusForAttack` -- cote port, celle des effets
            #    de l'ATTAQUANT (`piercing_bonus_from_effects`, meme mirror). L'exclusion de 0x4a5
            #    est STRUCTURELLE ici : l'effet 1189 vit sur la CIBLE, jamais dans cette liste.
            # TRI-ETAT : une cle absente FERME le gate cote effet -- jamais un 0 devine.
            if _actx is not None and is_melee is not None:
                att_ctx["extra_pierce"] = int(_actx.extra_pierce or 0)
                att_ctx["extra_pierce_dir"] = int((_actx.extra_pierce_melee if is_melee
                                                   else _actx.extra_pierce_ranged) or 0)
            _aeff = (state.effects.active_effects(attacker_id,
                                                  unit_state_for_effects(state, attacker_id))
                     if state.effects is not None else None)
            if _aeff is not None:
                att_ctx["effect_pierce_addition"] = int(piercing_bonus_from_effects(
                    _aeff, {"owner_id": attacker_id, "att_id": attacker_id,
                            "is_ranged": (None if is_melee is None else (not is_melee))}))
    # STAT-MODS DEFENSE de la CIBLE (#197) : moitie DEFENSE de `CalculateDefenderModifiersForPrediction
    # IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`, portee DANS la fonction PARTAGEE (fin du fork prediction/combat -- cf. son docstring).
    # Source runner = le `StatComponent` DEFENSE (stat 3) de l'ECS live (`ctx.stats`, delta cuit au load
    # depuis combatSnapshot + mutable par les operations) -- l'analogue de la DefenseComponent que le natif
    # relit. Ex. tuile Thorns -50 -> +50 -> x1.5 sur le degat RECU (GROUND TRUTH live #197 : degat reel x1.5).
    _te = state.get_entity(unit_id)
    _tsc = _te.get_component(StatsComponent) if _te is not None else None
    _def_stat = (_tsc.ctx.stats.components.get(int(StatType.DEFENSE))
                 if _tsc is not None and _tsc.ctx is not None else None)
    mods = build_defender_modifiers_from_effects(active, is_melee, damage_profile,
                                                 attacker_ctx=att_ctx, defense_stat=_def_stat)
    # AURAS-DÉFENSE state-wide (#184) : effets EffectWithTarget possédés par d'AUTRES unités dont le
    # TargetSelector projette sur la CIBLE — même boucle « TOUS les EffectWithTarget × leurs cibles »
    # que la prédiction (`IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`, appelée AUSSI par le
    # COMBAT via `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` slot 0xf, cf. case-68). Ex. DaughterOfTheAbyss
    # (Atlacoya) : -dmgReductionPct% Psychic aux amis rayon 2 / +extraDmgPct% aux Psykers ennemis.
    # Positions/équipes RÉELLES depuis l'ECS ; porteurs vivants uniquement. No-op sans carrier concerné.
    tp = None
    te = state.get_entity(unit_id)
    tpc = te.get_component(PositionComponent) if te is not None else None
    if tpc is not None:
        tp = (tpc.col, tpc.row)
    toc = te.get_component(OwnerComponent) if te is not None else None
    carriers = []
    for uid, e in state.entities.items():
        if uid == unit_id:
            continue
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        if oc is None:
            continue
        hc = e.get_component(HealthComponent)
        if hc is not None and hc.hp is not None and hc.hp <= 0:
            continue                                        # porteur mort -> aura éteinte
        ceff = (state.effects.active_effects(uid, unit_state_for_effects(state, uid))
                if state.effects is not None else [])
        if ceff:
            # #999-r3-r1-r1 -- MEME reparation que `_apply_ally_attack_damage_auras` ci-dessus, sur
            # l'autre face du MEME artefact : le `pc is None -> continue` ecartait toute MACHINE OF
            # WAR de l'univers des porteurs, alors que le natif
            # (`...DamageCalculations$$CalculateDefenderModifiersForPrediction`) itere l'ETAT
            # BOARD-WIDE sans lire aucune position. `owner_pos = None` -> les auras positionnelles
            # se taisent d'elles-memes chez leurs lecteurs.
            carriers.append((uid, ((pc.col, pc.row) if pc is not None else None), oc.team, ceff))
    if carriers and tp is not None:
        for eb in aura_defense_damage_malus_from_units(
                carriers, {"tgt_id": unit_id, "t_pos": tp,
                           "tgt_team": toc.team if toc is not None else None,
                           "tgt_traits": target_trait_names(state, unit_id),
                           # #999-r3-r1 -- RARETE de la CIBLE, `BaseUnitComponent.Rarity` (+0x74).
                           # Le BENEFICIAIRE de ce canal est la CIBLE du coup (la boucle native de
                           # `IdunBattle.Core.Services.DamageCalculations$$
                           # CalculateDefenderModifiersForPrediction` ecrit `AbilityEntities+0x18
                           # (Owner) <- CHAQUE CIBLE du selecteur`, et le trigger est
                           # `get_OwnerIsTarget`), donc un etage `UnitsWithRarity(...)` du
                           # `$$CreateTargetSelector` se lit ICI, sur `unit_id`. Consommateur :
                           # `ContemptuousDisregard_DamageReductionEffect` (1443), dont le selecteur
                           # est `Filter(UnitsWithRarity(Friends(Owner, AllUnits, 3), Mythic, 3),
                           # HasTileStatusEffect(Tiles(<element courant>)))`. MEME cle et MEME
                           # semantique que la face PREDICTION -- pas de fork. TRI-ETAT : `None` =
                           # non mesure -> le gate se FERME (cf. `_unit_rarity`).
                           "tgt_rarity": _unit_rarity(state, unit_id),
                           "damage_profile": damage_profile,
                           # `IsUnit(caster@0x160)` (= `DSLSelectors+0x48`) -- MEME cle/semantique
                           # que l'`att_ctx["is_unit"]` du canal defenseur ci-dessus, relayee au
                           # canal AURA parce que `PsychicStalk_ExtraAttackDamage` (#366-r1) porte
                           # son gate sur le CASTER, pas sur le porteur de l'effet. Absente si
                           # l'appelant ne passe pas `attacker_id` -> le gate se tait.
                           **({"att_id": attacker_id,
                               "att_is_unit": (att_ctx or {}).get("is_unit"),
                               # `IsAdjacent(Caster@+0x48, Owner@+0x30, 3)` et
                               # `AreEnemies(Owner@+0x30, Caster@+0x48, 0)` -- les DEUX arguments
                               # sont ici : `owner_*` vient du carrier (pose par l'agregateur),
                               # `att_*` du coup. MEMES cles que le canal AURA jumeau cote ATTAQUE
                               # (`_apply_ally_attack_damage_auras`), pas un nommage neuf.
                               # Consommateur : `TerrorsLament_DamageReduction`, dont le trigger ne
                               # porte NI sur la cible NI sur un `CreateTargetSelector`.
                               "att_pos": _unit_pos(state, attacker_id),
                               "att_team": (att_ctx or {}).get("team"),
                               # #952 : le TROISIEME conjoint du gate d'`HuntersBeyondDeathEffect`
                               # sur l'attaquant -- `HasTrait(Caster@+0x48, 0x3ea = Psyker)`. MEME
                               # nom et MEME resolveur que l'agregateur FRERE
                               # (`aura_attack_damage_bonus_from_allies`). Les deux autres
                               # conjoints (`att_pos`, `att_team`) etaient DEJA la, poses par
                               # #950 : cette tranche n'a eu qu'a ajouter les traits.
                               "att_traits": (att_ctx or {}).get("traits"),
                               # #959 : le second membre du `op_BitwiseOr` de
                               # `PredictiveGuidance_MeleeEffect$$BonusCondition` --
                               # `HasFaction(Caster@+0x48, 0x14 = LeaguesOfVotann, 3)`. MEME cle,
                               # MEME source (`FactionId` du gameconfig) et MEME resolveur que le
                               # canal AURA jumeau cote ATTAQUE et que `build_hits_board` : ce
                               # n'est pas un nommage neuf. Le PREMIER membre (`IsMechanical`) se
                               # lit dans `att_traits`, deja pose ci-dessus par #952.
                               "att_faction": (_unit_gameconfig(state, attacker_id)
                                               or {}).get("FactionId"),
                               # #1025-r1 : `HasRarity( Caster@<DSLSelectors+0x48>,
                               # 5 = idun.meta.Rarity.Mythic )` -- 2e conjoint du trigger de
                               # `MoreGitzOverEre_ExtraDamagePct`, dont le BENEFICIAIRE est la
                               # CIBLE (`get_OwnerIsTarget`) mais dont ce gate-ci porte sur
                               # l'ATTAQUANT. MEME cle, MEME resolveur et MEME tri-etat que
                               # l'agregateur FRERE cote ATTAQUE (`_apply_ally_attack_damage_
                               # auras`) : ce n'est pas un nommage neuf. `None` -> gate FERME.
                               "att_rarity": _unit_rarity(state, attacker_id)}
                              if attacker_id is not None else {}),
                           # `IsMeleeAttack`, 3e conjoint du meme trigger. Tri-etat #106 conserve :
                           # `None` = nature non declaree -> le gate se ferme cote effet.
                           "is_melee": is_melee,
                           # #959 : `UnitsWith[out]Flag(<aura>, 0 = UnitFlag.Moved, 3)` -- le noeud
                           # qui PARTITIONNE les deux effets de degat de `PredictiveGuidance` entre
                           # melee et distance. Il porte sur la CIBLE (l'element du selecteur), pas
                           # sur l'attaquant : `unit_has_moved` est le LECTEUR UNIQUE du
                           # `UnitFlagsComponent`, le meme que celui du `has_moved` attaquant.
                           # Tri-etat : `None` = flag non mesure -> le gate se FERME cote effet.
                           "tgt_has_moved": unit_has_moved(state, unit_id),
                           # `HasTileStatusEffect`/`EntitiesWithAnyEffect(Tiles(Target), Fire)` --
                           # MEME canal et MEME forme `{(col,row): [noms]}` que celui deja monte
                           # pour `LetTheGalaxyBurnEffect` (`collect_additional_hit_groups`).
                           # `Tiles` = `UnitsMainTilesSelector` -> la MAIN TILE seule (`tp`).
                           "tile_effects_by_pos": tile_status_effects_by_pos(state, [tp]),
                           # #954 -- le `CreateTargetSelector` d'`ObsessiveAnnunciation_ExtraDmg`
                           # (`AdjacentEnemies(Owner@+0x30, unique: true, UnitSelectionType 3)`).
                           # CALLABLE et PAR PORTEUR : la boucle native de
                           # `DamageCalculations$$CalculateDefenderModifiersForPrediction` ecrit
                           # `AbilityEntities+0x18 (Owner) <- CHAQUE CIBLE de l'effet`, donc
                           # `get_OwnerIsTarget` y demande une APPARTENANCE a cet ensemble.
                           # MEME cle, MEME resolveur et MEME semantique que celle posee par
                           # `_crit_board` pour la moitie CRIT du meme passif -- pas de fork, et
                           # les deux moities ne peuvent donc pas diverger sur la geometrie.
                           _OA_CTX_ADJ_ENEMY_IDS:
                               lambda oid: adjacent_enemy_ids(state, int(oid)),
                           # #1025-r1 -- `IsNormalAttack`, 4e conjoint du trigger de
                           # `MoreGitzOverEre_ExtraDamagePct` (<< normal melee attacks >>). MEME
                           # donnee et MEME tri-etat que le parametre homonyme deja threade dans
                           # l'`att_ctx` du canal defenseur non-aura juste au-dessus (#112) : on la
                           # relaie au canal AURA, on ne la re-derive pas. `None` -> gate FERME.
                           "is_normal_attack": is_normal_attack,
                           # #1025-r1 -- `AdjacentUnits(<la CIBLE>, unique, 3)` + `(team,
                           # visual_id, rarity)` par voisin : le substrat des DEUX branches du
                           # `$$CreateTargetSelector` de `MoreGitzOverEre_ExtraDamagePct`. La
                           # CIBLE est fixe pour tout cet appel -> valeur PRE-CALCULEE, pas un
                           # callable (contraste `_OA_CTX_ADJ_ENEMY_IDS`, qui se resout par
                           # PORTEUR). Tri-etat : `None` = non mesure -> le gate se FERME.
                           _MG_CTX_TGT_ADJ_PROFILES: _adjacent_unit_profiles(state, unit_id),
                           # #1042-r1 -- le `$$CreateTargetSelector` de
                           # `WisdomOfTheAncients_DamageReductionEffect` (1445), CALLABLE et PAR
                           # PORTEUR pour la meme raison que la cle ci-dessus : la boucle native de
                           # `DamageCalculations$$CalculateDefenderModifiersForPrediction` ecrit
                           # `AbilityEntities+0x18 (Owner) <- CHAQUE CIBLE de l'effet`, donc
                           # `get_OwnerIsTarget` y demande une APPARTENANCE. Ce selecteur pose des
                           # questions que le ctx d'un coup ne porte pas (adjacence d'un TIERS a la
                           # cible, sa rarete, son trait `Hero`), d'ou la re-evaluation complete.
                           # MEME cle, MEME semantique et MEME foyer d'adjacence NATIVE
                           # (`battle_query.is_adjacent`) que la face PREDICTION -- pas de fork.
                           _WOTA_CTX_TARGET_IDS:
                               lambda oid: wisdom_of_the_ancients_target_ids(state, int(oid)),
                           # #1038-r1 / #1042-r1 -- `GetAbilityState(effet)` des deux auras
                           # MYTHIQUES de MoW (1443, 1445). Leur `ConfigVar(0x46)` est indexe par
                           # l'`AbilityStateReference` BAKEE a la pose, c.-a-d. l'etat **TERTIAIRE**
                           # (`level 1..4 / mult 100`), jamais celui des PASSIFS. MEME cle, MEME
                           # foyer (`triggered_ability_state`, #357) et MEME callable que les trois
                           # ctx qui l'exposent deja (`attacker_modifiers`, `_crit_board`,
                           # `collect_additional_hit_groups`) -- pas un nommage neuf.
                           #
                           # ⚠ MERGE #1055 x #1056 : les DEUX tranches posaient cette cle ici, et
                           # les deux se declaraient << un seul foyer de nommage >>. Elles ont la
                           # MEME valeur de chaine (`"tertiary_ability_state_of"`) et le MEME
                           # resolveur (`_tertiary_ability_state_fn`), donc UNE SEULE entree est
                           # gardee -- deux auraient ete une cle dupliquee dans le litteral (Python
                           # garde la derniere, en silence). Il reste DEUX CONSTANTES pour cette
                           # unique chaine : `damage_reduction.CTX_TERTIARY_ABILITY_STATE_OF` et
                           # `extra_damage_aura.CTX_ABILITY_STATE_OF`. C'est le foyer de nommage
                           # DEDOUBLE que chacune pretendait etre -- a fusionner (residu).
                           _MYTHIC_CTX_ABILITY_STATE: _tertiary_ability_state_fn(state)}):
            add_modifier(mods, eb)
    return mods, active


def apply_elevation_bonus(state: State, mods, attacker_id: int, target_id: int) -> None:
    """#58 : ajoute au `mods` de l'ATTAQUANT le bonus d'ELEVATION (+surplomb) — feuille positionnelle du
    builder PARTAGE `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` que le COMBAT applique AUSSI
    (verdict RE cluster : misnomer "ForPrediction"). Elevations = `state.board` aux tuiles REELLES
    (attaquant/cible) ; gate no-elevation (effet 0x423 sur attaquant OU cible). No-op sans board/positions
    (mods inchange). MEME service `calculate_elevation_bonus_modifier` (DamageCalculations) que la
    prediction, MEME constante `ELEVATION_BONUS_PCT` (pas de fork)."""
    board = state.board          # toujours present (__slots__) ; None tant que le boardGraph n'est pas cale
    if board is None:
        return
    ea, et = state.get_entity(attacker_id), state.get_entity(target_id)
    pa = ea.get_component(PositionComponent) if ea is not None else None
    pt = et.get_component(PositionComponent) if et is not None else None
    if pa is None or pt is None:
        return
    ta, tt = board.tile_at(pa.col, pa.row), board.tile_at(pt.col, pt.row)
    if ta is None or tt is None:
        return
    a_elev, t_elev = ta.get("elevation"), tt.get("elevation")
    if a_elev is None or t_elev is None:
        return

    def _has_no_elev(uid: int) -> bool:
        effs = (state.effects.active_effects(uid, unit_state_for_effects(state, uid))
                if state.effects is not None else [])
        return any(getattr(ef, "effect_type", None) == EFFECT_NO_ELEVATION for ef in effs)

    no_elev = _has_no_elev(attacker_id) or _has_no_elev(target_id)
    # #449-r2-r4-r4 : le pct vient de la BC de CETTE bataille (`State`), plus de la seed figee a
    # l'import. `ELEVATION_BONUS_PCT` restait juste tant que la BC valait la seed et devenait faux
    # sinon -- mesure : a `ElevationBonus` ABSENT le natif inflige 5160 la ou le port en calculait
    # 8797 (+70,5 %), et a 100 le natif monte a 10520 quand le port restait a 8797.
    eb = calculate_elevation_bonus_modifier(
        a_elev, t_elev, resolve_damage_field("elevation_bonus", state=state),
        attacker_or_target_has_no_elev_effect=no_elev)
    if eb is not None:
        add_modifier(mods, eb)


def apply_trench_reduction(state: State, mods, attacker_id: int, target_id: int,
                           damage_profile: Optional[str] = None) -> None:
    """#181 : ajoute au `mods` de l'ATTAQUANT la reduction TRENCH (-TrenchReductionPercentage%, =-50%) — feuille
    positionnelle du builder PARTAGE `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` que le COMBAT applique
    AUSSI (comme l'elevation : misnomer "ForPrediction", xrefs DATA-only = invoque par delegate pour prediction
    ET combat ; aucun builder combat separe). MEME fonction nommee `calculate_trench_reduction`
    (`IdunBattle.Core.Services.DamageCalculations$$CalculateTrenchReduction`) que la prediction — gate cible-porte-Trench + sous-branche
    IsTrench(attackerTile)+IsNeighbourOf + IndirectFire(0x3ed) — sur les positions REELLES de l'ECS/board.
    No-op sans board/positions (mods inchange). MEME `TRENCH_PCT`/`_TRENCH_IGNORED_PROFILES` (pas de fork)."""
    board = state.board          # toujours present (__slots__) ; None tant que le boardGraph n'est pas cale
    if board is None:
        return
    ea, et = state.get_entity(attacker_id), state.get_entity(target_id)
    pa = ea.get_component(PositionComponent) if ea is not None else None
    pt = et.get_component(PositionComponent) if et is not None else None
    if pa is None or pt is None:
        return
    tgt_eff = (state.effects.active_effects(target_id, unit_state_for_effects(state, target_id))
               if state.effects is not None else [])
    target_has_trench = any(getattr(e, "name", None) == "Trench" for e in tgt_eff)   # HasEffect(cible, Trench 0x423)
    sc = ea.get_component(StatsComponent) if ea is not None else None
    att_traits = (getattr(sc.ctx, "traits", None) or ()) if sc is not None else ()
    eb = calculate_trench_reduction(
        (pa.col, pa.row), (pt.col, pt.row), target_has_trench,
        UnitTrait.IndirectFire.name in att_traits,                              # HasTrait(att, IndirectFire 0x3ed)
        bool(damage_profile) and damage_profile in _TRENCH_IGNORED_PROFILES,    # IgnoreTrenchReduction
        # #449-r2-r4-r4 : LU de la BC de cette bataille (`+0x2c`), plus de la seed figee a
        # l'import. `abs()` conserve : la config native est un pourcentage NEGATIF, et le port
        # passe la MAGNITUDE a un `PercentDecrease` (le signe est porte par le kind).
        board, abs(resolve_damage_field("trench_reduction_percentage", state=state)))
    if eb is not None:
        add_modifier(mods, eb)


def ice_crit_damage_addition(state: State, attacker_id: int, target_id: int, ctx) -> int:
    """#45f — `IdunBattle.Entities.Effects.IceEffect$$CreateEffectDamageBonusForAttack` : bonus crit-sur-Ice.

    L'Ice (effet de TUILE 0x11) contribue au degat d'attaque via la famille PARTAGEE
    `CreateEffectDamageBonusForAttack` -> struct `EffectBonus` (il2cpp : trigger@+0x10,
    multiplicator@+0x18, ADDITION@+0x20, subtraction/minimum/override/reset/sources/abilityOrEffect)
    collectee par `IdunBattle.Entities.Effects.BaseEffect$$DamageBonusForAttack` et consommee par le per-coup partage
    (`IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` / CBDWAM IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers). L'Ice ne remplit QUE le canal ADDITION :
        trigger  = IdunBattleLogic.Entities.DSLFactory$$AttackDamageIsCritical
                 & AreEqual(Units(occupant des tuiles de l'effet), target@0x178)
                 & op_LogicalNot(HasTrait(target, 0x19=Immune))
        addition = PercentageOf(StatAmount(attacker@0x160, 10=CRIT_DAMAGE), EffectConfig(5))
    avec `EffectConfig(5)` = `IceCritDmgBonusPct` (section Effect de la BC, =25).

    Evaluation offline PER-ATTAQUE : les gates occupant-Ice / Immune sont stables pendant l'attaque ;
    le gate `AttackDamageIsCritical` est per-COUP (le ctx AbilityEntities d'`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`
    porte isCritical) -> l'appelant n'ajoute ce flat qu'aux coups CRITIQUES, meme position pipeline
    que le crit flat (PRE-reduce / post-spread pre-percage, #75). MESURE live (probe_45f_gfa_elevation
    --case crit : cc=100/cd=700 forces, cible gelee par GreatFrostAxe, board plat) : delta natif =
    +175 sur CHAQUE coup crit — 4/4 bit-exact apres port. Rend 0 si : pas de
    board/effets, cible pas sur une tuile Ice ACTIVE, cible Immune, ou CRIT_DAMAGE attaquant = 0
    (le cas spaceWulfen cc=0/cd=0 — d'ou la « contradiction » historique du case-220 : cette formule
    n'a JAMAIS ete la source du residu x1.5, qui etait le bonus d'ELEVATION manquant du vecteur
    ability, cf. `apply_elevation_bonus`)."""
    board = state.board
    if board is None or state.effects is None or ctx is None:
        return 0
    et = state.get_entity(target_id)
    pt = et.get_component(PositionComponent) if et is not None else None
    if pt is None:
        return 0
    tid = board.id_at(pt.col, pt.row)
    if tid is None:
        return 0
    # AreEqual(occupant tuile-Ice, target) == « la cible occupe une tuile a effet Ice ACTIF »
    # (meme lecture tile-effects que LordOfTempests/_positional_att_ctx : state.effects.by_unit[tile_id]).
    if not any((getattr(x, "effect_type", None) == int(EffectType.Ice) and not x.consumed)
               for x in state.effects.by_unit.get(int(tid), [])):
        return 0
    if UnitTrait.Immune.name in target_trait_names(state, target_id):   # !HasTrait(target, 0x19=Immune)
        return 0
    cd = int(ctx.stat(StatType.CRIT_DAMAGE) or 0)          # StatAmount(attacker, 10) = GetStat(10)
    if cd <= 0:
        return 0
    pct = bc_effect_config("IceCritDmgBonusPct", 25) or 0   # EffectConfig(5)
    # `PercentageOf(..., roundingRule = 0)` -- le 4e argument est ECRIT `0` par
    # `IdunBattle.Entities.Effects.IceEffect$$CreateEffectDamageBonusForAttack`, et
    # `IdunBattle.DSL.AAmountFormula$$RoundFix64Result` le lit ainsi (decompile `rnca9r7q6c`) :
    # `1` = `Fix64.Ceiling`, `2` = `Fix64.Floor`, **tout le reste** = `Fix64.Round`. La regle 0
    # est donc ROUND (demi-vers-le-PAIR), PAS floor.
    #
    # ⚠ POURQUOI LE FLOOR A TENU SI LONGTEMPS -- la mesure qui l'attestait ne pouvait pas le
    # departager : `probe_45f --case crit` force `cd = 700`, et `700 x 25 / 100 = 175.0` n'a
    # AUCUNE partie fractionnaire ; floor et round y rendent le MEME 175, sur 4 coups sur 4. Un
    # accord en regime degenere. Le temoin discriminant est venu du snowball `LordOfTempests`
    # (#883) : `cd = 2727` -> `681.75`, ou floor rend 681 et le natif 682 -- l'ecart se propage
    # en +1 sur les DEUX bornes crit (`3530 x 0.8` et `x 1.2` sont tous deux entiers), donc +1
    # par coup CRITIQUE et 0 sur les autres. C'est exactement la signature mesuree live :
    # port `[5197, 4128, 1200]` contre natif `[5198, 4129, 1200]`, crits `[True, True, False]`.
    #
    # `CalculateInternal` normalise d'abord le pourcentage puis arrondit le produit a 2 decimales
    # (`Round(v x 100, 0) / 100`) avant `RoundFix64Result` : sur des entrees ENTIERES `cd` et
    # `pct`, `cd x pct / 100` a au plus 2 decimales, donc ces deux etages sont des no-op et la
    # chaine se reduit a l'arrondi final. Le `Fraction` le modelise EXACTEMENT.
    # Foyer d'arrondi PARTAGE (`engine/dsl/base.py`), jamais un round local.
    return _round_fix64(Fraction(cd * pct, 100), 0)


def build_hits_board(state: State, att_id: int, tgt_id: int,
                     attack_pos, t_pos, is_melee: Optional[bool],
                     trigger_ability_type: Optional[int] = None):
    """Bâtit `(board, aura_sources, target_effects)` pour `attack_hits_with_modifiers` depuis l'ECS
    (positions/teams/effets REELS). `board` = {att_id, tgt_id, attack_pos, t_pos, tgt_team, is_melee,
    pos_by_id, team_by_id} (base_hits posé par la Formule) ; `aura_sources` = [(owner_id, pos, team, effets)]
    des unités != cible (porteurs d'auras de coups type BigTarget) ; `target_effects` = effets actifs de la
    cible (LightCover/Parry). Identité = **entity_id**, team = **OwnerComponent.team** (instance-safe).

    ⚠ `vid_by_id` EST DE RETOUR (#1018), et la phrase qu'il remplace disait vrai sur son propre axe :
    « `visual_id` ne distinguerait pas 2 instances du même type en miroir » vise l'usage de
    `visual_id` comme **IDENTITÉ**, et cet usage-là reste proscrit — l'identité est l'`entity_id`,
    partout. Ce champ sert l'usage INVERSE, un **prédicat de TYPE** : le nœud
    `IdunBattleLogic.Entities.DSLSelectors$$UnitsWithIds` filtre par
    `IdunBattle.Entities.UnitExtensions$$HasUnitId(unit, id)` =
    `GetUnitIdWithoutRarity(GetUnitId(unit)) == id`, où deux instances du même type DOIVENT être
    indiscernables. Aucun consommateur ne compare deux unités entre elles par ce champ.
    `hp_by_id`/`hpmax_by_id` (#1018) portent la santé LUE : sans elle,
    `engine/dsl/base.py::_is_alive` classe MORT tout dict d'unité et les sélecteurs d'occupation
    rendent l'ensemble VIDE, sans erreur."""
    pos_by_id: dict = {}
    team_by_id: dict = {}
    # #372 — substrat d'ENTITÉ du canal AURA de COUPS : `UnitTurnsStarted` = `GetStat(., 0xc)` et
    # le lien `ParentComponent` (summoner), lus sur les MÊMES unités VIVANTES que les auras.
    turns_started_by_id: dict = {}
    parent_by_id: dict = {}
    # `HasUsedActiveAbilityThisTurn` (`HasFlag(unit, 2)`) -- substrat du selecteur d'aura de
    # `LegendaryCommander_ExtraHits` (#419-r1-tr9-r4-r1-r2-r1), sur les MEMES unites vivantes.
    used_active_by_id: dict = {}
    # `UnitComponent.visual_id` par unite vivante -- substrat du noeud `UnitsWithIds` (#1018).
    vid_by_id: dict = {}
    # SANTE par unite vivante (#1018) -- `HealthComponent.hp` / `.hp_max`, MEME source que le dict
    # d'unite DSL du runner (`runner/abilities/behaviours/context.py::_unit_dict`). Sans elle,
    # `engine/dsl/base.py::_is_alive` classe l'unite MORTE (sa degradation NOMMEE : << `hpMax`
    # ABSENT du dict -> MORT >>) et TOUT selecteur d'occupation rend l'ensemble VIDE, sans erreur.
    # Mesure #1018 : `AdjacentUnits` rendait `[]` sur un board pourtant peuple.
    hp_by_id: dict = {}
    hpmax_by_id: dict = {}
    aura_sources = []
    target_effects: list = []
    for uid, e in state.entities.items():
        # VIVANTS SEULEMENT (#57m) : le board natif = OCCUPATION DE TUILE (`IdunBattleLogic.Entities.DSLFactory$$AdjacentUnits`
        # = `Units(AdjacentTiles(.)) - .`) — un mort (alive=False, reste dans state.entities) n'est
        # plus sur le board : ni compte GetStuckIn, ni porteur d'aura. Cible conservee (vivante par
        # construction d'une attaque).
        _uc = e.get_component(UnitComponent)
        if uid != tgt_id and _uc is not None and not _uc.alive:
            continue
        pc = e.get_component(PositionComponent)
        oc = e.get_component(OwnerComponent)
        if pc is not None:
            pos_by_id[uid] = (pc.col, pc.row)
        if oc is not None:
            team_by_id[uid] = oc.team
        if _uc is not None:
            parent_by_id[uid] = getattr(_uc, "parent_id", None)
            used_active_by_id[uid] = unit_has_used_active_ability(state, uid)
            vid_by_id[uid] = getattr(_uc, "visual_id", None)
        _hc = e.get_component(HealthComponent)
        if _hc is not None:
            hp_by_id[uid] = _hc.hp
            hpmax_by_id[uid] = _hc.hp_max
        _sc = e.get_component(StatsComponent)
        if _sc is not None:
            turns_started_by_id[uid] = int(_sc.ctx.stat(StatType.TURNS_STARTED) or 0)
        effs = (state.effects.active_effects(uid, unit_state_for_effects(state, uid))
                if state.effects is not None else [])
        if uid == tgt_id:
            target_effects = effs
        else:
            aura_sources.append((uid, pos_by_id.get(uid), team_by_id.get(uid), effs))
    # Gates CIBLE du canal COUPS, memes deux entrees que le canal DEGAT (`attacker_modifiers`) :
    # `HasEffect(Target, <EffectType>, Both)` re-evalue (marqueurs non materialises) + grande-alliance
    # de la cible (`HasTrait(Target, 0x7ea = Chaos)` de `FearedInterrogator_Owner.CreateEffectHitsBonusForAttack`).
    board = {"att_id": att_id, "tgt_id": tgt_id, "attack_pos": attack_pos, "t_pos": t_pos,
             "tgt_team": team_by_id.get(tgt_id), "is_melee": is_melee,
             "pos_by_id": pos_by_id, "team_by_id": team_by_id,
             # #372 — substrat du canal AURA de COUPS (`aura_hits_bonus_for_attack`), consommateur
             # `DefenderOfTheGreaterGood_ExtraHits` (1183 / 1307) :
             #  * `att_faction` = `UnitsFromFaction(SurroundingFriends(owner, 2), 9 = Tau)` du
             #    sélecteur `DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector` — MÊME
             #    source (`FactionId` du gameconfig) que le canal DÉGÂT (`attacker_modifiers`) ;
             #  * `turns_started_by_id` / `parent_by_id` = le nœud
             #    `UnitTurnsStarted(If(AmountIsGreaterThanZero(Parent(src)), Parent(src), src))`
             #    (= `GetStat(., 0xc)` du PORTEUR, ou de son summoner pour un summon) ;
             #  * `rng` = `Maybe(chance)` — en COMBAT `CanUseRandom` est VRAI, le natif TIRE
             #    (`DisallowablePseudoRNG$$NextBool`) et ce tirage CONSOMME un genrand.
             "att_faction": (_unit_gameconfig(state, att_id) or {}).get("FactionId"),
             # `HasTrait(Caster@DSLSelectors+0x48, …)` sur le canal COUPS -- MEME resolveur
             # (`target_trait_names`) et MEME cle que le canal DEGAT (`attacker_modifiers`), pose ICI
             # parce que `build_hits_board` est la facade COMBAT PARTAGEE des deux vecteurs
             # d'attaque. Consommateur : `TerrorsLament_HitReduction`, dont le trigger porte
             # `NOT HasTrait(Caster, 0x19 = UnitTrait.Immune)`.
             "att_traits": target_trait_names(state, att_id),
             "turns_started_by_id": turns_started_by_id,
             "parent_by_id": parent_by_id,
             "rng": state.rng,
             "marked_effect_types": marked_effect_types_for_target(state, att_id, tgt_id),
             "tgt_grand_alliance": grand_alliance_of(state, tgt_id),
             # `vid_by_id` (#1018) -- l'id d'unite que `IdunBattle.Entities.UnitExtensions$$HasUnitId`
             # compare (`GetUnitIdWithoutRarity(GetUnitId(unit))`), donc le substrat du noeud
             # `IdunBattleLogic.Entities.DSLSelectors$$UnitsWithIds`. MEME source et MEME nom de champ
             # que le dict d'unite DSL du runner (`runner/abilities/behaviours/context.py::_unit_dict`
             # -> `UnitComponent.visual_id`), sur les MEMES unites VIVANTES que `pos_by_id`.
             # Consommateur : `HungeringSwarm_ExtraHits` (1041).
             "vid_by_id": vid_by_id,
             "hp_by_id": hp_by_id,
             "hpmax_by_id": hpmax_by_id,
             # `IsCharging` (case-ischarging-hits) sur le canal COUPS : MEME cle et MEME foyer que le canal
             # DEGAT (`attacker_modifiers`), pose ICI parce que `build_hits_board` est la facade
             # COMBAT PARTAGEE des DEUX vecteurs d'attaque (normale `damage_ops/normal.py` et
             # ability famille ATTACK `damage_ops/ability.py`) -- un seul point de calcul, pas un
             # par call-site. Consommateur : `SagaOfTheWarriorBorn_Owner` (1223).
             "is_charging": battle_query_is_charging(state, att_id, tgt_id),
             # `HasFlag(Owner, 0 = UnitFlag.Moved)` sur le canal COUPS (case-366-r1) -- MEME store et
             # MEME lecteur que le canal DEGAT (`attacker_modifiers` -> `unit_has_moved`). Pose ICI
             # parce que `build_hits_board` est la facade COMBAT PARTAGEE des deux vecteurs
             # d'attaque. Consommateur : `InescapableAccuracy_overrideHits` (1117), dont l'
             # `ActiveCondition` est rendue une seconde fois dans le canal (cf. sa docstring).
             "has_moved": unit_has_moved(state, att_id),
             # `AbilityEntities+0x98` (`triggerAbilityOrEffect`) sur le canal COUPS
             # (case-366-r1-blockhits-purgeresponse) -- MEME champ natif et MEME nom de cle que sur
             # le canal DEGAT (`attacker_modifiers`, #47). `DamagePrediction$$GetAttackHits` le
             # recopie du contexte d'attaque dans l'`AbilityEntities` qu'il passe a CHAQUE effet, et
             # `IdunBattleLogic.Entities.AbilityTypeSelector.TriggeringAbilitySelector$$Select` le
             # lit a cet offset. Consommateur : `PurgeResponse` (1538),
             # `TriggeringAbilityIs(EffectType 1009 Overwatch_AutoAttack)`.
             # None (attaque normale ordinaire / attaque d'ability) -> le noeud est FAUX, exactement
             # comme le `Nullable` vide du natif (`TriggeringAbilityIsNoneTrigger`).
             "trigger_ability_type": (None if trigger_ability_type is None
                                      else int(trigger_ability_type)),
             # `HasUsedActiveAbilityThisTurn(Subject@0x68)` du `Filter` de
             # `IdunBattle.Entities.Effects.Loki.ALegendaryCommander_BaseEffect$$CreateTargetSelector`
             # -- MEME store (`UnitFlagsComponent`, flag 2 `ActiveAbilityUsed`) et MEME foyer que le
             # gate d'entree du generateur d'abilities de l'IA. Table par unite VIVANTE, montee ici
             # parce que le selecteur d'aura doit la parcourir (il ne connait qu'un board).
             "used_active_by_id": used_active_by_id,
             # Accesseur au sac `PersistentDataComponent` d'une unite ARBITRAIRE (le natif lit celui
             # de l'`EffectSource`, pas celui de l'attaquant) -- meme tri-etat que
             # `entities.triggers.IsInPersistentDataList` : `None` hors runner -> liste vide, ce que
             # rend aussi `TryGetPersistDataList` sur une cle absente.
             "persistent_data_list": _persistent_data_list_reader(state),
             # #1073 -- les DEUX disjoints de `SynapticInsight_ExtraHitsEffect$$
             # CreateEffectHitsBonusForAttack`, sur le canal COUPS :
             #  * `Any(AdjacentFriends(Owner@+0x30, Target@+0x60, unique), HasFaction(It@+0x68,
             #    Tyranids, 3))` -- l'ARBRE vit dans la classe d'effet (doctrine #149) et
             #    `runner/components.py` lui donne son `AbilityEntities`. TRI-ETAT : `None` = porteur
             #    ou cible sans equipe/tuile -> le disjoint se FERME cote effet.
             #  * `IsInTeamSynapseRange(Target@+0x60, Owner@+0x30)` -- MEME cle et MEME foyer que le
             #    canal DEGAT (`attacker_modifiers`, #1011) : `_team_synapse_positions` est la
             #    POSITION des emetteurs `Synapse` par equipe, la comparaison de distance restant
             #    chez le consommateur (`norn_crown._in_team_synapse_range`).
             _SI_CTX_ADJACENT_TYRANID: synaptic_insight_adjacent_tyranid(state, att_id, tgt_id),
             _NORN_CTX_SYNAPSE: _team_synapse_positions(state)}
    return board, aura_sources, target_effects


def _persistent_data_list_reader(state: State):
    """`(unit_id, composite_key) -> list` sur le `PersistentDataComponent` de l'unite demandee.

    Mirror de l'acces natif `entity.GetComponent<PersistentDataComponent>().TryGetPersistDataList(
    GetPersistentDataId(abilityOrEffect), key)` (`IsInPersistentDataListTrigger$$ShouldTrigger`).
    Composant/entite absents -> `()`, exactement le `?? new List<T>()` du natif."""

    def _read(unit_id, key):
        if unit_id is None:
            return ()
        e = state.get_entity(int(unit_id))
        c = e.get_component(PersistentDataComponent) if e is not None else None
        if c is None:
            return ()
        return c.try_get_persist_data_list(key) or ()
    return _read


def getstuckin_combat_chance(state: State, att_id: int, tgt_id: int,
                             attack_pos, t_pos, board) -> Optional[int]:
    """Chance du coup bonus GetStuckIn en COMBAT (#62c), ou None si GetStuckIn INACTIF pour cet
    attaquant/cible. Mirror `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$GetBonusHitChance` + gate trigger `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger`
    (`On(8) & IsOdd & OwnerIsCaster & !(MinDistance > 2)`).

    Actif ssi l'attaquant PORTE GetStuckIn ET `min_distance(caster, target) <= 2` -- distance HEX,
    MEME primitive que la face PREDICTION (`GetStuckInTrait.as_attacker_bonus_hits`) : les deux faces
    du meme gate natif partagent le meme mirror. Chance = `If(orks_adj(cible) >= 2 OU
    amis_adj(caster) >= 4, ConfigConst(0x33)=100, ConfigConst(0x2a)=30)`.

    GAP DOCUMENTE (case-62c point 4) : la branche `orks_adj(cible) >= 2` (faction Orks=5) N'EST PAS
    calculee offline -- le runner ne porte PAS la FACTION (retiree de `build_hits_board` : `visual_id` ne
    distingue pas 2 instances du meme type en miroir). Seul `amis_adj(caster) >= 4` (team via
    OwnerComponent, adjacence via le service partage `are_tiles_adjacent`) est evalue -> en 1v1 = 30
    (la branche 100 n'est de toute facon pas confirmee live)."""
    if attack_pos is None or t_pos is None:
        return None
    att = state.get_entity(att_id)
    sc = att.get_component(StatsComponent) if att is not None else None
    if sc is None:
        return None
    if not any(isinstance(t, GetStuckInTrait) for t in sc.ctx.trait_objects()):
        return None
    if min_distance(attack_pos, t_pos) > 2:      # !(MinDistance > 2) = cible a <=2 hex (trigger structurel)
        return None
    oc = att.get_component(OwnerComponent)
    caster_team = oc.team if oc is not None else None
    friends_adj = 0
    if caster_team is not None:
        for uid, e in state.entities.items():
            if uid == att_id:
                continue
            oc2 = e.get_component(OwnerComponent)
            pc2 = e.get_component(PositionComponent)
            if oc2 is None or pc2 is None or oc2.team != caster_team:
                continue
            hc2 = e.get_component(HealthComponent)
            if hc2 is not None and hc2.hp is not None and hc2.hp <= 0:
                continue                         # unite morte -> non comptee
            if are_tiles_adjacent(attack_pos, (pc2.col, pc2.row), board):
                friends_adj += 1
    # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$GetBonusHitChance` =
    # `If(<4+ allies adjacents>, ConfigConst(0x33), ConfigConst(0x2a))` -> les DEUX branches rendent une
    # variable de trait, pas un litteral. Ecrire 100/30 en dur coincidait avec la config du jour ; au
    # premier reequilibrage le port aurait derive EN SILENCE (trouve pendant le lot D, #110).
    key = "getStuckInChance_2" if friends_adj >= 4 else "getStuckInChance"     # 0x33 : 0x2a
    chance = trait_var("GetStuckIn", key)
    assert chance is not None, f"traitVariables.{key} absent du gameconfig (trait GetStuckIn)"
    return int(chance)


def normal_attack_per_hit_range(state: State, unit_id: int) -> Optional[dict]:
    """Plage BRUTE (pré-armure) d'UN coup d'attaque normale de l'unité, calculée depuis
    l'ECS (StatsComponent + effets actifs). Renvoie `{min, max, base, effects, hasMods}`
    ou None si l'unité n'a pas de StatsComponent (stats non chargées).

    `min/max` = ce que `HitDamage.GetDamage` tirera (avant réduction perçage/armure)."""
    e = state.get_entity(unit_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return None
    ctx = sc.ctx
    active = (state.effects.active_effects(unit_id, unit_state_for_effects(state, unit_id))
              if state.effects is not None else [])
    mods = build_attacker_modifiers_from_effects(active)
    # armure=0 & perçage=100 → réduction = identité ⇒ la plage retournée est BRUTE (pré-armure),
    # = ce que `aiPredict` (pré-armure) renvoie par coup ; les MODIFIERS d'effet sont inclus.
    res = get_attack_prediction(
        target_current_health=_BIG_HP, initial_damage=ctx.stat(StatType.ATTACK), hits=1,
        profile_type=ctx.damage_type, armor=0, pierce_pct=100, mods=mods,
        attacker_effects=active)   # #202 : max-out evalue DANS predict_attack_raw
    r = res.accurate_health_damage
    return {
        "min": r.min, "max": r.max, "base": ctx.stat(StatType.ATTACK),
        "effects": [getattr(ef, "name", None) for ef in active],
        "hasMods": bool(mods is not None and (mods.pct_list or getattr(mods, "additive", 0))),
    }
