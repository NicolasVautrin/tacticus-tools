#!/usr/bin/env python
"""probe_112_darkangels -- CONFRONT LIVE des 3 actives DarkAngels du lot #112.

Confronte le port (arbres DSL de `engine/runner/abilities/darkangels.py`) au JEU, pour :
  * `Supercharge`            (1103, darkaHellblaster) -- 2 volets Plasma + effet de percage
  * `ExemplarOfHate`         (1140, darkaAsmodai)     -- debuff + branche Chaos (Pinned + attaque libre)
  * `CalibaniteGreatsword`   (1189, darkaCompanion)   -- toggle de posture Strike <-> Sweep

Le probe monte SES PROPRES runners depuis la seed BC, en DEPLACANT le camp joueur au CONTACT du camp
adverse (meme technique que `probe_92_catalog._placement(near_enemy=True)`) : sans ca les 9-11 hexes
qui separent les deux coins de MC1_67 rendent la branche Chaos d'ExemplarOfHate (qui exige un allie
DarkAngels a portee d'attaque de la cible) et le volet SPLASH de Supercharge (qui exige des ennemis
DERRIERE la cible) intestables -- « bloque par la geometrie de spawn » n'est pas une reponse.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_112_darkangels.py --case toggle
    python probe_112_darkangels.py --case exemplar
    python probe_112_darkangels.py --case supercharge
    python probe_112_darkangels.py --case all

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import copy
import json

import hexgeo
import rl_collect_batch as R

BOARD = "MC1_67"
SEED = 112112
RANK = 17

# Camp joueur : les 5 DarkAngels spawnables (rank 17). Les 3 porteurs du lot + 2 allies DarkAngels
# supplementaires -> le selecteur `UnitsFromFaction(Friends(caster), 10=DarkAngels)` d'ExemplarOfHate
# a plusieurs candidats, ce qui EXERCE le tri `SortAttackersByDamagePrediction`.
P_UNITS = ["darkaAsmodai", "darkaHellblaster", "darkaCompanion", "darkaAzrael", "darkaTerminator"]
# Camp adverse : 5 BlackLegion = grand-alliance CHAOS -> la branche `HasTrait(target, 0x7ea)`
# d'ExemplarOfHate est exercee.
A_UNITS = ["blackAbaddon", "blackTerminator", "blackObliterator", "blackHaarken", "blackPossession"]

_rids: list[int] = []


def rpc(sid, method, body, timeout=90):
    r = R._rpc(sid, method, [body], timeout=timeout)
    if isinstance(r, dict) and r.get("error"):
        raise RuntimeError("%s: %s" % (method, r["error"]))
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def dispose(sid, rid):
    try:
        R._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
    except Exception:
        pass
    if rid in _rids:
        _rids.remove(rid)


def _contact_placement(bc, n_units):
    """Tuiles de deploiement joueur AU CONTACT du camp adverse (couronne du 1er spawn twpi=1).
    Mirror de `probe_92_catalog._placement(near_enemy=True)` -- on DEPLACE les unites au lieu de subir
    la geometrie de spawn."""
    spawns = R._spawn_points_by_twpi(bc)
    epts = [tuple(p) for p in (spawns.get(1) or [])]
    if not epts:
        raise RuntimeError("aucun spawn adverse")
    board = bc.get("Board") or {}
    w, h = int(board.get("Width") or 0), int(board.get("Height") or 0)
    # On exclut TOUS les points de spawn adverses (5 ennemis = 5 spawns occupes) : une tuile deja
    # prise fait SILENCIEUSEMENT echouer le deploiement de l'unite joueur (mesure : 2 units sur 5).
    taken = set(epts)
    cands = [(c, r) for c, r in hexgeo.disk(epts[0][0], epts[0][1], 4)
             if (c, r) not in taken and 0 <= c < w and 0 <= r < h]
    cands.sort(key=lambda p: (hexgeo.distance(p, epts[0]), p))
    out = cands[:n_units]
    if len(out) < n_units:
        raise RuntimeError("pas assez de tuiles libres au contact de l'IA")
    return out


def build(sid, near=True, cap_wait_s=600):
    """Runner isole (seed BC + board MC1_67 + roster fixe). Rend le runnerId.

    CAP SATURE (MAX_RUNNERS=10, partage entre agents) : on ATTEND qu'un slot se libere jusqu'a
    `cap_wait_s` secondes au lieu d'echouer -- meme discipline que `tests/conftest.build_runner`
    (on ne dispose JAMAIS le runner d'un autre)."""
    import time
    deadline = time.time() + max(0, int(cap_wait_s))
    while True:
        try:
            return _build_once(sid, near)
        except RuntimeError as exc:
            if "cap reached" not in str(exc) or time.time() >= deadline:
                raise
            time.sleep(10)


def _build_once(sid, near=True):
    seed = R._load_seed_bc()
    board_dump = R._load_board_dump(BOARD)
    template, pool, _mow = R._normalize_and_extract_pool(sid, seed, RANK, board_dump=board_dump)
    miss = [u for u in P_UNITS + A_UNITS if u not in pool]
    if miss:
        raise RuntimeError("hors pool rank %d : %s" % (RANK, miss))
    bc = copy.deepcopy(template)
    R._patch_predefined_units(bc, list(A_UNITS))
    if near:
        pos = _contact_placement(bc, len(P_UNITS))
    else:
        pts = R._spawn_points_by_twpi(bc).get(0) or []
        pos = [(int(pts[i][0]), int(pts[i][1])) for i in range(len(P_UNITS))]
    player_units = [{"unitId": u, "playerId": R.PLAYER_ID_HUMAN,
                     "col": pos[i][0], "row": pos[i][1]} for i, u in enumerate(P_UNITS)]
    resp = R._rpc(sid, "initAndStart",
                  [{"configJson": json.dumps(bc), "seed": SEED, "playerUnits": player_units}],
                  timeout=60)
    rid = (resp.get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError("initAndStart KO: %s" % (resp.get("error") or resp))
    _rids.append(rid)
    return rid


# --------------------------------------------------------------------------- observation

def units_by_visual(dv):
    out = {}
    for u in (dv.get("units") or []):
        out[u.get("visualId")] = u
    return out


def eff_names(dv, uid):
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return sorted((e.get("effectType"), e.get("name"), e.get("remaining"))
                  for e in ((u or {}).get("effects") or []))


def positions(dv):
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u["id"]] = (p.get("col"), p.get("row"))
    return out


def hp_of(sid, rid):
    """PV par id d'unite. `observeBattle` cle ses lignes par `squadId` (== l'`id` de `decisionView`),
    PAS par `entityId` (qui vaut squadId+1)."""
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    return {u["squadId"]: (u.get("hp"), bool(u.get("isDead")))
            for u in (ob.get("units") or []) if u.get("squadId") is not None}


def act(sid, rid, action):
    """`applyAction` renvoie `{ok, actions:[{ok, mutated, changes, events}]}` -- on remonte le 1er
    element d'`actions` (la reponse de CETTE action), pas l'enveloppe."""
    r = rpc(sid, "applyAction", {"runnerId": rid, "action": action}, 90)
    acts = r.get("actions") or []
    out = dict(acts[0]) if acts else {}
    out["stage"] = r.get("stage")
    return out


def cast(sid, rid, caster, target, ability):
    return act(sid, rid, {"kind": "ability", "casterId": caster,
                          "targetId": target, "abilityType": ability})


def legal_from_here(sid, rid, unit, ability):
    """Cibles LEGALES DEPUIS LA POSITION COURANTE (`fromHere`) -- JAMAIS `targets`, qui est un
    SUPERSET incluant les cibles atteignables APRES deplacement (un cast depuis la position courante
    y serait REFUSE, et un refus natif est observationnellement identique a une ability inerte, #111)."""
    at = rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": unit, "abilityType": ability}, 90)
    out = []
    for u in (at.get("units") or []):
        for a in (u.get("abilities") or []):
            if int(a.get("abilityId") or -1) == int(ability):
                out += [x.get("targetId") for x in (a.get("fromHere") or [])]
    return out


# --------------------------------------------------------------------------- cas

def case_toggle(sid):
    """CalibaniteGreatsword (1189) : toggle de POSTURE. Attendu (mirror `ExecuteBehaviour`) :
    posture STRIKE au depart (1404 pose par la triggered `CalibaniteGreatsword_SetStartAbility`)
    -> 1er cast : +1405 Sweep / -1404 Strike ; 2e cast (tour suivant) : +1404/+1425/+1009, -1405."""
    rid = build(sid)
    try:
        dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        uid = units_by_visual(dv)["darkaCompanion"]["id"]
        print("[toggle] forcas u%s" % uid)
        print("  PRE  :", eff_names(dv, uid))
        print("  legal fromHere :", legal_from_here(sid, rid, uid, 1189))
        cast(sid, rid, uid, uid, 1189)
        dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        print("  POST1:", eff_names(dv, uid))
        # 2e cast : l'ability est once-per-turn -> il faut un nouveau tour.
        act(sid, rid, {"kind": "endturn"})
        rpc(sid, "aiPlayByUnit",
            {"runnerId": rid, "maxTurns": 1, "maxActivations": 9999, "maxPump": 400}, 300)
        dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        print("  T2 PRE :", eff_names(dv, uid))
        cast(sid, rid, uid, uid, 1189)
        dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        print("  T2 POST:", eff_names(dv, uid))
    finally:
        dispose(sid, rid)


def case_exemplar(sid):
    """ExemplarOfHate (1140) : debuff INCONDITIONNEL (1293, TurnsFromRounds(2)) + branche
    `If(HasTrait(target, 0x7ea=Chaos))` -> Pinned(1065) + override d'Attack + attaque normale libre
    du MEILLEUR allie DarkAngels a portee + retrait de l'override."""
    rid = build(sid)
    try:
        dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        bv = units_by_visual(dv)
        asmo = bv["darkaAsmodai"]["id"]
        pos = positions(dv)
        enemies = [u["id"] for u in (dv.get("units") or []) if not u.get("ctrl")]
        print("[exemplar] asmodai u%s @%s" % (asmo, pos.get(asmo)))
        for e in enemies:
            print("   enemy u%s %s @%s d=%s" % (
                e, next(x.get("visualId") for x in dv["units"] if x["id"] == e),
                pos.get(e), hexgeo.distance(pos[asmo], pos[e])))
        legal = legal_from_here(sid, rid, asmo, 1140)
        print("  legal fromHere :", legal)
        if not legal:
            print("  ABANDON : aucune cible legale depuis la position courante")
            return
        # cible = l'ennemi legal le PLUS PROCHE d'Asmodai (max de chances qu'un allie DA soit a portee)
        tgt = min(legal, key=lambda e: hexgeo.distance(pos[asmo], pos[e]))
        hp0 = hp_of(sid, rid)
        print("  target u%s d=%s hp=%s" % (tgt, hexgeo.distance(pos[asmo], pos[tgt]), hp0.get(tgt)))
        print("  PRE tgt :", eff_names(dv, tgt))
        r = cast(sid, rid, asmo, tgt, 1140)
        print("  applyAction ok=%s mutated=%s" % (r.get("ok"), r.get("mutated")))
        print("  events  :", json.dumps(r.get("events") or [], default=str)[:2500])
        dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        hp1 = hp_of(sid, rid)
        print("  POST tgt:", eff_names(dv, tgt))
        print("  hp delta:", {k: (hp0[k][0], hp1[k][0]) for k in hp0 if hp0[k][0] != hp1[k][0]})
    finally:
        dispose(sid, rid)


def case_supercharge(sid):
    """Supercharge (1103) : `AddEffect(1208 Supercharge_ExtraPiercing)` sur cible + <=2 ennemis
    DERRIERE elle (POSE AVANT les attaques) & 1x Plasma (minDmg/maxDmg) sur la cible & 1x Plasma
    (minDmg_2/maxDmg_2) sur ces memes unites derriere."""
    rid = build(sid)
    try:
        dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        bv = units_by_visual(dv)
        hell = bv["darkaHellblaster"]["id"]
        pos = positions(dv)
        legal = legal_from_here(sid, rid, hell, 1103)
        print("[supercharge] hellblaster u%s @%s legal=%s" % (hell, pos.get(hell), legal))
        if not legal:
            print("  ABANDON : aucune cible legale depuis la position courante")
            return

        # « derriere la cible » = anneau R1 de la cible, du cote OPPOSE au caster
        # (`MinDistance(caster,cand) > MinDistance(caster,target)`, STRICT).
        def behind(t):
            dt = hexgeo.distance(pos[hell], pos[t])
            return [e["id"] for e in dv["units"]
                    if (not e.get("ctrl")) and e["id"] != t
                    and hexgeo.distance(pos[e["id"]], pos[t]) == 1
                    and hexgeo.distance(pos[hell], pos[e["id"]]) > dt]
        ranked = sorted(legal, key=lambda t: -len(behind(t)))
        tgt = ranked[0]
        bh = behind(tgt)
        print("  target u%s behind=%s" % (tgt, bh))
        hp0 = hp_of(sid, rid)
        pre = {u: eff_names(dv, u) for u in [tgt] + bh}
        r = cast(sid, rid, hell, tgt, 1103)
        print("  applyAction ok=%s mutated=%s" % (r.get("ok"), r.get("mutated")))
        dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        hp1 = hp_of(sid, rid)
        for u in [tgt] + bh:
            print("  u%s PRE %s" % (u, pre[u]))
            print("  u%s POST %s" % (u, eff_names(dv, u)))
        print("  hp delta:", {k: (hp0[k][0], hp1[k][0]) for k in hp0 if hp0[k][0] != hp1[k][0]})
        print("  events  :", json.dumps(r.get("events") or [], default=str)[:2500])
    finally:
        dispose(sid, rid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="all",
                    choices=["toggle", "exemplar", "supercharge", "all"])
    a = ap.parse_args()
    sid = R._resolve_session()
    try:
        if a.case in ("toggle", "all"):
            case_toggle(sid)
        if a.case in ("exemplar", "all"):
            case_exemplar(sid)
        if a.case in ("supercharge", "all"):
            case_supercharge(sid)
    finally:
        for rid in list(_rids):
            dispose(sid, rid)


if __name__ == "__main__":
    main()
