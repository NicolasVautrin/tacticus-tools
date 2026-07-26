# Couverture moteur par KIT (unites lineup)

> Genere par `scripts/python/audit_kit_coverage.py` (kit gameconfig x registres moteur
> des deux faces). Vue KIT-centrique complementaire de `combat-ability-coverage.md`
> (par-ability). Faces : `[CD]` = combat/decision portees, `[--]` = aucune ; `D` couvre
> les DEUX registres de scoring (non-comparables + overrides custom des comparables).
> A regenerer
> apres tout port. Les MISSING passifs/traits sont des CANDIDATS (approximation
> registres, cf. docstring du script) : trancher au recon du kit.

## Bilan

- Unites lineup : **123** ; kits COMPLETS (aucun manque detecte) : **20** ; kits avec du travail : **103**
- Volume total : **156** items manquants (actives no-op + passifs/traits non registres)

## Par faction (kits avec du travail, tries par volume)

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

### EmperorsChildren — 5 kits, 9 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| emperExultant | 2 | EuphoricStrikes(1198) [--] NO-OP DAMAGE(Power) | RefusalToBeOutdone | - |
| emperFlawlessBlade | 2 | DaemonicPatrons(1203) [--] NO-OP EFFECT/BUFF | EcstaticSlaughter | - |
| emperKakophonist | 2 | DoomSiren(1199) [-D] NO-OP DAMAGE(DirectDamage) | ObsessiveAnnunciation | - |
| emperLucius | 2 | LashOfTorment(1196) [--] NO-OP DAMAGE(Eviscerate) | ArmourOfShriekingSouls | - |
| emperNoiseMarine | 1 | ExcruciatingFrequencies(1197) [--] NO-OP DAMAGE(Blast) | - | - |

### ThousandSons — 5 kits, 9 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| thousAhriman | 2 | Doombolt(1102) [--] NO-OP DAMAGE(Psychic) | PsychicStalk | - |
| thousDaemonPrince | 2 | AetherStride(1208) [--] NO-OP SUMMON<br>InfernalCannon(1209) [--] NO-OP DAMAGE(Flame) | - | - |
| thousTerminator | 2 | HellfyreMissileRack(1088) [--] NO-OP DAMAGE(HeavyRound) | TimeFlux | - |
| thousTzaangor | 2 | SorcerousFacade(1100) [-D] NO-OP DAMAGE(Psychic) | RealityUnbound | - |
| thousSorcerer | 1 | AttemptedPossession(1101) [--] NO-OP EFFECT/BUFF | - | - |

### BlackTemplars — 5 kits, 8 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| templAggressor | 2 | FragstormGrenadeLauncher(1048) [--] NO-OP DAMAGE(Blast) | Boltstorm | - |
| templChampion | 2 | HolyDuel(1050) [-D] NO-OP EFFECT/BUFF | MartialSuperiority | - |
| templHelbrecht | 2 | CrusadeOfWrath(1049) [--] NO-OP EFFECT/BUFF | DestroyTheWitch | - |
| templAncient | 1 | UnbreakableDuty(1061) [--] NO-OP EFFECT/BUFF | - | - |
| templSwordBrother | 1 | ThunderousAssault(1043) [C-] OK | ChampionOfTheFeast | - |

### BloodAngels — 6 kits, 8 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| bloodIntercessor | 2 | HammerOfWrath(1153) [-D] NO-OP DAMAGE(Power) | AggressiveOnslaught | - |
| bloodSanguinary | 2 | BloodChalice(1175) [--] NO-OP HEAL | SanguinaryPriest | - |
| bloodDante | 1 | LightOfSanguinius(1177) [-D] NO-OP DAMAGE(Melta) | - | - |
| bloodDeathCompany | 1 | BlackRage(1163) [CD] OK | VisionsOfHeresy | - |
| bloodMephiston | 1 | TheQuickening(1151) [CD] OK | FuryOfTheAncients | - |
| bloodTerminator | 1 | SavageEchoes(1230) [C-] OK | RedRampage | - |

### SpaceWolves — 5 kits, 8 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| spaceBlackmane | 2 | WarHowl(1106) [--] NO-OP EFFECT/BUFF | SagaOfTheWarriorBorn | - |
| spaceHound | 2 | GrapnelLauncher(1090) [-D] NO-OP DAMAGE(Physical) | HuntersBeyondDeath | - |
| spaceWolfPriest | 2 | RitesOfMorkai(1211) [--] NO-OP EFFECT/BUFF | HealingBalms | - |
| spaceRockfist | 1 | Foehammer(1097) [--] NO-OP DAMAGE(Power) | - | - |
| spaceWulfen | 1 | GreatFrostAxe(1089) [C-] OK | SavageKiller | - |

