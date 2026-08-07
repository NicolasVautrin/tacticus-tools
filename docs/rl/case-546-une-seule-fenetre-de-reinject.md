# case-546 — les neuf résidus `BLOCAGE: capteur`, et la fenêtre qu'il en reste

Build `rnca9r7q6c`. Session Frida 2, bundle injecté le 2026-08-07 à 11:18:51 depuis
`frida/dist/hooks.js` construit à 11:18:20.

Tranche à un seul but : **rendre UNE SEULE fenêtre de reinject suffisante**. Le dépôt portait
**neuf** lignes `BLOCAGE: capteur` (huit numérotées + une sans numéro). Confrontées au bundle
RÉELLEMENT injecté, **cinq ne bloquaient plus rien** et une sixième ne bloquait pas sur un
capteur. **Trois** capteurs restaient à écrire ; ils le sont.

---

## 1. Ce que le bundle injecté porte déjà — et pourquoi cinq lignes étaient périmées

Le critère n'est pas « le correctif est-il livré ? » mais « est-il dans le bundle que la session
a CHARGÉ ? ». La session lit `bundlePath` (`GET /api/sessions`), et le bundle est daté : tout
correctif mergé **avant** 11:18:20 y est. Le discriminant est un **symbole PROPRE au correctif**,
grepé dans `frida/dist/hooks.js` — jamais un nom de champ, qui préexiste au correctif.

| résidu | discriminant grepé | dans le bundle | verdict |
|---|---|---:|---|
| `#340-r2` | `fieldOffsetOr` (le helper INTRODUIT par le correctif) | **21 lignes** | déjà déployé |
| `#368-r1` | `includeInactive` dans le corps de `tileMeta` | **oui** | déjà déployé |
| `#350-r3c` | `nullUnitPosition` / `machine:NullPosition` | **4 / 3 lignes** | déjà déployé |
| MoW-stats (sans numéro) | filtre `EntityType.Machine` de `combatSnapshot`/`statModSources` | oui | déjà déployé |
| `#287-r10-r1` | `InFogOfWarBrokenTargetingRule` | **0** | **manque** |

⚠ **`tilesMovedThisBattle` PRÉSENT dans le bundle ne prouvait RIEN** — le nom du champ existait
avant `#340-r2`, seul le helper `fieldOffsetOr` signe le correctif. C'est la forme générale :
le discriminant d'un correctif est ce que le correctif **AJOUTE**, pas ce qu'il **corrige**.

Chacune des quatre lignes déjà déployées a été **confrontée LIVE**, pas déduite du grep :

* **`#340-r2`** — `python -m pytest tests/engine/test_actorstats_sensor_live.py` : **13 passed,
  0 xfailed**. La garde est tri-état ; elle prend désormais la branche POST-correctif, donc
  `+0xec` cumule le pas et ignore le reset, et `+0xf4` prend `+0xf0` au reset. Et les noms se
  lisent enfin : `ActorStatisticsComponent` porte `TotalTilesMoved@0xec`,
  `TilesMovedThisTurn@0xf0`, `TilesMovedLastOwnTurn@0xf4` — deux des trois noms écrits dans le
  hook (`TilesMovedThisBattle`, `TilesMovedLastTurn`) **n'existent pas**, donc le repli
  décompilé s'applique, et il est juste.
* **`#350-r3c`** — `python probe_360_mow_caster_oracle.py --step a` : les trois oracles partent
  de `posSrc = machine:NullPosition`, `aiPlaybookPredict` rend `count=1 listNull=False` (au lieu
  de `-1`/`true`) et **égale** `ncPlaybookPredict` ; `build_machine` rend
  `ctx.me = blackForgefiend`. Une MoW est CASTER, sans greffe.
* **MoW-stats** — `combatSnapshot.units` contient `entityId=81 entityType=6` avec ses stats, et
  `statModSources.units` porte `entityType ∈ {1, 6}`. Les deux filtres étaient déjà élargis.
