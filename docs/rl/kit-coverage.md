# Couverture moteur par KIT (unites lineup)

> Genere par `scripts/python/audit_kit_coverage.py` (kit gameconfig x registres moteur
> des deux faces). Vue KIT-centrique complementaire de `combat-ability-coverage.md`
> (par-ability). Faces : `[CD]` = combat/decision portees, `[--]` = aucune ; `D` couvre
> les TROIS registres de scoring (non-comparables + overrides custom des comparables
> + sous-classes `AActiveAbility` par ability). La mention « NC classee, utilite NC non
> portee » marque une ability reconnue NonComparable dont l'utilite reste a porter :
> c'est un travail restant, pas une face couverte.
> A regenerer
> apres tout port. Les MISSING passifs/traits sont des CANDIDATS (approximation
> registres, cf. docstring du script) : trancher au recon du kit.

## Bilan

- Unites lineup : **127** ; kits COMPLETS (aucun manque detecte) : **37** ; kits avec du travail : **90**
- Volume total : **115** items manquants (actives no-op + passifs/traits non registres)

## Par faction (kits avec du travail, tries par volume)

### Aeldari — 5 kits, 8 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| eldarJainZar | 2 | SilentDeath(1068) [--] NO-OP DAMAGE(Piercing) | TerrorsLament | - |
| eldarLhykhis | 2 | EmpyricAmbush(1232) [--] NO-OP DAMAGE(Eviscerate) | WhisperingWeb | - |
| eldarRanger | 2 | FireAndReposition(1063) [--] NO-OP EFFECT/BUFF | WireweaveNet | - |
| eldarAutarch | 1 | Loki_SwoopingHawk(1064) [--] NO-OP DAMAGE(Piercing) | - | - |
| eldarMauganRa | 1 | HarvesterOfSouls(1067) [CD] OK | InescapableAccuracy | - |

### EmperorsChildren — 5 kits, 8 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| emperExultant | 2 | EuphoricStrikes(1198) [--] NO-OP DAMAGE(Power) | RefusalToBeOutdone | - |
| emperFlawlessBlade | 2 | DaemonicPatrons(1203) [--] NO-OP EFFECT/BUFF | EcstaticSlaughter | - |
| emperLucius | 2 | LashOfTorment(1196) [--] NO-OP DAMAGE(Eviscerate) | ArmourOfShriekingSouls | - |
| emperKakophonist | 1 | DoomSiren(1199) [CD] OK | ObsessiveAnnunciation | - |
| emperNoiseMarine | 1 | ExcruciatingFrequencies(1197) [--] NO-OP DAMAGE(Blast) | - | - |

### Necrons — 6 kits, 8 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| necroReanimator | 2 | ReanimationBeam(1223) [--] NO-OP REPAIR<br>NanoscarabRepairProtocols(1224) [--] NO-OP REPAIR | - | - |
| necroWarden | 2 | AdaptiveStrategy(1005) [--] NO-OP EFFECT/BUFF | RelentlessMarch | - |
| necroChronomancer | 1 | Chronometron(1226) [CD] OK | TimesplinterMantle | - |
| necroDestroyer | 1 | MultiThreatEliminator(1006) [CD] OK | InescapableDeath | - |
| necroOverlord | 1 | ResurrectionOrb(1009) [CD] OK | MyWillBeDoneOverlord | - |
| necroPlasmancer | 1 | HarbingerOfDestruction(1008) [C-] OK | LivingLightning | - |

### BloodAngels — 6 kits, 7 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| bloodSanguinary | 2 | BloodChalice(1175) [--] NO-OP HEAL | SanguinaryPriest | - |
| bloodDante | 1 | LightOfSanguinius(1177) [-D] NO-OP DAMAGE(Melta) | - | - |
| bloodDeathCompany | 1 | BlackRage(1163) [CD] OK | VisionsOfHeresy | - |
| bloodIntercessor | 1 | HammerOfWrath(1153) [CD] OK | AggressiveOnslaught | - |
| bloodMephiston | 1 | TheQuickening(1151) [CD] OK | FuryOfTheAncients | - |
| bloodTerminator | 1 | SavageEchoes(1230) [CD] OK | RedRampage | - |

### ThousandSons — 5 kits, 7 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| thousDaemonPrince | 2 | AetherStride(1208) [--] NO-OP SUMMON<br>InfernalCannon(1209) [--] NO-OP DAMAGE(Flame) | - | - |
| thousSekhetar | 2 | HeavyWarpFlamer(1227) [-D] NO-OP DAMAGE(Flame) | PropheticSentinel | - |
| thousAhriman | 1 | Doombolt(1102) [C-] OK | PsychicStalk | - |
| thousSorcerer | 1 | AttemptedPossession(1101) [--] NO-OP EFFECT/BUFF | - | - |
| thousTerminator | 1 | HellfyreMissileRack(1088) [--] NO-OP DAMAGE(HeavyRound) | - | - |

