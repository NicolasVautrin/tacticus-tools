"""Selecteurs du domaine TUILE (ids de tuile) -- ils lisent `ctx.board`.

Pont unite -> tuile (`Tiles`, `AdjacentTiles`), dedup et intersection propres au domaine
(`TileUnique`, `TileIntersect`), occupation (`CanAddUnit`) et portee de deplacement
(`MovableTilesInRange`). Tranche 2 du decoupage de `selectors.py` -- cf. `__init__.py`."""
from __future__ import annotations

from dataclasses import replace

import hexgeo

from ... import battle_query          # mirror UNIQUE de GetTilesBehind/IsTileValidForList (#117/#124)
from ...dsl.base import (TargetsSelector, Const, _pos, _feet, _within, _is_alive, _units_of,
                         _effect_field, resolve_unit, _select_tile, _occupants_by_tile)
from ._shared import _entity_pos, _tile_positions
from ...utilities.utility_type import UtilityType   # #270-r1-r1-r3
from ...services.static_battle_rules import not_blocking_movement_of_traits
from ..effect_type import EffectType
from ..pathfinding.pathfinders import movable_positions_for_unit
from ..pathfinding.tile_blocking import (TILE_MOVEMENT_BLOCKING_EFFECT_TYPES,
                                             terrain_blocks_entering)
from ..traits.unit_trait import has_any_trait
from ..traits.unit_trait import unit_trait_names
from ..traits.unit_trait import UnitTrait          # `Steppable` (0x1b) de la branche allowSteppable


def _tile_items(node: TargetsSelector, ctx) -> list:
    """Normalise l'evaluation d'un operande TILE-DOMAINE en liste : `None` -> `[]`, une ENTITE SEULE
    (id de tuile `int`, dict d'unite) -> `[elle]`, un ensemble -> tel quel.

    Pendant tile-domaine de `_units_of` (`dsl/base.py`), et pour la MEME raison : le natif
    `IdunBattle.DSL.TargetsSelector$$op_Addition` / `$$op_Subtraction` accepte un operande MONO-ENTITE
    -- lecture deja ecrite sur `Sub` (`selectors/units.py`). `_units_of`, lui, fait `list(v)` sur un
    `int` et leve `TypeError` : il ne couvre pas ce domaine."""
    v = node.evaluate(ctx)
    if v is None:
        return []
    if isinstance(v, dict):
        return [v]
    if isinstance(v, bool):                            # un bool EST un int -- jamais une entite
        return []
    if isinstance(v, int):
        return [v]
    return list(v)


# --- Selecteurs de TUILES (domaine TILE = ids de tuile ; lisent ctx.board). Pont unit->tile
#     (`AdjacentTiles`) et tile->tile (`CanAddUnit`/`TileUnique`/`TileIntersect`). board None -> []. ---

class Caster(TargetsSelector):
    """L'unite CASTER (`caster@+0x168`, ref passee aux selecteurs). Accesseur unit-domain =
    `ctx.caster` (dict|None)."""
    def select(self, ctx):
        return ctx.caster


class AllAliveUnits(TargetsSelector):
    """Le champ PARTAGE `<DSLSelectors>+0x20` que pose `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared`
    -> `IdunBattle.Entities.Selectors.AllAliveUnitsSelector$$Select` -> `IBattleQuery` slot **137**
    `GetAllAliveUnits` -> `IdunBattle.Core.Services.BattleQuery$$GetAllAliveUnits` :
    `state.GetPool(EntityPool.AliveUnits)`. Unites **VIVANTES** de la bataille.

    C'EST LA SOURCE DE TOUS LES `Enemies`/`Friends` DU PORT, et c'est LU, pas suppose : les call-sites
    natifs ecrivent litteralement `Enemies(<dsl>+0x48 = Caster, <dsl>+0x20, 3)` --
    `TwinSmartMissileSystemAbility$$GetAttackTargets`, `GetEmRuntzAbility$$GetSpawnTileSelector`,
    `RadBombardmentAbility$$AffectedTileAmount`, `WaaaghAbility$$GetBuffedUnitsSelector`,
    `StormcallerAbility$$ExecuteBehaviour` (avec `<dsl>+0x30 = Owner` en reference).

    **Le filtre alive est ICI**, PAS via un noeud `Damageable` en aval -> confront LIVE #200 tracer-v2
    + fix #202 (`GetSpawnTileSelector` n'a AUCUN `Damageable`, et pourtant les morts en sont exclus).

    ⚠ **CE N'EST PAS `AllUnits`** (#514). Le noeud portait ce nom jusqu'au 2026-08-07 alors que
    `IdunBattleLogic.Entities.DSLSelectors$$AllUnits` designe une AUTRE primitive, sur un AUTRE pool
    (`EntityPool.AllUnits`, morts INCLUS) -- cf. la classe `AllUnits` ci-dessous. Les deux corps natifs
    ne different QUE par le littéral d'`EntityPool`, ce qui rend la confusion muette."""
    def select(self, ctx):
        return [u for u in ctx.units
                if bool(u.get("alive", True)) and (u.get("hp") or 0) > 0]


