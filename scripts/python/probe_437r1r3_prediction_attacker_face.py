"""#437-r1-r1-r3 -- pourquoi le `x1.25` (face ATTAQUANT) n'entre pas dans `aiPredict`.

Le residu herite dit : sur les memes entrees d'etage, le COMBAT rend (1130, 1695) et `aiPredict`
rend (904, 1356) = `Round(P x 0.25)` -- face attaquant absente. DEUX lectures possibles, et une
seule mesure les separe :

  * MONTAGE  -- dans l'etat lu, la face attaquant est NEUTRE (une condition du trigger DSL de
    `IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier` est
    fausse), ou bien `aiPredict` ne predit PAS le coup qu'on croit. Pas de divergence de modele.
  * REELLE   -- la face est vivante et seule la voie PREDICTION l'ignore.

CE QUE CE PROBE AJOUTE, et qui manquait : la garde `la cible est-elle attaquable DEPUIS LA TUILE
COURANTE`. Le RPC `aiPredict` porte un piege DOCUMENTE dans sa propre docstring
(`frida/hooks/features/ai-step/rpc-predict.ts`, piege 3) : quand la cible n'est pas atteignable
depuis la tuile de selection, le natif sert le FALLBACK
`GetPredictionForTargetsUnreachableFromSelectionTile` -- une prediction depuis une AUTRE tuile,
donc APRES un deplacement. Or la face attaquant est precisement gatee `!HasFlag(Moved)`.
Une lecture d'`aiPredict` hors portee ne mesure donc PAS le coup qu'on croit mesurer.

Le montage `--predict-2faces` de `probe_437r1_overwatch_offbyone.py` s'arretait des que
`pred` etait non nul -- ce qui arrive AUSSI hors portee. Idem `capture()` : son `aiPredict` est
lu juste AVANT le pas declencheur, donc NECESSAIREMENT hors portee de tir (sinon l'overwatch
aurait deja tire).

Montage ici : l'attaquant NE BOUGE JAMAIS. Le SPECTATEUR purge le tir d'overwatch (le porteur
garde son armure), puis le PORTEUR avance d'un cran. A chaque tour de l'equipe de l'attaquant on
lit, DANS LE MEME ETAT :
  * `abilityTargets(ow, 69).fromHere`  -- la cible est-elle castable SANS bouger ;
  * `aiPredict(ow -> cible, fresh)`    -- les bornes de la voie PREDICTION.
On s'arrete au PREMIER etat ou la cible est dans `fromHere` (donc a la portee de tir, sans
deplacement) avec `HeavyWeapon_ExtraDmg` pose et l'armure Terminator ARMEE.

Puis (`--shot`) on laisse partir le tir d'overwatch depuis CET etat et on INVERSE les bornes du
COMBAT depuis le `dumpRng` capture -- la comparaison prediction / combat est alors faite sur le
meme attaquant, a la meme tuile, au meme tour.

ASCII only (cp1252). Discipline runner : state-file ABSOLU sous `logs/`, `--board` explicite,
dispose en sortie.

CLI (depuis scripts/python) :
  python probe_437r1r3_prediction_attacker_face.py            # sweep + arret en portee
  python probe_437r1r3_prediction_attacker_face.py --shot     # + tir reel et inversion
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import probe_437_overwatch_consumes_armour as P            # noqa: E402
import probe_437r1_overwatch_offbyone as R1                # noqa: E402
from probe_r6_round_materialize import _mkrpc              # noqa: E402

NORMAL_ATTACK = 69          # `Loki_NormalAttack` -- l'ability concrete de l'attaque normale
STOP_AT = 2                 # distance visee : jamais 1 (a 1 le natif prend l'arme de MELEE, et le
                            # bonus RANGED `HeavyWeapon_ExtraDmg` ne mord plus -- mesure #437-r1-r1)


def _approach(rpc, rid, brd, ids, view, want):
    """Rapproche le PORTEUR de l'attaquant jusqu'a la distance BFS `want` (jamais en dessous)."""
    reach = P._mover_reach(view, ids[P.CARRIER])
    to_tile = R1._pick_tile_at_distance(brd, view, ids[P.CARRIER], ids[P.OVERWATCHER],
                                        reach, int(want))
    if to_tile is None:
        return False
    col, row = brd.coord(to_tile)
    try:
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": ids[P.CARRIER],
            "to": {"col": int(col), "row": int(row)}}}, 120)
        return True
    except Exception:
        return False


def _build(seed, board, rank, dmg_target, state_file=None):
    import subprocess as _sp
    sf = Path(state_file) if state_file else (
        ROOT / "logs" / "runners" / ("p437r1r3-%s.json" % uuid.uuid4().hex[:8]))
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
        return None, (proc.stderr or proc.stdout or "")[-800:]
    return int(json.loads(sf.read_text())["runnerId"]), None


def _from_here_ids(at_blob, unit_id, ability):
    """Les `targetId` castables SANS bouger pour (unit, ability), lus de `abilityTargets`.
    Champs natifs du RPC : `units[].unitId`, `abilities[].abilityId`, `abilities[].fromHere[]`."""
    out = []
    for u in ((at_blob or {}).get("units") or []):
        if int(u.get("unitId", -1)) != int(unit_id):
            continue
        for ab in (u.get("abilities") or []):
            if int(ab.get("abilityId", -1)) != int(ability):
                continue
            for t in (ab.get("fromHere") or []):
                if t.get("targetId") is not None:
                    out.append(int(t["targetId"]))
    return out


def _pred_bounds(pr):
    p = (pr or {}).get("pred") or {}
    lo, hi = p.get("healthDmgMin"), p.get("healthDmgMax")
    return None if lo is None else [int(lo), int(hi)]


def sweep(seed=P.SEED, board=P.BOARD, dmg_target=None, rank=17, max_turns=40,
          shot=False, state_file=None) -> dict:
    from engine.entities.pathfinding.board import Board

    rid, err = _build(seed, board, rank, dmg_target, state_file)
    if rid is None:
        return {"error": "build KO : %s" % err}
    rpc = _mkrpc()
    steps = []
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="native_sym")
        dv = P._view(rpc, rid, inactive=True)
        ids = {v: int(P._by_vis(dv, v)["id"])
               for v in [P.CARRIER, P.SPECTATOR, P.OVERWATCHER]}
        myplayer = (P._by_vis(dv, P.CARRIER) or {}).get("owner")
        owplayer = (P._by_vis(dv, P.OVERWATCHER) or {}).get("owner")
        hit = None

        def _dist(view):
            ow_u, car_u = P._unit(view, ids[P.OVERWATCHER]), P._unit(view, ids[P.CARRIER])
            if not ((ow_u or {}).get("pos") and (car_u or {}).get("pos")):
                return None
            src = brd.id_at(int(ow_u["pos"]["col"]), int(ow_u["pos"]["row"]))
            dst = brd.id_at(int(car_u["pos"]["col"]), int(car_u["pos"]["row"]))
            return P._bfs(brd, src).get(dst)

        def _armed(view):
            return P.OVERWATCH_EFFECT in [
                e.get("effectType") for e in
                ((P._unit(view, ids[P.OVERWATCHER]) or {}).get("effects") or [])]

        for _t in range(max_turns):
            dv = P._view(rpc, rid, inactive=True)
            cur = dv.get("currentPlayer")
            d_car = _dist(dv)
            ow_effs = [e.get("name") for e in
                       ((P._unit(dv, ids[P.OVERWATCHER]) or {}).get("effects") or [])]
            pres, act = P._armour_state(dv, ids[P.CARRIER])
            ow_pos = (P._unit(dv, ids[P.OVERWATCHER]) or {}).get("pos")
            car_pos = (P._unit(dv, ids[P.CARRIER]) or {}).get("pos")
            row = {"t": _t, "cur": cur, "d_car": d_car, "ow_effs": ow_effs,
                   "armour": [pres, act], "ow_pos": ow_pos, "car_pos": car_pos,
                   "ow_armed": _armed(dv)}
            if d_car is None:
                steps.append(row)
                return {"error": "unite sans position au tour %d" % _t, "steps": steps}
            # `abilityTargets` filtre sur `IsControlledByCurrentPlayer` : lisible SEULEMENT
            # pendant le tour de l'equipe de l'attaquant.
            if cur == owplayer:
                at = rpc("abilityTargets", {"runnerId": rid, "unitId": ids[P.OVERWATCHER],
                                            "abilityType": NORMAL_ATTACK,
                                            "allAbilities": False}, 120)
                fh = _from_here_ids(at, ids[P.OVERWATCHER], NORMAL_ATTACK)
                row["fromHere"] = fh
                row["inRange"] = ids[P.CARRIER] in fh
                pr = rpc("aiPredict", {"runnerId": rid, "unitId": ids[P.OVERWATCHER],
                                       "targetId": ids[P.CARRIER], "fresh": True}, 90)
                row["pred"] = _pred_bounds(pr)
                row["predTile"] = (pr or {}).get("tile")
                steps.append(row)
                if (row["inRange"] and "HeavyWeapon_ExtraDmg" in ow_effs
                        and pres and act is True):
                    hit = {"aiPredict": pr, "abilityTargets_fromHere": fh, "d_car": d_car,
                           "cap": {"dec": P._view(rpc, rid),
                                   "ob": rpc("observeBattle", {"runnerId": rid}, 60),
                                   "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
                                   "rng": rpc("dumpRng", {"runnerId": rid}, 30)}}
                    break
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
                continue
            steps.append(row)
            # tour de MON camp. L'ATTAQUANT ne bouge JAMAIS.
            #  * PHASE 1 (`d_car > STOP_AT`) : le PORTEUR avance jusqu'a `STOP_AT`. Il ENCAISSE
            #    le tir d'overwatch au passage -- c'est assume (PV 400000) : ce tir CONSOMME son
            #    armure Terminator et le tir d'overwatch de l'attaquant.
            #  * PHASE 2 (`d_car <= STOP_AT`) : plus AUCUN mouvement. On cede la main en boucle
            #    jusqu'a ce que les trois conditions soient RE-ARMEES au tour de l'attaquant
            #    (`HeavyWeapon_ExtraDmg` repose, armure Terminator active, overwatch arme).
            #    C'est le seul etat ou la prediction porte le regime DEUX FACES *sans* que
            #    personne n'ait bouge.
            if d_car > STOP_AT:
                _approach(rpc, rid, brd, ids, dv, max(STOP_AT, int(d_car) - 3))
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        if hit is None:
            return {"error": "aucun etat EN PORTEE (fromHere) atteint en %d tours" % max_turns,
                    "steps": steps, "ids": ids, "tiles": bg["tiles"]}
        out = {"ids": ids, "tiles": bg["tiles"], "steps": steps, "seed": str(seed),
               "board_id": board, "dmg_target": dmg_target, "myplayer": myplayer,
               "owplayer": owplayer}
        out.update(hit)
        if shot:
            out["shot"] = _fire(rpc, rid, brd, ids, out)
        return out
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def _fire(rpc, rid, brd, ids, blob) -> dict:
    """Depuis l'etat EN PORTEE deja capture, on cede la main et le PORTEUR fait UN pas qui ne le
    rapproche pas (distance conservee >= 2) : le tir d'overwatch part. Le delta de PV est le
    degat COMBAT natif du meme attaquant, a la meme tuile."""
    dv = P._view(rpc, rid, inactive=True)
    cur = dv.get("currentPlayer")
    myplayer = blob["myplayer"]
    for _ in range(4):
        if cur == myplayer:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        dv = P._view(rpc, rid, inactive=True)
        cur = dv.get("currentPlayer")
    if cur != myplayer:
        return {"error": "la main n'est pas revenue au camp du porteur"}
    ow_u, car_u = P._unit(dv, ids[P.OVERWATCHER]), P._unit(dv, ids[P.CARRIER])
    src = brd.id_at(int(ow_u["pos"]["col"]), int(ow_u["pos"]["row"]))
    d_now = P._bfs(brd, src).get(brd.id_at(int(car_u["pos"]["col"]), int(car_u["pos"]["row"])))
    hp0 = P._hp(dv, ids[P.CARRIER])
    ow_before = P._armour_state(dv, ids[P.OVERWATCHER], P.OVERWATCH_EFFECT)[1]
    reach = P._mover_reach(dv, ids[P.CARRIER])
    to_tile = R1._pick_tile_at_distance(brd, dv, ids[P.CARRIER], ids[P.OVERWATCHER],
                                        reach, max(2, int(d_now or 2)))
    if to_tile is None:
        return {"error": "aucune tuile de declenchement conservant la distance"}
    col, r0 = brd.coord(to_tile)
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": ids[P.CARRIER],
        "to": {"col": int(col), "row": int(r0)}}}, 120)
    dv2 = P._view(rpc, rid, inactive=True)
    hp1 = P._hp(dv2, ids[P.CARRIER])
    ow_after = P._armour_state(dv2, ids[P.OVERWATCHER], P.OVERWATCH_EFFECT)[1]
    car2 = P._unit(dv2, ids[P.CARRIER])
    d_after = P._bfs(brd, src).get(brd.id_at(int(car2["pos"]["col"]), int(car2["pos"]["row"])))
    return {"hp_before": hp0, "hp_after": hp1,
            "hp_delta": (None if (hp0 is None or hp1 is None) else hp0 - hp1),
            "ow_effect_before": ow_before, "ow_effect_after": ow_after,
            "d_before": d_now, "d_after": d_after, "moved_to": [int(col), int(r0)]}


def port_bounds(blob: dict) -> dict:
    """Les bornes que le PORT calcule pour CE tir depuis l'etat capture (foyer reel intercepte)."""
    return R1.port_bounds({"tiles": blob["tiles"], "cap": blob["cap"], "ids": blob["ids"]})


