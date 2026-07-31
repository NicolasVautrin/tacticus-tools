"""#381 -- le decodeur qui tranche la garde d'entree ne doit JAMAIS conclure d'un regime unique.

Ce que cette garde verrouille, et pourquoi elle existe
-----------------------------------------------------
`probe_381` etablit LAQUELLE des deux branches de
`IdunBattle.Core.Services.MovementQuery$$FindAnyOrAllMoveableTiles` rend l'`OrderedSet` VIDE :

    if ( (UnitFlagsComponent$$Has(unitFlags, 1) && ignoreUnitFlags == 0)
       || !UnitExtensions$$CanMove(unit) )   return;

Il le fait en BALAYANT les tours sur une geometrie FIGEE. Le piege propre a cette forme de
mesure : un balayage qui n'observe qu'UN SEUL regime de tour « correle » trivialement, et
rendrait une conclusion sur la moitie de la question. C'est la variante, sur l'axe TEMPS, de la
faute qui a coute ce residu -- un `pool-non-vide` lu sur un bras SANS deficit avait ete relu
comme « la perte est en aval », alors qu'il n'y avait aucune perte a expliquer.

Trois exigences sont donc verrouillees ici :
  1. deux regimes de tour OBSERVES, sinon `regime-unique` ;
  2. correlation PARFAITE dans les deux sens -- un pool non vide sans la main REFUTE la branche
     flag et doit se dire, pas se lisser ;
  3. l'accord avec la requete nue (`aiMovableTiles`) se calcule sur TOUTES les etapes ou sur
     aucune -- jamais sur le sous-ensemble qui repond.

100 % offline : aucun runner, aucune session.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from probe_381_movable_tiles_query_gate import (  # noqa: E402
    _branch_verdict, _query_agreement)


def _s(k, turn, pool, query=None, kind=None, aged=False):
    """Une etape du balayage, telle que `_step` la publie."""
    if kind is None:
        kind = "pool-non-vide" if (pool or 0) > 0 else "query-vide"
    return {"k": k, "caster_has_turn": turn, "pool": pool,
            "query_tiles": (pool if query is None else query),
            "tile_kind": kind, "tile_phrase": "phrase " + str(kind),
            "probe_predates_374": aged, "query": {"error": None}}


# --- l'oscillation MESUREE le 2026-07-31 (runner 80, geometrie de `#386` sec.1) : le pool suit
#     exactement le tour, et la requete nue s'y accorde a la tuile pres.
_MESURE = [_s(0, True, 51), _s(1, False, 0), _s(2, True, 51), _s(3, False, 0)]


def test_le_balayage_mesure_tranche_la_branche_flag():
    kind, phrase = _branch_verdict(_MESURE)
    assert kind == "branche-flag"
    # Le symbole natif DOIT etre nomme : « c'est le flag » sans le foyer n'est pas invalidable.
    assert "UnitFlagsComponent$$Has" in phrase
    assert "FindAnyOrAllMoveableTiles" in phrase


def test_un_seul_regime_de_tour_ne_conclut_RIEN():
    """LE piege de cette forme de mesure : n'observer que les etapes ou le caster a la main
    « correle » trivialement, et rendrait `branche-flag` sur la moitie de la question."""
    kind, phrase = _branch_verdict([_s(0, True, 51), _s(2, True, 51)])
    assert kind == "regime-unique"
    assert "indiscernables" in phrase
    # ... et symetriquement, ne voir que le regime sans la main ne conclut pas non plus.
    assert _branch_verdict([_s(1, False, 0), _s(3, False, 0)])[0] == "regime-unique"


def test_pool_vide_MEME_avec_la_main_accuse_l_etat_persistant():
    """L'autre branche de la garde : `UnitExtensions$$CanMove` lit un trait et un dictionnaire de
    blocages -- deux etats qu'un `endturn` ne change pas."""
    kind, phrase = _branch_verdict([_s(0, True, 0), _s(1, False, 0)])
    assert kind == "branche-persistante"
    assert "CanMove" in phrase
    assert kind != _branch_verdict(_MESURE)[0]


def test_correlation_imparfaite_REFUSE_de_trancher():
    """Un pool non vide alors que le caster n'a PAS la main refute la branche flag. Le decodeur
    doit le DIRE, pas l'absorber dans une majorite."""
    kind, phrase = _branch_verdict(
        [_s(0, True, 51), _s(1, False, 51), _s(2, True, 51), _s(3, False, 0)])
    assert kind == "correlation-imparfaite"
    assert "REFUSE" in phrase


