# #291 — pourquoi un SUMMON n'obtient JAMAIS d'activation, et par où il est quand même confrontable

**Verdict : COMPORTEMENT NATIF, pas un écart de harnais.** Le jeu TERMINE explicitement le tour de
toute unité qui apparaît pendant le tour de son propriétaire, puis la marque « sans action
disponible ». Elle ne peut donc, par construction, jamais entrer dans « À ACTIVER ». Elle agit
malgré tout — par deux chemins natifs distincts, qui sont les vraies voies de confrontation.

Le verrou #27-4f (5) (« les summons n'obtiennent jamais d'activation dans le harnais arène ») est
donc **fermé par la RE** : il n'y avait rien à débloquer côté harnais, il fallait regarder ailleurs
que `toActivate` / `aiDryRunAllUnits`.

---

## 1. La chaîne native, lue au décompilé

### 1.1 `SpawnUnitBehaviour` termine le tour du nouveau-né

`IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute` boucle sur son tile-sélecteur, appelle
`IOperationProcessor` slot 5 = `AddUnit(unitId, tileIds, playerId, SpawnSource.Ability(2), options)`
par tuile, **puis** ré-itère les unités créées dans
`IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours`, dont le corps est :

```
if (options.<on-appearance @+0x18> != null)          // SpawnUnitOptions+0x18
    <behaviour>.Execute(entities{ caster = unitSpawned })
turn = StateExtensions.GetMatchTurn(state)
if (TurnComponent.get_CurrentPlayerId(turn) == parentPlayerId) {
    v = UnitExtensions.HasTrait(unitSpawned, 0x1b = Steppable) ? false
                                                              : !HasTrait(unitSpawned, 0x10 = Hero)
    if (options.<Nullable<bool> @+0x48>.HasValue) v = <...>.Value
    if (v) IOperationProcessor.<slot 0x23>(unitSpawned, true)
}
```

**Le slot 0x23 est `FinishUnitTurn(unit, isTerminated)`**, identifié sans ambiguïté par deux
call-sites indépendants qui l'appellent avec le littéral `false` :
`IdunBattle.Entities.Behaviours.FinishUnitTurnBehaviour$$Execute` et
`IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute`. (Le slot `ComputerAction(unit, forced)`
est 0x34, cf. `IdunBattle.Entities.Behaviours.PerformAIActionBehaviour$$Execute` — ne pas les
confondre : les deux prennent `(unit, bool)`.)

`IdunBattle.Operations.FinishUnitTurnOperation$$Execute` pose alors
`UnitFlag.TurnTerminated(27)` (car `isTerminated`), `ArrivedAtFinalTile(1)`, `TurnFinished(3)`, vide
`UnitComponent.ChargedUnitIds`, et **termine par le slot 0x76 = `MarkUnitAsNoActionAvailable(unit)`**
(slot identifié par `IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded`,
qui appelle 0x76 pour poser et 0x77 = `MarkUnitAsActionAvailable` pour retirer).

Or `IdunBattle.Entities.UnitExtensions$$HasActionLeft` = `!UnitFlagsComponent.Has(4 =
NoActionAvailable)`. Le summon frais devient donc **invisible de toute liste d'activation**.

### 1.2 Le harnais lit exactement les bons prédicats — il n'a rien de faux

`decisionView.toActivate` (`frida/hooks/features/ai-step/internals.ts::toActivateSquads`) filtre sur
`IsControlledByCurrentPlayer(e, state) && IsAlive(e, state) && HasActionLeft(e)` — les trois
helpers natifs. Aucun filtre « summon » maison. `aiDryRunAllUnits`
(`sweepAllUnitProposals`) inclut au contraire TOUTES les unités contrôlées vivantes et rapporte leur
`hasActionLeft` ; interrogée sur une unité à `NoActionAvailable`, la tactique native rend
`FinishUnitTurnMessage`. **Le symptôme mesuré runner 189 était donc la réponse correcte du natif.**

### 1.3 Les DEUX voies par lesquelles le summon agit quand même

**(a) IMMÉDIATE — nœud DSL `PerformAIAction` câblé dans l'ability du summoner.**
`IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour` est une suite de
cinq `Group(...)` exécutés successivement :

