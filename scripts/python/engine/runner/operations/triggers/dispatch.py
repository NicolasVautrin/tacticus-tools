"""Dispatch GÉNÉRIQUE de triggers — `IdunBattle.Operations.EvaluateTriggerOperation` : registre
`AbilityAndEffectCache` + vecteurs d'événement.

Chaîne native : `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` → (record message 8) →
`IdunBattle.Operations.EvaluateTriggerOperation$$Execute → `IdunBattle.Operations.EvaluateTriggerOperation$$ExecuteInternal → itère le registre
`AbilityAndEffectCache` → `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityOrEffectTrigger par entrée → (ability-trigger)
`IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger + `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger.

**Structure native** (portée 1:1 ici) :
- Le dispatch N'EST PAS scopé à l'attaquant : il itère un **registre GLOBAL** de tous les triggers de la
  bataille (abilities accordées par les traits + effets porteurs de trigger). Le scoping (qui réagit à
  CET événement) est dans la **condition du trigger** de chaque entrée (`matches`).
- Par entrée : gates owner = `IsUnit` & VIVANT (sauf ability fire-on-death) & `!IsTriggersDisabled` ; cap
  `GetTimesTriggeredThisPhase < 0x33` (51/phase).

EVENT-MAPPING RE (#147, verdict agent #150) : `On(NormalAttack=38)` et le vecteur after-hit
`IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` (dispatche `AttackHit=8` TOUJOURS + `UnitBlocked=61`
(0x3d) sur la branche `param_6`) sont des events NATIFS DISTINCTS. L'ancien port les conflatait sous une
constante 0x26 → le splash (`IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit`, events {6,8,0x3d}, JAMAIS
NormalAttack) re-satisfaisait Psyker `On(NormalAttack)` → chain 51×. Corrigé (#147) : Psyker écoute
`NormalAttack` ; le reset ActOfFaith écoute `Attack=9` (attaque d'ability, #151). Les membres consommés
+ leurs VAs/sémantique sont annotés dans `dsl/event_trigger_type.py`.

Les classes concrètes vivent dans `loki.py` (`Abilities.{Active,Triggered,Damage}.Loki.*`), `tiles.py`
(`Abilities.Tiles.*`) et `effect_triggers.py` (`Entities.Effects.*`) ; le framework dans `base.py`.
"""
from __future__ import annotations

from typing import Optional

from ...state import State
from ...components import (StatsComponent, OwnerComponent, UnitComponent, HealthComponent,
                          TriggeredAbilityComponent)
from ....dsl.event_trigger_type import EventTriggerType
from .base import (TriggerEvent, TriggeredAbility, EffectTrigger, TileEffectTrigger,
                   PHASE_TRIGGER_CAP, _is_ranged_position)
from .loki import (PsykerExtraAttackAbility, ActOfFaithAccumulateAbility, ActOfFaithResetAbility,
                   FinalJusticeAbility, TheBetrayerAddEffectAbility, TheBetrayerTakeTurnAbility,
                   ArcaneShieldAbility, ControlEdictAbility, RadSaturationAbility,
                   LordOfTempestsAddIceAbility, FireTileDoT, FIRE_TILE,
                   _on_fire_damage_ability, _fire_of_absolution_after_attack)
from .tiles import dry_bush_fire_spread
from .effect_triggers import (OverwatchAutoAttack, ContaminatedTileEffect,
                              OVERWATCH_AUTO_ATTACK, CONTAMINATED_TILE)
from .genestealer import (DecoysAndMisdirectionDamageEnemiesAbility,
                          DecoysAndMisdirectionBuffFriendsAbility,
                          AmbushSummonAbility, EnvAmbushResurrectAbility,
                          HypersensoryMoveAndSpawnDecoyAbility)
from .loki.weaver_of_fate import WeaverOfFateAbility                 # #202-A (trait WeaverOfFate)
from .loki.living_metal import LivingMetalRepairAbility             # #203 (trait LivingMetal, Necron)
from .loki.destroyer_hive import DestroyerHiveAbility               # case-220 DG (passiveAbility deathTyphus)
from .loki.martial_apotheosis import MartialApotheosisAttackAbility  # case-220 (passif necroOverlord, Necron)
from .loki.master_of_the_tutelaries import (MasterOfTheTutelariesSummonAbility,   # #202-C (triggered 1173)
                                            MASTER_EFFECT as MASTEROFTUTELARIES_EFFECT)
from .loki.tainted_narthecium import TaintedNartheciumReviveAbility  # case-66 (passif deathRotbone, revive)
from .loki.narthecium import NartheciumReviveAbility                 # #79 (passif ultraApothecary, revive)
from .loki.rites_of_morkai import (RitesOfMorkaiReviveTrigger,       # #79 (effet 1502 pose par Baldr)
                                   RITES_OF_MORKAI_EFFECT)
from .loki.reanimation_beam import (ReanimationBeamReviveTrigger,    # #79 (effet 1547, MoW necroReanimator)
                                    REANIMATION_BEAM_EFFECT)
from .loki.phoenix_gem import (PhoenixGemReviveAbility,              # #79 (relic, marqueur 1451)
                               PhoenixGemRemoveMarkerOnRevive,       # #89-B3 (On(0x2e) -> RemoveEffect)
                               PhoenixGemRemoveMarkerOnResurrect,    # #89-B3 (On(0x2f) -> RemoveEffect)
                               PHOENIX_GEM_CAN_REVIVE)
from .loki.suppressive_fire import SuppressiveFireAddEffectAbility  # #74 (trait SuppressiveFire 1010)
from .loki.death_nova import ExplodesAbility, PutridExplosionAbility  # death-nova (traits 1008 / 2028)
from .loki.master_annihilator import MasterAnnihilatorMarkAbility   # lot POSE (passif admecDominus)
from .loki.fleshmetal_guns import FleshmetalGunsRotationAbility     # lot POSE (passif blackObliterator)
from .loki.terrifying_crescendo import (TerrifyingCrescendoOverkillAbility,   # lot POSE (passif
                                        TerrifyingCrescendoSuppressAbility)   # emperNoiseMarine, #204)
from .loki.anvil_shield import (AnvilShieldApplyIceAbility,          # lot POSE (passif spaceRockfist)
                                AnvilShieldApplyStunAbility,          # #100 volet Stun on-block
                                AnvilShieldFrozenAttackerAdvantageAbility,   # #100 volet +block glace
                                AnvilShieldFrozenAdvantageExpire,     # #100 conso On(UnitPostAbility)
                                FROZEN_ADVANTAGE as ANVIL_FROZEN_ADVANTAGE)
from .loki.let_the_galaxy_burn import (LetTheGalaxyBurnArmAbility,   # #84 (trait LetTheGalaxyBurn 1058)
                                       LetTheGalaxyBurnResetAbility)
from .loki.sworn_protector import (SwornProtectorSummonKellAbility,  # #95-RESTE2 (passif astraCreed)
                                   SwornProtectorProtectSwitchAbility)
from .loki.listen_up_maggots import ListenUpMaggotsAddEffectAbility  # #95-RESTE2 (passif astraSmnKell)
from .loki.thrill_seekers import (ThrillSeekersFullHealthTargetAbility,   # trait ThrillSeekers 1056
                                  ThrillSeekersDamageTakenAbility)        # (x5 Emperor's Children)
from .loki.hailstrike import HailstrikeAttackAbility                 # case-117 ph.2 (1214 -> 1507)

# --- FinalJustice / overkill ----------------------------------------------------------------------
OVERKILL_PCT_KEY = "overkillDmgPctOfHealth"  # globalValues = 100 → overkill ssi dmg-PV >= 100%*PV (dmg>=2*PV)


