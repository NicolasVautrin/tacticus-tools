"""R6-b -- ORDRE tirage/reduction du canal COUPS ADDITIONNELS HETEROGENES (#179/#202-B).

QUESTION (binaire) : pour un groupe `predefined`, le natif TIRE-T-IL AVANT de reduire
(roll-then-reduce, 2 tirages/coup) ou APRES (reduce-then-roll, 1 tirage/coup) ?

RE (decompile = verite, gqfc5mff6c) -- `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`,
ou retombent les DEUX voies natives de coups additionnels :

  1. `IdunBattle.Core.HitDamage$$GetDamage(attackData.HitDamage, rng, useAverage)` -- lu verbatim :
         if (min == max) return min ;                 # AUCUN tirage
         if (useAverage)  return (min + max) / 2 ;    # AUCUN tirage
         return rng.Range(min, max + 1) ;             # 1 tirage
  2. le crit -> `IdunBattle.Core.Services.CritDamageInfo`, dont le champ 0 EST ce degat ;
  3. slot 4 `IdunBattle.Core.Services.DamagePrediction$$PredictAttack` -- le `Nullable<int>` damage
     de sa struct d'entree est `CritDamageInfo.Damage` -> la reduction porte sur le degat TIRE ;
  4. slot 8 `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` -- lu
     verbatim : `rng.Range(pred.min, pred.max + 1)`, **SANS aucun gate min == max** (contraste
     EXACT avec `HitDamage$$GetDamage`, qui en a un) -> 1 tirage GASPILLE.

et `IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsData` bat l'AttackData de
CHAQUE groupe par `IdunBattle.Core.HitDamage$$.ctor(min = descripteur.minDmg,
max = Nullable(descripteur.maxDmg))` : un groupe PREDEFINED y arrive NON DEGENERE.
=> ROLL-THEN-REDUCE, 2 tirages/coup.

DEUX CAS DISCRIMINANTS, sur DEUX AXES DIFFERENTS (aucun ne suffit seul) :

  * `--case squig` (axe LARGEUR DU MODULO) -- `orksRuntherd`, passif `SquigHound` : 2 coups
    PREDEFINED [minDmg,maxDmg] profil `Physical` PiercingRatio **1**, cible forcee a
    `--armor-target 6000` => la reduction est une MULTIPLICATION (`d x fix(1/100)`), donc la
    largeur BRUTE (1329 cellules) et la largeur REDUITE (14) different : le modulo du tirage
    n'est pas le meme et **le PREMIER coup deja** discrimine les deux ordres.
  * `--case cordclaw` (axe CONSOMMATION) -- `admecRuststalker`, actif `CordClaw` (1122) qui pose
    sur lui-meme l'effet 1250 : 2 coups PREDEFINED profil `DirectDamage` PiercingRatio **100**
    => `max(0, d - armure, d x 1.0) = d`, la reduction est l'IDENTITE, les deux ordres donnent le
    MEME premier coup. Ce qui discrimine ici est le seul **resolve slot-8 gaspille**, qui decale
    le flux RNG : c'est le **DEUXIEME** coup qui tranche. Ce porteur n'a NI `GetStuckIn`
    (le `Maybe` qui pollue `orksRuntherd`) NI extra-degat conditionnel -> il isole aussi le
    residu R6-b' du 2e coup.

Discipline runner : state-file UNIQUE en chemin ABSOLU sous logs/, `--board` explicite, dispose
en fin. ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import sys

from probe_r6_round_materialize import (_build, _drive_normal, _live_amounts,   # noqa: F401
                                        _mkrpc, additional_hits_variant)

SQUIG_CARRIER = "orksRuntherd"
SQUIG_TARGET = "ultraApothecary"
CC_CARRIER = "admecRuststalker"       # CordClaw 1122 -> effet 1250 (2 coups DirectDamage p100)
CC_ABILITY = 1122
BOARD = "MC1_67"


def _replay_orders(dv, ob, snap, board, rng0, caster_id, target_id, moved, extra_rolls=0):
    """Rejoue le MEME coup offline (meme etat, meme flux RNG) sous les DEUX ordres candidats +
    le PORT LIVRE. La materialisation est celle du port dans les trois rejeux (`force_round=None`
    -> `reduce_group_damage`), donc SEUL l'ordre varie -- decomposition par etage."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import set_moved_flag
    from engine.runner.operations import additional_hits as _ah_mod
    from engine.runner.operations.damage_ops import normal as _dnormal
    from engine.runner.operations.damage_ops import ability as _dability

    def _one(impl):
        st = load_state(dv, ob, snap, board=board)
        if moved:
            set_moved_flag(st, caster_id)
        rng = IntBasedMersenneTwister()
        rng.mt = list(rng0["mt"])
        rng.mti = rng0["mti"]
        st.rng = rng
        per_hit: list = []
        arme: list = []
        o_ah = _ah_mod.execute_additional_hits
        o_n, o_a = _dnormal.execute_additional_hits, _dability.execute_additional_hits

        def _rec(*a, **kw):
            out = (impl or o_ah)(*a, **kw)
            if out:
                per_hit.extend(out.get("per_hit") or [])
            return out

        _ah_mod.execute_additional_hits = _rec
        _dnormal.execute_additional_hits = _rec
        _dability.execute_additional_hits = _rec
        try:
            runner = Runner(st).install_default_handlers(20)
            runner.apply(AttackUnitMessage(caster_id, target_id))
            last = getattr(getattr(runner, "damage_handler", None), "last", None)
            if isinstance(last, dict):
                arme.extend(last.get("per_hit") or [])
            return per_hit, arme
        finally:
            _ah_mod.execute_additional_hits = o_ah
            _dnormal.execute_additional_hits = o_n
            _dability.execute_additional_hits = o_a

    rtr = _one(additional_hits_variant("reduce_then_roll", None))
    rer = _one(additional_hits_variant("roll_then_reduce", None))
    rer_nores = _one(additional_hits_variant("roll_then_reduce", None, is_attack_op=False))
    ship = _one(None)
    out = {"reduce_then_roll": rtr[0], "roll_then_reduce": rer[0],
           "roll_then_reduce_no_resolve": rer_nores[0], "shipped": ship[0], "arme": ship[1]}
    if extra_rolls:
        for k in range(1, int(extra_rolls) + 1):
            out["extra_rolls_%d" % k] = _one(_extra_rolls_variant(k))[0]
    return out