def replay_overwatch(blob: dict) -> dict:
    """Rejeu OFFLINE du TIR D'OVERWATCH depuis l'etat capture (`is_overwatch=True`, comme
    `R1.port_bounds`), en espionnant le PRNG : rend les bornes du port et l'alea BRUT `r` du
    tirage, seul inconnu de l'inversion."""
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
        seen.setdefault("bounds", [int(hit_nc.min), int(hit_nc.max)])
        seen.setdefault("hits", int(hits))
        return orig(rng_, hit_nc, hit_cr, cc, ce, hits, block_sources, **kw)

    type(rng).genrand_int32, type(rng).next_internal = _spy_gr, _spy_ni
    AttackDamageOperation._run_hits = staticmethod(_spy)
    try:
        res = AttackDamageOperation.execute(st, int(blob["ids"][P.OVERWATCHER]),
                                            int(blob["ids"][P.CARRIER]), is_overwatch=True)
    finally:
        AttackDamageOperation._run_hits = staticmethod(orig)
        type(rng).genrand_int32, type(rng).next_internal = _g_gr, _g_ni
    big = [d for d in draws if d["hi"] - d["lo"] > 100]
    return {"bounds": seen.get("bounds"), "hits": seen.get("hits"),
            "total": (res or {}).get("total"),
            "r": (big[0]["raws"][-1] if big and big[0]["raws"] else None)}


