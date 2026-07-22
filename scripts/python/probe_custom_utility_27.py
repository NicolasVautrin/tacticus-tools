"""Garde legere OFFLINE des overrides CalculateCustomUtility portes (#27, case-27).

Verifie la FORME des 2 termes custom portes (dispatch + formule), pas le live :
- ArmoriumCherub (1014) @18111c530 = Fix64(1) constant.
- LightOfSanguinius (1177) @181133d70 = count(units caster-team a PV%==100) * W(-10).

Usage : python probe_custom_utility_27.py   (depuis scripts/python ; ASCII only ; exit 0 = OK)
"""
from __future__ import annotations

import sys
import types

import engine.playbook as pb
import engine.weights as W


def _fake_ctx(wt, **kw):
    d = dict(me={"team": 1, "id": 100}, units=[], obs_units=[], epos=[], elev_by_pos={}, wt=wt)
    d.update(kw)
    return types.SimpleNamespace(**d)


def main() -> int:
    wt = W.load()
    fails = []

    # dispatch : les 2 ids doivent etre enregistres sur les classes attendues.
    reg = pb.REGISTRY
    for aid, name in ((1014, "ArmoriumCherubPlaybook"), (1177, "LightOfSanguiniusPlaybook")):
        got = type(reg.get(aid)).__name__
        if got != name:
            fails.append(f"dispatch {aid}: attendu {name}, obtenu {got}")

    # ArmoriumCherub = 1 constant (independant du ctx).
    cb = pb.get_playbook(1014)
    v = cb.calculate_custom_utility(_fake_ctx(wt), (0, 0), 5, 1014)
    if v != 1.0:
        fails.append(f"ArmoriumCherub custom attendu 1.0, obtenu {v}")

    # LightOfSanguinius = count(full-HP friends) * W(-10). 2 amis pleins (100,101) sur la team 1.
    units = [
        {"team": 1, "id": 100, "alive": True},
        {"team": 1, "id": 101, "alive": True},
        {"team": 1, "id": 102, "alive": True},   # blesse -> exclu
        {"team": 2, "id": 200, "alive": True},   # ennemi -> exclu
        {"team": 1, "id": 103, "alive": False},  # mort -> exclu
    ]
    obs = [
        {"squadId": 100, "hp": 100, "hpMax": 100},
        {"squadId": 101, "hp": 50, "hpMax": 50},
        {"squadId": 102, "hp": 30, "hpMax": 100},
        {"squadId": 200, "hp": 80, "hpMax": 80},
        {"squadId": 103, "hp": 0, "hpMax": 100},
    ]
    w = wt.sub("ActiveAbilities", "LightOfSanguinius_FullHealthFriendlyUnits")
    ls = pb.get_playbook(1177)
    v = ls.calculate_custom_utility(_fake_ctx(wt, units=units, obs_units=obs), (0, 0), 5, 1177)
    expected = 2 * w
    if v != expected:
        fails.append(f"LightOfSanguinius custom attendu {expected} (2 amis pleins * W={w}), obtenu {v}")

    if fails:
        for f in fails:
            print("FAIL:", f)
        return 1
    print("OK: ArmoriumCherub=1 ; LightOfSanguinius=2*W(", w, ")=", expected, "; dispatch 1014/1177 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
