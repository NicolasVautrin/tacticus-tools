"""#10023-r1 -- `Tiles(origin)` quand l'origine n'est PAS une unite occupante.

MESURE, pas inventaire : chaque etage porte le regime AVANT/APRES et sa CONTRE-EPREUVE. Le probe
doit ROUGIR sur le port d'avant (`_main_tile` = `_origin_tiles(origin)[0]`, une tuile brute) et
VERDIR sur le mirror (`_main_tiles` = `GetMainTile o SelectUnit`, par ENTITE).

RE relue VERBATIM sur `t6dpr4k06g` (ghidra-mcp), et c'est la chaine ENTIERE qui compte :

    // IdunBattleLogic.Entities.DSLSelectors$$SurroundingTiles, branche includeCenter == 0
    SurroundingTiles(origin, includeCenter: 1, ...) op_Subtraction Tiles(origin)

    // IdunBattleLogic.Entities.DSLSelectors$$Tiles
    Tiles(entities) = new UnitsMainTilesSelector(inner: entities, state)

    // IdunBattle.Entities.Selectors.UnitsMainTilesSelector$$Select
    foreach (entity in inner.<slot 3 = SelectAllUnits>(entities, selectionType: 0)) {
        tile = EntityExtensions$$GetMainTile(entity, state);
        if (tile != null) result.Add(tile);
    }

    // IdunBattle.DSL.TargetsSelector$$SelectAllUnits
    list = this.Select(entities);
    if (this.<IsUnitSelector>) return list;
    foreach (e in list)
        if (e != null && (u = SelectUnit(this, e, selectionType)) != null) result.Add(u);

    // IdunBattle.DSL.TargetsSelector$$SelectUnit (surcharge par ENTITE)
    if (IsUnitFoot(entity) || IsTile(entity)) entity = UnitExtensions$$GetUnit(entity, state);
    if (entity != null && IsUnit(entity) && MatchesUnitSelectionType(...)) return entity;
    return null;

    // IdunBattle.Entities.UnitExtensions$$GetUnit (surcharge ENTITE generique)
    if (entity == null) return null;
    if (entity is UnitEntity) return entity;
    if (entity is TileEntity) {
        content = entity+0x38;                       // TileContentComponent
        if (!content.IsFilled()) return null;        // <<< TUILE VIDE : rien n'est ajoute
        entity = state.GetEntity(content+0x10);      // le PIED, re-resolu en son unite
    }

    // IdunBattle.DSL.CombinedSelector$$SelectExclusion  (ce que `op_Subtraction` construit)
    foreach (e in leftResults) if (!rightResults.Contains(e)) result.Add(e);

DEUX consequences que le port d'avant ne portait pas, et une TROISIEME qui est la question posee :

  (a) origine = TUILE VIDE -> `GetUnit` rend null, `SelectAllUnits` SAUTE l'element, `Tiles` est
      VIDE : le natif ne retranche AUCUNE tuile. Le port retranchait la tuile.
  (b) l'appel SANS `board` (`engine/dsl/base.py::_within`) : `_origin_tiles` d'un `list[int]` sans
      board rend `[]`, donc l'exclusion etait silencieusement VIDE.
  (c) origine a N UNITES DISTINCTES -> `GetMainTile` est applique PAR ENTITE, donc N main tiles
      retranchees ; le port n'en retranchait qu'UNE (`ts[0]`).

Board SYNTHETIQUE et plat : c'est la resolution d'occupant qui est le sujet, pas le terrain.
ASCII only (cp1252).
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
    b = _board()
    #: Une unite ailleurs, pour que `units` ne soit pas vide (un `units` vide ferait passer
    #: l'etage par le chemin DEGRADE, pas par le mirror -- accord en regime degenere = 0 preuve).
    ailleurs = _unite(10001, [(0, 0)])
    ctx = _Ctx(b, [ailleurs])
    centre = (4, 4)
    tid = b.id_at(*centre)
    sel = A.SurroundingTiles(_Fixe([tid]), _Fixe(1), include_center=False)
    sortie = sel.select(ctx)
    attendu = {b.id_at(c, r) for (c, r) in hexgeo.disk(centre[0], centre[1], 1)}
    print("[E1] origine = tuile VIDE %s (id %d), rayon 1" % (str(centre), tid))
    print("     natif attendu (Tiles(origine) = VIDE, rien retranche) : %d tuiles" % len(attendu))
    print("     port                                                  : %d tuiles" % len(sortie))
    if set(sortie) != attendu:
        manquant = sorted(attendu - set(sortie))
        print("[E1] ECHEC : le port retranche %s -- le natif ne retranche rien sur une tuile VIDE"
              % (manquant,))
        return 1
    # CONTRE-EPREUVE : la MEME tuile, OCCUPEE -> la main tile de l'occupant DOIT sortir.
    occupant = _unite(10002, [centre])
    ctx2 = _Ctx(b, [ailleurs, occupant])
    sortie2 = sel.select(ctx2)
    if tid in sortie2:
        print("[E1] ECHEC (contre-epreuve) : tuile OCCUPEE, la main tile n'est PAS retranchee")
        return 1
    if set(sortie2) != attendu - {tid}:
        print("[E1] ECHEC (contre-epreuve) : ensemble inattendu %s" % (sorted(set(sortie2)),))
        return 1
    print("[E1] OK : vide -> rien retranche ; occupee -> la main tile de l'occupant retranchee.")
    return 0


# --------------------------------------------------------------------------------------------
# ETAGE 1bis -- ORIGINE = PIED SECONDAIRE : le natif retranche la MAIN TILE, pas le pied
# --------------------------------------------------------------------------------------------
def etage1bis_pied_secondaire() -> int:
    """`GetMainTile(GetUnit(pied))` = la tuile du PREMIER pied de l'unite, JAMAIS le pied donne.

    Le port d'avant rendait `_origin_tiles(origin)[0]` = le pied lui-meme : sur une origine qui
    designe un pied SECONDAIRE, il retranchait la mauvaise tuile -- il gardait la main tile que le
    natif coupe, et coupait un pied que le natif garde. DEUX tuiles d'ecart, pas une."""
    b = _board()
    main, second = (4, 4), (5, 4)
    mortarion = _unite(10003, [main, second])
    ctx = _Ctx(b, [mortarion])
    tid_second = b.id_at(*second)
    tid_main = b.id_at(*main)
    sel = A.SurroundingTiles(_Fixe([tid_second]), _Fixe(1), include_center=False)
    sortie = set(sel.select(ctx))
    attendu = {b.id_at(c, r) for (c, r) in hexgeo.disk(second[0], second[1], 1)} - {tid_main}
    print("[E1bis] origine = PIED SECONDAIRE %s ; main tile de l'occupant = %s"
          % (str(second), str(main)))
    print("        attendu %d tuiles (main tile RETRANCHEE, le pied GARDE)" % len(attendu))
    print("        port    %d tuiles" % len(sortie))
    if tid_main in sortie:
        print("[E1bis] ECHEC : la MAIN TILE n'est pas retranchee (le port a coupe le pied a la place)")
        return 1
    if tid_second not in sortie:
        print("[E1bis] ECHEC : le PIED SECONDAIRE est retranche -- le natif le garde")
        return 1
    if sortie != attendu:
        print("[E1bis] ECHEC : ensemble inattendu %s" % (sorted(sortie),))
        return 1
    print("[E1bis] OK : main tile retranchee, pied secondaire garde.")
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
    """`UnitsMainTilesSelector$$Select` boucle sur les entites rendues par `SelectAllUnits` et
    ajoute `GetMainTile(entity)` pour CHACUNE. Une origine a N unites distinctes retranche donc
    N main tiles ; `ts[0]` n'en retranchait qu'une."""
    b = _board()
    a_pos, c_pos = (4, 4), (4, 6)
    ua, uc = _unite(10006, [a_pos]), _unite(10007, [c_pos])
    ctx = _Ctx(b, [ua, uc])
    tid_a, tid_c = b.id_at(*a_pos), b.id_at(*c_pos)
    sel = A.SurroundingTiles(_Fixe([tid_a, tid_c]), _Fixe(1), include_center=False)
    sortie = set(sel.select(ctx))
    print("[E3] origine = DEUX unites distinctes (%s, %s)" % (str(a_pos), str(c_pos)))
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
def etage5_substrat_absent() -> int:
    """`units` FALSY = NON MESURE, et la degradation est NOMMEE : on garde la premiere tuile de
    l'origine -- le comportement d'avant, EXACT sur toute origine mono-hex occupee -- plutot qu'un
    `[]` fabrique depuis une non-mesure, qui desarmerait l'exclusion partout.

    Une bataille native a TOUJOURS des unites : `units` vide n'est pas un etat de jeu, c'est un
    contexte de test. Le rabattre sur « mesure, aucune unite » ferait varier tous les tests
    offline qui montent un `ctx` sans population."""
    b = _board()
    centre = (4, 4)
    for etiquette, u in (("None", None), ("[]  ", [])):
        got = B._main_tiles([b.id_at(*centre)], b, u)
        print("[E5] units=%s (NON MESURE) -> %s" % (etiquette, got))
        if got != [centre]:
            print("[E5] ECHEC : la degradation ne rend pas la tuile brute")
            return 1
    #: CONTRE-EPREUVE : des que `units` est MESURE et non vide, la tuile VIDE ne rend plus rien.
    peuple = B._main_tiles([b.id_at(*centre)], b, [_unite(10001, [(0, 0)])])
    print("[E5] units=[1 unite ailleurs] (MESURE) -> %s" % (peuple,))
    if peuple != []:
        print("[E5] ECHEC (contre-epreuve) : substrat present, la tuile VIDE devrait rendre []")
        return 1
    print("[E5] OK : non-mesure -> tuile brute ; mesure -> resolution d'occupant.")
    return 0


def main() -> int:
    rc = 0
    for f in (etage0_recensement, etage1_tuile_vide, etage1bis_pied_secondaire,
              etage2_within_domaine_id, etage3_multi_unites, etage4_non_regression_10023,
              etage5_substrat_absent):
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
