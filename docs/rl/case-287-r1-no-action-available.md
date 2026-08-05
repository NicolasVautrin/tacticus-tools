# Case #287-r1 — `UnitFlag.NoActionAvailable` (4) : la voie que le port ne posait pas

**Statut** : PORTE + CONFRONTE LIVE. L'ecart mesure par `probe_287_facade_combat.py` (`[1, 2, 3, 4]`
cote natif, `[1, 2, 3]` cote port sur le caster d'un cast) tombe a l'ENSEMBLE VIDE.

Residu ouvert par `case-287-sorcerous-facade-combat.md` §7.1. Il etait annonce **TRANSVERSE au
turn-flow** — il l'est : le flag est pose par `FinishUnitTurnOperation$$Execute` pour **toute**
activation qui se termine, quelle que soit l'ability.

## 1. L'artefact natif

`IdunBattle.Operations.MarkUnitAsNoActionAvailableOperation$$Execute(unit, reverse)`, MIRROR :

```
if (unit == null) return
comp = unit.GetComponent<UnitFlagsComponent>()          # TryGetComponent -> null => return
if (comp == null) return
if (!reverse) { if (!comp.Add(UnitFlag.NoActionAvailable = 4))    return }
else          { if (!comp.Remove(UnitFlag.NoActionAvailable = 4)) return }
Events.Publish(0xc, entityId(unit),
               { TagKey.UnitStats_ActionsAvailable (0x6f) : reverse ? 1 : 0 })
```

`UnitFlagsComponent$$Add` rend « le flag N'ETAIT PAS la » (`Contains ? false : (Add, true)`) : l'event
n'est publie **que** si la mutation a mordu. Le port rend ce booleen sous `changed` ; il n'emet pas
l'event (couche stream non suivie, comme le reste des Operations).

DEUX entrees, qui different par `reverse` :

| entree | slot `IOperationProcessor` | `reverse` | effet |
|---|---|---|---|
| `Core.Services.OperationProcessor$$MarkUnitAsNoActionAvailable` | `0x76` | `false` | POSE |
| `Core.Services.OperationProcessor$$MarkUnitAsActionAvailable`   | `0x77` | `true`  | RETIRE |

Le couple est identifie **sans ambiguite**, par deux voies concordantes : les deux methodes sont
adjacentes dans la table de la classe, et la branche `Has(4)` de `VerifyUnitTurnEnded` (« l'unite a
REGAGNE des options ») appelle le `0x77` la ou la branche `!Has(4)` appelle le `0x76`.

## 2. Les CINQ porteurs du slot 0x76 — et pourquoi il a fallu un scan BINAIRE

`mcp__ghidra__list_xrefs` ne voit que les appels **directs** (`E8`) ; le slot 0x76 est un appel
**d'interface**, donc invisible de cette voie. Et l'index litteral de `mcp__ghidra__search_code`
n'est **pas exhaustif** : mesure de cette tranche, il rend **0** pour la chaine
`(0x22,DAT_18336dba8` que `Taunted_RefreshUnitTurnFinishedEffect$$RevertInternal` contient
litteralement, et **17** fonctions pour `UnitExtensions__HasFlag` contre ~60 xrefs reelles. Un zero
de cet index n'est pas une mesure — meme lecon que #425-r3.

`scripts/python/probe_287r1_no_action_available.py` scanne donc les **octets** des sections de code
du build (`.text` 2,7 Mo + `il2cpp` 39,9 Mo, critere DERIVE des `Characteristics`, jamais une liste
de noms). Resultat sur `rnca9r7q6c` :

| porteur du slot 0x76 | contexte |
|---|---|
| `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` | **DERNIERE instruction**, INCONDITIONNELLE |
| `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` | `if (!skipEndTurn)`, **AVANT** le corps de l'ability |
| `...VerifyUnitsTurnFinishedOperation$$Execute` | balayage du joueur courant |
| `...VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded` | branche « plus d'options » |
| `...VerifyUnitsTurnFinishedOperation$$VerifyMachineTurnEnded` | idem, pour la MoW |