# --- Registre : trait → ability-trigger(s) accordée(s) --------------------------------------------
TRAIT_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    "Psyker": [PsykerExtraAttackAbility],
    # ActOfFaith accorde DEUX ability-triggers (accumulation sur mort/kill + reset au crit).
    "ActOfFaith": [ActOfFaithAccumulateAbility, ActOfFaithResetAbility],
    # FinalJustice (worldKharn) = attaque normale à la mort (fire-on-death, gate overkill).
    "FinalJustice": [FinalJusticeAbility],
    # Ambush (Isaak/Judh/Neophyte, G3) = mort -> decoy (On UnitDefeated=55) + resurrection sur decoy allie
    # au debut du tour suivant (On TurnStart=22). Les DEUX sont fire-on-death (owner mort au moment du fire).
    "Ambush": [AmbushSummonAbility, EnvAmbushResurrectAbility],
    # WeaverOfFate (trait Abraxas thousInfernalMaster, #202-A) = `On(9=Attack)` : >=3 ennemis ayant recu
    # du degat PSYCHIC ce tour -> pose l'effet-marqueur 1185 WeaverOfFate_MaxOutDamage sur soi (1 tour,
    # degats max sans tirage). Cf. loki/weaver_of_fate.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$CreateBehaviour).
    "WeaverOfFate": [WeaverOfFateAbility],
    # LivingMetal (trait 1000, TOUT le roster Necron : 41 npc + 6 lineup + 4 summons, #203) = regen % PV
    # au debut du tour du proprietaire : `On(TurnStart_Other=19) & OwnerIsActor & IsDamaged(self)` ->
    # Repair(self, round(10% maxHP)). Cf. loki/living_metal.py (IdunBattleLogic.Entities.Abilities.Active.Loki.LivingMetalRepairAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Active.Loki.LivingMetalRepairAbility$$CreateBehaviour).
    "LivingMetal": [LivingMetalRepairAbility],
    # SuppressiveFire (trait 1010, x49 unites dont 8 lineup, #74) = pose Pinned/« Suppressed » (1065) sur
    # la cible d'une attaque RANGED du porteur : `On(PreAttack=5) & IsRangedAttack & OwnerIsActor &
    # AreEnemies & AmountIsGreaterThanZero(Units(target))` -> `AddEffect(Pinned, Target())`. Route sur
    # `On(NormalAttack=38)` (cf. loki/suppressive_fire.py IdunBattleLogic.Entities.Abilities.Active.Loki.SuppressiveFireAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Active.Loki.SuppressiveFireAbility$$CreateBehaviour).
    "SuppressiveFire": [SuppressiveFireAddEffectAbility],
    # DEATH-NOVA (`loki/death_nova.py`) : les deux traits qui font exploser le porteur a sa MORT, sur
    # l'event `PreUnitDeath_2 = 2` (PAS 1 : `IdunBattleLogic.Entities.DSLFactory$$OnPreDeath2` -> `OnDeathEvent(2,...)`).
    # Explodes (1008 -> triggered 1021, IdunBattleLogic.Entities.Abilities.Active.Loki.ExplodesAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Active.Loki.ExplodesAbility$$CreateBehaviour) : maxPV x 25% en DirectDamage a TOUS les
    # adjacents (friendly-fire), fire MEME EN OVERKILL (`OnPreDeath2(1,1)` = aucun gate).
    "Explodes": [ExplodesAbility],
    # PutridExplosion (2028 -> triggered 1074, IdunBattleLogic.Entities.Abilities.Active.Loki.PutridExplosion_Ability$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Active.Loki.PutridExplosion_Ability$$CreateBehaviour) : maxPV x 25% en Toxic aux adjacents
    # SAUF faction DeathGuard ; `OnPreDeath2(1,0)` = pas de gate overkill, mais NOT HasTrait(Steppable).
    "PutridExplosion": [PutridExplosionAbility],
    # LetTheGalaxyBurn (trait 1058, x5 heros Black Legion, #84 volet 1) = arme/desarme le FLAG persistant
    # 1482 qui alimente le +1 coup de `LetTheGalaxyBurnEffect` (effet 1477) :
    #   - `LetTheGalaxyBurnAbility` IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateBehaviour : `On(PreAttack=5) & OwnerIsCaster &
    #     Maybe(33%) & !HasTileStatusEffect(Targets)` -> `SetPersistentData` ;
    #   - `LetTheGalaxyBurn_ResetAbility` IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour : `ClearPersistentData` en fin d'attaque (`On(9)`).
    # Cf. loki/let_the_galaxy_burn.py (2 branches du gate, ground truth live 34.2% / 100%).
    "LetTheGalaxyBurn": [LetTheGalaxyBurnArmAbility, LetTheGalaxyBurnResetAbility],
    # ThrillSeekers (trait 1056 -> triggered 1444 ; les 5 kits Emperor's Children, tous lineup/HERO) =
    # DISJONCTION `op_BitwiseOr` de deux `On()` -> DEUX classes (patron TerrifyingCrescendo/ActOfFaith) :
    #   `On(PreAttackHit=6) & IsFirstHitInSeries & OwnerIsCaster & Not(IsWounded(target))`
    #      = « le porteur commence une attaque sur un ennemi a PLEINE VIE »
    #   `On(DamageTaken=0xf) & OwnerIsTarget`   = « le porteur SUBIT du degat »
    # -> pose (ou REFRESH via `ChangeEffectTurns(Set)` si deja porte) l'effet *Thrilled* 1434 =
    # `AddStaticStatModifierEffect(Owner, 1434, CRIT_CHANCE, extraCritChance=15, TurnsFromRounds(1))`.
    # Cf. loki/thrill_seekers.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.ThrillSeekersAbility$$CreateTrigger /
    # IdunBattleLogic.Entities.Abilities.Triggered.Loki.ThrillSeekersAbility$$CreateBehaviour).
    "ThrillSeekers": [ThrillSeekersFullHealthTargetAbility, ThrillSeekersDamageTakenAbility],
}

# --- Registre : passiveAbility → ability-trigger(s) accordée(s) ------------------------------------
# Certains triggers viennent d'une PASSIVE ABILITY (≠ trait), ex. worldKharn.passiveAbilities=['TheBetrayer'].
ABILITY_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    # TheBetrayer = gain-rage-au-kill (mort) + auto-tour (début de tour). Cf. les 2 classes dans loki.py.
    "TheBetrayer": [TheBetrayerAddEffectAbility, TheBetrayerTakeTurnAbility],
    # ArcaneShield (Thaumachus) = bouclier après activation (modélisé after-move quand mover==owner).
    "ArcaneShield": [ArcaneShieldAbility],
    # DecoysAndMisdirection (Isaak genesPrimus, G2) = 2 abilities-triggers step-on-decoy : DamageEnemies
    # (ennemi qui marche sur un decoy allié -> Blast) + BuffFriends (allié -> +582 dmg fin-de-tour + decoy).
    "DecoysAndMisdirection": [DecoysAndMisdirectionDamageEnemiesAbility,
                              DecoysAndMisdirectionBuffFriendsAbility],
    # HypersensoryAbilities (passif Judh genesKelermorph, G6b) = MoveAndSpawnDecoy : `On(9=Attack)` sur la 1re
    # attaque du tour ennemi -> move + decoy sur la tuile quittee + contre-attaque 3x Projectile. G6a (HP-floor,
    # effet 1380) est un OWNER-EFFECT auto-pose (pas un ability-trigger) ; ici = le volet triggered.
    "HypersensoryAbilities": [HypersensoryMoveAndSpawnDecoyAbility],
    # ControlEdict (passif Tan Gi'da admecMarshall, S4b) = after-normal-attack `On(0x26)` Imperative-gate :
    # Protector -> summon Skitarii Vanguard adjacent a Tan (cap maxSummons[level]) ; Conqueror -> les Summons
    # Mechanical amis adjacents attaquent la cible de Tan a portee. Cf. loki/control_edict.py.
    "ControlEdict": [ControlEdictAbility],
    # RadSaturation (passif Skitarii Vanguard admecSmnVanguard, S4b GAP) = pose l'effet de TUILE Contaminated
    # (1244) sur SA PROPRE tuile apres qu'il bouge (`On(4)&OwnerIsActor`, vecteur after_move) ou en fin de tour
    # s'il n'a pas bouge (`On(0x17=TurnEnd)`, vecteur end_turn ci-dessous). Cf. loki/rad_saturation.py.
    "RadSaturation": [RadSaturationAbility],
    # LordOfTempests (passif Njal spaceStormcaller, #35) = AddIce : glace la tuile de CHAQUE ennemi touche
    # par une attaque normale de Njal (`On(38)` cible principale + `On(9)&kind==0x3f5` victime du smite
    # Psyker), `OwnerIsCaster`. Cf. loki/lord_of_tempests.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility$$CreateBehaviour).
    "LordOfTempests": [LordOfTempestsAddIceAbility],
    # DestroyerHive (passif deathTyphus, case-220 DG) = au debut du tour de Typhus, sa nuee attaque 1x un
    # ennemi adjacent aleatoire (`On(0x16) & OwnerIsActor & AmountIsGreaterThanZero(GetValidTargets)` ->
    # AttackWithAttackDamage(caster, PickRandomly(ennemis adjacents,1), MinMax[passive lvl], DirectDamage,
    # nrOfHits=1)). Cf. loki/destroyer_hive.py (IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$GetValidTargets/IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$CreateBehaviour).
    "DestroyerHive": [DestroyerHiveAbility],
    # MartialApotheosis (passif necroOverlord, case-220 Necrons) = `On(TurnStart_Actions=0x16) & OwnerIsActor
    # & AmountIsGreaterThanZero(GetValidTargets)` : au debut de son tour, attaque 1 ennemi adjacent damageable
    # ALEATOIRE (PickRandomly count=1) avec 2 coups Energy (pierce 30). Classe native ETEND DestroyerHive
    # (CreateTrigger/GetValidTargets herites). Cf. loki/martial_apotheosis.py (IdunBattleLogic.Entities.Abilities.Active.Loki.MartialApotheosisAbility$$CreateBehaviour/IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$GetValidTargets).
    "MartialApotheosis": [MartialApotheosisAttackAbility],
    # TaintedNarthecium (passif deathRotbone, Death Guard/Chaos, case-66) = base ReviveEffect : `OnPreDeath &
    # CanBeRevived & AreFriends & HasTrait(Chaos) & IsAdjacent(2)` -> Maybe(75%){ Revive-EN-PLACE a
    # min(reviveHP,maxPV), even-if-Overkilled ; DeactivateEffect once-per-turn }. Debloqueur du sous-systeme
    # REVIVE (base ReviveEffect + ReviveUnitOperation). Cf. loki/tainted_narthecium.py (IdunBattle.Entities.Effects.Loki.TaintedNarthecium_ReviveEffect$$.ctor/IdunBattle.Entities.Effects.Loki.TaintedNarthecium_ReviveEffect$$CreateTargetFilter/
    # IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger/IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour) + operations/revive.py (IdunBattle.Operations.ReviveUnitOperation$$Execute).
    "TaintedNarthecium": [TaintedNartheciumReviveAbility],
    # Narthecium (passif ultraApothecary, Ultramarines/Imperial, #79 retrofit case-66) = MEME base
    # ReviveEffect : `OnPreDeath(unless-Overkilled) & CanBeRevived & AreFriends & IsAdjacent(2)` ->
    # Maybe(100%){ Revive-EN-PLACE a min(reviveHP,maxPV) ; DeactivateEffect once-per-turn }. Le filtre
    # IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$CreateTargetFilter n'a PAS de HasTrait (contraste Chaos de TaintedNarthecium) et get_ReviveOnOverkill
    # GameCamera$$ShouldBlurBackground = 0 -> gate `NOT overkill`. Cf. loki/narthecium.py + triggers/revive_effect.py.
    "Narthecium": [NartheciumReviveAbility],
    # MasterAnnihilator (passif admecDominus << Vitruvius >>) = POSE du marqueur 1249 avec REMOVE-BY-SOURCE :
    # `On(0x26=NormalAttack) & OwnerIsCaster & AreEnemies` -> `RemoveEffect(OwnerOfEffect(EffectsFromUnitSource(
    # Self, 1249)), 1249) + AddEffect(1249, Target())`. L'effet (+1 coup recu non-Psychic) etait deja porte
    # (hits.py) mais JAMAIS pose. Cf. loki/master_annihilator.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateBehaviour).
    "MasterAnnihilator": [MasterAnnihilatorMarkAbility],
    # FleshmetalGuns (passif blackObliterator << Volk >>) = ROTATION turn-start des 3 effets d'arme :
    # `On(0x16=TurnStart_Actions) & IsTurnOf(Self)` -> `RemoveEffect x3 + If(Modulo(UnitTurnsStarted(Self),
    # 3, k), AddEffect(1067|1212|1221))`. Les 3 effets (+2 coups Melta/Flame/HeavyRound) etaient deja portes
    # (hits.py) mais SEUL celui du seed vivait. Cf. loki/fleshmetal_guns.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArchContaminatorAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour).
    "FleshmetalGuns": [FleshmetalGunsRotationAbility],
    # TerrifyingCrescendo (passif emperNoiseMarine << Shiron >>) = ACCUMULATION du stack de l'effet 1424
    # (deja porte #204, magnitude x level) : disjonction `On(0=UnitDeath) & OwnerIsActor & TargetIsOverkilled`
    # | `On(0x3e=PreEffectAdded) & OwnerIsActor & TriggeringEffectIs(1065=Pinned)` -> `AddEffectOrIncreaseLevel(
    # 1424, +1, max=buffMaxLevel=6)`. Cf. loki/terrifying_crescendo.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateBehaviour).
    "TerrifyingCrescendo": [TerrifyingCrescendoOverkillAbility, TerrifyingCrescendoSuppressAbility],
    # AnvilShield (passif spaceRockfist << Arjac >>) = volet ON-BLOCK `ApplyIce` : `On(UnitBlocked=0x3d) &
    # OwnerIsTarget & IsUnit(caster)` -> `AddEffect(Ice=0x11, source=Self, cible=CasterTile)` (la tuile de
    # l'attaquant BLOQUE gele). L'effet de tuile Ice etait deja porte ; c'est le DISPATCH `On(0x3d)` qui
    # manquait. Volets Stun / FrozenAttackerAdvantage / init-effects = residus documentes.
    # Cf. loki/anvil_shield.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateBehaviour ; emetteur IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers).
    # #100 : les DEUX autres volets on-block sont desormais portes (ils etaient du dead-code faute de
    # leurs prerequis) — `ApplyStun` (`On(0x3d) & IsMeleeAttack & (HasEffect(1200)|HasEffect(1201))` ->
    # Stunned sur l'attaquant) et `FrozenAttackerAdvantage` (`On(0x2b=PreUnitAbility) & IsNormalAttack &
    # IsUnitOnTileWithEffect(caster, Ice)` -> +20 % block chance transitoire).
    "AnvilShield": [AnvilShieldApplyIceAbility, AnvilShieldApplyStunAbility,
                    AnvilShieldFrozenAttackerAdvantageAbility],
    # --- #95-RESTE2 : chaine SwornProtector -> Kell -> ListenUpMaggots ---------------------------
    # SwornProtector (passif `astraCreed`, triggered 1050) = `On(PreUnitAbility=0x2b)` : a la PREMIERE
    # attaque ennemie visant Creed, Kell (`astraSmnKell`) apparait sur un hex libre adjacent et prend
    # sa place (TriggerAbility -> SwornProtector_Protect). Cf. loki/sworn_protector.py.
    "SwornProtector": [SwornProtectorSummonKellAbility],
    # SwornProtector_Protect (passif `astraSmnKell`, triggered 1075) = MEME event : a chaque attaque
    # suivante visant Creed, Kell re-echange sa position avec lui et encaisse.
    "SwornProtector_Protect": [SwornProtectorProtectSwitchAbility],
    # ListenUpMaggots (passif `astraSmnKell`, triggered 1063) = `On(AbilityInit=0x21)` : pose l'effet
    # 0x426 sur Kell, qui ecrit `+1 nrOfSummons` / `+3 range` sur son PARENT (Creed) via
    # `AddUnitActiveAbilityModification` -- SEULE source non nulle de `GetAbilityStatModification`.
    "ListenUpMaggots": [ListenUpMaggotsAddEffectAbility],
}

