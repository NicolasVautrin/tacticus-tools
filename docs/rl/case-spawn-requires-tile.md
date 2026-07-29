# case-spawn-requires-tile — Le spawn NAÎT de la tuile : plus de summon fantôme hors plateau

> **Numérotation** : ce cas a été dispatché sous l'étiquette **#246**, numéro **déjà occupé** par
> `case-246-thunderous-assault-targeting.md` (livré le 2026-07-29, avec son
> `probe_246_thunderous_targeting.py`). Fiche et probe portent donc un nom **sans numéro** —
> `case-spawn-requires-tile.md` / `probe_spawn_requires_tile.py` — plutôt qu'un numéro qu'un
> prochain dispatch reprendrait. L'entrée de backlog visée est bien
> « `SpawnUnitOperation.execute` crée une entité SANS `PositionComponent` quand il manque une
> tuile » (remontée de `case-250` §9).

---

## 1. La question, et sa réponse

> `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute` crée-t-il **une entité par tuile
> disponible** — donc zéro entité quand il n'y a zéro tuile — ou crée-t-il l'entité puis lui
> cherche une place ?

**Une entité PAR TUILE ITÉRÉE.** Lu au décompilé, la fonction remise en C# :

```csharp
var results = new List<IEntity>();
var owner   = ownerSelector.SelectSingle(ctx);              // *(behaviour+0x50)
var player  = owner == null ? 0 : owner.GetOriginalPlayer(state).Id;
var (unit, options) = GetUnitToSpawn(ctx);                  // sortie NULLE -> return, rien
if (unit == null) return default;
var stats = GetStatsToOverride(ctx, options);
var tiles = tileSelector.Select(ctx);                       // *(behaviour+0x58), evalue UNE fois

if (options.<+0x60> == 0) {                                 // branche PAR DEFAUT
    foreach (var tile in tiles) {
        var e = addUnit.Execute(unit, tile.GetComponent<...>().Id.ToList(),
                                player, 2, GetAddUnitOptions(...));
        if (e != null) results.Add(e);
    }
} else {                                                    // branche MULTI-HEX
    var e = addUnit.Execute(unit, GetTileIds(tiles), player, 2, GetAddUnitOptions(...));
    if (e != null) results.Add(e);
}
foreach (var e in results) TriggerSpawnedUnitBehaviours(ctx, ..., e, player, options);
```

Trois conséquences directes, et c'est tout le cas :

1. **L'entité naît de l'itération.** Zéro tuile ⇒ le corps de boucle n'est jamais atteint ⇒ **zéro
   entité**, donc zéro `On(UnitAdded)` et zéro `TriggerSpawnedUnitBehaviours` (l'on-appearance).
   Le correctif est donc « **ne pas créer** », pas « créer puis nettoyer » — les deux ne produisent
   pas les mêmes événements.
2. **Le `count` d'une ability n'est PAS un compteur d'unités.** Il n'apparaît nulle part dans
   `Execute` : il vit dans le **tile-sélecteur**, dont le `First(<tri>, count)`
   (`IdunBattle.Entities.Selectors.PickAtIndexSelector$$Select`) rend **`min(count,
   len(source))`**. Le nombre de summons est donc `min(count, tuiles libres)`.
3. **`IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$GetTileIds`** n'est qu'un
   `tiles.Select(t => t.Id).ToList()` — il n'existe que dans la branche multi-hex.

### Les DEUX branches, et pourquoi la correction les distingue

| `SpawnUnitOptions+0x60` | forme | résultat | consommateur |
|---|---|---|---|
| `== 0` (défaut) | `foreach (tile in tiles) AddUnit(unit, [tile], …)` | **N unités** mono-pied | tous les spawns d'ability |
| `!= 0` | `AddUnit(unit, GetTileIds(tiles), …)` | **UNE** unité à N pieds | `DutyEternalAbility$$ExecuteBehaviour` (1158) — seul producteur d'empreinte multi-hex du binaire, cf. `case-91-duty-eternal.md` |

Une correction qui transformerait le multi-hex en « une entité par tuile » **casserait** 1158. Elle
ne l'a pas fait : côté port, la branche multi-hex passe par la feuille DSL
`abilities/behaviours/summon.py::Spawn`, qui **itérait déjà** ses tuiles (`spawns = [(tiles[0],
list(tiles))] if (spawn_as_single_unit and tiles) else [(t, None) for t in tiles]` — `tiles` vide ⇒
aucun spawn, dans les deux branches). Les 20 tests `test_multihex_dutyeternal_live` passent.

### Ce que fait `AddUnitOperation` avec une liste de tuiles VIDE (lecture complémentaire)

`IdunBattle.Operations.AddUnitOperation$$Execute` **ne se garde pas** contre une liste vide : ses
quatre filtres (`AreTilesDisallowedAndLog`, `TilesAreReserved`, `TilesArePendingDrafting`,
`TilesAreInFog`) sont des **boucles sur les tuiles**, donc tous rendent `false` sur liste vide ; puis
`UnitComponent.ClearFeet` + un `Blueprints.UnitFoot` **par tuile** ⇒ une unité **sans aucun pied**.
Ce n'est pas atteignable par la branche par défaut (pas de tuile = pas d'appel), et la branche
multi-hex n'y expose que si son sélecteur rend zéro tuile — ce que le port refuse déjà en amont
(`tiles` vide ⇒ `spawns` vide). **Résidu nommé** : si un futur consommateur de `+0x60 != 0` pouvait
recevoir un sélecteur vide, le natif produirait bel et bien une unité sans pied ; on ne l'a pas
porté parce qu'aucun call-site du binaire ne l'exerce.

