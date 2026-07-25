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
    """`DSLFactory.SurroundingUnits(center, radius, ..., includeCenter, ...) @180dfcb70` =
    `Units(SurroundingTiles(center, includeCenter, radius))` = unités à distance hex <= radius du centre.

    `include_center` = MIRROR de l'argument natif `param_3` de `DSLFactory.SurroundingTiles @180dfca70`
    (lu au décompilé) : `param_3 == 0` -> le factory construit `SurroundingTiles(includeCenter=1) op_Subtraction
    Tiles(center)` (centre EXCLU) ; `param_3 != 0` -> `SurroundingTilesSelector` DIRECT (centre **INCLUS**).
    Défaut `False` = centre exclu (tous les call-sites portés jusqu'ici). `HadesAutocannonsAbility.GetAllTargets
    @1811e5480` passe `SurroundingUnits(target@0x178, range, 1, 1, 3)` -> `SurroundingTiles(..., param_5=1, ...)`
    = **centre inclus** (la cible elle-même est un des summons frappés, cf. i2 « a targeted enemy summon AND all
    other enemy summons within 2 hexes »)."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector, include_center: bool = False):
        self.center, self.radius = center, radius
        self.include_center = bool(include_center)

    def select(self, ctx):
        return _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx),
                       include_center=self.include_center)


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
    """`TargetsSelector.op_Subtraction` : a \\ b par id. Le natif `op_Subtraction` accepte un SELECTEUR **ou
    une ENTITE** en 2e operande (ex. `AdjacentUnits(target) − caster − target` de FireOfAbsolution
    @18121f380) : on normalise les DEUX operandes via `_units_of` (un noeud-role `Caster()`/`Target()` ->
    dict -> `[dict]`), pour soustraire aussi bien une liste qu'une unite seule."""
    def __init__(self, a: TargetsSelector, b: TargetsSelector):
        self.a, self.b = a, b

    def select(self, ctx):
        bset = {u.get("id") for u in _units_of(self.b, ctx)}
        return [u for u in _units_of(self.a, ctx) if u.get("id") not in bset]


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
        behind  = FromTrigger(cands, MinDistance(caster, cand) > MinDistance(caster, target))  # côté OPPOSÉ
    COMPARATEUR = `>` STRICT (case #48). Piège gshared résolu par le SINGLETON de classe (ancre fiable,
    PAS le nom de ctor foldé/mislabelé par ghidra) : le comparateur natif est `DAT_1832482b0` = classe
    construite par `DSLFactory.AmountIsGreater @180de89d0` (`ShouldTrigger @180ee11f0 : iVar16 < iVar15`
    = `amount > threshold`), et NON `AmountIsEqualOrGreater` (@180ee0e00 `<=` = `>=`) comme le laissait
    croire le ctor foldé `AmountIsEqualOrGreaterAbilityTrigger___ctor` (ghidra fusionne les ctors qui
    stockent 2 champs → nom faux). La formule = `DAT_18324e3c0` = classe construite par
    `DSLFactory.MinDistance @180df6820` (distance hex entre MainTiles). Donc : un candidat À DISTANCE
    ÉGALE du caster que la cible (unité LATÉRALE, delta 0 sur l'anneau) est EXCLU (`2 > 2` faux) ; seul
    l'« away » strictement plus loin (delta +1) passe. Confirmé LIVE (test_plasma_cannon_lateral_live,
    probe_udb_case48) : lateral d(caster)==d_ct EXCLU du splash, away d(caster)==d_ct+1 INCLUS.
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
            if not _is_alive(u):                                   # cands = Enemies(Units(ring)) : occupation (#57m)
                continue
            p = _pos(u)
            if p is None or u.get("id") == tid or u.get("team") == ct:
                continue
            if hexgeo.distance(p, tpos) != 1:                      # anneau R1 de la cible
                continue
            if ctx.elev_by_pos is not None:                        # TilesOnSameElevationSelector (maxDiff=1)
                et, ec = ctx.elev_by_pos.get(tpos), ctx.elev_by_pos.get(p)
                if et is not None and ec is not None and abs(et - ec) > 1:
                    continue
            if hexgeo.distance(cpos, p) > d_ct:                    # STRICT (AmountIsGreater) : « derrière » = plus loin
                out.append(u)
        return out


