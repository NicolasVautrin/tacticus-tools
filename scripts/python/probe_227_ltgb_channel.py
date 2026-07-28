#!/usr/bin/env python
"""Probe #227 -- `LetTheGalaxyBurn` : le coup surnumeraire est-il un GROUPE du canal #179
(valeur DETERMINISTE sur le vecteur ATTAQUE NORMALE) ou un coup d'ARME de plus (valeur TIREE) ?

CRITERE BINAIRE : sur les attaques ou le gate est arme (base+1 evenements de degat), la valeur du
DERNIER evenement est-elle CONSTANTE d'une attaque a l'autre -- et egale a ce que le port calcule
offline pour le groupe ?

RE (decompile gqfc5mff6c) : `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`
-> `EffectAdditionalHits$$Create(dmg = FirstHitInCurrentAttackDamageRange, profil = NULL, count = NULL)`.
Le noeud rend le `IdunBattle.Core.HitDamage` de l'AttackData de l'attaque courante (liste
`currentAttack@+0x50`, alimentee par `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits`).
Pour une attaque NORMALE ce `HitDamage` est DEGENERE -> `IdunBattle.Core.HitDamage$$GetDamage`
court-circuite (gate min == max) -> valeur DETERMINISTE = base d'attaque reduite.

Deux contrefactuels rendus dans la meme passe :
  - les coups d'ARME de la MEME attaque, eux, VARIENT (c'est la mesure de reference) ;
  - le modele « +1 coup d'arme » (l'ancien port) predit une valeur TIREE dans la meme cellule :
    il est refute des que le dernier evenement est constant sur >= 2 attaques armees.

ASCII only. Usage :
  python probe_227_ltgb_channel.py --builds 3 --rounds 12
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

CARRIER = "blackTerminator"          # Angrax -- porteur du TRAIT LetTheGalaxyBurn (1058)
TARGET = "bloodSanguinary"
DIST = 1                             # 1 = melee force ; >=2 = tir (generalisation porteur RANGED)


def rpc(method, body, timeout=90):
    r = _rpc(SID, method, body, timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def build(seed: int, state: Path):
    out = subprocess.run([sys.executable, str(PYDIR / "rl_duel.py"), "build",
                          "--seed", str(seed), "--state-file", str(state),
                          "--p-units", CARRIER, "--a-units", TARGET,
                          "--board", "MC1_67", "--hp-target", "900000",
                          "--hp-player", "900000", "--crit", "0,0",
                          "--block-target", "0,0"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    for ln in (out.stdout or "").splitlines():
        if "runnerId=" in ln:
            return int(ln.split("runnerId=")[1].split()[0])
    print("[build KO]", (out.stdout or "")[-400:], (out.stderr or "")[-400:])
    return None


def live_rows(rid: int, rounds: int):
    """Rend [(tile_fx_avant, [montants des evenements de degat, dans l'ordre])]."""
    def dview():
        return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})

    def tile_fx():
        tm = rpc("tileMeta", {"runnerId": rid}, 60)
        return {(t.get("col"), t.get("row")): [e.get("name") for e in (t.get("effects") or [])]
                for t in (tm.get("tiles") or [])}

    dv = dview()
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    me = next((u for u in units if u.get("visualId") == CARRIER), None)
    en = next((u for u in units if u.get("id") != (me or {}).get("id")), None)
    if me is None or en is None:
        return []
    myp, aid, tid = me.get("owner"), me["id"], en["id"]
    norm = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
    if norm is None:
        return []
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    walk = [(t.get("col"), t.get("row")) for t in (bg.get("tiles") or []) if t.get("walkable")]

    rows = []
    for _ in range(rounds):
        for _ in range(6):
            dv = dview()
            if dv.get("currentPlayer") == myp:
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        else:
            break
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        me = next((u for u in units if u.get("id") == aid), None)
        en = next((u for u in units if u.get("id") == tid), None)
        if me is None or en is None:
            break
        T = upos(en)
        nb = [c for c in walk if T is not None and hexgeo.distance(c, T) == DIST]
        if not T or not nb:
            break
        if upos(me) not in nb:                        # DRIVE : distance voulue (melee ou tir)
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": aid, "to": {"col": nb[0][0], "row": nb[0][1]}}}, 40)
        fx_before = tile_fx().get(T) or []
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": aid, "targetId": tid, "abilityType": norm["id"]}}, 60)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        amounts = []
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Target_Id") == tid \
                    and td.get("Active_Ability_Type") == norm["id"]:
                amounts.append(int(td["Amount"]))
        if amounts:
            rows.append((tuple(fx_before), amounts))
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return rows


def offline_group_value(rid: int, n: int = 12):
    """Rejoue N attaques OFFLINE depuis l'etat live, branche B forcee (tuile de la cible portant un
    status-effect) -> le groupe #179 est TOUJOURS emis. Rend la liste des valeurs du coup de groupe."""
    from engine.entities.pathfinding.board import Board
    from engine.entities.effects.base import BaseEffect
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
    st.rng.init_genrand(227227)
    aid = next((u for u, e in st.entities.items()
                if (e.get_component(UnitComponent) or None) is not None
                and e.get_component(UnitComponent).visual_id == CARRIER), None)
    if aid is None:
        return None, [], [], []
    tid = next(u for u in st.entities if u != aid
               and st.entities[u].get_component(UnitComponent) is not None
               and st.entities[u].get_component(UnitComponent).visual_id == TARGET)
    tp = st.entities[tid].get_component(PositionComponent)
    ttile = board.id_at(tp.col, tp.row)
    ap = st.entities[aid].get_component(PositionComponent)
    if DIST == 1:
        nb = [board.coord(t) for t in board.neighbours(ttile) if board.walkable(t)]
        ap.col, ap.row = nb[0]
    else:
        far = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)
               and hexgeo.distance(board.coord(t), (tp.col, tp.row)) == DIST]
        if far:
            ap.col, ap.row = far[0]
    # branche B : `HasTileStatusEffect(Targets)` -> gate deterministe, groupe TOUJOURS emis.
    st.effects.by_unit.setdefault(int(ttile), []).append(BaseEffect(name="Fire", effect_type=5))
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
        # Le groupe LetTheGalaxyBurn est SANS profil -> il est execute EN PREMIER (mirror des deux
        # call-sites natifs : `ExecuteAdditionalHitsWithoutDamageProfileType` inline dans
        # `AttackDamageOperation$$Execute`, les groupes A profil en sous-operations planifiees).
        if ph:
            first.append((ph[0], (ah.get("profiles") or [None])[0], len(last.get("per_hit") or [])))
    return atk, weapon, grp, first


