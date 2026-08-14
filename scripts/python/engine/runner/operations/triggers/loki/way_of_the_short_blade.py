"""`WayOfTheShortBlade_AttackAbility` (#1019-r2) -- l'ATTAQUE NORMALE SUPPLEMENTAIRE que le passif de
`tauFarsight` accorde a lui-meme et aux `Hero` T'au amis a portee, apres CHACUNE de leurs attaques de
MELEE.

RE : decompile ghidra, build `rnca9r7q6c` (les deux corps ci-dessous sont LUS verbatim, pas deduits).

i2 (`Abilities/WayOfTheShortBlade_CurrentLevelDescription`, 2e phrase) : « Commander Farsight and
other friendly T'au Empire Characters within {range} hexes that perform a melee attack immediately
perform a normal ranged attack against the same unit, **even if they are adjacent to it**. »

===================================================================================================
LES DEUX ARBRES, LUS VERBATIM
===================================================================================================

`...Triggered.Loki.WayOfTheShortBlade_AttackAbility$$CreateTrigger` =

      On( 0x9 = EventTriggerType.Attack, ownerNeedsToBeAlive = 1 )
    & IsMeleeAttack()
    & AreFriends( Caster@<DSLSelectors+0x48>, Owner@<DSLSelectors+0x30>, 0 = ByCurrentTeam )
    & IsEffectTarget( Caster@<+0x48>, 0x5dc = 1500 WayOfTheShortBlade_AdditionalAttackMarker )

`...WayOfTheShortBlade_AttackAbility$$CreateBehaviour` =

      AddFlag( Caster@<+0x48>, 0x15 = UnitFlag.ForceRangedAttack )
    & UseNormalAttackIfAble( Caster@<+0x48>, Target@<+0x60> )
    & RemoveFlag( Caster@<+0x48>, 0x15 )

Les trois `op_BitwiseAnd` du behaviour s'associent `(AddFlag & UseNormalAttackIfAble) & RemoveFlag` --
lu au decompile (les deux `op_BitwiseAnd` sont emis dans cet ordre), et l'ordre est LOAD-BEARING :
c'est la parenthese POSE/RETIRE autour du sous-cast.

===================================================================================================
POURQUOI LE DRAPEAU EST LE COEUR DE CETTE ABILITY -- deux consommateurs, pas un
===================================================================================================

`UnitFlag.ForceRangedAttack` (21) est LU par les deux etages qui comptent, et le PORT ne le lisait
qu'a moitie :

  1. **La SELECTION D'ARME.** `IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack`
     (slot `0xaf`) : `if (rangeType == Normal && !HasFlag(attacker, 0x15) && AreEntitiesAdjacent(..))
     return FindMeleeWeapon(..)`. Sans le drapeau, l'attaque supplementaire d'un caster ADJACENT
     repartirait en MELEE -- l'exact contraire du « even if they are adjacent to it ». Cet etage
     etait ABSENT du port (aucun appelant ne passait le drapeau) ; il est pose par la meme tranche,
     au FOYER partage `services/battle_query.py`.
  2. **LE GARDE-FOU DE RE-ENTRANCE.** L'attaque supplementaire emet a son tour `On(0x9 = Attack)`.
     Elle ne se re-declenche pas parce qu'elle est RANGED -- donc `IsMeleeAttack()` est FAUX pour
     elle. Ce n'est pas un garde ecrit ici : c'est une CONSEQUENCE de l'etage 1, et c'est ce qui
     rend l'etage obligatoire plutot que cosmetique. Le port le realise par `ev.ranged`, que
     l'emetteur (`dispatch/attack.py::attack_triggers`) thread depuis l'arme REELLEMENT choisie.
     ⚠ SECOND garde, natif lui aussi : un caster SANS arme de portee utilisable rend
     `FindRangedWeapon -> null`, et `ALoki_NormalAttackAbility$$ExecuteBehaviour` retourne
     immediatement (`if (weapon == null) return;`) -- aucun `On(9)` n'est emis, donc aucune boucle.
     Le port porte ce gate depuis #419-r1-tr14-r1-r1 (`if _w is None: return None`).

===================================================================================================
LE GATE `IsEffectTarget(Caster, 1500)` -- pourquoi ce n'est PAS `HasEffect`
===================================================================================================

L'effet 1500 vit sur FARSIGHT SEUL (mesure live #1019 : `decisionView.effects` le porte sur
`u81 [tauFarsight]` et sur personne d'autre, deux autres T'au etant pourtant a portee). Ce sont ses
CIBLES -- la liste `EffectComponent.Targets @+0x48`, peuplee par le `CreateTargetSelector` -- qui
designent les beneficiaires. `HasEffect(Caster, 1500)` serait donc FAUX pour tout le monde sauf
Farsight : le port passe par le foyer `entities/effect_targets.py`, qui RE-DERIVE la liste de cibles
a la lecture (le selecteur de 1500 y est inscrit par la meme tranche).

⚠ **TRI-ETAT** : `is_effect_target` rend `None` quand le substrat manque (pas de canal `faction`,
constante `range` absente du gameconfig). Ce trigger traite `None` comme un REFUS -- degradation
RESTRICTIVE et nommee : declencher une attaque supplementaire sur une geometrie non mesuree serait
PERMISSIF, et c'est le sens de faute que la doctrine interdit en priorite.

===================================================================================================
CE QUE CE MODULE NE PORTE PAS
===================================================================================================

* Le second argument d'`On` (`ownerNeedsToBeAlive = 1`) est le gate « owner vivant » de
  `CanGetAbilityTrigger`, tenu par `dispatch/core.evaluate_trigger_operation` en amont
  (`fire_on_death = False`, le defaut) -- rien a ecrire ici.
* Le sous-cast passe par `UseNormalAttackIfAble`, donc par `ActiveAbilityOperation` avec
  `InvalidTargetPolicy = Skip` : une cible devenue invalide (morte au coup precedent) est un NO-OP
  complet, comme cote natif.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import op_and
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Target
from .....entities.selectors.tiles import Caster
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.unit_flag import UnitFlag
from ....abilities.behaviours.combat import UseNormalAttackIfAble
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.flags import AddFlag, RemoveFlag
from ....components import is_effect_target as _is_effect_target
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

#: CLE du registre `ABILITY_TRIGGERS` = le nom gameconfig du passif, pris au MEMBRE de l'enum et non
#: recopie en chaine (meme geste que `CALL_IN_REINFORCEMENTS_KEY`) : un renumerotage du build ferait
#: rougir `probe_313` au lieu de laisser une cle morte muette.
WAY_OF_THE_SHORT_BLADE_KEY = TriggeredAbilityType.WayOfTheShortBlade.name        # "WayOfTheShortBlade"
ABILITY_ID = WAY_OF_THE_SHORT_BLADE_KEY
WAY_OF_THE_SHORT_BLADE = int(TriggeredAbilityType.WayOfTheShortBlade)            # 0x5dc = 1500
#: `IsEffectTarget(Caster@<+0x48>, 0x5dc)` -- l'EFFET, homonyme du triggered a l'ordinal pres. Les
#: deux `0x5dc` ci-dessus sont DEUX enums differents (`TriggeredAbilityType` / `EffectType`), et ils
#: nomment ici la meme mecanique par coincidence de numerotation : les ecrire tous deux en ordinal
#: nu rendrait cette coincidence invisible.
ADDITIONAL_ATTACK_MARKER = int(EffectType.WayOfTheShortBlade_AdditionalAttackMarker)   # 0x5dc = 1500
#: `AddFlag/RemoveFlag(Caster, 0x15)` -- `IdunBattle.Entities.Enum.UnitFlag.ForceRangedAttack`.
FORCE_RANGED_ATTACK = int(UnitFlag.ForceRangedAttack)                            # 0x15 = 21


def way_of_the_short_blade_attack_tree():
    """`...WayOfTheShortBlade_AttackAbility$$CreateBehaviour` -- MIRROR 1:1, associativite comprise.

    `Caster()` = `DSLSelectors+0x48` (l'unite qui vient d'attaquer), `Target()` = `+0x60` (sa cible).
    Le caster du sous-cast est donc le BENEFICIAIRE, jamais Farsight -- c'est lui qui tire."""
    return op_and(
        op_and(AddFlag(Caster(), FORCE_RANGED_ATTACK),
               UseNormalAttackIfAble(Caster(), Target())),
        RemoveFlag(Caster(), FORCE_RANGED_ATTACK))


