"""#433-r3-r2 -- le volet `Untargetable` du `UnitSelectionType` du noeud DSL `IsAdjacent`.

Le residu disait << STOCKE mais non CONSOMME >> et prescrivait de garder le champ INERTE. Les deux
sont PERIMES : #524 avait deja porte le volet `IsAlive`. Ce qui restait -- et que la docstring du
noeud lisait comme un no-op benin -- est le volet `HasFlag(unit, UnitFlag.Untargetable)`.

**Et le trou etait exactement la ou il coute le plus.**
`IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType` :

    if (selectionType == OnlyAlive)              return IsAlive(unit, state);
    if (selectionType == OnlyTargetable)         return !HasFlag(unit, 0x11);
    if (selectionType == OnlyAliveAndTargetable) return IsAlive(unit, state) && !HasFlag(unit, 0x11);
    return true;                                 // Any

`OnlyTargetable` (2) **n'appelle PAS `IsAlive`** : pour ce `selectionType`, le seul filtre natif
etait precisement le seul que le port n'avait pas -- donc le noeud ne filtrait **rien du tout**.
C'est le regime de `runner/operations/behaviour.py`
(`IdunBattleLogic.Entities.Abilities.Active.Loki.BattleFatigueAbility$$CreateTrigger` ->
`IsAdjacent(self@+0x30, dying@+0x60, 2)`).

Le canal du flag (`ctx.has_unit_flag`, mirror `IdunBattle.Entities.Components.UnitFlagsComponent$$Has`)
existe dans `DslContext` et est alimente par `entities_from_state` -- rien a seeder.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: La CASCADE D'IMPORTS (476 modules) est DERIVEE par le foyer depuis #531 -- elle couvre a elle
#: seule les huit chemins que ce fichier lit vraiment (`unit_selection_type`, `triggers`,
#: `selectors/units`, `effects/aura_selectors`, `unit_flag`, `dsl/base`, `operations/behaviour`,
#: `pathfinding/board`). Les recopier ici serait du bruit, et surtout une liste a maintenir a la
#: main a cote d'une derivation exacte.
DECLENCHEUR = {
    "chemins": (
        # Le SEUL chemin hors cascade, rendu par `probe_486r15 --proposer` : l'`__init__` du
        # paquet, que l'import differe du domaine d'effets traverse a la premiere evaluation.
        "scripts/python/engine/entities/__init__.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "les gardes portent sur le PREDICAT `MatchesUnitSelectionType` et ses DEUX canaux "
              "(`has_unit_flag`, `has_effect` sur `UNTARGETABLE_EFFECT_TYPES`) ; tout ce qu'elles "
              "lisent est dans la cascade d'imports DERIVEE, sauf l'`__init__` du paquet que "
              "l'import differe traverse. Aucun canal hors-import (ni `data/`, ni binaire, ni "
              "runner) n'intervient : le montage construit son board a la main.",
}

COLS, ROWS = 6, 6


def _tid(col, row):
    return col * ROWS + row


def _board():
    """Board PLAT au format `boardGraph` -- l'adjacence y est GEOMETRIQUE et la porte d'elevation
    inerte (`|dElev| = 0 < 2` partout), donc seul le filtre de selection peut changer un verdict."""
    import hexgeo
    from engine.entities.pathfinding.board import Board
    tuiles = []
    for col in range(COLS):
        for row in range(ROWS):
            voisins = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                       if 0 <= c < COLS and 0 <= r < ROWS]
            tuiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                           "walkable": True, "isWall": False, "neighbours": voisins})
    # Meme forme que `probe_433_r3_isadjacent_node.py::_toy_board` : `Board` prend la LISTE, et la
    # cle d'id est `id`. Le mode par defaut `native_sym` lit le champ `neighbours` fourni ci-dessus.
    return Board(tuiles)


def _ctx(units, caster, target, *, flags=None, effets=None):
    """`flags = {unit_id: {flag, ...}}` -> `ctx.has_unit_flag` ; `effets = {unit_id: {type, ...}}`
    -> `ctx.has_effect`. `None` = canal ABSENT (tri-etat)."""
    from engine.dsl.base import DslContext
    hf = he = None
    if flags is not None:
        def hf(u, flag, _f=flags):
            return int(flag) in _f.get(u.get("id"), set())
    if effets is not None:
        def he(u, t, *_a, _e=effets, **_k):
            return int(t) in _e.get(u.get("id"), set())
    return DslContext(units=list(units), caster=caster, target=target, board=_board(),
                      has_unit_flag=hf, has_effect=he)


@pytest.fixture
def montage():
    """Caster (1,1) et cible (1,2) -- VOISINES sur un board plat, donc adjacentes sans condition.
    Tout verdict `False` ci-dessous vient donc du FILTRE, pas de la geometrie."""
    caster = {"id": 1, "team": 0, "alive": True, "hp": 100, "pos": {"col": 1, "row": 1}}
    cible = {"id": 2, "team": 1, "alive": True, "hp": 100, "pos": {"col": 1, "row": 2}}
    return caster, cible


def _noeud(selection_type):
    from engine.entities.selectors.accessors import Target
    from engine.entities.selectors.tiles import Caster
    from engine.entities.triggers import IsAdjacent
    return IsAdjacent(Caster(), Target(), selection_type)


# ------------------------------------------------- etage 1 : le temoin NON NUL (sans le flag)
def test_sans_le_flag_la_paire_est_adjacente_pour_les_quatre_selection_types(montage):
    """Temoin : sans quoi un `False` partout se lirait comme une garde qui mord."""
    from engine.entities.unit_selection_type import UnitSelectionType
    caster, cible = montage
    for st in UnitSelectionType:
        ctx = _ctx([caster, cible], caster, cible, flags={})
        assert _noeud(st).should_trigger(ctx) is True, \
            "geometrie voisine + unites vivantes et ciblables : le filtre ne doit rien retirer"


# ------------------------------- etage 2 : le volet `Untargetable` MORD, et seulement ou il doit
def test_untargetable_ecarte_la_cible_pour_OnlyTargetable_et_OnlyAliveAndTargetable(montage):
    """LE gisement. `OnlyTargetable` (2) est le regime de `BattleFatigue` : le port n'y filtrait
    RIEN, puisque son unique volet porte (`IsAlive`) n'y est pas appele par le natif non plus."""
    from engine.entities.unit_flag import UnitFlag
    from engine.entities.unit_selection_type import UnitSelectionType
    caster, cible = montage
    flags = {2: {int(UnitFlag.Untargetable)}}
    assert _noeud(UnitSelectionType.OnlyTargetable).should_trigger(
        _ctx([caster, cible], caster, cible, flags=flags)) is False
    assert _noeud(UnitSelectionType.OnlyAliveAndTargetable).should_trigger(
        _ctx([caster, cible], caster, cible, flags=flags)) is False


