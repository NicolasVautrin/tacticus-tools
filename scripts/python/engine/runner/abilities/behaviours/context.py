"""Socle du contexte DSL runner-couple : `entities_from_state` (construit le `DslContext` natif
`AbilityEntities` depuis le `State` runner) + `LiveUnit` (vue live-by-ref d'une unite). Consomme par
TOUTES les feuilles du package `behaviours`. cf. docs/rl/dsl-effect-nodes.md,
docs/rl/dsl-live-context-substrate.md."""
from __future__ import annotations

from ....dsl.base import DslContext
from ...components import (OwnerComponent, PositionComponent, UnitComponent, StatsComponent,
                          HealthComponent)
from ....entities.traits.unit_trait import UnitTrait, has_trait


import functools


_GRAND_ALLIANCE_TRAITS = frozenset({"Imperial", "Chaos", "Xenos"})


@functools.lru_cache(maxsize=None)
def _grand_alliance_trait(visual_id: str | None) -> str | None:
    """Trait d'ALLIANCE d'une unite, DERIVE de sa GrandAlliance (mirror `idun.Idun.Source.Shared.GrandAlliance$$GetTrait` : "Imperial"->0x1a=26, "Xenos"->0x3ee=1006, "Chaos"->0x7ea=2026). Le NOM du trait ==
    le `GrandAllianceId` gameconfig (== `UnitTrait.Imperial/Xenos/Chaos.name`) -> ajoutable tel quel au
    set de traits (resolu par `_has_trait` -> `UnitTrait(id).name in traits`). ABSENT de
    `gameconfig.unit().traits` (0 unite le porte) : c'est un trait de bataille inne non expose offline
    ni dans le combatSnapshot. None si l'alliance n'a pas de trait dedie. Cache (statique par unite)."""
    if not visual_id:
        return None
    try:
        import gameconfig as _GC
    except Exception:
        return None
    ga = (_GC.unit(visual_id) or {}).get("GrandAllianceId")
    return ga if ga in _GRAND_ALLIANCE_TRAITS else None


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
    traits = set(getattr(sc.ctx, "traits", None) or ()) if sc is not None else set()
    # Trait d'ALLIANCE (Imperial/Chaos/Xenos) inne, DERIVE de la GrandAlliance (cf. `_grand_alliance_trait`)
    # : requis par le split RevitalizingMalignancy (WithoutTrait Imperial / WithTrait Chaos) + l'exclusion
    # Imperial de CombatRestoratives. CONFIRME LIVE (case-220 : deathBlightbringer Chaos +6980,
    # eldarRanger Xenos +3490, adeptHospitaller Imperial +0).
    _ga = _grand_alliance_trait(uc.visual_id if uc is not None else None)
    if _ga is not None:
        traits = traits | {_ga}
    alive = uc.alive if uc is not None else True
    return {
        "id": eid,
        "team": oc.team if oc is not None else None,
        "player": oc.player if oc is not None else None,
        "pos": {"col": pc.col, "row": pc.row} if pc is not None else None,
        "alive": alive,
        "hp": hc.hp if hc is not None else (1 if alive else 0),
        "visualId": uc.visual_id if uc is not None else None,
        # Lien PARENT (`ParentComponent` id @+0x10, live `Unit_Parent_Id`) : lu par le selecteur
        # `Parent` (`IdunBattle.Entities.Selectors.ParentSelector$$Select` ->
        # `IdunBattle.Entities.UnitExtensions$$GetParent`). None pour toute unite du roster initial.
        "parentId": getattr(uc, "parent_id", None) if uc is not None else None,
        "_traits": traits,
    }


# Champs MUTABLES d'une unite (re-lus du state a chaque acces par LiveUnit). Les autres (id/team/player/
# visualId/_traits) sont quasi-statiques -> servis depuis le snapshot seed.
_LIVE_KEYS = frozenset({"pos", "hp", "alive"})


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

    def _has_trait(unit, trait_id):
        try:
            enum = UnitTrait(int(trait_id))
        except ValueError:
            return False
        return has_trait(unit.get("_traits") or set(), enum)

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
        from ....entities.stats import StatType as _ST
        if int(stat_type) == int(_ST.NUMBER_OF_MEMBERS):
            n = int(getattr(sc.ctx, "number_of_members", 1)) if sc is not None else 1
            hc = e.get_component(HealthComponent) if e is not None else None
            if hc is None or hc.hp is None or hc.hp_max is None:
                return n if int(variant) in (0, 2, 3) else 0
            from ....services.trait_damage_limits import group_unit_stat_part
            return group_unit_stat_part(int(variant), int(hc.hp_max), n, int(hc.hp))
        return us.get_stat(int(stat_type), int(variant)) if us is not None else 0

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
    # `IsPositionMachineForPlayerTrigger IdunBattle.Entities.Triggers.IsPositionMachineForPlayerTrigger$$ShouldTrigger` qui lit le slot MoW de `GetPlayer(turn.
    # CurrentPlayerId)`) : le slot (`MachineComponent.Position` @0x78) de la MoW dont l'owner-PLAYER
    # est le joueur courant. None si le joueur courant n'a pas de MoW deployee.
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

    # `ctx.stat_modifier_amount` (`CurrentStatModifierAmountFormula`, gate d'idempotence de
    # `AddOrUpdateStaticStatModifierEffect`) : contribution COURANTE, sur `stat_type`, de l'effet
    # `effect_type` porte par l'unite = la `ValueModification` keyee par SA cle d'instance
    # (`effect_stat_mod_key` : cle de pose, sinon cle DERIVEE du seed — meme invariant « une seule
    # entree per_source par entite-effet » que le natif, #118). 0 si l'effet n'est pas porte ou n'a
    # pose aucune stat-modification.
    def _stat_modifier_amount(unit, effect_type, stat_type):
        from ....entities.effects import effect_stat_mod_key
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
        from ...components import UnitFlagsComponent
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
        from ...operations.ability_reset import entity_can_have_active_ability_reset
        uid = (unit or {}).get("id")
        if uid is None:
            return None
        return entity_can_have_active_ability_reset(state, int(uid), False)

    return DslContext(units=units, caster=caster, target=target, actor=actor, board=state.board,
                      has_trait=_has_trait, faction_of=_faction_of, get_stat=_get_stat,
                      has_unit_flag=_has_unit_flag,
                      get_ability_level=_get_ability_level, tile_has_effect=_tile_has_effect,
                      has_effect=_has_effect, effects_from_source=_effects_from_source, children=[],
                      has_negative_modifier=_has_negative_modifier,
                      can_have_active_ability_reset=_can_have_active_ability_reset,
                      current_player_machine_position=mow_pos)
