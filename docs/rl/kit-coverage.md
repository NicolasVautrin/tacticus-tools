# Couverture moteur par KIT (unites lineup)

> Genere par `scripts/python/audit_kit_coverage.py` (kit gameconfig x registres moteur
> des deux faces). Vue KIT-centrique complementaire de `combat-ability-coverage.md`
> (par-ability). **Ne jamais fusionner un conflit sur ce fichier : le REGENERER.**
>
> Faces : `[CD]` = combat/decision portees, `[--]` = aucune ; `D` couvre les TROIS
> registres de scoring (non-comparables + overrides custom des comparables +
> sous-classes `AActiveAbility` par ability). La mention « NC classee, utilite NC non
> portee » marque une ability reconnue NonComparable dont l'utilite reste a porter :
> c'est un travail restant, pas une face couverte. Les MISSING passifs/traits sont des
> CANDIDATS (approximation registres, cf. docstring du script) : trancher au recon du kit.
>
> **Ce que le total compte** : les items du kit INTRINSEQUE (`activeAbilities`,
> `passiveAbilities`, traits de kit). **Ce qu'il ne compte pas** : les voies
> CONDITIONNELLES (mythique a debloquer, relique a equiper) — elles ont leur propre
> section, chiffree, en fin de document. Les voies `trait`/`liveevent`/`summon`/`tile`
> ne sont derivables d'aucune source offline (`case-323-unit-map-attribution-voies.md`).
>
> Sections detaillees ordonnees par NOM de faction (ordre stable, pour qu'une
> regeneration ne produise un diff que la ou le contenu bouge) ; la priorisation par
> volume est la table de bilan ci-dessous.

## Bilan

- Unites lineup : **127** ; kits COMPLETS (aucun manque detecte) : **59** ; kits avec du travail : **68**
- Volume total : **84** items manquants (actives no-op + passifs/traits non registres)
- HORS total — voies conditionnelles : **42** abilities non portees (11 mythiques, 31 reliques equipables)

### Priorite par faction (volume decroissant)

| faction | kits | items |
|---|---:|---:|
| EmperorsChildren | 5 | 8 |
| BloodAngels | 5 | 6 |
| Necrons | 5 | 6 |
| Custodes | 4 | 5 |
| DarkAngels | 4 | 5 |
| LeaguesOfVotann | 5 | 5 |
| Sisterhood | 4 | 5 |
| SpaceWolves | 4 | 5 |
| ThousandSons | 3 | 5 |
| AstraMilitarum | 3 | 4 |
| BlackTemplars | 4 | 4 |
| WorldEaters | 3 | 4 |
| AdeptusAstartes | 2 | 3 |
| AdeptusMechanicus | 3 | 3 |
| Aeldari | 3 | 3 |
| BlackLegion | 3 | 3 |
| Orks | 2 | 3 |
| Tyranids | 3 | 3 |
| Genestealers | 2 | 2 |
| Tau | 1 | 2 |

## Par faction (kits avec du travail)

### AdeptusAstartes — 2 kits, 3 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| astarCyrus | 1 | StrikeFromTheShadows(1225) [--] NO-OP DAMAGE(Bolter) | - | - |
| astarLysander | 2 | TitanhammerSquad(1231) [--] NO-OP HEAL | IconOfObstinacy | - |

### AdeptusMechanicus — 3 kits, 3 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| admecDestroyer | 1 | SentinelDirectives(1139) [C-] OK | - | Vehicle(x8) |
| admecManipulus | 1 | DefendTheDivineWork(1117) [CD] OK | GalvanicField | - |
| admecRuststalker | 1 | CordClaw(1122) [CD] OK | OptimizedGait | - |

### Aeldari — 3 kits, 3 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| eldarJainZar | 1 | SilentDeath(1068) [C-] OK | TerrorsLament | - |
| eldarLhykhis | 1 | EmpyricAmbush(1232) [C-] OK | WhisperingWeb | - |
| eldarRanger | 1 | FireAndReposition(1063) [--] NO-OP EFFECT/BUFF | - | - |

### AstraMilitarum — 3 kits, 4 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| astraDreir | 2 | LeadingTheCharge(1204) [--] NO-OP DAMAGE(Power) | ToughToKill | - |
| astraOrdnance | 1 | BasiliskBarrage(1026) [C-] OK | - | IndirectFire(x9) |
| astraYarrick | 1 | SendInTheNextWave(1016) [CD] OK | SummaryExecution | - |

