"""#433-r4-r1-r4-r2 -- CLIQUET : un call-site d'adjacence qui passe l'ELEVATION passe AUSSI le
VOISINAGE.

CE QU'IL EST SEUL A VOIR
------------------------
`battle_query.is_adjacent` porte DEUX etages du natif
(`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`) : l'ENUMERATION
de la liste STOCKEE (`neigh_by_pos`) puis la PORTE d'elevation (`elev_by_pos`). Les deux sont des
parametres OPTIONNELS, donc un call-site qui en oublie un degrade **en silence** -- ni erreur, ni
crash, juste un predicat plus PERMISSIF que le natif. C'est exactement la signature de degradation
de `TARGETING_OPTIONS` (cf. `CLAUDE.md`), et le seul gisement que notre propre cadence de portage
alimente : chaque nouveau playbook qui compte des voisins peut le rouvrir.

Le cliquet garde donc l'INVARIANT DE COUPLE, pas la presence d'un argument : **un call-site qui a
su fournir l'elevation a forcement un porteur de contexte sous la main, donc il peut fournir le
voisinage**. Un call-site qui ne passe NI l'un NI l'autre est hors gisement (arbre purement
numerique, test unitaire) et n'est pas compte.

MESURE qui justifie le cliquet (`probe_433r4r1r4r2_is_adjacent_substrat_live.py`) : la couronne hex
sur-atteint la liste stockee de **4** aretes dirigees sur `C1_74` et **38** sur `C3_14`, pour **0**
arete dans l'autre sens -- un ecart strictement PERMISSIF.

VERDICT : 0 = vert. Non nul = des call-sites branches a moitie (listes).
ASCII only.
"""
from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent

# nom -> index du parametre ELEVATION dans la signature positionnelle
CIBLES = {"is_adjacent": 2, "are_entities_adjacent": 2, "count_adjacent": 2,
          "count_adjacent_matching": 3}
MODULES = ("bq", "battle_query", "_bq")


def _fichiers() -> list[pathlib.Path] | None:
    """Les sources versionnees de `scripts/python/engine`, DANS CE CHECKOUT (#434).

    `git ls-files` borne le balayage a l'arbre courant : un `rglob` depuis la racine lirait le
    code en cours des autres agents sous `.claude/worktrees/` et leur rouge serait impute ici.
    `None` = git n'a pas repondu -> INDISPONIBLE (#471), jamais un zero silencieux."""
    try:
        r = subprocess.run(["git", "ls-files", "scripts/python/engine"], cwd=str(ROOT),
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        print("INDISPONIBLE: git ls-files injouable (%s)" % type(e).__name__)
        return None
    if r.returncode != 0:
        print("INDISPONIBLE: git ls-files rc=%d" % r.returncode)
        return None
    return [ROOT / ln.strip() for ln in r.stdout.splitlines()
            if ln.strip().endswith(".py")]


def balayer(fichiers) -> tuple[list, int]:
    """Rend `(call-sites a moitie branches, total des call-sites gates)`."""
    manquants, total = [], 0
    for p in fichiers:
        try:
            with open(p, encoding="utf-8", newline="") as fh:
                src = fh.read()
            tree = ast.parse(src)
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            f = getattr(node, "func", None)
            if not (isinstance(node, ast.Call) and isinstance(f, ast.Attribute)
                    and f.attr in CIBLES):
                continue
            if getattr(f.value, "id", None) not in MODULES:
                continue
            idx = CIBLES[f.attr]
            kw = {k.arg for k in node.keywords if k.arg}
            a_elev = len(node.args) > idx or "elev_by_pos" in kw
            a_neigh = len(node.args) > idx + 1 or "neigh_by_pos" in kw
            if not a_elev:
                continue                     # hors gisement : aucun des deux canaux
            total += 1
            if not a_neigh:
                manquants.append((p.relative_to(ROOT).as_posix(), node.lineno, f.attr))
    return manquants, total


def main() -> int:
    fichiers = _fichiers()
    if fichiers is None:
        return 99                            # INDISPONIBLE -- le harnais, pas le depot (#471)
    manquants, total = balayer(fichiers)
    print("== #433-r4-r1-r4-r2 -- canal `neigh_by_pos` sur les call-sites d'adjacence")
    print("   call-sites gates par l'elevation : %d" % total)
    print("   sans le canal de voisinage       : %d (attendu 0)" % len(manquants))
    for (rel, ln, name) in manquants:
        print("      %s:%d  %s -- elevation fournie, voisinage MANQUANT" % (rel, ln, name))
    if total == 0:
        # Un zero de TOTAL n'est pas un vert : le balayage n'a rien vu, donc il ne garde rien.
        print("ECART: aucun call-site trouve -- le cliquet ne garde rien (perimetre casse ?)")
        return 1
    print("VERDICT: %s" % ("PASS" if not manquants else "FAIL (%d)" % len(manquants)))
    return 0 if not manquants else 1


if __name__ == "__main__":
    raise SystemExit(main())
