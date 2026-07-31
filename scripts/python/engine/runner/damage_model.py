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

from typing import Optional, Tuple

from .state import State
from .components import (StatsComponent, HealthComponent, OwnerComponent, PositionComponent,
                         UnitComponent, unit_has_moved, unit_has_teleported,
                         unit_tiles_moved_this_turn, unit_state_for_effects)
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
)
from ..entities.traits.combat import GetStuckInTrait, min_distance
from ..entities.effects.magnitude import trait_var

_BIG_HP = 1 << 30          # santé cible « infinie » → scenario sans overkill/cap


def select_weapon(ctx, dist: Optional[int]):
    """Arme de l'attaque normale par PORTÉE — DÉLÈGUE au service PARTAGÉ
    `battle_query.get_attack_weapon_for_default_normal_attack` (foyer natif BattleQuery ; MÊME port que
    la prédiction). `dist` = distance hex du runner (1=adjacent via `board.neighbours`, 2=tir) → is_adjacent.
    Renvoie le dict d'arme gameconfig (ou None)."""
    w, _ranged = get_attack_weapon_for_default_normal_attack(
        ctx.visual_id, is_adjacent=(dist is not None and dist <= 1), prefer_hits=ctx.normal_hits, dist=dist)
    return w


def select_weapon_pierce(ctx, dist: Optional[int], effect_bonus: int = 0) -> Tuple[int, bool, int]:
    """Arme + perçage par PORTÉE — DÉLÈGUE au service PARTAGÉ `battle_query.select_weapon_pierce`
    (un service natif = UN port, prédiction ET combat l'appellent). `dist` hex (1=adjacent) → is_adjacent.
    Renvoie `(pierce, is_ranged, whits)` (le profil est fourni séparément par `select_weapon`).
    `effect_bonus` = Σ des `EffectBonus` de perçage de l'attaquant (`BaseEffect$$PiercingBonusForAttack`),
    sommé DANS le clamp natif unique (cf. la docstring du service). Défaut 0 = inchangé."""
    pierce, is_ranged, whits, _prof = _bq_select_weapon_pierce(ctx, dist is not None and dist <= 1, dist,
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
        if oc is None or pc is None or oc.team != aoc.team:
            continue                                      # Friends du porteur = même équipe que l'attaquant
        hc = ent.get_component(HealthComponent)
        if hc is not None and hc.hp is not None and hc.hp <= 0:
            continue                                      # porteur mort -> aura éteinte
        effs = state.effects.active_effects(uid, unit_state_for_effects(state, uid))
        if effs:
            carriers.append((uid, (pc.col, pc.row), oc.team, effs))
    if not carriers:
        return
    from ..services.damage_modifiers import add_modifier
    is_melee = (not is_ranged) if is_ranged is not None else None
    att_gu = _unit_gameconfig(state, att_id) or {}
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
           "tgt_team": _unit_team(state, target_id)}
    for eb in aura_attack_damage_bonus_from_allies(carriers, ctx):
        add_modifier(mods, eb)


