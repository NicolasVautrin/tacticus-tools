# #596-r3 — Qui devait emettre le message d'entree : `HandleStartSpawningUnitsOfTurn`

Mesure du 2026-08-16, build `t6dpr4k06g`. Cloture la question laissee ouverte par #596-r1
(« CE QUI a fait lever ces `Apply` ») — la reponse est qu'il n'y avait **rien a lever** : aucun
message d'entree n'etait produit.

## Le fait

`IdunBattle.ViewLogic.BattleSource.SandboxGameModeSource` **n'implemente pas**
`HandleStartSpawningUnitsOfTurn`. Resolu AU RUNTIME, pas lu dans une table :

```
SandboxGameModeSource.HandleStartSpawningUnitsOfTurn  -> methods: []  (rien jusqu'a System.Object)
SandboxGameModeSource.HandleBattleSurrender          -> existe, 9 params, +0x53cd80
TestSceneBattleModeSource.HandleStartSpawningUnitsOfTurn -> existe, 3 params, +0x55d870
```

La distinction compte : l'absence d'un nom dans `frida/methods.tsv` ne prouve rien (corps
dedupliques), donc le verdict vient de `resolveMethodPtr`, qui remonte la hierarchie sur
l'objet vivant. Il montre aussi que la classe de base de `Sandbox` est `System.Object` —
`AGameModeSource` n'est PAS son parent, il ne peut donc rien lui fournir par heritage.

Six sources l'implementent : `LinearHeroEvent`, `Onslaught`, `LegendaryEvent`,
`SurvivalEvent`, `TestScene`, `TreasureBeach`.

## La chaine, de bout en bout

Le seul travail du handler est d'appeler son `continueCallback` (verifie sur deux
implementations : `Onslaught` affiche le HUD de vague puis l'appelle ; `TestScene` delegue a
un slot d'interface). En aval,
`IdunBattle.View.Game.IdunGameViews$$RunComputerActionsForCurrentPlayerInMultipleFrames`
prend `IdunRunner$$get_AiControl`, lit `IdunGameViews$$get_CurrentPlayerEntityId`, construit
l'iterateur de `AiControl$$CalculateAndApplyAllComputerActions` et le deroule **sur plusieurs
frames** sous budget en millisecondes.

Sans le handler, `continueCallback` n'est jamais invoque : la coroutine n'est jamais lancee,
aucun message d'entree n'est enfile, la pompe de phase reste au repos et
`IdunBattle.View.FSM.AiTurnState` — qui n'a AUCUN `Update` et ne sort que par un changement
d'etat externe — ne sort jamais.

## Le releve qui l'a rendu visible

`replaySteps`, decoupage **par message d'entree**, meme montage et meme seed :

| run | pas | contenu |
|---|---|---|
| `PlayerType.AI` (fige) | **1** | `StartBattleMessage` — 416 486 car., 298 tirages |
| `CheatRunAIMessage` (fini) | **11** | `StartBattle` + 10 `CheatRunAI` — 655 568 car. |

Toute la bataille du run fige — quatre vagues — tient dans UN message d'entree. C'est
pourquoi elle avance longtemps avant de coincer.

⚠ **Le discriminant est le DECOUPAGE, pas le contenu du flux.** Les deux flux canoniques
divergent des 71 157 caracteres (17 % du premier) sur un `System_ProcessRemovals` d'ordre
interne : lire la divergence de TEXTE aurait designe un detail sans rapport.

⚠ **La decision, elle, est calculee — et identique dans les deux runs.**
`aiDryRunAllUnits` rend pour l'unite bloquee `MoveUnitMessage -> (2,6)` puis
`ActiveAbilityMessage(caster 282, target 166, ability 1065)`, meme unite, meme case, dans les
DEUX runs. Ce qui manque n'est pas le calcul, c'est ce qui le POMPE.

## Ce qui a ete elimine avant, et ne doit pas etre rouvert

La boucle IA (un RPC queued revient en 0,06 s, compteurs figes) ; le draft ; le
`SpawnPointTag` (vraie infidelite de la BC, corrigee, sans effet sur le gel) ; **nos trois
ancrages d'`Apply`** (coupes tous les trois via `applyHooks`, gel identique au bit pres) ;
**notre BC** (la BC capturee sur une partie reelle se fige aussi, plus tot).

⚠ **La frame orpheline d'`applyStack` n'etait PAS un symptome de la panne.** `onLeave` ne tire
pas quand la fonction leve — ce qui arrive sur TOUTE exception, y compris parfaitement
rattrapee. Elle etait un artefact de notre instrumentation. Les trois ancrages coupes, la pile
reste vide et le gel arrive quand meme.

## Portee — ce qui reste NON etabli

On n'a pas lu le SITE D'APPEL du handler : on ne sait donc pas s'il est saute silencieusement
ou s'il leve et qu'un appelant ravale. La chaine est etablie par ses deux bouts (le handler
manque ; aucun message d'entree n'apparait), pas par son milieu.

## Le contournement, eprouve

Laisser le joueur en `PlayerType.Human` et lui envoyer `CheatRunAIMessage` a chaque tour
(RPC `cheatRunAi`) : bataille menee a `Finished` en 10 tirs, FSM cyclant normalement
(`NormalState` -> `AiTurnState` -> `WaitingForPlayerTurnToEndVisuallyState`).
`sandbox_mode.py` avertit desormais sur `--player-type 1`.

Le correctif de fond serait d'implementer le handler cote source sandbox, ou de monter la
sandbox sur une source qui le porte — mais `TestSceneBattleModeSource`, qui l'a, n'a pas
`HandleBattleSurrender` : on ne pourrait plus sortir. Les deux sources sont complementaires,
et aucune n'est complete.