class WayOfTheShortBladeAttackAbility(TriggeredAbility):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.WayOfTheShortBlade_AttackAbility`.

    OBSERVABLE : Farsight, et tout `Hero` T'au ami dans son rayon, enchaine une attaque normale a
    DISTANCE sur la meme cible juste apres chacune de ses attaques de MELEE."""
    event_id = int(EventTriggerType.Attack)                          # `On(0x9, alive = 1)`
    TRIGGERED_ABILITY_ID = WAY_OF_THE_SHORT_BLADE                    # 0x5dc = 1500

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id is None or ev.target_id is None:
            return False
        # `IsMeleeAttack()` -- la nature de l'ARME choisie, threadee par l'emetteur du vecteur.
        # C'est AUSSI le garde-fou de re-entrance (cf. l'en-tete) : le sous-cast est ranged.
        if ev.ranged:
            return False
        # `AreFriends(Caster@<+0x48>, Owner@<+0x30>, 0 = ByCurrentTeam)`. L'attaquant peut etre le
        # porteur lui-meme (Farsight est ami de lui-meme, et le selecteur de 1500 l'inclut
        # explicitement par son `op_Addition Owner`) -- aucune soustraction `- Owner` ici.
        from ....components import OwnerComponent
        a = state.get_entity(int(ev.actor_id))
        o = state.get_entity(int(self.owner_id))
        ao = a.get_component(OwnerComponent) if a is not None else None
        oo = o.get_component(OwnerComponent) if o is not None else None
        if ao is None or oo is None or ao.team != oo.team:
            return False
        # `IsEffectTarget(Caster@<+0x48>, 0x5dc)` -- TRI-ETAT, `None` REFUSE (cf. l'en-tete).
        return _is_effect_target(state, int(ev.actor_id), ADDITIONAL_ATTACK_MARKER) is True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `caster_id = ev.actor_id` : sur CETTE ability le slot `Caster@+0x48` n'est PAS le porteur.
        # `owner_id` est threade EXPLICITEMENT parce que le natif les separe reellement ici (c'est le
        # cas rare que `entities_from_state` documente) -- le `AreFriends` du trigger l'atteste.
        entities = entities_from_state(state, int(ev.actor_id), int(ev.target_id),
                                       actor_id=int(ev.actor_id), owner_id=int(self.owner_id))
        way_of_the_short_blade_attack_tree().execute(entities, ectx)
        emitted: dict = {}
        for name, payload in ectx.emitted:
            emitted.setdefault(name, []).append(payload)
        attacks = emitted.get("UseNormalAttackIfAble", ())
        return {"passive": ABILITY_ID, "owner": int(self.owner_id),
                "caster": int(ev.actor_id), "target": int(ev.target_id),
                "flag_added": bool(any(p.get("added") for p in emitted.get("AddFlag", ()))),
                "flag_removed": bool(any(p.get("removed") for p in emitted.get("RemoveFlag", ()))),
                "extra_attacks": len(attacks)}
