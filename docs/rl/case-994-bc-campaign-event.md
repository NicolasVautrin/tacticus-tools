# `#994` — capturer les BC de TOUTES les campagnes d'event, et pourquoi 60 y perdent leur boss

**Build** `rnca9r7q6c` · session Frida 88 · 2026-08-13

## Le resultat

`POST /api/campaigns/build {campaignType:4, campaignId, locationIndex}` sort la BC de n'importe
quel noeud d'event, **praticable ou non**. Les 12 campagnes (6 `eventStandard` + 6 `eventExtremis`)
x 33 noeuds = **396 BC**, `220,8 Mo` bruts -> **`22,6 Mo` gzip**, ~6 min a ~1 s/noeud.

Fidelite verifiee **par noeud** contre le catalogue : les ennemis de `BC.PredefinedUnits` sont
exactement ceux de `units[0]`. Discriminant fort — `eventExtremis6` (hors event courant) rend ses
`darkaNpc1Infiltrator:16`, `campaign1` ses `necroNpc1TutWarriorFTUEtest`.

⚠ **Ca ne pousse RIEN au serveur.** Capteur wire-only (`netCaptureArm`, les 3 portes
`Snowprint.ClientSdk.Web.WwwWebHelper$$PostString|PostBytes|PostData`) sur une fenetre de 75+
builds : **2** requetes, toutes deux le heartbeat `ct-live/ct/userId/...`, **0** vers
`game-event/game3/`. La reserve de l'en-tete de `campaign-builder.ts` (« LoadBattle(true) may emit
funnel/analytics events », jamais verifiee) est donc **LEVEE**. C'est l'inverse du warmup d'avant
#993, qui deposait une defaite enregistree a chaque execution (`case-599`).

## Les 60 boss perdus — cause STRUCTURELLE, pas un bug de garde

**5 noeuds par campagne** (`locationIndex` 6, 11, 18, 23, 32), soit **60 sur 396**, sortent sans
leur boss : ni dans `PredefinedUnits`, ni dans `BC.BossUnit`, qui reste `null`. Regularite
parfaite — ce sont exactement les noeuds dont le catalogue porte un `boss`.

**Les campagnes Standard/Elite/Mirror/EliteMirror ne sont PAS touchees** : leur boss est une unite
ordinaire (`necroWarden`, `adeptRetributor`) deja listee dans `units`. Les events ont un boss
DEDIE (`admecBossMarshallCE`, `darkaBossLion`, `adeptNpcMorvenn`...).

La cause est le *mute-swap* : le builder usurpe l'identite d'un noeud sur la
`CampaignGameModeSource` live (il ecrit `_currentCampaignId`/`_currentLocationIndex`/`_currentMatch`
et, sur la `CampaignProgression` partagee, `_campaignType`/`_campaignId`/`_battlesConfigCampaigns`),
appelle `LoadBattle`, puis restaure. Or le boss d'event est un champ de la source **EVENT** :
`CampaignEventGameModeSource.SourceData.<Boss>` @ `+0x40` (`IUnitModel`), avec `<EnemyMow>` @
`+0x48`. La source standard n'a pas ce champ — elle ne peut pas le fournir.

## Le DOWNSCALE de rang n'est PAS dans la BC, et c'est normal

Mesure : entre une BC `Event` et une BC `Standard`, **0** unite commune differe. `BC.Units` porte
les rangs REELS du compte. Le cap s'applique **au deploiement**. Trois etages :

| etage | ou |
|---|---|
| la bataille declare sa rarete | `clientGameConfig.liveEvents.idunLiveEventConfigs[eventType=="campaignEvent"].campaigns[].standardBattles[].rarity` |
| la rarete donne le rang max | `clientGameConfig.units.heroProgressionSteps` : Common 3 · Uncommon 6 · Rare 9 · Epic 12 · Legendary 17 · Mythic 20 |
| le heros y est rabattu | `IdunMetaLogic.UserProgress.Model.UnitModelCappedAtProgressionIndex$$GetCappedRank` |

Profil : standard = 12 Common, 12 Uncommon, 9 Rare ; extremis = 12 Epic, 12 Legendary, 9 Mythic.
Table par noeud produite (396 entrees, 12/12 campagnes appariees, 0 orpheline).

