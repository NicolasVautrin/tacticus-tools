"""R6-c -- BORNES COMBAT des groupes `amount` RESTANTS du canal COUPS ADDITIONNELS (#179).

QUESTION (binaire, DEUX axes) : un groupe de coups additionnels en mode `amount` tire-t-il, en
COMBAT, dans les MEMES BORNES que le natif, et consomme-t-il le MEME NOMBRE de tirages ?

RE (decompile = verite, gqfc5mff6c). `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create`
range DEUX noeuds de degat, lu verbatim :

    param_1[1] = param_3                          # +0x08  noeud ROLL
    if (param_8 != 0) param_3 = param_8;
    param_1[2] = param_3                          # +0x10  noeud DISPLAY (repli = ROLL)

et `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits(this, entities, useDisplay)` :

    amount = displayNode.<slot 4>(entities)                       # toujours
    min = max = amount
    if (!useDisplay) { min = rollNode.<slot 2>; max = rollNode.<slot 3>; }   # FACE COMBAT

DEUX FORMES DISTINCTES, qui ne se generalisent PAS l'une a l'autre :

  (1) `CyclicIonBlaster_AdditionalHitsEffect$$CreateAdditionalHits` (tauCrisis) -- noeuds
      DISTINCTS :
        ROLL    = ConditionalAmount(cond, RandomAmount(Sum(minDmg,extraDmg), Sum(maxDmg,extraDmg)),
                                          RandomAmount(minDmg, maxDmg))
        DISPLAY = ConditionalAmount(cond, Sum(minDmg,extraDmg), minDmg)
        cond    = HasEffect(target@0x178, 0x462 Markerlight, 1, 6) | HasTrait(target@0x178, 5 Mechanical)
      => la face COMBAT tire dans [minDmg, maxDmg] (+extraDmg sur LES DEUX bornes si `cond`), la ou
      le port etalait `amount` (= le MIN) a +-20 %. Axe VALEUR.

  (2) `ExplosiveMaladies_ExtraRangedAttackEffect$$CreateAdditionalHits` (deathPutrifier) et
      `FoulInfusion_ExtraHitsEffect$$CreateAdditionalHits` -- noeud UNIQUE et SCALAIRE
      (`ConfigVar(8)` / `ConfigVar(0xb)`, `param_8 = 0`). La face COMBAT lit slot 2 ET slot 3 du
      MEME `IdunBattle.Entities.Formulas.ConfigAmount` => cellule DEGENEREE [v, v], et
      `IdunBattle.Core.HitDamage$$GetDamage` ouvre sur `if (*param_1 == param_1[1]) return *param_1;`
      => **0 tirage** la ou le port en consommait 1. Axe CONSOMMATION -- la valeur seule ne
      discrimine pas (le tirage +-20 % peut tomber sur v par hasard), le delta `mti` si.

MONTAGES (les deux modeles doivent predire des choses DIFFERENTES, et differemment) :

  --case cyclic --target astraCreed     cond FAUX : ROLL [599,898]   vs display 599 +-20 % [479,719]
  --case cyclic --target admecMarshall  cond VRAI : ROLL [1198,1497] vs display 1198 +-20 % [958,1437]

  Le renversement est le point : en cond FAUX la plage ROLL est PLUS LARGE que le contrefactuel
  (299 vs 240), en cond VRAI elle est PLUS ETROITE (299 vs 479). Un facteur d'ajustement cale sur
  l'un se trahit sur l'autre. `astraCreed` n'a AUCUN trait (hors Hero) et `admecMarshall` n'a que
  Mechanical : rien d'autre ne bouge entre les deux montages.

  --case maladies   deathPutrifier (porteur du passif) + un ami RANGED amene ADJACENT (le selecteur
  natif est `AdjacentFriends(owner, 1)`) ; verdict = delta de tirages entre deux `dumpRng`.

Discipline runner : state-file ABSOLU sous logs/, `--board` explicite, dispose en fin.
ASCII only (cp1252).

CLI (depuis scripts/python) :
  python probe_r6c_ah_bounds.py --case cyclic --target astraCreed    --seeds 777,12345,314159
  python probe_r6c_ah_bounds.py --case cyclic --target admecMarshall --seeds 777,12345,314159
  python probe_r6c_ah_bounds.py --case maladies --seeds 777,12345
"""
from __future__ import annotations

import argparse
import json
import sys

import hexgeo

from probe_r6_round_materialize import _build, _live_amounts, _mkrpc   # noqa: F401
from probe_159_ah_bounds import _board, _genrand_steps, _pos, _unit    # noqa: F401

