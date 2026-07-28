#!/usr/bin/env python
"""Probe #192 -- ISOLATION + validation de `SereneUnifierSenseOfStone` (EffectType 0x491 = 1169).

CE QUE CE PROBE ETABLIT, dans l'ordre, et pourquoi cet ordre :

  [1] QUI PORTE L'EFFET. On imprime `decisionView.units[].effects` unite par unite. Le decompile
      (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SereneUnifierAbility$$CreateBehaviour`)
      dit que 1169 est pose PAR UN `AddEffect(0x491, ..., targets = selecteur, TurnsFromRounds(1))`
      -- donc MATERIALISE sur CHAQUE beneficiaire, PAS une aura source-side invisible. Ce point
      decide le CANAL de port (`create_effect_damage_malus_for_defense` standard vs `create_aura_*`)
      et il se lit directement dans la capture.

  [2] IMPUTATION. Le symptome de depart (« tout banc embarquant `tauAunShi` mesure la MOITIE du
      degat attendu ») est un CONSTAT DE BANC, pas une preuve. On monte donc DEUX bancs identiques
      (meme seed, meme board, meme caster, meme geometrie, memes 2 cibles frappees) qui ne different
      QUE par l'unite d'appoint du roster adverse :
        banc A -> `tauAunShi`      (porteur de SereneUnifier)
        banc B -> substitut vanille (aucune aura d'equipe)
      Si le rapport offline/live vaut 2,000 en A et 1,000 en B, ET que le seul effet different chez
      les cibles est 1169, le coupable est NOMME -- pas devine.

  [3] REGRESSION. Apres le port de la classe d'effet, le MEME banc A doit rendre 1,000.

Le vehicule de degat est le cast 1137 `MurderousSwing` de `worldExecutions` (Tarvakh), monte avec
les helpers de `probe_murderous_swing_1137` : le caster NE BOUGE PAS et on ne laisse JAMAIS l'IA
jouer (`applyAction` n'applique qu'une action), donc le degat reste attribuable. On ne fitte aucun
scalaire : le rapport est lu sur DEUX cibles d'armures differentes a la fois (un modificateur
multiplicatif commun ne peut pas etre un accident du noeud de degat -- cf. `probe_ms1137_stage`).

DEUX `endturn` SONT OBLIGATOIRES AVANT LA MESURE, et c'est une consequence du decompile, pas un
bricolage : le trigger est `On(0x13 = TurnStarted) & <cond@0xa0> & get_OwnerIsCaster`
(`SereneUnifierAbility$$CreateTrigger`) -- l'effet n'existe PAS tant que l'equipe d'Aun'Shi n'a pas
DEMARRE un tour. Sur un banc sans `endturn` (celui de `probe_murderous_swing_1137`), 1169 est absent
et le rapport vaut deja 1,000 : c'est le meme banc, pas la meme phase de bataille.
Sequence : build -> endturn (mon tour) -> endturn (tour adverse : Aun'Shi pose 1169 sur
self + adjacents + T'au a <=2) -> placement des cibles -> cast.

ASCII only (cp1252). Usage :
  python probe_192_sense_of_stone.py                 # bancs A + B
  python probe_192_sense_of_stone.py --only A
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import json                                                             # noqa: E402

import probe_murderous_swing_1137 as MS                                 # noqa: E402
from rl_collect_batch import _resolve_session                           # noqa: E402
from engine.entities.pathfinding.board import Board                     # noqa: E402
from engine.runner.snapshot import load_state                           # noqa: E402
from engine.runner.runner import Runner                                 # noqa: E402
from engine.runner.messages import ActiveAbilityMessage                 # noqa: E402

# Banc A : le porteur de SereneUnifier (passif `tauAunShi`, TriggeredAbilityType 1145).
ROSTER_A = "tauAunShi,astraBullgryn,tauMarksman"
# Banc B : MEMES deux cibles, unite d'appoint remplacee par une VANILLE (aucune aura d'equipe).
# `bloodIntercessor` (Mataneo) -- `python unit_map.py vanilla-target`.
ROSTER_B = "bloodIntercessor,astraBullgryn,tauMarksman"

SENSE_OF_STONE = 1169


def _effects_by_unit(dv):
    """`decisionView.units[].effects` -> {unit_id: [(name, effectType, remaining, source)]}."""
    out = {}
    for u in (dv.get("units") or []):
        out[u.get("id")] = [(e.get("name"), e.get("effectType"), e.get("remaining"), e.get("source"))
                            for e in (u.get("effects") or [])]
    return out


def _visual_by_unit(dv):
    return {u.get("id"): u.get("visualId") for u in (dv.get("units") or [])}


def _build(state_file: Path, roster: str, seed: int, hp_target: int, board_id: str, rank: int) -> int:
    """Copie de `probe_murderous_swing_1137.build` avec le RANK paramétrable — c'est ce qui fait
    varier le niveau d'ability du porteur, donc l'entree lue dans la courbe `dmgReductionPct[level]`
    (25 -> 50). Un port qui aurait fige la magnitude a 50 passerait a rank 17 et TOMBERAIT ici."""
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board_id, "--rank", str(rank),
           "--p-units", MS.TARVAKH, "--a-units", roster,
           "--crit", "0,0", "--block-target", "0,0"]
    # `--hp-target` met AUSSI `Armor`/`FixedArmor` a 0 (cf. runner.md) : indispensable pour survivre
    # au cast multi-coups du banc COMBAT, mais il faut pouvoir s'en passer sur la face DECISION
    # (le harnais `predict_samples` lit `meta["armor"]`, absent quand l'armure a ete forcee a 0).
    if hp_target:
        cmd += ["--hp-target", str(hp_target)]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[192] build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
        sys.exit(2)
    return int(json.loads(state_file.read_text())["runnerId"])


def run_with_turns(roster: str, k: int, seed: int, hp_target: int, board_id: str, turns: int = 2,
                   rank: int = 17):
    """MEME sequence que `probe_murderous_swing_1137.run`, avec `turns` `endturn` INSERES entre le
    build et le placement -- c'est ce qui fait DEMARRER le tour de l'equipe adverse, donc ce qui
    declenche `On(TurnStarted)` du passif SereneUnifier et materialise 1169 sur ses beneficiaires.
    Les `endturn` sont joues AVANT `setup` (qui exige `currentPlayer == moi` et le caster activable)."""
    MS.ENEMIES = roster
    sid = _resolve_session()
    state = PYDIR / ("probe_192_%s_r%d.json" % (board_id, rank))
    rid = _build(state, roster, seed, hp_target, board_id, rank)
    try:
        bg = MS._r(sid, "boardGraph", {"runnerId": rid}, 60)
        if not bg.get("tiles"):
            return {"error": "boardGraph indispo"}
        board = Board(bg["tiles"], adjacency="native_sym")
        for _ in range(turns):
            MS.endturn(sid, rid)
        sc = MS.setup(sid, rid, board, k)
        if isinstance(sc, dict):
            return {"error": sc["reason"]}
        caster, adj, target = sc
        snap = {"dv": MS.view(sid, rid),
                "ob": MS._r(sid, "observeBattle", {"runnerId": rid}, 40),
                "snap": MS._r(sid, "combatSnapshot", {"runnerId": rid}, 60),
                "rng": MS._r(sid, "dumpRng", {"runnerId": rid}, 30)}
        res = MS._r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster, "targetId": target,
            "abilityType": MS.ABILITY}}, 90)
        a0 = (res.get("actions") or [{}])[0]
        live = {}
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == MS.ABILITY:
                live.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
        st = load_state(snap["dv"], snap["ob"], snap["snap"], board=board)
        if isinstance(snap["rng"], dict) and snap["rng"].get("mt"):
            st.rng = MS.seed_rng(snap["rng"])
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=caster, target_id=target,
                                          ability_type=MS.ABILITY))
        return {"caster": caster, "adjacent": adj, "target": target, "live_damage": live,
                "live_mutated": bool(a0.get("mutated")), "last": runner.ability_handler.last or {},
                "snapshot": snap, "board": board}
    finally:
        MS._r(sid, "disposeRunner", {"runnerId": rid}, 30)
        state.unlink(missing_ok=True)


def bench(label: str, roster: str, k: int, seed: int, hp_target: int, board_id: str, turns: int = 2,
          rank: int = 17):
    r = run_with_turns(roster, k, seed, hp_target, board_id, turns=turns, rank=rank)
    if "error" in r:
        print("[%s] ERROR: %s" % (label, r["error"]))
        return None
    dv = r["snapshot"]["dv"]
    eff, vis = _effects_by_unit(dv), _visual_by_unit(dv)
    print("[%s] roster=%s caster=u%s cibles=%s" % (label, roster, r["caster"], r["adjacent"]))
    # niveau/multiplier REELLEMENT lus par la magnitude (`ConfigVar(0x46)` -> dmgReductionPct[level])
    for u in ((r["snapshot"]["snap"] or {}).get("units") or []):
        uc = u.get("unitConfig") or {}
        if uc:
            print("    cfg u%-4s %-22s passiveAbLvl=%s activeAbLvl=%s mult=%s"
                  % (u.get("entityId") or u.get("squadId"), u.get("visualId"),
                     uc.get("passiveAbilityLevel"), uc.get("activeAbilityLevel"),
                     uc.get("abilityVariablesMultiplierPercentage")))
    for uid in sorted(eff):
        names = ["%s(t=%s,rem=%s,src=%s)" % (n, t, rm, s) for (n, t, rm, s) in eff[uid]]
        mark = " <== CIBLE" if uid in r["adjacent"] else ""
        print("    u%-4s %-22s effets=%s%s" % (uid, vis.get(uid), names or "-", mark))
    off = {}
    for h in (r["last"].get("hits") or []):
        off[h.get("target")] = sum((h.get("attack") or {}).get("per_hit") or [])
    ratios = {}
    for t in r["adjacent"]:
        lv = sum(r["live_damage"].get(t) or [])
        ov = off.get(t) or 0
        ratios[t] = (ov / lv) if lv else None
        carries = any(e[1] == SENSE_OF_STONE for e in eff.get(t, []))
        print("[%s] u%-4s live=%-8s off=%-8s ratio=%s  porte_1169=%s"
              % (label, t, lv, ov, ("%.4f" % ratios[t]) if ratios[t] else "n/a", carries))
    return {"ratios": ratios, "effects": eff, "targets": r["adjacent"]}


def decision_face(seed: int, board_id: str, rank: int = 17):
    """FACE DECISION — la prediction NATIVE applique-t-elle 1169 ?

    C'est la question qu'il ne faut PAS supposer : le hook `ai-step/projection.ts` porte un
    commentaire affirmant que « CalculateDamagePredictionScenario models only armor + stat caps »
    et que les reducteurs defensifs ne tirent qu'a la resolution reelle (flag `predOptimistic`,
    regex `/Reduce(Dmg|Damage|Hits)|HitReduction/i` -- qui ne matche PAS « SereneUnifierSenseOfStone »),
    en citant Aun'Shi en exemple. Si c'etait vrai pour 1169, porter la reduction ferait DIVERGER
    la face DECISION alors qu'elle repare la face COMBAT.

    Mesure : `predict_samples.build_samples` confronte, pour chaque plan d'attaque NORMALE,
    l'oracle natif (`decisionView.attackPlans[].ranked[0].dmgMin/dmgMax`) a la prediction OFFLINE.
    On isole les lignes dont la CIBLE porte 1169."""
    import predict_samples as PV
    from engine.playbook import scene as SC
    from engine.playbook.scene import Scene
    from engine.playbook import prediction
    sid = _resolve_session()
    state = PYDIR / ("probe_192_decision_%s.json" % board_id)
    rid = _build(state, ROSTER_A, seed, 0, board_id, rank)
    try:
        # MEME chaine que `predict_samples.build_samples` (drive au contact -> Scene -> une row par
        # plan d'attaque NORMALE), recopiee ici SANS le `meta["armor"]` : sur ce banc, une prediction
        # sort par la branche degradee `tile_pos is None` (meta = {"mv71","tile"}) et `build_samples`
        # leve KeyError -- bug PREEXISTANT du harnais, hors perimetre #192.
        rpc_b = lambda m, b, t: PV.rpc(sid, m, b, t)                       # noqa: E731
        predictor = SC.build_predictor(rpc_b, rid)
        if predictor is None:
            print("[decision] predictor indisponible")
            return
        # `endturn` EXPLICITES d'abord (le drive n'en joue pas forcement : si les unites sont deja a
        # portee il rend la main tout de suite, et 1169 n'existe alors PAS), puis on RAMENE la main a
        # l'equipe de TARVAKH -- sans ca les seuls `attackPlans` lus sont ceux des PORTEURS qui
        # attaquent, ce qui exerce le canal ATTAQUANT et jamais le canal DEFENSEUR que 1169 emprunte.
        dec = MS.view(sid, rid)
        tar = next((u for u in (dec.get("units") or []) if u.get("visualId") == MS.TARVAKH), None)
        if tar is None:
            print("[decision] Tarvakh absent du build")
            return
        my_team = tar.get("owner")
        for _ in range(2):
            MS.endturn(sid, rid)
        # POSITIONS DRIVEES (jamais subies) : on amene Tarvakh sur un voisin LIBRE d'un porteur, ce
        # qui garantit un `attackPlans` dont la CIBLE porte 1169. `_drive_into_range` ne suffit pas :
        # il rend la main des que les unites sont « a portee », sans garantir QUI est ciblable.
        dec = MS.view(sid, rid)
        eff0 = _effects_by_unit(dec)
        carrier_ids = [uid for uid, es in eff0.items()
                       if any(e[1] == SENSE_OF_STONE for e in es) and uid != tar.get("id")]
        bg = MS._r(sid, "boardGraph", {"runnerId": rid}, 60)
        if not bg.get("tiles") or not carrier_ids:
            print("[decision] pas de porteur ciblable (carriers=%s)" % carrier_ids)
            return
        from engine.entities.pathfinding.board import Board
        board = Board(bg["tiles"], adjacency="native_sym")
        alive = {u.get("id"): u for u in (dec.get("units") or []) if u.get("alive")}
        occupied = {(u["pos"]["col"], u["pos"]["row"]) for u in alive.values() if u.get("pos")}
        placed = False
        for cid in carrier_ids:
            cp = alive.get(cid, {}).get("pos") or {}
            if cp.get("col") is None:
                continue
            centre = board.id_at(cp["col"], cp["row"])
            for n in board.neighbours_native(centre):
                if not board.walkable(n):
                    continue
                coord = board.coord(n)
                if coord in occupied:
                    continue
                MS.move(sid, rid, tar["id"], coord)
                placed = True
                break
            if placed:
                break
        if not placed:
            print("[decision] aucun voisin libre autour d'un porteur")
            return
        dec = MS.view(sid, rid)
        sctx = SC.step_context(predictor, dec)
        scene = Scene.from_predictor_sctx(predictor, sctx, None)
        pos_by_id = sctx["pos_by_id"]
        eff, vis = _effects_by_unit(dec), _visual_by_unit(dec)
        carriers = {uid for uid, es in eff.items() if any(e[1] == SENSE_OF_STONE for e in es)}
        print("[decision] porteurs de 1169 : %s" % sorted(carriers))
        hit = 0
        for ap in (dec.get("attackPlans") or []):
            a_id = ap.get("unitId")
            if a_id not in predictor["ctx_by_id"]:
                continue
            norm_ids = {ab.get("id") for u in (dec.get("units") or []) if u.get("id") == a_id
                        for ab in (u.get("abilities") or []) if ab.get("kind") == "normal"}
            for ev in (ap.get("evals") or []):
                if norm_ids and ev.get("abilityId") not in norm_ids:
                    continue
                rk = ev.get("ranked") or []
                if not rk or rk[0].get("dmgMax") is None:
                    continue
                r0, t_id = rk[0], ev.get("targetId")
                attack_pos = ((r0.get("col"), r0.get("row")) if r0.get("col") is not None
                              else pos_by_id.get(a_id))
                res = prediction.make_normal_attack_predictions(
                    scene, a_id, t_id, attack_pos).prediction.accurate_health_damage
                oracle = (r0.get("dmgMin"), r0.get("dmgMax"))
                carried = t_id in carriers
                hit += 1 if carried else 0
                print("[decision] %s u%-4s -> u%-4s %-20s oracle=%s offline=(%s, %s) predOpt=%s"
                      % ("1169" if carried else "----", a_id, t_id, vis.get(t_id), oracle,
                         res.min, res.max, bool(r0.get("predOptimistic"))))
        print("[decision] %d echantillons ciblent un porteur de 1169" % hit)
    finally:
        MS._r(sid, "disposeRunner", {"runnerId": rid}, 30)
        state.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--seed", type=int, default=20137)
    ap.add_argument("--hp-target", type=int, default=500000)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--only", default=None, choices=["A", "B"])
    ap.add_argument("--decision", action="store_true",
                    help="face DECISION : oracle natif (attackPlans) vs prediction offline")
    ap.add_argument("--turns", type=int, default=2,
                    help="endturn joues avant la mesure (2 = l'equipe adverse a demarre un tour)")
    ap.add_argument("--rank", type=int, default=17,
                    help="rank du build -- fait varier l'entree lue dans dmgReductionPct[level]")
    a = ap.parse_args()
    if a.decision:
        decision_face(a.seed, a.board, a.rank)
        return 0
    res = {}
    if a.only in (None, "A"):
        res["A"] = bench("A/aunshi", ROSTER_A, a.k, a.seed, a.hp_target, a.board, a.turns, a.rank)
    if a.only in (None, "B"):
        res["B"] = bench("B/vanilla", ROSTER_B, a.k, a.seed, a.hp_target, a.board, a.turns, a.rank)
    print("[192] VERDICT %s" % {k: (v or {}).get("ratios") for k, v in res.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
