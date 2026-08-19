"""case-1547 -- GENERALISATION du gate `EffectComponent.IsActive @+0x5c` sur le rail TARGETS de
l'effet 1547 `ReanimationBeam_Revive`.

La garde de non-regression (`tests/engine/runner/test_revive_retrofit_offline_live.py::
test_beam_inactive_effect_does_not_revive`) tue la cible par l'helper `_kill` (pose hp=0 puis
`after_death_triggers`). Ce probe generalise sur les TROIS axes que cet helper ne couvre pas :

  1. CHEMIN DE MORT REEL -- la victime meurt d'une ATTAQUE portee par le pipeline du port
     (`Runner.apply(AttackUnitMessage)` -> `AttackDamageOperation` -> `_add_death` (enqueue,
     `IdunBattle.Core.MatchState$$AddDeath`) -> `_verify_deaths` (drain,
     `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths`) -> `_kill_unit_operation`
     (`IdunBattle.Operations.KillUnitOperation$$Execute`) -> `after_death_triggers`), donc a
     travers la file de morts.
  2. GEOMETRIE -- le porteur du beam est DEPLACE a >= 3 hex de la victime. Le filtre natif
     `IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$CreateTargetFilter` ne porte
     AUCUN noeud d'adjacence (`AreFriends & HasTrait(Mechanical) & HasEffect(1545)`) : le verdict
     ne doit dependre que du FLAG, jamais de la distance.
  3. BOARD / ROSTER / SEED -- plusieurs cellules, positions DRIVEES (jamais « bloque par la
     geometrie de spawn »).

Chaque cellule oppose TROIS faces sur le MEME etat et le MEME tirage :
    (a) sans effet 1547            -> la victime meurt          (temoin de letalite)
    (b) 1547 present et ACTIF      -> la victime est REVIVE      (temoin de fonctionnement)
    (c) 1547 present et INERTE     -> la victime meurt           (LE gate)
=> le probe ECHOUE si (b) et (c) rendent le meme verdict : le flag seul doit renverser l'issue.

Le porteur natif (`necroReanimator`, Machine of War hors pool -- verifie par
`rl_duel.py build --list-pool`) n'est pas montable en runner : l'effet 1547 est INJECTE dans
`state.effects`, comme dans tout le harnais #79. L'ETAT, lui, est LIVE (board, stats, traits,
armes reels).

Usage :  python probe_1547_reanimation_beam_active_gate.py [--verbose]
ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import deque
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import rl_collect_batch as R                                              # noqa: E402
from engine.runner.snapshot import load_state                            # noqa: E402
from engine.runner.runner import Runner                                  # noqa: E402
from engine.runner.messages import AttackUnitMessage                     # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                   # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,   # noqa: E402
                                      PositionComponent, StatsComponent,
                                      UnitComponent, UnitFlagsComponent)
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.entities.effects.base import BaseEffect                      # noqa: E402
from engine.runner.operations.triggers.loki.reanimation_beam import (    # noqa: E402
    REANIMATION_BEAM_EFFECT, NANOSCARAB_EFFECT)

LEVEL, MULT = 50, 180            # niveau/multiplicateur de l'ability SOURCE, transportes par l'effet
FAR = 3                          # distance MINIMALE beam <-> victime (le filtre n'a pas d'adjacence)

# board / seed / rosters -- cellules deliberement disjointes (arene, campagne, PvP desert).
CELLS = [
    {"board": "MC1_67", "seed": "777",
     "p": "ultraTitus,bloodIntercessor", "a": "worldKharn"},
    {"board": "C3_01", "seed": "4242",
     "p": "spaceRockfist,tauMarksman", "a": "necroDestroyer"},
    {"board": "PVP_desert_01", "seed": "31337",
     "p": "templChampion,adeptRetributor", "a": "orksNob"},
]


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _rpc(sid, method, body=None, timeout=90):
    return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _bfs(board, src):
    dist = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist:
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def _build(sid, cell, state_path: Path):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", cell["seed"],
            "--state-file", str(state_path), "--board", cell["board"],
            "--p-units", cell["p"], "--a-units", cell["a"]]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_path.exists():
        return None, (p.stderr or p.stdout or "")[-300:]
    return json.loads(state_path.read_text())["runnerId"], None


def _capture(sid, rid):
    bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return None, "boardGraph KO"
    board = Board(bg["tiles"], adjacency="evenq")
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    sn = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    if not (_ok(dv) and _ok(ob) and _ok(sn)):
        return None, "capture live KO"
    return {"dv": dv, "ob": ob, "sn": sn, "board": board}, None


def _fresh(cap, seed_int):
    st = load_state(cap["dv"], cap["ob"], cap["sn"], board=cap["board"])
    st.rng = IntBasedMersenneTwister(seed_int)
    return st


def _teams(st):
    out = {}
    for uid, e in st.entities.items():
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        if oc is None or (uc is not None and not uc.alive):
            continue
        out.setdefault(oc.team, []).append(int(uid))
    return {t: sorted(v) for t, v in out.items()}


def _roles(st):
    """(beam, victime, attaquant) : deux allies d'une meme equipe + un ennemi. None si le
    plateau n'a pas au moins 2 allies et 1 ennemi vivants."""
    tm = _teams(st)
    if len(tm) < 2:
        return None
    a, b = sorted(tm)[0], sorted(tm)[1]
    if len(tm[a]) >= 2 and tm[b]:
        return tm[a][0], tm[a][1], tm[b][0]
    if len(tm[b]) >= 2 and tm[a]:
        return tm[b][0], tm[b][1], tm[a][0]
    return None