def test_untargetable_ne_change_RIEN_pour_Any_ni_pour_OnlyAlive(montage):
    """La polarite se verifie DANS LES DEUX SENS : `MatchesUnitSelectionType` ne lit le flag QUE
    pour 2 et 3. Elargir le filtre a `OnlyAlive` serait une seconde faute, pas une correction."""
    from engine.entities.unit_flag import UnitFlag
    from engine.entities.unit_selection_type import UnitSelectionType
    caster, cible = montage
    flags = {2: {int(UnitFlag.Untargetable)}}
    assert _noeud(UnitSelectionType.Any).should_trigger(
        _ctx([caster, cible], caster, cible, flags=flags)) is True
    assert _noeud(UnitSelectionType.OnlyAlive).should_trigger(
        _ctx([caster, cible], caster, cible, flags=flags)) is True


def test_un_flag_AUTRE_que_Untargetable_ne_filtre_pas(montage):
    """`0x11` est LU (`UnitFlag.Untargetable`), pas << un flag quelconque >>."""
    from engine.entities.unit_flag import UnitFlag
    from engine.entities.unit_selection_type import UnitSelectionType
    caster, cible = montage
    flags = {2: {int(UnitFlag.Downed)}}
    assert _noeud(UnitSelectionType.OnlyTargetable).should_trigger(
        _ctx([caster, cible], caster, cible, flags=flags)) is True


# --------------- etage 2bis : LE CANAL QUI MORD VRAIMENT -- le domaine d'EFFETS, pas le flag
def test_le_domaine_UNTARGETABLE_EFFECT_TYPES_ecarte_la_cible_sans_aucun_flag():
    """⚠ C'EST CE CANAL-LA QUI EST VIVANT DANS LE RUNNER, et le voir manquer est tout le residu.

    Le port n'inscrit **jamais** `0x11` dans `UnitFlagsComponent` : le flag natif est pose par
    `IdunBattle.Entities.Effects.Common.UntargetableEffect$$ApplyInternal`, et le port modelise
    cette base par le DOMAINE de ses `EffectType` derives. Une correction qui n'aurait lu que
    `ctx.has_unit_flag` aurait donc rendu `targetable = True` PARTOUT -- une mesure affirmee a tort,
    pire qu'une non-mesure. Ici le canal des flags REPOND (comme en runner) et ne dit rien ; c'est
    le domaine d'effets qui tranche."""
    from engine.entities.effects.aura_selectors import UNTARGETABLE_EFFECT_TYPES
    from engine.entities.unit_selection_type import UnitSelectionType
    caster = {"id": 1, "team": 0, "alive": True, "hp": 100, "pos": {"col": 1, "row": 1}}
    cible = {"id": 2, "team": 1, "alive": True, "hp": 100, "pos": {"col": 1, "row": 2}}
    deep_strike = int(UNTARGETABLE_EFFECT_TYPES[0])
    ctx = _ctx([caster, cible], caster, cible, flags={}, effets={2: {deep_strike}})
    assert _noeud(UnitSelectionType.OnlyTargetable).should_trigger(ctx) is False, \
        "une unite en deep-strike porte le flag cote natif : le noeud doit l'ecarter du selecteur"
    assert _noeud(UnitSelectionType.Any).should_trigger(ctx) is True, \
        "et `Any` ne lit pas le flag -- la polarite se verifie dans les DEUX sens"


