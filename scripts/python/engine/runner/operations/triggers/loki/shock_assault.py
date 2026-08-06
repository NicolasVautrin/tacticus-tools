"""`IdunBattle.Entities.Effects.Loki.ShockAssaultBuffEffect` (effet 0x3e8 = 1000, pose par
`IdunBattleLogic.Entities.Abilities.Active.Loki.ShockAssaultAbility$$CreateBehaviour` sur les
Inceptors amis adjacents a `ultraInceptorSgt`) -- son TRIGGER DE RETRAIT.

## Pourquoi il ne suffit PAS de declarer la classe d'effet

La pose est `AddStaticStatModifierEffect(<Inceptors>, 0x3e8, stat = 0 ATTACK,
Get(ConfigVar(8 = extraDmg)), turns = **NULL**, isHidden)` : cote timer l'effet est **PERMANENT**.
Declarer la seule classe (`entities/effects/loki/shock_assault.py`) ferme l'ATTRIBUTION du seed,
mais laisserait le `+extraDmg` d'ATTACK coller **a vie** au summon, la ou l'i2 dit « for this
attack ». Le natif le borne par un TRIGGER, pas par une duree -- et c'est ce module-ci.

## RE native (decompile ghidra, build `rnca9r7q6c`)

`IdunBattle.Entities.Effects.Loki.ShockAssaultBuffEffect$$CreateRemoveEffectTrigger` :

    On(0xa, ownerNeedsToBeAlive: 1)          # `IdunBattleLogic.Entities.DSLTriggers$$On(df, 0xa, 1)`
      & get_OwnerIsCaster                    # `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsCaster`

C'est le SEUL membre propre de la classe (elle derive de
`IdunBattle.Entities.Effects.StaticStatModifierEffect` et n'en surcharge rien d'autre). Le trigger
n'est PAS enregistre par la classe : c'est `IdunBattle.Entities.Effects.BaseEffect$$
CreateHandleTriggerAbilities` (le wrapper GENERIQUE au-dessus de
`CreateHandleTriggerAbilitiesInternal`) qui, quand le virtuel `CreateRemoveEffectTrigger` rend un
trigger non nul, AJOUTE a l'`ArraySet` de l'effet

    Triggered( CreateRemoveEffectTrigger(), DSLFactory.RemoveEffect(df@0x150) )

(== `IdunBattle.Entities.Effects.BaseEffect$$GetRemoveEffectBehaviour`, `df@0x150` = le selecteur
d'ENTITE-EFFET COURANTE -> retire CETTE instance). Meme greffe generique que
`InspiredToGreatness_OverrideLevel` (#114) et `Chronometron_ExtraDamage` (R9).

`0xa` = `EventTriggerType.AttackDamageAttack`, le 2e des deux events de cloture d'attaque emis par
`IdunBattle.Operations.FinishAttackOperation$$Execute`, sous le gate `currentAttack@+0x2c != 0`
(« cette attaque a comporte une ATTAQUE-A-DEGATS »). Cote port, le vecteur existe deja :
`triggers/dispatch/attack.py::attack_damage_attack_triggers`, emis a la SORTIE des operations
d'attaque-a-degats.

⚠ **C'est le MEME event que celui qui DECLENCHE la pose** : `ShockAssaultAbility$$CreateTrigger` =
`On(0xa) & get_OwnerIsCaster & AmountIsGreaterThanZero(GetAffectedUnits(...))`. Les deux ne se
marchent pas dessus parce que le predicat `OwnerIsCaster` designe des unites DIFFERENTES -- le
BELLATOR pour la pose, l'INCEPTOR pour le retrait. Le buff survit donc a l'attaque du Bellator qui
l'a pose, et meurt a la cloture de l'attaque de l'Inceptor (celle que le noeud `PerformAIAbility`
du meme behaviour vient de lui faire jouer). Le degat de cette attaque-la EST buffe : il est
resolu pendant l'attaque, `On(0xa)` ne fire qu'a sa cloture.

**Regime ou le buff SURVIT** (et donc ou il est OBSERVABLE dans `decisionView.effects`) : quand
l'Inceptor n'attaque pas. Le `customUtility` de `PerformAIAbility`
(`...ShockAssaultAbility$$u003CCreateBehaviouru003Eb__1_1`) rend `null` -- donc aucune action --
des que `UnitExtensions.IsAlive(<la cible>)` est faux : si le Bellator TUE sa cible, l'Inceptor
garde son buff.

## Frontiere DSL/imperatif (#149)

Le behaviour est un noeud `DSLFactory.RemoveEffect` -> porte comme un ARBRE (feuille `RemoveEffect`),
qui delegue au revert imperatif (`AddEffectOperation.revert_stat_mods` = `AStatModifierEffect$$
RevertModification`, `ChangeStat` part 6, meme entite-effet qu'a l'apply). Le predicat du trigger
(`OwnerIsCaster`) est COLLAPSE imperativement dans `matches`, comme tous les triggers portes
(doctrine SuppressiveFire #74 / MasterAnnihilator / InspiredToGreatness).

COLLAPSE ASSUME, identique a celui d'`InspiredToGreatnessOverrideLevelRemove` : le natif retire
**l'instance** (`RemoveEffect(df@0x150)`), le port retire tous les 1000 non consommes du porteur
(`RemoveEffect(effectType, Caster())`, la seule forme portee). Le gate << deja present >> d'
`AddEffectOperation` garantit au plus UNE instance de 1000 par unite (la classe ne pose pas
`stacks_stat_mod_on_add`) -> les deux formes coincident.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import RemoveEffect
from .....entities.effect_type import EffectType
from .....entities.selectors.tiles import Caster
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import EffectTrigger, TriggerEvent

SHOCK_ASSAULT_BUFF = int(EffectType.ShockAssault_Buff)          # 0x3e8 = 1000


class ShockAssaultBuffRemove(EffectTrigger):
    """`ShockAssaultBuffEffect$$CreateRemoveEffectTrigger` = `On(0xa = AttackDamageAttack) &
    get_OwnerIsCaster` -> `BaseEffect$$GetRemoveEffectBehaviour` = `RemoveEffect(<cette instance>)`.

    OBSERVABLE : l'Inceptor buffe frappe UNE fois avec le `+extraDmg` d'ATTACK, puis 1000 disparait
    de `decisionView.effects` et sa stat ATTACK revient a sa valeur nue. Un Inceptor qui n'attaque
    pas (cible du Bellator morte -> `customUtility` nulle) garde son buff jusqu'a sa prochaine
    attaque."""
    effect_type = SHOCK_ASSAULT_BUFF
    event_id = EventTriggerType.AttackDamageAttack          # 0xa = 10

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsCaster` : le PORTEUR de l'effet est l'attaquant dont l'attaque se cloture
        # (`AbilityEntities` de `On(0xa)` : caster/actor = l'attaquant, cf. `attack_damage_attack_triggers`).
        return ev.actor_id is not None and int(ev.actor_id) == int(self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        RemoveEffect(SHOCK_ASSAULT_BUFF, Caster()).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        if not removed:
            return None
        return {"effect": "ShockAssault_Buff", "owner": int(self.owner_id),
                "removed": removed, "consumed_on": ev.target_id}
