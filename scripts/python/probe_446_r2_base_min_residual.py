"""#446-r2 -- LOCALISATION PAR ETAGE du `+3` de degat ANTERIEUR au fold `Boltstorm`.

#446-r1 a mesure, sur un controle APPARIE (`MC1_67` / seed `41504`, caster `templAggressor` dont les
passifs sont retires -> attaque normale generique, AUCUN fold en jeu), une base NATIVE de
`1302..1950` contre `1299..1950` cote port sur la seule cible entouree, et un accord EXACT sur la
cible isolee. Soit `+1` par coup sur la seule borne MIN. Le meme `+1/coup` se retrouve au cran MELEE
et disparait sur `C2_02` : il depend du REGIME, pas de l'identite de la cible.

Ce probe ne recolle AUCUN scalaire. Il decompose la chaine native

    IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw
      -> IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64          (bornes de base)
      -> IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers
           -> IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor
                -> StaticBattleRules.Damage$$GetDamageWithPiercing               (percage/armure)
           -> IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers   (%-list)

etage par etage, sur un BALAYAGE (tuile de tir x cible) qui produit des DIZAINES de couples
natif/port depuis UN SEUL runner : chaque tuile change le regime de modifiers (elevation) et chaque
cible change armure/traits/HP. Un modele qui n'expliquerait qu'un point ne survit pas au balayage.

Usage :
    python scripts/python/probe_446_r2_base_min_residual.py --state-file <chemin ABSOLU>
    ... [--armor-target N] [--models] [--tiles N] [--runner R]

ASCII only.
"""
from __future__ import annotations

import argparse
import os
import sys
from fractions import Fraction

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import probe_124_line_elevation_decision as P124                 # noqa: E402
import probe_446_boltstorm_pair_term as P446                     # noqa: E402
from engine import battle_query as bq                            # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402
from engine.services import fix64 as _fx                         # noqa: E402

MontageError = P446.MontageError

# Le controle APPARIE de #446-r1 : les passifs du caster retires -> l'attaque normale redevient la
# generique `69`, donc AUCUN fold `Boltstorm_NormalAttackAbility$$PredictAttack` en jeu. La base est
# NUE, et c'est exactement l'etage que ce residu accuse.
STRIP_PASSIVES = ["--unit-stat", f"{P446.CASTER}:PassiveAbilities=[]"]


def build_args(armor_target: int | None, unit_stat: list | None = None) -> list:
    extra = list(P446.BUILD_ARGS) + STRIP_PASSIVES
    if armor_target is not None:
        extra += ["--armor-target", str(armor_target)]
    for spec in (unit_stat or []):
        extra += ["--unit-stat", spec]
    return extra


# --------------------------------------------------------------------------- montage

def stage(sid, rpc, rid: int) -> dict:
    """MEME geometrie construite que #446 (les unites sont DEPLACEES), mais SANS l'attestation du
    passif 1090 : ici il est justement RETIRE. Le reste des attestations est conserve."""
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    cid = next((u["id"] for u in mine if u.get("visualId") == P446.CASTER), None)
    if cid is None:
        raise MontageError(f"montage NON INSTALLE : {P446.CASTER} absent du roster")
    myplayer = mine[0].get("owner")
    vis_uid = {}
    for vis in P446.FOES:
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster adverse")
        vis_uid[vis] = u["id"]

    # ATTESTATION du controle : le passif DOIT avoir disparu de l'AbilitiesComponent. Sans elle, un
    # `--unit-stat` avale (typo, champ inconnu) laisserait le fold actif et la mesure porterait sur
    # une base qui n'est PAS nue -- exactement le residu qu'on cherche a exclure.
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": cid}, 60) or {}
    live_ids = [i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)]
    if P446.ABILITY in live_ids:
        raise MontageError(
            f"controle NON INSTALLE : le passif {P446.ABILITY} est TOUJOURS sur {P446.CASTER} "
            f"(triggered live = {sorted(set(live_ids))}) -- la base ne serait pas nue")

    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    lay = P446.find_layout(cells, elev)
    if lay is None:
        raise MontageError("montage NON INSTALLE : aucune configuration (C,T,N1,N2,F,F2,A)")
    ids = {"C": cid, "T": vis_uid[P446.T_CROWD], "N1": vis_uid[P446.NEAR1],
           "N2": vis_uid[P446.NEAR2], "F": vis_uid[P446.FAR], "A": vis_uid[P446.T_ALONE]}
    wanted = {ids[k]: lay[k] for k in ids}
    if not P124._drive_to(sid, rid, walk, elev, wanted):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"montage NON INSTALLE : placement incomplet -- voulu {wanted}, "
                           f"obtenu { {u: pos.get(u) for u in wanted} }")
    P124._give_turn_back(sid, rid, myplayer)
    _dv2, pos = P124._positions(sid, rid)
    P446.attest_layout(pos, ids, elev)
    dv, ctx = P446._fresh_ctx(rpc, rid, cid)
    ab = next(iter(ctx.normal_ids or ()), None)
    if ab is None:
        raise MontageError("montage NON INSTALLE : aucune attaque normale sur le caster")
    return {"rid": rid, "cid": cid, "myplayer": myplayer, "ids": ids, "ab": ab, "ctx": ctx,
            "dv": dv, "tile": lay["C"], "layout": lay, "walk": walk, "elev": elev,
            "wanted": wanted}


