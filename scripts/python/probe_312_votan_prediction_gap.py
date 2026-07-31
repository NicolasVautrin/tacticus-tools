"""probe #312 -- LOCALISATION PAR ETAGE de l'ecart de prediction sur `votanChampion` (Kimm).

LE CRITERE, pose AVANT toute methode
------------------------------------
Question binaire : **A QUEL ETAGE de `pairUtility` les deux faces divergent-elles ?**
Ce probe ne corrige RIEN. Il MESURE, etage par etage, entree et sortie, jusqu'au PREMIER etage
ou natif != port. Tant que l'etage n'est pas nomme, toute correction est une devinette.

Le natif decompose ainsi (`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`,
= exactement ce que le RPC `pairUtility` invoque) :

    pairUtility(ability, cible, tuile)
      = SOMME_damage  vslot +0x358 `MakeDamagePredictions`  -> `Playbooku003C...u003E$$CalculateUtilityFromDamageEvent`
      + SOMME_heal    vslot +0x368                          -> `...$$CalculateUtilityFromHealEvent`
      + SOMME_effect  vslot +0x378 / +0x388                 -> `UtilityAttackCase$$ForEffect`
      + SOMME_repair  vslot +0x388 (Dictionary)             -> `UtilityAttackCase$$ForRepairPrediction`

D'ou les DEUX etages a separer, et l'ordre est impose :

    ETAGE 1 -- PREDICTION : `MakeDamagePredictions` (natif = RPC `aiPlaybookPredict` a la MEME tuile)
               vs `playbook.make_damage_predictions` (port). Champ a champ.
    ETAGE 2 -- CONVERSION : la SOMME ci-dessus, nourrie des MEMES evenements (les NATIFS) des deux
               cotes. Natif = RPC `pairUtility` ; port = `engine_agreement_stages.StageProbe.
               _formula_pair_utility`. Un ecart ici est un gap de FORMULE, jamais de feed.

Trois nombres par tuile, donc, et leur lecture est mecanique :

    A = pairUtility natif                      (verite)
    B = formule PORT nourrie des events NATIFS  (etage 2 isole)
    C = utilite PORT complete                   (= etage 1 o etage 2)

    A == B  et  B != C  ->  l'ecart est ENTIEREMENT a l'etage 1 (PREDICTION)
    A != B              ->  l'ecart est (aussi) a l'etage 2 (CONVERSION)

PIEGES MESURES SUR CE PORTEUR (ils ont deja coute) :
  1. NE JAMAIS deplacer Kimm : un `act move` consomme son mouvement et rend 1222 illegale.
     Ce probe ne bouge QUE les appats/auras/la cible, jamais le caster (`MDA.build_fixture`).
  2. Poser un appat sur la tuile ou le natif allait frapper fait basculer le natif pour une raison
     PUREMENT GEOMETRIQUE. Le bras utilise est donc `set_arm(rid, 0, geom)` -- aucun appat adjacent.

Usage :
    python probe_312_votan_prediction_gap.py                      # MC1_67 / 909 / Damage=1000
    python probe_312_votan_prediction_gap.py --damage 900,1000
    python probe_312_votan_prediction_gap.py --board C4_09 --seed 31337 --damage 3600
ASCII only.
"""
from __future__ import annotations

import sys

import probe_27_3_live as L
import probe_27_r1_massdriver_custom as MDA

NORMAL = 69
MDA_AB = 1222
DEFAULT_DAMAGE = 1000


def _build_ctx(rid: int):
    """`AiDecisionContext` du caster sur le runner vivant (meme couture qu'`engine_validate`)."""
    import engine_validate as EV
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX
    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)          # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, MDA.CASTER, wt, predictor)
    return ctx, wt, sid, dv, mov_by_unit


def _ranked_tiles(ctx, ability: int) -> list:
    """Tuiles d'attaque LEGALES pour `ability` sur la cible du montage, telles que le natif les
    range (`attackPlans[].evals[].ranked` = `GetBestTileToAttackFrom`)."""
    plan = ctx.plans.get(ctx.uid) or {}
    for ev in (plan.get("evals") or []):
        if ev.get("abilityId") == ability and ev.get("targetId") == MDA.TARGET:
            return [(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])]
    return []


