# #596 — Jouer la bataille RÉELLE par le FSM, en donnant l'ENTITÉ au lieu d'un pixel

## ✅ RÉSOLU (2026-08-08, session 8) — LIRE CECI D'ABORD

**Composer l'équipe et mener la bataille sans présélection ni souris est ACQUIS.** Le verbe
est `IdunBattle.View.FSM.StateMachineActions$$UnitDeployment_PlaceUnitOnBoard` :

```
fsmStateInvoke({target: "_actions._hud._menuSystems.unitDeploymentHud.Get()",
                method: "HandleOnRemoveAllHeroesPressed"})          # vider d'abord
fsmStateInvoke({target: "_actions", method: "UnitDeployment_PlaceUnitOnBoard",
                args: [unitId, col, row, true, 11]})                # puis poser
```

Cinq héros posés, bataille lancée, chaque unité mesurée sur **l'hex demandé** — puis un
déplacement joué (`mutated: true`). Tout le reste de cette fiche est le chemin qui y mène, y
compris trois hypothèses réfutées. Détail et chiffres : dernière section.

Mesuré le 2026-08-08, build `rnca9r7q6c`. Le déclencheur : composer soi-même l'équipe de
déploiement, geste que l'utilisateur décrit comme « cliquer une fois sur le portrait, puis
sur l'hex de spawn ». La première moitié passe par l'UI ; **la seconde vise le plateau, qui
n'a aucun `Button`**.

## Ce qui a été établi

**Le raycast n'est PAS dans le FSM.** Il vit dans `IdunBattle.View.Game.InputEntityAdapter`
(`GetEntityAtObject`, `GetTileAtObject`), qui appelle le FSM avec les entités **déjà
résolues** — signatures lues au décompilé :

```
IdunBattle.View.FSM.UnitSelectionFsm$$HandleMouseButtonDownThisFrame(this, mousePosition, entity)
IdunBattle.View.FSM.UnitSelectionFsm$$HandleMouseButtonUpThisFrame  (this, mousePosition, entityHit, tileHit)
IdunBattle.View.FSM.BaseSelectionState$$OnFingerDownThisFrame       (this, mousePosition, entityHit)
```

`HandleMouseButtonUpThisFrame` est un **dispatcher pur** : l'état courant est en `fsm+0x10`,
`mousePosition` (Vector3) est seulement RECOPIÉE dans un local, puis le slot d'interface est
appelé avec `(état, &pos, entityHit, tileHit, methodInfo)`. Aucune projection, aucune caméra.

⇒ **On peut désigner la tuile SOI-MÊME.** Pas de coordonnées écran, pas de souris, pas de
`WorldToScreenPoint` — donc `#595-r2` (position d'écran non établie) n'est PAS un préalable.

**Et `mousePosition` n'a probablement pas à être juste** : `IdunBattle.View.FSM.TouchInformation`
n'expose que `ShouldMoveCamera` / `ShouldMoveCameraWithScrollWheel`, donc la position sert à
distinguer un TAP d'un SWIPE. Passer la MÊME valeur au down et au up est un tap propre.
⚠ Hypothèse non confrontée — à vérifier avant de s'en servir, pas à recopier.

## L'étage du déploiement, nommé

`IdunBattle.View.FSM.UnitDeployment.UnitDeploymentState` porte le geste en toutes lettres :

| natif | ce que c'est |
|---|---|
| `OnUnitInHand(this, unitId, isMachineOfWar)` | le clic sur le portrait |
| `OnFingerDownThisFrameInternal(this, mousePosition, entityHit)` | le clic sur l'hex |
| `RemoveUnit(this, unitId)` / `RemoveAllDeployedUnits(this)` | le bouton `Clear` |
| `StartBattle(this, units)` | le bouton `Start!` |

La classe imbriquée `UnitDeploymentState.CurrentlySelectUnit` matérialise l'unité « en main ».

## Ce que ça ouvre, au-delà du déploiement

Le même FSM porte **toute la conduite manuelle** d'un tour : `NothingSelected.NormalState` →
`OwnUnit_didntMove_didntAttack.FingerDownOnUnitForFirstTime` → `MovementSuggestionState` →
`MovementTargetSelectedState` → `Swipe_AttackTargetSelected`, plus `InspectTileState`,
`MachineSelection.*`, `AiTurnState`, `MatchEndedState`. Une entrée par entité les atteint tous.

## LIVRÉ ET CONFRONTÉ (2026-08-08, session 7)

`frida/hooks/features/fsm-input.ts` — cinq RPC, aucune ne connaît le déploiement :

| RPC | état |
|---|---|
| `fsmStatus` | ✅ `captures:1`, `etatCourant:"UnitDeploymentState"`, `matchState` du FSM == celui du runner live |
| `fsmStateMethods` | ✅ rend les **12 méthodes** de l'état courant **avec leurs types** |
| `fsmStateInvoke` | ✅ `RemoveAllDeployedUnits()`, `RemoveUnit("bloodDante")`, `OnUnitInHand(null,false)` |
| `fsmInput` | ✅ s'exécute (`down`/`up`), n'a pas fait tomber le jeu |
| `fsmTap` | ✅ s'exécute ; ⚠ **aucun effet observé** sur une tuile de spawn |

**La capture à la construction tient** : `.ctor` fire à l'entrée en bataille, et la garde de
péremption (matchState du FSM confronté à celui du runner live) est passée verte, avec le refus
nommé quand elle ne l'est pas.

## `this+0x18` IDENTIFIÉ — et le blocage restant est NOMMÉ

Lu sur la classe VIVANTE (`classFields`), pas déduit. `UnitDeploymentState` (0x58 octets)
hérite toute sa couche de services de `BaseSelectionState` :

| offset | champ | type |
|---|---|---|
| `+0x10` | `_stateChanger` | `IUnitSelectionFsmStateChanger` |
| **`+0x18`** | **`_actions`** | **`IStateMachineActions`** |
| `+0x20` | `_state` | `IMatchState` |
| `+0x28` | `_visualBattleQuery` | `IVisualBattleQuery` |
| `+0x30` | `_timeQuery` | `ITimeQuery` |
| `+0x38` | `TouchInformation` | `ITouchInformation` |
| `+0x40` | `_isMovingCamera` | `Boolean` |
| `+0x48` | `_currentlySelectedUnit` | `CurrentlySelectUnit` |
| `+0x50` | `_enemySelected` | `IEntity` |

Cette table confirme les trois lectures du décompilé : `+0x38` est bien le service appelé avec
`mousePosition` par `BaseSelectionState.OnFingerDownThisFrame` ; `+0x50` est bien ce que
`OnFingerDownThisFrameInternal` compare à `entityHit` ; et `+0x48` est le `CurrentlySelectUnit`
dont `OnUnitInHand` écrit l'id en `+0x10` et le booléen en `+0x18`.

`IStateMachineActions` porte **131** méthodes, dont le vocabulaire exact du déploiement :
`UnitDeployment_PutUnitIntoHand(String)`, `UnitDeployment_TryRemoveUnitFromBoard(String)`,
`UnitDeployment_ShowUnitInfoBarHud(String)`, `CreateVisualUnitDataForDeployment(String)`.

⚠ **LE BLOCAGE N'EST NI L'ID NI LE CHEMIN D'APPEL — C'EST LA CRÉATION DU VISUEL.** Mesuré via
`fsmStateInvoke({target: "_actions", ...})`, qui atteint le service directement :

| appel | verdict |
|---|---|
| `UnitDeployment_TryRemoveUnitFromBoard("bloodDante")` | **ok** |
| `UnitDeployment_TryRemoveUnitFromBoard("zzIdQuiNexistePas")` | **ok** |
| `UnitDeployment_PutUnitIntoHand("zzIdQuiNexistePas")` | **ok** |
| `UnitDeployment_PutUnitIntoHand("bloodDante")` | **`system error`** |
| `UnitDeployment_ShowUnitInfoBarHud("bloodDante")` | **`system error`** |
| `CreateVisualUnitDataForDeployment("bloodDante")` | **`system error`** |

C'est l'id **RÉEL** qui faute, l'id **BIDON** qui passe : un id inconnu sort tôt sans rien
faire, un id connu descend dans la construction du visuel — et c'est là que ça casse. Le
chemin d'appel est donc DÉMONTRÉ bon (un vrai appel d'interface avec une vraie chaîne
managée réussit), et la forme de l'id aussi.

⚠ **La piste « session froide » est MORTE, et pas pour la raison que j'avançais.** J'écrivais
« à rejouer sur une session warmée » ; c'est sans objet — **l'amorce FAIT exactement ce que
cette mise au point fait déjà** : ouvrir une bataille de campagne, capturer, se retirer. Ce
cycle a été rejoué une dizaine de fois à la main ici. Il n'y a rien de froid à réchauffer.

## LA FAUTE, LOCALISÉE À TROIS ÉTAGES

Les deux méthodes de `StateMachineActions` sont de simples **relais**, et vers des champs
DIFFÉRENTS — d'où le contraste :

```
UnitDeployment_TryRemoveUnitFromBoard -> this+0x18 = _views : IIdunGameViews   -> OK
UnitDeployment_PutUnitIntoHand        -> this+0x48 = _hud   : IIdunGameHud     -> FAUTE
```

