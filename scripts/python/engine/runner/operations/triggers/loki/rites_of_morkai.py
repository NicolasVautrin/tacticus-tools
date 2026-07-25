"""`IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect` (base `ReviveEffect`) -- effet « Inspired »
pose par l'active `RitesOfMorkai` de spaceWolfPriest (« Baldr », Space Wolves/Imperial) sur lui-meme et
ses allies non-mecaniques adjacents. #79 (retrofit case-66).

i2 authoritatif (ability `RitesOfMorkai`, vars {"range":"1","nrOfRounds":"1"}) : « Baldr and all
surrounding friendly non-mechanical units become <i>Inspired</i> for 1 round or until they are revived.
**The first time each inspired unit would be defeated, it is instead revived with a maximum of {hp}
Health, unless Overkilled.** Inspired units with Final Vengeance deal +{dmg} Damage with all attacks.
After using this ability, Baldr immediately performs a normal melee attack against an adjacent enemy. »

Ce module ne porte QUE le volet REVIVE (`RitesOfMorkaiEffect`, EffectType 1502). Les autres volets de
l'ability (pose de l'effet sur la zone, `RitesOfMorkai_ExtraDamageEffect` @180f69ee0 = +dmg si Final
Vengeance, l'attaque melee de suivi de `RitesOfMorkaiAbility.ExecuteBehaviour @181202ca0`) NE SONT PAS
portes -- cf. le residu documente dans docs/rl/case-66-revive-in-place.md.

Artefact natif (RE ghidra gqfc5mff6c, VA citees) :

  RitesOfMorkaiEffect..ctor          @180f69c30  `ReviveEffect..ctor(turnsEnabled=2,
                                                  activationFrequency=0,
                                                  source=AbilityOrEffect(0x4bb=1211
                                                  ActiveAbilityType.RitesOfMorkai),
                                                  removeEffect=TRUE)`
                                                  -> removeEffect(0x488)=1 : le 2e volet du behaviour est
                                                  `GetRemoveEffectBehaviour` et NON `DeactivateEffect`
                                                  => revive **one-shot definitif** (« the FIRST TIME »),
                                                  pas un once-per-turn. C'est LE discriminant vs
                                                  Narthecium/TaintedNarthecium (qui passent 0).
  RitesOfMorkaiEffect.CreateTargetFilter (0x758) @180f69c10  `get_OwnerIsTarget`
                                                  -> le porteur de l'effet EST la cible du trigger :
                                                  chaque unite inspiree se revive ELLE-MEME (aucun
                                                  AreFriends / IsAdjacent : la portee a deja ete
                                                  appliquee a la POSE de l'effet).
  base ReviveEffect.CreateTargetTrigger  @180f46d80 / CreateTargetTriggerBehaviour @180f46a70
  get_ReviveOnOverkill (0x738)       : PAS d'override (la classe n'expose que .ctor + CreateTargetFilter)
                                       -> herite la BASE = @1802b15a0 `return 0` (lu LIVE sur la vtable de
                                       `ReviveEffect`, `probe_79_revive_vtable.py`) => « unless Overkilled »,
                                       ce que l'i2 confirme mot pour mot.

PORTEUR / VOIE DE VALIDATION : `spaceWolfPriest` est un HERO mais **absent du pool runner**
(`rl_duel.py build --list-pool`, rank 17) -> l'effet 1502 n'est PAS posable en runner. Port MIRROR +
validation OFFLINE (l'effet est injecte dans `state.effects` par le test).
"""
from __future__ import annotations

from ....state import State
from ..base import TriggerEvent
from ..revive_effect import ReviveEffectTrigger

ABILITY_ID = "RitesOfMorkai"
RITES_OF_MORKAI_EFFECT = 1502          # EffectType.RitesOfMorkai (i2/enum : l'effet « Inspired »)


class RitesOfMorkaiReviveTrigger(ReviveEffectTrigger):
    """`RitesOfMorkaiEffect` (ctor @180f69c30 / filter @180f69c10) -- self-revive one-shot de l'unite
    INSPIREE. Rail EFFET (l'effet est pose par l'active de Baldr) ; tout le reste (trigger OnPreDeath,
    CanBeRevived, behaviour Maybe/Revive) vient de la base `ReviveEffect`."""
    effect_type = RITES_OF_MORKAI_EFFECT
    ability_id = ABILITY_ID
    revive_on_overkill = False             # herite la base @1802b15a0 = 0 -> « unless Overkilled »
    remove_effect = True                   # ctor 0x488=1 -> RemoveEffect : one-shot DEFINITIF
    # `OwnerIsTarget` : le PORTEUR de l'effet est le MOURANT -> au moment ou le port emet PreUnitDeath
    # l'owner est deja `alive=False`. Sans ce flag, le gate `CanGetEffectTrigger` (owner vivant) du
    # dispatch l'ecarterait (meme besoin que FinalJustice/Ambush).
    fire_on_death = True
    # `GetReviveChance` : la config gameconfig de `RitesOfMorkai` n'a PAS de constante 'chance'
    # (constants = {range, nrOfRounds}) -- or `GetNumberConstant @181576af0 -> GetStringConstant
    # @181576bb0` JETTE sur cle absente. La sous-classe override donc `GetReviveChance` par un corps
    # litteral (folde par ICF -> illisible offline, et sa vtable n'est pas lisible LIVE : classe non
    # initialisee car le carrier est hors pool). HYPOTHESE : 100 -- l'i2 n'annonce AUCUN pourcentage
    # (« it is **instead revived** », inconditionnel), contrairement a TaintedNarthecium (« has a
    # {chance}% chance »). A confirmer si spaceWolfPriest entre un jour dans le pool.
    default_chance = 100

    def create_target_filter(self, state: State, ev: TriggerEvent, entities) -> bool:
        """`CreateTargetFilter @180f69c10` = `get_OwnerIsTarget` : le porteur de l'effet est la cible."""
        return ev.dying_id == self.owner_id
