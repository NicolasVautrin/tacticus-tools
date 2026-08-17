#!/usr/bin/env python
"""Probe #45f — cause racine du residu x1.5 GreatFrostAxe (case-220 SW / fable effect-damage-bonus).

HYPOTHESE (decompile) : le +50% mesure (live = 1.5x offline par coup, DidCrit=0) N'EST PAS le bonus
crit-sur-Ice (`IdunBattle.Entities.Effects.IceEffect$$CreateEffectDamageBonusForAttack` = EffectBonus.addition
`PercentageOf(StatAmount(attacker, CRIT_DAMAGE=10), EffectConfig(5)=IceCritDmgBonusPct=25)` gate
`AttackDamageIsCritical & AreEqual(occupant,target) & !HasTrait(target,0x19=Immune)` -> 0 pour un
attaquant cd=0, et crit-gated) mais le bonus d'ELEVATION (`Damage.ElevationBonus=50`, feuille du
builder PARTAGE `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction`, gate `elev(att) > elev(cible)`
SANS distinction normale/ability) que le chemin offline `execute_ability_attack`/`execute_normal_like`
n'applique PAS (fork de port : seul `execute` normal appelle `apply_elevation_bonus`, damage.py:406).

DISCRIMINANT (une variable = la relation d'elevation, positions FORCEES par applyAction) :
  high : tuile d'attaque PLUS HAUTE que la cible  -> attendu live = 1.5x offline (pre-fix), bit-exact (post-fix)
  flat : meme elevation                            -> attendu live == offline (ratio 1.0) AVANT ET APRES fix
  low  : tuile d'attaque PLUS BASSE                -> attendu ratio 1.0 (aucun malus, gate strict `>`)
  crit : --crit 100,700 + flat -> chaque coup crit ; bonus crit-sur-Ice REEL attendu live =
         roll + 700 (crit flat) + floor(700*25/100)=175 (Ice addition, cible gelee par GFA) ;
         discrimine la formule Ice (25% du CRIT_DAMAGE) une fois le crit force.

  immune : gate `!HasTrait(target, 0x19=Immune)` -- AUCUN porteur Immune spawnable (pool rank 17 =
         97 unites regulieres, Immune = bosses/NPC only) -> discriminant OFFLINE-PIPELINE : meme
         build que crit, DOUBLE replay offline (a) tel-quel -> bit-exact vs live ; (b) trait Immune
         INJECTE sur la cible offline -> chaque coup crit doit tomber a live-175 (le gate porte
         est CABLE dans le pipeline reel, pas seulement dans la fonction). La face NATIVE du gate
         reste decompile-only (IdunBattle.Entities.Effects.IceEffect$$CreateEffectDamageBonusForAttack : op_LogicalNot(HasTrait(target,0x19))).

Usage : python probe_45f_gfa_elevation.py [--case high|flat|low|crit|immune|all]
ASCII only (cp1252). State-file UNIQUE par cas ; dispose au teardown.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

from engine.runner.snapshot import load_state                     # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister            # noqa: E402
from engine.entities.pathfinding.board import Board               # noqa: E402
from engine.runner.abilities.spacewolves import great_frost_axe_ice_tiles, ICE_TILE  # noqa: E402
from engine.entities.behaviours import op_and, If                 # noqa: E402
from engine.entities.selectors.accessors import Target  # noqa: E402
from engine.entities.triggers import IsAlive                      # noqa: E402
from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.runner.abilities.behaviours.effects import AddEffect  # noqa: E402
from engine.dsl.effects import ExecutionContext                   # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
CASTER_VIS = "spaceWulfen"
ABILITY = 1089
A_UNITS = "necroOverlord,necroWarden,necroWarden"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _by_id(dec, uid):
    return next((u for u in (dec.get("units") or []) if u.get("id") == uid), None)


def _tags(e):
    tg = e.get("tags")
    return (json.loads(tg) if isinstance(tg, str) else tg) or {}


def build(sid, seed: int, tag: str, extra: list) -> tuple:
    state = ROOT / "logs" / "runners" / f"p45f-{tag}-{uuid.uuid4().hex[:6]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(state),
         "--board", "MC1_67", "--roster", "1", "--p-units", CASTER_VIS, "--a-units", A_UNITS,
         "--hp-target", "300000", "--hp-player", "300000"] + extra,
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print(f"[45f] build {tag} KO: {(proc.stderr or proc.stdout or '')[-400:]}")
        sys.exit(2)
    return json.loads(state.read_text())["runnerId"], state


def _pick_tiles(bg, occupied, relation: str):
    """Choisit (tuile_cible, tuile_attaque) ADJACENTES, walkables, libres, avec la relation
    d'elevation demandee (high: att>cible ; flat: == ; low: att<cible)."""
    tiles = {t["id"]: t for t in bg["tiles"]}
    for t in bg["tiles"]:
        if not t.get("walkable") or (t["col"], t["row"]) in occupied:
            continue
        for nid in (t.get("neighbours") or []):
            n = tiles.get(nid)
            if n is None or not n.get("walkable") or (n["col"], n["row"]) in occupied:
                continue
            et, en = t.get("elevation") or 0, n.get("elevation") or 0
            if relation == "high" and en > et:
                return t, n
            if relation == "flat" and en == et:
                return t, n
            if relation == "low" and en < et:
                return t, n
    return None, None


