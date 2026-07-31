"""Les QUATRE registres de triggers (trait / passiveAbility / activeAbility / effectType),
extraits de `triggers/dispatch.py` (scission du module >1000 lignes, tache #169 --
deplacement VERBATIM, zero changement de comportement).

Ce module porte AUSSI le gros bloc d'imports d'abilities concretes que ces registres
entrainent : ce sont leurs VALEURS, ils n'ont pas d'autre consommateur.

Les quatre dicts sont re-exportes TELS QUELS par le `__init__` du package (meme objet) :
un consommateur externe qui les MUTE (`ACTIVE_ABILITY_TRIGGERS.pop(...)` d'un test) agit
bien sur le dict que lit `core.collect_*`. Un REBIND, lui, ne porterait pas -- aucun site
connu n'en fait."""
from __future__ import annotations

from ..base import TriggeredAbility, EffectTrigger
from ..loki import (PsykerExtraAttackAbility, ActOfFaithAccumulateAbility, ActOfFaithResetAbility,
                   FinalJusticeAbility, TheBetrayerAddEffectAbility, TheBetrayerTakeTurnAbility,
                   ArcaneShieldAbility, ControlEdictAbility, RadSaturationAbility,
                   LordOfTempestsAddIceAbility, FireTileDoT, FIRE_TILE,
                   OnFireDamageAbility, OnToxicDamageAbility)
from ..effect_triggers import (OverwatchAutoAttack, ContaminatedTileEffect,
                              RangedAutoAttackActivateOnTurnStart,
                              RangedAutoAttackDeactivateOnTurnStart,
                              RangedAutoAttackDeactivateOnAttack,
                              OVERWATCH_AUTO_ATTACK, CONTAMINATED_TILE)
from ..genestealer import (DecoysAndMisdirectionDamageEnemiesAbility,
                          DecoysAndMisdirectionBuffFriendsAbility,
                          AmbushSummonAbility, EnvAmbushResurrectAbility,
                          HypersensoryMoveAndSpawnDecoyAbility)
from ..loki.weaver_of_fate import WeaverOfFateAbility                 # #202-A (trait WeaverOfFate)
from ..loki.reality_unbound import (RealityUnboundAbility,            # passif thousTzaangor (2 volets)
                                   RealityUnboundExtraMaxDamageAbility)
from ..loki.time_flux import TimeFluxRegenAbility                     # passif thousTerminator (volet regen)
from ..loki.ghost_revive import (GhostReviveAbility,                 # #213 (volet ghost-revive)
                                 GhostEffectRevive, GhostRemoveOnSourceMoves,
                                 GhostRemoveOnUnitAdded, GhostRemoveOnUnitEnters,
                                 GhostRemoveOnSourceDeathInactive, GhostRemoveOnSourceRemoved,
                                 GHOST_EFFECT)
from ..loki.living_metal import LivingMetalRepairAbility             # #203 (trait LivingMetal, Necron)
from ..loki.destroyer_hive import DestroyerHiveAbility               # case-220 DG (passiveAbility deathTyphus)
from ..loki.cursed_plague_bell import (CursedPlagueBellMovementAbility,   # #224 DG (passif deathBlightbringer)
                                      CursedPlagueBellAttackAbility)     # #224 item 5 (volet ATTAQUE)
from ..loki.martial_apotheosis import MartialApotheosisAttackAbility  # case-220 (passif necroOverlord, Necron)
from ..loki.martial_superiority import MartialSuperiorityRiposteAbility  # #133 (passif templChampion)
from ..loki.master_of_the_tutelaries import (MasterOfTheTutelariesSummonAbility,   # #202-C (triggered 1173)
                                            MASTER_EFFECT as MASTEROFTUTELARIES_EFFECT)
from ..loki.tainted_narthecium import TaintedNartheciumReviveAbility  # case-66 (passif deathRotbone, revive)
from ..loki.narthecium import NartheciumReviveAbility                 # #79 (passif ultraApothecary, revive)
from ..loki.rites_of_morkai import (RitesOfMorkaiReviveTrigger,       # #79 (effet 1502 pose par Baldr)
                                   RITES_OF_MORKAI_EFFECT)
from ..loki.reanimation_beam import (ReanimationBeamReviveTrigger,    # #79 (effet 1547, MoW necroReanimator)
                                    REANIMATION_BEAM_EFFECT)
from ..loki.phoenix_gem import (PhoenixGemReviveAbility,              # #79 (relic, marqueur 1451)
                               PhoenixGemRemoveMarkerOnRevive,       # #89-B3 (On(0x2e) -> RemoveEffect)
                               PhoenixGemRemoveMarkerOnResurrect,    # #89-B3 (On(0x2f) -> RemoveEffect)
                               PHOENIX_GEM_CAN_REVIVE)
from ..loki.suppressive_fire import SuppressiveFireAddEffectAbility  # #74 (trait SuppressiveFire 1010)
from ..loki.death_nova import ExplodesAbility, PutridExplosionAbility  # death-nova (traits 1008 / 2028)
from ..loki.master_annihilator import MasterAnnihilatorMarkAbility   # lot POSE (passif admecDominus)
from ..loki.fleshmetal_guns import (FleshmetalGunsRotationAbility,   # lot POSE (passif blackObliterator)
                                   FleshmetalGunsTileEffectAbility)  # #85 volet DespoiledGround
