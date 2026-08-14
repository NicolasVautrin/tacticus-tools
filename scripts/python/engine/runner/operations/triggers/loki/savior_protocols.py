"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SaviorProtocolsAbility` -- face **COMBAT** du
passif `SaviorProtocols` (`TriggeredAbilityType` `0x460` = 1120), #1020.

La face DECISION est portee depuis #443 / #443-r1 (`engine/playbook/savior_protocols.py`, les deux
volets ATTACK et MOVE). Ce module-ci porte ce qui manquait : **l'EXECUTION**.

PORTEURS (six, tous hors pool, ventiles) : `tauNpc2DroneSniper`, `tauNpc3DroneShield`,
`tauNpc4DroneCommandLink` (npc) et `tauSmnDroneSniper`, `tauSmnDroneShield`,
`tauSmnDroneCommandLink` (**summons**). Le chemin confrontable est le SUMMON : on spawne le
summoner (`tauMarksman`, au pool) et le drone arrive dans son equipe.

---

## L'artefact natif, RE-CONFRONTE au decompile (build `rnca9r7q6c`)

    SaviorProtocolsAbility$$CreateTrigger =
        On(0x39 = EventTriggerType.PreDamageTaken, ownerNeedsToBeAlive = 0)
          & TargetIsValidTrigger()
          & IsAdjacent(Owner@<DSLSelectors+0x30>, Target@<+0x60>, 0 = UnitSelectionType.Any)
          & !TriggeringAbilityIs(0x530 = 1328 PinpointCounterOffensive)   // #1020-r3 : LU aux octets
          & !TriggeringAbilityIs(0x52f = 1327 ATemptingTrap)              // #1020-r3 : LU aux octets

    SaviorProtocolsAbility$$TargetIsValidTrigger =            // PARTAGE avec la face MOVE
        AreFriends(Target@<+0x60>, Owner@<+0x30>)
          & HasFaction(Target@<+0x60>, 9 = UnitFaction.Tau, 3)
          & !ActorHasTriggeredAbility(Target@<+0x60>, 0x460 = 1120 SaviorProtocols)
          & !AreEqual(Target@<+0x60>, Owner@<+0x30>)

    SaviorProtocolsAbility$$CreateBehaviour =
        If( Maybe( ConfigConst(0x2a = AbilityConstantType.chance, abilityState) ),   // gameconfig : 50
            TransferDamage( caster         = Caster@<+0x48>,      // la SOURCE du degat
                            originalTarget = Target@<+0x60>,      // la VICTIME
                            transferTarget = Owner@<+0x30>,       // le DRONE
                            transferAbility = <DSLSelectors+0x88>,
                            attackAbility   = <DSLSelectors+0x90> ),
            null )

## Ce qui fait la mecanique, et le piege

`IdunBattle.Operations.TransferDamageOperation$$GetDamage` **CONSOMME** le
`Nullable<DamageAppliedResult>` pose par `IdunBattle.Operations.ApplyDamageOperation$$Execute` dans
`FillUpStatComponent+0x64` : il en lit `DamageAppliedResult$$get_Damage` puis ecrit
`*(qword*)(comp+0x64) = 0`. La relecture native etant un `System.Nullable<T>$$GetValueOrDefault`,
le `FillUpStatComponent$$Reduce(hp, pending.healthDamage)` qui suit n'enleve **plus rien**.

