"""#462-r4e-o-r2-r1-r1-r1 -- QUI joue ensuite : le cycle des joueurs, MESURE puis CALCULE.

QUESTION BINAIRE : dans quel ordre `IdunBattle.Operations.ChangeTurnOperation$$FindNextPlayer`
choisit-il le joueur suivant, et `turnflow.find_next_player` le reproduit-il ?

RE (decompile de `rnca9r7q6c`, VERBATIM des deux corps) :

    ChangeTurnOperation$$FindNextPlayer(matchEntity) :
        if (StateExtensions.IsMatchFinished(state))          return null
        turn    = matchEntity.GetComponent<TurnComponent>()
        players = matchEntity.<IMatchEntity>.<+0x10 : List<...>>        # la BORNE de la boucle
        current = turn.get_CurrentPlayerId()                            # BEntityId
        order   = query.<IBattleQuery slot 0x18 = GetPlayerTurnOrder, arite 0>   # IList<PlayerId>
        index   = FindTurnIndex(current)         # INLINE : position de `PlayerComponent+0x10`
        i = (index.HasValue ? index.Value : -1)
        for (offset = 1 ; offset <= players.Count ; offset++) {
            pid    = order[(i + offset) % order.Count]
            player = StateExtensions.GetPlayer(state, pid)
            if (!query.<IBattleQuery slot 0x1a = ShouldPlayerSkipTurn, arite 1>(player)) break
        }
        return player.Id                                                # null si la borne est atteinte

    ChangeTurnOperation$$Execute() :
        next = FindNextPlayer(matchEntity) ; if (next == 0) return
        prev = turn.get_CurrentPlayerId() ; turn.SetCurrentPlayer(next)   # NO-OP si next == prev
        if (next.GetPlayerComponent().<+0x20 : PlayerType> == 2)          # Environment
            { Execute(this) ; turn.<+0x18> = prev }                       # RECURSION
        return processor.<IOperationProcessor slot 0x14 = VerifyMatchEnd>()

`GetPlayerTurnOrder` est un pur accesseur de CONFIG (`BattleQuery+0xa0 = BattleConfiguration`,
`+0x30`, `+0x18`), soit **`BC.Player.TurnOrder`** -- `[11, 12, 13]` dans le seed BC, l'**Environment
inclus**. L'ordre ne depend donc PAS de qui est vivant : c'est `ShouldPlayerSkipTurn`, DANS la
boucle, qui ecarte un joueur, et la RECURSION d'`Execute` qui ecarte l'Environment.

CE QUE CE PROBE MESURE (aucun capteur neuf -- que des RPC existants) :
  * etape 1 -- LIVE : la suite des `currentPlayer` sur N changements de tour ;
  * etape 2 -- PORT : la MEME suite, CALCULEE depuis l'etat live recharge, et confrontee ;
  * etape 3 -- OFFLINE : les regimes que `rl_duel build` ne monte PAS (>= 3 joueurs, joueur
    ENTIEREMENT mort, joueur courant hors de l'ordre). C'est le SEUL endroit ou les quatre etages
    natifs se separent -- et c'est aussi le seul ou l'ancien port DIVERGEAIT.

⚠ CE QUE LA MESURE A REFUTE. `#462-r4e-o-r2-r1-r1` avait conclu de sa trace que le natif faisait
jouer le meme joueur DEUX TOURS D'AFFILEE (`currentPlayer` 3 -> 3 -> 4 -> 3). Re-mesure ici, meme
seed et meme board, sur 14 changements de tour : **alternance STRICTE**, avant comme apres la mort
d'une unite. Le terme surnumeraire venait d'un changement de tour AUTOMATIQUE
(`IdunBattle.Operations.VerifyAutomaticTurnEndOperation$$Execute`, slot `IOperationProcessor` 0x20)
declenche par l'ATTAQUE, qu'une trace relue seulement APRES chaque `endturn` ne pouvait pas voir.

Usage :
    python scripts/python/probe_462r4eor2r1r1r1_cycle_de_tour.py
        [--state-file <ABSOLU>] [--seed 777] [--tours 14] [--offline-seul] [--mutate <nom>]

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

from engine.runner.state import State                                 # noqa: E402
from engine.runner.operations import turnflow as TF                   # noqa: E402
from engine.runner.components import OwnerComponent, UnitComponent    # noqa: E402

BOARD = "MC1_67"
P_UNITS = "astraBullgryn,tauAunShi"
A_UNITS = "genesPrimus,necroWarden"

_created = []


# =================================================================== volet OFFLINE

def _etat(specs, cur):
    """`State` synthetique : `specs` = [(joueur, nb_vivantes, nb_mortes), ...]."""
    st = State()
    st.current_player_id = cur
    uid = 100
    for pl, vivantes, mortes in specs:
        for alive in ([True] * vivantes) + ([False] * mortes):
            uid += 1
            e = st.add_entity(uid)
            e.add_component(OwnerComponent(team=pl, player=pl))
            e.add_component(UnitComponent(visual_id="u%d" % uid, alive=alive))
    return st


def _port_davant(state):
    """`find_next_player` TEL QU'IL ETAIT avant #462-r4e-o-r2-r1-r1-r1 : les quatre etages natifs
    fondus en un seul cycle sur les joueurs a >= 1 unite VIVANTE, tries. Conserve ici comme TEMOIN
    de la divergence -- c'est le code que la tranche remplace."""
    joueurs = set()
    for e in state.entities.values():
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        if oc is None or oc.player is None:
            continue
        if uc is not None and not uc.alive:
            continue
        joueurs.add(int(oc.player))
    order = sorted(joueurs)
    if not order:
        return None
    cur = state.current_player_id
    if cur not in order:
        return order[0]
    return order[(order.index(cur) + 1) % len(order)]


