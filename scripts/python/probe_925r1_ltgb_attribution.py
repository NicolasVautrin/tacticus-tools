"""#925-r1 -- le `+1 coup` de `LetTheGalaxyBurn` : le FOLD rejouait le canal #179.

## La question binaire

`IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits` monte un
`EffectAdditionalHits` dont le trigger est
`get_OwnerIsCaster & (TargetHasTileEffect | IsPersistentData(0x5ca, Owner, Get(<statique>)))`.
Le coup qu'il ajoute part-il, cote NATIF, sur la cible PRIMAIRE ou sur une cible du CLEAVE -- et le
port fait-il l'inverse ?

## Reponse : NI l'un NI l'autre -- le port en mettait UN DE TROP, et c'est le tirage surnumeraire
   qui deplacait le reste

Le canal #179 (`IdunBattleLogic.Entities.DSLBehaviors$$ExecuteAdditionalHitsWithDamageProfileType`)
est un VOLET du `Attack(...)`, FRERE de la feuille de coups :
`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetAttackDamageBehaviour`
monte UN SEUL `IdunBattleLogic.Entities.DSLBehaviors$$Attack` autour de `b1 & b2 & b3` -- `b1` les
coups d'ARME, `b2` le FOLD (`$$GetCustomNormalAttackBehaviour`, une feuille NUE), `b3` ce canal. Le
FOLD n'a donc aucun titre a le rejouer. Le port le rejouait (`damage_ops/ability.py`, gate
`is_attack_damage_op` SEUL), et comme le port joue le fold APRES le `FinishAttack`/`On(Attack = 9)`
de l'attaque primaire -- donc APRES que `LetTheGalaxyBurn_ResetAbility` a efface le flag ET pose
`DespoiledGround` sur la tuile de la cible --, le groupe se re-qualifiait par l'AUTRE branche du
gate (`TargetHasTileEffect`).

MESURE (board `MC1_67`, seed 4463111, `templAggressor` + trait `LetTheGalaxyBurn` greffe) :

    NATIF       primaire 3508   necroWarden 1185   necroDestroyer 1654
    PORT avant  primaire 4134   necroWarden 1185   necroDestroyer 1129
    PORT apres  primaire 3508   necroWarden 1185   necroDestroyer 1654     (bit-exact)

et le coup `LetTheGalaxyBurn` part desormais sur `necroDestroyer` (553 = le 3e `Amount` natif),
exactement comme au natif -- il n'y etait plus parce que le tirage de trop avait fait rater son
`Maybe(LetTheGalaxyBurnChancePct)`.

## Ce probe ne fitte AUCUN scalaire -- il DECOMPOSE, et il REFUSE plutot que de rendre un vert

  0. MONTAGE : le trait canal est sur l'ENTITE (traits MESURES du port, canal `combatSnapshot`).
  1. ATTRIBUTION NATIVE : la ventilation par COUP de CHAQUE cible (`Amount`,
     `Active_Ability_Type`), pas seulement le delta de PV.
  2. ARMEMENT PORT : chaque evaluation de `LetTheGalaxyBurnArmAbility.matches`.
  3. CANAL #179 PORT : chaque appel de `collect_additional_hit_groups` /
     `execute_additional_hits`, par FACADE (`normal` = l'attaque primaire, `ability` = fold+cleave).
  4. VERDICT : le PV par cible du port == celui du natif, ET la ventilation par coup de la primaire.
  5. CONTRE-EPREUVE : sous mutation de `damage_ops.ability.leaf_executes_additional_hits`
     (l'ancien comportement), le port DOIT diverger. S'il n'y arrive pas, le canal est inerte et
     l'etage 4 ne prouve rien : REFUS, pas un vert.

Usage :
    python probe_925r1_ltgb_attribution.py --state-file <ABSOLU>.json [--regime boltstorm|rr]
        [--board MC1_67] [--seed 4463111] [--runner N] [--verbose]

ASCII only. Garde jumelle : `scripts/python/tests/engine/test_925r1_ltgb_attribution_live.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import probe_478_cleave_additional_targets as P478                # noqa: E402
import probe_446_r3b_fealty_talon_asymetrie as R3B                # noqa: E402
import probe_925_fold_pre_attack as P925                          # noqa: E402
from engine.runner.components import HealthComponent              # noqa: E402
from engine.runner.messages import AttackUnitMessage              # noqa: E402
from engine.runner.runner import Runner                           # noqa: E402

MontageError = R3B.MontageError

#: La fonction ORIGINALE, capturee AVANT toute substitution -- les restaurations la reposent plutot
#: qu'un `lambda` qui perdrait sa docstring (le point de mutation des autres cliquets).
from engine.runner.operations.damage_ops import ability as _ABIL  # noqa: E402
_LEAF_NATIF = _ABIL.leaf_executes_additional_hits


def native_hits_by_target(a0: dict, by_vis: dict) -> dict:
    """ETAGE 1 -- `{cible: [(Amount, Active_Ability_Type), ...]}` dans l'ORDRE d'emission natif.

    `probe_478._native_hits` ne rend la ventilation que pour la cible PRIMAIRE ; la question de ce
    residu porte sur TOUTES les cibles, donc on la re-derive ici depuis l'action complete."""
    out = {}
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" not in td:
            continue
        t = by_vis.get(td.get("Target_Id"), td.get("Target_Id"))
        out.setdefault(t, []).append((td.get("Amount"), td.get("Active_Ability_Type")))
    return out


