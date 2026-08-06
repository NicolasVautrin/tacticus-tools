"""Probe de MESURE des deux AoE Psychic (PlagueWind 1035 / Doombolt 1102) : geometrie CRAFTEE,
cast LIVE, replay OFFLINE bit-a-bit sur le MEME etat + le MEME `state.rng`.

Sert a produire les CAS DISCRIMINANTS des deux ports :

  * `pw-solo`  : cible ISOLEE            -> PlagueWind = bande 1 seule (minDmg/maxDmg)
  * `pw-chain` : cible + 1 adjacent-cible + 1 adjacent-du-secondaire (a distance 2 de la cible)
                 -> les TROIS bandes, avec TROIS plages de degat distinctes
  * `db-1/2/3` : 1 / 2 / 3 ennemis a portee -> Doombolt repartit N=3 coups en [3] / [2,1] / [1,1,1]

Chaque cas imprime, par cible : coups LIVE (Amount par event) vs coups OFFLINE (per_hit), le total,
et un verdict BIT-EXACT. ASCII only (cp1252). Dispose SON runner en sortie.

Usage (depuis scripts/python) :
    python probe_psychic_aoe.py --case pw-chain [--seed 31337] [--board MC1_67]
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
from engine.entities.pathfinding.board import Board
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.snapshot import load_state
from engine.runner.abilities.handler import ABILITY_CLASSES

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

CASES = {
    # nom -> (caster visualId, abilityType, nb d'ennemis, roster adverse)
    "pw-solo":  ("deathTyphus", 1035, 1, "necroOverlord"),
    "pw-chain": ("deathTyphus", 1035, 3, "necroOverlord,necroWarden,necroWarden"),
    "db-1":     ("thousAhriman", 1102, 1, "necroOverlord"),
    "db-2":     ("thousAhriman", 1102, 2, "necroOverlord,necroWarden"),
    "db-3":     ("thousAhriman", 1102, 3, "necroOverlord,necroWarden,necroWarden"),
    # 4 cibles pour N=3 coups -> repartition [1,1,1,0] : l'ORDRE du tri decide QUI ne recoit RIEN.
    # PV NATURELS (pas d'egalisation) pour que `SortUnitsByDamageUtility` ait de quoi discriminer.
    "db-4":     ("thousAhriman", 1102, 4, "necroOverlord,necroWarden,eldarRanger,orksNob"),
}
# Cas ou l'on NE force PAS les PV (le tri par utilite doit voir des PV heterogenes).
NO_HP_EQUALIZE = {"db-4"}


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _tags(e):
    tg = e.get("tags")
    return (json.loads(tg) if isinstance(tg, str) else tg) or {}


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


class Live:
    def __init__(self, sid, rid):
        self.sid, self.rid = sid, rid

    def rpc(self, method, body=None, timeout=90):
        return _unwrap(R._rpc(self.sid, method, [body] if body is not None else [], timeout=timeout))

    def dec(self):
        return self.rpc("decisionView", {"runnerId": self.rid, "allAbilities": True}, 150)

    def units(self):
        return [u for u in (self.dec().get("units") or []) if u.get("alive")]

    def unit(self, uid):
        return next((u for u in self.units() if u.get("id") == uid), None)

    def move(self, uid, dest):
        return self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": dest[0], "row": dest[1]}}}, 90)

    def endturn(self):
        return self.rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 90)


def free_tiles(board, occupied):
    """Tuiles marchables et INOCCUPEES, en positions (col,row)."""
    out = []
    for tid, t in board.by_id.items():
        p = (t["col"], t["row"])
        if board.walkable(tid) and p not in occupied:
            out.append(p)
    return out


def drive_to(live, board, uid, dest, rounds=10):
    """Amene `uid` sur `dest` par sauts LEGAUX successifs (`applyAction move`), en cyclant les tours
    quand l'activation est consommee. Rend True si arrive."""
    for _ in range(rounds):
        u = live.unit(uid)
        if u is None:
            return False
        cur = _pos(u)
        if cur == dest:
            return True
        occ = {_pos(x) for x in live.units() if x.get("id") != uid}
        cands = [p for p in free_tiles(board, occ)]
        cands.sort(key=lambda p: (hexgeo.distance(p, dest), hexgeo.distance(p, cur)))
        moved = False
        for p in cands[:40]:
            if p == cur:
                continue
            live.move(uid, p)
            nu = live.unit(uid)
            if nu is not None and _pos(nu) == p:
                moved = True
                break
        if not moved:
            live.endturn()
            continue
        if _pos(live.unit(uid)) == dest:
            return True
        live.endturn()
    return _pos(live.unit(uid)) == dest if live.unit(uid) else False


