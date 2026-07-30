# case-224 §4 — le port SUR-ATTEINT d'UNE tuile : le gate #131 était INERTE en silence

Résidu ouvert par `case-224-cursed-plague-bell-extramove` §4 et inscrit au backlog. Confrontation de
`aiMovableTiles` (`IdunBattle.Core.Services.MovementQuery$$GetMovableTilesFor`) au pendant offline
`engine/ai/state_bridge._move_tiles`, sur les couples exacts du constat :

| board / seed | unité | tuile sur-atteinte | la tuile d'où la fill s'étendait à tort |
|---|---|---|---|
| `MC1_67` / 777 | `astraBullgryn` | `(2,3)` | `(1,3)` **Swamp** |
| `MC1_67` / 777 | `worldJakhal` | `(2,3)` | `(1,3)` **Swamp** |
| `MC1_67` / 777 | `necroWarden` | `(3,6)` | `(4,6)` **Swamp** |
| `C4_09` / 31337 | `blackAbaddon` | `(4,4)` | `(4,3)` **Swamp** |

Les quatre cas ont **une seule et même cause**, et ce n'était pas une mécanique manquante.

> ### ⚠ FAUSSE BORNE LEVÉE — à lire avant de citer `test_block_entering_tiles_live`
>
> Ce test portait, en commentaire, une **interdiction de porter** qui reposait sur une confusion
> **BC ↔ live** :
>
> > « les Swamp de `PVP_desert_04` (10 tuiles, elevation 4) ne portent AUCUN `BlockEnteringUnits` …
> > la pose est CONDITIONNELLE … **c'est exactement ce qui interdit de gater sur le TERRAIN**
> > (`tileDefId == 'Swamp'`) : ce serait un sur-blocage ici. »
>
> **Le board DÉPLOYÉ par `--board PVP_desert_04` n'a AUCUNE tuile Swamp.** Son
> `boardGraph.tileDefId` rend `Unplayable 24 / Grass 21 / Block 14 / DryBush 4`. Les « 10 Swamp »
> étaient comptées dans le **dump BC** (`data/boards/**/PVP_desert_04.json`), pas sur le plateau
> réel. Il n'existe donc aucune observation de pose conditionnelle — l'interdiction n'avait pas de
> fondement, et **le repli terrain qu'elle proscrivait est précisément le fix de ce cas**.
>
> Ce qui la remplace n'est pas une autre affirmation, c'est une **mesure** : correspondance
> `Swamp` (terrain lu LIVE) ↔ effet bloqueur, **75 / 75 sur 13 boards, 0 sur-blocage**
> (`probe_pathfinding_overreach.py --audit`, détail en §3.1), `PVP_desert_04` inclus à 0/0.
> Le commentaire du test est corrigé sur place, avec la commande qui le re-dérive.
>
> **La leçon générale** : un comptage de terrain ne vaut que sur `boardGraph.tileDefId`. Le dump BC
> décrit ce que le board *contient*, pas ce que `rl_duel build` *déploie* — et une borne de port
> tirée du mauvais des deux se recopie ensuite de fiche en fiche sans que personne ne la re-mesure.

---

## 1. Ce que le décompilé dit (build `rnca9r7q6c`, chaîne lue en entier)

