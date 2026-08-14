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
# `AllAliveUnits` = le champ PARTAGE `<DSLSelectors>+0x20`, source LUE de `TilesWithEnemies` (et de
# tous les `Enemies`/`Friends` natifs). Import EN TETE, forme B interdite ici (c'est une CLASSE de
# noeud, pas une fonction patchable) : l'arete `units -> tiles` est NEUVE et ACYCLIQUE -- `tiles.py`
# n'importe pas `units.py` (verifie), et les deux modules restent importables SEULS en process frais.
from .tiles import AllAliveUnits
# #270-r4 : les deux litteraux de ce module DESIGNENT, et leur enum est LU au decompile --
# `UnitsWithTrait(source, 0x10)` (le parametre `trait` de `DSLFactory$$UnitsWithTrait`) et
# `has_unit_flag(u, 0xe)` (le parametre `flag` d'`UnitExtensions$$HasFlag`).
from ..traits.unit_trait import UnitTrait
from ..unit_flag import UnitFlag
# #585 : le 3e/4e argument `selectionType` des factories `DSLSelectors`, LU par
# `IdunBattle.DSL.TargetsSelector$$SelectUnit` -> `UnitExtensions$$MatchesUnitSelectionType`.
# Le FOYER du predicat existe depuis #524 (face DECISION, `playbook/adjacency.py`) : on l'appelle,
# on n'en ecrit pas un second. `selection_ok_from_ctx` est le DERIVATEUR runner, hisse la par
# #433-r3-r2 pour que `entities/triggers.py` puisse le partager sans arete (cf. `_selection_ok`).
from ..unit_selection_type import (UnitSelectionType, matches_unit_selection_type,   # noqa: F401
                                   selection_ok_from_ctx)
from ...battle_query import is_target_tile_obscured


def _selection_ok(u, selection_type, ctx) -> bool:
    """`IdunBattle.DSL.TargetsSelector$$SelectUnit(entity, selectionType)` cote RUNNER : derive les
    deux predicats que le foyer `matches_unit_selection_type` (#524) attend, puis DELEGUE.

    Le foyer vit dans `engine/entities/unit_selection_type.py` et sert deja la face DECISION
    (`playbook/adjacency.unit_matches`, qui derive `targetable` de `UNTARGETABLE_EFFECT_TYPES`).
    Ici le substrat est l'ECS : `alive`/`hp` du dict d'unite, et `ctx.has_unit_flag` pour le flag
    `0x11`. Un SECOND port du predicat aurait ete un fork.

    TRI-ETAT preserve : `ctx.has_unit_flag` absent -> `targetable = None` = **PAS MESURE**, et le
    foyer degrade alors la clause en VRAI. Un `False` invente ecarterait une unite que le natif
    compte.

    ⚠ LE CORPS A ETE HISSE (#433-r3-r2) dans `entities/unit_selection_type.py::selection_ok_from_ctx`
    -- feuille pure, donc importable des DEUX cotes sans arete. Ce n'etait pas de la cosmetique :
    `entities/triggers.py::IsAdjacent` avait ecrit un TROISIEME port du predicat, a la main et
    aveugle au volet `Untargetable`, exactement le fork que la phrase ci-dessus disait vouloir
    eviter. Cet alias reste pour ses lecteurs."""
    return selection_ok_from_ctx(u, selection_type, ctx)


class SurroundingUnits(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$SurroundingUnits(center, radius, ..., includeCenter, ...)` =
    `Units(SurroundingTiles(center, includeCenter, radius))` = unités à distance hex <= radius du centre.

    `include_center` = MIRROR de l'argument natif `param_3` de `IdunBattleLogic.Entities.DSLFactory$$SurroundingTiles`
    (lu au décompilé) : `param_3 == 0` -> le factory construit `SurroundingTiles(includeCenter=1) op_Subtraction
    Tiles(center)` (centre EXCLU) ; `param_3 != 0` -> `SurroundingTilesSelector` DIRECT (centre **INCLUS**).
    Défaut `False` = centre exclu (tous les call-sites portés jusqu'ici). `IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets` passe `SurroundingUnits(target@0x178, range, 1, 1, 3)` -> `SurroundingTiles(..., param_5=1, ...)`
    = **centre inclus** (la cible elle-même est un des summons frappés, cf. i2 « a targeted enemy summon AND all
    other enemy summons within 2 hexes »).

    `selection_type` = le DERNIER argument NATIF (#585-r3). Les DEUX surcharges de
    `IdunBattleLogic.Entities.DSLSelectors$$SurroundingUnits` ont la MEME signature
    `(this, origin, range, unique, includeCenter, unitSelectionType)` et le PROPAGENT toutes deux a
    leur `Units` interne (`Units(this, SurroundingTiles(...), unique, unitSelectionType)`) : aucune
    n'en code un EN DUR -- contrairement a `AdjacentFriends`/`AdjacentEnemies`, ou la variante B pose
    `3` invisible. `None` (defaut) = aucun filtre = comportement HISTORIQUE."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector, include_center: bool = False,
                 selection_type=None):
        self.center, self.radius = center, radius
        self.include_center = bool(include_center)
        self.selection_type = selection_type

    def select(self, ctx):
        # ordre = `SurroundingTiles` (triple boucle CUBE d'`IterateSurroundingTiles`), cf. `_tile_enum_rank`
        out = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx),
                      include_center=self.include_center,
                      board=getattr(ctx, "board", None), order="surrounding")
        st = self.selection_type
        # le natif filtre DANS son `Units` interne : PAR ELEMENT, apres resolution de l'occupant
        return out if st is None else [u for u in out if _selection_ok(u, st, ctx)]


class AdjacentEnemies(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$AdjacentEnemies(caster)` = `Enemies(Units(AdjacentTiles(caster)) - {caster})`
    = ennemis (team != caster) à dist <= radius du caster, self exclu.

    ⚠ DEUX SURCHARGES d'ARITE 4, meme nom affiche, INDISCERNABLES dans le pseudo-C (#585-r3) --
    c'est le piege central de ce parametre :

      * variante A `IdunBattleLogic.Entities.DSLSelectors$$AdjacentEnemies(this, unit, unique,
        selectionType)` = `Enemies(unit, Units(AdjacentTiles(unit), unique, selectionType) - unit,
        selectionType)` -> PROPAGE le litteral aux DEUX etages ;
      * variante B `IdunBattleLogic.Entities.DSLSelectors$$AdjacentEnemies(this, unit, unitTile,
        unique)` = `Enemies(unit, Units(AdjacentTiles(unitTile), unique, 3) - unitTile, 3)` -> `3`
        EN DUR aux deux etages, et son 3e argument est une ENTITE (l'ancre geometrique), pas un
        booleen.

    Lire le 4e argument de la variante B comme un `selectionType` donnerait `1` = `OnlyAlive`, soit
    le filtre qui n'ecarte PAS `Untargetable` -- l'INVERSE de ce que ce parametre repare. Le
    discriminant est la cible du `call`, donc les XREFS ENTRANTES, jamais le pseudo-C seul.
    `None` (defaut) = aucun filtre = comportement HISTORIQUE."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector | None = None,
                 selection_type=None):
        self.center, self.radius = center, radius or Const(1)
        self.selection_type = selection_type

    def select(self, ctx):
        # ordre = `AdjacentTiles` (liste d'adjacence STOCKEE, `boardGraph.neighbours` brut) -- R28-1
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx),
                       board=getattr(ctx, "board", None), order="adjacent")
        ct = (ctx.caster or {}).get("team")
        st = self.selection_type
        # le natif applique le meme predicat DEUX fois (au `Units` interne puis au `Enemies`) ; il est
        # PUR en (unite, selectionType), donc idempotent -> un seul passage ici.
        return [u for u in ring if u.get("team") != ct
                and (st is None or _selection_ok(u, st, ctx))]


