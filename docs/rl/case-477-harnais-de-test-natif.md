# #477 — Le harnais de test des devs (`idun.tests.AbilityAnimationTest`) : ce qu'il est, ce qu'il n'est pas

**Build mesuré** : `rnca9r7q6c`. Enquête offline (décompilé + tables de symboles + assets du build).
Aucun reinject, aucun runner monté.

## Verdict en une ligne

`AbilityAnimationTest` est un **lanceur d'animations piloté par la vue, SANS aucun oracle** —
l'hypothèse de départ est **CONFIRMÉE**. Sa configuration externe est **vivante en code, morte en
données**. Mais l'enquête a trouvé **l'oracle ailleurs, et il est vivant** :
`Runner.ReplayValidator`, dont le canal de comparaison —
`IdunBattleLogic.Replay.Replay$$GetWholeBattleOutputStream` — est **déjà disponible sur nos propres
runners**.

---

## 1. La configuration externe — vivante en code, MORTE en données

### Ce que fait le code

`idun.tests.AbilityAnimationTest$$HasExternalTestConfiguration` teste le champ `+0x370` par
`UnityEngine.Object$$op_Inequality`. `AbilityAnimationTest$$AwakeAfterStartup` en dérive la config
effective, stockée en `+0x390` :

```
cfg = (this+0x370 != null)
        ? ( (this+0x370)+0x20 != null ? ((this+0x370)+0x20)+0x18 : (this+0x370)+0x28 )
        : this+0x380            // config inline
this+0x390 = cfg
if (TryGetReplayFromTestConfiguration() == null) SetupBattleConfig()
```

`idun.tests.AbilityAnimationTest$$TryGetReplayFromTestConfiguration` lit **`cfg+0x10`**, une
`System.String`, la passe à `Snowprint.Core.Extensions.StringExtension$$IsNullOrEmpty` puis à
`thor.Scripts.Idun.Source.IdunBattle.ReplaySerialization.ReplaySerializer$$DeserializeReplay`.

### D'où vient la configuration : mesuré, pas déduit

| Question du brief | Réponse mesurée |
|---|---|
| Fichier / chemin ? | **Non** — aucune I/O dans la chaîne |
| Clé de préférences ? | **Non** |
| Argument de ligne de commande ? | **Non** |
| Objet Unity sérialisé ? | **OUI** |

`data/symbols/rnca9r7q6c/frida/classes.tsv` :

```
idun.tests.abilities.configuration.ExternalAbilityTestConfiguration        48   UnityEngine.MonoBehaviour
idun.tests.abilities.configuration.ExternalAbilityTestConfigurationObject  32   UnityEngine.ScriptableObject
```

⇒ le champ ne peut être peuplé que par la **sérialisation Unity** d'une scène, d'un prefab ou d'un
asset. **Il n'existe aucun chemin runtime pour l'alimenter.**

### Le FORMAT, lui, est entièrement connu

C'est celui de `ReplaySerializer$$DeserializeReplay`, qui accepte **trois formes** :

1. **JSON brut** — après `Trim()`, `StartsWith('{')` ;
2. **base64(gzip(JSON))** — `Convert.FromBase64String` puis
   `Snowprint.source.Core.Zip.ZipUtil$$GzipDecompress` ;
3. **base64 SEGMENTÉ** — si la chaîne contient `'='` en milieu, passage par
   `ReplaySerializer$$TryDecompressJsonFromFirstBase64GzipSegment`, qui balaie par pas de 4
   caractères jusqu'à trouver un segment dont le gunzip commence par `{`.

Un préfixe constant est strippé en tête (`StartsWith(<const>)` → `Replace(<const>, "")`).
L'écriture symétrique est `ReplaySerializer$$SerializeReplay` :
`Replay.ShallowClone` → `ReplayDto..ctor` → `Json.SerializeObject` → `GzipCompress` → `ToBase64String`.

### Pourquoi c'est mort dans le build livré — la mesure qui tranche

Le `BuildSettings` de `Tacticus_Data/globalgamemanagers` ne contient que **deux** scènes :

```
Assets/Scenes/SplashBackground.unity
Assets/Scenes/Empty.unity
```

