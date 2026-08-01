"""Selecteurs du domaine TUILE (ids de tuile) -- ils lisent `ctx.board`.

Pont unite -> tuile (`Tiles`, `AdjacentTiles`), dedup et intersection propres au domaine
(`TileUnique`, `TileIntersect`), occupation (`CanAddUnit`) et portee de deplacement
(`MovableTilesInRange`). Tranche 2 du decoupage de `selectors.py` -- cf. `__init__.py`."""
from __future__ import annotations

from dataclasses import replace

import hexgeo

from ... import battle_query          # mirror UNIQUE de GetTilesBehind/IsTileValidForList (#117/#124)
from ...dsl.base import (TargetsSelector, Const, _pos, _within, _is_alive, _units_of, _effect_field,
                         resolve_unit)
from ._shared import _entity_pos, _tile_positions


# --- Selecteurs de TUILES (domaine TILE = ids de tuile ; lisent ctx.board). Pont unit->tile
#     (`AdjacentTiles`) et tile->tile (`CanAddUnit`/`TileUnique`/`TileIntersect`). board None -> []. ---

class Caster(TargetsSelector):
    """L'unite CASTER (`caster@+0x168`, ref passee aux selecteurs). Accesseur unit-domain =
    `ctx.caster` (dict|None)."""
    def select(self, ctx):
        return ctx.caster