### BlackTemplars — 5 kits, 6 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| templAggressor | 2 | FragstormGrenadeLauncher(1048) [--] NO-OP DAMAGE(Blast) | Boltstorm | - |
| templAncient | 1 | UnbreakableDuty(1061) [--] NO-OP EFFECT/BUFF | - | - |
| templChampion | 1 | HolyDuel(1050) [-D] NO-OP EFFECT/BUFF | - | - |
| templHelbrecht | 1 | CrusadeOfWrath(1049) [--] NO-OP EFFECT/BUFF | - | - |
| templSwordBrother | 1 | ThunderousAssault(1043) [C-] OK | ChampionOfTheFeast | - |

### Custodes — 5 kits, 6 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| custoBladeChampion | 2 | MartialInspiration(1191) [--] NO-OP DAMAGE(Eviscerate) | LegacyOfCombat | - |
| custoAtlacoya | 1 | TalonsOfTheEmperor(1195) [--] NO-OP DAMAGE(Power) | - | - |
| custoKyrus | 1 | VigilanceEternal(1202) [CD] OK | UnwaveringSentinel | - |
| custoTrajann | 1 | MomentShackle(1184) [C-] OK | LegendaryCommander | - |
| custoVexilusPraetor | 1 | VexillaMagnifica(1183) [-D] NO-OP DAMAGE(Physical) | - | - |

### LeaguesOfVotann — 5 kits, 6 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| votanChampion | 2 | MassDriverAccelerator(1222) [-D] NO-OP DAMAGE(DirectDamage) | ModifiedExoarmour | - |
| votanBeserk | 1 | AugmentedAssault(1221) [C-] OK | FuryFromTheDelve | - |
| votanIronmaster | 1 | GravitonRifle(1206) [C-] OK | EcogSupport | - |
| votanMemnyr | 1 | IronkinSteeljack(1219) [C-] OK | PredictiveGuidance | - |
| votanUthar | 1 | AncestralFortune(1207) [C-] OK | GrimEfficiency | - |

### SpaceWolves — 4 kits, 6 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| spaceHound | 2 | GrapnelLauncher(1090) [-D] NO-OP DAMAGE(Physical) | HuntersBeyondDeath | - |
| spaceWolfPriest | 2 | RitesOfMorkai(1211) [--] NO-OP EFFECT/BUFF | HealingBalms | - |
| spaceBlackmane | 1 | WarHowl(1106) [--] NO-OP EFFECT/BUFF | - | - |
| spaceWulfen | 1 | GreatFrostAxe(1089) [C-] OK | SavageKiller | - |

### Tau — 5 kits, 6 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| tauFarsight | 2 | ExemplarOfTheMontka(1210) [--] NO-OP EFFECT/BUFF | WayOfTheShortBlade | - |
| tauAunShi | 1 | InspiredToGreatness(1082) [CD] OK | SereneUnifier | - |
| tauDarkstrider | 1 | FightingRetreat(1081) [CD] OK | StructuralAnalyser | - |
| tauMarksman | 1 | SeekerMissileFrequencyLock(1069) [--] NO-OP DAMAGE(HeavyRound) | - | - |
| tauShadowsun | 1 | ExemplarOfTheKauyon(1087) [--] NO-OP DAMAGE(Blast) | - | - |

### WorldEaters — 5 kits, 6 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| worldTerminator | 2 | BloodyFury(1129) [-D] NO-OP DAMAGE(Chain) | WrathfulDevotion | - |
| worldEightbound | 1 | OverwhelmingWrath(1141) [--] NO-OP DAMAGE(Eviscerate) | - | - |
| worldExecutions | 1 | MurderousSwing(1137) [CD] OK | TrophyTaker | - |
| worldJakhal | 1 | JakhalStimms(1131) [C-] OK | Skullsmasher | - |
| worldKharn | 1 | KillMaimBurn(1132) [--] NO-OP DAMAGE(Piercing) | - | - |

### AstraMilitarum — 4 kits, 5 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| astraDreir | 2 | LeadingTheCharge(1204) [--] NO-OP DAMAGE(Power) | ToughToKill | - |
| astraOrdnance | 1 | BasiliskBarrage(1026) [C-] OK | - | IndirectFire(x9) |
| astraPrimarisPsy | 1 | PsychicMaelstrom(1027) [--] NO-OP DAMAGE(Psychic) | - | - |
| astraYarrick | 1 | SendInTheNextWave(1016) [CD] OK | SummaryExecution | - |

