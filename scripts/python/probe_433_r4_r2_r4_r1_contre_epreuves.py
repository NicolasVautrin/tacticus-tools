"""probe #433-r4-r2-r4-r1 -- INVENTAIRE des contre-epreuves, et lesquelles supposent un canal EXCLUSIF.

POURQUOI. `#433-r4-r2-r4` a mesure qu'une contre-epreuve de la forme « je neutralise le canal X,
le port doit alors diverger » CESSE DE MORDRE des qu'un canal Y redondant apparait -- sans erreur,
sans que le code de la contre-epreuve change. Le test devient rouge pour une raison qui accuse le
PORT, et le rouge a survecu a trois merges.

La question de ce probe est l'INVERSE de celle du cliquet `probe_433r4r1r4r2_neigh_channel_wired`
(qui verifie que les call-sites de PRODUCTION lisent le canal) : **quels ORACLES supposent qu'un
canal est le SEUL a porter une exclusion ?**

CE QU'IL MESURE, en trois etages, tous DERIVES du source (aucun chiffre en dur) :

  * `--step inventaire` : toutes les MUTATIONS NEUTRALISANTES du depot, par AST -- un appel
    `replace(obj, champ=<neutre>)` ou `<neutre>` vaut `None`/`[]`/`{}`/`set()`/`False`/`0`/`""`.
    Ventile par OBJET mute (contexte de playbook, `TargetingOptions`, autre) et par PORTEUR
    (probe / test / engine).
  * `--step risque` : parmi ces mutations, celles qui neutralisent UN CANAL DE CONTEXTE. Pour
    chacune, on derive le(s) FOYER(s) d'`engine/` qui lisent ce canal, et on compte combien
    d'AUTRES canaux le meme foyer lit. Foyer a >= 2 canaux == REGIME A RISQUE : neutraliser un
    seul canal peut ne rien restituer.
  * `--step muettes` : pour chaque canal a risque, on JOUE le foyer sur un etat MINIMAL construit
    pour que la propriete soit portee par les deux canaux, et on regarde si neutraliser le canal
    seul change encore le verdict. Un foyer ou la neutralisation d'un canal ne change RIEN est
    exactement le regime qui a vide la contre-epreuve de `#433-r4-r2`.

Usage (ASCII only, depuis scripts/python) :
  python probe_433_r4_r2_r4_r1_contre_epreuves.py --step all
"""
from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "scripts" / "python"

# Valeurs qui NEUTRALISENT un canal : ce que le porteur ecrit pour dire « ce canal ne dit rien ».
_NEUTRES_CONST = (None, False, 0, "")
_NEUTRES_APPEL = {"set", "dict", "list", "frozenset", "tuple"}

# Canaux qui ne portent PAS le suffixe `_by_pos` : la VALEUR d'un canal, telle qu'un foyer d'aval la
# recoit apres le `.get(tile)` de son appelant. `tile_removed_by_walkability(rules, walkable,
# is_in_fog)` en est l'exemple LU -- deux volets d'`IdunBattle.Entities.TileExtensions$$IsWalkable`,
# deux canaux distincts du `boardGraph`, que le foyer recoit deja scalarises.
_CANAUX_SCALAIRES = ("walkable", "is_in_fog", "elevation", "neigh", "is_wall")