def test_capteur_non_exploitable_bascule_en_non_confronte_jamais_en_pool_vide():
    for kind in ("absent", "non-arme", "retour-illisible", "structure-inattendue",
                 "sous-maillon-non-arme", "fenetre-vide"):
        k, phrase = _branch_verdict([_s(0, True, None, kind=kind), _s(1, False, 0)])
        assert k == "non-confronte", "l'etat %r se lit [%s]" % (kind, k)
        assert "Rien n'est conclu" in phrase
    # Un bundle ANTERIEUR a #374 fire et compte ses appels : sans ce discriminant on l'accuserait
    # d'etre incoherent au lieu de dire qu'il n'est pas charge.
    k, _ = _branch_verdict([_s(0, True, 51, aged=True), _s(1, False, 0)])
    assert k == "non-confronte"


def test_zero_appel_accuse_l_AMONT_et_ne_se_confond_pas_avec_un_pool_vide():
    """`nodes == []` (l'arbre n'est PAS evalue) et `returnedCount == 0` (il l'est et rend vide)
    portent des verdicts OPPOSES -- le decodeur #370 le dit deja, #381 ne doit pas le defaire."""
    kind, phrase = _branch_verdict(
        [_s(0, True, 0, kind="zero-appel"), _s(1, False, 0)])
    assert kind == "amont"
    assert "AMONT" in phrase
    assert kind != _branch_verdict([_s(0, True, 0), _s(1, False, 0)])[0]


def test_tour_illisible_ne_compte_pas_comme_une_mesure():
    step = _s(0, None, 51)
    kind, _ = _branch_verdict([step, _s(1, False, 0)])
    assert kind == "non-confronte"


def test_aucune_etape_ne_rend_pas_un_verdict():
    kind, _ = _branch_verdict([])
    assert kind == "aucune-etape"


def test_accord_avec_la_requete_nue_est_STRICT():
    """Le piege `side="friendly"` : ce filtre fait disparaitre le caster EXACTEMENT quand il n'a
    pas la main. Il ne resterait que les etapes ou tout marche -- un accord parfait sur la moitie
    de la question. Une seule etape muette doit rendre l'accord NON CONCLUANT."""
    ok, phrase = _query_agreement(_MESURE)
    assert ok is True
    assert "s'accordent" in phrase
    muet = [_s(0, True, 51), dict(_s(1, False, 0), query_tiles=None), _s(2, True, 51)]
    ok2, phrase2 = _query_agreement(muet)
    assert ok2 is None, "une etape muette a ete ecartee du calcul au lieu de le suspendre"
    assert "sous-ensemble" in phrase2


def test_desaccord_avec_la_requete_nue_accuse_le_contexte_DSL():
    """Si le pool DSL est vide la ou la requete nue rend des tuiles, le vide ne vient PAS de
    `GetMovableTilesFor` -- et ce serait une conclusion opposee."""
    ok, phrase = _query_agreement([_s(0, True, 0, query=13), _s(1, False, 0)])
    assert ok is False
    assert "DESACCORD" in phrase
    assert "contexte DSL" in phrase


def test_les_sept_etats_du_decodeur_sont_deux_a_deux_distincts():
    kinds = {
        _branch_verdict([])[0],
        _branch_verdict([_s(0, True, 51, kind="absent"), _s(1, False, 0)])[0],
        _branch_verdict([_s(0, True, 0, kind="zero-appel"), _s(1, False, 0)])[0],
        _branch_verdict([_s(0, True, 51), _s(2, True, 51)])[0],
        _branch_verdict(_MESURE)[0],
        _branch_verdict([_s(0, True, 0), _s(1, False, 0)])[0],
        _branch_verdict([_s(0, True, 51), _s(1, False, 51), _s(3, False, 0)])[0],
    }
    assert len(kinds) == 7, "deux etats du decodeur se confondent : %s" % sorted(kinds)


def test_capteur_muet_et_tour_illisible_partagent_non_confronte_VOLONTAIREMENT():
    """Les deux disent la MEME chose -- le harnais n'est pas en etat de repondre -- et aucune des
    deux n'autorise a conclure du natif. C'est le seul partage d'etiquette du decodeur, et il est
    assume : leurs PHRASES, elles, restent distinctes."""
    a = _branch_verdict([_s(0, True, 51, kind="absent"), _s(1, False, 0)])
    b = _branch_verdict([_s(0, None, 51), _s(1, False, 0)])
    assert a[0] == b[0] == "non-confronte"
    assert a[1] != b[1]
    assert "capteur non exploitable" in a[1]
    assert "sans pool ou sans tour lisible" in b[1]
