"""CLIQUET #585-r3 -- l'ETAGE AMONT du `selectionType` : SEPT mirrors de selecteur.

Ce que la tranche a fait : `AdjacentUnits`, `AdjacentEnemies`, `AdjacentFriends`, `SurroundingUnits`,
`SurroundingEnemies`, `SurroundingFriends` et `UnitsFromFaction` ne portaient PAS le parametre --
un appelant qui connaissait son littéral ne pouvait pas le faire descendre. Ce fichier garde que
le parametre est LA, que son defaut ne change RIEN, et surtout qu'il MORD.

POURQUOI << MORD >> EST L'ASSERTION CENTRALE
-------------------------------------------
Poser un parametre et le voir dans une signature ne prouve rien : `introspection` passerait aussi
sur un parametre STOCKE et jamais LU. La degradation qu'on repare est PERMISSIVE et silencieuse
(le port retient une unite `Untargetable` que le natif ecarte), donc le seul canal de preuve est
un substrat ou les QUATRE valeurs de `UnitSelectionType` rendent des ensembles DIFFERENTS. C'est
l'etage 3, et il assertionne sa propre non-degenerescence.

CE QUE CE FICHIER NE PEUT PAS GARDER
------------------------------------
La distinction des SURCHARGES natives (`AdjacentFriends`/`AdjacentEnemies` ont deux variantes
d'arite 4, la seconde codant `3` en dur) est un fait du BINAIRE, pas du port : elle se tranche aux
XREFS ENTRANTES et se garde site par site, dans `test_585r1_selection_type_releve_offline.py`.

ASCII only (cp1252).
"""
from __future__ import annotations

#: Perimetre ETROIT et DERIVE : les fichiers dont une edition peut rendre faux ce qui est fige ici.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/entities/unit_flag.py",
        "scripts/python/engine/dsl/base.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Ce cliquet garde la PRESENCE, le DEFAUT et la MORSURE du parametre `selection_type` "
              "sur les sept mirrors de selecteur pose par #585-r3. Il ne lit ni le binaire ni les "
              "tables du build (`build: False`) : le seul axe qui peut le perimer est une edition "
              "du module qui porte les sept classes, du mirror d'enum, du mirror de `UnitFlag` "
              "ou du contexte DSL qui achemine `has_unit_flag`.",
}

import inspect

import pytest

from engine.entities.selectors.accessors import CasterTile, Const
from engine.entities.selectors.units import (AdjacentEnemies, AdjacentFriends, AdjacentUnits,
                                             SurroundingEnemies, SurroundingFriends,
                                             SurroundingUnits, UnitsFromFaction)
from engine.entities.unit_flag import UnitFlag
from engine.entities.unit_selection_type import UnitSelectionType

_ANY = int(UnitSelectionType.Any)
_ALIVE = int(UnitSelectionType.OnlyAlive)
_TARGETABLE = int(UnitSelectionType.OnlyTargetable)
_AAT = int(UnitSelectionType.OnlyAliveAndTargetable)

#: Les SEPT mirrors poses par #585-r3, avec l'ARITE HISTORIQUE (hors `self`) que la tranche ne
#: devait PAS bouger. C'est ce couple qui rend le test capable de voir une regression d'ORDRE des
#: parametres : un `selection_type` insere AVANT un parametre existant casserait tous les
#: call-sites positionnels du depot, en silence pour une simple introspection de presence.
MIRRORS = {
    AdjacentUnits: 2,
    AdjacentEnemies: 2,
    AdjacentFriends: 3,
    SurroundingUnits: 3,
    SurroundingEnemies: 3,
    SurroundingFriends: 2,
    UnitsFromFaction: 2,
}


# --------------------------------------------------- ETAGE 1 : le parametre EXISTE, et EN DERNIER