from ..loki.despoiled_ground import (DespoiledGroundTileDoT,         # #85 (EnvDespoiledGroundTileAbility)
                                    DESPOILED_GROUND_TILE)
from ..loki.terrifying_crescendo import (TerrifyingCrescendoOverkillAbility,   # lot POSE (passif
                                        TerrifyingCrescendoSuppressAbility)   # emperNoiseMarine, #204)
from ..loki.fuelled_by_fury import (FuelledByFuryExtraDamageAbility,  # compteur 1323 (passif ultraTitus)
                                    FuelledByFuryReviveAbility,       # #88 A1 : self-revive On(3)
                                    FuelledByFuryCanReviveActivateOnAbilityInit,
                                    FuelledByFuryCanReviveActivateOnTurnStart,
                                    FuelledByFuryCanReviveDeactivateOnRevive,
                                    FUELLED_BY_FURY_CAN_REVIVE)       # marqueur 1324
from ..loki.anvil_shield import (AnvilShieldApplyIceAbility,          # lot POSE (passif spaceRockfist)
                                AnvilShieldApplyStunAbility,          # #100 volet Stun on-block
                                AnvilShieldFrozenAttackerAdvantageAbility,   # #100 volet +block glace
                                AnvilShieldFrozenAdvantageExpire,     # #100 conso On(UnitPostAbility)
                                FROZEN_ADVANTAGE as ANVIL_FROZEN_ADVANTAGE)
from ..loki.let_the_galaxy_burn import (LetTheGalaxyBurnArmAbility,   # #84 (trait LetTheGalaxyBurn 1058)
                                       LetTheGalaxyBurnResetAbility)
from ..loki.sworn_protector import (SwornProtectorSummonKellAbility,  # #95-RESTE2 (passif astraCreed)
                                   SwornProtectorProtectSwitchAbility)
from ..loki.haze_of_corruption import (HazeOfCorruptionTargetFinderAbility,   # case-207 (deathBlightlord)
                                      HazeCorruptionBonusHitAbility,         # case-209 (coup Toxic bonus)
                                      HazeOfCorruptionDamageTransferTrigger,  # case-209 (effet 1077)
                                      HAZE_DAMAGE_TRANSFER)
from ..loki.listen_up_maggots import ListenUpMaggotsAddEffectAbility  # #95-RESTE2 (passif astraSmnKell)
from ..loki.thrill_seekers import (ThrillSeekersFullHealthTargetAbility,   # trait ThrillSeekers 1056
                                  ThrillSeekersDamageTakenAbility)        # (x5 Emperor's Children)
from ..loki.hailstrike import HailstrikeAttackAbility                 # case-117 ph.2 (1214 -> 1507)
from ..loki.inspired_to_greatness import (InspiredToGreatnessOverrideLevelRemove,   # #114 residu 2
                                         ITG_OVERRIDE_LEVEL)
from ..loki.chronometron import (ChronometronExtraDamageRemove,                    # residu R9
                                CHRONOMETRON_EXTRA_DAMAGE)
from ..loki.reactivate_overwatch import (EarlyWarningOverrideReactivateOverwatch,   # #114 residu 3
                                        EarlyWarningOverrideHitReductionPurge,
                                        EWO_REACTIVATE_OVERWATCH)
from ..loki.cosmic_horror import (CosmicHorrorOnKillAbility,           # passif genesPatriarch (GS Cults)
                                 CosmicHorrorOnMoveAbility)
from ..loki.spiritual_leader import SpiritualLeaderAbility             # passif genesMagus (GS Cults)
from ..loki.barbed_ovipositor import BarbedOvipositorSummonAbility     # passif tyranParasite (Tyranids)
from ..loki.fabricator_claw_array import FabricatorClawArrayAbility    # #303 (passif necroSpyder, N20)
from ..loki.dawn_blade import DawnBladeHealAbility                     # #317 (relique tauFarsight)
from ..loki.relentless_march import RelentlessMarchAbility             # #328 (passif necroWarden)


