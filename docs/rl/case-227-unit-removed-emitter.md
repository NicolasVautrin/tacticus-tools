# case-227 -- `On(UnitRemoved = 0x25)` : le vecteur sans emetteur

Residu de #213 (`GhostRevive` / `TimeFlux_Revive`, effet 1186). Fiche a l'etat FINAL.

## Verdict binaire

**NON** : au commit `b80cd84` (`origin/master` du 2026-07-29), `On(UnitRemoved = 0x25 = 37)`
n'avait **aucun emetteur de production** cote port. Le vecteur `unit_removed_triggers`
(`engine/runner/operations/triggers/dispatch/move_death.py`) existait, etait exporte, etait
enregistre -- et n'etait appele par **aucun** site du moteur (re-derive par grep : les seules
occurrences etaient la definition, les deux re-exports `__init__.py`, et une docstring).

## Chaine native (citee par symboles)

```
IdunBattleLogic.Entities.DSLFactory$$RemoveUnit(sel)                        (feuille DSL)
  -> IdunBattle.Entities.Behaviours.RemoveUnitBehaviour$$Execute
       resout le selecteur +0x50 (groupType 3), puis PAR UNITE :
       slot +6 de l'interface `Core.Services.OperationProcessor` avec (unitId, 1, 0)
  -> Core.Services.OperationProcessor$$RemoveUnit                (gate `this+0x1f0 != 0`)
  -> IdunBattle.Operations.RemoveUnitOperation$$Execute(state, entity, removeEffects=1, param4=0)
```

### `RemoveUnitOperation$$Execute` -- sequence LUE au decompile

Signature effective : `(operationCtx, entity, removeEffects, skipSlot0x55)`.
`operationCtx+0x10` = `MatchState`, `+0x18` = journal d'events de match, `+0x20` = logger,
`+0x28` = `OperationProcessor`.

1. `entity == 0` -> log d'erreur, **return** (aucune mutation).
2. `IdunBattle.Entities.EntityExtensions$$IsUnit(entity)` faux -> log d'erreur, **return**.
3. **GATE** `IdunBattle.Entities.UnitExtensions$$HasFlag(entity, 0x1a)` vrai -> log (StackDict),
   **return**. `0x1a = 26 = UnitFlag.Removed` (`enums.tsv`,
   `IdunBattle.Entities.Enum.UnitFlag`) -> anti-double-retrait.
4. gate d'appartenance : `MatchState` slot 0x2f -> collection, slot 4 `(entity)` -> bool.
   Faux -> log d'erreur, **return**.
5. log << removing unit >> (alloc d'un message, champ `+0x20 = entity`).
6. `OperationProcessor` slot 7 `(entity, false)`.
7. `PlayerComponent` du proprietaire (`MatchState` slot 0x29 -> player entity) :
   `List.Remove(unitId)` sur `+0x30`, puis `List.Add(unitId)` sur `+0x38`
   (la liste des unites RETIREES -- cf. `playbook/noncomparable/doctrina_imperatives.py`).
8. `MatchState` slot 0x32 `(entity, options)` -- retrait du plateau.
9. `IdunBattle.Entities.Components.UnitFlagsComponent$$Add(entity, 0x1a)` -- pose `Removed`.
10. sur un composant de l'unite : `+0x17c = TurnComponent$$GetAmountOfTurnsStartedByPlayer(matchTurn,
    ownerId)` et `+0x180 = 1` (tour de retrait + booleen).
11. si `param4 == 0` : `OperationProcessor` slot 0x55 `(entity, false)`.
12. **event de match** : `journal` slot 2, type `0xc`, payload `Dictionary` =
    `{0x88: HasFlag(entity, 6=Dead), 0x89: HasFlag(entity, 8=Overkilled)}`.
13. **PUBLICATION `On(0x25)`** : `OperationProcessor` slot 0x51 avec
    `(a = entity, b = entity, c = entity, eventType = 0x25, options = {0,0})`
    -> **actor = caster = target = l'unite retiree**.
14. si `removeEffects != 0` : bloc INLINE identique a
    `IdunBattle.Operations.RemoveUnitOperation$$RemoveEffects` -- `OperationProcessor` slot 0x5a
    `(entity, options{0,0})`.
15. `OperationProcessor` slot 0x2f avec `{5, 0}`.

**Ordre load-bearing pour le port** : l'event `On(0x25)` part **APRES** la pose du flag
`Removed`, le retrait du plateau et la purge de la liste du joueur, mais **AVANT** la
consommation des effets portes par l'unite (etape 14). Un port qui consommerait les effets
d'abord rendrait invisible, aux consommateurs de `On(0x25)`, tout effet porte par l'unite
retiree.

### Call-sites natifs de la feuille `DSLFactory$$RemoveUnit` (xrefs, 6 sites / 5 abilities)

| Ability native | Statut du port |
|---|---|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour` (x2) | PORTEE (`runner/abilities/loki/mv71.py`) |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HunterOfSoulsAbility$$CreateBehaviour` | non portee |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.NoHidingFromTheWatchers_LeaveBattleAbility$$CreateBehaviour` | non portee |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PriorityReclamation_EndTurnAbility$$CreateBehaviour` | non portee |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AggressiveOnslaught_UnsummonAbility$$CreateBehaviour` | non portee |

