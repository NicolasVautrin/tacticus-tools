"""HealingBalms_Heal (1212, Baldr `spaceWolfPriest`) -- face DECISION, confrontee au LIVE.

Deux etages du chemin de soin de 1212, gardes SEPAREMENT (jamais un scalaire fitte) :

A. MAGNITUDE, confrontee au natif par le canal SCALAIRE `pairUtility` (= invocation de
   `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`).
   Ce canal ne traverse AUCUN decodeur de struct des hooks : `IdunBattle.Core.Services.DamagePrediction$$PredictHeal`
   rend `CONCAT44(fill, currentHealth)` -- 8 octets, meme forme que `RepairPredictionResult` (backlog #276-r1).
   Le natif dispatche `HealAmount` par CLASSE d'ability :
     * `IdunBattleLogic.Entities.Abilities.Active.MassHealAbility$$HealAmount` = la variable de config ;
     * `IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility$$HealAmount`
       = `Multiply(StatAmount(weapon), Max(WeaponHighestHits(weapon), Get(1)))` = l'ARME,
       appelee NOMMEMENT par `...HealingBalms_HealPlaybook$$MakeHealPredictions`.
   Le port routait par la PRESENCE de `hpToHeal`, ce qui pour 1212 pointe sur la config du PASSIF
   (soin RETARDE de l'effet) : ce test EXIGE le regime DISCRIMINANT (les deux hypotheses donnent des
   utilites differentes) et verifie que le natif suit la branche ARME.

B. TERME CUSTOM `...HealingBalms_HealPlaybook$$CalculateCustomUtility` =
   `Fix64.FastMul(Sum(CalculateUtilityFromHealEvent), Fix64.<statics+0x30> = Half)` gate par
   `!HasEffect(target, EffectType.HealingBalms_ExtraCritDamage)`. Il n'apparait PAS dans `pairUtility`
   (le natif l'ajoute au-dessus, dans `CalculateActionUtility`) -> ce test garde que le GENERATEUR
   d'actions produit `u = 1.5 x U_natif` sur une cible non buffee, et `1.0 x U_natif` quand le gate
   ferme. La confrontation CAUSALE du facteur (choix natif) vit dans `probe_27_1212_healingbalms.py`.

PORTEUR HORS CATALOGUE : `spaceWolfPriest` est absent du seed BC capture -> injecte avec ses configs
d'ability par `catalog_inject.py` (copie sous `logs/`, jamais le seed partage).

ASCII only.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
ROOT = PYDIR.parents[1]                                     # racine repo
SEED_BC = ROOT / "logs" / "bc_healing_balms.json"
CASTER_VIS = "spaceWolfPriest"
ALLY_VIS = "spaceBlackmane,spaceHound,spaceStormcaller"
FOE_VIS = "blackTerminator,blackAbaddon"
ABILITY = 1212
HP_PLAYER = 20000            # PV max identiques cote joueur -> U ne depend que de `missing`
WOUND_ROUNDS = 5             # tours adverses max pour amener un allie en regime DISCRIMINANT


def _seed_bc() -> Path | None:
    if SEED_BC.exists():
        return SEED_BC
    SEED_BC.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "catalog_inject.py", "--units", CASTER_VIS,
                    "--out", str(SEED_BC)], cwd=str(PYDIR), capture_output=True,
                   text=True, encoding="utf-8", errors="replace")
    return SEED_BC if SEED_BC.exists() else None


def _caster(rpc, rid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 2}, 180)
    for u in (dv.get("units") or []):
        if u.get("visualId") == CASTER_VIS:
            return u.get("id"), dv
    return None, dv


def _wound_one_round(rpc, rid) -> None:
    """Passe la main et laisse l'IA adverse frapper UN tour (aucune de mes unites n'agit)."""
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    rpc("autoPlayRunner", {"runnerId": rid, "maxTurns": 1}, 240)


def _candidates(rpc, rid, cid):
    """Cibles legales de 1212 + leur etat, cote NATIF (`abilityTargets` + `observeBattle`)."""
    at = rpc("abilityTargets", {"runnerId": rid, "abilityType": ABILITY}, 60)
    obs = rpc("observeBattle", {"runnerId": rid}, 40)
    ob = {u.get("squadId"): u for u in (obs.get("units") or [])}
    out = []
    for u in (at.get("units") or []):
        if u.get("unitId") != cid:
            continue
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != ABILITY:
                continue
            for t in (a.get("targets") or []):
                if t.get("kind") != "unit" or t.get("targetId") is None:
                    continue
                o = ob.get(t["targetId"]) or {}
                if o.get("isDead"):
                    continue
                out.append({"tid": t["targetId"], "hp": int(o.get("hp") or 0),
                            "hpMax": int(o.get("hpMax") or 0)})
    return out


def test_healing_balms_heal_magnitude_is_weapon_not_config(live_session, rpc, build_runner):
    """A : `pairUtility` natif == la branche ARME de `HealAbility$$HealAmount`, et DIFFERE de la
    branche `hpToHeal` (regime discriminant EXIGE). B : le generateur d'actions applique le facteur
    `Half` du CustomUtility, et le gate d'effet l'annule."""
    from engine.predict import (heal_amount_weapon, heal_amount_config, predict_heal_effective,
                                heal_amount_for_ability)
    from engine.playbook.common import HEALING_BALMS_HEAL_PLAYBOOK as PB

    bc = _seed_bc()
    assert bc is not None, "catalog_inject KO : seed BC augmentee de spaceWolfPriest introuvable"

    rid = build_runner("4242", extra=["--seed-bc", str(bc), "--board", "MC1_67",
                                      "--p-units", f"{CASTER_VIS},{ALLY_VIS}",
                                      "--a-units", FOE_VIS,
                                      "--hp-player", str(HP_PLAYER)])["rid"]
    cid, _ = _caster(rpc, rid)
    assert cid is not None, f"{CASTER_VIS} absent du build (catalog_inject non pris en compte ?)"

    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    sn = next((u for u in (snap.get("units") or []) if u.get("entityId") == cid), {}) or {}
    attack = int(((sn.get("stats") or {}).get("attack")) or 0)
    hits = int((sn.get("normalAttack") or {}).get("hits") or 1)
    cfgu = sn.get("unitConfig") or {}
    amt_wpn = heal_amount_weapon(attack, hits)
    amt_cfg = heal_amount_config("HealingBalms_Heal", int(cfgu.get("activeAbilityLevel") or 0),
                                 int(cfgu.get("passiveAbilityLevel") or 0),
                                 int(cfgu.get("abilityVariablesMultiplier") or 100))
    assert amt_wpn > 0, f"magnitude ARME nulle (attack={attack}, hits={hits}) : montage muet"
    assert amt_cfg is not None and amt_cfg != amt_wpn, \
        (f"les deux hypotheses de magnitude coincident (arme={amt_wpn}, config={amt_cfg}) : "
         f"le test ne discriminerait RIEN")
    # le dispatch du port doit AVOIR choisi l'arme pour 1212
    assert heal_amount_for_ability(ABILITY, "HealingBalms_Heal",
                                   int(cfgu.get("activeAbilityLevel") or 0),
                                   int(cfgu.get("passiveAbilityLevel") or 0),
                                   int(cfgu.get("abilityVariablesMultiplier") or 100),
                                   attack, hits) == amt_wpn

    # Cible a PV pleins -> MaxFillUp = 0 -> `ShouldExecute` (u > 0) refuse : le natif rend 0.
    full = _candidates(rpc, rid, cid)
    assert full, "aucune cible legale pour 1212 au depart (ability non granted ?)"
    u0 = rpc("pairUtility", {"runnerId": rid, "unitId": cid, "targetId": full[0]["tid"],
                             "abilityType": ABILITY}, 60)
    assert abs(float(u0.get("utility") or 0.0)) < 1e-9, \
        f"cible a PV pleins : utilite native {u0.get('utility')} != 0 (MaxFillUp devrait valoir 0)"
    assert PB.score(predict_heal_effective(amt_wpn, full[0]["hpMax"], full[0]["hpMax"]),
                    full[0]["hpMax"], True, False) is None, \
        "le port emet une action de soin sur une cible a PV pleins (gate ShouldExecute absent)"

    # Amener un allie en regime DISCRIMINANT : `missing` strictement au-dessus des DEUX magnitudes.
    need = max(amt_wpn, amt_cfg)
    row = None
    for _ in range(WOUND_ROUNDS):
        row = next((c for c in _candidates(rpc, rid, cid)
                    if c["tid"] != cid and (c["hpMax"] - c["hp"]) > need), None)
        if row is not None:
            break
        _wound_one_round(rpc, rid)
    assert row is not None, \
        (f"aucun allie amene a plus de {need} PV manquants en {WOUND_ROUNDS} tours adverses : "
         f"montage NON discriminant (les deux hypotheses saturent a `missing`)")

    nat = rpc("pairUtility", {"runnerId": rid, "unitId": cid, "targetId": row["tid"],
                              "abilityType": ABILITY}, 60)
    nat_u = float(nat.get("utility"))
    assert nat.get("playbookClass") == "HealingBalms_HealPlaybook", \
        f"playbook natif inattendu : {nat.get('playbookClass')}"

    eff_wpn = predict_heal_effective(amt_wpn, row["hp"], row["hpMax"])
    eff_cfg = predict_heal_effective(amt_cfg, row["hp"], row["hpMax"])
    u_wpn = eff_wpn / (row["hpMax"] + 1) * 100.0
    u_cfg = eff_cfg / (row["hpMax"] + 1) * 100.0

    # A. le natif suit la branche ARME, et l'ecart avec la branche config est REEL (discriminant).
    assert abs(nat_u - u_wpn) < 1e-6, \
        (f"pairUtility natif {nat_u} != branche ARME {u_wpn} "
         f"(attack={attack} x hits={hits} = {amt_wpn}, cible {row['hp']}/{row['hpMax']})")
    assert abs(nat_u - u_cfg) > 1e-3, \
        f"branche config {u_cfg} indiscernable du natif {nat_u} : montage non discriminant"

    # B. le CustomUtility (Half) et son gate, cote port.
    assert abs(PB.score(eff_wpn, row["hpMax"], True, False) - 1.5 * nat_u) < 1e-6, \
        "le port n'applique pas le facteur Half de CalculateCustomUtility (cible NON buffee)"
    assert abs(PB.score(eff_wpn, row["hpMax"], True, True) - nat_u) < 1e-6, \
        ("le gate `HasEffect(HealingBalms_ExtraCritDamage)` n'annule pas le CustomUtility "
         "(cible DEJA buffee)")

    print("[1212] caster u%s attack=%d hits=%d | cible u%s %d/%d | natif=%.10f arme=%.10f config=%.10f"
          % (cid, attack, hits, row["tid"], row["hp"], row["hpMax"], nat_u, u_wpn, u_cfg))
