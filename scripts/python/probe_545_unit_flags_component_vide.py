"""#545 -- RAYON DE SOUFFLE de « un `UnitFlagsComponent` VIDE au lieu d'ABSENT ».

LE FAIT NATIF. `IdunBattle.Entities.Components.UnitFlagsComponent$$.ctor` construit un
`OrderedSet` **VIDE** et `IdunBattle.Entities.Factories.UnitFactory` le monte sur **CHAQUE** unite.
`IdunBattle.Entities.Behaviours.AddFlagBehaviour$$Execute` (et son jumeau `RemoveFlag`) resout le
composant sans garde et **LEVE** s'il est absent -- il ne l'ignore pas. Natif, « unite sans
`UnitFlagsComponent` » n'existe donc pas.

CE QUE LE PORT FAISAIT. `engine/runner/snapshot.py::_load_unit_flags` ne materialisait le composant
que si la ligne du snapshot portait une liste **NON VIDE** (`or not flags: continue`). Toute unite
sans aucun flag n'en avait donc pas, et chaque site qui fait `if fc is None: return` avant de POSER
un flag devenait un **no-op silencieux** (mesure #498-r4-r1 : natif `unitFlags = [1, 2, 3, 4, 25]`
apres le cast de `1152`, port RIEN).

CE PROBE MESURE LE RAYON **AVANT** DE CONCLURE, en trois etapes :

  1. RECENSEMENT AST de tous les sites `get_component(UnitFlagsComponent)` d'`engine/**`, classes
     par ce que le site fait du cas `None` :
       * `CREE`         -- il cree le composant absent  -> un composant VIDE ne change RIEN ;
       * `NEUTRE`       -- il ecrit `fl is not None and fl.has(X)` / `fl is None or not fl.has(X)`
                           -> indiscernable d'un `OrderedSet` vide ;
       * `DISTINGUANT`  -- une branche `if <nom> is None:` qui ne cree pas -> le comportement
                           CHANGE. C'est la seule classe qui compte, et le probe l'IMPRIME.
     Le classement est DERIVE de l'arbre (aucune liste ecrite a la main) : un site inconnu sort en
     `DISTINGUANT`, jamais en `NEUTRE` -- le defaut est du cote qui alerte.

  2. CONTREFACTUEL **EXECUTABLE** sur les lecteurs a signature reconnue : chaque fonction est
     appelee deux fois sur le MEME etat -- entite SANS composant, puis avec un composant VIDE -- et
     les deux retours sont compares. Un ecart ici est une preuve, pas une lecture. Les fonctions
     dont la signature n'est pas reconnue sont COMPTEES et NOMMEES (un balayage qui n'appelle pas
     ne peut pas rendre zero sur ce qu'il ne visite pas).

  3. TRI-ETAT de `_load_unit_flags` sur les QUATRE regimes de la ligne de snapshot : champ ABSENT,
     champ `null`, liste VIDE, liste NON VIDE. Les deux premiers = canal non mesure -> on ne touche
     a rien ; les deux derniers = mesure -> composant materialise.

ASCII only (console cp1252). Usage :

    python probe_545_unit_flags_component_vide.py [--verbeux]
"""
from __future__ import annotations

import argparse
import ast
import inspect
import os
import sys

_ICI = os.path.dirname(os.path.abspath(__file__))
if _ICI not in sys.path:
    sys.path.insert(0, _ICI)

RACINE_ENGINE = os.path.join(_ICI, "engine")


# ----------------------------------------------------------------- 1. RECENSEMENT AST
class _Site:
    __slots__ = ("fichier", "ligne", "fonction", "nom", "classe", "detail")

    def __init__(self, fichier, ligne, fonction, nom, classe, detail):
        self.fichier, self.ligne, self.fonction = fichier, ligne, fonction
        self.nom, self.classe, self.detail = nom, classe, detail

    def __repr__(self):
        return "%s:%d %s(%s) -> %s" % (self.fichier, self.ligne, self.fonction, self.nom,
                                       self.classe)


def _est_get_component_flags(node) -> bool:
    """`<x>.get_component(UnitFlagsComponent)` -- l'appel qu'on recense."""
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get_component"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "UnitFlagsComponent")


