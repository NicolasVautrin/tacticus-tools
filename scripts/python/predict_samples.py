"""Harnais de validation de la PRÉDICTION offline (agreement vs oracle live `decisionView`).

Capture des échantillons d'attaque NORMALE à portée et compare la prédiction du modèle objet
(`engine.playbook.prediction` sur `Scene`) à l'oracle live (dmgMin/dmgMax d'attackPlans). Remplace
l'ancien `predict_validate` (retiré) : même validation, prédicteur = le modèle objet.

⚠ ORACLE = `decisionView.attackPlans` (dmgMin/dmgMax) = un PREVIEW natif (`DamagePredictionQuery.
IdunBattle.Core.Services.DamagePredictionQuery$$GetAllPredictions`) qui peut DIVERGER de la verite per-ability `aiPlaybookPredict`
(= `<Ability>Playbook.MakeDamagePredictions`). Ce harnais ne sample QUE les attaques NORMALES (filtre
`norm_ids`) -- mais meme une attaque NORMALE peut voir son preview attackPlans COLLAPSE min->max alors
que `aiPlaybookPredict`/le moteur gardent la variance (#179, VERIFIE LIVE : astraPrimarisPsy attaque
normale 69, decisionView=(5522,5522) vs aiPlaybookPredict=(2505,5522) == moteur=(2507,5522) ; mecanisme
du collapse encore OUVERT, cf. case-179). Le moteur est construit pour matcher la verite per-ability ->
il diverge LEGITIMEMENT du preview dans ces cas. Pour la verite per-ability, utiliser `predict_sweep.py`
(oracle = `aiPlaybookPredict`, #102), PAS ce preview. Detail :
docs/rl/case-179-decisionview-preview-vs-playbook.md.

Consommé par la suite pytest (`tests/engine/test_predict_live.py`, `test_damage_roll_live.py`,
`test_runner_attack_live.py`) via `build_samples` / `sample_is_clean` / `sample_is_ok`, et en CLI
(`python predict_samples.py --seed 777`).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import rl_collect_batch as R
from engine.playbook import scene as SC
from engine.playbook.scene import Scene
from engine.playbook import prediction
from engine.runner import snapshot as _snapshot   # porte du canal de seed `includeInactive` (#443-r2-b1)
from sibling_script import sibling_script

ROOT = Path(__file__).resolve().parents[2]
# state-file DEDIE au harnais CLI : jamais data/duel_state.json (reserve au runner de travail
# utilisateur). Le CLI build+dispose SON propre runner sans toucher a celui de l'utilisateur
# (discipline coexistence : proprietaire = son --state-file, root-anchored).
STATE_REL = "data/_predict_samples.json"
STATE = ROOT / STATE_REL


def _res(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=60):
    return _res(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def _cheby(a, b) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _drive_into_range(sid, rid, my_team, max_turns):
    """Avance nos unités vers l'ennemi le plus proche jusqu'à un plan d'attaque à portée."""
    amine = 3 if my_team == 1 else 4

    def dec():
        # Canal de SEED (#443-r2-b1) : la vue rendue alimente `SC.step_context` (l'appelant), donc
        # elle passe par `decision_view_seed_body`, la porte NOMMEE du canal `includeInactive` --
        # le seul qui publie les effets POSES mais INERTES. La liste BRUTE reste ACTIF-ONLY
        # (projection dans `step_context` / `ai.context.build`).
        return rpc(sid, "decisionView",
                   _snapshot.decision_view_seed_body(rid, maxRank=3, allAbilities=True), 90)

    def populated(d):
        return [ap for ap in (d.get("attackPlans") or [])
                if any((e.get("ranked") or []) and e["ranked"][0].get("dmgMax") is not None
                       for e in (ap.get("evals") or []))]

    for t in range(max_turns):
        d = dec()
        if d.get("stageName") != "Running":
            return d
        if d.get("currentPlayer") != amine:
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 30); d = dec()
        if len(populated(d)) >= 3:
            return d
        enemies = [(u["id"], (u["pos"]["col"], u["pos"]["row"]))
                   for u in (d.get("units") or [])
                   if u.get("alive") and u.get("team") != my_team and u.get("pos")]
        mov = rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60)
        for mu in (mov.get("units") or []):
            up = mu.get("pos") or {}
            if up.get("col") is None or not enemies:
                continue
            tiles = [(tt["col"], tt["row"]) for tt in (mu.get("tiles") or []) if tt.get("col") is not None]
            if not tiles:
                continue
            cur = (up["col"], up["row"])
            best = min(tiles, key=lambda c: min(_cheby(c, e[1]) for e in enemies))
            if min(_cheby(best, e[1]) for e in enemies) < min(_cheby(cur, e[1]) for e in enemies):
                rpc(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": mu["unitId"], "to": {"col": best[0], "row": best[1]}}}, 30)
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 30)
    return dec()


