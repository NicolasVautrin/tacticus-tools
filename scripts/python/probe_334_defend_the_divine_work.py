"""#334 -- MONTAGE + MESURE de la face COMBAT de `DefendTheDivineWork` (1117, `admecManipulus`).

Ce fichier porte LE MONTAGE (build isole, conduite des positions des deux camps, capture
`decisionView`/`observeBattle`/`combatSnapshot`/`boardGraph`/`dumpRng`, cast OFFLINE sur cette
capture avec le MEME `state.rng`, puis cast LIVE et comparaison). `tests/engine/runner/
test_defend_the_divine_work_live.py` n'en est que la porte pytest -- meme organisation que
`probe_psychic_aoe.py`.

CE QU'IL MESURE, etage par etage (le natif est un `ExecuteBehaviour` a DEUX Operations) :

  * etage 1 `ExecuteAtomic(Repair(...), 0x2a)` -- repare le CASTER **et** ses amis ADJACENTS, du
    meme `hpToRepair[level]`. Temoin NEGATIF dans le meme cast : un ami MECANIQUE identique, mais
    ELOIGNE a >= 3 hex, n'est PAS repare -> la garde d'adjacence discrimine reellement ;
  * etage 2 `Repair_GalvanicFieldAbility$$CreateAttackBehavior(dsl, Friends(AdjacentUnits))` -- ne
    fait attaquer QUE les amis adjacents mecaniques, **jamais le caster**. C'est le point verrouille
    au DESASSEMBLAGE : l'etage 1 fait `Friends(...) op_Addition Caster@0x48`, l'etage 2 passe
    `Friends(...)` DIRECTEMENT a `CreateAttackBehavior` (aucun `op_Addition` entre les deux `call`).

Scenarios (`--scenario`), tous montes en CONDUISANT les positions :

  `repair`  -- les deux camps restent loin : mesure PURE de l'etage 1 (aucune attaque ne peut
               partir, donc rien ne peut masquer un ecart de reparation) ;
  `attack`  -- l'ALLIE adjacent est amene au CONTACT d'un ennemi, le caster NON : un ennemi DOIT
               perdre des PV (l'etage 2 mord) ;
  `caster`  -- le CASTER est amene au CONTACT d'un ennemi, l'allie adjacent NON : AUCUN ennemi ne
               doit perdre de PV. La mesure `normal_targets` (mirror de `AttackQuery$$HasValidTargets`
               depuis la tuile courante) est la CONTRE-EPREUVE : elle etablit que le caster POUVAIT
               frapper -- sans elle, « zero degat » ne prouverait rien.

Re-derivation : `python probe_334_defend_the_divine_work.py --scenario repair`
ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
_ROOT = _PYDIR.parents[1]

CASTER_VIS = "admecManipulus"      # active 1117 + passif GalvanicField
ADJ_VIS = "admecRuststalker"       # allie MECANIQUE, amene au CONTACT du caster
FAR_VIS = "admecDestroyer"         # allie MECANIQUE laisse LOIN -> temoin negatif
ENEMY_VIS = ("orksWarboss", "orksKillaKan")
SEED = "777"
BOARD = "MC1_67"
ABILITY = 1117
FAR_MIN_DIST = 3                   # distance hex du temoin negatif au caster


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def build_args(damaged: int, advance: int) -> list[str]:
    """Arguments `rl_duel build` du montage (hors `--seed`/`--state-file`)."""
    stats = ";".join("%s:RemainingHealth=%d" % (v, damaged)
                     for v in (CASTER_VIS, ADJ_VIS, FAR_VIS))
    argv = ["--p-units", "%s,%s,%s" % (CASTER_VIS, ADJ_VIS, FAR_VIS),
            "--a-units", ",".join(ENEMY_VIS),
            "--board", BOARD,
            "--unit-stat", stats,
            "--advance", str(advance)]
    if advance:
        # RAPPROCHEMENT SANS CASSE : `--advance` fait jouer les DEUX IA, donc sans garde-fou les
        # unites meurent avant la mesure (MESURE : au 4e tour il ne restait que 2 unites sur 5, et
        # l'allie a mesurer etait du nombre). `--dmg-target 1` neutralise la frappe adverse ;
        # `--hp-target`/`--hp-player` rendent les deux camps increvables.
        # `--hp-player` ecrit `Health` ET `RemainingHealth` (donc 100 % de PV, un repair NO-OP) --
        # c'est le `--unit-stat`, applique APRES lui dans `rl_duel build`, qui RE-BLESSE les allies.
        # Le manque vaut alors `hp_player - damaged`, tres au-dessus de `hpToRepair` : `MaxFillUp`
        # ne sature pas et le montant BRUT reste visible.
        argv += ["--dmg-target", "1", "--hp-target", "500000", "--hp-player", "300000"]
    return argv


def _build_subprocess(damaged: int, advance: int) -> int:
    state = _ROOT / "logs" / ("_probe334-%d.json" % os.getpid())
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            "--state-file", str(state), *build_args(damaged, advance)]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): "
                           + ((p.stderr or p.stdout or "")[-500:]))
    return json.loads(state.read_text())["runnerId"]


def _move_to(rpc, rid, sq, tile, board):
    c, r = board.coord(tile)
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": sq, "to": {"col": c, "row": r}}}, 60)


def _drive_adjacent(rpc, rid, board, live, sq_mover, anchor_tile, far_from=()):
    """DEPLACE `sq_mover` sur une tuile LIBRE adjacente a `anchor_tile` (et NON adjacente aux tuiles
    de `far_from`). On CONDUIT les positions, on ne subit jamais la geometrie de spawn."""
    U = live()
    mt = board.id_at(U[sq_mover]["col"], U[sq_mover]["row"])
    occ = {board.id_at(u["col"], u["row"]) for u in U.values()}
    banned = set()
    for t in far_from:
        banned |= set(board.neighbours(t)) | {t}
    if mt is not None and mt in board.neighbours(anchor_tile) and mt not in banned:
        return True
    cands = [n for n in board.neighbours(anchor_tile)
             if n in board.by_id and board.walkable(n) and n not in occ and n not in banned]
    cands.sort(key=lambda n: abs(board.coord(n)[0] - U[sq_mover]["col"])
               + abs(board.coord(n)[1] - U[sq_mover]["row"]))
    for n in cands:
        _move_to(rpc, rid, sq_mover, n, board)
        U2 = live()
        m2 = board.id_at(U2[sq_mover]["col"], U2[sq_mover]["row"]) if sq_mover in U2 else None
        if m2 is not None and m2 in board.neighbours(anchor_tile) and m2 not in banned:
            return True
    return False


def _drive_away(rpc, rid, board, live, sq_mover, anchor_tile, min_dist=FAR_MIN_DIST):
    """ELOIGNE `sq_mover` d'au moins `min_dist` hex d'`anchor_tile` -- le TEMOIN NEGATIF de la garde
    d'adjacence : meme cast, meme trait `Mechanical`, seule la DISTANCE change."""
    import hexgeo
    U = live()
    ap = board.coord(anchor_tile)
    if hexgeo.distance((U[sq_mover]["col"], U[sq_mover]["row"]), ap) >= min_dist:
        return True
    occ = {board.id_at(u["col"], u["row"]) for u in U.values()}
    cands = [t for t in board.by_id
             if board.walkable(t) and t not in occ
             and hexgeo.distance(board.coord(t), ap) >= min_dist]
    cands.sort(key=lambda t: abs(board.coord(t)[0] - U[sq_mover]["col"])
               + abs(board.coord(t)[1] - U[sq_mover]["row"]))
    for t in cands[:12]:
        _move_to(rpc, rid, sq_mover, t, board)
        U2 = live()
        if hexgeo.distance((U2[sq_mover]["col"], U2[sq_mover]["row"]), ap) >= min_dist:
            return True
    return False


