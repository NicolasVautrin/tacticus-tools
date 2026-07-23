# Couverture moteur par KIT (unites lineup)

> Genere par `scripts/python/audit_kit_coverage.py` (kit gameconfig x registres moteur
> des deux faces). Vue KIT-centrique complementaire de `combat-ability-coverage.md`
> (par-ability). Faces : `[CD]` = combat/decision portees, `[--]` = aucune. A regenerer
> apres tout port. Les MISSING passifs/traits sont des CANDIDATS (approximation
> registres, cf. docstring du script) : trancher au recon du kit.

## Bilan

- Unites lineup : **123** ; kits COMPLETS (aucun manque detecte) : **5** ; kits avec du travail : **118**
- Volume total : **246** items manquants (actives no-op + passifs/traits non registres)

## Par faction (kits avec du travail, tries par volume)

### AstraMilitarum — 7 kits, 15 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| astraOrdnance | 3 | BasiliskBarrage(1026) [--] NO-OP DAMAGE(Blast) | SpotterReworked | IndirectFire(x9) |
| astraBullgryn | 2 | FragBomb(1017) [--] NO-OP DAMAGE(Blast) | AvalancheOfMuscle | - |
| astraCreed | 2 | SupremeCommander(1028) [--] NO-OP SUMMON | SwornProtector | - |
| astraDreir | 2 | LeadingTheCharge(1204) [--] NO-OP DAMAGE(Power) | ToughToKill | - |
| astraOrdnanceBattery | 2 | MalleusRocketLauncher(1142) [--] NO-OP DAMAGE(Blast)<br>ForwardSpotter(1143) [--] NO-OP SUMMON | - | - |
| astraPrimarisPsy | 2 | PsychicMaelstrom(1027) [--] NO-OP DAMAGE(Psychic) | Nightshroud | - |
| astraYarrick | 2 | SendInTheNextWave(1016) [-D] NO-OP SUMMON | SummaryExecution | - |

### EmperorsChildren — 5 kits, 15 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| emperExultant | 3 | EuphoricStrikes(1198) [--] NO-OP DAMAGE(Power) | RefusalToBeOutdone | ThrillSeekers(x5) |
| emperFlawlessBlade | 3 | DaemonicPatrons(1203) [--] NO-OP EFFECT/BUFF | EcstaticSlaughter | ThrillSeekers(x5) |
| emperKakophonist | 3 | DoomSiren(1199) [--] NO-OP DAMAGE(DirectDamage) | ObsessiveAnnunciation | ThrillSeekers(x5) |
| emperLucius | 3 | LashOfTorment(1196) [--] NO-OP DAMAGE(Eviscerate) | ArmourOfShriekingSouls | ThrillSeekers(x5) |
| emperNoiseMarine | 3 | ExcruciatingFrequencies(1197) [--] NO-OP DAMAGE(Blast) | TerrifyingCrescendo | ThrillSeekers(x5) |

### Custodes — 5 kits, 14 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| custoBladeChampion | 3 | MartialInspiration(1191) [--] NO-OP DAMAGE(Eviscerate) | LegacyOfCombat | MartialKatah(x4) |
| custoKyrus | 3 | VigilanceEternal(1202) [-D] NO-OP DAMAGE(Power) | UnwaveringSentinel | MartialKatah(x4) |
| custoTrajann | 3 | MomentShackle(1184) [--] NO-OP DAMAGE(Bolter) | LegendaryCommander | MartialKatah(x4) |
| custoVexilusPraetor | 3 | VexillaMagnifica(1183) [-D] NO-OP DAMAGE(Physical) | StandVigil | MartialKatah(x4) |
| custoAtlacoya | 2 | TalonsOfTheEmperor(1195) [--] NO-OP DAMAGE(Power) | DaughterOfTheAbyss | - |

