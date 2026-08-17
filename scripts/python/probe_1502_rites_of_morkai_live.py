"""Probe #229/1502 -- confrontation LIVE du gate `EffectComponent.IsActive` de `RitesOfMorkaiEffect`.

Ce que ce probe MESURE (les deux residus laisses ouverts par la PR #235, faute de porteur) :

  Q1  RAYON DE SOUFFLE -- `readEffectsByUnit` (frida `hooks/game/effects.ts`, consomme par
      `decisionView`) publie-t-il une instance de l'effectType 1502 ? La case §3 de
      `docs/rl/case-229-effect-triggers-active-inventory.md` etait marquee NON MESURABLE, et
      l'exemple 1077 (bond `Haze`, `case-231`) montre que cette table n'est PAS fiable sans
      confrontation : la reponse doit etre MESUREE, jamais heritee.
  Q2  DISCRIMINATION DU GATE -- sur un etat ou 1502 est pose PAR LE CAST NATIF (aucune injection
      dans `state.effects`), le `matches` du port refuse-t-il le revive quand l'instance est
      `active=False` et l'accorde-t-il quand elle est `active=True` ? Face NATIVE en prime : on
      tue une unite inspiree EN LIVE et on regarde si le jeu la ressuscite.

Le deblocage : `spaceWolfPriest` (« Baldr ») est un HERO **hors seed BC**, ce qui avait ete lu comme
« non confrontable ». C'est FAUX -- `catalog_inject.write_augmented_seed_bc` l'injecte dans les DEUX
catalogues (`Units` + `Abilities`, mirror de
`Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration`) et il entre au pool
(97 -> 98 unites regulieres). Le seed augmente est ecrit HORS de `data/` (c'est une SORTIE).

Montage (calibre pour un coup fatal NON overkill) : `--hp-player 3000` + `--dmg-target 1000`.
`IdunBattle.Core.Services.DamagePrediction$$IsOverkill` rend `pct = (dmg - hpAvant)/hpAvant*100`
et compare a `overkillDmgPctOfHealth` (=100) : il faut donc `dmg < 2*hpAvant` au coup fatal. Le
Warboss (1 hit ranged) entame 3000 -> ~2000, le Nob (3 hits) acheve depuis 2000 avec ~3000 de
degat -> pct ~50 < 100 => mort NORMALE, pas overkill (le revive « unless Overkilled » est donc
exercable). Alliés NON-MECANIQUES obligatoires : `get_HealType` de RitesOfMorkai vaut 0 (Heal) et
`IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType` refuse les mecaniques.

Usage (depuis scripts/python, session Frida DEJA warmee -- ce probe ne (re)injecte JAMAIS) :

    python probe_1502_rites_of_morkai_live.py [--board MC1_67] [--seed 777] [--keep]

Sortie ASCII only (cp1252). Le runner est dispose en fin de course sauf `--keep`.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import catalog_inject as CI                                    # noqa: E402
from rl_collect_batch import _rpc, _resolve_session            # noqa: E402
from engine.entities.pathfinding.board import Board            # noqa: E402
from engine.runner.snapshot import load_state                  # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister         # noqa: E402
from engine.runner.components import (UnitComponent, HealthComponent,      # noqa: E402
                                      PositionComponent)
from engine.runner.operations.triggers.dispatch.move_death import after_death_triggers  # noqa: E402
from engine.runner.operations.revive import kill_unit_revive_gate           # noqa: E402
from engine.runner.operations.triggers.loki.rites_of_morkai import (        # noqa: E402
    RITES_OF_MORKAI_EFFECT)

RITES_OF_MORKAI_ABILITY = 1211        # ActiveAbilityType.RitesOfMorkai
P_UNITS = "spaceWolfPriest,astraCreed,eldarFarseer"
A_UNITS = "orksNob,orksWarboss"
LOGS = HERE.parents[1] / "logs"


# --------------------------------------------------------------------------- RPC helpers

def decision(sid, rid, include_inactive=False):
    return (_rpc(sid, "decisionView",
                 [{"runnerId": rid, "maxRank": 2, "allAbilities": True,
                   "includeInactive": bool(include_inactive)}], timeout=300).get("result") or {})


def apply_action(sid, rid, action):
    return (_rpc(sid, "applyAction", [{"runnerId": rid, "action": action}],
                 timeout=120).get("result") or {})


def movable(sid, rid):
    return (_rpc(sid, "aiMovableTiles", [{"runnerId": rid}], timeout=60).get("result") or {})


def units_by_id(view):
    return {u.get("id"): u for u in (view.get("units") or [])}


# --------------------------------------------------------------------------- board distance

def bfs_dist(board: Board, src: tuple, dst: tuple) -> int:
    """Distance en pas sur le graphe d'adjacence du board (walkable ignore : on veut un GUIDE
    de rapprochement, pas un chemin legal -- la legalite du move vient d'`aiMovableTiles`)."""
    a, b = board.id_at(*src), board.id_at(*dst)
    if a is None or b is None:
        return 10 ** 6
    seen, q = {a: 0}, deque([a])
    while q:
        t = q.popleft()
        if t == b:
            return seen[t]
        for n in board.neighbours(t):
            if n not in seen:
                seen[n] = seen[t] + 1
                q.append(n)
    return 10 ** 6


