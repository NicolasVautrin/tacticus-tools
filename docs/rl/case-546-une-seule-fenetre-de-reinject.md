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

## 6. La fenêtre du 2026-08-08 — ce qu'elle a rendu

Session 3 (pid 74348), bundle frais chargé, amorce 8/8.

⚠ **Le grep du `dist/hooks.js` sur disque n'était PAS le bon critère cette fois non plus** : le
fichier a été reconstruit à 01:53:15, soit **après** l'injection de 23:56:30, et sa taille avait
changé. Ce qui prouve qu'un capteur est chargé, c'est **la session qui répond** : les trois RPC
appelés SANS runner rendent déjà leurs drapeaux (`doorMeasured/occupantMeasured/powerUpMeasured:
true`, `movementLayout.componentResolved: true`, `effectsAll` ventilé).

| # | contre-épreuve jouée | AVANT | APRÈS | verdict |
|---|---|---|---|---|
| `#287-r10-r1` | `probe_287r10_fog_capteur_live.py` (`C6_09`, 34 tuiles/63) | `hex='0x0'`, « MENT : OUI » | **`hex='0x0000000000000001'`, `reasons=['ValidRequest']`, « MENT : non »** | **FERMÉ** |
| `#175-r` | `build --board C6_09` + `tileMeta` | — | **3** `isDoor`, **6** `isActivationTile`, appariement croisé exact | **FERMÉ** |
| `#231-r` | cast `1096` + `effectsAll --effectType 1197` | absent des deux canaux | **id 98, `removed: True`, `initialTurns: 1`, `orphanCount: 0`** | **TRANCHÉ** |
| `#347-r1` | `actorStats` avant/après un pas | — | canal VERT, **décodage MUET** (`tiles: null`) | **OUVERT** → `#347-r3` |
| — | `probe_546_capteurs_fenetre_offline.py` | 0 écart | 0 écart | tenu |

### 6.1 `#175-r` — le témoin NON NUL, et c'est lui qui fait la preuve

3 portes / 6 activations, chaque activation pointant la bonne porte par `DoorTileId`, et
`roomTileType = 2` sur les trois portes — **un second canal, indépendant du capteur**, concorde.
L'appariement est identique, terme à terme, à `data/boards/global/C6_09.json` (source disque vs
ECS live).

Mais `isOpen: False` partout ne prouvait rien — un capteur qui rendrait `False` en toute
circonstance donnerait la même chose. **On ouvre donc une porte** : l'unité marche sur `(5,2)`.

| | porte `(3,1)` | porte `(5,3)` | porte `(5,6)` |
|---|---|---|---|
| avant | `isOpen: False` | `isOpen: False` | `isOpen: False` |
| après le pas sur `(5,2)` | `False` | **`True`** | `False` |
| prédicat de ses activations | `True, True` | **`False, False`** | `True, True` |

Les **deux** activations de la porte ouverte basculent `True → False`, les **quatre** autres ne
bougent pas. Le prédicat natif « tuile d'activation d'une porte FERMÉE » est donc reproduit, et
la propagation passe bien par `DoorTileId`.

`occupantId` suit le déplacement `(6,1) → (5,2)`, `occupantIsPowerUp: False`.

### 6.2 `#231-r` — le régime est **POSÉ PUIS RETIRÉ**, et il ferme la question du §4.2

Après le cast de `1096` par `thousInfernalMaster` :

```
effectType=1197 : count=1
  id=98 owner=81 ownerType=1 inOwnerList=False active=False removed=True beingRemoved=True
       hasTurns=True initial=1 remaining=0 timesApplied=1 parent=None subs=[] src=81
```

Les trois régimes du §4.2 se départagent sans ambiguïté :

* **jamais posé** → RÉFUTÉ : l'entité existe, et `timesApplied = 1` prouve que `ApplyInternal`
  a tourné (donc `AddTriggeredAbility(1173)` a bien eu lieu) ;