# `(libelle, specs, courant, attendu_natif)` -- `attendu_natif` est DERIVE du decompile cite en
# tete, etage par etage, jamais du resultat du port.
REGIMES = [
    ("duel, courant 3 vivant",       [(3, 2, 0), (4, 2, 0)],            3, 4),
    ("duel, courant 4 vivant",       [(3, 2, 0), (4, 2, 0)],            4, 3),
    ("duel, camp 4 entierement mort", [(3, 2, 0), (4, 0, 2)],           3, 3),
    ("duel, COURANT 4 mort",         [(3, 2, 0), (4, 0, 2)],            4, 3),
    ("courant absent de l'ordre",    [(3, 2, 0), (4, 2, 0)],            9, 3),
    ("tous les joueurs morts",       [(3, 0, 2), (4, 0, 2)],            3, None),
    ("un seul joueur",               [(3, 2, 0)],                       3, 3),
    ("3 joueurs, tous vivants",      [(3, 2, 0), (4, 2, 0), (5, 2, 0)], 4, 5),
    ("3 joueurs, le 2e mort",        [(3, 2, 0), (4, 0, 2), (5, 2, 0)], 3, 5),
    # LES DEUX REGIMES DE DIVERGENCE. Le joueur COURANT n'a plus d'unite vivante : l'ancien port ne
    # le trouvait plus dans SON ordre (filtre en amont) et repartait de `order[0]` ; le natif, lui,
    # trouve sa position par `FindTurnIndex` -- qui ne consulte AUCUN skip -- et avance depuis elle.
    ("3 joueurs, COURANT 4 mort",    [(3, 2, 0), (4, 0, 2), (5, 2, 0)], 4, 5),
    ("4 joueurs, COURANT 4 et 5 morts",
     [(3, 2, 0), (4, 0, 2), (5, 0, 2), (6, 2, 0)],                      4, 6),
]


def _volet_offline():
    print("\n[offline] les regimes que `rl_duel build` ne monte pas")
    print("  %-36s %-8s %-8s %-8s" % ("regime", "natif", "port", "avant"))
    bad = 0
    divergences = 0
    for libelle, specs, cur, attendu in REGIMES:
        port = TF.find_next_player(_etat(specs, cur))
        avant = _port_davant(_etat(specs, cur))
        marque = ""
        if port != attendu:
            marque = "  <-- PORT != NATIF"
            bad += 1
        elif avant != attendu:
            marque = "  <-- corrige (l'ancien port divergeait)"
            divergences += 1
        print("  %-36s %-8s %-8s %-8s%s" % (libelle, attendu, port, avant, marque))
    print(f"  -> {len(REGIMES)} regimes, {bad} desaccord(s) port/natif, "
          f"{divergences} corrige(s) par cette tranche")
    # UN VOLET QUI NE MONTRE AUCUNE DIVERGENCE NE PROUVE RIEN DE LA CORRECTION : il faut qu'au
    # moins un regime SEPARE l'ancien port du natif, sinon la restructuration serait invisible et
    # ce volet passerait pour vert en ne mesurant rien (le vice du << test vide >>).
    if divergences == 0:
        print("  -> ANOMALIE : aucun regime ne separe l'ancien port du natif")
        bad += 1
    return bad


# =================================================================== volet LIVE

def _live_imports():
    sys.path.insert(0, os.path.join(_HERE, "tests", "engine", "runner"))
    import rl_collect_batch as R                                      # noqa: E402
    from engine.runner.snapshot import load_state                     # noqa: E402
    from engine.entities.pathfinding.board import Board               # noqa: E402
    return R, load_state, Board


