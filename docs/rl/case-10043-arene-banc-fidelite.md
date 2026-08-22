# #10043 — Le banc d'Arène : d'où viennent VRAIMENT les unités d'un duel sandbox

**Build `t6dpr4k06g`, 2026-08-22.** Lu au décompilé, confirmé sur une BC produite.

## Le fait qui a déclenché la chasse

`arene_banc.py` montait un duel dont l'équipe d'en face n'était **pas** celle de l'adversaire.
Preuve : `ultraTigurius` était dans les deux équipes, et le catalogue de la BC n'en portait
**qu'un seul exemplaire** (0 doublon sur 74 entrées) — la même entrée, nos stats, des deux côtés.
Et ce qu'on ne possède pas sort en coquille : `darkaAzrael` **rang 0 / puissance 562**, contre
396 257 pour notre `ultraInceptorSgt`.

## La chaîne, de bout en bout

```
SandboxGameModeSource$$LoadBattle
  builder = new BattleConfigBuilder(_unitProgression, gameConfigValues,
                                    releasableUnitsSource, _logger, settings)
  bc = builder.GetHotseatConfig(sandboxConfig)
     -> GetHotSeatGameModeSpecificConfig(sandboxConfig)     // cascade de dispatch PAR TYPE
        -> GetHotseatSyncPvpConfig(SandboxPvpBattleConfig)  // la seule branche PvP
           -> GetPvpLevelConfig(... 14 parametres ...)
```

⚠ La cascade a **dix** branches (nos dix modes). Ses **cinq dernières ne font pas `return`** :
elles affectent et retombent — c'est la **dernière** qui correspond qui gagne.

## La correspondance des 14 paramètres, lue au corps

| paramètre de `GetPvpLevelConfig` | vient de |
|---|---|
| `opponentLineup` | **`cfg.PlayerUnits[1]`** |
| `overrideMainPlayerUnits` | **`cfg.PlayerUnits[0]`** |
| `getEnemyUnit` | une CLÔTURE `Func<String, Boolean, IUnitModel>` fermée sur `PlayerUnits[1]` |
| `environmentAbilities` | `cfg.EnvironmentAbilities` (+0x18) |
| `opponentMachineOfWarLineup` | `cfg.EnemyPlayerMachineOfWar` |
| `overrideMainPlayerMachineOfWar` | `cfg.MainPlayerMachineOfWar` |
| `mainPlayerType` / `enemyPlayerType` | `cfg.Player1Type` / `cfg.Player2Type` |
| `boardId` / `spawnPointsSet` | champs homonymes |

Le natif traite les deux camps **asymétriquement**, et `GetRealUnitConfigurations` le dit aussi :
`enemies: List<String>` + un résolveur, contre `overrideMainPlayerUnits: List<IUnitModel>`.

## ⛔ LE CTOR DE LA SOURCE N'EST PAS LE LEVIER

Piège réel : `SandboxGameModeSource..ctor(config, **IUnitProgression**, gameConfig, logger,
featureUnlocker)` passe bien sa progression à `BattleConfigBuilder..ctor(**unitProgression**,
...)`. On en conclut naturellement qu'elle décide des stats. **Elle ne les décide pas** :

```
GetUnitConfiguration(unitModel: IUnitModel, logger, remainingHealth) -> UnitConfiguration
```

**Aucune progression en paramètre.** Ce qui est déjà un `IUnitModel` est FIGÉ. La progression du
compte agit en amont, quand le harnais résout les ids (`UnitProgression$$GetUnit`).

⇒ **Le seul levier est la position 4 du CONFIG**, et précisément `PlayerUnits[1]`.

## QUATRE propriétés que le ctor à 9 arguments ne pose PAS

Il ne remplit que `BoardId` (+0x28) → `BossUnit` (+0x58) :