def _fichiers_versionnes() -> list[Path]:
    """Perimetre DERIVE de git (jamais un glob : un fichier non suivi n'est pas un livrable)."""
    out = subprocess.run(["git", "-C", str(RACINE), "ls-files", "scripts/python"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("git ls-files KO : %s" % out.stderr.strip())
    return [RACINE / l for l in out.stdout.splitlines() if l.endswith(".py")]


def _est_neutre(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and any(node.value is v or node.value == v
                                              for v in _NEUTRES_CONST):
        # `is` d'abord : `0 == False` en Python, on veut juste savoir que c'est neutre.
        return True
    if isinstance(node, (ast.List, ast.Dict, ast.Set)) and not getattr(node, "elts", None) \
            and not getattr(node, "keys", None):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in _NEUTRES_APPEL and not node.args and not node.keywords:
        return True
    return False


def _nom_appele(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        base = f.value.id if isinstance(f.value, ast.Name) else "?"
        return "%s.%s" % (base, f.attr)
    return "?"


def _cible(node: ast.Call) -> str:
    if not node.args:
        return "?"
    a = node.args[0]
    if isinstance(a, ast.Name):
        return a.id
    if isinstance(a, ast.Attribute):
        return "%s.%s" % (a.value.id if isinstance(a.value, ast.Name) else "?", a.attr)
    return "?"


def _porteur(rel: str) -> str:
    if "/tests/" in rel or Path(rel).name.startswith("test_"):
        return "test"
    if Path(rel).name.startswith("probe_"):
        return "probe"
    if "/engine/" in rel:
        return "engine"
    return "autre"


def inventaire(verbose=True) -> dict:
    """Etage 1 -- toutes les mutations NEUTRALISANTES du depot, par AST."""
    sites = []
    for p in _fichiers_versionnes():
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError:
            continue
        rel = p.relative_to(RACINE).as_posix()
        for n in ast.walk(arbre):
            if not isinstance(n, ast.Call) or not n.keywords:
                continue
            nom = _nom_appele(n)
            if not (nom.endswith("replace") or nom.endswith("_replace")):
                continue
            champs = sorted(k.arg for k in n.keywords if k.arg and _est_neutre(k.value))
            if not champs:
                continue
            sites.append({"fichier": rel, "ligne": n.lineno, "appel": nom,
                          "cible": _cible(n), "champs": champs, "porteur": _porteur(rel)})
    par_porteur, par_champ = {}, {}
    for s in sites:
        par_porteur[s["porteur"]] = par_porteur.get(s["porteur"], 0) + 1
        for c in s["champs"]:
            par_champ.setdefault(c, []).append(s)
    res = {"sites": sites, "n_sites": len(sites),
           "n_fichiers": len({s["fichier"] for s in sites}),
           "par_porteur": par_porteur,
           "par_champ": {c: len(v) for c, v in sorted(par_champ.items())}}
    if verbose:
        print("[inventaire] %d mutations neutralisantes sur %d fichiers"
              % (res["n_sites"], res["n_fichiers"]))
        print("[inventaire] par porteur : %r" % (res["par_porteur"],))
        print("[inventaire] par champ neutralise :")
        for c, k in sorted(res["par_champ"].items(), key=lambda kv: -kv[1]):
            print("[inventaire]   %-24s %d" % (c, k))
        for s in sorted(sites, key=lambda x: (x["fichier"], x["ligne"])):
            print("[inventaire]   %s:%d  %s(%s, %s)"
                  % (s["fichier"], s["ligne"], s["appel"], s["cible"], ",".join(s["champs"])))
    return res


def foyers_multicanaux(verbose=True) -> dict:
    """Etage 2 -- les fonctions d'`engine/` qui acceptent PLUSIEURS canaux.

    Un canal = un parametre dont le nom suit le vocabulaire du port (`*_by_pos`). Un foyer
    MONO-canal ne peut pas heberger le vice : couper son unique canal restitue forcement quelque
    chose (ou rien, mais pas par redondance). Le gisement est donc exactement les foyers a >= 2."""
    foyers = []
    for p in _fichiers_versionnes():
        rel = p.relative_to(RACINE).as_posix()
        if "/engine/" not in rel:
            continue
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError:
            continue
        for n in ast.walk(arbre):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = n.args
            noms = [a.arg for a in (list(args.posonlyargs) + list(args.args)
                                    + list(args.kwonlyargs))]
            canaux = [x for x in noms if x.endswith("_by_pos")]
            if len(canaux) >= 2:
                foyers.append({"fichier": rel, "ligne": n.lineno, "fonction": n.name,
                               "canaux": canaux})
    res = {"foyers": foyers, "n": len(foyers),
           "canaux": sorted({c for f in foyers for c in f["canaux"]})}
    if verbose:
        print("[foyers] %d fonctions d'engine/ acceptent >= 2 canaux `*_by_pos`" % res["n"])
        for f in foyers:
            print("[foyers]   %s:%d  %s(%s)"
                  % (f["fichier"], f["ligne"], f["fonction"], ", ".join(f["canaux"])))
    return res


def _teinte(fn, canal: str) -> set:
    """Les noms qui portent une valeur de `canal` dans `fn`, par point fixe.

    Meme forme que la teinte du cliquet `probe_433r4r1r4r2_neigh_channel_wired` : un test ecrit sur
    `neigh` (derive de `neigh_by_pos.get(t)`) parle bien du canal `neigh_by_pos`."""
    g = {canal}
    change = True
    while change:
        change = False
        for st in ast.walk(fn):
            val = getattr(st, "value", None)
            if val is None or not isinstance(st, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                continue
            noms = {n.id for n in ast.walk(val) if isinstance(n, ast.Name)}
            noms |= {n.attr for n in ast.walk(val) if isinstance(n, ast.Attribute)}
            if not (noms & g):
                continue
            cibles = [st.target] if hasattr(st, "target") else list(st.targets)
            for t in cibles:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name) and n.id not in g:
                        g.add(n.id)
                        change = True
    return g


def _sorties_gouvernees(fn, canal: str) -> set:
    """Les VALEURS d'exclusion que `canal` peut faire rendre a `fn`, seul.

    Un `return <constante>` est « gouverne par le canal » s'il est sous un `if` dont le test parle
    du canal (ou d'un nom qui en derive). C'est la trace syntaxique d'une PORTE : le canal, a lui
    seul, decide cette sortie."""
    g = _teinte(fn, canal)
    out = set()

    def _parle(n) -> bool:
        noms = {x.id for x in ast.walk(n) if isinstance(x, ast.Name)}
        noms |= {x.attr for x in ast.walk(n) if isinstance(x, ast.Attribute)}
        return bool(noms & g)

    def _visite(stmts, sous_canal: bool):
        for st in stmts or ():
            if isinstance(st, ast.If):
                s = sous_canal or _parle(st.test)
                _visite(st.body, s)
                _visite(st.orelse, s)
            elif isinstance(st, ast.Return):
                if sous_canal and isinstance(st.value, ast.Constant):
                    out.add(st.value.value)
            elif isinstance(st, (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith,
                                 ast.Try)):
                for champ in ("body", "orelse", "finalbody"):
                    _visite(getattr(st, champ, None), sous_canal)
                for h in getattr(st, "handlers", ()) or ():
                    _visite(h.body, sous_canal)
    _visite(fn.body, False)
    return out


def foyers_redondants(verbose=True) -> dict:
    """Etage 2b -- les foyers ou DEUX canaux peuvent porter la MEME exclusion.

    C'est le gisement REEL du residu, et il est bien plus petit que celui des foyers multi-canaux :
    deux canaux ne se recouvrent que s'ils gouvernent, CHACUN SEUL, la meme valeur de sortie."""
    couples = []
    for p in _fichiers_versionnes():
        rel = p.relative_to(RACINE).as_posix()
        if "/engine/" not in rel:
            continue
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError:
            continue
        for n in ast.walk(arbre):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            noms = [a.arg for a in (list(n.args.posonlyargs) + list(n.args.args)
                                    + list(n.args.kwonlyargs))]
            canaux = [x for x in noms if x.endswith("_by_pos") or x in _CANAUX_SCALAIRES]
            if len(canaux) < 2:
                continue
            par_canal = {c: _sorties_gouvernees(n, c) for c in canaux}
            for i, c1 in enumerate(canaux):
                for c2 in canaux[i + 1:]:
                    partage = par_canal[c1] & par_canal[c2]
                    if partage:
                        couples.append({"fichier": rel, "ligne": n.lineno, "fonction": n.name,
                                        "canaux": (c1, c2), "sorties": sorted(map(repr, partage))})
    res = {"couples": couples, "n": len(couples),
           "fonctions": sorted({(c["fichier"], c["fonction"]) for c in couples})}
    if verbose:
        print("[redondance] %d COUPLES de canaux gouvernent la meme sortie, sur %d fonctions"
              % (res["n"], len(res["fonctions"])))
        for c in couples:
            print("[redondance]   %s:%d  %s -- %s / %s -> sortie(s) %s"
                  % (c["fichier"], c["ligne"], c["fonction"], c["canaux"][0], c["canaux"][1],
                     ",".join(c["sorties"])))
    return res


def _callees(fn) -> dict:
    """{nom du callee: [ (ligne, premier argument tel qu'ecrit) ]} pour toute une fonction."""
    out = {}
    for n in ast.walk(fn):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        nom = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
        if nom is None:
            continue
        recepteur = None
        if isinstance(f, ast.Attribute):
            recepteur = getattr(f.value, "id", None)
        a0 = None
        if n.args and isinstance(n.args[0], ast.Name):
            a0 = n.args[0].id
        out.setdefault(nom, []).append((n.lineno, recepteur, a0))
    return out


def contre_epreuves(verbose=True) -> dict:
    """Etage 3 -- les contre-epreuves A DEUX BRAS, le motif EXACT de l'incident.

    Motif : `Y = replace(X, <canal>=<neutre>)`, puis le MEME callee appele une fois sur `X` et une
    fois sur `Y`. C'est la seule forme qui porte la promesse « le bras mute doit differer du bras
    non mute » -- une neutralisation SANS bras temoin ne compare rien et ne peut pas devenir muette
    (elle mesure un regime, elle ne discrimine pas).

    Le porteur `engine` est EXCLU : une neutralisation y est une degradation de PRODUCTION, gardee
    par `probe_433r4r1r4r2_neigh_channel_wired`, pas un oracle."""
    inv = inventaire(verbose=False)
    couples = []
    for p in _fichiers_versionnes():
        rel = p.relative_to(RACINE).as_posix()
        if _porteur(rel) not in ("probe", "test"):
            continue
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError:
            continue
        for fn in ast.walk(arbre):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # les noms mutes DANS cette fonction, et la source dont ils derivent
            mutes = {}
            for st in ast.walk(fn):
                if not isinstance(st, ast.Assign) or not isinstance(st.value, ast.Call):
                    continue
                appel = st.value
                nom = _nom_appele(appel)
                if not (nom.endswith("replace") or nom.endswith("_replace")):
                    continue
                champs = sorted(k.arg for k in appel.keywords if k.arg and _est_neutre(k.value))
                if not champs or not appel.args or not isinstance(appel.args[0], ast.Name):
                    continue
                for t in st.targets:
                    if isinstance(t, ast.Name):
                        mutes[t.id] = (appel.args[0].id, champs, st.lineno)
            if not mutes:
                continue
            appels = _callees(fn)
            for nom, sites in appels.items():
                args = {a0 for (_ln, _r, a0) in sites if a0 is not None}
                for y, (x, champs, ligne) in mutes.items():
                    if y in args and x in args:
                        couples.append({"fichier": rel, "fonction": fn.name, "ligne": ligne,
                                        "callee": nom, "source": x, "mute": y,
                                        "champs": champs})
    res = {"couples": couples, "n": len(couples),
           "n_fichiers": len({c["fichier"] for c in couples}),
           "champs": sorted({c for x in couples for c in x["champs"]}),
           "inventaire_total": inv["n_sites"]}
    if verbose:
        print("[contre-epreuve] %d contre-epreuves A DEUX BRAS, sur %d fichiers"
              " (inventaire brut : %d neutralisations)"
              % (res["n"], res["n_fichiers"], res["inventaire_total"]))
        for c in couples:
            print("[contre-epreuve]   %s:%d  %s -- %s(%s) contre %s(%s), canal(aux) %s"
                  % (c["fichier"], c["ligne"], c["fonction"], c["callee"], c["source"],
                     c["callee"], c["mute"], ",".join(c["champs"])))
    return res


def _signatures_des_foyers() -> dict:
    """{nom de foyer: [noms de parametres, dans l'ordre]}, LU par introspection.

    Indispensable pour resoudre un argument POSITIONNEL : le nom de la VARIABLE passee n'est pas
    celui du parametre. `is_adjacent(t, p, elev, neigh)` passe une variable nommee `neigh` au
    parametre `neigh_by_pos` -- confondre les deux fabriquait 8 faux positifs sur 9 (mesure du
    2026-08-05, premier jet de ce probe)."""
    import inspect
    from engine import battle_query as BQ
    from engine.services import ability_range as AR
    out = {}
    for mod in (BQ, AR):
        for nom, fn in vars(mod).items():
            if inspect.isfunction(fn):
                out[nom] = list(inspect.signature(fn).parameters)
    return out


def _canaux_de_lappel(n: ast.Call, params: list | None) -> set:
    """Les canaux qu'un appel PASSE EFFECTIVEMENT, resolus contre la signature du foyer.

    Un argument NEUTRE (`None`, `{}`) ne compte pas comme passe : c'est le bras MUTE."""
    def _est_canal(nom):
        return bool(nom) and (nom.endswith("_by_pos") or nom in _CANAUX_SCALAIRES)

    out = set()
    for k in n.keywords:
        if _est_canal(k.arg) and not _est_neutre(k.value):
            out.add(k.arg)
    if params:
        for i, a in enumerate(n.args):
            if i < len(params) and _est_canal(params[i]) and not _est_neutre(a):
                out.add(params[i])
    return out


def contre_epreuves_par_argument(verbose=True) -> dict:
    """Etage 3b -- la SECONDE forme : le meme callee appele deux fois DANS LA MEME FONCTION, avec
    des jeux de canaux DIFFERENTS.

    C'est la forme qu'a prise le second defaut de `#433-r4-r2-r4` (`utility_at` canaux COMPLETS
    contre canaux VIDES) et celle des quatre combinaisons de `--step canaux`. Elle ne passe par
    aucun `replace` : le bras mute est fabrique a l'appel.

    Le callee est FILTRE sur les foyers d'`engine/` mesures par `foyers_multicanaux` : sans lui, un
    `len(neigh)` ou un `sorted(team_by_pos)` entre au gisement et le chiffre ne veut plus rien
    dire (33 sites bruts, dont la moitie sont des builtins)."""
    connus = {f["fonction"] for f in foyers_multicanaux(verbose=False)["foyers"]}
    sigs = _signatures_des_foyers()
    sites = []
    for p in _fichiers_versionnes():
        rel = p.relative_to(RACINE).as_posix()
        if _porteur(rel) not in ("probe", "test"):
            continue
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError:
            continue
        for fn in ast.walk(arbre):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            par_callee = {}
            for n in ast.walk(fn):
                if not isinstance(n, ast.Call):
                    continue
                f = n.func
                nom = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
                if nom is None or nom not in connus:
                    continue
                par_callee.setdefault(nom, []).append(
                    (n.lineno, _canaux_de_lappel(n, sigs.get(nom))))
            for nom, appels in par_callee.items():
                jeux = {frozenset(c) for (_ln, c) in appels}
                if len(jeux) < 2:
                    continue
                riche = max(jeux, key=len)
                pauvres = [j for j in jeux if j != riche and j < riche]
                if not riche or not pauvres:
                    continue
                sites.append({"fichier": rel, "fonction": fn.name,
                              "ligne": min(ln for (ln, _c) in appels), "callee": nom,
                              "riche": sorted(riche),
                              "manquants": sorted(riche - max(pauvres, key=len))})
    res = {"sites": sites, "n": len(sites),
           "n_fichiers": len({s["fichier"] for s in sites})}
    if verbose:
        print("[par-argument] %d sites ou un MEME callee est appele avec des jeux de canaux"
              " DIFFERENTS, sur %d fichiers" % (res["n"], res["n_fichiers"]))
        for s in sites:
            print("[par-argument]   %s:%d  %s -- %s(%s) prive de %s"
                  % (s["fichier"], s["ligne"], s["fonction"], s["callee"],
                     ",".join(s["riche"]), ",".join(s["manquants"])))
    return res


class _Capteur:
    """Plugin pytest qui INTERCEPTE les foyers et enregistre leurs appels REELS.

    Le patch balaie `sys.modules` au lieu de patcher le seul module qui DEFINIT le foyer : les
    call-sites du port l'importent par `from ..battle_query import is_adjacent`, donc ils portent
    leur PROPRE reference et un patch au point de definition ne les verrait pas (meme piege que
    l'etape 1 du cliquet `probe_433r4r1r4r2_neigh_channel_wired`, qui RESOUT les imports)."""

    def __init__(self, cibles):
        self.cibles = cibles                 # {nom: fonction originale}
        self.appels = {}                     # {nom: [ (nodeid, args, kwargs) ]}
        self.nodeid = "<hors test>"
        self._pose = False

    def _wrapper(self, nom, orig):
        def _w(*a, **kw):
            self.appels.setdefault(nom, []).append((self.nodeid, a, dict(kw)))
            return orig(*a, **kw)
        _w.__wrapped_probe_433r4r2r4r1__ = True
        return _w

    def pytest_runtest_setup(self, item):
        self.nodeid = item.nodeid

    def _patcher(self):
        for nom, orig in self.cibles.items():
            w = self._wrapper(nom, orig)
            for mod in list(sys.modules.values()):
                if mod is None:
                    continue
                try:
                    if getattr(mod, nom, None) is orig:
                        setattr(mod, nom, w)
                except Exception:
                    continue

    def pytest_collection_finish(self, session):
        if not self._pose:
            self._pose = True
            self._patcher()


def muettes(fichiers, verbose=True, max_appels=4000) -> dict:
    """Etage 4 -- sur les etats REELLEMENT joues, neutraliser UN canal change-t-il quelque chose ?

    C'est la question du residu, posee de la seule facon qui ne se devine pas : on capte les appels
    que les tests font aux foyers, puis on REJOUE chacun avec un canal neutralise.

      * `redondant` -- il existe un canal dont la neutralisation SEULE ne change RIEN, alors que
        neutraliser TOUS les canaux change le verdict. C'est EXACTEMENT le regime qui a vide la
        contre-epreuve de `#433-r4-r2` : le canal n'est pas le seul porteur de l'exclusion.
      * `porteur unique` -- neutraliser ce canal seul change deja le verdict : une contre-epreuve
        batie dessus MORD.

    Le foyer est appele avec les MEMES arguments, `inspect.signature` liant les positionnels : on
    ne suppose aucun ordre de parametres."""
    import inspect
    import pytest

    from engine import battle_query as BQ
    from engine.services import ability_range as AR

    cibles = {}
    for mod in (BQ, AR):
        for nom, fn in vars(mod).items():
            if not inspect.isfunction(fn):
                continue
            sig = inspect.signature(fn)
            canaux = [p for p in sig.parameters
                      if p.endswith("_by_pos") or p in _CANAUX_SCALAIRES]
            if len(canaux) >= 2:
                cibles[nom] = fn
    cap = _Capteur(cibles)
    code = pytest.main(["-q", "--no-header", "-p", "no:cacheprovider", *fichiers], plugins=[cap])

    res, total, par_test = {}, 0, {}
    for nom, appels in sorted(cap.appels.items()):
        orig = cibles[nom]
        sig = inspect.signature(orig)
        canaux = [p for p in sig.parameters if p.endswith("_by_pos") or p in _CANAUX_SCALAIRES]
        stats = {"appels": 0, "redondant": 0, "porteur_unique": {c: 0 for c in canaux},
                 "inerte": 0}
        for (nodeid, a, kw) in appels[:max_appels]:
            try:
                lie = sig.bind(*a, **kw)
                lie.apply_defaults()
                base = orig(*a, **kw)
                vals = dict(lie.arguments)
                actifs = [c for c in canaux if vals.get(c) is not None]
                if not actifs:
                    continue
                cle = (nodeid, nom)
                pt = par_test.setdefault(cle, {"appels": 0, "redondant": 0, "unique": set(),
                                               "canaux_concurrents": set()})
                tous = dict(vals)
                for c in actifs:
                    tous[c] = None
                stats["appels"] += 1
                pt["appels"] += 1
                # ⚠ CHAQUE canal est evalue SEPAREMENT, MEME quand couper tous les canaux ne
                # change rien. `tous == base` n'implique PAS « aucun canal ne mord » : deux canaux
                # de sens OPPOSES se compensent (`is_tile_in_range_of_any_ability` -- couper
                # l'elevation ELARGIT, couper l'equipe RESTREINT). Le premier jet sautait la
                # boucle sur ce test et rendait MUETTE une contre-epreuve qui mordait.
                seul_inerte = []
                for c in actifs:
                    un = dict(vals)
                    un[c] = None
                    if orig(**un) == base:
                        seul_inerte.append(c)     # ce canal N'EST PAS le seul porteur
                    else:
                        stats["porteur_unique"][c] += 1
                        pt["unique"].add(c)
                if len(seul_inerte) == len(actifs) and orig(**tous) == base:
                    stats["inerte"] += 1          # ni seul ni ensemble : hors regime
                elif seul_inerte and orig(**tous) != base:
                    stats["redondant"] += 1
                    pt["redondant"] += 1
                    # Un canal peut figurer ici ET dans `unique` : les deux verdicts portent sur
                    # des APPELS distincts du meme test. C'est le consommateur qui tranche, par
                    # appel -- agreger les deux ferait dire au probe l'inverse de sa mesure.
                    pt["canaux_concurrents"] |= set(seul_inerte)
            except (TypeError, ValueError):
                continue
        total += stats["appels"]
        res[nom] = stats
    out = {"rc_pytest": int(code), "total_appels": total, "par_foyer": res,
           "par_test": {"%s :: %s" % (k[0], k[1]):
                        {"appels": v["appels"], "redondant": v["redondant"],
                         "porteur_unique": sorted(v["unique"]),
                         "canaux_concurrents": sorted(v["canaux_concurrents"])}
                        for k, v in sorted(par_test.items())}}
    if verbose:
        print("[muettes] pytest rc=%d, %d appels de foyer multi-canaux captes"
              % (out["rc_pytest"], total))
        for nom, s in res.items():
            print("[muettes]   %-32s appels=%4d  exclusion REDONDANTE=%d  inertes=%d"
                  % (nom, s["appels"], s["redondant"], s["inerte"]))
            for c, k in sorted(s["porteur_unique"].items()):
                if k:
                    print("[muettes]       porteur UNIQUE de l'exclusion : %-18s sur %d appels"
                          % (c, k))
        print("[muettes] -- TESTS dont AUCUN appel n'a de porteur unique (une contre-epreuve"
              " mono-canal y serait MUETTE) :")
        for cle, v in out["par_test"].items():
            if v["redondant"] and not v["porteur_unique"]:
                print("[muettes]   %s  (%d/%d appels redondants, concurrents %s)"
                      % (cle, v["redondant"], v["appels"], ",".join(v["canaux_concurrents"])))
    return out


def verdict(verbose=True) -> int:
    """LE VERDICT, et il ne porte QUE sur une peremption EFFECTIVE.

    Ce module est d'abord un INVENTAIRE -- et un inventaire qui se declare garde-fou est le vice de
    `probe_181` avant #430. Le seul invariant qu'on puisse tenir SANS faux positif est celui-ci :
    une contre-epreuve dont le canal neutralise n'est porteur UNIQUE d'aucune exclusion, sur les
    etats qu'elle joue reellement, est MUETTE -- elle ne discrimine plus rien, quelle qu'en soit la
    cause. Elle rougit ici, nommee.

    Elle NE rougit PAS sur la couverture (« ce site ne passe pas par le helper ») : les 17 sites
    concernes sont tous justes aujourd'hui, et un garde qui les ferait rougir en bloc se ferait
    desarmer -- c'est l'avertissement du residu, pris au mot.

    TRI-ETAT : un site dont le callee n'est PAS un foyer capte (un playbook, un helper local) est
    rendu NON MESURE, jamais VERT -- et si TOUS le sont, le verdict est INDISPONIBLE (99), jamais
    un PASS. Un perimetre vide qui se lit « rien a signaler » est le vice qu'on ferme ici."""
    par_arg = contre_epreuves_par_argument(verbose=False)["sites"]
    par_rep = contre_epreuves(verbose=False)["couples"]
    sites = ([{"fichier": s["fichier"], "fonction": s["fonction"], "callee": s["callee"],
               "canaux": s["manquants"]} for s in par_arg]
             + [{"fichier": c["fichier"], "fonction": c["fonction"], "callee": c["callee"],
                 "canaux": c["champs"]} for c in par_rep])
    couverts = _sites_couverts_par_le_helper()
    tests = sorted({s["fichier"] for s in sites if _porteur(s["fichier"]) == "test"})
    mes = muettes([str(RACINE / f) for f in tests], verbose=False)
    par_test = mes["par_test"]

    muets, non_mesures, mesures, deja, multi = [], [], 0, [], []
    for s in sites:
        if (s["fichier"], s["fonction"]) in couverts:
            deja.append(s)                     # le helper le garde A L'EXECUTION
            continue
        if _porteur(s["fichier"]) != "test":
            non_mesures.append((s, "porteur PROBE -- non rejoue par pytest"))
            continue
        if len(s["canaux"]) != 1:
            # Une contre-epreuve qui coupe PLUSIEURS canaux d'un coup DISCRIMINE (le bras mute
            # differe), mais elle n'ATTRIBUE pas : elle ne dit pas LEQUEL des etages a mordu. Ce
            # n'est pas le regime du residu, et exiger que chaque canal soit porteur unique
            # ferait rougir des tests corrects. Hors verdict, listee.
            multi.append(s)
            continue
        base = Path(s["fichier"]).name
        vus = [(cle, v) for cle, v in par_test.items()
               if base in cle and ("::" + s["fonction"]) in cle
               and cle.rsplit(" :: ", 1)[-1] == s["callee"]]
        if not vus:
            non_mesures.append((s, "aucun appel capte de `%s` dans ce test" % s["callee"]))
            continue
        mesures += 1
        for canal in s["canaux"]:
            porte = any(canal in v["porteur_unique"] for (_c, v) in vus)
            redond = any(v["redondant"] for (_c, v) in vus)
            if not porte and redond:
                muets.append((s, canal, sorted({x for (_c, v) in vus
                                                for x in v["canaux_concurrents"]})))
    if verbose:
        print("== #433-r4-r2-r4-r1 -- contre-epreuves par CANAL")
        print("   sites a deux bras recenses : %d" % len(sites))
        print("   deja gardes par le helper  : %d" % len(deja))
        print("   MESURES par rejeu (MONO-canal) : %d" % mesures)
        print("   coupent PLUSIEURS canaux -> discriminent sans ATTRIBUER : %d" % len(multi))
        for s in multi:
            print("      %s::%s -- %s prive de %s (aucun etage isole)"
                  % (s["fichier"], s["fonction"], s["callee"], ",".join(s["canaux"])))
        print("   NON MESURES (tri-etat, jamais un vert) : %d" % len(non_mesures))
        for (s, pourquoi) in non_mesures:
            print("      %s::%s -- %s" % (s["fichier"], s["fonction"], pourquoi))
        print("   contre-epreuves MUETTES : %d (attendu 0)" % len(muets))
        for (s, canal, conc) in muets:
            print("      %s::%s -- `%s` n'est porteur UNIQUE d'aucune exclusion ; concurrents %s"
                  % (s["fichier"], s["fonction"], canal, ",".join(conc) or "?"))
    if not mesures and not deja:
        print("INDISPONIBLE: aucun site MESURE ni garde -- le verdict ne porte sur RIEN")
        return 99
    if verbose:
        print("VERDICT: %s" % ("PASS" if not muets else "FAIL (%d)" % len(muets)))
    return 0 if not muets else 1


def _sites_couverts_par_le_helper() -> set:
    """{(fichier, fonction)} des contre-epreuves qui passent par `assert_channel_counterproof*`.

    Elles n'ont pas besoin du rejeu de ce probe : le helper mesure la meme chose AU MOMENT ou la
    contre-epreuve joue, et leve un type NOMME. Les compter ici evite de les rendre « non
    mesurees », ce qui les ferait passer pour un trou alors qu'elles sont le remede."""
    out = set()
    for p in _fichiers_versionnes():
        rel = p.relative_to(RACINE).as_posix()
        if _porteur(rel) not in ("probe", "test"):
            continue
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError:
            continue
        for fn in ast.walk(arbre):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for n in ast.walk(fn):
                if not isinstance(n, ast.Call):
                    continue
                f = n.func
                nom = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
                if nom and nom.startswith("assert_channel_counterproof"):
                    out.add((rel, fn.name))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="all",
                    choices=["all", "inventaire", "foyers", "redondance", "contre-epreuves",
                             "par-argument", "muettes", "verdict"])
    ap.add_argument("--fichiers", nargs="*", default=None,
                    help="fichiers pytest OFFLINE a rejouer pour `--step muettes`")
    a = ap.parse_args()
    if a.step in ("all", "inventaire"):
        inventaire()
    if a.step in ("all", "foyers"):
        foyers_multicanaux()
    if a.step in ("all", "redondance"):
        foyers_redondants()
    if a.step in ("all", "contre-epreuves"):
        contre_epreuves()
    if a.step in ("all", "par-argument"):
        contre_epreuves_par_argument()
    if a.step == "muettes":
        cibles = a.fichiers or sorted(
            {c["fichier"] for c in contre_epreuves(verbose=False)["couples"]
             if _porteur(c["fichier"]) == "test"}
            | {s["fichier"] for s in contre_epreuves_par_argument(verbose=False)["sites"]
               if _porteur(s["fichier"]) == "test"})
        muettes([str(RACINE / f) for f in cibles])
    if a.step in ("all", "verdict"):
        return verdict()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