### DarkAngels — 4 kits, 5 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| darkaSternguard | 2 | SternguardFocus(1228) [--] NO-OP EFFECT/BUFF | SpecialIssueCombiMelta | - |
| darkaCompanion | 1 | CalibaniteGreatsword(1189) [C-] OK | EnmityForTheUnworthy | - |
| darkaHellblaster | 1 | Supercharge(1103) [C-] OK | GrimRetribution | - |
| darkaTerminator | 1 | PlasmaCannon(1150) [CD] OK | Deathwing | - |

### Sisterhood — 4 kits, 5 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| adeptHospitaller | 2 | RitesOfRestoration(1039) [-D] NO-OP HEAL | MedicusMinistorum | - |
| adeptCelestine | 1 | SkyStrike(1025) [C-] OK | GeminaeSuperia | - |
| adeptMorvenn | 1 | SanctorumMissile(1062) [C-] OK | RighteousRepugnance | - |
| adeptRetributor | 1 | ArmoriumCherub(1014) [CD] OK | FireOfAbsolution | - |

### AdeptusAstartes — 2 kits, 4 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| astarCyrus | 2 | StrikeFromTheShadows(1225) [--] NO-OP DAMAGE(Bolter) | HaywireMine | - |
| astarLysander | 2 | TitanhammerSquad(1231) [--] NO-OP HEAL | IconOfObstinacy | - |

### AdeptusMechanicus — 3 kits, 4 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| admecManipulus | 2 | DefendTheDivineWork(1117) [-D] NO-OP REPAIR | GalvanicField | - |
| admecDestroyer | 1 | SentinelDirectives(1139) [C-] OK | - | Vehicle(x8) |
| admecRuststalker | 1 | CordClaw(1122) [CD] OK | OptimizedGait | - |

### Orks — 3 kits, 4 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| orksBigMek | 2 | GrotTank(1057) [--] NO-OP SUMMON | KustomForceFieldReworked | - |
| orksNob | 1 | UnstoppableMomentumReworked(1152) [--] NO-OP DAMAGE(DirectDamage) | - | - |
| orksWarboss | 1 | Waaagh(1058) [C-] OK | LightImUp | - |

### BlackLegion — 4 kits, 4 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| blackAbaddon | 1 | Drachnyen(1029) [CD] OK | FirstAmongTraitors | - |
| blackHaarken | 1 | HeraldOfTheApocalypse(1020) [CD] OK | HeadClaimer | - |
| blackPossession | 1 | Incursion(1021) [CD] OK | Possession | - |
| blackTerminator | 1 | BringerOfDespair(1022) [C-] OK | HatefulAssault | - |

### Genestealers — 3 kits, 3 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| genesBiophagus | 1 | AberrantHypermorph(1166) [CD] OK | TwistedScience | - |
| genesMagus | 1 | MindControl(1164) [--] NO-OP EFFECT/BUFF | - | - |
| genesPatriarch | 1 | MightFromBelow(1165) [--] NO-OP DAMAGE(Psychic) | - | - |

### Tyranids — 3 kits, 3 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| tyranBiovore | 1 | BioMinefield(1144) [--] NO-OP SUMMON<br>SporeMineLauncher(1145) [C-] OK | - | - |
| tyranParasite | 1 | ItItches(1121) [-D] NO-OP SUMMON | - | - |
| tyranWingedPrime | 1 | AlphaWarrior(1112) [C-] OK | SynapticLinchpin | - |

### Ultramarines — 3 kits, 3 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| ultraEliminatorSgt | 1 | MortisRound(1004) [C-] OK | CamoCloak | - |
| ultraInceptorSgt | 1 | DeathFromAbove(1003) [C-] OK | ShockAssault | - |
| ultraTigurius | 1 | StormOfWrath(1019) [--] NO-OP DAMAGE(Psychic) | - | - |

### DeathGuard — 1 kits, 1 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| deathPutrifier | 1 | FoulInfusion(1038) [-D] NO-OP DAMAGE(Toxic) | - | - |

## Kits lineup COMPLETS (37)

adeptCanoness, adeptExorcist, admecDominus, admecMarshall, astraBullgryn, astraCreed, astraOrdnanceBattery, blackForgefiend, blackObliterator, darkaAsmodai, darkaAzrael, darkaStormSpeeder, deathBlightbringer, deathBlightlord, deathCrawler, deathRotbone, deathTyphus, eldarFarseer, genesKelermorph, genesPrimus, necroSpyder, orksKillaKan, orksRukkatrukk, orksRuntherd, spaceRockfist, spaceStormcaller, tauBroadside, tauCrisis, thousInfernalMaster, thousTzaangor, tyranDeathleaper, tyranNeurothrope, tyranTyrantGuard, ultraApothecary, ultraCalgar, ultraDreadnought, ultraTitus
