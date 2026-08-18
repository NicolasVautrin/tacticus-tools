# #10038 — Le guild war en sandbox, sans un octet vers le serveur

**État : RÉSOLU** (2026-08-19). Cycle complet éprouvé — déploiement héros + Machine of War,
poses converties en unités réelles, clear fonctionnel, retraite fonctionnelle.

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

## 3. La recette (ordre STRICT — c'est le piège principal)

Tout s'arme **avant** `sandbox_mode.py start`.

```
guildWarSourceForger  {warZoneId, zonePartIndex, slotIndex, boardId, spawnPointsSet, confirmer:true}
guildWarSourceBc      {confirmer:true}                     -> configJson
sandboxModeBcOverride {configJson}                         <- la BC BRUTE, non patchée
deploymentPrefabArmer     {armer:true}
deploymentPhaseArmer      {armer:true, forcer:true, confirmer:true}
deploymentPoolArmer       {armer:true, confirmer:true, source:"guildWar"}
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

## 6. Reste ouvert

- **Les salves d'ouverture.** `EnvironmentAbilities` de la zone reste VIDE : la popup les
  construit inline, avec deux dictionnaires génériques dont un `get_Item` sur clé entière — le mur
  gshared déjà rencontré sur `GetWarZoneConfig`. Le record capté au clic « Start Battle » (bouchon
  sur `StartGuildWarsMatch`, qui rend la main sans appeler `StartMatch`) les donnerait tout faits,
  sans contact serveur.
- **La MoW adverse** est nulle : le record l'attend sous forme MODÈLE (la popup la tire de
  `GetMachineOfWarUnits`), pas sous la forme DTO du slot.