class Friends(TargetsSelector):
    """`DSLFactory.Friends(reference, source) @180df0040` → `UnitsByTeamSelector(ctx, reference, source,
    flag=1)` (symétrique exact d'`Enemies` flag=0) : garde les unités de `source` ALLIÉES au **RÉFÉRENT**.

    Le référent est le 1ᵉʳ argument NATIF (`param_2`), pas une constante : `reference=None` (défaut) = le
    CASTER — le cas de tous les call-sites portés jusqu'ici (`Friends(caster@0x160 / Owner@0x148, ...)`,
    ex. `SquigLaunchasAbility.HasMinimumAdjacentFriendlyUnits @18120af30` = `Friends(Owner@0x148, ...)`).
    `HadesAutocannonsAbility.GetAllTargets @1811e5480` passe `Friends(target@0x178, ...)` = alliés **de la
    CIBLE** (donc les summons ENNEMIS du caster) — d'où le paramètre."""
    def __init__(self, inner: TargetsSelector, reference: TargetsSelector | None = None):
        self.inner, self.reference = inner, reference

    def select(self, ctx):
        ref = resolve_unit(self.reference, ctx) if self.reference is not None else ctx.caster
        rt = (ref or {}).get("team")
        return [u for u in self.inner.evaluate(ctx) if u.get("team") == rt]


class Units(TargetsSelector):
    """`DSLFactory.Units(tiles) @180e01340` → `UnitsOnTilesSelector` : unités DEBOUT sur les tuiles du
    sélecteur source (`tiles` évalue → liste de positions). Généralise l'inline de SurroundingUnits.
    (Mode d'occupation main/steppable = raffinement inerte offline : 1 unité par tuile.)"""
    def __init__(self, tiles: TargetsSelector):
        self.tiles = tiles

    def select(self, ctx):
        tset = set(self.tiles.evaluate(ctx))
        # Occupation de tuile (#57m) : un mort n'est plus DEBOUT sur sa tuile (cf. _within).
        return [u for u in ctx.units if _is_alive(u) and _pos(u) in tset]


class UnitsOnTilesWithEffect(TargetsSelector):
    """`DSLFactory.UnitsOnTilesWithEffect(source, effectType) @180dffc50` → `FromTrigger(source,
    <prédicat tuile-porte-effet>)` : garde les unités de `source` dont la TUILE porte un effet ACTIF
    du type `effect_type`. Structure du décompilé : construit un objet-config (effectType stocké
    @+0x20) + un prédicat (ctor gshared MISLABELÉ « AttackHitsWithModifiersFormula » dans ghidra —
    structure lue, jamais le nom) puis `DSLFactory.FromTrigger(source, prédicat)` = FILTRE de la
    source. Consommateur porté : `StormcallerAbility.ExecuteBehaviour @18120cc20` (#217 — cibles de
    l'attaque = `Enemies(Owner) ∩ on-tiles-with-Ice(0x11)`, TOUTES tuiles glacées, pas juste la zone
    du cast). Lit `ctx.tile_has_effect(tile_id, effect_type)` (wiré par `entities_from_state` sur
    `state.effects`, même clé tile-id que la pose `AddEffectOperation`, case-35) + `ctx.board.id_at`
    pour la tuile de l'unité. board/capacité absents → [] (dégradation documentée).
    ⚠ MainTile seule (l'occupation multi-tuile BigTarget n'est pas raffinée — même réduction que
    `Units`/`_within`)."""
    def __init__(self, source: TargetsSelector, effect_type: int):
        self.source, self.effect_type = source, int(effect_type)

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        the = getattr(ctx, "tile_has_effect", None)
        if board is None or the is None:
            return []
        out = []
        for u in _units_of(self.source, ctx):
            p = _pos(u)
            tid = board.id_at(p[0], p[1]) if p is not None else None
            if tid is not None and the(tid, self.effect_type):
                out.append(u)
        return out


class Tiles(TargetsSelector):
    """`DSLFactory.Tiles(units) @180dfdc60` → `UnitsMainTilesSelector.Select @180f02150` (ctor mislabelé
    "SortReverse", singleton distinct DAT_183278e98) : unités → leur MainTile. Retour list[position].
    `units` normalisé par `_units_of` (comme `AdjacentTiles`) : accepte une unité SEULE (dict, ex.
    `Tiles(Target())` d'OnFireDamage) ou une liste — sans quoi itérer un dict nu rendrait ses CLÉS."""
    def __init__(self, units: TargetsSelector):
        self.units = units

    def select(self, ctx):
        return [p for p in (_pos(u) for u in _units_of(self.units, ctx)) if p is not None]


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