### WorldEaters — 5 kits, 14 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| worldEightbound | 3 | OverwhelmingWrath(1141) [--] NO-OP DAMAGE(Eviscerate) | BeaconOfRage | BlessingsOfKhorne(x11) |
| worldExecutions | 3 | MurderousSwing(1137) [--] NO-OP DAMAGE(Piercing) | TrophyTaker | BlessingsOfKhorne(x11) |
| worldJakhal | 3 | JakhalStimms(1131) [--] NO-OP DAMAGE(Physical) | Skullsmasher | BlessingsOfKhorne(x11) |
| worldTerminator | 3 | BloodyFury(1129) [-D] NO-OP DAMAGE(Chain) | WrathfulDevotion | BlessingsOfKhorne(x11) |
| worldKharn | 2 | KillMaimBurn(1132) [--] NO-OP DAMAGE(Piercing) | - | BlessingsOfKhorne(x11) |

### DarkAngels — 7 kits, 14 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| darkaAsmodai | 2 | ExemplarOfHate(1140) [--] NO-OP EFFECT/BUFF | FearedInterrogator | - |
| darkaAzrael | 2 | DarkTalonStrike(1092) [-D] NO-OP DAMAGE(DirectDamage) | LionHelm | - |
| darkaCompanion | 2 | CalibaniteGreatsword(1189) [--] NO-OP DAMAGE(Power) | EnmityForTheUnworthy | - |
| darkaHellblaster | 2 | Supercharge(1103) [--] NO-OP DAMAGE(Plasma) | GrimRetribution | - |
| darkaSternguard | 2 | SternguardFocus(?) [--] NO-OP EFFECT/BUFF | SpecialIssueCombiMelta | - |
| darkaStormSpeeder | 2 | DeathOnTheWind(1213) [--] NO-OP DAMAGE(HeavyRound)<br>Hailstrike(1214) [--] NO-OP DAMAGE(Projectile) | - | - |
| darkaTerminator | 2 | PlasmaCannon(1150) [--] NO-OP DAMAGE(Plasma) | Deathwing | - |

### Tau — 7 kits, 14 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| tauAunShi | 2 | InspiredToGreatness(1082) [-D] NO-OP HEAL | SereneUnifier | - |
| tauBroadside | 2 | HeavyRailRifle(1160) [--] NO-OP DAMAGE(Piercing)<br>TwinSmartMissileSystem(1161) [--] NO-OP DAMAGE(Blast) | - | - |
| tauCrisis | 2 | EarlyWarningOverride(1077) [-D] NO-OP SUMMON | CyclicIonBlaster | - |
| tauDarkstrider | 2 | FightingRetreat(1081) [-D] NO-OP EFFECT/BUFF | StructuralAnalyser | - |
| tauFarsight | 2 | ExemplarOfTheMontka(1210) [--] NO-OP EFFECT/BUFF | WayOfTheShortBlade | - |
| tauMarksman | 2 | SeekerMissileFrequencyLock(1069) [--] NO-OP DAMAGE(HeavyRound) | MV71SniperDroneSquad | - |
| tauShadowsun | 2 | ExemplarOfTheKauyon(1087) [--] NO-OP DAMAGE(Blast) | DefenderOfTheGreaterGood | - |

### Ultramarines — 7 kits, 14 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| ultraApothecary | 2 | CombatRestoratives(1002) [-D] NO-OP HEAL | Narthecium | - |
| ultraCalgar | 2 | GauntletsOfUltramar(1000) [-D] NO-OP DAMAGE(Bolter) | RitesOfBattle | - |
| ultraDreadnought | 2 | DutyEternal(1158) [--] NO-OP SUMMON<br>MacroPlasmaIncinerator(1159) [--] NO-OP DAMAGE(Plasma) | - | - |
| ultraEliminatorSgt | 2 | MortisRound(1004) [--] NO-OP DAMAGE(HeavyRound) | CamoCloak | - |
| ultraInceptorSgt | 2 | DeathFromAbove(1003) [--] NO-OP EFFECT/BUFF | ShockAssault | - |
| ultraTigurius | 2 | StormOfWrath(1019) [--] NO-OP DAMAGE(Psychic) | PsychicFortress | - |
| ultraTitus | 2 | TacticalPrecision(1154) [--] NO-OP DAMAGE(Bolter) | FuelledByFury | - |