def main():
    global SID, CARRIER, TARGET, DIST
    ap = argparse.ArgumentParser()
    ap.add_argument("--builds", type=int, default=3)
    ap.add_argument("--rounds", type=int, default=12)
    ap.add_argument("--seed0", type=int, default=227100)
    ap.add_argument("--carrier", default=CARRIER,
                    help="porteur du trait 1058 (blackAbaddon/blackHaarken/blackObliterator/"
                         "blackPossession/blackTerminator)")
    ap.add_argument("--target", default=TARGET)
    ap.add_argument("--dist", type=int, default=DIST,
                    help="1 = melee force ; >=2 = tir (porteur RANGED, groupes #179 profiles coexistants)")
    args = ap.parse_args()
    CARRIER, TARGET, DIST = args.carrier, args.target, args.dist
    SID = _resolve_session()
    LOGS.mkdir(parents=True, exist_ok=True)
    state = LOGS / "_probe227_ltgb.json"

    allrows, atk, off_w, off_g, off_f = [], None, [], [], []
    for i in range(args.builds):
        rid = build(args.seed0 + i, state)
        if rid is None:
            continue
        rows = live_rows(rid, args.rounds)
        allrows += rows
        if i == 0:
            atk, off_w, off_g, off_f = offline_group_value(rid)
        subprocess.run([sys.executable, str(PYDIR / "rl_duel.py"), "dispose",
                        "--runner", str(rid), "--state-file", str(state)],
                       capture_output=True, text=True)
        print(f"[build {i}] rid={rid} +{len(rows)} attaques")

    if not allrows:
        print("aucune attaque exploitable")
        return
    base = min(len(a) for _fx, a in allrows)
    armed = [a for _fx, a in allrows if len(a) == base + 1]
    plain = [a for _fx, a in allrows if len(a) == base]
    print("\n=== LIVE ===")
    print(f"n={len(allrows)} base={base} armees(base+1)={len(armed)} nues={len(plain)}")
    for fx, a in allrows:
        print(f"  {'B' if fx else 'A'} n={len(a)} {a}")
    plain = [a for _fx, a in allrows if len(a) == base]
    wpn = sorted({v for _fx, a in allrows for v in a})
    print(f"\nATTAQUES ARMEES : n={len(armed)} | NUES : n={len(plain)}")
    print(f"  tous evenements observes : {len(wpn)} valeurs distinctes, min={min(wpn)} max={max(wpn)}")
    print("\n=== OFFLINE (branche B forcee) ===")
    print(f"stat ATTACK={atk}")
    print(f"coups d'arme offline distinct={sorted(set(off_w))[:8]}...")
    print(f"1er coup de GROUPE (= groupe SANS profil, execute en PREMIER -- mirror des deux "
          f"call-sites natifs) : {[v for v, _p, _n in off_f]}")
    print(f"  -> distinct={sorted({v for v, _p, _n in off_f})} "
          f"profil={sorted({p for _v, p, _n in off_f})} coups_arme={sorted({n for _v, _p, n in off_f})}")
    # La POSITION du coup LetTheGalaxyBurn dans la sequence live = juste apres les coups d'arme
    # (les groupes A profil, s'il y en a, passent APRES lui). L'offline la donne.
    off_ltgb = sorted({v for v, _p, _n in off_f})
    nw = sorted({n for _v, _p, n in off_f})
    if armed and len(nw) == 1 and nw[0] < base + 1:
        i = nw[0]
        vals = [a[i] for a in armed]
        base_vals = [a[i] for a in plain]
        print(f"\nLIVE, evenement d'index {i} (= juste apres les {i} coups d'arme) :")
        print(f"  attaques ARMEES : {vals}  -> distinct={sorted(set(vals))}")
        print(f"  attaques NUES   : {base_vals} (aucun coup LetTheGalaxyBurn a cet index)")
        # ATTENTION au confond `UnitFlag.Moved` : le probe DEPLACE l'attaquant a chaque tour, mais
        # pas au premier -> `HeavyWeapon_ExtraDmg` (x1.25) n'est pas encore pose. La valeur reste
        # DETERMINISTE, elle suit simplement les %-mods de l'attaque : reduce(base) sans le x1.25
        # puis avec. C'est pourquoi on compte les valeurs DISTINCTES (<= 2), pas une constante unique.
        print(f"  offline (attaquant deplace) = {off_ltgb} ; live distinct = {sorted(set(vals))} "
              f"-> {len(set(vals))} valeur(s) pour {len(vals)} attaques "
              f"(coups d'arme de la meme attaque : {len(wpn)} valeurs distinctes)")


if __name__ == "__main__":
    main()
