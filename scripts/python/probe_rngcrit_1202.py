#!/usr/bin/env python
"""Probe fable-solver — desync RNG des attaques d'ABILITY multi-coups a cc=0 (cas #220 VigilanceEternal).

CONTEXTE (verdicts contradictoires a reconcilier) :
  - damage.py:463 : "roll_critical ne tire QUE si cc>=1 -- cc=0 => 0 tirage, valide 18/18" (attaque NORMALE).
  - #220 (VigilanceEternal 1202) : le natif tire 6 rng pour 3 coups a cc=0 (attaque d'ABILITY) --
    attribue a "1 crit-roll NextBool PAR COUP" -> contredit la note.

RE DECOMPILE (verite, gqfc5mff6c) :
  - Le crit-roll UNIQUE du per-coup partage = IDamagePrediction slot 0xa -> IdunBattle.Core.Services.DamagePrediction$$RollCritical : gate `cc<1 -> return false SANS tirage`. (IdunBattle.Core.Services.DamageCalculations$$RollCritical =
    NextBool brut, atteint SEULEMENT via ce gate.) => l'hypothese "crit-roll a cc=0" est REFUTEE au decompile.
  - IdunBattle.Operations.AttackDamageOperation$$ExecuteHit (per-coup PARTAGE normal + AttackWithAttackDamage) consomme :
      1. IdunBattle.Core.HitDamage$$GetDamage sur le struct d'entree — GATE `min==max -> 0 tirage` ;
      2. RollCritical (0 tirage si cc<1) ;
      3. block/evade dans IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation (0 si aucune source) ;
      4. IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage (slot 8) — TOUJOURS 1 tirage (AUCUN gate min==max).
    => attaque NORMALE (struct degenere (Attack,Attack)) : 1 tirage/coup (le resolve) ;
       ability AttackWithAttackDamage (struct = bornes brutes minDmg/maxDmg) : 2 tirages/coup
       (GetDamage brut GASPILLE + resolve). Le "crit-roll fantome" #220 = le GetDamage brut.

CE PROBE (live = confirmation) — A/B sur le MEME attaquant/cible (Tyrith custoKyrus 3-hit Power cc=0
vs necroWarden), N seeds :
  A. attaque NORMALE live : mti-delta attendu 3 (1/coup) + total == port (reduce-then-roll) ;
  B. cast 1202 live : mti-delta attendu 6 (2/coup) + total confronte a 4 modeles :
       P0 = port courant  : tirage brut PAIRS g0,g1,g2, valeur=reduce(brut)      (3 tirages)
       M1 = reduce-then-roll IMPAIRS : valeur=next_internal(lo_red,hi_red+1) aux g1,g3,g5 (6 tirages)
       M2 = roll-then-reduce IMPAIRS : valeur=reduce(next_internal(bmin,bmax+1)) aux g1,g3,g5 (6 tirages)
       M3 = valeurs du port aux PAIRS + resolve gaspille IMPAIRS                  (6 tirages)
     Le modele dont le TOTAL == delta HP live sur TOUS les seeds gagne.

ASCII only (cp1252). Usage: python probe_rngcrit_1202.py [--seeds 31101,31102,31103]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
import stream_events as SE  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
ATK_VIS = "custoKyrus"          # Tyrith : 3 hits melee Power, cc=0
TGT_VIS = "necroWarden"         # cible #220 : mono-membre, 0 block/evade/shield
ABILITY = 1202                  # VigilanceEternal
BUILD_UNITS = ["--p-units", ATK_VIS, "--a-units", f"{TGT_VIS},necroDestroyer",
               "--hp-target", "300000", "--hp-player", "300000"]


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def build(seed: int, tag: str, a_units: str = f"{TGT_VIS},necroDestroyer",
          hp_override: bool = True, extra: list | None = None) -> int:
    state = ROOT / "logs" / "runners" / f"rngcrit-a35d06-{tag}.json"
    state.unlink(missing_ok=True)
    units = ["--p-units", ATK_VIS, "--a-units", a_units]
    if hp_override:
        # NB : ces overrides ZERONT l'armure (FixedArmor=0 constate live) -> reduce identite.
        units += ["--hp-target", "300000", "--hp-player", "300000"]
    units += list(extra or [])
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state), "--board", "MC1_67"] + units,
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print(f"[rngcrit] build {tag} KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        return -1
    return json.loads(state.read_text())["runnerId"]


def dispose(rpc, rid):
    """`rpc` = la closure (method, body, t) — dispose MON runner, jamais ceux des autres."""
    try:
        rpc("disposeRunner", {"runnerId": rid}, 60)
    except Exception:
        pass


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _hp_ob(ob, uid):
    for u in (ob.get("units") or []):
        if u.get("squadId") == uid and not u.get("isDead"):
            return u.get("hp")
    return None


def _advance_to_my_turn(rpc, rid, vis, max_iter=12):
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if not _ok(dec):
            return None, None
        u = _find(dec, vis)
        if u is None:
            return dec, None
        if dec.get("currentPlayer") == u.get("owner"):
            return dec, u
        rpc("aiPlayTurn", {"runnerId": rid}, 240)
        dec2 = rpc("decisionView", {"runnerId": rid}, 150)
        if _ok(dec2) and dec2.get("currentPlayer") != (u or {}).get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def _drive_adjacent(rpc, rid, max_turns=10, tgt_vis=TGT_VIS):
    """DRIVE Tyrith a dist 1 de la cible `tgt_vis` (doctrine drive-positions). Renvoie (dec, me, tgt)."""
    for _ in range(max_turns):
        dec, me = _advance_to_my_turn(rpc, rid, ATK_VIS)
        if me is None:
            return None, None, None
        tgt = _find(dec, tgt_vis)
        if tgt is None:
            return None, None, None
        d = hexgeo.distance(_pos(me), _pos(tgt))
        if d == 1:
            return dec, me, tgt
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == me["id"]), None)
        tiles = [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])
                 if t.get("col") is not None]
        if tiles:
            tp = _pos(tgt)
            best = min(tiles, key=lambda p: (0 if hexgeo.distance(p, tp) == 1 else 1,
                                             hexgeo.distance(p, tp)))
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
            dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            me2 = _find(dec2, ATK_VIS)
            tgt2 = _find(dec2, tgt_vis)
            if me2 is not None and tgt2 is not None \
                    and hexgeo.distance(_pos(me2), _pos(tgt2)) == 1:
                return dec2, me2, tgt2
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None, None


def _capture(rpc, rid):
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s = rpc("dumpRng", {"runnerId": rid}, 30)
    return dec, ob, snap, s


def _offline_state(dec, ob, snap, s, board):
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    state = load_state(dec, ob, snap)
    state.board = board
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    state.rng = rng
    return state


def _mk_rng(s):
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _consumed(s0, s1):
    """Nb de tirages genrand consommes entre 2 dumps (mti wrap 624)."""
    if not (_ok(s0) and _ok(s1)):
        return None
    d = s1["mti"] - s0["mti"]
    if d < 0:
        d += 624
    return d


def _ability_reduce_ctx(state, atk_id, tgt_id):
    """Replique le SETUP de execute_ability_attack (memes helpers, memes flags #217/#112) et renvoie
    (bmin, bmax, hits, reduce_fn, diag). Sert aux modeles M1/M2 SANS toucher le port."""
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.abilities.base import ability_attack_params
    from engine.runner.damage_model import (attacker_modifiers, defender_modifiers,
                                            defender_fixed_armor)
    from engine.runner.components import StatsComponent, HealthComponent
    from engine.services.damage_prediction import apply_pierce_and_modifiers
    from engine.services.damage_modifiers import apply_all_modifiers
    from engine.entities.traits import target_hit_multiplier

    att = state.get_entity(atk_id)
    tgt = state.get_entity(tgt_id)
    sc = att.get_component(StatsComponent)
    thc = tgt.get_component(HealthComponent)
    ahc = att.get_component(HealthComponent)
    tsc = tgt.get_component(StatsComponent)
    bmin, bmax, pierce, hits = ability_attack_params(state, atk_id, "VigilanceEternal", "Power")
    mods, active = attacker_modifiers(state, atk_id, ahc.hp if ahc else None,
                                      target_id=tgt_id, is_normal_attack=False)
    armor = defender_fixed_armor(state, tgt_id)
    def_mods, _da = defender_modifiers(state, tgt_id, thc.hp, is_melee=True,
                                       damage_profile="Power", attacker_id=atk_id,
                                       is_normal_attack=False)
    cc, cd, cen = AttackDamageOperation._crit_params(sc.ctx, active)
    AttackDamageOperation._apply_defender_flat_reductions(mods, def_mods)
    hm = target_hit_multiplier(tsc.ctx.trait_objects()) if tsc is not None else 1
    block = AttackDamageOperation._block_sources(tsc, _da, armor)

    def reduce_fn(v):
        return apply_all_modifiers(
            apply_pierce_and_modifiers(v, pierce, armor, mods, hit_mult=hm,
                                       attacker_additive_pre=True), def_mods)

    diag = {"bmin": bmin, "bmax": bmax, "pierce": pierce, "hits": hits, "armor": armor,
            "cc": cc, "cd": cd, "crit_enabled": cen, "block_sources": block,
            "hit_mult": hm, "lo_red": reduce_fn(bmin), "hi_red": reduce_fn(bmax)}
    return bmin, bmax, hits, reduce_fn, diag


def _variant_totals(s_rng, bmin, bmax, hits, reduce_fn):
    """Totaux/per-hit des 4 modeles candidats depuis le MEME etat MT (clones separes)."""
    out = {}
    # P0 : port courant — tirage brut consecutif, valeur = reduce(brut)
    rng = _mk_rng(s_rng)
    ph = [reduce_fn(rng.next_internal(bmin, bmax + 1)) for _ in range(hits)]
    out["P0_port(brut pairs, 3 tirages)"] = (sum(ph), ph)
    # M1 : reduce-then-roll aux IMPAIRS (1 tirage gaspille avant chaque coup)
    rng = _mk_rng(s_rng)
    lo, hi = reduce_fn(bmin), reduce_fn(bmax)
    ph = []
    for _ in range(hits):
        rng.next_internal(bmin, bmax + 1)          # tirage gaspille (GetDamage brut)
        ph.append(rng.next_internal(lo, hi + 1))   # resolve = valeur (bornes REDUITES)
    out["M1_reduce-then-roll impairs (6 tirages)"] = (sum(ph), ph)
    # M2 : roll-then-reduce aux IMPAIRS
    rng = _mk_rng(s_rng)
    ph = []
    for _ in range(hits):
        rng.next_internal(bmin, bmax + 1)                     # gaspille
        ph.append(reduce_fn(rng.next_internal(bmin, bmax + 1)))  # valeur = brut IMPAIR reduit
    out["M2_roll-then-reduce impairs (6 tirages)"] = (sum(ph), ph)
    # M3 : valeurs du port aux PAIRS + resolve degenere gaspille aux IMPAIRS
    rng = _mk_rng(s_rng)
    ph = []
    for _ in range(hits):
        v = reduce_fn(rng.next_internal(bmin, bmax + 1))      # valeur = brut PAIR reduit
        rng.next_internal(v, v + 1)                           # resolve degenere (gaspille)
        ph.append(v)
    out["M3_port-vals + resolve gaspille (6 tirages)"] = (sum(ph), ph)
    return out


def _live_hits_from_events(res, tgt_id, hp0):
    """Per-hit LIVE = deltas des events `UnitDamaged` (RemainingHealth) de la cible — IMMUNE au
    heal de fin de tour (LivingMetalRepair) qui pollue le delta HP observe apres coup."""
    hp_seq = [hp0]
    s_dmg = SE.step_id("UnitDamaged")
    for a in (res.get("actions") or []):
        for ev in (a.get("events") or []):
            if ev.get("kind") == "action" and ev.get("step") == s_dmg \
                    and ev.get("entity") == tgt_id:
                try:
                    tags = json.loads(ev.get("tags") or "{}")
                except Exception:
                    continue
                if "UnitStats_RemainingHealth" in tags:
                    hp_seq.append(tags["UnitStats_RemainingHealth"])
    return [hp_seq[i] - hp_seq[i + 1] for i in range(len(hp_seq) - 1)]


def run_seed(rpc, seed: int, fails: list, tgt_vis: str = TGT_VIS,
             a_units: str | None = None, hp_override: bool = True,
             branches=("B_ability", "A_normal"), build_extra: list | None = None):
    from engine.entities.pathfinding.board import Board

    if a_units is None:
        a_units = f"{TGT_VIS},necroDestroyer"
    print(f"=== seed {seed} (cible {tgt_vis}, hp_override={hp_override}) ===")
    for branch in branches:
        rid = build(seed, f"{branch}-{seed}-{tgt_vis}", a_units=a_units,
                    hp_override=hp_override, extra=build_extra)
        if rid < 0:
            fails.append(f"{seed}:{branch}:build")
            continue
        try:
            bg = rpc("boardGraph", {"runnerId": rid}, 60)
            if not (isinstance(bg, dict) and bg.get("tiles")):
                fails.append(f"{seed}:{branch}:boardGraph")
                continue
            board = Board(bg["tiles"], adjacency="evenq")
            dec, me, tgt = _drive_adjacent(rpc, rid, tgt_vis=tgt_vis)
            if me is None or tgt is None:
                fails.append(f"{seed}:{branch}:drive")
                continue
            dec0, ob0, snap0, s0 = _capture(rpc, rid)
            if not _ok(s0):
                fails.append(f"{seed}:{branch}:dumpRng")
                continue
            hp0 = _hp_ob(ob0, tgt["id"])

            if branch == "B_ability":
                act = {"kind": "ability", "casterId": me["id"], "targetId": tgt["id"],
                       "abilityType": ABILITY}
            else:
                norm = next((ab for ab in (me.get("abilities") or [])
                             if ab.get("kind") == "normal"), None)
                if norm is None:
                    fails.append(f"{seed}:{branch}:no-normal")
                    continue
                act = {"kind": "ability", "casterId": me["id"], "targetId": tgt["id"],
                       "abilityType": norm["id"]}
            res = rpc("applyAction", {"runnerId": rid, "action": act}, 120)
            if not _ok(res):
                fails.append(f"{seed}:{branch}:applyAction:{res.get('error')}")
                continue
            s1 = rpc("dumpRng", {"runnerId": rid}, 30)
            live_hits = _live_hits_from_events(res, tgt["id"], hp0)
            live_total = sum(live_hits) if live_hits else None
            ndraw = _consumed(s0, s1)
            print(f"[{branch}] LIVE: per-hit(events)={live_hits} total={live_total}, "
                  f"tirages consommes = {ndraw}")

            # ---- offline
            state = _offline_state(dec0, ob0, snap0, s0, board)
            atk_id, tgt_id = me["id"], tgt["id"]
            if branch == "B_ability":
                bmin, bmax, hits, reduce_fn, diag = _ability_reduce_ctx(state, atk_id, tgt_id)
                print(f"[{branch}] ctx: bornes brutes [{diag['bmin']},{diag['bmax']}] "
                      f"reduites [{diag['lo_red']},{diag['hi_red']}] pierce={diag['pierce']} "
                      f"armor={diag['armor']} hits={diag['hits']} cc={diag['cc']} cd={diag['cd']} "
                      f"crit_enabled={diag['crit_enabled']} block={diag['block_sources']} "
                      f"hit_mult={diag['hit_mult']}")
                if diag["cc"] != 0 or diag["block_sources"]:
                    print(f"[{branch}] !! setup NON PROPRE (cc/block) -> interpretations prudentes")
                for name, (tot, ph) in _variant_totals(s0, bmin, bmax, hits, reduce_fn).items():
                    mark = "<== MATCH LIVE" if (live_hits and ph == live_hits) else ""
                    print(f"[{branch}]   {name}: total={tot} per-hit={ph} {mark}")
                # PORT REEL (execute_ability_attack via _run_hits) sur un clone -> doit == LIVE post-fix
                st2 = _offline_state(dec0, ob0, snap0, s0, board)
                from engine.runner.operations.damage import AttackDamageOperation as _ADO
                rr = _ADO.execute_ability_attack(st2, atk_id, tgt_id, bmin, bmax,
                                                 diag["pierce"], hits,
                                                 damage_profile="Power", is_melee=True,
                                                 ability_type=ABILITY)
                drawn = st2.rng.mti - s0["mti"] + (624 if st2.rng.mti < s0["mti"] else 0)
                mark = "<== MATCH LIVE" if (rr and live_hits and rr["per_hit"] == live_hits) else "!! MISMATCH"
                print(f"[{branch}]   PORT execute_ability_attack: per-hit={rr['per_hit'] if rr else None} "
                      f"tirages={drawn} {mark}")
                if live_hits and rr and rr["per_hit"] != live_hits:
                    fails.append(f"{seed}:{branch}:PORT per-hit {rr['per_hit']} != live {live_hits}")
            else:
                from engine.runner.operations.damage import AttackDamageOperation
                st2 = _offline_state(dec0, ob0, snap0, s0, board)
                r = AttackDamageOperation.execute(st2, atk_id, tgt_id)
                mark = "<== MATCH LIVE" if (r and live_hits == r["per_hit"]) else "!! MISMATCH"
                print(f"[{branch}]   port execute(): total={r['total'] if r else None} "
                      f"per-hit={r['per_hit'] if r else None} rolls={r['rolls'] if r else None} {mark}")
                if live_hits and r and live_hits != r["per_hit"]:
                    fails.append(f"{seed}:{branch}:port-per-hit {r['per_hit']} != live {live_hits}")
        finally:
            dispose(rpc, rid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="31101,31102,31103")
    args = ap.parse_args()
    sid = _resolve_session()

    def rpc(method, body, t=90):
        return _r(sid, method, body, t)

    fails: list[str] = []
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    for seed in seeds:
        run_seed(rpc, seed, fails)
    # B2 : cible ARMUREE (orksNob, armure GetStat(16) reelle, block 0 verifie #72) -> discrimine
    # le PLACEMENT de la reduction (reduce(brut@pair) vs resolve@impair) que armor=0 masquait.
    run_seed(rpc, seeds[0] + 100, fails, tgt_vis="orksNob", a_units="orksNob,necroDestroyer")
    print("\n=== BILAN ===")
    if fails:
        for f in fails:
            print("FAIL:", f)
    else:
        print("OK (aucun echec de setup ; lire les MATCH LIVE ci-dessus)")


if __name__ == "__main__":
    main()
