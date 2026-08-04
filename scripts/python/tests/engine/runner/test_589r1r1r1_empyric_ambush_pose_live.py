"""CLIQUET #589-r1-r1-r1 -- la POSE d'`EmpyricAmbush` (ability ACTIVE **1232**).

CRITERE : « quand `eldarLhykhis` caste 1232, le PORT reproduit-il les TROIS observables du natif --
la TUILE ou elle atterrit, la salve de degats par coup, et la marque 1578 posee sur la cible -- a
partir du MEME etat et du MEME flux PRNG ? »

Avant ce port, `EmpyricAmbushAbility` etait absente d'`ABILITY_CLASSES` : le cast offline etait un
NO-OP COMPLET, et l'effet 1578 (porte, lui, par #589-r1-r1) n'entrait dans l'etat du port QUE par
la capture live. Un replay-diff qui aurait fait caster Lhykhis PAR LE PORT divergeait.

Le montage est IMPORTE de `probe_589r1r1r1_empyric_ambush_pose_live.py` au lieu d'etre
re-transcrit : un montage duplique derive de son original sans que rien ne le signale.

LES DEUX FACES, mesurees SEPAREMENT (decider != executer) :
  * DECIDER  -- `abilityReason` rend le masque `TargetingRule` NATIF par cible ; le port le rejoue
    par `is_invalid_target`. Le bras `--encercle` exerce le bit 5 `TargetHasFreeAdjacentTile`
    (0x20), que rien d'autre n'atteint.
  * EXECUTER -- le cast, rejoue offline sur le snapshot pris JUSTE AVANT, RNG cale sur le meme
    instant.

TROIS confrontations, et les deux dernieres sont ce qui interdit l'accord DEGENERE :
  1. LIVE == OFFLINE ;
  2. mutation `NOPORT` (1232 retiree d'`ABILITY_CLASSES`) : le rejeu doit CHANGER sur les TROIS
     observables -- c'est la vue « d'avant ce port » ;
  3. mutation `NORANDOM` (le noeud `Randomize` remplace par l'identite) : elle repond a la seule
     question que `NOPORT` ne peut pas poser -- l'etage de TIRAGE mord-il ? Si la tuile ne bougeait
     pas sans lui, l'accord sur le landing ne prouverait rien du PRNG.

ASCII only.
"""
from __future__ import annotations

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(__file__))
_PYDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if _PYDIR not in sys.path:
    sys.path.insert(0, _PYDIR)

from probe_589r1r1r1_empyric_ambush_pose_live import (  # noqa: E402
    ABILITY_TYPE, TR_TARGET_HAS_FREE_ADJACENT_TILE, cast_live, face_decision, replay,
    seed_bc_avec_lhykhis, stage, stage_encercle)

from _charge_regime import charge_regime  # noqa: E402,F401  (fixture)

_SEED_BC = seed_bc_avec_lhykhis()
_ARGS = types.SimpleNamespace(verbose=False)


def _monte(charge_regime, board, seed, encercle=False):
    """UN runner par bras. `--crit 0,0` : aucun coup ne crite des DEUX cotes, donc la salve est le
    pipeline de degat NU -- le canal crit de l'effet 1578 est confronte ailleurs
    (`test_empyric_ambush_threshold_live.py`), il n'a rien a faire ici."""
    h = charge_regime(p_units="eldarLhykhis,blackHaarken",
                      a_units="necroWarden,necroOverlord", seed=seed, board=board,
                      extra=["--crit", "0,0", "--block-target", "0,0",
                             "--hp-target", "900000", "--hp-player", "900000",
                             "--seed-bc", _SEED_BC])
    rec, why = (stage_encercle(h, _ARGS) if encercle else stage(h, _ARGS))
    assert rec is not None, "montage NON ATTEINT (%s) -- jamais un skip vert" % why
    return h, rec


@pytest.mark.parametrize("board,seed", [("MC1_67", "777"), ("C1_74", "31337")])
def test_la_pose_reproduit_le_natif_sur_les_trois_observables(charge_regime, board, seed):
    """FACE EXECUTER. Le vol, la salve et la marque, sur le MEME etat et le MEME flux PRNG.

    `NOPORT` doit mordre sur les TROIS : sans elle, un port qui ne ferait RIEN pourrait « concorder »
    avec un natif qui ne ferait rien non plus."""
    h, rec = _monte(charge_regime, board, seed)
    live, why = cast_live(h, rec)
    assert live is not None, "cast live non joue : %s" % why
    off = replay(h, rec)
    mut = replay(h, rec, mutate="NOPORT")

    assert off["ported"] is True, "1232 doit etre AU REGISTRE, sinon la mesure est vide"
    assert off["landing"] == live["landing"], (
        "tuile d'atterrissage : port %s != natif %s" % (off["landing"], live["landing"]))
    assert off["hits"] == live["hits"], (
        "salve : port %s != natif %s" % (off["hits"], live["hits"]))
    assert bool(off["marked"]) is bool(live["marked"]) is True, (
        "la marque 1578 doit etre posee des DEUX cotes (port=%s natif=%s)"
        % (off["marked"], live["marked"]))
    assert (mut["landing"] != off["landing"] and not mut["hits"] and not mut["marked"]), (
        "NOPORT ne mord pas : sans l'ability au registre le cast doit etre un NO-OP COMPLET "
        "(landing=%s hits=%s marked=%s)" % (mut["landing"], mut["hits"], mut["marked"]))