def invert(blob: dict) -> dict:
    """Bornes du COMBAT natif, INVERSEES depuis le `dumpRng` capture et le degat observe --
    `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal` rend
    `lo + ((genrand >> 1) % (hi + 1 - lo))`, donc `r` est connu et l'egalite s'enumere."""
    sh = blob.get("shot") or {}
    nat = sh.get("hp_delta")
    if nat is None:
        return {"error": "pas de tir"}
    pr = replay_overwatch(blob)
    r = pr["r"]
    if r is None or not pr.get("bounds"):
        return {"error": "rejeu offline sans tirage exploitable", "replay": pr}
    lo0, hi0 = pr["bounds"]
    sols = [(lo, hi) for lo in range(max(1, lo0 - 300), lo0 + 301)
            for hi in range(hi0 - 400, hi0 + 401)
            if hi > lo and lo + (r % (hi - lo + 1)) == int(nat)]
    return {"natif": int(nat), "r": r, "port_bounds": [lo0, hi0], "port_total": pr.get("total"),
            "solutions_proches": [list(s) for s in sols if abs(s[0] - lo0) <= 250][:40],
            "n_solutions": len(sols)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", action="store_true",
                    help="laisse partir le tir d'overwatch depuis l'etat EN PORTEE et inverse")
    ap.add_argument("--dmg-target", default=None)
    ap.add_argument("--max-turns", type=int, default=40)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    b = sweep(dmg_target=a.dmg_target, max_turns=a.max_turns, shot=a.shot,
              state_file=a.state_file)
    out = Path(a.out) if a.out else (ROOT / "logs" / ("probe_437r1r3_%s.json"
                                                      % (a.dmg_target or "base")))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(b), encoding="utf-8")
    print("[437r1r3] ecrit : %s" % out)
    for s in (b.get("steps") or []):
        print("[437r1r3] t=%s cur=%s d=%s armed=%s inRange=%s pred=%s effs=%s"
              % (s["t"], s["cur"], s["d_car"], s.get("ow_armed"), s.get("inRange"),
                 s.get("pred"), ",".join([e for e in (s["ow_effs"] or []) if e])))
    if "error" in b:
        print("[437r1r3] ERREUR : %s" % b["error"])
        return 2
    print("[437r1r3] EN PORTEE (fromHere) : d=%s  aiPredict=%s"
          % (b["d_car"], _pred_bounds(b["aiPredict"])))
    st = R1.stage_inputs({"tiles": b["tiles"], "cap": b["cap"], "ids": b["ids"]})
    print("[437r1r3] entrees d'etage PORT : %s" % json.dumps(st))
    if a.shot:
        print("[437r1r3] TIR : %s" % json.dumps(b.get("shot")))
        print("[437r1r3] INVERSION : %s" % json.dumps(invert(b)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
