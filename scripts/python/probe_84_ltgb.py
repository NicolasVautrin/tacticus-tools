#!/usr/bin/env python
"""Probe #84 -- LetTheGalaxyBurn (trait 1058 -> triggered 1482 -> effet 1477) volet 1 : le COUP ADDITIONNEL.

Mesure GROUND-TRUTH des DEUX branches du gate de `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`
(`OwnerIsCaster & (TargetHasTileEffect | IsPersistentData(0x5ca))`) :

  A. cible sur une tuile SANS status-effect -> `TargetHasTileEffect` FAUX, seule la pose 33%
     (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger` = `On(5=PreAttack) & OwnerIsCaster &
     Maybe(ConfigConst 0x2a = LetTheGalaxyBurnChancePct=33) & !HasTileStatusEffect(targets)`) peut
     armer le coup -> nb de coups = base OU base+1, frequence ~33%.
  B. cible sur une tuile AVEC status-effect -> `TargetHasTileEffect` VRAI -> base+1 SYSTEMATIQUE, et
     AUCUNE pose (le trigger de pose exige `!HasTileStatusEffect`).

Le tile-effect de la branche B est pose NATIVEMENT par le volet 2 du meme kit
(`IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour` -> `AddEffect(0x5c4=1476 DespoiledGround)`
sur la tuile de chaque cible quand le flag etait pose) : il suffit d'attaquer jusqu'a ce qu'il apparaisse.

Instrument : nb d'events de degat (`Amount`) de l'attaque NORMALE, croise avec `tileMeta` de la tuile
de la cible AVANT l'attaque.

ASCII only (cp1252).
Usage: python probe_84_ltgb.py --runner <rid> [--rounds 20]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

SID = None
RID = None


def rpc(method, body, timeout=90):
    r = _rpc(SID, method, body, timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def dview():
    return rpc("decisionView", {"runnerId": RID, "maxRank": 1, "allAbilities": True})


def tile_fx():
    tm = rpc("tileMeta", {"runnerId": RID}, 60)
    return {(t.get("col"), t.get("row")): [e.get("name") for e in (t.get("effects") or [])]
            for t in (tm.get("tiles") or [])}


def upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def main():
    global SID, RID
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, required=True)
    ap.add_argument("--rounds", type=int, default=20)
    args = ap.parse_args()
    SID = _resolve_session()
    RID = args.runner

    dv = dview()
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    me = next((u for u in units if u.get("ctrl")), None)
    en = next((u for u in units if not u.get("ctrl")), None)
    if me is None or en is None:
        print("ABORT: pas 1v1")
        return
    myp, aid, tid = me.get("owner"), me["id"], en["id"]
    norm = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
    print(f"[setup] attaquant u{aid} {me.get('visualId')} / cible u{tid} {en.get('visualId')} "
          f"normal={norm}")
    print(f"[setup] effets u{aid} = {[e.get('name') for e in (me.get('effects') or [])]}")

    bg = rpc("boardGraph", {"runnerId": RID}, 60)
    tiles = {(t.get("col"), t.get("row")): t for t in (bg.get("tiles") or [])}
    walk = [c for c, t in tiles.items() if t.get("walkable")]

    rows = []
    for it in range(args.rounds):
        for _ in range(6):
            dv = dview()
            if dv.get("currentPlayer") == myp:
                break
            rpc("applyAction", {"runnerId": RID, "action": {"kind": "endturn"}}, 40)
        else:
            print("[stop] jamais mon tour")
            break
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        me = next((u for u in units if u.get("id") == aid), None)
        en = next((u for u in units if u.get("id") == tid), None)
        if me is None or en is None:
            print("[stop] une unite est morte")
            break
        T = upos(en)
        if T is None:
            break
        # placer l'attaquant sur un voisin hex libre de la cible (melee)
        nb = [c for c in walk if hexgeo.distance(c, T) == 1 and c != T]
        if not nb:
            print("[stop] pas de voisin libre")
            break
        A = upos(me)
        if A not in nb:
            r = rpc("applyAction", {"runnerId": RID, "action": {
                "kind": "move", "unitId": aid, "to": {"col": nb[0][0], "row": nb[0][1]}}}, 40)
            if not (isinstance(r, dict) and r.get("ok")):
                print(f"[skip] move KO {str(r)[:120]}")
                rpc("applyAction", {"runnerId": RID, "action": {"kind": "endturn"}}, 40)
                continue
            A = nb[0]
        fx_before = tile_fx().get(T) or []
        res = rpc("applyAction", {"runnerId": RID, "action": {
            "kind": "ability", "casterId": aid, "targetId": tid, "abilityType": norm["id"]}}, 60)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        amounts = []
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Target_Id") == tid \
                    and td.get("Active_Ability_Type") == norm["id"]:
                amounts.append(td.get("Amount"))
        fx_after = tile_fx().get(T) or []
        rows.append({"i": it, "A": A, "T": T, "fx_before": fx_before, "fx_after": fx_after,
                     "hits": len(amounts)})
        print(f"[{it:02d}] A={A} T={T} tileFX_before={fx_before} -> hits={len(amounts)} "
              f"amounts={amounts} tileFX_after={fx_after}")
        rpc("applyAction", {"runnerId": RID, "action": {"kind": "endturn"}}, 40)

    a_rows = [r for r in rows if not r["fx_before"]]
    b_rows = [r for r in rows if r["fx_before"]]
    print("\n=== SYNTHESE ===")
    if a_rows:
        hs = [r["hits"] for r in a_rows]
        print(f"BRANCHE A (cible sur tuile SANS status-effect) : n={len(hs)} hits={hs} "
              f"min={min(hs)} max={max(hs)} pct_max={100*sum(1 for h in hs if h == max(hs))//len(hs)}")
    if b_rows:
        hs = [r["hits"] for r in b_rows]
        print(f"BRANCHE B (cible sur tuile AVEC status-effect {b_rows[0]['fx_before']}) : "
              f"n={len(hs)} hits={hs} min={min(hs)} max={max(hs)}")


if __name__ == "__main__":
    main()