# --- Registre : trait → ability-trigger(s) accordée(s) --------------------------------------------
TRAIT_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    "Psyker": [PsykerExtraAttackAbility],
    # ActOfFaith accorde DEUX ability-triggers (accumulation sur mort/kill + reset au crit).
    "ActOfFaith": [ActOfFaithAccumulateAbility, ActOfFaithResetAbility],
    # FinalJustice (worldKharn) = attaque normale à la mort (fire-on-death, gate overkill).
    "FinalJustice": [FinalJusticeAbility],
    # Ambush (Isaak/Judh/Neophyte, G3) = mort -> decoy (On UnitDefeated=54) + resurrection sur decoy allie
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
    # ArcaneShield (Thaumachus) = bouclier à la FIN DE L'ACTIVATION du porteur : `On(0x1c=
    # ArrivedAtFinalTile) & OwnerIsActor & OwnerIsCaster` -> vecteur `arrived_at_final_tile_triggers`
    # (après son 1er move, OU à la clôture de son tour s'il n'a pas bougé). Cible = `First(SortByFormula(
    # pool, Sum(3*distance, faction, chaos, owner), ASC), 1)` — score ADDITIF où la distance domine.
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
    # CursedPlagueBell (passif deathBlightbringer/Corrodius, Death Guard) -- DEUX des trois classes
    # natives du passif ; la DANGER ZONE (`CursedPlagueBellDangerZoneAbility` +
    # `CursedPlagueBell_DangerZoneEffect` 1084) n'est PAS portee.
    #  * MOUVEMENT (`CursedPlagueBellMovementAbility`) : `On(TurnStart_Other=0x13) & OwnerIsActor` ->
    #    `AddEffect(CursedPlagueBell_ExtraMove 1073, turns=Nullable(1))` sur
    #    `UnitsWithoutTrait(UnitsWithTrait(SurroundingFriends(Owner, ContagionsOfNurgleRange(Owner)),
    #    Chaos), Stationary)` = les allies Chaos non-Stationary du disque d'aura Contagion (centre
    #    exclu).
    #  * ATTAQUE (`CursedPlagueBellAttackAbility`, case-224 item 5) : `On(9=Attack) &
    #    (OwnerIsTarget|OwnerIsAlive) & !CasterIsTarget & CurrentAttackDamageProfilesContain(Psychic)
    #    & AreEnemies(Actor,Owner) & HasTrait(Actor,Psyker) & IsInContagionsOfNurgleRange &
    #    !CurrentAbilityIs(this)` -> `AttackWithAttackDamage(Actor -> Actor, Direct(dmg[lvl porteur]),
    #    Psychic, nrOfHits)` : le psyker ennemi qui porte une attaque Psychic DANS l'aura se blesse
    #    lui-meme. Cf. loki/cursed_plague_bell.py.
    "CursedPlagueBell": [CursedPlagueBellMovementAbility, CursedPlagueBellAttackAbility],
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
    # `FleshmetalGuns` porte DEUX abilities natives distinctes (deux slots voisins de la table de
    # pointeurs de methodes) : la ROTATION turn-start (`FleshMetalGunsAbility`) et le volet TILE-EFFECT
    # (`FleshMetalGuns_TileEffectAbility`, `On(0x10=DamageDealt)` -> DespoiledGround sur la tuile de la
    # victime pendant le round WarpHail, #85). Le gate `HasEffect(Self, 0x4c5)` du second rend
    # l'inscription inconditionnelle INERTE hors round WarpHail.
    "FleshmetalGuns": [FleshmetalGunsRotationAbility, FleshmetalGunsTileEffectAbility],
    # TerrifyingCrescendo (passif emperNoiseMarine << Shiron >>) = ACCUMULATION du stack de l'effet 1424
    # (deja porte #204, magnitude x level) : disjonction `On(0=UnitDeath) & OwnerIsActor & TargetIsOverkilled`
    # | `On(0x3d=PreEffectAdded) & OwnerIsActor & TriggeringEffectIs(1065=Pinned)` -> `AddEffectOrIncreaseLevel(
    # 1424, +1, max=buffMaxLevel=6)`. Cf. loki/terrifying_crescendo.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateBehaviour).
    "TerrifyingCrescendo": [TerrifyingCrescendoOverkillAbility, TerrifyingCrescendoSuppressAbility],
    # FuelledByFury (passif ultraTitus << Titus >>) = ACCUMULATION du stack de l'effet 1323 (magnitude
    # x level portee en meme temps, `entities/effects/loki/extra_damage.py`) : `On(0xe=UnitPostAbility)
    # & AreFriends(Owner, caster) & HasTrait(caster, 0x10=Hero) & !HasTrait(caster, 0x419=MachineOfWar)
    # & IsActiveAbilityCountedAsUsed(false)` -> `If(HasEffect, IncreaseEffectLevel(+1, SANS cap),
    # AddEffect(1323))`. Cf. loki/fuelled_by_fury.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ExtraDamageAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ExtraDamageAbility$$CreateBehaviour).
    # + volet REVIVE (#88 residu A1) : `FuelledByFury_ReviveAbility` = `On(3=PendingDeathAdded) &
    # HasEffect(self, 1324 actif) & AreEqual(caster, self) & TriggeringAbilityIs(1024=FinalJustice)` ->
    # `Revive(self, self, ConfigVar('hp'), healType=0, sourceId=1251)`. Le passif porte les DEUX
    # triggered-abilities (l'`ArraySet` du marqueur 1324 n'enregistre, lui, que ses 3 triggers d'etat).
    "FuelledByFury": [FuelledByFuryExtraDamageAbility, FuelledByFuryReviveAbility],
    # AnvilShield (passif spaceRockfist << Arjac >>) = volet ON-BLOCK `ApplyIce` : `On(UnitBlocked=0x3c) &
    # OwnerIsTarget & IsUnit(caster)` -> `AddEffect(Ice=0x11, source=Self, cible=CasterTile)` (la tuile de
    # l'attaquant BLOQUE gele). L'effet de tuile Ice etait deja porte ; c'est le DISPATCH `On(0x3d)` qui
    # manquait. Volets Stun / FrozenAttackerAdvantage / init-effects = residus documentes.
    # Cf. loki/anvil_shield.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateBehaviour ; emetteur IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers).
    # #100 : les DEUX autres volets on-block sont desormais portes (ils etaient du dead-code faute de
    # leurs prerequis) — `ApplyStun` (`On(0x3d) & IsMeleeAttack & (HasEffect(1200)|HasEffect(1201))` ->
    # Stunned sur l'attaquant) et `FrozenAttackerAdvantage` (`On(0x2a=PreUnitAbility) & IsNormalAttack &
    # IsUnitOnTileWithEffect(caster, Ice)` -> +20 % block chance transitoire).
    "AnvilShield": [AnvilShieldApplyIceAbility, AnvilShieldApplyStunAbility,
                    AnvilShieldFrozenAttackerAdvantageAbility],
    # --- #95-RESTE2 : chaine SwornProtector -> Kell -> ListenUpMaggots ---------------------------
    # SwornProtector (passif `astraCreed`, triggered 1050) = `On(PreUnitAbility=0x2a)` : a la PREMIERE
    # attaque ennemie visant Creed, Kell (`astraSmnKell`) apparait sur un hex libre adjacent et prend
    # sa place (TriggerAbility -> SwornProtector_Protect). Cf. loki/sworn_protector.py.
    "SwornProtector": [SwornProtectorSummonKellAbility],
    # SwornProtector_Protect (passif `astraSmnKell`, triggered 1075) = MEME event : a chaque attaque
    # suivante visant Creed, Kell re-echange sa position avec lui et encaisse.
    "SwornProtector_Protect": [SwornProtectorProtectSwitchAbility],
    # HazeOfCorruption (passif `deathBlightlord` << Maladus >>, triggered 1076) = MEME event
    # `On(PreUnitAbility=0x2a)`, gate `get_OwnerIsCaster` SEUL : a l'entree de CHAQUE ability du
    # porteur, `HazeOfCorruption_TargetFinderAbility$$CreateBehaviour` resout
    # `PickRandomly(Damageable(AdjacentEnemies(Self) & AdjacentFriends(Target)), 2)` -- donc
    # `min(len(pool), 2)` `genrand_int32` AVANT tout coup -- et bonde les relais (effet 1077).
    # C'etait la source des 2 tirages manquants de case-207. Cf. loki/haze_of_corruption.py.
    # case-209 : le passif porte un SECOND volet, `HazeCorruption_BonusHitAbility` (orthographe
    # native SANS le « Of ») -- `On(PreUnitDeath=1) & OwnerIsActor & IsDead(Target) & !IsDead(Owner)
    # & !TriggeringEffectIs(0x435)` -> 1 coup `extraDmg` profil Toxic sur la cible qui vient de
    # tomber, dont le degat DEBORDE integralement vers le relais bonde (l'effet 1077 ci-dessous).
    "HazeOfCorruption": [HazeOfCorruptionTargetFinderAbility, HazeCorruptionBonusHitAbility],
    # MartialSuperiority (passif `templChampion` << Brother Jaeger >>, triggered 0x444=1092) = MEME
    # event `On(PreUnitAbility=0x2a)` : quand Jaeger est CIBLE d'une attaque de MELEE pendant le tour
    # ADVERSE, il frappe l'attaquant 2x profil Power AVANT que l'attaque ne s'execute
    # (`MartialSuperiorityAbility$$CreateTrigger`/`$$CreateBehaviour`, cible = `Actor@0x158` ==
    # `$$GetInitialTarget`). Si la riposte TUE l'attaquant, le gate acteur-mort POST-`On(0x2b)` de
    # `ActiveAbilityOperation$$ExecuteInternal` annule l'attaque entrante. Cf. loki/martial_superiority.py.
    "MartialSuperiority": [MartialSuperiorityRiposteAbility],
    # ListenUpMaggots (passif `astraSmnKell`, triggered 1063) = `On(AbilityInit=0x21)` : pose l'effet
    # 0x426 sur Kell, qui ecrit `+1 nrOfSummons` / `+3 range` sur son PARENT (Creed) via
    # `AddUnitActiveAbilityModification` -- SEULE source non nulle de `GetAbilityStatModification`.
    "ListenUpMaggots": [ListenUpMaggotsAddEffectAbility],
    # --- Genestealer Cults : les 2 passifs HERO restants du parc GS ------------------------------
    # CosmicHorror (passif `genesPatriarch` << The Patermine >>) = DEUX abilities natives distinctes :
    #   * `On(0x36=UnitDefeated) & OwnerIsActor & AreEnemies & NOT HasTrait(Steppable)` -> decoy sur la
    #     tuile du mort + `Foreach(ennemis de l'anneau, Maybe(chance){ TriggerAbility(BattleFatigue)
    #     & If(IsAlive, AddEffect(Pinned 1065)) })` -- UN SEUL Maybe pour les DEUX volets (le << 60 %
    #     et 60 % >> de l'i2 est de la prose : le decompile n'a qu'un tirage par victime) ;
    #   * `On(0x35=PostUnitKill) & OwnerIsActor & AreFriends & HasTrait(Decoy)` -> `Heal(self, hp)`
    #     (le << marcher sur un decoy >> est en realite le CRUSH du decoy, qui passe par
    #     `KillUnitOperation$$Execute` -> `On(0x36)`).
    # Cf. loki/cosmic_horror.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnKillAbility$$CreateTrigger /
    # ...$$CreateBehaviour / IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnMoveAbility$$CreateTrigger).
    "CosmicHorror": [CosmicHorrorOnKillAbility, CosmicHorrorOnMoveAbility],
    # SpiritualLeader (passif `genesMagus` << Xybia >>) = `On(0x1c=ArrivedAtFinalTile) & OwnerIsActor`
    # (fin d'activation : apres son 1er move, OU cloture de tour si elle n'a pas bouge -- les DEUX
    # emetteurs natifs de 0x1c) -> decoy sur la meilleure tuile adjacente libre, puis si >=2 decoys
    # adjacents (le neuf COMPTE, DSL lazy) summon d'un Neophyte sur l'un d'eux tire au hasard.
    # Cf. loki/spiritual_leader.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpiritualLeaderAbility$$CreateTrigger /
    # ...$$CreateBehaviour / ...$$GetAdjacentDecoys).
    "SpiritualLeader": [SpiritualLeaderAbility],
    # RealityUnbound (passif `thousTzaangor` << Yazaghor >>) = DEUX volets, DEUX classes natives,
    # DEUX events -- le passif accorde les deux :
    #   * `RealityUnboundAbility` : `On(9=Attack)` & >=3 ennemis DISTINCTS ayant recu du Psychic ce
    #     tour & `Not(HasEffect(self, 1205))` -> +extraMovement MOVEMENT (1205) et +extraRange
    #     EXTRA_RANGE (1206), 1 tour. Son `CreateTrigger` est un fold ICF vers
    #     `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$GetTrigger` (parametre
    #     par l'effectType 0x4b5) -- MEME corps que WeaverOfFate, aucune parente.
    #   * `RealityUnboundExtraMaxDamageAbility` : `On(0x42=FinalDamage)` &
    #     `HasTakenDamageOfDamageProfileThisTurnAmountOfTimes(target, Psychic, times=1)` (EGALITE
    #     STRICTE = 1re instance seulement = « each DIFFERENT enemy ») & `AreEnemies` ->
    #     +extraMaxDmg EXTRA_MAX_DAMAGE (1207, EMPILABLE), 1 tour.
    # Cf. loki/reality_unbound.py + entities/effects/loki/reality_unbound.py.
    "RealityUnbound": [RealityUnboundAbility, RealityUnboundExtraMaxDamageAbility],
    # TimeFlux (passif `thousTerminator` << Toth >>) -- le natif derive DEUX triggered-abilities du
    # MEME passiveAbility, et ce registre en est le mirror :
    #   * `TimeFluxAbility` (REGEN) : `OwnerIsActor & On(0x13=TurnStart_Other)` -> `Heal(self,
    #     Min(Sum(hpToHeal, LastHitDamageTakenLastTurn(self)), maxHpToHeal))` -- loki/time_flux.py ;
    #   * `TimeFluxReviveAbility` = `GhostReviveAbility(effectType=1186)` (POSE DU GHOST, #213) :
    #     `OwnerIsActor & On(0x1f=PreUnitMove) & OwnerIsCaster` -> `If(<4 gates>, Nothing(),
    #     AddEffect(1186, source=self, targets=CurrentTurnStartTile(self)))` -- loki/ghost_revive.py.
    "TimeFlux": [TimeFluxRegenAbility, GhostReviveAbility],
    # BarbedOvipositor (passif `tyranParasite` << Parasite of Mortrex >>) = `On(0=UnitDeath) &
    # OwnerIsActor & AreEnemies & Not(IsObjectOrSteppable(target)) & Not(TriggeringAbilityIs(
    # TriggeredAbilityType.ItsGonnaBlow=1080)) & Not(HasTrait(target, 5=Mechanical))` -> `Spawn(owner,
    # PickRandomly(CanAddUnit(Tiles(target)),1).Otherwise(PickRandomly(CanAddUnit(AdjacentTiles(
    # target)),1)), "tyranSmnRipperSwarm", WithStatsFromConfig)` : chaque kill QUALIFIANT du Parasite
    # pose un Ripper Swarm sur l'hex du mort. Aucun cap de summons dans l'arbre natif, AUCUNE
    # on-appearance (le Ripper n'attaque PAS a l'apparition -- contraste l'actif `ItItches`).
    # Cf. loki/barbed_ovipositor.py (IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$CreateTrigger /
    # ...$$CreateBehaviour).
    "BarbedOvipositor": [BarbedOvipositorSummonAbility],
    # FabricatorClawArray (passif `necroSpyder` << Canoptek Spyder >>, triggered 0x3ee = 1006) =
    # `On(0x1c=ArrivedAtFinalTile) & OwnerIsActor & !AmountIsZero(GetTargetSelector())` ->
    # `Repair(Owner, GetTargetSelector(), Direct(ConfigVar(0x24 = hpToRepair)), ForRepair)`, ou
    # `GetTargetSelector` = `PickRandomly(Repairable(UnitsAffectedByHealType(AdjacentFriends(Owner,1,3),
    # 1), 0,1,3), 1).Otherwise(PickRandomly(UnitsWithNegativeEffects(<le meme filtre heal-type>), 1))`.
    # RESIDU N20 de #299 : le Spyder qui bouge PUIS repare restaurait, cote port, la SEULE reparation
    # active -- mesure natif 10457 vs port 6025, ecart 4432 = hpToRepair[50] 2216 x mult 200 %.
    # Cf. loki/fabricator_claw_array.py (IdunBattleLogic.Entities.Abilities.Active.Loki.FabricatorClawArrayAbility$$CreateTrigger /
    # ...$$CreateBehaviour / ...$$GetTargetSelector).
    "FabricatorClawArray": [FabricatorClawArrayAbility],
    # RelentlessMarch (passif `necroWarden` << Makhotep >>, `TriggeredAbilityType` 0x3ec = 1004 --
    # HOMONYME d'id avec `ActiveAbilityType` 1004 `MortisRound`, #328) :
    # `On(TurnStart_Other=0x13) & <DSLTriggers+0x28 = IsTurnOf(Owner)>` ->
    #   `AddEffect(0x3f3 RelentlessMarch_Effect, turns = Nullable<int>(1))` sur
    #   `UnitsWithoutTrait(Friends(AdjacentUnits(Owner)), 0x418 Stationary)`
    # + `Repair(Owner, Friends(AdjacentUnits(Owner)), Direct(hpToRepair[lvl]), ForRepair)`.
    # ⚠ Le filtre `Stationary` ne porte QUE sur la cible de l'`AddEffect` -- le `Repair` recoit
    # l'arbre NON filtre (la fiche #317 disait l'inverse ; lu au desassemblage des deux call-sites).
    # Les allies NON mecaniques sont ecartes de la reparation par le gate `EntityCanBeRepaired` de
    # l'Operation, pas par un selecteur. Branche `triggerType == Custom` (exclusion des HEROS) portee
    # mais SANS appelant cote port tant qu'`AdaptiveStrategy` (1005) n'est pas dans `ABILITY_CLASSES`.
    # Cf. loki/relentless_march.py + `docs/rl/case-328-relentless-march.md`.
    "RelentlessMarch": [RelentlessMarchAbility],
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