class AdjacentUnits(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$AdjacentUnits(target, radius, mask)` = `Units(AdjacentTiles(target)) - {target}`
    = TOUTES les unités (AUCUN filtre d'équipe) à distance hex <= radius de `target`, target exclu. ⚠ à la
    DIFFÉRENCE de `AdjacentEnemies` (filtre team != caster) et de `Enemies(...)` (wrapper `UnitsByTeamSelector`),
    ce sélecteur ne filtre PAS l'équipe → inclut les ALLIÉS du caster (et le caster) s'ils sont adjacents à la
    cible = FRIENDLY-FIRE. Le volet SPLASH de Stikkbomb (IdunBattleLogic.Entities.Abilities.Active.Loki.StikkbombAbility$$ExecuteBehaviour) passe ce sélecteur BRUT (sans wrapper
    `Enemies(...)`, contraste PlasmaGrenade/ScythingTalons) — corroboré par l'i2 (« units in hexes adjacent »
    vs « enemy units » des autres). `_within` exclut déjà le centre (target, dist 0). Mirror de `AdjacentEnemies`
    SANS le filtre team.

    `selection_type` = le 4e argument NATIF (#585-r3). `IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits`
    n'a **qu'UNE** surcharge -- `(this, origin, unique, selectionType)` =
    `op_Subtraction(Units(AdjacentTiles(origin), unique, selectionType), origin)` -- donc AUCUNE
    ambiguite de lecture ici, a la difference d'`AdjacentEnemies`/`AdjacentFriends`.

    ⚠ Et c'est le selecteur ou ce parametre PESE LE PLUS : sans wrapper `Enemies`/`Friends`, le
    `selectionType` du `Units` interne est le SEUL filtre de l'ensemble rendu. `None` (defaut) =
    aucun filtre = comportement HISTORIQUE."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector | None = None,
                 selection_type=None):
        self.center, self.radius = center, radius or Const(1)
        self.selection_type = selection_type

    def select(self, ctx):
        # ordre = `AdjacentTiles` (liste d'adjacence STOCKEE, `boardGraph.neighbours` brut) -- R28-1
        out = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx),
                      board=getattr(ctx, "board", None), order="adjacent")
        st = self.selection_type
        return out if st is None else [u for u in out if _selection_ok(u, st, ctx)]


class Enemies(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$Enemies(reference, source, mode)` -> `UnitsByTeamSelector`
    (`IdunBattle.Entities.Selectors.UnitsByTeamSelector$$Select` -> `$$CountOrAdd`, flag@+0x28 = 0) :
    filtre -> equipe != celle du referent (le CASTER a tous les call-sites portes). Symetrique exact de
    `Friends` (meme classe, flag 1).

    `_units_of` normalise l'operande (mirror du contrat natif : `source` peut etre un REF-ENTITE seul --
    `Enemies(caster, target@0x178, 3)` de `PlagueburstMortarAbility$$GetMainDamageTarget` -- ou une liste ;
    None -> vide). Sans ca, iterer un dict nu rendrait ses CLES (meme piege que `Tiles`/`Sub`).

    `selection_type` = le 4e argument NATIF (`DSLSelectors$$Enemies(this, of, entities,
    selectionType)`), que le ctor d'`UnitsFromFactionSelector` recoit et que `$$Select` transmet a
    `SelectUniqueUnits` -- donc a `MatchesUnitSelectionType` PAR ELEMENT. Symetrique exact de
    `Friends` ci-dessous. `None` (defaut) = aucun filtre = comportement HISTORIQUE (#585-r1).

    ⚠ DEUX SURCHARGES portent ce nom et cette arite, et la seconde est un SUCRE :
    `DSLSelectors$$Enemies(this, of, entities, onlyAlive)` se re-appelle avec
    `(onlyAlive & 0xff) + 2`, donc `false -> OnlyTargetable`, `true -> OnlyAliveAndTargetable`
    (cf. `entities/unit_selection_type.selection_type_from_only_alive`). Un call-site qui emprunte
    la surcharge booleenne ne vaut donc JAMAIS `Any` -- ne pas y lire << pas de filtre >>.

    `reference` = le 1er argument NATIF (`of`), STRICTEMENT le pendant de celui de `Friends`
    ci-dessous -- meme classe native, meme role, seul le flag `+0x28` differe. `None` (defaut) = le
    CASTER, comportement HISTORIQUE de tous les call-sites deja portes, qui passent bien
    `Caster@+0x48`. `IdunBattleLogic.Entities.DSLSelectors$$TilesWithEnemies` est le premier a
    passer autre chose (`Owner@+0x30`) : le referent y est ce que l'appelant lui donne, et
    l'ecraser par le caster serait faux des que les deux divergent (effet pose par un tiers,
    ability greffee).

    ⚠ **LE DOMAINE DE RETOUR EST L'ACTEUR RESOLU, JAMAIS L'ENTITE BRUTE DU SELECTEUR SOURCE, et
    c'est un ETAGE ENTIER qui manquait a la lecture (#1030-r5).** `CountOrAdd` fait bien
    `System.Collections.Generic.List<T>.Add(result, entity)` avec l'entite ITEREE -- mais ce qu'il
    itere n'est PAS `Select(entities)` : c'est le **SLOT 5 d'`ITargetsSelector`**, appele sur son
    selecteur source `<UnitsByTeamSelector+0x20>` avec le `selectionType` de `<+0x2c>`. Ce slot est
    `SelectAllActors` (grille `data/symbols/<build>/metadata/interface_slots.tsv`, entree
    VERSIONNEE ; l'arite 2 concorde, et le referent est pris au slot 8 `SelectActor`), et
    `IdunBattle.DSL.TargetsSelector$$SelectAllActors` **RESOUT chaque element** :

        raw = this.<slot 0x17 Select>(entities)
        if (this.<slot 0x21 get_ReturnsOnlyActors>) return raw;      // deja des acteurs
        foreach (entity in raw)
            u = SelectUnit(this, entity, selectionType);              // <- la RESOLUTION
            if (u != null) result.Add(u); else if (IsMachine(entity)) result.Add(entity);

    et `IdunBattle.DSL.TargetsSelector$$SelectUnit` porte le
    `if (IsUnitFoot(entity) || IsTile(entity)) entity = GetUnit(entity, state);`. L'`entity` qu'ajoute
    ensuite `CountOrAdd` est donc **l'acteur deja resolu**, et `GetUnitOrMachine` n'y est plus que
    l'identite -- ce qui explique qu'il ne serve qu'au test de camp.

    La grille de vtable est recoupee par la fonction SOEUR : `$$SelectAllUnits` teste `+0x278`
    (slot 20 `get_ReturnsOnlyUnits`) la ou `$$SelectAllActors` teste `+0x288` (slot 21
    `get_ReturnsOnlyActors`) -- meme forme, deux slots adjacents. SECONDE SOURCE INDEPENDANTE :
    `...NovaChargeAbility$$GetAdditionalMarkedTiles` enchaine
    `NormalUnits(Enemies(Owner@+0x30, <des TUILES>, 3), 3)` -- un selecteur d'UNITES consomme la
    sortie d'`Enemies`, ce qui n'aurait aucun sens sur des ids de tuile.

    ⚠ CE QUE CETTE LECTURE CORRIGE : la forme d'avant rendait l'entite SOURCE, donc des ids de
    TUILE des que la source etait tile-domain -- `1094 TheLantern` (`Enemies(Caster, <zone>, 3)`
    alimentant `AddEffect(1065 Pinned)`) posait alors `Pinned` sur PERSONNE, sans erreur. Aucun
    etage en aval ne rattrape : `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` lit ses
    cibles au **slot 0 `Select`** (entites brutes) et `IdunBattle.Operations.AddEffectOperation$$Execute`
    (lue INTEGRALEMENT) pose sur `owner` tel quel. La resolution est ICI, ou nulle part."""
    def __init__(self, inner: TargetsSelector, reference: TargetsSelector | None = None,
                 selection_type=None):
        self.inner, self.reference = inner, reference
        self.selection_type = selection_type

    def select(self, ctx):
        ref = resolve_unit(self.reference, ctx) if self.reference is not None else ctx.caster
        ct = (ref or {}).get("team")
        st = self.selection_type
        out = []
        for e in _entities_of(self.inner, ctx):
            # `SelectAllActors` : `SelectUnit(entity, selectionType)` d'abord -- la resolution
            # tuile/pied -> occupant. Sur une source DEJA unit-domain c'est l'IDENTITE (`u is e`),
            # donc les ~600 call-sites unit-domain sont inchanges.
            u = unit_or_machine(e, ctx)          # `UnitExtensions$$GetUnitOrMachine(entity, state)`
            if u is None or u.get("team") == ct:
                continue
            if st is not None and not _selection_ok(u, st, ctx):
                continue
            out.append(u)                        # `result.Add(entity)` : l'ACTEUR RESOLU (cf. supra)
        return out


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
    écartée. Utilisé par `SpiritLeech.GetHealTargets` (allies Tyranids adjacents).

    `selection_type` = le DERNIER argument NATIF (#585-r3). Les DEUX surcharges de
    `IdunBattleLogic.Entities.DSLSelectors$$UnitsFromFaction` ont la meme arite et le meme role du
    dernier argument -- elles ne different que par le TYPE du 3e (l'une recoit l'enum `UnitFaction`
    et le convertit par `System.Enum.ToString`, l'autre recoit deja le `factionId` string) -- et
    toutes deux le transmettent a `IdunBattle.Entities.Selectors.UnitsFromFactionSelector$$.ctor`
    (champ `+0x2c`), avec `shouldBelong = 1` EN DUR dans les deux cas.

    ORDRE natif lu dans `IdunBattle.Entities.Selectors.UnitsFromFactionSelector$$Select` : le
    `selectionType` est consomme D'ABORD, par le `SelectUniqueUnits` qui enumere `entities` ; le test
    `IdunBattle.Entities.UnitExtensions$$HasFaction(unit, factionId) == shouldBelong` ne vient
    QU'APRES. Les deux predicats sont independants et l'ordre de la liste est preserve -> une seule
    comprehension est fidele. `None` (defaut) = aucun filtre = comportement HISTORIQUE."""
    def __init__(self, source: TargetsSelector, faction, selection_type=None):
        self.source, self.faction = source, faction
        self.selection_type = selection_type

    def select(self, ctx):
        fo = ctx.faction_of
        if fo is None:
            return []
        st = self.selection_type
        return [u for u in self.source.evaluate(ctx)
                if (st is None or _selection_ok(u, st, ctx)) and fo(u) == self.faction]


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
        # MEME classe native, MEME corps qu'`Enemies` (`UnitsByTeamSelector$$CountOrAdd`, flag
        # `this+0x28` = 1 au lieu de 0) -> MEME forme, y compris le domaine de RETOUR (#1030-r5) :
        # ce que `CountOrAdd` itere est le **slot 5 `SelectAllActors`** de son selecteur source, qui
        # a DEJA resolu chaque entite par `IdunBattle.DSL.TargetsSelector$$SelectUnit` -- donc
        # `result.Add(entity)` reinjecte l'ACTEUR RESOLU. Demonstration complete et recoupements :
        # docstring d'`Enemies` ci-dessus. `Friends` portait le meme trou (une source en domaine
        # TUILE rendait `[]`), et il se repare du meme geste : la classe native est UNE.
        out = []
        for e in _entities_of(self.inner, ctx):
            u = unit_or_machine(e, ctx)          # `UnitExtensions$$GetUnitOrMachine(entity, state)`
            if u is None or u.get("team") != rt:
                continue
            if st is not None and not _selection_ok(u, st, ctx):
                continue
            out.append(u)                        # `result.Add(entity)` : l'ACTEUR RESOLU (cf. supra)
        return out


def _est_entite_tuile(d: dict, board) -> bool:
    """`IdunBattle.Entities.EntityExtensions$$IsTile(entity)` -- le conjoint du `IsUnitFoot ||
    IsTile` qui GARDE la re-resolution `GetUnit` de
    `IdunBattle.DSL.TargetsSelector$$SelectUnit`. Le port n'a pas de composant de tuile : sa SEULE
    fabrique d'entite-tuile est `runner.abilities.behaviours.context._tile_entity`, dont la forme
    est figee par `test_287r12_role_target_tuile_offline` -- `visualId` NUL et un `id` du
    `boardGraph`. Les deux conditions ensemble, jamais l'une seule : `visualId` nul designe aussi
    le caster MINIMAL non-tuile (qui n'a pas de `pos` et que la branche de re-resolution jette,
    comme le natif), et un id de tuile ne peut pas etre confondu avec une unite qui, elle, porte
    toujours son `visualId`.

    ⚠ POURQUOI CE PREDICAT EXISTE (#962). Le court-circuit << ENTITE-UNITE en entree >> de
    `Units.select` (#951) testait la seule presence de la CLE `visualId`. Or l'entite-tuile PORTE
    cette cle, a `None` : elle passait donc pour une unite et se rendait ELLE-MEME au lieu de son
    occupant. Effet MESURE sur `1017 FragBomb` (tile-target) : `Units(Target@0x178, 1, 1)` rendait
    l'id de la TUILE, donc `main_attack: None` et la cible principale rangee dans `splash` -- le
    defaut exact que #287-r12 avait ferme, rouvert par la bande.
    """
    return (d.get("visualId") is None
            and board is not None
            and d.get("id") in getattr(board, "by_id", {}))


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
    ce commit (l'index par main tile rendait au plus une tuile par unite).

    `selection_type` = le 4e argument NATIF, que `UnitsOnTilesSelector$$.ctor` recoit a cote d'`unique`
    et que `$$Select` transmet a `SelectUniqueUnits`/`SelectAllUnits` -- donc a
    `MatchesUnitSelectionType` PAR ELEMENT. `None` (defaut) = aucun filtre = comportement HISTORIQUE
    (#585-r1). ⚠ Meme piege de SURCHARGE que `Enemies` : `DSLSelectors$$Units(this, entities, unique,
    onlyAlive)` alloue le meme selecteur avec `(onlyAlive & 0xff) + 2` -- `false -> OnlyTargetable`,
    `true -> OnlyAliveAndTargetable`, JAMAIS `Any`."""
    def __init__(self, tiles: TargetsSelector, selection_type=None):
        self.tiles = tiles
        self.selection_type = selection_type

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
            if (isinstance(it, dict) and it.get("id") is not None and "visualId" in it
                    and not _est_entite_tuile(it, board)):
                # ENTITE-UNITE en entree -> COURT-CIRCUIT, mirror LU de
                # `IdunBattle.DSL.TargetsSelector$$SelectUnit(entity, selectionType)` :
                #
                #     if (IsUnitFoot(entity) || IsTile(entity)) entity = GetUnit(entity, state);
                #     if (entity != null && IsUnit(entity) && MatchesUnitSelectionType(...))
                #         return entity;
                #
                # La re-resolution par la tuile est SOUS un `IsUnitFoot || IsTile` : une entree qui
                # est DEJA une unite ne la traverse PAS. Le port, lui, repassait par `_pos` +
                # `_occupants_by_tile` -- lequel ne garde que les VIVANTS (#57m). L'ecart etait
                # ecrit dans cette meme docstring (« le filtre VIVANT y reste applique ») et
                # personne ne l'avait rencontre : il faut une source qui rende des unites MORTES.
                #
                # MESURE #951 : `Count(NormalUnits(UnitsDefeatedBy(Owner), Any))` -- le
                # multiplicateur de `TrophyTakerAbility$$GetCritChanceMultiplier` -- rendait **0**
                # la ou le natif rend **1** (stat-mod 1288 = 16 mesure live, port = rien). Les
                # unites vaincues sont MORTES par construction : aucun autre regime ne pouvait
                # montrer ce trou.
                #
                # RAYON DE SOUFFLE, borne par le `selection_type` : les call-sites qui passent
                # `OnlyAlive` (1) ou `OnlyAliveAndTargetable` (3) -- l'ecrasante majorite --
                # re-excluent le mort par `_selection_ok` deux lignes plus bas, donc RIEN ne change
                # pour eux. Seuls `Any` (0) et `OnlyTargetable` (2) voient la difference, et c'est
                # exactement ce que le natif fait.
                u = it
                if u.get("id") in seen:
                    continue
                if self.selection_type is not None and not _selection_ok(u, self.selection_type, ctx):
                    continue
                seen.add(u.get("id"))
                out.append(u)
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
            # `SelectUniqueUnits(source, entities, selectionType)` : le filtre est PAR ELEMENT, et il
            # tombe APRES la resolution de l'occupant (`SelectUnit` -> `MatchesUnitSelectionType`).
            if self.selection_type is not None and not _selection_ok(u, self.selection_type, ctx):
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
        # `GetMainTile(entity)` est DOMAINE MIXTE : il rend la tuile d'une UNITE **comme d'une
        # TUILE** (`_entity_pos`, dont c'est la docstring). Le port lisait `_pos`, qui ne resout
        # qu'un dict -> `Tiles(<des ids de tuile>)` rendait VIDE, alors que le natif est l'IDENTITE
        # sur ce domaine. Le call-site qui l'exige est `Tiles(Enemies(Owner, <TUILES>, 3))` de
        # `...NovaChargeAbility$$GetAdditionalMarkedTiles`. Inchange pour un dict (`_entity_pos`
        # y delegue a `_pos`).
        board = getattr(ctx, "board", None)
        pos = [p for p in (_entity_pos(u, board) for u in _entities_of(self.units, ctx))
               if p is not None]
        if not self.as_ids:
            return pos
        board = getattr(ctx, "board", None)
        if board is None:
            return []
        return [t for t in (board.id_at(p[0], p[1]) for p in pos) if t is not None]


def _entities_of(node, ctx) -> list:
    """Normalise un operande en liste d'ENTITES du domaine MIXTE (dict d'unite / id de tuile /
    position `(col,row)`). C'est `_units_of` PLUS la garde du tuple-position : `list((c, r))` rend
    `[c, r]`, deux entiers qui seraient relus comme deux ids de tuile. Meme garde que
    `_add_effect_targets` et `_tile_positions`, et meme motif que le « iterer un dict nu rendrait
    ses CLES » deja documente sur `Enemies`/`Tiles`."""
    v = node.evaluate(ctx)
    if v is None:
        return []
    if isinstance(v, dict):
        return [v]
    if (isinstance(v, tuple) and len(v) == 2
            and all(isinstance(x, int) and not isinstance(x, bool) for x in v)):
        return [v]
    return list(v)


def unit_or_machine(elem, ctx):
    """`IdunBattle.Entities.UnitExtensions$$GetUnitOrMachine(entity, state)` -- le pont ENTITE ->
    UNITE que `IdunBattle.Entities.Selectors.UnitsByTeamSelector$$CountOrAdd` applique a CHAQUE
    element avant de tester l'appartenance d'equipe. Une UNITE se rend elle-meme ; une TUILE rend
    son OCCUPANT (`TileContentComponent`) ; tout le reste rend `null`.

    C'est ce maillon qui rend sensee la lecture `Enemies(Owner, <des TUILES>, 3)` de
    `...NovaChargeAbility$$GetAdditionalMarkedTiles` -- sans lui, un selecteur d'equipe applique a
    un domaine TUILE rendrait vide. Le port lit l'EMPREINTE (`_feet`), pas la seule main tile :
    une unite multi-hex occupe toutes ses tuiles, exactement comme le `TileContentComponent`
    natif (meme lecture que `tiles.py::CanAddUnit`).

    ⚠ **NE PAS RELIRE `Add(result, entity)` DE `CountOrAdd` COMME << l'entite SOURCE >>** : c'est
    l'element itere, et ce qui est itere est le **slot 5 `SelectAllActors`** du selecteur source,
    donc un ACTEUR DEJA RESOLU (`SelectUnit` -> `IsUnitFoot || IsTile -> GetUnit`). Cette phrase a
    porte l'inverse et a fait rendre des ids de TUILE a `Enemies`/`Friends` : `1094 TheLantern`
    posait alors `Pinned` sur PERSONNE, sans erreur (#1030-r5). Demonstration : docstring
    d'`Enemies`. Les call-sites unit-domain restent inchanges dans les deux lectures
    (`GetUnitOrMachine(unit) == unit`), ce qui est exactement ce qui a rendu la faute invisible."""
    if isinstance(elem, dict):
        return elem
    p = _entity_pos(elem, getattr(ctx, "board", None))
    if p is None:
        return None
    p = (int(p[0]), int(p[1]))
    for u in (ctx.units or ()):
        if not isinstance(u, dict) or not _is_alive(u):
            continue
        if p in [(int(f[0]), int(f[1])) for f in _feet(u)]:
            return u
    return None


class TilesWithEnemies(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$TilesWithEnemies(of)` -- le noeud n'a PAS de
    selecteur a lui : son corps natif tient en DEUX lignes, et le port les mirrore telles quelles.

        entities = DSLSelectors.Enemies(of, <this+0x20 = AllAliveUnits>, 3)
        return     DSLSelectors.Tiles(entities)

    Donc : les tuiles occupees par les unites ENNEMIES DU REFERENT `of`. Les trois pieces sont
    LUES, pas choisies -- la source est le champ PARTAGE `AllAliveUnits@+0x20` (pas `AllUnits`,
    cf. #514), le `selectionType` est le litteral `3 = OnlyAliveAndTargetable`, et le referent est
    l'ARGUMENT (`Owner@+0x30` chez son unique consommateur porte,
    `...NovaChargeAbility$$GetAdditionalMarkedTiles`) -- surtout pas le caster par defaut.

    `Tiles` = `UnitsMainTilesSelector` = la MAIN TILE par entite (pas l'empreinte). `as_ids` a la
    meme semantique que sur `Tiles` ci-dessus : positions par defaut, ids sur demande."""
    def __init__(self, of: TargetsSelector, as_ids: bool = False):
        self.of, self.as_ids = of, bool(as_ids)

    def select(self, ctx):
        enemies = Enemies(AllAliveUnits(), reference=self.of,
                          selection_type=int(UnitSelectionType.OnlyAliveAndTargetable))
        return Tiles(enemies, as_ids=self.as_ids).evaluate(ctx)


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
        for u in _entities_of(self.source, ctx):
            # `Distinct()` porte sur l'IDENTITE D'ENTITE. Un dict d'unite la porte dans sa cle
            # `id` ; une TUILE, elle, EST son identite (id de tuile, ou position) -- le `u.get`
            # inconditionnel levait `AttributeError` sur le domaine TUILE, ce qu'exige le call-site
            # `Unique(<tuiles>)` de `...NovaChargeAbility$$GetAdditionalMarkedTiles`.
            k = u.get("id") if isinstance(u, dict) else u
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
    défaut None → trait ABSENT (convention HasFlag) → set vide.

    `selection_type` = le 4e argument NATIF -- `DSLSelectors$$UnitsWithTrait(this, entities, trait,
    selectionType)` alloue `UnitsWithTraitSelector..ctor(this, state, entities, trait, 1,
    selectionType)`, le `1` etant le flag << avec >> (`UnitsWithoutTrait` pose `0` au meme rang, meme
    ctor). `None` (defaut) = aucun filtre = comportement HISTORIQUE (#585-r1)."""
    def __init__(self, source: TargetsSelector, trait, selection_type=None):
        self.source, self.trait = source, trait
        self.selection_type = selection_type

    def select(self, ctx):
        ht = ctx.has_trait or (lambda u, t: False)
        st = self.selection_type
        return [u for u in self.source.evaluate(ctx)
                if ht(u, self.trait) and (st is None or _selection_ok(u, st, ctx))]


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


class UnitsWithRarity(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$UnitsWithRarity(units, rarity, unitSelectionType)` ->
    `IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select` (#999-r3) -- MIRROR 1:1 :

        inner = this-><+0x18>;  selType = this-><+0x24>
        if (inner == null) throw
        src  = inner.Select(entities, selType)             # slot 3 = Select(entities, selectionType)
        out  = new List<IEntity>()
        foreach (entity in src)
            buc = IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent(entity)
            if (buc == null) throw
            if (buc-><+0x74> == this-><+0x20>) out.Add(entity)
        return out

    ⚠ **AUCUN filtre de `UnitSelectionType` par ELEMENT ici, et ce n'est pas un oubli** : le natif
    ne fait qu'en TRANSMETTRE la valeur au selecteur INTERIEUR (`inner.Select(entities, selType)`)
    et sa propre boucle ne compare QUE la rarete. Cote port, c'est donc le noeud `source` qui porte
    son `selection_type` (ex. `UnitsWithRarity(Friends(owner, all_units, selection_type=3),
    Rarity.Mythic)`) -- rajouter ici un `_selection_ok` par element serait un SECOND filtre que le
    natif n'applique pas. C'est pourquoi ce ctor n'a pas de parametre `selection_type` : un
    parametre inerte se recopierait en croyant filtrer.

    SUBSTRAT : `BaseUnitComponent.Rarity` (+0x74), canal `combatSnapshot.units[].rarity` (#1039) ->
    `UnitContext.rarity` -> cle `rarity` du dict d'unite (`entities_from_state`).

    DEGRADATION NOMMEE -- une unite dont la rarete n'est PAS MESUREE (`None`) est **EXCLUE**, comme
    si son ordinal differait. Meme choix, meme raison que `triggers.HasRarity` : les consommateurs
    natifs de ce selecteur (`BlightedLandEffect`, `GuardianConstruct_ExtraDamagePctEffect`) s'en
    servent pour DESIGNER LES BENEFICIAIRES d'un bonus -- garder une unite non mesuree lui
    accorderait un bonus que le natif lui refuse peut-etre."""
    def __init__(self, source: TargetsSelector, rarity):
        self.source, self.rarity = source, rarity

    def select(self, ctx):
        want = int(self.rarity)
        out = []
        for u in self.source.evaluate(ctx):
            r = u.get("rarity") if isinstance(u, dict) else getattr(u, "rarity", None)
            if r is not None and int(r) == want:
                out.append(u)
        return out


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


class UnitsWithRangedWeapons(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$UnitsWithRangedWeapons(entities)` ->
    `IdunBattle.Entities.Selectors.UnitsWithWeaponsSelector$$Select` : garde les entites de `source`
    dont AU MOINS UN profil d'arme satisfait `IsMatchingWeapon`.

    ⚠ CE N'EST PAS LE COMPLEMENT EXACT d'`UnitsWithoutRangedWeapons` ci-dessous, et les deux
    differences sont LUES, pas deduites -- ce sont DEUX classes natives distinctes
    (`UnitsWithWeaponsSelector` vs `UnitsWithoutWeaponsSelector`) :

      * le predicat n'est pas `get_IsRanged` mais un FILTRE A QUATRE CHAMPS. La factory alloue
        `UnitsWithWeaponsSelector..ctor(state, entities, minRange: Nullable<int>(2), maxRange: null,
        requiredDamageProfile: null, excludedDamageProfile: null)` -- le `2` est LU (un
        `Nullable<int>` construit sur place et passe en 3e argument), et `IsMatchingWeapon` s'y
        reduit alors a « l'arme porte un `Range` ET `Range >= 2` ». Meme SEUIL que
        `weapon_is_melee`, donc meme verdict que `has_ranged_weapon` sur toute arme du kit ;
      * une entite dont `UnitExtensions$$GetUnit` rend `null` (une TUILE, une MoW) est **JETEE**
        ici -- la boucle `while (lVar8 == 0)` du `Select` reboucle sur l'iterateur -- la ou
        `UnitsWithoutWeaponsSelector` la GARDE. Les polarites degenerees sont donc OPPOSEES.

    `SelectUniqueUnits(<+0x18>, entities, 1)` : le litteral `1` = `UnitSelectionType.OnlyAlive` est
    LU dans le `Select`, exactement comme chez le jumeau negatif. Ce noeud ne prend PAS de
    `selectionType` cote natif (`DSLSelectors$$UnitsWithRangedWeapons(this, entities)` a DEUX
    arguments) -> aucun parametre ici : un optionnel inviterait a y passer le `3` de l'appelant,
    qui appartient au noeud PRECEDENT.

    SUBSTRAT : `ctx.has_ranged_weapon(unit)` -- le MEME accesseur que `UnitsWithoutRangedWeapons`
    (foyer `engine.services.battle_query.has_ranged_weapon`, cable par `entities_from_state`), donc
    un seul port du predicat. Accesseur ABSENT -> AUCUNE entite gardee : c'est la polarite du natif
    (il n'ajoute que sur match), et la seule qui ne fabrique pas un buff depuis une non-mesure.

    Call-site porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfTheMontkaAbility$$
    ExecuteBehaviour` (1210, `tauFarsight`)."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        # `SelectUniqueUnits(<+0x18>, entities, 1)` -- `1` = `OnlyAlive`, litteral LU dans
        # `UnitsWithWeaponsSelector$$Select` (meme site que chez le jumeau negatif).
        units = [u for u in self.source.evaluate(ctx)
                 if _selection_ok(u, UnitSelectionType.OnlyAlive, ctx)]
        hrw = getattr(ctx, "has_ranged_weapon", None)
        if hrw is None:
            return []                               # aucun match prouvable -> le natif n'ajoute rien
        # `GetUnit(entity) == null` -> JETEE (le natif reboucle sans `Add`). Le port le mirrore en
        # ecartant tout element que le predicat ne peut pas classer (`visualId` absent).
        return [u for u in units if u.get("visualId") is not None and hrw(u)]


def non_steppable_or_object_units(source: TargetsSelector, selection_type=None) -> TargetsSelector:
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

    Consommateurs natifs lus : `HellfyreMissileRackAbility$$ExecuteBehaviour` / `$$GetAffectedUnits`,
    et les deux predicats de ciblage de `SquigLaunchasAbility`
    (`IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$HasMinimumAdjacentOrks` /
    `$$HasMinimumAdjacentFriendlyUnits`) -- un decoy ou un objet adjacent a la cible NE COMPTE PAS
    comme << unite amie adjacente >>.

    ⚠ Ce module portait DEUX definitions homonymes de cette factory (#585-r1) : celle-ci et une
    seconde, plus bas, au corps IDENTIQUE mais a la docstring differente. La seconde ECRASAIT
    celle-ci a l'import, donc l'avertissement `0xd` ci-dessus et les consommateurs
    `HellfyreMissileRack` etaient dans du code MORT -- personne ne pouvait le voir en lisant le
    fichier de haut en bas. Les deux sont fusionnees ici.

    `selection_type` est PROPAGE aux deux `UnitsWithoutTrait`, comme le fait la factory native (le
    pseudo-code ci-dessus le montre au 3e argument des deux appels). Le port l'AVALAIT : un appelant
    qui connaissait son litteral ne pouvait pas le faire descendre (#585-r1). `None` = comportement
    HISTORIQUE."""
    return And(And(source, UnitsWithoutTrait(source, int(UnitTrait.Steppable),     # 0x1b
                                             selection_type)),
               UnitsWithoutTrait(source, int(UnitTrait.Object), selection_type))   # 0xd


def units_with_traits(source: TargetsSelector, traits, selection_type=None) -> TargetsSelector:
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
    ImperialUnits` (`[0x1a = Imperial, 0x10 = Hero]` = les « Imperial Characters » de l'i2).

    `selection_type` est PROPAGE a chaque `UnitsWithTrait`, comme le fait la boucle native (3e
    argument, cf. le pseudo-code). Le port l'AVALAIT (#585-r1) ; `None` = comportement HISTORIQUE."""
    left = source
    for t in traits:
        left = And(left, UnitsWithTrait(source, int(t), selection_type))
    return left


def non_steppable_units(source: TargetsSelector, selection_type=None) -> TargetsSelector:
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
    `$$ValidTargets`.

    `selection_type` est PROPAGE a l'`UnitsWithoutTrait`, comme le fait la factory native (3e
    argument, cf. le pseudo-code). Le port l'AVALAIT (#585-r1) ; `None` = comportement HISTORIQUE."""
    return And(source, UnitsWithoutTrait(source, int(UnitTrait.Steppable),        # 0x1b
                                         selection_type))


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
    ennemis adjacents TAUNTES -- un decoy `Steppable` ou un `Object` de plateau n'est pas taunte).

    `selection_type` = le 2e argument NATIF, que la factory PROPAGE a son `Units` interne (le
    pseudo-code ci-dessus le montre : `Units(entities, unique: true, selectionType)`), pas au
    `FromTrigger`. Le port l'AVALAIT (#585-r1) -- et le call-site cite juste au-dessus passe
    justement `3`. `None` = comportement HISTORIQUE."""
    def __init__(self, entities: TargetsSelector, selection_type=None):
        self.entities = entities
        self.selection_type = selection_type

    def select(self, ctx):
        ht = ctx.has_trait or (lambda u, t: False)
        return [u for u in Units(self.entities, self.selection_type).evaluate(ctx)
                if not ht(u, int(UnitTrait.Object))          # 0xd
                and not ht(u, int(UnitTrait.Steppable))]     # 0x1b


def hero_units(source: TargetsSelector, selection_type=None) -> TargetsSelector:
    """`IdunBattleLogic.Entities.DSLFactory$$HeroUnits(source, mask)` — MIRROR du decompile : la factory
    native N'ALLOUE PAS de selecteur dedie, elle DELEGUE textuellement a
    `IdunBattleLogic.Entities.DSLFactory$$UnitsWithTrait(source, 0x10, mask)`. On mirror donc la FACTORY
    (fonction de composition), pas une classe inventee — `0x10` = `UnitTrait.Hero` (16). Consommateur porte :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.AdaptiveStrategyAbility$$GetNonCharacterFriendsSelector`
    (`Friends(...) op_Subtraction HeroUnits(...)` = les amis NON-Character).

    Le 2e argument natif (`mask` dans la signature ci-dessus) EST le `selectionType` : la factory le
    passe tel quel a `UnitsWithTrait(source, 0x10, mask)`. Le port l'AVALAIT (#585-r1) ; `None` =
    comportement HISTORIQUE."""
    return UnitsWithTrait(source, int(UnitTrait.Hero), selection_type)          # 0x10


def non_steppable_units(source: TargetsSelector, selection_type=None) -> TargetsSelector:
    """`IdunBattleLogic.Entities.DSLSelectors$$NonSteppableUnits(entities, selectionType)` -- MIRROR
    du decompile : la factory native N'ALLOUE PAS de selecteur dedie, son corps ENTIER est

        UnitsWithoutTrait(entities, 0x1b, selectionType)  op_BitwiseAnd  <entities>

    (le `op_BitwiseAnd` prend `entities` a GAUCHE au call-site : `op_BitwiseAnd(entities, right)`).
    `0x1b` = `UnitTrait.Steppable` (27) -- LU dans `frida/enums.tsv`, jamais deduit du nom. On mirror
    donc la FACTORY (fonction de composition), pas une classe inventee -- meme regime que `hero_units`
    juste au-dessus.

    L'intersection avec la source est REDONDANTE en valeur (le filtre ne peut qu'enlever), mais elle
    est ECRITE dans le natif et `And` preserve l'ordre de `a` : on la garde pour que l'arbre porte la
    meme forme. Consommateur porte :
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TimesplinterMantleAbility$$GetTargets`."""
    return And(source, UnitsWithoutTrait(source, int(UnitTrait.Steppable), selection_type))   # 0x1b


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


class UnitsDefeatedBy(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$UnitsDefeatedBy(unit)` ->
    `IdunBattle.Entities.Selectors.UnitsDefeatedBySelector$$Select` -- MIRROR du decompile
    (`rnca9r7q6c`, #951) :

        result = new OrderedSet<IEntity>();
        foreach (var e in <source>.Select(entities)) {
            var stats = e.GetComponent<ActorStatisticsComponent>();
            AddUnits(result, stats.<+0xa8>);      // defaites en MELEE
            AddUnits(result, stats.<+0xb0>);      // les autres
        }

    et `$$AddUnits(result, ids)` :

        foreach (var id in ids) { var u = state.GetEntity(id); if (u != null) result.Add(u); }

    Trois consequences LUES, dont deux qu'un port naif aurait perdues :
      * les DEUX listes sont reunies -- c'est l'UNION, pas les seules defaites en melee (le
        selecteur qui, lui, ne prend que la melee est `$$UnitsDefeatedByMeleeAttack`, une AUTRE
        factory et une AUTRE classe : `UnitsDefeatedByMeleeAttackSelector`) ;
      * les MORTS en font partie -- rien ici ne filtre sur la liveness ; le seul rejet est
        « l'id ne resout pas en entite » ;
      * `OrderedSet` : ordre d'inscription, sans doublon.

    Substrat cote port : la cle `defeatedUnits` du dict d'unite (`ActorStatisticsComponent` @+0xa8
    UNION @+0xb0), alimentee par `components.register_defeated_unit`. `_units_of` normalise la
    source (un ref-unite SEUL devient `[dict]`), comme partout ailleurs dans ce module.

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TrophyTakerAbility$$
    GetCritChanceMultiplier` = `Count(NormalUnits(UnitsDefeatedBy(Owner@+0x30), Any))`."""
    def __init__(self, source: TargetsSelector):
        self.source = source

    def select(self, ctx):
        par_id = {}
        for u in (ctx.units or ()):
            if isinstance(u, dict) and u.get("id") is not None:
                par_id.setdefault(int(u["id"]), u)
        vus, out = set(), []
        for src in _units_of(self.source, ctx):
            if not isinstance(src, dict):
                continue
            for i in (src.get("defeatedUnits") or ()):
                # `if (u != null) result.Add(u)` : un id qui ne resout pas est IGNORE, il ne
                # devient pas une entree nulle -- sinon `Count` compterait des fantomes.
                u = par_id.get(int(i))
                if u is not None and int(i) not in vus:
                    vus.add(int(i))
                    out.append(u)
        return out


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
    `SurroundingEnemies.reference`.)

    ⚠ DEUX SURCHARGES d'ARITE 4, meme nom affiche, INDISCERNABLES dans le pseudo-C (#585-r3) :

      * variante A `IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends(this, unit, unique,
        selectionType)` = `Friends(unit, Units(AdjacentTiles(unit), unique, selectionType) - unit,
        selectionType)` -> PROPAGE le litteral aux DEUX etages ;
      * variante B `IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends(this, unit, unitTile,
        unique)` = `Friends(unit, Units(AdjacentTiles(unitTile), unique, 3) - unitTile, 3)` -> `3`
        EN DUR aux deux etages ; son 3e argument est l'ANCRE GEOMETRIQUE (donc `center` ici, quand
        `reference` = `unit`), pas un booleen.

    Lire le 4e argument de la variante B comme un `selectionType` donnerait `1` = `OnlyAlive` : le
    filtre qui n'ecarte PAS `Untargetable`, soit l'inverse exact de ce que ce parametre repare.
    Trancher par les XREFS ENTRANTES, jamais par le pseudo-C seul.
    `None` (defaut) = aucun filtre = comportement HISTORIQUE."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector | None = None,
                 reference: TargetsSelector | None = None, selection_type=None):
        self.center, self.radius = center, radius or Const(1)
        self.reference = reference
        self.selection_type = selection_type

    def select(self, ctx):
        # ordre = `AdjacentTiles` (liste d'adjacence STOCKEE, `boardGraph.neighbours` brut) -- R28-1
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx),
                       board=getattr(ctx, "board", None), order="adjacent")
        ref = resolve_unit(self.reference, ctx) if self.reference is not None else ctx.caster
        ct = (ref or {}).get("team")
        st = self.selection_type
        # predicat PUR en (unite, selectionType) : les deux passages natifs sont idempotents
        return [u for u in ring if u.get("team") == ct
                and (st is None or _selection_ok(u, st, ctx))]


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
    `center`).

    `selection_type` = le DERNIER argument NATIF (#585-r3). Les QUATRE surcharges de
    `IdunBattleLogic.Entities.DSLSelectors$$SurroundingEnemies` le portent en DERNIERE position et le
    propagent aux deux etages (`Units(..., unique, st)` puis `Enemies(unit, ..., st)`) : AUCUNE n'en
    code un en dur, donc **pas** de piege de litteral implicite ici -- les surcharges ne different
    que par la separation `unit`/`unitTile` et par le typage du `range`. `None` (defaut) = aucun
    filtre = comportement HISTORIQUE."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector,
                 reference: TargetsSelector | None = None, selection_type=None):
        self.center, self.radius, self.reference = center, radius, reference
        self.selection_type = selection_type

    def select(self, ctx):
        # ordre = `SurroundingTiles` (triple boucle CUBE d'`IterateSurroundingTiles`) -- R28-1
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx),
                       board=getattr(ctx, "board", None), order="surrounding")
        ref = resolve_unit(self.reference, ctx) if self.reference is not None else ctx.caster
        ct = (ref or {}).get("team")
        st = self.selection_type
        return [u for u in ring if u.get("team") != ct
                and (st is None or _selection_ok(u, st, ctx))]


