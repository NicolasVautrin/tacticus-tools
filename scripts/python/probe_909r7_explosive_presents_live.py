"""PROBE #909-r7 -- `1170 ExplosivePresents` : le SET de sa face DECISION, CONFRONTE LIVE.

CE QUE CE PROBE A TROUVE. Le residu #909-r1 visait << les 12 actives de kit dont le playbook natif
surcharge `MakeDamagePredictions` >>. Sa population est VIDE sur `master` (re-derivee :
`probe_909_decision_actives_kit.py --liste`), mais son perimetre -- `kind == lineup` -- ECARTE par
construction les porteurs npc. Re-derive sur les **233** cles du dict `active` de
`IdunBattle.AI.PlaybookDatabase`, un porteur de `MakeDamagePredictions` restait SANS VERDICT de face
DECISION : `1170 ExplosivePresents`, porteur `orksRedGobbo` (npc), dette declaree par
`probe_1021_face_decision_au_registre.DETTE`.

L'ECART, MESURE avant le port : natif **5** evenements, port **1**. Sous-prediction MUETTE -- ni
erreur ni crash, l'utilite de 1170 valait le cinquieme de ce que le natif lui donne dans ce montage.

    IdunBattle.AI.Playbook.Loki.ExplosivePresentsPlaybook$$MakeDamagePredictions
        targets = ...ExplosivePresentsAbility$$GetTargets()
                = op_Subtraction( op_Addition(Target, AdjacentUnits(Target, unique: 1, sel: 3)),
                                  Caster )
        damage  = <X>Ability$$GetDamage(abilityState)      # corps DEDUPLIQUE (etiquete
                                                            # `VigilanceEternalAbility$$GetDamage`)
        return GenerateAttackPredictions(caster, casterPosition, target, targets, damage, ..., 0, 0)

⚠ `GenerateAttackPredictions` n'est PAS `GenerateMultiHitAttackPredictions` : la premiere invoque
`IBattleQuery` slot `0x24 = GetAttackPrediction`, la seconde le slot `0x28 =
GetMultiHitAttackPrediction`, dont le corps EST la premiere suivie de `hits - 1` repetitions. Le
chemin plain vaut donc exactement UN coup, et n'appelle jamais `GetDefaultAttackHits` (donc n'ajoute
jamais `ExtraHits`).

MONTAGE -- le VRAI porteur, pas une greffe. `orksRedGobbo` est `kind == npc`, donc hors pool ; le
chemin de stats EXPLICITE (`--explicit-stats orksRedGobbo:5`, #419-r1-tr12-r2) l'y fait entrer AVEC
ses stats npc, ce qui evite la reserve d'une greffe (<< les stats, traits et armes du VRAI porteur
ne sont pas exercees >>). Geometrie : la fixture `_ringed_cast.ring_scenario`.

⚠ DEUX REGIMES A ARMER, sans quoi l'accord ne prouve presque rien :
  * ARMURE (`--armor-target`) -- a armure nulle le profil `Blast` est inobservable ;
  * ELEVATION -- l'anneau de `MC1_67` porte des elevations DIFFERENTES (mesure : 1, 2, 3 autour
    d'une cible en 2), et c'est le seul terme qui separe deux cibles par ailleurs identiques.

⚠ ET L'ARTEFACT DE MESURE QUI A FAILLI FAIRE ACCUSER LE PORT : `make_damage_predictions(...,
attack_pos=None)` SAUTE le terme d'elevation (`playbook/prediction/_shared.py` :
`if scene.elev_by_pos and attack_pos and t_pos`). Sans `attack_pos`, le port sous-predisait de x1,5
toute cible situee PLUS BAS que le caster -- un ecart qui ressemble a un bug de port et qui n'est
qu'un appel incomplet. Le terme suit la TUILE, pas l'unite : verifie par ECHANGE controle des deux
occupants (le x1,5 a suivi la tuile d'elevation 1).

Usage (depuis scripts/python) :

    python probe_909r7_explosive_presents_live.py
    python probe_909r7_explosive_presents_live.py --bras isole     # contre-cas : cible seule

ASCII only. Dispose SES runners, jamais ceux des autres.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_130_placement_sort_rng as P130  # noqa: E402

DECLENCHEUR = {
    "chemins": ("scripts/python/engine/entities/abilities/active_ability.py",
                "scripts/python/engine/playbook/prediction/abilities.py",
                "scripts/python/probe_909r7_explosive_presents_live.py",
                "scripts/python/tests/engine/runner/test_909r7_explosive_presents_live.py"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte au NATIF le SET, l'ORDRE, les COUPS et la MAGNITUDE de la face DECISION "
              "de 1170, sur son porteur REEL monte par `--explicit-stats`.",
}

PORTEUR = "orksRedGobbo:5"        # npc -- entre au pool par le chemin de stats EXPLICITE
PORTEUR_VID = "orksRedGobbo"
ALLY = "orksNob"                  # allie -> exerce le friendly-fire du set nu
ENNEMIS = "necroOverlord,necroWarden,necroDestroyer,necroSpyder"
ABILITY = 1170
BOARD = "MC1_67"
ARMURE = "3000"                   # arme le regime PERCAGE (a armure nulle le profil est inerte)


def _build(state_file, seed="777"):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", BOARD,
           "--state-file", str(state_file), "--p-units", "%s,%s" % (PORTEUR, ALLY),
           "--a-units", ENNEMIS, "--explicit-stats", PORTEUR,
           "--hp-target", "120000", "--hp-player", "120000", "--armor-target", ARMURE, "--no-ai"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not Path(state_file).exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-1200:])
        return None
    return json.loads(Path(state_file).read_text())["runnerId"]


def confronte(rpc, rid, isole: bool) -> dict:
    sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))
    from _ringed_cast import ring_scenario  # noqa: E402
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    from engine.playbook.prediction.abilities import make_damage_predictions
    from engine.runner import snapshot as _snapshot
    from engine import weights as W

    sc = ring_scenario(rpc, rid, PORTEUR_VID, ALLY, rounds=1, place_caster_adjacent=True,
                       isolate_target=isole)
    if sc.get("reason"):
        return {"ok": False, "raison": "montage : %s" % sc["reason"]}

    r = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": int(sc["me"]),
                                  "targetId": int(sc["target"]), "abilityType": ABILITY}, 90)
    if not isinstance(r, dict) or not r.get("ok"):
        return {"ok": False, "raison": "aiPlaybookPredict KO : %s"
                                       % (r if not isinstance(r, dict) else r.get("error"))}
    natif = [{"target": ev.get("targetId"), "hits": ev.get("appliedHits"),
              "min": ev.get("healthDmgMin"), "max": ev.get("healthDmgMax")}
             for ev in (r.get("events") or [])]

    seam = lambda m, b, t: rpc(m, b, t)                                        # noqa: E731
    pred = _scene.build_predictor(seam, rid)
    if pred is None:
        return {"ok": False, "raison": "predicteur offline indisponible -- NON MESURE"}
    dv = rpc("decisionView", _snapshot.decision_view_seed_body(rid, allAbilities=True, maxRank=8),
             180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}
    ctx = _ai_ctx.build(seam, rid, dv, {u.get("unitId"): u for u in (mov.get("units") or [])},
                        int(sc["me"]), W.load(), pred)
    if getattr(ctx, "scene", None) is None:
        return {"ok": False, "raison": "Scene non constructible -- NON MESURE"}
    # ⚠ `attack_pos` OBLIGATOIRE : sans lui le terme d'ELEVATION est saute cote port, et l'ecart
    # qui en resulte accuse le port d'une faute qui est dans l'APPEL.
    mp = next((u.get("pos") for u in (dv.get("units") or []) if u.get("id") == sc["me"]), None)
    apos = (mp["col"], mp["row"]) if mp else None
    evs = make_damage_predictions(ctx.scene, int(sc["me"]), int(sc["target"]), ABILITY,
                                  "ExplosivePresents", attack_pos=apos)
    port = []
    for e in (evs or []):
        dp = getattr(e, "prediction", None)
        acc = getattr(dp, "accurate_health_damage", None) if dp is not None else None
        port.append({"target": getattr(e, "target", None),
                     "hits": getattr(dp, "applied_hits", None) if dp is not None else None,
                     "min": getattr(acc, "min", None) if acc is not None else None,
                     "max": getattr(acc, "max", None) if acc is not None else None})

    tm = rpc("tileMeta", {"runnerId": rid}, 60) or {}
    elev_by_pos = {(t.get("col"), t.get("row")): t.get("elevation")
                   for t in (tm.get("tiles") or [])}
    pos = {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in (dv.get("units") or [])
           if u.get("alive") and u.get("pos")}
    elev = {uid: elev_by_pos.get(p) for uid, p in pos.items()}
    return {"ok": True, "caster": sc["me"], "target": sc["target"], "ally": sc["ally"],
            "ring": list(sc["ring_units"]), "natif": natif, "port": port,
            "attack_pos": apos, "elev": elev, "armure": int(ARMURE)}


def verdict(res: dict, isole: bool) -> int:
    if not res.get("ok"):
        print("NON CONFRONTE :", res.get("raison"))
        return 2
    el = res["elev"]
    print("caster=u%s (elev %s) cible=u%s (elev %s) allie=u%s (elev %s) anneau=%s armure a-units=%s"
          % (res["caster"], el.get(res["caster"]), res["target"], el.get(res["target"]),
             res["ally"], el.get(res["ally"]), res["ring"], res["armure"]))
    print("NATIF :", [(e["target"], e["hits"], e["min"], e["max"]) for e in res["natif"]])
    print("PORT  :", [(e["target"], e["hits"], e["min"], e["max"]) for e in res["port"]])
    if not res["natif"]:
        print("REGIME NON ARME : aucun evenement natif -- rien a confronter")
        return 2
    rc = 0
    if [e["target"] for e in res["natif"]] != [e["target"] for e in res["port"]]:
        print("ECART ORDRE/SET")
        rc = 1
    for a, b in zip(res["natif"], res["port"]):
        if (a["hits"], a["min"], a["max"]) != (b["hits"], b["min"], b["max"]):
            print("ECART u%s : natif %s != port %s"
                  % (a["target"], (a["hits"], a["min"], a["max"]),
                     (b["hits"], b["min"], b["max"])))
            rc = 1
    if not isole:
        cibles = {e["target"] for e in res["natif"]}
        if res["ally"] in cibles:
            print("FRIENDLY-FIRE : OK -- l'ALLIE u%s est PREDIT (set nu, sans wrapper `Enemies`)"
                  % res["ally"])
        else:
            print("ECART FRIENDLY-FIRE : l'allie u%s n'est pas predit" % res["ally"])
            rc = 1
        if res["caster"] in cibles:
            print("ECART : le CASTER est predit (le set natif le SOUSTRAIT)")
            rc = 1
        niv = {el.get(t) for t in cibles if el.get(t) is not None}
        print("ELEVATIONS des cibles :", sorted(niv),
              "-- regime ARME" if len(niv) > 1 else "-- regime DEGENERE (une seule elevation)")
    print("VERDICT :", "le natif et le port predisent la MEME chose" if rc == 0 else "ECART")
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bras", choices=("entoure", "isole"), default="entoure")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--seed", default="777")
    a = ap.parse_args()
    rpc = P130.Rpc()
    sf = Path(a.state_file) if a.state_file else (
        ROOT / "logs" / "runners" / ("p909r7-%s.json" % uuid.uuid4().hex[:8]))
    sf.parent.mkdir(parents=True, exist_ok=True)
    rid = _build(sf, seed=a.seed)
    if rid is None:
        print("NON CONFRONTE : le build a echoue (ce n'est PAS un verdict sur le port)")
        return 2
    try:
        res = confronte(rpc, rid, isole=(a.bras == "isole"))
        return verdict(res, isole=(a.bras == "isole"))
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)
        Path(sf).unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
