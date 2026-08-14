"""engine.entities.TriggeredAbilityType -- enum natif `TriggeredAbilityType` (mirror 1:1 complet).

Mirror 1:1 de `IdunBattle.Entities.Enum.TriggeredAbilityType`, GENERE depuis la table VERSIONNEE
`data/symbols/<CURRENT>/frida/enums.tsv` -- meme demarche que `UnitTrait` (#146) /
`EventTriggerType` (#155) / `DamageTrait` (#156). Source unique id<->nom : les constantes id-hex
eparses du port sont converties vers cet enum (#158).

  Regenerer : python scripts/python/regen_enum_mirrors.py --mirror TriggeredAbilityType --ecrire
  Verifier  : python scripts/python/probe_313_enum_mirror_bijection.py
  Cliquet   : scripts/python/tests/test_enum_mirror_ratchet_offline.py

CE MIRROR N'EST PAS QU'UNE TABLE, C'EST UN DICTIONNAIRE CONSOMME PAR NOM (#313)
------------------------------------------------------------------------------
`triggered_ability_ids()` (plus bas) fait `TriggeredAbilityType.__members__.get(nom_gameconfig)`
et jette silencieusement ce qu'il ne connait pas (`if m is not None`). Un membre MANQUANT n'est
donc pas inerte : il RETIRE un passif du kit porte, sans erreur ni trace. Un membre MORT, lui, ne
peut plus rien matcher -- c'est du code qui a l'air vivant. La bijection avec le build courant est
pour cette raison gardee DANS LES DEUX SENS, et non seulement « les membres presents sont justes ».

Valeur == id natif. ATTENTION (#157/#158) : le MEME id peut appartenir a des enums DIFFERENTS
selon le contexte (ex. 1017 = `EffectType.ActOfFaith` ET `UnitTrait.BigTarget`) -> chaque site
de conversion verifie l'enum correct.
"""
from __future__ import annotations

from enum import IntEnum


