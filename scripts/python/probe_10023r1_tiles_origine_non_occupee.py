"""#10023-r1 -- `Tiles(origin)` sur une origine en domaine TUILE. LA PREMISSE DU RESIDU ETAIT FAUSSE.

Le residu annoncait TROIS defauts. **UN SEUL etait reel** ; les deux autres reposaient sur une
resolution TUILE -> OCCUPANT que la MESURE LIVE refute :

  (a) « une origine TUILE VIDE ne fait rien retrancher au natif » -- **FAUX, mesure**.
      `probe_10023r1_squig_pool_live.py` : **11 casts sur 11** de `1201 SquigMine` (dont le masque
      porte `TargetTileIsFree`, donc la tuile ciblee est TOUJOURS vide) rendent `nrOfTiles + 1`
      tuiles minees, jamais `nrOfTiles`. Or `targets = Union(cible, picked)` est UNIQUE : si la
      cible etait dans le pool, `PickRandomly` l'aurait tiree avec `p = nrOfTiles/|pool| = 4/8` par
      cast, soit `0,5^11 = 0,05 %` de chance d'obtenir 11/11 par hasard. La tuile ciblee est donc
      RETRANCHEE -- exactement ce que faisait le port d'avant.
  (b) « `_within` appelle `_main_tile(center)` SANS `board` » -- **VRAI**. Sur une origine en
      domaine ID, `_origin_tiles(list[int], None)` rend `[]` : exclusion silencieusement VIDE.
      C'est la meme signature de faute que celle que #10023 a fermee a l'autre foyer. CORRIGE.
  (c) « une origine a N unites DISTINCTES retranche N main tiles » -- **VRAI, mais INERTE** :
      la boucle de `UnitsMainTilesSelector$$Select` est verbatim, et les 35 instanciations
      recensees (etage 6) sont toutes mono-unite. Porte quand meme, en domaine UNITE seulement.

POURQUOI LE DECOMPILE ET LA MESURE SE REJOIGNENT -- la porte VIRTUELLE de `SelectAllUnits` :

    // IdunBattleLogic.Entities.DSLSelectors$$SurroundingTiles, branche includeCenter == 0
    SurroundingTiles(origin, includeCenter: 1, ...) op_Subtraction Tiles(origin)
    // IdunBattleLogic.Entities.DSLSelectors$$Tiles
    Tiles(entities) = new UnitsMainTilesSelector(inner: entities, state)
    // IdunBattle.Entities.Selectors.UnitsMainTilesSelector$$Select
    foreach (entity in inner.<slot 3 = SelectAllUnits>(entities, selectionType: 0))
        if ((tile = EntityExtensions$$GetMainTile(entity, state)) != null) result.Add(tile);
    // IdunBattle.DSL.TargetsSelector$$SelectAllUnits
    list = this.<slot 0x17 = Select>(entities);
    if (this.<klass+0x278>()) return list;         // <- TEL QUEL, AUCUNE resolution
    foreach (e in list) if (e != null && (u = SelectUnit(this, e, 0)) != null) out.Add(u);
    // IdunBattle.Entities.EntityExtensions$$GetMainTileId, TROISIEME branche
    if (!IsTile(entity)) return 0;  return <id>(entity);   // une TUILE est SA PROPRE main tile

`klass+0x278` n'est PAS la propriete que teste `TargetsSelector$$SelectTiles`, qui lit
`klass+0x268` : deux offsets DISTINCTS dans le meme binaire. La vtable IL2CPP commence a
`klass+0x138`, entrees de `0x10` -> slots 20 et 19, soit `get_ReturnsOnlyUnits` et
`get_ReturnsOnlyTiles`. Le slot `Target` (`<DSLSelectors+0x60>`, une classe DISTINCTE de celle de
`CasterTiles` en `+0x58` -- lu dans `DSLSelectors$$InitializeShared`) declare rendre des UNITES,
donc l'entite-TUILE qu'il porte sur un cast tile-target traverse SANS etre resolue.

Cette propriete n'est PAS resoluble en statique (corps triviaux `return 1` dedupliques par IL2CPP,
aucun proprietaire nomme) et n'est PAS portee : residu `#10023-r3`.

Chaque etage porte sa CONTRE-EPREUVE. Board SYNTHETIQUE et plat : le sujet est le domaine de
l'origine, pas le terrain. ASCII only (cp1252).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

import hexgeo                                                          # noqa: E402
from engine.dsl import base as B                                       # noqa: E402
from engine.entities.pathfinding.board import Board                    # noqa: E402
from engine.entities.selectors import accessors as A                   # noqa: E402

COLS = ROWS = 9


class _Fixe:
    """Feuille de test : rend une valeur BRUTE la ou le DSL attend un `TargetsSelector`."""

    def __init__(self, v):
        self.v = v

    def evaluate(self, ctx):
        return self.v


class _Ctx:
    """`DslContext` minimal -- seuls `board` et `units` sont lus par le chemin mesure."""

    def __init__(self, board, units):
        self.board = board
        self.units = units


def _board() -> Board:
    tuiles = []
    for col in range(COLS):
        for row in range(ROWS):
            tuiles.append({"id": col * 100 + row, "col": col, "row": row,
                           "elevation": 0, "walkable": True,
                           "isWall": False, "isInFog": False})
    return Board(tuiles, adjacency="evenq")


def _unite(uid: int, feet: list[tuple[int, int]], team: int = 1) -> dict:
    return {"id": uid, "team": team, "player": team, "alive": True, "hp": 100,
            "pos": {"col": feet[0][0], "row": feet[0][1]},
            "feet": [{"col": c, "row": r} for (c, r) in feet], "_traits": set()}


def _ids(board: Board, positions) -> list[int]:
    return [board.id_at(c, r) for (c, r) in positions]


# --------------------------------------------------------------------------------------------
# ETAGE 0 -- RECENSEMENT : les call-sites d'EXCLUSION passent-ils leur substrat ?
# --------------------------------------------------------------------------------------------
def _homonymes_locaux(arbre) -> set:
    """Les `def _main_tile*` DEFINIS dans ce fichier -- un HOMONYME, pas le mirror.

    `engine/runner/abilities/loki/momentum.py` en porte un (`_main_tile(state, unit_id)`, qui lit
    `state.units` directement) : le compter ferait rougir E0 sur du code qui n'a rien a voir. Ce
    n'est pas une liste blanche -- c'est le nom RESOLU, derive du fichier lui-meme."""
    return {n.name for n in ast.walk(arbre)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name in ("_main_tile", "_main_tiles")}


def _importes_de_base(arbre) -> set:
    """Les noms `_main_tile*` importes DEPUIS `engine.dsl.base` (relatif ou absolu)."""
    out = set()
    for n in ast.walk(arbre):
        if not isinstance(n, ast.ImportFrom):
            continue
        mod = n.module or ""
        if not (mod == "base" or mod.endswith("dsl.base") or mod.endswith(".base")):
            continue
        for a in n.names:
            if a.name in ("_main_tile", "_main_tiles"):
                out.add(a.asname or a.name)
    return out


def etage0_recensement() -> int:
    """Un mirror de `Tiles(origin)` qui n'a ni `board` ni `units` ne peut PAS resoudre l'occupant.

    Le recenseur ne liste aucun call-site attendu : il visite TOUS les fichiers de
    `scripts/python/engine/**`, RESOUT le nom (import depuis `dsl.base`, ou definition dans
    `dsl/base.py` lui-meme, homonymes locaux ECARTES) et rend le nombre d'arguments EFFECTIFS. Un
    appel a moins de trois arguments est structurellement aveugle aux regimes (a) et (b).

    Il mesure AUSSI que les appelants de `_within` passent la population ENTIERE (`ctx.units`) :
    `_est_unite` s'appuie dessus, et un sous-ensemble la rendrait incomplete."""
    racine = RACINE / "engine"
    sites: list[tuple[str, int, str, int]] = []
    ecartes = 0
    for f in sorted(racine.rglob("*.py")):
        try:
            arbre = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = f.relative_to(RACINE).as_posix()
        locaux = _homonymes_locaux(arbre)
        est_le_foyer = rel == "engine/dsl/base.py"
        noms = _importes_de_base(arbre) | ({"_main_tile", "_main_tiles"} if est_le_foyer else set())
        for n in ast.walk(arbre):
            if not isinstance(n, ast.Call):
                continue
            nom = n.func.id if isinstance(n.func, ast.Name) else (
                n.func.attr if isinstance(n.func, ast.Attribute) else None)
            if nom not in ("_main_tile", "_main_tiles"):
                continue
            if nom not in noms or (nom in locaux and not est_le_foyer):
                ecartes += 1
                continue
            sites.append((rel, n.lineno, nom, len(n.args) + len(n.keywords)))
    print("[E0] call-sites RESOLUS vers engine/dsl/base : %d (homonymes ecartes : %d)"
          % (len(sites), ecartes))
    aveugles = []
    for rel, ligne, nom, nargs in sites:
        marque = "OK" if nargs >= 3 else "AVEUGLE"
        print("     %-58s:%-5d %s(%d args) -> %s" % (rel, ligne, nom, nargs, marque))
        if nargs < 3:
            aveugles.append((rel, ligne, nargs))
    if not sites:
        print("[E0] ECHEC : aucun call-site trouve -- le recenseur ne mesure RIEN.")
        return 1
    if aveugles:
        print("[E0] ECHEC : %d call-site(s) sans substrat d'occupation (board+units)." % len(aveugles))
        return 1
    print("[E0] OK : tous les call-sites resolus passent board ET units.")
    return _etage0bis_within_recoit_toute_la_population(racine)


