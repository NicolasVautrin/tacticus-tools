#!/usr/bin/env python
"""Probe #345 -- la FORMULE du terme BOUCLIER de la prediction (`AccurateShieldDamage`).

CE QUE #342 A LAISSE OUVERT
---------------------------
#342 a debloque le levier (faire POSER un bouclier en bataille) et confronte l'ARRONDI du
terme, mais pas sa FORMULE. Sa mesure : `shieldDmg = [3875, 5483]` pour
`totalDmg = [4813, 6005]` avec un bouclier de 5483 -- donc `shieldDmgMin` n'est PAS
`min(shield, totalDmgMin)`. Le modele evident etait REFUTE, sans modele de remplacement.

LA FORMULE, LUE AU DECOMPILE (build `rnca9r7q6c`)
------------------------------------------------
`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw`, PAR COUP :

    shield        = IdunBattle.Entities.UnitExtensions$$GetShield(defender)
    remShieldMin  = Math.Max(0, shield - prev.Damage.ShieldDamage.Min)
    remShieldMax  = Math.Max(0, shield - prev.Damage.ShieldDamage.Max)
    base          = IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64(...)
    blockedMin    = IdunBattle.Core.Services.DamageCalculations$$CalculateDamageBlockedByShield(
                        remShieldMin, base.Min, attacker, defender)   = Math.Min(remShieldMin, (int)base.Min)
    blockedMax    = ... (remShieldMax, base.Max)                      = Math.Min(remShieldMax, (int)base.Max)
    DefaultScenario.Damage.ShieldDamage = new MinMaxDamage(blockedMin, blockedMax)   # cap VIDE
    CurrentShield@+0x04                 = remShieldMax
    AccurateShieldDamage@+0x50          = new MinMaxDamage(DefaultScenario.Damage.ShieldDamage.Min,
                                                           .Max, cap: CurrentShield)

`IdunBattle.Core.Services.MinMaxDamage$$.ctor` appelle `MinMaxDamage$$ApplyCap` : les DEUX
bornes sont donc rabattues a `CurrentShield`. `IdunBattle.Core.Services.DamagePredictionResult$$Add`
cumule PAR PISTE (min+=min, max+=max) et re-applique le cap.

TROIS FAITS QUI EXPLIQUENT LA MESURE DE #342
--------------------------------------------
1. le bouclier absorbe la base AVANT percage/armure/%-mods, la sante est POST ;
2. `TotalDamage@+0x60` = `MinMaxDamage(healthFix64).Add(shieldFix64)` -- il somme les deux
   termes AVANT le cap de sante (`FillUpStatComponent$$MaxReduceByMinimum`) et AVANT le cap
   de bouclier ; `TotalDamage != AccurateHealthDamage + AccurateShieldDamage` ;
3. le rem est PER-PISTE (`remShieldMin` pour la borne min, `remShieldMax` pour la max), mais
   le cap `CurrentShield = remShieldMax` rabat ensuite la piste min -- et comme
   `remShieldMax <= remShieldMin`, cela EQUIVAUT a n'utiliser que `remShieldMax` :
       min(min(base.Min, remShieldMin), remShieldMax) == min(base.Min, remShieldMax)
   C'est exactement ce que fait le port (`engine/services/damage_prediction.py`), par un
   chemin different. L'equivalence est ALGEBRIQUE, pas fortuite -- ce probe la MESURE.

CE QUE CE PROBE CONFRONTE
-------------------------
Pour chaque `Damage` balaye (trois regimes : SOUS-CAP / CAP PARTIEL / SUR-CAP) :

  * le terme bouclier NATIF (`aiPlaybookPredict` -> `AccurateShieldDamage`) ;
  * le terme bouclier du PORT (`<Playbook>.MakeDamagePredictions` -> `composite_fields()`) ;
  * le modele EVIDENT `M1 = [min(shield, totalDmgMin), min(shield, totalDmgMax)]`, celui
    que #342 a refute -- reevalue ici sur chaque regime pour que la refutation soit une
    MESURE reproductible et pas une citation ;
  * le modele `M2 = [min(shield, healthDmgMin + shieldDmgMin), ...]` (variante « total =
    sante + bouclier ») -- second candidat plausible, separe par les memes regimes.

Un modele qui reproduit UN couple ne prouve rien : le verdict exige l'accord du port sur les
TROIS regimes, et la divergence d'au moins un modele concurrent sur au moins un regime.

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_345_shield_prediction_formula.py
    python probe_345_shield_prediction_formula.py --attacker emperNoiseMarine --victim necroWarden
    python probe_345_shield_prediction_formula.py --board C1_03 --center 3,6
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                          # noqa: E402
from engine.weights import load as load_weights                             # noqa: E402
from engine.playbook import scene as scene_mod                              # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK                   # noqa: E402
from engine.ai import context as _ai_ctx                                    # noqa: E402
from probe_r34_overkill_decision import (view, by_visual, place_ring,        # noqa: E402
                                         playbook_events, normal_attack_id)

ATTACKER = "ultraInceptorSgt"   # attaquant SANS `ThrillSeekers` (cf. #333 / #195)
FILLER_P = "astraBullgryn"      # 2e unite de mon camp : sans elle l'attaque finit mon tour
VICTIM = "genesPrimus"          # la cible mesuree -- c'est ELLE qui recoit le bouclier
SHIELDER = "thousSorcerer"      # porteur d'`ArcaneShield`, place DANS L'EQUIPE DE LA VICTIME
BOARD = "MC1_67"
CENTER = (3, 4)

CALIB_DAMAGE = 200              # sonde en regime NON cape : donne le ratio degat/`Damage`


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed: int, roster, board: str, damage=None) -> int:
    """`rl_duel build` -- board CHOISI (runner.md sec.2). `--crit 0,0` / `--block-target 0,0`
    neutralisent les canaux qui bougeraient les bornes pour une raison ETRANGERE au bouclier."""
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board, "--rank", "17",
           "--p-units", ",".join(roster["p"]), "--a-units", ",".join(roster["a"]),
           "--crit", "0,0", "--block-target", "0,0", "--no-ai"]
    if damage is not None:
        cmd += ["--unit-stat", "%s:Damage=%d" % (roster["p"][0], int(damage))]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _port_prediction(sid, rid, wt, att_id, tgt_id, ability):
    """Le terme bouclier PRODUIT par le port : ctx offline -> `MakeDamagePredictions` ->
    `DamagePredictionResult`. On rend le RESULTAT COMPLET (pas seulement le composite) pour
    pouvoir confronter aussi `TotalDamage`, que le composite n'expose pas."""
    rpc = lambda m, b, t=60: _r(sid, m, b, t)                       # noqa: E731
    predictor = scene_mod.build_predictor(rpc, rid)
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    ctx = _ai_ctx.build(rpc, rid, dv, mov_by_unit, int(att_id), wt, predictor)
    tile = ctx.scene.pos(int(att_id))
    evs = NORMAL_ATTACK_PLAYBOOK.make_damage_predictions(ctx, tile, int(tgt_id),
                                                         int(ability)) or []
    main = next((e for e in evs if e.target == int(tgt_id)), evs[0] if evs else None)
    if main is None:
        return None
    dp = main.prediction
    return {"shieldDmgMin": dp.accurate_shield_damage.min,
            "shieldDmgMax": dp.accurate_shield_damage.max,
            "healthDmgMin": min(dp.accurate_health_damage.min, dp.current_health),
            "healthDmgMax": min(dp.accurate_health_damage.max, dp.current_health),
            "totalDmgMin": dp.total_damage.min, "totalDmgMax": dp.total_damage.max,
            "shieldBefore": dp.shield, "appliedHits": dp.applied_hits}