| # | groupId | behaviour |
|---|---------|-----------|
| 1 | 0x22 | `Spawn(caster, PickRandomly(CanAddUnit(AdjacentTiles(casterTile)), nrOfSummons), unitId, WithStatsFromConfig)` |
| 2 | 0x25 | buff de faction |
| 3 | 0x23 | `MoveUnit` du CASTER |
| 4 | 0x20 | attaque du CASTER |
| 5 | 0x28 | **`PerformAIAction(Friends(UnitsWithVisualId(VisualUnitIdFromUnitId(Get(unitId)), 1)), asGroup, resetTurnFlags)`** |

`IdunBattle.Entities.Behaviours.PerformAIActionBehaviour$$Execute` appelle le slot 0x34 =
`ComputerAction(unit, forced)`, et `IdunBattle.Operations.ComputerActionOperation$$Execute`
**retire les flags de tour (`RemoveTurnFlags(flags, true, true)`, `NoActionAvailable` compris), fait
jouer l'unité, puis RESTAURE les flags** (`SetUnitTurnsFlags`). C'est ce qui rend l'action possible
malgré le finish-turn du §1.1 — et c'est pour ça que l'ability du summon reste affichée « prête »
après coup.

**(b) TURN-START SUIVANT — `PlayAutomaticUnits`.**
`IdunBattle.Operations.StartTurnOperation$$Execute` appelle, **après** les cinq émissions d'events
0x12..0x16, le slot 0x71 = `PlayAutomaticUnits(currentPlayer)`, sous deux gates :
`!IdunBattle.Core.Services.BattleQuery$$get_NoAutomaticUnitTurns` (flag de `BattleConfiguration`) et
`PlayerComponent.PlayerType` ∈ {`Human`(0), `Network`(3), `HumanAI`(4)}.
`IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute` :

```
foreach uid in PlayerComponent.CurrentlyOwnedUnitIds(player):
    u = state[uid]
    if u != null && IsAlive(u) && !HasFlag(u, 3 = TurnFinished) && IsAutomatic(u): auto += u
foreach u in auto:
    if (!skipAction) for i in 0..4: if HasActionLeft(u): ComputerAction(u, forced: false)
    FinishUnitTurn(u, isTerminated: false)
```

avec `IdunBattle.Entities.UnitExtensions$$IsAutomatic(u)` = `HasTrait(u, 2 = Summon) || HasTrait(u,
13 = Object)`. Le gate `!TurnFinished` n'est pas un obstacle au tour suivant : `StartTurnOperation`
a déjà appelé `RemoveTurnFlags(includeNoAction=0, newActivation=1)` sur les unités du joueur entrant.

Ce point (b) recoupe et confirme le §1 de **#250** (`test_summon_automatic_live.py`), qui l'avait
déjà établi ; #291 y ajoute le §1.1 (le finish-turn *à l'apparition*), la voie (a), l'ordre exact
dans `StartTurnOperation` et les deux gates d'entrée.

---

## 2. La mesure live (probe committé)

`scripts/python/probe_291_summon_activation.py` — runner arène, board `MC1_67`, seed 777,
`orksWarboss`+`orksNob` vs `darkaCompanion,tyranWingedPrime,ultraInceptorSgt`. Le Warboss est
rapproché jusqu'à ce que le natif publie une cible légale pour `Waaagh`(1058), puis on caste.

| étage | attendu (RE) | mesuré |
|---|---|---|
| E1 spawn | 2 `orksOrkBoys`, `SpawnSource=2` | u108, u110 — `Unit_IsSummoned=1`, `Unit_SpawnSource=2`, `Unit_Parent_Id=83` |
| E1 finish-turn | `TurnFinished` puis `ActionsAvailable=0` par summon | **`UnitStats_TurnFinished:1` puis `UnitStats_ActionsAvailable:0`, pour u108 ET u110**, immédiatement après leur spawn |
| E2 activation | absents de `toActivate` | `toActivate=[85]` (le Nob) — aucun summon |
| E3 voie (a) | mouvement + ability dans le MÊME cast | u108 : `group=11` move 4 tuiles (44→52→62→71) puis `group=12 source=Stikkbomb` ; u110 : `group=11` move (44→45→46→55) puis `group=12 source=Loki_NormalAttack` |
| E4 voie (b) | mouvement/attaque au turn-start suivant, sans action du joueur | u108 (6,5)→(5,6), u110 (4,7)→(3,7), et l'ennemi u81 `ultraInceptorSgt` passe de 4097 à **1474 PV** ; les deux restent hors de `toActivate` |