def _offline_per_hit(dec1, ob1, snap1, bg, s_cast, cid, eid, inject_immune=False):
    st = load_state(dec1, ob1, snap1)
    if inject_immune:
        # discriminant OFFLINE du gate !HasTrait(0x19) : la cible devient Immune dans le state
        # offline SEULEMENT -> le bonus Ice (+cd*25%) doit disparaitre de la branche crit.
        from engine.runner.components import StatsComponent
        sc = st.get_entity(eid).get_component(StatsComponent)
        sc.ctx.traits = list(getattr(sc.ctx, "traits", None) or []) + ["Immune"]
    st.board = Board(bg["tiles"], adjacency="native_sym")
    rng = IntBasedMersenneTwister()
    rng.mt = list(s_cast["mt"]); rng.mti = s_cast["mti"]
    st.rng = rng
    tgt = Target()
    ice = AddEffect(ICE_TILE, "Ice", great_frost_axe_ice_tiles(), duration_rounds=None)
    attack = AttackWithAttackDamage(tgt, "GreatFrostAxe", "Piercing", is_melee=True,
                                    native_factory="attack", ability_type=ABILITY)
    tree = op_and(ice, If(IsAlive(tgt), attack))
    ectx = ExecutionContext(state=st, rng=st.rng)
    tree.execute(entities_from_state(st, cid, eid), ectx)
    ma = next((p.get("attack") for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
    return (ma or {}).get("per_hit") or [], (ma or {}).get("crits") or []


def run_case(sid, case: str, seed: int):
    relation = "flat" if case in ("crit", "immune") else case
    extra = ["--crit", "100,700"] if case in ("crit", "immune") else []
    target_vis = "necroWarden"
    rid, state_file = build(sid, seed, case, extra)
    rpc = lambda m, b, t=90: (_rpc(sid, m, [dict(b)], timeout=t).get("result") or {})
    try:
        # avancer jusqu'au tour du caster (sans laisser l'IA jouer notre camp : endturn adverses)
        caster = None
        for _ in range(16):
            dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            if not _ok(dec):
                print(f"[45f:{case}] decisionView KO"); return None
            caster = _find(dec, CASTER_VIS)
            if caster is None:
                print(f"[45f:{case}] caster absent"); return None
            if caster.get("owner") == dec.get("currentPlayer"):
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        else:
            print(f"[45f:{case}] tour caster jamais atteint"); return None
        cid = caster["id"]
        target = next((u for u in (dec.get("units") or [])
                       if u.get("alive") and u.get("owner") != caster.get("owner")
                       and u.get("visualId") == target_vis), None)
        if target is None:
            print(f"[45f:{case}] cible absente ({target_vis})"); return None
        eid = target["id"]
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print(f"[45f:{case}] boardGraph KO"); return None
        occupied = {(u.get("pos") or {}).get("col") is not None and
                    ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
                    for u in (dec.get("units") or []) if u.get("alive")}
        occupied.discard(False)
        tt, ta = _pick_tiles(bg, occupied, relation)
        if tt is None:
            print(f"[45f:{case}] aucune paire de tuiles {relation} libre"); return None
        # positions forcees (drive-positions) : cible sur tt, caster sur ta (adjacents)
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": eid, "to": {"col": tt["col"], "row": tt["row"]}}}, 90)
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cid, "to": {"col": ta["col"], "row": ta["row"]}}}, 90)
        dec1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob1 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap1 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s_cast = rpc("dumpRng", {"runnerId": rid}, 30)
        if snap1 is None or not _ok(s_cast):
            print(f"[45f:{case}] snapshot/dumpRng KO"); return None
        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": eid, "abilityType": ABILITY},
            "captureEvents": True}, 120)
        if not _ok(cast):
            print(f"[45f:{case}] cast KO: {str(cast)[:200]}"); return None
        a0 = (cast.get("actions") or [{}])[0]
        live = [{"amt": int(_tags(e).get("Amount") or 0), "crit": int(_tags(e).get("Attack_DidCrit") or 0)}
                for e in (a0.get("events") or [])
                if _tags(e).get("Target_Id") == eid and "Amount" in _tags(e)
                and _tags(e).get("Active_Ability_Type") == ABILITY]
        off_ph, off_crits = _offline_per_hit(dec1, ob1, snap1, bg, s_cast, cid, eid)
        et, ea = tt.get("elevation") or 0, ta.get("elevation") or 0
        cc = "100,700" if case in ("crit", "immune") else "0"
        print(f"[45f:{case}] elev att={ea} cible={et} ({relation})  cc_case={cc}")
        print(f"[45f:{case}] live per-hit = {[h['amt'] for h in live]}  crits={[h['crit'] for h in live]}")
        print(f"[45f:{case}] off  per-hit = {off_ph}  crits={[int(c) for c in off_crits]}")
        for i, h in enumerate(live):
            if i < len(off_ph) and off_ph[i]:
                print(f"[45f:{case}]   hit{i}: live={h['amt']} off={off_ph[i]} "
                      f"ratio={h['amt']/off_ph[i]:.4f} delta={h['amt']-off_ph[i]}")
        if case == "immune":
            # replay (b) : trait Immune injecte cote OFFLINE -> attendu off_imm = live - 175 par coup crit
            off_imm, _ = _offline_per_hit(dec1, ob1, snap1, bg, s_cast, cid, eid, inject_immune=True)
            print(f"[45f:immune] off(Immune inj) = {off_imm}")
            for i, h in enumerate(live):
                if i < len(off_imm) and off_imm[i]:
                    print(f"[45f:immune]   hit{i}: live={h['amt']} off_imm={off_imm[i]} "
                          f"delta={h['amt']-off_imm[i]} (attendu +175 par coup crit)")
        return live, off_ph
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            state_file.unlink()
        except Exception:
            pass


