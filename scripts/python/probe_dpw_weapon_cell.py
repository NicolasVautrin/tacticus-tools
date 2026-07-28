"""case-dpw -- BORNES DE LA CELLULE D'ARME de `deathPutrifier` en MELEE.

QUESTION (binaire) : quelles sont les BORNES que le natif utilise pour l'attaque d'ARME melee de
`deathPutrifier`, et d'ou vient l'ecart avec celles du port ?

Le residu a ete releve par R6-c (docs/rl/case-r6c-amount-group-bounds.md §4) : sur le montage
`foul` (le porteur caste `FoulInfusion` 1038 puis attaque en melee), le GROUPE de coups
additionnels est bit-exact mais le COUP D'ARME diverge, et l'ecart CHANGE DE SIGNE (offline < live
sur 3 seeds, offline > live sur le seed 88) -- signature d'une divergence de BORNES, pas d'un
facteur ni d'un flat.

METHODE (decomposition par etage, aucun scalaire fitte) :

  1. On rejoue la MEME attaque OFFLINE sur le MEME flux RNG et on INSTRUMENTE le tirage :
     `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal(lo, hi)` -> on enregistre
     `(lo, hi, r)` avec `r = genrand_int32() >> 1` (la valeur ACCEPTEE). Le coup d'arme vaut
     `lo + (r % (hi - lo))`.
  2. La cellule d'arme du port est `_reduced_bounds(GetStat(Attack))` de
     `IdunBattle.Operations.AttackDamageOperation$$Execute` (mirror `damage_ops/normal.py`) :
         base -> `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64` (spread +-20 %)
              -> `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing`
              -> %-mods -> materialisation `FixMath.NET.Fix64$$Round(., AwayFromZero)`.
  3. `r` etant CONNU et IDENTIQUE des deux cotes (le flux est aligne : natif 3 tirages = port 3),
     on RESOUT la cellule native : on balaie la base candidate `B` et on retient celles qui
     reproduisent les 4 valeurs live A L'UNITE. Une base qui matche 4/4 sur 4 flux differents
     N'EST PAS un fit de scalaire -- le modulo change de residu a chaque flux.

Le probe imprime aussi, pour NOMMER la source de l'ecart : `combatSnapshot` (GetStat resolu) et
`statModSources` (les `ValueModification` PAR SOURCE) sur l'attaquant.

Discipline runner : state-file ABSOLU sous logs/, `--board` explicite, dispose en fin.
ASCII only (cp1252).

CLI (depuis scripts/python) :
  python probe_dpw_weapon_cell.py --seeds 777,12345,314159,88
  python probe_dpw_weapon_cell.py --seeds 777,12345,314159,88 --solve
"""
from __future__ import annotations

import argparse
import json
import sys

from probe_r6_round_materialize import _build, _mkrpc                      # noqa: F401
from probe_159_ah_bounds import _board, _genrand_steps, _pos, _unit        # noqa: F401
from probe_r6c_ah_bounds import _drive_foul_melee, MALADIES_CARRIER        # noqa: F401


# --------------------------------------------------------------------------- offline instrumente