def rejoue(bundle: dict, leaf_executes: bool) -> dict:
    """Rejoue l'attaque normale OFFLINE en tracant les trois canaux, sous le regime demande.

    `leaf_executes = False` = le port CORRIGE (#925-r1, une feuille NUE ne rejoue pas le canal
    #179) ; `True` = le port MUTANT, c'est-a-dire l'ancien comportement.

    Les deux facades importent `collect_additional_hit_groups` / `execute_additional_hits` en FORME
    A (`from ..additional_hits import ...`), donc le patch doit viser le MODULE CONSOMMATEUR, pas
    `additional_hits` -- une liaison de nom au niveau module est gelee a l'import."""
    from engine.runner.operations.damage_ops import normal as NORM
    from engine.runner.operations.damage_ops import ability as ABIL
    from engine.runner.operations.triggers.loki import let_the_galaxy_burn as LTGB

    state = P925._load(bundle)
    by_vis = {v: k for k, v in bundle["uid"].items()}
    trace = {"arm": [], "collect": [], "exec": []}

    def nom(i):
        return by_vis.get(i, i)

    vrai_matches = LTGB.LetTheGalaxyBurnArmAbility.matches

    def matches(self, st, ev):
        ok = vrai_matches(self, st, ev)
        trace["arm"].append({"owner": nom(self.owner_id), "actor": nom(ev.actor_id),
                             "target": nom(ev.target_id), "armed": bool(ok)})
        return ok

    LTGB.LetTheGalaxyBurnArmAbility.matches = matches
    # MUTATION du point nomme -- l'appel se resout dans les globals de `damage_ops.ability`, donc un
    # `setattr` de module MORD (forme B). `leaf_executes = True` reproduit l'ancien gate
    # (`is_attack_damage_op` seul), qui ignorait `is_outside_attack`.
    ABIL.leaf_executes_additional_hits = ((lambda _ioa: True) if leaf_executes else _LEAF_NATIF)

    originaux = {}
    for mod, voie in ((NORM, "normal"), (ABIL, "ability")):
        originaux[voie] = (mod.collect_additional_hit_groups, mod.execute_additional_hits)

        def mk_collect(m=mod, v=voie):
            vrai = m.collect_additional_hit_groups

            def collect(state_, att, tgt, *a, **k):
                g = vrai(state_, att, tgt, *a, **k)
                trace["collect"].append({"voie": v, "att": nom(att), "tgt": nom(tgt),
                                         "n": len(g or []),
                                         "pd": sorted(str(x) for x in (k.get("persistent_data")
                                                                       or ())),
                                         "groupes": [str(x)[:70] for x in (g or [])]})
                return g
            return collect

        def mk_exec(m=mod, v=voie):
            vrai = m.execute_additional_hits

            def ex(state_, att, tgt, *a, **k):
                r = vrai(state_, att, tgt, *a, **k)
                trace["exec"].append({"voie": v, "att": nom(att), "tgt": nom(tgt),
                                      "per_hit": list((r or {}).get("per_hit") or []),
                                      "total": (r or {}).get("total")})
                return r
            return ex

        mod.collect_additional_hit_groups = mk_collect()
        mod.execute_additional_hits = mk_exec()

    before = {i: (state.get_entity(i).get_component(HealthComponent).hp
                  if state.get_entity(i) is not None
                  and state.get_entity(i).get_component(HealthComponent) is not None else None)
              for i in P478._hp_by_id(bundle["dv"])}
    try:
        runner = Runner(state).install_default_handlers(20)
        runner.apply(AttackUnitMessage(bundle["cid"], bundle["tid"]))
    finally:
        LTGB.LetTheGalaxyBurnArmAbility.matches = vrai_matches
        ABIL.leaf_executes_additional_hits = _LEAF_NATIF
        for mod, voie in ((NORM, "normal"), (ABIL, "ability")):
            mod.collect_additional_hit_groups, mod.execute_additional_hits = originaux[voie]
    after = {i: (state.get_entity(i).get_component(HealthComponent).hp
                 if state.get_entity(i) is not None
                 and state.get_entity(i).get_component(HealthComponent) is not None else None)
             for i in before}
    d = {nom(i): int(before[i]) - int(after[i]) for i in before
         if before.get(i) is not None and after.get(i) is not None and before[i] != after[i]}
    rr = runner.damage_handler.last or {}
    return {"trace": trace, "pv": d,
            "arme": (list(rr.get("per_hit") or [])
                     + list((rr.get("additional_hits") or {}).get("per_hit") or [])),
            "fold": list(((rr.get("primary_fold") or {}).get("attack") or {}).get("per_hit") or []),
            # ETAGE STRUCTUREL du drapeau. ⚠ Le COMPTE GLOBAL de la voie `ability` ne discrimine
            # PAS : le CLEAVE l'emprunte lui aussi, et sur le regime `boltstorm` les deux regimes
            # tirent 1 coup chacun -- le corrige sur `necroDestroyer` (le cleave, LEGITIME), le
            # mutant sur la cible PRIMAIRE (le fold, EN TROP). C'est la CIBLE qui separe, pas le
            # nombre : mesure du 2026-08-13, ce cran a d'abord ete ecrit en compte global et a
            # rougi sur un montage pourtant juste.
            "n_exec_ability": sum(1 for x in trace["exec"] if x["voie"] == "ability"),
            "n_hits_ability": sum(len(x["per_hit"]) for x in trace["exec"]
                                  if x["voie"] == "ability"),
            # les coups que la voie `ability` tire du canal #179 SUR LA CIBLE PRIMAIRE = exactement
            # ce que le FOLD rejouait (le cleave, lui, ne frappe QUE des cibles additionnelles).
            "n_hits_fold_179": sum(len(x["per_hit"]) for x in trace["exec"]
                                   if x["voie"] == "ability" and x["tgt"] == nom(bundle["tid"]))}


