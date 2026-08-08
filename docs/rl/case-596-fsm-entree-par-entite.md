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
