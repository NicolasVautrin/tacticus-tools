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

Il ne remplit que `BoardId` (+0x28) → `BossUnit` (+0x58). Les quatre autres sont des
**auto-propriétés** (`k__BackingField` ⇒ il existe un setter, lu au RPC `classFields`) :

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

## L'objet `EnvironmentAbilities` est ENTIÈREMENT lu — 40 octets, 3 champs

Taille `classes.tsv` = 40 = les trois champs ci-dessous et rien d'autre ; les trois écritures
sont lues dans `idun.ui.SandboxContainer$$AddEnvironmentAbilities`, qui pose l'objet sur le
config par un appel d'interface **slot 5** (`set_EnvironmentAbilities`).

```
IdunBattle.Configuration.EnvironmentAbilities                (40)
  0x10  Abilities                List<EnvironmentAbilityConfiguration>
  0x18  EnhancementAbilities     List<EnhancementsEnvironmentAbilityConfiguration>
  0x20  AbilitiesConfigurations  Dictionary<TriggeredAbilityConfigId, AbilityConfiguration>

IdunBattle.Configuration.EnvironmentAbilityConfiguration     (48)
  0x10  ConfigId   TriggeredAbilityConfigId
  0x20  Level      Idun.Shared.Level          <- clampé 0..100 par le ctor de l'écran de dev
  0x24  PlayerId   Nullable<PlayerId>         <<< LA LATÉRALITÉ, ET ELLE EST PAR ABILITY

IdunBattle.Configuration.EnhancementsEnvironmentAbilityConfiguration  (64, dérive du précédent)
  0x30  Targets    List`1
  0x38  Stack      Int32
```

⚠ **`EnvironmentAbilityConfiguration.PlayerId` répond à « une triggered qui ne vise que
l'adversaire »** : chaque ability d'environnement porte un propriétaire OPTIONNEL. L'écran de dev
écrit `null` (`*(cfg + 0x24) = 0`), donc « sans propriétaire » est un DÉFAUT, pas une contrainte.
Ce que fait le natif de ce `PlayerId` n'est PAS encore lu — seule son existence est établie.
Elle **coexiste** avec le `TeamId` en dur du DSL de chaque ability (`EnvArtillerySupport` →
`Team1_Default` ; `EnvAttemptDebuff` et `EnvDefenderHealthBuff` → `Team2_DefaultEnemy`) : lequel
gagne reste à mesurer.

⚠ `EnvironmentAbilityTeams` (+0x20 du **config**, à ne pas confondre avec `AbilitiesConfigurations`
+0x20 de l'**objet**) reste un `Dictionary\`2` dont les paramètres ne sont pas résolus. Fait
mesuré : `AddEnvironmentAbilities` **ne l'écrit jamais** — l'écran de dev du jeu monte donc des
batailles sandbox en le laissant nul. Il n'est pas requis. Piste voisine :
`BattleConfigBuilder$$GetAdditionalPlayersRequiredByEnvironmentAbilities(battleConfig)` rend un
`OrderedSet<StaticBattleRules.AbilityPlayerRequirement>`.

## ⛔ NE PAS CONSTRUIRE `EnvironmentAbilities` À LA MAIN — le jeu en a TROIS fabriques

Toutes rendent l'objet fini, signatures lues dans `frida/methods.tsv` :

```
SyncPvpGameModeSource$$GetEnvironmentAbilities()                          -> EnvironmentAbilities
AProgressionGameModeSource$$GetEnvironmentAbilitiesFromProgression(extraAbilitiesConfig)
                                                                         -> EnvironmentAbilities
AutomaticTestingEnvironmentAbilitiesFactory$$Build(gameMode, units, battleCount, probability)
                                                                         -> EnvironmentAbilities
```

La deuxième est celle de l'Arène réelle (`PvpGameModeSource` dérive d'`AProgressionGameModeSource`).
Demander l'objet au jeu et passer le pointeur au setter coûte moins qu'un mirror, et ne peut pas
diverger du build.

