"""`Abilities.Active.Loki.FabricatorClawArrayAbility` -- passif `FabricatorClawArray` du
`necroSpyder` (TriggeredAbilityType 0x3ee = 1006). Residu N20, trouve par la GENERALISATION de #299.

POURQUOI CE MODULE EXISTE. #299 a porte la face COMBAT de la reparation REGULIERE et l'a confrontee
live sur ses trois porteurs. Sur le `necroSpyder`, et sur lui seul, il restait un ecart PARFAITEMENT
reproductible : natif **10457**, port **6025**. L'ecart, **4432**, n'etait pas dans la reparation --
c'etait une SECONDE reparation, celle de ce passif, qui part au MEME tour :

  * tout cast d'active TERMINE le tour (`AddFlagsAfterAbilityExecution` ->
    `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` -> `UnitFlags.Add(ArrivedAtFinalTile)`) ;
  * et un DEPLACEMENT le termine aussi (`IdunBattle.Operations.MoveUnitOperation$$Execute` pose le
    MEME flag, puis publie `On(0x1c)` ssi le flag venait d'etre ajoute).
Donc le Spyder qui bouge PUIS repare restaure `RepairAmount` **et** `hpToRepair[niveau]` dans le meme
tour. Un port qui ne modelise que la voie ACTIVE sous-estime le total, SILENCIEUSEMENT -- ni erreur,
ni crash : exactement la degradation que la doctrine « DECIDER != EXECUTER » nomme.

--------------------------------------------------------------------------------------------------
CHAINE NATIVE (decompile = verite, build `rnca9r7q6c`, symboles confirmes par
`search_symbols_by_name` -- la classe n'a NI `.ctor` NI `Playbook` dans ce module : le playbook 1006
est la face DECISION, tranchee par la tache #242 et hors perimetre ici).

`IdunBattleLogic.Entities.Abilities.Active.Loki.FabricatorClawArrayAbility$$CreateTrigger` =

    On(0x1c = ArrivedAtFinalTile, ownerNeedsToBeAlive = 1)
      & get_OwnerIsActor
      & op_LogicalNot( AmountIsZero( GetTargetSelector() ) )

  * `IdunBattleLogic.Entities.DSLTriggers$$On(type, ownerNeedsToBeAlive)` = `EventTrigger(type) &
    <owner-alive @this+0x20>` -- le volet « owner vivant » est deja le gate `CanGetAbilityTrigger` du
    dispatch porte (`dispatch/core.evaluate_trigger_operation`), pas re-ecrit ici ;
  * `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsActor` = `AreEqual(DSLSelectors+0x30,
    DSLSelectors+0x40)` -- c'est CETTE fonction qui NOMME les deux slots : `+0x30 = Owner`,
    `+0x40 = Actor` (cf. le noeud `selectors.accessors.Owner`) ;
  * `IdunBattleLogic.Entities.DSLTriggers$$AmountIsZero(selector)` (surcharge SELECTEUR) =
    `op_LogicalNot( AmountIsEqualOrGreaterAbilityTrigger(selector, <One @formulas+0x20>) )`
    = `NOT (1 <= Count(selector))` = « le selecteur ne rend RIEN » ; sous le `op_LogicalNot` du
    trigger, la condition est donc « il existe au moins une cible ».
    ⚠ **CETTE LIGNE A PORTE DEUX ERREURS, corrigees le 2026-08-18 (#927-r1), et elles se
    COMPENSAIENT** : le champ `<formulas+0x20>` est `Direct(1)`, PAS `Zero` (le `.ctor` de
    `DSLFormulas` pose `+0x18 = Direct(0)` et `+0x20 = Direct(1)`, verifie a l'ASSEMBLEUR, prologue
    `mov rdi,rcx` compris) ; et la classe allouee est `AmountIsEqualOrGreaterAbilityTrigger`
    (`ShouldTrigger` finit par `minAmount <= value`), PAS `AmountIsGreaterAbilityTrigger` (qui finit
    par `<`). Le discriminant est l'`Il2CppClass*` passe a l'allocateur : `AmountIsZero` alloue la
    MEME classe qu'`AmountIsEqualOrGreater`, et une AUTRE que celle d'`AmountIsGreaterThanZero`
    (lequel lit `<formulas+0x18> = Direct(0)`). Les deux `.ctor` sont des corps TRIVIAUX fondus par
    l'ICF, donc Ghidra les nomme pareil -- meme piege que celui deja rencontre sur l'aura (#293,
    `engine/battle_query.py`). Le predicat porte (`count <= 0`) etait JUSTE et ne change pas.

`...$$GetTargetSelector` =

    PickRandomly( Repairable( UnitsAffectedByHealType( AdjacentFriends(Owner, 1, 3), 1 ),
                              scope = 0, removeEffects = 1, unitSelectionType = 3 ),
                  amount = 1, allowDuplicates = 0, maxDuplicates = 0x7fffffff, ignoreForced = false )
    .Otherwise(
    PickRandomly( UnitsWithNegativeEffects( <le MEME UnitsAffectedByHealType> ),
                  1, 0, 0x7fffffff, false ) )

  ⚠ Le fallback part de `UnitsAffectedByHealType`, PAS de `Repairable` (lu au decompile : le second
  `PickRandomly` recoit `pvVar2`, le resultat du filtre heal-type, et non `pvVar1`). Il vise donc les
  allies mecaniques adjacents PAS reparables mais porteurs d'un effet NEGATIF -- le volet « purge »
  de `RepairBehaviourOptions.ForRepair` (`removeEffects = 1`).

`...$$CreateBehaviour` =

    Repair( mechanic = Owner@DSLSelectors+0x30,
            selector = GetTargetSelector(),
            amount   = DSLFormulas.Direct( AbilityConfiguration.GetVariableForLevel(
                             config, 0x24 = hpToRepair, abilityState, fallbackToDefault = 0) ),
            source   = AbilityOrEffect(this),
            options  = RepairBehaviourOptions.ForRepair() )        # scope 0, removeEffects 1

  ⚠ `mechanic = +0x30 = Owner`, la ou `IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$CreateBehaviour`
  prend `+0x48 = Caster`. Pour une TRIGGERED les deux coincident (le behaviour est execute par
  `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` sur son propre porteur), et
  `entities_from_state(state, owner_id)` pose `caster = owner` -- mais le port CITE le slot que le
  natif cite.

--------------------------------------------------------------------------------------------------
DOCTRINE #149. L'artefact natif est un `CreateTrigger` + un `CreateBehaviour` : c'est donc un ARBRE
DSL, et c'en est un ici -- aucun ciblage n'est recable a la main. Les quatre noeuds qui manquaient au
vocabulaire ont ete portes a leur place (`entities/selectors/`), pas inlines :
`UnitsAffectedByHealType`, `Repairable`, `UnitsWithNegativeEffects` (`units.py`) et `PickRandomly`
(`geometry.py`) ; plus l'accesseur de slot `Owner` (`accessors.py`). La FRONTIERE reste le `.Execute`
de la feuille : `Repair` (behaviours/stats.py) APPELLE `RepairUnitOperation` (#299), elle ne la
re-ecrit pas.

DEUX evaluations, DEUX arbres, DEUX tirages -- et c'est FIDELE. `CreateTrigger` et `CreateBehaviour`
sont deux fabriques distinctes : chacune appelle `GetTargetSelector()` et obtient donc SA PROPRE
instance de `PickRandomly`. A chaque `On(0x1c)`, le natif evalue l'arbre du trigger (1er tirage, sous
`AmountIsZero`) PUIS, s'il passe, l'arbre du behaviour (2e tirage). Aucun `Cache` n'intervient dans
ces arbres. Court-circuiter le second (« on connait deja la cible ») ferait deux fautes a la fois :
un tirage RNG en moins (desalignement de tout le flux aval, loi #215) et une cible potentiellement
DIFFERENTE de celle que le natif frappe des que le pool depasse 1.

RESIDUS NOMMES :
  * `UnitsWithNegativeEffects` -- la CATEGORIE d'un effet (`EffectsDatabase` def+0x58) n'est pas dans
    le canal de seed : le selecteur rend [] cote port (cf. son noeud). Consequence UNILATERALE : le
    fallback ne peut que RATER une cible, jamais en inventer une. Il n'est atteint que si AUCUN allie
    mecanique adjacent n'est reparable.
  * `unitSelectionType = 3` (mode d'occupation main/steppable passe au `Select` de la source) : le
    port n'a pas ce parametre cote selecteurs sources -- residu deja partage par tous les call-sites
    d'`AdjacentFriends`.
  * `source = AbilityOrEffect(this)` (attribution de la reparation) : aucun observable d'ETAT porte,
    non modelise -- meme choix que la feuille `Repair` de #299.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.selectors.accessors import Owner
from .....entities.selectors.geometry import Otherwise, PickRandomly
from .....entities.selectors.units import (
    AdjacentFriends, Repairable, UnitsAffectedByHealType, UnitsWithNegativeEffects
)
from .....entities.triggers import AmountIsZero, Not, OwnerIsActor, TriggerAnd
from .....entities.formulas import Count
from ....components import StatsComponent
from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.stats import Repair
from ..base import TriggeredAbility, TriggerEvent
from .....entities.effects.magnitude import ability_var

ABILITY_ID = "FabricatorClawArray"
HP_TO_REPAIR_KEY = "hpToRepair"        # `AbilityVariableType` 0x24 = 36 (cle gameconfig, cf. magnitude.py)
HEAL_TYPE_MECHANICAL = 1               # `IdunBattle.Entities.Enum.HealType`.Mechanical
ADJACENT_UNIQUE = 1                    # `AdjacentFriends(Owner, unique = 1, selectionType = 3)`
UNIT_SELECTION_TYPE = 3                # ... le 3e argument, propage au `Select` de la source
REPAIR_SCOPE = 0                       # `RepairBehaviourOptions$$ForRepair` : +0x10 = 0
REPAIR_REMOVE_EFFECTS = True           # ... +0x14 = 1

_ON_ARRIVED = int(EventTriggerType.ArrivedAtFinalTile)      # 0x1c = 28


def fabricator_claw_array_target_selector():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FabricatorClawArrayAbility$$GetTargetSelector`
    -- MIRROR 1:1, noeud pour noeud (cf. l'en-tete du module pour le decompile).

    Une NOUVELLE instance a chaque appel, EXPRES : le natif appelle cette fabrique depuis
    `CreateTrigger` **et** depuis `CreateBehaviour`, et chacun obtient donc son propre `PickRandomly`.
    Partager l'instance ne changerait rien cote port (les noeuds sont sans etat) mais masquerait le
    fait qu'il y a bien DEUX tirages."""
    affected = UnitsAffectedByHealType(                  # <- le sous-arbre PARTAGE par les deux branches
        AdjacentFriends(Owner(), Const(ADJACENT_UNIQUE), reference=Owner()),
        HEAL_TYPE_MECHANICAL)
    repairable = Repairable(affected, scope=REPAIR_SCOPE, remove_effects=REPAIR_REMOVE_EFFECTS,
                            unit_selection_type=UNIT_SELECTION_TYPE)
    return Otherwise(PickRandomly(repairable, 1, False, 0x7FFFFFFF, False),
                     PickRandomly(UnitsWithNegativeEffects(affected), 1, False, 0x7FFFFFFF, False))


