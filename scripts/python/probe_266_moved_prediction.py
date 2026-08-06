"""#266 -- le flag `UnitFlag.Moved` sur la face PREDICTION : decomposition par etage.

QUESTION BINAIRE. Sur un montage ou le caster A REELLEMENT BOUGE, la prediction offline rend-elle le
MEME degat que le natif -- c'est-a-dire SANS le +25% ranged que le gate no-move de
`IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier`
(`OwnerIsCaster & IsRangedAttack & ... & (!HasFlag(Moved=0) | HasFlag(Teleported=0xc))`) doit couper ?

MECANIQUE (decompile = verite). `CalculateAttackerModifiersForPrediction` ne substitue QUE la
POSITION (`AbilityEntities+0x40`) ; les flags sont lus sur l'ECS COURANT par
`HasFlagAbilityTrigger$$ShouldTrigger` -> `UnitFlagsComponent$$Has`. Mais une prediction depuis une
tuile AUTRE que la tuile courante passe par
`IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile`, qui appelle le MEME
`IdunBattle.Entities.UnitExtensions$$SetMovedFlag` que `MoveUnitOperation$$Execute` avant d'executer
l'action (puis restaure). Le choix est lu verbatim dans
`SimulateEffectsOperation.u003Cu003Ec__DisplayClass5_0u003C...u003E$$u003CExecuteu003Eb__0` :

    if (UnitPosition.op_Equality(GetUnitPosition(state, unit), simulatedPos))
        DoActionInSimulatedOnSameTile(...)   // AUCUN SetMovedFlag
    else
        DoActionInSimulatedTile(...)         // SetMovedFlag

=> `has_moved` vu par la prediction = `(tuile != tuile courante)` **OU** `HasFlag(u, Moved)`. Le port
ne portait que le PREMIER terme.

DEUX MESURES.

  A) BALAYAGE DE TUILES, un runner, caster NON deplace (tour cycle -> `RemoveTurnFlags` a purge
     `Moved`, positions conservees). On interroge l'utilite native de CHAQUE tuile du movable set.
     Discrimine « le natif traite la tuile simulee comme un deplacement » de « c'est l'elevation ou
     la distance qui varie ».

  B) RUNNERS JUMEAUX, meme seed / board / roster / geometrie, caster sur LA MEME tuile T1, le flag
     `Moved` etant le SEUL ecart :
       * runner A -- on deplace le caster sur T1 PUIS on cycle le tour : il est en T1, flag ABSENT ;
       * runner B -- on cycle le tour PUIS on deplace le caster sur T1 : il est en T1, flag POSE.
     Deux runners plutot qu'un seul, parce que l'instance par defaut est
     `CachedDamagePredictionQuery` (cle {unit, tile, ability}) : re-interroger la MEME tuile apres
     une mutation rendrait une valeur potentiellement STALE, et une egalite se lirait a tort comme
     « le flag n'a aucun effet ».

ORACLE NATIF = `pairUtility` (`ComparablePlaybook$$CalculateUtilityFromPredictions`). Ce n'est PAS
`aiPlaybookPredict` / `aiPredict` : sur le build `rnca9r7q6c` leur decodage de `ProbableDamageEvent`
/ `DamagePredictionResult` est PERIME -- `healthDmg{Min,Max}` rendus a 0 avec un `hpBefore` correct,
`targetId` a `null`, `appliedHits` valant un PV. Regression d'outillage PRE-EXISTANTE (elle rougit
deja `test_ability_hits_channel_live::test_frenzied_firing_aoe_batch_matches_native` sur master),
cote hooks, donc hors de portee sans reinjection. `pairUtility` ne lit qu'un Fix64 et reste sain.
L'utilite est MONOTONE en degat : elle discrimine le sens, la MAGNITUDE exacte (x1.25) est lue cote
port et, sur la face combat, par `test_heavy_weapon_moved_gate_live` (bit-exact).

CIBLE = `orksNob` (ni Mechanical, ni MkXGravis, ni TerminatorArmour) -> la `DamageCondition` de
`HeavyGravCannonEffect` est FAUSSE, ce passif est INERTE. CASTER = `admecDestroyer`, dont
`HeavyWeapon` est le SEUL trait a modifier le degat en %.

Aucune valeur attendue codee en dur : l'oracle est le natif qui tourne. ASCII only.

CLI (depuis scripts/python) :
  python probe_266_moved_prediction.py --board MC1_67 --seed 26601
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import hexgeo
import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

CASTER_VIS = "admecDestroyer"       # Sy-Gex : trait HeavyWeapon (+25% ranged not-moved), portee 3
TARGET_VIS = "orksNob"              # HeavyGravCannon INERTE (aucun des 3 traits de sa condition)
FILLER_VIS = "necroWarden"
NORMAL_ATTACK = 69                  # `Loki_NormalAttack` de admecDestroyer (ActiveAbilityType per-unit)


def _res(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=120):
    return _res(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def decision(sid, rid):
    return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _find(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _move(sid, rid, uid, coord):
    return rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": coord[0], "row": coord[1]}}}, 60)


def build(sid, seed, board):
    state = ROOT / "logs" / "runners" / f"probe266-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--roster", "1",
            "--p-units", CASTER_VIS, "--a-units", f"{TARGET_VIS},{FILLER_VIS}",
            "--hp-target", "300000"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("build KO: %s" % ((p.stderr or p.stdout or "")[-600:]))
        return None, state
    return json.loads(state.read_text())["runnerId"], state


def my_turn(sid, rid, owner, max_turns=10):
    """Avance jusqu'au tour du proprietaire. Chaque entree de tour purge `UnitFlag.Moved`
    (`StartTurnOperation$$Execute` -> `UnitFlagsComponent$$RemoveTurnFlags`)."""
    for _ in range(max_turns):
        if decision(sid, rid).get("currentPlayer") == owner:
            return True
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return False


def cycle_turn(sid, rid, owner):
    """Termine mon tour puis y revient : positions conservees, flags de tour purges."""
    rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return my_turn(sid, rid, owner)


def unit_flags(sid, rid, uid):
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
    row = next((u for u in (snap.get("units") or []) if u.get("entityId") == uid), {})
    return row.get("unitFlags"), (snap.get("unitFlagTypes") or {}).get("Moved")


def native_utility(sid, rid, cid, tid, coord=None):
    body = {"runnerId": rid, "unitId": cid, "targetId": tid, "abilityType": NORMAL_ATTACK}
    if coord is not None:
        body["col"], body["row"] = coord[0], coord[1]
    r = rpc(sid, "pairUtility", body, 90)
    if not (isinstance(r, dict) and r.get("ok")):
        return None, r
    return r.get("utility"), r


def port_pred(sid, rid, cid, tid, dv, coord):
    from engine.playbook import scene as SC
    from engine.playbook.scene import Scene
    from engine.playbook.prediction.normal_attack import make_normal_attack_predictions
    predictor = SC.build_predictor(lambda m, b=None, t=120: rpc(sid, m, b, t), rid)
    sctx = SC.step_context(predictor, dv)
    scene = Scene.from_predictor_sctx(predictor, sctx, None)
    ev = make_normal_attack_predictions(scene, cid, tid, attack_pos=coord)
    if ev is None:
        return None, scene
    return (ev.prediction.accurate_health_damage.min,
            ev.prediction.accurate_health_damage.max), scene


def movable(sid, rid, cid):
    mt = rpc(sid, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
    row = next((x for x in (mt.get("units") or []) if x.get("unitId") == cid), None)
    return [(t["col"], t["row"]) for t in ((row or {}).get("tiles") or [])]


def stage(sid, rid, board, elev, keep_moved_flag: bool):
    """Monte la geometrie COMMUNE puis place le caster sur T1.

    Sequence commune : caster -> `home` (plein champ), cible a distance 2, remplissage parque loin,
    puis DEUX cycles de tour au total, et un deplacement `home` -> T1. Le SEUL ecart entre les deux
    variantes est l'ORDRE du dernier cycle :

      `keep_moved_flag=True`  -> cycle, cycle, move : le caster est en T1 avec `Moved` POSE ;
      `keep_moved_flag=False` -> cycle, move, cycle : il est en T1 avec `Moved` PURGE.

    Meme nombre de tours ecoules des deux cotes (donc meme `turnsStarted`, meme etat d'effets), meme
    tuile finale, meme geometrie. Rend (cid, tid, t1, home) ou None."""
    walk = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]

    def nb_free(c):
        return [n for n in board.neighbours(board.id_at(c[0], c[1])) if board.walkable(n)]

    dv = decision(sid, rid)
    me = _find(dv, CASTER_VIS)
    if me is None:
        return None
    owner = me.get("owner")
    if not my_turn(sid, rid, owner):
        return None
    dv = decision(sid, rid)
    me, tgt = _find(dv, CASTER_VIS), _find(dv, TARGET_VIS)
    if me is None or tgt is None:
        return None
    cid, tid = me["id"], tgt["id"]

    # PLEIN CHAMP : caster sur une tuile a 6 voisins marchables, cible degagee a distance 2.
    open_tiles = [c for c in walk if len(nb_free(c)) == 6]
    if not open_tiles:
        return None
    home = open_tiles[len(open_tiles) // 2]
    _move(sid, rid, cid, home)
    dv = decision(sid, rid)
    home = _pos(_find(dv, CASTER_VIS)) or home
    spots = [c for c in open_tiles if hexgeo.distance(c, home) == 2 and c != home]
    if not spots:
        return None
    _move(sid, rid, tid, spots[0])
    dv = decision(sid, rid)
    far = [c for c in walk if hexgeo.distance(c, home) > 6]
    for i, u in enumerate(dv.get("units") or []):
        if u.get("alive") and u.get("id") not in (cid, tid) and i < len(far):
            _move(sid, rid, u["id"], far[i])

    # Le caster a deja consomme son deplacement pour rejoindre `home` : on cycle une premiere fois
    # avant de choisir T1 (le movable set doit etre celui d'un caster qui n'a pas encore bouge).
    if not cycle_turn(sid, rid, owner):
        return None

    # T1 : tuile candidate a MEME elevation et MEME distance a la cible que `home` -- ni l'elevation
    # ni la portee ne changent entre les deux runners jumeaux (ils sont de toute facon identiques,
    # mais T1 doit rester comparable a `home` pour le balayage A).
    dv = decision(sid, rid)
    tpos = _pos(next(u for u in dv["units"] if u.get("id") == tid))
    cands = [c for c in movable(sid, rid, cid)
             if c != home and elev.get(c) == elev.get(home)
             and hexgeo.distance(c, tpos) == hexgeo.distance(home, tpos)]
    if not cands:
        return None
    t1 = cands[0]

    if keep_moved_flag:
        if not cycle_turn(sid, rid, owner):          # 2e cycle AVANT le pas -> le flag survit
            return None
        _move(sid, rid, cid, t1)
    else:
        _move(sid, rid, cid, t1)
        if not cycle_turn(sid, rid, owner):          # 2e cycle APRES le pas -> le flag est purge
            return None
    if _pos(_find(decision(sid, rid), CASTER_VIS)) != t1:
        return None
    return cid, tid, t1, home


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sid", type=int)
    ap.add_argument("--seed", default="26601")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    sid = a.sid or R._resolve_session()
    from engine.entities.pathfinding.board import Board
    runners = []
    try:
        # ---------- (A) BALAYAGE DE TUILES, caster NON deplace -------------------------------
        rid, st = build(sid, a.seed, a.board)
        if rid is None:
            return 2
        runners.append((rid, st))
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        elev = {(t["col"], t["row"]): int(t.get("elevation") or 0) for t in board.by_id.values()}
        dv = decision(sid, rid)
        me = _find(dv, CASTER_VIS)
        owner = me.get("owner")
        staged = stage(sid, rid, board, elev, keep_moved_flag=False)
        if staged is None:
            print("(A) montage impossible")
            return 2
        cid, tid, t1, home = staged
        dv = decision(sid, rid)
        cpos = _pos(_find(dv, CASTER_VIS))
        tpos = _pos(next(u for u in dv["units"] if u.get("id") == tid))
        flags_a, moved_id = unit_flags(sid, rid, cid)
        print("\n[#266 A] runner=%s board=%s caster u%s @%s (elev %s) cible u%s @%s (d=%s) "
              "unitFlags=%s (Moved id=%s)"
              % (rid, a.board, cid, cpos, elev.get(cpos), tid, tpos,
                 hexgeo.distance(cpos, tpos), flags_a, moved_id))
        if not isinstance(flags_a, list):
            print("  !! unitFlags NON MESURE (null) : canal mort, rien n'est concluant")
            return 2
        if moved_id in flags_a:
            print("  !! flag Moved encore pose apres le cycle de tour -- protocole casse")
            return 2
        u_cur, _ = native_utility(sid, rid, cid, tid)
        print("  utilite native TUILE COURANTE (non deplace) = %s" % (u_cur,))
        rows = []
        for c in movable(sid, rid, cid):
            if c == cpos:
                continue
            u, _ = native_utility(sid, rid, cid, tid, c)
            rows.append((c, elev.get(c), hexgeo.distance(c, tpos), u))
        for c, e, d, u in rows:
            print("  tuile %-8s elev=%s d=%s -> %s" % (str(c), e, d, u))
        in_range = sorted({u for _c, _e, d, u in rows if d <= 3 and u is not None})
        print("  => %d valeur(s) distincte(s) sur les tuiles SIMULEES en portee : %s"
              % (len(in_range), in_range))
        if u_cur is not None and len(in_range) == 1:
            print("  => ni l'elevation ni la distance ne discriminent ; ratio courante/simulee = %s"
                  % round(u_cur / in_range[0], 5))

        # ---------- (B) RUNNERS JUMEAUX : meme tuile T1, le flag SEUL change ------------------
        rid_b, st_b = build(sid, a.seed, a.board)
        if rid_b is None:
            return 2
        runners.append((rid_b, st_b))
        staged_b = stage(sid, rid_b, board, elev, keep_moved_flag=True)
        if staged_b is None:
            print("(B) montage impossible")
            return 2
        cid_b, tid_b, t1_b, _ = staged_b
        dv_b = decision(sid, rid_b)
        cpos_b = _pos(_find(dv_b, CASTER_VIS))
        tpos_b = _pos(next(u for u in dv_b["units"] if u.get("id") == tid_b))
        flags_b, _ = unit_flags(sid, rid_b, cid_b)
        print("\n[#266 B] runner=%s caster u%s @%s cible u%s @%s (d=%s) unitFlags=%s"
              % (rid_b, cid_b, cpos_b, tid_b, tpos_b,
                 hexgeo.distance(cpos_b, tpos_b), flags_b))
        if cpos_b != cpos or tpos_b != tpos:
            print("  !! geometries A/B differentes (%s/%s vs %s/%s) -- non comparables"
                  % (cpos_b, tpos_b, cpos, tpos))
            return 2
        if not isinstance(flags_b, list) or moved_id not in flags_b:
            print("  !! le caster de B ne porte PAS Moved -- protocole casse")
            return 2

        u_b, _ = native_utility(sid, rid_b, cid_b, tid_b)
        p_a, _ = port_pred(sid, rid, cid, tid, dv, cpos)
        p_b, _ = port_pred(sid, rid_b, cid_b, tid_b, dv_b, cpos_b)

        print("\n  --- VERDICTS (meme tuile %s, meme geometrie, le flag Moved SEUL change) ---" % (cpos,))
        print("  NATIF  : A (flag absent) = %s   B (flag pose) = %s" % (u_cur, u_b))
        if u_cur and u_b:
            print("           ratio A/B = %s  (aucun ecart => la prediction native ignorerait le flag)"
                  % round(u_cur / u_b, 5))
        print("  PORT   : A = %s   B = %s" % (p_a, p_b))
        if p_a and p_b and p_b[0]:
            print("           ratio A/B = (%s, %s)  (attendu 1.25 = heavyWeaponExtraDmg)"
                  % (round(p_a[0] / p_b[0], 5), round(p_a[1] / p_b[1], 5)))
        return 0
    finally:
        if not a.keep:
            for rid_, st_ in runners:
                try:
                    rpc(sid, "disposeRunner", {"runnerId": rid_}, 20)
                except Exception:
                    pass
                try:
                    st_.unlink()
                except Exception:
                    pass


if __name__ == "__main__":
    raise SystemExit(main())