# --- Registre : ability ACTIVE → triggered-ability(s) DERIVEE(s) ----------------------------------
# Mirror de `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$GetDerived
# TriggeredAbilities` (dict statique `ActiveAbilityType -> List<TriggeredAbilityType>`, peuple par
# `...StaticBattleRules.ActiveAbility$$.cctor`) : posseder l'ability ACTIVE fait porter la (les)
# triggered-ability(s) derivee(s) DES L'INIT de l'unite, sans aucun cast prealable. C'est un TROISIEME
# chemin de registration, distinct des deux deja portes (`TRAIT_TRIGGERS` = par trait ;
# `ABILITY_TRIGGERS` = par passiveAbility) -- et le SEUL qui puisse porter une triggered-ability greffee
# sur une ability ACTIVE (cas des MoW, qui n'ont ni trait ni passif dedie).
# Cle = NOM gameconfig de l'ability active (`units.activeAbilities`), comme ABILITY_TRIGGERS l'est pour
# `units.passiveAbilities`. 39 entrees existent cote natif ; seules celles dont la triggered-ability est
# PORTEE sont inscrites ici (le reste = registered-but-unported, no-op fidele).
ACTIVE_ABILITY_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    # 0x4be (1214 Hailstrike, `darkaStormSpeeder` MoW) -> 0x5e3 (1507 Hailstrike_Attack) : quand un ALLIE
    # porteur du buff 1509 finit une attaque RANGED/OVERWATCH sur un ennemi VIVANT, la MoW attaque la
    # MEME cible (`nrOfHits` coups du profil de la config 1214, factory AttackWithAbilityDamage).
    # Le gate `HasEffect(attaquant, 1509)` du trigger rend l'entree INERTE tant qu'aucun Hailstrike
    # n'est pose -> l'inscription inconditionnelle est fidele. Cf. loki/hailstrike.py.
    "Hailstrike": [HailstrikeAttackAbility],
}

# --- Registre : effectType → effet-trigger(s) ------------------------------------------------------
# ⚠ La valeur est une LISTE : cote natif, `BaseEffect.CreateHandleTriggerAbilitiesInternal` renvoie un
# **`ArraySet`** (N `Triggered(trigger, behaviour)` par effet) — ex. `PhoenixGem_CanReviveEffect
# IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal` en enregistre DEUX. Un dict 1->1 ne pouvait pas les porter.
EFFECT_TRIGGERS: dict[int, list[type[EffectTrigger]]] = {
    OVERWATCH_AUTO_ATTACK: [OverwatchAutoAttack],
    CONTAMINATED_TILE: [ContaminatedTileEffect],  # tile-effect : enter(4)+tick(0x12) -> pose Contaminated_Unit
    FIRE_TILE: [FireTileDoT],                     # tile-effect : tick(0x14) -> DoT 20% PV initiale a l'occupant
    # MasterOfTheTutelaries (#202-C, effet 1197 pose par l'active 1096 d'Abraxas) : la collecte
    # par-effet-actif EST le Add/RemoveTriggeredAbility natif (IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$ApplyInternal /
    # IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$RevertInternal) -> Screamer sur attaque Psychic vs ennemi (On(9), triggered 1173).
    MASTEROFTUTELARIES_EFFECT: [MasterOfTheTutelariesSummonAbility],   # 1197 -> 1173
    # RitesOfMorkai (#79, effet « Inspired » 1502 pose par l'active 1211 de spaceWolfPriest) = MEME base
    # `ReviveEffect` que Narthecium, mais rail EFFET (pose par une ACTIVE, pas par un passif) : filtre
    # IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect$$CreateTargetFilter = `OwnerIsTarget` (self-revive) et IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect$$.ctor `removeEffect=TRUE` -> le 2e volet du
    # behaviour est `RemoveEffect` (one-shot DEFINITIF) et non `DeactivateEffect` (once-per-turn).
    RITES_OF_MORKAI_EFFECT: [RitesOfMorkaiReviveTrigger],            # 1502 (self-revive one-shot)
    # ReanimationBeam (#79, effet 1547 pose par l'active 1223 de la MoW necroReanimator) = base
    # ReviveEffect, filtre IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$CreateTargetFilter = AreFriends & HasTrait(Mechanical=5) & HasEffect(1545
    # NanoscarabRepairProtocols) ; IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$.ctor removeEffect=TRUE -> one-shot.
    REANIMATION_BEAM_EFFECT: [ReanimationBeamReviveTrigger],         # 1547 (allie Mechanical nanoscarabe)
    # PhoenixGem (#79, relic d'eldarAutarch) : PAS un ReviveEffect -- `PhoenixGem_ReviveAbility`
    # (IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateBehaviour) enregistree par l'effet-marqueur `PhoenixGem_CanReviveEffect` 1451
    # (IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal). Self-revive INCONDITIONNEL (pas de Maybe), **even if Overkilled**, one-shot par
    # bataille. Le `IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal` de l'effet enregistre en plus les
    # DEUX triggers de RETRAIT du marqueur (case-89 volet B3) : `On(0x2e=UnitRevived) & OwnerIsTarget &
    # CurrentAbilityIs(PhoenixGem=0x5b2)` et `On(0x2f=UnitResurrected) & OwnerIsTarget`.
    PHOENIX_GEM_CAN_REVIVE: [PhoenixGemReviveAbility,                # 1451 (self-revive, even-if-overkill)
                             PhoenixGemRemoveMarkerOnRevive,         # On(0x2e) -> RemoveEffect(1451)
                             PhoenixGemRemoveMarkerOnResurrect],     # On(0x2f) -> RemoveEffect(1451)
    # AnvilShield_FrozenAttackerAdvantage (#100, effet 0x4b1=1201 pose par le volet `On(0x2b)`) : son
    # SEUL trigger propre est `IdunBattle.Entities.Effects.Loki.AnvilShield_FrozenAttackerAdvantageEffect
    # $$CreateTargetTrigger` = `On(0xe=UnitPostAbility) & AreEqual(target@0x178, EffectSource(this))` ->
    # le bonus +20 % block ne vit QUE le temps de l'ability qui l'a declenche (ground truth live).
    ANVIL_FROZEN_ADVANTAGE: [AnvilShieldFrozenAdvantageExpire],      # 1201 -> conso a UnitPostAbility
}


def collect_triggered_abilities(state: State) -> list[TriggeredAbility]:
    """Mirror du registre `AbilityAndEffectCache` (volet ability-trigger) : itère TOUTES les entités et,
    pour chaque trait à trigger porté, instancie l'ability correspondante (owner = l'entité). (Le volet
    effet-trigger — Overwatch, on-hit — n'est pas encore collecté ici.)"""
    import gameconfig as GC
    from ..behaviour import BEHAVIOUR_TRAIT_TRIGGERS            # lazy : evite circular import behaviour<->triggers
    out: list[TriggeredAbility] = []
    for eid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is None:
            continue
        for trait in (sc.ctx.traits or []):
            for cls in TRAIT_TRIGGERS.get(trait, ()):            # un trait peut accorder >1 trigger
                out.append(cls(eid))
            for cls in BEHAVIOUR_TRAIT_TRIGGERS.get(trait, ()):  # mecaniques de comportement (Battle Fatigue)
                out.append(cls(eid))
        # passiveAbilities (TheBetrayer…) — résolues via gameconfig par visualId.
        vid = getattr(sc.ctx, "visual_id", None)
        if vid:
            gu = GC.unit(vid) or {}
            for pa in (gu.get("passiveAbilities") or []):
                for cls in ABILITY_TRIGGERS.get(pa, ()):
                    out.append(cls(eid))
            # activeAbilities -> triggered-abilities DERIVEES (`StaticBattleRules.ActiveAbility$$
            # GetDerivedTriggeredAbilities`) : porté dès l'init de l'unité, sans cast préalable.
            for aa in (gu.get("activeAbilities") or []):
                for cls in ACTIVE_ABILITY_TRIGGERS.get(aa, ()):
                    out.append(cls(eid))
    return out