def fabricator_claw_array_trigger_tree():
    """`...$$CreateTrigger`, moins le volet `On(0x1c)` / owner-vivant que porte le DISPATCH :

        get_OwnerIsActor & op_LogicalNot( AmountIsZero( GetTargetSelector() ) )

    `AmountIsZero` prend un SELECTEUR cote natif (surcharge `DSLTriggers$$AmountIsZero(selector)`, qui
    construit `NOT AmountIsEqualOrGreater(selector, <One @formulas+0x20>)`, cf. l'en-tete) ; le noeud
    porte prend une VALEUR, d'ou le `Count(...)` explicite -- meme predicat, `count <= 0`.

    Comme `GetTargetSelector`, une NOUVELLE instance a chaque appel : l'arbre du trigger porte SON
    `PickRandomly`, distinct de celui du behaviour (cf. l'en-tete du module)."""
    return TriggerAnd(OwnerIsActor(),
                      Not(AmountIsZero(Count(fabricator_claw_array_target_selector()))))


def fabricator_claw_array_behaviour_tree(amount: int):
    """`...$$CreateBehaviour` = `Repair(Owner, GetTargetSelector(), Direct(amount), ForRepair)`.

    `amount` est resolu par l'APPELANT parce que le natif le resout lui aussi AVANT de batir l'arbre :
    `CreateBehaviour` appelle `AbilityConfiguration.GetVariableForLevel(config, 0x24, abilityState, 0)`
    puis enveloppe la valeur dans `DSLFormulas$$Direct` -- c'est une CONSTANTE de l'arbre, pas un
    `ConfigVar` paresseux."""
    return Repair(fabricator_claw_array_target_selector(), amount,
                  scope=REPAIR_SCOPE, remove_effects=REPAIR_REMOVE_EFFECTS)


