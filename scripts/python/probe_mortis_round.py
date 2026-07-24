#!/usr/bin/env python
"""Validation MortisRound (1004, ultraEliminatorSgt « Eliminator Sergeant ») -- face COMBAT (execute) portee.

Port = `MortisRoundAbility.execute_behaviour` (arbre `mortis_round_tree`, ultramarines.py) :
  AtomicGroup( op_and( AttackWithAttackDamage(target, HeavyRound, nrOfHits=1, ranged),   # attaque mono-cible
                       PushUnit(caster, target) ) )                                        # recul 1 hex

RE : `MortisRoundAbility$$ExecuteBehaviour @1811f54a0` (callback `b__0 @1811fd290`) = AtomicGroup(0x3f,
callback) ou le callback Execute(attack) PUIS Execute(push). Overload attaque = @180dea520 (famille ATTACK,
resolu par XREF du call-site @1811f5683). Profil HeavyRound (constants.damageProfile), ranged (range 3),
nrOfHits ABSENT config -> hits=1 (i2 « 1x 3274-3638 ... pushed back 1 hex »).

(A) WIRING PUSH+ATTAQUE (OFFLINE deterministe, board+stats REELS) : place caster+cible ADJACENTS en champ
    ouvert (tuile libre derriere la cible, oppose caster) sur l'etat charge, rejoue le MESSAGE d'ability, et
    confronte : cible poussee d'1 hex a l'oppose du caster (DisplaceUnitOperation) + attaque MONO-cible 1 coup.
(C) RESIDU HeavyWeapon double (LIVE, caracterisation) : l'Eliminator porte le trait HeavyWeapon -> effet 1008
    HeavyWeapon_ExtraDmg ACTIF (seede). i2 « The Heavy Weapon trait applies double to this ability » : le natif
    DOUBLE le bonus +heavyWeaponExtraDmg% via `TriggeringAbilityIs(0x3ec=1004)` dans
    `HeavyWeapon_ExtraDmgEffect.CreateDamageModifier @180f4f030`. Le PORT n'applique PAS ce bonus aux attaques
    d'ability (is_ranged non threade dans `execute_ability_attack` -> HeavyWeapon/RangedSpecialist inertes pour
    TOUTE attaque d'ability : blast radius ArmoriumCherub/SpiritLeech/PlasmaCannon). RESIDU CROSS-CUTTING
    documente (candidat) -- PAS un echec du wiring core.

State-file UNIQUE. ASCII only. Usage : python probe_mortis_round.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import hexgeo  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "rl-state" / "mortisround-4b1c7d20.json"
CASTER_VIS = "ultraEliminatorSgt"
TARGET_VIS = "necroWarden"
ABILITY = 1004
HEAVY_WEAPON_EFFECT = 1008


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _by_id(dec, uid):
    return next((u for u in (dec.get("units") or []) if u.get("id") == uid), None)


def _effids(u):
    return {e.get("effectType") for e in ((u or {}).get("effects") or []) if e.get("effectType") is not None}


def _pos(u):
    p = (u or {}).get("pos")
    return (p.get("col"), p.get("row")) if isinstance(p, dict) else None


def main():
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import PositionComponent
    from engine.entities.pathfinding.board import Board
    from engine.runner.abilities.ultramarines import MortisRoundAbility
    from engine.runner.abilities.base import ability_attack_params
    from engine.runner.operations.displace import _dir_index, _step

    def _seed_rng(s):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s["mt"]); rng.mti = s["mti"]
        return rng

    sid = _resolve_session()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    build = ["--roster", "1", "--p-units", CASTER_VIS, "--a-units", f"{TARGET_VIS},necroDestroyer",
             "--hp-target", "80000"]                 # cible tanky armure 0 : survit + pas de confond armure
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "909",
         "--state-file", str(STATE), "--board", "MC1_67", *build],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-400:]); return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    print("runnerId", rid)
    fails = []
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print("SKIP: boardGraph indispo"); return 0
        board = Board(bg["tiles"], adjacency="native_sym")
        dec0 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob0 = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap0 = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
        caster = _find(dec0, CASTER_VIS)
        target = _find(dec0, TARGET_VIS)
        if caster is None or target is None:
            print("SKIP: caster/cible absents (non spawnable ?)"); return 0
        cid, eid = caster["id"], target["id"]
        third = next((u for u in (dec0.get("units") or [])
                      if u.get("alive") and u.get("id") not in (cid, eid)), None)
        tid3 = (third or {}).get("id")

        # ---------- (A) WIRING (OFFLINE, positions controlees) ----------
        # triplet (C caster, T cible adjacente, B derriere-oppose) en champ ouvert
        def _triple():
            for T in sorted(board.by_id):
                if not board.walkable(T):
                    continue
                for C in board.neighbours(T):
                    if not board.walkable(C) or C == T:
                        continue
                    cc, tc = board.coord(C), board.coord(T)
                    di = _dir_index(cc[0], cc[1], tc[0], tc[1])
                    if di is None:
                        continue
                    bcol, brow = _step(tc[0], tc[1], di)
                    B = board.id_at(bcol, brow)
                    if B is None or B in (T, C) or not board.walkable(B):
                        continue
                    return C, T, B
            return None
        tri = _triple()
        if tri is None:
            print("SKIP: aucun triplet (caster, cible adjacente, derriere) ouvert"); return 0
        C, T, B = tri
        cc, tc, bc = board.coord(C), board.coord(T), board.coord(B)

        s0 = _r(sid, "dumpRng", {"runnerId": rid}, 30)          # rng pour executer l'attaque offline
        st = load_state(dec0, ob0, snap0); st.board = board
        if isinstance(s0, dict) and s0.get("mt"):
            st.rng = _seed_rng(s0)
        ca, ta = st.get_entity(cid), st.get_entity(eid)
        cpc = ca.get_component(PositionComponent) if ca else None
        tpc = ta.get_component(PositionComponent) if ta else None
        if cpc is None or tpc is None:
            print("SKIP: positions offline non chargees"); return 0
        cpc.col, cpc.row = cc
        tpc.col, tpc.row = tc
        # 3e unite parquee LOIN (garde mono-cible + libere B)
        if tid3 is not None:
            e3 = st.get_entity(tid3)
            p3 = e3.get_component(PositionComponent) if e3 else None
            far = next((t for t in sorted(board.by_id)
                        if board.walkable(t) and t not in (C, T, B)
                        and hexgeo.distance(board.coord(t), tc) > 4), None)
            if p3 is not None and far is not None:
                p3.col, p3.row = board.coord(far)
        hp3_pre = None
        if tid3 is not None:
            e3 = st.get_entity(tid3)
            from engine.runner.components import HealthComponent
            h3 = e3.get_component(HealthComponent) if e3 else None
            hp3_pre = h3.hp if h3 else None
        bmin, bmax, pierce, hits = ability_attack_params(st, cid, "MortisRound", "HeavyRound", ranged=True)
        print(f"[A wiring] caster@{cc} target@{tc} attendu-derriere@{bc} ; config base=[{bmin},{bmax}] "
              f"pierce={pierce} hits={hits}")

        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=eid, ability_type=ABILITY))
        last = runner.ability_handler.last or {}
        if not last.get("ported"):
            fails.append("A: MortisRound non routee (ported=False)")
        # push geometrique
        ta2 = st.get_entity(eid)
        tpc2 = ta2.get_component(PositionComponent) if ta2 else None
        new_pos = (tpc2.col, tpc2.row) if tpc2 else None
        if new_pos == bc:
            print(f"A OK : PushUnit -> cible poussee {tc} -> {new_pos} (= derriere, oppose caster)")
        else:
            fails.append(f"A: push offline -> {new_pos} != tuile geometrique attendue {bc}")
        # attaque mono-cible 1 coup
        diag = last
        main = diag.get("main_attack") or {}
        per_hit = main.get("per_hit") or []
        off_total = main.get("total")
        if len(per_hit) == 1:
            print(f"B OK : attaque 1 coup total={off_total} (nrOfHits=1)")
        else:
            fails.append(f"B: attaque {len(per_hit)} coups != 1 (total={off_total})")
        if off_total and off_total > 0:
            print(f"B2 OK : degat offline {off_total} > 0 (base config [{bmin},{bmax}], armure 0 ; "
                  f"crit/HeavyWeapon = residu)")
        else:
            fails.append(f"B2: degat offline nul (total={off_total})")
        # mono-cible : 3e non touche
        if tid3 is not None and hp3_pre is not None:
            e3 = st.get_entity(tid3)
            from engine.runner.components import HealthComponent
            h3 = e3.get_component(HealthComponent) if e3 else None
            if h3 is not None and h3.hp == hp3_pre:
                print("B3 OK : mono-cible (3e unite non touchee)")
            elif h3 is not None:
                fails.append(f"B3: 3e unite touchee (hp {hp3_pre} -> {h3.hp}) -- attaque devrait etre mono-cible")

        # ---------- (C) RESIDU HeavyWeapon double (LIVE, caster stationnaire) ----------
        # caster au SPAWN (non deplace = no-move gate satisfait), cible deplacee a portee 3.
        cspawn = _pos(caster)
        cs_tid = board.id_at(cspawn[0], cspawn[1]) if cspawn else None
        Tlive = None
        if cs_tid is not None:
            for n in board.neighbours(cs_tid):            # cible adjacente au spawn (dans range 3)
                if board.walkable(n):
                    Tlive = n; break
        if Tlive is None:
            print("[C residu] SKIP : pas de tuile adjacente au spawn caster pour la cible");
        else:
            tl = board.coord(Tlive)
            if tid3 is not None:                          # park le 3e LOIN (live)
                far = next((t for t in sorted(board.by_id)
                            if board.walkable(t) and hexgeo.distance(board.coord(t), cspawn) > 4), None)
                if far is not None:
                    fc = board.coord(far)
                    _r(sid, "applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": tid3, "to": {"col": fc[0], "row": fc[1]}}}, 90)
            _r(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": eid, "to": {"col": tl[0], "row": tl[1]}}}, 90)
            dec1 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            ob1 = _r(sid, "observeBattle", {"runnerId": rid}, 60)
            snap1 = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
            cu1 = _by_id(dec1, cid)
            hw_active = HEAVY_WEAPON_EFFECT in _effids(cu1)
            print(f"[C residu] caster@{_pos(cu1)} (spawn, non deplace) target@{_pos(_by_id(dec1, eid))} "
                  f"HeavyWeapon_ExtraDmg actif={hw_active}")
            s_cast = _r(sid, "dumpRng", {"runnerId": rid}, 30)
            cast = _r(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": cid, "targetId": eid, "abilityType": ABILITY},
                "captureEvents": True}, 120)
            live_dmg = None
            for act in (cast.get("actions") or []):
                for ch in (act.get("changes") or []):
                    if ch.get("squadId") == eid and ch.get("hpDelta") is not None:
                        live_dmg = -int(ch["hpDelta"])
            # offline meme rng, meme geometrie
            st2 = load_state(dec1, ob1, snap1); st2.board = board
            st2.rng = _seed_rng(s_cast)
            res2 = MortisRoundAbility().execute_behaviour(st2, cid, eid)
            m2 = (res2 or {}).get("main_attack") or {}
            off2 = m2.get("total")
            print(f"[C residu] LIVE dmg={live_dmg}  OFFLINE(no bonus)={off2} off_did_crit={m2.get('did_crit')}")
            if live_dmg and off2:
                print(f"[C residu] ratio live/off={live_dmg/off2:.4f}  "
                      f"(off+50% HeavyWeapon={round(off2*1.5)})")
                print("[C residu] Divergence DAMAGE = confond CROSS-CUTTING (candidat fable) :")
                print("  (1) HeavyWeapon double +50% (TriggeringAbilityIs 1004 @180f4f030) NON applique aux")
                print("      attaques d'ability (is_ranged non threade dans execute_ability_attack ; blast")
                print("      radius ArmoriumCherub/SpiritLeech/PlasmaCannon) ;")
                print("  (2) crit-rng per-hit possiblement desynchronise offline vs live (cf. rngcrit-1202).")

    finally:
        _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)

    print("\n==== RESULT ====")
    if fails:
        for f in fails:
            print("FAIL", f)
        return 2
    print("WIRING PASS (attaque mono-cible 1 coup + push 1 hex oppose) ; residu HeavyWeapon double = documente")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
