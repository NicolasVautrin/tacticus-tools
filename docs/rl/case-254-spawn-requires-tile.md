# case-254 — Le spawn NAÎT de la tuile : plus de summon fantôme hors plateau

> **Numérotation** : ce cas a été dispatché sous l'étiquette **#246**, numéro **déjà occupé** par
> `case-246-thunderous-assault-targeting.md` (livré le 2026-07-29) — d'où la renumérotation en
> **254**. L'entrée de backlog visée est bien
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

`execute_pilein_replica` était déjà juste (`if tile is None: return []`).

**Pourquoi c'est devenu atteignable maintenant** : le masque de 1007 (`0x4020` =
`TargetHasFreeAdjacentTile | TargetIsEnemy`, `case-250-summon-targeting`) impose au caster d'être
**au contact** de sa cible — il consomme donc une voisine — alors que le bit 5 n'exige qu'**une
seule** voisine libre pour autoriser le cast d'une ability qui en spawne **deux**. Le défaut, lui,
est là depuis l'origine du port : ce n'est pas une régression.

---

## 3. Mesure — natif vs port, avant/après

`scripts/python/probe_254_spawn_requires_tile.py`. Roster `necroSpyder ×2 + necroOverlord` vs
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

---

## 4. Ce qui est confronté live, et ce qui ne l'est pas

**Confronté live sur `gqfc5mff6c`, avant la mise à jour du jeu** (mesures et décompilé du **même**
build — aucun mélange) :

* `probe_254_spawn_requires_tile.py` — les 6 lignes du tableau §3 ;
* `tests/engine/runner/test_summon_spawn_live.py` — 2 tests verts, dont la garde
  `test_spawn_requires_a_tile` (et **vérifiée ROUGE** sans le fix :
  `AssertionError: 1 tuile(s) libre(s) -> 2 summons != 1`) ;
* `tests/engine/runner/test_scarab_hive_migration_live.py` + `test_scarab_summon_migration_live.py`
  — 2 verts (les deux Operations modifiées) ;
* `tests/engine/runner/test_multihex_dutyeternal_live.py` — 20 verts (branche `+0x60 != 0` intacte).

**NON CONFRONTÉ LIVE — différé par la MAJ `gqfc5mff6c` → `rnca9r7q6c`.** Les call-sites
`_spawn_config_grot` / `spawn_decoy` n'ont reçu qu'un **durcissement de garde** (`tinfo is None` →
pas d'entité, au lieu d'une entité sans position) ; le chemin nominal est inchangé, mais leurs tests
n'ont pas été rejoués :

| à rejouer après migration | montage |
|---|---|
| `test_control_edict_live.py`, `test_spore_mine_launcher_live.py`, `test_alpha_warrior_live.py`, `test_ironkin_steeljack_live.py`, `test_aberrant_hypermorph_live.py`, `test_skitarii_turn_live.py`, `test_rad_saturation_live.py`, `test_cosmic_horror_live.py`, `test_mow_caster_load_live.py` | leurs montages propres (aucun paramètre à changer) |
| `test_decoy_foundation_live.py`, `test_decoys_misdirection_migration_live.py`, `test_hypersensory_moveandspawndecoy_live.py` | idem, pour `spawn_decoy` |
| `probe_254_spawn_requires_tile.py` (les 6 lignes) | `python probe_254_spawn_requires_tile.py` — deux couples par défaut |

Le renommage `#246 → #254` est **postérieur** aux runs verts et ne touche que des docstrings et des
messages d'assertion : le code exécutable testé est celui qui est livré.

---

## 5. Résidus nommés (non fermés ici)

* **`AddUnitOperation$$Execute` avec une liste de tuiles vide** produit nativement une unité sans
  pied (§1). Non porté : aucun call-site du binaire ne l'exerce (le seul consommateur de
  `+0x60 != 0` est `DutyEternalAbility$$ExecuteBehaviour`, dont le sélecteur rend 3 tuiles).
* **`SpawnUnitOperation.execute` ré-évalue son tile-sélecteur à chaque tour de boucle** (en excluant
  les tuiles déjà prises) là où le natif l'évalue **une seule fois** avant d'itérer. Les deux
  suites coïncident (retirer un élément ne change pas l'ordre relatif des autres, et les `OrderBy`
  LINQ sont stables) — c'est ce que les positions bit-exactes du §3 confirment — mais ce n'est pas
  la **structure** native. Un état qui changerait ENTRE deux spawns (l'`On(UnitAdded)` d'un summon
  qui tuerait une unité et libérerait une tuile) les ferait diverger ; aucun consommateur porté ne
  le fait aujourd'hui.
* **`execute_self_replica` boucle `count` fois sur un `PickRandomly(…, 1)`** là où le natif tire son
  sélecteur une fois. Sans effet pour `ScarabSummon` (`count = 1`), à revoir si un jour un
  auto-dédoublement `count > 1` apparaît.