---

## 2. Le défaut porté (avant)

`scripts/python/engine/runner/operations/spawn.py` faisait l'inverse du natif :

```python
for _ in range(max(0, int(count))):        # boucle sur le COUNT, pas sur les tuiles
    tile = _first(_sort_by_distance(...))  # peut valoir None
    e = state.add_entity()                 # l'entite est deja creee
    ...
    if tile is not None and board is not None:
        tinfo = board.by_id.get(tile)
        if tinfo is not None:
            e.add_component(PositionComponent(...))   # position CONDITIONNELLE
    on_unit_added(state, e.id)
    spawned.append(e.id)
```

Quatre sites, même patron :

| site | statut avant | statut après |
|---|---|---|
| `SpawnUnitOperation.execute` (ScarabHive 1007) | **fantôme** | itère les tuiles |
| `SpawnUnitOperation.execute_self_replica` (ScarabSummon 1047) | **fantôme** | idem |
| `_spawn_config_grot` (8 abilities : SquigHound, ControlEdict, MasterOfTheTutelaries, DeathFromAbove, SporeMineLauncher, AlphaWarrior, IronkinSteeljack, neophyte…) | `tile is None` gardé, mais **`tinfo is None` non gardé** | tuile résolue AVANT `add_entity` |
| `spawn_decoy` | idem | idem |
| `execute_pilein_replica` | idem | idem |

**Les CINQ points d'entrée de `SpawnUnitOperation` portent la règle**, pas seulement `execute` :
l'entité ne peut plus naître avant sa tuile nulle part dans la classe. `execute_pilein_replica`
gardait bien `tile is None` — mais laissait passer « id de tuile non résolu sur le board », puis
posait la `PositionComponent` de façon CONDITIONNELLE : le fantôme sous sa forme LATENTE. Ce chemin
n'est pas atteignable avec un `Board` réel (`Board.neighbours_native` filtre déjà sur `by_id`, et
`Board.walkable` l'indexerait), donc **son durcissement ne change aucun comportement mesurable** —
c'est un mirror de structure qui rend l'invariant vrai par construction, et une garde le verrouille
(`test_pilein_replica_requires_a_tile`, régimes 1 et 0 voisines libres).