# --------------------------------------------------- etage 3 : le TRI-ETAT du canal absent
def test_canal_absent_le_filtre_DEGRADE_EN_VRAI_et_ne_refuse_rien(montage):
    """`ctx.has_unit_flag is None` = **PAS MESURE**. Le rabattre sur << pas de flag >> serait juste
    ici, mais le rabattre sur << flag pose >> ecarterait une unite que le natif compte : c'est la
    degradation RESTRICTIVE silencieuse. Le foyer degrade la clause en VRAI, et c'est ce que cette
    garde fige -- un contexte de test ou de face DECISION se comporte comme avant, bit pour bit."""
    from engine.entities.unit_selection_type import UnitSelectionType
    caster, cible = montage
    for st in UnitSelectionType:
        ctx = _ctx([caster, cible], caster, cible, flags=None)     # canal ABSENT
        assert _noeud(st).should_trigger(ctx) is True


def test_selection_type_None_ne_filtre_RIEN_meme_avec_le_flag(montage):
    """`None` n'est pas `Any` : c'est un call-site dont le 3e argument natif n'a PAS ete releve.
    Le rabattre sur `0` ferait passer pour une lecture ce qui n'en est pas une -- et ici les deux
    coincident, ce qui est precisement pourquoi la distinction doit etre gardee explicitement."""
    from engine.entities.unit_flag import UnitFlag
    caster, cible = montage
    flags = {2: {int(UnitFlag.Untargetable)}}
    assert _noeud(None).should_trigger(
        _ctx([caster, cible], caster, cible, flags=flags)) is True


# ----------------------------- etage 4 : UN SEUL foyer de predicat, partage avec les selecteurs
def test_le_noeud_et_les_selecteurs_partagent_le_MEME_foyer(montage, monkeypatch):
    """Le noeud avait ecrit un TROISIEME port du predicat (apres le foyer de #524 et le derivateur
    de `selectors/units.py`), a la main et aveugle au flag.

    ⚠ Cette garde verifie l'APPEL, pas l'import. Un test qui comparait seulement les identites
    (`triggers.selection_ok_from_ctx is <foyer>`) restait VERT sous la mutation qui remet le filtre
    local -- l'import survit a la scission de l'usage, donc il ne prouve rien. Le patch mord parce
    qu'il vise le binding DANS le module consommateur (forme B de la doctrine d'import)."""
    from engine.entities import triggers
    from engine.entities.selectors import units
    from engine.entities.unit_selection_type import UnitSelectionType, selection_ok_from_ctx
    assert units.selection_ok_from_ctx is selection_ok_from_ctx

    vus = []

    def _espion(u, st, ctx):
        vus.append((u.get("id"), int(st)))
        return True

    monkeypatch.setattr(triggers, "selection_ok_from_ctx", _espion)
    caster, cible = montage
    _noeud(UnitSelectionType.OnlyTargetable).should_trigger(
        _ctx([caster, cible], caster, cible, flags={}))
    assert vus, "le noeud doit PASSER PAR le foyer, pas seulement l'importer"
    assert {st for _, st in vus} == {int(UnitSelectionType.OnlyTargetable)}


def test_le_call_site_BattleFatigue_passe_bien_OnlyTargetable():
    """`BattleFatigueAbility$$CreateTrigger` -> `IsAdjacent(self@+0x30, dying@+0x60, 2)`. C'est le
    call-site que le trou rendait entierement permissif ; si un jour il changeait de
    `selectionType`, cette garde le dirait au lieu de laisser la correction devenir inerte."""
    from engine.entities.unit_selection_type import UnitSelectionType
    from engine.runner.operations import behaviour
    assert int(behaviour._IS_ADJACENT.selection_type) == int(UnitSelectionType.OnlyTargetable)