def test_la_marque_dure_UN_tour_et_ce_n_est_pas_TurnsFromRounds(charge_regime):
    """LA DUREE, pas seulement la presence. Le natif passe `turns = <DSLFormulas+0x20> = Direct(1)`
    -- un nombre de TOURS deja resolu, PAS un `TurnsFromRounds`. Les deux formes posent la marque :
    seule la duree les separe, et rien d'autre dans ce fichier ne la regarderait.

    Le temoin `ROUNDS` est ce qui rend ce cran honnete : il rejoue la MEME pose en
    `TurnsFromRounds(1)` et doit donner une AUTRE valeur -- sinon le cran ne discriminerait rien."""
    h, rec = _monte(charge_regime, "MC1_67", "777")
    live, why = cast_live(h, rec)
    assert live is not None, "cast live non joue : %s" % why
    off = replay(h, rec)
    rnd = replay(h, rec, mutate="ROUNDS")
    assert live["remaining"] is not None and off["remaining"] is not None, (
        "duree NON MESUREE (live=%s port=%s) -- ce n'est PAS un accord"
        % (live["remaining"], off["remaining"]))
    assert off["remaining"] == live["remaining"], (
        "duree de la marque : port %s != natif %s" % (off["remaining"], live["remaining"]))
    assert rnd["remaining"] != off["remaining"], (
        "TurnsFromRounds(1) rend la MEME duree (%s) : ce cran ne discrimine rien"
        % rnd["remaining"])


def test_l_etage_de_tirage_mord_et_le_port_tombe_sur_la_tuile_native(charge_regime):
    """L'ETAGE PRNG, isole. `Randomize` est un `PickRandomAmountSelector` a `amount = 0x7fffffff`
    sans repetition = une PERMUTATION COMPLETE du pool (`len(pool)` tirages), et il est enveloppe par
    un `OrderBy` STABLE : l'alea ne survit donc que sur les EX AEQUO d'utilite.

    Le remplacer par l'identite doit CHANGER la tuile choisie. Si ce n'etait pas le cas, l'accord du
    test precedent sur le landing ne prouverait rien de ce niveau -- il serait compatible avec un
    port qui tire au MAUVAIS moment, ou qui ne tire pas du tout."""
    h, rec = _monte(charge_regime, "MC1_67", "777")
    live, why = cast_live(h, rec)
    assert live is not None, "cast live non joue : %s" % why
    off = replay(h, rec)
    nrd = replay(h, rec, mutate="NORANDOM")
    assert off["landing"] == live["landing"], "port %s != natif %s" % (off["landing"], live["landing"])
    assert nrd["landing"] != off["landing"], (
        "NORANDOM rend la MEME tuile (%s) : cet etage n'est pas exerce par ce montage, donc "
        "l'accord sur le landing ne mesure pas le tirage" % nrd["landing"])


def test_le_gate_de_ciblage_accorde_avec_le_masque_natif(charge_regime):
    """FACE DECIDER, contrat de fidelite : natif == 0 => port == 0 (STRICT, le port n'invente aucun
    refus) ; natif != 0 => port == natif ou 0 ; JAMAIS un refus pour la mauvaise raison."""
    h, rec = _monte(charge_regime, "MC1_67", "777")
    dec, why = face_decision(h, rec)
    assert dec is not None, "face DECIDER non mesuree : %s" % why
    assert dec["rows"], "aucune cible confrontee -- le bras ne prouve rien"
    assert not dec["fautes"], "\n".join(dec["fautes"])


def test_le_bit_target_has_free_adjacent_tile_refuse_des_deux_cotes(charge_regime):
    """Le SEUL bras qui exerce le bit 5 du masque `0x6004020`. Cible ENCERCLEE (aucune tuile libre au
    contact) : le natif rompt `TargetHasFreeAdjacentTile`, et le port doit rompre la MEME regle.

    C'est le pendant DECISION exact du `CanAddUnit(AdjacentTiles(cible))` du behaviour -- sans tuile
    libre autour de la cible, le `FlyUnit` n'aurait nulle part ou poser Lhykhis."""
    h, rec = _monte(charge_regime, "MC1_67", "777", encercle=True)
    dec, why = face_decision(h, rec)
    assert dec is not None, "face DECIDER non mesuree : %s" % why
    ligne = next((r for r in dec["rows"] if r[0] == rec["target"]), None)
    assert ligne is not None, "la cible encerclee n'a pas ete confrontee"
    uid, natif, port, noms = ligne
    assert natif & int(TR_TARGET_HAS_FREE_ADJACENT_TILE), (
        "le natif n'a PAS rompu TargetHasFreeAdjacentTile (0x%x, %s) -- regime NON ATTEINT, le bras "
        "ne prouve rien" % (natif, noms))
    assert port == natif, "port 0x%x != natif 0x%x sur la cible encerclee" % (port, natif)
    assert not dec["fautes"], "\n".join(dec["fautes"])


def test_le_registre_porte_l_ability_et_ses_deux_donnees_obligatoires():
    """Garde STRUCTURELLE : une ability au registre SANS son masque de ciblage est PERMISSIVE en
    silence, et sans son `AbilityAttackType` le vecteur `On(PreUnitAbility)` route a cote. Les deux
    donnees sont posees dans le meme commit que l'entree au registre -- ce test le fige."""
    from engine.runner.abilities.aeldari import EmpyricAmbushAbility
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.handler import ABILITY_CLASSES
    assert ABILITY_CLASSES.get(ABILITY_TYPE) is EmpyricAmbushAbility
    opts = EmpyricAmbushAbility.TARGETING_OPTIONS
    assert opts is not None and int(opts.rules) == 0x6004020, (
        "masque != le litteral du ctor natif (0x%x)" % int(opts.rules))
    assert ABILITY_ATTACK_TYPE.get(ABILITY_TYPE) == AbilityAttackType.DirectTargetAttack