def _cree_le_composant(node) -> bool:
    """Le sous-arbre contient-il une CREATION du composant ?

    DEUX ecritures existent dans l'arbre et il faut les DEUX -- n'en voir qu'une classe un
    createur en `DISTINGUANT` (mesure : `operations/summon_ai.py::_flags`) :
      (a) `add_component(UnitFlagsComponent())`             -- l'appel EN ARGUMENT ;
      (b) `fl = UnitFlagsComponent()` puis `add_component(fl)` -- passage par une variable."""
    noms_construits = set()
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Assign) and len(sub.targets) == 1
                and isinstance(sub.targets[0], ast.Name)
                and isinstance(sub.value, ast.Call) and isinstance(sub.value.func, ast.Name)
                and sub.value.func.id == "UnitFlagsComponent"):
            noms_construits.add(sub.targets[0].id)
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "add_component"):
            for a in sub.args:
                if (isinstance(a, ast.Call) and isinstance(a.func, ast.Name)
                        and a.func.id == "UnitFlagsComponent"):
                    return True                                        # (a)
                if isinstance(a, ast.Name) and a.id in noms_construits:
                    return True                                        # (b)
    return False


def _test_is_none_de(test, nom: str) -> bool:
    """`<nom> is None` -- la forme qui SEPARE composant absent et composant vide."""
    return (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
            and test.left.id == nom and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Is)
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value is None)


def _classe_site(fn_node, nom_lie: str):
    """Classe UN site par ce que sa fonction englobante fait du cas `None`.

    DEFAUT PRUDENT : une forme non reconnue sort `DISTINGUANT`, jamais `NEUTRE`."""
    if nom_lie is None:
        # `... .get_component(UnitFlagsComponent) is None` sans liaison -- le site TESTE
        # directement ; le corps du `if` decide.
        return "CREE" if _cree_le_composant(fn_node) else "DISTINGUANT", "test direct"
    branches_none = []
    for sub in ast.walk(fn_node):
        if isinstance(sub, ast.If) and _test_is_none_de(sub.test, nom_lie):
            branches_none.append(sub)
    if not branches_none:
        # Aucune branche `is None` -> le site ne peut pas distinguer les deux etats, SAUF s'il
        # dereference le nom sans garde (`fl.has(...)` nu), ce qui LEVERAIT sur `None`. On verifie.
        for sub in ast.walk(fn_node):
            if (isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name)
                    and sub.value.id == nom_lie and sub.attr in ("has", "add", "remove",
                                                                 "turn_ended", "flags")):
                # dereference : garde par un `and`/`or` en amont ? On le suppose NEUTRE seulement
                # si la forme `<nom> is not None and`/`<nom> is None or` est presente.
                src = ast.dump(fn_node)
                garde = ("IsNot()" in src or "Is()" in src)
                return ("NEUTRE" if garde else "DISTINGUANT"), "deref sans branche is-None"
        return "NEUTRE", "jamais deref"
    for br in branches_none:
        if _cree_le_composant(br):
            return "CREE", "branche is-None qui cree"
    return "DISTINGUANT", "branche is-None qui NE cree PAS"


def recenser(racine: str = RACINE_ENGINE):
    sites = []
    for base, _dirs, fichiers in os.walk(racine):
        for f in sorted(fichiers):
            if not f.endswith(".py"):
                continue
            chemin = os.path.join(base, f)
            rel = os.path.relpath(chemin, _ICI).replace("\\", "/")
            try:
                with open(chemin, "r", encoding="utf-8") as fh:
                    arbre = ast.parse(fh.read(), filename=chemin)
            except (SyntaxError, UnicodeDecodeError):
                continue
            # parent map pour retrouver la fonction englobante et la liaison
            parents = {}
            for n in ast.walk(arbre):
                for c in ast.iter_child_nodes(n):
                    parents[c] = n
            for n in ast.walk(arbre):
                if not _est_get_component_flags(n):
                    continue
                # fonction englobante
                fn, cur = None, n
                while cur in parents:
                    cur = parents[cur]
                    if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        fn = cur
                        break
                if fn is None:
                    fn = arbre
                # nom lie : `fl = <x>.get_component(...)` ou `fl = ... if ... else None`
                nom_lie, cur = None, n
                while cur in parents:
                    p = parents[cur]
                    if isinstance(p, ast.Assign) and len(p.targets) == 1 \
                            and isinstance(p.targets[0], ast.Name):
                        nom_lie = p.targets[0].id
                        break
                    if isinstance(p, (ast.IfExp, ast.BoolOp, ast.Call, ast.Compare)):
                        cur = p
                        continue
                    break
                classe, detail = _classe_site(fn, nom_lie)
                sites.append(_Site(rel, n.lineno, getattr(fn, "name", "<module>"),
                                   nom_lie, classe, detail))
    return sites


