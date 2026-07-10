"""Noeuds SELECTEURS / geometrie (retour list) du DSL (cf. base.py)."""
from __future__ import annotations

from dataclasses import replace

import hexgeo

from .base import Node, Const, _pos, _within, _is_alive


class SurroundingUnits(Node):
    """`DSLFactory.SurroundingUnits(center, radius) @180dfcb70` = `Units(SurroundingTiles(center, radius))`
    = unités à distance hex <= radius du centre, centre exclu."""
    def __init__(self, center: Node, radius: Node):
        self.center, self.radius = center, radius

    def evaluate(self, ctx):
        return _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))


class AdjacentEnemies(Node):
    """`DSLFactory.AdjacentEnemies(caster) @180de80c0` = `Enemies(Units(AdjacentTiles(caster)) - {caster})`
    = ennemis (team != caster) à dist <= radius du caster, self exclu."""
    def __init__(self, center: Node, radius: Node | None = None):
        self.center, self.radius = center, radius or Const(1)

    def evaluate(self, ctx):
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))
        ct = (ctx.caster or {}).get("team")
        return [u for u in ring if u.get("team") != ct]


class Enemies(Node):
    """`DSLFactory.Enemies` : filtre → équipe != celle du caster."""
    def __init__(self, inner: Node):
        self.inner = inner

    def evaluate(self, ctx):
        ct = (ctx.caster or {}).get("team")
        return [u for u in self.inner.evaluate(ctx) if u.get("team") != ct]


class Damageable(Node):
    """`DSLFactory.Damageable` : filtre → unités vivantes ciblables (PV > 0)."""
    def __init__(self, inner: Node):
        self.inner = inner

    def evaluate(self, ctx):
        return [u for u in self.inner.evaluate(ctx)
                if bool(u.get("alive", True)) and (u.get("hp") or 0) > 0]


class And(Node):
    """`TargetsSelector.op_BitwiseAnd` : intersection par id."""
    def __init__(self, a: Node, b: Node):
        self.a, self.b = a, b

    def evaluate(self, ctx):
        bset = {u.get("id") for u in self.b.evaluate(ctx)}
        return [u for u in self.a.evaluate(ctx) if u.get("id") in bset]


class Sub(Node):
    """`TargetsSelector.op_Subtraction` : a \\ b par id."""
    def __init__(self, a: Node, b: Node):
        self.a, self.b = a, b

    def evaluate(self, ctx):
        bset = {u.get("id") for u in self.b.evaluate(ctx)}
        return [u for u in self.a.evaluate(ctx) if u.get("id") not in bset]


class UnitSet(Node):
    """Feuille = un ensemble d'unités explicite (ex. `{mainTarget}` pour la soustraction AoE)."""
    def __init__(self, units: list):
        self.units = units

    def evaluate(self, ctx):
        return list(self.units)


class Filter(Node):
    """`DSLFactory.Filter(source, predicate) @180def870` → thunk `FromTrigger @180df00e0` →
    `FromTriggerSelector.Select @180eebaa0` : énumère `source` et, POUR CHAQUE élément, LIE l'élément
    au slot sujet du contexte (mirror du `0x20`→`ability+0x180` natif) puis évalue le prédicat bool
    contre ce contexte ; garde l'élément si le prédicat est vrai. Preuve binding : `TheBetrayer
    GetPreferredAttackTargets @1811a58a0` = `Filter(src, NOT(HasTrait(subject, 0xd)))` — le prédicat
    lit son sujet via `Subject` (= `ctx.subject`). Retour list.
    (`FilterContinuous @180def7b0` = même construction + flag short-circuit ; `FilterByDirection
    @180def700` = classe distincte directionnelle — hors batch, à porter à la demande.)"""
    def __init__(self, source: Node, predicate: Node):
        self.source, self.predicate = source, predicate

    def evaluate(self, ctx):
        out = []
        for item in self.source.evaluate(ctx):
            if self.predicate.evaluate(replace(ctx, subject=item)):
                out.append(item)
        return out


class UnitsDirectlyBehind(Node):
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

    def evaluate(self, ctx):
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


class Friends(Node):
    """`DSLFactory.Friends(inner) @180df0040` → `UnitsByTeamSelector` flag=1 (symétrique exact d'`Enemies`
    flag=0) : garde les unités du sélecteur ALLIÉES au référent (référent = caster standard)."""
    def __init__(self, inner: Node):
        self.inner = inner

    def evaluate(self, ctx):
        ct = (ctx.caster or {}).get("team")
        return [u for u in self.inner.evaluate(ctx) if u.get("team") == ct]


class Units(Node):
    """`DSLFactory.Units(tiles) @180e01340` → `UnitsOnTilesSelector` : unités DEBOUT sur les tuiles du
    sélecteur source (`tiles` évalue → liste de positions). Généralise l'inline de SurroundingUnits.
    (Mode d'occupation main/steppable = raffinement inerte offline : 1 unité par tuile.)"""
    def __init__(self, tiles: Node):
        self.tiles = tiles

    def evaluate(self, ctx):
        tset = set(self.tiles.evaluate(ctx))
        return [u for u in ctx.units if _pos(u) in tset]


class Tiles(Node):
    """`DSLFactory.Tiles(units) @180dfdc60` → `UnitsMainTilesSelector.Select @180f02150` (ctor mislabelé
    "SortReverse", singleton distinct DAT_183278e98) : unités → leur MainTile. Retour list[position]."""
    def __init__(self, units: Node):
        self.units = units

    def evaluate(self, ctx):
        return [p for p in (_pos(u) for u in self.units.evaluate(ctx)) if p is not None]


