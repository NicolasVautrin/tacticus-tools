# #462-r4b-r1-r1-r1-r1-c-r3-r1-r5 — la POSE de la mine Haywire

La tranche precedente savait faire **exploser** une mine, jamais en **creer** : toute simulation
offline partant d'un etat sans mine n'en voyait donc jamais apparaitre. `HaywireMineAbility` (1531)
est portee ici, avec les cinq primitives qu'elle exige — et la lecture du natif a fait tomber au
passage une divergence de fidelite de `CanAddUnit` qui n'a rien a voir avec les mines.

| ce qui entre | verdict |
|---|---|
| `HaywireMineAbility` (1531), ses DEUX disjonctions | **PORTE** — confronte live, natif vs port, sur 4 bras |
| `HaywireMine_ResetAbility` (meme id 1531, 2e classe) | **PORTE** — c'est lui qui re-arme la pose de fin de tour |
| la branche `triggerType == Custom` (re-declenchement differe) | **PORTE** (`CUSTOM_TRIGGERED_ABILITIES[1531]`) |
| `PreviousTile` / `SelectIf` / `AddPersistentData` / `ClearPersistentData` / `GetPersistentData` | **PORTES comme PRIMITIVES** |
| `CanAddUnit` filtrait sur `hp > 0` | **CORRIGE** — le natif ne lit que le contenu de la tuile |
| `HaywireMineSteppable_InitAbility` | **NON PORTE** — `Inform(0x77, …)`, canal VUE (residu) |

## 1. Les artefacts natifs, lus sur `rnca9r7q6c`

Slots de `DSLFactory` (`this+0x28`), lus verbatim : `+0x78` = `DSLBehaviors`, `+0x80` = `DSLFormulas`,
`+0x88` = `DSLTriggers`, `+0x90` = `DSLSelectors` ; `DSLSelectors+0x30` = le selecteur `Owner`.

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HaywireMineAbility$$CreateTrigger`

```
  ( On(4 = UnitAfterMove, ownerNeedsToBeAlive = 1) & get_OwnerIsActor & TriggeringAbilityIsNone )
| ( On(0x29 = UnitFinishedTurnNormally, ownerNeedsToBeAlive = 1) & get_OwnerIsActor
    & AmountIsZero( GetPersistentData(AbilityOrEffect(self), Owner, <cle statique>) ) )
```

### `…HaywireMineAbility$$CreateBehaviour(abilityState, triggerType)`

```
tiles = Cache( If( AmountIsGreaterThanZero(PreviousTile(Owner)) & HasFlag(Owner, 0 = Moved),
                   CanAddUnit(PreviousTile(Owner)),
                   First(SortTilesByUtilityForSummon(
                             Randomize(CanAddUnit(AdjacentTiles(Owner))), 7, Owner), 1) ),
               1 )
pose  = Spawn(Owner, tiles, GetStringConstant(8 = unitToSpawn),
              SpawnUnitOptions.WithStatsFromConfig(config, abilityState, 0, 0))
        & AddPersistentData(AbilityOrEffect(self), Owner, <cle>, DSLFormulas+0x20 = Direct(1))

if (triggerType == 0x20 = Custom) return pose;
return If( AmountIsGreaterThanZero(Count(tiles)), pose,
           TriggerAbilityDelayed(Owner, 0x5fb = 1531, 3) );
```

Trois traits **lus**, qu'aucune lecture rapide ne donne :

* la garde du selecteur est une **conjonction** — « il existe une tuile precedente » ET « l'unite a
  bouge ce tour ». Le second membre (`UnitFlag.Moved`, purge au turn-start par
  `RemoveTurnFlags(new_activation = 1)`) est ce qui bascule sur la branche ADJACENTE au tour ou
  l'unite ne s'est pas deplacee ;
* `PreviousTile` apparait **deux fois**, et pas au meme etage : dans la garde SANS `CanAddUnit`,
  dans la branche `then` AVEC. La garde ne teste donc pas la libre-occupation — une tuile
  precedente OCCUPEE passe la garde et rend un ensemble vide, ce qui fait tomber le behaviour sur
  `TriggerAbilityDelayed` ;
* le 4e argument de `TriggerAbilityDelayed` est un **`UnitSelectionType`**, pas un delai
  (`IdunBattle.Entities.Behaviours.TriggerAbilityDelayedBehaviour$$.ctor(state, entity,
  triggeredAbilityType, unitSelectionType)`).

### `…HaywireMine_ResetAbility`

```
CreateTrigger   : On(0x28 = UnitFinishedTurn, ownerNeedsToBeAlive = 1) & get_OwnerIsActor
CreateBehaviour : triggerType == 0x20 -> Nothing()
                  sinon               -> ClearPersistentData(AbilityOrEffect(self), Owner, <cle>)
