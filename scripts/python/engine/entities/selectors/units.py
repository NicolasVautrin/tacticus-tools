"""Selecteurs du domaine UNITE + algebre d'ensembles (kind S).

Mirror de `IdunBattle.Entities.Selectors` pour tout ce qui rend des UNITES : voisinage, camp,
faction, traits, vivants, plus les combinateurs qui s'y appliquent (`And`/`Sub`/`Union`/`Filter`/
`First`/`Unique`/`SortBy*`). Tranche 1 du decoupage de `selectors.py` -- cf. `__init__.py`."""
from __future__ import annotations

from dataclasses import replace

import hexgeo

from ... import battle_query          # mirror UNIQUE de GetTilesBehind/IsTileValidForList (#117/#124)
from ...dsl.base import (TargetsSelector, Const, _pos, _feet, _within, _is_alive, _units_of,
                         _effect_field, resolve_unit, _tile_enum_rank, _occupants_by_tile,
                         _origin_tiles, _main_tile)
from ._shared import _entity_pos, _tile_positions
# #270-r4 : les deux litteraux de ce module DESIGNENT, et leur enum est LU au decompile --
# `UnitsWithTrait(source, 0x10)` (le parametre `trait` de `DSLFactory$$UnitsWithTrait`) et
# `has_unit_flag(u, 0xe)` (le parametre `flag` d'`UnitExtensions$$HasFlag`).
from ..traits.unit_trait import UnitTrait
from ..unit_flag import UnitFlag
# #585 : le 3e/4e argument `selectionType` des factories `DSLSelectors`, LU par
# `IdunBattle.DSL.TargetsSelector$$SelectUnit` -> `UnitExtensions$$MatchesUnitSelectionType`.
# Le FOYER du predicat existe depuis #524 (face DECISION, `playbook/adjacency.py`) : on l'appelle,
# on n'en ecrit pas un second.
from ..unit_selection_type import UnitSelectionType, matches_unit_selection_type
from ...battle_query import is_target_tile_obscured
# #433-r4-r1-r4-r1 : FOYER du canal d'elevation (tri-etat, l'inconnu est OMIS et non rabattu sur 0).
# Import de NIVEAU MODULE, aucun cycle : `dsl.base` -- que ce module importe deja ci-dessus -- tire
# lui-meme `entities.pathfinding.board` au niveau module.
from ..pathfinding.board import elevations_by_pos


def _selection_ok(u, selection_type, ctx) -> bool:
    """`IdunBattle.DSL.TargetsSelector$$SelectUnit(entity, selectionType)` cote RUNNER : derive les
    deux predicats que le foyer `matches_unit_selection_type` (#524) attend, puis DELEGUE.

    Le foyer vit dans `engine/entities/unit_selection_type.py` et sert deja la face DECISION
    (`playbook/adjacency.unit_matches`, qui derive `targetable` de `UNTARGETABLE_EFFECT_TYPES`).
    Ici le substrat est l'ECS : `alive`/`hp` du dict d'unite, et `ctx.has_unit_flag` pour le flag
    `0x11`. Un SECOND port du predicat aurait ete un fork.

    TRI-ETAT preserve : `ctx.has_unit_flag` absent -> `targetable = None` = **PAS MESURE**, et le
    foyer degrade alors la clause en VRAI. Un `False` invente ecarterait une unite que le natif
    compte."""
    hf = getattr(ctx, "has_unit_flag", None)
    targetable = None if hf is None else (not bool(hf(u, int(UnitFlag.Untargetable))))
    alive = bool(u.get("alive", True)) and (u.get("hp") or 0) > 0
    return matches_unit_selection_type(selection_type, alive=alive, targetable=targetable)


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
        # ordre = `SurroundingTiles` (triple boucle CUBE d'`IterateSurroundingTiles`), cf. `_tile_enum_rank`
        return _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx),
                       include_center=self.include_center,
                       board=getattr(ctx, "board", None), order="surrounding")


