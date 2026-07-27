"""Probe #133-C -- volet DEGAT du passif `DestroyTheWitch` (templHelbrecht, triggered 1091).

`DestroyTheWitch_ExtraDamage` (effet 1089) = aura posee sur Helbrecht, projetee sur **lui-meme +
ses allies hex-adjacents** (`CreateTargetSelector` = `Unique(SurroundingFriends(Owner,1) + Owner)`),
qui gagnent +`extraDmg` PLAT par coup sur leurs attaques **MELEE contre une cible Psyker**
(`CreateEffectDamageBonusForAttack` = `OwnerIsCaster & IsMeleeAttack & HasTrait(Target, Psyker)`).

Trois scenarios crafte (positions PILOTEES, jamais subies) :
  --leg self  (defaut) : HELBRECHT frappe un Psyker            -> bonus ENGAGE   (patte SELF)
  --leg aura           : un ALLIE ADJACENT de Helbrecht frappe un Psyker -> bonus ENGAGE (patte AURA)
  --leg aura-far       : MEME allie, MEME cible Psyker, mais Helbrecht LOIN (>=2 hexes) -> bonus NUL
                         (cas NEGATIF de la GEOMETRIE `SurroundingFriends(Owner, 1)`)
  --leg none           : MEME attaquant, cible NON-Psyker      -> bonus NUL      (cas NEGATIF du gate
                         `HasTrait(Target, Psyker)`)

Chaque scenario finit par un REPLAY-DIFF RNG-seede : per-hit et PV offline == live.

Usage :  python probe_133_dtw_damage.py [--leg self|aura|none]
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import deque
from pathlib import Path

import rl_collect_batch as R
from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent
from engine.runner.damage_model import target_trait_names
from engine.entities.pathfinding.board import Board
from engine.entities.effects.magnitude import ability_var

PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parents[1] / "logs" / "runners"

HELBRECHT = "templHelbrecht"
# Allie MELEE choisi pour son kit SANS AUCUN modificateur de degat propre -> la seule variable
# mesuree est l'aura DestroyTheWitch. `ultraApothecary` : traits {Healer, Hero}, passif `Narthecium`
# (trigger de revive, porte, aucune contribution au degat), arme melee 1x Piercing.
#
# DEUX allies ont ete ECARTES en cours de route, et pour des raisons DIFFERENTES -- les deux valent
# d'etre notees, ce sont des pieges de HARNAIS, pas des bugs du port :
#  * `templSwordBrother` (le voisin « naturel » de Helbrecht) : son passif `ChampionOfTheFeast` est
#    un GAP non porte (cf. docs/rl/passive-ability-coverage.md) -> LIVE emet un 2e evenement de
#    degat `Active_Ability_Type = None` que l'offline ne produit pas (1er coup deja bit-exact).
#  * `astraBullgryn` : son passif `AvalancheOfMuscle` (+extraDmg[L50]x1.8 = 599/coup) est gate
#    `IsCharging`, porte offline par le PROXY `has_moved` (`UnitFlag.Moved`) -- residu DEJA
#    DOCUMENTE dans `AvalancheOfMuscleExtraDamageEffect`. Selon le nombre de tours consommes par la
#    marche, les deux predicats divergent et injectent un ecart de 599/coup SANS RAPPORT avec l'aura.
FRIEND = "ultraApothecary"
PSYKER = "astraPrimarisPsy"      # trait Psyker
NONPSY = "orksNob"               # sans trait Psyker -> cas NEGATIF


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def rpc(sid, m, body=None, timeout=60):
    return _unwrap(R._rpc(sid, m, [body] if body is not None else [], timeout=timeout))


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def build(tag):
    LOGS.mkdir(parents=True, exist_ok=True)
    state = LOGS / ("dtwdmg_%s.json" % tag)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", "777",
            "--state-file", str(state), "--board", "MC1_67", "--roster", "2",
            "--p-units", "%s,%s" % (HELBRECHT, FRIEND),
            "--a-units", "%s,%s" % (PSYKER, NONPSY),
            "--hp-player", "999999", "--hp-target", "999999"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO: %s" % (p.stderr or p.stdout or "")[-600:])
        return None, None
    return json.loads(state.read_text())["runnerId"], state


def _bfs(board, src):
    dist = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def _u(dv, vis):
    return next((x for x in (dv.get("units") or []) if x.get("visualId") == vis and x.get("alive")),
                None)


def _walk_to(sid, rid, board, mover_vis, anchor_tile_of, want, turns=30):
    """Rapproche `mover_vis` jusqu'a `want` hexes de la tuile rendue par `anchor_tile_of(dv)`.
    Pilote MON camp (`aiMovableTiles side=friendly`) ; `endturn` quand ce n'est pas mon tour."""
    for _ in range(turns):
        dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        mv = _u(dv, mover_vis)
        anchor = anchor_tile_of(dv)
        if mv is None or anchor is None:
            return dv
        p = mv.get("pos") or {}
        cur = board.id_at(p.get("col"), p.get("row"))
        dist = _bfs(board, anchor)
        if dist.get(cur) == want:
            return dv
        if dv.get("currentPlayer") != mv.get("owner"):
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        mt = rpc(sid, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        row = next((x for x in (mt.get("units") or []) if x.get("unitId") == mv["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((row or {}).get("tiles") or [])}
        exact = [t for t in reach if dist.get(t) == want]
        pool = exact or [t for t in reach if t in dist]
        if not pool:
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        best = exact[0] if exact else min(pool, key=lambda t: dist[t])
        col, r = reach[best]
        rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mv["id"], "to": {"col": col, "row": r}}}, 40)
        if not exact:
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leg", choices=("self", "aura", "aura-far", "none"), default="self")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    att_vis = FRIEND if args.leg.startswith("aura") else HELBRECHT
    tgt_vis = NONPSY if args.leg == "none" else PSYKER
    sid = R._resolve_session()
    rid, state_file = build(args.leg)
    if rid is None:
        return
    try:
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")

        def tile_of(dv, vis):
            x = _u(dv, vis)
            p = (x or {}).get("pos") or {}
            return board.id_at(p.get("col"), p.get("row")) if x else None

        # 1) l'ATTAQUANT vient au contact de la CIBLE
        _walk_to(sid, rid, board, att_vis, lambda dv: tile_of(dv, tgt_vis), 1)
        # 2) patte AURA : HELBRECHT doit etre HEX-ADJACENT a l'attaquant (le selecteur natif est
        #    `SurroundingFriends(Owner, 1)`) -> on le pilote lui aussi.
        if args.leg == "aura":
            _walk_to(sid, rid, board, HELBRECHT, lambda dv: tile_of(dv, att_vis), 1)
        dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        att, tgt, hel = _u(dv, att_vis), _u(dv, tgt_vis), _u(dv, HELBRECHT)
        if att is None or tgt is None:
            print("unites manquantes"); return
        # tour du camp attaquant
        for _ in range(4):
            if dv.get("currentPlayer") == att.get("owner"):
                break
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            att, tgt, hel = _u(dv, att_vis), _u(dv, tgt_vis), _u(dv, HELBRECHT)
        d_at = _bfs(board, tile_of(dv, tgt_vis)).get(tile_of(dv, att_vis))
        d_ha = _bfs(board, tile_of(dv, att_vis)).get(tile_of(dv, HELBRECHT))
        print("[state] leg=%s att=%s u%s @%s | tgt=%s u%s @%s | dist(att,tgt)=%s dist(helb,att)=%s"
              % (args.leg, att_vis, att["id"], att["pos"], tgt_vis, tgt["id"], tgt["pos"],
                 d_at, d_ha))
        norm = next((a for a in (att.get("abilities") or []) if a.get("kind") == "normal"), None)
        if norm is None:
            print("pas d'attaque normale"); return
        ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 40)
        st = load_state(dv, ob, snap, board=board)
        # --- contribution ATTENDUE, lue des classes portees (pas d'un chiffre en dur) -----------
        he = st.get_entity(hel["id"])
        hhc = he.get_component(HealthComponent) if he is not None else None
        heff = (st.effects.active_effects(hel["id"], {"hp": hhc.hp if hhc else None})
                if st.effects is not None else [])
        dtw = next((e for e in heff if getattr(e, "name", None) == "DestroyTheWitch_ExtraDamage"),
                   None)
        tgt_traits = target_trait_names(st, tgt["id"])
        expected = None
        if dtw is not None:
            if args.leg.startswith("aura"):
                ap_ = st.get_entity(att["id"]).get_component
                from engine.runner.components import PositionComponent, OwnerComponent
                apc, aoc = ap_(PositionComponent), ap_(OwnerComponent)
                hpc = he.get_component(PositionComponent)
                hoc = he.get_component(OwnerComponent)
                expected = dtw.create_aura_attack_damage_bonus_for_ally({
                    "att_id": att["id"], "att_pos": (apc.col, apc.row), "att_team": aoc.team,
                    "owner_id": hel["id"], "owner_pos": (hpc.col, hpc.row), "owner_team": hoc.team,
                    "is_melee": True, "tgt_traits": tgt_traits})
            else:
                expected = dtw.create_effect_damage_bonus_for_attack(
                    is_ranged=False, target_traits=tgt_traits)
        print("[port ] effet 1089 sur Helbrecht=%s ; tgt_traits=%s ; bonus attendu=%s "
              "(extraDmg[ablvl=%s]xmult=%s -> %s)"
              % (dtw is not None, sorted(tgt_traits), expected,
                 getattr(dtw, "ability_level", None), getattr(dtw, "ability_variables_multiplier", None),
                 ability_var("DestroyTheWitch", "extraDmg", getattr(dtw, "ability_level", None) or 0,
                             multiplier_pct=getattr(dtw, "ability_variables_multiplier", 100) or 100)))
        s0 = rpc(sid, "dumpRng", {"runnerId": rid}, 30)
        st.rng = _seed_rng(s0)
        runner = Runner(st).install_default_handlers(20)
        hp_before = st.get_entity(tgt["id"]).get_component(HealthComponent).hp
        res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": att["id"], "targetId": tgt["id"],
            "abilityType": norm["id"]}}, 60)
        a0 = (res.get("actions") or [{}])[0]
        if not (res.get("ok") and a0.get("ok")):
            print("[live] applyAction KO: %s" % json.dumps(res, default=str)[:800])
        live_ph, evade = [], False
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if td.get("Target_Id") == tgt["id"] and "Amount" in td:
                live_ph.append(td.get("Amount"))
                evade = evade or bool(td.get("Attack_DidEvade"))
                print("   [tag] amount=%s ability=%s effect=%s attacker=%s"
                      % (td.get("Amount"), td.get("Active_Ability_Type"),
                         td.get("Effect_Type"), td.get("Attacker_Id") or td.get("Caster_Id")))
        live_after = next((u.get("hp") for u in (res.get("units") or [])
                           if u.get("squadId") == tgt["id"]), None)
        runner.apply(AttackUnitMessage(att["id"], tgt["id"]))
        rr = runner.damage_handler.last
        off_after = st.get_entity(tgt["id"]).get_component(HealthComponent).hp
        print("[live] per-hit=%s hp=%s (avant %s) evade=%s" % (live_ph, live_after, hp_before, evade))
        print("[off ] per-hit=%s hp=%s" % ((rr or {}).get("per_hit"), off_after))
        print("[off ] rr=%s" % json.dumps(rr, default=str)[:700])
        import hexgeo
        from engine.runner.components import PositionComponent as _PC
        _hp2 = he.get_component(_PC) if he is not None else None
        _ap2 = st.get_entity(att["id"]).get_component(_PC)
        print("[diag] helb=%s att=%s hexdist=%s | effets att(live)=%s"
              % ((_hp2.col, _hp2.row) if _hp2 else None, (_ap2.col, _ap2.row) if _ap2 else None,
                 hexgeo.distance((_hp2.col, _hp2.row), (_ap2.col, _ap2.row)) if (_hp2 and _ap2) else None,
                 [e.get("name") for e in (att.get("effects") or [])]))
        ok = ((rr or {}).get("per_hit") == live_ph) and (off_after == live_after)
        print("[VERDICT leg=%s] %s" % (args.leg, "MATCH" if ok else "DIVERGENCE"))
    finally:
        if not args.keep:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
            state_file.unlink(missing_ok=True)
            print("[dispose] %s" % rid)


if __name__ == "__main__":
    main()
