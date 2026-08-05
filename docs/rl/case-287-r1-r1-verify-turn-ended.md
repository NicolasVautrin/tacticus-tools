# Case #287-r1-r1 — `VerifyUnitTurnEnded` : la voie qui RE-OUVRE l'activation

**Statut** : PORTE + CONFRONTE LIVE, sur les DEUX faces. Residu ouvert par
`case-287-r1-no-action-available.md` §7 (point 1).

#287-r1 avait porte la POSE de `UnitFlag.NoActionAvailable` (par `FinishUnitTurnOperation`), pas son
RETRAIT. Et le flag est **COLLANT** : `IdunBattle.Operations.StartTurnOperation$$Execute` appelle
`IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags(includeNoAction: 0, ...)`, qui
le **CONSERVE**. Une unite marquee une fois le restait donc pour toujours cote port — sur-fermeture
permanente, et `IdunBattle.Entities.UnitExtensions$$HasActionLeft` la voyait finie a chaque tour.

## 1. Ce que la fiche parente annoncait, et que la mesure a REFUTE

> « Le blocage n'est PAS l'ancrage mais `HasTilesToMoveTo` = `MovementQuery$$GetMovableTilesFor`,
> que le moteur offline ne CALCULE pas — il le RECOIT du RPC `aiMovableTiles`. »

**FAUX au commit courant.** `engine/services/movement_query.get_movable_tiles_for` est un
pathfinding offline COMPLET (`movable_positions_for_unit`, les trois etages de `#381-r1`/`#381-r5`)
depuis `#381-r4`. Ce qui prend `movable_tiles` en ENTREE, c'est `get_movable_positions_for` — l'etage
d'EMPREINTE au-dessus, pas le pathfinding. La premiere question de la tranche (« un equivalent
existe-t-il deja ? ») avait donc **une reponse OUI**, et l'ecrire a evite d'ajouter une deuxieme
source de verite : la voie appelle `state_bridge._move_tiles`, le mirror d'`aiMovableTiles` deja
confronte live, qui appelle ce foyer.

Le vrai obstacle etait l'AUTRE predicat, `HasActionAvailable` (§3).

## 2. La RE — la condition COMPLETE

`IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded(unit)`, MIRROR :

```
if (unit == null) throw
flags = unit.GetComponent<UnitFlagsComponent>()                      # throw si absent
if (flags.TurnEnded())                                    return     # tour deja fini
if (unit.TryGetComponent<HealthComponent>(out hp) && hp.IsDead())  return     # morte
if (!flags.Has(UnitFlag.NoActionAvailable)) {
    if (HasTilesToMoveTo(unit))                           return
    if (HasActionAvailable(unit))                         return
    <IOperationProcessor slot 0x76>(unit)     # MarkUnitAsNoActionAvailable  -> POSE
} else {
    if (!HasTilesToMoveTo(unit) && !HasActionAvailable(unit))  return
    <IOperationProcessor slot 0x77>(unit)     # MarkUnitAsActionAvailable    -> RETRAIT
}
```

Les DEUX branches evaluent `HasTilesToMoveTo` **en premier**, et le OU **court-circuite**. Ce detail
n'est pas cosmetique : c'est lui qui rend le port EXACT (§3).

**Les deux predicats**, chacun un slot d'interface identifie par sa SIGNATURE, jamais au jugement :

| predicat | slot | fonction native |
|---|---|---|
| `HasTilesToMoveTo(unit)` | `IMovementQuery` **3**, `(unit, ignoreUnitFlags: false, options: <memset 0>)` -> **bool** | `IdunBattle.Core.Services.MovementQuery$$HasAnyMovablePositionsFor` |
| `HasActionAvailable(unit)` | `IMovementQuery` **0** puis `IDamagePredictionQuery` **1** | `MovementQuery$$GetMovableTilesFor` + `DamagePredictionQuery$$CanAttackAnyUnitFromTilesWithAnyAbility` |

L'interface `IDamagePredictionQuery` est identifiee par le TRIPLET de ses slots voisins, tous
portes par la meme classe : `0` = `CanAttackAnyUnitFromAnyTileWithAnyAbility(unit)`, `1` =
`CanAttackAnyUnitFromTilesWithAnyAbility(unit, tiles)`, `2` =
`MachineCanAttackAnyUnitWithAnyAbility(machine)` — ce dernier etant celui qu'appelle
`$$VerifyMachineTurnEnded`, ce qui recoupe l'attribution.