def run_scenario(rpc, scenario: str = "repair", advance: int | None = None,
                 damaged: int | None = None, build_runner=None, keep: bool = False) -> dict:
    """Monte le scenario, caste 1117 OFFLINE puis LIVE, rend les mesures.

    `rpc(method, body, timeout)` = appel RPC deballe. `build_runner` = fabrique pytest du conftest ;
    absente, on construit par subprocess (`rl_duel build`).

    Rend un dict : `ok`/`why` (montage), `hp_to_repair`, `off`/`live` (deltas HP par visualId ET par
    squadId), `attacks` (port), `normal_targets` (contre-epreuve), `geometry`.
    """
    import hexgeo
    from engine.entities.pathfinding.board import Board
    from engine.entities.effects.magnitude import ability_var
    from engine.runner.abilities.admec import DEFEND_THE_DIVINE_WORK_ID
    from engine.runner.abilities.targeting import valid_normal_attack_targets
    from engine.runner.components import HealthComponent, StatsComponent
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.runner import Runner
    from engine.runner.snapshot import load_state

    advance = advance if advance is not None else (0 if scenario == "repair" else 4)
    damaged = damaged if damaged is not None else (200000 if advance else 2000)

    if build_runner is not None:
        rid = build_runner(SEED, extra=build_args(damaged, advance))["rid"]
    else:
        rid = _build_subprocess(damaged, advance)
    out = {"rid": rid, "scenario": scenario, "advance": advance, "ok": False, "why": None}

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        out["why"] = "boardGraph indispo"
        return out
    board = Board(bg["tiles"], adjacency="native_sym")

    def live():
        return {u["squadId"]: u
                for u in (rpc("observeBattle", {"runnerId": rid}, 40).get("units") or [])
                if not u.get("isDead")}

    U = live()
    sq = {u.get("visualId"): s for s, u in U.items()}
    out["spawn"] = {u.get("visualId"): (u.get("col"), u.get("row")) for u in U.values()}
    for vis in (CASTER_VIS, ADJ_VIS, FAR_VIS):
        if vis not in sq:
            out["why"] = "%s absent du live (mort pendant --advance ?)" % vis
            return out
    enemy_tiles = [board.id_at(u["col"], u["row"]) for u in U.values() if u.get("teamId") == 2]
    if not enemy_tiles:
        out["why"] = "aucun ennemi vivant"
        return out

    if scenario == "attack":
        if not _drive_adjacent(rpc, rid, board, live, sq[ADJ_VIS], enemy_tiles[0]):
            out["why"] = "%s ne peut pas atteindre le contact d'un ennemi" % ADJ_VIS
            return out
        U = live()
        at = board.id_at(U[sq[ADJ_VIS]]["col"], U[sq[ADJ_VIS]]["row"])
        if not _drive_adjacent(rpc, rid, board, live, sq[CASTER_VIS], at, far_from=enemy_tiles):
            out["why"] = "le caster ne peut pas se poser adjacent a l'allie et LOIN des ennemis"
            return out
    elif scenario == "caster":
        if not _drive_adjacent(rpc, rid, board, live, sq[CASTER_VIS], enemy_tiles[0]):
            out["why"] = "le caster ne peut pas atteindre le contact d'un ennemi"
            return out
        U = live()
        ct = board.id_at(U[sq[CASTER_VIS]]["col"], U[sq[CASTER_VIS]]["row"])
        if not _drive_adjacent(rpc, rid, board, live, sq[ADJ_VIS], ct, far_from=enemy_tiles):
            out["why"] = "l'allie ne peut pas se poser adjacent au caster et LOIN des ennemis"
            return out
    else:
        U = live()
        ct = board.id_at(U[sq[CASTER_VIS]]["col"], U[sq[CASTER_VIS]]["row"])
        if not _drive_adjacent(rpc, rid, board, live, sq[ADJ_VIS], ct):
            out["why"] = "impossible d'amener %s au contact du caster" % ADJ_VIS
            return out

    U = live()
    ct = board.id_at(U[sq[CASTER_VIS]]["col"], U[sq[CASTER_VIS]]["row"])
    out["far_driven"] = _drive_away(rpc, rid, board, live, sq[FAR_VIS], ct)

    U = live()
    cp = (U[sq[CASTER_VIS]]["col"], U[sq[CASTER_VIS]]["row"])
    apos = (U[sq[ADJ_VIS]]["col"], U[sq[ADJ_VIS]]["row"])
    fp = (U[sq[FAR_VIS]]["col"], U[sq[FAR_VIS]]["row"])
    out["geometry"] = {
        "caster": cp, "adj": apos, "far": fp,
        "d_caster_adj": hexgeo.distance(cp, apos),
        "d_caster_far": hexgeo.distance(cp, fp),
        "enemies": [{"squadId": s, "visualId": u.get("visualId"), "pos": (u["col"], u["row"]),
                     "d_caster": hexgeo.distance(cp, (u["col"], u["row"])),
                     "d_adj": hexgeo.distance(apos, (u["col"], u["row"]))}
                    for s, u in sorted(U.items()) if u.get("teamId") == 2]}

    # --- capture PRE-cast (positions FINALES) + cast OFFLINE --------------------------------------
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    state = load_state(dv, ob, snap, board=board)
    # `state.rng` CALE sur le MT natif : l'etage 2 TIRE (l'attaque gratuite), donc sans graine le
    # port leve. Meme graine des deux cotes -> les coups sont comparables.
    if isinstance(rng0, dict) and rng0.get("mt"):
        r = IntBasedMersenneTwister()
        r.mt = list(rng0["mt"])
        r.mti = rng0["mti"]
        state.rng = r

    def by_vis(vis):
        for uid, e in state.entities.items():
            sc = e.get_component(StatsComponent)
            if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
                return uid
        return None

    cid = by_vis(CASTER_VIS)
    if cid is None:
        out["why"] = "caster absent offline"
        return out
    out["normal_targets"] = {
        CASTER_VIS: len(valid_normal_attack_targets(state, cid) or []),
        ADJ_VIS: len(valid_normal_attack_targets(state, by_vis(ADJ_VIS)) or [])}

    sc = state.get_entity(cid).get_component(StatsComponent)
    lvl = getattr(sc.ctx, "active_ability_level", None)
    mult = int(getattr(sc.ctx, "ability_variables_multiplier", 100) or 100)
    out["level"], out["multiplier"] = lvl, mult
    out["hp_to_repair"] = ability_var(DEFEND_THE_DIVINE_WORK_ID, "hpToRepair", lvl,
                                      multiplier_pct=mult)

    vis_of = {}
    off_pre = {}
    for uid, e in state.entities.items():
        hc = e.get_component(HealthComponent)
        scc = e.get_component(StatsComponent)
        if hc is not None and hc.hp is not None:
            off_pre[uid] = int(hc.hp)
            vis_of[uid] = getattr(scc.ctx, "visual_id", None) if scc is not None else None
    out["missing_before"] = {vis_of[u]: int(state.get_entity(u)
                                            .get_component(HealthComponent).hp_max) - pre
                             for u, pre in off_pre.items() if vis_of.get(u)}
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=cid, ability_type=ABILITY))
    last = runner.ability_handler.last or {}
    out["ported"] = last.get("ported")
    out["amount"] = last.get("amount")
    out["repairs"] = last.get("repairs")
    out["attacks"] = last.get("attacks")
    out["off"] = {}
    for uid, pre in off_pre.items():
        d = int(state.get_entity(uid).get_component(HealthComponent).hp) - pre
        if vis_of.get(uid):
            out["off"][vis_of[uid]] = d

    # --- cast LIVE ---------------------------------------------------------------------------------
    pre = {s: u["hp"] for s, u in live().items()}
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": sq[CASTER_VIS], "targetId": sq[CASTER_VIS],
        "abilityType": ABILITY}}, 120)
    post = live()
    out["live"] = {u.get("visualId"): u["hp"] - pre.get(s, u["hp"]) for s, u in post.items()}
    out["live_enemy_loss"] = -sum(min(0, u["hp"] - pre.get(s, u["hp"]))
                                  for s, u in post.items() if u.get("teamId") == 2)
    out["off_enemy_loss"] = -sum(min(0, d) for v, d in out["off"].items() if v in ENEMY_VIS)
    out["ok"] = True

    if not keep:
        rpc("disposeRunner", {"runnerId": rid}, 40)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="repair", choices=("repair", "attack", "caster"))
    ap.add_argument("--advance", type=int, default=None)
    ap.add_argument("--damaged", type=int, default=None)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    r = run_scenario(rpc, args.scenario, args.advance, args.damaged, keep=args.keep)
    print("runner=%s scenario=%s advance=%s ok=%s why=%s"
          % (r.get("rid"), r.get("scenario"), r.get("advance"), r.get("ok"), r.get("why")))
    if not r.get("ok"):
        return 1
    g = r["geometry"]
    print("geometrie : caster%s | allie-adj%s d=%d | allie-loin%s d=%d (drive=%s)"
          % (g["caster"], g["adj"], g["d_caster_adj"], g["far"], g["d_caster_far"],
             r.get("far_driven")))
    for e in g["enemies"]:
        print("   ennemi u%-4s %-14s %s d(caster)=%d d(allie-adj)=%d"
              % (e["squadId"], e["visualId"], e["pos"], e["d_caster"], e["d_adj"]))
    print("cibles d'attaque normale depuis la tuile COURANTE : %s" % (r["normal_targets"],))
    print("hpToRepair(lvl=%s mult=%s) = %s" % (r["level"], r["multiplier"], r["hp_to_repair"]))
    print("[PORT] ported=%s amount=%s repairs=%s attacks=%s"
          % (r["ported"], r["amount"], r["repairs"], r["attacks"]))
    print("[PORT] deltas HP : %s" % ({k: v for k, v in r["off"].items() if v},))
    print("[LIVE] deltas HP : %s" % ({k: v for k, v in r["live"].items() if v},))
    print("perte ENNEMIE totale : live=%s port=%s" % (r["live_enemy_loss"], r["off_enemy_loss"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
