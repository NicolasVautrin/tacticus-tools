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

- Unites lineup : **127** ; kits COMPLETS (aucun manque detecte) : **87** ; kits avec du travail : **40**
- Volume total : **41** items manquants (actives no-op + passifs/traits non registres)
- HORS total — voies conditionnelles : **34** abilities non portees (11 mythiques, 23 reliques equipables)

### Priorite par faction (volume decroissant)

| faction | kits | items |
|---|---:|---:|
| EmperorsChildren | 4 | 4 |
| LeaguesOfVotann | 4 | 4 |
| AstraMilitarum | 3 | 3 |
| DarkAngels | 3 | 3 |
| Sisterhood | 3 | 3 |
| SpaceWolves | 3 | 3 |
| WorldEaters | 3 | 3 |
| AdeptusMechanicus | 2 | 2 |
| Aeldari | 2 | 2 |
| BlackLegion | 2 | 2 |
| BloodAngels | 2 | 2 |
| Custodes | 2 | 2 |
| Necrons | 2 | 2 |
| Tau | 1 | 2 |
| Tyranids | 2 | 2 |
| Genestealers | 1 | 1 |
| ThousandSons | 1 | 1 |

## Par faction (kits avec du travail)

### AdeptusMechanicus — 2 kits, 2 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| admecDestroyer | 1 | SentinelDirectives(1139) [C-] OK | - | Vehicle(x8) |
| admecManipulus | 1 | DefendTheDivineWork(1117) [CD] OK | GalvanicField | - |

### Aeldari — 2 kits, 2 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| eldarJainZar | 1 | SilentDeath(1068) [C-] OK | TerrorsLament | - |
| eldarLhykhis | 1 | EmpyricAmbush(1232) [C-] OK | WhisperingWeb | - |

### AstraMilitarum — 3 kits, 3 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| astraDreir | 1 | LeadingTheCharge(1204) [C-] OK | ToughToKill | - |
| astraOrdnance | 1 | BasiliskBarrage(1026) [C-] OK | - | IndirectFire(x9) |
| astraYarrick | 1 | SendInTheNextWave(1016) [CD] OK | SummaryExecution | - |

### BlackLegion — 2 kits, 2 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| blackHaarken | 1 | HeraldOfTheApocalypse(1020) [CD] OK | HeadClaimer | - |
| blackPossession | 1 | Incursion(1021) [CD] OK | Possession | - |

### BloodAngels — 2 kits, 2 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| bloodIntercessor | 1 | HammerOfWrath(1153) [CD] OK | AggressiveOnslaught | - |
| bloodTerminator | 1 | SavageEchoes(1230) [CD] OK | RedRampage | - |

### Custodes — 2 kits, 2 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| custoBladeChampion | 1 | MartialInspiration(1191) [C-] OK | LegacyOfCombat | - |
| custoKyrus | 1 | VigilanceEternal(1202) [CD] OK | UnwaveringSentinel | - |

### DarkAngels — 3 kits, 3 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| darkaCompanion | 1 | CalibaniteGreatsword(1189) [C-] OK | EnmityForTheUnworthy | - |
| darkaHellblaster | 1 | Supercharge(1103) [CD] OK | GrimRetribution | - |
| darkaTerminator | 1 | PlasmaCannon(1150) [CD] OK | Deathwing | - |

### EmperorsChildren — 4 kits, 4 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| emperExultant | 1 | EuphoricStrikes(1198) [C-] OK | RefusalToBeOutdone | - |
| emperFlawlessBlade | 1 | DaemonicPatrons(1203) [C-] OK | EcstaticSlaughter | - |
| emperKakophonist | 1 | DoomSiren(1199) [CD] OK | ObsessiveAnnunciation | - |
| emperLucius | 1 | LashOfTorment(1196) [C-] OK | ArmourOfShriekingSouls | - |

### Genestealers — 1 kits, 1 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| genesBiophagus | 1 | AberrantHypermorph(1166) [CD] OK | TwistedScience | - |

### LeaguesOfVotann — 4 kits, 4 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| votanBeserk | 1 | AugmentedAssault(1221) [C-] OK | FuryFromTheDelve | - |
| votanIronmaster | 1 | GravitonRifle(1206) [C-] OK | EcogSupport | - |
| votanMemnyr | 1 | IronkinSteeljack(1219) [C-] OK | PredictiveGuidance | - |
| votanUthar | 1 | AncestralFortune(1207) [CD] OK | GrimEfficiency | - |

### Necrons — 2 kits, 2 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| necroChronomancer | 1 | Chronometron(1226) [CD] OK | TimesplinterMantle | - |
| necroPlasmancer | 1 | HarbingerOfDestruction(1008) [CD] OK | LivingLightning | - |

### Sisterhood — 3 kits, 3 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| adeptCelestine | 1 | SkyStrike(1025) [CD] OK | GeminaeSuperia | - |
| adeptHospitaller | 1 | RitesOfRestoration(1039) [CD] OK | MedicusMinistorum | - |
| adeptRetributor | 1 | ArmoriumCherub(1014) [CD] OK | FireOfAbsolution | - |