# --------------------------------------------------------------------------- etages

def native_event(rpc, rid, cid, tgt, ab, tile) -> dict | None:
    r = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                                  "abilityType": ab, "col": tile[0], "row": tile[1]}, 60) or {}
    if not r.get("ok"):
        return None
    evs = r.get("events") or []
    return next((e for e in evs if e.get("targetId") == tgt), evs[0] if evs else None)


def port_stage(ctx, tgt, tile) -> tuple:
    """Le port + ses ENTREES d'etage (`meta=True` : base, percage, armure, coups, %-list).

    ⚠ Le FOLD `Boltstorm` est NEUTRALISE ici : le controle apparie RETIRE le passif de l'unite
    LIVE (`--unit-stat PassiveAbilities=[]`), mais le dispatch du port lit le KIT gameconfig, pas
    l'AbilitiesComponent -- il folderait donc la ou le natif ne folde plus, et la comparaison ne
    porterait plus sur la meme chose. La neutralisation est LOCALE et RESTAUREE."""
    import engine.playbook.prediction.normal_attack as NA
    from engine.playbook.prediction import make_normal_attack_predictions
    saved = NA._RANGED_FOLLOWUP_PASSIVES
    NA._RANGED_FOLLOWUP_PASSIVES = ()
    try:
        out = make_normal_attack_predictions(ctx.scene, ctx.uid, tgt, tuple(tile), meta=True)
    finally:
        NA._RANGED_FOLLOWUP_PASSIVES = saved
    if out is None:
        return None, None
    ev, meta = out
    return ev, meta


def target_facts(ctx, uid) -> dict:
    """Ce que le port SAIT de la cible (armure, traits, effets, modifications de DEFENSE) -- la
    matiere qui distingue deux cibles a entrees d'etage par ailleurs identiques."""
    sc = ctx.scene
    tctx = sc.ctx(uid)
    stats = getattr(tctx, "stats", None) if tctx is not None else None
    dmods = None
    if stats is not None:
        d = getattr(stats, "defense", None)
        if d is not None:
            dmods = {"initial": getattr(d, "initial", None),
                     "current": d.get_current_value() if hasattr(d, "get_current_value") else None,
                     "per_source": dict(getattr(getattr(d, "modification", None),
                                                "per_source", {}) or {})}
    pos = sc.pos(uid)
    return {"pos": pos, "elev": (sc.elev_by_pos or {}).get(tuple(pos)) if pos else None,
            "armor": sc.armor(uid), "hp": sc.hp(uid), "shield": sc.shield(uid),
            "traits": sorted(getattr(tctx, "traits", None) or ()) if tctx is not None else None,
            "effects": sorted({getattr(e, "name", "?") for e in (sc.effects(uid) or [])}),
            "defense": dmods}


