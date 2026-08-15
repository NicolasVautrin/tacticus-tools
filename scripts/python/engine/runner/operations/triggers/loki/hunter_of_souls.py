"""`HunterOfSouls` (`TriggeredAbilityType` 0x5d9 = **1497**) -- le passif du summon
`thousSmnDaemonPrince` << Z'Kar >>. #1078-r2.

Porteur (voie `passiveAbilities`) : `thousSmnDaemonPrince`, un SUMMON -- donc confrontable par son
SUMMONER, jamais par `--list-pool`. Le summoner natif est la MoW `thousDaemonPrince`
(`AetherStride` 1208, `constants.unitId = "thousSmnDaemonPrince"`), HORS du pool des 8 MoW
spawnables ; le montage ECRIT est la GREFFE de `AetherStride` sur `ultraDreadnought` (MoW du pool,
#1022), ce qui fait de la MoW greffee le `Parent(Owner)` que lit ce module.

================================================================================================
UN id, DEUX classes natives -- et c'est MESURE, pas suppose
================================================================================================
Meme patron que `Lakrimae` / `DaemonfleshPlate` / `ChaliceOfBaal`. `TriggeredAbilityType` du build
ne porte qu'**UN SEUL** membre `HunterOfSouls` (`1497`) -- balayage de
`data/symbols/<build>/frida/enums.tsv` : aucun `HunterOfSouls_Killed`. Le gameconfig concorde
(`GC.ability("HunterOfSouls")` existe, `GC.ability("HunterOfSouls_Killed")` rend `None`). Les deux
classes partagent donc l'id 1497, et l'entree de registre est UNE LISTE.

--- 1) `...Triggered.Loki.HunterOfSoulsAbility` -- le tour du Daemon Prince ------------------

`$$CreateTrigger` (corps DEDUPLIQUE par l'ICF, partage avec
`IdunBattleLogic.Entities.Abilities.Active.Loki.LethalMiasmaAbility$$CreateTrigger`, dont le corps
est LU) :

    On(0x16 = TurnStart_Actions, ownerNeedsToBeAlive = 1) & <DSLTriggers+0x28>

⚠ **`<DSLTriggers+0x28>` EST NOMME (2026-08-15), et c'est le dernier verrou de lecture de #1078-r2
qui tombe** : `IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf(selector)` alloue EXACTEMENT la meme
classe (`DAT_1833ac7e8` sur `t6dpr4k06g`) avec la MEME signature `(selector, <ctx+0x10>)`, et le
balayage LITTERAL de cette classe dans tout le decompile ne rend que TROIS sites :
`DSLTriggers$$IsTurnOf`, `DSLTriggers$$InitializeShared` (qui construit `+0x28` avec
`Owner@DSLSelectors+0x30`) et un `AnvilShieldAbility_ApplyStun$$CreateBehaviour`. Donc

    <DSLTriggers+0x28> = IsTurnOf(Owner@DSLSelectors+0x30)

-- ce que `armour_of_shrieking_souls.py` et le registre citaient deja pour ce meme champ.

`$$CreateBehaviour` (MIRROR du decompile, RELU dans cette tranche) :

    A = If( NOT HasEffect(Owner@+0x30, 0x5d7 = 1495 HunterOfSouls_ExtraDamage,
                          onlyActive = 0, selectionType = 6),
            AddEffect(0x5d7, AbilityStateReference, targets = Owner@+0x30, options = 0),
            null )
    B =   PerformAIAttack(Owner@+0x30, allowMoveAction = 1, moveAmount = null, null, null)
        + AddFlag(Owner@+0x30, 0x16 = 22 PreventResurrect)
        + RemoveUnit(Owner@+0x30)
        + ReAddMachine(Parent(Owner@+0x30), <DSLTriggers+0x70> = YesTrigger)
    return A + B

L'OBSERVABLE : au debut de SON tour, le Daemon Prince se buff (une seule fois), joue une action
d'IA, se marque irressuscitable, QUITTE le plateau, et la MoW dont il est issu REVIENT.

--- 2) `...Triggered.Loki.HunterOfSouls_KilledAbility` -- il est tue avant d'agir ------------

`$$CreateTrigger` :

    On(0x36 = UnitDefeated, ownerNeedsToBeAlive = 0) & get_OwnerIsTarget

`$$CreateBehaviour` :

      AddFlag(Owner@+0x30, 0x16 = 22 PreventResurrect)
    + ReAddMachine(Parent(Owner@+0x30), NOT HasFlag(Owner@+0x30, 0x3 = TurnFinished))

⚠ **LE 2e ARGUMENT DE `ReAddMachine` DIFFERE ENTRE LES DEUX CLASSES, ET C'EST TOUT LE POINT.** Il
n'est PAS un booleen mais un PREDICAT (`IAbilityTrigger`), evalue par
`IdunBattle.Entities.Behaviours.ReAddMachineBehaviour$$Execute` avant l'appel a l'Operation :
constante VRAIE quand le Prince a joue son tour (volet 1), et `NOT HasFlag(TurnFinished)` quand il
meurt (volet 2) -- c'est-a-dire << ne remets les flags de tour a zero que s'il n'avait PAS deja
fini son tour >>. Le figer en `bool` cote port aurait rendu ce volet FAUX en silence.

================================================================================================
FORME DU PORT (doctrine #149) et ETAGE NEUF
================================================================================================
Les deux `CreateTrigger` COLLAPSENT dans `matches` ; les `CreateBehaviour` sont des arbres DSL.

L'etage qui manquait est `ReAddMachine`, porte par la MEME tranche en DEUX morceaux :
`abilities/behaviours/lifecycle.py::ReAddMachine` (la feuille) et
`runner/operations/re_add_machine.py::ReAddMachineOperation` (le mutateur). `AddFlag` et
`RemoveUnit`, eux, existaient deja -- l'enonce de #1078-r2 les a comptes manquants DEUX FOIS de
suite, toujours dans le meme sens.

1497 est une `TriggeredAbilityType` : elle n'entre NI dans `ABILITY_CLASSES`, NI dans
`TARGETING_OPTIONS`, NI dans `ABILITY_ATTACK_TYPE`.

RESIDUS NOMMES
  * L'effet `1495 HunterOfSouls_ExtraDamage` est pose par cet arbre ; sa MAGNITUDE
    (`HunterOfSouls_ExtraDamageEffect$$GetDamageBonusMultiplier` / `$$GetUnits`) est hors de cette
    tranche -- le port pose l'entite-effet, pas son bonus de degat.
  * `PerformAIAttack` consomme le rail d'IA existant (`abilities/behaviours/summon.py`) : le tour
    joue par le Prince depend du walk IA, pas de ce module.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import UnitComponent
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from ....abilities.behaviours.flags import AddFlag
from ....abilities.behaviours.lifecycle import ReAddMachine, RemoveUnit
from ....abilities.behaviours.summon import PerformAIAttack
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import If, op_add
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Owner
from .....entities.selectors.tiles import Parent
from .....entities.triggers import HasEffect, HasUnitFlag, IsTurnOf, Not, YesTrigger
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.unit_flag import UnitFlag
from ..base import TriggeredAbility, TriggerEvent

#: Cle du registre `ABILITY_TRIGGERS` = le NOM gameconfig du passif.
ABILITY_ID = "HunterOfSouls"
#: `AddEffect(0x5d7, ...)` / `HasEffect(Owner, 0x5d7, ...)`.
HUNTER_OF_SOULS_EXTRA_DAMAGE = int(EffectType.HunterOfSouls_ExtraDamage)      # 0x5d7 = 1495
#: `AddFlag(Owner@+0x30, 0x16)` -- le flag SE NOMME, il ne s'ecrit pas en ordinal nu.
PREVENT_RESURRECT = int(UnitFlag.PreventResurrect)                           # 0x16 = 22
#: `NOT HasFlag(Owner@+0x30, 0x3)` -- le 2e argument de `ReAddMachine` du volet KILLED.
TURN_FINISHED = int(UnitFlag.TurnFinished)                                   # 0x3 = 3


def hunter_of_souls_tree() -> object:
    """`HunterOfSoulsAbility$$CreateBehaviour` -- MIRROR 1:1 (cf. l'en-tete).

    L'ORDRE des quatre termes de `B` est celui du natif et il est LOAD-BEARING : le Prince attaque
    AVANT de poser son flag, se retire APRES, et la machine ne revient qu'en DERNIER. Inverser
    `RemoveUnit` et `ReAddMachine` rattacherait la MoW pendant que le summon occupe encore ses
    tuiles.

    `HasEffect(..., onlyActive = 0)` : aucun filtre `IsActive` au call-site -> `has_effect_of_type`,
    exactement comme `calibanite_greatsword.py`. Le `selectionType = 6` du 5e argument gouverne le
    MODE de resolution du selecteur natif, non porte (le selecteur rend une unite unique)."""
    a = If(Not(HasEffect(Owner(), HUNTER_OF_SOULS_EXTRA_DAMAGE)),
           AddEffect(HUNTER_OF_SOULS_EXTRA_DAMAGE, EffectType.HunterOfSouls_ExtraDamage.name,
                     Owner(), duration_rounds=None))
    b = op_add(op_add(op_add(
        # `PerformAIAttack(Owner, allowMoveAction = 1, moveAmount = null, ...)` -- la surcharge
        # `DSLBehaviors$$PerformAIAttack` (le `1` litteral et le `null`), PAS
        # `...FromCurrentPosition` : le Prince APPROCHE avant de frapper.
        PerformAIAttack(Owner(), True, None),
        AddFlag(Owner(), PREVENT_RESURRECT)),
        RemoveUnit(Owner())),
        # `<DSLTriggers+0x70>` = le `YesTrigger` CONSTANT : le rattachement remet TOUJOURS les
        # flags de tour a zero sur ce vecteur.
        ReAddMachine(Parent(Owner()), YesTrigger()))
    return op_add(a, b)


def hunter_of_souls_killed_tree() -> object:
    """`HunterOfSouls_KilledAbility$$CreateBehaviour` -- MIRROR 1:1 :

        AddFlag(Owner@+0x30, 0x16) + ReAddMachine(Parent(Owner@+0x30),
                                                  NOT HasFlag(Owner@+0x30, 0x3 = TurnFinished))

    Le predicat est evalue A L'EXECUTION par la feuille (`ShouldTrigger`), pas fige ici : le Prince
    tue APRES avoir fini son tour ne doit PAS voir la MoW repartir avec un tour neuf."""
    # `HasUnitFlag` (et non `HasFlag`, qui teste un flag SCALAIRE du contexte de decision) : le
    # natif appelle `DSLTriggers$$HasFlag(unit, flag)`, la surcharge UNIT-DOMAIN.
    return op_add(AddFlag(Owner(), PREVENT_RESURRECT),
                  ReAddMachine(Parent(Owner()), Not(HasUnitFlag(Owner(), TURN_FINISHED))))


class HunterOfSoulsAbility(TriggeredAbility):
    """`HunterOfSoulsAbility` (une des deux classes natives du triggered 1497).

    OBSERVABLE : au debut de son tour, le Daemon Prince se buff (1495, une fois), joue une action
    d'IA, se marque `PreventResurrect`, quitte le plateau, et sa MoW parente est RATTACHEE."""
    event_id = int(EventTriggerType.TurnStart_Actions)        # `On(0x16, alive = 1)`
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.HunterOfSouls)             # 0x5d9 = 1497

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `<DSLTriggers+0x28>` = `IsTurnOf(Owner@DSLSelectors+0x30)` -- evalue par le NOEUD DSL
        # (`entities/triggers.py::IsTurnOf`), FOYER UNIQUE du mirror de
        # `IdunBattle.Entities.Triggers.IsTurnOfUnitTrigger$$ShouldTrigger`. Le re-collapser a la
        # main ici en fabriquerait un SECOND port : le noeud lit `ctx.current_player_id`
        # (`ctx@+0x50 == null -> false`, la garde de tete du natif), pas le `player_id` de
        # l'evenement -- et sur CE vecteur les deux coincident, `set_current_player` posant
        # `state.current_player_id` a l'ENTRANT (ChangeTurn) AVANT que `StartTurn` n'emette `On(0x16)`.
        ent = state.get_entity(int(self.owner_id))
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if uc is None or not uc.alive:                # `ownerNeedsToBeAlive = 1`
            return False
        entities = entities_from_state(state, self.owner_id, self.owner_id)
        return bool(IsTurnOf(Owner()).should_trigger(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, self.owner_id)
        hunter_of_souls_tree().execute(entities, ectx)
        emitted = dict()
        for n, p in ectx.emitted:
            emitted.setdefault(n, []).append(p)
        return {"ability": ABILITY_ID, "owner": int(self.owner_id),
                "buffed": bool([p for p in emitted.get("AddEffect", []) if p.get("placed")]),
                "removed": bool(emitted.get("RemoveUnit")),
                "machine": [p.get("machine") for p in emitted.get("ReAddMachine", [])]}


class HunterOfSoulsKilledAbility(TriggeredAbility):
    """`HunterOfSouls_KilledAbility` (la seconde classe native du triggered 1497).

    OBSERVABLE : si le Daemon Prince est VAINCU avant d'avoir joue, il est marque
    `PreventResurrect` et sa MoW parente revient -- avec ses flags de tour remis a zero SEULEMENT
    s'il n'avait pas deja fini son tour."""
    event_id = int(EventTriggerType.UnitDefeated)             # `On(0x36, alive = 0)`
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.HunterOfSouls)             # 0x5d9 = 1497
    #: `ownerNeedsToBeAlive = 0` -- le porteur est justement celui qui vient d'etre vaincu.
    fire_on_death = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsTarget` : le VAINCU doit etre le porteur. AUCUN gate de vie (`On(0x36)` porte
        # `ownerNeedsToBeAlive = 0`, LU) -- sans quoi ce trigger ne firerait jamais.
        return ev.target_id is not None and int(ev.target_id) == int(self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, self.owner_id)
        hunter_of_souls_killed_tree().execute(entities, ectx)
        readd = [p for n, p in ectx.emitted if n == "ReAddMachine"]
        flags = [p for n, p in ectx.emitted if n == "AddFlag"]
        return {"ability": "HunterOfSouls_Killed", "owner": int(self.owner_id),
                "prevent_resurrect": bool([p for p in flags if p.get("added")]),
                "machine": [p.get("machine") for p in readd],
                "reset_flags": [p.get("reset_flags") for p in readd]}
