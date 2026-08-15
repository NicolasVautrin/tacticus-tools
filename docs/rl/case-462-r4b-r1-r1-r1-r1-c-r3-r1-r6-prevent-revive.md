# #462-r4b-r1-r1-r1-r1-c-r3-r1-r6 (+ #448-r1-r1-r3, #448-r1-r2-r1, #462-...-r5-r5) — le RANG, et le flag qui manquait

Tranche ENGINE, foyer `runner/operations/movement.py`. Quatre residus, **trois premisses fausses
sur quatre** — et la quatrieme etait fausse *dans l'autre sens* : elle annoncait un risque de
divergence la ou il n'y en a pas, en taisant celui qui existait.

| residu | premisse | verdict |
|---|---|---|
| `#448-r1-r1-r3` | « double parcours, aucun risque de divergence » | **FAUSSE ×2** — c'est TRIPLE, et c'est un ecart de RANG. **CORRIGE** |
| `#448-r1-r2-r1` | « la RESERVATION n'est pas portee » | **PERIMEE** — tout porte depuis #550-r1. Regime MONTE, 4/4 |
| `#462-…-r5-r5` | « pose sur multi-hex indistinguable » | **REFUTEE par le decompile** — le port est FIDELE. 6/6 |
| `#462-…-r6` | « la famille revive peut ANNULER un crush » | **REFUTEE** — et le port avait le bug INVERSE. **CORRIGE** |

## 1. `#462-…-r6` — un CRUSHE ne peut JAMAIS etre revive

### L'etage que la fiche `-r1` §6 saute

`IdunBattle.Core.Services.BattleQuery$$CanBeRevived(target, healType)` a **CINQ** etages, lus :

```
GetStat(target, 5 = Health) < 1
&& UnitExtensions.IsAffectedByHealType(target, healType)
&& !UnitExtensions.HasFlag(target, 0xd)              <-- CELUI-CI
&& !UnitExtensions.HasTrait(target, 0x41a = PermaDeath)
&& !UnitExtensions.HasHealBlockers(target)
```

`0xd = 13 = UnitFlag.PreventRevive` (`data/symbols/t6dpr4k06g/frida/enums.tsv`, **LU**). Le §6
enumere `PermaDeath` et le heal-type, et conclut « `CanBeRevived` passe sur un decoy [...] donc un
apothicaire adjacent **peut** annuler un crush ». Il manque le 3ᵉ etage.

### Qui pose le flag, et sous quel gate

`IdunBattle.Operations.KillUnitOperation$$Execute`, lu :

```csharp
bool preventRevive = options.<+0x45> ? true : UnitExtensions.IsSteppable(killed);
if (options.<+0x46> && CanBeOverkilled(killed))  flags.Add(0x08 = Overkilled);
if (preventRevive)                               flags.Add(0x0d = PreventRevive);
```

et `IdunBattle.Operations.KillUnitOperationOptions$$ForSteppable` ecrit littéralement
`*(undefined2 *)(opts + 0x44) = 0x101` ⇒ **`+0x45 = 1`**. Un crushe le recoit donc **sans
condition** ; hors crush (`ForDefault`, les 0x48 octets a zero) c'est `IsSteppable(killed)` qui
decide, donc **tout `Steppable` mort**, quelle qu'en soit la cause.

### LE RANG, qui est tout — et qui refute la justification du port

Aux adresses de retour de `KillUnitOperation$$Execute` :

```
RecordDeathReason               (gate +0x44)
flags.Add(0x08 = Overkilled)    (gate +0x46 && CanBeOverkilled)
flags.Add(0x0d = PreventRevive) <-- ICI
On(1 = PreUnitDeath)            <-- LE VECTEUR QUI PORTE LES REVIVES
<garde revive : UnitComponent+0xa8 = PendingRevive>
On(2) / Add(6 = Dead) / RemoveEffects(0) / RemoveEffects(1) / On(0) / On(0x36) /
RemoveEffects(2) / +0xa8 = 0 / On(0x35)
```

