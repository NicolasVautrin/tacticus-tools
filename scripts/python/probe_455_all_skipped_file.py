#!/usr/bin/env python
"""Probe #455 -- le cliquet du garde-fou << fichier de test 100 % skippe >>.

CE QU'IL EST SEUL A VOIR
------------------------
Un fichier de test dont le bilan est `passed == 0 and skipped > 0` : la suite le compte comme un
SUCCES, il n'a evalue AUCUNE assertion, et rien ne le signale. Mesure d'origine :
`test_summon_trait_effects_live.py` = 8 skipped / 0 passed / rc 0 sur `origin/master`, trouve en
ECARTANT une PR, pas cherche.

Le mecanisme de detection vit dans `green_skip_guard.py` (plugin pytest, branche par
`tests/conftest.py`) : c'est LUI qui voit le gisement, a chaque passe ciblee que joue n'importe
quel agent, pour un cout nul. Ce probe est le CLIQUET qui garde que ce plugin existe, mord, et
**est branche**. Sans lui, le garde pourrait etre neutralise (import retire du conftest, critere
elargi) sans qu'aucun rouge ne tombe -- exactement le vice de `probe_181` avant #430.

TROIS ETAPES, ET LA TROISIEME EST LA COUVERTURE
-----------------------------------------------
0. AUTO-TEST du critere sur des rapports SYNTHETIQUES. Un cliquet dont le detecteur a cesse de
   mordre rend vert sur un depot fautif. Il tourne a CHAQUE run et fait partie du verdict.
1. BOUT EN BOUT sur des fichiers de test SYNTHETIQUES, dans un repertoire isole, plugin charge par
   `-p green_skip_guard` : le rouge tombe-t-il, et **seulement** quand il doit ? Chaque cas positif
   a son jumeau NEGATIF -- c'est lui qui interdit de faire mordre le garde en elargissant son
   critere. Le cas << sans le plugin >> rend le rouge ATTRIBUABLE : sans lui, on ne saurait pas si
   c'est le garde qui rougit ou le fichier synthetique.
2. CABLAGE (#421 -- prouver sa couverture dans le MEME processus que sa conformite). Un garde qui
   mord dans un tmpdir mais n'est pas charge par la suite reelle ne garde RIEN. On depose donc un
   fichier inerte SOUS `scripts/python/tests/` et on exige un rouge **sans aucun `-p`** : le seul
   chemin possible est l'import du conftest de production. Contre-epreuve dans le meme geste : le
   MEME fichier, hors de `tests/`, sans `-p`, doit rendre VERT.
   Le depot est temporaire (nom porte le PID), efface en `finally`, et sa fenetre d'existence est
   la duree d'un run pytest.

PERIMETRE : ce probe n'enumere RIEN depuis la racine du depot (il ecrit dans un tmpdir et sous son
PROPRE checkout, resolu par `Path(__file__)`), il est donc hors du gisement de `probe_440`.

ASCII only (console Windows cp1252).
Usage: python probe_455_all_skipped_file.py [-v] [--self-test]
"""
from __future__ import annotations

import argparse
import ast
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
TESTS = PYDIR / "tests"

sys.path.insert(0, str(PYDIR))
import green_skip_guard as G                                        # noqa: E402

#: Les hooks que `tests/conftest.py` DOIT re-exporter. Derives du module, pas saisis : ajouter un
#: hook au garde sans le brancher fait rougir l'etape 2.
HOOKS = tuple(n for n in dir(G) if n.startswith("pytest_"))


# ==========================================================================================
#  Etape 0 -- auto-test du critere sur des rapports synthetiques
# ==========================================================================================

class _Rep:
    """Le strict necessaire d'un `TestReport` pour `bilan_par_fichier` : nodeid, phase, issue."""

    def __init__(self, nodeid, when, issue, xfail=False):
        self.nodeid, self.when = nodeid, when
        self.passed = issue == "passed"
        self.failed = issue == "failed"
        self.skipped = issue == "skipped"
        if xfail:
            self.wasxfail = ""


def _stats(reports) -> dict:
    """Imite `terminalreporter.stats` : un dict de listes, indexe par categorie (non lue)."""
    return {"tout": list(reports)}


