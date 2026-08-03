"""#448-r1-r1 -- `FullThrottleAbility$$CreateTrigger` : le gate porte, et le SEUIL confronte.

Le behaviour de `1134 FullThrottle` etait porte depuis #532 ; son `CreateTrigger` ne l'etait pas.
Ce probe (a) verifie le cablage offline, (b) tranche LIVE la seule constante que la RE laisse
disputable : le seuil effectif du gate.

    ...FullThrottleAbility$$CreateTrigger =
        On(0x24 = UnitPositionChanged_1) & get_OwnerIsActor
      & AmountIsEqualOrGreater( MovementSteps(), Direct(GetNumberConstant(0x51='movement'=3)) )

`MovementSteps()` = `IdunBattle.DSL.MovementStepFormula$$Calculate` =
`Nullable<int>.GetValueOrDefault(AbilityEntities+0x11c)`, et `AbilityEntities+0x11c` se nomme
`movementSteps` (signature du ctor a 33 parametres). Son SEUL emetteur,
`IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers`, le recoit de
`IdunBattle.Operations.MoveUnitOperation$$Execute` qui y met **`path.Count`** pour un marcheur.

    path[0] = tuile de DEPART  (la boucle `MoveUnitOperation$$AddMoveEvent` demarre a i = 1)
    `BattleQuery$$GetNumTilesMoved(path)` = path.Count - 1   <- le compte de tuiles PARCOURUES

=> HYPOTHESE H_COUNT : le gate mord des **2 pas** (2 pas -> Count 3 -> 3 >= 3).
   HYPOTHESE H_STEPS : le gate mord des **3 pas** (lecture naive « movementSteps = nb de pas »).

Les deux ne different QUE sur un mouvement de 2 pas -- c'est le bras discriminant, et il est joue
LIVE : on greffe le passif sur des unites du pool (`catalog_inject.graft_passive_ability`, seul
chemin de confrontation d'une ability a porteur npc -- `orksNpc6Stormboy` est le seul porteur),
on les deplace d'EXACTEMENT L pas, et on compte les morts.

    L = 1 -> Count 2 : gate FAUX sous les DEUX hypotheses  -> 0 mort attendue (controle NEGATIF)
    L = 2 -> Count 3 : gate VRAI sous H_COUNT, FAUX sous H_STEPS   -> **DISCRIMINANT**
    L = 3 -> Count 4 : gate VRAI sous les DEUX               -> morts attendues (controle POSITIF)

`chance` = 30 %, donc chaque bras est une mesure de FREQUENCE : le verdict se lit sur « au moins
une mort » (bras 2 et 3) et « aucune mort » (bras 1), avec le nombre d'essais publie pour que la
force du test soit lisible (P(0 mort | gate vrai) = 0.7^n).

Usage :
    python probe_448_r1_r1_full_throttle.py --offline    # etape 0 SEULE (0 runner)
    python probe_448_r1_r1_full_throttle.py              # etape 0 + les 3 bras live
    python probe_448_r1_r1_full_throttle.py --mutate     # CONTRE-EPREUVE (doit ROUGIR)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
sys.path.insert(0, str(PYDIR))

ABILITY = "FullThrottle"
# Greffons : des unites DU POOL (`rl_duel build --list-pool`). `orksNob` porte Movement 4, les
# autres 3 -- tous permettent un pas de 1, 2 et 3 hexes.
GRAFTS = ["orksNob", "orksWarboss", "orksRuntherd", "orksBigMek", "orksKillaKan"]


# ------------------------------------------------------------------ ETAPE 0 (offline)
def etape0() -> int:
    import gameconfig as GC
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    from engine.runner.operations.triggers.loki.full_throttle import (FullThrottlePassiveAbility,
                                                                      FULL_THROTTLE)
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.dsl.event_trigger_type import EventTriggerType

    bad = 0
    print("== ETAPE 0 (offline) -- cablage du gate")

    cls = ABILITY_TRIGGERS.get(ABILITY) or []
    ok = FullThrottlePassiveAbility in cls
    print("   ABILITY_TRIGGERS[%s] = %s -> %s" % (ABILITY, [c.__name__ for c in cls],
                                                  "OK" if ok else "MANQUANT"))
    bad += 0 if ok else 1

    ev_id = int(FullThrottlePassiveAbility.event_id)
    ok = ev_id == int(EventTriggerType.UnitPositionChanged_1)
    print("   event_id = %s (0x%x) attendu 0x24 UnitPositionChanged_1 -> %s"
          % (ev_id, ev_id, "OK" if ok else "FAUX"))
    bad += 0 if ok else 1

    consts = (GC.ability(ABILITY) or {}).get("constants", {})
    movement, chance = consts.get("movement"), consts.get("chance")
    ok = str(movement) == "3" and str(chance) == "30"
    print("   constants = movement=%s chance=%s -> %s" % (movement, chance, "OK" if ok else "FAUX"))
    bad += 0 if ok else 1

    # Le gate, balaye sur toutes les valeurs du canal. `None` = le `Nullable` VIDE du natif, dont
    # `GetValueOrDefault()` rend 0 -> gate FAUX (et non « se taire »).
    trig = FullThrottlePassiveAbility(owner_id=7)
    table = [(None, False), (0, False), (1, False), (2, False), (3, True), (4, True), (9, True)]
    for steps, expect in table:
        ev = TriggerEvent(ev_id, 7, 7, ranged=False, profile=None, movement_steps=steps)
        got = bool(trig.matches(None, ev))
        flag = "OK" if got == expect else "FAUX"
        bad += 0 if got == expect else 1
        print("     movement_steps=%-4s -> matches=%-5s (attendu %-5s) %s"
              % (steps, got, expect, flag))

    # `OwnerIsActor` : un autre acteur ne declenche pas mon passif.
    ev = TriggerEvent(ev_id, 8, 8, ranged=False, profile=None, movement_steps=9)
    got = bool(trig.matches(None, ev))
    print("     actor != owner, steps=9 -> matches=%s (attendu False) %s"
          % (got, "OK" if not got else "FAUX"))
    bad += 0 if not got else 1

    print("   TRIGGERED_ABILITY_BEHAVIOURS[%d] (face DIRECTE #532) toujours inscrit : %s"
          % (FULL_THROTTLE, _behaviour_registered(FULL_THROTTLE)))
    bad += 0 if _behaviour_registered(FULL_THROTTLE) else 1
    return bad


def _behaviour_registered(aid: int) -> bool:
    from engine.runner.abilities.behaviours import TRIGGERED_ABILITY_BEHAVIOURS
    return aid in TRIGGERED_ABILITY_BEHAVIOURS


# ------------------------------------------------------------------ VOLET LIVE
def _rpc_factory():
    from rl_collect_batch import _resolve_session, _rpc

    def rpc(sid, m, args, t=120):
        r = _rpc(sid, m, [args], timeout=t)
        return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}
    return _resolve_session(), rpc


def _build(board: str, seed: int, tag: str, foes: list) -> tuple[int, pathlib.Path]:
    import catalog_inject as CI
    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    state_file = logs / ("p448r1r1_state_%s.json" % tag)
    bc_path = logs / ("p448r1r1_bc_%s.json" % tag)

    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    for uid in GRAFTS:
        CI.graft_passive_ability(bc, uid, ABILITY)
    bc_path.write_text(json.dumps(bc), encoding="utf-8")

    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
           "--board", board, "--p-units", ",".join(GRAFTS),
           "--a-units", ",".join(foes), "--no-ai",
           "--seed-bc", str(bc_path), "--state-file", str(state_file)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        sys.stdout.write((p.stdout or "")[-1500:])
        sys.stdout.write((p.stderr or "")[-1500:])
        raise SystemExit("build KO (%s)" % tag)
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
    return rid, state_file


def _port_state(sid, rpc, rid, board):
    """L'etat du PORT, charge depuis le natif -- c'est lui qui calcule les longueurs de chemin
    (`_num_tiles_moved`, le mirror de `BattleQuery$$GetNumTilesMoved`).

    ⚠ `board=` est OBLIGATOIRE : sans lui `_num_tiles_moved` court-circuite a 0 (`if board is None:
    return 0`) et TOUTES les destinations se liraient a 0 pas -- le probe rendrait alors « 0 essai »
    en silence, ce qu'il a fait au premier jet."""
    from engine.runner.snapshot import load_state
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
    # ⚠ `ability_states=` est OBLIGATOIRE POUR UNE GREFFE. `snapshot._load_passive_abilities`
    # seede `UnitContext.passive_abilities` depuis CE canal ; sans lui il reste `None`, et
    # `collect_triggered_abilities` retombe sur la derivation gameconfig par `visualId` -- ou
    # `orksNob` porte `SmashaEad`, jamais `FullThrottle`. Le passif greffe serait alors INERTE
    # cote port, SANS ERREUR : mesure du premier jet de ce probe, `collect -> 0 instance` et
    # 0 mort sur 200 essais la ou le natif en tue 30 %.
    ast = rpc(sid, "unitAbilityStates", {"runnerId": rid}, 90)
    return load_state(dv, ob, snap, board=board, ability_states=ast), dv, ob


