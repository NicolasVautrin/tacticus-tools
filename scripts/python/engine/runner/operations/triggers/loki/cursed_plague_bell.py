"""`CursedPlagueBellMovementAbility` -- le volet MOUVEMENT du passif `CursedPlagueBell` (1071) de
`deathBlightbringer` / Corrodius (Death Guard, POOL-HERO rank 17).

i2 : « Friendly Chaos units STARTING THEIR TURN within Corrodius' Contagion aura gain +1 Movement
for this turn. » -- ce module porte la POSE (le trigger + l'arbre de cibles + l'`AddEffect`) ;
l'EFFET pose (`CursedPlagueBell_ExtraMove` 0x431=1073, `...$$AddStatModifier` = le +1 Movement) est
une tranche SEPAREE, non portee ici.

NB PLACEMENT : `IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellMovementAbility` est
dans le namespace `Abilities.Active.Loki` mais derive de `IdunBattle.Entities.Abilities.
BaseTriggeredAbility` (releve `classes.tsv` du build : parent direct, et `BaseTriggeredAbility`
derive de `System.Object`, PAS d'`AActiveAbility`) -- exactement comme `DestroyerHiveAbility`,
`FireOfAbsolution`, `ControlEdict`. C'est donc un PASSIF TRIGGERED : il entre au registre
`ABILITY_TRIGGERS` (cle = `units.passiveAbilities` = `CursedPlagueBell`), PAS dans
`handler.ABILITY_CLASSES` (reserve aux ACTIVES).
=> Corollaire : NI `TARGETING_OPTIONS` NI `ABILITY_ATTACK_TYPE` ne s'appliquent. Ces deux donnees
sont celles que `AActiveAbility$$.ctor` recoit (`TargetingOptions$$.ctor` + 3e argument
`AbilityAttackType`) ; `BaseTriggeredAbility$$Init(abilityConfigId, dsl, query, state, config,
operationProcessor, effectsDatabase, logger)` n'en prend AUCUNE, et la classe n'a ni `.ctor` propre
ni champ de ciblage. Les deux regles de non-regression du CLAUDE.md portent sur `ABILITY_CLASSES` :
elles sont SANS OBJET ici, et `probe_120` / `probe_181` le verifient (aucune entree ajoutee).

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- TROIS fonctions natives NOMMEES
================================================================================================

## 1. `...CursedPlagueBellMovementAbility$$CreateTrigger`

    On(TurnStart_Other = 0x13 = 19, 1) & <DSLTriggers+0x28 = OwnerIsActor>

Le CORPS est PARTAGE (dedup IL2CPP de corps identiques) avec
`IdunBattleLogic.Entities.Abilities.Active.Loki.RelentlessMarchAbility$$CreateTrigger`, qui en est
le PROPRIETAIRE dans les tables indexees par adresse. Deux elements l'etablissent, aucun n'est une
deduction depuis l'absence :
  * le BLOC de classe est contigu dans `ghidra/functions.tsv` -- `CursedPlagueBellMovementAbility
    $$CreateBehaviour`, puis le corps attribue a `RelentlessMarchAbility$$CreateTrigger`, puis
    `CursedPlagueBellMovementAbility$$GetTargetsSelector` : la place du `CreateTrigger` de CETTE
    classe, dans SON bloc ;
  * `BaseTriggeredAbility$$GetTrigger` appelle le slot de vtable `+0x2d8` (`CreateTrigger`) et la
    base n'a AUCUN corps propre (abstraite) -> la classe DOIT en avoir un.
`<DSLTriggers+0x28>` = le meme slot que `...LivingMetalRepairAbility$$CreateTrigger` (`+0x28 &
On(0x13,1) & IsDamaged(Owner)`), que le port nomme `OwnerIsActor` et qui est PROUVE LIVE (#203,
probe_203 : la regen ne fire QU'AU tour du proprietaire). Porte = `ev.player_id ==
OwnerComponent.player`. Vecteur = `turn_start_other_triggers` (dispatch/turn.py).

## 2. `...CursedPlagueBellMovementAbility$$GetTargetsSelector(dsl, isDangerZone)`

    range   = DSLFormulas.ContagionsOfNurgleRange(unit = Owner,
                                                  unitSelectionType = 0 = Any,
                                                  isNextTurn = isDangerZone)
    targets = UnitsWithoutTrait(
                UnitsWithTrait(
                  SurroundingFriends(unit = Owner, range = range, unique = true,
                                     unitSelectionType = 3 = OnlyAliveAndTargetable),
                  trait = 0x7ea = UnitTrait.Chaos,      selectionType = 3),
                trait = 0x418 = UnitTrait.Stationary,   selectionType = 3)

`Owner` = `DSLSelectors+0x30`, le meme slot que `LivingMetalRepairAbility` passe a `IsDamaged` et
que `RelentlessMarchAbility` passe a `AdjacentUnits`/`Friends`.

`DSLSelectors$$SurroundingFriends(unit, range:IAmountFormula, unique, selType)` se DEPLIE en
    `Friends( of = unit,
              Units( SurroundingTiles(unit, includeCenter=1, range) - Tiles(unit), unique, selType ),
              selType )`
-> disque hex de rayon `range` autour de l'Owner, **centre EXCLU** (la soustraction `- Tiles(unit)`),
filtre ALLIES de l'Owner.

## 3. `...CursedPlagueBellMovementAbility$$CreateBehaviour(abilityState, triggerType)`

    AddEffect( effectType   = 0x431 = 1073 = EffectType.CursedPlagueBell_ExtraMove,
               abilityState = BaseTriggeredAbility.get_AbilityStateReference(this),
               targets      = <l'arbre du 2., avec isNextTurn = false>,
               turns        = Nullable<int>(1) )

C'est l'overload `DSLBehaviors$$AddEffect(effectType, abilityState, targets, turns:Nullable<Int32>)`
(4 parametres) : la duree est deja en TOURS -> `duration_turns=1`, JAMAIS `TurnsFromRounds`.
Le behaviour ne lit PAS `triggerType` (aucune branche, contrairement a `RelentlessMarchAbility`).

## 4. `DSLFormulas$$ContagionsOfNurgleRange(unit, unitSelectionType, isNextTurn)`

    = new IdunBattle.Entities.Triggers.AuraEffectRangeFormula(
            effects, unit, effectType = 0x42f = EffectType.ContagionsOfNurgle_ArmorReduction1,
            unitSelectionType, isNextTurn)

et `AuraEffectRangeFormula$$Calculate(entities)` :
    unit = <selecteur `unit`>.Select(entities)
    if (unit == null) return 0
    def = effectsDatabase.Get(0x42f)                       // IAuraEffect
    if (!UnitExtensions.HasTrait(unit, def.GetTrait())) return 0
    entities.<slot Owner> = unit                           // re-ancrage
    return (isNextTurn ? def.GetNextTurnRange() : def.GetCurrentRange()).Calculate(entities)

L'implementation `IAuraEffect` est `IdunBattle.Entities.Effects.Loki.
ContagionsOfNurgle_ArmorReduction_Effect` :
    `$$GetTrait`          = `return 0x7eb` (= `UnitTrait.ContagionsOfNurgle`, 2027) -- LITTERAL ;
    `$$GetCurrentRange`   = `GetRangeOnOwnerTurn( StatAmount(Owner, 0xc=TurnsStarted, part 0) )` ;
    `$$GetNextTurnRange`  = `GetRangeOnOwnerTurn( Sum(StatAmount(Owner, 0xc, 0), Direct(1)) )` ;
    `$$GetRangeOnOwnerTurn(n)` = la table 1 / 2 / 3 aux seuils 2 et 4
        (foyer partage du port : `runner/abilities/deathguard.contagions_of_nurgle_range_for_turns`).

⚠ QUALIFICATION D'ENUM -- `0x42f` vaut 1071 dans DEUX enums distincts et les deux apparaissent
dans ce cas : `TriggeredAbilityType.CursedPlagueBell` (l'id du PASSIF) et
`EffectType.ContagionsOfNurgle_ArmorReduction1` (celui que lit `ContagionsOfNurgleRange`).
Ici c'est l'EffectType.

================================================================================================
FORME DU PORT
================================================================================================
DOCTRINE #149 : l'artefact natif est un `CreateBehaviour`/`GetTargetsSelector` -> ARBRE DSL. Les
predicats du `CreateTrigger` (`On` + `OwnerIsActor`) sont collapses imperativement dans `matches`
(comme LivingMetal / DestroyerHive) ; l'arbre, lui, est construit de noeuds EXISTANTS
(`SurroundingFriends`, `UnitsWithTrait`, `UnitsWithoutTrait`, feuille `AddEffect`) -- aucun
recablage a la main du ciblage.

SUBSTRAT DES TROIS GATES DE TRAIT (`Chaos`, `Stationary`, et le `ContagionsOfNurgle` de la formule
d'aura) : tous passent par `ctx.has_trait`, donc par `UnitContext.traits`, que `load_state` seede
depuis `combatSnapshot.units[].traits` depuis #264/#270 -- l'ensemble EFFECTIF invoque de
`IdunBattle.Entities.UnitExtensions$$HasTrait`, et non plus une reconstruction depuis le kit
gameconfig. C'est la MEME source que celle qu'interroge le natif ; les traits d'ALLIANCE (`Chaos`)
comme ceux poses EN BATAILLE (`Stationary` d'un summon `Movement = 0`) y sont.

RESIDUS EXPLICITES :
 * `unitSelectionType = 3 = OnlyAliveAndTargetable` : le port n'honore que le volet ALIVE
   (`_within` filtre les cadavres). Le volet TARGETABLE (`UnitBecameUntargetable` / deep-strike en
   cours d'atterrissage) n'est materialise nulle part cote port -> une unite VIVANTE mais
   non-ciblable serait comptee. Meme residu que tous les selecteurs d'occupation du port.
 * `unique = true` : `_within` ne peut pas produire de doublon (une unite = une position), le flag
   est donc sans effet observable ici.
 * `SurroundingFriends` du port prend `ctx.caster` comme reference de camp, la ou le natif prend
   son parametre `unit` (= Owner). Pour un triggered, `entities_from_state(state, owner_id, ...)`
   pose `caster = owner` -> IDENTIQUE. (Note assumee, pas une equivalence supposee : la construction
   du contexte est juste au-dessus, dans `execute_behaviour`.)
 * `isNextTurn = true` (la branche DANGER ZONE de `GetTargetsSelector`) n'est PAS portee : elle
   n'a aucun appelant ici (`CreateBehaviour` passe `false`). Le noeud leve si on la demande, plutot
   que de rendre un rayon faux en silence.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import AAmountFormula, TargetsSelector, resolve_unit
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.selectors import Caster, SurroundingFriends, UnitsWithoutTrait, UnitsWithTrait
from .....entities.stats import StatType
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....abilities.behaviours import AddEffect, entities_from_state
from ....components import OwnerComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

ABILITY_ID = "CursedPlagueBell"
EXTRA_MOVE = int(EffectType.CursedPlagueBell_ExtraMove)          # 0x431 = 1073
EXTRA_MOVE_NAME = "CursedPlagueBell_ExtraMove"
# `AuraEffectRangeFormula..ctor(effects, unit, effectType, ...)` : le 3e argument LITTERAL de
# `DSLFormulas$$ContagionsOfNurgleRange`. EffectType (PAS TriggeredAbilityType) -- cf. l'en-tete.
AURA_EFFECT = int(EffectType.ContagionsOfNurgle_ArmorReduction1)  # 0x42f = 1071
# `IAuraEffect.GetTrait()` PAR effect-def -- le natif l'interroge sur l'effet resolu par
# `effectsDatabase.Get(effectType)`, il n'est PAS cable en dur dans la formule. Seule entree lue :
# `ContagionsOfNurgle_ArmorReduction_Effect$$GetTrait` = `return 0x7eb` (litteral decompile).
# Un effect-def absent de cette table = `IAuraEffect` non porte -> la formule le dit, cf. `calculate`.
AURA_TRAIT_BY_EFFECT = {AURA_EFFECT: int(UnitTrait.ContagionsOfNurgle)}   # 0x42f -> 0x7eb = 2027
CHAOS = int(UnitTrait.Chaos)                                      # 0x7ea = 2026
STATIONARY = int(UnitTrait.Stationary)                            # 0x418 = 1048
# Duree du `AddEffect` : `Nullable<int>(1)` -- deja en TOURS (overload 4-args de `DSLBehaviors.AddEffect`).
EXTRA_MOVE_TURNS = 1


class ContagionsOfNurgleRange(AAmountFormula):
    """`IdunBattleLogic.Entities.DSLFormulas$$ContagionsOfNurgleRange(unit, unitSelectionType,
    isNextTurn)` -> `IdunBattle.Entities.Triggers.AuraEffectRangeFormula$$Calculate` -- MIRROR (cf.
    en-tete de module, section 4) :

        u = unit.Select(entities) ; if (u == null) return 0
        if (!HasTrait(u, IAuraEffect(0x42f).GetTrait() = 0x7eb ContagionsOfNurgle)) return 0
        return GetCurrentRange().Calculate(entities re-ancre sur u)
             = GetRangeOnOwnerTurn( StatAmount(u, 0xc=TurnsStarted, Current) )

    Le re-ancrage natif (`entities.<slot Owner> = unit` avant l'evaluation du sous-formule) rend le
    `StatAmount(Owner, ...)` de `GetCurrentRange` equivalent a « le TurnsStarted de `u` » : c'est ce
    que le port lit directement, via `ctx.get_stat` (le meme accesseur que le noeud `StatAmount`).

    `effect_type` est le 3e argument du ctor natif (l'effet d'AURA interroge, PAS l'ability) ;
    `unit_selection_type` est CONSERVE tel quel (le natif le stocke @+0x1c et le passe au
    `Select` du selecteur) : il vaut 0 = Any sur l'unique call-site porte, et le selecteur `Caster()`
    du port ne discrimine pas -> aucun effet observable, mais l'argument reste NOMME plutot
    qu'efface. `is_next_turn=True` = la branche `GetNextTurnRange` (DangerZone) : NON PORTEE."""

    def __init__(self, unit: TargetsSelector, unit_selection_type: int = 0,
                 is_next_turn: bool = False, effect_type: int = AURA_EFFECT):
        self.unit = unit
        self.unit_selection_type = int(unit_selection_type)
        self.is_next_turn = bool(is_next_turn)
        self.effect_type = int(effect_type)

    def calculate(self, ctx):
        from ....abilities.deathguard import contagions_of_nurgle_range_for_turns
        if self.is_next_turn:                       # `GetNextTurnRange` (Sum(TurnsStarted, 1)) -- residu
            raise NotImplementedError(
                "ContagionsOfNurgleRange(is_next_turn=True) : branche DangerZone non portee "
                "(`ContagionsOfNurgle_ArmorReduction_Effect$$GetNextTurnRange`)")
        # `def = effectsDatabase.Get(effectType)` : sans `IAuraEffect` porte pour ce type, le port
        # n'a PAS de `GetTrait()` a interroger -- il le DIT (jamais un 0 muet qui passerait pour
        # « l'unite n'a pas le trait »).
        trait = AURA_TRAIT_BY_EFFECT.get(self.effect_type)
        if trait is None:
            raise NotImplementedError(
                "AuraEffectRangeFormula : aucun IAuraEffect porte pour l'effectType %d "
                "(GetTrait/GetCurrentRange a lire au decompile)" % self.effect_type)
        u = resolve_unit(self.unit, ctx)
        if u is None:                               # `if (unit == null) return 0`
            return 0
        ht = ctx.has_trait or (lambda unit, tr: False)
        if not ht(u, trait):                        # `HasTrait(unit, IAuraEffect.GetTrait())`
            return 0
        gs = ctx.get_stat
        turns = 0 if gs is None else int(gs(u, int(StatType.TURNS_STARTED), 0, None) or 0)
        return contagions_of_nurgle_range_for_turns(turns)


def cursed_plague_bell_targets_selector(is_danger_zone: bool = False) -> TargetsSelector:
    """`...CursedPlagueBellMovementAbility$$GetTargetsSelector(dsl, isDangerZone)` -- MIRROR 1:1 :
    les ALLIES de l'Owner, dans le disque de son aura Contagion (centre EXCLU), qui portent le trait
    `Chaos` et ne portent PAS le trait `Stationary`.

    `Caster()` = le slot `DSLSelectors+0x30` (Owner) : pour un triggered, `entities_from_state`
    pose Owner == Caster (cf. residus de l'en-tete)."""
    owner = Caster()
    rng = ContagionsOfNurgleRange(owner, unit_selection_type=0, is_next_turn=is_danger_zone)
    friends = SurroundingFriends(owner, rng)        # `SurroundingFriends(Owner, range, unique, 3)`
    return UnitsWithoutTrait(UnitsWithTrait(friends, CHAOS), STATIONARY)


def cursed_plague_bell_movement_tree() -> AddEffect:
    """`...CursedPlagueBellMovementAbility$$CreateBehaviour` -- MIRROR 1:1 :
        `AddEffect(0x431 CursedPlagueBell_ExtraMove, AbilityStateReference,
                   GetTargetsSelector(dsl, false), turns = Nullable<int>(1))`.
    `duration_turns=1` (l'overload natif prend des TOURS, pas des rounds -> aucun
    `ConvertRoundsToTurns`) ; `source` = `AbilityStateReference` = le caster = l'Owner (defaut de la
    feuille du port)."""
    return AddEffect(EXTRA_MOVE, EXTRA_MOVE_NAME, cursed_plague_bell_targets_selector(),
                     duration_rounds=None, duration_turns=EXTRA_MOVE_TURNS)


class CursedPlagueBellMovementAbility(TriggeredAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellMovementAbility` (volet
    MOUVEMENT du passif `CursedPlagueBell` 1071, `deathBlightbringer`) -- cf. en-tete de module.

    `On(TurnStart_Other=19) & OwnerIsActor` -> `AddEffect(CursedPlagueBell_ExtraMove 1073, 1 tour)`
    sur les allies Chaos non-Stationary du disque d'aura Contagion de l'Owner (centre exclu)."""
    event_id = int(EventTriggerType.TurnStart_Other)         # On(0x13 = 19)
    # `BaseTriggeredAbility$$Execute` ecrit `AbilityOrEffect(this.Id)` avant le behaviour -> c'est
    # ce que lit `TriggeringAbilityIs`. Id = `TriggeredAbilityType.CursedPlagueBell` (0x42f = 1071),
    # celui du PASSIF (les trois classes Attack/Movement/DangerZone le partagent).
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.CursedPlagueBell)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`CreateTrigger` = `On(0x13) & OwnerIsActor` -- et RIEN d'autre (aucun
        `AmountIsGreaterThanZero`, contrairement a DestroyerHive) : l'arbre de cibles VIDE est un
        no-op du behaviour, pas un gate du trigger."""
        e = state.get_entity(self.owner_id)
        if e is None:
            return False
        oc = e.get_component(OwnerComponent)
        # OwnerIsActor (`DSLTriggers+0x28`) : fire au debut du tour du PROPRIETAIRE uniquement.
        return oc is not None and ev.player_id is not None and oc.player == int(ev.player_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None                              # pas d'EffectsState -> pose impossible
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `entities_from_state(state, owner)` : Owner == Caster pour un triggered (le natif lit les
        # deux dans le meme slot `DSLSelectors+0x30` cote selecteurs). Pas de cible d'evenement.
        cursed_plague_bell_movement_tree().execute(
            entities_from_state(state, self.owner_id, None), ectx)
        placed = [p for n, p in ectx.emitted if n == "AddEffect"]
        if not placed:
            return None
        return {"type": "cursed_plague_bell_extra_move", "owner": int(self.owner_id),
                "targets": [p.get("target") for p in placed],
                "newly_placed": [p.get("target") for p in placed if p.get("placed")],
                "turns": EXTRA_MOVE_TURNS, "effect": EXTRA_MOVE}