def measure(rid: int, damage: int) -> dict:
    """Rend le tableau de LOCALISATION par etage, tuile par tuile."""
    import hexgeo
    import engine_agreement_stages as ST
    from engine.playbook import get_playbook_or_default
    from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK
    from engine.playbook.modified_exoarmour import path_node_counts
    from engine.utilities.tile import tile_leaf_ctx

    ctx, wt, sid, dv, mov_by_unit = _build_ctx(rid)
    probe = ST.StageProbe(sid, rid, wt)
    counts = path_node_counts(tile_leaf_ctx(ctx))
    epos = ctx.scene.pos(MDA.TARGET)
    bg = L._rpc("boardGraph", [{"runnerId": rid}])
    by_id = {t.get("id"): (t.get("col"), t.get("row")) for t in (bg.get("tiles") or [])}
    nb_of = {(t.get("col"), t.get("row")): {by_id[i] for i in (t.get("neighbours") or [])
                                            if i in by_id}
             for t in (bg.get("tiles") or [])}
    out = {"rows": [], "pred_rows": [], "damage": damage, "enemy": epos}
    for ab in (NORMAL, MDA_AB):
        tiles = _ranked_tiles(ctx, ab)
        pb = NORMAL_ATTACK_PLAYBOOK if ab in ctx.normal_ids else get_playbook_or_default(ab)
        for t in tiles:
            # ---- A : le scoreur NATIF
            u = probe._confront_utility(ctx, 0, MDA.CASTER, ab, MDA.TARGET, t)
            if u.get("skipped"):
                out["rows"].append({"ab": ab, "tile": t, "skipped": u.get("skipped")})
                continue
            # ---- C : le port COMPLET (sa propre prediction + sa propre conversion)
            act = pb.calculate_action_utility(ctx, t, MDA.TARGET, ab)
            c = None if act is None else act["u"]
            # ---- ETAGE 1 : champ a champ des predictions, MEME tuile
            p = probe._confront_prediction(ctx, dv, mov_by_unit, 0, MDA.CASTER, ab, MDA.TARGET, t)
            nat_evs = probe._native_events(0, MDA.CASTER, ab, MDA.TARGET, t) or []
            nat_main = next((e for e in nat_evs if e.get("targetId") == MDA.TARGET),
                            nat_evs[0] if nat_evs else {})
            off_evs = pb.make_damage_predictions(ctx, t, MDA.TARGET, ab) or []
            off_main = next((e for e in off_evs if e.target == MDA.TARGET),
                            off_evs[0] if off_evs else None)
            off_f = off_main.composite_fields() if off_main is not None else {}
            nodes = counts.get(t)
            row = {"ab": ab, "tile": t, "A_nat": u["nat"], "B_formula": u["off"],
                   "C_port": None if c is None else round(c, 4), "fams": u.get("families"),
                   "moved": None if nodes is None else nodes - 1,
                   "melee": (epos in nb_of.get(t, set())),
                   "hexE": None if epos is None else hexgeo.distance(t, epos),
                   "off_min": off_f.get("healthDmgMin"), "off_max": off_f.get("healthDmgMax"),
                   "nat_min": nat_main.get("healthDmgMin"), "nat_max": nat_main.get("healthDmgMax"),
                   "hits_off": off_f.get("appliedHits"), "hits_nat": nat_main.get("appliedHits")}
            out["rows"].append(row)
            out["pred_rows"].append({"ab": ab, "tile": t, "pred": p})
    out["ctx"] = ctx
    return out


