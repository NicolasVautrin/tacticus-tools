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

PORTEUR / VOIE DE VALIDATION : `spaceWolfPriest` est absent du seed BC capture, ce qui avait ete
lu comme « hors pool donc non confrontable ». **C'est FAUX** : `catalog_inject.
write_augmented_seed_bc` l'injecte dans les DEUX catalogues (`Units` + `Abilities`, mirror d'
`Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration`) et il entre au pool
(97 -> 98). Mesure du 2026-07-29 : Baldr deploye, `RitesOfMorkai` (1211) caste, **3 instances 1502
posees par la cascade native**, publiees par `readEffectsByUnit` (canal par defaut ET
`includeInactive`) et materialisees par `load_state`. Le revive natif d'une unite inspiree tuee
sans overkill rend `Min(GetReviveHP, StatAmount(Health,max))`, valeur sur laquelle le port est
en AGREMENT. cf. `docs/rl/case-229-1502-rites-of-morkai-live-confrontation.md`.

GATE `EffectComponent.IsActive @+0x5c` (#229 -> tache 1502, 2026-07-29) -- cf. `matches` ci-dessous.
C'est un **cliquet de FIDELITE**, et c'est desormais MESURE, plus suppose : aucun vecteur de jeu ne
peut rendre une instance 1502 inerte. `RitesOfMorkaiEffect` passe `activationFrequency = 0`, mais
son `CreateActiveCondition` (slot vtable `+0x518`, LU LIVE) est le trigger CONSTANT vrai que
`IdunBattleLogic.Entities.DSLFactory$$.ctor` construit a `+0xf8` -> `IdunBattle.Operations.
RefreshEffectsOperation$$ShouldBeActive` rend toujours vrai, donc `RefreshEffect` ne peut que
REACTIVER (`+0x5c = 1`), jamais appeler `...$$DeactivateEffect`. Et l'autre ecrivain de `+0x5c = 0`,
`IdunBattle.Operations.RemoveEffectOperation$$Execute`, pose `+0x5f = 1` (Removed) dans la MEME
operation, quelques instructions plus loin -- or le canal filtre `removed` inconditionnellement. Il
n'existe donc aucun etat publiable ou l'instance soit `IsActive == 0`. Le gate reste juste (mirror
1:1 de la lecture par-cible du natif) mais ne corrige aucun nombre observable EN JEU : il ne mord
que sur ce que le canal de SEED peut fabriquer.
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

    def _instance_is_active(self, state: State) -> bool:
        """Le flag `EffectComponent.IsActive @+0x5c` de MON instance 1502 -- mirror du gate que
        `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` applique AVANT
        d'evaluer le trigger de cible. Meme forme que `_ranged_auto_attack_flag_is_set` (1009).

        Aucune instance trouvee -> True : degradation PERMISSIVE (on ne fabrique pas un refus). Le cas
        ne se presente que si l'etat n'a pas d'`EffectsState` ; si l'effet etait reellement absent,
        `collect_effect_triggers` n'aurait instancie aucun trigger. Le filtre `not e.consumed` est
        celui du collecteur (le natif retire l'entite-effet, le port la marque)."""
        eff = getattr(state, "effects", None)
        if eff is None:
            return True
        insts = [e for e in eff.by_unit.get(int(self.owner_id), [])
                 if (not e.consumed) and e.effect_type == self.effect_type]
        return (not insts) or any(e.active for e in insts)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """Gate `IsActive` de l'INSTANCE, puis le trigger de la base (`ReviveEffect$$CreateTargetTrigger`).

        `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTrigger` route le MEME effet vers
        DEUX evaluateurs, et un seul porte un gate (inventaire #229) :

          * `...$$EvaluateEffectTriggerTargets` (rail TARGETS, issu de `<Effect>$$CreateTargetTrigger`)
            lit `EffectComponent.IsActive @+0x5c` **deux fois**, et c'est le rail de CE trigger :
              (1) a l'entree, sur le composant recu -- `if (IsActive) { if (Targets.Count == 0) return; }`
                  = fast-path (« actif mais sans cible : rien a faire ») ;
              (2) DANS la boucle PAR CIBLE, sur l'`EffectComponent` RECHARGE depuis l'entite-effet
                  (`GetComponent(effectEntity)` puis `if (*(char *)(comp + 0x5c) != '\\0')`), AVANT
                  `ShouldTrigger` (slot 0x13) puis le behaviour (slot 0x14). C'est LE gate : une
                  desactivation survenue en cours de drain stoppe les cibles suivantes.
            Les DEUX lectures portent sur l'effet SOURCE -- l'instance qui PORTE le trigger --, jamais
            sur la cible : `EvaluateEffectTrigger` passe l'entite-effet et son composant, et la boucle
            re-fetch le composant de CETTE MEME entite.
          * `...$$EvaluateEffectTriggerEffectAbilities` (rail ArraySet) n'accede JAMAIS a `+0x5c` --
            c'est lui qui porte les `ActivateEffect` capables de RALLUMER un effet eteint. Ne rien y
            gater : 1502 n'a de toute facon aucun `CreateHandleTriggerAbilitiesInternal`.

        Le port relit le flag DANS `matches`, donc a chaque item du drain de `evaluate_trigger_operation`
        = exactement la re-lecture par-cible du natif.

        ATTEIGNABILITE (pas une precaution theorique) : `IdunBattle.Operations.RefreshEffectsOperation$$
        RefreshEffect` eteint N'IMPORTE QUEL effet (`!ShouldBeActive` -> `...$$DeactivateEffect` ->
        `+0x5c = 0`), et le canal de seed `decisionView { includeInactive: true }` publie `active: false`,
        que `EffectFactory.create` recopie sur l'instance (#219). Une instance 1502 INERTE est donc
        seedable ; sans ce gate elle revivait son porteur."""
        if not self._instance_is_active(state):
            return False
        return super().matches(state, ev)