Le flag tombe **AVANT** le vecteur. `revive_effect.py::can_be_revived` ecrivait pourtant :
« Flag 0xd (**pas encore pose a l'instant de l'OnPreDeath**) [...] -> non-bloquant ». C'est une
**justification ecrite, et elle etait fausse** — le port ressuscitait un crushe que le natif refuse.
Degradation **PERMISSIVE** : ni erreur ni crash, donc invisible en self-play.

### Mesure, avant -> apres (`probe_462r4br6_revive_apres_crush.py`, `C4_09`)

| etage | avant | apres | natif |
|---|---|---|---|
| `UnitFlag.PreventRevive` pose sur le crushe | NON (`flags=[]`) | **OUI** (`flags=[13]`) | pose |
| `can_be_revived(crushe)` | `True` | **`False`** | `False` |
| TEMOIN — `can_be_revived(mort ORDINAIRE)` | `True` | `True` | `True` |

Le temoin est ce qui etablit que le gate mord **sur le seul regime vise** : un correctif qui
refuserait aussi les morts ordinaires serait un refus INVENTE, pas un mirror.

### Les quatre pieces

| piece | fichier |
|---|---|
| la constante `PREVENT_REVIVE = UnitFlag.PreventRevive` | `runner/components.py` |
| la POSE au rang natif + son gate (`prevent_revive_option` = `KillUnitOptions+0x45`) | `runner/operations/damage.py` |
| la LECTURE (3ᵉ etage de `CanBeRevived`) | `runner/operations/triggers/revive_effect.py` |
| le cablage du crush (`+0x45 = 1`) | `runner/operations/movement.py` |

`remove_turn_flags` ne retire pas `0xd` (il retire `{2,3,0x1b}` + `{4}` + `{0,0xc,1}`) : le flag
SURVIT au changement de tour, comme au natif. Et `_load_unit_flags` materialise le composant sur
**toute** ligne mesuree (#545), donc le gate mord aussi sur un etat charge du live — ou le capteur
seede d'ailleurs le flag natif par un canal independant.

### Ce qui reste NON couvert (residu `-r6-r2`)

`HazeCorruptionBonusHitAbility` et `DawnBladeHealAbility` restent en verdict **analytique** : leur
gate est lu, aucune confrontation live. La famille revive, elle, sort du blast radius — non pas
« confrontee » mais **eliminee par le decompile**.

## 2. `#448-r1-r1-r3` — le compte de tuiles etait re-derive APRES la mutation

L'enonce se trompait deux fois.

**(1) « double » est TRIPLE.** `_calculate_path` est arrive avec #448-r1-r1-r2-r2, *apres* la
redaction du residu, et ajoute un `_dijkstra_by_pos` complet.

**(2) « aucun risque de divergence » est FAUX.** `_num_tiles_moved` est pure en ses ARGUMENTS mais
LIT `state` (`_blocking_positions` derive des occupants ennemis VIVANTS). Or les deux appels du port
ENCADRAIENT `_kill_steppable_units` et toute sa cascade de mort.

Le natif n'a qu'**un** point de calcul : `CalculatePaths` produit `path` **et** `connectedPath` dans
le meme appel, avant toute mutation, et `Execute` ne les CONSOMME que bien plus bas
(`movementSteps = path.Count`, `RecordTilesMoved(GetNumTilesMoved(connectedPath))`) — sur des listes
**figees**.

### Mesure (`probe_448r1r1r3_double_parcours.py`, `C4_09`, 70 mouvements)

| | parcours / move | ms / move |
|---|---|---|
| AVANT | 2,83 | 1,38 |
| APRES | **1,91** | **0,91** |
| gain | **-32,3 %** | **-34,1 %** |

Le AVANT/APRES est mesure **dans un seul arbre** : le probe RECONSTITUE le regime d'avant en
rejouant, apres le mouvement, le `_num_tiles_moved` que `record_tiles_moved` faisait a ce rang-la.

**Le plancher fidele est DEUX, pas un** : `CalculatePaths` appelle `Pathfinders.<slot 4>` PUIS
`BattleQuery.<slot 0x15>` — deux parcours natifs distincts, et le second ne voit **ni** les options
**ni** l'override. Deriver le compte de `last_path` serait INFIDELE.

### Le RANG mord, et c'est mesure

* **RANG** : `_num_tiles_moved` appele **1 fois** (contre 2), le mover encore a sa tuile de depart.
* **DIVERGENCE**, `(0,0) -> (0,2)` avec un bloqueur ennemi en `(0,1)` (chemin 11 nœuds avec lui,
  3 sans) : le port enregistrait `tiles_moved = 2` la ou le natif ecrit **10**, pendant que
  `movement_steps` restait a **11**. C'est ce dernier, **INCHANGE**, qui etablit que la cause est le
  RANG et non la geometrie.

Le regime est monte de facon SYNTHETIQUE (un stub tue le bloqueur pendant la cascade), parce
qu'aucune ability du registre ne le fait offline ; la voie NATURELLE est le blast radius du §1.

## 3. `#448-r1-r2-r1` — premisse PERIMEE, regime MONTE

Les trois pieces existent depuis #550-r1 : `SetReservation`, `RemoveReservation`, et leur lecteur
G6 `IsPositionReservedForOtherUnit`. Les trois mirrors natifs, relus, sont exacts.

⚠ **Detail corrige** : `_remove_reservation` annoncait « quatre call-sites natifs » et en enumerait
quatre en OUBLIANT la RELANCE, que le port jouait pourtant deja. Les xrefs rendent **TROIS**
`UNCONDITIONAL_CALL` pour **CINQ** chemins logiques : le label d'abandon PARTAGE (ou convergent
`TilesAreEmpty` faux, `!ovr.HasValue || IsDead`, et `path` vide), la relance, et le nominal.

