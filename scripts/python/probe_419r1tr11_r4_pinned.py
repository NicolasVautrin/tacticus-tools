#!/usr/bin/env python
"""#419-r1-tr11-r4 -- le `Pinned` (1065) a `d == 3` de `SpecialIssueCombiMelta`, natif contre port.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpecialIssueCombiMelta_AddEffectAbility` est la
TROISIEME portee du kit, la seule qui vive sur une ABILITY et non sur un effet :

    $$CreateTrigger   = On(0x26 = NormalAttack, 1) & get_OwnerIsCaster
                        & IsAtRange(Caster@DSLSelectors+0x48, Target@DSLSelectors+0x60,
                                    DSLFormulas.Get(3))
    $$CreateBehaviour = DSLBehaviors.AddEffect(0x429 = 1065 Pinned, AbilityStateReference,
                                               targets = Target@DSLSelectors+0x60, turns = null)

Ce que ce probe MESURE (aucune assertion : c'est un probe ; la garde est
`tests/engine/runner/test_419r1tr11_r4_pinned_live.py`) :

  1. l'attaque normale de `darkaSternguard` portee depuis une tuile a distance EXACTEMENT 3 de la
     cible pose-t-elle `Pinned` sur la cible, LIVE et OFFLINE ?
  2. la MEME attaque portee a une AUTRE distance ne le pose PAS -- des DEUX cotes. C'est ce second
     bras qui rend le premier discriminant : `IsAtRange` compare par EGALITE
     (`IdunBattle.Entities.Triggers.IsAtRangeAbilityTrigger$$ShouldTrigger` : `d == attendu`), donc
     un port qui lirait `<= 3` passerait le bras 3 et echouerait celui-ci.

Le porteur `darkaSternguard` << Ramus >> est un HERO HORS CATALOGUE du seed BC : il entre par
`catalog_inject.write_augmented_seed_bc` + `rl_duel build --seed-bc` (case-92 SS6), comme pour la
face DECISION (`probe_419r1tr11_combi_melta.py`). Son arme est `ranged r3`, donc la distance 3 est
a portee sans montage supplementaire.

ASCII only (cp1252).
Usage:
    python probe_419r1tr11_r4_pinned.py --state-file <ABS> [--dist 3] [--seed 41545]
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
from engine.runner.snapshot import load_state  # noqa: E402
from engine.runner.runner import Runner  # noqa: E402
from engine.runner.messages import AttackUnitMessage  # noqa: E402
from engine.entities.pathfinding.board import Board  # noqa: E402
from engine.entities.effect_type import EffectType  # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister  # noqa: E402

PYDIR = Path(__file__).resolve().parent
CASTER = "darkaSternguard"
ENEMIES = "astraBullgryn,necroWarden"
PINNED = int(EffectType.Pinned)                 # 0x429 = 1065 -- UI << Suppressed >>
PINNED_NAME = EffectType.Pinned.name


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _normal_attack_type(dv, uid):
    """`decisionView.units[].abilities[kind == normal].id` -- l'`ActiveAbilityType` CONCRET de
    l'attaque normale, qui est PER-UNITE (`ActiveAbilityComponent.NormalAttackType`).
    `applyAction{"kind": "attack"}` n'existe pas."""
    for u in (dv.get("units") or []):
        if int(u.get("id", -1)) == int(uid):
            for a in (u.get("abilities") or []):
                if a.get("kind") == "normal" and a.get("id") is not None:
                    return int(a["id"])
    return None