def _pos(st, uid):
    pc = st.get_entity(uid).get_component(PositionComponent)
    return (pc.col, pc.row)


def _place(st, uid, col, row):
    pc = st.get_entity(uid).get_component(PositionComponent)
    pc.col, pc.row = col, row


def _drive(st, board, beam, victim, attacker):
    """DEPLACE les unites pour fabriquer la configuration voulue : attaquant ADJACENT a la
    victime (l'attaque doit porter), porteur du beam a >= FAR hex (aucune adjacence exigee par
    le filtre natif). Renvoie la distance beam<->victime, ou None si le board ne permet pas."""
    occupied = {board.id_at(*_pos(st, u)) for u in st.entities
                if st.get_entity(u).get_component(PositionComponent) is not None}
    vt = board.id_at(*_pos(st, victim))
    free_adj = [t for t in board.neighbours(vt) if t not in occupied]
    if not free_adj:
        return None
    at = free_adj[0]
    occupied.discard(board.id_at(*_pos(st, attacker)))
    occupied.add(at)
    _place(st, attacker, *board.coord(at))
    dist = _bfs(board, vt)
    far = [t for t, d in sorted(dist.items(), key=lambda kv: -kv[1])
           if d >= FAR and t not in occupied]
    if not far:
        return None
    _place(st, beam, *board.coord(far[0]))
    return dist[far[0]]


def _arm(st, beam, victim, *, with_effect: bool, active: bool):
    """Filtre `ReanimationBeam_ReviveEffect$$CreateTargetFilter` : la victime est Mechanical et
    porte 1545 ; le beam porte 1547 (ou non). `active` = le flag `EffectComponent.IsActive`."""
    sc = st.get_entity(victim).get_component(StatsComponent)
    sc.ctx.traits = list(getattr(sc.ctx, "traits", None) or []) + ["Mechanical"]
    st.effects.by_unit.setdefault(int(victim), []).append(
        BaseEffect(name="NanoscarabRepairProtocols", effect_type=NANOSCARAB_EFFECT,
                   active_ability_level=LEVEL, ability_level=LEVEL,
                   ability_variables_multiplier=MULT, source=victim, target=victim))
    if not with_effect:
        return None
    inst = BaseEffect(name="ReanimationBeam_Revive", effect_type=REANIMATION_BEAM_EFFECT,
                      active_ability_level=LEVEL, ability_level=LEVEL,
                      ability_variables_multiplier=MULT, source=beam, target=beam)
    inst.active = bool(active)
    st.effects.by_unit.setdefault(int(beam), []).append(inst)
    return inst


def _run_face(cap, cell, *, with_effect: bool, active: bool, hp_override=None):
    """Monte l'etat, drive les positions, arme la face, puis porte l'ATTAQUE REELLE."""
    st = _fresh(cap, int(cell["seed"]))
    roles = _roles(st)
    if roles is None:
        return {"err": "roles KO"}
    beam, victim, attacker = roles
    d = _drive(st, cap["board"], beam, victim, attacker)
    if d is None:
        return {"err": "drive KO (board sature)"}
    inst = _arm(st, beam, victim, with_effect=with_effect, active=active)
    hc = st.get_entity(victim).get_component(HealthComponent)
    if hp_override is not None:
        hc.hp = int(hp_override)
    hp_before = int(hc.hp)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(AttackUnitMessage(attacker, victim))
    last = runner.damage_handler.last or {}
    fl = st.get_entity(victim).get_component(UnitFlagsComponent)
    return {"beam": beam, "victim": victim, "attacker": attacker, "dist": d,
            "hp_before": hp_before,
            "alive": bool(st.get_entity(victim).get_component(UnitComponent).alive),
            "hp_after": st.get_entity(victim).get_component(HealthComponent).hp,
            "damage": sum(last.get("per_hit") or []) if last.get("per_hit") else None,
            "overkill": bool(fl is not None and fl.has(UnitFlagsComponent.OVERKILLED)),
            "consumed": (None if inst is None else bool(inst.consumed))}