**Ce qui restait vrai** : la reservation n'a aucune duree de vie hors d'un mouvement — les quatre
autres poseurs (`DSLBehaviors$$Reserve` : `TheQuickening` ×2, `NovaBoost`, `EreWeGo`, `ItItches` ×2)
la retirent dans le meme arbre. G6 ne peut donc mordre que sur un mouvement **IMBRIQUE**.

`probe_448r1r2r1_reservation_regime.py` monte ce regime — **4/4** :

| bras | resultat |
|---|---|
| B1 TEMOIN — U2 atteint la tuile hors regime | MORD |
| B2 REGIME — pendant le move de U1, U2 est refuse | `position-reserved` |
| B3 CONTRE-EPREUVE — `SetReservation` no-op | U2 PASSE et se SUPERPOSE |
| B4 CYCLE — apres le move | 0 reservation ; refus suivant = `tiles-not-empty` |

B3 est ce qui etablit que le refus de B2 vient de la reservation et pas d'ailleurs.

## 4. `#462-…-r5-r5` — le multi-hex, tranche par le decompile

Le residu craignait que le natif appelle `SetUnitPosition` **par pas**. Il ne le fait pas. Dans
`MoveUnitOperation$$Execute`, branche reelle :

```
processor.<slot 0x7e>(unit, position, false)   <- UNE SEULE FOIS, destination COMPLETE
<log>
if (path.Count == 1) AddMoveEvent(...)
else for (i = 1; i < path.Count; i++) AddMoveEvent(...)   <- LA BOUCLE PAR PAS EST ICI
```

