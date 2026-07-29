#!/usr/bin/env python3
"""Resynchronise les commentaires numeriques `int(UtilityType.X)  # N` sur l'enum courant.

POURQUOI CET OUTIL EXISTE : le code du port designe les feuilles d'utilite par SYMBOLE
(`int(UtilityType.Elevation)`) -- il est donc juste par construction. Mais des dizaines de
lignes portent en plus la valeur en COMMENTAIRE (`# 8`), et ces commentaires-la ne sont
verifies par rien. Quand le jeu RENUMEROTE l'enum, le code reste juste et les commentaires
deviennent FAUX en ayant l'air justes -- exactement le mode de defaillance qu'on evite
ailleurs en citant un symbole plutot qu'une adresse.

MESURE (2026-07-29, MAJ gqfc5mff6c -> rnca9r7q6c) : l'insertion de `AttackTile` en 8 a
decale 59 membres de +1. Un lecteur voyant `UtilityType.Elevation  # 8` aurait cru que la
feuille 8 est Elevation, alors que 8 est desormais AttackTile.

A RELANCER A CHAQUE CHANGEMENT DE BUILD, apres avoir re-derive `engine/utilities/utility_type.py`
depuis `data/symbols/<build>/frida/enums.tsv`.

Usage :
    python scripts/python/sync_utility_type_comments.py            # rapport seul (dry-run)
    python scripts/python/sync_utility_type_comments.py --write    # applique
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENGINE = REPO / "scripts" / "python" / "engine"

# `... int(UtilityType.<Nom>) ...  # <nombre>` -- on ne touche QUE le nombre du commentaire,
# et seulement quand le commentaire est exactement un entier (pas de prose accrochee).
PAT = re.compile(r"(int\(UtilityType\.(\w+)\)\s*)(#\s*)(\d+)(\s*)$")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="applique les corrections")
    args = ap.parse_args()

    sys.path.insert(0, str(REPO / "scripts" / "python"))
    from engine.utilities.utility_type import UtilityType

    total, fixed, unknown = 0, 0, []
    for path in sorted(ENGINE.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        out_lines, touched = [], False
        for line in text.splitlines(keepends=True):
            stripped = line.rstrip("\r\n")
            m = PAT.search(stripped)
            if not m:
                out_lines.append(line)
                continue
            total += 1
            name, written = m.group(2), int(m.group(4))
            member = getattr(UtilityType, name, None)
            if member is None:
                unknown.append((path, name))
                out_lines.append(line)
                continue
            real = int(member)
            if written == real:
                out_lines.append(line)
                continue
            eol = line[len(stripped):]
            new = stripped[:m.start()] + m.group(1) + m.group(3) + str(real) + m.group(5) + eol
            out_lines.append(new)
            touched = True
            fixed += 1
            rel = path.relative_to(REPO).as_posix()
            print("  %-58s %-42s %3d -> %3d" % (rel, name, written, real))
        if touched and args.write:
            path.write_text("".join(out_lines), encoding="utf-8")

    print("")
    print("commentaires `# N` examines : %d" % total)
    print("desynchronises              : %d %s" % (fixed, "(CORRIGES)" if args.write else "(dry-run)"))
    if unknown:
        print("membres INCONNUS de l'enum  : %d -- a qualifier a la main :" % len(unknown))
        for path, name in unknown:
            print("    %s : %s" % (path.relative_to(REPO).as_posix(), name))
    return 1 if (fixed and not args.write) else 0


if __name__ == "__main__":
    raise SystemExit(main())
