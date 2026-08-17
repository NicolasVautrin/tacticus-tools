#!/usr/bin/env python
"""Probe #217 — validation live de TheQuickening (active 1151, bloodMephiston).

`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$ExecuteBehaviour` : cast TILE-TARGET. Le caster se TELEPORTE sur la tuile
ciblee (portee-mouvement 2) ; l'unite presente y est ECHANGEE vers la tuile d'origine du caster ; puis
caster + unite-echangee (SI BloodAngels, `HasFaction 0xe=14`) attaquent en melee depuis leur nouvelle
position, Attack OVERRIDE par `IdunBattleLogic.Entities.DSLFormulas$$PercentageOfAttackCappedAtMax` = min(maxDmg[lvl]xmult,
round(Attack x dmgPct[lvl]/100)).

LOIS MESUREES (parse de la CASCADE BRUTE du cast) :
  A. SWAP : POST decisionView -> caster occupe la tuile ciblee ; l'ally occupe la tuile d'origine du caster.
  B. EFFETS TRANSITOIRES (net-zero) : Untargetable(0x414)/ForcedInMelee(0x529)/TemporaryStatOverride(0x510)
     sont AJOUTES (step 16/18) ET RETIRES (step 17/19) DANS le cast -> AUCUN effet persistant apres.
  C. OVERRIDE : le `UnitStats_Attack_Override` pose (step 13) par unite BloodAngels == la formule config
     calculee OFFLINE (mirror `_quickening_override`), du caster ET de l'ally echange.
  D. CONFRONTATION OFFLINE : `load_state` du snapshot PRE-cast + rejoue le message d'ability offline (mon
     port) -> le SWAP offline == le SWAP live (positions).

ASCII only (cp1252). Usage: python probe_217_thequickening.py [--seed 31337]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
import stream_events as SE  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_a217_quick_state.json"
MEPH_VIS = "bloodMephiston"
ALLY_VIS = "bloodIntercessor"     # allie BloodAngels (echange + free-attack faction-14)
ENEMY_VIS = "necroWarden"
ABILITY = 1151
W, H = 7, 9


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int) -> int:
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67",
         "--p-units", f"{MEPH_VIS},{ALLY_VIS}",
         "--a-units", f"{ENEMY_VIS},{ENEMY_VIS}",
         "--hp-target", "300000", "--hp-player", "300000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[217] build KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def _pos(u: dict) -> tuple:
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _units(dec: dict, vis=None) -> list:
    out = [u for u in (dec.get("units") or []) if u.get("alive")]
    return [u for u in out if u.get("visualId") == vis] if vis else out


def _free_tiles(dec) -> set:
    occ = {_pos(u) for u in (dec.get("units") or []) if u.get("alive")}
    return {(c, r) for c in range(W) for r in range(H)} - occ


def _apply(rpc, rid, action, t=240) -> dict:
    return rpc("applyAction", {"runnerId": rid, "action": action}, t)


def _move(rpc, rid, uid, tile) -> bool:
    r = _apply(rpc, rid, {"kind": "move", "unitId": uid,
                          "to": {"col": int(tile[0]), "row": int(tile[1])}}, 120)
    return bool(((r or {}).get("actions") or [{}])[0].get("ok"))


def _my_turn(rpc, rid, vis, mx=12):
    for _ in range(mx):
        dec = rpc("decisionView", {"runnerId": rid}, 150)
        u = next((x for x in (dec.get("units") or [])
                  if x.get("visualId") == vis and x.get("alive")), None)
        if u is not None and dec.get("currentPlayer") == u.get("owner"):
            return dec, u
        rpc("aiPlayTurn", {"runnerId": rid}, 240)
        d2 = rpc("decisionView", {"runnerId": rid}, 90)
        if u is not None and isinstance(d2, dict) and d2.get("currentPlayer") != u.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def _end_round(rpc, rid, my_owner) -> None:
    for _ in range(4):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        dec = rpc("decisionView", {"runnerId": rid}, 90)
        if isinstance(dec, dict) and dec.get("ok") and dec.get("currentPlayer") != my_owner:
            rpc("aiPlayTurn", {"runnerId": rid}, 300)
            return


def _cascade(r) -> list:
    out = list(r.get("cascade") or [])
    for a in (r.get("actions") or []):
        out += list(a.get("events") or [])
    return out


def _tags(ev) -> dict:
    try:
        return json.loads(ev.get("tags") or "{}")
    except Exception:
        return {}


# effets transitoires attendus (net-zero) : nom de groupe src -> il doit etre AJOUTE ET RETIRE
_TRANSIENT = {"Untargetable", "ForcedInMelee", "TemporaryStatOverride"}


def _parse_cast(cascade: list) -> dict:
    """De la cascade du cast : effets transitoires (add/remove par Effect_Id) + overrides Attack par unite.
    add = `ReceiveEffect`/`ActivateEffect` sous group `Effect_Refresh` src=<name> ; remove =
    `LoseEffect`/`DeactivateEffect` (Effect_Id). override = `ChangeStats` UnitStats_Attack_Override > 0
    (la pose ; -2147483648 = retrait).

    Les pas sont resolus PAR NOM (#254b-b) : ecrits en dur avec les ordinaux de `gqfc5mff6c`, les
    cinq filtres de ce parseur designaient depuis la MAJ `rnca9r7q6c` les pas VOISINS (l'ajout lisait
    `LoseEffect`/`DeactivateEffect`, le retrait `ActivateEffect`/`UpdateEffect`, l'override
    `ChangeAbility`) -- add et remove etaient donc INTERVERTIS, sans erreur ni trace."""
    out = {"eff_name": {}, "eff_added": set(), "eff_removed": set(), "overrides": {}}
    s_add = (SE.step_id("ReceiveEffect"), SE.step_id("ActivateEffect"))
    s_remove = (SE.step_id("LoseEffect"), SE.step_id("DeactivateEffect"))
    s_change_stats = SE.step_id("ChangeStats")
    g_effect_refresh = SE.group_id("Effect_Refresh")
    stack: list = []
    for ev in cascade:
        k = ev.get("kind")
        if k == "group":
            stack.append((ev.get("group"), ev.get("source"), ev.get("entity")))
            continue
        if k == "finish":
            if stack:
                stack.pop()
            continue
        t = _tags(ev)
        eid = t.get("Effect_Id")
        cur_src = next((s for (g, s, _e) in reversed(stack) if g == g_effect_refresh), None)
        step = ev.get("step")
        if eid is not None and cur_src is not None:
            out["eff_name"][eid] = cur_src
        if step in s_add and eid is not None:
            out["eff_added"].add(eid)
        if step in s_remove and eid is not None:
            out["eff_removed"].add(eid)
        if step == s_change_stats and "UnitStats_Attack_Override" in t:
            v = int(t["UnitStats_Attack_Override"])
            if v > 0:
                out["overrides"][ev.get("entity")] = v
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=31337)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    rpc = lambda m, b, t=90: _r(sid, m, b, t)   # noqa: E731
    print(f"[217] seed={args.seed} runner={rid}")
    from engine.entities.effects.magnitude import ability_var
    fails: list = []
    try:
        # --- drive : meph + ally A PORTEE <=2 l'un de l'autre ET PRES d'un ennemi (cast legal :
        #     TheQuickening ne se caste que sur une tuile d'ou l'on peut attaquer) -------------------
        dec, meph = _my_turn(rpc, rid, MEPH_VIS)
        if meph is None:
            print("[217] Mephiston introuvable -> stop"); return 2
        for rnd in range(12):
            dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            meph = next(iter(_units(dec, MEPH_VIS)), None)
            ally = next(iter(_units(dec, ALLY_VIS)), None)
            wardens = _units(dec, ENEMY_VIS)
            if meph is None or ally is None or not wardens:
                print("[217] unite perdue -> stop"); return 2
            mp, apos = _pos(meph), _pos(ally)
            wp = [_pos(w) for w in wardens]
            d_ma = hexgeo.distance(mp, apos)
            enemy_near_ally = any(hexgeo.distance(apos, w) <= 2 for w in wp)
            if d_ma <= 2 and enemy_near_ally and dec.get("currentPlayer") == meph.get("owner"):
                break
            if dec.get("currentPlayer") == meph.get("owner"):
                goalw = min(wp, key=lambda p: hexgeo.distance(apos, p))
                # deplacer l'ally vers un warden (a dist ~2) puis meph vers l'ally (a dist ~2)
                ft = _free_tiles(dec)
                acand = sorted([t for t in hexgeo.disk(apos[0], apos[1], 3) if t in ft],
                               key=lambda t: abs(hexgeo.distance(t, goalw) - 2))
                for t in acand[:6]:
                    if _move(rpc, rid, ally["id"], t):
                        break
                dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
                ally = next(iter(_units(dec, ALLY_VIS)), None); apos = _pos(ally)
                ft = _free_tiles(dec)
                mcand = sorted([t for t in hexgeo.disk(mp[0], mp[1], 3) if t in ft],
                               key=lambda t: abs(hexgeo.distance(t, apos) - 2))
                for t in mcand[:6]:
                    if _move(rpc, rid, meph["id"], t):
                        break
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            _end_round(rpc, rid, meph.get("owner"))
            dec, meph = _my_turn(rpc, rid, MEPH_VIS)
            if meph is None:
                print("[217] meph perdu au drive -> stop"); return 2

        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        meph = next(iter(_units(dec, MEPH_VIS)), None)
        ally = next(iter(_units(dec, ALLY_VIS)), None)
        mp, apos = _pos(meph), _pos(ally)
        print(f"[217] positions PRE: meph={mp} ally={apos} d={hexgeo.distance(mp, apos)}")
        # snapshot PRE-cast pour la confrontation offline
        ob_pre = rpc("observeBattle", {"runnerId": rid}, 40)
        snap_pre = rpc("combatSnapshot", {"runnerId": rid}, 40)
        dv_pre = dec

        # --- A. cast 1151 sur la tuile de l'ally (echange) ------------------------------------------
        r = _apply(rpc, rid, {"kind": "ability", "casterId": meph["id"],
                              "to": {"col": apos[0], "row": apos[1]}, "abilityType": ABILITY})
        if not ((r or {}).get("actions") or [{}])[0].get("ok"):
            print("[217] A cast KO"); return 2
        pc = _parse_cast(_cascade(r))

        dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        meph2 = next(iter(_units(dec2, MEPH_VIS)), None)
        ally2 = next(iter(_units(dec2, ALLY_VIS)), None)
        mp2, ap2 = _pos(meph2), _pos(ally2)
        ok_swap = (mp2 == apos and ap2 == mp)
        print(f"[217] A SWAP: meph {mp}->{mp2} ; ally {apos}->{ap2} : {'OK' if ok_swap else 'X'}")
        if not ok_swap:
            fails.append("A:swap")

        # --- B. effets transitoires : chaque effet transitoire AJOUTE est aussi RETIRE (net-zero) ---
        trans_ids = [eid for eid, nm in pc["eff_name"].items() if nm in _TRANSIENT]
        leaked = [eid for eid in trans_ids
                  if eid in pc["eff_added"] and eid not in pc["eff_removed"]]
        print(f"[217] B effets transitoires {[(eid, pc['eff_name'][eid]) for eid in trans_ids]}")
        print(f"[217] B net-zero (aucun effet transitoire persistant): {'OK' if not leaked else 'X ' + str(leaked)}")
        if leaked:
            fails.append("B:leak")
        # garde-fou : aucun effet transitoire visible dans decisionView post
        for u in (meph2, ally2):
            effs = [e for e in (u.get("effects") or [])]
            if effs:
                print(f"[217] B effets residuels sur {u.get('visualId')}: {effs}")

        # --- C. override Attack : formule config == valeur live, du caster ET de l'ally -------------
        from engine.runner.snapshot import load_state
        from engine.runner.components import StatsComponent
        from engine.entities.stats import StatType
        st = load_state(dv_pre, ob_pre, snap_pre)
        csc = st.get_entity(meph["id"]).get_component(StatsComponent)
        level = getattr(csc.ctx, "active_ability_level", None)
        mult = int(getattr(csc.ctx, "ability_variables_multiplier", 100) or 100)
        pct = ability_var("TheQuickening", "dmgPct", level, multiplier_pct=mult)
        cap = ability_var("TheQuickening", "maxDmg", level, multiplier_pct=mult)
        print(f"[217] C meph ability level={level} mult={mult} dmgPct={pct} maxDmg={cap}")
        for uu, name in ((meph, "meph"), (ally, "ally")):
            sc = st.get_entity(uu["id"]).get_component(StatsComponent)
            atk = int(sc.ctx.stat(StatType.ATTACK))
            V = round(atk * int(pct) / 100.0)
            if cap is not None:
                V = min(V, int(cap))
            live_ovr = pc["overrides"].get(uu["id"])
            ok = live_ovr is not None and int(V) == int(live_ovr)
            print(f"[217] C {name}: Attack={atk} -> V_offline={V} vs live_override={live_ovr}: "
                  f"{'OK' if ok else 'X'}")
            if not ok:
                fails.append(f"C:{name}-override")

        # --- D. confrontation OFFLINE : mon port rejoue le message -> meme SWAP --------------------
        from engine.runner.runner import Runner
        from engine.runner.messages import ActiveAbilityMessage
        from engine.runner.components import PositionComponent
        from engine.entities.pathfinding.board import Board
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym") if (bg and bg.get("tiles")) else None
        if board is not None:
            st.board = board
            tile_id = board.id_at(apos[0], apos[1])   # cast tile-target = tuile de l'ally
            runner = Runner(st).install_default_handlers(20)
            runner.apply(ActiveAbilityMessage(caster_id=meph["id"], target_id=tile_id,
                                              ability_type=ABILITY))
            last = runner.ability_handler.last or {}

            def _tile(uid):
                e = st.get_entity(uid)
                pcp = e.get_component(PositionComponent) if e is not None else None
                return (pcp.col, pcp.row) if pcp is not None else None
            off_meph, off_ally = _tile(meph["id"]), _tile(ally["id"])
            ok_off = (last.get("ported") and off_meph == apos and off_ally == mp)
            print(f"[217] D offline: ported={last.get('ported')} meph->{off_meph} ally->{off_ally} "
                  f"(live meph->{mp2} ally->{ap2}): {'OK' if ok_off else 'X'}")
            if not ok_off:
                fails.append("D:offline-swap")
        else:
            print("[217] D SKIP (boardGraph indispo)")
            fails.append("D:no-board")

        print(f"[217] VERDICT: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}")
        return 0 if not fails else 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