class AllUnits(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$AllUnits` -> `AllAliveMachinesSelector IdunBattle.Entities.Selectors.AllAliveMachinesSelector$$Select` : toutes les unites
    VIVANTES de la bataille. Le primitif DSL `AllUnits` est **la variante ALIVE** (un `AllUnitsSelector`
    natif distinct existe pour l'ensemble brut, mais `DSLFactory.AllUnits` ne l'utilise PAS). Source des
    filtres `Enemies`/`Friends` du port (le natif `Enemies(caster, ...)` folde la source ; cote port on
    fournit `AllUnits` a l'inner). **Le filtre alive est ICI** (mirror de AllAliveMachines), PAS via un
    noeud `Damageable` en aval -> cf. confront LIVE #200 tracer-v2 + fix #202 (le natif GetSpawnTileSelector
    n'a AUCUN Damageable ; c'est `AllUnits`=alive qui exclut les morts)."""
    def select(self, ctx):
        return [u for u in ctx.units
                if bool(u.get("alive", True)) and (u.get("hp") or 0) > 0]


class AllTiles(TargetsSelector):
    """`IdunBattle.Entities.Selectors.AllTilesSelector` — le slot PARTAGE `factory+0x78` que
    `IdunBattleLogic.Entities.DSLFactory$$InitializeShared` alloue (`AllTilesSelector..ctor(uVar2, ctx,
    0, 0)` -> `*(factory + 0x78) = uVar2`) : TOUTES les tuiles du plateau, en domaine ID.

    C'est la source des selecteurs board-wide de TUILES ; unique consommateur porte :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomboltAbility$$NrOfHitsFormula`
    (`Count(EntitiesWithAnyEffect(AllTiles@0x78, Fire=5, sourceFlag=6))` = « +1 coup par hex EN FEU »).

    Ordre = celui de `board.by_id` (ordre d'insertion du dump) ; le seul consommateur en prend le
    CARDINAL, donc l'ordre n'est pas observable. board None -> []."""
    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        return list(board.by_id.keys())


class Children(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Children` = `Entities.Selectors.AllAliveMachinesSelector` (IdunBattle.Entities.Selectors.AllAliveMachinesSelector$$.ctor) SCOPÉ
    aux enfants (summons) produits par CE cast (natif `factory+0x148`). Port = l'accumulateur `ctx.children`
    (alimenté par la feuille `SpawnUnit`, `runner/abilities/behaviours.py`). ⚠ Le filtre `AllAlive` est un
    no-op offline pour l'on-appearance de CE cast (les summons survivent à leur apparition). cf.
    `getemruntz_taunt_tree` (loki.py)."""
    def select(self, ctx):
        return list(getattr(ctx, "children", None) or [])


class Parent(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Parent(source, mode)` -> `IdunBattle.Entities.Selectors.ParentSelector$$Select` :
    pour CHAQUE entite du selecteur source, `IdunBattle.Entities.UnitExtensions$$GetParent(u, ..., mode)` ;
    les parents non nuls sont accumules dans un `OrderedSet` (donc DEDUPLIQUES, ordre d'apparition).

    ⚠ La RECURSION vers la racine est conditionnee au 3e argument `root` de `GetParent` (le champ
    `+0x20` que `ParentSelector$$.ctor` recopie du `mode`) : sans lui le natif rend le parent
    DIRECT, ce que porte ce selecteur.

    Port : le lien enfant -> parent vit sur le dict d'unite (`parentId` = `ChildComponent.ParentId`,
    alimente par `UnitComponent.parent_id` que `SpawnUnitOperation` pose au spawn = le
    `Unit_Parent_Id` natif, ou que `snapshot._load_unit_parent` seede depuis
    `combatSnapshot.units[].parentId` sur un etat hydrate, #378). Le parent est
    RESOLU dans `ctx.units` (meme domaine que tous les selecteurs d'unite) ; un parent absent du
    contexte (ou `parentId` None) ne produit rien -> selecteur VIDE, mirror du `if (parent != null)`.

    Call-sites portes : `IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect$$CreateTargetSelector`
    (`Parent(Self@0x148)` = le summoner que l'effet buffe) et
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SwornProtector_ProtectAbility$$CreateBehaviour`
    (`SwitchPosition(Self, Parent(Self))`)."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        out: list = []
        seen: set = set()
        for u in _units_of(self.source, ctx):
            pid = u.get("parentId") if isinstance(u, dict) else None
            if pid is None or pid in seen:
                continue
            for cand in ctx.units:
                if cand.get("id") == pid:
                    seen.add(pid)
                    out.append(cand)
                    break
        return out


class LastUnitAttackedBy(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$LastUnitAttackedBy` = `Entities.Selectors.LastUnitAttackedBySelector`
    (IdunBattle.Entities.Selectors.LastUnitAttackedBySelector$$Select) : dernière unité attaquée par `unit`. Port : le dict FRAIS (état POST-attaque, relu par la
    feuille `PerformAIAttack`) de la cible frappée → champ `_last_attacked` de l'unité (None si aucune). Ce
    dict porte `alive`/`hp` COURANTS → `IsAlive(LastUnitAttackedBy(child))` lit l'état vivant APRÈS l'attaque."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def select(self, ctx):
        u = resolve_unit(self.unit, ctx)
        return (u or {}).get("_last_attacked")


class AdjacentTiles(TargetsSelector):
    """`DSLFactory.AdjacentTiles(source)` : UNION (BRUTE, avec doublons possibles entre unites -> le
    natif fait suivre d'un `Unique`) des tuiles hex-adjacentes aux unites de `source`, via le
    voisinage NATIF `ctx.board.neighbours(tile_de_l_unite)`. `source` = TargetsSelector d'ENTITES : le
    natif prend la MainTile de chaque entite -- pour une entite-UNITE c'est sa tuile, pour une
    entite-TUILE c'est ELLE-MEME. Le port accepte donc les DEUX domaines (`_tile_positions`), ce
    qu'exige un cast TILE-TARGET (`PlagueburstMortarAbility$$ExecuteBehaviour` :
    `AdjacentTiles(target@0x178)` ou `target@0x178` EST la tuile ciblee ; les call-sites unit-domain
    historiques passent par le meme chemin, resultat inchange). Retour list[int]. board None -> [].

    ORDRE (R28-1) : `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` accumule dans un
    `OrderedSet` (ordre d'INSERTION) ce que rend `BattleQuery$$GetAdjacentTiles` = la liste
    d'adjacence STOCKEE sur la tuile -> `Board.neighbours_native` (champ brut `boardGraph.neighbours`),
    et **pas** `board.neighbours()` qui trie les ids et symetrise. Observable des qu'un
    `PickRandomly`/`First`/tri stable consomme le resultat (== `_free_tiles_adjacent(native_order=True)`,
    valide live par fc23f1e). 2e consommateur confronte live : le splash de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.FragBombAbility$$ExecuteBehaviour`, itere par un
    `SortedAttackSeries` SANS `OrderBy` -> l'ordre fixe la sequence de tirages de degat."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        out: list = []
        for p in _tile_positions(self.source, ctx, board):
            tid = board.id_at(p[0], p[1])
            if tid is None:
                continue
            out.extend(board.neighbours_native(tid))
        return out


class TileUnique(TargetsSelector):
    """`DSLFactory.Unique(source)` sur le domaine TILE (LINQ Distinct sur ids de tuile, 1re
    apparition preservee). Homologue tile de `Unique` (qui dedup par id d'ENTITE, KO sur des ints)."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        seen, out = set(), []
        for t in self.source.evaluate(ctx):
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out


class CanAddUnit(TargetsSelector):
    """`DSLFactory.CanAddUnit(tiles)` : garde les tuiles ou une unite PEUT etre ajoutee = `walkable`
    ET LIBRE (aucun occupant VIVANT). Occupation = tuiles des `ctx.units` vivants (mirror du
    `_occupied_tiles(state)` imperatif). Ordre de `source` preserve. board None -> [].

    OCCUPATION PAR PIED (#91) : le natif `IdunBattle.Entities.TileExtensions$$CanAddUnit` lit le
    `TileContentComponent` de la tuile -- une tuile sous N'IMPORTE QUEL pied est occupee (#R30 §1).
    On lit donc l'EMPREINTE (`unit["feet"]`, mirror `EntityExtensions$$GetTiles`), pas la seule
    `PositionComponent`. Strictement equivalent pour une unite mono-tuile (`feet == [pos]`) ; sans
    ca, un Galatian pose au sol par `DutyEternal` ne bloquait que sa MAIN TILE et le port acceptait
    de spawner sur ses deux autres pieds."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        occ = set()
        for u in ctx.units:
            if not _is_alive(u):
                continue
            feet = (u or {}).get("feet")
            if not feet:                                  # unite hors plateau / dict sans empreinte
                p = _pos(u)
                feet = [] if p is None else [p]
            for f in feet:
                t = board.id_at(f[0], f[1])
                if t is not None:
                    occ.add(t)
        return [t for t in self.source.evaluate(ctx) if t not in occ and board.walkable(t)]


class TileIntersect(TargetsSelector):
    """Intersection de deux ensembles de TUILES (ids) — `op_BitwiseAnd` du domaine tile
    (`CombinedSelector`). Garde les tuiles de `left` presentes dans `right` (ordre de `left`,
    dedup). Homologue tile de `And` (intersection par id d'entite)."""
    def __init__(self, left: TargetsSelector, right: TargetsSelector):
        self.left, self.right = left, right

    def select(self, ctx):
        rs = set(self.right.evaluate(ctx))
        seen, out = set(), []
        for t in self.left.evaluate(ctx):
            if t in rs and t not in seen:
                seen.add(t)
                out.append(t)
        return out


def _movement_can_continue(ctx, board, mover_traits):
    """Gate d'EXPANSION `IdunBattle.Entities.Pathfinding.BasePathfinder$$NodesInNextLevel` ->
    `WalkPathfinder$$IsValidContinuePathTile` (#131), monte sur le SUBSTRAT DSL.

        if (currentTile != startTile && !IsValidContinuePathTile(this, unit, currentTile))
            return <liste vide>;          // aucun voisin -> la tuile est un CUL-DE-SAC

    Le prédicat lui-meme est `GetTileBlockingReasons(tile, unit) == 0` ; son bit `0x1` vient d'un
    effet de tuile BLOQUEUR NEUTRE (`BlockEnteringUnitsTileEffect` et ses cinq freres, cf.
    `pathfinding/tile_blocking.TILE_MOVEMENT_BLOCKING_EFFECT_TYPES`) dont l'unite n'est pas exemptee
    (`StaticBattleRules.Effect$$NotBlockingMovementOfTraits`).

    DEUX sources, en UNION, evaluees PAR TUILE et memoisees (le BFS n'interroge que les tuiles qu'il
    atteint — balayer le board entier a chaque evaluation de selecteur serait un cout inutile) :

      1. le canal DYNAMIQUE `ctx.tile_has_effect(tileId, effectType)` — le meme accesseur que le
         noeud `HasEffect` en domaine tuile ;
      2. le repli TERRAIN `tile_blocking.terrain_blocks_entering` (le tile-def `Swamp` heberge
         `ThornsBlockMovementAbility`, qui pose l'effet AU SETUP), indispensable parce que la
         plupart des contextes DSL sont montes SANS le canal opt-in des effets de tuile — sans lui
         le gate serait INERTE en silence, exactement le residu ferme par case-224 §4.

    ⚠ Ce que ce substrat ne sait PAS distinguer, et que `tile_blocking.tile_blocks_entering` sait,
    lui, sur un `EffectsState` : la NEUTRALITE du bloqueur (`blockerId == 0`, cote port
    `e.source == tile_id`). `ctx.tile_has_effect` n'expose pas la source -> un bloqueur pose par une
    UNITE (bit `0x4`, qui ne bloque que ses ennemis) compterait ici comme neutre. Aucun poseur de ce
    genre n'existe dans les effets listes ; degradation RESTRICTIVE et nommee, a rouvrir si un
    `BlockTileMovementEffect` unit-owned apparait.

    Rend `None` quand aucun canal n'est disponible (pas de board) — soit « aucun gate », le
    comportement d'avant #131."""
    from ...services.static_battle_rules import not_blocking_movement_of_traits
    from ..pathfinding.tile_blocking import (TILE_MOVEMENT_BLOCKING_EFFECT_TYPES,
                                             terrain_blocks_entering)
    from ..traits.unit_trait import has_any_trait
    if board is None:
        return None
    tile_has_effect = getattr(ctx, "tile_has_effect", None)
    # Types de bloqueur dont CE mover n'est PAS exempte (`Any(exemptTraits, t => HasTrait(unit, t))`).
    types = tuple(et for et in sorted(TILE_MOVEMENT_BLOCKING_EFFECT_TYPES)
                  if not has_any_trait(mover_traits, not_blocking_movement_of_traits(et)))
    cache: dict = {}

    def _blocks(tid: int) -> bool:
        tid = int(tid)
        hit = cache.get(tid)
        if hit is None:
            hit = bool(tile_has_effect is not None
                       and any(tile_has_effect(tid, int(et)) for et in types))
            if not hit:
                hit = terrain_blocks_entering(board, tid, mover_traits)
            cache[tid] = hit
        return hit

    return lambda tid: not _blocks(tid)


class MovableTilesInRange(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$MovableTilesInRange(unitSelector, unitTileSelector,
    overrideRange, ignoreFlags, ignoreUnitsOnTiles)` -> `IdunBattle.Entities.Selectors.
    MovableTilesInRangeSelector$$Select`. CINQ arguments, pas quatre — le `.ctor` les range en
    `+0x20 unitSelector`, `+0x28 unitTileSelector`, `+0x30 overrideRange`, `+0x38 ignoreFlags`,
    `+0x39 ignoreUnitsOnTiles`.

    LA CHAINE NATIVE COMPLETE (#381-r1), lue de bout en bout
    ------------------------------------------------------
    `Select` resout `entity` (slot 7 du `unitSelector`), `fromTile` (`GetMainTile(entity)`, remplace
    par `SelectTile` du `unitTileSelector` s'il existe), `overrideRange` (`Nullable<int>`) puis
    appelle **`IdunBattle.Core.Services.BattleQuery$$GetMovableTilesFor(entity, fromTile,
    ignoreFlags, options)`** — `options` etant une struct dont le port lit trois champs :
    `+0x00 pathfinderTypeOverride` (0), `+0x01 = ignoreUnitsOnTiles` (le champ `+0x39` du noeud),
    `+0x04 = overrideRange`. De la :

        BattleQuery$$GetMovableTilesFor  ->  MovementQuery$$GetMovableTilesFor(unit, [fromTile],
                                                                              ignoreFlags, options)
          -> MovementQuery$$FindAnyOrAllMoveableTiles :
                 if ((UnitFlagsComponent$$Has(unitFlags, 1) && ignoreFlags == 0)
                     || !UnitExtensions$$CanMove(unit))            return;   // set VIDE
                 type  = GetPathfinderTypeForUnit(unit, options.pathfinderTypeOverride)
                 range = options.overrideRange ?? StatComponent(Movement).CurrentValue
                 bonus = options.rangeBonusesOverride ?? GetRangeBonusForUnit(unit, ...)
          -> MovementQuery$$AnyOrFillMoveableTiles(tiles, type, unit, range, bonus,
                                                   ignoreUnitsOnTiles, out) :
                 range = MovementRangeWithAppliedBonus(unit, range, bonus)
                 foreach (start in tiles) {
                     r = GetReachableTiles(start, type, range, unit)          // le PATHFINDING
                     r.RemoveAll(t => !IsMovableTile(this, unit, t, ignoreUnitsOnTiles))
                     result.AddRange(r) }

    Les TROIS `RemoveAll` de `AnyOrFillMoveableTiles` partagent le MEME corps
    (`MovementQuery.<>c__DisplayClass11_0$$<AnyOrFillMoveableTiles>b__2`, dedupliqué) :

        IsMovableTile(unit, tile, ignoreUnitsOnTiles) =
              (!IsTileReserved(tile) || IsTileReservedForUnit(tile, unit))
           && !IsTilePendingDrafting(tile, state, null)
           && IsFreeTile(tile, state, allowSteppable: 1, allowTemporaryTile: 0,
                         allowAnyUnit: ignoreUnitsOnTiles)
           && !IsTemporary(tile)

    ⇒ **le pool rendu par ce noeud est TOUJOURS filtre par l'occupation** (sauf
    `ignoreUnitsOnTiles`), et la tuile de DEPART en sort avec les autres (elle porte l'unite).
    C'est exactement le `stop_set` du BFS porte.

    `ignore_flags` N'EST PAS `canReachOnly` — c'est le bug ferme ici (`#381-r1`)
    -------------------------------------------------------------------------
    Le port lisait le 4e argument comme un `canReachOnly` qui aurait choisi entre `visited` et
    `stop_set`. **Cet axe n'existe pas dans le natif** : le 4e argument est `ignoreFlags`, qui ne
    touche QUE la garde d'entree de `FindAnyOrAllMoveableTiles` (elle rend un set VIDE, pas un set
    plus large), et le 5e — le seul qui elargisse l'ensemble — vaut `0` sur les CINQ call-sites lus
    (`RammingSpeedAbility$$GetTileToMoveTo`, `VigilanceEternalAbility$$GetPossibleMovementTiles`,
    `HeroicFusilladeAbility$$ExecuteBehaviour`, `DSLSelectors$$TilesUnitCanMoveToChargeTarget` —
    qui force `ignoreUnitsOnTiles = 0` en dur — et `VigilanceEternalAbility$$
    GetPossibleAdditionalTargetTilesForDangerZone`).
    Consequence mesuree : sur les call-sites `ignoreFlags = 0` (Waaagh, RammingSpeed, BlackRage) le
    port rendait le `visited` — un DISQUE incluant les tuiles occupees et la tuile de depart — la
    ou le natif rend le `stop_set`.

    Le PATHFINDING est le meme foyer que partout ailleurs
    ----------------------------------------------------
    `GetReachableTiles` -> `Pathfinders$$FindReachableTiles(type, start, depth, unit)` ->
    `BasePathfinder$$FindReachableTiles` = `ListPool(IterateReachableTiles(start, depth, unit))`,
    qui delegue a `BasePathfinder$$GetMovablePositions` (le BFS par niveaux porte dans
    `entities/pathfinding/walk_pathfinder.py`). Ce noeud est donc la FEUILLE DSL qui appelle le
    pathfinder, comme `CanAddUnit` est la feuille qui appelle les predicats de board — et il doit
    l'appeler avec LES MEMES trois etages que `ai/state_bridge._move_tiles`, le mirror deja
    confronte d'`aiMovableTiles` (qui est litteralement `MovementQuery$$GetMovableTilesFor`) :

      1. **le TYPE de pathfinder** (`GetPathfinderTypeForUnit`) — DEUX axes, pas un : un volant
         (`UnitExtensions$$IsLikeFlying`) traverse tout et ignore l'elevation, ET quatre effets
         « je descends du ciel » detournent vers un `ATeleportPathfinder` au pool board-wide
         (`#381-r5`). Le dispatch entier vit dans `pathfinding.pathfinders` ;
      2. **le gate d'EXPANSION #131** (`BasePathfinder$$NodesInNextLevel` ->
         `IsValidContinuePathTile`) — une tuile block-entering (Swamp/Fire/Ice/...) reste un STOP
         legal mais devient un CUL-DE-SAC. Sans lui le port SUR-ATTEINT (mesure #131 : 6/17/27
         contre 6/16/25 au natif) ;
      3. **l'occupation par EMPREINTE** (`GetTileContent` lit le contenu de la tuile, peuple par
         TOUS les pieds) — meme lecture que `CanAddUnit` (#91), pas la seule main tile.

    RESIDUS NOMMES (degradation PERMISSIVE dans les trois cas — le port sur-atteint, jamais
    l'inverse, donc l'ecart reste mesurable) :
      * la garde d'entree `UnitFlagsComponent$$Has(unitFlags, 1) && ignoreFlags == 0` (#381) et
        `UnitExtensions$$CanMove` : `unitFlags` n'a pas de substrat cote port -> jamais de set vide
        par cette voie. C'est pour ca que `ignore_flags` est STOCKE mais ne change rien ici ;
      * `IsTileReserved` / `IsTilePendingDrafting` / `IsTemporary` : aucun canal offline ;
      * le trait `Steppable` (0x1b) de `IsFreeTile(allowSteppable: 1)` : une tuile sous un Steppable
        reste un arret legal cote natif. Non porte — meme residu, et surtout meme CONVENTION, que
        `CanAddUnit` : les deux noeuds s'intersectent, un ecart entre eux serait pire que l'ecart
        commun au natif ;
      * `MovementQuery$$GetRangeBonusForUnit` / `MovementRangeWithAppliedBonus` : tous les
        call-sites portes passent un `overrideRange` explicite, et la boucle de bonus est un no-op
        sur une liste vide. Le volet `HasTriggeredAbility(0x4b8) || HasTrait(0x418) -> range 0`
        n'est pas porte ici (`GetMovablePositionsFor` le porte deja pour la face empreinte).

    ORDRE : `sorted(...)` (id de tuile croissant) la ou le natif rend l'ordre de visite du BFS.
    Residu herite de `#353-r1`, INCHANGE par ce correctif (il ne departage que des utilites
    STRICTEMENT egales, cf. `ramming_speed_charge_tiles_selector`). `board` absent -> []."""
    def __init__(self, unit: TargetsSelector, from_tile: TargetsSelector,
                 range_amount, ignore_flags: bool = False,
                 ignore_units_on_tiles: bool = False):
        self.unit, self.from_tile = unit, from_tile
        self.range_amount = range_amount
        self.ignore_flags = bool(ignore_flags)
        self.ignore_units_on_tiles = bool(ignore_units_on_tiles)

    def select(self, ctx):
        from ..pathfinding.pathfinders import movable_positions_for_unit
        from ..traits.unit_trait import unit_trait_names
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        u = resolve_unit(self.unit, ctx)
        if u is None:
            return []
        start_pos = None
        for p in _tile_positions(self.from_tile, ctx, board):
            start_pos = p
            break
        if start_pos is None:
            start_pos = _pos(u)
        start = board.id_at(start_pos[0], start_pos[1]) if start_pos is not None else None
        if start is None:
            return []
        # `WalkPathfinder$$UnitIsBlockedByEnemyUnit` lit `TileExtensions$$GetTileContent`, que TOUS
        # les pieds d'une unite peuplent -> occupation par EMPREINTE (#91, meme lecture que
        # `CanAddUnit`), pas par la seule main tile.
        occ: dict = {}
        for other in ctx.units:
            if not _is_alive(other):
                continue
            feet = (other or {}).get("feet")
            if not feet:
                p = _pos(other)
                feet = [] if p is None else [p]
            for f in feet:
                t = board.id_at(f[0], f[1])
                if t is not None:
                    occ[t] = other.get("team")
        traits = unit_trait_names(u.get("visualId"))
        # `MovementQuery$$GetPathfinderTypeForUnit` -- le dispatch COMPLET (IsLikeFlying **et** la
        # branche MOUVEMENT SPECIAL de `#381-r5`), au FOYER partage par les trois consommateurs.
        # `ctx.has_effect(unit, effectType)` est le canal d'effets du DSL (defaut None -> pas de
        # canal -> Walk/Fly, comportement anterieur).
        he = getattr(ctx, "has_effect", None)
        visited, stop = movable_positions_for_unit(
            board, start, int(self.range_amount.evaluate(ctx)), occ, u.get("team"),
            traits=traits, has_effect=(None if he is None else (lambda et: bool(he(u, int(et))))),
            can_continue=_movement_can_continue(ctx, board, traits),
            # `TitanhammerSquadPathfinder$$IsValidTeleportTile` exige de savoir QUI a pose
            # `TitanhammerSquad_TargetTile` sur la tuile ; `ctx.tile_has_effect` n'expose pas la
            # source -> NON MESURE (`None`), pool de teleport Titanhammer vide. Residu NOMME et
            # RESTRICTIF ; inventer « n'importe quel poseur » serait plus faux.
            teleport_target_tiles=None)
        # `RemoveAll(t => !IsMovableTile(..., ignoreUnitsOnTiles))` : sans `ignoreUnitsOnTiles` le
        # natif ne garde que les tuiles LIBRES (`IsFreeTile`), depart compris — c'est le stop_set.
        return sorted(visited if self.ignore_units_on_tiles else stop)


def tiles_unit_can_move_to_charge_target(unit: TargetsSelector, from_tile: TargetsSelector,
                                         target: TargetsSelector, range_amount,
                                         ignore_flags: bool = False) -> TargetsSelector:
    """`IdunBattleLogic.Entities.DSLSelectors$$TilesUnitCanMoveToChargeTarget(caster, casterTiles,
    target, movementRange, ignoreFlags)` — MIRROR du decompile, qui n'assemble QUE deux noeuds :

        CanAddUnit(AdjacentTiles(target))  op_BitwiseAnd  MovableTilesInRange(caster, casterTiles,
                                                                              movementRange,
                                                                              ignoreFlags,
                                                                              ignoreUnitsOnTiles = 0)

    = « tuiles LIBRES et marchables hex-adjacentes a la cible, que l'unite peut atteindre en <=
    `range` pas ». `op_BitwiseAnd` du domaine TILE = `TileIntersect` (ordre de l'operande GAUCHE
    preserve). Helper de FACTORY (comme `get_spawn_tile_selector`), pas une classe native.

    ⚠ `ignoreUnitsOnTiles` est ecrit **EN DUR a 0** par ce helper natif (le 8e argument du
    `MovableTilesInRangeSelector$$.ctor` y est un octet nul) : seul `ignoreFlags` remonte a
    l'appelant. `WaaaghAbility$$GetPossibleMovementTiles` et `BlackRage_MoveAbility` passent `0`,
    `VigilanceEternalAbility$$GetPossibleMovementTiles` passe `1` — et ce booleen ne change PAS
    l'ensemble rendu (il desarme la garde d'entree de `FindAnyOrAllMoveableTiles`, cf.
    `MovableTilesInRange`)."""
    return TileIntersect(CanAddUnit(AdjacentTiles(target)),
                         MovableTilesInRange(unit, from_tile, range_amount,
                                             ignore_flags=ignore_flags,
                                             ignore_units_on_tiles=False))