* **`#368-r1`** — mesure au §3.

---

## 2. `#448-r2b-r1-r1` — ce n'était pas un capteur, c'était le MONTAGE

La ligne disait : « `decisionView` est rendu du point de vue du player **ATTACHÉ**, pas du joueur
courant ; ni `endturn` ni `attach --team 2` ne donnent l'énumération de cibles ADVERSE ».

**L'énoncé est FAUX, et le décompilé le dit.** `computeAttackPlans`
(`frida/hooks/features/ai-step/projection.ts`) partitionne les entités par
`IdunBattle.Entities.UnitExtensions$$IsControlledByCurrentPlayer`, dont le corps entier est

    OwnerComponent.get_CurrentPlayerEntityId(unit) == TurnComponent.get_CurrentPlayerId(state)

— le joueur **DU TOUR**, jamais un joueur « attaché ». `attach --team 2` n'y change rien dans un
sens comme dans l'autre.

Ce qui bloquait : `act endturn` **ne flippe pas toujours** le joueur courant (quirk H19 — le
premier rend la preview IA ; `rl_duel._enemy_turn` porte déjà le garde-fou). La vue restait sur
MON tour, et les deux bras rendaient MES cibles — d'où le `{81, 83}` cité par la ligne.

`probe_448_r2b_r1_fear_untargetable.py` re-`endturn` désormais jusqu'au flip (et **REFUSE** de
mesurer s'il n'a pas lieu). Mesure :

| bras | cibles énumérées par l'adversaire | porteur dedans ? |
|---|---|---|
| TÉMOIN (pas de cast) | `[77, 79]` | **oui** |
| CAST (`1115 FearOfTheUnseen`) | `[79]` | **non** |

L'inscription de `1238` dans `UNTARGETABLE_EFFECT_TYPES`, gardée OFFLINE depuis `#448-r2b-r1`,
est **CONFRONTÉE LIVE**. Contre-épreuve intégrée : `--mutate-un-seul-endturn` rejoue le montage
d'avant et rend `currentPlayer=3` avec `[81, 83]` sur les DEUX bras — exactement le faux négatif
qui avait fait écrire « il manque un point d'observation ».

---

## 3. `#368-r1` — tranché LIVE, et l'hypothèse de substrat est RÉFUTÉE

`case-368` §3 laissait deux lectures : la tuile non marchable n'est *jamais soumise* (alors
`StateExtensions$$GetTileAt` ne l'inscrirait pas dans `BoardComponent+0x18`, et c'est le substrat
`board.id_at` du port qu'il faudrait corriger), ou elle est *posée puis désactivée*.

`probe_368_daemonic_ordnance_pose.py --pose --only D` relit désormais
`tileMeta(includeInactive=True)` **après** le cast. Bras D, `MC1_67`, caster MoW
`blackForgefiend`, ancre `(0,7)`, les trois tuiles du triangle à la MÊME élévation :

| tuile | marchable | terrain | `Fire` publié |
|---|---|---|---|
| `(0,7)` | oui | Grass | `active: True`, `remaining: 4` |
| `(1,8)` | oui | Grass | `active: True`, `remaining: 4` |
| **`(0,8)`** | **non** | Block | **`active: False`, `remaining: 4`** |

⇒ **l'effet EST posé sur la tuile non marchable, puis DÉSACTIVÉ.** Le sélecteur la retient,
`GetTileAt` la rend, `AddEffectOperation` la sert : le substrat du port est exact et il n'y a
rien à corriger dans `daemonic_ordnance_target_area_tiles`. Le refus vit dans
`IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` → l'`ActiveCondition` de l'effet
(slot `+0x518` de `BaseEffect`), **non portée** — résidu **`#368-r2`**.

