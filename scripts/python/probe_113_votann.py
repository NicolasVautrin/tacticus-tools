"""Probe #113 -- confront LIVE des 3 actives Votann du lot 1 et de leurs 4 effets.

    AugmentedAssault (1221, votanBeserk)   -> AugmentedAssault_ReduceArmor    (1541)
    GravitonRifle    (1206, votanIronmaster) -> Stunned (1162) + owner-effect GravitonRifle_ExtraPierce (1484)
    AncestralFortune (1207, votanUthar)    -> AncestralFortune_ExtraCritChance (1485) + _ExtraBlockChance (1486)

Les 3 porteurs sont HORS du seed BC capture -> `catalog_inject.py` (#92) les injecte dans les DEUX
catalogues (`BC.Units` + `BC.Abilities`) ; sans le second, le cast faute (« system error »).

PIEGE DE MESURE (case-92 / #111) : une cible ILLEGALE rend le MEME observable qu'une ability inerte
(`ok:true`, `mutated:false`, groupe 12 present). On prend donc TOUJOURS la cible dans
`abilityTargets(...).fromHere` (castable SANS bouger), jamais dans `targets` (superset apres deplacement).

Usage :
    python probe_113_votann.py --phase stats     # crit/block INITIAL d'Uthar (gates CanAdd*Chance)
    python probe_113_votann.py --phase augmented # cast 1221 + statModSources de la cible
    python probe_113_votann.py --phase graviton  # cast 1206 vs cible Mechanical / non qualifiante
    python probe_113_votann.py --phase fortune   # cast 1207 self-buff + attaque conditionnelle

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
from rl_collect_batch import _rpc, _resolve_session

PYDIR = Path(__file__).resolve().parent
# SORTIES du probe -> `logs/` (gitignore, meurt avec le worktree). `data/` est VERSIONNE et ne porte
# que des ENTREES : une sortie qui y atterrit salit `git status` sans qu'on ait rien edite (#349).
LOGS = PYDIR.parent.parent / "logs" / "runners"
SEED_BC = LOGS / "_113_votann_bc.json"
BOARD = "MC1_67"

BESERK, IRONMASTER, UTHAR = "votanBeserk", "votanIronmaster", "votanUthar"
SPARE = "spaceHound"            # jamais activee : garde le tour OUVERT (buffs 1-round encore lisibles)
FOE_MECH = "necroWarden"        # Mechanical -> QUALIFIE le +extraPierceRatio de GravitonRifle
FOE_PLAIN = "bloodMephiston"    # ni Mechanical ni MkXGravis ni TerminatorArmour -> contre-cas


def _unwrap(r):
    if isinstance(r, dict) and "result" in r:
        return r["result"]
    return r


def rpc(sid, method, body=None, timeout=90):
    return _unwrap(_rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def ensure_seed_bc():
    if SEED_BC.exists():
        return
    subprocess.run([sys.executable, "catalog_inject.py", "--units",
                    f"{BESERK},{IRONMASTER},{UTHAR}", "--out", str(SEED_BC)],
                   cwd=str(PYDIR), check=True)


def build(state_file: str, p_units: str, a_units: str, seed: str = "31337",
          extra: list | None = None) -> int:
    ensure_seed_bc()
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", seed,
                        "--board", BOARD, "--seed-bc", str(SEED_BC),
                        "--p-units", p_units, "--a-units", a_units,
                        "--state-file", state_file, *(extra or [])],
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    st = json.loads(Path(state_file).read_text(encoding="utf-8"))
    rid = st.get("runnerId")
    if rid is None:
        raise RuntimeError((p.stderr or p.stdout or "")[-2000:])
    return int(rid)


def upos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def find(d, vis):
    return next((u for u in (d.get("units") or []) if u.get("visualId") == vis), None)


def legal_targets(sid, rid, unit_id, ability_id):
    """Cibles castables DEPUIS LA POSITION COURANTE (`fromHere`). JAMAIS `targets` (superset
    apres deplacement) -- c'est ce qui fait passer un refus de ciblage pour une ability inerte."""
    at = rpc(sid, "abilityTargets", {"runnerId": rid}, 90)
    for u in (at.get("units") or []):
        if u.get("unitId") != unit_id:
            continue
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != ability_id:
                continue
            fh = a.get("fromHere")
            src = fh if isinstance(fh, list) else (a.get("targets") or [])
            return [t.get("targetId") for t in src if t.get("targetId") is not None]
    return []