```

`HaywireMine_Reset` **n'a pas d'entree dans `TriggeredAbilityType`** : c'est une SECONDE classe
native du meme id 1531 — le patron `DawnBlade_Heal` / `DawnBlade_Init` deja rencontre en #317. Elle
s'inscrit donc sous le meme nom de kit (`ABILITY_TRIGGERS["HaywireMine"]`).

## 2. L'ORDRE, qui decide tout — et qui est MESURE

`IdunBattle.Operations.FinishUnitTurnOperation$$Execute` publie, dans cet ordre :

```
if (flags.Add(0x01 = ArrivedAtFinalTile) && !isTerminated)  publish On(0x1c)
if (flags.Add(0x03 = TurnFinished)) {
    publish On(0x28 = UnitFinishedTurn)                 <- le Clear du Reset
    if (!isTerminated) publish On(0x29 = UnitFinishedTurnNormally)   <- la lecture AmountIsZero
}
```

Le `ClearPersistentData` tombe donc **avant** la lecture. Ce n'est pas une deduction : le bras
`--step discriminant` du probe le montre. Sequence live (`MC1_67`, `astarCyrus` injecte au
catalogue, `--no-ai`, 5 tours) :

| tour | geste | mines |
|---|---|---|
| avec deplacement | `move` d'un hex | **1** mine sur la tuile QUITTEE ; le `finish` n'ajoute RIEN (9 evenements, aucun spawn) |
| sans deplacement | rien | le `finish` pose **1** mine ADJACENTE (16 evenements, `Unit_IsSummoned=1` + `UnitStats_TriggeredAbility_Id=1542`) |

Une mine par tour, donc — mais **pas** grace au gate persistant. Le bras discriminant le prouve :
on fait mourir un ecraseur ENNEMI **sur** la mine (PV bas -> la mine l'ecrase ET lui explose
dessus -> `RemoveUnitFromTiles` retire les DEUX), ce qui LIBERE la tuile precedente ; le `finish`
du meme tour y **repose** une mine. **Deux mines dans un seul tour.**

⇒ ce qui borne la pose a une par tour est l'**OCCUPATION DE LA TUILE**, pas le gate.

### Corollaire, assume et documente : le gate persistant est STRUCTURELLEMENT INERTE

`AmountIsZero(GetPersistentData(…))` est **toujours vrai** au moment ou il est lu, dans tous les
regimes atteignables : `On(0x29)` n'est jamais publie sans que `On(0x28)` l'ait ete juste avant
(meme bloc, et `On(0x28)` n'a PAS le gate `!isTerminated`), et rien d'autre ne lit la cle entre
l'`AddPersistentData` du move et le `Clear`. Il est porte quand meme — c'est le decompile — mais
une mutation qui neutraliserait `AddPersistentData` ne ferait ROUGIR aucun bras, et c'est dit
plutot que masque (residu `-r4`).

## 3. Les primitives portees (pas l'ability)

| noeud natif | port |
|---|---|
| `IdunBattleLogic.Entities.DSLSelectors$$PreviousTile` -> `IdunBattle.Entities.Selectors.PreviousTileSelector$$Select` | `entities/selectors/tiles.py::PreviousTile` + `PositionComponent.previous` + le foyer `components.py::save_previous_position` |
| `IdunBattleLogic.Entities.DSLSelectors$$If(abilityTrigger, selTrue, selFalse)` | `entities/selectors/geometry.py::SelectIf` |
| `IdunBattleLogic.Entities.DSLBehaviors$$AddPersistentData` -> `IdunBattle.Entities.Triggers.AddPersistentDataBehavior$$Execute` | `abilities/behaviours/persistent_data.py::AddPersistentData` |
| `IdunBattleLogic.Entities.DSLBehaviors$$ClearPersistentData` -> `IdunBattle.Entities.Behaviours.ClearPersistentDataBehaviour$$Execute` | `…::ClearPersistentData` |
| `IdunBattleLogic.Entities.DSLFormulas$$GetPersistentData` -> `IdunBattle.Entities.Triggers.GetPersistentDataFormula$$Calculate` | `entities/formulas.py::GetPersistentData` |
| `IdunBattleLogic.Entities.DSLBehaviors$$TriggerAbilityDelayed` | **existait deja** (#406) — la file `pending.py` est reutilisee telle quelle |

`SelectIf` est le **troisieme homonyme** du DSL : `DSLBehaviors$$If` (kind E), `DSLFormulas$$If`
(kind V) et celui-ci (kind S) sont trois classes natives distinctes, et `HaywireMineAbility` en
utilise **deux** dans le meme corps.

**`PositionComponent.previous`** mirrore `+0x88`, ecrit par
`IdunBattle.Operations.SetUnitPositionOperation$$SavePreviousPosition` — dont le gate LU est
`previousPosition.Count >= 1` (une empreinte vide n'ecrit rien). Le meme `SavePreviousPosition`
ecrit AUSSI `+0x98`, que lit `IdunBattle.Entities.EntityExtensions$$GetPreviousPositionThisTurn` :
non porte, aucun consommateur (residu `-r2`).

**`Spawn`** gagne deux parametres, tous deux lus au call-site et jamais devines :

* `unit_id_constant` — `GetStringConstant(config, 8)` = `AbilityConstantType.unitToSpawn`, la ou
  les six call-sites anterieurs lisent `0 = unitId`. Recopier le mauvais rend `None` et le spawn
  disparait **sans erreur** ;
* `ability_state` — le 2e argument de `SpawnUnitOptions$$WithStatsFromConfig`, c'est-a-dire
  l'`AbilityState` sous lequel l'unite posee monte SES propres abilities. Ground truth live :
  `ChangeAbility UnitStats_TriggeredAbility_Id=1542 Level=50 VariableMultiplierPercentage=180` sur
  la mine posee par `astarCyrus`. Sans lui, la passive de la mine lirait ses variables a l'index 0
  — le mode de panne #174, deja mesure a un facteur ~55 sur ce meme porteur en `-c-r3-r1-r1`.

## 4. La divergence trouvee en chemin : `CanAddUnit` lisait les PV

Le port posait sa seconde mine **sur** la premiere. Ventilation etage par etage (jamais un scalaire
ajuste) : registre OK, `previous` OK, selecteur OK — le desaccord naissait dans `CanAddUnit`.

Chaine native, lue de bout en bout :

```
IdunBattle.Entities.Selectors.CanAddUnitTileSelector$$Select
    allowSteppable = !<trigger @+0x28>.ShouldTrigger(entities, 0x20)
    garde t si TileExtensions.CanAddUnitFromAbility(t, state, parent, allowSteppable)