La question reste GÉNÉRALE (tout effet de tuile), et l'écart reste INERTE sur les deux faces pour
la raison déjà écrite : aucune unité ne peut occuper une tuile non marchable.

---

## 4. Les TROIS capteurs écrits ici

### 4.1 `#175-r` — `tileMeta` : la porte et l'occupant power-up

Les deux feuilles restantes lisent des composants qu'aucun RPC ne remontait. Les deux `$$IsActivationTile`
— `IdunBattle.AI.Utilities.SummonDislikeDoorOpeningUtility$$IsActivationTile` et
`IdunBattle.AI.Utilities.HeroDoorOpeningUtility$$IsActivationTile` — ont le **même corps** :

    TryGetComponent<DoorActivationComponent>(tile)                     -> sinon false
    porte = state.GetEntity(DoorActivationComponent.DoorTileId @+0x10)
    TryGetComponent<DoorComponent>(porte)                              -> sinon false
    return DoorComponent.IsOpen @+0x18 == 0                            // porte FERMÉE

Les deux composants sont portés par des entités **TUILE** (mesuré sur `C6_09`, 3 portes) :
`DoorComponent{ActivationTiles(List<BEntityId>)@0x10, IsOpen@0x18}` et
`DoorActivationComponent{DoorTileId@0x10}`.

`PowerUp(26)` :
`IdunBattle.AI.Utilities.PowerUpTileUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext` fait
`UnitExtensions$$GetUnit(case.MovementTile.MainTile, state)` puis `UnitExtensions$$IsPowerUp`.
Ce dernier n'est **pas** un trait : il itère `StaticBattleRules.TriggeredAbility$$GetPowerUps()`
et teste `TriggeredAbilityComponent$$TryGetAbility` — donc **INVOQUÉ**, jamais re-dérivé.

⚠ **`GetUnit` a TROIS surcharges d'arité 2** (`IEntity` / `FootEntity` / `TileEntity`, lues dans
`data/symbols/<build>/frida/methods.tsv`). `findMethodByParamCount` en rendrait une au hasard, et
deux des trois ne prennent pas une tuile : la résolution passe par
`findMethodByParamClasses(..., ["TileEntity", null])`. Le cliquet §5 garde ce point.

`tileMeta` publie en plus `roomTileType` et `isInFog`, que `projectMatchState` PROJETAIT déjà
sans les publier, et trois drapeaux tri-état (`doorMeasured`, `occupantMeasured`,
`powerUpMeasured`) : sans eux, `door: null` partout ne distingue pas « ce board n'a pas de porte »
de « la classe n'est pas résolue ».

### 4.2 `#231-r` — `effectsAll` : les entités-effet HORS de la liste possédée

Le décompilé tranche la moitié du problème :

* `IdunBattle.Operations.AddEffectOperation$$AddNewEffect` écrit `EffectComponent.OwnerId@+0x14`
  puis fait `List.Add` sur l'`EffectsOwnedComponent` de **cette même entité** — inconditionnellement.
  Un effet POSÉ est donc, à la pose, dans la liste de son owner ;
* `IdunBattle.Operations.RemoveEffectOperation$$Execute` fait `List.Remove`, pose
  `BeingRemoved@+0x5e` puis `Removed@+0x5f`, et **ne détruit pas l'entité**.

Trois régimes, trois signatures, qu'aucun canal existant ne séparait (`decisionView` et `tileMeta`
partent tous deux de `ActiveEffectIds`, et `includeInactive` ne desserre que `IsActive`) :

