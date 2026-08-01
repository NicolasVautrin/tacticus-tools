"""#437 -- un TIR D'OVERWATCH consomme-t-il l'armure Terminator ? (natif vs port)

QUESTION (binaire, sans arithmetique) : apres un tir d'overwatch sur un porteur de
`1147 TerminatorArmour_ReduceDmg`, le flag `EffectComponent.IsActive @+0x5c` de l'instance
tombe-t-il ? Le natif dit OUI ; le port, avant #437, disait NON.

POURQUOI (RE, decompile = verite) : `On(9 = Attack)` n'est PAS emis par une operation de degat.
Son foyer est le noeud DSL `Attack(...)` :

    IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute
        for tgt in targets:  StartAttack (slot 0x3a) -> <inner> -> FinishAttack (slot 0x3b)
    Core.Services.OperationProcessor$$FinishAttack
        -> IdunBattle.Operations.FinishAttackOperation$$Execute
           FUN_1800280e0(0x50, .., 9, entities)          # On(9)  : INCONDITIONNEL
           if (currentAttack@+0x2c) FUN_1800280e0(.., 10, ..)   # On(10) : gate

L'attaque NORMALE traverse ce noeud (`ALoki_NormalAttackAbility$$GetAttackDamageBehaviour` se
termine par `IdunBattleLogic.Entities.DSLBehaviors$$Attack(...)`), et le tir d'overwatch EST une
attaque normale (`Overwatch_AutoAttackEffect$$GetAttackBehaviour = UseActiveAbility(NormalAttack)`).
Le port, lui, emettait `On(9)` au niveau MESSAGE (`DamageHandler.visit_AttackUnitMessage`), que le
tir d'overwatch ne traverse pas -- il appelle directement `AttackDamageOperation.execute`.

MONTAGE (aucune geometrie subie ; le porteur est DRIVE vers la portee de l'overwatcher) :

  * porteur / MOVER : `spaceStormcaller` (Njal) -- MEME porteur que #432 : seul `lineup`
    `TerminatorArmour` sans `TeleportStrike` (hors plateau 2 tours) ni `Resilient` (plafond
    per-coup). Il est ICI dans MON camp, parce que c'est LUI qui doit BOUGER.
  * overwatcher : `eldarRanger` (ennemi) -- trait `HeavyWeapon`, donc effet `Overwatch_AutoAttack`
    (1009) ACTIF au deploiement, sans aucun cast (meme porteur que `test_overwatch_live`).
  * SPECTATEUR : `necroOverlord` dans mon camp, qui n'agit JAMAIS. Sans lui, le tour se cloturerait
    SEUL apres le move de Njal (le natif enchaine EndTurn/ChangeTurn/StartTurn) et la lecture du
    flag porterait deja le `On(0x12)` de RE-ARMEMENT du tour suivant -- piege mesure par #432.

SEQUENCE : lire le flag -> capturer (dec/ob/snap/rng) -> `applyAction {move}` de Njal vers une tuile
a portee de l'overwatcher -> relire le flag (NATIF) ; puis REJOUER le meme move OFFLINE sur le meme
`State` et le meme flux RNG (`MoveUnitMessage`) -> lire `e.active` (PORT).

CONTRE-EPREUVE (`--mutate`) : le foyer `finish_attack_triggers` est NEUTRALISE (monkeypatch en
no-op) a la sortie de `AttackDamageOperation.execute` -- c'est EXACTEMENT l'etat d'avant #437 pour
une attaque declenchee par un trigger (le vecteur MESSAGE n'etait de toute facon pas traverse). Le
port doit alors laisser le flag a True, donc DIVERGER du natif. Sur une contre-epreuve, VERT est le
resultat SUSPECT : le probe verifie d'abord que la mutation a MORDU.

Discipline runner : state-file ABSOLU sous `logs/`, `--board` explicite, dispose en sortie.
ASCII only (cp1252).

CLI (depuis scripts/python) :
  python probe_437_overwatch_consumes_armour.py
  python probe_437_overwatch_consumes_armour.py --verdict
  python probe_437_overwatch_consumes_armour.py --mutate
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from collections import deque
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

from probe_r6_round_materialize import _mkrpc                    # noqa: E402

BOARD = "MC1_67"
SEED = "4321"
CARRIER = "spaceStormcaller"     # Njal -- TerminatorArmour, MOBILE, dans MON camp
SPECTATOR = "necroOverlord"      # n'agit jamais : empeche la cloture AUTOMATIQUE du tour
OVERWATCHER = "eldarRanger"      # trait HeavyWeapon -> effet 1009 actif au deploiement
TERMINATOR_REDUCE = 1147
OVERWATCH_EFFECT = 1009


# --------------------------------------------------------------------------- montage live


def _build(seed, board, rank=17, overwatchers=None):
    sf = ROOT / "logs" / "runners" / ("p437-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    ow = list(overwatchers or [OVERWATCHER])
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", board, "--rank", str(rank),
         "--p-units", "%s,%s" % (CARRIER, SPECTATOR), "--a-units", ",".join(ow),
         # PV du MOVER tres hauts : le tir d'overwatch ne doit ni le tuer ni le faire fuir.
         "--hp-player", "400000",
         "--crit", "0,0", "--crit-target", "0,0",
         "--block-target", "0,0", "--block-player", "0,0", "--no-ai"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, None, (proc.stderr or proc.stdout or "")[-800:]
    return int(json.loads(sf.read_text())["runnerId"]), sf, None


def _view(rpc, rid, inactive=False):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                "includeInactive": bool(inactive)}, 180)


def _by_vis(dv, vis):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vis), None)


def _unit(dv, uid):
    return next((x for x in (dv.get("units") or []) if int(x.get("id", -1)) == int(uid)), None)


def _armour_state(dv, uid, effect_type=TERMINATOR_REDUCE):
    """(present, active) de l'instance sur `uid`, lu du canal `includeInactive` --
    `active` EST le flag natif `EffectComponent.IsActive @+0x5c`."""
    for e in ((_unit(dv, uid) or {}).get("effects") or []):
        et = e.get("effectType")
        if et is not None and int(et) == int(effect_type):
            a = e.get("active")
            return True, (None if a is None else bool(a))
    return False, None


def _hp(dv, uid):
    u = _unit(dv, uid)
    return None if u is None else int(u.get("hp", 0))


def _bfs(board, src):
    dist = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def _pick_move_tile(board, dv, mover_id, ow_id, reach):
    """La tuile d'arrivee : LIBRE, atteignable en <= `reach` pas depuis le mover, et la PLUS PROCHE
    de l'overwatcher -- c'est ce qui fait entrer le mover dans `IsInAttackRange(overwatcher, mover,
    3)`, le conjoint du trigger de tir `RangedAutoAttackEffect$$CreateTargetTrigger`."""
    mv, ow = _unit(dv, mover_id), _unit(dv, ow_id)
    src = board.id_at(int(mv["pos"]["col"]), int(mv["pos"]["row"]))
    owt = board.id_at(int(ow["pos"]["col"]), int(ow["pos"]["row"]))
    occupied = {board.id_at(int(u["pos"]["col"]), int(u["pos"]["row"]))
                for u in (dv.get("units") or []) if u.get("pos") and u.get("alive")}
    d_src = _bfs(board, src)
    d_ow = _bfs(board, owt)
    cands = [t for t, d in d_src.items()
             if 0 < d <= int(reach) and t not in occupied and board.walkable(t)]
    if not cands:
        return None, None
    best = min(cands, key=lambda t: (d_ow.get(t, 10 ** 6), d_src[t]))
    return best, d_ow.get(best)


def _mover_reach(dv, mover_id, fallback=2):
    """Portee de MOUVEMENT du mover, lue du `decisionView` (le champ varie selon la version du
    canal) ; a defaut le `Movement` du gameconfig, a defaut `fallback`."""
    u = _unit(dv, mover_id) or {}
    for k in ("movement", "move", "Movement", "moveRange", "movementLeft"):
        v = u.get(k)
        if isinstance(v, int) and v > 0:
            return int(v)
    import gameconfig as GC
    g = GC.unit(u.get("visualId") or "") or {}
    v = g.get("Movement")
    return int(v) if isinstance(v, int) and v > 0 else int(fallback)


# --------------------------------------------------------------------------- rejeu offline


def _replay_move(cap, board, mover_id, to_tile, mutate=False):
    """Rejoue OFFLINE le MEME move sur le MEME `State` et le MEME flux RNG. Le vecteur after-move
    declenche l'overwatch (`OverwatchAutoAttack` -> `AttackDamageOperation.execute`), dont la
    SORTIE emet desormais `On(9)` (`finish_attack_triggers`).

    `mutate=True` neutralise ce foyer (no-op) : c'est l'etat d'avant #437 pour une attaque
    declenchee par un trigger."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent
    from engine.runner.runner import Runner
    from engine.runner.messages import MoveUnitMessage
    from engine.runner.operations.damage_ops import normal as _normal_mod

    st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board)
    mover = st.get_entity(int(mover_id))
    hc = mover.get_component(HealthComponent)
    hp_before = int(hc.hp)

    rng = IntBasedMersenneTwister()
    rng.mt = list(cap["rng"]["mt"])
    rng.mti = cap["rng"]["mti"]
    st.rng = rng

    saved = None
    if mutate:
        # Neutralise le FOYER de `On(9)` a la sortie de l'operation. ⚠ PATCH-POINT : `damage_ops.
        # normal.execute` fait `from ..triggers.dispatch import ... finish_attack_triggers`, donc il
        # lit l'attribut du PACKAGE `dispatch` -- patcher le module `dispatch.attack` serait un
        # NO-OP SILENCIEUX (mesure : la contre-epreuve rendait VERT, donc « pas mordu »).
        from engine.runner.operations.triggers import dispatch as _disp
        saved = _disp.finish_attack_triggers
        _disp.finish_attack_triggers = lambda *a, **k: []
    try:
        runner = Runner(st).install_default_handlers(20)
        runner.apply(MoveUnitMessage(int(mover_id), board.coord(int(to_tile))))
    finally:
        if saved is not None:
            from engine.runner.operations.triggers import dispatch as _disp2
            _disp2.finish_attack_triggers = saved
    assert _normal_mod is not None                    # module charge (patch-point documente)
    return {"hp_before": hp_before, "hp_after": int(hc.hp),
            "hp_delta": hp_before - int(hc.hp),
            "armour_active": _port_armour_active(st, int(mover_id))}