```
MovementQuery$$GetMovableTilesFor(unit, ignoreUnitFlags, options)
  -> MovementQuery$$FindAnyOrAllMoveableTiles      (gate UnitFlags.Has(1) + UnitExtensions$$CanMove)
     -> MovementQuery$$AnyOrFillMoveableTiles
        range = MovementQuery$$MovementRangeWithAppliedBonus(unit, baseRange, rangeBonuses)
        pour chaque tuile du footprint (EntityExtensions$$GetTiles) :
          reach = MovementQuery$$GetReachableTiles(start, pathfinderType, range, unit)
                  -> Pathfinders$$FindReachableTiles -> <pathfinder>$$FindReachableTiles
                     -> BasePathfinder$$IterateReachableTiles
                        depth = GetEffectiveDepth(start, unit, depth)         [vtable +0x208]
                        + BasePathfinder$$GetMovablePositions  (BFS PAR NIVEAUX, NON pondéré)
                           -> BasePathfinder$$NodesInNextLevel
                              if (node != start && !IsValidContinuePathTile(unit, node))
                                  return <liste vide>            // CUL-DE-SAC
                           -> BasePathfinder$$GetValidNeighbours
                              = AddNeighbours (voisins `ConnectivityComponent`
                                               + IsValidPathNode [vtable +0x1e8])
                              + AddTeleportationTiles + AddShadewalkerTiles
          reach.RemoveAll(t => !MovementQuery$$IsMovableTile(unit, t, ignoreUnitsOnTiles))
        all.AddRange(reach)
```

Deux points que la lecture complète a tranchés, et qui ont orienté tout le diagnostic :

* **L'énumération est bien un BFS par niveaux, non pondéré** — `WeightCost` ne sert qu'à `GetPath`.
  Donc « une tuile de trop » ne peut venir que d'une ARÊTE ou d'un CUL-DE-SAC, pas d'un coût.
* **Le filtre d'arrêt est `MovementQuery$$IsMovableTile`**, plus riche que « tuile non occupée » :

```csharp
IsMovableTile(unit, tile, ignoreUnitsOnTiles) =
      (!TileExtensions$$IsTileReserved(tile) || IsTileReservedForUnit(tile, unit))
   && !TileExtensions$$IsTilePendingDrafting(tile, state, null)
   && TileExtensions$$IsFreeTile(tile, state, allowSteppable: true,
                                 allowTemporaryTile: false, allowAnyUnit: ignoreUnitsOnTiles)
   && !TileExtensions$$IsTemporary(tile)
```

Il fallait savoir lequel des deux étages mordait. **Mesure discriminante** (`aiMovableTiles` ré-interrogé
à `overrideRange` croissant) : la tuile en écart entre dans l'ensemble natif à **`mv + 1`**, jamais à `mv`.

| unité | `mv` | portée à laquelle le natif la rend |
|---|---|---|
| `MC1_67` `necroWarden` (3,6) | 3 | **4** |
| `MC1_67` `worldJakhal` (2,3) | 4 | **5** |
| `MC1_67` `astraBullgryn` (2,3) | 3 | **4** |
| `C4_09` `blackAbaddon` (4,4) | 4 | **5** |

⇒ étage **FLOOD-FILL**, un pas de trop côté port. Le filtre d'arrêt est hors de cause.

---

## 2. La cause : un gate PORTÉ, mais qui ne s'armait jamais

`WalkPathfinder$$IsValidContinuePathTile` = `GetTileBlockingReasons(tile, unit) == 0`. Ce gate est
porté depuis #131 (`engine/entities/pathfinding/tile_blocking.make_can_continue`), et
`state_bridge._move_tiles` l'appelle bien. **Mais il lit `State.effects`, et le canal qui l'alimente
est OPT-IN** : `load_state(..., tiles=tileMeta)`. Sans lui, aucune entité-tuile ne porte d'effet,
`make_can_continue` rend `None`, et la flood-fill s'étend DEPUIS un Swamp.

C'est la dégradation que la docstring de `make_can_continue` annonçait déjà (« ⚠ SEED REQUIS … c'est
la dégradation SÛRE, mais elle est SILENCIEUSE ») — et **la quasi-totalité des call-sites ne passe
pas `tiles=`**, à commencer par celui qui a produit le constat (`probe_224_…` fait
`load_state(dec, ob, snap, board=board)`).

Le probe le mesure des deux côtés, sur le MÊME état, et c'est ce couple qui identifie le résidu :

| régime | `MC1_67`/777 | `C4_09`/31337 | `EMC2_02`/4242 |
|---|---|---|---|
| **A** état chargé SANS `tiles=` | **3** tuiles en trop | **1** | **15** |
| **B** état chargé AVEC `tiles=tileMeta` | 0 | 0 | 6 (cf. §4) |