**Pourquoi c'est devenu atteignable maintenant** : le masque de 1007 (`0x4020` =
`TargetHasFreeAdjacentTile | TargetIsEnemy`, `case-250-summon-targeting`) impose au caster d'être
**au contact** de sa cible — il consomme donc une voisine — alors que le bit 5 n'exige qu'**une
seule** voisine libre pour autoriser le cast d'une ability qui en spawne **deux**. Le défaut, lui,
est là depuis l'origine du port : ce n'est pas une régression.

---

## 3. Mesure — natif vs port, avant/après

`scripts/python/probe_spawn_requires_tile.py`. Roster `necroSpyder ×2 + necroOverlord` vs
`necroWarden ×3`, runner `--no-ai`, **un runner dédié par phase** (les summons d'une phase bouchent
la géométrie de l'autre et rendaient le montage non reproductible). Le caster est **amené au
contact** par `applyAction move`, la couronne de la cible est **saturée / dégagée** par
déplacements (`_saturate` / `_free_up` / `_tune_free`) : on drive la géométrie, on ne la subit pas.
Les unités apparues sont comptées par **différence d'ids** de `decisionView`, jamais par `visualId`
(le visuel d'un spawn n'est pas l'id gameconfig du summon — piège #248).

**Build `gqfc5mff6c`, session Frida 16.**

| couple | régime | natif | port AVANT | port APRÈS |
|---|---|---|---|---|
| `MC1_67`/777 | 2 voisines libres | **2** — (5,7) (4,8) | 2 | **2** — (5,7) (4,8) |
| `MC1_67`/777 | 1 voisine libre | **1** — (6,6) | **2, dont 1 sans `PositionComponent`** | **1** — (6,6) |
| `MC1_67`/777 | 0 voisine libre | cast **REFUSÉ** (bit 5 `TargetHasFreeAdjacentTile`) | **2 fantômes** | **0 entité créée** |
| `C3_26`/31337 | 2 voisines libres | **2** — (6,2) (6,4) | 2 | **2** — (6,2) (6,4) |
| `C3_26`/31337 | 1 voisine libre | **1** — (5,1) | **2, dont 1 sans `PositionComponent`** | **1** — (5,1) |
| `C3_26`/31337 | 0 voisine libre | cast **REFUSÉ** | **2 fantômes** | **0 entité créée** |

Le régime « 1 libre » reproduit exactement la mesure d'origine (`spawned = [1, 2]`, un des deux hors
plateau). Le régime « 2 libres » est la **contre-épreuve** : le correctif ne mange aucun spawn
légitime, et les **positions sont identiques au natif** dans les deux régimes — le placement
(`SortByDistance` ×2 puis prise en tête) n'a pas bougé.

La mesure « AVANT » a été obtenue en `git stash`-ant le seul `spawn.py` puis en rejouant le probe :
c'est le comportement de `master`, pas une reconstitution.

### Re-mesure sur le build `rnca9r7q6c` (session Frida 19)

Le fix a été livré sur `gqfc5mff6c` ; le jeu s'est mis à jour ensuite. La RE **et** les 6 lignes ont
été refaites sur le nouveau build, sans rien changer :

* **structure native identique** — `SpawnUnitBehaviour$$Execute` sur `rnca9r7q6c` teste toujours
  `*(options + 0x60)`, prend toujours le `foreach` sur l'énumérateur du tile-sélecteur
  (`*(entities + 0x58)`, résolu **une** fois) dans la branche `== 0`, et toujours l'appel unique sur
  `GetTileIds(tiles)` dans l'autre. Aucune des deux branches n'a bougé ;
* **6/6 lignes reproduites**, avec les **mêmes positions au hex près** que sur `gqfc5mff6c` :
  `MC1_67`/777 → `(5,7) (4,8)` à 2 libres, `(6,6)` à 1 libre, refus à 0 ;
  `C3_26`/31337 → `(6,2) (6,4)`, `(5,1)`, refus. Natif == port dans les six cas, **zéro fantôme**.

Un changement de build ne fait donc rien bouger ici : c'est la même fonction, et le port lui reste
bit-exact.

---

## 4. Ce qui est confronté live, et ce qui ne l'est pas

**Tout ce qui est listé ci-dessous a été rejoué sur `rnca9r7q6c` / session 19** (la vague différée
par la migration de build est fermée) :

| suite | verdict |
|---|---|
| `probe_spawn_requires_tile.py` (les 6 lignes du §3, deux couples) | **6/6 OK**, positions bit-exactes |
| `test_summon_spawn_live.py` (dont `test_spawn_requires_a_tile` et `test_pilein_replica_requires_a_tile`) | **3 verts** |
| `test_scarab_hive_migration_live.py` + `test_scarab_summon_migration_live.py` | **2 verts** (les deux Operations modifiées) |
| `test_multihex_dutyeternal_live.py` | **20 verts** (branche `+0x60 != 0` intacte) |
| `test_control_edict_live.py`, `test_spore_mine_launcher_live.py`, `test_alpha_warrior_live.py`, `test_ironkin_steeljack_live.py`, `test_aberrant_hypermorph_live.py` | **18 verts** (`_spawn_config_grot`) |
| `test_skitarii_turn_live.py`, `test_rad_saturation_live.py`, `test_cosmic_horror_live.py`, `test_mow_caster_load_live.py` | **21 verts** (`_spawn_config_grot`) |
| `test_decoy_foundation_live.py`, `test_decoys_misdirection_migration_live.py`, `test_hypersensory_moveandspawndecoy_live.py` | **11 verts** (`spawn_decoy`) |
| `test_endturn_order_live.py`, `test_maybe_trigger_rng_live.py` | **verts** (consommateurs de `execute_pilein_replica`) |

Sur `gqfc5mff6c`, la garde `test_spawn_requires_a_tile` avait été **vérifiée ROUGE** sans le fix
(`AssertionError: 1 tuile(s) libre(s) -> 2 summons != 1`) — c'est ce qui lui donne sa valeur ; elle
n'a pas été re-cassée sur `rnca9r7q6c` (le comportement fautif n'existe plus dans l'arbre).

**Ce qui n'est PAS couvert** : la branche `+0x60 != 0` n'est exercée que par `DutyEternal` (1158),
seul producteur d'empreinte multi-hex du binaire — aucun autre consommateur n'existe pour la
confronter ; et `test_pilein_replica_requires_a_tile` est un **cliquet**, pas un test discriminant
(le durcissement qu'il verrouille n'a pas de chemin atteignable, cf. §2).

---

## 5. Résidus nommés (non fermés ici)

* **`AddUnitOperation$$Execute` avec une liste de tuiles vide** produit nativement une unité sans
  pied (§1). Non porté : aucun call-site du binaire ne l'exerce (le seul consommateur de
  `+0x60 != 0` est `DutyEternalAbility$$ExecuteBehaviour`, dont le sélecteur rend 3 tuiles).