def pick_geometry(board, case, occupied_seed):
    """Choisit un HUB a 6 voisins marchables et rend les positions VOULUES :
       {"target": T, "extra": [...], "caster": C}.
    `pw-chain` exige un U adjacent a S mais a distance 2 de T (bande TERTIAIRE non vide)."""
    hubs = []
    for tid, t in board.by_id.items():
        if not board.walkable(tid):
            continue
        p = (t["col"], t["row"])
        nb = [n for n in board.neighbours(tid) if board.walkable(n)]
        if len(nb) == 6:
            hubs.append((p, [board.coord(n) for n in nb]))
    if not hubs:
        return None
    hubs.sort(key=lambda h: (abs(h[0][0] - 3), abs(h[0][1] - 4)))     # le plus central d'abord
    for T, ring in hubs:
        S = ring[0]
        # U : voisin de S a distance EXACTEMENT 2 de T (donc hors bande secondaire)
        stid = board.id_at(S[0], S[1])
        U = next((board.coord(n) for n in board.neighbours(stid)
                  if board.walkable(n) and hexgeo.distance(board.coord(n), T) == 2), None)
        # caster : a distance <= 2 de T, distinct de S/U
        C = next((p for p in (board.coord(n) for tid2 in [board.id_at(T[0], T[1])]
                              for n in board.neighbours(tid2))
                  if p not in (S, U) and board.walkable(board.id_at(p[0], p[1]))), None)
        if case == "pw-chain" and U is None:
            continue
        if C is None:
            continue
        if case == "pw-chain":
            return {"target": T, "extra": [S, U], "caster": C}
        if case == "pw-solo":
            return {"target": T, "extra": [], "caster": C}
        # Doombolt : les ennemis doivent etre a <= 2 hexes du CASTER (pas de la cible)
        if case.startswith("db"):
            n = CASES[case][2]
            spots = [T] + [p for p in ring if p != C][:n - 1]
            return {"target": T, "extra": spots[1:], "caster": C}
    return None


def control_variant(ability, dec1, ob1, snap1, bg, s_cast, cid, tid):
    """CONTRE-EPREUVE de DISCRIMINANCE : rejoue un port DELIBEREMENT FAUX sur le MEME etat et le MEME
    `state.rng`, pour prouver que le cas mesure separe bien les hypotheses (un cas ou toutes les
    variantes coincident ne valide rien).

      * PlagueWind : les TROIS bandes partagent la plage `minDmg`/`maxDmg` (au lieu de _2/_3) —
        c'est l'erreur naturelle « une seule plage pour tout l'AoE ».
      * Doombolt   : `native_factory="ability"` (1 tirage/coup) au lieu de la famille ATTACK
        (2 tirages/coup a cc=0) — le discriminant de famille (tip #2 / rngcrit-1202).
    """
    from engine.dsl.effects import ExecutionContext
    from engine.entities.behaviours import AtomicGroup, Group, op_add, op_and
    from engine.entities.selectors.units import UnitSet
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.runner.abilities import deathguard as DG
    from engine.runner.abilities import thousandsons as TS
    from functools import reduce

    st = load_state(dec1, ob1, snap1, board=Board(bg["tiles"], adjacency="native_sym"))
    st.rng = _seed_rng(s_cast)
    ectx = ExecutionContext(state=st, rng=st.rng)
    entities = entities_from_state(st, cid, tid)
    if ability == 1035:
        t1, t2, t3 = DG.plague_wind_target_selectors()
        mk = lambda sel: AttackWithAttackDamage(sel, DG.PLAGUE_WIND_ID, "Psychic", is_melee=False,   # noqa: E731
                                                multi=True, native_factory="ability")
        AtomicGroup(op_and(op_and(Group(mk(t1), 0x4b, t1), Group(mk(t2), 0x4c, t1)),
                           Group(mk(t3), 0x4d, t1))).execute(entities, ectx)
    else:
        cand = [u for u in (TS.doombolt_targets_selector().evaluate(entities) or [])
                if isinstance(u, dict) and u.get("id") is not None]
        by_id = {int(u["id"]): u for u in cand}
        if tid is not None and entities.target is not None:
            by_id.setdefault(int(tid), entities.target)
        lvl, mult = TS._ability_state(st, cid)
        from engine.entities.effects.magnitude import ability_var
        dmin = int(ability_var(TS.DOOMBOLT_ID, "minDmg", lvl, multiplier_pct=mult) or 0)
        ordered = [t for t in TS.doombolt_ordered_targets(st, cid, tid,
                                                          [int(u["id"]) for u in cand], dmin)
                   if t in by_id]
        n = int(TS.doombolt_nr_of_hits_formula().evaluate(entities))
        dist = TS.doombolt_hits_distribution(n, len(ordered))
        leaves = [AttackWithAttackDamage(UnitSet([by_id[t]]), TS.DOOMBOLT_ID, "Psychic",
                                         is_melee=False, hits=int(k), native_factory="ability")
                  for t, k in zip(ordered, dist)]
        if leaves:
            AtomicGroup(reduce(op_add, leaves)).execute(entities, ectx)
    out = {}
    for n_, p in ectx.emitted:
        if n_ == "AttackWithAttackDamage":
            out.setdefault(p.get("target"), []).extend((p.get("attack") or {}).get("per_hit") or [])
    return out


