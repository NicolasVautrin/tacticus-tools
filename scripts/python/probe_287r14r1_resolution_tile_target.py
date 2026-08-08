#!/usr/bin/env python3
"""#287-r14-r1 -- le regime TUILE-en-direct est MORT ; l'invariant qui vit est << toute
`TargetIsTile` resout en tete de son `execute_behaviour` >>, et il n'etait pas garde.

CE QUE LE RESIDU DEMANDAIT, ET CE QUE LA MESURE A RENVERSE
------------------------------------------------------------
`#287-r14-r1` proposait de porter la resolution de cible sur la tete des **73** abilities qui
divergent entre regime UNITE et regime TUILE par appel DIRECT a `execute_behaviour` -- en
notant que ce regime n'est << emprunte par aucun appelant reel >>. La fiche demandait de le
VERIFIER avant de porter 73 sites. Verifie, et c'est vrai :

  * **214** appels directs a `execute_behaviour` (hors `AbilityHandler`) dans l'arbre ;
  * **10** d'entre eux passent une TUILE -- et les **10** visent une ability `TargetIsTile`,
    donc l'un des 23 sites DEJA pourvus. Les 3 attribuables statiquement sont
    `DaemonicOrdnance` (1148), `DutyEternal` (1158), `SporeMineLauncher` (1145) ; les 7 autres
    viennent des probes #287-r12, qui balaient TOUT le registre avec une tuile parce que
    mesurer ce regime est leur objet meme ;
  * **0** appelant passe une tuile a une ability unit-target.

Porter 73 tetes reviendrait donc a recopier 73 fois une ligne INERTE, sur un regime qu'aucun
consommateur n'emprunte -- et a s'en donner la maintenance. Ce n'est pas un port, c'est une
dette. Le verdict de ce probe est : **branche morte, NON PORTEE**.

L'INVARIANT QUI, LUI, EST VIVANT -- ET QUE NOTRE PROPRE CADENCE ROUVRE
-----------------------------------------------------------------------
La resolution n'a pas ete posee sur les 23 tile-target par hasard : c'est exactement la ou
elle MORD, parce que le regime symetrique -- passer une UNITE a une ability tile-target -- EST
emprunte (`test_valkyrie_strike_migration_live` le grave). La ventilation est nette et
DERIVEE, jamais saisie :

    TargetIsTile        : 23, dont 23 resolvent      (0 manquante)
    non-tile            : 106, dont 0 resolvent      (0 surplus)

C'est la meme forme que `TARGETING_OPTIONS` et `ABILITY_ATTACK_TYPE` : un zero que **notre
propre cadence de portage** rouvre, une ability tile-target neuve entrant au registre sans sa
ligne de resolution. Aucune garde ne le voyait. La degradation serait PERMISSIVE et muette --
l'ability opererait sur l'UNITE la ou le natif lui donne sa TUILE.

    python probe_287r14r1_resolution_tile_target.py            # ventilation
    python probe_287r14r1_resolution_tile_target.py --cliquet  # rc 1 si une tile-target manque

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import ast
import inspect
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PYDIR = REPO / "scripts" / "python"
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
#:
#: Le registre et les masques vivent sous `engine/runner/abilities/` -- toute entree neuve, et
#: tout masque re-lu, peuvent basculer le verdict. L'etage 2 lit en plus les APPELANTS directs,
#: qui sont des probes et des tests. `build: False` : le critere lit le PORT (masques deja
#: RE-lus et inscrits), jamais le binaire.
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/abilities/**/*.py",
                "scripts/python/probe_*.py",
                "scripts/python/tests/**/*.py"),
    "build": False,
    "toujours": False,
    "raison": "Une ability qui entre au registre avec le bit `TargetIsTile`, ou un masque "
              "`TARGETING_OPTIONS` re-lu, rouvre le gisement ; et l'etage 2 mesure les "
              "appelants directs, qui vivent dans les probes et les tests.",
}

#: Les mots par lesquels un appelant NOMME une tuile. C'est une heuristique, et elle est
#: ANNONCEE : elle sert a TROUVER les sites a examiner, jamais a en declarer l'absence --
#: l'etage 2 imprime separement les sites qu'il n'a pas su attribuer.
MOTS_TUILE = ("tile", "tuile", "hex")


def _corps(fn) -> ast.AST | None:
    try:
        src = inspect.getsource(fn)
    except (OSError, TypeError):
        return None
    try:
        return ast.parse(textwrap.dedent(src))
    except (SyntaxError, IndentationError):
        return None


def resout_sa_cible(cls) -> str:
    """'OUI' | 'NON' | 'HERITE' | 'ILLISIBLE' -- le corps appelle-t-il `get_actual_target` ?

    Lu par AST sur la source de la methode : un `grep` sur le fichier attribuerait a une classe
    la ligne de sa voisine (les modules d'abilities en portent jusqu'a 40).
    """
    fn = cls.__dict__.get("execute_behaviour")
    if fn is None:
        return "HERITE"
    t = _corps(fn)
    if t is None:
        return "ILLISIBLE"
    for n in ast.walk(t):
        if isinstance(n, ast.Call):
            f = n.func
            nom = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if nom in ("get_actual_target", "actual_target"):
                return "OUI"
    return "NON"


def ventiler():
    """(tile, autres) = [(id, nom, verdict)] -- DERIVE du registre, jamais d'une liste saisie."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting_rule import TargetingRule as TR
    tile, autres, sans_masque = [], [], []
    for aid, cls in sorted(ABILITY_CLASSES.items()):
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        if opts is None:
            # `TARGETING_OPTIONS is None` = masque non RE-lu. Ce n'est pas << pas tile-target >>,
            # c'est << pas mesure >> : le compter comme non-tile fabriquerait un zero.
            sans_masque.append((aid, cls.__name__, resout_sa_cible(cls)))
            continue
        cible = tile if int(opts.rules) & int(TR.TargetIsTile) else autres
        cible.append((aid, cls.__name__, resout_sa_cible(cls)))
    return tile, autres, sans_masque


