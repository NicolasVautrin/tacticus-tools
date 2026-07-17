"""Noeuds SELECTEUR du DSL = famille `TargetsSelector.Select` (kind S) : selecteurs d'unites, de
tuiles (domaine TILE = ids), et accesseurs de tuile/entite/sujet.

Mirror du namespace natif `IdunBattle.Entities.Selectors` : les concrets vivent ici, a cote de leurs
freres `entities/{abilities,triggers,formulas,behaviours,effects}` ; la base `TargetsSelector`
(= `IdunBattle.DSL`) reste dans `dsl/base.py`. Construits via la facade `DSLFactory` (`dsl/nodes.py`).
Les selecteurs de TUILES lisent `ctx.board` (entities/pathfinding : `neighbours`/`id_at`/`walkable`)."""
from __future__ import annotations

from dataclasses import replace

import hexgeo

from ..dsl.base import (TargetsSelector, Const, _pos, _within, _is_alive, _units_of, _effect_field,
                        resolve_unit)


class SurroundingUnits(TargetsSelector):
    """`DSLFactory.SurroundingUnits(center, radius) @180dfcb70` = `Units(SurroundingTiles(center, radius))`
    = unités à distance hex <= radius du centre, centre exclu."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector):
        self.center, self.radius = center, radius

    def select(self, ctx):
        return _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))


class AdjacentEnemies(TargetsSelector):
    """`DSLFactory.AdjacentEnemies(caster) @180de80c0` = `Enemies(Units(AdjacentTiles(caster)) - {caster})`
    = ennemis (team != caster) à dist <= radius du caster, self exclu."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector | None = None):
        self.center, self.radius = center, radius or Const(1)

    def select(self, ctx):
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))
        ct = (ctx.caster or {}).get("team")
        return [u for u in ring if u.get("team") != ct]


class AdjacentUnits(TargetsSelector):
    """`DSLFactory.AdjacentUnits(target, radius, mask) @180de8320` = `Units(AdjacentTiles(target)) - {target}`
    = TOUTES les unités (AUCUN filtre d'équipe) à distance hex <= radius de `target`, target exclu. ⚠ à la
    DIFFÉRENCE de `AdjacentEnemies` (filtre team != caster) et de `Enemies(...)` (wrapper `UnitsByTeamSelector`),
    ce sélecteur ne filtre PAS l'équipe → inclut les ALLIÉS du caster (et le caster) s'ils sont adjacents à la
    cible = FRIENDLY-FIRE. Le volet SPLASH de Stikkbomb (@18120c180) passe ce sélecteur BRUT (sans wrapper
    `Enemies(...)`, contraste PlasmaGrenade/ScythingTalons) — corroboré par l'i2 (« units in hexes adjacent »
    vs « enemy units » des autres). `_within` exclut déjà le centre (target, dist 0). Mirror de `AdjacentEnemies`
    SANS le filtre team."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector | None = None):
        self.center, self.radius = center, radius or Const(1)

    def select(self, ctx):
        return _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))


class Enemies(TargetsSelector):
    """`DSLFactory.Enemies` : filtre → équipe != celle du caster."""
    def __init__(self, inner: TargetsSelector):
        self.inner = inner

    def select(self, ctx):
        ct = (ctx.caster or {}).get("team")
        return [u for u in self.inner.evaluate(ctx) if u.get("team") != ct]


class Damageable(TargetsSelector):
    """`DSLFactory.Damageable` : filtre → unités vivantes ciblables (PV > 0)."""
    def __init__(self, inner: TargetsSelector):
        self.inner = inner

    def select(self, ctx):
        return [u for u in self.inner.evaluate(ctx)
                if bool(u.get("alive", True)) and (u.get("hp") or 0) > 0]


class And(TargetsSelector):
    """`TargetsSelector.op_BitwiseAnd` : intersection par id."""
    def __init__(self, a: TargetsSelector, b: TargetsSelector):
        self.a, self.b = a, b

    def select(self, ctx):
        bset = {u.get("id") for u in self.b.evaluate(ctx)}
        return [u for u in self.a.evaluate(ctx) if u.get("id") in bset]


class Sub(TargetsSelector):
    """`TargetsSelector.op_Subtraction` : a \\ b par id."""
    def __init__(self, a: TargetsSelector, b: TargetsSelector):
        self.a, self.b = a, b

    def select(self, ctx):
        bset = {u.get("id") for u in self.b.evaluate(ctx)}
        return [u for u in self.a.evaluate(ctx) if u.get("id") not in bset]


class Union(TargetsSelector):
    """`TargetsSelector.op_Addition` : UNION (concaténation) de deux sélecteurs d'unités — mirror du
    `op_Addition(Self, UnitsFromFaction(...))` de `SpiritLeechAbility.GetHealTargets @18120a1e0`. Concatène
    `a` puis `b`, chaque opérande normalisé en liste (`_units_of` : un dict comme `Caster()` → `[dict]`).
    Ici les deux volets sont DISJOINTS (le `Self` du 1er volet est exclu de l'anneau adjacent du 2e via
    `_within` d>0) → concat SANS doublon = fidèle à l'imperatif (`[caster] + adjacents`)."""
    def __init__(self, a: TargetsSelector, b: TargetsSelector):
        self.a, self.b = a, b

    def select(self, ctx):
        return _units_of(self.a, ctx) + _units_of(self.b, ctx)


