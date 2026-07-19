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
from engine import weights  # noqa: E402
from engine.playbook import noncomparable as playbooks  # noqa: E402  (namespace unifié ; is_summon)
from engine.playbook import scene as _scene  # noqa: E402  (seam live-feed : build_predictor/refresh_shields)


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


_DEBUG = bool(os.environ.get("ENGINE_DEBUG"))

# Le scoring et la sélection d'action vivent désormais dans engine/ai/ (context / bucket /
# action_generators / tactic) = mirroir du namespace natif IdunBattle.AI. engine_decide (ci-dessous)
# n'est plus qu'un harnais mince : build ctx (couture RPC) -> DefaultAiUnitTactic.calculate_next_action.
# (Les helpers de scoring — _faction, _tile_term, sweep attaque/heal, best_move — ont migré dans
#  engine/ai/action_generators.py ; les flags ENGINE_MOVE_VS_ATTACK/HEAL_MIN_UTIL morts sont retirés.)


def engine_decide(sid: int, rid: int, dv: dict, mov_by_unit: dict, uid: int, wt,
                  predictor: dict | None = None) -> dict:
    """Decision du moteur pour l'unite uid sur l'etat dv. Forme normalisee :
    {kind:"move", to:(c,r)} ou {kind:"ability", target, ability, to:(c,r)}.

    HARNAIS MINCE : construit le contexte (couture RPC) puis delegue au spine natif porte
    (DefaultAiUnitTactic -> generateurs ordonnes -> premiere action non-nulle). Toute la logique de
    scoring/selection vit desormais dans engine/ai/ (context/bucket/action_generators/tactic) =
    mirroir du namespace natif IdunBattle.AI.
    """
    from engine.ai import context as _ai_ctx
    from engine.ai.tactic import DefaultAiUnitTactic
    ctx = _ai_ctx.build(lambda m, b, t: _r(sid, m, b, t), rid, dv, mov_by_unit, uid, wt,
                        predictor, debug=_DEBUG)
    return DefaultAiUnitTactic().calculate_next_action(ctx)


def native_chunk(action: dict) -> dict:
    """Extrait le chunk COMPLET d'une action native — move ∧ ability, PAS seulement le 1er
    message. Une action native est COMPOSÉE : `[MoveUnitMessage?, ActiveAbilityMessage?,
    FinishUnitTurnMessage?]`. On DOIT comparer les DEUX dimensions (position du move +
    ability castée) : sinon un soin/attaque COMPOSÉ (move+ability) échappe à la métrique
    ability — c'est le bug historique `native_first` (s'arrêtait au 1er message → un move+heal
    ne comptait QUE comme move ; cause de la saga « VERDICT B », cf. doctrine mesure-vérité).
    Renvoie {move:{to}|None, ability:{ability,target}|None, finish:bool, unit}."""
    move = ability = None
    finish = False
    unit = None
    for m in (action.get("messages") or []):
        cls = m.get("cls")
        if cls == "MoveUnitMessage" and move is None:
            to = m.get("to") or {}
            move = {"to": (to.get("col"), to.get("row"))}
            unit = unit if unit is not None else m.get("unitId")
        elif cls == "ActiveAbilityMessage" and ability is None:
            ability = {"ability": m.get("abilityType"), "target": m.get("targetId")}
            unit = unit if unit is not None else m.get("casterId")
        elif cls == "FinishUnitTurnMessage":
            finish = True
            unit = unit if unit is not None else m.get("unitId")
    return {"move": move, "ability": ability, "finish": finish, "unit": unit}