def _test(nodeid, issue, when="call", xfail=False):
    """Les trois rapports d'un test qui PASSE, ou le seul rapport de son issue."""
    if issue == "passed" and not xfail:
        return [_Rep(nodeid, "setup", "passed"), _Rep(nodeid, "call", "passed"),
                _Rep(nodeid, "teardown", "passed")]
    return [_Rep(nodeid, when, issue, xfail=xfail)]


F = "tests/x/test_f.py"
AUTRE = "tests/x/test_g.py"

# (nom, reports, kwargs de fichiers_inertes, fichiers attendus)
CAS = [
    ("3 skips : INERTE",
     _test(F + "::a", "skipped") + _test(F + "::b", "skipped") + _test(F + "::c", "skipped"),
     {}, [F]),
    ("skip en SETUP (fixture) : INERTE aussi",
     _test(F + "::a", "skipped", when="setup") + _test(F + "::b", "skipped", when="setup"),
     {}, [F]),
    # --- jumeaux NEGATIFS : ce sont eux qui interdisent d'elargir le critere ---
    ("1 passed + 2 skips : le fichier a mesure quelque chose",
     _test(F + "::a", "passed") + _test(F + "::b", "skipped") + _test(F + "::c", "skipped"),
     {}, []),
    ("3 passed : rien a signaler",
     _test(F + "::a", "passed") + _test(F + "::b", "passed") + _test(F + "::c", "passed"),
     {}, []),
    ("2 xfail : l'assertion A ETE evaluee (son echec etait attendu)",
     _test(F + "::a", "skipped", xfail=True) + _test(F + "::b", "skipped", xfail=True),
     {}, []),
    ("1 xpass + 1 skip : idem",
     _test(F + "::a", "passed", xfail=True) + _test(F + "::b", "skipped"),
     {}, []),
    ("aucun skip : le critere exige skipped > 0",
     _test(F + "::a", "failed"), {}, []),
    # --- les trois causes de bilan PARTIEL ---
    ("session INTERROMPUE : bilan tronque, on ne conclut rien",
     _test(F + "::a", "skipped") + _test(F + "::b", "skipped"), {"interrompu": True}, []),
    ("nodeid EXPLICITE en argument : selection partielle",
     _test(F + "::a", "skipped") + _test(F + "::b", "skipped"),
     {"args": [F + "::a"]}, []),
    ("argument FICHIER (sans ::) : selection COMPLETE, on conclut",
     _test(F + "::a", "skipped") + _test(F + "::b", "skipped"), {"args": [F]}, [F]),
    # --- discrimination entre fichiers ---
    ("deux fichiers, un seul inerte",
     _test(F + "::a", "skipped") + _test(AUTRE + "::a", "passed") + _test(AUTRE + "::b", "skipped"),
     {}, [F]),
    # --- le critere est LITTERAL : un fichier avec des echecs y entre aussi (il est deja
    #     visible en rouge, mais il reste vrai que rien n'y a ete confronte) ---
    ("1 failed + 2 skips : retenu (critere litteral passed == 0 and skipped > 0)",
     _test(F + "::a", "failed") + _test(F + "::b", "skipped") + _test(F + "::c", "skipped"),
     {}, [F]),
]


def self_test(verbose: bool) -> list:
    bad = []
    for nom, reports, kw, attendu in CAS:
        G._DESELECTIONNES.clear()
        obtenu = sorted(G.fichiers_inertes(_stats(reports), **kw))
        ok = obtenu == sorted(attendu)
        if verbose or not ok:
            print("   %-5s %-58s -> %s (attendu %s)"
                  % ("OK" if ok else "FAIL", nom, obtenu, sorted(attendu)))
        if not ok:
            bad.append(nom)

    # La deselection passe par le HOOK, pas par un argument : on l'exerce tel quel.
    G._DESELECTIONNES.clear()
    G.pytest_deselected([type("I", (), {"nodeid": F + "::b"})()])
    reports = _test(F + "::a", "skipped") + _test(F + "::c", "skipped")
    obtenu = sorted(G.fichiers_inertes(_stats(reports)))
    ok = obtenu == []
    if verbose or not ok:
        print("   %-5s %-58s -> %s (attendu [])"
              % ("OK" if ok else "FAIL", "items DESELECTIONNES : selection partielle", obtenu))
    if not ok:
        bad.append("deselection")
    G._DESELECTIONNES.clear()

    # L'echappatoire consciente.
    os.environ[G.ENV_ALLOW] = "1"
    try:
        reports = _test(F + "::a", "skipped") + _test(F + "::b", "skipped")
        obtenu = sorted(G.fichiers_inertes(_stats(reports)))
    finally:
        os.environ.pop(G.ENV_ALLOW, None)
    ok = obtenu == []
    if verbose or not ok:
        print("   %-5s %-58s -> %s (attendu [])"
              % ("OK" if ok else "FAIL", "%s=1 : debranche" % G.ENV_ALLOW, obtenu))
    if not ok:
        bad.append("echappatoire")
    return bad