⚠ `dumpCampaignCatalog` ne le voit PAS : il ne sort que `battles.campaigns`, ou `rarity` a **0**
occurrence. Chercher le cap la-dedans ne rend rien.
⚠ Piste plausible mais **FAUSSE, verifiee** : `CampaignBattleRestrictions` (champ `<Restrictions>`
du `SourceData`) ne porte que `RequiredFactions` / `RequiredUnits`.
⚠ **NON TRANCHE** : `HeroProgressionSteps` serialisee dans une BC donne `Rarity 5 -> MaxRank 19`,
le gameconfig donne `Mythic -> 20`. Deux sources, non re-mesure.

## Le runner ne consomme AUCUNE GameModeSource

`ctx.rpc.initAndStart` prend `{configJson, seed, playerUnits, owner, recordReplay}` : il
deserialise une `BattleConfiguration` JSON et monte l'`IdunRunner` dessus. `launch.ts` ne contient
**aucune** occurrence de `GameModeSource`. `live-bc.ts` documente que tout ce qui consommait la
source live pour le runner a ete supprime au passage a `buildNormalizedBC`.

Le warmup capture **trois** choses, et le partage est net : `UnitProgression` (-> `json-build.ts`)
et `GameConfig` (-> `items-catalog.ts`) servent au **runner** ; la `CampaignGameModeSource` sert au
**builder de BC**.

**Verifie** : BC `eventStandard1/0` passee en `--seed-bc` avec `--rank 3` -> runner monte, bataille
jouable. ⚠ `rl_duel build` l'utilise comme **seed** (roster + config) et compose un duel par-dessus ;
rejouer le noeud a l'identique demande de pousser ses `PredefinedUnits` (`_patch_predefined_units`).

## `buildCampaignEventConfig` — la voie, entierement cartographiee

`CampaignEventGameModeSource$$LoadBattleInternal` lit du `SourceData` : `+0x20` `<Config>`,
`+0x28` `<AvailableUnits>`, `+0x30` `<BorrowableUnits>`, `+0x48` `<EnemyMow>` (offsets confirmes
**deux fois** — decompile et `classFields` runtime), puis appelle
`Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetCampaignEventConfig` — le pendant event de
`GetCampaignLevelConfig`.

⚠ **`isRestart` doit valoir `false`** : a `true`, `LoadBattleInternal` RELIT le `SourceData` via
`GetUpdatedSourceData` et **ecrase toute mutation**. C'est l'inverse du builder campagne, qui
appelle `LoadBattle(true)`.

⚠ **`ViewCommandExecutor$$StartCampaignEventMatch` ne prend PAS `(campaignId, locationIndex)`** :
son unique argument est le `SourceData` (18 champs, dont 3 `Func<>` et un `IUnitModel` resolu).
Le fabriquer a la main pour le passer a un natif qui ecrit est exclu.

Les pieces sont toutes chez `IdunMetaLogic.UserProgress.CampaignEventProgression` :
`GetCampaignBattleConfig` · `GetBattle`/`GetBattles` · **`GetBoss`** · `GetEnemies` ·
`GetBorrowableUnits` · `GetBattleRestrictions` · **`GetCappedUnitModel`** /
`GetCappedUnitsAllowedInBattle`. Elle est atteignable depuis le `ViewCommandExecutor` epingle
(`+0x3a0` -> `+0x2d0`, lu dans `StartCampaignEventMatch`).

⇒ Reste a faire : capturer l'instance de `CampaignEventGameModeSource` (hook `.ctor`, exactement
le patron deja en place pour `MachinesOfWarEventGameModeSource` et `PvpGameModeSource` dans
`campaign-builder.ts`), puis muter son `SourceData` et appeler `LoadBattle(false)`. Prerequis
identique a celui du MoW : l'event doit avoir ete ouvert une fois in-game. **Exige une fenetre de
reinject.**

## Outillage decouvert au passage

RPC **`classFields(ns, cls)`** et `findClassesNamed` (`mode-source-capture.ts`) lisent les champs
d'une classe en runtime. Une classe **imbriquee** se lit avec `ns` **VIDE** (`classFields("",
"SourceData")`). C'est ce qui a donne les 18 champs du `SourceData`.

## Pointeurs

`frida/hooks/features/campaign-builder.ts` (mute-swap, RPC `buildCampaignConfig`) ·
`frida/hooks/features/mode-source-capture.ts` (`classFields`) · `docs/rl/case-599-trafic-serveur-campagne.md`
(le capteur wire-only et ce que le client envoie) · `docs/rl/case-993-warmup-sans-clic.md`