* **`execute_self_replica` boucle `count` fois sur un `PickRandomly(…, 1)`** là où le natif tire son
  sélecteur une fois. Inerte : `SpawnReplica` n'est instancié qu'avec `count = 1`
  (`abilities/loki/summon.py` → `SpawnReplica("ScarabSummon", 1)`), et c'est son seul site de
  construction. À revoir si un jour un auto-dédoublement `count > 1` apparaît — le porter
  aujourd'hui serait spéculatif.

**FERMÉ depuis** : le résidu « `execute` ré-évalue son tile-sélecteur à chaque tour de boucle » n'en
est plus un. `SpawnUnitBehaviour$$Execute` résout `tileSelector.Select(ctx)` **une** fois puis itère
le résultat ; `execute` fait désormais pareil — un seul `CanAddUnit(AdjacentTiles(target))`, un seul
double `SortByDistance`, puis `[:count]` (le `First(source, count)` natif). Les deux formes rendent
la même suite (retirer la tête ne change pas l'ordre relatif du reste, et les `OrderBy` LINQ sont
stables), ce que les positions bit-exactes du §3 **re-mesurées après le changement** confirment —
mais seule la seconde a la forme du natif, et donc son comportement si l'état changeait ENTRE deux
spawns (un `On(UnitAdded)` qui tuerait une unité et libérerait une tuile).