def _extra_rolls_variant(k):
    """DIAGNOSTIC du residu R6-b' (2e coup du groupe non reproduit sur `orksRuntherd`) : meme
    pipeline que le port, mais on consomme `k` tirages ENTRE deux coups du groupe. Sert
    uniquement a CHIFFRER « combien de tirages le natif consomme en plus », pas a porter quoi
    que ce soit -- les coups sont donc emis un par un (`count=1`), ce qui n'est PAS le
    decoupage natif (l'etage limites/rogne et la failedList sont per-ATTAQUE)."""
    def _exec(state, attacker_id, target_id, tgt, thc, groups, mods, def_mods, armor, hit_mult,
              block_sources, shc, spread_pct=20, extra_pierce=0,
              bonus_hit_chance=None, hit_index0=0, crit_allowed0=True, attack_profile=None,
              hit_interceptor=None, failed_block0=None, damaging_done0=False):
        # #963-r2 : `damaging_done0` (`isFirstDamagingHit`) complete la signature. REIMPLEMENTATION
        # -- le parametre est accepte et NON LU, comme `failed_block0`.
        # Comme `additional_hits_variant` : la signature suit `execute_additional_hits` PARAMETRE
        # POUR PARAMETRE et repasse tout ce que ce diagnostic ne fait pas varier -- sa SEULE
        # variable est le nombre `k` de tirages intercalaires. (Garde :
        # `test_additional_hits_variant_signatures_offline.py`.)
        import gameconfig as GC
        from engine.runner.operations.damage import AttackDamageOperation, HitDamage
        from engine.runner.operations.additional_hits import reduce_group_damage
        from engine.entities.damage_trait import DamageTrait
        from engine.services.damage_prediction import get_base_damage_fix64
        if not groups or thc is None or int(thc.hp or 0) <= 0:
            return None
        out = {"groups": 0, "hits": 0, "total": 0, "per_hit": [], "rolls": [], "profiles": []}
        # #407 : `OngoingAttack+0x48` (`FailedBlockIds`) CHAINE, comme le port livre. Ce diagnostic
        # decoupe chaque coup en un `_run_hits` distinct : sans chainage la failed-list se perdrait
        # meme ENTRE COUPS d'un groupe, ce qui n'est pas la variable mesuree ici (`k`).
        failed_block = set(failed_block0 or ())
        for g in groups:
            # #227 : meme convention que le port livre -- profil NULL = profil de l'ATTAQUE.
            g_profile = g.get("profile")
            if g_profile is None:
                g_profile = attack_profile
            dp = GC.damage_profile(g_profile) or {}
            g_pierce = max(0, min(100, int(dp.get("PiercingRatio") or 0) + int(extra_pierce or 0)))
            if "min" in g and "max" in g:
                g_min, g_max = int(g.get("min") or 0), int(g.get("max") or 0)
            else:
                mm = get_base_damage_fix64(g.get("amount") or 0, spread_pct=spread_pct)
                g_min, g_max = mm.min, mm.max

            def _red(v, _p=g_pierce):
                return reduce_group_damage(v, _p, armor, mods, def_mods, hit_mult=hit_mult)

            g_block = (None if DamageTrait.NoBlocking.name in (dp.get("Traits") or [])
                       else block_sources)
            hd = HitDamage(g_min, g_max)
            for i in range(max(0, int(g.get("count") or 0))):
                if i:
                    for _ in range(k):
                        state.rng.next_internal(0, 100)
                r = AttackDamageOperation._run_hits(
                    state.rng, hd, hd, 0, False, 1, g_block,
                    shield=(shc.get_total_shield() if shc is not None else 0),
                    post_roll=_red, is_attack_damage_op=True,
                    hit_interceptor=hit_interceptor,      # #366-r1 : threade VERBATIM
                    # #366-r1-crit-multihit : `isCriticalDamageAllowed` (`OngoingAttack+0x40`)
                    # repasse VERBATIM. Non CHAINE d'un coup a l'autre (le port livre chaine
                    # `r["crit_allowed"]`) : ce diagnostic passe `crit_enabled=False` ci-dessus,
                    # donc le canal crit y est structurellement ferme -- sa SEULE variable reste
                    # le nombre `k` de tirages intercalaires.
                    crit_allowed0=crit_allowed0,
                    failed_block0=failed_block,          # #407 : chaine (cf. ci-dessus)
                    limits=AttackDamageOperation._target_limits(tgt, thc, g_profile, is_special=1),
                    limits_hp=int(thc.hp or 0))
                failed_block = r["failed_block"]
                out["per_hit"] += r["per_hit"]
                out["total"] += r["total"]
            out["groups"] += 1
            out["profiles"].append(g_profile)
        # #419-r6-r1 -- MEME gisement que `probe_r6_round_materialize` : les trois cles d'etat
        # d'`OngoingAttack` que le port livre pose depuis #419-r3. Sans elles,
        # `damage_hits.attack_state_out(r, ah)` leve `KeyError` des qu'un groupe existe -- et
        # l'echec accuse le moteur au lieu du harnais. Ce contrefactuel-ci n'a pas encore de
        # consommateur qui traverse ce chemin, donc il n'a jamais rougi ; c'est exactement le
        # profil d'un defaut qui attend son premier appelant.
        out["next_hit_index"] = int(hit_index0 or 0) + int(out.get("hits") or 0)
        out["crit_allowed"] = bool(crit_allowed0)
        out["failed_block"] = failed_block
        return out if out["groups"] else None
    return _exec


