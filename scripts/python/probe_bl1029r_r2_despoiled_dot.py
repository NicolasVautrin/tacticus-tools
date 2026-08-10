#!/usr/bin/env python
"""#BL-1029r-r2 -- le DoT de tuile `DespoiledGround` (1476) et le buff 1478, natif contre port.

⚠ LA PREMISSE DU RESIDU EST FAUSSE, ET C'EST MESURABLE SANS RUNNER. Le backlog dit
<< Cote port, AUCUN `TileEffectTrigger` n'est enregistre pour 1476 >>. Or, depuis #85
(commit `769b965a`, 2026-07-28, soit DOUZE jours avant l'ouverture du residu) :

    EFFECT_TRIGGERS[1476] == [DespoiledGroundTileDoT]         (dispatch/registry.py)
    EFFECT_CLASSES["DespoiledGround"]              == DespoiledGroundEffect
    EFFECT_CLASSES["DespoiledGround_ExtraDamagePct"] == DespoiledGroundExtraDamagePctEffect

Le mode `--registre` de ce probe RE-DERIVE ces trois faits du code (jamais d'une fiche).

CE QUI N'AVAIT PAS ETE FAIT, et que ce probe fait : CONFRONTER ce port. Le probe de
`#BL-1029r-r1` mesurait bien `Effect_Type: 1476` cote LIVE (35 188 sur une cible a 500 000 PV),
mais il ECARTAIT explicitement de sa comparaison tout evenement portant un `Effect_Type` -- le tick
de tuile n'a donc jamais ete oppose au port, ni dans un sens ni dans l'autre.

## Le montage, et pourquoi la cible est CHAOS

`IdunBattleLogic.Entities.Abilities.Active.Loki.EnvDespoiledGroundTileAbility$$CreateBehaviour`
(corps LU sur `rnca9r7q6c`) fait DEUX choses par occupant, et la seconde est gatee :

    Foreach( UnitsWithoutTraits(., [0x1b = 27 Steppable, 0x19 = 25 Immune], 3)
             & Units(EntitiesWithAnyEffect(., 0x5c4 = 1476, 2), 1, 1),
        AttackWithAbilityDamage( Tiles(elem), elem,
                                 RandomAmount( PercentageOf(StatAmount(elem, Health, Max), EffectConfig(9)),
                                               PercentageOf(StatAmount(elem, Health, Max), EffectConfig(10)) ),
                                 AbilityOrEffect(0x5c4), Direct(Nullable(0xf = DirectDamage)) )
      + If( IsTurnOf(elem) & HasTrait(elem, 0x7ea = 2026 Chaos) & NOT HasTrait(elem, 0x19 = Immune),
            AddEffect(0x5c6 = 1478, AbilityStateReference, elem, <DSLFormulas+0x20 = Const(1)>) ) )

-> le DoT frappe TOUT occupant non-Steppable/Immune, mais le buff 1478 n'est pose que sur un
occupant **CHAOS**, **a SON tour**. La cible du montage est donc un HERO CHAOS (`worldKharn`) : sur
un Necron, le volet 1478 serait STRUCTURELLEMENT inatteignable et son accord vide de sens.

Sequence : Abaddon caste `Drachnyen` (1029) au CONTACT de Kharn -> le volet 2 de
`LetTheGalaxyBurn_ResetAbility` despoile la TUILE de Kharn (#BL-1029r-r1) ; on passe le tour ; le
tick `On(0x14 = TurnStart_EnvironmentEffects)` du tour de Kharn inflige le DoT et pose 1478.
Une 2e p-unit JAMAIS activee garde le tour OUVERT apres le cast, pour que le tick soit ISOLABLE
(meme levier que `test_env_fire_tile_migration_live.py`).

ASCII only (cp1252).
Usage:
    python probe_bl1029r_r2_despoiled_dot.py --registre
    python probe_bl1029r_r2_despoiled_dot.py --state-file <ABS> [--seed 777] [--board MC1_67]
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
from engine.runner.messages import EndTurnMessage  # noqa: E402
from engine.runner.components import HealthComponent  # noqa: E402
from engine.entities.pathfinding.board import Board  # noqa: E402
from engine.entities.effect_type import EffectType  # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ABADDON = "blackAbaddon"
IDLE = "astraDreir"          # 2e p-unit JAMAIS activee -> le tour ne bascule pas apres le cast
TARGET = "worldKharn"         # HERO **CHAOS** : seul regime ou le volet 1478 existe
DRACHNYEN = 1029
DESPOILED = int(EffectType.DespoiledGround)                      # 0x5c4 = 1476
DESPOILED_BUFF = int(EffectType.DespoiledGround_ExtraDamagePct)  # 0x5c6 = 1478


def registre() -> int:
    """Etage 0, 100 % OFFLINE : la premisse du residu, RE-DERIVEE du code."""
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    from engine.entities.effects.factory import EFFECT_CLASSES
    trig = EFFECT_TRIGGERS.get(DESPOILED)
    print("[dg2] EFFECT_TRIGGERS[%d %s] = %s"
          % (DESPOILED, EffectType.DespoiledGround.name,
             [c.__name__ for c in (trig or [])] or None))
    for nm in (EffectType.DespoiledGround.name, EffectType.DespoiledGround_ExtraDamagePct.name):
        cls = EFFECT_CLASSES.get(nm)
        print("[dg2] EFFECT_CLASSES[%-30s] = %s" % (nm, cls.__name__ if cls else None))
    print("[dg2] PREMISSE DU BACKLOG (<< aucun TileEffectTrigger pour 1476 >>) : %s"
          % ("VRAIE" if not trig else "REFUTEE"))
    return 0


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _unit(dv, uid):
    return next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)


def _fx(u):
    return [e.get("name") for e in ((u or {}).get("effects") or [])]


class MontageError(RuntimeError):
    """Le montage n'a pas ete exerce. ECHEC FRANC, jamais un skip (#268)."""