### AstraMilitarum — 5 kits, 7 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| astraDreir | 2 | LeadingTheCharge(1204) [--] NO-OP DAMAGE(Power) | ToughToKill | - |
| astraOrdnance | 2 | BasiliskBarrage(1026) [--] NO-OP DAMAGE(Blast) | - | IndirectFire(x9) |
| astraBullgryn | 1 | FragBomb(1017) [--] NO-OP DAMAGE(Blast) | - | - |
| astraPrimarisPsy | 1 | PsychicMaelstrom(1027) [--] NO-OP DAMAGE(Psychic) | - | - |
| astraYarrick | 1 | SendInTheNextWave(1016) [CD] OK | SummaryExecution | - |

### BlackLegion — 5 kits, 7 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| blackAbaddon | 2 | Drachnyen(1029) [-D] NO-OP DAMAGE(Piercing) | FirstAmongTraitors | - |
| blackHaarken | 2 | HeraldOfTheApocalypse(1020) [-D] NO-OP DAMAGE(Piercing) | HeadClaimer | - |
| blackObliterator | 1 | FrenziedFiring(1036) [--] NO-OP DAMAGE(HeavyRound) | - | - |
| blackPossession | 1 | Incursion(1021) [CD] OK | Possession | - |
| blackTerminator | 1 | BringerOfDespair(1022) [C-] OK | HatefulAssault | - |

### Custodes — 5 kits, 7 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| custoBladeChampion | 2 | MartialInspiration(1191) [--] NO-OP DAMAGE(Eviscerate) | LegacyOfCombat | - |
| custoTrajann | 2 | MomentShackle(1184) [--] NO-OP DAMAGE(Bolter) | LegendaryCommander | - |
| custoAtlacoya | 1 | TalonsOfTheEmperor(1195) [--] NO-OP DAMAGE(Power) | - | - |
| custoKyrus | 1 | VigilanceEternal(1202) [CD] OK | UnwaveringSentinel | - |
| custoVexilusPraetor | 1 | VexillaMagnifica(1183) [-D] NO-OP DAMAGE(Physical) | - | - |

### WorldEaters — 5 kits, 7 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| worldExecutions | 2 | MurderousSwing(1137) [--] NO-OP DAMAGE(Piercing) | TrophyTaker | - |
| worldTerminator | 2 | BloodyFury(1129) [-D] NO-OP DAMAGE(Chain) | WrathfulDevotion | - |
| worldEightbound | 1 | OverwhelmingWrath(1141) [--] NO-OP DAMAGE(Eviscerate) | - | - |
| worldJakhal | 1 | JakhalStimms(1131) [C-] OK | Skullsmasher | - |
| worldKharn | 1 | KillMaimBurn(1132) [--] NO-OP DAMAGE(Piercing) | - | - |

### AdeptusMechanicus — 4 kits, 6 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| admecDestroyer | 2 | SentinelDirectives(1139) [C-] OK | HeavyGravCannon | Vehicle(x8) |
| admecManipulus | 2 | DefendTheDivineWork(1117) [-D] NO-OP REPAIR | GalvanicField | - |
| admecDominus | 1 | RadBombardment(1116) [--] NO-OP DAMAGE(Toxic) | - | - |
| admecRuststalker | 1 | CordClaw(1122) [CD] OK | OptimizedGait | - |

### Aeldari — 4 kits, 6 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| eldarJainZar | 2 | SilentDeath(1068) [--] NO-OP DAMAGE(Piercing) | TerrorsLament | - |
| eldarRanger | 2 | FireAndReposition(1063) [--] NO-OP EFFECT/BUFF | WireweaveNet | - |
| eldarAutarch | 1 | Loki_SwoopingHawk(1064) [--] NO-OP DAMAGE(Piercing) | - | - |
| eldarMauganRa | 1 | HarvesterOfSouls(1067) [C-] OK | InescapableAccuracy | - |

