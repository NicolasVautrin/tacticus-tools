"""#91 -- MESURE des deux etages de `DutyEternal` (1158) que le port ne peut pas deviner :

  A. `GetDynamicInvalidTargetReason` : le natif REFUSE-t-il vraiment une tuile sans aire de 3 ?
     (canal `abilityReason` avec `targetId` = un id de TUILE).
  B. `RemoveMachineOperation` : apres le cast, le natif REFUSE-t-il un nouveau cast de la MoW
     (l'AUTRE ability, `MacroPlasmaIncinerator` 1159) ? -> quel est l'OBSERVABLE du retrait ?

Ces deux points ne se lisent pas au decompile seul : (A) parce que la cascade native peut
court-circuiter avant la regle dynamique quand la cible-tuile n'est pas resolue par le canal, et
(B) parce que `RemoveMachineOperation$$Execute` ne touche NI `ActiveAbilityComponent` NI l'entite --
il DETACHE de la plateforme, et il faut mesurer ce que ce detachement rend observable.

Porteur : `ultraDreadnought` (MoW du pool). Levier munitions : `BC.Player.Players[*].
MachineOfWarAmmo` (meme levier que probe_129). ASCII only.

Usage : python probe_91_duty_eternal.py [--board MC1_67] [--seed 777]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.services import spawn_tile_shape as STS
from rl_collect_batch import _rpc, _resolve_session

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
MOW = "ultraDreadnought"
DUTY_ETERNAL = 1158
MACRO_PLASMA = 1159


def rpc(sid, method, args, timeout=120):
    r = _rpc(sid, method, [args], timeout=timeout)
    return r.get("result", r) if isinstance(r, dict) else r


def make_bc(ammo: int = 9) -> Path:
    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    for _pid, p in ((bc.get("Player") or {}).get("Players") or {}).items():
        if isinstance(p, dict) and p.get("PlayerType") != 2:
            p["MachineOfWarAmmo"] = ammo
    out = ROOT / "logs" / "runners" / f"bc-91-{uuid.uuid4().hex[:8]}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bc), encoding="utf-8")
    return out


def build(seed: str, board: str, bc: Path):
    state = ROOT / "logs" / "runners" / f"st-91-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
         "--seed-bc", str(bc), "--state-file", str(state), "--no-ai",
         "--p-units", "ultraTitus,ultraCalgar", "--a-units", "necroWarden,necroSpyder",
         "--p-mow", MOW],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO:", (p.stderr or p.stdout or "")[-800:])
        return None, state
    return json.loads(state.read_text())["runnerId"], state


def occupants(sid, rid) -> set:
    g = rpc(sid, "boardGraph", {"runnerId": rid})
    return {(t["col"], t["row"]) for t in g["tiles"] if t.get("occupantUnitId") is not None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    a = ap.parse_args()

    sid = _resolve_session()
    rid, state_file = build(a.seed, a.board, make_bc())
    if rid is None:
        return 2
    print(f"[build] runner={rid} board={a.board}")

    view = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
    mows = [m for m in (view.get("mows") or []) if m.get("visualId") == MOW]
    if not mows:
        print("KO: MoW absente de decisionView.mows")
        return 2
    caster, owner = mows[0]["casterId"], mows[0].get("owner")
    g = rpc(sid, "boardGraph", {"runnerId": rid})
    board = Board(g["tiles"])

    # attendre que 1158 soit castable ET que ce soit le tour du proprietaire
    for _ in range(16):
        v = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        ab = next((x for x in (v["mows"][0].get("abilities") or [])
                   if x.get("id") == DUTY_ETERNAL), None)
        ready = ab and ab.get("usable") and ab.get("hasAmmo", True) and not (ab.get("cooldown") or 0)
        if ready and (owner is None or v.get("currentPlayer") == owner):
            break
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}})

    occ = occupants(sid, rid)
    pre_dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
    pre_ob = rpc(sid, "observeBattle", {"runnerId": rid})
    pre_state = load_state(pre_dv, pre_ob, board=board)
    from engine.runner.abilities.ultramarines import DutyEternalAbility
    probe = DutyEternalAbility()

    # ---------------------------------------------------------------- A. regle dynamique
    print("\n=== A. GetDynamicInvalidTargetReason : natif vs port, tuile par tuile ===")
    print("pos        tile  area   port  native")
    agree = disagree = 0
    first_valid = None
    for pos in sorted(board.by_coord):
        tid = board.id_at(pos[0], pos[1])
        if tid is None:
            continue
        area = STS.get_area(board, occ, pos)
        pv = probe.get_dynamic_invalid_target_reason(pre_state, caster, tid)
        nat = rpc(sid, "abilityReason", {"runnerId": rid, "casterId": caster,
                                         "abilityType": DUTY_ETERNAL, "targetId": tid})
        names = " ".join(str(x) for x in (nat.get("reasons") or []))
        ok = bool(names.strip()) == bool(pv)
        agree, disagree = agree + int(ok), disagree + int(not ok)
        if not area and first_valid is None:
            pass
        if area and first_valid is None:
            first_valid = pos
        print(f"{str(pos):10s} {tid:5d} {len(area):5d} {pv:5d}  '{names}'"
              + ("" if ok else "   <-- DESACCORD"))
    print(f"[A] accord={agree} desaccord={disagree}")

    # est-ce que le natif ACCEPTE vraiment un cast sur une tuile sans aire ? (le test decisif)
    dead = next((p for p in sorted(board.by_coord)
                 if board.id_at(p[0], p[1]) is not None and not STS.get_area(board, occ, p)), None)
    if dead is not None:
        r = rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster, "abilityType": DUTY_ETERNAL,
            "to": {"col": dead[0], "row": dead[1]}}})
        acts = r.get("actions") or []
        print(f"[A] cast SUR TUILE SANS AIRE {dead} -> ok={r.get('ok')} "
              f"mutated={acts[0].get('mutated') if acts else None} "
              f"spawned={acts[0].get('spawned') if acts else None} "
              f"consumed={acts[0].get('actionConsumed') if acts else None}")

    # ---------------------------------------------------------------- B. RemoveMachine
    print("\n=== B. RemoveMachineOperation : que devient la MoW apres le cast ? ===")
    anchor = first_valid
    if anchor is None:
        print("KO: aucune ancre valide")
        return 2
    r = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster, "abilityType": DUTY_ETERNAL,
        "to": {"col": anchor[0], "row": anchor[1]}}})
    acts = r.get("actions") or []
    print(f"[B] cast 1158 en {anchor} -> ok={r.get('ok')} "
          f"mutated={acts[0].get('mutated') if acts else None} "
          f"spawned={acts[0].get('spawned') if acts else None}")

    after = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
    row = next((m for m in (after.get("mows") or []) if m.get("casterId") == caster), None)
    print(f"[B] MoW encore dans decisionView.mows ? {row is not None}")
    if row is not None:
        print("[B] abilities:", json.dumps(row.get("abilities") or [])[:400])
    ob = rpc(sid, "observeBattle", {"runnerId": rid})
    print("[B] machine dans observeBattle ?",
          any((u.get("squadId") == caster or u.get("entityId") == caster)
              for u in (ob.get("units") or [])))

    # LE test : le natif accepte-t-il encore un cast de l'AUTRE ability de la MoW retiree ?
    # ANTI-CONFOND OBLIGATOIRE : un refus peut venir du RETRAIT *ou* d'une fenetre fermee
    # (cooldown / ce n'est pas le tour du proprietaire). On mesure donc la FENETRE au moment du
    # cast, et on double d'un runner de CONTROLE ou 1158 n'est jamais caste.
    ok_after, win_after = _try_macro_plasma(sid, rid, caster, owner, board, "APRES retrait")
    rpc(sid, "disposeRunner", {"runnerId": rid})
    try:
        state_file.unlink()
    except OSError:
        pass

    print("\n=== B-controle : MEME cast 1159, MoW NON retiree (1158 jamais caste) ===")
    rid2, sf2 = build(a.seed, a.board, make_bc())
    if rid2 is None:
        return 2
    v2 = rpc(sid, "decisionView", {"runnerId": rid2, "allAbilities": True})
    m2 = [m for m in (v2.get("mows") or []) if m.get("visualId") == MOW]
    g2 = rpc(sid, "boardGraph", {"runnerId": rid2})
    ok_ctrl, win_ctrl = _try_macro_plasma(sid, rid2, m2[0]["casterId"], m2[0].get("owner"),
                                          Board(g2["tiles"]), "CONTROLE")
    rpc(sid, "disposeRunner", {"runnerId": rid2})
    try:
        sf2.unlink()
    except OSError:
        pass

    print(f"\n[VERDICT B] 1159 apres retrait : mute={ok_after} (fenetre {win_after}) | "
          f"controle sans retrait : mute={ok_ctrl} (fenetre {win_ctrl})")
    print("[VERDICT B] le RETRAIT est la cause SSI (controle mute) ET (apres-retrait ne mute pas)")
    return 0


def _try_macro_plasma(sid, rid, caster, owner, board, label):
    """Tente `MacroPlasmaIncinerator` (1159) avec la MoW `caster`, en OUVRANT d'abord la fenetre
    (cooldown a 0 + tour du proprietaire) et en la RAPPORTANT : sans ca, un refus est
    inattribuable (retrait vs fenetre fermee). Rend `(mutated, fenetre_ouverte)`."""
    window = False
    for _ in range(12):
        v = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        rw = next((m for m in (v.get("mows") or []) if m.get("casterId") == caster), None)
        ab = next((x for x in ((rw or {}).get("abilities") or [])
                   if x.get("id") == MACRO_PLASMA), None)
        ready = bool(ab and ab.get("usable") and ab.get("hasAmmo", True)
                     and not (ab.get("cooldown") or 0))
        if ready and (owner is None or v.get("currentPlayer") == owner):
            window = True
            break
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}})
    tgt = sorted(board.by_coord)[len(board.by_coord) // 2]
    r = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster, "abilityType": MACRO_PLASMA,
        "to": {"col": tgt[0], "row": tgt[1]}}})
    acts = r.get("actions") or []
    act = acts[0] if acts else {}
    print(f"[B/{label}] fenetre_ouverte={window} cible={tgt} -> ok={r.get('ok')} "
          f"mutated={act.get('mutated')} consumed={act.get('actionConsumed')} "
          f"changes={len(act.get('changes') or [])} events={len(act.get('events') or [])}")
    if act.get("changes"):
        print(f"[B/{label}] changes:", json.dumps(act["changes"])[:300])
    return bool(act.get("mutated")), window


if __name__ == "__main__":
    raise SystemExit(main())