et `MoveUnitOperation$$AddMoveEvent` **ne touche aucun composant ECS** (un `Dictionary<int,int>`
pousse par `AddStep(3, unit.Id, dict)` — canal de VUE). Le seul ecrivain de `PositionComponent+0x88`
est `SetUnitPositionOperation$$SavePreviousPosition`, dont l'entree `previousPosition =
GetUnitPosition(unit, state)` est capturee **avant** la boucle d'ecriture des pieds.

⇒ `PreviousTile` = la tuile de **DEPART du mouvement entier**, quelle que soit la longueur du
chemin. Les deux lectures que le residu declarait indistinguables ne le sont pas : **la seconde
n'existe pas**.

`probe_462r4br5r5_pose_multihex.py --volet offline`, **6/6** sur un chemin de 4 nœuds
`(0,0) -> (0,1) -> (0,2) -> (0,3)` — dont un controle de **non-degenerescence** (l'avant-derniere
tuile, `(0,2)`, DIFFERE du depart : sans lui, l'accord serait vrai pour la mauvaise raison) et un
compteur d'ecritures (`save_previous_position` appele **une** fois, avec `[(0,0)]`).

**Et la condition de retournement que le residu exigeait a ete JOUEE, natif contre port**
(`--volet live`, `MC1_67`, `astarCyrus` injecte au catalogue, `Movement` releve a 25 pour que le pas
de 2+ hex entre dans `aiMovableTiles` — le montage est CRAFTE, pas subi) :

| | valeur |
|---|---|
| deplacement | `(1,0) -> (0,1)`, distance hex **2** |
| chemin | `[(1,0), (0,0), (0,1)]` — 3 nœuds, avant-derniere `(0,0)` **DIFFERENTE** du depart |
| mine NATIF | `[(1,0)]` = la tuile de **DEPART** |
| mine PORT | `[(1,0)]` — **meme tuile** |

Les trois assertions passent, dont « elle n'est PAS sur l'avant-derniere du chemin ». Le regime
est donc **non degenere** et le port **fidele**.

## 5. Deux ROUGES de `master` trouves en chemin

### (a) REPARE — la contre-epreuve du dispatch de pathfinder etait DESARMEE

`test_448_r1_r1_r1_r1_flying_tiles_moved_live::test_le_walkpathfinder_diverge_sur_letat_live`,
ROUGE sur `88471bcd` (reproduit avec le `movement.py` de master, donc sans rapport avec cette
tranche). Le montage etait **SAIN** : 3 porteurs, dispatch mesure `Fly` et `TeleportStrikeFly` ×2.
C'est le **PATCH** qui etait inerte — le test fait `MQ.get_pathfinder_type_for_unit = lambda: 0`,
mais `movement.py` importait ce nom en **forme A**, donc la substitution ne mordait pas et la
contre-epreuve comparait le port **a lui-meme** : ensemble vide, quel que soit le board.

C'est le gisement « HISSER EN FORME A fait passer de MORD a NE MORD PAS » du CLAUDE.md, pris dans
l'autre sens : on RE-DESCEND en forme B, ce qui ne peut que **re-armer** un patch. Cout en cascade
nul, valeur inchangee. Le fichier passe **8/8 avec sa version d'ORIGINE** — aucune modification du
test.

### (b) SIGNALE, non repare — `test_narthecium_revive_live.py`

**3 rouges sur `master`** (`test_revive_base_hp_and_position`, `test_no_overkill_revives`,
`test_once_per_turn`), reproduits avec les quatre fichiers de cette tranche restaures a `88471bcd`.
**Non aggrave** par la tranche : 6 passed / 3 failed avant comme apres.

Signature utile : **tous** les bras « revive attendu » sur `ally = bloodIntercessor` echouent,
**tous** les bras « revive refuse » passent, et le meme scenario sur `ally2 = eldarRanger`
(`test_…_ally2`) **PASSE**. Ce n'est donc ni le montage global ni le trigger : c'est specifique a ce
porteur. Traits mesures de `bloodIntercessor` sur un autre montage : `Flying, Hero, Imperial,
RapidAssault, TeleportStrike`. Piste : un etage de `can_be_revived` ou du `create_target_filter`
qui le discrimine. Residu `#448-r1-r1-r3-r1` **ne le couvre pas** — foyer distinct, a ouvrir par qui
le prendra.

