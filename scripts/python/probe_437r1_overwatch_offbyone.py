"""#437-r1 -- DECOMPOSITION PAR ETAGE de l'ecart de 1 sur le degat du tir d'overwatch.

`probe_437_overwatch_consumes_armour` mesure natif=1184 / port=1183 (regime UN tir, board
`MC1_67`, seed 4321). Un ecart de 1 sur un tir n'est pas « une imprecision » : c'est la
signature d'un ETAGE. Ce probe le localise, sans jamais fitter le scalaire.

DEUX MODES, volontairement separes pour ne monter QU'UN SEUL runner :

  * `--capture` : monte le montage #437, avance jusqu'au move DECLENCHEUR, capture sur disque
    (`logs/probe_437r1_capture.json`) tout ce dont le rejeu offline a besoin -- `decisionView`,
    `observeBattle`, `combatSnapshot`, `dumpRng`, `boardGraph` -- PLUS les bornes de degat que
    le NATIF lui-meme annonce pour ce tir (`aiPredict` = `GetAllPredictions`, le preview
    authoritatif de l'attaque normale) et la mesure native de PV.
  * `--replay` (defaut) : rejoue le meme move OFFLINE sur la capture, avec un intercepteur pose
    sur `AttackDamageOperation._run_hits` -- le foyer qui recoit les BORNES REDUITES
    (`hit_nc`/`hit_cr`), le nombre de coups et les sources de block, et qui rend les tirages.
    Etages imprimes : bornes -> tirages -> per-coup -> total.

Ce qui separe les etages :
  1. si les BORNES du port != celles du natif (`aiPredict`), l'ecart nait AVANT le tirage
     (percage / armure / modificateurs / materialisation `Fix64$$Round`) ;
  2. si les bornes sont EGALES et que le total differe, l'ecart nait au tirage
     (`IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` = Next(min,max+1))
     ou dans un etage AVAL (limites de trait, bouclier, ecretage).

ASCII only (cp1252). Discipline runner : state-file ABSOLU sous `logs/`, `--board` explicite,
dispose en sortie.

CLI (depuis scripts/python) :
  python probe_437r1_overwatch_offbyone.py --capture
  python probe_437r1_overwatch_offbyone.py --replay
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import probe_437_overwatch_consumes_armour as P          # noqa: E402
from probe_r6_round_materialize import _mkrpc            # noqa: E402

CAPTURE = ROOT / "logs" / "probe_437r1_capture.json"


# --------------------------------------------------------------------------- capture live


def _build_dmg(seed, board, ows, dmg_target, rank=17):
    """`P._build` + `--dmg-target` : DEPLACE la base d'attaque de l'overwatcher, donc la partie
    fractionnaire a chaque etage. C'est le levier qui fabrique les cas DISCRIMINANTS (sans lui, la
    base 4518 fait coincider deux modeles sur trois)."""
    import uuid as _uuid
    import subprocess as _sp
    sf = ROOT / "logs" / "runners" / ("p437r1c-%s.json" % _uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
           "--board", board, "--rank", str(rank),
           "--p-units", "%s,%s" % (P.CARRIER, P.SPECTATOR), "--a-units", ",".join(ows),
           "--hp-player", "400000", "--crit", "0,0", "--crit-target", "0,0",
           "--block-target", "0,0", "--block-player", "0,0", "--no-ai"]
    if dmg_target is not None:
        cmd += ["--dmg-target", str(dmg_target)]
    proc = _sp.run(cmd, cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                   errors="replace")
    if not sf.exists():
        return None, None, (proc.stderr or proc.stdout or "")[-800:]
    return int(json.loads(sf.read_text())["runnerId"]), sf, None


def capture(seed=P.SEED, board=P.BOARD, overwatchers=None, out=CAPTURE, dmg_target=None) -> dict:
    from engine.entities.pathfinding.board import Board

    ows = list(overwatchers or [P.OVERWATCHER])
    rid, sf, err = _build_dmg(seed, board, ows, dmg_target)
    if rid is None:
        return {"error": "build KO : %s" % err}
    rpc = _mkrpc()
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="native_sym")
        dv = P._view(rpc, rid, inactive=True)
        ids = {}
        for v in [P.CARRIER, P.SPECTATOR] + ows:
            u = P._by_vis(dv, v)
            if u is None:
                return {"error": "unite absente du build : %s" % v}
            ids[v] = int(u["id"])

        approach = []
        for _turn in range(24):
            dv = P._view(rpc, rid, inactive=True)
            reach = P._mover_reach(dv, ids[P.CARRIER])
            to_tile, d_ow = P._pick_move_tile(brd, dv, ids[P.CARRIER], ids[ows[0]], reach)
            if to_tile is None:
                return {"error": "aucune tuile d'arrivee libre", "approach": approach}
            hp0 = P._hp(dv, ids[P.CARRIER])
            player0 = dv.get("currentPlayer")
            ow_before = {v: P._armour_state(dv, ids[v], P.OVERWATCH_EFFECT)[1] for v in ows}
            # Ce que le NATIF annonce pour CE tir, AVANT qu'il parte : `GetAllPredictions` est le
            # meme `PredictAttack` (slot 4) que `AttackDamageOperation$$ExecuteHit` consulte pour
            # obtenir sa cellule, donc ses bornes SONT celles dans lesquelles le tirage tombe.
            preds = {}
            for v in ows:
                try:
                    preds[v] = rpc("aiPredict", {"runnerId": rid, "unitId": ids[v],
                                                 "targetId": ids[P.CARRIER], "fresh": True}, 90)
                except Exception as exc:                      # capteur absent -> on le DIT
                    preds[v] = {"error": "%s" % exc}
            cap = {"dec": P._view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
                   "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
                   "rng": rpc("dumpRng", {"runnerId": rid}, 30)}
            col, row = brd.coord(to_tile)
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": ids[P.CARRIER],
                "to": {"col": int(col), "row": int(row)}}}, 120)
            dv2 = P._view(rpc, rid, inactive=True)
            hp1 = P._hp(dv2, ids[P.CARRIER])
            ow_after = {v: P._armour_state(dv2, ids[v], P.OVERWATCH_EFFECT)[1] for v in ows}
            shots = [v for v in ows if ow_before.get(v) is True and ow_after.get(v) is False]
            approach.append({"to": [int(col), int(row)], "d_ow": d_ow, "hp": hp1,
                             "shots": list(shots)})
            if hp0 is not None and hp1 is not None and hp1 < hp0:
                blob = {"board_id": board, "seed": str(seed), "overwatchers": ows, "ids": ids,
                        "tiles": bg["tiles"], "cap": cap, "predictions": preds,
                        "move_to": [int(col), int(row)], "d_ow": d_ow,
                        "native": {"hp_before": hp0, "hp_after": hp1, "hp_delta": hp0 - hp1,
                                   "shots": shots, "n_shots": len(shots)},
                        "approach": approach}
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(blob), encoding="utf-8")
                print("[437r1] capture ECRITE : %s" % out)
                print("[437r1] NATIF : hp %s -> %s (delta=%s) | tirs=%d %s"
                      % (hp0, hp1, hp0 - hp1, len(shots), shots))
                for v, pr in preds.items():
                    print("[437r1] aiPredict[%s] = %s" % (v, json.dumps(pr)[:900]))
                return blob
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
            d3 = P._view(rpc, rid)
            if d3.get("currentPlayer") != player0:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        return {"error": "aucun tir en 24 tours", "approach": approach}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


# --------------------------------------------------------------------------- rejeu offline


def replay(blob: dict, mutate=False) -> dict:
    """Rejeu OFFLINE du move capture, avec un intercepteur sur `_run_hits` : c'est LUI qui recoit
    les bornes reduites et rend les tirages, donc il donne la ventilation par etage."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent
    from engine.runner.runner import Runner
    from engine.runner.messages import MoveUnitMessage
    from engine.runner.operations.damage import AttackDamageOperation

    brd = Board(blob["tiles"], adjacency="native_sym")
    cap = blob["cap"]
    mover_id = int(blob["ids"][P.CARRIER])
    st = load_state(cap["dec"], cap["ob"], cap["snap"], board=brd)
    hc = st.get_entity(mover_id).get_component(HealthComponent)
    hp_before = int(hc.hp)

    rng = IntBasedMersenneTwister()
    rng.mt = list(cap["rng"]["mt"])
    rng.mti = cap["rng"]["mti"]
    st.rng = rng

    # SOUS-ETAGES de `_reduced_bounds` : bornes BRUTES (`get_base_damage_fix64`), reduction
    # attaquant (`apply_pierce_and_modifiers` = percage + armure + mods), puis reduction
    # DEFENSEUR (`apply_all_modifiers`, ou vit la materialisation `Fix64$$Round`). Patch pose sur
    # les GLOBALS du module `damage_ops.normal` -- c'est la ou `execute` les resout (patch-point
    # documente en tete du module).
    from engine.runner.operations.damage_ops import normal as _nm
    sub = []
    _g_base, _g_pierce, _g_all = (_nm.get_base_damage_fix64, _nm.apply_pierce_and_modifiers,
                                  _nm.apply_all_modifiers)

    def _spy_base(*a, **k):
        r = _g_base(*a, **k)
        sub.append(("base", {"args": list(a), "kw": dict(k), "min": int(r.min), "max": int(r.max)}))
        return r

    def _spy_pierce(v, pierce, armor, mods, **k):
        r = _g_pierce(v, pierce, armor, mods, **k)
        sub.append(("pierce", {"in": v, "pierce": pierce, "armor": armor, "mods": repr(mods),
                               "kw": {kk: repr(vv) for kk, vv in k.items()}, "out": r}))
        return r

    def _spy_all(v, dmods, **k):
        r = _g_all(v, dmods, **k)
        sub.append(("defmods", {"in": v, "def_mods": repr(dmods), "kw": dict(k), "out": r}))
        return r

    # PROVENANCE des entrees de `%-list` : qui pose quoi, et sur quelle FACE. C'est ce qui separe
    # mon regime du cran DEUX FACES de #462-r4a (elevation = `ElevationBonus` de la BC, +50).
    _g_attmods, _g_elev, _g_trench, _g_defmods = (_nm.attacker_modifiers, _nm.apply_elevation_bonus,
                                                  _nm.apply_trench_reduction, _nm.defender_modifiers)

    def _snap(m):
        return {"pct": [list(x) for x in m.pct_list], "pct_def": [list(x) for x in m.pct_list_defender],
                "mult": m.multiplicative, "mult_def": m.multiplicative_defender,
                "add": m.additive, "details": [repr(d) for d in m.details],
                "flat": list(m.flat_reductions), "extra_pierce": m.extra_pierce}

    def _spy_attmods(*a, **k):
        m, act = _g_attmods(*a, **k)
        sub.append(("mods:attacker_modifiers", _snap(m)))
        sub.append(("mods:attacker_effects", {"active": [getattr(e, "name", None) for e in act]}))
        return m, act

    def _spy_elev(state, m, *a, **k):
        _g_elev(state, m, *a, **k)
        sub.append(("mods:after_elevation", _snap(m)))

    def _spy_trench(state, m, *a, **k):
        _g_trench(state, m, *a, **k)
        sub.append(("mods:after_trench", _snap(m)))

    def _spy_defmods(*a, **k):
        m, act = _g_defmods(*a, **k)
        sub.append(("mods:defender_modifiers", _snap(m)))
        sub.append(("mods:defender_effects", {"active": [getattr(e, "name", None) for e in act]}))
        return m, act

    _nm.get_base_damage_fix64 = _spy_base
    _nm.apply_pierce_and_modifiers = _spy_pierce
    _nm.apply_all_modifiers = _spy_all
    _nm.attacker_modifiers = _spy_attmods
    _nm.apply_elevation_bonus = _spy_elev
    _nm.apply_trench_reduction = _spy_trench
    _nm.defender_modifiers = _spy_defmods

    # L'ALEA BRUT du tirage de degat. `IntBasedMersenneTwister$$NextInternal` rend
    # `lo + ((genrand >> 1) % (hi - lo))` : connaissant `r = genrand >> 1`, les bornes NATIVES
    # s'INVERSENT sans rien inferer (meme methode que `solve_bounds` de #462-r4d) -- une valeur
    # tiree seule ne separe pas deux modeles, un `r` connu le fait.
    draws = []
    raws = []
    _g_ni = type(rng).next_internal
    _g_gr = type(rng).genrand_int32

    def _spy_gr(self):
        g = _g_gr(self)
        raws.append(int(g))
        return g

    def _spy_ni(self, lo, hi):
        n0 = len(raws)
        out = _g_ni(self, lo, hi)
        draws.append({"lo": int(lo), "hi": int(hi), "out": int(out),
                      "raws": [x >> 1 for x in raws[n0:]]})
        return out

    type(rng).genrand_int32 = _spy_gr
    type(rng).next_internal = _spy_ni

    stages = []
    orig = AttackDamageOperation._run_hits

    def _spy(rng_, hit_nc, hit_cr, crit_chance, crit_enabled, hits, block_sources, **kw):
        before = (getattr(rng_, "mti", None), )
        res = orig(rng_, hit_nc, hit_cr, crit_chance, crit_enabled, hits, block_sources, **kw)
        stages.append({
            "bounds_nc": [int(hit_nc.min), int(hit_nc.max)],
            "bounds_cr": [int(hit_cr.min), int(hit_cr.max)],
            "hits": int(hits), "crit_chance": crit_chance, "crit_enabled": bool(crit_enabled),
            "block_sources": list(block_sources or []),
            "shield": kw.get("shield"), "limits": str(kw.get("limits")),
            "limits_hp": kw.get("limits_hp"), "prevent_overkill": kw.get("prevent_overkill"),
            "capped_reductions": str(kw.get("capped_reductions")),
            "mti_before": before[0],
            "rolls": list(res.get("rolls") or []), "per_hit": list(res.get("per_hit") or []),
            "total": res.get("total"), "did_block": res.get("did_block"),
            "did_crit": res.get("did_crit"), "armor_dmg": res.get("armor_dmg"),
            "shield_dmg": res.get("shield_dmg"),
        })
        return res

    saved_disp = None
    if mutate:
        from engine.runner.operations.triggers import dispatch as _disp
        saved_disp = _disp.finish_attack_triggers
        _disp.finish_attack_triggers = lambda *a, **k: []
    AttackDamageOperation._run_hits = staticmethod(_spy)
    try:
        Runner(st).install_default_handlers(20).apply(
            MoveUnitMessage(mover_id, (int(blob["move_to"][0]), int(blob["move_to"][1]))))
    finally:
        AttackDamageOperation._run_hits = staticmethod(orig)
        type(rng).next_internal, type(rng).genrand_int32 = _g_ni, _g_gr
        _nm.get_base_damage_fix64, _nm.apply_pierce_and_modifiers, _nm.apply_all_modifiers = (
            _g_base, _g_pierce, _g_all)
        _nm.attacker_modifiers, _nm.apply_elevation_bonus = _g_attmods, _g_elev
        _nm.apply_trench_reduction, _nm.defender_modifiers = _g_trench, _g_defmods
        if saved_disp is not None:
            from engine.runner.operations.triggers import dispatch as _disp2
            _disp2.finish_attack_triggers = saved_disp
    return {"hp_before": hp_before, "hp_after": int(hc.hp), "hp_delta": hp_before - int(hc.hp),
            "stages": stages, "sub": sub, "draws": draws}