`GetTileBlockingReasons` n'a donc jamais été faux : il n'était **pas exécuté**.

---

## 3. Le fix — un repli TERRAIN, adossé à l'ability hébergée par le tile-def

`IdunBattleLogic.Entities.Abilities.Tiles.ThornsBlockMovementAbility$$CreateBehaviour` (l'ability que
la tile-config Unity assigne au tile-def **Swamp**) =

```csharp
AddBlockEnteringUnitsEffect(0)
  & AddStaticStatModifierEffectToOwner(0xb, 3, Direct(GetNumberConstant(cfg, 0x14)))
```

⇒ chaque Swamp porte `BlockEnteringUnits` **dès la construction de la bataille**. Un état non hydraté
ne le sait pas, mais le **board**, lui, connaît le `tileDefId` (`boardGraph`). `make_can_continue`
gagne donc un paramètre `board=` et une seconde source, **subordonnée** :

1. le canal **dynamique** `State.effects` — la vérité, quand il existe ;
2. à défaut SEULEMENT, le repli **terrain** (`TERRAIN_BLOCK_ENTERING = {"Swamp"}`).

L'arbitrage n'est pas un drapeau posé à la main : `state_carries_tile_effects(effects_state, board)`
lit si AU MOINS UNE entité-tuile du board a une entrée dans `EffectsState.by_unit`. Un état hydraté
fait autorité intégralement (il connaît les poses/retraits survenus en cours de bataille) ; un état
non hydraté n'a aucune information de tuile, et c'est là, et là seulement, que le repli reconstruit
la pose du setup. `board=None` ⇒ comportement strictement inchangé.

### 3.1 Le garde-fou qui fonde le repli (et qui corrige une affirmation du dépôt)

Un repli terrain n'est légitime que si **tout** Swamp porte l'effet — sinon il SUR-BLOQUE, ce qui est
pire que la sur-atteinte (le port refuserait une expansion que le natif autorise).

`test_block_entering_tiles_live` affirmait le contraire :

> « les Swamp de `PVP_desert_04` (10 tuiles, elevation 4) ne portent AUCUN `BlockEnteringUnits` … la
> pose est CONDITIONNELLE … c'est exactement ce qui interdit de gater sur le TERRAIN »

**C'est une confusion BC ↔ live.** Le board DÉPLOYÉ par `--board PVP_desert_04` n'a **aucune** tuile
Swamp : son `boardGraph.tileDefId` rend `Unplayable 24 / Grass 21 / Block 14 / DryBush 4`. Les « 10
Swamp » venaient du **dump BC** (`data/boards/**/PVP_desert_04.json`), pas du plateau réel. Le board
reste un excellent contrôle négatif — zéro tuile bloquante, repli inerte — mais il ne dit rien d'une
pose conditionnelle. Le commentaire du test est rectifié, mesure à l'appui.

**Audit sur 13 boards** (`probe_pathfinding_overreach.py --audit`), terrain lu LIVE :

| board | Swamp (live) | tuiles bloquantes | sur-blocage |
|---|---|---|---|
| `MC1_67` | 4 | 4 | 0 |
| `C4_09` | 2 | 2 | 0 |
| `EMC2_02` | 13 | 16 (13 + 3 `Fire`) | 0 |
| `PVP_desert_04` | **0** | 0 | 0 |
| `C2_26` · `C2_19` · `MC1_15` · `MC1_64` · `C3_10` | 6 chacun | 6 chacun | 0 |
| `EC2_10` | 9 | 9 | 0 |
| `LE2_12` · `Infested_SyncPvp_Arctic_01` | 7 chacun | 7 chacun | 0 |
| `C1_02` | 3 | 3 | 0 |

**75 Swamp live, 75 porteuses, 0 exception.**

---

## 4. Le second trou, trouvé en CRAFTANT le cas discriminant : ce n'est pas que `BlockEnteringUnits`