def _confront(label, seed, live, off):
    """Imprime la confrontation et rend (n_match_c1, n_match_c2, n_disc_c1, n_disc_c2)."""
    arme = off["arme"]
    n = len(arme)
    grp_live = live[n:]
    print("[%s] seed %s live=%s (arme offline=%s -> groupe live=%s)"
          % (label, seed, live, arme, grp_live))
    for k in sorted(off, key=lambda x: (x == "arme", x.startswith("extra_rolls"), x)):
        if k != "arme":
            print("  %-28s -> %s" % (k, off[k]))
    if live[:n] != arme:
        print("  [!] coups d'ARME desalignes -> mesure NON portante sur cet etage")
        return (0, 0, 0, 0)
    rtr, rer = off["reduce_then_roll"], off["roll_then_reduce"]
    m1 = int(bool(grp_live) and bool(rer) and rer[0] == grp_live[0])
    m2 = int(len(grp_live) > 1 and len(rer) > 1 and rer[1] == grp_live[1])
    d1 = int(bool(rtr) and bool(rer) and rtr[0] != rer[0])
    d2 = int(len(rtr) > 1 and len(rer) > 1 and rtr[1] != rer[1])
    return (m1, m2, d1, d2)


def _case_squig(rpc, args):
    """AXE LARGEUR : `orksRuntherd`/SquigHound en regime percage-dominant -> le 1er coup du
    groupe suffit a discriminer les deux ordres."""
    from engine.entities.pathfinding.board import Board
    tot = [0, 0, 0, 0]
    n_rows = 0
    for seed in [s for s in args.seeds.split(",") if s]:
        rid, sf = _build(seed, SQUIG_CARRIER, args.target,
                         extra=["--crit", "0,0", "--block-target", "0,0",
                                "--armor-target", str(args.armor)], rank=args.rank)
        if rid is None:
            continue
        try:
            bg = rpc("boardGraph", {"runnerId": rid}, 60)
            board = Board(bg["tiles"], adjacency="native_sym")
            cid, tid, moved = _drive_normal(rpc, rid, board, SQUIG_CARRIER, args.target)
            if cid is None:
                print("seed %s: drive KO" % seed)
                continue
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
            ob = rpc("observeBattle", {"runnerId": rid}, 60)
            snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
            rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
            cu = next((u for u in (dv.get("units") or []) if u.get("id") == cid), {})
            nrm = next((a for a in (cu.get("abilities") or []) if a.get("kind") == "normal"), None)
            res = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": cid, "targetId": tid,
                "abilityType": nrm["id"]}, "captureEvents": True}, 120)
            live, dirty = _live_amounts(res, tid, verbose=args.verbose)
            if dirty:
                print("[squig] seed %s: coup SALE (crit/block/evade) -- ignore" % seed)
                continue
            off = _replay_orders(dv, ob, snap, board, rng0, cid, tid, moved,
                                 extra_rolls=args.extra_rolls)
            r = _confront("squig", seed, live, off)
            tot = [a + b for a, b in zip(tot, r)]
            n_rows += 1
        finally:
            _dispose(rpc, rid, sf)
    print()
    print("[squig] BILAN %d montages : coup1 roll-then-reduce %d/%d (discriminants %d), "
          "coup2 %d/%d (discriminants %d)"
          % (n_rows, tot[0], n_rows, tot[2], tot[1], n_rows, tot[3]))
    return 0