def _report(blob, out):
    n = blob["native"]
    print("[437r1] NATIF  : hp %s -> %s (delta=%s) | tirs=%d"
          % (n["hp_before"], n["hp_after"], n["hp_delta"], n["n_shots"]))
    print("[437r1] PORT   : hp %s -> %s (delta=%s)"
          % (out["hp_before"], out["hp_after"], out["hp_delta"]))
    for v, pr in (blob.get("predictions") or {}).items():
        print("[437r1] aiPredict[%s] : %s" % (v, json.dumps(pr)[:1200]))
    for i, s in enumerate(out["stages"]):
        print("[437r1] etage[%d] bornes_nc=%s bornes_cr=%s hits=%d cc=%s block=%s"
              % (i, s["bounds_nc"], s["bounds_cr"], s["hits"], s["crit_chance"],
                 s["block_sources"]))
        print("           rolls=%s per_hit=%s total=%s armor_dmg=%s block=%s"
              % (s["rolls"], s["per_hit"], s["total"], s["armor_dmg"], s["did_block"]))
        print("           limits=%s limits_hp=%s prevent_overkill=%s capped=%s"
              % (s["limits"], s["limits_hp"], s["prevent_overkill"], s["capped_reductions"]))
    for kind, d in (out.get("sub") or []):
        print("[437r1] sous-etage %-8s %s" % (kind, json.dumps(d)[:600]))
    for d in (out.get("draws") or []):
        print("[437r1] tirage lo=%d hi=%d out=%d r=%s" % (d["lo"], d["hi"], d["out"], d["raws"]))
    _solve(blob, out)


