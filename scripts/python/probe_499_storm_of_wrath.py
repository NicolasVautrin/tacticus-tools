"""Probe #499 -- `1019 StormOfWrath` (ultraTigurius) : la CHAINE, mesuree LIVE contre le port.

CE QUE CE PROBE MESURE, ET POURQUOI CES REGIMES-LA
--------------------------------------------------
`IdunBattleLogic.Entities.Abilities.Active.Loki.StormOfWrathAbility$$ExecuteBehaviour` construit un
`IdunBattleLogic.Entities.DSLBehaviors$$ChainAbilityDamage` : la cible encaisse un coup, puis la
chaine saute jusqu'a `maxAdjacentTargets` fois vers UN ennemi tire au sort parmi ceux qui touchent
un maillon deja frappe. QUATRE regimes, et chacun tombe pour une raison DIFFERENTE si le port est
faux :

  [A] REGIME CHAINE  -- N maillons mutuellement adjacents -> le natif frappe la cible **et** les
      maillons. Un port qui n'aurait porte que le coup principal (le patron « ability = attaque
      mono-cible ») rendrait 1 unite au lieu de N.
  [B] REGIME COUPE   -- MEMES unites, MEME roster, mais les autres ennemis places HORS adjacence :
      la chaine ne peut pas partir -> **1 seule** unite frappee. C'est le contre-cas qui interdit
      un forfait « toujours N unites » : le nombre frappe CHANGE avec la seule geometrie.
  [C] REGIME GRAPPE  -- la cible a PLUSIEURS voisins libres, donc le `PickRandomly(cand, 1)` a un
      VRAI CHOIX a chaque saut (pool 3, puis 2, puis 1). SANS CE REGIME l'accord de [A] serait
      DEGENERE : en ligne il n'y a qu'UN candidat par pas, et ni le tirage ni son ordre ne seraient
      exerces. Mesure du 2026-08-07 : l'ordre rendu est `77, 81, 79, 83` -- **pas** celui des ids.
  [D] REGIME BLOCK   -- meme geometrie que [A] avec `--block-target 100,500`. Attention, c'est une
      contre-epreuve NEGATIVE et non l'exercice du block : la famille de degat est bien ABILITY
      (`IdunBattle.Operations.AbilityDamageOperation`, LU dans le `.ctor` de
      `ChainAbilityDamageBehaviour`), donc pas de crit et un block qui, EN GENERAL, mord -- mais le
      profil de 1019 est `Psychic`, qui porte `DamageTrait.NoBlocking`
      (`AttackDamageOperation._block_sources`, gate #65). MESURE : avec `BlockChance = 100` sur les
      cibles, **personne** ne bloque, ni le natif ni le port, et le flux RNG est IDENTIQUE au regime
      sans block -- aucun tirage de block n'a meme ete consomme. Le temoin `BlockChance > 0` est
      rendu par la sortie et ASSERTIONNE par la garde : sans lui, « aucun block observe » serait un
      vert qui ment.

Dans les quatre cas la comparaison est PER-COUP et PAR CIBLE : `Amount` des evenements live filtres
sur `Active_Ability_Type == 1019`, contre le `per_hit` du diagnostic offline. Un scalaire fitte ne
peut passer ni [A] et [B] ensemble (le CARDINAL change), ni [A] et [C] ensemble (l'ORDRE du tirage
et les valeurs qui en decoulent changent).

CONFONDS NEUTRALISES AU BUILD : `--hp-target` eleve (cibles a ARMURE NULLE qui SURVIVENT, donc la
chaine n'est pas coupee par une mort et le degat net est lisible), `--crit 0,0` (la famille ABILITY
n'a de toute facon pas de slot crit, mais on ne laisse pas le hasard decider), `--block-target 0,0`
hors regime [D], `--no-ai`.

ASCII only (cp1252). Usage :
    python probe_499_storm_of_wrath.py                 # les quatre regimes
    python probe_499_storm_of_wrath.py --regime grappe
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import gameconfig as GC                                     # noqa: E402
from engine.entities.pathfinding.board import Board         # noqa: E402
from engine.runner.components import StatsComponent         # noqa: E402
from engine.runner.messages import ActiveAbilityMessage     # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister      # noqa: E402
from engine.runner.runner import Runner                     # noqa: E402
from engine.runner.snapshot import load_state               # noqa: E402

STORM_OF_WRATH = 1019
TIGURIUS = "ultraTigurius"
ENEMIES = "orksNob,orksWarboss,orksBigMek,orksRuntherd"
CHAIN_LEN = 3            # cible + 2 maillons -- tient sur MC1_67 et reste sous `maxAdjacentTargets`


def _rpc(sid, m, b=None, t=60):
    r = R._rpc(sid, m, [b] if b is not None else [], timeout=t)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _build(state_file, seed, board, extra):
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", state_file, *extra]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    sf = Path(state_file)
    if not sf.exists():
        return None, (p.stderr or p.stdout or "")[-1200:]
    return json.loads(sf.read_text())["runnerId"], None


def _upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def live_hits(res, ability=STORM_OF_WRATH):
    """[(target_id, amount)] des coups de `ability` dans la reponse d'`applyAction`, DANS L'ORDRE."""
    out = []
    for a in (res.get("actions") or []):
        for e in (a.get("events") or []):
            td = e.get("tags")
            if isinstance(td, str):
                td = json.loads(td)
            if not td:
                continue
            if td.get("Active_Ability_Type") == ability and "Amount" in td:
                out.append((td["Target_Id"], td["Amount"]))
    return out


def off_seq(diag):
    """per-coup du diagnostic `StormOfWrathAbility.execute_behaviour`, dans l'ordre joue."""
    out = []
    main = diag.get("main_attack") or {}
    out += [(diag.get("target"), a) for a in (main.get("per_hit") or [])]
    for s in (diag.get("chain") or []):
        out += [(s.get("target"), a) for a in ((s.get("attack") or {}).get("per_hit") or [])]
    return out


