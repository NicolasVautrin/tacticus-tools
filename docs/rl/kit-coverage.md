# Couverture moteur par KIT (unites lineup)

> Genere par `scripts/python/audit_kit_coverage.py` (kit gameconfig x registres moteur
> des deux faces). Vue KIT-centrique complementaire de `combat-ability-coverage.md`
> (par-ability). Faces : `[CD]` = combat/decision portees, `[--]` = aucune. A regenerer
> apres tout port. Les MISSING passifs/traits sont des CANDIDATS (approximation
> registres, cf. docstring du script) : trancher au recon du kit.

## Bilan

- Unites lineup : **123** ; kits COMPLETS (aucun manque detecte) : **6** ; kits avec du travail : **117**
- Volume total : **220** items manquants (actives no-op + passifs/traits non registres)

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

### Custodes — 5 kits, 13 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| custoBladeChampion | 3 | MartialInspiration(1191) [--] NO-OP DAMAGE(Eviscerate) | LegacyOfCombat | MartialKatah(x4) |
| custoTrajann | 3 | MomentShackle(1184) [--] NO-OP DAMAGE(Bolter) | LegendaryCommander | MartialKatah(x4) |
| custoVexilusPraetor | 3 | VexillaMagnifica(1183) [-D] NO-OP DAMAGE(Physical) | StandVigil | MartialKatah(x4) |
| custoAtlacoya | 2 | TalonsOfTheEmperor(1195) [--] NO-OP DAMAGE(Power) | DaughterOfTheAbyss | - |
| custoKyrus | 2 | VigilanceEternal(1202) [CD] OK | UnwaveringSentinel | MartialKatah(x4) |

### WorldEaters — 5 kits, 13 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| worldEightbound | 3 | OverwhelmingWrath(1141) [--] NO-OP DAMAGE(Eviscerate) | BeaconOfRage | BlessingsOfKhorne(x11) |
| worldExecutions | 3 | MurderousSwing(1137) [--] NO-OP DAMAGE(Piercing) | TrophyTaker | BlessingsOfKhorne(x11) |
| worldTerminator | 3 | BloodyFury(1129) [-D] NO-OP DAMAGE(Chain) | WrathfulDevotion | BlessingsOfKhorne(x11) |
| worldJakhal | 2 | JakhalStimms(1131) [C-] OK | Skullsmasher | BlessingsOfKhorne(x11) |
| worldKharn | 2 | KillMaimBurn(1132) [--] NO-OP DAMAGE(Piercing) | - | BlessingsOfKhorne(x11) |

### DarkAngels — 7 kits, 13 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| darkaAsmodai | 2 | ExemplarOfHate(1140) [--] NO-OP EFFECT/BUFF | FearedInterrogator | - |
| darkaAzrael | 2 | DarkTalonStrike(1092) [-D] NO-OP DAMAGE(DirectDamage) | LionHelm | - |
| darkaCompanion | 2 | CalibaniteGreatsword(1189) [--] NO-OP DAMAGE(Power) | EnmityForTheUnworthy | - |
| darkaHellblaster | 2 | Supercharge(1103) [--] NO-OP DAMAGE(Plasma) | GrimRetribution | - |
| darkaSternguard | 2 | SternguardFocus(1228) [--] NO-OP EFFECT/BUFF | SpecialIssueCombiMelta | - |
| darkaStormSpeeder | 2 | DeathOnTheWind(1213) [--] NO-OP DAMAGE(HeavyRound)<br>Hailstrike(1214) [--] NO-OP DAMAGE(Projectile) | - | - |
| darkaTerminator | 1 | PlasmaCannon(1150) [C-] OK | Deathwing | - |

