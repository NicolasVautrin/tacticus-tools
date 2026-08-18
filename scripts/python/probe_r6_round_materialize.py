"""R6 -- MATERIALISATION FINALE des deux vecteurs restes TRONQUANTS : `execute_normal_like`
et `additional_hits`.

QUESTION (binaire) : ces deux vecteurs doivent-ils ARRONDIR (`Fix64.Round(., AwayFromZero)`)
la ou ils TRONQUENT (`op_Explicit` = `raw >> 32`) ?

RE (decompile = verite, gqfc5mff6c) :
  * `IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute` appelle
    le slot 0x3c de l'interface OperationProcessor = `Core.Services.OperationProcessor$$AttackDamage`
    -> `IdunBattle.Operations.AttackDamageOperation$$Execute` ; et
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType`
    finit sur `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits`. Les DEUX voies de coups
    additionnels retombent donc sur le MEME per-coup `IdunBattle.Operations.AttackDamageOperation$$
    ExecuteHit` que l'attaque d'arme.
  * `execute_normal_like` est le mode `amount` de la MEME feuille `AttackDamageBehaviour`
    (`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`) et la route du
    `UseNormalAttackIfAble` on-appearance d'un summon -- toutes deux famille ATTACK, donc
    encore `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`.
  * `ExecuteHit` resout la cellule par le slot 4 `IdunBattle.Core.Services.DamagePrediction$$
    PredictAttack` (cache -> `PredictAttackRaw`) puis le slot 8 `IdunBattle.Core.Services.
    DamagePrediction$$RandomlyResolveMinMaxDamage`. `PredictAttackRaw` passe par
    `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`, dont le
    dernier etage est le MULTIPLICATEUR (slot 0x10 -> `IdunBattle.Core.Services.
    DamageCalculations$$CalculateBaseDamageWithModifiers`), LU verbatim :
        v = Mul(dmg, multiplier) ; v <= 0 -> 0 ; 0 < v < 1 -> 1 ; sinon Round(v, AwayFromZero)
    traverse des qu'un `Nullable<DamageModifiers>` HasValue (attaquant OU defenseur).
  => les trois vecteurs COMBAT (normale #131, ability bounds-mode HeavyGravCannon, et ces deux-ci)
     partagent LE MEME etage. Le live sert a CONFIRMER, sur un regime DISCRIMINANT.

REGIME DISCRIMINANT (les deux materialisations donnent des cellules DIFFERENTES) :
  (a) les DEUX %-list vides -- sinon `IdunBattle.Core.Services.DamageCalculations$$
      ApplyCappedModifiers` arrondit deja en fin d'appel ;
  (b) la branche PERCAGE du plancher `max(0, d - armure, d x pierce%)` l'emporte, i.e.
      `armure > d x (1 - pierce/100)` -- sinon `d - armure` est ENTIER ;
  (c) la partie fractionnaire de `d x fix(pierce/100)` est >= 0.5. `fix(p/100)` est
      LEGEREMENT INFERIEUR a la fraction exacte des que p/100 n'est pas dyadique
      (`Div(20,100)` = 0.1999999999534) -> tout `d` tel que `d x p / 100` soit ENTIER donne
      une fraction ~0.99999 : c'est le cas le plus discriminant.

MONTAGES (`--case`) :
  * `normal_like`      : `ultraInceptorSgt` caste DeathFromAbove (1003) -> chaque `ultraSmnInceptor`
                         execute son `UseNormalAttackIfAble` on-appearance = 6 coups Bolter
                         (pierce 20) via `execute_normal_like`, contre une cible ARMUREE.
  * `additional_hits`  : `orksRuntherd` (passif `SquigHound`, effet 0x50c) attaque -> 2 coups
                         additionnels [minDmg,maxDmg] profil Physical (pierce 1) via
                         `execute_additional_hits`, contre une cible ARMUREE.
  * `scan`             : 100 % OFFLINE -- balaie (base|bornes, pierce, armure) et imprime les
                         regimes discriminants (aucun runner, aucune session requise).
  * `explore`          : build + dump LIVE (armures, effets, niveaux, multiplicateurs) pour
                         choisir la cible et verifier que le regime est en place.

Discipline runner : state-file UNIQUE en chemin ABSOLU sous logs/, `--board` explicite, dispose
en fin. ASCII only (cp1252).
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
TAG = "pr6"
BOARD = "MC1_67"

DFA_CASTER = "ultraInceptorSgt"      # DeathFromAbove 1003 -> ultraSmnInceptor (Bolter p20, 6 coups)
DFA_ABILITY = 1003
SQUIG_CARRIER = "orksRuntherd"       # passif SquigHound -> effet 0x50c (2 coups Physical p1, PREDEFINED)
AH_CARRIER = "tauCrisis"             # passif CyclicIonBlaster -> effet 0x47c (3 coups Particle p35,
#                                      forme `amount` = struct DEGENERE, donc reduce-then-roll --
#                                      MEME forme que l'attaque normale, ce qui ISOLE l'etage de
#                                      materialisation de l'etage ORDRE (cf. rapport R6).


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _mkrpc():
    import rl_collect_batch as R
    sid = R._resolve_session()
    _unwrap(R._rpc(sid, "warmupGameSingletons", [{}], timeout=180))   # idempotent (no-op si chaud)

    def _call(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))
    return _call


def _build(seed, p_units, a_units, extra=None, rank=None):
    sf = ROOT / "logs" / "runners" / f"{TAG}-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
            "--board", BOARD, "--roster", "1", "--p-units", p_units, "--a-units", a_units,
            *(["--rank", str(rank)] if rank else []), *(extra or [])]
    proc = subprocess.run(args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not sf.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-500:])
        return None, None
    return int(json.loads(sf.read_text())["runnerId"]), sf


# --------------------------------------------------------------------------- offline


def _two_models(bounds, pierce, armor):
    """Rend `((lo_floor, hi_floor), (lo_round, hi_round), (exact_lo, exact_hi))` pour un couple de
    bornes BRUTES reduit par (pierce, armure) SANS aucun %-mod (regime discriminant (a))."""
    from engine.services.damage_prediction import apply_pierce_and_modifiers
    from engine.services.damage_modifiers import DamageModifiers
    import engine.services.fix64 as fx
    f, r, e = [], [], []
    for b in bounds:
        v = apply_pierce_and_modifiers(int(b), int(pierce), int(armor), DamageModifiers(),
                                       attacker_additive_pre=True)
        raw = v.raw
        f.append(fx.to_int(raw))
        r.append(fx.to_int(fx.round_raw(raw, 1)))
        e.append(raw / 2 ** 32)
    return tuple(f), tuple(r), tuple(e)


def _case_scan(_rpc, args):
    """100 % OFFLINE : balaie les regimes et imprime lesquels DISCRIMINENT. Sert a choisir un
    couple (base|bornes, profil, armure) AVANT de bruler un runner."""
    from engine.services.damage_prediction import get_base_damage_fix64
    from engine.entities.effects.magnitude import ability_var
    import gameconfig as GC

    print("=== vecteur normal_like : on-appearance `ultraSmnInceptor` (Bolter pierce 20, spread 20%)")
    print("    base = ability_var(DeathFromAbove, summonDmg, <lvl caster>, mult)")
    for mult in (100, 150, 180, 200):
        for lvl in (30, 40, 50, 60, 65):
            base = ability_var("DeathFromAbove", "summonDmg", lvl, multiplier_pct=mult)
            if not base:
                continue
            mm = get_base_damage_fix64(int(base), spread_pct=20)
            for armor in (1909, 2008, 2411, 3513):
                fl, rd, ex = _two_models((mm.min, mm.max), 20, armor)
                print("  mult=%-4d lvl=%-3d base=%-5d bornes=[%d,%d] armure=%-5d "
                      "floor=%s round=%s exact=(%.4f,%.4f) DISCRIMINANT=%s"
                      % (mult, lvl, base, mm.min, mm.max, armor, fl, rd, ex[0], ex[1], fl != rd))

    print()
    print("=== vecteur additional_hits : groupe `SquigHound` (predefined [minDmg,maxDmg], "
          "profil %s pierce %s)"
          % (((GC.ability("SquigHound") or {}).get("constants") or {}).get("damageProfile"),
             (GC.damage_profile("Physical") or {}).get("PiercingRatio")))
    for mult in (100, 150, 180, 200):
        for lvl in (30, 40, 50, 60, 65):
            mn = ability_var("SquigHound", "minDmg", lvl, multiplier_pct=mult)
            mx = ability_var("SquigHound", "maxDmg", lvl, multiplier_pct=mult)
            if not mn or not mx:
                continue
            for armor in (1909, 2008, 2411, 3513):
                fl, rd, ex = _two_models((mn, mx), 1, armor)
                print("  mult=%-4d lvl=%-3d bornes=[%d,%d] armure=%-5d floor=%s round=%s "
                      "exact=(%.4f,%.4f) DISCRIMINANT=%s"
                      % (mult, lvl, mn, mx, armor, fl, rd, ex[0], ex[1], fl != rd))
    return 0


# --------------------------------------------------------------------------- live


def _dump_live(rpc, rid, note=""):
    from engine.runner.snapshot import load_state
    from engine.runner.damage_model import defender_fixed_armor
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    st = load_state(dv, ob, snap)
    print("--- etat live %s" % note)
    for u in (dv.get("units") or []):
        if not u.get("alive"):
            continue
        uc = next((su.get("unitConfig") or {} for su in (snap.get("units") or [])
                   if su.get("entityId") == u.get("id")), {})
        print("  id=%-4s %-22s hp=%-6s armure=%-5s effets=%s lvlA=%s lvlP=%s mult=%s"
              % (u.get("id"), u.get("visualId"), u.get("hp"),
                 defender_fixed_armor(st, u.get("id")),
                 [e.get("name") for e in (u.get("effects") or [])],
                 uc.get("activeAbilityLevel"), uc.get("passiveAbilityLevel"),
                 uc.get("abilityVariablesMultiplier")))
    return dv, ob, snap


def _drive_into_range(rpc, rid, board, caster_vis, target_vis, ability_id, max_turns=25):
    """Amene `caster_vis` a portee de cast de `target_vis` (positions DRIVEES). Rend
    `(caster_id, target_id, moved)` ou `(None, None, 0)`."""
    from collections import deque
    my, moves = None, 0
    for _ in range(max_turns):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        units = dv.get("units") or []
        cst = next((u for u in units if u.get("visualId") == caster_vis and u.get("alive")), None)
        tg = next((u for u in units if u.get("visualId") == target_vis and u.get("alive")), None)
        if cst is None or tg is None:
            return None, None, 0
        if my is None:
            my = cst.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": cst["id"],
                                    "abilityType": ability_id}, 90)
        ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                   if a.get("abilityId") == ability_id), {})
        legal = [x.get("targetId") for x in (ab.get("fromHere") or [])]
        if tg["id"] in legal:
            return cst["id"], tg["id"], moves
        tpos = (tg["pos"]["col"], tg["pos"]["row"])
        ttile = board.id_at(*tpos)
        dist = {ttile: 0}
        q = deque([ttile])
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
        best = min(pool, key=lambda t: dist[t])
        col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cst["id"], "to": {"col": col, "row": row}}}, 60)
        moves += 1
        if dist[best] <= 1:                       # deja au contact : laisser le cast tenter
            continue
    return None, None, 0


def _live_amounts(res, target_id, verbose=False):
    """Per-coup LIVE attribues a `target_id` (dans l'ordre des events), + flags de salete."""
    out, dirty = [], False
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if td.get("Target_Id") == target_id and "Amount" in td:
                out.append(int(td.get("Amount")))
                dirty = dirty or bool(td.get("Attack_DidCrit")) or bool(td.get("Attack_DidBlock")) \
                    or bool(td.get("Attack_DidEvade"))
                if verbose:
                    print("   live event: %s" % {k: v for k, v in td.items()
                                                 if k in ("Amount", "Source_Id", "Effect_Type",
                                                          "Damage_Profile", "Active_Ability_Type",
                                                          "Attack_DidCrit", "Attack_DidBlock",
                                                          "Attack_Weapon_IsMelee")})
    return out, dirty


def _replay(dv, ob, snap, board, rng0, caster_id, target_id, ability_id, moved,
            module_path, force_round, ah_impl=None):
    """Rejoue le MEME cast OFFLINE sur le MEME flux RNG, en ne faisant varier QUE la
    materialisation finale du vecteur vise (`round_materialize` FORCE dans les globals du module
    porteur -- patcher le `__init__` du package serait un NO-OP SILENCIEUX, cf. #169)."""
    import importlib
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage, AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import set_moved_flag
    from engine.services.damage_modifiers import apply_all_modifiers as _aam
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations import additional_hits as _ah_mod

    mod = importlib.import_module(module_path)
    st = load_state(dv, ob, snap, board=board)
    if moved:
        set_moved_flag(st, caster_id)
    r = IntBasedMersenneTwister()
    r.mt = list(rng0["mt"])
    r.mti = rng0["mti"]
    st.rng = r
    per_hit: list = []
    diag: list = []
    orig_aam = mod.apply_all_modifiers
    orig_nl = AttackDamageOperation.execute_normal_like
    orig_ah = _ah_mod.execute_additional_hits

    def _patched(v, m, round_materialize=False):
        return _aam(v, m, round_materialize=force_round)

    def _rec_nl(*a, **kw):
        out = orig_nl(*a, **kw)
        if out:
            per_hit.extend(out.get("per_hit") or [])
        return out

    def _rec_ah(*a, **kw):
        # a = (state, attacker_id, target_id, tgt, thc, groups, mods, def_mods, armor, hit_mult,
        #      block_sources, shc, ...) -- on trace les entrees de l'etage reduction pour pouvoir
        # DIAGNOSTIQUER un regime non discriminant (%-list non vide, armure dominante...).
        if len(a) >= 9:
            diag.append({"groups": a[5], "att_pct": list(getattr(a[6], "pct_list", []) or []),
                         "att_add": getattr(a[6], "additive", None),
                         "def_pct": list(getattr(a[7], "pct_list", []) or []),
                         "def_flat": list(getattr(a[7], "flat_reductions", []) or []),
                         "armor": a[8], "hit_mult": a[9] if len(a) > 9 else None,
                         "extra_pierce": kw.get("extra_pierce")})
        out = (ah_impl or orig_ah)(*a, **kw)
        if out:
            per_hit.extend(out.get("per_hit") or [])
        return out

    mod.apply_all_modifiers = _patched
    AttackDamageOperation.execute_normal_like = staticmethod(_rec_nl)
    _ah_mod.execute_additional_hits = _rec_ah
    # `execute` / `execute_ability_attack` ont importe le symbole DANS leurs globals -> re-pointer
    from engine.runner.operations.damage_ops import normal as _dnormal
    from engine.runner.operations.damage_ops import ability as _dability
    o_nrm, o_abl = _dnormal.execute_additional_hits, _dability.execute_additional_hits
    _dnormal.execute_additional_hits = _rec_ah
    _dability.execute_additional_hits = _rec_ah
    try:
        runner = Runner(st).install_default_handlers(20)
        if ability_id is None:
            runner.apply(AttackUnitMessage(caster_id, target_id))
        else:
            runner.apply(ActiveAbilityMessage(caster_id=caster_id, target_id=target_id,
                                              ability_type=ability_id))
        last = getattr(getattr(runner, "damage_handler", None), "last", None)
        if isinstance(last, dict):
            diag.append({"arme_per_hit": last.get("per_hit"), "arme_hits": last.get("hits"),
                         "arme_pierce": last.get("pierce"), "arme_armure": last.get("armor")})
        return per_hit, diag
    finally:
        mod.apply_all_modifiers = orig_aam
        AttackDamageOperation.execute_normal_like = orig_nl
        _ah_mod.execute_additional_hits = orig_ah
        _dnormal.execute_additional_hits = o_nrm
        _dability.execute_additional_hits = o_abl


def additional_hits_variant(order, force_round, is_attack_op=True):
    """Variante INSTRUMENTEE d'`execute_additional_hits` : meme pipeline, mais ORDRE et
    MATERIALISATION parametres. Sert a DECOMPOSER PAR ETAGE quand le port ne reproduit le live
    sous AUCUN des deux modeles de materialisation -- l'autre etage (l'ORDRE reduce/roll) est
    alors le suspect.

      `order` = "reduce_then_roll" (le port : bornes PRE-reduites, `post_roll=None`, 1 tirage/coup)
                | "roll_then_reduce" (struct NON degenere de `IdunBattle.Core.HitDamage$$GetDamage`
                  -> 1 tirage BRUT + 1 resolve slot-8 GASPILLE = 2 tirages/coup, cf. `_one_hit`).
      `force_round` = materialisation finale FORCEE (`Fix64.Round(., AwayFromZero)` vs
                      `op_Explicit`), ou **None** = celle du PORT LIVRE (`reduce_group_damage`
                      d'`operations/additional_hits.py`) -- c'est CE mode que la garde
                      `test_additional_hits_rounding_live` confronte au live, pour que le test
                      soit ROUGE si l'etage regresse.

    R6-b' : cette variante IGNORE volontairement `bonus_hit_chance`/`hit_index0` -> elle EST le
    CONTREFACTUEL « le `Maybe` after-hit n'est PAS evalue sur les coups d'un groupe » (le port
    d'avant R6-b'). C'est a ce titre qu'elle sert de discriminant a
    `test_additional_hits_after_hit_maybe_live`.

    ⚠ TOUT LE RESTE EST TRANSMIS VERBATIM, et c'est la CONDITION de validite du contrefactuel : la
    substitution ne doit faire varier QUE `order` et `force_round`. Tout parametre qu'elle avalerait
    sans le repasser a `_run_hits` deviendrait une TROISIEME variable silencieuse, et l'ecart mesure
    ne porterait plus sur l'etage vise. `hit_interceptor` (#366-r1) en est l'exemple : le laisser
    tomber desarmerait le discard `HarlequinsPanoply` ET le `RegisterBlockMade` per-coup dans les
    rejeux offline, mais PAS dans le port livre -- l'ecart se lirait comme une regression de
    materialisation. La signature suit donc `execute_additional_hits` PARAMETRE POUR PARAMETRE
    (garde : `test_additional_hits_variant_signatures_offline.py`).
    """
    def _exec(state, attacker_id, target_id, tgt, thc, groups, mods, def_mods, armor, hit_mult,
              block_sources, shc, spread_pct=20, extra_pierce=0,
              bonus_hit_chance=None, hit_index0=0, crit_allowed0=True, attack_profile=None,
              hit_interceptor=None, failed_block0=None, damaging_done0=False,
              source_ability=None, attacker_mods_for_profile=None):
        # #488-r3 : `attacker_mods_for_profile` complete la signature du port. Cette variante
        # REIMPLEMENTE la materialisation et n'a pas de canal de mods per-groupe -- accepte et
        # NON LU, comme `source_ability`.
        # #1020-r6 : `source_ability` complete la signature du port. Cette variante REIMPLEMENTE
        # la materialisation et n emet aucun event -- accepte et NON LU, comme `damaging_done0`.
        # #963-r2 : `damaging_done0` (`isFirstDamagingHit`) fait partie de la signature du port.
        # Cette variante REIMPLEMENTE la materialisation et ne modelise pas cet etat -- le
        # parametre est donc accepte et NON LU, comme `failed_block0` juste avant.
        import gameconfig as GC
        from engine.runner.operations.damage import AttackDamageOperation, HitDamage
        from engine.entities.damage_trait import DamageTrait
        from engine.services.damage_prediction import (get_base_damage_fix64,
                                                       apply_pierce_and_modifiers)
        from engine.services.damage_modifiers import apply_all_modifiers
        if not groups or thc is None or int(thc.hp or 0) <= 0:
            return None
        out = {"groups": 0, "hits": 0, "total": 0, "per_hit": [], "rolls": [], "profiles": []}
        # #227 : meme convention que le port livre -- profil NULL = profil de l'ATTAQUE (le groupe
        # passe par `ExecuteAdditionalHitsWithoutDamageProfileType`, execute AVANT les groupes a
        # profil). L'ORDRE et la MATERIALISATION restent les seules variables de ce contrefactuel.
        groups = ([g for g in groups if g.get("profile") is None]
                  + [g for g in groups if g.get("profile") is not None])
        # #407 : `OngoingAttack+0x48` (`FailedBlockIds`) CHAINE de groupe en groupe, comme le port
        # livre -- l'exclusion par source n'est pas une variable de ce contrefactuel (ORDRE +
        # MATERIALISATION le sont).
        failed_block = set(failed_block0 or ())
        for g in groups:
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
                if force_round is None:            # materialisation DU PORT LIVRE (foyer unique)
                    from engine.runner.operations.additional_hits import reduce_group_damage
                    return reduce_group_damage(v, _p, armor, mods, def_mods, hit_mult=hit_mult)
                return apply_all_modifiers(
                    apply_pierce_and_modifiers(v, _p, armor, mods, hit_mult=hit_mult,
                                               attacker_additive_pre=True),
                    def_mods, round_materialize=force_round)

            g_block = (None if DamageTrait.NoBlocking.name in (dp.get("Traits") or [])
                       else block_sources)
            shield_total = shc.get_total_shield() if shc is not None else 0
            if order == "roll_then_reduce":
                hd = HitDamage(g_min, g_max)                    # bornes BRUTES
                post = _red
            else:
                hd = HitDamage(_red(g_min), _red(g_max))        # bornes PRE-reduites
                post = None
            hd, _ = AttackDamageOperation._apply_max_out(state, attacker_id, hd, hd)
            r = AttackDamageOperation._run_hits(
                state.rng, hd, hd, 0, False, max(0, int(g.get("count") or 0)), g_block,
                shield=shield_total, post_roll=post,
                # #366-r1 : threade VERBATIM, comme le port livre -- l'intercepteur per-coup
                # (`should_discard` / `on_blocked` + `RegisterBlockMade`) n'est PAS une variable de
                # ce contrefactuel. Cf. l'avertissement de la docstring.
                hit_interceptor=hit_interceptor,
                # #366-r1-crit-multihit : idem -- `isCriticalDamageAllowed` (`OngoingAttack+0x40`)
                # est repasse VERBATIM, jamais reconstruit. Il est REÇU et non CHAINE d'un groupe
                # a l'autre (le port livre, lui, chaine `r["crit_allowed"]`) : ce contrefactuel
                # passe `crit_enabled=False` ci-dessus, donc le canal crit y est structurellement
                # ferme et les deux formes sont indiscernables. Limite NOMMEE : un contrefactuel
                # qui ouvrirait le crit devrait chainer comme `execute_additional_hits`.
                crit_allowed0=crit_allowed0,
                failed_block0=failed_block,             # #407 : chaine (cf. ci-dessus)
                limits=AttackDamageOperation._target_limits(tgt, thc, g_profile, is_special=1),
                limits_hp=int(thc.hp or 0), is_attack_damage_op=is_attack_op)
            failed_block = r["failed_block"]
            # #1020-r1 : la depletion du bouclier vit desormais DANS `_apply_damage_pipeline`
            # (`ApplyDamageOperation$$ReduceShield` lit le pending RELU, apres `On(0x39)`).
            AttackDamageOperation._apply_damage_pipeline(
                state, target_id, attacker_id, tgt, thc, r["total"], g_profile,
                r["shield_dmg"], r["armor_dmg"], is_attack=False)
            out["groups"] += 1
            out["hits"] += max(0, int(g.get("count") or 0))
            out["total"] += r["total"]
            out["per_hit"] += r["per_hit"]
            out["rolls"] += r["rolls"]
            out["profiles"].append(g_profile)
        # #419-r6-r1 -- LES TROIS CLES D'ETAT D'ATTAQUE, que le port livre pose depuis #419-r3.
        #
        # Sans elles, `damage_hits.attack_state_out(r, ah)` -- appele par les DEUX vecteurs
        # (`damage_ops/normal.py`, `damage_ops/ability.py`) des que `ah` existe -- leve
        # `KeyError: 'next_hit_index'`. C'est la cause UNIQUE des 15 rouges des trois fichiers
        # `test_additional_hits_*_live.py`, mesures pre-existants par #419-r6 : un contrefactuel
        # qui n'expose pas le contrat de SORTIE du port qu'il remplace ne remplace pas ce port,
        # il le casse -- et l'echec accuse alors le moteur, pas le harnais.
        #
        # ⚠ Ce sont bien les valeurs de CE contrefactuel, pas des constantes : `next_hit_index`
        # avance de `hit_index0` par les coups reellement executes, `crit_allowed`/`failed_block`
        # sont ceux que la boucle a chaines. Poser des valeurs FIGEES ferait taire l'erreur en
        # introduisant une TROISIEME variable silencieuse -- exactement ce que l'en-tete interdit.
        out["next_hit_index"] = int(hit_index0 or 0) + int(out["hits"])
        out["crit_allowed"] = bool(crit_allowed0)
        out["failed_block"] = failed_block
        return out if out["groups"] else None
    return _exec


def _measure(rpc, args, *, caster_vis, target_vis, ability_id, module_path, label):
    """Corps COMMUN des deux montages live : build -> drive -> snapshot -> action live ->
    double rejeu offline (troncature / arrondi) -> confrontation per-coup."""
    from engine.entities.pathfinding.board import Board
    rows = []
    for seed in [s for s in args.seeds.split(",") if s]:
        rid, sf = _build(seed, caster_vis, target_vis,
                         extra=["--crit", "0,0", "--block-target", "0,0",
                                *(args.extra.split() if args.extra else [])],
                         rank=args.rank)
        if rid is None:
            continue
        try:
            bg = rpc("boardGraph", {"runnerId": rid}, 60)
            board = Board(bg["tiles"], adjacency="native_sym")
            if ability_id is None:
                cid, tid, moved = _drive_normal(rpc, rid, board, caster_vis, target_vis)
            else:
                cid, tid, moved = _drive_into_range(rpc, rid, board, caster_vis, target_vis,
                                                    ability_id)
            if cid is None:
                print("seed %s: drive KO" % seed)
                continue
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
            ob = rpc("observeBattle", {"runnerId": rid}, 60)
            snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
            rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
            if ability_id is None:
                cu = next((u for u in (dv.get("units") or []) if u.get("id") == cid), {})
                nrm = next((a for a in (cu.get("abilities") or []) if a.get("kind") == "normal"),
                           None)
                act = {"kind": "ability", "casterId": cid, "targetId": tid,
                       "abilityType": nrm["id"]}
            else:
                act = {"kind": "ability", "casterId": cid, "targetId": tid,
                       "abilityType": ability_id}
            res = rpc("applyAction", {"runnerId": rid, "action": act, "captureEvents": True}, 120)
            live, dirty = _live_amounts(res, tid, verbose=args.verbose)
            if not live:
                tgt_dv = next((u for u in (dv.get("units") or []) if u.get("id") == tid), {})
                print("[%s] AUCUN degat live sur tid=%s (%s hp=%s) action=%s -> res=%s"
                      % (label, tid, tgt_dv.get("visualId"), tgt_dv.get("hp"), act,
                         json.dumps(res)[:600]))
            off_f, dg = _replay(dv, ob, snap, board, rng0, cid, tid, ability_id, moved,
                                module_path, False)
            off_r, _ = _replay(dv, ob, snap, board, rng0, cid, tid, ability_id, moved,
                               module_path, True)
            for d in dg:
                print("[%s] etage: %s" % (label, d))
            print("[%s] seed %s: live=%s" % (label, seed, live))
            print("[%s]          floor=%s" % (label, off_f))
            print("[%s]          round=%s  dirty=%s" % (label, off_r, dirty))
            rows.append({"seed": seed, "live": live, "floor": off_f, "round": off_r,
                         "dirty": dirty})
        finally:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 20)
            except Exception:
                pass
            try:
                sf.unlink()
            except Exception:
                pass
    n_disc = sum(1 for r in rows if r["floor"] != r["round"])
    n_round = sum(1 for r in rows if r["round"] and _sub(r["round"], r["live"]))
    n_floor = sum(1 for r in rows if r["floor"] and _sub(r["floor"], r["live"]))
    print()
    print("[%s] BILAN : %d montages, %d DISCRIMINANTS ; live==arrondi %d/%d, "
          "live==troncature %d/%d" % (label, len(rows), n_disc, n_round, len(rows),
                                      n_floor, len(rows)))
    return 0