def test_etage1_les_sept_mirrors_portent_selection_type_en_DERNIERE_position():
    """Le parametre est present ET place APRES l'arite historique.

    Le second cran n'est pas cosmetique : les call-sites du depot passent leurs arguments en
    POSITIONNEL. Un `selection_type` glisse au milieu decalerait silencieusement `radius`,
    `reference` ou `faction` -- une regression que « le parametre existe » ne verrait pas."""
    ecarts = []
    for cls, arite in MIRRORS.items():
        params = [p for p in inspect.signature(cls.__init__).parameters if p != "self"]
        if "selection_type" not in params:
            ecarts.append("%s : parametre ABSENT -- l'etage amont est retombe, un appelant qui "
                          "connait son littéral ne peut plus le faire descendre" % cls.__name__)
            continue
        if params.index("selection_type") != arite:
            ecarts.append("%s : `selection_type` en position %d, attendu %d (apres l'arite "
                          "historique) -- les call-sites positionnels du depot sont decales"
                          % (cls.__name__, params.index("selection_type"), arite))
    assert not ecarts, "ETAGE AMONT #585-r3 rompu :\n  " + "\n  ".join(ecarts)


def test_etage1b_le_defaut_est_None_donc_le_comportement_HISTORIQUE_est_inchange():
    """`None` = aucun filtre. C'est ce qui rend la pose de l'etage observationnellement NULLE.

    Si un defaut passait a `3`, tous les call-sites encore MUETS du releve se mettraient a filtrer
    des unites que le natif garde -- une regression RESTRICTIVE, celle-la, et bien plus visible que
    la permissive... mais introduite par le correctif meme qui devait la fermer."""
    mauvais = [cls.__name__ for cls in MIRRORS
               if inspect.signature(cls.__init__).parameters["selection_type"].default is not None]
    assert not mauvais, ("defaut != None sur %r : la pose de l'etage n'est plus neutre" % mauvais)


# --------------------------------------------------- le substrat

COLS, ROWS = 7, 7


def _board():
    """Board PLAT : adjacence purement geometrique, elevation inerte -- tout verdict vient donc du
    FILTRE, jamais du terrain."""
    import hexgeo
    from engine.entities.pathfinding.board import Board
    tuiles = []
    for col in range(COLS):
        for row in range(ROWS):
            voisins = [c * ROWS + r for (c, r) in hexgeo.neighbors(col, row)
                       if 0 <= c < COLS and 0 <= r < ROWS]
            tuiles.append({"id": col * ROWS + row, "col": col, "row": row, "elevation": 0,
                           "walkable": True, "isWall": False, "neighbours": voisins})
    return Board(tuiles)


def _u(uid, team, col, row, alive):
    """⚠ La POSITION passe par la cle `pos` (`{col,row}`) : c'est ce que lisent `_pos`/`_feet` du
    foyer `engine/dsl/base.py`. Des `col`/`row` a plat laissent `_feet` rendre `[]` -- donc TOUT
    selecteur geometrique rend l'ensemble VIDE, et chaque assertion de l'etage 3 passerait pour un
    accord alors qu'elle ne mesure rien. C'est la degenerescence que `test_etage3b` intercepte."""
    return {"id": uid, "team": team, "pos": {"col": col, "row": row},
            "alive": alive, "hp": 10 if alive else 0}


#: Caster en (3,3) ; les cinq autres occupent ses SIX tuiles adjacentes, donc le champ des sept
#: selecteurs a la fois, et ne different QUE par ce que `MatchesUnitSelectionType` regarde.
#:
#: ⚠ IL FAUT UN `Untargetable` DANS CHAQUE CAMP, et ce n'est pas une precaution : `AdjacentEnemies`
#: /`SurroundingEnemies` ne voient QUE l'equipe B. Avec un seul temoin cote allie, ces deux-la
#: rendaient le meme ensemble pour les quatre littéraux -- un accord DEGENERE, exactement le regime
#: contre lequel ce fichier existe.
_CASTER = _u(1, "A", 3, 3, True)
_ALLIE_OK = _u(2, "A", 3, 2, True)
_ALLIE_CACHE = _u(3, "A", 4, 3, True)          # vivant, `UnitFlag.Untargetable`
_ENNEMI_OK = _u(4, "B", 2, 3, True)
_ENNEMI_CACHE = _u(5, "B", 3, 4, True)         # vivant, `UnitFlag.Untargetable`
_ENNEMI_MORT = _u(6, "B", 2, 2, False)         # temoin de la regle #57m (cf. etage 3c)

