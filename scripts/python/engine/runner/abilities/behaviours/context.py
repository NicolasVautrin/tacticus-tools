"""Socle du contexte DSL runner-couple : `entities_from_state` (construit le `DslContext` natif
`AbilityEntities` depuis le `State` runner) + `LiveUnit` (vue live-by-ref d'une unite). Consomme par
TOUTES les feuilles du package `behaviours`. cf. docs/rl/dsl-effect-nodes.md,
docs/rl/dsl-live-context-substrate.md."""
from __future__ import annotations

from .... import battle_query as _bq
from ....dsl.base import DslContext
from ...components import (OwnerComponent, PositionComponent, UnitComponent, StatsComponent,
                          HealthComponent, get_unit_feet)
from ....entities.traits.unit_trait import (UnitTrait, has_trait, grand_alliance_trait_name,
                                            entity_trait_names)
from ....entities.effects import effect_stat_mod_key
from ....entities.stats import StatPart as _SP, StatType as _ST
from ....entities.stats import StatType as _ST
from ....utilities.tile import sort_tiles_by_utility as _stbu, runner_tile_leaf_ctx
from ...components import UnitComponent as _UC
from ...components import UnitFlagsComponent
from ...components import charged_unit_ids
from ...components import persistent_data as _pd
from ...components import persistent_data_list as _pdl
from ...components import previous_tiles as _pt
from ...operations.ability_reset import entity_can_have_active_ability_reset


# Trait d'ALLIANCE derive de la GrandAlliance : la resolution CANONIQUE vit desormais dans
# `entities/traits/unit_trait.py` (le module d'autorite du mapping id <-> nom), parce qu'elle est
# consommee par DEUX substrats — le contexte DSL runner (ici) et le `ctx` des feuilles Tile(7)
# (`utilities/tile.py::tile_leaf_ctx`). Un 2e mapping "Imperial/Xenos/Chaos -> 26/1006/2026" aurait
# ete un fork de port. Alias conserve : il NOMME la source (cite par `abilities/ultramarines.py` et
# par les fiches de test RevitalizingMalignancy / CombatRestoratives) ; depuis #264 le substrat de
# traits de ce module passe par `entity_trait_names`, qui l'applique lui-meme.
_grand_alliance_trait = grand_alliance_trait_name


def _unit_dict(state, eid: int, entity=None) -> dict | None:
    """Dict d'unite {id, team, player, pos, alive, hp, visualId, _traits} lu du `State` runner — la forme
    `unit` que consomment les selecteurs DSL. `entity` optionnel (evite un `get_entity` redondant)."""
    e = entity if entity is not None else state.get_entity(eid)
    if e is None:
        return None
    oc = e.get_component(OwnerComponent)
    pc = e.get_component(PositionComponent)
    uc = e.get_component(UnitComponent)
    sc = e.get_component(StatsComponent)
    hc = e.get_component(HealthComponent)
    # REPLI GAMECONFIG quand l'unite n'a pas de `StatsComponent` — cas d'un CADAVRE : `_load_stats_and_
    # effects` ne pose le composant que pour les entrees de `combatSnapshot.units`, et une unite MORTE en
    # est absente ; son dict sortait donc SANS trait, alors que `decisionView` la garde et que le natif,
    # lui, teste les flags d'une entite morte (`UnitsWithFlagSelector` sur `AllDeadUnitsSelector`).
    # MESURE (#226, Foehammer) : `Count(UnitsWithTrait(AllDeadOrResurrectedUnits, Hero))` rendait 0 avec
    # un heros mort au sol -> bonus `extraDmg x deadHeroes` PERDU (live 2142 vs port 343). La source du
    # repli est EXACTEMENT celle du chemin vivant (`UnitContext.traits = gameconfig.unit(vis).traits`).
    # Le trait d'ALLIANCE (Imperial/Chaos/Xenos) fait partie du substrat : requis par le split
    # RevitalizingMalignancy (WithoutTrait Imperial / WithTrait Chaos) + l'exclusion Imperial de
    # CombatRestoratives. CONFIRME LIVE (case-220 : deathBlightbringer Chaos +6980, eldarRanger Xenos
    # +3490, adeptHospitaller Imperial +0). #264 : il vient desormais de `entity_trait_names` -- soit
    # de la MESURE live (`BC.Units[].Traits` la porte explicitement), soit, a defaut de mesure, de la
    # derivation `GrandAlliance$$GetTrait`. Ce site ne l'ajoute donc plus lui-meme : un DEUXIEME
    # ajout par-dessus une mesure re-introduirait exactement la reconstruction que #264 retire.
    # A defaut de mesure, `entity_trait_names(ctx, vis)` == l'ancien `set(ctx.traits) | {_ga}` et
    # `entity_trait_names(None, vis)` == l'ancien repli `_config_traits(vis) | {_ga}` -- bit pour bit.
    traits = set(entity_trait_names(sc.ctx if sc is not None else None,
                                    uc.visual_id if uc is not None else None))
    alive = uc.alive if uc is not None else True
    return {
        "id": eid,
        "team": oc.team if oc is not None else None,
        "player": oc.player if oc is not None else None,
        "pos": {"col": pc.col, "row": pc.row} if pc is not None else None,
        # EMPREINTE (#R30/#91) — `IdunBattle.Entities.EntityExtensions$$GetTiles` = les tuiles des
        # PIEDS, dans l'ordre des pieds. Toujours une LISTE (jamais None) : une unite mono-tuile
        # rend `[(col,row)]`, exactement ce que le natif rend pour un seul `UnitFoot`. C'est la
        # SEULE porte d'entree des selecteurs DSL sur « quelles tuiles cette unite occupe » ; sans
        # elle un `CanAddUnit` ne voyait qu'un tiers de l'empreinte d'un Galatian pose au sol.
        "feet": get_unit_feet(state, eid),
        "alive": alive,
        "hp": hc.hp if hc is not None else (1 if alive else 0),
        "visualId": uc.visual_id if uc is not None else None,
        # Lien PARENT (`ParentComponent` id @+0x10, live `Unit_Parent_Id`) : lu par le selecteur
        # `Parent` (`IdunBattle.Entities.Selectors.ParentSelector$$Select` ->
        # `IdunBattle.Entities.UnitExtensions$$GetParent`). None pour toute unite du roster initial.
        "parentId": getattr(uc, "parent_id", None) if uc is not None else None,
        # `ActorStatisticsComponent @+0x70` — lu par le noeud formule `LastHitDamageTakenLastTurn`
        # (`IdunBattle.Entities.Formulas.LastHitDamageTakenLastTurnFormula$$Calculate`). 0 par defaut.
        "lastHitDamageTakenLastTurn": (int(getattr(uc, "last_hit_damage_taken_last_turn", 0) or 0)
                                       if uc is not None else 0),
        "_traits": traits,
    }


