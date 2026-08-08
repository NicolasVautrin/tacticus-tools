"""#521-r7 / #521-r4 -- l'etage `On(0x4a = AttackInAtomicGroup)` de la voie NORMALE, et la
triggered `1316 CalibaniteGreatsword_NormalAttackAdditionalDamage` qu'il debloque.

CE QUE CE PROBE TRANCHE, et il ne se contente pas d'un total :

  1. le NATIF fait-il perdre des PV a une unite qui n'est PAS la cible de l'attaque normale, quand
     `darkaCompanion` << Forcas >> est en posture SWEEP (effet 1405, pose par le TOGGLE 1189) ?
     -> si oui, `EvaluateAbilities(0x4a)` EST emis sur la voie normale, ce que #521-r4 niait ;
  2. le PORT rend-il les MEMES deltas de PV, unite par unite, sur le MEME etat et le MEME MT ?
  3. DEUX contre-epreuves OFFLINE, sur le MEME bundle (donc gratuites) :
     * `--mutate sans-emetteur` : l'emetteur `evaluate_abilities_for_event` du site normal est
       neutralise -> le balayage DOIT disparaitre (attribution de l'etage) ;
     * `--mutate sans-posture` : l'effet 1405 est retire de l'etat OFFLINE -> le balayage DOIT
       disparaitre (attribution du gate `HasEffect(Owner, 1405)`).

MONTAGE (geometrie CHOISIE, jamais subie) : une tuile `T` (cible primaire), une tuile `C`
adjacente a `T` (Forcas), une tuile `A` adjacente a `T` **et** a `C` (la cible de BALAYAGE --
c'est exactement `AdjacentEnemies(Caster, CasterTile, 1) & AdjacentUnits(Target, 1, 3)`), plus une
unite alliee INERTE pour que le tour NE BASCULE PAS (sans quoi le delta de PV mesurerait aussi le
tour adverse -- piege deja paye par #478).

Usage :
    python probe_521r7_calibanite_sweep.py --state-file <ABSOLU>.json [--runner <id>]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import hexgeo                                                    # noqa: E402
from engine import battle_query as bq                            # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType         # noqa: E402
from engine.entities.effect_type import EffectType               # noqa: E402
from engine.entities.pathfinding.board import Board              # noqa: E402
from engine.runner.components import HealthComponent, StatsComponent      # noqa: E402
from engine.runner.messages import AttackUnitMessage             # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister           # noqa: E402
from engine.runner.runner import Runner                          # noqa: E402
from engine.runner.snapshot import load_state                    # noqa: E402
from probe_446_r3b_fealty_talon_asymetrie import (               # noqa: E402
    MontageError, board_geometry)

BOARD = "MC1_67"
SEED = "4463111"
HP = 60000                    # personne ne meurt -- le delta de PV reste lisible

CASTER = "darkaCompanion"     # << Forcas >>, porteur de l'active 1189 CalibaniteGreatsword
INERT = "darkaAzrael"         # allie INERTE : garde le tour ouvert apres le cast + l'attaque
TARGET = "astraBullgryn"      # cible PRIMAIRE de l'attaque normale
SWEEP = "necroWarden"         # cible de BALAYAGE : adjacente a T ET a C

CG_ACTIVE = int(ActiveAbilityType.CalibaniteGreatsword)          # 0x4a5 = 1189
CG_SWEEP_EFFECT = int(EffectType.CalibaniteGreatswordSweep)      # 0x57d = 1405
CG_STRIKE_EFFECT = int(EffectType.CalibaniteGreatswordStrike)    # 0x57c = 1404


# --------------------------------------------------------------------------- geometrie / montage

def find_layout(elev: dict, playable: set) -> "dict | None":
    """`T` avec au moins DEUX voisins natifs mutuellement adjacents (`C` et `A`) + une tuile libre
    pour l'unite inerte. Adjacence au sens NATIF (`bq.is_adjacent`, porte d'elevation)."""
    cells = sorted(playable)
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    for t in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        ring = [q for q in hexgeo.neighbors(t[0], t[1])
                if q in playable and bq.is_adjacent(t, q, elev)]
        for c in ring:
            for a in ring:
                if a == c or not bq.is_adjacent(a, c, elev):
                    continue
                free = [q for q in cells if q not in (t, c, a)]
                if not free:
                    continue
                # l'inerte est pose LOIN de T pour n'entrer dans AUCUN des deux selecteurs
                far = max(free, key=lambda q: hexgeo.distance(q, t))
                return {"T": t, "C": c, "A": a, "F": far}
    return None


def build_args(lay: dict, board: str) -> list:
    hp = [f"{v}:Health={HP},RemainingHealth={HP}" for v in (CASTER, INERT, TARGET, SWEEP)]
    return ["--board", board,
            "--p-units", f"{CASTER},{INERT}", "--a-units", f"{TARGET},{SWEEP}",
            "--place", f"{CASTER}:{lay['C'][0]},{lay['C'][1]}",
            # l'INERTE n'est PAS place : sa tuile n'a aucune contrainte (il est ALLIE du caster,
            # donc `AdjacentEnemies` -- qui filtre `team != caster` -- ne peut pas le balayer, ou
            # qu'il soit). Le forcer sur une tuile lointaine se heurtait au `SpawnPointGroup` du
            # board (placement NON honore, retour NUL silencieux cote natif).
            "--a-place", f"{TARGET}:{lay['T'][0]},{lay['T'][1]}",
            "--a-place", f"{SWEEP}:{lay['A'][0]},{lay['A'][1]}",
            "--unit-stat", ";".join(hp)]


def build(state_file: str, board: str, seed: str, lay: dict) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--state-file", state_file,
            *build_args(lay, board)]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-900:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


# --------------------------------------------------------------------------- lectures

def _uid_by_vis(dv) -> dict:
    out = {}
    for u in (dv.get("units") or []):
        v, i = u.get("visualId"), u.get("id")
        if v is not None and i is not None:
            out.setdefault(v, i)
    return out


def _hp_by_id(dv) -> dict:
    return {u["id"]: int(u.get("hp") or 0)
            for u in (dv.get("units") or []) if u.get("id") is not None}


def _effects_of(dv, uid) -> list:
    for u in (dv.get("units") or []):
        if u.get("id") == uid:
            return [e.get("effectType") if isinstance(e, dict) else e
                    for e in (u.get("effects") or [])]
    return []


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _deltas(b, a):
    return {i: int(b[i]) - int(a[i]) for i in b
            if b.get(i) is not None and a.get(i) is not None and int(b[i]) != int(a[i])}


def _bundle_state(rpc, rid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        raise MontageError("boardGraph indisponible -- l'etat offline serait sans geometrie")
    ast = rpc("unitAbilityStates", {"runnerId": rid}, 90)
    if not (isinstance(ast, dict) and (ast.get("units") or [])):
        raise MontageError(f"unitAbilityStates muet : {str(ast)[:200]} -- le canal des ACTIVES "
                           f"mesurees serait vide et `PASSIVE_HELPER_ABILITY_TRIGGERS` "
                           f"n'inscrirait RIEN")
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(s0, dict) and s0.get("ok")):
        raise MontageError(f"dumpRng indisponible : {str(s0)[:200]}")
    return {"dv": dv, "ob": ob, "snap": snap, "bg": bg, "ast": ast, "rng": s0}


def _load(bundle):
    board = Board(bundle["bg"]["tiles"], adjacency="native_sym")
    state = load_state(bundle["dv"], bundle["ob"], bundle["snap"], board=board,
                       ability_states=bundle["ast"])
    state.rng = _seed_rng(bundle["rng"])
    return state


def port_replay(bundle, cid, tid, mutate: str = "") -> dict:
    """Rejoue l'attaque normale OFFLINE sur le bundle PRE-ATTAQUE. `mutate` :
      * `sans-emetteur` -- neutralise l'emission d'`On(0x4a)` du site NORMAL (le correctif #521-r7) ;
      * `sans-posture`  -- retire l'effet 1405 de l'etat charge (le gate `HasEffect`)."""
    state = _load(bundle)
    if mutate == "sans-posture":
        # retrait DIRECT dans le substrat que lit `has_effect_of_type` (`EffectsState.by_unit`) --
        # c'est le canal exact du gate `HasEffect(Owner, 1405, onlyActive: 0)`.
        lst = state.effects.by_unit.get(int(cid)) or []
        state.effects.by_unit[int(cid)] = [e for e in lst
                                           if int(getattr(e, "effect_type", -1)) != CG_SWEEP_EFFECT]
    before = {i: (state.get_entity(i).get_component(HealthComponent).hp
                  if state.get_entity(i) is not None
                  and state.get_entity(i).get_component(HealthComponent) is not None else None)
              for i in _hp_by_id(bundle["dv"])}
    import engine.runner.operations.triggers.dispatch.ability as _AB
    saved = _AB.evaluate_abilities_for_event
    if mutate == "sans-emetteur":
        _AB.evaluate_abilities_for_event = lambda *a, **k: []
    try:
        runner = Runner(state).install_default_handlers(20)
        runner.apply(AttackUnitMessage(cid, tid))
    finally:
        _AB.evaluate_abilities_for_event = saved
    rr = runner.damage_handler.last or {}
    after = {i: (state.get_entity(i).get_component(HealthComponent).hp
                 if state.get_entity(i) is not None
                 and state.get_entity(i).get_component(HealthComponent) is not None else None)
             for i in before}
    return {"deltas": _deltas(before, after),
            "atomic": rr.get("attack_in_atomic_group"),
            "per_hit": list(rr.get("per_hit") or [])}


# --------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du state-file")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--runner", type=int, default=None)
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    elev, playable = board_geometry(args.board)
    lay = find_layout(elev, playable)
    if lay is None:
        raise MontageError(f"montage NON INSTALLE : aucune tuile de {args.board} n'a deux voisins "
                           f"natifs mutuellement adjacents")
    rid = args.runner or build(args.state_file, args.board, args.seed, lay)
    print(f"runner {rid} | board {args.board} seed {args.seed}")
    print(f"  layout T={lay['T']} C={lay['C']} A={lay['A']} inerte={lay['F']}")

    dv0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    uid = _uid_by_vis(dv0)
    for v in (CASTER, INERT, TARGET, SWEEP):
        if v not in uid:
            raise MontageError(f"{v} absent de decisionView -- montage NON installe : {sorted(uid)}")
    cid, tid, aid = uid[CASTER], uid[TARGET], uid[SWEEP]
    eff0 = _effects_of(dv0, cid)
    print(f"  ids : caster={cid} cible={tid} balayage={aid} ; effets du caster AVANT = {eff0}")
    if CG_STRIKE_EFFECT not in [int(e) for e in eff0 if e is not None]:
        raise MontageError(f"Forcas ne demarre PAS en posture STRIKE (1404) : {eff0} -- le TOGGLE "
                           f"1189 ne l'amenerait pas en SWEEP et la mesure serait vide")

    # --- (1) le TOGGLE : 1404 STRIKE -> 1405 SWEEP
    r1 = rpc("applyAction", {"runnerId": rid, "captureEvents": True,
                             "action": {"kind": "ability", "casterId": cid, "targetId": cid,
                                        "abilityType": CG_ACTIVE}}, 120) or {}
    a1 = (r1.get("actions") or [{}])[0]
    if r1.get("ok") is False or a1.get("ok") is False or a1.get("error"):
        raise MontageError(f"cast 1189 REFUSE : {str(r1)[:400]}")
    dv1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    eff1 = [int(e) for e in _effects_of(dv1, cid) if e is not None]
    print(f"  effets du caster APRES le toggle = {eff1}")
    if CG_SWEEP_EFFECT not in eff1:
        raise MontageError(f"posture SWEEP (1405) NON posee apres le cast : {eff1} -- le gate "
                           f"`HasEffect(Owner, 1405)` de 1316 ne pourrait pas passer")

    # --- (2) bundle PRE-ATTAQUE (le port rejouera EXACTEMENT cet etat)
    bundle = _bundle_state(rpc, rid)
    state0 = _load(bundle)
    from engine.runner.abilities.targeting import normal_attack_type_for
    na = normal_attack_type_for(state0, cid)
    if na is None:
        raise MontageError("l'attaque normale du caster n'est pas resolue offline")
    if state0.get_entity(cid) is None or \
            state0.get_entity(cid).get_component(StatsComponent) is None:
        raise MontageError("le caster n'a pas de StatsComponent offline")
    print(f"  attaque normale = {na} ({ActiveAbilityType(na).name})")

    # --- (3) l'attaque normale LIVE
    before = _hp_by_id(bundle["dv"])
    player0 = bundle["dv"].get("currentPlayer")
    r2 = rpc("applyAction", {"runnerId": rid, "captureEvents": True,
                             "action": {"kind": "ability", "casterId": cid, "targetId": tid,
                                        "abilityType": int(na)}}, 120) or {}
    a2 = (r2.get("actions") or [{}])[0]
    if r2.get("ok") is False or a2.get("ok") is False or a2.get("error"):
        raise MontageError(f"attaque normale REFUSEE : {str(r2)[:400]}")
    if r2.get("currentPlayer") is not None and player0 is not None \
            and r2["currentPlayer"] != player0:
        raise MontageError(f"LE TOUR A BASCULE ({player0} -> {r2['currentPlayer']}) : le delta de "
                           f"PV mesurerait aussi le tour adverse")
    dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    nat = _deltas(before, _hp_by_id(dv2))

    # --- (4) le PORT, sur le MEME etat et le MEME MT
    port = port_replay(bundle, cid, tid)
    sans_emetteur = port_replay(bundle, cid, tid, mutate="sans-emetteur")
    sans_posture = port_replay(bundle, cid, tid, mutate="sans-posture")

    by_vis = {i: v for v, i in uid.items()}
    def _named(d):
        return {by_vis.get(i, i): v for i, v in d.items()}

    print("  --- DELTAS DE PV (par unite) ---")
    print(f"      NATIF          = {_named(nat)}")
    print(f"      PORT           = {_named(port['deltas'])}")
    print(f"      port SANS emetteur On(0x4a) = {_named(sans_emetteur['deltas'])}")
    print(f"      port SANS posture 1405      = {_named(sans_posture['deltas'])}")
    print(f"      port : coups d'arme = {port['per_hit']}")
    print(f"      port : resultat du vecteur On(0x4a) = {str(port['atomic'])[:500]}")
    # ETAGE 3 : la ventilation par COUP. Le delta de PV dit COMBIEN, elle dit COMMENT -- c'est elle
    # qui separe << un coup de plus >> d'un << montant par coup different >>.
    nh = {}
    for e in (a2.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" not in td:
            continue
        nh.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
    print(f"      NATIF coups par cible = "
          f"{ {by_vis.get(k, k): v for k, v in nh.items()} }")

    # DEUX VERDICTS SEPARES, parce que ce sont DEUX etages : la STRUCTURE (qui est frappe, combien
    # de fois, et par quoi) et la MAGNITUDE (combien par coup). Les confondre en un seul rouge
    # ferait lire << 1316 ne marche pas >> la ou le vrai residu est en AMONT.
    struct, magn = [], []
    if nat.get(aid, 0) <= 0:
        struct.append(f"le NATIF ne retire AUCUN PV a la cible de BALAYAGE {SWEEP} (u{aid}) -- "
                      f"l'etage On(0x4a) n'est pas exerce, la mesure est VIDE")
    if port["deltas"].get(aid, 0) <= 0:
        struct.append(f"le PORT ne retire aucun PV a {SWEEP} -- 1316 n'a pas fire")
    if set(_named(nat)) != set(_named(port["deltas"])):
        struct.append(f"les ENSEMBLES d'unites touchees different : natif {sorted(_named(nat))} "
                      f"!= port {sorted(_named(port['deltas']))}")
    n_hits, p_hits = len(nh.get(aid) or []), len(port["atomic"][0]["sweep"][0]["attack"]["per_hit"]
                                                 if port.get("atomic") else [])
    if n_hits != p_hits:
        struct.append(f"nombre de coups du BALAYAGE : natif {n_hits} != port {p_hits}")
    if sans_emetteur["deltas"].get(aid, 0) != 0:
        struct.append("contre-epreuve INERTE : sans l'emetteur On(0x4a) le balayage part quand meme")
    if sans_posture["deltas"].get(aid, 0) != 0:
        struct.append("contre-epreuve INERTE : sans la posture 1405 le balayage part quand meme")
    if _named(nat) != _named(port["deltas"]):
        magn.append(f"MAGNITUDE : natif {_named(nat)} != port {_named(port['deltas'])}")
    for b in struct:
        print(f"  [ECHEC STRUCTURE] {b}")
    for b in magn:
        print(f"  [ECART MAGNITUDE] {b}")
    print(f"STRUCTURE : {'OK' if not struct else 'ECHEC'} | "
          f"MAGNITUDE : {'OK' if not magn else 'ECART'}")
    return 1 if struct else 0


if __name__ == "__main__":
    sys.exit(main())
