"""#494-r1 -- DECOMPOSITION du montage `db-4` de `test_doombolt_live.py`, etage par etage.

`db-4` est le SEUL montage historique de Doombolt qui confronte l'ordre, et il est HETEROGENE (PV
naturels, quatre visualId differents). Quand l'ordre du port y bouge, il faut savoir LEQUEL des
etages a bouge -- jamais fitter le resultat.

Ce probe monte le MEME build que `probe_psychic_aoe.CASES["db-4"]` (meme seed, meme board, meme
roster, PV NON egalises) et imprime, cible par cible :
  * PV / PV max / armure / defense / statDelta          -- ce que la cle lisait DEJA
  * elevation de la tuile + elevation du caster         -- l'entree POSITIONNELLE (#494-r1)
  * l'utilite portee SANS `owner_id` (cle constante) et AVEC (cle positionnelle)
  * l'ordre final du port dans les DEUX regimes, et l'ordre joue par le NATIF

Usage : python probe_494r1_db4_decompose.py [--seed 31337] [--board MC1_67] [--state-file <abs>]
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

# Le MONTAGE est celui de `probe_psychic_aoe` (recherche d'un hub 6-voisins puis DEPLACEMENT des
# unites) : on le REUTILISE tel quel plutot que de le recopier -- un montage recopie derive.
import probe_psychic_aoe as PA   # noqa: E402

from engine.battle_query import iterate_surrounding_tiles_order_key   # noqa: E402
from engine.entities.effects.magnitude import ability_var             # noqa: E402
from engine.entities.pathfinding.board import Board                   # noqa: E402
from engine.runner.abilities.behaviours.context import entities_from_state   # noqa: E402
from engine.runner.abilities.thousandsons import (DOOMBOLT_ID, _ability_state,
                                                  doombolt_targets_selector)   # noqa: E402
from engine.runner.components import StatsComponent, HealthComponent  # noqa: E402
from engine.runner.messages import ActiveAbilityMessage               # noqa: E402
from engine.runner.operations.damage_utility import (_target_utility, damage_utility_weights,
                                                     sort_units_by_damage_utility)  # noqa: E402,E501
from engine.runner.prng import IntBasedMersenneTwister                # noqa: E402
from engine.runner.runner import Runner                               # noqa: E402
from engine.runner.snapshot import load_state                         # noqa: E402

CASTER = "thousAhriman"
A_UNITS = "necroOverlord,necroWarden,eldarRanger,orksNob"
DOOMBOLT = 1102


def _rpc(sid, m, b=None, t=60):
    r = R._rpc(sid, m, [b] if b is not None else [], timeout=t)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _live_hits(res, ability):
    out = []
    for a in (res.get("actions") or []):
        for e in (a.get("events") or []):
            td = e.get("tags")
            if isinstance(td, str):
                td = json.loads(td)
            if td and td.get("Active_Ability_Type") == ability and "Amount" in td:
                out.append((td["Target_Id"], td["Amount"]))
    return out


def _first_seen(seq):
    out = []
    for tid, _a in seq:
        if tid not in out:
            out.append(tid)
    return out


def run(seed="31337", board_id="MC1_67", state_file=None, keep=False, egalise=False):
    """`egalise` = `--hp-target/--hp-player` -> PV EGAUX et `Armor = FixedArmor = 0`. C'est le
    DISCRIMINANT du montage `db-4` : tel quel il est HETEROGENE (PV naturels, quatre `fixedArmor`
    differents), donc plusieurs etages de la cle y bougent ENSEMBLE. Egalise, il ne reste que la
    GEOMETRIE -- et il repond a « le bonus d'elevation entre-t-il dans la cle sur CETTE
    geometrie ? » sans que l'armure puisse repondre a sa place."""
    sf = state_file or str(PYDIR.parents[1] / "logs" / "runners" / "probe-494r1-db4.json")
    Path(sf).parent.mkdir(parents=True, exist_ok=True)
    sid = R._resolve_session()
    hp = ["--hp-target", "400000", "--hp-player", "400000"] if egalise else []
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board_id,
            "--roster", "1", "--p-units", CASTER, "--a-units", A_UNITS, *hp,
            "--state-file", sf, "--no-ai"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("ERREUR build:", (p.stderr or p.stdout or "")[-1200:])
        return 2
    rid = json.loads(Path(sf).read_text())["runnerId"]
    try:
        live_h = PA.Live(sid, rid)
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        units0 = live_h.units()
        caster0 = next((u for u in units0 if u.get("visualId") == CASTER), None)
        enemies0 = [u for u in units0 if u.get("id") != caster0["id"]]
        geo = PA.pick_geometry(board, "db-4", set())
        if geo is None:
            print("ERREUR: aucune geometrie candidate (hub 6-voisins)")
            return 2
        wanted = [(enemies0[0]["id"], geo["target"])]
        for i, pp in enumerate(geo["extra"]):
            if i + 1 < len(enemies0):
                wanted.append((enemies0[i + 1]["id"], pp))
        far = [pp for pp in PA.free_tiles(board, set())
               if hexgeo.distance(pp, geo["target"]) >= 5]
        for j in range(len(geo["extra"]) + 1, len(enemies0)):
            if far:
                wanted.append((enemies0[j]["id"], far[j % len(far)]))
        wanted.append((caster0["id"], geo["caster"]))
        for uid, dest in wanted:
            PA.drive_to(live_h, board, uid, dest)
        for _ in range(6):
            d = live_h.dec()
            cu = next((u for u in (d.get("units") or []) if u.get("id") == caster0["id"]), None)
            if cu is not None and cu.get("owner") == d.get("currentPlayer"):
                break
            live_h.endturn()
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        ahri = next((u for u in units if u.get("visualId") == CASTER), None)
        if ahri is None:
            print("ERREUR: caster absent")
            return 2
        ap = (ahri["pos"]["col"], ahri["pos"]["row"])
        ens = [u for u in units if u.get("owner") != ahri.get("owner")
               and hexgeo.distance((u["pos"]["col"], u["pos"]["row"]), ap) <= 2]
        if not ens:
            print("ERREUR: aucun ennemi a portee apres le drive")
            return 2
        # MEME cible que `probe_psychic_aoe` : celle qui occupe `geo["target"]`.
        target = next((u for u in ens if (u["pos"]["col"], u["pos"]["row"]) == tuple(geo["target"])),
                      sorted(ens, key=lambda u: (hexgeo.distance(
                          (u["pos"]["col"], u["pos"]["row"]), ap), u["id"]))[0])
        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 40)
        tm = _rpc(sid, "tileMeta", {"runnerId": rid}, 40)
        elev = {}
        for t in ((tm.get("tiles") or []) if isinstance(tm, dict) else []):
            if isinstance(t, dict) and t.get("col") is not None:
                elev[(int(t["col"]), int(t["row"]))] = t.get("elevation")
        raw = {}
        eids = {int(u["id"]) for u in ens}
        blob = snap.get("units") if isinstance(snap, dict) else None
        for e in (list(blob.values()) if isinstance(blob, dict) else (blob or [])):
            if isinstance(e, dict):
                for cle in ("squadId", "unitId", "id", "entityId"):
                    if e.get(cle) is not None and int(e[cle]) in eids:
                        raw[int(e[cle])] = e
                        break
        s0 = _rpc(sid, "dumpRng", {"runnerId": rid}, 30)
        res = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": ahri["id"], "targetId": target["id"],
            "abilityType": DOOMBOLT}}, 90)
        live = _live_hits(res, DOOMBOLT)

        st = load_state(dv, ob, snap, board=board)
        rng = IntBasedMersenneTwister()
        rng.mt, rng.mti = list(s0["mt"]), s0["mti"]
        st.rng = rng
        ents = entities_from_state(st, ahri["id"], target["id"])
        cand = [int(u["id"]) for u in (doombolt_targets_selector().evaluate(ents) or [])
                if isinstance(u, dict) and u.get("id") is not None]
        level, mult = _ability_state(st, ahri["id"])
        dmin = int(ability_var(DOOMBOLT_ID, "minDmg", level, multiplier_pct=mult) or 0)
        wt = damage_utility_weights()

        st2 = load_state(dv, ob, snap, board=board)
        print("runner %s | board %s | seed %s" % (rid, board_id, seed))
        print("caster u%s @%s elev=%s | cible du message u%s"
              % (ahri["id"], ap, elev.get(ap), target["id"]))
        print("\n--- etage 0 : ce que la cle PEUT lire ---")
        print("%-6s %-16s %-8s %-6s %-9s %-9s %-7s %-6s %-6s %s"
              % ("id", "visualId", "pos", "elev", "hp", "maxHp", "armor", "fixArm", "def",
                 "statDelta"))
        for u in ens:
            uid = int(u["id"])
            pos = (u["pos"]["col"], u["pos"]["row"])
            e = st2.get_entity(uid)
            hc = e.get_component(HealthComponent) if e is not None else None
            sc = e.get_component(StatsComponent) if e is not None else None
            ctx = getattr(sc, "ctx", None)
            r0 = raw.get(uid) or {}
            print("%-6s %-16s %-8s %-6s %-9s %-9s %-7s %-6s %-6s %s"
                  % (uid, u.get("visualId"), "%d,%d" % pos, elev.get(pos),
                     getattr(hc, "hp", None), getattr(hc, "hp_max", None),
                     getattr(ctx, "armor", None), getattr(ctx, "fixed_armor", None),
                     (r0.get("stats") or {}).get("defense"),
                     json.dumps(r0.get("statDelta") or {}, sort_keys=True)))
        print("\n--- etage 1 : ORDRE SOURCE du selecteur (avant tri) ---")
        print("  %s" % cand)
        print("  cube_key : %s" % {c: iterate_surrounding_tiles_order_key(
            (next(u for u in ens if int(u["id"]) == c)["pos"]["col"],
             next(u for u in ens if int(u["id"]) == c)["pos"]["row"])) for c in cand})
        print("\n--- etage 2 : UTILITE portee, SANS owner (cle constante) vs AVEC (positionnelle) ---")
        u_sans = {c: _target_utility(st2, c, dmin, dmin, wt) for c in cand}
        u_avec = {c: _target_utility(st2, c, dmin, dmin, wt, owner_id=ahri["id"]) for c in cand}
        for c in cand:
            print("  u%-4s sans=%.10f  avec=%.10f  %s"
                  % (c, u_sans[c], u_avec[c], "" if u_sans[c] == u_avec[c] else "<== POSITIONNEL"))
        print("\n--- etage 3 : ORDRE du tri, dans les DEUX regimes ---")
        print("  ordre source                      : %s" % cand)
        print("  tri SANS owner (cle constante)    : %s"
              % sort_units_by_damage_utility(st2, cand, dmin, dmin))
        print("  tri AVEC owner (positionnelle)    : %s"
              % sort_units_by_damage_utility(st2, cand, dmin, dmin, owner_id=ahri["id"]))
        print("  tri SANS owner, ordre source = id : %s"
              % sort_units_by_damage_utility(st2, sorted(cand), dmin, dmin))
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=ahri["id"], target_id=target["id"],
                                          ability_type=DOOMBOLT))
        diag = runner.ability_handler.last or {}
        print("\n--- etage 4 : ce que le PORT joue / ce que le NATIF joue ---")
        print("  port  ordre=%s hits=%s" % (diag.get("targets"), diag.get("hits")))
        print("  natif ordre=%s" % _first_seen(live))
        print("  natif per-coup=%s" % live)
        return 0
    finally:
        if not keep:
            subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", sf],
                           cwd=str(PYDIR), capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="31337")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--egalise", action="store_true",
                    help="PV egaux + Armor/FixedArmor a 0 : ne laisse que la GEOMETRIE")
    a = ap.parse_args()
    raise SystemExit(run(seed=a.seed, board_id=a.board, state_file=a.state_file, keep=a.keep,
                         egalise=a.egalise))


if __name__ == "__main__":
    main()
