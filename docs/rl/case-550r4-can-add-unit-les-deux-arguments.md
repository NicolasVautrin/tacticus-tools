# case-550-r4 / #462-…-r5-r3 / #287-r11-r2-r1-r3 — les DEUX arguments de `CanAddUnit`, et le nœud qui manquait

Tranche SÉLECTEURS DE TUILES. Build `t6dpr4k06g`. Foyer principal :
`engine/entities/selectors/tiles.py`. Foyers touchés : `engine/dsl/base.py`,
`engine/runner/abilities/behaviours/context.py`, `engine/runner/operations/{movement,displace}.py`,
`engine/runner/abilities/{tyranids,orks}.py`, `engine/runner/abilities/loki/mv71.py`,
`engine/runner/operations/triggers/loki/haywire_mine.py`,
`engine/entities/selectors/composites.py`.

> **Le fil de la tranche** : `IdunBattle.Entities.Selectors.CanAddUnitTileSelector$$Select` passe
> DEUX arguments à `TileExtensions$$CanAddUnitFromAbility` — `parent` et `allowSteppable`. Le port
> n'avait **ni l'un** (le gate de réservation n'était pas joué) **ni l'autre au bon sens** (le défaut
> était l'inverse de celui du natif). Les deux erreurs vivaient dans la même fonction, et aucune
> n'avait de symptôme.

## 1. `parent` — il ne vaut pas « rien », il vaut `None()` (#550-r4)

```csharp
CanAddUnitFromAbility(tile, state, parent, allowSteppable) {
    if (!IsFreeTile(tile, state, allowSteppable, 0, 0))  return false;   // porté
    if (IsTileReservedForOtherUnit(tile, parent))        return false;   // ← manquait
    if (IsTilePendingDrafting(tile, state, 0))           return false;   // NON PORTÉ, dit
    return true;
}
```

`Select` résout `parent` par le sélecteur `<this+0x20>`. Ce que les trois surcharges de
`IdunBattleLogic.Entities.DSLSelectors$$CanAddUnit` y mettent est **LU** :

| surcharge | xrefs de code | `parent` |
|---|---|---|
| `CanAddUnit(tiles)` | 123 | `new EntitySelector(state, entityId: null)` |
| `CanAddUnit(tiles, isSteppable)` | 15 | idem |
| `CanAddUnit(tiles, parent, isSteppable)` | **1** (`ItItchesAbility$$ExecuteBehaviour`) | celui de l'appelant |

⚠ **Le sélecteur par défaut est identifié par IDENTITÉ DE CORPS, pas par son nom** : les deux
premières surcharges allouent le MÊME `Il2CppClass*` avec le MÊME ctor et les MÊMES arguments
`(state, 0, 0)` que `IdunBattleLogic.Entities.DSLSelectors$$None()`. Le type est nommé par la
surcharge voisine `DSLSelectors$$Entity(entityId)`, dont le ctor est
`IdunBattle.Entities.Selectors.EntitySelector$$.ctor(this, state, entityId)`. Et
`EntitySelector$$GetEntity` rend `null` quand ses trois champs (`+0x18` entité, `+0x20` id, `+0x28`
sélecteur d'id) sont nuls — ce qui est le cas.

⇒ **`parent` est NUL sur 146 call-sites sur 147**, et `IsTileReservedForOtherUnit(tile, null)` prend
sa branche `allowedUnit == null` = `HasValue` = « réservée par quiconque ». Polarité SAINE.
Sur le 147ᵉ (`ItItches`, qui passe `Owner@+0x30`), la polarité **s'inverse** :
`!(HasValue && Value == parent.Id)` refuse toute tuile **NON** réservée pour lui — ce qui rend le
`Reserve(Owner, targetTiles)` placé juste avant **load-bearing**.

**Les deux omissions se compensaient** : ajouter le gate sans consommer le modèle de réservation
(#550-r1) aurait fait spawner ZÉRO Ripper Swarm. Elles sont portées ensemble.

Substrat : `ctx.tile_reserved_for_other_unit`, délégué au foyer unique
`runner/operations/tile_reservation.py`. **Absent = NON MESURÉ** → le gate ne joue pas du tout ;
le rabattre sur une table vide viderait tout `CanAddUnit(…, parent)` non nul en contexte de
prédiction.

## 2. `allowSteppable` — le défaut du port était l'INVERSE du défaut natif (#462-…-r5-r3)

`CanAddUnitTileSelector$$Select` calcule `allowSteppable = !<this+0x28>.ShouldTrigger(entities, 0x20)`
— il **INVERSE** le trigger reçu. Et `IdunBattleLogic.Entities.DSLTriggers$$.ctor` pose :

```
+0x40 = new <trigger sans champ>()                       // le trigger NU
+0x48 = AbilityTrigger$$op_LogicalNot( new <le même> )   // sa NÉGATION
+0x70 = new <le même>()                                  // déjà nommé `YesTrigger` par le port
```

La chaîne d'accès est fermée par `IdunBattleLogic.Entities.DSLFactory$$.ctor`
(`this+0x88 = new DSLTriggers(this)`) et `DSLSelectors$$.ctor` (`this+0x10 = <la factory>`) — c'est
ce qui restait « à confirmer » dans la fiche, et c'est confirmé.

**Relevé à l'OCTET, call-site par call-site** (`mov r8, [reg+disp8]` juste avant le `call`) :

| trigger passé | `ShouldTrigger` | `allowSteppable` | call-sites |
|---|---|---|---|
| `<DSLTriggers+0x48>` (nié) | faux | **VRAI** | les **123** de la surcharge 1-arg (en dur dans son corps) + `ItItches` + les 6 consommateurs de `FreeTilesOrAdjacentFreeTiles` sans trigger |
| `<DSLTriggers+0x40>` (nu) | vrai | **FAUX** | **14** : `SquigMine` ×2, `OiWatchIt`, `DecoysAndMisdirection` ×2, `HaywireMine` ×2, `SpiritualLeader` ×2, `CultDemagogue` ×2, et les 3 appelants de la surcharge à trigger de `FreeTilesOrAdjacentFreeTiles` (`Ambush_Summon`, `CosmicHorror_OnKill`, `Hypersensory_MoveAndSpawnDecoy`) |

⇒ **14 sur 147 valent FAUX.** Le défaut du port (`allow_steppable=False`) était donc RESTRICTIF sur
la quasi-totalité des sites : il refusait une tuile occupée par un `Steppable` (decoy, mine, spore,
token) que le natif accepte. Le défaut passe à `True` ; les trois sites portés dont l'artefact natif
passe le trigger NU (`haywire_mine` ×2, `orks::squig_mine_pool_tree`) l'écrivent explicitement.

⚠ **La mesure live de Haywire n'est pas contredite, elle est EXPLIQUÉE.** Elle disait « au tour où
la mine occupe `PreviousTile`, le natif ne repose rien » — c'est exactement ce que prédit `+0x40` à
ce call-site. Ce recoupement est ce qui établit le **sens** du trigger nu, et donc celui de sa
négation.

⚠ **Deux lectures du dépôt disaient déjà `+0x48 ⇒ VRAI`** et n'avaient pas été rapprochées de la
surcharge 1-arg : `test_955r2_free_tiles_steppable_offline.py` (qui grave l'appariement slot/valeur)
et `triggers/loki/cursed_of_the_walking_pox.py`. À l'inverse, deux sites portaient la conclusion
INVERSE par **déduction** et non par lecture — `composites.py::random_adjacent_free_tile`
(« passer `True` autoriserait la pose sur un `Steppable` occupé ») et l'assertion
`allow_steppable is False` de `test_939_bio_minefield_offline.py`. Les deux sont corrigés, le test
gardant désormais la valeur MESURÉE.

⚠ **Les jumeaux impératifs du port étaient déjà du bon côté**, et c'est une seconde lecture
concordante : `services/spawn_tile_shape.py` cite `CanAddUnit(tile, state, true, false, false)` et
`battle_query.py` cite « arg3=1 ». Le nœud DSL était le SEUL des trois à coder la branche inverse.

## 3. `SetUnitPositionOperation$$Execute` a ses DEUX gates propres (#550-r4, volet b)

```csharp
feet = GetUnitFeet(unit, state);
if (feet.Count != position.Count)          { log; return; }   // S1
if (UnitExtensions.HasFlag(unit, 6=Dead))  { log; return; }   // S2
```

`6 = Dead` est LU dans `data/symbols/<build>/frida/enums.tsv`, pas déduit du nom.

⚠ **S1 n'est PAS le gate G4 de `MoveUnitOperation`** : G4 porte un bras `tilesToMoveTo.Count == 0 →
true` qui laisse passer le LIFT-OFF, S1 ne l'a pas. Une `UnitPosition` VIDE y est donc REFUSÉE dès
que l'unité a un pied — le seul régime que le collapse mono-hex du port laisse atteignable, et il
est figé par test.

⚠ **La prémisse du résidu était FAUSSE sur la moitié S2, et c'est mesuré.** Elle annonçait « un
déplacement forcé sur une unité morte est accepté côté port ». Il ne l'est pas : les quatre
Operations de `displace.py` portent déjà un gate `alive` en tête, et `SwitchPosition` lit
`dead_caster`/`dead_target`. **Deux écarts subsistent, et ce sont eux qui sont réels** :

1. **le PROPRIÉTAIRE** — ces gates étaient documentés « ABSENT du natif, CONSERVÉ » (#498-r2). C'est
   faux : leur artefact est S2, c'est-à-dire le slot `0x7e` par lequel ces Operations ÉCRIVENT la
   position. La prose est corrigée aux trois sites ;
2. **le RANG** — le natif ne saute QUE l'écriture de position puis joue quand même `AddTilesMoved`
   et `EventAndAbilitiesAndEffects`, là où le `return` du port abandonne toute l'opération.
   Résidu **`#550-r4-r1`**.

S2 est donc porté au rang natif (`set_unit_position_gates`, orthogonal à `enforce_native_gates` :
`TheQuickening` et `FleeOperation` portent le second sans mirroiter `SetUnitPositionOperation`), et
il est **aujourd'hui DOUBLÉ** par le second bras du gate (c) du bloc override de
`MoveUnitOperation$$Execute` (`if (!ovr.HasValue || IsDead(unit)) return`), que le port joue
inconditionnellement — y compris aux stand-ins, où ce gate-là n'a rien à faire. Le test le dit et
rougira le jour où ce doublon sera défait.

## 4. `UnobscuredTiles` devient un nœud DSL — et le cycle annoncé n'existe pas (#287-r11-r2-r1-r3)

L'artefact natif est un `IdunBattleLogic.Entities.DSLSelectors$$UnobscuredTiles`, donc un ARBRE
(doctrine #149) — exactement comme son voisin de chaîne `FilterTilesIfCanAttackTargetTileFrom`,
nœud depuis #433-r4-r1. Le port en avait la DÉCISION, collapsée dans `mv71._is_obscured_from_tiles`.

Le nœud porte la formule ENTIÈRE, y compris ce que le collapse ne disait pas :

* `Select` sort sur **`if (caster.Count == 0) return <liste VIDE>`** — sans tuile source, TOUT est
  retiré. Le collapse atteignait le même observable par `IsObscured → true`, mais par un autre
  chemin ;
* `IsObscured` = `∀ f ∈ fromTiles : |GetTilesObscuringTerrain(f, target, 6=All, 2)| > 0` — une seule
  ligne dégagée suffit à garder la candidate. Le slot **16** est lu dans
  `data/symbols/<build>/metadata/interface_slots.tsv` (`IMovementQuery 16 GetTilesObscuringTerrain`) ;
* le ctor **inverse les noms** de ses deux sélecteurs (`+0x20 = fromAnyTiles`, `+0x18 = toTiles`),
  ce qui est écrit au nœud pour qu'un lecteur ne les échange pas.

⚠ **LE BLOCAGE `etage` DE LA FICHE ÉTAIT FAUX.** Elle annonçait qu'il fallait « HISSER le foyer hors
de `mv71`, donc trancher le cycle `services.battle_query -> movement_query` ». Or le foyer du calcul
n'est PAS dans `mv71` : c'est `engine/services/movement_query.py::get_tiles_obscuring_terrain`, un
module partagé. `mv71` n'en portait que la boucle. Et la mesure d'import (process FRAIS) :

| mesure | résultat |
|---|---|
| `movement_query` seul → `entities.selectors.tiles` dans `sys.modules` | **True** (donc un import direct depuis `tiles.py` fermerait un cycle) |
| `movement_query` seul → `abilities/behaviours/context.py` | **False** |
| `context.py` seul → `movement_query` | **True** (déjà dans sa cascade) |

⇒ la voie est l'**ACCESSEUR de ctx** — le mécanisme que cette couche utilise déjà pour
`sort_tiles_by_utility`, `previous_tiles`, `is_in_team_aura`. `ctx.tiles_obscuring_terrain` est posé
par `entities_from_state` (face RUNNER, arête **GRATUITE** par la mesure ci-dessus) et par le site
qui bâtit son `DslContext` à la main (face DÉCISION de `mv71`). **Aucun hissage, aucun différé,
aucun cycle.**

Les DEUX consommateurs portés sont rebranchés (faces runner et décision de `PickTile`).

⚠ **Le renommage a cassé QUATRE lecteurs, dont un que le test ne voyait pas** : trois dans
`test_287r11r2r1_los_summon_offline.py`, et un **accès attributaire** dans
`probe_287r11r2r1_los_summon_live.py` (`MV._is_obscured_from_tiles = …`), c'est-à-dire un
contre-modèle qui aurait cessé de MORDRE en silence. C'est `test_485r2_portee_des_noms_offline.py`
qui l'a trouvé, pas la passe de tests.

## 5. `1193 NovaCharge` — NON PORTÉE, et le `BLOCAGE` de la fiche est à corriger (#895-r1)

Verdict inchangé sur le fond : **port refusé, il serait SPÉCULATIF**. Le masque `0x2000000042` porte
`CasterHas7Tiles`, `TargetingQuery$$GetInvalidCasterReason` refuse `GetFeetCount(caster) != 7`, et le
boss monté rend **0** cible légale — aucun canal ne validerait le behaviour.

**Ce que cette tranche mesure, et qui change la fiche :**

* **`BLOCAGE: porteur` est FAUX — c'est `seeding`.** Le boss EST montable et le montage est déjà
  celui qu'il faut : `probe_895` utilise `--explicit-stats tauBossRiptide:4 --p-units … --board
  GB_Riptide_01` (sa carte dédiée). Ce qui manque n'est pas le porteur, c'est son **EMPREINTE** ;
* **le canal manquant est nommé** : `IdunBattle.Operations.AddUnitOperation$$Execute` crée UN
  `Blueprints$$UnitFoot` **par tuile de la position de déploiement** (`ClearFeet`, puis une boucle
  `AddFoot` sur la liste reçue). Le nombre de pieds n'est donc dérivé d'aucun trait — pas même de
  `BigTarget`, que le boss porte — il est le **cardinal de la `UnitPosition` d'ajout**. Le montage
  `rl_duel` en fournit une seule ;
* **la greffe est éliminée** : le masque est statique et suit l'ABILITY, pas le porteur — la greffer
  sur un héros du pool ne lèverait pas `CasterHas7Tiles` ;
* **la validation par un AUTRE consommateur est éliminée aussi**, et c'est mesuré : 4 des 5
  primitives manquantes ont d'autres consommateurs natifs (`DirectionTo` : `TheWailingDoom` ×3,
  `SolarAtomizer`, `ArmouredMight_Move` ×4 · `TilesWithEnemies` : `AAnnihilatorBeam`,
  `UnbridledCarnage` ×3, `…Reworked` ×3 · `CenterTiles` : `TheWailingDoom` ×3 · `NextTileClockwise` :
  `TheWailingDoomStrikes`), mais **aucun de ces consommateurs n'a son sélecteur porté** — seul
  `SolarAtomizerAbility` est au registre, et pas par ce chemin. `NextTileInLine` n'a **aucun** autre
  consommateur (2 xrefs, toutes deux dans `NovaChargeAbility$$GetLineTiles`).

## 6. Mesures

### 6.1 Offline

`tests/engine/runner/test_550r4_462r5r3_can_add_unit_offline.py` — **12 étages**, dont 2 qui lisent
`GameAssembly.dll` (résolution par `ghidra/functions.tsv`, RVA calculée en code, corps borné par la
fonction suivante — sans ce bornage, un blob de taille fixe faisait répondre DEUX surcharges au même
critère).

| étage | ce qu'il grave |
|---|---|
| 1 | la surcharge à UN argument charge `<DSLTriggers+0x48>` depuis le contexte partagé — et **pas** `+0x40` |
| 2 | `HaywireMine` et `SquigMine` chargent `+0x40` (contre-épreuve : sans elle, le paramètre n'aurait pas de raison d'exister) |
| 3-4 | le défaut du nœud est `True` ; les 3 sites portés qui posent `False` le font toujours ; les deux branches mordent sur le MÊME état |
| 5-7 | les deux polarités du gate de réservation, le tri-état du substrat, et `ItItches` qui porte `parent_sel` **et** son `Reserve` amont |
| 8-9 | S1 (lift-off refusé), S2 (raison nommée + le doublon mesuré), et les 5 stand-ins de `displace.py` armés — vérifié par **AST**, un comptage textuel rendait 9 pour 5 (les commentaires) |

**Non-régression** : 141 fichiers offline touchant `CanAddUnit` / `MoveUnitOperation` / `displace` /
`spawn` / `steppable`, joués en 6 groupes. **27 rouges**, tous confrontés à un arbre témoin extrait
de `8dfd75d5` (`git archive` COMPLET, `data/` inclus) : **23 sont des rouges de `master`**, les 4
restants étaient les lecteurs du renommage ci-dessus, réparés.

### 6.2 Live

**NON CONFRONTÉ — fenêtre DRAIN.** La vague ciblée (`test_it_itches_live`,
`test_mv71_sniper_drone_live`, `test_462_…_r5_haywire_pose_live`, `test_498r3_switch_position_gate_live`)
est tombée pendant une fenêtre de reinject : les builds de runner refusent avec
`initAndStart: Fenetre de reinject`. Aucun verdict n'en est tiré.

## 7. Reproduction

    python -m pytest scripts/python/tests/engine/runner/test_550r4_462r5r3_can_add_unit_offline.py
    python -m pytest scripts/python/tests/engine/test_287r11r2r1_los_summon_offline.py
    python -m pytest scripts/python/tests/engine/runner/test_955r2_free_tiles_steppable_offline.py
    python -m pytest scripts/python/tests/engine/runner/test_939_bio_minefield_offline.py
    python -m pytest scripts/python/tests/engine/test_287r11r2_mv71_gate_offline.py
