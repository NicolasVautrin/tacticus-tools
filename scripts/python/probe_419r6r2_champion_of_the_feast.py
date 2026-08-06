"""#419-r6-r2 -- `ChampionOfTheFeast` (`TriggeredAbilityType` 0x43e = 1086), le passif de
`templSwordBrother` << Sword Brother Godswyl >>, CONFRONTE AU LIVE.

CE QUE CE PROBE MESURE. Le passif n'etait dans AUCUN des quatre registres de trigger : offline,
Godswyl terminait son activation SANS frapper l'ennemi adjacent et SANS lui poser son malus
d'armure -- ni erreur, ni crash.

CRITERE BINAIRE, sur DEUX observables INDEPENDANTS : quand Godswyl termine son activation a cote
d'un ennemi damageable,
  (a) cet ennemi PERD-il des PV -- du MEME montant live et offline ?
  (b) son `FixedArmor` BAISSE-t-il -- du MEME montant (`-armorReduction[lvl] x mult`) des deux cotes ?
  (c) et, quand PLUSIEURS ennemis sont adjacents, est-ce LE MEME qui est frappe ?

Le montage DISCRIMINE par construction : avant le port, le cote PORT rend `0` sur les DEUX axes
pendant que le natif rend du non-nul. Un accord a zero des deux cotes ne prouverait rien -- c'est
pourquoi `run()` publie `temoin_natif_non_nul` et que les assertions le REQUIERENT.

⚠ LE POOL A UNE SEULE CIBLE EST UN REGIME DEGENERE. Avec un seul ennemi adjacent, ni le
`PickRandomly` ni l'`Otherwise` du natif ne peuvent diverger : n'importe quel port qui frappe
« l'ennemi adjacent » passe. `--prefer-multi` (defaut) cherche donc EN PRIORITE une tuile libre
adjacente a **au moins deux** ennemis, et `run()` publie `pool_size` pour que l'appelant sache dans
quel regime il a mesure.

MONTAGE. Les positions sont CONDUITES (jamais « bloque par la geometrie de spawn ») : on cherche une
tuile LIBRE adjacente a un (ou deux) ennemi(s) et on y DEPLACE Godswyl. C'est ce deplacement qui
publie `On(0x1c = ArrivedAtFinalTile)` (`IdunBattle.Operations.MoveUnitOperation$$Execute`).

DEUX PIEGES DE HARNAIS, tous deux mesures ici et nommes a leur point d'usage :
  * `Runner.apply(MoveUnitMessage(...))` NE ROUTE PAS le move hors boucle de tour -- la position
    reste inchangee, et le probe conclurait « port inerte » pour une raison de HARNAIS. La voie est
    `MovementHandler.visit_MoveUnitMessage` (le chemin du mouvement JOUEUR porte).
  * `AttackDamageOperation.execute_ability_attack` SKIP le degat (`return None`) quand `state.rng`
    n'est pas cale. D'ou le `dumpRng` de `_capture` -- qui sert de toute facon au `PickRandomly`.

ASCII only (console cp1252).

    python probe_419r6r2_champion_of_the_feast.py [--board MC1_67] [--seed 777] [--no-prefer-multi]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.entities.pathfinding.board import Board                    # noqa: E402
from engine.entities.stats import StatPart, StatType                   # noqa: E402
from engine.runner.components import HealthComponent, StatsComponent   # noqa: E402
from engine.runner.messages import MoveUnitMessage                     # noqa: E402
from engine.runner.snapshot import load_state                          # noqa: E402

CASTER_VIS = "templSwordBrother"          # << Sword Brother Godswyl >>, le SEUL porteur lineup
BOARD = "MC1_67"
SEED = 777
P_UNITS = "templSwordBrother,templAggressor"
A_UNITS = "templChampion,templAncient"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _unwrap(r):
    if isinstance(r, dict) and "result" in r:
        return r["result"]
    return r


def _live_units(rpc, rid):
    r = rpc("observeBattle", {"runnerId": rid}, 40)
    return {u["squadId"]: u for u in (r.get("units") or [])} if _ok(r) else {}


def _by_vis(state, vis):
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
            return uid
    return None


def _capture(rpc, rid, board):
    """Capture l'etat offline ET CALE LE PRNG sur l'etat MT live (`dumpRng`).

    Le calage n'est PAS cosmetique ici, pour DEUX raisons : le behaviour porte un `PickRandomly`
    (1 tirage par fire), et `execute_ability_attack` REFUSE d'infliger le degat sur un rng non cale
    (cf. l'en-tete du module)."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        return None
    state = load_state(dv, ob, snap, board=board)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if isinstance(s0, dict) and s0.get("mt"):
        from engine.runner.prng import IntBasedMersenneTwister
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        state.rng = rng
    return state


def _hp(state, uid):
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return int(hc.hp) if hc is not None else None


def _armor(state, uid, part=StatPart.CURRENT):
    e = state.get_entity(uid)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return None
    return int(sc.ctx.get_stat(int(StatType.FIXED_ARMOR), int(part)) or 0)


def _adjacency_count(board, tile, enemy_tiles):
    from engine.runner.operations.triggers.base import _hex_dist
    return sum(1 for t in enemy_tiles if _hex_dist(board, tile, t, 1) == 1)


def _destination_candidates(board, occupied, enemy_tiles, exclude, prefer_multi=True):
    """Tuiles LIBRES marchables adjacentes a >= 1 ennemi, TRIEES par nombre d'ennemis adjacents
    DECROISSANT. CONDUIT la position -- le montage ne SUBIT jamais la geometrie de spawn.

    `prefer_multi` privilegie les tuiles a >= 2 ennemis adjacents : c'est le SEUL regime ou le
    `PickRandomly`/`Otherwise` natif peut diverger du port (cf. l'en-tete).

    ⚠ On rend une LISTE, pas un candidat unique : `walkable` + adjacence ne suffisent PAS a
    garantir que le natif ACCEPTE le move (pathfinding, elevation, reservation). Mesure du
    2026-08-06 sur `MC1_63` : la meilleure tuile (0,5) etait libre et adjacente a DEUX ennemis, et
    le natif a laisse Godswyl sur son spawn -- le probe concluait alors « temoin nul » pour une
    raison de GEOMETRIE. L'appelant essaie donc les candidates dans l'ordre jusqu'a ce qu'un move
    ABOUTISSE."""
    scored = []
    for t in board.by_id:
        if t in occupied or t in exclude or not board.walkable(t):
            continue
        n = _adjacency_count(board, t, enemy_tiles)
        if n < 1:
            continue
        scored.append(((n if prefer_multi else 1), t, n))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [(t, n) for _, t, n in scored]


def _build(seed, board_id, p_units, a_units, state_file, move=25):
    """`--unit-stat <vis>:Movement=<n>` CONDUIT la position : sur les boards 5v5 les spawns sont a
    ~8 hex et Godswyl a `Movement=3` -- le move live serait CLAMPE avant l'adjacence, et le probe
    mesurerait « pas de fire » pour une raison de GEOMETRIE, pas de port. On lui donne la portee
    d'atteindre l'ennemi EN UN MOVE (meme levier que
    `test_462_..._crush_death_events_live.py`). Cela ne touche NI le passif NI l'armure."""
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board_id,
           "--state-file", state_file, "--p-units", p_units, "--a-units", a_units,
           "--unit-stat", "%s:Movement=%d" % (CASTER_VIS, move)]
    r = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)),
                       capture_output=True, text=True, timeout=600)
    if not os.path.exists(state_file):
        return None, "BUILD KO rc=%s\n%s\n%s" % (r.returncode, (r.stdout or "")[-1200:],
                                                 (r.stderr or "")[-1200:])
    with open(state_file, encoding="utf-8") as fh:
        return json.load(fh).get("runnerId"), None