`ShowUnitInfoBarHud` faute aussi : **les deux méthodes HUD tombent, la méthode `views` passe.**

⚠ **`_hud` n'est PAS nul** — sondé par la traversée `target: "_actions._hud"`, il rend un
`IdunGameHud` vivant. L'hypothèse `NullReferenceException` sur le garde
`if (this+0x48 != 0)` est donc **réfutée**. La chaîne complète est :

```
UnitDeploymentState.OnUnitInHand(unitId, isMoW)
  -> _actions : StateMachineActions .UnitDeployment_PutUnitIntoHand(unitId)
       -> _hud : IdunGameHud .UnitDeployment_PutIntoHand(unitId)      <-- FAUTE ICI
```

Appelé DIRECTEMENT sur `_actions._hud`, `UnitDeployment_PutIntoHand("bloodDante")` faute de la
même façon : le défaut est bien dans cette méthode, pas dans le relais.

⚠ **`fsmStateInvoke` PUBLIE la valeur de retour — et le no-op silencieux était un REFUS.**
`fsmStateInvoke` la jetait ; « a refusé » et « a marché » étaient donc indiscernables, le vice
exact qu'on reproche à `uiClick`, reproduit dans notre propre outil. Une fois publiée :

| appel | retour |
|---|---|
| `IdunGameHud.UnitDeployment_TryPlaceUnitOnBoard("bloodDante", false)` | **`Boolean false`** |
| `…TryPlaceUnitOnBoard("zzBidon", false)` | `Boolean false` |
| `UnitDeploymentState.RemoveAllDeployedUnits()` | `Void null` (témoin de décodage) |

La pose **refuse**, elle n'échoue pas silencieusement. Cohérent avec l'alignement PLEIN
(`PlayerPower` 1912587, 5/5) et avec le fait que `PutIntoHand` — l'étape qui libère la pose —
est justement celle qui faute.

## ✅ L'ÉQUIPE SE COMPOSE — `TryPlaceUnitOnBoard` SUFFIT, `PutIntoHand` EST INUTILE

Le `false` n'était **que** l'alignement plein. Vidé par le bouton `Clear` (prouvé par le
témoin : `PlayerPower` 1912587 → 0), la même pose rend **`true`** :

| unité | posée | `PlayerPower` |
|---|---|---|
| `bloodDante` | `true` | 453 134 |
| `ultraTitus` | `true` | 661 343 |
| `custoTrajann` | `true` | 1 004 555 |
| `templHelbrecht` | `true` | 1 392 041 |
| `astraYarrick` | `true` | 1 708 392 |
| `admecDominus` | **`false`** | inchangé — plafond de 5 |
| `bloodMephiston` | **`false`** | inchangé |

⇒ **Composer l'équipe soi-même est ACQUIS**, sans présélection, sans souris, sans UI (hors le
`Clear`). L'appel est
`fsmStateInvoke({target: "_actions._hud", method: "UnitDeployment_TryPlaceUnitOnBoard",
args: ["<unitId>", false]})`.

⚠ **Et `PutIntoHand` n'est PAS sur le chemin.** Il faute toujours (id réel), mais il ne sert
qu'à l'étape visuelle « unité en main » du geste HUMAIN — le portrait qu'on traîne. La pose
directe ne passe pas par lui. Une panne qu'on croyait bloquante ne l'était pas : c'est la
DEUXIÈME fois dans cette fiche qu'un verrou supposé se dissout (après « le roster est
tronqué »).

⚠ **Les unités du joueur ne sont TOUJOURS PAS des entités ECS en `Setup`** : `observeBattle`
reste à 12 unités, toutes ennemies, alors que cinq héros sont bel et bien dans l'alignement.
Le témoin de composition est `PlayerPower`, pas l'ECS.

⚠ **ET LE PLATEAU NE SE MET PAS À JOUR — LE NOM NATIF LE DIT.** `IdunGameHud` n'est qu'un
relais ; les deux méthodes descendent dans `idun.ui.UnitDeploymentHud` :

```
IdunGameHud.UnitDeployment_TryPlaceUnitOnBoard -> UnitDeploymentHud.TryMarkUnitAsPlaced   OK
IdunGameHud.UnitDeployment_PutIntoHand         -> UnitDeploymentHud.PutUnitIntoHand       FAUTE
```