def drive(sid, rid, vis, goal_vis, want_dist, iters=16):
    """Rapproche `vis` a <= want_dist de `goal_vis` (mouvements legaux uniquement)."""
    for _ in range(iters):
        d = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        u, g = find(d, vis), find(d, goal_vis)
        if u is None or g is None:
            return d
        if hexgeo.distance(upos(u), upos(g)) <= want_dist:
            return d
        mov = rpc(sid, "aiMovableTiles", {"runnerId": rid, "side": "all"}, 60)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == u["id"]), None)
        tiles = [(t["col"], t["row"]) for t in (mu or {}).get("tiles") or []
                 if t.get("col") is not None
                 and hexgeo.distance((t["col"], t["row"]), upos(g)) >= want_dist]
        if not tiles:
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        best = min(tiles, key=lambda t: (hexgeo.distance(t, upos(g)), t))
        if hexgeo.distance(best, upos(g)) >= hexgeo.distance(upos(u), upos(g)):
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": u["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
    return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)


def snap_stats(sid, rid, uid):
    s = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    for u in (s.get("units") or []):
        if u.get("entityId") == uid:
            return u
    return {}


def phase_stats(sid, args):
    """Gates `CanAddCritChance` / `CanAddBlockChance` = `StatAmount(self, 9|7, 3=INITIAL) > 0`."""
    rid = build(args.state, f"{UTHAR},{SPARE}", FOE_MECH)
    print(f"[stats] runner {rid}")
    d = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    u = find(d, UTHAR)
    su = snap_stats(sid, rid, u["id"])
    print("[stats] uthar stats  =", json.dumps(su.get("stats") or {}))
    print("[stats] uthar delta  =", json.dumps(su.get("statDelta") or {}))
    print("[stats] uthar config =", json.dumps(su.get("unitConfig") or {}))
    print("[stats] statTypes    =", json.dumps(rpc(sid, "combatSnapshot",
                                                   {"runnerId": rid}, 60).get("statTypes") or {}))
    return rid


def _cast(sid, rid, caster_id, target_id, ability_type):
    act = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "targetId": target_id,
        "abilityType": ability_type}}, 150)
    a0 = ((act or {}).get("actions") or [{}])[0]
    return a0


def phase_augmented(sid, args):
    rid = build(args.state, f"{BESERK},{SPARE}", FOE_MECH)
    print(f"[augmented] runner {rid}")
    drive(sid, rid, BESERK, FOE_MECH, 1)
    d = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    c, f = find(d, BESERK), find(d, FOE_MECH)
    print("[augmented] dist =", hexgeo.distance(upos(c), upos(f)))
    tg = legal_targets(sid, rid, c["id"], 1221)
    print("[augmented] fromHere =", tg)
    if f["id"] not in tg:
        print("[augmented] ABORT : cible non legale depuis la position courante")
        return rid
    before = {"hp": f.get("hp"), "armor": snap_stats(sid, rid, f["id"]).get("stats", {})}
    print("[augmented] before =", json.dumps(before))
    a0 = _cast(sid, rid, c["id"], f["id"], 1221)
    print("[augmented] cast =", json.dumps({k: a0.get(k) for k in
                                            ("ok", "mutated", "actionConsumed", "error")}))
    d2 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    f2 = next((u for u in (d2.get("units") or []) if u["id"] == f["id"]), None)
    c2 = next((u for u in (d2.get("units") or []) if u["id"] == c["id"]), None)
    print("[augmented] target hp", f.get("hp"), "->", (f2 or {}).get("hp"))
    print("[augmented] target effects =", [e.get("name") for e in (f2 or {}).get("effects") or []])
    print("[augmented] caster effects =", [e.get("name") for e in (c2 or {}).get("effects") or []])
    print("[augmented] target stats after =",
          json.dumps(snap_stats(sid, rid, f["id"]).get("stats") or {}))
    for stat in (16, 4):
        sm = rpc(sid, "statModSources", {"runnerId": rid, "unitId": f["id"], "statType": stat}, 60)
        print(f"[augmented] statModSources(target, {stat}) =", json.dumps(sm)[:800])
    return rid


def phase_graviton(sid, args):
    rid = build(args.state, f"{IRONMASTER},{SPARE}", f"{FOE_MECH},{FOE_PLAIN}")
    print(f"[graviton] runner {rid}")
    d = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    v = find(d, IRONMASTER)
    print("[graviton] vynn effects =", [e.get("name") for e in (v or {}).get("effects") or []])
    goal = args.foe or FOE_MECH
    drive(sid, rid, IRONMASTER, goal, 2)
    d = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    v, f = find(d, IRONMASTER), find(d, goal)
    print("[graviton] dist =", hexgeo.distance(upos(v), upos(f)))
    tg = legal_targets(sid, rid, v["id"], 1206)
    print("[graviton] fromHere =", tg, "target", f["id"])
    if f["id"] not in tg:
        print("[graviton] ABORT : cible non legale depuis la position courante")
        return rid
    print("[graviton] target stats =", json.dumps(snap_stats(sid, rid, f["id"]).get("stats") or {}))
    a0 = _cast(sid, rid, v["id"], f["id"], 1206)
    print("[graviton] cast =", json.dumps({k: a0.get(k) for k in
                                           ("ok", "mutated", "actionConsumed", "error")}))
    d2 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    f2 = next((u for u in (d2.get("units") or []) if u["id"] == f["id"]), None)
    print("[graviton] target hp", f.get("hp"), "->", (f2 or {}).get("hp"),
          "delta", (f.get("hp") or 0) - ((f2 or {}).get("hp") or 0))
    print("[graviton] target effects =", [e.get("name") for e in (f2 or {}).get("effects") or []])
    return rid


