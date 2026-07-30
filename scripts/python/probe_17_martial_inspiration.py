#!/usr/bin/env python
"""probe_17_martial_inspiration -- MONTAGE NOMME du canal `actorStats` PAR-PAS qui alimente la
prediction de MartialInspiration (1191).

QUESTION BINAIRE. Quand le compteur natif `TotalAttacksMade` du caster BOUGE en cours de bataille,
la prediction offline de 1191 suit-elle le natif -- et le figer (regime COLD) la fait-il diverger ?
Sans la seconde moitie, la premiere ne prouve rien : un port qui ignorerait le compteur matcherait
aussi longtemps que le compteur vaut 0.

MECANIQUE (decompile = verite, build `rnca9r7q6c`).

    IdunBattle.AI.Playbook.Loki.MartialInspirationPlaybook.u003CMakeDamagePredictionsu003Ed__2$$MoveNext
        var12 = IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel(cfg, 0xc)   # minDmg, rarity-scaled
        var10 = IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel(cfg, 0xa)   # extraDmgPct, NON rarity-scaled
        count = <ActorStatisticsComponent>+0x20                                                 # TotalAttacksMade
        base  = slot0x10( Fix64(var12), Fix64.FromIntFraction(var10 * count + 100, 100) )
              = IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers   # round(a*b)
        hits  = 1 (litteral ecrit a +0x40)

L'ECRIVAIN du compteur est `IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterAttackMade`
(appele par `IdunBattle.Operations.RegisterAttackOperation$$Execute`) : il incremente `+0x20` a CHAQUE
attaque enregistree. Le lecteur cote formule est
`IdunBattle.Entities.Formulas.TotalAttacksMadeFormula$$Calculate` (`return *(uint *)(comp + 0x20)`).

    ATTENTION -- la face COMBAT lit un AUTRE compteur :
    `IdunBattle.Entities.Effects.Loki.MartialInspiration_ExtraDamageEffect$$GetBuffPct` =
    `Multiply(ConfigVar(0xa), TotalTurnsWithAttacksMade)` (+0x30, incremente une seule fois par TOUR).
    La divergence prediction (+0x20) / combat (+0x30) est NATIVE ; ce probe ne mesure QUE la premiere.

COTE PORT. `engine/playbook/prediction/abilities.py::_martial_inspiration_inputs` (registre
`_MAKE_DMG_INPUT_OVERRIDES[1191]`) lit `scene.total_attacks_made(caster)`, qui vient de
`predictor["actorstats_by_id"]`. Ce dict a DEUX ecrivains : le COLD de `scene.build_predictor` (capte
au pas 0, donc 0 pour tout le monde) et la RE-CAPTURE PAR-PAS de `scene.refresh_shields` (#33). C'est
cette seconde ecriture -- une lecture du RPC `actorStats` a chaque pas compare -- que ce montage
eprouve.

CE QUE MESURE LE MONTAGE, par tour :

  * `count`      -- `actorStats[caster].totalAttacksMade`, lu LIVE (verite du natif, pas un derive) ;
  * `nat`        -- `aiPlaybookPredict(caster, cible, 1191)` depuis la tuile COURANTE ;
  * `off_fresh`  -- le port avec le canal per-pas ACTIF (build_predictor + refresh_shields) ;
  * `off_cold`   -- le MEME port, un SEUL canal perime : `actorstats_by_id` re-ecrit avec l'instantane
                    du tour 0. Mutation CHIRURGICALE (tous les autres canaux restent frais), sinon un
                    ecart pourrait venir des PV, du bouclier ou de l'armure.

Puis le caster attaque (attaque NORMALE, id concret lu dans `decisionView`) : le compteur passe a
count+1, et le tour suivant re-mesure. Le regime discriminant est donc `count >= 1`.

Aucune valeur attendue codee en dur : l'oracle est le natif qui tourne.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_17_martial_inspiration.py [--seed 11911] [--board MC1_67] [--rounds 3]

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402
from engine_agreement_stages import _fields_from_native_event, _pred_delta  # noqa: E402

MARTIAL_INSPIRATION = 1191
CARRIER = "custoBladeChampion"    # Kariyan -- le porteur de MartialInspiration (1191)
TARGET = "necroWarden"            # cible robuste ; PV forces tres haut -> survit a tous les coups
FILLER = "necroOverlord"          # 2e a-unit : la bataille ne se termine pas si la cible tombe
BOARD = "MC1_67"
RANK = 17
HP_TARGET = 300000                # `--hp-target` : la cible ne meurt jamais (et son armure tombe a 0)


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(sid, state_file: Path, seed: int, board: str) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state_file), "--board", board, "--rank", str(RANK),
         "--p-units", CARRIER, "--a-units", "%s,%s" % (TARGET, FILLER),
         "--hp-target", str(HP_TARGET), "--crit", "0,0", "--block-target", "0,0"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-500:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _view(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)


def _by_visual(dv, vis):
    for u in (dv.get("units") or []):
        if u.get("visualId") == vis:
            return u
    return None


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _move(sid, rid, uid, col, row):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def _attack(sid, rid, attacker, target, ability):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(attacker), "targetId": int(target),
        "abilityType": int(ability)}}, 120)


def _my_player(dv):
    for u in (dv.get("units") or []):
        if u.get("ctrl"):
            return u.get("owner")
    return dv.get("currentPlayer")


def _next_turn(sid, rid, me, max_steps=8):
    """Rend la main a MON camp sans faire jouer l'IA (`endturn` seulement : la geometrie est figee)."""
    _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    for _ in range(max_steps):
        dv = _view(sid, rid)
        if dv.get("currentPlayer") == me:
            return dv
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    return _view(sid, rid)


