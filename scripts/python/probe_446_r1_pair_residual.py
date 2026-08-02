"""#446-r1 -- LOCALISATION PAR ETAGE de l'ecart residuel port/natif de la paire mesuree par #446.

#446 a mesure, sur `templAggressor` (board `MC1_67`, seed `41504`), un ecart CONSTANT entre le
`pairUtility` natif et le port : -4.159792 sur la cible ENTOUREE, -5.639718 sur la cible ISOLEE.
Cet ecart est INVARIANT aux trois crans du balayage du cardinal `Boltstorm` (1090), donc ORTHOGONAL
a cette tranche, et il DIFFERE PAR CIBLE, donc composite de DEGAT et non forfait.

Ce probe ne cherche PAS a recoller un scalaire : il DECOMPOSE la paire en deux etages et dit lequel
diverge.

    ETAGE 1 -- PREDICTION : `aiPlaybookPredict` natif (les `ProbableDamageEvent` que le playbook
               natif construit) contre `NormalAttackPlaybook.make_damage_predictions` du port,
               champ par champ (`_pred_delta` de `engine_agreement_stages`).
    ETAGE 2 -- UTILITE : la MEME formule offline (`damage_composite` + terme TriggeredAbilities),
               nourrie une fois des champs du PORT et une fois des champs NATIFS. Le second etage
               est donc mesure A FEED IDENTIQUE -- c'est ce qui separe « le port predit autre
               chose » de « le port score autre chose ».

Verdict lu en sortie :

  * `u_hybride == u_natif` (a EPS) -> l'etage UTILITE est FIDELE, tout l'ecart vient de la
    PREDICTION, et `delta` nomme le(s) champ(s).
  * `u_hybride != u_natif` -> l'ecart (ou une part) est DANS le composite, feed identique.

Usage :
    python scripts/python/probe_446_r1_pair_residual.py --state-file <chemin ABSOLU>

ASCII only. Le montage (geometrie construite, attestations) est celui de
`scripts/python/probe_446_boltstorm_pair_term.py` -- importe, pas duplique.
"""
from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import probe_446_boltstorm_pair_term as P446                     # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK        # noqa: E402
from engine.utilities import damage_composite                    # noqa: E402

EPS = P446.EPS
ABILITY = P446.ABILITY


def native_events(rpc, rid, cid, tgt, ab, tile) -> list:
    """`aiPlaybookPredict` -- les `ProbableDamageEvent` que le playbook NATIF construit pour la
    paire, PREDITS DEPUIS `tile` (meme tuile que le `pairUtility` confronte)."""
    r = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                                  "abilityType": ab, "col": tile[0], "row": tile[1]}, 60) or {}
    if not r.get("ok"):
        raise P446.MontageError(f"aiPlaybookPredict indisponible pour {tile} / cible {tgt}: {r}")
    return r.get("events") or []