def collect_effect_triggers(state: State) -> list[EffectTrigger]:
    """Mirror du registre `AbilityAndEffectCache` (volet effet-trigger) : itère les effets ACTIFS portés
    par chaque unité (via `state.effects`) et, pour chaque effet d'un type enregistré, instancie son
    effet-trigger (owner = le porteur). No-op si `state.effects` absent."""
    out: list[EffectTrigger] = []
    eff = getattr(state, "effects", None)
    if eff is None:
        return out
    for uid, effs in eff.by_unit.items():
        for e in effs:
            if e.consumed:
                continue
            for cls in EFFECT_TRIGGERS.get(e.effect_type, ()):   # ArraySet natif : N triggers par effet
                out.append(cls(int(uid)))
    return out


def evaluate_trigger_operation(state: State, ev: TriggerEvent) -> list[dict]:
    """Mirror COLLAPSÉ du PUMP FIFO natif (#201) — `IdunBattle.Operations.EvaluateTriggerOperation$$ExecuteInternal`
    (dispatch) + `IdunBattle.Messages.InputMessageProcessor$$ProcessPendingTriggeredAbilities` (drain) + `IdunBattle.Messages.InputMessageProcessor$$RunPhase(0xf)`
    (item) + `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` (retrait-des-morts entre items), fondus en UNE boucle.

    Structure native (RE) :
      1. `ExecuteInternal` : itère le registre GLOBAL `AbilityAndEffectCache` (composant #3 = triggers de
         CET event) → `EvaluateAbilityOrEffectTrigger` par entrée → **ENFILE** un pending triggered-ability
         (file #5) — il n'EXÉCUTE PAS inline.
      2. `ProcessPendingTriggeredAbilities` : **SNAPSHOT** la file #5 dans une List + **`Queue.Clear`**, puis
         `foreach` item → `RunPhase(0xf, item)`. Chaque `RunPhase` = callback (le behaviour de l'item) PUIS
         `VerifyDeaths` PUIS `ProcessDamageEvents` PUIS `ProcessPendingTriggeredAbilities` (cascade imbriquée).
         => les morts causées par l'item N sont RETIRÉES avant l'item N+1.

    Collapse du port (équivalent observable, sans machinerie de file) :
      - `registry` = liste MATÉRIALISÉE une fois = le SNAPSHOT (mirror du snapshot+Clear : les effets/traits
        ajoutés PENDANT le drain n'entrent pas dans CE registre).
      - la boucle draine le snapshot en ordre FIFO ; le **re-appel de `matches` par item** (contre l'état
        COURANT) = la re-validation de cible du `RunPhase(0xf)` (un item tué par un item antérieur ne matche
        plus — cf. la leg target-validity `OverwatchAutoAttack.matches`, alive du mover).
      - les morts sont appliquées **INLINE** par `_fire_death_if_killed` (alive=False + `after_death_triggers`
        LIFO) DANS `execute_behaviour` = le `VerifyDeaths`-entre-items (la victime est morte avant l'entrée
        suivante). Équivalent au pump pour la cascade prouvée #201 (overwatch kill-cancel) ; une vraie file
        pending explicite (ordre snapshot-clear multi-rounds) n'ajoute AUCUN effet observable ici → non portée
        (blast-radius/ordre RNG) tant qu'aucune divergence ne l'exige.

    Gates par entrée : `event_id` écouté → `CanGet*Trigger` (owner VIVANT sauf fire-on-death ;
    triggers-disabled non porté) → cap-phase (`<0x33`, ability-triggers) → `matches` → behaviour.
    Renvoie la liste des résultats (diagnostic)."""
    out: list[dict] = []
    registry = collect_triggered_abilities(state) + collect_effect_triggers(state)
    for entry in registry:
        # Un tile-effect écoute souvent PLUSIEURS events (`event_ids`) ; sinon `event_id` unique.
        if entry.event_id != ev.event_id and ev.event_id not in getattr(entry, "event_ids", ()):
            continue
        if getattr(entry, "owner_is_tile", False):
            pass                                           # owner = TUILE : pas de gate unit-entity/alive
        else:
            owner = state.get_entity(entry.owner_id)
            if owner is None:
                continue
            uc = owner.get_component(UnitComponent)        # CanGet*Trigger : owner unit vivant
            if uc is not None and not uc.alive and not getattr(entry, "fire_on_death", False):
                continue                                   # sauf ability fire-on-death (ex. FinalJustice)
        if not entry.matches(state, ev):
            continue
        # #140 : CAP phase-triggers (mirror IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger : GetTimesTriggeredThisPhase
        # < 0x33). S'applique aux ability-triggers (TriggeredAbility) — les effet-triggers passent par
        # EvaluateEffectTrigger (sans ce cap). Borne l'auto-récursion (splash Psyker qui re-déclenche le
        # splash Psyker via le vecteur after-hit). Clé = type d'ability-trigger (1 par trait-trigger).
        # `mark_as_triggered` AVANT le behaviour → la récursion voit le compteur incrémenté.
        if isinstance(entry, TriggeredAbility) and not getattr(entry, "owner_is_tile", False):
            tac = _trigger_phase_component(state, entry.owner_id)
            if tac is not None:
                pkey = type(entry).__name__
                tac.try_add(pkey)                                       # peuplement paresseux (idempotent)
                if tac.get_times_triggered_this_phase(pkey) >= PHASE_TRIGGER_CAP:
                    continue                                           # cap atteint cette phase → skip
                tac.mark_as_triggered(pkey)
        r = entry.execute_behaviour(state, ev)
        if r is not None:
            out.append(r)
    return out


def _trigger_phase_component(state: State, owner_id: int) -> Optional[TriggeredAbilityComponent]:
    """Get-or-create le `TriggeredAbilityComponent` de l'unité `owner_id` (mirror du composant natif ;
    absent d'une unité spawnée avant #140 → créé paresseusement). None si l'entité n'existe pas."""
    e = state.get_entity(owner_id)
    if e is None:
        return None
    c = e.get_component(TriggeredAbilityComponent)
    if c is None:
        c = TriggeredAbilityComponent()
        e.add_component(c)
    return c