class UnitsWithIds(TargetsSelector):
    """`DSLFactory.UnitsWithIds(source, string[] ids) @180e00230` : UNION (`op_Addition`) sur `ids` de
    `UnitsWithIdSelector(source, TestUnitProvider(id))` -- l'accumulateur part du selecteur VIDE
    (`ctor` gshared mislabele « AllAliveMachinesSelector » dans ghidra : structure lue, jamais le nom),
    donc `ids` vide -> ensemble VIDE.

    `UnitsWithIdSelector.Select @180f04390` = filtre de `source` par
    `UnitExtensions.HasUnitId(unit, id) @180ed70c0` =
    `UnitNamingConventions.GetUnitIdWithoutLevel(GetUnitId(unit)) == id` -- comparaison sur l'id de
    CONFIG de l'unite (`GetUnitId @180ed48d0` lit le champ +0x10 du composant d'identite), pas sur son
    id VISUEL.

    ⚠ OFFLINE : le champ `visualId` du dict d'unite porte l'id de CONFIG pour les unites SPAWNEES
    (`_spawn_config_grot(visual_id=constants['unitId'])`, ex. `astraSmnGuardsman`) et l'id VISUEL rendu
    par `decisionView` pour les unites seedees depuis le live (ex. `astraNpc1Guardsman`, qui est le
    `visualId` gameconfig d'`astraSmnGuardsman`). Le seul consommateur porte (SupremeCommander,
    `affectedUnitIds = "astraSmnGuardsman,astraNpc1Guardsman"`) liste LES DEUX formes -> le filtre est
    EXACT dans les deux cas. Un futur consommateur qui ne listerait qu'une seule forme demanderait un
    id de config par-unite dans le `State` (residu documente).

    Ordre : union dans l'ordre des `ids` (comme le `op_Addition` natif), chaque volet preservant
    l'ordre de `source` ; DOUBLONS possibles si un id apparait deux fois (fidele au natif, qui
    n'insere aucun `Unique`)."""
    def __init__(self, source: TargetsSelector, ids):
        self.source = source
        if isinstance(ids, str):                          # constante gameconfig = liste CSV
            ids = [s.strip() for s in ids.split(",") if s.strip()]
        self.ids = list(ids or ())

    def select(self, ctx):
        units = self.source.evaluate(ctx)
        out: list = []
        for uid in self.ids:                              # op_Addition dans l'ordre des ids
            out += [u for u in units if u.get("visualId") == uid]
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