def decompose(rpc, case: dict, key: str) -> dict:
    """Decompose la paire (caster@tile, cible `key`) en ses deux etages."""
    import engine_agreement_stages as EAS
    from engine.playbook.prediction import defender_prediction_block_amount
    from engine.playbook.probable_damage_event import calculate_utility_from_damage_event
    from engine.utilities.tile import triggered_abilities_attack_utility

    ctx, tile, ab = case["ctx"], case["tile"], case["ab"]
    uid = case["ids"][key]
    wt = ctx.wt
    hpmax = ctx.hpmax_by_id.get(uid)

    nat_u = P446.pair_native(rpc, case["rid"], case["cid"], uid, ab, tile)
    port_u = P446.pair_port(ctx, ab, uid, tile)

    # --- ETAGE 1 : les deux jeux d'events, champ par champ -------------------------------
    nat_evs = native_events(rpc, case["rid"], case["cid"], uid, ab, tile)
    nat_main = next((e for e in nat_evs if e.get("targetId") == uid), nat_evs[0] if nat_evs else None)
    off_evs = NORMAL_ATTACK_PLAYBOOK.make_damage_predictions(ctx, tile, uid, ab) or []
    off_main = next((e for e in off_evs if e.target == uid), off_evs[0] if off_evs else None)
    if nat_main is None or off_main is None:
        raise P446.MontageError(f"cible {key}: events manquants (nat={len(nat_evs)} off={len(off_evs)})")

    blk = defender_prediction_block_amount(ctx.scene, uid) if ctx.scene is not None else 0
    nat_f = EAS._fields_from_native_event(nat_main, block_amount=blk)
    off_f = off_main.composite_fields()
    shield_ok = "shieldDmgMin" in nat_main
    delta = EAS._pred_delta(off_f, nat_f, shield_ok)

    # --- ETAGE 2 : la MEME formule, nourrie des deux feeds -------------------------------
    # terme TriggeredAbilities(2) du port (c'est la part `Boltstorm`), isole du composite degat.
    trig = triggered_abilities_attack_utility(ctx, ctx.uid, ab, uid, tile,
                                              prediction=off_main.prediction)
    u_dmg_port = calculate_utility_from_damage_event(off_main, wt, hpmax)
    u_dmg_hybrid = damage_composite(nat_f, hpmax, wt) * off_main.probability
    return {"target": key, "uid": uid, "native": nat_u, "port": port_u,
            "gap": port_u - nat_u,
            "hpmax": hpmax, "trig": trig,
            "u_dmg_port": u_dmg_port, "u_dmg_hybrid": u_dmg_hybrid,
            "u_hybrid_total": u_dmg_hybrid + trig,
            "delta": delta or None, "off_f": off_f, "nat_f": nat_f,
            "n_off": len(off_evs), "n_nat": len(nat_evs)}


def followup_probe(case: dict, key: str, passive: str) -> dict:
    """ETAGE 1bis -- HYPOTHESE INSTRUITE : le mold RANGED
    `IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$PredictAttack`
    = `ALoki_NormalAttackAbility$$PredictAttack` + `GetAdditionalDamagePrediction`, sommes par
    `IdunBattle.Core.Services.DamagePredictionResult$$Add` quand l'arme choisie n'est PAS melee.

    Le port a la FORMULE (`engine.playbook.prediction.get_additional_damage_prediction`) mais son
    registre de dispatch `_RANGED_FOLLOWUP_PASSIVES` est VIDE : l'etage est porte et INERTE. Ce
    bras calcule le fold A LA MAIN (sans toucher au registre) et rend les champs resultants, pour
    que la comparaison au natif tranche AVANT tout branchement."""
    from engine.playbook.prediction import (get_additional_damage_prediction,
                                            make_normal_attack_predictions)
    ctx, tile = case["ctx"], case["tile"]
    uid = case["ids"][key]
    scene = ctx.scene
    ev = make_normal_attack_predictions(scene, ctx.uid, uid, tile)
    if ev is None:
        raise P446.MontageError(f"cible {key}: le port ne produit aucune prediction de base")
    base_f = ev.composite_fields()
    fw = get_additional_damage_prediction(scene, ctx.uid, uid, passive)
    if fw is None:
        return {"base": base_f, "followup": None, "folded": None}
    fw_f = {"rawMin": fw.raw_health_damage.min, "rawMax": fw.raw_health_damage.max,
            "hits": fw.applied_hits}
    ev.prediction.add(fw)
    return {"base": base_f, "followup": fw_f, "folded": ev.composite_fields()}