Le seed BC de l'arène a été relu : `NoAutomaticUnitTurns = false`, player 11 = `PlayerType 0`
(Human), player 12 = `PlayerType 1` (AI). Les deux gates d'entrée de (b) sont donc satisfaits côté
joueur — et **ne le sont pas** pour la team AI, dont les summons passent par la boucle IA globale.

---

## 3. Conséquence pratique : comment CONFRONTER un porteur summon

Un summon **est** confrontable avec SES stats et SES traits — la greffe sur un autre porteur n'est
pas nécessaire pour la face COMBAT. Ce qui change, c'est le point d'observation :

1. **Ne jamais chercher le summon dans `decisionView.toActivate`** ni attendre une proposition
   d'`aiDryRunAllUnits` : par construction native il n'y sera pas, et le `FinishUnitTurnMessage`
   rendu pour lui est la réponse correcte.
2. **Voie (a)** — quand l'ability du summoner porte un nœud `PerformAIAction` (Waaagh 1058,
   CultDemagogue, …) : la décision ET l'exécution du summon sont dans les **events du cast**
   (`applyAction(...).actions[0].events`), portés par l'entité du summon : `group=11` = déplacement,
   `group=12 source=<AbilityName>` = ability jouée. C'est un oracle de décision complet.
3. **Voie (b)** — sinon : finir le tour, laisser l'adversaire jouer, et **relire l'état au tout début
   de son propre tour, avant toute action**. Tout delta de position / de PV vient de
   `PlayAutomaticUnits`. C'est exactement ce que fait E4 du probe.
