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
    """`IdunBattleLogic.Entities.DSLFactory$$SurroundingUnits(center, radius, ..., includeCenter, ...)` =
    `Units(SurroundingTiles(center, includeCenter, radius))` = unités à distance hex <= radius du centre.

    `include_center` = MIRROR de l'argument natif `param_3` de `IdunBattleLogic.Entities.DSLFactory$$SurroundingTiles`
    (lu au décompilé) : `param_3 == 0` -> le factory construit `SurroundingTiles(includeCenter=1) op_Subtraction
    Tiles(center)` (centre EXCLU) ; `param_3 != 0` -> `SurroundingTilesSelector` DIRECT (centre **INCLUS**).
    Défaut `False` = centre exclu (tous les call-sites portés jusqu'ici). `IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets` passe `SurroundingUnits(target@0x178, range, 1, 1, 3)` -> `SurroundingTiles(..., param_5=1, ...)`
    = **centre inclus** (la cible elle-même est un des summons frappés, cf. i2 « a targeted enemy summon AND all
    other enemy summons within 2 hexes »)."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector, include_center: bool = False):
        self.center, self.radius = center, radius
        self.include_center = bool(include_center)

    def select(self, ctx):
        return _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx),
                       include_center=self.include_center)


class AdjacentEnemies(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$AdjacentEnemies(caster)` = `Enemies(Units(AdjacentTiles(caster)) - {caster})`
    = ennemis (team != caster) à dist <= radius du caster, self exclu."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector | None = None):
        self.center, self.radius = center, radius or Const(1)

    def select(self, ctx):
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))
        ct = (ctx.caster or {}).get("team")
        return [u for u in ring if u.get("team") != ct]


class AdjacentUnits(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$AdjacentUnits(target, radius, mask)` = `Units(AdjacentTiles(target)) - {target}`
    = TOUTES les unités (AUCUN filtre d'équipe) à distance hex <= radius de `target`, target exclu. ⚠ à la
    DIFFÉRENCE de `AdjacentEnemies` (filtre team != caster) et de `Enemies(...)` (wrapper `UnitsByTeamSelector`),
    ce sélecteur ne filtre PAS l'équipe → inclut les ALLIÉS du caster (et le caster) s'ils sont adjacents à la
    cible = FRIENDLY-FIRE. Le volet SPLASH de Stikkbomb (IdunBattleLogic.Entities.Abilities.Active.Loki.StikkbombAbility$$ExecuteBehaviour) passe ce sélecteur BRUT (sans wrapper
    `Enemies(...)`, contraste PlasmaGrenade/ScythingTalons) — corroboré par l'i2 (« units in hexes adjacent »
    vs « enemy units » des autres). `_within` exclut déjà le centre (target, dist 0). Mirror de `AdjacentEnemies`
    SANS le filtre team."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector | None = None):
        self.center, self.radius = center, radius or Const(1)

    def select(self, ctx):
        return _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))


class Enemies(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Enemies(reference, source, mode)` -> `UnitsByTeamSelector`
    (`IdunBattle.Entities.Selectors.UnitsByTeamSelector$$Select` -> `$$CountOrAdd`, flag@+0x28 = 0) :
    filtre -> equipe != celle du referent (le CASTER a tous les call-sites portes). Symetrique exact de
    `Friends` (meme classe, flag 1).

    `_units_of` normalise l'operande (mirror du contrat natif : `source` peut etre un REF-ENTITE seul --
    `Enemies(caster, target@0x178, 3)` de `PlagueburstMortarAbility$$GetMainDamageTarget` -- ou une liste ;
    None -> vide). Sans ca, iterer un dict nu rendrait ses CLES (meme piege que `Tiles`/`Sub`)."""
    def __init__(self, inner: TargetsSelector):
        self.inner = inner

    def select(self, ctx):
        ct = (ctx.caster or {}).get("team")
        return [u for u in _units_of(self.inner, ctx) if isinstance(u, dict) and u.get("team") != ct]


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
    IdunBattleLogic.Entities.Abilities.Active.Loki.FireOfAbsolutionAbility$$CreateBehaviour) : on normalise les DEUX operandes via `_units_of` (un noeud-role `Caster()`/`Target()` ->
    dict -> `[dict]`), pour soustraire aussi bien une liste qu'une unite seule."""
    def __init__(self, a: TargetsSelector, b: TargetsSelector):
        self.a, self.b = a, b

    def select(self, ctx):
        bset = {u.get("id") for u in _units_of(self.b, ctx)}
        return [u for u in _units_of(self.a, ctx) if u.get("id") not in bset]