def run(case, seed="31337", board_id="MC1_67", verbose=True):
    """Monte le cas, mesure LIVE + OFFLINE + contre-epreuve, et rend le dict de resultats :
    `{case, runner, caster, target, live, off, control, diag, exact, discriminant}` (ou
    `{error: <raison>}` si le harnais n'a pas pu monter le cas). Consomme par `main()` (impression)
    et par les tests de garde `tests/engine/runner/test_{plague_wind,doombolt}_live.py`."""
    caster_vis, ability, n_enemies, a_units = CASES[case]
    sid = R._resolve_session()
    state_file = ROOT / "logs" / "runners" / f"psychic-{case}-{uuid.uuid4().hex[:6]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    hp_args = [] if case in NO_HP_EQUALIZE else ["--hp-target", "900000", "--hp-player", "900000"]
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board_id,
            "--roster", "1", "--p-units", caster_vis, "--a-units", a_units,
            *hp_args, "--state-file", str(state_file)]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    def _say(*a):
        if verbose:
            print(*a)

    if not state_file.exists():
        _say("[probe] build KO:", (p.stderr or p.stdout or "")[-400:])
        return {"error": "build runner KO: " + (p.stderr or p.stdout or "")[-300:]}
    rid = json.loads(state_file.read_text())["runnerId"]
    live = Live(sid, rid)
    try:
        bg = live.rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        units = live.units()
        caster = next((u for u in units if u.get("visualId") == caster_vis), None)
        enemies = [u for u in units if u.get("id") != caster["id"]]
        geo = pick_geometry(board, case, set())
        if geo is None:
            _say("[probe] aucune geometrie candidate (hub 6-voisins)")
            return {"error": "aucune geometrie candidate (hub 6-voisins) sur " + board_id}
        _say(f"[probe] case={case} runner={rid} geo={geo}")
        # --- drive : ennemis d'abord (ils ont le plus de move), caster ensuite -----------------
        wanted = [(enemies[0]["id"], geo["target"])]
        for i, p in enumerate(geo["extra"]):
            if i + 1 < len(enemies):
                wanted.append((enemies[i + 1]["id"], p))
        # les ennemis en trop : loin de la zone
        far = [p for p in free_tiles(board, set()) if hexgeo.distance(p, geo["target"]) >= 5]
        for j in range(len(geo["extra"]) + 1, len(enemies)):
            if far:
                wanted.append((enemies[j]["id"], far[j % len(far)]))
        wanted.append((caster["id"], geo["caster"]))
        for uid, dest in wanted:
            ok = drive_to(live, board, uid, dest)
            _say(f"[probe]   drive u{uid} -> {dest} : {'OK' if ok else 'PARTIEL ' + str(_pos(live.unit(uid)))}")
        # --- le caster doit etre le joueur courant et activable -------------------------------
        for _ in range(6):
            d = live.dec()
            cu = next((u for u in (d.get("units") or []) if u.get("id") == caster["id"]), None)
            if cu is not None and cu.get("owner") == d.get("currentPlayer"):
                break
            live.endturn()
        # --- capture de l'etat AU CAST --------------------------------------------------------
        dec1 = live.dec()
        ob1 = live.rpc("observeBattle", {"runnerId": rid}, 60)
        snap1 = live.rpc("combatSnapshot", {"runnerId": rid}, 90)
        s_cast = live.rpc("dumpRng", {"runnerId": rid}, 30)
        if not (isinstance(s_cast, dict) and s_cast.get("ok")):
            _say("[probe] dumpRng KO:", str(s_cast)[:200])
            return {"error": "dumpRng KO: " + str(s_cast)[:200]}
        cid = caster["id"]
        tid = next((u["id"] for u in (dec1.get("units") or [])
                    if _pos(u) == geo["target"] and u.get("alive")), None)
        if tid is None:
            _say("[probe] cible introuvable sur", geo["target"])
            return {"error": "cible introuvable sur " + str(geo["target"])}
        positions = {u["id"]: _pos(u) for u in (dec1.get("units") or []) if u.get("alive")}
        _say("[probe] positions au cast:", positions)
        # --- OFFLINE (avant le cast live : meme etat, meme rng) --------------------------------
        st = load_state(dec1, ob1, snap1, board=Board(bg["tiles"], adjacency="native_sym"))
        st.rng = _seed_rng(s_cast)
        diag = ABILITY_CLASSES[ability]().execute_behaviour(st, cid, tid)
        off = {}
        for a in (diag.get("attacks") or []):
            atk = a.get("attack") or {}
            off.setdefault(a["target"], []).extend(atk.get("per_hit") or [])
        # --- LIVE -----------------------------------------------------------------------------
        cast = live.rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ability},
            "captureEvents": True}, 150)
        if not (isinstance(cast, dict) and cast.get("ok")):
            _say("[probe] cast KO:", str(cast)[:300])
            return {"error": "cast KO: " + str(cast)[:300]}
        a0 = (cast.get("actions") or [{}])[0]
        livehits = {}
        for e in (a0.get("events") or []):
            tg = _tags(e)
            if "Amount" in tg and tg.get("Active_Ability_Type") == ability:
                livehits.setdefault(tg.get("Target_Id"), []).append(int(tg.get("Amount") or 0))
        livetot = {}
        for ch in (a0.get("changes") or []):
            if ch.get("hpDelta") is not None and int(ch["hpDelta"]) < 0:
                livetot[ch.get("squadId")] = -int(ch["hpDelta"])
        # --- rapport --------------------------------------------------------------------------
        _say("\n=== %s  (caster u%s, cible u%s, ability %d) ===" % (case, cid, tid, ability))
        if ability == 1035:
            _say("bandes offline: main=%s secondary=%s tertiary=%s"
                  % ([a["target"] for a in diag["main"]],
                     [a["target"] for a in diag["secondary"]],
                     [a["target"] for a in diag["tertiary"]]))
        else:
            _say("ordre offline=%s  hits=%s  total_hits=%s"
                  % (diag["targets"], diag["hits"], diag["total_hits"]))
        allt = sorted(set(list(off.keys()) + list(livehits.keys())))
        exact = True
        for t in allt:
            lh, oh = livehits.get(t, []), off.get(t, [])
            ok = lh == oh
            exact = exact and ok
            _say("  u%-4s live=%-28s off=%-28s livetot=%-8s %s"
                  % (t, lh, oh, livetot.get(t), "BIT-EXACT" if ok else "DIVERGE"))
        ctl = control_variant(ability, dec1, ob1, snap1, bg, s_cast, cid, tid)
        ctl_div = any(ctl.get(t, []) != livehits.get(t, []) for t in allt)
        _say("  [controle port-FAUX] %s -> %s"
              % ({("u%s" % t): ctl.get(t, []) for t in allt},
                 "DIVERGE du live (cas DISCRIMINANT)" if ctl_div
                 else "IDENTIQUE au live (cas NON discriminant !)"))
        _say("VERDICT:", "BIT-EXACT" if exact else "DIVERGENCE",
             "| discriminance:", "OK" if ctl_div else "INSUFFISANTE")
        return {"case": case, "runner": rid, "caster": cid, "target": tid, "ability": ability,
                "positions": positions, "live": livehits, "off": off, "livetot": livetot,
                "control": ctl, "diag": diag, "exact": exact, "discriminant": ctl_div}
    finally:
        try:
            live.rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            state_file.unlink()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True, choices=sorted(CASES))
    ap.add_argument("--seed", default="31337")
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()
    r = run(a.case, a.seed, a.board)
    if "error" in r:
        print("[probe] KO:", r["error"])
        sys.exit(2)
    sys.exit(0 if (r["exact"] and r["discriminant"]) else 1)


if __name__ == "__main__":
    main()
