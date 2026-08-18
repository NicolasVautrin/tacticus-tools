#!/usr/bin/env python
"""#485-r1-r4 / #485-r1-r2 -- le baril `engine.playbook` : RE-EXPORTS MORTS et EXHAUSTIVITE.

    python probe_485r1r4_baril_playbook.py

CE QU'IL GARDE, ET POURQUOI CES DEUX ETAGES-LA
----------------------------------------------
`engine/playbook/__init__.py` est un baril a REGISTRE : il importe ses enfants POUR L'EFFET DE
BORD (l'enfant s'inscrit au chargement). Le sweep #485-r1-r1 a donc exclu ce baril -- mais EN
BLOC, et c'est l'exclusion qui etait trop large : un baril a registre porte DEUX choses
independantes, et une seule justifie l'exclusion.

    LES ENREGISTREURS   `from . import loki_custom` -- l'import EST l'effet. Les retirer vide un
                        registre EN SILENCE (`.get(cle)` rend `None`, le moteur continue).
    LES RE-EXPORTS      `from .base import BasePlaybook, ...` -- du confort d'appel. Les retirer
                        ne vide RIEN ; ca casse seulement les lecteurs, qui sont DENOMBRABLES.

MESURE DU 2026-08-15 (`probe_485_imports_differes`, arbre TEMOIN a `62db139d`) -- le gain est
presque entierement du cote qui ne coute rien :

    baril tel quel                                    porteurs 277
    les 9 `from . import` (enregistreurs) retires     porteurs 273   (-4)
    les re-exports MORTS retires, enregistreurs GARDES porteurs 262   (-15)
    baril entierement vide                            porteurs 253   (-24)

Sur 34 symboles re-exportes, **4** sont consommes (`get_playbook_or_default` 25 sites,
`REGISTRY` 4 + 32 accces attributaires, `get_playbook` 12, `tile_utility` 2) ; les **30** autres
ne sont reclames NULLE PART. Les retirer vaut -15 porteurs pour **0** lecteur casse.

ETAGE [0] -- INVENTAIRE DES CINQ BARILS A REGISTRE (bloquant sur `engine.playbook` SEUL)
    Mesure du 2026-08-15, APRES le nettoyage de `playbook` :

        engine.playbook                          re-exports   4   MORTS   0   <- BLOQUANT
        engine.runner.abilities                  re-exports   4   MORTS   4
        engine.runner.abilities.loki             re-exports 106   MORTS  92
        engine.runner.operations.triggers.loki   re-exports  62   MORTS  51
        engine.utilities                         re-exports  32   MORTS  30

    **177 re-exports morts hors `playbook`** -- meme forme que les 29 qu'on vient de retirer ici.
    C'est le VRAI gisement de `#485-r1-r2`, qui visait au contraire les ENREGISTREURS
    (`charger_tout()`) : mesure sur arbre temoin, retirer les 9 enregistreurs de `playbook` vaut
    **-4** porteurs, retirer ses re-exports morts en vaut **-15**. Residu ouvert : `#485-r3`.
    ⚠ NON BLOQUANT hors de `PAQUET`, et c'est deliberе : ces quatre barils sont les foyers d'autres
    tranches, et un cliquet qui rougit sur ce qu'on n'a pas le droit de reparer se fait desarmer.

ETAGE [1] -- AUCUN RE-EXPORT MORT
    Tout symbole re-exporte par le baril doit avoir au moins un consommateur. C'est le cliquet de
    NON-RETOUR : sans lui, le baril se re-remplit au premier port qui ajoute son import << pour
    faire comme les autres >>, et le gisement se propage par IMITATION (mesure #485 : 32 des 52
    gratuits vivaient dans un module portant DEJA un differe legitime).
    ⚠ LES DEUX VOIES DE CONSOMMATION COMPTENT. `from engine.playbook import X` se recense par
    `ImportFrom` ; `import engine.playbook as PB` puis `PB.X` est ATTRIBUTAIRE et ne laisse
    AUCUNE trace dans un recensement d'imports. C'est l'angle mort qui a vide 4 couples sous les
    pieds de leurs lecteurs (#485-r1-r1). Ici il n'est pas theorique : `REGISTRY` est reclame
    **32 fois** par cette voie et **4** par l'autre -- un recenseur d'`ImportFrom` seul le
    verrait 8 fois moins consomme qu'il ne l'est, mais surtout `get_playbook` serait vu MORT
    alors qu'il a 12 lecteurs.

ETAGE [2] -- LE BARIL PEUPLE AUTANT QUE LE CHARGEMENT EXHAUSTIF
    `import engine.playbook` doit peupler les registres EXACTEMENT comme le ferait le chargement
    de tous les sous-modules du paquet. C'est le cran que #485-r1-r2 cherche, obtenu SANS changer
    le regime de chargement : l'invariant est DERIVE (on compare a l'exhaustif mesure dans un
    process frais), jamais une liste attestee qui se perimerait au prochain enregistreur ajoute.

    ⚠ C'est CE cran qui manque aujourd'hui, pas `charger_tout()`. La panne que #485-r1-r2 decrit
    -- << un registre vide NE LEVE PAS >> -- se produit des qu'un enregistreur cesse d'etre tire,
    quelle que soit la raison (retire du baril, renomme, deplace). Un `charger_tout()` explicite
    ne la supprime pas non plus : il la deplace sur l'appelant qui oublie de l'appeler.

TRI-ETAT
--------
    rc 0   VERT   -- aucun re-export mort, et le baril peuple autant que l'exhaustif
    rc 1   ROUGE  -- un re-export mort, ou un registre sous-peuple par le baril
    rc 2   PAS MESURE -- le paquet n'a pas pu etre charge, ou le recensement est vide. JAMAIS
                        rabattu sur un zero : un capteur muet ne rend pas un vert.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ICI = Path(__file__).resolve().parent
PAQUET = "engine.playbook"
RACINE_PAQUET = ICI / "engine" / "playbook"

#: Les barils a REGISTRE du depot (`migrate_485r1_barils_reexport.py inventaire`). L'etage [0] les
#: balaie TOUS et n'est BLOQUANT que sur `PAQUET` : les quatre autres sont des foyers d'autres
#: tranches, et un cliquet qui rougirait sur ce qu'on n'a pas le droit de reparer se ferait
#: desarmer. Leur compte est imprime a chaque run -- c'est ce qui rend le gisement dispatchable
#: (residu #485-r3).
BARILS_A_REGISTRE = ("engine.playbook", "engine.runner.abilities", "engine.runner.abilities.loki",
                     "engine.runner.operations.triggers.loki", "engine.utilities")

EX_VERT, EX_ROUGE, EX_PAS_MESURE = 0, 1, 2

#: `from __future__ import annotations` atterrit dans les `ImportFrom` du preambule sans etre un
#: re-export. Le NOMMER, plutot que de filtrer par une forme.
_NON_REEXPORTS = {"annotations"}


def _est_prive(nom: str) -> bool:
    """Un nom en `_` n'est PAS un re-export : c'est une dependance INTERNE du baril.

    ⚠ Ce n'est pas une echappatoire : renommer un symbole en `_x` le retire du contrat du baril,
    donc TOUT lecteur externe casse immediatement et bruyamment (`ImportError`). La convention
    Python fait ici le travail d'un cliquet -- contrairement a une liste blanche, qu'il faudrait
    maintenir et qui se perimerait en silence."""
    return nom.startswith("_")


def _racine(paquet: str) -> Path:
    return ICI / Path(*paquet.split("."))


def sous_modules(paquet: str = PAQUET) -> set[str]:
    """Les enfants directs du paquet -- ce que `from engine.playbook import X` resout SANS que
    le baril ait rien a re-exporter (Python importe le sous-module lui-meme)."""
    rac = _racine(paquet)
    out = {p.stem for p in rac.glob("*.py") if p.stem != "__init__"}
    out |= {d.name for d in rac.iterdir() if d.is_dir() and (d / "__init__.py").exists()}
    return out


def reexports(paquet: str = PAQUET) -> set[str]:
    """Les symboles que le baril EXPOSE et qui ne sont pas des sous-modules."""
    arbre = ast.parse((_racine(paquet) / "__init__.py").read_text(encoding="utf-8"))
    out: set[str] = set()
    for n in arbre.body:
        if isinstance(n, ast.ImportFrom):
            out |= {a.asname or a.name for a in n.names}
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.Assign):
            out |= {c.id for c in n.targets if isinstance(c, ast.Name)}
    return {s for s in (out - sous_modules(paquet) - _NON_REEXPORTS) if not _est_prive(s)}


def morts_du_baril(paquet: str) -> list[str]:
    """Les re-exports de `paquet` qu'AUCUN fichier ne reclame -- par les DEUX voies."""
    lus = consommateurs(paquet)
    return sorted(s for s in reexports(paquet) if not lus.get(s))


