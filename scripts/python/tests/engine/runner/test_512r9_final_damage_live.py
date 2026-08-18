"""#512-r9 -- CONFRONTATION LIVE : le vecteur `amount` emet-il `On(0x42 = FinalDamage)` ?

LA QUESTION, POSEE AVANT LA METHODE
------------------------------------
Le decompile dit que `IdunBattle.Operations.ADamageOperation$$RegisterFinalDamage` est appelee en
DERNIERE instruction d'`IdunBattle.Operations.AttackDamageOperation$$Execute`, INCONDITIONNELLEMENT.
Le vecteur `amount` du port (`damage_ops/normal_like.py`) mirroite CETTE fonction -- comme
`damage_ops/normal.py`, qui emet deja l'evenement. #512-r9 le lui fait emettre aussi.

Reste a CONFRONTER : le natif emet-il vraiment DEUX fois sur ce montage, ou une seule ? Si une
seule, l'ajout est un event FANTOME et doit etre retire.

LE MONTAGE, ET CE QUI LE REND DISCRIMINANT
-------------------------------------------
`thousSorcerer` (trait `Psyker`, arme ranged `Psychic` portee 2) tire sur un ennemi A. Le splash
`PsykerExtraAttackAbility` (`On(0x26 = NormalAttack) & IsRangedAttack & DamageProfileIs(Psychic)`)
frappe alors un ennemi B ADJACENT a A, en `Psychic`, **par le vecteur `amount`**
(`psyker_smite_tree` -> `AttackWithAttackDamage` mode `amount` -> `execute_normal_like`).

`thousTzaangor`, ALLIE du Sorcerer, porte `RealityUnbound`. Son volet B est
`On(0x42) & HasTakenDamageOfDamageProfileThisTurnAmountOfTimes(target, Psychic, times = 1)
& AreEnemies(target, self)` et pose `AddStaticStatModifierEffect(self, 1207, EXTRA_MAX_DAMAGE, ...)`
**SANS `RemoveEffect` prealable** -- les instances CUMULENT (l'i2 dit « for each DIFFERENT enemy
unit »).

D'ou l'observable, qui est un COMPTE et pas un scalaire fitte :
  * sans #512-r9 : seul le coup PRINCIPAL (vecteur `normal`) emet `On(0x42)` -> **1** instance ;
  * avec         : le splash l'emet aussi, sur une victime DIFFERENTE -> **2** instances.
Le natif tranche, en lisant le nombre d'instances de l'effet 1207 sur `thousTzaangor`.

⚠ REGIME DEGENERE = SKIP NOMME, JAMAIS UN VERT. Les causes possibles sont nommees une par une :
le Sorcerer n'atteint pas A, A n'a aucun voisin ennemi (pas de splash), ou `thousTzaangor` ne
qualifie pas. Un accord obtenu sans splash ne prouverait RIEN.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helper sibling
from _pierce_floor_regime import (drive, _ok,                                 # noqa: E402
                                  pierce_dominant_regime)                     # noqa: F401 (fixture)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                            # scripts/python

PSYKER = "thousSorcerer"            # trait `Psyker`, arme ranged `Psychic` (portee 2)
OBSERVATEUR = "thousTzaangor"       # passif `RealityUnbound` -- l'ECOUTEUR de l'event 66
CIBLES = "admecDestroyer,admecRuststalker"      # deux ennemis, pour que le splash ait un voisin
#: `EffectType.RealityUnbound_ExtraMaxDamage`.
EFFET = "RealityUnbound_ExtraMaxDamage"
SEEDS = ["777", "31337", "12345", "4463111"]

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/tests/engine/runner/_pierce_floor_regime.py",
        "scripts/python/rl_duel.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Monte un runner LIVE (`rl_duel build`) et lit le NOMBRE d'instances de l'effet "
              "1207 pose sur l'allie observateur. Depend du harnais de build, du helper de "
              "regime, de tout `engine/**` et du BUILD du jeu (traits, armes et magnitudes "
              "viennent du gameconfig).",
}


def _porte_effet(dv, uid, nom) -> bool:
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), {})
    return any(str(e.get("name") or "") == nom for e in (u.get("effects") or []))


def _total_stat(sms, uid, nom_stat):
    """Le TOTAL des modifications d'un stat, lu par le RPC `statModSources`.

    ⚠ C'EST LE BON CAPTEUR, ET LE COMPTE PAR NOM NE L'EST PAS. `decisionView.effects` est une vue
    par NOM : deux instances du MEME effet n'y apparaissent qu'UNE fois. Mesure faite -- ce test
    accusait « le natif ne pose qu'une instance » alors que `statModSources` rendait `total = 598`
    pour une magnitude unitaire de 299. Un capteur qui deduplique ne peut pas compter."""
    for u in (sms.get("units") or []):
        if int(u.get("entityId") or -1) != int(uid):
            continue
        m = ((u.get("mods") or {}).get(nom_stat) or {})
        return m.get("total")
    return None


def _magnitude_unitaire(rpc, rid, uid) -> int:
    """La magnitude d'UNE pose, DERIVEE du foyer du port -- jamais fittee sur le total mesure.

    `reality_unbound_extra_max_damage` lit `RealityUnbound.extraMaxDmg` au `passive_ability_level`
    de l'unite et le scale par son `ability_variables_multiplier` (la variable est dans
    `variablesAffectedByRarityBonus`), exactement comme `AddStaticStatModifierEffect` cote natif.
    On reconstruit donc l'etat offline et on appelle CE foyer, plutot que de recopier une formule
    -- une formule recopiee se perimerait sans que rien ne le dise."""
    from engine.runner.snapshot import load_state
    from engine.runner.operations.triggers.loki.reality_unbound import (
        reality_unbound_extra_max_damage)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    st = load_state(dv, ob, snap)
    return int(reality_unbound_extra_max_damage(st, int(uid)) or 0)


@pytest.mark.parametrize("seed", SEEDS)
def test_le_splash_psyker_emet_final_damage_live(live_session, rpc, pierce_dominant_regime, seed):
    r = pierce_dominant_regime(seed, "%s,%s" % (PSYKER, OBSERVATEUR), CIBLES, armor=0)
    rid, board = r["rid"], r["board"]
    dv0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    cu0 = next((u for u in (dv0.get("units") or [])
                if (u.get("visualId") or u.get("visual_id")) == PSYKER), {})
    obs = next((u for u in (dv0.get("units") or [])
                if (u.get("visualId") or u.get("visual_id")) == OBSERVATEUR), None)
    if obs is None:
        pytest.skip("%s absent du montage (roster non honore)" % OBSERVATEUR)
    nrm0 = next((a for a in (cu0.get("abilities") or []) if a.get("kind") == "normal"), None)
    if nrm0 is None:
        pytest.skip("pas d'attaque normale sur %s" % PSYKER)
    assert not _porte_effet(dv0, obs["id"], EFFET), (
        "l'etat de DEPART porte deja `%s` sur %s : la mesure d'apres ne prouverait rien"
        % (EFFET, OBSERVATEUR))

    # L'attaque doit etre RANGED (le splash est gate `IsRangedAttack`) -> drive sur l'ID de
    # l'attaque normale, qui s'arrete des que la cible est LEGALE (portee 2), jamais au contact.
    cid, tid, moved = drive(rpc, rid, board, PSYKER, "admecDestroyer", ability_id=nrm0["id"])
    if cid is None:
        pytest.skip("%s n'a pas amene sa cible a portee (geometrie de ce seed)" % PSYKER)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid,
        "abilityType": nrm0["id"]}, "captureEvents": True}, 120)
    if not _ok(res):
        pytest.skip("attaque live KO: %s" % str(res)[:120])

    dv1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    sms = rpc("statModSources", {"runnerId": rid, "unitId": obs["id"],
                                 "stats": ["extraMaxDamage"], "minAbs": 1}, 120)
    total = _total_stat(sms, obs["id"], "extraMaxDamage")
    # LE SPLASH A-T-IL EU LIEU ? Sans lui, le total natif vaudrait `unitaire` pour une raison qui
    # n'a rien a voir avec l'event -- et l'accord serait DEGENERE.
    # ⚠ Le format est `res["actions"][].events[].tags` (JSON ou dict), champ `Target_Id` -- PAS
    # un `targetId` a plat. Mesure : la lecture a plat rendait `victimes = []` et faisait skipper
    # le test en accusant le montage au lieu de sa propre lecture.
    victimes = set()
    for act in (res.get("actions") or []):
        for ev in (act.get("events") or []):
            td = ev.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if td.get("Target_Id") is not None and "Amount" in td:
                victimes.add(int(td["Target_Id"]))
    print("\n[512-r9] seed=%s total(extraMaxDamage)=%s victimes=%s"
          % (seed, total, sorted(victimes)))
    if len(victimes) < 2:
        pytest.skip("aucun SPLASH observe (une seule victime : %s) -- le montage ne discrimine "
                    "pas l'emission du vecteur `amount`" % sorted(victimes))
    assert _porte_effet(dv1, obs["id"], EFFET), (
        "`%s` n'est pas sur %s : meme le coup PRINCIPAL n'a pas declenche le passif -- le montage "
        "ne mesure pas ce qu'il croit" % (EFFET, OBSERVATEUR))
    assert isinstance(total, int) and total > 0, (
        "`statModSources` ne rend aucun total pour `extraMaxDamage` sur %s (%r) : le capteur est "
        "muet, pas la mecanique" % (OBSERVATEUR, total))

    # LE VERDICT. La magnitude UNITAIRE est DERIVEE du foyer du port (jamais fittee sur le total
    # mesure) : `reality_unbound_extra_max_damage` lit `RealityUnbound.extraMaxDmg` au niveau et
    # au multiplicateur de rarete de l'unite, exactement comme `AddStaticStatModifierEffect`.
    unitaire = _magnitude_unitaire(rpc, rid, obs["id"])
    if not unitaire:
        pytest.skip("magnitude unitaire non derivable (etats d'ability indisponibles) -- le "
                    "verdict serait un fit sur le total mesure")
    print("[512-r9] unitaire=%s -> attendu 2x=%s (1x=%s si l'event manque)"
          % (unitaire, 2 * unitaire, unitaire))
    assert total == 2 * unitaire, (
        "le natif rend total=%s pour une magnitude unitaire de %s. `%s` == %s signifierait UNE "
        "seule pose, c'est-a-dire que le vecteur `amount` n'emet PAS `On(0x42)` cote natif et que "
        "#512-r9 ajoute un event FANTOME -- le retirer. Toute autre valeur : lire la ventilation "
        "avant de conclure." % (total, unitaire, total, unitaire))


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
