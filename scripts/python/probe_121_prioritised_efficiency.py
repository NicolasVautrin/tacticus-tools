"""Probe #121 -- ou l'ETAGE du +25 % du trait `PrioritisedEfficiency` tombe-t-il, et sous quelles
conditions ? Mesure LIVE + reconstruction coup par coup des DEUX placements candidats.

RE (decompile = verite) :
  `IdunBattle.Entities.Effects.Loki.PrioritisedEfficiency_ExtraDmgEffect$$CreateEffectDamageBonusForAttack`
      = EffectBonus.ForPercentIncrease( DSLFactory.get_OwnerIsCaster,
                                        DSLFactory.ConfigConst(0xf, source@effet+0x60) )
  -> %-list du DamageModifiers ATTAQUANT, appliquee APRES percage/armure.

Ce que la probe MESURE (et qui ne se lit pas dans un total) :
  * le REGIME de `GetDamageWithPiercing` = `max(0, dmg - armure, dmg x percage/100)`. Dans le regime
    PLANCHER-PERCAGE (`dmg x p/100` gagne), un +25 % pre-percage et un +25 % post-percage donnent
    EXACTEMENT le meme nombre -> l'etat NE DISCRIMINE PAS l'etage. Dans le regime ARMURE
    (`dmg - armure` gagne), ils different de `0.25 x armure` par coup.
  * le vecteur ATTAQUE NORMALE (le natif n'a PAS de noeud `IsNormalAttack` -> le bonus doit AUSSI
    s'y appliquer), en plus du vecteur ABILITY deja couvert par #113.
  * l'ORIENTATION : un porteur ATTAQUE ne doit rien gagner (gate `get_OwnerIsCaster`).

Usage (depuis scripts/python) :
    python probe_121_prioritised_efficiency.py --phase regime   # balaye les cibles -> qui discrimine
    python probe_121_prioritised_efficiency.py --phase normal   # vecteur ATTAQUE NORMALE
    python probe_121_prioritised_efficiency.py --phase defense  # porteur ATTAQUE (orientation)

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

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.services.static_battle_rules import get_damage_with_piercing

PYDIR = Path(__file__).resolve().parent
# SORTIES du probe -> `logs/` (gitignore), jamais `data/` qui ne porte que des ENTREES versionnees
# et sert de garde-fou `git status` a l'isolation par worktree (#349).
LOGS = PYDIR.parent.parent / "logs" / "runners"
SEED_BC = LOGS / "_121_votann_bc.json"
BOARD = "MC1_67"
SEED = "31337"

BESERK, IRONMASTER, UTHAR = "votanBeserk", "votanIronmaster", "votanUthar"
SPARE = "spaceHound"
PE_EXTRA_DMG = "PrioritisedEfficiency_ExtraDmg"
AUGMENTED_ASSAULT = 1221


def _unwrap(r):
    return r["result"] if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=90):
    return _unwrap(_rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def ensure_seed_bc(units: str):
    if SEED_BC.exists():
        return
    subprocess.run([sys.executable, "catalog_inject.py", "--units", units, "--out", str(SEED_BC)],
                   cwd=str(PYDIR), check=True)


def build(state_file: str, p_units: str, a_units: str, extra=None) -> int:
    ensure_seed_bc(f"{BESERK},{IRONMASTER},{UTHAR}")
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", SEED,
                        "--board", BOARD, "--seed-bc", str(SEED_BC),
                        "--p-units", p_units, "--a-units", a_units,
                        "--state-file", state_file, *(extra or [])],
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    st = json.loads(Path(state_file).read_text(encoding="utf-8"))
    rid = st.get("runnerId")
    if rid is None:
        raise RuntimeError((p.stderr or p.stdout or "")[-1500:])
    return int(rid)


def upos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def find(d, vis):
    return next((u for u in (d.get("units") or []) if u.get("visualId") == vis), None)


def by_id(d, uid):
    return next((u for u in (d.get("units") or []) if u["id"] == uid), None)


def from_here(sid, rid, unit_id, ability_id):
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


def live_hits(a0, tgt_id, hp_before):
    """Degat par coup, lu des events (`UnitStats_RemainingHealth` + `Attack_DidCrit`)."""
    out, prev = [], int(hp_before or 0)
    for ev in (a0.get("events") or []):
        if ev.get("kind") != "action" or ev.get("entity") != tgt_id:
            continue
        tg = ev.get("tags") or ""
        if "UnitStats_RemainingHealth" not in tg or "Attack_DidCrit" not in tg:
            continue
        try:
            t = json.loads(tg)
        except Exception:
            continue
        hp = int(t.get("UnitStats_RemainingHealth"))
        out.append({"hp": hp, "dmg": prev - hp, "crit": bool(int(t.get("Attack_DidCrit") or 0))})
        prev = hp
    return out


def replay(dv0, ob0, snap0, rng0, board_obj, drop=()):
    st = load_state(dv0, ob0, snap0, board=board_obj)
    if isinstance(rng0, dict) and rng0.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(rng0["mt"])
        rng.mti = rng0["mti"]
        st.rng = rng
    if drop and st.effects is not None:
        for lst in st.effects.by_unit.values():
            for e in lst:
                if (getattr(e, "name", "") or "") in drop:
                    e.consumed = True
    return st


def regime(pct, per_hit_off, pierce, armor, base_min, base_max):
    """Reconstruit le tirage BRUT `raw` de chaque coup depuis le degat REDUIT sans bonus, puis rend
    les deux placements candidats. `raw` = `per_hit + armure` (regime ARMURE) ou
    `per_hit x 100/percage` (regime PLANCHER-PERCAGE) : on retient la branche COHERENTE avec les
    bornes de config ET avec `max(0, raw-armure, raw x p/100) == per_hit`."""
    rows = []
    for v in per_hit_off:
        cands = []
        if pierce > 0:
            cands.append(("pierce", int(round(v * 100.0 / pierce))))
        cands.append(("armor", int(v) + int(armor)))
        for kind, raw in cands:
            if not (base_min - 1 <= raw <= base_max + 1):
                continue
            if abs(int(get_damage_with_piercing(raw, pierce, armor)) - int(v)) > 1:
                continue
            post = int(round(int(get_damage_with_piercing(raw, pierce, armor)) * (1 + pct / 100.0)))
            pre = int(get_damage_with_piercing(int(round(raw * (1 + pct / 100.0))), pierce, armor))
            rows.append({"branch": kind, "raw": raw, "off": int(v), "post": post, "pre": pre,
                         "gap": pre - post})
            break
        else:
            rows.append({"branch": "?", "raw": None, "off": int(v), "post": None, "pre": None,
                         "gap": None})
    return rows


def _scenario(sid, rid, caster_vis, foe_vis, ability_id, want_dist, board_obj):
    drive(sid, rid, caster_vis, foe_vis, want_dist)
    dv0 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    c, f = find(dv0, caster_vis), find(dv0, foe_vis)
    if c is None or f is None:
        print(f"[{foe_vis}] caster/cible absents")
        return None
    dist = hexgeo.distance(upos(c), upos(f))
    if dist > want_dist:
        print(f"[{foe_vis}] geometrie : dist {dist} > {want_dist}")
        return None
    legal = from_here(sid, rid, c["id"], ability_id)
    if f["id"] not in legal:
        print(f"[{foe_vis}] cible {f['id']} hors fromHere {legal}")
        return None
    ob0 = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap0 = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    rng0 = rpc(sid, "dumpRng", {"runnerId": rid}, 30)
    act = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": c["id"], "targetId": f["id"],
        "abilityType": ability_id}}, 150)
    a0 = ((act or {}).get("actions") or [{}])[0]
    if not a0.get("mutated"):
        print(f"[{foe_vis}] cast non mute : {a0.get('error')}")
        return None
    return {"caster": c, "foe": f, "dv0": dv0, "ob0": ob0, "snap0": snap0, "rng0": rng0,
            "live": live_hits(a0, f["id"], f.get("hp"))}


def phase_regime(sid, args):
    """Balaye plusieurs cibles : pour chacune, REGIME de GetDamageWithPiercing + ecart POST/PRE."""
    from engine.entities.pathfinding.board import Board
    from engine.entities.effects.magnitude import trait_var
    from engine.runner.abilities.handler import ABILITY_CLASSES
    pct = int(trait_var("PrioritisedEfficiency", "prioritisedEfficiencyExtraDmgPct") or 0)
    print(f"[regime] prioritisedEfficiencyExtraDmgPct = {pct}")
    foes = (args.foes or "necroWarden,adeptRetributor,genesMagus").split(",")
    for foe in foes:
        rid = build(args.state, f"{BESERK},{SPARE}", f"{foe}")
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board_obj = Board(bg["tiles"], adjacency="evenq")
        sc = _scenario(sid, rid, BESERK, foe, AUGMENTED_ASSAULT, 1, board_obj)
        if sc is None:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
            continue
        res_on = ABILITY_CLASSES[AUGMENTED_ASSAULT]().execute_behaviour(
            replay(sc["dv0"], sc["ob0"], sc["snap0"], sc["rng0"], board_obj),
            sc["caster"]["id"], sc["foe"]["id"])
        res_off = ABILITY_CLASSES[AUGMENTED_ASSAULT]().execute_behaviour(
            replay(sc["dv0"], sc["ob0"], sc["snap0"], sc["rng0"], board_obj, drop=(PE_EXTRA_DMG,)),
            sc["caster"]["id"], sc["foe"]["id"])
        aon = (res_on or {}).get("attack") or {}
        aoff = (res_off or {}).get("attack") or {}
        print(f"\n[{foe}] runner {rid} pierce={aon.get('pierce')} armor={aon.get('armor')} "
              f"bounds=[{aon.get('base_min')},{aon.get('base_max')}]")
        print(f"[{foe}] live per-coup = {[h['dmg'] for h in sc['live']]} "
              f"crits={[h['crit'] for h in sc['live']]}")
        print(f"[{foe}] port ON  per-coup = {aon.get('per_hit')} total={aon.get('total')}")
        print(f"[{foe}] port OFF per-coup = {aoff.get('per_hit')} total={aoff.get('total')}")
        rows = regime(pct, aoff.get("per_hit") or [], int(aon.get("pierce") or 0),
                      int(aon.get("armor") or 0), int(aon.get("base_min") or 0),
                      int(aon.get("base_max") or 0))
        for i, r in enumerate(rows):
            print(f"[{foe}] coup {i}: branche={r['branch']} raw={r['raw']} off={r['off']} "
                  f"POST={r['post']} PRE={r['pre']} gap={r['gap']}")
        rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
    return None


def phase_normal(sid, args):
    """Vecteur ATTAQUE NORMALE (le natif n'a PAS de noeud IsNormalAttack -> le bonus s'y applique)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.operations.damage import AttackDamageOperation
    foe = args.foe or "necroWarden"
    rid = build(args.state, f"{BESERK},{SPARE}", foe)
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board_obj = Board(bg["tiles"], adjacency="evenq")
    drive(sid, rid, BESERK, foe, 1)
    dv0 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    c, f = find(dv0, BESERK), find(dv0, foe)
    norm = next((ab for ab in (c.get("abilities") or []) if ab.get("kind") == "normal"), None)
    print(f"[normal] runner {rid} dist={hexgeo.distance(upos(c), upos(f))} normal={norm}")
    if norm is None:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
        return None
    ob0 = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap0 = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    rng0 = rpc(sid, "dumpRng", {"runnerId": rid}, 30)
    act = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": c["id"], "targetId": f["id"],
        "abilityType": norm["id"]}}, 150)
    a0 = ((act or {}).get("actions") or [{}])[0]
    print("[normal] cast =", json.dumps({k: a0.get(k) for k in ("ok", "mutated", "error")}))
    lh = live_hits(a0, f["id"], f.get("hp"))
    print(f"[normal] live per-coup = {[h['dmg'] for h in lh]} crits={[h['crit'] for h in lh]}")
    on = AttackDamageOperation.execute(
        replay(dv0, ob0, snap0, rng0, board_obj), c["id"], f["id"])
    off = AttackDamageOperation.execute(
        replay(dv0, ob0, snap0, rng0, board_obj, drop=(PE_EXTRA_DMG,)), c["id"], f["id"])
    print(f"[normal] port ON  per-coup = {(on or {}).get('per_hit')} total={(on or {}).get('total')}")
    print(f"[normal] port OFF per-coup = {(off or {}).get('per_hit')} total={(off or {}).get('total')}")
    print(f"[normal] pierce={(on or {}).get('pierce')} armor={(on or {}).get('armor')}")
    rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
    return None


