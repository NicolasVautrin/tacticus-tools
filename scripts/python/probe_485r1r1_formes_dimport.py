#!/usr/bin/env python
"""#485-r1-r1 -- LA FORME DE L'IMPORT DECIDE SI UN `monkeypatch` MORD. Banc EXECUTABLE.

POURQUOI CE BANC EXISTE
-----------------------
#484 (PR #741) a hisse 624 imports differes : **0 divergence sur 197 017 attributs** d'empreinte,
et **28 fichiers de tests rouges**. Puis la famille #429-r1 a rendu **12 rouges** de plus, cette
fois sur des tests LIVE -- que le recensement 100 % offline de #484 ne pouvait pas voir. Les deux
fois, le diagnostic ecrit fut << le test etait mal ecrit >>. Il est FAUX, et ce banc le montre en
trente lignes : c'est la FORME de l'import du consommateur qui decide, pas l'ecriture du test.

    A  `from X import foo` au NIVEAU MODULE   -> nom GELE au chargement  -> NE MORD PAS
    B  `import X` / `from pkg import X`       -> attribut relu a l'appel -> MORD
    C  `from X import foo` DANS la fonction   -> instruction RE-EXECUTEE -> MORD, par accident

HISSER, c'est passer de C a A -- donc de << mord >> a << ne mord pas >>. Le desarmement est
SILENCIEUX : le test ne mesure plus, il ne mesure pas FAUX.

TROIS ETAGES, ET LE TROISIEME EST LE PLUS COUTEUX A DECOUVRIR
-------------------------------------------------------------
    [1] FORMES      les trois formes, meme symbole, meme patch. A=VRAI, B/C=PATCHE.
    [2] CASCADE     A et B chargent-ils les MEMES modules ? Si oui, passer en B ne coute rien
                    et ne rouvre aucun cycle -- c'est ce qui rend le geste praticable.
                    Mesure DERIVEE de l'arbre reel, jamais un module ecrit en dur.
    [3] ORDRE       un differe protege SON site, mais la cascade qu'il declenche cree des
                    liaisons de forme A dans les modules TRAVERSES, gelees des le premier
                    chargement. Dans UNE passe pytest (un seul process), le verdict depend
                    alors de l'ORDRE des fichiers. B eteint ce vice, A ne l'eteint pas.

⚠ CE BANC N'EST PAS UN CLIQUET DU DEPOT : il garde une propriete du LANGAGE, qui ne changera pas.
Ce qui garde le DEPOT est `migrate_485r1_barils_reexport.py morsure`, qui croise les
substitutions reelles avec les differes que le cliquet #485 prescrit de hisser.

TRI-ETAT
--------
    rc 0   VERT   -- les trois etages se comportent comme decrit
    rc 1   ROUGE  -- une forme ne se comporte plus ainsi : la doctrine ci-dessus est a refaire
    rc 2   PAS MESURE -- le banc n'a pas pu etre monte / l'arbre reel est introuvable

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ICI = Path(__file__).resolve().parent
EX_VERT, EX_ROUGE, EX_PAS_MESURE = 0, 1, 2


def _ecrire(d: Path, nom: str, texte: str) -> None:
    (d / nom).write_text(texte, encoding="utf-8")


def _jouer(d: Path, script: str) -> str | None:
    try:
        r = subprocess.run([sys.executable, "-c", script], cwd=str(d), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return (r.stdout or "").strip()


def etage_formes(d: Path) -> tuple[dict[str, tuple[str, str]] | None, list[str]]:
    """Rend {forme: (avant, apres)} et les fautes."""
    _ecrire(d, "src_x.py", "def foo():\n    return 'VRAI'\n")
    _ecrire(d, "cons_a.py", "from src_x import foo\n\n\ndef appelle():\n    return foo()\n")
    _ecrire(d, "cons_b.py", "import src_x\n\n\ndef appelle():\n    return src_x.foo()\n")
    _ecrire(d, "cons_c.py", "def appelle():\n    from src_x import foo\n    return foo()\n")
    out = _jouer(d, "import cons_a, cons_b, cons_c, src_x\n"
                    "av = [cons_a.appelle(), cons_b.appelle(), cons_c.appelle()]\n"
                    "src_x.foo = lambda: 'PATCHE'\n"
                    "ap = [cons_a.appelle(), cons_b.appelle(), cons_c.appelle()]\n"
                    "print(' '.join(av + ap))")
    if out is None:
        return None, ["le banc des formes n'a pas pu etre joue"]
    bouts = out.split()
    if len(bouts) != 6:
        return None, ["sortie inattendue du banc : %r" % out]
    table = {"A": (bouts[0], bouts[3]), "B": (bouts[1], bouts[4]), "C": (bouts[2], bouts[5])}
    attendu = {"A": ("VRAI", "VRAI"), "B": ("VRAI", "PATCHE"), "C": ("VRAI", "PATCHE")}
    fautes = ["forme %s : %s attendu, %s mesure" % (f, attendu[f], table[f])
              for f in ("A", "B", "C") if table[f] != attendu[f]]
    return table, fautes


def _cible_profonde(racine: Path) -> str | None:
    """Un module `engine.*` niche a AU MOINS trois niveaux, DERIVE de l'arbre.

    Un module ecrit en dur perimerait au premier renommage, et la mesure se lirait alors comme
    un vert alors qu'elle n'aurait rien charge. On prend le plus profond, a nom stable trie."""
    pkg = racine / "engine"
    if not pkg.is_dir():
        return None
    cands = []
    for p in sorted(pkg.rglob("*.py")):
        if "__pycache__" in str(p) or p.name == "__init__.py":
            continue
        parts = p.relative_to(racine).with_suffix("").parts
        if len(parts) >= 4:
            cands.append(".".join(parts))
    return cands[0] if cands else None


def etage_cascade(racine: Path) -> tuple[dict[str, int] | None, list[str]]:
    """A et B chargent-ils les MEMES modules ? (ecart attendu : 0)"""
    cible = _cible_profonde(racine)
    if cible is None:
        return None, ["aucun module `engine.*` assez profond -- perimetre VIDE, pas un vert"]
    parent, feuille = cible.rsplit(".", 1)
    formes = {"A": "from %s import *" % cible,          # A : symboles du module
              "B": "from %s import %s" % (parent, feuille),
              "B2": "import %s" % cible}
    charges: dict[str, set[str]] = {}
    for nom, stmt in formes.items():
        out = _jouer(racine, "%s\nimport sys\nprint('\\n'.join(sorted(m for m in sys.modules "
                             "if m.startswith('engine'))))" % stmt)
        if out is None:
            return None, ["forme %s non chargeable sur `%s`" % (nom, cible)]
        charges[nom] = set(out.split())
    if not charges["A"]:
        return None, ["0 module charge -- capteur muet, pas un ecart nul"]
    ecarts = {n: len(charges["A"] ^ charges[n]) for n in charges}
    fautes = ["forme %s : %d module(s) d'ecart avec A sur `%s`" % (n, e, cible)
              for n, e in ecarts.items() if e]
    return {"modules charges": len(charges["A"]), **{"ecart %s" % n: e
                                                     for n, e in ecarts.items()}}, fautes


def etage_ordre(d: Path) -> tuple[dict[str, str] | None, list[str]]:
    """Le VERDICT depend-il de l'ORDRE des fichiers dans une meme passe ?

    Deux consommateurs, un module INTERMEDIAIRE traverse. Le test 1 charge la cascade SANS
    patcher, le test 2 patche ensuite. Si l'intermediaire lie en forme A, son binding est gele
    par le test 1 et le test 2 ne mord plus. En forme B, l'ordre n'a aucun effet."""
    _ecrire(d, "o_src.py", "def foo():\n    return 'VRAI'\n")
    _ecrire(d, "o_interA.py", "from o_src import foo\n\n\ndef via():\n    return foo()\n")
    _ecrire(d, "o_interB.py", "import o_src\n\n\ndef via():\n    return o_src.foo()\n")
    #: le consommateur resout TARDIVEMENT -- c'est le regime qui protege SON site, et c'est
    #: precisement celui qui laisse croire que tout va bien.
    for suffixe in ("A", "B"):
        _ecrire(d, "o_cons%s.py" % suffixe,
                "def appelle():\n    from o_inter%s import via\n    return via()\n" % suffixe)
    res: dict[str, str] = {}
    for suffixe in ("A", "B"):
        for ordre, script in (
            ("charge-puis-patche",
             "import o_cons{s}, o_src\n"
             "o_cons{s}.appelle()\n"                       # 1er test : charge SANS patcher
             "o_src.foo = lambda: 'PATCHE'\n"
             "print(o_cons{s}.appelle())"),
            ("patche-en-premier",
             "import o_cons{s}, o_src\n"
             "o_src.foo = lambda: 'PATCHE'\n"
             "print(o_cons{s}.appelle())"),
        ):
            out = _jouer(d, script.format(s=suffixe))
            if out is None:
                return None, ["banc d'ordre non jouable (inter%s / %s)" % (suffixe, ordre)]
            res["inter%s / %s" % (suffixe, ordre)] = out
    fautes = []
    if res["interA / charge-puis-patche"] == res["interA / patche-en-premier"]:
        fautes.append("l'intermediaire de forme A n'est PLUS ordre-dependant -- la doctrine "
                      "ecrite ici ne decrit plus Python, elle est a refaire")
    if res["interB / charge-puis-patche"] != res["interB / patche-en-premier"]:
        fautes.append("l'intermediaire de forme B est devenu ordre-dependant")
    if res["interB / charge-puis-patche"] != "PATCHE":
        fautes.append("l'intermediaire de forme B ne mord plus")
    return res, fautes


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--racine", type=Path, default=ICI,
                    help="repertoire qui CONTIENT `engine/` (defaut : celui de ce fichier)")
    a = ap.parse_args(argv)
    racine = a.racine.resolve()

    print("[485-r1-r1] la FORME de l'import decide si un `monkeypatch` mord")
    fautes: list[str] = []
    muet = False

    with tempfile.TemporaryDirectory(prefix="formes485_") as tmp:
        d = Path(tmp)
        print("\n[1] LES TROIS FORMES (banc isole)")
        table, f1 = etage_formes(d)
        if table is None:
            muet = True
        else:
            for forme in ("A", "B", "C"):
                av, ap_ = table[forme]
                print("    %s  avant=%-6s apres=%-6s  %s"
                      % (forme, av, ap_, "NE MORD PAS" if ap_ == av else "MORD"))
        fautes += f1

        print("\n[3] ORDRE-DEPENDANCE d'une passe (un seul process, deux fichiers)")
        ordre, f3 = etage_ordre(d)
        if ordre is None:
            muet = True
        else:
            for k in sorted(ordre):
                print("    %-38s -> %s" % (k, ordre[k]))
            print("    lecture : la forme A rend le verdict dependant de l'ORDRE des fichiers ;")
            print("    la forme B rend le meme verdict dans les deux ordres.")
        fautes += f3

    print("\n[2] CASCADE -- passer en forme B coute-t-il des modules charges ?")
    casc, f2 = etage_cascade(racine)
    if casc is None:
        muet = True
        print("    NON MESURE : %s" % ("; ".join(f2) or "?"))
        f2 = []
    else:
        for k in sorted(casc):
            print("    %-24s %d" % (k, casc[k]))
        print("    ecart NUL => B ne rouvre aucun cycle. Mais B ne RESOUT aucun cycle non plus :")
        print("    un differe PORTEUR le reste, quelle que soit sa forme. Deux problemes.")
    fautes += f2

    if muet and not fautes:
        print("\n[485-r1-r1] rc=%d -- PAS MESURE." % EX_PAS_MESURE)
        return EX_PAS_MESURE
    if fautes:
        print("\n  FAUTES :")
        for f in fautes:
            print("      %s" % f)
        print("\n[485-r1-r1] rc=%d -- ROUGE." % EX_ROUGE)
        return EX_ROUGE
    print("\n[485-r1-r1] rc=%d -- VERT." % EX_VERT)
    return EX_VERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
