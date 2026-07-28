"""`GhostRevive` / `TimeFlux_Revive` -- le SEUL revive NON-IN-PLACE du binaire (case-66 §8.2, #213).

Carrier : `thousTerminator` (<< Toth >>, hero ThousandSons, present dans `rl_duel.py --list-pool`).
i2 : « When Toth moves, he leaves a **time ghost** behind on the hex he moved from. If Toth is
defeated, he is revived on the hex of the time ghost with {hp} Health. The time ghost vanishes if the
hex becomes occupied by another unit. »
⚠ le decompile CORRIGE l'i2 sur un point : la tuile n'est PAS « the hex he moved from », c'est la
tuile ou Toth se trouvait au **DEBUT DE SON TOUR** (`CurrentTurnStartTile`, `UnitComponent + 0x18c`,
ecrit par `IdunBattle.Operations.StartTurnOperation$$Execute`). Les deux coincident tant que Toth ne
bouge qu'une fois par tour -- ce qui est le cas nominal -- mais c'est bien le champ +0x18c qui est lu.

TROIS artefacts natifs DISTINCTS (ne pas les fondre) :

1. `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GhostReviveAbility` -- la POSE du ghost.
   `...TimeFluxReviveAbility$$.ctor` = `GhostReviveAbility..ctor(this, 0x4a2 = 1186)` ; le ctor de
   base est nomme `EnvDefenderHealthBuffAbility..ctor` par ICF -- **ne PAS se fier au nom**.
   DEUXIEME instanciation dans ce build (classes.tsv) :
   `...EchoesFromTheWarpAbility$$.ctor` = `GhostReviveAbility..ctor(this, 0x504 = 1284)` -- hors
   perimetre #213 (porteur non etabli), mais c'est ELLE qui explique le fork d'amount ci-dessous.

       `GhostReviveAbility$$CreateTrigger` =
           <cache factory@0xa0 = OwnerIsActor> & On(0x1f = PreUnitMove, 1) & OwnerIsCaster

       `GhostReviveAbility$$CreateBehaviour` =
           tile = CurrentTurnStartTile(caster@0x160)
           cond = AmountIsEqual(CurrentTurnStartTile(caster@0x160), Direct(0))
                | HasBeenRevivedByAbility(caster@0x160, AbilityOrEffect(this.effectType@0x60))
                | NOT(OwnerIsCaster)
                | TileHasTriggeredAbility(tile, 0x1d = 29 = BrokenIce)
           If( cond, Nothing(),
               AddEffect(this.effectType@0x60, AbilityStateReference,
                         source = caster@0x160, targets = tile, options = null) )

   `AddEffect` est ici la surcharge `(effectType, abilityState, source, targets, options)` (5 args) :
   **source = Toth, targets = la TUILE**. L'effet est donc PORTE PAR LA TUILE, avec Toth pour source.

2. `IdunBattle.Entities.Effects.Loki.GhostEffect` -- l'effet porte par la tuile.

       `GhostEffect$$CreateTargetTrigger` =
           OnPreDeath(ignoreOverkill = 1) & AreEqual(EffectSource(self@0x150), target@0x178)
       -> **even if Overkilled**, et seul le POSEUR du ghost peut le declencher.

       `GhostEffect$$CreateTargetTriggerBehaviour` =
           src    = EffectSource(Get(effect))
           cond   = NOT(IsAlive(src)) & NOT(HasFlag(src, 6 = Dead))
                    & NOT(HasBeenRevivedByAbility(src, AbilityOrEffect(effectType@0x10)))
           amount = <si effect.source@0x14 vaut 0x485 = 1157 TriggeredAbilityType.TimeFlux>
                    ? Direct(GetVariableForLevel(config@0x60, 0x1d = 'hp', abilityState))
                    : StatAmount(src, Health = 5, max = 3)
           If( cond, Revive(src, src, amount, healType = 2,
                            Nullable(AbilityOrEffect(effectType@0x10)),
                            **tiles = Owner@0x148**, priority = 0)
                     + BaseEffect.GetRemoveEffectBehaviour(),
               null )

   Le fork d'`amount` est resolu A LA CONSTRUCTION de l'arbre (comparaison de champs, pas de noeud) :
   la branche `Direct('hp')` est celle de `TimeFlux_Revive` (source = le passif TimeFlux = 1157), la
   branche `StatAmount(max)` celle d'`EchoesFromTheWarp`. Confirmation croisee : `TimeFlux.hp`
   (2401 @ L65) existe au gameconfig et n'est lue par AUCUN autre arbre (cf. `time_flux.py`).

   Le 7e argument de `DSLFactory.Revive` (`targetsTile`) est ici **NON NUL** -- c'est LA difference
   avec les six revives deja portes, et le seul endroit du sous-systeme ou la position change.

       `GhostEffect$$CreateHandleTriggerAbilitiesInternal` = ArraySet de CINQ retraits
       (`GetRemoveEffectBehaviour` a chaque fois) -- la « condition de disparition » de l'i2 :
         1. On(0x1f = PreUnitMove, 1) & AreEqual(caster@0x160, EffectSource)
         2. On(0x33 = UnitAdded, 1) & NOT AreEqual(caster, EffectSource)
            & Contains(TargetTiles@0x190, Owner@0x148) & NOT HasTrait(caster, 0x1b = Steppable)
         3. On(0x24 = UnitPositionChanged_1, 1) & NOT AreEqual(caster, EffectSource)
            & Contains(TargetTiles@0x190, Owner@0x148)
         4. OnDeath(1) & AreEqual(EffectSource, target@0x178) & NOT IsEffectActive(self@0x150)
         5. On(0x25 = UnitRemoved, 1) & AreEqual(EffectSource, target@0x178)

3. `IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition` -- le mutateur de position
   (mirror dans `operations/revive.py::_set_revive_position`), garde par
   `if (!revivePosition.HasValue) return;`.

DOCTRINE #149 : les `CreateTrigger` sont COLLAPSES dans `matches()` (idiome de tous les
trigger-ports) ; les `CreateBehaviour`/`CreateTargetTriggerBehaviour` sont de VRAIS arbres DSL
(`If`/`Nothing` + feuilles `AddEffect` / `Revive` / `RemoveEffect`), et la frontiere reste le
`.execute` des feuilles (`AddEffectOperation`, `post_pending_revive` -> `ReviveUnitOperation`).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import UnitComponent, PositionComponent
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.traits import UnitTrait, has_trait
from .....entities.selectors import Caster, Target
from ....abilities.behaviours import entities_from_state
from ..base import TriggeredAbility, TileEffectTrigger, TriggerEvent, _unit_trait_names
from ..revive_effect import Revive, can_be_revived

ABILITY_ID = "TimeFlux"                       # cle gameconfig des variables ('hp')
GHOST_EFFECT = int(EffectType.TimeFlux_Revive)        # 0x4a2 = 1186 -- le litteral du ctor
TIME_FLUX_ABILITY = int(TriggeredAbilityType.TimeFlux)  # 0x485 = 1157 (source qui choisit la branche 'hp')
GHOST_HEAL_TYPE = 2                           # 4e argument du `Revive` -- `IsAffectedByHealType` ne
                                              # filtre NI Heal NI Repair (meme litteral que PhoenixGem).
GHOST_REVIVE_PRIORITY = 0                     # 8e argument (`IsPreferredRevive`)
# `TileHasTriggeredAbility(tile, 0x1d = 29)` -- `TriggeredAbilityType.BrokenIce` (dump d'enums du
# build). Une tuile de glace BRISEE ne peut pas porter de ghost. Aucun board du pool ne porte cette
# tile-ability -> gate INERTE en pratique, porte quand meme (mirror, et il ne coute rien).
BROKEN_ICE_TILE_ABILITY = 29
# `NOT HasTrait(caster, 0x1b)` du retrait n°2 : `UnitTrait.Steppable` -- un decoy / une spore-mine
# posee sur la tuile du ghost ne le dissipe PAS.
GHOST_UNIT_ADDED_EXCLUDED_TRAIT = UnitTrait.Steppable


def _tile_of(state: State, unit_id: int) -> Optional[int]:
    """Id d'entite-tuile (`boardGraph`) ou se tient `unit_id` -- mirror
    `IdunBattle.Entities.EntityExtensions$$GetMainTile(unit).Id`. None sans board / sans position."""
    board = getattr(state, "board", None)
    e = state.get_entity(unit_id)
    pc = e.get_component(PositionComponent) if e is not None else None
    if board is None or pc is None:
        return None
    return board.id_at(pc.col, pc.row)


def _has_been_revived_by_ability(state: State, unit_id: int, source: int) -> bool:
    """`IdunBattleLogic.Entities.DSLFactory$$HasBeenRevivedByAbility(unit, source)` ->
    `Idun.Source.IdunBattle.Logic.Entities.Triggers.HasBeenRevivedAbilityTrigger$$ShouldTrigger` :
    resout son selecteur, prend l'`ActorStatisticsComponent` de l'entite et rend
    `component@+0xe0 .Contains(source)`. Le set est alimente par
    `IdunBattle.Operations.ReviveUnitOperation$$Execute` (l'`AbilityOrEffect` de la `ReviveData`) et
    n'est JAMAIS remis a zero -> gate « une seule fois par BATAILLE ». Port : le set
    `UnitComponent.revived_by_abilities` (meme residu structurel que `last_hit_damage_taken_*`)."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    return uc is not None and int(source) in uc.revived_by_abilities


def _tile_has_triggered_ability(state: State, tile_id: Optional[int], ability: int) -> bool:
    """`IdunBattleLogic.Entities.DSLFactory$$TileHasTriggeredAbility(tile, ability)` ->
    `IdunBattle.Entities.Triggers.TileHasTriggeredAbilityTrigger$$ShouldTrigger` : resout le
    selecteur de tuile (slot 0xc = une entite) puis
    `IdunBattle.Entities.UnitExtensions$$HasTriggeredAbility(tile, abilityType)`.

    Cote port, les tile-abilities sont portees par le `tileDefId` du terrain (cf.
    `triggers/tiles.py`, ou `TilesWithTriggeredAbility(0x39 = DryBushFireSpread)` <=> `tileDefId ==
    'DryBush'`). `BrokenIce` (29) n'a AUCUN tile-def hote dans les boards du pool -> False.
    RESIDU NOMME : la table `TriggeredAbilityType -> tileDefId` n'existe pas cote port (elle vit dans
    les Unity assets de tuile, hors gameconfig) ; ce gate est donc structurellement present mais
    toujours faux. Il ne peut REFUSER un ghost a tort que sur un board a glace brisee."""
    return False


class GhostReviveAbility(TriggeredAbility):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.GhostReviveAbility` parametree par
    `TimeFluxReviveAbility$$.ctor` (effectType 1186) -- la POSE du time-ghost.

    Rail : `ABILITY_TRIGGERS["TimeFlux"]` (aux cotes de `TimeFluxRegenAbility`) -- le natif derive
    DEUX triggered-abilities du MEME passiveAbility `TimeFlux` de `thousTerminator`, et ce registre
    est precisement le mirror de cette derivation.

    `CreateTrigger` = `<factory@0xa0 = OwnerIsActor> & On(0x1f = PreUnitMove, 1) & OwnerIsCaster` :
      * `OwnerIsActor` (le MEME cache @0xa0 que `TimeFluxAbility`/`LivingMetalRepairAbility`, ou il
        est PROUVE live par `probe_203`) + `OwnerIsCaster` : sur `On(PreUnitMove)` le natif construit
        `AbilityEntities.ctor(mover, mover, mover)` -> actor == caster == target == le mover, donc
        les deux predicats se reduisent au MEME test : « c'est MOI qui bouge »."""
    event_id = int(EventTriggerType.PreUnitMove)            # On(0x1f = 31)
    TRIGGERED_ABILITY_ID = TIME_FLUX_ABILITY                # `BaseTriggeredAbility$$Execute` inscrit cet id

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `OwnerIsActor & OwnerIsCaster` -- collapse : le mover EST l'acteur ET le caster de l'event.
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        e = state.get_entity(self.owner_id)
        uc = e.get_component(UnitComponent) if e is not None else None
        return uc is not None and uc.alive

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        e = state.get_entity(self.owner_id)
        uc = e.get_component(UnitComponent) if e is not None else None
        if uc is None:
            return None
        # `tile = CurrentTurnStartTile(caster@0x160)` -- `CurrentTurnStartTileSelector$$Select` lit
        # `UnitComponent + 0x18c` et rend `[]` quand il vaut 0.
        tile = uc.current_turn_start_tile
        # --- `cond` (les quatre disjonctions, dans l'ordre du decompile) --------------------------
        # 1. `AmountIsEqual(CurrentTurnStartTile(caster), Direct(0))` : aucune tuile de debut de tour
        #    enregistree (le champ vaut 0) -> pas de ghost.
        no_start_tile = tile is None
        # 2. `HasBeenRevivedByAbility(caster, AbilityOrEffect(1186))` : Toth a DEJA ete ressuscite par
        #    ce ghost dans cette bataille -> il n'en repose plus.
        already = _has_been_revived_by_ability(state, self.owner_id, GHOST_EFFECT)
        # 3. `NOT(OwnerIsCaster)` : deja tranche par `matches` (event mover==owner) -> toujours faux ici.
        # 4. `TileHasTriggeredAbility(tile, BrokenIce=29)` : pas de ghost sur une glace brisee.
        broken_ice = _tile_has_triggered_ability(state, tile, BROKEN_ICE_TILE_ABILITY)
        if no_start_tile or already or broken_ice:
            return None                                  # branche `Nothing()` du `If`
        # --- branche `AddEffect(1186, AbilityStateReference, source=caster, targets=tile)` ---------
        # `AddEffectOperation` = la feuille imperative (frontiere #149). L'`AbilityStateReference` du
        # natif = l'etat d'ability du PORTEUR (TimeFlux est un PASSIF) -> on transmet son
        # `passive_ability_level` + `ability_variables_multiplier`, ce que relira le
        # `GetVariableForLevel(config, 'hp')` du behaviour de l'effet.
        from ...effects import AddEffectOperation
        lvl, mult = _passive_scaling(state, self.owner_id)
        eff = AddEffectOperation.execute(state, source=int(self.owner_id), target=int(tile),
                                         effect_type=GHOST_EFFECT, name="TimeFlux_Revive",
                                         ability_level=lvl, multiplier_pct=mult)
        if eff is None:
            return None
        return {"ability": ABILITY_ID, "owner": int(self.owner_id), "ghost_tile": int(tile),
                "effect_type": GHOST_EFFECT, "on_event": int(ev.event_id)}


def _passive_scaling(state: State, owner_id: int) -> tuple:
    """`(passive_ability_level, ability_variables_multiplier)` du porteur -- `TimeFlux` est un PASSIF
    (meme resolution que `time_flux.py::_passive_scaling`, volet regen)."""
    from ....components import StatsComponent
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return None, 100
    return (getattr(ctx, "passive_ability_level", None),
            int(getattr(ctx, "ability_variables_multiplier", 100) or 100))


def _effect_source(state: State, tile_id: int) -> Optional[int]:
    """`EffectSource(self@0x150)` -- l'unite qui a POSE le ghost (`EffectComponent.SourceUnit @+0x10`).
    None si la tuile ne porte plus l'effet."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return None
    for e in (eff.by_unit.get(int(tile_id)) or []):
        if e.effect_type == GHOST_EFFECT and not e.consumed:
            return None if e.source is None else int(e.source)
    return None


def _ghost_effect(state: State, tile_id: int):
    """L'instance de `GhostEffect` ACTIVE portee par `tile_id`, ou None."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return None
    for e in (eff.by_unit.get(int(tile_id)) or []):
        if e.effect_type == GHOST_EFFECT and not e.consumed:
            return e
    return None


def _remove_ghost(state: State, tile_id: int) -> bool:
    """`BaseEffect.GetRemoveEffectBehaviour()` -- retire le ghost de la tuile. Le port marque
    l'instance `consumed=True` (MEME mecanique que `RemoveReviveEffect`, cf. `revive_effect.py`) :
    `collect_effect_triggers` skippe les effets consommes -> plus aucun trigger du ghost ne fire."""
    e = _ghost_effect(state, tile_id)
    if e is None:
        return False
    e.consumed = True
    return True


class GhostEffectRevive(TileEffectTrigger):
    """`GhostEffect$$CreateTargetTrigger` + `$$CreateTargetTriggerBehaviour` -- la RESURRECTION.

    Porteur = la TUILE (`TileEffectTrigger` : `owner_is_tile` fait sauter les gates unit/alive du
    dispatch, `owner_id` est un id de `boardGraph`). C'est le seul revive du binaire dont le
    `DSLFactory.Revive` recoit un `targetsTile` non nul (`Owner@0x148` = cette tuile), donc le seul
    qui ecrit une position dans la `ReviveData`."""
    effect_type = GHOST_EFFECT
    event_ids = (int(EventTriggerType.PreUnitDeath),)       # OnPreDeath -> OnDeathEvent(1)
    event_id = int(EventTriggerType.PreUnitDeath)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        dying = ev.dying_id
        if dying is None or state.get_entity(dying) is None:
            return False
        # `OnPreDeath(ignoreOverkill = 1)` -> AUCUN gate overkill (« even if Overkilled ») : on ne
        # teste DELIBEREMENT PAS `ev.overkill`.
        # `AreEqual(EffectSource(self@0x150), target@0x178)` : seul le POSEUR du ghost le declenche.
        src = _effect_source(state, self.owner_id)
        if src is None or int(src) != int(dying):
            return False
        # --- `cond` du behaviour (evaluee ici : c'est un `If`, pas un second trigger) -------------
        # `NOT(IsAlive(src))` -- l'unite doit etre morte. Sur le vecteur `On(1)` le port a deja pose
        # `alive=False` (fire-on-death), donc ce gate est satisfait ; il reste porte pour le cas ou
        # ce trigger serait atteint hors sequence de mort.
        e = state.get_entity(dying)
        uc = e.get_component(UnitComponent) if e is not None else None
        if uc is not None and uc.alive:
            return False
        # `NOT(HasFlag(src, 6 = Dead))` -- le flag `UnitFlag.Dead` n'est pose qu'APRES la garde de
        # `KillUnitOperation` (donc jamais a l'instant de l'`On(1)`) : mirror non modelise, gate
        # toujours vrai ici, exactement comme le flag 0xd de `can_be_revived` (case-66 §5).
        # `NOT(HasBeenRevivedByAbility(src, AbilityOrEffect(1186)))`
        if _has_been_revived_by_ability(state, dying, GHOST_EFFECT):
            return False
        # `DSLFactory.Revive` -> `ReviveBehaviour$$Execute` gate `BattleQuery.CanBeRevived(target,
        # healType)` avant d'ecrire la `ReviveData` : meme mirror que la base `ReviveEffect`.
        entities = entities_from_state(state, self.owner_id, dying)
        tgt = entities.target
        if tgt is None:
            return False
        return can_be_revived(entities, tgt, dying, state, heal_type=GHOST_HEAL_TYPE)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        dying = ev.dying_id
        entities = entities_from_state(state, self.owner_id, dying)
        ectx = ExecutionContext(state=state, rng=state.rng)
        eff = _ghost_effect(state, self.owner_id)
        lvl = None if eff is None else (eff.active_ability_level
                                        if eff.active_ability_level is not None else eff.ability_level)
        mult = 100 if eff is None else int(eff.ability_variables_multiplier or 100)
        # Branche `Direct(GetVariableForLevel(config, 0x1d='hp', abilityState))` du fork d'amount :
        # c'est celle de `TimeFlux_Revive` (source = 1157). La branche `StatAmount(src, Health, max)`
        # appartient a l'AUTRE instanciation de `GhostEffect` (`EchoesFromTheWarp`, effet 1284), hors
        # perimetre #213 -> non portee (aucun porteur etabli).
        # `tiles_sel = Caster()` = `Owner@0x148` : dans le contexte d'un effet-trigger le port pose
        # `caster = owner` (collapse documente de `entities_from_state`), et l'owner est ICI la TUILE.
        Revive(Target(), ABILITY_ID, "hp", lvl, mult,
               heal_type=GHOST_HEAL_TYPE, source_id=GHOST_EFFECT,
               priority=GHOST_REVIVE_PRIORITY, tiles_sel=Caster()).execute(entities, ectx)
        # 2e volet de l'`op_Addition` : `BaseEffect.GetRemoveEffectBehaviour()` -- le ghost est
        # consomme par la resurrection qu'il vient de declencher.
        removed = _remove_ghost(state, self.owner_id)
        revives = [p for n, p in ectx.emitted if n == "Revive" and p.get("revived")]
        return {"ability": ABILITY_ID, "ghost_tile": int(self.owner_id), "dying": dying,
                "revives": revives, "ghost_removed": removed}


class _GhostRemoval(TileEffectTrigger):
    """Base des CINQ `Triggered(<cond>, GetRemoveEffectBehaviour())` de
    `GhostEffect$$CreateHandleTriggerAbilitiesInternal`. Behaviour commun : retirer le ghost."""
    effect_type = GHOST_EFFECT

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        raise NotImplementedError

    def _source(self, state: State) -> Optional[int]:
        return _effect_source(state, self.owner_id)

    def _actor_is_on_my_tile(self, state: State, unit_id) -> bool:
        """`Contains(TargetTiles@0x190, Owner@0x148)` -- les tuiles-cible de l'evenement contiennent
        la tuile porteuse du ghost. Sur `On(0x24)`/`On(0x33)` ces tuiles sont celles ou l'unite vient
        d'arriver / d'apparaitre : le port les derive de sa `PositionComponent` (deja ecrite quand le
        natif emet ces events)."""
        if unit_id is None:
            return False
        return _tile_of(state, int(unit_id)) == int(self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if not _remove_ghost(state, self.owner_id):
            return None
        return {"ability": ABILITY_ID, "ghost_tile": int(self.owner_id),
                "ghost_removed": True, "on_event": int(ev.event_id)}


class GhostRemoveOnSourceMoves(_GhostRemoval):
    """Retrait n°1 : `On(0x1f = PreUnitMove, 1) & AreEqual(caster@0x160, EffectSource)` -- le poseur
    du ghost REBOUGE, l'ancien ghost part.

    ⚠ ORDRE avec la POSE (`GhostReviveAbility`, meme event) : `evaluate_trigger_operation` MATERIALISE
    le registre une fois en tete de dispatch (mirror du snapshot + `Queue.Clear` natif) -> le ghost
    POSE pendant ce dispatch n'y figure pas et ne peut donc pas s'auto-retirer, quel que soit l'ordre
    des deux entrees. Le cas de bord subsistant est le double-move DANS LE MEME TOUR sur la MEME tuile
    de debut de tour : `AddEffectOperation` no-ope (effet deja present) puis ce retrait le supprime.
    Residu documente -- une unite ne bouge qu'une fois par tour (flag `UnitFlag.Moved`)."""
    event_ids = (int(EventTriggerType.PreUnitMove),)
    event_id = int(EventTriggerType.PreUnitMove)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        src = self._source(state)
        return src is not None and ev.actor_id is not None and int(ev.actor_id) == int(src)


class GhostRemoveOnUnitAdded(_GhostRemoval):
    """Retrait n°2 : `On(0x33 = UnitAdded, 1) & NOT AreEqual(caster, EffectSource)
    & Contains(TargetTiles@0x190, Owner@0x148) & NOT HasTrait(caster, 0x1b = Steppable)` -- une AUTRE
    unite (non-Steppable) APPARAIT sur la tuile du ghost."""
    event_ids = (int(EventTriggerType.UnitAdded),)
    event_id = int(EventTriggerType.UnitAdded)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        actor = ev.actor_id
        src = self._source(state)
        if actor is None or (src is not None and int(actor) == int(src)):
            return False                                   # `NOT AreEqual(caster, EffectSource)`
        if not self._actor_is_on_my_tile(state, actor):
            return False
        # `NOT HasTrait(caster, Steppable)` : un decoy / une spore-mine ne dissipe pas le ghost.
        return not has_trait(_unit_trait_names(state, int(actor)), GHOST_UNIT_ADDED_EXCLUDED_TRAIT)


class GhostRemoveOnUnitEnters(_GhostRemoval):
    """Retrait n°3 : `On(0x24 = UnitPositionChanged_1, 1) & NOT AreEqual(caster, EffectSource)
    & Contains(TargetTiles@0x190, Owner@0x148)` -- une AUTRE unite ARRIVE sur la tuile du ghost.
    C'est le « the time ghost vanishes if the hex becomes occupied by another unit » de l'i2.
    Noter l'ABSENCE du gate `Steppable` ici (contraste avec le retrait n°2) : lu au decompile."""
    event_ids = (int(EventTriggerType.UnitPositionChanged_1),)
    event_id = int(EventTriggerType.UnitPositionChanged_1)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        actor = ev.actor_id
        src = self._source(state)
        if actor is None or (src is not None and int(actor) == int(src)):
            return False
        return self._actor_is_on_my_tile(state, actor)


class GhostRemoveOnSourceDeathInactive(_GhostRemoval):
    """Retrait n°4 : `OnDeath(1) & AreEqual(EffectSource, target@0x178)
    & NOT IsEffectActive(self@0x150)` -- le poseur meurt ALORS QUE l'effet est INACTIF.

    `IdunBattleLogic.Entities.DSLFactory$$IsEffectActive` lit le champ `Active` de l'`EffectComponent`
    (@+0x5c), que `ActivateEffectBehaviour` bascule. Le port materialise cet etat par
    `BaseEffect.active` ; un ghost fraichement pose est ACTIF -> ce retrait ne fire pas, et c'est
    `GhostEffectRevive` (le MEME event `On(1)`) qui prend la main. Le retrait n°4 est donc le
    complement exact de la resurrection : « le poseur meurt mais le ghost ne peut pas agir ».

    NB : `OnDeath(1)` = `OnDeathEvent(eventType = 0 = UnitDeath, ignoreOverkill = 1)`, un event
    NATIF DISTINCT du `OnPreDeath(1)` de la resurrection -- d'ou le vecteur `unit_death_triggers`."""
    event_ids = (int(EventTriggerType.UnitDeath),)
    event_id = int(EventTriggerType.UnitDeath)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        dying = ev.dying_id
        src = self._source(state)
        if dying is None or src is None or int(src) != int(dying):
            return False
        eff = _ghost_effect(state, self.owner_id)
        return eff is not None and not bool(getattr(eff, "active", True))   # `NOT IsEffectActive`


class GhostRemoveOnSourceRemoved(_GhostRemoval):
    """Retrait n°5 : `On(0x25 = UnitRemoved, 1) & AreEqual(EffectSource, target@0x178)` -- le poseur
    QUITTE le plateau.

    RESIDU ASSUME : le port n'a aucun emetteur d'`On(UnitRemoved)`
    (`IdunBattle.Operations.RemoveUnitOperation` n'est pas porte -- dans le runner isole les morts
    restent en place). Le trigger est enregistre et testable via `unit_removed_triggers`, mais aucun
    site de production ne l'atteint aujourd'hui."""
    event_ids = (int(EventTriggerType.UnitRemoved),)
    event_id = int(EventTriggerType.UnitRemoved)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        src = self._source(state)
        return (src is not None and ev.target_id is not None
                and int(ev.target_id) == int(src))
