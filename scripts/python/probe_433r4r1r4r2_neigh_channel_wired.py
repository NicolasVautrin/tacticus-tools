"""#433-r4-r1-r4-r2 -- CLIQUET : le substrat de VOISINAGE NATIF est branche partout ou le port
declare le mirrorer.

CE QU'IL EST SEUL A VOIR
------------------------
`battle_query.is_adjacent` porte DEUX etages du natif
(`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`) : l'ENUMERATION
de la liste STOCKEE (`neigh_by_pos`) puis la PORTE d'elevation (`elev_by_pos`). Les deux sont des
parametres OPTIONNELS, donc un call-site qui en oublie un degrade **en silence** -- ni erreur, ni
crash, juste un predicat plus PERMISSIF que le natif. C'est exactement la signature de degradation
de `TARGETING_OPTIONS` (cf. `CLAUDE.md`), et le seul gisement que notre propre cadence de portage
alimente : chaque nouveau playbook qui compte des voisins peut le rouvrir.

MESURE qui justifie le cliquet (`probe_433r4r1r4r2_is_adjacent_substrat_live.py`) : la couronne hex
sur-atteint la liste stockee de **4** aretes dirigees sur `C1_74` et **38** sur `C3_14`, pour **0**
arete dans l'autre sens -- un ecart strictement PERMISSIF.

DEUX ETAPES, et la seconde existe parce que la premiere ne peut pas voir son gisement
-------------------------------------------------------------------------------------
* **ETAPE 1 -- l'invariant de COUPLE sur les call-sites.** « Un call-site qui a su fournir
  l'elevation a forcement un porteur de contexte sous la main, donc il peut fournir le voisinage. »
  Un call-site qui ne passe NI l'un NI l'autre est hors gisement (arbre purement numerique, test
  unitaire) et n'est pas compte.

  ⚠ La detection RESOUT l'import, elle ne compare pas des noms (#433-r4-r1-r4-r2-r1). Un
  `bq.is_adjacent(...)` etait vu, mais pas un appel en nom NU ni sous ALIAS -- or la face PREDICTION
  n'importe QUE sous alias (`from ..battle_query import is_charging as bq_is_charging`), et les
  foyers de `battle_query.py` s'appellent entre eux en nom nu. Comparer les seuls noms produirait
  l'erreur SYMETRIQUE : `engine/services/movement_query.py` definit son propre `is_adjacent(board,
  a, b)` et `engine/services/battle_query.py` son propre `are_entities_adjacent(a, b, board)` --
  homonymes dont le 3e parametre n'est PAS `elev_by_pos`. On n'accepte donc un nom que s'il resout
  vers `engine.battle_query` (import resolu, `level` relatif compris) ou s'il est defini dans CE
  fichier-la.

* **ETAPE 2 -- pas de GEOMETRIE NUE dans un mirror declare du substrat stocke**
  (#433-r4-r1-r4-r2-r1). L'etape 1 est structurellement AVEUGLE au vice qui a rouvert ce residu :
  `battle_query.newly_adjacent_ids` et `runner.components.update_charging` mirroraient
  `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` -> `GetAdjacentUnits` ->
  `IterateAdjacentTiles` avec un `hexgeo.distance == 1` **NU** -- donc sans elevation, donc hors
  gisement de l'invariant de couple, PAR CONSTRUCTION. Mesure du 2026-08-04 : 2 foyers, 0 vus par
  l'etape 1.

  Le critere est DERIVE du contenu, jamais une liste de noms (#440), et il tient en trois termes
  conjoints : la fonction CITE un natif dont le substrat d'enumeration est la liste stockee ; son
  corps COMPARE une distance hexagonale a 1 (la geometrie nue) ; et elle n'a AUCUN acces au canal
  (ni parametre, ni derivation depuis un board). Les trois ensemble sont exactement le vice ; deux
  d'entre eux ne le sont pas -- `is_adjacent` porte les termes 1 et 2 et c'est son repli documente,
  le terme 3 l'en sort. Le module qui DEFINIT le foyer du canal est exclu par la meme derivation
  (on le localise en cherchant ou `adjacent_neigh_by_pos` est `def`-ini) : la source du canal ne
  peut pas le recevoir en entree.

VERDICT : 0 = vert. Non nul = des mirrors non branches (listes). 99 = INDISPONIBLE (#471).
ASCII only.
"""
from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent

# ETAPE 1 -- nom -> index du parametre ELEVATION dans la signature positionnelle de
# `engine.battle_query`. Seuls comptent les appels qui RESOLVENT vers ce module.
CIBLES = {"is_adjacent": 2, "are_entities_adjacent": 2, "count_adjacent": 2,
          "count_adjacent_matching": 3, "is_charging": 4, "newly_adjacent_ids": 3}
