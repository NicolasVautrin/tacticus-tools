"""#270-r4-r2 -- CLIQUET : aucun CYCLE d'import NIVEAU MODULE dans `engine/`.

Critere DERIVE (calcul de composantes fortement connexes sur le graphe reel des
imports), jamais une liste de noms : un cycle qui reapparait ailleurs rougit pareil.

Deux graphes sont construits, et la difference entre les deux EST le sujet :

  * graphe NIVEAU MODULE  -- seuls les `import` executes a l'import du module
                             (hors corps de fonction, hors `if TYPE_CHECKING`).
                             C'est CELUI qui peut lever `ImportError`. Etape 1.
  * graphe TOUS IMPORTS   -- module-level + differes. Il exhibe un SCC geant qui
                             est un ARTEFACT : un import differe ne cree pas de
                             cycle a l'import, il en BRISE un. Etape 2, informative.

Un import differe ne casse pas un cycle, il le CACHE : il deplace l'echec vers le
premier appel et rend l'ordre d'initialisation dependant du chemin d'execution.
L'etape 3 les COMPTE (avant/apres se lisent sur ce chiffre).

Usage :
    python probe_270r4r2_cycles_imports.py            # cliquet (rc != 0 si cycle)
    python probe_270r4r2_cycles_imports.py --detail   # + arêtes de chaque SCC
    python probe_270r4r2_cycles_imports.py --differes # + ventilation des differes
"""
from __future__ import annotations

import argparse
import ast
import sys
from collections import defaultdict
from pathlib import Path

RACINE = Path(__file__).resolve().parent
PAQUET = "engine"


# ---------------------------------------------------------------- collecte AST

class _Visiteur(ast.NodeVisitor):
    """Collecte les imports en distinguant NIVEAU MODULE et DIFFERE.

    `module_level` : l'import s'execute quand le module est importe.
    `differe`      : l'import est dans un corps de fonction/methode -> il ne
                     s'execute qu'a l'appel. `if TYPE_CHECKING:` compte comme
                     differe aussi (jamais execute au runtime).
    """

    def __init__(self, mod: str, pkg: str) -> None:
        self.mod = mod
        self.pkg = pkg
        self.module_level: set[str] = set()
        self.differe: list[tuple[str, int, str]] = []   # (cible, ligne, cause)
        self._profondeur_fn = 0
        self._profondeur_tc = 0

    # -- resolution -----------------------------------------------------------
    def _resoudre(self, noeud: ast.ImportFrom) -> list[str]:
        if noeud.level == 0:
            return [noeud.module] if noeud.module else []
        # relatif : remonter `level - 1` crans depuis le PAQUET du module
        parts = self.pkg.split(".")
        remontee = noeud.level - 1
        base = parts[: len(parts) - remontee] if remontee else parts
        if not base:
            return []
        cible = ".".join(base)
        if noeud.module:
            cible = f"{cible}.{noeud.module}"
        # `from .x import y` : y peut etre un SOUS-MODULE ou un symbole. On emet
        # les deux candidats ; le filtrage se fait contre l'ensemble des modules
        # reellement presents sur le disque.
        out = [cible]
        for alias in noeud.names:
            if alias.name != "*":
                out.append(f"{cible}.{alias.name}")
        return out

    def _absolu(self, noeud: ast.ImportFrom) -> list[str]:
        if not noeud.module:
            return []
        out = [noeud.module]
        for alias in noeud.names:
            if alias.name != "*":
                out.append(f"{noeud.module}.{alias.name}")
        return out

    # -- visite ---------------------------------------------------------------
    def _enregistrer(self, cibles: list[str], ligne: int, cause: str) -> None:
        differe = self._profondeur_fn > 0 or self._profondeur_tc > 0
        for c in cibles:
            if not c.startswith(PAQUET):
                continue
            if differe:
                self.differe.append((c, ligne, cause))
            else:
                self.module_level.add(c)

    def visit_Import(self, noeud: ast.Import) -> None:
        cibles = [a.name for a in noeud.names]
        cause = "fonction" if self._profondeur_fn else ("TYPE_CHECKING" if self._profondeur_tc else "")
        self._enregistrer(cibles, noeud.lineno, cause)

    def visit_ImportFrom(self, noeud: ast.ImportFrom) -> None:
        cibles = self._resoudre(noeud) if noeud.level else self._absolu(noeud)
        cause = "fonction" if self._profondeur_fn else ("TYPE_CHECKING" if self._profondeur_tc else "")
        self._enregistrer(cibles, noeud.lineno, cause)

    def visit_FunctionDef(self, noeud: ast.FunctionDef) -> None:
        self._profondeur_fn += 1
        self.generic_visit(noeud)
        self._profondeur_fn -= 1

    def visit_AsyncFunctionDef(self, noeud: ast.AsyncFunctionDef) -> None:
        self._profondeur_fn += 1
        self.generic_visit(noeud)
        self._profondeur_fn -= 1

    def visit_If(self, noeud: ast.If) -> None:
        if _est_type_checking(noeud.test):
            self._profondeur_tc += 1
            for enfant in noeud.body:
                self.visit(enfant)
            self._profondeur_tc -= 1
            for enfant in noeud.orelse:
                self.visit(enfant)
            return
        self.generic_visit(noeud)


