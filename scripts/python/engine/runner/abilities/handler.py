"""Registre d'abilities + handler (visiteur) du `ActiveAbilityMessage`.

`AbilityHandler` route un `ActiveAbilityMessage` vers la classe d'ability correspondante
(`ABILITY_CLASSES[ability_type]`) et exécute sa behaviour-seq (mirror `AActiveAbility.Execute` →
`<Ability>.ExecuteBehaviour`). C'est le point d'entrée du wiring : `Runner.apply(ActiveAbilityMessage)`
→ l'engine DÉRIVE les effets/mutations de l'ability. Ability non portée → no-op (dégradation fidèle,
comme un effet non porté = BaseEffect).

Il mirror les GATES d'`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` qui precedent
l'execution : le gate ACTEUR-MORT (#70) puis le GATE DE CIBLE (#115, `IsInvalidTarget` — filtre
generique + regle dynamique par ability, cf. `targeting.py`). Un refus = no-op COMPLET : ni
behaviour, ni `AddFlagsAfterAbilityExecution` (donc `actionConsumed = false` cote natif).

#120 — LES VECTEURS D'OPERATION `On(0x2a = PreUnitAbility)` / `On(0xe)`. Le natif emet `PreUnitAbility (0x2a)` depuis
UN SEUL site, `ActiveAbilityOperation$$ExecuteInternal`, et l'attaque NORMALE emprunte cette MEME
operation (elle EST une active ability :
`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility`). Le port, lui, a DEUX
portes d'operation — `DamageHandler.visit_AttackUnitMessage` (damage.py) et ce visiteur — et seule la
premiere emettait : FORK de port (1 site natif -> 2 sites offline dont 1 muet). Les DEUX emettent
desormais, au MEME rang relatif que le natif. Sequence native mesuree au decompile
(`ExecuteInternal`, ordre des `FUN_1800280e0(0x4d, .., <event>)` par adresse croissante) :

    IsDeadUnitAndNotAllowedByAbility(target)  -> return 0
    IsInvalidTarget(caster, casterTiles, target) -> return 0
    GetAbilityEntities(...)
    On(0x2a = PreUnitAbility)                        <- AVANT toute execution (donc avant tout degat / calcul de block)
    if (!options@0x4a && IsUnit(caster) && IsDead(caster)) return 0
    ... execution de la behaviour ...
    On(0xb)   UnitAbility           <- INCONDITIONNEL, apres l'execution ; consommateur : 1319 LegacyOfCombat (#928)
    On(0xc)   UnitActiveAbility     (aucun consommateur porte)
    AddFlagsAfterAbilityExecution(...)
    On(0xe)   UnitPostAbility

DIVERGENCE D'ORDRE ASSUMEE ET NOMMEE : le port place le gate ACTEUR-MORT (#70) AVANT `0x2b`, alors
que le natif le place JUSTE APRES. Consequence theorique : un cast issu d'un caster deja mort emet
`0x2b` cote natif et pas cote port. Les deux voies du port sont alignees entre elles sur ce point
(l'attaque normale gate aussi en tete, damage.py), et #70 a ete valide live sur l'observable
« attaquant mort = no-op complet » ; on ne le deplace pas ici sans mesure dediee.
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from .base import ActiveAbility
from .targeting import is_invalid_target
from .loki import (ThunderousAssaultAbility, ScarabHiveAbility,
                   ScarabSummonAbility, GetEmRuntzAbility, CrushingClawsAbility, ValkyrieStrikeAbility,
                   PlasmaGrenadeAbility, StikkbombAbility, FragstormAbility, ScythingTalonsAbility,
                   SpiritLeechAbility, ArmoriumCherubAbility, DoctrinaImperativesAbility,
                   MV71SniperDroneSquadAttackAbility, MasterOfTheTutelariesAbility,
                   StormcallerAbility, TheQuickeningAbility, BlackRageAbility,
                   GauntletsOfUltramarAbility, AberrantHypermorphAbility, CordClawAbility,
                   SorcerousFacadeAbility, WallOfMirrorsAbility, PsychicMaelstromAbility,
                   UnstoppableMomentumReworkedAbility, FoulInfusionAbility,
                   MightFromBelowAbility, LeadingTheChargeAbility, MindControlAbility,
                   AttemptedPossessionAbility, BioMinefieldAbility)
from .loki.healing_balms import HealingBalms_HealAbility        # #966 (1212, `spaceWolfPriest`)
from .loki.reveal import RevealAbility                          # #1033 (1107, `eldarNpc2Warlock`)
from .genestealer import (CultDemagogueAbility, HeroicFusilladeAbility, VigilanceEternalAbility,
                          TwistedScience_HealAbility)
from .deathguard import (RevitalizingMalignancyAbility, FlailSwingAbility, SpawnPoxwalkersAbility,
                         EntropyCannonsAbility, PlagueburstMortarAbility, PlagueWindAbility,
                         MortarionsPlagueWindAbility, ReapingScytheAbility,
                         BlightGrenadesAbility)
from .thousandsons import (AetherStrideAbility, DoomboltAbility, HeavyWarpFlamerAbility,
                           HellfyreMissileRackAbility, SlashingDiveAbility, InfernalCannonAbility)
from .blacklegion import (BringerOfDespairAbility, IncursionAbility, HadesAutocannonsAbility,
                          DaemonicOrdnanceAbility, FrenziedFiringAbilityCombat,
                          DrachnyenAbility, HeraldOfTheApocalypseAbility)
from .orks import (WaaaghAbility, SquigLaunchasAbility, SquigMineAbility, DakkaDakkaDakkaAbility,
                   RammingSpeedAbility, GrotTankAbility, ExplosivePresentsAbility)
from .darkangels import (PlasmaCannonAbility, DarkTalonStrikeAbility, DeathOnTheWindAbility,
                         HailstrikeAbility, SuperchargeAbility, ExemplarOfHateAbility,
                         CalibaniteGreatswordAbility, TheLionsWrathAbility,
                         MartialExemplarAbility, SternguardFocusAbility)
from .ultramarines import (CombatRestorativesAbility, MortisRoundAbility, DeathFromAboveAbility,
                           MacroPlasmaIncineratorAbility, TacticalPrecisionAbility,
                           DutyEternalAbility, StormOfWrathAbility, HellfireShellsAbility)
from .custodes import (MartialInspirationAbility, MomentShackleAbility,
                       TalonsOfTheEmperorAbility, VexillaMagnificaAbility)
from .bloodangels import (SavageEchoesAbility, HammerOfWrathAbility, LightOfSanguiniusAbility,
                          BloodChaliceAbility)
from .necrons import (AdaptiveStrategyAbility, HarbingerOfDestructionAbility,
                      ResurrectionOrbAbility, ChronometronAbility,
                      MultiThreatEliminatorAbility, TunnelingHorrorAbility,
                      NanoscarabRepairProtocolsAbility, ReanimationBeamAbility,
                      StormOfFlensingBladesAbility)
from .sisterhood import (SanctorumMissileAbility, SkyStrikeAbility, DevastatingRefrainAbility,
                         ThriceBlessedConflagrationAbility, BrazierOfHolyFireAbility,
                         RitesOfRestorationAbility)
from .tau import (HeavyRailRifleAbility, TwinSmartMissileSystemAbility, FightingRetreatAbility,
                  EarlyWarningOverrideAbility, InspiredToGreatnessAbility,
                  SeekerMissileFrequencyLockAbility, ExemplarOfTheKauyonAbility,
                  ExemplarOfTheMontkaAbility, NovaShieldAbility, NovaBoostAbility,
                  NovaChargeAbility, ForwardObserversAbility)
from .votann import (IronkinSteeljackAbility, AugmentedAssaultAbility, GravitonRifleAbility,
                     AncestralFortuneAbility, MassDriverAcceleratorAbility)
from .aeldari import (EmpyricAmbushAbility, ExecutionerAbility, FireAndRepositionAbility,
                      HarvesterOfSoulsAbility, KissOfDeathAbility, SilentDeathAbility,
                      SwoopingHawkAbility, WarConstructAbility)
from .spacewolves import RitesOfMorkaiAbility                        # 1211 (spaceWolfPriest Baldr)
from .spacewolves import (GreatFrostAxeAbility, FoehammerAbility, GrapnelLauncherAbility,
                          WarHowlAbility)
from .tyranids import (SporeMineLauncherAbility, AlphaWarriorAbility, FearOfTheUnseenAbility,
                       BurrowersAbility, ItItchesAbility, CatalystAbility,
                       StranglethornCannonAbility, CallRipperSwarmsAbility)
from .worldeaters import (BloodyFuryAbility, JakhalStimmsAbility, KillMaimBurnAbility,
                          MurderousSwingAbility, OverwhelmingWrathAbility)
from .admec import (SentinelDirectivesAbility, RadBombardmentAbility,
                    DefendTheDivineWorkAbility, ArcScourgeAbility,
                    InvocationOfMachineVengeanceAbility, SolarAtomizerAbility)
from .repair import RepairAbility, Repair_GalvanicFieldAbility
from .heal import HealAbility                                   # #931-r1 (18, trait `Healer`)
from .astramilitarum import (SupremeCommanderAbility, SendInTheNextWaveAbility,
                             MalleusRocketLauncherAbility, ForwardSpotterAbility,
                             FragBombAbility, BasiliskBarrageAbility)
from .emperorschildren import (DaemonicPatronsAbility, DoomSirenAbility, EuphoricStrikesAbility,
                               ExcruciatingFrequenciesAbility, LashOfTormentAbility)
from .blacktemplars import (CrusadeOfWrathAbility, FragstormGrenadeLauncherAbility, HolyDuelAbility,
                            IncendiaryShellsAbility, UnbreakableDutyAbility)
from .astartes import StrikeFromTheShadowsAbility, TitanhammerSquadAbility
from ..components import is_alive_and_not_fled
from ..components import unit_is_dead, MachineComponent
from ..messages import ActiveAbilityMessage
from ..operations.active_ability import (execute_for_replaced_target, get_tiles,
                                                 resolve_replaced_target)
from ..operations.active_ability import is_dead_unit_and_not_allowed_by_ability
from .base import sets_end_turn_flags_for, sets_active_ability_used_flag_for
from ..operations.triggers.base import _is_ranged_position
from ..operations.triggers.dispatch import ability as ability_dispatch

# Registre ActiveAbilityType (int) -> classe d'ability portée. À ÉTENDRE au roster.
ABILITY_CLASSES: dict[int, type[ActiveAbility]] = {
    ThunderousAssaultAbility.ABILITY_TYPE: ThunderousAssaultAbility,   # 1043 (validé live)
    ScarabHiveAbility.ABILITY_TYPE: ScarabHiveAbility,                 # 1007 ScarabHive (summoner necroSpyder, validé live)
    ScarabSummonAbility.ABILITY_TYPE: ScarabSummonAbility,             # 1047 ScarabSummon (auto-dédoublement du scarab)
    GetEmRuntzAbility.ABILITY_TYPE: GetEmRuntzAbility,                 # 1045 GetEmRuntz (summoner orksRuntherd -> grots)
    GrotTankAbility.ABILITY_TYPE: GrotTankAbility,                     # 1057 GrotTank (orksBigMek Orks : UN `Execute(Spawn(Caster@0x48, Target@0x60, unitId, opts))` TILE-TARGET, opts portant `StatModifierFormula(Health, Initial, summonHp + RoundsStarted(Caster) x extraHp)` en +0x28 et `PerformAIAttackFromCurrentPosition(ActiveTarget@0x68)` en +0x18 -- #570)
    CrushingClawsAbility.ABILITY_TYPE: CrushingClawsAbility,           # 1105 (Tyrant Guard : attaque+Taunt+Suppress+splash)
    ValkyrieStrikeAbility.ABILITY_TYPE: ValkyrieStrikeAbility,         # 1018 (airstrike différé — EXCLUT le sur-tir générique)
    PlasmaGrenadeAbility.ABILITY_TYPE: PlasmaGrenadeAbility,           # 1098 (splash Plasma adjacent-cible)
    StikkbombAbility.ABILITY_TYPE: StikkbombAbility,                   # 1051 (splash Blast adjacent-cible)
    FragstormAbility.ABILITY_TYPE: FragstormAbility,                   # 1078 (splash Blast pick-random <=4)
    ScythingTalonsAbility.ABILITY_TYPE: ScythingTalonsAbility,         # 1065 (splash Bio adjacent-both)
    SpiritLeechAbility.ABILITY_TYPE: SpiritLeechAbility,               # 1104 (Neurothrope : attaque Psychic config + Suppress ; lifesteal #94)
    ArmoriumCherubAbility.ABILITY_TYPE: ArmoriumCherubAbility,         # 1014 (Vindicta : 4x Flame ranged + feu + passif FireOfAbsolution)
    CultDemagogueAbility.ABILITY_TYPE: CultDemagogueAbility,           # 1179 (Isaak : pose decoys + summon Neophytes moitié + tour AI immédiat)
    HeroicFusilladeAbility.ABILITY_TYPE: HeroicFusilladeAbility,       # 1180 (Judh : move + 6x Projectile splash cible+voisins + crit-per-free-hex)
    DoctrinaImperativesAbility.ABILITY_TYPE: DoctrinaImperativesAbility,  # 1118 (Tan Gi'da : toggle Protector<->Conqueror ; Protector +FixedArmor self)
    MV71SniperDroneSquadAttackAbility.ABILITY_TYPE: MV71SniperDroneSquadAttackAbility,  # 1076 (Sho'syl : summon drone + attaque commandee + Markerlight, #61bis)
    WallOfMirrorsAbility.ABILITY_TYPE: WallOfMirrorsAbility,           # 1186 (Stealth Battlesuit T'au : vol sur l'anneau dist==2 d'une cible Markerlight + attaque normale a +extraPierce, #433-r4-r1-r1)
    MasterOfTheTutelariesAbility.ABILITY_TYPE: MasterOfTheTutelariesAbility,  # 1096 (Abraxas : effet 1197 + summon Pink Horror tile-target + Screamer sur Psychic, #202-C)
    StormcallerAbility.ABILITY_TYPE: StormcallerAbility,               # 1113 (Njal : glace zone cible+ring1 + 3x Psychic ennemis-sur-glace + stun Flying, #217)
    PsychicMaelstromAbility.ABILITY_TYPE: PsychicMaelstromAbility,     # 1027 (Sibyll astraPrimarisPsy : 1 coup garanti + 4 jets 75/50/25/10 -> 1..5 coups Psychic mono-cible, #490)
    BioMinefieldAbility.ABILITY_TYPE: BioMinefieldAbility,             # 1144 (Bio-minefield tyranBiovore : UN Execute = AddEffect(BioMinefield_Target 1315 sur la cible, source=Owner, 1 tour) & If(Count(Alive(ChildrenOf(Owner))) >= nrOfSummons, then = PerformAIMovement(les mines non-Taunted_BlockMovement, 1 tuile, utilite 62 IMPOSEE) & Kill(les mines adjacentes a un ennemi, sur ELLES-MEMES = l'explosion), else = Spawn(nrOfSummons_2 mines tyranSmnSporeMine sur des tuiles libres adjacentes a la CIBLE)). L'audit la classait SUMMON : le summon n'est que la branche `else`. #939)
    MightFromBelowAbility.ABILITY_TYPE: MightFromBelowAbility,         # 1165 (The Patermine genesPatriarch : TROIS Execute -- Group(5x Psychic Pierce100 NoBlocking sur la cible adjacente, Ability_Attack) puis KillDeadUnits(UnitsDamagedThisPhase) puis IfAlive(Group(Spawn genesSmnGenestealer sur CHAQUE decoy ami adjacent + attaque IA immediate sans move, Ability_Summon)) -- les tuiles sont evaluees APRES l'attaque, donc le decoy pose par CosmicHorror sur un kill compte, #501)
    TheQuickeningAbility.ABILITY_TYPE: TheQuickeningAbility,  # 1151 (Mephiston : teleport-echange tile-target + free melee attack faction-BloodAngels, #217)
    BlackRageAbility.ABILITY_TYPE: BlackRageAbility,                   # 1163 (Lucien bloodDeathCompany : setHealth 30% + 3 self-buffs + charge + attaque normale, #217)
    GauntletsOfUltramarAbility.ABILITY_TYPE: GauntletsOfUltramarAbility,  # 1000 (ultraCalgar : AoE 2 bandes adjacent 2 coups + surrounding r=2 Unobscured 1 coup, case-220 P0-DAMAGE)
    AberrantHypermorphAbility.ABILITY_TYPE: AberrantHypermorphAbility,  # 1166 (Biophagus genesBiophagus : summon genesSmnAberrant tile-target hex libre adjacent + attaque a l'apparition, case-220 P0)
    VigilanceEternalAbility.ABILITY_TYPE: VigilanceEternalAbility,     # 1202 (Tyrith custoKyrus : charge gap-close + attaque melee Power mono-cible 3 hits, #220)
    TwistedScience_HealAbility.ABILITY_TYPE: TwistedScience_HealAbility,  # 1167 (`genesBiophagus` "Hollan" GenestealerCults HERO -- l'active que le PASSIF `TwistedScience` (1278) SUBSTITUE au `18 Heal` du trait `Healer` (`...TwistedScienceAbility$$CreateBehaviour` = `RemoveActiveAbility(Owner, 18) & AddActiveAbility(Owner, 1167, abilityState)`, sur `On(AbilityInit) & OwnerIsActor`). `Execute( If( NOT HasEffect(Target, 1355 TwistedScience_ExtraHp, onlyActive=false, Both) AND NOT OwnerIsTarget, AddDynamicStatModifierEffect(Target, source=Owner, 1355, StatType.Health, AbilityStateReference, turns=null) + ChangeStat(Target, Health, Add, ConfigVar(TwistedScience, Owner, hp)) + If( HasFaction(Target, Genestealers, OnlyAliveAndTargetable), AddEffect(1356 TwistedScience_ExtraDmg, AbilityStateReference, source=Owner, Target, PERMANENT) ) ) + Heal(Caster, Target, HealAbility.HealAmount(dsl), ForHeal()) )` -- le SOIN est hors du `If`, donc inconditionnel ; masque 0x8402 = TargetMatchesDynamicRule|TargetIsFriendly|CasterIsPossibleTarget, range `TargetingRange` statics+0x00 = RANGE_ADJACENT_IF_MELEE_CASTER ; regle dynamique NEUVE (une cible alliee NON marquee est valide MEME a PV pleins) ; #931)
    HealingBalms_HealAbility.ABILITY_TYPE: HealingBalms_HealAbility,   # 1212 (`spaceWolfPriest` "Baldr" SpaceWolves HERO -- l'active que le PASSIF `HealingBalms` (1502) SUBSTITUE au `18 Heal` du trait `Healer` (`...Triggered.Loki.HealingBalmsAbility$$CreateBehaviour` = `AddFlag(Owner, 0x17 CanHealFullHealthUnits) + RemoveActiveAbility(Owner, 18) + AddActiveAbility(Owner, 1212, abilityState)`, sur le trigger d'INIT partage `<DSLTriggers+0x30>`). `Execute( RemoveEffect(Target, 1503) + RemoveEffect(Target, 1504) + AddDynamicStatModifierEffect(Target, source=Owner, 1503, CriticalDamage, TurnsFromRounds(ConfigConst(HealingBalms, nrOfRounds))) + AddDynamicStatModifierEffect(Target, Owner, 1504, CriticalChance, idem) + AddEffect(1508 HealingBalms, Caster, Target) + Heal(Caster, Target, HealAbility.HealAmount(dsl), ForHeal()) )` -- arbre PLAT, aucun `If` : les buffs partent meme sur un self-cast ; masque 0x8402, range `TargetingRange` statics+0x00 = RANGE_ADJACENT_IF_MELEE_CASTER ; regle dynamique = `IsAffectedByHealType` SEUL, donc valide a PV PLEINS ; #966)
    CordClawAbility.ABILITY_TYPE: CordClawAbility,                     # 1122 (Exitor-Rho admecRuststalker : 4x DirectDamage melee + self-buff coups additionnels 2 tours, case-220)
    RevitalizingMalignancyAbility.ABILITY_TYPE: RevitalizingMalignancyAbility,  # 1037 (deathRotbone : heal self+allies adj non-Imperial, split trait Chaos regular/chaos-cumul, case-220)
    FlailSwingAbility.ABILITY_TYPE: FlailSwingAbility,                 # 1042 (deathBlightlord DeathGuard : 3x Power melee mono-cible + InformWeapon no-op ; residu overkill flag, case-220)
    FoulInfusionAbility.ABILITY_TYPE: FoulInfusionAbility,             # 1038 (Pestillian deathPutrifier DeathGuard HERO, SELF-CAST : AddEffect(1074 FoulInfusion_ExtraHits, 2 rounds) sur UnitsWithTrait(SurroundingFriends(Caster, ContagionsOfNurgleRange(Owner)), Chaos) + Caster, PUIS UseNormalAttack(Caster, PickRandomly(Attackable(AdjacentEnemies(Caster)), 1)) -- l'attaque libre beneficie DEJA du buff ; #500)
    MindControlAbility.ABILITY_TYPE: MindControlAbility,               # 1164 (Magus genesMagus GenestealerCults HERO -- le cast NE FRAPPE PAS (categorie EFFECT/BUFF CONFIRMEE, aucun AttackWithAttackDamage / UseActiveAbility / Spawn dans l'arbre) et n'est PAS un owner-swap : Execute( AddEffect(1349 MindControl_OutoingDamageReduction -> Target, TurnsFromRounds(2)) & AddEffect(1350 MindControl_IncomingDamageBonus -> Target, meme duree) & If( NOT HasTrait(Target, 25 Immune), Inform(0xcb Custom_Unit_Id, cache) & If(cache, AddBondEffect(27 Taunted_OnlySpecificTargets -> Target, bonde au cache) & AddBondEffect(1367 MindControl_Taunter -> cache, bonde a Target)) ) ) ou cache = Cache(First(SortByFormula(Attackable(Friends(Owner, AdjacentUnits(Target))), StatAmount(It, HEALTH), ascending=0), 1)) = l'ALLIE DU CASTER adjacent a la cible a la plus haute Health COURANTE ; masque 0x4002 MIGRE depuis `TARGETING_OPTIONS_UNPORTED` ; regle dynamique NEUVE (1164 n'etait dans AUCUNE des deux tables : le port rendait 0 = permissif) -- `GetAdjacentUnits(targetTiles, friendsOf=caster, ignoreSteppables=false)` non vide, le predicat du `FilterInPlace` restant illisible (corps dedupliqué) -> residu #552-r2 ; #552)
    AttemptedPossessionAbility.ABILITY_TYPE: AttemptedPossessionAbility,  # 1101 (Thaumachus thousSorcerer ThousandSons HERO -- le cast NE FRAPPE PAS LUI-MEME mais fait FRAPPER la cible : c'est un OWNER-SWAP TRANSITOIRE, LU (`AttemptedPossession_PossessedEffect$$ApplyInternal` = `processor.ChangeUnitOwner(target, bondedEntity)` (slot 127), `$$RevertInternal` = `processor.ResetUnitOwner(target)` (slot 128)) -- contre-exemple exact de 1164 MindControl, ou le swap est REFUTE. Execute( AddBondEffect(1209 AttemptedPossession_Possessed -> possedes, bondedEntity=Caster, turns=Constant(1)) + AddStatOverrideEffect(1210 AttemptedPossession_DmgOverride, ATTACK, min(maxDmg, dmgPct% x StatAmount(It, ATTACK, INITIAL)), isHidden) + PerformAIAbility(possedes, overrideMovement=ConditionalAmount(HasTrait(Actor, Summon), StatAmount(Actor, MOVEMENT), 0), utilityEntity=Owner, customUtility=GetAttackCustomUtility) + RemoveEffect(1210) & RemoveEffect(1209) ) ou possedes = UnitsWithoutTrait(If(HasTrait(Target, Immune), Alive(Children(Target)), Target + Alive(Children(Target))), Object) ; masque 0x200004002 (preset +0x180 = 0x4002, flags 0x200000002) MIGRE depuis `TARGETING_OPTIONS_UNPORTED` ; regle dynamique NEUVE (double refus : cible Immune sans enfant vivant, ou cible sans enfant ET sans cible d'attaque preferee) ; #590)
    BringerOfDespairAbility.ABILITY_TYPE: BringerOfDespairAbility,     # 1022 (Angrax blackTerminator : 4x Power cible melee + 4x Power ennemi random adjacent-CASTER, splash factory attack, case-220 BL)
    FrenziedFiringAbilityCombat.ABILITY_TYPE: FrenziedFiringAbilityCombat,  # 1036 (Volk blackObliterator BlackLegion : AtomicGroup(op_Addition( SetCache(hitsNode) & Attack(cible, hits=Min(Cache(nrOfHits + #tuiles-adjacentes-marchables-sans-ennemi), maxNrOfHits)), SetCache(hitsNode) & Attack(AdjacentEnemies(TargetTile,1), hits=Direct(1), multi) )) ; famille ATTACK, HeavyRound ranged ; case-61 volet AoE COMBAT)
    PlasmaCannonAbility.ABILITY_TYPE: PlasmaCannonAbility,             # 1150 (darkaTerminator DarkAngels : 3x Plasma cible + 3x sur <=2 unites tirees directly-behind, native_factory attack, case-220)
    CombatRestorativesAbility.ABILITY_TYPE: CombatRestorativesAbility,  # 1002 (ultraApothecary : heal self+allies adj, split trait Imperial hpToHeal_2 / non-Imperial hpToHeal, PAS de cumul, case-220 P0-HEAL)
    MortisRoundAbility.ABILITY_TYPE: MortisRoundAbility,               # 1004 (ultraEliminatorSgt : AtomicGroup(Attack HeavyRound 1x + PushUnit cible 1 hex) ; wiring valide ; quirk HeavyWeapon double = residu cross-cutting non porte, case-220 UM)
    InfernalCannonAbility.ABILITY_TYPE: InfernalCannonAbility,         # 1209 (`thousDaemonPrince` « Z'Kar » ThousandSons, cast TILE-TARGET hors pool -> catalog_inject : `AttackWithAbilityDamage( caster = Owner@0x30, target = Unique( UnitsOnTilesWithEffect(Enemies(AllAliveUnits), 5 Fire) + FromTrigger(Enemies(AllAliveUnits), HasTakenDamageOfDamageProfileThisTurn(ActiveTarget@0x68, damageProfile_2 = Psychic), 0) ), hits = GetHits = nrOfHits 3, profil Flame )` PUIS `AddEffect(5 Fire -> la TUILE visee, surcharge 5-args donc source = NULL, duree par defaut)` ; masque 0x46000040 = TargetIsTile|AllowObscuredByElevation|AllowObscuredByWalls|AllowNullCasterTile, RANGE_WHOLE_BOARD ; #605)
    AetherStrideAbility.ABILITY_TYPE: AetherStrideAbility,             # 1208 (`thousNpcMowDaemonPrince` ThousandSons MoW npc, cast TILE-TARGET : `RemoveMachine(Caster@0x48) & Spawn(ThreeTileUnitSpawnShape(Target@0x60), "thousSmnDaemonPrince", spawn_as_single_unit)` -- une unite a 3 PIEDS. Sous-behaviour on-appearance = `op_Addition( AddTrait(ActiveTarget, 0x418 Stationary) & If(ActorHasTriggeredAbility(Owner@0x30, 0x5d8 CabalOfSorcerers), AddTriggeredAbility(ActiveTarget, 0x5d8)), If(Count(UnitsWithTrait(AdjacentFriends(ActiveTarget, 1, 3), 0x3ea Psyker, 3)) > 0, PerformAIAttack(ActiveTarget)) )`. MEME patron que 1158 DutyEternal, mais transfert de triggered ability par ID FIXE en DSL (pas par reflection sur le caster) + terme `PerformAIAttack` absent de 1158 ; masque 0x20000040000042 = TargetMatchesDynamicRule|TargetIsTile|AllowNullCasterTile|CasterIsMachine, RANGE_WHOLE_BOARD ; #1022)
    HellfireShellsAbility.ABILITY_TYPE: HellfireShellsAbility,         # 1080 (`ultraSmnHeavyIntercessor` SUMMON d'ENVIRONNEMENT + 2 npc `ultra*HeavyIntercessor*` : `If( HasTrait(Target@0x60, 0x3f9 BigTarget), AttackWithAttackDamage(hits = nrOfHits + extraHit), AttackWithAttackDamage(hits = nrOfHits) )` -- deux `AttackDamageBehaviour` DISTINCTS, famille ATTACK, profil `Piercing`, `MinMaxDamage(minDmg/maxDmg)` ; masque 0x4002 MIGRE depuis `TARGETING_OPTIONS_UNPORTED` ; face DECISION deja portee par #173 ; #605)
    StormOfWrathAbility.ABILITY_TYPE: StormOfWrathAbility,             # 1019 (ultraTigurius : ExecuteAtomic(ChainAbilityDamage) -- 1 coup Psychic famille ABILITY sur la cible puis <= maxAdjacentTargets sauts vers un ennemi TIRE AU SORT adjacent a un maillon deja frappe ; coup DIFFERE d'un cran, cf. case-499)
    DeathFromAboveAbility.ABILITY_TYPE: DeathFromAboveAbility,         # 1003 (ultraInceptorSgt : spawn ultraSmnInceptor x StatAmount(TURNS_STARTED) tuiles adjacentes-cible SortByDistance(caster) cap-tuiles + on-appearance attaque normale Bolter cible, template SpawnSummon, case-220 UM)
    SavageEchoesAbility.ABILITY_TYPE: SavageEchoesAbility,             # 1230 (Cezare bloodTerminator : 4x Eviscerate melee + extraDmg x free-tiles + self-heal si HP<=50%, case-220 template ArmoriumCherub)
    HarbingerOfDestructionAbility.ABILITY_TYPE: HarbingerOfDestructionAbility,  # 1008 (necroPlasmancer : cible + N-1 ennemis random disque rayon-2 CASTER unobscured, 1x DirectDamage pierce-100, case-220 Necrons)
    ResurrectionOrbAbility.ABILITY_TYPE: ResurrectionOrbAbility,       # 1009 (necroOverlord Anuphet Necrons : SUMMON PUR (aucun revive) — Spawn(PickRandomly(CanAddUnit(AdjacentTiles(caster)), Min(Count(amis LivingMetal morts/ressuscites) + TURNS_STARTED(caster), 6)), necroSmnWarrior, WithStatsFromConfig), Execute plain, #116)
    ChronometronAbility.ABILITY_TYPE: ChronometronAbility,             # 1226 (necroChronomancer Thothmek Necrons : Foreach(SurroundingEnemies(caster, range=2), If(HasTrait(It, Summon), AddEffect(Stunned), AddEffect(Pinned)) & AddEffect(Chronometron_ExtraDamage)) ; porteur hors seed BC -> catalog_inject, #116)
    MultiThreatEliminatorAbility.ABILITY_TYPE: MultiThreatEliminatorAbility,  # 1006 (necroDestroyer Imospekh Necrons : ChainLeftOverHitsAttackDamage 6 coups Gauss + report des coups gaspilles (+extraHit par kill) sur l'ennemi adjacent-derniere-cible & disque rayon-2 caster unobscured, #116)
    IncendiaryShellsAbility.ABILITY_TYPE: IncendiaryShellsAbility,     # 1044 (templNeophyte SUMMON / templNpc2Neophyte NPC, Black Templars : ExecuteAtomic(GroupType 0x51, InformWeapon(Flame, isMelee 0) & AttackWithAttackDamage(Caster, Target, RandomAmount(minDmg, maxDmg), Flame, nrOfHits=3, selectionType=OnlyTargetable)) ; attaque RANGEE mono-cible NUE -- ni splash, ni report, ni effet ; #907)
    FragstormGrenadeLauncherAbility.ABILITY_TYPE: FragstormGrenadeLauncherAbility,  # 1048 (templAggressor « Brother Burchard » Black Templars : ChainLeftOverHitsAttackDamage 6 coups Blast sur la cible, extraHits NULL, report des coups gaspilles sur Damageable(SurroundingEnemies(Owner, range 2) - Target) trie PV croissants puis SortTargetsByDamagePredictionSelector (priorite aux kills), #489)
    CrusadeOfWrathAbility.ABILITY_TYPE: CrusadeOfWrathAbility,         # 1049 (templHelbrecht « High Marshal Helbrecht » Black Templars : AddStatic(0x43e CrusadeOfWrath_ExtraDamage, ATTACK, +extraDmg) & (AddStatic(0x43f CrusadeOfWrath_ExtraPierce, EXTRA_PIERCE_MELEE 0x15, +extraPierceRatio) + If(Count(ValidNormalAttackTargets(CasterTile) & AdjacentEnemies(Caster)) > 0, UseActiveAbility(Owner, PickRandomly(., 1), UnitNormalAttackType(Owner)))) ; les DEUX buffs vont sur Friends(SurroundingUnits(CasterTile, range 2, includeCenter 0) - Caster) -- le caster ne se buffe PAS -- pour TurnsFromRounds(2) ; #893)
    HolyDuelAbility.ABILITY_TYPE: HolyDuelAbility,                     # 1050 (templChampion « Brother Jaeger » Black Templars : AddBondEffect(0x443 HolyDuel_Taunt -> la CIBLE, bondedEntity=Caster, PERMANENT) & UseActiveAbility(attaque NORMALE dirigee sur la cible) ; le composite 1091 pose ensuite les DEUX `Taunted` symetriques + 1092/1093 sur le champion)
    AdaptiveStrategyAbility.ABILITY_TYPE: AdaptiveStrategyAbility,     # 1005 (necroWarden « Makhotep » Necrons, ORDONNANCEUR et non buff : If(ActorHasTriggeredAbility(Caster, 1004 RelentlessMarch), TriggerAbility(Caster, 1004)) + AddStatOverrideEffect(allies adjacents NON-Hero, 1012 AdaptiveStrategy_DmgOverride, ATTACK = RandomAmount(minDmg, maxDmg)) + PerformAIAction(les memes, asGroup=0, resetTurnFlags=1) + RemoveEffect(TOUS les allies non-Hero VIVANTS, 1012) ; le cast ne frappe personne, le degat vient de l'action forcee ; #577)
    UnbreakableDutyAbility.ABILITY_TYPE: UnbreakableDutyAbility,       # 1061 (templAncient « Ancient Thoread » Black Templars : AddEffect(0x449 UnbreakableDuty_DamageReduction -> Owner, TurnsFromRounds(1), AURA -dmgReductionPct% projetee sur Owner + SurroundingFriends(range=2)) op_Addition If(Count(UnitsWithTraits(Friends(AllDeadOrResurrectedUnits), [Imperial, Hero])) >= 2, AddStatic(0x4e3 Health, +extraHp) + ChangeStat(Owner, Health, Add, +extraHp) + AddStatic(0x4e8 Attack, +extraDmg) + If(Count(ValidNormalAttackTargets(CasterTile) & AdjacentEnemies(Caster)) > 0, UseActiveAbility(Owner, PickRandomly(.., 1), Loki_NormalAttack))) ; #572)
    NanoscarabRepairProtocolsAbility.ABILITY_TYPE: NanoscarabRepairProtocolsAbility,  # 1224 (necroReanimator MACHINE OF WAR Necrons : AddEffect(0x609 NanoscarabRepairProtocols PERMANENT sur un allie mecanique NON marque) + AddDynamicStatModifierEffect(0x60a _ExtraHp, stat Health, hp[level]) + ChangeStat(Health, mode 2 Add, hp[level]) -- AUCUN Repair : le hpToRepair de 1224 est lu par l'EFFET 1545, pas par le cast ; #902)
    ReanimationBeamAbility.ABILITY_TYPE: ReanimationBeamAbility,       # 1223 (necroReanimator MACHINE OF WAR Necrons : Repair(hpToRepair) de TOUTES les machines alliees marquees 1545 + les SUMMONS marques agissent (PerformAIAction asGroup/forced) sous Attack OVERRIDE Min(maxDmg, Attack_Current x dmgPct%) puis retrait + AddEffect(0x60b ReanimationBeam_Revive, Actor, 1 round) ; #902)
    TunnelingHorrorAbility.ABILITY_TYPE: TunnelingHorrorAbility,       # 1011 (necroSmnDestroyer Necrons, cast TILE-TARGET : RemoveUnitFromItsTiles(Caster, true) -> le caster QUITTE le plateau (pos=null, alive=true) & RemoveAllForcedAttackTargets(Caster) & AddBondEffect(0x459 TunnelingHorror_PendingSummon -> la tuile visee, bondedEntity=Caster, PERMANENT) ; porteur summon SANS invocateur -> greffe sur un heros du pool ; #366-r1)
    BurrowersAbility.ABILITY_TYPE: BurrowersAbility,                   # 1023 (tyranSmnRipperSwarm + 5 tyranNpc2RipperSwarm* Tyranids, SELF-CAST : RemoveUnitFromItsTiles(Caster, true) -> le caster QUITTE le plateau (pos=null, alive=true) & RemoveAllForcedAttackTargets(Caster) & AddEffect(0x410 Burrowers_Hidden -> le CASTER, surcharge SANS source, PERMANENT) ; gate CASTER-dynamique `GetDynamicInvalidCasterReason` = casterTiles vide OU une tuile IsTemporary -> 4 ; 2e appelant de la primitive #366-r1, tranche 1 de `#366-r1-tunnel-family`)
    SanctorumMissileAbility.ABILITY_TYPE: SanctorumMissileAbility,     # 1062 (adeptMorvenn Morvenn Vahl Sisterhood : missile 2x Blast cible + 1x Blast adjacents-cible (hex Morvenn exclu) Unobscured, native_factory attack, case-220)
    IronkinSteeljackAbility.ABILITY_TYPE: IronkinSteeljackAbility,     # 1219 (votanMemnyr : summon votanSmnSteeljack hex libre adjacent-self + attaque a l'apparition, corps dedup IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour==AberrantHypermorph, case-220 Votann)
    AugmentedAssaultAbility.ABILITY_TYPE: AugmentedAssaultAbility,     # 1221 (votanBeserk Havyr : 4x Eviscerate melee mono-cible + AddDynamicStatModifierEffect(1541) FixedArmor NEGATIF sur la CIBLE, permanent, #113 Votann)
    GravitonRifleAbility.ABILITY_TYPE: GravitonRifleAbility,           # 1206 (votanIronmaster Vynn : 3x Physical range-2 + Stunned(1162) nrOfRounds ; owner-effect 1484 = +extraPierceRatio vs TerminatorArmour/MkXGravis/Mechanical, #113 Votann)
    AncestralFortuneAbility.ABILITY_TYPE: AncestralFortuneAbility,     # 1207 (votanUthar Uthar : self-buff +critChance(1485) & +blockChance(1486) 1 round, gates StatAmount(INITIAL)>0, puis 3x Plasma sur First(SortUnitsByDamageUtility(AdjacentEnemies)) ; reset persistent-data HORS perimetre, #113 Votann)
    MassDriverAcceleratorAbility.ABILITY_TYPE: MassDriverAcceleratorAbility,  # 1222 (votanChampion Kimm : CHARGE a splash -- AddStaticStatModifierEffect(1542) MOVEMENT sur owner + AdjacentFriends, MoveUnit(SortTilesByUtility MovementSuggestion), puis IfAlive(caster) 1x DirectDamage sur la cible + 1x Physical sur Alive(Cache(Enemies(AdjacentUnits(target)))), #525)
    ExecutionerAbility.ABILITY_TYPE: ExecutionerAbility,               # 1066 (Eldryon eldarFarseer Aeldari : Psychic ranged hits=RoundsStarted cible + si cible morte 1 ennemi random adjacent-cible, native_factory attack, case-220 §6.19)
    EmpyricAmbushAbility.ABILITY_TYPE: EmpyricAmbushAbility,           # 1232 (Lhykhis eldarLhykhis Aeldari, HORS CATALOGUE -> catalog_inject : FlyUnit(caster, First(SortTilesByUtility(Randomize(CanAddUnit(AdjacentTiles(cible)) - CasterTile), caster, 7))) & If(OwnerIsAlive, nrOfHits x Eviscerate melee mono-cible & AddEffect(1578 EmpyricAmbush -> la CIBLE, source = Owner, Direct(1) tour)) ; l'effet et son gate etaient portes par #589-r1-r1, la POSE manquait -> #589-r1-r1-r1)
    HarvesterOfSoulsAbility.ABILITY_TYPE: HarvesterOfSoulsAbility,     # 1067 (Maugan Ra eldarMauganRa Aeldari : ranged HeavyRound cible hits=If(HasMoved,2,3) + splash MinMaxDamage2 ennemis ring1-cible ∩ rayon-3 caster, native_factory attack, ExecuteAtomic, case-220 §6.19)
    RevealAbility.ABILITY_TYPE: RevealAbility,                         # 1107 (eldarNpc2Warlock Aeldari : LE CAST NE FRAPPE PAS -- UNE feuille `AddEffect(1219 Revealed, source=Caster@+0x48, targets=Target@+0x60, TurnsFromRounds(nrOfRounds))`. Gate DYNAMIQUE mirroré : refuse une cible deja Revealed, puis exige qu'elle ait DEFAIT >= 1 unite Aeldari AMIE du caster (`BattleQuery$$GetDeadUnitsKilledBy` -> `UnitComponent+0x108`). L'effet donne +extraDmgPct% aux attaques des Aeldari ENNEMIS du porteur. #1033)
    SwoopingHawkAbility.ABILITY_TYPE: SwoopingHawkAbility,             # 1064 (Aethana eldarAutarch Aeldari : VAGUE EN LIGNE -- `DiveAttackAbilityBase` : 3 tuiles `First(TilesBehindInLine(CasterTile, <tuile de contact de la cible>), 3)`, 1 coup `Piercing` par tuile aux montants `dmg[0..2]` (famille ABILITY, AUCUN crit), puis `MoveUnit` du caster sur la tuile DERRIERE la derniere cible touchee -- ou, si occupee, la tuile libre la plus proche d'elle (`ConditionalSelector`) ; `ExecuteAtomic(..., 0x2a)` ; #502)
    SlashingDiveAbility.ABILITY_TYPE: SlashingDiveAbility,             # 1091 (Screamer thousNpc2Screamer/thousSmnScreamer ThousandSons : la SECONDE heritiere de `DiveAttackAbilityBase` -- MEME code natif que 1064 (ctor FUSIONNE par IL2CPP, partage prouve au slot de methode runtime), seule la CONFIG change : profil `Power` (1064 : `Piercing`), `nrOfHits`=1, `dmg[0..2]` decroissants ; porteurs npc+summons, confrontee par le chemin de stats explicite `--explicit-stats thousNpc2Screamer:<palier>` ; #507)
    FireAndRepositionAbility.ABILITY_TYPE: FireAndRepositionAbility,   # 1063 (Calandis eldarRanger Aeldari : TROIS feuilles `op_Addition((atk + reset) + eff)` -- (1) `UseActiveAbility(Caster, Target, UnitNormalAttackType(Caster))` = l'attaque NORMALE dispatchee (la config 1063 n'a NI minDmg/maxDmg NI nrOfHits NI damageProfile), (2) `ResetMovement(Owner)` = elle recupere deplacement + activation, PAS son active, (3) `AddEffect(1110 FireAndReposition_ReduceDmg -> ELLE-MEME, source = Caster, TurnsFromRounds(1))` dont l'effet etait deja porte par #366-r1 ; #567)
    # --- #940 : gisement `[-D]` (la DECISION choisit, l'EXECUTION etait un NO-OP SILENCIEUX).
    KissOfDeathAbility.ABILITY_TYPE: KissOfDeathAbility,               # 1108 (Harlequin Player -- porteurs `eldarSmnHarlequin` SUMMON et `eldarNpc3Harlequin` npc ; summoner = `EnvFactionSummons:Aeldari`, une ability d'ENVIRONNEMENT rattachee a AUCUNE unite -> voie summon FERMEE, confronte par GREFFE (case-92 §5bis) : `ExecuteAtomic(((AddEffect(1044 Untargetable -> le CASTER, source Caster@0x48, options VIDES) & ChainAttackDamage(preselected = Target@0x60, jump = `lastTargets => Enemies(Caster, AdjacentUnits(lastTargets, 1, 3), 3)` ATTRIBUE PAR ICF au corps de StormOfWrath, maxTargets = ConfigVar(0x0 maxAdjacentTargets), dmg = Direct(GetVariableForLevel(0xb dmg)) -- mode `amount`, PAS de minDmg/maxDmg dans la config --, hits = Direct(GetHits()), chainOptions +0x12 = 1 differe)) & FlyUnit(Caster@0x48, First(SortTilesByUtility(`CanAddUnit(AdjacentTiles(Last(UnitsAttackedThisTurn(Caster), 1))) - CasterTile@0x50` .Otherwise(idem sur AtIndex(.,1)) .Otherwise(idem sur Target@0x60), Caster, 7 Tile), 1))) & RemoveEffect(1044, Caster@0x48), 0x2a)` ; l'atterrissage se LIT APRES la chaine -> `unitsAttackedThisTurn` entre dans `_LIVE_KEYS` et passe de `set` a `dict` ORDONNE)
    SilentDeathAbility.ABILITY_TYPE: SilentDeathAbility,               # 1068 (Jain Zar eldarJainZar Aeldari : CHAINE DE DEGAT -- nrOfHits=3 coups Piercing melee sur la cible ADJACENTE, puis nrOfTargets=3 rebonds `Cache(PickRandomly(AdjacentUnits(maillon precedent) & <cache ennemis> - deja frappes, 1))`, memes bornes/profil/coups a chaque maillon ; `Group(..., GroupType.DamageChain)` ; #497)
    SkyStrikeAbility.ABILITY_TYPE: SkyStrikeAbility,                   # 1025 (adeptCelestine Celestine Sisterhood : charge tuile libre adjacente (vole, sans reach) + attaque melee normale base Attack+extraDmg profil/coups arme melee, template VigilanceEternal, case-220)
    GreatFrostAxeAbility.ABILITY_TYPE: GreatFrostAxeAbility,           # 1089 (spaceWulfen : glace zone cible+ring1 + attaque melee 4x Piercing mono-cible ATTACK-family, case-220 SW)
    GrapnelLauncherAbility.ABILITY_TYPE: GrapnelLauncherAbility,       # 1090 (spaceHound Tjark SpaceWolves : PULL de la cible d'1 hex vers le caster (arc AVANT, GetMinimumTiles180Front) PUIS 1x Physical ranged (range 3) puis VOL du caster sur la tuile d'origine liberee (sinon une voisine libre au hasard) ; quirk cible-adjacente = knockback 20% maxHP, #366-r1 tranche 2)
    FoehammerAbility.ABILITY_TYPE: FoehammerAbility,                   # 1097 (spaceRockfist Arjac SpaceWolves : Stunned(1162) cible + 1x Power ranged, degat + extraDmg x Count(heros morts/ressuscites), ATTACK-family, case-226)
    WarHowlAbility.ABILITY_TYPE: WarHowlAbility,                       # 1106 (spaceBlackmane Ragnar SpaceWolves : BUFF D'EQUIPE board-wide, AUCUNE attaque -- AddEffect(0x4c6 WarHowl_ExtraDamage_Unstoppable, CreateSnapshot(abilityState), source=Caster@0x48, cibles=op_Addition(Owner, UnitsWithoutTrait(UnitsWithoutRangedWeapons(Friends(Owner, AllAliveUnits - Owner)), Summon)), turns=Get(1)) = 1 TOUR ; ni faction ni rayon ; l'effet accorde le trait 0x412 Unstoppable (ApplyInternal/RevertInternal -> AddTrait/RemoveTrait temporaires) et porte +extraDmg / +extraCritChance sur les attaques NORMALES de MELEE ; free action (1106 dans les DEUX inventaires de turn-flags) ; masque 0x8014 MIGRE depuis `TARGETING_OPTIONS_UNPORTED` ; case-366-r1 residu 6.3)
    RitesOfMorkaiAbility.ABILITY_TYPE: RitesOfMorkaiAbility,           # 1211 (spaceWolfPriest Baldr SpaceWolves : TROIS mecaniques -- AddEffect(0x5de RitesOfMorkai = le REVIVE one-shot, cibles = Cache(Owner + UnitsWithoutTrait(SurroundingFriends(Owner, range, unique, 3), 0x5 Mechanical, 3)), TurnsFromRounds(ConfigConst(0x45 nrOfRounds))) puis AddEffect(0x5f9 RitesOfMorkai_ExtraDamage sur Filter(<la MEME zone cachee>, HasTrait(ActiveTarget, 0x3f6 FinalJustice) | HasEffect(ActiveTarget, 0x5ae FinalVengeance_UnitEffect, onlyActive:0, Both))) puis If(AmountIsGreaterThanZero(<cibles>), UseNormalAttack(Owner, SortUnitsByDamageUtility(ValidNormalAttackTargets(Owner, Tiles(Owner)) & AdjacentEnemies(Owner, unique, 3), Owner, UnitNormalAttackType(Owner), UtilityDefinition(0x23 Damage), NormalAttackDamage(Owner), selectionType 0 = Any, hits null))) ; les DEUX AddEffect sont la surcharge 4-args -> `source` NULL, donc chaque cible est SA PROPRE source, l'`abilityState` restant celui du CASTER ; l'audit classe 1211 EFFECT/BUFF et rate l'attaque normale ; #906)
    HammerOfWrathAbility.ABILITY_TYPE: HammerOfWrathAbility,           # 1153 (bloodIntercessor Mataneo BloodAngels : Infiltrate self + CHARGE tuile libre adj-cible <=range + 2x Power cible & 1x Physical ennemis adj-cible, ABILITY-family, degat DOUBLE si effet 1332 actif (HP<=healthPct), case-226)
    LightOfSanguiniusAbility.ABILITY_TYPE: LightOfSanguiniusAbility,   # 1177 (bloodDante « Dante » BloodAngels : jumeau structurel de 1153 -- Infiltrate self (Direct(1) TOUR) + VOL (FlyUnit, PAS MoveUnit) sur la tuile libre adj-cible <=range, puis IfAlive(Owner) : nrOfHits coups Melta ATTACK-family sur la cible & AddEffect(1376 LightOfSanguinius -> cible + ennemis non-Steppable/non-Object a range_2 d'elle, TurnsFromRounds(nrOfRounds)) ; le debuff -dmgReductionPct% (DOUBLE si le defenseur est a <= healthPct% PV) vit dans `entities/effects/loki/damage_reduction.py::LightOfSanguiniusDmgReductionEffect` ; masque 0x102004032 MIGRE depuis `TARGETING_OPTIONS_UNPORTED` ; #510)
    BloodChaliceAbility.ABILITY_TYPE: BloodChaliceAbility,             # 1175 (bloodSanguinary « Sanguinary Priest » BloodAngels, UNIQUE porteur : TROIS mecaniques la ou l'audit n'en annoncait qu'une (`HEAL`) -- Execute(op_Addition(op_Addition( ChangeStat(GetTargets(), Position(HEALTH,0,0), mode **0 = SetAbsolute**, PercentageOf(StatAmount(It@0x68, HEALTH, MAXIMUM), ConfigConst(0x4f healthPct), **2 = Floor**)), AddEffect(1368 BloodChalice_HealOnAttack -> GetTargets(), source Owner@0x30, TurnsFromRounds(1)) ), AddStaticStatModifierEffect(GetTargets(), 1369 BloodChalice_ExtraPiercing, 0x15 ExtraPierceMelee, ConfigVar(0x3f extraPierceRatio), TurnsFromRounds(1), isHidden=0) )) ou GetTargets = UnitsWithoutTrait(AdjacentFriends(Caster) - MechanicalUnits(.), 0x19 Immune) ; le volet 1 n'est PAS un soin -- mode 0 = SET, un allie au-dessus de healthPct% REDESCEND ; masque 0xc02 MIGRE depuis `TARGETING_OPTIONS_UNPORTED`, regle dynamique MIGREE depuis `DYNAMIC_TARGET_RULE_UNPORTED` ; #576)
    SporeMineLauncherAbility.ABILITY_TYPE: SporeMineLauncherAbility,   # 1145 (tyranBiovore Biovore MoW Tyranids : spawn tyranSmnSporeMine sur tuile-cible directe WithStatsFromConfig, corps IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$ExecuteBehaviour = IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour MOINS on-appearance ; mine inerte offline FloatingDeath non porte, case-220 §6.16)
    AlphaWarriorAbility.ABILITY_TYPE: AlphaWarriorAbility,             # 1112 (tyranWingedPrime Winged Prime Tyranids : spawn tyranSmnWarrior sur tuile-cible WithStatsFromConfig + attaque a l'apparition, corps IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$ExecuteBehaviour = template IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour AberrantHypermorph ; gate IsInTeamSynapseRange live ABSENT, case-220 §6.16)
    ItItchesAbility.ABILITY_TYPE: ItItchesAbility,                     # 1121 (tyranParasiteOfMortrex Parasite of Mortrex Tyranids, cast TILE-TARGET adjacent sur une tuile a ENNEMI : COMPOSITE de cinq mecaniques -- AddEffect(0x429 Pinned) + DisplaceUnitInAdjacentDirection (push direction 3 `AdjacentVector`, MEME vecteur casterTile->tuile ciblee pour toutes les cibles, les steppables sont ECRASES) + Kill(DeadUnits) + ResetMovement(Owner) + Spawn(CanAddUnit(<tuiles liberees>, allowSteppable) -> tyranSmnRipperSwarm, on-appearance PerformAIAbility) ; TROIS Execute natifs (ExecuteAtomic 0x2a, Execute, Execute(Group 0x22)) ; face DECISION deja portee (playbook/noncomparable/it_itches.py) -- #550)
    CatalystAbility.ABILITY_TYPE: CatalystAbility,                     # 1032 (tyranBossHiveTyrantLeviathan « Hive Tyrant » Tyranids, SEUL porteur : SELF-CAST, buff d'equipe -- Execute(op_Addition(op_Addition( AddStaticStatModifierEffect(targets, 0x420 Catalyst_ExtraArmor_Effect, 0x10 FixedArmor, Direct(ConfigVar 0x1b extraArmor), Nullable(2)), AddStaticStatModifierEffect(targets, 0x422 Catalyst_ExtraBlockChance_Effect, 0x07 BlockChance, Direct(ConfigConst 0x2d blockChance), Nullable(2)) ), AddStaticStatModifierEffect(targets, 0x421 Catalyst_ExtraBlockDamage_Effect, 0x08 BlockDamage, Direct(ConfigVar 0x14 blockDmg), Nullable(2)) )) ou targets = Cache(Friends(Caster@0x48, UnitsFromFaction(AllAliveUnits@0x20, GetStringConstant(0x3d factionId) = "Tyranids", 3), 3) - Caster@0x48) ; le CASTER est EXCLU du buff ; duree = Nullable<int>(2) LITTERAL donc deja en TOURS ; masque STATIC-COPY preset +0x280 -> 0x8004 ; #890)
    StranglethornCannonAbility.ABILITY_TYPE: StranglethornCannonAbility,  # 1056 (tyranBossHiveTyrantLeviathan « Hive Tyrant » Tyranids, SEUL porteur : RANGED range 3, ExecuteAtomic(op_BitwiseAnd(op_BitwiseAnd( InformWeapon, AttackWithAttackDamage(Target@0x60, MinMaxDamage, nrOfHits=3) ), AttackWithAttackDamage(AdjacentUnits(Target@0x60, unique:1, 3), MinMaxDamage2, nrOfHits_2=1) ), 0x55 GroupType.StranglethornCannon_AtomicGroup) ; profil Blast ; le ring-1 est passe BRUT (aucun wrapper Enemies) -> FRIENDLY-FIRE sur les allies adjacents a la cible, et la cible principale est EXCLUE du splash ; masque PRESET+FLAGS preset +0x140 | 0x100000000 -> 0x100004002 (TargetIsNotAdjacent AJOUTE par le ctor) ; #890)
    CallRipperSwarmsAbility.ABILITY_TYPE: CallRipperSwarmsAbility,     # 1052 (tyranBossHiveTyrantLeviathan « Hive Tyrant » Tyranids, SEUL porteur : SELF-CAST, summon EN ATTENTE -- Execute(AddBondEffect(0x446 CallRipperSwarms_PendingSummon, AbilityStateReference, source = Caster@0x48, targets = First(SortByFormula(CanAddUnit(AllTiles@0x18), AverageDistance(ActiveTarget@0x68, Enemies(Caster@0x48, AllAliveUnits@0x20, 3)), ascending: FALSE), amount = ConfigConst 0x10 nrOfSummons = 4), bondedEntity = Caster@0x48, options = struct ZERO)) ; AUCUN spawn au cast -- le ripper apparait en PHASE 2 (CallRipperSwarms_PendingSummonEffect -> CallRipperSwarms_SpawnAbility) ; tri DESCENDANT donc les tuiles les PLUS LOIN de l'equipe adverse ; CanAddUnit surcharge 2-ARGS -> allowSteppable TOUJOURS vrai ; masque STATIC-COPY preset +0x280 -> 0x8004 ; #1032)
    BloodyFuryAbility.ABILITY_TYPE: BloodyFuryAbility,                 # 1129 (worldTerminator « Wrask » WorldEaters : ChainLeftOverHitsAttackDamage MELEE profil Chain, hits = Sum(nrOfHits, Min(extraHit x TotalTimesAttacked(Owner), maxNrOfHits - nrOfHits)) = SNOWBALL sur les attaques recues DANS LA BATAILLE (ActorStatisticsComponent+0x34, jamais reset), report des coups gaspilles sur Damageable(AdjacentEnemies(Owner) - Target) trie par SortTargetsByDamagePredictionSelector avec hits=Direct(1) LU au champ DSLFormulas+0x20 ; extraHitsAfterTargetKilled NULL ; #505)
    JakhalStimmsAbility.ABILITY_TYPE: JakhalStimmsAbility,             # 1131 (worldJakhal Macer WorldEaters : 4x Physical melee cible + AoE intersection AdjacentUnits(caster) & AdjacentFriends(target) + self-loss 25% PV courant (ChangeStat Subtract, Execute separe) ; free action ; native_factory attack, ExecuteAtomic 0x2a, case-220 §6.3)
    OverwhelmingWrathAbility.ABILITY_TYPE: OverwhelmingWrathAbility,   # 1141 (worldEightbound « Azkor » WorldEaters : patron 2-PHASES « pose d'effets seule » -- le cast NE FRAPPE PAS : Execute(op_Addition(op_Addition( AddEffect(1301 OverwhelmingWrath_RangeDmgReduction -> Caster, TurnsFromRounds(1)), AddBondEffect(27 Taunted_OnlySpecificTargets -> NormalUnits(AdjacentEnemies(Owner)), bonde au Caster, TurnsFromRounds(1)) ), AddBondEffect(1300 OverwhelmingWrath_PendingAttack -> Caster, bonde au Caster, options ZERO = duree DEFAUT) )) ; le 2x Eviscerate du kit vit dans la TRIGGERED 1237 OverwhelmingWrath_Attack, hors registre (residu #503-r1) ; masque 0x4000 MIGRE depuis `TARGETING_OPTIONS_UNPORTED` ; #503)
    MurderousSwingAbility.ABILITY_TYPE: MurderousSwingAbility,         # 1137 (worldExecutions Tarvakh WorldEaters : 1x Piercing melee sur TOUS les ennemis adjacents au CASTER (AdjacentEnemies(caster), self-centre), degat If(Count(set) > 1, MinMaxDamage, Sum(MinMaxDamage, extraDmg)) reevalue PAR CIBLE ; native_factory attack ; face COMBAT du gisement [-D], case-decision-noop)
    KillMaimBurnAbility.ABILITY_TYPE: KillMaimBurnAbility,             # 1132 (worldKharn Kharn WorldEaters : TROIS attaques melee enchainees -- nrOfHits x Piercing sur la cible, puis nrOfHits_2 x Eviscerate, puis nrOfHits_3 x Plasma ; chaque bande GARDE la cible tant qu'elle vit et se re-cible sinon par GetNextTarget = If(IsAlive(prev), prev, First(SortUnitsByDamageUtility(pool))) -- pool = AdjacentEnemies(caster) puis Unobscured(SurroundingEnemies(caster, range=2)) ; le tri CONSOMME un tirage RandomAmount(minDmg_2,maxDmg_2) ; native_factory attack, Group(0x20) x3 + ExecuteAtomic 0x2a ; face COMBAT du gisement [-D], #504)
    LeadingTheChargeAbility.ABILITY_TYPE: LeadingTheChargeAbility,     # 1204 (astraDreir « Dreir » AstraMilitarum : DEUX phases natives -- (1) Execute(AddEffect(1046 Infiltrate_UnitEffect -> Owner, Direct(1) tour) & MoveUnit(Caster, GetMoveTile())) ou GetMoveTile = First(SortTilesByUtility(TilesUnitCanMoveToChargeTarget(range=4), Caster, UtilityDefinition(UtilityBucket[WeightedUtility(33 MovementSuggestion), WeightedUtility(67 LeadingTheCharge_ChargeTile)]))) ; (2) ExecuteAtomic((SetCache(Cache(TimesAttackMadeThisTurn)) & IfAlive(Caster, AddStaticStatModifierEffect(1388 TemporaryStatModifier / StatType.ExtraPierce = extraPierceRatio x #allies vaincus) & nrOfHits=3 x Power sur Target)) & If(AmountIsGreater(TimesAttackMadeThisTurn, cache), Spawn(nrOfSummons astraSmnDeathRider sur First(SortByFormula(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(Caster)), 7, Owner), ConditionalAmount(HasAdjacentEnemies, 1, 0)), nrOfSummons), on-appearance = meme +ExtraPierce & PerformAIAttackFromCurrentPosition)) & RemoveEffect(Caster + Children(Caster), 1388), 0x2a Ability_AtomicGroup) ; native_factory attack ; masque 0x... MIGRE depuis `TARGETING_OPTIONS_UNPORTED`, regle dynamique MIGREE depuis `DYNAMIC_TARGET_RULE_UNPORTED` ; #508)
    SentinelDirectivesAbility.ABILITY_TYPE: SentinelDirectivesAbility,  # 1139 (admecDestroyer Sy-Gex AdeptusMechanicus : 1x Physical ranged cible + AddEffect Pinned/Suppressed, quasi-clone SpiritLeech sans heal/conditional, native_factory attack, ne finit pas le tour, case-220 §6.17)
    ArcScourgeAbility.ABILITY_TYPE: ArcScourgeAbility,                  # 1173 (admecBossBelisarius « Belisarius Cawl », BOSS npc AdeptusMechanicus : ChainBehaviour(preselected = Target, jump = AdjacentUnits(picked) - Caster puis UnitsWithoutTraits[Steppable,Object] avec PRIORITE Mechanical .Otherwise(Enemies), maxAdjacentTargets = 3, coup DIFFERE chainOptions+0x12) ; par maillon : If(AreEnemies, AttackWithAttackDamage(Particle, nrOfHits 3) + If(IsMechanical, AddEffect(1162 Stunned) + AddPersistentData("EffectLevel", +1)), AddPersistentData + Inform) ; en fin de cast la pile "EffectLevel" devient le niveau de 1365 MachineVengeance sur le CASTER (IncreaseEffectLevel si deja pose, AddEffect sinon) puis SetPersistentData(0) ; masque 0x4006 = TargetMatchesDynamicRule|CasterMatchesDynamicRule|TargetIsEnemy ; AbilityAttackType = 2 Others ; #894)
    InvocationOfMachineVengeanceAbility.ABILITY_TYPE: InvocationOfMachineVengeanceAbility,   # 1172 (admecBossBelisarius « Belisarius Cawl », BOSS npc AdeptusMechanicus : SPAWN puis BUFF, ne frappe pas -- Spawn(First(SortByRow(CanAddUnit(AllTiles@+0x18), sameColumnIsRandom 1, additionalSorting ConditionalAmount(HasTrait(Units(ActiveTarget@+0x68), 0x1b Steppable), Const(1), Const(0)), ascending 1), GetVariableForLevel(0x4f nrOfSummons)), unitId = GetStringConstant(0) = admecSmnTechpriest, WithStatsFromConfig) op_BitwiseAnd AddEffectOrIncreaseLevel(0x555 = 1365 MachineVengeance, source Owner@+0x30, targets MechanicalUnits(Friends(Caster@+0x48, AllUnits)), amount GetNumberConstant(0x73 effectLevel) = 1) ; masque 0x8000 = CasterIsPossibleTarget, isSelfCasting 1, range TargetingRange statics+0x60 = RANGE_SELF ; AbilityAttackType = 2 Others ; #1027)
    SolarAtomizerAbility.ABILITY_TYPE: SolarAtomizerAbility,            # 1174 (admecBossBelisarius « Belisarius Cawl », BOSS npc AdeptusMechanicus : NE FRAPPE PAS -- (a) TRANSFERT de 0x555 = 1365 MachineVengeance des AUTRES allies mecaniques vers le caster : AddPersistentData(AbilityOrEffect(0x496), Caster@+0x48, Get(literal #3759 AccumulatedEffectLevel), EffectLevel(EffectFromOwner(Cache(EntitiesWithAnyEffect(Friends(Caster@+0x48, AllUnits - Caster@+0x48), 0x555)), 0x555))) + RemoveEffect(cache, 0x555) + If(AmountIsGreater(pd, DSLFormulas+0x18 = 0), AddEffectOrIncreaseLevel(0x555, Caster, pd)) + SetPersistentData(0) ; (b) MARQUAGE d une bande de 2 lignes hex : AddEffect(0x55b = 1371 SolarAtomizer_PendingAttack, Caster) + AddEffect(0x55c = 1372 SolarAtomizer_PendingTarget, GetTargetTiles()) ; le degat vient au tour SUIVANT par la triggered 1297 ; masque 0x1000100042 = TargetMatchesDynamicRule|TargetIsTile|AllowSteppableUnit|CasterHas3Tiles, range CustomRange(2), GetDynamicInvalidTargetReason = IsValidLineStartTile (la tuile visee doit etre ADJACENTE a une tuile du caster) ; AbilityAttackType = 2 Others ; #1027)
    BrazierOfHolyFireAbility.ABILITY_TYPE: BrazierOfHolyFireAbility,   # 1041 (adeptCanoness Canoness Sisterhood : ConditionalAmount(HasTrait(cible, Daemon), nrOfHits_2=4, nrOfHits=2) coups Flame mono-cible native_factory attack & AddEffect(5 Fire -> TUILE de la cible, source = la tuile, surcharge 4-args) & AddEffect(1075 BrazierOfHolyFire_ExtraDmg -> UnitsWithTrait(SurroundingUnits(cible, range_2, includeCenter), Daemon), TurnsFromRounds(2)) ; case-brazier-radbombardment)
    RadBombardmentAbility.ABILITY_TYPE: RadBombardmentAbility,         # 1116 (admecDominus Dominus AdeptusMechanicus, cast TILE-TARGET CustomRange(1) : ligne droite depuis l'aim de Sum(Get(1), RoundsStarted(caster), TotalRepairActionsAmount(amis Mechanic)) tuiles (SortReverse - Blocking) -> Foreach(occupants, 1x Toxic famille ABILITY) & AddEffect(1065 Pinned -> ces occupants) & AddEffect(1244 Contaminated -> les tuiles, source = la tuile) ; case-brazier-radbombardment)
    SupremeCommanderAbility.ABILITY_TYPE: SupremeCommanderAbility,     # 1028 (astraCreed Creed AstraMilitarum : ExecuteAtomic(Spawn nrOfSummons gardes hex libres adjacents WithStatsFromConfig) puis Execute(PerformAIAction(UnitsWithIds(SurroundingFriends(range), affectedUnitIds), asGroup=1, resetTurnFlags=1)) — 1er consommateur du debloqueur PerformAIAction, case-perform-ai-action)
    FragBombAbility.ABILITY_TYPE: FragBombAbility,                     # 1017 (astraBullgryn « Kut Skoden » AstraMilitarum : ExecuteAtomic(SortedAttackSeries(Units(Target), 6x Blast melee, AdjacentUnits(Target)-Caster, 3x Blast)) -- splash FRIENDLY-FIRE (allies inclus, caster exclu), ordre du splash = voisinage NATIF (aucun OrderBy dans SortedAttackSeries))
    BasiliskBarrageAbility.ABILITY_TYPE: BasiliskBarrageAbility,       # 1026 (astraOrdnance « Thaddeus Noble » AstraMilitarum : Execute(AtomicGroup(AttackWithAbilityDamage(caster, <5 tuiles d'obus tirees AVEC REMISE : guaranteed=TurnsStarted-1 sur la tuile cible, maybe sur {cible} u ring1, miss sur ring2>, 2x Blast/obus))) -- famille ABILITY, cibles TILE-domain)
    UnstoppableMomentumReworkedAbility.ABILITY_TYPE: UnstoppableMomentumReworkedAbility,  # 1152 (orksNob « Tanksmasha » Orks, cast TILE-TARGET adjacent : CHARGE EN LIGNE imperative <=10 tuiles — `TilesBehindInLine(CasterTile, cible, checkWalkable+updateReference)` mise en cache, puis par tuile : `Move` si libre/steppable, sinon `RemoveEffect(1061)` + `AttackWithAttackDamage(Enemies(occupants), MinMaxDamage + extraDmg x index)` DirectDamage pierce-100 + `If(!CanBeDisplaced, Stunned(1162), Pinned(1065))` + `PushToPrioritizedTiles` (diagonales avant tirees au sort, puis diagonales arriere, puis tout droit ; jamais `Backward`) sinon `SwitchPosition` ; s'ARRETE sur BigTarget/Immovable. `AddFlag/RemoveFlag(UnitFlag.Undisplaceable)` encadrent la charge. #498)
    WaaaghAbility.ABILITY_TYPE: WaaaghAbility,                      # 1058 (orksWarboss Orks : 5 Execute successifs IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour — Spawn(2 Ork Boyz adjacents) / buff 1099+1100+1101 (caster + allies adjacents + TOUS les allies Orks, 1 round) / charge MoveUnit(movement+extraMovement) / attaque normale si adjacent / PerformAIAction(Friends(UnitsWithVisualId(orksOrkBoys)) BOARD-WIDE, asGroup=1, resetTurnFlags=1) — 2e consommateur PerformAIAction, tache #94)
    SendInTheNextWaveAbility.ABILITY_TYPE: SendInTheNextWaveAbility,   # 1016 (astraYarrick AstraMilitarum : Spawn(min(nrOfSummons + allies morts, maxSummons[level]) Cadians sur tuiles libres <=2 hex de la cible, priorite AttackTilesForTarget) + on-appearance UseNormalAttackIfAble(cible) — case-220 P0-SUMMON, tache #94)
    IncursionAbility.ABILITY_TYPE: IncursionAbility,                   # 1021 (blackPossession BlackLegion : ChainBehaviour <=maxSummons=6 iterations, 1 Bloodletter/iteration sur hex libre adjacent a la cible, arret si cible morte/hors portee + on-appearance UseNormalAttackIfAble(cible) — case-220 P0-SUMMON, tache #94)
    SpawnPoxwalkersAbility.ABILITY_TYPE: SpawnPoxwalkersAbility,       # 1040 (deathBlightbringer DeathGuard : self-cast, ceil(rand(n*chance, n*chance_2)/100) Poxwalkers sur hex libres rayon CalculateRange(TurnsStarted)=1/2/3 + on-appearance PerformAIAttackFromCurrentPosition — case-220 P0-SUMMON, tache #94)
    # --- MACHINES OF WAR (debloqueur case-mow-offboard-cast : la MoW est une entite ECS hors-plateau,
    # `_load_machines`). Les 3 abilities MoW a PREDICAT DE CIBLAGE conditionnel (tache #90 lot A) :
    EntropyCannonsAbility.ABILITY_TYPE: EntropyCannonsAbility,         # 1168 (deathCrawler MoW DeathGuard : 2x Energy mono-cible, famille ABILITY ; ciblage = cible sous aura Contagion alliee OU FixedArmor negativement modifiee, IdunBattleLogic.Entities.Abilities.Active.EntropyCannonsAbility$$GetDynamicInvalidTargetReason)
    HadesAutocannonsAbility.ABILITY_TYPE: HadesAutocannonsAbility,     # 1147 (blackForgefiend MoW BlackLegion : buff CRIT_DAMAGE +extraCritDmg -> 6x Flame sur la cible ET les summons de SON camp <=range hex (IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets, includeCenter) -> retrait du buff ; ciblage = SUMMON ennemi)
    SquigLaunchasAbility.ABILITY_TYPE: SquigLaunchasAbility,           # 1200 (orksRukkatrukk MoW Orks : 3x Physical famille ABILITY + summon orksSmnSquig conditionne par IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$FulfillsSummonCriteria EVALUE AVANT l'attaque (SetCache) ; ciblage = >=1 Ork allie ou >=2 allies adjacents a la cible)
    # --- Lot #90-B : abilities de MACHINE OF WAR au patron « POSE D'EFFET(S) SEULE » (le behaviour de
    # cast n'est qu'un arbre d'`AddEffect`/`AddBondEffect` : aucune attaque, aucun spawn, aucune stat).
    # Le degat vit dans la PHASE 2 (l'ability TRIGGERED portee par l'effet), hors de ces ports.
    # cf. docs/rl/case-90-mow-effect-posers.md.
    HeavyRailRifleAbility.ABILITY_TYPE: HeavyRailRifleAbility,         # 1160 (tauBroadside Tau MoW : AddEffect(1334 PendingTarget -> cible) & AddEffect(1333 PendingAttack -> la MoW) ; unit-target)
    MacroPlasmaIncineratorAbility.ABILITY_TYPE: MacroPlasmaIncineratorAbility,  # 1159 (ultraDreadnought Ultramarines MoW : AddEffect(1335 Tile -> triangle Walkable/SameElevation autour de la tuile ciblee) & AddEffect(1336 AutoAttack -> la MoW), TurnsFromRounds(1) ; tile-target)
    DutyEternalAbility.ABILITY_TYPE: DutyEternalAbility,               # 1158 (ultraDreadnought Ultramarines MoW : RemoveMachine(caster) & Spawn(ThreeTileUnitSpawnShape(tuile ciblee), "ultraSmnDreadnought", opts+0x60=1 -> UNE unite a 3 PIEDS) ; on-appearance AddTrait(0x418 Stationary) [& AddTriggeredAbility(1re triggered du caster)] ; tile-target -- SEULE ability multi-hex du build, cf. case-91)
    DevastatingRefrainAbility.ABILITY_TYPE: DevastatingRefrainAbility,  # 1188 (adeptExorcist Sisterhood MoW : AddEffect(1403 Attack -> la MoW) + AddBondEffect(1402 Target -> tuile ciblee + 3 voisines {3,1,5}/{0,2,4} selon le cote) ; tile-target)
    SquigMineAbility.ABILITY_TYPE: SquigMineAbility,                   # 1201 (orksRukkatrukk Orks MoW : AddEffect(1441 SquigMine_Tile -> tuile ciblee + PickRandomly(nrOfTiles) dans le disque range=2 libre/sans-mine), TurnsFromRounds(nrOfRounds) ; tile-target)
    MalleusRocketLauncherAbility.ABILITY_TYPE: MalleusRocketLauncherAbility,  # 1142 (astraOrdnanceBattery AstraMilitarum MoW : Inform + AddBondEffect(1308) + AddEffect(1309 PendingTarget) + AddEffect(1310 SpottedTarget), tous sur la TUILE ciblee ; tile-target)
    # --- Lot #90 groupes B/C/D : les 5 abilities MoW restantes (cf. docs/rl/case-90-mow-effect-posers.md).
    # B = attaque DSL filtree par un ETAT + entretien de cet etat ; C = template SPAWN ; D = composite lourd.
    TwinSmartMissileSystemAbility.ABILITY_TYPE: TwinSmartMissileSystemAbility,  # 1161 (tauBroadside Tau MoW, groupe B : 3x Blast famille ABILITY sur TOUT ennemi porteur de Markerlight(1122) + refresh du marquage sur la cible (ChangeEffectTurns ChangeType.Add sinon AddEffect), TurnsFromRounds(2) ; unit-target)
    PlagueburstMortarAbility.ABILITY_TYPE: PlagueburstMortarAbility,   # 1169 (deathCrawler DeathGuard MoW, groupe B : 3x Toxic + Pinned(1065) sur cible+adjacents FILTRES par le predicat aura-Contagion/armure-reduite, + Contaminated(1244) sur la cible + nrOfTiles-1 tuiles adjacentes tirees ; unit-target)
    ForwardSpotterAbility.ABILITY_TYPE: ForwardSpotterAbility,         # 1143 (astraOrdnanceBattery AstraMilitarum MoW, groupe C : Spawn(nrOfSummons=1 astraSmnGuardsman sur tuile libre adjacente a la cible, WithStatsFromConfig) + on-appearance PerformAIAttack ; template SpawnSummon)
    DaemonicOrdnanceAbility.ABILITY_TYPE: DaemonicOrdnanceAbility,     # 1148 (blackForgefiend BlackLegion MoW, groupe D : ChangeStat(+extraCritDmg CRIT_DAMAGE) -> 3x Plasma famille ATTACK sur les ennemis deja sur une tuile EN FEU du triangle -> ChangeStat(-extraCritDmg) -> If(HasEffect 1316) AddOrUpdateStaticStatModifier((usages+1) x extraCritChance sur CRIT_CHANCE) -> AddEffect(Fire -> triangle) ; 2-phases par construction)
    # --- #117 DarkAngels lot 2 (case-117-darkangels-lot2.md) ---
    DarkTalonStrikeAbility.ABILITY_TYPE: DarkTalonStrikeAbility,        # 1092 (darkaAzrael HERO : cible TILE ; 1x DirectDamage sur l'occupant + nrOfHits_2 Bolter sur la ligne CONTIGUE d'ennemis (best-line count DESC, tie-break angle ASC, gate walkable+elevation |d|<2 pas-a-pas) + Pinned sur tous les touches)
    DeathOnTheWindAbility.ABILITY_TYPE: DeathOnTheWindAbility,          # 1213 (darkaStormSpeeder MoW : 6x HeavyRound sur les ennemis des nrOfTiles hexes de la ligne (best = direction qui aligne le plus d'ennemis, PAS de FilterContinuous) + effet 1257 sur les survivants, 1 tour ; gate de ciblage = cible deja attaquee ce tour)
    HailstrikeAbility.ABILITY_TYPE: HailstrikeAbility,                  # 1214 (darkaStormSpeeder MoW, effect-poser : AddEffect(1509 Hailstrike) sur un ALLIE, TurnsFromRounds(nrOfRounds) ; phase 2 = pierce bonus + ability triggered Hailstrike_Attack)
    RitesOfRestorationAbility.ABILITY_TYPE: RitesOfRestorationAbility,  # 1039 (adeptHospitaller Isabella Sisterhood HERO : op_BitwiseAnd(Heal(ForHeal, hpToHeal) sur Healable(soi + allies adjacents), Resurrect(PickRandomly(morts Imperial non-mecaniques Hero, nrOfHeroes) + PickRandomly(idem Summon, nrOfSummons) zippes sur CanAddUnit(AdjacentTiles(casterTile)), hp, healType 0, takesImmediateTurn=false)) ; #564)
    ThriceBlessedConflagrationAbility.ABILITY_TYPE: ThriceBlessedConflagrationAbility,  # 1187 (adeptExorcist Sisterhood MoW, groupe D : Foreach(1x Flame famille ABILITY sur la ligne CONTIGUE d'ennemis partant de la cible dans la direction qui en aligne le plus) + If(HasFaction(cible, Sisterhood), AddEffect(1401), AddEffect(1436)) sur la cible ALLIEE)
    # --- Lot #114 (TAU) : face COMBAT des abilities dont la face DECISION (playbook) etait deja portee.
    FightingRetreatAbility.ABILITY_TYPE: FightingRetreatAbility,  # 1081 (tauDarkstrider Tau HERO : AddEffect(1157 DmgReduction)+AddEffect(1158 HitReduction) sur les ennemis adjacents non-Steppable/Object + Foreach(Markerlight 1122) + Foreach(allies adjacents + soi, If(HasTrait RangedSpecialist, ActivateEffect 1515)) + If(nbEnnemisAdjacents>0, ResetTurn(soi), FinishTurn(soi)) ; duree TurnsUntilEndOfCurrentPlayersNextTurn ; self-cast)
    InspiredToGreatnessAbility.ABILITY_TYPE: InspiredToGreatnessAbility,  # 1082 (tauAunShi Aun'Shi Tau HERO : split UnitsThatCanHaveActiveAbilityReset(cible) / complementaire -> RepairOrHeal(hpToHeal) / RepairOrHeal(hpToHeal_2) + AddStatOverrideEffect(1180, ACTIVE_ABILITY_LEVEL = Min(niveau 1082 du caster, niveau de l'actif primaire de la cible)) + ResetActiveAbility ; unit-target allie)
    EarlyWarningOverrideAbility.ABILITY_TYPE: EarlyWarningOverrideAbility,  # 1077 (tauCrisis Re'vas Tau HERO : AddEffect x4 sur soi (1009 Overwatch_AutoAttack, 1144 SuppressCloseCombatWeakness, 1145 ReactivateOverwatch, 1149 Visual, TurnsFromRounds(1)) + Spawn(nrOfSummons=2 tauSmnDroneShield sur tuiles libres adjacentes-caster, WithStatsFromConfig) + on-appearance PerformAIAttack ; self-cast)
    SeekerMissileFrequencyLockAbility.ABILITY_TYPE: SeekerMissileFrequencyLockAbility,  # 1069 (#491 -- tauMarksman Sho'syl Tau HERO : le cast NE FRAPPE PAS (patron 2-phases de HeavyRailRifle, le degat HeavyRound du kit appartient a la triggered 1127 SeekerMissileFrequencyLock_Attack, NON portee) : AddEffect(1122 Markerlight -> cible, TurnsUntilEndOfCurrentPlayersNextTurn) & AddBondEffect(1123 _Target -> cible, bonde au caster) & AddBondEffect(1136 _Aiming -> caster, bonde a la cible), les deux bonds a duree DEFAUT ; unit-target, range=5 depuis config)
    ExemplarOfTheKauyonAbility.ABILITY_TYPE: ExemplarOfTheKauyonAbility,  # 1087 (tauShadowsun Commander Shadowsun Tau HERO : Teleport(Caster -> tuile cible libre adjacente a un allie) & If(OwnerIsAlive, AddEffect(1181 ExemplarOfTheKauyon_AdditionalHits sur soi) & PerformAIAttackFromCurrentPosition(Target) & RemoveEffect(1181)) & Spawn(tauSmnDroneCommandLink sur l'EX-tuile du caster, First(1) de CanAddUnit(exTile + SortByDistance(Randomize(AllTiles), exTile)), on-appearance AddTrait(Stationary)) ; tile-target -- #488)
    ExemplarOfTheMontkaAbility.ABILITY_TYPE: ExemplarOfTheMontkaAbility,  # 1210 (tauFarsight « Commander Farsight » Tau HERO : UN SEUL noeud -- Execute(AddEffect(1498 ExemplarOfTheMontka, abilityState = get_AbilityStateReference, source = Caster@0x48, targets = UnitsWithRangedWeapons(UnitsWithTrait(Friends(of = Caster@0x48, entities = AllAliveUnits@0x20, 3), 0x10 = Hero, 3)), turns = <DSLFormulas+0x20> = 1 TOUR)). Le caster entre par le FILTRE (aucune soustraction/addition, contrairement au jumeau de forme WarHowl 1106) : il n'est buffe que parce qu'il porte Hero ET une arme Range>=2. L'effet 1498 pose `UnitTrait.Unstoppable` (AddTrait 0x412 temporaire) et `+extraDmg` / `+extraDmg_2 si HasTrait(Target, BigTarget)` sur les attaques NORMALES -- melee ET distance, aucun gate de nature. Masque STATIC-COPY `<TargetingOptions statics>+0x280` = 0x8004 sur RANGE_SELF ; AbilityAttackType litteral 2 ; 1210 est deja dans NO_END_TURN / NO_ABILITY_USED_FLAG)
    # --- Lot BOSS RIPTIDE (#895) : les DEUX actives du boss de guilde `tauBossRiptide` (NPC) dont le
    #     cast est une PURE POSE D'EFFETS (patron 2-PHASES de HeavyRailRifle) -- l'audit les classait
    #     `DAMAGE(Particle)` d'apres le `damageProfile` du KIT, pas d'apres le behaviour.
    NovaChargeAbility.ABILITY_TYPE: NovaChargeAbility,                 # 1193 (tauBossRiptide Tau NPC boss : cast TILE-TARGET, 2-PHASES comme ses deux freres -- Execute(op_BitwiseAnd(op_BitwiseAnd( AddBondEffect(0x583 NovaCharge_PendingAttack, source = Caster@0x48, targets = Caster@0x48, bondedEntity = Owner@0x30), AddEffect(0x584 NovaCharge_PendingTarget_Line, source = Caster@0x48, targets = Cache(GetLineTiles())) ), AddEffect(0x585 NovaCharge_PendingTarget_Single, source = Caster@0x48, targets = GetAdditionalMarkedTiles(lineTiles)) )) ; GetLineTiles = TROIS lignes paralleles depuis CenterTiles(CasterTile) vers Target, moins les tuiles du caster, trenches exclues ; GetAdditionalMarkedTiles = First(Unique(tuiles a occupant ennemi + ring-2 des ennemis) & rest, ConfigConst 0x11 nrOfTargets = 8) ; AUCUN degat au cast -- il vient de NovaCharge_Attack 1324 ; masque FLAGS DIRECTS 0x2000000042 + CustomRange(1) ; gate dynamique = la tuile visee touche EXACTEMENT UNE tuile du caster ; #1032)
    NovaShieldAbility.ABILITY_TYPE: NovaShieldAbility,                 # 1194 (tauBossRiptide Tau NPC boss : CreateShield(Caster, shieldHp, TurnsFromRounds(nrOfRounds=1), stackable) & AddStaticStatModifierEffect(Owner, 1416 NovaShield_ExtraBlockChance, BLOCK_CHANCE, +blockChance, meme duree) & AddEffect(1415 NovaShield_PendingTarget -> Filter(tuile ciblee + sa couronne, NOT IsTrenchTile), surcharge 5-args => chaque TUILE est sa propre SOURCE) & AddBondEffect(1414 NovaShield_PendingAttack -> Owner, bonde a lui-meme, duree DEFAUT) ; tile-target, masque STATIC-COPY `<TargetingOptions statics>+0x1c0` = 0x6000040 sur RANGE_WHOLE_BOARD ; le degat Particle est en phase 2 (triggered NovaShield_Attack, NON portee))
    NovaBoostAbility.ABILITY_TYPE: NovaBoostAbility,                   # 1192 (tauBossRiptide Tau NPC boss : AddBondEffect(1409 NovaBoost_PendingAttack -> Caster, bonde a Owner, duree DEFAUT) & AddEffect(1410 NovaBoost_PendingTarget -> Filter(AdjacentTiles(Caster), NOT IsTrenchTile), source=Caster) ; self-cast, masque PRESET+FLAGS `statics+0x280` (0x8004) | 0x10 = 0x8014 sur RANGE_SELF ; le saut + le degat sont en phase 2 (triggered NovaBoost_Attack, NON portee) ; gate dynamique `GetDynamicInvalidCasterReason` (>= 2 ennemis dans la couronne) NON PORTE = permissif)
    # --- Lot #112 : DarkAngels lot 1 (artefact natif = `<Ability>.ExecuteBehaviour` => arbres DSL).
    SuperchargeAbility.ABILITY_TYPE: SuperchargeAbility,               # 1103 (darkaHellblaster Sarquael : AddEffect(1208 Supercharge_ExtraPiercing) sur cible + <=2 PickRandomly(UnitsDirectlyBehind) POSE AVANT les attaques (elles en beneficient), TurnsFromRounds(1) & 1x Plasma minDmg/maxDmg sur la cible & 1x Plasma minDmg_2/maxDmg_2 sur ces memes unites ; native_factory attack, ExecuteAtomic 0x2a)
    ExemplarOfHateAbility.ABILITY_TYPE: ExemplarOfHateAbility,         # 1140 (darkaAsmodai Asmodai : AddEffect(1293 ExemplarOfHate_Target, TurnsFromRounds(2)) INCONDITIONNEL & If(grand-alliance Chaos de la cible, Pinned(1065) duree DEFAUT & override d'Attack + attaque normale libre + retrait, portes par le MEILLEUR allie DarkAngels a portee -- collapse S GetAttacker/SortAttackersByDamagePrediction))
    # --- case-bl-1029-1020 : les DEUX actives Black Legion HERO restees NO-OP (docs/rl/case-bl-1029-1020.md)
    DrachnyenAbility.ABILITY_TYPE: DrachnyenAbility,                   # 1029 (blackAbaddon Abaddon : SetHealth(Min(MaxHealth, hp[level])) & AddEffect(1471 Drachnyen_ExtraAttack -> soi, permanent) & UseActiveAbility(attaque NORMALE dirigee sur la cible) ; la triggered 1485 qui en decoule = residu nomme)
    HeraldOfTheApocalypseAbility.ABILITY_TYPE: HeraldOfTheApocalypseAbility,  # 1020 (blackHaarken Haarken : nrOfHits x Piercing sur la cible ET l'ennemi de la tuile DIRECTEMENT DERRIERE (TilesBehindInLine(CasterTile -> tuile cible, maxCount=2)) & AddEffect(1027 -> ces memes cibles) & TriggerAbility(BattleFatigue -> ennemis disque range=2 autour de la cible, cible incluse))
    # --- Famille PSYCHIC (case-psychic-aoe) : deux AoE Psychic HERO, jusqu'ici NO-OP offline. ---
    PlagueWindAbility.ABILITY_TYPE: PlagueWindAbility,                 # 1035 (deathTyphus Typhus DeathGuard : AoE CONCENTRIQUE 3 bandes ancree cible -- cible (minDmg/maxDmg) + adjacents-cible (minDmg_2/maxDmg_2) + adjacents-d'un-secondaire moins cible/secondaires (minDmg_3/maxDmg_3), 1 coup chacune, native_factory ABILITY, ExecuteAtomic 0x4a + 3 Group 0x4b/4c/4d)
    MortarionsPlagueWindAbility.ABILITY_TYPE: MortarionsPlagueWindAbility,  # 1093 (deathBossMortarion « Mortarion » GUILD BOSS, npc : JUMEAU de 1035 -- memes trois bandes concentriques ancrees cible (range 2), MAIS degat DETERMINISTE (`MinMaxDamage{,2,3}Average`, aucun tirage) et chaque bande DOUBLEE quand la CIBLE PRINCIPALE porte `Summon` (`If(HasTrait(Target@0x60, 2), Multiply(avg, <DSLFormulas+0x28>=Direct(2)), avg)`) ; degat CROISSANT par bande, a l'inverse de 1035 ; native_factory ABILITY, ExecuteAtomic 0x5c + 3 Group 0x5d/0x5e/0x5f ; masque 0x4002 MIGRE depuis `TARGETING_OPTIONS_UNPORTED`)
    BlightGrenadesAbility.ABILITY_TYPE: BlightGrenadesAbility,         # 1176 (deathNpc2PlagueMarine, npc -- #997 : DEUX `AttackWithAbilityDamage` a plage ET coups IDENTIQUES (le natif rappelle `MinMaxDamage`/`GetHits`, PAS de `*_2`), volet 2 = `PickRandomly(UnitsDirectlyBehind(caster, target), 2)` ; `ExecuteAtomic(op_BitwiseAnd(..), 0x2a)` ; masque `0x2004002` = preset inline `0x4002` OU flags `0x2000000` (surcharge PRESET+FLAGS) ; regle dynamique = refus si une tuile de la cible porte `Contaminated` 1244)
    ExplosivePresentsAbility.ABILITY_TYPE: ExplosivePresentsAbility,   # 1170 (orksRedGobbo, npc -- #997 : UN SEUL `AttackWithAbilityDamage` sur `(Target + AdjacentUnits(TargetTile)) - Caster` (friendly-fire, `AdjacentUnits` BRUT), plage/coups partages ; `ExecuteAtomic(., 0x2a)` ; masque `0x200000000002` = `TargetMatchesDynamicRule | TargetIsUnit` -- AUCUN `TargetIsEnemy`, le filtrage de camp vit dans la regle dynamique, qui EXEMPTE l'unite `constants.unitId` = `orksGrot`)
    ReapingScytheAbility.ABILITY_TYPE: ReapingScytheAbility,           # 1095 (deathBossMortarion « Mortarion » GUILD BOSS, npc : Execute(AttackWithAttackDamage(Caster@0x48, Target@0x60 op_Addition AdjacentFriends(Target@0x60, 1, 3), MinMaxDamage, Chain, GetHits()=nrOfHits=7, options Nullable VIDE)) -- PAS d'ExecuteAtomic, aucun groupe. L'`AdjacentFriends` est ANCRE SUR LA CIBLE (variante A, reference = le centre) : ce sont les allies DE LA CIBLE, donc les ennemis du caster autour d'elle ; famille ATTACK (crit/block actifs) ; masque = preset TargetingOptions statics+0x40 TEL QUEL = 0x4000 TargetIsEnemy + RANGE_ADJACENT)
    DoomboltAbility.ABILITY_TYPE: DoomboltAbility,                     # 1102 (thousAhriman Ahriman ThousandSons : Min(nrOfHits + Count(hexes en Feu), 9) coups Psychic REPARTIS par division entiere sur les ennemis <=range non obscurcis, tries SortUnitsByDamageUtility avec la CIBLE forcee en tete ; native_factory ATTACK, ExecuteAtomic 0x61)
    HeavyWarpFlamerAbility.ABILITY_TYPE: HeavyWarpFlamerAbility,       # 1227 (thousSekhetar « Sekhetar Robot » ThousandSons : ChainLeftOverHitsAttackDamage de GetNumTotalHits = Sum(nrOfHits, Min(GetPersistentData(1227, Owner, "PSYCHIC_ATTACKS_KEY"), maxNrOfHits - nrOfHits)) coups Flame sur la cible, extraHits NULL, report des coups gaspilles sur And(Damageable(AdjacentFriends(Target)), SurroundingEnemies(Caster, range 2)) trie par SortTargetsByDamagePredictionSelector (hits=1) ; porteur hors seed BC -> catalog_inject ; #523)
    HellfyreMissileRackAbility.ABILITY_TYPE: HellfyreMissileRackAbility,  # 1088 (thousTerminator « Toth » ThousandSons : Execute(SortedAttackSeries(Caster, Target, nrOfHits coups HeavyRound, FromTrigger(NonSteppableOrObjectUnits(Enemies(Caster, AllUnits)), HasTakenDamageOfDamageProfileThisTurn(ActiveTarget, Psychic)), nrOfHits coups HeavyRound)) -- le 2e volet frappe TOUT ennemi du plateau ayant pris du PSYCHIC ce tour, cible du message COMPRISE ; native_factory ABILITY, PAS d'ExecuteAtomic ; masque 0x4002 MIGRE depuis `TARGETING_OPTIONS_UNPORTED` ; #487)
    # --- case #154 : EmperorsChildren DoomSiren + Tyranids FearOfTheUnseen (canal DirectDamage) ---
    DoomSirenAbility.ABILITY_TYPE: DoomSirenAbility,                   # 1199 (emperKakophonist « Adamatar » : UN leaf combine — nrOfHits coups DirectDamage MELEE sur la cible + PickRandomly(nrOfUnits) ennemis adjacents A LA CIBLE (Damageable), passe id-triee unique ; puis Foreach(UnitsDamagedThisPhase(caster), If(IsDead(It) & HasFlag(It, 8=Overkilled), AddStaticStatModifierEffect(caster, 1431 DoomSiren_ExtraHit, EXTRA_HITS, Direct(1), PERMANENT))) ; ExecuteAtomic 0x2a)
    ExcruciatingFrequenciesAbility.ABILITY_TYPE: ExcruciatingFrequenciesAbility,  # 1197 (emperNoiseMarine « Shiron » EmperorsChildren : cast TILE-TARGET -- la tuile ADJACENTE visee donne la DIRECTION d'un rayon de nrOfTiles=3 tuiles. Execute((AddStaticStatModifierEffect(Caster, 1388 TemporaryStatModifier, 9 CritChance, Multiply(Count(Cache(Units(GetAffectedTiles))), Direct(extraCritChance)), Direct(1) tour, isHidden=1) & AttackWithAttackDamage(Caster, Cache(Enemies(Units(GetAffectedTiles))), MinMaxDamage, Blast, nrOfHits)) & RemoveEffect(Caster, 1388)) -- PAS d'ExecuteAtomic. Le COMPTE porte sur TOUTES les unites de la ligne (allies compris), l'ATTAQUE sur les seuls ennemis : deux selecteurs distincts sur le meme GetAffectedTiles. native_factory attack ; masque 0x20000000042 MIGRE depuis `TARGETING_OPTIONS_UNPORTED`, regle dynamique MIGREE depuis `DYNAMIC_TARGET_RULE_UNPORTED` ; #512)
    LashOfTormentAbility.ABILITY_TYPE: LashOfTormentAbility,           # 1196 (emperLucius « Lucius » EmperorsChildren : Execute(AttackWithAttackDamage(Caster, Target, MinMaxDamage, Eviscerate, GetHits()=nrOfHits=6) & IfAlive(Caster, PullUnitOneTile(Caster, Target, elevationKnockback NUL) & If(IsAdjacent(Caster, Target, 3), AddBondEffect(27 Taunted_OnlySpecificTargets -> Target, bonde au Caster, TurnsFromRounds(nrOfRounds))))) -- l'ATTAQUE PRECEDE le pull (inverse de GrapnelLauncher 1090) et le taunt est evalue APRES le pull ; PAS d'ExecuteAtomic ; masque STATIC-COPY `<TargetingOptions statics>+0x140` = 0x4002 + RANGE_FROM_CONFIG (range 2) ; porteur HORS pool et HORS catalogue -> injection catalogue ; #524)
    EuphoricStrikesAbility.ABILITY_TYPE: EuphoricStrikesAbility,       # 1198 (emperExultant « Laviscus » EmperorsChildren : Execute(AttackWithAttackDamage(Caster@0x48, Target@0x60, MinMaxDamage, GetDamageProfile()=Power, GetHits()=nrOfHits, options Nullable VIDE) & AddEffect(1429 EuphoricStrikes_ExtraCrit, AbilityStateReference, source=Caster@0x48, targets=Target@0x60, turns=<DSLFormulas+0x20>=Direct(1))) -- PAS d'ExecuteAtomic. La marque donne +extraCritChance a la PROCHAINE attaque portee contre la cible (gate get_OwnerIsTarget & AmountIsGreaterThanZero(StatAmount(Caster,9=CritChance,0=Current))), et son CreateRemoveEffectTrigger (On(9)&OwnerIsTarget | On(0)&Target==EffectSource) en fait une charge a usage unique. native_factory attack ; masque = preset TargetingOptions statics+0x40 TEL QUEL = 0x4000 TargetIsEnemy + RANGE_ADJACENT (le voisin ThunderousAssault lit le MEME preset mais y OR-e 0x10000000) ; #522)
    DaemonicPatronsAbility.ABILITY_TYPE: DaemonicPatronsAbility,       # 1203 (emperFlawlessBlade « Hascule » EmperorsChildren : Execute(AddBondEffect(27 Taunted_OnlySpecificTargets, source=Caster@0x48, targets=Target@0x60, bonde au Caster) & (AddEffect(1464 DaemonicPatrons_ExtraDamage -> Owner@0x30) & AddEffect(1465 DaemonicPatrons_DmgReduction -> Owner@0x30))), les TROIS a la MEME duree Sum(TurnsFromRounds(GetNumberConstant(0x45=nrOfRounds)), Const(1)@formulas+0x20) TOURS -- PAS d'ExecuteAtomic, AUCUNE attaque. L'audit classait 1203 en EFFECT/BUFF : l'arbre pose d'abord un TAUNT, et c'est le compte d'ennemis adjacents TAUNTES qui module les deux buffs (+extraDmg additif face attaquant ; -min(100, dmgReductionPct x n) % face defenseur). Masque PRESET+FLAGS : preset `<TargetingOptions statics>+0x40` (0x4000) OR-e 0x200000000 = 0x200004000 TargetIsEnemy|TargetIsNotAnObject + RANGE_ADJACENT ; porteur HORS pool et HORS catalogue -> injection catalogue ; la triggered 1473 DaemonicPatrons_Finale reste HORS PERIMETRE (residu #911) ; #911)
    FearOfTheUnseenAbility.ABILITY_TYPE: FearOfTheUnseenAbility,       # 1115 (tyranDeathleaper « Deathleaper » Tyranids : POSEUR D'EFFETS pur, AUCUN degat au cast — Execute plain de (If(NOT HasFlag(Self, Moved), AddEffect(1065 Pinned -> Enemies(NonSteppableOrObjectUnits(SurroundingUnits(Self, range, includeCenter))), duree DEFAUT) + TriggerAbility(memes ennemis, 1025 BattleFatigue)) + AddEffect(1238 TeleportingIn -> Self) + AddEffect(1239 ExtraDamage -> Self)), les 2 effets self a Sum(TurnsFromRounds(1), Direct(1)) TOURS ; le DirectDamage vit en PHASE 2 dans l'effet 1239 (canal coups additionnels #179))
    TheLionsWrathAbility.ABILITY_TYPE: TheLionsWrathAbility,           # 1217 (darkaBossLion « le Lion » GuildBoss DarkAngels, #889 : Execute((AddEffect(1522 TheLionsWrath_ExtraCritChance -> Owner@0x30, turns=null, AbilityStateReference) + AttackWithAttackDamage(Caster@0x48, Target@0x60, MinMaxDamage, GetDamageProfile()=Power, ConfigConst(0x2f=nrOfHits)=2, selectionType=2)) + IfAlive(Target@0x60, AddBondEffect(27 Taunted, source=Owner, targets=Target, bonded=Owner, TurnsFromRounds(nrOfRounds=1)) + AddBondEffect(1521 TheLionsWrath_PendingAttack, memes slots, options ZEROEES))). PATRON 2-PHASES : le 1521 derive d'APendingAttackEffect et arme la TRIGGERED 1520, qui frappe au debut du tour SUIVANT du Lion avec le SECOND jeu (minDmg_2/maxDmg_2/damageProfile_2=Piercing/nrOfHits_2=2) et retire le 1522 HORS de son If. Le 1522 rend le coup d'index 1 critique (ConfigVar(0x3a=chance)=100). masque = preset TargetingOptions statics+0x40 TEL QUEL = 0x4000 TargetIsEnemy + RANGE_ADJACENT ; AbilityAttackType litteral 0 = DirectTargetAttack)
    MartialExemplarAbility.ABILITY_TYPE: MartialExemplarAbility,       # 1216 (darkaBossLion « le Lion » GuildBoss DarkAngels, #889-r5 : Execute((AddEffect(1520 MartialExemplar_ExtraCritChance -> Owner@0x30, turns=Direct(1), AbilityStateReference) + AttackWithAttackDamage(Owner@0x30, AdjacentEnemies(Owner, unique:true, OnlyAliveAndTargetable), MinMaxDamage, GetDamageProfile()=Power, ConfigConst(0x2f=nrOfHits)=6, selectionType=2)) + IfAlive(Caster@0x48, KillDeadUnits(Caster@0x48, AdjacentEnemies(Owner, unique:true, Any)) + If(AmountIsGreaterThanZero(<attaquables adjacents>), UseNormalAttack(Owner, SortUnitsByDamageUtility(<attaquables adjacents>, Owner, UnitNormalAttackType(Owner), UtilityDefinition(0x23), NormalAttackDamage(Owner), 3, null)), MoveUnit(Owner, ClosestPositionToTarget(Owner, Tiles(<cible tiree>), ConfigConst(0x17=nrOfTiles)=1, false)) + UseNormalAttackIfAble(Owner, <cible tiree>)))). Le cast a DEUX volets de degat : l'AoE `Power` 6 coups, PUIS une ATTAQUE NORMALE (profil de l'ARME) -- la colonne `DAMAGE(Power)` de l'audit ne voit que le premier. Les DEUX `AdjacentEnemies` different par leur `selectionType` (3 pour frapper, **0 = Any** pour nettoyer les cadavres). L'effet 1520 ne mord que sur les cibles `UnitTrait.Summon` (ConfigVar(0x41=extraCritChance)=10). masque = preset TargetingOptions statics+0x280 (0x8004) OR flags 0x10 = 0x8014 ; AbilityAttackType litteral 2)
    SternguardFocusAbility.ABILITY_TYPE: SternguardFocusAbility,       # 1228 (darkaSternguard lineup / darkaBossSternguardLHE npc, #905 : Execute(AddTemporaryAttackOverrideEffect(Caster@0x48, PercentageOfAttackCappedAtMax(Subject@0x68, statPart=3 Initial, ConfigVar(1228, Owner@0x30, 0xd=maxDmg), ConfigVar(1228, Owner@0x30, 0x4a=dmgPct), rounding=0)) + UseNormalAttack(Caster@0x48, Target@0x60) + ResetTemporaryAttackOverrideEffect(Caster@0x48)). L'audit la classe EFFECT/BUFF : l'effet 0x510 est pose PUIS retire dans le cast, son seul role est d'armer une ATTAQUE NORMALE dont le profil/les coups viennent de l'ARME (1228 n'a AUCUN damageProfile au gameconfig) -- meme angle mort que 1216. masque = preset TargetingOptions statics+0x00 (0x4002, PRESET-COPIE sans flags), range = TargetingRange statics+0x00 = RANGE_ADJACENT_IF_MELEE_CASTER, forceMeleeTarget = 2 = IfRangedCaster ; AbilityAttackType litteral 2)
    CalibaniteGreatswordAbility.ABILITY_TYPE: CalibaniteGreatswordAbility,  # 1189 (darkaCompanion Forcas : TOGGLE de posture = If(HasEffect(Self,1404 Strike), AddEffect(1405 Sweep)+RemoveStrikeEffects(1404/1425/1009/1406), AddStrikeEffects(1404/1425/1009)+RemoveEffect(1405)) ; aucun degat, aucun tirage, ne finit pas le tour ; les observables Sweep/Overwatch vivent dans les TRIGGERED, hors port)
    # --- case-231 : socle `IsCharging` (BattleQuery$$IsCharging = adjacence + ChargedUnitIds@+0x190)
    #     + `force_crit` (octet +5 du Nullable<AttackOptions>). Les DEUX abilities du lot.
    TacticalPrecisionAbility.ABILITY_TYPE: TacticalPrecisionAbility,   # 1154 (ultraTitus Titus : If(IsCharging(caster,cible), ChangeStat(+extraCritDmg) & 1x Bolter FORCE-CRIT sur la cible & ChangeStat(revert), 3x Chain sur TOUS les AdjacentEnemies(caster)) ; ExecuteAtomic, branches EXCLUSIVES)
    MomentShackleAbility.ABILITY_TYPE: MomentShackleAbility,           # 1184 (custoTrajann Trajann : self-cast Heal(hpToHeal) & AddDynamicStatModifierEffect(1391 BlockChance) & (1392 BlockDamage) & AddEffect(1393 marqueur de la triggered MomentShackle_Attack), TurnsFromRounds(nrOfRounds=1) ; aucun degat)
    MartialInspirationAbility.ABILITY_TYPE: MartialInspirationAbility,  # 1191 (custoBladeChampion Kariyan Custodes : AddEffect(1408 MartialInspiration_ExtraDamage sur le CASTER, Direct(1) tour) op_BitwiseAnd AttackWithAttackDamage(Target, MinMaxDamage, Eviscerate, nrOfHits=3) -- le buff est pose AVANT l'attaque et la buffe (gate `CurrentAbilityIs(1191)`), magnitude `extraDmgPct x TotalTurnsWithAttacksMade(Owner)` donc NULLE au 1er tour de bataille, #509)
    TalonsOfTheEmperorAbility.ABILITY_TYPE: TalonsOfTheEmperorAbility,  # 1195 (custoAtlacoya Atlacoya Custodes : If(HasTrait(cible, Psyker) | HasFaction(NonSteppableOrObjectUnits(AdjacentFriends(caster)), Custodes), 1x DirectDamage, 1x Power) sur la cible adjacente ; degat = Sum(MinMaxDamage, Multiply(ConfigVar(extraDmg), If(HasEffect(caster, 1420), EffectLevel, 0))) ; AbilityAttackType = 2 Others, #521)
    VexillaMagnificaAbility.ABILITY_TYPE: VexillaMagnificaAbility,      # 1183 (custoVexilusPraetor Aesoth Custodes : ExecuteAtomic( ((AttackWithAttackDamage(Target) & AttackWithAttackDamage(Cache(First(SortUnitsByDamageUtility(NormalUnits(AdjacentEnemies(caster)) - Target, MinMaxDamage(isPrediction:0), 3))))) & AddEffect(1162 Stunned -> Target + 2e cible, options ZEROEES = duree DEFAUT) ) & AddEffect(1383 VexillaMagnifica_DmgReduction -> Caster, TurnsFromRounds(nrOfRounds=1)), 0x2a Ability_AtomicGroup) ; le tri CONSOMME un tirage, ENTRE les deux attaques ; AbilityAttackType = 0 DirectTargetAttack ; masque 0x200004000 MIGRE depuis `TARGETING_OPTIONS_UNPORTED` ; #566)
    # --- case-decision-noop : gisement `[-D]` (la DECISION choisit, l'EXECUTION etait un NO-OP). ---
    # --- #287 : face COMBAT de SorcerousFacade, dont la face DECISION etait deja portee (#27-4e).
    SorcerousFacadeAbility.ABILITY_TYPE: SorcerousFacadeAbility,       # 1100 (thousTzaangor « Yazaghor » ThousandSons : cast sur un ALLIE Psyker -> AddEffect(1204 SorcerousFacade_AdditionalHits -> Caster + Target, TurnsFromRounds(1)) & UseActiveAbility(attaque NORMALE dirigee sur `sel` = l'ENNEMI le plus proche de `ValidNormalAttackTargets`) & KillDeadUnits(Caster, sel) & TriggerAbilityDelayed(Owner, 1180 SorcerousFacade_Switch, 3) -> SwitchPosition(Caster, Target) ; masque 0x402 MIGRE depuis `TARGETING_OPTIONS_UNPORTED`)
    # --- #299 : REPARATION REGULIERE. La face DECISION etait complete (#296/#298 : enumeration,
    # ciblage, prediction, choix IA) et la face COMBAT etait un NO-OP -- cast accepte, tour consomme,
    # ZERO PV restaure. Les deux ids sont EXACTEMENT
    # `idun...StaticBattleRules.ActiveAbility$$IsRegularRepair`.
    RepairAbility.ABILITY_TYPE: RepairAbility,                         # 28 (ability DERIVEE du trait `Mechanic`, donc ABSENTE du gameconfig et multi-factions : admecDominus / admecManipulus / necroSpyder / orksBigMek / votanIronmaster ; `Repair(Caster, ActiveTarget, Attack x Max(WeaponHighestHits,1), ForRepair)` -> `RepairUnitOperation`)
    Repair_GalvanicFieldAbility.ABILITY_TYPE: Repair_GalvanicFieldAbility,  # 1119 (admecManipulus, passif `GalvanicField` : la reparation HERITEE de 28 & volet attaque -- AddStatOverrideEffect(1242 ATTACK = Min(maxDmg, Attack_Initial x dmgPct)) & PerformAIAttackFromCurrentPosition & RemoveEffect, patron TheQuickening)
    # --- #931-r1 : le SOIN GENERIQUE, jumeau EXACT de 28 sur l'axe formule (`Attack x Max(hits,1)`)
    # et sur l'axe origine (une ability DERIVEE D'UN TRAIT, ici `Healer`), et pourtant DEUX classes
    # natives distinctes. La voie de specialisation n'est PAS un heritage (contrairement a 1119, qui
    # fait `return RepairAbility..ctor(this)`) mais un SWAP DSL : `TwistedScience` et `HealingBalms`
    # font `RemoveActiveAbility(Owner, 18) & AddActiveAbility(Owner, 1167 / 1212)`, et leurs deux
    # classes derivent d'`AActiveAbility`. Porter 1167 (#931) et 1212 (#966) ne portait donc PAS 18.
    HealAbility.ABILITY_TYPE: HealAbility,                             # 18 (ability DERIVEE du trait `Healer`, donc ABSENTE du gameconfig et multi-factions : adeptHospitaller / bloodSanguinary / deathRotbone / ultraApothecary au pool, plus genesBiophagus et spaceWolfPriest qui la PERDENT au swap ; `Heal(Caster, ActiveTarget, Attack x Max(WeaponHighestHits,1), ForHeal)` -> `HealUnitOperation` ; masque `0x8500` STATIQUE -- `TargetIsHealable | TargetIsFriendly | CasterIsPossibleTarget` -- et NON `0x8002` comme 28, qui delegue tout a sa regle dynamique)
    # --- case-317 §5 tranche 2 : face COMBAT de 1117 (la face DECISION etait deja portee, playbook
    # NonComparable). MEME porteur qu'au-dessus (`admecManipulus`), et il REUTILISE litteralement
    # `Repair_GalvanicFieldAbility$$CreateAttackBehavior` -- avec un `actingUnits` DIFFERENT.
    DefendTheDivineWorkAbility.ABILITY_TYPE: DefendTheDivineWorkAbility,  # 1117 (admecManipulus « Actus » AdeptusMechanicus, self-cast : ExecuteAtomic(Repair(Caster@0x48, Friends(Caster, AdjacentUnits(CasterTile@0x50)) + Caster, Get(hpToRepair), ForRepair), 0x2a) PUIS Execute(Repair_GalvanicFieldAbility.CreateAttackBehavior(dsl, Friends(Caster, AdjacentUnits(CasterTile)) SANS le caster)) -- l'etage 1 repare le caster ET ses amis adjacents, l'etage 2 ne fait attaquer que les amis adjacents MECANIQUES)
    # --- #389 (residu `#383-r1`) : face COMBAT de 1059, dont la face DECISION (playbook, batchs 1-4)
    # etait deja portee (#353/#361/#383). Le verrou etait le noeud `<DSLTriggers+0x20>` du `If` qui
    # gate les deux attaques : il n'est NOMME NULLE PART (slot de metadata-usage a xref UNIQUE) et un
    # port speculatif aurait ete pire que l'absence. Nomme par TROIS sources -- gabarit de classe
    # (taille 24, parent AbilityTrigger), TYPE du champ (`dsl.state` = MatchState, ce qui ecarte les
    # 21 classes de meme gabarit allouees avec un SELECTEUR par un `DSLTriggers$$X` nomme), et le
    # corps trivial `DSLTriggers$$IsRangedPosition = op_LogicalNot(<+0x18>)` qui nomme le JUMEAU et
    # force l'appariement -> `IdunBattle.Entities.Triggers.OwnerIsAliveAbilityTrigger`.
    RammingSpeedAbility.ABILITY_TYPE: RammingSpeedAbility,             # 1059 (ZERO porteur gameconfig -> greffe orksKillaKan : CHARGE sur First(SortTilesByUtility(MovableTilesInRange(caster, range=5) & CanAddUnit(AdjacentTiles(cible)), [Tile(7), RammingSpeed_MostAdjacentEnemies(54)])) gatee par NOT(IsAdjacent) & AddEffect(1098 RammingSpeed_ExtraExplode -> SOI, duree DEFAUT, source = Owner) & If(OwnerIsAlive, nrOfHits=4 coups Physical sur la cible + nrOfHits_2=2 coups sur SOI-MEME) ; famille ATTACK, Execute PLAIN)
    DakkaDakkaDakkaAbility.ABILITY_TYPE: DakkaDakkaDakkaAbility,       # 1171 (orksKillaKan « Snappawrecka » Orks : Min(nrOfHits + TimesRepaired*extraHits, maxNrOfHits) coups Projectile ranged sur la cible & If(NumLeftOverHits(cible), attaque des coups GASPILLES repartis (Divide Floor + reste a la 1re) sur PickRandomly(Damageable(Unobscured(SurroundingEnemies(caster, range_2))), RandomAmount(1, Min(numLeft, Count))) ) & If(IsAlive(caster), ChangeStat(caster, Health, Subtract, PercentageOf(StatAmount(caster, Health, MAXIMUM), healthPct))))
    # --- #511 : face COMBAT de 1225 (la face DECISION etait deja portee -- famille (b) de
    # `entities/abilities/active_ability.py`, `MakeDamagePredictions` = GenerateMultiHitAttackPredictions).
    # Porteur HORS pool (`astarCyrus`) -> confronte par `catalog_inject`, comme son passif HaywireMine.
    StrikeFromTheShadowsAbility.ABILITY_TYPE: StrikeFromTheShadowsAbility,  # 1225 (astarCyrus « Cyrus » Adeptus Astartes : (AttackWithAttackDamage(Caster@0x48, Target@0x60, MinMaxDamage, Bolter, GetHits, selectionType 2) + AddEffect(0x60d StrikeFromTheShadows -> Target, source Caster, Sum(TurnsFromRounds(1), Direct(1)) TOURS)) + ResetMovement(Owner@0x30) ; l'attaque part D'ABORD, le mouvement est rendu EN DERNIER ; l'effet 0x60d est numeriquement INERTE (EffectBonus a trigger seul, six slots de magnitude a ZERO) ; PAS d'ExecuteAtomic)
    # --- #996 : trois des SIX no-op silencieuses du lot (docs/rl/case-996-six-no-op-silencieuses-
    # reconnaissance.md). La colonne « categorie » de l'audit derive du `damageProfile` de l'ARME du
    # porteur (residu #491-r2) : elle etait FAUSSE pour 1010, JUSTE pour 1133 et 1185. Les trois
    # sont npc-only ou summon -> confrontees par GREFFE (case-92 §5bis) / via leur summoner.
    ForwardObserversAbility.ABILITY_TYPE: ForwardObserversAbility,   # 1185 (`tauNpc5StealthSuit` npc + `tauSmnStealthSuit` SUMMON, Tau : EFFECT/BUFF CONFIRMEE -- op_Addition( AddEffect(0x462 = 1122 Markerlight, absRef, source Owner@0x30, targets Target@0x60, TurnsFromRounds(GetNumberConstant(0x45 nrOfRounds) = 2)), AddEffect(0x575 = 1397 ForwardObservers_DamageReduction, absRef, source Owner@0x30, targets Owner@0x30, TurnsFromRounds(GetNumberConstant(0x77 nrOfRounds_2) = 1)) ) ; DEUX durees DISTINCTES et DEUX cibles distinctes ; la face DECISION etait deja portee (`playbook/loki_custom.py`) et la face COMBAT etait un NO-OP)
    WarConstructAbility.ABILITY_TYPE: WarConstructAbility,           # 1133 (`eldarNpc4Wraithguard` + `eldarNpc4WraithguardSurv` npc Aeldari : EFFECT/BUFF CONFIRMEE -- cast SELF (`isSelfCasting = 1`), op_Addition( AddEffect(0x506 = 1286 WarConstruct_CounterAttack -> Target@0x60, TurnsFromRounds(1)), AddEffect(0x516 = 1302 IgnoreUsedAbilityInOverwatch -> Owner@0x30, TurnsFromRounds(1)) ) ; les deux durees sont le LITTERAL 1, le kit 1133 ne porte NI constants NI variables ; la MECANIQUE des deux effets vit dans l'EFFET (`WarConstruct_CounterAttackEffect$$GetCounterAttackBehaviour`), hors port -> effets POSES et INERTES)
    StormOfFlensingBladesAbility.ABILITY_TYPE: StormOfFlensingBladesAbility,  # 1010 (`necroNpc2FlayedOne` + 2 Flayed One de tutoriel, npc Necrons : categorie annoncee EFFECT/BUFF **FAUSSE** -- c'est une DOUBLE ATTAQUE NORMALE. `ExecuteBehaviour` ne construit AUCUN arbre : `DSLBehaviors$$AtomicGroup(0x3e = GroupType.StormOfFlensingBlades_Attacks, <delegue>, null)` surcharge 4-args (executee par le PROCESSOR), et le delegue `<>c__DisplayClass1_0$$<ExecuteBehaviour>b__0` boucle DEUX fois sur `Execute(UseActiveAbility(Caster@0x48, Target@0x60, UnitNormalAttackType(Caster@0x48), options{SkipEndTurnFlag = (i == 0), SkipAtomicCheck = 1}))` ; kit 1010 = `attackRangeType=Melee` SEUL, aucun profil de degats propre)
    TitanhammerSquadAbility.ABILITY_TYPE: TitanhammerSquadAbility,  # 1231 (astarLysander « Lysander » Adeptus Astartes/ImperialFists, TILE-TARGET : ((AddEffect(0x623 _TargetTile -> Target@0x60 la TUILE, source Caster@0x48, Sum(TurnsUntilUnitOwnerTurn(groupe), Direct(1)) TOURS) & Heal(Caster@0x48, groupe, Get(GetVariableForLevel(0x20 hpToHeal)), ForHeal)) & AddDynamicStatModifierEffect(Filter(groupe, AmountIsGreaterThanZero(StatAmount(ActiveTarget@0x68, 7 BlockChance, 0 Current))), Caster@0x48, 0x624 _ExtraBlockDamage, stat 8 BlockDamage, Sum(TurnsUntilUnitOwnerTurn(ActiveTarget@0x68), TurnsFromRounds(1)))) & AddEffect(0x625 _TeleportingIn -> Filter(groupe, NOT HasFlag(ActiveTarget@0x68, 1 ArrivedAtFinalTile)), source Caster@0x48, Sum(TurnsUntilUnitOwnerTurn(ActiveTarget@0x68), Direct(1)) TOURS) ; groupe = Caster@0x48 + Filter(SurroundingFriends(Caster@0x48, GetNumberConstant(0x16 range), unique, 3 OnlyAliveAndTargetable), HasTrait(ActiveTarget@0x68, 0x40f TerminatorArmour)) ; l'audit la classait HEAL, le soin n'est que le 2e des QUATRE volets ; PAS d'ExecuteAtomic)
}


class AbilityHandler:
    """Visiteur des `ActiveAbilityMessage` (mirror du handler natif lançant `AActiveAbility.Execute`)."""
    __slots__ = ("state", "last", "unported")

    def __init__(self, state: State):
        self.state = state
        self.last: Optional[dict] = None     # diagnostic du dernier cast
        # DURCISSEMENT HARNAIS (leçon SpiritLeech #93) : ActiveAbilityType tombés sur no-op (registry combat
        # incomplet) ACCUMULÉS ici — un cast d'ability non portée ne DEAL/POSE rien mais ne lève AUCUNE erreur.
        # Sans cette trace, la divergence est SILENCIEUSE (attribuée à tort au bruit). Le harnais replay-diff /
        # self-play doit LIRE `unported` (et un test qui FORCE une ability assert `last["ported"] is True`).
        self.unported: set[int] = set()

    def visit_ActiveAbilityMessage(self, msg) -> None:
        """`IdunBattle.Messages.InputMessageProcessor$$Visit(ActiveAbilityMessage)` — le VISITEUR
        DE MESSAGE, et son gate, qui PRECEDENT toute operation. Mirror du decompile :

            caster = state.GetEntity(message.CasterId@0x10);
            target = state.GetEntity(message.TargetId@0x14);
            abilityType = message.ActiveAbilityType@0x18;
            if (!UnitExtensions.IsAliveAndNotFled(caster)
             || !UnitExtensions.IsAliveAndNotFled(target)) {
                AddBattleReporterDataForRejectedActiveAbilityMessage(...);   // INLINE ; ne loggue
                return;                                                       // QUE le caster mort
            }
            RunPhase(PhaseType.ActiveAbility /*6*/, () => {                       // <- rien de tout ceci n'est atteint
                streamHelper.OpenGroup(0xc User_UseAbility, casterId, abilityType, targetId);
                operationProcessor.ActiveAbility(caster, target, abilityType, options);
                streamHelper.CloseGroup();
            });

        #429-r1-r3 -- POURQUOI CE GATE EST ICI, ET PAS CELUI D'`ExecuteInternal`. Le gate
        cible-morte de l'OPERATION (`ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility`,
        #429-r1) DEROGE pour l'unique porteur du bit 38 `AllowDeadTarget` -- `GreatFrostAxe`
        (1089), dont `CanContinueOnDeadTarget()` rend vrai. Celui-ci NE DEROGE PAS : il ne lit ni
        l'ability ni ses `TargetingOptions`. Les deux coexistent dans le natif, a deux RANGS
        differents, et c'est ce qui explique la derniere divergence de la famille : 1089 echappe
        bien au gate d'operation (mirror correct), puis le natif le refuse ICI.

        L'ETAGE EST MESURE, pas deduit (`probe_429r1r3_dead_target_message_gate.py --volet
        signature`) : le compte d'evenements de stream SEPARE les deux rangs, parce que le groupe
        `User_UseAbility` est ouvert par la lambda de ce Visit, donc APRES ce gate et AVANT
        l'operation --
          * cast sur un CADAVRE (1089 comme 1003)          -> **0** evenement, aucun groupe ;
          * cast hors PORTEE sur une cible VIVANTE          -> **2** evenements, groupe 12 ;
          * cast legal                                      -> 43 evenements.
        Un refus au rang de l'OPERATION ouvre donc le groupe ; celui-ci ne l'ouvre pas.

        CONVENTION PERMISSIVE sur ce qui n'est pas RESOLU (meme regle que `targeting.py`) :
        `target_id is None` (le port modelise ainsi « pas de cible », le natif n'a que des ids) et
        entite absente de l'etat -> aucun refus. On ne gate que sur une entite RESOLUE dont
        `is_alive_and_not_fled` rend faux."""
        for role, eid in (("caster", msg.caster_id), ("target", msg.target_id)):
            if eid is None:
                continue
            ent = self.state.get_entity(int(eid))
            if ent is None or is_alive_and_not_fled(ent):
                continue
            self.last = {"ability_type": msg.ability_type, "ported": None,
                         "caster": msg.caster_id, "target": msg.target_id,
                         "not_alive_and_not_fled": role}
            return
        self._active_ability_operation(msg)

    def _active_ability_operation(self, msg) -> None:
        """`Core.Services.OperationProcessor$$ActiveAbility` -> `IdunBattle.Operations.
        ActiveAbilityOperation$$Execute` -> `$$ExecuteInternal` : tout ce que le natif fait UNE
        FOIS le gate de message passe. Appele par le visiteur ci-dessus ET par la RE-ENTREE
        `ExecuteForReplacedTarget` -- qui, cote natif, appelle `ActiveAbilityOperation$$Execute`
        DIRECTEMENT, sans repasser par `InputMessageProcessor$$Visit` : le gate de message ne doit
        donc PAS s'y appliquer, d'ou cette separation."""
        # #70 GATE ACTEUR-MORT (mirror `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` :
        # `if (EntityExtensions.IsUnit(caster) && UnitExtensions.IsDead(caster)) return 0;`). Un caster MORT
        # (hp<1, non-Fled ; `IdunBattle.Entities.UnitExtensions$$IsDead`) => l'ability est un NO-OP complet AVANT toute
        # execution : aucune behaviour, aucun degat, AUCUN flag de tour (le natif retourne 0 en amont du
        # `AddFlagsAfterAbilityExecution`). MEME gate que l'attaque normale (#139, cf. damage.py). Inerte pour
        # tout caster vivant (les casts legitimes partent d'unites vivantes) -> zero regression. cf. case-70.
        caster = self.state.get_entity(int(msg.caster_id))
        if unit_is_dead(caster):
            self.last = {"ability_type": msg.ability_type, "ported": None,
                         "caster": msg.caster_id, "target": msg.target_id, "actor_dead": True}
            return
        # #91 GATE MACHINE RETIREE -- une Machine of War que `IdunBattle.Operations.
        # RemoveMachineOperation$$Execute` a detachee de sa plateforme ne caste PLUS, ni l'ability
        # qui l'a retiree ni l'AUTRE (i2 DutyEternal : « Galatian can no longer be used as a
        # Machine of War for the rest of the battle »).
        #
        # SOURCE = la MESURE, pas une lecture de decompile : `RemoveMachineOperation` ne touche ni
        # `ActiveAbilityComponent` ni l'entite, et `decisionView.mows` continue d'exposer
        # `usable: true` -- donc aucun champ natif ne porte ce refus. Ce qui le porte est
        # OBSERVABLE et a ete mesure avec anti-confond (`probe_91_duty_eternal.py`, runner de
        # CONTROLE a fenetre cooldown/tour IDENTIQUE) : cast de 1159 apres retrait ->
        # `actionConsumed = False` ; le meme cast sans retrait -> `actionConsumed = True`.
        # Le no-op est donc pose ICI, au meme rang que le gate acteur-mort : aucune behaviour,
        # aucun flag de tour, aucun vecteur d'evenement -- exactement la signature d'un refus.
        mc = caster.get_component(MachineComponent) if caster is not None else None
        if mc is not None and getattr(mc, "removed", False):
            self.last = {"ability_type": msg.ability_type, "ported": None,
                         "caster": msg.caster_id, "target": msg.target_id,
                         "machine_removed": True}
            return
        klass = ABILITY_CLASSES.get(int(msg.ability_type))
        ability = klass() if klass is not None else None
        # #287-r14 RESOLUTION DE CIBLE -- `finalTarget = IActiveAbility.GetActualTarget(ability,
        # caster, target)` (slot 16 -> `IdunBattle.Entities.Abilities.AActiveAbility$$GetActualTarget`
        # -> slot `ITargetingQuery` 6 = `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`).
        # PLACE ICI parce que c'est SA place au decompile : `ExecuteInternal` transforme la cible
        # AVANT ses deux gates, et TOUT ce qui suit (`IsDeadUnitAndNotAllowedByAbility`,
        # `IsInvalidTarget`, `GetTiles` du snapshot, la re-resolution, `GetAbilityEntities`) voit le
        # finalTarget -- JAMAIS la cible de l'appelant.
        #
        # Ce que ca corrige : le port avait DEUX regimes d'appel la ou le natif n'en a qu'UN. Les
        # tests live envoient `targetId: <unite>` (`_ringed_cast.cast_and_confront`) et la face
        # DECISION portee emet `tileEntityId` -- le natif accepte les deux PARCE QU'IL RESOUT.
        # MESURE (#287-r12, live `MC1_67` seed 777) : `1018 ValkyrieStrike` pose `1022` sur la TUILE
        # cote natif ; en regime « id d'unite » le port le posait sur l'UNITE.
        #
        # `ability`/`klass` non portee -> `ActiveAbility.get_actual_target` n'est pas disponible :
        # aucune resolution (on ne devine pas le masque d'une ability qu'on n'a pas RE-lue), meme
        # convention que `is_invalid_target(ability=None)` -> 0.
        target_id = (klass.get_actual_target(self.state, msg.caster_id, msg.target_id)
                     if klass is not None else msg.target_id)
        # `if (finalTarget == null) return 0;` -- le natif abandonne AVANT tout, sans behaviour, sans
        # flag, sans vecteur. Porte SEULEMENT quand la resolution a REELLEMENT PERDU une cible qui
        # existait : le port modelise « pas de cible » par `target_id is None` (convention ecrite
        # dans `_gate_message` ci-dessus) alors que le natif n'a que des ids, donc rabattre un
        # `None` d'ENTREE sur ce refus transformerait « ability sans cible » en « cast refuse ».
        if msg.target_id is not None and target_id is None:
            self.last = {"ability_type": msg.ability_type, "ported": ability is not None,
                         "caster": msg.caster_id, "target": msg.target_id,
                         "no_actual_target": True}
            return
        # #429-r1 GATE CIBLE-MORTE -- mirror d'`ActiveAbilityOperation$$ExecuteInternal` :
        #     if (IsDeadUnitAndNotAllowedByAbility(abilityType, target)) return 0;
        # Le natif le place AVANT `IsInvalidTarget` (ordre relu au decompile, cf. l'en-tete de ce
        # module), donc ici. Son gate est le slot 0x11 `CanContinueOnDeadTarget`, qui lit le bit 38
        # `AllowDeadTarget` du masque de CONTINUE -- `False` pour toutes les abilities du binaire
        # sauf `GreatFrostAxe` (1089). Detail et mesure : `operations/active_ability.py`.
        if is_dead_unit_and_not_allowed_by_ability(self.state, klass, target_id):
            self.last = {"ability_type": msg.ability_type, "ported": ability is not None,
                         "caster": msg.caster_id, "target": msg.target_id,
                         "dead_target_not_allowed": True}
            return
        # #115 GATE DE CIBLE (mirror `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` :
        # `if (IsInvalidTarget(caster, casterTiles, target)) return 0;`). Le natif sort ICI, en amont
        # du 1er `AActiveAbility.Execute` de la behaviour, d'`AddFlagsAfterAbilityExecution` ET du
        # vecteur `On(0x2a = PreUnitAbility)` -> un cast REFUSE ne mute rien, ne consomme PAS l'activation
        # (`actionConsumed=false`, cf. case-111) et NE REVEILLE AUCUN trigger. Le filtre + son point
        # d'extension par ability vivent dans `targeting.py` ; une ability dont les
        # `TARGETING_OPTIONS` n'ont pas ete RE-lues n'est PAS gatee (aucun refus invente), et
        # `ability=None` (non portee) rend 0 par construction (`is_invalid_target`).
        reason = is_invalid_target(self.state, int(msg.caster_id), target_id, ability)
        if reason:
            self.last = {"ability_type": msg.ability_type, "ported": ability is not None,
                         "caster": msg.caster_id, "target": msg.target_id,
                         "invalid_target": int(reason)}
            return
        # #120bis SNAPSHOT DE TUILE de la cible — `IdunBattle.Operations.ActiveAbilityOperation$$
        # GetAbilityEntities` fige `AbilityEntities@+0x38 = EntityExtensions.GetTiles(finalTarget)`
        # AVANT le `On(0x2a = PreUnitAbility)`. C'est ce fige-la que la re-resolution ci-dessous confronte a
        # l'occupation REELLE d'apres la cascade. Pris ICI, au rang natif (juste apres les gates).
        _target_tiles = get_tiles(self.state, target_id)
        # #120 `On(PreUnitAbility=0x2a)` — le vecteur d'OPERATION, emis pour TOUTE ability qui passe
        # les gates, portee ou non (il ne depend pas de la behaviour : cf. le meme raisonnement que
        # les FLAGS de tour #139 ci-dessous). Emis AVANT l'execution, comme le natif.
        self._pre_unit_ability(msg)
        # #133 GATE ACTEUR-MORT **POST-`On(0x2a = PreUnitAbility)`** — mirror du test qui suit IMMEDIATEMENT
        # l'evenement dans `ActiveAbilityOperation$$ExecuteInternal` (lu verbatim au decompile) :
        #     FUN_1800280e0(0x4d, .., 0x2a);          # On(PreUnitAbility)
        #     if (options@0x4a == 0 && IsUnit(caster) && IsDead(caster, state)) return 0;
        # Le natif teste DEUX FOIS la mort du caster : en TETE d'operation (#70, deja porte) et ICI,
        # parce que la cascade de triggers reveillee par `0x2b` peut l'avoir TUE entre-temps. C'est
        # exactement ce que fait la riposte `MartialSuperiority` (« before the enemy attack
        # executes ») : si elle tue l'attaquant, l'attaque entrante est ANNULEE. `options@0x4a` = le
        # flag « caster mort autorise » des `AbilityOptions` : aucune voie du port ne le pose ->
        # gate toujours actif ici. Inerte pour toute cascade qui ne tue pas le caster.
        if unit_is_dead(self.state.get_entity(int(msg.caster_id))):
            self.last = {"ability_type": msg.ability_type, "ported": ability is not None,
                         "caster": msg.caster_id, "target": msg.target_id,
                         "actor_dead": True, "actor_dead_after_pre_ability": True}
            return
        # #120bis RE-RESOLUTION DE CIBLE — mirror du bloc qui suit IMMEDIATEMENT le `0x2b` dans
        # `ActiveAbilityOperation$$ExecuteInternal` : si une AUTRE unite occupe desormais la tuile
        # visee (SwornProtector : Kell echange sa place avec Creed pendant la cascade), le natif
        # `return`e sur `ExecuteForReplacedTarget`, qui RE-ENTRE dans `Execute` avec la nouvelle
        # cible. Cet appelant-ci ne pose donc NI behaviour NI flags — c'est la re-entree qui les
        # pose, une seule fois. Meme foyer que la voie d'ATTAQUE NORMALE (damage_ops.execute) : le
        # natif n'a qu'un site, le cabler sur une seule voie recreerait le fork ferme par #120.
        _replaced, _new_target = resolve_replaced_target(self.state, target_id, _target_tiles)
        if _replaced:
            self._execute_for_replaced_target(msg, ability, _new_target,
                                              execute_for_replaced_target)
            return
        if ability is None:
            self.unported.add(int(msg.ability_type))   # #93/#95 : rend le no-op VISIBLE (plus muet)
            self.last = {"ability_type": msg.ability_type, "ported": False}
            # #139 : les FLAGS de tour sont poses par le natif pour TOUTE ability executee, independamment
            # de sa behaviour -> on les mirror MEME quand la behaviour n'est pas portee (turn-flow fidele).
            self._unit_ability(msg)                    # `On(0xb)` : INCONDITIONNEL, avant le gate du `0xc`
            self._unit_active_ability(msg)             # `On(0xc)` : AVANT les flags (ordre natif)
            self.last["flags"] = self._add_flags_after_execution(msg)
            self._post_unit_ability(msg)               # `On(0xe)` : dernier evenement, apres les flags
            return                            # ability non portée → behaviour no-op (présent ≠ exécuté)
        diag = ability.execute_behaviour(self.state, msg.caster_id, target_id) or {}
        self.last = {"ability_type": msg.ability_type, "ported": True,
                     "caster": msg.caster_id, "target": msg.target_id, **diag}
        # `actual_target` n'est publie que quand la resolution a DEPLACE la cible : un diagnostic qui
        # le porte toujours ferait diverger toutes les empreintes des tests sur un no-op.
        if target_id != msg.target_id:
            self.last["actual_target"] = target_id
        # `On(UnitAbility=0xb)` (#928) — emis JUSTE AVANT le `0xc`, et sans son gate
        # `IsActiveAbility` : le natif publie `0xb` inconditionnellement, puis teste le kind pour
        # `0xc`. Consommateur porte : `1319 LegacyOfCombat` (l'attaque supplementaire de Kariyan).
        # Publie SEULEMENT s'il a declenche quelque chose (cf. `actual_target` ci-dessus : un champ
        # toujours present ferait diverger l'empreinte de tous les casts qui n'en declenchent pas).
        _trig = self._unit_ability(msg)
        if _trig:
            self.last["unit_ability_triggers"] = _trig
        # `On(UnitActiveAbility=0xc)` — emis APRES l'execution de la behaviour et AVANT
        # `AddFlagsAfterAbilityExecution` (ordre lu au decompile). L'ability qui vient de s'executer
        # beneficie donc encore de tout ce que ce vecteur consomme (ex. l'override de niveau 1180 que
        # son PORTEUR retire ICI, une fois le cast resolu).
        self._unit_active_ability(msg)
        self.last["flags"] = self._add_flags_after_execution(msg, ability)
        # #120 `On(UnitPostAbility=0xe)` — DERNIER evenement d'`ExecuteInternal`, apres
        # `AddFlagsAfterAbilityExecution`. Pendant exact du `0x2b` emis en tete : c'est lui qui
        # consomme les effets « le temps de CETTE ability » (ex. 1201 AnvilShield_FrozenAttackerAdvantage).
        self._post_unit_ability(msg)

    def _execute_for_replaced_target(self, msg, ability, new_target, op) -> None:
        """Voie CAST de `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteForReplacedTarget` : la
        re-entree est un `visit_ActiveAbilityMessage` NEUF sur la cible remplacante — mirror du
        `ActiveAbilityOperation$$Execute(caster, newTarget, abilityType, options)` natif, qui rejoue
        TOUTE la chaine (gate acteur-mort, gate de cible, un nouveau `On(0x2a = PreUnitAbility)`, la behaviour, puis
        `AddFlagsAfterAbilityExecution` + `On(0xe)`). `self.last` est donc celui de la re-entree,
        enrichi de la tracabilite du remplacement.

        `new_target is None` (tuile videe pendant la cascade) : no-op complet, cf.
        `operations/active_ability.execute_for_replaced_target`.

        ⚠ La re-entree passe par `_active_ability_operation`, PAS par `visit_ActiveAbilityMessage` :
        le natif re-entre dans `ActiveAbilityOperation$$Execute` sans repasser par
        `InputMessageProcessor$$Visit`, donc SANS son gate de message (#429-r1-r3). L'ecart serait
        inerte en pratique (`resolve_replaced_target` ne rend qu'un occupant VIVANT, cf.
        `operations/active_ability.get_unit`), mais un gate pose au mauvais rang est un fork, et
        c'est exactement ce que #120 avait ferme sur ce meme etage."""
        caster, ability_type = int(msg.caster_id), int(msg.ability_type)
        self.last = {"ability_type": ability_type, "ported": ability is not None,
                     "caster": caster, "target": msg.target_id,
                     "replaced_from": msg.target_id, "replaced_target": None,
                     "replaced_aborted": True}

        def _reenter(target_id: int):
            self._active_ability_operation(ActiveAbilityMessage(caster, target_id, ability_type))
            if isinstance(self.last, dict):
                self.last["replaced_from"] = msg.target_id
                self.last["replaced_target"] = target_id
            return self.last

        op(self.state, caster, new_target, _reenter)

    def _pre_unit_ability(self, msg) -> None:
        """`FUN_1800280e0(0x4d, .., 0x2a)` = `On(PreUnitAbility)` en tete d'`ExecuteInternal`.
        L'`AbilityEntities` de l'evenement est celui de l'ability : caster/actor = le CASTER,
        target = la cible du cast.
        `ability_type` = `df@0x130` (l'ability declenchante), lu par les gates `IsNormalAttack` /
        `AbilityHasAttackType` des consommateurs (cf. `abilities/attack_type.py`). `ranged` =
        `DSLFactory$$IsRangedAttack` (position-based, `_is_ranged_position`) — False si la cible est
        une TUILE ou si les positions manquent, comme partout ailleurs dans le port."""
        # Forme MODULE : l'attribut est relu a l'appel, donc une substitution posee sur
        # `dispatch.ability` mord quelle que soit la forme finale de cet import. Ce differe-ci
        # est mesure GRATUIT (`probe_485_imports_differes.py`) : hisse en `from ... import X`
        # il serait INERTE, exactement le gisement des 12 rouges de la famille #429-r1.
        ability_dispatch.pre_unit_ability_triggers(self.state, int(msg.caster_id), msg.target_id,
                                                   ranged=self._ranged(msg), profile=None,
                                                   ability_type=int(msg.ability_type))

    def _unit_ability(self, msg) -> list:
        """`FUN_1800280e0(0x4d, .., 0xb)` = `On(UnitAbility)` d'`ExecuteInternal` (#928), emis APRES
        l'execution de la behaviour et **SANS AUCUN GATE** -- le `IsActiveAbility` qui suit ne
        conditionne que le `0xc`. Il fire donc pour TOUTE ability qui traverse cette operation,
        attaque normale comprise. Voie ABILITY ici ; voie NORMALE dans
        `triggers/dispatch/attack.py::after_hit_normal_attack` (meme raison que #120 : un seul site
        natif, deux portes d'operation cote port).

        Rend les diagnostics des triggers declenches -- l'appelant ne les publie dans `self.last`
        que s'il y en a (un champ toujours present ferait diverger l'empreinte de tout cast qui
        n'en declenche aucun)."""
        return ability_dispatch.unit_ability_triggers(
            self.state, int(msg.caster_id), msg.target_id,
            ranged=self._ranged(msg), profile=None,
            ability_type=int(msg.ability_type)) or []

    def _unit_active_ability(self, msg) -> None:
        """`FUN_1800280e0(0x4d, .., 0xc)` = `On(UnitActiveAbility)` d'`ExecuteInternal`, emis SOUS LE GATE
        `StaticBattleRules.ActiveAbility$$IsActiveAbility(abilityType)` (le gate est applique dans le
        vecteur). Emis depuis la SEULE voie ABILITY : l'attaque normale est un `IsRegularAttack`, donc
        exclue par le gate natif -- la voie normale (`damage.py`) n'a rien a emettre."""
        ability_dispatch.unit_active_ability_triggers(
            self.state, int(msg.caster_id), msg.target_id,
            ranged=self._ranged(msg), profile=None,
            ability_type=int(msg.ability_type))

    def _post_unit_ability(self, msg) -> None:
        """`FUN_1800280e0(0x4d, .., 0xe)` = `On(UnitPostAbility)` en queue d'`ExecuteInternal` (apres
        `AddFlagsAfterAbilityExecution`)."""
        ability_dispatch.unit_post_ability_triggers(
            self.state, int(msg.caster_id), msg.target_id,
            ranged=self._ranged(msg), profile=None,
            ability_type=int(msg.ability_type))

    def _ranged(self, msg) -> bool:
        """`IdunBattleLogic.Entities.DSLFactory$$IsRangedAttack` = adjacence caster/cible (mirror
        `_is_ranged_position`). Cible-TUILE / entite absente -> False (melee, le defaut conservateur
        deja retenu par le helper)."""
        if msg.target_id is None:
            return False
        return _is_ranged_position(self.state, int(msg.caster_id), int(msg.target_id))

    def _add_flags_after_execution(self, msg, ability=None) -> dict:
        """#139 — queue d'`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal :
            skipEndTurn     = `IdunBattle.Operations.ActiveAbilityOperation$$GetSkipEndTurnFlag   = !ability.SetsEndTurnFlags().Evaluate(...)
            skipAbilityUsed = `IdunBattle.Operations.ActiveAbilityOperation$$GetSkipAbilityUsedFlag = !ability.SetsActiveAbilityUsedFlag(...)
            -> `IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution (flag 2 + FinishUnitTurn -> flags 1+3).
        Les overrides `options.skip*Flag` du message natif (ActiveAbilityOptions+0x49/+0x4b, sous-abilities/
        derived) ne sont pas transportes par notre ActiveAbilityMessage offline -> defaut false (aucun skip
        force par le caller), fidele au cast top-level."""
        from ..operations.turnflow import add_flags_after_ability_execution
        caster = int(msg.caster_id)
        if ability is not None:
            sets_end = ability.sets_end_turn_flags(self.state, caster)
            sets_used = ability.sets_active_ability_used_flag(self.state, caster)
        else:
            sets_end = sets_end_turn_flags_for(int(msg.ability_type), self.state, caster)
            sets_used = sets_active_ability_used_flag_for(int(msg.ability_type), self.state, caster)
        return add_flags_after_ability_execution(
            self.state, caster, skip_ability_used=not sets_used, skip_end_turn=not sets_end)
