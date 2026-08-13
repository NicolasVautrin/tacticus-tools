"""#996-r1 -- ventilation des EVENEMENTS du cast 1053 : qui produit quoi.

Le cast de 1053 emet plus de `UnitDamaged` que son arbre n'en contient : il faut savoir LESQUELS
viennent de l'arbre (l'attaque NORMALE dispatchee) et lesquels viennent d'AUTRES mecanismes (passif
du caster, overwatch de l'ennemi). Comparer un total agrege ferait fitter un scalaire.

Usage : python probe_996r1_events_diag.py --state-file <ABSOLU propre>
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import sys

import stream_events as SE

import probe_996r1_devout_push as P


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    a = ap.parse_args()
    sid = P._sid()
    rid = P._build(sid, a.state_file, P.GEOMETRIE, p_places={P.PORTEUR: P.CASTER_TILE})
    try:
        cap = P._capture(sid, rid)
        caster = P._by_vis(cap, P.PORTEUR_VIS)
        cibles = [u for u in P._units(cap) if u.get("team") != caster.get("team")]
        cibles.sort(key=lambda u: (P._dist(caster, u) or 99, int(u["id"])))
        cible = cibles[0]
        res = P._rpc(sid, "applyAction",
                     {"runnerId": rid,
                      "action": {"kind": "ability", "casterId": int(caster["id"]),
                                 "targetId": int(cible["id"]), "abilityType": P.ABILITY}}, 240)
        dmg = SE.step_id("UnitDamaged")
        for act in ((res or {}).get("actions") or []):
            for e in (act.get("events") or []):
                try:
                    t = json.loads(e.get("tags") or "{}")
                except Exception:
                    t = {}
                if e.get("step") == dmg or "Amount" in t:
                    print("[events] step=%s tags=%s"
                          % (e.get("step"), json.dumps(t, sort_keys=True)[:700]))
    finally:
        P._dispose(sid, rid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