def build_arm(damage: int, with_passive: bool, board: str = MDA.BOARD, seed: int = MDA.SEED,
              geom=None, unit_stats=None) -> tuple:
    """Monte UN bras de la fixture et le MESURE. Rend `(res, rid, geom)`.
    Kimm n'est JAMAIS deplacee ; `set_arm(..., 0, ...)` garde les appats LOIN (pieges 1 et 2).

    GARDE-FOU DE MONTAGE (#322) : `MDA.build_fixture` lance `rl_duel build` avec `check=False` et
    `stdout=DEVNULL` -- un build REFUSE ne leve donc RIEN, et `_runner_id()` relit paisiblement
    l'ANCIEN runner du meme `--state-file`. Le probe mesure alors un bras qu'il croit neuf et rend
    des chiffres parfaitement coherents... de la mesure precedente. VECU sur ce cas meme : un bras
    `--board C2_19` (3 spawns joueur < 5 unites -> `[error]` du builder) a rendu, a la ligne pres,
    les valeurs du bras `C4_09` d'avant, `Damage` inclus. On EXIGE donc un runner NEUF a chaque
    build -- un echec RENDU ne doit pas pouvoir se lire comme une mesure."""
    before = None
    if MDA.STATE.exists():
        try:
            before = MDA._runner_id()
        except Exception:                       # noqa: BLE001  (state-file illisible -> pas d'ancre)
            before = None
    rid, geom = MDA.build_fixture(damage, with_passive=with_passive, board=board, seed=seed,
                                  geom=geom, unit_stats=unit_stats)
    if before is not None and rid == before:
        raise SystemExit(
            "build REFUSE (runner inchange : %d) pour board=%s seed=%d Damage=%d -- le bras "
            "mesurerait le runner PRECEDENT. Relancer `rl_duel build` a la main pour lire l'erreur "
            "(cause frequente : le plateau n'a pas assez de spawns joueur pour 5 unites)."
            % (rid, board, seed, damage))
    MDA.set_arm(rid, 0, geom)
    return measure(rid, damage), rid, geom


def measure_without_the_effect(rid: int, damage: int) -> dict:
    """RE-MESURE le meme runner avec `ModifiedExoarmour_ExtraDmgEffect` NEUTRALISE -- la MUTATION
    ADVERSARIALE du port de #322, integree au harnais.

    Elle sert deux fois : (a) elle prouve que le montage EXERCE reellement le regime (sans l'effet,
    le port re-diverge du natif exactement comme avant le portage) ; (b) elle fournit le port
    SANS-EFFET, donc l'ecart imputable a CE seul effet, tuile par tuile."""
    from engine.entities.effects.loki import ModifiedExoarmourExtraDmgEffect as _E
    orig = _E.create_effect_damage_bonus_for_attack
    _E.create_effect_damage_bonus_for_attack = (
        lambda self, *a, **k: None)                # le port comme si l'effet n'existait pas
    try:
        return measure(rid, damage)
    finally:
        _E.create_effect_damage_bonus_for_attack = orig


def divergent_tiles(res: dict) -> list:
    """Tuiles (ability, tuile) ou l'etage PREDICTION du port s'ecarte du natif."""
    out = []
    for r in res["rows"]:
        if r.get("skipped") or r.get("off_min") is None or r.get("nat_min") is None:
            continue
        if r["off_min"] != r["nat_min"] or r["off_max"] != r["nat_max"]:
            out.append(r)
    return out


def conversion_mismatches(res: dict) -> list:
    """Paires ou l'etage CONVERSION diverge : |A_nat - B_formule| au-dela de la tolerance Fix64."""
    bad = []
    for r in res["rows"]:
        if r.get("skipped"):
            continue
        a, b = r["A_nat"], r["B_formula"]
        if abs(b - a) > max(0.01, 0.001 * abs(a)):
            bad.append(r)
    return bad


