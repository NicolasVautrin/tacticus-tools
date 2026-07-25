"""`IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect` (base `ReviveEffect`) -- effet « Inspired »
pose par l'active `RitesOfMorkai` de spaceWolfPriest (« Baldr », Space Wolves/Imperial) sur lui-meme et
ses allies non-mecaniques adjacents. #79 (retrofit case-66).

i2 authoritatif (ability `RitesOfMorkai`, vars {"range":"1","nrOfRounds":"1"}) : « Baldr and all
surrounding friendly non-mechanical units become <i>Inspired</i> for 1 round or until they are revived.
**The first time each inspired unit would be defeated, it is instead revived with a maximum of {hp}
Health, unless Overkilled.** Inspired units with Final Vengeance deal +{dmg} Damage with all attacks.
After using this ability, Baldr immediately performs a normal melee attack against an adjacent enemy. »

Ce module ne porte QUE le volet REVIVE (`RitesOfMorkaiEffect`, EffectType 1502). Les autres volets de
l'ability (pose de l'effet sur la zone, `RitesOfMorkai_ExtraDamageEffect` IdunBattle.Entities.Effects.Loki.RitesOfMorkai_ExtraDamageEffect$$.ctor = +dmg si Final
Vengeance, l'attaque melee de suivi de `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfMorkaiAbility$$ExecuteBehaviour`) NE SONT PAS
portes -- cf. le residu documente dans docs/rl/case-66-revive-in-place.md.

Artefact natif (RE ghidra gqfc5mff6c, VA citees) :

  RitesOfMorkaiEffect..IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect$$.ctor  `ReviveEffect..ctor(turnsEnabled=2,
                                                  activationFrequency=0,
                                                  source=AbilityOrEffect(0x4bb=1211
                                                  ActiveAbilityType.RitesOfMorkai),
                                                  removeEffect=TRUE)`
                                                  -> removeEffect(0x488)=1 : le 2e volet du behaviour est
                                                  `GetRemoveEffectBehaviour` et NON `DeactivateEffect`
                                                  => revive **one-shot definitif** (« the FIRST TIME »),
                                                  pas un once-per-turn. C'est LE discriminant vs
                                                  Narthecium/TaintedNarthecium (qui passent 0).
  RitesOfMorkaiEffect.CreateTargetFilter (0x758) IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect$$CreateTargetFilter  `get_OwnerIsTarget`
                                                  -> le porteur de l'effet EST la cible du trigger :
                                                  chaque unite inspiree se revive ELLE-MEME (aucun
                                                  AreFriends / IsAdjacent : la portee a deja ete
                                                  appliquee a la POSE de l'effet).
  base IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger / IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour
  VTABLE — LUE dans la table `methodPointers` d'IL2CPP du PE (la classe n'est jamais initialisee ->
  `resolveVtableSlot` LIVE rend des slots nuls ; case-89 volet B1/B2). Bloc @file 0x3100878 :

      0x3100878  GameCamera$$ShouldBlurBackground   get_ReviveOnOverkill = `return 0` (bool)  -> **« unless Overkilled »**
      0x3100880  IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect$$.ctor   .ctor
      0x3100888  IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect$$CreateTargetFilter   CreateTargetFilter
      0x3100890  meta_interstitial_popup_test.u003Cu003Ec$$u003CStartu003Eb__2_1+0x70   GetReviveChance      = `mov eax,100 ; ret` -> **chance = 100**
      0x3100898  IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$GetReviveHP   GetReviveHP          (corps partage ICF avec Narthecium)

  PAS d'entree `get_HealType` (corps 8 octets) dans le bloc -> la classe l'HERITE de la base = 0 (Heal),
  contrairement a ReanimationBeam qui l'override a 1. L'i2 confirme mot pour mot le gate overkill.

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
    """`RitesOfMorkaiEffect` (IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect$$.ctor / filter IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect$$CreateTargetFilter) -- self-revive one-shot de l'unite
    INSPIREE. Rail EFFET (l'effet est pose par l'active de Baldr) ; tout le reste (trigger OnPreDeath,
    CanBeRevived, behaviour Maybe/Revive) vient de la base `ReviveEffect`."""
    effect_type = RITES_OF_MORKAI_EFFECT
    ability_id = ABILITY_ID
    revive_on_overkill = False             # methodPointers @0x3100878 = GameCamera$$ShouldBlurBackground (`return 0`) : LU
    heal_type = 0                          # pas d'override de `get_HealType` dans son bloc -> base = 0
    remove_effect = True                   # ctor 0x488=1 -> RemoveEffect : one-shot DEFINITIF
    # `OwnerIsTarget` : le PORTEUR de l'effet est le MOURANT -> au moment ou le port emet PreUnitDeath
    # l'owner est deja `alive=False`. Sans ce flag, le gate `CanGetEffectTrigger` (owner vivant) du
    # dispatch l'ecarterait (meme besoin que FinalJustice/Ambush).
    fire_on_death = True
    # `GetReviveChance` : la config gameconfig de `RitesOfMorkai` n'a PAS de constante 'chance'
    # (constants = {range, nrOfRounds}) -- or `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant -> GetStringConstant
    # IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant` JETTE sur cle absente, et `GetReviveChance` est ABSTRAIT dans la base -> la sous-classe
    # DOIT overrider par un corps litteral. Ce corps est LU dans `methodPointers` @0x3100890 =
    # **meta_interstitial_popup_test.u003Cu003Ec$$u003CStartu003Eb__2_1+0x70** = `b8 64 00 00 00 c3` = `mov eax,100 ; ret` -> **100** (case-89 volet B2 : ce n'est
    # plus une hypothese justifiee par l'i2, c'est une lecture du binaire).
    default_chance = 100

    def create_target_filter(self, state: State, ev: TriggerEvent, entities) -> bool:
        """`IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect$$CreateTargetFilter` = `get_OwnerIsTarget` : le porteur de l'effet est la cible."""
        return ev.dying_id == self.owner_id