### BlackLegion — 3 kits, 3 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| blackAbaddon | 1 | Drachnyen(1029) [CD] OK | FirstAmongTraitors | - |
| blackHaarken | 1 | HeraldOfTheApocalypse(1020) [CD] OK | HeadClaimer | - |
| blackPossession | 1 | Incursion(1021) [CD] OK | Possession | - |

### BlackTemplars — 4 kits, 4 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| templAggressor | 1 | FragstormGrenadeLauncher(1048) [CD] OK | Boltstorm | - |
| templAncient | 1 | UnbreakableDuty(1061) [--] NO-OP EFFECT/BUFF | - | - |
| templChampion | 1 | HolyDuel(1050) [-D] NO-OP EFFECT/BUFF | - | - |
| templHelbrecht | 1 | CrusadeOfWrath(1049) [--] NO-OP EFFECT/BUFF | - | - |

### BloodAngels — 5 kits, 6 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| bloodDante | 1 | LightOfSanguinius(1177) [-D] NO-OP DAMAGE(Melta) | - | - |
| bloodIntercessor | 1 | HammerOfWrath(1153) [CD] OK | AggressiveOnslaught | - |
| bloodMephiston | 1 | TheQuickening(1151) [CD] OK | FuryOfTheAncients | - |
| bloodSanguinary | 2 | BloodChalice(1175) [--] NO-OP HEAL | SanguinaryPriest | - |
| bloodTerminator | 1 | SavageEchoes(1230) [CD] OK | RedRampage | - |

### Custodes — 4 kits, 5 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| custoAtlacoya | 1 | TalonsOfTheEmperor(1195) [--] NO-OP DAMAGE(Power) | - | - |
| custoBladeChampion | 2 | MartialInspiration(1191) [--] NO-OP DAMAGE(Eviscerate) | LegacyOfCombat | - |
| custoKyrus | 1 | VigilanceEternal(1202) [CD] OK | UnwaveringSentinel | - |
| custoVexilusPraetor | 1 | VexillaMagnifica(1183) [-D] NO-OP DAMAGE(Physical) | - | - |

### DarkAngels — 4 kits, 5 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| darkaCompanion | 1 | CalibaniteGreatsword(1189) [C-] OK | EnmityForTheUnworthy | - |
| darkaHellblaster | 1 | Supercharge(1103) [CD] OK | GrimRetribution | - |
| darkaSternguard | 2 | SternguardFocus(1228) [--] NO-OP EFFECT/BUFF | SpecialIssueCombiMelta | - |
| darkaTerminator | 1 | PlasmaCannon(1150) [CD] OK | Deathwing | - |

### EmperorsChildren — 5 kits, 8 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| emperExultant | 2 | EuphoricStrikes(1198) [--] NO-OP DAMAGE(Power) | RefusalToBeOutdone | - |
| emperFlawlessBlade | 2 | DaemonicPatrons(1203) [--] NO-OP EFFECT/BUFF | EcstaticSlaughter | - |
| emperKakophonist | 1 | DoomSiren(1199) [CD] OK | ObsessiveAnnunciation | - |
| emperLucius | 2 | LashOfTorment(1196) [--] NO-OP DAMAGE(Eviscerate) | ArmourOfShriekingSouls | - |
| emperNoiseMarine | 1 | ExcruciatingFrequencies(1197) [--] NO-OP DAMAGE(Blast) | - | - |

### Genestealers — 2 kits, 2 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| genesBiophagus | 1 | AberrantHypermorph(1166) [CD] OK | TwistedScience | - |
| genesMagus | 1 | MindControl(1164) [--] NO-OP EFFECT/BUFF | - | - |

### LeaguesOfVotann — 5 kits, 5 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| votanBeserk | 1 | AugmentedAssault(1221) [C-] OK | FuryFromTheDelve | - |
| votanChampion | 1 | MassDriverAccelerator(1222) [-D] NO-OP DAMAGE(DirectDamage) | - | - |
| votanIronmaster | 1 | GravitonRifle(1206) [C-] OK | EcogSupport | - |
| votanMemnyr | 1 | IronkinSteeljack(1219) [C-] OK | PredictiveGuidance | - |
| votanUthar | 1 | AncestralFortune(1207) [CD] OK | GrimEfficiency | - |

