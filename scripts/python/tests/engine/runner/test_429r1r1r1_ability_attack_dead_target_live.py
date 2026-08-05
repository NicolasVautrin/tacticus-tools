"""#429-r1-r1-r1 -- GARDE du TRI des call-sites d'`AttackDamageOperation.execute_ability_attack`.

Ce que ce fichier empeche de regresser EN SILENCE, et c'est un tri, pas un gate :

  * qu'on POSE le gate cadavre sur le foyer `execute_ability_attack` (ou sur un site trie
    NON GATE) -- ce serait un FORK du natif, dont le prix est mesure ici : le coup bonus de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeCorruption_BonusHitAbility` disparait
    et le relais bonde perd son transfert ;
  * qu'on RETIRE le gate de la seule porte qui doit le porter (le repli generique de
    `summon_ai._apply_active_ability`, qui EMULE un cast d'ability active) ;
  * qu'un call-site NEUF apparaisse sans avoir ete trie (le cliquet du volet `tri`).

Le critere est natif et mesure sur le build `rnca9r7q6c` (xrefs) :
`IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility` n'a que DEUX
appelants CODE -- `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` et
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteForReplacedTarget`. Aucun sur le trajet
`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` ->
`IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget` ->
`Core.Services.OperationProcessor$$AttackDamage` ->
`IdunBattle.Operations.AttackDamageOperation$$Execute`.
"""
from __future__ import annotations

import importlib

import pytest

PROBE = "probe_429r1r1r1_ability_attack_dead_target"


@pytest.fixture(scope="module")
def P():
    return importlib.import_module(PROBE)


# --------------------------------------------------------------------------- LE TRI (offline)

def test_le_tri_decrit_l_arbre_courant(P, capsys):
    """CLIQUET. Tout call-site doit etre trie, tout site trie doit exister, et la POSE du gate
    dans le code doit correspondre au tri. Un site neuf non trie fait rougir : c'est le point --
    le prochain call-site devra etre lu au decompile avant d'etre range."""
    rc = P.volet_tri()
    assert rc == 0, "le tri ne decrit plus l'arbre :\n%s" % capsys.readouterr().out


def test_le_cliquet_du_tri_mord_vraiment(P):
    """Contre-epreuve du test precedent : un cliquet qui ne rougit jamais ne garde rien.

    Trois facons de casser le tri, trois rouges attendus -- verifies en MUTANT la table, jamais
    en la relisant. Le 3e (`pose contredit le tri`) est celui qui compte le plus : c'est lui qui
    attrape un gate pose en bloc sur un site classe NON GATE."""
    ref = dict(P.TRI)
    cle_non_gate = next(k for k, v in ref.items() if not v[0])
    cle_gate = next(k for k, v in ref.items() if v[0])
    try:
        # (1) un site EXISTANT retire de la table -> « non classe »
        P.TRI = {k: v for k, v in ref.items() if k != cle_non_gate}
        assert P.volet_tri() == 1, "un call-site non trie devrait faire rougir"
        # (2) un site de la table qui n'existe pas dans l'arbre -> « disparu »
        P.TRI = dict(ref)
        P.TRI[("runner/inexistant.py", "Fantome::execute")] = (False, "n/a", "n/a")
        assert P.volet_tri() == 1, "un site trie mais absent du scan devrait faire rougir"
        # (3) la POSE contredit le tri -> c'est le gate en bloc qui se ferait prendre
        P.TRI = dict(ref)
        P.TRI[cle_non_gate] = (True,) + ref[cle_non_gate][1:]
        assert P.volet_tri() == 1, "un site NON GATE declare GATE devrait faire rougir"
        P.TRI = dict(ref)
        P.TRI[cle_gate] = (False,) + ref[cle_gate][1:]
        assert P.volet_tri() == 1, "le site GATE declare NON GATE devrait faire rougir"
    finally:
        P.TRI = ref
    assert P.volet_tri() == 0, "la table doit avoir ete restauree"