class TriggeredAbilityType(IntEnum):
    """Mirror 1:1 de `IdunBattle.Entities.Enum.TriggeredAbilityType`. Valeur == id natif.

    Le COMPTE de membres n'est pas ecrit ici : il change a chaque build (573 sur `gqfc5mff6c`,
    476 sur `rnca9r7q6c`), et un compte fige dans une docstring est la premiere chose qui ment."""
    None_ = 0
    Electrified = 2
    SwampBlockMovement = 5
    FirstAidHeal = 6
    ShrubDefenseBonus = 14
    ForceOfNature = 20
    EnvFireTileDamage = 24
    BrokenIce = 29
    OnFire = 30
    DryBushDefenseBonus = 52
    DryBushFireSpread = 57
    TeleportTile = 60
    Explosive = 72
    SpikySting = 77
    EggLayer = 81
    TerrifyingAbility = 98
    ThornyVines = 105
    LandMine = 114
    PsychicFortress = 1000
    Narthecium = 1001
    ShockAssault = 1002
    CamoCloak = 1003
    RelentlessMarch = 1004
    InescapableDeath = 1005
    FabricatorClawArray = 1006
    LivingLightning = 1007
    ReanimationProtocols = 1008
    WhipcoilBody = 1009
    LivingMetalRepair = 1010
    OverwatchAutoAttack = 1011
    HeavyWeaponExtraDamage = 1012
    PsykerExtraAttack = 1013
    RitesOfBattle = 1014
    LightCover = 1015
    OnFireDamageAbility = 1016
    FireOfAbsolution = 1017
    ActOfFaithAbility = 1018
    AutoRevive = 1019
    LivingLightning_MoveEffect = 1020
    Explodes = 1021
    AutoSummonOnDamage = 1022
    Swarm = 1023
    FinalJustice = 1024
    BattleFatigue = 1025
    ValkyrieStrike_Attack = 1026
    Emplacement = 1027
    AvalancheOfMuscle = 1028
    CallInReinforcements = 1029
    BigTarget = 1030
    HeadClaimer = 1031
    DeathToTheFalseEmperor = 1032
    SummaryExecution = 1033
    Possession = 1034
    UnstoppableFerocity = 1035
    Daemon = 1036
    TeleportStrike = 1037
    HatefulAssault = 1038
    UNUSED_3 = 1039
    UNUSED_4 = 1040
    HungeringSwarm = 1041
    HailOfLivingAmmunition = 1042
    InstinctiveBehaviour = 1043
    SuppressiveFire = 1044
    MartialApotheosis = 1045
    Nightshroud = 1046
    Spotter = 1047
    GeminaeSuperia = 1048
    Lifewards = 1049
    SwornProtector = 1050
    Infiltrate_AddEffect = 1051
    AdrenalGlands = 1052
    BroodProgenitor = 1053
    MassiveScythingTalons = 1054
    SynapticBacklash = 1055
    SynapticImperative = 1056
    BioBarrage = 1057
    LethalMiasma = 1058
    Synapse_AddEffect = 1059
    ShadowInTheWarp_AddEffect = 1060
    Trench = 1061
    GuildBossRunAway = 1062
    ListenUpMaggots = 1063
    FirstAmongTraitors = 1064
    FleshmetalGuns = 1065
    DestroyerHive = 1066
    TaintedNarthecium = 1067
    ExplosiveMaladies = 1068
    MedicusMinistorum = 1069
    CondemnorStake = 1070
    CursedPlagueBell = 1071
    CursedOfTheWalkingPox = 1072
    ContagionsOfNurgle_AddEffect = 1073
    PutridExplosion_Ability = 1074
    SwornProtector_Protect = 1075
    HazeOfCorruption = 1076
    Volatile = 1077
    Detonation = 1078
    PileIn = 1079
    ItsGonnaBlow = 1080
    OiWatchIt = 1081
    SquigHound = 1082
    HeavyBoltPistol = 1083
    BeastSnagga = 1084
    Parry = 1085
    ChampionOfTheFeast = 1086
    Diminutive = 1087
    RunsAway = 1088
    RunsAround = 1089
    Boltstorm = 1090
    DestroyTheWitch = 1091
    MartialSuperiority = 1092
    Ramshackle = 1093
    PrehensilePincerTail = 1095
    SoulHunger = 1096
    AdaptiveToxins = 1097
    Pyreblaster = 1098
    CallRipperSwarms_Spawn = 1099
    CallRipperSwarms_Spawn2 = 1100
    CallRipperSwarms_Spawn3 = 1101
    KustomForceField = 1102
    LightImUp = 1103
    KanOpener = 1104
    SmashaSquigJaws = 1105
    AstartesBanner = 1106
    RighteousRepugnance = 1107
    Dakka = 1108
    DrawFire = 1109
    AutoCounterAttack = 1110
    WireweaveNet = 1111
    PathOfCommand = 1112
    ReinforcedHiveNode = 1113
    Doom = 1114
    InescapableAccuracy = 1115
    Shrapnel = 1116
    UNUSED = 1117
    TerrorsLament = 1118
    MV71SniperDroneSquad = 1119
    SaviorProtocols = 1120
    ObeisanceGenerators = 1121
    NoctilithBeacons = 1122
    PhaeronOfTheStars = 1123
    PhaeronOfTheBlades = 1124
    IntegratedCircuits = 1125
    TargetingProtocols_Attack = 1126
    SeekerMissileFrequencyLock_Attack = 1127
    BreathOfSilence_SetStart = 1128
    AnnihilatorBeam_Attack = 1129
    CloseCombatWeakness = 1130
    Loki_Camouflage = 1131
    NetworkedTargeting = 1132
    CyclicIonBlaster = 1133
    FullThrottle = 1134
    RapidFire = 1135
    PowerUp_Armor = 1136
    PowerUp_Health = 1137
    PowerUp_MeleeHits = 1138
    PowerUp_Damage = 1139
    PowerUp_Hits = 1140
    StormboyzStrike = 1141
    TerminatorArmour = 1142
    StructuralAnalyser = 1143
    FiringPosition = 1144
    SereneUnifier = 1145
    ProperKilly = 1147
    ProphetOfGorkAndMork = 1148
    DaBossIsWatchin = 1149
    UnbridledCarnage = 1150
    NeedsMoreDakka_Attack = 1151
    EreWeGo_Attack = 1152
    BigBadaBoom = 1153
    BossAdjutant_Old = 1154
    DefenderOfTheGreaterGood = 1155
    Split = 1156
    TimeFlux = 1157
    AllIsDust = 1158
    SavageKiller = 1159
    FlamesOfMutation = 1160
    WeaverOfFate = 1161
    HuntersBeyondDeath = 1162
    LionHelm = 1163
    HostOfPlagues = 1164
    RevoltinglyResilient = 1165
    TheWrathfulDead = 1166
    TheLantern_Attack = 1167
    ArchContaminator = 1168
    TheWrathfulDead_Overkill = 1169
    InfernalPacts = 1170
    AnvilShield = 1171
    BattleFocus = 1172
    MasterOfTheTutelaries_Summon = 1173
    RealityUnbound = 1174
    ArcaneShield = 1175
    GrimRetribution = 1177
    Doombolt_Reset = 1178
    PsychicStalk = 1179
    SorcerousFacade_Switch = 1180
    GuardianOrganism = 1181
    SagaOfTheWarriorBorn = 1182
    Neuroparasite = 1183
    Conceal = 1184
    EnvThinVeil = 1185
    CrushingStrike = 1186
    HarlequinsPanoply = 1187
    RapidAssault = 1188
    AdrenalSurge = 1189
    BlisteringAssault = 1190
    HyperAggression = 1191
    SynapticLinchpin = 1192
    SynapticInsight = 1193
    LordOfTempests = 1194
    VulnerableToMelee = 1195
    VulnerableToFlameAndBlast = 1196
    FeederTendrils = 1197
    MasterAnnihilator = 1198
    GalvanicField = 1199
    ControlEdict = 1200
    DoctrinaImperatives_SetStart = 1201
    RadSaturation = 1202
    OnToxicDamageAbility = 1203
    BarbedOvipositor = 1204
    OptimizedGait = 1205
    AblativePlating = 1206
    WeakerRearArmour = 1207
    ArmouredMight = 1208
    PoundThemToDust_Attack = 1209
    GunnersKillOnSight_Attack = 1210
    OnOnMeltaDamageAbility = 1211
    Reinforcements = 1212
    FieldsOfFire = 1213
    WrathfulDevotion = 1214
    UNUSED_2 = 1215
    BlessingsOfKhorne = 1216
    Skullsmasher = 1217
    TheBetrayer = 1218
    EchoesFromTheWarp = 1219
    Wraithcannon = 1220
    MoltenForm = 1221
    TheBloodyHanded = 1222
    BloodRunsAngerRisesWarCalls = 1223
    TheWailingDoomSweeps_DelayedAttack = 1224
    TheWailingDoomStrikes_DelayedAttack = 1225
    TheWildHost = 1226
    Phantasm = 1227
    TheWrathOfKhaineUnleashed_Attack = 1228
    TrophyTaker = 1229
    EnvArtillerySupport = 1230
    EnvFlakFire = 1231
    EnvDefenderHealthBuff = 1232
    HeavyGravCannon = 1233
    GetStuckIn = 1234
    FearedInterrogator = 1235
    BeaconOfRage = 1236
    OverwhelmingWrath_Attack = 1237
    BossAdjutant = 1238
    MalleusRocketLauncher_Attack = 1239
    EnvGarrison = 1240
    EnvArmourSupplies = 1241
    EnvFortified = 1242
    FloatingDeath = 1243
    DaemonicOrdnance_Crit = 1244
    Deathwing = 1245
    SmashaEad = 1246
    FuryOfTheAncients = 1247
    AggressiveOnslaught = 1248
    RedThirst = 1249
    TacticalPrecision_Reset = 1250
    FuelledByFury = 1251
    GazeOfMagnus = 1252
    PsychicDominion = 1253
    ImpossibleForm = 1254
    GazeOfMagnus_Attack = 1255
    AncientFury = 1256
    MacroPlasmaIncinerator_Attack = 1257
    HammerOfWrath_ConditionalDamage = 1258
    UnbridledCarnageReworked = 1259
    HeavyRailRifle_Attack = 1260
    BigBadaBoomReworked = 1261
    IllusionsOfTzeentch = 1262
    ScreamerInvocation = 1263
    VisionsOfHeresy = 1264
    BlackRage_Activation = 1265
    PowerUp_Reinforcement = 1266
    EnvValkyrieStrike = 1267
    EnvAngelsOfDeath = 1268
    PowerUp_ReinforcementShield = 1269
    EnvReinforcementShield = 1270
    Ambush = 1271
    PowerUp_ReactivateAbility = 1272
    PowerUp_Healing = 1273
    EnvAmbushResurrect = 1274
    SpiritualLeader = 1275
    EnvSurvivalStatBoost = 1276
    CosmicHorror = 1277
    TwistedScience = 1278
    Hypermorph = 1279
    EnvStartProtection = 1280
    EnvEndBombardment = 1281
    PowerUp_Bomb = 1282
    DaRevolushun = 1283
    PowerTrip = 1285
    EnvDefenderHealthBuff2 = 1287
    EnvAttemptDebuff = 1288
    Bounce = 1289
    ExplosivePresents_Cooldown = 1290
    SelfRepairMechanism = 1291
    Unused = 1292
    PreCalibratedPurgeSolution = 1293
    RadZoneCorps = 1294
    PriorityReclamation = 1295
    SanguinaryPriest = 1296
    SolarAtomizer_PendingAttack = 1297
    VengeanceForTheOmnissiah = 1298
    OmnissiahsBlessing = 1299
    CloudOfFlies = 1300
    LordOfTheHost = 1301
    VoltagheistField = 1302
    ElectroShock = 1303
    DecoysAndMisdirection = 1304
    HypersensoryAbilities = 1305
    EnvSquigSmash = 1306
    HeroicFusillade_Reset = 1307
    StandVigil = 1308
    EnhancementLifeSteal = 1309
    LegendaryCommander = 1310
    MomentShackle_Attack = 1311
    EnhancementHitBoost = 1312
    EnhancementSummonHarlequin = 1313
    EnmityForTheUnworthy = 1314
    DevastatingRefrain_Attack = 1315
    CalibaniteGreatsword_NormalAttackAdditionalDamage = 1316
    EnvFactionSummons = 1317
    UNUSED_1 = 1318
    LegacyOfCombat = 1319
    PowerUp_Resurrect = 1320
    MultiTracker = 1321
    TargetLock = 1322
    NovaBoost_Attack = 1323
    NovaCharge_Attack = 1324
    NovaShield_Attack = 1325
    EnvCapturePointShield = 1326
    ATemptingTrap = 1327
    PinpointCounterOffensive = 1328
    DaughterOfTheAbyss = 1329
    TalonsOfTheEmperor_UsedAbilities = 1330
    EnvAllyAndEnemyNpcs = 1431
    ArmourOfShriekingSouls = 1432
    EnhancementRegeneration = 1433
    PowerUp_HeroSpawn = 1434
    TerrifyingCrescendo = 1435
    PowerUp_HeroSpawn_VexilusPraetor = 1436
    PowerUp_HeroSpawn_BladeChampion = 1437
    EmbodiedProphecy = 1438
    NovaShield_BlockVisual = 1439
    EnhancementSummonHavoc = 1440
    RefusalToBeOutdone = 1441
    EnhancementAddTrait = 1442
    ObsessiveAnnunciation = 1443
    ThrillSeekers = 1444
    EnhancementSummon = 1445
    Decoy = 1446
    BlightedLand = 1447
    HuntersInstincts = 1448
    UnwaveringSentinel = 1449
    ContemptuousDisregard = 1450
    WisdomOfTheAncients = 1451
    OnMyPosition = 1452
    ShieldOfFaith = 1453
    ElectrochaffBackups = 1454
    HyperCorrosiveAcid = 1455
    MoreGitzOverEre = 1456
    KardiocoreGalvanus = 1457
    PhoenixGem = 1458
    RelicOfLostCadia = 1459
    TalismanOfRage = 1460
    BookOfFate = 1461
    NetherRealmCasket = 1462
    IntoxicatingElixir = 1463
    AmuletOfTheVoidwyrm = 1464
    OrbsOfDecay = 1465
    RelicPowerFist = 1466
    RelicBoltPistol = 1467
    TheArdentBlade = 1468
    MawClawsOfThyrax = 1469
    Vitarus = 1470
    MischiefMakers = 1471
    EcstaticSlaughter = 1472
    DaemonicPatrons_Finale = 1473
    SelfRepairMechanismReworked = 1474
    SupaCyborkBody = 1475
    Dw02AdvancedBurstCannon = 1476
    ToughToKill = 1477
    SabreOfSacrifice = 1478
    Drachnyen_Attack = 1479
    EnhancementDamageBoost = 1480
    FragLance = 1481
    LetTheGalaxyBurn = 1482
    EnvDespoiledGroundTileDamage = 1483
    TalonOfHorus = 1484
    Drachnyen_ExtraAttack = 1485
    PrioritisedEfficiency = 1486
    EcogSupport = 1487
    VolummsMasterArtifice = 1488
    AncestralFortune_Reset = 1489
    GrimEfficiency = 1490
    BladeOfTheAncestors = 1491
    BossEndFightUndefeated = 1492
    DaemonfleshPlate = 1493
    ParagonSpear = 1494
    NornCrown = 1495
    CabalOfSorcerers = 1496
    HunterOfSouls = 1497
    Maugetar = 1498
    CrazedFocus = 1499
    WayOfTheShortBlade = 1500
    DawnBlade = 1501
    HealingBalms = 1502
    SpotterReworked = 1503
    WyrdmakersHelm = 1504
    EnhancementPierceBoost = 1505
    EnvStatBoost = 1506
    Hailstrike_Attack = 1507
    MastersOfManoeuvre = 1508
    UNUSED_5 = 1509
    DeathwingKnight = 1510
    PrimarchOfTheFirstLegion = 1511
    Fealty = 1512
    TheEmperorsShield = 1513
    RepairEnthusiast = 1514
    BloodRunsAngerRisesWarCallsReworked = 1515
    TheWrathOfKhaineUnleashedRework_Attack = 1516
    PowerUp_HeroSpawn_Uthar = 1517
    BeastSlayer = 1518
    InstrumentsOfVengeance_PendingAttack = 1519
    TheLionsWrath_PendingAttack = 1520
    HuntTheFallen = 1521
    RedemptionOfTheRisen = 1522
    NoHidingFromTheWatchers = 1523
    WatchedOver = 1524
    PredictiveGuidance = 1525
    PurgeResponse = 1526
    MonsterSlayerOfCaliban = 1527
    FuryFromTheDelve = 1528
    # #304 -- membre AJOUTE par le build `rnca9r7q6c` (passif de `votanChampion`/Kimm). Sans lui,
    # `triggered_ability_ids('votanChampion')` rendait `[]` et le dispatcher
    # `TriggeredAbilitiesUtility(2)` restait MUET pour ce porteur, quel que soit le playbook porte.
    # C'est LE symptome type d'un membre manquant, et la raison du cliquet #313.
    ModifiedExoarmour = 1529
    GuardianConstruct = 1530
    HaywireMine = 1531
    PowerUp_SummonSpawn = 1532
    PowerUp_SummonSpawn_ultraSmnInceptor = 1533
    TimesplinterMantle = 1534
    EnvStrategicBuff = 1535
    PowerUp_SummonSpawn_ultraSmnHeavyIntercessor = 1536
    PowerUp_SummonSpawn_bloodSmnIntercessor = 1537
    PowerUp_SummonSpawn_darkaSmnHellblaster = 1538
    PowerUp_SummonSpawn_darkaSmnTerminator = 1539
    PowerUp_SummonSpawn_templSmnAggressor = 1540
    Lakrimae = 1541
    HaywireMineSteppable = 1542
    PropheticSentinel = 1543
    EnhancementCritBoost = 1544
    # 1545/1548/1551 : les placeholders `DA_Hero6_*` de l'ancien `data/il2cpp_enums.tsv` etaient
    # deja perimes sur `gqfc5mff6c` (ce sont les abilities de Ramus darkaSternguard ; 1551
    # RedRampage = passif de Cezare bloodTerminator). Corriges par le RPC live `dumpEnum` en
    # 2026-07-23 (case-219), et depuis CONFIRMES par la table versionnee `enums.tsv`. Le meme
    # placeholder survit d'ailleurs encore dans `engine/entities/effect_type.py` (1563/1564).
    SpecialIssueCombiMelta = 1545
    HeavyWarpFlamer_AttackTrackingAbility = 1546
    KustomForceFieldReworked = 1547
    SternguardFocus_Cooldown = 1548
    HeadwoppasKillchoppa = 1549
    ChaliceOfBaal = 1550
    RedRampage = 1551
    IconOfObstinacy = 1552
    WhisperingWeb = 1554
    EmpyricAmbush_Reset = 1555
    MyWillBeDoneOverlord = 1556
    PhasalSubjugator = 1557
    Helspear = 1558
    TestBlank = 9001
    TestMachineOfWar = 9002
    TestRetaliateOnRandomAdjacentUnit = 9004
    testRelicAbility = 9005
    testAssetBundles = 9999