class AllUnits(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$AllUnits` -> `IdunBattle.Entities.Selectors.AllUnitsSelector$$Select`
    -> `IBattleQuery` slot **136** `GetAllUnits` -> `IdunBattle.Core.Services.BattleQuery$$GetAllUnits` :
    `state.GetPool(EntityPool.AllUnits)`, **MORTS INCLUS**.

    Le corps natif est le MEME que celui de `GetAllAliveUnits` / `GetAllAliveMachines` a l'ordinal
    d'`EntityPool` pres (`8` / `0` / `6`, lus dans `data/symbols/<build>/frida/enums.tsv`) : il n'y a
    **aucun** predicat de vie dedans. Le seul filtre du corps est le `playerEntityId` **nullable**, que
    tous les call-sites du DSL passent a `null`. Contraste : `BattleQuery$$GetAllDeadUnits` (slot 139)
    lit le pool `1 = DefeatedUnits` PUIS applique `IdunBattle.Entities.UnitExtensions$$IsDead` -- c'est
    la seule des quatre a porter un predicat.

    Cette primitive est RARE et se DECLARE : les seuls consommateurs legitimes sont les call-sites
    natifs qui appellent `DSLSelectors$$AllUnits` (24 releves sur le build `rnca9r7q6c`), typiquement
    ceux dont le predicat porte sur les MORTS -- `LeadingTheChargeAbility$$GetExtraPierceRatio`
    (`HasBeenDefeated`), `SabreOfSacrificeAbility$$GetNumDefeatedFriendlyUnits`,
    `WaaaghAbility$$GetAttackBehaviour` (`KillDeadUnits`). Partout ailleurs le natif passe le champ
    partage `+0x20` -> `AllAliveUnits` ci-dessus. Le cliquet
    `probe_514_allunits_rayon_de_souffle.py` (etape 3) refuse tout site non declare."""
    def select(self, ctx):
        return list(ctx.units)


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


class ChildrenOf(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$Children(parent)` -- le MIROIR INVERSE de `Parent`
    ci-dessus : pour un selecteur d'entites `parent`, rend les unites dont il est le parent.

    ⚠ **CE N'EST PAS `Children` (`tiles.py`, plus haut dans ce module), ET LES CONFONDRE EST UNE
    FAUTE SILENCIEUSE.** Deux primitives natives HOMONYMES coexistent :
      * `IdunBattleLogic.Entities.DSLFactory$$Children` -- SANS argument, `factory+0x148`, =
        l'accumulateur des summons produits par CE cast. C'est la classe `Children` ci-dessus,
        alimentee par la feuille `SpawnUnit` (`ctx.children`).
      * `IdunBattleLogic.Entities.DSLSelectors$$Children(this, parent)` -- AVEC un argument, qui
        alloue un selecteur scope sur le `parent` passe (`.ctor(state, parent, 0)`, mislabele
        `System.Data.NameNode$$.ctor` par ghidra -- structure lue, jamais le nom). CELLE-CI.
    Un cast qui ne spawne rien a `ctx.children` VIDE : brancher la premiere la ou le natif appelle
    la seconde rend un selecteur toujours vide, sans erreur -- exactement le no-op invisible que ce
    port est cense fermer. Unique consommateur porte a ce jour :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.AttemptedPossessionAbility$$ExecuteBehaviour`
    (`Children(Target)` = les summons de la CIBLE, pas ceux du caster). (#590)

    Port : meme substrat que `Parent` -- le lien `parentId` du dict d'unite
    (`UnitComponent.parent_id` = le `Unit_Parent_Id` natif, pose au spawn par
    `SpawnUnitOperation` ou seede par `snapshot._load_unit_parent` depuis
    `combatSnapshot.units[].parentId`). Le natif accumule dans un `OrderedSet` (dedupliques, ordre
    d'apparition) ; ici l'ordre est celui de `ctx.units`, et une unite ne peut avoir qu'UN parent,
    donc aucun doublon n'est possible.

    ⚠ **AUCUN filtre `alive` ici** : `DSLSelectors$$Children` rend TOUTES les entites enfants. Le
    call-site 1101 compose explicitement `Alive(Children(Target))` -- c'est l'arbre qui filtre, pas
    le selecteur, et le port garde cette separation."""
    def __init__(self, parent: TargetsSelector):
        self.parent = parent

    def select(self, ctx):
        pids = {u.get("id") for u in _units_of(self.parent, ctx)
                if isinstance(u, dict) and u.get("id") is not None}
        if not pids:
            return []
        return [c for c in ctx.units
                if isinstance(c, dict) and c.get("parentId") in pids]


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


class PendingMovingTile(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$PendingMovingTile(unit)` ->
    `IdunBattle.Entities.Selectors.PendingMovingTileSelector$$Select` (#963).

    Le corps natif, LU :

        var pending = <unit>.SelectFirst(entities)?.<+0xa8 Nullable<UnitPositionId>>;
        if (pending.HasValue)
            return UnitPositionIdExtensions.ToTileList(pending.Value, this.<+0x10 state>);
        return new List<IEntity>();                       // Nullable VIDE -> liste vide

    C'est la tuile vers laquelle l'unite est **EN COURS** de se deplacer : le champ `+0xa8` n'est
    renseigne que pendant qu'un `MoveUnitOperation` est en vol (la reservation de destination), et
    il est VIDE le reste du temps.

    ⚠ CE SELECTEUR REND TOUJOURS `[]` COTE PORT, ET C'EST FIDELE, pas une degradation : le
    deplacement y est ATOMIQUE (`MoveUnitOperation` ecrit la `PositionComponent` et rend la main),
    il n'existe aucun etat « position reservee, pas encore atteinte ». Il est porte quand meme pour
    que la structure des arbres qui l'utilisent reste LISIBLE -- le call-site
    `IdunBattleLogic.Entities.Abilities.Active.Loki.GeminaeSuperiaAbility$$GetPossibleSpawnTiles`
    ecrit `AdjacentTiles(Owner) op_Subtraction PendingMovingTile(Owner)`, et effacer la
    soustraction ferait disparaitre un terme du natif au lieu de le documenter comme inerte.
    Il redeviendra actif le jour ou le port modelisera la reservation de destination."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def select(self, ctx):
        return []               # `Nullable<UnitPositionId>` toujours VIDE cote port (cf. docstring)


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
    `SortedAttackSeries` SANS `OrderBy` -> l'ordre fixe la sequence de tirages de degat.

    EXCLUSION DE L'ORIGINE (#459) -- `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select`,
    VERBATIM :

        result = new OrderedSet<TileEntity>();
        tiles  = this.source.SelectTiles(entities);        // vslot 0xa -- l'EMPREINTE de l'origine
        foreach (t in tiles)
            foreach (a in battleQuery.GetAdjacentTiles(t, false, true, true))
                if (!tiles.Contains(a)) result.Add(a);
        return result;

    Le `Contains` porte sur ce que rend `SelectTiles`, c'est-a-dire l'EMPREINTE ENTIERE de l'origine
    -- que le call-site passe une ENTITE (que `SelectTiles` deplie) ou un selecteur de TUILES. Sur
    une origine MONO-hex il est INERTE (une tuile n'est jamais dans son propre voisinage) ; sur une
    origine MULTI-hex il retire les pieds, qui sont voisins les uns des autres.

    ⚠ RESIDU `#459-r2` : le `OrderedSet` natif DEDOUBLONNE aussi ; le port rend toujours l'union
    BRUTE (les call-sites portes font suivre d'un `Unique`/`TileUnique`, cf. l'en-tete)."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        tiles = _tile_positions(self.source, ctx, board)
        origin_ids = {board.id_at(p[0], p[1]) for p in tiles}      # les `tiles` du `Contains` natif
        out: list = []
        for p in tiles:
            tid = board.id_at(p[0], p[1])
            if tid is None:
                continue
            out.extend(n for n in board.neighbours_native(tid) if n not in origin_ids)
        return out


class TrenchTiles(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$Trench(source)` ->
    `IdunBattle.Entities.Selectors.TrenchTilesSelector$$Select` -- MIRROR du decompile :

        result = new List<TileEntity>()
        foreach (t in this.<+0x18 source>.SelectTiles(entities))     # vslot 10 = SelectTiles
            if (IdunBattle.Entities.TileExtensions$$IsTrench(t)) result.Add(t)
        return result

    Deux points LUS, pas deduits :

    1. Le natif consomme la source par **`SelectTiles`** (le slot virtuel 10, pas `Select`) -- donc
       une ENTITE-unite y est depliee en son EMPREINTE, exactement comme pour `AdjacentTiles`. Le
       port passe par `_tile_positions` (domaine MIXTE unite / id de tuile / position), meme
       normalisation.
    2. `IdunBattle.Entities.TileExtensions$$IsTrench(tile)` = `IdunBattle.Entities.TileExtensions
       $$IsTileWithId(tile, <TileId Trench>)` : c'est le TERRAIN STATIQUE de la tuile (`tileDefId`
       de la BC), **pas** l'effet de tuile `EffectType.Trench` (1059) que pose
       `IdunBattleLogic.Entities.Abilities.Tiles.Loki.TrenchAbility$$CreateBehaviour` sur les
       UNITES. Le port lit donc `Board.terrain_at` -- le MEME canal que la sous-branche
       `IsTrench(attackerTile)` de `IdunBattle.Core.Services.DamageCalculations$$
       CalculateTrenchReduction` (`services/damage_modifiers.py`), pas un second.

    AUCUN dedoublonnage natif (`List.Add` nu, pas un `OrderedSet`) -> le port n'en fait pas non
    plus ; l'ordre est celui de la source. board None -> []."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        out: list = []
        for p in _tile_positions(self.source, ctx, board):
            if board.terrain_at(p[0], p[1]) != "Trench":     # TileExtensions.IsTrench(t)
                continue
            tid = board.id_at(p[0], p[1])
            if tid is not None:
                out.append(tid)
        return out


class PreviousTile(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$PreviousTile(unit)` ->
    `IdunBattle.Entities.Selectors.PreviousTileSelector$$Select` -- MIRROR du decompile :

        entity = this.<+0x18 unitSelector>.SelectSingle(entities)     # null -> throw (cf. ci-dessous)
        comp   = entity.GetComponent<PositionComponent>()
        nul    = comp.<+0x88>                                          # Nullable<UnitPositionId>
        return nul.HasValue ? UnitPositionIdExtensions.ToTileList(nul.Value, this.<+0x10 state>)
                            : new List<TileEntity>()

    Le `Nullable` est ecrit par `IdunBattle.Operations.SetUnitPositionOperation$$SavePreviousPosition`
    (foyer porte : `runner/components.py::save_previous_position`), donc il vaut l'EMPREINTE QUITTEE
    au dernier deplacement -- **pas** la tuile courante, et **pas** une valeur per-tour (`+0x98`,
    l'autre slot que le meme `SavePreviousPosition` ecrit, est celui que lit
    `IdunBattle.Entities.EntityExtensions$$GetPreviousPositionThisTurn` ; il n'a aucun consommateur
    porte -- residu nomme sur `PositionComponent`).

    DOMAINE : ids de TUILE (comme `AdjacentTiles`/`CanAddUnit`), pour etre consommable par
    `CanAddUnit`/`Count`. Le natif rend des `TileEntity` ; la conversion coordonnees -> id passe par
    le board, donc `board` absent -> `[]`.

    DEGRADATION : `ctx.previous_tiles` absent (contexte hors runner) -> `[]`. Le natif, lui, LEVE sur
    selecteur vide ; le port refuse en silence, comme partout ailleurs dans cette couche.

    CONSOMMATEUR PORTE : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HaywireMineAbility$$
    CreateBehaviour` (`AmountIsGreaterThanZero(PreviousTile(Owner))` en garde, puis
    `CanAddUnit(PreviousTile(Owner))` comme tuile de pose)."""
    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        fn = getattr(ctx, "previous_tiles", None)
        if board is None or fn is None:
            return []
        u = resolve_unit(self.unit, ctx)
        if not u:
            return []
        out: list = []
        for col, row in (fn(u) or ()):
            tid = board.id_at(col, row)
            if tid is not None:
                out.append(tid)
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


class SortTilesByUtility(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$SortTilesByUtility(tiles, unit, definition, parent)`
    -> `IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select` : les tuiles de `source`,
    triees par utilite DECROISSANTE (tri STABLE -> l'ordre de `source` tranche les egalites).

    Le NOEUD ; le CALCUL vit dans le foyer UNIQUE `engine/utilities/tile.py::sort_tiles_by_utility`
    (mirror du `UtilityDecider.CalculateUtility` + composition de bucket, deja valide) -- on delegue
    par l'accesseur `ctx.sort_tiles_by_utility` au lieu de le reecrire. **ZERO tirage** : le tri ne
    touche pas le PRNG.

    POURQUOI UN NOEUD, et pas un collapse (#448-r1). Les call-sites portes jusqu'ici collapsaient
    `First(SortTilesByUtility(...), 1)` en un helper imperatif (`first_tile_by_utility`), parce que
    leur resultat n'etait consomme QU'UNE FOIS. `...StormboyzStrike_FallbackAbility$$CreateBehaviour`
    ne le peut pas : il passe **le MEME objet-noeud** a `MoveUnitBehaviour` ET a `AddEffect`, et
    l'`op_BitwiseAnd` les execute EN SEQUENCE -- donc le noeud est RE-EVALUE apres le move, quand le
    caster occupe deja la meilleure tuile et que `CanAddUnit` l'exclut. C'est exactement le quirk
    mesure par #425 (la tuile MARQUEE n'est pas la tuile d'ATTERRISSAGE). Un collapse le perdrait,
    silencieusement.

    `unit_sel` = le `dc.unit` natif (`Select` SINGULIER, null si rien) ; `utility_type` = le litteral
    du call-site (`UtilityDefinition(6 = UnitMovement)` pour le Fallback, tranche par XREF ENTRANTE
    sur la surcharge `UtilityDefinition..ctor(utilityType)`). `parent_sel` = `dc.parent`, nul a ce
    call-site.

    DOMAINE : rend des IDS d'entite-tuile (comme `CanAddUnit`/`AdjacentTiles`, sa source naturelle).
    `ctx.sort_tiles_by_utility` absent -> ordre SOURCE inchange (aucune utilite calculee)."""
    def __init__(self, source: TargetsSelector, unit_sel: TargetsSelector = None,
                 utility_type: int = UtilityType.Tile, parent_sel: TargetsSelector = None,
                 utility_definition=None):
        self.source = source
        self.unit_sel = unit_sel
        self.utility_type = int(utility_type)
        self.parent_sel = parent_sel
        # `utility_definition` (#120bis-spawn) = le 3e argument natif quand le call-site BATIT sa
        # definition au lieu de passer un `UtilityType` scalaire -- allocation d'un
        # `WeightedUtility[N]`, un `IdunBattleLogic.AI.Utilities.UtilityBucket$$.ctor` puis un
        # `IdunBattleLogic.AI.Utilities.UtilityDefinition$$.ctor(bucket)`. C'est ce que fait
        # `IdunBattleLogic.Entities.Abilities.Active.Loki.SwornProtectorAbility$$GetSpawnTile`
        # (`[ WeightedUtility(7 = Tile), WeightedUtility(0x34 = 52
        # SwornProtector_AvoidAdjacentEnemies) ]`). Elle PRIME sur `utility_type` (meme regle que
        # dans le foyer `engine/utilities/tile.py::sort_tiles_by_utility`) ; `None` = comportement
        # INCHANGE pour tous les call-sites existants.
        self.utility_definition = utility_definition

    def select(self, ctx):
        tiles = list(self.source.evaluate(ctx) or [])
        f = getattr(ctx, "sort_tiles_by_utility", None)
        if f is None or not tiles:
            return tiles                      # cf. docstring : degradation NOMMEE, ordre source
        u = resolve_unit(self.unit_sel, ctx) if self.unit_sel is not None else None
        p = resolve_unit(self.parent_sel, ctx) if self.parent_sel is not None else None
        return list(f(tiles, (u or {}).get("id"), self.utility_type, (p or {}).get("id"),
                      self.utility_definition))


class CanAddUnit(TargetsSelector):
    """`DSLFactory.CanAddUnit(tiles)` : garde les tuiles ou une unite PEUT etre ajoutee = `walkable`
    ET LIBRE (aucun occupant VIVANT). Occupation = tuiles des `ctx.units` vivants (mirror du
    `_occupied_tiles(state)` imperatif). Ordre de `source` preserve. board None -> [].

    OCCUPATION PAR PIED (#91) : le natif `IdunBattle.Entities.TileExtensions$$CanAddUnit` lit le
    `TileContentComponent` de la tuile -- une tuile sous N'IMPORTE QUEL pied est occupee (#R30 §1).
    On lit donc l'EMPREINTE (`unit["feet"]`, mirror `EntityExtensions$$GetTiles`), pas la seule
    `PositionComponent`. Strictement equivalent pour une unite mono-tuile (`feet == [pos]`) ; sans
    ca, un Galatian pose au sol par `DutyEternal` ne bloquait que sa MAIN TILE et le port acceptait
    de spawner sur ses deux autres pieds.

    OCCUPATION : le CONTENU DE LA TUILE, PAS les PV de son occupant
    (#462-r4b-r1-r1-r1-r1-c-r3-r1-r5). La chaine native, LUE de bout en bout :

        IdunBattle.Entities.Selectors.CanAddUnitTileSelector$$Select
            allowSteppable = !<trigger @+0x28>.ShouldTrigger(entities, 0x20)
            garde les tuiles t telles que TileExtensions.CanAddUnitFromAbility(t, state, parent,
                                                                              allowSteppable)
        IdunBattle.Entities.TileExtensions$$CanAddUnitFromAbility
            = IsFreeTile(t, state, allowSteppable, allowTemporaryTile: 0, allowAnyUnit: 0)
              && !IsTileReservedForOtherUnit(t, parent) && !IsTilePendingDrafting(t, state, 0)
        IdunBattle.Entities.TileExtensions$$IsFreeTile   (branche `allowAnyUnit == 0`)
            libre = allowSteppable ? (content.IsEmpty() || GetUnit(t).HasTrait(0x1b = Steppable))
                                   : content.IsEmpty()

    **Aucun etage ne lit les PV.** Le port filtrait `alive ET hp > 0` (`_is_alive`) : une unite a
    **0 PV** -- ce qu'est une mine Haywire PAR CONSTRUCTION (`HaywireMine` n'a pas de variable
    `summonHp`, donc `UnitStats_MaxHealth = 0`, mesure live) -- ne bloquait donc RIEN, et le port
    posait une seconde mine SUR la premiere. Le critere est desormais `alive` seul, c'est-a-dire
    « l'unite est SUR le plateau » : c'est deja le modele des DEUX jumeaux imperatifs de ce noeud
    (`operations/spawn.py::_occupied_tiles` et `::_free_tiles_adjacent`), qui ne lisent que
    `UnitComponent.alive` -- le noeud DSL etait le seul a diverger.
    ⚠ Les MORTS restent exclus, et c'est fidele : `KillUnitOperation` -> `RemoveUnitFromTiles` vide
    le `TileContentComponent`, donc un cadavre n'occupe plus rien cote natif non plus.

    `allow_steppable` = la branche `allowSteppable` d'`IsFreeTile`, DESORMAIS PAR CALL-SITE. Le natif
    ne la recoit pas comme un booleen mais comme un TRIGGER (`DSLSelectors$$CanAddUnit(tiles, parent,
    isSteppable: IAbilityTrigger)` -> `CanAddUnitTileSelector+0x28`), et
    `IdunBattle.Entities.Selectors.CanAddUnitTileSelector$$Select` l'INVERSE, verbatim :

        allowSteppable = !(<+0x28>.ShouldTrigger(entities, 0x20))
        garde t ssi TileExtensions.CanAddUnitFromAbility(t, state, parent, allowSteppable)

    `False` (defaut) = branche `allowSteppable == 0`, comportement HISTORIQUE inchange -- c'est celle
    du call-site `HaywireMineAbility`, MESUREE (au tour ou la mine occupe deja `PreviousTile`, le
    natif ne repose RIEN : `Count(tiles) == 0` -> `TriggerAbilityDelayed`).
    `True` = branche `allowSteppable == 1` : une tuile dont l'occupant porte `Steppable` est LIBRE.
    Unique porteur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.ItItchesAbility$$ExecuteBehaviour`
    passe `isSteppable = <DSLTriggers+0x48>`, que `IdunBattleLogic.Entities.DSLTriggers$$.ctor` pose
    comme `op_LogicalNot(<le trigger SANS operande de +0x40/+0x70>)` -- ce meme slot `+0x70` est deja
    nomme `YesTrigger` par le port (`entities/effects/loki/martial_superiority.py`,
    `.../counter_attack.py`, identifie par sa taille 16 et son absence de champ). Donc
    `ShouldTrigger` y est TOUJOURS FAUX, donc `allowSteppable` TOUJOURS VRAI a ce call-site.

    `parent_sel` = LE SECOND GATE, et il n'a PAS de valeur « neutre » (#550-r4). `CanAddUnitFromAbility`
    appelle `IsTileReservedForOtherUnit(t, parent)` juste apres `IsFreeTile`, et
    `CanAddUnitTileSelector$$Select` resout `parent` par le SELECTEUR `<this+0x20>`
    (`SelectUnit(entities, 3)`). Les TROIS surcharges natives de `IdunBattleLogic.Entities.DSLSelectors$$
    CanAddUnit` construisent le meme `CanAddUnitTileSelector(state, tiles, parent, isSteppable)`, et
    ce qu'elles mettent en `parent` est LU, pas suppose :

        CanAddUnit(tiles)                    parent = <le selecteur que rend DSLSelectors$$None()>
        CanAddUnit(tiles, isSteppable)       parent = idem
        CanAddUnit(tiles, parent, isSteppable)  parent = celui de l'appelant

    Les deux premieres allouent `new EntitySelector(state, entityId: null)` -- **le corps est
    IDENTIQUE, instruction pour instruction, a celui de `IdunBattleLogic.Entities.DSLSelectors$$None`**
    (meme `Il2CppClass*`, meme ctor, memes arguments `(state, 0, 0)`), et le type est NOMME par la
    surcharge voisine `DSLSelectors$$Entity(entityId)`, dont le ctor est `IdunBattle.Entities.Selectors.
    EntitySelector$$.ctor(this, state, entityId)`. Or `IdunBattle.Entities.Selectors.EntitySelector$$
    GetEntity` rend `null` quand ses trois champs (`+0x18` entite, `+0x20` id, `+0x28` selecteur d'id)
    sont nuls. ⇒ **`parent` est NUL a ces call-sites**, et `IsTileReservedForOtherUnit(t, null)` prend
    sa branche `allowedUnit == null` = `content.<+0x34>.HasValue` : « la tuile est reservee par
    QUICONQUE » -> refus. Polarite SAINE.

    ⇒ `parent_sel=None` (defaut) N'EST PAS « pas de gate » : c'est le `None()` natif, donc le gate
    « refuse toute tuile RESERVEE ». Un `parent_sel` non nul bascule sur l'autre branche
    (`!(HasValue && Value == parent.Id)`), qui refuse toute tuile **NON** reservee pour ce parent --
    c'est ce qui rend le `Reserve(Owner, targetTiles)` d'`ItItches` LOAD-BEARING. Unique call-site
    natif de la surcharge a trois arguments : `IdunBattleLogic.Entities.Abilities.Active.Loki.
    ItItchesAbility$$ExecuteBehaviour`, qui y passe `<DSLSelectors+0x30>` = `Owner`.

    SUBSTRAT : `ctx.tile_reserved_for_other_unit` (foyer unique `runner/operations/tile_reservation.py`).
    **Absent = NON MESURE**, et le gate ne joue alors pas du tout : le rabattre sur une table VIDE
    ferait rendre un ensemble VIDE a tout call-site `parent` non nul (contexte de prediction, arbre
    monte hors runner). Meme tri-etat nomme que `ctx.sort_tiles_by_utility`.

    RESIDU NOMME : `IsTilePendingDrafting(t, state, 0)`, le TROISIEME gate, n'a pas d'equivalent porte
    (le `DraftingComponent` des joueurs n'est publie par aucune seed BC) -- direction PERMISSIVE, meme
    residu que le gate G7 de `IdunBattle.Operations.MoveUnitOperation$$Execute`."""
    def __init__(self, source: TargetsSelector, allow_steppable: bool = False,
                 parent_sel: TargetsSelector = None):
        self.source = source
        self.allow_steppable = bool(allow_steppable)      # `!<+0x28>.ShouldTrigger` (cf. docstring)
        # `<CanAddUnitTileSelector+0x20>` : `None` ENCODE le selecteur que rend `DSLSelectors$$None()`
        # (un `EntitySelector` vide, donc `parent` NUL), PAS l'absence de gate. Cf. la docstring.
        self.parent_sel = parent_sel

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        ht = getattr(ctx, "has_trait", None) or (lambda u, t: False)
        occ = set()
        for u in ctx.units:
            # `TileContentComponent.IsEmpty` -- l'occupation est celle de la TUILE, PAS la vitalite
            # de son occupant : cf. le bloc « OCCUPATION : le CONTENU DE LA TUILE » de la docstring.
            if not u.get("alive", True):
                continue
            # `IsFreeTile` branche `allowSteppable == 1` : `content.IsEmpty() || GetUnit(t).HasTrait(
            # 0x1b = Steppable)` -- l'occupant STEPPABLE ne rend PAS la tuile occupee.
            if self.allow_steppable and ht(u, UnitTrait.Steppable):
                continue
            for f in _feet(u):                            # `GetTiles` (repli main tile documente)
                t = board.id_at(f[0], f[1])
                if t is not None:
                    occ.add(t)
        kept = [t for t in self.source.evaluate(ctx) if t not in occ and board.walkable(t)]
        # `if (IsTileReservedForOtherUnit(tile, parent)) return false;` -- le 2e gate de
        # `IdunBattle.Entities.TileExtensions$$CanAddUnitFromAbility`. `parent` est resolu UNE FOIS
        # par cast, comme le natif (`Select` le calcule avant sa boucle sur les tuiles).
        reserved = getattr(ctx, "tile_reserved_for_other_unit", None)
        if reserved is None:
            return kept                                   # substrat NON MESURE, cf. docstring
        parent = resolve_unit(self.parent_sel, ctx) if self.parent_sel is not None else None
        parent_id = (parent or {}).get("id") if parent else None
        return [t for t in kept if not reserved(board.coord(t), parent_id)]


class TileBehindTargetFromSourceDirection(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$TileBehindTargetFromSourceDirection(target, source)`
    -> `IdunBattle.Entities.Selectors.TileBehindTargetFromSourceDirectionSelector$$Select` : LA tuile
    adjacente a `target`, un pas AU-DELA dans la direction `source -> target`. Retour domaine ID
    (0 ou 1 element), pour composer avec `CanAddUnit` -- son consommateur immediat au seul call-site
    porte.

    Le `Select` natif resout ses deux sous-selecteurs puis delegue INTEGRALEMENT a
    `IdunBattle.Core.Services.BattleQuery$$GetTileBehindTargetFromSourceDirection(source, target)` ;
    la geometrie (et le `DirectionTo` qui la porte) vit donc dans le mirror UNIQUE
    `engine.battle_query.get_tile_behind_target_from_source_direction`, ce noeud n'en est que
    l'adaptateur tile-id.

    ⚠ ORDRE DES ARGUMENTS -- tranche au ctor, jamais au nom de la factory : le ctor
    `...TileBehindTargetFromSourceDirectionSelector$$.ctor(this, state, query, targetTileSelector,
    sourceTileSelector)` ecrit `+0x18 = sourceTileSelector` et `+0x20 = targetTileSelector`, et
    `Select` appelle `query.<slot 0x59>(Select(+0x18), Select(+0x20))` = `(source, target)`. La
    factory, elle, prend `(target, source)` -- les deux ordres sont INVERSES l'un de l'autre, et ce
    noeud expose celui de la FACTORY (le seul qu'un call-site ecrit).

    AUCUN gate ici (ni walkable, ni occupation) : le natif rend la tuile telle quelle. Au call-site
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DiveAttackAbilityBase$$GetMovementBehavior`,
    c'est le `CanAddUnit(...)` englobant qui filtre -- et c'est ce qui rend la branche de repli
    (`ConditionalSelector`) atteignable quand la tuile d'atterrissage est occupee.

    `source`/`target` normalises par `_tile_positions` (unite / id de tuile / position), comme
    `TilesBehindInLine`. board None -> []."""
    def __init__(self, target: TargetsSelector, source: TargetsSelector):
        self.target, self.source = target, source

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        src = _tile_positions(self.source, ctx, board)
        dst = _tile_positions(self.target, ctx, board)
        if not src or not dst:
            return []
        positions = battle_query.get_tile_behind_target_from_source_direction(
            src[0], dst[0], tile_exists=lambda p: board.id_at(p[0], p[1]) is not None)
        return [t for t in (board.id_at(p[0], p[1]) for p in positions) if t is not None]


class TileBehindFilled(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$TileBehindFilled(origin, target)`
    -> `IdunBattle.Entities.Selectors.TileBehindFilledSelector$$Select` : la ou les tuiles situees
    UN PAS AU-DELA de `target`, dans la direction `origin -> target`. Retour domaine ID.

    Le `Select` natif resout ses deux sous-selecteurs (`+0x18 = origin`, `+0x20 = target`, dans
    l'ordre des arguments de la factory -- contraste avec `TileBehindTargetFromSourceDirection`,
    dont le ctor INVERSE l'ordre) puis delegue integralement a `IBattleQuery` **slot 85** =
    `GetTilesBehindFilled(from, direction, checkElevation)`, avec `checkElevation = 1` (litteral).
    La geometrie vit donc dans le mirror UNIQUE `engine.battle_query.get_tiles_behind_filled` ; ce
    noeud n'en est que l'adaptateur tile-id.

    ⚠ « Filled » = le natif peut rendre DEUX tuiles quand `origin` et `target` ne sont pas alignes
    hexagonalement (branche `MovementUtil$$RoundDirection`, NON portee -- residu `#1052-r1`, cf. le
    mirror). Aligne -> une seule tuile, comme
    `GetTileBehindTargetFromSourceDirection`.

    Seul call-site porte : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PyreblasterAbility$$
    CreateBehaviour` (et son jumeau `$$GetUnitBehindTarget`), qui l'appelle avec
    `origin = <DSLSelectors+0x50> = CasterTile` et `target = <DSLSelectors+0x60> = Target`.

    `origin`/`target` normalises par `_tile_positions` (unite / id de tuile / position), comme
    `TileBehindTargetFromSourceDirection`. board None -> []."""
    def __init__(self, origin: TargetsSelector, target: TargetsSelector):
        self.origin, self.target = origin, target

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        src = _tile_positions(self.origin, ctx, board)
        dst = _tile_positions(self.target, ctx, board)
        if not src or not dst:
            return []
        # `IsReachableElevation(from, tile)` = `|elev(a) - elev(b)| < 2` ; canal absent -> gate
        # INERTE (meme convention tri-etat que `tiles_behind_accessors`).
        def _elev(p):
            tid = board.id_at(p[0], p[1])
            return None if tid is None else board.elevation(tid)
        positions = battle_query.get_tiles_behind_filled(
            src[0], dst[0], check_elevation=True,
            tile_exists=lambda p: board.id_at(p[0], p[1]) is not None,
            elevation_at=_elev)
        return [t for t in (board.id_at(p[0], p[1]) for p in positions) if t is not None]


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


class TileUnion(TargetsSelector):
    """Union de deux ensembles de TUILES (ids) -- `IdunBattle.DSL.TargetsSelector$$op_Addition` du
    domaine tile. Concatene `left` puis `right`, DEDUP (1re apparition preservee).

    Homologue tile de `Union` (`selectors/units.py`), qui passe par `_units_of` et rendrait `[]` sur
    des ids de tuile. Meme motif que `TileIntersect`/`TileUnique` juste au-dessus : le natif n'a
    qu'UN `op_Addition`, le port en a deux ecritures parce que le domaine n'est pas type cote port.

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.ItItchesAbility$$GetTargetTiles`
    = `Target@0x60 op_Addition AdjacentTilesIntersection(CasterTile@0x50, Target@0x60)`.

    ⚠ **UN OPERANDE PEUT ETRE UNE ENTITE SEULE, pas un ensemble** (#889-r6) : le natif `op_Addition`
    prend deux `TargetsSelector` et l'un des deux peut etre un noeud MONO-ENTITE -- exactement la
    lecture deja ecrite sur `Sub` (`op_Subtraction` accepte << un SELECTEUR ou une ENTITE >>).
    Call-site : `...InstrumentsOfVengeanceAbility$$GetEffectBehavior` ecrit
    `TilesBehindInLine(...) op_Addition ActiveTarget@DSLSelectors+0x68`, ou `ActiveTarget` est
    l'element COURANT du tri -- donc **un id de tuile NU**, sur lequel `list(...)` levait
    `TypeError`. `_tile_items` normalise, comme `_units_of` cote unite."""
    def __init__(self, left: TargetsSelector, right: TargetsSelector):
        self.left, self.right = left, right

    def select(self, ctx):
        seen, out = set(), []
        for t in _tile_items(self.left, ctx) + _tile_items(self.right, ctx):
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out


def _power_up_ids() -> frozenset:
    """Les 22 `TriggeredAbilityType` du `HashSet<TriggeredAbilityType>` que
    `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.TriggeredAbility$$.cctor`
    ecrit dans `<statics+0x70>` et dont
    `...StaticBattleRules.TriggeredAbility$$GetPowerUps` rend une COPIE.

    LUS un a un dans le `.cctor` (suite de `local_res10[0] = <ordinal> ; HashSet.Add(...)`), jamais
    derives du prefixe `PowerUp_` du nom -- et ecrits par leur MEMBRE, pas par leur ordinal (regle
    d'enum du `CLAUDE.md` : `TriggeredAbilityType` partage 458 ordinaux avec `EffectType`)."""
    from ..triggered_ability_type import TriggeredAbilityType as _T
    return frozenset(int(x) for x in (
        _T.PowerUp_Armor, _T.PowerUp_Damage, _T.PowerUp_Health, _T.PowerUp_Hits,
        _T.PowerUp_MeleeHits, _T.PowerUp_Reinforcement, _T.PowerUp_ReinforcementShield,
        _T.PowerUp_ReactivateAbility, _T.PowerUp_Healing, _T.PowerUp_Bomb, _T.PowerUp_Resurrect,
        _T.PowerUp_HeroSpawn, _T.PowerUp_HeroSpawn_VexilusPraetor,
        _T.PowerUp_HeroSpawn_BladeChampion, _T.PowerUp_HeroSpawn_Uthar, _T.PowerUp_SummonSpawn,
        _T.PowerUp_SummonSpawn_ultraSmnInceptor, _T.PowerUp_SummonSpawn_ultraSmnHeavyIntercessor,
        _T.PowerUp_SummonSpawn_bloodSmnIntercessor, _T.PowerUp_SummonSpawn_darkaSmnHellblaster,
        _T.PowerUp_SummonSpawn_darkaSmnTerminator, _T.PowerUp_SummonSpawn_templSmnAggressor))


def unit_is_power_up(unit, has_triggered_ability=None) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsPowerUp(unit)` -- MIRROR : la boucle native parcourt
    `GetPowerUps()` et sort a la PREMIERE `TriggeredAbilityComponent$$TryGetAbility` vraie.

    `has_triggered_ability` = l'accesseur `ctx.has_triggered_ability` du contexte DSL, FOYER UNIQUE
    du kit declenche d'une ENTITE cote port (`entity_triggered_ability_ids`, tri-etat mesure/repli
    gameconfig documente a la source). C'est exactement ce que lit le noeud-trigger homonyme
    `entities/triggers.py::HasTriggeredAbility`.

    ⚠ **Le dict d'unite du DSL NE PORTE PAS de cle `triggered_abilities`** (`_unit_dict` de
    `runner/abilities/behaviours/context.py` : `id/team/pos/feet/alive/hp/visualId/...`). Lire une
    telle cle rendrait donc TOUJOURS `False`, en silence -- c'est-a-dire le predicat INERTE, et un
    filtre inerte est indiscernable d'un filtre correct sur un plateau sans power-up.

    Accesseur ABSENT -> `False` : degradation NOMMEE et RESTRICTIVE (les deux consommateurs portes
    RETIRENT des tuiles quand ce predicat est vrai, donc un VRAI invente amputerait la selection)."""
    if unit is None or has_triggered_ability is None:
        return False
    return any(bool(has_triggered_ability(unit, int(a))) for a in _power_up_ids())


class TilesWithoutPowerUps(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$TilesWithoutPowerUps(entities)` ->
    `IdunBattle.Entities.Selectors.TilesWithoutPowerUpsSelector$$Select` -- MIRROR du decompile :

        foreach (e in <+0x18>.Select(entities)) {
            unit = UnitExtensions.GetUnit(e, state@<+0x20>);
            if (unit == null || !UnitExtensions.IsPowerUp(unit))  out.Add(e);
        }

    ⚠ **La garde est `unit == null` OU `!IsPowerUp`, dans CET ordre** : une tuile LIBRE passe (c'est
    la branche `goto LAB_180fefd3a` du decompile, prise AVANT tout appel a `IsPowerUp`). Le noeud ne
    retire donc QUE les tuiles dont l'OCCUPANT est un power-up -- il n'exige PAS que la tuile soit
    libre. C'est ce qui le rend composable avec le `.Otherwise(base)` de son unique call-site porte
    (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BattleFocusAbility$$CreateMoveBehaviour`),
    ou `base` est deja un `CanAddUnit(...)` : sans ce point, l'`Otherwise` serait toujours inerte.

    DOMAINE : ids de tuile en entree comme en sortie, ordre de `source` preserve. `board` absent ->
    aucune tuile ne resout d'occupant, donc le noeud rend `source` TEL QUEL -- degradation
    RESTRICTIVE au sens du natif (il ne retire rien), et NOMMEE."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        src = list(self.source.evaluate(ctx) or [])
        board = getattr(ctx, "board", None)
        if board is None:
            return src
        # `UnitExtensions$$GetUnit(tile)` = foyer unique de la resolution d'occupant (#433-r3-r1a) :
        # index par COORD, n'importe quel PIED resout en son unite.
        occ = _occupants_by_tile(ctx.units)
        hta = getattr(ctx, "has_triggered_ability", None)
        out = []
        for t in src:
            c = board.coord(t)
            u = occ.get((int(c[0]), int(c[1]))) if c is not None else None
            if not unit_is_power_up(u, hta):
                out.append(t)
        return out


class SafestTiles(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$SafestTiles(tiles, unit, unitsToAvoid)` ->
    `IdunBattle.Entities.Selectors.SafestTileSelector$$Select` -- MIRROR du decompile, boucle par
    boucle (champs poses par
    `IdunBattle.Entities.Selectors.SafestTileSelector$$.ctor(state, battleQuery, tiles, unit,
    unitsToAvoid)` : `+0x18 tiles`, `+0x20 unit`, `+0x28 state`, `+0x30 battleQuery`,
    `+0x38 unitsToAvoid`) :

        me    = Enumerable.First( unit@<+0x20>.Select(entities) )
        avoid = unitsToAvoid@<+0x38>.SelectAll(entities, 3)
        best = new List(); bestMin = 0; bestCount = int.MaxValue;
        foreach (tile in tiles@<+0x18>.Select(entities)) {
            cur = new List(); curMin = int.MaxValue;
            foreach (e in avoid) {
                if (e == me) continue;
                eTiles = EntityExtensions.GetTiles(e, state@<+0x28>);
                d = battleQuery@<+0x30>.<slot 0x6d = GetDistance>(tile, eTiles);
                if (d <= curMin) {
                    if (d < curMin) { cur.Clear(); curMin = d; }
                    cur.AddRange(eTiles);
                }
            }
            if (curMin > bestMin) { best.Clear(); best.Add(tile);
                                    bestMin = curMin; bestCount = cur.Count; }
            else if (curMin == bestMin) {
                if (cur.Count < bestCount) { best.Clear(); best.Add(tile);
                                             bestCount = cur.Count; }
                else if (cur.Count == bestCount) best.Add(tile);
            }
        }
        return best;

    QUATRE lectures que le decompile TRANCHE, et qu'il ne faut pas deviner :

    * **le critere est LEXICOGRAPHIQUE, a deux etages** : MAXIMISER d'abord la distance au plus
      proche des `unitsToAvoid`, puis, a egalite, MINIMISER `cur.Count`. Ce compteur est alimente
      par `AddRange(eTiles)`, donc il compte des TUILES, pas des unites : une unite multi-hex y pese
      autant de fois qu'elle a de pieds. C'est le natif, pas un biais du port ;
    * **le sujet ne se fuit pas lui-meme** : `if (entity != <me>) ...` ecarte l'unite rendue par
      `unit@<+0x20>` de la liste a eviter ;
    * **`bestMin` part de `0`, pas de `int.MinValue`** -- donc une tuile dont la distance minimale a
      un ennemi vaut `0` (un ennemi est DESSUS) ne peut jamais entrer dans `best` ;
    * **le retour est un ENSEMBLE d'ex aequo**, pas une tuile : son unique call-site porte
      (`...BattleFocusAbility$$CreateMoveBehaviour`) l'enchaine sur `PickRandomly(..., 1)`.

    `avoid` VIDE : la 1re tuile a `curMin == int.MaxValue > bestMin == 0` -> elle entre seule et
    pose `bestCount = 0` ; les suivantes ont `curMin == bestMin` et `cur.Count == bestCount == 0`
    -> elles s'AJOUTENT. Sans unite a eviter, le noeud rend donc TOUTES les tuiles -- mirror exact,
    pas une degradation.

    La distance passe par `board.distance` (le `<slot 0x6d> = GetDistance(tileA, tilesB)` natif prend
    le MIN sur l'empreinte), avec les EMPREINTES (`_feet`) des unites a eviter, pas leur seule main
    tile. `board` absent -> `[]`."""
    _INF = 2 ** 31 - 1                                   # `int.MaxValue` des deux compteurs natifs

    def __init__(self, tiles: TargetsSelector, unit: TargetsSelector,
                 units_to_avoid: TargetsSelector):
        self.tiles = tiles
        self.unit = unit
        self.units_to_avoid = units_to_avoid

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        me = resolve_unit(self.unit, ctx)
        me_id = (me or {}).get("id")
        avoid = []
        for u in _units_of(self.units_to_avoid, ctx):
            if not isinstance(u, dict) or u.get("id") is None:
                continue
            if me_id is not None and int(u["id"]) == int(me_id):
                continue                                 # `if (entity != <me>)`
            pos = [p for p in _feet(u) if p is not None]  # `EntityExtensions$$GetTiles` = l'empreinte
            if pos:
                avoid.append(pos)
        best, best_min, best_count = [], 0, self._INF
        for t in self.tiles.evaluate(ctx) or []:
            c = board.coord(t) if hasattr(board, "coord") else None
            if c is None:
                continue
            cur_count, cur_min = 0, self._INF
            for feet in avoid:
                d = min(hexgeo.distance((c[0], c[1]), (p[0], p[1])) for p in feet)
                if d <= cur_min:
                    if d < cur_min:
                        cur_count, cur_min = 0, d
                    cur_count += len(feet)               # `cur.AddRange(eTiles)`
            if cur_min > best_min:
                best, best_min, best_count = [t], cur_min, cur_count
            elif cur_min == best_min:
                if cur_count < best_count:
                    best, best_count = [t], cur_count
                elif cur_count == best_count:
                    best.append(t)
        return best


class UnobscuredTiles(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$UnobscuredTiles(fromAnyTiles, toTiles)` ->
    `IdunBattle.Entities.Selectors.UnobscuredTilesSelector$$Select` -- MIRROR du decompile.

    `IdunBattle.Entities.Selectors.UnobscuredTilesSelector$$.ctor(state, movementQuery, fromTile,
    targetTiles)` pose `+0x20 = fromTile` et `+0x18 = targetTiles` (LU, pas interpole : les trois
    ecritures du ctor sont explicites). `Select` fait alors

        tiles  = <+0x18 targetTiles>.Select(entities);      // la LISTE parcourue
        caster = <+0x20 fromTile>.SelectUnit(entities);     // le REFERENT de visibilite
        foreach (t in tiles) if (!IsObscured(caster, t)) result.Add(t);

    et `IdunBattle.Entities.Selectors.UnobscuredTilesSelector$$IsObscured(caster, targetTile)` :

        foreach (c in IterateTiles(caster))                          // TOUTES les tuiles du referent
            if (<IMovementQuery slot 16>(c, targetTile, 6, 2).Count == 0)  return false;
        return true;

    => une tuile est GARDEE des qu'UNE SEULE tuile du referent la voit (d'ou le nom `fromAnyTiles`),
    et la liste source VIDE rend `true` = OBSCURCI => la tuile est RETIREE. Les deux litteraux
    `6, 2` sont `ObscuringType.All` et `blockingElevationDifference` --
    `services.targeting_query.OBSCURING_TYPE_ALL` / `BLOCKING_ELEVATION_DIFFERENCE`, le meme couple
    que la DECISION deja portee (`runner/abilities/loki/mv71.py::_is_obscured_from_tiles`).

    Ce noeud manquait (residu `#287-r11-r2-r1-r3`), et le motif de ce manque etait
    « aucun SECOND consommateur porte ne peut le justifier » : les trois call-sites natifs sont
    `MV71SniperDroneSquadAttackAbility$$PickTile`,
    `IdunBattleLogic.Entities.Abilities.Active.Loki.LivingLightningAbility$$GetPossibleTargets` et
    `...$$GetEnemiesInRange`. Le port de `LivingLightning` EST ce second consommateur -- le noeud est
    donc materialise ici et CONSOMME par `runner/operations/triggers/loki/living_lightning.py`.
    Le REBRANCHEMENT de `mv71.py` (qui garde sa DECISION impérative) reste ouvert, hors de cette
    tranche : c'est le foyer d'un autre residu.

    `board is None` -> le canal d'elevation n'existe pas -> PASSE-TOUT (aucun retrait invente ;
    meme convention permissive que `Unobscured` cote unites et que `mv71`)."""
    def __init__(self, from_tiles: TargetsSelector, to_tiles: TargetsSelector):
        self.from_tiles, self.to_tiles = from_tiles, to_tiles

    def select(self, ctx):
        raw = self.to_tiles.evaluate(ctx)                    # `<+0x18>.Select(entities)`
        tiles = list(raw) if isinstance(raw, (list, tuple)) and not (
            len(raw) == 2 and all(isinstance(x, int) and not isinstance(x, bool) for x in raw)
        ) else ([raw] if raw is not None else [])
        board = ctx.board
        if board is None:
            return tiles                                     # pas de canal d'elevation -> passe-tout
        frm = _tile_positions(self.from_tiles, ctx, board)    # `IterateTiles(<+0x20>.SelectUnit(...))`
        if not frm:
            return []                                        # boucle vide -> `return true` = obscurci
        # DIFFERE **PORTEUR**, classe MESUREE (CLAUDE.md) : en process frais,
        # `import engine.services.movement_query` charge DEJA `engine.entities.selectors.tiles`
        # (146 modules `engine.*`) -- un import au niveau module fermerait donc le cycle. Meme
        # regime que le `is_mechanical` de `MechanicalUnits` (`selectors/units.py`).
        # FORME B (module, pas symbole) : le binding de module n'est jamais gele.
        from ...services import movement_query as _mq
        from ...services.targeting_query import (BLOCKING_ELEVATION_DIFFERENCE,
                                                 OBSCURING_TYPE_ALL)
        out = []
        for t in tiles:
            tp = _entity_pos(t, board)                       # domaine MIXTE (id / (col,row) / unite)
            if tp is None:
                continue
            obscured = True
            for f in frm:
                if not _mq.get_tiles_obscuring_terrain(board, f, tp, OBSCURING_TYPE_ALL,
                                                       BLOCKING_ELEVATION_DIFFERENCE):
                    obscured = False                         # une ligne degagee suffit
                    break
            if not obscured:
                out.append(t)                                # DOMAINE PRESERVE (l'element source)
        return out


class FilterTilesIfCanAttackTargetTileFrom(TargetsSelector):
    """`IdunBattle.Entities.Selectors.FilterTilesIfCanAttackTargetTileFromSelector$$Select` --
    « garde les tuiles DEPUIS lesquelles `enemyOf` peut attaquer la tuile cible ». Mirror 1:1 :

        enemyOf    = this.<+0x18>.SelectUnit(entities, 0);      // vslot 7
        targetTile = this.<+0x20>.SelectTile(entities);         // vslot 0xc (SINGULIER)
        if (enemyOf == null || targetTile == null) return new List<Tile>();
        result = new List<Tile>();
        foreach (tile in this.<+0x28>.SelectTiles(entities))    // vslot 0xa
            if (query.GetAdjacentUnits(tile, friendsOf: null, enemiesOf: enemyOf,
                                       ignoreSteppables: false).Count == 0
                || TileExtensions.IsAdjacentTo(tile, targetTile))
                result.Add(tile);
        return result;

    LE PREMIER OPERANDE N'EST PAS UNE « RAISON D'INVALIDITE » -- c'est un CARDINAL. Le slot
    d'interface est `IBattleQuery` **0x7a**, etabli MECANIQUEMENT : les trois fermetures
    `RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass149_0$$u003CGetAdjacentUnitsu003Eb__0`
    / `...DisplayClass150_0...` / `...DisplayClass151_0...` -- le decorateur d'enregistrement, qui
    re-appelle la query interne PAR LE MEME SLOT -- portent respectivement `0x7a`, `0x7b`, `0x7c`,
    et sont toutes trois nommees `GetAdjacentUnits`. Le retour est donc une LISTE d'unites, et
    `iVar5` du decompile est son `ICollection.get_Count` (meme paire lue dans
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfTheKauyonAbility$$GetDynamicInvalidTargetReason`,
    qui appelle le MEME slot puis `ICollection.Remove(caster)` -- on ne retire pas un caster d'une
    liste de raisons).

    Semantique, une fois les deux operandes lus : une unite est empechee de TIRER quand elle est
    engagee au contact -> la tuile candidate n'est gardee que si `enemyOf` n'y aurait AUCUN ennemi
    adjacent, **ou** si elle est adjacente a la tuile cible (auquel cas c'est une attaque de MELEE
    qui devient possible). C'est ce SECOND bras -- le bras de RATTRAPAGE -- qui n'etait pas porte
    (#433-r4-r1).

    Les DEUX adjacences sont NATIVEMENT DIFFERENTES et le port ne les confond pas (#433-r1) :

      * `GetAdjacentUnits` -> `BattleQuery$$IterateAdjacentTiles` -> la liste d'adjacence STOCKEE
        (une tuile n'y est jamais sa propre voisine) + la porte d'elevation `|dElev| < 2`
        -> foyer `battle_query.is_adjacent` ;
      * `TileExtensions$$IsAdjacentTo` -> `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent`
        (surcharge SCALAIRE), qui porte le COURT-CIRCUIT D'IDENTITE `tile1 == tile2` -> foyer
        `battle_query.are_entities_adjacent`. Un port en `distance == 1` REFUSERAIT la paire
        identique que le natif accorde.

    FILTRE d'unites de `BattleQuery$$CountOrGetUnitsOnTiles`, verbatim : `GetUnit(tile)` (le
    `TileContentComponent`, donc N'IMPORTE QUEL pied resout en son unite -> `_occupants_by_tile`,
    #433-r3-r1a), puis `if (ignoreSteppables && IsSteppable) skip` (ici `ignoreSteppables == false`
    -> les steppables COMPTENT), `if (friendsOf != null && !IsFriend) skip` (ici null -> inerte),
    `if (enemiesOf != null && !IsEnemy(u, enemyOf)) skip`. Seul le CARDINAL est lu, donc l'ordre et
    la deduplication de l'`OrderedSet` natif ne sont pas observables.

    CONSOMMATEURS (xrefs de `IdunBattleLogic.Entities.DSLSelectors$$FilterTilesIfCanAttackTargetTileFrom`,
    cloture MECANIQUE : refcount 6 = 2 appels + 4 entrees DATA) -- **UN SEUL noeud DSL, DEUX abilities** :
      * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$PickTile`
        (1076), branche de REPLI uniquement ;
      * `IdunBattleLogic.Entities.Abilities.Active.Loki.WallOfMirrorsAbility$$GetPossibleTiles` (1186,
        NON PORTEE -- residu `#433-r4-r1-r1`).
    Les deux passent `(enemyOf = Caster()@DSLSelectors+0x48, target = Target()@+0x60)`.
    ⚠ `DSLSelectors$$AttackTilesForTarget` et `$$CanAddMultiTileUnit` ne construisent PAS ce
    selecteur-la : ils partagent seulement son `.ctor` (corps DEDUPLIQUE par IL2CPP) et ont leurs
    propres `AttackTilesForTargetSelector$$Select` / `CanAddMultiTileUnitTileSelector$$Select`,
    dont AUCUN n'appelle `IsAdjacentTo`.

    DOMAINE : les elements de `from_tiles` sont rendus TELS QUELS (ids de tuile aux call-sites
    portes), dans l'ordre source et sans dedup -- le natif accumule dans un `List<Tile>`, pas un
    `OrderedSet`. Un element non resolvable en position (`board` absent pour un id) est JETE."""
    def __init__(self, enemy_of: TargetsSelector, target: TargetsSelector,
                 from_tiles: TargetsSelector):
        self.enemy_of, self.target, self.from_tiles = enemy_of, target, from_tiles

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        attacker = resolve_unit(self.enemy_of, ctx)                       # vslot 7  SelectUnit
        target_tile = _select_tile(self.target.evaluate(ctx), board)      # vslot 0xc SelectTile
        if attacker is None or target_tile is None:
            return []                                    # `new List<Tile>()` -- selection vide
        elev = getattr(ctx, "elev_by_pos", None)
        neigh = battle_query.neigh_map(ctx)      # liste STOCKEE (#433-r4-r1-r4-r2), tri-etat
        team = attacker.get("team")
        # `GetUnitsOnTiles(..., enemiesOf: enemyOf, ...)` : occupation PAR PIED (TileContentComponent),
        # vivants seulement (un mort n'occupe plus sa tuile), filtre `IsEnemy` vs le referent.
        enemy_tiles = [p for p, u in _occupants_by_tile(ctx.units).items()
                       if u.get("team") != team]
        v = self.from_tiles.evaluate(ctx)                                 # vslot 0xa SelectTiles
        if v is None:
            items = []
        elif isinstance(v, (dict, int)) or (isinstance(v, tuple) and len(v) == 2
                                            and all(isinstance(x, int) for x in v)):
            items = [v]
        else:
            items = list(v)
        out: list = []
        for item in items:
            pos = _entity_pos(item, board)
            if pos is None:
                continue
            # `GetAdjacentUnits(tile, null, enemyOf, false).Count == 0`
            no_adjacent_enemy = not any(battle_query.is_adjacent(pos, p, elev, neigh)
                                        for p in enemy_tiles)
            # `|| TileExtensions.IsAdjacentTo(tile, targetTile)` -- LE BRAS DE RATTRAPAGE, sur la
            # primitive a court-circuit d'identite (surtout PAS `hexgeo.distance == 1`).
            if no_adjacent_enemy or battle_query.are_entities_adjacent(pos, target_tile, elev,
                                                                       neigh):
                out.append(item)
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


def _synapse_tiles(ctx, board, moving_team):
    """La BULLE SYNAPSE de l'equipe du mover, montee sur le substrat DSL -- troisieme branche de
    `FearOfTheUnseenPathfinder$$IsValidTeleportTile` (`Synapse_Effect` 0x41c + `GetSurroundingTiles
    (allie, 2, ..., includeCenter: true)`). `ctx.has_effect` absent -> `None` (NON MESURE), branche
    inerte. Meme mirror que `services.movement_query.synapse_tiles_for`, autre substrat."""
    he = getattr(ctx, "has_effect", None)
    if he is None or board is None or moving_team is None:
        return None
    want = int(EffectType.Synapse_Effect)
    centers = [_pos(o) for o in ctx.units
               if _is_alive(o) and o.get("team") == moving_team and he(o, want)]
    centers = [c for c in centers if c is not None]
    if not centers:
        return set()
    return {int(t) for t in board.by_id
            if any(hexgeo.distance(board.coord(int(t)), c) <= 2 for c in centers)}


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
        # ⚠ PAR LE FOYER `_feet`, jamais par une recopie locale : ce site recopiait la regle
        # (`feet` sinon `[_pos]`) SANS normaliser la forme des tuiles, donc il levait `KeyError: 0`
        # des que la scene venait de la face DECISION -- `decisionView.units[].feet` porte des
        # dicts `{"col","row"}` depuis le capteur `#419-r1-tr10-r2`. Meme faute, meme jour, que
        # `dsl/base.py::_feet` ; elle est fermee AU FOYER pour que le prochain canal n'ait qu'un
        # seul site a satisfaire.
        occ: dict = {}
        for other in ctx.units:
            if not _is_alive(other):
                continue
            for f in _feet(other):
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
            teleport_target_tiles=None,
            synapse_tiles=_synapse_tiles(ctx, board, u.get("team")))
        # `RemoveAll(t => !IsMovableTile(..., ignoreUnitsOnTiles))` : sans `ignoreUnitsOnTiles` le
        # natif ne garde que les tuiles LIBRES (`IsFreeTile`), depart compris — c'est le stop_set.
        #
        # ⚠ AVEC `ignoreUnitsOnTiles`, LA TUILE DE DEPART RESTE DEHORS (#287-r5-r1). Le port et le
        # natif ne mettent pas la meme chose sous le mot « visited » : cote port c'est l'ensemble
        # TRAVERSE (depart inclus, cf. `walk_pathfinder.get_movable_positions`, « le depart n'est
        # jamais filtre »), cote natif `GetReachableTiles` = `BasePathfinder$$FindReachableTiles` =
        # `ListPool(IterateReachableTiles(start, depth, unit))`, et
        # `BasePathfinder.u003CIterateReachableTilesu003Ed__12$$MoveNext` ne l'EMET PAS : sa branche
        # `depth == 1` rend `GetValidNeighbours(start, unit, null)` et rien d'autre, et sa branche
        # generale amorce `visited` VIDE en ne mettant `start` que dans la FILE (le niveau 0).
        # C'est donc l'etage PATHFINDING qui l'exclut, pas ce filtre-ci -- d'ou la soustraction ici.
        # Tant que `ignore_units_on_tiles` valait `False` a TOUS les call-sites portes, l'ecart etait
        # INOBSERVABLE (le stop_set retire le depart de toute facon) ; `TheQuickeningAbility$$
        # GetDynamicInvalidTargetReason` est le premier a poser ce booleen, et il l'a rendu visible :
        # sur `MC1_67`, le natif refuse la tuile du caster par `TargetIsInRange` la ou le port
        # l'acceptait (mesure `probe_287r5r1_charge_tiles_live.py`).
        return sorted((visited - {start}) if self.ignore_units_on_tiles else stop)


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