def _solve(blob, out):
    """INVERSION des bornes NATIVES : a `r` connu, `natif = lo + (r % width)`. On enumere les
    (lo, hi) plausibles autour des bornes du port et on garde ceux qui rendent EXACTEMENT le degat
    natif. Aucune inference : c'est une equation, pas une soustraction."""
    nat = int(blob["native"]["hp_delta"])
    ds = [d for d in (out.get("draws") or []) if d["hi"] - d["lo"] > 100]
    if not ds or not ds[0]["raws"]:
        print("[437r1] pas de tirage exploitable pour inverser les bornes")
        return
    r = ds[0]["raws"][-1]
    lo0, hi0 = ds[0]["lo"], ds[0]["hi"] - 1
    sols = [(lo, hi) for lo in range(lo0 - 4, lo0 + 5) for hi in range(hi0 - 4, hi0 + 5)
            if hi > lo and lo + (r % (hi - lo + 1)) == nat]
    print("[437r1] INVERSION : natif=%d r=%d ; port=(%d,%d) ; bornes natives possibles = %s"
          % (nat, r, lo0, hi0, sols))


# --------------------------------------------------------------------------- oracle BORNES


def _pick_tile_at_distance(board, dv, mover_id, ref_id, reach, want):
    """Tuile LIBRE atteignable en <= `reach` pas, dont la distance BFS a `ref_id` est la plus
    proche de `want` PAR LE HAUT (on ne descend jamais sous `want`)."""
    mv, rf = P._unit(dv, mover_id), P._unit(dv, ref_id)
    src = board.id_at(int(mv["pos"]["col"]), int(mv["pos"]["row"]))
    rft = board.id_at(int(rf["pos"]["col"]), int(rf["pos"]["row"]))
    occupied = {board.id_at(int(u["pos"]["col"]), int(u["pos"]["row"]))
                for u in (dv.get("units") or []) if u.get("pos") and u.get("alive")}
    d_src, d_ref = P._bfs(board, src), P._bfs(board, rft)
    cands = [t for t, d in d_src.items()
             if 0 < d <= int(reach) and t not in occupied and board.walkable(t)
             and d_ref.get(t, 10 ** 6) >= want]
    if not cands:
        return None
    return min(cands, key=lambda t: (d_ref.get(t, 10 ** 6), d_src[t]))


