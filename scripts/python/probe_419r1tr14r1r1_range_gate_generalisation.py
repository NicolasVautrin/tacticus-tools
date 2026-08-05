"""#419-r1-tr14-r1-r1 -- GENERALISATION de la porte de portee, sur un porteur MIXTE.

Le residu a ete ouvert sur `templNpc1Initiate` (npc, arme `Chain` de MELEE seule) : un porteur ou
la porte se reduit a « adjacent ou rien ». Ce probe la confronte sur un regime STRICTEMENT PLUS
RICHE, choisi pour que les trois issues de
`IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack(attacker,
attackerTiles, target)` soient TOUTES exercees et TOUTES distinguables :

    `adeptCanoness` (HERO du pool) -- armes `Chain` (melee, 3 coups) et `Bolter` (Range 2, 2 coups)

      d = 1  -> `FindMeleeWeapon`  -> `Chain`   -> prediction NON NULLE, 3 coups
      d = 2  -> `FindRangedWeapon` -> `Bolter`  -> prediction NON NULLE, 2 coups   (BOUNDARY `<=`)
      d = 3  -> `FindRangedWeapon` -> ensemble VIDE -> `null` -> prediction `0..0`, 1 coup

Les trois issues different par le NOMBRE DE COUPS autant que par les bornes : aucun accord ne peut
y etre degenere. Le cran `d = 2` garde en plus le SENS de l'inegalite : avec `dist < Range` au lieu
de `dist <= Range`, il tomberait a `0..0`.

MONTAGE : les unites sont DEPLACEES pour forcer la configuration (`P124._drive_to`), jamais subies.
La tuile d'attaque de chaque cran est prise dans les TUILES D'ACTION re-mesurees du caster.

Usage (depuis `scripts/python`) :
    python probe_419r1tr14r1r1_range_gate_generalisation.py --state-file <ABSOLU> [--seed 419141]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gameconfig as GC                                          # noqa: E402
import hexgeo                                                    # noqa: E402
import probe_124_line_elevation_decision as P124                 # noqa: E402
import probe_419r1tr14_heavy_bolt_pistol as P                    # noqa: E402
import probe_419r1tr14r1_heavy_bolt_pistol_real_carriers as P419  # noqa: E402

BOARD = "MC1_67"
HOST = "adeptCanoness"           # HERO du pool : `Chain` (melee, 3 coups) + `Bolter` (Range 2, 2)
ALLY = "necroWarden"             # garage ami
T_MAIN = "astraBullgryn"         # la cible
FOE1 = "astraCreed"              # garage ennemi
HP = 10000                       # personne ne meurt : les bornes restent lisibles
SEED_DEFAULT = "419141"          # le seed n'est qu'un generateur de bataille, hors critere
MontageError = P.MontageError


def build_extra() -> list:
    """Les arguments `rl_duel build` du montage, SANS `--seed` ni `--state-file` : c'est ce que la
    fixture `build_runner` du harnais consomme. Un seul foyer avec la voie CLI (`_build`)."""
    stats = [f"{v}:Health={HP},RemainingHealth={HP}" for v in (HOST, ALLY, T_MAIN, FOE1)]
    return ["--board", BOARD,
            "--p-units", ",".join((HOST, ALLY)), "--a-units", ",".join((T_MAIN, FOE1)),
            "--unit-stat", ";".join(stats)]


def host_weapons() -> list:
    return (GC.unit(HOST) or {}).get("weapons") or []


def attest_host_kit() -> dict:
    """Le montage EXIGE le regime a trois issues -- il ne le suppose pas. Si le kit du porteur
    change (arme retiree, portee modifiee), le probe le DIT au lieu de mesurer un lot degenere."""
    ws = host_weapons()
    melee = [w for w in ws if w.get("Range") is None or int(w["Range"]) < 2]
    ranged = [w for w in ws if w.get("Range") is not None and int(w["Range"]) >= 2]
    if not melee or not ranged:
        raise MontageError(f"{HOST} n'est plus un porteur MIXTE ({ws}) : le lot ne separerait plus "
                           f"les trois issues")
    rmax = max(int(w["Range"]) for w in ranged)
    hits_melee = {int(w.get("hits") or 0) for w in melee}
    hits_ranged = {int(w.get("hits") or 0) for w in ranged}
    if hits_melee == hits_ranged:
        raise MontageError(f"{HOST} : melee et distance portent le MEME nombre de coups "
                           f"({hits_melee}) -- les crans d=1 et d=2 deviendraient indiscernables "
                           f"par les coups")
    return {"weapons": [(w.get("DamageProfile"), w.get("Range"), w.get("hits")) for w in ws],
            "range_max": rmax, "hits_melee": sorted(hits_melee),
            "hits_ranged": sorted(hits_ranged)}


def _build(state_file: str, seed: str) -> int:
    cmd = ([sys.executable, "rl_duel.py", "build", "--seed", seed, "--state-file", state_file]
           + build_extra())
    r = subprocess.run(cmd, capture_output=True, text=True,
                       cwd=str(Path(__file__).resolve().parent))
    if r.returncode != 0:
        raise MontageError(f"rl_duel build rc={r.returncode} : {(r.stdout + r.stderr)[-600:]}")
    rid = json.loads(Path(state_file).read_text(encoding="utf-8")).get("runnerId")
    if rid is None:
        raise MontageError("build sans runnerId")
    return int(rid)


def _dispose(state_file: str) -> None:
    try:
        subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", state_file],
                       capture_output=True, text=True,
                       cwd=str(Path(__file__).resolve().parent), timeout=120)
    except Exception:
        pass


def _roster(rpc, rid: int) -> tuple:
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee")
    myplayer = mine[0].get("owner")
    ids = {}
    for key, vis in (("C", HOST), ("F", ALLY)):
        u = next((x for x in mine if x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster ami")
        ids[key] = u["id"]
    for key, vis in (("T", T_MAIN), ("E1", FOE1)):
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster adverse")
        ids[key] = u["id"]
    return dv, ids, myplayer


def find_layout(cells: list, elev: dict, rmax: int) -> "dict | None":
    """(T, C, K1, K2) : la cible, le caster A DISTANCE 2 d'elle (ses tuiles d'action couvrent alors
    les distances 1..rmax+1 a la cible), et deux garages loin de tout. Elevation EGALE partout :
    le bonus d'elevation ne doit pas bouger d'un cran a l'autre, sans quoi il masquerait la porte."""
    by_elev: dict = {}
    for p in cells:
        by_elev.setdefault(elev.get(p), []).append(p)
    for _e, pool in sorted(by_elev.items(), key=lambda kv: -len(kv[1])):
        for t in pool:
            for c in pool:
                if hexgeo.distance(c, t) != 2:
                    continue
                # il faut que les trois distances visees existent autour de la cible, sur le meme
                # palier d'elevation, et soient LIBRES (les garages iront ailleurs).
                ring = {d: [p for p in pool if hexgeo.distance(p, t) == d and p != c]
                        for d in (1, rmax, rmax + 1)}
                if not all(ring[d] for d in ring):
                    continue
                far = [p for p in pool
                       if hexgeo.distance(p, t) >= rmax + 3 and hexgeo.distance(p, c) >= rmax + 3]
                if len(far) < 2:
                    continue
                return {"T": t, "C": c, "K1": far[0], "K2": far[1]}
    return None


