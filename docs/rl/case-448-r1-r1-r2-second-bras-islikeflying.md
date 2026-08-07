# case-448-r1-r1-r2 — le SECOND BRAS d'`IsLikeFlying`, fermé

`#448-r1-r1-r2`. Le résidu était écrit ainsi : « **Le second bras d'`IsLikeFlying`**
(`options.<+0x8> == 3`) : la struct `options` d'`Execute` n'est pas modélisée et aucun call-site du
port ne la pose. » Il est **fermé**. La RE a corrigé au passage **le canal de mesure annoncé**, qui
est structurellement aveugle à ce bras.

---

## 1. Quels sont les DEUX bras — et lequel manquait

Il y a **deux fonctions natives homonymes**, et le résidu parle de la seconde :

| symbole | arité | corps |
|---|---|---|
| `IdunBattle.Entities.UnitExtensions$$IsLikeFlying` | `(unit)` | `HasTrait(0x4 = Flying) \|\| HasTrait(0x13 = Burrow)` |
| `IdunBattle.Operations.MoveUnitOperation$$IsLikeFlying` | `(unit, options)` | ci-dessous |

```csharp
bool IsLikeFlying(IEntity unit, MoveUnitOptions options) {
    if (UnitExtensions.IsLikeFlying(unit)) return true;      // BRAS 1 -- les TRAITS
    var ov = options.<+0x8>;                                 // Nullable<PathfinderType>
    if (!ov.HasValue) return false;
    return ov.Value == PathfinderType.Fly /* 3 */;           // BRAS 2 -- l'OVERRIDE d'OPTIONS
}
```

Les **deux** bras de `UnitExtensions$$IsLikeFlying` (Flying **et** Burrow) étaient déjà portés.
Ce qui manquait est le **second bras de la fonction de l'opération** : l'override porté par la
struct `options`.

Le type du champ `+0x8` n'est pas une déduction : `IdunBattle.Operations.MoveUnitOperation$$CalculatePaths`
le relit deux lignes plus loin par `Nullable.get_HasValue` / `get_Value` pour **écraser** le type
résolu par `MovementQuery$$GetPathfinderTypeForUnit`. `PathfinderType.Fly = 3` (dump d'enums du
build : `0=Walk 1=IgnoreTerrain 2=Beeline 3=Fly 4=IgnoreDoor 5=WaveValidator 6..13` décorés).

**`MoveUnitOptions`** = `ValueType`, `classes.tsv` publie **40** = la taille BOXÉE ⇒ **24 octets**
réels. Offsets connus : `+0x8` `Nullable<PathfinderType>` (cette tranche), `+0x11` `setMoved`,
`+0x12` `skipPreMoveTriggers`, `+0x15` `allowNullTargetPosition`, `+0x16` `recordTiles`.

## 2. Pourquoi il n'avait pas été porté — le chaînon manquant, nommé

Le port de la feuille DSL `FlyUnit` (`abilities/behaviours/movement.py`) portait ce résidu :

> la SEMANTIQUE de ce `Nullable(3)` n'est PAS resolue (le champ `+0x08` de
> `MoveUnitBehaviourOptions` n'a aucun lecteur lu au decompile a ce stade)

**Le lecteur existe**, et il est à deux sauts : `MoveUnitBehaviour$$Execute` recopie le champ
`+0x08` de son `MoveUnitBehaviourOptions` (0x40 octets) dans le `MoveUnitOptions+0x08` (0x18) qu'il
passe au slot `MoveUnit` de l'`IOperationProcessor` — d'où `MoveUnitOperation$$Execute`, puis les
deux lecteurs ci-dessus. La recherche s'était arrêtée au premier saut.

## 3. Les producteurs de l'override — EXHAUSTIFS, par les XREFS du `.ctor` du `Nullable`

Le `MethodInfo*` de `Nullable<PathfinderType>..ctor` a **quatre** lecteurs dans tout le binaire :

