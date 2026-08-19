# #10038 — Le guild war en sandbox, sans un octet vers le serveur

**État : BATAILLE JOUABLE, IA ADVERSE CONDUITE** (2026-08-19).

⚠ **Deux versions antérieures de cette ligne étaient FAUSSES, et par la même faute** : conclure sur
un cycle éprouvé sans avoir joué la suite. La première annonçait « RÉSOLU » sans avoir joué un tour ;
la seconde attribuait la panne à un flux visuel gelé, alors que c'était une CONSÉQUENCE. Ce qui est
acquis maintenant est MESURÉ tour joué : vue et runner sur le même joueur (`0x3` / `3`) et le même
compte de tours (`3` / `3`), quatre drapeaux de pause à 0, file `IsIdle`, 10 unités sans doublon,
l'IA adverse joue seule et rend la main.

## 1. La voie, et pourquoi c'est celle-là

Le guild war est le **seul** mode sans voie sandbox native : pas de
`SandboxGuildWarBattleConfig`, pas de `GetHotseatGuildWarsConfig`, pas de branche GuildWars dans
`GetHotSeatGameModeSpecificConfig`. C'est une absence côté JEU, pas un trou d'outillage.

⛔ **La voie native parle au serveur.** `ViewCommandExecutor$$StartGuildWarsMatch` alloue une
`GuildWarsGameModeSource` puis appelle `StartMatch` ; le squelette `AGameModeSource` appelle
`SendLoadBattleGameEventInternal` **par slot de vtable**, qui génère un battleId et l'enregistre
**au chargement**. Le guild war a des tentatives limitées ET un debuff cumulatif.

**Ce qu'on fait** : on FORGE la source (son ctor n'envoie rien) et on invoque
`LoadBattleInternal`, un override virtuel **indépendant** de l'envoi.

    guildWarSourceForger  ->  GuildWarBattleData..ctor(12)  puis  GuildWarsGameModeSource..ctor(17)
    guildWarSourceBc      ->  LoadBattleInternal(false)     =>    la BC DU JEU

⚠ **Ne PAS fabriquer la BC à la main.** `guildWarBuildBc` (appel direct de `GetGuildWarsConfig`
avec nos 14 arguments) existe encore mais produit une BC dont chaque entrée est une occasion de se
tromper — mesuré : catalogue tronqué, ennemis en ids nus au lieu de `<id>:pvp`, `MachineOfWarAmmo`
à 0 au lieu de 148. La source forgée va chercher les 14 seule.

## 2. Les pièges du montage, tous mesurés

| # | Piège | Signature |
|---|---|---|
| 1 | `Nullable<T>` porte `hasValue` **en tête** | `access violation accessing 0x11` = `0x1 + 0x10` : le natif lit le `slotIndex` comme un `String*` et sa longueur au `+0x10` |
| 2 | `GuildWarBattleData` est **imbriquée** | `findClassAnywhere` rend « introuvable » ; la prendre comme **paramètre 0** du ctor de la source |
| 3 | `Enemies` n'est pas la liste brute | c'est `GetLineUpModels(slot, unitProgression, out power)` ; le DTO brut fait lever le ctor |
| 4 | L'adresse du roster est **(zone, SLOT)** | le record porte aussi `ZonePartIndex` (`+0x18`), le ctor lit `+0x1c` |
| 5 | Le plafond de pose vaut **0** | `maxUnitsPossible: 0` avec `allUnitModels: 98` — la HUD autorise zéro pose |
| 6 | Le prêteur du HUD doit être **la source du mode** | la sandbox rend un `HotseatUnitModel` qui échoue à `IsUnlocked`, et ne pose jamais `supportsMachinesOfWar` |
| 7 | La délégation rendait une **BOÎTE** | `GetUnitsForDeploymentHUD` rend un `PooledList<T>`, type VALEUR : `runtime_invoke` le boxe. `fires=4, ok:true` **et** `allUnitModels: 0` |

⚠ **Le n°7 est le plus coûteux parce qu'il RAPPORTE UN SUCCÈS.** La valeur vit à `+0x10`
(cf. `rosterFraisGuildBoss`, même correctif côté guild boss).

