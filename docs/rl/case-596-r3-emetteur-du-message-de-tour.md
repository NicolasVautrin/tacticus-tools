# #596-r3 — Qui devait emettre le message d'entree : la porte est `QueueComputerActions`

Mesure du 2026-08-16, build `t6dpr4k06g`. Repond a la question laissee ouverte par #596-r1
(« CE QUI a fait lever ces `Apply` ») : il n'y avait **rien a lever** — aucun message d'entree
n'etait produit. La porte qui aurait du en produire est
`IdunBattle.View.Game.IdunGameViews$$QueueComputerActions`, et elle porte un **verrou de
reentrance**.

⚠ **Cette fiche a d'abord accuse `HandleStartSpawningUnitsOfTurn`. C'est FAUX** — la lecture du
site d'appel l'a refute, et la section « CORRECTION » ci-dessous garde le detail. L'absence de
ce handler sur `SandboxGameModeSource` reste un fait mesure, mais elle n'est pas la cause.

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

## ⚠ CORRECTION — la chaine ecrite ici d'abord etait une INFERENCE, et elle est FAUSSE

La premiere redaction de cette fiche reliait « le handler manque » a « la coroutine d'IA ne
part pas ». **Ce lien n'a jamais ete etabli, et la lecture du SITE D'APPEL le refute.**

`idun.Ui.IdunGameHud$$StartSpawningUnitsOfTurn(playerId, group, continueCallback)` :

```c
if (hud + 0x1f8 == 0)  -> continueCallback.Invoke()   // le HUD continue LUI-MEME
else                   -> slot 4 d'interface -> HandleStartSpawningUnitsOfTurn
```

Quand aucune source n'est enregistree, **le HUD invoque le callback lui-meme** : la chaine ne
casse pas. Et ce handler porte sur l'APPARITION DES VAGUES, pas sur le tour d'IA — nos 39
unites apparaissent effectivement. L'absence du handler est un fait ; ce n'est pas la cause.

## La vraie porte : `IdunGameViews$$QueueComputerActions`

```c
IsPlayerAiControlled(this, joueurCourant) != 0
  && this+0x80 == 0 && this+0x81 == 0 && this+0x82 == 0 && this+0x83 == 0
  && this+0x1f8 == 0                                   // <- VERROU
     -> this+0x1f8 = IdunBattle.Utils.EmptyEnumerator.Instance   // on l'ARME
        puis on lance la coroutine (slot 0 d'interface sur this+0xe0)
```

`IdunGameViews +0x1f8` est un **verrou de reentrance** : pose quand la coroutine est mise en
file, et la porte exige qu'il soit NUL pour remettre en file. S'il n'est jamais relache, plus
aucun tour d'IA n'est jamais enfile — ce qui donne exactement « ca tourne un moment, puis plus
rien, definitivement ».

En aval, `RunComputerActionsForCurrentPlayerInMultipleFrames` prend
`IdunRunner$$get_AiControl`, lit `get_CurrentPlayerEntityId`, construit l'iterateur de
`AiControl$$CalculateAndApplyAllComputerActions` et le deroule sur plusieurs frames sous
budget en millisecondes.

⚠ **Le `+0x1f8` du HUD et celui d'`IdunGameViews` sont DEUX champs de DEUX classes** — meme
offset par coincidence. Les confondre ferait lire un verrou la ou il y a un test de source.

## TROIS candidats, tous MESURABLES, aucun tranche

1. `IsPlayerAiControlled` rend faux pour notre joueur ;
2. l'un des quatre booleens `+0x80..0x83` est arme ;
3. le verrou `+0x1f8` est reste pose.

Le 3 explique le mieux la forme observee (progression puis arret definitif), mais **ce n'est
pas une mesure**. Il se lit en direct sur l'instance : `IdunMainView.gameViews` (+0xb0), puis
les cinq champs. Tant que ce n'est pas fait, cette fiche NE nomme pas la cause — elle nomme la
porte.

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

## ⚠ CONSEQUENCE DE PORTEE : ce pilote est dans la couche VUE — inutilisable SANS UI

`QueueComputerActions`, le verrou `+0x1f8` et
`RunComputerActionsForCurrentPlayerInMultipleFrames` sont tous des membres de
`IdunBattle.View.Game.**IdunGameViews**`, et le deroulement est une coroutine Unity etalee sur
plusieurs frames sous budget en millisecondes. **Le tour d'IA d'une bataille live est donc
pilote par la VUE.**

Consequence directe pour un objectif « jouer des batailles SANS UI » : reparer `PlayerType.AI`
par ce chemin n'y sert a RIEN — il n'y a ni `IdunGameViews`, ni frames, ni coroutine. Ne pas
investir la si c'est la cible. Les voies headless connues, a instruire a leur place :

* `Runner.AutomaticBattleRunner..ctor(logger, battleConfig, **maxAmountOfTurns**, findReplayBugs,
  validate, timeSource)` -> `Run()` -> `AutomaticBattleResult {config, state, query, replay,
  runTimeInMs, exception, validationResult}` — banc headless du jeu, avec plafond de tours
  (donc un blocage y serait COUPE) et validation par le moteur lui-meme ;
* `AutomaticBattlesGameModeSource`, qui porte son propre `LoadBattle` ;
* cote harnais, `autoPlayRunner` boucle deja `CheatRunAIMessage` sur un runner ENREGISTRE
  jusqu'a `Finished` ou `maxTurns`, sans toucher a l'etat live.

Le contournement `--player-type 0` + `cheatRunAi` decrit plus bas a la meme propriete
interessante : il passe par un MESSAGE, pas par la vue. C'est donc le seul des deux regimes
qui ait une chance de se transposer headless.

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