def phase_fortune(sid, args):
    # Les DEUX gates natifs `CanAddCritChance` / `CanAddBlockChance` (`StatAmount(self, 9|7,
    # INITIAL) > 0`) se lisent sur la BASE de l'unite. Pour les exercer dans les DEUX sens, il faut
    # donc un montage a base NULLE et un montage a base POSITIVE -- et c'est le montage qui doit
    # l'ETABLIR, jamais une premisse ecrite (#914-r2, cran de #933/#914).
    #
    # ⚠ PREMISSE PERIMEE, corrigee ici : ce bloc disait << un heros FRAIS a critChance/blockChance
    # de BASE = 0, ces stats viennent des ITEMS que la normalisation strippe >>. C'etait vrai a
    # l'ecriture ; depuis #419-r5/-r6 `_normalize_and_extract_pool` EQUIPE les items Best-In-Slot
    # PAR DEFAUT (mesure sur le seed BC au rank 17 : `could_crit` 0/106 -> 98/106, `could_block`
    # 0/106 -> 46/106). Sans drapeau, la base n'est donc PLUS nulle : le gate etait VRAI des deux
    # cotes et la phase mesurait DEUX FOIS le meme sens en croyant les opposer.
    #
    # Le sens NEGATIF se CONSTRUIT desormais (`--unit-stat`), il ne se suppose plus. Pas
    # `TACTICUS_BIS_ITEMS=0`, qui deshabille tout le roster : c'est l'instrument de DIAGNOSTIC,
    # jamais le remede (#914 §3.3).
    extra = []
    if args.crit:
        extra += ["--crit", args.crit]
    else:
        extra += ["--unit-stat", "%s:CritChance=0,CritDamage=0" % UTHAR]
    if args.block:
        extra += ["--block-player", args.block]
    else:
        extra += ["--unit-stat", "%s:BlockChance=0,BlockDamage=0" % UTHAR]
    rid = build(args.state, f"{UTHAR},{SPARE}", FOE_MECH, extra=extra)
    print(f"[fortune] runner {rid} extra={extra}")
    drive(sid, rid, UTHAR, FOE_MECH, 1)
    d = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    u, f = find(d, UTHAR), find(d, FOE_MECH)
    print("[fortune] dist =", hexgeo.distance(upos(u), upos(f)))
    print("[fortune] uthar stats =", json.dumps(snap_stats(sid, rid, u["id"]).get("stats") or {}))
    tg = legal_targets(sid, rid, u["id"], 1207)
    print("[fortune] fromHere =", tg)
    tid = u["id"] if u["id"] in tg else (tg[0] if tg else u["id"])
    a0 = _cast(sid, rid, u["id"], tid, 1207)
    print("[fortune] cast =", json.dumps({k: a0.get(k) for k in
                                          ("ok", "mutated", "actionConsumed", "error")}))
    d2 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    u2 = next((x for x in (d2.get("units") or []) if x["id"] == u["id"]), None)
    f2 = next((x for x in (d2.get("units") or []) if x["id"] == f["id"]), None)
    print("[fortune] uthar effects =", [e.get("name") for e in (u2 or {}).get("effects") or []])
    print("[fortune] uthar stats after =",
          json.dumps(snap_stats(sid, rid, u["id"]).get("stats") or {}))
    print("[fortune] foe hp", f.get("hp"), "->", (f2 or {}).get("hp"),
          "delta", (f.get("hp") or 0) - ((f2 or {}).get("hp") or 0))
    for stat in (9, 7):
        sm = rpc(sid, "statModSources", {"runnerId": rid, "unitId": u["id"], "statType": stat}, 60)
        print(f"[fortune] statModSources(uthar, {stat}) =", json.dumps(sm)[:600])
    return rid


PHASES = {"stats": phase_stats, "augmented": phase_augmented,
          "graviton": phase_graviton, "fortune": phase_fortune}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=sorted(PHASES))
    ap.add_argument("--state", default=str(LOGS / "_113_probe_state.json"))
    ap.add_argument("--foe", default=None)
    ap.add_argument("--crit", default=None, help="'CC,CD' passe a rl_duel --crit (p-units)")
    ap.add_argument("--block", default=None, help="'BC,BD' passe a rl_duel --block-player")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    sid = _resolve_session()
    rid = PHASES[args.phase](sid, args)
    if rid is not None and not args.keep:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
        print(f"[probe] runner {rid} dispose")


if __name__ == "__main__":
    main()
