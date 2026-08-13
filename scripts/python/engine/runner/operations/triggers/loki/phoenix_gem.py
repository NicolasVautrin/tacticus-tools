"""PhoenixGem -- self-revive one-shot-par-bataille du relic unique porte par `eldarAutarch` (« Aethana »).
#79. **N'est PAS une sous-classe de `ReviveEffect`** : c'est un couple
`PhoenixGem_CanReviveEffect` (marqueur, base `BaseEffect`) + `PhoenixGem_ReviveAbility` (TriggeredAbility
autonome) qui appelle le MEME `DSLFactory.Revive` -> `ReviveUnitOperation` (donc le meme sous-systeme
revive-en-place, d'ou son rattachement a case-66).

i2 authoritatif : « The first time each battle that Aethana is defeated, she is instead revived with a
maximum of {hp} Health remaining, **even if Overkilled**. »

Artefact natif (RE ghidra gqfc5mff6c, VA citees) :

  PhoenixGem_CanReviveEffect..IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$.ctor  `BaseEffect..ctor(turnsEnabled=1,
                                                  source=AbilityOrEffect(0x5b2=1458
                                                  TriggeredAbilityType.PhoenixGem))`
                                                  -> effet-MARQUEUR `EffectType.PhoenixGem_CanRevive`=1451
  IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal
      ArraySet{
        Triggered( On(0x2d=UnitRevived) & OwnerIsTarget
                   & CurrentAbilityIs(AbilityOrEffect(0x5b2=1458 TriggeredAbilityType.PhoenixGem)),
                   RemoveEffect(self@0x150) ),          # revive consomme -> le marqueur DISPARAIT
        Triggered( On(0x2e=UnitResurrected) & OwnerIsTarget, RemoveEffect(self@0x150) )
      }
      -> case-89 volet B3 : ces DEUX triggers sont desormais PORTES pour de vrai
      (`PhoenixGemRemoveMarkerOnRevive` / `PhoenixGemRemoveMarkerOnResurrect` ci-dessous), branches sur
      les vecteurs `unit_revived_triggers` (`On(0x2d = UnitRevived)`, emis par `ReviveUnitOperation` @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xac1) et
      `unit_resurrected_triggers` (`On(0x2e = UnitResurrected)`). Avant, le retrait etait CHAINE en dur au behaviour du
      revive faute de vecteur `On(0x2d = UnitRevived)` dispatche — la structure DSL est retablie.
  IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateTrigger
      `OnPreDeath(ignoreOverkill=TRUE) & OwnerIsTarget & HasEffect(self@0x148, 0x5ab=1451, 0, 6)`
      -> `ignoreOverkill=1` : `IdunBattleLogic.Entities.DSLTriggers$$OnDeathEvent` n'ajoute AUCUN gate overkill
         => « **even if Overkilled** » (contraste Narthecium/RitesOfMorkai) ; lu DIRECTEMENT dans le
         decompile (constante litterale du call, pas un virtuel) -- rien a deviner ici.
  IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateBehaviour
      `hp = GetVariableForLevel(config@0x20, 0x1d='hp', abilityState)`
      `Revive(self@0x148, self@0x148, Direct(hp), healType=2, AbilityOrEffect(this.Id), 0, -1000, 0)`
      (pas de `Maybe` -> inconditionnel ; pas de `Min(hp, maxPV)` explicite dans l'arbre, mais
       `IdunBattle.Entities.Behaviours.ReviveBehaviour$$Execute` re-clampe a `GetMaxReviveAmount` -> `ReviveUnitOperation`
       clampe de toute facon via `IdunBattle.Operations.ReviveUnitOperation$$SetHealth`.)

PORTEUR / VOIE : PhoenixGem est un **UniqueRelic** (cf. `PowerCalculationPlatformIntegrationTest$$
Loki.Tests.PlatformIntegrationTests.Tests.PowerCalculationPlatformIntegrationTest$$UniqueRelicPhoenixGem`), PAS une ability du kit d'`eldarAutarch` (dont les abilities sont
`Loki_SwoopingHawk` / `PathOfCommand`). Item `R_Booster_Block_PhoenixGem`,
`allowedUnits = ['eldarAutarch']`.

⚠ LA LIGNE QUI VIVAIT ICI DISAIT « le relic ne se pose pas depuis `rl_duel build` -> l'effet 1451
n'est pas posable » : c'est PERIME depuis le montage #237, et c'est MESURE (#1006). `eldarAutarch` est
au pool rank 17 et `rl_duel build --equip-relic "eldarAutarch:PhoenixGem[:lvl]"` monte la relique ;
le natif POSE alors l'effet 1451, que `decisionView.effects` publie (`probe_1006_reliques_aeldari.py`).
C'est l'etat 2 des TROIS d'une ability de relique, pas un « non confrontable ». La consequence
n'etait pas seulement documentaire : personne ne pouvant monter la relique, personne n'avait vu que
`_level` lisait le mauvais slot (cf. la docstring de `_level`).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.selectors.tiles import Caster
from ...effects import BaseEffect  # noqa: F401  (documente le type materialise dans state.effects)
from ..base import EffectTrigger, TriggerEvent, triggered_ability_state
from ..revive_effect import Revive, RemoveReviveEffect, can_be_revived
from ....abilities.behaviours.context import entities_from_state
from .....entities.effects.magnitude import ability_var
from .....entities.effect_type import EffectType   # #270-r1-r1-r3
from .....entities.triggered_ability_type import TriggeredAbilityType   # #270-r1-r1-r3

ABILITY_ID = "PhoenixGem"
PHOENIX_GEM_CAN_REVIVE = EffectType.PhoenixGem_CanRevive          # EffectType.PhoenixGem_CanRevive (le marqueur « peut encore revive »)
PHOENIX_GEM_ABILITY = TriggeredAbilityType.PhoenixGem             # TriggeredAbilityType.PhoenixGem (0x5b2) -- l'id `AbilityOrEffect`
                                       # passe en `sourceId` du `Revive` IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateBehaviour ET teste par le
                                       # `CurrentAbilityIs` du trigger de retrait IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal.
PHOENIX_GEM_HEAL_TYPE = 2              # 5e argument du `Revive` IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateBehaviour (`CONCAT44(0,2)`) : healType=2
                                       # -> `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType` ne filtre NI Heal NI Repair.
PHOENIX_GEM_PRIORITY = -1000           # 8e argument (`0xfffffc18`) : priorite la plus BASSE ->
                                       # `IdunBattle.Entities.Behaviours.ReviveBehaviour$$IsPreferredRevive` prefere TOUT autre revive.


class PhoenixGemReviveAbility(EffectTrigger):
    """`PhoenixGem_ReviveAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateTrigger / IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateBehaviour), collectee via
    l'effet-marqueur `PhoenixGem_CanReviveEffect` (1451, IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$.ctor) porte par l'unite -- d'ou le rail
    `EFFECT_TRIGGERS[1451]` (mirror de `IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal`, qui EST le
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
        # mirroir le meme gate que la base ReviveEffect (mort + non-PermaDeath + heal-type=2 litteral).
        return can_be_revived(entities, tgt, ev.dying_id, state, heal_type=PHOENIX_GEM_HEAL_TYPE)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        entities = entities_from_state(state, self.owner_id, ev.dying_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        level, mult = self._level(state)
        # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateBehaviour` = `Revive(self@0x148, self@0x148, Direct(GetVariableForLevel('hp')),
        # healType=2, Nullable(AbilityOrEffect(this.Id=1458)), 0, priority=-1000, 0)` -- AUCUN `Maybe`
        # (inconditionnel). Le behaviour se REDUIT a ce seul noeud : le retrait du marqueur est, cote
        # natif, un trigger SEPARE de `PhoenixGem_CanReviveEffect` (IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal), desormais porte a part
        # (`PhoenixGemRemoveMarkerOnRevive`) — plus de chainage en dur ici (case-89 volet B3).
        Revive(Caster(), ABILITY_ID, "hp", level, mult,
               heal_type=PHOENIX_GEM_HEAL_TYPE, source_id=PHOENIX_GEM_ABILITY,
               priority=PHOENIX_GEM_PRIORITY).execute(entities, ectx)
        revives = [p for n, p in ectx.emitted if n == "Revive" and p.get("revived")]
        return {"ability": ABILITY_ID, "owner": self.owner_id, "dying": ev.dying_id,
                "revives": revives}

    def _level(self, state: State):
        """`GetVariableForLevel(config@0x20, 0x1d='hp', abilityState)` : le niveau vient de
        l'`AbilityState` du RELIC porte, PAS du passif de l'unite.

        ⚠ CE NIVEAU NE SE LIT PAS SUR L'INSTANCE D'EFFET, et c'est MESURE (#1006,
        `probe_1006_reliques_aeldari.py` sur deux runners `--equip-relic "eldarAutarch:PhoenixGem:1"`
        puis `:10`) : l'instance 1451 captee publie `ability_level = 50` -- l'etat PASSIF du porteur
        sur tout runner normalise -- dans LES DEUX cas. Or `hp` a **10 paliers** (3915 au niveau 1,
        5817 au niveau 10, soit x1,49) : lire l'instance clampait TOUJOURS au dernier palier, un
        ecart SILENCIEUX de +49 % de PV rendus. C'est exactement le residu que #357 avait ferme pour
        `DawnBlade`, resté ouvert ici parce que la prose de l'epoque tenait la relique pour non
        montable.

        On passe donc par le foyer UNIQUE `triggered_ability_state` (#357), qui arbitre : couple
        TERTIAIRE (`TertiaryAbilityLevel`, `TertiaryAbilityVariablesMultiplierPercentage`) quand la
        relique est EQUIPEE, couple PASSIF quand `PhoenixGem` est cablee au kit d'un npc -- ou quand
        le canal tertiaire n'a pas ete fourni au chargement. Repli sur l'instance quand le foyer ne
        connait pas l'unite : c'est le comportement d'avant, jamais un zero fabrique."""
        lvl, mult = triggered_ability_state(state, int(self.owner_id), ABILITY_ID)
        if lvl is not None:
            return int(lvl), int(mult if mult is not None else 100)
        eff = getattr(state, "effects", None)
        if eff is not None:
            for e in (eff.by_unit.get(int(self.owner_id)) or []):
                if e.effect_type == PHOENIX_GEM_CAN_REVIVE:
                    lvl = e.active_ability_level if e.active_ability_level is not None else e.ability_level
                    return lvl, (e.ability_variables_multiplier or 100)
        return None, 100