### DeathGuard — 6 kits, 13 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| deathPutrifier | 3 | FoulInfusion(1038) [-D] NO-OP DAMAGE(Toxic) | ExplosiveMaladies | PutridExplosion(x6) |
| deathBlightbringer | 2 | Poxwalkers(1040) [-D] NO-OP SUMMON | CursedPlagueBell | - |
| deathBlightlord | 2 | FlailSwing(1042) [--] NO-OP DAMAGE(Power) | HazeOfCorruption | - |
| deathCrawler | 2 | EntropyCannons(1168) [--] NO-OP DAMAGE(Energy)<br>PlagueburstMortar(1169) [--] NO-OP DAMAGE(Toxic) | - | - |
| deathRotbone | 2 | RevitalizingMalignancy(1037) [-D] NO-OP HEAL | TaintedNarthecium | - |
| deathTyphus | 2 | PlagueWind(1035) [--] NO-OP DAMAGE(Psychic) | DestroyerHive | - |

### Necrons — 7 kits, 13 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| necroChronomancer | 2 | Chronometron(1226) [--] NO-OP EFFECT/BUFF | TimesplinterMantle | - |
| necroDestroyer | 2 | MultiThreatEliminator(1006) [--] NO-OP DAMAGE(Gauss) | InescapableDeath | - |
| necroOverlord | 2 | ResurrectionOrb(1009) [--] NO-OP SUMMON | MartialApotheosis | - |
| necroPlasmancer | 2 | HarbingerOfDestruction(1008) [--] NO-OP DAMAGE(DirectDamage) | LivingLightning | - |
| necroReanimator | 2 | ReanimationBeam(1223) [--] NO-OP REPAIR<br>NanoscarabRepairProtocols(1224) [--] NO-OP REPAIR | - | - |
| necroWarden | 2 | AdaptiveStrategy(1005) [--] NO-OP EFFECT/BUFF | RelentlessMarch | - |
| necroSpyder | 1 | ScarabHive(1007) [CD] OK | FabricatorClawArray | - |

### LeaguesOfVotann — 4 kits, 12 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| votanBeserk | 3 | AugmentedAssault(1221) [--] NO-OP DAMAGE(Eviscerate) | FuryFromTheDelve | PrioritisedEfficiency(x7) |
| votanIronmaster | 3 | GravitonRifle(1206) [--] NO-OP DAMAGE(Physical) | EcogSupport | PrioritisedEfficiency(x7) |
| votanMemnyr | 3 | IronkinSteeljack(1219) [--] NO-OP SUMMON | PredictiveGuidance | PrioritisedEfficiency(x7) |
| votanUthar | 3 | AncestralFortune(1207) [--] NO-OP DAMAGE(Plasma) | GrimEfficiency | PrioritisedEfficiency(x7) |

### BlackLegion — 6 kits, 12 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| blackAbaddon | 2 | Drachnyen(1029) [--] NO-OP DAMAGE(Piercing) | FirstAmongTraitors | - |
| blackForgefiend | 2 | HadesAutocannons(1147) [--] NO-OP DAMAGE(Flame)<br>DaemonicOrdnance(1148) [--] NO-OP DAMAGE(Plasma) | - | - |
| blackHaarken | 2 | HeraldOfTheApocalypse(1020) [--] NO-OP DAMAGE(Piercing) | HeadClaimer | - |
| blackObliterator | 2 | FrenziedFiring(1036) [--] NO-OP DAMAGE(HeavyRound) | FleshmetalGuns | - |
| blackPossession | 2 | Incursion(1021) [-D] NO-OP SUMMON | Possession | - |
| blackTerminator | 2 | BringerOfDespair(1022) [--] NO-OP DAMAGE(Power) | HatefulAssault | - |