def _port_armour_active(state, uid):
    eff = getattr(state, "effects", None)
    if eff is None:
        return None
    for e in eff.by_unit.get(int(uid), []):
        if e.effect_type == TERMINATOR_REDUCE and not e.consumed:
            return bool(e.active)
    return None


# --------------------------------------------------------------------------- pilote


def run(seed=SEED, board=BOARD, mutate=False, verbose=True, overwatchers=None) -> dict:
    ow = list(overwatchers or [OVERWATCHER])
    rid, sf, err = _build(seed, board, overwatchers=ow)
    if rid is None:
        return {"error": "build KO : %s" % err}
    rpc = _mkrpc()
    try:
        return _measure(rpc, rid, mutate, verbose, board_id=board, seed_id=str(seed),
                        overwatchers=ow)
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def _measure(rpc, rid, mutate, verbose, board_id=None, seed_id=None, overwatchers=None):
    from engine.entities.pathfinding.board import Board

    ows = list(overwatchers or [OVERWATCHER])
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = _view(rpc, rid, inactive=True)
    ids = {}
    for v in [CARRIER, SPECTATOR] + ows:
        u = _by_vis(dv, v)
        if u is None:
            return {"error": "unite absente du build : %s" % v}
        ids[v] = int(u["id"])

    for v in ows:
        ow_effs = [e.get("effectType") for e in ((_unit(dv, ids[v]) or {}).get("effects") or [])]
        if OVERWATCH_EFFECT not in [int(x) for x in ow_effs if x is not None]:
            return {"error": "overwatcher %s sans effet 1009 actif (effets=%s)" % (v, ow_effs)}

    present0, _ = _armour_state(dv, ids[CARRIER])
    if not present0:
        return {"error": "le porteur n'a pas l'effet 1147 (pas de TerminatorArmour ?)"}

    # --- APPROCHE : le porteur avance d'un tour a l'autre jusqu'a ce que le move le fasse ENTRER
    #     dans la portee de l'overwatcher (Njal a Movement=2, l'arme Energy du Ranger porte a 3).
    #     Le move DECLENCHEUR est celui apres lequel les PV du mover baissent -- c'est LUI qu'on
    #     mesure et qu'on rejoue offline. On capture donc AVANT CHAQUE move.
    approach = []
    for _turn in range(24):
        dv = _view(rpc, rid, inactive=True)
        if dv.get("currentPlayer") != dv.get("myPlayer", dv.get("currentPlayer")):
            pass                                    # (le canal ne publie pas toujours `myPlayer`)
        mvu = _unit(dv, ids[CARRIER])
        if mvu is None or not mvu.get("alive"):
            return {"error": "le porteur est mort pendant l'approche", "approach": approach}
        reach = _mover_reach(dv, ids[CARRIER])
        # On vise le PREMIER overwatcher declare ; les autres tirent s'ils couvrent aussi la tuile
        # d'arrivee (c'est exactement le regime a DEUX tirs qui rend le DEGAT observable).
        to_tile, d_ow = _pick_move_tile(board, dv, ids[CARRIER], ids[ows[0]], reach)
        if to_tile is None:
            return {"error": "aucune tuile d'arrivee libre a portee de mouvement",
                    "approach": approach}
        present0, act0 = _armour_state(dv, ids[CARRIER])
        hp0 = _hp(dv, ids[CARRIER])
        player0 = dv.get("currentPlayer")
        # Etat 1009 de CHAQUE overwatcher AVANT le move. Le 3e `Triggered()` de
        # `RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` (`On(10) & OwnerIsActor ->
        # DeactivateEffect`) desarme celui qui TIRE : le passage True->False compte donc les tirs
        # REELLEMENT partis, sans avoir a deviner la geometrie.
        ow_before = {v: _armour_state(dv, ids[v], OVERWATCH_EFFECT)[1] for v in ows}
        cap = {"dec": _view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
               "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
               "rng": rpc("dumpRng", {"runnerId": rid}, 30)}
        col, row = board.coord(to_tile)
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": ids[CARRIER], "to": {"col": int(col), "row": int(row)}}}, 120)
        dv2 = _view(rpc, rid, inactive=True)
        hp1 = _hp(dv2, ids[CARRIER])
        present1, act1 = _armour_state(dv2, ids[CARRIER])
        ow_after = {v: _armour_state(dv2, ids[v], OVERWATCH_EFFECT)[1] for v in ows}
        shots = [v for v in ows if ow_before.get(v) is True and ow_after.get(v) is False]
        approach.append({"to": [int(col), int(row)], "d_ow": d_ow, "hp": hp1,
                         "armour": act1, "shots": list(shots),
                         "player": dv2.get("currentPlayer")})
        if hp0 is not None and hp1 is not None and hp1 < hp0:
            break                                   # LE tir d'overwatch a eu lieu sur CE move
        # pas de tir : on clot le tour (le SPECTATEUR n'agit jamais, donc la cloture est explicite)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        d3 = _view(rpc, rid)
        if d3.get("currentPlayer") != player0:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
    else:
        return {"error": "l'overwatch n'a jamais tire en 24 tours d'approche", "approach": approach}

    port = _replay_move(cap, board, ids[CARRIER], to_tile, mutate=mutate)

    out = {"runner": rid, "ids": ids, "board": board_id, "seed": seed_id,
           "overwatchers": ows,
           "move_to": [int(col), int(row)], "dist_to_overwatcher": d_ow,
           "approach": approach,
           "native": {"armour_before": act0, "armour_after": act1,
                      "present_after": present1, "hp_before": hp0, "hp_after": hp1,
                      "hp_delta": (hp0 - hp1) if (hp0 is not None and hp1 is not None) else None,
                      "shots": list(shots), "n_shots": len(shots),
                      "player_before": player0, "player_after": dv2.get("currentPlayer")},
           "port": port, "mutate": bool(mutate)}
    if verbose:
        _report(out)
    return out


