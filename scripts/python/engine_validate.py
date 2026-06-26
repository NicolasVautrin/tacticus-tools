#!/usr/bin/env python
"""Harnais de validation du moteur playbook — le PILIER (cf. docs/rl/playbook-engine.md §4).

Marche la trajectoire de l'IA NATIVE (`aiStepDryRun` = sa décision non-appliquée), et à
chaque pas compare la décision du MOTEUR à celle du jeu sur le MÊME état -> **agreement %**.
On compare au grain du « chunk » natif (1 message/pas) : un MoveUnitMessage -> on compare la
destination du 1er move ; un ActiveAbilityMessage -> on compare (cible, ability).

Premier jet : décision moteur = attaque (attackPlans + aiPredict + barème kill/overkill) si une
cible est à portée, sinon move « avance vers l'ennemi le plus proche » (MovementSuggestion). Le
move-scoring est grossier (à raffiner par l'agreement) ; l'attaque s'appuie sur le barème validé.

Usage: python engine_validate.py [--runner N] [--steps K]
Pré-requis: session Frida warmee + un runner construit (rl_duel build).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import hexgeo  # noqa: E402
import gameconfig as gc  # noqa: E402
from engine import weights, move, leaves  # noqa: E402
from engine.utility import attack_utility  # noqa: E402


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


# Le natif `RangedAdjacentEnemyUtility.ShouldApply` gate sur l'arme/ability RANGED
# (`WeaponProfile.IsRanged`), PAS le flag unité-classe `UnitExtensions.IsRanged` que
# decisionView expose (faux pour les unités HeavyWeapon mêlée-classe : darkaTerminator
# = melee mais PlasmaCannon ranged). On dérive donc « ranged-pour-mouvement » de
# gameconfig (vérité offline) via le visualId : arme Range≥2 OU active attackRangeType==Ranged.
#   def="weapon_or_ability" (défaut) : arme OU ability ranged (capture u96)
#   def="weapon" : arme Range≥2 seulement
_RANGED_DEF = os.environ.get("ENGINE_RANGED_DEF", "weapon_or_ability").lower()
_RANGED_CACHE: dict = {}
_DEBUG = bool(os.environ.get("ENGINE_DEBUG"))


def _is_ranged_unit(visual_id) -> bool:
    """« ranged-pour-mouvement » d'une unité (cf. RangedAdjacentEnemyUtility.ShouldApply),
    dérivé de gameconfig par visualId. Cache par visualId."""
    if not visual_id:
        return False
    if visual_id in _RANGED_CACHE:
        return _RANGED_CACHE[visual_id]
    res = False
    try:
        uid = gc.resolve_unit_id(visual_id)
        u = gc.unit(uid) if uid else None
        if u:
            if any((w.get("Range") or 0) >= 2 for w in (u.get("weapons") or [])):
                res = True
            elif _RANGED_DEF != "weapon":
                for aid in (u.get("activeAbilities") or []):
                    a = gc.ability(aid) or {}
                    if (a.get("attackRangeType") or "").lower() == "ranged":
                        res = True
                        break
    except Exception:
        res = False
    _RANGED_CACHE[visual_id] = res
    return res


def _enemies(units: list, cur_player: int) -> list:
    # ctrl=False => unité adverse ; vivante
    return [u for u in units if not u.get("ctrl") and u.get("alive")
            and u.get("pos")]


def engine_decide(sid: int, rid: int, dv: dict, mov_by_unit: dict, uid: int, wt) -> dict:
    """Décision du moteur pour l'unité uid sur l'état dv. Renvoie une forme normalisée :
    {kind:"move", to:(c,r)} ou {kind:"ability", target, ability, to:(c,r)}."""
    units = dv.get("units") or []
    cur = dv.get("currentPlayer")
    plans = {p.get("unitId"): p for p in (dv.get("attackPlans") or [])}
    enemies = _enemies(units, cur)
    epos = [(e["pos"]["col"], e["pos"]["row"]) for e in enemies]
    me = next((u for u in units if u.get("id") == uid), None)

    # 1. Attaque : evals atteignables (rankCount>0) -> barème kill/overkill via aiPredict.
    #    allAbilities=True => inclut les abilities spéciales d'attaque (ex. DakkaDakkaDakka 1171),
    #    Comparable, MÊME barème → argmax sûr (n'ajoute que des candidats).
    plan = plans.get(uid) or {}
    # Ids d'attaque NORMALE de l'unité (name « *NormalAttack »). Tie-break : à utilité
    # ÉGALE, le natif préfère l'ability SPÉCIALE à l'attaque normale (bucket d'ability
    # active > bucket normal-attack ; RE bucket-tree §10). Ex. seed777 step21 : 1171
    # DakkaDakkaDakka et 69 normal tuent tous deux u84 (util 50) -> natif prend 1171.
    normal_ids = {a.get("id") for a in ((me or {}).get("abilities") or [])
                  if "NormalAttack" in (a.get("name") or "")}
    best = None  # (util, target, ability, tile)
    best_key = None  # (util, is_special) — tie-break spécial>normal
    dbg = []
    for ev in (plan.get("evals") or []):
        if not ev.get("rankCount"):
            continue
        ranked = ev.get("ranked") or []
        if not ranked:
            continue
        tile = (ranked[0].get("col"), ranked[0].get("row"))
        tgt, ab = ev.get("targetId"), ev.get("abilityId")
        pr = _r(sid, "aiPredict", {"runnerId": rid, "unitId": uid, "targetId": tgt,
                                   "abilityType": ab, "col": tile[0], "row": tile[1]}, 30)
        u = attack_utility(pr.get("pred"), wt)
        key = (u, 0 if ab in normal_ids else 1)  # util d'abord, puis spécial > normal
        if _DEBUG:
            p = pr.get("pred") or {}
            dbg.append((ab, tgt, round(u, 1), p.get("killSure"), p.get("kill"),
                        p.get("healthDmgMax"), p.get("hpBefore")))
        if best_key is None or key > best_key:
            best = (u, tgt, ab, tile)
            best_key = key
    if _DEBUG:
        ab_ids = [a.get("id") for a in ((me or {}).get("abilities") or [])]
        print(f"    [dbg u{uid}] abilities={ab_ids} attack_cands(ab,tgt,util,kS,k,dmax,hp)={dbg}",
              file=sys.stderr)
    if best and best[0] > 0:
        return {"kind": "ability", "target": best[1], "ability": best[2], "to": best[3],
                "util": best[0]}

    # 1bis. HEAL (ability Comparable GRANTED-par-passif, ex. TwistedScience_Heal 1167, surfacée
    #        via le pass GetUnusedAbilities du hook). Le natif la cast quand aucune attaque n'est
    #        dispo (sa CustomUtility ~100 = échelle attaque, pas summon). Candidats = cibles UNIT ;
    #        score = montant de soin prédit (aiPredict.healthDmgMax = magnitude de soin). On
    #        soigne la cible au plus gros soin. (CustomUtility faction-15/effet-1355 = raffinement.)
    heal_best = None  # (heal_amt, ability, target)
    for ab in ((me or {}).get("abilities") or []):
        aid, nm = ab.get("id"), (ab.get("name") or "")
        if "Heal" not in nm or ab.get("usable") is False:
            continue
        at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": uid, "abilityType": aid}, 40)
        tgts = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == aid:
                    tgts = [t.get("targetId") for t in (a.get("targets") or [])
                            if t.get("kind") == "unit" and t.get("targetId") is not None]
        for tg in tgts:
            pr = _r(sid, "aiPredict", {"runnerId": rid, "unitId": uid, "targetId": tg,
                                       "abilityType": aid}, 30)
            amt = (pr.get("pred") or {}).get("healthDmgMax") or 0
            if amt > 0 and (heal_best is None or amt > heal_best[0]):
                heal_best = (amt, aid, tg)
    if heal_best:
        return {"kind": "ability", "target": heal_best[2], "ability": heal_best[1],
                "to": None, "util": heal_best[0]}

    # 1ter. Leaf NonComparable (summon) — RÈGLE DE TIR empirique : quand AUCUNE attaque n'est
    #       disponible, l'unité INVOQUE (si une tuile de spawn a ≥1 ennemi adjacent) plutôt que
    #       de seulement bouger. Heuristique = `engine/leaves.py` (AberrantHypermorph = #ennemis
    #       adjacents, RE'd). L'ordre exact summon-vs-move du bucket-tree natif reste à RE (§10) :
    #       on VALIDE cette règle par l'agreement (ne tire que pour les leaves PORTÉES → sûr).
    ctx = {"enemy_positions": epos}
    best_summon = None  # (util, ability, tile)
    for ab in ((me or {}).get("abilities") or []):
        aid = ab.get("id")
        if not leaves.is_leaf(aid) or ab.get("usable") is False:
            continue
        at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": uid, "abilityType": aid}, 40)
        tiles_s = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == aid:
                    tiles_s = [t.get("tile") for t in (a.get("targets") or [])
                               if t.get("kind") == "tile" and t.get("tile")]
        tile_s, su = leaves.best_leaf_tile(aid, tiles_s, ctx)
        if tile_s and su and su >= 1 and (best_summon is None or su > best_summon[0]):
            best_summon = (su, aid, tile_s)
    if best_summon:
        return {"kind": "ability", "target": None, "ability": best_summon[1],
                "to": best_summon[2], "util": best_summon[0]}

    # 2. Sinon move : scoring MovementSuggestion porté (engine/move.py) — somme pondérée
    #    MinDistanceToClosestEnemy + MaxDistanceToEnemies (+ RangedAdjacent ; UnitTile off).
    mu = mov_by_unit.get(uid) or {}
    tiles = mu.get("tiles") or []
    if not tiles or not enemies:
        return {"kind": "move", "to": None}
    origin = None
    if me and me.get("pos"):
        origin = (me["pos"]["col"], me["pos"]["row"])
    # « ranged » au sens du natif (arme/ability ranged via gameconfig), PAS le flag
    # unité-classe decisionView.ranged (rate les HeavyWeapon mêlée-classe type u96).
    ranged = _is_ranged_unit(me.get("visualId")) if me else False
    bt, bu = move.best_move(tiles, origin, epos, wt, ranged)
    return {"kind": "move", "to": bt, "util": bu}


def native_first(action: dict) -> dict:
    """Normalise le 1er message SIGNIFICATIF du chunk natif (move/ability) ; à défaut
    finish ; sinon other."""
    for m in (action.get("messages") or []):
        cls = m.get("cls")
        if cls == "MoveUnitMessage":
            to = m.get("to") or {}
            return {"kind": "move", "to": (to.get("col"), to.get("row")), "unit": m.get("unitId")}
        if cls == "ActiveAbilityMessage":
            return {"kind": "ability", "target": m.get("targetId"),
                    "ability": m.get("abilityType"), "unit": m.get("casterId")}
    for m in (action.get("messages") or []):
        if m.get("cls") == "FinishUnitTurnMessage":
            return {"kind": "finish", "unit": m.get("unitId")}
    return {"kind": "other"}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--steps", type=int, default=12)
    a = ap.parse_args(argv)
    sid = _resolve_session()
    rid = a.runner
    if rid is None:
        rl = _rpc(sid, "listRunners", [], timeout=10).get("result") or []
        first = rl[0] if rl else None
        # listRunners renvoie soit des ints, soit des objets {runnerId, started, seed}.
        rid = first.get("runnerId") if isinstance(first, dict) else first
    if rid is None:
        print("[validate] aucun runner — `rl_duel build` d'abord", file=sys.stderr)
        return 2
    wt = weights.load()
    print(f"[validate] session={sid} runner={rid} steps={a.steps}  {wt}")

    # Métriques : POSITIONING (destination = tuile où va l'unité, unifie move &
    # attack-approach car le natif splitte move|ability) + ABILITY (cast en place).
    n_pos = n_pos_exact = n_pos_near = 0
    n_ab = n_ab_match = 0
    for step in range(a.steps):
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 40)
        if not dry.get("ok") or not dry.get("hasNext"):
            print(f"  step {step}: native épuisé / fin de tour ({dry.get('error') or 'no action'})")
            break
        nat = native_first(dry.get("action") or {})
        uid = dry.get("activatedUnitId") or nat.get("unit")

        # On ne COMPARE que les chunks décisionnels (move/ability) ; finish/other =
        # on applique et on avance (le natif clôt l'activation d'une unité).
        if nat["kind"] in ("move", "ability") and uid is not None:
            dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
            mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
            mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
            eng = engine_decide(sid, rid, dv, mov_by_unit, uid, wt)
            eng_to, nat_to = eng.get("to"), nat.get("to")
            if nat["kind"] == "move":
                # POSITIONING : compare la DESTINATION (peu importe que le moteur
                # l'étiquette move ou attack-approach — c'est la même tuile-cible).
                n_pos += 1
                if eng_to and nat_to:
                    d = hexgeo.distance(eng_to, nat_to)
                    n_pos_exact += int(d == 0)
                    n_pos_near += int(d <= 1)
                    tag = "EXACT" if d == 0 else f"~{d}hex"
                else:
                    tag = "no-dest"
                print(f"  step {step:2} u{uid}: pos native->{nat_to} engine->{eng_to} "
                      f"[{tag}] (eng={eng['kind']})")
            else:  # native ability castée (en place / buff / summon)
                same_ab = (eng["kind"] == "ability"
                           and eng.get("target") == nat.get("target")
                           and eng.get("ability") == nat.get("ability"))
                n_ab += 1
                n_ab_match += int(same_ab)
                print(f"  step {step:2} u{uid}: ABIL native(ab={nat.get('ability')},tgt={nat.get('target')}) "
                      f"engine={eng['kind']}(ab={eng.get('ability')},tgt={eng.get('target')}) "
                      f"[{'MATCH' if same_ab else 'MISS'}]")
        else:
            print(f"  step {step:2} u{uid}: native={nat['kind']} (non comparé, on avance)")

        # applique l'action NATIVE (on marche SA trajectoire) pour avancer l'état.
        msgs = [m for m in (dry["action"]["messages"])]
        acts = []
        for m in msgs:
            if m.get("cls") == "MoveUnitMessage":
                acts.append({"kind": "move", "unitId": m["unitId"],
                             "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
            elif m.get("cls") == "ActiveAbilityMessage":
                acts.append({"kind": "ability", "casterId": m["casterId"],
                             "targetId": m.get("targetId"), "abilityType": m["abilityType"]})
            elif m.get("cls") == "FinishUnitTurnMessage":
                acts.append({"kind": "finish", "unitId": m["unitId"]})
        if acts:
            _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 40)

    print()
    if n_pos:
        print(f"[positioning] {n_pos} moves : exact={n_pos_exact} ({100*n_pos_exact//n_pos}%)  "
              f"≤1hex={n_pos_near} ({100*n_pos_near//n_pos}%)")
    if n_ab:
        print(f"[ability]     {n_ab} casts : match={n_ab_match} ({100*n_ab_match//n_ab}%)")
    if not n_pos and not n_ab:
        print("[agreement] aucun chunk décisionnel comparé")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