### Necrons — 5 kits, 6 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| necroChronomancer | 1 | Chronometron(1226) [CD] OK | TimesplinterMantle | - |
| necroDestroyer | 1 | MultiThreatEliminator(1006) [CD] OK | InescapableDeath | - |
| necroPlasmancer | 1 | HarbingerOfDestruction(1008) [CD] OK | LivingLightning | - |
| necroReanimator | 2 | ReanimationBeam(1223) [--] NO-OP REPAIR<br>NanoscarabRepairProtocols(1224) [--] NO-OP REPAIR | - | - |
| necroWarden | 1 | AdaptiveStrategy(1005) [--] NO-OP EFFECT/BUFF | - | - |

### Orks — 2 kits, 3 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| orksBigMek | 2 | GrotTank(1057) [--] NO-OP SUMMON | KustomForceFieldReworked | - |
| orksWarboss | 1 | Waaagh(1058) [C-] OK | LightImUp | - |

### Sisterhood — 4 kits, 5 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| adeptCelestine | 1 | SkyStrike(1025) [CD] OK | GeminaeSuperia | - |
| adeptHospitaller | 2 | RitesOfRestoration(1039) [-D] NO-OP HEAL | MedicusMinistorum | - |
| adeptMorvenn | 1 | SanctorumMissile(1062) [CD] OK | RighteousRepugnance | - |
| adeptRetributor | 1 | ArmoriumCherub(1014) [CD] OK | FireOfAbsolution | - |

### SpaceWolves — 4 kits, 5 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| spaceBlackmane | 1 | WarHowl(1106) [--] NO-OP EFFECT/BUFF | - | - |
| spaceHound | 1 | GrapnelLauncher(1090) [CD] OK | HuntersBeyondDeath | - |
| spaceWolfPriest | 2 | RitesOfMorkai(1211) [--] NO-OP EFFECT/BUFF | HealingBalms | - |
| spaceWulfen | 1 | GreatFrostAxe(1089) [CD] OK | SavageKiller | - |

### Tau — 1 kits, 2 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| tauFarsight | 2 | ExemplarOfTheMontka(1210) [--] NO-OP EFFECT/BUFF | WayOfTheShortBlade | - |

### ThousandSons — 3 kits, 5 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| thousDaemonPrince | 2 | AetherStride(1208) [--] NO-OP SUMMON<br>InfernalCannon(1209) [--] NO-OP DAMAGE(Flame) | - | - |
| thousSekhetar | 2 | HeavyWarpFlamer(1227) [-D] NO-OP DAMAGE(Flame) | PropheticSentinel | - |
| thousSorcerer | 1 | AttemptedPossession(1101) [--] NO-OP EFFECT/BUFF | - | - |

### Tyranids — 3 kits, 3 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| tyranBiovore | 1 | BioMinefield(1144) [--] NO-OP SUMMON<br>SporeMineLauncher(1145) [C-] OK | - | - |
| tyranParasite | 1 | ItItches(1121) [-D] NO-OP SUMMON | - | - |
| tyranWingedPrime | 1 | AlphaWarrior(1112) [C-] OK | SynapticLinchpin | - |

### WorldEaters — 3 kits, 4 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| worldExecutions | 1 | MurderousSwing(1137) [CD] OK | TrophyTaker | - |
| worldJakhal | 1 | JakhalStimms(1131) [C-] OK | Skullsmasher | - |
| worldTerminator | 2 | BloodyFury(1129) [-D] NO-OP DAMAGE(Chain) | WrathfulDevotion | - |

## Kits lineup COMPLETS (59)

adeptCanoness, adeptExorcist, admecDominus, admecMarshall, astraBullgryn, astraCreed, astraOrdnanceBattery, astraPrimarisPsy, blackForgefiend, blackObliterator, blackTerminator, bloodDeathCompany, custoTrajann, darkaAsmodai, darkaAzrael, darkaStormSpeeder, deathBlightbringer, deathBlightlord, deathCrawler, deathPutrifier, deathRotbone, deathTyphus, eldarAutarch, eldarFarseer, eldarMauganRa, genesKelermorph, genesPatriarch, genesPrimus, necroOverlord, necroSpyder, orksKillaKan, orksNob, orksRukkatrukk, orksRuntherd, spaceRockfist, spaceStormcaller, tauAunShi, tauBroadside, tauCrisis, tauDarkstrider, tauMarksman, tauShadowsun, templSwordBrother, thousAhriman, thousInfernalMaster, thousTerminator, thousTzaangor, tyranDeathleaper, tyranNeurothrope, tyranTyrantGuard, ultraApothecary, ultraCalgar, ultraDreadnought, ultraEliminatorSgt, ultraInceptorSgt, ultraTigurius, ultraTitus, worldEightbound, worldKharn