def _sub(off, live):
    """`off` est-il une SOUS-SEQUENCE contigue de `live` (les coups du vecteur vise sont noyes
    dans le flux d'events de l'action complete) ?"""
    if not off:
        return False
    n = len(off)
    return any(live[i:i + n] == off for i in range(0, max(1, len(live) - n + 1)))


def _drive_normal(rpc, rid, board, caster_vis, target_vis, max_turns=25):
    """Amene `caster_vis` au CONTACT hex de `target_vis` (attaque normale melee)."""
    from collections import deque
    my, moves = None, 0
    for _ in range(max_turns):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        units = dv.get("units") or []
        cst = next((u for u in units if u.get("visualId") == caster_vis and u.get("alive")), None)
        tg = next((u for u in units if u.get("visualId") == target_vis and u.get("alive")), None)
        if cst is None or tg is None:
            return None, None, 0
        if my is None:
            my = cst.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        cpos = (cst["pos"]["col"], cst["pos"]["row"])
        tpos = (tg["pos"]["col"], tg["pos"]["row"])
        ctile, ttile = board.id_at(*cpos), board.id_at(*tpos)
        if ctile in board.neighbours(ttile):
            return cst["id"], tg["id"], moves
        dist = {ttile: 0}
        q = deque([ttile])
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
        adj = [(t, cr) for t, cr in reach.items() if t in board.neighbours(ttile)]
        if adj:
            _t, (col, row) = sorted(adj)[0]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": cst["id"], "to": {"col": col, "row": row}}}, 60)
            return cst["id"], tg["id"], moves + 1
        pool = [t for t in reach if t in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        best = min(pool, key=lambda t: dist[t])
        col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cst["id"], "to": {"col": col, "row": row}}}, 60)
        moves += 1
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None, 0


