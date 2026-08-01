"""#421 -- CLIQUET DE COUVERTURE : le `RAIL` de `probe_229` couvre-t-il tout `EFFECT_TRIGGERS` ?

Ce probe est le pendant STRUCTUREL de `probe_229_effect_triggers_active.py`. Le 229 verifie
que les classes QU'IL CONNAIT sont conformes a leur rail ; il ne dit RIEN de celles qu'il ne
connait pas. C'est cette asymetrie qui a laisse son `RAIL` deriver : entre l'ecriture du 229
et le 2026-08-01, **19** classes sont entrees au registre sans y entrer, et le probe est reste
muet sur elles -- il rendait FAIL pour une AUTRE raison (`EXPECTED_GAPS` change), ce qui masque
le trou au lieu de le nommer.

Ce que ce probe mesure, et QUE lui :

  * COUVERTURE  : toute classe de `EFFECT_TRIGGERS` a une entree dans `RAIL` ;
  * FRAICHEUR   : toute entree de `RAIL` designe une classe REELLEMENT inscrite (une entree
                  orpheline est une classe renommee/supprimee -- exactement ce qui est arrive
                  a `GhostEffectRevive`, scinde en `TimeFluxGhostEffectRevive` +
                  `EchoesFromTheWarpGhostEffectRevive` par #366-r1) ;
  * COHERENCE   : `EXPECTED_GAPS` et `ARRAYSET_READS_BY_TREE` ne citent que des classes
                  inscrites (meme piege : `EXPECTED_GAPS = {"GhostEffectRevive"}` a survecu au
                  renommage et s'est mis a rendre « resorbe » un gap qui ne l'etait pas).

100 % OFFLINE. Cout mesure : ~1 s (import du registre + reflexion, aucun runner).

Usage :  python probe_421_rail_covers_registry.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS   # noqa: E402
from probe_229_effect_triggers_active import (                                    # noqa: E402
    RAIL, EXPECTED_GAPS, ARRAYSET_READS_BY_TREE)


def main() -> int:
    registered: dict[str, int] = {}
    for etype, classes in sorted(EFFECT_TRIGGERS.items()):
        for cls in classes:
            registered[cls.__name__] = etype

    missing = sorted(n for n in registered if n not in RAIL)
    orphan = sorted(n for n in RAIL if n not in registered)
    bad_gaps = sorted(n for n in EXPECTED_GAPS if n not in registered)
    bad_tree = sorted(n for n in ARRAYSET_READS_BY_TREE if n not in registered)

    print("=== #421 RAIL(probe_229) vs EFFECT_TRIGGERS(registry) ===")
    print("classes inscrites = %d ; entrees RAIL = %d" % (len(registered), len(RAIL)))
    print("")
    print("-- inscrites SANS entree RAIL (trou de recensement) : %d" % len(missing))
    for n in missing:
        print("   %-6d %s" % (registered[n], n))
    print("-- entrees RAIL orphelines (classe disparue/renommee) : %d" % len(orphan))
    for n in orphan:
        print("   %s  [%s]" % (n, RAIL[n][0]))
    print("-- EXPECTED_GAPS citant une classe non inscrite : %d" % len(bad_gaps))
    for n in bad_gaps:
        print("   %s" % n)
    print("-- ARRAYSET_READS_BY_TREE citant une classe non inscrite : %d" % len(bad_tree))
    for n in bad_tree:
        print("   %s" % n)

    ok = not (missing or orphan or bad_gaps or bad_tree)
    if missing:
        print("FAIL: le RAIL ne couvre pas le registre -- toute classe entrant dans "
              "EFFECT_TRIGGERS pose son rail NATIF dans le meme commit.")
    if orphan:
        print("FAIL: entree(s) RAIL sans classe -- renommage non repercute.")
    if bad_gaps or bad_tree:
        print("FAIL: table auxiliaire de probe_229 perimee.")
    print("")
    print("RESULT: %s" % ("OK" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
