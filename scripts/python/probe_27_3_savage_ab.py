"""probe #27-3 -- A/B causal LIVE de SavageEchoes (1230) : le terme custom
`SavageEchoes_DislikesAboveHealthPct` et son seuil `healthPct`.

Montage (une passe par valeur de `--hp-player`) :
  build (bloodTerminator injecte au catalogue) -> place le caster en (4,8) et
  la cible tauCrisis en (5,8) -> mesure les DEUX `pairUtility` natifs (controle
  du confond de prediction) -> lit le choix natif (`aiDryRunAllUnits`) -> fait
  frapper le caster par la cible (une seule fois : `TerminatorArmour` reduit la
  premiere attaque du tour) -> re-mesure les DEUX `pairUtility` + le choix natif.

Le seul input qui change entre les deux mesures d'une passe est le PV% du
CASTER. Des `pairUtility` bit-identiques ferment la porte au confond de
prediction (le heal `ForRegenerate` n'entre pas dans la prediction du playbook).

Usage : python probe_27_3_savage_ab.py <hp-player> [<hp-player> ...]
ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
SEED_BC = LOGS / "bc_savage.json"
STATE = LOGS / "rs_savage_ab.json"
BOARD = "MC1_67"
SEED = 909
CASTER, TARGET = 81, 77


def _run(args):
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=False)


def _runner_id() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _hp(rid):
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    for u in (dv.get("units") or []):
        if u.get("id") == CASTER:
            return u.get("hp")
    return None


def _engine(rid):
    """Decision MOTEUR pour le caster, telle quelle et avec le custom 1230 FORCE a 0
    (test de NECESSITE du terme)."""
    import engine_validate as EV
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)          # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                              "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    # Utilites OFFLINE par ability (etage PAIRE du moteur) -- a confronter aux `pairUtility` natifs.
    from engine.ai import context as AICTX
    from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK
    from engine.playbook import get_playbook_or_default
    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, CASTER, wt, predictor)
    mp = ctx.me.get("pos") or {}
    here = (mp.get("col"), mp.get("row"))
    offline = {}
    for ab in (69, 1230):
        p = NORMAL_ATTACK_PLAYBOOK if ab in ctx.normal_ids else get_playbook_or_default(ab)
        c = p.calculate_action_utility(ctx, here, TARGET, ab)
        offline[ab] = (None if c is None else round(c["u"], 4),
                       p.calculate_custom_utility(ctx, here, TARGET, ab))
    print("      offline u/custom : 69=%s  1230=%s" % (offline[69], offline[1230]))
    a = EV.engine_decide(sid, rid, dv, mov_by_unit, CASTER, wt, predictor)
    pb = PB.REGISTRY.get(1230)
    orig = type(pb).calculate_custom_utility
    type(pb).calculate_custom_utility = (
        lambda self, ctx, tile, target, ability_id: 0.0)
    try:
        b = EV.engine_decide(sid, rid, dv, mov_by_unit, CASTER, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig
    return a.get("ability"), b.get("ability")


def _measure(rid, label, hp_max, engine=False):
    hp = _hp(rid)
    pct = round(hp / hp_max * 100) if hp_max else None
    pairs = {}
    for ab in (69, 1230):
        r = L._rpc("pairUtility", [{"runnerId": rid, "unitId": CASTER,
                                    "targetId": TARGET, "abilityType": ab}])
        pairs[ab] = r.get("utility")
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    chosen = None
    for u in (dr.get("units") or []):
        if u.get("unitId") == CASTER:
            for m in (u.get("proposed") or []):
                if m.get("cls") == "ActiveAbilityMessage":
                    chosen = m.get("abilityType")
    eng = eng0 = None
    if engine:
        eng, eng0 = _engine(rid)
    print("  %-10s hp=%-6s pct=%-4s pair69=%-20r pair1230=%-20r natif=%-5s"
          " moteur=%-5s moteur[custom=0]=%s"
          % (label, hp, pct, pairs[69], pairs[1230], chosen, eng, eng0))
    return pct, pairs, chosen


def main() -> int:
    engine = "--engine" in sys.argv[1:]
    if not SEED_BC.exists():
        print("seed BC augmentee absente : lancer d'abord")
        print("  python catalog_inject.py --units bloodTerminator --out %s"
              % SEED_BC)
        return 2
    for raw in [a for a in sys.argv[1:] if not a.startswith("--")]:
        hp_max = int(raw)
        print("=== hp-player=%d ===" % hp_max)
        extra = []
        for a in sys.argv[1:]:
            if a.startswith("--armor-target="):
                extra += ["--armor-target", a.split("=", 1)[1]]
            elif a.startswith("--hp-target="):
                extra += ["--hp-target", a.split("=", 1)[1]]
        if not any(x == "--hp-target" for x in extra):
            extra += ["--hp-target", "60000"]
        _run(["build", "--seed", str(SEED), "--board", BOARD,
              "--seed-bc", str(SEED_BC),
              "--p-units", "bloodTerminator,ultraCalgar",
              "--a-units", "tauCrisis,blackTerminator",
              "--hp-player", str(hp_max), "--state-file", str(STATE)] + extra)
        rid = _runner_id()
        for u, to in ((CASTER, "4,8"), (TARGET, "5,8")):
            _run(["act", "move", "--unit", str(u), "--to", to,
                  "--state-file", str(STATE), "--runner", str(rid)])
        _measure(rid, "PV pleins", hp_max, engine)
        _run(["act", "ability", "--caster", str(TARGET), "--target",
              str(CASTER), "--ability", "69",
              "--state-file", str(STATE), "--runner", str(rid)])
        _measure(rid, "PV baisses", hp_max, engine)
    print("(pense a disposer le runner : disposeRunner)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