def _case_ah_matrix(rpc, args):
    """DECOMPOSITION PAR ETAGE du canal `additional_hits` : rejoue le MEME coup sous les QUATRE
    combinaisons (ordre reduce/roll) x (materialisation floor/round) et dit laquelle reproduit le
    live. Un seul etage a la fois est donc responsable d'un mismatch."""
    from engine.entities.pathfinding.board import Board
    carrier = args.carrier or SQUIG_CARRIER
    for seed in [s for s in args.seeds.split(",") if s]:
        rid, sf = _build(seed, carrier, args.a_units,
                         extra=["--crit", "0,0", "--block-target", "0,0",
                                *(args.extra.split() if args.extra else [])], rank=args.rank)
        if rid is None:
            continue
        try:
            bg = rpc("boardGraph", {"runnerId": rid}, 60)
            board = Board(bg["tiles"], adjacency="native_sym")
            cid, tid, moved = _drive_normal(rpc, rid, board, carrier, args.target)
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
            print("[matrix] seed %s carrier=%s live=%s dirty=%s" % (seed, carrier, live, dirty))
            for order in ("reduce_then_roll", "roll_then_reduce"):
                for resolve in (True, False):
                    for fr in (False, True):
                        ph, dg = _replay(dv, ob, snap, board, rng0, cid, tid, None, moved,
                                         "engine.runner.operations.additional_hits", fr,
                                         ah_impl=additional_hits_variant(order, fr, is_attack_op=resolve))
                        arme = next((d.get("arme_per_hit") for d in dg if "arme_per_hit" in d),
                                    None)
                        print("  %-17s resolve=%-5s %-6s -> groupe=%s (arme=%s)"
                              % (order, resolve, "round" if fr else "floor", ph, arme))
        finally:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 20)
            except Exception:
                pass
            try:
                sf.unlink()
            except Exception:
                pass
    return 0