def _cible_absolue(mod: str, est_paquet: bool, n: ast.ImportFrom) -> str | None:
    """La cible ABSOLUE d'un `ImportFrom`, `level` compris.

    ⚠ SANS CETTE RESOLUTION, LE RECENSEUR DECLARE MORT CE QU'IL NE SAIT PAS LIRE, et c'est le
    vice symetrique de celui que `probe_270r1` a du corriger (un recenseur ne rend pas zero sur
    ce qu'il ne visite pas ; ici il rend MORT). L'ancienne forme exigeait `n.level == 0`, donc
    elle ne voyait AUCUN import relatif -- or c'est la forme dominante DANS `engine/**`, ou
    presque tout consommateur est un voisin de paquet. Mesure du 2026-08-18, avant vidange :
    **177** re-exports annonces morts sur les cinq barils, **141** reellement morts, soit
    **36 FAUX MORTS** -- 24 sur `engine.runner.abilities.loki` (reclames par
    `runner/abilities/handler.py`, qui ecrit `from .loki import (...)`) et 12 sur
    `engine.runner.operations.triggers.loki` (reclames par
    `runner/operations/triggers/dispatch/registry.py`). Agir sur le chiffre d'avant aurait
    retire des noms que `handler.py` importe : `ImportError` au chargement, donc
    `ABILITY_CLASSES` entier hors service.

    `level` compte les points ; pour un `__init__.py`, le paquet de reference est le paquet
    LUI-MEME, pas son parent -- d'ou `est_paquet`. Confondre les deux decalerait TOUTES les
    cibles relatives d'un cran, ce qui ne rate pas un cas : ca en invente d'autres.
    """
    if not n.level:
        return n.module
    bouts = mod.split(".")
    montee = n.level - 1 if est_paquet else n.level
    if len(bouts) < montee:
        return None
    base = bouts[:len(bouts) - montee] if montee else bouts
    return ".".join(base + ([n.module] if n.module else []))