# --------------------------------------------------------------------------- scenario

def build(seed, board_id, state_file, seed_bc, hp_player, dmg_target,
          p_units=P_UNITS, a_units=A_UNITS):
    cmd = [sys.executable, "rl_duel.py", "build",
           "--seed", str(seed), "--board", board_id, "--seed-bc", str(seed_bc),
           "--p-units", p_units, "--a-units", a_units,
           "--hp-player", str(hp_player), "--dmg-target", str(dmg_target),
           "--state-file", str(state_file), "--no-ai"]
    r = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
        raise RuntimeError("rl_duel build KO")
    st = json.loads(Path(state_file).read_text(encoding="utf-8"))
    return int(st["runnerId"])


def march(sid, rid, board, victim_id, foe_ids, max_rounds=10):
    """Rapproche les unites ADVERSES (`foe_ids`, FIXES -- `ctrl` bascule a chaque `endturn`, on ne
    peut donc pas s'y fier) de `victim_id` jusqu'a l'adjacence ; les miennes ne bougent pas (le
    groupe de Baldr doit rester compact pour la pose en zone, range 1). Rend le nb de rounds."""
    for rnd in range(max_rounds):
        ub = units_by_id(decision(sid, rid))
        vp = ub[victim_id]["pos"]
        vpos = (vp["col"], vp["row"])
        d = [bfs_dist(board, (ub[f]["pos"]["col"], ub[f]["pos"]["row"]), vpos)
             for f in foe_ids if ub.get(f, {}).get("alive")]
        if d and min(d) <= 1:
            return rnd
        for mu in (movable(sid, rid).get("units") or []):
            uid = mu.get("unitId")
            if uid not in foe_ids:
                continue                                  # on ne bouge QUE l'adversaire
            tiles = [(t["col"], t["row"]) for t in (mu.get("tiles") or [])
                     if t.get("col") is not None]
            if not tiles:
                continue
            best = min(tiles, key=lambda t: bfs_dist(board, t, vpos))
            apply_action(sid, rid, {"kind": "move", "unitId": uid,
                                    "to": {"col": best[0], "row": best[1]}})
        apply_action(sid, rid, {"kind": "endturn"})
    return -1


def normal_attack_id(view, caster_id, target_id):
    """Id d'ability de l'attaque du plan `caster -> target` (`decisionView.attackPlans`)."""
    for p in (view.get("attackPlans") or []):
        if p.get("unitId") != caster_id:
            continue
        for ev in (p.get("evals") or []):
            if ev.get("targetId") == target_id:
                return ev.get("abilityId")
    return None


def capture(sid, rid):
    bg = _rpc(sid, "boardGraph", [{"runnerId": rid}], 60).get("result") or {}
    board = Board(bg["tiles"], adjacency="evenq")
    dv = decision(sid, rid)
    ob = _rpc(sid, "observeBattle", [{"runnerId": rid}], 60).get("result") or {}
    snap = _rpc(sid, "combatSnapshot", [{"runnerId": rid}], 60).get("result") or {}
    return board, dv, ob, snap