class UnitsFromFaction(TargetsSelector):
    """`DSLFactory.UnitsFromFaction(source, factionName) @...` : garde les unités de `source` dont la
    faction gameconfig (`FactionId`) == `faction`. Le natif passe `System.Enum.ToString(UnitFaction)` = le
    NOM de la faction (ex. `0xc`=12 → `"Tyranids"`). Résolution via `ctx.faction_of` (callback par-unité,
    même pattern que `has_trait`/`get_stat`, fourni par la couche runner) ; None → faction inconnue → unité
    écartée. Utilisé par `SpiritLeech.GetHealTargets` (allies Tyranids adjacents)."""
    def __init__(self, source: TargetsSelector, faction):
        self.source, self.faction = source, faction

    def select(self, ctx):
        fo = ctx.faction_of
        if fo is None:
            return []
        return [u for u in self.source.evaluate(ctx) if fo(u) == self.faction]


class UnitSet(TargetsSelector):
    """Feuille = un ensemble d'unités explicite (ex. `{mainTarget}` pour la soustraction AoE)."""
    def __init__(self, units: list):
        self.units = units

    def select(self, ctx):
        return list(self.units)


class Filter(TargetsSelector):
    """`DSLFactory.Filter(source, predicate) @180def870` → thunk `FromTrigger @180df00e0` →
    `FromTriggerSelector.Select @180eebaa0` : énumère `source` et, POUR CHAQUE élément, LIE l'élément
    au slot sujet du contexte (mirror du `0x20`→`ability+0x180` natif) puis évalue le prédicat bool
    contre ce contexte ; garde l'élément si le prédicat est vrai. Preuve binding : `TheBetrayer
    GetPreferredAttackTargets @1811a58a0` = `Filter(src, NOT(HasTrait(subject, 0xd)))` — le prédicat
    lit son sujet via `Subject` (= `ctx.subject`). Retour list.
    (`FilterContinuous @180def7b0` = même construction + flag short-circuit ; `FilterByDirection
    @180def700` = classe distincte directionnelle — hors batch, à porter à la demande.)"""
    def __init__(self, source: TargetsSelector, predicate: TargetsSelector):
        self.source, self.predicate = source, predicate

    def select(self, ctx):
        out = []
        for item in self.source.evaluate(ctx):
            if self.predicate.evaluate(replace(ctx, subject=item)):
                out.append(item)
        return out