* **orphelin** → RÉFUTÉ : `orphanCount = 0` sur les 18 entités-effet du state ;
* **posé puis RETIRÉ** → **c'est celui-là** (`inOwnerList: False`, `removed`, `beingRemoved`).

⚠ **Et `initialTurns = 1` confirme au chiffre près une prédiction faite OFFLINE**, avant la
fenêtre : `…MasterOfTheTutelariesAbility$$ExecuteBehaviour` passe le nœud `<DSLFormulas>+0x20`,
que `IdunBattleLogic.Entities.DSLFormulas$$.ctor` construit avec le littéral **1**. La durée
n'était pas « non décodée » (`case-231` §7) — elle était lisible, et elle est juste.

**La conséquence, mesurée** : `unitAbilityStates` après le cast donne
`u81 triggered = [1170, 1161, 1013]` — **`1173` n'est sur AUCUNE unité**. La chaîne native est
donc entière : pose → `ApplyInternal` → `AddTriggeredAbility(1173)` → durée épuisée → retrait →
`RevertInternal` → `RemoveTriggeredAbility`. Le port, lui, **garde `1173` collectée tour après
tour** : c'est une divergence, et c'est exactement ce que `#231-r` demandait de trancher.
Résidu **`#231-r1`**.

### 6.3 `#347-r1` — le canal est VERT, le DÉCODAGE est muet

Ce qui marche, et qui est le cran principal :

| | u81 (bouge) | u83 (ne bouge pas) |
|---|---|---|
| début de tour | `previousPositionThisTurn: null` | `null` |
| après le 1er pas | **`{...}`** (non nul) | **`null`** |

`hasValue` discrimine donc, et `movementLayout` rend `componentResolved: true`,
`toTileListResolved: true`, avec les quatre offsets **résolus PAR NOM** égaux aux replis
décompilés (`0x78 / 0x88 / 0x98 / 0xa8`) — confirmation indépendante que le composant est bien
`MovementComponent`.

Ce qui ne marche pas : **`tiles: null` sur les quatre champs**. Le décodage est muet.

⚠ **Et la transition ne discrimine PAS la cause** — c'est le point qui compte.
`frida/hooks/game/match-state.ts` a déjà mesuré sur ce build que le `Nullable<T>` d'IL2CPP met
**`hasValue` EN PREMIER** (`MachinePlatformComponent` : « hasValue @+0, value @+4 »). Sous cette
disposition, l'octet lu à `off + 8` est l'octet de poids faible du **pointeur de liste** — nul
quand le champ est vide, non nul quand la liste existe. **Le drapeau « marche » par accident**, et
l'adresse passée à `ToTileList` désigne le drapeau au lieu de la valeur. Les deux dispositions
expliquent exactement la même transition ; aucune mesure de terrain ne les sépare.

**Ce n'était pas la seule faute, et l'autre est la mienne** : le capteur rendait `{tiles: null}`
pour **quatre** causes distinctes (méthode non résolue, invocation levée, liste nulle, disposition
fausse). La mesure disait « muet » sans dire de quoi — le défaut de tri-état que ce dépôt reproche
partout ailleurs.

### 6.4 L'hypothèse est CONFIRMÉE par un autre agent, sur un autre foyer — et la parade existait

En cherchant à réparer, le travail de **`#579-r1`** est apparu dans la sélection de `probe_457` :
`readAbilityState` (`internals.ts`) avait **exactement** le même défaut, mesuré le 2026-08-04 —
il lisait les `Nullable<int>` d'`ActiveAbility` à `{ value @+0 ; hasValue @+4 }`, et deux casts
d'une même bataille publiaient tous deux `unresetedLastTurnUsed = 1`, ce qu'un compteur
**monotone** ne peut pas faire : le `1` publié était le bit `hasValue`. Sa conclusion, lue dans
les métadonnées ET au décompilé : **`System.Nullable\`1` déclare `hasValue` PUIS `value`**.