def non_steppable_or_object_units(source: TargetsSelector) -> TargetsSelector:
    """`DSLFactory.NonSteppableOrObjectUnits(source) @180df7420` — MIRROR du décompilé (composition PURE
    de primitives déjà portées, comme `get_spawn_tile_selector`) :
        `(source op_BitwiseAnd UnitsWithoutTrait(source, 0x1b=Steppable))
                op_BitwiseAnd UnitsWithoutTrait(source, 0xd=Object)`
    = les unités de `source` qui ne sont NI `Steppable` (27, decoys/mines traversables) NI `Object` (13,
    murs/objets de plateau). Le nom natif dit « non (steppable ou object) ».

    Consommateur porté : les deux prédicats de ciblage de `SquigLaunchasAbility`
    (`HasMinimumAdjacentOrks @18120aff0` / `HasMinimumAdjacentFriendlyUnits @18120af30`) — un decoy ou un
    objet adjacent à la cible NE COMPTE PAS comme « unité amie adjacente »."""
    from .traits.unit_trait import UnitTrait
    return And(And(source, UnitsWithoutTrait(source, int(UnitTrait.Steppable))),
               UnitsWithoutTrait(source, int(UnitTrait.Object)))


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
    """`DSLFactory.SurroundingEnemies` = `Enemies(<ref>, Units(SurroundingTiles(center, includeCenter=1,
    radius) - Tiles(center)))` : unites a dist hex <= radius du centre (centre EXCLU) filtrees ENNEMIES
    d'une unite de REFERENCE.

    ⚠ DEUX FORMES NATIVES, distinguees par le nombre d'arguments (lues au decompile) :
      * surcharge 6-args `@180dfc300`/`@180dfc3d0` : `SurroundingEnemies(ref, center, radius, ...)` ->
        reference et centre SEPARES ; le call-site standard passe le CASTER en reference
        (symetrique du `SurroundingFriends(caster, casterTile, ...)` de SupremeCommander @18120df30) ;
      * surcharge 4-args `@180dfc570`/`@180dfc4a0` : `SurroundingEnemies(X, radius, ...)` -> le MEME
        selecteur `X` sert de centre **ET** de reference (`Enemies(param_2 = X, units)`). Call-site lu :
        `CultDemagogueAbility.ExecuteBehaviour @1811cdc30`
        (`SurroundingEnemies(target@0x178, GetNumberConstant(0x44)=range, 1, 3)`) -> « unites entourant la
        CIBLE et ennemies DE LA CIBLE » = les ALLIES du caster (les Neophytes fraichement invoques),
        PAS ses ennemis.

    `reference` = None (defaut) -> forme 6-args, reference = `ctx.caster` (comportement historique,
    inchange pour HeroicFusillade/Stormcaller/...). Explicite -> forme 4-args (passer le MEME noeud que
    `center`)."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector,
                 reference: TargetsSelector | None = None):
        self.center, self.radius, self.reference = center, radius, reference

    def select(self, ctx):
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))
        ref = resolve_unit(self.reference, ctx) if self.reference is not None else ctx.caster
        ct = (ref or {}).get("team")
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


class Unobscured(TargetsSelector):
    """`DSLFactory.Unobscured(from, source) @180e01540` -> `UnobscuredEntitiesSelector.Select @180f06d30` :
    garde les unites de `source` dont la tuile n'est PAS obscurcie (terrain) depuis la tuile du referent
    `from` (`TargetingQuery.IsTargetUnitObscured @1810bf680` -> `MovementQuery.GetTilesObscuringTerrain
    @18109bad0`, mask 6 = elevation bit2 + murs bit4 ; TERRAIN seul, aucun blocage par unite). Multi-tuiles :
    unite obscurcie ssi TOUTES ses tuiles le sont (v1 : MainTile seule).

    - **dist 1 : jamais obscurcie** (la ligne n'a aucune tuile intermediaire testable, cf. case-49x §3) -> gardee.
    - **dist 2 : `bq.is_target_tile_obscured(from, unit, elev)`** (elevation, cube-line ±eps) -- geometrie
      DEJA validee live cote PREDICTION (`bq.surrounding_enemies`, craft-O/O2 probe_49x : crete elev 4 ->
      ennemi dist-2 EXCLU / deplace visible -> compte). `elev` construit depuis `ctx.board`
      (`by_coord[(col,row)]['elevation']`).

    v1 FLAGS (IDENTIQUES a la face prediction, cf. `battle_query.is_target_tile_obscured`) : murs (bit 4)
    non modelises (aucun board d'agreement n'a de mur en zone jouable) ; mask 4 IndirectFire non gate
    (`HasTrait(caster, 0x3ed)` -- aucun caster concerne) ; dist>=3 non modelisee (hors perimetre du seul
    consommateur porte : Gauntlets, source = disque r<=2 MOINS adjacent = dist EXACTEMENT 2). Sans
    `ctx.board` (elevation indisponible) -> passe-tout (degradation sure : board plat = 0 obscurcissement).

    `from_ref` = referent de visibilite (`DSLFactory.Unobscured` recoit l'ENTITE caster `@+0x160`) ; None ->
    tuile du caster (`ctx.caster_pos or _pos(ctx.caster)` = tuile REELLE en execute, aucune position balayee)."""
    def __init__(self, source: TargetsSelector, from_ref: TargetsSelector | None = None):
        self.source, self.from_ref = source, from_ref

    def select(self, ctx):
        from ..battle_query import is_target_tile_obscured
        frm = (_pos(resolve_unit(self.from_ref, ctx)) if self.from_ref is not None
               else (ctx.caster_pos or _pos(ctx.caster)))
        units = _units_of(self.source, ctx)
        if frm is None:
            return list(units)
        board = getattr(ctx, "board", None)
        bc = getattr(board, "by_coord", None) if board is not None else None
        elev = ({k: t.get("elevation", 0) for k, t in bc.items()} if bc else None)
        out = []
        for u in units:
            p = _pos(u)
            if p is None:
                continue
            if hexgeo.distance(frm, p) == 2 and elev is not None \
                    and is_target_tile_obscured(frm, p, elev):
                continue                                    # terrain obscurcit la tuile dist-2 -> exclue
            out.append(u)
        return out


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


class FixedTiles(TargetsSelector):
    """Sélecteur de tuile(s) LITTÉRAL(es) — PAS un noeud natif : VÉHICULE DE COLLAPSE (doctrine slice-18/19)
    présentant à une feuille une tuile déjà résolue IMPÉRATIVEMENT. Analogue tile-domain du collapse
    `Units(Cache(First(Nearest(...))))` -> `Target()` : quand une chaîne native de sélecteurs de TUILES
    (ex. TheBetrayer `First(SortByFormula(SortTilesByUtility((AdjacentTiles(target) & movable).Otherwise(
    movable)), MinPathLength))`) est un sélecteur AI/pathfinding LOURD (kind S), on la calcule hors DSL puis
    on injecte la/les (col,row) résultante(s) via ce nœud pour alimenter la feuille (`MoveUnit`). Retour =
    liste de positions (contrat `dest_tile_sel.evaluate` de `MoveUnit`)."""
    def __init__(self, positions):
        self.positions = [p for p in positions if isinstance(p, tuple) and len(p) == 2]

    def select(self, ctx):
        return list(self.positions)


class FixedTileIds(TargetsSelector):
    """Jumeau ID-DOMAIN de `FixedTiles` — PAS un noeud natif : VEHICULE DE COLLAPSE presentant a une
    feuille des **ids de tuile** deja resolus imperativement. Les deux domaines coexistent parce que les
    feuilles ne lisent PAS le meme contrat : `MoveUnit` consomme des positions `(col,row)` (-> `FixedTiles`)
    alors que `Spawn` consomme des **ids** (comme les rendent `AdjacentTiles`/`SurroundingTiles`/
    `CanAddUnit`) -> `FixedTileIds`. Consommateurs : les collapses de tuiles de spawn de
    `SendInTheNextWaveAbility.GetSpawnTilesSelector @181206cc0`, `IncursionAbility.GetNextSpawnTile
    @1811ea520` et `SpawnPoxwalkersAbility.ExecuteBehaviour @181208b80` (chaines a `PickRandomly`
    imbriques : le tirage vit dans le collapse, seul endroit qui voit `state.rng`)."""
    def __init__(self, tile_ids):
        self.tile_ids = [int(t) for t in (tile_ids or []) if isinstance(t, int)]

    def select(self, ctx):
        return list(self.tile_ids)


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


class Actor(TargetsSelector):
    """L'entité ACTOR/KILLER du contexte de trigger (`AbilityEntities` slot `factory+0x158`) : l'ACTEUR
    de l'événement déclencheur — ex. le TUEUR sur `OnPreDeath` (ActOfFaith accumulate @181219a70 lit
    `killer@0x158` pour `HasTrait`/`AreFriends`/`UnitNormalAttackType`). Accesseur unit-domain =
    `ctx.actor` (dict|None) ; None si non threadé (le prédicat au-dessus retombe alors sur False)."""
    def select(self, ctx):
        return ctx.actor


class Target(TargetsSelector):
    """Cible principale de l'ability (l'UNITÉ, pas sa tuile — cf. `TargetTile`). Mirror du contexte
    d'entité-cible natif (`AbilityEntities` slot cible = `factory+0x178`) : les behaviours d'ability
    (`AttackWithAttackDamage`, `AddEffect`) ancrés sur la cible lisent `ctx.target` ici. None si l'ability
    est sans cible (auto/tuile)."""
    def select(self, ctx):
        return ctx.target


class ActiveTarget(TargetsSelector):
    """Slot `factory+0x180` = **ActiveTarget** (carte des selecteurs caches du `DSLFactory`, posee par
    `DSLFactory.InitializeShared @180df2670` : `0x148 Owner · 0x150 Effect · 0x158 Actor · 0x160 Caster ·
    0x168 CasterTile · 0x170 CasterTiles · 0x178 Target · 0x180 ActiveTarget · 0x188 PreviousActiveTarget ·
    0x190 TargetTiles · 0x198 UnitFeetTiles`). C'est l'ELEMENT COURANT lie par le behaviour englobant :

      * sous-behaviour **on-appearance** d'un `Spawn` (`SpawnUnitOptions+0x18`, fire par
        `TriggerSpawnedUnitBehaviours`) -> le SUMMON fraichement pose. Consommateurs lus :
        `SpawnPoxwalkersAbility.ExecuteBehaviour @181208b80`
        (`PerformAIAttackFromCurrentPosition(ActiveTarget@0x180)`),
        `SendInTheNextWaveAbility.ExecuteBehaviour @181206490`
        (`UseNormalAttackIfAble(ActiveTarget@0x180, Target@0x178)`),
        `IncursionAbility.ExecuteBehaviour @1811e9fe0`
        (`UseNormalAttackIfAble(ActiveTarget@0x180, Entity(<unite cible>))`) ;
      * iteration d'un `ChainBehaviour` -> l'element rendu par le selecteur de l'iteration (Incursion :
        la TUILE de spawn, `Spawn(caster@0x160, ActiveTarget@0x180, unitId, opts)`).

    Accesseur = `ctx.active_target` (dict d'unite | id de tuile | liste) ; None hors behaviour liant."""
    def select(self, ctx):
        return getattr(ctx, "active_target", None)


class SurroundingTiles(TargetsSelector):
    """`DSLFactory.SurroundingTiles(center, includeCenter, radius, ...) @180dfca70` : les TUILES du disque
    hex de rayon `radius` autour du centre (`center` = selecteur unit-domain OU position). `include_center`
    = l'argument natif `includeCenter` (0 aux call-sites portes : Poxwalkers @181208b80, SendInTheNextWave
    @181206bc0/@181206cc0, CultDemagogue @1811cdc30 -> centre EXCLU). Retour list[int] (tile ids), ordre
    hexgeo deterministe. Generalisation d'`AdjacentTiles` (= radius 1 via le voisinage board) au disque :
    ici la geometrie vient de `hexgeo.disk` (meme primitive que le collapse `_surrounding_free_tiles` du
    port CultDemagogue). board None -> []."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector, include_center: bool = False):
        self.center, self.radius = center, radius
        self.include_center = bool(include_center)

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        r = int(self.radius.evaluate(ctx) or 0)
        centers = self.center.evaluate(ctx)
        if isinstance(centers, tuple) and len(centers) == 2:
            centers = [centers]
        elif isinstance(centers, dict) or centers is None:
            centers = [_pos(centers)] if centers is not None else []
        else:
            centers = [c if (isinstance(c, tuple) and len(c) == 2) else _pos(c) for c in centers]
        seen, out = set(), []
        for c in centers:
            if c is None:
                continue
            for (col, row) in hexgeo.disk(c[0], c[1], r):
                if not self.include_center and (col, row) == (c[0], c[1]):
                    continue
                t = board.id_at(col, row)
                if t is not None and t not in seen:
                    seen.add(t)
                    out.append(t)
        return out


class UnitsWithVisualId(TargetsSelector):
    """`DSLFactory.UnitsWithVisualId(visualIdValue, mode) @180e00e90` = `UnitsWithIdSelector(ctx,
    factory+0x80, visualIdValue, mode)`. La source est le slot PARTAGE `factory+0x80` (pose par
    `InitializeShared @180df2670`, == la source d'`AllUnits`/`Friends(caster, @0x80)` de
    `WaaaghAbility.GetBuffBehaviour @18122b900`) -> le selecteur est **BOARD-WIDE : AUCUN RAYON**, a ne pas
    confondre avec `UnitsWithIds(source, ids)` (qui FILTRE un sous-ensemble deja restreint, ex.
    `SurroundingFriends` de SupremeCommander @18120df30).

    Consommateurs lus : `WaaaghAbility.ExecuteBehaviour @18122b010` (site @18122b306+) et son homologue
    `WaaaghAbility.GetTriggerSummonsBehaviour @18122c260`, tous deux
    `Friends(caster@0x160, UnitsWithVisualId(VisualUnitIdFromUnitId(Get(unitId)), 1), 3)`.

    `visual_id` = noeud VALEUR (`VisualUnitIdFromUnitId`, entities/formulas.py) ou str/iterable de str.
    Le filtre compare le champ `visualId` du dict d'unite (meme convention que `UnitsWithIds`)."""
    def __init__(self, visual_id, mode: int = 1):
        self.visual_id, self.mode = visual_id, int(mode)

    def _ids(self, ctx) -> list:
        v = self.visual_id
        v = v.evaluate(ctx) if hasattr(v, "evaluate") else v
        if v is None:
            return []
        return [v] if isinstance(v, str) else [s for s in v if s]

    def select(self, ctx):
        ids = self._ids(ctx)
        if not ids:
            return []
        return [u for u in ctx.units if u.get("visualId") in ids]


class UnitsWithId(TargetsSelector):
    """`DSLFactory.UnitsWithId(source, idValue, mode) @180e00170` = `UnitsWithIdSelector(ctx, source,
    TestUnitProvider(idValue), mode)` : le VOLET MONO-ID d'`UnitsWithIds` (qui, lui, UNIONNE les volets sur
    un tableau d'ids). Filtre `source` par `UnitExtensions.HasUnitId(unit, id) @180ed70c0`.
    Consommateur lu : `CultDemagogueAbility.ExecuteBehaviour @1811cdc30`
    (`UnitsWithId(SurroundingEnemies(target@0x178, range, 1, 3), GetStringConstant(0|4), 3)`).
    Meme reduction offline que `UnitsWithIds` : comparaison sur le champ `visualId` du dict d'unite
    (qui porte l'id de CONFIG pour les unites SPAWNEES, cf. `_spawn_config_grot`)."""
    def __init__(self, source: TargetsSelector, unit_id, mode: int = 3):
        self.source, self.unit_id, self.mode = source, unit_id, int(mode)

    def select(self, ctx):
        uid = self.unit_id.evaluate(ctx) if hasattr(self.unit_id, "evaluate") else self.unit_id
        if uid is None:
            return []
        return [u for u in self.source.evaluate(ctx) if u.get("visualId") == uid]


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


class EffectsFromUnitSource(TargetsSelector):
    """`DSLFactory.EffectsFromUnitSource(source, effectType) @180deec70` -> `EffectWithTypeSelector
    @180ee7f30` (frere d'`EffectFromOwner`, keye sur la SOURCE au lieu de l'owner) : les INSTANCES d'effet
    du type `effect_type` dont le `EffectComponent.SourceUnit @+0x10` est l'unite `source`. Domaine =
    ENTITES-EFFET (pas des unites) -> consomme par `OwnerOfEffect` qui remonte a leurs porteurs.

    Seul call-site porte : `MasterAnnihilatorAbility.CreateBehaviour @18110b940`
    (`RemoveEffect(OwnerOfEffect(EffectsFromUnitSource(Self@0x148, 0x4e1)), 0x4e1)` = le marqueur pose par
    CE caster, ou qu'il soit). Offline l'entite-effet est modelisee par un dict
    `{"effect_type", "source", "owner_id"}` (`ctx.effects_from_source`) ; sans accesseur -> [] (degradation
    fidele « present != applique »)."""
    def __init__(self, source: TargetsSelector, effect_type):
        self.source, self.effect_type = source, effect_type

    def select(self, ctx):
        fn = getattr(ctx, "effects_from_source", None)
        if fn is None:
            return []
        src = resolve_unit(self.source, ctx)
        if src is None:
            return []
        et = self.effect_type.evaluate(ctx) if hasattr(self.effect_type, "evaluate") else self.effect_type
        return list(fn(src, int(et)) or [])


class OwnerOfEffect(TargetsSelector):
    """`DSLFactory.OwnerOfEffect(effects) @180df8350` : remonte de chaque ENTITE-EFFET a l'UNITE qui la
    PORTE (`EffectComponent.Target @+0x14` / cle `EffectsState.by_unit`). Rend des dicts d'unite
    (domaine unit) dedupliques, dans l'ordre du selecteur source."""
    def __init__(self, effects: TargetsSelector):
        self.effects = effects

    def select(self, ctx):
        by_id = {u.get("id"): u for u in (ctx.units or []) if isinstance(u, dict)}
        out, seen = [], set()
        for e in (self.effects.evaluate(ctx) or []):
            oid = e.get("owner_id") if isinstance(e, dict) else None
            if oid is None or oid in seen:
                continue
            u = by_id.get(oid)
            if u is not None:
                seen.add(oid)
                out.append(u)
        return out


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