def _est_type_checking(test: ast.expr) -> bool:
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return True
    return False


# ---------------------------------------------------------------- graphe

def _nom_module(chemin: Path) -> str:
    rel = chemin.relative_to(RACINE)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][: -len(".py")]
    return ".".join(parts)


def construire(racine_paquet: Path) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, list]]:
    """Rend (aretes_module_level, aretes_toutes, differes_par_module)."""
    fichiers = sorted(racine_paquet.rglob("*.py"))
    modules = {_nom_module(f): f for f in fichiers}
    # les paquets eux-memes sont des modules valides
    connus = set(modules)

    ml: dict[str, set[str]] = defaultdict(set)
    tous: dict[str, set[str]] = defaultdict(set)
    differes: dict[str, list] = defaultdict(list)

    for mod, chemin in modules.items():
        src = chemin.read_text(encoding="utf-8")
        arbre = ast.parse(src, filename=str(chemin))
        pkg = mod if chemin.name == "__init__.py" else mod.rsplit(".", 1)[0]
        v = _Visiteur(mod, pkg)
        v.visit(arbre)

        for cible in v.module_level:
            reel = _reduire(cible, connus)
            if reel and reel != mod:
                ml[mod].add(reel)
                tous[mod].add(reel)
        for cible, ligne, cause in v.differe:
            reel = _reduire(cible, connus)
            differes[mod].append((cible, reel, ligne, cause))
            if reel and reel != mod:
                tous[mod].add(reel)

    for m in connus:
        ml.setdefault(m, set())
        tous.setdefault(m, set())
    return dict(ml), dict(tous), dict(differes)


def _reduire(cible: str, connus: set[str]) -> str | None:
    """`engine.a.b.SYMBOLE` -> `engine.a.b` si `.SYMBOLE` n'est pas un module."""
    if cible in connus:
        return cible
    while "." in cible:
        cible = cible.rsplit(".", 1)[0]
        if cible in connus:
            return cible
    return None


# ---------------------------------------------------------------- Tarjan

def scc(graphe: dict[str, set[str]]) -> list[list[str]]:
    index: dict[str, int] = {}
    bas: dict[str, int] = {}
    sur_pile: dict[str, bool] = {}
    pile: list[str] = []
    out: list[list[str]] = []
    compteur = [0]

    def _fort(v: str) -> None:
        # iteratif : la recursion depasse la limite sur 400+ modules
        travail = [(v, iter(sorted(graphe.get(v, ()))))]
        index[v] = bas[v] = compteur[0]
        compteur[0] += 1
        pile.append(v)
        sur_pile[v] = True
        while travail:
            noeud, it = travail[-1]
            avance = False
            for w in it:
                if w not in index:
                    index[w] = bas[w] = compteur[0]
                    compteur[0] += 1
                    pile.append(w)
                    sur_pile[w] = True
                    travail.append((w, iter(sorted(graphe.get(w, ())))))
                    avance = True
                    break
                if sur_pile.get(w):
                    bas[noeud] = min(bas[noeud], index[w])
            if avance:
                continue
            travail.pop()
            if travail:
                parent = travail[-1][0]
                bas[parent] = min(bas[parent], bas[noeud])
            if bas[noeud] == index[noeud]:
                comp = []
                while True:
                    w = pile.pop()
                    sur_pile[w] = False
                    comp.append(w)
                    if w == noeud:
                        break
                out.append(sorted(comp))

    for v in sorted(graphe):
        if v not in index:
            _fort(v)
    return out