def run(sid, rpc, rid: int) -> dict:
    kit = attest_host_kit()
    rmax = kit["range_max"]
    elev, walk, _tid = P124._board(sid, rid)
    _dv, ids, myplayer = _roster(rpc, rid)
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    lay = find_layout(cells, elev, rmax)
    if lay is None:
        raise MontageError(f"montage NON INSTALLE : aucune configuration (T,C,K1,K2) sur {BOARD}")
    wanted = {ids["C"]: lay["C"], ids["T"]: lay["T"], ids["F"]: lay["K1"], ids["E1"]: lay["K2"]}
    if not P124._drive_to(sid, rid, walk, elev, wanted):
        _d, pos = P124._positions(sid, rid)
        raise MontageError(f"placement INCOMPLET : voulu {wanted}, obtenu "
                           f"{ {u: pos.get(u) for u in wanted} }")
    P124._give_turn_back(sid, rid, myplayer)
    _dv2, ctx = P._fresh_ctx(rpc, rid, ids["C"])
    ab = next(iter(ctx.normal_ids or ()), None)
    if ab is None:
        raise MontageError("montage NON INSTALLE : aucune attaque normale sur le caster")
    tiles = [t for t in (ctx.action_tiles or []) if t and t[0] is not None]
    t_pos = lay["T"]
    rows = []
    for d in (1, rmax, rmax + 1):
        cand = [t for t in tiles if hexgeo.distance(tuple(t), t_pos) == d]
        if not cand:
            raise MontageError(f"cran d={d} NON MESURABLE : aucune tuile d'action a cette distance "
                               f"de la cible (tuiles = {sorted(tiles)[:12]})")
        tile = tuple(cand[0])
        pn = P419.native_prediction(rpc, rid, ids["C"], ids["T"], ab, tile)
        pp = P419.port_prediction(ctx.scene, ids["C"], ids["T"], tile)
        rows.append({"d": d, "tile": tile, "native": pn, "port": pp})
    return {"rid": rid, "kit": kit, "layout": lay, "ab": int(ab), "rows": rows,
            "range_max": rmax}