### Orks — 6 kits, 11 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| orksBigMek | 2 | GrotTank(1057) [--] NO-OP SUMMON | KustomForceFieldReworked | - |
| orksKillaKan | 2 | DakkaDakkaDakka(1171) [--] NO-OP DAMAGE(Projectile) | PowerTrip | - |
| orksNob | 2 | UnstoppableMomentumReworked(1152) [--] NO-OP DAMAGE(DirectDamage) | SmashaEad | - |
| orksRukkatrukk | 2 | SquigLaunchas(1200) [--] NO-OP DAMAGE(Physical)<br>SquigMine(1201) [--] NO-OP DAMAGE(Blast) | - | - |
| orksWarboss | 2 | Waaagh(1058) [--] NO-OP SUMMON | LightImUp | - |
| orksRuntherd | 1 | GetEmRuntz(1045) [CD] OK | SquigHound | - |

### Sisterhood — 6 kits, 11 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| adeptCanoness | 2 | BrazierOfHolyFire(1041) [--] NO-OP DAMAGE(Flame) | CondemnorStake | - |
| adeptCelestine | 2 | SkyStrike(1025) [--] NO-OP EFFECT/BUFF | GeminaeSuperia | - |
| adeptExorcist | 2 | ThriceBlessedConflagration(1187) [--] NO-OP DAMAGE(Flame)<br>DevastatingRefrain(1188) [--] NO-OP DAMAGE(Blast) | - | - |
| adeptHospitaller | 2 | RitesOfRestoration(1039) [-D] NO-OP HEAL | MedicusMinistorum | - |
| adeptMorvenn | 2 | SanctorumMissile(1062) [--] NO-OP DAMAGE(Blast) | RighteousRepugnance | - |
| adeptRetributor | 1 | ArmoriumCherub(1014) [C-] OK | FireOfAbsolution | - |

### BloodAngels — 6 kits, 10 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| bloodDante | 2 | LightOfSanguinius(1177) [--] NO-OP DAMAGE(Melta) | LordOfTheHost | - |
| bloodIntercessor | 2 | HammerOfWrath(1153) [-D] NO-OP DAMAGE(Power) | AggressiveOnslaught | - |
| bloodSanguinary | 2 | BloodChalice(1175) [--] NO-OP HEAL | SanguinaryPriest | - |
| bloodTerminator | 2 | SavageEchoes(?) [--] NO-OP DAMAGE(Eviscerate) | RedRampage | - |
| bloodDeathCompany | 1 | BlackRage(1163) [CD] OK | VisionsOfHeresy | - |
| bloodMephiston | 1 | TheQuickening(1151) [CD] OK | FuryOfTheAncients | - |

### SpaceWolves — 5 kits, 10 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| spaceBlackmane | 2 | WarHowl(1106) [--] NO-OP EFFECT/BUFF | SagaOfTheWarriorBorn | - |
| spaceHound | 2 | GrapnelLauncher(1090) [-D] NO-OP DAMAGE(Physical) | HuntersBeyondDeath | - |
| spaceRockfist | 2 | Foehammer(1097) [--] NO-OP DAMAGE(Power) | AnvilShield | - |
| spaceWolfPriest | 2 | RitesOfMorkai(1211) [--] NO-OP EFFECT/BUFF | HealingBalms | - |
| spaceWulfen | 2 | GreatFrostAxe(1089) [--] NO-OP DAMAGE(Piercing) | SavageKiller | - |

### Tyranids — 6 kits, 10 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| tyranBiovore | 2 | BioMinefield(1144) [--] NO-OP SUMMON<br>SporeMineLauncher(1145) [--] NO-OP SUMMON | - | - |
| tyranDeathleaper | 2 | FearOfTheUnseen(1115) [--] NO-OP DAMAGE(DirectDamage) | FeederTendrils | - |
| tyranParasite | 2 | ItItches(1121) [-D] NO-OP SUMMON | BarbedOvipositor | - |
| tyranWingedPrime | 2 | AlphaWarrior(1112) [--] NO-OP SUMMON | SynapticLinchpin | - |
| tyranNeurothrope | 1 | SpiritLeech(1104) [C-] OK | Neuroparasite | - |
| tyranTyrantGuard | 1 | CrushingClaws(1105) [C-] OK | GuardianOrganism | - |