def mesure(rpc, st: dict, porteur: str) -> dict:
    """Le CAS COMPLET, reutilisable par la garde jumelle : cast LIVE (une seule fois), ventilation
    native par cible, et les DEUX regimes du port rejoues sur le MEME bundle (meme MT)."""
    vrai_nh, capt = P478._native_hits, {}

    def nh(a0):
        capt["a0"] = a0
        return vrai_nh(a0)

    P478._native_hits = nh
    try:
        r = P478.replay(rpc, st, porteur)
    finally:
        P478._native_hits = vrai_nh
    bundle = r["bundle"]
    by_vis = {v: k for k, v in st["uid"].items()}
    return {"r": r, "bundle": bundle, "porteur": porteur,
            "traits": P925.traits_mesures(bundle),
            "nat_hits": native_hits_by_target(capt.get("a0") or {}, by_vis),
            "corr": rejoue(bundle, leaf_executes=False),
            "mut": rejoue(bundle, leaf_executes=True)}


def verdict(case: dict) -> list:
    """Les cinq crans, dans l'ordre. Rend la liste des ECHECS (vide = OK)."""
    bad = []
    r, corr, mut = case["r"], case["corr"], case["mut"]

    # (0) le canal est ARME sur l'ENTITE -- sinon aucun consommateur d'`On(5)` ne tire.
    if P925.TRAITS[-1] not in case["traits"]:
        bad.append(f"etage 0 : canal NON ARME -- l'entite de {case['porteur']} porte "
                   f"{sorted(case['traits'])}, sans {P925.TRAITS[-1]} aucun accord ne discrimine")

    # (1) NON-TRIVIALITE : le natif DOIT porter un coup `LetTheGalaxyBurn` quelque part, sinon le
    #     montage ne met en jeu aucun canal #179 et les crans suivants jugent une branche morte.
    nat_tot = {k: sum(int(a) for a, _ in v) for k, v in case["nat_hits"].items()}
    if not any(len(v) for v in case["nat_hits"].values()):
        bad.append("etage 1 : le NATIF ne rapporte AUCUN coup -- rien n'a eu lieu")
    # (1bis) et le DRAPEAU doit etre ATTEINT : le mutant DOIT tirer au moins un coup du canal #179
    #        par la voie `ability` SUR LA CIBLE PRIMAIRE (c'est-a-dire par le FOLD), et le corrige
    #        AUCUN. Le compte GLOBAL de la voie `ability` ne discriminerait pas -- le cleave
    #        l'emprunte aussi, legitimement.
    if not (mut["n_hits_fold_179"] >= 1 and corr["n_hits_fold_179"] == 0):
        bad.append(f"etage 1bis : montage TRIVIAL -- coups du canal #179 tires par le FOLD "
                   f"(voie `ability`, cible PRIMAIRE) : corrige {corr['n_hits_fold_179']}, mutant "
                   f"{mut['n_hits_fold_179']}. Attendu 0 et >= 1 : le drapeau n'est pas atteint.")

    # (2) COHERENCE DU NATIF : la somme des coups d'une cible == son delta de PV. Sans ce cran, le
    #     verdict par PV serait une echappatoire ; avec lui, c'est une mesure.
    for k, tot in nat_tot.items():
        got = int(r["nat"].get(k, 0))
        if got and tot != got:
            bad.append(f"etage 2 : le NATIF est INCOHERENT sur {k} (somme des coups {tot} != delta "
                       f"de PV {got}) -- la ventilation ne peut pas servir de verdict")

    # (3) VERDICT : le PV PAR CIBLE du port corrige == celui du natif. C'est bien le total qui fait
    #     verdict ici -- l'ecart de #925-r1 etait un coup APPLIQUE hors ventilation.
    if corr["pv"] != r["nat"]:
        bad.append(f"etage 3 : PV par cible -- port corrige {corr['pv']} != natif {r['nat']}")

    # (3bis) et la ventilation par COUP de la cible primaire, qui dit COMMENT.
    nat_prim = list(r["nat_primaire_hits"])
    got_prim = list(corr["arme"]) + list(corr["fold"])
    if got_prim != nat_prim:
        bad.append(f"etage 3bis : ventilation par COUP sur la primaire -- port {got_prim} "
                   f"(arme {corr['arme']} + fold {corr['fold']}) != natif {nat_prim}")

    # (4) CONTRE-EPREUVE : le MUTANT doit s'ecarter. Sinon le canal est inerte sur ce montage.
    if mut["pv"] == r["nat"]:
        bad.append("etage 4 : le port MUTANT (le FOLD rejoue le canal #179) rend EXACTEMENT les PV "
                   "natifs -- le canal est INERTE sur ce montage, donc l'accord de l'etage 3 ne "
                   "discrimine rien. REFUSE.")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default=P478.BOARD)
    ap.add_argument("--seed", default=P478.SEED)
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--regime", default="boltstorm", choices=tuple(P925.REGIMES))
    ap.add_argument("--verbose", action="store_true", help="imprime les trois traces du port")
    args = ap.parse_args()
    porteur, layout = P925.REGIMES[args.regime]

    from rl_collect_batch import _resolve_session, _rpc, bind_ambient_rpc
    sid = _resolve_session()
    # #1074 -- LE CANAL EST DEMANDE ICI, la ou le `load_state` est AILLEURS. Ce probe charge son
    # etat par `P478.stage(...)`, donc dans un AUTRE module : le recensement de
    # `probe_448_r3_r1_r1` ne peut ni l'accuser ni le blanchir (regime `indirect`), et c'est
    # precisement le cas ou personne ne verrait le canal muet. Le montage passe par `rl_duel
    # build`, dont `--equip-mythic` / `--equip-relic` / `--graft-*` ecrivent les trois cles que le
    # port ne lit QUE par `unitAbilityStates`. Lier l'ambiant tranche l'indetermination du bon
    # cote -- celui ou la mesure existe.
    bind_ambient_rpc(sid)

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    elev, playable = R3B.board_geometry(args.board)
    lay = P478.LAYOUTS[layout](elev, playable)
    if lay is None:
        raise MontageError(f"montage NON INSTALLE : aucun layout {layout} sur {args.board}")
    rid = (args.runner if args.runner is not None
           else P925.build(args.state_file, args.board, args.seed, lay, porteur))
    print(f"board {args.board} seed {args.seed} | regime {args.regime} (porteur {porteur}) "
          f"| runner {rid}")
    try:
        st = P478.stage(rpc, rid, lay, elev)
        case = mesure(rpc, st, porteur)
        r, corr, mut = case["r"], case["corr"], case["mut"]
        print(f"  traits MESURES sur l'entite : {sorted(case['traits'])}")
        print("  [etage 1] NATIF -- ventilation par COUP et par CIBLE")
        for k, v in case["nat_hits"].items():
            print(f"      {k:<16} {[a for a, _ in v]}  aat {[t for _, t in v]}")
        if args.verbose:
            print("  [etage 2] PORT -- armement `LetTheGalaxyBurnArmAbility.matches`")
            for a in corr["trace"]["arm"]:
                print(f"      target {a['target']:<16} armed {a['armed']}")
            print("  [etage 3] PORT -- canal #179 par facade")
            for c in corr["trace"]["collect"]:
                print(f"      collect voie={c['voie']:<8} tgt {c['tgt']:<16} n={c['n']} "
                      f"pd={c['pd']}")
            for x in corr["trace"]["exec"]:
                print(f"      exec    voie={x['voie']:<8} tgt {x['tgt']:<16} "
                      f"per_hit={x['per_hit']}")
        print(f"  [etage 4] PV   NATIF   {r['nat']}")
        print(f"                 CORRIGE {corr['pv']}")
        print(f"            coups primaire NATIF   {list(r['nat_primaire_hits'])}")
        print(f"                           CORRIGE arme {corr['arme']} + fold {corr['fold']}")
        print(f"  [etage 5] MUTANT PV {mut['pv']} -- appels du canal #179 par la voie ability : "
              f"corrige {corr['n_exec_ability']} coups {corr['n_hits_ability']} | mutant "
              f"{mut['n_exec_ability']} coups {mut['n_hits_ability']}")
        bad = verdict(case)
    finally:
        _ABIL.leaf_executes_additional_hits = _LEAF_NATIF
        if args.runner is None:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 60)
            except Exception:
                pass
    if bad:
        print("[925-r1] ECHEC")
        for b in bad:
            print("   - " + b)
        return 1
    print("[925-r1] OK -- une feuille NUE ne rejoue PAS le canal #179 ; le port egale le natif PV "
          "par cible ET coup par coup, le mutant non")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MontageError as e:
        print(f"[925-r1] MONTAGE : {e}")
        sys.exit(2)