def _nom_module(p: Path) -> str:
    """Nom de module absolu d'un fichier, `__init__.py` rendu comme SON paquet."""
    rel = p.relative_to(ICI).with_suffix("")
    bouts = list(rel.parts)
    if bouts and bouts[-1] == "__init__":
        bouts = bouts[:-1]
    return ".".join(bouts)


def consommateurs(paquet: str = PAQUET) -> dict[str, set[str]]:
    """`{symbole: {fichiers}}` -- LES DEUX VOIES, `ImportFrom` ET acces attributaire.

    L'`ImportFrom` est compte qu'il soit ABSOLU ou RELATIF (`_cible_absolue`)."""
    out: dict[str, set[str]] = defaultdict(set)
    for p in sorted(ICI.rglob("*.py")):
        if "__pycache__" in str(p) or p.resolve() == Path(__file__).resolve():
            continue
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        rel = str(p.relative_to(ICI))
        mod, est_paquet = _nom_module(p), p.name == "__init__.py"
        #: Le baril ne se reclame pas lui-meme : ses propres `from .enfant import X` visent ses
        #: ENFANTS, jamais lui -- mais l'`__init__.py` d'un SOUS-paquet, si.
        alias: set[str] = set()
        for n in ast.walk(arbre):
            if isinstance(n, ast.ImportFrom) and mod != paquet \
                    and _cible_absolue(mod, est_paquet, n) == paquet:
                for a in n.names:
                    out[a.name].add(rel)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    if a.name == paquet:
                        #: `import engine.playbook` SANS `as` lie le nom `engine` : tout
                        #: `engine.playbook.X` qui suit est un acces a DEUX niveaux, capte
                        #: ci-dessous par le `Attribute(Attribute(Name))`.
                        alias.add(a.asname or "engine")
        if not alias:
            continue
        for n in ast.walk(arbre):
            if not isinstance(n, ast.Attribute):
                continue
            base = n.value
            if isinstance(base, ast.Name) and base.id in alias and base.id != "engine":
                out[n.attr].add(rel)
            elif _chemin_pointe(base) == paquet:
                #: `import engine.playbook` SANS `as` : la chaine complete `engine.playbook.X` est
                #: une cascade d'`Attribute`. Elle est RECONSTRUITE, jamais testee sur le seul
                #: dernier segment -- sinon un paquet imbrique (`engine.runner.abilities.loki`)
                #: serait confondu avec son parent, et le compte des morts s'en trouverait fausse.
                out[n.attr].add(rel)
    return out