# --- Registre : relicAbility → triggered-ability(s) accordée(s) ------------------------------------
# QUATRIEME chemin de registration (#317), et il est DISTINCT des trois autres : une RELIQUE accorde
# une triggered-ability sans passer ni par `traits`, ni par `passiveAbilities`, ni par
# `activeAbilities`. Deux formes cote natif :
#   * `gameconfig.units.<kind>.<id>.relicAbilities` -- la relique EN DUR sur l'unite. 25 abilities
#     du build sont dans ce cas, TOUTES sur des npc (mesure : `probe_317_repair_callers_inventory.py`) ;
#   * l'item relique EQUIPE par le joueur (`items[*].abilityId` + `allowedUnits`), materialise dans
#     `BattleConfiguration.Units[].TertiaryAbility` -- 4 unites sur 175 du seed BC en portent une.
# **SEULE la premiere forme est lue ici** : le rail COMBAT derive du gameconfig, et la lecture fidele
# du kit declenche REEL (RPC `unitAbilityStates`, `engine/ai/context.py::live_triggered_ability_ids`)
# n'existe que cote DECISION. Gap NOMME, mesure par `probe_193_move_playbook_inventory.py` volet 2.
#
# Registre SEPARE de `ABILITY_TRIGGERS` a dessein : aucune des 25 relicAbilities n'y figure, donc un
# registre distinct rend la double-inscription STRUCTURELLEMENT impossible.
RELIC_ABILITY_TRIGGERS: dict[str, list[type[TriggeredAbility]]] = {
    # DawnBlade (relique `R_Crit_DawnBlade` de `tauFarsight` ; en dur sur les 5 npc `*Farsight`),
    # `TriggeredAbilityType` 0x5dd = 1501. `DawnBlade_HealAbility` : `On(0=UnitDeath) & OwnerIsActor
    # & IsDefeatedByMeleeAttack(Targets@0x60)` -> `Repair(self, self, Get(hpToHeal[lvl]), ForRepair)`.
    # ⚠ LE NOM MENT : l'artefact est un `DSLBehaviors$$Repair`, pas un `$$Heal` -- et la variable lue
    # s'appelle `hpToHeal` (`AbilityVariableType` 0x20). Cf. loki/dawn_blade.py.
    # La 2e classe native du meme id (`DawnBlade_InitAbility`, qui pose l'effet 1501
    # `DawnBlade_ExtraDmg`) n'est PAS portee : elle ne construit aucun `Repair` (#317, hors perimetre).
    "DawnBlade": [DawnBladeHealAbility],
}

