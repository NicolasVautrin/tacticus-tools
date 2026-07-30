#!/usr/bin/env python
"""probe_17_active_ability_used_gate -- MONTAGE NOMME du gate d'entree du generateur d'abilities de
l'IA : `HasFlag(unit, UnitFlag.ActiveAbilityUsed = 2)`.

QUESTION BINAIRE. Une unite qui a DEJA consomme son action (flag 2 pose) mais dont le tour n'est PAS
termine se voit-elle encore proposer une ability par le port, la ou le natif ne peut plus que la
DEPLACER ?

MECANIQUE (decompile = verite, build `rnca9r7q6c`). PREMIERE instruction de l'etat 0 de
`IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` :

    if (IdunBattle.Entities.UnitExtensions$$HasFlag(<unit @+0x20>, 2)) return 0;

Le generateur rend ZERO action -- AVANT `GetUnitAbilitiesInOrder`, donc l'attaque NORMALE tombe avec
les actives (elles partagent la meme liste, cf. #64).
`IdunBattle.AI.Tactics.ABaseAiActorTactic$$GetDefaultActiveAbilityActionGenerators` instancie SIX
generateurs de cette MEME classe (5 tiers NonComparable + 1 Comparable) ; le
`MovementActionGenerator`, lui, est d'une AUTRE classe et n'est pas gate -- d'ou l'asymetrie
observable : plus aucune ability, mais le deplacement reste.

CE QUI POSE LE FLAG SANS FINIR LE TOUR. `IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution`
lit DEUX virtuals independants : `SetsActiveAbilityUsedFlag` (-> flag 2) et `SetsEndTurnFlags`
(-> `FinishUnitTurn`). Deux abilities du binaire overrident le SECOND sans le premier
(`engine/runner/abilities/base.py` : `NO_END_TURN_ABILITY_TYPES` prive de
`NO_ABILITY_USED_FLAG_ABILITY_TYPES`) : **1121 ItItches** (tyranParasite) et **1063
FireAndReposition** (Calandis, hors pool). Ce sont exactement les etats ou le gate est OBSERVABLE :
l'unite reste activable et porte deja son flag.

ORIGINE DU CAS. Residu `move` de la fiche #17, etiquete « over-fire RNG » -- etiquette FAUSSE pour
celui-la : re-derive le 2026-07-30, `1357 s6 u85 tyranParasite` porte `unitFlags = [2]` apres avoir
caste 1121 au pas 5 ; le natif BOUGE vers (3,2) sans attaquer, le port emet `69 -> u93`. C'est un
gate DETERMINISTE manquant, pas un tirage. (L'AUTRE residu, `2468 s4`, est lui reellement RNG :
`SpawnPoxwalkersPlaybook$$GetUseProbability = TurnsStarted x 1/5`.)

CE QUE MESURE LE MONTAGE, en deux regimes sur le MEME runner :
  * AVANT le cast (flag absent)  -- temoin : le natif ET le port proposent une ability ;
  * APRES le cast (flag pose)    -- le natif ne propose plus d'ability ; le port GATE non plus ;
                                    le port dont on NEUTRALISE le seul canal
                                    `active_ability_used_by_id` en propose une (contre-epreuve).
Sans la contre-epreuve, « le port ne propose pas d'ability » pourrait venir de n'importe quoi
(plus de cible, plus de tuile) et la garde serait vide.

Oracle natif = `aiDryRunAllUnits` (`CalculateNextActionForUnit` par unite, sans appliquer).

Usage (depuis scripts/python, session Frida chaude) :
    python probe_17_active_ability_used_gate.py [--seed 12100] [--board MC1_67]

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

from rl_collect_batch import _resolve_session, _rpc            # noqa: E402

CARRIER = "tyranParasite"      # Parasite of Mortrex -- porteur d'ItItches (1121)
IT_ITCHES = 1121               # SetsEndTurnFlags override (pas de fin de tour) MAIS pose le flag 2
TARGET = "necroWarden"
FILLER = "necroOverlord"
BOARD = "MC1_67"
RANK = 17
HP_TARGET = 300000             # la cible survit : l'etat reste stable entre les deux regimes
ACTIVE_ABILITY_USED = "ActiveAbilityUsed"


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


def _my_player(dv):
    for u in (dv.get("units") or []):
        if u.get("ctrl"):
            return u.get("owner")
    return dv.get("currentPlayer")


def _unit_flags(sid, rid, uid):
    """(liste des flags de l'unite, id de `ActiveAbilityUsed`) -- tri-etat conserve : `None` = le
    capteur n'a rien mesure, ce qui n'est PAS « aucun flag »."""
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
    row = next((u for u in (snap.get("units") or []) if u.get("entityId") == uid), {})
    return row.get("unitFlags"), (snap.get("unitFlagTypes") or {}).get(ACTIVE_ABILITY_USED)


def _ability_row(sid, rid, uid, ability_id):
    at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": uid}, 90)
    u = next((x for x in (at.get("units") or []) if x.get("unitId") == uid), {})
    for a in (u.get("abilities") or []):
        if a.get("abilityId") == ability_id:
            return a
    return {}


def _native_proposal(sid, rid, uid):
    """Action que le NATIF propose pour `uid` contre l'etat courant (`CalculateNextActionForUnit`,
    sans appliquer). Rend (liste des classes de messages, ligne brute)."""
    res = _r(sid, "aiDryRunAllUnits", {"runnerId": rid}, 180)
    row = next((u for u in (res.get("units") or []) if u.get("unitId") == uid), None)
    if row is None:
        return None, res
    return [m.get("cls") for m in (row.get("proposed") or [])], row


def _port_decision(sid, rid, dv, uid, wt, neutralise_gate: bool = False):
    """Decision du PORT sur l'etat courant. `neutralise_gate` VIDE le seul canal
    `active_ability_used_by_id` -> l'accesseur rend `None` (non mesure) et le gate reste ouvert :
    c'est EXACTEMENT le port d'avant ce correctif, tous les autres canaux restant frais.

    INSTRUMENTATION (#302) : on COMPTE les appels a `nonattack_candidates`, la route Comparable
    SANS prediction -- celle qui porte le domaine de cible TUILE depuis #302. Elle vit a
    l'INTERIEUR de `ComparableAbilityGenerator.generate`, donc EN AVAL du gate ; le compteur le
    MESURE au lieu de le supposer. Attendu : 0 appel quand le gate coupe, >= 1 quand il est
    neutralise. Cote natif, le gate est la 1re instruction de l'UNIQUE classe de generateur
    d'abilities (`ABaseAiActorTactic$$GetDefaultActiveAbilityActionGenerators` en instancie SIX,
    toutes `ActiveAbilityActionGenerator$$.ctor`) et il precede `GetUnitAbilitiesInOrder` : il
    ignore donc le domaine de cible, entite comme tuile.

    Rend `(action, flag_vu_par_la_scene, {"nonattack_calls": n, "nonattack_cands": m})`."""
    from engine.playbook import scene as SC
    from engine.ai import action_generators as AG
    import engine_validate as EV
    rpc_l = (lambda m, b, t=90: _r(sid, m, b, t))
    predictor = SC.build_predictor(rpc_l, rid)
    if predictor is None:
        raise RuntimeError("build_predictor KO (combatSnapshot indisponible)")
    SC.refresh_shields(predictor, rpc_l, rid)
    seen = dict(predictor.get("active_ability_used_by_id") or {})
    if neutralise_gate:
        predictor["active_ability_used_by_id"] = {}
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    orig = AG.nonattack_candidates
    tally = {"nonattack_calls": 0, "nonattack_cands": 0}

    def counted(c):
        tally["nonattack_calls"] += 1
        out = orig(c)
        tally["nonattack_cands"] += len(out or [])
        return out
    AG.nonattack_candidates = counted
    try:
        act = EV.engine_decide(sid, rid, dv, mov_by_unit, uid, wt, predictor)
    finally:
        AG.nonattack_candidates = orig
    return act, seen.get(uid), tally


def _adjacent_free(brd, center, occupied):
    for tid in brd.neighbours(brd.id_at(*center)):
        c = brd.coord(tid)
        t = brd.by_id.get(tid) or {}
        if c and c not in occupied and t.get("walkable") and not t.get("isWall"):
            return c
    return None


def run(seed: int = 12100, board: str = BOARD, state_file=None, keep: bool = False,
        verbose: bool = True) -> dict:
    """Monte les deux regimes, mesure, dispose. Rend un dict ; `{"error": ...}` si le montage ne
    s'installe pas -- un montage NON INSTALLE doit ROUGIR chez l'appelant."""
    from engine import weights
    from engine.entities.pathfinding.board import Board

    sid = _resolve_session()
    sf = Path(state_file) if state_file else (ROOT / "logs" / ("probe_17_aau_%d.json" % seed))
    rid = None
    try:
        rid = _build(sid, sf, seed, board)
        if verbose:
            print("[17-aau] runner=%d seed=%d board=%s" % (rid, seed, board))
        dv = _view(sid, rid)
        me = _my_player(dv)
        car, tgt = _by_visual(dv, CARRIER), _by_visual(dv, TARGET)
        if car is None or tgt is None:
            raise RuntimeError("roster incomplet : carrier=%s target=%s" % (car, tgt))
        cid, tid = car["id"], tgt["id"]
        if dv.get("currentPlayer") != me:
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            dv = _view(sid, rid)

        # GEOMETRIE DRIVEE : la cible est amenee au CONTACT du caster (graphe NATIF = la portee de
        # melee que le jeu consulte). Le caster ne bouge pas : son deplacement doit rester
        # disponible pour que le regime APRES puisse encore produire un `move`.
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="native_sym")
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

        wt = weights.load()

        # ---- REGIME AVANT : le flag n'est pas pose ------------------------------------------
        fl_before, flag_id = _unit_flags(sid, rid, cid)
        if flag_id is None:
            raise RuntimeError("`unitFlagTypes.%s` absent du capteur -- rien n'est concluant"
                               % ACTIVE_ABILITY_USED)
        na_before = _ability_row(sid, rid, cid, IT_ITCHES)
        nat_before, _row_b = _native_proposal(sid, rid, cid)
        port_before, seen_b, tally_before = _port_decision(sid, rid, dv, cid, wt)

        # cible de tuile d'ItItches, castable SANS bouger (`fromHere` = legalite exacte du cast
        # immediat) -- sinon le caster consommerait son deplacement et le regime APRES ne pourrait
        # plus produire de `move`.
        from_here = [t for t in (na_before.get("fromHere") or []) if t.get("kind") == "tile"]
        if not from_here:
            raise RuntimeError(
                "ItItches (1121) n'est castable depuis AUCUNE tuile courante (fromHereCount=%s, "
                "targetCount=%s) -- le montage ne peut pas poser le flag sans deplacer le caster"
                % (na_before.get("fromHereCount"), na_before.get("targetCount")))
        cast_tile = from_here[0]["tile"]
        cast = _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": int(cid), "abilityType": IT_ITCHES,
            "to": {"col": int(cast_tile["col"]), "row": int(cast_tile["row"])}}}, 180)

        # ---- REGIME APRES : le flag est pose, le tour n'est PAS termine ----------------------
        dv2 = _view(sid, rid)
        fl_after, _ = _unit_flags(sid, rid, cid)
        atk_after = _ability_row(sid, rid, cid, 69)
        nat_after, row_a = _native_proposal(sid, rid, cid)
        port_after, seen_a, tally_after = _port_decision(sid, rid, dv2, cid, wt)
        port_ungated, _, tally_ungated = _port_decision(sid, rid, dv2, cid, wt,
                                                        neutralise_gate=True)

        out = {
            "rid": rid, "seed": seed, "board": board, "caster": cid, "target": tid,
            "caster_pos": cpos, "target_pos": tpos, "cast_tile": (cast_tile["col"], cast_tile["row"]),
            "cast_ok": bool(cast.get("ok")), "cast_mutated": cast.get("mutated"),
            "flag_id": flag_id,
            "flags_before": fl_before, "flags_after": fl_after,
            "flag_set_before": (None if fl_before is None else (flag_id in fl_before)),
            "flag_set_after": (None if fl_after is None else (flag_id in fl_after)),
            "scene_sees_before": seen_b, "scene_sees_after": seen_a,
            "native_before": nat_before, "native_after": nat_after,
            "has_action_left_after": (row_a or {}).get("hasActionLeft"),
            "port_before": port_before, "port_after": port_after, "port_ungated": port_ungated,
            # `AttackQuery$$GetValidTargets` ne gate PAS sur le flag : l'attaque reste « legale »
            # apres le cast. C'est ce qui rend l'over-fire possible cote port -- et ce qui rend la
            # contre-epreuve credible.
            "attack_targets_after": atk_after.get("targetCount"),
            "attack_fromhere_after": atk_after.get("fromHereCount"),
            # #302 : la route Comparable SANS prediction (domaine de cible TUILE) est-elle
            # COUVERTE par le gate ? Mesure, pas supposition.
            "nonattack_route_before": tally_before,
            "nonattack_route_after": tally_after,
            "nonattack_route_ungated": tally_ungated,
        }
        if verbose:
            print("[17-aau] caster u%d @%s | cible u%d @%s | cast 1121 -> tuile %s (ok=%s)"
                  % (cid, cpos, tid, tpos, out["cast_tile"], out["cast_ok"]))
            print("[17-aau] AVANT : flags=%s scene voit=%s | natif=%s | port=%s"
                  % (fl_before, seen_b, nat_before, port_before))
            print("[17-aau] APRES : flags=%s scene voit=%s hasActionLeft=%s | 69 targets=%s "
                  "fromHere=%s" % (fl_after, seen_a, out["has_action_left_after"],
                                   out["attack_targets_after"], out["attack_fromhere_after"]))
            print("[17-aau]   natif      = %s" % (nat_after,))
            print("[17-aau]   port GATE  = %s" % (port_after,))
            print("[17-aau]   port SANS  = %s   (contre-epreuve : le port d'avant le correctif)"
                  % (port_ungated,))
            print("[17-aau]   route non-attaque / TUILE (#302) : avant=%s apres(gate)=%s "
                  "apres(sans gate)=%s" % (tally_before, tally_after, tally_ungated))
        return out
    except RuntimeError as exc:
        return {"error": str(exc)}
    finally:
        if rid is not None and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            if verbose:
                print("[17-aau] runner %d dispose" % rid)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=12100)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    res = run(seed=a.seed, board=a.board, keep=a.keep)
    if "error" in res:
        print("[17-aau] MONTAGE NON INSTALLE : %s" % res["error"], file=sys.stderr)
        return 2
    ok = (res["flag_set_after"] and res["port_after"].get("kind") != "ability"
          and res["port_ungated"].get("kind") == "ability")
    print("[17-aau] VERDICT : flag pose=%s | port gate propose %s | port sans gate propose %s"
          % (res["flag_set_after"], res["port_after"].get("kind"),
             res["port_ungated"].get("kind")))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
