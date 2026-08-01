"""#411-r2 -- DECOMPOSITION PAR ETAGE de l'ecart port/natif isole par
`probe_411r2_scale_discriminant.py`. On ne fitte AUCUN scalaire : on fait varier UNE entree
a la fois et on lit la PENTE des deux cotes.

CE QUE LE PREMIER PROBE A ETABLI (deux runs, meme montage)
-----------------------------------------------------------
    block 0,0     : port 3433 (6 coups, per_hit 514..642) | natif 6597 | pred [2610..3912]
    block 100,500 : port  426                             | natif 3433 | pred [2610..3912]

Le "x8,06" du rapport #411-r1 n'est donc PAS un facteur : c'est une DIFFERENCE CONSTANTE
(le block retranche ~6 x 500 = 3000 des DEUX cotes) appliquee a deux bases differentes --
3433-3007=426 cote port, ~6433-3000=3433 cote natif. Le seul ecart REEL est le facteur ~1,9
sur le degat BRUT, et c'est lui qu'on decompose ici. Le block confirme au passage le NOMBRE
de coups natif : une reduction de ~3000 a 500/coup = ~6 coups, pas 12.

CE QUE CE PROBE MESURE
----------------------
Le port rend `roll x 0,60` par coup -- exactement le PiercingRatio de l'arme, ce qui est la
signature d'une armure si grande qu'elle absorbe toute la part non percee. L'hypothese a
falsifier est donc : **l'etage ARMURE**. Un balayage de `FixedArmor` de la CIBLE la tranche
sans aucun ajustement :

    armure GRANDE (defaut 3513) : port = roll x pierce           <- regime observe
    armure NULLE  (0)           : port = roll (aucune reduction)

    * si l'ecart natif/port DISPARAIT a armure nulle -> l'etage EST l'armure ;
    * s'il PERSISTE          -> l'armure est hors de cause, l'etage est en amont
                                (base de degat ou nombre de coups).

Un regime INTERMEDIAIRE donne la pente et distingue "armure ignoree" de "armure comptee
une demi-fois". Chaque regime est un runner independant ; le port y est rejoue sur le MEME
etat pre-attaque que le natif.

Usage (depuis scripts/python, session warmee) :
    python probe_411r2_stage_sweep.py --state-file <ABSOLU> [--armors 3513,1000,0]

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from probe_411r2_scale_discriminant import (
    ATTACKER, CARRIER, MOVE_STAT, VICTIM, _adjacent_free, _find, _native_prediction,
    _plan_for, _port_replay, _run, _snapshot_stats, _units, rpc, sid,
)


def one_regime(pydir: Path, sf: Path, seed: str, board: str, rank: str,
               armor: int, block_target: str, target_health: int = 0,
               attacker_damage: int = 0, skip_attack: bool = False) -> dict:
    """Un regime = un runner neuf. `armor=None` -> on ne touche pas a l'armure de la cible.

    `target_health` LEVE LA TRONCATURE : a armure nulle le natif TUE la cible, et `hp_v0-hp_v1`
    vaut alors les PV et non le degat -- une mesure PLAFONNEE qui se lit comme une mesure. Le
    premier sweep l'a rencontree (9539 = PV exacts, hp -> 0). On monte donc les PV assez haut
    pour que le regime reste LISIBLE."""
    us = ["%s:Movement=%d" % (ATTACKER, MOVE_STAT)]
    if attacker_damage:
        # Deuxieme AXE du sweep : la BASE de degat de l'attaquant. Il separe un facteur
        # MULTIPLICATIF d'un terme ADDITIF -- un seul point ne le fait pas (cf. la consigne
        # « jamais fitter un scalaire »).
        us.append("%s:Damage=%d" % (ATTACKER, attacker_damage))
    if target_health:
        us.append("%s:Health=%d,RemainingHealth=%d" % (VICTIM, target_health, target_health))
    if armor is not None:
        # `Armor` ET `FixedArmor` : `--armor-target` du builder ecrit les DEUX, et n'en
        # ecrire qu'un laisserait l'autre a sa valeur de rank -- une demi-mutation qui
        # rendrait un resultat inexploitable sans le dire.
        us.append("%s:Armor=%d,FixedArmor=%d" % (VICTIM, armor, armor))
    extra = ["--rank", rank, "--p-units", ATTACKER,
             "--a-units", "%s,%s" % (VICTIM, CARRIER),
             "--crit", "0,0", "--crit-target", "0,0", "--block-target", block_target,
             "--board", board]
    for u in us:
        extra += ["--unit-stat", u]
    _run(["rl_duel.py", "build", "--seed", seed, "--state-file", str(sf)] + extra, pydir)
    st = json.loads(sf.read_text(encoding="utf-8"))
    rid = int(st["runnerId"])
    s = sid()
    try:
        units = _units(s, rid)
        att, _ = _find(units, ATTACKER)
        vic, uv = _find(units, VICTIM)
        to = _adjacent_free(s, rid, units, uv["pos"], att)
        _run(["rl_duel.py", "act", "move", "--unit", str(att), "--to", "%d,%d" % to,
              "--state-file", str(sf)], pydir)
        units1 = _units(s, rid)
        hp_v0 = int((units1.get(vic) or {}).get("hp") or 0)
        dv = rpc(s, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 8}, 150)
        plan = _plan_for(dv, att, vic)
        # TOUS les evals (att -> vic), pas seulement le premier. `attackPlans` porte UNE entree
        # par ABILITY : `_plan_for` retient le PREMIER, tandis que `rl_duel._plan_ab_map` ECRASE
        # et retient le DERNIER. Si les deux different, le probe interroge une ability et le
        # natif en joue une autre -- exactement le genre d'artefact de montage qui se lit comme
        # une divergence de port. On les imprime pour que la question ne se pose plus.
        all_evals = [{"abilityId": ev.get("abilityId"), "ability": ev.get("ability"),
                      "kind": ev.get("kind")}
                     for p in (dv.get("attackPlans") or []) if int(p.get("unitId") or -1) == att
                     for ev in (p.get("evals") or [])
                     if int(ev.get("targetId") or -1) == vic]
        pred = _native_prediction(s, rid, att, vic, plan.get("abilityId"))
        # ORACLE DU NOMBRE DE COUPS, cote natif : `MakeDamagePredictions` rend `appliedHits`
        # par `ProbableDamageEvent`. C'est la seule voie qui NOMME les coups sans capteur neuf.
        pbp = rpc(s, "aiPlaybookPredict", {"runnerId": rid, "unitId": att, "targetId": vic,
                                           "abilityType": plan.get("abilityId")}, 90) or {}
        port = _port_replay(s, rid, att, vic)
        nat = _snapshot_stats(s, rid, [att, vic])
        # PV de TOUTES les unites avant/apres : un delta sur une unite AUTRE que la cible
        # dirait que le nombre observe n'est pas celui de l'attaque. Sans ce releve, un
        # dommage venu d'ailleurs se lit comme le degat de l'attaque.
        hp_all0 = {int(u): int((units1.get(u) or {}).get("hp") or 0) for u in units1}
        if not skip_attack:
            # `--ability` EXPLICITE : on joue exactement celle qu'on a interrogee, plus celle
            # que l'auto-resolution choisirait. Sans ca, le natif et le probe peuvent viser
            # deux abilities differentes sans que rien ne le signale.
            _run(["rl_duel.py", "act", "ability", "--caster", str(att), "--target", str(vic),
                  "--ability", str(plan.get("abilityId")), "--state-file", str(sf)], pydir)
        units2 = _units(s, rid)
        hp_v1 = int((units2.get(vic) or {}).get("hp") or 0)
        hp_all1 = {int(u): int((units2.get(u) or {}).get("hp") or 0) for u in units2}
        deltas = {u: hp_all0.get(u, 0) - hp_all1.get(u, 0) for u in hp_all0
                  if hp_all0.get(u, 0) != hp_all1.get(u, 0)}
    finally:
        try:
            rpc(s, "disposeRunner", {"runnerId": rid}, 20)
        except Exception as e:                                        # noqa: BLE001
            print("[warn] disposeRunner: %s" % (e,))
    pf = pred.get("pred") or {}
    vs = ((nat.get(vic) or {}).get("stats") or {})
    return {"armor_arg": armor, "runner": rid,
            "nat_fixed_armor": vs.get("fixedArmor"), "nat_defense": vs.get("defense"),
            "N": hp_v0 - hp_v1, "hp_v0": hp_v0, "hp_v1": hp_v1,
            "G": int(port["total"]), "hits": port["hits"], "per_hit": port["per_hit"],
            "port_armor": port["armor"], "port_pierce": port["pierce"],
            "clean": [port["clean_min"], port["clean_max"]],
            "pred": [pf.get("healthDmgMin"), pf.get("healthDmgMax")],
            "killed": hp_v1 <= 0, "deltas": deltas, "skipped": skip_attack,
            "ability": plan.get("abilityId"), "all_evals": all_evals,
            "pbp": [{k: e.get(k) for k in ("targetId", "healthDamageMin", "healthDamageMax",
                                           "appliedHits", "probability") if k in e}
                    for e in (pbp.get("damageEvents") or pbp.get("events") or [])][:4],
            "pbp_err": pbp.get("error"),
            "attack": (((nat.get(att) or {}).get("stats") or {}).get("attack"))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="31337")
    ap.add_argument("--rank", default="17")
    ap.add_argument("--block-target", default="0,0")
    ap.add_argument("--armors", default="3513,1000,0",
                    help="valeurs de FixedArmor/Armor de la CIBLE a balayer (CSV)")
    ap.add_argument("--target-health", type=int, default=0,
                    help="PV forces de la CIBLE -- indispensable a armure basse, sinon le natif "
                         "TUE et le delta de PV est PLAFONNE (mesure illisible).")
    ap.add_argument("--skip-attack", action="store_true",
                    help="BRAS TEMOIN : ne joue PAS l'attaque. Tout delta de PV observe alors "
                         "ne vient PAS de l'attaque -- le controle qui manquait.")
    ap.add_argument("--damages", default="",
                    help="CSV de `Damage` de l'ATTAQUANT. Si fourni, le sweep porte sur CET axe "
                         "(armure fixee au 1er element de --armors) : separe multiplicatif/additif.")
    a = ap.parse_args()
    pydir = Path(__file__).resolve().parent
    sf = Path(a.state_file).resolve()
    sys.path.insert(0, str(pydir))
    import host_inputs                                        # noqa: F401 (garde data/)

    rows = []
    if a.damages.strip():
        armor0 = int(a.armors.split(",")[0].strip())
        for tok in a.damages.split(","):
            tok = tok.strip()
            if not tok:
                continue
            rows.append(one_regime(pydir, sf, a.seed, a.board, a.rank, armor0, a.block_target,
                                   a.target_health, int(tok), a.skip_attack))
    else:
        for tok in a.armors.split(","):
            tok = tok.strip()
            if not tok:
                continue
            rows.append(one_regime(pydir, sf, a.seed, a.board, a.rank, int(tok), a.block_target,
                                   a.target_health, 0, a.skip_attack))
    print("=== #411-r2 SWEEP D'ETAGE : armure de la CIBLE ===")
    print("armure |  ATT | natif N | port G | ratio | hits | port clean       | pred natif    | mort")
    for r in rows:
        ratio = (r["N"] / r["G"]) if r["G"] else float("nan")
        print("%6s | %4s | %7d | %6d | %5.3f | %4d | [%5s..%5s] | [%5s..%5s] | %s"
              % (r["nat_fixed_armor"], r["attack"], r["N"], r["G"], ratio, r["hits"],
                 r["clean"][0], r["clean"][1], r["pred"][0], r["pred"][1],
                 "TUEE (mesure PLAFONNEE)" if r["killed"] else "-"))
    print()
    for r in rows:
        print("[detail] armure=%s runner=%d per_hit=%s port_armor=%s pierce=%s hp %d->%d"
              % (r["nat_fixed_armor"], r["runner"], r["per_hit"], r["port_armor"],
                 r["port_pierce"], r["hp_v0"], r["hp_v1"]))
        print("[hits-natif] armure=%s aiPlaybookPredict=%s err=%s"
              % (r["nat_fixed_armor"], json.dumps(r["pbp"], ensure_ascii=True)[:400],
                 r["pbp_err"]))
        print("[deltas]   attaque_jouee=%s pertes_de_PV_par_unite=%s"
              % (not r["skipped"], json.dumps(r["deltas"], ensure_ascii=True)))
        print("[ability]  JOUEE=%s | TOUS les evals att->vic = %s"
              % (r["ability"], json.dumps(r["all_evals"], ensure_ascii=True)))
    if len(rows) >= 2:
        lo = min(rows, key=lambda r: int(r["nat_fixed_armor"] or 0))
        hi = max(rows, key=lambda r: int(r["nat_fixed_armor"] or 0))
        print()
        print("[lecture] armure MAX (%s) : ratio %.3f | armure MIN (%s) : ratio %.3f"
              % (hi["nat_fixed_armor"], (hi["N"] / hi["G"]) if hi["G"] else float("nan"),
                 lo["nat_fixed_armor"], (lo["N"] / lo["G"]) if lo["G"] else float("nan")))
        print("[lecture] si le ratio TOMBE a ~1 quand l'armure tombe a 0 -> l'ETAGE EST "
              "L'ARMURE ; s'il PERSISTE -> l'armure est hors de cause.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