## Rayon de souffle, MESURE (pas herite)

`python scripts/python/probe_227_unit_removed_blast_radius.py` balaie les quatre registres
(`TRAIT_` / `ABILITY_` / `ACTIVE_ABILITY_` / `EFFECT_TRIGGERS`) et grep les appels du vecteur.

| | avant | apres |
|---|---|---|
| ecouteurs portes de `On(0x25)` | **1** (`GhostRemoveOnSourceRemoved`, effet 1186) | 1 |
| emetteurs de production | **0** | **1** (`operations/remove_unit.py`) |

**Atteignabilite des porteurs natifs** (ventilation `unit_map.py find --ability`, gate
HERO/MoW/SUMMON -- jamais `kind == lineup`) :

| ability native (`RemoveUnit`) | porteur(s) | pool | ce qui est retire |
|---|---|---|---|
| `MV71SniperDroneSquad` | `tauMarksman` (Sho'syl) + 4 npc | **hero, DANS le pool** | un drone `tauSmnDroneSniper` |
| `AggressiveOnslaught` | `bloodIntercessor` (Mataneo) | **hero, DANS le pool** | `Children(Owner)` = ses summons |
| `HunterOfSouls` | `thousSmnDaemonPrince` (Z'Kar) | summon (via son summoner) | **le porteur lui-meme** (`Owner`) |
| `NoHidingFromTheWatchers` | `darkaNpc4Watcher` (npc) + `darkaSmnWatcher` (summon) | summon | -- (non porte) |
| `PriorityReclamation` | **aucun porteur** au gameconfig | -- | -- |

Cote PORT, un seul de ces call-sites est porte : `MV71SniperDroneSquadAttackAbility$$
ExecuteBehaviour` (`runner/abilities/loki/mv71.py`). La feuille DSL `RemoveUnit`
(`abilities/behaviours/lifecycle.py`) n'a, elle, **aucun instanciateur** dans le port.

**Chiffre honnete de l'atteignabilite du CONSOMMATEUR** : `GhostRemoveOnSourceRemoved` exige que
le POSEUR du ghost (`thousTerminator`, Toth) soit retire. Aucune des cinq abilities natives ne
retire Toth (MV71 retire un drone, AggressiveOnslaught des summons, HunterOfSouls son propre
porteur). **En bataille reelle le trigger reste donc inerte** -- ce que ce foyer corrige est la
FIDELITE STRUCTURELLE (l'Operation existe, emet, et se gate), pas un comportement observable
en partie. La garde exerce le consommateur en appelant l'Operation directement sur Toth : c'est
legitime, c'est exactement ce que fait `HunterOfSouls` sur SON porteur.

## Ce que le fix pose

Nouveau module `scripts/python/engine/runner/operations/remove_unit.py` --
`RemoveUnitOperation.execute(state, unit_id, *, remove_effects=True)`, mirror de la sequence
ci-dessus, avec ses gates (entite inconnue / pas une unite / **flag `Removed` deja pose**), la
pose de `UnitFlagsComponent.REMOVED (26 = 0x1a)`, la publication d'`On(0x25)` **puis** la
consommation des effets portes.

Cablage -- les DEUX sites de despawn du port passent desormais par l'Operation :
  * `abilities/behaviours/lifecycle.py::RemoveUnit.execute` (feuille DSL -> Operation, #149) ;
  * `abilities/loki/mv71.py::_remove` (eviction (a) tuile occupee et (b) cap `maxSummons`).

Deux ajouts de fidelite dans le meme foyer :
  * `UnitFlagsComponent.REMOVED = 26` (le flag manquait -- d'ou l'absence de gate) ;
  * `operations/resurrect.py` : `fl.remove(REMOVED)`, mirror du `Remove(0x1a)` que
    `ResurrectUnitOperation$$Execute` fait dans la meme rafale que `Remove(6)/Remove(0xf)/
    Remove(8)/Remove(9)` -- la docstring le citait deja sans pouvoir le porter. Ferme le cycle
    pose/retrait du flag.

### Collapses et residus assumes

  * **etape 8** (`MatchState` slot 0x32, retrait des tuiles) -> `UnitComponent.alive = False`.
    C'est ce que les deux sites faisaient deja et c'est ce qui LIBERE l'occupation
    (`_occupied` / `CanAddUnit` excluent les non-`alive`) -- indispensable au spawn qui suit
    l'eviction MV71. Le natif, lui, ne touche NI les PV NI le flag `Dead (6)` : l'ecart est
    INCHANGE par ce foyer, il est seulement desormais NOMME. Une unite retiree reste donc
    indistinguable d'une morte pour les selecteurs du port (`_valid_dead_decoys`,
    `post_unit_kill_triggers_for_move`, ...). **Residu ouvert** : si un port futur a besoin de
    separer << mort >> et << retire >>, c'est ici qu'il faudra introduire un predicat
    d'occupation qui lise `REMOVED` plutot que `alive`.
  * **etapes 7, 10, 12** : `PlayerComponent.units`/`removedUnits` (`+0x30`/`+0x38`), le tour de
    retrait (`+0x17c`/`+0x180`) et l'event de match `0xc` `{0x88: Dead, 0x89: Overkilled}` ne
    sont pas portes -- aucun consommateur porte ne les lit.
  * **etapes 6, 11, 15** : slots `OperationProcessor` 7, 0x55 et 0x2f non identifies et non
    portes (le 0x2f est le meme appel de cloture qu'en fin de `ResurrectUnitOperation$$Execute`,
    non porte la-bas non plus).

## Validation

`python scripts/python/probe_227_remove_unit_operation.py` -- deux faces, etat LIVE-capte :

  * **FACE A** (discriminante, runner Toth + `orksNob`, board `MC1_67`, seed 31337) :
    ghost pose sur la tuile de debut de tour (`21`) ; apres `RemoveUnitOperation` :
    `ghosts=[]`, `flag Removed=True`, 2e appel -> `None` (le gate mord).
    **CONTRE-EPREUVE dans le meme run** : le despawn << a l'ancienne >> (`alive=False` +
    consommation des effets PORTES par Toth, sans event) laisse `ghosts=[21]` -- le ghost est
    porte par la TUILE, donc rien d'autre que l'evenement ne le retire.
  * **FACE B** (non-regression du seul call-site, runner Sho'syl + `astraBullgryn`) :
    4 casts -> `spawned=[1],[2],[3],[4]`, `evicted=[1]` au 4e ; l'evince porte `Removed` ;
    3 drones vivants = cap natif `maxSummons` 3.

Garde pytest : `scripts/python/tests/engine/test_unit_removed_vector_live.py` (6 tests, verts).
**Mordant verifie par DEUX mutations adversariales** :

| mutation | resultat |
|---|---|
| neutraliser `unit_removed_triggers(...)` dans l'Operation | `test_removing_the_ghost_source_dissipates_the_ghost` ROUGE (`[21] != []`) |
| supprimer `fl.add(REMOVED)` | ce meme test **et** `test_mv71_eviction_goes_through_the_operation` ROUGES |

Non-regression : `probe_213_ghost_revive.py` VERDICT OK apres le foyer (hp de revive
live == port == 3290, position de revive `(1,2)` identique) -- c'est le probe le plus expose,
puisqu'il exerce a la fois `GhostEffect` et `resurrect.py`.

### Ce qui n'est PAS couvert

  * Aucune confrontation LIVE du CONSOMMATEUR : le natif n'offre aucun chemin pour retirer Toth
    (cf. tableau d'atteignabilite). La face A confronte le port a lui-meme sur un etat live-capte
    avec contre-epreuve ; elle ne dit rien de ce que ferait le natif dans cette situation.
  * L'ecart `alive=False` vs `Removed` (le natif garde l'unite vivante hors plateau) n'est pas
    mesure live -- il faudrait observer ce que `decisionView`/`observeBattle` rapportent d'un
    drone MV71 evince cote natif.
  * Les quatre autres call-sites natifs de `RemoveUnit` restent non portes ; deux d'entre eux ont
    un porteur au pool (`bloodIntercessor` / `AggressiveOnslaught_Unsummon`, et
    `thousSmnDaemonPrince` / `HunterOfSouls` par son summoner) -- ce sont les candidats naturels
    pour donner au vecteur un chemin de production supplementaire.