def _alive_map(dv) -> dict:
    """`decisionView.units[].alive`, indexe par `id`.

    ⚠ C'est le canal `decisionView` et PAS `observeBattle` : les deux n'ont pas la meme cle
    d'unite (`decisionView.id` = squadId, `observeBattle.entityId` = entityId -- mesure : le
    tauCrisis rend `id: 77` d'un cote et `entityId: 78, squadId: 77` de l'autre), et `toActivate`
    est exprime dans la numerotation de `decisionView`. Melanger les deux ferait lire l'etat
    d'une AUTRE unite."""
    out = {}
    for u in (dv.get("units") or []):
        uid = u.get("id")
        if uid is not None:
            out[int(uid)] = bool(u.get("alive"))
    return out


def _carriers(dv) -> set:
    """Les unites qui portent REELLEMENT la greffe : `visualId` dans `GRAFTS`. Le canal est la
    liste `decisionView.units[]`, seule a donner le `visualId` sous la meme cle que `toActivate`."""
    return {int(u.get("id")) for u in (dv.get("units") or [])
            if u.get("id") is not None and (u.get("visualId") in GRAFTS)}


def _pick_dest(state, uid: int, legal: set, want_len: int):
    """Une destination LEGALE (le natif l'a listee) dont le chemin de marche fait EXACTEMENT
    `want_len` pas selon le port. Rend `None` s'il n'en existe aucune -- et l'appelant le DIT."""
    from engine.runner.operations.movement import _num_tiles_moved
    from engine.runner.components import PositionComponent
    e = state.get_entity(int(uid))
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is None:
        return None
    src = (pc.col, pc.row)
    for dest in sorted(legal):
        if _num_tiles_moved(state, int(uid), src, dest) == want_len:
            return dest
    return None