def _normal_attack_id(dv, uid):
    """Id CONCRET de l'attaque normale du caster (`kind == "normal"` de `decisionView`) -- per-unite,
    JAMAIS le 17 generique (cf. `NormalAttackType@0x28`)."""
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    for a in ((u or {}).get("abilities") or []):
        if a.get("kind") == "normal":
            return a.get("id")
    return None


def _actor_counts(sid, rid):
    """`ActorStatisticsComponent+0x20` per-unite, LU LIVE (RPC `actorStats`) -- la verite du natif."""
    resp = _r(sid, "actorStats", {"runnerId": rid}, 60)
    units = resp.get("units")
    if units is None:
        return None                      # canal NON MESURE (RPC KO) != canal mesure et vide
    return {u["entityId"]: int(u.get("totalAttacksMade") or 0)
            for u in units if u.get("entityId") is not None}


def _build_predictor(sid, rid):
    """Le predicteur COLD, construit UNE SEULE FOIS -- exactement comme `engine_validate.
    run_agreement`, qui appelle `build_predictor` au debut du walk puis `refresh_shields` a chaque
    pas. Le reconstruire a chaque tour masquerait le defaut que ce montage eprouve (un
    `build_predictor` neuf re-capte `actorStats` par lui-meme)."""
    from engine.playbook import scene as SC
    predictor = SC.build_predictor((lambda m, b, t=90: _r(sid, m, b, t)), rid)
    if predictor is None:
        raise RuntimeError("build_predictor KO (combatSnapshot indisponible)")
    return predictor


def _ctx_for(sid, rid, dv, uid, wt, predictor, cold_actorstats=None):
    """`AiDecisionContext` du caster, sur le predicteur COLD rafraichi PAR PAS (`refresh_shields`)
    -- la couture reelle du seam de decision. `cold_actorstats` non None => on RE-ECRIT ensuite le
    SEUL canal `actorstats_by_id` avec l'instantane du tour 0 : tous les autres canaux restent
    FRAIS, l'ecart mesure ne peut donc venir que de ce canal."""
    from engine.playbook import scene as SC
    from engine.ai import context as AICTX
    rpc_l = (lambda m, b, t=90: _r(sid, m, b, t))
    SC.refresh_shields(predictor, rpc_l, rid)
    if cold_actorstats is not None:
        predictor["actorstats_by_id"] = dict(cold_actorstats)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return AICTX.build(rpc_l, rid, dv, mov_by_unit, uid, wt, predictor)


def _off_fields(ctx, tile, tgt, ability=MARTIAL_INSPIRATION):
    """Champs composite de la prediction OFFLINE d'une ability sur la cible principale."""
    from engine.playbook import get_playbook_or_default
    from engine.playbook.common import NormalAttackPlaybook
    pb = (NormalAttackPlaybook() if ability in getattr(ctx, "normal_ids", set())
          else get_playbook_or_default(ability))
    evs = pb.make_damage_predictions(ctx, tile, tgt, ability) or []
    main = next((e for e in evs if e.target == tgt), evs[0] if evs else None)
    return (None if main is None else main.composite_fields()), len(evs)


def _adjacent_free(brd, center, occupied):
    for tid in brd.neighbours(brd.id_at(*center)):
        c = brd.coord(tid)
        t = brd.by_id.get(tid) or {}
        if c and c not in occupied and t.get("walkable") and not t.get("isWall"):
            return c
    return None


