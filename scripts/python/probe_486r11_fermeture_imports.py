"""#486-r11 -- MESURE de la fermeture d'imports d'`engine/` : granularite et angles morts.

Ce fichier ne juge rien (aucun `rc != 0` sur le depot) : il RECENSE, pour qu'on puisse citer des
chiffres re-derives au lieu de recopier un paragraphe. Trois vues :

    --granularite  distribution des fermetures et RAYON D'INVALIDATION par fichier -- c'est-a-dire
                   « si je touche ce fichier, combien de modules doivent etre re-testes ? ».
                   Le gain de la cle par sous-graphe se lit LA, et nulle part ailleurs.
    --formes       les sites qui font SOUS-APPROXIMER un calcul statique : import dynamique
                   (`importlib.import_module`, `__import__`, `pkgutil`, `exec`/`eval`) et import
                   OPTIONNEL dont la cible n'existe pas (creer le fichier le rendrait vivant sans
                   qu'aucune cle bouge). Ce sont les deux angles morts NOMMES d'`import_closure`.
    --debordements confronte, pour un echantillon, la fermeture CALCULEE a la fermeture MESUREE
                   par un interpreteur frais. C'est le controle qui rend les `--formes` inoffensifs :
                   ce qui deborde retombe sur la cle grossiere, et se lit ici.

Usage :
    python probe_486r11_fermeture_imports.py --granularite
    python probe_486r11_fermeture_imports.py --formes
    python probe_486r11_fermeture_imports.py --debordements --echantillon 24

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RACINE = Path(__file__).resolve().parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

import import_closure as IC                                            # noqa: E402
import probe_270r4r2_import_en_premier as IP                           # noqa: E402

#: Les appels qui chargent un module sans qu'aucun `import` ne le declare. Un calcul statique
#: ne peut pas les suivre : leur cible est une CHAINE, potentiellement construite a l'execution.
DYNAMIQUES = ("importlib.import_module", "importlib.__import__", "import_module", "__import__",
              "pkgutil.iter_modules", "pkgutil.walk_packages", "exec", "eval")


def _nom_appele(noeud: ast.AST) -> str:
    if isinstance(noeud, ast.Name):
        return noeud.id
    if isinstance(noeud, ast.Attribute):
        return "%s.%s" % (_nom_appele(noeud.value), noeud.attr)
    return ""


def formes(racine_paquet: Path) -> tuple[list, list]:
    """`(sites dynamiques, imports optionnels non resolus)` sous `racine_paquet`."""
    dyn, optionnels = [], []
    for f in sorted(racine_paquet.rglob("*.py")):
        try:
            texte = f.read_text(encoding="utf-8")
            arbre = ast.parse(texte, filename=str(f))
        except (OSError, UnicodeDecodeError, SyntaxError):             # pragma: no cover
            continue
        try:
            rel = f.relative_to(RACINE).as_posix()
        except ValueError:                                             # racine JETABLE (temoin)
            rel = f.name
        for n in ast.walk(arbre):
            if isinstance(n, ast.Call):
                nom = _nom_appele(n.func)
                if nom in DYNAMIQUES:
                    dyn.append((rel, n.lineno, nom))
            if isinstance(n, ast.Try):
                #: un import sous `try/except ImportError` dont la cible n'existe PAS : le jour
                #: ou le fichier est cree, il devient vivant, et il n'etait dans AUCUNE fermeture.
                capte = any(isinstance(h.type, ast.Name) and h.type.id in
                            ("ImportError", "ModuleNotFoundError") for h in n.handlers)
                if not capte:
                    continue
                for sous in ast.walk(n):
                    if not isinstance(sous, (ast.Import, ast.ImportFrom)):
                        continue
                    cibles = ([a.name for a in sous.names] if isinstance(sous, ast.Import)
                              else [sous.module or ""])
                    for c in cibles:
                        if c and IC.CLOTURE.resoudre(c) is None and c.split(".")[0] in (
                                "engine",):
                            optionnels.append((rel, sous.lineno, c))
    return dyn, optionnels


_TEMOIN_DYN = '''\
import importlib


def charge(nom):
    return importlib.import_module("engine." + nom)
'''

_TEMOIN_OPT = '''\
try:
    from engine.ce_module_n_existe_pas import X
except ImportError:
    X = None
'''


def temoin_formes() -> tuple[int, int]:
    """`formes()` VOIT-il encore ? Rend `(sites dynamiques, imports optionnels)` sur un corpus JOUET.

    Un recenseur qui rend ZERO sur `engine/` ne prouve RIEN s'il ne voit plus rien nulle part --
    et c'est precisement le regime ou son zero serait cite comme « aucun angle mort ». Le temoin
    est SYNTHETIQUE : balayer les 2 000 fichiers de `scripts/python/` couterait ~28 s pour la
    meme information.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        racine = Path(d)
        (racine / "dyn.py").write_text(_TEMOIN_DYN, encoding="utf-8")
        (racine / "opt.py").write_text(_TEMOIN_OPT, encoding="utf-8")
        (racine / "sain.py").write_text("import os\n\n\ndef f():\n    return os.sep\n",
                                        encoding="utf-8")
        dyn, opt = formes(racine)
    return len(dyn), len(opt)