**Le port ne mirrore que le premier**, et c'est un choix motive, pas un oubli : les deux premiers
sont equivalents sur l'observable final (`AddFlagsAfterAbilityExecution` appelle `FinishUnitTurn`
sous le **meme** gate `!skipEndTurn`, et `Add` est idempotent). Le seul ecart est **temporel** — le
natif pose le flag pendant l'execution du corps de l'ability, le port en queue. Il ne serait
observable que si un noeud lisait `HasActionLeft` du caster **pendant** son propre cast.

### Le POINT D'ANCRAGE des trois `Verify*` — lu, apres avoir ete declare introuvable

Cette fiche a d'abord ecrit que `VerifyUnitsTurnFinished` n'avait « aucun appelant CODE, donc pas
d'ancrage portable ». **La mesure l'a refute** (cf. §7, bras `apres_deplacement`), et la relecture
donne l'ancrage : `IdunBattle.Messages.InputMessageProcessor$$RunPhase` — la boucle de
post-traitement jouee apres CHAQUE message d'entree — invoque le slot `IOperationProcessor`
**0x21** *deux fois*, en phase NON interne :

```
StreamHelper<0x22>(type) ; action() ; VerifyDeaths ; ProcessDamageEvents ; <0x1e>
ProcessPendingTriggeredAbilities ; <0x14>
if (!isInternalPhase) {
    <0x8e> ; <0x94> ; if (!isManualTurnEnd) VerifyDrafting
    <0x21>()                      # VerifyUnitsTurnFinished  -- AUCUN argument
    <0x20>(0, isManualTurnEnd)
    ProcessPendingTriggeredAbilities ; VerifyDeaths ; ProcessDamageEvents ; VerifyDrafting
    <0x21>()                      # une SECONDE fois
}
StreamHelper<0x23>(type)
```

Le slot est identifie par son ARITE et par ses voisins, pas au jugement : `0x21` n'a **aucun**
argument (`VerifyUnitsTurnFinished() : void`), `0x22` en a **un** (`VerifyAndRefreshUnitTurnFinished
(unit)`, confirme independamment par `Taunted_RefreshUnitTurnFinishedEffect$$RevertInternal` qui
l'appelle avec `target`), `0x23` en a **deux** (`FinishUnitTurn(unit, isTerminated)`, deja etabli
par `spawn.py` et `FinishUnitTurnBehaviour$$Execute`). Les trois fonctions « fin de tour d'unite »
sont adjacentes dans l'interface.

⇒ Ce qui bloque le port de `VerifyUnitTurnEnded` n'est donc **pas** l'ancrage, mais le **CORPS** :
`HasTilesToMoveTo` = `<IMovementQuery slot 3>` = `MovementQuery$$GetMovableTilesFor`, que le moteur
offline ne CALCULE pas — il le RECOIT du RPC `aiMovableTiles` (`engine/services/movement_query.py`
prend `movable_tiles` en ENTREE). C'est la vraie forme du residu `#287-r1-r1`.

## 3. QUI LIT le flag, et qu'en fait-il — la ventilation, pas la liste

C'est la question qui decide si l'absence rendait le port **permissif**. Meme scan (etapes 1 et 2) :

**DECISION moteur** :
* `IdunBattle.Entities.UnitExtensions$$HasActionLeft` = `(entityType in {Unit(1), Machine(6)}) &&
  !UnitFlagsComponent.Has(flags, 4)` — lu par
  `IdunBattle.AI.OperationalDeciders.AnAiGroupOperator$$GetValidUnits` (`HasActionLeft(u) &&
  !IsDead(u) && baseUnit@+0x60 < 0x3e9`) et `IdunBattle.Operations.PlayAutomaticUnitsOperation$$
  Execute` (`for i in 0..4: if HasActionLeft(u) -> ComputerAction(u, false)`). **Ce sont les deux
  boucles qui TERMINENT grace a lui** ;
* `IdunBattle.Core.Services.BattleQuery$$GetUsableUnitsFor` (2 sites : les unites, puis la MoW) —
  une unite marquee n'est plus « utilisable » ;
* les trois `VerifyUnitsTurnFinishedOperation$${Execute, VerifyUnitTurnEnded, VerifyMachineTurnEnded}`
  — qui arbitrent pose et retrait.