def _chemin_pointe(node: ast.AST) -> str | None:
    """`engine.runner.abilities.loki` pour le noeud AST de cette expression pointee, `None` sinon."""
    bouts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        bouts.append(cur.attr)
        cur = cur.value
    if not isinstance(cur, ast.Name):
        return None
    bouts.append(cur.id)
    return ".".join(reversed(bouts))


#: Les registres du paquet, `(module porteur, attribut)`. Chacun est mesure DANS SON PROPRE
#: process : voir `_registre`.
_REGISTRES = (
    ("engine.playbook.base", "REGISTRY"),
    ("engine.playbook.noncomparable", "PLAYBOOKS"),
    ("engine.playbook.psyker", "TRIGGERED_ATTACK_PLAYBOOKS"),
    ("engine.playbook.adjacent_unit_preference", "TRIGGERED_MOVE_PLAYBOOKS"),
)

#: ⚠ Gabarit a substitution TEXTUELLE (`str.replace`), PAS un `%`-format : le corps de la sonde
#: contient lui-meme des `%` (et en contiendrait a la moindre reecriture), et un `%`-format y
#: leve `TypeError: not enough arguments` -- panne rencontree a l'ecriture de ce probe.
_SONDE = r"""
import importlib, json, pkgutil, sys, types
sys.path.insert(0, __ICI__)
mode, porteur, attr = __MODE__, __PORTEUR__, __ATTR__
if mode.startswith("ampute:"):
    # CONTRE-EPREUVE : on NEUTRALISE un enregistreur en posant un module VIDE dans `sys.modules`
    # AVANT le chargement du baril. `from . import <x>` trouve alors le stub et n'execute jamais
    # l'inscription. C'est l'amputation la plus fidele a la panne reelle (un enregistreur qui
    # cesse d'etre tire), et elle ne demande aucune copie de l'arbre.
    _cible = mode.split(":", 1)[1]
    _stub = types.ModuleType(_cible)
    _stub.__spec__ = importlib.machinery.ModuleSpec(_cible, None)
    sys.modules[_cible] = _stub
m = importlib.import_module(porteur)
if mode == "exhaustif":
    import engine.playbook as PB
    for _, nom, _ in pkgutil.walk_packages(PB.__path__, PB.__name__ + "."):
        try:
            importlib.import_module(nom)
        except Exception:
            pass
v = getattr(m, attr, None)
print("EMPREINTE " + json.dumps(sorted(str(k) for k in v) if isinstance(v, dict) else None))
"""


def _registre(porteur: str, attr: str, mode: str) -> list | None:
    """Les cles du registre `porteur.attr`, mesurees dans un process FRAIS. `None` = PAS MESURE.

    ⚠ UN PROCESS PAR REGISTRE, ET C'EST LE POINT. Une premiere ecriture les mesurait TOUS dans
    le meme interpreteur : importer `engine.playbook.noncomparable` pour lire `PLAYBOOKS` y
    executait ses enfants, dont les `@register`, donc `base.REGISTRY` etait lu APRES avoir ete
    enrichi par un import que le mode << baril >> n'aurait jamais du faire. Le capteur mesurait
    alors sa propre sonde, et rendait le meme chiffre quoi qu'on retire du baril.

    ⚠ Le point d'ancrage est le MODULE PORTEUR, pas le baril -- et ce n'est pas un affaiblissement :
    `import engine.playbook.<x>` execute NECESSAIREMENT `engine/playbook/__init__.py` (Python
    charge chaque paquet ancetre). Le baril est donc toujours dans la mesure. Ce que ce choix
    ajoute, c'est le seul chemin par lequel un consommateur atteint reellement le registre."""
    code = (_SONDE.replace("__ICI__", repr(str(ICI))).replace("__MODE__", repr(mode))
            .replace("__PORTEUR__", repr(porteur)).replace("__ATTR__", repr(attr)))
    try:
        r = subprocess.run([sys.executable, "-c", code], cwd=str(ICI), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=300)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    for ligne in (r.stdout or "").splitlines():
        if ligne.startswith("EMPREINTE "):
            try:
                return json.loads(ligne[len("EMPREINTE "):])
            except json.JSONDecodeError:
                return None
    return None


