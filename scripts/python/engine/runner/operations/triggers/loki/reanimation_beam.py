"""`IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect` (base `ReviveEffect`) -- effet pose
par l'active `ReanimationBeam` (1223) de `necroReanimator` (Machine of War Necron). #79.

Artefact natif (RE ghidra gqfc5mff6c, VA citees) :

  ReanimationBeam_ReviveEffect..ctor @180f67b90  `ReviveEffect..ctor(turnsEnabled=2,
                                                  activationFrequency=0,
                                                  source=AbilityOrEffect(0x4c7=1223
                                                  ActiveAbilityType.ReanimationBeam),
                                                  removeEffect=TRUE)`
                                                  -> 0x488=1 : 2e volet = `RemoveEffect` (one-shot
                                                  DEFINITIF), comme RitesOfMorkai.
  ReanimationBeam_ReviveEffect.CreateTargetFilter (0x758) @180f67ac0
                                                  `AreFriends(self@0x148, target@0x178)
                                                   & HasTrait(target, 5=Mechanical)
                                                   & HasEffect(target, 0x609=1545
                                                     EffectType.NanoscarabRepairProtocols, 0, 6)`
                                                  (PAS de `baseFilter(0x98)`, PAS d'IsAdjacent : le noeud
                                                   d'accroche est l'effet 1545 pose par l'autre active du
                                                   Reanimator.)
  base ReviveEffect.CreateTargetTrigger @180f46d80 / CreateTargetTriggerBehaviour @180f46a70
  get_ReviveOnOverkill (0x738)       : PAS d'override visible -> herite la BASE = @1802b15a0 `return 0`
                                       => « unless Overkilled ». RESIDU : l'i2 de ReanimationBeam est MUET
                                       sur l'overkill (pas de phrase de tooltip dans le dump) et la vtable
                                       de la classe n'est pas lisible LIVE (classe non initialisee : son
                                       carrier n'est pas montable, cf. VOIE) -> le port herite la base,
                                       a confirmer si le carrier devient atteignable.

PORTEUR / VOIE : `necroReanimator` est une **Machine of War** ABSENTE du pool runner (les 8 MoW
spawnables au rank 17 sont adeptExorcist, astraOrdnanceBattery, blackForgefiend, deathCrawler,
orksRukkatrukk, tauBroadside, tyranBiovore, ultraDreadnought). De plus, les abilities castees par une MoW
depuis hors-plateau sont connues comme BLOQUEES par le harnais headless (meme famille que
`NanoscarabRepairProtocols`). Port MIRROR valide OFFLINE : l'effet 1547 est injecte dans `state.effects`.
"""
from __future__ import annotations

from ....state import State
from .....entities.traits.unit_trait import UnitTrait
from ..base import TriggerEvent
from ..revive_effect import ReviveEffectTrigger, are_friends

ABILITY_ID = "ReanimationBeam"
REANIMATION_BEAM_EFFECT = 1547           # EffectType.ReanimationBeam_Revive (l'effet porte par le beam)
NANOSCARAB_EFFECT = 1545                 # EffectType.NanoscarabRepairProtocols (le noeud HasEffect du filtre)
MECHANICAL = int(UnitTrait.Mechanical)   # 5 (HasTrait(target, 5))


class ReanimationBeamReviveTrigger(ReviveEffectTrigger):
    """`ReanimationBeam_ReviveEffect` (ctor @180f67b90 / filter @180f67ac0) -- le Reanimator revive un
    ALLIE Mechanical porteur de `NanoscarabRepairProtocols`. Rail EFFET, one-shot (`removeEffect`)."""
    effect_type = REANIMATION_BEAM_EFFECT
    ability_id = ABILITY_ID
    revive_on_overkill = False             # herite la base @1802b15a0 = 0 -> « unless Overkilled »
    remove_effect = True                   # ctor 0x488=1 -> RemoveEffect : one-shot DEFINITIF
    # Meme raisonnement que RitesOfMorkai : le gameconfig `ReanimationBeam` n'a pas de constante 'chance'
    # (constants = {initialCooldownTurns, munitionsCost}) et `GetStringConstant @181576bb0` JETTE sur cle
    # absente -> `GetReviveChance` est override par un corps litteral, folde/illisible. HYPOTHESE : 100
    # (aucun pourcentage annonce ; l'ability est un soin/repair deterministe).
    default_chance = 100

    def create_target_filter(self, state: State, ev: TriggerEvent, entities) -> bool:
        """`CreateTargetFilter @180f67ac0` = `AreFriends(self,target) & HasTrait(target, Mechanical=5)
        & HasEffect(target, NanoscarabRepairProtocols=1545)`."""
        dying = ev.dying_id
        # AreFriends(self@0x148, target@0x178)
        if not are_friends(state, self.owner_id, dying):
            return False
        ht = entities.has_trait
        # HasTrait(target, 5=Mechanical)  -- l'INVERSE de Narthecium, qui exclut les Mechanical
        if ht is None or not ht(entities.target, MECHANICAL):
            return False
        # HasEffect(target, 1545=NanoscarabRepairProtocols)
        eff = getattr(state, "effects", None)
        if eff is None:
            return False
        return any(e.effect_type == NANOSCARAB_EFFECT and not e.consumed
                   for e in (eff.by_unit.get(int(dying)) or []))