BOARD = "MC1_67"
CYCLIC_CARRIER = "tauCrisis"          # passif CyclicIonBlaster (effet 0x47c = 1148)
MALADIES_CARRIER = "deathPutrifier"   # passif ExplosiveMaladies (aura hostee SUR LE PORTEUR)
MALADIES_ALLY = "admecMarshall"       # ami RANGED (Range 2, 1 coup) ; `Mechanical` est un trait de
#                                       CIBLE -> inerte quand l'unite est l'ATTAQUANT. Le selecteur
#                                       RANGED d'ExplosiveMaladies n'a AUCUN gate d'alliance.


# --------------------------------------------------------------------------- drive


def _normal(u):
    return next((a for a in (u.get("abilities") or []) if a.get("kind") == "normal"), None)


def _legal(rpc, rid, caster, ability_id, target_id):
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster["id"],
                                "abilityType": ability_id}, 120)
    ab = next((x for u in (at.get("units") or []) for x in (u.get("abilities") or [])
               if x.get("abilityId") == ability_id), {})
    return target_id in [x.get("targetId") for x in (ab.get("fromHere") or [])]


def _reachable(rpc, rid, unit_id):
    mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
    cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == unit_id), None)
    return [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])]


def _drive_attack(rpc, rid, carrier_vis, target_vis, max_turns=30):
    """Amene `carrier_vis` a un tour ou son attaque normale est LEGALE sur `target_vis`. Rend
    `(caster_id, target_id, ability_id, moved)`. `moved` est rejoue offline (`set_moved_flag`)."""
    my, moved = None, 0
    for _ in range(max_turns):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        cst, tg = _unit(dv, carrier_vis), _unit(dv, target_vis)
        if cst is None or tg is None:
            return None, None, None, 0, "caster/cible absent"
        if my is None:
            my = cst.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            moved = 0        # `UnitFlag.Moved` est PER-TOUR
            continue
        nrm = _normal(cst)
        if nrm is None:
            return None, None, None, 0, "attaque normale introuvable"
        if _legal(rpc, rid, cst, nrm["id"], tg["id"]):
            return cst["id"], tg["id"], nrm["id"], moved, None
        tpos = _pos(tg)
        pool = _reachable(rpc, rid, cst["id"])
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            moved = 0
            continue
        col, row = min(pool, key=lambda t: hexgeo.distance(t, tpos))
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cst["id"], "to": {"col": col, "row": row}}}, 60)
        moved += 1
    return None, None, None, 0, "portee non atteinte en %d tours" % max_turns


def _drive_aura_attack(rpc, rid, owner_vis, ally_vis, target_vis, max_turns=30, trace=False):
    """Monte la configuration d'AURA d'ExplosiveMaladies : le PORTEUR (`owner_vis`) amene ADJACENT
    a l'ALLIE (`ally_vis`), qui attaque `target_vis`. On DEPLACE les deux pour forcer la
    configuration -- l'adjacence natif est re-evaluee a la tuile candidate au moment de l'attaque
    (`GetRefreshTriggers` = PreAttack(5)), donc c'est la position A L'ATTAQUE qui compte."""
    my, moved = None, 0
    for _it in range(max_turns):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        own, ally, tg = _unit(dv, owner_vis), _unit(dv, ally_vis), _unit(dv, target_vis)
        if trace and own is not None and ally is not None and tg is not None:
            print("   [drive %02d] cur=%s my=%s ally=%s owner=%s tgt=%s d(a,t)=%s d(a,o)=%s"
                  % (_it, dv.get("currentPlayer"), my, _pos(ally), _pos(own), _pos(tg),
                     hexgeo.distance(_pos(ally), _pos(tg)),
                     hexgeo.distance(_pos(ally), _pos(own))))
        if own is None or ally is None or tg is None:
            return None, None, None, None, 0, "owner/ally/cible absent"
        if my is None:
            my = ally.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            moved = 0
            continue
        nrm = _normal(ally)
        if nrm is None:
            return None, None, None, None, 0, "attaque normale de l'allie introuvable"
        apos, opos, tpos = _pos(ally), _pos(own), _pos(tg)
        # `IsRangedAttack` du trigger : l'attaque doit etre a DISTANCE (>= 2), pas au contact.
        if (hexgeo.distance(apos, opos) == 1 and hexgeo.distance(apos, tpos) >= 2
                and _legal(rpc, rid, ally, nrm["id"], tg["id"])):
            return ally["id"], own["id"], tg["id"], nrm["id"], moved, None
        # Les deux avancent DE CONCERT (une action de mouvement chacun par tour) : le PORTEUR
        # d'abord vers la cible en restant a >= 2, puis l'ALLIE se recolle a lui. Faire courir
        # l'allie seul le SEPARE definitivement du porteur (portee de mouvement bornee) -- c'est
        # ce que la trace du premier montage a montre (allie (4,7) / porteur (1,0), d=9).
        pown = [t for t in _reachable(rpc, rid, own["id"]) if hexgeo.distance(t, tpos) >= 2]
        if pown:
            best = min(pown, key=lambda t: hexgeo.distance(t, tpos))
            if hexgeo.distance(best, tpos) < hexgeo.distance(opos, tpos):
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": own["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
                opos = best
        pally = [t for t in _reachable(rpc, rid, ally["id"])
                 if hexgeo.distance(t, opos) == 1 and hexgeo.distance(t, tpos) >= 2]
        if pally:
            best = min(pally, key=lambda t: hexgeo.distance(t, tpos))
            if best != apos:
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": ally["id"],
                    "to": {"col": best[0], "row": best[1]}}}, 60)
                moved += 1
                apos = best
        if (hexgeo.distance(apos, opos) == 1 and hexgeo.distance(apos, tpos) >= 2
                and _legal(rpc, rid, ally, nrm["id"], tg["id"])):
            return ally["id"], own["id"], tg["id"], nrm["id"], moved, None
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        moved = 0
    return None, None, None, None, 0, "configuration d'aura non montee en %d tours" % max_turns


