"""`HealingBalms` (`EffectType` 0x5e4 = **1508**) -- le SOIN RETARDÉ du passif de
`spaceWolfPriest` << Baldr >>. #966

i2 (`UnitEffects/HealingBalms_Description`, autoritatif) : << Is healed for {[hpToHeal]} Health at
the start of their next turn. >>

L'effet est posé sur la cible soignée par `...Active.Loki.HealingBalms_HealAbility$$ExecuteBehaviour`
(`AddEffect(0x5e4, AbilityStateReference, source = Caster@+0x48, targets = Target@+0x60)`, cf.
`runner/abilities/loki/healing_balms.py`). Ce module ne porte QUE son couple trigger/behaviour.

## LES DEUX ARBRES (build `rnca9r7q6c`)

`IdunBattle.Entities.Effects.Loki.HealingBalmsEffect$$CreateTargetTrigger` -- MIRROR :

    On(0x13 = 19 = EventTriggerType.TurnStart_Other, ownerNeedsToBeAlive: 1)
      op_BitwiseAnd <DSLTriggers+0x28>

`<DSLTriggers+0x28>` = `IsTurnOf(Owner)` -- le champ que `DSLTriggers$$InitializeShared` construit
depuis le sélecteur `Owner@DSLSelectors+0x30`. MÊME slot que `ToughToKill_HealAbility` et
`LivingMetalRepairAbility` : le soin ne tombe QU'AU début du tour du PORTEUR de l'effet (l'allié
soigné), pas au tour de Baldr -- c'est littéralement le « at the start of **their** next turn ».

`IdunBattle.Entities.Effects.Loki.HealingBalmsEffect$$CreateTargetTriggerBehaviour` -- MIRROR :

    amount = DSLFormulas.ConfigVar(0x20 = AbilityVariableType.hpToHeal,
                                   <abilityState du poseur>, config@this+0x60)
    healer = DSLSelectors.EffectSource( DSLSelectors.Get(effect) )
    cible  = Owner@DSLSelectors+0x30
    return DSLBehaviors.Heal(healer, cible, amount,
                             IdunBattle.Entities.Behaviours.HealBehaviourOptions$$ForHeal(effect))
             op_Addition  IdunBattle.Entities.Effects.BaseEffect$$GetRemoveEffectBehaviour(this)

Quatre points que la STRUCTURE donne, et qu'aucun tooltip ne donnerait :

* **le soin est CONSOMMÉ** : `GetRemoveEffectBehaviour(this)` est joint au `Heal` par
  `op_Addition` -- une seule salve, pas une régénération par tour. Sans lui, l'effet soignerait à
  CHAQUE début de tour jusqu'à expiration de sa durée par défaut : dégradation PERMISSIVE, aucune
  erreur ;
* **les deux entités du soin sont DISTINCTES** : le SOIGNEUR est `EffectSource` (Baldr), la CIBLE
  est l'`Owner` (l'allié qui porte l'effet). C'est ce couple que
  `IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed(caster, target, scope, removeEffects)`
  consulte -- d'où le passage OBLIGATOIRE par `HealUnitOperation.execute`, qui porte le gate ET
  `PredictHeal`, jamais une mutation directe de `HealthComponent` (#520 / #564, deux fois la même
  panne). Source non captée -> repli sur le porteur, dégradation NOMMÉE ;
* **la magnitude est un `ConfigVar` du PASSIF, pas de l'arme** : `hpToHeal` vit dans
  `abilities.HealingBalms.variables` et EST dans `variablesAffectedByRarityBonus`. C'est la
  distinction que `engine/predict.py` note déjà (« `HealingBalms_Heal` -> clé `HealingBalms` pointe
  sur la config du PASSIF, dont le `hpToHeal` alimente le soin RETARDÉ, PAS l'action ») ;
* **`ForHeal`, pas `ForRegenerate`** : `(scope 0, removeEffects 1)` -- LU aux xrefs (#576). Les deux
  ne sont pas interchangeables (`scope 1` armerait le cap de groupe `GetGroupUnitHealLimit`).

DOCTRINE #149 : le `CreateTargetTrigger` est COLLAPSE dans `matches()` ; le behaviour appelle
l'Operation impérative `HealUnitOperation`.

ASCII only.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .....dsl.event_trigger_type import EventTriggerType
from .....entities.ability_variable_type import AbilityVariableType
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from ....components import OwnerComponent
from ...heal import HealUnitOperation
from ..base import EffectTrigger
from ...remove_effects import remove_effect_instance

if TYPE_CHECKING:                                        # pragma: no cover
    from ....state import State
    from ..base import TriggerEvent

#: Nom gameconfig du PASSIF -- `config@this+0x60` est la config de `HealingBalms`, pas celle d'une
#: active (1212 n'a AUCUNE entrée `abilities.*`).
HEALING_BALMS = "HealingBalms"
HEALING_BALMS_EFFECT = int(EffectType.HealingBalms)      # 0x5e4 = 1508

#: `HealBehaviourOptions$$ForHeal` = `(scope 0, removeEffects 1)` -- littéraux du call-site.
FOR_HEAL_SCOPE = 0
FOR_HEAL_REMOVE_EFFECTS = True


class HealingBalmsDelayedHeal(EffectTrigger):
    """`On(TurnStart_Other = 0x13 = 19, ownerNeedsToBeAlive: 1) & IsTurnOf(Owner)`
    -> `Heal(EffectSource, Owner, ConfigVar(hpToHeal), ForHeal) + RemoveEffect(self)`.

    Cf. l'en-tête de module pour les deux arbres natifs."""
    event_id = int(EventTriggerType.TurnStart_Other)      # On(0x13 = 19)
    effect_type = HEALING_BALMS_EFFECT

    def _instance(self, state: "State"):
        """L'entité-effet 1508 portée par `owner_id`. Elle porte l'`AbilityState` du POSEUR
        (`scale_from_source=True` au call-site d'`AddEffect`) et sa SOURCE (Baldr)."""
        if state.effects is None:
            return None
        for e in state.effects.by_unit.get(int(self.owner_id), []):
            if not e.consumed and e.effect_type == HEALING_BALMS_EFFECT:
                return e
        return None

    def matches(self, state: "State", ev: "TriggerEvent") -> bool:
        # Gate `EffectComponent.IsActive @+0x5c` (#231) -- ce trigger vient de
        # `$$CreateTargetTrigger`, donc du rail que
        # `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` gate AVANT
        # d'appeler `ShouldTrigger`. Même lecture que `BloodChaliceHealOnMeleeAttack`.
        inst = self._instance(state)
        if inst is None or not inst.active:
            return False
        # `<DSLTriggers+0x28>` = `IsTurnOf(Owner)` : le soin ne tombe qu'au début du tour du PORTEUR
        # de l'effet. `ownerNeedsToBeAlive: 1` est déjà tenu par le dispatch (il ne visite que les
        # porteurs vivants) -- même lecture que `ToughToKillHealAbility`.
        e = state.get_entity(self.owner_id)
        if e is None:
            return False
        oc = e.get_component(OwnerComponent)
        return oc is not None and ev.player_id is not None and oc.player == int(ev.player_id)

    def execute_behaviour(self, state: "State", ev: "TriggerEvent") -> Optional[dict]:
        inst = self._instance(state)
        lvl = mult = None
        healer = self.owner_id                           # repli NOMMÉ si `EffectSource` est absente
        if inst is not None:
            lvl = (inst.active_ability_level if inst.active_ability_level is not None
                   else inst.ability_level)
            mult = inst.ability_variables_multiplier
            if inst.source is not None:                  # DSLSelectors.EffectSource -> BALDR
                healer = int(inst.source)
        amount = ability_var(HEALING_BALMS, AbilityVariableType.hpToHeal.name, lvl,
                             multiplier_pct=(100 if mult is None else int(mult)))
        # `GetRemoveEffectBehaviour(this)` est joint au `Heal` par `op_Addition` : il part QUOI
        # QU'IL ARRIVE, y compris quand le soin est nul (montant 0, cible à PV pleins, gate fermé).
        # Le consommer AVANT le soin serait faux dans l'autre sens ; l'ordre natif est Heal puis
        # Remove, mais les deux behaviours sont indépendants -- on retire APRÈS.
        healed = None
        if amount:
            healed = HealUnitOperation.execute(state, healer, int(self.owner_id), int(amount),
                                               scope=FOR_HEAL_SCOPE,
                                               remove_effects=FOR_HEAL_REMOVE_EFFECTS)
        removed = self._consume(state, inst)
        if not amount and not removed:
            return None
        return {"type": "healing_balms_delayed_heal", "unit": int(self.owner_id),
                "healer": int(healer), "hp_to_heal": int(amount or 0), "healed": healed,
                "removed": removed}

    def _consume(self, state: "State", inst) -> bool:
        """`IdunBattle.Entities.Effects.BaseEffect$$GetRemoveEffectBehaviour(this)` -- l'effet se
        consomme lui-même. Foyer PARTAGÉ `operations/remove_effects.py::remove_effect_instance`
        (#389-r2), jamais un `consumed = True` recâblé à la main : le retrait doit émettre ses deux
        events `On(0x3f = PreEffectRemoved)`/`On(0x40 = EffectRemoved)` et dé-enregistrer le nom de
        l'`EffectsOwnedComponent`."""
        if inst is None:
            return False
        return bool(remove_effect_instance(state, int(self.owner_id), inst))