## Ce que `SetupGameOperation` en fait vraiment, à la pose

`SetupGameOperation$$GetEnvironmentAbilities(gameMode)` APLATIT les deux listes de `BC+0x78` dans
une seule (même `MethodInfo` d'`AddRange` pour les deux ⇒ `EnhancementAbilities` est bien une
sous-classe), puis ajoute **des ids EN DUR** : `1483` et `24` inconditionnellement, `1326` sous
condition de mode, plus tout `StaticBattleRules.DamageTrait$$GetDamageTraitAbilities()`, plus les
dérivées de `StaticBattleRules.TriggeredAbility$$GetDerivedEnvironmentAbilities(<clé>)` pour
chaque clé du dictionnaire `BC+0x90 +0x18`.

⇒ **Une BC à `EnvironmentAbilities` vide n'est PAS une bataille sans environnement** : ces
ajouts-là tombent quand même. Ce qui manque au banc, c'est le bombardement de fin, pas tout.

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
| `opponentUnitIdPostFix` (`System.String`) | une **CONSTANTE** non nulle | **null** — codé en dur par `GetHotseatSyncPvpConfig` |

⚠ **`opponentUnitIdPostFix` EXPLIQUE LE SYMPTOME EXACT.** C'est un suffixe applique aux ids
adverses. Le duel reel le pose, donc deux unites homonymes restent DEUX entrees de catalogue.
Le chemin sandbox passe `0` — d'ou l'`ultraTigurius` UNIQUE mesure plus haut, partage par les
deux equipes. **C'est une limite du chemin par CONFIG SANDBOX** : meme avec les bons modeles en
`PlayerUnits[1]`, deux homonymes fusionneraient, et le ctor a 9 arguments ne l'expose pas. Les
deux autres appelants accessibles passent `null` eux aussi (`AutomaticTestingPvpConfigFactory$$Build`
mesuré : `randomizeAiInput = 1`, postfix `0`). ⚠ Ce n'est PAS une limite du MOTEUR : le paramètre
existe sur `GetPvpLevelConfig`, qu'on peut appeler directement — cf. « La tranche suivante ».

⚠ **Et `overrideMainPlayerUnits = NULL` renverse une hypothese** : on croyait devoir fournir NOS
unites. Le duel officiel ne les fournit pas — il laisse le builder les tirer de la progression du
compte, qui est justement ce que le ctor de la source lui donne. Notre equipe n'a donc jamais eu
besoin d'etre passee en position 4.

## La tranche suivante — et elle NE PASSE PLUS par `SandboxPvpBattleConfig`

Le config sandbox est un **emballage de commodité**. Dès lors qu'on touche au hook (inévitable
pour passer des `IUnitModel` par pointeur), viser directement le constructeur coûte le même
geste et lève le verrou du postfix. `frida/methods.tsv` en donne la signature COMPLÈTE, nommée
et typée — c'est la découverte qui change le plan (`#187` le disait déjà : les noms de paramètres
natifs sont lisibles hors Ghidra) :

```
BattleConfigBuilder$$GetPvpLevelConfig(
    id: String, boardId: String, spawnPointsSet: Int32,
    opponentLineup: List<IUnitModel>, opponentMachineOfWarLineup: IUnitModel,
    getEnemyUnit: Func<String, Boolean, IUnitModel>, playerAmmo: Int32,
    environmentAbilities: EnvironmentAbilities,
    overrideMainPlayerUnits: List<IUnitModel>, overrideMainPlayerMachineOfWar: IUnitModel,
    mainPlayerType: Nullable<PlayerType>, enemyPlayerType: Nullable<PlayerType>,
    randomizeAiInput: Boolean, opponentUnitIdPostFix: String)   -> BattleConfiguration
```

⚠ **`opponentUnitIdPostFix` est un `System.String`**, pas un entier opaque : le `0` lu partout
ailleurs est un `null`. En appelant le constructeur directement on le FOURNIT, et la fusion des
homonymes disparaît — le verrou n'était structurel qu'au chemin sandbox.