### LeaguesOfVotann — 4 kits, 11 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| votanBeserk | 3 | AugmentedAssault(1221) [--] NO-OP DAMAGE(Eviscerate) | FuryFromTheDelve | PrioritisedEfficiency(x7) |
| votanIronmaster | 3 | GravitonRifle(1206) [--] NO-OP DAMAGE(Physical) | EcogSupport | PrioritisedEfficiency(x7) |
| votanUthar | 3 | AncestralFortune(1207) [--] NO-OP DAMAGE(Plasma) | GrimEfficiency | PrioritisedEfficiency(x7) |
| votanMemnyr | 2 | IronkinSteeljack(1219) [C-] OK | PredictiveGuidance | PrioritisedEfficiency(x7) |

### BlackLegion — 6 kits, 11 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| blackAbaddon | 2 | Drachnyen(1029) [--] NO-OP DAMAGE(Piercing) | FirstAmongTraitors | - |
| blackForgefiend | 2 | HadesAutocannons(1147) [--] NO-OP DAMAGE(Flame)<br>DaemonicOrdnance(1148) [--] NO-OP DAMAGE(Plasma) | - | - |
| blackHaarken | 2 | HeraldOfTheApocalypse(1020) [--] NO-OP DAMAGE(Piercing) | HeadClaimer | - |
| blackObliterator | 2 | FrenziedFiring(1036) [--] NO-OP DAMAGE(HeavyRound) | FleshmetalGuns | - |
| blackPossession | 2 | Incursion(1021) [-D] NO-OP SUMMON | Possession | - |
| blackTerminator | 1 | BringerOfDespair(1022) [C-] OK | HatefulAssault | - |

### Necrons — 7 kits, 11 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| necroChronomancer | 2 | Chronometron(1226) [--] NO-OP EFFECT/BUFF | TimesplinterMantle | - |
| necroDestroyer | 2 | MultiThreatEliminator(1006) [--] NO-OP DAMAGE(Gauss) | InescapableDeath | - |
| necroReanimator | 2 | ReanimationBeam(1223) [--] NO-OP REPAIR<br>NanoscarabRepairProtocols(1224) [--] NO-OP REPAIR | - | - |
| necroWarden | 2 | AdaptiveStrategy(1005) [--] NO-OP EFFECT/BUFF | RelentlessMarch | - |
| necroOverlord | 1 | ResurrectionOrb(1009) [--] NO-OP SUMMON | - | - |
| necroPlasmancer | 1 | HarbingerOfDestruction(1008) [C-] OK | LivingLightning | - |
| necroSpyder | 1 | ScarabHive(1007) [CD] OK | FabricatorClawArray | - |

### Orks — 6 kits, 11 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| orksBigMek | 2 | GrotTank(1057) [--] NO-OP SUMMON | KustomForceFieldReworked | - |
| orksKillaKan | 2 | DakkaDakkaDakka(1171) [--] NO-OP DAMAGE(Projectile) | PowerTrip | - |
| orksNob | 2 | UnstoppableMomentumReworked(1152) [--] NO-OP DAMAGE(DirectDamage) | SmashaEad | - |
| orksRukkatrukk | 2 | SquigLaunchas(1200) [--] NO-OP DAMAGE(Physical)<br>SquigMine(1201) [--] NO-OP DAMAGE(Blast) | - | - |
| orksWarboss | 2 | Waaagh(1058) [--] NO-OP SUMMON | LightImUp | - |
| orksRuntherd | 1 | GetEmRuntz(1045) [CD] OK | SquigHound | - |

### Ultramarines — 7 kits, 10 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| ultraDreadnought | 2 | DutyEternal(1158) [--] NO-OP SUMMON<br>MacroPlasmaIncinerator(1159) [--] NO-OP DAMAGE(Plasma) | - | - |
| ultraTigurius | 2 | StormOfWrath(1019) [--] NO-OP DAMAGE(Psychic) | PsychicFortress | - |
| ultraTitus | 2 | TacticalPrecision(1154) [--] NO-OP DAMAGE(Bolter) | FuelledByFury | - |
| ultraApothecary | 1 | CombatRestoratives(1002) [CD] OK | Narthecium | - |
| ultraCalgar | 1 | GauntletsOfUltramar(1000) [CD] OK | RitesOfBattle | - |
| ultraEliminatorSgt | 1 | MortisRound(1004) [C-] OK | CamoCloak | - |
| ultraInceptorSgt | 1 | DeathFromAbove(1003) [C-] OK | ShockAssault | - |

