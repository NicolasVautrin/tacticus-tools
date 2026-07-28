#!/usr/bin/env python
"""Probe #204 -- `MasterAnnihilator_AdditionalHitEffect` (1249) et `AstartesBanner_AdditionalHits
Effect` (1106) : le coup surnumeraire est-il un GROUPE du canal #179 (valeur DETERMINISTE sur le
vecteur ATTAQUE NORMALE) ou un coup d'ARME de plus (valeur TIREE dans les bornes d'arme) ?

CRITERE BINAIRE (le meme qui a tranche #227) : sur les attaques ou le bonus mord, la valeur du
DERNIER evenement de degat est-elle CONSTANTE d'une attaque a l'autre -- et egale a la stat ATTACK
reduite -- alors que les coups d'ARME de la MEME campagne, eux, DISPERSENT ?

RE (decompile gqfc5mff6c) -- les deux descripteurs sont des `EffectAdditionalHits` :
  `IdunBattle.Entities.Effects.Loki.MasterAnnihilator_AdditionalHitEffect$$CreateAdditionalHits`
      = Create(cond = OwnerIsTarget & !AreEqual(CurrentAttackDamageProfile, 0xd=Psychic),
               roll = FirstHitInCurrentAttackDamageRange, profil = -1 (NULL),
               count = ConfigConst(0x2f=nrOfHits), display = FirstHitInCurrentAttackDamageRange,
               cap = ConfigVar(0xd=maxDmg))
  `IdunBattle.Entities.Effects.Loki.AstartesBanner_AdditionalHitsEffect$$CreateAdditionalHits`
      = Create(cond = OwnerIsCaster & IsMeleeAttack, roll = FirstHitInCurrentAttackDamageRange,
               profil = -1 (NULL), count = ConfigConst(0x64=extraHits),
               display = FirstHitInCurrentAttackDamageRange, cap = ConfigVar(0xd=maxDmg))
Le noeud `FirstHitInCurrentAttackDamageRange` rend le `IdunBattle.Core.HitDamage` de l'AttackData de
l'attaque COURANTE ; sur une attaque NORMALE il est DEGENERE -> `IdunBattle.Core.HitDamage$$GetDamage`
court-circuite (gate `min == max`) -> valeur DETERMINISTE = stat ATTACK reduite.

MONTAGES (les deux porteurs sont dans `rl_duel.py --list-pool` au rank courant) :
  --case astartes : p-units templAncient (porteur AstartesBanner) + ultraApothecary (attaquant
      TEMOIN : 1 SEUL coup melee, `mech: {}`) ; phase NUE = banner hors rayon 2, phase ARMEE = dedans.
  --case master   : p-units admecDominus (Vitruvius, POSEUR du marqueur 1249 sur SA cible d'attaque
      normale) + ultraApothecary ; phase NUE = Vitruvius n'attaque pas, phase ARMEE = il attaque la
      MEME cible juste avant l'apothicaire (le marqueur dure 1 tour).

Contrefactuel « +1 coup d'ARME » (le port AVANT ce cas) : il predit une valeur TIREE dans la cellule
d'arme -> il est refute des que le dernier evenement est constant sur >= 2 attaques armees.

ASCII only. Usage :
  python probe_204_ah_channel.py --case astartes --builds 2 --rounds 10
  python probe_204_ah_channel.py --case master   --builds 2 --rounds 10
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parent.parent / "logs"
SID = None

ATTACKER = "ultraApothecary"          # temoin : 1 coup melee, aucune mecanique parasite
TARGET = "bloodSanguinary"
CASES = {
    # case      -> (porteur, rayon d'armement, ability du porteur)
    "astartes": ("templAncient", 2, "AstartesBanner"),
    "master":   ("admecDominus", None, "MasterAnnihilator"),
}


def rpc(method, body, timeout=90):
    r = _rpc(SID, method, body, timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def build(seed: int, state: Path, carrier: str):
    out = subprocess.run([sys.executable, str(PYDIR / "rl_duel.py"), "build",
                          "--seed", str(seed), "--state-file", str(state),
                          "--p-units", f"{carrier},{ATTACKER}", "--a-units", TARGET,
                          "--board", "MC1_67", "--hp-target", "900000",
                          "--hp-player", "900000", "--crit", "0,0",
                          "--block-target", "0,0"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    for ln in (out.stdout or "").splitlines():
        if "runnerId=" in ln:
            return int(ln.split("runnerId=")[1].split()[0])
    print("[build KO]", (out.stdout or "")[-500:], (out.stderr or "")[-500:])
    return None


def _amounts(res, tid, ability_id):
    """Montants des evenements de degat portes par CETTE attaque, dans l'ordre d'emission."""
    out = []
    for a in (res.get("actions") or []) if isinstance(res, dict) else []:
        for e in (a.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Target_Id") == tid \
                    and td.get("Active_Ability_Type") == ability_id:
                out.append(int(td["Amount"]))
    return out


def live_rows(rid: int, rounds: int, carrier: str, radius, near_from: int):
    """Rend [(armed, [montants])] pour les attaques de l'ATTAQUANT temoin.

    `near_from` = index de tour a partir duquel on ARME le bonus (avant : phase NUE) :
      - case astartes : on rapproche le porteur a <= `radius` de la tuile d'attaque ;
      - case master   : le poseur attaque la MEME cible juste AVANT l'apothicaire.
    """
    def dview():
        return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})

    dv = dview()
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    att = next((u for u in units if u.get("visualId") == ATTACKER), None)
    car = next((u for u in units if u.get("visualId") == carrier), None)
    en = next((u for u in units if u.get("visualId") == TARGET), None)
    if att is None or car is None or en is None:
        print("[live] unites introuvables", [u.get("visualId") for u in units])
        return [], None
    myp, aid, cid, tid = att.get("owner"), att["id"], car["id"], en["id"]
    a_norm = next((a for a in (att.get("abilities") or []) if a.get("kind") == "normal"), None)
    c_norm = next((a for a in (car.get("abilities") or []) if a.get("kind") == "normal"), None)
    if a_norm is None:
        return [], None
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    walk = [(t.get("col"), t.get("row")) for t in (bg.get("tiles") or []) if t.get("walkable")]

    rows, stat_attack = [], None
    for rnd in range(rounds):
        for _ in range(6):
            dv = dview()
            if dv.get("currentPlayer") == myp:
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        else:
            break
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        att = next((u for u in units if u.get("id") == aid), None)
        car = next((u for u in units if u.get("id") == cid), None)
        en = next((u for u in units if u.get("id") == tid), None)
        if att is None or car is None or en is None:
            break
        if stat_attack is None:
            stat_attack = (att.get("stats") or {}).get("attack") or (att.get("stats") or {}).get("Attack")
        T = upos(en)
        occ = {upos(u) for u in units if upos(u) is not None}
        adj = [c for c in walk if T is not None and hexgeo.distance(c, T) == 1]
        free_adj = [c for c in adj if c not in occ or c == upos(att)]
        if not T or not free_adj:
            break
        A = upos(att) if upos(att) in free_adj else free_adj[0]
        want_near = rnd >= near_from

        # --- PORTEUR : positionnement (astartes) ou attaque de pose (master) --------------------
        if radius is not None:                                   # case astartes
            if want_near:
                cand = [c for c in walk if c not in occ and c != A
                        and hexgeo.distance(c, A) <= radius]
            else:
                cand = [c for c in walk if c not in occ and c != A
                        and hexgeo.distance(c, A) > radius]
            cand.sort(key=lambda c: hexgeo.distance(c, upos(car)))
            if cand and upos(car) != cand[0]:
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": cid, "to": {"col": cand[0][0], "row": cand[0][1]}}}, 40)

        if upos(att) != A:
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": aid, "to": {"col": A[0], "row": A[1]}}}, 40)

        if radius is None and want_near and c_norm is not None:  # case master : POSE du marqueur
            car2 = next((u for u in (dview().get("units") or []) if u.get("id") == cid), None)
            cadj = [c for c in walk if hexgeo.distance(c, T) == 1
                    and c != A and (c not in occ or c == upos(car2))]
            if car2 is not None and upos(car2) not in cadj and cadj:
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": cid, "to": {"col": cadj[0][0], "row": cadj[0][1]}}}, 40)
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": cid, "targetId": tid,
                "abilityType": c_norm["id"]}}, 60)

        # --- etat REEL au moment de l'attaque temoin -------------------------------------------
        dv2 = dview()
        u2 = {u["id"]: u for u in (dv2.get("units") or []) if u.get("alive")}
        if aid not in u2 or tid not in u2:
            break
        if radius is not None:
            armed = (upos(u2[cid]) is not None
                     and hexgeo.distance(upos(u2[cid]), upos(u2[aid])) <= radius) if cid in u2 else False
        else:
            armed = any((e.get("name") or "") == "MasterAnnihilator_extraHit"
                        for e in (u2[tid].get("effects") or []))

        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": aid, "targetId": tid,
            "abilityType": a_norm["id"]}}, 60)
        am = _amounts(res, tid, a_norm["id"])
        if am:
            rows.append((bool(armed), am))
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return rows, stat_attack


def offline_rows(rid: int, carrier: str, radius, n: int = 20):
    """Rejoue N attaques OFFLINE depuis l'etat live, bonus ARME, et rend
    (stat ATTACK, coups d'arme, coups de groupe, 1er coup de groupe par attaque)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import (UnitComponent, PositionComponent, HealthComponent,
                                          StatsComponent)
    from engine.entities.stats import StatType

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    st = load_state(dv, ob, snap, board=board)
    st.rng = IntBasedMersenneTwister()
    st.rng.init_genrand(204204)

    def by_vid(v):
        return next((u for u, e in st.entities.items()
                     if e.get_component(UnitComponent) is not None
                     and e.get_component(UnitComponent).visual_id == v), None)
    aid, cid, tid = by_vid(ATTACKER), by_vid(carrier), by_vid(TARGET)
    if aid is None or cid is None or tid is None:
        return None, [], [], []
    tp = st.entities[tid].get_component(PositionComponent)
    ttile = board.id_at(tp.col, tp.row)
    nb = [board.coord(t) for t in board.neighbours(ttile) if board.walkable(t)]
    ap = st.entities[aid].get_component(PositionComponent)
    ap.col, ap.row = nb[0]
    cp = st.entities[cid].get_component(PositionComponent)
    if radius is not None:                                   # porteur DANS le rayon
        cand = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)
                and board.coord(t) not in ((ap.col, ap.row), (tp.col, tp.row))
                and hexgeo.distance(board.coord(t), (ap.col, ap.row)) <= radius]
        if cand:
            cp.col, cp.row = cand[0]
    else:                                                    # marqueur 1249 pose sur la CIBLE
        from engine.entities.effects.loki.hits import MasterAnnihilatorAdditionalHitEffect
        st.effects.by_unit.setdefault(int(tid), []).append(
            MasterAnnihilatorAdditionalHitEffect(name="MasterAnnihilator_extraHit",
                                                 effect_type=1249, source=int(cid)))
    thc = st.entities[tid].get_component(HealthComponent)
    atk = st.entities[aid].get_component(StatsComponent).ctx.stat(StatType.ATTACK)
    runner = Runner(st).install_default_handlers(20)
    grp, weapon, first = [], [], []
    for _ in range(n):
        thc.hp = 10 ** 9
        runner.apply(AttackUnitMessage(attacker_id=aid, target_id=tid))
        last = runner.damage_handler.last
        if last is None:
            break
        ah = last.get("additional_hits") or {}
        ph = list(ah.get("per_hit") or [])
        grp += ph
        weapon += list(last.get("per_hit") or [])
        if ph:
            first.append((ph[0], (ah.get("profiles") or [None])[0], len(last.get("per_hit") or [])))
    return atk, weapon, grp, first