# Champs MUTABLES d'une unite (re-lus du state a chaque acces par LiveUnit). Les autres (id/team/player/
# visualId/_traits) sont quasi-statiques -> servis depuis le snapshot seed.
_LIVE_KEYS = frozenset({"pos", "hp", "alive", "feet"})


class LiveUnit(dict):
    """Vue LIVE d'une unite pour le contexte RUNNER (mirror natif : `AbilityEntities` tient une REF
    d'entite @+0x40, position/PV re-derives A LA LECTURE -- jamais un snapshot ; cf.
    docs/rl/dsl-live-context-substrate.md, `IdunBattle.Entities.Abilities.AbilityEntities$$get_CasterPosition` / `UnitPosition..IdunBattle.Core.UnitPosition$$.ctor`).

    Sous-classe `dict` pour rester reconnue par les `isinstance(v, dict)` du DSL (`resolve_unit`/`_units_of`/
    helpers de `dsl/base.py`) et exposer les champs STATIQUES (id/team/player/visualId/_traits) via le
    snapshot seed (compat `**`/`.items()`/iteration). Les champs MUTABLES (`_LIVE_KEYS` = pos/hp/alive) sont
    RE-LUS du `state` a chaque `get`/`[]` -> une re-eval de predicat (ex. `IsAdjacent`) APRES une mutation
    (Move/degat/mort) voit l'etat COURANT. C'est CE qui permet a UN arbre DSL de rester correct a travers une
    mutation intra-arbre (Voie A, S-chantier).

    L'override `caster_pos` (mode `AbilityEntities+0x48`, decision balayee AI) reste applique par les
    SELECTEURS (`ctx.caster_pos or _pos(...)`), PAS ici : LiveUnit rend la position BRUTE live du `state`.
    Le chemin PREDICTION (`playbook/prediction.py`) construit toujours des dicts FIGES depuis sa scene
    hypothetique -> il n'utilise PAS LiveUnit (frozen-by-design)."""

    def __init__(self, state, eid: int, entity=None):
        self._state = state
        self._eid = eid
        # Ref d'entite STABLE (les composants mutent en place) = l'homologue de AbilityEntities+0x40.
        self._entity = entity if entity is not None else state.get_entity(eid)
        super().__init__(_unit_dict(state, eid, self._entity) or {"id": eid})

    def _live(self, key):
        d = _unit_dict(self._state, self._eid, self._entity)
        return (d or {}).get(key)

    def get(self, key, default=None):
        if key in _LIVE_KEYS:
            v = self._live(key)
            return v if v is not None else default
        return super().get(key, default)

    def __getitem__(self, key):
        if key in _LIVE_KEYS:
            v = self._live(key)
            if v is None:
                raise KeyError(key)
            return v
        return super().__getitem__(key)