### SpaceWolves — 3 kits, 3 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| spaceHound | 1 | GrapnelLauncher(1090) [CD] OK | HuntersBeyondDeath | - |
| spaceWolfPriest | 1 | RitesOfMorkai(1211) [C-] OK | HealingBalms | - |
| spaceWulfen | 1 | GreatFrostAxe(1089) [CD] OK | SavageKiller | - |

### Tau — 1 kits, 2 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| tauFarsight | 2 | ExemplarOfTheMontka(1210) [--] NO-OP EFFECT/BUFF | WayOfTheShortBlade | - |

### ThousandSons — 1 kits, 1 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| thousDaemonPrince | 1 | AetherStride(1208) [--] NO-OP SUMMON<br>InfernalCannon(1209) [C-] OK | - | - |

### Tyranids — 2 kits, 2 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| tyranBiovore | 1 | BioMinefield(1144) [--] NO-OP SUMMON<br>SporeMineLauncher(1145) [C-] OK | - | - |
| tyranWingedPrime | 1 | AlphaWarrior(1112) [C-] OK | SynapticLinchpin | - |

### WorldEaters — 3 kits, 3 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| worldExecutions | 1 | MurderousSwing(1137) [CD] OK | TrophyTaker | - |
| worldJakhal | 1 | JakhalStimms(1131) [C-] OK | Skullsmasher | - |
| worldTerminator | 1 | BloodyFury(1129) [CD] OK | WrathfulDevotion | - |

## Kits lineup COMPLETS (87)

adeptCanoness, adeptExorcist, adeptMorvenn, admecDominus, admecMarshall, admecRuststalker, astarCyrus, astarLysander, astraBullgryn, astraCreed, astraOrdnanceBattery, astraPrimarisPsy, blackAbaddon, blackForgefiend, blackObliterator, blackTerminator, bloodDante, bloodDeathCompany, bloodMephiston, bloodSanguinary, custoAtlacoya, custoTrajann, custoVexilusPraetor, darkaAsmodai, darkaAzrael, darkaSternguard, darkaStormSpeeder, deathBlightbringer, deathBlightlord, deathCrawler, deathPutrifier, deathRotbone, deathTyphus, eldarAutarch, eldarFarseer, eldarMauganRa, eldarRanger, emperNoiseMarine, genesKelermorph, genesMagus, genesPatriarch, genesPrimus, necroDestroyer, necroOverlord, necroReanimator, necroSpyder, necroWarden, orksBigMek, orksKillaKan, orksNob, orksRukkatrukk, orksRuntherd, orksWarboss, spaceBlackmane, spaceRockfist, spaceStormcaller, tauAunShi, tauBroadside, tauCrisis, tauDarkstrider, tauMarksman, tauShadowsun, templAggressor, templAncient, templChampion, templHelbrecht, templSwordBrother, thousAhriman, thousInfernalMaster, thousSekhetar, thousSorcerer, thousTerminator, thousTzaangor, tyranDeathleaper, tyranNeurothrope, tyranParasite, tyranTyrantGuard, ultraApothecary, ultraCalgar, ultraDreadnought, ultraEliminatorSgt, ultraInceptorSgt, ultraTigurius, ultraTitus, votanChampion, worldEightbound, worldKharn

## HORS total — voies conditionnelles (34 abilities non portees)

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
| DawnBlade | item | 1 | tauFarsight |
| Dw02AdvancedBurstCannon | item | 1 | tauCrisis |
| HeadwoppasKillchoppa | item | 1 | orksWarboss |
| Helspear | item | 1 | blackHaarken |
| Lakrimae | item | 1 | deathTyphus |
| Maugetar | item | 1 | eldarMauganRa |
| MonsterSlayerOfCaliban | item | 1 | darkaCompanion |
| NornCrown | item | 1 | tyranNeurothrope |
| OrbsOfDecay | item | 3 | deathBlightbringer, deathPutrifier, deathRotbone |
| ParagonSpear | item | 1 | custoKyrus |
| PhasalSubjugator | item | 1 | necroOverlord |
| PhoenixGem | item | 1 | eldarAutarch |
| RelicOfLostCadia | item | 3 | astraBullgryn, astraOrdnance, astraPrimarisPsy |
| RelicPowerFist | item | 3 | bloodIntercessor, darkaTerminator, templAggressor |
| SabreOfSacrifice | item | 1 | astraDreir |
| TalismanOfRage | item | 3 | worldEightbound, worldExecutions, worldJakhal |
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

Portees (au moins un registre) : **9** — AmuletOfTheVoidwyrm, DaemonfleshPlate, IntoxicatingElixir, KardiocoreGalvanus, MawClawsOfThyrax, NetherRealmCasket, RelicBoltPistol, SupaCyborkBody, TalonOfHorus