def _cell(sid, cell, verbose: bool):
    state_path = ROOT / "logs" / ("_probe1547_%s_%s.json" % (cell["board"], cell["seed"]))
    rid, err = _build(sid, cell, state_path)
    if rid is None:
        return {"cell": cell, "skip": "build KO: %s" % err}
    try:
        cap, err = _capture(sid, rid)
        if cap is None:
            return {"cell": cell, "skip": err}
        if _fresh(cap, 1).effects is None:
            return {"cell": cell, "skip": "pas d'EffectsState"}
        # 1) sonde de letalite : combien l'attaque enleve-t-elle sur cette configuration ?
        dry = _run_face(cap, cell, with_effect=False, active=True)
        if dry.get("err"):
            return {"cell": cell, "skip": dry["err"]}
        dmg = dry.get("damage")
        if not dmg:
            return {"cell": cell, "skip": "attaque sans degat (%s)" % json.dumps(dry, default=str)}
        # PV cales EXACTEMENT sur le degat -> mort LETALE mais NON overkill (`unit_is_overkill`
        # compare le CUMUL a 2*PV) : l'overkill est l'autre gate du meme trigger
        # (`get_ReviveOnOverkill` = 0), on l'ecarte pour n'observer QUE le flag.
        faces = {}
        for key, kw in (("a_sans", dict(with_effect=False, active=True)),
                        ("b_actif", dict(with_effect=True, active=True)),
                        ("c_inerte", dict(with_effect=True, active=False))):
            faces[key] = _run_face(cap, cell, hp_override=dmg, **kw)
        return {"cell": cell, "dmg": dmg, "faces": faces}
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
        state_path.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    try:
        sid = R._resolve_session()
    except Exception as e:
        print("SKIP: pas de session Frida (%s)" % str(e)[:120])
        return 2
    w = _unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=180))
    if not _ok(w):
        print("SKIP: amorce KO (%s)" % str(w)[:160])
        return 2

    print("=== case-1547 : le flag IsActive de l'instance 1547 renverse-t-il l'issue ? ===")
    print("%-16s %-6s %-5s %-9s %-9s %-9s %s" %
          ("board", "seed", "dist", "a_sans", "b_actif", "c_inerte", "verdict"))
    ok, ran = True, 0
    for cell in CELLS:
        r = _cell(sid, cell, args.verbose)
        if r.get("skip"):
            print("%-16s %-6s SKIP  %s" % (cell["board"], cell["seed"], r["skip"][:70]))
            ok = False
            continue
        f = r["faces"]
        bad = [k for k, v in f.items() if v.get("err")]
        if bad:
            print("%-16s %-6s FAIL  faces en erreur: %s" % (cell["board"], cell["seed"], bad))
            ok = False
            continue
        verdict = []
        if f["a_sans"]["alive"]:
            verdict.append("temoin-letalite KO (survit sans 1547)")
        if f["a_sans"]["overkill"] or f["b_actif"]["overkill"] or f["c_inerte"]["overkill"]:
            verdict.append("OVERKILL (l'autre gate masque le flag)")
        if not f["b_actif"]["alive"]:
            verdict.append("face ACTIVE ne revive pas")
        if f["c_inerte"]["alive"]:
            verdict.append("face INERTE revive -> GATE ABSENT")
        if f["c_inerte"]["consumed"]:
            verdict.append("effet 1547 CONSOMME par un trigger non evalue")
        ran += 1
        if verdict:
            ok = False
        print("%-16s %-6s %-5d %-9s %-9s %-9s %s" %
              (cell["board"], cell["seed"], f["b_actif"]["dist"],
               "mort" if not f["a_sans"]["alive"] else "VIVANT",
               "REVIVE" if f["b_actif"]["alive"] else "mort",
               "mort" if not f["c_inerte"]["alive"] else "REVIVE",
               "OK" if not verdict else " ; ".join(verdict)))
        if args.verbose:
            print("   %s" % json.dumps(f, default=str))
    print("")
    print("cellules concluantes : %d / %d" % (ran, len(CELLS)))
    print("RESULT: %s" % ("OK" if (ok and ran == len(CELLS)) else "FAIL"))
    return 0 if (ok and ran == len(CELLS)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