def _offline_storm_per_hit(dec1, ob1, snap1, bg, s_cast, cid, eid):
    """Rejoue l'arbre Stormcaller (famille ABILITY IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage) -> {target_id: per_hit}."""
    from engine.runner.abilities.loki.stormcaller import stormcaller_tree
    st = load_state(dec1, ob1, snap1)
    st.board = Board(bg["tiles"], adjacency="native_sym")
    rng = IntBasedMersenneTwister()
    rng.mt = list(s_cast["mt"]); rng.mti = s_cast["mti"]
    st.rng = rng
    ectx = ExecutionContext(state=st, rng=st.rng)
    stormcaller_tree().execute(entities_from_state(st, cid, eid), ectx)
    out = {}
    for n, p in ectx.emitted:
        if n == "AttackWithAttackDamage" and p.get("attack"):
            out[p.get("target")] = {"per_hit": p["attack"].get("per_hit") or [],
                                    "crits": p["attack"].get("crits") or []}
    return out


def run_scrit(sid, seed: int):
    """Cas SCRIT : Stormcaller (famille ABILITY) + crit force (--crit 100,700) + paire FLAT.
    Discrimine si le bonus crit-sur-Ice s'applique aussi a la famille ABILITY (live vs offline :
    delta 0 = oui comme le port ; delta -175 par coup crit = non -> gater par famille)."""
    state = ROOT / "logs" / "runners" / f"p45f-scrit-{uuid.uuid4().hex[:6]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(state),
         "--board", "MC1_67", "--roster", "1", "--p-units", "spaceStormcaller",
         "--a-units", A_UNITS, "--hp-target", "300000", "--hp-player", "300000",
         "--crit", "100,700"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print(f"[45f:scrit] build KO: {(proc.stderr or proc.stdout or '')[-400:]}")
        return None
    rid = json.loads(state.read_text())["runnerId"]
    rpc = lambda m, b, t=90: (_rpc(sid, m, [dict(b)], timeout=t).get("result") or {})
    try:
        caster = None
        for _ in range(16):
            dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            if not _ok(dec):
                print("[45f:scrit] decisionView KO"); return None
            caster = _find(dec, "spaceStormcaller")
            if caster is None:
                print("[45f:scrit] caster absent"); return None
            if caster.get("owner") == dec.get("currentPlayer"):
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        else:
            print("[45f:scrit] tour caster jamais atteint"); return None
        cid = caster["id"]
        target = next((u for u in (dec.get("units") or [])
                       if u.get("alive") and u.get("owner") != caster.get("owner")
                       and u.get("visualId") == "necroWarden"), None)
        if target is None:
            print("[45f:scrit] cible absente"); return None
        eid = target["id"]
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print("[45f:scrit] boardGraph KO"); return None
        occupied = {((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
                    for u in (dec.get("units") or []) if u.get("alive") and u.get("pos")}
        tt, ta = _pick_tiles(bg, occupied, "flat")
        if tt is None:
            print("[45f:scrit] aucune paire flat libre"); return None
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": eid, "to": {"col": tt["col"], "row": tt["row"]}}}, 90)
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cid, "to": {"col": ta["col"], "row": ta["row"]}}}, 90)
        dec1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob1 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap1 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s_cast = rpc("dumpRng", {"runnerId": rid}, 30)
        if snap1 is None or not _ok(s_cast):
            print("[45f:scrit] snapshot/dumpRng KO"); return None
        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": eid, "abilityType": 1113},
            "captureEvents": True}, 120)
        if not _ok(cast):
            print(f"[45f:scrit] cast KO: {str(cast)[:200]}"); return None
        a0 = (cast.get("actions") or [{}])[0]
        live: dict = {}
        for e in (a0.get("events") or []):
            tg = _tags(e)
            if "Amount" in tg and tg.get("Active_Ability_Type") == 1113:
                live.setdefault(tg.get("Target_Id"), []).append(
                    {"amt": int(tg.get("Amount") or 0), "crit": int(tg.get("Attack_DidCrit") or 0)})
        off = _offline_storm_per_hit(dec1, ob1, snap1, bg, s_cast, cid, eid)
        et, ea = tt.get("elevation") or 0, ta.get("elevation") or 0
        print(f"[45f:scrit] elev caster={ea} cible={et} (flat) cc=100,700 famille=ABILITY")
        for uid in sorted(set(live) | set(off)):
            lp = [h["amt"] for h in live.get(uid, [])]
            lc = [h["crit"] for h in live.get(uid, [])]
            op = (off.get(uid) or {}).get("per_hit") or []
            oc = [int(c) for c in ((off.get(uid) or {}).get("crits") or [])]
            print(f"[45f:scrit]   u{uid}: live={lp} crits={lc} | off={op} crits={oc} "
                  f"deltas={[a - b for a, b in zip(lp, op)]}")
        return live, off
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            state.unlink()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="all",
                    choices=["high", "flat", "low", "crit", "immune", "scrit", "all"])
    ap.add_argument("--seed", type=int, default=45001)
    args = ap.parse_args()
    sid = _resolve_session()
    cases = ["high", "flat", "low", "crit"] if args.case == "all" else [args.case]
    for i, c in enumerate(cases):
        if c == "scrit":
            run_scrit(sid, args.seed + i)
        else:
            run_case(sid, c, args.seed + i)


if __name__ == "__main__":
    main()