| observation | régime |
|---|---|
| l'entité n'apparaît pas | **JAMAIS POSÉ** (gate d'`AddEffectOperation`) |
| `inOwnerList: false, removed: true` | **POSÉ PUIS RETIRÉ** |
| `inOwnerList: false, removed: false` | **ORPHELIN** — vivant hors de la liste |

`readAllEffects` (`frida/hooks/game/effects.ts`) énumère `EntityType.Effect` et publie, en plus
de l'`EffectInfo` existant : `ownerId`, `ownerType`, `inOwnerList`, `hasTurns`, `initialTurns`,
`beingRemoved`, `timesApplied`, `parentEffect`, `subEffects`. Le RPC `effectsAll` ventile
`orphanCount` / `removedCount` — un `count: 0` doit dire de quoi il est le zéro.

Pour le cas d'origine (`1197 EffectType.MasterOfTheTutelaries`), la **durée est lue** :
`…MasterOfTheTutelariesAbility$$ExecuteBehaviour` passe à `DSLBehaviors$$AddEffect` le nœud
`<DSLFormulas>+0x20`, et `IdunBattleLogic.Entities.DSLFormulas$$.ctor` construit ce slot avec le
littéral **1** (la table est `+0x18 → 0 · +0x20 → 1 · +0x28 → 2 · +0x30 → 100 · +0x38 → -1`).
Owner et cible sont tous deux `DSLSelectors+0x48` = **Caster**, donc une Unit : l'hypothèse
« vivant hors de la liste » ne peut se réaliser que par un owner d'un autre `EntityType`, et
c'est le capteur qui le dira.

### 4.3 `#347-r1` — `actorStats[].movement`

⚠ **`case-347` §8 nomme le mauvais composant.** Sur `rnca9r7q6c`, `UnitComponent+0x98` est
`PendingHit`. Les quatre `Nullable<UnitPositionId>` vivent sur
**`IdunBattle.Entities.Components.MovementComponent`** :

    TurnStartPosition @+0x78 · PreviousPosition @+0x88 ·
    PreviousPositionThisTurn @+0x98 · PendingPosition @+0xa8

et c'est bien `+0x98` que lit `IdunBattle.Entities.EntityExtensions$$GetPreviousPositionThisTurn`,
qu'écrit `IdunBattle.Operations.SetUnitPositionOperation$$SavePreviousPosition` et que remet à
zéro `IdunBattle.Entities.Behaviours.ResetPreviousPositionBehaviour$$Execute`. L'offset coïncide,
le COMPOSANT non — un capteur écrit sur la foi de la fiche aurait lu `PendingHit` sans lever.

`Nullable<UnitPositionId>` = 16 octets : la valeur (`UnitPositionId`, 8 o = un `List<BEntityId>` —
`classes.tsv` publie 24, taille BOXÉE) puis `hasValue` à `+8`. Décodage : `hasValue` lu au champ,
puis `IdunBattle.Core.UnitPositionIdExtensions$$ToTileList(positionId, state)` **INVOQUÉ** (valeur
passée par pointeur, convention value-type d'`il2cpp_runtime_invoke`), puis `extractTiles`.

Le capteur publie les **quatre** champs et un `movementLayout` tri-état. Il débloque aussi
`#462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r1` et `-r5-r2`, qui nomment eux aussi
`PositionComponent+0x88/+0x98` (même mislabel de composant) et attendaient exactement ce canal.

---

## 5. Le cliquet, et pourquoi il est OFFLINE

Un capteur livré AVANT sa fenêtre n'est confronté par RIEN d'ici là : un rebase, une
régénération de table ou un renommage peut le vider en silence, et la fenêtre s'ouvrirait sur du
code qui publie `null` partout — ce qui se lit exactement comme « le régime n'existe pas ».

`probe_546_capteurs_fenetre_offline.py` (garde :
`scripts/python/tests/test_546_capteurs_fenetre_offline.py`, 10 tests) confronte les capteurs
ÉCRITS aux tables VERSIONNÉES du build, sans session. Cinq étapes, chacune avec son TÉMOIN, et
une PANNE si le témoin est vide.

L'étape 5 est celle qui ne se lit pas dans le texte : un capteur résout ses classes et ses
méthodes **par nom** au runtime, et un nom faux ne lève rien — il rend `null`. Elle confronte
donc chaque nom cité aux tables, **et l'arité ne suffit pas** (les trois `GetUnit`).

Cinq contre-épreuves, toutes vues ROUGES :

| mutation | étape qui rougit |
|---|---|
| ligne `InFogOfWarBrokenTargetingRule` retirée | 1 (et le décodeur Python la réclame) |
| `occupantIsPowerUp` retiré de la publication | 2 |
| `orphanCount` retiré | 3 |
| `PreviousPositionThisTurn` déplacé de `0x98` à `0x88` | 4 |
| `GetUnit` résolu par ARITÉ | 5 |

⚠ **La 2ᵉ mutation a d'abord laissé le cliquet VERT**, et c'est un enseignement : chaque clé
publiée est aussi CITÉE dans la docstring du RPC qui la publie, donc un balayage du fichier
ENTIER gardait la PROSE, pas le capteur. Les étapes 2 à 5 lisent depuis
`_code_seul()` (commentaires retirés).

---

## 6. Ce que le rebuild emportera, et la contre-épreuve de chacun

| # | ce qui s'active | contre-épreuve APRÈS la fenêtre | verdict attendu |
|---|---|---|---|
| `#287-r10-r1` | `NON_GENERIC_RULE_CODES.InFogOfWarBrokenTargetingRule = 1` | `python probe_287r10_fog_capteur_live.py` | `abilityReason` sur une tuile en brouillard rend `hex: "0x0000000000000001"` (plus `"0x0"`) avec `ruleClass: "InFogOfWarBrokenTargetingRule"` |
| `#175-r` | `tileMeta.tiles[].door` / `occupantId` / `occupantIsPowerUp` | `python rl_duel.py build --board C6_09 --state-file <abs>` puis `tileMeta` | `doorMeasured: true` ; **3** tuiles `isDoor` et **6** `isActivationTile` sur `C6_09` ; `isActivationTileOfClosedDoor: true` tant qu'aucune porte n'est ouverte |
| `#231-r` | RPC `effectsAll` | monter le cast de `1096` (`thousInfernalMaster`, cf. `case-231` §4) puis `effectsAll --effectType 1197` | l'un des trois régimes du §4.2 — et c'est LUI le résultat, pas un accord |
| `#347-r1` | `actorStats[].movement` | `python probe_347_tiles_moved_call_sites.py` + `actorStats` après un pas | `movementLayout.componentResolved: true` ; `previousPositionThisTurn.tiles` non nul après le premier pas du tour, `null` au tout début |
| — | le cliquet | `python scripts/python/probe_546_capteurs_fenetre_offline.py` | `0 ecart` — à rejouer APRÈS le rebuild, il ne dépend pas de la session |

**Ordre** : jouer `probe_546` AVANT la fenêtre (il dit si le code partira intact), puis les quatre
contre-épreuves APRÈS.

---

## 7. Ce qui n'est PAS couvert

* Les trois capteurs neufs ne sont **NON CONFRONTÉS** — ils n'existent pas dans le bundle chargé.
  Leur contrat est gardé statiquement (§5) ; leur VALEUR ne l'est pas.
* `#368-r2` (l'`ActiveCondition` d'un effet de tuile) n'est pas porté ; le port continue de
  marquer la tuile non marchable, et l'écart reste inerte pour la raison du §3.
* Le régime ORPHELIN de `#231-r` reste une hypothèse : le décompilé montre que la voie d'ajout ne
  peut pas le produire, mais il ne ferme pas les autres écrivains d'`ActiveEffectIds`.
* Trois rouges de `master` **hors périmètre**, une seule cause :
  `test_463r1_ecart_empreinte_offline.py`, `test_474_optional_locks_offline.py` et
  `test_486r15_empreinte_par_entree_offline.py` déclarent trop étroit — il leur manque
  `scripts/python/livraison.py`. Non touchés (trois familles distinctes, agents en vol).
