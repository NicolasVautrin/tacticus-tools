"""#429-r1-r1-r1-r1 -- le repli generique de `summon_ai` doit mirrorer les DEUX helpers de degat.

Le probe `probe_429r1r1r1r1_repli_variables_degat.py` MESURE ; ce fichier GARDE. Un cliquet que
personne ne joue ne garde rien : ces tests jouent ses deux volets et figent les invariants qui
n'ont pas le droit de se degrader en silence.

CE QUI EST GARDE, ET POURQUOI CHAQUE ETAGE EXISTE :
  1. la fonction de selection distingue les TROIS cas natifs (`MinMaxDamage`, `DmgDamage`, aucun) ;
  2. toute ability de l'ASSIETTE DERIVEE du repli resout un helper -- c'est le cliquet qui rougira
     le jour ou une ability a `dmg` sortira du registre ;
  3. le bras qui montre que le residu MORD (0 -> non nul) et sa contre-epreuve ;
  4. le 3e cas ne frappe PAS pour 0 : il rend `no_damage_variable`.

Les etages 2 et 3 sont deliberement redondants avec le probe : c'est le probe qui porte la mesure
(assiette DERIVEE, ventilation), le test qui porte le REFUS. Ecrire l'un sans l'autre laisse soit
une mesure que personne ne relit, soit une assertion dont on ne sait plus ce qu'elle compte.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_RACINE = Path(__file__).resolve().parents[3]
if str(_RACINE) not in sys.path:
    sys.path.insert(0, str(_RACINE))

_PROBE = importlib.import_module("probe_429r1r1r1r1_repli_variables_degat")


def test_etage1_la_selection_distingue_les_trois_cas_natifs():
    """`repli_variables_de_degat` rend les cles du helper natif que le site appellerait.

    Les deux helpers, corps LUS :
      `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage` -> 0xc/0xd (minDmg/maxDmg)
      `IdunBattle.Entities.Abilities.AActiveAbility$$DmgDamage`    -> 0xb    (dmg), `Direct(v)`
    """
    from engine.runner.operations.summon_ai import repli_variables_de_degat
    from engine.entities.ability_variable_type import AbilityVariableType
    _min = AbilityVariableType.minDmg.name
    _max = AbilityVariableType.maxDmg.name
    _dmg = AbilityVariableType.dmg.name

    assert repli_variables_de_degat({"variables": {_min: [1], _max: [2]}}) == (_min, _max)
    assert repli_variables_de_degat({"variables": {_dmg: [1]}}) == (_dmg, _dmg)
    assert repli_variables_de_degat({"variables": {}}) is None
    assert repli_variables_de_degat({}) is None
    # PRIORITE : le natif appelle `MinMaxDamage` des que la config porte ses variables ; une
    # config qui porterait les deux jeux ne doit pas basculer sur `DmgDamage`.
    assert repli_variables_de_degat({"variables": {_min: [1], _max: [2], _dmg: [3]}}) == (_min, _max)


def test_etage2_toute_ability_de_l_assiette_resout_un_helper():
    """CLIQUET. L'assiette est DERIVEE (hors `ABILITY_CLASSES` + attaque active), donc elle bouge
    a chaque tranche portee : une ability a `dmg` qui en sortirait rougirait ICI plutot que
    d'infliger 0 en silence."""
    assiette = _PROBE.assiette_du_repli()
    # ASSERTIONNER SON PROPRE NON-VIDE : une assiette vide rendrait le test vert pour de mauvaises
    # raisons (le recenseur ne mesurerait plus rien).
    assert assiette, "assiette du repli VIDE : le recenseur ne mesure plus rien"
    sans = [(aid, nom) for aid, nom in assiette if _PROBE._helper(aid)[0] == "AUCUN"]
    assert not sans, (
        "ces abilities atteignent le repli sans resoudre aucun helper de degat natif : %r -- "
        "lire leur `ExecuteBehaviour` au decompile et etendre `repli_variables_de_degat`" % (sans,))


def test_etage3_le_bras_montre_que_le_residu_mord():
    """Le regime du residu : une ability a `dmg` forcee hors registre.

    Port LIVRE -> degat NON NUL ; cles figees a `minDmg`/`maxDmg` (le comportement d'AVANT) -> 0.
    Sans la contre-epreuve, un bras a 2493 se lirait aussi bien comme « le montage marche »."""
    aid = _PROBE._ability_a_dmg_pour_le_bras()
    if aid < 0:
        pytest.fail("aucune ability a `dmg` classee attaque active dans ce build : le bras n'a "
                    "pas de porteur -- ce n'est pas un vert, c'est un NON MESURE")
    total_apres, routed_apres = _PROBE._bras(aid, figer_les_cles=False)
    total_avant, _routed_avant = _PROBE._bras(aid, figer_les_cles=True)
    assert total_avant == 0, ("la contre-epreuve devait mesurer 0 (c'est le residu meme), "
                              "elle mesure %r" % (total_avant,))
    assert total_apres > 0, "le port livre devait infliger un degat non nul, il mesure %r" % (
        total_apres,)
    assert routed_apres == "generic_attack"


def test_etage4_sans_helper_le_repli_le_DIT_au_lieu_de_frapper_pour_zero():
    """3e cas : aucun helper resolu. Le repli rend `no_damage_variable` -- un no-op EXPLICITE.

    Avant, il traversait `execute_ability_attack` avec des bornes nulles et rendait
    `routed: generic_attack` : un coup annonce PORTE, pour 0. C'est ce silence-la qui a fait
    ecrire le residu."""
    import engine.runner.operations.summon_ai as SA
    from engine.runner.abilities.handler import ABILITY_CLASSES
    aid = _PROBE._ability_a_dmg_pour_le_bras()
    assert aid > 0
    st = _PROBE._etat()
    avant_registre = ABILITY_CLASSES.pop(int(aid), None)
    avant_fn = SA.repli_variables_de_degat
    SA.repli_variables_de_degat = lambda cfg: None
    try:
        res = SA._apply_active_ability(st, 1, 2, int(aid))
    finally:
        SA.repli_variables_de_degat = avant_fn
        if avant_registre is not None:
            ABILITY_CLASSES[int(aid)] = avant_registre
    assert (res or {}).get("routed") == "no_damage_variable"
    assert "result" not in (res or {})