| # | producteur | ce qu'il pose |
|---|---|---|
| 1 | `IdunBattleLogic.Entities.DSLBehaviors$$FlyUnit(unit, tiles)` | alloue un `MoveUnitBehaviourOptions` de 0x40 octets ZERO et n'y écrit **QUE** `+0x08 = Nullable(3)` |
| 2 | `IdunBattleLogic.Entities.Abilities.Active.Loki.TreasonOfTzeentchAbility$$ExecuteBehaviour` | via `DSLBehaviors$$MoveUnit`, `options[+0x08] = Nullable(3)` |
| 3 | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.NovaBoost_AttackAbility$$CreateBehaviour` | le **second** `MoveUnit` (l'atterrissage, `GetLandPosition`) ; le premier a `+0x08` nul |
| 4 | `IdunBattle.Messages.InputMessageProcessor.u003Cu003Ec__DisplayClass40_0$$u003CVisitu003Eb__0` | la lambda de `Visit(**CheatMoveUnitMessage**)` |

**Le #4 est identifié par les champs CAPTURÉS, pas par le nom** — et ce point est décisif. La
lambda lit `+0x10` (le processeur), `+0x18` (l'unité), `+0x20` (la liste de tuiles) : exactement
les **trois** champs que pose `Visit(CheatMoveUnitMessage)` (`RunPhase(this, 0x10, ...)`), là où
`Visit(MoveUnitMessage)` en pose **quatre** (`+0x20 = message`, `+0x28 = List<TileEntity>`,
`RunPhase(this, 5, ...)`).

⇒ **le mouvement joueur ordinaire ne pose AUCUN override**. Corroboré par un chemin indépendant :
la non-régression MARCHEUR de `#448-r1-r1-r1-r1` (bras W, 10 mesures, 0 désaccord) serait tombée
sinon.

## 4. Ventilation des porteurs — hero / MoW / summon / npc

Call-sites natifs de `FlyUnit` (8 sites, 7 abilities) plus les deux `MoveUnit` à override :