_UNITS = [_CASTER, _ALLIE_OK, _ALLIE_CACHE, _ENNEMI_OK, _ENNEMI_CACHE, _ENNEMI_MORT]
_CACHES = {3, 5}
_FACTIONS = {u["id"]: "Orks" for u in _UNITS}


def _ctx():
    """`has_unit_flag` marque 3 (allie) et 5 (ennemi) `Untargetable` -- le SEUL canal qui separe
    `OnlyAlive` d'`OnlyAliveAndTargetable`, c'est-a-dire le couple que ce chantier repare."""
    from engine.dsl.base import DslContext

    def hf(u, flag):
        return u.get("id") in _CACHES and int(flag) == int(UnitFlag.Untargetable)

    return DslContext(units=list(_UNITS), caster=_CASTER, target=None, board=_board(),
                      has_unit_flag=hf, faction_of=lambda u: _FACTIONS.get(u.get("id")))


def _fabrique(cls, st):
    """Construit chaque mirror avec le MEME champ geometrique (adjacence au caster) -- seul le
    littéral varie d'un appel a l'autre."""
    if cls is UnitsFromFaction:
        return cls(AdjacentUnits(CasterTile(), Const(1)), "Orks", selection_type=st)
    if cls in (SurroundingUnits, SurroundingEnemies, SurroundingFriends):
        return cls(CasterTile(), Const(1), selection_type=st)
    return cls(CasterTile(), Const(1), selection_type=st)


#: Ce que CHAQUE littéral doit retenir, par mirror -- `MatchesUnitSelectionType` croise avec le
#: filtre d'equipe propre a chaque selecteur. Le caster (1) est exclu partout (`_within` retire le
#: centre) et le MORT (6) l'est aussi, QUEL QUE SOIT le littéral -- y compris `Any`.
#:
#: ⚠ Ce dernier point est une MESURE, pas un oubli, et il change quel couple de littéraux est
#: discriminant : `_within` filtre les vivants EN AMONT du `selectionType` (mirror de
#: `IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select`, qui resout l'occupant par le
#: `TileContentComponent` -- un mort n'est plus DEBOUT sur sa tuile, cf. #57m). Sur un selecteur
#: d'OCCUPATION, `Any` et `OnlyAlive` sont donc indistinguables, et c'est le couple
#: `OnlyAlive` / `OnlyAliveAndTargetable` qui porte la preuve -- soit exactement le couple que
#: #585 a mesure live sur `spaceRockfist` en deep strike.
_ATTENDU = {
    AdjacentUnits:       {_ANY: {2, 3, 4, 5}, _ALIVE: {2, 3, 4, 5}, _TARGETABLE: {2, 4}, _AAT: {2, 4}},
    AdjacentEnemies:     {_ANY: {4, 5},       _ALIVE: {4, 5},       _TARGETABLE: {4},    _AAT: {4}},
    AdjacentFriends:     {_ANY: {2, 3},       _ALIVE: {2, 3},       _TARGETABLE: {2},    _AAT: {2}},
    SurroundingUnits:    {_ANY: {2, 3, 4, 5}, _ALIVE: {2, 3, 4, 5}, _TARGETABLE: {2, 4}, _AAT: {2, 4}},
    SurroundingEnemies:  {_ANY: {4, 5},       _ALIVE: {4, 5},       _TARGETABLE: {4},    _AAT: {4}},
    SurroundingFriends:  {_ANY: {2, 3},       _ALIVE: {2, 3},       _TARGETABLE: {2},    _AAT: {2}},
    UnitsFromFaction:    {_ANY: {2, 3, 4, 5}, _ALIVE: {2, 3, 4, 5}, _TARGETABLE: {2, 4}, _AAT: {2, 4}},
}