def _etage0bis_within_recoit_toute_la_population(racine: Path) -> int:
    """`_est_unite` lit l'APPARTENANCE a `units` : un appelant de `_within` qui passerait un
    SOUS-ENSEMBLE la rendrait incomplete, et l'origine (le caster) n'y serait plus reconnue."""
    mauvais = []
    total = 0
    for f in sorted(racine.rglob("*.py")):
        try:
            arbre = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = f.relative_to(RACINE).as_posix()
        if rel == "engine/dsl/base.py":
            continue
        for n in ast.walk(arbre):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "_within" and n.args):
                continue
            total += 1
            a0 = n.args[0]
            plein = (isinstance(a0, ast.Attribute) and a0.attr == "units"
                     and isinstance(a0.value, ast.Name) and a0.value.id == "ctx")
            if not plein:
                mauvais.append((rel, n.lineno, ast.unparse(a0)))
    print("[E0bis] appelants de _within : %d ; population partielle : %d" % (total, len(mauvais)))
    for rel, ligne, src in mauvais:
        print("        %-58s:%-5d units = %s" % (rel, ligne, src))
    if total == 0:
        print("[E0bis] ECHEC : aucun appelant trouve -- le recenseur ne mesure RIEN.")
        return 1
    if mauvais:
        print("[E0bis] ECHEC : `_est_unite` s'appuie sur une population qui n'est pas entiere.")
        return 1
    print("[E0bis] OK : tous passent ctx.units entier.")
    return 0