def _volet_live(R, load_state, Board, state_file, seed, tours):
    sid = R._resolve_session()

    def _unwrap(x):
        return x.get("result") if isinstance(x, dict) and "result" in x else x

    def _rpc(m, b=None, t=60):
        return _unwrap(R._rpc(sid, m, [b] if b is not None else [], timeout=t))

    def _dv(rid):
        return _rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)

    w = _unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=240))
    print("amorce ok=", isinstance(w, dict) and w.get("ok"), (w or {}).get("skipped") or "")

    args = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", state_file, "--board", BOARD, "--roster", "1",
            "--p-units", P_UNITS, "--a-units", A_UNITS]
    waited = 0.0
    rid = None
    while rid is None:
        try:
            os.unlink(state_file)
        except OSError:
            pass
        p = subprocess.run(args, cwd=_HERE, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if os.path.exists(state_file):
            rid = json.loads(open(state_file).read())["runnerId"]
            _created.append(rid)
            break
        out = (p.stderr or p.stdout or "")
        if ("runner cap reached" not in out and "runner creation paused" not in out) \
                or waited >= 900:
            print("  build KO:", out[-500:])
            return 1
        print(f"  cap/drain, attente 20s ({waited:.0f}/900)")
        time.sleep(20)
        waited += 20

    try:
        bg = _rpc("boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="native_sym") if isinstance(bg, dict) else None
        dv = _dv(rid)
        ob = _rpc("observeBattle", {"runnerId": rid}, 60)
        snap = _rpc("combatSnapshot", {"runnerId": rid}, 60)
        if not all(isinstance(x, dict) and x.get("ok") for x in (dv, ob, snap)):
            print("  capture KO")
            return 1
        st = load_state(dv, ob, snap, board=board)
        print("  joueurs (counts.player) :", (ob.get("counts") or {}).get("player"))
        print("  ordre de tour PORTE     :", TF.player_turn_order(st))
        # PORT : la suite CALCULEE, sur l'etat live de depart. On ne rejoue QUE le changement de
        # tour -- c'est l'etage mesure ; le reste du tour n'y change rien.
        port = [st.current_player_id]
        for _ in range(tours):
            port.append(TF.ChangeTurnOperation.execute(st))
        # LIVE : la suite MESUREE.
        live = [dv.get("currentPlayer")]
        for _ in range(tours):
            _rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            live.append((_dv(rid) or {}).get("currentPlayer"))
        print("  suite LIVE :", live)
        print("  suite PORT :", port)
        if live == port:
            print(f"  -> ACCORD sur {tours} changements de tour")
            return 0
        print("  -> DESACCORD")
        return 1
    finally:
        for r in list(_created):
            try:
                _rpc("disposeRunner", {"runnerId": r}, 30)
            except Exception:
                pass


# =================================================================== mutations

MUTATION_CIBLE = {
    # nom                        observable   ce qu'elle casse
    "ordre-par-joueurs-vivants": "offline",   # le port d'AVANT : ordre filtre par `alive`
    "index-sans-valeur-a-zero":  "offline",   # `Nullable<int>` absent rabattu sur 0 au lieu de -1
    "skip-jamais":               "offline",   # `ShouldPlayerSkipTurn` toujours faux
}


def _mutation(nom):
    if nom == "ordre-par-joueurs-vivants":
        TF.find_next_player = _port_davant
        return ("`find_next_player` repasse au cycle sur les joueurs a unites VIVANTES, tries "
                "(les quatre etages natifs re-fondus en un -- le port d'avant)")
    if nom == "index-sans-valeur-a-zero":
        _vrai = TF.find_turn_index
        TF.find_turn_index = lambda st, p: (0 if _vrai(st, p) is None else _vrai(st, p))
        return ("`find_turn_index` rend 0 au lieu de `None` quand le joueur courant est hors de "
                "l'ordre : l'appelant n'applique plus le `-1` LU dans le decompile")
    if nom == "skip-jamais":
        TF.should_player_skip_turn = lambda st, p: False
        return ("`should_player_skip_turn` rend toujours False : un joueur sans aucune unite "
                "vivante recoit un tour")
    raise SystemExit(f"mutation inconnue: {nom}")


# =================================================================== main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--tours", type=int, default=14)
    ap.add_argument("--offline-seul", action="store_true")
    ap.add_argument("--mutate", default=None, choices=sorted(MUTATION_CIBLE))
    a = ap.parse_args()

    if a.mutate:
        print("MUTATION:", _mutation(a.mutate))

    bad = _volet_offline()
    if not a.offline_seul:
        state_file = a.state_file or os.path.abspath(os.path.join(
            _HERE, "..", "..", "logs", "runners",
            f"_probe462r4eor2r1r1r1_{uuid.uuid4().hex[:8]}_state.json"))
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        R, load_state, Board = _live_imports()
        print("\n[live] la suite des `currentPlayer`, mesuree puis calculee")
        bad += _volet_live(R, load_state, Board, state_file, a.seed, a.tours)

    print("\n--- VERDICT ---")
    if a.mutate:
        # `a_mordu` est SEPARE du verdict : une mutation qui ne mord pas se DECLARE, elle ne compte
        # pas verte. Les trois mutations visent l'observable `offline` -- c'est le seul volet ou
        # les quatre etages se separent, le live etant une alternance stricte a deux camps.
        mordu = bad > 0
        print(f"  mutation `{a.mutate}` (observable `{MUTATION_CIBLE[a.mutate]}`) -- "
              f"a_mordu : {mordu}")
        print(f"VERDICT: {'PASS' if mordu else 'FAIL'} "
              f"({'diverge, attendu' if mordu else 'IDENTIQUE SOUS MUTATION'})")
        return 0 if mordu else 1
    print(f"VERDICT: {'PASS' if bad == 0 else 'FAIL'} ({bad} anomalie(s))")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