def _squighound_after_attack(state: State, attacker_id: int, target_id: int) -> list[dict]:
    """`SquigHoundSummonUnitAbility` trigger `On(0x26) & OwnerIsCaster` IdunBattleLogic.Entities.Abilities.Triggered.Loki.SquigHoundSummonUnitAbility$$CreateTrigger : APRÈS une attaque du
    caster porteur du passif `SquigHound`, si **< maxSummons(5)** grots amis, spawn 1 grot adjacent à la CIBLE
    (behaviour IdunBattleLogic.Entities.Abilities.Triggered.Loki.SquigHoundSummonUnitAbility$$CreateBehaviour -> `SpawnUnitOperation.execute_squighound_summon`, `WithStatsFromConfig(SquigHound)`
    au niveau du caster -> le grot porte `active_ability_level` = **lève le GAP PileIn**). No-op si l'attaquant
    n'a pas SquigHound. Le `PerformAIAttack` on-appearance = FLAGGÉ non porté (secondaire)."""
    import gameconfig as GC
    from ..spawn import SpawnUnitOperation
    e = state.get_entity(attacker_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None or "SquigHound" not in ((GC.unit(uc.visual_id) or {}).get("passiveAbilities") or []):
        return []
    spawned = SpawnUnitOperation.execute_squighound_summon(state, attacker_id, target_id)
    return [{"squighound": attacker_id, "spawned": spawned}] if spawned else []


def unit_blocked_triggers(state: State, attacker_id: int, target_id: int,
                          ranged: bool, profile: Optional[str]) -> list[dict]:
    """Vecteur `On(UnitBlocked=0x3d=61)` — emis par `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`
    sur la branche `if (param_6 != 0)` (le flag BLOCK), **AVANT** le `On(8)` inconditionnel. L'
    `AbilityEntities` de ce vecteur est `ctor(caster = param_3 = l'ATTAQUANT, owner = actor = target =
    param_4 = le DEFENSEUR, casterTiles = GetTiles(attaquant), targetTiles = GetTiles(defenseur))` :
    d'ou `actor_id` = attaquant et `target_id` = defenseur (le BLOQUEUR) cote port -> le predicat
    `get_OwnerIsTarget` d'AnvilShield se lit `ev.target_id == owner_id`.

    Consommateur : `AnvilShieldApplyIceAbility` (glace la tuile de l'attaquant bloque, IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateTrigger/
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateBehaviour). AVANT ce vecteur, `did_block` etait resolu par le pipeline (damage_hits.py) mais
    l'evenement n'etait JAMAIS emis -> tout le cluster on-block etait inatteignable.

    ⚠ GRANULARITE : le natif emet `On(0x3d)` PAR COUP bloque ; le port l'emet UNE fois par ATTAQUE
    (meme agregation que `is_crit`, deja en place). Observationnellement EQUIVALENT pour le seul
    consommateur porte (la pose d'Ice est idempotente : `AddEffectOperation` no-op si la tuile est deja
    glacee). A raffiner si un consommateur per-coup apparait."""
    ev = TriggerEvent(EventTriggerType.UnitBlocked, attacker_id, target_id,
                      ranged=ranged, profile=profile)
    return evaluate_trigger_operation(state, ev)


def ability_init_triggers(state: State, unit_id: int) -> list[dict]:
    """Vecteur `On(AbilityInit=0x21=33)` — emis par
    `IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute` quand les abilities d'une unite
    s'INITIALISENT (creation d'unite : roster de depart ET summon pose en cours de bataille).

    C'est le trigger de base pre-cache `df@0xa8` (`IdunBattleLogic.Entities.DSLFactory$$InitializeShared` :
    `On(0x21) & df@0x128 & OwnerIsActor(owner@0x148, actor@0x158)`), consomme tel quel par toute la
    famille des owner-effects poses a l'init (`LifewardsAddEffectAbility$$CreateTrigger` = `return df@0xa8`)
    et, AVEC un gate supplementaire, par `IdunBattleLogic.Entities.Abilities.Active.Loki.ListenUpMaggotsAbility$$CreateTrigger`
    (`df@0xa8 & HasUnit(Parent(caster@0x160), 3)`).

    Le port materialise deja la BRANCHE INCONDITIONNELLE de cette famille par SEEDING au spawn
    (`spawn.py::_seed_*_owner_effects` = la table `factory.ABILITY_INIT_OWNER_EFFECTS`) ; ce vecteur
    couvre la branche GATEE, qu'un seed inconditionnel ne peut pas porter. `actor_id == target_id ==
    l'unite qui s'initialise` (owner == actor : c'est le sens de `get_OwnerIsActor` ici).

    SEUL consommateur porte : `ListenUpMaggotsAddEffectAbility` (#95-RESTE2). Aucun autre trigger du
    registre n'ecoute `event_id == 33` -> zero effet de bord, zero conso RNG pour les autres spawns."""
    ev = TriggerEvent(EventTriggerType.AbilityInit, unit_id, unit_id, ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)


def pre_unit_ability_triggers(state: State, caster_id: int, target_id: int,
                              ranged: bool, profile: Optional[str] = None,
                              ability_type: Optional[int] = None) -> list[dict]:
    """Vecteur `On(PreUnitAbility=0x2b=43)` — emis par
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` (`FUN_180026490(0x4d, .., 0x2b)`)
    **TOUT EN HAUT**, avant l'execution de l'ability (donc avant tout degat/block) ; la MEME operation
    emet ensuite, dans l'ordre, `0xb (UnitAbility)`, `0xc (UnitActiveAbility)` et `0xe (UnitPostAbility)`.
    L'`AbilityEntities` de l'evenement est celui de l'ability : caster = l'ACTEUR, target = la cible.

    L'attaque NORMALE emprunte cette operation (l'attaque normale EST une active ability, cf.
    `NormalAttackType` — memoire « normal attack = concrete ability id »).

    #120 — LES DEUX VOIES L'EMETTENT. Le natif n'a qu'UN site d'emission ; le port en a deux parce
    qu'il a deux portes d'operation (`DamageHandler.visit_AttackUnitMessage` pour l'attaque normale,
    `AbilityHandler.visit_ActiveAbilityMessage` pour un cast). Jusqu'a #120 seule la voie NORMALE
    emettait = FORK de port (1 site natif -> 2 sites offline dont 1 muet), et les consommateurs
    s'appuyaient sur un gate STRUCTUREL (« ce vecteur ne peut venir que d'une attaque normale »).
    Les deux voies emettent desormais, au meme rang relatif que le natif (apres les gates
    acteur-mort / cible-invalide, avant l'execution), et les gates des consommateurs sont PORTES
    (`abilities/attack_type.py` : `IsNormalAttack`, `AbilityHasAttackType`).

    `ability_type` = `df@0x130` (l'ability declenchante) : `0x3f5` (marqueur « kind attaque-normale »)
    sur la voie normale, l'`ActiveAbilityType` du cast sur la voie ability. C'est LE discriminant que
    lisent les deux gates ci-dessus — le renseigner n'est pas optionnel.

    Consommateurs portes :
      * `AnvilShieldFrozenAttackerAdvantageAbility` (#100) — gate `IsNormalAttack`, donc actif sur la
        seule voie normale : le bonus +20 % block d'Arjac doit etre POSE avant le calcul du block de
        CETTE attaque (c'est exactement pour ca que le natif emet l'evenement AVANT l'execution) ;
      * `SwornProtectorSummonKellAbility` / `SwornProtectorProtectSwitchAbility` (#95) — gate
        `AbilityHasAttackType(0|1)`, donc actifs sur les DEUX voies : c'est eux que le fork rendait
        muets face a une ability offensive.
    AUCUN autre trigger porte n'ecoute `event_id == 0x2b`."""
    ev = TriggerEvent(EventTriggerType.PreUnitAbility, caster_id, target_id,
                      ranged=ranged, profile=profile, ability_type=ability_type)
    return evaluate_trigger_operation(state, ev)


def unit_post_ability_triggers(state: State, caster_id: int, target_id: int,
                               ranged: bool, profile: Optional[str] = None,
                               ability_type: Optional[int] = None) -> list[dict]:
    """Vecteur `On(UnitPostAbility=0xe=14)` — DERNIER evenement emis par
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` (`FUN_180026490(0x4d, .., 0xe)`),
    apres `0x2b` puis `0xb`/`0xc`. Consommateur porte : le trigger PROPRE de l'effet 1201
    (`AnvilShieldFrozenAdvantageExpire`) qui consomme le +20 % block a la fin de l'ability.
    AUCUN autre trigger porte n'ecoute `event_id == 0xe`.

    #120 — PENDANT EXACT de `pre_unit_ability_triggers` : emis par les DEUX voies (fin de
    `after_hit_normal_attack` pour l'attaque normale, queue de
    `AbilityHandler.visit_ActiveAbilityMessage` pour un cast, apres `AddFlagsAfterAbilityExecution`
    comme le natif). Emettre `0x2b` sans son `0xe` sur la meme voie laisserait un effet
    « le temps de CETTE ability » pose pour toujours."""
    ev = TriggerEvent(EventTriggerType.UnitPostAbility, caster_id, target_id,
                      ranged=ranged, profile=profile, ability_type=ability_type)
    return evaluate_trigger_operation(state, ev)


def pre_attack_triggers(state: State, attacker_id: int, target_id: int,
                        ranged: bool, profile: Optional[str] = None,
                        ability_type: Optional[int] = None) -> list[dict]:
    """Vecteur `On(PreAttack=5)` — emis par le pipeline d'attaque natif **AVANT** le calcul du nombre de
    coups (`GetAttackHits`) et avant tout degat, UNE fois par attaque, sur la cible PRIMAIRE.

    Le port ne l'emettait PAS jusqu'a #84 : les consommateurs deja portes qui l'ecoutent nativement
    avaient ete ROUTES sur d'autres vecteurs (`SuppressiveFireAddEffectAbility` -> `On(38)`, cf. son
    en-tete) parce que leur observable ne depend pas du timing. `LetTheGalaxyBurnArmAbility` (#84), lui,
    **exige** ce timing : son behaviour arme un flag (`SetPersistentData`) que le canal de coups de la
    MEME attaque relit (`IsPersistentData` dans `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits) — le router apres coup serait un no-op silencieux.

    AUCUN autre trigger porte n'ecoute `event_id == 5` (verifie : le seul `PreAttack` du port etait une
    mention en commentaire) -> emettre ce vecteur ne reveille rien d'autre, et le seul cout RNG possible
    est le `Maybe(33%)` de LetTheGalaxyBurn, qui ne fire que pour ses 5 porteurs."""
    ev = TriggerEvent(EventTriggerType.PreAttack, attacker_id, target_id,
                      ranged=ranged, profile=profile, ability_type=ability_type)
    return evaluate_trigger_operation(state, ev)


def pre_attack_hit_triggers(state: State, attacker_id: int, target_id: int,
                            ranged: bool, profile: Optional[str] = None,
                            is_first_hit: bool = True,
                            ability_type: Optional[int] = None) -> list[dict]:
    """Vecteur `On(PreAttackHit=6)` — emis PAR COUP par `IdunBattle.Operations.AttackDamageOperation$$
    ExecuteHit` (et son homologue `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit`) TOUT EN
    HAUT du coup : `FUN_180026490(0x50, .., 6, entities)` puis `.., 7 (PreAttackDamageHit)`, les DEUX
    **AVANT** le calcul du crit (`CritDamageInfo`) et avant le degat. L'`AbilityEntities` du vecteur est
    `ctor(caster = attaquant, .., target = defenseur, hitIndex@+0x110 = param_3)` -> `actor_id` =
    l'attaquant, `target_id` = le defenseur, `is_first_hit` = `hitIndex == 0` (lu par
    `IsFirstHitInSeries`).

    Le port n'a pas de boucle de coups au niveau des triggers (`_run_hits` resout les N coups d'un
    bloc) : il emet ce vecteur **UNE fois par attaque, avec `is_first_hit=True`** — strictement
    equivalent pour tout consommateur gate par `IsFirstHitInSeries` (le seul aujourd'hui : les deux
    branches PreAttackHit de ThrillSeekers). MEME classe d'approximation, et meme justification, que la
    granularite per-attaque de `unit_blocked_triggers`. A raffiner si un consommateur `On(6)` NON gate
    par `IsFirstHitInSeries` apparait (il fire alors N fois cote natif).

    PLACE D'EMISSION dans le port : apres `GetAttackHits` et **avant `_crit_params`** — c'est la place
    NATIVE, et elle est fonctionnellement obligatoire : le seul consommateur porte pose un stat-mod
    CRIT_CHANCE que le calcul de crit de CETTE attaque doit voir (sinon le port serait un no-op
    silencieux, exactement comme `AnvilShieldFrozenAttackerAdvantageAbility` sur `On(0x2b)`).
    AUCUN autre trigger porte n'ecoute `event_id == 6` -> no-op (et zero conso RNG) pour toute unite
    non-porteuse de ThrillSeekers."""
    ev = TriggerEvent(EventTriggerType.PreAttackHit, attacker_id, target_id,
                      ranged=ranged, profile=profile, ability_type=ability_type,
                      is_first_hit=bool(is_first_hit))
    return evaluate_trigger_operation(state, ev)


def damage_taken_triggers(state: State, source_id: Optional[int], target_id: int,
                          profile: Optional[str] = None) -> list[dict]:
    """Vecteur `On(DamageTaken=0xf=15)` — emis par `IdunBattle.Operations.ApplyDamageOperation$$Execute`
    (`FUN_180026490(0x4d, .., 0xf, entities)`) apres la mutation des PV, sous le gate
    `if ((0 < (int)local_7dc) || !HealthComponent.IsUnitWithHealthStat(target))` ou
    `local_7dc = FillUpStatComponent.Reduce(hp, healthDamage)` = la reduction de PV **REELLEMENT
    APPLIQUEE** (pas le degat demande). L'operation emet, dans l'ordre : `On(0x3a)`, `On(0xf)`
    DamageTaken, puis `On(0x10)` DamageDealt (celui-la gate `0 < armorDamage`). Son `AbilityEntities`
    porte la SOURCE du degat en caster/actor et la VICTIME en 3e slot -> `get_OwnerIsTarget` (le seul
    predicat porte qui lit ce vecteur) = « le porteur EST la victime ».

    Emis par le chokepoint `AttackDamageOperation._apply_damage_pipeline` (mirror du pipeline natif
    post-resolution partage par les 4 vecteurs de degat), **avant** `_fire_death_if_killed` : cote natif
    la mort n'est traitee qu'ensuite (`VerifyDeaths` -> `KillUnitOperation`), donc une victime qui vient
    de tomber a 0 PV est encore vivante quand `On(0xf)` part. Granularite : le natif emet par COUP
    (`ApplyDamageOperation` est appelee par coup), le port une fois par attaque -- sans effet observable
    pour le seul consommateur porte (re-pose/refresh idempotent).

    AUCUN autre trigger porte n'ecoute `event_id == 15`."""
    ev = TriggerEvent(EventTriggerType.DamageTaken, source_id, target_id,
                      ranged=False, profile=profile)
    return evaluate_trigger_operation(state, ev)


def after_hit_normal_attack(state: State, attacker_id: int, target_id: int,
                            ranged: bool, profile: Optional[str], is_crit: bool = False,
                            profiles=None, did_block: bool = False) -> list[dict]:
    """Vecteur attaque NORMALE. Le natif émet DEUX events distincts (verdict RE #147) : `On(0x26)`=NormalAttack
    (per-ATTAQUE, chemin normal only) ET l'after-hit `On(8)` (message 8 de `EvaluateAfterHitTriggers`). On
    dispatche les deux : `NormalAttack` déclenche Psyker (splash Smite) ; `after-hit(8)` = vecteur natif
    conservé (aucun consommateur actif depuis #151 — le reset ActOfFaith a migré sur On(9) ability-only, donc
    NE fire PLUS sur un crit d'attaque normale). `ranged`/`profile` = nature du coup primaire. Ajoute le passif
    `SquigHound` (spawn de grot après attaque) + la POSE on-hit des tile-effects de profil (`OnFireDamageAbility`).
    No-op si rien ne matche."""
    ev_na = TriggerEvent(EventTriggerType.NormalAttack, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit)
    out = evaluate_trigger_operation(state, ev_na)              # On(0x26) : Psyker (per-attaque)
    if did_block:                                               # `EvaluateAfterHitTriggers` : 0x3d AVANT 8
        out = out + unit_blocked_triggers(state, attacker_id, target_id, ranged, profile)
    ev_ah = TriggerEvent(EventTriggerType.AttackHit, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit)
    out = out + evaluate_trigger_operation(state, ev_ah)        # On(8) after-hit (vecteur natif ; sans conso #151)
    out = out + _on_fire_damage_ability(state, attacker_id, target_id, profile)  # OnFireDamageAbility IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateBehaviour
    out = out + _fire_of_absolution_after_attack(state, attacker_id, target_id, ranged)  # passif IdunBattleLogic.Entities.Abilities.Active.Loki.FireOfAbsolutionAbility$$CreateBehaviour (Vindicta)
    out = out + _squighound_after_attack(state, attacker_id, target_id)
    # On(9=Attack) : event GENERIQUE emis par `FinishAttackOperation IdunBattle.Operations.FinishAttackOperation$$Execute` a la FIN de CHAQUE attaque
    # (normale ET ability -- verdict RE re-expert : `On(9)` est BRUT, PAS ability-only ; le helper
    # `IdunBattleLogic.Entities.DSLFactory$$OnNormalAttackOrSmite` = `On(38)|(On(9)&Smite)` n'est PAS ce trigger). CORRIGE #151 : le
    # reset ActOfFaith (`On(9)&OwnerIsCaster&WasCrit` IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaith_RemoveEffectAbility$$CreateTrigger, AUCUN gate normal/ability) fire DONC AUSSI sur
    # un crit d'attaque NORMALE (avant, non emis en voie normale -> reset manquant = bug). Meme event consomme
    # par Judh `MoveAndSpawnDecoy` (G6b, `On(9)&OwnerIsTarget` IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateTrigger -> reaction a toute attaque la ciblant).
    # actor=attaquant, target=defenseur ; emis EN DERNIER (apres tous les after-hit(8) per-coup).
    # `profiles` (#202-C) = set COMPLET des profils de l'attaque (arme + bonus-hits #179) — lu par
    # `CurrentAttackDamageProfilesContain` (trigger 1173 : une attaque non-Psychic au corps a corps
    # avec bonus InfernalPacts Psychic QUALIFIE — mesure live diag 202c).
    ev_at = TriggerEvent(EventTriggerType.Attack, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit, profiles=profiles)
    out = out + evaluate_trigger_operation(state, ev_at)
    # `On(UnitPostAbility=0xe)` (#100) — DERNIER evenement de `ActiveAbilityOperation.ExecuteInternal`
    # (sequence `0x2b` -> execution -> `0xb` -> `0xc` -> `0xe`). Emis ICI = a la CLOTURE de l'attaque
    # normale, en pendant exact du `On(0x2b)` emis en tete par `AttackDamageOperation.execute`.
    # Consommateur porte : `AnvilShieldFrozenAdvantageExpire` (consomme le +20 % block transitoire).
    return out + unit_post_ability_triggers(state, attacker_id, target_id, ranged, profile,
                                            ability_type=1013)


def after_hit_ability_attack(state: State, attacker_id: int, target_id: int,
                             is_crit: bool, profile: Optional[str] = None,
                             ability_type: Optional[int] = None,
                             did_block: bool = False) -> list[dict]:
    """Vecteur after-hit d'une attaque d'ABILITY ou de SPLASH. Mirror `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`,
    porté par `ADamageOperation` donc PARTAGÉ par l'attaque normale ET les attaques d'ability : dispatche le
    message **after-hit `On(8)`** (branche crit `param_6!=0` = `On(0x3d)`, non écouté ici). ⚠ Ce vecteur
    NE dispatche PAS `NormalAttack(0x26)` : le splash emprunte `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit`
    (events {6,8,0x3d}, JAMAIS 0x26) → **Psyker `On(0x26)` ne re-fire PAS ici = pas de chain** (verdict RE
    #147/#150 ; corrige la sur-propagation de #140). Consommateur actif : reset ActOfFaith (#138, `On(8)` +
    gate `is_crit`) au crit d'ability/splash (ArmoriumCherub, splash FireOfAbsolution). `ranged` (position-based,
    `_is_ranged_position` = mirror `DSLFactory.IsRangedAttack`) reste porté par l'événement pour fidélité (aucun
    consommateur `On(8)` ne le lit aujourd'hui). Le cap `<51/phase` (`TriggeredAbilityComponent`) reste un
    garde-fou générique fidèle au natif (`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger`). No-op si aucun trigger ne matche."""
    ranged = _is_ranged_position(state, attacker_id, target_id)
    # On(9) ability-attack (per-attaque) : reset ActOfFaith au crit (IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaith_RemoveEffectAbility$$CreateTrigger = On(9) & OwnerIsCaster &
    # WasCrit & HasEffect(0x3f9)). #151 : ROUTE le reset ICI (voie ability/splash/normal-like = is_normal_attack
    # =False) au lieu de after-hit(8) partagé avec la NORMALE -> plus de reset sur un crit d'attaque normale.
    # `ability_type` = AbilityOrEffect du coup (payload d'event natif, lu par les gates kind type
    # DirectAbilitySelector) — threadé par la feuille `AttackWithAttackDamage` (ex. smite Psyker =
    # 0x3f5=1013 → branche 2 de LordOfTempests AddIce #35). None (callers historiques) = gates kind muets.
    ev_aa = TriggerEvent(EventTriggerType.Attack, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit, ability_type=ability_type)
    out = evaluate_trigger_operation(state, ev_aa)
    if did_block:                                     # `EvaluateAfterHitTriggers` : 0x3d AVANT 8
        out = out + unit_blocked_triggers(state, attacker_id, target_id, ranged, profile)
    # On(8) after-hit (vecteur natif per-coup, EvaluateAfterHitTriggers) : conservé pour fidélité ; aucun
    # consommateur actif depuis #151 (le reset a migré sur On(9)).
    ev_ah = TriggerEvent(EventTriggerType.AttackHit, attacker_id, target_id,
                         ranged=ranged, profile=profile, is_crit=is_crit)
    return out + evaluate_trigger_operation(state, ev_ah)


def evaluate_abilities_for_event(state: State, caster_id: int, target_id: int,
                                 event: int, ranged: bool) -> list[dict]:
    """Mirror `IdunBattle.Entities.Behaviours.EvaluateAbilitiesBehaviour$$Execute` (IdunBattle.Entities.Behaviours.EvaluateAbilitiesBehaviour$$.ctor, champ +0x50 = `EventTriggerType`)
    : EVALUE les abilities DÉCLENCHÉES du CASTER pour l'`EventTriggerType` `event`, INLINE dans un behaviour-tree
    (nœud DSL générique `IdunBattleLogic.Entities.DSLFactory$$EvaluateAbilities`). Callers natifs : NormalAttack
    `EvaluateAbilities(0x26)`, ArmoriumCherub `EvaluateAbilities(0x4b=AttackInAtomicGroup)`, ArmouredMight/
    TheQuickening (after-move).

    `AttackInAtomicGroup` (attaque d'ability ATOMIQUE du caster, ex. ArmoriumCherub `ExecuteAtomic`) -> le passif
    ranged `FireOfAbsolution` (SEUL passif de ce chemin PORTÉ ; les autres after-hit de l'attaque primaire fire
    déjà DANS l'Operation d'attaque via `after_hit_ability_attack`). Ranged-only (FireOfAbsolution ne fire que
    sur attaque RANGED). No-op pour tout autre event (rien d'autre porté ici). Extensible : un futur passif
    keyé sur cet event s'ajoute ici."""
    out: list[dict] = []
    if int(event) == int(EventTriggerType.AttackInAtomicGroup):
        out += _fire_of_absolution_after_attack(state, caster_id, target_id, ranged)
    return out


def after_move_triggers(state: State, mover_id: int) -> list[dict]:
    """Vecteur after-move (mirror `IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers → dispatch).
    Le natif émet, dans l'ordre, `On(0x24=UnitPositionChanged_1)` (aucun consommateur porté), `On(4=
    UnitAfterMove)` (overwatch) PUIS `On(0x1d=UnitPositionChanged_2)`. On dispatche `On(4)` puis `On(0x1d)` :
    ce dernier déclenche DecoysAndMisdirection (G2 — ennemi/allié qui marche sur un decoy allié crushé par
    `_kill_steppable_units`, G1). No-op si aucun trigger ne matche (ou pas de board/rng)."""
    ev = TriggerEvent(EventTriggerType.UnitAfterMove, mover_id, mover_id, ranged=False, profile=None)
    out = evaluate_trigger_operation(state, ev)
    # G2 : `On(0x1d=UnitPositionChanged_2)` émis APRÈS `On(4)` par le même `EvaluateAfterMoveTriggers` natif.
    ev2 = TriggerEvent(EventTriggerType.UnitPositionChanged_2, mover_id, mover_id, ranged=False, profile=None)
    return out + evaluate_trigger_operation(state, ev2)


def displace_triggers(state: State, pusher_id: int, pushed_id: int) -> list[dict]:
    """Vecteur DÉPLACEMENT FORCÉ (push/pull) — mirror `IdunBattle.Operations.DisplaceUnitOperation$$EventAndAbilitiesAndEffects`. APRÈS le `MoveUnit@0x7e` de la poussée, le natif émet (via `EvaluateTriggerOperation`, msg 0x52)
    la SÉQUENCE d'events `On(0x24=UnitPositionChanged_1)` -> `On(0x23=UnitDisplaced)` -> `On(0x1d=
    UnitPositionChanged_2)`, tous {actor=pusher, target=pushed}. On dispatche `On(UnitDisplaced)` (actor=pusher,
    target=pushed) : consommateur `RadSaturationAbility` (branche 2 `OwnerIsTarget` -> le Skitarii Vanguard POUSSÉ
    contamine sa tuile d'ATTERRISSAGE ; le pushed a déjà bougé via `MoveUnitOperation` donc `Tiles(Caster())` =
    sa tuile POST-push). Siblings `On(0x24)` / `On(0x1d)` = NON dispatchés ici (flaggés) : `0x24` sans consommateur
    porté ; `0x1d`=DecoysAndMisdirection G2-sur-push = concern séparé (non validé). No-op si aucun trigger ne
    matche. Appelé par `DisplaceUnitOperation.execute` (displace.py) après un push réussi."""
    ev = TriggerEvent(EventTriggerType.UnitDisplaced, pusher_id, pushed_id, ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)


def tile_tick_triggers(state: State) -> list[dict]:
    """Vecteur ROUND-TICK des tile-effects (#128) : `IdunBattle.Operations.StartTurnOperation$$Execute émet la séquence
    0x12/0x13/0x14/... → ici on tire `On(0x12)` (Contaminated re-apply IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$CreateHandleTriggerAbilitiesInternal) puis `On(0x14)` (Fire DoT
    IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateTrigger + DryBush spread IdunBattleLogic.Entities.Abilities.Tiles.DryBushFireSpreadAbility$$CreateTrigger). Chaque tile-effect trigger (owner=tuile) matche sur l'occupant
    de SA tuile. Ordre 0x12 puis 0x14, AVANT le turn-start `On(0x16)` (ordre exact = HYPOTHÈSE à valider,
    cf. verdict RE #128). La PROPAGATION DryBush (`dry_bush_fire_spread`) tourne APRÈS le DoT `On(0x14)` : le
    DoT frappe les occupants des tuiles en feu AU DÉBUT du tick, puis la propagation allume les voisines pour
    le tick SUIVANT (snapshot source → pas de cascade même-tick). No-op si aucun tile-effect actif."""
    out: list[dict] = []
    for eid in (EventTriggerType.TurnStart_EffectActivation, EventTriggerType.TurnStart_EnvironmentEffects):
        ev = TriggerEvent(eid, -1, -1, ranged=False, profile=None)
        out += evaluate_trigger_operation(state, ev)
    out += dry_bush_fire_spread(state)    # `DryBushFireSpreadAbility` On(0x14) : feu DryBush -> DryBush adjacent (10%)
    return out


def after_death_triggers(state: State, dying_id: int, killer_id: Optional[int],
                         overkill: bool = False) -> list[dict]:
    """Vecteur MORT (mirror `IdunBattleLogic.Entities.DSLFactory$$OnDeathEvent → dispatch). Construit l'événement `On(1)`
    {killer=0x158, dying=0x178, overkill} et lance `evaluate_trigger_operation`. Déclenche les accumulations
    ActOfFaith (allié Imperial qui meurt ou tue) + FinalJustice (l'unité mourante riposte, sauf overkill).
    `actor_id`/`target_id` reflètent killer/dying pour le dispatch générique. No-op si aucun trigger ne
    matche."""
    ev = TriggerEvent(EventTriggerType.PreUnitDeath,
                      killer_id if killer_id is not None else dying_id, dying_id,
                      ranged=False, profile=None, killer_id=killer_id, dying_id=dying_id,
                      overkill=overkill)
    return evaluate_trigger_operation(state, ev)


def pre_unit_death_2_triggers(state: State, dying_id: int, killer_id: Optional[int],
                              overkill: bool = False) -> list[dict]:
    """Vecteur `On(PreUnitDeath_2 = 2)` — event NATIF DISTINCT de `PreUnitDeath(1)` et de
    `UnitDefeated(55)`. Emis par `KillUnitOperation$$IdunBattle.Operations.KillUnitOperation$$Execute` ENTRE les deux : ordre
    d'instruction LU au decompile `On(1)` (ret IdunBattle.Operations.KillUnitOperation$$Execute+0x7dc) -> `On(2)` (ret IdunBattle.Operations.KillUnitOperation$$Execute+0x97a) ->
    `On(0)` (IdunBattle.Operations.KillUnitOperation$$Execute+0xdf9) -> `On(0x37=55)` (IdunBattle.Operations.KillUnitOperation$$Execute+0xeac) -> `On(0x36=54)` (IdunBattle.Operations.KillUnitOperation$$Execute+0x102c).
    (`ApplyDamageOperation$$IdunBattle.Operations.ApplyDamageOperation$$Execute` n'emet AUCUN des trois ; `InputMessageProcessor$$
    IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` non plus — il ne fait qu'appeler `OperationProcessor$$Core.Services.OperationProcessor$$KillUnit.)

    Consommateurs portes : la famille DEATH-NOVA (`IdunBattleLogic.Entities.DSLFactory$$OnPreDeath2` ->
    `IdunBattleLogic.Entities.DSLFactory$$OnDeathEvent(2, a, b)) — `ExplodesAbility` (trait Explodes) et `PutridExplosion_Ability`
    (trait PutridExplosion). Les DEUX passent `a=1` -> AUCUN gate `NOT HasFlag(dying, Overkilled=8)` :
    la nova part MEME EN OVERKILL (le flag `overkill` est thread pour fidelite du payload, aucun
    consommateur de CE vecteur ne le lit aujourd'hui). L'unite est deja `alive=False` au dispatch
    (fire-on-death). No-op si aucun porteur ne meurt."""
    ev = TriggerEvent(EventTriggerType.PreUnitDeath_2,
                      killer_id if killer_id is not None else dying_id, dying_id,
                      ranged=False, profile=None, killer_id=killer_id, dying_id=dying_id,
                      overkill=overkill)
    return evaluate_trigger_operation(state, ev)


def unit_death_triggers(state: State, dying_id: int, killer_id: Optional[int] = None,
                        overkill: bool = False) -> list[dict]:
    """Vecteur `On(UnitDeath=0)` — 3e des events de mort emis par `IdunBattle.Operations.KillUnitOperation$$Execute`
    (sequence verifiee au decompile : `FUN_180026490(...,1)` PreUnitDeath -> `...,2` PreUnitDeath_2 ->
    `...,0` **UnitDeath** -> `...,0x37` UnitDefeated -> `...,0x36` PostUnitKill). Le port emettait deja
    `On(1)` (`after_death_triggers`) et `On(0x37)` (`unit_defeated_triggers`) mais PAS `On(0)` — d'ou ce
    vecteur, insere a sa place EXACTE (entre les deux).

    Consommateur : branche 1 de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger`
    (`On(0) & OwnerIsActor & TargetIsOverkilled` -> +1 stack). `actor` = le TUEUR (OwnerIsActor),
    `target`/`dying` = la victime, `overkill` = `TargetIsOverkilled`. No-op si rien ne matche.
    (Le `IdunBattle.Entities.Effects.Loki.MasterAnnihilator_AdditionalHitEffect$$CreateRemoveEffectTrigger` ecoute aussi `On(0)`
    — retrait du marqueur a la mort de SA source — mais c'est un EFFET-trigger non enregistre, cf.
    loki/master_annihilator.py.)"""
    ev = TriggerEvent(EventTriggerType.UnitDeath,
                      killer_id if killer_id is not None else dying_id, dying_id,
                      ranged=False, profile=None, killer_id=killer_id, dying_id=dying_id,
                      overkill=overkill)
    return evaluate_trigger_operation(state, ev)


def pre_effect_added_triggers(state: State, source_id: Optional[int], target_id: Optional[int],
                              effect_type: int) -> list[dict]:
    """Vecteur `On(PreEffectAdded=0x3e=62)` — emis par `IdunBattle.Operations.AddEffectOperation$$Execute` **TOUT EN
    HAUT** (`FUN_180026490(0x50, ..., 0x3e)` juste apres la construction de l'`AbilityEntities`, AVANT le
    gate cible-nulle, AVANT le gate << deja present >> et AVANT le gate d'immunite `HasFlag(target,6)`).
    => l'evenement fire meme quand l'effet n'est finalement PAS applique (semantique << would have >>).

    `AbilityEntities.ctor(source, source, target)` -> **actor = la SOURCE** de l'effet ; `target` = la
    cible ; `triggering_effect` = le type pose (lu par `TriggeringEffectIs`). Consommateur : branche 2 de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger`. No-op si rien ne matche."""
    ev = TriggerEvent(EventTriggerType.PreEffectAdded,
                      source_id if source_id is not None else -1,
                      target_id if target_id is not None else -1,
                      ranged=False, profile=None, triggering_effect=int(effect_type))
    return evaluate_trigger_operation(state, ev)


def unit_defeated_triggers(state: State, dying_id: int, killer_id: Optional[int] = None) -> list[dict]:
    """Vecteur `On(UnitDefeated=55=0x37)` (G3) — event NATIF DISTINCT de `PreUnitDeath(1)` : le natif
    `Ambush_SummonAbility` IdunBattleLogic.Entities.Abilities.Triggered.Loki.Ambush_SummonAbility$$CreateTrigger ecoute `On(0x37) & OwnerIsTarget & Not(HasFlag 0xe)`, PAS On(1). Emis
    par le pipeline de mort APRES `after_death_triggers(On 1)` (l'unite est deja alive=False -> l'ability
    fire-on-death voit sa mort). Declenche la pose du decoy Ambush (mort -> decoy) + l'enregistrement de
    `turn_defeated`. No-op si aucun porteur Ambush ne meurt."""
    ev = TriggerEvent(EventTriggerType.UnitDefeated,
                      killer_id if killer_id is not None else dying_id, dying_id,
                      ranged=False, profile=None, killer_id=killer_id, dying_id=dying_id)
    return evaluate_trigger_operation(state, ev)


def unit_revived_triggers(state: State, revived_id: int, current_ability=None) -> list[dict]:
    """Vecteur `On(UnitRevived = 46 = 0x2e)` (case-89 volet B3) — emis par `ReviveUnitOperation.Execute`
    @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xac1 (`FUN_180026490(0x4d, DAT_1831d3468, events, 0x2e)`), APRES la mutation PV/flags/position
    et **AVANT** la purge de la `ReviveData` (@IdunBattle.Operations.ReviveUnitOperation$$Execute+0xda7+). DISTINCT d'`On(UnitResurrected=47=0x2f)`
    (`ResurrectUnitOperation`, ambush).

    `current_ability` = le `sourceId` (`AbilityOrEffect`) porte par la `ReviveData` — c'est ce que lit le
    noeud `CurrentAbilityIs` des consommateurs. Consommateurs portes :
      * `PhoenixGem_CanReviveEffect` IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal : `On(0x2e) & OwnerIsTarget & CurrentAbilityIs(0x5b2=1458
        TriggeredAbilityType.PhoenixGem)` -> `RemoveEffect(marqueur 1451)` = « the FIRST TIME each battle » ;
      * (non porte, cf. residu A2) `FuelledByFury_CanReviveEffect` IdunBattle.Entities.Effects.Loki.FuelledByFury_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal : meme forme avec
        `CurrentAbilityIs(0x4e3=1251)` -> `DeactivateEffect` (« first time each TURN »).
    Le bras `On(UnitRevived)` du trait Swarm est, lui, re-evalue IMPERATIVEMENT par l'Operation (helper
    `on_group_unit_hp_changed`) — residu structurel deja documente (#60). No-op si rien ne matche."""
    ev = TriggerEvent(EventTriggerType.UnitRevived, revived_id, revived_id,
                      ranged=False, profile=None, ability_type=current_ability)
    return evaluate_trigger_operation(state, ev)


def unit_resurrected_triggers(state: State, resurrected_id: int) -> list[dict]:
    """Vecteur `On(UnitResurrected=47=0x2f)` (G3) — emis par `ResurrectUnitOperation` IdunBattle.Operations.ResurrectUnitOperation$$Execute apres une
    resurrection Ambush (`actor` = l'unite ressuscitee, co-localisee avec le decoy qu'elle vient de crusher).
    Alimente `DecoysAndMisdirection_BuffFriends` (G2, `(On(0x2f)|On(0x1d)) & AreFriends` -> +582 + nouveau
    decoy si GS Cult) et la re-arme HeroicFusillade (G5, `On(0x2f) & OwnerIsTarget`). No-op si aucun
    consommateur ne matche. Le decoy crushe (steppable, alive=False, meme tuile) satisfait `GetValidDeadDecoys`
    de BuffFriends (co-localisation dead-decoy/stepper)."""
    ev = TriggerEvent(EventTriggerType.UnitResurrected, resurrected_id, resurrected_id,
                      ranged=False, profile=None)
    return evaluate_trigger_operation(state, ev)


def is_overkill(hp_before, damage) -> bool:
    """`IdunBattle.Core.Services.DamagePrediction$$IsOverkill : coup létal OVERKILL ssi l'excès `(dmg - PV)` >=
    `overkillDmgPctOfHealth`% du PV (=100% → `dmg >= 2*PV`). `CanBeOverkilled` (= NOT trait 0x1b) non
    porté offline (aucun nom de trait dispo ; worldKharn ne l'a pas) → supposé True. No-op (False) si
    dégât inconnu ou PV<=0."""
    import gameconfig as GC
    if damage is None or hp_before is None or hp_before <= 0:
        return False
    pct = int(GC.global_value(OVERKILL_PCT_KEY) or 100)
    return (int(damage) - int(hp_before)) * 100 >= pct * int(hp_before)


def start_turn_triggers(state: State, player_id: int) -> list[dict]:
    """Vecteur DÉBUT DE TOUR (mirror `IdunBattle.Operations.StartTurnOperation$$Execute émettant l'event `On(0x16)`).
    Construit l'événement turn-start {player=player_id} et lance `evaluate_trigger_operation`. Déclenche
    les auto-tours forcés du player courant (ex. TheBetrayer de worldKharn : move+attaque). `actor`/`target`
    = -1 (pas d'acteur unique ; chaque trigger filtre sur `ev.player_id` == son owner). No-op si aucun
    trigger turn-start ne matche (ou pas de board/rng pour le move+attaque).

    #G6a : au boundary de tour, remet a 0 le compteur d'attaques recues (`HasBeenAttackedAmountThisTurn`) de
    toutes les unites PUIS re-evalue l'ActiveCondition des HP-floors Hypersensory (`IsEnemyTurn(owner) &
    Not(attacked>=1)`) -> Apply (snapshot 50% du HP courant) au tour ENNEMI du porteur, Revert sinon. Avant
    l'emission de l'event (l'etat floor doit etre pose quand les triggers turn-start s'executent)."""
    from ..minimal_health import reset_times_attacked, evaluate_minimal_health
    from ..revive import reset_revive_gates
    reset_times_attacked(state)
    reset_revive_gates(state)          # case-66 : REACTIVE le passif revive (once-per-turn) au turn-start
    evaluate_minimal_health(state, player_id)
    ev = TriggerEvent(EventTriggerType.TurnStart_Actions, -1, -1, ranged=False, profile=None, player_id=player_id)
    return evaluate_trigger_operation(state, ev)


def turn_start_other_triggers(state: State, player_id: int) -> list[dict]:
    """Vecteur `On(TurnStart_Other=0x13=19)` — 2e des 5 events emis par `IdunBattle.Operations.StartTurnOperation$$Execute` (sequence 0x12->0x13->0x14->0x15->0x16 ; cf. turnflow.py). Dispatch GENERIQUE du
    registre `TRAIT_TRIGGERS` sur cet event. Consommateur : `LivingMetalRepairAbility` (#203, regen %
    PV des Necron endommages, `OwnerIsActor` via `player_id`). Le meme event 0x13 porte aussi FirstAid
    (tile-effect, reste bespoke dans tiles.py). `actor`/`target` = -1 (chaque trigger filtre sur
    `ev.player_id`). No-op si aucun porteur LivingMetal endommage du player courant."""
    ev = TriggerEvent(EventTriggerType.TurnStart_Other, -1, -1, ranged=False, profile=None, player_id=player_id)
    return evaluate_trigger_operation(state, ev)


PILEIN_MIN_OWNER_TURNS = 2      # `OwnerHasFinishedMinTurns(2)` — gate du trigger PileIn IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateTrigger


def end_turn_summon_triggers(state: State, player_id: int) -> list[dict]:
    """Vecteur FIN DE TOUR (`On(0x17=TurnEnd=23)`). Deux volets :

    1. DISPATCH GENERIQUE `On(TurnEnd)` (registre `ABILITY_TRIGGERS`) — ability-triggers TurnEnd. Consommateur :
       `RadSaturationAbility` (branche 3 : le Skitarii Vanguard qui n'a PAS bouge ce tour contamine sa tuile en
       fin de tour ; gate `not unit_has_moved(state, owner)` = `NOT HasFlag(owner, UnitFlag.Moved)`).
       `player_id` scope l'`OwnerIsActor`.
    2. Passif d'auto-dédoublement `PileInAbility` (BESPOKE : trigger IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateTrigger `On(0x17)` &
       `OwnerHasFinishedMinTurns(2)` & `IsUnitWithStatAmount(Health Cur==Max)` ; behaviour IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateBehaviour) — chaque
       grot (passif `PileIn`) du `player_id`, a PV PLEINS et owner >=2 tours finis, s'auto-dédouble avec proba
       `chance − chance_2 × (#grots amis)` = 75 − 5×n. `Maybe(chance)` non modélisé -> DÉTERMINISTE (fire si
       chance>0, cap naturel n=15). Double = `execute_pilein_replica`. Snapshot AVANT la boucle (« acts on its
       NEXT turn »).

    (PileIn reste BESPOKE — pas dans `ABILITY_TRIGGERS` -> pas de double-fire par le dispatch generique.)"""
    import gameconfig as GC
    from ..spawn import SpawnUnitOperation
    # 1. dispatch generique On(TurnEnd) : RadSaturation (fin de tour si pas bouge) + tout futur ability-trigger TurnEnd.
    ev = TriggerEvent(EventTriggerType.TurnEnd, -1, -1, ranged=False, profile=None, player_id=player_id)
    out: list[dict] = evaluate_trigger_operation(state, ev)
    # 2. PileIn (bespoke) — gate min-turns propre a PileIn (n'affecte pas le dispatch generique ci-dessus).
    if state.turn_counts.get(int(player_id), 0) < PILEIN_MIN_OWNER_TURNS:
        return out
    consts = (GC.ability("PileIn") or {}).get("constants") or {}
    chance0 = int(consts.get("chance") or 75)
    chance_2 = int(consts.get("chance_2") or 5)
    # snapshot des grots-PileIn vivants du player, à PV PLEINS (avant tout spawn de ce tour).
    candidates: list[tuple] = []
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        hc = e.get_component(HealthComponent)
        if uc is None or oc is None or hc is None or not uc.alive:
            continue
        if oc.player != int(player_id):
            continue
        if "PileIn" not in ((GC.unit(uc.visual_id) or {}).get("passiveAbilities") or []):
            continue
        if hc.hp < hc.hp_max:                  # `IsUnitWithStatAmount(Health Cur==Max)` = PV PLEINS
            continue
        candidates.append((eid, uc.visual_id, oc.team))
    # NB : `out` porte deja les resultats du dispatch generique On(TurnEnd) (volet 1) — on APPEND PileIn dessus.
    for (gid, vid, team) in candidates:
        # `UnitsWithSameVisualId(self) & Friends(3)` -> Count = grots amis (même visualId) hors self.
        n = sum(1 for e2 in state.entities.values()
                if e2.id != gid
                and (u2 := e2.get_component(UnitComponent)) is not None and u2.alive and u2.visual_id == vid
                and (o2 := e2.get_component(OwnerComponent)) is not None and o2.team == team)
        chance = chance0 - chance_2 * n        # `Difference(75, Multiply(count, 5))`
        if chance <= 0:                        # cap naturel : 0 % dès n>=15 grots
            continue
        spawned = SpawnUnitOperation.execute_pilein_replica(state, gid)
        if spawned:
            out.append({"grot": gid, "spawned": spawned, "chance": chance, "n_grots": n})
    return out