SEED = 777
HP_TARGET = "500000"
#: `--hp-target` fixe les PV **et met l'armure a 0** : le DoT (6 a 9 % de la PV MAX) devient assez
#: grand pour etre lu sans bruit, et la cible SURVIT au cast de Drachnyen (~19 000).
BUILD_ARGS = ["--no-ai", "--p-units", "%s,%s" % (ABADDON, IDLE), "--a-units", TARGET,
              "--hp-target", HP_TARGET]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--registre", action="store_true",
                    help="etage 0 seul (offline) : re-derive la premisse du residu")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file")
    args = ap.parse_args(argv)

    rc = registre()
    if args.registre:
        return rc
    if not args.state_file:
        print("[dg2] --state-file requis hors mode --registre")
        return 2

    state_file = Path(args.state_file)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(args.seed),
         "--state-file", str(state_file), "--board", args.board, *BUILD_ARGS],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[dg2] build KO: " + (proc.stderr or proc.stdout or "")[-700:])
        return 2
    rid = json.loads(state_file.read_text())["runnerId"]
    sid = _resolve_session()

    def rpc(m, b, t=120):
        return (_rpc(sid, m, [b], timeout=t).get("result") or {})

    print("[dg2] seed=%d board=%s runner=%s cible=%s (CHAOS)"
          % (args.seed, args.board, rid, TARGET))
    try:
        measure(rpc, rid, verbose=True)
        return 0
    except MontageError as e:
        print("[dg2] MONTAGE KO : %s" % e)
        return 2
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)