class UnitsDirectlyBehind(TargetsSelector):
    """`DSLFactory.UnitsDirectlyBehind @180dff5e0` — cibles secondaires « derrière la cible »
    (PlasmaCannon…). Transcription EXACTE de la construction native :
        ring    = SurroundingTiles(target, 1, 1) − Tiles(target)          # anneau R1 de la CIBLE
        cands   = Enemies(caster, Units(ring))                            # ennemis du caster dessus
        sameElv = TilesOnSameElevationSelector(target, cands, 1)          # même élévation que la cible
        behind  = FromTrigger(cands, dist(caster, cand) >= dist(caster, target))   # côté OPPOSÉ au caster
    (Les ctors de nœuds gshared sont MISLABELÉS par ghidra — sémantique lue par STRUCTURE : la paire
    SortReverse(caster)/SortReverse(x) + AmountIsEqualOrGreater = comparaison de DISTANCES au caster.)
    `dist` = distance hex ; caster = `ctx.caster_pos` (tuile d'attaque balayée). Élévation :
    `TilesOnSameElevationSelector.Select @180efa8a0` garde si `GetElevationDifference(cand, target)
    <= maxDiff` (ctor +0x28 = 1 ici) → TOLÉRANCE ±1, pas une égalité stricte (prouvé step-11 :
    78 elev1 derrière 82 elev2 inclus par le natif). Dégradé no-op sans `ctx.elev_by_pos`."""

    def select(self, ctx):
        tpos = _pos(ctx.target)
        cpos = ctx.caster_pos or _pos(ctx.caster)
        if tpos is None or cpos is None:
            return []
        ct = (ctx.caster or {}).get("team")
        tid = (ctx.target or {}).get("id")
        d_ct = hexgeo.distance(cpos, tpos)
        out = []
        for u in ctx.units:
            p = _pos(u)
            if p is None or u.get("id") == tid or u.get("team") == ct:
                continue
            if hexgeo.distance(p, tpos) != 1:                      # anneau R1 de la cible
                continue
            if ctx.elev_by_pos is not None:                        # TilesOnSameElevationSelector (maxDiff=1)
                et, ec = ctx.elev_by_pos.get(tpos), ctx.elev_by_pos.get(p)
                if et is not None and ec is not None and abs(et - ec) > 1:
                    continue
            if hexgeo.distance(cpos, p) >= d_ct:                   # « derrière » = au moins aussi loin
                out.append(u)
        return out


class Friends(TargetsSelector):
    """`DSLFactory.Friends(inner) @180df0040` → `UnitsByTeamSelector` flag=1 (symétrique exact d'`Enemies`
    flag=0) : garde les unités du sélecteur ALLIÉES au référent (référent = caster standard)."""
    def __init__(self, inner: TargetsSelector):
        self.inner = inner

    def select(self, ctx):
        ct = (ctx.caster or {}).get("team")
        return [u for u in self.inner.evaluate(ctx) if u.get("team") == ct]


class Units(TargetsSelector):
    """`DSLFactory.Units(tiles) @180e01340` → `UnitsOnTilesSelector` : unités DEBOUT sur les tuiles du
    sélecteur source (`tiles` évalue → liste de positions). Généralise l'inline de SurroundingUnits.
    (Mode d'occupation main/steppable = raffinement inerte offline : 1 unité par tuile.)"""
    def __init__(self, tiles: TargetsSelector):
        self.tiles = tiles

    def select(self, ctx):
        tset = set(self.tiles.evaluate(ctx))
        return [u for u in ctx.units if _pos(u) in tset]


class Tiles(TargetsSelector):
    """`DSLFactory.Tiles(units) @180dfdc60` → `UnitsMainTilesSelector.Select @180f02150` (ctor mislabelé
    "SortReverse", singleton distinct DAT_183278e98) : unités → leur MainTile. Retour list[position]."""
    def __init__(self, units: TargetsSelector):
        self.units = units

    def select(self, ctx):
        return [p for p in (_pos(u) for u in self.units.evaluate(ctx)) if p is not None]