class First(Node):
    """`DSLFactory.First(source[, index]) @180defae0` → `PickAtIndexSelector.Select @180ef02e0` :
    l'élément à `index` (défaut 0) de la liste source (ordre TEL QUEL), `[]` si hors borne. Retour list
    de 0/1 élément (PAS un élément nu). S'appuie sur un tri préalable si l'appelant en pose un."""
    def __init__(self, source: Node, index: int = 0):
        self.source, self.index = source, index

    def evaluate(self, ctx):
        lst = self.source.evaluate(ctx)
        return [lst[self.index]] if 0 <= self.index < len(lst) else []


class Unique(Node):
    """`DSLFactory.Unique(source) @180dfeec0` → LINQ Distinct : dedup de la source (ordre de 1re
    apparition préservé), clé = identité d'entité (== par id). [structure PROUVÉE, clé DÉDUITE du nom]."""
    def __init__(self, source: Node):
        self.source = source

    def evaluate(self, ctx):
        seen, out = set(), []
        for u in self.source.evaluate(ctx):
            k = u.get("id")
            if k is None or k not in seen:
                if k is not None:
                    seen.add(k)
                out.append(u)
        return out


class UnitsWithTrait(Node):
    """`DSLFactory.UnitsWithTrait(source, traitId) @180e00b10` → `UnitsWithFlagSelector` flag=1 : garde
    les unités où `HasFlag(unit, traitId)` (même primitive que HasFlag). `ctx.has_trait` teste le trait ;
    défaut None → trait ABSENT (convention HasFlag) → set vide."""
    def __init__(self, source: Node, trait):
        self.source, self.trait = source, trait

    def evaluate(self, ctx):
        ht = ctx.has_trait or (lambda u, t: False)
        return [u for u in self.source.evaluate(ctx) if ht(u, self.trait)]


class UnitsWithoutTrait(Node):
    """`DSLFactory.UnitsWithoutTrait(source, traitId) @180e01040` → `UnitsWithFlagSelector` flag=0 : garde
    les unités où `HasFlag(unit, traitId)` est FAUX. Défaut `ctx.has_trait` None → trait absent → garde
    TOUT."""
    def __init__(self, source: Node, trait):
        self.source, self.trait = source, trait

    def evaluate(self, ctx):
        ht = ctx.has_trait or (lambda u, t: False)
        return [u for u in self.source.evaluate(ctx) if not ht(u, self.trait)]


class AdjacentFriends(Node):
    """`DSLFactory.AdjacentFriends(caster) @180de81d0` = symétrique d'`AdjacentEnemies` (finit par
    `Friends`) : alliés (team == caster) à dist <= radius du caster, self exclu."""
    def __init__(self, center: Node, radius: Node | None = None):
        self.center, self.radius = center, radius or Const(1)

    def evaluate(self, ctx):
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))
        ct = (ctx.caster or {}).get("team")
        return [u for u in ring if u.get("team") == ct]


class SurroundingEnemies(Node):
    """`DSLFactory.SurroundingEnemies(center, radius) @180dfc570` = `Enemies(SurroundingUnits(center,
    radius))` : ennemis (team != caster) à dist <= radius du centre, centre exclu."""
    def __init__(self, center: Node, radius: Node):
        self.center, self.radius = center, radius

    def evaluate(self, ctx):
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))
        ct = (ctx.caster or {}).get("team")
        return [u for u in ring if u.get("team") != ct]


class SurroundingFriends(Node):
    """`DSLFactory.SurroundingFriends(center, radius) @180dfc640` = `Friends(SurroundingUnits(center,
    radius))` : alliés (team == caster) à dist <= radius du centre, centre exclu."""
    def __init__(self, center: Node, radius: Node):
        self.center, self.radius = center, radius

    def evaluate(self, ctx):
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))
        ct = (ctx.caster or {}).get("team")
        return [u for u in ring if u.get("team") == ct]


class SortByFormula(Node):
    """`DSLFactory.SortByFormula(source, formula[, ascending]) @180dfb0a0` → `SortByFormulaSelector.Select
    @180ef3010` : trie la source par `formula` évaluée PAR ÉLÉMENT (binding `subject`, comme Filter).
    ⚠ flag natif : 0 (défaut) → DESCENDANT, 1 → ASCENDANT. Tri STABLE (mergesort .NET ≡ `sorted`)."""
    def __init__(self, source: Node, formula: Node, ascending: bool = False):
        self.source, self.formula, self.ascending = source, formula, ascending

    def evaluate(self, ctx):
        lst = list(self.source.evaluate(ctx))
        return sorted(lst, key=lambda u: self.formula.evaluate(replace(ctx, subject=u)),
                      reverse=not self.ascending)


class SortByDistance(Node):
    """`DSLFactory.SortByDistance(source, refPoint) @180dfb020` → `SortByDistanceSelector.Select
    @180ef2ce0` : trie la source par distance hex CROISSANTE au `refPoint` (arg2 = sélecteur de
    position/unité, PAS forcément le caster). ASCENDANT, tri STABLE."""
    def __init__(self, source: Node, ref_point: Node):
        self.source, self.ref_point = source, ref_point

    def evaluate(self, ctx):
        rp = self.ref_point.evaluate(ctx)
        if isinstance(rp, dict):
            rp = _pos(rp)
        lst = list(self.source.evaluate(ctx))
        return sorted(lst, key=lambda u: hexgeo.distance(_pos(u), rp) if _pos(u) is not None else (1 << 30))


class Alive(Node):
    """`DSLFactory.Alive(source) @180de8390` = `Filter(source, IsAlive)` : garde les unités vivantes
    (alive & hp>0). Équivaut à `Damageable`. Retour list."""
    def __init__(self, source: Node):
        self.source = source

    def evaluate(self, ctx):
        return [u for u in self.source.evaluate(ctx) if _is_alive(u)]