def _case_cordclaw(rpc, args):
    """AXE CONSOMMATION : `admecRuststalker` caste CordClaw (pose l'effet 1250 sur LUI-MEME),
    puis attaque NORMALEMENT au tour suivant. Profil DirectDamage p100 -> reduction = IDENTITE,
    donc les deux ordres donnent le MEME 1er coup ; seul le resolve slot-8 GASPILLE les separe,
    et c'est le 2e coup qui tranche. Porteur SANS `GetStuckIn` -> isole le residu R6-b'."""
    from engine.entities.pathfinding.board import Board
    tot = [0, 0, 0, 0]
    n_rows = 0
    for seed in [s for s in args.seeds.split(",") if s]:
        rid, sf = _build(seed, CC_CARRIER, args.a_units,
                         extra=["--crit", "0,0", "--block-target", "0,0",
                                "--armor-target", str(args.armor)], rank=args.rank)
        if rid is None:
            continue
        try:
            bg = rpc("boardGraph", {"runnerId": rid}, 60)
            board = Board(bg["tiles"], adjacency="native_sym")
            if not _cast_cord_claw(rpc, rid, board):
                print("[cordclaw] seed %s: cast KO" % seed)
                continue
            cid, tid, moved = _drive_normal(rpc, rid, board, CC_CARRIER, args.target)
            if cid is None:
                d = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
                print("[cordclaw] seed %s: drive post-cast KO -- units=%s"
                      % (seed, [(u.get("visualId"), u.get("owner"), u.get("alive"),
                                 (u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
                                for u in (d.get("units") or [])]))
                continue
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
            cu = next((u for u in (dv.get("units") or []) if u.get("id") == cid), {})
            effs = {e.get("effectType") for e in (cu.get("effects") or [])}
            if 1250 not in effs:
                print("[cordclaw] seed %s: effet 1250 absent au tour d'attaque (eff=%s)"
                      % (seed, sorted(x for x in effs if x is not None)))
                continue
            ob = rpc("observeBattle", {"runnerId": rid}, 60)
            snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
            rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
            nrm = next((a for a in (cu.get("abilities") or []) if a.get("kind") == "normal"), None)
            res = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": cid, "targetId": tid,
                "abilityType": nrm["id"]}, "captureEvents": True}, 120)
            live, dirty = _live_amounts(res, tid, verbose=args.verbose)
            if dirty:
                print("[cordclaw] seed %s: coup SALE (crit/block/evade) -- ignore" % seed)
                continue
            off = _replay_orders(dv, ob, snap, board, rng0, cid, tid, moved)
            r = _confront("cordclaw", seed, live, off)
            tot = [a + b for a, b in zip(tot, r)]
            n_rows += 1
        finally:
            _dispose(rpc, rid, sf)
    print()
    print("[cordclaw] BILAN %d montages : coup1 roll-then-reduce %d/%d (discriminants %d), "
          "coup2 %d/%d (discriminants %d)"
          % (n_rows, tot[0], n_rows, tot[2], tot[1], n_rows, tot[3]))
    return 0