def build_samples(sid, rid, my_team, max_turns=6):
    """Échantillons d'agrément prédiction pour le runner `rid` DÉJÀ construit : seam cold ->
    drive au contact -> une row par plan d'attaque NORMALE à portée (offline modèle objet vs oracle live)."""
    rpc_b = lambda m, b, t: rpc(sid, m, b, t)
    predictor = SC.build_predictor(rpc_b, rid)
    if predictor is None:
        return []
    print(f"[validate] UnitContext (cold): {len(predictor['ctx_by_id'])} unités")
    dec = _drive_into_range(sid, rid, my_team, max_turns)
    sctx = SC.step_context(predictor, dec)
    scene = Scene.from_predictor_sctx(predictor, sctx, None)
    pos_by_id = sctx["pos_by_id"]
    rows = []
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
            r0 = rk[0]; t_id = ev.get("targetId")
            attack_pos = ((r0.get("col"), r0.get("row")) if r0.get("col") is not None
                          else pos_by_id.get(a_id))
            pred_ev, meta = prediction.make_normal_attack_predictions(scene, a_id, t_id, attack_pos, meta=True)
            res = pred_ev.prediction.accurate_health_damage
            rows.append({
                "att": a_id, "tgt": t_id, "tgtVis": ev.get("targetVis"),
                "base": meta["base"], "pierce": meta["pierce"], "armor": meta["armor"], "hits": meta["hits"],
                "oracle": (r0.get("dmgMin"), r0.get("dmgMax")), "offline": (res.min, res.max),
                "predOpt": bool(r0.get("predOptimistic")), "mods": meta["mods"], "effects": meta["effects"],
            })
    return rows


def sample_is_clean(r):
    """Échantillon EXPLOITABLE : prédiction non-optimiste (les `predOptimistic` ignorent une
    réduction de trigger côté moteur, cf. TF04)."""
    return not r["predOpt"]


def sample_is_ok(r, tol=3):
    """Agrément exact (tolérance arrondi //100 vs Fix64) sur un échantillon clean."""
    om, oM = r["oracle"]; fm, fM = r["offline"]
    return sample_is_clean(r) and _cheby((om, oM), (fm, fM)) <= tol


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--max-turns", type=int, default=6)
    a = ap.parse_args(argv)
    sid = R._resolve_session()
    print(f"[validate] session {sid} — build seed {a.seed}")
    subprocess.run([sys.executable, sibling_script("rl_duel.py"), "build", "--seed", str(a.seed),
                    "--state-file", STATE_REL],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        st = json.loads(STATE.read_text())
        rid = st["runnerId"]; my_team = st.get("myTeam", 1)
        rows = build_samples(sid, rid, my_team, a.max_turns)
        if not rows:
            print("[validate] aucun échantillon d'attaque normale capturé."); return 1
        print(f"\n=== {len(rows)} ÉCHANTILLONS (base=Attack+pierce+armure+MODIFIER effets) ===")
        n_clean = n_ok = 0
        for r in rows:
            clean = sample_is_clean(r)
            if clean:
                n_clean += 1
                n_ok += int(sample_is_ok(r))
        print(f"AGREEMENT exact (+/-3) : {n_ok}/{n_clean}")
        return 0
    finally:
        # dispose du runner du harnais (jamais orphelin, jamais le runner utilisateur)
        subprocess.run([sys.executable, sibling_script("rl_duel.py"), "dispose", "--state-file", STATE_REL],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
