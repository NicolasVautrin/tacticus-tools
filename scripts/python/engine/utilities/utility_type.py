"""`UtilityType` — enum natif des utilites d'IA (`IdunBattle.Configuration.UtilityType`).

Mirror 1:1 des valeurs natives. Sert de cle a `UtilitiesDatabase` (GetUtility) et d'argument a
`GetMovementUtility`. Les COMPOSITES (Tile=7, Damage=35, UnitMovement=6, …) sont des instances
`ComposedUtility` enregistrees a ces valeurs — PAS des classes dediees.

⚠ RENUMEROTE PAR LA MAJ `gqfc5mff6c` -> `rnca9r7q6c` (2026-07-29, cf. tache #252).
Le jeu a INSERE `AttackTile` en 8 : les 59 membres suivants ont TOUS pris +1
(`Elevation` 8->9, `TileEffects` 9->10, `SteppableUnit` 19->20,
`DecoysAndMisdirection_AttractToDecoys` 64->65…). Les 8 premiers (0-7) sont intacts.

**CES VALEURS TRAVERSENT LA FRONTIERE AVEC LE JEU** — ce ne sont pas de simples etiquettes
internes : la membership exacte des composites est LUE A L'EXECUTION via le RPC
`dumpComposedUtility` (`UtilitiesDatabase.InitializeUtilities._composedUtilityLookup`), qui
rend des cles NUMERIQUES du build courant. Un decalage ici fait donc nommer chaque feuille
avec le libelle de sa VOISINE, silencieusement. C'est pour ca que ce module doit etre
re-derive de `data/symbols/<build>/frida/enums.tsv` a CHAQUE changement de build, et jamais
recopie a la main.

Verifie au portage (2026-07-29) : les 67 noms du port existent tous dans la table native du
nouveau build — AUCUN renommage local a preserver. Confrontation faite nom par nom, pas par
position.

GAP CONNU, PRE-EXISTANT (non elargi ici) : le natif compte 83 membres, ce mirror en declare
68. La queue 68-81 (`ActiveAbilities`, `PreferNonBoss`, `PreferFreshlySpawned`,
`MinPossibleNormalAttackTarget`, `UnitWithShortestPathToEnemy`, `Remaining`,
`PreferAbilities`, `PreferSummons`, `LastAbilities`, `UnitOrder`, `Random`,
`AdjacentHarmonizedFriend`, `PsychicFortress`, `NoMovementToTileWithAdjacentEnemies`) et
`STRIPPED = 9999` n'ont jamais ete transcrites — doctrine « ajouter au fil des call-sites,
jamais deviner ». Les ajouter quand un call-site les exige, en relisant le natif."""
from __future__ import annotations

from enum import IntEnum


class UtilityType(IntEnum):
    # --- 0-7 : INCHANGES par la MAJ (sous le point d'insertion) ---
    Spawn = 0
    SingleAdjacency = 1
    TriggeredAbilities = 2
    UnitSpecificBehaviours = 3
    TriggeredAbilitiesNonOwner = 4
    UnitMovementFromTemporary = 5
    UnitMovement = 6
    Tile = 7
    # --- 8 : INSERE par la MAJ rnca9r7q6c — c'est lui qui decale tout ce qui suit ---
    AttackTile = 8
    # --- 9+ : tous decales de +1 par rapport a gqfc5mff6c ---
    Elevation = 9
    TileEffects = 10
    UnitEffectsAdjacent = 11
    UnitEffectsSurrounding = 12
    UnitEffectsRanged = 13
    TemporaryTile = 14
    TilePendingBlockableSummon = 15
    RangedAdjacentEnemy = 16
    MinDistanceToClosestEnemy = 17
    MaxDistanceToUnitTile = 18
    MaxDistanceToEnemies = 19
    SteppableUnit = 20
    KustomForceField = 21
    DefenderOfTheGreaterGood = 22
    SaviorProtocols = 23
    MoltenForm = 24
    CapturePoint = 25
    Contaminated = 26
    PowerUp = 27
    DislikeStartingTilesUtility = 28   # nom natif de la CONSTANTE d'enum (le meme que la classe)
    DespoiledGround = 29
    SummonDislikeDoorOpening = 30
    HeroLikeDoorOpening = 31
    EnvEndBombardment = 32
    MovementSuggestion = 33
    TileDistance = 34
    Damage = 35
    DamageDealt = 36
    KillUnit = 37
    OverkillUnit = 38
    DislikeObjects = 39
    DislikeEnvironmentUnits = 40
    OnlyImperviousUnitIfCanBeDamaged = 41
    EnemyOnTerritoryTile = 42
    AttackTargetWithEffect = 43
    DislikeBoss = 44
    Heal = 45
    AddedTileEffects = 46
    Repair = 47
    RepairedAmount = 48
    DanceOfDaggers = 49
    AdjacentQuickSlash = 50
    RoyalGuard_AvoidAdjacentEnemies = 51
    SwornProtector_AvoidAdjacentEnemies = 52
    DevoutPush_AdjacentRangedEnemies = 53
    RammingSpeed_MostAdjacentEnemies = 54
    WireweaveNet_FirstAttack = 55
    MV71SniperDroneSquad_ClosestToParent = 56
    EarlyWarningOverride_SpawnSummon = 57
    DoctrinaImperatives_AttractMechanicals = 58
    EchoesFromTheWarp_FriendliesAvoidGhost = 59
    OptimizedGait_AdjacentFriends = 60
    Phantasm_AvoidFriendlyPhantasm = 61
    BioMinefield_MoveTowardsTarget = 62
    MasterOfTheTutelaries_MoveTowardsTarget = 63
    HypersensoryAbilities_BonusForFirstAttack = 64
    DecoysAndMisdirection_AttractToDecoys = 65
    TheArdentBlade_Geminae = 66
    LeadingTheCharge_ChargeTile = 67