def _cast_cord_claw(rpc, rid, board, max_turns=25):
    """Amene `admecRuststalker` a portee de CordClaw et le caste. L'effet 1250 se pose sur le
    CASTER (`AddEffect(target=Self)`) et dure 2 rounds -> l'attaque du tour SUIVANT porte les
    coups additionnels (l'attaque DU cast, elle, ne les a pas : l'effet est pose APRES)."""
    from collections import deque
    my = None
    for _ in range(max_turns):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        cst = next((u for u in (dv.get("units") or [])
                    if u.get("visualId") == CC_CARRIER and u.get("alive")), None)
        if cst is None:
            return False
        if my is None:
            my = cst.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": cst["id"],
                                    "abilityType": CC_ABILITY}, 90)
        ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                   if a.get("abilityId") == CC_ABILITY), {})
        here = [x.get("targetId") for x in (ab.get("fromHere") or [])]
        if here:
            r = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": cst["id"], "targetId": here[0],
                "abilityType": CC_ABILITY}}, 120)
            return isinstance(r, dict) and r.get("ok")
        # pas encore a portee -> se rapprocher de l'ennemi le plus proche
        foes = [u for u in (dv.get("units") or [])
                if u.get("alive") and u.get("owner") != my and u.get("pos")]
        if not foes:
            return False
        ttile = board.id_at(foes[0]["pos"]["col"], foes[0]["pos"]["row"])
        dist, q = {ttile: 0}, deque([ttile])
        while q:
            x = q.popleft()
            for n in board.neighbours(x):
                if n not in dist and board.walkable(n):
                    dist[n] = dist[x] + 1
                    q.append(n)
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == cst["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        col, row = reach[min(pool, key=lambda t: dist[t])]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cst["id"], "to": {"col": col, "row": row}}}, 60)
    return False


def _dispose(rpc, rid, sf):
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
    ap.add_argument("--case", default="squig", choices=("squig", "cordclaw"))
    ap.add_argument("--seeds", default="777,31337,12345,314159,88")
    ap.add_argument("--rank", type=int, default=None)
    ap.add_argument("--armor", type=int, default=6000)
    ap.add_argument("--target", default=SQUIG_TARGET)
    ap.add_argument("--a-units", dest="a_units", default=None)
    ap.add_argument("--extra-rolls", dest="extra_rolls", type=int, default=0,
                    help="diagnostic R6-b' : rejoue aussi avec 1..N tirages consommes ENTRE "
                         "deux coups du groupe (chiffre le decalage RNG residuel)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if args.a_units is None:
        args.a_units = args.target
    rpc = _mkrpc()
    if args.case == "squig":
        return _case_squig(rpc, args)
    return _case_cordclaw(rpc, args)


if __name__ == "__main__":
    sys.exit(main())