def port_mod_details(ctx, tgt, tile) -> list:
    """Les EffectBonus que le port accumule pour CETTE paire -- c'est ce qui dit si le `1.5` du
    port est l'ELEVATION ou la modification de stat DEFENSE (les deux valent 1.5)."""
    from engine.playbook.prediction._shared import (_add_positional_and_defender_mods,
                                                    _weapon_pierce)
    from engine.services.battle_query import are_tiles_adjacent
    from engine.services.damage_modifiers import DamageModifiers
    sc = ctx.scene
    t_pos = sc.pos(tgt)
    adj = are_tiles_adjacent(tuple(tile), t_pos, sc.board)
    import hexgeo
    _d = hexgeo.distance(tuple(tile), t_pos) if t_pos else None
    _p, _ranged, _wh, prof = _weapon_pierce(sc, ctx.uid, adj, _d)
    m = DamageModifiers()
    _add_positional_and_defender_mods(m, sc, ctx.uid, tgt, not _ranged, tuple(tile), t_pos,
                                      damage_profile=prof)
    return [(getattr(e, "kind", "?"), getattr(e, "value", None),
             getattr(e, "owner_is_caster", None)) for e in m.details]


def chain(base: int, pierce: int, armor: int, mults: list, hits: int, hit_mult: int = 1,
          mults_def: list | None = None) -> dict:
    """Re-joue la chaine PORT etage par etage, en gardant les Fix64 EXACTS (raw). Rend, PAR BORNE :
      `spread`   -- IdunBattle.Core.Services.DamageCalculations$$CalculateDamageSpread
      `base_mm`  -- IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64
      `pierced`  -- StaticBattleRules.Damage$$GetDamageWithPiercing (raw exact, fractionnaire)
      `modded`   -- IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers (raw, AVANT round)
      `out`      -- la borne materialisee, et sa VALEUR EXACTE en Fraction (pour lire la distance
                    au prochain entier : c'est ce qui dit si un `+1` est un ARRONDI ou une OPERATION)
    """
    from engine.services.damage_calculations import calculate_damage_spread
    from engine.services.damage_modifiers import (apply_pct_entries,
                                                  calculate_base_damage_with_modifiers)
    from engine.services.static_battle_rules import get_damage_with_piercing
    d = calculate_damage_spread(base, 20)
    lo_b, hi_b = base - d, base + d
    res = {"spread": d, "base_min": lo_b, "base_max": hi_b, "hits": hits}
    for name, b in (("min", lo_b), ("max", hi_b)):
        v = b
        for _ in range(max(1, hit_mult)):
            v = get_damage_with_piercing(v, pierce, armor)
        raw = _fx.from_number(v)
        res[f"pierced_{name}"] = raw
        res[f"exact_{name}"] = Fraction(raw, _fx.ONE)
        # LES QUATRE ETAPES de `CalculateBaseDamageWithAllModifiers`, dans l'ordre natif.
        x = apply_pct_entries(_fx.Fix64(raw), [(m, None) for m in mults])
        x = calculate_base_damage_with_modifiers(x)                             # Round ATTAQUANT
        res[f"after_att_{name}"] = Fraction(x.raw, _fx.ONE)
        x = apply_pct_entries(x, [(m, None) for m in (mults_def or [])])
        x = calculate_base_damage_with_modifiers(x)                             # Round DEFENSEUR
        res[f"out_{name}"] = _fx.to_int(_fx.round_raw(x.raw, 1))
    return res


def sweep(rpc, case: dict, tiles: list, targets: list) -> list:
    """Balayage (tuile de tir x cible). Chaque ligne porte les ENTREES d'etage du port ET les bornes
    natives -- c'est la matiere qui separe « arrondi » de « operation »."""
    ctx = case["ctx"]
    rows = []
    for tile in tiles:
        for key in targets:
            uid = case["ids"][key]
            nat = native_event(rpc, case["rid"], case["cid"], uid, case["ab"], tile)
            if nat is None:
                continue
            ev, meta = port_stage(ctx, uid, tile)
            if ev is None:
                continue
            f = ev.composite_fields()
            rows.append({
                "tile": tuple(tile), "target": key, "uid": uid,
                "nat_min": int(nat.get("willKillDmg") or 0),
                "nat_max": int(nat.get("mightKillDmg") or 0),
                "nat_hits": int(nat.get("appliedHits") or 0),
                "port_min": int(f.get("rawHealthDmgMin") or 0),
                "port_max": int(f.get("rawHealthDmgMax") or 0),
                "port_hits": int(f.get("appliedHits") or 0),
                "meta": meta})
    return rows