def counts(seq):
    out = {}
    for tid, _a in seq:
        out[tid] = out.get(tid, 0) + 1
    return out


def _ability_level(state, uid) -> int:
    e = state.get_entity(uid)
    sc = e.get_component(StatsComponent) if e is not None else None
    return int(getattr(sc.ctx, "active_ability_level", 0) or 0) if sc is not None else 0


def _block_chance(state, uid):
    """`GetStat(7 = BlockChance)` de l'unite, LU dans l'etat offline pre-cast."""
    e = state.get_entity(uid)
    sc = e.get_component(StatsComponent) if e is not None else None
    return int(getattr(sc.ctx, "block_chance", 0) or 0) if sc is not None else None


def max_adjacent_targets(level: int) -> int:
    """`GetVariableForLevel(config, 0 = AbilityVariableType.maxAdjacentTargets, level)`."""
    arr = ((GC.ability("StormOfWrath") or {}).get("variables") or {}).get("maxAdjacentTargets") or []
    if not arr:
        return 0
    idx = max(0, min((level or 1) - 1, len(arr) - 1))
    return int(arr[idx])


# ------------------------------------------------------------------ geometrie derivee du board

def _walk_free(board, alive, exclude=()):
    occupied = {_upos(u) for u in alive if u.get("id") not in set(exclude)}
    return [t for t in sorted(board.by_id)
            if board.walkable(t) and board.coord(t) not in occupied]


def _find_chain(board, alive, n):
    """(C, [T, A2, ... An]) : C marchable, T voisin de C, chaque maillon voisin du precedent.
    Toutes les tuiles distinctes et libres. Rend None si le board ne le porte pas."""
    free = _walk_free(board, alive)
    coords = {t: board.coord(t) for t in free}
    for c in free:
        C = coords[c]
        for t in free:
            if t == c or hexgeo.distance(C, coords[t]) != 1:
                continue
            path = [coords[t]]
            used = {C, coords[t]}
            cur = coords[t]
            while len(path) < n:
                nxt = next((coords[x] for x in free
                            if coords[x] not in used and hexgeo.distance(cur, coords[x]) == 1),
                           None)
                if nxt is None:
                    break
                path.append(nxt)
                used.add(nxt)
                cur = nxt
            if len(path) == n:
                return C, path
    return None


def _find_cluster(board, alive, k):
    """(C, [T, V1, ... Vk]) : C marchable, T voisin de C, et `k` autres tuiles libres TOUTES
    voisines de T (hors C). Le pool de candidats du 1er saut vaut donc `k`, celui du 2e `k-1`, ...
    -- c'est ce qui rend le `PickRandomly` NON DEGENERE."""
    free = _walk_free(board, alive)
    coords = {t: board.coord(t) for t in free}
    for c in free:
        C = coords[c]
        for t in free:
            if t == c or hexgeo.distance(C, coords[t]) != 1:
                continue
            T = coords[t]
            ring = [coords[x] for x in free
                    if coords[x] != C and coords[x] != T and hexgeo.distance(T, coords[x]) == 1]
            if len(ring) >= k:
                return C, [T, *ring[:k]]
    return None