class First(TargetsSelector):
    """`DSLFactory.First(source[, index]) @180defae0` → `PickAtIndexSelector.Select @180ef02e0` :
    l'élément à `index` (défaut 0) de la liste source (ordre TEL QUEL), `[]` si hors borne. Retour list
    de 0/1 élément (PAS un élément nu). S'appuie sur un tri préalable si l'appelant en pose un."""
    def __init__(self, source: TargetsSelector, index: int = 0):
        self.source, self.index = source, index

    def select(self, ctx):
        lst = self.source.evaluate(ctx)
        return [lst[self.index]] if 0 <= self.index < len(lst) else []


class Unique(TargetsSelector):
    """`DSLFactory.Unique(source) @180dfeec0` → LINQ Distinct : dedup de la source (ordre de 1re
    apparition préservé), clé = identité d'entité (== par id). [structure PROUVÉE, clé DÉDUITE du nom]."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        seen, out = set(), []
        for u in self.source.evaluate(ctx):
            k = u.get("id")
            if k is None or k not in seen:
                if k is not None:
                    seen.add(k)
                out.append(u)
        return out


class UnitsWithTrait(TargetsSelector):
    """`DSLFactory.UnitsWithTrait(source, traitId) @180e00b10` → `UnitsWithFlagSelector` flag=1 : garde
    les unités où `HasFlag(unit, traitId)` (même primitive que HasFlag). `ctx.has_trait` teste le trait ;
    défaut None → trait ABSENT (convention HasFlag) → set vide."""
    def __init__(self, source: TargetsSelector, trait):
        self.source, self.trait = source, trait

    def select(self, ctx):
        ht = ctx.has_trait or (lambda u, t: False)
        return [u for u in self.source.evaluate(ctx) if ht(u, self.trait)]


class UnitsWithoutTrait(TargetsSelector):
    """`DSLFactory.UnitsWithoutTrait(source, traitId) @180e01040` → `UnitsWithFlagSelector` flag=0 : garde
    les unités où `HasFlag(unit, traitId)` est FAUX. Défaut `ctx.has_trait` None → trait absent → garde
    TOUT."""
    def __init__(self, source: TargetsSelector, trait):
        self.source, self.trait = source, trait

    def select(self, ctx):
        ht = ctx.has_trait or (lambda u, t: False)
        return [u for u in self.source.evaluate(ctx) if not ht(u, self.trait)]


class AdjacentFriends(TargetsSelector):
    """`DSLFactory.AdjacentFriends(caster) @180de81d0` = symétrique d'`AdjacentEnemies` (finit par
    `Friends`) : alliés (team == caster) à dist <= radius du caster, self exclu."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector | None = None):
        self.center, self.radius = center, radius or Const(1)

    def select(self, ctx):
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))
        ct = (ctx.caster or {}).get("team")
        return [u for u in ring if u.get("team") == ct]


class SurroundingEnemies(TargetsSelector):
    """`DSLFactory.SurroundingEnemies(center, radius) @180dfc570` = `Enemies(SurroundingUnits(center,
    radius))` : ennemis (team != caster) à dist <= radius du centre, centre exclu."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector):
        self.center, self.radius = center, radius

    def select(self, ctx):
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))
        ct = (ctx.caster or {}).get("team")
        return [u for u in ring if u.get("team") != ct]


class SurroundingFriends(TargetsSelector):
    """`DSLFactory.SurroundingFriends(center, radius) @180dfc640` = `Friends(SurroundingUnits(center,
    radius))` : alliés (team == caster) à dist <= radius du centre, centre exclu."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector):
        self.center, self.radius = center, radius

    def select(self, ctx):
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))
        ct = (ctx.caster or {}).get("team")
        return [u for u in ring if u.get("team") == ct]


class SortByFormula(TargetsSelector):
    """`DSLFactory.SortByFormula(source, formula[, ascending]) @180dfb0a0` → `SortByFormulaSelector.Select
    @180ef3010` : trie la source par `formula` évaluée PAR ÉLÉMENT (binding `subject`, comme Filter).
    ⚠ flag natif : 0 (défaut) → DESCENDANT, 1 → ASCENDANT. Tri STABLE (mergesort .NET ≡ `sorted`)."""
    def __init__(self, source: TargetsSelector, formula: TargetsSelector, ascending: bool = False):
        self.source, self.formula, self.ascending = source, formula, ascending

    def select(self, ctx):
        lst = list(self.source.evaluate(ctx))
        return sorted(lst, key=lambda u: self.formula.evaluate(replace(ctx, subject=u)),
                      reverse=not self.ascending)


