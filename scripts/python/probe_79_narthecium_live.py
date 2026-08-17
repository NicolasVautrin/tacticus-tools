"""Probe #79 -- preuve LIVE end-to-end du revive `Narthecium` (ultraApothecary, base `ReviveEffect`).

On ne se contente PAS d'un smoke offline : on monte des runners, on DRIVE les positions des DEUX camps
(apothicaire a distance <= 2 de l'allie, ennemi au contact de l'allie), on fait REELLEMENT mourir l'allie
sous un coup MESURE, puis on lit `observeBattle`.

DISCRIMINANT (le revive-en-place est SILENCIEUX si on ne regarde que « hp a baisse ») : apres un coup dont
le degat mesure `d >= PV_avant` (donc LETAL), l'allie est
  * VIVANT (`isDead=false`) a `hp == min(reviveHP, maxPV)` -- une valeur ABSOLUE, la MEME pour deux
    `--hp-player` differents (c'est la signature du revive : l'etat de sortie ne depend plus des PV
    d'entree) -- et SUR SA PROPRE TUILE (revive EN PLACE) ;
  * ou MORT si le coup est un OVERKILL (`dmg >= 2 x PV_avant`, `overkillDmgPctOfHealth`=100), car
    `Narthecium.get_ReviveOnOverkill @vtable+0x738` = GameCamera$$ShouldBlurBackground `return 0` -> le trigger AJOUTE
    `NOT(HasFlag(dying, 8=overkill))`  =>  « unless Overkilled ».

Le probe execute les TROIS scenarios et compare (A et B = revive, C = overkill bloquant).

Chaine native prouvee : `Narthecium_ReviveEffect` (IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$.ctor / filter IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$CreateTargetFilter) sur la base
`IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger` + `IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour`
-> `IdunBattleLogic.Entities.DSLBehaviors$$Revive` -> `IdunBattle.Operations.ReviveUnitOperation$$Execute`.

Usage : python probe_79_narthecium_live.py   (ASCII only)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import hexgeo  # noqa: E402

# SORTIE de run -> `logs/` RELATIF au checkout (#314) : un chemin absolu ferait
# ecrire ce probe dans l'arbre principal depuis un worktree d'agent.
STATE = str(PYDIR.parents[1] / "logs" / "runners" / "_probe79_narthecium_state.json")
CASTER = "ultraApothecary"
ALLY = "orksNob"            # melee simple : ni deep-strike ni flying (positions pilotables directement)
FOE = "astraBullgryn"       # melee : degat de charge eleve et MESURABLE
BOARD = "MC1_67"


def rpc(sid, m, args, t=90):
    return (_rpc(sid, m, [args], timeout=t).get("result") or {})


def build(hp_player: int):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", "31337", "--rank", "17",
           "--p-units", f"{CASTER},{ALLY}", "--a-units", FOE,
           "--hp-player", str(hp_player), "--board", BOARD, "--state-file", STATE]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True)
    if p.returncode != 0:
        sys.stdout.write(p.stdout[-1500:])
        sys.stdout.write(p.stderr[-2000:])
        raise SystemExit("build KO")
    return json.loads(Path(STATE).read_text(encoding="utf-8"))["runnerId"]


def view(sid, rid):
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    obs = {u.get("visualId"): u for u in (ob.get("units") or [])}
    out = {}
    for u in (dv.get("units") or []):
        vid = u.get("visualId")
        o = obs.get(vid) or {}
        p = u.get("pos") or {}
        out[vid] = {"id": u.get("id"), "col": p.get("col", o.get("col")),
                    "row": p.get("row", o.get("row")), "hp": o.get("hp", u.get("hp")),
                    "hpMax": o.get("hpMax"), "isDead": o.get("isDead"),
                    "effects": u.get("effects"), "hasAction": u.get("hasAction")}
    return dv, out


def act(sid, rid, action, t=90):
    return rpc(sid, "applyAction", {"runnerId": rid, "action": action}, t)


def movable(sid, rid, uid):
    r = rpc(sid, "aiMovableTiles", {"runnerId": rid, "unitId": uid}, 90)
    for u in (r.get("units") or []):
        if u.get("unitId") == uid:
            return [(t.get("col"), t.get("row")) for t in (u.get("tiles") or [])]
    return [(t.get("col"), t.get("row")) for t in (r.get("unionTiles") or [])]


def step_towards(sid, rid, uid, goal, keep_near=None, keep_dist=2):
    tiles = movable(sid, rid, uid)
    if keep_near is not None:
        tiles = [t for t in tiles if hexgeo.distance(t, keep_near) <= keep_dist] or tiles
    if not tiles:
        return None
    tiles.sort(key=lambda t: hexgeo.distance(t, goal))
    act(sid, rid, {"kind": "move", "unitId": uid, "to": {"col": tiles[0][0], "row": tiles[0][1]}})
    return tiles[0]


def normal_attack_id(dv, caster_id, target_id):
    for p in (dv.get("attackPlans") or []):
        if p.get("unitId") == caster_id:
            for ev in (p.get("evals") or []):
                if ev.get("targetId") == target_id:
                    return ev.get("abilityId")
    return None


def setup(sid, hp_player):
    """Monte un runner et DRIVE la geometrie : ennemi au contact de l'allie, apothicaire a <=2.
    Retourne (rid, ids, uu) pret pour le coup fatal."""
    rid = build(hp_player)
    dv, uu = view(sid, rid)
    for k in (CASTER, ALLY, FOE):
        if k not in uu:
            raise SystemExit("MISSING %s" % k)
    cid, aid, fid = uu[CASTER]["id"], uu[ALLY]["id"], uu[FOE]["id"]
    for _ in range(12):
        dv, uu = view(sid, rid)
        fp = (uu[FOE]["col"], uu[FOE]["row"])
        apos = (uu[ALLY]["col"], uu[ALLY]["row"])
        if hexgeo.distance(apos, fp) <= 1:
            break
        step_towards(sid, rid, aid, fp)
        dv, uu = view(sid, rid)
        apos = (uu[ALLY]["col"], uu[ALLY]["row"])
        step_towards(sid, rid, cid, apos, keep_near=apos, keep_dist=2)
        act(sid, rid, {"kind": "endturn"})
        act(sid, rid, {"kind": "endturn"})
    dv, uu = view(sid, rid)
    return rid, (cid, aid, fid), dv, uu


def scenario(sid, hp_player, label):
    """Monte la geometrie, frappe UNE fois, rend l'etat observe de l'allie."""
    rid, (cid, aid, fid), dv, uu = setup(sid, hp_player)
    try:
        apos = (uu[ALLY]["col"], uu[ALLY]["row"])
        cpos = (uu[CASTER]["col"], uu[CASTER]["row"])
        d_ac = hexgeo.distance(apos, cpos)
        print("  [%s] hp_player=%d geometrie: ally=%s apo=%s d=%d (filtre IsAdjacent<=2 : %s)" % (
            label, hp_player, apos, cpos, d_ac, "OK" if d_ac <= 2 else "KO"))
        if d_ac > 2:
            return None
        nid = normal_attack_id(dv, fid, aid)
        if nid is None:
            print("  [%s] pas de plan foe->ally" % label)
            return None
        hp0 = int(uu[ALLY]["hp"])
        act(sid, rid, {"kind": "ability", "casterId": fid, "targetId": aid, "abilityType": nid})
        _, uu2 = view(sid, rid)
        u = uu2[ALLY]
        res = {"hp0": hp0, "hp1": u["hp"], "isDead": u.get("isDead"),
               "pos0": apos, "pos1": (u["col"], u["row"]),
               "apo_effects": [e.get("name") for e in (uu2[CASTER].get("effects") or [])]}
        print("  [%s] ally hp %s -> %s  isDead=%s  pos %s -> %s  (seuil overkill = 2 x %d = %d)" % (
            label, hp0, u["hp"], u.get("isDead"), apos, res["pos1"], hp0, 2 * hp0))
        return res
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        print("  [%s] runner %s dispose" % (label, rid))


def main():
    ap = argparse.ArgumentParser()
    ap.parse_args()
    sid = _resolve_session()
    print("[probe79] Narthecium (ultraApothecary) -- preuve LIVE du revive-en-place")

    # --- 0. CALIBRAGE : degat reel du coup de charge du bullgryn (PV enormes -> pas de mort).
    rid, (cid, aid, fid), dv, uu = setup(sid, 60000)
    try:
        nid = normal_attack_id(dv, fid, aid)
        hp0 = int(uu[ALLY]["hp"])
        act(sid, rid, {"kind": "ability", "casterId": fid, "targetId": aid, "abilityType": nid})
        _, uu2 = view(sid, rid)
        dmg = hp0 - int(uu2[ALLY]["hp"])
        print("[probe79] calibrage: degat du coup = %d (attaque normale ability=%s)" % (dmg, nid))
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
    if dmg <= 0:
        print("calibrage KO")
        return 4

    # --- A/B : deux PV DIFFERENTS, tous deux LETAUX mais NON-overkill (dmg < 2 x PV).
    #     Si l'allie survit aux DEUX avec le MEME hp de sortie -> c'est un REVIVE (valeur absolue).
    hp_a = int(dmg * 0.85)
    hp_b = int(dmg * 0.60)
    print("[probe79] A: PV=%d (dmg=%d letal, 2xPV=%d > dmg -> NON-overkill)" % (hp_a, dmg, 2 * hp_a))
    ra = scenario(sid, hp_a, "A")
    print("[probe79] B: PV=%d (dmg=%d letal, 2xPV=%d > dmg -> NON-overkill)" % (hp_b, dmg, 2 * hp_b))
    rb = scenario(sid, hp_b, "B")
    # --- C : PV assez bas pour que dmg >= 2 x PV -> OVERKILL -> le gate `unless Overkilled` bloque.
    hp_c = int(dmg * 0.30)
    print("[probe79] C: PV=%d (2xPV=%d <= dmg=%d -> OVERKILL)" % (hp_c, 2 * hp_c, dmg))
    rc = scenario(sid, hp_c, "C")

    ok = True
    if not (ra and rb and rc):
        print("[probe79] scenarios incomplets")
        return 1
    for tag, r in (("A", ra), ("B", rb)):
        if r["isDead"]:
            print("[probe79] KO %s: allie MORT alors que le coup n'est PAS un overkill" % tag)
            ok = False
        if r["pos0"] != r["pos1"]:
            print("[probe79] KO %s: position CHANGEE %s -> %s (revive doit etre EN PLACE)" % (
                tag, r["pos0"], r["pos1"]))
            ok = False
    if ok and ra["hp1"] != rb["hp1"]:
        print("[probe79] KO: hp de sortie A=%s != B=%s -> ce n'est pas une valeur absolue (pas un revive)"
              % (ra["hp1"], rb["hp1"]))
        ok = False
    if not rc["isDead"]:
        print("[probe79] KO C: allie VIVANT malgre l'overkill (gate `unless Overkilled` non respecte)")
        ok = False
    print("[probe79] ---- SYNTHESE ----")
    print("  degat mesure du coup           : %d" % dmg)
    print("  A  PV=%-6d -> hp=%-6s isDead=%s pos %s->%s" % (
        ra["hp0"], ra["hp1"], ra["isDead"], ra["pos0"], ra["pos1"]))
    print("  B  PV=%-6d -> hp=%-6s isDead=%s pos %s->%s" % (
        rb["hp0"], rb["hp1"], rb["isDead"], rb["pos0"], rb["pos1"]))
    print("  C  PV=%-6d -> hp=%-6s isDead=%s  (overkill attendu)" % (
        rc["hp0"], rc["hp1"], rc["isDead"]))
    print("  => hp de sortie A == B == %s : valeur ABSOLUE = min(reviveHP, maxPV) -> REVIVE" % ra["hp1"])
    print("[probe79] VERDICT: %s" % ("OK" if ok else "KO"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