et `Tacticus_Data/` ne porte que `level0` (1 984 o) et `level1` (1 436 o). **Aucune scène de test
n'est buildée.** `AbilityAnimationTest` étant un `MonoBehaviour` (parent `BaseTest`, lui-même
`UnityEngine.MonoBehaviour`), **aucune instance n'existe jamais** dans le jeu livré — donc ni
`Awake`, ni `AwakeAfterStartup`, ni `HasExternalTestConfiguration` ne s'exécutent.

⚠ **Contre-mesure à ne pas mal lire** : les noms `AbilityAnimationTest`,
`ExternalAbilityTestConfigurationObject`, `ability_camo_cloak_test` **apparaissent** dans
`globalgamemanagers.assets`. Ce fichier porte la table des **`MonoScript`** (déclaration des
scripts), pas leurs instances — la preuve étant qu'il liste précisément les classes dont on vient
d'établir que la scène est absente. **Cette présence ne prouve rien** et ne doit pas être citée
comme atteignabilité.

---

## 2. L'API de montage — deux étages, dont UN SEUL est le chemin de prod

### 2a. Étage CONFIG — fidèle, et c'est déjà notre étage

`SetupBattleConfig`, `AddPredefinedUnits`, `GetAddUnitMessageForPredefinedUnit`,
`GetPlaceholderConfigForSummon`, `AddMissingStatsToUnitConfig`, `AddAbilityConfiguration`,
`AddOrUpdateAbilityConfiguration`, `AddUtilities`, `MakeWeaponProfile`, `GetDamageProfile`
écrivent un `IdunBattle.Configuration.BattleConfiguration` **en mémoire, avant que la bataille
existe**.

`AbilityAnimationTest$$SetupBattleConfig` part de `idun.Tests.Helpers.SampleBattle$$Get`, mute des
champs du BC, puis appelle une fonction de **prod** :
`Idun.Source.IdunBattle.View.BattleConfigBuilder$$AddDamageProfiles`. Ensuite
`AbilityAnimationTest$$MainViewInitializationSetup` construit un
`IdunBattle.ViewLogic.BattleSource.TestSceneBattleModeSource`, qui implémente **`IGameModeSource`** —
la même interface que `CampaignGameModeSource` / `PvpGameModeSource`.

⇒ **le harnais ne fabrique pas une bataille parallèle : il se substitue au fournisseur de BC, et tout
le pipeline aval est celui de prod.**

**Aucun appel direct à `IdunBattle.Entities.Factories.UnitFactory`** depuis le harnais : le chaînage
vers la fabrique se fait en aval, par le conduit de prod.

Réponse à la question posée : ces méthodes entrent **au même étage que nous**. Nous patchons
`BattleConfiguration.Units[]`, le harnais écrit `bc+0x80` — même objet, même moment (avant
`IdunRunner.Initialize`). **Il n'y a rien de plus fidèle à gagner là** ; le harnais fait même *moins*
que nous (il re-clampe Health ≥ 50 / Damage ≥ 5 à la main).

### 2b. Étage ENTITÉ — à NE PAS copier

`SetUnitStat` / `SetUnitArmor` / `SetUnitAttack` / `SetUnitMaxHealth` / `SetUnitHealth`,
`AddTraitToUnit`, `RemoveTraitFromUnit` écrivent **directement dans les composants ECS d'une entité
vivante**, en court-circuitant les `Operation` : `ArmorComponent+0x18`, `AttackComponent+0x48`,
composant santé `+0x10`/`+0x18`, `Add/Remove` sur la collection de traits en `+0x40`.

Là où la prod passe par `IdunBattle.Operations.SetupGameOperation$$ModifyUnitAttack` /
`ModifyUnitHp` / `ModifyUnitFixedArmor` … — qui **retournent de vrais
`IdunBattleLogic.Battle.StatModifier`** — le harnais écrit le scalaire brut.

**Preuve qu'aucun event n'est émis** : `SetUnitArmor`, `SetUnitAttack` et `SetUnitHealth` doivent
**rafraîchir la vue à la main** (`IdunBattle.View.Game.IdunGameViews$$GetUnitView` puis
`idun.Game.Board.AUnitView$$UpdateStats`). Si le stream émettait, ce rattrapage serait inutile.
(`SetUnitMaxHealth` ne le fait même pas — divergence assumée dans le natif.)