def mutants(case: dict) -> list[dict]:
    """CONTRE-EPREUVES du fix. Le critere est le DEPLACEMENT du port par rapport au port NON MUTE,
    JAMAIS l'ecart au natif : cette paire porte encore un residu (`#446-r2`), donc `abs(port -
    natif) > EPS` serait vrai meme pour un mutant INERTE -- le piege que #446 avait deja trouve.

      `no_dispatch` -- registre `_RANGED_FOLLOWUP_PASSIVES` vide : plus aucun fold.
      `amount_min`  -- montant = `minDmg` seul (l'ancienne lecture « slot 4 = MIN »).
      `no_mods`     -- fold sans les modifiers de l'attaque porteuse (l'ancien `mods=None`)."""
    import engine.playbook.prediction.normal_attack as NA
    ctx, tile, ab = case["ctx"], case["tile"], case["ab"]
    ref = {k: P446.pair_port(ctx, ab, case["ids"][k], tile) for k in ("T", "A")}
    out = []
    for name in ("no_dispatch", "amount_min", "no_mods"):
        saved_reg = NA._RANGED_FOLLOWUP_PASSIVES
        saved_fn = NA.get_additional_damage_prediction
        saved_avg = NA.calculate_average
        try:
            if name == "no_dispatch":
                NA._RANGED_FOLLOWUP_PASSIVES = ()
            elif name == "amount_min":
                NA.calculate_average = lambda mn, mx: int(mn)
            elif name == "no_mods":
                NA.get_additional_damage_prediction = (
                    lambda *a, **k: saved_fn(*a, **{**k, "mods": None}))
            got = {k: P446.pair_port(ctx, ab, case["ids"][k], tile) for k in ("T", "A")}
        finally:
            NA._RANGED_FOLLOWUP_PASSIVES = saved_reg
            NA.get_additional_damage_prediction = saved_fn
            NA.calculate_average = saved_avg
        shift = {k: got[k] - ref[k] for k in ref}
        out.append({"mutant": name, "shift": shift,
                    "bites": max(abs(v) for v in shift.values()) > EPS})
    return out