def _cycles(graphe: dict[str, set[str]]) -> list[list[str]]:
    """SCC de taille > 1, PLUS les boucles sur soi (impossible ici, mais derive)."""
    out = []
    for comp in scc(graphe):
        if len(comp) > 1:
            out.append(comp)
        elif comp[0] in graphe.get(comp[0], set()):
            out.append(comp)
    return sorted(out, key=len, reverse=True)


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", action="store_true", help="arêtes internes de chaque SCC")
    ap.add_argument("--differes", action="store_true", help="ventilation des imports differes")
    args = ap.parse_args()

    racine_paquet = RACINE / PAQUET
    if not racine_paquet.is_dir():
        print("[270-r4-r2] ECHEC : paquet introuvable -> %s" % racine_paquet)
        return 2

    ml, tous, differes = construire(racine_paquet)
    n_mod = len(ml)
    n_ar_ml = sum(len(v) for v in ml.values())
    n_ar_tous = sum(len(v) for v in tous.values())

    print("[270-r4-r2] TEMOIN : %d modules visites sous %s/" % (n_mod, PAQUET))
    if n_mod == 0:
        print("[270-r4-r2] ECHEC : 0 module visite -- un zero de balayage ne prouve RIEN")
        return 2

    # -- etape 1 : le CLIQUET
    cyc_ml = _cycles(ml)
    print("[270-r4-r2] etape 1 -- graphe NIVEAU MODULE : %d aretes, %d SCC > 1"
          % (n_ar_ml, len(cyc_ml)))
    for comp in cyc_ml:
        print("   SCC de %d : %s" % (len(comp), ", ".join(comp)))
        if args.detail:
            dedans = set(comp)
            for m in comp:
                for c in sorted(ml[m] & dedans):
                    print("      %s -> %s" % (m, c))

    # -- etape 2 : l'ARTEFACT (informatif)
    cyc_tous = _cycles(tous)
    plus_gros = max((len(c) for c in cyc_tous), default=0)
    print("[270-r4-r2] etape 2 -- graphe TOUS IMPORTS (differes inclus) : %d aretes, "
          "%d SCC > 1, plus gros = %d module(s)" % (n_ar_tous, len(cyc_tous), plus_gros))
    print("   (ce SCC est un ARTEFACT : un import differe BRISE le cycle, il n'en cree pas)")

    # -- etape 3 : le COMPTE des differes
    n_diff = sum(len(v) for v in differes.values())
    par_cause: dict[str, int] = defaultdict(int)
    for v in differes.values():
        for _, _, _, cause in v:
            par_cause[cause] += 1
    print("[270-r4-r2] etape 3 -- imports differes vers %s/ dans %s/ : %d "
          "(%s)" % (PAQUET, PAQUET, n_diff,
                    ", ".join("%s=%d" % (k or "?", n) for k, n in sorted(par_cause.items()))))
    if args.differes:
        for mod in sorted(differes):
            for cible, reel, ligne, cause in sorted(differes[mod], key=lambda t: t[2]):
                print("   %s:%d  -> %s  [%s]" % (mod, ligne, cible, cause))

    if cyc_ml:
        print("[270-r4-r2] ECHEC : %d cycle(s) d'import NIVEAU MODULE" % len(cyc_ml))
        return 1
    print("[270-r4-r2] OK : 0 cycle d'import niveau module (temoin : %d modules, %d aretes)"
          % (n_mod, n_ar_ml))
    return 0


if __name__ == "__main__":
    sys.exit(main())