IdunBattle.Entities.TileExtensions$$CanAddUnitFromAbility
    = IsFreeTile(t, state, allowSteppable, allowTemporaryTile: 0, allowAnyUnit: 0)
      && !IsTileReservedForOtherUnit(t, parent) && !IsTilePendingDrafting(t, state, 0)
IdunBattle.Entities.TileExtensions$$IsFreeTile        (branche allowAnyUnit == 0)
    libre = allowSteppable ? (content.IsEmpty() || GetUnit(t).HasTrait(0x1b = Steppable))
                           : content.IsEmpty()
```

**Aucun etage ne lit les PV.** Le port filtrait `alive ET hp > 0` (`dsl/base.py::_is_alive`) ; or une
mine Haywire a **0 PV par construction** (`HaywireMine` n'a pas de variable `summonHp`), donc elle
ne bloquait RIEN. Le critere est desormais `alive` seul — « l'unite est SUR le plateau » — ce qui
est deja le modele des DEUX jumeaux imperatifs du meme noeud (`operations/spawn.py::_occupied_tiles`
et `::_free_tiles_adjacent`, qui ne lisent que `UnitComponent.alive`) : **le noeud DSL etait le seul
a diverger**. Les morts restent exclus, et c'est fidele — `KillUnitOperation` ->
`RemoveUnitFromTiles` vide le `TileContentComponent`.

Le flag `allowSteppable` n'est PAS modelise par call-site (residu `-r3`) : le port implemente la
branche `allowSteppable == 0`, et c'est **mesure** — au tour ou la mine occupe deja `PreviousTile`,
le natif ne repose rien (`Count(tiles) == 0`), alors qu'avec `allowSteppable == 1` le bras
`GetUnit(t).HasTrait(Steppable)` aurait rendu la tuile libre.

Perimetre du changement, **mesure** : sur les 7 abilities de summon portees qui passent par `Spawn`,
**7 declarent `summonHp`** — les seules unites a 0 PV du plateau sont donc les tokens `Steppable`
(les mines ; un decoy, lui, nait a `hp = 1` et bloquait deja).

## 5. Confrontation LIVE natif vs port

`probe_462_r4b_r1_r1_r1_r1_c_r3_r1_r5_haywire_pose.py` — trois etapes :
`--step live` (la sequence natif seule), `--step port` (natif vs port sur 3 bras),
`--step discriminant` (le bras qui LIBERE la tuile, natif ET port).

| bras | natif | port |
|---|---|---|
| `move` d'un hex | mine sur la tuile QUITTEE | **meme tuile** |
| `finish` du meme tour | aucune pose | **aucune pose** |
| `finish` d'un tour SANS move | 1 mine adjacente | **meme tuile adjacente** |
| chaine pose -> crush -> explosion -> repose | `[[(1,0)], [], [(1,0)]]` | **identique** |

Le 4e bras est le **second cas discriminant** : c'est le seul qui reveille la branche `then` du
selecteur (`CanAddUnit(PreviousTile)`) apres liberation, et le seul qui exerce la chaine complete —
la pose portee ici debouche bien sur l'explosion validee par la tranche precedente.

⚠ **Le port est CHAINE, jamais recharge a mi-tour**, et c'est load-bearing : `PositionComponent+0x88`
n'est publiee par AUCUN RPC, donc un `load_state` pris APRES le deplacement repart avec `previous`
vide et le port bascule sur la branche adjacente. C'est un ecart de HARNAIS (residu `-r1`), pas de
port : une simulation offline reelle part d'un etat et JOUE.

## 6. Validation

**5 bras verts** dans `tests/engine/runner/test_462_r4b_r1_r1_r1_r1_c_r3_r1_r5_haywire_pose_live.py`
(les quatre du §5, plus `test_la_mine_posee_herite_de_l_ability_state_du_summoner`, qui garde le
mode de panne #174 transpose aux summons : sans propagation, la passive de la mine lirait
`minDmg[0]` au lieu de `minDmg[49] x 180 %`).

**Matrice de 7 mutants, 6 rouges** (mutation verifiee AUX OCTETS avant de lire pytest — un
`replace` qui ne matche pas est un no-op silencieux, et le depot est en CRLF sur disque) :

| mutant | delta | rouges |
|---|---|---|
| M1 `PreviousTile` rend vide | −1 o | **1** |
| M2 `CanAddUnit` refiltre sur `hp > 0` (l'etat d'AVANT) | −8 o | **2** |
| M3 `Spawn` lit `unitId` au lieu d'`unitToSpawn` | −9 o | **5** |
| M4 branches du `SelectIf` inversees | 0 o | **2** |
| M5 `HaywireMineResetAbility` retiree du registre | −46 o | **1** |
| M6 `AbilityState` non propage au summon | −22 o | **2** |
| M7 `AddPersistentData` neutralise | −5 o | **0** |

⚠ **M7 est vert, et c'est le RESULTAT, pas un trou** : il CONFIRME par la mesure ce que le §2
annonce analytiquement — le gate persistant est structurellement inerte, parce que le `Clear`
d'`On(0x28)` precede toujours la lecture d'`On(0x29)`. Aucun montage ne peut le faire mordre ; le
dire vaut mieux qu'un bras qui ferait semblant. (M4 a un delta de **0 octet** — les deux branches
ont la meme longueur — d'ou la verification `contenu mute != contenu original` AVANT de lancer
pytest, et non un test sur la taille.)

**Non-regression, 171 tests** : `test_462_…_c_r3_r1_r1_crush_death_events_live` +
`test_462_…_c_r3_r1_crush_steppable_live` (13) ; `test_summon_spawn_live` +
`test_placement_sort_rng_live` (25) ; `test_runner_move_live` +
`test_448_r1_r1_r2_r1_dsl_after_move_live` + `test_decoy_foundation_live` (8 + 1 xfail
PREEXISTANT, sans rapport) ; `test_steppable_targeting_live` +
`test_hypersensory_moveandspawndecoy_live` + `test_summon_consumers_live` (42) ; et **82 offline**
sur les zones touchees (`test_448_*_offline` x3, `test_347_tiles_moved_call_sites_offline`,
`test_389r2_kill_unit_remove_effects_offline`).

**RE-JOUE APRES REBASE** sur `origin/master` (21 commits d'avance, dont
`#462-r4b-r1-r1-r1-r1-c-r3-r1-r4` qui fait entrer `On(0x35 = PostUnitKill)` dans
`_kill_unit_operation` -- exactement la sequence que le 4e bras traverse) : **100 tests verts**
(5 + 13 + 82). Conflit unique, sur `docs/rl/backlog.md` : chaque cote fermait SA propre ligne
(`-r4` en amont, `-r5` ici) tout en gardant l'autre ouverte -- resolution sans arbitrage, on garde
les deux fermetures et leurs residus. Les deux audits generes ont ete REGENERES apres rebase
(`audit_combat_ability_coverage.py`, `audit_kit_coverage.py`), pas fusionnes.