def hp_to_repair(state: State, owner_id: int) -> int:
    """`AbilityConfiguration.GetVariableForLevel(config, 0x24 = hpToRepair, abilityState, 0)`.

    `abilityState` (les 12 octets copies par `GetVariableForLevel` avant de deleguer a
    `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel`) porte le NIVEAU et le
    `VariableMultiplierPercentage` de l'ability -- et `hpToRepair` est bien dans
    `variablesAffectedByRarityBonus` du gameconfig, donc le multiplicateur de rarete s'applique. Le
    port lit les deux sur le `StatsComponent.ctx` du PORTEUR (`passive_ability_level` : c'est un
    PASSIF) et delegue a `ability_var`, foyer unique de cette lecture.

    0 si l'unite, son contexte ou la variable manquent -> la feuille `Repair` est alors un no-op
    (`amount > 0` est sa garde)."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    if ctx is None:
        return 0
    lvl = getattr(ctx, "passive_ability_level", None)
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
    return int(ability_var(ABILITY_ID, HP_TO_REPAIR_KEY, lvl, multiplier_pct=mult) or 0)


class FabricatorClawArrayAbility(TriggeredAbility):
    """`FabricatorClawArrayAbility` (`...$$CreateTrigger` / `...$$CreateBehaviour` /
    `...$$GetTargetSelector`) -- le passif du `necroSpyder`.

    A la fin de l'activation du Spyder (`On(0x1c = ArrivedAtFinalTile)` : apres son 1er deplacement,
    OU a la cloture de son tour s'il n'a pas bouge -- les DEUX emetteurs natifs), il repare
    `hpToRepair[niveau]` PV a UN allie mecanique adjacent reparable, tire au hasard.

    Cf. l'en-tete du module pour la chaine native, la doctrine #149 et les residus."""
    event_id = _ON_ARRIVED
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.FabricatorClawArray)     # 0x3ee = 1006

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`CreateTrigger` moins le volet porte par le dispatch (`On(0x1c)` + owner vivant).

        ⚠ CETTE EVALUATION CONSOMME LE PRNG (le `PickRandomly` sous `AmountIsZero`), et c'est le
        natif qui le veut : son `ShouldTrigger` evalue le meme sous-arbre. Le dispatch n'appelle
        `matches` que pour les entrees dont l'`event_id` correspond ET dont l'owner est vivant, donc
        aucune consommation parasite."""
        entities = entities_from_state(state, self.owner_id, None, actor_id=ev.actor_id)
        return bool(fabricator_claw_array_trigger_tree().evaluate(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        amount = hp_to_repair(state, self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, None, actor_id=ev.actor_id)
        fabricator_claw_array_behaviour_tree(amount).execute(entities, ectx)
        emitted = next((p for (n, p) in ectx.emitted if n == "Repair"), {})
        repairs = emitted.get("repairs") or []
        return {"passive": ABILITY_ID, "owner": int(self.owner_id), "amount": int(amount),
                "repairs": repairs,
                "repaired": sum(int(r.get("repaired") or 0) for r in repairs)}