⚠ Reproduire ces mutateurs côté moteur créerait exactement la divergence silencieuse qu'on chasse :
stat écrite **sans `StatModifier`**, donc invisible de `statModSources`, et **sans event de stream**.
`SetUnitStat` ne couvre d'ailleurs que 2 `StatType` (0 → attack, 5 → health) et **lève** sur tout
autre.

### 2c. Les deux leviers de montage du `BattleConfiguration` — RÉSOLUS (#477-r5 / #477-r6)

**La disposition est MESURÉE en live** (RPC `classFields`, build `rnca9r7q6c`), pas déduite d'un
offset : `BattleConfiguration` = 35 champs d'instance, taille boxée 240. Les deux champs visés sont
`UnitModifiers` **@0x50** (`Dictionary<string, List<UnitModifier>>`) et `StartingActions` **@0xc0**
(`List<...>`) — le second s'appelle `StartingActions`, pas « starting messages ».

#### `StartingActions` (@0xc0) — INATTEIGNABLE depuis le JSON, et c'est mesuré

Le champ existe et fait bien ce que la RE disait : `SetupGameOperation$$ExecuteStartingMessages` le
lit, empile ses éléments avec ceux dérivés du `SpawnPointSet`, enveloppe chacun dans un
`IdunBattle.Messages.StartingActionContainerMessage` et les pousse dans l'`IOperationProcessor`.
Il est appelé par `SetupGameOperation$$Execute`, **après** `AddPredefinedUnits` /
`AddPredefinedMachines` / `AddBossUnit`.

**Mais il n'est pas désérialisé.** Discriminant joué (`probe_477_bc_montage_leviers.py` étape 1) :
poser un **scalaire** là où le champ déclare une `List<T>`.

| champ posé à `42` | résultat |
|---|---|
| `StartingActions` | build **silencieux**, rc 0 |
| `AbilitiesToHide` (témoin, `List<T>` réellement désérialisée) | **`initAndStart: system error`** |

Le témoin est ce qui rend la mesure concluante : la désérialisation *sait* refuser un mauvais type,
donc le silence sur `StartingActions` n'est pas de la tolérance — le champ est **ignoré**. Notre
chaîne passant intégralement par `deserializeFromJson(configJson, BattleConfiguration)`
(`ctx.rpc.initAndStart`), **ce levier n'est pas pilotable sans écrire dans l'objet natif après
désérialisation** — donc sans un hook neuf, donc sans fenêtre de reinject. Résidu **#477-r9**.

**Ce n'est pas une perte fonctionnelle** : le besoin « placer une unité sur une tuile exacte » est
servi par la **même** voie native. `initAndStart` applique déjà, pour chaque entrée de
`playerUnits[]`, un `AddUnitMessage(unitId, playerId, col, row)` → `IdunRunner$$Apply` →
`IdunBattle.Operations.AddUnitOperation$$Execute`. `ExecuteStartingMessages` ne fait rien d'autre que
pousser des messages dans ce même processeur : le pipeline traversé est identique, seul le **moment**
diffère (pendant `SetupGameOperation` vs après `Initialize`). C'est cette voie qu'exposent
`rl_duel build --place` / `--a-place`.

#### `--place` / `--a-place` — placement à la tuile exacte, des DEUX côtés

`--place` écrase `col`/`row` de l'entrée `playerUnits` correspondante. `--a-place` **sort** l'unité
de `BC.PredefinedUnits` (que le natif place lui-même sur le `SpawnPointGroup` via
`AddPredefinedUnits`) pour la poser à la main avec `playerId = 12`.