Le board neuf `EMC2_02` (13 Swamp, seed 4242) a montré **6 tuiles en trop qui subsistaient même en
régime hydraté** — donc étrangères au canal, et préexistantes. Leurs parents portaient tous `Fire`.

Retour au décompilé : **`GetTileBlockingReasons` ne teste aucun EffectType.** Il énumère le registre
de blocage du `MovementComponent` de la tuile, qu'alimente le corps commun
`IdunBattle.Entities.Effects.BlockTileMovementEffect$$ApplyInternal` :

```csharp
int blockerId = owner.IsUnit() ? owner.GetComponent<OwnerComponent>().CurrentPlayerEntityId : 0;
tile.GetComponent<MovementComponent>().blockers.Add(effect.Id, new {
    blockerId, effect.Id, tileBlockingType = this@+0x480, exemptTraits = this@+0x488 });
```

et que `GetTileBlockingReasons` relit ainsi : `blockerId == 0` → **bit 0x1** (blocage neutre) ; sinon
`IsEnemy(state[blockerId], unit)` → bit 0x4 ; `tileBlockingType == 1` → bit 0x2 en plus.

Les classes qui s'enregistrent sont **exactement** celles qui appellent
`StaticBattleRules.Effect$$NotBlockingMovementOfTraits` dans leur `.ctor` — six, lues une par une
(l'`EffectType` est le littéral écrit à `+0x10`) :

| EffectType | classe |
|---|---|
| `0x00` | `IdunBattle.Entities.Effects.BlockEnteringUnitsTileEffect$$.ctor` |
| `0x05` | `IdunBattle.Entities.Effects.FireEffect$$.ctor` |
| `0x11` | `IdunBattle.Entities.Effects.IceEffect$$.ctor` |
| `0x3a` | `IdunBattle.Entities.Effects.Idun.DarknessEffect$$.ctor` |
| `0x5e` | `IdunBattle.Entities.Effects.Idun.LandMineBlockTileMovementEffect$$.ctor` |
| paramétré | `IdunBattle.Entities.Effects.BlockTileMovementEffect$$.ctor` — la BASE, **aucun appelant nommé** dans le dump, donc aucun type de plus à lister |

⚠ Ne pas confondre avec `_MOVEMENT_BLOCKING_EFFECT_TYPES` de `static_battle_rules` : celui-là est
l'ensemble des types qui PARTAGENT l'exemption Mounted/Vehicle/Unstoppable — `Darkness` (exempté par
NightVision) et `LandMine` (aucune exemption) en sont absents alors qu'ils bloquent bel et bien.

Le port ne reconnaissait que `0`. Il reconnaît désormais les cinq, avec l'exemption propre à chaque
type (`not_blocking_movement_of_traits(effect_type)`), et le gate de **neutralité** :
`e.source is None or e.source == tile_id` = l'effet est porté par la TUILE (pendant offline de
`blockerId == 0`). Mesuré sur les trois boards : `BlockEnteringUnits`, `Thorns_DefenseReduction` et
les `Fire` de décor ont TOUS `source == <id de leur propre tuile>`.

Cette extension ferme les 6 écarts d'`EMC2_02` **en régime hydraté** (6 → 0).

---

## 5. Chiffres avant / après

Ensemble COMPLET `aiMovableTiles` vs offline, toutes unités encore mobiles, `extra` = `offline \ natif`.
`AVANT` = repli terrain désarmé et EffectType 0 seul (`--mutate terrain-fallback` sur l'arbre d'avant).

| board / seed | régime | AVANT `extra` | APRÈS `extra` | `missing` (avant et après) |
|---|---|---|---|---|
| `MC1_67` / 777 | A (non hydraté) | **3** | **0** | 0 |
| `MC1_67` / 777 | B (hydraté) | 0 | 0 | 0 |
| `C4_09` / 31337 | A | **1** | **0** | 0 |
| `C4_09` / 31337 | B | 0 | 0 | 0 |
| `EMC2_02` / 4242 | A | **15** | **6** (cf. §6) | 0 |
| `EMC2_02` / 4242 | B | **6** | **0** | 0 |