# ------------------------------------------------------- ETAGE 2 : les APPELANTS directs
def _nom_classe_appelee(node: ast.Call) -> str | None:
    """`XAbility().execute_behaviour(...)` -> 'XAbility'. `cls().execute_behaviour(...)` -> None.

    L'attribution est EXACTE quand elle rend un nom (la classe est ecrite au site) et ABSENTE
    sinon -- jamais devinee. Les sites non attribues sont IMPRIMES : un recenseur ne peut pas
    rendre zero sur ce qu'il ne visite pas.
    """
    f = node.func
    if not isinstance(f, ast.Attribute):
        return None
    b = f.value
    if isinstance(b, ast.Call) and isinstance(b.func, ast.Name):
        nom = b.func.id
        return nom if nom.endswith("Ability") else None
    return None


def appels_directs() -> tuple[list, list]:
    """([(rel, ligne, classe, cible)] attribues, [(rel, ligne, cible)] non attribues).

    Perimetre : tout `.py` versionne, moins `AbilityHandler` -- qui est la voie NATIVE et
    resout deja, donc n'est pas un << appel direct >>.
    """
    r = subprocess.run(["git", "ls-files", "-z"], cwd=str(REPO),
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise SystemExit("git ls-files a echoue : %s" % (r.stderr or "").strip())
    attribues, non_attribues = [], []
    for rel in [p for p in r.stdout.split("\0") if p.endswith(".py")]:
        if rel.endswith("engine/runner/abilities/handler.py"):
            continue
        try:
            t = ast.parse((REPO / rel).read_text(encoding="utf-8", errors="replace"),
                          filename=rel)
        except SyntaxError:
            continue
        for n in ast.walk(t):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            nom = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if nom != "execute_behaviour" or len(n.args) < 3:
                continue
            try:
                cible = ast.unparse(n.args[2])
            except Exception:                                       # noqa: BLE001
                cible = "<?>"
            klass = _nom_classe_appelee(n)
            if klass:
                attribues.append((rel, n.lineno, klass, cible))
            else:
                non_attribues.append((rel, n.lineno, cible))
    return attribues, non_attribues


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cliquet", action="store_true",
                    help="rc 1 si une ability `TargetIsTile` ne resout pas sa cible")
    ap.add_argument("--verbeux", action="store_true")
    args = ap.parse_args()

    tile, autres, sans_masque = ventiler()

    print("=== (1) L'INVARIANT : toute `TargetIsTile` resout en tete d'`execute_behaviour` ===")
    print("registre                 : %d entrees" % (len(tile) + len(autres) + len(sans_masque)))
    print("  TargetIsTile           : %d" % len(tile))
    print("  non-tile               : %d" % len(autres))
    print("  masque NON RE-LU       : %d  (pas mesure -- jamais compte comme non-tile)"
          % len(sans_masque))
    manquantes = [t for t in tile if t[2] != "OUI"]
    surplus = [a for a in autres if a[2] == "OUI"]
    print("")
    print("  tile-target qui RESOLVENT       : %d / %d" % (len(tile) - len(manquantes), len(tile)))
    print("  tile-target qui NE resolvent PAS: %d" % len(manquantes))
    print("  non-tile qui resolvent (surplus): %d" % len(surplus))
    if args.verbeux:
        for aid, nom, v in tile:
            print("     %-6s %-44s %s" % (aid, nom, v))
    for aid, nom, v in manquantes:
        print("     !! %-6s %-44s %s" % (aid, nom, v))
    for aid, nom, v in surplus:
        print("     ?  %-6s %-44s resout alors qu'elle n'est pas tile-target" % (aid, nom))
    print("")

    print("=== (2) LE REGIME TUILE-EN-DIRECT : est-il emprunte ? ===")
    attribues, non_attribues = appels_directs()
    tile_ids = {nom for _a, nom, _v in tile}
    par_tuile_attr = [(r, l, k, c) for r, l, k, c in attribues
                      if any(m in c for m in MOTS_TUILE)]
    par_tuile_anon = [(r, l, c) for r, l, c in non_attribues
                      if any(m in c for m in MOTS_TUILE)]
    hors_contrat = [(r, l, k, c) for r, l, k, c in par_tuile_attr if k not in tile_ids]
    print("appels DIRECTS a `execute_behaviour` (hors handler) : %d"
          % (len(attribues) + len(non_attribues)))
    print("  attribues a une classe ecrite au site : %d" % len(attribues))
    print("  NON attribues (classe portee par une variable) : %d" % len(non_attribues))
    print("dont l'expression de cible NOMME une tuile : %d attribue(s), %d non attribue(s)"
          % (len(par_tuile_attr), len(par_tuile_anon)))
    for rel, ln, k, c in sorted(par_tuile_attr):
        etat = "tile-target (regime NATUREL)" if k in tile_ids else "!! UNIT-TARGET"
        print("     %s:%d  %s(%s) -- %s" % (rel, ln, k, c, etat))
    for rel, ln, c in sorted(par_tuile_anon):
        print("     %s:%d  <classe non ecrite au site>(%s)" % (rel, ln, c))
    print("")
    print("  VERDICT : %s" % (
        "regime MORT -- aucun appelant ne passe une tuile a une ability unit-target"
        if not hors_contrat else
        "regime VIVANT -- %d site(s) hors contrat, la tete correspondante doit etre portee"
        % len(hors_contrat)))
    print("  (les sites non attribues sont ceux des probes #287-r12, dont l'objet EST de")
    print("   balayer tout le registre avec une tuile : les compter en faute ferait rougir")
    print("   la mesure du regime sur la mesure elle-meme.)")
    print("")

    if args.cliquet:
        ko = len(manquantes) + len(hors_contrat)
        if not tile:
            print("CLIQUET ROUGE : ZERO ability `TargetIsTile` -- un ensemble vide passerait")
            print("  pour un vert. Le registre ou la lecture des masques a casse.")
            return 1
        if manquantes:
            print("CLIQUET ROUGE : %d ability(s) `TargetIsTile` sans resolution de cible en"
                  " tete d'`execute_behaviour`." % len(manquantes))
            print("  Le natif resout AVANT `GetAbilityEntities` "
                  "(`ActiveAbilityOperation$$ExecuteInternal`) : sans cette ligne, un appelant")
            print("  qui passe une UNITE fait operer l'ability sur l'unite au lieu de sa TUILE.")
            print("  Degradation PERMISSIVE et muette. Poser, en tete du corps :")
            print("      target_id = self.get_actual_target(state, caster_id, target_id)")
        if hors_contrat:
            print("CLIQUET ROUGE : %d appel(s) direct(s) passent une TUILE a une ability"
                  " unit-target." % len(hors_contrat))
            print("  Le regime etait MORT quand #287-r14-r1 a ete tranche ; il ne l'est plus.")
            print("  Porter la resolution sur la tete de CES abilities-la (pas les 73).")
        if ko:
            return 1
        print("CLIQUET VERT : %d/%d tile-target resolvent, 0 surplus, et aucun appelant direct"
              " n'emprunte le regime tuile hors contrat." % (len(tile), len(tile)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
