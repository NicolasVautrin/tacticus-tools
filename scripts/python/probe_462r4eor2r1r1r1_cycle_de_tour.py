"""#462-r4e-o-r2-r1-r1-r1 -- QUI joue ensuite : mesurer le CYCLE des joueurs du natif.

QUESTION BINAIRE : dans quel ordre `IdunBattle.Operations.ChangeTurnOperation$$FindNextPlayer`
choisit-il le joueur suivant, et `turnflow.find_next_player` le reproduit-il ?

RE (decompile de `rnca9r7q6c`, VERBATIM des deux corps) :

    ChangeTurnOperation$$FindNextPlayer(matchEntity) :
        if (StateExtensions.IsMatchFinished(state))          return null
        turn      = matchEntity.GetComponent<TurnComponent>()
        players   = matchEntity.<IMatchEntity>.<...>.Players       // borne de la boucle
        current   = turn.get_CurrentPlayerId()                     // BEntityId
        order     = query.<IBattleQuery slot 0x18 = GetPlayerTurnOrder(), 0 arg>   // IList<PlayerId>
        index     = FindTurnIndex(current)          // INLINE : order.IndexOf(PlayerComponent+0x10)
        i = (index.HasValue ? index.Value : -1)
        for (offset = 1 ; offset <= players.Count ; offset++) {
            pid    = order[(i + offset) % order.Count]
            player = StateExtensions.GetPlayer(state, pid)
            if (!query.<IBattleQuery slot 0x1a = ShouldPlayerSkipTurn(player), 1 arg>) break
        }
        return player.Id            // null si la boucle epuise `players.Count`

    ChangeTurnOperation$$Execute() :
        next = FindNextPlayer(matchEntity) ; if (next == 0) return
        prev = turn.get_CurrentPlayerId() ; turn.SetCurrentPlayer(next)
        if (next.GetPlayerComponent().<+0x20 : PlayerType> == 2)   // Environment
            { Execute(this) ; turn.<+0x18> = prev }                 // RECURSION
        return processor.<IOperationProcessor slot 0x14 = VerifyMatchEnd>()

CE QUE LE PORT FAISAIT : `find_next_player` cyclait sur `sorted(joueurs ayant >= 1 unite vivante)`,
donc ALTERNAIT entre les deux camps. Le natif, lui, indexe un ORDRE LU DANS LA BC
(`BC.Player.TurnOrder`, seed BC = `[11, 12, 13]` -- l'Environment EN FAIT PARTIE), et l'Environment
est ecarte non pas par `FindNextPlayer` mais par la RECURSION d'`Execute`.

CE QUE CE PROBE MESURE (aucun capteur neuf -- que des RPC existants) :
  * etape 1 : la SUITE des `currentPlayer` sur N changements de tour, sur un montage 2 camps ;
  * etape 2 : la MEME suite, calculee par le PORT depuis l'etat live recharge, joueur par joueur ;
  * etape 3 : la suite du port apres la mort de TOUTES les unites d'un camp (regime ou l'ancien
    port et le nouveau divergent le plus : l'ancien EXCLUAIT le camp vide de l'ordre).

`--mutate` : contre-epreuves du foyer. Chacune DECLARE son observable.

Usage :
    python scripts/python/probe_462r4eor2r1r1r1_cycle_de_tour.py
        [--state-file <ABSOLU>] [--seed 777] [--tours 10] [--mutate <nom>]

ASCII only. Dispose ses runners.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "tests", "engine", "runner"))
import rl_collect_batch as R                                          # noqa: E402

from engine.runner.snapshot import load_state                         # noqa: E402
from engine.runner.operations import turnflow as TF                   # noqa: E402
from engine.entities.pathfinding.board import Board                   # noqa: E402
from engine.runner.components import OwnerComponent, UnitComponent    # noqa: E402

_SID = R._resolve_session()
_created = []

BOARD = "MC1_67"
P_UNITS = "astraBullgryn,tauAunShi"
A_UNITS = "genesPrimus,necroWarden"


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _rpc(method, body=None, timeout=60):
    return _unwrap(R._rpc(_SID, method, [body] if body is not None else [], timeout=timeout))


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _build(state_file, seed, cap_wait_s=900, poll_s=20):
    args = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", state_file, "--board", BOARD, "--roster", "1",
            "--p-units", P_UNITS, "--a-units", A_UNITS]
    waited = 0.0
    while True:
        try:
            os.unlink(state_file)
        except OSError:
            pass
        p = subprocess.run(args, cwd=_HERE, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if os.path.exists(state_file):
            rid = json.loads(open(state_file).read())["runnerId"]
            _created.append(rid)
            return rid
        out = (p.stderr or p.stdout or "")
        if ("runner cap reached" not in out and "runner creation paused" not in out) \
                or waited >= cap_wait_s:
            raise RuntimeError(f"build KO: {out[-800:]}")
        print(f"  cap/drain, attente {poll_s}s ({waited:.0f}/{cap_wait_s})")
        time.sleep(poll_s)
        waited += poll_s


def _dv(rid):
    return _rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _capture(rid, board):
    dv = _dv(rid)
    ob = _rpc("observeBattle", {"runnerId": rid}, 60)
    snap = _rpc("combatSnapshot", {"runnerId": rid}, 60)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        return None
    return {"dv": dv, "ob": ob, "snap": snap,
            "state": load_state(dv, ob, snap, board=board)}


def _endturn(rid):
    return _rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)


# ------------------------------------------------------------------ mutations

MUTATION_CIBLE = {
    # nom                        observable      ce qu'elle casse
    "ordre-par-joueurs-actifs": "suite",     # le port d'AVANT : cycle sur les joueurs VIVANTS tries
    "sans-environnement":       "suite",     # l'Environment retire de l'ordre de tour
    "sans-recursion":           "suite",     # `Execute` ne recurse plus sur PlayerType == 2
}


def _mutation(nom):
    if nom == "ordre-par-joueurs-actifs":
        # LE PORT D'AVANT #462-r4e-o-r2-r1-r1-r1 : ordre = joueurs a >= 1 unite vivante, tries.
        def _avant(state):
            order = TF._active_players(state)
            if not order:
                return None
            cur = state.current_player_id
            if cur not in order:
                return order[0]
            return order[(order.index(cur) + 1) % len(order)]
        TF.find_next_player = _avant
        return "`find_next_player` repasse au cycle sur les JOUEURS ACTIFS tries (port d'avant)"
    if nom == "sans-environnement":
        # L'ordre de tour perd l'Environment : la boucle native ne le traverse plus, donc le
        # `PlayerType == 2` d'`Execute` ne recurse jamais.
        _orig = TF.player_turn_order

        def _sans_env(state):
            return [p for p in _orig(state) if not TF.is_environment_player(state, p)]
        TF.player_turn_order = _sans_env
        return "`player_turn_order` exclut l'Environment (l'ordre de tour de la BC l'INCLUT)"
    if nom == "sans-recursion":
        _orig = TF.is_environment_player
        TF.is_environment_player = lambda state, pid: False
        del _orig
        return ("`is_environment_player` rend toujours False : `ChangeTurnOperation` ne recurse "
                "plus, l'Environment devient un joueur ordinaire")
    raise SystemExit(f"mutation inconnue: {nom}")


# ------------------------------------------------------------------ mesure

def _joueurs(cap):
    """Recense, depuis l'etat live recharge, les joueurs porteurs d'unites et leur vivacite."""
    st = cap["state"]
    out = {}
    for uid, e in st.entities.items():
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        if oc is None or oc.player is None:
            continue
        d = out.setdefault(int(oc.player), {"unites": 0, "vivantes": 0})
        d["unites"] += 1
        if uc is None or uc.alive:
            d["vivantes"] += 1
    return out


def _suite_live(rid, tours):
    """La suite MESUREE des `currentPlayer`, un `applyAction endturn` par pas."""
    suite = [(_dv(rid) or {}).get("currentPlayer")]
    for _ in range(tours):
        _endturn(rid)
        suite.append((_dv(rid) or {}).get("currentPlayer"))
    return suite


def _suite_port(cap, tours):
    """La MEME suite, CALCULEE par le port depuis l'etat live de depart. On ne rejoue que le
    changement de tour (`ChangeTurnOperation`), pas le tour entier : c'est l'etage mesure."""
    st = cap["state"]
    suite = [st.current_player_id]
    for _ in range(tours):
        nxt = TF.ChangeTurnOperation.execute(st)
        suite.append(nxt)
    return suite


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--tours", type=int, default=10)
    ap.add_argument("--mutate", default=None, choices=sorted(MUTATION_CIBLE))
    a = ap.parse_args()

    state_file = a.state_file or os.path.abspath(os.path.join(
        _HERE, "..", "..", "logs", "runners",
        f"_probe462r4eor2r1r1r1_{uuid.uuid4().hex[:8]}_state.json"))
    os.makedirs(os.path.dirname(state_file), exist_ok=True)

    if a.mutate:
        print("MUTATION:", _mutation(a.mutate))

    w = _unwrap(R._rpc(_SID, "warmupGameSingletons", [{}], timeout=240))
    print("warmup ok=", isinstance(w, dict) and w.get("ok"), (w or {}).get("skipped") or "")

    rc = 1
    try:
        rid = _build(state_file, a.seed)
        bg = _rpc("boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="native_sym") if isinstance(bg, dict) else None
        cap = _capture(rid, board)
        if cap is None:
            print("VERDICT: FAIL (capture KO)")
            return 1
        print("joueurs (depuis l'etat live) :", _joueurs(cap))
        print("turn_order porte             :", TF.player_turn_order(cap["state"]))
        print("environnement porte          :", TF.environment_players(cap["state"]))
        port = _suite_port(cap, a.tours)
        live = _suite_live(rid, a.tours)
        print("suite LIVE :", live)
        print("suite PORT :", port)
        accord = (live == port)
        if a.mutate:
            ok = not accord
            print(f"\n--- VERDICT (mutation `{a.mutate}`, observable "
                  f"`{MUTATION_CIBLE[a.mutate]}`) ---")
            print("  a_mordu :", ok)
            print(f"VERDICT: {'PASS' if ok else 'FAIL'} "
                  f"({'la mutation diverge, attendu' if ok else 'IDENTIQUE SOUS MUTATION'})")
            rc = 0 if ok else 1
        else:
            print("\n--- VERDICT ---")
            print(f"VERDICT: {'PASS' if accord else 'FAIL'} "
                  f"(suite live {'==' if accord else '!='} suite port)")
            rc = 0 if accord else 1
    finally:
        for rid in list(_created):
            try:
                _rpc("disposeRunner", {"runnerId": rid}, 30)
            except Exception:
                pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