def _native_prediction(sid, rid, att_id, tgt_id, ability) -> dict | None:
    """Les champs BRUTS de l'event natif -- `AccurateShieldDamage`, `TotalDamage`,
    `CurrentShield`, lus par le decodeur PAR NOM (#279)."""
    evs = playbook_events(sid, rid, int(att_id), int(tgt_id), int(ability))
    ev = next((e for e in evs if e.get("targetId") == int(tgt_id)), None)
    if ev is None:
        return None
    hp = int(ev.get("hpBefore") or 0)
    return {"shieldDmgMin": int(ev.get("shieldDmgMin") or 0),
            "shieldDmgMax": int(ev.get("shieldDmgMax") or 0),
            "healthDmgMin": min(int(ev.get("healthDmgMin") or 0), hp),
            "healthDmgMax": min(int(ev.get("healthDmgMax") or 0), hp),
            "totalDmgMin": int(ev.get("totalDmgMin") or 0),
            "totalDmgMax": int(ev.get("totalDmgMax") or 0),
            "shieldBefore": int(ev.get("shieldBefore") or 0),
            "hpBefore": hp, "appliedHits": int(ev.get("appliedHits") or 0),
            "limitedByMinHp": bool(ev.get("limitedByMinHp")),
            "events": len(evs)}