def _replay_recording(dv, ob, snap, board, rng0, cid, tid, moved):
    """Rejoue l'attaque OFFLINE sur le MEME flux et rend :
        {rolls: [(lo, hi, r, out)], cell: (min, max), attack: GetStat(Attack),
         pierce, armor, per_hit, n_genrand}
    `rolls` = TOUS les `NextInternal` du replay dans l'ordre ; `cell` = les bornes que
    `AttackDamageOperation._run_hits` a recues pour les coups d'ARME (branche non-crit)."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import set_moved_flag, StatsComponent
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.entities.stats import StatType

    st = load_state(dv, ob, snap, board=board)
    if moved:
        set_moved_flag(st, cid)
    rolls = []
    cnt = [0]

    class _Recording(IntBasedMersenneTwister):
        __slots__ = ()

        def genrand_int32(self):
            cnt[0] += 1
            return IntBasedMersenneTwister.genrand_int32(self)

        def next_internal(self, lo, hi):
            base = cnt[0]
            out = IntBasedMersenneTwister.next_internal(self, lo, hi)
            # `r` accepte = out - lo (modulo range) ; on le recalcule proprement en rejouant la
            # derniere valeur brute consommee, mais l'invariant `out = lo + (r % range)` suffit :
            # on stocke le RESIDU, qui est l'information portable d'une cellule a l'autre... sauf
            # qu'il ne l'est PAS (le residu depend du range). On garde donc `r` LUI-MEME.
            rolls.append({"lo": lo, "hi": hi, "out": out, "n": cnt[0] - base})
            return out

    rng = _Recording()
    rng.mt = list(rng0["mt"])
    rng.mti = rng0["mti"]
    st.rng = rng
    cell = {}
    # ETAGE REDUCTION : on capture les ARGUMENTS REELS de `_reduced_bounds` (valeur pre-percage,
    # pierce, armure, mods) -- le champ `armor` du dict d'attaque n'est PAS fiable (il peut avoir
    # ete ecrase par une sous-attaque de la cascade after-hit).
    from engine.runner.operations.damage_ops import normal as _dn
    _orig_app = _dn.apply_pierce_and_modifiers
    red_args = []

    def _spy_red(value, pierce_pct=100, armor=0, mods=None, hit_mult=1,
                 attacker_additive_pre=False):
        if len(red_args) < 4:
            red_args.append({"value": value, "pierce": pierce_pct, "armor": armor,
                             "pct_list": list(getattr(mods, "pct_list", ()) or ()),
                             "additive": getattr(mods, "additive", 0),
                             "extra_pierce": getattr(mods, "extra_pierce", 0),
                             "armor_pen": getattr(mods, "armor_penetration", 0),
                             "ignore_armor": getattr(mods, "ignore_armor", False),
                             "hit_mult": hit_mult})
        return _orig_app(value, pierce_pct, armor, mods, hit_mult=hit_mult,
                         attacker_additive_pre=attacker_additive_pre)

    _dn.apply_pierce_and_modifiers = _spy_red
    orig = AttackDamageOperation._run_hits      # resolu par MRO (mixin) -> fonction nue

    def _spy(rngo, hit_nc, hit_cr, *a, **kw):
        cell.setdefault("all", []).append(((hit_nc.min, hit_nc.max), (hit_cr.min, hit_cr.max),
                                           kw.get("post_roll") is not None))
        if "weapon" not in cell:
            cell["weapon"] = (hit_nc.min, hit_nc.max)
            cell["weapon_crit"] = (hit_cr.min, hit_cr.max)
        return orig(rngo, hit_nc, hit_cr, *a, **kw)

    AttackDamageOperation._run_hits = staticmethod(_spy)
    try:
        runner = Runner(st).install_default_handlers(20)
        runner.apply(AttackUnitMessage(cid, tid))
        last = getattr(getattr(runner, "damage_handler", None), "last", None)
    finally:
        del AttackDamageOperation._run_hits
        _dn.apply_pierce_and_modifiers = _orig_app
    last = last if isinstance(last, dict) else {}
    e = st.get_entity(cid)
    sc = e.get_component(StatsComponent) if e is not None else None
    # ETAGE ARMURE du DEFENSEUR, decompose : ce que le snapshot porte, ce que l'ECS rend apres
    # rechargement, et ce que le foyer `defender_fixed_armor` rend au moment de l'attaque.
    from engine.runner.damage_model import defender_fixed_armor
    from engine.runner.components import PositionComponent, UnitComponent
    ents = []
    for uid, ent in st.entities.items():
        _p = ent.get_component(PositionComponent)
        _u = ent.get_component(UnitComponent)
        _s = ent.get_component(StatsComponent)
        ents.append({"id": uid, "vis": getattr(_u, "visual_id", None),
                     "alive": getattr(_u, "alive", None),
                     "pos": (_p.col, _p.row) if _p is not None else None,
                     "fixed_armor": int(_s.ctx.stat(StatType.FIXED_ARMOR)) if _s is not None else None,
                     "attack": int(_s.ctx.stat(StatType.ATTACK)) if _s is not None else None})
    te = st.get_entity(tid)
    tsc = te.get_component(StatsComponent) if te is not None else None
    tgt_arm = {"ctx_fixed_armor": int(tsc.ctx.stat(StatType.FIXED_ARMOR)) if tsc is not None else None,
               "defender_fixed_armor": defender_fixed_armor(st, tid),
               "effects": [(getattr(x, "effect_type", None), getattr(x, "name", None))
                           for x in (st.effects.by_unit.get(int(tid)) or [])]
               if st.effects is not None else []}
    return {"rolls": rolls, "cell": cell.get("weapon"), "cell_crit": cell.get("weapon_crit"),
            "cells": cell.get("all"), "tgt_arm": tgt_arm, "red_args": red_args,
            "target": last.get("target"), "entities": ents, "tid": int(tid),
            "attack": int(sc.ctx.stat(StatType.ATTACK)) if sc is not None else None,
            "pierce": last.get("pierce"), "armor": last.get("armor"),
            "per_hit": list(last.get("per_hit") or []),
            "profile": last.get("profile"), "hits": last.get("hits"),
            "n_genrand": cnt[0]}


def _raw_stream(rng0, n=8):
    """Les n premieres valeurs BRUTES `genrand_int32` du flux (independant de toute cellule) --
    c'est `r = g >> 1` qui sert a re-resoudre une cellule ALTERNATIVE."""
    from engine.runner.prng import IntBasedMersenneTwister
    m = IntBasedMersenneTwister()
    m.mt = list(rng0["mt"])
    m.mti = rng0["mti"]
    return [m.genrand_int32() for _ in range(n)]