**STREAM seulement, aucune decision** : `IdunBattle.Operations.ReAddMachineOperation$$Execute` et
`IdunBattle.Operations.ResurrectUnitOperation$$SendStreamEvents`, qui publient
`TagKey.UnitStats_ActionsAvailable = HasFlag(u, 4) ^ 1` ; plus **11** sites `IdunBattle.View.FSM`
via `HasActionLeft` (selection a la souris).

**NON couvert par l'axe « immediat », et NOMME** : 9 sites dont le flag arrive par un REGISTRE
(le probe les enumere un par un — un compte non enumere se lirait « rien a signaler »). Aucun
n'ouvre une voie de lecture cachee du flag 4 **sauf** les trois generiques DSL
(`HasFlagAbilityTrigger$$ShouldTrigger`, `UnitsWithFlagSelector$$Select`,
`RemoveFlagBehaviour$$Execute`) : une ability dont la config nomme le flag 4 le lirait par la.
Aucune n'a ete trouvee, mais ce n'est pas mesure ici.

**REPONSE A LA QUESTION** : l'absence du flag n'etait PAS inerte. `has_action_left` est deja mirroree
cote port (`runner/operations/summon_ai.py`) et gate `ai_control_execute_for_group` — sans la pose,
elle rendait `True` **pour toujours**, et la boucle ne terminait que grace a une pose compensatoire
ecrite a la main.

## 4. Le doublon — il existait, et il est RESORBE (pas supprime)

`ai_control_execute_for_group` posait `NO_ACTION_AVAILABLE` **directement sur le composant**, en
`finally` de chaque passe, « pour sortir de la boucle ». C'etait la seule ecriture du flag dans tout
le port.

Elle **reste necessaire** — ce n'est pas un doublon du branchement de `FinishUnitTurnOperation` : le
natif arrive au flag par `AiControl$$ApplyAiMessages` -> `FinishUnitTurn`, chaine que
`decide_and_apply` ne joue PAS (il applique directement `MoveUnitOperation` / `AttackDamageOperation`).
Ce qui a change, c'est qu'elle passe desormais **par le foyer** (`MarkUnitAsNoActionAvailableOperation`)
au lieu d'ecrire le flag a la main : une seule source de verite.

## 5. L'objection qui retenait cette pose depuis deux tranches — MESUREE

`runner/operations/spawn.py` et `runner/operations/summon_ai.py` la refusaient toutes deux, au meme
motif : « le flag, sans son retrait (`VerifyUnitTurnEnded`, non porte), SURVIT au turn-start
(`RemoveTurnFlags(includeNoAction=0)`) et FIGE l'unite — `has_action_left` etant le gate de
`ai_control_execute_for_group` ».

Ce qui manquait au raisonnement : `ai_control_execute_for_group` n'est atteint que par
`ComputerActionOperation.execute_group`, et **tous** les call-sites natifs recenses passent
`resetTurnFlags = 1` (`SupremeCommanderAbility`, `CultDemagogueAbility`, `WaaaghAbility`,
`ReanimationBeamAbility`, `BlackRage_ActivationAbility`, `AdaptiveStrategyAbility`) —
`RemoveTurnFlags(True, True)` **efface** le flag juste avant la boucle. Et la passe automatique du
turn-start (`run_ai_control_pass` -> `collect_ai_controlled`) filtre sur `TurnEnded()` (flag 3), pas
sur le flag 4.

Le flag collant n'a donc **aucun lecteur effectif** offline. `test_287r1_no_action_available_offline.py`
le mesure de bout en bout, **avec sa contre-epreuve** : sous `reset_turn_flags=False`, les memes
unites sont bien ECARTEES — sans quoi « les deux unites jouent » ne prouverait pas que le flag est lu.

## 6. Ce que le port a construit

| piece | ou |
|---|---|
| `MarkUnitAsNoActionAvailableOperation` (foyer unique, `reverse`) | `runner/operations/turnflow.py` |
| branchement en queue de `FinishUnitTurnOperation.execute` | idem |
| routage de la pose compensatoire par le foyer | `runner/operations/summon_ai.py` |
| recensement binaire ecrivains/lecteurs | `scripts/python/probe_287r1_no_action_available.py` |
| generalisation transverse (2 bras opposes) | `scripts/python/probe_287r1_flags_transverse.py` |
| cliquet offline (8 tests, 4 etages) | `tests/engine/runner/test_287r1_no_action_available_offline.py` |