class SortByDistance(TargetsSelector):
    """`DSLFactory.SortByDistance(source, refPoint) @180dfb020` → `SortByDistanceSelector.Select
    @180ef2ce0` : trie la source par distance hex CROISSANTE au `refPoint` (arg2 = sélecteur de
    position/unité, PAS forcément le caster). ASCENDANT, tri STABLE."""
    def __init__(self, source: TargetsSelector, ref_point: TargetsSelector):
        self.source, self.ref_point = source, ref_point

    def select(self, ctx):
        rp = self.ref_point.evaluate(ctx)
        if isinstance(rp, dict):
            rp = _pos(rp)
        lst = list(self.source.evaluate(ctx))
        return sorted(lst, key=lambda u: hexgeo.distance(_pos(u), rp) if _pos(u) is not None else (1 << 30))


class Alive(TargetsSelector):
    """`DSLFactory.Alive(source) @180de8390` = `Filter(source, IsAlive)` : garde les unités vivantes
    (alive & hp>0). Équivaut à `Damageable`. Retour list."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        return [u for u in self.source.evaluate(ctx) if _is_alive(u)]


# --- Selecteurs de TUILES (domaine TILE = ids de tuile ; lisent ctx.board). Pont unit->tile
#     (`AdjacentTiles`) et tile->tile (`CanAddUnit`/`TileUnique`/`TileIntersect`). board None -> []. ---

class Caster(TargetsSelector):
    """L'unite CASTER (`caster@+0x168`, ref passee aux selecteurs). Accesseur unit-domain =
    `ctx.caster` (dict|None)."""
    def select(self, ctx):
        return ctx.caster


class AllUnits(TargetsSelector):
    """`DSLFactory.AllUnits @180de85f0` -> `AllAliveMachinesSelector @180ee0080` : toutes les unites
    VIVANTES de la bataille. Le primitif DSL `AllUnits` est **la variante ALIVE** (un `AllUnitsSelector`
    natif distinct existe pour l'ensemble brut, mais `DSLFactory.AllUnits` ne l'utilise PAS). Source des
    filtres `Enemies`/`Friends` du port (le natif `Enemies(caster, ...)` folde la source ; cote port on
    fournit `AllUnits` a l'inner). **Le filtre alive est ICI** (mirror de AllAliveMachines), PAS via un
    noeud `Damageable` en aval -> cf. confront LIVE #200 tracer-v2 + fix #202 (le natif GetSpawnTileSelector
    n'a AUCUN Damageable ; c'est `AllUnits`=alive qui exclut les morts)."""
    def select(self, ctx):
        return [u for u in ctx.units
                if bool(u.get("alive", True)) and (u.get("hp") or 0) > 0]


class Children(TargetsSelector):
    """`DSLFactory.Children @180debed0` = `Entities.Selectors.AllAliveMachinesSelector` (@180ee00d0) SCOPÉ
    aux enfants (summons) produits par CE cast (natif `factory+0x148`). Port = l'accumulateur `ctx.children`
    (alimenté par la feuille `SpawnUnit`, `runner/abilities/behaviours.py`). ⚠ Le filtre `AllAlive` est un
    no-op offline pour l'on-appearance de CE cast (les summons survivent à leur apparition). cf.
    `getemruntz_taunt_tree` (loki.py)."""
    def select(self, ctx):
        return list(getattr(ctx, "children", None) or [])


class LastUnitAttackedBy(TargetsSelector):
    """`DSLFactory.LastUnitAttackedBy @180df5ee0` = `Entities.Selectors.LastUnitAttackedBySelector`
    (@180eed130) : dernière unité attaquée par `unit`. Port : le dict FRAIS (état POST-attaque, relu par la
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
    voisinage NATIF `ctx.board.neighbours(tile_de_l_unite)`. `source` = TargetsSelector unit-domain (unite
    seule ou liste, normalise par `_units_of`). Retour list[int] (tile ids). board None -> []."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        out: list = []
        for u in _units_of(self.source, ctx):
            p = _pos(u)
            if p is None:
                continue
            tid = board.id_at(p[0], p[1])
            if tid is None:
                continue
            out.extend(board.neighbours(tid))
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
    `_occupied_tiles(state)` imperatif). Ordre de `source` preserve. board None -> []."""
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
            p = _pos(u)
            if p is None:
                continue
            t = board.id_at(p[0], p[1])
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


# --- Accesseurs SELECTEUR (mirror `DSLFactory.X` -> tuiles/entites/sujet natifs ; kind S). ---

class CasterTile(TargetsSelector):
    """Tuile du caster (`UnitPosition.MainTile` du casterPosition passé par le generator) — pour une
    décision balayée c'est la TUILE D'ATTAQUE candidate (`ctx.caster_pos`), pas la position courante."""
    def select(self, ctx):
        return ctx.caster_pos or _pos(ctx.caster)


class TargetTile(TargetsSelector):
    """Tuile de la cible principale (`MainTile` de la cible) — centre de `SurroundingUnits`."""
    def select(self, ctx):
        return _pos(ctx.target)


class OwnerTile(TargetsSelector):
    """Tuile COURANTE (réelle) de l'owner/caster — position du composant entité, PAS la tuile d'attaque
    balayée. `HarvesterOfSoulsAbility.GetSurroundingUnits @1811e76a0` ancre son `SurroundingUnits(sel@0x160,
    range)` sur ce sélecteur (sel@0x160 = OWNER : cf. `StatAmount(@0x160,Health)`=maxHP caster dans
    `DakkaDakkaDakka.GetHealthToLose @1811d09a0`, `HasFlag(@0x160)` du caster dans `Harvester.GetHits`).
    La fonction native ne reçoit AUCUN `casterPosition` (elle ne prend que l'ability) -> sel@0x160 résout
    la position LIVE de l'owner (non déplacé pendant la prédiction), != `CasterTile` (= `ctx.caster_pos`,
    la tuile d'attaque post-move). Preuve ground-truth seed777 step-17 : AoE ancré sur (5,6)=owner-réel
    (et non (4,3)=tuile d'attaque) reproduit les 4 sets natifs (cf. active_ability.HarvesterOfSoulsAbility)."""
    def select(self, ctx):
        return _pos(ctx.caster)


class Subject(TargetsSelector):
    """Élément COURANT lié par un `Filter` (mirror du sélecteur-sujet natif `ability+0x180` =
    OriginalTarget). Les prédicats sous un `Filter` lisent leur sujet ici ; hors Filter → `ctx.subject`
    (None par défaut)."""
    def select(self, ctx):
        return ctx.subject


class Target(TargetsSelector):
    """Cible principale de l'ability (l'UNITÉ, pas sa tuile — cf. `TargetTile`). Mirror du contexte
    d'entité-cible natif (`AbilityEntities` slot cible = `factory+0x178`) : les behaviours d'ability
    (`AttackWithAttackDamage`, `AddEffect`) ancrés sur la cible lisent `ctx.target` ici. None si l'ability
    est sans cible (auto/tuile)."""
    def select(self, ctx):
        return ctx.target


class Cache(TargetsSelector):
    """`DSLFactory.Cache(source) @180deb0d0` → `CacheSelector.Select @180ee35f0` : **MÉMOÏSE** le résultat
    du sous-arbre. Décompilé : 1re éval calcule (`source.evaluate` + `ToList`) et STOCKE dans le slot
    `+0x28` (mode slot unique, flag `+0x20`==0) ou un dict keyé par le contexte (`+0x30`) ; évals suivantes
    renvoient le CACHE. **PAS un pass-through** : la mémoïsation est OBSERVABLE quand l'état mute entre deux
    consommateurs — GetEmRuntz partage `Cache(GetSpawnTileSelector)` entre `Spawn` (capture les tuiles
    LIBRES PRÉ-spawn) et `PerformAIAttackFromCurrentPosition` (relit ces MÊMES tuiles POST-spawn pour y
    trouver les grots) ; sans mémoïsation, `CanAddUnit` recalculé exclurait les tuiles désormais occupées
    → zéro grot trouvé. Portée = l'instance du nœud ; l'arbre étant rebâti par cast (`getemruntz_tree()`),
    le cache est **par-cast**. Slot unique (suffisant pour GetEmRuntz : même contexte top-level aux deux
    évals ; la variante dict-keyée par contexte reste à porter si un `Cache` est éval sous un `Foreach`)."""
    def __init__(self, source):
        self.source = source
        self._has = False
        self._cached = None

    def select(self, ctx):
        if not self._has:                            # slot +0x28 : miss -> calcule + stocke
            self._cached = self.source.evaluate(ctx)
            self._has = True
        return self._cached                          # hit -> renvoie le cache (mémoïsation observable)


class Entity(TargetsSelector):
    """`DSLFactory.Entity(ref) @180def540` : résout la RÉFÉRENCE passée en argument (rôle
    caster/target/subject) en ENTITÉ. Wrapper fin — l'opérande (souvent un nœud rôle, ex. `Subject`)
    évalue déjà l'entité."""
    def __init__(self, ref):
        self.ref = ref

    def select(self, ctx):
        return self.ref.evaluate(ctx)


class Nothing(TargetsSelector):
    """`DSLFactory.Nothing @180df7870` : sélecteur VIDE (retourne `[]`). Classe DISTINCTE de `Null`."""
    def select(self, ctx):
        return []


class Null(TargetsSelector):
    """`DSLFactory.Null @180df74f0` : entité/valeur NULLE (retourne `None`). Même classe qu'`Entity` avec
    arg null ; distinct de `Nothing` (ensemble vide)."""
    def select(self, ctx):
        return None


class EffectSource(TargetsSelector):
    """`DSLFactory.EffectSource @180deeb90` : entité SOURCE de l'effet COURANT (`ctx.effect`). NON captable
    hors application d'effet → None si `ctx.effect` absent."""
    def select(self, ctx):
        return _effect_field(ctx.effect, "source", None)


class EffectFromOwner(TargetsSelector):
    """`DSLFactory.EffectFromOwner(effectType) @180deea50` → `EffectWithTypeSelector @180ee7f30` : effets
    du type possédés par l'owner. NON captable offline (effets par unité absents du state) → `[]` défaut."""
    def __init__(self, effect_type):
        self.effect_type = effect_type

    def select(self, ctx):
        return []


def get_spawn_tile_selector() -> TargetsSelector:
    """`GetEmRuntzAbility.GetSpawnTileSelector @1811e26b0` (mirror 1:1, confirme LIVE #200 tracer-v2) =
        op_BitwiseAnd( CanAddUnit(AdjacentTiles(caster)),
                       Unique(AdjacentTiles( UnitsWithoutTrait(Enemies(AllUnits), 0x1b) )) )
    = ids de tuiles LIBRES (walkable + inoccupees) adjacentes au CASTER **ET** adjacentes a un
    ENNEMI vivant non-`Steppable` (0x1b=27, cf. `UnitTrait.Steppable` #146/#158 ; `UnitsWithoutTrait`
    = filtre TRAIT). **AUCUN noeud `Damageable`** : le natif n'en a pas (decompile + capture live
    tracer-v2 concordent) — l'exclusion des morts est portee par `AllUnits`=`AllAliveMachinesSelector`
    (#202). Enemies/UnitsWithoutTrait = meme module."""
    from .traits.unit_trait import UnitTrait
    caster_free = CanAddUnit(AdjacentTiles(Caster()))
    enemies = UnitsWithoutTrait(Enemies(AllUnits()), int(UnitTrait.Steppable))
    enemy_adj = TileUnique(AdjacentTiles(enemies))
    return TileIntersect(caster_free, enemy_adj)