def _find_isolated(board, alive, anchors, k):
    """`k` tuiles marchables mutuellement A DISTANCE >= 2, et a distance >= 3 de CHAQUE tuile
    d'`anchors` (le caster ET tout le trace de la chaine).

    ⚠ `anchors` doit contenir TOUT le trace, pas seulement la cible : mesure du 2026-08-07 --
    ecarter une unite « loin de la cible » seulement l'a laissee ADJACENTE au 3e maillon, et la
    chaine l'a bel et bien atteinte (regime `chaine`, u83). Le regime COUPE aurait alors mesure
    autre chose que ce qu'il annonce."""
    if k <= 0:
        return []
    out = []
    for t in sorted(board.by_id):
        if not board.walkable(t):
            continue
        c = board.coord(t)
        if any(hexgeo.distance(c, a) < 3 for a in anchors):
            continue
        if any(hexgeo.distance(c, o) < 2 for o in out):
            continue
        out.append(c)
        if len(out) == k:
            return out
    return None


# ------------------------------------------------------------------ le regime

def run(regime: str = "chaine", seed: str = "777", board_id: str = "MC1_67",
        state_file: str | None = None, keep: bool = False, verbose: bool = False) -> dict:
    """Monte, caste LIVE, rejoue OFFLINE depuis le snapshot pre-cast. Rend le dict de mesure, ou
    `{"error": ...}` si le montage echoue -- l'appelant decide skip ou echec."""
    assert regime in ("chaine", "grappe", "coupe", "block"), regime
    sf = state_file or str(PYDIR.parents[1] / "logs" / "runners"
                           / ("probe-499-storm-of-wrath-%s.json" % regime))
    Path(sf).parent.mkdir(parents=True, exist_ok=True)
    sid = R._resolve_session()
    # `--block-target 'BlockChance,BlockDamage'` : 100 % de chance, 500 = le pas de l'aide de
    # `rl_duel build` (meme echelle que `--crit`). Hors regime BLOCK on l'ETEINT, sinon un block
    # aleatoire decalerait le flux RNG et l'egalite ne mesurerait plus la chaine.
    block = "100,500" if regime == "block" else "0,0"
    rid, err = _build(sf, seed, board_id,
                      ["--p-units", TIGURIUS, "--a-units", ENEMIES,
                       "--hp-target", "400000", "--hp-player", "400000",
                       "--crit", "0,0", "--crit-target", "0,0",
                       "--block-target", block, "--no-ai"])
    if rid is None:
        return {"error": "build KO: " + str(err)}
    out: dict = {"rid": rid, "regime": regime, "seed": seed, "board": board_id}
    try:
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            return {"error": "boardGraph indispo"}
        board = Board(bg["tiles"], adjacency="native_sym")

        def dview():
            return _rpc(sid, "decisionView",
                        {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)

        def alive(dv=None):
            dv = dv if dv is not None else dview()
            return [u for u in (dv.get("units") or []) if not u.get("isDead")]

        def place(uid, coord):
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid,
                "to": {"col": int(coord[0]), "row": int(coord[1])}}}, 40)
            u = next((x for x in alive() if x.get("id") == uid), None)
            return u is not None and _upos(u) == (int(coord[0]), int(coord[1]))

        dv = dview()
        us = alive(dv)
        caster = next((u for u in us if u.get("visualId") == TIGURIUS), None)
        if caster is None:
            return {"error": "%s absent du runner (pool ?)" % TIGURIUS}
        me = caster.get("owner")
        ens = [u for u in us if u.get("owner") != me]
        if len(ens) < CHAIN_LEN:
            return {"error": "pas assez d'ennemis: %d" % len(ens)}

        if regime == "grappe":
            # GRAPPE : la cible a >= 2 voisins libres -> le `PickRandomly(cand, 1)` a un VRAI CHOIX
            # a chaque saut. Sans ce regime, la chaine en LIGNE ne presente qu'UN candidat par pas :
            # l'accord y serait DEGENERE et ne prouverait rien du tirage ni de son ordre.
            geom = _find_cluster(board, us, len(ens) - 1)
            if geom is None:
                return {"error": "grappe de %d voisins non montable" % (len(ens) - 1)}
            C, path = geom
        else:
            geom = _find_chain(board, us, CHAIN_LEN)
            if geom is None:
                return {"error": "chaine de %d tuiles non montable" % CHAIN_LEN}
            C, path = geom
        target = ens[0]["id"]
        links = [e["id"] for e in ens[1:len(path)]]
        spare = [e["id"] for e in ens[len(path):]]

        # ECARTER d'abord les non-participants, PUIS poser caster/cible/maillons. `applyAction` ne
        # verifie NI la propriete NI la portee : les deux camps sont pilotables.
        n_far = len(spare) + (len(links) if regime == "coupe" else 0)
        # ancres = le caster + TOUT le trace de la chaine (regime `chaine`/`block`) ; en regime
        # COUPE le trace se reduit a la seule tuile de la cible, les maillons partant au loin.
        anchors = [C] + (path if regime != "coupe" else path[:1])
        far = _find_isolated(board, us, anchors, n_far)
        if far is None:
            return {"error": "tuiles isolees insuffisantes"}
        exiled = list(spare) + (list(links) if regime == "coupe" else [])
        for uid, c in zip(exiled, far):
            if not place(uid, c):
                return {"error": "placement isole KO u%d" % uid}
        if not place(caster["id"], C) or not place(target, path[0]):
            return {"error": "placement caster/cible KO"}
        if regime != "coupe":
            for uid, c in zip(links, path[1:]):
                if not place(uid, c):
                    return {"error": "placement maillon KO u%d" % uid}

        # tour NEUF pour le caster (les `move` consomment des activations -- cf. #111)
        for _ in range(12):
            dv = dview()
            if dv.get("currentPlayer") == me:
                break
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        if dview().get("currentPlayer") != me:
            return {"error": "tour du caster jamais atteint"}

        snap = {"dv": dview(),
                "ob": _rpc(sid, "observeBattle", {"runnerId": rid}, 40),
                "snap": _rpc(sid, "combatSnapshot", {"runnerId": rid}, 60),
                "rng": _rpc(sid, "dumpRng", {"runnerId": rid}, 30)}
        res = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster["id"], "abilityType": STORM_OF_WRATH,
            "targetId": target}}, 60)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        if not (isinstance(res, dict) and res.get("ok") and a0.get("ok")):
            return {"error": "cast live refuse: %s" % str(res)[:300]}

        st = load_state(snap["dv"], snap["ob"], snap["snap"], board=board)
        if isinstance(snap["rng"], dict) and snap["rng"].get("mt"):
            st.rng = _seed_rng(snap["rng"])
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=caster["id"], target_id=target,
                                          ability_type=STORM_OF_WRATH))
        diag = runner.ability_handler.last or {}

        out.update({
            "caster": caster["id"], "target": target, "links": links, "exiled": exiled,
            "live": live_hits(res), "off": off_seq(diag), "diag": diag,
            "max_adjacent_targets": max_adjacent_targets(_ability_level(st, caster["id"])),
            # NON-VACUITE du regime BLOCK : sans ce temoin, « aucun block observe » ne prouverait
            # rien (le montage aurait pu ne rien armer). On LIT la BlockChance effective des cibles
            # dans l'etat pre-cast.
            "block_chance": {uid: _block_chance(st, uid)
                             for uid in [target, *links]},
        })
        if verbose:
            print(json.dumps({k: v for k, v in out.items() if k != "diag"}, indent=1))
        return out
    finally:
        if not keep:
            subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", sf],
                           cwd=str(PYDIR), capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regime", choices=["chaine", "grappe", "coupe", "block", "tous"], default="tous")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    rc = 0
    a = ap.parse_args()
    regimes = ["chaine", "grappe", "coupe", "block"] if a.regime == "tous" else [a.regime]
    for reg in regimes:
        r = run(regime=reg, seed=a.seed, board_id=a.board, state_file=a.state_file, keep=a.keep)
        if r.get("error"):
            print("[499 %s] ERREUR: %s" % (reg, r["error"]))
            rc = 1
            continue
        lc, oc = counts(r["live"]), counts(r["off"])
        print("[499 %s] caster=u%s cible=u%s maillons=%s exiles=%s maxAdjacentTargets=%s"
              % (reg, r["caster"], r["target"], r["links"], r["exiled"],
                 r["max_adjacent_targets"]))
        print("[499 %s] live coups par cible = %s" % (reg, dict(sorted(lc.items()))))
        print("[499 %s] off  coups par cible = %s" % (reg, dict(sorted(oc.items()))))
        print("[499 %s] live per-coup = %s" % (reg, r["live"]))
        print("[499 %s] off  per-coup = %s" % (reg, r["off"]))
        print("[499 %s] BlockChance des cibles = %s (Psychic porte NoBlocking -> block BYPASSE)"
              % (reg, dict(sorted(r["block_chance"].items()))))
        print("[499 %s] porte=%s ; ACCORD per-coup=%s"
              % (reg, r["diag"].get("ported"), r["off"] == r["live"]))
        if r["off"] != r["live"]:
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