# --- Registre : abilities GLOBALES (aucun owner) ---------------------------------------------------
# Les abilities `IdunBattleLogic.Entities.Abilities.Damage.Loki.*` ne sont portees par AUCUNE unite :
# leur `CreateTrigger` ne teste que le PROFIL DU COUP, jamais un owner (`get_OwnerIs*` absent). Elles
# sont donc inscrites UNE SEULE FOIS pour la bataille -- une inscription par entite les ferait firer N
# fois par evenement, ce que la mesure live REFUTE (exactement UN `NextBool` par serie de coups pour le
# canal 1203, oracle = etat MT). Cf. `core.collect_global_triggers`.
#
#   OnFireDamageAbility  (1016) : On(0x10) & DamageProfileHasTrait(1 = OnFire)  & !TriggeringEffectIs(5)
#                                 -> AddEffect(5 = Fire, Tiles(Target()))            [INCONDITIONNEL]
#   OnToxicDamageAbility (1203) : On(0x10) & DamageProfileHasTrait(4 = OnToxic) & !TriggeringEffectIs(0x4dc)
#                                 -> If(IsFirstHitInSeries & Maybe(chance=25), AddEffect(0x4dc))
#
# Le 3e membre de la famille, `OnMeltaDamageAbility` (1211), n'a PAS de `CreateTrigger` dans ce build
# (`case-72-onmelta-dead-code.md`) : DEAD-CODE, volontairement absent de ce registre.
GLOBAL_TRIGGERS: list[type[TriggeredAbility]] = [
    OnFireDamageAbility,
    OnToxicDamageAbility,
]

