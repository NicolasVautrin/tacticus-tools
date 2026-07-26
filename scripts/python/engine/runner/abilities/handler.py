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
                   GauntletsOfUltramarAbility, AberrantHypermorphAbility, CordClawAbility)
from .genestealer import CultDemagogueAbility, HeroicFusilladeAbility, VigilanceEternalAbility
from .deathguard import (RevitalizingMalignancyAbility, FlailSwingAbility, SpawnPoxwalkersAbility,
                         EntropyCannonsAbility, PlagueburstMortarAbility)
from .blacklegion import (BringerOfDespairAbility, IncursionAbility, HadesAutocannonsAbility,
                          DaemonicOrdnanceAbility)
from .orks import WaaaghAbility, SquigLaunchasAbility, SquigMineAbility
from .darkangels import PlasmaCannonAbility
from .ultramarines import (CombatRestorativesAbility, MortisRoundAbility, DeathFromAboveAbility,
                           MacroPlasmaIncineratorAbility)
from .bloodangels import SavageEchoesAbility
from .necrons import (HarbingerOfDestructionAbility, ResurrectionOrbAbility, ChronometronAbility,
                      MultiThreatEliminatorAbility)
from .sisterhood import (SanctorumMissileAbility, SkyStrikeAbility, DevastatingRefrainAbility,
                         ThriceBlessedConflagrationAbility)
from .tau import HeavyRailRifleAbility, TwinSmartMissileSystemAbility
from .votann import (IronkinSteeljackAbility, AugmentedAssaultAbility, GravitonRifleAbility,
                     AncestralFortuneAbility)