def triggered_ability_ids(visual_id: str | None) -> list[int]:
    """Ids `TriggeredAbilityType` du KIT PASSIF d'une unité (gameconfig `passiveAbilities` -> enum).

    Source OFFLINE du dispatcher `TriggeredAbilitiesUtility(2)` (le natif lit l'AbilitiesComponent
    ECS de l'unité qui bouge, `IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext` — cf. case-36). Les abilities DÉCLENCHÉES du jeu sont les
    `passiveAbilities` du gameconfig (namespace natif `Abilities.Triggered.Loki.*Ability`).
    [] si unité inconnue ou passif hors enum."""
    if not visual_id:
        return []
    import gameconfig as GC
    out: list[int] = []
    for a in (GC.unit_abilities(visual_id).get("passive") or []):
        m = TriggeredAbilityType.__members__.get(a.get("name") or "")
        if m is not None:
            out.append(int(m))
    return out


# Abilities déclenchées ACCORDÉES PAR TRAIT (l'AbilityFactory native peuple l'AbilitiesComponent
# depuis les traits, pas seulement les `passiveAbilities` gameconfig — mirror AI du registre runner
# `BEHAVIOUR_TRAIT_TRIGGERS` de `runner/operations/triggers/dispatch.py`, même source de vérité).
# Ex. u89 spaceStormcaller : unitAbilityStates raw = {1194, 1013, 1142} alors que passiveAbilities
# gameconfig = [LordOfTempests] seul — 1013 vient du trait Psyker, 1142 du trait TerminatorArmour.
TRAIT_TRIGGERED_ABILITY_IDS: dict[str, tuple[int, ...]] = {
    "Psyker": (int(TriggeredAbilityType.PsykerExtraAttack),),        # 1013 (splash Smite)
    "TerminatorArmour": (int(TriggeredAbilityType.TerminatorArmour),),   # 1142 (réduction dégât)
    # DEATH-NOVA — mappings du registre natif `StaticBattleRules.Trait$$.idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor, lu par
    # `Trait$$idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetTriggeredAbility et matérialisé par `AddTraitOperation$$AddDerivedAbilities`
    # IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities : trait `Explodes` (UnitTrait 1008) -> 1021, trait `PutridExplosion` (UnitTrait 2028) -> 1074.
    # ⚠ MESURE d'inertie (vérifiée) : `PlaybookDatabase.LoadPlaybook` n'a AUCUN playbook pour 1021/1074 (aucun
    # symbole `Explodes*Playbook`/`PutridExplosion*Playbook` dans le binaire) -> le dispatcher natif
    # `TriggeredAbilitiesUtility` SKIPPE ces ids (`if (playbook == null) continue`). L'ajout ici est donc le
    # mirror FIDÈLE du contenu de l'AbilitiesComponent (et le socle de tout futur consommateur), mais reste
    # OBSERVABLEMENT INERTE côté utilité — comme dans le jeu.
    "Explodes": (int(TriggeredAbilityType.Explodes),),                     # 1021 (nova de mort)
    "PutridExplosion": (int(TriggeredAbilityType.PutridExplosion_Ability),),  # 1074 (nova de mort Toxic)
    # #415 — `SuppressiveFire` (UnitTrait 1010) -> triggered 1044, MEME mapping que le registre
    # runner `BEHAVIOUR_TRAIT_TRIGGERS["SuppressiveFire"]` (#74) : une source de verite, deux faces.
    # Son playbook ATTACK existe (`SuppressiveFirePlaybook`, registre `psyker.TRIGGERED_ATTACK_PLAYBOOKS`)
    # -> contrairement a Explodes/PutridExplosion, cette entree N'EST PAS inerte : sans elle le
    # dispatcher n'itere jamais 1044 et le +35 `SUPPRESSIVEFIRE_TargetWithOverwatch` manque au
    # `pairUtility` de tout porteur du trait (49 unites). Mesure : #415, ecart de 35 exactement.
    "SuppressiveFire": (int(TriggeredAbilityType.SuppressiveFire),),       # 1044 (bonus de TIR)
    # #1015-r1 -- `CloseCombatWeakness` (UnitTrait 0x40b = 1035) -> triggered 0x46a = 1130, LU dans
    # le dict `GetTriggeredAbility` (+0x0) du `.cctor` de `StaticBattleRules.Trait`. Comme
    # `SuppressiveFire` et contrairement a `Explodes`/`PutridExplosion`, cette entree n'est PAS
    # inerte : son playbook MOVE existe (`CloseCombatWeaknessPlaybook`, registre
    # `adjacent_unit_preference.TRIGGERED_MOVE_PLAYBOOKS`) et vaut **-40 par ennemi adjacent** a la
    # tuile visee -- sans elle le dispatcher n'itere jamais 1130 et le porteur ne fuit pas le contact.
    # Sa face ATTAQUE, elle, est une CONSTANTE ZERO cote natif (cf. `playbook/close_combat_weakness.py`).
    "CloseCombatWeakness": (int(TriggeredAbilityType.CloseCombatWeakness),),   # 1130 (fuite du contact)
}