def run_agreement(sid: int, rid: int, steps: int, wt, log=print, probe=None) -> dict:
    """Marche la trajectoire NATIVE sur `steps` pas (aiStepDryRun → applyAction) et
    compare la décision du MOTEUR à chaque chunk décisionnel (move/ability). SOURCE
    UNIQUE de la comparaison — réutilisée par `main` ET la suite pytest
    (tests/engine/test_playbook_live.py). MUTE l'état du runner (applique les
    actions natives pour avancer) → runner ISOLÉ recommandé.

    `probe` (optionnel) = sonde de DIAGNOSTIC par-étage (Étape 1 réconciliation,
    cf. engine_agreement_stages.py) appelée à chaque pas COMPARÉ, AVANT applyAction
    (l'état runner est encore l'état de décision) : `probe(step, uid, dv, mov_by_unit,
    nat, eng, predictor)`. None (défaut) = comportement inchangé ; une exception de la
    sonde est loggée, jamais propagée (le walk d'agreement prime sur le diagnostic).

    Retourne {pos:{n,exact,near}, ability:{n,match}, records:[…]}."""
    # Prédicteur OFFLINE capturé 1×/runner (combatSnapshot cold) — nourrit le scoring d'attaque
    # d'engine_decide SANS aiPredict live. None si combatSnapshot KO (le scoring d'attaque saute alors).
    predictor = _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t), rid)
    if predictor is None:
        log("[agreement] combatSnapshot KO — prédicteur offline indisponible (scoring attaque désactivé)")
    n_pos = n_pos_exact = n_pos_near = 0
    n_ab = n_ab_match = 0
    records: list = []
    for step in range(steps):
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 40)
        if not dry.get("ok") or not dry.get("hasNext"):
            log(f"  step {step}: native épuisé / fin de tour ({dry.get('error') or 'no action'})")
            break
        nat = native_chunk(dry.get("action") or {})
        uid = dry.get("activatedUnitId") or nat.get("unit")

        if (nat["move"] or nat["ability"]) and uid is not None:
            # maxRank 32 (défaut 8) : le SWEEP de position par paire (ability,cible) doit voir TOUTES
            # les tuiles d'attaque — le rang natif est arbitraire pour les spéciales (dmg 0-0), la
            # meilleure tuile moteur peut être au-delà du rang 8 (step-11 : (6,3) pour (1150,82)).
            dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
            mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
            # Boucliers = état DYNAMIQUE (accordés en cours de bataille) → refresh par pas comparé
            # (cf. PV.refresh_shields ; le cold de build_predictor rate p.ex. worldTerminator 3989).
            if predictor is not None:
                _scene.refresh_shields(predictor, lambda m, b, t: _r(sid, m, b, t), rid)
            mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
            eng = engine_decide(sid, rid, dv, mov_by_unit, uid, wt, predictor)
            eng_to = eng.get("to")
            # Chunk COMPOSÉ → on compare les DEUX dimensions présentes (move ET/OU ability).
            # POSITIONING — SSI le natif a bougé (l'`eng.to` porte la tuile move-to, y compris
            # pour une action composée où eng.kind == "ability").
            if nat["move"]:
                nat_to = nat["move"]["to"]
                n_pos += 1
                d = hexgeo.distance(eng_to, nat_to) if (eng_to and nat_to) else None
                if d is not None:
                    n_pos_exact += int(d == 0)
                    n_pos_near += int(d <= 1)
                    tag = "EXACT" if d == 0 else f"~{d}hex"
                else:
                    tag = "no-dest"
                records.append({"step": step, "uid": uid, "kind": "move",
                                "native": nat_to, "engine": eng_to, "dist": d,
                                "engine_kind": eng["kind"]})
                log(f"  step {step:2} u{uid}: pos native->{nat_to} engine->{eng_to} "
                    f"[{tag}] (eng={eng['kind']})")
            # ABILITY — SSI le natif a casté (in-place OU composé move+ability). C'est ICI que
            # les soins/attaques COMPOSÉS entrent enfin dans la métrique ability (fix §e).
            if nat["ability"]:
                na = nat["ability"]
                # SUMMON : le `targetId` natif = l'id de l'unité SPAWNÉE (artefact post-exécution,
                # inconnaissable a priori) -> comparaison sur l'ability seule (loggé tel quel).
                tgt_ok = (eng.get("target") == na["target"]
                          or playbooks.is_summon(na["ability"]))
                same_ab = (eng["kind"] == "ability"
                           and tgt_ok
                           and eng.get("ability") == na["ability"])
                n_ab += 1
                n_ab_match += int(same_ab)
                records.append({"step": step, "uid": uid, "kind": "ability",
                                "native": (na["ability"], na["target"]),
                                "engine": (eng.get("ability"), eng.get("target")),
                                "match": same_ab, "engine_kind": eng["kind"]})
                log(f"  step {step:2} u{uid}: ABIL native(ab={na['ability']},tgt={na['target']}) "
                    f"engine={eng['kind']}(ab={eng.get('ability')},tgt={eng.get('target')}) "
                    f"[{'MATCH' if same_ab else 'MISS'}]")
            # Sonde par-étage (Étape 1) : AVANT applyAction — l'état runner est encore
            # celui de la décision (les RPC de la sonde lisent le même état que le natif).
            if probe is not None:
                try:
                    probe(step, uid, dv, mov_by_unit, nat, eng, predictor)
                except Exception as exc:
                    log(f"  [probe] step {step} u{uid}: sonde KO ({exc}) — walk poursuivi")
        else:
            k = "finish" if nat["finish"] else "other"
            log(f"  step {step:2} u{uid}: native={k} (non comparé, on avance)")

        # applique l'action NATIVE (on marche SA trajectoire) pour avancer l'état.
        acts = []
        for m in (dry["action"]["messages"]):
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

    return {"pos": {"n": n_pos, "exact": n_pos_exact, "near": n_pos_near},
            "ability": {"n": n_ab, "match": n_ab_match}, "records": records}


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

    # Marche la trajectoire native + compare (SOURCE UNIQUE : run_agreement).
    res = run_agreement(sid, rid, a.steps, wt)
    pos, ab = res["pos"], res["ability"]

    print()
    if pos["n"]:
        print(f"[positioning] {pos['n']} moves : exact={pos['exact']} ({100*pos['exact']//pos['n']}%)  "
              f"<=1hex={pos['near']} ({100*pos['near']//pos['n']}%)")
    if ab["n"]:
        print(f"[ability]     {ab['n']} casts : match={ab['match']} ({100*ab['match']//ab['n']}%)")
    if not pos["n"] and not ab["n"]:
        print("[agreement] aucun chunk décisionnel comparé")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
