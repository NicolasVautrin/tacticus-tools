# #525 — `1222 MassDriverAccelerator` : le port COMBAT d'une CHARGE que l'audit classait `DAMAGE`

**Verdict : QUIRK PORTÉ.** L'ability était un **NO-OP SILENCIEUX** — absente d'`ABILITY_CLASSES`,
donc la décision pouvait la choisir et l'exécution l'ignorait : 0 buff, 0 déplacement, 0 dégât,
aucune erreur. Elle est portée, confrontée live **bit-exact sur 4 régimes × 2 couples
(board, seed)**, et son masque de ciblage + son `AbilityAttackType` sont posés dans le même commit.

Porteur : `votanChampion` « Kimm » (LeaguesOfVotann, **lineup unique**), **hors pool ET hors
catalogue** — le seed BC est augmenté par `catalog_inject.write_augmented_seed_bc`. Ce n'est pas un
refus de confrontabilité : aucun `data/unspawnable_rank*.json` ne le déclare.

Face **DÉCISION** déjà portée avant cette tranche : `#27-r1` (`CalculateCustomUtility`) et `#305`
(`MakeDamagePredictions`, le splash). Cette tranche ferme la face **EXÉCUTION**.

---

## 1. Ce que l'audit disait, et ce que le décompilé dit

L'audit `combat-ability-coverage.md` classait 1222 en `DAMAGE(DirectDamage)`. C'est **juste mais
incomplet**, et le brief avertissait du piège inverse (« plusieurs entrées classées DAMAGE sont en
fait des BUFF à `damageProfile` — `NovaBoost`/`NovaCharge`/`NovaShield` »). Ni l'un ni l'autre :

* le `damageProfile` de la config **vaut bien** `DirectDamage`, et le 1er `AttackWithAttackDamage`
  le consomme — l'audit n'a pas menti ;
* mais l'`ExecuteBehaviour` porte **aussi** un stat-mod de mouvement, un **déplacement**, et un
  **second volet de dégât** au profil `Physical`.