def entity_triggered_ability_ids(unit_ctx, visual_id: str | None = None) -> list[int]:
    """IDS du kit DECLENCHE d'une ENTITE -- le substrat COMPLET que le dispatcher d'utilite itere,
    cote port. FOYER UNIQUE : c'est la version ENTITE de `triggered_ability_ids`, exactement comme
    `entity_trait_ids` est la version entite d'`unit_trait_ids` (#225).

    `unit_ctx` = le `UnitContext` de l'entite (`StatsComponent.ctx` cote runner, `Scene.ctx(uid)`
    cote prediction : c'est le MEME objet, cf. `Scene.from_state`). Son champ `triggered_abilities`
    est l'image du `TriggeredAbilityComponent` -- ce que
    `IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`
    enumere reellement (`case.unit@+0x10` -> GetComponent -> `+0x18` -> `GetEnumerator`).

    TRI-ETAT, et le REMPLACEMENT est DELIBERE (#304, meme arbitrage cote DECISION) :
      * `triggered_abilities is None` -> canal NON MESURE : repli sur le kit gameconfig
        `triggered_ability_ids(visual_id)`, comportement strictement d'avant #456-r1 ;
      * une LISTE -> MESURE, et elle FAIT AUTORITE. Une UNION serait fausse dans le sens qui compte :
        elle ne peut qu'AJOUTER, donc elle REINTRODUIRAIT un passif que la bataille n'a PAS monte.
        Mesure #456-r1 (`MC1_67`/777, greffe `tauCrisis:SaviorProtocols`) : natif `[1120, 1030]`,
        gameconfig `[1133]`, union `[1133, 1120, 1030]` -- l'union fait iterer `1133`, que
        l'`AbilitiesComponent` ne contient pas.

    `unit_ctx is None` -> borne STATIQUE `triggered_ability_ids(visual_id)`, comme
    `entity_trait_ids`. Ce n'est pas une verite : relique, greffe et abilities derivees d'un trait y
    sont invisibles.

    ⚠ NON CACHE : le champ est MUTABLE (deux entites de meme `visualId` n'ont pas forcement le meme
    kit des qu'une greffe, une relique ou un `AddTrait` est en jeu)."""
    if unit_ctx is not None:
        got = getattr(unit_ctx, "triggered_abilities", None)
        if got is not None:
            return [int(x) for x in got]
        if visual_id is None:
            visual_id = getattr(unit_ctx, "visual_id", None)
    return triggered_ability_ids(visual_id)


def kit_triggered_ability_ids(visual_id: str | None) -> list[int]:
    """Kit déclenché COMPLET d'une unité = passifs gameconfig (`triggered_ability_ids`) + abilities
    accordées par TRAIT (`TRAIT_TRIGGERED_ABILITY_IDS`) — le miroir fidèle de l'AbilitiesComponent
    ECS qu'itèrent les dispatchers `TriggeredAbilitiesUtility(2)` (faces move IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext ET attack
    IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateAttackInStepsInternalu003Ed__3$$MoveNext). La face move historique (case-36) lit encore `triggered_ability_ids` seul —
    sans impact (aucun trait-granted n'a de playbook move enregistré)."""
    out = list(triggered_ability_ids(visual_id))
    if visual_id:
        import gameconfig as GC
        for tr in ((GC.unit(visual_id) or {}).get("traits") or []):
            out.extend(TRAIT_TRIGGERED_ABILITY_IDS.get(tr, ()))
    return out