## 2bis. TROUVER LA ZONE — `guildWarZones`, par PSEUDO

`guildWarSourceForger` exige un `warZoneId`, et l'inventaire complet (`guildWarBoardRead`, 637 Ko)
ne désigne les zones que par des GUID. `guildWarZones { filtre: "<pseudo>" }` les rend compactes et
nommées, via `GuildWarPhaseProgression$$GetOccupyingGuildMember(warZoneId, zonePartIndex)` :
`zoneId`, `type`, `zonePartIndex`, le PSEUDO de l'occupant, et par slot `battu` / `tentatives` /
`unites`. Lecture pure, aucune tentative consommée.

⚠ **`battu` n'est pas cosmétique** : sur `VAE〙Nicodsf` (`SupplyDepot`, `zonePartIndex 1`), les
index 1, 2 et 3 sont RASÉS — les cinq défenseurs à 0 PV. Monter dessus donne une bataille
dégénérée que rien ne signale. Et **« slot 1 » est ambigu** : l'UI numérote à partir de 1, l'API à
partir de 0.

⚠ **LA CARTE NE VIENT PAS DE LÀ.** `warZoneConfigParOrdinal` rend `boardId: null` sur les 16
ordinaux (mur gshared de `GetWarZoneConfig`). La table qui répond est `guildWarZoneConfigs` ->
`config.zoneTypeConfigs[<type>]` — mesuré : `SupplyDepot` = `MC1_31` / sps **3**,
`AntiAirBattery` = `PVP_desert_10` / sps **1**.

## 3. La recette (ordre STRICT — c'est le piège principal)

Tout s'arme **avant** `sandbox_mode.py start`.

```
guildWarSourceForger  {warZoneId, zonePartIndex, slotIndex, boardId, spawnPointsSet, confirmer:true}
guildWarSourceBc      {confirmer:true}                     -> configJson
sandboxModeBcOverride {configJson}                         <- la BC BRUTE, non patchée
deploymentPrefabArmer     {armer:true}
deploymentPhaseArmer      {armer:true, forcer:true, confirmer:true}
deploymentPoolArmer       {armer:true, confirmer:true, source:"guildWar",
                           only:["GetUnitModel","GetGameModeSpecificDeploymentHudOptions",
                                 "GetUnitsForDeploymentHUD"]}     <- `only` OBLIGATOIRE (cf. §5bis)
deploymentPlafondArmer    {armer:true, max:5, min:1, confirmer:true}
deploymentHudArmer        {armer:true}
deploymentMemoire         {armer:true}
deploymentClearArmer      {armer:true, confirmer:true}
deploymentPoseCommitArmer {armer:true, confirmer:true}
deploymentSyncArmer       {armer:true, confirmer:true}
deploymentStartArmer / deploymentRunnerStartArmer {armer:true}
sandboxModeGameViews      {armer:true, confirmer:true}
```

Puis `python scripts/python/sandbox_mode.py start --mode waves --session <SID> --units a,b,c,d,e
--onslaught-tier 5 --confirmer` (le mode importe peu : l'override substitue la BC ; ce qui compte
est la SOURCE).

⚠ **La BC de la source n'a AUCUNE unité joueur (`PredefinedUnits = 12:5`, l'ennemi seul), et c'est
CORRECT** — le jeu passe `mainPlayerUnits = 0` et la phase de déploiement pousse les unités au
runner en `AddUnitMessage`. Un ajout de camp joueur avait été introduit comme béquille quand le
montage échouait sans unités ; ce témoin avait été mesuré **avec le plafond cassé**, donc il ne
prouvait rien. La béquille est retirée.

⚠ **Le roster ne s'injecte PLUS** (`deploymentDraftUnites`) : avec le prêteur `guildWar`, la source
fournit son propre roster, MoW comprises. Les deux mécanismes se battaient sur
`GetUnitsForDeploymentHUD`.

## 4. Vérification du cycle complet

    POSE-COMMIT faits = 5   tous ok, placeholderOte=true, compte 0->1->2->3->4->5
    HUD poses         = 6   dont adeptExorcist avec mow=true
    MEMOIRE           = 5 poses + mow={adeptExorcist, playerId 11, position 2}