### Sisterhood — 5 kits, 6 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| adeptHospitaller | 2 | RitesOfRestoration(1039) [-D] NO-OP HEAL | MedicusMinistorum | - |
| adeptCanoness | 1 | BrazierOfHolyFire(1041) [--] NO-OP DAMAGE(Flame) | - | - |
| adeptCelestine | 1 | SkyStrike(1025) [C-] OK | GeminaeSuperia | - |
| adeptMorvenn | 1 | SanctorumMissile(1062) [C-] OK | RighteousRepugnance | - |
| adeptRetributor | 1 | ArmoriumCherub(1014) [CD] OK | FireOfAbsolution | - |

### Tau — 5 kits, 6 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| tauFarsight | 2 | ExemplarOfTheMontka(1210) [--] NO-OP EFFECT/BUFF | WayOfTheShortBlade | - |
| tauAunShi | 1 | InspiredToGreatness(1082) [CD] OK | SereneUnifier | - |
| tauDarkstrider | 1 | FightingRetreat(1081) [CD] OK | StructuralAnalyser | - |
| tauMarksman | 1 | SeekerMissileFrequencyLock(1069) [--] NO-OP DAMAGE(HeavyRound) | - | - |
| tauShadowsun | 1 | ExemplarOfTheKauyon(1087) [--] NO-OP DAMAGE(Blast) | - | - |

### Ultramarines — 5 kits, 6 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| ultraTitus | 2 | TacticalPrecision(1154) [--] NO-OP DAMAGE(Bolter) | FuelledByFury | - |
| ultraDreadnought | 1 | DutyEternal(1158) [--] NO-OP SUMMON<br>MacroPlasmaIncinerator(1159) [C-] OK | - | - |
| ultraEliminatorSgt | 1 | MortisRound(1004) [C-] OK | CamoCloak | - |
| ultraInceptorSgt | 1 | DeathFromAbove(1003) [C-] OK | ShockAssault | - |
| ultraTigurius | 1 | StormOfWrath(1019) [--] NO-OP DAMAGE(Psychic) | - | - |

### Genestealers — 3 kits, 5 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| genesMagus | 2 | MindControl(1164) [--] NO-OP EFFECT/BUFF | SpiritualLeader | - |
| genesPatriarch | 2 | MightFromBelow(1165) [--] NO-OP DAMAGE(Psychic) | CosmicHorror | - |
| genesBiophagus | 1 | AberrantHypermorph(1166) [CD] OK | TwistedScience | - |

### Orks — 4 kits, 5 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| orksBigMek | 2 | GrotTank(1057) [--] NO-OP SUMMON | KustomForceFieldReworked | - |
| orksKillaKan | 1 | DakkaDakkaDakka(1171) [--] NO-OP DAMAGE(Projectile) | - | - |
| orksNob | 1 | UnstoppableMomentumReworked(1152) [--] NO-OP DAMAGE(DirectDamage) | - | - |
| orksWarboss | 1 | Waaagh(1058) [C-] OK | LightImUp | - |

### Tyranids — 4 kits, 5 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| tyranParasite | 2 | ItItches(1121) [-D] NO-OP SUMMON | BarbedOvipositor | - |
| tyranBiovore | 1 | BioMinefield(1144) [--] NO-OP SUMMON<br>SporeMineLauncher(1145) [C-] OK | - | - |
| tyranDeathleaper | 1 | FearOfTheUnseen(1115) [--] NO-OP DAMAGE(DirectDamage) | - | - |
| tyranWingedPrime | 1 | AlphaWarrior(1112) [C-] OK | SynapticLinchpin | - |

### DeathGuard — 4 kits, 4 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| deathBlightbringer | 1 | Poxwalkers(1040) [CD] OK | CursedPlagueBell | - |
| deathBlightlord | 1 | FlailSwing(1042) [C-] OK | HazeOfCorruption | - |
| deathPutrifier | 1 | FoulInfusion(1038) [-D] NO-OP DAMAGE(Toxic) | - | - |
| deathTyphus | 1 | PlagueWind(1035) [--] NO-OP DAMAGE(Psychic) | - | - |

### AdeptusAstartes — 1 kits, 2 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| astarCyrus | 2 | StrikeFromTheShadows(1225) [--] NO-OP DAMAGE(Bolter) | HaywireMine | - |

## Kits lineup COMPLETS (20)

adeptExorcist, admecMarshall, astraCreed, astraOrdnanceBattery, blackForgefiend, deathCrawler, deathRotbone, eldarFarseer, genesKelermorph, genesPrimus, orksRukkatrukk, orksRuntherd, spaceStormcaller, tauBroadside, tauCrisis, thousInfernalMaster, tyranNeurothrope, tyranTyrantGuard, ultraApothecary, ultraCalgar