# ----------------------------------------------------------- 2. CONTREFACTUEL EXECUTABLE
def _etat_minimal():
    """Un etat runner MINIMAL portant UNE entite d'unite, SANS `UnitFlagsComponent`.

    Il porte un `ActiveAbilitiesComponent` VIDE : sans lui, `turnflow.has_action_available` sort par
    « canal `allAbilities` non demande -> None » AVANT d'avoir lu le moindre flag, et le
    contrefactuel ne peut alors RIEN montrer sur ce site-la (les deux bras rendent `None`). Le
    composant vide est un etat REEL (une unite dont on a demande les abilities et qui n'en a
    aucune d'utilisable), pas un artefact : c'est ce qui rend le gate PUR-FLAG observable."""
    from engine.runner.state import State
    from engine.runner.components import (UnitComponent, OwnerComponent, PositionComponent,
                                          HealthComponent, ActiveAbilitiesComponent)
    from engine.entities.pathfinding.board import Board
    tiles, n = [], 1
    for col in range(3):
        for row in range(3):
            tiles.append({"id": n, "col": col, "row": row, "walkable": True, "elevation": 0})
            n += 1
    st = State()
    st.board = Board(tiles, adjacency="evenq")
    e = st.add_entity(1)
    e.add_component(UnitComponent(visual_id="orksNob", alive=True))
    e.add_component(OwnerComponent(team=1, player=1))
    e.add_component(PositionComponent(col=1, row=1))
    e.add_component(HealthComponent(hp=1000, hp_max=1000))
    e.add_component(ActiveAbilitiesComponent(abilities=[]))
    return st, e


_RE_ADRESSE = __import__("re").compile(r" at 0x[0-9A-Fa-f]+")


def _canon(valeur) -> str:
    """L'empreinte doit hacher la VALEUR, pas la REPRESENTATION (doctrine #270-r1-r1).

    Ici la representation porte des ADRESSES MEMOIRE (`<function ... at 0x...>`, `<Board object at
    0x...>`) qui differ ent a chaque construction d'etat : les comparer rend des divergences
    FAUSSES. Mesure : `entities_from_state` en rendait une, uniquement par ce canal."""
    return _RE_ADRESSE.sub(" at 0xXX", repr(valeur))