## 5. Deux méthodes qui ont sauvé le diagnostic

⚠ **Un état AU REPOS ne dit pas si quelque chose s'est passé.** `_isMachinesOfWarSelection` valait
`false` après un aller-retour — ce qui est AUSSI sa valeur initiale. C'est le **compteur de tirs**
qui porte le fait. `deploymentHudArmer.chemins` ancre les huit chemins de sélection/bascule et
relève le drapeau à l'entrée et à la sortie.

⚠ **Un compteur se confronte à son ADRESSE, et une liste d'ancrages se dérive de `list_xrefs`.**
Trois relevés mutuellement incompatibles ont fait soupçonner un corps dédupliqué ; les adresses
publiées l'ont réfuté. Le filet n'était pas faux, il était **troué** : `PrepareFor...` a **cinq**
appelants, la première liste n'en portait que trois.

⚠ **Et une conclusion tirée d'un écran incomplet est fausse.** « Aucun chemin MoW ne tire, donc il
n'y a pas de bascule » a été démenti par l'utilisateur qui la voyait à l'écran. Une fois la chaîne
complète, les mêmes compteurs montent tous.

## 5bis. LA BATAILLE — ce qui tourne, ce qui ne tourne pas

**Tourne** : les poses deviennent des unités réelles, la résolution de dégâts fonctionne (PV qui
descendent des deux côtés), la retraite sort proprement, aucun doublon.

**L'IA ADVERSE ÉTAIT MORTE PARCE QU'UNE EXCEPTION VERROUILLAIT LA BATAILLE — ET C'ÉTAIT LA NÔTRE.**

⚠ **DEUX explications antérieures de ce paragraphe sont RÉFUTÉES, dans l'ordre.** La première
disait « il manque le déclencheur automatique, la sandbox est en hotseat » : le déclencheur EXISTE
et tourne à chaque frame, et le remède qu'elle prescrivait (« écrire un relais qui appelle l'IA au
changement de tour ») aurait masqué la panne. La seconde désignait le flux visuel gelé : c'était un
SYMPTÔME observé une fois, pas la cause. Les deux avaient la même faiblesse — désigner un coupable
sans contre-épreuve. Ce qui a tranché est une **contre-épreuve** : même montage, une délégation en
moins, plus d'exception.

La chaîne native, décompilée puis confrontée aux objets vivants le 2026-08-19 (`t6dpr4k06g`) :

```
IdunBattle.View.Game.IdunGameViews$$Update                       (chaque frame)
  -> QueueComputerActions()
       si IsPlayerAiControlled(joueurCourant)
          ET !IsPaused ET !_isLogicPausedFromUI
          ET !_isLogicPausedFromVisuals ET !_isLogicPausedFromException
          ET _queuedComputerActions == null
       -> StartCoroutine(RunComputerActionsForCurrentPlayerInMultipleFrames)
            -> IdunRunner.AiControl.RunComputerActionsForPlayer(id)
```

Le joueur courant de la VUE n'est pas celui du RUNNER :
`IdunGameViews$$get_CurrentPlayerEntityId` = `_matchView.CurrentDraftingPlayerId ?? _matchView.CurrentPlayerId`,
et `MatchView` est un **miroir poussé** par `PrepareTurnStepHandler$$ExecuteInternal`, seul appelant
de `MatchView$$SetCurrentPlayer`.

| étage | AVANT (cassé) | APRÈS (correctif) |
|---|---|---|
| runner | `currentPlayer 4`, `turn 4` | `currentPlayer 3`, `turn 3` |
| vue | `MatchView.CurrentPlayerId = **3**`, `toursTotal 5` | `CurrentPlayerId = **3**`, `toursTotal 3` |
| pauses | `_isLogicPausedFromException = **1**` | les **quatre** à 0, `IsLogicPaused false` |
| file | `IsIdle false`, 9 messages, gelée sur `Ability_Active:Loki_NormalAttack` / `start` | `IsIdle true` |
| verdict | `IsCurrentPlayerAiControlled false` alors que c'est le tour de l'IA | l'IA joue et rend la main |