def granularite(mods) -> None:
    ferm = IC.CLOTURE.fermetures(mods)
    tailles = sorted(len(f) for f in ferm.values())
    n = len(tailles)
    print("[486-r11] TEMOIN : %d module(s) sous engine/" % n)
    if n == 0:
        print("[486-r11] ECHEC : 0 module -- un zero de balayage ne prouve RIEN")
        return
    print("[486-r11] taille de FERMETURE : min=%d med=%d moy=%.1f p90=%d max=%d"
          % (tailles[0], tailles[n // 2], sum(tailles) / n, tailles[int(n * 0.9)], tailles[-1]))

    inverse: dict[str, set] = {}
    for m, f in ferm.items():
        for x in f:
            inverse.setdefault(x, set()).add(m)
    rayons = sorted((len(v), k) for k, v in inverse.items())
    r = [x for x, _ in rayons]
    print("[486-r11] RAYON D'INVALIDATION par fichier (modules a re-tester si on le touche) :")
    print("          %d fichier(s) gouvernent au moins un module ; min=%d med=%d moy=%.1f max=%d"
          % (len(r), r[0], r[len(r) // 2], sum(r) / len(r), r[-1]))
    print("          cle GROSSIERE (#486-r5) : ce rayon vaut %d pour TOUT fichier." % n)
    print("[486-r11] les 8 plus larges : %s"
          % ", ".join("%s=%d" % (k, x) for x, k in rayons[-8:]))
    print("[486-r11] fichiers de rayon 1 (une PR qui n'y touche qu'eux ne relance qu'eux) : %d"
          % sum(1 for x, _ in rayons if x == 1))
    hors = sorted(k for k in inverse if not (k == "engine" or k.startswith("engine.")))
    print("[486-r11] fichiers HORS engine/ dans au moins une fermeture : %d (%s)"
          % (len(hors), ", ".join("%s=%d" % (h, len(inverse[h])) for h in hors) or "aucun"))
    print("          la cle grossiere ne les regardait PAS : les modifier ne reinvalidait rien.")


def debordements(mods, jobs: int) -> int:
    """Confronte fermeture CALCULEE et fermeture MESUREE. Rend le nombre de modules opaques."""
    def _un(mod):
        r = subprocess.run([sys.executable, "-c", IC.code_sonde(mod, RACINE)],
                           cwd=str(RACINE), capture_output=True, text=True, timeout=180)
        return mod, r.returncode, IC.lire_fermeture_mesuree(r.stdout)

    IC.CLOTURE.fermetures(mods)
    opaques, non_mesures, rouges = [], [], []
    with ThreadPoolExecutor(max_workers=max(1, min(jobs, len(mods)))) as ex:
        for mod, rc, mesuree in ex.map(_un, mods):
            if rc != 0:
                rouges.append(mod)
                continue
            if mesuree is None:
                non_mesures.append(mod)
                continue
            deborde = IC.CLOTURE.sous_approximation(mod, mesuree)
            if deborde:
                opaques.append((mod, sorted(deborde)))
    print("[486-r11] TEMOIN : %d module(s) sondes, %d en echec d'import" % (len(mods), len(rouges)))
    print("[486-r11] fermeture NON MESUREE (tri-etat, repli grossier) : %d" % len(non_mesures))
    print("[486-r11] SOUS-APPROXIMATIONS (repli sur la cle GROSSIERE) : %d" % len(opaques))
    for mod, quoi in opaques[:20]:
        print("   %s  <- %s" % (mod, ", ".join(quoi[:6])))
    return len(opaques) + len(non_mesures)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--granularite", action="store_true")
    ap.add_argument("--formes", action="store_true")
    ap.add_argument("--debordements", action="store_true")
    ap.add_argument("--echantillon", type=int, default=0,
                    help="ne sonder qu'un module sur N (0 = tous)")
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()
    if not (a.granularite or a.formes or a.debordements):
        a.granularite = a.formes = True

    mods = IP._modules_sous(("engine",))
    if not mods:
        print("[486-r11] ECHEC : 0 module sous engine/ -- un zero de balayage ne prouve RIEN")
        return 2

    if a.granularite:
        granularite(mods)
    if a.formes:
        t_dyn, t_opt = temoin_formes()
        print("[486-r11] TEMOIN du detecteur (corpus jouet) : %d dynamique(s), %d optionnel(s)"
              % (t_dyn, t_opt))
        if not (t_dyn and t_opt):
            print("[486-r11] ECHEC : le detecteur ne voit plus rien -- son ZERO sur engine/ ne")
            print("          prouverait RIEN, et se lirait pourtant comme « aucun angle mort »")
            return 2
        dyn, opt = formes(RACINE / "engine")
        print("[486-r11] sites d'import DYNAMIQUE dans engine/ : %d" % len(dyn))
        for rel, ligne, nom in dyn[:20]:
            print("   %s:%d  %s(...)" % (rel, ligne, nom))
        print("[486-r11] imports OPTIONNELS `engine.*` dont la cible n'existe pas : %d" % len(opt))
        for rel, ligne, cible in opt[:20]:
            print("   %s:%d  -> %s" % (rel, ligne, cible))
        print("          (le jour ou ce fichier est cree, il devient vivant sans qu'aucune cle")
        print("           bouge -- c'est l'angle mort NOMME d'`import_closure`.)")
    if a.debordements:
        cibles = mods[::a.echantillon] if a.echantillon > 1 else mods
        debordements(cibles, a.jobs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
