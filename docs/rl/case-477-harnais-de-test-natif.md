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

## 2. L'absence de machinerie d'assertion — confirmée, et sur quatre classes

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

## 3. L'ORACLE — trouvé, mais ailleurs : `Runner.ReplayValidator`

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

## 4. Ce qui est réellement actionnable : l'output stream

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

## 5. Réfutation d'une prémisse du brief

> « Le `MoveNext` de chaque coroutine `<RunAbilityTestInternal>d__N` est absent des DEUX tables. »

**FAUX, mesuré.** `data/symbols/rnca9r7q6c/ghidra/functions.tsv` en contient **97**, et
`frida/methods.tsv` **97** également (`idun.tests.ability_precision_shot_test.u003CRunAbilityTestInternalu003Ed__1$$MoveNext`,
`normal_attack_test`, `ability_narthecium_test`, …). Ils sont lisibles ; ils n'ont simplement pas été
lus, l'enquête ayant basculé sur la piste de l'oracle. Le corps décompilé de
`ability_camo_cloak_test$$RunAbilityTestInternal` (celui qui « ressemble à de la télémétrie Unity »)
est bien la **fabrique de coroutine**, pas le corps — le corps est dans le `MoveNext`.

---

## 6. Ce que je n'ai PAS regardé

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

## 7. Ce qui existait déjà et que je n'ai pas redécouvert

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