```
0x10  DeactivateActiveAbilitiesOnAI   Boolean
0x11  DisableOverkill                 Boolean
0x18  EnvironmentAbilities            EnvironmentAbilities
0x20  EnvironmentAbilityTeams         Dictionary`2
```

⚠ Corrige une affirmation FAUSSE qui a circulé : « le mode sandbox n'installe pas
`EnvEndBombardment` ». Il l'installerait très bien — **c'est nous qui laissons le champ vide**.
`GetHotseatSyncPvpConfig` LIT `EnvironmentAbilities`, en tire `GetExtraEnemyUnits`, et le repasse
à `GetPvpLevelConfig`. Un banc qui remplit ce champ retrouve la pression de fin de l'Arène
(`nrOfRounds = 8`, `healthPct = 20`, lus sur `PvpProgression$$GetEnvironmentAbilitiesConfig`).

⚠ `EnvironmentAbilityTeams` est **nommé, pas typé** : ses types de clé et de valeur n'ont pas été
lus. Le nom suggère une table ability → équipe, ce qui recouperait la question « une triggered
qui ne vise que l'adversaire » — mais la latéralité mesurée ailleurs est un `TeamId` **en dur**
dans le DSL de chaque ability (`EnvArtillerySupport` → `Team1_Default` ; `EnvAttemptDebuff` et
`EnvDefenderHealthBuff` → `Team2_DefaultEnemy`). Les deux mécanismes coexistent peut-être ;
**ne rien conclure avant d'avoir lu le dictionnaire**.

## Ce que le jeu DÉTIENT sur l'adversaire, et qu'on n'exploite pas

`PvpServerResponseTranslator$$ApplyUnitInfo(unitsDto, data)` est un traducteur DTO → progression.
Par unité adverse, le SERVEUR envoie : `rank`, `xpLevel`, `xp`, `progressionIndex`,
`primaryAbility`, `secondaryAbility`, `upgrades`, `items`. Rangés dans le dictionnaire de
`PvpOpponentProgressionData` (+0x78), lisible par `GetKnownUnitIds()` (**6 clés** mesurées : les
5 du lineup **+ la MoW**) et `GetUnit(id)`.

⚠ **`progressionIndexDirectionAscension` n'est PAS recopié** — il existe des deux côtés (+0x18 sur
le DTO, +0x1c sur `UnitProgressData`) et aucune des neuf affectations ne l'écrit.

⇒ La donnée pour un banc FIDÈLE est complète. `GetPublicProfileLineup(...)` rend une
`List<IUnitModel>` — exactement le type qu'attend `PlayerUnits[1]`.

## ⚠ LA VRAIE REFERENCE EST `PvpGameModeSource`, PAS L'ECRAN DE DEV

`idun.ui.SandboxContainer$$GetSandboxPvpBattleConfig` est le bac-a-sable **de developpement** du
jeu : son corps lit des *dropdowns* (`GetMachineOfWarFromCurrentDropDowns`) et des toggles. Il
montre comment REMPLIR notre config sandbox (ctor 9 args -> `DeactivateActiveAbilitiesOnAI` ->
`SandboxContainer$$AddEnvironmentAbilities`), mais ce n'est PAS le chemin d'un duel officiel.

**Les xrefs de `GetPvpLevelConfig` donnent la vraie reponse — CINQ appelants, et le duel reel en
fait partie :**

```
BattleConfigBuilder$$GetHotseatSyncPvpConfig            <- notre banc (sandbox)
AutomaticTestingPvpConfigFactory$$Build                 <- tests automatises
FriendlyGameModeSource$$LoadBattle                      <- duels amicaux
PvpGameModeSource$$LoadBattleInternal                   <<< L'ARENE OFFICIELLE
PvpStarterSeasonGameModeSource$$LoadBattleInternal      <- saison debutant
```

⇒ **Le duel officiel et le banc convergent sur le MEME constructeur de BC.** Le banc n'est pas un
chemin parallele : c'est le meme code, alimente autrement.

Ce que passe `PvpGameModeSource$$LoadBattleInternal`, et qui DIFFERE du chemin sandbox :

| paramètre | Arène officielle | notre banc |
|---|---|---|
| `opponentLineup` | `this+0xC8` — ses modèles, depuis SA progression | `PlayerUnits[1]` — nos ids, notre progression |
| `overrideMainPlayerUnits` | **NULL** — le builder résout depuis le compte | `PlayerUnits[0]` |
| `overrideMainPlayerMachineOfWar` | **NULL** | `cfg.MainPlayerMachineOfWar` |
| `environmentAbilities` | `AProgressionGameModeSource$$GetEnvironmentAbilitiesFromProgression` | champ laissé vide |
| `opponentUnitIdPostFix` | une **CONSTANTE** (non nulle) | **0** — codé en dur par `GetHotseatSyncPvpConfig` |

⚠ **`opponentUnitIdPostFix` EXPLIQUE LE SYMPTOME EXACT.** C'est un suffixe applique aux ids
adverses. Le duel reel le pose, donc deux unites homonymes restent DEUX entrees de catalogue.
Le chemin sandbox passe `0` — d'ou l'`ultraTigurius` UNIQUE mesure plus haut, partage par les
deux equipes. **C'est une limite STRUCTURELLE du chemin sandbox** : meme avec les bons modeles
en `PlayerUnits[1]`, deux homonymes fusionneraient. Le ctor a 9 arguments ne l'expose pas.

⚠ **Et `overrideMainPlayerUnits = NULL` renverse une hypothese** : on croyait devoir fournir NOS
unites. Le duel officiel ne les fournit pas — il laisse le builder les tirer de la progression du
compte, qui est justement ce que le ctor de la source lui donne. Notre equipe n'a donc jamais eu
besoin d'etre passee en position 4.

## La tranche suivante

1. **`PlayerUnits[1]`** ← les `IUnitModel` de `GetPublicProfileLineup`. Demande un genre de plus
   côté hook : des modèles DÉJÀ RÉSOLUS passés par pointeur, au lieu d'ids.
2. **`EnvironmentAbilities`** ← pour retrouver le bombardement.

⚠ **NE PAS DEVINER comment poser ces propriétés** : `idun.ui.SandboxContainer$$GetSandboxPvpBattleConfig`
est le constructeur du JEU pour ce config (identifié dans `case-10020` §statique PvP) — il alloue
sur le même statique puis appelle le ctor. C'est la référence à mirrorer.

## Garde en place

`arene_banc.py --confirmer` **REFUSE** (rc 2) tant que `--adversaire-faux-je-sais` n'est pas posé,
et refuse AVANT d'ouvrir l'Arène. Une prose d'avertissement avait déjà été écrite au commit
précédent — et le banc a quand même été monté avec un `darkaAzrael` à 562 en face.

## Coût

**Aucun.** `energyUsedSinceServerUpdate` = 0, rating et trophées inchangés. Un
`SandboxGameModeSource` ne porte aucun `PvpEncounterId`, et c'est lui que
`GameEventService$$CompletePvpLocation` exige pour débiter.
