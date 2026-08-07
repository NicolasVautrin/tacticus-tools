#!/usr/bin/env python
"""Contre-epreuve #490 -- le probe `probe_490_psychic_maelstrom.py` MORD-IL ?

Un accord bit-exact ne vaut que si le controle qui l'etablit est capable de rougir. Ce script
SUBSTITUE le noeud de coups du port par un scalaire fige (`Const(1)` = « 1 coup, toujours »,
exactement la faute que la surcharge `hits:System.Int32` aurait produite si on l'avait choisie
sans lire les xrefs), puis rejoue le probe. Le resultat ATTENDU est `rc != 0`.

Le patch est ATTRIBUTAIRE sur le module (`setattr(mod, 'psychic_maelstrom_hits', stub)`) et
`psychic_maelstrom_tree` resout ce nom en GLOBAL de son module a chaque appel -> il mord (forme B ;
un `from ... import psychic_maelstrom_hits` dans l'arbre ne mordrait pas -- c'est verifie ici par
le compteur d'appels du stub, qui doit etre NON NUL).

ASCII only (cp1252). Usage: python probe_490_contre_epreuve.py [--seed 49001] [--casts 4]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import engine.runner.abilities.loki.psychic_maelstrom as PM  # noqa: E402
from engine.dsl.base import Const  # noqa: E402
import probe_490_psychic_maelstrom as PROBE  # noqa: E402

_CALLS = []


def _hits_fige(rng):
    """La MUTATION : le nombre de coups devient la constante 1, quel que soit l'etat du RNG."""
    _CALLS.append(rng)
    return Const(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=49001)
    ap.add_argument("--casts", type=int, default=4)
    args, _ = ap.parse_known_args()

    PM.psychic_maelstrom_hits = _hits_fige
    sys.argv = [sys.argv[0], "--seed", str(args.seed), "--casts", str(args.casts)]
    rc = PROBE.main()

    print(f"[490-CE] le stub a ete appele {len(_CALLS)} fois (0 = la mutation N'A PAS MORDU)")
    if not _CALLS:
        print("[490-CE] X -- patch INERTE : la contre-epreuve ne prouve rien.")
        return 2
    if rc == 0:
        print("[490-CE] X -- le probe est VERT avec un `hits` FIGE : il ne discrimine pas.")
        return 1
    print(f"[490-CE] OK -- le probe ROUGIT (rc={rc}) des que `hits` est fige. Il mord.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
