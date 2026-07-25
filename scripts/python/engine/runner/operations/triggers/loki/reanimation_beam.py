"""`IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect` (base `ReviveEffect`) -- effet pose
par l'active `ReanimationBeam` (1223) de `necroReanimator` (Machine of War Necron). #79.

Artefact natif (RE ghidra gqfc5mff6c, VA citees) :

  ReanimationBeam_ReviveEffect..IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$.ctor  `ReviveEffect..ctor(turnsEnabled=2,
                                                  activationFrequency=0,
                                                  source=AbilityOrEffect(0x4c7=1223
                                                  ActiveAbilityType.ReanimationBeam),
                                                  removeEffect=TRUE)`
                                                  -> 0x488=1 : 2e volet = `RemoveEffect` (one-shot
                                                  DEFINITIF), comme RitesOfMorkai.
  ReanimationBeam_ReviveEffect.CreateTargetFilter (0x758) IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$CreateTargetFilter
                                                  `AreFriends(self@0x148, target@0x178)
                                                   & HasTrait(target, 5=Mechanical)
                                                   & HasEffect(target, 0x609=1545
                                                     EffectType.NanoscarabRepairProtocols, 0, 6)`
                                                  (PAS de `baseFilter(0x98)`, PAS d'IsAdjacent : le noeud
                                                   d'accroche est l'effet 1545 pose par l'autre active du
                                                   Reanimator.)
  base IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger / IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour

  VTABLE — RESIDU #89/B1 **FERME PAR LECTURE** (2026-07-25). La vtable de la classe reste illisible LIVE
  (classe jamais initialisee : `resolveVtableSlot` rend des slots NULS, carrier hors pool) -> lecture par
  l'AUTRE chemin : la table `methodPointers` d'IL2CPP, presente TELLE QUELLE dans `GameAssembly.dll`
  (VA image-base 0x180000000). Bloc de la classe @file 0x3100698 :

      0x3100698  GameCamera$$ShouldBlurBackground   get_ReviveOnOverkill  = `return 0` (corps 1 octet, bool)  -> **overkill BLOQUE**
      0x31006a0  GameCamera$$get_ScreenStatus   get_HealType          = `return 1` (corps 8 octets, int)  -> **healType = 1**
      0x31006a8  IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$.ctor   .ctor
      0x31006b0  IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$CreateTargetFilter   CreateTargetFilter
      0x31006b8  meta_interstitial_popup_test.u003Cu003Ec$$u003CStartu003Eb__2_1+0x70   GetReviveChance       = `mov eax,100 ; ret`               -> **chance = 100**
      0x31006c0  IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$GetReviveHP   GetReviveHP           (corps partage ICF avec Narthecium)

  (Ordre valide sur la BASE @0x30fdb28 et croise LIVE sur Narthecium @0x30fffc0 / TaintedNarthecium
  @0x3100e28, dont les `get_ReviveOnOverkill` lus ici — `return 0` / `return 1` — coincident exactement
  avec les slots 0x738 lus par `resolveVtableSlot`.)

  ⚠ `get_HealType = 1` (**Repair**) est la CLE du port : `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType` avec healType=1
  exige une cible MECHANICAL. Avec l'ancien healType=0 code en dur, `CanBeRevived` REJETAIT precisement
  les cibles que `CreateTargetFilter` exige (`HasTrait(Mechanical)`) -> le revive etait un **NO-OP
  GARANTI** hors trait `AffectedByHealAndRepair`. Corrige.

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
    """`ReanimationBeam_ReviveEffect` (IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$.ctor / filter IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$CreateTargetFilter) -- le Reanimator revive un
    ALLIE Mechanical porteur de `NanoscarabRepairProtocols`. Rail EFFET, one-shot (`removeEffect`)."""
    effect_type = REANIMATION_BEAM_EFFECT
    ability_id = ABILITY_ID
    revive_on_overkill = False             # methodPointers @0x3100698 = GameCamera$$ShouldBlurBackground (`return 0`) : LU
    heal_type = 1                          # methodPointers @0x31006a0 = GameCamera$$get_ScreenStatus (`return 1`) = Repair :
                                           # `IsAffectedByHealType(1)` exige une cible MECHANICAL (LU)
    remove_effect = True                   # ctor 0x488=1 -> RemoveEffect : one-shot DEFINITIF
    # `GetReviveChance` : le gameconfig `ReanimationBeam` n'a PAS de constante 'chance' (constants =
    # {initialCooldownTurns, munitionsCost}) et `IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant` JETTE sur cle absente ->
    # la classe DOIT overrider. methodPointers @0x31006b8 = **meta_interstitial_popup_test.u003Cu003Ec$$u003CStartu003Eb__2_1+0x70** = `b8 64 00 00 00 c3` =
    # `mov eax,100 ; ret` -> **100, LU** (ce n'est plus une hypothese ; case-89 volet B2).
    default_chance = 100

    def create_target_filter(self, state: State, ev: TriggerEvent, entities) -> bool:
        """`IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$CreateTargetFilter` = `AreFriends(self,target) & HasTrait(target, Mechanical=5)
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