| ability | porteur(s) | catégorie | chemin d'arrivée en bataille |
|---|---|---|---|
| `GrapnelLauncher` | **`spaceHound` (Tjark)** | **HERO, au pool** | direct — **et NON DÉGÉNÉRÉ** (traits `Hero/Infiltrate/Terrifying`) |
| `EmpyricAmbush` | `eldarLhykhis` | HERO, au pool | direct — mais **DÉGÉNÉRÉ** : trait `Flying` ⇒ bras 1 déjà vrai |
| `LightOfSanguinius` | `bloodDante` | HERO, au pool | direct — **DÉGÉNÉRÉ** : trait `Flying` |
| `KissOfDeath` | `eldarNpc3Harlequin` / `eldarSmnHarlequin` | npc + **SUMMON** | summon via son summoner |
| `WallOfMirrors` | `tauNpc5StealthSuit` / `tauSmnStealthSuit` | npc + **SUMMON** | summon via son summoner |
| `NovaBoost` | `tauBossRiptide` | npc | greffe d'ability (`case-92` §5bis) |
| `PhantasmCreate` | 0 des 5 voies dérivables | **non tranché** | `unit_map` imprime ses 4 voies non couvertes |
| `EreWeGo` | 0 des 5 voies dérivables | **non tranché** | idem (le nom du gameconfig n'est pas `EreWeGo`) |
| `TreasonOfTzeentch` | 0 des 5 voies dérivables | **non tranché** | idem |
| `CheatMoveUnitMessage` | — | canal de MESSAGE | hors runner normal |

**Le porteur retenu est `spaceHound`** : c'est le seul call-site de `FlyUnit` **porté** dans
`engine/`, il est au pool, et surtout il **ne porte ni `Flying` ni `Burrow`** — donc son bras 1 est
FAUX et seul le bras 2 peut allumer `IsLikeFlying`. Les deux autres héros sont `Flying` : les
choisir aurait produit un **régime dégénéré** où les deux modèles coïncident.

## 5. RÉFUTÉ : `tilesMovedThisTurn` ne peut PAS mesurer ce bras

La fiche de cadrage annonçait « le canal existe et il est direct : `actorStats.tilesMovedThisTurn` ».
**Il est structurellement aveugle à ce bras**, et c'est lu, pas supposé.

`MoveUnitOperation$$CalculatePaths` produit **DEUX** listes :

| out-param | produit par | voit l'override ? |
|---|---|---|
| `path` (8e) | `Pathfinders$$GetPath(pathfinderType, unit, from, to, useTeleporter)` | **OUI** — `pathfinderType` porte l'override |
| `connectedPath` (9e) | `IdunBattle.Core.Services.BattleQuery$$GetConnectedPathTo(entity, from, to)` | **NON** — signature à **TROIS** arguments, ni options ni pathfinderType ; il re-résout `GetPathfinderTypeForUnit(unit)` seul |

Or, dans `Execute` :

    if (options.<+0x16> == 0) RecordTilesMoved(unit, GetNumTilesMoved(**connectedPath**), state);
    movementSteps = IsLikeFlying(unit, options) ? GetDistance(path.First(), path.Last())
                                                : **path**.Count;

⇒ `tilesMovedThisTurn` compte `connectedPath` ⇒ **il ne bouge pas** quand l'override est posé.
C'est une contrainte de FIDÉLITÉ, pas une limite : un port qui propagerait l'override jusqu'à
`_num_tiles_moved` « par symétrie » serait **infidèle**. Un test le verrouille (§8).

**Le seul effet d'état du bras 2 est donc `movementSteps`**, et `movementSteps` n'a **qu'un**
lecteur dans tout le binaire (xrefs de `IdunBattleLogic.Entities.DSLFormulas$$MovementSteps`) :

    ...FullThrottleAbility$$CreateTrigger  = On(0x24) & OwnerIsActor
                                           & AmountIsEqualOrGreater(MovementSteps(), Direct(3))
    ...FullThrottleAbility$$CreateBehaviour = If(Maybe(chance = 30), Kill(Caster), null)

Second effet du **même champ**, mais qui ne se compose pas : l'override change `path`, donc la
trajectoire, donc la garde native `path vide -> mouvement ABANDONNÉ` et les `AddMoveEvent`. Il ne
touche pas `movementSteps` : dès que l'override vaut `Fly`, `IsLikeFlying` est vrai et c'est la
DISTANCE qui est prise. Même statut pour le troisième forceur de `Fly` de `CalculatePaths`
(`if (previousPosition.IsEmpty()) pathfinderType = 3`) — il n'entre pas dans `IsLikeFlying`.

## 6. Le discriminant, ÉNONCÉ AVANT LA MESURE

Montage : `FullThrottle` greffé (`catalog_inject.graft_passive_ability`) sur `spaceHound`, qui
caste `1090 GrapnelLauncher` — dont le `If` final est `FlyUnit(Caster, <tuile d'ORIGINE de la
cible>)`. Chaque vol est classé par sa géométrie **MESURÉE** (position de Tjark avant/après le
cast), jamais supposée :

    d     = hex_distance(avant, apres)                   <- ce que rend le NATIF si le bras 2 mord
    count = _num_tiles_moved(avant, apres) + 1           <- `path.Count`, le port SANS le bras 2

| bras | condition | prédiction AVEC le bras 2 | prédiction SANS (le port d'avant) |
|---|---|---|---|
| **A** contrôle POSITIF | `d >= 3` et `count >= 3` | gate VRAI -> ~30 % | gate VRAI -> ~30 % |
| **B** DISCRIMINANT | `d < 3` et `count >= 3` | gate FAUX -> **0 mort** | gate VRAI -> ~30 % |
| **C** contrôle NÉGATIF | `d < 3` et `count < 3` | FAUX -> 0 mort | FAUX -> 0 mort |

**B n'est pas dégénéré** : `count = d + 1` dès que le chemin de marche est direct, donc les deux
modèles rendent des valeurs DIFFÉRENTES (2 contre 3) que le seuil 3 sépare.
**A est obligatoire** : sans lui, « 0 mort partout » se lirait comme un verdict alors que ce
serait un montage inerte — l'absence d'événement ne prouve rien.

⚠ **Piège de montage neutralisé** : tout pas de Tjark émet lui aussi un `On(0x24)` avec
`movementSteps = path.Count`, donc un repositionnement de 2 pas suffirait à le tuer **avant** le
cast, et cette mort se lirait comme une mort du vol. C'est la **CIBLE** qu'on déplace (elle ne
porte pas le passif) ; Tjark n'ajuste que d'**UN** pas (`count = 2 < 3`, gate inoffensif).

## 7. La mesure — 8 runners, 70 vols

`probe_448_r1_r1_r2_fly_override.py`, board `MC1_67`, `--no-ai`, seeds 777 / 31337 / 4242 / 999 /
12345 / 555.

| bras | essais | morts | `P(0 mort \| gate vrai)` |
|---|---|---|---|
| **A** contrôle POSITIF | **26** | **5** (19,2 %) | — |
| **B** DISCRIMINANT | **22** | **0** | **3,9e-4** |
| **C** contrôle NÉGATIF | **22** | **0** | 3,9e-4 |

* **A tue** (5/26, compatible avec les 30 % du kit : moyenne 7,8, écart-type 2,3) ⇒ le montage
  MORD, la greffe est vivante et le trigger armé.
* **B ne tue JAMAIS** sur 22 vols dont le chemin de marche vaut 3 pas ou plus ⇒ le natif lit la
  **DISTANCE**. Le port d'avant, qui aurait lu `path.Count >= 3`, est **réfuté** à 3,9e-4.
* **C** confirme le bord inférieur.

## 8. Le port, et les contre-épreuves

* `runner/operations/movement.py::_is_like_flying(traits, override)` — mirror 1:1 des deux bras.
  Le `== 3` est **STRICT** : `TeleportStrikeFly = 7`, malgré son nom, ne compte pas.
* `MoveUnitOperation(pathfinder_type_override=...)` — mirror du `Nullable<PathfinderType>`. `None`
  = le `Nullable` VIDE. Il **survit à la relance** après un override de destination : le natif
  recopie la struct `options` dans son appel récursif (il n'y touche que pour poser `+0x12 = 1`).
* `abilities/behaviours/movement.py::FlyUnit` — pose `PathfinderType.Fly`, seul champ que
  `DSLBehaviors$$FlyUnit` écrit. `MoveUnit` ne le pose pas (aucun call-site porté n'a d'options).
* `_num_tiles_moved` — **INCHANGÉ**, et c'est la garde §5.

Contre-épreuve `--mutate-no-second-arm` (le port d'AVANT) : l'étape 0 rougit sur **exactement une**
ligne, `traits=Hero override=3 -> False (attendu True)`. Elle mord sur son gisement et nulle part
ailleurs.

## 9. Ce que la tranche ne porte PAS, nommément

* **Le vecteur after-move des feuilles DSL de mouvement** — RÉSIDU **PRÉEXISTANT**, et il rend le
  second bras INERTE côté port aujourd'hui. `after_move_triggers` n'est joué que par
  `MovementHandler.visit_MoveUnitMessage` ; `FlyUnit`/`MoveUnit`/`PushUnit`/`SwitchPosition`
  appellent `MoveUnitOperation.execute` **directement**. `last_movement_steps` est donc calculé
  correctement mais non consommé sur ce chemin. Le corriger toucherait push / switch / quickening /
  genestealer, bien au-delà de ce cas — **résidu `#448-r1-r1-r2-r1`**.
* ~~**`path` dans `MoveUnitOperation`**~~ — **PORTÉ (2026-08-07)**, `_calculate_path` +
  `walk_pathfinder.get_path_by_pos` (même `_dijkstra_by_pos` que les comptes, aucun second port du
  pathfinding), et la garde `path vide -> ABANDONNÉ` est au rang natif. ⚠ Les `AddMoveEvent` par
  pas **n'étaient PAS à porter** : `AddMoveEvent` ne touche aucun composant ECS, c'est un canal de
  VUE (`AOperation.get_Events()` → `AddStep(3, unitId, dict)`). Détail :
  **`docs/rl/case-448-r1-r1-r2-r2-gates-abandon.md`**.
* **`useTeleporter`** : `CalculatePaths` pose `Nullable(GetStat(unit, Movement))` quand
  `IsLikeFlying && GetDistance(startTile, endTile) > Movement`. Argument mort sur les deux routes
  lues (`#448-r1-r1-r1-r1` §4) ; non re-vérifié sur les autres pathfinders.
* **Les trois abilities à porteur non tranché** (`PhantasmCreate`, `EreWeGo`, `TreasonOfTzeentch`)
  — `unit_map find --ability` rend 0 sur les 5 voies dérivables et imprime les 4 non couvertes.
  **NON CONFRONTÉ**, pas « pas de porteur ».
* **Les call-sites `FlyUnit` non portés** (6 abilities sur 7) et les deux `MoveUnit` à override
  (`TreasonOfTzeentch`, `NovaBoost`) : le second bras les servira le jour où ils entreront dans
  `engine/` — la feuille est prête, la valeur d'override est la même.

## 10. Reproduction

    python scripts/python/probe_448_r1_r1_r2_fly_override.py --offline
    python scripts/python/probe_448_r1_r1_r2_fly_override.py --offline --mutate-no-second-arm
    python scripts/python/probe_448_r1_r1_r2_fly_override.py --seeds 777   --rounds 44 --want 3 --out <ABSOLU>
    python scripts/python/probe_448_r1_r1_r2_fly_override.py --seeds 31337 --rounds 44 --want 2 --out <ABSOLU>
    python scripts/python/probe_448_r1_r1_r2_fly_override.py --report "<dir>/p448r2_*.json"
    python -m pytest scripts/python/tests/engine/runner/test_448_r1_r1_r2_fly_override_offline.py

## 11. Non-régression jouée (2026-08-04)

| fichier | verdict |
|---|---|
| `test_448_r1_r1_r2_fly_override_offline.py` (neuf) | **14 passed** |
| `test_448_r1_r1_full_throttle_offline.py` + `test_448_r1_r1_r1_r1_flying_tiles_moved_offline.py` | **41 passed** |
| `test_366_r1_grapnel_launcher_cast_offline.py` | **19 passed** |
| `test_448_r1_r1_full_throttle_live.py` | **3 passed** |
| `test_448_r1_r1_r1_flying_movement_steps_live.py` | **5 passed** |
| `test_448_r1_r1_r1_r1_flying_tiles_moved_live.py` | **8 passed** |
| `test_tiles_moved_combat_live.py` | **8 passed** |