class Union(TargetsSelector):
    """`TargetsSelector.op_Addition` : UNION (concaténation) de deux sélecteurs d'unités — mirror du
    `op_Addition(Self, UnitsFromFaction(...))` de `IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetHealTargets`. Concatène
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
    """`IdunBattleLogic.Entities.DSLFactory$$Filter(source, predicate)` → thunk `IdunBattleLogic.Entities.DSLFactory$$FromTrigger` →
    `IdunBattle.Entities.Selectors.FromTriggerSelector$$Select` : énumère `source` et, POUR CHAQUE élément, LIE l'élément
    au slot sujet du contexte (mirror du `0x20`→`ability+0x180` natif) puis évalue le prédicat bool
    contre ce contexte ; garde l'élément si le prédicat est vrai. Preuve binding : `TheBetrayer
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheBetrayer_TakeTurnAbility$$GetPreferredAttackTargets` = `Filter(src, NOT(HasTrait(subject, 0xd)))` — le prédicat
    lit son sujet via `Subject` (= `ctx.subject`). Retour list.
    (`IdunBattleLogic.Entities.DSLFactory$$FilterContinuous` = même construction + flag short-circuit ; `IdunBattleLogic.Entities.DSLFactory$$FilterByDirection` = classe distincte directionnelle — hors batch, à porter à la demande.)"""
    def __init__(self, source: TargetsSelector, predicate: TargetsSelector):
        self.source, self.predicate = source, predicate

    def select(self, ctx):
        out = []
        for item in self.source.evaluate(ctx):
            if self.predicate.evaluate(replace(ctx, subject=item)):
                out.append(item)
        return out


class UnitsDirectlyBehind(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$UnitsDirectlyBehind` — cibles secondaires « derrière la cible »
    (PlasmaCannon…). Transcription EXACTE de la construction native :
        ring    = SurroundingTiles(target, 1, 1) − Tiles(target)          # anneau R1 de la CIBLE
        cands   = Enemies(caster, Units(ring))                            # ennemis du caster dessus
        sameElv = TilesOnSameElevationSelector(target, cands, 1)          # même élévation que la cible
        behind  = FromTrigger(cands, MinDistance(caster, cand) > MinDistance(caster, target))  # côté OPPOSÉ
    COMPARATEUR = `>` STRICT (case #48). Piège gshared résolu par le SINGLETON de classe (ancre fiable,
    PAS le nom de ctor foldé/mislabelé par ghidra) : le comparateur natif est `DAT_1832482b0` = classe
    construite par `IdunBattleLogic.Entities.DSLFactory$$AmountIsGreater` (`IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger : iVar16 < iVar15`
    = `amount > threshold`), et NON `AmountIsEqualOrGreater` (IdunBattle.Entities.Conditions.AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger `<=` = `>=`) comme le laissait
    croire le ctor foldé `AmountIsEqualOrGreaterAbilityTrigger___ctor` (ghidra fusionne les ctors qui
    stockent 2 champs → nom faux). La formule = `DAT_18324e3c0` = classe construite par
    `IdunBattleLogic.Entities.DSLFactory$$MinDistance` (distance hex entre MainTiles). Donc : un candidat À DISTANCE
    ÉGALE du caster que la cible (unité LATÉRALE, delta 0 sur l'anneau) est EXCLU (`2 > 2` faux) ; seul
    l'« away » strictement plus loin (delta +1) passe. Confirmé LIVE (test_plasma_cannon_lateral_live,
    probe_udb_case48) : lateral d(caster)==d_ct EXCLU du splash, away d(caster)==d_ct+1 INCLUS.
    `dist` = distance hex ; caster = `ctx.caster_pos` (tuile d'attaque balayée). Élévation :
    `IdunBattle.Entities.Selectors.TilesOnSameElevationSelector$$Select` garde si `GetElevationDifference(cand, target)
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
    """`IdunBattleLogic.Entities.DSLFactory$$Friends(reference, source)` → `UnitsByTeamSelector(ctx, reference, source,
    flag=1)` (symétrique exact d'`Enemies` flag=0) : garde les unités de `source` ALLIÉES au **RÉFÉRENT**.

    Le référent est le 1ᵉʳ argument NATIF (`param_2`), pas une constante : `reference=None` (défaut) = le
    CASTER — le cas de tous les call-sites portés jusqu'ici (`Friends(caster@0x160 / Owner@0x148, ...)`,
    ex. `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$HasMinimumAdjacentFriendlyUnits` = `Friends(Owner@0x148, ...)`).
    `IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets` passe `Friends(target@0x178, ...)` = alliés **de la
    CIBLE** (donc les summons ENNEMIS du caster) — d'où le paramètre."""
    def __init__(self, inner: TargetsSelector, reference: TargetsSelector | None = None):
        self.inner, self.reference = inner, reference

    def select(self, ctx):
        ref = resolve_unit(self.reference, ctx) if self.reference is not None else ctx.caster
        rt = (ref or {}).get("team")
        return [u for u in self.inner.evaluate(ctx) if u.get("team") == rt]


class Units(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Units(tiles)` → `UnitsOnTilesSelector` : unités DEBOUT sur les tuiles du
    sélecteur source (`tiles` évalue → liste de positions). Généralise l'inline de SurroundingUnits.
    (Mode d'occupation main/steppable = raffinement inerte offline : 1 unité par tuile.)

    ORDRE = celui des TUILES (le natif ITERE le sélecteur de tuiles et résout l'occupant de chacune),
    PAS l'ordre des entités. Observable dès qu'un `Foreach` consomme le résultat : le beam de
    `DarkTalonStrikeAbility$$ExecuteBehaviour` frappe la CIBLE puis les tuiles de la ligne en s'éloignant
    (cascade live u79 @(5,5) puis u77 @(5,6)) — l'ordre d'entité aurait donné u77 d'abord et désynchronisé
    `state.rng`. Dédoublonnage par id d'unité (première occurrence conservée) : une même tuile peut
    apparaître deux fois dans une union de sélecteurs."""
    def __init__(self, tiles: TargetsSelector):
        self.tiles = tiles

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        raw = self.tiles.evaluate(ctx)
        # Le natif ITERE son selecteur de tuiles : un selecteur MONO-TUILE (`Subject()` sous un
        # `Filter`/`SortByFormula` tile-domain, ex. `Units(Subject@0x180)` de
        # `ThriceBlessedConflagrationAbility$$GetTilesInLine`) rend UN element -> normalisation, sinon
        # `set(int)` leve. Domaine mixte accepte : id de tuile (int), position (col,row), dict d'unite.
        items = [] if raw is None else ([raw] if isinstance(raw, (dict, int, tuple)) else list(raw))
        # Index position -> unite VIVANTE (occupation de tuile, #57m : un mort n'est plus DEBOUT sur sa
        # tuile, cf. _within).
        occupant: dict = {}
        for u in ctx.units:
            if not _is_alive(u):
                continue
            p = _pos(u)
            if p is not None and p not in occupant:
                occupant[p] = u
        out, seen = [], set()
        for it in items:
            if isinstance(it, bool):
                continue
            if isinstance(it, dict):
                p = _pos(it)
            elif isinstance(it, int):
                p = board.coord(it) if (board is not None and it in board.by_id) else None
            elif isinstance(it, (tuple, list)) and len(it) == 2:
                p = (it[0], it[1])
            else:
                p = None
            if p is None:
                continue
            u = occupant.get((int(p[0]), int(p[1])))
            if u is None or u.get("id") in seen:
                continue
            seen.add(u.get("id"))
            out.append(u)
        return out


class UnitsOnTilesWithEffect(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$UnitsOnTilesWithEffect(source, effectType)` → `FromTrigger(source,
    <prédicat tuile-porte-effet>)` : garde les unités de `source` dont la TUILE porte un effet ACTIF
    du type `effect_type`. Structure du décompilé : construit un objet-config (effectType stocké
    @+0x20) + un prédicat (ctor gshared MISLABELÉ « AttackHitsWithModifiersFormula » dans ghidra —
    structure lue, jamais le nom) puis `DSLFactory.FromTrigger(source, prédicat)` = FILTRE de la
    source. Consommateur porté : `IdunBattleLogic.Entities.Abilities.Active.Loki.StormcallerAbility$$ExecuteBehaviour` (#217 — cibles de
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
    """`IdunBattleLogic.Entities.DSLFactory$$Tiles(units)` → `IdunBattle.Entities.Selectors.UnitsMainTilesSelector$$Select` (ctor mislabelé
    "SortReverse", singleton distinct DAT_183278e98) : unités → leur MainTile. Retour list[position].
    `units` normalisé par `_units_of` (comme `AdjacentTiles`) : accepte une unité SEULE (dict, ex.
    `Tiles(Target())` d'OnFireDamage) ou une liste — sans quoi itérer un dict nu rendrait ses CLÉS."""
    def __init__(self, units: TargetsSelector):
        self.units = units

    def select(self, ctx):
        return [p for p in (_pos(u) for u in _units_of(self.units, ctx)) if p is not None]


class First(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$First(source[, index])` → `IdunBattle.Entities.Selectors.PickAtIndexSelector$$Select` :
    l'élément à `index` (défaut 0) de la liste source (ordre TEL QUEL), `[]` si hors borne. Retour list
    de 0/1 élément (PAS un élément nu). S'appuie sur un tri préalable si l'appelant en pose un."""
    def __init__(self, source: TargetsSelector, index: int = 0):
        self.source, self.index = source, index

    def select(self, ctx):
        lst = self.source.evaluate(ctx)
        return [lst[self.index]] if 0 <= self.index < len(lst) else []


class Unique(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Unique(source)` → LINQ Distinct : dedup de la source (ordre de 1re
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
    """`IdunBattleLogic.Entities.DSLFactory$$UnitsWithIds(source, string[] ids)` : UNION (`op_Addition`) sur `ids` de
    `UnitsWithIdSelector(source, TestUnitProvider(id))` -- l'accumulateur part du selecteur VIDE
    (`ctor` gshared mislabele « AllAliveMachinesSelector » dans ghidra : structure lue, jamais le nom),
    donc `ids` vide -> ensemble VIDE.

    `IdunBattle.Entities.Selectors.UnitsWithIdSelector$$Select` = filtre de `source` par
    `IdunBattle.Entities.UnitExtensions$$HasUnitId(unit, id)` =
    `UnitNamingConventions.GetUnitIdWithoutLevel(GetUnitId(unit)) == id` -- comparaison sur l'id de
    CONFIG de l'unite (`IdunBattle.Entities.UnitExtensions$$GetUnitId` lit le champ +0x10 du composant d'identite), pas sur son
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
    """`IdunBattleLogic.Entities.DSLFactory$$UnitsWithTrait(source, traitId)` → `UnitsWithFlagSelector` flag=1 : garde
    les unités où `HasFlag(unit, traitId)` (même primitive que HasFlag). `ctx.has_trait` teste le trait ;
    défaut None → trait ABSENT (convention HasFlag) → set vide."""
    def __init__(self, source: TargetsSelector, trait):
        self.source, self.trait = source, trait

    def select(self, ctx):
        ht = ctx.has_trait or (lambda u, t: False)
        return [u for u in self.source.evaluate(ctx) if ht(u, self.trait)]


class UnitsWithoutTrait(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$UnitsWithoutTrait(source, traitId)` → `UnitsWithFlagSelector` flag=0 : garde
    les unités où `HasFlag(unit, traitId)` est FAUX. Défaut `ctx.has_trait` None → trait absent → garde
    TOUT."""
    def __init__(self, source: TargetsSelector, trait):
        self.source, self.trait = source, trait

    def select(self, ctx):
        ht = ctx.has_trait or (lambda u, t: False)
        return [u for u in self.source.evaluate(ctx) if not ht(u, self.trait)]


def hero_units(source: TargetsSelector) -> TargetsSelector:
    """`IdunBattleLogic.Entities.DSLFactory$$HeroUnits(source, mask)` — MIRROR du decompile : la factory
    native N'ALLOUE PAS de selecteur dedie, elle DELEGUE textuellement a
    `IdunBattleLogic.Entities.DSLFactory$$UnitsWithTrait(source, 0x10, mask)`. On mirror donc la FACTORY
    (fonction de composition), pas une classe inventee — `0x10` = `UnitTrait.Hero` (16). Consommateur porte :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.AdaptiveStrategyAbility$$GetNonCharacterFriendsSelector`
    (`Friends(...) op_Subtraction HeroUnits(...)` = les amis NON-Character)."""
    return UnitsWithTrait(source, 0x10)


class AllDeadOrResurrectedUnits(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$AllDeadOrResurrectedUnits` ->
    `IdunBattle.Entities.Selectors.AllDeadOrResurrectedUnitsSelector$$Select` — MIRROR du decompile :

        result = StateExtensions.<slot 0x8a>(state)          # == AllDeadUnitsSelector.Select : les MORTS
        foreach u in StateExtensions.<slot 0x88>(state):     # toutes les unites du state
            if UnitFlagsComponent.Has(u, 0xe) and !result.Contains(u):
                result.Add(u)                                # les RESSUSCITES (deja revenus a la vie)
        return result

    Le flag `0xe` est celui que `ResurrectUnitOperation` pose (port : `UnitFlagsComponent.AMBUSH_CONSUMED`,
    permanent, survit a `remove_turn_flags`). Cote port : la moitie MORTS se lit directement de `ctx.units`
    (le state runner GARDE les cadavres, `alive=False`), la moitie RESSUSCITES via `ctx.has_unit_flag`
    (None -> False = aucun ressuscite, degradation fidele). Ordre = morts d'abord (ordre `ctx.units`), puis
    les ressuscites non deja presents — meme ordre d'insertion que le natif.

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$GetMaxSummonsFormula`
    (`Count(Friends(caster, UnitsWithTrait(AllDeadOrResurrectedUnits, 1000=LivingMetal)))`)."""
    def select(self, ctx):
        out = [u for u in ctx.units if not _is_alive(u)]          # == AllDeadUnitsSelector
        seen = {u.get("id") for u in out}
        hf = ctx.has_unit_flag
        if hf is None:
            return out
        for u in ctx.units:
            if u.get("id") in seen:
                continue
            if hf(u, 0xe):                                        # UnitFlag 0xe = ressuscite
                out.append(u)
                seen.add(u.get("id"))
        return out


def non_steppable_or_object_units(source: TargetsSelector) -> TargetsSelector:
    """`IdunBattleLogic.Entities.DSLFactory$$NonSteppableOrObjectUnits(source)` — MIRROR du décompilé (composition PURE
    de primitives déjà portées, comme `get_spawn_tile_selector`) :
        `(source op_BitwiseAnd UnitsWithoutTrait(source, 0x1b=Steppable))
                op_BitwiseAnd UnitsWithoutTrait(source, 0xd=Object)`
    = les unités de `source` qui ne sont NI `Steppable` (27, decoys/mines traversables) NI `Object` (13,
    murs/objets de plateau). Le nom natif dit « non (steppable ou object) ».

    Consommateur porté : les deux prédicats de ciblage de `SquigLaunchasAbility`
    (`IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$HasMinimumAdjacentOrks` / `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$HasMinimumAdjacentFriendlyUnits`) — un decoy ou un
    objet adjacent à la cible NE COMPTE PAS comme « unité amie adjacente »."""
    from .traits.unit_trait import UnitTrait
    return And(And(source, UnitsWithoutTrait(source, int(UnitTrait.Steppable))),
               UnitsWithoutTrait(source, int(UnitTrait.Object)))


class AdjacentFriends(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$AdjacentFriends(caster)` = symétrique d'`AdjacentEnemies` (finit par
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
      * surcharge 6-args `IdunBattleLogic.Entities.DSLFactory$$SurroundingEnemies`/`IdunBattleLogic.Entities.DSLFactory$$SurroundingEnemies` : `SurroundingEnemies(ref, center, radius, ...)` ->
        reference et centre SEPARES ; le call-site standard passe le CASTER en reference
        (symetrique du `SurroundingFriends(caster, casterTile, ...)` de SupremeCommander IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour) ;
      * surcharge 4-args `IdunBattleLogic.Entities.DSLFactory$$SurroundingEnemies`/`IdunBattleLogic.Entities.DSLFactory$$SurroundingEnemies` : `SurroundingEnemies(X, radius, ...)` -> le MEME
        selecteur `X` sert de centre **ET** de reference (`Enemies(param_2 = X, units)`). Call-site lu :
        `IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$ExecuteBehaviour`
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
    """`IdunBattleLogic.Entities.DSLFactory$$SurroundingFriends(center, radius)` = `Friends(SurroundingUnits(center,
    radius))` : alliés (team == caster) à dist <= radius du centre, centre exclu."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector):
        self.center, self.radius = center, radius

    def select(self, ctx):
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx))
        ct = (ctx.caster or {}).get("team")
        return [u for u in ring if u.get("team") == ct]


class SortByFormula(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$SortByFormula(source, formula[, ascending])` → `IdunBattle.Entities.Selectors.SortByFormulaSelector$$Select` : trie la source par `formula` évaluée PAR ÉLÉMENT (binding `subject`, comme Filter).
    ⚠ flag natif : 0 (défaut) → DESCENDANT, 1 → ASCENDANT. Tri STABLE (mergesort .NET ≡ `sorted`)."""
    def __init__(self, source: TargetsSelector, formula: TargetsSelector, ascending: bool = False):
        self.source, self.formula, self.ascending = source, formula, ascending

    def select(self, ctx):
        lst = list(self.source.evaluate(ctx))
        return sorted(lst, key=lambda u: self.formula.evaluate(replace(ctx, subject=u)),
                      reverse=not self.ascending)


class SortByDistance(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$SortByDistance(source, refPoint)` → `IdunBattle.Entities.Selectors.SortByDistanceSelector$$Select` : trie la source par distance hex CROISSANTE au `refPoint` (arg2 = sélecteur de
    position/unité, PAS forcément le caster). ASCENDANT, tri STABLE.

    Domaine MIXTE (unité / id de tuile / position) des DEUX côtés : le natif trie des ENTITES et lit leur
    `MainTile` (`DarkTalonStrikeAbility$$GetTilesInBestLine` trie les tuiles `AdjacentTiles(caster@0x160)`
    par distance a `target@0x178`). `_tile_positions` normalise le refPoint ; `_entity_pos` chaque élément."""
    def __init__(self, source: TargetsSelector, ref_point: TargetsSelector):
        self.source, self.ref_point = source, ref_point

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        rp_list = _tile_positions(self.ref_point, ctx, board)
        rp = rp_list[0] if rp_list else None
        lst = list(self.source.evaluate(ctx))
        if rp is None:
            return lst
        return sorted(lst, key=lambda u: (hexgeo.distance(p, rp) if (p := _entity_pos(u, board)) is not None
                                          else (1 << 30)))


class Alive(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Alive(source)` = `Filter(source, IsAlive)` : garde les unités vivantes
    (alive & hp>0). Équivaut à `Damageable`. Retour list."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        return [u for u in self.source.evaluate(ctx) if _is_alive(u)]


class Unobscured(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Unobscured(from, source)` -> `IdunBattle.Entities.Selectors.UnobscuredEntitiesSelector$$Select` :
    garde les unites de `source` dont la tuile n'est PAS obscurcie (terrain) depuis la tuile du referent
    `from` (`IdunBattle.Core.Services.TargetingQuery$$IsTargetUnitObscured` -> `IdunBattle.Core.Services.MovementQuery$$GetTilesObscuringTerrain`, mask 6 = elevation bit2 + murs bit4 ; TERRAIN seul, aucun blocage par unite). Multi-tuiles :
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

    Port : le lien enfant -> parent vit sur le dict d'unite (`parentId`, alimente par `UnitComponent.
    parent_id` que `SpawnUnitOperation` pose au spawn = le `Unit_Parent_Id` natif). Le parent est
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
    historiques passent par le meme chemin, resultat inchange). Retour list[int]. board None -> []."""
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


class MovableTilesInRange(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$MovableTilesInRange(unit, fromTile, range, canReachOnly,
    …)` -> `IdunBattle.Entities.Selectors.MovableTilesInRangeSelector$$Select`, qui resout
    `unit` (@+0x20), `fromTile` (@+0x28, a defaut `GetMainTile(unit)`), `range` (formule @+0x30,
    `Nullable<int>`) puis delegue au slot 0xc de la `PathfindingQuery` avec `canReachOnly` (@+0x38).

    Le calcul est le PATHFINDER (impératif, `entities/pathfinding/walk_pathfinder.py` — mirror de
    `IdunBattle.Entities.Pathfinding.BasePathfinder$$GetMovablePositions`) : ce noeud est la FEUILLE
    DSL qui l'appelle, comme `CanAddUnit` est la feuille qui appelle les predicats de board.

    `can_reach_only` :
      * `False` (natif `0`) -> le `visited` du BFS = TOUTES les tuiles ATTEINTES en <= range pas
        (traversables, y compris occupees par un allie) ;
      * `True`  (natif `1`) -> le `stop_set` = celles ou l'unite peut S'ARRETER (libres, start exclu).
    Contraste mesure : `WaaaghAbility$$GetPossibleMovementTiles` passe `0`,
    `VigilanceEternal`/`HeroicFusillade` passent `1`.

    Occupation = les unites VIVANTES de `ctx.units` (meme modele que `CanAddUnit`) ; `moving_team` =
    l'equipe de `unit` (un ENNEMI sur la tuile bloque la traversee, un allie non). Ordre de sortie =
    id de tuile croissant (le natif rend un `List<Tile>` issu d'un BFS ; ce noeud n'est consomme
    qu'a travers une INTERSECTION `op_BitwiseAnd`, cf. `tiles_unit_can_move_to_charge_target`, ou
    seul l'ordre de l'operande GAUCHE est observable). `board` absent -> []."""
    def __init__(self, unit: TargetsSelector, from_tile: TargetsSelector,
                 range_amount, can_reach_only: bool = False):
        self.unit, self.from_tile = unit, from_tile
        self.range_amount, self.can_reach_only = range_amount, bool(can_reach_only)

    def select(self, ctx):
        from .pathfinding.walk_pathfinder import get_movable_positions
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
        occ: dict = {}
        for other in ctx.units:
            if not _is_alive(other):
                continue
            p = _pos(other)
            if p is None:
                continue
            t = board.id_at(p[0], p[1])
            if t is not None:
                occ[t] = other.get("team")
        visited, stop = get_movable_positions(board, start, int(self.range_amount.evaluate(ctx)),
                                              occ, u.get("team"))
        return sorted(stop if self.can_reach_only else visited)


def tiles_unit_can_move_to_charge_target(unit: TargetsSelector, from_tile: TargetsSelector,
                                         target: TargetsSelector, range_amount,
                                         can_reach_only: bool = False) -> TargetsSelector:
    """`IdunBattleLogic.Entities.DSLFactory$$TilesUnitCanMoveToChargeTarget(unit, fromTile, target,
    range, canReachOnly)` — MIRROR du decompile, qui n'assemble QUE deux noeuds :

        CanAddUnit(AdjacentTiles(target))  op_BitwiseAnd  MovableTilesInRange(unit, fromTile,
                                                                             range, canReachOnly)

    = « tuiles LIBRES et marchables hex-adjacentes a la cible, que l'unite peut atteindre en <=
    `range` pas ». `op_BitwiseAnd` du domaine TILE = `TileIntersect` (ordre de l'operande GAUCHE
    preserve). Helper de FACTORY (comme `get_spawn_tile_selector`), pas une classe native."""
    return TileIntersect(CanAddUnit(AdjacentTiles(target)),
                         MovableTilesInRange(unit, from_tile, range_amount, can_reach_only))


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
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetSpawnTilesSelector`, `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$GetNextSpawnTile` et `IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$ExecuteBehaviour` (chaines a `PickRandomly`
    imbriques : le tirage vit dans le collapse, seul endroit qui voit `state.rng`)."""
    def __init__(self, tile_ids):
        self.tile_ids = [int(t) for t in (tile_ids or []) if isinstance(t, int)]

    def select(self, ctx):
        return list(self.tile_ids)


class OwnerTile(TargetsSelector):
    """Tuile COURANTE (réelle) de l'owner/caster — position du composant entité, PAS la tuile d'attaque
    balayée. `IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetSurroundingUnits` ancre son `SurroundingUnits(sel@0x160,
    range)` sur ce sélecteur (sel@0x160 = OWNER : cf. `StatAmount(@0x160,Health)`=maxHP caster dans
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetHealthToLose`, `HasFlag(@0x160)` du caster dans `Harvester.GetHits`).
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
    de l'événement déclencheur — ex. le TUEUR sur `OnPreDeath` (ActOfFaith accumulate IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaithAbility$$CreateBehaviour lit
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
    `IdunBattleLogic.Entities.DSLFactory$$InitializeShared` : `0x148 Owner · 0x150 Effect · 0x158 Actor · 0x160 Caster ·
    0x168 CasterTile · 0x170 CasterTiles · 0x178 Target · 0x180 ActiveTarget · 0x188 PreviousActiveTarget ·
    0x190 TargetTiles · 0x198 UnitFeetTiles`). C'est l'ELEMENT COURANT lie par le behaviour englobant :

      * sous-behaviour **on-appearance** d'un `Spawn` (`SpawnUnitOptions+0x18`, fire par
        `TriggerSpawnedUnitBehaviours`) -> le SUMMON fraichement pose. Consommateurs lus :
        `IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$ExecuteBehaviour`
        (`PerformAIAttackFromCurrentPosition(ActiveTarget@0x180)`),
        `IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$ExecuteBehaviour`
        (`UseNormalAttackIfAble(ActiveTarget@0x180, Target@0x178)`),
        `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$ExecuteBehaviour`
        (`UseNormalAttackIfAble(ActiveTarget@0x180, Entity(<unite cible>))`) ;
      * iteration d'un `ChainBehaviour` -> l'element rendu par le selecteur de l'iteration (Incursion :
        la TUILE de spawn, `Spawn(caster@0x160, ActiveTarget@0x180, unitId, opts)`).

    Accesseur = `ctx.active_target` (dict d'unite | id de tuile | liste) ; None hors behaviour liant."""
    def select(self, ctx):
        return getattr(ctx, "active_target", None)


class SurroundingTiles(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$SurroundingTiles(center, includeCenter, radius, ...)` : les TUILES du disque
    hex de rayon `radius` autour du centre (`center` = selecteur unit-domain OU position). `include_center`
    = l'argument natif `includeCenter` (0 aux call-sites portes : Poxwalkers IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$ExecuteBehaviour, SendInTheNextWave
    IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetPossibleSpawnTiles/IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$GetSpawnTilesSelector, CultDemagogue IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$ExecuteBehaviour -> centre EXCLU). Retour list[int] (tile ids), ordre
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
            # Le centre natif est une ENTITE-tuile : le domaine ID (list[int], ce que rendent
            # `AdjacentTiles`/`FixedTileIds`) est accepte au meme titre que (col,row) et le dict d'unite
            # — necessaire pour un cast TILE-TARGET (`IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$ExecuteBehaviour` :
            # `SurroundingTiles(Target@0x178 = la TUILE ciblee, range)`).
            centers = [_center_pos(c, board) for c in centers]
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


def _center_pos(c, board):
    """Position (col,row) d'UN element de centre : (col,row) tel quel, dict d'unite -> sa position,
    id de TUILE (int) -> `board.coord`. None si non resolvable (le caller saute)."""
    if isinstance(c, tuple) and len(c) == 2:
        return c
    if isinstance(c, bool):
        return None
    if isinstance(c, int):
        return board.coord(c) if c in board.by_id else None
    return _pos(c)


# --- Geometrie de TUILES par DIRECTION HEX (`IdunBattle.Utils.Hex`) -------------------------
#
# `CubeDirections..IdunBattle.Utils.Hex.CubeDirections$$.cctor` alloue SIX `int[3]` (coordonnees CUBE x/y/z aux offsets
# +0x20/+0x24/+0x28) puis les range dans l'array statique indexe par direction :
#     V0=(0,-1,1)  V1=(0,1,-1)  V2=(1,0,-1)  V3=(1,-1,0)  V4=(-1,1,0)  V5=(-1,0,1)
#     array[0..5] = [V0, V3, V2, V1, V4, V5]
# `IdunBattle.Utils.Hex.AxialCoordinate$$NeighbourAt` lit `array[dir][0]` (= dx, ajoute a la COLONNE) et
# `array[dir][2]` (= dz, ajoute au z cube `row - (col + (col&1))/2`) -> la table (dx, dz) ci-dessous.
# En offset (col,row) odd-q-UP (convention `hexgeo`, live-validee vs `boardGraph`) cela donne :
#     0 = S     1 = SE    2 = NE    3 = N     4 = NW    5 = SW
# CONFIRME LIVE (#90) : `DevastatingRefrain` bombarde `Target + dirs {3,1,5}` -> cast sur (2,3) a
# marque (2,2)=N, (3,4)=SE, (1,4)=SW.
_CUBE_DIRECTIONS = ((0, 1), (1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1))


def neighbour_at(col: int, row: int, direction: int) -> tuple:
    """`IdunBattle.Utils.Hex.AxialCoordinate$$NeighbourAt` : position de la tuile voisine dans la DIRECTION HEX
    `direction` (0..5, table `_CUBE_DIRECTIONS`). Le natif passe en cube (x=col, z=row-(col+(col&1))/2),
    ajoute (dx,dz) puis reconvertit — soit exactement `hexgeo.to_cube`/`from_cube` (meme parite
    odd-q-UP : le natif calcule `col + (col & 1)` quand le flag de parite @+0x18 vaut 0)."""
    dx, dz = _CUBE_DIRECTIONS[int(direction) % 6]
    x, _y, z = hexgeo.to_cube(int(col), int(row))
    return hexgeo.from_cube(x + dx, z + dz)


# `IdunBattle.Core.Services.BattleQuery$$GetTilesInTriangleShape` : par index de COIN (0..5), le COUPLE de directions
# hex des deux voisines ajoutees a la tuile-centre, dans l'ordre d'insertion du natif (lVar5 puis lVar6).
# Lu case par case sur les DEUX branches de parite du decompile (colonne paire / impaire), qui donnent
# le MEME couple de directions — la parite ne change que l'ecriture en offset.
_TRIANGLE_SHAPE_DIRECTIONS = {0: (5, 0), 1: (0, 1), 2: (5, 4), 3: (1, 2), 4: (4, 3), 5: (3, 2)}


class TilesInTriangleShape(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$TilesInTriangleShape` -> `IdunBattle.Entities.Selectors.TilesInTriangleShapeSelector$$Select`
    -> `IdunBattle.Core.Services.BattleQuery$$GetTilesInTriangleShape` : la tuile-CENTRE + les DEUX voisines du coin
    `direction` (0..5) = un triangle de 3 hexes. `direction > 5` -> le centre SEUL (garde native
    `if (5 < param_3) goto LAB_18106bd25`). Les voisines hors-plateau sont ignorees (le natif
    n'ajoute au HashSet que les `GetTileAt` non nuls).

    `center` = selecteur (position (col,row), dict d'unite, ou liste) ; `direction` = scalaire ou noeud
    VALEUR (`.evaluate`). Retour list[int] (tile ids), centre d'abord. board None -> []."""
    def __init__(self, center: TargetsSelector, direction):
        self.center, self.direction = center, direction

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        d = self.direction.evaluate(ctx) if hasattr(self.direction, "evaluate") else self.direction
        d = int(d)
        seen, out = set(), []
        for c in _tile_positions(self.center, ctx, board):
            for p in [c] + [neighbour_at(c[0], c[1], k)
                            for k in _TRIANGLE_SHAPE_DIRECTIONS.get(d, ())]:
                t = board.id_at(p[0], p[1])
                if t is not None and t not in seen:
                    seen.add(t)
                    out.append(t)
        return out


class TileFromVector(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$TileFromVector` -> `IdunBattle.Entities.Selectors.TileFromVectorSelector$$Select` : pour CHAQUE
    tuile de `tiles`, la VOISINE dans la direction hex `direction` (`IdunBattle.Utils.Hex.AxialCoordinate$$NeighbourAt`). Le natif abandonne si le noeud-vecteur (Nullable @+0x28) n'a pas de valeur, et n'ajoute
    que les tuiles resolues (hors-plateau -> ignorees). Retour list[int] (tile ids)."""
    def __init__(self, tiles: TargetsSelector, direction):
        self.tiles, self.direction = tiles, direction

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        d = self.direction.evaluate(ctx) if hasattr(self.direction, "evaluate") else self.direction
        if d is None:
            return []
        out = []
        for c in _tile_positions(self.tiles, ctx, board):
            p = neighbour_at(c[0], c[1], int(d))
            t = board.id_at(p[0], p[1])
            if t is not None:
                out.append(t)
        return out


class Walkable(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Walkable` : garde les tuiles WALKABLE (`BattleQuery.IsWalkableTile` =
    `TileExtensions.IsWalkable`, expose par `Board.walkable`). N'exige PAS que la tuile soit LIBRE
    (c'est `CanAddUnit` qui ajoute la contrainte d'occupation). Ordre de `source` preserve."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        return [t for t in self.source.evaluate(ctx) if board.walkable(t)]


class TilesOnSameElevation(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$TilesOnSameElevation` -> `IdunBattle.Entities.Selectors.TilesOnSameElevationSelector$$Select` :
    garde les tuiles de `tiles` dont l'ECART D'ELEVATION avec la tuile d'ANCRAGE (selecteur @+0x18, une
    seule tuile) est <= `max_diff` (@+0x28) — `TileExtensions.GetElevationDifference(tile, anchor) <=
    maxDiff`. Ancrage introuvable -> [] (le natif abandonne si le selecteur d'ancre ne rend rien)."""
    def __init__(self, anchor: TargetsSelector, tiles: TargetsSelector, max_diff: int = 0):
        self.anchor, self.tiles, self.max_diff = anchor, tiles, int(max_diff)

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        anchors = _tile_positions(self.anchor, ctx, board)
        if not anchors:
            return []
        at = board.id_at(anchors[0][0], anchors[0][1])
        if at is None:
            return []
        ae = board.elevation(at)
        return [t for t in self.tiles.evaluate(ctx)
                if abs(board.elevation(t) - ae) <= self.max_diff]


class EntitiesWithoutEffects(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$EntitiesWithoutEffects` -> `IdunBattle.Entities.Selectors.EntitiesWithoutEffectsSelector$$Select` : garde les entites de `source` qui NE portent AUCUN des `effect_types`
    (`EntityExtensions.HasOneOfEffects(entity, types, source-flag 6)` -> exclusion).

    Domaine MIXTE, comme le natif (il itere des `IEntity` indifferenciees) : une entite-UNITE (dict) est
    testee par `ctx.has_effect`, une entite-TUILE (id int) par `ctx.tile_has_effect`. Accesseur absent ->
    « aucun effet » (degradation fidele documentee dans `DslContext`)."""
    def __init__(self, source: TargetsSelector, effect_types):
        self.source = source
        self.effect_types = [int(e) for e in (effect_types or [])]

    def select(self, ctx):
        out = []
        for e in (self.source.evaluate(ctx) or []):
            if isinstance(e, dict):
                has = any(ctx.has_effect(e, et) for et in self.effect_types) \
                    if ctx.has_effect is not None else False
            else:
                has = any(ctx.tile_has_effect(int(e), et) for et in self.effect_types) \
                    if ctx.tile_has_effect is not None else False
            if not has:
                out.append(e)
        return out


class EntitiesWithAnyEffect(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$EntitiesWithAnyEffect` -> `IdunBattle.Entities.Selectors.EntitiesWithAnyEffectSelector$$Select` : JUMEAU EXACT (branche opposee) d'`EntitiesWithoutEffects` -- garde les entites de `source`
    qui portent AU MOINS UN des `effect_types` (`EntityExtensions.HasOneOfEffects(entity, types, ...,
    source-flag @+0x30)` -> INCLUSION ; le `Without` fait l'exclusion sur le MEME appel).

    Domaine MIXTE comme le natif (il itere des `IEntity` indifferenciees) : entite-UNITE (dict) testee par
    `ctx.has_effect`, entite-TUILE (id int) par `ctx.tile_has_effect`. Accesseur absent -> « aucun effet »
    -> l'entite est ECARTEE (symetrique fidele de la degradation d'`EntitiesWithoutEffects`, qui garde).

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.TwinSmartMissileSystemAbility$$GetAttackTargets`
    (`EntitiesWithAnyEffect(Enemies(caster, allUnits), 0x462=1122 Markerlight)`)."""
    def __init__(self, source: TargetsSelector, effect_types):
        self.source = source
        self.effect_types = [int(e) for e in (effect_types or [])]

    def select(self, ctx):
        out = []
        for e in (self.source.evaluate(ctx) or []):
            if isinstance(e, dict):
                has = any(ctx.has_effect(e, et) for et in self.effect_types) \
                    if ctx.has_effect is not None else False
            else:
                has = any(ctx.tile_has_effect(int(e), et) for et in self.effect_types) \
                    if ctx.tile_has_effect is not None else False
            if has:
                out.append(e)
        return out


class PickFirstN(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$First(source, amountNode)` -> `IdunBattle.Entities.Selectors.PickFirstNSelector` (`IdunBattle.DSL.APickSelector`, taille 0x30 =
    ctx/source/amount-node/flag) : les `amount` PREMIERS elements de la source, ordre PRESERVE.

    ⚠ A NE PAS CONFONDRE avec `IdunBattle.Entities.Selectors.PickAtIndexSelector$$Select` (taille 0x28, champ
    +0x20 = un INT d'index) qui rend `[source[index]]` : c'est une classe DISTINCTE, construite par une
    AUTRE factory. `DSLFactory.First` construit bien `PickFirstN`. Le noeud `First` de ce module (index 0
    par defaut) coincide avec `PickFirstN(1)` pour tous ses call-sites historiques (index non passe).

    `amount` = noeud VALEUR (`Direct(nrOfSummons)`) ou int. <=0 -> liste vide."""
    def __init__(self, source: TargetsSelector, amount):
        self.source, self.amount = source, amount

    def select(self, ctx):
        n = self.amount.evaluate(ctx) if hasattr(self.amount, "evaluate") else self.amount
        n = int(n or 0)
        if n <= 0:
            return []
        return list(self.source.evaluate(ctx))[:n]


class Otherwise(TargetsSelector):
    """`IdunBattle.DSL.TargetsSelector$$Otherwise(primary, fallback)` : le natif alloue un selecteur a DEUX
    branches (ctor : `+0x18 = primary`, `+0x20 = fallback`) qui rend `primary` s'il produit quelque chose,
    `fallback` sinon -- le FALLBACK d'un selecteur potentiellement VIDE.

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardSpotterAbility$$PickTiles`
    (`TilesUnitCanAttackFrom(free, caster, unitId, 1).Otherwise(free)` = si aucune tuile libre ne permet au
    summon d'attaquer la cible, on retombe sur TOUTES les tuiles libres adjacentes)."""
    def __init__(self, primary: TargetsSelector, fallback: TargetsSelector):
        self.primary, self.fallback = primary, fallback

    def select(self, ctx):
        v = self.primary.evaluate(ctx)
        if v:
            return v
        return self.fallback.evaluate(ctx)


class TilesBehindInLine(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$TilesBehindInLine(from, to, settings)` -> `IdunBattle.Entities.Selectors.TilesBehindInLineSelector$$Select` : les tuiles ALIGNEES au-dela de `to`, en partant de `to`, dans la direction
    `from -> to`. Geometrie CUBE droite (parite-INDEPENDANTE) DEJA live-reconciliee par les deux autres
    consommateurs portes du meme noeud (`IdunBattleLogic.Entities.Abilities.Active.Loki.ExcruciatingFrequenciesAbility$$GetAffectedTiles`
    `_line_tiles`, `IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetTilesInLine`) :
    `tile_k = cube(to) + k*dir`, `dir = cube(to) - cube(from)`, `k = 0..` -- la 1re tuile rendue EST `to`.

    `max_count` = le `Direct(n)` natif quand il est fourni (Excruciating : `nrOfTiles` ; DeathOnTheWind :
    `Get(nrOfTiles-1)`) ; None = pas de borne -> on prolonge JUSQU'AU BORD du plateau. Retour list[int]
    (tile ids). `from`/`to` normalises par `_tile_positions` (unite/id/position). board None -> [].

    GATE PAR TUILE — `IdunBattle.Core.Services.TileUtil$$IsTileValidForList(tile, refTile, checkWalkable,
    checkElevation=1)` (MIRROR ; le 4e argument est le litteral `1` dans `GetTilesBehind`) :
        if tileComponent+0x41 != 0            -> false
        if !checkWalkable                     -> return tileComponent+0x40 == 0
        if !TileExtensions.IsWalkable(tile)   -> false
        if refTile != null                    -> return |elev(refTile) - elev(tile)| < 2
    La ligne S'ARRETE au 1er echec (`return list`) — c'est un PREFIXE, pas un filtre.

    `check_walkable` / `update_reference` = les DEUX bools de la struct `settings` que chaque call-site
    alloue et passe a `IdunBattleLogic.Entities.DSLFactory$$TilesBehindInLine` (champs `+0x10` / `+0x11`),
    relayes par `IdunBattle.Entities.Selectors.TilesBehindInLineSelector$$Select` a
    `IdunBattle.Core.Services.BattleQuery$$GetTilesBehind(from, to, bool1, bool2, maxCount)` :
      * `+0x10 = check_walkable` : gate `IsWalkable` **ET** — c'est la consequence NON EVIDENTE —
        l'activation du gate d'ELEVATION (qui vit DANS la branche walkable de `IsTileValidForList`).
      * `+0x11 = update_reference` : `GetTilesBehind` re-affecte la tuile de REFERENCE d'elevation a la
        DERNIERE tuile ajoutee (marche pas-a-pas) au lieu de garder la tuile d'origine.
    INVENTAIRE des call-sites (lu au decompile, PAS deduit) :
      | ability | +0x10 | +0x11 |
      | `DarkTalonStrikeAbility$$GetTilesInLine`            | 1 | 1 |
      | `ExcruciatingFrequenciesAbility$$GetAffectedTiles`  | 1 | 1 |
      | `DeathOnTheWindAbility$$GetTilesInLine`             | 0 | 1 |
      | `ThriceBlessedConflagrationAbility$$GetTilesInLine` | 0 | 0 |
    Defauts `False/False` = le comportement HISTORIQUE (ThriceBlessed, inchange).

    RESIDU documente : la branche `check_walkable == False` du natif teste `tileComponent+0x40 == 0`
    (drapeau de tuile SEUL, sans le composant MUR) ; le port utilise `board.walkable` (capture live de
    `TileExtensions.IsWalkable`, qui FOND le drapeau de tuile ET le mur). Inerte pour ses deux call-sites
    (`FilterContinuous(HasUnit & AreEnemies)` en aval : une tuile non-walkable ne porte pas d'unite)."""
    def __init__(self, frm: TargetsSelector, to: TargetsSelector, max_count=None,
                 check_walkable: bool = False, update_reference: bool = False):
        self.frm, self.to, self.max_count = frm, to, max_count
        self.check_walkable = bool(check_walkable)
        self.update_reference = bool(update_reference)

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        src = _tile_positions(self.frm, ctx, board)
        dst = _tile_positions(self.to, ctx, board)
        if not src or not dst:
            return []
        ox, _oy, oz = hexgeo.to_cube(src[0][0], src[0][1])
        ax, _ay, az = hexgeo.to_cube(dst[0][0], dst[0][1])
        dx, dz = ax - ox, az - oz
        if dx == 0 and dz == 0:
            return []
        n = self.max_count
        n = (n.evaluate(ctx) if hasattr(n, "evaluate") else n)
        n = int(n) if n is not None else None
        ref = board.id_at(src[0][0], src[0][1])       # `lVar6` = MainTileEntity(from) au 1er tour
        out, k = [], 0
        while n is None or len(out) < n:
            p = hexgeo.from_cube(ax + dx * k, az + dz * k)
            t = board.id_at(p[0], p[1])
            if t is None:                      # sortie de plateau -> fin de ligne
                break
            if not self._is_tile_valid_for_list(board, t, ref):
                break                          # `return list` natif : PREFIXE, pas un filtre
            out.append(t)
            if self.update_reference:          # settings+0x11 : la reference d'elevation suit la ligne
                ref = t
            k += 1
            if n is None and k > 64:           # garde-fou (plateau borne ; jamais atteint)
                break
        return out

    def _is_tile_valid_for_list(self, board, tile_id, ref_tile_id) -> bool:
        """`IdunBattle.Core.Services.TileUtil$$IsTileValidForList` (cf. la docstring de la classe)."""
        if not board.walkable(tile_id):
            return False
        if not self.check_walkable:
            return True                        # branche `!checkWalkable` : PAS de gate d'elevation
        if ref_tile_id is None:
            return True
        return abs(board.elevation(ref_tile_id) - board.elevation(tile_id)) < 2


class FilterContinuous(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$FilterContinuous(source, predicate)` = MEME construction que
    `IdunBattleLogic.Entities.DSLFactory$$Filter` (`FromTriggerSelector`) + le FLAG de court-circuit : on garde
    le PREFIXE CONTIGU d'elements satisfaisant le predicat et on S'ARRETE au premier echec (une « ligne »
    d'ennemis s'interrompt au premier trou), la ou `Filter` balaie tout.

    Meme binding sujet que `Filter` (l'element courant est lie au slot sujet du contexte avant evaluation).
    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$GetTilesInLine`."""
    def __init__(self, source: TargetsSelector, predicate: TargetsSelector):
        self.source, self.predicate = source, predicate

    def select(self, ctx):
        out = []
        for item in self.source.evaluate(ctx):
            if not self.predicate.evaluate(replace(ctx, subject=item)):
                break                          # court-circuit (flag `Continuous`)
            out.append(item)
        return out


def _entity_pos(item, board):
    """Position (col,row) d'UN element du domaine MIXTE (dict d'unite / id de tuile / position) — mirror
    du `EntityExtensions.GetMainTile(entity)` natif, qui rend la tuile d'une UNITE comme d'une TUILE.
    None si non resolvable (board absent pour un id de tuile, unite sans position)."""
    if isinstance(item, dict):
        return _pos(item)
    if isinstance(item, bool):
        return None
    if isinstance(item, int):
        if board is None or item not in board.by_id:
            return None
        c = board.coord(item)
        return (int(c[0]), int(c[1]))
    if isinstance(item, (tuple, list)) and len(item) == 2 and all(isinstance(x, int) for x in item):
        return (int(item[0]), int(item[1]))
    return None


def _tile_positions(sel: TargetsSelector, ctx, board) -> list:
    """Normalise l'evaluation d'un selecteur en liste de POSITIONS (col,row) : id de tuile (int) ->
    `board.coord`, position (col,row) -> telle quelle, dict d'unite -> sa position, liste -> chacun.
    Helper PARTAGE des selecteurs tile-domain ancres sur une tuile (triangle/vecteur/elevation) — le
    natif, lui, manipule des entites-tuiles homogenes."""
    v = sel.evaluate(ctx)
    if v is None:
        return []
    if isinstance(v, tuple) and len(v) == 2 and all(isinstance(x, int) for x in v):
        items = [v]
    elif isinstance(v, (dict, int)):
        items = [v]
    else:
        items = list(v)
    out = []
    for it in items:
        p = _entity_pos(it, board)             # domaine mixte unite / id de tuile / position
        if p is not None:
            out.append((int(p[0]), int(p[1])))
    return out


class UnitsWithVisualId(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$UnitsWithVisualId(visualIdValue, mode)` = `UnitsWithIdSelector(ctx,
    factory+0x80, visualIdValue, mode)`. La source est le slot PARTAGE `factory+0x80` (pose par
    `IdunBattleLogic.Entities.DSLFactory$$InitializeShared`, == la source d'`AllUnits`/`Friends(caster, @0x80)` de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour`) -> le selecteur est **BOARD-WIDE : AUCUN RAYON**, a ne pas
    confondre avec `UnitsWithIds(source, ids)` (qui FILTRE un sous-ensemble deja restreint, ex.
    `SurroundingFriends` de SupremeCommander IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour).

    Consommateurs lus : `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour` (site IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour+0x2f6+) et son homologue
    `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetTriggerSummonsBehaviour`, tous deux
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
    """`IdunBattleLogic.Entities.DSLFactory$$UnitsWithId(source, idValue, mode)` = `UnitsWithIdSelector(ctx, source,
    TestUnitProvider(idValue), mode)` : le VOLET MONO-ID d'`UnitsWithIds` (qui, lui, UNIONNE les volets sur
    un tableau d'ids). Filtre `source` par `IdunBattle.Entities.UnitExtensions$$HasUnitId(unit, id)`.
    Consommateur lu : `IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$ExecuteBehaviour`
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
    """`IdunBattleLogic.Entities.DSLFactory$$Cache(source)` → `IdunBattle.Entities.Selectors.CacheSelector$$Select` : **MÉMOÏSE** le résultat
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
    """`IdunBattleLogic.Entities.DSLFactory$$Entity(ref)` : résout la RÉFÉRENCE passée en argument (rôle
    caster/target/subject) en ENTITÉ. Wrapper fin — l'opérande (souvent un nœud rôle, ex. `Subject`)
    évalue déjà l'entité."""
    def __init__(self, ref):
        self.ref = ref

    def select(self, ctx):
        return self.ref.evaluate(ctx)


class Nothing(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Nothing` : sélecteur VIDE (retourne `[]`). Classe DISTINCTE de `Null`."""
    def select(self, ctx):
        return []


class Null(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Null` : entité/valeur NULLE (retourne `None`). Même classe qu'`Entity` avec
    arg null ; distinct de `Nothing` (ensemble vide)."""
    def select(self, ctx):
        return None


class EffectSource(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$EffectSource` : entité SOURCE de l'effet COURANT (`ctx.effect`). NON captable
    hors application d'effet → None si `ctx.effect` absent."""
    def select(self, ctx):
        return _effect_field(ctx.effect, "source", None)


class EffectFromOwner(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$EffectFromOwner(effectType)` → `EffectWithTypeSelector IdunBattle.Entities.Selectors.EffectWithTypeSelector$$Select` : effets
    du type possédés par l'owner. NON captable offline (effets par unité absents du state) → `[]` défaut."""
    def __init__(self, effect_type):
        self.effect_type = effect_type

    def select(self, ctx):
        return []


class EffectsFromUnitSource(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$EffectsFromUnitSource(source, effectType)` -> `EffectWithTypeSelector
    IdunBattle.Entities.Selectors.EffectWithTypeSelector$$Select` (frere d'`EffectFromOwner`, keye sur la SOURCE au lieu de l'owner) : les INSTANCES d'effet
    du type `effect_type` dont le `EffectComponent.SourceUnit @+0x10` est l'unite `source`. Domaine =
    ENTITES-EFFET (pas des unites) -> consomme par `OwnerOfEffect` qui remonte a leurs porteurs.

    Seul call-site porte : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateBehaviour`
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
    """`IdunBattleLogic.Entities.DSLFactory$$OwnerOfEffect(effects)` : remonte de chaque ENTITE-EFFET a l'UNITE qui la
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
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$GetSpawnTileSelector` (mirror 1:1, confirme LIVE #200 tracer-v2) =
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