### `HasTilesToMoveTo` = « le stop-set est non vide », terme a terme

`HasAnyMovablePositionsFor` appelle `FindAnyOrAllMoveableTiles(..., movableTilesFor: **null**)`, et
ce `null` selectionne le mode **ANY** d'`AnyOrFillMoveableTiles` : le natif rend `true` des que le
premier `GetReachableTiles` filtre par `IsMovableTile` est non vide. C'est donc, exactement,
`GetMovableTilesFor(...).Count > 0` — meme stop-set, meme filtre d'occupation.

Garde d'entree, LUE :

```
if ((unitFlags.Has(UnitFlag.Moved) && !ignoreUnitFlags) || !UnitExtensions.CanMove(unit))
    return false
```

`ignoreUnitFlags` vaut **0** au call-site : le flag `Moved` MORD. C'est ce qui explique la mesure du
bras `apres_deplacement` — une unite qui vient de bouger n'a plus de tuile ou aller. Contrairement
au noeud DSL `MovableTilesInRange`, qui laissait ce gate inerte faute de substrat, le runner porte
`UnitFlagsComponent` : le gate est ici REEL.

`IdunBattle.Entities.UnitExtensions$$CanMove` :
```
EntityType(unit) == Unit(1)  &&  !BaseUnitComponent.HasTrait(UnitTrait.Stationary)
&& MovementComponent.IsAllowedToMove()
```
Les deux premiers etages sont portes. Le troisieme,
`IdunBattle.Entities.Components.MovementComponent$$IsAllowedToMove` = `<+0x50 : Dictionary>.Count
== 0`, ne l'est pas : aucun canal de seed ne l'expose, et **aucun de ses ecrivains n'est une methode
NOMMEE** du binaire (ecritures inline) — le decompile ne donne donc meme pas la liste des poseurs.
Il est NOMME plutot que devine ; on n'a **pas** fabrique un proxy depuis les effets `*_BlockMovement`
(4 candidats existent dans `EffectType`), ce qui aurait ete une hypothese deguisee en mirror.
Direction de l'ecart : le port croit l'unite mobile la ou le natif la bloquerait -> il RETIRE le
flag un peu plus souvent, il ne le POSE jamais a tort.

### `HasActionAvailable` et son corps terminal

```
HasActionAvailable(unit) :
    movable = MovementQuery.GetMovableTilesFor(unit, ignoreUnitFlags: false, options: <memset 0>)
    movable.Add(EntityExtensions.GetMainTile(unit, state))
    return DamagePredictionQuery.CanAttackAnyUnitFromTilesWithAnyAbility(unit, movable)

AttackQuery$$CanAttackAnyUnitFromAnyTileWithAnyAbility(unit, tiles) :
    flags = unit.GetComponent<UnitFlagsComponent>()
    if (flags.TurnEnded())                          return false
    if (flags.Has(UnitFlag.ActiveAbilityUsed))      return false
    if (UnitExtensions.IsBoss(unit))                return true
    positions = EntityExtensions.GetUnitPositionsAtTiles(unit, tiles, state)
    foreach (ActiveAbility a in unit.GetComponent<ActiveAbilityComponent>().<+0x20>)
        if (a.CanCurrentlyBeUsed && !UnitExtensions.IsAbilityBlocked(unit, a.AbilityName)
            && AttackQuery.HasValidTargets(unit, positions, a.AbilityName))
            return true
    return false
```

`AttackQuery$$HasValidTargets(unit, tiles, type)` boucle sur les positions et delegue a la surcharge
par POSITION, qui verifie `CanCurrentlyBeUsed` puis applique la cascade de
`TargetingQuery$$GetValidTargets` — sa surcharge **7 arguments**, le FILTRE STATIQUE PUR (ni
aiguillage self-cast, ni volet caster).

## 3. Pourquoi la tuile courante SUFFIT — la propriete qui rend le port exact

Le port ne sait juger une cible que depuis la position REELLE du caster
(`get_invalid_target_reason` mesure la portee de la, cf. `valid_normal_attack_targets`). Evaluer
`HasValidTargets` sur un sous-ensemble des positions natives serait SOUS-estimer, donc POSER le flag
a tort — la sur-fermeture meme que la tranche combat.