# --- Registre : effectType → effet-trigger(s) ------------------------------------------------------
# ⚠ La valeur est une LISTE : cote natif, `BaseEffect.CreateHandleTriggerAbilitiesInternal` renvoie un
# **`ArraySet`** (N `Triggered(trigger, behaviour)` par effet) — ex. `PhoenixGem_CanReviveEffect
# IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal` en enregistre DEUX. Un dict 1->1 ne pouvait pas les porter.
EFFECT_TRIGGERS: dict[int, list[type[EffectTrigger]]] = {
    # 1009 : le trigger de TIR (`CreateTargetTrigger`, On(4)) + les TROIS `Triggered()` de
    # `IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` qui
    # pilotent `EffectComponent.IsActive @+0x5c` de l'instance (activation au tour adverse, desactivation
    # au tour du porteur, desactivation des que le porteur attaque = « un seul tir par activation »).
    OVERWATCH_AUTO_ATTACK: [OverwatchAutoAttack,                      # On(4)    -> le TIR
                            RangedAutoAttackActivateOnTurnStart,      # On(0x12) -> ActivateEffect
                            RangedAutoAttackDeactivateOnTurnStart,    # On(0x12) -> DeactivateEffect
                            RangedAutoAttackDeactivateOnAttack],      # On(10)   -> DeactivateEffect
    # HazeOfCorruption_DamageTransfer 0x435=1077 (case-209, bond pose par le target-finder de #207) :
    # `IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTrigger` =
    # `(OnDeath & (TriggeringAbilityIs(0x435) | AreEqual(Actor, bonded)) | On(0x2e) | On(0x35))
    # & IsAlive(bonded) & AreEqual(Target, EffectSource)` -> le RELAIS encaisse, de la part du
    # porteur, chaque `LeftOverDamage` que la cible initiale a gaspillee.
    HAZE_DAMAGE_TRANSFER: [HazeOfCorruptionDamageTransferTrigger],
    CONTAMINATED_TILE: [ContaminatedTileEffect],  # tile-effect : enter(4)+tick(0x12) -> pose Contaminated_Unit
    FIRE_TILE: [FireTileDoT],                     # tile-effect : tick(0x14) -> DoT 20% PV initiale a l'occupant
    # DespoiledGround 0x5c4=1476 (#85) : MEME patron que le feu — `EnvDespoiledGroundTileAbility`
    # (`On(0x14) & Count(EntitiesWithAnyEffect(0x5c4))>0`) inflige a l'occupant non-immune un degat
    # tire dans [DespoiledGroundMinDmgPct, DespoiledGroundMaxDmgPct] % de sa PV MAX (profil
    # DirectDamage), puis pose 1478 (+%degat vs Xenos/Imperial) si l'occupant est Chaos a SON tour.
    DESPOILED_GROUND_TILE: [DespoiledGroundTileDoT],
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
    # DEUX triggers de RETRAIT du marqueur (case-89 volet B3) : `On(0x2d=UnitRevived) & OwnerIsTarget &
    # CurrentAbilityIs(PhoenixGem=0x5b2)` et `On(0x2e=UnitResurrected) & OwnerIsTarget`.
    PHOENIX_GEM_CAN_REVIVE: [PhoenixGemReviveAbility,                # 1451 (self-revive, even-if-overkill)
                             PhoenixGemRemoveMarkerOnRevive,         # On(0x2e) -> RemoveEffect(1451)
                             PhoenixGemRemoveMarkerOnResurrect],     # On(0x2f) -> RemoveEffect(1451)
    # FuelledByFury_CanRevive 1324 (#88 A1, marqueur POSE PAR LE JEU a l'init d'ultraTitus -- donc capte
    # tel quel par le snapshot live) : l'`ArraySet` d'`IdunBattle.Entities.Effects.Loki.
    # FuelledByFury_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal` n'enregistre QUE les 3
    # triggers qui pilotent son etat ACTIF (`EffectComponent.IsActive @+0x5c`) -- l'ability de revive,
    # elle, est portee par le PASSIF (`ABILITY_TRIGGERS["FuelledByFury"]`). Contraste PhoenixGem : ici
    # c'est une DESACTIVATION (once-per-TURN, re-armee au tick 0x12), pas un retrait definitif.
    FUELLED_BY_FURY_CAN_REVIVE: [FuelledByFuryCanReviveActivateOnAbilityInit,    # On(0x21) -> Activate
                                 FuelledByFuryCanReviveActivateOnTurnStart,     # On(0x12) -> Activate
                                 FuelledByFuryCanReviveDeactivateOnRevive],     # On(0x2e) -> Deactivate
    # AnvilShield_FrozenAttackerAdvantage (#100, effet 0x4b1=1201 pose par le volet `On(0x2b)`) : son
    # SEUL trigger propre est `IdunBattle.Entities.Effects.Loki.AnvilShield_FrozenAttackerAdvantageEffect
    # $$CreateTargetTrigger` = `On(0xe=UnitPostAbility) & AreEqual(target@0x178, EffectSource(this))` ->
    # le bonus +20 % block ne vit QUE le temps de l'ability qui l'a declenche (ground truth live).
    ANVIL_FROZEN_ADVANTAGE: [AnvilShieldFrozenAdvantageExpire],      # 1201 -> conso a UnitPostAbility
    # InspiredToGreatness_OverrideLevel (#114 residu 2, effet 1180 pose par l'active 1082 de tauAunShi
    # sur l'allie `canReset`) : son SEUL trigger est celui que `BaseEffect$$CreateHandleTriggerAbilities`
    # greffe quand `CreateRemoveEffectTrigger` est non nul --
    # `InspiredToGreatness_OverrideLevelEffect$$CreateRemoveEffectTrigger` = `On(0xc) & OwnerIsCaster`
    # -> `BaseEffect$$GetRemoveEffectBehaviour` = `RemoveEffect(<cette instance>)`. Borne l'override de
    # `ACTIVE_ABILITY_LEVEL` au PROCHAIN CAST D'ACTIF du porteur.
    ITG_OVERRIDE_LEVEL: [InspiredToGreatnessOverrideLevelRemove],    # 1180 -> retrait On(0xc)
    # Chronometron_ExtraDamage (residu R9, effet 1550 pose par l'active 1226 de `necroChronomancer` sur
    # chaque ennemi du disque rayon 2) : meme greffe generique que 1180 --
    # `Chronometron_ExtraDamageEffect$$CreateRemoveEffectTrigger` = `On(9) & OwnerIsTarget &
    # IsUnit(caster) & AreFriends(caster, EffectSource)` -> `RemoveEffect(<cette instance>)`. C'est ce
    # qui fait du +degat une CHARGE A USAGE UNIQUE (consommee au 1er coup d'un allie du Chronomancer),
    # et non un buff persistant. Cf. loki/chronometron.py.
    CHRONOMETRON_EXTRA_DAMAGE: [ChronometronExtraDamageRemove],      # 1550 -> retrait On(9)
    # EarlyWarningOverride_ReactivateOverwatch (#114 residu 3, effet 1145 pose par l'active 1077 de
    # tauCrisis) : `AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal` rend un ArraySet
    # de DEUX `Triggered()` -> DEUX classes. (1) `On(1=PreUnitDeath) & OwnerIsActor & NOT IsTurnOf(owner)
    # & AmountIsGreater(Max(Ranged,Melee AttackHits), hitsReduction) & LegitDeathReasons` ->
    # `ActivateEffect(1009) & AddStaticStatModifierEffect(1146, EXTRA_HITS, -hitsReduction,
    # TurnsUntilUnitOwnerTurn)` ; (2) `(On(0)|On(0x11)) & NOT HasEffect(owner,1009,onlyActive)` ->
    # `RemoveEffect(1146)`. Cf. loki/reactivate_overwatch.py.
    EWO_REACTIVATE_OVERWATCH: [EarlyWarningOverrideReactivateOverwatch,   # 1145 -> re-entree + -1 coup
                               EarlyWarningOverrideHitReductionPurge],   # 1145 -> purge du 1146
    # TimeFlux_Revive 1186 (#213) -- le time-ghost de `thousTerminator`, effet dont le PORTEUR est une
    # TUILE. SIX entrees : le `CreateTargetTrigger`/`CreateTargetTriggerBehaviour` de `GhostEffect`
    # (la resurrection NON in-place, `OnPreDeath(ignoreOverkill=1) & AreEqual(EffectSource, target)`)
    # + les CINQ `Triggered()` de son `CreateHandleTriggerAbilitiesInternal`, qui sont la « condition
    # de disparition » de l'i2. Cf. loki/ghost_revive.py pour les arbres in extenso.
    GHOST_EFFECT: [GhostEffectRevive,                    # On(1)    -> Revive(tiles=Owner) + RemoveEffect
                   GhostRemoveOnSourceMoves,             # On(0x1f) -> le poseur rebouge
                   GhostRemoveOnUnitAdded,               # On(0x33) -> une autre unite APPARAIT dessus
                   GhostRemoveOnUnitEnters,              # On(0x24) -> une autre unite ARRIVE dessus
                   GhostRemoveOnSourceDeathInactive,     # On(0)    -> poseur mort, effet INACTIF
                   GhostRemoveOnSourceRemoved],          # On(0x25) -> poseur retire du plateau
}