## 7. Validation

**Le test #287 a CHANGE DE SENS, et c'etait l'objet de la tranche.**
`test_le_switch_ne_pose_pas_le_flag_moved` exigeait `live_added - off_added == {4}` (il ENCADRAIT le
residu) ; il exige desormais l'**egalite d'ensembles**, bilaterale — ni flag manquant, ni flag en
trop. Deux regimes TEMOINS y ont ete ajoutes, parce qu'une egalite entre deux ensembles VIDES
passerait trivialement : le natif doit poser au moins un flag, **et** il doit poser
`NoActionAvailable`. Les ordinaux nus (`MOVED, NO_ACTION = 0, 4`) passent par `UnitFlag`.

| epreuve | avant | apres |
|---|---|---|
| `test_sorcerous_facade_combat_live.py` | 9/9 (avec l'ecart `{4}` encadre) | **9/9**, ecart = `set()` |
| `test_287r1_no_action_available_offline.py` | — | **8/8** |
| `test_turnflow_endturn_flags.py` + 3 fichiers offline | 51/51 | **51/51** |
| `probe_181` (masques) / `probe_120` etape 0 / `probe_313` / `probe_273` / `probe_365` | verts | **verts** |

**GENERALISATION** (`probe_287r1_flags_transverse.py`) — le residu etait annonce transverse, il
fallait le montrer AILLEURS que sur 1100. Autre board (`C1_74`, pas `MC1_67`), autre seed (34117,
pas 28701), roster inverse, et une **attaque normale** (id concret **69**, pas l'ability 1100) :

| bras | natif | port | verdict |
|---|---|---|---|
| `attaque` (attaque normale commandee) | `[1, 2, 3, 4]` | `[1, 2, 3, 4]` | **accord EXACT, bilateral** |
| `apres_deplacement` (une autre unite BOUGE) | `[0, 1, 4]` | `[0, 1]` | ecart `{4}`, RESTRICTIF, borne |

⚠ **Le 2e bras a REFUTE l'attente avec laquelle il avait ete ecrit.** Il attendait « aucun flag 4,
ni live ni port » — le natif le pose pourtant, **sans** poser `TurnFinished` (3). Ce n'est donc pas
`FinishUnitTurn` : c'est la seconde voie, `VerifyUnitTurnEnded` (§2). Le bras a ete RECRIT pour
MESURER l'ecart au lieu de l'attendre a zero, avec deux bornes : il vaut EXACTEMENT
`{NoActionAvailable}` (tout autre flag rougit) et il est RESTRICTIF (le port ne pose que par
`FinishUnitTurn`, donc il est un SOUS-ENSEMBLE du natif — **jamais permissif**, ce qui est la
propriete qui compte pour un moteur d'entrainement).

**CONTRE-EPREUVE**, mutation verifiee (le texte du fichier a change, grep a l'appui) : pose retiree
de `FinishUnitTurnOperation.execute` ->
* LIVE **ROUGE** : `le natif pose des flags que le port ne pose PAS : live=[1, 2, 3, 4]
  port=[1, 2, 3] (manquants=[4])` — c'est-a-dire exactement le fait d'origine ;
* OFFLINE **6 rouges sur 8** (les 2 verts testent l'Operation elle-meme, non mutee).
Arbre restaure, verts re-joues.

**NON COUVERT** :
1. le RETRAIT et la POSE par `VerifyUnitTurnEnded` -> residu `#287-r1-r1`, **chiffre** ci-dessus.
   Le blocage n'est PAS l'ancrage (lu, §2) mais `HasTilesToMoveTo`, non derivable offline ;
2. la pose PRECOCE d'`ActiveAbilityOperation$$ExecuteInternal` n'est pas mirroree a sa place exacte
   (equivalente sur l'observable final, cf. §2) ;
3. les trois generiques DSL qui pourraient lire le flag 4 par configuration ne sont pas balayes ;
4. l'event de stream `TagKey.UnitStats_ActionsAvailable` n'est pas emis (couche non suivie) ;
5. le bras `apres_deplacement` n'est mesure que sur **un** couple (board, unite) : l'amplitude du
   residu (combien d'unites, a quels moments) n'est pas chiffree.