def melee_regime(sid, rpc, case: dict) -> dict:
    """GATE du mold : `Boltstorm_NormalAttackAbility$$PredictAttack` ne folde QUE si l'arme choisie
    n'est PAS melee (`FindAttackWeapon(...).get_IsMelee == false`). On amene le caster AU CONTACT de
    la cible entouree : le natif doit retomber au compte de coups de l'arme, et le port avec lui.

    ⚠ Cette mesure DEPLACE les unites -- a jouer EN DERNIER, comme le balayage de #446."""
    import hexgeo
    import probe_124_line_elevation_decision as P124
    from engine import battle_query as bq
    from engine.playbook.prediction import make_normal_attack_predictions

    ctx, elev, walk, ids = case["ctx"], case["elev"], case["walk"], case["ids"]
    tpos = ctx.scene.pos(ids["T"])
    busy = {ctx.scene.pos(u) for u in ids.values()}
    cand = [q for q in hexgeo.neighbors(tpos[0], tpos[1])
            if walk.get(q) and elev.get(q) is not None and q not in busy
            and bq.is_adjacent(tpos, q, elev)]
    if not cand:
        raise P446.MontageError("regime MELEE NON INSTALLE : aucune tuile adjacente NATIVE libre "
                                "autour de la cible -- la gate du mold n'est pas exercee")
    dest = cand[0]
    wanted = dict(case["wanted"])
    wanted[case["cid"]] = dest
    if not P124._drive_to(sid, case["rid"], walk, elev, wanted):
        raise P446.MontageError(f"regime MELEE NON INSTALLE : placement en {dest} incomplet")
    P124._give_turn_back(sid, case["rid"], case["myplayer"])
    dv = rpc("decisionView", {"runnerId": case["rid"], "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": case["rid"]}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    c2 = _ai_ctx.build(rpc, case["rid"], dv, mbu, case["cid"], W.load(),
                       _scene.build_predictor(rpc, case["rid"]))
    if not bq.is_adjacent(dest, c2.scene.pos(ids["T"]), elev):
        raise P446.MontageError("regime MELEE NON INSTALLE : le caster n'est pas adjacent NATIF "
                                "a la cible apres le drive")
    r = rpc("aiPlaybookPredict", {"runnerId": case["rid"], "unitId": case["cid"],
                                  "targetId": ids["T"], "abilityType": case["ab"],
                                  "col": dest[0], "row": dest[1]}, 60)
    e0 = (r.get("events") or [{}])[0]
    ev = make_normal_attack_predictions(c2.scene, case["cid"], ids["T"], dest)
    f = ev.composite_fields() if ev is not None else {}
    return {"tile": dest,
            "native": (e0.get("willKillDmg"), e0.get("mightKillDmg"), e0.get("appliedHits")),
            "port": (f.get("rawHealthDmgMin"), f.get("rawHealthDmgMax"), f.get("appliedHits"))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du state-file")
    ap.add_argument("--runner", type=int, default=None,
                    help="reutilise un runner deja monte (sinon build)")
    ap.add_argument("--followup", default=None, metavar="PASSIF",
                    help="instruit l'hypothese du mold RANGED avec la config de ce passif "
                         "(ex. Boltstorm) -- calcule le fold A LA MAIN, sans toucher au registre")
    ap.add_argument("--mutants", action="store_true",
                    help="joue les contre-epreuves du fix (chacune doit DEPLACER le port)")
    ap.add_argument("--melee", action="store_true",
                    help="joue la GATE du mold en amenant le caster au contact (DEPLACE les unites)")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = args.runner if args.runner else P446._build(args.state_file, P446.BUILD_ARGS)
    case = P446.build_case(sid, rpc, rid)
    lay = case["layout"]
    print(f"runner {rid} | caster u{case['cid']} @ {lay['C']} | normale {case['ab']}")
    print(f"  layout T={lay['T']} N1={lay['N1']} N2={lay['N2']} F={lay['F']} A={lay['A']}")
    for key in ("T", "A"):
        d = decompose(rpc, case, key)
        print(f"  [{d['target']}] u{d['uid']} hpmax={d['hpmax']} "
              f"nat={d['native']:.6f} port={d['port']:.6f} gap={d['gap']:+.6f}")
        print(f"      trig(1090)={d['trig']:.6f} | u_dmg_port={d['u_dmg_port']:.6f} "
              f"u_dmg_hybride={d['u_dmg_hybrid']:.6f} "
              f"| hybride+trig={d['u_hybrid_total']:.6f} "
              f"reste_vs_nat={d['u_hybrid_total'] - d['native']:+.6f}")
        print(f"      events off={d['n_off']} nat={d['n_nat']}")
        if d["delta"]:
            for k, v in sorted(d["delta"].items()):
                print(f"      DELTA {k}: off={v['off']} nat={v['nat']}")
        else:
            print("      DELTA prediction: AUCUN (champs identiques)")
        print(f"      off_f={ {k: d['off_f'].get(k) for k in ('healthDmgMin','healthDmgMax','rawHealthDmgMin','rawHealthDmgMax','shieldDmgMin','shieldDmgMax','appliedHits','hpBefore','shieldBefore')} }")
        print(f"      nat_f={ {k: d['nat_f'].get(k) for k in ('healthDmgMin','healthDmgMax','rawHealthDmgMin','rawHealthDmgMax','shieldDmgMin','shieldDmgMax','appliedHits','hpBefore','shieldBefore')} }")
        if args.followup:
            fu = followup_probe(case, key, args.followup)
            f = fu["folded"]
            print(f"      FOLLOWUP({args.followup}) = {fu['followup']}")
            if f is None:
                print("      FOLD: la formule rend None (config absente ou nulle)")
            else:
                keys = ("healthDmgMin", "healthDmgMax", "rawHealthDmgMin", "rawHealthDmgMax",
                        "appliedHits")
                diff = {k: (f.get(k), d["nat_f"].get(k)) for k in keys
                        if f.get(k) != d["nat_f"].get(k)}
                print(f"      FOLD  ={ {k: f.get(k) for k in keys} }")
                print(f"      FOLD vs NATIF: {'IDENTIQUE' if not diff else diff}")
    if args.mutants:
        for m in mutants(case):
            det = " ".join(f"{k}:{v:+.4f}" for k, v in sorted(m["shift"].items()))
            print(f"  [mutant {m['mutant']:<12}] deplacement du port [{det}] "
                  f"({'MORD' if m['bites'] else 'NE MORD PAS'})")
    if args.melee:
        g = melee_regime(sid, rpc, case)
        print(f"  [gate MELEE @ {g['tile']}] NAT={g['native']} PORT={g['port']} "
              f"({'ACCORD' if g['native'] == g['port'] else 'DELTA'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