def bounds(seed=P.SEED, board=P.BOARD, dmg_target=None, rank=17, want_dist=3) -> dict:
    """ORACLE DES BORNES, sans passer par le tirage. C'est L'INVERSE du montage #437 : ici c'est
    l'OVERWATCHER qui MARCHE vers le porteur -- donc aucun tir ne part, l'armure Terminator reste
    ARMEE, et la prediction native (`aiPredict` = `GetAllPredictions` -> `PredictAttack` ->
    `PredictAttackRaw`, LA MEME fonction native dont `AttackDamageOperation$$ExecuteHit` tire sa
    cellule, cf. #131) donne directement `min`/`max`.

    Les bornes separent les modeles ; une valeur tiree ne les separe pas (deux bornes distinctes
    peuvent rendre la meme cellule). `dmg_target` (`rl_duel --dmg-target`) DEPLACE la base d'attaque
    de l'overwatcher : c'est le levier qui fabrique des cas DISCRIMINANTS.
    """
    import uuid as _uuid
    import subprocess as _sp
    from engine.entities.pathfinding.board import Board

    sf = ROOT / "logs" / "runners" / ("p437r1b-%s.json" % _uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
           "--board", board, "--rank", str(rank),
           "--p-units", "%s,%s" % (P.CARRIER, P.SPECTATOR), "--a-units", P.OVERWATCHER,
           "--hp-player", "400000", "--crit", "0,0", "--crit-target", "0,0",
           "--block-target", "0,0", "--block-player", "0,0", "--no-ai"]
    if dmg_target is not None:
        cmd += ["--dmg-target", str(dmg_target)]
    proc = _sp.run(cmd, cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                   errors="replace")
    if not sf.exists():
        return {"error": "build KO : %s" % (proc.stderr or proc.stdout or "")[-600:]}
    rid = int(json.loads(sf.read_text())["runnerId"])
    rpc = _mkrpc()
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="native_sym")
        dv = P._view(rpc, rid, inactive=True)
        ids = {v: int(P._by_vis(dv, v)["id"]) for v in [P.CARRIER, P.SPECTATOR, P.OVERWATCHER]}
        # Le porteur NE BOUGE PAS ; on cede la main et on fait AVANCER l'overwatcher.
        for _t in range(24):
            dv = P._view(rpc, rid, inactive=True)
            cur = dv.get("currentPlayer")
            ow_u, mv_u = P._unit(dv, ids[P.OVERWATCHER]), P._unit(dv, ids[P.CARRIER])
            src = brd.id_at(int(ow_u["pos"]["col"]), int(ow_u["pos"]["row"]))
            dst = brd.id_at(int(mv_u["pos"]["col"]), int(mv_u["pos"]["row"]))
            d = P._bfs(brd, src).get(dst)
            if d is not None and d == want_dist:
                break
            # tour de l'overwatcher ? on tente son move ; sinon on clot le tour courant.
            # ⚠ On vise la distance `want_dist` EXACTEMENT, pas « le plus pres possible » : a
            # distance 1 le natif selectionne l'arme de MELEE et `HeavyWeapon_ExtraDmg` (bonus
            # RANGED) ne mord plus -- le regime a deux faces disparait sans erreur (mesure : bornes
            # [904, 1356], face attaquant neutre, natif ET port d'accord pour rien).
            reach = P._mover_reach(dv, ids[P.OVERWATCHER])
            to_tile = _pick_tile_at_distance(brd, dv, ids[P.OVERWATCHER], ids[P.CARRIER],
                                             reach, want_dist)
            moved = False
            if to_tile is not None:
                col, row = brd.coord(to_tile)
                try:
                    rpc("applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": ids[P.OVERWATCHER],
                        "to": {"col": int(col), "row": int(row)}}}, 120)
                    moved = True
                except Exception:
                    moved = False
            if not moved:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
                d3 = P._view(rpc, rid)
                if d3.get("currentPlayer") == cur:
                    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        else:
            return {"error": "l'overwatcher n'a pas atteint la portee en 24 tours"}
        # REPOS : `HeavyWeapon_ExtraDmg` (+25%, la face ATTAQUANT du regime a deux faces) est
        # RETIRE des que le porteur a bouge, et re-pose au debut de son tour suivant. On cede donc
        # la main jusqu'a le revoir : sans lui, la face attaquant est neutre et le regime
        # discriminant n'existe pas (c'est ce que rendait la 1re version, bornes [904, 1356]).
        for _r in range(6):
            dv = P._view(rpc, rid, inactive=True)
            effs = [e.get("name") for e in ((P._unit(dv, ids[P.OVERWATCHER]) or {}).get("effects")
                                            or [])]
            if "HeavyWeapon_ExtraDmg" in effs:
                break
            cur = dv.get("currentPlayer")
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
            if P._view(rpc, rid).get("currentPlayer") == cur:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        dv = P._view(rpc, rid, inactive=True)
        ow_effs = [e.get("name") for e in ((P._unit(dv, ids[P.OVERWATCHER]) or {}).get("effects")
                                           or [])]
        if "HeavyWeapon_ExtraDmg" not in ow_effs:
            return {"error": "face ATTAQUANT neutre (HeavyWeapon_ExtraDmg absent : %s) -- le "
                             "regime a DEUX faces n'est pas realise" % ow_effs}
        pres, act = P._armour_state(dv, ids[P.CARRIER])
        if not (pres and act is True):
            return {"error": "armure Terminator non ARMEE au moment de la lecture (present=%s "
                             "active=%s) : la prediction ne porterait pas le regime" % (pres, act)}
        pr = rpc("aiPredict", {"runnerId": rid, "unitId": ids[P.OVERWATCHER],
                               "targetId": ids[P.CARRIER], "fresh": True}, 90)
        pb = None
        try:
            pb = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": ids[P.OVERWATCHER],
                                           "targetId": ids[P.CARRIER], "abilityType": 69}, 90)
        except Exception as exc:
            pb = {"error": "%s" % exc}
        cap = {"dec": P._view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
               "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
               "rng": rpc("dumpRng", {"runnerId": rid}, 30)}
        return {"ids": ids, "tiles": bg["tiles"], "cap": cap, "aiPredict": pr,
                "aiPlaybookPredict": pb, "dmg_target": dmg_target, "seed": str(seed),
                "board_id": board}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def port_bounds(blob: dict) -> dict:
    """Les bornes que le PORT calcule pour ce meme coup, via le foyer REEL
    (`AttackDamageOperation.execute` intercepte a `_run_hits`) -- pas une reimplementation."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.operations.damage import AttackDamageOperation

    brd = Board(blob["tiles"], adjacency="native_sym")
    cap = blob["cap"]
    st = load_state(cap["dec"], cap["ob"], cap["snap"], board=brd)
    rng = IntBasedMersenneTwister()
    rng.mt = list(cap["rng"]["mt"])
    rng.mti = cap["rng"]["mti"]
    st.rng = rng
    seen = {}
    orig = AttackDamageOperation._run_hits

    def _spy(rng_, hit_nc, hit_cr, crit_chance, crit_enabled, hits, block_sources, **kw):
        seen.setdefault("nc", [int(hit_nc.min), int(hit_nc.max)])
        seen.setdefault("hits", int(hits))
        raise _Stop()

    class _Stop(Exception):
        pass

    AttackDamageOperation._run_hits = staticmethod(_spy)
    try:
        AttackDamageOperation.execute(st, int(blob["ids"][P.OVERWATCHER]),
                                      int(blob["ids"][P.CARRIER]), is_overwatch=True)
    except _Stop:
        pass
    finally:
        AttackDamageOperation._run_hits = staticmethod(orig)
    return seen


# ------------------------------------------------------ PREDICTION dans le regime DEUX FACES


def predict_two_faces(seed=P.SEED, board=P.BOARD, dmg_target=None, rank=17, want_dist=3,
                      max_turns=30) -> dict:
    """LE discriminant : le **MEME couple de faces** que la mesure COMBAT de #437-r1
    (`HeavyWeapon_ExtraDmg` x1.25 cote ATTAQUANT, `TerminatorArmour_ReduceDmg` x0.25 cote
    DEFENSEUR), lu par la voie **PREDICTION** (`aiPredict` / `aiPlaybookPredict`).

    Ce que ce montage seul peut trancher : la lecture VECTEUR (le COMBAT ferait deux appels
    `ApplyCappedModifiers`, la PREDICTION une chaine unique) predit ici (1129, 1694) ; toute
    lecture non-vectorielle predit les MEMES bornes que le combat, (1130, 1695).

    ⚠ Pourquoi `--bounds` ne peut PAS servir a ca (piege MESURE le 2026-08-04) : il fait
    MARCHER l'overwatcher pour l'amener a portee, ce qui arme le flag `Moved`. Or
    `IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier` porte
    le gate `!HasFlag(Moved)` -- l'EFFET reste pose (la garde `HeavyWeapon_ExtraDmg in effects`
    passe) mais son bonus ne mord plus. Mesure : bornes natives ET port = (904, 1356), c.-a-d.
    `Round(P x 0.25)` -- face attaquant NEUTRE, regime a UNE face. La garde par presence de
    l'effet est donc INSUFFISANTE ; celle qui vaut est la valeur du bonus construit.

    Le montage ici ne fait donc JAMAIS bouger l'attaquant. C'est le SPECTATEUR qui purge le tir
    d'overwatch (il encaisse a la place du porteur, dont l'armure Terminator reste ARMEE), puis
    le PORTEUR avance d'un cran. Repete jusqu'a ce que la prediction native devienne lisible
    (`pred` non nul = la cible est dans le dictionnaire de `GetAllPredictions`).
    """
    import uuid as _uuid
    import subprocess as _sp
    from engine.entities.pathfinding.board import Board

    sf = ROOT / "logs" / "runners" / ("p437r1p2f-%s.json" % _uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
           "--board", board, "--rank", str(rank),
           "--p-units", "%s,%s" % (P.CARRIER, P.SPECTATOR), "--a-units", P.OVERWATCHER,
           "--hp-player", "400000", "--crit", "0,0", "--crit-target", "0,0",
           "--block-target", "0,0", "--block-player", "0,0", "--no-ai"]
    if dmg_target is not None:
        cmd += ["--dmg-target", str(dmg_target)]
    proc = _sp.run(cmd, cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                   errors="replace")
    if not sf.exists():
        return {"error": "build KO : %s" % (proc.stderr or proc.stdout or "")[-600:]}
    rid = int(json.loads(sf.read_text())["runnerId"])
    rpc = _mkrpc()
    trace = []
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="native_sym")
        dv = P._view(rpc, rid, inactive=True)
        ids = {v: int(P._by_vis(dv, v)["id"]) for v in [P.CARRIER, P.SPECTATOR, P.OVERWATCHER]}
        pr = None
        for _t in range(max_turns):
            dv = P._view(rpc, rid, inactive=True)
            ow_effs = [e.get("name") for e in ((P._unit(dv, ids[P.OVERWATCHER]) or {}).get("effects")
                                               or [])]
            pres, act = P._armour_state(dv, ids[P.CARRIER])
            ow_u = P._unit(dv, ids[P.OVERWATCHER])
            src = brd.id_at(int(ow_u["pos"]["col"]), int(ow_u["pos"]["row"]))
            d_from_ow = P._bfs(brd, src)
            car_u = P._unit(dv, ids[P.CARRIER])
            car_t = brd.id_at(int(car_u["pos"]["col"]), int(car_u["pos"]["row"]))
            d_car = d_from_ow.get(car_t)
            trace.append({"t": _t, "d_car": d_car, "ow_effs": ow_effs,
                          "armour": [pres, act]})
            if ("HeavyWeapon_ExtraDmg" in ow_effs) and pres and act is True:
                pr = rpc("aiPredict", {"runnerId": rid, "unitId": ids[P.OVERWATCHER],
                                       "targetId": ids[P.CARRIER], "fresh": True}, 90)
                if (pr or {}).get("pred"):
                    break
                pr = None
            cur = dv.get("currentPlayer")
            acted = False
            # 1) l'overwatch est ARME -> le SPECTATEUR va le declencher a la place du porteur.
            if P.OVERWATCH_EFFECT in [e.get("effectType") for e in
                                      ((P._unit(dv, ids[P.OVERWATCHER]) or {}).get("effects") or [])]:
                reach = P._mover_reach(dv, ids[P.SPECTATOR])
                to_tile, _d = P._pick_move_tile(brd, dv, ids[P.SPECTATOR], ids[P.OVERWATCHER], reach)
                if to_tile is not None:
                    col, row = brd.coord(to_tile)
                    try:
                        rpc("applyAction", {"runnerId": rid, "action": {
                            "kind": "move", "unitId": ids[P.SPECTATOR],
                            "to": {"col": int(col), "row": int(row)}}}, 120)
                        acted = True
                    except Exception:
                        acted = False
            # 2) puis le PORTEUR se rapproche d'un cran (l'overwatch vient d'etre consomme).
            dv2 = P._view(rpc, rid, inactive=True)
            still_armed = P.OVERWATCH_EFFECT in [
                e.get("effectType") for e in
                ((P._unit(dv2, ids[P.OVERWATCHER]) or {}).get("effects") or [])]
            if not still_armed:
                reach = P._mover_reach(dv2, ids[P.CARRIER])
                to_tile = _pick_tile_at_distance(brd, dv2, ids[P.CARRIER], ids[P.OVERWATCHER],
                                                 reach, want_dist)
                if to_tile is not None:
                    col, row = brd.coord(to_tile)
                    try:
                        rpc("applyAction", {"runnerId": rid, "action": {
                            "kind": "move", "unitId": ids[P.CARRIER],
                            "to": {"col": int(col), "row": int(row)}}}, 120)
                        acted = True
                    except Exception:
                        acted = False
            if not acted:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
                if P._view(rpc, rid).get("currentPlayer") == cur:
                    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
            else:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
                if P._view(rpc, rid).get("currentPlayer") == cur:
                    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        if pr is None:
            return {"error": "prediction non lisible dans le regime DEUX FACES en %d tours"
                             % max_turns, "trace": trace}
        pb = None
        try:
            pb = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": ids[P.OVERWATCHER],
                                           "targetId": ids[P.CARRIER], "abilityType": 69}, 90)
        except Exception as exc:
            pb = {"error": "%s" % exc}
        cap = {"dec": P._view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
               "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
               "rng": rpc("dumpRng", {"runnerId": rid}, 30)}
        return {"ids": ids, "tiles": bg["tiles"], "cap": cap, "aiPredict": pr,
                "aiPlaybookPredict": pb, "dmg_target": dmg_target, "seed": str(seed),
                "board_id": board, "trace": trace}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def stage_inputs(blob: dict) -> dict:
    """Les ENTREES d'etage que le port construit pour ce coup (bornes brutes, %-listes par face,
    percage, armure), lues PAR INSTRUMENTATION du foyer reel -- jamais recalculees a la main."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.operations.damage import AttackDamageOperation
    import engine.runner.operations.damage_ops.normal as _nm

    brd = Board(blob["tiles"], adjacency="native_sym")
    cap = blob["cap"]
    st = load_state(cap["dec"], cap["ob"], cap["snap"], board=brd)
    rng = IntBasedMersenneTwister()
    rng.mt = list(cap["rng"]["mt"])
    rng.mti = cap["rng"]["mti"]
    st.rng = rng
    got = {}
    g_base, g_pierce = _nm.get_base_damage_fix64, _nm.apply_pierce_and_modifiers
    orig = AttackDamageOperation._run_hits

    class _Stop(Exception):
        pass

    def w_base(*a, **k):
        r = g_base(*a, **k)
        got.setdefault("base", [int(r.min), int(r.max)])
        return r

    def w_pierce(value, pierce_pct=100, armor=0, mods=None, **k):
        got.setdefault("pierce", int(pierce_pct))
        got.setdefault("armor", int(armor))
        got.setdefault("pct_att", [list(x) for x in (mods.pct_list if mods else [])])
        got.setdefault("pct_def", [list(x) for x in (mods.pct_list_defender if mods else [])])
        got.setdefault("mult_att", float(mods.multiplicative) if mods else 1.0)
        got.setdefault("mult_def", float(mods.multiplicative_defender) if mods else 1.0)
        got.setdefault("kw", {kk: str(vv) for kk, vv in k.items()})
        return g_pierce(value, pierce_pct, armor, mods, **k)

    def _spy(rng_, hit_nc, hit_cr, cc, ce, hits, block_sources, **k):
        got["port_bounds"] = [int(hit_nc.min), int(hit_nc.max)]
        raise _Stop()

    _nm.get_base_damage_fix64, _nm.apply_pierce_and_modifiers = w_base, w_pierce
    AttackDamageOperation._run_hits = staticmethod(_spy)
    try:
        AttackDamageOperation.execute(st, int(blob["ids"][P.OVERWATCHER]),
                                      int(blob["ids"][P.CARRIER]))
    except _Stop:
        pass
    finally:
        AttackDamageOperation._run_hits = staticmethod(orig)
        _nm.get_base_damage_fix64, _nm.apply_pierce_and_modifiers = g_base, g_pierce
    return got