4. **Troisième voie, hors régime natif : `applyAction` accepte quand même de piloter le summon.**
   Mesuré sur le même runner : `orksNpc2OrkBoy` u108 est `ctrl=True`, `hasAction=False`, absent de
   `toActivate=[83,85]` — et `applyAction {kind:"move", unitId:108}` rend `ok=True mutated=True`, la
   position passe de (5,6) à (5,7). `applyAction` construit et applique un message natif **sans
   repasser par le gate `HasActionLeft`**, qui n'est qu'un filtre de la couche décision. C'est ce que
   TF36 observait. Utile pour forcer une configuration de test — mais on sort du régime natif (le
   moteur, lui, ne l'aurait pas activé), donc **jamais comme oracle de décision**.
5. Ce qui reste hors d'atteinte par ces voies : rien côté COMBAT. Côté **DÉCISION**, l'oracle
   « une proposition par unité contre un même état » (`aiDryRunAllUnits`) n'existe pas pour un
   summon. Le point d'ancrage exact qui le débloquerait est nommé au §5.

---

## 4. Ce que le port a gagné

| natif | avant | après |
|---|---|---|
| `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` (finish-turn du nouveau-né) | non porté | `spawn.trigger_spawned_unit_finish_turn` (gates `Steppable`/`Hero` + `currentPlayer == owner`), appelé par les choke points de spawn |
| ordre `on-appearance` → `FinishUnitTurn` | — | respecté (`Spawn.execute` fait le finish après l'on-appearance, via `finish_turn_on_spawn=False`) |
| `UnitExtensions$$IsAutomatic` | proxy `UnitComponent.ai_controlled` seul | union `ai_controlled` ∪ trait `Summon`/`Object` (`summon_ai.is_automatic`) |
| gate `!HasFlag(TurnFinished)` de `PlayAutomaticUnitsOperation` | absent | porté dans `collect_ai_controlled` |
| artefact natif cité pour la passe turn-start | `IdunGameViews$$QueueComputerActions` (**faux**) | `PlayAutomaticUnitsOperation$$Execute` + slot 0x71 de `StartTurnOperation` |

**Gardes** (`tests/engine/runner/test_summon_consumers_live.py`) :
`test_waaagh_fresh_summons_get_no_activation_live_and_port` (live : summon frais absent de
`toActivate` ; port : `TURN_FINISHED` + `TURN_FINISHED_FORCED` ; contre-épreuve : le caster EST dans
`toActivate` avant son cast) et `test_spawn_finish_turn_gate_spares_steppable` (contre-cas du gate :
un token `Steppable` n'est PAS finish-turn).

---

## 5. Résidus nommés (avec leur débloqueur exact)

1. **`MarkUnitAsNoActionAvailable` (flag 4) non posé offline.** Le poser serait une régression, pas
   un gain : son unique retrait natif est
   `IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded` (slot 0x77), non
   mirroré, et `StartTurnOperation` appelle `RemoveTurnFlags(includeNoAction=0)` → le flag
   survivrait au turn-start et figerait l'unité pour toujours (`has_action_left` est le gate de
   `ai_control_execute_for_group`). **Débloqueur** : porter `VerifyUnitTurnEnded` (+ `HasTilesToMoveTo`
   / `HasActionAvailable`) et les deux slots 0x76/0x77.
2. **Cap de 5 actions par unité automatique** (`for i in 0..4: if HasActionLeft -> ComputerAction`)
   et **`FinishUnitTurn(u, false)` final** de `PlayAutomaticUnitsOperation` : non portés, même
   raison que (1) — la boucle ne pourrait pas terminer sans le flag 4.
3. **Les deux gates d'entrée** (`!NoAutomaticUnitTurns`, `PlayerType ∈ {Human, Network, HumanAI}`) :
   ni le flag de BC ni le `PlayerType` ne sont suivis par le `State` offline. Impact **nul mesuré**
   sur l'arène ; il faudrait les suivre pour un montage où la team automatique appartiendrait à un
   joueur `AI`(1).
4. **Le champ `SpawnUnitOptions+0x48`** (`Nullable<bool>` qui écrase le verdict Steppable/Hero) :
   son producteur n'a pas été localisé (aucun `SpawnUnitOptions..ctor` exposé — les factories
   statiques `WithStatsFromConfig`/`ForSteppable`/`CopyOwner` initialisent les champs en ligne). Le
   port lit donc toujours le verdict par traits. **Débloqueur** : lire les écritures à `+0x48` dans
   les factories de `IdunBattle.Entities.Behaviours.SpawnUnitOptions`. Aucun porteur connu ne s'en
   sert (la mesure live sur Waaagh est conforme au verdict par traits).
5. **Oracle de DÉCISION d'un summon (face playbook).** `aiDryRunAllUnits` interroge la tactique sur
   une unité à `NoActionAvailable` et récupère `FinishUnitTurnMessage`. Le geste natif qui lève
   exactement cet obstacle est celui de `ComputerActionOperation` : `RemoveTurnFlags(flags, true,
   true)` **avant** d'interroger la tactique, `SetUnitTurnsFlags` après. **Point d'ancrage à ajouter
   au harnais** : une option `resetTurnFlags` sur `aiDryRunAllUnits`
   (`frida/hooks/features/ai-step/rpc-drive.ts`, autour de `sweepAllUnitProposals`) qui encadre le
   sweep de ce couple retirer/restaurer. Non implémenté ici : le valider exigerait une réinjection
   Frida, interdite pendant que d'autres agents travaillent — un hook ajouté à l'aveugle serait un
   port spéculatif.

## 6. Ce que #291 corrige dans la doctrine

La gate de confrontabilité du `CLAUDE.md` disait qu'un summon « apparaît dans l'équipe du summoner
et **agit dès son apparition** ». C'est **vrai mais trompeur** : vrai parce que la voie (a) existe,
trompeur parce qu'elle a été lue comme « on pourra le piloter / il apparaîtra dans les listes
d'activation ». Formulation corrigée dans le `CLAUDE.md` : le summon n'a **jamais** d'activation
propre, il est joué par le moteur, et on l'observe — pas on le commande.
