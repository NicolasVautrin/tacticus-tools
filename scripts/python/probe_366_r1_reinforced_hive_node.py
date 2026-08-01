"""#366-r1 -- MESURE LIVE de `1108 ReinforcedHiveNode_ExtraArmor` ET de son jumeau
`1109 ReinforcedHiveNode_ExtraBlock` sur le SUMMON `tyranSmnWarrior`, invoque par
`tyranWingedPrime` (`AlphaWarrior`, 1112).

Ce que le probe etablit, round par round :
  * quels effets `1108`/`1109` le summon porte, et leur flag `active`
    (canal `decisionView { includeInactive: true }` -- le canal par defaut DROPPE les inactifs) ;
  * son `fixedArmor` COURANT et son `statDelta` (`combatSnapshot`), donc la contribution reelle
    de `1108`, ET la MEME grandeur cote PORT (avant / apres `refresh_stat_modifier_effects`) ;
  * son `blockChance` COURANT -- le canal OVERRIDE de `1109` (part 7 `SetOverride`, `isModifiable`
    = 0) -- et la MEME grandeur cote PORT, avant / apres le meme driver ;
  * son `turnsStarted` (`GetStat(., 0xc)`), l'entree de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ReinforcedHiveNodeAbility$$GetEffectActiveCondition`
    = `AmountIsOdd(Sum(RoundsStarted(Owner), Direct(1)))`.

⚠ Le summon se PROJETTE sous le visualId `tyranNpc4Warrior` (pas `tyranSmnWarrior`) : le porteur
est identifie par ses EFFETS, jamais par un visualId suppose.

Usage (depuis `scripts/python`, session Frida warmee) :
    # scenario complet (build + cast + N rounds), c'est la voie de GENERALISATION :
    python probe_366_r1_reinforced_hive_node.py --seed 777 --board MC1_67 --rounds 4
    python probe_366_r1_reinforced_hive_node.py --seed 31337 --board C3_01 --rounds 4 \
        --unit-stat "tyranWingedPrime:AbilityVariablesMultiplierPercentage=100"
    # ou lecture d'un runner DEJA monte :
    python probe_366_r1_reinforced_hive_node.py --runner <id>

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HOST = "http://127.0.0.1:8765"
PYDIR = Path(__file__).resolve().parent
SUMMONER = "tyranWingedPrime"
ALPHA_WARRIOR = 1112


# ------------------------------------------------------------------ transport

def session_id() -> int:
    with urllib.request.urlopen(f"{HOST}/api/admin/status", timeout=20) as r:
        return int((json.loads(r.read().decode("utf-8")).get("session") or {})["id"])


def rpc(sid: int, method: str, args, timeout: int = 90):
    body = json.dumps({"method": method, "args": args}).encode("utf-8")
    req = urllib.request.Request(f"{HOST}/api/scripts/{sid}/rpc", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _res(sid, method, body, timeout=90):
    return rpc(sid, method, [body], timeout).get("result") or {}


# ------------------------------------------------------------------ montage

def build(seed: str, board: str, unit_stat: "list[str]", state_file: Path) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", str(state_file),
            "--p-units", f"{SUMMONER},tyranTyrantGuard",
            "--a-units", "orksNob,orksRuntherd", "--hp-target", "300000"]
    for us in (unit_stat or []):
        argv += ["--unit-stat", us]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise SystemExit("[build] KO rc=%s\n%s\n%s"
                         % (p.returncode, (p.stdout or "")[-2000:], (p.stderr or "")[-2000:]))
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def dview(sid, rid):
    from engine.runner.snapshot import decision_view_seed_body
    return _res(sid, "decisionView", decision_view_seed_body(rid, allAbilities=True), 150)


def carrier_row(dv):
    for u in (dv.get("units") or []):
        if any(str(e.get("name", "")).startswith("ReinforcedHiveNode")
               for e in (u.get("effects") or [])):
            return u
    return None


def spawn_summon(sid, rid) -> int:
    dv = dview(sid, rid)
    caster = next((u for u in (dv.get("units") or [])
                   if u.get("visualId") == SUMMONER and u.get("alive")), None)
    if caster is None:
        raise SystemExit("[probe] %s absent du runner -- montage casse" % SUMMONER)
    at = _res(sid, "abilityTargets", {"runnerId": rid, "allAbilities": True}, 120)
    tiles = []
    for row in (at.get("units") or []):
        if int(row.get("unitId", -1)) != int(caster["id"]):
            continue
        for ab in (row.get("abilities") or []):
            if int(ab.get("abilityId", -1)) != ALPHA_WARRIOR:
                continue
            for t in (ab.get("fromHere") or ab.get("targets") or []):
                p = t.get("tile") or {}
                if p.get("col") is not None:
                    tiles.append((int(p["col"]), int(p["row"])))
    if not tiles:
        raise SystemExit("[probe] aucune tuile de spawn legale pour AlphaWarrior")
    col, row = tiles[0]
    _res(sid, "applyAction", {"runnerId": rid,
                              "action": {"kind": "ability", "casterId": int(caster["id"]),
                                         "to": {"col": col, "row": row},
                                         "abilityType": ALPHA_WARRIOR}}, 90)
    c = carrier_row(dview(sid, rid))
    if c is None:
        raise SystemExit("[probe] le cast n'a pose AUCUN effet ReinforcedHiveNode")
    return int(c["id"])


def end_round(sid, rid):
    dv = dview(sid, rid)
    for uid in (dv.get("toActivate") or []):
        _res(sid, "applyAction",
             {"runnerId": rid, "action": {"kind": "finish", "unitId": int(uid)}}, 60)
    _res(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)


# ------------------------------------------------------------------ mesure

def observe(sid: int, rid: int, carrier_id=None) -> "list[dict]":
    """Une ligne par porteur d'effet `ReinforcedHiveNode_*` (live ET port)."""
    from engine.entities.stats import StatType
    from engine.runner.components import StatsComponent, unit_state_for_effects
    from engine.runner.operations.refresh_effects import refresh_stat_modifier_effects
    from engine.runner.snapshot import load_state
    dv = dview(sid, rid)
    ob = _res(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _res(sid, "combatSnapshot", {"runnerId": rid}, 90)
    snapu = {int(x["entityId"]): x for x in (snap.get("units") or [])
             if x.get("entityId") is not None}
    st = load_state(dv, ob, snap)
    rows = []
    for u in (dv.get("units") or []):
        rhn = [e for e in (u.get("effects") or [])
               if str(e.get("name", "")).startswith("ReinforcedHiveNode")]
        if not rhn:
            continue
        uid = int(u["id"])
        if carrier_id is not None and uid != int(carrier_id):
            continue
        su = snapu.get(uid) or {}
        stats, delta = su.get("stats") or {}, su.get("statDelta") or {}
        us = st.get_entity(uid).get_component(StatsComponent).ctx.stats
        ustate = unit_state_for_effects(st, uid)
        before = int(us.get_stat(int(StatType.FIXED_ARMOR)))
        block_before = int(us.get_stat(int(StatType.BLOCK_CHANCE)))
        bcomp = us.components.get(int(StatType.BLOCK_CHANCE))
        block_src = dict(bcomp.modification.per_source) if bcomp is not None else {}
        per_src = dict(us.components[int(StatType.FIXED_ARMOR)].modification.per_source)
        refresh_stat_modifier_effects(st, uid)
        rows.append({
            "port_block_before": block_before,
            "port_block_after": int(us.get_stat(int(StatType.BLOCK_CHANCE))),
            "block_per_source": {str(k): v for k, v in block_src.items()},
            "block_override": (None if bcomp is None else bcomp.override.override),
            "uid": uid, "vid": u.get("visualId"), "alive": bool(u.get("alive")),
            "turnsStarted": int(ustate["turns_started"]),
            "live_active": {str(e.get("name")): bool(e.get("active", True)) for e in rhn},
            "live_armor": stats.get("fixedArmor"),
            "live_initial": (int(stats.get("fixedArmor") or 0)
                             - int(delta.get("fixedArmor") or 0)),
            "live_blockChance": stats.get("blockChance"),
            "live_block_initial": (int(stats.get("blockChance") or 0)
                                   - int(delta.get("blockChance") or 0)),
            # i2 : << and - IF IT HAS BLOCK - 100% Block chance >>. `blockDamage` (GetStat(8)) est
            # l'AUTRE moitie de l'entree par defaut de `GetMultiValueStat(7)` : a 0, la source de
            # block n'existe pas et l'override de `blockChance` reste sans effet observable en
            # combat. On le MESURE au lieu de le supposer.
            "live_blockDamage": stats.get("blockDamage"),
            "port_armor_before": before,
            "port_armor_after": int(us.get_stat(int(StatType.FIXED_ARMOR))),
            "per_source": {str(k): v for k, v in per_src.items()},
            "port_active": {e.name: bool(e.is_active(ustate))
                            for e in st.effects.by_unit.get(uid, [])
                            if e.name.startswith("ReinforcedHiveNode")},
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None,
                    help="lire un runner DEJA monte (pas de build/cast)")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--unit-stat", action="append", default=[])
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner construit")
    a = ap.parse_args()
    sid = session_id()
    if a.runner is not None:
        print(json.dumps(observe(sid, a.runner), indent=1))
        return 0
    with tempfile.TemporaryDirectory() as td:
        sf = Path(td) / "probe366r1.json"
        rid = build(a.seed, a.board, a.unit_stat, sf)
        print("[probe] runner=%d seed=%s board=%s unit-stat=%s"
              % (rid, a.seed, a.board, a.unit_stat))
        try:
            carrier = spawn_summon(sid, rid)
            out = []
            for _ in range(a.rounds):
                rows = observe(sid, rid, carrier)
                if not rows or not rows[0]["alive"]:
                    break
                out.append(rows[0])
                end_round(sid, rid)
            for o in out:
                print("  ts=%d live[1108/1109]=%s/%s armor live=%-6s port=%-6s (refresh %-6s) "
                      "initial=%-6s | block live=%-4s port=%-4s (refresh %-4s) init=%-4s ovr=%s"
                      % (o["turnsStarted"],
                         o["live_active"].get("ReinforcedHiveNode_ExtraArmor"),
                         o["live_active"].get("ReinforcedHiveNode_ExtraBlock"),
                         o["live_armor"], o["port_armor_before"], o["port_armor_after"],
                         o["live_initial"],
                         o["live_blockChance"], o["port_block_before"], o["port_block_after"],
                         o["live_block_initial"], o["block_override"]))
                print("      blockDamage=%s per_source[armor]=%s per_source[block]=%s port_active=%s"
                      % (o["live_blockDamage"], o["per_source"], o["block_per_source"],
                         o["port_active"]))
            parities = sorted({o["turnsStarted"] % 2 for o in out})
            print("[probe] %d observations, parites vues=%s" % (len(out), parities))
        finally:
            if not a.keep:
                _res(sid, "disposeRunner", {"runnerId": rid}, 30)
                print("[probe] runner %d dispose" % rid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
