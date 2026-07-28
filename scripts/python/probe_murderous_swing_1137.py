#!/usr/bin/env python
"""Probe 1137 MurderousSwing (`worldExecutions` << Tarvakh >>, WorldEaters) -- gisement `[-D]`
(face DECISION portee, face COMBAT NO-OP silencieux).

CE QUE CE PROBE MESURE, et pourquoi il precede le port :
  * le cast est-il ACCEPTE par le natif (il consomme le tour) ?
  * le port MUTE-t-il quelque chose (`ported`, PV des cibles, PV du caster) ?
Avant le port, la reponse attendue est << cast ACCEPTE, tour CONSOMME, ZERO mutation >>. C'est
exactement la signature du gisement -- et exactement celle d'un MONTAGE RATE (`applyAction` rend
`ok=True` sans rien muter quand l'unite n'est pas dans `toActivate`). Le probe distingue les deux en
exigeant `mutated=true` cote LIVE : si le natif, lui, a bien mute, alors un offline a zero est un
VRAI no-op de port.

MONTAGE (geometrie DRIVEE, jamais subie -- `applyAction move` ignore la propriete) :
  le CASTER NE BOUGE PAS ; on amene `k` ennemis sur SON ring 1. `k` est LE parametre discriminant :

    IdunBattleLogic.Entities.Abilities.Active.MurderousSwingAbility$$ExecuteBehaviour
        targets = AdjacentEnemies(caster@0x160)                       # ring 1, ennemis du caster
        dmg     = If( AmountIsGreater(Count(targets), Direct(1)),     # STRICT (> 1)
                      MinMaxDamage,                                   # GetMultipleUnitsDamage
                      Sum(MinMaxDamage, Direct(GetVariableForLevel(8 = extraDmg))) )  # GetSingleUnitDamage
        Execute( AttackWithAttackDamage(caster@0x160, targets, dmg, GetDamageProfile, GetHits) )

  -> `k = 1` : UNE cible, degat = base + extraDmg ; `k >= 2` : k cibles, degat = base seule.

POURQUOI LE CASTER NE BOUGE PAS -- c'est ce qui permet de caster SANS AUCUN `endturn`, donc SANS
que l'IA adverse ne joue. Mesure du 2026-07-28 : avec des `endturn`, l'adversaire castait ses
propres abilities (`Doom_extraDmg` observe sur une cible) et le degat n'etait plus attribuable.
On VERIFIE quand meme que le caster est dans `toActivate` et que le tour n'a pas bascule : un cast
hors-tour est refuse EN SILENCE (`ok=True`, aucune mutation) et se lirait comme un no-op de port.
On re-verifie AUSSI qu'aucun ennemi NON place n'est adjacent au caster (un summon adverse peut
apparaitre sur une tuile libre du ring 1 -- `genesSmnDecoy`, mesure).

ASCII only (cp1252). Usage :
  python probe_murderous_swing_1137.py --k 1
  python probe_murderous_swing_1137.py --k 2 --board C1_74
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                                          # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                    # noqa: E402
from engine.entities.pathfinding.board import Board                    # noqa: E402
from engine.runner.snapshot import load_state                          # noqa: E402
from engine.runner.runner import Runner                                # noqa: E402
from engine.runner.messages import ActiveAbilityMessage                # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                 # noqa: E402
from engine.runner.components import HealthComponent                   # noqa: E402

TARVAKH = "worldExecutions"
ABILITY = 1137
# Cibles VANILLA (`python unit_map.py vanilla-target`) : aucun trait/ability qui modifie le degat
# RECU. ⚠ CE CRITERE NE SUFFIT PAS : il regarde ce que l'unite s'applique A ELLE-MEME, pas ce
# qu'un ALLIE lui donne. DEUX rosters ont ete ECARTES PAR LA MESURE (2026-07-28), pour des raisons
# differentes :
#   * `tauAunShi` : les DEUX cibles portaient `SereneUnifierSenseOfStone` (pose d'equipe au turn-start
#     d'Aun'Shi) -> le degat LIVE valait EXACTEMENT la MOITIE du degat offline sur chacune. RESOLU
#     par #192 : l'effet 1169 a desormais sa classe (`SereneUnifierSenseOfStoneEffect`), l'agrement
#     est bit-exact avec Aun'Shi en jeu (`probe_192_sense_of_stone.py`). Le roster reste neanmoins
#     ECARTE ICI : `SereneUnifierSenseOfStone` n'existe qu'APRES un turn-start d'Aun'Shi, or ce
#     montage cast SANS aucun `endturn` -- le banc serait donc muet sur l'aura, pas propre grace a elle.
#   * `genesMagus` : son summon `genesSmnDecoy` apparait quand il se DEPLACE, et il se pose sur une
#     tuile LIBRE du ring 1 du caster -> il entre dans `AdjacentEnemies(caster)` et fait varier le
#     `Count` sans qu'on l'ait demande.
ENEMIES = "eldarFarseer,astraBullgryn,tauMarksman"


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def build(state_file: Path, seed: int, hp_target: int, board_id: str = "MC1_67") -> int:
    state_file.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state_file), "--board", board_id, "--rank", "17",
         "--p-units", TARVAKH, "--a-units", ENEMIES,
         "--hp-target", str(hp_target), "--crit", "0,0", "--block-target", "0,0"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[1137] build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
        sys.exit(2)
    return int(json.loads(state_file.read_text())["runnerId"])


def view(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 180)


def alive(dv):
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def move(sid, rid, uid, coord):
    _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid,
        "to": {"col": int(coord[0]), "row": int(coord[1])}}}, 40)


def endturn(sid, rid):
    _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)


def seed_rng(dump):
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"])
    rng.mti = dump["mti"]
    return rng


def hp_of(state, uid):
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def setup(sid, rid, board, k: int, which=None):
    """Pose `k` ennemis sur le ring 1 du caster (le caster, lui, NE BOUGE PAS).

    `which` = indices (dans la liste des ennemis, ordre `decisionView`) des unites a amener au
    contact. Il sert au regime DISCRIMINANT du `Count` reevalue : l'ordre d'attaque est l'id
    croissant (`AttackBehaviour$$Execute` -> `OrderBy`), donc c'est le CHOIX des deux ennemis qui
    decide laquelle est frappee la premiere -- et donc quelle fenetre de PV rend la bascule
    MULTI -> SINGLE observable par une MORT plutot que par un `Amount` clampe.

    Rend `(caster_id, [ids adjacents], target_id)` ou `{"reason": ...}`."""
    dv = view(sid, rid)
    units = alive(dv)
    me = next((u for u in units if u.get("visualId") == TARVAKH), None)
    if me is None:
        return {"reason": "Tarvakh absent du build"}
    myp = me.get("owner")
    ens = [u for u in units if u.get("owner") != myp]
    if which is not None:
        if max(which) >= len(ens):
            return {"reason": "indice d'ennemi hors roster"}
        ens = [ens[i] for i in which]
    if len(ens) < k:
        return {"reason": "moins de %d ennemis vivants" % k}
    # LE CASTER NE BOUGE PAS. On amene les `k` ennemis sur SON ring 1 -- c'est ce qui permet de
    # caster SANS AUCUN `endturn` : le caster garde son activation, et surtout l'IA ADVERSE ne
    # joue jamais. Mesure du 2026-07-28 : avec des `endturn`, l'adversaire castait ses propres
    # abilities (`Doom_extraDmg` observe sur une cible) et le banc de mesure devenait illisible.
    cpos = upos(me)
    centre = board.id_at(cpos[0], cpos[1])
    ring = [board.coord(n) for n in board.neighbours_native(centre) if board.walkable(n)]
    if len(ring) < k:
        return {"reason": "le caster n'a que %d voisins marchables (< %d)" % (len(ring), k)}
    occupied = {upos(u) for u in units if u["id"] != me["id"]}
    free = [c for c in ring if c not in occupied]
    if len(free) < k:
        return {"reason": "moins de %d voisins LIBRES autour du caster" % k}
    adj = []
    for i in range(k):
        move(sid, rid, ens[i]["id"], free[i])
        adj.append(ens[i]["id"])
    cc = cpos
    # Les ennemis NON places doivent rester HORS du ring 1 du caster (sinon `Count` change).
    dv = view(sid, rid)
    for u in alive(dv):
        if u.get("owner") == myp or u["id"] in adj:
            continue
        p = upos(u)
        if p is not None and hexgeo.distance(p, cc) <= 1:
            return {"reason": "un ennemi non place est adjacent au caster (u%s)" % u["id"]}
    if dv.get("currentPlayer") != myp:
        return {"reason": "le tour a bascule pendant les placements"}
    if me["id"] not in (dv.get("toActivate") or []):
        return {"reason": "le caster n'a plus d'activation (cast refuse en silence)"}
    # verification de la geometrie EFFECTIVE apres les endturn (l'IA adverse a pu bouger)
    pos = {u["id"]: upos(u) for u in alive(dv)}
    got = [uid for uid, p in pos.items()
           if uid in adj and p is not None and hexgeo.distance(p, cc) == 1]
    if len(got) != k:
        return {"reason": "geometrie perdue : %d/%d ennemis encore adjacents" % (len(got), k)}
    return me["id"], got, got[0]


def run(k: int, seed: int, hp_target: int, verbose: bool = True, which=None, board_id: str = "MC1_67"):
    sid = _resolve_session()
    state = PYDIR / ("probe_ms1137_k%d_%s.json" % (k, board_id))
    rid = build(state, seed, hp_target, board_id=board_id)
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
        if not bg.get("tiles"):
            return {"error": "boardGraph indispo"}
        board = Board(bg["tiles"], adjacency="native_sym")
        sc = setup(sid, rid, board, k, which=which)
        if isinstance(sc, dict):
            return {"error": sc["reason"]}
        caster, adj, target = sc
        snap = {"dv": view(sid, rid),
                "ob": _r(sid, "observeBattle", {"runnerId": rid}, 40),
                "snap": _r(sid, "combatSnapshot", {"runnerId": rid}, 60),
                "rng": _r(sid, "dumpRng", {"runnerId": rid}, 30)}
        res = _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster, "targetId": target,
            "abilityType": ABILITY}}, 90)
        a0 = (res.get("actions") or [{}])[0]
        live = {}
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                live.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))

        st = load_state(snap["dv"], snap["ob"], snap["snap"], board=board)
        if isinstance(snap["rng"], dict) and snap["rng"].get("mt"):
            st.rng = seed_rng(snap["rng"])
        before = {u: hp_of(st, u) for u in ([caster] + adj)}
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=caster, target_id=target,
                                          ability_type=ABILITY))
        last = runner.ability_handler.last or {}
        after = {u: hp_of(st, u) for u in ([caster] + adj)}

        out = {"k": k, "caster": caster, "adjacent": adj, "target": target,
               "live_ok": bool(a0.get("ok")), "live_mutated": bool(a0.get("mutated")),
               "live_events": len(a0.get("events") or []), "live_damage": live,
               "ported": last.get("ported"), "flags": last.get("flags"),
               "hp_before": before, "hp_after": after, "last": last,
               # snapshot PRE-cast + board : rejouable a volonte (decomposition par etage)
               "snapshot": snap, "board": board}
        if verbose:
            print("[1137 k=%d] caster=u%s adjacents=%s cible=u%s" % (k, caster, adj, target))
            print("[1137 k=%d] LIVE ok=%s mutated=%s events=%d damage=%s"
                  % (k, out["live_ok"], out["live_mutated"], out["live_events"], live))
            print("[1137 k=%d] OFFLINE ported=%s flags=%s" % (k, out["ported"], out["flags"]))
            print("[1137 k=%d] hp %s -> %s" % (k, before, after))
        return out
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        state.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=1, help="nb d'ennemis adjacents au caster")
    ap.add_argument("--seed", type=int, default=20137)
    ap.add_argument("--hp-target", type=int, default=500000)
    ap.add_argument("--board", default="MC1_67", help="board dumpe (ids : python board.py)")
    ap.add_argument("--which", default=None,
                    help="indices des ennemis a amener au contact, ex. '1,2'")
    a = ap.parse_args()
    which = [int(x) for x in a.which.split(",")] if a.which else None
    r = run(a.k, a.seed, a.hp_target, which=which, board_id=a.board)
    if "error" in r:
        print("[1137] ERROR: %s" % r["error"])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
