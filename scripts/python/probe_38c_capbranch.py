"""Probe #38c -- CONFRONTATION de la branche `count>0 & free>0` du gate 1118 (DoctrinaImperatives).

Chaine natif visee :
  `IdunBattle.AI.Playbook.Loki.DoctrinaImperativesPlaybook$$EvaluateNonComparable`
    -> (slot itf 0xc9) `IdunBattle.Core.Services.BattleQuery$$ReachedSummonCap`
       -> `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel(cfg, 0x31=maxSummons, level)`
          <= `IdunBattle.Entities.UnitExtensions$$GetChildrenCount(caster, entities, predicat=null)`

#38b avait etabli un A/B a DEUX points (0 summon -> pas d'emission ; >=5 summons -> emission).
Ce probe pousse la mesure sur DEUX axes que cet A/B ne tranchait pas :

  (1) SEUIL EXACT -- la leaf native `ncEvaluate(1118, sweep=false)` est lue a CHAQUE valeur de
      `summons_ever` (0,1,2,...) pendant que Tan attaque sous Protector. Le point de bascule
      no-emit -> emit donne la valeur NATIVE du cap, confrontee a
      `ability_var("ControlEdict", "maxSummons", passiveLevel)` (le mirror du port). Un A/B
      0-vs-5 reste compatible avec un cap de 1..5 ; ce balayage n'est compatible que d'UN seul.

  (2) SEMANTIQUE MORTS-INCLUS -- `GetChildrenCount` lit `ParentComponent.children`, liste
      APPEND-ONLY (aucun `RemoveChild` n'existe ; `IdunBattle.Operations.RemoveUnitOperation$$Execute`
      ne touche que les listes du PlayerComponent). Deduit du DECOMPILE, jamais confronte live.
      Ici on DETRUIT des Skitarii en pilotant les unites ADVERSES (`applyAction` ne verifie pas la
      propriete du caster -- runner.md S4 ; frappe rendue letale par `rl_duel build --dmg-target`)
      pour atteindre `alive < cap <= ever`, puis on relit la leaf native : si elle emet encore, la
      semantique append-only est confirmee LIVE et le port (qui ne filtre pas `isDead`) est fidele ;
      si elle cesse d'emettre, le port SUR-tire.

A chaque point, les 3 etages du port (hv / free_adj / cap) sont imprimes face a la leaf native ->
divergence localisable par ETAGE, jamais par scalaire ajuste.

Le coeur de mesure (`run_capbranch_scenario`) est REUTILISE par
`tests/engine/test_doctrina_gate_cap_live.py` (regle DRY : le probe mesure, le test assere).

Usage : `python probe_38c_capbranch.py [seed] [board]`. Console ASCII strict.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import deque
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]          # RELATIF au checkout (#314), jamais l'arbre principal
sys.path.insert(0, str(PYDIR))

STATE = ROOT / "logs" / "runners" / "_case38c_capbranch_state.json"
OUT = ROOT / "logs" / "runners" / "_probe38c_capbranch.json"

TAN_VIS = "admecMarshall"              # Tan Gi'da : actif DoctrinaImperatives(1118) + passif ControlEdict(1200)
SUMMON_LIVE_VIS = "admecNpc1Vanguard"  # visualId LIVE du Skitarii Vanguard (cle de config = admecSmnVanguard)
ENEMY_VIS = "necroWarden"
PROTECTOR = 1247                       # ProtectorImperative (face summon de ControlEdict)
ABILITY_1118 = 1118

#: args `rl_duel build` du scenario. `--hp-target` : ennemis increvables -> Tan attaque en boucle
#: et sature le cap. `--dmg-target` : frappe adverse letale -> phase 2 peut TUER des Skitarii (leurs
#: PV viennent du kit ControlEdict, hors de portee de --hp-target/--hp-player).
BUILD_EXTRA = ["--roster", "1",
               "--p-units", f"{TAN_VIS},admecRuststalker",
               "--a-units", f"{ENEMY_VIS},{ENEMY_VIS}",
               "--hp-target", "400000",
               "--dmg-target", "9000"]


def run_capbranch_scenario(rid: int, rpc, board_turns: int = 26,
                           kill_rounds: int = 14, log=print) -> list[dict]:
    """Joue le scenario et rend une ligne de mesure par point d'observation.

    `rpc(method, body, timeout) -> dict` (deja deballe). Ne construit NI ne dispose le runner :
    l'appelant (probe `main` ou fixture pytest) en est proprietaire.

    Chaque ligne : `{label, summons_alive, summons_ever, fromHereCount, native_emit, native_util,
    port:{hv,free,conq,cap,emit,passiveLevel,capValue}, agree}`.
    """
    from engine.playbook.noncomparable import _base as ncbase
    from engine.playbook.noncomparable.doctrina_imperatives import DoctrinaImperativesPlaybook
    from engine.entities.effects.magnitude import ability_var
    import gameconfig as GC

    pb = DoctrinaImperativesPlaybook()

    # ---- geometrie statique du board (memes sources que `engine.ai.context.build`) ----
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    tiles = bg.get("tiles") or []
    idc = {t.get("id"): (t.get("col"), t.get("row")) for t in tiles}
    neigh_by_pos = {(t.get("col"), t.get("row")):
                    [idc[n] for n in (t.get("neighbours") or []) if n in idc] for t in tiles}
    walkable_by_pos = {(t.get("col"), t.get("row")): bool(t.get("walkable")) for t in tiles}
    elev_by_pos = {(t.get("col"), t.get("row")): t.get("elevation") for t in tiles}

    def bfs(start):
        seen = {start: 0}
        q = deque([start])
        while q:
            x = q.popleft()
            for n in neigh_by_pos.get(x, []):
                if n not in seen:
                    seen[n] = seen[x] + 1
                    q.append(n)
        return seen

    def dec_view():
        return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)

    def find_tan(dec):
        return next((u for u in (dec.get("units") or [])
                     if u.get("visualId") == TAN_VIS and u.get("alive")), None)

    def advance_to_tan(max_iter=25):
        for _ in range(max_iter):
            dec = dec_view()
            tan = find_tan(dec)
            if tan is None:
                return None, None
            if dec.get("currentPlayer") == tan.get("owner"):
                return dec, tan
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"},
                                "captureEvents": False}, 60)
        return None, None

    def normal_ability(u):
        return next((a for a in (u.get("abilities") or [])
                     if a.get("kind") == "normal" and a.get("id") is not None), None)

    def ability_targets(uid, ab_id):
        return rpc("abilityTargets", {"runnerId": rid, "unitId": uid, "abilityId": ab_id}, 60)

    def from_here_count(tan):
        """`GetEligibleTargetsForNormalAttack(caster, curPos).Count` -- proxy natif `fromHereCount`."""
        na = normal_ability(tan)
        if na is None:
            return 0
        at = ability_targets(tan["id"], na["id"])
        for uu in (at.get("units") or []):
            if uu.get("unitId") != tan["id"]:
                continue
            for a in (uu.get("abilities") or []):
                if a.get("abilityId") == na["id"]:
                    return int(a.get("fromHereCount") or 0)
        return 0

    _lvl: dict = {}

    def passive_level():
        """`GetAbilityState(caster, ControlEdict).level` = niveau PASSIF (combatSnapshot)."""
        if "p" not in _lvl:
            snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
            for u in (snap.get("units") or []):
                cfg = u.get("unitConfig") or {}
                if cfg.get("visualId") == TAN_VIS:
                    _lvl["p"] = cfg.get("passiveAbilityLevel")
        return _lvl.get("p")

    def port_stages(dec, tan, obs):
        """Les 3 etages du PORT sur un NCContext cable comme `engine.ai.context.build`
        (memes sources RPC : decisionView.units / observeBattle.units / boardGraph). Aucun
        etat forge -- tout vient du LIVE."""
        uid = tan["id"]
        pos = tan.get("pos") or {}
        origin = (pos.get("col"), pos.get("row"))
        units = dec.get("units") or []
        enemies = [u for u in units if not u.get("ctrl") and u.get("alive") and u.get("pos")]
        plvl = passive_level()
        nc = ncbase.NCContext(
            uid=uid, origin=origin, reach_nc=[],
            epos=[(e["pos"]["col"], e["pos"]["row"]) for e in enemies],
            fpos=[(u["pos"]["col"], u["pos"]["row"]) for u in units
                  if u.get("ctrl") and u.get("alive") and u.get("pos")],
            enemies=enemies, neigh_by_pos=neigh_by_pos, walkable_by_pos=walkable_by_pos,
            plan={}, plans={}, hp_cur_by_id={u.get("id"): u.get("hp") for u in units},
            elev_by_pos=elev_by_pos, wt=None,
            ability_targets=lambda _u, _a: ability_targets(_u, _a),
            is_temporary_by_pos={}, effects_by_pos={}, obs_units=(obs.get("units") or []),
            tile_id_by_pos={}, active_levels={}, units=units,
            ability_config=lambda _u, _l=plvl: {"passive": _l},
            cast_from_tiles=None, scene=None, debug=False)
        return {"hv": ncbase._has_valid_targets(nc, uid),
                "free": pb._free_adjacent_tiles(nc),
                "conq": pb._is_conqueror(nc),
                "cap": pb._reached_summon_cap(nc),
                "emit": pb._should_emit(nc),
                "passiveLevel": plvl,
                "capValue": int(ability_var("ControlEdict", "maxSummons", plvl) or -1)}

    def summon_counts(obs):
        alive, ever = set(), set()
        for u in (obs.get("units") or []):
            if u.get("visualId") != SUMMON_LIVE_VIS:
                continue
            ever.add(u.get("squadId"))
            if not u.get("isDead"):
                alive.add(u.get("squadId"))
        return len(alive), len(ever)

    rows: list[dict] = []

    def measure(label, dec=None, tan=None):
        if dec is None or tan is None:
            dec = dec_view()
            tan = find_tan(dec)
        if tan is None:
            return None
        obs = rpc("observeBattle", {"runnerId": rid}, 60)
        alive_s, ever_s = summon_counts(obs)
        fh = from_here_count(tan)
        st = port_stages(dec, tan, obs)
        ncev = rpc("ncEvaluate", {"runnerId": rid, "unitId": tan["id"],
                                  "abilityType": ABILITY_1118, "sweep": False}, 60)
        p0 = (ncev.get("positions") or [{}])[0]
        native_emit = bool(p0.get("action")) and p0.get("util") is not None
        pos = tan.get("pos") or {}
        row = {"label": label, "uid": tan["id"],
               "origin": [pos.get("col"), pos.get("row")],
               "summons_alive": alive_s, "summons_ever": ever_s,
               "protector": PROTECTOR in {e.get("effectType") for e in (tan.get("effects") or [])},
               "fromHereCount": fh, "native_emit": native_emit, "native_util": p0.get("util"),
               "native_hvt": p0.get("hvt"), "port": st, "agree": native_emit == st["emit"]}
        rows.append(row)
        log(f"[{label}] ever={ever_s} alive={alive_s} prot={row['protector']} fh={fh} "
            f"| port: hv={st['hv']} free={st['free']} conq={st['conq']} cap={st['cap']}"
            f"(capVal={st['capValue']} lvl={st['passiveLevel']}) emit={st['emit']} "
            f"| native_emit={native_emit} util={p0.get('util')} | AGREE={row['agree']}")
        return row

    # ================= PHASE 1 : balayage du SEUIL =================
    ranges = [int(w.get("Range") or 0) for w in ((GC.unit(TAN_VIS) or {}).get("weapons") or [])]
    reach = max([r for r in ranges if r > 0] + [1])
    last_ever = -1
    for _turn in range(board_turns):
        dec, tan = advance_to_tan()
        if tan is None:
            break
        tid = tan["id"]
        pos = tan.get("pos") or {}
        org = (pos.get("col"), pos.get("row"))
        if from_here_count(tan) > 0:
            obs = rpc("observeBattle", {"runnerId": rid}, 60)
            _al, ev = summon_counts(obs)
            if ev != last_ever:                       # une mesure par palier de summons_ever
                measure(f"P1.ever={ev}", dec, tan)
                last_ever = ev
            # attaque NORMALE -> trigger ControlEdict On(0x26) -> +1 Skitarii sous Protector
            na = normal_ability(tan)
            tgt = ab = None
            for p in (dec.get("attackPlans") or []):
                if p.get("unitId") != tid:
                    continue
                for ev2 in (p.get("evals") or []):
                    if ev2.get("targetId") is None:
                        continue
                    if na is not None and ev2.get("abilityId") != na["id"]:
                        continue
                    e = next((u for u in (dec.get("units") or [])
                              if u.get("id") == ev2["targetId"]), None)
                    ep = (e or {}).get("pos") or {}
                    if ep.get("col") is None:
                        continue
                    if bfs((ep["col"], ep["row"])).get(org, 99) <= reach:
                        tgt, ab = ev2["targetId"], ev2["abilityId"]
                        break
                if tgt is not None:
                    break
            if tgt is not None:
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "ability", "casterId": tid, "targetId": tgt,
                    "abilityType": ab}, "captureEvents": False}, 120)
        else:
            # approcher un ennemi -- on DRIVE les positions, on ne subit pas la geometrie
            foes = [u for u in (dec.get("units") or [])
                    if u.get("alive") and u.get("owner") != tan.get("owner")
                    and (u.get("pos") or {}).get("col") is not None]
            if not foes:
                break
            dgoal = bfs((foes[0]["pos"]["col"], foes[0]["pos"]["row"]))
            mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == tid), None)
            pool = [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])
                    if t.get("col") is not None and (t["col"], t["row"]) in dgoal]
            if pool:
                best = min(pool, key=lambda t: dgoal[t])
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": tid,
                    "to": {"col": best[0], "row": best[1]}}}, 60)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        obs = rpc("observeBattle", {"runnerId": rid}, 60)
        _al, ev = summon_counts(obs)
        if rows and ev > rows[-1]["port"]["capValue"]:
            break
    dec, tan = advance_to_tan()
    if tan is not None:
        measure("P1.final", dec, tan)

    # ================= PHASE 2 : semantique MORTS-INCLUS =================
    capv = rows[-1]["port"]["capValue"] if rows else 5
    tan_owner = (find_tan(dec_view()) or {}).get("owner")
    killed = 0

    def legal_summon_target(fid, ab_id, sk_ids):
        """Cible Skitarii LEGALE pour `fid` DEPUIS SA TUILE (`abilityTargets.fromHere` =
        `AttackQuery.GetValidTargets` natif : portee + LoS + filtre ennemi)."""
        at = ability_targets(fid, ab_id)
        for uu in (at.get("units") or []):
            if uu.get("unitId") != fid:
                continue
            for a in (uu.get("abilities") or []):
                if a.get("abilityId") != ab_id:
                    continue
                for t in (a.get("fromHere") or []):
                    tid = t.get("targetId") if isinstance(t, dict) else t
                    if tid in sk_ids:
                        return tid
        return None

    def foe_turn_kill_pass():
        nonlocal killed
        foes = [u for u in (dec_view().get("units") or [])
                if u.get("alive") and u.get("owner") != tan_owner
                and (u.get("pos") or {}).get("col") is not None]
        for f in foes:
            obs = rpc("observeBattle", {"runnerId": rid}, 60)
            sk = [u for u in (obs.get("units") or [])
                  if u.get("visualId") == SUMMON_LIVE_VIS and not u.get("isDead")
                  and u.get("col") is not None]
            if not sk:
                return
            sk_ids = {u.get("squadId") for u in sk}
            fid = f["id"]
            fna = normal_ability(f)
            if fna is None:
                continue
            tid = legal_summon_target(fid, fna["id"], sk_ids)
            if tid is None:
                fnow = next((u for u in (dec_view().get("units") or [])
                             if u.get("id") == fid), None)
                if fnow is None:
                    continue
                fpos = ((fnow.get("pos") or {}).get("col"), (fnow.get("pos") or {}).get("row"))
                mt = rpc("aiMovableTiles", {"runnerId": rid}, 60)
                cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == fid), None)
                reachable = [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])
                             if t.get("col") is not None]
                best, bestd = None, 99
                for v in sk:
                    dg = bfs((v.get("col"), v.get("row")))
                    for t in reachable:
                        if dg.get(t, 99) < bestd:
                            best, bestd = t, dg[t]
                if best is not None and best != fpos:
                    rpc("applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": fid,
                        "to": {"col": best[0], "row": best[1]}}}, 60)
                tid = legal_summon_target(fid, fna["id"], sk_ids)
            if tid is None:
                continue
            if rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "ability", "casterId": fid, "targetId": tid,
                    "abilityType": fna["id"]}, "captureEvents": False}, 120).get("ok"):
                killed += 1

    for _round in range(kill_rounds):
        obs = rpc("observeBattle", {"runnerId": rid}, 60)
        alive_s, ever_s = summon_counts(obs)
        if alive_s < capv <= ever_s:
            break                                     # etat cible : alive < cap <= ever
        for _ in range(4):                            # passer au camp adverse
            if (dec_view().get("currentPlayer") or tan_owner) != tan_owner:
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        foe_turn_kill_pass()
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    log(f"[38c] phase2 : {killed} attaque(s) adverse(s) portee(s) sur des Skitarii")
    dec, tan = advance_to_tan()
    if tan is not None:
        measure("P2.dead", dec, tan)
    return rows


def main(argv: list[str]) -> int:
    from rl_collect_batch import _resolve_session, _rpc
    seed = argv[1] if len(argv) > 1 else "777"
    board = argv[2] if len(argv) > 2 else "MC1_67"
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed,
         "--state-file", str(STATE), "--board", board, *BUILD_EXTRA],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[38c] build KO:", (proc.stderr or proc.stdout or "")[-400:])
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    sid = _resolve_session()
    print(f"[38c] seed={seed} board={board} runner={rid}")

    def _r(m, b, t=60):
        return _rpc(sid, m, [b], timeout=t).get("result") or {}

    try:
        rows = run_capbranch_scenario(rid, _r)
    finally:
        _r("disposeRunner", {"runnerId": rid}, 30)
        try:
            STATE.unlink()
        except OSError:
            pass
    OUT.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print(f"[38c] dump -> {OUT}")
    dis = [r for r in rows if not r["agree"]]
    print(f"[38c] points={len(rows)} desaccords_port_vs_natif={len(dis)}")
    for r in dis:
        print("  DESACCORD", r["label"], "native", r["native_emit"], "port", r["port"]["emit"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