# --------------------------------------------------------------------------------------------
# ETAGE 1 -- ORIGINE = TUILE VIDE : le natif ne retranche RIEN
# --------------------------------------------------------------------------------------------
def etage1_tuile_vide() -> int:
    """MESURE LIVE (`probe_10023r1_squig_pool_live.py`) : la tuile VIDE **EST** retranchee.

    C'est l'inverse de ce que l'enonce de #10023-r1 annoncait. Sur `1201 SquigMine`, dont le
    masque `TargetTileIsFree` garantit une tuile ciblee VIDE, **11 casts sur 11** ont rendu
    `nrOfTiles + 1` tuiles minees : la cible n'est jamais dans le pool. Si elle y etait,
    `Union(cible, picked)` l'aurait dedoublonnee avec `p = 4/8` par cast -- soit `0,5^11 = 0,05 %`
    d'obtenir 11/11 par hasard. Cet etage FIGE ce resultat."""
    b = _board()
    #: Une unite ailleurs, pour que `units` ne soit pas vide -- un accord en regime degenere ne
    #: prouverait rien.
    ailleurs = _unite(10001, [(0, 0)])
    ctx = _Ctx(b, [ailleurs])
    centre = (4, 4)
    tid = b.id_at(*centre)
    sel = A.SurroundingTiles(_Fixe([tid]), _Fixe(1), include_center=False)
    sortie = set(sel.select(ctx))
    attendu = {b.id_at(c, r) for (c, r) in hexgeo.disk(centre[0], centre[1], 1)} - {tid}
    print("[E1] origine = tuile VIDE %s (id %d), rayon 1" % (str(centre), tid))
    print("     natif MESURE (la tuile ciblee est RETRANCHEE) : %d tuiles" % len(attendu))
    print("     port                                          : %d tuiles" % len(sortie))
    if tid in sortie:
        print("[E1] ECHEC : la tuile VIDE n'est PAS retranchee -- 11 casts live disent qu'elle l'est")
        return 1
    if sortie != attendu:
        print("[E1] ECHEC : ensemble inattendu %s" % (sorted(sortie),))
        return 1
    # CONTRE-EPREUVE : `include_center=True` desarme l'exclusion, la tuile revient.
    sel2 = A.SurroundingTiles(_Fixe([tid]), _Fixe(1), include_center=True)
    if tid not in set(sel2.select(ctx)):
        print("[E1] ECHEC (contre-epreuve) : include_center=True ne rend pas la tuile centrale")
        return 1
    print("[E1] OK : tuile VIDE retranchee, et l'exclusion se desarme.")
    return 0