def port_gate_matrix(board, dv, ob, snap, victim, killer):
    """Q2 cote PORT : le meme etat LIVE, seule l'instance 1502 change d'etat."""
    def fresh():
        st = load_state(dv, ob, snap, board=board)
        st.rng = IntBasedMersenneTwister(777)
        return st

    def inst(st, uid):
        return [e for e in (st.effects.by_unit.get(int(uid)) or [])
                if e.effect_type == RITES_OF_MORKAI_EFFECT]

    def run(label, mutate=None, overkill=False):
        st = fresh()
        es = inst(st, victim)
        if not es:
            print("  %-30s SKIP: aucune instance 1502 seedee sur u%d" % (label, victim))
            return None
        for e in es:
            if mutate:
                mutate(e)
        pc = st.get_entity(victim).get_component(PositionComponent)
        pos0 = (pc.col, pc.row)
        st.get_entity(victim).get_component(HealthComponent).hp = 0
        st.get_entity(victim).get_component(UnitComponent).alive = False
        res = after_death_triggers(st, dying_id=victim, killer_id=killer, overkill=overkill)
        kill_unit_revive_gate(st, victim)
        uc = st.get_entity(victim).get_component(UnitComponent)
        hc = st.get_entity(victim).get_component(HealthComponent)
        fired = [r for r in res if r.get("ability") == "RitesOfMorkai"]
        print("  %-30s alive=%-5s hp=%-6s pos=%s->%s trigger=%d consumed=%s"
              % (label, uc.alive, hc.hp, pos0, (pc.col, pc.row), len(fired),
                 [e.consumed for e in inst(st, victim)]))
        return bool(uc.alive)

    a = run("active=True (tel que capte)")
    b = run("active=False (gate eteint)", mutate=lambda e: setattr(e, "active", False))
    c = run("active=False->True (re-arme)", mutate=lambda e: setattr(e, "active", True))
    d = run("active=True + OVERKILL", overkill=True)
    return a, b, c, d


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--hp-player", type=int, default=3000)
    ap.add_argument("--dmg-target", type=int, default=1000)
    ap.add_argument("--p-units", default=P_UNITS,
                    help="allies NON-MECANIQUES obligatoires (get_HealType=0 -> "
                         "IsAffectedByHealType refuse les mecaniques) ; spaceWolfPriest doit "
                         "rester EN TETE (c'est Baldr, le caster)")
    ap.add_argument("--a-units", default=A_UNITS)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)

    LOGS.mkdir(parents=True, exist_ok=True)
    seed_bc = LOGS / "seed_bc_swp_probe.json"
    state_file = LOGS / "swp_probe_state.json"
    p, units, abils = CI.write_augmented_seed_bc(seed_bc, ["spaceWolfPriest"])
    print("[inject] seed BC augmente (HORS data/) -> %s" % p)
    print("[inject] units=%s abils=%s" % (units, abils))

    sid = _resolve_session()
    rid = build(a.seed, a.board, state_file, seed_bc, a.hp_player, a.dmg_target,
                a.p_units, a.a_units)
    print("[build] sid=%d runnerId=%d board=%s seed=%d hp_player=%d dmg_target=%d"
          % (sid, rid, a.board, a.seed, a.hp_player, a.dmg_target))
    print("[build] p_units=%s | a_units=%s" % (a.p_units, a.a_units))
    rc = 0
    try:
        board, _, _, _ = capture(sid, rid)
        view = decision(sid, rid)
        # ⚠ `ctrl` bascule a chaque `endturn` (c'est « appartient au joueur COURANT ») : on fige
        # les deux camps ICI, au 1er tour, et on n'y revient plus.
        mine = [u["id"] for u in (view.get("units") or []) if u.get("ctrl")]
        foes = [u["id"] for u in (view.get("units") or []) if not u.get("ctrl")]
        baldr = mine[0]
        victim = mine[1]
        print("[roster] mine=%s foes=%s | Baldr=u%d victime=u%d" % (mine, foes, baldr, victim))

        n = march(sid, rid, board, victim, foes)
        print("[march] adjacence atteinte apres %d rounds" % n)
        if n < 0:
            print("[march] ECHEC -- l'adversaire n'a pas atteint la victime")
            return 2

        # --- Q1 : le canal publie-t-il 1502 ? ---------------------------------------
        before = decision(sid, rid, include_inactive=True)
        n0 = sum(1 for u in (before.get("units") or []) for e in (u.get("effects") or [])
                 if e.get("effectType") == RITES_OF_MORKAI_EFFECT)
        print("[Q1] AVANT cast : instances 1502 publiees = %d" % n0)

        # Le tour peut etre a l'adversaire au sortir de `march` -> le rendre a mon camp.
        for _ in range(3):
            if units_by_id(decision(sid, rid)).get(baldr, {}).get("ctrl"):
                break
            apply_action(sid, rid, {"kind": "endturn"})
        res = apply_action(sid, rid, {"kind": "ability", "casterId": baldr,
                                      "targetId": baldr,
                                      "abilityType": RITES_OF_MORKAI_ABILITY})
        print("[cast] RitesOfMorkai(u%d) ok=%s" % (baldr, res.get("ok")))
        if not res.get("ok"):
            print("[cast] ECHEC: %s" % json.dumps(res)[:400])
            return 2

        for inc in (False, True):
            v = decision(sid, rid, include_inactive=inc)
            hits = [(u.get("id"), e) for u in (v.get("units") or [])
                    for e in (u.get("effects") or [])
                    if e.get("effectType") == RITES_OF_MORKAI_EFFECT]
            print("[Q1] includeInactive=%-5s -> instances 1502 = %d" % (inc, len(hits)))
            for uid, e in hits:
                print("       unit=%s name=%s type=%s active=%s removed=%s eid=%s rem=%s"
                      % (uid, e.get("name"), e.get("effectType"), e.get("active"),
                         e.get("removed"), e.get("effectId"), e.get("remaining")))

        # --- Q2 cote PORT (etat live, pose NATIVE) ----------------------------------
        board, dv, ob, snap = capture(sid, rid)
        st0 = load_state(dv, ob, snap, board=board)
        seeded = [(uid, e) for uid, lst in (st0.effects.by_unit or {}).items()
                  for e in lst if e.effect_type == RITES_OF_MORKAI_EFFECT]
        print("[Q2/port] instances 1502 SEEDEES par load_state = %d" % len(seeded))
        for uid, e in seeded:
            print("       unit=%s active=%s rem=%s source=%s abil_lvl=%s mult=%s"
                  % (uid, e.active, e.remaining_turns, e.source, e.ability_level,
                     e.ability_variables_multiplier))
        got = port_gate_matrix(board, dv, ob, snap, victim, foes[0])
        expect = (True, False, True, False)
        print("[Q2/port] matrice=%s attendu=%s -> %s"
              % (got, expect, "OK" if got == expect else "MISMATCH"))
        if got != expect:
            rc = 1

        # --- Q2 face NATIVE : tuer l'unite inspiree EN LIVE --------------------------
        apply_action(sid, rid, {"kind": "endturn"})            # passe la main a l'adversaire
        for fid in foes:
            v = decision(sid, rid)
            before_u = units_by_id(v).get(victim) or {}
            aid = normal_attack_id(v, fid, victim)
            if aid is None:
                print("[live] u%d n'a pas de plan sur u%d (hors portee)" % (fid, victim))
                continue
            r = apply_action(sid, rid, {"kind": "ability", "casterId": fid,
                                        "targetId": victim, "abilityType": aid})
            u = units_by_id(decision(sid, rid, include_inactive=True)).get(victim) or {}
            still = [e for e in (u.get("effects") or [])
                     if e.get("effectType") == RITES_OF_MORKAI_EFFECT]
            print("[live] u%d attaque u%d (ability %s) ok=%s : hp %s -> %s alive=%s 1502=%d"
                  % (fid, victim, aid, r.get("ok"), before_u.get("hp"), u.get("hp"),
                     u.get("alive"), len(still)))
            for act in (r.get("actions") or []):
                for ev in (act.get("events") or []):
                    print("        ev %s" % json.dumps(ev)[:260])
            if not u.get("alive"):
                break

        # --- VECTEUR D'EXTINCTION : l'instance 1502 peut-elle devenir INERTE en bataille ? -----
        # `RefreshEffectsOperation$$DeactivateEffect` est le SEUL ecrivain de `+0x5c = 0` hors du
        # 2e volet `IdunBattleLogic.Entities.DSLBehaviors$$DeactivateEffect` (que 1502 n'emprunte pas : `removeEffect`=1 ->
        # `BaseEffect$$GetRemoveEffectBehaviour`). On observe l'instance survivante tour apres tour :
        # si elle FINIT `active=false`, l'extinction est atteignable ; si elle DISPARAIT d'un coup,
        # c'est un RETRAIT (`RemoveEffect`) et l'inertie reste hors de portee du jeu.
        survivor = next((m for m in mine if m != victim and m != baldr), baldr)
        print("[extinction] suivi de l'instance 1502 de u%d, tour apres tour :" % survivor)
        for i in range(6):
            v = decision(sid, rid, include_inactive=True)
            u = units_by_id(v).get(survivor) or {}
            rows = [e for e in (u.get("effects") or [])
                    if e.get("effectType") == RITES_OF_MORKAI_EFFECT]
            print("   t+%d : alive=%s | 1502 = %s" % (
                i, u.get("alive"),
                [(e.get("active"), e.get("removed"), e.get("remaining")) for e in rows] or "ABSENT"))
            if not rows:
                break
            apply_action(sid, rid, {"kind": "endturn"})
        return rc
    finally:
        if not a.keep:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            print("[dispose] runnerId=%d" % rid)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