def _unit_pos(state: State, unit_id: Optional[int]):
    """`(col,row)` de l'unité, ou None (unité absente / sans position — ex. MoW hors-plateau)."""
    if unit_id is None:
        return None
    e = state.get_entity(int(unit_id))
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _unit_team(state: State, unit_id: Optional[int]):
    """Équipe de l'unité, ou None."""
    if unit_id is None:
        return None
    e = state.get_entity(int(unit_id))
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


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
    from ..utilities.tile import terrain_tile_effects            # lazy : évite cycle runner<->utilities
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
    from ..services.static_battle_rules import is_tile_status_effect
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
    produirait (`battle_query.newly_adjacent_ids`)."""
    from ..battle_query import is_charging as _bq_is_charging
    from .components import charged_unit_ids

    def _pos(uid):
        e = state.get_entity(uid)
        pc = e.get_component(PositionComponent) if e is not None else None
        return (pc.col, pc.row) if pc is not None else None

    return _bq_is_charging(_pos(caster_id), _pos(target_id), target_id,
                           charged_unit_ids(state, int(caster_id)))


def attacker_modifiers(state: State, unit_id: int, hp: Optional[int], is_ranged: Optional[bool] = None,
                       target_traits=None, target_id: Optional[int] = None,
                       is_normal_attack: bool = True, damage_profile: Optional[str] = None,
                       trigger_ability_type: Optional[int] = None,
                       is_overwatch: bool = False):
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
        from ..entities.effects.loki.dark_angels_passives import grand_alliance_of
        att_ctx = dict(att_ctx or {})
        att_ctx["marked_effect_types"] = marked_effect_types_for_target(state, unit_id, target_id)
        att_ctx["tgt_grand_alliance"] = grand_alliance_of(state, target_id)
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
            att_ctx["team_by_id"] = {int(uid): oc.team
                                     for uid, e in state.entities.items()
                                     for oc in (e.get_component(OwnerComponent),) if oc is not None}
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
        if oc is None or pc is None:
            continue
        hc = e.get_component(HealthComponent)
        if hc is not None and hc.hp is not None and hc.hp <= 0:
            continue                                        # porteur mort -> aura éteinte
        ceff = (state.effects.active_effects(uid, unit_state_for_effects(state, uid))
                if state.effects is not None else [])
        if ceff:
            carriers.append((uid, (pc.col, pc.row), oc.team, ceff))
    if carriers and tp is not None:
        from ..services.damage_modifiers import add_modifier
        for eb in aura_defense_damage_malus_from_units(
                carriers, {"tgt_id": unit_id, "t_pos": tp,
                           "tgt_team": toc.team if toc is not None else None,
                           "tgt_traits": target_trait_names(state, unit_id),
                           "damage_profile": damage_profile}):
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
    from .components import PositionComponent
    from ..services.damage_modifiers import (add_modifier, calculate_elevation_bonus_modifier,
                                             ELEVATION_BONUS_PCT, EFFECT_NO_ELEVATION)
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
    eb = calculate_elevation_bonus_modifier(a_elev, t_elev, ELEVATION_BONUS_PCT,
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
    from .components import PositionComponent
    from ..services.damage_modifiers import (add_modifier, calculate_trench_reduction,
                                             TRENCH_PCT, _TRENCH_IGNORED_PROFILES)
    from ..entities.traits.unit_trait import UnitTrait
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
        board, TRENCH_PCT)
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
    +175 = floor(700 x 25 / 100) sur CHAQUE coup crit — 4/4 bit-exact apres port. Rend 0 si : pas de
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
    from ..entities.effect_type import EffectType
    from ..entities.traits.unit_trait import UnitTrait
    if not any((getattr(x, "effect_type", None) == int(EffectType.Ice) and not x.consumed)
               for x in state.effects.by_unit.get(int(tid), [])):
        return 0
    if UnitTrait.Immune.name in target_trait_names(state, target_id):   # !HasTrait(target, 0x19=Immune)
        return 0
    cd = int(ctx.stat(StatType.CRIT_DAMAGE) or 0)          # StatAmount(attacker, 10) = GetStat(10)
    if cd <= 0:
        return 0
    from ..entities.effects.magnitude import bc_effect_config
    pct = bc_effect_config("IceCritDmgBonusPct", 25) or 0   # EffectConfig(5)
    return (cd * pct) // 100                                # PercentageOf -> Fix64 -> floor int (+175 mesure)


def build_hits_board(state: State, att_id: int, tgt_id: int,
                     attack_pos, t_pos, is_melee: Optional[bool]):
    """Bâtit `(board, aura_sources, target_effects)` pour `attack_hits_with_modifiers` depuis l'ECS
    (positions/teams/effets REELS). `board` = {att_id, tgt_id, attack_pos, t_pos, tgt_team, is_melee,
    pos_by_id, team_by_id} (base_hits posé par la Formule) ; `aura_sources` = [(owner_id, pos, team, effets)]
    des unités != cible (porteurs d'auras de coups type BigTarget) ; `target_effects` = effets actifs de la
    cible (LightCover/Parry). Identité = **entity_id**, team = **OwnerComponent.team** (instance-safe). PAS
    de `faction_of`/visual_id : le comptage par faction de GetStuckIn est retiré, aucun consommateur ne le
    lit — et `visual_id` ne distinguerait pas 2 instances du même type en miroir (danger connu)."""
    from .components import PositionComponent, OwnerComponent, UnitComponent
    pos_by_id: dict = {}
    team_by_id: dict = {}
    # #372 — substrat d'ENTITÉ du canal AURA de COUPS : `UnitTurnsStarted` = `GetStat(., 0xc)` et
    # le lien `ParentComponent` (summoner), lus sur les MÊMES unités VIVANTES que les auras.
    turns_started_by_id: dict = {}
    parent_by_id: dict = {}
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
    from ..entities.effects.loki.dark_angels_passives import grand_alliance_of
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
             "turns_started_by_id": turns_started_by_id,
             "parent_by_id": parent_by_id,
             "rng": state.rng,
             "marked_effect_types": marked_effect_types_for_target(state, att_id, tgt_id),
             "tgt_grand_alliance": grand_alliance_of(state, tgt_id),
             # `IsCharging` (case-ischarging-hits) sur le canal COUPS : MEME cle et MEME foyer que le canal
             # DEGAT (`attacker_modifiers`), pose ICI parce que `build_hits_board` est la facade
             # COMBAT PARTAGEE des DEUX vecteurs d'attaque (normale `damage_ops/normal.py` et
             # ability famille ATTACK `damage_ops/ability.py`) -- un seul point de calcul, pas un
             # par call-site. Consommateur : `SagaOfTheWarriorBorn_Owner` (1223).
             "is_charging": battle_query_is_charging(state, att_id, tgt_id)}
    return board, aura_sources, target_effects


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
