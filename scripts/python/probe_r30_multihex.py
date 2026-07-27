"""R30 -- substrat MULTI-HEX : mesurer l'EMPREINTE native d'une unite a N pieds.

Question binaire : « une unite occupant N tuiles est-elle representee, positionnee, deplacee et
ciblee par le port comme par le natif ? »

Porteur CONFRONTABLE (verifie) : `ultraDreadnought` (Galatian), MoW du pool
(`rl_duel build --list-pool` -> "8 MoW spawnables"). Son ability `DutyEternal` (1158) fait
`RemoveMachine + Spawn(ThreeTileUnitSpawnShape)` -> l'unite `ultraSmnDreadnought` apparait sur
**3 tuiles**. Levier MUNITIONS : `munitionsCost = 3` et le seed BC part a
`BC.Player.Players[*].MachineOfWarAmmo = 0` -> on patche le seed (meme levier que probe_129).
`initialCooldownTurns = 2` -> il faut faire tourner les tours avant que le cast passe.

CANAL DE MESURE (aucun nouveau hook) : le dump `matchState` du host,
`GET /api/runners/<rid>/latest-state`. Chaine native, la meme que `frida/public/src/runners.js` :

    Match(Type=4).Components[].Tiles[col][row]  -> tileId
    Unit(Type=1).Components[].Feet              -> [footEntityId, ...]  (UnitComponent._feet)
    Foot(Type=5).Components[].TileId            -> tileId               (UnitFootComponent)

L'empreinte = [coord(TileId(foot)) for foot in Feet], DANS L'ORDRE des Feet ; `Feet[0]` = la
MAIN TILE (`IdunBattle.Entities.EntityExtensions$$GetMainTileId` : pour un `UnitComponent` il prend
`_feet[0]` puis recurse sur le `UnitFootComponent.TileId` de ce pied).

Usage :  python probe_r30_multihex.py [--board MC1_67] [--seed 777] [--keep]
ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
import uuid
from pathlib import Path

from rl_collect_batch import _rpc, _resolve_session

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
HOST = "http://127.0.0.1:8765"
MOW = "ultraDreadnought"
ABILITY_DUTY_ETERNAL = 1158


def rpc(sid, method, args, timeout=120):
    r = _rpc(sid, method, [args], timeout=timeout)
    return r.get("result", r) if isinstance(r, dict) else r


def make_bc(ammo: int = 9) -> Path:
    """Seed BC + munitions de MoW (levier connu, cf. probe_129 / test_storm_speeder_live)."""
    src = ROOT / "data" / "seed-bc.json"
    bc = json.loads(src.read_text(encoding="utf-8"))
    for _pid, p in ((bc.get("Player") or {}).get("Players") or {}).items():
        if isinstance(p, dict) and p.get("PlayerType") != 2:      # Environment exclu
            p["MachineOfWarAmmo"] = ammo
    out = ROOT / "logs" / "runners" / f"bc-r30-{uuid.uuid4().hex[:8]}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bc), encoding="utf-8")
    return out


def build(seed: str, board: str, bc: Path, p_units: str, a_units: str):
    state = ROOT / "logs" / "runners" / f"st-r30-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
         "--seed-bc", str(bc), "--state-file", str(state), "--p-units", p_units,
         "--a-units", a_units, "--p-mow", MOW, "--no-ai"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO:", (p.stderr or p.stdout or "")[-1500:])
        return None, state
    return json.loads(state.read_text())["runnerId"], state


# --------------------------------------------------------------- lecture du matchState natif

def latest_state(rid: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"{HOST}/api/runners/{rid}/latest-state", timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:                                   # noqa: BLE001
        print("latest-state KO:", e)
        return None


def tile_id_to_coord(entities: list) -> dict:
    """`Match.Tiles[col][row] -> tileId` inverse (mirror de `runners.js::resumeRunnerState`)."""
    out = {}
    for e in entities:
        if not e:
            continue
        for c in (e.get("Components") or []):
            tiles = (c or {}).get("Tiles")
            if not (isinstance(tiles, list) and tiles and isinstance(tiles[0], list)):
                continue
            if not isinstance(tiles[0][0], int):
                continue
            for col, colv in enumerate(tiles):
                for row, tid in enumerate(colv):
                    out[tid] = (col, row)
            return out
    return out


def footprints(dump: dict) -> list:
    """[{id, visualId, feet:[(col,row)...], main:(col,row)}] pour chaque entite Type=1."""
    ms = (dump or {}).get("matchState") or {}
    ents = ms.get("_entities") or []
    coord = tile_id_to_coord(ents)
    out = []
    for e in ents:
        if not e or e.get("Type") != 1:
            continue
        feet_ids, visual = None, None
        for c in (e.get("Components") or []):
            if not c:
                continue
            if isinstance(c.get("Feet"), list) and feet_ids is None:
                feet_ids = c["Feet"]
            if isinstance(c.get("VisualId"), str) and visual is None:
                visual = c["VisualId"]
        if not feet_ids:
            continue
        feet = []
        for fid in feet_ids:
            foot = ents[fid] if 0 <= fid < len(ents) else None
            tid = None
            for c in ((foot or {}).get("Components") or []):
                if c and c.get("TileId") is not None:
                    tid = c["TileId"]
                    break
            feet.append(coord.get(tid))
        out.append({"id": e.get("Id"), "visualId": visual, "feet": feet,
                    "main": feet[0] if feet else None})
    return out


def show(tag: str, rid: int):
    dump = latest_state(rid)
    if dump is None:
        return []
    fps = footprints(dump)
    print(f"\n=== {tag} : {len(fps)} unites")
    for f in fps:
        n = len(f["feet"])
        mark = "  <== MULTI-HEX" if n > 1 else ""
        print("  id=%-4s %-24s feet=%d %s main=%s%s"
              % (f["id"], f["visualId"], n, f["feet"], f["main"], mark))
    return fps


# --------------------------------------------------------------------------------- scenario

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--p-units", default="ultraIntercessor,ultraCalgar")
    ap.add_argument("--a-units", default="necroWarden,necroSpyder")
    ap.add_argument("--to", default=None, help="hex cible du cast, 'col,row'")
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    sid = _resolve_session()
    bc = make_bc()
    rid, state_file = build(a.seed, a.board, bc, a.p_units, a.a_units)
    if rid is None:
        return 1
    print("runner", rid)
    try:
        show("T0 (avant DutyEternal)", rid)

        # cooldown initial = 2 rounds -> on fait tourner les tours jusqu'a ce que 1158 soit
        # `usable` sur la MoW, puis on caste sur un hex libre.
        mow_id, target = None, None
        for rnd in range(a.rounds):
            view = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
            units = (view or {}).get("units") or []
            for u in units:
                for ab in (u.get("abilities") or []):
                    if ab.get("id") == ABILITY_DUTY_ETERNAL:
                        mow_id = u.get("id")
                        print("  round %d : caster=%s %s ability 1158 usable=%s cd=%s ammo=%s"
                              % (rnd, mow_id, u.get("visualId"), ab.get("usable"),
                                 ab.get("cooldown"), ab.get("hasAmmo")))
                        if ab.get("usable") and ab.get("hasAmmo", True) \
                                and not (ab.get("cooldown") or 0):
                            target = "ready"
            if target:
                break
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}})
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}})
        if mow_id is None:
            print("KO: aucune unite ne porte 1158 dans decisionView")
            return 2
        if not target:
            print("KO: 1158 jamais castable apres %d rounds" % a.rounds)
            return 3

        to = None
        if a.to:
            c, r = a.to.split(",")
            to = {"col": int(c), "row": int(r)}
        else:
            # premiere tuile libre a distance raisonnable : on lit les tuiles de mouvement
            # d'une unite du roster comme proxy de « hex jouable et vide ».
            mv = rpc(sid, "aiMovableTiles", {"runnerId": rid}) or {}
            cand = None
            for entry in (mv.get("units") or []):
                for t in (entry.get("tiles") or []):
                    cand = {"col": t["col"], "row": t["row"]}
                    break
                if cand:
                    break
            to = cand
        print("cast 1158 caster=%s to=%s" % (mow_id, to))
        res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": mow_id, "abilityId": ABILITY_DUTY_ETERNAL,
            "to": to}})
        print("cast ->", json.dumps(res)[:800])

        show("T1 (apres DutyEternal)", rid)
    finally:
        if not a.keep:
            rpc(sid, "disposeRunner", {"runnerId": rid})
            print("\ndisposed runner", rid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