# --------------------------------------------------- ETAGE 2 : le defaut ne filtre RIEN

def test_etage2_sans_litteral_chaque_mirror_rend_EXACTEMENT_ce_qu_il_rendait():
    """Le defaut `None` doit rendre le MEME ensemble que `Any` -- c'est la definition de
    << comportement historique inchange >>, et elle est ici MESUREE et non affirmee."""
    ctx = _ctx()
    ecarts = []
    for cls in MIRRORS:
        sans = {u["id"] for u in _fabrique(cls, None).evaluate(ctx)}
        avec_any = {u["id"] for u in _fabrique(cls, _ANY).evaluate(ctx)}
        if sans != avec_any:
            ecarts.append("%s : defaut rend %r, `Any` rend %r -- la pose de l'etage a CHANGE le "
                          "comportement des call-sites encore muets" % (cls.__name__,
                                                                        sorted(sans), sorted(avec_any)))
    assert not ecarts, "\n  ".join(ecarts)


# --------------------------------------------------- ETAGE 3 : le parametre MORD, sur les SEPT

@pytest.mark.parametrize("cls", list(MIRRORS), ids=lambda c: c.__name__)
def test_etage3_chaque_mirror_applique_MatchesUnitSelectionType_par_element(cls):
    """CONTRE-EPREUVE : un parametre stocke et jamais lu passerait l'etage 1 sans broncher.

    On exige la partition exacte que le foyer natif prescrit, POUR LES QUATRE valeurs, et on exige
    que ces quatre ensembles ne soient pas tous egaux -- sinon le substrat serait degenere et
    l'accord ne prouverait rien (le regime que #585-r1 a nomme : un temoin non discriminant dont
    l'accord se cite ensuite comme une preuve)."""
    ctx = _ctx()
    rendus = {}
    ecarts = []
    for st, attendu in _ATTENDU[cls].items():
        vu = {u["id"] for u in _fabrique(cls, st).evaluate(ctx)}
        rendus[st] = vu
        if vu != attendu:
            ecarts.append("%s / littéral %d : rend %r, `MatchesUnitSelectionType` prescrit %r"
                          % (cls.__name__, st, sorted(vu), sorted(attendu)))
    assert not ecarts, "\n  ".join(ecarts)

    distincts = {frozenset(v) for v in rendus.values()}
    assert len(distincts) >= 2, (
        "%s rend le MEME ensemble pour les quatre littéraux (%r) : le parametre est DECORATIF, ou "
        "le substrat a perdu son `Untargetable` / son mort" % (cls.__name__, sorted(rendus[_ANY])))
    assert rendus[_ALIVE] != rendus[_AAT], (
        "%s : `OnlyAlive` et `OnlyAliveAndTargetable` rendent le MEME ensemble -- c'est LE couple "
        "que ce chantier repare (le premier n'ecarte PAS `Untargetable`), et le test ne le voit "
        "plus. Verifier que `ctx.has_unit_flag` arrive bien jusqu'au mirror." % cls.__name__)