Deux voies indépendantes, deux foyers différents, la même disposition. Et la même signature :
« les prédicats de PRÉSENCE coïncidaient par accident » — mot pour mot le « le drapeau marche par
accident » du §6.3.

⚠ **Corollaire, et c'est une faute que j'ai commise avant de la voir** : `#579-r1` avait déjà posé
la parade — un `nullableLayoutOf` par réflexion dans `internals.ts`. Ma première réparation en a
écrit une **SECONDE copie**, homonyme, dans `rpc-snapshot.ts`. C'est le patron que `case-287-r12` a
eu à défaire en **trois** exemplaires, et il se recrée par imitation. La copie est retirée, la
fonction d'`internals.ts` est **exportée**, et le cliquet garde les deux crans : `function
nullableLayoutOf` interdit dans `rpc-snapshot.ts`, `export function nullableLayoutOf` exigé dans
`internals.ts`.

Le correctif ne CHOISIT donc pas la disposition, il la **LIT** — comme le natif, qui calcule
l'adresse de `hasValue` depuis les métadonnées. S'y ajoutent les **16 octets bruts** publiés quoi
qu'il arrive (la seule donnée qui survive à une erreur de disposition, donc la seule qui permette
de la corriger sans réinjecter) et la **cause** nommée (`layout-not-derived` /
`hasValue-unreadable` / `no-ToTileList` / `null-list` / `threw` / `ok`).

---

## 7. Ce qui n'est PAS couvert

* **Le témoin POSITIF d'`occupantIsPowerUp` manque** : aucun power-up n'existe dans un runner
  PvP, donc le champ n'a été vu qu'à `False`. Ce n'est pas un trou de port —
  `UnitExtensions$$IsPowerUp` est **INVOQUÉ**, il n'y a aucun mirror à valider — mais l'axe
  n'a pas de contre-épreuve, et il faut le dire. Le témoin de la PORTE, lui, est non nul (§6.1).
* **`#347-r1` reste OUVERT** : le lift-off de `TheQuickening` exige les TUILES de
  `movementStartPosition`, donc il attend `#347-r3`.
* **La fenêtre temporelle « pendant le cast » de `1197` n'est pas observée** : le relevé du §6.2
  est POST-cast. Dans ce montage un seul Pink Horror apparaît (les ennemis sont hors de portée) —
  la cascade à 4 Screamers de `case-231` §4 n'a pas eu lieu. La conclusion ne s'appuie pas
  dessus : elle est lue sur les composants (`timesApplied`, `removed`, `initialTurns`).
* `#368-r2` (l'`ActiveCondition` d'un effet de tuile) n'est pas porté ; le port continue de
  marquer la tuile non marchable, et l'écart reste inerte pour la raison du §3.
* Le régime ORPHELIN de `#231-r` reste une hypothèse : le décompilé montre que la voie d'ajout ne
  peut pas le produire, mais il ne ferme pas les autres écrivains d'`ActiveEffectIds`.
* **Un rouge de `master` réparé dans le périmètre, un autre qui l'était déjà.**
  `test_175e_175r_tile_meta_live.py` (famille `#175-r`) déclarait `DECLENCHEUR` **sans** `build`
  ni `toujours` : `probe_486r15_declencheurs_tests` rendait « declaration MAL FORMEE ». En le
  réparant, une **seconde** faute est apparue sur le même fichier — six chemins de la fermeture
  d'imports non déclarés —, invisible tant que la première tenait : **le cliquet s'arrête à la
  déclaration MAL FORMÉE et ne confronte le PÉRIMÈTRE qu'ensuite**. `#486-r29` a réparé les deux
  en parallèle sur `master` ; le rebase a produit le conflit et c'est la version de `master` qui
  est retenue. Les trois autres rouges observés en cours de tranche
  (`test_463r1` / `test_474` / `test_486r15_empreinte_par_entree`, tous « il manque
  `scripts/python/livraison.py` ») sont fermés par le même commit : après rebase,
  `probe_486r15_declencheurs_tests` rend **PASS**.