def _rival_models(nat: dict) -> dict:
    """Les modeles CONCURRENTS, evalues sur les faits NATIFS du meme tir.

    M1 = `[min(shield, totalDmgMin), min(shield, totalDmgMax)]` : « le bouclier absorbe le
         degat total, plafonne au bouclier ». C'est le modele que #342 a refute.
    M2 = meme forme, mais sur `sante + bouclier` au lieu de `TotalDamage` : la variante qui
         survivrait si `TotalDamage` etait simplement mal decode.
    """
    s = nat["shieldBefore"]
    m2min = nat["healthDmgMin"] + nat["shieldDmgMin"]
    m2max = nat["healthDmgMax"] + nat["shieldDmgMax"]
    return {"M1_min_shield_total": [min(s, nat["totalDmgMin"]), min(s, nat["totalDmgMax"])],
            "M2_min_shield_health_plus_shield": [min(s, m2min), min(s, m2max)]}


def _regime(nat: dict) -> str:
    """SOUS-CAP (aucune borne rabattue) / CAP PARTIEL (la haute seule) / SUR-CAP (les deux)."""
    s = nat["shieldBefore"]
    if s <= 0:
        return "SANS-BOUCLIER"
    lo_cap, hi_cap = nat["shieldDmgMin"] >= s, nat["shieldDmgMax"] >= s
    if lo_cap and hi_cap:
        return "SUR-CAP"
    if hi_cap:
        return "CAP-PARTIEL"
    return "SOUS-CAP"