**Ce n'est donc PAS un bonus, c'est un DEPLACEMENT.** Un port qui ajouterait le degat au drone sans
le retirer a la victime DOUBLERAIT le degat total. Le canal de retrait est
`_pre_damage_taken_per_hit` (#1020, `operations/damage.py`), le canal d'ajout
`transfer_damage_operation` (`operations/transfer_damage.py`).

## Le predicat est mirrore DEUX FOIS, et ce n'est pas un fork

`TargetIsValidTrigger` existe deja en version SCALAIRE dans `playbook/savior_protocols.py`
(`_target_is_valid_trigger`), parce que le substrat du playbook est un contexte tile-leaf sans
`AbilityEntities` -- il n'y a aucun arbre DSL a evaluer la-bas. Ici le substrat EST un
`AbilityEntities` (on est dans un dispatch de trigger), donc le mirror est l'ARBRE, noeud pour
noeud, comme l'exige la doctrine #149. Les deux lisent le meme decompile ; ils ne se recopient pas.

## RESIDUS

* **`#1020-r3` -- FERME.** Les deux `!TriggeringAbilityIs` sont LUS (aux octets : `mov edx, 0x530`
  et `mov edx, 0x52f`, cf. `EXCLUDED_*` ci-dessous) et PORTES. Le noeud `TriggeringAbilityIs` lit
  `ctx.attack_ability_type` (le canal `AbilityEntities+0x98`), que le vecteur
  `pre_damage_taken_triggers` alimente desormais.
* **`#1020-r1` -- FERME.** Le natif annule AUSSI `ReduceShield` sur un coup transfere : `Reduce` et
  `ReduceShield` lisent le MEME pending relu APRES l'emission. `_deplete_shield` a donc quitte les
  APPELANTS pour le chokepoint (`operations/damage.py`), ou il consomme `kept_shield`.
* **`#1020-r2` -- FERME.** Les deux `Nullable<AbilityOrEffect>` sont consommes, et ils n'ont pas le
  meme role : les DEUX forment un GATE (`HasValue` exige, sinon `TransferDamageBehaviour$$Execute`
  ne fait RIEN), et seul `attackAbility` descend jusqu'au slot `64 = DirectDamage` pour nommer la
  source du degat porte par le protecteur. Cf. `abilities/behaviours/transfer.py`.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_constant_type import AbilityConstantType
from .....entities.behaviours import If
from .....entities.selectors.accessors import Actor, Target
from .....entities.selectors.tiles import Caster
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import (ActorHasTriggeredAbility, AreEqual, AreFriends, HasFaction,
                                    IsAdjacent, MaybeTrigger, Not, TriggerAnd, TriggeringAbilityIs)
from .....entities.unit_faction import UnitFaction
from .....entities.unit_selection_type import UnitSelectionType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.transfer import TransferDamage
from ..base import TriggeredAbility, TriggerEvent
from ....state import State

ABILITY_ID = "SaviorProtocols"
#: `0x460` = 1120 -- l'argument du `ActorHasTriggeredAbility` du gate ET l'id de l'ability.
SAVIOR_PROTOCOLS = TriggeredAbilityType.SaviorProtocols
#: `HasFaction(Target, 9, 3)` -- `9` est `UnitFaction.Tau`, `3` le `UnitSelectionType` du selecteur.
TAU = UnitFaction.Tau
FACTION_SELECTION = UnitSelectionType.OnlyAliveAndTargetable          # = 3
#: `IsAdjacent(Owner, Target, 0)` -- le 3e argument va aux SELECTEURS, pas au predicat (#433-r3).
ADJACENCY_SELECTION = UnitSelectionType.Any                           # = 0
#: `ConfigConst(0x2a, abilityState)` -- `AbilityConstantType.chance`, `constants.chance` du gameconfig.
CHANCE_CONSTANT = AbilityConstantType.chance
#: Les DEUX `!TriggeringAbilityIs(<AbilityOrEffect>)` qui terminent `$$CreateTrigger` (#1020-r3).
#: L'argument est INVISIBLE au decompile (ghidra ne montre que le buffer de retour d'
#: `IdunBattle.Core.AbilityOrEffect$$op_Implicit`) : les deux valeurs sont lues AUX OCTETS de
#: `SaviorProtocolsAbility$$CreateTrigger`, ou l'immediat est charge dans `edx` juste avant le
#: `call` -- `mov edx, 0x530` puis `mov edx, 0x52f`, dans CET ordre. Les deux `call` visent la
#: MEME surcharge (meme rel32 apres correction de site), celle dont le parametre de metadata se
#: nomme `triggeredAbility` et dont le corps appelle `IdunBattle.Core.AbilityOrEffect$$
#: set_TriggeredAbility` -> l'enum est `TriggeredAbilityType`, PAS `ActiveAbilityType` ni
#: `EffectType` (les trois surcharges portent le meme nom affiche, seul le rel32 les separe).
EXCLUDED_PINPOINT = TriggeredAbilityType.PinpointCounterOffensive     # 0x530 = 1328
EXCLUDED_TEMPTING_TRAP = TriggeredAbilityType.ATemptingTrap           # 0x52f = 1327

_ON_PRE_DAMAGE_TAKEN = int(EventTriggerType.PreDamageTaken)           # 0x39 = 57


def target_is_valid_trigger_tree():
    """`SaviorProtocolsAbility$$TargetIsValidTrigger` -- les quatre noeuds, dans l'ordre du
    decompile, chacun avec son selecteur natif :

        AreFriends(Target@<+0x60>, Owner@<+0x30>)
          & HasFaction(Target@<+0x60>, 9 = UnitFaction.Tau, 3)
          & !ActorHasTriggeredAbility(Target@<+0x60>, 0x460 = 1120)
          & !AreEqual(Target@<+0x60>, Owner@<+0x30>)

    `Owner@<DSLSelectors+0x30>` est rendu par `Caster()` cote port : pour une
    `BaseTriggeredAbility`, `Owner == Caster` (meme convention que `geminae_superia.py`)."""
    t = TriggerAnd(AreFriends(Target(), Caster()),
                   HasFaction(Target(), int(TAU)))
    t = TriggerAnd(t, Not(ActorHasTriggeredAbility(Target(), int(SAVIOR_PROTOCOLS))))
    return TriggerAnd(t, Not(AreEqual(Target(), Caster())))


def savior_trigger_tree():
    """`SaviorProtocolsAbility$$CreateTrigger`, moins le seul volet `On(0x39)` que porte le
    DISPATCH -- les QUATRE conjoints restants sont portes (#1020-r3 a ferme les deux derniers) :

        TargetIsValidTrigger()
          & IsAdjacent(Owner@<+0x30>, Target@<+0x60>, 0)
          & !TriggeringAbilityIs(0x530 = 1328 PinpointCounterOffensive)
          & !TriggeringAbilityIs(0x52f = 1327 ATemptingTrap)

    ⚠ `ownerNeedsToBeAlive` vaut **0** (2e argument d'`On`), comme `GeminaeSuperia` -- le gate
    « owner vivant » du dispatch (`CanGetAbilityTrigger`) reste celui du port, residu PARTAGE.

    ZERO tirage PRNG : le `Maybe` est dans le BEHAVIOUR, pas dans le trigger. Un drone dont le gate
    ferme ne consomme donc aucun tirage -- point load-bearing pour le flux RNG."""
    t = TriggerAnd(target_is_valid_trigger_tree(),
                   IsAdjacent(Caster(), Target(), int(ADJACENCY_SELECTION)))
    t = TriggerAnd(t, Not(TriggeringAbilityIs(EXCLUDED_PINPOINT)))
    return TriggerAnd(t, Not(TriggeringAbilityIs(EXCLUDED_TEMPTING_TRAP)))


def savior_chance() -> int:
    """`IdunBattleLogic.Entities.DSLFormulas$$ConfigConst(0x2a = AbilityConstantType.chance,
    abilityState)` = `gameconfig.abilities.SaviorProtocols.constants.chance`.

    C'est une CONSTANTE d'ability (pas une variable de niveau) : elle ne depend ni du rang du
    porteur ni du niveau du passif -- d'ou `constants`, et non `variables`. Cle absente -> `0`,
    donc `Maybe(0)` ne declenche jamais (degradation SURE : on n'invente pas un transfert)."""
    import gameconfig as GC
    v = ((GC.ability(ABILITY_ID) or {}).get("constants") or {}).get(CHANCE_CONSTANT.name)
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def savior_behaviour_tree(rng, *, transfer_ability=None, attack_ability=None):
    """`SaviorProtocolsAbility$$CreateBehaviour` -- LU VERBATIM :

        transfer = DSLBehaviors.TransferDamage(<+0x78>, sel+0x48, sel+0x60, sel+0x30,
                                               sel+0x88, sel+0x90)
        chance   = DSLFormulas.ConfigConst(0x2a, this+0x20)
        maybe    = DSLTriggers.Maybe(chance)                    // <-- DSL**Triggers**, un PREDICAT
        return     DSLBehaviors.If(maybe, transfer, 0)

    ⚠ **`Maybe` est ici la surcharge PREDICAT** (`IdunBattleLogic.Entities.DSLTriggers$$Maybe`,
    `IdunBattle.Entities.Triggers.MaybeTrigger`), PAS le noeud EFFET homonyme
    (`IdunBattle.Entities.Behaviours.MaybeBehaviour`). Le confondre changerait la STRUCTURE de
    l'arbre (un behaviour enveloppant au lieu d'une condition d'`If`) pour un resultat en apparence
    identique -- exactement le genre de recopie de voisin que la doctrine interdit.

    UN tirage `NextBool(chance)`, consomme AVANT de savoir si le transfert aboutira : tout drone
    dont le TRIGGER a passe le consomme, meme si le pending est deja vide. Le RNG est un CHAMP de
    l'instance native (`MaybeTrigger+0x18`), d'ou son passage au CONSTRUCTEUR ici.

    La branche `else` est le 4e argument natif, ici `(void *)0x0` -> ABSENTE.

    Les selecteurs : `Caster@<+0x48>` = la SOURCE du degat = `Actor()` cote port (le vecteur
    `pre_damage_taken_triggers` pose `caster == actor == la source`, cf. sa docstring) ;
    `Target@<+0x60>` = la VICTIME ; `Owner@<+0x30>` = le DRONE = `Caster()` cote port."""
    return If(MaybeTrigger(rng, savior_chance()),
              TransferDamage(caster_sel=Actor(),
                             original_target_sel=Target(),
                             transfer_targets_sel=Caster(),
                             # #1020-r2 -- les 4e et 5e arguments natifs, sur leurs canaux propres.
                             # `<DSLSelectors+0x88>` = `CurrentAbilitySelector` = `+0x60`, que
                             # `BaseTriggeredAbility$$Execute` vient d'ecrire AVANT ce behaviour :
                             # c'est la triggered elle-meme.
                             transfer_ability=transfer_ability,
                             # `<+0x90>` = `TriggeringAbilitySelector` = `+0x98`, que le publieur y
                             # a mis et que `BaseTriggeredAbility$$Execute` n'ecrira qu'APRES : c'est
                             # l'ability qui inflige le degat.
                             attack_ability=attack_ability),
              None)


class SaviorProtocolsAbility(TriggeredAbility):
    """`SaviorProtocolsAbility` -- cf. l'en-tete du module pour la chaine native et les residus.

    `On(0x39 = PreDamageTaken) & AreFriends(Target, Owner) & HasFaction(Target, Tau)
     & !ActorHasTriggeredAbility(Target, 1120) & !AreEqual(Target, Owner)
     & IsAdjacent(Owner, Target)`
    -> `If(Maybe(chance = 50), TransferDamage(source, victime, DRONE))`."""

    event_id = _ON_PRE_DAMAGE_TAKEN
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.SaviorProtocols)      # 0x460 = 1120

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`CreateTrigger` moins le volet `On(0x39)` du dispatch.

        Le porteur (`self.owner_id`) est l'`Owner@<+0x30>` ; `ev.target_id` la victime ;
        `ev.actor_id` la source du degat.

        `attack_ability_type` = le canal `AbilityEntities+0x98`, que les DEUX `!TriggeringAbilityIs`
        comparent. Il vient d'`ev.triggering_effect`, celui des deux champs d'evenement qui porte
        `+0x98` (l'autre, `ev.triggering_ability`, porte `+0x60` -- leurs NOMS Python sont
        historiques et trompeurs, cf. le bloc de commentaire de `TriggerEvent`). Meme voie que
        `relic_power_fist.py`, qui expose le meme slot `<DSLSelectors+0x90>` a son arbre."""
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        entities = replace(entities, attack_ability_type=ev.triggering_effect)
        return bool(savior_trigger_tree().evaluate(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        savior_behaviour_tree(
            state.rng,
            # `+0x60`, ecrit par `BaseTriggeredAbility$$Execute` AVANT le behaviour. Cote port ce
            # canal est `state.triggering_ability`, pose autour d'`execute_behaviour` par
            # `triggers/dispatch/core.py` -- avec exactement cet id. On le LIT plutot que de
            # recopier la constante : si le foyer cessait de le poser, le gate doit s'en apercevoir.
            transfer_ability=state.triggering_ability,
            # `+0x98`, que le publieur d'`On(0x39)` a rempli depuis la `DamageSource` du coup et que
            # `BaseTriggeredAbility$$Execute` n'ecrasera qu'APRES ce behaviour.
            attack_ability=ev.triggering_effect).execute(entities, ectx)
        transfers = [p for (n, p) in ectx.emitted if n == "TransferDamage"]
        return {"passive": ABILITY_ID, "owner": int(self.owner_id),
                "chance": savior_chance(),
                "transfers": transfers,
                "transferred": bool(transfers and any(t.get("result") for t in transfers)),
                "dsl": True}
