"""#61 (a) -- VOLET AoE de FrenziedFiring (1036) : le 2e batch du playbook natif vs le port.

`IdunBattle.AI.Playbook.Loki.FrenziedFiringPlaybook$$MakeDamagePredictions` appelle DEUX fois
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions` :

  1. `targets = Target@0x178`, `hits = Evaluate(FrenziedFiringAbility$$GetHitsForOriginalTarget)`
     (base GEOMETRIQUE -- deja portee et validee, case-61 #3) ;
  2. `targets = IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$GetTargets`
     = `DSLFactory.AdjacentEnemies(caster@0x160, TargetTiles@0x190, 1)`
     = `Enemies(caster, Units(AdjacentTiles(tuile de la cible)) - tuile de la cible)`,
     `hits = 1` **LITTERAL** (immediat du call-site) ; ses events sont CONCATENES au batch 1.

Ce probe DRIVE la geometrie (place K ennemis autour de la cible) et confronte, event par event,
l'oracle natif (`aiPlaybookPredict`, qui invoque le `MakeDamagePredictions` natif et decode TOUS
les events) au port (`engine.playbook.prediction.make_damage_predictions`).

Aucune valeur attendue codee en dur : l'oracle est le natif qui tourne. ASCII only.

CLI (depuis scripts/python) :
  python probe_61c_frenzy_aoe.py --board MC1_67 --seed 61201 --k 3
  python probe_61c_frenzy_aoe.py --board MC1_67 --seed 61201 --k 0     # volet AoE inerte
  python probe_61c_frenzy_aoe.py --runner R --sid S --caster U --target T   # runner deja monte
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

FRENZY = 1036
FRENZY_NAME = "FrenziedFiring"
CASTER_VIS = "blackObliterator"
FOE_VIS = ["necroWarden", "templChampion", "ultraTitus", "astraBullgryn"]


def _res(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=120):
    return _res(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def decision(sid, rid):
    return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _move(sid, rid, uid, coord):
    rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": coord[0], "row": coord[1]}}}, 60)


def build(sid, seed, board):
    """Monte un runner ISOLE (state-file dans logs/, hors data/) et rend son runnerId."""
    state = ROOT / "logs" / f"probe61c-{seed}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--roster", "1",
            "--p-units", CASTER_VIS, "--a-units", ",".join(FOE_VIS),
            "--hp-target", "90000"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("build KO: %s" % ((p.stderr or p.stdout or "")[-500:]))
        return None, state
    return json.loads(state.read_text())["runnerId"], state


def _my_turn(sid, rid, owner, max_turns=8):
    for _ in range(max_turns):
        if decision(sid, rid).get("currentPlayer") == owner:
            return True
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return False


def native_events(sid, rid, cid, tid):
    """Oracle natif : TOUS les ProbableDamageEvent rendus par le MakeDamagePredictions natif."""
    r = rpc(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": cid,
                                       "targetId": tid, "abilityType": FRENZY}, 90)
    return [(e.get("targetId"), e.get("appliedHits"), e.get("healthDmgMin"),
             e.get("healthDmgMax")) for e in ((r or {}).get("events") or [])], r


def port_events(sid, rid, cid, tid, dv):
    """Port : `make_damage_predictions` sur le meme etat live."""
    from engine.playbook import scene as SC
    from engine.playbook.scene import Scene
    from engine.playbook import prediction as PRED
    predictor = SC.build_predictor(lambda m, b=None, t=120: rpc(sid, m, b, t), rid)
    sctx = SC.step_context(predictor, dv)
    scene = Scene.from_predictor_sctx(predictor, sctx, None)
    evs = PRED.make_damage_predictions(scene, cid, tid, FRENZY, FRENZY_NAME,
                                       attack_pos=scene.pos(cid)) or []
    return [(e.target, e.prediction.applied_hits, e.prediction.accurate_health_damage.min,
             e.prediction.accurate_health_damage.max) for e in evs]


def _fmt(rows):
    return " ".join("u%s:h%s[%s,%s]" % r for r in sorted(rows, key=lambda x: (x[0] or 0)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sid", type=int)
    ap.add_argument("--runner", type=int)
    ap.add_argument("--seed", default="61201")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--k", type=int, default=3, help="nb d'ennemis places autour de la cible")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    sid = a.sid or R._resolve_session()
    state = None
    rid = a.runner
    if rid is None:
        rid, state = build(sid, a.seed, a.board)
        if rid is None:
            return 2
    try:
        from engine.entities.pathfinding.board import Board
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = decision(sid, rid)
        me = next((u for u in (dv.get("units") or [])
                   if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
        foes = [u for u in (dv.get("units") or [])
                if u.get("owner") != (me or {}).get("owner") and u.get("alive")]
        if me is None or len(foes) < 1:
            print("caster/ennemis absents (me=%s foes=%d)" % (bool(me), len(foes)))
            return 2
        if not _my_turn(sid, rid, me.get("owner")):
            print("tour du caster non atteint")
            return 2

        walk = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]

        def nb_free(coord):
            return [n for n in board.neighbours(board.id_at(coord[0], coord[1]))
                    if board.walkable(n)]

        # !! LE CASTER N'EST JAMAIS DEPLACE (case-101 #6) : `applyAction move` poserait
        # `UnitFlag.Moved`, que le natif lit pour DESARMER `HeavyWeapon_ExtraDmg` (+25% ranged
        # not-moved) -- alors qu'AUCUN RPC n'expose les UnitFlags au port. Bouger le caster
        # introduirait donc un x1.25 de MESURE sur le degat, etranger au volet AoE. On deplace
        # la CIBLE et ses voisins autour du caster immobile.
        cpos = _pos(me)
        # Cible en PLEIN CHAMP (6 voisins marchables), a portee (range=3) du caster immobile,
        # dist >= 2 pour ecarter la reduction ranged-in-melee.
        open_tiles = [c for c in walk
                      if len(nb_free(c)) == 6 and 2 <= hexgeo.distance(c, cpos) <= 3]
        if not open_tiles:
            print("board sans tuile a 6 voisins marchables a portee du caster @%s" % (cpos,))
            return 2
        tcoord = max(open_tiles, key=lambda c: hexgeo.distance(c, cpos))
        tgt, others = foes[0], foes[1:]
        _move(sid, rid, tgt["id"], tcoord)
        dv = decision(sid, rid)
        tu = next((u for u in (dv.get("units") or []) if u.get("id") == tgt["id"]), None)
        tcoord = _pos(tu) or tcoord
        # Anneau exploitable : voisins marchables de la cible, hors tuile du caster.
        ring = [board.coord(n) for n in nb_free(tcoord) if board.coord(n) != cpos]

        # K ennemis SUR l'anneau, les autres LOIN (>4 hex de la cible ET du caster) -> le compte
        # AoE est PILOTE (aucun voisin parasite, aucune unite hors-scenario a portee).
        far = [c for c in walk if hexgeo.distance(c, tcoord) > 4
               and hexgeo.distance(c, cpos) > 4]
        for i, u in enumerate(others):
            if i < a.k and i < len(ring):
                _move(sid, rid, u["id"], ring[i])
            elif far:
                _move(sid, rid, u["id"], far[(i * 7) % len(far)])

        dv = decision(sid, rid)
        tu = next((u for u in (dv.get("units") or []) if u.get("id") == tgt["id"]), None)
        real = _pos(tu)
        by_id = {u.get("id"): u for u in (dv.get("units") or [])}
        adj_foes = sorted(u.get("id") for u in (dv.get("units") or [])
                          if u.get("alive") and u.get("id") != tgt["id"]
                          and u.get("owner") != me.get("owner") and _pos(u)
                          and hexgeo.distance(_pos(u), real) == 1)
        nat, raw = native_events(sid, rid, me["id"], tgt["id"])
        port = port_events(sid, rid, me["id"], tgt["id"], dv)

        print("\n[#61c frenzy AoE] runner=%s board=%s k=%d" % (rid, a.board, a.k))
        print("  caster u%s @%s | cible u%s @%s (voisins marchables=%d)"
              % (me["id"], _pos(by_id.get(me["id"])), tgt["id"], real, len(nb_free(real))))
        print("  ennemis ADJACENTS a la cible (attendu = volet AoE) : %s" % (adj_foes or "aucun"))
        print("  NATIF  (%d events) %s" % (len(nat), _fmt(nat)))
        print("  PORT   (%d events) %s" % (len(port), _fmt(port)))
        nat_h = {t: h for t, h, _, _ in nat}
        port_h = {t: h for t, h, _, _ in port}
        nat_d = {t: (lo, hi) for t, _, lo, hi in nat}
        port_d = {t: (lo, hi) for t, _, lo, hi in port}
        print("  verdict CIBLES : %s" % ("OK" if set(nat_h) == set(port_h)
                                         else "MISMATCH nat=%s port=%s"
                                              % (sorted(nat_h), sorted(port_h))))
        print("  verdict HITS   : %s" % ("OK" if nat_h == port_h
                                         else "MISMATCH nat=%s port=%s" % (nat_h, port_h)))
        print("  verdict DEGAT  : %s" % ("BIT-EXACT" if nat_d == port_d
                                         else "DIFF " + " ".join(
                                             "u%s nat%s port%s" % (t, nat_d[t], port_d.get(t))
                                             for t in sorted(nat_d) if nat_d[t] != port_d.get(t))))
        if raw and raw.get("error"):
            print("  (raw error=%s)" % raw.get("error"))
        return 0 if nat_h == port_h else 1
    finally:
        if state is not None and not a.keep:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
            state.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