def _measure(sid, sf, seed, roster, board, center, damage, wt, verbose) -> dict:
    att, vic = roster["p"][0], roster["a"][0]
    rid = None
    try:
        rid = _build(sf, seed, roster, board, damage)
        dv = view(sid, rid)
        ids = {}
        for v in tuple(roster["p"]) + tuple(roster["a"]):
            u = by_visual(dv, v)
            if u is None:
                raise RuntimeError("unite absente du build : %s" % v)
            ids[v] = int(u["id"])
        # Le `place_ring` a un SECOND role : le deplacement du `thousSorcerer` declenche
        # `On(0x1c = ArrivedAtFinalTile)`, donc la POSE du bouclier sur son meilleur voisin allie.
        place_ring(sid, rid, ids, vic, tuple(center))
        ability = normal_attack_id(view(sid, rid), ids[att])
        nat = _native_prediction(sid, rid, ids[att], ids[vic], ability)
        if nat is None:
            return {"damage": damage, "error": "aucun event natif pour la paire"}
        port = _port_prediction(sid, rid, wt, ids[att], ids[vic], ability)
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    if port is None:
        return {"damage": damage, "error": "aucun event PORT pour la paire", "native": nat}
    rivals = _rival_models(nat)
    nat_pair = [nat["shieldDmgMin"], nat["shieldDmgMax"]]
    out = {"damage": damage, "regime": _regime(nat), "native": nat, "port": port,
           "rivals": rivals,
           "shield_match": bool(port["shieldDmgMin"] == nat["shieldDmgMin"]
                                and port["shieldDmgMax"] == nat["shieldDmgMax"]),
           "total_match": bool(port["totalDmgMin"] == nat["totalDmgMin"]
                               and port["totalDmgMax"] == nat["totalDmgMax"]),
           "health_match": bool(port["healthDmgMin"] == nat["healthDmgMin"]
                                and port["healthDmgMax"] == nat["healthDmgMax"]),
           "rivals_match": {k: bool(v == nat_pair) for k, v in rivals.items()}}
    if verbose:
        print("[345] Damage=%-6d %-11s bouclier=%-6d hits=%d" %
              (damage, out["regime"], nat["shieldBefore"], nat["appliedHits"]))
        print("        shieldDmg  natif=[%5d,%5d]  port=[%5d,%5d]  %s"
              % (nat["shieldDmgMin"], nat["shieldDmgMax"], port["shieldDmgMin"],
                 port["shieldDmgMax"], "MATCH" if out["shield_match"] else "ECART"))
        print("        totalDmg   natif=[%5d,%5d]  port=[%5d,%5d]  %s"
              % (nat["totalDmgMin"], nat["totalDmgMax"], port["totalDmgMin"],
                 port["totalDmgMax"], "MATCH" if out["total_match"] else "ECART"))
        print("        healthDmg  natif=[%5d,%5d]  port=[%5d,%5d]  %s"
              % (nat["healthDmgMin"], nat["healthDmgMax"], port["healthDmgMin"],
                 port["healthDmgMax"], "MATCH" if out["health_match"] else "ECART"))
        for k, v in rivals.items():
            print("        %-32s = [%5d,%5d]  %s"
                  % (k, v[0], v[1], "match" if out["rivals_match"][k] else "REFUTE"))
    return out


