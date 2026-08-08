"""#550 -- `1121 ItItches` (`tyranParasite`, Parasite of Mortrex) : NATIF vs PORT, etage par etage.

CE QUE CE PROBE MESURE, ET POURQUOI CES ETAGES-LA. Le corps natif
`IdunBattleLogic.Entities.Abilities.Active.Loki.ItItchesAbility$$ExecuteBehaviour` est un COMPOSITE
de cinq mecaniques (cf. `engine/runner/abilities/tyranids.py::it_itches_tree`). Un critere unique
(« le cast passe ») serait VERT sur un port qui n'en porterait qu'une : chaque etage est donc mesure
SEPAREMENT, avec sa propre grandeur observable.

  E1 CIBLAGE   : `GetTargetUnits` = la cible + les ennemis adjacents A LA FOIS a la cible et au
                 caster. On CRAFTE une configuration a 3 cibles (cf. `--place`) et on verifie que le
                 natif en affecte exactement 3.
  E2 PIN       : `AddEffect(0x429 = Pinned)` sur chacune des cibles.
  E3 POUSSEE   : `DisplaceUnitInAdjacentDirection` -- chaque cible recule d'UN hex dans la MEME
                 direction (celle `casterTile -> tuile ciblee`), pas dans sa direction propre. C'est
                 le seul etage ou le port aurait pu « marcher » en etant faux : un
                 `FindTileToPush` (direction 0) donnerait des destinations DIFFERENTES pour les deux
                 cibles laterales. Le probe compare les positions FINALES, une par une.
  E4 SUMMON    : un `tyranSmnRipperSwarm` par hex LIBERE.
  E5 RESET     : le caster recupere son deplacement (`ResetMovement(Owner)`) -- il doit rester
                 activable APRES le cast.
  E6 ON-APPEAR : le `PerformAIAbility` de l'on-appearance. C'est l'HYPOTHESE declaree du port (la
                 lambda `getAbilityType` est DEDUPLIQUEE dans le binaire, donc illisible
                 statiquement) : si elle rendait `1023 Burrowers` au lieu de
                 `UnitExtensions$$GetNormalAttackType`, le Ripper Swarm DISPARAITRAIT du plateau au
                 lieu d'attaquer. Le probe regarde donc si les summons sont TOUJOURS SUR LE PLATEAU
                 apres le cast, et s'ils ont fait des degats.

Le port est execute sur l'etat AVANT (charge par `load_state`), le natif sur le meme etat via
`applyAction` -- les deux verdicts sont imprimes cote a cote.

Usage (depuis scripts/python) :
    python probe_550_it_itches.py --state-file <ABSOLU> [--board MC1_67] [--seed 777] [--keep]

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
CASTER = "tyranParasite"
ENEMIES = "orksNob,orksRuntherd,orksBigMek"
IT_ITCHES = 1121
SUMMON_VID = "tyranSmnRipperSwarm"

# Configuration CRAFTEE (cf. l'en-tete) : P adjacent a T, et les deux autres ennemis sur les DEUX
# seules tuiles adjacentes A LA FOIS a P et a T -- c'est le maximum que `GetTargetUnits` peut rendre.
P_POS = (3, 5)
T_POS = (3, 6)
E1_POS = (2, 5)
E2_POS = (4, 5)


def sid() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60):
    r = requests.post(f"{HOST}/api/scripts/{s}/rpc",
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def build(state_file: Path, board: str, seed: str) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    if state_file.exists():
        state_file.unlink()
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
           "--p-units", CASTER, "--a-units", ENEMIES,
           "--place", "%s:%d,%d" % (CASTER, P_POS[0], P_POS[1]),
           "--a-place", "orksNob:%d,%d" % T_POS,
           "--a-place", "orksRuntherd:%d,%d" % E1_POS,
           "--a-place", "orksBigMek:%d,%d" % E2_POS,
           "--state-file", str(state_file)]
    proc = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parent),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise SystemExit("[550] build KO: %s" % ((proc.stderr or proc.stdout or "")[-500:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def live_units(s: int, rid: int) -> list:
    ob = rpc(s, "observeBattle", {"runnerId": rid}, 40) or {}
    return list(ob.get("units") or [])


def load_port_state(s: int, rid: int):
    from engine.entities.pathfinding.board import Board
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(s, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc(s, "dumpRng", {"runnerId": rid}, 30)
    st = load_state(dec, ob, snap, board=board)
    if isinstance(s0, dict) and s0.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        st.rng = rng
    return st, board


def unit_by_vid(units: list, vid: str):
    return next((u for u in units if u.get("visualId") == vid and not u.get("isDead")), None)


def positions(units: list) -> dict:
    return {u.get("squadId"): (u.get("visualId"), u.get("col"), u.get("row"),
                               bool(u.get("isDead"))) for u in units}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    s = sid()
    rid = build(Path(a.state_file), a.board, a.seed)
    print("[550] runner %d monte (board %s, seed %s)" % (rid, a.board, a.seed))
    rc = 0
    try:
        before = live_units(s, rid)
        caster = unit_by_vid(before, CASTER)
        if caster is None:
            print("[550] ECHEC : caster absent")
            return 1
        cid = caster["squadId"]
        pos_before = positions(before)
        print("[550] AVANT :")
        for uid, (vid, col, row, dead) in sorted(pos_before.items()):
            print("    u%-4s %-16s (%d,%d)%s" % (uid, vid, col, row, " MORT" if dead else ""))

        # ---------------- PORT : execute l'arbre sur l'etat AVANT ----------------
        st, board = load_port_state(s, rid)
        from engine.runner.abilities.handler import ABILITY_CLASSES
        from engine.entities.active_ability_type import ActiveAbilityType
        from engine.runner.components import PositionComponent, UnitComponent
        cls = ABILITY_CLASSES.get(ActiveAbilityType.ItItches)
        if cls is None:
            print("[550] ECHEC : 1121 absente d'ABILITY_CLASSES")
            return 1
        tile_id = board.id_at(T_POS[0], T_POS[1])
        port_res = cls().execute_behaviour(st, cid, tile_id) or {}
        port_pos = {}
        for eid, e in st.entities.items():
            pc = e.get_component(PositionComponent)
            uc = e.get_component(UnitComponent)
            if uc is None:
                continue
            port_pos[eid] = (uc.visual_id, None if pc is None else pc.col,
                             None if pc is None else pc.row, not uc.alive)
        print("[550] PORT  : direction=%s pinned=%s" % (port_res.get("direction"),
                                                        port_res.get("pinned")))
        for p in (port_res.get("pushed") or []):
            print("    push u%-4s moved=%-5s to=%s reason=%s killed=%s"
                  % (p["unit"], p["moved"], p.get("to"), p.get("reason"), p.get("killed")))
        print("    spawned=%s  attacks=%s  movement_reset=%s"
              % (port_res.get("spawned"), port_res.get("attacks"), port_res.get("movement_reset")))

        # ---------------- NATIF : le meme cast via applyAction ----------------
        info = board.by_id[tile_id]
        res = rpc(s, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "abilityType": IT_ITCHES,
            "to": {"col": info["col"], "row": info["row"]}}}, 90) or {}
        act = (res.get("actions") or [{}])[0]
        if act.get("error"):
            print("[550] cast natif REFUSE : %s" % act.get("error"))
            return 1
        after = live_units(s, rid)
        pos_after = positions(after)
        print("[550] APRES (natif) :")
        for uid, (vid, col, row, dead) in sorted(pos_after.items()):
            was = pos_before.get(uid)
            mark = ""
            if was is None:
                mark = "   <- APPARU"
            elif (was[1], was[2]) != (col, row):
                mark = "   <- POUSSE depuis (%s,%s)" % (was[1], was[2])
            print("    u%-4s %-16s (%s,%s)%s%s" % (uid, vid, col, row,
                                                   " MORT" if dead else "", mark))

        # ---------------- CONFRONTATION etage par etage ----------------
        print("\n[550] CONFRONTATION")
        # E1/E3 : positions finales des ennemis, une par une
        ok_push = True
        for uid, (vid, col, row, dead) in sorted(pos_after.items()):
            if uid not in port_pos or vid == SUMMON_VID:
                continue
            pv, pc_, pr_, pd = port_pos[uid]
            same = (pc_, pr_) == (col, row) and pd == dead
            if not same:
                ok_push = False
            print("    E1/E3 u%-4s %-16s natif=(%s,%s)%s port=(%s,%s)%s -> %s"
                  % (uid, vid, col, row, " MORT" if dead else "",
                     pc_, pr_, " MORT" if pd else "", "OK" if same else "DIVERGE"))
        # E2 : effet Pinned. `observeBattle` ne publie PAS les effets -> canal `decisionView`
        # (`units[].effects`, la source des effets du port, cf. `snapshot.load_state`).
        dv2 = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 60) or {}
        pin_native = sorted(u.get("id") for u in (dv2.get("units") or [])
                            if any(int((e or {}).get("effectType") or 0) == 1065   # 0x429 Pinned
                                   for e in (u.get("effects") or [])))
        print("    E2 Pinned (0x429) natif=%s  port=%s"
              % (pin_native, sorted(port_res.get("pinned") or [])))
        # E4 : summons. ⚠ IDENTIFIES PAR squadId NEUF, PAS par `visualId` : la resolution DOWNSTREAM
        # (`SpawnUnitBehaviour`, HORS `ExecuteBehaviour`) substitue la variante NPC concrete
        # (`tyranNpc2RipperSwarm`) au constant config (`tyranSmnRipperSwarm`) que le port mirrore --
        # ecart DEJA documente pour `AlphaWarrior` (meme kit, stats prises sur la config d'ABILITY,
        # seul le trait `Summon` differe). Comparer les visualId ferait rendre 0 a ce compteur, ce
        # qui est exactement ce qu'il a fait a son premier passage.
        known = set(pos_before)
        sn = [u for u in after if u.get("squadId") not in known]
        sn_pos = sorted((u.get("col"), u.get("row")) for u in sn if not u.get("isDead"))
        sp_pos = sorted((board.by_id[p["tile"]]["col"], board.by_id[p["tile"]]["row"])
                        for p in (port_res.get("spawned") or []) if p.get("tile") in board.by_id)
        print("    E4 summons natif=%d %s  port=%d %s -> %s"
              % (len(sn), sn_pos, len(port_res.get("spawned") or []), sp_pos,
                 "OK" if sn_pos == sp_pos else "DIVERGE"))
        if sn_pos != sp_pos:
            rc = 1
        # E5 : le caster peut-il encore agir ?
        dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 60) or {}
        print("    E5 ResetMovement : caster dans toActivate = %s (port movement_reset=%s)"
              % (cid in (dv.get("toActivate") or []), port_res.get("movement_reset")))
        # E6 : hypothese `getAbilityType`. Si la lambda rendait `1023 Burrowers` (la seule ACTIVE du
        # Ripper Swarm), le summon aurait QUITTE le plateau a l'apparition (`Burrowers` =
        # `RemoveUnitFromItsTiles(Caster, true)` -> `col/row` nuls, `alive` VRAI).
        on_board = [u for u in sn if not u.get("isDead") and u.get("col") is not None]
        off_board = [u for u in sn if not u.get("isDead") and u.get("col") is None]
        hp_delta = {}
        for uid, (vid, col, row, dead) in pos_after.items():
            b = next((x for x in before if x.get("squadId") == uid), None)
            a2 = next((x for x in after if x.get("squadId") == uid), None)
            if b is not None and a2 is not None and b.get("hp") != a2.get("hp"):
                hp_delta[uid] = (b.get("hp"), a2.get("hp"))
        print("    E6 on-appearance : %d summon(s) SUR le plateau, %d HORS plateau (enfouis) ; "
              "deltas de PV natif = %s" % (len(on_board), len(off_board), hp_delta))
        print("       -> HORS plateau > 0 signifierait `getAbilityType` = 1023 Burrowers ; "
              "des PV perdus cote ennemi = attaque normale (l'hypothese du port)")
        # E6bis -- LE CRAN QUANTITATIF : le TOTAL de degat par CIBLE, port vs natif. C'est ce qui
        # distingue « des summons ont attaque » (qu'un port approximatif satisferait) de « ils ont
        # attaque le meme, avec le meme pipeline de degat ».
        port_dmg: dict = {}
        for at in (port_res.get("attacks") or []):
            port_dmg[at["target"]] = port_dmg.get(at["target"], 0) + int(at.get("total") or 0)
        nat_dmg = {uid: (hp0 - hp1) for uid, (hp0, hp1) in hp_delta.items()}
        same_dmg = port_dmg == nat_dmg
        print("    E6bis degat on-appearance par cible : natif=%s  port=%s -> %s"
              % (nat_dmg, port_dmg, "BIT-EXACT" if same_dmg else "DIVERGE"))
        if not same_dmg:
            rc = 1
        if not ok_push:
            rc = 1
        print("\n[550] %s" % ("PROBE OK" if rc == 0 else "PROBE : DIVERGENCE (voir E1/E3)"))
    finally:
        if not a.keep:
            try:
                rpc(s, "disposeRunner", {"runnerId": rid}, 20)
                print("[550] runner %d dispose" % rid)
            except Exception as exc:
                print("[550] dispose KO: %s" % str(exc)[:200])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
