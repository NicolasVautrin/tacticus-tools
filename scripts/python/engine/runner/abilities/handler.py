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
    On(0xb)   UnitAbility           (aucun consommateur porte)
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
                   UnstoppableMomentumReworkedAbility)
from .genestealer import CultDemagogueAbility, HeroicFusilladeAbility, VigilanceEternalAbility
from .deathguard import (RevitalizingMalignancyAbility, FlailSwingAbility, SpawnPoxwalkersAbility,
                         EntropyCannonsAbility, PlagueburstMortarAbility, PlagueWindAbility)
from .thousandsons import DoomboltAbility, HellfyreMissileRackAbility
from .blacklegion import (BringerOfDespairAbility, IncursionAbility, HadesAutocannonsAbility,
                          DaemonicOrdnanceAbility, FrenziedFiringAbilityCombat,
                          DrachnyenAbility, HeraldOfTheApocalypseAbility)
from .orks import (WaaaghAbility, SquigLaunchasAbility, SquigMineAbility, DakkaDakkaDakkaAbility,
                   RammingSpeedAbility)
from .darkangels import (PlasmaCannonAbility, DarkTalonStrikeAbility, DeathOnTheWindAbility,
                         HailstrikeAbility, SuperchargeAbility, ExemplarOfHateAbility,
                         CalibaniteGreatswordAbility)
from .ultramarines import (CombatRestorativesAbility, MortisRoundAbility, DeathFromAboveAbility,
                           MacroPlasmaIncineratorAbility, TacticalPrecisionAbility,
                           DutyEternalAbility)
from .custodes import MomentShackleAbility
from .bloodangels import SavageEchoesAbility, HammerOfWrathAbility
from .necrons import (HarbingerOfDestructionAbility, ResurrectionOrbAbility, ChronometronAbility,
                      MultiThreatEliminatorAbility, TunnelingHorrorAbility)
from .sisterhood import (SanctorumMissileAbility, SkyStrikeAbility, DevastatingRefrainAbility,
                         ThriceBlessedConflagrationAbility, BrazierOfHolyFireAbility)
from .tau import (HeavyRailRifleAbility, TwinSmartMissileSystemAbility, FightingRetreatAbility,
                  EarlyWarningOverrideAbility, InspiredToGreatnessAbility,
                  SeekerMissileFrequencyLockAbility, ExemplarOfTheKauyonAbility)
from .votann import (IronkinSteeljackAbility, AugmentedAssaultAbility, GravitonRifleAbility,
                     AncestralFortuneAbility)
from .aeldari import (EmpyricAmbushAbility, ExecutionerAbility, HarvesterOfSoulsAbility,
                      SilentDeathAbility)
from .spacewolves import GreatFrostAxeAbility, FoehammerAbility, GrapnelLauncherAbility
from .tyranids import (SporeMineLauncherAbility, AlphaWarriorAbility, FearOfTheUnseenAbility,
                       BurrowersAbility)
from .worldeaters import JakhalStimmsAbility, MurderousSwingAbility
from .admec import (SentinelDirectivesAbility, RadBombardmentAbility,
                    DefendTheDivineWorkAbility)
from .repair import RepairAbility, Repair_GalvanicFieldAbility
from .astramilitarum import (SupremeCommanderAbility, SendInTheNextWaveAbility,
                             MalleusRocketLauncherAbility, ForwardSpotterAbility,
                             FragBombAbility, BasiliskBarrageAbility)