**Le natif refuse par QUATRE gardes, toutes en RETOUR NUL SILENCIEUX** dans
`AddUnitOperation$$Execute` — ni exception, ni event vers l'appelant :
`AreTilesDisallowedAndLog` (tuile non marchable, ou `TileContentComponent$$IsFilled` sans
`HasSteppableUnit` — c'est la seule qui *log*, et le runner de test a un `NullLogger`),
`TilesAreReserved`, `TilesArePendingDrafting`, `TilesAreInFog`. D'où deux gardes côté harnais :

- **avant** le build, ce qui se tranche sur la config seule — hors board (`Board.Width/Height`),
  `Board.Tiles[col].Tile[row].ForceUnplayable`, deux unités sur la même tuile → refus rc 2, **aucun
  runner construit** (un refus découvert après laisserait un runner sur le cap partagé) ;
- **après** le build, `_verify_placements` relit `decisionView` et confronte la position obtenue,
  clé `(visualId, team)` — sans la team, un placement joueur refusé se lirait comme honoré par
  l'unité adverse homonyme. Écart → rc 3, *après* `_save_state` (sinon le runner serait orphelin).

#### `--unit-modifier` — `UnitModifiers` (@0x50), le point d'entrée NATIF des stats

`AddPredefinedUnits` fait `UnitModifiers.TryGetValue(GetUnitIdWithoutRarity(unitId))`, puis
`ApplyModifiers(unit, modifiers)` **sur l'entité déjà créée** ; `AddBossUnit` fait de même. C'est le
seul chemin de lecture pour une unité régulière ⇒ **le dictionnaire ne mord que sur les unités de
`BC.PredefinedUnits`**, c'est-à-dire, dans notre montage, le roster **adverse** — et pas sur une
unité sortie par `--a-place`. Les deux cas sont refusés en amont (rc 2), parce que l'échec natif est
muet.

Disposition de `IdunBattleLogic.Shared.UnitModifier` (48 boxé / 32 de champs, mesurée) :
`ModificationType`@0x10 (`0=Stat, 1=AbilityVariable, 2=AbilityConstant,
3=InitialSpawnAmountDecrease`), `Id`@0x18, `SubId`@0x20, `IsBuff`@0x28, `IsPercentage`@0x29,
`Amount`@0x2c. ⚠ **`IsBuff` et `IsPercentage` ne sont jamais lus** par `ApplyModifiers` : la nature
pourcentage/absolu est **câblée par `Id`** dans le natif.

Les **huit** `Id` que `ApplyModifiers` dispatche — littéraux du binaire, chacun **confronté en live**
(témoin vs modifié, mêmes unités, mêmes positions, board MC1_67, rank 17) :

| `Id` | méthode native | stat `combatSnapshot` | `Amount` | mesure témoin → modifié |
|---|---|---|---|---|
| `dmg` | `ModifyUnitAttack` | `attack` | POURCENTAGE | 2609 → 2348 (`Amount` 10) |
| `fixedArmor` | `ModifyUnitFixedArmor` | `fixedArmor` | POURCENTAGE | 3806 → 2501 (50) |
| `movement` | `ModifyUnitMovement` | `movement` | ABSOLU | 4 → 3 (1) |
| `hits` | `ModifyUnitHits` | `extraHits` | ABSOLU | 0 → −1 (1) |
| `hp` | `ModifyUnitHp` | `health` | POURCENTAGE | cf. ci-dessous |
| `blockChance` | `ModifyUnitBlockChance` | `blockChance` | ABSOLU | 50 → 40 (10) |
| `critDmg` | `ModifyUnitCritDamage` | `critDamage` | POURCENTAGE | 300 → 0 (100) |
| `critChance` | `ModifyUnitCritChance` | `critChance` | ABSOLU | 50 → 40 (10) |

POURCENTAGE passe par `SetupGameOperation$$CalculatePercentage` (Fix64, `Round` puis `Ceiling`) ;
ABSOLU vaut `StatComponent.CurrentValue − Amount`. **Tout autre `Id` tombe dans la branche de log de
`ApplyModifiers` et n'applique RIEN** — c'est le mode de panne principal, d'où le refus au parse
contre la liste fermée.

⚠ **Seul `fixedArmor` a une base native différente de la valeur affichée** : le natif lit un champ du
**composant** (`+0x48`) que `combatSnapshot` n'expose pas. Mesuré : affiché **3806**, base native
**2609** — le `StatModifier` posé vaut `total = −2349` pour `Amount = 90`, soit exactement
`−ceil(2609 × 90 %)`, et `residual = 0` (donc rien d'autre n'y contribue). Le probe exige de lui un
**écart** et un mod **négatif**, jamais une valeur prédite depuis l'affichage — la prédire serait
exactement la faute « ajuster un scalaire ».

**C'est un vrai `StatModifier`, et c'est mesuré par différence** — le point qui sépare ce levier de
`--unit-stat` (qui écrase un scalaire du template et ne laisse aucune trace) :

| bras (même unité, même seed, même board) | `statModSources.fixedArmor` | dégât infligé par `ultraTitus` |
|---|---|---|
| témoin | **aucun** | **1 963** |
| `--unit-modifier orksWarboss:fixedArmor:90` | `total −2349`, `bySource[0].source = 77` | **8 882** |

Le second montage combine les deux leviers : `--place ultraTitus:6,7` amène le mêlée au contact au
tour 1 (la géométrie de spawn ne le permettait pas), `--unit-modifier` retire l'armure. C'est
l'étape 3 de `probe_477_bc_montage_leviers.py`.

**Effet BINAIRE, seul attendu calculable sans témoin** :
`SetupGameOperation$$IsPredefinedUnitDisabledByModifiers` teste littéralement
`m.Id == "hp" && m.Amount > 99` (et, sur l'autre prédicat,
`m.ModificationType == InitialSpawnAmountDecrease && numAlreadyDisabled < m.Amount`) — l'unité
**n'est alors pas déployée du tout**. Mesuré : `orksKillaKan:hp:111` → présent au témoin, absent au
bras modifié. C'est aussi le premier discriminant qui a prouvé que le dictionnaire **arrive** au
natif, avant même de connaître les littéraux.

⚠ Le nom `GetAddUnitMessageForPredefinedUnit` dit vrai sur le **TYPE**, faux sur le **MOMENT** : ce
n'est pas envoyé à une bataille en cours.

⚠ **Indéterminé nommé** : le lien `<Visit>g__AddUnit|0` → `AddUnitOperation$$Execute` →
`UnitFactory$$Build` n'est **pas lu** (`UnitFactory$$Build` n'a aucune xref d'appel — invoqué par
vtable). Ce qui est prouvé : `Build` appelle `AddConfiguredAbilities`, et le harnais utilise les
**mêmes classes de message que la prod** (`IdunMainView$$AddUnitsFromPlaceholdersAndRunnerStartMatch`
construit littéralement les mêmes). Seule différence mesurée : la prod pose `AddUnitMessage+0x28 = 5`,
le harnais `1` — champ non lu par `InputMessageProcessor$$Visit`, sémantique non tranchée.