def _empreinte(mode: str) -> dict | None:
    """`{`<porteur>.<attr>`: cles}` pour tous les registres, chacun dans son propre process."""
    out: dict[str, list] = {}
    for porteur, attr in _REGISTRES:
        cles = _registre(porteur, attr, mode)
        if cles is None:
            return None
        out[porteur.rsplit(".", 1)[1] + "." + attr] = cles
    return out


def _un_enregistreur() -> str | None:
    """Le nom PLEIN d'un `from . import <x>` du baril -- la cible de la contre-epreuve.

    DERIVE du fichier, jamais ecrit en dur : un enregistreur renomme ferait sinon porter la
    contre-epreuve sur un module inexistant, et elle passerait au vert sans rien amputer."""
    arbre = ast.parse((RACINE_PAQUET / "__init__.py").read_text(encoding="utf-8"))
    for n in arbre.body:
        if isinstance(n, ast.ImportFrom) and n.level == 1 and n.module is None:
            return PAQUET + "." + n.names[0].name
    return None


#: AUTO-TEST DU RESOLVEUR RELATIF -- `(module, est_paquet, level, module_cite, attendu)`.
#: Une erreur de UN CRAN sur `level` ne rate pas des consommateurs : elle en INVENTE d'autres,
#: donc elle rendrait des morts FAUX dans les deux sens sans qu'aucun compte n'ait l'air anormal.
#: Le seul controle qui la voit est un jeu de cas ECRIT, joue a chaque run.
_CAS_RESOLVEUR = (
    ("engine.runner.abilities.handler", False, 1, "loki", "engine.runner.abilities.loki"),
    ("engine.runner.abilities", True, 1, "loki", "engine.runner.abilities.loki"),
    ("engine.runner.abilities.genestealer", False, 2, "abilities.loki",
     "engine.runner.abilities.loki"),
    ("engine.runner.abilities.loki", True, 1, "summon", "engine.runner.abilities.loki.summon"),
    ("engine.playbook.base", False, 0, "engine.utilities", "engine.utilities"),
    ("engine.utilities.move", False, 1, None, "engine.utilities"),
    ("engine", True, 1, None, "engine"),
)