## HORS total — voies conditionnelles (42 abilities non portees)

> Une unite `lineup` porte aussi des abilities par deux voies que le kit n'expose
> pas : `mythic` (`units.<kind>.<id>.mythicAbilities`, a DEBLOQUER) et `item`
> (`items[*].abilityId` + `allowedUnits`, la relique a EQUIPER). Elles sont hors du
> total parce que leur nature differe — mais les taire reproduirait la cecite de #323,
> qui a fait rendre un faux « 0 unite, DEAD ». Une relique se ventile en TROIS etats
> (equipee au seed / porteur au pool relique non equipee / porteur hors pool) :
> `case-323-unit-map-attribution-voies.md` §5. La voie `relicAbilities` ne touche
> AUCUNE unite `lineup` (0 mesure) — elle n'apparait donc pas ici.

| ability | voie | porteurs lineup | ex. |
|---|---|---:|---|
| BladeOfTheAncestors | item | 1 | votanUthar |
| BookOfFate | item | 3 | blackPossession, thousInfernalMaster, thousSorcerer |
| ChaliceOfBaal | item | 1 | bloodSanguinary |
| DaemonfleshPlate | item | 4 | blackTerminator, deathBlightlord, thousTerminator, worldTerminator |
| DawnBlade | item | 1 | tauFarsight |
| Dw02AdvancedBurstCannon | item | 1 | tauCrisis |
| HeadwoppasKillchoppa | item | 1 | orksWarboss |
| Helspear | item | 1 | blackHaarken |
| IntoxicatingElixir | item | 4 | emperExultant, emperFlawlessBlade, emperKakophonist, emperNoiseMarine |
| KardiocoreGalvanus | item | 3 | admecDestroyer, admecMarshall, admecRuststalker |
| Lakrimae | item | 1 | deathTyphus |
| Maugetar | item | 1 | eldarMauganRa |
| MawClawsOfThyrax | item | 4 | genesPatriarch, tyranParasite, tyranTyrantGuard, tyranWingedPrime |
| MonsterSlayerOfCaliban | item | 1 | darkaCompanion |
| NetherRealmCasket | item | 3 | necroDestroyer, necroSpyder, necroWarden |
| NornCrown | item | 1 | tyranNeurothrope |
| OrbsOfDecay | item | 3 | deathBlightbringer, deathPutrifier, deathRotbone |
| ParagonSpear | item | 1 | custoKyrus |
| PhasalSubjugator | item | 1 | necroOverlord |
| PhoenixGem | item | 1 | eldarAutarch |
| RelicBoltPistol | item | 7 | astarCyrus, darkaHellblaster, darkaSternguard, spaceHound |
| RelicOfLostCadia | item | 3 | astraBullgryn, astraOrdnance, astraPrimarisPsy |
| RelicPowerFist | item | 3 | bloodIntercessor, darkaTerminator, templAggressor |
| SabreOfSacrifice | item | 1 | astraDreir |
| SupaCyborkBody | item | 3 | orksBigMek, orksNob, orksRuntherd |
| TalismanOfRage | item | 3 | worldEightbound, worldExecutions, worldJakhal |
| TalonOfHorus | item | 1 | blackAbaddon |
| TheArdentBlade | item | 1 | adeptCelestine |
| Vitarus | item | 1 | bloodMephiston |
| VolummsMasterArtifice | item | 1 | votanIronmaster |
| WyrdmakersHelm | item | 1 | spaceWolfPriest |
| BlightedLand | mythic | 1 | deathCrawler |
| CabalOfSorcerers | mythic | 1 | thousDaemonPrince |
| ContemptuousDisregard | mythic | 1 | blackForgefiend |
| ElectrochaffBackups | mythic | 1 | tauBroadside |
| GuardianConstruct | mythic | 1 | necroReanimator |
| HyperCorrosiveAcid | mythic | 1 | tyranBiovore |
| MastersOfManoeuvre | mythic | 1 | darkaStormSpeeder |
| MoreGitzOverEre | mythic | 1 | orksRukkatrukk |
| OnMyPosition | mythic | 1 | astraOrdnanceBattery |
| ShieldOfFaith | mythic | 1 | adeptExorcist |
| WisdomOfTheAncients | mythic | 1 | ultraDreadnought |

Portees (au moins un registre) : **1** — AmuletOfTheVoidwyrm