def run(board_id=BOARD, seed=SEED, p_units=P_UNITS, a_units=A_UNITS,
        state_file=None, prefer_multi=True, keep=False) -> dict:
    """Monte UN runner, CONDUIT Godswyl au contact, mesure les deux cotes, DISPOSE le runner.

    Rend un dict de mesure (jamais d'assertion ici -- un probe MESURE, un test GARDE)."""
    sf = state_file or os.path.join(tempfile.gettempdir(), "st_419r6r2_probe.json")
    import rl_collect_batch as R
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    out: dict = {"ok": False, "err": None, "board": board_id, "seed": seed}
    rid, err = _build(seed, board_id, p_units, a_units, sf)
    if rid is None:
        out["err"] = err
        return out
    out["runner"] = rid
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym") if bg and bg.get("tiles") else None
        if board is None:
            out["err"] = "boardGraph indispo"
            return out

        U = _live_units(rpc, rid)
        sq_c = next((sq for sq, u in U.items() if u.get("visualId") == CASTER_VIS), None)
        if sq_c is None:
            out["err"] = "caster %s absent live" % CASTER_VIS
            return out
        # `observeBattle` publie l'appartenance sous `teamId` (et `playerId`), PAS `team`.
        c_team = U[sq_c].get("teamId")
        enemies = [sq for sq, u in U.items()
                   if u.get("teamId") != c_team and not u.get("isDead")]
        if not enemies:
            out["err"] = "aucun ennemi live"
            return out

        occupied = {board.id_at(u["col"], u["row"]) for u in U.values()}
        c_tile = board.id_at(U[sq_c]["col"], U[sq_c]["row"])
        enemy_tiles = {sq: board.id_at(U[sq]["col"], U[sq]["row"]) for sq in enemies}
        cands = _destination_candidates(board, occupied, set(enemy_tiles.values()),
                                        exclude={c_tile}, prefer_multi=prefer_multi)
        if not cands:
            out["err"] = "aucune tuile libre adjacente a un ennemi"
            return out
        out["candidates"] = len(cands)

        # --- capture PRE-move : l'etat COMMUN aux deux cotes ---------------------------------
        state = _capture(rpc, rid, board)
        if state is None:
            out["err"] = "capture pre-move KO"
            return out
        cid = _by_vis(state, CASTER_VIS)
        if cid is None:
            out["err"] = "caster absent offline"
            return out
        # On suit TOUS les ennemis : c'est ce qui permet de dire QUI a ete frappe (axe (c)).
        vis_by_sq = {sq: U[sq].get("visualId") for sq in enemies}
        tids = {sq: _by_vis(state, vis_by_sq[sq]) for sq in enemies}
        before = {sq: (_hp(state, tids[sq]), _armor(state, tids[sq]))
                  for sq in enemies if tids[sq] is not None}
        out["before"] = {str(sq): before[sq] for sq in before}

        from engine.runner.operations.triggers.loki.champion_of_the_feast import armor_reduction
        out["armor_reduction_attendu"] = armor_reduction(state, cid)

        # --- LIVE : le move publie On(0x1c), le natif fire -----------------------------------
        # On essaie les candidates DANS L'ORDRE et on RELIT toujours la position atteinte : le
        # natif peut refuser le move ou clamper la destination (cf. `_destination_candidates`).
        # Un montage ou l'unite N'A PAS BOUGE ne publie AUCUN `On(0x1c)` -- c'est une panne de
        # GEOMETRIE, et elle doit se dire comme telle, pas se deguiser en « temoin nul ».
        dest = reached = None
        for cand, n_adj in cands:
            ccol, crow = board.coord(cand)
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": sq_c, "to": {"col": ccol, "row": crow}}}, 60)
            U2 = _live_units(rpc, rid)
            if sq_c not in U2:
                out["err"] = "le caster a disparu apres le move"
                return out
            got = board.id_at(U2[sq_c]["col"], U2[sq_c]["row"])
            if got != c_tile:                       # l'unite A bouge -> `On(0x1c)` a ete publie
                dest, reached = cand, got
                out["pool_size"] = _adjacency_count(board, got, set(enemy_tiles.values()))
                out["dest"] = board.coord(cand)
                out["reached"] = board.coord(got)
                break
        if reached is None:
            out["err"] = ("aucune des %d tuiles candidates n'a ete atteinte par le natif "
                          "(l'unite est restee sur son spawn) -- panne de GEOMETRIE, pas de port"
                          % len(cands))
            return out
        if (out.get("pool_size") or 0) < 1:
            out["err"] = ("le natif a clampe le move sur une tuile SANS ennemi adjacent "
                          "(%s) -- montage non discriminant" % (out.get("reached"),))
            return out
        after_live_state = _capture(rpc, rid, board)
        if after_live_state is None:
            out["err"] = "capture post-move KO"
            return out
        live = {}
        for sq in before:
            t = _by_vis(after_live_state, vis_by_sq[sq])
            live[sq] = (before[sq][0] - (_hp(after_live_state, t) or 0),
                        before[sq][1] - (_armor(after_live_state, t) or 0))
        out["delta_live"] = {str(sq): live[sq] for sq in live}

        # --- PORT : rejouer le MEME move sur l'etat PRE-move ---------------------------------
        # Voie = `MovementHandler.visit_MoveUnitMessage`, le chemin du mouvement JOUEUR porte,
        # le MEME que traverse `AiControl$$ApplyAiMessages`. C'est lui qui publie
        # `On(0x1c = ArrivedAtFinalTile)` en fin d'`Execute`. NE PAS passer par `Runner.apply`
        # (cf. l'en-tete : le message n'est pas route hors boucle de tour).
        # ⚠ On rejoue vers la tuile REELLEMENT ATTEINTE par le natif (`reached`), jamais vers la
        # destination DEMANDEE : le natif peut clamper, et comparer deux positions differentes
        # ferait diverger les deux cotes pour une raison qui n'est pas le passif.
        from engine.runner.events import EventBus
        from engine.runner.operations.movement import MovementHandler
        handler = MovementHandler(state, EventBus())
        handler.visit_MoveUnitMessage(MoveUnitMessage(unit_id=cid, to=board.coord(reached)))
        out["fire"] = handler.after_move or []
        port = {}
        for sq in before:
            port[sq] = (before[sq][0] - (_hp(state, tids[sq]) or 0),
                        before[sq][1] - (_armor(state, tids[sq]) or 0))
        out["delta_port"] = {str(sq): port[sq] for sq in port}

        # --- verdicts ------------------------------------------------------------------------
        # TEMOIN : au moins un ennemi a REELLEMENT bouge cote natif, sur l'un des deux axes.
        out["temoin_natif_non_nul"] = any(d[0] or d[1] for d in live.values())
        out["accord_hp"] = all(live[sq][0] == port[sq][0] for sq in before)
        out["accord_armure"] = all(live[sq][1] == port[sq][1] for sq in before)
        # AXE (c) : la cible FRAPPEE est-elle la meme ? (celle dont l'armure a baisse)
        out["cible_live"] = sorted(str(sq) for sq in live if live[sq][1])
        out["cible_port"] = sorted(str(sq) for sq in port if port[sq][1])
        out["accord_cible"] = out["cible_live"] == out["cible_port"]
        out["ok"] = bool(out["temoin_natif_non_nul"] and out["accord_hp"]
                         and out["accord_armure"] and out["accord_cible"])
        return out
    finally:
        if not keep:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 30)
            except Exception as exc:                       # noqa: BLE001
                out.setdefault("dispose_err", type(exc).__name__)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--p-units", dest="p_units", default=P_UNITS)
    ap.add_argument("--a-units", dest="a_units", default=A_UNITS)
    ap.add_argument("--state-file", dest="state_file", default=None)
    ap.add_argument("--no-prefer-multi", dest="prefer_multi", action="store_false",
                    help="ne PAS chercher une tuile adjacente a >= 2 ennemis (regime DEGENERE)")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    m = run(board_id=args.board, seed=args.seed, p_units=args.p_units, a_units=args.a_units,
            state_file=args.state_file, prefer_multi=args.prefer_multi, keep=args.keep)
    if m.get("err"):
        print("KO : %s" % m["err"])
        return 1
    print("runner=%s board=%s seed=%s ; pool adjacent = %s ennemi(s) ; dest=%s atteinte=%s "
          "(%s candidates)" % (m.get("runner"), m["board"], m["seed"], m.get("pool_size"),
                               m.get("dest"), m.get("reached"), m.get("candidates")))
    print("armorReduction attendu = %s" % m.get("armor_reduction_attendu"))
    for sq in sorted(m.get("before") or {}):
        print("  squad %s : avant hp/armor=%s | natif d=%s | port d=%s"
              % (sq, (m["before"] or {}).get(sq), (m["delta_live"] or {}).get(sq),
                 (m["delta_port"] or {}).get(sq)))
    print("-" * 90)
    if not m.get("temoin_natif_non_nul"):
        print("INCONCLUANT : temoin natif NUL -- un accord a zero ne prouve rien.")
        return 1
    print("temoin natif NON NUL : OK")
    print("accord PV      : %s" % ("OK" if m["accord_hp"] else "DIVERGE"))
    print("accord ARMURE  : %s" % ("OK" if m["accord_armure"] else "DIVERGE"))
    print("accord CIBLE   : %s  (live=%s port=%s)"
          % ("OK" if m["accord_cible"] else "DIVERGE", m["cible_live"], m["cible_port"]))
    if (m.get("pool_size") or 0) < 2:
        print("NOTE : pool = %s -> regime DEGENERE, le PickRandomly/Otherwise n'est PAS discrimine."
              % m.get("pool_size"))
    return 0 if m["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