def _report(r):
    n, p = r["native"], r["port"]
    print("[437] board=%s seed=%s runner=%s ids=%s move_to=%s d(overwatcher)=%s"
          % (r["board"], r["seed"], r["runner"], r["ids"], r["move_to"], r["dist_to_overwatcher"]))
    print("[437] NATIF : armure avant=%-5s apres=%-5s | hp %s -> %s (delta=%s) | tirs=%d %s"
          % (n["armour_before"], n["armour_after"], n["hp_before"], n["hp_after"],
             n["hp_delta"], n.get("n_shots", 0), n.get("shots")))
    print("[437] PORT  (mutate=%s) : armure apres=%-5s | hp %s -> %s (delta=%s)"
          % (r["mutate"], p["armour_active"], p["hp_before"], p["hp_after"], p["hp_delta"]))


def verdict(base: dict, mut: dict = None) -> list:
    """Echecs (liste de chaines). Vide = tout tient.

    (1) NATIF : l'armure etait ARMEE avant le move et le tir d'overwatch l'a CONSOMMEE.
    (2) PORT  : meme trajectoire de flag, et meme degat encaisse (bit-exactitude du tir).
    (3) MUTATION (si fournie) : foyer `On(9)` neutralise -> le flag ne tombe PLUS. C'est ce qui
        atteste que le verdict (2) porte bien sur CE foyer et pas sur autre chose."""
    f = []
    n, p = base["native"], base["port"]
    if n["hp_delta"] is None or int(n["hp_delta"]) <= 0:
        f.append("[montage] le tir d'overwatch n'a inflige AUCUN degat (delta=%s) : le conjoint "
                 "`AmountIsGreaterThanZero(HealthDamageFromEvent())` ne peut pas etre exerce"
                 % n["hp_delta"])
    if n["armour_before"] is not True:
        f.append("[natif] l'armure n'etait pas ARMEE avant le move (before=%s)" % n["armour_before"])
    if n["armour_after"] is not False:
        f.append("[natif] le tir d'overwatch n'a PAS desarme l'armure (after=%s) -- la premisse "
                 "du cas #437 serait fausse" % n["armour_after"])
    if p["armour_active"] is not False:
        f.append("[port] le flag `e.active` n'est PAS tombe apres le tir d'overwatch (=%s) : le "
                 "vecteur `On(9)` ne traverse pas le tir declenche par trigger"
                 % p["armour_active"])
    if int(p["hp_delta"]) != int(n["hp_delta"] or 0):
        f.append("[port] degat du tir d'overwatch : port=%d natif=%s (ecart %+d)"
                 % (p["hp_delta"], n["hp_delta"], p["hp_delta"] - int(n["hp_delta"] or 0)))
    if mut is not None:
        mp = mut["port"]
        if mp["armour_active"] is not True:
            f.append("[mutation] LA MUTATION N'A PAS MORDU : le flag tombe quand meme (=%s) -- le "
                     "verdict [port] ne prouverait rien" % mp["armour_active"])
        # Le DEGAT attendu depend du REGIME, et c'est ce qui separe les deux montages :
        #  * UN seul overwatcher -> son tir est la 1re attaque du tour, REDUITE dans les deux bras :
        #    le degat doit etre IDENTIQUE (la mutation ne deborde pas du vecteur qu'elle vise) ;
        #  * DEUX overwatchers couvrant la tuile d'arrivee -> deux tirs sur le MEME move : le 2e est
        #    PLEIN quand l'armure a ete consommee par le 1er, REDUIT sinon. Le degat total doit donc
        #    CHUTER sous mutation -- c'est l'observable de DEGAT, celui que le flag seul ne donne pas.
        # Le regime est celui des tirs REELLEMENT partis (compte par le desarmement 1009 de chaque
        # overwatcher), pas celui des overwatchers DECLARES : la geometrie peut n'en amener qu'un.
        multi = int(n.get("n_shots", 0)) >= 2
        if not multi and int(mp["hp_delta"]) != int(p["hp_delta"]):
            f.append("[mutation] le DEGAT a change (%d vs %d) : avec UN seul tir (donc la 1re "
                     "attaque du tour, reduite des deux cotes) la mutation deborde du seul vecteur "
                     "d'evenement qu'elle vise" % (mp["hp_delta"], p["hp_delta"]))
        if multi and int(mp["hp_delta"]) >= int(p["hp_delta"]):
            f.append("[mutation] regime DEUX TIRS : degat mute=%d >= normal=%d -- le 2e tir n'est "
                     "donc pas PLEIN dans le bras normal, la garde ne rougirait PAS"
                     % (mp["hp_delta"], p["hp_delta"]))
    return f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--overwatchers", default=OVERWATCHER,
                    help="liste d'overwatchers ENNEMIS separee par virgule (defaut : %s). Deux "
                         "overwatchers couvrant la meme tuile = DEUX tirs sur le meme move -> le "
                         "DEGAT devient l'observable (tir 1 REDUIT, tir 2 PLEIN)." % OVERWATCHER)
    ap.add_argument("--verdict", action="store_true",
                    help="joue les deux bras (normal + mutate) et imprime le verdict")
    a = ap.parse_args()
    ows = [x.strip() for x in a.overwatchers.split(",") if x.strip()]
    if a.verdict:
        base = run(seed=a.seed, board=a.board, overwatchers=ows)
        if "error" in base:
            print("[437] ERREUR (base) : %s" % base["error"])
            return 2
        mut = run(seed=a.seed, board=a.board, mutate=True, overwatchers=ows)
        if "error" in mut:
            print("[437] ERREUR (mutate) : %s" % mut["error"])
            return 2
        fails = verdict(base, mut)
        print("[437] VERDICT : %s" % ("OK" if not fails else "%d echec(s)" % len(fails)))
        for x in fails:
            print("   - %s" % x)
        return 0 if not fails else 1
    r = run(seed=a.seed, board=a.board, mutate=a.mutate, overwatchers=ows)
    if "error" in r:
        print("[437] ERREUR : %s" % r["error"])
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
