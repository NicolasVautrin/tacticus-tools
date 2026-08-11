"""#907 -- DECOMPOSITION PAR ETAGE de l'ecart 3 coups (natif) / 2 coups (port) sur `eldarRanger`.
Jetable-utile : il imprime l'etat de chaque etage, il n'assertionne rien."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import probe_907_incendiary_shells as P


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--cible", default="eldarRanger")
    a = ap.parse_args(argv)
    sid = P._sid()
    rid = P._build(sid, a.state_file, P.GEOMETRIES["libre"])
    try:
        cap = P._capture(sid, rid)
        caster = P._by_vis(cap, P.PORTEUR_VIS)
        cible = P._by_vis(cap, a.cible)
        print("caster=%s cible=%s d=%s" % (caster["id"], cible["id"], P._dist(caster, cible)))
        print("cible effects=%r" % (cible.get("effects"),))
        st = P._state(cap)

        # ETAGE 1 -- les traits/effets PORTES de la cible et la tuile qu'elle occupe
        from engine.runner.abilities.attack_query import _has_trait
        from engine.runner.components import PositionComponent
        e = st.get_entity(int(cible["id"]))
        pc = e.get_component(PositionComponent) if e is not None else None
        pos = getattr(pc, "pos", None) or getattr(pc, "tiles", None)
        c, r = P._pos(cible)
        cc, rr = P._pos(caster)
        print("etage1 pos portee=%r terrain_cible=%r terrain_caster=%r"
              % (pos, st.board.terrain_at(c, r) if st.board else None,
                 st.board.terrain_at(cc, rr) if st.board else None))

        # ETAGE 2 -- le nombre de coups que l'etage `hits` du port calcule
        from engine.runner.abilities.base import ability_attack_params
        print("etage2 ability_attack_params(ranged=True) = %r"
              % (ability_attack_params(st, int(caster["id"]), P.INCENDIARY_SHELLS_ID,
                                       P.INCENDIARY_SHELLS_PROFILE, ranged=True),))

        # ETAGE 3 -- le diag COMPLET de l'attaque portee
        seq, diag = P._port_sequence(cap, caster["id"], cible["id"])
        print("etage3 seq=%r" % (seq,))
        atk = diag.get("attack") or {}
        for k in sorted(atk):
            v = atk[k]
            print("   attack[%-20s] = %s" % (k, repr(v)[:300]))
        return 0
    finally:
        P._rpc(sid, "disposeRunner", {"runnerId": rid}, 60)


if __name__ == "__main__":
    raise SystemExit(main())