def _appel(fn, st, ent):
    """Appelle `fn` avec la signature RECONNUE. Rend `(appelee, valeur_ou_exception)`."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False, "signature illisible"
    noms = [p.name for p in sig.parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    obligatoires = [p for p in sig.parameters.values()
                    if p.default is p.empty and p.kind in (p.POSITIONAL_ONLY,
                                                           p.POSITIONAL_OR_KEYWORD)]
    try:
        if len(obligatoires) == 1 and noms[:1] in (["entity"], ["e"], ["unit"], ["ent"]):
            return True, fn(ent)
        if len(obligatoires) == 2 and noms[0] == "state":
            return True, fn(st, 1)
        if len(obligatoires) == 1 and noms[:1] == ["state"]:
            return True, fn(st)
    except Exception as exc:                                  # noqa: BLE001 -- on MESURE la levee
        return True, "LEVE:%s" % type(exc).__name__
    return False, "signature non reconnue (%s)" % ",".join(noms)


def contrefactuel(sites, verbeux=False):
    """Pour chaque module recense, rejoue ses fonctions module-level SANS puis AVEC un composant
    VIDE, et compare. Rend `(ecarts, appelees, non_appelees)`."""
    import importlib
    from engine.runner.components import UnitFlagsComponent
    modules = sorted({s.fichier for s in sites})
    ecarts, appelees, non_appelees = [], 0, []
    for rel in modules:
        mod_nom = rel[:-3].replace("/", ".")
        try:
            mod = importlib.import_module(mod_nom)
        except Exception as exc:                              # noqa: BLE001
            non_appelees.append((rel, "<module>", "IMPORT %s" % type(exc).__name__))
            continue
        for nom, fn in sorted(vars(mod).items()):
            if not inspect.isfunction(fn) or fn.__module__ != mod_nom:
                continue
            try:
                src = inspect.getsource(fn)
            except (OSError, TypeError):
                continue
            if "get_component(UnitFlagsComponent)" not in src:
                continue
            st_a, ent_a = _etat_minimal()
            ok_a, val_a = _appel(fn, st_a, ent_a)
            st_b, ent_b = _etat_minimal()
            ent_b.add_component(UnitFlagsComponent())          # le composant VIDE
            ok_b, val_b = _appel(fn, st_b, ent_b)
            if not (ok_a and ok_b):
                non_appelees.append((rel, nom, val_a if not ok_a else val_b))
                continue
            appelees += 1
            ca, cb = _canon(val_a), _canon(val_b)
            if ca != cb:
                ecarts.append((rel, nom, ca[:160], cb[:160]))
            elif verbeux:
                print("    [=] %s.%s -> %s" % (rel, nom, ca[:100]))
    return ecarts, appelees, non_appelees


# ------------------------------------------------------------------- 3. TRI-ETAT DU FOYER
def tri_etat():
    """Les QUATRE regimes de la ligne de snapshot, joues sur le VRAI `_load_unit_flags`."""
    from engine.runner import snapshot as SNAP
    from engine.runner.components import UnitFlagsComponent
    resultats = {}
    for nom, ligne in (("champ ABSENT", {"entityId": 1}),
                       ("champ null", {"entityId": 1, "unitFlags": None}),
                       ("liste VIDE", {"entityId": 1, "unitFlags": []}),
                       ("liste PLEINE", {"entityId": 1, "unitFlags": [0, 25]})):
        st, ent = _etat_minimal()
        SNAP._load_unit_flags(st, {"units": [ligne]})
        fl = ent.get_component(UnitFlagsComponent)
        resultats[nom] = {
            "composant": fl is not None,
            "flags": sorted(fl.flags) if fl is not None else None,
            "seed": dict(st.unit_flags_seed or {}),
        }
    return resultats


# ------------------------------------------------------------------------------ MAIN
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbeux", action="store_true")
    args = ap.parse_args()

    print("=" * 92)
    print("#545 -- ETAPE 1 : recensement AST des sites `get_component(UnitFlagsComponent)`")
    print("=" * 92)
    sites = recenser()
    par_classe = {}
    for s in sites:
        par_classe.setdefault(s.classe, []).append(s)
    total = len(sites)
    for classe in ("CREE", "NEUTRE", "DISTINGUANT"):
        lot = par_classe.get(classe, [])
        print("  %-12s : %3d" % (classe, len(lot)))
    print("  %-12s : %3d  (somme = partition exhaustive)" % ("TOTAL", total))
    inconnues = set(par_classe) - {"CREE", "NEUTRE", "DISTINGUANT"}
    if inconnues:
        print("  !! classes inattendues : %s" % sorted(inconnues))
    print()
    print("  LES SITES QUI DISTINGUENT (composant VIDE != composant ABSENT) :")
    dist = par_classe.get("DISTINGUANT", [])
    if not dist:
        print("    (aucun)")
    for s in dist:
        print("    %s:%d  %s  [%s]" % (s.fichier, s.ligne, s.fonction, s.detail))
    if args.verbeux:
        print()
        print("  DETAIL des NEUTRES :")
        for s in par_classe.get("NEUTRE", []):
            print("    %s:%d  %s" % (s.fichier, s.ligne, s.fonction))

    print()
    print("=" * 92)
    print("#545 -- ETAPE 2 : contrefactuel EXECUTABLE (sans composant / composant VIDE)")
    print("=" * 92)
    ecarts, appelees, non_appelees = contrefactuel(sites, verbeux=args.verbeux)
    print("  fonctions APPELEES des deux cotes : %d" % appelees)
    print("  fonctions NON appelees (signature non reconnue / import) : %d" % len(non_appelees))
    for rel, nom, pourquoi in non_appelees:
        print("    - %s.%s : %s" % (rel, nom, pourquoi))
    print("  ECARTS mesures : %d" % len(ecarts))
    for rel, nom, a, b in ecarts:
        print("    ! %s.%s : sans=%s  vide=%s" % (rel, nom, a, b))

    print()
    print("=" * 92)
    print("#545 -- ETAPE 3 : tri-etat de `_load_unit_flags`")
    print("=" * 92)
    tri = tri_etat()
    for nom, r in tri.items():
        print("  %-14s : composant=%-5s flags=%-12s vides=%s units=%s"
              % (nom, r["composant"], r["flags"], r["seed"].get("vides"),
                 r["seed"].get("units")))

    ok = True
    # Le contrat que cette tranche ETABLIT (et que le test offline garde) :
    if tri["champ ABSENT"]["composant"] or tri["champ null"]["composant"]:
        print("\n  !! ECHEC : une ligne NON MESUREE a materialise un composant (tri-etat casse)")
        ok = False
    if not tri["liste VIDE"]["composant"] or tri["liste VIDE"]["flags"] != []:
        print("\n  !! ECHEC : une ligne MESUREE a liste VIDE n'a PAS materialise de composant vide")
        ok = False
    if tri["liste PLEINE"]["flags"] != [0, 25]:
        print("\n  !! ECHEC : une ligne MESUREE pleine n'a pas seede ses flags")
        ok = False
    print("\nVERDICT : %s" % ("OK" if ok else "ECHEC"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