### DeathGuard — 5 kits, 9 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| deathPutrifier | 3 | FoulInfusion(1038) [-D] NO-OP DAMAGE(Toxic) | ExplosiveMaladies | PutridExplosion(x6) |
| deathBlightbringer | 2 | Poxwalkers(1040) [-D] NO-OP SUMMON | CursedPlagueBell | - |
| deathCrawler | 2 | EntropyCannons(1168) [--] NO-OP DAMAGE(Energy)<br>PlagueburstMortar(1169) [--] NO-OP DAMAGE(Toxic) | - | - |
| deathBlightlord | 1 | FlailSwing(1042) [C-] OK | HazeOfCorruption | - |
| deathTyphus | 1 | PlagueWind(1035) [--] NO-OP DAMAGE(Psychic) | - | - |

### BlackTemplars — 5 kits, 9 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| templAggressor | 2 | FragstormGrenadeLauncher(1048) [--] NO-OP DAMAGE(Blast) | Boltstorm | - |
| templAncient | 2 | UnbreakableDuty(1061) [--] NO-OP EFFECT/BUFF | AstartesBanner | - |
| templChampion | 2 | HolyDuel(1050) [-D] NO-OP EFFECT/BUFF | MartialSuperiority | - |
| templHelbrecht | 2 | CrusadeOfWrath(1049) [--] NO-OP EFFECT/BUFF | DestroyTheWitch | - |
| templSwordBrother | 1 | ThunderousAssault(1043) [C-] OK | ChampionOfTheFeast | - |

### BloodAngels — 6 kits, 9 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| bloodDante | 2 | LightOfSanguinius(1177) [--] NO-OP DAMAGE(Melta) | LordOfTheHost | - |
| bloodIntercessor | 2 | HammerOfWrath(1153) [-D] NO-OP DAMAGE(Power) | AggressiveOnslaught | - |
| bloodSanguinary | 2 | BloodChalice(1175) [--] NO-OP HEAL | SanguinaryPriest | - |
| bloodDeathCompany | 1 | BlackRage(1163) [CD] OK | VisionsOfHeresy | - |
| bloodMephiston | 1 | TheQuickening(1151) [CD] OK | FuryOfTheAncients | - |
| bloodTerminator | 1 | SavageEchoes(1230) [C-] OK | RedRampage | - |

### Sisterhood — 6 kits, 9 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| adeptCanoness | 2 | BrazierOfHolyFire(1041) [--] NO-OP DAMAGE(Flame) | CondemnorStake | - |
| adeptExorcist | 2 | ThriceBlessedConflagration(1187) [--] NO-OP DAMAGE(Flame)<br>DevastatingRefrain(1188) [--] NO-OP DAMAGE(Blast) | - | - |
| adeptHospitaller | 2 | RitesOfRestoration(1039) [-D] NO-OP HEAL | MedicusMinistorum | - |
| adeptCelestine | 1 | SkyStrike(1025) [C-] OK | GeminaeSuperia | - |
| adeptMorvenn | 1 | SanctorumMissile(1062) [C-] OK | RighteousRepugnance | - |
| adeptRetributor | 1 | ArmoriumCherub(1014) [C-] OK | FireOfAbsolution | - |

### SpaceWolves — 5 kits, 9 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| spaceBlackmane | 2 | WarHowl(1106) [--] NO-OP EFFECT/BUFF | SagaOfTheWarriorBorn | - |
| spaceHound | 2 | GrapnelLauncher(1090) [-D] NO-OP DAMAGE(Physical) | HuntersBeyondDeath | - |
| spaceRockfist | 2 | Foehammer(1097) [--] NO-OP DAMAGE(Power) | AnvilShield | - |
| spaceWolfPriest | 2 | RitesOfMorkai(1211) [--] NO-OP EFFECT/BUFF | HealingBalms | - |
| spaceWulfen | 1 | GreatFrostAxe(1089) [C-] OK | SavageKiller | - |

