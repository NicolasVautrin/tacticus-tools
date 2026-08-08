# #596 — Jouer la bataille RÉELLE par le FSM, en donnant l'ENTITÉ au lieu d'un pixel

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
« à rejouer sur une session warmée » ; c'est sans objet — **le warmup FAIT exactement ce que
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