# --------------------------------------------------------------------------------------------
# ETAGE 1bis -- ORIGINE = PIED SECONDAIRE : le natif retranche LE PIED DONNE, pas la main tile
# --------------------------------------------------------------------------------------------
def etage1bis_pied_secondaire() -> int:
    """Corollaire de la mesure : sans resolution d'occupant, l'entite-TUILE est SA PROPRE main
    tile (`EntityExtensions$$GetMainTileId`, 3e branche : `if (!IsTile(e)) return 0; return id(e)`).

    Donc une origine qui designe un pied SECONDAIRE retranche CE PIED, et laisse la main tile de
    l'occupant dans l'anneau. L'enonce du residu voulait l'inverse ; cet etage garde le sens
    MESURE, et il rougirait si on retablissait la resolution."""
    b = _board()
    principale, second = (4, 4), (5, 4)
    mortarion = _unite(10003, [principale, second])
    ctx = _Ctx(b, [mortarion])
    tid_second, tid_main = b.id_at(*second), b.id_at(*principale)
    sel = A.SurroundingTiles(_Fixe([tid_second]), _Fixe(1), include_center=False)
    sortie = set(sel.select(ctx))
    attendu = {b.id_at(c, r) for (c, r) in hexgeo.disk(second[0], second[1], 1)} - {tid_second}
    print("[E1bis] origine = PIED SECONDAIRE %s ; main tile de l'occupant = %s"
          % (str(second), str(principale)))
    print("        attendu %d tuiles (le PIED retranche, la main tile GARDEE)" % len(attendu))
    print("        port    %d tuiles" % len(sortie))
    if tid_second in sortie:
        print("[E1bis] ECHEC : le pied designe n'est pas retranche")
        return 1
    if tid_main not in sortie:
        print("[E1bis] ECHEC : la MAIN TILE est retranchee -- ce serait la resolution d'occupant, "
              "que la mesure live REFUTE")
        return 1
    if sortie != attendu:
        print("[E1bis] ECHEC : ensemble inattendu %s" % (sorted(sortie),))
        return 1
    print("[E1bis] OK : pied designe retranche, main tile gardee.")
    return 0