# --------------------------------------------------------------------------- modele de cellule


def cell_for_base(base, pierce, armor, spread_pct=20, extra_max=0):
    """Cellule d'ARME (bornes REDUITES) pour une base d'attaque donnee -- MEME chaine que
    `damage_ops/normal.py::_reduced_bounds`, sans aucun modificateur (le montage n'en a aucun :
    le groupe additionnel du meme coup vaut exactement `Round(v x pierce/100)`)."""
    from engine.services.damage_prediction import get_base_damage_fix64
    from engine.services.static_battle_rules import get_damage_with_piercing
    from engine.services import fix64 as _fx
    mm = get_base_damage_fix64(int(base), extra_max=int(extra_max), spread_pct=spread_pct)

    def _red(v):
        return _fx.to_int(_fx.round_raw(_fx.from_number(get_damage_with_piercing(v, pierce, armor)), 1))
    return int(_red(mm.min)), int(_red(mm.max))


def resolve(lo, hi, g):
    """`NextInternal(lo, hi + 1)` sur la valeur brute `g` (1 tirage ; le rejet Java est ignore --
    il ne mord qu'a moins de 1 / 2^21 pres des bornes, et il serait VISIBLE comme un
    `n_genrand` > 1 dans les `rolls` enregistres)."""
    rng = hi + 1 - lo
    if rng <= 0:
        return lo
    if (-rng & rng) == rng:
        return ((rng * (g >> 1)) >> 31) + lo
    return lo + ((g >> 1) % rng)


# --------------------------------------------------------------------------- run