## ⛔ MESURÉ : un lineup MATÉRIALISÉ ne dispense PAS du résolveur — le natif le DÉ-matérialise

L'espoir était qu'en passant des `IUnitModel` déjà résolus, `getEnemyUnit` ne serve qu'aux ids
manquants et puisse rester nul. **Le corps de `GetPvpLevelConfig` le réfute** : il fait
délibérément l'aller-retour `modèle -> chaîne -> modèle`.

```
b__2(u: IUnitModel) -> String        // MAP appliqué a opponentLineup
    u.Id  puis  String.Concat(id, postFix)      <- le POSTFIX est appliqué ICI

b__0(enemyTypeId: String) -> UnitConfiguration  // RÉSOLVEUR passé a GetLevelConfigWithRealUnits
    isExtra = extraEnemyUnits.Contains(enemyTypeId)
    modele  = getEnemyUnit.Invoke(enemyTypeId, isExtra)   <- INVOCATION INCONDITIONNELLE
    cfg     = GetUnitConfiguration(modele, logger, null)
    cfg.Id  = enemyTypeId                                 <- RE-ESTAMPE l'id POSTFIXÉ
```

Trois faits qui en découlent :

1. **`getEnemyUnit` est invoqué pour CHAQUE unité adverse, sans garde de nullité** — la branche
   sans délégué tombe sur le helper de `throw`. Passer `null` lève, ça ne dégrade pas.
2. **Le postfix et le résolveur sont COUPLÉS.** `cfg.Id = enemyTypeId` est *le* mécanisme qui
   garde deux homonymes distincts au catalogue — la question de départ. Il n'a de sens que si le
   résolveur sait rendre un modèle pour un id postfixé.
3. ⇒ **Patcher le seul `opponentUnitIdPostFix` CASSE la résolution.** Le résolveur du chemin
   sandbox (`<>c__DisplayClass37_0$$<GetHotseatSyncPvpConfig>g__GetEnemy|0`) apparie par
   **égalité de chaîne exacte** et termine sur `Enumerable.First` — pas `FirstOrDefault`. Un
   `ultraTigurius<postfix>` ne matche rien et **lève**.

## ⛔ ET POURTANT IL N'Y AVAIT AUCUN HOOK À ÉCRIRE — la délégation existait déjà

**Cette section a d'abord prescrit d'ancrer `g__GetEnemy|0` et de poser le postfix. C'était une
sur-ingénierie**, bâtie sur une lecture partielle : `b__0` est la clôture côté **builder**, et en
conclure « le délégué est obligatoire donc on le hooke » saute une question — *contre quoi le
résolveur sandbox résout-il ?* Le corps de `GetHotseatSyncPvpConfig` y répond :

```
<>c__DisplayClass37_0  +0x10 = le SandboxPvpBattleConfig   +0x20 = le builder
                       +0x18 = extraEnemyUnits             +0x28 = cfg.PlayerUnits[1]

g__GetEnemy|0(unitId) -> ... -> Enumerable.First(PlayerUnits[1], u => u.Id == unitId)
```

⇒ **le résolveur lit la liste QU'ON FOURNIT.** Le délégué est bien obligatoire ; le *hooker* ne
l'a jamais été. Le seul défaut était la **source** des modèles : `modeleUnite()` les résolvait par
`UnitProgression$$GetUnit`, donc sur NOTRE progression.

**Le correctif est une délégation, comme dans les neuf autres modes** (livré le 2026-08-22) :
un joueur de `unitesParJoueur` s'écrit `{adversaire: n}`, et la liste vient de
`PvpOpponentProgressionData$$GetPublicProfileLineup(unitProgression, itemProgression, logger,
null)` — nos services de lecture, SES données. Idem `machineAdverse` pour la MoW.

## Ce qui reste ouvert : le POSTFIX, et lui seul

