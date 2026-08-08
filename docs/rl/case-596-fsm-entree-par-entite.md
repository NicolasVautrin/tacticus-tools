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

⚠ **La piste « session froide » (warmup désactivé) n'est PAS tranchée.** Un `POST
/api/admin/warmup` puis re-entrée en bataille laisse l'appel en `system error` — mais **le
warmup lui-même a rendu 500**, donc ce test ne réfute rien. À rejouer sur une session
warmée pour de bon avant de conclure quoi que ce soit.

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
