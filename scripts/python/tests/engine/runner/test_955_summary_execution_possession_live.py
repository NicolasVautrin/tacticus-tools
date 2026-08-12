"""#955 -- cliquet LIVE des deux passifs, adosse a `probe_955_summary_execution_possession.py`.

Trois volets, chacun avec un TEMOIN QUI DISCRIMINE et une CONTRE-EPREUVE PAR MUTATION :

  * `possession` -- deux bras qui ne different QUE par la geometrie (d == 1 / d == 2), et qui
    doivent rendre des summons DIFFERENTS cote natif. Un bras qui n'obtient pas sa configuration
    fait ECHOUER le test (jamais un skip) ; deux bras qui rendent le meme summon font ECHOUER le
    test aussi -- c'est exactement ce qu'un port lisant la mauvaise adjacence produirait.
  * `summary`    -- l'aura permanente 1043 : +400 au stat Attack du Guardsman (trait
    `BattleFatigue`), RIEN sur l'allie temoin ni sur le porteur. La comparaison porte sur la part
    sous la CLE D'AURA, jamais sur le total : `load_state` seede la part capturee, donc le TOTAL
    reste a 400 meme quand le port est neutralise (regime degenere mesure).
  * `execution`  -- `On(PreUnitFled)` : le Guardsman voisin de l'allie tue est EXECUTE (pas enfui)
    et Yarrick gagne 1031. `Maybe(GetFleeChance)` etant un TIRAGE, le volet rejoue plusieurs seeds
    et ECHOUE franchement si aucune fuite n'a pu etre declenchee -- « non confronte » est alors un
    resultat, pas un vert.
"""
from __future__ import annotations

import pytest

import probe_955_summary_execution_possession as P
from probe_r6_round_materialize import _mkrpc


@pytest.fixture(scope="module")
def rpc():
    return _mkrpc()


def test_possession_deux_bras_discriminants_et_port_egal(rpc):
    res = P.volet_possession(rpc, "eldarRanger")
    assert not res.get("erreur"), res.get("erreur")
    bras = res["bras"]
    # geometrie ASSERTIONNEE contre les positions REELLES (le probe echoue avant si elle manque)
    assert bras["melee"]["d"] == 1 and bras["ranged"]["d"] == 2
    assert bras["melee"]["victime_morte"] and bras["ranged"]["victime_morte"]
    # le TEMOIN DISCRIMINE : deux summons DIFFERENTS cote natif
    assert res["discrimine"], "les deux bras rendent le MEME summon : le temoin ne prouve rien"
    assert res["verdict_natif"]["conforme"], res["verdict_natif"]
    for nom, v in res["verdict_port"].items():
        assert v["egal"], "bras %s : port %s != natif %s" % (nom, v["port"], v["natif"])
        assert v["meme_tuile"], "bras %s : le summon n'est pas sur la meme tuile" % nom
        assert v["mutant_registre_mord"], "bras %s : retirer le passif du registre NE MORD PAS" % nom
        assert v["mutant_melee_mord"], "bras %s : inverser la nature du coup NE MORD PAS" % nom


def test_summary_aura_permanente_et_temoin_sans_le_trait(rpc):
    res = P.volet_summary(rpc, "tauCrisis", "eldarRanger")
    assert not res.get("erreur"), res.get("erreur")
    # l'effet 1043 est pose AU CHARGEMENT (trigger d'INIT partage) -- l'arbitrage du registre
    assert P.EFF_BASE in res["effets_yarrick_avant"], res["effets_yarrick_avant"]
    nat = res["attack_mod_natif"]
    assert nat["guardsman"] > 0 and nat["allie_temoin"] == 0 and nat["yarrick"] == 0, nat
    assert res["discrimine"], "l'allie SANS le trait recoit la meme chose : le selecteur ne mord pas"
    v = res["verdict_port"]
    assert v["total_egal_natif"], res["attack_mod_port"]
    assert v["aura_attribuee"]["guardsman"] == nat["guardsman"], v["aura_attribuee"]
    assert v["aura_discrimine"], v["aura_attribuee"]
    assert v["mutant_effet_mord"], "retirer 1043 d'EFFECT_CLASSES NE MORD PAS"
    assert v["mutant_trait_mord"], "retirer le gate de trait du selecteur NE MORD PAS"


def test_execution_le_fuyard_est_tue_et_yarrick_gagne_1031(rpc):
    res = P.volet_execution(rpc, "tauCrisis", "eldarRanger", essais=6)
    assert res["execution_observee"], (
        "aucune fuite declenchee en %d essais (Maybe(GetFleeChance) est un tirage) -- "
        "NON CONFRONTE : %s" % (len(res["essais"]), res["essais"]))
    ligne = [e for e in res["essais"] if e.get("execution_observee")][0]
    # NATIF : le Guardsman qu'on n'a JAMAIS attaque meurt, et Yarrick porte les DEUX effets
    assert ligne["temoin_mort"] and ligne["victime_morte"]
    assert P.EFF_EXEC in ligne["effets_yarrick"] and P.EFF_BASE in ligne["effets_yarrick"]
    v = ligne["verdict_port"]
    assert v["temoin_execute"], ligne["port"]
    assert v["temoin_pas_enfui"], "le port l'a fait FUIR au lieu de l'EXECUTER : %s" % ligne["port"]
    assert v["effet_1031_sur_yarrick"], ligne["port"]
    assert v["immunite_posee"], "IgnoreBattleFatigue non pose sur les autres porteurs du trait"
    assert v["effets_yarrick_egaux_natif"], (ligne["port"], ligne["effets_yarrick"])
    assert v["mutant_registre_mord"], "retirer le passif du registre NE MORD PAS"
    assert v["mutant_vecteur_mord"], "supprimer le vecteur On(PreUnitFled) NE MORD PAS"
