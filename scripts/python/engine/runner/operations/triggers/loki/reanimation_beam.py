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

PORTEUR / VOIE — **RECTIFIE le 2026-07-29 par MESURE** (`probe_1547_carrier_live.py`, case-1547 §3).
Les deux affirmations que ce bloc portait depuis #79 sont FAUSSES :

  * « `necroReanimator` est ABSENTE du pool runner donc non confrontable » -> elle est absente de
    `rl_duel build --list-pool` par DEFAUT, mais `--list-pool` derive du seed BC (capture d'UNE
    bataille). `catalog_inject.py --units necroReanimator` l'ajoute aux DEUX catalogues
    (`Units` 175 -> 176, +2 configs d'ability) et `--list-pool --seed-bc <augmente>` la liste
    (8 -> 9 MoW). Elle SE DEPLOIE (`decisionView.mows`, PAS `.units`).
  * « les abilities castees par une MoW depuis hors-plateau sont BLOQUEES par le harnais headless »
    -> l'autre active du meme kit, `NanoscarabRepairProtocols` (1224), CASTE et MUTE reellement
    (allie 9537 -> 12196 PV, effets 1545/1546 poses et relus).

POSE NATIVE DE 1547 -- **OBTENUE le 2026-07-29** (`probe_mow_ammo_gauge.py`,
`docs/rl/case-mow-ammo-gauge.md`). L'attribution precedente (« `1223` a `hasAmmo = false`, la jauge
de munitions d'une MoW ne monte pas dans un runner -> le cast est ACCEPTE mais NO-OPE ») est
**REFUTEE par mesure** : avec `MachineOfWarAmmo` pose dans la BC, donc `hasAmmo = true`, le cast
no-ope EXACTEMENT PAREIL. Le terme MUNITIONS gate la face DECISION
(`ActiveAbility$$get_CanCurrentlyBeUsed`, donc ce que l'IA/l'UI PROPOSENT), pas l'EXECUTION par
`applyAction` -- a munition ZERO le cast pose 1547 quand meme, `SpendAmmoOperation$$Execute`
echouant silencieusement.

Les deux vrais obstacles, cumulatifs :

  1. `initialCooldownTurns = 1` (gameconfig) -> au tour 1 le 3e terme de `get_CanCurrentlyBeUsed`
     est deja faux. Le champ `usable` de `decisionView` ne le montre PAS (c'est `CanStillBeUsed`
     @0x28, le PREMIER terme seul) ; `abilityReason` le montre.
  2. une MoW n'a qu'UNE action par tour, et le cast PREREQUIS de `1224 NanoscarabRepairProtocols`
     (exige par `...ReanimationBeamAbility$$GetDynamicInvalidTargetReason` : cible Mechanical
     PORTANT l'effet 0x609 = 1545) la consomme -> le beam qui suit dans le MEME tour no-ope.

Recette live qui pose 1547 : 2 `endturn` -> cast `1224` sur un allie Mechanical -> 2 `endturn`
-> cast `1223`. L'effet apparait alors sur la MACHINE (`decisionView.mows[].effects`, PAS
`units[]`), 1 entree aux DEUX canaux. Port MIRROR valide sur etat LIVE avec l'effet 1547 INJECTE
dans `state.effects` (`test_revive_retrofit_offline_live.py`) ; la pose native est desormais
disponible pour une confrontation de bout en bout.
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
    ALLIE Mechanical porteur de `NanoscarabRepairProtocols`. Rail EFFET, one-shot (`removeEffect`).

    GATE `IsActive` (case-1547) : l'arbre vient de
    `IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger`, donc du rail que
    `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` gate sur
    `EffectComponent.IsActive @+0x5c`. `matches` le lit sur l'instance 1547 du porteur, AVANT
    l'arbre. Ni `CreateTargetTrigger` ni `$$CreateTargetFilter` ne portent de noeud d'activite
    (le `HasEffect` du filtre vise l'effet 1545 de la CIBLE, avec `onlyActive = 0`) : sans ce
    gate le port n'avait AUCUNE lecture du flag."""
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

    def _instance_flag_is_set(self, state: State) -> bool:
        """Le `EffectComponent.IsActive @+0x5c` de l'instance 1547 portee par `owner_id` -- mirror du
        gate que `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets`
        applique AVANT d'evaluer le trigger de CIBLE. Le natif le lit DEUX fois sur le MEME effet
        source : une fois sur l'`EffectComponent` transmis par
        `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTrigger` (early-out quand la
        liste de cibles est vide), puis -- c'est LE gate -- dans la boucle PAR CIBLE, sur le
        composant RE-CHARGE depuis l'entite-effet : `ShouldTrigger` (slot 0x13 de la def) et
        `Execute` (slots 0x15/0x14) ne sont appeles que `if (*(char *)(<component> + 0x5c) != '\\0')`.
        Une desactivation survenue en cours de drain stoppe donc les cibles suivantes -- ce que rend
        la re-evaluation par-item du pump collapse (`triggers/dispatch/core.py`).

        Ce gate est celui du rail TARGETS SEUL : `...$$EvaluateEffectTriggerEffectAbilities`, l'autre
        rail, n'accede JAMAIS a `+0x5c` (case-229) -- l'y poser eteindrait les `ActivateEffect` qui
        RALLUMENT un effet eteint.

        Aucune instance trouvee -> True : degradation PERMISSIVE (on ne fabrique pas un refus), meme
        convention que `_ranged_auto_attack_flag_is_set` (1009). Inatteignable en production :
        `collect_effect_triggers` n'instancie ce trigger QUE depuis une instance 1547 non consommee."""
        eff = getattr(state, "effects", None)
        if eff is None:
            return True
        insts = [e for e in (eff.by_unit.get(int(self.owner_id)) or [])
                 if (not e.consumed) and e.effect_type == REANIMATION_BEAM_EFFECT]
        return (not insts) or any(e.active for e in insts)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`EvaluateEffectTriggerTargets` : `if (IsActive@+0x5c)` PUIS l'arbre
        `IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger` (`_ReviveEffectCore.matches`,
        le `ShouldTrigger` du slot 0x13). L'ordre est celui du natif -- le flag d'abord."""
        if not self._instance_flag_is_set(state):
            return False
        return super().matches(state, ev)

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