### AdeptusMechanicus — 4 kits, 9 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| admecDestroyer | 3 | SentinelDirectives(1139) [--] NO-OP DAMAGE(Physical) | HeavyGravCannon | Vehicle(x8) |
| admecDominus | 2 | RadBombardment(1116) [--] NO-OP DAMAGE(Toxic) | MasterAnnihilator | - |
| admecManipulus | 2 | DefendTheDivineWork(1117) [-D] NO-OP REPAIR | GalvanicField | - |
| admecRuststalker | 2 | CordClaw(1122) [-D] NO-OP DAMAGE(DirectDamage) | OptimizedGait | - |

### Aeldari — 5 kits, 9 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| eldarFarseer | 2 | Executioner(1066) [--] NO-OP EFFECT/BUFF | Doom | - |
| eldarJainZar | 2 | SilentDeath(1068) [--] NO-OP DAMAGE(Piercing) | TerrorsLament | - |
| eldarMauganRa | 2 | HarvesterOfSouls(1067) [--] NO-OP EFFECT/BUFF | InescapableAccuracy | - |
| eldarRanger | 2 | FireAndReposition(1063) [--] NO-OP EFFECT/BUFF | WireweaveNet | - |
| eldarAutarch | 1 | Loki_SwoopingHawk(1064) [--] NO-OP DAMAGE(Piercing) | - | - |

### BlackTemplars — 5 kits, 9 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| templAggressor | 2 | FragstormGrenadeLauncher(1048) [--] NO-OP DAMAGE(Blast) | Boltstorm | - |
| templAncient | 2 | UnbreakableDuty(1061) [--] NO-OP EFFECT/BUFF | AstartesBanner | - |
| templChampion | 2 | HolyDuel(1050) [-D] NO-OP EFFECT/BUFF | MartialSuperiority | - |
| templHelbrecht | 2 | CrusadeOfWrath(1049) [--] NO-OP EFFECT/BUFF | DestroyTheWitch | - |
| templSwordBrother | 1 | ThunderousAssault(1043) [C-] OK | ChampionOfTheFeast | - |

### ThousandSons — 5 kits, 9 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| thousAhriman | 2 | Doombolt(1102) [--] NO-OP DAMAGE(Psychic) | PsychicStalk | - |
| thousDaemonPrince | 2 | AetherStride(1208) [--] NO-OP SUMMON<br>InfernalCannon(1209) [--] NO-OP DAMAGE(Flame) | - | - |
| thousTerminator | 2 | HellfyreMissileRack(1088) [--] NO-OP DAMAGE(HeavyRound) | TimeFlux | - |
| thousTzaangor | 2 | SorcerousFacade(1100) [--] NO-OP DAMAGE(Psychic) | RealityUnbound | - |
| thousSorcerer | 1 | AttemptedPossession(1101) [--] NO-OP EFFECT/BUFF | - | - |

### Genestealers — 3 kits, 6 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| genesBiophagus | 2 | AberrantHypermorph(1166) [-D] NO-OP SUMMON | TwistedScience | - |
| genesMagus | 2 | MindControl(1164) [--] NO-OP EFFECT/BUFF | SpiritualLeader | - |
| genesPatriarch | 2 | MightFromBelow(1165) [--] NO-OP DAMAGE(Psychic) | CosmicHorror | - |

### AdeptusAstartes — 1 kits, 2 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| astarCyrus | 2 | StrikeFromTheShadows(1225) [--] NO-OP DAMAGE(Bolter) | HaywireMine | - |

## Kits lineup COMPLETS (5)

admecMarshall, genesKelermorph, genesPrimus, spaceStormcaller, thousInfernalMaster