# --------------------------------------------------------------------------------------------
# ETAGE 2 -- L'APPEL SANS `board` de `engine/dsl/base.py::_within`
# --------------------------------------------------------------------------------------------
def etage2_within_domaine_id() -> int:
    """`_within(..., order='surrounding', include_center=False)` sur une origine en DOMAINE ID.

    Le port d'avant appelait `_main_tile(center)` SANS `board` : `_origin_tiles` d'un `list[int]`
    sans board rend `[]`, donc l'exclusion etait VIDE et l'occupant du centre SORTAIT du selecteur
    -- exactement la faute que #10023 a fermee a l'autre foyer."""
    b = _board()
    centre = (4, 4)
    occupant = _unite(10004, [centre])
    voisin = _unite(10005, [(4, 5)])
    units = [occupant, voisin]
    tid = b.id_at(*centre)
    out = B._within(units, [tid], 1, include_center=False, board=b, order="surrounding")
    ids = [u["id"] for u in out]
    print("[E2] _within(centre = [%d] en domaine ID, r=1, include_center=False)" % tid)
    print("     attendu [10005] (l'occupant du centre EXCLU) ; port %s" % (ids,))
    if 10004 in ids:
        print("[E2] ECHEC : l'occupant du centre n'est PAS exclu -- exclusion silencieusement vide")
        return 1
    if 10005 not in ids:
        print("[E2] ECHEC : le voisin a disparu -- l'exclusion mord trop large")
        return 1
    # CONTRE-EPREUVE : include_center=True -> l'occupant DOIT revenir.
    out2 = B._within(units, [tid], 1, include_center=True, board=b, order="surrounding")
    if 10004 not in [u["id"] for u in out2]:
        print("[E2] ECHEC (contre-epreuve) : include_center=True n'inclut pas l'occupant")
        return 1
    print("[E2] OK : exclusion armee en domaine ID, et desarmee par include_center.")
    return 0


# --------------------------------------------------------------------------------------------
# ETAGE 3 -- N UNITES DISTINCTES : `GetMainTile` est PAR ENTITE
# --------------------------------------------------------------------------------------------
def etage3_multi_unites() -> int:
    """DOMAINE UNITE -- la seule des trois corrections annoncees qui reste DEBOUT, et elle vient du
    decompile, pas d'une mesure : `UnitsMainTilesSelector$$Select` boucle sur les entites rendues
    par `SelectAllUnits` et ajoute `GetMainTile(entity)` pour CHACUNE.

    L'origine est ici une LISTE DE DICTS D'UNITE, pas d'ids : c'est le domaine ou aucune resolution
    tuile n'intervient, donc la mesure live ne le contredit pas. INERTE : les 35 instanciations
    recensees a l'etage 6 sont toutes mono-unite."""
    b = _board()
    a_pos, c_pos = (4, 4), (4, 6)
    ua, uc = _unite(10006, [a_pos]), _unite(10007, [c_pos])
    ctx = _Ctx(b, [ua, uc])
    tid_a, tid_c = b.id_at(*a_pos), b.id_at(*c_pos)
    sel = A.SurroundingTiles(_Fixe([ua, uc]), _Fixe(1), include_center=False)
    sortie = set(sel.select(ctx))
    print("[E3] origine = DEUX unites distinctes (%s, %s), en domaine UNITE"
          % (str(a_pos), str(c_pos)))
    print("     attendu : les DEUX main tiles retranchees")
    if tid_a in sortie or tid_c in sortie:
        restantes = [t for t in (tid_a, tid_c) if t in sortie]
        print("[E3] ECHEC : main tile(s) NON retranchee(s) : %s" % (restantes,))
        return 1
    union = set()
    for p in (a_pos, c_pos):
        union |= {b.id_at(c, r) for (c, r) in hexgeo.disk(p[0], p[1], 1)}
    if sortie != union - {tid_a, tid_c}:
        print("[E3] ECHEC : ensemble inattendu (%d tuiles)" % len(sortie))
        return 1
    print("[E3] OK : les deux main tiles retranchees, le reste de l'union garde.")
    return 0