def _case_explore(rpc, args):
    rid, sf = _build(args.seed, args.p_units, args.a_units,
                     extra=(args.extra.split() if args.extra else None), rank=args.rank)
    if rid is None:
        return 1
    try:
        _dump_live(rpc, rid, "(build %s vs %s)" % (args.p_units, args.a_units))
        return 0
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
    ap.add_argument("--case", default="scan",
                    choices=("scan", "explore", "normal_like", "additional_hits", "ah_matrix"))
    ap.add_argument("--seed", default="777")
    ap.add_argument("--seeds", default="777,31337,4242,12345")
    ap.add_argument("--rank", type=int, default=None)
    ap.add_argument("--p-units", dest="p_units", default=DFA_CASTER)
    ap.add_argument("--a-units", dest="a_units", default="necroWarden")
    ap.add_argument("--target", default="necroWarden")
    ap.add_argument("--extra", default="", help="args rl_duel build supplementaires (espaces)")
    ap.add_argument("--verbose", action="store_true", help="detaille les events LIVE retenus")
    ap.add_argument("--carrier", default=None,
                    help="additional_hits: porteur du canal #179 (defaut tauCrisis)")
    ap.add_argument("--caster", default=None,
                    help="normal_like: caster du summon (defaut ultraInceptorSgt)")
    ap.add_argument("--ability", type=int, default=None,
                    help="normal_like: id de l'ability de summon (defaut 1003 DeathFromAbove)")
    args = ap.parse_args()

    if args.case == "scan":
        return _case_scan(None, args)
    rpc = _mkrpc()
    if args.case == "explore":
        return _case_explore(rpc, args)
    if args.case == "ah_matrix":
        return _case_ah_matrix(rpc, args)
    if args.case == "normal_like":
        return _measure(rpc, args, caster_vis=(args.caster or DFA_CASTER), target_vis=args.target,
                        ability_id=(args.ability or DFA_ABILITY),
                        module_path="engine.runner.operations.damage_ops.normal_like",
                        label="normal_like")
    return _measure(rpc, args, caster_vis=(args.carrier or AH_CARRIER), target_vis=args.target,
                    ability_id=None,
                    module_path="engine.runner.operations.additional_hits",
                    label="additional_hits")


if __name__ == "__main__":
    raise SystemExit(main())