def _auto_test_resolveur() -> list[str]:
    """Rend les cas EN ECHEC. Un jeu vide serait un vert creux -- l'appelant l'asserte."""
    faux = []
    for mod, paquet, level, cite, attendu in _CAS_RESOLVEUR:
        n = ast.ImportFrom(module=cite, names=[], level=level)
        rendu = _cible_absolue(mod, paquet, n)
        if rendu != attendu:
            faux.append("%s (level %d, `%s`) -> %r, attendu %r"
                        % (mod, level, cite, rendu, attendu))
    return faux


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--detail", action="store_true", help="liste les consommateurs par symbole")
    a = ap.parse_args(argv)

    print("[485-r1-r4] baril `%s` -- re-exports morts et exhaustivite" % PAQUET)
    if not RACINE_PAQUET.is_dir():
        print("  paquet INTROUVABLE (%s)." % RACINE_PAQUET)
        return EX_PAS_MESURE

    if not _CAS_RESOLVEUR:
        print("  AUTO-TEST VIDE -- ce n'est pas un vert, c'est un capteur muet.")
        return EX_PAS_MESURE
    faux = _auto_test_resolveur()
    print("  auto-test du resolveur relatif : %d/%d cas, %d en echec"
          % (len(_CAS_RESOLVEUR) - len(faux), len(_CAS_RESOLVEUR), len(faux)))
    for f in faux:
        print("      ECHEC %s" % f)
    if faux:
        return EX_ROUGE

    #: ⚠ ETAGE [0] -- BLOQUANT SUR LES CINQ BARILS DEPUIS #485-r3 (2026-08-18), et le
    #: RENVERSEMENT est celui du droit de reparer, pas d'un avis. Il etait inventaire parce que
    #: les quatre barils hors `PAQUET` etaient les foyers d'autres tranches : rougir sur ce qu'on
    #: n'a pas le droit de reparer fait desarmer un cliquet (lecon de #486-r4 et de `probe_181`
    #: d'avant #430). Le gisement est ferme -- 149 re-exports morts retires, etage [0] a ZERO
    #: partout -- donc la meme prudence commande maintenant l'inverse : sans cran, il se
    #: rouvrirait par notre propre cadence, comme les 29 morts de `playbook` l'avaient fait.
    #: ⚠ CE CRAN NE MORD PAS SUR UN PORT NEUF, et c'est ce qui le rend tenable : une ability
    #: qui entre au baril est importee par `handler.py` (ou par `dispatch/registry.py`), donc
    #: elle est RECLAMEE. Seul un re-export que PERSONNE ne lit rougit -- exactement la faute.
    print("\n=== [0] RE-EXPORTS MORTS des barils a REGISTRE (BLOQUANT sur les 5) ===")
    total_hors, introuvables = 0, []
    for b in BARILS_A_REGISTRE:
        if not _racine(b).is_dir():
            #: Un baril INTROUVABLE n'est pas un zero : c'est un perimetre qui a bouge sous le
            #: cliquet. Il sort en PAS MESURE, jamais avale.
            introuvables.append(b)
            print("      %-42s INTROUVABLE (paquet deplace ou renomme)" % b)
            continue
        ex, mts = reexports(b), morts_du_baril(b)
        total_hors += 0 if b == PAQUET else len(mts)
        print("      %-42s re-exports %3d   MORTS %3d%s"
              % (b, len(ex), len(mts), "   <- " + ", ".join(mts) if mts else ""))
    if introuvables:
        print("      PAS MESURE : %d baril(s) introuvable(s) -- le zero des autres ne couvre"
              % len(introuvables))
        print("      pas ce perimetre-la. Mettre `BARILS_A_REGISTRE` a jour (residu #485-r7).")
        return EX_PAS_MESURE
    print("      %d re-export(s) mort(s) hors `%s`." % (total_hors, PAQUET))
    print("      Ce compte a ete SUREVALUE de 36 tant que le recenseur exigeait `level == 0` :")
    print("      il ne voyait AUCUN import relatif, donc il declarait morts des symboles que")
    print("      `runner/abilities/handler.py` et `triggers/dispatch/registry.py` importent")
    print("      (#485-r3, 2026-08-18). Le gisement REEL etait 141, pas 177.")
    if total_hors:
        print("      ROUGE : un re-export que PERSONNE ne reclame, dans un baril a REGISTRE.")
        print("      Le retirer se fait par `migrate_485r1_barils_reexport.py vider")
        print("      --inclure-registres --baril <le baril> --appliquer` : il PROTEGE les imports")
        print("      chargeurs de registre et les ENREGISTREURS, et convertit a la forme")
        print("      `from . import <enfant>` ceux dont tous les noms meurent.")
        return EX_ROUGE

    exposes = reexports()
    if not exposes:
        print("  le baril n'expose AUCUN symbole -- etage [1] sans objet, etage [2] joue seul.")
    lus = consommateurs()
    morts = sorted(s for s in exposes if not lus.get(s))

    print("\n=== [1] RE-EXPORTS MORTS ===")
    print("  sous-modules du paquet : %d   symboles re-exportes : %d"
          % (len(sous_modules()), len(exposes)))
    for s in sorted(exposes):
        f = lus.get(s, set())
        etat = "MORT" if not f else "%d fichier(s)" % len(f)
        print("      %-42s %s" % (s, etat))
        if a.detail and f:
            for x in sorted(f)[:6]:
                print("           %s" % x)
    if morts:
        print("\n  %d re-export(s) MORT(s) : %s" % (len(morts), ", ".join(morts)))
        print("  Un re-export que personne ne lit alourdit la cascade du paquet POUR RIEN :")
        print("  il fait tirer son module au chargement, donc il ferme des cycles que d'autres")
        print("  paient ensuite en imports DIFFERES. Retire-le du baril.")
    else:
        print("\n  0 re-export mort : tout ce que le baril expose est reclame.")

    print("\n=== [2] LE BARIL PEUPLE-T-IL AUTANT QUE L'EXHAUSTIF ? ===")
    baril, exhaustif = _empreinte("baril"), _empreinte("exhaustif")
    if baril is None or exhaustif is None:
        print("  PAS MESURE : le paquet n'a pas pu etre charge dans un process frais.")
        print("  Un capteur muet ne rend pas un vert -- rc=%d." % EX_PAS_MESURE)
        return EX_PAS_MESURE
    manques: list[tuple[str, list[str]]] = []
    for nom in sorted(set(baril) | set(exhaustif)):
        av, ap = set(baril.get(nom, ())), set(exhaustif.get(nom, ()))
        perdu = sorted(ap - av)
        print("      %-46s baril %4d   exhaustif %4d%s"
              % (nom, len(av), len(ap), "   MANQUE %d" % len(perdu) if perdu else ""))
        if perdu:
            manques.append((nom, perdu))
    if manques:
        print("\n  SOUS-PEUPLEMENT -- le baril ne tire pas tous ses enregistreurs :")
        for nom, perdu in manques:
            print("      %s : %s%s" % (nom, ", ".join(perdu[:8]),
                                       " ..." if len(perdu) > 8 else ""))
        print("  C'est la panne SILENCIEUSE de #485-r1-r2 : un registre incomplet ne LEVE pas,")
        print("  `.get(cle)` rend `None` et le moteur continue avec le playbook par defaut.")
    else:
        print("\n  0 sous-peuplement : le chargement du baril est EXHAUSTIF.")

    #: ⚠ SANS CECI, [2] SERAIT UN INVENTAIRE DEGUISE EN GARDE. Un etage qui rend « 0 » parce que
    #: le depot est sain et un etage qui rend « 0 » parce qu'il ne sait pas voir sont
    #: INDISTINGUABLES depuis leur sortie -- c'est exactement le vice de `probe_181`, qui rendait
    #: `0` inconditionnellement tout en se lisant comme un garde-fou. On AMPUTE donc un
    #: enregistreur pour de vrai, et on exige que la comparaison le VOIE.
    print("\n=== [2b] CONTRE-EPREUVE -- l'etage [2] sait-il seulement rougir ? ===")
    cible = _un_enregistreur()
    if cible is None:
        print("  PAS MESURE : aucun enregistreur `from . import <x>` trouve dans le baril.")
        return EX_PAS_MESURE
    ampute = _empreinte("ampute:" + cible)
    if ampute is None:
        print("  PAS MESURE : le chargement ampute n'a pas abouti.")
        return EX_PAS_MESURE
    ref, vu = len(baril.get("base.REGISTRY", ())), len(ampute.get("base.REGISTRY", ()))
    print("      enregistreur neutralise : %s" % cible)
    print("      base.REGISTRY  normal %d   ampute %d   ecart %d" % (ref, vu, ref - vu))
    if vu >= ref:
        print("  *** LE CAPTEUR NE MORD PAS *** : amputer un enregistreur ne change RIEN au")
        print("  registre mesure. Le « 0 sous-peuplement » ci-dessus ne prouve donc rien.")
        print("\n[485-r1-r4] rc=%d -- ROUGE (contre-epreuve MORTE)." % EX_ROUGE)
        return EX_ROUGE
    print("      -> le capteur MORD : un enregistreur perdu se voit.")

    if morts or manques:
        print("\n[485-r1-r4] rc=%d -- ROUGE (%d re-export(s) mort(s), %d registre(s) "
              "sous-peuple(s))." % (EX_ROUGE, len(morts), len(manques)))
        return EX_ROUGE
    print("\n[485-r1-r4] rc=%d -- VERT." % EX_VERT)
    return EX_VERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
