"""case-277 -- l'ecart de degat de `FlailSwing` (1042) : DECOMPOSITION PAR ETAGE.

QUESTION (binaire) : l'ecart port/live releve sur le montage `revive-flail` de #178
(port 21680 / live 21023, +3,1 %) vient-il d'UN etage IDENTIFIE de la chaine de degat,
ou est-il diffus ?

AUCUN SCALAIRE N'EST FITTE. Le probe separe les etages en trois mesures independantes :

  1. ETAGE CONSOMMATION RNG -- `dumpRng` avant/apres le cast LIVE donne le nombre EXACT de
     `genrand_int32` du natif ; les rejeux offline sont instrumentes et rendent le leur. Un
     ecart de COMPTE localise l'ecart EN AMONT de la formule.
  2. ETAGE CELLULE D'ARME -- les bornes REDUITES `(lo, hi)` que `AttackDamageOperation._run_hits`
     recoit (mirror `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64` ->
     `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing`
     -> `FixMath.NET.Fix64$$Round`), plus `GetStat(Attack)`, le percage et l'armure du defenseur.
  3. ETAGE DECALAGE -- on rejoue le port avec le flux RNG AVANCE de `k` tirages (k = 0..4). Si un
     `k > 0` reproduit les valeurs live A L'UNITE, la CELLULE du port est JUSTE et l'ecart est un
     DECALAGE de flux (etage amont), pas un facteur. Si AUCUN `k` ne marche, c'est la cellule.

TROIS VOIES DE REJEU, sur le MEME etat et le MEME flux :

  * `direct`   -- `FlailSwingAbility().execute_behaviour(...)` appele A LA MAIN. C'est EXACTEMENT
                  ce que fait `probe_178_overkill_gate._replay_attack`, donc le contrepoint qui a
                  produit le 21680.
  * `pipeline` -- `Runner.apply(ActiveAbilityMessage(...))` : la voie de PRODUCTION, qui passe par
                  `AbilityHandler.visit_ActiveAbilityMessage` et emet donc `On(0x2a = PreUnitAbility)`
                  avant la behaviour (mirror `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`).
  * `pipeline_nohaze` -- la MEME voie, trigger `HazeOfCorruption_TargetFinderAbility` NEUTRALISE.
                  Anti-tautologie : si celui-la reproduit aussi le live, la mesure ne prouve rien.

DEUX REGIMES GEOMETRIQUES (le SECOND cas discriminant, exige avant toute conclusion) :

  * `k1` -- geometrie de #178 : la victime au centre, `deathBlightlord` ET `ultraApothecary` sur
            son ring 1. Le pool de `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateBehaviour`
            (`Damageable(AdjacentEnemies(Self) & AdjacentFriends(Target))`) contient 1 candidat.
  * `k0` -- MEME montage, `ultraApothecary` TELEPORTE LOIN : le pool est VIDE. Un etage
            MULTIPLICATIF survivrait a ce changement de geometrie ; un decalage de flux DISPARAIT.
  * `k2` -- GENERALISATION : les DEUX voisins communs du caster et de la victime sont occupes par
            des allies de la victime -> pool = 2, donc 2 tirages amont. L'ECHELLE `k = 0/1/2` est le
            vrai discriminant : elle refute a la fois « forfait de 2 tirages par cast du porteur »
            (qui predirait 2 partout) et « pas de tirage quand le pool tient dans amount » (0
            partout), et elle verifie que le port suit le CARDINAL, pas une constante.

Discipline runner : state-file ABSOLU sous logs/, `--board` explicite, dispose en fin. ASCII only.

CLI (depuis scripts/python) :
  python probe_277_flail_damage_stages.py --seeds 17831
  python probe_277_flail_damage_stages.py --seeds 17831,17833 --regimes k1,k0
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

from probe_r6_round_materialize import _mkrpc                    # noqa: E402
from probe_159_ah_bounds import _genrand_steps                   # noqa: E402

BOARD = "MC1_67"
FLAIL = 1042
CARRIER = "deathBlightlord"      # FlailSwing (1042) + passif HazeOfCorruption
VICTIM = "genesPrimus"
APO = "ultraApothecary"          # allie de la victime -> alimente le pool Haze
EXTRA = "necroWarden"            # 2e allie de la victime -> regime k2 (pool de cardinal 2)
FILLER = "astraBullgryn"         # 2e unite de mon camp, tenue a l'ecart
FAR = (6, 7)                     # tuile de parking (hors ring de la victime)
VERY_FAR = (0, 0)


# --------------------------------------------------------------------------- montage live


def _build(seed, p_units, a_units, hp, rank=17, crit="0,0"):
    sf = ROOT / "logs" / "runners" / ("p277-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", BOARD, "--rank", str(rank), "--p-units", ",".join(p_units),
         "--a-units", ",".join(a_units), "--hp-target", str(hp), "--crit", crit,
         "--block-target", "0,0"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        print("[277] build KO : %s" % ((proc.stderr or proc.stdout or "")[-600:]))
        return None, None
    return int(json.loads(sf.read_text())["runnerId"]), sf


def _view(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)


def _by_vis(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _move(rpc, rid, uid, col, row):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def _geometry(rpc, rid, center, regime):
    """GEOMETRIE DRIVEE (jamais subie) -- mirror de `probe_178_overkill_gate.setup` : la victime au
    centre, le porteur sur son ring 1, le filler parque. Le CARDINAL du pool Haze est pilote par la
    seule position des ALLIES DE LA VICTIME :
      k0 -> tous hors du ring         (pool vide, 0 tirage amont)
      k1 -> l'apothicaire sur ring[1] (pool = 1)
      k2 -> les DEUX voisins COMMUNS du caster et de la victime occupes (pool = 2)
    Sur une grille hex, deux hexes adjacents ont exactement 2 voisins communs : c'est la borne
    naturelle du regime k2, et elle sature `amount = 2` du `PickRandomly`."""
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")
    ccol, crow = center
    ctile = board.id_at(ccol, crow)
    ring_t = list(board.neighbours(ctile))
    if len(ring_t) < 3:
        raise RuntimeError("centre (%d,%d) trop pauvre en voisins (%d)" % (ccol, crow, len(ring_t)))
    dv = _view(rpc, rid)
    wanted = [CARRIER, FILLER, VICTIM, APO] + ([EXTRA] if regime == "k2" else [])
    ids = {}
    for v in wanted:
        u = _by_vis(dv, v)
        if u is None:
            raise RuntimeError("unite absente du build : %s" % v)
        ids[v] = u["id"]
    carrier_t = ring_t[0]
    _move(rpc, rid, ids[FILLER], *FAR)
    _move(rpc, rid, ids[VICTIM], ccol, crow)
    _move(rpc, rid, ids[CARRIER], *board.coord(carrier_t))
    if regime == "k0":
        _move(rpc, rid, ids[APO], *VERY_FAR)
    elif regime == "k1":
        _move(rpc, rid, ids[APO], *board.coord(ring_t[1]))
    else:
        common = [t for t in board.neighbours(carrier_t) if t in set(ring_t)]
        if len(common) < 2:
            raise RuntimeError("regime k2 : %d voisin(s) commun(s) seulement" % len(common))
        _move(rpc, rid, ids[APO], *board.coord(common[0]))
        _move(rpc, rid, ids[EXTRA], *board.coord(common[1]))
    return board, ids, bg


def _capture(rpc, rid, bg):
    return {"dec": _view(rpc, rid),
            "ob": rpc("observeBattle", {"runnerId": rid}, 60),
            "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
            "bg": bg,
            "rng": rpc("dumpRng", {"runnerId": rid}, 30)}


def _live_cast(rpc, rid, cid, tid):
    """Cast LIVE + lecture des evenements natifs : per-coup (`Amount`) et bonds `HazeOfCorruption`
    (`Effect_SourceTriggeredAbility == 1076`, temoin DIRECT du cardinal du pool)."""
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(cid), "targetId": int(tid),
        "abilityType": FLAIL}, "captureEvents": True}, 150)
    rows, bonds = [], 0
    for act in (res.get("actions") or []):
        for ev in (act.get("events") or []):
            td = ev.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if td.get("Effect_SourceTriggeredAbility") == 1076:
                bonds += 1
            if "Amount" in td:
                rows.append(td)
    return res, rows, bonds


# --------------------------------------------------------------------------- rejeu instrumente


def _load(cap, board):
    from engine.runner.snapshot import load_state
    return load_state(cap["dec"], cap["ob"], cap["snap"], board=board)


def _replay(cap, board, cid, tid, mode, skip=0, big_hp=10 ** 7):
    """Rejoue le cast OFFLINE sur le MEME etat et le MEME flux, et rend la DECOMPOSITION :
        {per_hit, total, n_genrand, rolls, cell, attack, pierce, armor, bonds}
    `skip` = nombre de `genrand_int32` CONSOMMES A VIDE avant le rejeu (etage DECALAGE).
    `mode` : "direct" (execute_behaviour a la main = la voie de probe_178),
             "pipeline" (Runner.apply(ActiveAbilityMessage) = la voie de PRODUCTION),
             "pipeline_nohaze" (idem, trigger HazeOfCorruption_TargetFinder neutralise)."""
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent, StatsComponent
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.entities.stats import StatType

    st = _load(cap, board)
    ent = st.get_entity(int(tid))
    hc = ent.get_component(HealthComponent)
    hp0 = int(hc.hp)
    hc.hp = int(big_hp)                       # la victime ne meurt pas -> degat NON tronque

    rolls, cnt = [], [0]

    class _Recording(IntBasedMersenneTwister):
        __slots__ = ()

        def genrand_int32(self):
            cnt[0] += 1
            return IntBasedMersenneTwister.genrand_int32(self)

        def next_internal(self, lo, hi):
            base = cnt[0]
            out = IntBasedMersenneTwister.next_internal(self, lo, hi)
            rolls.append({"lo": lo, "hi": hi, "out": out, "n": cnt[0] - base})
            return out

    rng = _Recording()
    rng.mt = list(cap["rng"]["mt"])
    rng.mti = cap["rng"]["mti"]
    for _ in range(int(skip)):
        rng.genrand_int32()
    cnt[0] = 0
    rolls.clear()
    st.rng = rng

    cell = {}
    orig_hits = AttackDamageOperation._run_hits

    def _spy(rngo, hit_nc, hit_cr, *a, **kw):
        cell.setdefault("all", []).append(((hit_nc.min, hit_nc.max), (hit_cr.min, hit_cr.max)))
        cell.setdefault("weapon", (hit_nc.min, hit_nc.max))
        return orig_hits(rngo, hit_nc, hit_cr, *a, **kw)

    AttackDamageOperation._run_hits = staticmethod(_spy)
    haze_orig = None
    try:
        if mode == "pipeline_nohaze":
            from engine.runner.operations.triggers.loki.haze_of_corruption import (
                HazeOfCorruptionTargetFinderAbility as _H)
            haze_orig = _H.matches
            _H.matches = lambda self, state, ev: False
        if mode == "direct":
            from engine.runner.abilities.deathguard import FlailSwingAbility
            diag = FlailSwingAbility().execute_behaviour(st, int(cid), int(tid)) or {}
        else:
            from engine.runner.runner import Runner
            from engine.runner.messages import ActiveAbilityMessage
            runner = Runner(st).install_default_handlers(20)
            runner.apply(ActiveAbilityMessage(int(cid), int(tid), FLAIL))
            diag = getattr(runner.ability_handler, "last", None) or {}
    finally:
        del AttackDamageOperation._run_hits
        if haze_orig is not None:
            from engine.runner.operations.triggers.loki.haze_of_corruption import (
                HazeOfCorruptionTargetFinderAbility as _H)
            _H.matches = haze_orig

    atk = (diag.get("attack") or {})
    ce = st.get_entity(int(cid))
    sc = ce.get_component(StatsComponent) if ce is not None else None
    te = st.get_entity(int(tid))
    ts = te.get_component(StatsComponent) if te is not None else None
    from engine.runner.damage_model import defender_fixed_armor
    return {"mode": mode, "skip": int(skip), "hp0": hp0,
            "per_hit": list(atk.get("per_hit") or []),
            "total": int(big_hp) - int(hc.hp),
            "n_genrand": cnt[0], "rolls": rolls,
            "cell": cell.get("weapon"), "cells": cell.get("all"),
            "hits": atk.get("hits"), "pierce": atk.get("pierce"),
            "profile": atk.get("profile"),
            "attack_stat": int(sc.ctx.stat(StatType.ATTACK)) if sc is not None else None,
            "tgt_fixed_armor": int(ts.ctx.stat(StatType.FIXED_ARMOR)) if ts is not None else None,
            "defender_armor": defender_fixed_armor(st, int(tid)),
            "ported": diag.get("ported"), "invalid_target": diag.get("invalid_target"),
            "actor_dead": diag.get("actor_dead")}


def _raw_stream(cap, n=10):
    from engine.runner.prng import IntBasedMersenneTwister
    m = IntBasedMersenneTwister()
    m.mt = list(cap["rng"]["mt"])
    m.mti = cap["rng"]["mti"]
    return [m.genrand_int32() for _ in range(n)]


# --------------------------------------------------------------------------- run


def _run(rpc, seed, regime, center, args):
    a_units = [VICTIM, APO] + ([EXTRA] if regime == "k2" else [])
    rid, sf = _build(seed, [CARRIER, FILLER], a_units, args.hp, rank=args.rank)
    if rid is None:
        return None
    try:
        board, ids, bg = _geometry(rpc, rid, center, regime)
        dv = _view(rpc, rid)
        vic = next(u for u in dv["units"] if int(u["id"]) == int(ids[VICTIM]))
        if int(vic.get("hp") or 0) != int(args.hp):
            raise RuntimeError("SETUP POLLUE : victime a %s PV au lieu de %s"
                               % (vic.get("hp"), args.hp))
        cap = _capture(rpc, rid, bg)
        cid, tid = ids[CARRIER], ids[VICTIM]
        res, rows, bonds = _live_cast(rpc, rid, cid, tid)
        rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
        n_native = _genrand_steps(cap["rng"], rng1)
        live_rows = [td for td in rows if td.get("Target_Id") == tid]
        live = [int(td["Amount"]) for td in live_rows]
        dirty = [k for k in ("Attack_DidCrit", "Attack_DidBlock", "Attack_DidEvade")
                 if any(td.get(k) for td in live_rows)]
        dv2 = _view(rpc, rid)
        vic2 = next(u for u in dv2["units"] if int(u["id"]) == int(tid))
        live_total = int(vic["hp"]) - int(vic2.get("hp") or 0)
        out = {"seed": seed, "regime": regime, "rid": rid, "cid": cid, "tid": tid,
               "n_native": n_native, "live": live, "live_total": live_total,
               "bonds": bonds, "dirty": dirty,
               "targets": sorted({td.get("Target_Id") for td in rows}),
               "raw": _raw_stream(cap, 10), "replays": {}}
        for mode in ("direct", "pipeline", "pipeline_nohaze"):
            out["replays"][mode] = _replay(cap, board, cid, tid, mode)
        # ETAGE DECALAGE : la CELLULE du port est-elle juste, a un decalage de flux pres ?
        out["shift"] = []
        for k in range(0, args.max_shift + 1):
            r = _replay(cap, board, cid, tid, "direct", skip=k)
            out["shift"].append({"k": k, "per_hit": r["per_hit"], "total": r["total"]})
        return out
    except RuntimeError as exc:
        print("[277] seed %s regime %s : %s" % (seed, regime, exc))
        return None
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


def _report(row):
    print("[277] seed %s regime %s : genrand natif=%s bonds(1076)=%d cibles touchees=%s%s"
          % (row["seed"], row["regime"], row["n_native"], row["bonds"], row["targets"],
             (" COUP SALE %s" % row["dirty"]) if row["dirty"] else ""))
    print("   LIVE per-coup   = %s  (somme %d, hp delta %d)"
          % (row["live"], sum(row["live"]), row["live_total"]))
    for mode, r in row["replays"].items():
        print("   %-16s= %s  (somme %d, total hp %d) genrand=%d cellule=%s hits=%s "
              "pierce=%s attack=%s armure=%s"
              % (mode, r["per_hit"], sum(r["per_hit"]), r["total"], r["n_genrand"],
                 r["cell"], r["hits"], r["pierce"], r["attack_stat"], r["defender_armor"]))
        if r.get("invalid_target") or r.get("actor_dead"):
            print("     ^ REFUS du port : invalid_target=%s actor_dead=%s"
                  % (r.get("invalid_target"), r.get("actor_dead")))
    print("   NextInternal direct = %s" % ([(x["lo"], x["hi"], x["out"], x["n"])
                                            for x in row["replays"]["direct"]["rolls"]],))
    print("   NextInternal pipe   = %s" % ([(x["lo"], x["hi"], x["out"], x["n"])
                                            for x in row["replays"]["pipeline"]["rolls"]],))
    print("   genrand bruts       = %s" % (row["raw"],))
    hits = [s for s in row["shift"] if s["per_hit"] == row["live"]]
    for s in row["shift"]:
        print("   decalage k=%d       -> %s%s"
              % (s["k"], s["per_hit"], "   <== REPRODUIT LE LIVE" if s in hits else ""))
    if hits:
        print("   VERDICT etage : la CELLULE du port est JUSTE ; l'ecart est un DECALAGE de %d "
              "tirage(s) en AMONT des coups." % hits[0]["k"])
    else:
        print("   VERDICT etage : AUCUN decalage 0..%d ne reproduit le live -> l'ecart n'est PAS "
              "un decalage de flux (chercher la CELLULE)." % row["shift"][-1]["k"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="17831")
    ap.add_argument("--regimes", default="k1,k0,k2")
    ap.add_argument("--center", default="3,4")
    ap.add_argument("--hp", type=int, default=200000)
    ap.add_argument("--rank", type=int, default=17)
    ap.add_argument("--max-shift", dest="max_shift", type=int, default=4)
    args = ap.parse_args()
    center = tuple(int(x) for x in args.center.split(","))
    rpc = _mkrpc()
    rows = []
    for seed in [s for s in args.seeds.split(",") if s.strip()]:
        for regime in [r for r in args.regimes.split(",") if r.strip()]:
            row = _run(rpc, seed, regime, center, args)
            if row is None:
                continue
            rows.append(row)
            _report(row)
            print()
    if not rows:
        print("[277] aucun montage exploitable")
        return 1
    print("[277] BILAN %d montages" % len(rows))
    for r in rows:
        agree_direct = r["live"] == r["replays"]["direct"]["per_hit"]
        agree_pipe = r["live"] == r["replays"]["pipeline"]["per_hit"]
        agree_nohaze = r["live"] == r["replays"]["pipeline_nohaze"]["per_hit"]
        print("   seed %-7s %-3s natif=%-3s direct=%-3s pipeline=%-3s | live==direct %s "
              "live==pipeline %s live==nohaze %s"
              % (r["seed"], r["regime"], r["n_native"], r["replays"]["direct"]["n_genrand"],
                 r["replays"]["pipeline"]["n_genrand"], agree_direct, agree_pipe, agree_nohaze))
    return 0


if __name__ == "__main__":
    sys.exit(main())