FOUL_ABILITY = 1038          # ActiveAbilityType.FoulInfusion
FOUL_EFFECT = 1074           # EffectType.FoulInfusion_ExtraHits (0x432)


def _drive_foul_melee(rpc, rid, carrier_vis, target_vis, max_turns=30, trace=False):
    """`FoulInfusion` : le PORTEUR caste 1038 (l'effet 1074 se pose sur lui), puis attaque en
    MELEE au tour suivant (trigger `IsMeleeAttack & OwnerIsCaster`). deathPutrifier n'a qu'une
    arme sans `Range` -> toute attaque normale est mélée."""
    my, moved = None, 0
    for _it in range(max_turns):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        cst, tg = _unit(dv, carrier_vis), _unit(dv, target_vis)
        if cst is None or tg is None:
            return None, None, None, 0, "caster/cible absent"
        if my is None:
            my = cst.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            moved = 0
            continue
        has = FOUL_EFFECT in {e.get("effectType") for e in (cst.get("effects") or ())}
        cpos, tpos = _pos(cst), _pos(tg)
        if trace:
            print("   [drive %02d] cur=%s cst=%s tgt=%s d=%s effet1074=%s"
                  % (_it, dv.get("currentPlayer"), cpos, tpos, hexgeo.distance(cpos, tpos), has))
        if not has:                      # 1) poser l'effet
            ab = next((a for a in (cst.get("abilities") or [])
                       if a.get("id") == FOUL_ABILITY), None)
            if ab is None:
                return None, None, None, 0, "ability FoulInfusion (1038) absente du kit"
            at = rpc("abilityTargets", {"runnerId": rid, "unitId": cst["id"],
                                        "abilityType": FOUL_ABILITY}, 120)
            cand = [x.get("targetId") for u in (at.get("units") or [])
                    for a2 in (u.get("abilities") or []) if a2.get("abilityId") == FOUL_ABILITY
                    for x in (a2.get("fromHere") or [])]
            if not cand:
                return None, None, None, 0, "aucune cible legale pour FoulInfusion"
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": cst["id"], "targetId": cand[0],
                "abilityType": FOUL_ABILITY}}, 120)
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            moved = 0
            continue
        nrm = _normal(cst)
        if nrm is None:
            return None, None, None, 0, "attaque normale introuvable"
        if hexgeo.distance(cpos, tpos) == 1 and _legal(rpc, rid, cst, nrm["id"], tg["id"]):
            return cst["id"], tg["id"], nrm["id"], moved, None
        pool = [t for t in _reachable(rpc, rid, cst["id"])]
        if pool:
            best = min(pool, key=lambda t: hexgeo.distance(t, tpos))
            if best != cpos:
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": cst["id"],
                    "to": {"col": best[0], "row": best[1]}}}, 60)
                moved += 1
                continue
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        moved = 0
    return None, None, None, 0, "melee FoulInfusion non montee en %d tours" % max_turns