def run(seed: int = 11911, board: str = BOARD, rounds: int = 3, state_file=None,
        keep: bool = False, verbose: bool = True) -> dict:
    """Monte le cas, mesure `rounds` tours, dispose. Rend un dict ; `{"error": ...}` si le montage
    ne s'installe pas -- un montage NON INSTALLE doit ROUGIR chez l'appelant, jamais passer vert."""
    from engine import weights
    from engine.entities.pathfinding.board import Board

    sid = _resolve_session()
    sf = Path(state_file) if state_file else (ROOT / "logs" / ("probe_17_mi_%d.json" % seed))
    rid = None
    try:
        rid = _build(sid, sf, seed, board)
        if verbose:
            print("[17-mi] runner=%d seed=%d board=%s" % (rid, seed, board))
        dv = _view(sid, rid)
        me = _my_player(dv)
        car = _by_visual(dv, CARRIER)
        tgt = _by_visual(dv, TARGET)
        if car is None or tgt is None:
            raise RuntimeError("roster incomplet : carrier=%s target=%s" % (car, tgt))
        cid, tid = car["id"], tgt["id"]

        bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="native_sym")

        # GEOMETRIE DRIVEE : la cible est amenee au CONTACT du caster (voisin au sens NATIF, c'est
        # la portee de melee que le jeu consulte). Le caster ne bouge pas : son deplacement doit
        # rester disponible, et sa tuile sert d'origine a toutes les predictions.
        occupied = {p for p in (_pos(u) for u in (dv.get("units") or [])) if p}
        cpos = _pos(car)
        spot = _adjacent_free(brd, cpos, occupied - {_pos(tgt)})
        if spot is None:
            raise RuntimeError("aucune tuile libre voisine du caster @%s" % (cpos,))
        _move(sid, rid, tid, spot[0], spot[1])
        dv = _view(sid, rid)
        cpos, tpos = _pos(_by_visual(dv, CARRIER)), _pos(_by_visual(dv, TARGET))
        if cpos is None or tpos is None or hexgeo.distance(cpos, tpos) != 1:
            raise RuntimeError("contact NON etabli : caster @%s cible @%s" % (cpos, tpos))

        na = _normal_attack_id(dv, cid)
        if na is None:
            raise RuntimeError("aucune attaque normale (`kind == normal`) sur u%d" % cid)
        wt = weights.load()
        cold0 = _actor_counts(sid, rid)
        if cold0 is None:
            raise RuntimeError("RPC actorStats NON MESURE (units absent) -- rien de concluant")
        if verbose:
            print("[17-mi] caster u%d @%s | cible u%d @%s | attaque normale=%d | count(tour 0)=%d"
                  % (cid, cpos, tid, tpos, na, cold0.get(cid, 0)))

        # DEUX predicteurs COLD, construits UNE SEULE FOIS au tour 0 (mirror de `run_agreement`) :
        # `pred_live` est rafraichi par pas ; `pred_stale` l'est AUSSI, mais son `actorstats_by_id`
        # est re-ecrit apres coup avec l'instantane du tour 0 -- la MUTATION d'un SEUL canal.
        pred_live = _build_predictor(sid, rid)
        pred_stale = _build_predictor(sid, rid)
        rows = []
        for rnd in range(rounds):
            counts = _actor_counts(sid, rid)
            if counts is None:
                raise RuntimeError("RPC actorStats NON MESURE au tour %d" % rnd)
            count = counts.get(cid, 0)
            dv = _view(sid, rid)
            cpos = _pos(_by_visual(dv, CARRIER))

            nat_resp = _r(sid, "aiPlaybookPredict", {
                "runnerId": rid, "unitId": cid, "targetId": tid,
                "abilityType": MARTIAL_INSPIRATION,
                "col": cpos[0], "row": cpos[1]}, 90)
            nat_evs = (nat_resp.get("events") or []) if nat_resp.get("ok") else []
            nat_main = next((e for e in nat_evs if e.get("targetId") == tid),
                            nat_evs[0] if nat_evs else None)
            nat_f = None if nat_main is None else _fields_from_native_event(nat_main)
            shield_ok = bool(nat_main) and "shieldDmgMin" in nat_main

            ctx_fresh = _ctx_for(sid, rid, dv, cid, wt, pred_live)
            off_f, n_off = _off_fields(ctx_fresh, cpos, tid)
            ctx_cold = _ctx_for(sid, rid, dv, cid, wt, pred_stale, cold_actorstats=cold0)
            cold_f, _ = _off_fields(ctx_cold, cpos, tid)

            # CONTROLE : la MEME confrontation sur l'attaque NORMALE, meme tuile, meme pas. Elle ne
            # passe PAS par `_martial_inspiration_inputs` ni par le compteur. Un ecart present des
            # DEUX cotes est donc AVAL (pipeline de degat commun), pas imputable a ce canal.
            ctrl_nat = _r(sid, "aiPlaybookPredict", {
                "runnerId": rid, "unitId": cid, "targetId": tid, "abilityType": na,
                "col": cpos[0], "row": cpos[1]}, 90)
            ctrl_evs = (ctrl_nat.get("events") or []) if ctrl_nat.get("ok") else []
            ctrl_main = next((e for e in ctrl_evs if e.get("targetId") == tid),
                             ctrl_evs[0] if ctrl_evs else None)
            ctrl_nat_f = None if ctrl_main is None else _fields_from_native_event(ctrl_main)
            ctrl_off_f, _ = _off_fields(ctx_fresh, cpos, tid, ability=na)

            row = {
                "round": rnd, "count_live": count,
                "count_seen_fresh": ctx_fresh.scene.total_attacks_made(cid),
                "count_seen_cold": ctx_cold.scene.total_attacks_made(cid),
                "caster_pos": cpos, "n_native_events": len(nat_evs), "n_off_events": n_off,
                "native": (None if nat_f is None else
                           {"rawMin": nat_f["rawHealthDmgMin"], "rawMax": nat_f["rawHealthDmgMax"],
                            "hits": nat_f["appliedHits"]}),
                "off_fresh": (None if off_f is None else
                              {"rawMin": off_f["rawHealthDmgMin"],
                               "rawMax": off_f["rawHealthDmgMax"],
                               "hits": off_f["appliedHits"]}),
                "off_cold": (None if cold_f is None else
                             {"rawMin": cold_f["rawHealthDmgMin"],
                              "rawMax": cold_f["rawHealthDmgMax"],
                              "hits": cold_f["appliedHits"]}),
                "delta_fresh": (None if (nat_f is None or off_f is None)
                                else (_pred_delta(off_f, nat_f, shield_ok) or None)),
                "delta_cold": (None if (nat_f is None or cold_f is None)
                               else (_pred_delta(cold_f, nat_f, shield_ok) or None)),
                "control_normal_attack": (
                    None if (ctrl_nat_f is None or ctrl_off_f is None) else
                    {"nat": {"rawMin": ctrl_nat_f["rawHealthDmgMin"],
                             "rawMax": ctrl_nat_f["rawHealthDmgMax"]},
                     "off": {"rawMin": ctrl_off_f["rawHealthDmgMin"],
                             "rawMax": ctrl_off_f["rawHealthDmgMax"]},
                     "delta": (_pred_delta(ctrl_off_f, ctrl_nat_f,
                                           bool(ctrl_main) and "shieldDmgMin" in ctrl_main)
                               or None)}),
            }
            rows.append(row)
            if verbose:
                print("[17-mi] tour %d count=%d (fresh voit %s / cold voit %s) | nat=%s "
                      "off_fresh=%s off_cold=%s"
                      % (rnd, count, row["count_seen_fresh"], row["count_seen_cold"],
                         row["native"], row["off_fresh"], row["off_cold"]))
                if row["delta_fresh"]:
                    print("[17-mi]    ECART fresh<->natif : %s" % (row["delta_fresh"],))
                if row["delta_cold"]:
                    print("[17-mi]    ecart COLD<->natif (attendu des count>=1) : %s"
                          % (row["delta_cold"],))
                cn = row["control_normal_attack"]
                if cn:
                    print("[17-mi]    CONTROLE attaque normale (%d) : nat=%s off=%s ecart=%s"
                          % (na, cn["nat"], cn["off"], bool(cn["delta"])))

            if rnd + 1 < rounds:
                _attack(sid, rid, cid, tid, na)     # incremente TotalAttacksMade (+0x20)
                _next_turn(sid, rid, me)

        return {"rid": rid, "seed": seed, "board": board, "caster": cid, "target": tid,
                "normal_attack": na, "cold0": cold0.get(cid, 0), "rows": rows}
    except RuntimeError as exc:
        return {"error": str(exc)}
    finally:
        if rid is not None and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            if verbose:
                print("[17-mi] runner %d dispose" % rid)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=11911)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    res = run(seed=a.seed, board=a.board, rounds=a.rounds, keep=a.keep)
    if "error" in res:
        print("[17-mi] MONTAGE NON INSTALLE : %s" % res["error"], file=sys.stderr)
        return 2
    bad = [r for r in res["rows"] if r["delta_fresh"]]
    disc = [r for r in res["rows"] if r["count_live"] >= 1 and r["delta_cold"]]
    print("[17-mi] VERDICT : %d/%d tours d'accord port<->natif ; %d tour(s) ou le canal COLD "
          "DIVERGE (canal discriminant)"
          % (len(res["rows"]) - len(bad), len(res["rows"]), len(disc)))
    return 0 if (not bad and disc) else 1


if __name__ == "__main__":
    sys.exit(main())