def report(res: dict, damage: int) -> bool:
    print("\n  ETAGES  (A = pairUtility NATIF ; B = formule PORT sur events NATIFS ; "
          "C = port COMPLET)")
    print("  %-6s %-8s %10s %10s %10s   %s" % ("ab", "tuile", "A_nat", "B_form", "C_port",
                                               "verdict d'etage"))
    ok_stage2 = True
    localized = []
    for r in res["rows"]:
        if r.get("skipped"):
            print("  %-6s %-8s   SKIP %s" % (r["ab"], str(r["tile"]), r["skipped"]))
            continue
        a, b, c = r["A_nat"], r["B_formula"], r["C_port"]
        tol = max(0.01, 0.001 * abs(a))
        s2 = abs(b - a) <= tol
        s1 = (c is not None) and abs(c - b) <= tol
        if s2 and s1:
            v = "OK (aucun ecart)"
        elif s2 and not s1:
            v = "ECART ETAGE 1 (PREDICTION) d=%.3f" % ((c if c is not None else 0) - b)
        elif not s2 and s1:
            v = "ECART ETAGE 2 (CONVERSION) d=%.3f" % (b - a)
        else:
            v = ("ECART ETAGE 1 d=%.3f ET ETAGE 2 d=%.3f"
                 % ((c if c is not None else 0) - b, b - a))
        ok_stage2 = ok_stage2 and s2
        localized.append((r["ab"], r["tile"], s2, s1))
        print("  %-6s %-8s %10.3f %10.3f %10s   %s"
              % (r["ab"], str(r["tile"]), a, b, "-" if c is None else "%.3f" % c, v))
    print("\n  ETAGE 1 -- DEGAT par tuile (port vs aiPlaybookPredict = `MakeDamagePredictions`)")
    print("  %-6s %-8s %-6s %-6s %-5s %11s %11s %8s %8s %9s"
          % ("ab", "tuile", "melee", "bouge", "hexE", "port min/max", "natif min/max",
             "d_min", "d_max", "d/(n x pm)"))
    for r in res["rows"]:
        if r.get("skipped"):
            continue
        om, ox = r.get("off_min"), r.get("off_max")
        nm, nx = r.get("nat_min"), r.get("nat_max")
        if om is None or nm is None:
            continue
        dmin, dmax = nm - om, (nx - ox) if (nx is not None and ox is not None) else None
        n = r.get("moved") or 0
        ratio = (dmin / float(n * om)) if (n and om) else None
        print("  %-6s %-8s %-6s %-6s %-5s %11s %11s %8s %8s %9s"
              % (r["ab"], str(r["tile"]), "OUI" if r["melee"] else "non", n, r["hexE"],
                 "%d/%d" % (om, ox), "%d/%d" % (nm, nx), dmin, dmax,
                 "-" if ratio is None else "%.5f" % ratio))
    return ok_stage2


def main() -> int:
    argv = sys.argv[1:]
    scan = MDA._opt(argv, "--damage")
    damages = [int(x) for x in scan.split(",")] if scan else [DEFAULT_DAMAGE]
    board = MDA._opt(argv, "--board", MDA.BOARD)
    seed = int(MDA._opt(argv, "--seed", str(MDA.SEED)))
    # `--passive-off` : le CONTRE-BRAS. Le seed BC `SEED_BC_NP` retire `PassiveAbilities` de Kimm ;
    # si l'ecart DISPARAIT sur toutes les tuiles, il vient ENTIEREMENT du passif -- et la base
    # native des tuiles de melee devient LISIBLE (elle est masquee par le bonus dans l'autre bras).
    passive = "--passive-off" not in argv
    # `--unit-stat "VisualId:Champ=Valeur"` (repetable via `;`) : le levier de CONFIG de #312 SS 5
    # (niveau de passif, multiplicateur de rarete) -- c'est lui qui fait varier `V` sans toucher a la
    # geometrie, donc le seul moyen de montrer que la magnitude n'est pas fittee sur UN regime.
    us = MDA._opt(argv, "--unit-stat")
    unit_stats = [s for s in us.split(";") if s] if us else None
    geom = None
    for d in damages:
        res, rid, geom = build_arm(d, passive, board=board, seed=seed, geom=geom,
                                   unit_stats=unit_stats)
        print("\n--- runner=%d board=%s seed=%d Damage=%d passif=%s stats=%s ---"
              % (rid, board, seed, d, "ON" if passive else "RETIRE", unit_stats or "-"))
        print("    geometrie : Kimm=%s ennemi=%s" % (geom["kimm"], res.get("enemy")))
        report(res, d)
    print("\n(pense a disposer le runner : python rl_duel.py dispose --state-file %s)" % MDA.STATE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
