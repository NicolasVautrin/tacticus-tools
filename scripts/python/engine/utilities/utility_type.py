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

BIJECTION COMPLETE ET GARDEE (#318) : les 83 membres du natif sont la (68 -> 83 ; la queue
68-81 + `STRIPPED = 9999`), et `tests/test_enum_mirror_ratchet_offline.py` exige desormais les
DEUX sens contre le build courant. La doctrine « ajouter au fil des call-sites » ne tenait pas
ici : c'est justement le sens MANQUANT qui degrade en silence (une cle numerique rendue par le
RPC `dumpComposedUtility` que le port ne sait pas nommer est jetee, pas signalee). La table
entiere se regenere par `python scripts/python/regen_enum_mirrors.py --mirror UtilityType
--ecrire` depuis `data/symbols/<build>/frida/enums.tsv` — ne jamais transcrire a la main.

Les 15 membres ajoutes en #318 ne sont adosses a AUCUNE feuille portee : ce sont des NOMS
corrects, pas des utilites implementees. Porter une feuille reste un travail a part entiere
(lire son `IdunBattle.AI.Utilities.<X>Utility$$.ctor` et son `EvaluateMovementInSteps`)."""
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
    ActiveAbilities = 68
    PreferNonBoss = 69
    PreferFreshlySpawned = 70
    MinPossibleNormalAttackTarget = 71
    UnitWithShortestPathToEnemy = 72
    Remaining = 73
    PreferAbilities = 74
    PreferSummons = 75
    LastAbilities = 76
    UnitOrder = 77
    Random = 78
    AdjacentHarmonizedFriend = 79
    PsychicFortress = 80
    NoMovementToTileWithAdjacentEnemies = 81
    STRIPPED = 9999