`TryMarkUnitAsPlaced` **MARQUE** l'unité comme placée dans le HUD — il ne la pose pas. D'où
un alignement juste (`PlayerPower` monte, `Start!` s'active) et un plateau vide. Le nom seul
suffisait à le prévoir : c'est le genre de chose qu'on ne voit qu'en lisant le symbole plutôt
qu'en jugeant sur l'effet du premier appel qui rend `true`.

La vraie pose est ailleurs sur la même classe, dont l'inventaire donne tout le vocabulaire du
geste : **`EmptySpawnPointTapped()`** (le clic sur l'hex libre), `HandleOnUnitTapped(widget,
unit)`, `HandleOnUnitInHandTapped(widget, unit)`, `HasUnitInHand() -> Boolean` (le témoin
manquant), `HandleOnRemoveAllHeroesPressed()` (= `Clear`),
`HandleOnStartBattleTapped(Boolean)` (= `Start!`), `GetPlayerPower() -> Int32`.

## LE SEGMENT APPELANT — `target` traverse par APPEL, et le HUD est atteint

`IdunGameHud._menuSystems` (`+0x1a8`, `thor.Menu.MenuSystems`) `+0x188` est
`unitDeploymentHud : IMenu<UnitDeploymentHud>` — un **wrapper**. Un segment `nom()` appelle
donc une méthode sans paramètre et continue sur son résultat :

```
target: "_actions._hud._menuSystems.unitDeploymentHud.Get()"   ->  UnitDeploymentHud (122 methodes)
```

⚠ **La sélection se fait par ARITÉ, pas par nom — et c'est mesuré, pas prudentiel.**
`Menu<T>` porte DEUX `Get` (`Get()` et `Get(Transform)`), et `findMethod` rend la PREMIÈRE :
la mauvaise. Le garde d'arité a refusé au lieu de mal appeler (« la methode prend 1
parametre(s) »), et `findMethodByParamCount(klass, nom, 0)` l'a réparé. Un segment appelant
qui rendrait un TYPE VALEUR est refusé aussi : on ne traverse pas une boîte.

⚠ **`fsmStateMethods` prend le MÊME `target`.** Sans ça, on ne pourrait pas DÉCOUVRIR le nom
à appeler sur un objet qu'on vient d'atteindre — un chemin appelant se réduirait à deviner un
accesseur. C'est ainsi que `Get()` a été trouvé, pas supposé.

## CE QUE ÇA A OUVERT, ET LE MUR QUI RESTE

Deux **témoins natifs** remplacent enfin les libellés d'UI : `GetPlayerPower() -> Int32` et
`HasUnitInHand() -> Boolean`.

| appel sur `UnitDeploymentHud` | effet mesuré |
|---|---|
| `HandleOnRemoveAllHeroesPressed()` | ✅ `GetPlayerPower()` 1912587 → **0** |
| `PutUnitIntoHand("bloodDante")` | ⚠ **faute — ET exécute quand même** : `HasUnitInHand()` False → **True** |
| `EmptySpawnPointTapped()` | s'exécute, aucun effet |
| `fsmTap` sur un spawn libre, unité EN MAIN | aucun effet |

⚠ **`PutUnitIntoHand` est une TROISIÈME occurrence du handler PARTIELLEMENT exécuté** (après
le `onClick.Invoke threw` du portrait qui montait quand même le `PreviewContainer`). Il faute,
et il met malgré tout l'unité en main. Un échec rapporté n'est donc pas un échec réel — ici
c'est même l'inverse du besoin : c'est en fautant qu'il fait ce qu'on lui demande.

⚠ **`EmptySpawnPointTapped()` ne prend AUCUN paramètre** : c'est une NOTIFICATION émise par la
vue du point de spawn, pas une commande de pose. Appelée à nu, elle n'a aucun hex à viser.
C'est pourquoi elle ne fait rien, et ce n'est pas une panne.

## LA TRACE D'INPUT — CE QUE LE JEU PASSE VRAIMENT (clic HUMAIN)

`fsmTrace` hooke les DEUX entrées du FSM (`Down` n'a qu'une entité, `Up` a le couple
`entityHit`/`tileHit` — la distinction en cause). Un clic humain sur l'hex de spawn `(0,1)` :

```
down  etat=UnitDeploymentState  pos=[231, 1043, 0]   entity = TileEntity id=13  hex (0,1)
up    etat=UnitDeploymentState  pos=[231, 1043, 0]   entity = TileEntity id=13
                                                     tile   = TileEntity id=13
```

⚠ **DEUX HYPOTHÈSES TOMBENT D'UN COUP.**
1. « l'entité attendue est celle du POINT DE SPAWN, pas la tuile » — **FAUX** : c'est bien
   `TileEntity id=13`, exactement ce que `fsmTap` passait déjà. `entityHit` et `tileHit` sont
   d'ailleurs **le même objet**.
2. « `mousePosition` ne sert qu'au tap-vs-swipe, `[0,0,0]` suffit » — **FAUX aussi** : le jeu
   passe une vraie position écran.

⚠ **ET REJOUER LE COUPLE EXACT NE SUFFIT PAS.** `fsmTap({entityId: 13, tileEntityId: 13,
pos: [231, 1043, 0]})`, unité en main, tuile libre : **aucun effet**. Les arguments sont donc
DÉMONTRÉS justes — le défaut n'est pas dans ce qu'on passe.

⚠ **TOUT SE RAMÈNE À UNE SEULE CAUSE, ET ELLE ÉTAIT DÉJÀ SOUS LES YEUX.** `PutUnitIntoHand`
faute *à l'intérieur*, après avoir levé `HasUnitInHand()` mais **avant** d'avoir construit la
donnée visuelle (`CreateVisualUnitDataForDeployment`, qui faute identiquement). L'unité est
donc « en main » **par le drapeau, pas par les données** — et une pose qui lit ces données ne
trouve rien à poser. Le trio symptôme (pose inerte, `TryMarkUnitAsPlaced` qui ne peuple pas le
plateau, `PutIntoHand` qui faute) n'est pas trois problèmes : c'est **un**.

⇒ Prochaine question, et une seule : pourquoi la construction du visuel faute-t-elle depuis
NOTRE chemin d'appel et pas depuis celui du jeu, alors que les deux sont sur le thread
principal ? Piste : le moment dans la frame — `queueOnMainThread` s'exécute depuis la pompe,
le jeu appelle depuis son propre traitement d'input.

Le décodeur lit la charge utile à `+0x10` de l'objet BOXÉ (en-tête de 0x10 sur tout
ValueType), et **dit ce qu'il ne sait pas lire** : type non couvert ⇒ `decode: false` avec le
nom du type et le pointeur brut, plutôt qu'une lecture plausible. Les deux exports
`method_get_return_type` / `class_is_valuetype` étant POSSIBLEMENT NULS (résolus par IIFE dans
`helpers.ts`), leur absence rend `type: null` + `NON MESURE` — jamais un type inventé.

⚠ **Et le `Start!` reste hors de portée par cette voie** : `StartBattle(List<System.String>)`
prend un type COMPOSÉ, que `fsmStateInvoke` refuse volontairement (construire une `List<T>`
demanderait de choisir une classe, donc de deviner). Le bouton UI reste la voie.

⚠ **Le clic UI sur un portrait rend `ok:false, "onClick.Invoke threw: system error"` — et
monte QUAND MÊME le `PreviewContainer`.** Le handler s'exécute donc PARTIELLEMENT. C'est une
troisième forme du mensonge de `uiClick`, distincte des deux connues : ni un clic avalé
rapporté vrai, ni un clic porté rapporté faux, mais un clic **à moitié exécuté**.

## La tranche

1. Capturer l'instance du FSM en hookant `IdunBattle.View.FSM.UnitSelectionFsm$$.ctor`
   (idiome `lastSource` du dépôt). Le faire à la CONSTRUCTION, et non au premier
   `HandleMouseButton*`, est ce qui évite d'exiger un clic humain par bataille.
2. RPC `fsmTap({ entityId?, tileId? })` : résout les pointeurs d'entité dans l'état de match
   vivant, puis enchaîne `HandleMouseButtonDownThisFrame` et `HandleMouseButtonUpThisFrame`
   avec la MÊME `mousePosition`.
3. Côté Python, `gamenav/` s'en sert pour composer l'équipe puis conduire le tour.

**BLOCAGE : capteur** — c'est du `frida/hooks/*`, donc une fenêtre de reinject, et elle se
prend HORS bataille.

## Ce qui a été mesuré au passage, et qui contredit deux intuitions

- **Le roster de déploiement n'est PAS tronqué.** 46 portraits éligibles montés dans la
  hiérarchie, et `CharacterRestrictionsButton_Info` porte exactement **46** ; les 5 verrouillés
  portent leur jauge (`adeptCelestine [401/500]`). Tous impériaux : c'est une **restriction de
  faction** d'Indomitus, pas une fenêtre de défilement. `ButtonPortrait_ultraTitus`, hors du
  champ visible, a répondu au clic — donc *voir* et *cliquer* ne dépendent pas du défilement.
- **La molette est inerte sur les deux canaux** (`PostMessage(WM_MOUSEWHEEL)` et `SendInput`) :
  0 portrait neuf, 0 parti. Cohérent avec ce qui précède — et `TouchInformation` confirme que
  la molette du jeu sert à la CAMÉRA (`ShouldMoveCameraWithScrollWheel`).
- **Un clic sur un portrait met l'unité EN MAIN — il ne la POSE pas**, et le compteur ment si
  on le lit trop tôt. Premier relevé après le clic sur `ultraTitus` : `PlayerPower` à `0`, d'où
  la conclusion hâtive « ça ne fait que prévisualiser ». Relevé plus tard : **453134** — le
  label s'anime, donc une lecture immédiate est une mesure FAUSSE, pas une mesure nulle.
  Pendant ce temps `observeBattle` reste à **12 unités, toutes ennemies** (`player=4`) : rien
  n'est sur le plateau. Le clic monte `Container/PreviewContainer/ButtonPortrait_<id>` et
  alimente `UnitDeploymentState.CurrentlySelectUnit` ; c'est le clic sur l'HEX qui pose.
- **Et tant qu'une unité est en main, les autres portraits ne répondent plus** : deux clics sur
  `ButtonPortrait_ultraCalgar` laissent `PlayerPower` à `453134` (`ok:false` les deux fois).
  Le FSM attend sa tuile. C'est la confirmation comportementale du couple
  `OnUnitInHand` / `OnFingerDownThisFrameInternal` — et la raison pour laquelle le
  déploiement est **bloqué net** sans l'entrée par entité décrite plus haut.
- **`Clear` a bien vidé la présélection** : `PlayerPower` 1912587 → 0, alors que `agir` rendait
  `porte : NON`. L'empreinte par jeu de chemins est **aveugle à une sélection** — d'où le témoin
  explicite ajouté à `gamenav/agir.py`.

## LA RÉSOLUTION — la pose a DEUX crans, et je n'en appelais qu'un

Le mur tenait à une lecture incomplète du décompilé, pas au moment dans la frame.
`StateMachineActions$$UnitDeployment_PlaceUnitOnBoard(unitId, column, row, isManual, playerId)`
— paramètres NOMMÉS, lus dans `data/symbols/<build>/frida/methods.tsv` — enchaîne :

```
1. slot 0x11 sur this+0x48 (_hud)   (unitId, false)  -> Boolean   # = TryMarkUnitAsPlaced
   si false : RETOUR IMMEDIAT, sans rien faire, et la methode est void
2. slot 0x1a sur this+0x18 (_views) (unitId, column, row, isManual, playerId)   # LA POSE
```

`IdunGameHud.UnitDeployment_TryPlaceUnitOnBoard` **est le cran 1 tout seul**. Je jugeais sur
son `true` — d'où « l'alignement se remplit mais le plateau reste vide ». Le cran 2 n'a pas
d'équivalent sur le HUD : il faut passer par `_actions`.

⚠ **ET LE CRAN 1 N'EST PAS UNE LECTURE — IL MARQUE.** L'appeler pour « vérifier si ça passe »
consomme un emplacement. Faute commise ici : trois unités marquées sans être posées, à
re-vider. Un nom en `Try…` qui rend `Boolean` se lit comme un test ; c'en est un **et** une
mutation.

⚠ **`playerId` est le PlayerId LOGIQUE (11 = joueur, 12 = IA), pas l'id ECS.** `observe.ts` le
dit en toutes lettres — *« Owner's PlayerEntityId (BEntityId in MatchState — not the logical
11/12 PlayerId of the BC config) »* — et la BC live confirme : `predefinedUnits[0].playerId ==
12` pour l'équipe nécron. Les deux espaces coexistent dans les mêmes relevés (`observeBattle`
rend `playerId: 4` pour ces mêmes nécrons) ; confondre les deux écrirait un propriétaire faux
sans lever d'erreur. À noter : `IdunBattle.Core.PlayerId` **n'a aucun membre nommé**
(`classFields` : 1 champ `value__`), donc rien à convertir en enum — c'est un int typé.

### Ce que ça mesure

| étape | témoin | mesure |
|---|---|---|
| présélection restaurée à la re-entrée | `PlayerPower` | 1 912 587, et la porte rend **`false`** |
| `HandleOnRemoveAllHeroesPressed()` | `PlayerPower` | → **0**, porte → **`true`** |
| 5 × `PlaceUnitOnBoard` | `PlayerPower` | 453 134 → 1 146 969 → 1 595 180 → 1 596 532 → **1 912 883** |
| `Start!` puis `observeBattle` | position ECS | **5/5 sur l'hex demandé** — (0,1)(0,0)(1,0)(1,1)(2,0) |
| `applyAction` move | position ECS | `astraYarrick` (2,0) → **(3,1)**, `mutated: true` |

⚠ **`observeBattle` était le MAUVAIS témoin pendant tout le Setup, et ça a coûté cher.** Les
héros du joueur ne sont **pas** des entités ECS avant `Start!` : `counts.total` reste à 99,
inchangé, pose après pose. Les 12 ennemis, eux, y sont — ce sont des `PredefinedUnits` spawnées
au chargement de la BC. Un témoin qui montre un camp et pas l'autre se lit comme « rien ne s'est
passé ». Le témoin de composition est `PlayerPower` ; le témoin de POSITION n'existe qu'après le
lancement.

⚠ **Un `ok: true` d'`applyAction` ne dit rien — lire `mutated`.** `move 101 -> (3,0)` rend
`ok: true, mutated: false, changes: [], events: []` et l'unité ne bouge pas ; `(3,1)`, tirée des
`ranked` de `decisionView`, rend `mutated: true`. La case était fausse, pas le mécanisme.

### `depuisInput` : construit, et RÉFUTÉ COMME NÉCESSAIRE

L'hypothèse « le moment dans la frame » est **sans objet** : la pose réussit depuis la pompe
(`voie: "pompe"`). Elle n'a jamais été fausse — elle était sans emploi, parce que le défaut était
un cran manquant, pas un instant manqué.

⚠ **Et son point d'ancrage ne bat PAS.** `fsmStatus.ancrageInput.appels` est resté à **0** sur
toute la session — nav, re-entrée en bataille, 5 poses, lancement, un déplacement.
`TouchInformation.ShouldMoveCamera` n'est appelé que depuis un VRAI événement d'input, pas à
chaque frame : sans clic humain ou `SendInput`, la file ne se draine jamais et `depuisInput`
sortirait en refus de délai. C'est exactement ce que le compteur était là pour dire, et il le
dit. Le module reste livré et honnête ; il ne doit pas être présenté comme une voie disponible.

## FIN DE TOUR — le drapeau est `toActivate`, et le canal est le journal des MESSAGES

Mesuré le 2026-08-09, build `rnca9r7q6c`, trois batailles et un runner isolé.

**« Cette unité a-t-elle encore une action ? » se lit dans `decisionView.toActivate`**, et
nulle part ailleurs : `observeBattle` ne publie AUCUN drapeau d'action (ses 13 clés par unité
sont position / hp / armor / rank / isDead). La règle de fin de tour est **symétrique** et se
dérive de ce seul champ :

```
toActivate == []   ->  le jeu termine le tour LUI-MEME. Ne rien toucher.
toActivate != []   ->  il attend. Cliquer `EndTurnButton`.
```

⚠ **`WaitingForPlayerTurnToEndVisuallyState` N'EST PAS un écran figé** — c'est l'état NORMAL
que la vue traverse pendant qu'elle termine le tour toute seule. Mesuré : la dernière frappe
du tour rend `etatApres = WaitingForPlayerTurnToEndVisuallyState`, puis 8 messages tombent,
puis `AiTurnState`, puis `NormalState` avec la main rendue. Ce qui fige, c'est **d'agir
pendant** cet état (cf. la section suivante) — pas l'état lui-même.

⚠ **AGIR CONSOMME LE TOUR DE L'UNITÉ — et l'exception est portée par l'ABILITY, pas par le
fait d'avoir bougé.** Frapper consomme aussi le déplacement ; seules certaines abilities
laissent l'unité rejouer après le cast.

**CECI EST DÉJÀ PORTÉ, NE PAS LE RE-DÉRIVER À GHIDRA.** La liste nominative est
`NO_END_TURN_ABILITY_TYPES` (`engine/runner/abilities/base.py`) — **14 abilities**, avec
l'unité porteuse en commentaire : `1014 ArmoriumCherub=Vindicta`, `1106 WarHowl=Ragnar`,
`1081 FightingRetreat=Darkstrider`, `1131 JakhalStimms=Macer`… Le mécanisme est décrit dans
`case-52-generalisation.md` § « Ce qui rend l'état atteignable » :
`IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution` lit **deux
virtuals INDÉPENDANTS** — `SetsActiveAbilityUsedFlag` (→ flag 2) et `SetsEndTurnFlags` (→ fin
de tour) — d'où le second ensemble `NO_ABILITY_USED_FLAG_ABILITY_TYPES`, qui n'est pas le
même (13 classes, cf. `1063 FireAndReposition` et `1121 ItItches`).

Le seul apport de ce tour de mesure est l'étage de LECTURE du flag, côté opération :

```
IdunBattle.Operations.ActiveAbilityOperation$$GetSkipEndTurnFlag(options, abilityImpl, entities)
   si options+0x40[9] != 0  ->  rendre options+0x40[10]      # surcharge portee par TargetingOptions
   sinon                    ->  slot 0x17 sur l'ability (= `<X>Ability$$SetsEndTurnFlags`),
                                evalue sur les entites, resultat INVERSE (`^ 1`)
```

Appelé depuis `$$ExecuteInternal` et `$$ExecuteForReplacedTarget`. La surcharge par
`TargetingOptions` (`options+0x40[9]`) ne figure pas dans le port — à confronter avant d'en
faire quoi que ce soit.

⚠ **NON EXPLIQUÉ, ET ÇA RESTE OUVERT** : `ultraCalgar` demeure dans `toActivate` après avoir
lancé un `ActiveAbilityMessage` depuis sa case, là où `darkaAzrael` en sort. **Calgar n'est
dans AUCUN des deux ensembles ci-dessus**, donc ce n'est pas ce mécanisme. L'ability employée
n'a pas été relevée (`decisionView.evals[].abilityId` la donne, il suffisait de la lire). Ne
pas présenter cette observation comme un exemple de `SetsEndTurnFlags`.

⚠ Ne pas compter les porteurs depuis la table de symboles : `SetsEndTurnFlags` est un slot
virtuel à corps trivial, donc dédupliqué par IL2CPP (30 xrefs DATA sur la seule entrée
WarHowl). Cf. « L'ABSENCE d'une méthode dans les tables ne prouve RIEN ».

⚠ **Déselectionner N'EST PAS inconditionnel** : taper une case vide depuis `NormalState`
n'annule rien, ça OUVRE `InspectTileState`. Ne déselectionner que si le FSM est ailleurs que
`NormalState`, et re-vérifier avant d'appuyer.

### Le canal, c'est `dump`/`summary`, pas le flux d'events

`battleEvents` (frame au FOND d'`applyStack`) capte **0** event pendant une bataille : le
recorder de `game/recorder.ts` ouvre une frame par `Apply(message)`, donc tout ce que le jeu
émet tombe dans la SIENNE, au sommet. Mesuré : `flux hors-msg +0` à chacun des 12 relevés d'un
tour. Ce qui répond à la question, c'est le journal des messages — `src` y discrimine :

```
src = "top"  ->  nos actions            (MoveUnitMessage, ActiveAbilityMessage, EndTurnMessage)
src = "ai"   ->  L'ADVERSAIRE JOUE      (14 a 18 messages par tour necron)
```

`battleEvents` reste utile hors bataille (146 events captés sur la nav + le déploiement).

### `applyStack` non vide = un `Apply` a LEVÉ, et c'est le seul détecteur qu'on ait

`Interceptor.attach` n'appelle **pas** `onLeave` quand la fonction hookée lève : chaque `Apply`
qui jette laisse donc une frame orpheline. Le refus d'armement de `battleEvents` (« la pile
d'apply n'est pas vide (N frame(s)) ») **est** ce détecteur, à son corps défendant.

Mesuré : dans la bataille qui refusait de basculer, `N == 2` — exactement les **deux**
`EndTurnMessage` envoyés (bouton, puis `_actions.EndTurn()`). Les deux ont été appliqués
(journal du recorder), les deux ont vidé `toActivate`, et **aucun** n'a fait avancer le tour :
l'exception coupe le pipeline de `IdunBattle.Messages.InputMessageProcessor$$RunPhase` avant
son appel à `ContinueTurnPhase`. Les frames survivent à la retraite et à la bataille suivante.

**Ce qui a été RÉFUTÉ en chemin** : l'armement global d'`aiUtility`
(`frida/hooks/features/ai-utility-trace.ts`, `arm("aiUtility")` au register). Contre-épreuve
jouée : **armé**, l'IA joue immédiatement au `EndTurnMessage` suivant (14 messages `src=ai`).
Ce n'était pas la cause. `bucketAudit` était `installed: false`, donc inerte.

**Et le chemin moteur est SAIN** : sur un runner isolé (`rl_duel build --board-pool pvp`),
`act endturn` rend `currentPlayer` 3 -> 4 du premier coup, et `aiturn` joue 147 events. Le
blocage était propre à cette bataille-là, pas au verbe.

⚠ **Reste NON NOMMÉ**, et les trois voies de mesure ont chacune rendu un silence :

- `armExceptionCtorHook` **n'aurait rien vu** — son hook faisait `if (insideInitialize === 0)
  return`, c'est une fenêtre de cctor IL2CPP, pas d'`Apply`. Je l'ai armé et présenté comme le
  capteur du régime : c'était faux. **Corrigé** — il s'ouvre désormais aussi sur la fenêtre
  `Apply` (`insideApply()`, tenue par `game/recorder.ts`), et l'event dit LAQUELLE des deux.
- Le **`Player.log` d'Unity ne porte aucune exception managée** sur ce run. Donc si c'en est
  une, elle est **ravalée par un appelant** (elle sort d'`Apply` — sinon `onLeave` aurait tiré
  — et quelqu'un au-dessus la mange sans la journaliser).
- La pile ne publiait que sa HAUTEUR. **Corrigé** : `battleEvents` rend `pile: [role, …]`, donc
  une frame orpheline désigne son module.

⚠ **Notre propre mode de fuite connu est RÉFUTÉ** : le recursion guard de Frida supprime le
`onLeave` des sub-messages (cf. l'en-tête de `features/message-trace.ts`), mais il grossirait à
chaque imbrication — or le compte est resté à **exactement 2** à travers deux batailles saines
et ~40 messages de plus, dont deux tours d'IA complets. Deux événements ponctuels.

Résidu **#596-r1**. Les deux capteurs sont livrés mais **NON ARMÉS** : ils exigent une fenêtre
de reinject.

### Le bouton End Turn demande DEUX taps, et le premier ment

```
idun.ui.EndTurnButton$$OnTap(this):
    si  !(this+0x28).activeSelf              # panneau de confirmation pas encore affiche
        this+0x39 = 1
        return SetConfirmationMode(this, true)      # AFFICHE la confirmation, ET C'EST TOUT
    return (this+0x40).Invoke()              # 2e tap seulement -> IdunGameHud$$OnEndTurnButtonTapped
                                             #   -> slot 0x3b -> UnitSelectionFsm$$HandleOnEndTurnButtonTapped
```

`SetConfirmationMode(value)` ne fait qu'un `SetActive(value)` sur `this+0x28` et `this+0x30`.

⇒ **`porte: True` d'un clic sur `EndTurnButton` ne distingue pas « j'ai ouvert la confirmation »
de « j'ai terminé le tour ».** Le témoin est l'apparition d'un `EndTurnMessage` dans `dump`,
jamais le retour du clic — application directe de « ne jamais conclure du retour d'un clic
qu'il a porté ».

⚠ Ceci **corrige** ce que le handoff attribuait à `UnitNormallySelected` (« cliqué en
`UnitNormallySelected`, le bouton rend `porte: True` et ne fait rien »). Le gate décompilé est
l'`activeSelf` du panneau de confirmation, pas l'état du FSM.

⚠ Et ça **n'explique PAS** le blocage : dans les deux régimes — celui qui bascule et celui qui
ne bascule pas — un seul tap de `clic.py` a produit un `EndTurnMessage`. À instruire dans
#596-r1 : dans quel état était le panneau au moment de chaque tap.

### La suite : se greffer sur l'AUTOMATE, pas sur ses entrées

`fsmTrace` capte les **entrées** (`down`/`up` que le jeu passe au FSM) — pas les
**transitions**. L'entonnoir existe et il est unique :
`IdunBattle.View.FSM.UnitSelectionFsm$$ChangeState<T>`, appelé par
`$$HandleOnEndTurnButtonTapped` comme par tout le reste. Le tracer donnerait la suite d'états
avec son déclencheur — ce qui aurait tranché ce dossier en minutes.

⚠ **Difficulté à mesurer, pas à contourner** : c'est une définition GÉNÉRIQUE
(`ChangeStateu003C__Il2CppFullySharedGenericTypeu003E`). `findMethod` sur une définition
générique rend le **thunk d'invocation**, pas le corps gshared — le piège de `bucket-audit`,
qui se déclarait `enabled` avec **0 fire**. Passer par l'instance inflatée (cf. `case-259`).

### Ce que le décompilé dit du verbe, et où notre port diverge

```
IdunBattle.View.FSM.UnitSelectionFsm$$HandleOnEndTurnButtonTapped  -> ChangeState<...>
IdunBattle.View.FSM.StateMachineActions$$EndTurn                   -> TryGetLocalPlayerIdIfCurrentTurn
                                                                      puis new EndTurnMessage(playerId)
IdunBattle.Messages.EndTurnMessage$$.ctor(this, playerId)          -> Nullable<PlayerId> @ +0x10
```

⚠ Le paramètre du ctor est un **`Nullable<PlayerId>`**, pas un booléen `advance` — et
`Core.Services.OperationProcessor$$EndTurn(isAutomatically)` porte ce nom-là. Or
`engine/runner/messages.py` déclare `EndTurnMessage(advance: bool)` et `turnflow.py` écrit que
`EndTurnOperation$$Execute` « enqueue le changement de tour » : **le décompilé ne contient
aucun appel à `ChangeTurnOperation`**. L'avance vient de
`IdunBattle.Messages.InputMessageProcessor$$RunPhase` -> `ContinueTurnPhase`, qui boucle sur
`IdunBattle.Entities.Components.TurnComponent$$GetNextTurnStage` (`null` dès que l'étape
courante `+0x10` égale l'étape cible `+0x14`). Divergence de port à instruire — **#596-r1**.

## CONDUIRE PAR LA VUE — le tour se referme, et c'est la seule voie qui le fasse

⚠ **MOTEUR ET VUE NE SE MÉLANGENT PAS.** Jouer les unités par `applyAction` (moteur) puis
demander la fin de tour à la vue la fait entrer dans `WaitingForPlayerTurnToEndVisuallyState` :
elle masque le bouton `EndTurnButton` et attend un visuel qu'aucune de nos actions n'a produit
(`eventCount: 0` sur toutes). Écran figé, moteur intact, plus aucune sortie — sauf
`Pause -> Retreat`. Le `eventCount: 0` était l'avertissement ; il a été relevé et pas suivi.

Les mêmes gestes joués **par la vue** referment le cycle : `EndTurnButton` -> `AiTurnState` ->
`currentPlayer` 3 -> 4 (les nécrons jouent, `unitsAlive` 17 -> 19 : les swarms se multiplient)
-> retour en `NormalState`, la main est à nous.

### L'id d'entité-tuile se DÉRIVE

```
tileEntityId = 12 + col * 9 + row          # col 0..6, row 0..8
```

Vérifié : donne 63 ids contigus (12..74), soit exactement `observeBattle.counts.tiles`, et
concorde avec les cinq points de spawn relevés par `fsmTrace` sur clic humain ((0,1) = 13).
Aucun RPC ne publie ces ids aujourd'hui — c'est la seule voie.

### Les gestes, mesurés

| geste | séquence | résultat |
|---|---|---|
| **sélectionner** | `down(tuileUnite)` puis `up(unitId)` | `UnitNormallySelected` |
| **déplacer** | `down(tuileUnite)` `held(tuileDest)` `up(tuileDest)` | `Swipe_MovementTargetSelected` -> `UnitNormallySelected`, unité déplacée — **3/3** |
| **attaquer** | depuis `UnitNormallySelected` : `up(cibleUnitId)` | `TryAttackFromCurrentTile` — cible passée à `hp=0`, morte |
| **tap simple** | `down(t)` `up(t)` même tuile | retour à `NormalState` : ça NE sélectionne pas durablement |
| **inspecter** | `down(tuileEnnemie)` `up(...)` depuis `NormalState` | `InspectEnemyState` |

`BaseSelectionState$$TrySelectPlayerOwnedUnitWithActionLeft(this, entityHit, selectedUnit)`
convertit `entityHit` en unité par `_visualBattleQuery` slot 0x19 : au **`down`** on passe donc
la **TUILE**. Au **`up`**, c'est l'inverse — `FingerDownOnUnitForFirstTime$$OnFingerUpThisFrame`
teste `entityHit == this+0x48` (`_unit`), et `UnitNormallySelected$$OnFingerUpThisFrame` teste
`IsUnit(entityHit)` avant `TryAttackFromCurrentTile(this, _unit, entityHit, null)`. **Le `down`
prend la tuile, le `up` prend l'unité** ; c'est écrit dans les deux décompilés, et aucune
expérience ne l'aurait deviné.

⚠ **DEUX ESPACES D'IDS, ET LES CONFONDRE COÛTE SIX GESTES SANS EFFET.**

```
tuile  ->  12 + col*9 + row
unite  ->  `decisionView.unitId` / `targetId`  ==  `observeBattle.squadId`
           JAMAIS `observeBattle.entityId`, qui est le PIED
```

`observeBattle` émet **une ligne par `UnitFoot`** : `entityId` = le pied, `squadId` = l'escouade.
Sur une unité mono-pied l'écart vaut **+1 exactement** (mesuré : 19 `Unit` / 19 `UnitFoot`,
deltas tous à 1), donc l'id fautif **désigne une autre entité VALIDE** — rien ne lève, le geste
part, il ne se passe rien. Ce n'est PAS un décalage à corriger : les deux entités existent, et
`snapshot.py::_load_feet` dépend légitimement de l'ordre croissant des pieds (Galatian : 3 pieds
108/109/110 pour le squad 107). C'est le **nom** qui trompe.

Trouvé en lisant `_unit.ToString()` du FSM, qui rend `[Unit 101, unitId: spaceBlackmane]` là où
`observeBattle` disait `102`. **Garde exécutable** posé depuis : `fsmInput`/`fsmTap` REFUSENT un
id de `UnitFoot` en nommant la cause. Le renommage `entityId` -> `footId` toucherait **133
fichiers** (dont ~30 tests live) — pas fait, à ouvrir en résidu.

⚠ **NE PAS TERMINER LE TOUR — LE JEU LE FAIT.** Quand toutes les unités ont joué, la transition
vers le tour adverse est automatique. Appeler `fsmInput({kind:"endTurn"})` par-dessus fige
l'écran dans `WaitingForPlayerTurnToEndVisuallyState` (bouton masqué, plus de sortie hors
`Pause -> Retreat`) — reproduit **deux fois**. Le clic sur `EndTurnButton` n'a fonctionné que
dans le cas où il RESTAIT des unités à jouer : c'est un raccourci, pas la fin de tour normale.
Et `fsmInput endTurn` n'est pas ce que fait le bouton.

## LE TERRAIN — `Buttons/LevelN` est un SLOT D'ÉCRAN, pas un nœud de campagne

Mesuré le 2026-08-09 (`rnca9r7q6c`). Question de départ : « on n'a pas choisi le bon niveau ? »
Réponse mesurée : **on ne peut même pas le NOMMER par le chemin qu'on clique.**

**Le chemin ne désigne aucun nœud stable.** L'écran monte **15** slots
(`CampaignScreen_Part_1_5(Clone)/Buttons/Level1..Level15`) pour une campagne de **75** nœuds,
et la bataille réellement montée était **`Campaign1_62`** — aucun slot ne s'appelle `Level62`.
Le `LevelN` du chemin est donc une **position dans la fenêtre de carte affichée**, pas un
identifiant de bataille.

**Et personne ne choisit ce slot.** `auto-boot.ts::findButtonBySuffix` fait
`enumerateButtons(r, false).find(b => b.path.endsWith(NODE_SUFFIX))` — le premier de l'ordre
d'énumération Unity, qui n'est ni numérique ni la progression :

```
ordre mesure (uiList ET uiListAll, identiques) : 5, 14, 2, 13, 12, 11, 6, 3, 4, 8, 7, 1, 15, 9, 10
                                                 ^ l'amorce prend le slot Level5
```

Les scripts de pilotage, eux, écrivaient `Buttons/Level1/...` en dur. Deux voies, deux slots
différents, et aucune des deux ne nomme sa bataille.

**Le seul nommage non ambigu** — et il existe, donc il n'y a aucune raison de s'en priver :

| voie | base | vérifié |
|------|------|---------|
| `inspectBattleConfig().id` | `Campaign1_<NN>`, **1-based** | `Campaign1_62`, board `C1_62` |
| `buildCampaignConfig({campaignType, campaignId, locationIndex})` | **0-based** | `66` -> `Campaign1_67` |

`buildCampaignConfig` construit la BC **sans entrer dans la bataille** : c'est de quoi choisir
un terrain sur pièces plutôt qu'au hasard de l'énumération.

⚠ **Le « node 61 » de la ligne #596-r1 est ce `locationIndex` 0-based** : le nœud est
**`Campaign1_62`**. Écrire un index 0-based comme un numéro de niveau se relit faux.

### Ce qu'il faut regarder pour choisir un nœud — et les deux champs qui ne discriminent rien

`dumpCampaignCatalog` (1,2 Mo, 5 types de campagne). Sur `campaign1` :

- **`tutorials` est présent sur 75/75 nœuds** et **`requiredUnits` sur 71/75** : filtrer sur
  leur *présence* rend « aucun nœud libre », ce qui est faux. Il faut lire la **valeur**.
- `tutorials` → seul un préfixe `tut_` est un script ; `dlg_` n'est qu'une bulle de dialogue.
  Et la **clé** dit *quand* ça tire : `startUntilVictory` / `startFirstBattle` **pendant** la
  bataille, `afterFirstVictory*` / `afterFirstDefeat*` **après** (sans effet sur le combat).
  Mon premier critère ne testait que `startUntilVictory` et laissait passer Level15, qui porte
  `startFirstBattle: "tut_btl15"`.
- `requiredUnits` → le **trio de la campagne**, constant sur ses 75 niveaux
  (`ultraTigurius/…`, `blackHaarken/…`, `orksBigMek/…`, `eldarRanger/…`). Il discrimine la
  **campagne**, jamais le nœud.

Scénarisés *pendant* la bataille, une fois la valeur lue : `campaign1` **17/75**,
`campaign2` **1/75** (L4), `campaign3` **1/75** (L16), `campaign4` **0/75**.
Les **13 premiers** nœuds de `campaign1` opposent des **mannequins FTUE**
(`necroNpc1TutWarriorFTUEtest`) et non les unités du jeu ; aucune autre campagne n'en porte.
Level1 y ajoute `AbilitiesToHide: "StormOfWrath,PsychicFortress"` et **1** point de
déploiement. Premier nœud propre de `campaign1` (aucun script pendant la bataille, aucun
mannequin, 5 déploiements) : **Level16** (`board=C1_51`).

⚠ **`observeBattle` NE PEUT PAS montrer qu'un ennemi est un mannequin** — son `visualId`
laisse tomber le suffixe. Mesuré sur `Campaign1_06` (2026-08-09), même bataille, deux voies :

```
inspectBattleConfig  ->  necroNpc2TutFlayedOneFTUEtest:3, necroNpc1TutWarriorFTUEtest:3, ...
observeBattle        ->  necroNpc2FlayedOne,              necroNpc1Warrior,              ...
```

Un relevé `observeBattle` d'une bataille FTUE est donc **indiscernable** d'une bataille
ordinaire. La BC est la seule voie qui nomme le mannequin.

⚠ **HYPOTHÈSE RÉFUTÉE, ne pas la rouvrir** : « le script de tutoriel a fait lever les deux
`Apply` » (#596-r1) — **mais par UN seul argument, pas deux.** Ce qui tient : la bataille
était `Campaign1_62` (`inspectBattleConfig`), hors du bloc scénarisé **et** hors des 13 nœuds
à mannequins. Ce qui NE tient pas, et que j'avais écrit comme second appui : « les marqueurs
`FTUEtest` sont absents de tout le transcript ». Le paragraphe ci-dessus dit pourquoi — nos
relevés passent par `observeBattle`, qui **efface le suffixe**. L'absence était donc attendue
quelle que soit la bataille, et ne prouvait rien.

Re-dériver ces comptes (`dumpCampaignCatalog`), ne jamais citer ce paragraphe.
Résidu : **#596-r2**.


## LANCER UN ACTIF PAR L'INTERFACE — la chaîne complète, mesurée

Confronté le 2026-08-09 sur `Campaign1_06` (`rnca9r7q6c`, session 22). Aucun message vers le
runner : on joue ce que le joueur joue.

```
1. reset        fsmInput back  jusqu'a NormalState
2. selection    fsmInput down(TUILE) puis up(UNITE)      -> UnitNormallySelected
3. armement     uiClick sur la barre d'abilities          -> Ability_Info_Bar_HUD
4. designation  fsmInput up(CIBLE)                        -> le cast part
```

Résultat mesuré, un seul geste : **3 ennemis à 0 pv** (49, 53, 55 : 43 -> 0), `toActivate`
`[63,65,67,69,71]` -> `[63,65,67,69]` — le tour du caster est consommé — et `battleEvents.pile`
reste **vide** (aucun `Apply` n'a levé). Trois morts d'un coup : c'est bien l'AoE de l'actif,
pas l'attaque normale.

⚠ **LE RANG DU BOUTON NE DÉSIGNE PAS UNE ABILITY.** La barre monte DEUX boutons de chemin
IDENTIQUE (`Ability_Selection_HUD/Loki_Ability_Selection_HUD_MoW(Clone)/Button` — même parent,
même nom). Mesuré : le rang qui porte l'actif était **1** à un essai et **0** au suivant, sur
la même unité dans la même bataille. Le rang sert à ATTEINDRE les deux exemplaires ; il ne dit
pas lequel est lequel. **On essaie et on juge par l'EFFET** : quand un actif est armé, la barre
d'info bascule de `Unit_Info_Bar_HUD` vers `Ability_Info_Bar_HUD`. Ce témoin-là est net.

⚠ **ARMER NE CHANGE PAS L'ÉTAT DU FSM.** Il reste `UnitNormallySelected` avant comme après :
la sélection d'ability est un fait de HUD, et c'est le `up(cible)` qui déclenche. Chercher un
`AbilitySelectedState` est une impasse.

⚠ **HORS DE PORTÉE, LE `up` PART EN DÉPLACEMENT — sans rien dire.** Au tour 1 les 7 ennemis
sont à distance 5 pour un mouvement de 3 : `up(ennemi)` rendait `ok: true` et faisait
`UnitNormallySelected -> MovementSuggestionState`, ce qui se lit comme « le cast n'a pas
marché » alors que c'est « la cible n'est pas atteignable ». **Approcher d'abord** — et la
destination ne se devine pas : `decisionView.attackPlans[].evals[].ranked` publie les
positions DEPUIS LESQUELLES une cible est attaquable (ici `(2,2)` pour la cible `53`). Le
déplacement se joue `down(tuileUnite)` `held(tuileDest)` `up(tuileDest)`, 1/1.

⚠ **`uiClick` frappait TOUJOURS le premier bouton d'un chemin**, avec `ok: true` — donc
toujours l'attaque normale, en silence. Corrigé (`d64b5fa1`) : `uiClick({path, index?, ptr?})`,
et le retour porte désormais `matches`, ce qui rend l'ambiguïté VISIBLE. Un `matches: 2` dit à
l'appelant qu'il vient d'en frapper un sur deux.

⚠ **CE QUE `uiList` NE VOIT PAS.** Il énumère les `UnityEngine.UI.Button` par l'overload à
2 args de `FindObjectsByType`, **qui exclut les objets inactifs** — même piège que celui trouvé
sur `ScreenVisibility`. Un widget d'UI qui n'est pas un `Button`, ou qui est sur un objet
inactif, lui est invisible ; c'est ce qui bloque la lecture des effets appliqués (les icônes
`Idun_Unit_Info_Bar_UnitEffectIcon` sont énumérées mais sans libellé ni sous-arbre lisible).

**La couche que le bouton APPELLE**, si l'on veut court-circuiter le pixel un jour :
`_actions.OnAbilityTapped(IUnitAbility)`, `_actions.SelectAbilityInHud(IUnitAbility)`,
`_actions._hud.OnAbilitySelected(IUnitAbility, AbilityState)`, et côté widget
`idun.Ui.AbilitySelectionHudImage$$OnButtonClicked()` (sans paramètre). La chaîne d'objets est
`_actions._hud._abilitySelectionHud._allAbilityViews` (`List<AbilitySelectionHudImage>`, chaque
vue portant `_ability`). ⚠ Inatteignable en l'état : `fsmStateInvoke` n'accepte que
`chaine/booleen/entier/{float}/{long}/{entityId}` — **pas de pointeur**, et pas d'indexation de
liste dans un chemin de traversée.

⚠ **UN DIFF D'ÉCRAN SE FAIT PAR MULTIPLICITÉ, PAS PAR ENSEMBLE.** Deux widgets partagent leur
chemin : un `set` de chemins les écrase. J'ai lu « 17 -> 17 feuilles, rien n'a changé » alors
qu'un bouton venait d'apparaître. Compter (`Counter`), jamais `set`.


## LE BOUTON END TURN NE TERMINE PAS LE TOUR — et cette fois AUCUN `Apply` n'a levé

Mesuré le 2026-08-09 sur `Campaign1_06` (session 22), FSM à `NormalState`, 5 unités dans
`toActivate`, capteur d'exceptions armé.

```
etat de depart   turn=3  currentPlayer=3  toActivate=[63,65,67,69,71]   pile=[]
tap 1            ok:true   AUCUN changement d'ecran
tap 2            ok:true   EndTurnButton DISPARAIT (1 -> 0)
apres            turn=3  currentPlayer=3  toActivate=[63,65,67,69,71]   pile=[]
                 FSM = NormalState, veille 60 s : rien ne vient
```

Il ne reste à l'écran que `PauseButton`, un `Idun_Unit_HUD` et les deux `FullScreenButton` :
**la seule sortie est Pause -> Retreat**, exactement le symptôme du 2026-08-08.

⚠ **CE QUE ÇA FAIT À `#596-r1`.** La fiche impute le blocage à un `Apply` qui LÈVE — deux
frames orphelines dans `applyStack` en étaient la signature. Ici le **même symptôme visible**
se produit avec `pile` **vide** à chaque relevé, capteur armé, et sans qu'aucun
`EndTurnMessage` ne parte (rien ne bouge côté état). Donc, au choix : deux chemins distincts
mènent au même écran figé, ou l'exception d'hier était **concomitante et non causale**.
L'hypothèse « une exception coupe `RunPhase` » n'est plus la seule sur la table, et ce n'est
pas elle qui explique CE relevé-ci.

⚠ **LE PREMIER TAP N'AFFICHE AUCUN PANNEAU DE CONFIRMATION** — mesuré par diff de
multiplicité, zéro widget apparu. Le décompilé dit pourtant que `idun.ui.EndTurnButton$$OnTap`
affiche `this+0x28` et retourne quand il n'est pas `activeSelf`. Deux lectures restent
ouvertes : le panneau n'est pas un `Button` (donc invisible à `uiList`, qui n'énumère que des
`UnityEngine.UI.Button` sur objets ACTIFS), ou il n'a pas été affiché du tout. **Non tranché.**

⚠ **`observeBattle` GARDE LES MORTS.** `battleStatus.unitsAlive` rendait **12** après trois
kills confirmés (`hp 43 -> 0`). Filtrer sur `isDead` est obligatoire dès qu'on compte, qu'on
cherche une tuile libre ou qu'on choisit une cible — `gamenav.combat.unites` le fait
désormais, sa première version ne le faisait pas malgré sa docstring.

⚠ **UN NOUVEAU ROUND REMET LE CASTER DANS `toActivate`.** Après le cast de Calgar,
`toActivate` était passé à 4 ; plus tard il est revenu à **5, Calgar compris**, sans que
`currentPlayer` change et avec `turnsEnded: 6`. Le compteur `turn` est resté à 3 tout du long :
**il ne compte pas les rounds**, et s'en servir comme témoin de round est une erreur.


## `#596-r1` RESSERRÉ — les deux gardes nommables PASSENT (⚠ le 3ᵉ constat de ce chapitre est RÉTRACTÉ, cf. chapitre suivant)

Mesuré le 2026-08-09 (`Campaign1_06`, session 22). Trois hypothèses tombent d'un coup.

### Les trois gardes de `HandleOnEndTurnButtonTapped`, lues au décompilé

`IdunBattle.View.FSM.UnitSelectionFsm$$HandleOnEndTurnButtonTapped` ne construit son
`EndTurnMessage` qu'après trois filtres, et **chacun sort par un `return` MUET** :

```
cVar4 = <slot 0x66 sur _actions>   ; if (cVar4 == 0) return       <- garde 1
uVar7 = <slot 0x6e sur _actions>   ; if (uVar7 != 0) return       <- garde 2
                                     if (iVar5 != uVar6) return   <- garde 3
                                     ... ChangeState<T>, puis EndTurnMessage(playerId)
```

`this+0x40` = `_actions : IStateMachineActions`, `this+0x38` = `_matchView : IMatchView`
(`classFields` sur la classe VIVANTE). Le vocabulaire de l'interface donne les deux prédicats
qui ont cette forme exacte : `TryGetLocalPlayerIdIfCurrentTurn(PlayerId)` (doit RÉUSSIR) et
`IsControllingEnemies()` (doit être FAUX).

⇒ **Le blocage n'a jamais eu besoin d'une exception : un garde qui tombe suffit, et il est
silencieux par construction.**

### Sauf que les gardes PASSENT

Les deux prédicats sont sur `_actions`, donc appelables. Mesuré dans l'état bloqué :

| appel | valeur | garde |
|---|---|---|
| `IsControllingEnemies()` | **false** | satisfaite (doit être fausse) |
| `TryGetLocalPlayerIdIfCurrentTurn()` | **true** | satisfaite (doit réussir) |
| ~~`EndTurn()`~~ | ~~**true**~~ | **RETIRÉ — ce `true` est une CONSTANTE, cf. ci-dessous** |

Et `turnsEnded` **monte : 6 -> 9**. Puis, 35 s de veille : `currentPlayer` reste **3**,
`toActivate` reste **[63,65,67,69,71]** (les 5, caster compris), FSM à `NormalState`,
`pile` **vide** à chaque relevé.

### Ce que ça élimine

- **L'exception** — `pile` vide, capteur armé, aucune frame orpheline (cf. section précédente).
- **Le garde qui tombe** — les deux prédicats nommables rendent la bonne valeur.
- ~~**Le clic avalé**~~ — **RETIRÉ le 2026-08-09**, cf. la section suivante : l'appui de cette
  ligne était le retour d'`EndTurn()`, qui ne mesure rien.


## `#596-r1` — CE QUE J'AI PUBLIÉ COMME MESURE ÉTAIT UNE CONSTANTE, et les trois états de gel sont RÉFUTÉS

Mesuré le 2026-08-09 (`Campaign1_06`, session 23), après relecture du décompilé.

### Le `true` d'`EndTurn` est écrit en dur

`IdunBattle.View.FSM.StateMachineActions$$EndTurn` :

```
if (!TryGetLocalPlayerIdIfCurrentTurn(this, &playerId)) { LogWarning(...); return false; }
msg = new EndTurnMessage(playerId);
ApplyInput(this, msg);          // <-- retour IGNORE
return CONCAT71(..., 1);        // <-- litteral 1, jamais le resultat d'ApplyInput
```

Le seul `false` que cette méthode sache rendre est celui du prédicat de joueur. **Une fois ce
prédicat passé, elle rend `true` quoi qu'il advienne du message.** La ligne « la fin de tour est
ACCEPTÉE » du chapitre précédent lisait donc un littéral, et l'hypothèse « clic avalé » qu'elle
prétendait tuer n'a jamais été testée. C'est la **même** signature que le piège déjà écrit plus
haut dans cette fiche pour les clics UI — *ne jamais conclure du retour d'un appel qu'il a porté* —
commise cette fois sur un appel natif.

⚠ Et elle se **répète** un étage plus bas : `applyAction {kind:"finish", unitId}` rend `ok:true`
sur les **5** unités de `toActivate`, et ni `hasAction` ni `toActivate` ne bougent. Un `ok` de
dispatch n'est pas un effet.

### Les trois états de gel du composant de tour : tous à zéro

`TurnComponent` porte de quoi trancher, en clair (noms LUS par `dumpEntityComponents` sur
l'entité 1, seule porteuse) : `<CurrentTurnStage>k__BackingField@+0x10`,
`<RequestedTurnStage>k__BackingField@+0x14`, `BlockTurnChangeCounter@+0x30`. Relevé par le RPC
neuf `turnPhaseState` :

| grandeur | valeur | l'état de gel qu'elle testait |
|---|---|---|
| `BlockTurnChangeCounter` | **0** | `AActiveAbility$$ExecuteOn` bloque puis débloque : un cast interrompu entre les deux laisserait > 0 **RÉFUTÉ** |
| `get_IsTurnChangeBlocked()` | **false** | accord natif/champ (`blockedAgrees: true`) |
| `<CurrentTurnStage>` | **3 = `Start`** | le bail « stage == `End` » de `VerifyAutomaticTurnEndOperation$$Execute` **RÉFUTÉ** |
| `verifyBailsOut` | **null** | aucune des deux sorties muettes de cet opérateur n'est prise |

`IdunBattle.Entities.Enum.TurnStage` = `0=Change, 1=Prepare, 2=Draft, 3=Start, 4=End`.
`IdunBattle.Entities.Components.TurnComponent$$GetNextTurnStage` rend `null` **exactement** quand
`Current == Requested` ; `IdunBattle.Operations.ContinueTurnPhaseOperation$$Execute` écrit
`Requested` puis fait avancer `Current` vers lui par `HandleNextTurn`. Ici `Start == Start` : la
machine de phase est **au repos, non bloquée**, ce qui est l'état NORMAL d'un tour qui attend le
joueur — et 5 de nos unités ont encore leur action, donc
`VerifyAutomaticTurnEndOperation$$DidAllUnitsFinish` a **raison** de refuser la bascule.

⇒ **Le gel n'est pas dans la machine de phase de tour.** Les trois pistes que la fiche désignait
comme « suspect suivant » sont fermées.

### Ce que ce spécimen ne peut PLUS trancher

Il est **contaminé** : une session entière d'injection directe de messages, de casts par l'UI et
d'appels `EndTurn` répétés. On ne peut plus y distinguer un bug du jeu de ce qu'on lui a fait.
Toute reprise part d'une bataille NEUVE, et la première question à lui poser n'est pas « pourquoi
ça gèle » mais **« est-ce que ça gèle »**.

⚠ **`turnsEnded` n'est PAS un compteur de rounds et ne se lit pas comme un booléen de bascule**
— il valait **9** avec 12 entités sur le plateau et 5 unités encore dans `toActivate`. Contrôle
posé le 2026-08-09 : **6 lectures consécutives sans aucune action rendent 12, 12, 12, 12, 12, 12**
— il ne dérive donc pas tout seul, ses sauts sont bien causés. Et ils valent **+3 deux fois de
suite** pour des lots de 5 `finish`, quand le plateau porte exactement **3 entités `player`** :
la grandeur est une **somme par JOUEUR** (`GetAmountOfTurnsEnded` = somme de
`AmountOfTurnsFinishedByPlayer`), pas un compte d'unités. Établir ce qu'elle compte reste un
préalable à toute conclusion bâtie dessus.


## `decisionView.effects` N'EST PAS la liste d'effets que le joueur VOIT

Confronté le 2026-08-09 (`Campaign1_06`, session 22), unité par unité : ce que le MOTEUR
déclare (`decisionView.units[].effects`) contre ce que la VUE PERSONNAGE montre (les icônes
`Idun_Unit_Info_Bar_UnitEffectIcon` de `Unit_Info_Bar_HUD`, relevées après sélection).

| unité | effets déclarés | dont actifs | icônes affichées |
|---|---|---|---|
| `ultraApothecary` | 1 — `Narthecium_Revive` | 1 | **0** |
| `ultraInceptorSgt` | 0 | 0 | 0 |
| `ultraEliminatorSgt` | 2 — `HeavyWeapon_ExtraDmg`, `Infiltrate` | 2 | **0** |
| `ultraTigurius` | 2 — `PsychicFortress_ExtraBlock`, `_DmgReduction` | 2 | **0** |
| `ultraCalgar` | 3 — `RitesOfBattle_ExtraDmgBasic`, `_ExtraDmgImperial`, `CrushingStrike` | 3 | **1** |

**8 effets déclarés, 1 icône.** Et le fait qui l'explique : **les 8 portent `source` == leur
propre unité**. Ce sont les passifs du KIT, pas des effets reçus — la vue ne les rend pas
comme icônes d'effet.

⇒ **Les deux sources ne comptent pas la même chose, et l'écart n'est pas une erreur.**
`decisionView.effects` inclut le kit intrinsèque ; les icônes montrent (au moins
principalement) ce qui a été APPLIQUÉ. En déduire « la vue est en retard » ou « notre lecture
est fausse » serait faux dans les deux sens.

⚠ **Contrôle interne : le zéro est un VRAI zéro.** `uiList` n'énumère que des
`UnityEngine.UI.Button` sur objets ACTIFS, donc un « 0 icône » pourrait n'être qu'un angle
mort de l'outil. Il ne l'est pas ici : Calgar en rend **1** dans le même relevé, avec le même
énumérateur — le lister VOIT ces widgets quand ils sont affichés.

⚠ ~~**CE QUI RESTE HORS D'ATTEINTE : QUEL effet est l'icône.**~~ **LEVÉ le 2026-08-10** — cf.
la section suivante. L'icône n'a effectivement ni libellé ni sous-arbre lisible, mais ce
n'était pas la bonne question : le jeu ne MET PAS le nom dans l'icône, il le montre dans une
INFOBULLE quand on clique. « 1 icône pour 3 effets » n'est plus un compte, c'est apparié.


## Les icônes se NOMMENT — il suffisait de cliquer et de lire l'infobulle

Mesuré le 2026-08-10 (`Campaign1_06`, session 28), sur `ultraCalgar`. En cliquant chaque icône
de `Unit_Info_Bar_HUD` puis en lisant `uiTexts` (cf. `case-599`), les **6** icônes se nomment,
se décrivent et se typent :

| widget | `_Info` | Titre | Description (extrait) |
|---|---|---|---|
| `Info_Bar_Ability` | *Active Ability · Ranged Attack* | **Gauntlets of Ultramar** | `1x` **2713-3488 Bolter Damage** à tous les ennemis à 2 hexes |
| `Info_Bar_Ability` | *Passive Ability* | **Rites of Battle** | alliés adjacents **+898 Damage** ; Imperial … |
| `UnitEffectIcon` | **Buffed** | **Crushing Strike** | attaques Melee normales **+50% Damage** |
| `TraitIcon` | Trait | **Mk X Gravis** | les dégâts entrants retraversent l'Armour |
| `TraitIcon` | Trait | **Crushing Strike** | **+50% Damage** en melee si l'unité n'a pas bougé |
| `TraitIcon` | Trait | **Final Vengeance** | à la mort, attaque normale sur une cible éligible |

⇒ **Et l'écart 3 effets / 1 icône s'explique enfin.** Le moteur déclare
`RitesOfBattle_ExtraDmgBasic`, `RitesOfBattle_ExtraDmgImperial`, `CrushingStrike` ; la vue les
répartit sur **trois familles de widgets distinctes** — les deux `RitesOfBattle` sont rendus
comme l'**ability passive** « Rites of Battle », `CrushingStrike` comme **icône d'effet**, et
le trait homonyme comme **trait**. Compter les `UnitEffectIcon` face à `decisionView.effects`
comparait donc deux ensembles qui ne se recouvrent pas.

⚠ **Les descriptions portent les valeurs RÉSOLUES** (`+898 Damage`, `2713-3488 Bolter Damage`)
— per-unit, per-niveau, calculées par le jeu. C'est un oracle de contre-épreuve pour un port :
la valeur que le joueur LIT, à confronter à celle que notre moteur calcule. On ne l'avait
jamais eue.

⚠ Le texte est balisé (`<style="Stat_Damage">…</style>`) : le dépouiller est trivial mais les
balises NOMMENT la catégorie (`DMG_Bolter`, `Aliance_Imperial`, `Stat_Melee`) — les jeter
perdrait de l'information.

⚠ **Ne pas généraliser depuis ce relevé** : il est pris au tout début d'une bataille, avant
que l'adversaire ait joué — donc AUCUN effet reçu n'existe encore. La confrontation qui
compte vraiment (un buff/debuff appliqué apparaît-il des DEUX côtés ?) demande un tour d'IA,
et elle n'est PAS faite. Écrire qu'elle l'est serait exactement le genre d'accord en régime
dégénéré que le dépôt proscrit : deux sources qui s'accordent sur du vide ne prouvent rien.