class AdjacentEnemies(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$AdjacentEnemies(caster)` = `Enemies(Units(AdjacentTiles(caster)) - {caster})`
    = ennemis (team != caster) à dist <= radius du caster, self exclu."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector | None = None):
        self.center, self.radius = center, radius or Const(1)

    def select(self, ctx):
        # ordre = `AdjacentTiles` (liste d'adjacence STOCKEE, `boardGraph.neighbours` brut) -- R28-1
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx),
                       board=getattr(ctx, "board", None), order="adjacent")
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
        # ordre = `AdjacentTiles` (liste d'adjacence STOCKEE, `boardGraph.neighbours` brut) -- R28-1
        return _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx),
                       board=getattr(ctx, "board", None), order="adjacent")


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
    dict -> `[dict]`), pour soustraire aussi bien une liste qu'une unite seule.

    DOMAINE MIXTE (natif : `op_Subtraction` travaille sur des ENTITES ECS, unites comme TUILES) : la cle
    de comparaison est l'`id` pour un dict d'unite, et l'ELEMENT LUI-MEME pour un id de tuile (int) ou une
    position `(col,row)` -- le natif compare des references d'entite, sans distinguer le domaine.
    Consommateur tile-domain : `IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$GetAffectedTiles`
    (`SortReverse(TilesBehindInLine(...)) op_Subtraction Blocking(...)`)."""
    def __init__(self, a: TargetsSelector, b: TargetsSelector):
        self.a, self.b = a, b

    @staticmethod
    def _key(x):
        """Cle d'identite d'une entite du domaine MIXTE : `id` d'un dict d'unite, sinon l'element brut
        (id de tuile / position) -- une liste devient un tuple pour rester hashable."""
        if isinstance(x, dict):
            return x.get("id")
        return tuple(x) if isinstance(x, list) else x

    def select(self, ctx):
        bset = {self._key(u) for u in _units_of(self.b, ctx)}
        return [u for u in _units_of(self.a, ctx) if self._key(u) not in bset]


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
            # LE SLOT LIE EST `ability+0x180` = **ActiveTarget** (`FromTriggerSelector$$Select` ecrase
            # ce slot a chaque item). Le port le vehiculait par `ctx.subject` SEUL -- suffisant pour
            # les predicats ecrits avec `Subject()`, mais un arbre qui CITE le slot natif sous son nom
            # (`IsObscured(ActiveTarget@+0x68, Target@+0x60)` de `WallOfMirrorsAbility$$GetPossible
            # Tiles`) lisait alors `ctx.active_target`, resté au liant ENGLOBANT. On pose donc les DEUX
            # noms du MEME slot : aucun predicat existant ne lit `active_target` sous un `Filter`.
            if self.predicate.evaluate(replace(ctx, subject=item, active_target=item)):
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
    `IdunBattleLogic.Entities.DSLFactory$$MinDistance` — **distance HEX, jamais un pathfinding** :
    `IdunBattle.Entities.Formulas.MinDistanceFormula$$Calculate` prend le `Min` sur toutes les paires
    (a de selA, b de selB) de `IdunBattle.Entities.Components.PositionComponent$$Distance`, qui est
    `AxialCoordinate$$ToCubeCoordinate` ×2 puis `CubeCoordinate$$Distance = Max(|dx|,|dy|,|dz|)`.
    Le `Min` sur les paires est ce qui donne son sens au préfixe `Min-` : pour un sélecteur d'UNITÉ il
    n'y a qu'un `PositionComponent` (donc une seule paire), mais pour un sélecteur de TUILES (ex.
    `CasterTiles@0x170`) il balaie l'empreinte entière. Mirror : `entities.traits.combat.min_distance`
    pour le cas 1↔1. Donc : un candidat À DISTANCE
    ÉGALE du caster que la cible (unité LATÉRALE, delta 0 sur l'anneau) est EXCLU (`2 > 2` faux) ; seul
    l'« away » strictement plus loin (delta +1) passe. Confirmé LIVE (test_plasma_cannon_lateral_live,
    probe_udb_case48) : lateral d(caster)==d_ct EXCLU du splash, away d(caster)==d_ct+1 INCLUS.
    `dist` = distance hex ; caster = `ctx.caster_pos` (tuile d'attaque balayée). Élévation :
    `IdunBattle.Entities.Selectors.TilesOnSameElevationSelector$$Select` garde si `GetElevationDifference(cand, target)
    <= maxDiff` (ctor +0x28 = 1 ici) → TOLÉRANCE ±1, pas une égalité stricte (prouvé step-11 :
    78 elev1 derrière 82 elev2 inclus par le natif). Dégradé no-op sans `ctx.elev_by_pos`.

    ORDRE (R28-1) : la chaîne part de `SurroundingTiles(target, 1, 1)`, donc l'énumération est celle de
    `TileQuery$$IterateSurroundingTiles` (triple boucle CUBE, cf. `_tile_enum_rank`) — les filtres en aval
    (`Enemies`, `TilesOnSameElevation`, `FromTrigger`) la PRÉSERVENT (chacun reconstruit une liste dans
    l'ordre reçu). Ça décide QUI est piqué par le `PickRandomly(UnitsDirectlyBehind(...), 2)` de
    PlasmaCannon/Supercharge dès qu'il y a > 2 candidats derrière la cible. Sans `ctx.board` : ordre
    `ctx.units` (dégradation, pas un mirror)."""

    def select(self, ctx):
        # EMPREINTES (#433-r3-r1a). Le decompile de `IdunBattleLogic.Entities.DSLSelectors$$UnitsDirectlyBehind`
        # se lit terme a terme : `SurroundingTiles(target, includeCenter:1, 1) op_Subtraction Tiles(target)`
        # -> l'anneau part de TOUS les pieds de la cible et n'en retranche que sa MAIN TILE ;
        # `Units(ring, unique:1, selectionType:3)` -> occupant par n'importe quel pied ;
        # `AmountIsGreater(MinDistance(Tiles(caster), It), MinDistance(Tiles(caster), Tiles(target)))`
        # -> le SEUIL compare deux MAIN TILES (`Tiles` = `UnitsMainTilesSelector`), tandis que la
        # distance du CANDIDAT est un MIN sur SES pieds (`It` est un selecteur d'unite, et
        # `MinDistanceFormula` balaie `SelectTiles` des deux cotes).
        tfeet = _feet(ctx.target)
        tmain = _main_tile(ctx.target)
        cpos = ctx.caster_pos or _pos(ctx.caster)
        if not tfeet or cpos is None:
            return []
        ct = (ctx.caster or {}).get("team")
        tid = (ctx.target or {}).get("id")
        d_ct = hexgeo.distance(cpos, tmain)
        out = []
        for u in ctx.units:
            if not _is_alive(u):                                   # cands = Enemies(Units(ring)) : occupation (#57m)
                continue
            feet = _feet(u)
            if not feet or u.get("id") == tid or u.get("team") == ct:
                continue
            # anneau R1 de la cible = union des anneaux de ses pieds, MOINS sa seule main tile
            ring = [p for p in feet
                    if p != tmain and any(hexgeo.distance(p, t) <= 1 for t in tfeet)]
            if not ring:
                continue
            if ctx.elev_by_pos is not None:                        # TilesOnSameElevationSelector (maxDiff=1)
                et = ctx.elev_by_pos.get(tmain)
                ring = [p for p in ring
                        if et is None or ctx.elev_by_pos.get(p) is None
                        or abs(et - ctx.elev_by_pos.get(p)) <= 1]
                if not ring:
                    continue
            if min(hexgeo.distance(cpos, p) for p in feet) > d_ct:  # STRICT (AmountIsGreater) : « derrière » = plus loin
                out.append(u)
        board = getattr(ctx, "board", None)
        if board is None or len(out) < 2:
            return out
        rank = _tile_enum_rank(board, tfeet, 1, "surrounding")      # SurroundingTiles(target, 1, 1)
        if not rank:
            return out
        big = len(rank) + 1
        return sorted(out, key=lambda u: min([rank.get(f, big) for f in _feet(u)] or [big]))  # STABLE


class Friends(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Friends(reference, source)` → `UnitsByTeamSelector(ctx, reference, source,
    flag=1)` (symétrique exact d'`Enemies` flag=0) : garde les unités de `source` ALLIÉES au **RÉFÉRENT**.

    Le référent est le 1ᵉʳ argument NATIF (`param_2`), pas une constante : `reference=None` (défaut) = le
    CASTER — le cas de tous les call-sites portés jusqu'ici (`Friends(caster@0x160 / Owner@0x148, ...)`,
    ex. `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$HasMinimumAdjacentFriendlyUnits` = `Friends(Owner@0x148, ...)`).
    `IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets` passe `Friends(target@0x178, ...)` = alliés **de la
    CIBLE** (donc les summons ENNEMIS du caster) — d'où le paramètre.

    `selection_type` = le 4ᵉ argument NATIF (`DSLSelectors$$Friends(this, of, entities,
    selectionType)`), que `UnitsFromFactionSelector$$Select` transmet à `SelectUniqueUnits(source,
    entities, selectionType)` — donc à `MatchesUnitSelectionType` PAR ÉLÉMENT. `None` (défaut) =
    aucun filtre, le comportement HISTORIQUE de tous les call-sites déjà portés : ce paramètre n'a
    de valeur que là où le littéral a été RE-LU (`WarHowlAbility$$OtherBuffTargets` passe `3`).
    ⚠ Il MORD, et c'est mesuré (#585) : `OnlyAliveAndTargetable` écarte une unité en DEEP STRIKE
    (`UnitFlag.Untargetable`) que tous les autres filtres retiennent. Relever le littéral aux ~100
    call-sites portés est une tranche à part — même régime que le flag `unique` de `Units`."""
    def __init__(self, inner: TargetsSelector, reference: TargetsSelector | None = None,
                 selection_type=None):
        self.inner, self.reference = inner, reference
        self.selection_type = selection_type

    def select(self, ctx):
        ref = resolve_unit(self.reference, ctx) if self.reference is not None else ctx.caster
        rt = (ref or {}).get("team")
        st = self.selection_type
        return [u for u in self.inner.evaluate(ctx)
                if u.get("team") == rt
                and (st is None or _selection_ok(u, st, ctx))]


class Units(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Units(tiles)` → `UnitsOnTilesSelector` : unités DEBOUT sur les tuiles du
    sélecteur source (`tiles` évalue → liste de positions). Généralise l'inline de SurroundingUnits.
    (Mode d'occupation main/steppable = raffinement inerte offline : 1 unité par tuile.)

    ORDRE = celui des TUILES (le natif ITERE le sélecteur de tuiles et résout l'occupant de chacune),
    PAS l'ordre des entités. Observable dès qu'un `Foreach` consomme le résultat : le beam de
    `DarkTalonStrikeAbility$$ExecuteBehaviour` frappe la CIBLE puis les tuiles de la ligne en s'éloignant
    (cascade live u79 @(5,5) puis u77 @(5,6)) — l'ordre d'entité aurait donné u77 d'abord et désynchronisé
    `state.rng`. Dédoublonnage par id d'unité (première occurrence conservée) : une même tuile peut
    apparaître deux fois dans une union de sélecteurs.

    OCCUPANT = `dsl.base._occupants_by_tile` (#433-r3-r1a), le foyer UNIQUE : le natif resout par
    `IdunBattle.DSL.TargetsSelector$$SelectUnit` -> `IdunBattle.Entities.UnitExtensions$$GetUnit`, qui
    lit le `TileContentComponent` de la tuile et re-resout l'entite-PIED qui s'y trouve. **N'importe
    quel pied d'une unite multi-hex resout en cette unite** ; l'index par main tile d'avant voyait VIDE
    une tuile sous un pied secondaire.

    ⚠ DEDOUBLONNAGE INCONDITIONNEL = residu `#433-r3-r1a-r1`. Le natif a DEUX regimes, tranches par le
    flag `unique` du ctor (`IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$.ctor(state,
    tilesSelector, unique, selectionType)`, pose par `IdunBattleLogic.Entities.DSLSelectors$$Units`) :
    `unique == 0` -> `IdunBattle.DSL.TargetsSelector$$SelectAllUnits` (List, AUCUN dedoublonnage : une
    unite occupant DEUX tuiles du selecteur sort DEUX FOIS) ; `unique != 0` ->
    `$$SelectUniqueUnits` (ArraySet). Le port fait toujours l'equivalent d'`unique = 1` -- c'est le flag
    qu'ont les deux call-sites natifs LUS (les deux `Units(..., 1, 3)` de
    `IdunBattleLogic.Entities.DSLSelectors$$UnitsDirectlyBehind`). Relever le flag aux ~100 call-sites
    portes est une tranche a part ; le regime `unique = 0` n'etait de toute facon PAS atteignable avant
    ce commit (l'index par main tile rendait au plus une tuile par unite)."""
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
        # Occupation de tuile par EMPREINTE (#433-r3-r1a) ; VIVANTS seulement (#57m : un mort n'est
        # plus DEBOUT sur sa tuile -> son TileContentComponent est vide).
        occupant = _occupants_by_tile(ctx.units)
        out, seen = [], set()
        for it in items:
            if isinstance(it, bool):
                continue
            if isinstance(it, dict):
                # Une ENTITE-unite en entree : le natif la rend telle quelle (`SelectUnit` court-circuite
                # sur `IsUnit`). Le port passe par sa main tile, qui reindexe sur elle-meme via
                # `_occupants_by_tile` -- meme resultat, et le filtre VIVANT y reste applique.
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

    EMPREINTE (#433-r3-r1a) — le prédicat est `IdunBattle.Entities.Triggers.IsUnitOnTileEffectTrigger$$ShouldTrigger`,
    et il est EXISTENTIEL sur les pieds :

        unit = <selecteur@+0x10>.SelectUnit(entities, 0);   if (unit == null) return false;
        foreach (tile in EntityExtensions.IterateTiles(unit, state))
            if (EntityExtensions.HasOneOfEffects(tile, effectsDb, config, true, 6)) return true;
        return false;

    ⇒ vrai dès qu'**UNE** tuile de l'unité porte l'effet ; le port ne testait que la main tile."""
    def __init__(self, source: TargetsSelector, effect_type: int):
        self.source, self.effect_type = source, int(effect_type)

    def select(self, ctx):
        board = getattr(ctx, "board", None)
        the = getattr(ctx, "tile_has_effect", None)
        if board is None or the is None:
            return []
        out = []
        for u in _units_of(self.source, ctx):
            for p in _feet(u):                      # IterateTiles(unit, state) -- existentiel
                tid = board.id_at(p[0], p[1])
                if tid is not None and the(tid, self.effect_type):
                    out.append(u)
                    break
        return out


class Tiles(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Tiles(units)` → `IdunBattle.Entities.Selectors.UnitsMainTilesSelector$$Select` (ctor mislabelé
    "SortReverse", singleton distinct DAT_183278e98) : unités → leur MainTile. Retour list[position].
    `units` normalisé par `_units_of` (comme `AdjacentTiles`) : accepte une unité SEULE (dict, ex.
    `Tiles(Target())` d'OnFireDamage) ou une liste — sans quoi itérer un dict nu rendrait ses CLÉS.

    `as_ids` — le natif rend des ENTITES-tuile ; le port a historiquement matérialisé la tuile par sa
    POSITION `(col,row)`. `as_ids=True` (board requis) rend l'**ID d'entité-tuile**, ce qu'exige toute
    composition avec un nœud tile-domain ID (`AdjacentTiles`, qui rend des ids) — sans quoi un
    `op_Subtraction` compare des positions à des ids et ne soustrait RIEN (silencieusement). Call-site :
    `FragstormAbility$$ExecuteBehaviour` = `AdjacentTiles(target) − Tiles(Friends(caster, …))`."""
    def __init__(self, units: TargetsSelector, as_ids: bool = False):
        self.units, self.as_ids = units, bool(as_ids)

    def select(self, ctx):
        pos = [p for p in (_pos(u) for u in _units_of(self.units, ctx)) if p is not None]
        if not self.as_ids:
            return pos
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        return [t for t in (board.id_at(p[0], p[1]) for p in pos) if t is not None]


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
    TOUT.

    `selection_type` = le 3ᵉ argument NATIF (`DSLSelectors$$UnitsWithoutTrait(this, source, trait,
    selectionType)`), transmis à `SelectUniqueUnits` puis à `MatchesUnitSelectionType` par élément.
    `None` (défaut) = aucun filtre = comportement HISTORIQUE. Cf. `Friends` pour le détail et la
    mesure qui l'a rendu obligatoire (#585)."""
    def __init__(self, source: TargetsSelector, trait, selection_type=None):
        self.source, self.trait = source, trait
        self.selection_type = selection_type

    def select(self, ctx):
        ht = ctx.has_trait or (lambda u, t: False)
        st = self.selection_type
        return [u for u in self.source.evaluate(ctx)
                if not ht(u, self.trait)
                and (st is None or _selection_ok(u, st, ctx))]


class UnitsWithoutRangedWeapons(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$UnitsWithoutRangedWeapons(entities)` ->
    `IdunBattle.Entities.Selectors.UnitsWithoutWeaponsSelector$$Select` : garde les entites de
    `source` dont AUCUN profil d'arme n'est `IsRanged`.

    Corps natif relu (`UnitsWithoutWeaponsSelector$$Select`), la boucle VERBATIM :

        foreach (entity in this.<+0x18>.SelectUniqueUnits(entities)) {
            unit = UnitExtensions.GetUnit(entity, this.<+0x10>);
            if (unit != null) {
                foreach (w in unit.WeaponsComponent.Weapons)      // == $$HasRangedWeapon inline
                    if (w.IsRanged) goto NEXT_ENTITY;             // porteuse d'arme distance -> JETEE
            }
            result.Add(entity);                                   // y compris si `unit == null`
        }

    DEUX points LUS, pas deduits :
      * le predicat est `WeaponProfile$$get_IsRanged` (= `get_IsMelee ^ 1`, donc seuil `Range >= 2`),
        **pas** « l'unite a un `Range` » -- le tri d'`UnitExtensions$$IsRanged` est un AUTRE corps
        (cf. `engine.services.ability_range._has_ranged_weapon`) ;
      * une entite dont `GetUnit` rend `null` (une TUILE, une MoW) est **GARDEE** : le natif saute
        alors tout le bloc d'armes et tombe sur le `Add`. Le port le mirrore en gardant l'element
        des que le predicat ne peut pas le classer (`visualId` absent).

    SUBSTRAT : `ctx.has_ranged_weapon(unit)` -- meme patron d'accesseur que `has_trait`/`faction_of`
    (foyer `engine.services.battle_query.has_ranged_weapon`, cable par `entities_from_state`).
    Accesseur ABSENT -> aucun filtre (tout est garde) : c'est la MEME polarite que la branche
    `unit == null` du natif, et la seule qui ne fabrique pas un refus depuis une non-mesure.

    `selection_type` : ce noeud-ci n'en prend PAS cote natif (`DSLSelectors$$
    UnitsWithoutRangedWeapons(this, entities)` a DEUX arguments, et
    `UnitsWithoutWeaponsSelector$$Select` appelle `SelectUniqueUnits` avec le litteral `1` --
    `OnlyAlive`, lu au decompile). Il est donc porte en dur, sans parametre : un `selection_type`
    optionnel ici inviterait a passer le `3` de l'appelant, qui n'appartient PAS a ce noeud.

    Call-site porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.WarHowlAbility$$
    ExecuteBehaviour` / `$$OtherBuffTargets` (1106, `spaceBlackmane`)."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        # `SelectUniqueUnits(<+0x18>, entities, 1)` -- le litteral `1` = `OnlyAlive` est LU dans
        # `UnitsWithoutWeaponsSelector$$Select` (`FUN_180026100(3, ..., source, entities, 1)`).
        units = [u for u in self.source.evaluate(ctx)
                 if _selection_ok(u, UnitSelectionType.OnlyAlive, ctx)]
        hrw = getattr(ctx, "has_ranged_weapon", None)
        if hrw is None:
            return list(units)                      # accesseur non cable -> aucun filtre invente
        return [u for u in units if not hrw(u)]


def non_steppable_or_object_units(source: TargetsSelector) -> TargetsSelector:
    """`IdunBattleLogic.Entities.DSLSelectors$$NonSteppableOrObjectUnits(source, selectionType)` --
    MIRROR de la FACTORY : le natif N'ALLOUE AUCUN selecteur dedie, il COMPOSE textuellement

        a = UnitsWithoutTrait(source, 0x1b, selectionType)      # 27 = UnitTrait.Steppable
        b = TargetsSelector.op_BitwiseAnd(source, a)
        c = UnitsWithoutTrait(source, 0xd,  selectionType)      # 13 = UnitTrait.Object
        return TargetsSelector.op_BitwiseAnd(b, c)

    -> `source & sans-Steppable & sans-Object`. On mirror la composition telle quelle (les deux
    `And` compris) plutot que de la simplifier : c'est la structure LUE, et l'`And` du port
    (`op_BitwiseAnd`) preserve l'ordre de son operande GAUCHE, donc l'ordre du `source` traverse.

    ⚠ Le `0xd` de CE site est un `UnitTrait` (`Object`), pas un `DamageProfileType` -- l'ordinal 13
    nomme les deux, et `HellfyreMissileRackAbility$$ExecuteBehaviour` les utilise TOUS LES DEUX dans
    la meme expression (`NonSteppableOrObjectUnits(...)` avec le trait, `HasTakenDamage...(..., 0xd)`
    avec `DamageProfileType.Psychic`). C'est exactement le regime ou l'ordinal nu ment en silence.

    Consommateurs natifs lus : `HellfyreMissileRackAbility$$ExecuteBehaviour` / `$$GetAffectedUnits`."""
    return And(And(source, UnitsWithoutTrait(source, int(UnitTrait.Steppable))),   # 0x1b
               UnitsWithoutTrait(source, int(UnitTrait.Object)))                   # 0xd


def units_with_traits(source: TargetsSelector, traits) -> TargetsSelector:
    """`IdunBattleLogic.Entities.DSLSelectors$$UnitsWithTraits(entities, traits, selectionType)` --
    MIRROR de la FACTORY, qui n'alloue AUCUN selecteur dedie et FOLDE la collection de traits :

        left = entities
        foreach t in traits:                                   # ordre de la `ICollection`
            right = DSLSelectors.UnitsWithTrait(entities, t, selectionType)
            left  = TargetsSelector.op_BitwiseAnd(left, right)
        return left

    -> **CONJONCTION** : une unite doit porter TOUS les traits, pas au moins un. Le `right` part a
    chaque tour de `entities` (la SOURCE), jamais du `left` accumule -- on mirror la composition
    telle quelle, l'`And` du port preservant l'ordre de son operande GAUCHE, donc l'ordre de
    `source` traverse. Liste VIDE -> `source` inchange (c'est ce que rend la boucle native).

    Consommateur porte : `...Loki.UnbreakableDutyAbility$$ExecuteBehaviour` / `$$GetAmountOfDead
    ImperialUnits` (`[0x1a = Imperial, 0x10 = Hero]` = les « Imperial Characters » de l'i2)."""
    left = source
    for t in traits:
        left = And(left, UnitsWithTrait(source, int(t)))
    return left


def non_steppable_units(source: TargetsSelector) -> TargetsSelector:
    """`IdunBattleLogic.Entities.DSLSelectors$$NonSteppableUnits(source, selectionType)` -- MIRROR de
    la FACTORY, qui n'alloue AUCUN selecteur dedie et COMPOSE textuellement :

        a = UnitsWithoutTrait(source, 0x1b, selectionType)      # 27 = UnitTrait.Steppable
        return TargetsSelector.op_BitwiseAnd(source, a)

    ⚠ **CE N'EST PAS `NonSteppableOrObjectUnits`** (juste au-dessus), qui ajoute un second
    `UnitsWithoutTrait(0xd = Object)`. Les deux factories existent et le natif les distingue :
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.Drachnyen_ExtraAttackAbility$$CreateTrigger`
    et `$$CreateBehaviour` appellent celle-ci (SANS le volet Object), la fiche
    `docs/rl/case-bl-1029-1020.md` Sec.5.1 ayant note l'autre. Un `Object` adjacent est donc une
    cible VALIDE de l'extra attack.

    Consommateurs natifs lus : `Drachnyen_ExtraAttackAbility$$CreateTrigger` / `$$CreateBehaviour` /
    `$$ValidTargets`."""
    return And(source, UnitsWithoutTrait(source, int(UnitTrait.Steppable)))       # 0x1b


class NormalUnits(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$NormalUnits(entities, selectionType)` -- MIRROR du
    decompile (build `rnca9r7q6c`), qui COMPOSE trois noeuds deja portes :

        u = Units(entities, unique: true, selectionType)          # UnitsOnTilesSelector
        t = DSLTriggers.IsNormalUnit(It@0x68)                     # IsNormalUnitTrigger
        return FromTrigger(u, t, requireContinuous: false)        # == `Filter`

    Le predicat est `IdunBattle.Entities.Triggers.IsNormalUnitTrigger$$ShouldTrigger` :

        e = <resolution du selecteur sur l'item courant>
        if (e == null)                 return false;
        if (!EntityExtensions.IsUnit(e)) return false;
        return UnitExtensions.IsNormalUnit(e);

    et `IdunBattle.Entities.UnitExtensions$$IsNormalUnit` :

        if (GetBaseUnitComponent(u) != null && BaseUnitComponent.HasTrait(u, 0xd))  return false;
        if (GetBaseUnitComponent(u) != null)  return !BaseUnitComponent.HasTrait(u, 0x1b);
        return true;

    soit `!HasTrait(Object) && !HasTrait(Steppable)` -- MEME predicat que
    `non_steppable_or_object_units` ci-dessus, mais PAS le meme noeud natif (celui-la compose deux
    `UnitsWithoutTrait`/`op_BitwiseAnd`, celui-ci un `FromTrigger`). On garde les deux distincts :
    le site qui cite `NormalUnits` doit pouvoir se re-grepper contre son symbole.

    Le `IsUnit` de la tete du trigger est SATISFAIT par construction : `Units(...)` ne rend que des
    occupants d'unite. La branche « composant de base absent -> true » l'est aussi (`ctx.has_trait`
    absent -> `False` sur les deux traits -> unite gardee), meme substrat que `UnitsWithoutTrait`.

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.OverwhelmingWrathAbility$$ExecuteBehaviour`
    (`NormalUnits(AdjacentEnemies(Owner@0x30, unique: 1, selectionType: 3), selectionType: 3)` = les
    ennemis adjacents TAUNTES -- un decoy `Steppable` ou un `Object` de plateau n'est pas taunte)."""
    def __init__(self, entities: TargetsSelector):
        self.entities = entities

    def select(self, ctx):
        ht = ctx.has_trait or (lambda u, t: False)
        return [u for u in Units(self.entities).evaluate(ctx)
                if not ht(u, int(UnitTrait.Object))          # 0xd
                and not ht(u, int(UnitTrait.Steppable))]     # 0x1b


def hero_units(source: TargetsSelector) -> TargetsSelector:
    """`IdunBattleLogic.Entities.DSLFactory$$HeroUnits(source, mask)` — MIRROR du decompile : la factory
    native N'ALLOUE PAS de selecteur dedie, elle DELEGUE textuellement a
    `IdunBattleLogic.Entities.DSLFactory$$UnitsWithTrait(source, 0x10, mask)`. On mirror donc la FACTORY
    (fonction de composition), pas une classe inventee — `0x10` = `UnitTrait.Hero` (16). Consommateur porte :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.AdaptiveStrategyAbility$$GetNonCharacterFriendsSelector`
    (`Friends(...) op_Subtraction HeroUnits(...)` = les amis NON-Character)."""
    return UnitsWithTrait(source, int(UnitTrait.Hero))          # 0x10


class AllDeadUnits(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$AllDeadUnits` ->
    `IdunBattle.Entities.Selectors.AllDefeatedUnitsSelector$$Select` : les unites DEFAITES du state.

    Primitif DISTINCT d'`AllDeadOrResurrectedUnits` (deux factories natives, deux classes de selecteur) :
    celui-ci N'AJOUTE PAS les ressuscites (le flag `0xe`). L'ecart est observable des qu'une unite a ete
    ressuscitee dans la bataille -- elle est VIVANTE, donc absente d'ici, mais presente la-bas.

    Cote port, la lecture est directe : le state runner GARDE les cadavres (`alive=False`), et la
    `Scene` de decision expose les memes dicts (`decisionView.units` conserve les morts, cf.
    [[project_decisionview_keeps_dead]]). Consommateurs portes :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$GetPossibleResurrectTargets`
    et `$$GetMaxSummonsFormula` (les deux passent par `Friends(AllDeadUnits, caster@0x48)`)."""
    def select(self, ctx):
        return [u for u in ctx.units if not _is_alive(u)]


class DeadUnits(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$DeadUnits(entities)` -- le FILTRE, a ne pas confondre
    avec `AllDeadUnits` ci-dessus (qui, lui, part du POOL de la bataille et n'a pas de source).
    Le corps natif alloue son selecteur avec `(state, entities, 0)` : une SOURCE, pas un pool.

    Garde les elements MORTS de `source`. `_units_of` normalise (dict seul -> `[dict]`).

    ⚠ CE NOEUD N'A DE SENS QUE DERRIERE UN `Cache` -- et c'est LE couple que son unique porteur ecrit.
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ItItchesAbility$$ExecuteBehaviour` construit
    `Cache(Enemies(...))` UNE fois, POUSSE les unites (le displace TUE les steppables :
    `IdunBattle.Operations.DisplaceUnitOperation$$Execute` tete de fonction -- `if (IsSteppable(target))
    { Kill(caster, target, ForSteppable()); return; }`), PUIS lit `DeadUnits(<le meme Cache>)`. Sans la
    memoisation, la source serait re-evaluee POST-displace et les morts en seraient deja exclus (le
    `Units`/`AllAliveUnits` amont ne rend que des vivants) -> `DeadUnits` VIDE, `Kill` no-op, cadavres
    laisses sur les tuiles, et le `CanAddUnit` aval ne trouverait aucune tuile libre. Mode de panne
    SANS erreur."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        return [u for u in _units_of(self.source, ctx) if isinstance(u, dict) and not _is_alive(u)]


class MechanicalUnits(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$MechanicalUnits(source, selectionType)` ->
    `IdunBattle.Entities.Selectors.MechanicalUnitsSelector$$Select` — MIRROR du decompile : garde les
    unites de `source` pour lesquelles `IdunBattle.Entities.UnitExtensions$$IsMechanical` rend vrai.

    `IsMechanical` (decompile relu sur `rnca9r7q6c`) = `HasTrait(5 = Mechanical) || HasTrait(0x3e8 =
    1000 LivingMetal) || HasTrait(0x405 = 1029 Vehicle)` -- TROIS traits, pas un seul : un Necron
    `LivingMetal` est mecanique SANS porter le trait `Mechanical`. Le port delegue au helper PARTAGE
    `runner.abilities.behaviours.stats.is_mechanical`, deja confronte LIVE (case-220).

    ⚠ NOMS D'ENUM QUALIFIES : 5 / 1000 / 1029 sont des **UnitTrait**, jamais des EffectType.
    Ordre de `source` preserve (le natif accumule dans une `List` en iterant la source)."""
    def __init__(self, source: TargetsSelector, selection_type: int = 0):
        self.source, self.selection_type = source, int(selection_type)

    def select(self, ctx):
        from ...runner.abilities.behaviours.stats import is_mechanical   # lazy : evite le cycle
        ht = ctx.has_trait
        if ht is None:
            return []                       # `ctx.has_trait` absent -> trait absent (cf. UnitsWithTrait)
        return [u for u in _units_of(self.source, ctx) if is_mechanical(ht, u)]


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
        out = list(AllDeadUnits().select(ctx))       # slot 0x8a du decompile == AllDeadUnitsSelector
        seen = {u.get("id") for u in out}
        hf = ctx.has_unit_flag
        if hf is None:
            return out
        for u in ctx.units:
            if u.get("id") in seen:
                continue
            if hf(u, int(UnitFlag.Resurrected)):                   # UnitFlag 0xe = ressuscite
                out.append(u)
                seen.add(u.get("id"))
        return out


class UnitsDamagedThisPhase(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$UnitsDamagedThisPhase(attacker)` ->
    `IdunBattle.Entities.Formulas.UnitsDamagedThisPhaseSelector$$Select` — MIRROR du decompile :

        result = OrderedSet<IEntity>()
        foreach att in attackerSelector.Select(entities):        # champ +0x18 = le selecteur `attacker`
            stats = att.GetComponent<ActorStatisticsComponent>() # meme paire de statics que
                                                                 # `ApplyDamageOperation$$RecordHitStatistics`
            foreach id in stats.<champ 0x48>:                    # List<BEntityId> « endommagees cette phase »
                e = state.GetEntity(id)
                if (e != null && EntityExtensions.IsUnit(e)) result.Add(e)
        return result

    Le champ 0x48 est un `List<BEntityId>` alloue par `ActorStatisticsComponent$$.ctor` et **vide par
    `IdunBattle.Operations.EndPhaseOperation$$ResetEntityPhase`** — la MEME boucle qui appelle
    `TriggeredAbilityComponent$$ResetPhase`, d'ou le mapping de phase du port (`State.reset_trigger_phases`,
    appelee en tete de `Runner.apply`).

    Port : `ctx.units_damaged_this_phase(att)` (fourni par `entities_from_state`, lit
    `UnitComponent.damaged_units_this_phase`). L'accesseur absent -> [] (degradation fidele). `attacker`
    normalise par `_units_of` (un noeud-role `Caster()` rend un dict -> `[dict]`). Dedup par id (l'`OrderedSet`
    natif), ordre = ordre d'insertion (premiere frappe).

    Consommateur porte : le volet OVERKILL de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomSirenAbility$$ExecuteBehaviour`."""
    def __init__(self, attacker: TargetsSelector):
        self.attacker = attacker

    def select(self, ctx):
        fn = ctx.units_damaged_this_phase
        if fn is None:
            return []
        out, seen = [], set()
        for att in _units_of(self.attacker, ctx):
            for u in (fn(att) or []):
                uid = u.get("id") if isinstance(u, dict) else None
                if uid is not None and uid not in seen:
                    seen.add(uid)
                    out.append(u)
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
    return And(And(source, UnitsWithoutTrait(source, int(UnitTrait.Steppable))),
               UnitsWithoutTrait(source, int(UnitTrait.Object)))


class AdjacentFriends(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$AdjacentFriends(X)` = symétrique d'`AdjacentEnemies` (finit par
    `Friends`) : alliés à dist <= radius du centre, self exclu.

    ⚠ La REFERENCE d'équipe est le 2e argument de `Friends`, PAS le caster. La surcharge 4-args LUE au
    décompilé est `AdjacentFriends(factory, X, p3, p4)` =
    `Friends(reference = X, Units(AdjacentTiles(X), p3, p4) - X, p4)` : la référence EST le centre.
    Tant que le centre est le caster (tous les call-sites portés jusqu'ici), `team == ctx.caster.team`
    est exact — d'où le collapse historique, conservé en défaut (`reference=None`).
    `reference` EXPLICITE = la forme générale, requise dès que le centre n'est pas le caster :
    `AdjacentFriends(Target@0x178, 1, 3)` de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateBehaviour`
    = les alliés DE LA CIBLE, c'est-à-dire les ENNEMIS du caster quand les deux camps s'opposent — le
    collapse caster y rendrait exactement le camp INVERSE. (Même paramètre, même rôle et même défaut que
    `SurroundingEnemies.reference`.)"""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector | None = None,
                 reference: TargetsSelector | None = None):
        self.center, self.radius = center, radius or Const(1)
        self.reference = reference

    def select(self, ctx):
        # ordre = `AdjacentTiles` (liste d'adjacence STOCKEE, `boardGraph.neighbours` brut) -- R28-1
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx),
                       board=getattr(ctx, "board", None), order="adjacent")
        ref = resolve_unit(self.reference, ctx) if self.reference is not None else ctx.caster
        ct = (ref or {}).get("team")
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
        # ordre = `SurroundingTiles` (triple boucle CUBE d'`IterateSurroundingTiles`) -- R28-1
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx),
                       board=getattr(ctx, "board", None), order="surrounding")
        ref = resolve_unit(self.reference, ctx) if self.reference is not None else ctx.caster
        ct = (ref or {}).get("team")
        return [u for u in ring if u.get("team") != ct]


class SurroundingFriends(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$SurroundingFriends(center, radius)` = `Friends(SurroundingUnits(center,
    radius))` : alliés (team == caster) à dist <= radius du centre, centre exclu."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector):
        self.center, self.radius = center, radius

    def select(self, ctx):
        # ordre = `SurroundingTiles` (triple boucle CUBE d'`IterateSurroundingTiles`) -- R28-1
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx),
                       board=getattr(ctx, "board", None), order="surrounding")
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


class ValidNormalAttackTargets(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$ValidNormalAttackTargets(unit, unitTile, range,
    ignoreRule, additionalRule)` -> `IdunBattle.Entities.Selectors.
    ValidNormalAttackTargetsSelector$$Select` : les cibles que le `unit` pourrait attaquer A
    L'ATTAQUE NORMALE depuis `unitTile`. MIRROR du decompile :

        u     = SelectSingle(unit@+0x18)            # null -> liste VIDE
        tiles = Select(unitTile@+0x20)              # null -> liste VIDE
        opts  = battleQuery.<slot 0x3e>(GetNormalAttackType(u))
        [overrides range / ignoreRule / additionalRule]
        return targetingQuery.<slot 2>(u, tiles, opts, false).Targets

    Les TROIS overrides sont a `null` / `Nullable` VIDE aux deux call-sites lus
    (`IdunBattleLogic.Entities.Abilities.Active.Loki.SorcerousFacadeAbility$$GetTarget` et son
    `$$ExecuteBehaviour`, `IdunBattle.Entities.Effects.Loki.FearedInterrogator_TargetEffect$$
    CreateTargetSelector`) -> ce noeud ne les modelise pas (les ajouter sans call-site serait
    speculatif ; le jour ou un call-site les pose, ils entrent ICI, pas dans un fork). Verifie une
    troisieme fois sur `...Loki.UnbreakableDutyAbility$$ExecuteBehaviour` (#572) : `range = 0`,
    `ignoreRule`/`additionalRule` = deux `Nullable` ZEROEES sur la pile.

    ⚠ **`unit` peut etre un selecteur de TUILE, et le natif le resout en son OCCUPANT.** Les trois
    call-sites LUS ne s'accordent PAS sur le domaine : `SorcerousFacadeAbility$$GetTarget` passe
    `(Caster@DSLSelectors+0x48, CasterTile@+0x50)`, `FinalJusticeAbility$$GetTarget` passe
    `(Owner@+0x30, Tiles(Owner))`, et `UnbreakableDutyAbility$$ExecuteBehaviour` passe **`CasterTile`
    DANS LES DEUX SLOTS** -- lu aux octets du call-site (`mov r8,[r10+0x50]` puis `mov rdx,r8` : un
    seul chargement, deux registres). Ce n'est pas une divergence de comportement : le slot `unit`
    est consomme par `SelectSingle` -> `IdunBattle.DSL.TargetsSelector$$SelectUnit`, dont la tete est
    `if (IsUnitFoot(e) || IsTile(e)) e = UnitExtensions.GetUnit(e, state);` -- une tuile resout en son
    occupant. Le port fait donc la MEME resolution, par le foyer partage `_occupants_by_tile`
    (`dsl/base.py`), plutot que de rendre `[]` sur un `resolve_unit` qui echoue.

    Le filtre lui-meme est `ctx.valid_normal_attack_targets` (fourni par `entities_from_state`,
    qui delegue a `runner/abilities/targeting.py` -- LE port unique de la cascade de ciblage, avec
    le masque `NORMAL_ATTACK_TARGETING_OPTIONS` relu du preset statique). Accesseur ABSENT (contexte
    hors runner : prediction, tests de noeud) -> **[]**, et c'est une DEGRADATION nommee, pas un
    mirror : sans `State` la cascade native n'est pas evaluable.

    `unit_tile` est accepte pour le MIRROR STRUCTUREL de la signature native ; le port mesure la
    portee depuis la position REELLE de `unit` (cf. `valid_normal_attack_targets`), ce qui est exact
    au seul call-site COMBAT porte -- le cast part de la tuile courante du caster."""
    def __init__(self, unit: TargetsSelector, unit_tile: TargetsSelector = None):
        self.unit, self.unit_tile = unit, unit_tile

    def select(self, ctx):
        fn = getattr(ctx, "valid_normal_attack_targets", None)
        if fn is None:
            return []
        u = resolve_unit(self.unit, ctx)
        if u is None:
            # `SelectUnit` : une TUILE (ou un pied) resout en son OCCUPANT avant tout le reste.
            # Le port n'a pas d'entite-tuile -- il compare des POSITIONS -- d'ou l'index partage.
            occ = _occupants_by_tile(ctx.units)
            for p in _tile_positions(self.unit, ctx, getattr(ctx, "board", None)):
                if p in occ:
                    u = occ[p]
                    break
        if u is None:                                  # mirror `unit == null -> liste VIDE`
            return []
        return list(fn(u) or [])


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


class UnitsThatCanHaveActiveAbilityReset(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$UnitsThatCanHaveActiveAbilityReset(source, flag)` ->
    `IdunBattle.Entities.Selectors.UnitsThatCanHaveActiveAbilityResetSelector$$Select` : garde les
    unites de `source` pour lesquelles `IdunBattle.Core.Services.BattleQuery$$
    EntityCanHaveActiveAbilityReset(unit, flag)` est vrai -- c'est-a-dire celles dont une ability
    active a DEJA ete utilisee (charge consommee, ou en cooldown).

    UNIQUE consommateur lu : `IdunBattleLogic.Entities.Abilities.Active.Loki.
    InspiredToGreatnessAbility$$ExecuteBehaviour`, qui SPLITTE sa cible en
    `canReset = UnitsThatCanHaveActiveAbilityReset(target)` et `cantReset = target - canReset` pour
    router les DEUX montants de soin (var `hpToHeal` vs `hpToHeal_2`).

    Le verdict vient de `ctx.can_have_active_ability_reset` (branche `entities_from_state` ->
    `operations/ability_reset.py`). **Verdict INCONNU (None, canal `ActiveAbilitiesComponent` absent)
    -> l'unite est ECARTEE des DEUX cotes** : elle sort de `canReset` (ici) et le `Sub` la laisse dans
    `cantReset` ; c'est le comportement du natif quand aucune ability n'est resettable, mais ce n'est
    PAS un verdict -- l'ignorance est journalisee par l'ability (`unknown_reset_verdict`), jamais
    silencieuse. Accesseur absent -> meme chemin."""
    def __init__(self, source: TargetsSelector, ignore_turn_flag: bool = False):
        self.source, self.ignore_turn_flag = source, bool(ignore_turn_flag)

    def select(self, ctx):
        f = getattr(ctx, "can_have_active_ability_reset", None)
        if f is None:
            return []
        return [u for u in _units_of(self.source, ctx) if f(u) is True]


class Unobscured(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Unobscured(from, source)` -> `IdunBattle.Entities.Selectors.UnobscuredEntitiesSelector$$Select` :
    garde les unites de `source` dont la tuile n'est PAS obscurcie (terrain) depuis la tuile du referent
    `from` (`IdunBattle.Core.Services.TargetingQuery$$IsTargetUnitObscured` -> `IdunBattle.Core.Services.MovementQuery$$GetTilesObscuringTerrain`, mask 6 = elevation bit2 + murs bit4 ; TERRAIN seul, aucun blocage par unite).

    MULTI-TUILES (#433-r3-r1a) -- mirror LU de `IdunBattle.Core.Services.TargetingQuery$$IsTargetUnitObscured` :

        foreach (tile in EntityExtensions.IterateTiles(target, state))
            if (!IsTargetTileObscured(from, tile, onlyWalls)) return false;
        return true;

    ⇒ une unite est obscurcie ssi **TOUTES** ses tuiles le sont ; UNE seule tuile degagee la rend
    visible. Le port ne testait que sa main tile -- une cible 3-hex a moitie decouverte etait donc
    exclue a tort. ⚠ Le referent `from`, LUI, est bien une main tile :
    `IdunBattle.Entities.Selectors.UnobscuredEntitiesSelector$$Select` calcule
    `casterTile = EntityExtensions.GetMainTile(<casterSel>.SelectUnit(entities), state)` -- le port y
    etait deja d'accord, et l'etendre a l'empreinte serait une SECONDE erreur.

    - **dist 1 : jamais obscurcie** (la ligne n'a aucune tuile intermediaire testable, cf. case-49x §3) -> gardee.
    - **dist 2 : `bq.is_target_tile_obscured(from, unit, elev)`** (elevation, cube-line ±eps) -- geometrie
      DEJA validee live cote PREDICTION (`bq.surrounding_enemies`, craft-O/O2 probe_49x : crete elev 4 ->
      ennemi dist-2 EXCLU / deplace visible -> compte).

    `elev` vient du FOYER `entities/pathfinding/board.elevations_by_pos` (#433-r4-r1-r4-r1). Il
    lisait auparavant `ctx.board.by_coord` a la main avec `t.get("elevation", 0)` : ce defaut
    FABRIQUAIT une elevation `0` pour toute tuile dont le canal ne porte pas la donnee, alors que le
    foyer OMET l'inconnu (tri-etat : `None` = pas de canal, une carte = les tuiles CAPTEES). Le `0`
    invente n'etait pas neutre, et il deviait dans les DEUX sens selon la position de la tuile
    inconnue sur la ligne, contre le contrat que `battle_query.is_target_tile_obscured` tient deja :
      * inconnue en `from`/`to` -- le contrat rend `False` (jamais obscurci) ; le `0` invente faisait
        au contraire passer le seuil des qu'un mid valait `>= 2` (obscurcissement FABRIQUE) ;
      * inconnue en MID -- le contrat la RETIRE (`GetTileAt null -> pas bloquant`), ce qui bascule le
        cas diagonal sur la branche `len(mids) == 1` (plus bloquante) ; le `0` invente la gardait
        dans le `all(...)` de la fat-line et ETEIGNAIT le blocage.
    Passer par le foyer aligne aussi le CANAL : `elevations_by_pos` accepte un `Board` (cache
    `elev_by_pos()`) et un board duck-type `by_id`, la ou `by_coord` seul rendait `None`
    (passe-tout) sur ces deux formes.

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
        frm = (_pos(resolve_unit(self.from_ref, ctx)) if self.from_ref is not None
               else (ctx.caster_pos or _pos(ctx.caster)))
        units = _units_of(self.source, ctx)
        if frm is None:
            return list(units)
        # FOYER unique du canal d'elevation (#433-r4-r1-r4-r1) : tri-etat `None` = pas de canal,
        # et l'inconnu est OMIS -- jamais rabattu sur `0`. Cf. la docstring ci-dessus.
        elev = elevations_by_pos(getattr(ctx, "board", None))
        out = []
        for u in units:
            feet = _feet(u)
            if not feet:
                continue
            # `IsTargetUnitObscured` = ET sur TOUTES les tuiles -> l'unite est GARDEE des qu'UNE tuile
            # n'est pas obscurcie (`return false` au premier degagement).
            if all(hexgeo.distance(frm, p) == 2 and elev is not None
                   and is_target_tile_obscured(frm, p, elev) for p in feet):
                continue                                    # terrain obscurcit TOUTES les tuiles -> exclue
            out.append(u)
        return out


# --- Filtres d'ELIGIBILITE SOIN/REPARATION (les deux slots `IAttackQuery` du DSL, #303) -----------
# Ces DEUX selecteurs partagent la MEME forme native (`Select(entities)` : ils iterent le selecteur
# source et gardent l'entite si un slot du service `IAttackQuery` rend vrai) et le meme
# service -- seul le slot differe : 0x13 = `EntityCanBeRepaired(entity, scope, removeEffects)`,
# 0x14 = `EntityIsAffectedByHealType(entity, healType)`. Cf.
# `IdunBattleLogic.Core.Services.Caches.CachedAttackQuery$$EntityCanBeRepaired` /
# `$$EntityIsAffectedByHealType`, les deux thunks nommes qui donnent l'ordre des slots.

class UnitsAffectedByHealType(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$UnitsAffectedByHealType(units, healType)` ->
    `IdunBattle.Entities.Selectors.UnitsAffectedByHealTypeSelector$$Select` -- MIRROR du decompile :

        foreach entity in source.Select(entities):
            if (query.<slot 0x14>(entity, this.healType@+0x20)) result.Add(entity)

    Le slot 0x14 est `IdunBattle.Core.Services.AttackQuery$$EntityIsAffectedByHealType`, qui delegue
    a `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType(entity, healType)` :
      * `healType = 0` (NonMechanical) : `HasTrait(0x421 AffectedByHealAndRepair)` OU **NON**-IsMechanical ;
      * `healType = 1` (Mechanical)    : `HasTrait(0x421)` OU IsMechanical
        (`Mechanical 5 | LivingMetal 1000 | Vehicle 1029`).
    Le port DELEGUE au mirror UNIQUE de ce predicat (`operations/triggers/revive_effect.py`), le meme
    que consomment `abilities/attack_query.is_affected_by_heal_type` et le trigger `IsRepairable` --
    surtout pas une 3e ecriture de la meme regle.

    Ordre de `source` PRESERVE (le natif accumule dans une `List` en iterant la source).
    `ctx.has_trait` absent -> [] (aucun verdict de trait n'est disponible, meme degradation que
    `UnitsWithTrait`/`MechanicalUnits`).

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.FabricatorClawArrayAbility$$GetTargetSelector`
    (`UnitsAffectedByHealType(AdjacentFriends(Owner,1,3), 1)`)."""
    def __init__(self, source: TargetsSelector, heal_type: int = 1):
        self.source, self.heal_type = source, int(heal_type)

    def select(self, ctx):
        from ...runner.operations.triggers.revive_effect import is_affected_by_heal_type
        ht = ctx.has_trait
        if ht is None:
            return []
        return [u for u in _units_of(self.source, ctx)
                if is_affected_by_heal_type(ht, u, self.heal_type)]


class Healable(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$Healable(caster, targets, scope)` ->
    `IdunBattle.Entities.Selectors.HealableUnitsSelector$$Select` -- MIRROR du decompile :

        caster = <+0x18>.SelectSingle(entities, 3)            # slot 7 = selecteur MONO du soigneur
        foreach entity in <+0x20>.Select(entities, 3) :       # slot 4 = les cibles candidates
            if (query<+0x30>.<slot 0x11>(caster, entity, this.scope@+0x28, 1))
                result.Add(entity)

    Le slot 0x11 est `IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed`, surcharge a QUATRE
    arguments (caster en tete) -- la MEME que le gate d'`IdunBattle.Operations.HealUnitOperation$$
    Execute`. Le dernier argument (`removeEffects`) est le LITTERAL `1` du selecteur, pas un champ :
    le selecteur ne porte que `scope` (`+0x28`).

    ⚠ ASYMETRIE LUE, pas deduite : le jumeau `Repairable` juste en dessous appelle la surcharge a
    TROIS arguments (SANS caster). Recopier son patron ici ferait tomber le disjunct
    `caster != null && HasFlag(caster, 0x17 CanHealFullHealthUnits)`, qui est precisement ce qui rend
    une cible a PLEINS PV soignable. D'ou un accesseur DISTINCT (`ctx.entity_can_be_healed`, 4 args).

    Le port DELEGUE a l'unique mirror deja en place (`abilities/attack_query.entity_can_be_healed`).
    Accesseur absent -> [] (aucun verdict d'eligibilite : degradation fidele, jamais un
    « tout passe »).

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$
    GetHealTargets` (`Healable(Caster, Caster + AdjacentFriends(Caster, CasterTile, unique), 0)`).

    ⚠ CE NOEUD N'EST PAS L'ALTERNATIVE DE `Heal(guard=healable_heal_type_0)` : les deux mirrorent
    des etages NATIFS differents. Le `guard` de la feuille porte le pre-filtre `HealableUnitsSelector`
    d'un call-site qui n'a PAS de noeud `Healable` dans son arbre (1002/1037, ou le natif applique le
    wrapper AVANT le split de trait) ; ce selecteur-ci porte le noeud quand il EST dans l'arbre. Un
    call-site qui a les deux les ecrit tous les deux -- ils sont idempotents l'un sur l'autre."""
    def __init__(self, source: TargetsSelector, caster: TargetsSelector | None = None,
                 scope: int = 0, unit_selection_type: int = 3):
        self.source, self.caster = source, caster
        self.scope = int(scope)
        self.unit_selection_type = int(unit_selection_type)

    def select(self, ctx):
        f = getattr(ctx, "entity_can_be_healed", None)
        if f is None:
            return []
        # `<+0x18>.SelectSingle` : le SOIGNEUR. `None` (defaut) = `Caster`, ce que passe le seul
        # call-site lu -- resolu comme partout ailleurs (`Friends.reference`, `AdjacentFriends`).
        healer = resolve_unit(self.caster, ctx) if self.caster is not None else ctx.caster
        return [u for u in _units_of(self.source, ctx)
                if f(healer, u, self.scope, True)]           # `removeEffects` = litteral 1 du selecteur


class Repairable(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$Repairable(entities, scope, removeEffects, unitsToTarget)`
    -> `IdunBattle.Entities.Selectors.RepairableUnitsSelector$$Select` -- MIRROR du decompile :

        foreach entity in source.Select(entities, this.unitSelectionType@+0x28):
            if (query.<slot 0x13>(entity, this.scope@+0x20, this.removeEffects@+0x24))
                result.Add(entity)

    Le slot 0x13 est la surcharge **A TROIS ARGUMENTS** d'`IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired`
    (celle SANS caster) ; relue verbatim, elle est la 4-args avec `caster = null` -- le seul disjunct
    qui disparait est `caster != null && HasFlag(caster, 0x18 CanRepairFullHealthUnits)`. Le port
    DELEGUE donc a l'unique mirror deja en place (`abilities/attack_query.entity_can_be_repaired`,
    appele avec `caster_id = None`), via l'accesseur de contexte `ctx.entity_can_be_repaired` --
    exactement le patron de `UnitsThatCanHaveActiveAbilityReset` (slot `IBattleQuery`).

    `unit_selection_type` = le 4e argument natif (`+0x28`), passe au `Select` de la SOURCE (mode
    d'occupation main/steppable). Le port n'a pas ce parametre cote selecteurs sources -> conserve
    pour la lisibilite du mirror, INERTE (residu deja partage par tous les call-sites d'`AdjacentFriends`).

    Accesseur absent -> [] (aucun verdict d'eligibilite : degradation fidele, jamais un « tout passe »).

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.FabricatorClawArrayAbility$$GetTargetSelector`
    (`Repairable(UnitsAffectedByHealType(...), 0, 1, 3)`)."""
    def __init__(self, source: TargetsSelector, scope: int = 0, remove_effects: bool = True,
                 unit_selection_type: int = 3):
        self.source, self.scope = source, int(scope)
        self.remove_effects = bool(remove_effects)
        self.unit_selection_type = int(unit_selection_type)

    def select(self, ctx):
        f = getattr(ctx, "entity_can_be_repaired", None)
        if f is None:
            return []
        return [u for u in _units_of(self.source, ctx)
                if f(u, self.scope, self.remove_effects)]


class UnitsWithEffectsOfType(TargetsSelector):
    """`IdunBattle.Entities.Selectors.UnitsWithEffectsOfTypeSelector$$Select` -- MIRROR du decompile :

        foreach entity in source.Select(entities, 3):
            if (EntityExtensions.HasEffectOfType(entity, state, effectsDatabase, this.<+0x28>))
                result.Add(entity)

    ⚠ `<+0x28>` n'est PAS un `EffectType` : `IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffectOfType`
    lit, pour CHAQUE effet porte, la DEFINITION de l'effet dans l'`EffectsDatabase` et en compare le
    `Nullable<int>` de CATEGORIE (`def+0x58` -> champ optionnel de la definition). C'est une CATEGORIE
    d'effet (1 = negatif), pas un id d'effet.

    **RESIDU NOMME, dimension NON PORTEE** : le canal de seed (`decisionView.units[].effects`) donne la
    LISTE des effets portes mais AUCUNE categorie, et il n'existe pas de table `EffectType -> categorie`
    cote port -- meme trou, exactement, que `attack_query.has_negative_unit_effect` (qui lit un AUTRE
    conteneur natif, `EffectsComponent+0x100`, et rend `False` pour la meme raison). L'accesseur
    `ctx.has_effect_of_type` n'est donc branche par AUCUN substrat : ce selecteur rend **[]**.
    Rendre « tout » serait pire (le fallback deviendrait universel). La consequence est bornee et
    UNILATERALE : ce selecteur n'apparait qu'en FALLBACK d'`Otherwise`, donc il ne peut que RATER une
    cible que le natif aurait prise -- jamais en prendre une de trop."""
    def __init__(self, source: TargetsSelector, effect_category: int = 1):
        self.source, self.effect_category = source, int(effect_category)

    def select(self, ctx):
        f = getattr(ctx, "has_effect_of_type", None)
        if f is None:
            return []
        return [u for u in _units_of(self.source, ctx) if f(u, self.effect_category)]


def UnitsWithNegativeEffects(source: TargetsSelector) -> UnitsWithEffectsOfType:
    """`IdunBattleLogic.Entities.DSLSelectors$$UnitsWithNegativeEffects(entities)` = la FABRIQUE qui
    construit `UnitsWithEffectsOfTypeSelector(state, effectsDatabase, entities, 1)` -- le littéral
    `1` (categorie NEGATIVE) est ecrit par la fabrique elle-meme, lu au decompile."""
    return UnitsWithEffectsOfType(source, 1)


class EntitiesFromPersistentDataList(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$GetPersistentDataListAsEntities(abilityOrEffect, unit,
    key)` -> `IdunBattle.Entities.Selectors.EntitiesFromPersistentDataListSelector$$Select` -- MIRROR
    du decompile :

        holder = <selecteur `unit` @+0x30>.<slot 8 SelectSingle>(entities, UnitSelectionType 3)
        key    = <formule `key` @+0x38>.Calculate(entities)          # !HasValue -> liste VIDE
        list   = holder.GetComponent<PersistentDataComponent>()
                       .TryGetPersistDataList<int>(GetPersistentDataId(abilityOrEffect@+0x18), key)
                 ?? new List<int>()
        foreach (id in list) {
            e = state.GetEntity(id)
            if (e != null && (!e.IsUnit() || MatchesUnitSelectionType(e, 3)))  result.Add(e)
        }
        return result

    Trois traits LUS :
      * l'ORDRE rendu est celui d'INSERTION dans la liste persistante (aucun tri intermediaire) ;
      * une entite disparue est SILENCIEUSEMENT jetee (`GetEntity` rend null) ;
      * le filtre `MatchesUnitSelectionType(3)` ne s'applique qu'aux ENTITES-UNITE (`IsUnit()`), le
        reste passe tel quel. Le litteral `3` est ecrit par le `Select` lui-meme, ce n'est pas un
        parametre de la fabrique.

    Ce selecteur etait le RESIDU NOMME de #354 (« le jour ou un consommateur a besoin des ENTITES,
    le selecteur entre ici », `runner/abilities/behaviours/persistent_data.py`). Son consommateur
    est la formule de tri de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PrimarchOfTheFirstLegionAbility$$CreateBehaviour`.

    Le port range la liste sous la MEME cle composite `(abilityOrEffect, dataKey)` que le scalaire
    (`PersistentDataComponent`) et lit par l'accesseur `ctx.persistent_data_list` -- absent (contexte
    hors runner) -> liste VIDE, ce qui est la reponse du natif quand la cle n'existe pas.
    `ctx.entity_by_id` absent -> les ids ne sont pas resolvables -> liste VIDE (meme polarite)."""
    def __init__(self, ability_or_effect: int, unit_sel: TargetsSelector, data_key):
        self.ability_or_effect = int(ability_or_effect)
        self.unit_sel, self.data_key = unit_sel, data_key

    def select(self, ctx):
        fn = getattr(ctx, "persistent_data_list", None)
        by_id = getattr(ctx, "entity_by_id", None)
        if fn is None or by_id is None:
            return []
        holders = _units_of(self.unit_sel, ctx)
        if len(holders) != 1:                       # `SelectSingle` : 0 ou plusieurs -> pas de sac
            return []
        key = self.data_key.evaluate(ctx) if hasattr(self.data_key, "evaluate") else self.data_key
        if key is None:                             # `!HasValue` -> liste vide
            return []
        out = []
        for eid in (fn(holders[0], (self.ability_or_effect, key)) or ()):
            e = by_id(eid)
            if e is not None:
                out.append(e)
        return out
