#!/usr/bin/env python
"""Probe #339 -- le terme LIFESTEAL de SpiritLeech moyenne `AccurateHealthDamage` avec l'arrondi
de `IdunBattle.Core.Services.MinMaxDamage$$Avg` (demi-vers-le-PAIR), pas les bornes BRUTES + bouclier.

CE QUE LE DECOMPILE DIT (`rnca9r7q6c`, lu VERBATIM)
---------------------------------------------------

    IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetHealAmountForPrediction
        = DSLFormulas.PercentageOf(
              DSLFormulas.DamagePredictionFormula(attacker, attackerPos, Entity(target),
                                                  Direct(AbilityOrEffect(this)),
                                                  GetAttackDamage(state, isPrediction: true),
                                                  Direct(GetNumberConstant(0x2f)),
                                                  GetDamageProfile(this),
                                                  prioritizeKills: FALSE),
              DSLFormulas.ConfigVar(0x4b = hpToHealPct), roundingRule = 1 (Ceiling))

    IdunBattle.Entities.Formulas.DamagePredictionFormula$$Calculate (queue) :
        result  = <BattleQuery>.GetAttackPrediction(...)                 # DamagePredictionResult
        minmax  = prioritizeKills@+0x54 ? <getter result+0x14>           # bornes du DefaultScenario
                                        : result + 0x40                  # AccurateHealthDamage
        avg     = IdunBattle.Core.Services.MinMaxDamage$$Avg(minmax)     # <<< LE FOYER DE #333
        ...     return -avg / avg / avg*2 / avg*3 selon kill

`prioritizeKills` est le 10e argument du ctor `IdunBattle.Entities.Formulas.DamagePredictionFormula$$.ctor`
(champ `+0x54`) ; `GetHealAmountForPrediction` passe **0**. Le montant moyenne est donc
`AccurateHealthDamage@+0x40` -- les bornes CAPEES aux PV (`healthDmgMin/Max` du decodeur), une
SEULE fois, avec `Avg` = `Fix64.Round(., ToEven)`. Ni les bornes BRUTES (`willKillDmg`/
`mightKillDmg` = `DefaultScenario` @+0x14), ni le moindre terme de BOUCLIER.

CE QUE CE PROBE MESURE
----------------------
`pairUtility` invoque
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`
= Sigma des 4 familles (damage + heal + effect + repair). Le terme DEGAT se recalcule EXACTEMENT
cote port depuis les events NATIFS d'`aiPlaybookPredict` (voie #333/#R34, feed identique des deux
cotes). Le RESIDU `natif - degat` est donc le terme LIFESTEAL, isole -- et le probe VERIFIE que le
terme d'effet est nul en le montrant.

`aiPlaybookPredict` ne rend PAS les heal events pour ce playbook (`healCount = -1`, limite du
decodeur) : le residu d'utilite est le seul canal, et il suffit.

PILOTER LA PARITE, PAS LA SUBIR (le piege de #329, redit par #333)
------------------------------------------------------------------
Un `.5` EXACT n'existe que si `Min + Max` est IMPAIR, et sur un `.5` a partie entiere IMPAIRE
demi-vers-le-pair et demi-vers-le-haut COINCIDENT. Un seul bras ne dit donc rien du mode.
Levier : `AccurateHealthDamage` est CAPE aux PV, et `rl_duel build --hp-target H` pose
`Health = RemainingHealth = H` -- donc `H` choisit la parite de la somme ET celle du floor.
Contrainte SUPPLEMENTAIRE ici : le `Ceiling` de `PercentageOf` peut ABSORBER un ecart d'une unite
sur la moyenne (a 60 %, `ceil(2759 x .6) == ceil(2760 x .6)`). On ne retient donc que les `H` dont
les variantes rendent des montants de soin DISTINCTS -- sinon le bras est vert sans rien discriminer.

  bras UP   : floor IMPAIR -> `to_even` MONTE (= `half_up`), `trunc` (= `kept_half`) reste
  bras DOWN : floor PAIR   -> `to_even` reste (= `trunc`),   `half_up` (= `kept_half`) monte

Seul `to_even` est nul sur les DEUX bras. La variante `port_avant` (bornes BRUTES + bouclier,
`.5` conserve) est evaluee sur le meme feed : elle est refutee par la seule cape des PV.

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_339_spiritleech_lifesteal.py
    python probe_339_spiritleech_lifesteal.py --victim necroWarden --board C1_03 --center 3,6
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                         # noqa: E402
from engine.weights import load as load_weights                            # noqa: E402
from engine_agreement_stages import _fields_from_native_event              # noqa: E402
from engine.services.min_max_damage import min_max_avg                     # noqa: E402
from engine.predict import heal_utility                                    # noqa: E402
from engine.entities.effects.magnitude import ability_var                  # noqa: E402
from probe_r34_overkill_decision import (view, by_visual, place_ring,       # noqa: E402
                                         port_pair_utility, _hpmax_by_id, _f)

SPIRIT_LEECH = 1104             # ActiveAbilityType.SpiritLeech (playbook Comparable)
CASTER = "tyranNeurothrope"     # le SEUL porteur de SpiritLeech (heros, au pool rank 17)
FILLER_P = "astraBullgryn"      # 2e unite de mon camp, NON Tyranid : ne devient pas cible de soin
VICTIM = "genesPrimus"
FILLER_A = "necroWarden"        # 2e ennemi : tuer la cible ne doit pas finir la bataille
BOARD = "MC1_67"
CENTER = (3, 4)

CALIB_HP = 200000               # passe 1 : PV hors de portee -> bornes NON capees
CASTER_HP = 1000                # PV COURANTS du caster : le soin doit rester NON cape par le manque


def _r(sid, m, b, t=120):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed: int, roster, hp_target: int, board: str) -> int:
    """`rl_duel build` -- board CHOISI (runner.md sec.2). `--crit 0,0` / `--block-target 0,0`
    neutralisent les canaux qui bougeraient les bornes pour une raison ETRANGERE a l'arrondi.
    `--unit-stat <caster>:RemainingHealth=` creuse les PV MANQUANTS du caster : sans ca
    `PredictHeal` cape le soin a 0 et le terme mesure disparait."""
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board, "--rank", "17",
           "--p-units", ",".join(roster["p"]), "--a-units", ",".join(roster["a"]),
           "--unit-stat", "%s:RemainingHealth=%d" % (roster["p"][0], CASTER_HP),
           "--hp-target", str(hp_target), "--crit", "0,0", "--block-target", "0,0", "--no-ai"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _setup(sid, sf, seed, hp_target, roster, board, center):
    """Build + GEOMETRIE DRIVEE : le caster au centre, tout le monde sur son ring 1 (sinon la
    portee refuse le cast et la prediction rend des bornes `[0,0]`)."""
    rid = _build(sf, seed, roster, hp_target, board)
    dv = view(sid, rid)
    ids = {}
    for v in tuple(roster["p"]) + tuple(roster["a"]):
        u = by_visual(dv, v)
        if u is None:
            raise RuntimeError("unite absente du build : %s" % v)
        ids[v] = int(u["id"])
    place_ring(sid, rid, ids, roster["p"][0], tuple(center))
    return rid, ids


def _predict(sid, rid, att_id, tgt_id) -> dict:
    return _r(sid, "aiPlaybookPredict",
              {"runnerId": rid, "unitId": int(att_id), "targetId": int(tgt_id),
               "abilityType": SPIRIT_LEECH}, 180)


def _native_utility(sid, rid, att_id, tgt_id):
    return _r(sid, "pairUtility",
              {"runnerId": rid, "unitId": int(att_id), "targetId": int(tgt_id),
               "abilityType": SPIRIT_LEECH}, 180).get("utility")


# -- variantes de MONTANT MOYENNE, appliquees au SEUL point de branchement ---------------------
#    (Fraction : `kept_half` / `port_avant` gardent un demi EXACT, sans bruit flottant)

def _bases(f: dict) -> dict:
    mn, mx = int(f["healthDmgMin"]), int(f["healthDmgMax"])
    rmn, rmx = int(f["rawHealthDmgMin"]), int(f["rawHealthDmgMax"])
    smn, smx = int(f["shieldDmgMin"] or 0), int(f["shieldDmgMax"] or 0)
    s = mn + mx
    return {
        "to_even": Fraction(min_max_avg(mn, mx)),        # `MinMaxDamage$$Avg` = ce que dit le natif
        "trunc": Fraction(s // 2),
        "half_up": Fraction(s // 2 + (s & 1)),
        "kept_half": Fraction(s, 2),
        # le port d'AVANT #339 : bornes BRUTES + bouclier, `.5` conserve
        "port_avant": Fraction(rmn + rmx, 2) + Fraction(smn + smx, 2),
    }


VARIANTS = ("to_even", "trunc", "half_up", "kept_half", "port_avant")


def _heal_terms(f: dict, pct: int, hp_max: int, hp_cur: int) -> dict:
    """`PercentageOf(dmg, hpToHealPct, roundUp=1)` puis `PredictHeal = min(montant, manquant)`
    puis `HealUtility` -- le reste du terme est deja porte et n'est pas ce qu'on discrimine."""
    missing = max(0, int(hp_max) - int(hp_cur))
    out = {}
    for name, base in _bases(f).items():
        amount = math.ceil(base * pct / 100)             # Ceiling exact (Fraction)
        eff = min(amount, missing)
        out[name] = {"base": base, "amount": amount, "eff": eff,
                     "utility": heal_utility(eff, int(hp_max), is_friend=True, is_boss=False)}
    return out


def _real_port_term(sid, rid, uid, wt, tile, cand_pred):
    """LE TERME TEL QU'IL EST APPELE EN PRODUCTION : `ComparableAbilityGenerator.
    _spiritleech_lifesteal_util`, sur le contexte IA REEL (`engine.ai.context.build`) et nourri de
    la prediction NATIVE (feed identique des deux cotes, comme `port_pair_utility` pour le degat).
    Sans ce deuxieme etage, on validerait une formule de probe, pas le code livre."""
    from engine.ai import context as _ai_ctx
    from engine.ai.action_generators import ComparableAbilityGenerator
    from engine.playbook import scene as scene_mod
    rpc = lambda m, b, t=90: _r(sid, m, b, t)          # noqa: E731
    predictor = scene_mod.build_predictor(rpc, rid)
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    if predictor is not None:
        scene_mod.refresh_shields(predictor, rpc, rid)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    ctx = _ai_ctx.build(rpc, rid, dv, mov_by_unit, int(uid), wt, predictor, debug=False)
    return ComparableAbilityGenerator()._spiritleech_lifesteal_util(ctx, tuple(tile), cand_pred)


def _measure_arm(sid, sf, seed, hp, wt, label, roster, board, center) -> dict:
    att, vic = roster["p"][0], roster["a"][0]
    rid = None
    try:
        rid, ids = _setup(sid, sf, seed, hp, roster, board, center)
        dv = view(sid, rid)
        team_by_id = {int(u["id"]): u.get("team") for u in (dv.get("units") or [])}
        hpmax = _hpmax_by_id(sid, rid)
        ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        cur = {int(u.get("squadId")): int(u.get("hp") or 0)
               for u in (ob.get("units") or []) if u.get("squadId") is not None}
        pr = _predict(sid, rid, ids[att], ids[vic])
        evs = list(pr.get("events") or [])
        main = next((e for e in evs if e.get("targetId") == ids[vic]), None)
        if main is None:
            return {"label": label, "hp": hp, "error": "aucun event natif pour la paire"}
        nat = _native_utility(sid, rid, ids[att], ids[vic])
        lvl = int(((pr.get("abilityState") or {}).get("level")) or 0)
        mult = int(((pr.get("abilityState") or {}).get("multiplier")) or 100)
        eff_events = list(pr.get("effectEvents") or [])
        heal_count = pr.get("healCount")
        dmg_port = port_pair_utility(evs, hpmax, team_by_id, team_by_id.get(ids[att]), wt)
        real_port = _real_port_term(sid, rid, ids[att], wt, center,
                                    _fields_from_native_event(main))
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)

    f = _fields_from_native_event(main)
    pct = int(ability_var("SpiritLeech", "hpToHealPct", lvl, multiplier_pct=mult) or 0)
    hp_max_c, hp_cur_c = int(hpmax.get(ids[att]) or 0), int(cur.get(ids[att]) or 0)
    terms = _heal_terms(f, pct, hp_max_c, hp_cur_c)
    residual = None if nat is None else nat - dmg_port
    s = int(f["healthDmgMin"]) + int(f["healthDmgMax"])
    return {"label": label, "hp": hp, "events": len(evs), "level": lvl, "multiplier": mult,
            "pct": pct, "casterHpMax": hp_max_c, "casterHp": hp_cur_c,
            "healthDmgMin": int(f["healthDmgMin"]), "healthDmgMax": int(f["healthDmgMax"]),
            "rawHealthDmgMin": int(f["rawHealthDmgMin"]), "rawHealthDmgMax": int(f["rawHealthDmgMax"]),
            "shieldDmgMin": int(f["shieldDmgMin"] or 0), "shieldDmgMax": int(f["shieldDmgMax"] or 0),
            "sum": s, "sum_odd": bool(s % 2), "floor": s // 2, "floor_odd": bool((s // 2) % 2),
            "limitedByMinHp": bool(f["limitedByMinHp"]), "kill": bool(f["kill"]),
            "killSure": bool(f["killSure"]), "healCount": heal_count,
            "effectEvents": eff_events, "native": nat, "damage_port": dmg_port,
            "residual": residual, "terms": terms, "real_port": real_port,
            "real_delta": (None if residual is None else residual - real_port),
            "deltas": {k: (None if residual is None else residual - v["utility"])
                       for k, v in terms.items()}}


def _pick_hp(raw_min: int, raw_max: int, pct: int):
    """Les DEUX PV qui posent un `.5` EXACT de part et d'autre de la parite du floor, ET dont le
    `Ceiling` de `PercentageOf` ne fait PAS retomber les variantes sur le meme montant (sinon le
    bras est vert sans rien discriminer)."""
    def _sep(floor: int) -> bool:
        return (math.ceil(Fraction(floor * pct, 100))
                != math.ceil(Fraction((floor + 1) * pct, 100)))

    up = down = None
    for h in range(raw_min + 1, raw_max):
        s = raw_min + h
        if s % 2 == 0:
            continue
        k = s // 2
        if not _sep(k):
            continue
        if k % 2 == 1 and up is None:
            up = h
        if k % 2 == 0 and down is None:
            down = h
        if up is not None and down is not None:
            break
    return up, down


def _expected(arm: dict) -> dict:
    """Ce que le decompile PREDIT pour chaque variante : `residual - utility(variante)` doit etre
    NUL pour `to_even` seul (et pour ses colistiers de bras, qui coincident par construction)."""
    if not arm.get("sum_odd"):
        return {"to_even": True, "trunc": True, "half_up": True, "kept_half": True,
                "port_avant": False}
    if arm["floor_odd"]:                       # natif = floor + 1
        return {"to_even": True, "trunc": False, "half_up": True, "kept_half": False,
                "port_avant": False}
    return {"to_even": True, "trunc": True, "half_up": False, "kept_half": False,
            "port_avant": False}


def run(seed: int = 33910, state_file=None, verbose: bool = True, victim: str = VICTIM,
        board: str = BOARD, center=CENTER, tol: float = 1e-6) -> dict:
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parents[1] / "logs" / "p339.json")
    sf.parent.mkdir(parents=True, exist_ok=True)
    wt = load_weights()
    roster = {"p": (CASTER, FILLER_P), "a": (victim, FILLER_A if victim != FILLER_A else VICTIM)}

    rid = None
    try:
        rid, ids = _setup(sid, sf, seed + 900, CALIB_HP, roster, board, center)
        pr = _predict(sid, rid, ids[CASTER], ids[victim])
        main = next((e for e in (pr.get("events") or [])
                     if e.get("targetId") == ids[victim]), None)
        if main is None:
            return {"error": "calibration : aucun event natif pour la paire"}
        cal = _fields_from_native_event(main)
        raw_min, raw_max = int(cal["healthDmgMin"]), int(cal["healthDmgMax"])
        lvl = int(((pr.get("abilityState") or {}).get("level")) or 0)
        mult = int(((pr.get("abilityState") or {}).get("multiplier")) or 100)
        pct = int(ability_var("SpiritLeech", "hpToHealPct", lvl, multiplier_pct=mult) or 0)
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)

    if verbose:
        print("[339] montage : %s -> %s sur %s, anneau centre en %s"
              % (CASTER, victim, board, tuple(center)))
        print("[339] calibration : bornes NON capees = [%d, %d] ; hpToHealPct = %d"
              % (raw_min, raw_max, pct))
    if raw_max - raw_min < 4:
        # Des bornes `[0,0]` ne disent PAS "couple non mesurable" : elles disent que l'anneau
        # choisi n'a pas mis les unites au CONTACT sur ce board -> changer --center.
        return {"error": "fenetre de pilotage trop etroite : bornes [%d,%d] (centre %s sur %s -- "
                         "si elles valent [0,0], l'anneau ne met pas au contact : changer --center)"
                         % (raw_min, raw_max, tuple(center), board),
                "raw": [raw_min, raw_max]}
    if not pct:
        return {"error": "hpToHealPct nul (niveau %d, mult %d) : le terme mesure n'existe pas"
                         % (lvl, mult)}

    hp_up, hp_down = _pick_hp(raw_min, raw_max, pct)
    if hp_up is None or hp_down is None:
        return {"error": "aucun couple de PV donnant les deux parites AVEC separation du Ceiling "
                         "dans ]%d,%d[ a %d %%" % (raw_min, raw_max, pct),
                "raw": [raw_min, raw_max]}
    if verbose:
        print("[339] PV pilotes : UP=%d (somme %d, floor %d IMPAIR) | DOWN=%d (somme %d, floor %d PAIR)"
              % (hp_up, raw_min + hp_up, (raw_min + hp_up) // 2,
                 hp_down, raw_min + hp_down, (raw_min + hp_down) // 2))

    arms = {"up": _measure_arm(sid, sf, seed, hp_up, wt, "UP (le natif MONTE)", roster, board, center),
            "down": _measure_arm(sid, sf, seed + 1, hp_down, wt, "DOWN (le natif DESCEND)",
                                 roster, board, center)}

    ok = True
    for key, arm in arms.items():
        if arm.get("error"):
            ok = False
            if verbose:
                print("[339] bras %s : ERREUR %s" % (key, arm["error"]))
            continue
        exp = _expected(arm)
        arm["expected_null"] = exp
        arm["measured_null"] = {k: (arm["deltas"][k] is not None and abs(arm["deltas"][k]) < tol)
                                for k in VARIANTS}
        # Le code LIVRE, pas seulement la formule du probe.
        arm["real_ok"] = bool(arm["real_delta"] is not None and abs(arm["real_delta"]) < tol)
        arm["ok"] = bool(all(arm["measured_null"][k] == exp[k] for k in VARIANTS)
                         and arm["real_ok"] and arm["sum_odd"] and not arm["limitedByMinHp"])
        ok &= arm["ok"]
        if verbose:
            print("\n=== bras %s === PV=%d bornes CAPEES=[%d,%d] somme=%d (%s) floor=%d (%s)"
                  % (arm["label"], arm["hp"], arm["healthDmgMin"], arm["healthDmgMax"],
                     arm["sum"], "IMPAIRE" if arm["sum_odd"] else "PAIRE",
                     arm["floor"], "IMPAIR" if arm["floor_odd"] else "PAIR"))
            print("  bornes BRUTES=[%d,%d] bouclier=[%d,%d] kill=%s killSure=%s limitedByMinHp=%s"
                  % (arm["rawHealthDmgMin"], arm["rawHealthDmgMax"], arm["shieldDmgMin"],
                     arm["shieldDmgMax"], arm["kill"], arm["killSure"], arm["limitedByMinHp"]))
            print("  caster PV=%d/%d pct=%d ; effets natifs=%s ; healCount=%s"
                  % (arm["casterHp"], arm["casterHpMax"], arm["pct"],
                     [(e.get("effectType"), e.get("probability")) for e in arm["effectEvents"]],
                     arm["healCount"]))
            print("  natif=%s  degat(port)=%s  RESIDU=%s"
                  % (_f(arm["native"]), _f(arm["damage_port"]), _f(arm["residual"])))
            for name in VARIANTS:
                t = arm["terms"][name]
                print("    %-10s base=%-10s soin=%-6d healU=%-18s delta=%-14s %s (attendu %s)"
                      % (name, str(t["base"]), t["amount"], _f(t["utility"]),
                         _f(arm["deltas"][name]),
                         "NUL" if arm["measured_null"][name] else "non nul",
                         "NUL" if exp[name] else "non nul"))
            print("    %-10s %-38s delta=%-14s %s"
                  % ("PORT LIVRE", "_spiritleech_lifesteal_util = " + _f(arm["real_port"]),
                     _f(arm["real_delta"]), "NUL" if arm["real_ok"] else "ECHEC"))

    verdict = {"ok": bool(ok), "raw": [raw_min, raw_max], "pct": pct, "arms": arms,
               "montage": {"caster": CASTER, "victim": victim, "board": board,
                           "center": tuple(center)}}
    if all(not a.get("error") for a in arms.values()):
        both = {n: all((arms[k].get("measured_null") or {}).get(n) for k in arms) for n in VARIANTS}
        verdict["nul_on_both_arms"] = [n for n, v in both.items() if v]
        verdict["ok"] = bool(verdict["ok"] and verdict["nul_on_both_arms"] == ["to_even"])
    if verbose:
        print("\n=== VERDICT ===")
        for key, arm in arms.items():
            print("  %-5s : %s" % (key, "OK" if arm.get("ok") else "ECHEC"))
        if "nul_on_both_arms" in verdict:
            print("  variantes nulles sur les DEUX bras : %s"
                  % ", ".join(verdict["nul_on_both_arms"]))
        print("  -> %s" % ("OK" if verdict["ok"] else "ECHEC"))
    return verdict


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=33910)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--victim", default=VICTIM)
    ap.add_argument("--board", default=BOARD, help="board CHOISI (runner.md sec.2), jamais subi")
    ap.add_argument("--center", default="%d,%d" % CENTER,
                    help="centre de l'anneau (col,row) -- a adapter au board")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(seed=a.seed, state_file=a.state_file, victim=a.victim, board=a.board,
              center=tuple(int(x) for x in a.center.split(",")))
    if out.get("error"):
        print("[339] ERREUR : %s" % out["error"])
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
