#!/usr/bin/env python
"""DECOMPOSITION PAR ETAGE du residu `blackObliterator` (case-o10 SS 6) : separer la PHASE D'ARME
du canal COUPS ADDITIONNELS (#179), au lieu de chercher un ratio sur le total.

LEVIER DE SEPARATION -- le gate natif `IsRangedAttack` du trigger de
`IdunBattle.Entities.Effects.Loki.BaseFleshmetalGunsEffect$$CreateAdditionalHits`
(`condition = OwnerIsCaster & IsRangedAttack`) : en MELEE, le passif FleshmetalGuns ne produit
AUCUN groupe. Une attaque de melee de Volk n'exerce donc que la PHASE D'ARME
(`IdunBattle.Operations.AttackDamageOperation$$ExecuteHits`), la meme ou l'attaque ranged en
exerce DEUX etages empiles.

    melee  d'accord live/offline + ranged en desaccord  => l'ecart est dans le canal #179
    melee  en desaccord                                 => l'ecart est dans la phase d'arme
                                                           (mods attaquant / percage / armure)

Le montage force `--hp-target` HAUT (la cible survit -> aucune attaque n'est ecretee par
l'overkill, donc TOUTES sont discriminantes) ET `--armor-target` pour RESTAURER l'armure que
`--hp-target` met a zero (piege de mesure documente : sans lui, l'etage armure disparait).

Positions DRIVEES (doctrine : jamais « bloque par la geometrie de spawn ») -- `applyAction` ne
verifie pas la propriete du `unitId`, donc on deplace la CIBLE au contact de Volk.

Usage :
  python probe_o10_volk_stage_split.py --dist 1     # MELEE  (phase d'arme seule)
  python probe_o10_volk_stage_split.py --dist 3     # RANGED (arme + canal #179)
ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc            # noqa: E402
from engine.entities.pathfinding.board import Board            # noqa: E402
from engine.entities.stats import StatType                     # noqa: E402
from engine.runner.components import (HealthComponent, PositionComponent,   # noqa: E402
                                      StatsComponent)
from engine.runner.messages import AttackUnitMessage           # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister         # noqa: E402
from engine.runner.runner import Runner                        # noqa: E402
from engine.runner.snapshot import load_state                  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_o10_volk_split_state.json"

CARRIER = "blackObliterator"
P_UNITS = "blackObliterator,adeptHospitaller"
A_UNITS = "necroWarden,necroWarden"
ARMOR = 2008          # armure NATIVE de necroWarden au rank courant (mesuree, cf. probe residu)


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(s["mt"]), s["mti"]
    return rng


def build(seed, board, hp, armor):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(STATE), "--board", board, "--roster", "2",
           "--p-units", P_UNITS, "--a-units", A_UNITS]
    if hp:                       # 0 = stats NATIVES (ni PV ni armure forces)
        cmd += ["--hp-target", str(hp)]
    if armor:
        cmd += ["--armor-target", str(armor)]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[split] build KO: %s" % ((proc.stderr or proc.stdout or "")[-600:],))
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def _dv(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def _find(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row"))


def place_target_at_distance(rpc, rid, board, dist, w=7, h=9, at_att=None, at_tgt=None):
    """DRIVE la CIBLE (unite ADVERSE) sur une tuile a `dist` hex de Volk. `applyAction` ne verifie
    pas la propriete du `unitId` -> on pilote les deux camps. Rend (volk_id, tgt_id) ou None.

    `at_att`/`at_tgt` (col,row) : positions EXACTES imposees -- necessaires pour rejouer la
    GEOMETRIE du montage d'origine (l'elevation entre dans le calcul de degat, et une difference
    d'elevation non voulue a deja ete lue a tort comme un bug moteur, cf. #63)."""
    dv = _dv(rpc, rid)
    volk = _find(dv, CARRIER)
    if volk is None:
        return None
    my = volk.get("owner")
    foes = [u for u in (dv.get("units") or [])
            if u.get("owner") != my and u.get("alive") and (u.get("pos") or {}).get("col") is not None]
    if not foes:
        return None
    tgt = foes[0]
    if at_att is not None:
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": volk["id"], "to": {"col": at_att[0], "row": at_att[1]}}}, 60)
        volk = _find(_dv(rpc, rid), CARRIER) or volk
    vp = _pos(volk)
    if at_tgt is None and dist is not None:
        # tuiles du BOARD REEL a `dist` hex de Volk (pas un rectangle en dur : le probe doit tourner
        # sur n'importe quel `--board`, cf. discipline de generalisation de runner.md SS 3).
        occupied = {_pos(u) for u in (dv.get("units") or []) if u.get("alive")} - {_pos(tgt)}
        ring = [board.coord(t) for t in sorted(board.by_id)
                if board.walkable(t) and board.coord(t) not in occupied
                and hexgeo.distance(board.coord(t), vp) == dist]
        for t in ring[:16]:
            r = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": tgt["id"], "to": {"col": t[0], "row": t[1]}}}, 60)
            if isinstance(r, dict) and r.get("ok"):
                t2 = _find(_dv(rpc, rid), tgt.get("visualId"))
                if t2 is not None and hexgeo.distance(_pos(t2), vp) == dist:
                    return volk["id"], tgt["id"]
        return None
    if at_tgt is not None:
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": tgt["id"], "to": {"col": at_tgt[0], "row": at_tgt[1]}}}, 60)
        t2 = _find(_dv(rpc, rid), tgt.get("visualId"))
        if t2 is not None and _pos(t2) == tuple(at_tgt):
            return volk["id"], tgt["id"]
        print("[split] placement EXACT de la cible en %s REFUSE (%s)" % (at_tgt, _pos(t2)))
        return None
    occupied = {_pos(u) for u in (dv.get("units") or []) if u.get("alive")} - {_pos(tgt)}
    cands = [t for t in hexgeo.ring(vp[0], vp[1], dist)
             if 0 <= t[0] < w and 0 <= t[1] < h and t not in occupied
             and board.walkable(board.id_at(t[0], t[1]))]
    for t in cands:
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": tgt["id"], "to": {"col": t[0], "row": t[1]}}}, 60)
        if isinstance(r, dict) and r.get("ok"):
            dv2 = _dv(rpc, rid)
            t2 = _find(dv2, tgt.get("visualId"))
            if t2 is not None and hexgeo.distance(_pos(t2), vp) == dist:
                return volk["id"], tgt["id"]
    return None