# --------------------------------------------------------------------------------------------
# ETAGE 4 -- NON-REGRESSION #10023 : les SEPT tuiles de Mortarion retranchent UNE tuile
# --------------------------------------------------------------------------------------------
def etage4_non_regression_10023() -> int:
    b = _board()
    centre = (4, 4)
    empreinte = [centre] + [(c, r) for (c, r) in hexgeo.disk(centre[0], centre[1], 1)
                            if (c, r) != centre]
    mortarion = _unite(10008, empreinte)
    ctx = _Ctx(b, [mortarion])
    ids = _ids(b, empreinte)
    sel = A.SurroundingTiles(_Fixe(ids), _Fixe(1), include_center=False)
    sortie = set(sel.select(ctx))
    union = set()
    for p in empreinte:
        union |= {b.id_at(c, r) for (c, r) in hexgeo.disk(p[0], p[1], 1)}
    attendu = union - {b.id_at(*centre)}
    print("[E4] origine = les SEPT entites-tuile de l'empreinte (#10023)")
    print("     attendu %d tuiles (UNE SEULE retranchee) ; port %d" % (len(attendu), len(sortie)))
    if sortie != attendu:
        print("[E4] ECHEC : %d tuile(s) retranchee(s) au lieu d'une" % (len(union) - len(sortie)))
        return 1
    print("[E4] OK : une seule main tile retranchee, les six pieds secondaires gardes.")
    return 0


# --------------------------------------------------------------------------------------------
# ETAGE 5 -- SUBSTRAT ABSENT : la degradation est NOMMEE, pas silencieuse
# --------------------------------------------------------------------------------------------
def etage5_domaine_tuile_insensible_a_units() -> int:
    """En domaine TUILE, la sortie ne depend PAS de `units` -- consequence directe de la mesure :
    il n'y a aucune resolution d'occupant a faire, donc rien a mesurer dans la population.

    Cet etage est ce qui empeche la resolution de revenir par la petite porte : si un jour
    `_main_tiles` se remettait a lire l'occupation, ces trois appels cesseraient de coincider."""
    b = _board()
    centre = (4, 4)
    tid = b.id_at(*centre)
    occupant = _unite(10002, [centre])
    cas = (("units=None            ", None),
           ("units=[]              ", []),
           ("units=[1 ailleurs]    ", [_unite(10001, [(0, 0)])]),
           ("units=[l'OCCUPANT]    ", [occupant]))
    vus = []
    for etiquette, u in cas:
        got = B._main_tiles([tid], b, u)
        print("[E5] %s -> %s" % (etiquette, got))
        vus.append(got)
    if any(v != [centre] for v in vus):
        print("[E5] ECHEC : la sortie du domaine TUILE varie avec `units` -- une resolution "
              "d'occupant est revenue, alors que la mesure live la REFUTE")
        return 1
    #: CONTRE-EPREUVE : en domaine UNITE, `units` compte -- sinon l'etage ne mesurerait qu'une
    #: fonction constante et passerait meme si tout etait casse.
    empreinte = B._main_tiles([_unite(10003, [(2, 2), (3, 2)])], b, None)
    print("[E5] domaine UNITE (contre-epreuve) -> %s" % (empreinte,))
    if empreinte != [(2, 2)]:
        print("[E5] ECHEC (contre-epreuve) : le domaine UNITE ne rend pas la main tile")
        return 1
    print("[E5] OK : domaine TUILE insensible a `units`, domaine UNITE distinct.")
    return 0