def entities_from_state(state, caster_id: int, target_id: int | None = None,
                        actor_id: int | None = None) -> DslContext:
    """Construit l'`AbilityEntities` (= `DslContext`) lu par les selecteurs d'un behaviour, depuis le
    `State` runner : `units` = `LiveUnit` (vues live-by-ref, pos/hp/alive re-lus du `state` a chaque acces
    -> mirror `AbilityEntities+0x40` ; permet la re-eval de predicat post-mutation, Voie A), `caster`
    (`factory+0x160`, aussi `Self@0x148`
    pour un triggered Owner==Caster), `target` (cible principale = `factory+0x178`, lu par `Target()` —
    None si l'ability est sans cible ; sur un OnPreDeath = l'unite MOURANTE @0x178), `actor` (`factory+
    0x158` = ACTEUR/TUEUR de l'evenement, lu par `Actor()` — threade sur les behaviours de trigger type
    ActOfFaith accumulate ; None sinon), `board` (= `state.board`), `has_trait(unit, traitId)` (mirror
    `UnitExtensions.HasFlag`, via l'enum `UnitTrait` + le set de noms `ctx.traits`). `children=[]` =
    accumulateur de spawn FRAIS pour CE cast (mirror factory+0x148)."""
    units: list = []
    caster = None
    target = None
    actor = None
    for eid, e in state.entities.items():
        u = LiveUnit(state, eid, e)                   # vue LIVE (pos/hp/alive re-lus a chaque acces)
        units.append(u)
        if eid == caster_id:
            caster = u
        if target_id is not None and eid == target_id:
            target = u
        if actor_id is not None and eid == actor_id:
            actor = u

    # CASTER NON-UNITE (entite TUILE). `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`
    # resout son champ +0x50 (le caster) en UNE **entite**, pas forcement une unite : le DoT de tuile
    # (`IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour`) y passe
    # `Tiles(<occupant>)`, donc l'entite-TUILE. Cote port, une tuile ne vit que dans `EffectsState`
    # (`state.entities` ne contient que des unites/MoW) -> la boucle ci-dessus laissait `caster=None`,
    # et toute feuille qui lit `entities.caster` (ex. `AttackWithAbilityDamage`) devenait un NO-OP
    # SILENCIEUX des que le porteur etait une tuile. On materialise donc un caster MINIMAL porteur du
    # seul `id` — exactement ce dont la feuille a besoin (source du degat / attribution de mort).
    # Il n'entre PAS dans `units` : le natif non plus ne met pas la tuile dans la liste d'unites de
    # l'`AbilityEntities`, donc aucun selecteur ne peut la ramasser. INERTE quand `caster_id` designe
    # une unite (cas de tous les autres appelants).
    # `pos` : la TUILE porteuse a une position, et `IdunBattle.Entities.EntityExtensions$$GetMainTile`
    # rend une entite-tuile ELLE-MEME (domaine mixte) -> on la renseigne quand `caster_id` est un id
    # du `boardGraph`. Sans elle, tout selecteur de TUILE ancre sur ce caster (#213 : le `tiles =
    # Owner@0x148` du `Revive` de `GhostEffect`) resolvait une liste VIDE = no-op silencieux. Reste
    # `None` pour un caster non resolvable (ni unite, ni tuile du board).
    if caster is None and caster_id is not None:
        _board = getattr(state, "board", None)
        _tpos = None
        if _board is not None and int(caster_id) in getattr(_board, "by_id", {}):
            _c = _board.coord(int(caster_id))
            _tpos = {"col": int(_c[0]), "row": int(_c[1])}   # forme lue par `dsl.base._pos`
        caster = {"id": caster_id, "team": None, "player": None, "pos": _tpos,
                  "alive": True, "hp": None, "visualId": None, "_traits": set()}

    def _has_trait(unit, trait_id):
        try:
            enum = UnitTrait(int(trait_id))
        except ValueError:
            return False
        return has_trait((unit or {}).get("_traits") or set(), enum)

    # `ctx.faction_of` (mirror `UnitsFromFaction`) — FactionId gameconfig par visualId (`_faction` cache).
    # Lazy import (garde anti-circulaire, comme les Operations importees dans les feuilles).
    from ....ai.action_generators import _faction

    def _faction_of(unit):
        return _faction((unit or {}).get("visualId"))

    # `ctx.get_stat` (mirror `IdunBattle.Entities.UnitExtensions$$GetStat`) : le noeud `StatAmount(sel, statType,
    # variant)` lit la VRAIE stat de l'unite (Attack/Health/…) via son `StatsComponent.ctx.stats` — sans
    # ce wiring il degraderait vers Health (hp) via `_default_get_stat`. `variant` = `StatPart` natif
    # (0=Current, 2=Maximum, 3=Initial) ; `level` ignore offline (stats non scalees par niveau tierce).
    # id de l'unite DSL -> entite ECS -> `UnitStats.get_stat(statType, part)`.
    def _get_stat(unit, stat_type, variant=0, level=None):
        uid = (unit or {}).get("id")
        e = state.get_entity(uid) if uid is not None else None
        sc = e.get_component(StatsComponent) if e is not None else None
        us = getattr(sc.ctx, "stats", None) if sc is not None else None
        # #60 : stat 20 (NUMBER_OF_MEMBERS) = branche DEDIEE du GetStat natif (handler jumptable 0x14
        # IdunBattle.Entities.UnitExtensions$$GetStat+0x859 : GroupUnitComponent fill-up {+0x10=nrOfMembers, +0x18=restants}, PAS un
        # StatComponent — `IdunBattle.Entities.UnitExtensions$$GetStatComponent` n'a pas de case 0x14). Offline : parts derivees
        # de l'etat PV via `group_unit_stat_part` (lu par `SwarmAbility` StatAmount(Self,20,3/4)).
        # HEALTH = l'AUTRE stat « fill-up » du natif (comme NUMBER_OF_MEMBERS ci-dessous) :
        # `IdunBattle.Entities.UnitExtensions$$GetStat` route la PV sur un `FillUpStatComponent`
        # (+0x10 = maximum courant, +0x18 = valeur courante) et delegue a
        # `IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart`, PAS sur le `StatComponent`
        # generique. Cote port la PV vit dans le `HealthComponent` (hp / hp_max) ; passer par
        # `UnitStats.get_stat` rendait le composant HEALTH generique, dont l'`initial` est la PV
        # COURANTE captee -> `Maximum` valait la PV COURANTE des que l'unite etait blessee.
        # MESURE : DoT de tuile sur darkaTerminator a 473240/500000 PV -> base offline 94648
        # (= 20 % de 473240) contre 100000 attendu (= 20 % de 500000), tick natif 25000.
        # Parts (mirror `FillUpStatComponent$$GetStatPart`) : 0=Current, 1=CurrentPct, 2=Maximum,
        # 3=Initial, 4=Missing.
        if int(stat_type) == int(_ST.HEALTH):
            hc = e.get_component(HealthComponent) if e is not None else None
            if hc is not None and hc.hp is not None and hc.hp_max is not None:
                cur, mx, p = int(hc.hp), int(hc.hp_max), int(variant)
                if p in (2, 3):
                    return mx
                if p == 0:
                    return cur
                if p == _SP.MISSING:                # 4
                    return max(0, mx - cur)
                if p == 1:
                    return round(max(0.0, cur / mx) * 100) if mx else 0
            return us.get_stat(int(stat_type), int(variant)) if us is not None else 0
        if int(stat_type) == int(_ST.NUMBER_OF_MEMBERS):
            n = int(getattr(sc.ctx, "number_of_members", 1)) if sc is not None else 1
            hc = e.get_component(HealthComponent) if e is not None else None
            if hc is None or hc.hp is None or hc.hp_max is None:
                return n if int(variant) in (0, 2, 3) else 0
            from ....services.trait_damage_limits import group_unit_stat_part
            return group_unit_stat_part(int(variant), int(hc.hp_max), n, int(hc.hp))
        return us.get_stat(int(stat_type), int(variant)) if us is not None else 0

    # `ctx.player_turns_started` (mirror `IdunBattle.Entities.Formulas.UnitsPlayerTurnsStartedFormula
    # $$Calculate`) : `TurnComponent.GetAmountOfTurnsStartedByPlayer(turn, GetOriginalOwnerEntityId(
    # unit))` = le dict PAR JOUEUR `TurnComponent+0x38`, cote port `State.turn_counts`. Lu par le
    # noeud `PlayerTurnsStarted` (cycle a 3 temps de `SereneUnifierAbility`). L'owner ORIGINAL du
    # natif est approxime par l'owner COURANT (`OwnerComponent.player`) -- approximation nommee dans
    # la docstring du noeud. Unite sans `OwnerComponent` -> 0.
    def _player_turns_started(unit):
        uid = (unit or {}).get("id")
        e = state.get_entity(uid) if uid is not None else None
        oc = e.get_component(OwnerComponent) if e is not None else None
        if oc is None or oc.player is None:
            return 0
        return int(state.turn_counts.get(int(oc.player), 0) or 0)

    # `ctx.get_ability_level` (mirror du niveau d'ability lu par `ConfigVar` sur une unite TIERCE) : le noeud
    # `ConfigVarForEntity(RighteousRepugnance, chance, killer)` lit le niveau PASSIF/ACTIF capte de l'unite
    # (`StatsComponent.ctx.passive_ability_level`/`active_ability_level`, seede depuis unitConfig).
    def _get_ability_level(unit, slot="passive"):
        uid = (unit or {}).get("id")
        e = state.get_entity(uid) if uid is not None else None
        sc = e.get_component(StatsComponent) if e is not None else None
        if sc is None:
            return None
        return getattr(sc.ctx, "active_ability_level" if slot == "active" else "passive_ability_level", None)

    # `ctx.tile_has_effect` (predicat tuile de `IdunBattleLogic.Entities.DSLFactory$$UnitsOnTilesWithEffect`, #217) : la TUILE
    # (entite ECS tile-id) porte-t-elle un effet ACTIF (non consomme) du type ? Meme cle tile-id de
    # `state.effects` que la pose `AddEffectOperation` (case-35 : la glace vit dans by_unit[tile_id]).
    def _tile_has_effect(tile_id, effect_type):
        return (state.effects is not None
                and state.effects.has_effect(int(tile_id), effect_type=int(effect_type)))

    # `ctx.has_effect` (`IdunBattleLogic.Entities.DSLFactory$$HasEffect(unit, effectType, activeOnly,
    # sourceFlags)` -> `IdunBattle.Entities.Triggers.HasEffectTrigger$$ShouldTrigger` ->
    # `IdunBattle.Entities.EntityExtensions$$HasOneOfEffects`) : l'unite porte-t-elle un effet du type ?
    # (source-flag 6 = owned|incoming -> offline on ne distingue pas la source, toutes les instances
    # portees comptent). Meme cle `by_unit` que la pose `AddEffectOperation`. Sans `state.effects` ->
    # False (degradation fidele).
    # `active_only` (#100) = le 4e argument NATIF : `IsOwnerOfEffect` skippe toute entree dont
    # `EffectComponent+0x5c` (= IsActive) est nul. Cote port, l'equivalent est l'`ActiveCondition`
    # (`BaseEffect.is_active(unit_state)`) — indispensable pour
    # `AnvilShield_BlockChanceBelowHealthCap` (1200), PRESENT en permanence sur Arjac mais ACTIF
    # seulement sous 35 % PV. `unit_state` = `{hp, max_hp}` lu du `HealthComponent` du porteur.
    def _has_effect(unit, effect_type, source_flag=6, min_level=0, active_only=True):
        if state.effects is None:
            return False
        uid = (unit or {}).get("id")
        if uid is None:
            return False
        ustate = None
        for e in state.effects.by_unit.get(int(uid), []):
            if e.consumed or e.expired or e.effect_type != int(effect_type):
                continue
            if int(min_level or 0) > 0 and int(e.level or 0) < int(min_level):
                continue
            if active_only:
                if ustate is None:
                    _ent = state.get_entity(int(uid))
                    _hc = _ent.get_component(HealthComponent) if _ent is not None else None
                    ustate = ({"hp": _hc.hp, "max_hp": _hc.hp_max} if _hc is not None else {})
                if not e.is_active(ustate):
                    continue
            return True
        return False

    # `ctx.effects_from_source` (`IdunBattleLogic.Entities.DSLFactory$$EffectsFromUnitSource`, #MasterAnnihilator) : les INSTANCES
    # d'effet du type dont le `EffectComponent.SourceUnit` == `source_unit`. Balaye `state.effects.by_unit`
    # (cle = le PORTEUR) et ne garde que les instances ACTIVES (non consommees) de la bonne source.
    def _effects_from_source(source_unit, effect_type):
        if state.effects is None:
            return []
        sid = (source_unit or {}).get("id")
        if sid is None:
            return []
        out = []
        for uid, effs in state.effects.by_unit.items():
            for e in effs:
                if e.consumed or e.effect_type != int(effect_type) or e.source is None:
                    continue
                if int(e.source) == int(sid):
                    out.append({"effect_type": int(effect_type), "source": int(sid), "owner_id": int(uid)})
        return out

    # `ctx.current_player_machine_position` (predicat `IsPositionMachineForCurrentPlayer`, mirror
    # `IsPositionMachineForPlayerTrigger IdunBattle.Entities.Triggers.IsPositionMachineForPlayerTrigger$$ShouldTrigger`).
    # ⚠ RESIDU NOMME (#302 tranche 3) : le natif ne lit PAS une machine deployee, il lit
    # `IdunBattle.Core.Services.BattleQuery$$GetPositionMachineForPlayer` = la
    # `MachineOfWarPosition` du GROUPE DE SPAWN du joueur (`SpawnPointSetConfiguration.
    # GroupForPlayer(teamIndex, playerNr).<+0x14>`), une propriete du PLATEAU disponible qu'une MoW
    # soit la ou non -- cf. `engine.services.machine_of_war_position`, ou la cascade est portee, et
    # `AiDecisionContext.machine_of_war_position`, qui la cable cote DECISION.
    # Ce qui suit est donc un PROXY : le slot (`MachineComponent.Position` @0x78) de la MoW dont
    # l'owner-PLAYER est le joueur courant. Il est EXACT quand une MoW est deployee (elle l'a ete
    # sur le slot de son groupe) et rend None sinon, la ou le natif repond toujours. Le combler
    # demande de porter les `SpawnPointGroups` de la BC jusqu'au `State` -- hors perimetre #302-3,
    # qui n'a valide que la face DECISION.
    mow_pos = None
    if state.current_player_id is not None:
        from ...components import MachineComponent
        for _e, _mc in state.with_component(MachineComponent):
            _oc = _e.get_component(OwnerComponent)
            if _oc is not None and _oc.player == state.current_player_id:
                mow_pos = _mc.slot
                break

    # `ctx.has_negative_modifier` (`IdunBattle.Entities.Triggers.HasNegativeModifier$$ShouldTrigger`) :
    # l'unite porte-t-elle >=1 modification per-source NEGATIVE sur l'un des StatTypes du filtre ? Mirror
    # deja en place cote stats (`UnitStats.has_negative_modifier`, foyer du gate ConquerorImperative) —
    # ici on l'expose au DSL (predicat de ciblage PlagueburstMortar). Stats absentes -> False.
    def _has_negative_modifier(unit, stat_types):
        uid = (unit or {}).get("id")
        e = state.get_entity(uid) if uid is not None else None
        sc = e.get_component(StatsComponent) if e is not None else None
        us = getattr(sc.ctx, "stats", None) if sc is not None else None
        return bool(us.has_negative_modifier(stat_types)) if us is not None else False

    # `ctx.is_in_team_aura` (`IdunBattle.Entities.Triggers.IsInAuraRangeTrigger$$ShouldTrigger` ->
    # slot `IdunBattle.Core.Services.BattleQuery$$IsInTeamAuraRange`) : `unit` est-elle dans la portee
    # d'une aura `effect_type` portee par une unite de l'EQUIPE de `team_reference` ?
    # Le canal etait un RESIDU ASSUME (accesseur jamais fourni -> le noeud `IsInTeamAura` rendait
    # toujours False, donc la branche AURA de `PlagueburstMortarAbility$$GetIsValidAdjacentEnemyTrigger`
    # etait morte). Il est desormais MATERIALISE : `BattleQuery$$GetInRangeAuraAmount` est entierement
    # lisible au decompile (aucun slot opaque) et son etage de portee vit dans
    # `entities/effects/aura.py`, partage avec la formule `AuraEffectRange`. La correction est
    # strictement dans le sens de la FIDELITE (le port refusait des cibles que le natif accepte).
    def _is_in_team_aura(unit, effect_type, team_reference):
        team = (team_reference or {}).get("team")
        if team is None:
            return False                       # `GetCurrentTeamId(ref)` indisponible -> pas d'aura
        return _bq.is_in_team_aura_range(int(effect_type), int(team), unit, units,
                                         _has_trait, _turns_started)

    def _turns_started(unit):
        """`StatAmount(Owner, 0xc = TurnsStarted)` -- l'entree de `GetCurrentRange` d'un `IAuraEffect`."""
        return int(_get_stat(unit, int(_ST.TURNS_STARTED), 0, None) or 0)

    # `ctx.stat_modifier_amount` (`CurrentStatModifierAmountFormula`, gate d'idempotence de
    # `AddOrUpdateStaticStatModifierEffect`) : contribution COURANTE, sur `stat_type`, de l'effet
    # `effect_type` porte par l'unite = la `ValueModification` keyee par SA cle d'instance
    # (`effect_stat_mod_key` : cle de pose, sinon cle DERIVEE du seed — meme invariant « une seule
    # entree per_source par entite-effet » que le natif, #118). 0 si l'effet n'est pas porte ou n'a
    # pose aucune stat-modification.
    def _stat_modifier_amount(unit, effect_type, stat_type):
        uid = (unit or {}).get("id")
        if uid is None or state.effects is None:
            return 0
        e = state.get_entity(uid)
        sc = e.get_component(StatsComponent) if e is not None else None
        us = getattr(sc.ctx, "stats", None) if sc is not None else None
        comp = us.components.get(int(stat_type)) if us is not None else None
        if comp is None:
            return 0
        total = 0
        for eff in state.effects.by_unit.get(int(uid), []):
            if eff.consumed or eff.effect_type != int(effect_type):
                continue
            key = effect_stat_mod_key(eff)
            if key is None:
                continue
            total += int(comp.modification.get_modification_from_entity(key) or 0)
        return total

    # `ctx.has_unit_flag` (`IdunBattle.Entities.Components.UnitFlagsComponent$$Has`) : l'unite porte-t-elle
    # le drapeau ? Lu par `AllDeadOrResurrectedUnits` (flag 0xe = RESSUSCITE, pose par
    # `ResurrectUnitOperation` cote port `UnitFlagsComponent.AMBUSH_CONSUMED`). Unite sans composant de
    # flags -> False.
    def _has_unit_flag(unit, flag):
        uid = (unit or {}).get("id")
        e = state.get_entity(uid) if uid is not None else None
        fl = e.get_component(UnitFlagsComponent) if e is not None else None
        return bool(fl.has(int(flag))) if fl is not None else False

    # `ctx.can_have_active_ability_reset` (`IdunBattle.Core.Services.BattleQuery$$
    # EntityCanHaveActiveAbilityReset(unit, false)`) : l'unite a-t-elle une ability active RESETTABLE
    # (charge consommee hors cooldown, ou en cooldown sous conditions de tour) ? C'est le predicat du
    # selecteur `UnitsThatCanHaveActiveAbilityReset` (InspiredToGreatness). None = INCONNU (canal
    # `ActiveAbilitiesComponent` absent) -> propage, jamais rabattu sur False.
    def _can_have_active_ability_reset(unit):
        uid = (unit or {}).get("id")
        if uid is None:
            return None
        return entity_can_have_active_ability_reset(state, int(uid), False)

    # `ctx.units_damaged_this_phase` : mirror de la `List<BEntityId>` @`ActorStatisticsComponent + 0x48`
    # de l'ATTAQUANT (`IdunBattle.Entities.Formulas.UnitsDamagedThisPhaseSelector$$Select` prend ce
    # composant sur chaque attaquant selectionne et resout les ENTITES). Cote port la liste vit sur le
    # `UnitComponent` de l'attaquant (`damaged_units_this_phase`) ; on rend les vues `LiveUnit` deja
    # construites (meme identite d'objet que `ctx.units`, donc les predicats aval lisent le state LIVE).
    _by_id = {u.get("id"): u for u in units}

    def _units_damaged_this_phase(unit):
        uid = (unit or {}).get("id")
        e = state.get_entity(uid) if uid is not None else None
        uc = e.get_component(_UC) if e is not None else None
        if uc is None:
            return []
        return [_by_id[t] for t in uc.damaged_units_this_phase if t in _by_id]

    # `ctx.valid_normal_attack_targets` (`IdunBattle.Entities.Selectors.
    # ValidNormalAttackTargetsSelector$$Select`) : les cibles LEGALES de l'attaque NORMALE de
    # `caster_unit` depuis ses tuiles. DELEGUE a `runner/abilities/targeting.py` -- la cascade de
    # ciblage n'a QU'UN port, et c'est celui-la (surtout pas un 2e filtre ici). Rend les vues
    # `LiveUnit` deja construites (meme identite d'objet que `ctx.units`), dans l'ordre
    # d'enumeration de `state.entities`.
    def _valid_normal_attack_targets(caster_unit):
        from ..targeting import valid_normal_attack_targets as _vnat
        cid = (caster_unit or {}).get("id")
        if cid is None:
            return []
        return [_by_id[t] for t in _vnat(state, int(cid)) if t in _by_id]

    # `ctx.entity_can_be_repaired` (slot 0x13 d'`IAttackQuery`, lu par
    # `IdunBattle.Entities.Selectors.RepairableUnitsSelector$$Select`) : DELEGUE a l'unique mirror du
    # predicat (`abilities/attack_query.entity_can_be_repaired`) avec `caster_id = None` -- la
    # surcharge a TROIS arguments EST la 4-args a caster nul (relue au decompile : le seul disjunct
    # qui disparait est `caster != null && HasFlag(caster, 0x18)`). Surtout pas un 2e port du gate.
    def _entity_can_be_repaired(unit, scope=0, remove_effects=True):
        from ..attack_query import entity_can_be_repaired as _ecbr
        uid = (unit or {}).get("id")
        if uid is None:
            return False
        return bool(_ecbr(state, None, int(uid), scope=int(scope),
                          remove_effects=bool(remove_effects)))

    # `ctx.pick_randomly` (`IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select`) : le noeud
    # DSL `PickRandomly` n'a pas acces au PRNG de bataille -> il passe par cet accesseur, qui delegue
    # au foyer UNIQUE de la boucle native (`abilities/loki/splash._pick_randomly_n`, loi #130/#215 :
    # `min(len(pool), amount)` tirages, y compris sur un pool de 1). L'ORDRE de `items` est celui du
    # selecteur source -- on ne le retrie pas ici (R28-1).
    def _pick_randomly(items, amount, allow_repeat=False, max_repeats=0x7FFFFFFF):
        from ..loki.splash import _pick_randomly_n
        return _pick_randomly_n(state, list(items), int(amount),
                                allow_repeat=bool(allow_repeat), max_repeats=int(max_repeats))

    # `ctx.sort_tiles_by_utility` (`IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select`)
    # : le noeud DSL `SortTilesByUtility` n'a pas acces au `State` (les feuilles d'utilite lisent
    # l'ECS entier) -> il passe par cet accesseur, qui delegue au foyer UNIQUE
    # `engine/utilities/tile.py::sort_tiles_by_utility` -- le MEME que consomment les call-sites qui
    # collapsent `First(SortTilesByUtility(...), 1)` (`first_tile_by_utility`). ZERO tirage.
    # `leaf_ctx` = `runner_tile_leaf_ctx(state, unit_id, parent_id)`, le port de `dc.units`/`dc.owner`
    # que le natif met dans le `UtilityMovementCase` de chaque feuille (#165).
    def _sort_tiles_by_utility(tiles, unit_id, utility_type, parent_id=None):
        uid = None if unit_id is None else int(unit_id)
        pid = None if parent_id is None else int(parent_id)
        return _stbu(state, list(tiles), None, uid, int(utility_type), pid, None,
                     runner_tile_leaf_ctx(state, uid, pid))

    # `ctx.charged_units` (`UnitComponent + 0x190`, cf. `update_charging`) : ids que l'unite a CHARGES
    # pendant son activation courante. Moitie runtime du predicat
    # `IdunBattle.Core.Services.BattleQuery$$IsCharging` (l'autre moitie = l'adjacence). Vide si le
    # composant manque (degradation fidele : personne n'a charge).
    def _charged_units(unit):
        uid = (unit or {}).get("id")
        return charged_unit_ids(state, int(uid)) if uid is not None else set()

    # `ctx.persistent_data_list` (`IdunBattle.Entities.Components.PersistentDataComponent$$
    # TryGetPersistDataListu003C__Il2CppFullySharedGenericStructTypeu003E`) : le `List<T>` range sous
    # la cle composite `(GetPersistentDataId(abilityOrEffect), dataKey)` du sac persistant de l'unite.
    # Cle absente / composant absent -> `[]`, exactement ce que fait le natif (les trois consommateurs
    # -- `AddToPersistentDataListBehaviour$$Execute`, `IsInPersistentDataListTrigger$$ShouldTrigger`,
    # `EntitiesFromPersistentDataListSelector$$Select` -- font tous `?? new List<T>()`).
    def _persistent_data_list(unit, key):
        uid = (unit or {}).get("id")
        return _pdl(state.get_entity(int(uid)) if uid is not None else None, key)

    def _persistent_data(unit, key):
        """`ctx.persistent_data` -- le pendant SCALAIRE de `_persistent_data_list`, sur le MEME
        `Dictionary` @+0x10 et la MEME cle composite. `None` = cle absente (la formule
        `GetPersistentData` le rend en 0, comme l'`out` par defaut du natif)."""
        uid = (unit or {}).get("id")
        return _pd(state.get_entity(int(uid)) if uid is not None else None, key)

    def _previous_tiles(unit):
        """`ctx.previous_tiles` -- `PositionComponent+0x88` deplie en coordonnees, ce que rend
        `IdunBattle.Entities.Selectors.PreviousTileSelector$$Select`. `[]` = `Nullable` VIDE."""
        uid = (unit or {}).get("id")
        return _pt(state.get_entity(int(uid)) if uid is not None else None)

    # `ctx.entity_by_id` (`IBattleState.GetEntity(id)`, slot 0x29) : la resolution id -> unite que
    # fait `EntitiesFromPersistentDataListSelector$$Select`. On la sert depuis `units` (deja
    # materialise ci-dessus), donc dans la MEME representation que tous les autres selecteurs.
    # Un id absent rend None -> le selecteur le jette, comme le natif.
    _by_id = {int(u["id"]): u for u in units if (u or {}).get("id") is not None}

    def _entity_by_id(eid):
        try:
            return _by_id.get(int(eid))
        except (TypeError, ValueError):
            return None

    return DslContext(units=units, caster=caster, target=target, actor=actor, board=state.board,
                      # `TurnComponent.CurrentPlayer` -> noeud `IsTurnOf` (#85). Le runner le tient
                      # dans `state.current_player_id` (pose par `ChangeTurnOperation.execute`).
                      current_player_id=getattr(state, "current_player_id", None),
                      player_turns_started=_player_turns_started,
                      units_damaged_this_phase=_units_damaged_this_phase,
                      charged_units=_charged_units,
                      valid_normal_attack_targets=_valid_normal_attack_targets,
                      persistent_data_list=_persistent_data_list,
                      persistent_data=_persistent_data,
                      previous_tiles=_previous_tiles,
                      entity_by_id=_entity_by_id,
                      has_trait=_has_trait, faction_of=_faction_of, get_stat=_get_stat,
                      has_unit_flag=_has_unit_flag,
                      get_ability_level=_get_ability_level, tile_has_effect=_tile_has_effect,
                      has_effect=_has_effect, effects_from_source=_effects_from_source, children=[],
                      has_negative_modifier=_has_negative_modifier,
                      is_in_team_aura=_is_in_team_aura,
                      can_have_active_ability_reset=_can_have_active_ability_reset,
                      entity_can_be_repaired=_entity_can_be_repaired,
                      pick_randomly=_pick_randomly,
                      sort_tiles_by_utility=_sort_tiles_by_utility,
                      # `has_effect_of_type` reste NON BRANCHE : la CATEGORIE d'un effet
                      # (`EffectsDatabase` def+0x58) n'est pas dans le canal de seed. Cf. le noeud
                      # `UnitsWithEffectsOfType` -- residu NOMME, pas un oubli.
                      current_player_machine_position=mow_pos)
