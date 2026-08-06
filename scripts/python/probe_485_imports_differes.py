#!/usr/bin/env python
"""#485 -- CLIQUET des imports DIFFERES vers `engine.*` ecrits DANS `engine/**`.

CE QU'IL GARDE, ET CE QU'IL NE GARDE PAS
----------------------------------------
Il refuse tout NOUVEAU differe GRATUIT. Il ne pretend PAS que le graphe d'imports est sain :
mesure du 2026-08-06, les 430/430 modules qui s'importent seuls le sont **grace a** 262 differes
PORTEURS. Un cliquet qui se lirait << aucun cycle >> serait un faux certificat.

    PORTEUR   hisser l'import FERMERAIT un cycle -> legitime, il RESTE
    GRATUIT   hissable, aucun cycle              -> scorie, il DOIT partir

⚠⚠ HISSER, OUI -- MAIS PAS DANS N'IMPORTE QUELLE FORME, ET CETTE LIGNE-CI A PRESCRIT LA MAUVAISE.
Elle disait << il DOIT partir >> sans dire OU il arrive. Trois formes, MESUREES le 2026-08-06 sous
`monkeypatch.setattr("src_x.foo", stub)` :

    A  from X import foo   (au niveau module)     NE MORD PAS   <- ce que << hisser >> produit par defaut
    B  import X ; X.foo()                         MORD
    C  from X import foo   (dans la fonction)     MORD          <- le differe qu'on retire

    avant patch  A=VRAI  B=VRAI    C=VRAI
    apres patch  A=VRAI  B=PATCHE  C=PATCHE

**HISSER EN FORME A FAIT PASSER DE C A A, c'est-a-dire de MORD a NE MORD PAS.** Les differes
rendaient le patch robuste par accident : la forme C est re-executee a chaque appel, donc elle relit
l'attribut du module. C'est TOUTE l'explication des 25 sites `PERD_LA_MORSURE` de #485-r1 -- ce ne
sont pas des tests mal ecrits, ce sont des tests prives d'une propriete que le hissage leur retire.

⚠ ET LE VICE NE S'ARRETE PAS AU PATCH : IL REND LE VERDICT ORDRE-DEPENDANT. Un differe protege son
propre site, mais la CASCADE qu'il declenche cree des bindings de forme A dans les modules
traverses, GELES des le premier chargement pour toute la session pytest :

    ORDRE 1  un test charge SANS patch, puis un autre patche  ->  patch IGNORE
    ORDRE 2  le test qui patche passe EN PREMIER              ->  patch MORD

Le meme test rend donc un verdict different selon `-k`, `--deselect`, un fichier ajoute avant dans
la passe, ou la redistribution xdist. La forme B eteint les DEUX couches (forme et ordre) : un
binding de MODULE n'est jamais gele, l'attribut est resolu a l'appel. La forme A n'en eteint aucune.

⚠ La cascade d'`__init__` est IDENTIQUE entre A et B (`from pkg.sub import mod` charge exactement
`pkg`, `pkg.sub`, `pkg.sub.mod`). B ne coute donc RIEN en chargement et ne rouvre aucun cycle -- son
seul cout est au SITE D'APPEL (`foo()` -> `X.foo()`).
⚠ B ne resout PAS les cycles : un PORTEUR reste un porteur dans les deux formes. Monkeypatch
fragile et cycle d'import sont deux problemes distincts qui se ressemblent.

POURQUOI UN CLIQUET ET PAS UNE REGLE ECRITE
-------------------------------------------
`CLAUDE.md` porte la doctrine depuis le 2026-08-06, mais la prose n'arrete pas un comportement --
un en-tete se lit APRES la decision (mesure : `probe_457`, de-oblige la veille et joue quand meme).
Et le gisement se propage par IMITATION, mesuree : **32 des 52 gratuits (62 %)** vivent dans un
module qui porte DEJA un differe legitime. Un agent ouvre `abilities/targeting.py`, y voit
4 porteurs, et ecrit le 5e sans se poser la question. Seul un REFUS executable coupe la boucle.

DEUX CRITERES, ET LEUR UNION -- n'en avoir qu'UN l'a rendu VERT SUR UN DEPOT ROUGE
----------------------------------------------------------------------------------
    CYCLE       charger `X` SEUL dans un process FRAIS : `M` atterrit-il dans `sys.modules` ?
                Oui ⇒ l'arete fermerait une boucle ⇒ PORTEUR. Non ⇒ GRATUIT.
                (Calibrage : 0 indecis sur 314. Ne demande AUCUNE reecriture.)
    REDONDANCE  la cible est-elle DEJA importee au niveau module dans le PREAMBULE du MEME
                fichier ? Oui ⇒ GRATUIT, **cycle ou pas**. Critere IMPORTE de
                `probe_270r4r2r2_tri_differes.gratuits` -- foyer unique, jamais recopie.

⚠ LE SECOND NE SE DEDUIT PAS DU PREMIER, et c'est ce qui a manque. Quand le preambule importe
deja la cible, charger celle-ci tire souvent l'appelant : le critere CYCLE repond << PORTEUR >>
et TOLERE une instruction purement redondante. Mesure du 2026-08-06 : la PR #743 a hisse `Const`
et les selecteurs au niveau module d'`abilities/targeting.py` **en citant #485 dans son
commentaire**, a laisse les copies deferees derriere, et ce probe est reste VERT pendant que
`tests/engine/test_270r4r2r2_differes_offline.py::etage1` rougissait sur 6 sites. Un cliquet qui
RASSURE la ou un autre ROUGIT est pire qu'absent.

⚠ ON NE CLASSE PAS SUR LE GRAPHE STATIQUE, et c'est deliberе. Le graphe des imports DECLARES est
aveugle aux boucles passant par un paquet ANCETRE, que Python execute quoi qu'on ecrive : mesure
anterieure, `dsl.base -> engine.entities (init) -> ... -> dsl.base` leve un `ImportError` REEL
sans apparaitre dans aucun SCC. Le process frais, lui, mesure ce que Python FAIT.

TRI-ETAT
--------
    rc 0   VERT   -- aucun gratuit hors base, aucune declaration morte
    rc 1   ROUGE  -- gratuit neuf, ou declaration perimee
    rc 2   PAS MESURE -- le recensement ou la classification n'a pas abouti. JAMAIS un verdict
                        sur le depot : un capteur muet ne rend pas un zero.
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

#: Racine RESOLUE DEPUIS `__file__`, jamais depuis le CWD. `probe_457` a rendu un FAUX `FAIL`
#: pour avoir lu son perimetre depuis le repertoire courant (#457-r7) ; on supprime la question.
ICI = Path(__file__).resolve().parent
ENGINE = ICI / "engine"
BASE = ICI.parent / "ratchets-485-differes-attestes.json"

EX_VERT, EX_ROUGE, EX_PAS_MESURE = 0, 1, 2

#: Heuristique de << raison ecrite >> : mots-cles cherches dans les 4 lignes qui PRECEDENT
#: l'import. Volontairement grossiere, et c'est pourquoi l'etage 3 est INFORMATIF : un mot-cle
#: absent ne prouve pas qu'aucune raison n'est donnee, il dit qu'aucune n'est REPERABLE.
_MOTS_RAISON = ("cycle", "circulaire", "lazy", "tardif", "differe", "import retarde")


def _nom_module(p: Path) -> str:
    parts = list(p.relative_to(ICI).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resoudre(mod: str, node: ast.AST) -> list[str]:
    """Rend les modules ABSOLUS `engine.*` vises par `node`, [] sinon."""
    if isinstance(node, ast.Import):
        return [a.name for a in node.names if a.name.split(".")[0] == "engine"]
    base = mod.split(".")
    if node.level:
        pkg = base if (ICI / Path(*base)).is_dir() else base[:-1]
        pkg = pkg[: len(pkg) - (node.level - 1)] if node.level > 1 else pkg
        cible = ".".join(pkg + ([node.module] if node.module else []))
    else:
        cible = node.module or ""
    return [cible] if cible.split(".")[0] == "engine" else []


def recenser() -> list[tuple[str, str, int, bool]]:
    """Tout import `engine.*` ecrit DANS un corps de fonction de `engine/**`."""
    out: list[tuple[str, str, int, bool]] = []
    for p in sorted(ENGINE.rglob("*.py")):
        if "__pycache__" in str(p):
            continue
        mod = _nom_module(p)
        src = p.read_text(encoding="utf-8")
        lignes = src.splitlines()
        arbre = ast.parse(src)
        for fn in [n for n in ast.walk(arbre)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for node in ast.walk(fn):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                ctx = " ".join(lignes[max(0, node.lineno - 4):node.lineno]).lower()
                raison = any(m in ctx for m in _MOTS_RAISON)
                for cible in _resoudre(mod, node):
                    out.append((mod, cible, node.lineno, raison))
    return out


def _atteints(cible: str) -> set[str] | None:
    """Modules `engine.*` charges par `import <cible>` dans un process FRAIS. `None` = echec."""
    code = ("import sys, %s\n"
            "print('\\n'.join(m for m in sys.modules if m.startswith('engine')))" % cible)
    try:
        r = subprocess.run([sys.executable, "-c", code], cwd=str(ICI), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0 or r.stdout is None:
        return None
    return set(r.stdout.split())


def _redondants() -> set[tuple[str, int]] | None:
    """Les (module, ligne) dont la cible est DEJA importee au PREAMBULE du meme fichier.

    ⚠ FOYER IMPORTE, JAMAIS RECOPIE. Le critere vit dans `probe_270r4r2r2_tri_differes.gratuits`,
    et son cliquet est `tests/engine/test_270r4r2r2_differes_offline.py::etage1`. Deux
    implementations jumelles du meme predicat divergeraient -- c'est la lecon de #332, et de
    #390 qui vient de ramener le triplet de nav a un seul corps.
    """
    try:
        import probe_270r4r2r2_tri_differes as TR
    except ImportError:
        return None
    try:
        return {(mod, ligne) for mod, ligne, _ in TR.gratuits(ENGINE)}
    except (OSError, ValueError):
        return None


def classer(differes) -> tuple[list, list] | None:
    """(porteurs, gratuits). `None` si une seule cible n'a pas pu etre chargee.

    UN DIFFERE EST GRATUIT PAR L'UNION DE DEUX CRITERES INDEPENDANTS, et n'en avoir qu'un a
    rendu ce probe VERT sur un depot ROUGE (mesure du 2026-08-06, PR #743 puis #741) :

        CYCLE       charger la cible SEULE dans un process frais -- le module appelant
                    atterrit-il dans `sys.modules` ? Non ⇒ hisser ne ferme aucune boucle.
        REDONDANCE  la cible est-elle DEJA importee au niveau module dans le PREAMBULE du
                    MEME fichier ? Oui ⇒ la copie deferee ne sert a rien, CYCLE OU PAS.

    Le second ne se deduit PAS du premier. Quand le preambule importe deja la cible, charger
    celle-ci tire souvent l'appelant -- le critere CYCLE repond donc << PORTEUR >> et TOLERE une
    instruction purement redondante. C'est exactement ce qui est arrive : #743 a hisse `Const`
    et les selecteurs au niveau module de `abilities/targeting.py` **en citant #485**, a laisse
    les copies deferees derriere, et ce probe est reste vert pendant que
    `test_270r4r2r2::etage1` rougissait.

    ⚠ TRI-ETAT PRESERVE : si le critere REDONDANCE n'est pas mesurable (foyer introuvable), on
    ne le rabat PAS sur un ensemble vide -- ce serait fabriquer un zero. On rend `None`, donc
    `rc 2 = PAS MESURE`, parce qu'un verdict rendu sur un seul des deux criteres est
    precisement le faux vert qu'on repare ici.
    """
    cibles = sorted({c for _, c, _, _ in differes})
    with ThreadPoolExecutor(max_workers=16) as ex:
        table = dict(zip(cibles, ex.map(_atteints, cibles)))
    if any(v is None for v in table.values()):
        muettes = sorted(k for k, v in table.items() if v is None)
        print("  cible(s) NON CHARGEABLE(s), classification impossible : %s"
              % ", ".join(muettes[:6]))
        return None
    redondants = _redondants()
    if redondants is None:
        print("  critere REDONDANCE NON MESURABLE (`probe_270r4r2r2_tri_differes` muet) --")
        print("  un verdict sur le seul critere CYCLE est le faux vert que ce probe repare.")
        return None
    porteurs, gratuits = [], []
    for mod, cible, ligne, raison in differes:
        cycle_gratuit = mod not in table[cible]
        if cycle_gratuit or (mod, ligne) in redondants:
            gratuits.append((mod, cible, ligne, raison))
        else:
            porteurs.append((mod, cible, ligne, raison))
    return porteurs, gratuits


def _compter(entrees) -> dict[str, dict[str, int]]:
    """Cle (module, cible) -> compte. PAS la ligne : elle bouge a chaque edition voisine."""
    d: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for mod, cible, _, _ in entrees:
        d[mod][cible] += 1
    return {m: dict(v) for m, v in sorted(d.items())}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ecrire", action="store_true",
                    help="REGENERE la base attestee depuis la mesure courante. A n'employer "
                         "qu'en connaissance de cause : la base est VERSIONNEE et ne doit que "
                         "DECROITRE.")
    a = ap.parse_args(argv)

    print("[485] imports DIFFERES vers `engine.*` ecrits dans `engine/**`")
    differes = recenser()
    if not differes:
        print("  recensement VIDE -- ce n'est pas un zero, c'est un capteur muet.")
        print("[485] rc=%d -- PAS MESURE." % EX_PAS_MESURE)
        return EX_PAS_MESURE

    classe = classer(differes)
    if classe is None:
        print("[485] rc=%d -- PAS MESURE : la classification n'a pas abouti." % EX_PAS_MESURE)
        return EX_PAS_MESURE
    porteurs, gratuits = classe

    print("  recenses : %d   PORTEURS : %d   GRATUITS : %d"
          % (len(differes), len(porteurs), len(gratuits)))

    courant = _compter(gratuits)
    if a.ecrire:
        BASE.write_text(json.dumps(courant, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("  base REGENEREE : %s (%d module(s), %d entree(s))"
              % (BASE.name, len(courant), len(gratuits)))
        return EX_VERT

    if not BASE.exists():
        print("  base attestee ABSENTE (%s) -- rien a confronter." % BASE.name)
        print("[485] rc=%d -- PAS MESURE." % EX_PAS_MESURE)
        return EX_PAS_MESURE
    atteste = json.loads(BASE.read_text(encoding="utf-8"))

    neufs, perimes = [], []
    for mod, cibles in courant.items():
        for cible, n in cibles.items():
            ref = atteste.get(mod, {}).get(cible, 0)
            if n > ref:
                neufs.append((mod, cible, n - ref))
    for mod, cibles in atteste.items():
        for cible, n in cibles.items():
            vu = courant.get(mod, {}).get(cible, 0)
            if vu < n:
                perimes.append((mod, cible, n - vu))

    if neufs:
        print("\n  [1] GRATUITS NEUFS -- hors base attestee :")
        for mod, cible, n in sorted(neufs):
            print("      %-52s -> %-38s x%d" % (mod, cible, n))
        print("      Un differe GRATUIT est HISSABLE : aucun cycle ne le justifie. Hisse-le au")
        print("      niveau module. Si tu crois qu'un cycle l'impose, la mesure dit le contraire")
        print("      -- re-joue `python probe_485_imports_differes.py` apres avoir hisse.")

    if perimes:
        print("\n  [2] DECLARATIONS PERIMEES -- la base attend plus que ce qui existe :")
        for mod, cible, n in sorted(perimes):
            print("      %-52s -> %-38s -%d" % (mod, cible, n))
        print("      C'est le cas NORMAL apres une reparation : retire ces entrees de %s"
              % BASE.name)
        print("      DANS LE MEME COMMIT. Une base qui ne decroit pas n'est plus un cliquet.")

    sans_raison = [x for x in porteurs if not x[3]]
    print("\n  [3] INFORMATIF -- porteurs sans raison REPERABLE : %d / %d"
          % (len(sans_raison), len(porteurs)))
    print("      Non bloquant : la detection est une heuristique par mots-cles, un manque ne")
    print("      prouve pas qu'aucune raison n'est donnee. Mais c'est par eux que l'imitation")
    print("      se propage -- un lecteur ne distingue pas << structurel >> de << scorie >>.")

    if neufs or perimes:
        print("\n[485] rc=%d -- ROUGE (%d neuf(s), %d perime(s))."
              % (EX_ROUGE, len(neufs), len(perimes)))
        return EX_ROUGE
    print("\n[485] rc=%d -- VERT : aucun gratuit hors base, aucune declaration morte." % EX_VERT)
    print("      Ce vert dit << aucun NOUVEAU cycle contourne >>, PAS << aucun cycle >>.")
    return EX_VERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