from .aeldari import ExecutionerAbility, HarvesterOfSoulsAbility
from .spacewolves import GreatFrostAxeAbility
from .tyranids import SporeMineLauncherAbility, AlphaWarriorAbility
from .worldeaters import JakhalStimmsAbility
from .admec import SentinelDirectivesAbility
from .astramilitarum import (SupremeCommanderAbility, SendInTheNextWaveAbility,
                             MalleusRocketLauncherAbility, ForwardSpotterAbility)

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
    MasterOfTheTutelariesAbility.ABILITY_TYPE: MasterOfTheTutelariesAbility,  # 1096 (Abraxas : effet 1197 + summon Pink Horror tile-target + Screamer sur Psychic, #202-C)
    StormcallerAbility.ABILITY_TYPE: StormcallerAbility,               # 1113 (Njal : glace zone cible+ring1 + 3x Psychic ennemis-sur-glace + stun Flying, #217)
    TheQuickeningAbility.ABILITY_TYPE: TheQuickeningAbility,  # 1151 (Mephiston : teleport-echange tile-target + free melee attack faction-BloodAngels, #217)
    BlackRageAbility.ABILITY_TYPE: BlackRageAbility,                   # 1163 (Lucien bloodDeathCompany : setHealth 30% + 3 self-buffs + charge + attaque normale, #217)
    GauntletsOfUltramarAbility.ABILITY_TYPE: GauntletsOfUltramarAbility,  # 1000 (ultraCalgar : AoE 2 bandes adjacent 2 coups + surrounding r=2 Unobscured 1 coup, case-220 P0-DAMAGE)
    AberrantHypermorphAbility.ABILITY_TYPE: AberrantHypermorphAbility,  # 1166 (Biophagus genesBiophagus : summon genesSmnAberrant tile-target hex libre adjacent + attaque a l'apparition, case-220 P0)
    VigilanceEternalAbility.ABILITY_TYPE: VigilanceEternalAbility,     # 1202 (Tyrith custoKyrus : charge gap-close + attaque melee Power mono-cible 3 hits, #220)
    CordClawAbility.ABILITY_TYPE: CordClawAbility,                     # 1122 (Exitor-Rho admecRuststalker : 4x DirectDamage melee + self-buff coups additionnels 2 tours, case-220)
    RevitalizingMalignancyAbility.ABILITY_TYPE: RevitalizingMalignancyAbility,  # 1037 (deathRotbone : heal self+allies adj non-Imperial, split trait Chaos regular/chaos-cumul, case-220)
    FlailSwingAbility.ABILITY_TYPE: FlailSwingAbility,                 # 1042 (deathBlightlord DeathGuard : 3x Power melee mono-cible + InformWeapon no-op ; residu overkill flag, case-220)
    BringerOfDespairAbility.ABILITY_TYPE: BringerOfDespairAbility,     # 1022 (Angrax blackTerminator : 4x Power cible melee + 4x Power ennemi random adjacent-CASTER, splash factory attack, case-220 BL)
    PlasmaCannonAbility.ABILITY_TYPE: PlasmaCannonAbility,             # 1150 (darkaTerminator DarkAngels : 3x Plasma cible + 3x sur <=2 unites tirees directly-behind, native_factory attack, case-220)
    CombatRestorativesAbility.ABILITY_TYPE: CombatRestorativesAbility,  # 1002 (ultraApothecary : heal self+allies adj, split trait Imperial hpToHeal_2 / non-Imperial hpToHeal, PAS de cumul, case-220 P0-HEAL)
    MortisRoundAbility.ABILITY_TYPE: MortisRoundAbility,               # 1004 (ultraEliminatorSgt : AtomicGroup(Attack HeavyRound 1x + PushUnit cible 1 hex) ; wiring valide ; quirk HeavyWeapon double = residu cross-cutting non porte, case-220 UM)
    DeathFromAboveAbility.ABILITY_TYPE: DeathFromAboveAbility,         # 1003 (ultraInceptorSgt : spawn ultraSmnInceptor x StatAmount(TURNS_STARTED) tuiles adjacentes-cible SortByDistance(caster) cap-tuiles + on-appearance attaque normale Bolter cible, template SpawnSummon, case-220 UM)
    SavageEchoesAbility.ABILITY_TYPE: SavageEchoesAbility,             # 1230 (Cezare bloodTerminator : 4x Eviscerate melee + extraDmg x free-tiles + self-heal si HP<=50%, case-220 template ArmoriumCherub)
    HarbingerOfDestructionAbility.ABILITY_TYPE: HarbingerOfDestructionAbility,  # 1008 (necroPlasmancer : cible + N-1 ennemis random disque rayon-2 CASTER unobscured, 1x DirectDamage pierce-100, case-220 Necrons)
    ResurrectionOrbAbility.ABILITY_TYPE: ResurrectionOrbAbility,       # 1009 (necroOverlord Anuphet Necrons : SUMMON PUR (aucun revive) — Spawn(PickRandomly(CanAddUnit(AdjacentTiles(caster)), Min(Count(amis LivingMetal morts/ressuscites) + TURNS_STARTED(caster), 6)), necroSmnWarrior, WithStatsFromConfig), Execute plain, #116)
    ChronometronAbility.ABILITY_TYPE: ChronometronAbility,             # 1226 (necroChronomancer Thothmek Necrons : Foreach(SurroundingEnemies(caster, range=2), If(HasTrait(It, Summon), AddEffect(Stunned), AddEffect(Pinned)) & AddEffect(Chronometron_ExtraDamage)) ; porteur hors seed BC -> catalog_inject, #116)
    MultiThreatEliminatorAbility.ABILITY_TYPE: MultiThreatEliminatorAbility,  # 1006 (necroDestroyer Imospekh Necrons : ChainLeftOverHitsAttackDamage 6 coups Gauss + report des coups gaspilles (+extraHit par kill) sur l'ennemi adjacent-derniere-cible & disque rayon-2 caster unobscured, #116)
    SanctorumMissileAbility.ABILITY_TYPE: SanctorumMissileAbility,     # 1062 (adeptMorvenn Morvenn Vahl Sisterhood : missile 2x Blast cible + 1x Blast adjacents-cible (hex Morvenn exclu) Unobscured, native_factory attack, case-220)
    IronkinSteeljackAbility.ABILITY_TYPE: IronkinSteeljackAbility,     # 1219 (votanMemnyr : summon votanSmnSteeljack hex libre adjacent-self + attaque a l'apparition, corps dedup IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour==AberrantHypermorph, case-220 Votann)
    AugmentedAssaultAbility.ABILITY_TYPE: AugmentedAssaultAbility,     # 1221 (votanBeserk Havyr : 4x Eviscerate melee mono-cible + AddDynamicStatModifierEffect(1541) FixedArmor NEGATIF sur la CIBLE, permanent, #113 Votann)
    GravitonRifleAbility.ABILITY_TYPE: GravitonRifleAbility,           # 1206 (votanIronmaster Vynn : 3x Physical range-2 + Stunned(1162) nrOfRounds ; owner-effect 1484 = +extraPierceRatio vs TerminatorArmour/MkXGravis/Mechanical, #113 Votann)
    AncestralFortuneAbility.ABILITY_TYPE: AncestralFortuneAbility,     # 1207 (votanUthar Uthar : self-buff +critChance(1485) & +blockChance(1486) 1 round, gates StatAmount(INITIAL)>0, puis 3x Plasma sur First(SortUnitsByDamageUtility(AdjacentEnemies)) ; reset persistent-data HORS perimetre, #113 Votann)
    ExecutionerAbility.ABILITY_TYPE: ExecutionerAbility,               # 1066 (Eldryon eldarFarseer Aeldari : Psychic ranged hits=RoundsStarted cible + si cible morte 1 ennemi random adjacent-cible, native_factory attack, case-220 §6.19)
    HarvesterOfSoulsAbility.ABILITY_TYPE: HarvesterOfSoulsAbility,     # 1067 (Maugan Ra eldarMauganRa Aeldari : ranged HeavyRound cible hits=If(HasMoved,2,3) + splash MinMaxDamage2 ennemis ring1-cible ∩ rayon-3 caster, native_factory attack, ExecuteAtomic, case-220 §6.19)
    SkyStrikeAbility.ABILITY_TYPE: SkyStrikeAbility,                   # 1025 (adeptCelestine Celestine Sisterhood : charge tuile libre adjacente (vole, sans reach) + attaque melee normale base Attack+extraDmg profil/coups arme melee, template VigilanceEternal, case-220)
    GreatFrostAxeAbility.ABILITY_TYPE: GreatFrostAxeAbility,           # 1089 (spaceWulfen : glace zone cible+ring1 + attaque melee 4x Piercing mono-cible ATTACK-family, case-220 SW)
    SporeMineLauncherAbility.ABILITY_TYPE: SporeMineLauncherAbility,   # 1145 (tyranBiovore Biovore MoW Tyranids : spawn tyranSmnSporeMine sur tuile-cible directe WithStatsFromConfig, corps IdunBattleLogic.Entities.Abilities.Active.Loki.SporeMineLauncherAbility$$ExecuteBehaviour = IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour MOINS on-appearance ; mine inerte offline FloatingDeath non porte, case-220 §6.16)
    AlphaWarriorAbility.ABILITY_TYPE: AlphaWarriorAbility,             # 1112 (tyranWingedPrime Winged Prime Tyranids : spawn tyranSmnWarrior sur tuile-cible WithStatsFromConfig + attaque a l'apparition, corps IdunBattleLogic.Entities.Abilities.Active.Loki.AlphaWarriorAbility$$ExecuteBehaviour = template IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour AberrantHypermorph ; gate IsInTeamSynapseRange live ABSENT, case-220 §6.16)
    JakhalStimmsAbility.ABILITY_TYPE: JakhalStimmsAbility,             # 1131 (worldJakhal Macer WorldEaters : 4x Physical melee cible + AoE intersection AdjacentUnits(caster) & AdjacentFriends(target) + self-loss 25% PV courant (ChangeStat Subtract, Execute separe) ; free action ; native_factory attack, ExecuteAtomic 0x2a, case-220 §6.3)
    SentinelDirectivesAbility.ABILITY_TYPE: SentinelDirectivesAbility,  # 1139 (admecDestroyer Sy-Gex AdeptusMechanicus : 1x Physical ranged cible + AddEffect Pinned/Suppressed, quasi-clone SpiritLeech sans heal/conditional, native_factory attack, ne finit pas le tour, case-220 §6.17)
    SupremeCommanderAbility.ABILITY_TYPE: SupremeCommanderAbility,     # 1028 (astraCreed Creed AstraMilitarum : ExecuteAtomic(Spawn nrOfSummons gardes hex libres adjacents WithStatsFromConfig) puis Execute(PerformAIAction(UnitsWithIds(SurroundingFriends(range), affectedUnitIds), asGroup=1, resetTurnFlags=1)) — 1er consommateur du debloqueur PerformAIAction, case-perform-ai-action)
    WaaaghAbility.ABILITY_TYPE: WaaaghAbility,                         # 1058 (orksWarboss Orks : 5 Execute successifs IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour — Spawn(2 Ork Boyz adjacents) / buff 1099+1100+1101 (caster + allies adjacents + TOUS les allies Orks, 1 round) / charge MoveUnit(movement+extraMovement) / attaque normale si adjacent / PerformAIAction(Friends(UnitsWithVisualId(orksOrkBoys)) BOARD-WIDE, asGroup=1, resetTurnFlags=1) — 2e consommateur PerformAIAction, tache #94)
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
    DevastatingRefrainAbility.ABILITY_TYPE: DevastatingRefrainAbility,  # 1188 (adeptExorcist Sisterhood MoW : AddEffect(1403 Attack -> la MoW) + AddBondEffect(1402 Target -> tuile ciblee + 3 voisines {3,1,5}/{0,2,4} selon le cote) ; tile-target)
    SquigMineAbility.ABILITY_TYPE: SquigMineAbility,                   # 1201 (orksRukkatrukk Orks MoW : AddEffect(1441 SquigMine_Tile -> tuile ciblee + PickRandomly(nrOfTiles) dans le disque range=2 libre/sans-mine), TurnsFromRounds(nrOfRounds) ; tile-target)
    MalleusRocketLauncherAbility.ABILITY_TYPE: MalleusRocketLauncherAbility,  # 1142 (astraOrdnanceBattery AstraMilitarum MoW : Inform + AddBondEffect(1308) + AddEffect(1309 PendingTarget) + AddEffect(1310 SpottedTarget), tous sur la TUILE ciblee ; tile-target)
    # --- Lot #90 groupes B/C/D : les 5 abilities MoW restantes (cf. docs/rl/case-90-mow-effect-posers.md).
    # B = attaque DSL filtree par un ETAT + entretien de cet etat ; C = template SPAWN ; D = composite lourd.
    TwinSmartMissileSystemAbility.ABILITY_TYPE: TwinSmartMissileSystemAbility,  # 1161 (tauBroadside Tau MoW, groupe B : 3x Blast famille ABILITY sur TOUT ennemi porteur de Markerlight(1122) + refresh du marquage sur la cible (ChangeEffectTurns ChangeType.Add sinon AddEffect), TurnsFromRounds(2) ; unit-target)
    PlagueburstMortarAbility.ABILITY_TYPE: PlagueburstMortarAbility,   # 1169 (deathCrawler DeathGuard MoW, groupe B : 3x Toxic + Pinned(1065) sur cible+adjacents FILTRES par le predicat aura-Contagion/armure-reduite, + Contaminated(1244) sur la cible + nrOfTiles-1 tuiles adjacentes tirees ; unit-target)
    ForwardSpotterAbility.ABILITY_TYPE: ForwardSpotterAbility,         # 1143 (astraOrdnanceBattery AstraMilitarum MoW, groupe C : Spawn(nrOfSummons=1 astraSmnGuardsman sur tuile libre adjacente a la cible, WithStatsFromConfig) + on-appearance PerformAIAttack ; template SpawnSummon)
    DaemonicOrdnanceAbility.ABILITY_TYPE: DaemonicOrdnanceAbility,     # 1148 (blackForgefiend BlackLegion MoW, groupe D : ChangeStat(+extraCritDmg CRIT_DAMAGE) -> 3x Plasma famille ATTACK sur les ennemis deja sur une tuile EN FEU du triangle -> ChangeStat(-extraCritDmg) -> If(HasEffect 1316) AddOrUpdateStaticStatModifier((usages+1) x extraCritChance sur CRIT_CHANCE) -> AddEffect(Fire -> triangle) ; 2-phases par construction)
    ThriceBlessedConflagrationAbility.ABILITY_TYPE: ThriceBlessedConflagrationAbility,  # 1187 (adeptExorcist Sisterhood MoW, groupe D : Foreach(1x Flame famille ABILITY sur la ligne CONTIGUE d'ennemis partant de la cible dans la direction qui en aligne le plus) + If(HasFaction(cible, Sisterhood), AddEffect(1401), AddEffect(1436)) sur la cible ALLIEE)
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
        # #70 GATE ACTEUR-MORT (mirror `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` :
        # `if (EntityExtensions.IsUnit(caster) && UnitExtensions.IsDead(caster)) return 0;`). Un caster MORT
        # (hp<1, non-Fled ; `IdunBattle.Entities.UnitExtensions$$IsDead`) => l'ability est un NO-OP complet AVANT toute
        # execution : aucune behaviour, aucun degat, AUCUN flag de tour (le natif retourne 0 en amont du
        # `AddFlagsAfterAbilityExecution`). MEME gate que l'attaque normale (#139, cf. damage.py). Inerte pour
        # tout caster vivant (les casts legitimes partent d'unites vivantes) -> zero regression. cf. case-70.
        from ..components import unit_is_dead
        caster = self.state.get_entity(int(msg.caster_id))
        if unit_is_dead(caster):
            self.last = {"ability_type": msg.ability_type, "ported": None,
                         "caster": msg.caster_id, "target": msg.target_id, "actor_dead": True}
            return
        klass = ABILITY_CLASSES.get(int(msg.ability_type))
        if klass is None:
            self.unported.add(int(msg.ability_type))   # #93/#95 : rend le no-op VISIBLE (plus muet)
            self.last = {"ability_type": msg.ability_type, "ported": False}
            # #139 : les FLAGS de tour sont poses par le natif pour TOUTE ability executee, independamment
            # de sa behaviour -> on les mirror MEME quand la behaviour n'est pas portee (turn-flow fidele).
            self.last["flags"] = self._add_flags_after_execution(msg)
            return                            # ability non portée → behaviour no-op (présent ≠ exécuté)
        ability = klass()
        # #115 GATE DE CIBLE (mirror `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` :
        # `if (IsInvalidTarget(caster, casterTiles, target)) return 0;`). Le natif sort ICI, en amont
        # du 1er `AActiveAbility.Execute` de la behaviour ET d'`AddFlagsAfterAbilityExecution` -> le
        # cast ne mute rien et ne consomme PAS l'activation (`actionConsumed=false`, cf. case-111).
        # Le filtre + son point d'extension par ability vivent dans `targeting.py` ; une ability dont
        # les `TARGETING_OPTIONS` n'ont pas ete RE-lues n'est PAS gatee (aucun refus invente).
        reason = is_invalid_target(self.state, int(msg.caster_id), msg.target_id, ability)
        if reason:
            self.last = {"ability_type": msg.ability_type, "ported": True,
                         "caster": msg.caster_id, "target": msg.target_id,
                         "invalid_target": int(reason)}
            return
        diag = ability.execute_behaviour(self.state, msg.caster_id, msg.target_id) or {}
        self.last = {"ability_type": msg.ability_type, "ported": True,
                     "caster": msg.caster_id, "target": msg.target_id, **diag}
        self.last["flags"] = self._add_flags_after_execution(msg, ability)

    def _add_flags_after_execution(self, msg, ability=None) -> dict:
        """#139 — queue d'`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal :
            skipEndTurn     = `IdunBattle.Operations.ActiveAbilityOperation$$GetSkipEndTurnFlag   = !ability.SetsEndTurnFlags().Evaluate(...)
            skipAbilityUsed = `IdunBattle.Operations.ActiveAbilityOperation$$GetSkipAbilityUsedFlag = !ability.SetsActiveAbilityUsedFlag(...)
            -> `IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution (flag 2 + FinishUnitTurn -> flags 1+3).
        Les overrides `options.skip*Flag` du message natif (ActiveAbilityOptions+0x49/+0x4b, sous-abilities/
        derived) ne sont pas transportes par notre ActiveAbilityMessage offline -> defaut false (aucun skip
        force par le caller), fidele au cast top-level."""
        from ..operations.turnflow import add_flags_after_ability_execution
        from .base import sets_end_turn_flags_for, sets_active_ability_used_flag_for
        caster = int(msg.caster_id)
        if ability is not None:
            sets_end = ability.sets_end_turn_flags(self.state, caster)
            sets_used = ability.sets_active_ability_used_flag(self.state, caster)
        else:
            sets_end = sets_end_turn_flags_for(int(msg.ability_type), self.state, caster)
            sets_used = sets_active_ability_used_flag_for(int(msg.ability_type), self.state, caster)
        return add_flags_after_ability_execution(
            self.state, caster, skip_ability_used=not sets_used, skip_end_turn=not sets_end)