def mutants(rpc, case: dict, tiles: list, targets: list) -> list:
    """CONTRE-EPREUVES du fix. Le critere est le DEPLACEMENT du port par rapport au port NON MUTE,
    JAMAIS l'ecart au natif : un mutant INERTE laisserait `abs(port - natif)` a 0 sur les couples
    deja justes, ce qui se lirait comme une reussite. (Meme piege que #446/#446-r1.)

      `no_round_stages` -- les DEUX `CalculateBaseDamageWithModifiers` neutralises (identite) :
                           c'est EXACTEMENT le modele d'AVANT le fix sur ce montage.
      `drop_defender_face` -- la face DEFENSEUR (`pct_list_defender`) n'est plus consommee : prouve
                           que le champ neuf n'est pas un cul-de-sac (une entree qui n'irait nulle
                           part rendrait le meme resultat que la %-list fusionnee sur les couples
                           sans stat-mod, donc verte partout sauf a le tester).
    """
    import engine.services.damage_prediction as DP
    from engine.services import fix64 as fx
    ref = {}
    for t in tiles:
        for k in targets:
            ev, _m = port_stage(case["ctx"], case["ids"][k], t)
            if ev is not None:
                f = ev.composite_fields()
                ref[(tuple(t), k)] = (f.get("rawHealthDmgMin"), f.get("rawHealthDmgMax"))
    out = []
    for name in ("no_round_stages", "drop_defender_face"):
        saved_cbd = DP.calculate_base_damage_with_modifiers
        saved_pct = DP.apply_pct_entries
        try:
            if name == "no_round_stages":
                DP.calculate_base_damage_with_modifiers = (
                    lambda d, m=1.0: fx.Fix64(fx.mul(fx.from_number(d), fx.mult_raw_from_float(m))))
            else:
                DP.apply_pct_entries = lambda v, entries: fx.Fix64(fx.from_number(v))
            moved = 0
            worst = None
            for key, base in ref.items():
                ev, _m = port_stage(case["ctx"], case["ids"][key[1]], key[0])
                if ev is None:
                    continue
                f = ev.composite_fields()
                got = (f.get("rawHealthDmgMin"), f.get("rawHealthDmgMax"))
                if got != base:
                    moved += 1
                    d = (got[0] - base[0], got[1] - base[1])
                    if worst is None or abs(d[0]) + abs(d[1]) > abs(worst[1][0]) + abs(worst[1][1]):
                        worst = (key, d)
        finally:
            DP.calculate_base_damage_with_modifiers = saved_cbd
            DP.apply_pct_entries = saved_pct
        out.append({"mutant": name, "moved": moved, "total": len(ref), "worst": worst})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du state-file")
    ap.add_argument("--runner", type=int, default=None, help="reutilise un runner deja monte")
    ap.add_argument("--armor-target", type=int, default=None,
                    help="force Armor+FixedArmor de TOUTES les cibles (balayage de l'etage armure)")
    ap.add_argument("--tiles", type=int, default=6,
                    help="nombre de tuiles de tir balayees (defaut 6)")
    ap.add_argument("--targets", default="T,A,N1,N2,F")
    ap.add_argument("--mutants", action="store_true",
                    help="joue les contre-epreuves du fix (chacune doit DEPLACER le port)")
    ap.add_argument("--unit-stat", action="append", default=None,
                    help="ABLATION : patch supplementaire de BC.Units (repetable), transmis a "
                         "`rl_duel build` -- ex. 'astraBullgryn:Traits=[\"Hero\"]'")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = args.runner if args.runner else P446._build(
        args.state_file, build_args(args.armor_target, args.unit_stat))
    case = stage(sid, rpc, rid)
    ctx = case["ctx"]
    lay = case["layout"]
    print(f"runner {rid} | caster u{case['cid']} @ {lay['C']} | normale {case['ab']} "
          f"| armor-target={args.armor_target}")
    print(f"  layout T={lay['T']} N1={lay['N1']} N2={lay['N2']} F={lay['F']} A={lay['A']}")

    # tuiles de tir : celles de l'oracle (action_tiles), la tuile de montage EN TETE.
    at = [tuple(t) for t in (ctx.action_tiles or []) if t and t[0] is not None]
    tiles = [tuple(lay["C"])] + [t for t in at if tuple(t) != tuple(lay["C"])]
    tiles = tiles[:max(1, args.tiles)]
    targets = [k for k in args.targets.split(",") if k in case["ids"] and k != "C"]

    for key in targets:
        uid = case["ids"][key]
        print(f"  FACTS[{key}] u{uid} {target_facts(ctx, uid)}")
        # GROUND TRUTH NATIVE des modifications de stat de la cible : c'est la SEULE voie qui
        # alimente `IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications`
        # (face DEFENSEUR, negate=1), donc une entree %-list que le port pourrait ne pas voir.
        sms = rpc("statModSources", {"runnerId": case["rid"], "unitId": uid,
                                     "stats": ["defense", "attack", "armor"], "minAbs": 0}, 120) or {}
        if sms.get("ok"):
            for u in (sms.get("units") or []):
                if u.get("mods"):
                    print(f"    statModSources u{u.get('entityId')}: {u.get('mods')}")
        else:
            print(f"    statModSources KO: {sms.get('error')}")
        print(f"    port EffectBonus @ {tuple(lay['C'])}: {port_mod_details(ctx, uid, lay['C'])}")
    print(f"  elev caster {tuple(lay['C'])} = {(ctx.scene.elev_by_pos or {}).get(tuple(lay['C']))}")

    rows = sweep(rpc, case, tiles, targets)
    n_bad = 0
    for r in rows:
        if r["nat_hits"] <= 1 and r["nat_min"] == 0 and r["nat_max"] == 0:
            continue          # cible hors portee depuis cette tuile : le natif rend une prediction NULLE
        m = r["meta"] or {}
        dmin = r["port_min"] - r["nat_min"]
        dmax = r["port_max"] - r["nat_max"]
        dh = r["port_hits"] - r["nat_hits"]
        tag = "OK  " if (dmin == 0 and dmax == 0 and dh == 0) else "DIFF"
        if tag == "DIFF":
            n_bad += 1
        ch = chain(int(m.get("base") or 0), int(m.get("pierce") or 0), int(m.get("armor") or 0),
                   list(m.get("mods") or []), int(r["port_hits"] or 1),
                   mults_def=list(m.get("mods_def") or []))
        e_lo, e_hi = ch["exact_min"], ch["exact_max"]
        print(f"  [{tag}] tile={r['tile']} {r['target']} u{r['uid']} "
              f"nat=({r['nat_min']},{r['nat_max']},{r['nat_hits']}) "
              f"port=({r['port_min']},{r['port_max']},{r['port_hits']}) "
              f"d=({dmin:+d},{dmax:+d},{dh:+d})")
        print(f"        base={m.get('base')} pierce={m.get('pierce')} armor={m.get('armor')} "
              f"hits={m.get('hits')} modsATT={m.get('mods')} modsDEF={m.get('mods_def')} "
              f"detail={m.get('mods_detail')} "
              f"baseMM=({ch['base_min']},{ch['base_max']}) spread={ch['spread']}")
        print(f"        percage EXACT min={float(e_lo):.8f} max={float(e_hi):.8f} "
              f"| apres face ATT min={float(ch['after_att_min']):.4f} "
              f"max={float(ch['after_att_max']):.4f} "
              f"-> port/coup=({ch['out_min']},{ch['out_max']}) "
              f"nat/coup=({r['nat_min'] / max(1, r['nat_hits']):.4f},"
              f"{r['nat_max'] / max(1, r['nat_hits']):.4f})")
    print(f"  TOTAL {len(rows)} couples, {n_bad} DIFF")
    if args.mutants:
        for mt in mutants(rpc, case, tiles, targets):
            print(f"  [mutant {mt['mutant']:<19}] DEPLACE {mt['moved']}/{mt['total']} couples "
                  f"(pire {mt['worst']}) ({'MORD' if mt['moved'] else 'NE MORD PAS'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
