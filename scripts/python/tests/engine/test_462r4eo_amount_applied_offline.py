"""#462-r4e-o -- GARDE OFFLINE de `damage_amount_applied` : les BRANCHES que le live n'exerce pas.

`test_overkill_amount_live.py` confronte la borne au natif sur trois regimes de bataille. Mais deux
branches du mirror n'y sont jamais armees, et le dire est le point : aucune des cibles jouables n'a
de BOUCLIER non nul, ni de plancher `Minimum` (`FillUpStatComponent+0x1c`, le HP-floor
Hypersensory). Ce fichier garde donc la FORME du mirror, la ou le live garde sa VALEUR.

Le natif mirrore (`IdunBattle.Entities.Components.FillUpStatComponent$$Reduce`, plus le second terme
d'`IdunBattle.Operations.ApplyDamageOperation$$Execute`) :

    applied = Math.Min(Math.Max(0, damage), Current)
    if (!ignoreMinimum && Minimum.HasValue)
        applied = Math.Min(Current - Math.Min(Current, Minimum.Value), applied)
    Current -= applied ; return applied            # + ApplyDamageOperation.ReduceShield(.)

ASCII only.
"""
from __future__ import annotations

from engine.runner.operations.damage_hits import damage_amount_applied as amount


def test_borne_aux_pv_courants():
    """`Min(Max(0, damage), Current)` -- le surplus n'est PAS rapporte."""
    assert amount(2404, 0, 1643) == (1643, 0)      # le coup letal de MC1_67/31337
    assert amount(2289, 0, 979) == (979, 0)        # le coup 3 de C3_01/777 (ecrete PARTIELLEMENT)
    assert amount(500, 0, 1000) == (500, 500)      # sous les PV : inchange


def test_coup_sur_cadavre_rapporte_zero():
    """PV a 0 -> `Amount` 0, et les PV ne descendent pas sous 0."""
    assert amount(2203, 0, 0) == (0, 0)            # le coup 4 de C3_01/777


def test_degat_negatif_clampe_a_zero():
    """`Math.Max(0, damage)` -- une entree negative ne SOIGNE pas."""
    assert amount(-50, 0, 1000) == (0, 1000)


def test_bouclier_s_ajoute_sans_passer_par_la_borne_pv():
    """Le second terme est `ApplyDamageOperation.ReduceShield`, DEJA borne par le split
    shield-first : il s'AJOUTE au retrait de PV, il n'est pas ecrete par les PV restants."""
    assert amount(500, 120, 1000) == (620, 500)    # 500 PV + 120 bouclier
    assert amount(2404, 300, 1643) == (1943, 0)    # PV ecretes a 1643, bouclier intact
    assert amount(0, 250, 0) == (250, 0)           # cible a 0 PV, bouclier encore absorbant


def test_plancher_minimum_borne_avant_les_pv():
    """`Min(Current - Min(Current, Minimum.Value), applied)` -- le HP-floor Hypersensory."""
    assert amount(900, 0, 1000, 300) == (700, 300)   # ne descend pas sous 300
    assert amount(50, 0, 1000, 300) == (50, 950)     # plancher non atteint : inchange
    assert amount(900, 0, 200, 300) == (0, 200)      # deja SOUS le plancher : plus rien ne passe


def test_borne_decroissante_sur_une_salve():
    """Les PV restants se resserrent COUP PAR COUP (le natif applique un coup a la fois :
    `DamageAppliedResult` porte un `hitIndex` @+0x14). Rejoue C3_01/777 a l'identique."""
    hp, out = 7530, []
    for brut in (2764, 3787, 2289, 2203):
        a, hp = amount(brut, 0, hp)
        out.append(a)
    assert out == [2764, 3787, 979, 0] and hp == 0
