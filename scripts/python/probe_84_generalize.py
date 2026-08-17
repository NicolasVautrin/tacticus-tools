#!/usr/bin/env python
"""Probe #84d -- GENERALISATION du port LetTheGalaxyBurn (#84 volet 1), sur des configurations qui
n'ont PAS servi a construire le port :

  G1. autre CARRIER  : `blackHaarken` (arme Piercing MELEE, traits Terrifying/Flying) au lieu de
      `blackTerminator` -> le canal ne depend ni du profil d'arme ni du reste du kit ;
  G2. autre BOARD    : `C1_74` au lieu de `MC1_67` ;
  G3. cible sur DRYBUSH (cover HEBERGE par le terrain, `LightCoverAbility`) -> DISCRIMINANT du residu 5
      du case-doc : si `IdunBattleLogic.Entities.DSLTriggers$$HasTileStatusEffect` comptait les covers de terrain, le +1 serait
      SYSTEMATIQUE sur une cible en DryBush ; s'il ne compte que les status-effects DYNAMIQUES portes
      par l'entite-tuile (ce que le port mirrore), on doit retrouver l'oscillation ~33 %.
      Carrier MELEE choisi expres : LightCover est gate `!IsMeleeAttack` -> aucun confond de coups.

ASCII only. Usage: python probe_84_generalize.py [--carrier blackHaarken] [--board C1_74] [--rounds 14]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
# SORTIE de run -> `logs/` RELATIF au checkout (#314) : un chemin absolu ferait
# ecrire ce probe dans l'arbre principal depuis un worktree d'agent.
STATE = PYDIR.parents[1] / "logs" / "runners" / "_probe84_generalize_state.json"
SID = None
RID = None


def rpc(method, body, timeout=90):
    r = _rpc(SID, method, body, timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def main():
    global SID, RID
    ap = argparse.ArgumentParser()
    ap.add_argument("--carrier", default="blackHaarken")
    ap.add_argument("--board", default="C1_74")
    ap.add_argument("--rounds", type=int, default=14)
    ap.add_argument("--seed", type=int, default=84900)
    ap.add_argument("--target-terrain", default="DryBush",
                    help="terrain sur lequel PARQUER la cible (G3) ; vide = pas de contrainte")
    args = ap.parse_args()
    SID = _resolve_session()

    out = subprocess.run([sys.executable, str(PYDIR / "rl_duel.py"), "build",
                          "--seed", str(args.seed), "--state-file", str(STATE),
                          "--p-units", args.carrier, "--a-units", "bloodSanguinary",
                          "--board", args.board, "--hp-target", "900000",
                          "--hp-player", "900000"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    RID = None
    for ln in (out.stdout or "").splitlines():
        if "runnerId=" in ln:
            RID = int(ln.split("runnerId=")[1].split()[0]); break
    if RID is None:
        print("[build KO]", (out.stdout or "")[-400:], (out.stderr or "")[-400:]); return 2
    print(f"[gen] carrier={args.carrier} board={args.board} runner={RID}")

    bg = rpc("boardGraph", {"runnerId": RID}, 60)
    terr = {(t.get("col"), t.get("row")): t.get("tileDefId") for t in (bg.get("tiles") or [])}
    walk = [(t.get("col"), t.get("row")) for t in (bg.get("tiles") or []) if t.get("walkable")]
    park = [c for c in walk if terr.get(c) == args.target_terrain] if args.target_terrain else []
    # DRIVE : privilegier la tuile visee la plus ENTOUREE (un coin de board n'a pas assez de voisins
    # marchables pour y coller l'attaquant -> l'attaque part sans cible en portee).
    park.sort(key=lambda c: -sum(1 for d in walk if hexgeo.distance(c, d) == 1))
    print(f"[gen] tuiles {args.target_terrain} marchables = {park}")

    def dview():
        return rpc("decisionView", {"runnerId": RID, "maxRank": 1, "allAbilities": True})

    def tile_fx():
        tm = rpc("tileMeta", {"runnerId": RID}, 60)
        return {(t.get("col"), t.get("row")): [e.get("name") for e in (t.get("effects") or [])]
                for t in (tm.get("tiles") or [])}

    dv = dview()
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    me = next((u for u in units if u.get("visualId") == args.carrier), None)
    en = next((u for u in units if u.get("id") != (me or {}).get("id")), None)
    if me is None or en is None:
        print("[gen] 1v1 KO"); return 2
    myp, aid, tid = me.get("owner"), me["id"], en["id"]
    norm = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
    print(f"[gen] u{aid} effets = {[e.get('name') for e in (me.get('effects') or [])]}")

    rows = []
    for it in range(args.rounds):
        for _ in range(6):
            dv = dview()
            if dv.get("currentPlayer") == myp:
                break
            rpc("applyAction", {"runnerId": RID, "action": {"kind": "endturn"}}, 40)
        else:
            break
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        me = next((u for u in units if u.get("id") == aid), None)
        en = next((u for u in units if u.get("id") == tid), None)
        if me is None or en is None:
            break
        # G3 : parquer la cible sur le terrain vise (DRIVE, pas de fatalisme geometrique)
        T = upos(en)
        if park and T not in park:
            r = rpc("applyAction", {"runnerId": RID, "action": {
                "kind": "move", "unitId": tid, "to": {"col": park[0][0], "row": park[0][1]}}}, 40)
            if isinstance(r, dict) and r.get("ok"):
                T = park[0]
        nb = [c for c in walk if hexgeo.distance(c, T) == 1 and c != T]
        if not nb:
            break
        if upos(me) not in nb:
            rpc("applyAction", {"runnerId": RID, "action": {
                "kind": "move", "unitId": aid, "to": {"col": nb[0][0], "row": nb[0][1]}}}, 40)
        fx_before = tile_fx().get(T) or []
        res = rpc("applyAction", {"runnerId": RID, "action": {
            "kind": "ability", "casterId": aid, "targetId": tid, "abilityType": norm["id"]}}, 60)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        n = 0
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Target_Id") == tid \
                    and td.get("Active_Ability_Type") == norm["id"]:
                n += 1
        if n:
            rows.append((tuple(fx_before), n, terr.get(T)))
            print(f"[{it:02d}] T={T} terrain={terr.get(T)} tileFX={fx_before} -> hits={n}")
        else:
            print(f"[{it:02d}] T={T} A={upos(me)} attaque sans event: {str(res)[:200]}")
        rpc("applyAction", {"runnerId": RID, "action": {"kind": "endturn"}}, 40)

    subprocess.run([sys.executable, str(PYDIR / "rl_duel.py"), "dispose",
                    "--runner", str(RID), "--state-file", str(STATE)],
                   capture_output=True, text=True)
    if not rows:
        print("[gen] aucun echantillon"); return 1
    base = min(n for _f, n, _t in rows)
    a = [n for f, n, _t in rows if not f]
    b = [n for f, n, _t in rows if f]
    onterr = [n for _f, n, t in rows if t == args.target_terrain]
    print("\n=== GENERALISATION ===")
    print(f"base={base} | A(sans tile-fx dynamique) n={len(a)} {a} "
          f"-> +1 sur {sum(1 for n in a if n > base)}/{len(a)}")
    print(f"B(avec tile-fx dynamique) n={len(b)} {b}")
    print(f"cible sur terrain {args.target_terrain} : n={len(onterr)} {onterr} "
          f"-> +1 sur {sum(1 for n in onterr if n > base)}/{len(onterr)} "
          f"(si 100% ET aucun tile-fx dynamique => les covers de TERRAIN comptent : residu 5 a corriger)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
