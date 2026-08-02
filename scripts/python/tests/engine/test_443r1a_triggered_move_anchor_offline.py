"""#443-r1a -- GARDE OFFLINE des verdicts du probe d'ancrage du terme MOVE.

Ce que ces tests gardent : la LOGIQUE DE DECISION du probe, exercee sans live. C'est ce qui la rend
adversariale -- un test live ne saurait pas distinguer « capteur absent » de « le terme ne fire
pas », et c'est precisement la confusion qui produit un vert silencieux.

Le coeur est `check_attribution`. Il encode le critere d'acceptation du capteur, et surtout la
lecon MESUREE de #443-r1 : une version anterieure du probe, SANS filtre d'attribution, avait rendu
un **accord parfait sur la tuile d'une AUTRE unite**. Les cas ci-dessous rejouent cette situation
et exigent qu'elle soit REFUSEE.

La face LIVE (le capteur `frida/hooks/features/triggered-move-trace.ts` REELLEMENT charge) est
**NON CONFRONTEE** et exige une fenetre de reinject. Aucun test d'ici ne prouve qu'il fire.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from probe_443r1a_triggered_move_anchor import (      # noqa: E402
    check_attribution, check_channel, check_decomposition, check_savior, check_value,
)


# ------------------------------------------------------------- E5 la VALEUR (et l'accord DEGENERE)

def _vr(nat, port, missing=(), uid=81, tile=(1, 0)):
    return {"unitId": uid, "utility": "TriggeredAbilitiesUtility", "tile": tile,
            "nat": nat, "port": port, "missing": missing}


def test_valeur_nominale():
    v = check_value([_vr(40.0, 40.0), _vr(20.0, 20.0, tile=(2, 0)), _vr(0.0, 0.0, tile=(3, 0))])
    assert v["status"] == "ok", v["message"]


def test_un_ACCORD_TOUT_A_ZERO_ne_prouve_RIEN():
    """LE vice que #456 ferme, transpose sur l'axe VALEUR : « 0 == 0 » sur toute la table est un
    accord PARFAIT et vide. Un port qui rendrait 0 partout -- ce qu'il fait quand aucun playbook
    n'est charge -- passerait un critere d'accord naif."""
    v = check_value([_vr(0.0, 0.0), _vr(0.0, 0.0, tile=(2, 0))])
    assert v["status"] == "wrong"
    assert "DEGENEREE" in v["message"]


def test_une_SEULE_valeur_native_ne_DISCRIMINE_pas():
    v = check_value([_vr(20.0, 20.0), _vr(20.0, 20.0, tile=(2, 0))])
    assert v["status"] == "wrong"
    assert "ne DISCRIMINE pas" in v["message"]


def test_ecart_sur_ability_NON_PORTEE_est_un_TROU_pas_une_FORMULE():
    """La decomposition par etage appliquee au VERDICT (#456) : le port rend 0 parce que
    `load_playbook` rend `None`, pas parce qu'une formule diverge. Confondre les deux enverrait
    chercher un bug de calcul dans un chemin ou rien n'est calcule.

    Le verdict `gap` s'arrete la ou la MESURE s'arrete : il NOMME l'ability et refuse de departager
    « playbook non porte » de « kit du port trop etroit », ce que seule la decomposition tranche."""
    v = check_value([_vr(40.0, 0.0, missing=(1133,)), _vr(0.0, 0.0, tile=(9, 9))])
    assert v["status"] == "gap", v["message"]
    assert "1133" in v["message"]
    assert "FORMULE" in v["message"] and "DECOMPOSITION" in v["message"]


def test_ecart_sur_ability_PORTEE_est_une_divergence_de_FORMULE():
    v = check_value([_vr(40.0, 33.0), _vr(0.0, 0.0, tile=(9, 9))])
    assert v["status"] == "wrong"
    assert "FORMULE" in v["message"]


def test_valeur_sans_ligne_ne_conclut_RIEN():
    assert check_value([])["status"] == "no-rows"


def _ev(unit_id=10, col=3, row=4, total=50.0, contribs=None, spawning=False, parent=None,
        measured=True):
    return {
        "seq": 1, "originRunnerId": 1, "utility": "TriggeredAbilitiesUtility",
        "unitId": unit_id, "unitMeasured": measured, "parentId": parent,
        "isSpawning": spawning,
        "tile": None if col is None else {"col": col, "row": row},
        "total": total,
        "contribs": ([{"playbook": "SaviorProtocolsPlaybook."
                                   "<CalculateMovementUtilityInStepsInternal>d__4",
                       "value": total}] if contribs is None else contribs),
        "steps": 3,
    }


# ------------------------------------------------------------------------------ E0 le canal

def test_capteur_ABSENT_est_dit_NON_CONFRONTE():
    """Le RPC inconnu -> `not_reinjected`. C'est la SEULE issue qui ne conclut rien du natif, et
    elle doit etre atteinte par la REPONSE DU RPC, jamais par un compte d'events a zero (qui est
    ambigu : capteur absent / rien n'a score / le declencheur ne mord pas)."""
    v = check_channel(None)
    assert v["status"] == "not_reinjected"
    assert "NON CONFRONTE" in v["message"]


def test_capteur_charge_mais_AUCUN_hook_pose_n_est_PAS_un_vert():
    """La resolution runtime peut echouer (classe utility, state machine nested, MoveNext). Le
    capteur repond alors, mais il est INERTE -- exactement le patron « porte + inerte » applique au
    harnais. Ce n'est ni `measured`, ni `not_reinjected`."""
    v = check_channel({"installed": {"TriggeredAbilitiesUtility": "state_machine_not_found",
                                     "TriggeredAbilitiesNonOwnerUtility": "class_not_found"}})
    assert v["status"] == "not-installed"


def test_les_REPLIS_d_offset_sont_DITS_pas_tus():
    """Un champ retombe sur son offset de repli reste LU, mais le capteur n'est plus
    auto-verifiant : il faut le SAVOIR avant d'exploiter la mesure."""
    v = check_channel({"installed": {"TriggeredAbilitiesUtility": "ok"},
                       "resolved": {"TriggeredAbilitiesUtility": {"fallbacks": ["acc"]}}})
    assert v["status"] == "measured"
    assert "REPLI" in v["message"] and "acc" in v["message"]
    assert v["fallbacks"] == ["TriggeredAbilitiesUtility.acc"]


# ------------------------------------------------------- E2 l'ATTRIBUTION (critere d'acceptation)

def test_attribution_nominale():
    ev = [_ev(unit_id=10, col=3, row=4), _ev(unit_id=11, col=5, row=5)]
    movable = {10: {(3, 4)}, 11: {(5, 5)}}
    assert check_attribution(ev, movable)["status"] == "ok"


def test_LE_FAUX_POSITIF_DE_443r1_EST_REFUSE():
    """LE test qui justifie ce capteur. Deux events dont les tuiles sont ATTEIGNABLES par un TIERS
    mais PAS par l'unite a laquelle ils sont attribues : c'est la forme exacte de ce que #443-r1 a
    mesure (4 events, toutes tuiles occupees par un tiers) et qui avait produit un accord parfait
    -- et faux."""
    ev = [_ev(unit_id=10, col=9, row=9), _ev(unit_id=11, col=8, row=8)]
    movable = {10: {(3, 4)}, 11: {(5, 5)}, 99: {(9, 9), (8, 8)}}
    v = check_attribution(ev, movable)
    assert v["status"] == "wrong"
    assert "DIFFERE" in v["message"]


def test_attribution_PARTIELLE_est_refusee():
    """Ce que l'INCLUSION laissait passer et que l'IDENTITE refuse (#456) : une unite dont le
    capteur ne rendrait qu'une tuile sur trois. Toutes ses tuiles vues sont pourtant atteignables --
    l'ancien critere aurait donc dit `ok` sur un capteur qui perd 2/3 du sweep."""
    ev = [_ev(unit_id=10, col=3, row=4), _ev(unit_id=11, col=5, row=5)]
    movable = {10: {(3, 4), (3, 5), (3, 6)}, 11: {(5, 5)}}
    v = check_attribution(ev, movable)
    assert v["status"] == "wrong"
    assert "manquantes" in v["message"] or "DIFFERE" in v["message"]


def test_la_tuile_COURANTE_est_une_candidate_LEGITIME():
    """MESURE #456 : le sweep evalue aussi le fait de RESTER SUR PLACE
    (`IdunBattle.AI.Utilities.UtilityMovementCase$$StaysOnTile` compare la tuile candidate a
    `GetMainTile(case.Unit)`), et `aiMovableTiles` ne rend JAMAIS la tuile courante -- mesure du
    2026-08-02 : 0 unite sur 6. Sans le terme `UNION {position}`, un capteur PARFAIT rougirait."""
    ev = [_ev(unit_id=10, col=3, row=4), _ev(unit_id=10, col=0, row=0),
          _ev(unit_id=11, col=5, row=5)]
    movable = {10: {(3, 4)}, 11: {(5, 5)}}
    positions = {10: (0, 0), 11: (5, 5)}
    v = check_attribution(ev, movable, positions)
    assert v["status"] == "ok", v["message"]


def test_le_terme_POSITION_est_LOAD_BEARING():
    """Contre-epreuve du precedent : le MEME jeu d'events, sans `pos_by_unit`, DOIT rougir. Sans
    ce controle, on ne saurait pas si le terme elargit reellement quoi que ce soit -- un
    elargissement qui ne change rien serait un elargissement de confort."""
    ev = [_ev(unit_id=10, col=3, row=4), _ev(unit_id=10, col=0, row=0),
          _ev(unit_id=11, col=5, row=5)]
    movable = {10: {(3, 4)}, 11: {(5, 5)}}
    assert check_attribution(ev, movable)["status"] == "wrong"


def test_attribution_CONSTANTE_est_refusee():
    """Une constante passerait (a) et (b) sans rien attribuer. Exiger PLUSIEURS unites distinctes
    est ce qui la demasque."""
    ev = [_ev(unit_id=10, col=3, row=4), _ev(unit_id=10, col=3, row=5)]
    v = check_attribution(ev, {10: {(3, 4), (3, 5)}})
    assert v["status"] == "wrong"
    assert "MEME unite" in v["message"]


def test_event_SANS_unite_est_refuse():
    ev = [_ev(unit_id=None, measured=False), _ev(unit_id=11, col=5, row=5)]
    v = check_attribution(ev, {11: {(5, 5)}})
    assert v["status"] == "wrong"
    assert "SANS unite attribuee" in v["message"]


def test_le_regime_SPAWN_n_est_PAS_compte_en_echec():
    """`case.Unit == null` est un etat NATIF legitime (`UtilityMovementCase$$get_IsSpawning`) : le
    natif y consulte le `Parent`. Le compter en echec ferait rougir le capteur sur du comportement
    correct."""
    ev = [_ev(unit_id=None, measured=True, spawning=True, parent=7, col=3, row=4),
          _ev(unit_id=10, col=3, row=4), _ev(unit_id=11, col=5, row=5)]
    v = check_attribution(ev, {10: {(3, 4)}, 11: {(5, 5)}})
    assert v["status"] == "ok", v["message"]
    assert "1 spawn(s)" in v["message"]


def test_unite_SANS_reference_movable_n_est_pas_comptee_en_echec():
    """`aiMovableTiles` peut ne rien rendre pour une unite (deja activee, morte, hors tour).
    Transformer ce trou de REFERENCE en echec du CAPTEUR accuserait le mauvais coupable."""
    ev = [_ev(unit_id=10, col=3, row=4), _ev(unit_id=11, col=99, row=99)]
    v = check_attribution(ev, {10: {(3, 4)}})     # rien pour u11
    assert v["status"] == "ok", v["message"]
    assert "1/1 unite(s)" in v["message"]


def test_zero_event_ne_conclut_RIEN():
    v = check_attribution([], {10: {(3, 4)}})
    assert v["status"] == "no-events"
    assert "RIEN n'est conclu" in v["message"]


# ------------------------------------------------------------- E3 la decomposition (auto-verif)

def test_decomposition_nominale():
    assert check_decomposition([_ev(total=50.0)])["status"] == "ok"


def test_somme_des_contributions_DIFFERENTE_du_total_est_refusee():
    """L'auto-verification du decodage : `total` vient de `<>2__current`, les contributions du
    DELTA de l'accumulateur -- deux champs, deux chemins de lecture. Un offset d'accumulateur faux
    casse l'egalite, et c'est le seul controle qui le voit sans live."""
    ev = _ev(total=50.0, contribs=[{"playbook": "XPlaybook.<CalculateMovementUtilityInSteps>d__1",
                                    "value": 20.0}])
    v = check_decomposition([ev])
    assert v["status"] == "wrong"
    assert "decodage de l'accumulateur" in v["message"]


def test_etiquette_NON_QUALIFIEE_est_refusee():
    """Sans `il2cpp_class_get_declaring_type`, le nom court d'une state machine est AMBIGU : 39
    classes portent un `<EvaluateMovementInSteps>d__N` sur ce build. Une etiquette sans `Playbook`
    signale que la qualification par le declarant n'a pas eu lieu."""
    ev = _ev(total=20.0, contribs=[{"playbook": "?.<CalculateMovementUtilityInSteps>d__4",
                                    "value": 20.0}])
    v = check_decomposition([ev])
    assert v["status"] == "wrong"
    assert "declarant" in v["message"]


def test_contribs_null_est_NON_MESURE_pas_vide():
    """`null` = l'accumulateur ou l'enumerateur interne n'a pas ete resolu. Le lire comme « aucune
    ability n'a contribue » ferait conclure a un terme MORT."""
    ev = _ev()
    ev["contribs"] = None
    v = check_decomposition([ev])
    assert v["status"] == "not-measured"
    assert "PAS" in v["message"]


# ------------------------------------------------------------------------------ E4 SaviorProtocols

def test_savior_trouve_sa_contribution_sur_le_PORTEUR():
    v = check_savior([_ev(unit_id=10, total=50.0)], carrier_id=10)
    assert v["status"] == "ok"


def test_savior_ne_prend_PAS_la_contribution_d_une_AUTRE_unite():
    """Meme discipline que l'attribution : la contribution de 1120 vue sur u11 ne prouve RIEN sur
    u10. C'est le faux positif de #443-r1, transpose a l'etage de la decomposition."""
    v = check_savior([_ev(unit_id=11, total=50.0)], carrier_id=10)
    assert v["status"] == "absent"


def test_savior_est_SKIP_sans_porteur():
    assert check_savior([_ev()], carrier_id=None)["status"] == "skipped"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