# ==========================================================================================
#  Etapes 1 et 2 -- pytest en sous-processus sur des fichiers synthetiques
# ==========================================================================================

SRC_INERTE = (
    "import pytest\n\n\n"
    "def _montage():\n"
    "    pytest.skip('montage indisponible (fichier synthetique probe_455)')\n\n\n"
    "def test_un():\n    _montage()\n    assert False\n\n\n"
    "def test_deux():\n    _montage()\n    assert False\n\n\n"
    "def test_trois():\n    _montage()\n    assert False\n"
)
SRC_MIXTE = (
    "import pytest\n\n\n"
    "def test_qui_passe():\n    assert 1 + 1 == 2\n\n\n"
    "def test_skip_un():\n    pytest.skip('montage indisponible')\n\n\n"
    "def test_skip_deux():\n    pytest.skip('montage indisponible')\n"
)
SRC_XFAIL = (
    "import pytest\n\n\n"
    "@pytest.mark.xfail(reason='connu', strict=False)\n"
    "def test_xf_un():\n    assert False\n\n\n"
    "@pytest.mark.xfail(reason='connu', strict=False)\n"
    "def test_xf_deux():\n    assert False\n"
)

MARQUEUR = "FICHIERS 100 POURCENT SKIPPES"


def _pytest(args, cwd: Path, env_extra: dict = None) -> tuple:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PYDIR) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop(G.ENV_ALLOW, None)
    env.update(env_extra or {})
    p = subprocess.run([sys.executable, "-m", "pytest", *args, "-q", "-p", "no:cacheprovider"],
                       cwd=str(cwd), env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _verifie(nom, rc, out, rouge_attendu, nomme=(), pas_nomme=(), verbose=False) -> "str | None":
    """Un cas bout-en-bout : le rouge est-il tombe (ou non), et le rapport nomme-t-il ce qu'il faut ?"""
    pbs = []
    if rouge_attendu and rc == 0:
        pbs.append("rc=0 alors qu'un rouge etait attendu")
    if (not rouge_attendu) and rc != 0:
        pbs.append("rc=%d alors que le VERT etait attendu" % rc)
    if rouge_attendu and MARQUEUR not in out:
        pbs.append("le rapport du garde (%r) est absent de la sortie" % MARQUEUR)
    if (not rouge_attendu) and MARQUEUR in out:
        pbs.append("le rapport du garde apparait alors qu'il ne devait pas")
    for n in nomme:
        if n not in out:
            pbs.append("le fichier %r n'est pas nomme" % n)
    for n in pas_nomme:
        section = out.split(MARQUEUR, 1)[1] if MARQUEUR in out else ""
        if n in section:
            pbs.append("le fichier SAIN %r est nomme a tort" % n)
    ok = not pbs
    if verbose or not ok:
        print("   %-5s %-58s rc=%d" % ("OK" if ok else "FAIL", nom, rc))
        for pb in pbs:
            print("         %s" % pb)
        if not ok:
            for ln in out.strip().splitlines()[-12:]:
                print("         | %s" % ln.encode("ascii", "replace").decode("ascii"))
    return None if ok else nom


def bout_en_bout(verbose: bool) -> list:
    """Etape 1 -- le garde dans un repertoire ISOLE, charge par `-p green_skip_guard`."""
    bad = []
    tmp = Path(tempfile.mkdtemp(prefix="probe455_"))
    try:
        (tmp / "test_455_inerte.py").write_text(SRC_INERTE, encoding="utf-8")
        (tmp / "test_455_mixte.py").write_text(SRC_MIXTE, encoding="utf-8")
        (tmp / "test_455_xfail.py").write_text(SRC_XFAIL, encoding="utf-8")
        P = ["-p", "green_skip_guard"]
        cas = [
            ("fichier 100 pourcent skippe -> ROUGE", ["test_455_inerte.py", *P], None,
             True, ("test_455_inerte.py",), ()),
            ("le MEME sans le plugin -> vert (le rouge est ATTRIBUABLE au garde)",
             ["test_455_inerte.py"], None, False, (), ()),
            ("le MEME avec l'echappatoire -> vert", ["test_455_inerte.py", *P],
             {G.ENV_ALLOW: "1"}, False, (), ()),
            ("1 passed + 2 skips -> vert", ["test_455_mixte.py", *P], None, False, (), ()),
            ("2 xfail (assertions evaluees) -> vert", ["test_455_xfail.py", *P], None,
             False, (), ()),
            ("les trois ensemble -> ROUGE, et SEUL l'inerte est nomme", [".", *P], None,
             True, ("test_455_inerte.py",), ("test_455_mixte.py", "test_455_xfail.py")),
            ("selection par -k (deselection) -> vert",
             ["test_455_inerte.py", "-k", "test_un", *P], None, False, (), ()),
            ("nodeid explicite -> vert",
             ["test_455_inerte.py::test_un", *P], None, False, (), ()),
        ]
        for nom, args, env, rouge, nomme, pas_nomme in cas:
            rc, out = _pytest(args, tmp, env)
            r = _verifie(nom, rc, out, rouge, nomme, pas_nomme, verbose)
            if r:
                bad.append(r)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return bad


def cablage(verbose: bool) -> list:
    """Etape 2 -- le garde est-il BRANCHE sur la suite reelle ? (#421 : couverture prouvee ici)"""
    bad = []
    # (a) introspection : le conftest de production re-exporte-t-il TOUS les hooks du garde ?
    manquants = []
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_probe455_conftest",
                                                      TESTS / "conftest.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        manquants = [h for h in HOOKS if getattr(mod, h, None) is not getattr(G, h)]
    except Exception as exc:                              # noqa: BLE001
        manquants = ["<conftest non importable : %s>" % exc]
    ok = not manquants
    if verbose or not ok:
        print("   %-5s %-58s %s"
              % ("OK" if ok else "FAIL", "tests/conftest.py re-exporte les %d hooks" % len(HOOKS),
                 "" if ok else "manquants: %s" % manquants))
    if not ok:
        bad.append("conftest ne re-exporte pas les hooks")

    # (b) bout en bout SANS `-p` : le seul chemin de chargement possible est ce conftest.
    rep = TESTS / ("_probe455_cablage_%d" % os.getpid())
    hors = PYDIR / ("_probe455_hors_%d" % os.getpid())
    try:
        rep.mkdir(parents=True, exist_ok=True)
        hors.mkdir(parents=True, exist_ok=True)
        (rep / "test_455_cablage.py").write_text(SRC_INERTE, encoding="utf-8")
        (hors / "test_455_cablage.py").write_text(SRC_INERTE, encoding="utf-8")
        rc, out = _pytest([str(rep.relative_to(PYDIR).as_posix())], PYDIR)
        r = _verifie("sous tests/, SANS -p -> ROUGE (le conftest charge le garde)",
                     rc, out, True, ("test_455_cablage.py",), (), verbose)
        if r:
            bad.append(r)
        # Contre-epreuve : hors de `tests/`, le conftest ne s'applique pas -> vert.
        rc, out = _pytest([str(hors.relative_to(PYDIR).as_posix())], PYDIR)
        r = _verifie("hors tests/, SANS -p -> vert (contre-epreuve du cablage)",
                     rc, out, False, (), (), verbose)
        if r:
            bad.append(r)
    finally:
        shutil.rmtree(rep, ignore_errors=True)
        shutil.rmtree(hors, ignore_errors=True)
    return bad


# ==========================================================================================
#  INVENTAIRE -- HORS VERDICT, et il faut dire pourquoi
# ==========================================================================================
#
# Le gisement REEL (« quels fichiers sont inertes aujourd'hui ») ne se dérive que d'une
# EXECUTION : un skip de montage depend de l'etat live, il est indecidable statiquement. Or la
# suite complete est proscrite (`CLAUDE.md`) et chaque fichier live monte un runner.
#
# Ce mode ne repond donc PAS a cette question : il rend le SUR-ENSEMBLE statique des fichiers
# dont TOUS les tests peuvent atteindre un `pytest.skip` -- le seul sous-ensemble qu'il vaille
# la peine de jouer pour mesurer le gisement. Il rend TOUJOURS 0 : un sur-ensemble ne conclut
# rien, et le faire entrer au verdict en ferait un cliquet qui rougit sur des fichiers sains.
# C'est le garde RUNTIME (`green_skip_guard`) qui voit le gisement, a chaque passe.

_SKIPPEURS = ("skip", "importorskip", "xfail")          # `pytest.<nom>(...)` qui sort du test


def _appels_pytest(noeud) -> set:
    """Noms `pytest.<x>(...)` appeles dans le sous-arbre (`x` dans `_SKIPPEURS`)."""
    out = set()
    for n in ast.walk(noeud):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr in _SKIPPEURS \
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "pytest":
            out.add(n.func.attr)
    return out


def _noms_appeles(noeud) -> set:
    """Noms de fonctions appelees dans le sous-arbre (appels simples `f(...)`)."""
    return {n.func.id for n in ast.walk(noeud)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def _marque_skip(fn) -> bool:
    """`@pytest.mark.skip` / `@pytest.mark.skipif` sur la fonction."""
    for d in fn.decorator_list:
        cible = d.func if isinstance(d, ast.Call) else d
        if isinstance(cible, ast.Attribute) and cible.attr in ("skip", "skipif"):
            return True
    return False


def candidats(verbose: bool) -> list:
    """[(fichier, nb tests)] dont TOUS les tests peuvent atteindre un skip."""
    out = []
    for p in sorted(TESTS.rglob("test_*.py")):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=p.name)
        except (SyntaxError, ValueError, OSError):
            continue
        fns = {n.name: n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        direct = {nom: bool(_appels_pytest(fn)) for nom, fn in fns.items()}
        appels = {nom: _noms_appeles(fn) for nom, fn in fns.items()}
        # Fermeture transitive : un test qui appelle un helper skippeur skippe aussi.
        for _ in range(6):
            avant = sum(direct.values())
            for nom in fns:
                if not direct[nom] and any(direct.get(a) for a in appels[nom]):
                    direct[nom] = True
            if sum(direct.values()) == avant:
                break
        tests = [nom for nom in fns if nom.startswith("test_")]
        if not tests:
            continue
        if all(direct[t] or _marque_skip(fns[t]) for t in tests):
            out.append((p.relative_to(PYDIR).as_posix(), len(tests)))
    if verbose:
        for rel, n in out:
            print("   %-72s %d test(s)" % (rel, n))
    return out


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--self-test", action="store_true",
                    help="ne joue QUE l'auto-test du critere, en detail")
    ap.add_argument("--inventaire", action="store_true",
                    help="HORS VERDICT : sur-ensemble statique des fichiers dont TOUS les tests "
                         "peuvent atteindre un skip (le sous-ensemble a jouer pour mesurer le "
                         "gisement reel). Rend toujours 0.")
    args = ap.parse_args(argv)

    if args.inventaire:
        c = candidats(True)
        total = len(list(TESTS.rglob("test_*.py")))
        print("[455] inventaire (HORS VERDICT) : %d fichier(s) candidat(s) sur %d -- "
              "SUR-ENSEMBLE statique, un candidat n'est pas un fichier inerte." % (len(c), total))
        return 0

    print("[455] garde : %s" % (PYDIR / "green_skip_guard.py"))
    e0 = self_test(args.verbose or args.self_test)
    print("[455] etape 0 : auto-test du critere -- %d cas, %d en echec"
          % (len(CAS) + 2, len(e0)))
    if args.self_test:
        print("[455] VERDICT: %s" % ("PASS" if not e0 else "FAIL (%d)" % len(e0)))
        return 0 if not e0 else 1

    e1 = bout_en_bout(args.verbose)
    print("[455] etape 1 : bout en bout (repertoire isole) -- 8 cas, %d en echec" % len(e1))
    e2 = cablage(args.verbose)
    print("[455] etape 2 : CABLAGE sur la suite reelle -- 3 cas, %d en echec" % len(e2))

    ko = len(e0) + len(e1) + len(e2)
    for nom in e0 + e1 + e2:
        print("   FAIL %s" % nom)
    if ko:
        print("[455] Un fichier 100 pourcent skippe ne serait plus signale : la suite le "
              "compterait comme un succes, sans qu'aucune assertion n'ait ete evaluee.")
    print("[455] VERDICT: %s" % ("PASS" if ko == 0 else "FAIL (%d)" % ko))
    return 0 if ko == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
