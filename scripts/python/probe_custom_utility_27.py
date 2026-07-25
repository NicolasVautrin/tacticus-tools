"""Garde legere OFFLINE des overrides CalculateCustomUtility portes (#27, case-27).

Verifie la FORME des termes custom portes (dispatch + formule), pas le live :
- ArmoriumCherub (1014) @18111c530 = Fix64(1) constant.
- LightOfSanguinius (1177) @181133d70 = count(units caster-team a PV%==100) * W(-10).
- HeraldOfTheApocalypse (1020) @1811441b0 = 0 si un ennemi normal-attaquable par le caster
  peut lui-meme frapper quelqu'un, sinon W(HeraldOfTheApocalypse_CannotKillEnemy)=50.
- Drachnyen (1029) @18112dc60 = W(Drachnyen_MultipleAdjacentUnits)=10 si >= 2 ENNEMIS
  adjacents a la TUILE D'ATTAQUE, sinon 0.

Usage : python probe_custom_utility_27.py   (depuis scripts/python ; ASCII only ; exit 0 = OK)
"""
from __future__ import annotations

import sys
import types

import engine.playbook as pb
import engine.weights as W


def _fake_ctx(wt, **kw):
    d = dict(me={"team": 1, "id": 100}, units=[], obs_units=[], epos=[], elev_by_pos={}, wt=wt,
             uid=100, plans={}, normal_ids={69})
    d.update(kw)
    return types.SimpleNamespace(**d)


def main() -> int:
    wt = W.load()
    fails = []

    # dispatch : les ids doivent etre enregistres sur les classes attendues.
    reg = pb.REGISTRY
    for aid, name in ((1014, "ArmoriumCherubPlaybook"), (1177, "LightOfSanguiniusPlaybook"),
                      (1020, "HeraldOfTheApocalypsePlaybook"), (1029, "DrachnyenPlaybook")):
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

    # --- Drachnyen (1029) : >= 2 ENNEMIS adjacents a la TUILE D'ATTAQUE -> W(10), sinon 0.
    wd = wt.sub("ActiveAbilities", "Drachnyen_MultipleAdjacentUnits")
    dr = pb.get_playbook(1029)
    tile = (2, 5)
    adj2 = [(2, 4), (2, 6)]            # deux voisins de (2,5)
    adj1 = [(2, 4), (9, 9)]            # un seul voisin
    v2 = dr.calculate_custom_utility(_fake_ctx(wt, epos=adj2), tile, 5, 1029)
    v1 = dr.calculate_custom_utility(_fake_ctx(wt, epos=adj1), tile, 5, 1029)
    v0 = dr.calculate_custom_utility(_fake_ctx(wt, epos=[]), tile, 5, 1029)
    if v2 != wd:
        fails.append(f"Drachnyen 2 ennemis adjacents: attendu {wd}, obtenu {v2}")
    if v1 != 0.0 or v0 != 0.0:
        fails.append(f"Drachnyen <2 adjacents: attendu 0/0, obtenu {v1}/{v0}")
    # position-DEPENDANCE : la meme config vue depuis une tuile eloignee doit rendre 0
    if dr.calculate_custom_utility(_fake_ctx(wt, epos=adj2), (8, 8), 5, 1029) != 0.0:
        fails.append("Drachnyen: terme non position-dependant (tuile eloignee != 0)")

    # --- Herald (1020) : 0 si un ennemi normal-attaquable peut lui-meme frapper, sinon W(50).
    wh = wt.sub("ActiveAbilities", "HeraldOfTheApocalypse_CannotKillEnemy")
    hp = pb.get_playbook(1020)
    # caster (id 100, team 1) ; ennemi 200 (team 2, blackTerminator = melee portee 1).
    units_far = [{"id": 100, "team": 1, "alive": True, "visualId": "blackHaarken",
                  "pos": {"col": 0, "row": 0}},
                 {"id": 200, "team": 2, "alive": True, "visualId": "blackTerminator",
                  "pos": {"col": 0, "row": 4}}]
    plans = {100: {"evals": [{"abilityId": 69, "targetId": 200, "rankCount": 3}]}}
    v_far = hp.calculate_custom_utility(
        _fake_ctx(wt, units=units_far, plans=plans), (0, 3), 200, 1020)
    if v_far != wh:
        fails.append(f"Herald (ennemi hors de SA portee): attendu {wh}, obtenu {v_far}")
    units_near = [dict(units_far[0], pos={"col": 0, "row": 3}), units_far[1]]
    v_near = hp.calculate_custom_utility(
        _fake_ctx(wt, units=units_near, plans=plans), (0, 3), 200, 1020)
    if v_near != 0.0:
        fails.append(f"Herald (ennemi ADJACENT au caster -> peut frapper): attendu 0, obtenu {v_near}")
    # aucune cible normale atteignable -> la boucle sort immediatement -> W
    v_none = hp.calculate_custom_utility(
        _fake_ctx(wt, units=units_far, plans={100: {"evals": []}}), (0, 3), 200, 1020)
    if v_none != wh:
        fails.append(f"Herald (aucune cible normale): attendu {wh}, obtenu {v_none}")

    if fails:
        for f in fails:
            print("FAIL:", f)
        return 1
    print("OK: ArmoriumCherub=1 ; LightOfSanguinius=2*W(", w, ")=", expected,
          "; Drachnyen 2adj=", v2, "/1adj=", v1, "; Herald far=", v_far, "/near=", v_near,
          "; dispatch 1014/1177/1020/1029 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
