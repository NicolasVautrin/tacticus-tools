"""#462-r4b-r1 -- GARDE OFFLINE : l'ADDITIF DEFENSEUR partage le slot PRE-PERCAGE de l'attaquant.

`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` resout ses DEUX accumulateurs par les
slots d'interface `0xd` et `0xe`, lit le champ `+0x10` (`Addition`) de CHACUN via
`FixMath.NET.Fix64$$op_Explicit`, et passe a
`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` la SOMME
`base + Addition(0xd) + Addition(0xe)` -- aux DEUX call-sites (borne MIN et borne MAX).
`CalculateBaseDamageWithAllModifiers` NE re-consomme PAS `+0x10` : il commence par
`GetBaseDamageWithFixedPiercedArmor`. L'additif du DEFENSEUR traverse donc percage/armure PUIS les
deux `%-list`, EXACTEMENT comme celui de l'ATTAQUANT (#75).

Le COMBAT laissait cet additif a `apply_all_modifiers(., def_mods)`, qui l'ajoute APRES les %-list et
les deux `Multiplier@0x30` : un montant NI dilue par l'armure NI reduit par la face defenseur.

CE QUE CETTE GARDE VERROUILLE, avec les valeurs EXACTES du cas mesure
(`probe_462_r4b_r1_terminator_commanded_attack.py`, chaine `ExemplarOfHate` de `darkaAsmodai` sur
`blackAbaddon`, runner `MC1_67`/seed 112112) :

  * override d'Attack 2008 -> bornes `GetBaseDamageFix64` 1606 / 2410 ;
  * percage 40 (profil `Power`), armure 2510 ;
  * additif ATTAQUANT 997 (`FearedInterrogator_Owner.extraDmg`, `HasEffect(Target, 1295)`) ;
  * additif DEFENSEUR 997 (`ExemplarOfHate_Target.extraDmg`, pose par la chaine elle-meme) ;
  * `%-list` DEFENSEUR `x0.25` (`TerminatorArmour_ReduceDmg`, `terminatorArmourDmgReduction = -75`).

Bornes natives = **360 / 474** (per-coup live bit-exact `[449, 401, 428, 445, 460, 413]`).
Le placement POST-%-list -- celui d'avant ce correctif -- rendait **1257 / 1338**, soit 7730 degats
contre 2596. ASCII only.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PY = os.path.dirname(os.path.dirname(_HERE))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

from engine.runner.operations.damage import AttackDamageOperation           # noqa: E402
from engine.services.damage_modifiers import (                              # noqa: E402
    DamageModifiers, apply_all_modifiers)
from engine.services.damage_prediction import apply_pierce_and_modifiers    # noqa: E402

BASE_MIN, BASE_MAX = 1606, 2410     # `GetBaseDamageFix64(2008)`, spread 20 %
PIERCE, ARMOR = 40, 2510            # profil `Power` / armure de `blackAbaddon`
ADD_ATT = 997.0                     # `FearedInterrogator_Owner.extraDmg`
ADD_DEF = 997.0                     # `ExemplarOfHate_Target.extraDmg`
TERMINATOR = 0.25                   # `terminatorArmourDmgReduction = -75`

NATIVE_BOUNDS = (360, 474)          # mesure live, per-coup bit-exact
POST_PCT_BOUNDS = (1257, 1338)      # le placement d'AVANT #462-r4b-r1


def _accumulators():
    """Les DEUX accumulateurs tels que les rendent `attacker_modifiers` / `defender_modifiers`,
    AVANT le merge -- c'est l'entree exacte de `_apply_defender_flat_reductions`."""
    att = DamageModifiers()
    att.additive = ADD_ATT
    deff = DamageModifiers()
    deff.additive = ADD_DEF
    deff.pct_list.append((TERMINATOR, None))
    return att, deff


def _bounds(att, deff):
    """Les deux etages que `_reduced_bounds` enchaine, a l'identique."""
    return tuple(
        apply_all_modifiers(
            apply_pierce_and_modifiers(v, PIERCE, ARMOR, att, hit_mult=1,
                                       attacker_additive_pre=True),
            deff, round_materialize=True)
        for v in (BASE_MIN, BASE_MAX))


def test_le_foyer_DEPLACE_l_additif_defenseur_et_VIDE_la_source():
    """Le geste lui-meme : `_apply_defender_flat_reductions` transfere `Addition@+0x10` du defenseur
    dans l'accumulateur consomme PRE-percage, et VIDE la source -- sans ce second point,
    `apply_all_modifiers(def_mods)` en aval le compterait une SECONDE fois."""
    att, deff = _accumulators()
    AttackDamageOperation._apply_defender_flat_reductions(att, deff)
    assert att.additive == ADD_ATT + ADD_DEF, (
        "additif fusionne attendu %s, obtenu %s" % (ADD_ATT + ADD_DEF, att.additive))
    assert deff.additive == 0.0, "source non videe -> double-application dans apply_all_modifiers"


