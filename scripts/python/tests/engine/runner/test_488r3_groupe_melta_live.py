"""#488-r3 -- CONFRONTATION LIVE : le NATIF applique-t-il `Melta_ExtraDmg` aux coups du GROUPE ?

LA QUESTION, POSEE AVANT LA METHODE
------------------------------------
#488-r2 a mesure OFFLINE que le port evaluait `MeltaExtraDmgEffect` (`DamageProfileHasTrait(
OnMelta)` & `HasTrait(Target, Vehicle)`, +50 %) avec le profil de l'ARME au lieu de celui du
GROUPE. #488-r3 le repare, en s'appuyant sur une lecture du decompile : un groupe a profil propre
est une SOUS-OPERATION (`ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute` -> slot
0x3c -> `AttackDamageOperation$$Execute`) dont l'`ExecuteHit` rebatit un `AbilityEntities` NEUF au
`damageProfileType` DU GROUPE.

Reste la seule question qui tranche : **le NATIF applique-t-il ce +50 % sur les coups du groupe ?**
Si oui, le port d'AVANT sous-estimait. Si non, la reparation est un SUR-AJUSTEMENT et il faut la
retirer. Ce fichier ne prouve pas la lecture -- il la CONFRONTE.

LE MONTAGE, ET POURQUOI CELUI-LA
---------------------------------
`blackObliterator` (HERO lineup, au pool) porte `FleshmetalGuns` : un cycle de groupes additionnels
du canal #179 aux profils `Melta` / `Flame` / `HeavyRound` (lu au gameconfig). Ses armes sont
`Power` (melee) et `HeavyRound` (ranged) -- **jamais `Melta`**, donc le profil de l'ARME et celui
du GROUPE different par construction, ce qui est exactement le regime que #488-r3 change.
`admecDestroyer` (HERO lineup, au pool) porte le trait `Vehicle`, second conjoint du gate.
`Melta_ExtraDmg` (1297) est MATCH-WIDE (`OnMeltaDamageAbility$$CreateBehaviour` le pose a
`On(MatchInit)` sur une tuile arbitraire, #488-r1) : rien a greffer, rien a injecter.

COMMENT LE VERDICT SE PREND
----------------------------
Le MEME etat est rejoue offline DEUX fois, sur le MEME flux RNG (`replay_orders`) :
  * `shipped`  -- le port TEL QU'IL EST LIVRE (canal `attacker_mods_for_profile` cable) ;
  * `sans_recollecte` -- le MEME code avec le canal force a `None`, c'est-a-dire l'etat d'AVANT.
Les deux sont compares aux montants LIVE. Celui qui reproduit le natif tranche, et l'autre doit
DIVERGER -- sinon le regime ne discrimine pas et le test le DIT au lieu de rendre un accord vide.

⚠ REGIME DEGENERE = SKIP NOMME, JAMAIS UN VERT. Trois causes possibles, chacune nommee : le cycle
`FleshmetalGuns` n'est pas sur son profil `Melta` a ce tour, le coup n'est pas propre (crit /
block / evade), ou l'attaquant n'atteint pas la cible. Un skip de montage est un rouge de fichier
(#455) si TOUS les cas y tombent -- c'est voulu.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helper sibling
from _pierce_floor_regime import (drive, live_amounts, replay_orders, _ok,   # noqa: E402
                                  pierce_dominant_regime)                    # noqa: F401 (fixture)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                           # scripts/python

CARRIER = "blackObliterator"        # passif `FleshmetalGuns` -> cycle #179, dont un groupe `Melta`
TARGET = "admecDestroyer"           # trait `Vehicle` -> second conjoint du gate `Melta_ExtraDmg`
MELTA = "Melta"
SEEDS = ["777", "31337", "12345"]

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/tests/engine/runner/_pierce_floor_regime.py",
        "scripts/python/rl_duel.py",
        # le rejeu traverse le chargement d'etat, le runner, le pipeline de degat et le canal #179.
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Monte un runner LIVE (`rl_duel build`, board MC1_67) et confronte les montants "
              "natifs au rejeu offline du MEME etat sur le MEME flux RNG. Depend donc du harnais "
              "de build, du helper de regime, de tout `engine/**` (le rejeu), et du BUILD du jeu "
              "(les profils de `FleshmetalGuns` et le trait `Vehicle` viennent du gameconfig).",
}


#: ⚠ CAPTUREE AU CHARGEMENT, JAMAIS A L'APPEL. `replay_orders` REMPLACE
#: `additional_hits.execute_additional_hits` pendant le rejeu : un `from ... import` fait DANS la
#: variante rendrait la substitution elle-meme -> `RecursionError` (mesuree ici, et deja rencontree
#: par `probe_407_failed_block_attack_scope.py`, qui porte la meme note).
from engine.runner.operations.additional_hits import execute_additional_hits as _VRAI_AH  # noqa: E402


def _sans_recollecte(*a, **kw):
    """L'ETAT D'AVANT #488-r3 : le MEME `execute_additional_hits`, canal de re-collecte MUET.

    On ne REIMPLEMENTE rien -- une reimplementation ferait varier bien plus que l'axe mesure, et
    c'est exactement ce que la doctrine appelle fitter deux etages avec un scalaire. Ici une SEULE
    chose bouge : le profil avec lequel les mods ATTAQUANT du groupe sont evalues."""
    kw = dict(kw)
    kw["attacker_mods_for_profile"] = None
    return _VRAI_AH(*a, **kw)


@pytest.mark.parametrize("seed", SEEDS)
def test_le_groupe_melta_prend_le_bonus_vs_vehicle_live(live_session, rpc,
                                                        pierce_dominant_regime, seed):
    r = pierce_dominant_regime(seed, CARRIER, TARGET, armor=0)
    rid, board = r["rid"], r["board"]
    # ⚠ L'ATTAQUE DOIT ETRE RANGED, ET C'EST LU AU DECOMPILE, pas suppose :
    # `IdunBattle.Entities.Effects.Loki.BaseFleshmetalGunsEffect$$CreateAdditionalHits` pose
    # `condition = OwnerIsCaster & IsRangedAttack`. Un `drive` au CONTACT fait choisir l'arme
    # `Power` (melee) a `select_weapon` -> AUCUN groupe #179, et la mesure serait vide. On drive
    # donc sur l'ID de l'attaque normale, ce qui arrete le deplacement des que la cible est LEGALE
    # -- soit a portee 3, l'arme `HeavyRound`. (Mesure : au contact, `live == arme_offline` a 4
    # coups et `livre == []`.)
    dv0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    cu0 = next((u for u in (dv0.get("units") or [])
                if (u.get("visualId") or u.get("visual_id")) == CARRIER), {})
    nrm0 = next((a for a in (cu0.get("abilities") or []) if a.get("kind") == "normal"), None)
    if nrm0 is None:
        pytest.skip("pas d'attaque normale sur %s au montage" % CARRIER)
    cid, tid, moved = drive(rpc, rid, board, CARRIER, TARGET, ability_id=nrm0["id"])
    if cid is None:
        pytest.skip("%s n'a pas amene %s a portee de tir (geometrie de ce seed)" % (CARRIER, TARGET))
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(rng0, dict) and rng0.get("mt")):
        pytest.skip("dumpRng indispo")
    cu = next((u for u in (dv.get("units") or []) if u.get("id") == cid), {})
    nrm = next((a for a in (cu.get("abilities") or []) if a.get("kind") == "normal"), None)
    if nrm is None:
        pytest.skip("pas d'attaque normale sur %s" % CARRIER)
    # Le CYCLE doit etre sur sa variante `Melta`. `FleshMetalGunsAbility$$CreateBehaviour` retire
    # les trois effets au debut du tour de Volk puis pose celui de `UnitTurnsStarted % 3` :
    # `== 1 -> FocusedMalice` (profil `Melta`, jeu de cles de BASE), `== 2 -> RuinousSalvo`
    # (`Flame`), `== 0 -> WarpHail` (`HeavyRound`). Un autre tour ne prouverait RIEN sur ce gate.
    effs = [str(e.get("name") or "") for e in (cu.get("effects") or [])]
    if not any("FocusedMalice" in e for e in effs):
        pytest.skip("le cycle `FleshmetalGuns` n'est pas sur sa variante `Melta` "
                    "(`FocusedMalice`) a ce tour : effets = %s" % effs)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid,
        "abilityType": nrm["id"]}, "captureEvents": True}, 120)
    if not _ok(res):
        pytest.skip("attaque live KO: %s" % str(res)[:120])
    live, dirty = live_amounts(res, tid)
    if dirty:
        pytest.skip("coup non propre (crit/block/evade) -- la comparaison porterait sur autre chose")

    off = replay_orders(dv, ob, snap, board, rng0, cid, tid, None, moved,
                        {"sans_recollecte": _sans_recollecte})
    livre, avant, arme = off["shipped"], off["sans_recollecte"], off["arme"]
    n_arme = len(arme)
    print("\n[488-r3] seed=%s live=%s arme_offline=%s" % (seed, live, arme))
    print("[488-r3] groupe LIVRE=%s AVANT(sans re-collecte)=%s" % (livre, avant))

    assert livre, ("aucun coup additionnel rejoue offline : %s n'a pas produit de groupe #179 sur "
                   "ce tour (le cycle `FleshmetalGuns` est ailleurs) -- rien a mesurer" % CARRIER)
    # (0) le flux RNG doit etre aligne a l'entree du groupe, sinon la mesure ne porte pas.
    assert live[:n_arme] == arme, (
        "les coups d'ARME divergent (live=%s off=%s) : le flux RNG n'est PAS aligne a l'entree du "
        "groupe -- la mesure ne porterait pas sur le bonus." % (live[:n_arme], arme))
    assert n_arme < len(live), (
        "aucun event live apres les %d coups d'arme : le groupe n'a pas ete emis" % n_arme)
    live_g = live[n_arme:n_arme + len(livre)]

    # (1) LE REGIME DOIT DISCRIMINER, sinon ce test ne prouverait rien (accord degenere).
    if livre == avant:
        pytest.skip(
            "regime NON DISCRIMINANT sur ce seed : le groupe execute n'est pas au profil `%s` "
            "(ou la cible ne declenche pas le gate), donc les deux rejeux coincident. Ce n'est "
            "PAS un accord -- c'est l'absence de mesure." % MELTA)

    # (2) LE VERDICT : lequel des deux reproduit le natif ?
    assert live_g == livre, (
        "le port LIVRE ne reproduit pas le natif sur les coups du groupe : live=%s livre=%s "
        "avant=%s. Si c'est `avant` qui reproduit, #488-r3 est un SUR-AJUSTEMENT et doit etre "
        "RETIRE." % (live_g, livre, avant))
    assert live_g != avant, (
        "l'etat d'AVANT reproduit AUSSI le natif : les deux rejeux different entre eux mais le "
        "natif ne les separe pas -- lire la ventilation avant de conclure (live=%s)" % live_g)


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