from .emperorschildren import DoomSirenAbility
from .blacktemplars import FragstormGrenadeLauncherAbility
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
    TheQuickeningAbility.ABILITY_TYPE: TheQuickeningAbility,  # 1151 (Mephiston : teleport-echange tile-target + free melee attack faction-BloodAngels, #217)
    BlackRageAbility.ABILITY_TYPE: BlackRageAbility,                   # 1163 (Lucien bloodDeathCompany : setHealth 30% + 3 self-buffs + charge + attaque normale, #217)
    GauntletsOfUltramarAbility.ABILITY_TYPE: GauntletsOfUltramarAbility,  # 1000 (ultraCalgar : AoE 2 bandes adjacent 2 coups + surrounding r=2 Unobscured 1 coup, case-220 P0-DAMAGE)
    AberrantHypermorphAbility.ABILITY_TYPE: AberrantHypermorphAbility,  # 1166 (Biophagus genesBiophagus : summon genesSmnAberrant tile-target hex libre adjacent + attaque a l'apparition, case-220 P0)
    VigilanceEternalAbility.ABILITY_TYPE: VigilanceEternalAbility,     # 1202 (Tyrith custoKyrus : charge gap-close + attaque melee Power mono-cible 3 hits, #220)
    CordClawAbility.ABILITY_TYPE: CordClawAbility,                     # 1122 (Exitor-Rho admecRuststalker : 4x DirectDamage melee + self-buff coups additionnels 2 tours, case-220)
    RevitalizingMalignancyAbility.ABILITY_TYPE: RevitalizingMalignancyAbility,  # 1037 (deathRotbone : heal self+allies adj non-Imperial, split trait Chaos regular/chaos-cumul, case-220)
    FlailSwingAbility.ABILITY_TYPE: FlailSwingAbility,                 # 1042 (deathBlightlord DeathGuard : 3x Power melee mono-cible + InformWeapon no-op ; residu overkill flag, case-220)
    BringerOfDespairAbility.ABILITY_TYPE: BringerOfDespairAbility,     # 1022 (Angrax blackTerminator : 4x Power cible melee + 4x Power ennemi random adjacent-CASTER, splash factory attack, case-220 BL)
    FrenziedFiringAbilityCombat.ABILITY_TYPE: FrenziedFiringAbilityCombat,  # 1036 (Volk blackObliterator BlackLegion : AtomicGroup(op_Addition( SetCache(hitsNode) & Attack(cible, hits=Min(Cache(nrOfHits + #tuiles-adjacentes-marchables-sans-ennemi), maxNrOfHits)), SetCache(hitsNode) & Attack(AdjacentEnemies(TargetTile,1), hits=Direct(1), multi) )) ; famille ATTACK, HeavyRound ranged ; case-61 volet AoE COMBAT)
    PlasmaCannonAbility.ABILITY_TYPE: PlasmaCannonAbility,             # 1150 (darkaTerminator DarkAngels : 3x Plasma cible + 3x sur <=2 unites tirees directly-behind, native_factory attack, case-220)
    CombatRestorativesAbility.ABILITY_TYPE: CombatRestorativesAbility,  # 1002 (ultraApothecary : heal self+allies adj, split trait Imperial hpToHeal_2 / non-Imperial hpToHeal, PAS de cumul, case-220 P0-HEAL)
    MortisRoundAbility.ABILITY_TYPE: MortisRoundAbility,               # 1004 (ultraEliminatorSgt : AtomicGroup(Attack HeavyRound 1x + PushUnit cible 1 hex) ; wiring valide ; quirk HeavyWeapon double = residu cross-cutting non porte, case-220 UM)
    DeathFromAboveAbility.ABILITY_TYPE: DeathFromAboveAbility,         # 1003 (ultraInceptorSgt : spawn ultraSmnInceptor x StatAmount(TURNS_STARTED) tuiles adjacentes-cible SortByDistance(caster) cap-tuiles + on-appearance attaque normale Bolter cible, template SpawnSummon, case-220 UM)
    SavageEchoesAbility.ABILITY_TYPE: SavageEchoesAbility,             # 1230 (Cezare bloodTerminator : 4x Eviscerate melee + extraDmg x free-tiles + self-heal si HP<=50%, case-220 template ArmoriumCherub)
    HarbingerOfDestructionAbility.ABILITY_TYPE: HarbingerOfDestructionAbility,  # 1008 (necroPlasmancer : cible + N-1 ennemis random disque rayon-2 CASTER unobscured, 1x DirectDamage pierce-100, case-220 Necrons)
    ResurrectionOrbAbility.ABILITY_TYPE: ResurrectionOrbAbility,       # 1009 (necroOverlord Anuphet Necrons : SUMMON PUR (aucun revive) — Spawn(PickRandomly(CanAddUnit(AdjacentTiles(caster)), Min(Count(amis LivingMetal morts/ressuscites) + TURNS_STARTED(caster), 6)), necroSmnWarrior, WithStatsFromConfig), Execute plain, #116)
    ChronometronAbility.ABILITY_TYPE: ChronometronAbility,             # 1226 (necroChronomancer Thothmek Necrons : Foreach(SurroundingEnemies(caster, range=2), If(HasTrait(It, Summon), AddEffect(Stunned), AddEffect(Pinned)) & AddEffect(Chronometron_ExtraDamage)) ; porteur hors seed BC -> catalog_inject, #116)
    MultiThreatEliminatorAbility.ABILITY_TYPE: MultiThreatEliminatorAbility,  # 1006 (necroDestroyer Imospekh Necrons : ChainLeftOverHitsAttackDamage 6 coups Gauss + report des coups gaspilles (+extraHit par kill) sur l'ennemi adjacent-derniere-cible & disque rayon-2 caster unobscured, #116)
    FragstormGrenadeLauncherAbility.ABILITY_TYPE: FragstormGrenadeLauncherAbility,  # 1048 (templAggressor « Brother Burchard » Black Templars : ChainLeftOverHitsAttackDamage 6 coups Blast sur la cible, extraHits NULL, report des coups gaspilles sur Damageable(SurroundingEnemies(Owner, range 2) - Target) trie PV croissants puis SortTargetsByDamagePredictionSelector (priorite aux kills), #489)
    TunnelingHorrorAbility.ABILITY_TYPE: TunnelingHorrorAbility,       # 1011 (necroSmnDestroyer Necrons, cast TILE-TARGET : RemoveUnitFromItsTiles(Caster, true) -> le caster QUITTE le plateau (pos=null, alive=true) & RemoveAllForcedAttackTargets(Caster) & AddBondEffect(0x459 TunnelingHorror_PendingSummon -> la tuile visee, bondedEntity=Caster, PERMANENT) ; porteur summon SANS invocateur -> greffe sur un heros du pool ; #366-r1)
    BurrowersAbility.ABILITY_TYPE: BurrowersAbility,                   # 1023 (tyranSmnRipperSwarm + 5 tyranNpc2RipperSwarm* Tyranids, SELF-CAST : RemoveUnitFromItsTiles(Caster, true) -> le caster QUITTE le plateau (pos=null, alive=true) & RemoveAllForcedAttackTargets(Caster) & AddEffect(0x410 Burrowers_Hidden -> le CASTER, surcharge SANS source, PERMANENT) ; gate CASTER-dynamique `GetDynamicInvalidCasterReason` = casterTiles vide OU une tuile IsTemporary -> 4 ; 2e appelant de la primitive #366-r1, tranche 1 de `#366-r1-tunnel-family`)
    SanctorumMissileAbility.ABILITY_TYPE: SanctorumMissileAbility,     # 1062 (adeptMorvenn Morvenn Vahl Sisterhood : missile 2x Blast cible + 1x Blast adjacents-cible (hex Morvenn exclu) Unobscured, native_factory attack, case-220)
    IronkinSteeljackAbility.ABILITY_TYPE: IronkinSteeljackAbility,     # 1219 (votanMemnyr : summon votanSmnSteeljack hex libre adjacent-self + attaque a l'apparition, corps dedup IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour==AberrantHypermorph, case-220 Votann)
    AugmentedAssaultAbility.ABILITY_TYPE: AugmentedAssaultAbility,     # 1221 (votanBeserk Havyr : 4x Eviscerate melee mono-cible + AddDynamicStatModifierEffect(1541) FixedArmor NEGATIF sur la CIBLE, permanent, #113 Votann)
    GravitonRifleAbility.ABILITY_TYPE: GravitonRifleAbility,           # 1206 (votanIronmaster Vynn : 3x Physical range-2 + Stunned(1162) nrOfRounds ; owner-effect 1484 = +extraPierceRatio vs TerminatorArmour/MkXGravis/Mechanical, #113 Votann)
    AncestralFortuneAbility.ABILITY_TYPE: AncestralFortuneAbility,     # 1207 (votanUthar Uthar : self-buff +critChance(1485) & +blockChance(1486) 1 round, gates StatAmount(INITIAL)>0, puis 3x Plasma sur First(SortUnitsByDamageUtility(AdjacentEnemies)) ; reset persistent-data HORS perimetre, #113 Votann)
    ExecutionerAbility.ABILITY_TYPE: ExecutionerAbility,               # 1066 (Eldryon eldarFarseer Aeldari : Psychic ranged hits=RoundsStarted cible + si cible morte 1 ennemi random adjacent-cible, native_factory attack, case-220 §6.19)
    EmpyricAmbushAbility.ABILITY_TYPE: EmpyricAmbushAbility,           # 1232 (Lhykhis eldarLhykhis Aeldari, HORS CATALOGUE -> catalog_inject : FlyUnit(caster, First(SortTilesByUtility(Randomize(CanAddUnit(AdjacentTiles(cible)) - CasterTile), caster, 7))) & If(OwnerIsAlive, nrOfHits x Eviscerate melee mono-cible & AddEffect(1578 EmpyricAmbush -> la CIBLE, source = Owner, Direct(1) tour)) ; l'effet et son gate etaient portes par #589-r1-r1, la POSE manquait -> #589-r1-r1-r1)
    HarvesterOfSoulsAbility.ABILITY_TYPE: HarvesterOfSoulsAbility,     # 1067 (Maugan Ra eldarMauganRa Aeldari : ranged HeavyRound cible hits=If(HasMoved,2,3) + splash MinMaxDamage2 ennemis ring1-cible ∩ rayon-3 caster, native_factory attack, ExecuteAtomic, case-220 §6.19)
    SilentDeathAbility.ABILITY_TYPE: SilentDeathAbility,               # 1068 (Jain Zar eldarJainZar Aeldari : CHAINE DE DEGAT -- nrOfHits=3 coups Piercing melee sur la cible ADJACENTE, puis nrOfTargets=3 rebonds `Cache(PickRandomly(AdjacentUnits(maillon precedent) & <cache ennemis> - deja frappes, 1))`, memes bornes/profil/coups a chaque maillon ; `Group(..., GroupType.DamageChain)` ; #497)
    SkyStrikeAbility.ABILITY_TYPE: SkyStrikeAbility,                   # 1025 (adeptCelestine Celestine Sisterhood : charge tuile libre adjacente (vole, sans reach) + attaque melee normale base Attack+extraDmg profil/coups arme melee, template VigilanceEternal, case-220)
    GreatFrostAxeAbility.ABILITY_TYPE: GreatFrostAxeAbility,           # 1089 (spaceWulfen : glace zone cible+ring1 + attaque melee 4x Piercing mono-cible ATTACK-family, case-220 SW)
    GrapnelLauncherAbility.ABILITY_TYPE: GrapnelLauncherAbility,       # 1090 (spaceHound Tjark SpaceWolves : PULL de la cible d'1 hex vers le caster (arc AVANT, GetMinimumTiles180Front) PUIS 1x Physical ranged (range 3) puis VOL du caster sur la tuile d'origine liberee (sinon une voisine libre au hasard) ; quirk cible-adjacente = knockback 20% maxHP, #366-r1 tranche 2)
    FoehammerAbility.ABILITY_TYPE: FoehammerAbility,                   # 1097 (spaceRockfist Arjac SpaceWolves : Stunned(1162) cible + 1x Power ranged, degat + extraDmg x Count(heros morts/ressuscites), ATTACK-family, case-226)
    HammerOfWrathAbility.ABILITY_TYPE: HammerOfWrathAbility,           # 1153 (bloodIntercessor Mataneo BloodAngels : Infiltrate self + CHARGE tuile libre adj-cible <=range + 2x Power cible & 1x Physical ennemis adj-cible, ABILITY-family, degat DOUBLE si effet 1332 actif (HP<=healthPct), case-226)
    SporeMineLauncherAbility.ABILITY_TYPE: SporeMineLauncherAbility,   # 1145 (tyranBiovore Biovore MoW Tyranids : spawn tyranSmnSporeMine sur tuile-cible directe WithStatsFromConfig, corps IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$ExecuteBehaviour = IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour MOINS on-appearance ; mine inerte offline FloatingDeath non porte, case-220 §6.16)
    AlphaWarriorAbility.ABILITY_TYPE: AlphaWarriorAbility,             # 1112 (tyranWingedPrime Winged Prime Tyranids : spawn tyranSmnWarrior sur tuile-cible WithStatsFromConfig + attaque a l'apparition, corps IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$ExecuteBehaviour = template IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour AberrantHypermorph ; gate IsInTeamSynapseRange live ABSENT, case-220 §6.16)
    JakhalStimmsAbility.ABILITY_TYPE: JakhalStimmsAbility,             # 1131 (worldJakhal Macer WorldEaters : 4x Physical melee cible + AoE intersection AdjacentUnits(caster) & AdjacentFriends(target) + self-loss 25% PV courant (ChangeStat Subtract, Execute separe) ; free action ; native_factory attack, ExecuteAtomic 0x2a, case-220 §6.3)
    MurderousSwingAbility.ABILITY_TYPE: MurderousSwingAbility,         # 1137 (worldExecutions Tarvakh WorldEaters : 1x Piercing melee sur TOUS les ennemis adjacents au CASTER (AdjacentEnemies(caster), self-centre), degat If(Count(set) > 1, MinMaxDamage, Sum(MinMaxDamage, extraDmg)) reevalue PAR CIBLE ; native_factory attack ; face COMBAT du gisement [-D], case-decision-noop)
    SentinelDirectivesAbility.ABILITY_TYPE: SentinelDirectivesAbility,  # 1139 (admecDestroyer Sy-Gex AdeptusMechanicus : 1x Physical ranged cible + AddEffect Pinned/Suppressed, quasi-clone SpiritLeech sans heal/conditional, native_factory attack, ne finit pas le tour, case-220 §6.17)
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
    ThriceBlessedConflagrationAbility.ABILITY_TYPE: ThriceBlessedConflagrationAbility,  # 1187 (adeptExorcist Sisterhood MoW, groupe D : Foreach(1x Flame famille ABILITY sur la ligne CONTIGUE d'ennemis partant de la cible dans la direction qui en aligne le plus) + If(HasFaction(cible, Sisterhood), AddEffect(1401), AddEffect(1436)) sur la cible ALLIEE)
    # --- Lot #114 (TAU) : face COMBAT des abilities dont la face DECISION (playbook) etait deja portee.
    FightingRetreatAbility.ABILITY_TYPE: FightingRetreatAbility,  # 1081 (tauDarkstrider Tau HERO : AddEffect(1157 DmgReduction)+AddEffect(1158 HitReduction) sur les ennemis adjacents non-Steppable/Object + Foreach(Markerlight 1122) + Foreach(allies adjacents + soi, If(HasTrait RangedSpecialist, ActivateEffect 1515)) + If(nbEnnemisAdjacents>0, ResetTurn(soi), FinishTurn(soi)) ; duree TurnsUntilEndOfCurrentPlayersNextTurn ; self-cast)
    InspiredToGreatnessAbility.ABILITY_TYPE: InspiredToGreatnessAbility,  # 1082 (tauAunShi Aun'Shi Tau HERO : split UnitsThatCanHaveActiveAbilityReset(cible) / complementaire -> RepairOrHeal(hpToHeal) / RepairOrHeal(hpToHeal_2) + AddStatOverrideEffect(1180, ACTIVE_ABILITY_LEVEL = Min(niveau 1082 du caster, niveau de l'actif primaire de la cible)) + ResetActiveAbility ; unit-target allie)
    EarlyWarningOverrideAbility.ABILITY_TYPE: EarlyWarningOverrideAbility,  # 1077 (tauCrisis Re'vas Tau HERO : AddEffect x4 sur soi (1009 Overwatch_AutoAttack, 1144 SuppressCloseCombatWeakness, 1145 ReactivateOverwatch, 1149 Visual, TurnsFromRounds(1)) + Spawn(nrOfSummons=2 tauSmnDroneShield sur tuiles libres adjacentes-caster, WithStatsFromConfig) + on-appearance PerformAIAttack ; self-cast)
    SeekerMissileFrequencyLockAbility.ABILITY_TYPE: SeekerMissileFrequencyLockAbility,  # 1069 (#491 -- tauMarksman Sho'syl Tau HERO : le cast NE FRAPPE PAS (patron 2-phases de HeavyRailRifle, le degat HeavyRound du kit appartient a la triggered 1127 SeekerMissileFrequencyLock_Attack, NON portee) : AddEffect(1122 Markerlight -> cible, TurnsUntilEndOfCurrentPlayersNextTurn) & AddBondEffect(1123 _Target -> cible, bonde au caster) & AddBondEffect(1136 _Aiming -> caster, bonde a la cible), les deux bonds a duree DEFAUT ; unit-target, range=5 depuis config)
    ExemplarOfTheKauyonAbility.ABILITY_TYPE: ExemplarOfTheKauyonAbility,  # 1087 (tauShadowsun Commander Shadowsun Tau HERO : Teleport(Caster -> tuile cible libre adjacente a un allie) & If(OwnerIsAlive, AddEffect(1181 ExemplarOfTheKauyon_AdditionalHits sur soi) & PerformAIAttackFromCurrentPosition(Target) & RemoveEffect(1181)) & Spawn(tauSmnDroneCommandLink sur l'EX-tuile du caster, First(1) de CanAddUnit(exTile + SortByDistance(Randomize(AllTiles), exTile)), on-appearance AddTrait(Stationary)) ; tile-target -- #488)
    # --- Lot #112 : DarkAngels lot 1 (artefact natif = `<Ability>.ExecuteBehaviour` => arbres DSL).
    SuperchargeAbility.ABILITY_TYPE: SuperchargeAbility,               # 1103 (darkaHellblaster Sarquael : AddEffect(1208 Supercharge_ExtraPiercing) sur cible + <=2 PickRandomly(UnitsDirectlyBehind) POSE AVANT les attaques (elles en beneficient), TurnsFromRounds(1) & 1x Plasma minDmg/maxDmg sur la cible & 1x Plasma minDmg_2/maxDmg_2 sur ces memes unites ; native_factory attack, ExecuteAtomic 0x2a)
    ExemplarOfHateAbility.ABILITY_TYPE: ExemplarOfHateAbility,         # 1140 (darkaAsmodai Asmodai : AddEffect(1293 ExemplarOfHate_Target, TurnsFromRounds(2)) INCONDITIONNEL & If(grand-alliance Chaos de la cible, Pinned(1065) duree DEFAUT & override d'Attack + attaque normale libre + retrait, portes par le MEILLEUR allie DarkAngels a portee -- collapse S GetAttacker/SortAttackersByDamagePrediction))
    # --- case-bl-1029-1020 : les DEUX actives Black Legion HERO restees NO-OP (docs/rl/case-bl-1029-1020.md)
    DrachnyenAbility.ABILITY_TYPE: DrachnyenAbility,                   # 1029 (blackAbaddon Abaddon : SetHealth(Min(MaxHealth, hp[level])) & AddEffect(1471 Drachnyen_ExtraAttack -> soi, permanent) & UseActiveAbility(attaque NORMALE dirigee sur la cible) ; la triggered 1485 qui en decoule = residu nomme)
    HeraldOfTheApocalypseAbility.ABILITY_TYPE: HeraldOfTheApocalypseAbility,  # 1020 (blackHaarken Haarken : nrOfHits x Piercing sur la cible ET l'ennemi de la tuile DIRECTEMENT DERRIERE (TilesBehindInLine(CasterTile -> tuile cible, maxCount=2)) & AddEffect(1027 -> ces memes cibles) & TriggerAbility(BattleFatigue -> ennemis disque range=2 autour de la cible, cible incluse))
    # --- Famille PSYCHIC (case-psychic-aoe) : deux AoE Psychic HERO, jusqu'ici NO-OP offline. ---
    PlagueWindAbility.ABILITY_TYPE: PlagueWindAbility,                 # 1035 (deathTyphus Typhus DeathGuard : AoE CONCENTRIQUE 3 bandes ancree cible -- cible (minDmg/maxDmg) + adjacents-cible (minDmg_2/maxDmg_2) + adjacents-d'un-secondaire moins cible/secondaires (minDmg_3/maxDmg_3), 1 coup chacune, native_factory ABILITY, ExecuteAtomic 0x4a + 3 Group 0x4b/4c/4d)
    DoomboltAbility.ABILITY_TYPE: DoomboltAbility,                     # 1102 (thousAhriman Ahriman ThousandSons : Min(nrOfHits + Count(hexes en Feu), 9) coups Psychic REPARTIS par division entiere sur les ennemis <=range non obscurcis, tries SortUnitsByDamageUtility avec la CIBLE forcee en tete ; native_factory ATTACK, ExecuteAtomic 0x61)
    HellfyreMissileRackAbility.ABILITY_TYPE: HellfyreMissileRackAbility,  # 1088 (thousTerminator « Toth » ThousandSons : Execute(SortedAttackSeries(Caster, Target, nrOfHits coups HeavyRound, FromTrigger(NonSteppableOrObjectUnits(Enemies(Caster, AllUnits)), HasTakenDamageOfDamageProfileThisTurn(ActiveTarget, Psychic)), nrOfHits coups HeavyRound)) -- le 2e volet frappe TOUT ennemi du plateau ayant pris du PSYCHIC ce tour, cible du message COMPRISE ; native_factory ABILITY, PAS d'ExecuteAtomic ; masque 0x4002 MIGRE depuis `TARGETING_OPTIONS_UNPORTED` ; #487)
    # --- case #154 : EmperorsChildren DoomSiren + Tyranids FearOfTheUnseen (canal DirectDamage) ---
    DoomSirenAbility.ABILITY_TYPE: DoomSirenAbility,                   # 1199 (emperKakophonist « Adamatar » : UN leaf combine — nrOfHits coups DirectDamage MELEE sur la cible + PickRandomly(nrOfUnits) ennemis adjacents A LA CIBLE (Damageable), passe id-triee unique ; puis Foreach(UnitsDamagedThisPhase(caster), If(IsDead(It) & HasFlag(It, 8=Overkilled), AddStaticStatModifierEffect(caster, 1431 DoomSiren_ExtraHit, EXTRA_HITS, Direct(1), PERMANENT))) ; ExecuteAtomic 0x2a)
    FearOfTheUnseenAbility.ABILITY_TYPE: FearOfTheUnseenAbility,       # 1115 (tyranDeathleaper « Deathleaper » Tyranids : POSEUR D'EFFETS pur, AUCUN degat au cast — Execute plain de (If(NOT HasFlag(Self, Moved), AddEffect(1065 Pinned -> Enemies(NonSteppableOrObjectUnits(SurroundingUnits(Self, range, includeCenter))), duree DEFAUT) + TriggerAbility(memes ennemis, 1025 BattleFatigue)) + AddEffect(1238 TeleportingIn -> Self) + AddEffect(1239 ExtraDamage -> Self)), les 2 effets self a Sum(TurnsFromRounds(1), Direct(1)) TOURS ; le DirectDamage vit en PHASE 2 dans l'effet 1239 (canal coups additionnels #179))
    CalibaniteGreatswordAbility.ABILITY_TYPE: CalibaniteGreatswordAbility,  # 1189 (darkaCompanion Forcas : TOGGLE de posture = If(HasEffect(Self,1404 Strike), AddEffect(1405 Sweep)+RemoveStrikeEffects(1404/1425/1009/1406), AddStrikeEffects(1404/1425/1009)+RemoveEffect(1405)) ; aucun degat, aucun tirage, ne finit pas le tour ; les observables Sweep/Overwatch vivent dans les TRIGGERED, hors port)
    # --- case-231 : socle `IsCharging` (BattleQuery$$IsCharging = adjacence + ChargedUnitIds@+0x190)
    #     + `force_crit` (octet +5 du Nullable<AttackOptions>). Les DEUX abilities du lot.
    TacticalPrecisionAbility.ABILITY_TYPE: TacticalPrecisionAbility,   # 1154 (ultraTitus Titus : If(IsCharging(caster,cible), ChangeStat(+extraCritDmg) & 1x Bolter FORCE-CRIT sur la cible & ChangeStat(revert), 3x Chain sur TOUS les AdjacentEnemies(caster)) ; ExecuteAtomic, branches EXCLUSIVES)
    MomentShackleAbility.ABILITY_TYPE: MomentShackleAbility,           # 1184 (custoTrajann Trajann : self-cast Heal(hpToHeal) & AddDynamicStatModifierEffect(1391 BlockChance) & (1392 BlockDamage) & AddEffect(1393 marqueur de la triggered MomentShackle_Attack), TurnsFromRounds(nrOfRounds=1) ; aucun degat)
    # --- case-decision-noop : gisement `[-D]` (la DECISION choisit, l'EXECUTION etait un NO-OP). ---
    # --- #287 : face COMBAT de SorcerousFacade, dont la face DECISION etait deja portee (#27-4e).
    SorcerousFacadeAbility.ABILITY_TYPE: SorcerousFacadeAbility,       # 1100 (thousTzaangor « Yazaghor » ThousandSons : cast sur un ALLIE Psyker -> AddEffect(1204 SorcerousFacade_AdditionalHits -> Caster + Target, TurnsFromRounds(1)) & UseActiveAbility(attaque NORMALE dirigee sur `sel` = l'ENNEMI le plus proche de `ValidNormalAttackTargets`) & KillDeadUnits(Caster, sel) & TriggerAbilityDelayed(Owner, 1180 SorcerousFacade_Switch, 3) -> SwitchPosition(Caster, Target) ; masque 0x402 MIGRE depuis `TARGETING_OPTIONS_UNPORTED`)
    # --- #299 : REPARATION REGULIERE. La face DECISION etait complete (#296/#298 : enumeration,
    # ciblage, prediction, choix IA) et la face COMBAT etait un NO-OP -- cast accepte, tour consomme,
    # ZERO PV restaure. Les deux ids sont EXACTEMENT
    # `idun...StaticBattleRules.ActiveAbility$$IsRegularRepair`.
    RepairAbility.ABILITY_TYPE: RepairAbility,                         # 28 (ability DERIVEE du trait `Mechanic`, donc ABSENTE du gameconfig et multi-factions : admecDominus / admecManipulus / necroSpyder / orksBigMek / votanIronmaster ; `Repair(Caster, ActiveTarget, Attack x Max(WeaponHighestHits,1), ForRepair)` -> `RepairUnitOperation`)
    Repair_GalvanicFieldAbility.ABILITY_TYPE: Repair_GalvanicFieldAbility,  # 1119 (admecManipulus, passif `GalvanicField` : la reparation HERITEE de 28 & volet attaque -- AddStatOverrideEffect(1242 ATTACK = Min(maxDmg, Attack_Initial x dmgPct)) & PerformAIAttackFromCurrentPosition & RemoveEffect, patron TheQuickening)
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
        # #429-r1 GATE CIBLE-MORTE -- mirror d'`ActiveAbilityOperation$$ExecuteInternal` :
        #     if (IsDeadUnitAndNotAllowedByAbility(abilityType, target)) return 0;
        # Le natif le place AVANT `IsInvalidTarget` (ordre relu au decompile, cf. l'en-tete de ce
        # module), donc ici. Son gate est le slot 0x11 `CanContinueOnDeadTarget`, qui lit le bit 38
        # `AllowDeadTarget` du masque de CONTINUE -- `False` pour toutes les abilities du binaire
        # sauf `GreatFrostAxe` (1089). Detail et mesure : `operations/active_ability.py`.
        if is_dead_unit_and_not_allowed_by_ability(self.state, klass, msg.target_id):
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
        reason = is_invalid_target(self.state, int(msg.caster_id), msg.target_id, ability)
        if reason:
            self.last = {"ability_type": msg.ability_type, "ported": ability is not None,
                         "caster": msg.caster_id, "target": msg.target_id,
                         "invalid_target": int(reason)}
            return
        # #120bis SNAPSHOT DE TUILE de la cible — `IdunBattle.Operations.ActiveAbilityOperation$$
        # GetAbilityEntities` fige `AbilityEntities@+0x38 = EntityExtensions.GetTiles(finalTarget)`
        # AVANT le `On(0x2a = PreUnitAbility)`. C'est ce fige-la que la re-resolution ci-dessous confronte a
        # l'occupation REELLE d'apres la cascade. Pris ICI, au rang natif (juste apres les gates).
        _target_tiles = get_tiles(self.state, msg.target_id)
        # #120 `On(PreUnitAbility=0x2a)` — le vecteur d'OPERATION, emis pour TOUTE ability qui passe
        # les gates, portee ou non (il ne depend pas de la behaviour : cf. le meme raisonnement que
        # les FLAGS de tour #139 ci-dessous). Emis AVANT l'execution, comme le natif.
        self._pre_unit_ability(msg)
        # #133 GATE ACTEUR-MORT **POST-`On(0x2a = PreUnitAbility)`** — mirror du test qui suit IMMEDIATEMENT
        # l'evenement dans `ActiveAbilityOperation$$ExecuteInternal` (lu verbatim au decompile) :
        #     FUN_1800280e0(0x4d, .., 0x2a);
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
        _replaced, _new_target = resolve_replaced_target(self.state, msg.target_id, _target_tiles)
        if _replaced:
            self._execute_for_replaced_target(msg, ability, _new_target,
                                              execute_for_replaced_target)
            return
        if ability is None:
            self.unported.add(int(msg.ability_type))   # #93/#95 : rend le no-op VISIBLE (plus muet)
            self.last = {"ability_type": msg.ability_type, "ported": False}
            # #139 : les FLAGS de tour sont poses par le natif pour TOUTE ability executee, independamment
            # de sa behaviour -> on les mirror MEME quand la behaviour n'est pas portee (turn-flow fidele).
            self._unit_active_ability(msg)             # `On(0xc)` : AVANT les flags (ordre natif)
            self.last["flags"] = self._add_flags_after_execution(msg)
            self._post_unit_ability(msg)               # `On(0xe)` : dernier evenement, apres les flags
            return                            # ability non portée → behaviour no-op (présent ≠ exécuté)
        diag = ability.execute_behaviour(self.state, msg.caster_id, msg.target_id) or {}
        self.last = {"ability_type": msg.ability_type, "ported": True,
                     "caster": msg.caster_id, "target": msg.target_id, **diag}
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
        """`FUN_1800280e0(0x4d, .., 0x2a)` en tete d'`ExecuteInternal`. L'`AbilityEntities` de
        l'evenement est celui de l'ability : caster/actor = le CASTER, target = la cible du cast.
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

    def _unit_active_ability(self, msg) -> None:
        """`FUN_1800280e0(0x4d, .., 0xc)` d'`ExecuteInternal`, emis SOUS LE GATE
        `StaticBattleRules.ActiveAbility$$IsActiveAbility(abilityType)` (le gate est applique dans le
        vecteur). Emis depuis la SEULE voie ABILITY : l'attaque normale est un `IsRegularAttack`, donc
        exclue par le gate natif -- la voie normale (`damage.py`) n'a rien a emettre."""
        ability_dispatch.unit_active_ability_triggers(
            self.state, int(msg.caster_id), msg.target_id,
            ranged=self._ranged(msg), profile=None,
            ability_type=int(msg.ability_type))

    def _post_unit_ability(self, msg) -> None:
        """`FUN_1800280e0(0x4d, .., 0xe)` en queue d'`ExecuteInternal` (apres
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
