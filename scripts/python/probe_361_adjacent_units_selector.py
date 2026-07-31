"""probe #365 (residu #361-r1) -- `AdjacentUnits` VIT-ELLE dans `GenerateAttackPredictions` ?

LA QUESTION, BINAIRE
--------------------
Les deux batchs 3/4 de `IdunBattle.AI.Playbook.Loki.RammingSpeedPlaybook$$MakeDamagePredictions`
rendent VIDE (etabli par exhaustion : `MakeDamagePredictions` n'a que DEUX `return`, et le capteur
#361 mesure `get_WillBeKill -> TRUE`, ce qui ecarte le retour anticipe). Leurs selecteurs sont

    Friends(Caster@0x48, AdjacentUnits(GetTileToMoveTo(), 1, 3), 3)
    Enemies(Caster@0x48, AdjacentUnits(GetTileToMoveTo(), 1, 3), 3)

`DSLSelectors$$Friends` et `$$Enemies` allouent le MEME `UnitsFromFactionSelector` a un seul bit
pres (`friends = 1` / `0`) et PARTITIONNENT leur entree par `UnitExtensions$$HasFaction` :
les deux vides <=> `AdjacentUnits(GetTileToMoveTo(), 1, 3)` vide.

Il reste alors DEUX suspects, et un seul les separe :
  (A) la composition `AdjacentUnits` elle-meme, evaluee par `TargetsSelector$$SelectUniqueUnits`
      dans le contexte que `ComparablePlaybook<T>$$GenerateAttackPredictions` construit ;
  (B) l'`origin` : l'arbre `RammingSpeedAbility$$GetTileToMoveTo()`.

CE QUE CE PROBE MESURE
----------------------
`ExplosivePresentsPlaybook$$MakeDamagePredictions` (l'un des TROIS seuls appelants de
`GenerateAttackPredictions`, avec `MortisRoundPlaybook` et `RammingSpeedPlaybook`) passe

    ExplosivePresentsAbility$$GetTargets()
        = (Target@0x60 op_Addition AdjacentUnits(Target@0x60, 1, 3)) op_Subtraction Caster@0x48

c'est-a-dire la MEME `AdjacentUnits(..., 1, 3)`, la MEME `op_Subtraction`, la MEME
`SelectUniqueUnits(ctx, 3)` et le MEME `GenerateAttackPredictions` -- avec un `origin` SIMPLE.
Ce bras SEPARE donc (A) de (B), et il n'exige AUCUN capteur neuf.

  bras `control`  (`MortisRound`, selecteur `Entity(target)`) : `GenerateAttackPredictions` NU.
                  Il ne teste PAS `AdjacentUnits` -- il verrouille que le chemin emet, sans quoi
                  le bras discriminant ne voudrait rien dire.
  bras `adjacent` (`ExplosivePresents`) : caster LOIN de la cible.
  bras `adjacent-caster` : le MEME, caster POSE sur un 3e voisin de la cible. L'attendu ne bouge
                  pas (`op_Subtraction Caster@0x48` le retire) -- ce bras discrimine la
                  SOUSTRACTION : un natif qui ne la ferait pas rendrait un event de plus.

Les attendus sont DERIVES du selecteur natif (`montage_361...expected_targets`), jamais ecrits
d'avance ; le probe REFUSE de compter un bras dont la geometrie ne peuple pas le voisinage.

ASCII only (cp1252). Usage (depuis scripts/python, host up, session deja warmee) :
    python probe_361_adjacent_units_selector.py
    python probe_361_adjacent_units_selector.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402
from probe_353r1_ramming_speed_charge_tile import GRAFT, VICTIM, _pos    # noqa: E402
import montage_361_attack_predictions_selector as M                      # noqa: E402


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _predict(sid, rid, cid, tid, ability):
    nat = _r(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": cid, "targetId": tid,
                                        "abilityType": int(ability)}, 120)
    rows = [{"targetId": e.get("targetId"), "healthDmgMin": e.get("healthDmgMin"),
             "healthDmgMax": e.get("healthDmgMax"), "appliedHits": e.get("appliedHits")}
            for e in (nat.get("events") or [])]
    return rows, nat


def measure(sid, arm_key: str, seed: int, level: int, caster_adjacent: bool,
            mutate: str = "none") -> dict:
    arm = M.ARMS[arm_key]
    out: dict = {"arm": arm.key, "caster_adjacent": bool(caster_adjacent), "mutation": mutate,
                 "ability": arm.ability, "ability_name": arm.ability_name,
                 "selector": arm.selector, "seed": seed, "level": level}
    m = None
    try:
        m = M.build_montage(sid, arm, seed=seed, level=level, caster_adjacent=caster_adjacent)
        out["runner"] = m.runner
        out["graft"] = m.graft
        out["geometry"] = {k: list(v) for k, v in (m.geometry or {}).items()}
        if m.errors:
            out["error"] = " | ".join(m.errors)
            return out
        caster, target = m.ids[GRAFT], m.ids[VICTIM]
        out["caster_pos"] = list(_pos(m.dv, caster) or [])
        out["target_pos"] = list(_pos(m.dv, target) or [])
        exp = M.expected_targets(arm, m.board, m.dv, caster, target, mutate=mutate)
        out["expected"] = exp
        rows, nat = _predict(sid, m.runner, caster, target, arm.ability)
        out["events"] = rows
        out["n_events"] = len(rows)
        out["event_targets"] = sorted({int(r["targetId"]) for r in rows if r.get("targetId")})
        out["playbook"] = nat.get("playbookClass")
        out["native_error"] = nat.get("error")
    finally:
        if m is not None:
            M.dispose_montage(sid, m)

    # --- VERDICT DERIVE DES CHAMPS
    exp = out.get("expected") or {}
    if out.get("native_error"):
        out["ok"] = False
        out["verdict"] = "NATIF EN ERREUR : %s -- rien n'est mesure" % out["native_error"]
    elif out.get("playbook") and arm.playbook not in str(out["playbook"]):
        out["ok"] = False
        out["verdict"] = ("MONTAGE KO : le natif a charge %r, pas %r -- la greffe n'expose pas "
                          "l'ability" % (out["playbook"], arm.playbook))
    elif arm.kind == "adjacent" and exp.get("n", 0) < 2:
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT : le voisinage de la cible est VIDE (attendu=%d) "
                          "-- la geometrie ne teste pas `AdjacentUnits`." % exp.get("n", 0))
    elif out.get("n_events") == exp.get("n") and out.get("event_targets") == sorted(exp["ids"]):
        out["ok"] = True
        out["verdict"] = ("SELECTEUR VIVANT : %d events, CIBLES EXACTES %s == attendu (%s)."
                          % (out["n_events"], out["event_targets"], arm.selector))
    elif out.get("n_events") == exp.get("n"):
        out["ok"] = False
        out["verdict"] = ("COMPTE JUSTE mais CIBLES DIFFERENTES : natif=%s attendu=%s -- ecart de "
                          "selecteur, a decomposer." % (out["event_targets"], sorted(exp["ids"])))
    elif out.get("n_events", 0) <= 1 and arm.kind == "adjacent":
        out["ok"] = False
        out["verdict"] = ("SELECTEUR MORT : %d event(s) pour %d attendus (%s). `AdjacentUnits` ne "
                          "rend RIEN dans le contexte de `GenerateAttackPredictions`, meme avec un "
                          "`origin` SIMPLE -- la cause de RammingSpeed n'est donc PAS "
                          "`GetTileToMoveTo`." % (out.get("n_events"), exp.get("n"), arm.selector))
    else:
        out["ok"] = False
        out["verdict"] = ("COMPTE DIFFERENT : %d events pour %d attendus (natif=%s attendu=%s)."
                          % (out.get("n_events"), exp.get("n"), out.get("event_targets"),
                             sorted(exp.get("ids") or [])))
    return out


def run(seed: int = 36500, level: int = 8, verbose: bool = True,
        mutate: str = "none") -> dict:
    sid = _resolve_session()
    out: dict = {"seed": seed, "level": level, "board": M.BOARD, "mutation": mutate, "arms": []}
    if mutate != "none":
        # GARDE ADVERSARIALE : un seul bras suffit, celui ou le terme mute PORTE.
        plan = [("adjacent", True)]
    else:
        plan = [("control", False), ("adjacent", False), ("adjacent", True)]
    for key, cadj in plan:
        res = measure(sid, key, seed, level, cadj, mutate=mutate)
        out["arms"].append(res)
        if verbose:
            _print(res)
    if mutate != "none":
        rouge = [a for a in out["arms"] if not a.get("ok")]
        out["ok"] = bool(rouge)
        out["conclusion"] = (
            "MUTATION %r : le probe ROUGIT (%d/%d bras) -- le bras DISCRIMINE bien ce terme."
            % (mutate, len(rouge), len(out["arms"])) if rouge else
            "MUTATION %r : le probe reste VERT -- le bras NE DISCRIMINE PAS ce terme, son accord "
            "ne prouve rien." % mutate)
        if verbose:
            print("[365] %s" % out["conclusion"])
            print("[365] -> %s" % ("OK" if out["ok"] else "ECHEC"))
        return out

    ctrl = next((a for a in out["arms"] if a["arm"] == "control"), {})
    adjs = [a for a in out["arms"] if a["arm"] == "adjacent"]
    live = [a for a in adjs if a.get("ok")]
    dead = [a for a in adjs if a.get("n_events", -1) <= 1]
    if not ctrl.get("ok"):
        out["ok"] = False
        out["conclusion"] = ("CONTROLE POSITIF EN ECHEC (%s) : `GenerateAttackPredictions` n'emet "
                             "pas meme sur `Entity(target)`. Le bras discriminant ne conclut RIEN "
                             "-- reprendre le montage." % ctrl.get("verdict"))
    elif len(live) == len(adjs) and adjs:
        out["ok"] = True
        out["conclusion"] = (
            "`AdjacentUnits(origin, 1, 3)` est VIVANTE dans le contexte de "
            "`GenerateAttackPredictions` (%d/%d bras exacts, dont le bras caster-adjacent qui "
            "verifie `op_Subtraction Caster@0x48`). Le vide des batchs 3/4 de `RammingSpeed` ne "
            "vient donc PAS de la composition `AdjacentUnits` ni du contexte : il vient du seul "
            "terme qui differe -- l'`origin`, l'arbre "
            "`RammingSpeedAbility$$GetTileToMoveTo()`." % (len(live), len(adjs)))
    elif dead and len(dead) == len(adjs):
        out["ok"] = True
        out["conclusion"] = (
            "`AdjacentUnits(origin, 1, 3)` rend VIDE dans le contexte de "
            "`GenerateAttackPredictions` MEME avec un `origin` SIMPLE (`Target@0x60`), alors que "
            "le controle positif emet. La cause du vide des batchs 3/4 de `RammingSpeed` est donc "
            "la COMPOSITION `AdjacentUnits`/`SelectUniqueUnits(ctx, 3)`, PAS `GetTileToMoveTo`.")
    else:
        out["ok"] = False
        out["conclusion"] = ("BRAS DISCORDANTS : %s -- deux hypotheses ne peuvent pas donner le "
                             "meme resultat ; le montage est a reprendre."
                             % [(a["arm"], a.get("caster_adjacent"), a.get("n_events"),
                                 (a.get("expected") or {}).get("n")) for a in adjs])
    if verbose:
        print("[365] %s" % out["conclusion"])
        print("[365] -> %s" % ("OK" if out.get("ok") else "ECHEC"))
    return out


def _print(res: dict) -> None:
    print("[365] bras=%s caster_adjacent=%s ability=%s runner=%s playbook=%s"
          % (res.get("arm"), res.get("caster_adjacent"), res.get("ability"), res.get("runner"),
             res.get("playbook")))
    print("        geo=%s caster=%s cible=%s"
          % (json.dumps(res.get("geometry")), res.get("caster_pos"), res.get("target_pos")))
    exp = res.get("expected") or {}
    print("        attendu n=%s cibles=%s" % (exp.get("n"), exp.get("detail")))
    print("        natif   n=%s cibles=%s erreur=%s"
          % (res.get("n_events"), res.get("event_targets"), res.get("native_error")))
    for r in res.get("events") or []:
        print("        %s" % json.dumps(r, sort_keys=True))
    print("        %s" % res.get("verdict", res.get("error")))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=36500)
    ap.add_argument("--level", type=int, default=8)
    ap.add_argument("--mutate", choices=sorted(M.MUTATIONS), default="none",
                    help="garde adversariale : attendu volontairement FAUX, le probe DOIT rougir")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(seed=a.seed, level=a.level, verbose=not a.json, mutate=a.mutate)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