def _draws(a: int, b: int) -> int:
    return b - a + (624 if b < a else 0)


def _rng(s):
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"])
    r.mti = s["mti"]
    return r


def _attack_once(sid, rpc, rid: int, board, att: int, tgt: int, norm_id: int) -> dict:
    """UNE attaque normale, jouee LIVE puis REJOUEE OFFLINE sur l'etat PRE-attaque. Rend le degat et
    le nombre de tirages RNG des deux cotes -- le patron de `test_dead_attacker_noop_live.py`."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.components import HealthComponent
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    st = load_state(dv, ob, snap)
    st.board = board
    te = st.get_entity(tgt)
    hc = te.get_component(HealthComponent) if te is not None else None
    hp_before = hc.hp if hc is not None else None
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(s0, dict) and s0.get("ok")):
        raise MontageError("dumpRng KO : le no-op ne serait pas mesurable cote RNG")
    st.rng = _rng(s0)
    mti0 = st.rng.mti
    runner = Runner(st).install_default_handlers(20)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tgt, "abilityType": int(norm_id)}}, 40)
    s1 = rpc("dumpRng", {"runnerId": rid}, 30)
    live_nd = _draws(s0["mti"], s1["mti"]) if isinstance(s1, dict) and s1.get("ok") else None
    live_after = next((u.get("hp") for u in ((res or {}).get("units") or [])
                       if u.get("squadId") == tgt), None)
    live_dmg = (hp_before - live_after) if (hp_before is not None and live_after is not None) else None
    runner.apply(AttackUnitMessage(att, tgt))
    off_nd = _draws(mti0, st.rng.mti)
    off_after = st.get_entity(tgt).get_component(HealthComponent).hp
    off_dmg = (hp_before - off_after) if hp_before is not None else None
    return {"hp_before": hp_before, "live_dmg": live_dmg, "live_nd": live_nd,
            "off_dmg": off_dmg, "off_nd": off_nd,
            "last_none": runner.damage_handler.last is None}


def run_combat(sid, rpc, rid: int) -> dict:
    """LA FACE COMBAT du meme foyer.
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteBehaviour` est
    tout entier `weapon = FindAttackWeapon(entities); if (weapon == null) return;` -- le MEME slot
    `0xaf` que `PredictAttack`. Deux crans, sur le meme porteur mixte :

      * caster REELLEMENT a distance 1 -> arme `Chain` -> degat > 0 (le gate est INERTE) ;
      * caster REELLEMENT a distance Range+1 -> aucune arme -> NO-OP : 0 degat ET 0 tirage RNG.

    Les deux sont confrontes LIVE contre le rejeu OFFLINE du meme etat -- c'est ce qui distingue
    « le port no-ope comme le natif » de « le port no-ope pour une autre raison »."""
    from engine.entities.pathfinding.board import Board
    kit = attest_host_kit()
    rmax = kit["range_max"]
    elev, walk, _tid = P124._board(sid, rid)
    _dv, ids, myplayer = _roster(rpc, rid)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        raise MontageError("boardGraph indisponible : l'etat offline ne serait pas montable")
    board = Board(bg["tiles"], adjacency="native_sym")
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    lay = find_layout(cells, elev, rmax)
    if lay is None:
        raise MontageError(f"montage NON INSTALLE : aucune configuration sur {BOARD}")
    t_pos = lay["T"]
    same = [p for p in cells if elev.get(p) == elev.get(t_pos)]
    spots = {}
    for d in (1, rmax + 1):
        cand = [p for p in same
                if hexgeo.distance(p, t_pos) == d and p not in (lay["K1"], lay["K2"], t_pos)]
        if not cand:
            raise MontageError(f"cran combat d={d} NON INSTALLABLE : aucune tuile a cette distance")
        spots[d] = cand[0]
    out = {}
    for d in (1, rmax + 1):
        wanted = {ids["C"]: spots[d], ids["T"]: t_pos, ids["F"]: lay["K1"], ids["E1"]: lay["K2"]}
        if not P124._drive_to(sid, rid, walk, elev, wanted):
            _dd, pos = P124._positions(sid, rid)
            raise MontageError(f"cran combat d={d} : placement INCOMPLET -- voulu {wanted}, obtenu "
                               f"{ {u: pos.get(u) for u in wanted} }")
        P124._give_turn_back(sid, rid, myplayer)
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        cu = next((u for u in (dv.get("units") or []) if u.get("id") == ids["C"]), {})
        norm = next((a for a in (cu.get("abilities") or []) if a.get("kind") == "normal"), {})
        if norm.get("id") is None:
            raise MontageError("aucune attaque normale sur le caster")
        out[d] = _attack_once(sid, rpc, rid, board, ids["C"], ids["T"], norm["id"])
        out[d]["spot"] = spots[d]
    return {"rid": rid, "kit": kit, "range_max": rmax, "target": t_pos, "crans": out}


def verdict(res: dict) -> list:
    """Les trois lectures que ce lot garde, rendues en clair (le test les asserte)."""
    out = []
    rows = {r["d"]: r for r in res["rows"]}
    rmax = res["range_max"]
    for d, r in sorted(rows.items()):
        n, p = r["native"], r["port"]
        out.append(("accord d=%d" % d,
                    (n["dmin"], n["dmax"], n["hits"]) == (p["dmin"], p["dmax"], p["hits"]),
                    "natif %s..%s (%s coups) / port %s..%s (%s)"
                    % (n["dmin"], n["dmax"], n["hits"], p["dmin"], p["dmax"], p["hits"])))
    n1, n2, n3 = rows[1]["native"], rows[rmax]["native"], rows[rmax + 1]["native"]
    out.append(("melee d=1 non nulle", (n1["dmin"], n1["dmax"]) != (0, 0),
                "%s..%s (%s coups)" % (n1["dmin"], n1["dmax"], n1["hits"])))
    out.append(("boundary d=%d INCLUSIF" % rmax, (n2["dmin"], n2["dmax"]) != (0, 0),
                "%s..%s (%s coups)" % (n2["dmin"], n2["dmax"], n2["hits"])))
    out.append(("hors portee d=%d VIDE" % (rmax + 1), (n3["dmin"], n3["dmax"], n3["hits"]) == (0, 0, 1),
                "%s..%s (%s coups)" % (n3["dmin"], n3["dmax"], n3["hits"])))
    out.append(("les trois issues DIFFERENT",
                len({(r["native"]["dmin"], r["native"]["dmax"], r["native"]["hits"])
                     for r in res["rows"]}) == 3,
                str([(r["d"], r["native"]["dmin"], r["native"]["dmax"], r["native"]["hits"])
                     for r in res["rows"]])))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed", default=SEED_DEFAULT)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--combat", action="store_true",
                    help="joue AUSSI la face COMBAT (`ExecuteBehaviour`), sur un runner separe")
    args = ap.parse_args()
    sf = os.path.abspath(args.state_file)
    os.makedirs(os.path.dirname(sf), exist_ok=True)
    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = _build(sf, args.seed)
    try:
        res = run(sid, rpc, rid)
        print("PORTEUR %s -- armes %s" % (HOST, res["kit"]["weapons"]))
        print("LAYOUT  %s" % res["layout"])
        print("ABILITY attaque normale = %d" % res["ab"])
        for r in res["rows"]:
            n, p = r["native"], r["port"]
            print("  d=%d tuile=%s  natif %s..%s (%s coups)  port %s..%s (%s coups)"
                  % (r["d"], r["tile"], n["dmin"], n["dmax"], n["hits"],
                     p["dmin"], p["dmax"], p["hits"]))
        ok = True
        for name, val, detail in verdict(res):
            print("  [%s] %-28s %s" % ("OK" if val else "KO", name, detail))
            ok = ok and val
        if args.combat:
            cmb = run_combat(sid, rpc, rid)
            print("FACE COMBAT (`ExecuteBehaviour`) -- cible %s" % (cmb["target"],))
            for d, c in sorted(cmb["crans"].items()):
                print("  d=%d spot=%s  live dmg=%s tirages=%s | offline dmg=%s tirages=%s"
                      % (d, c["spot"], c["live_dmg"], c["live_nd"], c["off_dmg"], c["off_nd"]))
            near = cmb["crans"][1]
            far = cmb["crans"][cmb["range_max"] + 1]
            checks = [
                ("d=1 le gate est INERTE", (near["live_dmg"] or 0) > 0,
                 "live %s / offline %s" % (near["live_dmg"], near["off_dmg"])),
                ("d=1 accord live/offline", near["live_dmg"] == near["off_dmg"],
                 "live %s / offline %s" % (near["live_dmg"], near["off_dmg"])),
                ("hors portee : NO-OP natif", far["live_dmg"] == 0 and far["live_nd"] == 0,
                 "live dmg=%s tirages=%s" % (far["live_dmg"], far["live_nd"])),
                ("hors portee : NO-OP port", far["off_dmg"] == 0 and far["off_nd"] == 0,
                 "offline dmg=%s tirages=%s" % (far["off_dmg"], far["off_nd"])),
            ]
            for name, val, detail in checks:
                print("  [%s] %-28s %s" % ("OK" if val else "KO", name, detail))
                ok = ok and val
        return 0 if ok else 1
    finally:
        if not args.keep:
            _dispose(sf)


if __name__ == "__main__":
    raise SystemExit(main())