class _PhoenixGemRemoveMarker(EffectTrigger):
    """Base des DEUX triggers de RETRAIT du marqueur 1451 (`PhoenixGem_CanReviveEffect.
    IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal`, entrees de l'`ArraySet`). Behaviour commun :
    `RemoveEffect(self@0x150)` -> la feuille `RemoveReviveEffect` (revive_effect.py). C'est CE retrait
    qui realise le « the FIRST TIME each battle » (et non un gate dans le trigger de revive)."""
    effect_type = PHOENIX_GEM_CAN_REVIVE
    fire_on_death = True        # au moment du dispatch, l'unite vient d'etre revive (alive=True), mais
                                # `On(0x2e = UnitResurrected)` peut arriver sur une unite encore marquee morte -> tolerant.

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        raise NotImplementedError

    def _owner_is_target(self, ev: TriggerEvent) -> bool:
        """`get_OwnerIsTarget` : le porteur du marqueur EST la cible de l'event (target@0x178)."""
        return ev.target_id == self.owner_id

    def execute_behaviour(self, state: State, ev: TriggerEvent):
        entities = entities_from_state(state, self.owner_id, self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        RemoveReviveEffect(Caster(), PHOENIX_GEM_CAN_REVIVE).execute(entities, ectx)
        return {"ability": ABILITY_ID, "owner": self.owner_id,
                "removed": PHOENIX_GEM_CAN_REVIVE, "on_event": int(ev.event_id)}


class PhoenixGemRemoveMarkerOnRevive(_PhoenixGemRemoveMarker):
    """1re entree de l'`ArraySet IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal` : `On(0x2d=UnitRevived) & OwnerIsTarget &
    CurrentAbilityIs(AbilityOrEffect(0x5b2=1458))` -> `RemoveEffect(1451)`. Le gate `CurrentAbilityIs`
    est essentiel : un revive de PhoenixGem consomme le marqueur, un revive venu d'AILLEURS (Narthecium
    d'un allie, ...) le LAISSE en place."""
    event_id = EventTriggerType.UnitRevived                    # 0x2d = 45

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if not self._owner_is_target(ev):
            return False
        return ev.ability_type is not None and int(ev.ability_type) == PHOENIX_GEM_ABILITY


class PhoenixGemRemoveMarkerOnResurrect(_PhoenixGemRemoveMarker):
    """2e entree de l'`ArraySet IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal` : `On(0x2e=UnitResurrected) & OwnerIsTarget` ->
    `RemoveEffect(1451)`. AUCUN `CurrentAbilityIs` ici (lu au decompile) : toute RESURRECTION
    (`ResurrectUnitOperation` IdunBattle.Operations.ResurrectUnitOperation$$Execute, ambush) consomme aussi le marqueur."""
    event_id = EventTriggerType.UnitResurrected                # 0x2e = 46

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return self._owner_is_target(ev)


# `PhoenixGem.hp` n'est PAS dans `variablesAffectedByRarityBonus` (gameconfig) -> pas de scaling rarete :
# `ability_var('PhoenixGem','hp', lvl)` suffit. Sanity-check i2 : au niveau du tooltip la valeur vaut 5817.
_ = ability_var
