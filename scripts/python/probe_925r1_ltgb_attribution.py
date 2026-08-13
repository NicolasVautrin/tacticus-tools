"""#925-r1 -- le `+1 coup` de `LetTheGalaxyBurn` : cible PRIMAIRE (port) ou cible du CLEAVE (natif) ?

## La question binaire

`IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits` monte un
`EffectAdditionalHits` dont le trigger est
`get_OwnerIsCaster & (TargetHasTileEffect | IsPersistentData(0x5ca, Owner, Get(<statique>)))`.
Ce descripteur est consomme par le canal #179
(`IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute`), qui est un
volet de CHAQUE `Attack(...)`. Le montage de #925 en compte TROIS (primaire + 2 cleave), donc trois
occasions d'armer et trois occasions de tirer le coup.

**Sur quelle attaque le coup part-il, NATIF contre PORT ?**

## Ce probe ne fitte AUCUN scalaire -- il DECOMPOSE

  1. ATTRIBUTION NATIVE -- la ventilation par COUP de CHAQUE cible (`Amount`, `Active_Ability_Type`,
     `Effect_Type`), pas seulement le delta de PV. Le coup surnumeraire natif se lit alors comme un
     coup DE PLUS sur une cible nommee, dans un ordre nomme.
  2. ARMEMENT PORT -- chaque evaluation de `LetTheGalaxyBurnArmAbility.matches` : la cible, le
     verdict du `Maybe(LetTheGalaxyBurnChancePct)`, et l'etat du flag apres coup.
  3. CANAL #179 PORT -- chaque appel de `collect_additional_hit_groups` / `execute_additional_hits`
     dans les DEUX facades (`damage_ops/normal.py` = primaire, `damage_ops/ability.py` = cleave) :
     la cible, les groupes retenus, les coups reellement infliges.
  4. CONFRONTATION -- qui porte le coup de chaque cote.

Usage :
    python probe_925r1_ltgb_attribution.py --state-file <ABSOLU>.json [--regime boltstorm|rr]
        [--board MC1_67] [--seed 4463111] [--runner N]

ASCII only.
"""
from __future__ import annotations

import argparse
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


def instrumente(bundle: dict) -> dict:
    """Rejoue l'attaque normale OFFLINE (regime NATIF du drapeau #925) en tracant les trois canaux.

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
                                         "groupes": [getattr(x, "name", None)
                                                     or getattr(x, "source", None) or str(x)[:60]
                                                     for x in (g or [])]})
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
        for mod, voie in ((NORM, "normal"), (ABIL, "ability")):
            mod.collect_additional_hit_groups, mod.execute_additional_hits = originaux[voie]
    after = {i: (state.get_entity(i).get_component(HealthComponent).hp
                 if state.get_entity(i) is not None
                 and state.get_entity(i).get_component(HealthComponent) is not None else None)
             for i in before}
    d = {nom(i): int(before[i]) - int(after[i]) for i in before
         if before.get(i) is not None and after.get(i) is not None and before[i] != after[i]}
    rr = runner.damage_handler.last or {}
    return {"trace": trace, "pv": d, "last": rr}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default=P478.BOARD)
    ap.add_argument("--seed", default=P478.SEED)
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--regime", default="boltstorm", choices=tuple(P925.REGIMES))
    args = ap.parse_args()
    porteur, layout = P925.REGIMES[args.regime]

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    elev, playable = R3B.board_geometry(args.board)
    lay = P478.LAYOUTS[layout](elev, playable)
    if lay is None:
        raise MontageError(f"aucun layout {layout} sur {args.board}")
    rid = (args.runner if args.runner is not None
           else P925.build(args.state_file, args.board, args.seed, lay, porteur))
    print(f"board {args.board} seed {args.seed} regime {args.regime} porteur {porteur} runner {rid}")
    try:
        st = P478.stage(rpc, rid, lay, elev)
        # CAPTURE de l'action NATIVE complete : `replay` ne rend la ventilation que pour la cible
        # primaire, or la question porte sur TOUTES les cibles. `_native_hits` est le seul point ou
        # `a0` transite -- on l'enveloppe plutot que de rejouer le cast (il n'a lieu qu'UNE fois).
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

        # --- etage 1 : ATTRIBUTION NATIVE, par cible, coup par coup
        a0 = capt.get("a0") or {}
        print("\n[etage 1] NATIF -- ventilation par COUP et par CIBLE (ordre d'emission)")
        import json as _json
        seq = []
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = _json.loads(td) if isinstance(td, str) else td
            if "Amount" not in td:
                continue
            seq.append((by_vis.get(td.get("Target_Id"), td.get("Target_Id")),
                        td.get("Amount"), td.get("Active_Ability_Type"), td.get("Effect_Type")))
        for i, (t, a, k, ft) in enumerate(seq):
            print(f"    [{i:02d}] {t:<16} amount {a:<7} aat {k} eft {ft}")
        print(f"    PV natif {r['nat']}")

        # --- etages 2-3 : PORT instrumente
        ins = instrumente(bundle)
        print("\n[etage 2] PORT -- armement `LetTheGalaxyBurnArmAbility.matches`")
        for a in ins["trace"]["arm"]:
            print(f"    owner {a['owner']:<16} actor {a['actor']:<16} target {a['target']:<16} "
                  f"armed {a['armed']}")
        print("\n[etage 3] PORT -- canal #179 par facade")
        for c in ins["trace"]["collect"]:
            print(f"    collect voie={c['voie']:<8} att {c['att']:<16} tgt {c['tgt']:<16} "
                  f"n={c['n']} pd={c['pd']} {c['groupes']}")
        for x in ins["trace"]["exec"]:
            print(f"    exec    voie={x['voie']:<8} att {x['att']:<16} tgt {x['tgt']:<16} "
                  f"per_hit={x['per_hit']} total={x['total']}")
        print(f"\n[etage 4] PV port {ins['pv']}")
        print(f"          last.per_hit          {list((ins['last'] or {}).get('per_hit') or [])}")
        print(f"          last.additional_hits  "
              f"{list(((ins['last'] or {}).get('additional_hits') or {}).get('per_hit') or [])}")
        print(f"          last.primary_fold     "
              f"{list((((ins['last'] or {}).get('primary_fold') or {}).get('attack') or {}).get('per_hit') or [])}")
    finally:
        if args.runner is None:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 60)
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MontageError as e:
        print(f"[925-r1] MONTAGE : {e}")
        sys.exit(2)