def _run_seed(rpc, seed, args):
    rid, sf = _build(seed, MALADIES_CARRIER, args.target,
                     extra=["--crit", "0,0", "--block-target", "0,0",
                            "--hp-target", str(args.hp), "--armor-target", str(args.armor)],
                     rank=args.rank)
    if rid is None:
        return None
    try:
        cid, tid, aid, moved, err = _drive_foul_melee(rpc, rid, MALADIES_CARRIER, args.target,
                                                      max_turns=args.max_turns)
        if cid is None:
            print("[dpw] seed %s: drive KO -- %s" % (seed, err))
            return None
        board = _board(rpc, rid)
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        sms = rpc("statModSources", {"runnerId": rid}, 90)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": aid},
            "captureEvents": True}, 120)
        rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
        n_native = _genrand_steps(rng0, rng1)
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)

        def _roster(_dv, _snap):
            """(id, visualId, position, FixedArmor, effets) AVANT/APRES -- c'est l'etage qui compte :
            le re-routage `SwornProtector` (#120bis) DEPLACE des unites PENDANT l'attaque, donc
            l'armure du defenseur REEL peut changer entre le snapshot et la resolution."""
            arm = {u.get("entityId"): (u.get("stats") or {}).get("fixedArmor")
                   for u in (_snap.get("units") or [])}
            out = []
            for u in (_dv.get("units") or []):
                p = u.get("pos") or {}
                out.append({"id": u.get("id"), "vis": u.get("visualId"),
                            "pos": [p.get("col"), p.get("row")],
                            "alive": u.get("alive"),
                            "fixedArmor": arm.get(u.get("id")),
                            "eff": [e.get("effectType") for e in (u.get("effects") or ())]})
            return out
        roster_before, roster_after = _roster(dv, snap), _roster(dv2, snap2)
        rows = []
        for act in (res.get("actions") or []):
            for ev in (act.get("events") or []):
                td = ev.get("tags")
                td = json.loads(td) if isinstance(td, str) else (td or {})
                if "Amount" in td:
                    rows.append(td)
        if len({td.get("Target_Id") for td in rows}) != 1:
            print("[dpw] seed %s: montage AMBIGU (plusieurs cibles) -- ignore" % seed)
            return None
        if any(td.get("Attack_DidCrit") or td.get("Attack_DidBlock") or td.get("Attack_DidEvade")
               for td in rows):
            print("[dpw] seed %s: coup SALE (crit/block/evade) -- ignore" % seed)
            return None
        live = [int(td["Amount"]) for td in rows]
        off = _replay_recording(dv, ob, snap, board, rng0, cid, tid, moved)
        cst_snap = next((u for u in (snap.get("units") or []) if u.get("entityId") == cid), None)
        cst_sms = next((u for u in (sms.get("units") or []) if u.get("entityId") == cid
                        or u.get("unitId") == cid), None)
        tgt_snap = next((u for u in (snap.get("units") or []) if u.get("entityId") == tid), None)
        tgt_sms = next((u for u in (sms.get("units") or []) if u.get("entityId") == tid
                        or u.get("unitId") == tid), None)
        return {"seed": seed, "live": live, "off": off, "moved": moved, "n_native": n_native,
                "roster_before": roster_before, "roster_after": roster_after,
                "raw": _raw_stream(rng0, 6),
                "cst_full": cst_snap, "tgt_full": tgt_snap,
                "cst_stats": (cst_snap or {}).get("stats"),
                "cst_cfg": (cst_snap or {}).get("unitConfig"),
                "cst_sms": cst_sms, "tgt_sms": tgt_sms,
                "tgt_stats": (tgt_snap or {}).get("stats")}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="777,12345,314159,88")
    ap.add_argument("--target", default="astraCreed")
    ap.add_argument("--rank", type=int, default=None)
    ap.add_argument("--hp", type=int, default=90000)
    ap.add_argument("--armor", type=int, default=6000)
    ap.add_argument("--max-turns", dest="max_turns", type=int, default=30)
    ap.add_argument("--solve", action="store_true",
                    help="balaye la base d'attaque candidate et retient celles qui rendent les "
                         "valeurs live A L'UNITE sur TOUS les seeds")
    ap.add_argument("--span", type=int, default=4000, help="demi-largeur du balayage --solve")
    ap.add_argument("--dump-stats", action="store_true")
    args = ap.parse_args()
    rpc = _mkrpc()
    rows = []
    for seed in [s for s in args.seeds.split(",") if s.strip()]:
        row = _run_seed(rpc, seed, args)
        if row is None:
            continue
        rows.append(row)
        off = row["off"]
        print("[dpw] seed %s moved=%d genrand natif=%s offline=%s"
              % (seed, row["moved"], row["n_native"], off["n_genrand"]))
        print("   live            = %s" % (row["live"],))
        print("   arme offline    = %s (hits=%s profil=%s pierce=%s armure=%s)"
              % (off["per_hit"], off["hits"], off["profile"], off["pierce"], off["armor"]))
        print("   ATTACK offline  = %s   -> cellule ARME port = %s (crit %s)"
              % (off["attack"], off["cell"], off["cell_crit"]))
        print("   cellules        = %s" % (off["cells"],))
        print("   armure cible    = %s" % json.dumps(off["tgt_arm"]))
        print("   args reduction  = %s" % json.dumps(off["red_args"]))
        print("   cible attaquee  = %s (msg tid = %s)" % (off["target"], off["tid"]))
        print("   entites ECS     = %s" % json.dumps(off["entities"]))
        print("   roster AVANT    = %s" % json.dumps(row["roster_before"]))
        print("   roster APRES    = %s" % json.dumps(row["roster_after"]))
        if args.dump_stats:
            print("   snapshot att.   = %s" % json.dumps(row["cst_full"])[:1600])
            print("   snapshot cible  = %s" % json.dumps(row["tgt_full"])[:1600])
        print("   NextInternal    = %s" % (off["rolls"],))
        print("   genrand bruts   = %s" % (row["raw"],))
        if args.dump_stats:
            print("   statMod att.    = %s" % json.dumps(row["cst_sms"])[:900])
    if not rows:
        print("[dpw] aucun montage exploitable")
        return 1
    print()
    print("[dpw] BILAN %d montages : ARME alignee %d/%d"
          % (len(rows), sum(1 for r in rows if r["live"][:1] == r["off"]["per_hit"][:1]), len(rows)))
    if args.solve:
        _solve(rows, args)
    return 0