def _damage_grid(sid, sf, seed, roster, board, center, wt, verbose):
    """Choisit les `Damage` qui posent les TROIS regimes, a partir d'une sonde non capee.

    On calibre le ratio `shieldDmgMax / Damage` en regime sous-cap, puis on vise :
      * SOUS-CAP    : la moitie du `Damage` de saturation ;
      * CAP-PARTIEL : juste au-dessus de la saturation de la borne HAUTE ;
      * SUR-CAP     : trois fois ce seuil (les deux bornes rabattues au bouclier).
    """
    probe = _measure(sid, sf, seed, roster, board, center, CALIB_DAMAGE, wt, False)
    if probe.get("error"):
        return None, probe
    nat = probe["native"]
    if nat["shieldBefore"] <= 0:
        return None, {"error": "aucun bouclier pose : %s n'a pas accorde ArcaneShield "
                               "(deplacement refuse, ou aucun allie dans son rayon)"
                               % roster["a"][1]}
    if nat["shieldDmgMax"] <= 0:
        return None, {"error": "sonde a Damage=%d : degat bouclier nul (unites hors contact "
                               "-- changer --center)" % CALIB_DAMAGE}
    ratio = nat["shieldDmgMax"] / float(CALIB_DAMAGE)
    d_sat = int(nat["shieldBefore"] / ratio) + 1
    grid = [max(1, d_sat // 2), d_sat, d_sat * 3]
    if verbose:
        print("[345] calibration : bouclier=%d, sonde Damage=%d -> shieldDmg=[%d,%d] "
              "(ratio max/D=%.4f) -> saturation vers Damage=%d"
              % (nat["shieldBefore"], CALIB_DAMAGE, nat["shieldDmgMin"], nat["shieldDmgMax"],
                 ratio, d_sat))
        print("[345] grille de Damage : %s" % grid)
    return grid, {"probe": probe, "ratio": ratio, "d_sat": d_sat}


def run(seed: int = 34501, state_file=None, verbose: bool = True,
        attacker: str = ATTACKER, victim: str = VICTIM, shielder: str = SHIELDER,
        board: str = BOARD, center=CENTER, damages=None) -> dict:
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parents[1] / "logs" / "p345.json")
    sf.parent.mkdir(parents=True, exist_ok=True)
    wt = load_weights()
    roster = {"p": (attacker, FILLER_P if attacker != FILLER_P else ATTACKER),
              "a": (victim, shielder)}
    if verbose:
        print("[345] montage : %s -> %s (bouclier pose par %s) sur %s, anneau centre en %s"
              % (attacker, victim, shielder, board, tuple(center)))

    if damages:
        grid, cal = list(damages), {"grid": "fournie"}
    else:
        grid, cal = _damage_grid(sid, sf, seed + 900, roster, board, center, wt, verbose)
        if grid is None:
            return {"error": cal.get("error", "calibration KO"), "calibration": cal}

    rows = []
    for i, d in enumerate(grid):
        rows.append(_measure(sid, sf, seed + i, roster, board, center, d, wt, verbose))

    good = [r for r in rows if not r.get("error")]
    regimes = sorted({r["regime"] for r in good})
    port_ok = bool(good) and all(r["shield_match"] for r in good)
    # Un modele concurrent n'est REFUTE que s'il s'ecarte sur AU MOINS un regime -- sur un
    # seul couple, plusieurs modeles coincident (c'est tout le point de la grille).
    refuted = {k: any(not r["rivals_match"][k] for r in good)
               for k in (good[0]["rivals"] if good else {})}
    verdict = {
        "ok": bool(port_ok and len(regimes) >= 2 and all(refuted.values())),
        "port_matches_native": port_ok,
        "regimes": regimes,
        "rivals_refuted": refuted,
        "total_matches": {r["damage"]: r["total_match"] for r in good},
        "health_matches": {r["damage"]: r["health_match"] for r in good},
        "rows": rows, "calibration": cal,
        "montage": {"attacker": attacker, "victim": victim, "shielder": shielder,
                    "board": board, "center": tuple(center)}}
    if verbose:
        print("\n=== VERDICT ===")
        print("  regimes couverts               : %s" % ", ".join(regimes))
        print("  terme BOUCLIER port == natif   : %s" % ("OUI" if port_ok else "NON"))
        for k, v in refuted.items():
            print("  %-32s : %s" % (k, "REFUTE" if v else "non separe"))
        print("  totalDmg port == natif         : %s" % verdict["total_matches"])
        print("  healthDmg port == natif        : %s" % verdict["health_matches"])
        print("  -> %s" % ("OK" if verdict["ok"] else "ECHEC"))
    return verdict


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=34501)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--attacker", default=ATTACKER)
    ap.add_argument("--victim", default=VICTIM)
    ap.add_argument("--shielder", default=SHIELDER)
    ap.add_argument("--board", default=BOARD, help="board CHOISI (runner.md sec.2), jamais subi")
    ap.add_argument("--center", default="%d,%d" % CENTER,
                    help="centre de l'anneau (col,row) -- a adapter au board")
    ap.add_argument("--damages", default=None,
                    help="liste de Damage explicite (ex. 400,800,2400) au lieu de la grille")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    dmg = [int(x) for x in a.damages.split(",")] if a.damages else None
    out = run(seed=a.seed, state_file=a.state_file, attacker=a.attacker, victim=a.victim,
              shielder=a.shielder, board=a.board, damages=dmg,
              center=tuple(int(x) for x in a.center.split(",")))
    if out.get("error"):
        print("[345] ERREUR : %s" % out["error"])
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