def main():
    global SID, ATTACKER, TARGET
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=sorted(CASES), default="astartes")
    ap.add_argument("--builds", type=int, default=2)
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--near-from", type=int, default=3,
                    help="index de tour a partir duquel on ARME le bonus (avant : phase NUE)")
    ap.add_argument("--seed0", type=int, default=204100)
    ap.add_argument("--attacker", default=ATTACKER)
    ap.add_argument("--target", default=TARGET)
    ap.add_argument("--offline", action="store_true", help="ajoute le rejeu offline")
    args = ap.parse_args()
    ATTACKER, TARGET = args.attacker, args.target
    carrier, radius, ability = CASES[args.case]
    SID = _resolve_session()
    LOGS.mkdir(parents=True, exist_ok=True)
    state = LOGS / f"_probe204_{args.case}.json"

    allrows, atk_live, off = [], None, None
    for i in range(args.builds):
        rid = build(args.seed0 + i, state, carrier)
        if rid is None:
            continue
        rows, sa = live_rows(rid, args.rounds, carrier, radius, args.near_from)
        allrows += rows
        atk_live = atk_live or sa
        if args.offline and off is None:
            off = offline_rows(rid, carrier, radius)
        subprocess.run([sys.executable, str(PYDIR / "rl_duel.py"), "dispose",
                        "--runner", str(rid), "--state-file", str(state)],
                       capture_output=True, text=True)
        print(f"[build {i}] rid={rid} +{len(rows)} attaques")

    if not allrows:
        print("aucune attaque exploitable")
        return
    print(f"\n=== LIVE case={args.case} porteur={carrier} ability={ability} "
          f"attaquant={ATTACKER} cible={TARGET} ===")
    for armed, a in allrows:
        print(f"  {'ARMED' if armed else 'nue  '} n={len(a)} {a}")
    armed = [a for f, a in allrows if f]
    plain = [a for f, a in allrows if not f]
    print(f"\nattaques ARMEES n={len(armed)} | NUES n={len(plain)}")
    if plain:
        pv = sorted({v for a in plain for v in a})
        print(f"  NUES   : longueurs={sorted({len(a) for a in plain})} "
              f"valeurs={len(pv)} distinctes {pv[:12]}{'...' if len(pv) > 12 else ''}")
    if armed:
        av = sorted({v for a in armed for v in a})
        print(f"  ARMEES : longueurs={sorted({len(a) for a in armed})} "
              f"valeurs={len(av)} distinctes {av[:12]}{'...' if len(av) > 12 else ''}")
        base = min(len(a) for a in plain) if plain else min(len(a) for a in armed) - 1
        idx = base
        vals = [a[idx] for a in armed if len(a) > idx]
        wpn = [v for a in armed for v in a[:idx]] + [v for a in plain for v in a]
        print(f"\nCRITERE -- evenement d'index {idx} (juste apres les {base} coups d'arme) :")
        print(f"  ARMEES  : {vals}")
        print(f"    -> {len(set(vals))} valeur(s) distincte(s) pour {len(vals)} attaques "
              f"= {sorted(set(vals))}")
        print(f"  coups d'ARME de la meme campagne : {len(set(wpn))} valeurs distinctes "
              f"sur {len(wpn)} coups, min={min(wpn) if wpn else '-'} max={max(wpn) if wpn else '-'}")
        print(f"  stat ATTACK live (attaquant) = {atk_live}")
    if off:
        atk, off_w, off_g, off_f = off
        print("\n=== OFFLINE (bonus arme) ===")
        print(f"stat ATTACK={atk}")
        print(f"coups d'arme distinct={sorted(set(off_w))[:10]}")
        print(f"1er coup de GROUPE : {[v for v, _p, _n in off_f]}")
        print(f"  -> distinct={sorted({v for v, _p, _n in off_f})} "
              f"profil={sorted({str(p) for _v, p, _n in off_f})} "
              f"coups_arme={sorted({n for _v, _p, n in off_f})}")


if __name__ == "__main__":
    main()