**Aucun `missing` créé nulle part** : le port reste exact sur tout ce qu'il atteignait justement.

Reproduire :

```bash
cd scripts/python
python probe_pathfinding_overreach.py --seed 777   --board MC1_67 --dist
python probe_pathfinding_overreach.py --seed 31337 --board C4_09  --dist
python probe_pathfinding_overreach.py --seed 4242  --board EMC2_02 --dist
python probe_pathfinding_overreach.py --seed 777   --board MC1_67 --mutate terrain-fallback   # AVANT
python probe_pathfinding_overreach.py --audit "MC1_67,C4_09,EMC2_02,PVP_desert_04,C2_26,C2_19,MC1_15,EC2_10,LE2_12,MC1_64,C3_10,Infested_SyncPvp_Arctic_01,C1_02"
python -m pytest tests/engine/entities/pathfinding/test_block_entering_tiles_live.py -q
```

Garde : `test_block_entering_gate_armed_without_tile_channel_live` (`MC1_67` + `C4_09`) charge
l'état **sans** `tiles=`, exige l'égalité exacte avec le natif, et **échoue si le scénario n'est pas
discriminant** — il vérifie d'abord qu'avec `TERRAIN_BLOCK_ENTERING` vide la sur-atteinte réapparaît.

---

## 6. Ce que ce cas ne ferme PAS

* **Régime non hydraté + bloqueur de DÉCOR hors tile-def.** Les trois `Fire` d'`EMC2_02` sont posés
  sur du `Grass` (source = leur propre tuile) : aucun `tileDefId` ne les annonce, et la BC de board
  ne porte pas d'effet (`Tiles[]` = `TileId`/`Elevation`/`Rotation`/`RoomID`/`ForceUnplayable`). Le
  repli ne peut donc reconstruire QUE ce que le tile-def héberge — 6 tuiles restent sur-atteintes sur
  `EMC2_02` en régime A. Fermeture réelle = alimenter `load_state(tiles=tileMeta)` aux call-sites,
  ou un canal statique board→effets initiaux. **Aucun des boards du cas (`MC1_67`, `C4_09`) n'est
  concerné** : leurs bloqueurs sont tous des Swamp.
* **Le bit 0x4 (`blockerId != 0`)** — un bloqueur posé par une UNITÉ ne bloque que les ENNEMIS de son
  poseur. Non porté (il faudrait la team du mover dans `tile_blocks_entering`) : on ne bloque pas,
  donc on sur-atteint au lieu de sur-restreindre, et ça reste mesurable. Aucun cas live rencontré
  (tous les bloqueurs observés ont `source == tuile`).
* **Le bit 0x2 / `WalkPathfinder$$GetEffectiveDepth`** (`Min(1, depth)` quand
  `GetTileBlockingReasons & 2`) : le bit vient de `BlockTileMovementEffect` construit avec
  `tileBlockingType == 1`, dont aucun appelant n'est nommé dans le dump. Toujours non porté (résidu
  #131 d'origine), toujours sans datapoint.
* **Le gate d'ACTIVATION de `FindAnyOrAllMoveableTiles`** (`UnitFlagsComponent.Has(1)` = unité déjà
  activée, `UnitExtensions$$CanMove`) : le natif rend un ensemble VIDE, `_move_tiles` rend l'ensemble
  complet. Étage différent, hors périmètre — le probe le signale et ne le compte pas. En usage IA
  normal la question ne se pose pas (on interroge une unité non encore activée), mais tout harnais qui
  interroge une unité ayant bougé verra l'écart.
* **`AddTeleportationTiles` / `AddShadewalkerTiles`**, les deux autres branches de
  `GetValidNeighbours`, restent non portées (aucun téléporteur sur les boards du cas).