## 6. Residus ouverts

* **`#448-r1-r1-r3-r1`** — **`_movement_start_position` est portee mais n'a AUCUN appelant.**
  `MoveUnitOperation.execute` passe `old_pos` (la `PositionComponent`, = `currentPosition`) a
  `_calculate_path` / `_num_tiles_moved`, la ou le natif passe `movementStartPosition` — qui vaut
  `previousPositionThisTurn` quand la position courante est VIDE. Consequence mesurable : sur une
  unite HORS PLATEAU, `_calculate_path` rend `[to, to]` (correct, branche
  `movementStartPosition.Count == 0`) mais `_num_tiles_moved` rend **0** la ou le natif rend **1**
  (`GetNumTilesMoved([end,end])`), et `movementSteps` **0** la ou le natif rend **2**
  (`path.Count`). Regimes concernes : `GhostRevive`, `EchoesFromTheWarp`,
  `StormboyzStrike_Fallback`. ⚠ Ne pas cabler a l'aveugle : `movementSteps` est CONFRONTE LIVE
  (#448-r1-r1-r1).
* **`#462-r4b-r1-r1-r1-r1-c-r3-r1-r6-r2`** — `HazeCorruptionBonusHitAbility` et
  `DawnBladeHealAbility` restent en verdict **analytique** (gate lu, aucune confrontation live).
  ⚠ Le numero saute `-r6-r1` : `probe_468 --suggere` a rendu `-r6-r2`, `-r6-r1` etant deja vu par le
  corpus (il lit les worktrees). On ne recycle pas un trou.

## 7. Validation

**Offline — 259 verts.** Item A : `test_448_r1_r1_r2_r2_gates_abandon`, `…_r2_r2_r1_gates_amont`,
`…_r1_r1_flying_tiles_moved`, `…_r1_flying_movement_steps`, `…_full_throttle`, `…_r2_fly_override`,
`…_r2_r1_dsl_after_move`, `test_347_tiles_moved_call_sites` (138). Zone revive/crush :
`test_389r2_kill_unit_remove_effects`, `test_902r1_revive_1547_porte`, `test_564_resurrect_pipeline`,
`test_564r3_gates_resurrect`, `test_955r2_free_tiles_steppable`, `test_462r4eor1_overkill_cardinality`,
`test_revive_retrofit_offline_live` (121).

**Live — 66 verts, 3 rouges PREEXISTANTS.** `test_tiles_moved_combat` (8),
`test_448_r1_r1_full_throttle` (3), `test_448_r1_r1_r1_r1_flying_tiles_moved` (8, **etait rouge sur
master**), `test_448_r1_r1_r2_r2_r1_gates_amont` (1), `test_462_…_c_r3_r1_r1_crush_death_events` (7),
`test_462_…_c_r3_r1_crush_steppable` (6), `test_revive_cancels_death_events` (3),
`test_ghost_revive` (5), `test_rites_of_morkai_revive` (13), `test_tainted_narthecium_revive` (12) ;
`test_narthecium_revive` = **3 rouges de `master`**, non aggraves (§5b).

**Probes** : `probe_448r1r1r3_double_parcours` (mesure + rang + divergence),
`probe_448r1r2r1_reservation_regime` (4/4), `probe_462r4br5r5_pose_multihex` (6/6 offline + 3/3
live), `probe_462r4br6_revive_apres_crush` (5/5).

**NON couvert** : les deux classes du `-r6-r2` ; le crush par `AddUnitOperation` (4ᵉ site natif,
ecart PREEXISTANT) ; `HasHealBlockers` ; `VerifyTerritoryCapture` de
`SetUnitPositionOperation$$Execute`, non porte et non touche ici.