def test_etage3b_le_substrat_porte_bien_ses_temoins():
    """Garde-fou du garde-fou : si les unites `Untargetable` sortaient du champ geometrique,
    l'etage 3 deviendrait vert en ne mesurant plus rien. On l'assertionne separement pour que la
    cause soit LISIBLE au lieu d'apparaitre comme une partition qui << ne colle plus >>."""
    ctx = _ctx()
    assert ctx.has_unit_flag(_ALLIE_CACHE, int(UnitFlag.Untargetable)) is True
    assert ctx.has_unit_flag(_ENNEMI_CACHE, int(UnitFlag.Untargetable)) is True
    assert ctx.has_unit_flag(_ALLIE_OK, int(UnitFlag.Untargetable)) is False
    assert ctx.has_unit_flag(_ENNEMI_OK, int(UnitFlag.Untargetable)) is False
    tous = {u["id"] for u in AdjacentUnits(CasterTile(), Const(1)).evaluate(ctx)}
    assert tous == {2, 3, 4, 5}, (
        "les quatre temoins vivants ne sont plus TOUS dans le champ geometrique du selecteur (%r) "
        ": deplacer les unites, jamais relacher l'attendu" % sorted(tous))


def test_etage3c_le_MORT_est_exclu_par_l_amont_quel_que_soit_le_litteral():
    """La regle #57m, NOMMEE plutot que subie.

    `_within` mirror `IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select` : il resout
    l'occupant par le `TileContentComponent`, et un mort n'y est plus. Le `selectionType` tombe
    DONC en aval d'un ensemble deja purge -- ce qui est correct, et ce qui explique pourquoi
    `Any` ne ramene pas le cadavre. Sans cette assertion, un lecteur de la table `_ATTENDU`
    croirait a un oubli ; avec elle, il lit la mecanique."""
    ctx = _ctx()
    for st in (_ANY, _ALIVE, _TARGETABLE, _AAT):
        vus = {u["id"] for u in AdjacentUnits(CasterTile(), Const(1),
                                              selection_type=st).evaluate(ctx)}
        assert _ENNEMI_MORT["id"] not in vus, (
            "le mort (%d) ressort d'un selecteur d'OCCUPATION sous le littéral %d -- le filtre "
            "vivant de `_within` (#57m) a saute" % (_ENNEMI_MORT["id"], st))
    assert _ENNEMI_MORT["alive"] is False, "le temoin mort n'est plus mort"


# --------------------------------------------------- ETAGE 4 : la reference d'equipe reste LUE

def test_etage4_le_parametre_neuf_n_a_pas_ecrase_la_reference_d_equipe():
    """`AdjacentFriends` / `SurroundingEnemies` portent DEJA un `reference` -- et c'est justement
    entre lui et le parametre neuf que l'ordre pouvait deraper.

    `AdjacentFriends(centre, radius, reference=<ennemi>)` doit rendre les ALLIES DE CET ENNEMI,
    c'est-a-dire l'equipe B ; si `selection_type` avait ete insere avant `reference`, un call-site
    positionnel aurait mis un entier a la place du noeud-reference et le collapse caster serait
    revenu EN SILENCE -- le camp exactement INVERSE."""
    ctx = _ctx()
    from engine.entities.selectors.units import UnitSet

    class _Ref:
        """Noeud-role minimal qui rend l'ennemi vivant : `resolve_unit` accepte un selecteur."""
        def evaluate(self, _ctx):
            return [_ENNEMI_OK]

    sans_filtre = {u["id"] for u in
                   AdjacentFriends(CasterTile(), Const(1), reference=_Ref()).evaluate(ctx)}
    assert sans_filtre == {4, 5}, (
        "`AdjacentFriends(reference=<ennemi>)` rend %r au lieu de l'equipe B de la reference : "
        "le parametre neuf a decale `reference`, et le collapse caster est revenu EN SILENCE "
        "-- le camp exactement INVERSE" % sorted(sans_filtre))

    avec_filtre = {u["id"] for u in
                   AdjacentFriends(CasterTile(), Const(1), reference=_Ref(),
                                   selection_type=_AAT).evaluate(ctx)}
    assert avec_filtre == {4}, (
        "les DEUX axes ne cohabitent pas : `reference` designe bien l'equipe B, mais le littéral "
        "n'y ecarte plus l'`Untargetable` (%r)" % sorted(avec_filtre))
    assert UnitSet is not None      # import garde : la fabrique ci-dessus reste lisible