---

## 3. L'absence de machinerie d'assertion — confirmée, et sur quatre classes

Le brief demandait si `TestVisualBattleQuery`, `TestBattleStatisticQuery`, `TestVisualQuery`,
`AutomatedTestSuite`/`AutomatedTest`/`AutomatedTestStep` portent des valeurs attendues.

- `idun.tests.TestVisualBattleQuery` — **~80 méthodes, toutes des GETTERS** de requête
  (`GetAllPredictions`, `GetInvalidTargetReason`, `GetMovableTilesFor`, `GetValidTargets`,
  `GetZoneOfTerror`, `GetBestTileToAttackFrom`, …). Aucune comparaison, aucun `Expected`.
- `idun.tests.TestBattleStatisticQuery` — **~40 méthodes**, toutes des agrégats de fin de bataille
  (`GetTotalDamageDealtByUnitsAndMachines`, `GetMaxUnitsDefeatedInOneTurn`,
  `GetTotalBlocksMadeByUnitsAndMachines`, …). Des **compteurs**, pas des attendus.
- `AutomatedTestSuite` / `AutomatedTest` / `AutomatedTestStep` — **n'existent pas** sous ces noms.
  Ce qui existe est le namespace `Idun.Source.AutomatedTesting.*` : un générateur de
  `BattleConfiguration` pour tous les modes de jeu (`AutomaticTestingCampaignConfigFactory`,
  `AutomaticTestingPvpConfigFactory`, `AutomaticTestingSurvivalFactory`, …). Il **fabrique des
  entrées**, il ne vérifie aucune sortie.

⇒ **Ces quatre pistes sont des FAÇADES DE LECTURE.** Les assertions vivaient dans du code de test
NUnit qui n'entre pas dans un player build. **Résultat négatif, net.**

---

## 4. L'ORACLE — trouvé, mais ailleurs : `Runner.ReplayValidator`

Le chemin y mène depuis les xrefs de `ReplaySerializer$$DeserializeReplay`.

### La chaîne

`Runner.AutomaticBattleRunner$$Run` (signature lue dans `frida/methods.tsv` :
`..ctor(logger, battleConfig, maxAmountOfTurns, findReplayBugs: bool, validate: bool, timeSource)`,
`Run() -> Runner.AutomaticBattleResult`) monte un `IdunBattle.Runner.IdunRunner`, joue les tours par
`IdunRunner$$get_AiControl`, récupère `IdunRunner$$GetRecordedReplay`, puis — **si et seulement si le
flag `validate` est armé** — appelle `Runner.ReplayValidator$$RunReplayWithParameters`.