def _effects_of(dv, uid):
    for u in (dv.get("units") or []):
        if int(u.get("id", -1)) == int(uid):
            return [e.get("name") for e in (u.get("effects") or [])]
    return []


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=41545)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--dist", type=int, default=3,
                    help="distance EXACTE caster<->cible au moment de l'attaque (3 = le regime "
                         "du Pinned ; toute autre valeur = contre-epreuve)")
    ap.add_argument("--state-file", required=True)
    args = ap.parse_args(argv)

    state_file = Path(args.state_file)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    seed_bc = state_file.with_suffix(".seedbc.json")
    state_file.unlink(missing_ok=True)

    import catalog_inject
    catalog_inject.write_augmented_seed_bc(str(seed_bc), [CASTER])
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(args.seed),
         "--state-file", str(state_file), "--board", args.board, "--seed-bc", str(seed_bc),
         "--p-units", CASTER, "--a-units", ENEMIES, "--no-ai"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[pin] build KO: " + (proc.stderr or proc.stdout or "")[-700:])
        return 2
    rid = json.loads(state_file.read_text())["runnerId"]
    sid = _resolve_session()

    def rpc(m, b, t=120):
        return (_rpc(sid, m, [b], timeout=t).get("result") or {})

    print("[pin] seed=%d board=%s runner=%s dist_cible=%d"
          % (args.seed, args.board, rid, args.dist))
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")

        def dview():
            return rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 180)

        dec = dview()
        cst = next((u for u in (dec.get("units") or [])
                    if u.get("alive") and u.get("visualId") == CASTER), None)
        if cst is None:
            print("[pin] caster absent du montage")
            return 2
        for _ in range(12):
            if dec.get("currentPlayer") == cst.get("owner"):
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            dec = dview()
        alive = [u for u in (dec.get("units") or []) if u.get("alive")]
        cst = next((u for u in alive if u.get("id") == cst["id"]), None)
        ens = [u for u in alive if u.get("owner") != cst.get("owner")]
        if not ens:
            print("[pin] aucun ennemi vivant")
            return 2
        tgt = ens[0]
        C, T = _pos(cst), _pos(tgt)
        occ = {_pos(u) for u in alive}

        # DEPLACER le caster (jamais << bloque par la geometrie de spawn >>) : on cherche une tuile
        # LIBRE, marchable, a distance hexagonale EXACTEMENT `--dist` de la cible.
        cands = [board.coord(t) for t in sorted(board.by_id)
                 if board.walkable(t) and board.coord(t) not in occ
                 and hexgeo.distance(board.coord(t), T) == args.dist]
        dest = None
        if hexgeo.distance(C, T) == args.dist:
            dest = C                                    # deja a la bonne distance
        else:
            for cand in cands:
                r = rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": cst["id"],
                    "to": {"col": cand[0], "row": cand[1]}}}, 120)
                a0 = ((r or {}).get("actions") or [{}])[0]
                if a0.get("ok"):
                    dest = cand
                    break
        if dest is None:
            print("[pin] aucune tuile atteignable a distance %d de %s (candidates=%d)"
                  % (args.dist, T, len(cands)))
            return 2
        dec = dview()
        alive = [u for u in (dec.get("units") or []) if u.get("alive")]
        cst = next((u for u in alive if u.get("id") == cst["id"]), None)
        tgt = next((u for u in alive if u.get("id") == tgt["id"]), None)
        C, T = _pos(cst), _pos(tgt)
        d = hexgeo.distance(C, T)
        nat = _normal_attack_type(dec, cst["id"])
        print("[pin] caster=%s@%s cible=%s@%s distance=%d normalAttackType=%s"
              % (cst["id"], C, tgt["id"], T, d, nat))
        if d != args.dist:
            print("[pin] distance obtenue %d != demandee %d -- montage rate" % (d, args.dist))
            return 2
        if nat is None:
            print("[pin] pas d'attaque normale publiee pour le caster")
            return 2

        print("[pin] AVANT: effets cible = %s" % json.dumps(_effects_of(dec, tgt["id"])))

        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        state = load_state(dec, ob, snap, board=board)
        if s0 and s0.get("mt"):
            state.rng = _seed_rng(s0)

        # --- OFFLINE (port) : la MEME attaque normale ---
        # ⚠ PAS `ActiveAbilityMessage(ability_type = <id concret>)` : le port ne connait pas les
        # `ActiveAbilityType` CONCRETS d'attaque normale (ici 69) et rendrait `ported: false`, un
        # NO-OP silencieux -- l'attaque n'aurait pas lieu du tout et le `False` du Pinned
        # n'accuserait pas le port mais le MONTAGE. La porte du port est `AttackUnitMessage`
        # (`DamageHandler.visit_AttackUnitMessage`), qui traverse le MEME `AttackDamageOperation`
        # et emet le MEME `On(0x26 = NormalAttack)` (`after_hit_normal_attack`).
        runner = Runner(state).install_default_handlers(20)
        runner.apply(AttackUnitMessage(attacker_id=cst["id"], target_id=tgt["id"]))
        off_pinned = bool(state.effects and state.effects.has_effect(int(tgt["id"]),
                                                                    effect_type=PINNED))
        off_names = sorted({getattr(e, "name", None)
                            for e in (state.effects.by_unit.get(int(tgt["id"])) or [])
                            if getattr(e, "name", None)}) if state.effects else []
        print("[pin] OFFLINE Pinned pose sur la cible : %s" % off_pinned)
        print("[pin] OFFLINE effets cible = %s" % json.dumps(off_names))
        last = getattr(getattr(runner, "ability_handler", None), "last", None)
        print("[pin] OFFLINE last = %s" % json.dumps(last, default=str)[:900])

        # --- LIVE ---
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cst["id"], "targetId": tgt["id"],
            "abilityType": nat}, "captureEvents": True}, 240)
        a0 = ((r or {}).get("actions") or [{}])[0]
        if not a0.get("ok"):
            print("[pin] attaque LIVE KO %s" % str(r)[:500])
            return 2
        dec2 = dview()
        live_names = _effects_of(dec2, tgt["id"])
        live_pinned = PINNED_NAME in (live_names or [])
        print("[pin] LIVE   Pinned pose sur la cible : %s" % live_pinned)
        print("[pin] LIVE   effets cible = %s" % json.dumps(live_names))
        print("[pin] ACCORD offline == live : %s   (attendu a d == 3 : True/True ; sinon : "
              "False/False)" % (off_pinned == live_pinned))
        return 0
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