Elle ne se produit pas, et ce n'est pas une chance : **les deux predicats partagent le meme
`GetMovableTilesFor`**. `_can_act` ne consulte `HasActionAvailable` que si `HasTilesToMoveTo` est
FAUX (le OU court-circuite sinon) — or ce faux signifie exactement « le stop-set est vide », par la
meme garde d'entree et le meme calcul. La liste native se reduit alors a la seule `GetMainTile`.
Le port porte ce raisonnement en EXECUTABLE (`movable_is_empty`) plutot qu'en prose : si le set
n'est pas vide, un `False` n'est pas certain -> `None`.

## 4. Le tri-etat, et ce qu'il refuse de fabriquer

`has_tiles_to_move_to` / `has_action_available` / `_can_act` rendent `True` / `False` / `None`.
`None` = INDETERMINE -> `verify_unit_turn_ended` **s'abstient** : ni pose, ni retrait, et le compte
est RENDU (`undetermined`), pas tu. Verdicts `False` certains de `has_action_available` : les deux
gates pur-flag (`TurnEnded`, `ActiveAbilityUsed`), et « aucune ability utilisable n'a de cible ».
`IsBoss` passe par le foyer unique du port (`operations/repair._is_boss`, non porte, rend `False`) :
le port peut manquer un `True`, jamais en fabriquer un.

**MESURE : 0 abstention** sur tous les regimes joues.

## 5. Ce que le port a construit

| piece | ou |
|---|---|
| `_can_move`, `has_tiles_to_move_to`, `has_action_available`, `_has_valid_targets`, `_can_act` | `runner/operations/turnflow.py` |
| `VerifyUnitsTurnFinishedOperation` (+ `verify_units_turn_finished`) | idem |
| branchement a l'ancrage (slot 0x21 de `RunPhase`) | `runner/runner.py`, `Runner.apply` |
| probe des DEUX faces + amplitude + cout | `scripts/python/probe_287r1r1_verify_turn_ended.py` |
| cliquet offline (15 tests, 6 etages) | `tests/engine/runner/test_287r1r1_verify_turn_ended_offline.py` |

**La MACHINE OF WAR est ECARTEE, et c'est un mirror** : le natif ne lui applique pas
`VerifyUnitTurnEnded` mais `$$VerifyMachineTurnEnded`, dont le corps ne teste NI `HasTilesToMoveTo`
NI `HasActionAvailable` mais `MachineCanAttackAnyUnitWithAnyAbility` — un verdict que le port n'a
pas plus. Elle est COMPTEE (`machines_skipped`), pas traitee en silence comme une unite.

**UN SEUL appel, la ou le natif en fait DEUX** (`RunPhase` invoque `0x21` avant et apres son bloc de
fin de tour). Meme choix, meme motif que le DRAIN #2 des triggered-abilities : aucun des gestes que
le natif intercale n'est joue a cet endroit cote port, l'operation est idempotente, et le second
appel couterait un second pathfinding par unite. RESIDU NOMME.

## 6. Validation

**Le probe #287-r1 a CHANGE DE SENS, comme son test l'avait fait a la tranche precedente.** Le bras
`apres_deplacement` de `probe_287r1_flags_transverse.py` ENCADRAIT le residu (« l'ecart vaut
exactement `{NoActionAvailable}`, et il est RESTRICTIF ») ; il exige desormais l'**EGALITE
D'ENSEMBLES, bilaterale**, sous deux regimes temoins : le natif doit poser `NoActionAvailable`
(sinon le bras ne mesure rien) et ne PAS poser `TurnFinished` (sinon il mesurerait `FinishUnitTurn`,
pas `VerifyUnitTurnEnded`).

**Le probe de cette tranche a vu son PREMIER MONTAGE REFUTE par son propre temoin.** Il placait le
retrait sur un message ULTERIEUR au retour de tour, en supposant que le flag survivrait ; la mesure
a rendu `live=[]` — le natif avait deja re-ouvert l'unite. Cause : c'est l'`EndTurnMessage` de
retour qui porte tout (`ChangeTurn` + `StartTurn` -> `RemoveTurnFlags`, puis, dans la MEME
`RunPhase`, le slot 0x21 sur le joueur devenu courant). Le montage a ete resserre sur ce message.