Il n'a d'effet que si les **deux équipes alignent le même `unitId`** — `b__0` fait
`cfg.Id = enemyTypeId`, donc deux homonymes se fondent encore en une entrée de catalogue. C'est
une tranche séparée, et elle exige les **deux crans ensemble** : poser
`opponentUnitIdPostFix` sans adapter le résolveur le fait **lever** (appariement par égalité
exacte, `Enumerable.First` sans variante `OrDefault`).

## ✅ CONFRONTÉ — A/B sur la MÊME proposition, build `t6dpr4k06g`, session 15, 2026-08-22

Proposition 0 (`Tarkin`, rating 477, niveau 43). Deux BC construites (`bc`, rien monté), la même
équipe de notre côté, seul l'argument du camp adverse change.

| unité adverse | `--adversaire 0` (FIDÈLE) | `--enemies` (PAR IDS) |
|---|---|---|
| `custoTrajann` | rang 10 · niv 36 · 2 012 PV · 30 463 | rang 17 · niv 50 · 8 213 PV · **343 212** |
| `orksWarboss` | rang 11 · niv 32 · 2 253 PV · 31 115 | rang 17 · niv 52 · 9 584 PV · **569 109** |
| `custoBladeChampion` | rang 7 · niv 27 · 778 PV · 5 021 | rang 17 · niv 50 · 8 670 PV · **507 238** |
| `emperExultant` | rang 9 · niv 35 · 1 396 PV · 25 852 | **rang 0 · niv 1 · 90 PV · 0** |
| `custoVexilusPraetor` | rang 5 · niv 19 · 569 PV · 2 148 | **rang 0** · niv 25 · 198 PV · 1 282 |

⇒ La colonne PAR IDS est **notre roster** : ce qu'on possède sort maxé (rang 17, jusqu'à 569 109
de puissance), ce qu'on ne possède pas sort en **coquille** (rang 0). La colonne FIDÈLE est
cohérente de bout en bout — rangs 5 à 11, niveaux 19 à 36, puissances 2 148 à 31 115 — ce à quoi
ressemble un joueur de niveau 43. L'erreur allait donc **dans les deux sens** : elle gonflait ET
elle rabotait.

⚠ **LA MACHINE OF WAR EST LE CAS QUI A FAIT ROUGIR MON PROPRE GARDE, À TORT.** `tyranBiovore`
sort `Rank 0` / `Health 0` / `Damage 0` — mais **à l'identique sur les DEUX voies**, donc ce
n'est pas causé par le changement. Ce qui diffère est `StarLevel` **4 (le sien) contre 8 (le
nôtre)** et `Power` 154 contre 604 : la liaison MORD bien. **L'axe de progression d'une MoW est
`StarLevel`, pas `Rank`** — un critère écrit sur le rang rend un faux échec sur un modèle
pourtant juste.

**Résidu ouvert, PRÉEXISTANT et hors de cette tranche** : les statistiques de combat d'une MoW
(`Health`, `Damage`, `Movement`, `Armor`) sont à **zéro dans `Units`** sur les deux voies, alors
que ses abilities et ses traits, eux, sont peuplés. Où le natif les prend au moment de la
bataille n'est pas établi — `PredefinedMachines[0].MachineOfWar` ne porte qu'un `UnitId`.

## Garde en place

`arene_banc.py --confirmer` **REFUSE** (rc 2) tant que `--adversaire-faux-je-sais` n'est pas posé,
et refuse AVANT d'ouvrir l'Arène. Une prose d'avertissement avait déjà été écrite au commit
précédent — et le banc a quand même été monté avec un `darkaAzrael` à 562 en face.

## Coût

**Aucun.** `energyUsedSinceServerUpdate` = 0, rating et trophées inchangés. Un
`SandboxGameModeSource` ne porte aucun `PvpEncounterId`, et c'est lui que
`GameEventService$$CompletePvpLocation` exige pour débiter.