def _legal_moves(sid, rpc, rid, uid: int) -> set:
    """Les tuiles ou le NATIF accepte de deplacer `uid` -- canal `aiMovableTiles` (le set de
    repositionnement REEL, creuse par les blockers/le terrain/le BFS ; `decisionView` ne le porte
    pas). C'est ce que `rl_duel moves` affiche."""
    mov = rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    out = set()
    for mu in (mov.get("units") or []):
        if int(mu.get("unitId", -1)) != int(uid):
            continue
        for t in (mu.get("tiles") or []):
            c, r = t.get("col"), t.get("row")
            if c is not None and r is not None:
                out.add((int(c), int(r)))
    return out


def bras(board: str, seed: int, want_len: int, foes: list, max_turns: int) -> dict:
    """Un bras : tous les greffons vivants font un pas de `want_len` hexes, tour apres tour.
    Rend {essais, morts, details}."""
    tag = "L%d_%s_%d" % (want_len, board, seed)
    rid, state_file = _build(board, seed, tag, foes)
    sid, rpc = _rpc_factory()
    print("== BRAS L=%d  board=%s seed=%d  runner=%s" % (want_len, board, seed, rid))
    from engine.entities.pathfinding.board import Board
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 90)
    brd = Board(bg["tiles"], adjacency="native_sym")
    essais, morts, details = 0, 0, []
    try:
        for turn in range(max_turns):
            state, dv, ob = _port_state(sid, rpc, rid, brd)
            alive = _alive_map(dv)
            to_act = [int(u) for u in (dv.get("toActivate") or [])]
            if not to_act:
                print("     t%d : toActivate vide -> fin" % turn)
                break
            carriers = _carriers(dv)
            for uid in to_act:
                if not alive.get(uid, False):
                    continue
                # N'ESSAYER QUE LES PORTEURS. `toActivate` contient aussi l'ADVERSAIRE quand c'est
                # son tour (mesure : `u77 tauCrisis` y apparaissait, et ses pas gonflaient le
                # denominateur d'essais alors qu'il ne porte pas le passif).
                if uid not in carriers:
                    continue
                legal = _legal_moves(sid, rpc, rid, uid)
                state, _, _ = _port_state(sid, rpc, rid, brd)
                dest = _pick_dest(state, uid, legal, want_len)
                if dest is None:
                    details.append({"turn": turn, "unit": uid, "skip": "aucune tuile legale a %d pas"
                                    % want_len})
                    print("     t%d u%s : SKIP -- aucune des %d tuiles legales n'est a %d pas"
                          % (turn, uid, len(legal), want_len))
                    continue
                res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": int(uid),
                    "to": {"col": int(dest[0]), "row": int(dest[1])}}}, 120)
                dv2 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1,
                                                "allAbilities": True}, 150)
                dead = not _alive_map(dv2).get(uid, False)
                essais += 1
                morts += 1 if dead else 0
                details.append({"turn": turn, "unit": uid, "dest": list(dest),
                                "steps": want_len, "dead": dead,
                                "err": (res or {}).get("error")})
                print("     t%d u%s -> %s (%d pas) : %s" % (turn, uid, dest, want_len,
                                                            "MORT" if dead else "vivant"))
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
    return {"len": want_len, "essais": essais, "morts": morts, "details": details,
            "board": board, "seed": seed}