MODULES = ("bq", "battle_query", "_bq")     # porteurs de module pour la forme `bq.is_adjacent(...)`
FOYER = "engine.battle_query"

# ETAPE 2 -- les natifs dont le substrat d'ENUMERATION est la liste stockee du
# `ConnectivityComponent` (`+0x10`). Citer l'un d'eux, c'est declarer mirrorer ce substrat.
# Echappement `u003C`/`u003E` conserve tel quel (convention `CLAUDE.md`).
NATIFS_LISTE_STOCKEE = ("IterateAdjacentTiles", "GetAdjacentUnits", "GetAdjacentTiles",
                        "GetAdjacentEnemies", "GetAdjacentFriends", "AreTilesAdjacent",
                        "IsNeighbour", "UpdateCharging")
# Formes d'ACCES au canal reconnues : parametre, ou derivation nommee depuis un board.
ACCES_CANAL = ("neigh_by_pos", "neigh_map", "adjacent_neigh_by_pos", "neighbours_native",
               "neighbours_connectivity", "connectivity_neighbours")
FOYER_CANAL = "adjacent_neigh_by_pos"       # sa DEFINITION localise le module a exclure


def _fichiers(sous_arbre: str) -> list[pathlib.Path] | None:
    """Les sources versionnees de `sous_arbre`, DANS CE CHECKOUT (#434).

    `git ls-files` borne le balayage a l'arbre courant : un `rglob` depuis la racine lirait le
    code en cours des autres agents sous `.claude/worktrees/` et leur rouge serait impute ici.
    `None` = git n'a pas repondu -> INDISPONIBLE (#471), jamais un zero silencieux."""
    try:
        r = subprocess.run(["git", "ls-files", sous_arbre], cwd=str(ROOT),
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        print("INDISPONIBLE: git ls-files injouable (%s)" % type(e).__name__)
        return None
    if r.returncode != 0:
        print("INDISPONIBLE: git ls-files rc=%d" % r.returncode)
        return None
    return [ROOT / ln.strip() for ln in r.stdout.splitlines()
            if ln.strip().endswith(".py")]


def _paquet(p: pathlib.Path) -> str:
    """Le paquet Python du fichier, tel qu'un import ABSOLU le nommerait (`engine.playbook...`).

    La racine d'import est `scripts/python` (le CWD impose a tous les probes et a pytest)."""
    rel = p.relative_to(ROOT / "scripts" / "python")
    return ".".join(rel.parts[:-1])


def _module_importe(p: pathlib.Path, node: ast.ImportFrom) -> str:
    """Le module ABSOLU que designe un `from ... import`, `level` relatif RESOLU.

    C'est ce qui distingue `from ..battle_query import ...` (le foyer) de
    `from .battle_query import ...` ecrit DANS `engine/services/` (un homonyme)."""
    base = _paquet(p)
    if not node.level:
        return node.module or ""
    parts = base.split(".") if base else []
    montee = node.level - 1
    if montee:
        parts = parts[:-montee] if montee <= len(parts) else []
    return ".".join(parts + ([node.module] if node.module else []))


def _noms_du_foyer(p: pathlib.Path, tree) -> dict:
    """{nom tel qu'il apparait dans CE fichier: nom reel dans `engine.battle_query`}.

    Deux sources, et deux seulement : les imports qui RESOLVENT vers le foyer (alias compris), et
    -- si le fichier EST le foyer -- les definitions locales."""
    out = {}
    if _paquet(p) + "." + p.stem == FOYER:
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in CIBLES:
                out[node.name] = node.name
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and _module_importe(p, node) == FOYER:
            for a in node.names:
                if a.name in CIBLES:
                    out[a.asname or a.name] = a.name
    return out


def etape1(arbres) -> tuple[list, int]:
    """Rend `(call-sites a moitie branches, total des call-sites gates)`."""
    manquants, total = [], 0
    for p, tree in arbres.items():
        locaux = _noms_du_foyer(p, tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if isinstance(f, ast.Attribute):
                # `bq.is_adjacent(...)` : porteur de module connu, sinon un homonyme de methode
                # (`self.is_adjacent`) entrerait au gisement a tort.
                if f.attr not in CIBLES or getattr(f.value, "id", None) not in MODULES:
                    continue
                reel = f.attr
            elif isinstance(f, ast.Name):
                reel = locaux.get(f.id)      # nom NU / alias, RESOLU vers le foyer
                if reel is None:
                    continue
            else:
                continue
            idx = CIBLES[reel]
            kw = {k.arg for k in node.keywords if k.arg}
            a_elev = len(node.args) > idx or "elev_by_pos" in kw
            a_neigh = len(node.args) > idx + 1 or "neigh_by_pos" in kw
            if not a_elev:
                continue                     # hors gisement : aucun des deux canaux
            total += 1
            if not a_neigh:
                manquants.append((p.relative_to(ROOT).as_posix(), node.lineno, reel))
    return manquants, total


def _compare_distance_a_un(fn) -> bool:
    """Le corps compare-t-il une distance hexagonale a 1 ? (`distance(...) == 1`, `!= 1`, `<= 1`)

    C'est la forme EXACTE de la geometrie nue : une adjacence decidee sur la couronne hex au lieu
    de la liste stockee. `<= 2` (un disque) et `== 2` (un ring-2) n'en sont pas -- ils mirrorent
    `IterateSurroundingTiles`, qui EST geometrique."""
    for node in ast.walk(fn):
        if not isinstance(node, ast.Compare):
            continue
        gauche = node.left
        appel = (isinstance(gauche, ast.Call)
                 and (getattr(gauche.func, "attr", None) == "distance"
                      or getattr(gauche.func, "id", "").endswith("distance")))
        if not appel:
            continue
        for op, cmp in zip(node.ops, node.comparators):
            if isinstance(op, (ast.Eq, ast.NotEq, ast.LtE)) and \
                    isinstance(cmp, ast.Constant) and cmp.value == 1:
                return True
    return False


def etape2(arbres) -> tuple[list, int]:
    """Rend `(mirrors declares qui font de la geometrie NUE sans acces au canal, total examine)`.

    Le module qui DEFINIT `adjacent_neigh_by_pos` est exclu par derivation : il EST la source du
    canal, il ne peut pas le recevoir."""
    exclus = {p for p, tree in arbres.items()
              if any(isinstance(n, ast.FunctionDef) and n.name == FOYER_CANAL
                     for n in ast.walk(tree))}
    manquants, total = [], 0
    for p, tree in arbres.items():
        if p in exclus:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            doc = ast.get_docstring(node) or ""
            if not any(nat in doc for nat in NATIFS_LISTE_STOCKEE):
                continue
            if not _compare_distance_a_un(node):
                continue                     # pas de geometrie nue -> rien a garder ici
            total += 1
            # ⚠ Le critere porte sur l'USAGE, pas sur la DISPONIBILITE. Contre-epreuve du
            # 2026-08-04 : coter la SIGNATURE laissait passer la mutation qui remettait
            # `newly_adjacent_ids` en geometrie nue -- ses parametres `elev_by_pos`/`neigh_by_pos`
            # restaient declares, donc le cliquet la voyait « branchee ». Un parametre non lu ne
            # branche rien. En AST un parametre n'apparait comme `ast.Name` QUE s'il est utilise :
            # ne regarder que le corps rend le critere exact.
            corps = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            corps |= {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
            if not corps & set(ACCES_CANAL):
                manquants.append((p.relative_to(ROOT).as_posix(), node.lineno, node.name))
    return manquants, total


def main() -> int:
    fichiers = _fichiers("scripts/python/engine")
    if fichiers is None:
        return 99                            # INDISPONIBLE -- le harnais, pas le depot (#471)
    arbres = {}
    for p in fichiers:
        try:
            with open(p, encoding="utf-8", newline="") as fh:
                arbres[p] = ast.parse(fh.read())
        except (OSError, SyntaxError):
            continue
    m1, t1 = etape1(arbres)
    m2, t2 = etape2(arbres)
    print("== #433-r4-r1-r4-r2 -- substrat de voisinage natif")
    print("-- etape 1 : invariant de COUPLE sur les call-sites (imports RESOLUS)")
    print("   call-sites gates par l'elevation : %d" % t1)
    print("   sans le canal de voisinage       : %d (attendu 0)" % len(m1))
    for (rel, ln, name) in m1:
        print("      %s:%d  %s -- elevation fournie, voisinage MANQUANT" % (rel, ln, name))
    print("-- etape 2 : geometrie NUE dans un mirror declare du substrat stocke")
    print("   mirrors declares qui comparent une distance a 1 : %d" % t2)
    print("   dont SANS acces au canal                        : %d (attendu 0)" % len(m2))
    for (rel, ln, name) in m2:
        print("      %s:%d  %s -- mirror declare, geometrie NUE, canal INACCESSIBLE" % (rel, ln, name))
    if t1 == 0:
        # Un zero de TOTAL n'est pas un vert : le balayage n'a rien vu, donc il ne garde rien.
        print("ECART: etape 1 a un perimetre VIDE -- le cliquet ne garde rien (perimetre casse ?)")
        return 1
    n = len(m1) + len(m2)
    print("VERDICT: %s" % ("PASS" if not n else "FAIL (%d)" % n))
    return 0 if not n else 1


if __name__ == "__main__":
    raise SystemExit(main())