def solve_cell(cases, lo_range, w_max):
    """RESOLUTION DIRECTE de la cellule NATIVE, SANS aucun modele : on cherche `(LO, W)` tel que
    `LO + (r % W) == live` pour TOUS les flux. `r = g >> 1` est le tirage brut, IDENTIQUE des deux
    cotes (le flux est aligne). Avec 4 flux la solution est unique en pratique -- et une solution
    qui tient sur 4 residus differents n'est PAS un scalaire fitte."""
    out = []
    for lo in lo_range:
        for w in range(2, w_max):
            if all(lo + (g >> 1) % w == live for _s, g, live in cases):
                out.append((lo, lo + w - 1, w))
    return out


def _solve(rows, args):
    """Deux etages, dans l'ordre :
       1. RESOUDRE la cellule NATIVE depuis les valeurs live + les flux (aucun modele) ;
       2. la CONFRONTER a la chaine du port en balayant les seuls termes qui peuvent la produire
          -- l'ARMURE du defenseur (le `max(0, d - armure, d x pierce%)` est une brisure de pente :
          elle deplace le HAUT sans toucher le BAS) et `ExtraMaxDamage` (`GetBaseDamageFix64` :
          `max += FromInt(param_5)`, `min` intact) -- puis dire lequel colle."""
    ref = rows[0]["off"]
    pierce = int(ref["pierce"] or 0)
    # ARMURE EFFECTIVE de la reduction = le foyer `defender_fixed_armor` (le champ `armor` du dict
    # d'attaque peut avoir ete ecrase par une sous-attaque de la cascade after-hit).
    armor = int(ref["tgt_arm"]["defender_fixed_armor"] or 0)
    base0 = int(ref["attack"] or 0)
    cases = [(r["seed"], r["raw"][0], int(r["live"][0])) for r in rows if r["off"]["rolls"]]
    print("[dpw] solve : pierce=%d armure_port=%d base_port=%d cellule_port=%s"
          % (pierce, armor, base0, ref["cell"]))
    lo0, hi0 = ref["cell"]
    sols = solve_cell(cases, range(max(1, lo0 - args.span), lo0 + args.span + 1), args.span * 2)
    if not sols:
        print("[dpw] solve : AUCUNE cellule (LO,W) ne reproduit les %d flux -- ce n'est PAS une "
              "cellule d'arme unique (chercher un autre etage)" % len(cases))
        return
    print("[dpw] solve : %d cellule(s) NATIVE(S) sur %d flux" % (len(sols), len(cases)))
    for lo, hi, w in sols:
        print("   cellule NATIVE = [%d, %d] (largeur %d)  vs port [%d, %d] (largeur %d)"
              % (lo, hi, w, lo0, hi0, hi0 - lo0 + 1))
        # (a) meme base, ARMURE differente
        cand_a = [a for a in range(0, 60001) if cell_for_base(base0, pierce, a) == (lo, hi)]
        # (b) meme armure, ExtraMaxDamage different (n'agit QUE sur le haut)
        cand_b = [x for x in range(0, 20001)
                  if cell_for_base(base0, pierce, armor, extra_max=x) == (lo, hi)]
        print("     -> armure NATIVE candidate    : %s" % (cand_a[:6] or "aucune"))
        print("     -> extraMaxDamage candidat    : %s" % (cand_b[:6] or "aucun"))
    for s, g, live in cases:
        print("   seed %-7s g=%-12d live=%-6d" % (s, g, live))


if __name__ == "__main__":
    sys.exit(main())