**L'EXCEPTION, captée par `vueExceptionArmer`** (ancrage d'observation sur
`IdunGameViews$$HandleException`) :

```
MethodAccessException
  'idun.shared.collections.pools.IPoolableObject.BeforeReturnToPoolAttempt'
  on type 'idun.shared.collections.pools.PooledList<System.String>'

IdunMainView$$Start -> BattleAndEditorFlowController$$LoadBattle
  -> IdunMainView$$StartBattle+0x1265 -> IdunGameViews$$Enable+0xf1
```

Elle tombe **AU CHARGEMENT**, avant le premier clic : la bataille naissait déjà verrouillée. D'où
« l'IA ne joue pas » ET « l'UI refuse mes moves » — un seul défaut, deux symptômes.

**LA CAUSE : NOS DÉLÉGATIONS SUBSTITUAIENT UN OBJET MIS EN POOL.** Deux méthodes du prêteur rendent
un `PooledList<System.String>` — `GetUnitsForDeploymentHUD` et `GetUnlockedUnitsPooled`. C'est un
TYPE VALEUR d'un seul champ (`_listWithStatus : PooledListElement<T>`, mesuré par `classFields`).
En substituant le retour, la liste que la source SANDBOX venait de louer n'était jamais rendue,
et l'appelant disposait la NÔTRE, louée dans un autre pool. Le `Dispose` heurtait alors
`BeforeReturnToPoolAttempt` sur un générique pleinement partagé.

**LE CORRECTIF, en deux volets :**
1. `GetUnitsForDeploymentHUD` — **on ne substitue plus, on REMPLIT** la liste que le jeu a déjà
   louée (`retval` -> `PooledListElement._object` -> `List<String>`, offset résolu PAR NOM), avec
   les ids mis en cache en chaînes JS au premier tir. Plus aucun objet mis en pool ne traverse la
   frontière. Mesuré : `REMPLI 125/125`.
2. `GetUnlockedUnitsPooled` — **retiré de la délégation** (`only:` sans lui). Son commentaire
   affirmait « MESURÉ jamais appelé sur ce chemin » : PÉRIMÉ, il tirait (`fires: 1`). Et il est
   inutile — `allUnlockedUnitModels` vaut **107** sans lui.

⚠ **CONTRE-ÉPREUVE, et c'est elle qui fait foi** : même montage, `deploymentPoolArmer` désarmé ->
`fires` inchangé, aucun verrou. Puis volet 1 seul -> l'exception PERSISTE, et l'état de la
délégation nomme le coupable restant (`GetUnlockedUnitsPooled` : « délégué à … »). Sans les deux
volets, on aurait conclu à tort que le volet 1 suffisait.

⚠ **ET LE VERROU N'A AUCUNE CLEF.** `PauseLogic`/`ContinueLogic` et
`PauseLogicFromVisuals`/`ContinueLogicFromVisuals` vont par paires ;
`_isLogicPausedFromException` n'a **pas** de `ContinueLogicFromException`. Une exception attrapée
tue donc la bataille DÉFINITIVEMENT. Et en silence : `HandleException` ne journalise que si
`_gameModeSource.HandleBattleException(e)` rend vrai, `_errorListeners` est **vide**,
`_firebaseAnalytics` est un **Mock**, et `Player.log` fait 0 octet. Aucun popup, aucune trace.
Le capteur est `vueExceptionArmer` / `vueExceptionEtat` (`frida/hooks/features/vue-exception.ts`).

⚠ **ET LE CHIEN DE GARDE NE RÉPARE RIEN.** `MessageExecutionQueue$$CheckLastActivityTimeout`
(appelé par `Update` quand `!_disableTimeouts`) ne fait que **JOURNALISER** au-delà de 10 s puis
`ManualStopwatch$$Reset`. Il ne force jamais la complétion.

