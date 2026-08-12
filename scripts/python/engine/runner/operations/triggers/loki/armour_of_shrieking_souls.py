"""`ArmourOfShriekingSouls` (`TriggeredAbilityType 0x598 = 1432`, passif de kit d'`emperLucius`) --
la vengeance posthume : le TUEUR de Lucius est marque, saigne au debut de chacun de ses tours, et
c'est SA disparition qui fait revenir Lucius sur son hex.

i2 : << If Lucius is defeated by an enemy unit, that enemy becomes *Elated*. At the beginning of
each of its turns, the affected unit loses {minHp}-{maxHp} Health and when it is defeated or leaves
the battlefield, Lucius resurrects on the last hex the enemy was on with a maximum of {hp} Health. >>

===================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- recense par le bloc `methodPointers`
===================================================================================================

DEUX classes, DEUX registres (bases LUES dans `frida/classes.tsv`, jamais dans le nom du `.ctor`) :

  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArmourOfShriekingSoulsAbility`
      : `IdunBattle.Entities.Abilities.BaseTriggeredAbility`
      bloc = **4 slots / 3 corps PROPRES** : `[CreateTrigger, CreateBehaviour, Resurrect, .ctor]`,
      le `.ctor` FONDU par l'ICF (aucune ligne a lui dans `frida/methods.tsv`).
      `$$Resurrect` est **STATIQUE** (`dsl, resurrectTarget, targetTiles, abilityState, config`) et
      c'est ce qui compte : elle est appelee par DEUX proprietaires distincts -- le
      `CreateBehaviour` de l'ability ET le `CreateHandleTriggerAbilitiesInternal` de l'EFFET.

  `IdunBattle.Entities.Effects.Loki.ArmourOfShriekingSoulsEffect` : `IdunBattle.Entities.Effects.BaseEffect`
      bloc = **4 corps propres** : `[CreateTargetTriggerBehaviour, CreateTargetTrigger, .ctor,
      CreateHandleTriggerAbilitiesInternal]`.
      `$$.ctor` = `BaseEffect..ctor(AbilityOrEffect(0x58f = EffectType.ArmourOfShriekingSouls), true)`.

Slots `DSLSelectors` (`InitializeShared` relu : `+0x30 Owner · +0x38 Effect · +0x40 Actor ·
+0x48 Caster · +0x60 Target · +0x68 ActiveTarget · +0x78 TargetTiles`).

## `Ability$$CreateTrigger`

      OnDeathEvent( triggerType: 0 = EventTriggerType.UnitDeath,
                    triggerOnOverKill: true, triggerOnSteppable: false )
    & get_OwnerIsTarget
    & IsUnit( Actor@+0x40 )
    & AreEnemies( Actor@+0x40, Owner@+0x30, UnitTeamSelectionType 0 )

⚠ Le 3e conjoint est un **mislabel ICF** dans le pseudo-C
(`UnityEngine.Scripting.RequiredByNativeCodeAttribute$$.ctor`) : son pointeur de classe
(`DAT_1833ab7f8`) n'est partage qu'avec `IdunBattleLogic.Entities.DSLTriggers$$IsUnit(selector)` --
c'est donc `IsUnit(Actor)`, pas un attribut Unity. Resolu par recherche LITTERALE du `DAT_` dans le
decompile, pas par le nom affiche.

⚠ `triggerOnOverKill: true` **DESARME** le gate d'overkill d'`OnDeathEvent` (il devient la
constante VRAIE) : contrairement a `ObsessiveAnnunciation`, aucun `TargetIsOverkilled()` SEPARE ne
le re-exige -- Lucius revient qu'il ait ete overkill ou non. `triggerOnSteppable: false` laisse le
gate `NOT HasTrait(Target@+0x60, 0x1b = Steppable)`.

## `Ability$$CreateBehaviour`

    If( NOT IsAlive( Actor@+0x40 ),
        Resurrect( dsl, resurrectTarget: Owner@+0x30, targetTiles: Tiles(Actor@+0x40),
                   abilityState: Direct(AbilityStateReference(abilityState)), config ),
        AddEffect( 0x58f = EffectType.ArmourOfShriekingSouls,
                   abilityState: get_AbilityStateReference(),
                   source: Target@+0x60, targets: Actor@+0x40, options: null ) )

Le tueur est encore VIVANT dans le cas nominal -> branche ELSE : il recoit l'effet (<< that enemy
becomes Elated >>). Si le tueur est mort dans le meme echange (mort simultanee), le natif court-
circuite et ressuscite Lucius TOUT DE SUITE sur les tuiles du tueur -- l'effet ne serait porte par
personne. `source = Target@+0x60` : sur cet evenement `OwnerIsTarget` vient d'etre exige, donc la
source de l'effet EST Lucius, ce que relit ensuite `EffectSource(Effect@+0x38)`.

## `Ability$$Resurrect` (STATIQUE, partagee)

    tile = PickRandomly( FreeTilesOrAdjacentFreeTiles(targetTiles),
                         amount: 1, allowDuplicates: false,
                         maxDuplicatesAllowed: 0x7fffffff, ignoreForcedTargets: false )
    hp   = ConfigVar( 0x1d = AbilityVariableType.hp, abilityState, config )
    res  = Resurrect( targets: resurrectTarget, targetTiles: tile, hp: hp,
                      healType: 2, abilityType: Nullable(AbilityType(0x598 = 1432)), options: null )
    return If( NOT AmountIsZero( Filter( PlayersByTeam(resurrectTarget),
                                         NOT IsPlayerDefeated(ActiveTarget@+0x68) ) ),
               res, null )

`IsPlayerDefeated` est le SECOND mislabel ICF
(`System.Linq.Expressions.Interpreter.QuoteInstruction$$.ctor`) : `DAT_1833aac70` n'est partage
qu'avec `IdunBattleLogic.Entities.DSLTriggers$$IsPlayerDefeated(player)`. Le gate dit donc :
<< il reste au moins un joueur NON DEFAIT dans l'equipe de Lucius >>.

## `Effect$$CreateTargetTrigger` / `$$CreateTargetTriggerBehaviour`

    On( 0x16 = EventTriggerType.TurnStart_Actions, ownerNeedsToBeAlive: true )
      & <DSLTriggers+0x28>
    ->
    DirectDamage( caster: EffectSource( Get(effect) ), target: Owner@+0x30,
                  amount: RandomAmount( ConfigVar(0x25 = minHp), ConfigVar(0x95 = maxHp) ),
                  abilityOrEffect: AbilityOrEffect(this = 0x58f), selectionType: 3, options: <zero> )

`<DSLTriggers+0x28>` est un CHAMP, pas un appel : `DSLTriggers$$InitializeShared` l'initialise avec
`<DAT_1833ab568>(Owner@DSLSelectors+0x30, state)`, et ce pointeur de classe n'est partage qu'avec
`IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf(selector)` -> le champ est
**`IsTurnOf(Owner@+0x30)`** (voisins du meme bloc : `+0x30 = On(0x21) & OwnerIsActor`,
`+0x38 = On(0x41) & OwnerIsActor`). C'est le << at the beginning of each of ITS turns >> de l'i2.

## `Effect$$CreateHandleTriggerAbilitiesInternal` -- DEUX `Triggered()` de plus

    1)  On(0x25 = UnitRemoved) & get_OwnerIsTarget & IsDead( Owner@+0x30 )
        -> Resurrect( dsl, resurrectTarget: EffectSource(Effect@+0x38),
                      targetTiles: Tiles(Owner@+0x30), GetAbilityState(), config )

    2)  On(0x2e = UnitResurrected)
        & AreEqual( EffectSource(Effect@+0x38), Target@+0x60 )
        -> GetRemoveEffectBehaviour()

Le (1) est le coeur du passif : quand la victime *Elated* est RETIREE du plateau, Lucius revient sur
SES tuiles -- `resurrectTarget` et `targetTiles` sont donc EXACTEMENT INVERSES par rapport au
`CreateBehaviour` de l'ability, qui, lui, fait revenir Lucius sur les tuiles du tueur. Recopier
l'un sur l'autre aurait fait ressusciter la mauvaise unite au mauvais endroit.
Le (2) nettoie : des que Lucius (= la SOURCE de l'effet) est ressuscite, l'effet quitte sa victime.

===================================================================================================
FORME DU PORT (doctrine #149) ET RESIDUS NOMMES
===================================================================================================
* les quatre `CreateTrigger`/target-trigger COLLAPSENT dans `matches` (idiome du repo) ;
* les behaviours sont des ARBRES DSL dont les feuilles (`AddEffect`, `Resurrect`, `DirectDamage`,
  `RemoveEffect`) appellent leurs Operations. `DirectDamage` est un noeud NEUF (`abilities/
  behaviours/combat.py`) : c'est la premiere feuille du port a mirrorer vraiment
  `IdunBattle.Operations.DirectDamageOperation`.

RESIDUS :
* **`IsPlayerDefeated`** n'a pas de noeud porte. `IdunBattle.Entities.PlayerExtensions$$
  IsPlayerDefeated(player, state, countSummons, countObjects)` a TROIS branches -- drafts restants
  (`DraftingComponent$$HasRemainingDrafts && CanDraft`), unites en attente de spawn
  (`PlayerComponent$$HasPendingUnitsToSpawn`), unites originellement possedees encore la
  (`HasOriginallyOwnedUnits`) -- dont seule la derniere est modelisable ici. Le port approxime par
  << l'equipe de `resurrectTarget` compte au moins une unite VIVANTE >>. Sens de la degradation :
  RESTRICTIF (un joueur sans unite vivante mais avec des drafts restants serait tenu pour defait).
* **profil de degat du DoT** : la factory native `DirectDamage` n'en prend PAS et la struct
  `options` du call-site est integralement zeroee -> le port passe `profile=None`, donc
  `PiercingRatio = 0` (degat entierement soumis a l'armure). La face `CalculateDirectDamage` sur
  profil NUL n'a pas ete RE-derivee : c'est le premier ecart a mesurer si le montant live diverge.
* **`abilityType: Nullable(AbilityType(1432))`** du `Resurrect` : le behaviour porte ne modelise
  pas ce canal d'attribution (residu deja nomme dans sa docstring, inchange ici).
* **`matchAbilityEntities` / `ignoreForcedTargets` / `maxDuplicatesAllowed`** : transcrits, non
  portes (sans objet pour `amount = 1` sans duplicata).
* **face DECISION** : `ArmourOfShriekingSoulsAbility` n'a **aucun playbook** dans le build (seul
  `IdunBattle.View.AbilityConfigs.Loki.ArmourOfShriekingSouls{Visuals,EffectVisuals}` existe, et la
  couche View n'est pas portee) -- il n'y a donc rien a porter de ce cote, ce n'est pas un manque.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_variable_type import AbilityVariableType
from .....entities.behaviours import If as IfBehaviour
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import RandomAmount
from .....entities.selectors.accessors import Actor, Target
from .....entities.selectors.geometry import Entity, Otherwise, PickRandomly
from .....entities.selectors.tiles import AdjacentTiles, CanAddUnit, Caster
from .....entities.selectors.units import Tiles
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import HasTrait, IsAlive
from ....abilities.behaviours.combat import DirectDamage
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect, RemoveEffect
from ....abilities.behaviours.lifecycle import Resurrect
from ....components import OwnerComponent, UnitComponent
from ....state import State
from ..base import EffectTrigger, TriggeredAbility, TriggerEvent

#: cle gameconfig (minHp / maxHp / hp) ET nom de l'ability.
ABILITY_ID = "ArmourOfShriekingSouls"
#: `TriggeredAbilityType.ArmourOfShriekingSouls` = `0x598` = 1432 -- le litteral que
#: `$$Resurrect` passe a `AbilityType$$op_Implicit` pour son `Nullable<AbilityType>`.
ARMOUR_ABILITY = int(TriggeredAbilityType.ArmourOfShriekingSouls)
#: `EffectType.ArmourOfShriekingSouls` = `0x58f` = 1423 -- l'effet << Elated >> pose sur le TUEUR.
ELATED_EFFECT = int(EffectType.ArmourOfShriekingSouls)
ELATED_EFFECT_NAME = EffectType.ArmourOfShriekingSouls.name
#: alias exporte pour la cle d'`EFFECT_TRIGGERS` (meme convention que les autres lots).
ARMOUR_OF_SHRIEKING_SOULS_EFFECT = ELATED_EFFECT
#: `HealType 2` -- le 4e argument du `Resurrect` natif, LU au desassemblage (`mov dword ptr
#: [rsp + 0x20], 2`), jamais deduit.
RESURRECT_HEAL_TYPE = 2
#: `steppableGate` d'`OnDeathEvent(0, a, b = false)` = `NOT HasTrait(Target@+0x60, 0x1b)`.
_TARGET_IS_STEPPABLE = HasTrait(Target(), int(UnitTrait.Steppable))
#: `NOT IsAlive(Actor@+0x40)` -- la CONDITION du `If` du `CreateBehaviour`.
_ACTOR_IS_ALIVE = IsAlive(Actor())


def _effect_source(state: State, owner_id: int) -> Optional[int]:
    """`EffectSource( Effect@DSLSelectors+0x38 )` -- l'entite qui a POSE l'instance de 1423 portee
    par `owner_id`, c'est-a-dire Lucius.

    COLLAPSE IMPERATIF assume : le noeud `EffectSource()` du port lit `ctx.effect`, que
    `entities_from_state` ne thread PAS (aucun parametre `effect`). On resout donc l'instance dans
    `EffectsState.by_unit` -- la MEME donnee (`BaseEffect.source`), lue une case plus tot. None si
    l'effet n'est plus la."""
    if state.effects is None:
        return None
    for e in state.effects.by_unit.get(int(owner_id), []):
        if not e.consumed and int(e.effect_type) == ELATED_EFFECT:
            return None if e.source is None else int(e.source)
    return None


def _elated_instance(state: State, owner_id: int):
    """L'instance de 1423 portee par `owner_id` (celle dont `GetAbilityState()` fournit le niveau
    aux trois `ConfigVar`). None si absente."""
    if state.effects is None:
        return None
    for e in state.effects.by_unit.get(int(owner_id), []):
        if not e.consumed and int(e.effect_type) == ELATED_EFFECT:
            return e
    return None


def armour_var(key: str, level: Optional[int]) -> int:
    """`ConfigVar(<key>, GetAbilityState(), config)` = `AbilityConfiguration$$GetVariableForLevel`
    sur le gameconfig d'`ArmourOfShriekingSouls`, indexe par le niveau BAKE dans l'instance d'effet
    (`AbilityStateReference` -> `scale_from_source`). Les trois cles sont qualifiees par
    `AbilityVariableType` (`0x25 = minHp`, `0x95 = maxHp`, `0x1d = hp`), et les trois sont listees
    dans `variablesAffectedByRarityBonus` -- `ability_var` applique donc le meme
    `AbilityVariablesMultiplier` que le natif. Niveau absent -> `ability_var` retombe sur le defaut
    du gameconfig ; valeur illisible -> 0 (aucune magnitude inventee)."""
    return int(ability_var(ABILITY_ID, key, level) or 0)


def _team_has_living_unit(state: State, unit_id: int) -> bool:
    """Approximation portee de `NOT AmountIsZero( Filter( PlayersByTeam(resurrectTarget),
    NOT IsPlayerDefeated(It) ) )` -- cf. le residu nomme dans l'en-tete de module. On teste
    << l'equipe de `unit_id` compte au moins une unite vivante >> ; les deux autres branches natives
    (drafts restants, unites en attente de spawn) ne sont pas modelisables offline."""
    ent = state.get_entity(unit_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    if oc is None:
        return False
    for eid, e in state.entities.items():
        if int(eid) == int(unit_id):
            continue                                  # le ressuscite est MORT : il ne se compte pas
        uc, o2 = e.get_component(UnitComponent), e.get_component(OwnerComponent)
        if uc is not None and uc.alive and o2 is not None and o2.team == oc.team:
            return True
    return False


def armour_resurrect_tree(resurrect_target_id: int, tiles_of_id: int, hp: int, rng):
    """`ArmourOfShriekingSoulsAbility$$Resurrect` (statique), noeud pour noeud :

        Resurrect( targets: <resurrectTarget>,
                   targetTiles: PickRandomly(FreeTilesOrAdjacentFreeTiles(<targetTiles>), 1, false,
                                             0x7fffffff, false),
                   hp: ConfigVar(0x1d = hp), healType: 2, abilityType: Nullable(1432), options: null )

    `FreeTilesOrAdjacentFreeTiles(tiles)` est DEPLIE en son corps natif --
    `Otherwise( CanAddUnit(tiles, isSteppable), CanAddUnit(AdjacentTiles(tiles), isSteppable) )`
    avec `isSteppable = <DSLTriggers+0x48> = op_LogicalNot(YesTrigger)` donc TOUJOURS VRAI a ce
    call-site -- meme depliage, meme lecture et meme call-site-type que `Possession` (#955).

    Les DEUX sélecteurs d'entite sont COLLAPSES en `Entity(<id>)` : le natif recoit ici des
    SELECTEURS (`Owner@+0x30` ou `EffectSource(Effect@+0x38)` selon l'appelant), mais `$$Resurrect`
    est STATIQUE et les recoit en PARAMETRE -- c'est l'appelant qui choisit, et le port fait le
    meme choix a l'appel plutot que de rebatir deux arbres.

    Le gate `If(NOT AmountIsZero(Filter(PlayersByTeam, NOT IsPlayerDefeated)), res, null)` vit chez
    l'appelant (`_team_has_living_unit`), pas dans cet arbre : c'est un collapse imperatif, cf. le
    residu nomme."""
    tiles = Tiles(Entity(tiles_of_id), as_ids=True)
    free = Otherwise(CanAddUnit(tiles, allow_steppable=True),
                     CanAddUnit(AdjacentTiles(tiles), allow_steppable=True))
    return Resurrect(Entity(resurrect_target_id), PickRandomly(free, 1), int(hp),
                     heal_type=RESURRECT_HEAL_TYPE)


class ArmourOfShriekingSoulsOnDeathAbility(TriggeredAbility):
    """`ArmourOfShriekingSoulsAbility` -- Lucius tombe : son tueur devient *Elated*
    (`AddEffect(0x58f, source = Lucius, targets = le tueur)`), ou, si le tueur est deja mort,
    Lucius ressuscite immediatement sur les tuiles du tueur.

    `fire_on_death` : `get_OwnerIsTarget` sur `On(UnitDeath)` -> le porteur EST le mourant, donc
    `alive == False` au dispatch. Sans lui, `CanGetAbilityTrigger` ecarterait le trigger et le
    passif ne firerait JAMAIS (meme raison que `HaywireMine` / `FinalJustice`)."""
    event_id = int(EventTriggerType.UnitDeath)         # OnDeathEvent(0, overKill: 1, steppable: 0)
    TRIGGERED_ABILITY_ID = ARMOUR_ABILITY              # 1432
    fire_on_death = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsTarget` : le porteur est la victime (`unit_death_triggers` pose
        # `target = dying`).
        victim = ev.dying_id if ev.dying_id is not None else ev.target_id
        if victim is None or int(victim) != int(self.owner_id):
            return False
        killer = ev.killer_id if ev.killer_id is not None else ev.actor_id
        if killer is None or int(killer) == int(self.owner_id):
            return False
        owner, actor = state.get_entity(self.owner_id), state.get_entity(killer)
        if owner is None or actor is None:
            return False
        entities = entities_from_state(state, self.owner_id, self.owner_id, actor_id=killer)
        # `steppableGate` d'`OnDeathEvent(0, a, b = false)` -- porte sur `Target@+0x60`, ici Lucius.
        if _TARGET_IS_STEPPABLE.should_trigger(entities):
            return False
        # `IsUnit(Actor@+0x40)` : le tueur doit etre une UNITE (une tuile piegee, une entite-effet
        # ou l'absence de tueur ne declenchent rien). Meme granularite que le gate ci-dessus.
        if actor.get_component(UnitComponent) is None:
            return False
        # `AreEnemies(Actor@+0x40, Owner@+0x30, UnitTeamSelectionType 0 = ByCurrentTeam)` -- c'est le
        # << defeated by an ENEMY unit >> : un kill par un allie (ou par soi-meme) ne declenche PAS.
        oo, ao = owner.get_component(OwnerComponent), actor.get_component(OwnerComponent)
        return oo is not None and ao is not None and oo.team != ao.team

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        killer = int(ev.killer_id if ev.killer_id is not None else ev.actor_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, self.owner_id, actor_id=killer)
        # `If( NOT IsAlive(Actor@+0x40), Resurrect(...), AddEffect(0x58f, ...) )`. La branche THEN
        # (tueur deja mort) porte le gate `PlayersByTeam/IsPlayerDefeated` de `$$Resurrect`, evalue
        # ICI comme chez l'appelant natif.
        actor_alive = _ACTOR_IS_ALIVE.should_trigger(entities)
        if not actor_alive:
            lvl = None
            hp = armour_var(AbilityVariableType.hp.name, lvl)
            if not _team_has_living_unit(state, int(self.owner_id)):
                return {"ability": ABILITY_ID, "owner": int(self.owner_id), "killer": killer,
                        "branch": "resurrect", "resurrected": [], "gate": "team_defeated"}
            armour_resurrect_tree(int(self.owner_id), killer, hp, state.rng).execute(entities, ectx)
            res = next((p for n, p in ectx.emitted if n == "Resurrect"), None)
            return {"ability": ABILITY_ID, "owner": int(self.owner_id), "killer": killer,
                    "branch": "resurrect", "hp": hp,
                    "resurrected": (res or {}).get("resurrections") or []}
        # `AddEffect(0x58f, AbilityStateReference, source = Target@+0x60 = Lucius,
        #            targets = Actor@+0x40 = le tueur, options: null)`. `scale_from_source=True`
        # porte l'`AbilityStateReference` : sans lui l'instance n'a pas d'`ability_level` et les
        # TROIS `ConfigVar` de l'effet (minHp/maxHp/hp) resteraient inertes.
        # `duration_rounds=None` = l'options-struct NULLE du natif -> `DefaultAmountOfRounds(1423)`,
        # absent de la table -> PERMANENT : l'effet ne se retire que par son propre trigger (2).
        AddEffect(ELATED_EFFECT, ELATED_EFFECT_NAME, Actor(),
                  duration_rounds=None, scale_from_source=True).execute(entities, ectx)
        placed = [p for n, p in ectx.emitted if n == "AddEffect" and p.get("placed")]
        return {"ability": ABILITY_ID, "owner": int(self.owner_id), "killer": killer,
                "branch": "add_effect", "elated": bool(placed)}


class ArmourOfShriekingSoulsDrainOnTurnStart(EffectTrigger):
    """`Effect$$CreateTargetTrigger` + `$$CreateTargetTriggerBehaviour` : la victime *Elated* saigne
    au debut de CHACUN de ses tours.

    `On(0x16 = TurnStart_Actions, ownerNeedsToBeAlive: true) & <DSLTriggers+0x28 =
    IsTurnOf(Owner@+0x30)>` -> `DirectDamage(EffectSource(effet), Owner, RandomAmount(minHp, maxHp),
    AbilityOrEffect(0x58f), 3, <options zeroees>)`."""
    event_id = int(EventTriggerType.TurnStart_Actions)   # On(0x16 = 22)
    effect_type = ELATED_EFFECT
    TRIGGERED_ABILITY_ID = ARMOUR_ABILITY

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # Gate `EffectComponent.IsActive @+0x5c` (#231, pose ici par #962) -- ce trigger vient de
        # `IdunBattle.Entities.Effects.Loki.ArmourOfShriekingSoulsEffect$$CreateTargetTrigger`
        # (decompile : `On(0x16, ownerNeedsToBeAlive: 1) op_BitwiseAnd <DSLTriggers+0x28>`), donc du
        # rail que `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets`
        # gate AVANT d'appeler `ShouldTrigger` : sa boucle PAR CIBLE recharge l'`EffectComponent` et
        # n'evalue rien `if (*(char *)(<component> + 0x5c) == '\0')`. C'est le gate du rail TARGETS
        # SEUL -- `EvaluateEffectTriggerEffectAbilities`, la voie des deux `Triggered()` ci-dessous,
        # n'accede JAMAIS a `+0x5c` (case-229). Sans lui, la victime saignerait encore alors que son
        # `Elated` est DESACTIVE : ni erreur, ni crash, juste un tick de trop.
        inst = _elated_instance(state, self.owner_id)
        if inst is None or not inst.active:
            return False
        # `IsTurnOf(Owner@+0x30)` -- `start_turn_triggers` porte le JOUEUR dont le tour debute ;
        # `IdunBattle.Entities.Triggers.IsTurnOfTrigger` compare le joueur courant a celui du
        # selecteur. Non threade -> FAUX (on ne fabrique pas un tour).
        if ev.player_id is None:
            return False
        ent = state.get_entity(self.owner_id)
        oc = ent.get_component(OwnerComponent) if ent is not None else None
        if oc is None or int(oc.player) != int(ev.player_id):
            return False
        uc = ent.get_component(UnitComponent)
        return uc is not None and uc.alive          # `ownerNeedsToBeAlive: true`

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        src = _effect_source(state, self.owner_id)
        eff = _elated_instance(state, self.owner_id)
        if src is None or eff is None:
            return None
        lvl = getattr(eff, "ability_level", None)
        lo = armour_var(AbilityVariableType.minHp.name, lvl)
        hi = armour_var(AbilityVariableType.maxHp.name, lvl)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, self.owner_id)
        # `RandomAmount(min, max)` = `rng.next_internal(min, max + 1)` -- bornes INCLUSIVES, un
        # tirage par tick. `caster = EffectSource(...)` = Lucius (l'attribution de la mort lui
        # revient), `target = Owner@+0x30` = la victime.
        DirectDamage(Caster(), RandomAmount(Const(lo), Const(hi), state.rng),
                     source_sel=Entity(src), ability_type=ELATED_EFFECT).execute(entities, ectx)
        hit = next((p for n, p in ectx.emitted if n == "DirectDamage"), None)
        return {"effect": ELATED_EFFECT_NAME, "unit": int(self.owner_id), "source": src,
                "min": lo, "max": hi, "dot": (hit or {}).get("total"),
                "attack": (hit or {}).get("attack"), "on_event": int(ev.event_id)}


class ArmourOfShriekingSoulsResurrectOnRemoved(EffectTrigger):
    """1er `Triggered()` de `Effect$$CreateHandleTriggerAbilitiesInternal` :
    `On(0x25 = UnitRemoved) & get_OwnerIsTarget & IsDead(Owner@+0x30)` ->
    `Resurrect(dsl, resurrectTarget = EffectSource(Effect@+0x38), targetTiles = Tiles(Owner@+0x30),
    GetAbilityState(), config)`.

    ⚠ Les deux selecteurs sont EXACTEMENT INVERSES par rapport au `CreateBehaviour` de l'ability :
    ici c'est **Lucius** (la source de l'effet) qu'on ressuscite, sur les tuiles de **la victime**.

    `fire_on_death` : le porteur de l'effet est l'unite RETIREE, donc `alive == False` -- le gate
    `IsDead(Owner)` du natif l'exige explicitement, et le gate de vivacite du dispatch l'ecarterait."""
    event_id = int(EventTriggerType.UnitRemoved)        # On(0x25 = 37)
    effect_type = ELATED_EFFECT
    TRIGGERED_ABILITY_ID = ARMOUR_ABILITY
    fire_on_death = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsTarget` : `unit_removed_triggers` pose `actor = target = l'unite retiree`.
        if ev.target_id is None or int(ev.target_id) != int(self.owner_id):
            return False
        # `IsDead(Owner@+0x30)`.
        ent = state.get_entity(self.owner_id)
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if uc is not None and uc.alive:
            return False
        return _effect_source(state, self.owner_id) is not None

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        src = _effect_source(state, self.owner_id)
        eff = _elated_instance(state, self.owner_id)
        if src is None:
            return None
        lvl = getattr(eff, "ability_level", None) if eff is not None else None
        hp = armour_var(AbilityVariableType.hp.name, lvl)
        if not _team_has_living_unit(state, src):
            return {"effect": ELATED_EFFECT_NAME, "unit": int(self.owner_id), "source": src,
                    "resurrected": [], "gate": "team_defeated"}
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, src, int(self.owner_id))
        armour_resurrect_tree(src, int(self.owner_id), hp, state.rng).execute(entities, ectx)
        res = next((p for n, p in ectx.emitted if n == "Resurrect"), None)
        return {"effect": ELATED_EFFECT_NAME, "unit": int(self.owner_id), "source": src, "hp": hp,
                "resurrected": (res or {}).get("resurrections") or [],
                "on_event": int(ev.event_id)}


class ArmourOfShriekingSoulsRemoveOnSourceResurrected(EffectTrigger):
    """2e `Triggered()` de `Effect$$CreateHandleTriggerAbilitiesInternal` :
    `On(0x2e = UnitResurrected) & AreEqual(EffectSource(Effect@+0x38), Target@+0x60)` ->
    `GetRemoveEffectBehaviour()`.

    Des que Lucius revient, l'effet quitte sa victime -- sinon elle continuerait a saigner pour un
    mort qui n'en est plus un, et un second retrait le ferait ressusciter une fois de trop."""
    event_id = int(EventTriggerType.UnitResurrected)    # On(0x2e = 46)
    effect_type = ELATED_EFFECT
    TRIGGERED_ABILITY_ID = ARMOUR_ABILITY

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `AreEqual(EffectSource(Effect@+0x38), Target@+0x60)` : le ressuscite est la SOURCE de
        # l'effet. `AreEqual` est SYMETRIQUE -- l'ordre des arguments ne porte aucun sens ici.
        if ev.target_id is None:
            return False
        src = _effect_source(state, self.owner_id)
        return src is not None and int(src) == int(ev.target_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, self.owner_id)
        # `BaseEffect$$GetRemoveEffectBehaviour` = `RemoveEffect(<ce type>, <le porteur>)`.
        RemoveEffect(ELATED_EFFECT, Caster()).execute(entities, ectx)
        removed = [p for n, p in ectx.emitted if n == "RemoveEffect"]
        return {"effect": ELATED_EFFECT_NAME, "unit": int(self.owner_id),
                "removed": sum(int(p.get("removed") or 0) for p in removed),
                "on_event": int(ev.event_id)}