C'est une **CHARGE À SPLASH**, du patron exact de `LeadingTheChargeAbility` (1204, #508) et
`BlackRageAbility` (1163, #217). L'indice donné au brief — une utilité de gameconfig nommée
`MassDriverAccelerator_AdjacentFriendly` — est **confirmé au décompilé**, et pas supposé :
`...MassDriverAcceleratorAbility$$GetBuffTargets` = `owner@0x30 + AdjacentFriends(owner@0x30)`.
Le scoreur préfère les positions où Kimm a des alliés au contact **parce que le buff de mouvement
les touche aussi**.

## 2. RE — build `rnca9r7q6c`, mirror 1:1

Carte des slots de sélecteur (`IdunBattleLogic.Entities.DSLFactory$$InitializeShared`, déjà établie
par #508) : `sel+0x30 = Owner`, `sel+0x48 = Caster`, `sel+0x50 = CasterTile`, `sel+0x60 = Target`,
`sel+0x78 = TargetTiles`. `DSLFormulas+0x20 = Direct(1)` (relu dans
`IdunBattleLogic.Entities.DSLFormulas$$.ctor`, qui alloue
`+0x18 Direct(0) · +0x20 Direct(1) · +0x28 Direct(2) · +0x30 Direct(100) · +0x38 Direct(-1)`).

### `...MassDriverAcceleratorAbility$$ExecuteBehaviour` — UNE seule exécution top-level

```
Execute(
  ( AddStaticStatModifierEffect( owner@0x30 + AdjacentFriends(owner@0x30, unique: 1, sel: 3),
                                 0x606 = MassDriverAccelerator_ExtraMovement,
                                 0x1   = StatType.Movement,
                                 Get(GetNumberConstant(0xe = extraMovement)),
                                 <DSLFormulas+0x20> = Direct(1),
                                 isHidden = 0 )
    & MoveUnit( caster@0x48,
                First(SortTilesByUtility(GetPossibleMoveTiles(), caster@0x48,
                                         0x21 = UtilityType.MovementSuggestion, null), 1),
                <options ZERO> ) )
  & IfAlive( caster@0x48,
      AtomicGroup(
        ( SetCache( Cache(GetAdjacentAttackTargets(), matchAbilityEntities: 1) )
          & Group( AttackWithAttackDamage(caster@0x48, target@0x60, MinMaxDamage,
                                          Nullable(GetDamageProfile()), GetHits(),
                                          AbilityOrEffect(this), <options ZERO>, sel: 2),
                   caster@0x48, 0x20 = GroupType.Ability_Attack ) )
        & Group( AttackWithAttackDamage(caster@0x48, Alive(<le MEME cache>), MinMaxDamage2,
                                        Nullable(GetDamageProfile2()), GetHits2(),
                                        AbilityOrEffect(this), <options ZERO>, sel: 2),
                 caster@0x48, 0x21 = GroupType.Ability_Attack_2 ) ) ) )
```

### Les trois getters, tous ré-inlinés par `ExecuteBehaviour`

| symbole natif | arbre |
|---|---|
| `...MassDriverAcceleratorAbility$$GetBuffTargets` | `TargetsSelector.op_Addition(owner@0x30, AdjacentFriends(owner@0x30, 1, 3))` |
| `...MassDriverAcceleratorAbility$$GetPossibleMoveTiles` | `TilesUnitCanMoveToChargeTarget(caster@0x48, casterTile@0x50, targetTiles@0x78, UnitMovementRangeWithBonus(caster@0x48, 0x606, Get(GetNumberConstant(0xe))), ignoreFlags: 0)` |
| `...MassDriverAcceleratorAbility$$GetMoveTile` | `First(SortTilesByUtility(GetPossibleMoveTiles(), caster@0x48, 0x21, null), 1)` |
| `...MassDriverAcceleratorAbility$$GetAdjacentAttackTargets` | `Enemies(of: caster@0x48, entities: AdjacentUnits(target@0x60, 1, 3), sel: 3)` |
| `...MassDriverAcceleratorAbility$$GetDynamicInvalidTargetReason` | `Count(GetPossibleMoveTiles().Select(<AbilityEntities>)) > 0 ? 0 : 0x8000000 = TargetIsInRange` |

`ExecuteBehaviour` **ré-inline** les corps de `GetBuffTargets`, `GetMoveTile` et
`GetAdjacentAttackTargets` au lieu de les appeler — les getters ne servent qu'au playbook. Les deux
faces voient donc le MÊME artefact, et le port n'a qu'UN foyer par sélecteur.

### L'anti-double-compte, et c'est le natif qui le porte

`IdunBattleLogic.Entities.DSLFormulas$$UnitMovementRangeWithBonus(unit, effectType, movementBonus)` :

```
If( HasEffect(unit, effectType, onlyActive: 0, targetType: 6),
    StatAmountFormula(unit, 0x1 = StatType.Movement),
    Sum(StatAmountFormula(unit, 0x1), movementBonus) )
```

Les DEUX consommateurs de `GetPossibleMoveTiles` obtiennent la même portée effective, **par des
branches différentes** :

* le **GATE** (`GetDynamicInvalidTargetReason`) l'évalue avant tout cast → l'effet 1542 n'est pas
  posé → branche `Movement + extraMovement` ;
* l'**étage MOVE** l'évalue après le `AddStaticStatModifierEffect` (les sélecteurs natifs sont
  PARESSEUX) → l'effet EST posé et la stat MOVEMENT est déjà bonifiée → branche `Movement` nu.

Prendre la mauvaise branche à l'étage MOVE surestime la portée de charge de `extraMovement` et
change la tuile d'atterrissage. Même forme, même foyer natif que `orks.py::waaagh_move_range` (1099)
et `loki/strike.py::_black_rage_move_range` (1342) — seul l'`EffectType` diffère.

### Le masque, RELU sur ce preset

`...MassDriverAcceleratorAbility$$.ctor` n'appelle **aucun** `TargetingOptions$$.ctor` : il recopie
les 0x40 octets de `<TargetingOptions statics>+0x240` puis appelle
`AActiveAbility..ctor(this, &opts, 0)`. Le ctor est **byte-identique** à celui de 1204 — mais le
masque a été relu au `.cctor`, pas hérité :

```
*(statics + 0x240) = 0            -> isSelfCasting = False
*(statics + 0x248..0x25c)         -> copie de `TargetingRange statics+0x48` = useWholeBoard
*(statics + 0x260) = 1            -> forceMeleeTarget = RangedBool.False
*(statics + 0x268) = 0x102004032  -> rules
```

`0x102004032` se décompose **exhaustivement** (reste `0x0`) en `TargetMatchesDynamicRule` (0x2) |
`CasterHasNotMoved` (0x10) | `TargetHasFreeAdjacentTile` (0x20) | `TargetIsEnemy` (0x4000) |
`AllowObscuredTargetByElevation` (0x2000000) | `TargetIsNotAdjacent` (0x100000000).

`AbilityAttackType` = **littéral `0` = `DirectTargetAttack`**, transcrit et non déduit : 1222 pose
d'abord un stat-mod, se déplace, et son 2e volet est un splash multi-cible.

## 3. Ce que le port livre

`engine/runner/abilities/votann.py` (le porteur est LeaguesOfVotann ; le namespace natif
`Abilities.Active.Loki` est celui de TOUTES les abilities du jeu) :

| foyer | artefact natif |
|---|---|
| `mass_driver_buff_targets_selector()` | `GetBuffTargets` — `Union(Owner(), AdjacentFriends(Owner(), 1, reference=Owner()))` |
| `mass_driver_buff_tree(extra_movement)` | le `AddStaticStatModifierEffect(0x606, MOVEMENT, Direct(1) tour)` |
| `mass_driver_move_range(state, caster)` | `UnitMovementRangeWithBonus`, les DEUX branches |
| `mass_driver_possible_move_tiles_selector(range)` | `GetPossibleMoveTiles` |
| `mass_driver_move_tile(...)` | `GetMoveTile` (foyer `first_tile_by_utility`) |
| `mass_driver_adjacent_attack_targets_selector()` | `GetAdjacentAttackTargets` |
| `mass_driver_attack_tree()` | `AtomicGroup((SetCache & Group(atk1, 0x20)) & Group(atk2, 0x21))` |
| `MassDriverAcceleratorAbility.TARGETING_OPTIONS` | le masque `0x102004032` |
| `MassDriverAcceleratorAbility.get_dynamic_invalid_target_reason` | `GetDynamicInvalidTargetReason` |

La composition `op_BitwiseAnd` de `IdunBattle.DSL.AbilityBehaviour` étant SÉQUENTIELLE
(`CombinedBehaviour`), `execute_behaviour` joue `buff` puis `move & ifAlive` sur le MÊME
`AbilityEntities` — mirror exact de l'arbre unique, et c'est ce qui permet de lire la destination
de charge APRÈS la pose du buff, exactement comme le natif dont les sélecteurs sont paresseux.

⚠ **L'arbre est reconstruit à chaque cast** : le nœud `Cache` est STATEFUL (mémoïsation par
instance). Un arbre gardé en attribut de classe rendrait au 2e cast l'ensemble d'ennemis du premier.

## 4. Confrontation live — `probe_525_mass_driver_accelerator.py`

Sept étages, jamais un scalaire : E0 `ported` · E1 le buff 1542 (QUI le reçoit) · E2 la tuile
d'atterrissage · E3 le dégât sur la cible · E4 le splash (qui, quel profil) · E5 les tirages
`genrand_int32` · E6 le gate de cible contre le `fromHere` d'`abilityTargets`.

Quatre régimes, chacun crafté pour rendre un étage NON trivial :

| régime | montage | ce qu'il exerce |
|---|---|---|
| R1 | 1 ennemi adjacent à la cible | le cas nominal |
| R2 | 2 ennemis adjacents | le `multi` du 2e `AttackWithAttackDamage` ; les tuiles occupées **changent** la tuile d'atterrissage |
| R3 | 3 ennemis adjacents | tuile d'atterrissage contrainte, splash sur 3 unités |
| R4 | un **ALLIÉ** adjacent à la cible | **le seul** régime où le filtre `Enemies` est observable (friendly fire) |

Résultat, **`MC1_67` / seed 525** — port == natif sur les sept étages, aux 4 régimes :

| | R1 | R2 | R3 | R4 |
|---|---|---|---|---|
| buff 1542 | `{Kimm, allié adjacent}` | idem | idem | idem |
| tuile | (4,8) | (6,7) | (6,7) | (6,7) |
| cible (`DirectDamage`, pierce 100) | 6530 | 5906 | 5906 | 5906 |
| splash (`Physical`, pierce 1) | {6918} | {6294, 6496} | {6294, 6496, 6743} | {6294} |
| tirages | 4 | 6 | 8 | 4 |
| gate (`fromHere`) | — | [83,85,87] | [83,85,87] | [85,87] |

**Généralisation, `C2_02` / seed 777** (7×9 tout Grass, élévations 2/3/4 → un étage d'élévation
actif que `MC1_67` n'exerce pas) : les 4 régimes passent, avec des tuiles d'atterrissage **et** des
dégâts DIFFÉRENTS ((4,7) puis (6,6) ; 6963 / 6339 sur la cible) — donc les accords de `MC1_67` ne
sont pas des artefacts de ce board.

Le montage **échoue avant de mesurer** si l'allié « adjacent » ne l'est pas, si l'allié « lointain »
l'est, si la cible est adjacente (`TargetIsNotAdjacent` refuserait le cast) ou si aucun ennemi n'est
adjacent à la cible (splash structurellement vide → accord sans contenu).

### Contre-épreuves hors-ligne (régime R4)

| variante | résultat | verdict |
|---|---|---|
| AB1 buff sur l'owner SEUL (collapse) | `[77]` ≠ `[77,79]` | **discriminante** |
| AB2 `AdjacentFriends` ancré sur la CIBLE | `[77,87]` ≠ `[77,79]` | **discriminante** — le buff partirait au camp adverse |
| AB3 splash sans le filtre `Enemies` | `[83,87]` ≠ `[87]` | **discriminante** — friendly fire |
| AB4 splash ancré sur le CASTER | `[]` ≠ `[87]` | **discriminante** |
| AB5 tri de tuile par `Tile(7)` | identique | **NON discriminante** sur ce montage |
| AB6 portée sans la branche `HasEffect` | pool identique | **NON discriminante** — le pool est déjà saturé par `CanAddUnit(AdjacentTiles(target))` ; la branche est prouvée par `move_range = 4` (et non 5) |

AB3 **ne discrimine rien** hors de R4 : c'est exactement pourquoi ce régime a été ajouté après coup,
et pourquoi les deux non-discriminantes sont **nommées** au lieu d'être tues.

## 5. Ce qui n'est PAS couvert

* **Le régime où Kimm MEURT pendant la charge** (`IfAlive(caster@0x48)` faux) : le `MoveUnit` natif
  passe des options ZÉRO, donc il ne déclenche aucun overwatch sur ce chemin — le gate est porté et
  gardé statiquement (`test_525…offline.py`), pas confronté live.
* **`isHidden = 0`** (7e argument de `AddStaticStatModifierEffect`) : le port ne modélise pas la
  visibilité UI d'un effet. Inerte offline.
* **`ignoreFlags = 0`** de `TilesUnitCanMoveToChargeTarget` : terme NON exercé côté port (résidu
  #381), propagé tel quel pour que les call-sites divergent le jour où le substrat existe.
* **`MinMaxDamage` vs `MinMaxDamage2`** : les valeurs sont ÉGALES sur cette config, donc l'erreur y
  serait invisible en mesure. Les deux jeux de clés sont passés séparément et le cliquet offline le
  fige — c'est le seul canal où la faute serait visible aujourd'hui.
* **La divergence natif/natif décision↔exécution** documentée par #305 (le playbook repasse la
  valeur du batch PRINCIPAL aux deux volets, l'exécution appelle bien `MinMaxDamage2`) reste sans
  conséquence numérique sur cette config, et le port la garde explicite des deux côtés.
* **Un caster portant `ExtraHits`** (stat runtime, non posable par `--unit-stat`) — même limite que
  #305.

## 6. Trouvé en chemin, hors périmètre

* `engine/runner/abilities/loki/strike.py` (BlackRage, 1163) commente `0x20 = 32 =
  UtilityType.MovementSuggestion`. Sur le build `rnca9r7q6c`, **`32 = EnvEndBombardment` et
  `33 = MovementSuggestion`** (`data/symbols/rnca9r7q6c/frida/enums.tsv`, et le mirror Python
  concorde). Le littéral que 1163 passe au natif n'a pas été relu par cette tranche — seul le
  COMMENTAIRE est en cause si l'ordinal a glissé entre builds. Résidu à ouvrir si quelqu'un le
  confirme au décompilé de `BlackRageAbility$$ExecuteBehaviour`.
* **Deux rouges de `master`** (`40917cd0`), reproduits à l'identique sur un worktree témoin détaché
  et **sans lien avec cette tranche** :
  * `probe_486r15_declencheurs_tests.py` : `FAIL — 2 fichier(s) en faute`
    (`test_501_might_from_below_offline.py` et `test_486r15_empreinte_par_entree_offline.py`
    déclarent trop étroit) ;
  * `tests/engine/runner/test_votann_lot1_live.py` : **6 failed / 13 passed / 2 skipped**
    (`graviton_*` et `fortune_*`, `total live 0`).

## 7. Résidus

Aucun ouvert par cette tranche. `#525-r1` est LIBRE
(`probe_468_collision_numeros.py --suggere 525`).

## 8. Artefacts

* Port : `scripts/python/engine/runner/abilities/votann.py`
* Registre : `scripts/python/engine/runner/abilities/handler.py`,
  `scripts/python/engine/runner/abilities/attack_type.py`
* Mesure : `scripts/python/probe_525_mass_driver_accelerator.py`
  (`--tables` / `--regime` / `--board` / `--seed` / `--ab` / `--keep`)
* Garde : `scripts/python/tests/engine/runner/test_525_mass_driver_accelerator_offline.py` (15 tests)