`Runner.ReplayValidator$$RunReplayWithParameters` rejoue le replay dans un
`IdunBattle.Runner.ReplayRunner` neuf (`AddMessageValidator`, `InitializeBattle`, `RunAllSteps`),
récupère `ReplayRunner$$GetValidationReplay`, et compare par **quatre** contrôles :

| Contrôle | Ce qu'il compare |
|---|---|
| `ReplayValidator$$CheckForInvalidMessages` | messages refusés par l'`IMessageValidator` |
| `ReplayValidator$$CompareOutputStream` | `Replay$$GetWholeBattleOutputStream` des deux replays, **caractère par caractère** (`System.String$$get_Chars`) |
| `ReplayValidator$$CheckForCheats` | motifs texte des `Runner.Cheats.*` dans le flux |
| `ReplayValidator$$CompareRngEvents` | `Replay$$GetWholeBattleRngEvents` via `Runner.RngEventComparer$$DoRngEventsDiffer` |

Le verdict est un `Runner.ValidationResult` (104 o) : `IsValid` en `+0x10`, raison en `+0x18`,
confiance (float) en `+0x20`, les deux flux comparés en `+0x30`/`+0x38`, les deux listes RNG en
`+0x50`/`+0x58`. `idun.ui.HeadlessBattleRunnerPopup$$HandleBattleResult` traite un `IsValid == false`
comme une **erreur** : incrément du compteur, `ReplayFiles$$SaveAutoBattleReplay`, et
`idun.Idun.Source.Util.ReportingTool$$ReportBattleBugWithReplay`.

### Nature exacte de cet oracle — à ne pas surestimer

C'est un oracle de **re-simulation déterministe** : il compare **le natif à lui-même**. Il ne porte
**aucune valeur attendue écrite par un dev**, et ne dit donc rien sur la justesse des règles du jeu.
Son objet est le non-déterminisme et la triche.

**Vis-à-vis de notre port Python, en revanche, il est parfaitement non circulaire** — et c'est là
qu'est la valeur.

---

## 5. Ce qui est réellement actionnable : l'output stream

### Ce que contient le flux

`IdunBattleLogic.Replay.ReplayRecorder$$OnStreamCacheRootGroupFinished(group)` fait
`_outputStreamBuffer.Append(group)`, et
`ReplayRecorder$$SaveCurrentOutputStreamBufferToLastMessage(clearBuffer)` vide ce buffer dans
`ReplayStep.OutputStream` (`+0x28`) du **dernier message appliqué**, puis `StringBuilder.Clear()`.

⇒ **l'output stream est la sérialisation texte des groupes racine du StreamDispatcher, découpée par
message d'entrée** — c'est-à-dire l'arbre de stream que le projet a déjà matérialisé (mig 014).

Qu'il s'agisse de texte **structuré en lignes taguées** est attesté par deux sources indépendantes :
`Runner.TextComparer` (`DoesLineMatchPattern`, `DoLinesDifferByTagValue`, `FindLineDifferences`,
`LinePattern`) et les détecteurs `Runner.Cheats.*`, qui reconnaissent des motifs par
`get_OutputStreamTextPattern` — `BlockDamageCheat`, `CritDamageModificationCheat`,
`AbilityVariableAmountCheat`, `MoreDamageAndKillCheat`, `ForceOverkillCheat`, `ScoreAmountCheat`.
**Dégâts, blocks, crits, overkills et valeurs de variable d'ability y figurent donc nommément.**

### Pourquoi c'est disponible sur NOS runners, sans rien armer

- `IdunBattle.Runner.IdunRunner$$Initialize` appelle **inconditionnellement**
  `IdunBattle.Runner.IdunRunner$$SetupReplayRecorder` (xref unique et directe).
  ⇒ **tout runner que `buildRunner` initialise a déjà un `ReplayRecorder` actif.**
- `frida/hooks/game/recorder.ts` tient **déjà** l'objet `Replay` (via `runnerOff.replayRecorder`
  puis `ReplayRecorder.GetReplay`) — il n'en lisait que `RngSeed`.

Le capteur manquant tenait donc en **deux invocations de plus sur un objet déjà en main**.