### ThousandSons — 5 kits, 9 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| thousAhriman | 2 | Doombolt(1102) [--] NO-OP DAMAGE(Psychic) | PsychicStalk | - |
| thousDaemonPrince | 2 | AetherStride(1208) [--] NO-OP SUMMON<br>InfernalCannon(1209) [--] NO-OP DAMAGE(Flame) | - | - |
| thousTerminator | 2 | HellfyreMissileRack(1088) [--] NO-OP DAMAGE(HeavyRound) | TimeFlux | - |
| thousTzaangor | 2 | SorcerousFacade(1100) [--] NO-OP DAMAGE(Psychic) | RealityUnbound | - |
| thousSorcerer | 1 | AttemptedPossession(1101) [--] NO-OP EFFECT/BUFF | - | - |

### Tyranids — 6 kits, 8 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| tyranDeathleaper | 2 | FearOfTheUnseen(1115) [--] NO-OP DAMAGE(DirectDamage) | FeederTendrils | - |
| tyranParasite | 2 | ItItches(1121) [-D] NO-OP SUMMON | BarbedOvipositor | - |
| tyranBiovore | 1 | BioMinefield(1144) [--] NO-OP SUMMON<br>SporeMineLauncher(1145) [C-] OK | - | - |
| tyranNeurothrope | 1 | SpiritLeech(1104) [C-] OK | Neuroparasite | - |
| tyranTyrantGuard | 1 | CrushingClaws(1105) [C-] OK | GuardianOrganism | - |
| tyranWingedPrime | 1 | AlphaWarrior(1112) [C-] OK | SynapticLinchpin | - |

### AdeptusMechanicus — 4 kits, 7 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| admecDestroyer | 2 | SentinelDirectives(1139) [C-] OK | HeavyGravCannon | Vehicle(x8) |
| admecDominus | 2 | RadBombardment(1116) [--] NO-OP DAMAGE(Toxic) | MasterAnnihilator | - |
| admecManipulus | 2 | DefendTheDivineWork(1117) [-D] NO-OP REPAIR | GalvanicField | - |
| admecRuststalker | 1 | CordClaw(1122) [CD] OK | OptimizedGait | - |

### Aeldari — 5 kits, 7 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| eldarJainZar | 2 | SilentDeath(1068) [--] NO-OP DAMAGE(Piercing) | TerrorsLament | - |
| eldarRanger | 2 | FireAndReposition(1063) [--] NO-OP EFFECT/BUFF | WireweaveNet | - |
| eldarAutarch | 1 | Loki_SwoopingHawk(1064) [--] NO-OP DAMAGE(Piercing) | - | - |
| eldarFarseer | 1 | Executioner(1066) [C-] OK | Doom | - |
| eldarMauganRa | 1 | HarvesterOfSouls(1067) [C-] OK | InescapableAccuracy | - |

### Genestealers — 3 kits, 5 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| genesMagus | 2 | MindControl(1164) [--] NO-OP EFFECT/BUFF | SpiritualLeader | - |
| genesPatriarch | 2 | MightFromBelow(1165) [--] NO-OP DAMAGE(Psychic) | CosmicHorror | - |
| genesBiophagus | 1 | AberrantHypermorph(1166) [CD] OK | TwistedScience | - |

### AdeptusAstartes — 1 kits, 2 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| astarCyrus | 2 | StrikeFromTheShadows(1225) [--] NO-OP DAMAGE(Bolter) | HaywireMine | - |

## Kits lineup COMPLETS (6)

admecMarshall, deathRotbone, genesKelermorph, genesPrimus, spaceStormcaller, thousInfernalMaster