class SurroundingFriends(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$SurroundingFriends(center, radius)` = `Friends(SurroundingUnits(center,
    radius))` : alliés (team == caster) à dist <= radius du centre, centre exclu."""
    def __init__(self, center: TargetsSelector, radius: TargetsSelector, selection_type=None):
        self.center, self.radius = center, radius
        self.selection_type = selection_type

    def select(self, ctx):
        # ordre = `SurroundingTiles` (triple boucle CUBE d'`IterateSurroundingTiles`) -- R28-1
        ring = _within(ctx.units, self.center.evaluate(ctx), self.radius.evaluate(ctx),
                       board=getattr(ctx, "board", None), order="surrounding")
        ct = (ctx.caster or {}).get("team")
        st = self.selection_type
        # `selection_type` = le DERNIER argument NATIF (#585-r3). Comme pour `SurroundingEnemies`, les
        # QUATRE surcharges de `IdunBattleLogic.Entities.DSLSelectors$$SurroundingFriends` le portent en
        # derniere position et le propagent aux deux etages (`Units(..., unique, st)` puis
        # `Friends(unit, ..., st)`) -- aucune n'en code un EN DUR, donc pas de piege de litteral
        # implicite ici. `None` (defaut) = aucun filtre = comportement HISTORIQUE.
        return [u for u in ring if u.get("team") == ct
                and (st is None or _selection_ok(u, st, ctx))]


class SortByFormula(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLFactory$$SortByFormula(source, formula[, ascending])` → `IdunBattle.Entities.Selectors.SortByFormulaSelector$$Select` : trie la source par `formula` évaluée PAR ÉLÉMENT.
    ⚠ flag natif : 0 (défaut) → DESCENDANT, 1 → ASCENDANT. Tri STABLE (mergesort .NET ≡ `sorted`).

    ⚠ **LE SLOT LIE EST `AbilityEntities.ActiveTarget@+0x20`, ET IL EST LU, PAS DEDUIT (#927).**
    `SortByFormulaSelector$$Select` copie l'`AbilityEntities` recue dans sa closure
    (`<>c__DisplayClass4_0+0x10 .. +0x138`) puis passe `OrderBy`/`OrderByDescending` un `Func<IEntity,
    int>` dont le corps
    (`SortByFormulaSelector.u003Cu003Ec__DisplayClass4_0$$u003CSelectu003Eb__0`) fait EXACTEMENT
    deux choses : `closure+0x30 = s` -- c.-a-d. `<la copie d'entities>+0x20` -- puis
    `(<le selecteur>+0x20 = formula).Calculate(<la copie>)`. `+0x20` de l'`AbilityEntities` est le
    slot `ActiveTarget` (le MEME que `ChainBehaviourBehaviour$$Execute` ecrit avant chaque coup, cf.
    `runner/abilities/behaviours/chain.py`), donc une formule qui lit `ActiveTarget()` voit bien
    l'element courant du tri. La docstring precedente annoncait « binding `subject`, comme Filter » :
    c'etait une DEDUCTION par analogie, jamais une lecture.

    Le port lie **les deux** roles (`subject` ET `active_target`) : cote natif il n'y a qu'UN slot,
    et les deux noeuds du port (`Subject`, `ActiveTarget`) sont deux lectures du meme
    `+0x20`/`factory+0x180`. Ecrire `active_target` seul casserait les consommateurs deja portes qui
    ecrivent `Subject()`/`It()` dans leur formule (`MindControl` 1164, `DarkTalonStrike`,
    `ThriceBlessedConflagration`, `LeadingTheCharge`, `ArcaneShield`) sans rien corriger -- ils
    designent le meme element. Ce qui CHANGE, c'est qu'une formule ecrite avec `ActiveTarget()` --
    le nom que le decompile cite -- est desormais evaluable ici."""
    def __init__(self, source: TargetsSelector, formula: TargetsSelector, ascending: bool = False):
        self.source, self.formula, self.ascending = source, formula, ascending

    def select(self, ctx):
        lst = list(self.source.evaluate(ctx))
        return sorted(lst,
                      key=lambda u: self.formula.evaluate(replace(ctx, subject=u, active_target=u)),
                      reverse=not self.ascending)


class SortUnitsByDamageUtility(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$SortUnitsByDamageUtility(targets, caster, ability,
    utilityDefinition, damage, unitSelectionType, hits)` -- le NOEUD ; le `$$Select` du selecteur
    (`IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector`) est deja porte, integralement
    et confronte live, dans `runner/operations/damage_utility.py`. Ce noeud ne le REECRIT PAS : il
    l'appelle par l'accesseur `ctx.sort_units_by_damage_utility`, comme `PickRandomly` appelle
    `ctx.pick_randomly`. Une seconde implementation du tri serait une divergence garantie.

    ⚠ **QUATRE SURCHARGES portent ce nom**, et le port doit en designer UNE. Tranche par les XREFS
    ENTRANTES, pas par la proximite : `MartialExemplarAbility$$ExecuteBehaviour` appelle celle a
    SEPT arguments dont l'`ability` est un `IAbilityTypeSelector` (partagee avec
    `RitesOfMorkai`/`FinalJustice`/`Doombolt`/`WyrdmakersHelm`) ; les trois autres sont
    `(targets, caster, ability:ActiveAbilityType, …)`, `(targets, caster, damage, …)` et
    `(targets, damage, …)`, et les DEUX dernieres DELEGUENT a celle-ci apres avoir bati leurs
    defauts. C'est le foyer, et c'est lui que ce noeud mirrore.

    `damage` = noeud VALEUR (`IAmountFormula`). Le selecteur natif l'evalue UNE fois
    (`(+0x40).Calculate(entities)`) et s'en sert comme borne de prediction ; `NormalAttackDamage(
    Owner)` = `StatAmountFormula(unit, StatType.Attack)`, donc un SCALAIRE -> `dmin == dmax`. Un
    noeud a plage (`MinMaxDamage`) exposerait deux bornes ; aucun call-site porte ne le fait ici.

    `ability` = noeud `IAbilityTypeSelector` ; `UnitNormalAttackType(Owner)` rend exactement le
    defaut natif (`AbilityOrEffect(GetNormalAttackType(owner))`), donc `None` cote port -- ce n'est
    pas une omission, c'est la MEME valeur par les deux chemins. `utility_definition` reste
    IMPLICITE : le port impératif code `UtilityDefinition(0x23 = UtilityType.Damage)`, la seule que
    les quatre surcharges construisent (`UtilityDefinition$$.ctor(this, 0x23)`).

    `selection_type` = le 6e argument (`UnitSelectionType`), applique a la SOURCE
    (`(+0x20).SelectUnits(entities, unitSelectionType)`) ; `hits` = le 7e (`null` -> 1).

    `ctx.sort_units_by_damage_utility` absent (contexte hors runner : prediction, test de noeud) ->
    la source est rendue TELLE QUELLE, ordre intact. DEGRADATION nommee : sans `State` la prediction
    native n'est pas evaluable, et rendre `[]` ferait disparaitre des cibles. #889-r5."""
    def __init__(self, targets: TargetsSelector, caster: TargetsSelector,
                 damage, ability: TargetsSelector = None, selection_type=None, hits=None):
        self.targets, self.caster, self.damage = targets, caster, damage
        self.ability, self.selection_type, self.hits = ability, selection_type, hits

    def select(self, ctx):
        src = [u for u in _units_of(self.targets, ctx) if isinstance(u, dict)]
        st = self.selection_type
        if st is not None:                          # `SelectUnits(entities, unitSelectionType)`
            src = [u for u in src if _selection_ok(u, st, ctx)]
        fn = getattr(ctx, "sort_units_by_damage_utility", None)
        if fn is None or not src:
            return src                              # degradation nommee (cf. docstring)
        owner = resolve_unit(self.caster, ctx)
        dmg = (self.damage.evaluate(ctx) if hasattr(self.damage, "evaluate") else self.damage)
        n = 1 if self.hits is None else int(
            self.hits.evaluate(ctx) if hasattr(self.hits, "evaluate") else self.hits)
        # `AbilityOrEffect(GetNormalAttackType(owner))` quand le slot `+0x28` est nul OU quand il
        # rend precisement l'attaque normale : dans les deux cas le port passe `None`, que
        # `damage_utility` resout par `GetNormalAttackType(owner)` -- le MEME natif.
        aid = None
        if self.ability is not None:
            aid = self.ability.evaluate(ctx)
        # `damage` est un `IAmountFormula` : SCALAIRE pour `NormalAttackDamage(Owner)`
        # (`StatAmountFormula` -> dmin == dmax), mais `IdunBattle.Entities.Abilities.
        # BaseTriggeredAbility$$MinMaxDamage` est une PLAGE -- et c'est ce que passe
        # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.EcstaticSlaughterAbility$$CreateBehaviour`.
        # Un noeud qui rend `(dmin, dmax)` est donc transmis TEL QUEL au foyer de tri ; tout autre
        # retour reste dedouble comme avant (aucun call-site anterieur ne rend de couple).
        if isinstance(dmg, tuple) and len(dmg) == 2:
            dmin, dmax = int(dmg[0] or 0), int(dmg[1] or 0)
        else:
            dmin = dmax = int(dmg or 0)
        ordered = fn([u.get("id") for u in src], dmin, dmax,
                     None if owner is None else owner.get("id"), n, aid)
        by_id = {u.get("id"): u for u in src}
        return [by_id[i] for i in ordered if i in by_id]


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

    Les DEUX `Nullable<TargetingRule>` (`ignoreRule` / `additionalRule`) sont VIDES a TOUS les
    call-sites lus (`IdunBattleLogic.Entities.Abilities.Active.Loki.SorcerousFacadeAbility$$GetTarget`
    et son `$$ExecuteBehaviour`, `IdunBattle.Entities.Effects.Loki.FearedInterrogator_TargetEffect$$
    CreateTargetSelector`, `...Loki.UnbreakableDutyAbility$$ExecuteBehaviour` #572) -> ce noeud ne les
    modelise pas ; les ajouter sans call-site serait speculatif.

    `range` L'EST, et ce module avait ecrit « le jour ou un call-site les pose, ils entrent ICI, pas
    dans un fork » : ce jour est #946.
    `IdunBattle.Entities.Effects.Loki.UnwaveringSentinel_CounterAttackEffect$$GetCounterAttackCondition`
    passe `DSLFormulas$$Direct(GetNumberConstant(cfg, AbilityConstantType.range))`. C'est donc un
    `IAmountFormula` (le port accepte un `AAmountFormula` ou un `int`), et le bloc natif qu'il arme
    fait AUSSI `opts.rules &= ~TargetMatchesDynamicRule` -- les deux ecritures vivent dans le foyer
    unique `runner/abilities/targeting.valid_normal_attack_targets`, pas ici.

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
    def __init__(self, unit: TargetsSelector, unit_tile: TargetsSelector = None, range=None):
        self.unit, self.unit_tile, self.range = unit, unit_tile, range

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
        if self.range is None:                         # `rangeSel@+0x28 == null` : aucun override
            return list(fn(u) or [])
        # `rangeSel != null` -> le natif EVALUE la formule puis arme `CustomRange(<valeur>)`. Un `int`
        # nu est accepte pour les tests de noeud ; un `AAmountFormula` passe par `calculate(ctx)`,
        # comme partout ailleurs.
        r = self.range.calculate(ctx) if hasattr(self.range, "calculate") else self.range
        if r is None:                                  # formule non evaluable -> pas d'override
            return list(fn(u) or [])
        return list(fn(u, range_override=int(r)) or [])


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

    `elev` = **`ctx.elev_by_pos`** (#433-r4-r1-r4-r1), le canal du contexte -- celui que
    `DslContext.__post_init__` derive du board par `entities/pathfinding/board.elevations_by_pos`, et
    que `UnitsDirectlyBehind` ci-dessus consomme deja. Ce noeud-ci re-derivait AU LIEU DE LE LIRE :
    `{k: t.get("elevation", 0) for k, t in ctx.board.by_coord.items()}`. Deux ecarts, tous deux reels :

      * le defaut `0` FABRIQUAIT une elevation pour toute tuile dont le canal ne porte pas la donnee,
        alors que le foyer OMET l'inconnu (tri-etat : `None` = pas de canal, une carte = les tuiles
        CAPTEES). Le `0` invente n'est pas neutre et devie dans les DEUX SENS, contre le contrat que
        `battle_query.is_target_tile_obscured` tient deja -- inconnue en `from`/`to` : le contrat rend
        `False` (jamais obscurci), le `0` faisait au contraire passer le seuil des qu'un mid valait
        `>= 2` (obscurcissement FABRIQUE) ; inconnue en MID : le contrat la RETIRE (`GetTileAt null ->
        pas bloquant`), ce qui bascule le cas diagonal sur la branche `len(mids) == 1`, PLUS
        bloquante, la ou le `0` la gardait dans le `all(...)` de la fat-line et ETEIGNAIT le blocage ;
      * la FORME du board : `by_coord` seul rendait `None` (passe-tout) sur un `Board` sans cette
        vue et sur tout board duck-type `by_id`, que le foyer, lui, sait lire. Et une injection
        EXPLICITE de `elev_by_pos` dans le contexte etait purement ignoree.

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
        # CANAL du contexte (#433-r4-r1-r4-r1) -- le MEME que consomme `UnitsDirectlyBehind`
        # ci-dessus : tri-etat `None` = pas de canal, et l'inconnu est OMIS, jamais rabattu sur `0`.
        # Cf. la docstring.
        elev = ctx.elev_by_pos
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


class UnitsAttackedThisTurn(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$UnitsAttackedThisTurn(attacker)` ->
    `IdunBattle.Entities.Selectors.UnitsAttackedThisTurnSelector$$Select` (#940).

    LU, terme a terme :

        result = new OrderedSet<IEntity>()
        holder = <attacker>.Select(entities).First()               // SelectSingle : le PREMIER
        foreach (id in holder.<ActorStatisticsComponent+0x40>) :    // l'OrderedSet d'ids
            e = state.GetEntity(id)
            if (e != null && EntityExtensions$$IsUnit(e)) result.Add(e)
        return result

    Autrement dit : les unites que le PORTEUR a frappees depuis le debut de son tour, **dans
    l'ordre des coups**. Le natif ne filtre NI la mort NI la ciblabilite -- seulement `IsUnit`
    (une entite-TUILE enregistree la serait ecartee) ; une cible tuee par le premier maillon
    d'une chaine reste donc dans la liste, et c'est exactement ce dont `KissOfDeath` a besoin
    pour atterrir a cote de sa derniere victime.

    Le substrat est `UnitComponent.units_attacked_this_turn` (mirror de `+0x40`, ecrit par
    `components.register_attack_made` au chokepoint post-resolution, remis a zero par
    `reset_units_attacked_this_turn` / `StartTurnOperation`). Il transite par la cle
    `unitsAttackedThisTurn` du dict d'unite, qui est dans `_LIVE_KEYS` : le champ MUTE pendant
    l'arbre qui le relit.

    `attacker` rend 0 unite (contexte sans caster) -> `[]`. `ctx.entity_by_id` absent (contexte
    hors runner : prediction, test unitaire) -> `[]` : le port DIT qu'il ne resout pas, il
    n'invente pas d'entite. Meme polarite que le natif quand `GetEntity` rend null."""
    def __init__(self, attacker: TargetsSelector):
        self.attacker = attacker

    def select(self, ctx):
        holders = _units_of(self.attacker, ctx)
        if not holders:                                  # `First()` sur une source VIDE
            return []
        holder = holders[0]
        ids = (holder or {}).get("unitsAttackedThisTurn") or ()
        by_id = getattr(ctx, "entity_by_id", None)
        out = []
        for eid in ids:
            u = by_id(eid) if by_id is not None else None
            if u is None:                                # repli : l'unite du pool `ctx.units`
                u = next((x for x in (ctx.units or ())
                          if isinstance(x, dict) and x.get("id") == eid), None)
            if isinstance(u, dict) and u.get("id") is not None:
                out.append(u)                            # `EntityExtensions$$IsUnit`
        return out


class ForcedAttackTargets(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$ForcedAttackTargets(unit)` ->
    `IdunBattle.Entities.Selectors.UnitForcedAttackTargetsSelector$$Select`, MIRROR du decompile :

        unit = <+0x18>.SelectSingle(entities)
        if (unit == null) return new List<Entity>()          # liste VIDE, pas null
        return ListExtensions.Map( UnitExtensions.GetOnlyTargets(unit), <Select>b__2_0 )

    -- soit : les ENTITES designees par les ids du `ForcedAttackTargetsComponent` du sujet. C'est
    le meme store que lit la regle de ciblage `TargetIsAllowedForCaster` (bit 23) via
    `IdunBattle.Entities.UnitExtensions$$GetOnlyTargets` -- le TAUNT, et, depuis #1015-r1, la voie
    incrementale `AddForcedAttackTargetBehaviour` du trait `InstinctiveBehaviour`.

    Le port lit le meme store par l'accesseur `ctx.only_targets` (cable sur le foyer unique
    `runner/abilities/targeting.get_only_targets`), puis resout chaque id en dict d'unite --
    exactement le `Map` natif. Accesseur absent (contexte hors runner) -> `[]`, et c'est une
    DEGRADATION nommee : sans `State` le composant n'existe pas, on ne l'invente pas."""
    __slots__ = ("unit",)

    def __init__(self, unit: TargetsSelector):
        self.unit = unit

    def select(self, ctx):
        u = resolve_unit(self.unit, ctx)                 # `SelectSingle(unit)`
        if u is None or u.get("id") is None:
            return []                                    # `unit == null` -> liste VIDE
        fn = getattr(ctx, "only_targets", None)
        if fn is None:
            return []                                    # canal non branche (cf. docstring)
        by_id = getattr(ctx, "entity_by_id", None)
        out = []
        for eid in (fn(int(u["id"])) or ()):
            e = by_id(eid) if by_id is not None else None
            if e is None:                                # repli : l'unite du pool `ctx.units`
                e = next((x for x in (ctx.units or ())
                          if isinstance(x, dict) and x.get("id") == eid), None)
            if isinstance(e, dict) and e.get("id") is not None:
                out.append(e)
        return out


def nearest_attackable_enemies(unit: TargetsSelector, distance_type: int = 0, max_distance=None):
    """`IdunBattleLogic.Entities.DSLSelectors$$NearestAttackableEnemies(unit, distanceType,
    maxDistance)` -- ce n'est PAS une classe de selecteur, c'est une COMPOSITION, transcrite
    noeud par noeud du decompile :

        e = Enemies( of = unit, entities = <DSLSelectors+0x20>, selectionType = 3 )
        e = UnitsWithoutTrait( e, UnitTrait.Steppable = 0x1b, selectionType = 3 )
        u = UnobscuredEntitiesSelector( query, <dsl+0x60>, e, unit )
        return NearestSelector( query, 3, <dsl+0x28>,
                                entities = u, target = unit, pathfindingUnit = unit,
                                distanceType, maxDistance )

    `<DSLSelectors+0x20>` = le champ PARTAGE `IdunBattle.Entities.Selectors.AllAliveUnitsSelector`
    (`EntityPool.AliveUnits`) -- lecture deja etablie par `spacewolves` / `necrons` / `thousandsons`,
    pas re-devinee ici. `selectionType = 3` = `OnlyAliveAndTargetable` aux TROIS sites.

    ⚠ `target` ET `pathfindingUnit` de `Nearest` recoivent le MEME `unit` : on cherche les ennemis
    les plus proches DE LUI, et c'est LUI qui sert de gabarit de pathfinding quand
    `distanceType == PathLength`. `distanceType = 0 = Simple` au seul call-site porte
    (`InstinctiveBehaviour_UpdateTargetAbility$$GetUpdatedForcedTarget`) -> distance HEX.

    « Attackable » ne designe donc AUCUN gate de ciblage : c'est litteralement
    « ennemi vivant et ciblable, non Steppable, non obscurci ». Le nom natif est trompeur ; les
    quatre noeuds, non."""
    from .pathing import Nearest                          # forme A locale : `pathing` n'importe PAS
    #                                                       ce module (aucun cycle a fermer), mais
    #                                                       l'import est garde LOCAL pour ne pas
    #                                                       allonger la cascade de `units` (lu par
    #                                                       ~200 modules) pour un seul appelant.
    sel = int(UnitSelectionType.OnlyAliveAndTargetable)   # le litteral `3` des trois sites
    e = Enemies(unit, AllAliveUnits(), selection_type=sel)
    e = UnitsWithoutTrait(e, int(UnitTrait.Steppable), selection_type=sel)
    u = Unobscured(e, unit)
    return Nearest(u, unit, pathfinding_unit=unit,
                   distance_type=int(distance_type), max_distance=max_distance)