**CE QUE ÇA ÉCARTE** — quatre hypothèses, toutes mesurées FAUSSES :
`PreventAIControl` (slot 0x13 d'`IGameModeSource`) rend `false` pour 11, 12 ET 13 — aucun verrou
hotseat ; `IsPlayerAiControlled(entité 4)` rend **true** — l'ennemi EST reconnu piloté par l'IA ;
`UseSyncPvpEnemyTurnInputState` = false ; la section `Player.Players` de notre BC est **identique**
à celle du guild boss qui marche (11 = PlayerType 0, 12 = PlayerType 1), tout comme
`DisableTimeouts`, `DisableAnimatorRecovery`, `NoAutomaticUnitTurns` et
`Turn.IsStartTurnAutomaticAfterHuman`. Ni la BC ni la source de mode ne sont en cause.
Écarté aussi : `_unitViews.count = 10` pour 10 unités, `_pendingUnitViews` vide — ce n'est pas une
vue d'unité manquante.

**RESTE NON EXPLIQUÉ, et il faut le dire** : la file gelée sur
`Ability_Active:Loki_NormalAttack` / `start` n'a été observée QU'UNE FOIS, et elle n'a pas été
reproduite après correctif. Qu'elle soit le même défaut attrapé en plein message n'est **PAS
établi** — c'est plausible (une exception au milieu d'un message laisse
`_currentlyProcessingMessage` en l'air), rien de plus. Si elle revient :
`Loki_NormalAttackVisuals` referme son pas sur `OnCasterAnimationEventInternal`, un ÉVÉNEMENT
D'ANIMATION du caster — instrumenter `PickWeapon` / `GetWeapon` / `GetFallbackWeaponVisualConfig`.

⚠ **MÉTHODE — tout ce qui précède a été mesuré SANS UN SEUL REINJECT**, par les RPC génériques déjà
embarqués : `classFields(ns, cls)` pour NOMMER les champs, `classInterfaceSlots` pour nommer le slot
0x13, et `viewField` / `viewJson` / `viewList` / `viewInvoke` avec `surPointeur` pour marcher les
objets vivants depuis `IdunMainView.gameViews`. Réflexe à garder : avant d'écrire une sonde et de
dépenser une fenêtre, vérifier ce que la surface générique atteint déjà.

⚠ **DEUX PIÈGES D'OUTILLAGE, tous deux payés dans cette tranche même.**

- **UN `Update()` NE FAIT PAS UN MonoBehaviour.** `premiereInstance` / `FindObjectsByType` rend
  `null` sur `IdunGameViews` : c'est `IdunMainView` qui appelle son `Update`, pas Unity. Elle se
  prend par le champ NOMMÉ `gameViews`. Même piège que `ViewCommandExecutor` et
  `thor.Menu.MenuSystems`, déjà consigné dans `view-command.ts` — et re-commis ici.
  ⚠ Et **DEUX `IdunMainView` coexistent** après une retraite suivie d'un remontage :
  `FindObjectsByType` rend d'abord la MORTE, dont `gameViews` est nul. Un lecteur bâti dessus rend
  « champ NUL » et se lit « pas de bataille », alors que la bataille tourne. Viser
  `sandboxProbe.instance`, ou énumérer et écarter celles sans `gameViews`.

- **UN CAPTEUR NE DOIT JAMAIS LAISSER UN ÉCHEC ACCESSOIRE MASQUER CE QU'IL A DÉJÀ MESURÉ.**
  La première version de `vueExceptionEtat` rendait le refus de résolution d'instance AVANT les
  captures : une exception RÉELLEMENT captée (`fires: 1`) était invisible, et il a fallu un
  reinject pour relire — qui l'a effacée. Les captures sortent maintenant **toujours**.

⚠ **DEUX PIÈGES DE LECTURE, tous deux payés cher dans cette tranche.**

1. **`ctrl` de `decisionView` n'est PAS « contrôlé par l'humain ».** C'est
   `UnitExtensions$$IsControlledByCurrentPlayer(entity, state)` — donc **« appartient au joueur dont
   c'est le tour »**. J'en ai déduit une « inversion du contrôle » qui n'existait pas, et j'ai bâti
   deux hypothèses dessus (`GameMode`, puis les paramètres de la source) avant d'aller lire le code
   qui produit le champ. **Lire le producteur du champ avant de l'interpréter.**
2. **Un relais de déploiement qui reste armé PENDANT le combat est un suspect.**
   `deploymentPlafondArmer` tirait encore 16 fois en pleine bataille, en écrivant dans
   `VisualBattleQuery` que tous les modes partagent. Ils doivent se désarmer au START.

⚠ **ET LE REJEU DE POSES EST À DOUBLE TRANCHANT.** Avec une BC portant AUSSI un camp joueur,
`deploymentPoseCommitArmer` produit des **DOUBLONS** : 5 (natif) + 5 (rejeu) + 5 (ennemis) = 15
unités, dont les copies sortent invalides. Le compte tombe exactement. Sans béquille dans la BC, la
question de savoir s'il redevient nécessaire est **OUVERTE** — c'est le prochain essai.

## 5ter. « AUCUNE UNITÉ NE BOUGE » — un PAS VISUEL qui ne se referme jamais

**Le moteur n'est PAS en cause, et le mesurer a pris trois attributions fausses.** Mesuré le
2026-08-19 sur la session 41, bataille au tour 3 :

| couche | mesure |
|---|---|
| clic -> FSM | `fsmTrace` enregistre TOUT : `NormalState -> FingerDownOnUnitForFirstTime -> UnitNormallySelected -> MovementTargetSelectedState -> NormalState` |
| FSM -> moteur | `fsmTap` rejoué à la main déplace `eldarAutarch` de (2,0) à **(6,0)** |
| moteur | `MovementComponent.InitialValue` = mobilité ; `ActorStatisticsComponent.TilesMovedThisTurn` la consomme. `tauMarksman` : 2 et 2 -> **0 tuile, et c'est la RÈGLE** |
| vue | `GetUnitViewAt(col,row)` place **4 des 5 unités du joueur sur leur case de DÉPLOIEMENT**, les 4 ennemies à jour |

**LE VERROU, nommé** : `MessageExecutionQueue._currentlyProcessingMessage` reste `true`,
`_lastActivity` = `Ability_Active:Loki_NormalAttack`, `_lastActivityStep` = `start`, et **6**
messages attendent derrière (`_messages._size`). Le groupe bloqué est
`<EntityId> 85` (`eldarMauganRa`), `<Source> "Loki_NormalAttack"`, **3 messages,
`_nextMessageIndex` 0 — aucun exécuté**. Son `Loki_NormalAttackVisuals` a `Status`, `Caster`,
`_weaponWeaponVisualConfig` et `_onFinished` **tous NULS** : sans `_onFinished`, le pas ne
signale jamais sa fin, et `CheckLastActivityTimeout` ne force rien (cf. §5bis).

⚠ **CE N'EST PAS UNE CONFIG MANQUANTE — et c'est ce qui écarte l'explication facile.** Le
**MÊME** Maugan Ra a réussi une attaque normale plus tôt dans la même bataille
(`Status "Finished"`, `_weaponWeaponVisualConfig` NON nul). Même unité, même ability, deux
issues : raté d'initialisation ponctuel, pas un trou de données. **Cause racine NON ÉTABLIE.**

⚠ **LE LIEN ENTITÉ -> VUE EST INTACT, donc il n'accuse RIEN.** `HasUnitView` et `GetUnitView`
rendent la bonne vue pour les **9** entités ; `GetUnitView(91)` rend exactement le pointeur que
`GetUnitViewAt(2,0)` trouve. Chercher une vue manquante est une impasse — déjà écartée en §5bis
sur `_unitViews.count`, et re-écartée ici par une autre voie.

⚠ **`aiMovableTiles` À 0 N'EST PAS UNE PANNE** : c'est la mobilité consommée. Le lire comme un
défaut du moteur a coûté une attribution fausse de plus. La discrimination se fait sur
`InitialValue` vs `TilesMovedThisTurn`, pas sur le compte de tuiles.

⚠ **ET `AUnitView` N'EST PAS ÉNUMÉRABLE** : sa chaîne est `AUnitView <- ABaseUnitView <-
System.Object` — `viewInstances` rend `instances: null` (classe NON dérivée d'`UnityEngine.Object`),
pas `[]`. Passer par `IdunGameViews$$GetUnitViewAt` / `$$GetUnitView`, jamais par l'énumération.
`Loki_NormalAttackVisuals`, lui, EST un `MonoBehaviour` et s'énumère.

### 5quater. LES 12 RELAIS SONT ÉCARTÉS — le suspect nommé est RÉFUTÉ

Le test que ce dossier annonçait comme « jamais réalisé » a été joué le 2026-08-19, sur une
bataille montée sur `MedicaeStation1` part 1 slot 3 (occupant `VAE`-Gaunt) : **les 12 relais de
déploiement DÉSARMÉS et l'override BC RETIRÉ au cast 39**, en plein combat, `0` échec au
désarmement. L'abandon est tombé **entre les casts 39 et 44**, donc APRÈS la coupure, avec la
signature EXACTE des trois reproductions précédentes — écart **1** sur `SetupAndExecuteAbility`,
`Init` et `ParseTargetsFromQueue`, **0** sur `Execute` ; groupe `<EntityId> 93`,
`<Source> "Loki_NormalAttack"`, `onFinished: false`.

⇒ **« Un relais qui reste armé PENDANT le combat » ne cause pas ce bug.** C'était le suspect que
§6 nommait ; il tombe.

⚠ **NE PAS ÉLARGIR LA CONCLUSION.** Retirer l'override ne retire PAS la BC guild war de la
bataille EN COURS — elle continue de tourner dessus. Ce qui est écarté, ce sont les 12 relais
ACTIFS pendant le combat, **pas le montage entier**. Restent armés les deux pompes
(indispensables) et le capteur — un `attach` pur, posé APRÈS les deux premières reproductions,
donc hors de cause.

⚠ **ET « JEU BLOQUÉ » N'EST PAS UN GEL.** Deux lectures de `pumpFaults.frameNo` espacées de 3 s
rendent **+372 frames** (~124 f/s) pendant que l'écran ne bouge plus. Le témoin vaut parce que
`pumpFaults` et `visuelAbandonneEtat` sont **SYNCHRONES** : ils répondent même thread principal
bloqué. Tout RPC mis en file, lui, expirerait — et `ping` ne prouve rien, pour la même raison
(déjà payé une fois : une réponse en 141 ms sur un jeu dont la boucle était arrêtée).

Taux cumulé : **4 abandons / 393 casts ≈ 1,0 %** sous montage, contre **0 / 183** en sandbox
native. À ce taux, le contrôle natif a ~16 % de chance d'être un hasard : **« montage vs jeu de
base » n'est TOUJOURS pas tranché** — il y faudrait ~400 casts natifs de plus.

## 6. Reste ouvert

- **Les salves d'ouverture.** `EnvironmentAbilities` de la zone reste VIDE : la popup les
  construit inline, avec deux dictionnaires génériques dont un `get_Item` sur clé entière — le mur
  gshared déjà rencontré sur `GetWarZoneConfig`. Le record capté au clic « Start Battle » (bouchon
  sur `StartGuildWarsMatch`, qui rend la main sans appeler `StartMatch`) les donnerait tout faits,
  sans contact serveur.
- **La MoW adverse** est nulle : le record l'attend sous forme MODÈLE (la popup la tire de
  `GetMachineOfWarUnits`), pas sous la forme DTO du slot.
- **POURQUOI un `Loki_NormalAttackVisuals` sort NON INITIALISÉ** (§5ter). Le mécanisme est
  mesuré, la cause ne l'est pas — et **nos 12 relais sont désormais écartés** (§5quater), donc
  c'est la piste qui reste. À confronter : ces visuels sont des `MonoBehaviour` **POOLÉS**
  (3 instances vivantes, 2 `Finished`) — une location qui ne passe pas par son `Setup` rendrait
  exactement cette signature, et le pooling est déjà connu pour mentir sur l'identité d'un
  pointeur. `IdunUnitViewPool` est le voisin à lire.
- **La file bloquée n'a pas de sortie connue.** `MessageExecutionQueue` expose
  `OnMessageFinishedProcessing(message)` et `ProcessNextMessage()` ; forcer l'un des deux est
  une ÉCRITURE dans une bataille vivante, **jamais tentée**. À n'essayer que sur une bataille
  qu'on accepte de perdre, et en observant d'abord.