def face_models(stage: dict) -> dict:
    """Les DEUX modeles en presence, evalues sur les entrees d'etage MESUREES.
    `chaine_unique` = un seul `Fix64.Round` pour les deux faces ; `deux_appels` = un `Round` par
    face (ce que rend `ApplyCappedModifiers` appele deux fois)."""
    from engine.services import fix64 as _fx
    from engine.services.damage_prediction import get_damage_with_piercing

    def chain(v0, groups):
        v = _fx.from_number(v0)
        for g in groups:
            for m, _c in g:
                v = _fx.mul(v, _fx.mult_raw_from_float(m))
            v = _fx.round_raw(v, 1)
        return _fx.to_int(v)

    att = [tuple(x) for x in stage.get("pct_att") or []]
    deff = [tuple(x) for x in stage.get("pct_def") or []]
    out = {}
    for name, b in (("min", 0), ("max", 1)):
        p = get_damage_with_piercing(int((stage["base"])[b]), int(stage["pierce"]),
                                     int(stage["armor"]))
        out["chaine_unique_" + name] = chain(p, [att + deff])
        out["deux_appels_" + name] = chain(p, [att, deff])
    return out


# --------------------------------------------------------------------------- elevation en COMBAT


def elev_combat(seed=P.SEED, board=P.BOARD, dmg_target=None, rank=17) -> dict:
    """LE discriminant qui reste : face ATTAQUANT = **ELEVATION** (feuille positionnelle) et face
    DEFENSEUR = **EFFET** (`TerminatorArmour`), mesures AU COMBAT (degat reel + inversion des
    bornes), pas en prediction.

    Pourquoi il faut celui-la : #462-r4a a mesure ce meme couple de faces EN PREDICTION
    (`aiPlaybookPredict`) et obtenu `Round(P x 1.5 x 0.7)` -- une CHAINE UNIQUE. Le present cas
    #437-r1 mesure, EN COMBAT, `Round(Round(P x 1.25) x 0.25)` -- DEUX arrondis. Deux lectures
    restent alors possibles, et elles ne different QUE sur ce montage :
      (a) la loi tient a la NATURE de la source ATTAQUANT (effet -> arrondi, positionnel -> non) ;
      (b) la loi tient au VECTEUR (combat -> deux appels, prediction -> chaine).
    Ici la source attaquante est POSITIONNELLE et le vecteur est le COMBAT : (a) predit la chaine,
    (b) predit deux arrondis.

    Le ranger MARCHE (donc il perd `HeavyWeapon_ExtraDmg`, ce qui est ce qu'on veut : la face
    attaquant ne doit porter QUE l'elevation) vers une tuile STRICTEMENT plus haute que celle du
    porteur, puis ATTAQUE."""
    import uuid as _uuid
    import subprocess as _sp
    from engine.entities.pathfinding.board import Board

    sf = ROOT / "logs" / "runners" / ("p437r1e-%s.json" % _uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
           "--board", board, "--rank", str(rank),
           "--p-units", "%s,%s" % (P.CARRIER, P.SPECTATOR), "--a-units", P.OVERWATCHER,
           "--hp-player", "400000", "--crit", "0,0", "--crit-target", "0,0",
           "--block-target", "0,0", "--block-player", "0,0", "--no-ai"]
    if dmg_target is not None:
        cmd += ["--dmg-target", str(dmg_target)]
    proc = _sp.run(cmd, cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                   errors="replace")
    if not sf.exists():
        return {"error": "build KO : %s" % (proc.stderr or proc.stdout or "")[-600:]}
    rid = int(json.loads(sf.read_text())["runnerId"])
    rpc = _mkrpc()
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="native_sym")
        elev = {}
        for t in bg["tiles"]:
            tid = t.get("id", t.get("tileId"))
            if tid is not None:
                elev[int(tid)] = t.get("elevation")
        dv = P._view(rpc, rid, inactive=True)
        ids = {v: int(P._by_vis(dv, v)["id"]) for v in [P.CARRIER, P.SPECTATOR, P.OVERWATCHER]}
        tgt_tile = brd.id_at(int(P._unit(dv, ids[P.CARRIER])["pos"]["col"]),
                             int(P._unit(dv, ids[P.CARRIER])["pos"]["row"]))
        e_tgt = elev.get(tgt_tile)
        for _t in range(30):
            dv = P._view(rpc, rid, inactive=True)
            ow_u = P._unit(dv, ids[P.OVERWATCHER])
            src = brd.id_at(int(ow_u["pos"]["col"]), int(ow_u["pos"]["row"]))
            d = P._bfs(brd, src).get(tgt_tile)
            if (d is not None and 2 <= d <= 3 and e_tgt is not None
                    and (elev.get(src) or 0) > e_tgt):
                break
            reach = P._mover_reach(dv, ids[P.OVERWATCHER])
            occupied = {brd.id_at(int(u["pos"]["col"]), int(u["pos"]["row"]))
                        for u in (dv.get("units") or []) if u.get("pos") and u.get("alive")}
            d_src, d_tgt = P._bfs(brd, src), P._bfs(brd, tgt_tile)
            cands = [t for t, dd in d_src.items()
                     if 0 < dd <= int(reach) and t not in occupied and brd.walkable(t)
                     and 2 <= d_tgt.get(t, 10 ** 6) <= 3
                     and e_tgt is not None and (elev.get(t) or 0) > e_tgt]
            cur = dv.get("currentPlayer")
            if cands:
                col, row = brd.coord(min(cands, key=lambda t: d_src[t]))
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": ids[P.OVERWATCHER],
                    "to": {"col": int(col), "row": int(row)}}}, 120)
                continue
            # pas de tuile surplombante a portee -> on se rapproche puis on retente
            to_tile = _pick_tile_at_distance(brd, dv, ids[P.OVERWATCHER], ids[P.CARRIER], reach, 2)
            moved = False
            if to_tile is not None:
                col, row = brd.coord(to_tile)
                try:
                    rpc("applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": ids[P.OVERWATCHER],
                        "to": {"col": int(col), "row": int(row)}}}, 120)
                    moved = True
                except Exception:
                    moved = False
            if not moved:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
                if P._view(rpc, rid).get("currentPlayer") == cur:
                    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        else:
            return {"error": "aucune tuile SURPLOMBANTE a portee en 30 tours"}
        dv = P._view(rpc, rid, inactive=True)
        pres, act = P._armour_state(dv, ids[P.CARRIER])
        if not (pres and act is True):
            return {"error": "armure Terminator non ARMEE (present=%s active=%s)" % (pres, act)}
        ow_effs = [e.get("name") for e in ((P._unit(dv, ids[P.OVERWATCHER]) or {}).get("effects")
                                           or [])]
        if "HeavyWeapon_ExtraDmg" in ow_effs:
            return {"error": "HeavyWeapon_ExtraDmg ENCORE actif (%s) : la face attaquant porterait "
                             "DEUX sources et le montage ne discriminerait plus" % ow_effs}
        cap = {"dec": P._view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
               "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
               "rng": rpc("dumpRng", {"runnerId": rid}, 30)}
        hp0 = P._hp(dv, ids[P.CARRIER])
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": ids[P.OVERWATCHER], "targetId": ids[P.CARRIER],
            "abilityType": 69}}, 120)
        dv2 = P._view(rpc, rid, inactive=True)
        hp1 = P._hp(dv2, ids[P.CARRIER])
        return {"ids": ids, "tiles": bg["tiles"], "cap": cap,
                "native": {"hp_before": hp0, "hp_after": hp1, "hp_delta": (hp0 - hp1)},
                "attack": {"caster": ids[P.OVERWATCHER], "target": ids[P.CARRIER]},
                "dmg_target": dmg_target, "board_id": board, "seed": str(seed)}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def replay_attack(blob: dict) -> dict:
    """Rejeu OFFLINE de l'ATTAQUE capturee (pas d'un move) : bornes du port + alea BRUT du tirage."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.operations.damage import AttackDamageOperation

    brd = Board(blob["tiles"], adjacency="native_sym")
    cap = blob["cap"]
    st = load_state(cap["dec"], cap["ob"], cap["snap"], board=brd)
    rng = IntBasedMersenneTwister()
    rng.mt = list(cap["rng"]["mt"])
    rng.mti = cap["rng"]["mti"]
    st.rng = rng
    seen, raws, draws = {}, [], []
    _g_gr, _g_ni = type(rng).genrand_int32, type(rng).next_internal
    orig = AttackDamageOperation._run_hits

    def _spy_gr(self):
        g = _g_gr(self)
        raws.append(int(g))
        return g

    def _spy_ni(self, lo, hi):
        n0 = len(raws)
        out = _g_ni(self, lo, hi)
        draws.append({"lo": int(lo), "hi": int(hi), "out": int(out),
                      "raws": [x >> 1 for x in raws[n0:]]})
        return out

    def _spy(rng_, hit_nc, hit_cr, cc, ce, hits, block_sources, **kw):
        seen.setdefault("bounds", (int(hit_nc.min), int(hit_nc.max)))
        seen.setdefault("hits", int(hits))
        return orig(rng_, hit_nc, hit_cr, cc, ce, hits, block_sources, **kw)

    type(rng).genrand_int32, type(rng).next_internal = _spy_gr, _spy_ni
    AttackDamageOperation._run_hits = staticmethod(_spy)
    try:
        res = AttackDamageOperation.execute(st, int(blob["attack"]["caster"]),
                                            int(blob["attack"]["target"]))
    finally:
        AttackDamageOperation._run_hits = staticmethod(orig)
        type(rng).genrand_int32, type(rng).next_internal = _g_gr, _g_ni
    big = [d for d in draws if d["hi"] - d["lo"] > 100]
    return {"bounds": seen.get("bounds"), "hits": seen.get("hits"),
            "total": (res or {}).get("total"),
            "r": (big[0]["raws"][-1] if big and big[0]["raws"] else None)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--elev-combat", action="store_true",
                    help="regime ELEVATION (att, positionnel) + EFFET (def), mesure AU COMBAT")
    ap.add_argument("--bounds", action="store_true",
                    help="oracle des BORNES natives (l'overwatcher marche vers le porteur)")
    ap.add_argument("--dmg-target", default=None,
                    help="force le stat Damage de l'overwatcher (deplace la fraction)")
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--overwatchers", default=P.OVERWATCHER)
    ap.add_argument("--capture-file", default=str(CAPTURE))
    a = ap.parse_args()
    cf = Path(a.capture_file)
    if a.elev_combat:
        b = elev_combat(dmg_target=a.dmg_target)
        if "error" in b:
            print("[437r1] ERREUR elev-combat : %s" % b["error"])
            return 2
        out = ROOT / "logs" / ("probe_437r1_elev_%s.json" % (a.dmg_target or "base"))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(b), encoding="utf-8")
        pr = replay_attack(b)
        print("[437r1] ELEV-COMBAT natif=%s port=%s bornes_port=%s r=%s"
              % (b["native"]["hp_delta"], pr["total"], pr["bounds"], pr["r"]))
        nat, r, (lo0, hi0) = int(b["native"]["hp_delta"]), pr["r"], pr["bounds"]
        sols = [(lo, hi) for lo in range(lo0 - 4, lo0 + 5) for hi in range(hi0 - 4, hi0 + 5)
                if hi > lo and lo + (r % (hi - lo + 1)) == nat]
        print("[437r1] INVERSION : bornes natives possibles = %s" % sols)
        print("[437r1] ecrit : %s" % out)
        return 0
    if a.bounds:
        b = bounds(dmg_target=a.dmg_target)
        if "error" in b:
            print("[437r1] ERREUR bounds : %s" % b["error"])
            return 2
        pbnd = port_bounds(b)
        out = ROOT / "logs" / ("probe_437r1_bounds_%s.json" % (a.dmg_target or "base"))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"blob": b, "port": pbnd}), encoding="utf-8")
        print("[437r1] dmg_target=%s" % a.dmg_target)
        print("[437r1] aiPredict         : %s" % json.dumps(b["aiPredict"])[:900])
        print("[437r1] aiPlaybookPredict : %s" % json.dumps(b["aiPlaybookPredict"])[:900])
        print("[437r1] PORT bornes       : %s" % pbnd)
        print("[437r1] ecrit : %s" % out)
        return 0
    if a.capture:
        ows = [x.strip() for x in a.overwatchers.split(",") if x.strip()]
        blob = capture(overwatchers=ows, out=cf, dmg_target=a.dmg_target)
        if "error" in blob:
            print("[437r1] ERREUR capture : %s" % blob["error"])
            return 2
        return 0
    if not cf.exists():
        print("[437r1] pas de capture : lancer --capture d'abord (%s)" % cf)
        return 2
    blob = json.loads(cf.read_text(encoding="utf-8"))
    out = replay(blob, mutate=a.mutate)
    _report(blob, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