### Livré ici : `frida/hooks/features/replay-output-stream.ts`

RPC `replayOutputStream({ runnerId, maxChars })` et `replayOutputStreamStatus()`.
**Aucun `Interceptor` posé** — coût nul tant que le RPC n'est pas appelé.

⚠ **Piège intégré** : `readIl2cppString` (`il2cpp/helpers.ts`) **plafonne à 500 caractères et rend
`null` au-delà**. L'output stream d'une bataille le dépasse de plusieurs ordres de grandeur — un
appel naïf aurait rendu un flux « absent » en silence. Le module embarque son propre lecteur de
grande chaîne (`length` en `+0x10`, chars UTF-16 en `+0x14`) et rapporte `outputStreamLength` réel +
un booléen `truncated`.

**Vérifié** : `npx tsc -p tsconfig.hooks.json --noEmit` → **0 erreur imputable** (146 erreurs
préexistantes, dont 142 dans `hooks/scratch/`, gitignoré) ; `npm run build:hooks` → **exit 0**,
bundle 1 135 960 o, symbole présent.

⛔ **NON CONFRONTÉ — nécessite une fenêtre de reinject.** Un agent ne réinjecte pas. Le code est
livré, jamais exécuté. **Première mesure à faire quand la fenêtre s'ouvre** : sur un runner monté par
`rl_duel build`, appeler `replayOutputStreamStatus()` (doit rendre tout `true`), puis jouer quelques
tours et appeler `replayOutputStream({ runnerId })` — **et regarder le texte**. Toute la valeur de la
piste dépend de sa granularité réelle, qui n'est PAS établie ici.

---

## 6. Réfutation d'une prémisse du brief

> « Le `MoveNext` de chaque coroutine `<RunAbilityTestInternal>d__N` est absent des DEUX tables. »

**FAUX, mesuré.** `data/symbols/rnca9r7q6c/ghidra/functions.tsv` en contient **97**, et
`frida/methods.tsv` **97** également (`idun.tests.ability_precision_shot_test.u003CRunAbilityTestInternalu003Ed__1$$MoveNext`,
`normal_attack_test`, `ability_narthecium_test`, …). Ils sont lisibles ; ils n'ont simplement pas été
lus, l'enquête ayant basculé sur la piste de l'oracle. Le corps décompilé de
`ability_camo_cloak_test$$RunAbilityTestInternal` (celui qui « ressemble à de la télémétrie Unity »)
est bien la **fabrique de coroutine**, pas le corps — le corps est dans le `MoveNext`.

---

## 7. Une tentative qui a ÉCHOUÉ — à ne pas refaire à l'identique

Pour dériver le format des lignes du flux **sans** attendre la fenêtre, j'ai essayé de lire les
littéraux de `Runner.Cheats.*::get_OutputStreamTextPattern`.

- **Par Ghidra** : impossible. Ces getters chargent leur chaîne depuis un **slot de cache de string
  literal** résolu au runtime ; `include_strings` rend `[]`. Le décompilé ne montre que le slot.
- **Par `global-metadata.dat`** : parsing tenté avec le layout d'en-tête `stringLiteralOffset` /
  `stringLiteralDataOffset` documenté pour v29+. **Il ne tient pas** sur ce build —
  `metadata version = 39`, et sur 15 186 entrées déclarées seulement **396** se décodent en UTF-8
  valide, les « résultats » étant des blobs qui se chevauchent (donc index/longueur faux). Le layout
  de l'en-tête a changé et je ne l'ai pas re-dérivé.

⇒ Le format des lignes reste **non établi**. C'est le résidu `#477-r2`, et il faut commencer par
re-dériver le header v39 (ou passer par un dumper qui le connaît), pas par re-tenter ce parsing.

## 8. Ce que je n'ai PAS regardé

- **Le contenu réel d'un output stream.** Établi par RE (producteur + consommateurs), jamais
  observé. C'est le trou principal, et il est bloqué sur la fenêtre de reinject.
- **Les 97 `MoveNext`** des coroutines par ability : lisibles, non lus. Ils diraient le scénario
  exact que les devs jouent pour chaque ability (positions, ordre des casts) — potentiellement une
  banque de scénarios de test toute faite.
- **`Runner.Cheats.*`** : ~12 classes, chacune avec son `get_OutputStreamTextPattern`. Les lire
  donnerait le **format des lignes** du flux sans avoir à l'observer.
