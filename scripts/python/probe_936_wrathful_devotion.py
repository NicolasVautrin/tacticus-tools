#!/usr/bin/env python
"""#936 -- `WrathfulDevotion` (passif `worldTerminator` << Wrask >>, TriggeredAbilityType 1214) :
CONFRONTATION LIVE vs PORT de ses DEUX faces, sur le MEME etat de depart.

RE + residus : `engine/runner/operations/triggers/loki/wrathful_devotion.py`.

MONTAGE (le meme pour les deux regimes, et il n'a rien de commode -- chaque unite y est un TEMOIN) :
duel `worldTerminator + worldJakhal + orksNob` (moi) vs `ultraTitus`, board `MC1_67`, seed 777.

    worldTerminator  le PORTEUR. Trait `TeleportStrike` -> il arrive SOUS `1035
                     TeleportStrike_TeleportingIn`, ce qui rend la face B jouable SANS RIEN MONTER.
    worldJakhal      allie **Chaos** (trait 0x7ea publie par `combatSnapshot.units[].traits`) :
                     temoin POSITIF du bras `UnitsWithTrait` quand il est adjacent, temoin NEGATIF
                     du bras `AdjacentFriends` quand il ne l'est pas.
    orksNob          allie **Xenos** (1006) et ADJACENT : le SEUL temoin qui separe
                     `UnitsWithTrait(Chaos)` d'un << tous les allies adjacents >>. Sans lui, un port
                     qui aurait oublie le trait passerait.
    ultraTitus       la victime de la face A (`--hp-target 1` -> l'attaque normale TUE a coup sur).

REGIME B -- `applyAction finish` sur Wrask. Le natif retire alors `1035` (T3 d'`ATeleportingEffect`,
`On(UnitFinishedTurn) & OwnerIsActor & HasTile(Owner)`), et `RemoveEffectOperation$$Execute` publie
`On(0x3b = UnitBecameTargetable)` en queue de corps. C'est CE vecteur que le port n'emettait nulle
part avant cette tranche.
REGIME A -- Wrask est amene au contact de Titus, puis l'ACHEVE d'une attaque normale ->
`On(0x36 = UnitDefeated)`, `OwnerIsActor`, `IsDefeatedByMeleeAttack`.

CE QUI EST COMPARE, terme a terme : le TOTAL de bouclier de CHAQUE unite (`combatSnapshot.units[]
.shields` cote natif, `ShieldComponent.get_total_shield()` cote port) et l'ENSEMBLE des porteurs de
chacun des DEUX marqueurs visuels. Le port rejoue le MEME geste sur l'etat capture AVANT, avec le
flux PRNG natif (`dumpRng`) -- aucun re-derivage, aucun ajustement.

MESURE DU 2026-08-11 (build `rnca9r7q6c`, rank 17, mult de rarete 180 %) :

    regime B   live {79: 3989, 81: 3989, 83: 0}   port {79: 3989, 81: 3989, 83: 0}
               visual Teleported live [79, 81]    port [79, 81]
               visual Killed     live []          port []
    regime A   live {79: 3989, 81: 0, 83: 0}      port {79: 3989, 81: 0, 83: 0}
               visual Teleported live []          port []      (la face A ne pose AUCUN marqueur)
               visual Killed     live []          port []

Le regime A est la confrontation LIVE du VERDICT DEAD : le natif lui-meme ne pose AUCUN marqueur
quand Wrask tue en melee -- la branche `triggerType == UnitDeath` (`0x517
WrathfulDevotionKilled_Visual`) est inatteignable, et le jeu le montre.

ASCII only. Usage (depuis scripts/python) :
    python probe_936_wrathful_devotion.py
    python probe_936_wrathful_devotion.py --face b
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "logs" / "probe936"

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402

BOARD = "MC1_67"
SEED = "777"
PORTEUR = "worldTerminator"
ALLIE_CHAOS = "worldJakhal"
ALLIE_XENOS = "orksNob"
VICTIME = "ultraTitus"


# --------------------------------------------------------------------------- transport
def rpc(sid, m, args, t=120):
    r = _rpc(sid, m, [args], timeout=t)
    return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}


def _build(tag: str, extra: list) -> tuple:
    sf = LOGS / f"probe936_{tag}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
           "--roster", "3", "--p-units", f"{PORTEUR},{ALLIE_CHAOS},{ALLIE_XENOS}",
           "--a-units", VICTIME, "--hp-player", "999999",
           "--state-file", str(sf), "--no-ai"] + extra
    p = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parent),
                       capture_output=True, text=True, timeout=900)
    if p.returncode != 0:
        raise SystemExit("MONTAGE : build KO -- " + (p.stdout or "")[-600:] + (p.stderr or "")[-600:])
    st = json.loads(sf.read_text(encoding="utf-8"))
    return (st.get("runnerId") or st.get("rid")), sf


def _snap3(sid, rid):
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    return dv, ob, snap


def _live_shields(snap) -> dict:
    return {int(u["entityId"]): sum(int(s.get("amount") or 0) for s in (u.get("shields") or []))
            for u in (snap.get("units") or [])}


def _live_visual(dv, name) -> list:
    return sorted(int(u["id"]) for u in (dv.get("units") or [])
                  if name in [e.get("name") if isinstance(e, dict) else e
                              for e in (u.get("effects") or [])])


def _port_state(sid, rid, dv, ob, snap):
    from engine.entities.pathfinding.board import Board
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import bind_live_rpc, load_state
    bind_live_rpc(lambda m, b=None, timeout=60: rpc(sid, m, b if b is not None else {}, timeout))
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise SystemExit("MONTAGE : `boardGraph` indisponible -- le gate d'adjacence est POSITIONNEL")
    st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
    mt = rpc(sid, "dumpRng", {"runnerId": rid}, 30) or {}
    if mt.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt, rng.mti = list(mt["mt"]), int(mt["mti"])
        st.rng = rng
    return st


def _port_shields(st) -> dict:
    from engine.runner.components import ShieldComponent
    out = {}
    for eid, e in st.entities.items():
        sc = e.get_component(ShieldComponent)
        out[int(eid)] = int(sc.get_total_shield()) if sc is not None else 0
    return out


def _port_visual(st, effect_type: int) -> list:
    if st.effects is None:
        return []
    return sorted(int(uid) for uid, effs in st.effects.by_unit.items()
                  if any(not e.consumed and int(e.effect_type) == int(effect_type)
                         for e in (effs or [])))


def _ids(dv) -> dict:
    return {u.get("visualId"): int(u["id"]) for u in (dv.get("units") or [])}


# --------------------------------------------------------------------------- les deux regimes
def run_face_b() -> dict:
    """Sortie de Deep Strike : `finish` sur Wrask -> retrait de `1035` -> `On(0x3b)`."""
    from engine.entities.effect_type import EffectType
    from engine.runner.messages import FinishUnitTurnMessage
    from engine.runner.runner import Runner
    rid, _sf = _build("b", [])
    sid = _resolve_session()
    try:
        dv, ob, snap = _snap3(sid, rid)
        n = _ids(dv)
        uids = {k: n[k] for k in (PORTEUR, ALLIE_CHAOS, ALLIE_XENOS, VICTIME) if k in n}
        if len(uids) != 4:
            raise SystemExit(f"MONTAGE : unites manquantes {sorted(n)}")
        avant_live = _live_shields(snap)
        effets_avant = [e.get("name") if isinstance(e, dict) else e
                        for e in (next(u for u in dv["units"]
                                       if u["id"] == uids[PORTEUR]).get("effects") or [])]
        st = _port_state(sid, rid, dv, ob, snap)
        avant_port = _port_shields(st)
        Runner(st).install_default_handlers(20).apply(FinishUnitTurnMessage(uids[PORTEUR]))
        port = {"shields": _port_shields(st),
                "teleported": _port_visual(st, int(EffectType.WrathfulDevotionTeleported_Visual)),
                "killed": _port_visual(st, int(EffectType.WrathfulDevotionKilled_Visual))}
        res = rpc(sid, "applyAction", {"runnerId": rid,
                                       "action": {"kind": "finish", "unitId": uids[PORTEUR]}}, 120)
        a0 = (res.get("actions") or [{}])[0]
        if not (res.get("ok") and a0.get("ok")):
            raise SystemExit("MONTAGE : `finish` live refuse -- " + str(res)[:300])
        dv2, _o2, snap2 = _snap3(sid, rid)
        live = {"shields": _live_shields(snap2),
                "teleported": _live_visual(dv2, "WrathfulDevotionTeleported_Visual"),
                "killed": _live_visual(dv2, "WrathfulDevotionKilled_Visual")}
        return {"regime": "B", "uids": uids, "effets_porteur_avant": effets_avant,
                "avant": {"live": avant_live, "port": avant_port}, "live": live, "port": port}
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 30)


def run_face_a() -> dict:
    """Kill en melee : Wrask acheve `ultraTitus` (1 PV) au contact -> `On(0x36)`."""
    from engine.entities.effect_type import EffectType
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.runner import Runner
    rid, _sf = _build("a", ["--hp-target", "1"])
    sid = _resolve_session()
    try:
        dv, _ob, _snap = _snap3(sid, rid)
        n = _ids(dv)
        uids = {k: n[k] for k in (PORTEUR, ALLIE_CHAOS, ALLIE_XENOS, VICTIME) if k in n}
        if len(uids) != 4:
            raise SystemExit(f"MONTAGE : unites manquantes {sorted(n)}")
        # 1) tout le monde finit son tour -- c'est ce qui SORT Wrask du Deep Strike (T3), donc son
        #    bouclier de face B est deja pose et sera EXPIRE par les fins de tour qui suivent.
        for uid in (uids[PORTEUR], uids[ALLIE_CHAOS], uids[ALLIE_XENOS]):
            rpc(sid, "applyAction", {"runnerId": rid,
                                     "action": {"kind": "finish", "unitId": uid}}, 90)
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        mien = next(u["owner"] for u in dv["units"] if u["id"] == uids[PORTEUR])
        for _ in range(6):
            dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            if dv.get("currentPlayer") == mien:
                break
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        # 2) amener Wrask au CONTACT (le gate melee est POSITIONNEL des deux cotes)
        for _ in range(12):
            dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            w = next((u for u in (dv.get("units") or [])
                      if u["id"] == uids[PORTEUR] and u.get("alive")), None)
            t = next((u for u in (dv.get("units") or [])
                      if u["id"] == uids[VICTIME] and u.get("alive")), None)
            if w is None or t is None:
                raise SystemExit("MONTAGE : unite disparue pendant l'approche")
            cibles = []
            for a in (w.get("abilities") or []):
                if a.get("kind") == "normal":
                    cibles += [c.get("id") if isinstance(c, dict) else c
                               for c in (a.get("targets") or [])]
            if uids[VICTIME] in cibles:
                break
            mt = rpc(sid, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            row = next((x for x in (mt.get("units") or []) if x.get("unitId") == uids[PORTEUR]), None)
            tiles = (row or {}).get("tiles") or []
            if not tiles:
                rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            tp = t.get("pos") or {}
            best = min(tiles, key=lambda x: abs(x["col"] - tp["col"]) + abs(x["row"] - tp["row"]))
            rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uids[PORTEUR],
                "to": {"col": best["col"], "row": best["row"]}}}, 90)
        # 3) l'etat de depart de la CONFRONTATION, puis le MEME coup des deux cotes
        dv, ob, snap = _snap3(sid, rid)
        positions = {int(u["id"]): u.get("pos") for u in (dv.get("units") or [])}
        avant_live = _live_shields(snap)
        st = _port_state(sid, rid, dv, ob, snap)
        avant_port = _port_shields(st)
        Runner(st).install_default_handlers(20).apply(
            AttackUnitMessage(uids[PORTEUR], uids[VICTIME]))
        port = {"shields": _port_shields(st),
                "teleported": _port_visual(st, int(EffectType.WrathfulDevotionTeleported_Visual)),
                "killed": _port_visual(st, int(EffectType.WrathfulDevotionKilled_Visual))}
        w2 = next(u for u in dv["units"] if u["id"] == uids[PORTEUR])
        nat = next((a for a in (w2.get("abilities") or []) if a.get("kind") == "normal"), None)
        if nat is None:
            raise SystemExit("MONTAGE : aucune attaque normale exposee sur le porteur")
        # `kind: attack` n'existe PAS -- l'attaque normale EST une ability (`NormalAttackType`).
        res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": uids[PORTEUR], "targetId": uids[VICTIME],
            "abilityType": nat["id"]}}, 120)
        a0 = (res.get("actions") or [{}])[0]
        if not (res.get("ok") and a0.get("ok")):
            raise SystemExit("MONTAGE : attaque live refusee -- " + str(res)[:300])
        hp = {int(u.get("squadId")): u.get("hp") for u in (res.get("units") or [])}
        dv2, _o2, snap2 = _snap3(sid, rid)
        # La bataille peut etre FINIE (le dernier ennemi meurt) : `decisionView` rend alors une
        # erreur, pas des unites. Les boucliers, eux, restent lisibles par `combatSnapshot`.
        live = {"shields": _live_shields(snap2),
                "teleported": _live_visual(dv2, "WrathfulDevotionTeleported_Visual")
                if dv2.get("units") else [],
                "killed": _live_visual(dv2, "WrathfulDevotionKilled_Visual")
                if dv2.get("units") else []}
        return {"regime": "A", "uids": uids, "positions": positions, "hp_apres": hp,
                "victime_morte": hp.get(uids[VICTIME]) == 0,
                "avant": {"live": avant_live, "port": avant_port}, "live": live, "port": port}
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 30)


def _verdict(r: dict) -> bool:
    ok = True
    uids = r["uids"]
    for nom in (PORTEUR, ALLIE_CHAOS, ALLIE_XENOS):
        uid = uids[nom]
        lv, pv = r["live"]["shields"].get(uid, 0), r["port"]["shields"].get(uid, 0)
        if lv != pv:
            print(f"[{r['regime']}] ECART bouclier {nom} (u{uid}) : live={lv} port={pv}")
            ok = False
    for cle in ("teleported", "killed"):
        if r["live"][cle] != r["port"][cle]:
            print(f"[{r['regime']}] ECART visual {cle} : live={r['live'][cle]} "
                  f"port={r['port'][cle]}")
            ok = False
    if r["live"]["killed"] or r["port"]["killed"]:
        print(f"[{r['regime']}] ECART : `WrathfulDevotionKilled_Visual` POSE -- sa branche est du "
              "DEAD CODE (`$$CreateTrigger` n'abonne pas `On(UnitDeath)`)")
        ok = False
    print(f"[{r['regime']}] boucliers live={r['live']['shields']} port={r['port']['shields']}")
    print(f"[{r['regime']}] visual teleported live={r['live']['teleported']} "
          f"port={r['port']['teleported']} | killed live={r['live']['killed']} "
          f"port={r['port']['killed']}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--face", default="both", choices=["a", "b", "both"])
    a = ap.parse_args()
    ok = True
    if a.face in ("b", "both"):
        r = run_face_b()
        print("[B] effets du porteur AVANT :", r["effets_porteur_avant"])
        ok = _verdict(r) and ok
    if a.face in ("a", "both"):
        r = run_face_a()
        print("[A] victime morte :", r["victime_morte"])
        ok = (_verdict(r) and r["victime_morte"]) and ok
    print("VERDICT:", "OK" if ok else "ECART")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
