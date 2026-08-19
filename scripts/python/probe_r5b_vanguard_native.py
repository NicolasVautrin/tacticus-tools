"""R5 -- CONFRONTATION NATIVE de la passe IA generique sur un SUMMON REEL (Skitarii Vanguard).

`test_skitarii_turn_live` spawne le Vanguard OFFLINE (`_spawn_config_grot`) : aucun oracle natif
n'existe pour sa DECISION. Ce probe amene un Vanguard REEL dans le runner LIVE (le summoner
`admecMarshall` attaque -> son passif `ControlEdict` invoque le Vanguard), puis DECOMPOSE PAR ETAGE :

  etage 1 -- tuiles de deplacement : `aiMovableTiles` (natif `GetMovableTilesFor`) vs `_move_tiles` ;
  etage 2 -- degat predit par tuile : `aiPredict(col,row)` vs `make_normal_attack_predictions` ;
  etage 3 -- utilite / argmax       : action reellement jouee par le NATIF au turn-start de ma team
                                      (le trait `Summon` la fait jouer seule) vs
                                      `DefaultAiUnitTactic.calculate_next_action` du port.

Les RPC `aiMovableTiles`/`aiPredict`/`aiAttackRank` sont scopees au JOUEUR COURANT : elles ne rendent
rien pendant le tour adverse -- d'ou l'ordre (mesures pendant MON tour, puis endturn x2 pour laisser
le turn-start natif jouer le summon).

Sortie ASCII only. Usage :
    python probe_r5b_vanguard_native.py [--seed 777] [--board MC1_67]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

HOST = os.environ.get("TACTICUS_HOST", "http://127.0.0.1:8765")
PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

MARSHALL = "admecMarshall"
ENEMY = "necroWarden"
# Geometrie CIBLE (mirror du scenario offline de test_skitarii_turn_live sur MC1_67) :
POS_FOE_A = (6, 8)      # ennemi "77" du test (celui que `_pick_enemy` retient)
POS_FOE_B = (6, 7)      # ennemi "79" du test (celui que le port attaque)
POS_MARSHALL = (3, 7)   # le summon apparait dans un hex libre ADJACENT au summoner
POS_VANGUARD = (3, 7)   # ou on le CONDUIT ensuite : hex 3 des DEUX ennemis (geometrie du test R5)
POS_SANDBAG = (0, 0)    # 3e ennemi (souffre-douleur du Marshall) exile apres l'invocation
POS_MARSHALL_EXIT = (0, 4)   # le Marshall s'ecarte (son aura ProtectorImperative est adjacente)


def _http(path: str, body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(HOST + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _sid() -> int:
    return int((_http("/api/admin/status").get("session") or {}).get("id"))


def _rpc(sid: int, method: str, body: dict, timeout=120):
    r = _http(f"/api/scripts/{sid}/rpc",
              {"method": method, "args": [body], "timeout": int(timeout * 1000)}, timeout=timeout + 5)
    return r.get("result", r)


def _build(seed: str, board: str, state_file: Path) -> int:
    cmd = [sys.executable, str(PYDIR / "rl_duel.py"), "build", "--seed", seed,
           "--state-file", str(state_file), "--board", board, "--roster", "1",
           "--p-units", f"{MARSHALL},admecRuststalker",
           "--a-units", f"{ENEMY},{ENEMY},{ENEMY}"]
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PYDIR),
                         encoding="utf-8", errors="replace")
    if not state_file.exists():
        print((out.stderr or out.stdout or "")[-2500:])
        raise SystemExit("build KO")
    return int(json.loads(state_file.read_text())["runnerId"])


def _dec(sid, rid):
    return _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def _units(dec):
    return {int(u["id"]): u for u in (dec.get("units") or [])}


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _normal_id(u):
    for a in (u.get("abilities") or []):
        if a.get("kind") == "normal":
            return a.get("id")
    return None


def _move(sid, rid, uid, pos):
    r = _rpc(sid, "applyAction",
             {"runnerId": rid, "action": {"kind": "move", "unitId": int(uid),
                                          "to": {"col": int(pos[0]), "row": int(pos[1])}}}, 90)
    return bool(r.get("ok"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()

    sys.path.insert(0, str(PYDIR))
    import hexgeo

    sid = _sid()
    w = _rpc(sid, "autoBootExtraire", {}, timeout=240)
    print("amorce ok=%s" % (isinstance(w, dict) and w.get("ok")))
    sf = ROOT / "logs" / "probe_r5b_state.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    rid = _build(a.seed, a.board, sf)
    print("runner=%s" % rid)
    try:
        dec = _dec(sid, rid)
        us = _units(dec)
        mar = next(u for u in us.values() if u.get("visualId") == MARSHALL)
        mine = mar.get("team")
        foes = [u for u in us.values() if u.get("team") != mine and u.get("alive")]
        foe_a, foe_b, sandbag = foes[0], foes[1], foes[2]
        mid, aid, bid, sbid = int(mar["id"]), int(foe_a["id"]), int(foe_b["id"]), int(sandbag["id"])
        print("marshall=%s normal=%s | foes=%s" % (mid, _normal_id(mar), [int(f["id"]) for f in foes]))

        # --- 1. GEOMETRIE + invocation ---------------------------------------------------
        print("moves ok=%s" % [_move(sid, rid, mid, POS_MARSHALL),
                               _move(sid, rid, sbid, (POS_MARSHALL[0] - 1, POS_MARSHALL[1])),
                               _move(sid, rid, aid, POS_FOE_A), _move(sid, rid, bid, POS_FOE_B)])
        before = set(_units(_dec(sid, rid)))
        r = _rpc(sid, "applyAction",
                 {"runnerId": rid, "action": {"kind": "ability", "casterId": mid, "targetId": sbid,
                                              "abilityType": int(_normal_id(mar))}}, 120)
        print("attack ok=%s" % r.get("ok"))
        us = _units(_dec(sid, rid))
        van = next((u for i, u in us.items()
                    if i not in before and "vanguard" in (u.get("visualId") or "").lower()), None)
        if van is None:
            raise SystemExit("Vanguard non invoque")
        vid = int(van["id"])
        print("exile sandbag=%s / marshall=%s / vanguard->%s=%s"
              % (_move(sid, rid, sbid, POS_SANDBAG), _move(sid, rid, mid, POS_MARSHALL_EXIT),
                 POS_VANGUARD, _move(sid, rid, vid, POS_VANGUARD)))
        # FIN DE MON TOUR -> tour adverse : l'etat est FIGE (l'IA ennemie ne joue pas toute seule),
        # et le summon n'a pas encore rejoue. C'est l'instant de la confrontation.
        _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)

        dec = _dec(sid, rid)
        us = _units(dec)
        vpos = _pos(us[vid])
        print("currentPlayer=%s (MON tour)" % dec.get("currentPlayer"))
        for i in (vid, aid, bid, sbid, mid):
            u = us[i]
            print("  u%s %s pos=%s hp=%s hasAction=%s" % (i, u.get("visualId"), _pos(u),
                                                          u.get("hp"), u.get("hasAction")))
        print("vanguard@%s : hex(foeA=%s)=%s hex(foeB=%s)=%s"
              % (vpos, _pos(us[aid]), hexgeo.distance(vpos, _pos(us[aid])),
                 _pos(us[bid]), hexgeo.distance(vpos, _pos(us[bid]))))

        # --- 2. ETAGE 1 : tuiles de deplacement NATIVES ------------------------------------
        mv = _rpc(sid, "aiMovableTiles", {"runnerId": rid}, 90)
        nat_tiles = None
        for e in (mv.get("units") or []):
            if int(e.get("unitId", -1)) == vid:
                nat_tiles = sorted((t["col"], t["row"]) for t in (e.get("tiles") or []))
        print("NATIF movable(u%s) n=%s : %s" % (vid, len(nat_tiles or []), nat_tiles))

        tm = _rpc(sid, "tileMeta", {"runnerId": rid}, 90)
        elev = {}
        for t in (tm.get("tiles") or []):
            elev[(t.get("col"), t.get("row"))] = t.get("elevation")

        # --- 3. ETAT OFFLINE + etage 1/2 PORT ---------------------------------------------
        from engine.entities.pathfinding.board import Board
        from engine.runner.snapshot import load_state
        from engine.runner.prng import IntBasedMersenneTwister
        from engine.ai.state_bridge import build_from_state, _move_tiles
        from engine.ai.tactic import DefaultAiUnitTactic
        from engine.runner.components import UnitComponent, OwnerComponent, PositionComponent
        from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK
        from engine.playbook.base import tile_utility
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
        s0 = _rpc(sid, "dumpRng", {"runnerId": rid}, 30)
        tmeta = _rpc(sid, "tileMeta", {"runnerId": rid}, 90)   # #131 : effets de TUILE
        state = load_state(dec, ob, snap, board=board, tiles=tmeta)
        rng = IntBasedMersenneTwister(); rng.mt = list(s0["mt"]); rng.mti = s0["mti"]
        state.rng = rng
        ent = state.get_entity(vid)
        uc = ent.get_component(UnitComponent)
        oc = ent.get_component(OwnerComponent)
        pc = ent.get_component(PositionComponent)
        print("offline u%s visual=%s ai_controlled=%s player=%s"
              % (vid, uc.visual_id, uc.ai_controlled, oc.player))
        port_tiles = sorted((t["col"], t["row"]) for t in
                            _move_tiles(state, vid, uc.visual_id, oc.team, (pc.col, pc.row)))
        print("PORT  movable(u%s) n=%s : %s" % (vid, len(port_tiles), port_tiles))
        if nat_tiles is not None:
            print("  DIFF port-only=%s | natif-only=%s"
                  % (sorted(set(port_tiles) - set(nat_tiles)), sorted(set(nat_tiles) - set(port_tiles))))

        ctx = build_from_state(state, vid)
        plan = (getattr(ctx, "plans", None) or {}).get(vid) or {}
        print("SWEEP (cible, tuile) : elev | PORT u/tile/u_full | NATIF aiPredict")
        for ev in (plan.get("evals") or []):
            tgt = int(ev["targetId"])
            for t in sorted((t["col"], t["row"]) for t in ev["ranked"]):
                cand = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, t, tgt, ev["abilityId"])
                if cand is None:
                    print("  tgt=%s tile=%s -> None" % (tgt, t)); continue
                nat_p = _rpc(sid, "aiPredict", {"runnerId": rid, "unitId": vid, "targetId": tgt,
                                                "col": int(t[0]), "row": int(t[1]), "fresh": True}, 60)
                p = cand["pred"] or {}
                print("  tgt=%s tile=%s hex=%s elev=%s | u=%.4f tile=%.4f u_full=%.4f "
                      "| port(dmin=%s dmax=%s) | natif=%s"
                      % (tgt, t, hexgeo.distance(t, _pos(us[tgt])), elev.get(t), cand["u"],
                         tile_utility(ctx, t), cand["u_full"],
                         p.get("healthDmgMin"), p.get("healthDmgMax"),
                         {k: nat_p.get(k) for k in ("dmgMin", "dmgMax", "hits", "error")}))
        act = DefaultAiUnitTactic().calculate_next_action(ctx)
        print("PORT   action = %s" % act)

        # --- 4. NATIF : je rends la main -> turn-start de ma team -> le summon JOUE seul ---
        _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        us2 = _units(_dec(sid, rid))
        print("NATIF: vanguard %s -> %s ; foeA %s->%s ; foeB %s->%s"
              % (vpos, _pos(us2[vid]), us[aid].get("hp"), us2[aid].get("hp"),
                 us[bid].get("hp"), us2[bid].get("hp")))
    finally:
        try:
            _rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
            print("disposed runner %s" % rid)
        except Exception as ex:
            print("dispose failed: %r" % ex)


if __name__ == "__main__":
    main()