def measure(rpc, rid, verbose: bool = False) -> dict:
    """Le coeur, PARTAGE par le probe et la garde `tests/engine/runner/
    test_bl1029r_r2_despoiled_dot_live.py`. Rend
    `{"dot_offline", "dot_live", "buff_offline", "buff_live", ...}`."""
    def say(msg):
        if verbose:
            print(msg)

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")

    def dview():
        return rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 180)

    def tile_fx():
        tm = rpc("tileMeta", {"runnerId": rid}, 60)
        return {(t.get("col"), t.get("row")): [e.get("name") for e in (t.get("effects") or [])]
                for t in (tm.get("tiles") or [])}

    dec = dview()
    cst = next((u for u in (dec.get("units") or [])
                if u.get("alive") and u.get("visualId") == ABADDON), None)
    tgt = next((u for u in (dec.get("units") or [])
                if u.get("alive") and u.get("visualId") == TARGET), None)
    if cst is None or tgt is None:
        raise MontageError("roster incomplet (caster=%s cible=%s)" % (bool(cst), bool(tgt)))
    me = cst.get("owner")
    for _ in range(12):
        if dec.get("currentPlayer") == me:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        dec = dview()

    # AMENER Abaddon AU CONTACT (Drachnyen est melee) -- on DEPLACE, on ne subit pas le spawn.
    alive = [u for u in (dec.get("units") or []) if u.get("alive")]
    occ = {_pos(u) for u in alive}
    T = _pos(_unit(dec, tgt["id"]))
    nb = [board.coord(t) for t in sorted(board.by_id)
          if board.walkable(t) and board.coord(t) not in occ
          and hexgeo.distance(board.coord(t), T) == 1]
    moved = False
    for cand in nb:
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cst["id"], "to": {"col": cand[0], "row": cand[1]}}}, 120)
        if (((r or {}).get("actions") or [{}])[0]).get("ok"):
            moved = True
            break
    dec = dview()
    C = _pos(_unit(dec, cst["id"]))
    say("[dg2] caster=%s@%s cible=%s@%s d=%d (deplace=%s)"
        % (cst["id"], C, tgt["id"], T, hexgeo.distance(C, T), moved))

    r = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cst["id"], "targetId": tgt["id"],
        "abilityType": DRACHNYEN}}, 240)
    if not (((r or {}).get("actions") or [{}])[0]).get("ok"):
        raise MontageError("cast Drachnyen refuse : %s" % str(r)[:300])
    dec = dview()
    tu = _unit(dec, tgt["id"])
    if tu is None or not tu.get("alive"):
        raise MontageError("cible morte au cast")
    T = _pos(tu)
    fx = tile_fx()
    say("[dg2] APRES CAST : tuile cible %s effets=%s" % (T, fx.get(T)))
    if EffectType.DespoiledGround.name not in (fx.get(T) or []):
        raise MontageError("la tuile de la cible n'est pas despoilee (effets : %r)" % (fx.get(T),))
    if dec.get("currentPlayer") != me:
        raise MontageError("le tour a bascule au cast : le tick n'est plus isolable "
                           "(currentPlayer=%r, moi=%r) -- la 2e p-unit n'a pas joue son role"
                           % (dec.get("currentPlayer"), me))
    before_fx = _fx(tu)
    if EffectType.DespoiledGround_ExtraDamagePct.name in (before_fx or []):
        raise MontageError("la cible porte DEJA 1478 avant le tick -- le regime ne discrimine rien")
    say("[dg2] AVANT TICK : PV cible = %s, effets = %s" % (tu.get("hp"), json.dumps(before_fx)))

    # --- ETAT DE REFERENCE (les deux moteurs partent d'ICI) ---
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    hp_before = int(tu.get("hp") or 0)
    state = load_state(dec, ob, snap, board=board, tiles=tm)
    if s0 and s0.get("mt"):
        state.rng = _seed_rng(s0)

    # --- OFFLINE : le MEME geste que le live -- une FIN DE TOUR ---
    # ⚠ NE PAS appeler `tile_tick_triggers(state)` directement : le 2e volet du behaviour est gate
    # par `IsTurnOf(elem)`, et l'etat capture porte encore MON `current_player_id`. Le natif, lui,
    # emet `On(0x14)` depuis `StartTurnOperation`, donc APRES le flip de `ChangeTurnOperation` --
    # c'est exactement ce que fait la sequence `EndTurnOperation -> ChangeTurnOperation ->
    # StartTurnOperation` de `EndTurnMessage` (`operations/turnflow.py`, qui appelle
    # `tile_tick_triggers` avec le joueur DEJA change). MESURE : l'appel direct rend
    # `1478 : False` cote port -- un faux ROUGE qui accuse le MONTAGE, pas le port.
    runner = Runner(state).install_default_handlers(20)
    runner.apply(EndTurnMessage(advance=True))
    e = state.get_entity(tgt["id"])
    hc = e.get_component(HealthComponent) if e is not None else None
    off_dot = (hp_before - int(hc.hp)) if hc is not None else None
    off_fx = sorted({getattr(x, "name", None)
                     for x in (state.effects.by_unit.get(int(tgt["id"])) or [])
                     if getattr(x, "name", None)}) if state.effects else []
    off_buff = bool(state.effects and state.effects.has_effect(int(tgt["id"]),
                                                               effect_type=DESPOILED_BUFF))
    say("[dg2] OFFLINE joueur courant apres EndTurn = %s"
        % getattr(state, "current_player_id", None))
    say("[dg2] OFFLINE dPV     = %s" % off_dot)
    say("[dg2] OFFLINE effets cible = %s" % json.dumps(off_fx))
    say("[dg2] OFFLINE 1478 pose : %s" % off_buff)

    # --- LIVE : on passe le tour -> le tour de la cible demarre -> le tick fire ---
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
    dec2 = dview()
    tu2 = _unit(dec2, tgt["id"])
    live_fx = _fx(tu2)
    live_dot = (hp_before - int(tu2.get("hp") or 0)) if tu2 else None
    live_buff = EffectType.DespoiledGround_ExtraDamagePct.name in (live_fx or [])
    say("[dg2] LIVE   currentPlayer = %s" % dec2.get("currentPlayer"))
    say("[dg2] LIVE   dPV     = %s" % live_dot)
    say("[dg2] LIVE   effets cible = %s" % json.dumps(live_fx))
    say("[dg2] LIVE   1478 pose : %s" % live_buff)
    say("[dg2] ACCORD dPV offline == live : %s" % (off_dot == live_dot))
    return {"target": int(tgt["id"]), "hp_before": hp_before,
            "dot_offline": off_dot, "dot_live": live_dot,
            "buff_offline": off_buff, "buff_live": live_buff,
            "effects_before": before_fx, "effects_offline": off_fx, "effects_live": live_fx}


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


