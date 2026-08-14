"""probe #1083 -- QUEL symbole du moteur fait basculer les `PowerUp_*` en canal `R` ?

`audit_passive_ability_coverage.channels` classe en canal `R` (dernier repli) tout passif
dont le NOM est retrouve dans un symbole du CODE de `engine/**`, via `_boundary_hit`. Ce
probe ne se contente pas du verdict : il REMONTE le ou les symboles responsables, zone par
zone, pour qu'on puisse juger si le rapprochement designe la bonne chose.

Motivation : les 20 `PowerUp_*` sont passes de GAP a ZONE-GRISE canal `R` d'un seul bloc,
au merge d'une PR qui ne parle ni de power-ups ni de tuiles. Un rapprochement par NOM doit
qualifier son ENUM -- sinon c'est un faux ami (l'en-tete de l'audit documente lui-meme le
cas `GalvanicField` / `Repair_GalvanicField`).

Usage :
    python probe_1083_canal_r_powerup.py               # les 20 PowerUp_*
    python probe_1083_canal_r_powerup.py --prefixe X   # une autre famille
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import audit_passive_ability_coverage as A  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefixe", default="PowerUp")
    args = ap.parse_args()

    passives = A.collect_passives()
    zones, prose, n_files, n_enum = A.scan_engine()

    noms = sorted(n for n in passives if n.startswith(args.prefixe))
    print("[1083] passifs dont le nom commence par %r : %d" % (args.prefixe, len(noms)))
    print("[1083] zones engine/ balayees : %d fichiers, %d definitions d'enum exclues"
          % (n_files, n_enum))

    for nom in noms:
        ch, det, czones = A.channels(nom, zones, prose)
        print("")
        print("  %-32s canaux=%s" % (nom, ",".join(ch) if ch else "(aucun)"))
        if "R" in ch:
            # remonter le ou les symboles responsables, zone par zone
            for z in czones:
                syms = zones[z]["syms"]
                exact = nom in syms
                frag = sorted(s for s in syms if s != nom and A._boundary_hit(s, nom))
                print("     zone %-14s exact=%s  fragments=%s"
                      % (z, exact, frag[:6] if frag else "[]"))
        for cle, val in det.items():
            if cle != "R":
                print("     canal %s -> %s" % (cle, val))
    return 0


if __name__ == "__main__":
    sys.exit(main())