def _fmt(last):
    if not last:
        return "<aucun attack dict>"
    ah = last.get("additional_hits")
    ahs = "None" if not isinstance(ah, dict) else ", ".join(
        "%s=%r" % (k, v) for k, v in sorted(ah.items()) if k != "death")
    return ("base=%s pierce=%s armor=%s hits=%s ranged=%s profile=%s clean=[%s,%s] total=%s "
            "per_hit=%s rolls=%s addhits=(%s)" % (
                last.get("base"), last.get("pierce"), last.get("armor"), last.get("hits"),
                last.get("ranged"), last.get("profile"), last.get("clean_min"),
                last.get("clean_max"), last.get("total"), last.get("per_hit"),
                last.get("rolls"), ahs))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--dist", type=int, default=1, help="1 = melee, >=2 = ranged")
    ap.add_argument("--hp", type=int, default=900000, help="0 = PV natifs (aucun --hp-target)")
    ap.add_argument("--armor", type=int, default=ARMOR, help="0 = armure native")
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--at-att", default=None, help="position EXACTE de Volk 'col,row'")
    ap.add_argument("--at-tgt", default=None, help="position EXACTE de la cible 'col,row'")
    ap.add_argument("--move-volk", action="store_true",
                    help="DEPLACE Volk (arme UnitFlag.Moved) avant de tirer, en gardant la portee")
    args = ap.parse_args(argv)
    at_att = tuple(int(x) for x in args.at_att.split(",")) if args.at_att else None
    at_tgt = tuple(int(x) for x in args.at_tgt.split(",")) if args.at_tgt else None

    sid = _resolve_session()
    rid = build(args.seed, args.board, args.hp, args.armor)
    rpc = lambda m, b, t=90: _r(sid, m, b, t)           # noqa: E731
    print("[split] sid=%s runner=%s seed=%s dist=%s hp=%s armor=%s"
          % (sid, rid, args.seed, args.dist, args.hp, args.armor))
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print("[split] boardGraph KO"); return 2
        board = Board(bg["tiles"], adjacency="evenq")

        n = 0
        for it in range(args.rounds):
            pl = place_target_at_distance(rpc, rid, board, args.dist,
                                          at_att=at_att, at_tgt=at_tgt)
            if pl is not None and args.move_volk:
                # ARME le flag `UnitFlag.Moved` du PORTEUR : un deplacement REEL de Volk (tuile de
                # `aiMovableTiles`, donc accepte par le moteur -> `SetMovedFlag` pose cote natif) qui
                # garde la cible a portee de son arme ranged (range 3).
                volk_id, tgt_id_ = pl
                dvm = _dv(rpc, rid)
                tp_ = _pos(next((u for u in (dvm.get("units") or [])
                                 if u.get("id") == tgt_id_), {}))
                cur = _pos(_find(dvm, CARRIER) or {})
                mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60) or {}
                cmt = next((x for x in (mt.get("units") or [])
                            if x.get("unitId") == volk_id), None)
                cand = [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])
                        if (t["col"], t["row"]) != cur
                        and 2 <= hexgeo.distance((t["col"], t["row"]), tp_) <= 3]
                moved_ok = False
                for c in cand[:10]:
                    rpc("applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": volk_id, "to": {"col": c[0], "row": c[1]}}}, 60)
                    if _pos(_find(_dv(rpc, rid), CARRIER) or {}) == c:
                        moved_ok = True
                        break
                print("[split] move-volk applique=%s" % moved_ok)
            if pl is None:
                print("[split] placement impossible a dist=%d (it=%d)" % (args.dist, it))
                break
            volk_id, tgt_id = pl

            dv = _dv(rpc, rid)
            if dv.get("currentPlayer") != (_find(dv, CARRIER) or {}).get("owner") \
                    or volk_id not in (dv.get("toActivate") or []):
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            norm = next((a for a in ((_find(dv, CARRIER) or {}).get("abilities") or [])
                         if a.get("kind") == "normal"), None)
            if norm is None:
                print("[split] pas d'attaque normale"); break

            ob = rpc("observeBattle", {"runnerId": rid}, 60)
            snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
            s1 = rpc("dumpRng", {"runnerId": rid}, 30)
            if not _ok(s1):
                print("[split] dumpRng KO"); break
            state = load_state(dv, ob, snap, board=board)
            state.rng = _seed_rng(s1)
            hp0 = state.get_entity(tgt_id).get_component(HealthComponent).hp
            sc = state.get_entity(tgt_id).get_component(StatsComponent)
            pa = state.get_entity(volk_id).get_component(PositionComponent)
            pt = state.get_entity(tgt_id).get_component(PositionComponent)
            d = hexgeo.distance((pa.col, pa.row), (pt.col, pt.row))
            volk_live = _find(dv, CARRIER) or {}
            tgt_live = next((u for u in (dv.get("units") or []) if u.get("id") == tgt_id), {})
            print("\n[split] --- it %d : dist=%d att=(%s,%s) tgt=(%s,%s) hp_tgt=%s"
                  % (it, d, pa.col, pa.row, pt.col, pt.row, hp0))
            print("[split]     armure off: FIXED=%s ARMOR=%s | elev att=%s tgt=%s"
                  % (sc.ctx.stat(StatType.FIXED_ARMOR) if sc is not None else None,
                     sc.ctx.stat(StatType.ARMOR) if sc is not None else None,
                     board.elevation(board.id_at(pa.col, pa.row)),
                     board.elevation(board.id_at(pt.col, pt.row))))
            print("[split]     effets_att=%s | effets_tgt=%s"
                  % ([e.get("name") for e in (volk_live.get("effects") or [])],
                     [e.get("name") for e in (tgt_live.get("effects") or [])]))
            # GEOMETRIE COMPLETE : la famille RangedInMelee de
            # `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction`
            # depend d'un ennemi ADJACENT a l'ATTAQUANT -- donc des positions de TOUTES les unites,
            # pas seulement du couple attaquant/cible.
            print("[split]     board: %s" % ([
                "u%s/%s/own%s@(%s,%s)%s" % (
                    u.get("id"), u.get("visualId"), u.get("owner"),
                    (u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"),
                    "" if u.get("alive") else "/DEAD")
                for u in (dv.get("units") or [])],))
            adj_foes = [u.get("visualId") for u in (dv.get("units") or [])
                        if u.get("alive") and u.get("owner") != volk_live.get("owner")
                        and (u.get("pos") or {}).get("col") is not None
                        and hexgeo.distance(_pos(u), (pa.col, pa.row)) == 1]
            print("[split]     ennemis ADJACENTS a Volk = %s  (gate RangedInMelee)" % (adj_foes,))

            rpc("hitTraceReset", {"runnerId": rid}, 20)
            rpc("hitTraceArm", {}, 30)
            res = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": volk_id, "targetId": tgt_id,
                "abilityType": norm["id"]}}, 60)
            ht = rpc("hitTrace", {"runnerId": rid, "limit": 60}, 30)
            if not (_ok(res) and (res.get("actions") or [{}])[0].get("ok")):
                print("[split] applyAction KO -> endturn")
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            live_hp = next((u.get("hp") for u in (res.get("units") or [])
                            if u.get("squadId") == tgt_id), None)
            s2 = rpc("dumpRng", {"runnerId": rid}, 30)
            live_mt = (list(s2["mt"]), s2["mti"]) if _ok(s2) else None
            if live_mt is not None and live_mt[1] == s1["mti"] and live_mt[0] == list(s1["mt"]):
                print("[split] NOOP live -> ignore")
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue

            runner = Runner(state).install_default_handlers(20)
            runner.apply(AttackUnitMessage(volk_id, tgt_id))
            off_hp = state.get_entity(tgt_id).get_component(HealthComponent).hp
            last = runner.damage_handler.last or {}
            lh = (ht.get("hits") or []) if isinstance(ht, dict) else []
            print("[split] LIVE degat=%s | OFF degat=%s | ECART=%s"
                  % ((hp0 - live_hp) if live_hp is not None else None, hp0 - off_hp,
                     (hp0 - off_hp) - (hp0 - live_hp) if live_hp is not None else None))
            print("[split] OFF %s" % _fmt(last))
            print("[split] LIVE coups=%d seq=%s" % (
                len(lh), [(h.get("hitIndex"), h.get("profile")) for h in lh]))
            print("[split] mti off=%s live=%s mt_same=%s" % (
                state.rng.mti, live_mt[1] if live_mt else None,
                (list(state.rng.mt), state.rng.mti) == (live_mt[0], live_mt[1])))
            n += 1
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        print("\n[split] confrontations=%d" % n)
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print("[split] runner %s dispose" % rid)
        except Exception as e:
            print("[split] dispose KO: %s" % e)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