# --------------------------------------------------------------------------- offline


def _cyclic_variant(mode):
    """Modele de bornes pour `CyclicIonBlasterAdditionalHitsEffect` :
      `display` = port HISTORIQUE (`amount` seul -> spread +-20 % du pipeline) ;
      `roll`    = lecture native (`min`/`max` du noeud ROLL, cf. en-tete)."""
    from engine.entities.effects.magnitude import ability_var

    def _groups(self, ctx=None):
        lvl = self.ability_level if self.ability_level is not None else self.level
        mn = ability_var("CyclicIonBlaster", "minDmg", lvl,
                         multiplier_pct=self.ability_variables_multiplier)
        mx = ability_var("CyclicIonBlaster", "maxDmg", lvl,
                         multiplier_pct=self.ability_variables_multiplier)
        count = ability_var("CyclicIonBlaster", "nrOfHits", is_constant=True)
        if mn is None or mx is None or not count or count <= 0:
            return None
        c = ctx or {}
        extra = 0
        if ("Markerlight" in (c.get("tgt_effect_names") or ()) or
                "Mechanical" in (c.get("tgt_traits") or ())):
            extra = int(ability_var("CyclicIonBlaster", "extraDmg", lvl,
                                    multiplier_pct=self.ability_variables_multiplier) or 0)
        import gameconfig as _GC
        profile = ((_GC.ability("CyclicIonBlaster") or {}).get("constants") or {}) \
            .get("damageProfile") or "Particle"
        g = {"count": int(count), "amount": int(mn) + extra, "profile": profile}
        if mode == "roll":
            g["min"], g["max"] = int(mn) + extra, int(mx) + extra
        return [g]
    return _groups


def _scalar_variant(cls, attr):
    """Modele de bornes des descripteurs a noeud SCALAIRE UNIQUE (`ExplosiveMaladies`,
    `FoulInfusion`) :
      `display`    = port HISTORIQUE (`amount` seul -> spread +-20 %, 1 tirage `GetDamage`) ;
      `degenerate` = lecture native (`param_8 == 0` -> DISPLAY == ROLL == `ConfigAmount` scalaire
                     -> [v, v], et `HitDamage$$GetDamage` court-circuite -> 0 tirage).
    Le contrefactuel se fabrique en RETIRANT `min`/`max` du groupe LIVRE : on ne re-derive rien,
    donc on ne peut pas se tromper de valeur en construisant l'adversaire."""
    orig = getattr(cls, attr)

    def _make(mode):
        def _wrapped(self, *a, **kw):
            g = orig(self, *a, **kw)
            if g is None:
                return None
            if isinstance(g, list):
                out = [dict(x) for x in g]
            else:
                out = [dict(g)]
            if mode == "display":
                for x in out:
                    x.pop("min", None)
                    x.pop("max", None)
            return out if isinstance(g, list) else out[0]
        return _wrapped
    return _make