# --------------------------------------------------------------------------------------------
# ETAGE 6 -- ATTEIGNABILITE : quels call-sites peuvent porter une origine MULTI-UNITES ?
# --------------------------------------------------------------------------------------------
#: Les QUATRE noeuds dont l'exclusion passe par `op_Subtraction Tiles(origin)` -- DERIVES du code :
#: ce sont ceux qui appellent `_within(order='surrounding')` sans `include_center=True`, plus
#: l'accesseur de tuiles. `order='adjacent'` est un AUTRE selecteur natif
#: (`AdjacentTilesSelector$$Select`, exclusion INTERNE sur l'EMPREINTE) et ne passe pas par ici.
NOEUDS_A_EXCLUSION = ("SurroundingTiles", "SurroundingUnits", "SurroundingEnemies",
                      "SurroundingFriends")

#: Accesseurs qui rendent UNE SEULE entite (donc au plus UNE main tile), lus dans
#: `entities/selectors/accessors.py` : les slots de role du contexte natif.
CENTRES_MONO = ("Caster", "Target", "Owner", "Actor", "Subject", "Self",
                "CasterTile", "TargetTile", "OwnerTile", "ActorTile", "Const")


def etage6_atteignabilite_multi_unites() -> int:
    """La question MULTI-UNITES, tranchee par une mesure et non par un raisonnement.

    `UnitsMainTilesSelector$$Select` retranche UNE main tile PAR ENTITE : une origine a N unites
    distinctes en retranche N. Le port le fait desormais (E3) ; reste a savoir si un call-site
    peut y arriver -- si non, la correction est une mise en conformite, pas un changement de
    comportement observable.

    Le recenseur visite TOUTES les instanciations des quatre noeuds a exclusion dans
    `engine/**` et deparse leur premier argument. Il ne classe pas « sur » : tout ce qui n'est pas
    un accesseur de role MONO sort en INDETERMINE et doit etre lu a la main. Un INDETERMINE n'est
    pas un echec -- c'est ce que ce probe RAPPORTE."""
    racine = RACINE / "engine"
    mono, indetermine = [], []
    for f in sorted(racine.rglob("*.py")):
        try:
            arbre = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = f.relative_to(RACINE).as_posix()
        for n in ast.walk(arbre):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id in NOEUDS_A_EXCLUSION and n.args):
                continue
            #: `include_center=True` -> AUCUNE exclusion, le noeud sort du perimetre.
            kw = {k.arg: k.value for k in n.keywords}
            ic = kw.get("include_center")
            if isinstance(ic, ast.Constant) and ic.value:
                continue
            src = ast.unparse(n.args[0])
            tete = src.split("(")[0].split(".")[-1]
            ligne = (rel, n.lineno, n.func.id, src)
            (mono if tete in CENTRES_MONO else indetermine).append(ligne)
    print("[E6] instanciations a exclusion armee : %d (MONO %d, INDETERMINE %d)"
          % (len(mono) + len(indetermine), len(mono), len(indetermine)))
    for rel, ligne, noeud, src in mono:
        print("     MONO         %-46s:%-5d %s(%s)" % (rel, ligne, noeud, src[:52]))
    for rel, ligne, noeud, src in indetermine:
        print("     INDETERMINE  %-46s:%-5d %s(%s)" % (rel, ligne, noeud, src[:52]))
    if not (mono or indetermine):
        print("[E6] ECHEC : aucune instanciation trouvee -- le recenseur ne mesure RIEN.")
        return 1
    print("[E6] OK (INVENTAIRE, jamais bloquant) : les INDETERMINE se lisent un par un.")
    return 0


def main() -> int:
    rc = 0
    for f in (etage0_recensement, etage1_tuile_vide, etage1bis_pied_secondaire,
              etage2_within_domaine_id, etage3_multi_unites, etage4_non_regression_10023,
              etage5_domaine_tuile_insensible_a_units, etage6_atteignabilite_multi_unites):
        try:
            rc |= f()
        except Exception as exc:                                    # noqa: BLE001
            print("[%s] EXCEPTION : %r" % (f.__name__, exc))
            rc |= 1
        print("")
    print("RC =", rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