def phase_defense(sid, args):
    """ORIENTATION : le Votann est la CIBLE. `get_OwnerIsCaster` -> aucune contribution au degat
    RECU (contre-epreuve du volet defensif 1483, qui lui est `get_OwnerIsTarget`)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.operations.damage import AttackDamageOperation
    atk = args.foe or "necroWarden"
    rid = build(args.state, atk, f"{BESERK},{SPARE}")
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board_obj = Board(bg["tiles"], adjacency="evenq")
    drive(sid, rid, atk, BESERK, 1)
    dv0 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    a, v = find(dv0, atk), find(dv0, BESERK)
    if a is None or v is None:
        print("[defense] unites absentes")
        rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
        return None
    print("[defense] effets du Votann CIBLE =",
          [e.get("name") for e in (v.get("effects") or [])])
    norm = next((ab for ab in (a.get("abilities") or []) if ab.get("kind") == "normal"), None)
    print(f"[defense] runner {rid} dist={hexgeo.distance(upos(a), upos(v))} normal={norm}")
    if norm is None:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
        return None
    ob0 = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap0 = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    rng0 = rpc(sid, "dumpRng", {"runnerId": rid}, 30)
    act = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": a["id"], "targetId": v["id"],
        "abilityType": norm["id"]}}, 150)
    a0 = ((act or {}).get("actions") or [{}])[0]
    print("[defense] cast =", json.dumps({k: a0.get(k) for k in ("ok", "mutated", "error")}))
    lh = live_hits(a0, v["id"], v.get("hp"))
    print(f"[defense] live per-coup = {[h['dmg'] for h in lh]}")
    on = AttackDamageOperation.execute(
        replay(dv0, ob0, snap0, rng0, board_obj), a["id"], v["id"])
    off = AttackDamageOperation.execute(
        replay(dv0, ob0, snap0, rng0, board_obj, drop=(PE_EXTRA_DMG,)), a["id"], v["id"])
    print(f"[defense] port (effet sur la CIBLE present) per-coup = {(on or {}).get('per_hit')}")
    print(f"[defense] port (effet consomme)           per-coup = {(off or {}).get('per_hit')}")
    rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
    return None


PHASES = {"regime": phase_regime, "normal": phase_normal, "defense": phase_defense}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=sorted(PHASES))
    ap.add_argument("--state", default=str(LOGS / "_121_probe_state.json"))
    ap.add_argument("--foes", default=None, help="regime: liste de cibles (virgules)")
    ap.add_argument("--foe", default=None, help="normal/defense: unite adverse")
    args = ap.parse_args()
    sid = _resolve_session()
    PHASES[args.phase](sid, args)


if __name__ == "__main__":
    main()