def test_les_bornes_reduites_valent_le_natif():
    """Bout en bout, sur le regime MESURE : 360 / 474. C'est le couple qui rend le degat total de
    2596 relevé live -- le seul axe que #462-r4b avait laisse sans aucune assertion."""
    att, deff = _accumulators()
    AttackDamageOperation._apply_defender_flat_reductions(att, deff)
    assert _bounds(att, deff) == NATIVE_BOUNDS, (
        "bornes attendues %s, obtenues %s" % (NATIVE_BOUNDS, _bounds(att, deff)))


def test_le_placement_POST_pct_list_est_bien_le_modele_REFUTE():
    """CONTRE-MODELE ECRIT (pas monkeypatche) : sans le transfert, l'additif defenseur est ajoute
    par `apply_all_modifiers` APRES les %-list et les deux `Multiplier`. Il echappe alors a l'armure
    ET a la reduction `TerminatorArmour`, et rend 1257 / 1338 -- 2,98x le natif. Ce test est ce qui
    empeche `NATIVE_BOUNDS` d'etre un nombre sans adversaire : les deux modeles doivent DIFFERER,
    sinon le regime n'est pas discriminant et la garde ci-dessus ne verrouille rien."""
    att, deff = _accumulators()          # AUCUN merge : l'etat d'`origin/master` avant ce correctif
    assert _bounds(att, deff) == POST_PCT_BOUNDS, (
        "contre-modele attendu %s, obtenu %s" % (POST_PCT_BOUNDS, _bounds(att, deff)))
    assert POST_PCT_BOUNDS != NATIVE_BOUNDS, "regime NON discriminant"


def test_les_deux_placements_COINCIDENT_sur_la_branche_ARMURE():
    """LA BORNE DU PHENOMENE, et la raison pour laquelle le residu ne s'est vu que sur ce bras-la.

    Le plancher de `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor`
    est `max(d x pierce%, d - armure)`. Sur la branche ARMURE il est AFFINE DE PENTE 1, donc
    `P(v + A) = P(v) + A` : les deux placements rendent le MEME nombre. Il faut donc OU une `%-list`
    defenseur, OU la branche PERCAGE gagnante, pour qu'un ecart apparaisse. MESURE du bras `followup`
    du probe (Hellblaster melee `Physical` sur `blackAbaddon`, armure consommee) : port == contre-
    modele == natif == 2746 -- un accord qui ne prouve RIEN sur le placement. Ce test fige ce fait
    pour qu'aucune mesure future ne se lise comme une confirmation."""
    lo_pierce, armor = 1, ARMOR              # profil `Physical` du Hellblaster, armure de la cible
    bases = (5000, 6000)

    def _b(a, d):
        return tuple(apply_all_modifiers(
            apply_pierce_and_modifiers(v, lo_pierce, armor, a, hit_mult=1,
                                       attacker_additive_pre=True),
            d, round_materialize=True) for v in bases)

    # On MESURE que la branche ARMURE gagne bien -- sans ca le cran ne dit rien.
    for v in bases:
        for extra in (0, ADD_ATT + ADD_DEF):
            d = v + extra
            assert d - armor > d * lo_pierce / 100.0, "regime hors branche ARMURE (d=%s)" % d

    att, deff = _accumulators()
    deff.pct_list.clear()
    post = _b(att, deff)
    att, deff = _accumulators()
    deff.pct_list.clear()
    AttackDamageOperation._apply_defender_flat_reductions(att, deff)
    assert _b(att, deff) == post, (
        "sur la branche ARMURE les deux placements doivent COINCIDER : %s vs %s" % (_b(att, deff), post))


def test_l_additif_defenseur_est_DILUE_par_l_armure_meme_sans_reduction():
    """Le second axe, INDEPENDANT de `TerminatorArmour` : meme sans la moindre `%-list`, le placement
    change le resultat, parce que l'additif traverse `GetBaseDamageWithFixedPiercedArmor`. C'est le
    bras `control` du probe (`blackPossession`, armure 1806, aucune reduction) : natif 1794 / 2598,
    placement POST 2038 / 2598. Les DEUX bornes ne separent PAS -- seule la MIN le fait, parce que
    la borne MAX bascule sur la branche ARMURE du plancher `max(d x pierce%, d - armure)`."""
    att, deff = _accumulators()
    deff.pct_list.clear()                                  # pas de TerminatorArmour ici
    lo_post, hi_post = _bounds(att, deff)
    att, deff = _accumulators()
    deff.pct_list.clear()
    AttackDamageOperation._apply_defender_flat_reductions(att, deff)
    lo_pre, hi_pre = _bounds(att, deff)
    assert (lo_pre, hi_pre) != (lo_post, hi_post), "l'armure ne separe pas les deux placements ici"
    assert lo_pre < lo_post, "l'additif pre-percage doit etre DILUE, donc rendre MOINS"
