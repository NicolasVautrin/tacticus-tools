"""PhoenixGem -- self-revive one-shot-par-bataille du relic unique porte par `eldarAutarch` (« Aethana »).
#79. **N'est PAS une sous-classe de `ReviveEffect`** : c'est un couple
`PhoenixGem_CanReviveEffect` (marqueur, base `BaseEffect`) + `PhoenixGem_ReviveAbility` (TriggeredAbility
autonome) qui appelle le MEME `DSLFactory.Revive` -> `ReviveUnitOperation` (donc le meme sous-systeme
revive-en-place, d'ou son rattachement a case-66).

i2 authoritatif : « The first time each battle that Aethana is defeated, she is instead revived with a
maximum of {hp} Health remaining, **even if Overkilled**. »

Artefact natif (RE ghidra gqfc5mff6c, VA citees) :

  PhoenixGem_CanReviveEffect..ctor   @180f5e680  `BaseEffect..ctor(turnsEnabled=1,
                                                  source=AbilityOrEffect(0x5b2=1458
                                                  TriggeredAbilityType.PhoenixGem))`
                                                  -> effet-MARQUEUR `EffectType.PhoenixGem_CanRevive`=1451
  PhoenixGem_CanReviveEffect.CreateHandleTriggerAbilitiesInternal @180f5e4a0
      ArraySet{
        Triggered( On(0x2e) & OwnerIsTarget & CurrentAbilityIs(AbilityOrEffect(0x5b2)),
                   RemoveEffect(self@0x150) ),          # revive consomme -> le marqueur DISPARAIT
        Triggered( On(0x2f) & OwnerIsTarget, RemoveEffect(self@0x150) )
      }
  PhoenixGem_ReviveAbility.CreateTrigger   @1811117b0
      `OnPreDeath(ignoreOverkill=TRUE) & OwnerIsTarget & HasEffect(self@0x148, 0x5ab=1451, 0, 6)`
      -> `ignoreOverkill=1` : `OnDeathEvent @180df7ad0` n'ajoute AUCUN gate overkill
         => « **even if Overkilled** » (contraste Narthecium/RitesOfMorkai) ; lu DIRECTEMENT dans le
         decompile (constante litterale du call, pas un virtuel) -- rien a deviner ici.
  PhoenixGem_ReviveAbility.CreateBehaviour @181111610
      `hp = GetVariableForLevel(config@0x20, 0x1d='hp', abilityState)`
      `Revive(self@0x148, self@0x148, Direct(hp), healType=2, AbilityOrEffect(this.Id), 0, -1000, 0)`
      (pas de `Maybe` -> inconditionnel ; pas de `Min(hp, maxPV)` explicite dans l'arbre, mais
       `ReviveBehaviour.Execute @180fd1230` re-clampe a `GetMaxReviveAmount` -> `ReviveUnitOperation`
       clampe de toute facon via `SetHealth @180e93450`.)

PORTEUR / VOIE : PhoenixGem est un **UniqueRelic** (cf. `PowerCalculationPlatformIntegrationTest$$
UniqueRelicPhoenixGem @180b9e9a0`), PAS une ability du kit d'`eldarAutarch` (dont les abilities sont
`Loki_SwoopingHawk` / `PathOfCommand`). L'unite EST dans le pool runner, mais le relic ne se pose pas
depuis `rl_duel build` -> l'effet 1451 n'est pas posable. Port MIRROR valide OFFLINE (effet injecte).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import op_add
from .....entities.selectors import Caster
from ...effects import BaseEffect  # noqa: F401  (documente le type materialise dans state.effects)
from ..base import EffectTrigger, TriggerEvent
from ..revive_effect import Revive, RemoveReviveEffect, can_be_revived
from ....abilities.behaviours import entities_from_state
from .....entities.effects.magnitude import ability_var

ABILITY_ID = "PhoenixGem"
PHOENIX_GEM_CAN_REVIVE = 1451          # EffectType.PhoenixGem_CanRevive (le marqueur « peut encore revive »)


class PhoenixGemReviveAbility(EffectTrigger):
    """`PhoenixGem_ReviveAbility` (CreateTrigger @1811117b0 / CreateBehaviour @181111610), collectee via
    l'effet-marqueur `PhoenixGem_CanReviveEffect` (1451, @180f5e680) porte par l'unite -- d'ou le rail
    `EFFECT_TRIGGERS[1451]` (mirror de `CreateHandleTriggerAbilitiesInternal @180f5e4a0`, qui EST le
    vecteur natif d'enregistrement des trigger-abilities d'un effet)."""
    effect_type = PHOENIX_GEM_CAN_REVIVE
    event_id = EventTriggerType.PreUnitDeath    # OnPreDeath -> OnDeathEvent(1)
    # `OwnerIsTarget` : le porteur du marqueur EST le mourant -> il est deja `alive=False` quand le port
    # emet PreUnitDeath (meme besoin que FinalJustice/Ambush/RitesOfMorkai).
    fire_on_death = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # get_OwnerIsTarget : seul le porteur du marqueur est revive
        if ev.dying_id is None or ev.dying_id != self.owner_id:
            return False
        # HasEffect(self, 1451) : le marqueur doit etre encore la (il est RETIRE apres le 1er revive
        # -> « the first time each battle »). `collect_effect_triggers` skippe deja les effets consommes,
        # on re-verifie ici (re-validation de cible du RunPhase).
        eff = getattr(state, "effects", None)
        if eff is None:
            return False
        if not any(e.effect_type == PHOENIX_GEM_CAN_REVIVE and not e.consumed
                   for e in (eff.by_unit.get(int(self.owner_id)) or [])):
            return False
        # `OnPreDeath(ignoreOverkill=TRUE)` -> AUCUN gate overkill (« even if Overkilled ») : on ne teste
        # DELIBEREMENT PAS `ev.overkill` ici.
        entities = entities_from_state(state, self.owner_id, ev.dying_id)
        tgt = entities.target
        if tgt is None:
            return False
        # `DSLFactory.Revive` -> `ReviveBehaviour` verifie la revivabilite en amont du mutateur ; on
        # mirroir le meme gate que la base ReviveEffect (mort + non-PermaDeath + heal-type).
        return can_be_revived(entities, tgt, ev.dying_id, state)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        entities = entities_from_state(state, self.owner_id, ev.dying_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        level, mult = self._level(state)
        # `CreateBehaviour @181111610` = Revive(self, self, Direct(GetVariableForLevel('hp'))) -- AUCUN
        # `Maybe` (inconditionnel). Le 2e volet (retrait du marqueur) est, cote NATIF, un trigger SEPARE
        # de `PhoenixGem_CanReviveEffect` (`On(0x2e) & OwnerIsTarget & CurrentAbilityIs(PhoenixGem)`
        # @180f5e4a0). Le port le chaine ici parce que le vecteur d'event `0x2e` n'est pas dispatche
        # (cf. `ReviveUnitOperation` : « emet On(UnitRevived) -> pas d'autre consommateur porte »).
        # Observable IDENTIQUE (le retrait suit immediatement le revive) ; a RE-SEPARER le jour ou le
        # vecteur d'event est porte.
        op_add(Revive(Caster(), ABILITY_ID, "hp", level, mult),
               RemoveReviveEffect(Caster(), PHOENIX_GEM_CAN_REVIVE)).execute(entities, ectx)
        revives = [p for n, p in ectx.emitted if n == "Revive" and p.get("revived")]
        return {"ability": ABILITY_ID, "owner": self.owner_id, "dying": ev.dying_id,
                "revives": revives,
                "gate_consumed": any(n == "RemoveReviveEffect" for n, _ in ectx.emitted)}

    def _level(self, state: State):
        """`GetVariableForLevel(config@0x20, 0x1d='hp', abilityState)` : le niveau vient de l'AbilityState
        du RELIC porte par l'effet 1451 (pas du passif de l'unite)."""
        eff = getattr(state, "effects", None)
        if eff is not None:
            for e in (eff.by_unit.get(int(self.owner_id)) or []):
                if e.effect_type == PHOENIX_GEM_CAN_REVIVE:
                    lvl = e.active_ability_level if e.active_ability_level is not None else e.ability_level
                    return lvl, (e.ability_variables_multiplier or 100)
        return None, 100


# `PhoenixGem.hp` n'est PAS dans `variablesAffectedByRarityBonus` (gameconfig) -> pas de scaling rarete :
# `ability_var('PhoenixGem','hp', lvl)` suffit. Sanity-check i2 : au niveau du tooltip la valeur vaut 5817.
_ = ability_var