def volet_port(board: str, seed: int, foes: list, lens: list, trials: int) -> dict:
    """VOLET PORT -- la CHAINE COMPLETE cote python, sur le meme etat de depart que le natif.

    L'etape 0 prouve le GATE ; elle ne prouve pas le CABLAGE (que `movementSteps` remonte bien de
    `MoveUnitOperation` jusqu'au trigger a travers `after_move_triggers`). Ici on joue REELLEMENT
    le mouvement cote port -- `MovementHandler.visit_MoveUnitMessage`, le meme chemin que le
    runner -- et on compte les morts sur `trials` graines de PRNG. La frequence attendue est celle
    du natif : 0 % a 1 pas, ~30 % (`chance`) a 2 et 3 pas."""
    import copy
    from engine.entities.pathfinding.board import Board
    from engine.runner.events import EventBus
    from engine.runner.operations.movement import MovementHandler
    from engine.runner.components import UnitComponent
    from engine.runner.prng import IntBasedMersenneTwister

    rid, _sf = _build(board, seed, "port_%s_%d" % (board, seed), foes)
    sid, rpc = _rpc_factory()
    print("== VOLET PORT  board=%s seed=%d  runner=%s (%d graines/bras)"
          % (board, seed, rid, trials))
    out = {}
    try:
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 90)
        brd = Board(bg["tiles"], adjacency="native_sym")
        base, dv, ob = _port_state(sid, rpc, rid, brd)
        carriers = sorted(_carriers(dv))
        for want in lens:
            morts, essais, skipped = 0, 0, 0
            for uid in carriers:
                legal = _legal_moves(sid, rpc, rid, uid)
                dest = _pick_dest(base, uid, legal, want)
                if dest is None:
                    skipped += 1
                    continue
                for t in range(trials):
                    st = copy.deepcopy(base)
                    st.rng = IntBasedMersenneTwister(seed=1000 * want + 7 * t + uid)
                    bus = EventBus()
                    h = MovementHandler(st, bus)

                    class _Msg:                      # le message que le runner poste
                        unit_id = uid
                        to = dest
                    h.visit_MoveUnitMessage(_Msg())
                    e = st.get_entity(int(uid))
                    uc = e.get_component(UnitComponent) if e is not None else None
                    essais += 1
                    morts += 0 if (uc is None or uc.alive) else 1
            pct = (100.0 * morts / essais) if essais else 0.0
            out[want] = {"morts": morts, "essais": essais, "pct": pct, "skipped": skipped}
            print("     L=%d : %d mort(s) / %d essai(s) = %.1f %%  (%d porteur(s) sans tuile a "
                  "cette distance)" % (want, morts, essais, pct, skipped))
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--mutate", action="store_true",
                    help="CONTRE-EPREUVE : neutralise le gate (matches -> True) ; doit ROUGIR")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--foes", default="tauCrisis")
    ap.add_argument("--turns", type=int, default=4)
    ap.add_argument("--lens", default="1,2,3")
    ap.add_argument("--port", action="store_true",
                    help="VOLET PORT : joue les mouvements cote python (chaine complete)")
    ap.add_argument("--mutate-steps", action="store_true",
                    help="CONTRE-EPREUVE du `+1` : `movementSteps = nb de pas` (H_STEPS) au lieu "
                         "de `path.Count`. Avec --port, le bras L=2 doit TOMBER A 0 %% alors que "
                         "le natif y tue 30 %% -- c'est la mesure qui a tranche le seuil.")
    ap.add_argument("--trials", type=int, default=40)
    a = ap.parse_args()

    if a.mutate_steps:
        # H_STEPS : on retire le `+1` qui fait de `movementSteps` un `path.Count`. Le gate ne mord
        # alors qu'a 3 pas -- et le bras L=2 doit s'effondrer a 0 % cote port, la ou le natif
        # mesure 30 %. C'est la contre-epreuve du SEUIL (celle qui garde l'off-by-one), distincte
        # de `--mutate` qui, elle, neutralise le gate entier.
        from engine.runner.operations import movement as MV
        _orig = MV._num_tiles_moved

        def _steps_naif(state, mover_id, from_pos, to_pos):
            return _orig(state, mover_id, from_pos, to_pos)
        MV._movement_steps = _steps_naif
        print("[mutate-steps] H_STEPS : movementSteps = nb de pas (le `+1` de path.Count RETIRE)")

    if a.mutate:
        # Le gate NEUTRALISE = le port qu'on obtiendrait en inscrivant l'ability sans lire son
        # `CreateTrigger` (« toujours vrai »). L'etape 0 doit alors rougir sur les 4 premieres
        # lignes de la table (None/0/1/2 devraient rendre False).
        from engine.runner.operations.triggers.loki import full_throttle as FT
        FT.FullThrottlePassiveAbility.matches = lambda self, state, ev: True
        print("[mutate] gate NEUTRALISE (matches -> True)")

    bad = etape0()
    print("   -> etape 0 : %d anomalie(s)" % bad)
    if a.offline or a.mutate:
        print("VERDICT: %s" % ("FAIL" if bad else "PASS"))
        return 1 if bad else 0

    lens = [int(x) for x in a.lens.split(",") if x.strip()]
    foes = [f for f in a.foes.split(",") if f.strip()]
    if a.port:
        pr = volet_port(a.board, a.seed, foes, lens, a.trials)
        # Le port doit reproduire les DEUX bords : rien a 1 pas, la frequence de `chance` au-dela.
        for L, r in sorted(pr.items()):
            if L <= 1:
                ok = r["morts"] == 0
            else:
                ok = r["essais"] == 0 or (10.0 <= r["pct"] <= 55.0)
            print("   L=%d port %.1f %% -> %s" % (L, r["pct"], "OK" if ok else "ANOMALIE"))
            bad += 0 if ok else 1
        print("VERDICT: %s" % ("FAIL" if bad else "PASS"))
        return 1 if bad else 0
    res = [bras(a.board, a.seed, L, foes, a.turns) for L in lens]

    print("\n== SYNTHESE")
    for r in res:
        print("   L=%d : %d mort(s) / %d essai(s)" % (r["len"], r["morts"], r["essais"]))
    by = {r["len"]: r for r in res}
    verdict = []
    if 1 in by:
        r = by[1]
        okneg = r["morts"] == 0
        verdict.append(("controle NEGATIF (L=1, gate faux sous les 2 hypotheses)", okneg))
    if 2 in by:
        r = by[2]
        print("   -> BRAS DISCRIMINANT L=2 : %d mort(s) / %d essai(s). "
              "H_COUNT (seuil 2 pas) predit ~30%%, H_STEPS (seuil 3 pas) predit 0."
              % (r["morts"], r["essais"]))
    if 3 in by:
        r = by[3]
        okpos = r["morts"] > 0 or r["essais"] == 0
        verdict.append(("controle POSITIF (L=3, gate vrai sous les 2 hypotheses)", okpos))
    for label, ok in verdict:
        print("   %-58s %s" % (label, "OK" if ok else "ANOMALIE"))
    bad += sum(0 if ok else 1 for _, ok in verdict)
    print("VERDICT: %s" % ("FAIL" if bad else "PASS"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