def test_un_seul_site_est_gate_et_c_est_le_repli_d_ability_active(P):
    """Le tri lui-meme, enonce : une seule porte se gate, et on la NOMME."""
    gates = sorted(k for k, v in P.TRI.items() if v[0])
    assert gates == [("runner/operations/summon_ai.py", "_apply_active_ability")], gates


# ------------------------------------------------------------------- LES QUATRE BRAS (offline)

@pytest.fixture(scope="module")
def bras(P):
    """Les quatre bras du temoin, joues UNE fois. `_ability_hors_registre` DERIVE son couple
    (ability, porteur) : le registre grandit a chaque tranche, un id fige finirait porte et le
    bras deviendrait muet sans rougir."""
    aid, vis = P._ability_hors_registre()
    if aid < 0:
        pytest.fail("plus aucune ability d'attaque active n'atteint le repli generique : "
                    "le montage de ce fichier est MUET, il faut le refaire (pas le skipper).")
    return {"aid": aid, "vis": vis,
            "morte": P._bras_summon(True), "vive": P._bras_summon(False),
            "foyer": P._bras_foyer_nu(False), "haze": P._bras_haze()}


def test_le_gate_mord_sur_la_porte_gatee(bras):
    """(a) Cible MORTE sur le repli generique -> refus complet : aucun total, AUCUN tirage.
    L'observable n'est pas le delta de PV -- sur un cadavre il vaut 0 quoi qu'il arrive."""
    routed, total, tirages, _aid = bras["morte"]
    assert routed == "dead_target_not_allowed", routed
    assert (total, tirages) == (0, 0), (total, tirages)


def test_le_gate_ne_refuse_pas_TOUT(bras):
    """(b) MEME porteur, MEME ability, cible VIVANTE -> l'attaque part. Sans cette ligne, un gate
    qui refuserait tout passerait le test precedent."""
    routed, total, tirages, _aid = bras["vive"]
    assert routed == "generic_attack", routed
    assert total > 0 and tirages > 0, (total, tirages)


def test_le_foyer_lui_meme_n_est_PAS_gate(bras):
    """(c) `execute_ability_attack` appele NU sur un cadavre frappe encore -- c'est ce qui separe
    cette tranche d'un gate en bloc, et c'est le comportement natif
    (`IdunBattle.Operations.AttackDamageOperation$$Execute` ne teste pas la mort)."""
    assert bras["foyer"] > 0, bras["foyer"]


def test_un_site_NON_gate_passe_encore(bras):
    """(d) `HazeCorruption_BonusHitAbility` frappe un cadavre PAR CONSTRUCTION (son trigger est
    `IsDead(Target@0x178)`). Le port doit continuer a le faire."""
    assert bras["haze"] > 0, bras["haze"]


def test_les_deux_contre_epreuves_offline(P, capsys):
    """Le volet complet, contre-epreuves comprises : gate DEBRANCHE (le refus redevient une
    attaque) et gate EN BLOC (les sites non gates tombent). Un VERT sans elles ne prouverait
    rien -- une mutation qui ne mord pas rend le temoin ininterpretable."""
    rc = P.volet_gate()
    assert rc == 0, capsys.readouterr().out


# ------------------------------------------------------------------------------- LIVE (Haze)

def test_le_natif_frappe_le_cadavre_par_la_voie_DSL_live(P, capsys):
    """LE bras qui rend le tri attribuable, et le seul qui confronte le NATIF.

    Montage case-209 (`probe_209_haze_damage_transfer`), PV 5000 : la cible meurt avant le
    dernier coup, le coup BONUS tombe sur le cadavre et sa `LeftOverDamage` part sur le relais
    bonde. On exige TROIS choses :
      1. le port livre reproduit le natif ;
      2. un gate pose EN BLOC change le resultat (sinon la distinction n'est pas observable et
         ce montage ne prouverait rien) ;
      3. et donc que le tri n'est pas un gate en bloc deguise.

    Montage KO -> `fail`, jamais un skip : un fichier qui rend 0 passed est traite comme rouge."""
    rc = P.volet_live("5000", "777")
    sortie = capsys.readouterr().out
    if rc == 2:
        pytest.fail("montage live KO -- rien mesure :\n%s" % sortie)
    assert rc == 0, sortie