- **`IdunBattleLogic.Synchronous.SynchronousRunner$$UploadDiscrepancyReplay`** : la voie
  client/serveur de détection de divergence, non explorée.
- **L'atteignabilité de `HeadlessBattleRunnerPopup`** dans le build livré. Elle est enregistrée par
  `thor.Menu.MenuSystems` et exposée par
  `idun.shared.commands.ViewCommandExecutor$$ShowHeadlessBattleRunnerPopup`, mais **je n'ai pas
  établi** que son prefab est présent ni par quel geste UI on l'ouvre. Sans intérêt direct de toute
  façon : `Runner.AutomaticBattleRunner` est une classe `System.Object` ordinaire (48 o), donc
  instanciable par appel IL2CPP direct sans passer par l'UI.

## 9. Ce qui existait déjà et que je n'ai pas redécouvert

`docs/ai/game-architecture.md` et `docs/ai/ai-engine-audit.md` décrivent **déjà**
`AutomaticBattleRunner` et la recette pour l'instancier (« voler `_logger` et `_timeSource` du runner
actif »). Ce qui est neuf ici : les deux derniers booléens du ctor sont **nommés** (`findReplayBugs`,
`validate`) — et la doc existante les passe tous deux à `false`, donc **la validation n'a jamais été
armée** ; ainsi que tout le mécanisme `ReplayValidator` / output stream / RNG events.

## Résidus

- **#477-r1** — Mesurer le contenu réel de l'output stream (bloqué : fenêtre de reinject).
  Tant qu'il n'est pas lu, la valeur de la piste reste une **hypothèse étayée**, pas un fait.
- **#477-r2** — Lire les ~12 `Runner.Cheats.*::get_OutputStreamTextPattern` pour dériver le format
  des lignes **offline**, sans dépendre de la fenêtre.
- **#477-r3** — Lire les 97 `<RunAbilityTestInternal>d__N$$MoveNext` : banque de scénarios par
  ability, écrite par les devs.
- **#477-r4** — Armer `validate: true` sur un `AutomaticBattleRunner` instancié par nos soins, et
  voir si `ValidationResult.IsValid` détecte une divergence sur une bataille montée par nous.
- ~~**#477-r5**~~ / ~~**#477-r6**~~ — **RÉSOLUS**, cf. § 2c. `UnitModifiers` (@0x50) est porté
  (`rl_duel build --unit-modifier`, 8 `Id` mesurés) ; le placement à la tuile exacte est porté par
  `--place` / `--a-place`. `StartingActions` (@0xc0) est **mesuré INATTEIGNABLE** depuis le JSON →
  #477-r9. Probe : `probe_477_bc_montage_leviers.py`.
- **#477-r9** — `BattleConfiguration.StartingActions` (@0xc0) est **ignoré par la désérialisation
  Newtonsoft** (mesuré, avec témoin). L'atteindre exige d'**écrire dans l'objet natif après
  `deserializeFromJson`** — donc un capteur/hook neuf dans `frida/hooks/`, donc une fenêtre de
  reinject. Ancrage : `ctx.rpc.initAndStart` (`frida/hooks/features/launch.ts`), juste après
  `deserializeFromJson(args.configJson, battleConfigClass)`, avant `buildRunner`. **Intérêt réel à
  qualifier avant de dépenser la fenêtre** : le pipeline traversé est le même que celui de
  `playerUnits[]` (`AddUnitMessage` → `AddUnitOperation$$Execute`), déjà exposé par `--place` /
  `--a-place`. Ce que `StartingActions` apporterait en plus : **tout autre message d'entrée** que
  `AddUnit` (le champ est une `List<IInputMessage>`), joué **pendant** `SetupGameOperation`.
- **#477-r7** — Trancher `<Visit>g__AddUnit|0` → `AddUnitOperation$$Execute` →
  `UnitFactory$$Build` (invoqué par vtable, aucune xref d'appel).
- **#477-r8** — **Outillage** : une table `fields.tsv` (`classe` → `offset` → `nom de champ`) dans
  `data/symbols/<build>/frida/` supprimerait la triangulation d'offsets qui a coûté le plus de temps
  ici, et trancherait à elle seule plusieurs indéterminés ci-dessus. À considérer si le pipeline de
  dump peut l'émettre.