def _replay(dv, ob, snap, board, rng0, cid, tid, moved, case):
    """Rejoue la MEME attaque OFFLINE sur le MEME flux RNG sous les deux modeles de bornes, et
    compte les `genrand_int32` consommes (meme unite que `_genrand_steps` cote natif)."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import set_moved_flag
    from engine.runner.operations import additional_hits as _ah_mod
    from engine.runner.operations.damage_ops import normal as _dnormal
    from engine.runner.operations.damage_ops import ability as _dability
    from engine.entities.effects.loki.hits import (CyclicIonBlasterAdditionalHitsEffect as _CIB,
                                                   _ExplosiveMaladiesAuraHitsBase as _EM,
                                                   FoulInfusionExtraHitsEffect as _FI)
    # (classe, attribut) patche par le contrefactuel, et fabrique du modele alternatif
    _cls, _attr = {"cyclic": (_CIB, "additional_hit_groups"),
                   "maladies": (_EM, "create_aura_additional_hits_for_ally"),
                   "foul": (_FI, "additional_hit_groups")}[case]

    def _one(impl):
        st = load_state(dv, ob, snap, board=board)
        if moved:
            set_moved_flag(st, cid)
        cnt = [0]

        class _Counting(IntBasedMersenneTwister):
            __slots__ = ()

            def genrand_int32(self):
                cnt[0] += 1
                return IntBasedMersenneTwister.genrand_int32(self)

        rng = _Counting()
        rng.mt = list(rng0["mt"])
        rng.mti = rng0["mti"]
        st.rng = rng
        grp, bounds = [], []
        o_ah = _ah_mod.execute_additional_hits
        o_n, o_a = _dnormal.execute_additional_hits, _dability.execute_additional_hits
        o_cls = getattr(_cls, _attr)

        def _rec(*a, **kw):
            for g in (a[5] if len(a) > 5 else kw.get("groups")) or ():
                bounds.append({k: g.get(k) for k in ("count", "min", "max", "amount", "profile")})
            out = o_ah(*a, **kw)
            if out:
                grp.extend(out.get("per_hit") or [])
            return out

        _ah_mod.execute_additional_hits = _rec
        _dnormal.execute_additional_hits = _rec
        _dability.execute_additional_hits = _rec
        if impl is not None:
            setattr(_cls, _attr, impl)
        try:
            runner = Runner(st).install_default_handlers(20)
            runner.apply(AttackUnitMessage(cid, tid))
            last = getattr(getattr(runner, "damage_handler", None), "last", None)
            arme = list((last or {}).get("per_hit") or []) if isinstance(last, dict) else []
            return arme, grp, bounds, cnt[0]
        finally:
            _ah_mod.execute_additional_hits = o_ah
            _dnormal.execute_additional_hits = o_n
            _dability.execute_additional_hits = o_a
            setattr(_cls, _attr, o_cls)

    alt = _cyclic_variant if case == "cyclic" else _scalar_variant(_cls, _attr)
    native_mode = "roll" if case == "cyclic" else "degenerate"
    return {"shipped": _one(None),
            "display": _one(alt("display")),
            "native": _one(alt(native_mode))}


# --------------------------------------------------------------------------- run


def _run_seed(rpc, seed, args):
    if args.case == "cyclic":
        p_units, a_units = CYCLIC_CARRIER, args.target
    elif args.case == "foul":
        p_units, a_units = MALADIES_CARRIER, args.target      # le PORTEUR attaque lui-meme
    else:
        p_units, a_units = "%s,%s" % (MALADIES_CARRIER, MALADIES_ALLY), args.target
    rid, sf = _build(seed, p_units, a_units,
                     extra=["--crit", "0,0", "--block-target", "0,0",
                            "--hp-target", str(args.hp), "--armor-target", str(args.armor)],
                     rank=args.rank)
    if rid is None:
        return None
    try:
        if args.case == "cyclic":
            cid, tid, aid, moved, err = _drive_attack(rpc, rid, CYCLIC_CARRIER, args.target,
                                                      max_turns=args.max_turns)
            oid = None
        elif args.case == "foul":
            cid, tid, aid, moved, err = _drive_foul_melee(
                rpc, rid, MALADIES_CARRIER, args.target,
                max_turns=args.max_turns, trace=args.verbose)
            oid = None
        else:
            cid, oid, tid, aid, moved, err = _drive_aura_attack(
                rpc, rid, MALADIES_CARRIER, MALADIES_ALLY, args.target,
                max_turns=args.max_turns, trace=args.verbose)
        if cid is None:
            print("[r6c] seed %s: drive KO -- %s" % (seed, err))
            return None
        board = _board(rpc, rid)
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": aid},
            "captureEvents": True}, 120)
        rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
        n_native = _genrand_steps(rng0, rng1)
        # `tags.Target_Id` n'est PAS l'`id` de `decisionView` (referentiels distincts : mesure de
        # ce probe -- dv id=77 vs Target_Id=93 sur le meme montage 1v1, valeurs bit-exactes cote
        # offline). On s'appuie donc sur l'UNICITE de la cible endommagee, garantie par le montage
        # (1 attaquant, 1 cible), et on REFUSE le montage si plusieurs cibles ont pris des degats.
        rows = []
        for act in (res.get("actions") or []):
            for e in (act.get("events") or []):
                td = e.get("tags")
                td = json.loads(td) if isinstance(td, str) else (td or {})
                if "Amount" in td:
                    rows.append(td)
        hit_ids = {td.get("Target_Id") for td in rows}
        if len(hit_ids) != 1:
            print("[r6c] seed %s: %d cibles endommagees %s -- montage AMBIGU, ignore"
                  % (seed, len(hit_ids), sorted(x for x in hit_ids if x is not None)))
            return None
        live = [int(td["Amount"]) for td in rows]
        dirty = any(td.get("Attack_DidCrit") or td.get("Attack_DidBlock")
                    or td.get("Attack_DidEvade") for td in rows)
        profiles = [td.get("DamageProfileType") for td in rows]
        if args.verbose:
            for td in rows:
                print("   live event: %s" % {k: v for k, v in td.items()
                                             if k in ("Amount", "Target_Id", "Source_Id",
                                                      "Effect_Type", "DamageProfileType",
                                                      "Attack_DidCrit", "Attack_DidBlock")})
        if dirty:
            print("[r6c] seed %s: coup SALE (crit/block/evade) -- ignore" % seed)
            return None
        off = _replay(dv, ob, snap, board, rng0, cid, tid, moved, args.case)
        # Diagnostic d'un desalignement de VALEUR du coup d'ARME (orthogonal au canal #179 tant que
        # le FLUX reste aligne) : on expose les effets portes par l'attaquant et sa stat Damage,
        # pour que le residu soit NOMME et pas seulement constate.
        cst_dv = next((u for u in (dv.get("units") or []) if u.get("id") == cid), None)
        diag = {"effects": [(e.get("effectType"), e.get("name"))
                            for e in ((cst_dv or {}).get("effects") or ())],
                "damage": (cst_dv or {}).get("damage"),
                "attack": (cst_dv or {}).get("attack")}
        return {"seed": seed, "live": live, "profiles": profiles, "off": off, "moved": moved,
                "n_native": n_native, "owner": oid, "diag": diag}
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
    ap.add_argument("--case", default="cyclic", choices=("cyclic", "maladies", "foul"))
    ap.add_argument("--seeds", default="777,12345,314159")
    ap.add_argument("--target", default="astraCreed")
    ap.add_argument("--rank", type=int, default=None)
    ap.add_argument("--hp", type=int, default=90000)
    ap.add_argument("--armor", type=int, default=6000)
    ap.add_argument("--max-turns", dest="max_turns", type=int, default=30)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    rpc = _mkrpc()
    n = m_ship = m_disp = m_nat = disc = 0
    n_arme_ok = c_nat = c_disp = 0
    for seed in [s for s in args.seeds.split(",") if s.strip()]:
        row = _run_seed(rpc, seed, args)
        if row is None:
            continue
        n += 1
        live, off = row["live"], row["off"]
        arme_s, grp_s, bnd_s, n_s = off["shipped"]
        _a_d, grp_d, bnd_d, n_d = off["display"]
        _a_r, grp_r, bnd_r, n_r = off["native"]
        k = len(arme_s)
        grp_live = live[k:k + len(grp_r or grp_s or ())]
        print("[r6c %s/%s] seed %s moved=%d" % (args.case, args.target, seed, row["moved"]))
        print("   genrand NATIF=%s | offline shipped=%d display=%d native-model=%d"
              % (row["n_native"], n_s, n_d, n_r))
        print("   live            = %s   (profils %s)" % (live, row["profiles"]))
        print("   arme offline    = %s -> groupe live = %s" % (arme_s, grp_live))
        print("   bornes port     = %s" % (bnd_s,))
        print("   bornes DISPLAY  = %s" % (bnd_d,))
        print("   bornes NATIVES  = %s" % (bnd_r,))
        print("   groupe SHIPPED  = %s" % (grp_s,))
        print("   groupe DISPLAY  = %s   (contrefactuel amount +-20%%)" % (grp_d,))
        print("   groupe NATIF    = %s" % (grp_r,))
        if live[:k] != arme_s:
            print("   [!] coups d'ARME desalignes live=%s offline=%s" % (live[:k], arme_s))
            print("   [!] attaquant : %s" % (row["diag"],))
        else:
            n_arme_ok += 1
        m_ship += int(bool(grp_live) and grp_s == grp_live)
        m_disp += int(bool(grp_live) and grp_d == grp_live)
        m_nat += int(bool(grp_live) and grp_r == grp_live)
        disc += int(grp_r != grp_d)
        if row["n_native"] and row["n_native"] > 0:
            c_nat += int(n_r == row["n_native"])
            c_disp += int(n_d == row["n_native"])
    print()
    print("[r6c %s/%s] BILAN %d montages : ARME alignee %d/%d | groupe SHIPPED %d/%d | "
          "DISPLAY %d/%d | NATIF %d/%d | discriminants %d/%d"
          % (args.case, args.target, n, n_arme_ok, n, m_ship, n, m_disp, n, m_nat, n, disc, n))
    print("[r6c %s/%s] CONSO (genrand) : modele NATIF %d/%d | modele DISPLAY %d/%d"
          % (args.case, args.target, c_nat, n, c_disp, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
