"""probe #1083 -- RAYON DE SOUFFLE de l'exclusion des catalogues d'enum ecrits en vrac.

Compare, passif par passif (les ~211, pas seulement les `PowerUp_*`), l'ensemble de canaux
AVANT et APRES `_catalogue_member_ids`. Le but n'est pas de constater que les 19 `PowerUp_*`
reviennent en GAP -- c'est de montrer que RIEN D'AUTRE ne bouge. Un correctif de detecteur
qui repare sa cible et deplace trois voisins en silence est pire que le defaut.

Rejoue-le apres toute retouche du signal code de l'audit.

Usage :
    python probe_1083_rayon_catalogue.py
    python probe_1083_rayon_catalogue.py --catalogues   # ou sont les catalogues ecartes
"""

from __future__ import annotations

import argparse
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import audit_passive_ability_coverage as A  # noqa: E402


def _canaux(sans_catalogue: bool) -> dict[str, str]:
    """{passif -> canaux} avec ou sans l'exclusion des catalogues."""
    reel = A._catalogue_member_ids
    if sans_catalogue:
        A._catalogue_member_ids = lambda tree: set()   # regime AVANT
    try:
        zones, prose, _nf, _ne = A.scan_engine()
        out = {}
        for nom in sorted(A.collect_passives()):
            ch, _det, _cz = A.channels(nom, zones, prose)
            out[nom] = ",".join(ch) if ch else "-"
        return out
    finally:
        A._catalogue_member_ids = reel


def _lister_catalogues() -> list[tuple[str, int, int, str]]:
    trouves = []
    for root, _d, files in os.walk(A.ENGINE_DIR):
        for fn in sorted(files):
            if not fn.endswith(".py"):
                continue
            p = os.path.join(root, fn)
            try:
                with open(p, encoding="utf-8") as f:
                    tree = ast.parse(f.read())
            except (OSError, SyntaxError):
                continue
            for n in ast.walk(tree):
                if not isinstance(n, (ast.Tuple, ast.List, ast.Set)):
                    continue
                elts = n.elts
                if len(elts) < 2:
                    continue
                bases = set()
                ok = True
                for e in elts:
                    if not (isinstance(e, ast.Attribute) and isinstance(e.value, ast.Name)):
                        ok = False
                        break
                    bases.add(e.value.id)
                if ok and len(bases) == 1:
                    trouves.append((os.path.relpath(p, A.ENGINE_DIR), n.lineno,
                                    len(elts), sorted(bases)[0]))
    return trouves


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalogues", action="store_true")
    args = ap.parse_args()

    if args.catalogues:
        cats = _lister_catalogues()
        print("[1083] catalogues d'enum ecrits en vrac dans engine/ : %d" % len(cats))
        for f, ln, n, base in sorted(cats, key=lambda t: -t[2])[:40]:
            print("   %-52s l.%-5d %3d membres  base=%s" % (f, ln, n, base))
        return 0

    avant = _canaux(sans_catalogue=True)
    apres = _canaux(sans_catalogue=False)

    changes = {k: (avant[k], apres[k]) for k in avant if avant[k] != apres[k]}
    print("[1083] passifs balayes : %d" % len(avant))
    print("[1083] passifs dont l'ensemble de CANAUX change : %d" % len(changes))
    for k, (a, b) in sorted(changes.items()):
        print("   %-46s %-12s -> %-12s" % (k, a, b))

    hors_powerup = sorted(k for k in changes if not k.startswith("PowerUp"))
    print("[1083] parmi eux, HORS famille PowerUp : %d %s"
          % (len(hors_powerup), hors_powerup if hors_powerup else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