## 7. Ce qui n'est PAS couvert, et nomme

* le gate persistant est **inerte** (§2) — aucune mutation de `AddPersistentData` ne peut rougir ;
* `PositionComponent+0x98` et `DSLBehaviors$$ResetPreviousPosition` : aucun consommateur porte ;
* `allowSteppable` per-call-site (§4) ;
* `HaywireMineSteppable_InitAbility$$CreateBehaviour` = `Inform(0x77, OriginalOwner(Owner))` — un
  canal de VUE (`DSLBehaviors$$Inform`), sans effet d'etat ;
* un deplacement de **plusieurs** hex : les bras joues ne bougent que d'UN hex, donc « la position
  precedente est la tuile de DEPART » et « c'est la derniere tuile intermediaire » restent
  indistinguables.

## 8. Residus ouverts

* **`#462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r1`** — la POSITION PRECEDENTE n'est seedee par AUCUN canal.
* **`#462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r2`** — `+0x98` / `ResetPreviousPosition` non portes.
* **`#462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r3`** — `allowSteppable` de `CanAddUnit` non modelise.
* **`#462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r4`** — le gate persistant est inerte.
* ~~**`#462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r5`**~~ — **FERME**, cf.
  `case-462-r4b-r1-r1-r1-r1-c-r3-r1-r6-prevent-revive.md` §4. La premisse est **REFUTEE par le
  decompile** : le natif n'appelle PAS `SetUnitPosition` par pas. `MoveUnitOperation$$Execute`
  l'appelle **une seule fois** (slot `0x7e`), avec la destination COMPLETE, **avant** la boucle
  `AddMoveEvent` — et `MoveUnitOperation$$AddMoveEvent` ne touche **aucun** composant ECS (canal de
  VUE). Donc `SavePreviousPosition` grave la tuile de DEPART du mouvement entier, quelle que soit la
  longueur du chemin. Confronte LIVE (`MC1_67`, pas de 2 hex, chemin `[(1,0),(0,0),(0,1)]` dont
  l'avant-derniere DIFFERE du depart) : mine natif `[(1,0)]` = port `[(1,0)]`.
  ⚠ **Corollaire pour le §7 ci-dessus** : sa derniere puce (« un deplacement de plusieurs hex : les
  deux lectures restent indistinguables ») n'est plus un trou de couverture — les deux lectures ne
  sont pas indistinguables, **la seconde n'existe pas**.