| epreuve | resultat |
|---|---|
| `probe_287r1r1_verify_turn_ended.py` (POSE / SURVIE / RETRAIT) | **PROBE OK** — pose `live=[0,1,4]` = `port` ; survie `live=[0,1,3,4]` ; retrait `live=[]` = `port` |
| `probe_287r1_flags_transverse.py` (2 bras, egalite bilaterale) | **PROBE OK** — `deplacement live=[0,1,4] port=[0,1,4]` ; `attaque live=[1,2,3,4] port=[1,2,3,4]` |
| `test_287r1r1_verify_turn_ended_offline.py` | **15/15** |
| `test_287r1_no_action_available_offline.py` + `test_turnflow_endturn_flags.py` | **17/17** |
| `test_sorcerous_facade_combat_live` / `test_turnflow_live` / `test_runner_move_live` / `test_448_r1_r1_r2_r1_dsl_after_move_live` | **9 / 2 / 2+1xfail / 3** |
| `test_runner_attack_live` / `test_damage_roll_live` / `test_overwatch_live` / `test_summon_automatic_live` | **2 / 2 / 1 / 8** |

**AMPLITUDE** (cote port, par message, `C1_74`/34117, 2 unites) : le message de deplacement pose
**1** flag ; l'`EndTurnMessage` de retour en retire **2**. **0 abstention**, **0 MoW**.

**CONTRE-EPREUVES**, mutation verifiee sur disque avant de conclure :
* voie desarmee dans `Runner.apply` -> `probe_287r1r1` ROUGE sur les DEUX faces
  (`ECHEC temps 1 (POSE) : live=[0,1,4] port=[0,1]`, puis
  `ECHEC temps 3 (RETRAIT) : live=[] port=[4] (en_trop=[4])`) et `probe_287r1_flags_transverse`
  ROUGE (`manquants=[4]`) ;
* branche de retrait desarmee dans `verify_unit_turn_ended` -> cliquet offline **2 rouges sur 15**.

## 7. NON COUVERT

1. `$$VerifyMachineTurnEnded` (et son slot `IDamagePredictionQuery` 2,
   `MachineCanAttackAnyUnitWithAnyAbility`) : la MoW est ECARTEE et COMPTEE, pas portee ;
2. `MovementComponent$$IsAllowedToMove` (le registre de bloqueurs `<+0x50>`) : aucun substrat,
   ecart PERMISSIF nomme (§2) ;
3. `UnitExtensions$$IsAbilityBlocked` : aucun substrat ; il ne peut que RESTREINDRE, donc ne peut
   pas rendre un `False` a tort ;
4. le SECOND appel du slot 0x21 dans `RunPhase` (§5) ;
5. `HasValidTargets` depuis une position AUTRE que la tuile courante : hors du regime atteignable
   par `_can_act` (§3), mais la fonction `has_action_available` appelee seule le signale par `None` ;
6. `turn.<+0x24> != 1` (« la bataille est en cours ») : sans substrat offline, un `State` de runner
   etant par construction une bataille en cours ;
7. l'amplitude n'est mesuree que sur les trois configurations du §8 — pas sur une bataille entiere.

## 8. Generalisation, et le COUT

Le probe prend `--board` / `--seed` / `--p-units` / `--a-units` / `--walker` : les trois axes qui
pourraient faire passer un accord pour une propriete alors qu'il n'est qu'une coincidence de
montage (geometrie, roster, unite mesuree) varient.

| board / seed / roster | walker | POSE (live = port) | RETRAIT (live = port) | abstentions |
|---|---|---|---|---|
| `C1_74` / 34117 / ultra vs thous | `ultraCalgar` | `[0, 1, 4]` | `[]` | 0 |
| `MC1_67` / 28701 / ultra vs thous | `ultraTitus` | `[0, 1, 4, 19]` | `[19]` | 0 |
| `C1_74` / 91117 / world vs ultra | `worldJakhal` | `[0, 1, 4]` | `[]` | 0 |

Le 2e bras porte un temoin gratuit : `UnitFlag.PreventOverkill` (19) est present AVANT et APRES —
le retrait est donc CIBLE sur `NoActionAvailable`, il ne vide pas le jeu de flags.

**COUT.** La voie balaye les unites du joueur courant a CHAQUE message, et chaque unite non gatee
paie un pathfinding : c'est le seul reproche serieux qu'on puisse lui faire, donc il est CHIFFRE
(`ms_verify` / `ms_apply` du probe, la voie seule contre le message complet) :

| configuration | `ms_apply` | `ms_verify` | part |
|---|---|---|---|
| `C1_74` / 34117 | 65 - 134 | 0,2 - 0,6 | **< 1 %** |
| `C1_74` / 91117 | 162 - 385 | 0,5 | **< 1 %** |

La raison est structurelle, pas une chance : `HasTilesToMoveTo` teste `Has(UnitFlag.Moved)` et
`TurnEnded()` AVANT tout pathfinding, et ces deux gates coupent la grande majorite des unites d'un
tour en cours.
