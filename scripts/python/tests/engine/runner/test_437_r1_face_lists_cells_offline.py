"""#437-r1 -- les CELLULES NATIVES du tir d'overwatch, verrouillees OFFLINE.

Le natif appelle `IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers` DEUX FOIS
dans `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` -- une fois
sur `attackModifiers`, une fois sur `defenseModifiers` -- et cette fonction porte un
`FixMath.NET.Fix64$$Round(., AwayFromZero)` PAR ENTREE. La face DEFENSEUR part donc d'une valeur
DEJA MATERIALISEE. Le port COMBAT fusionnait les deux faces dans UNE chaine, donc UN seul arrondi :
`-1` sur la borne des que le produit de la face attaquant tombait sur un demi-entier.

LES CELLULES, ET COMMENT ELLES ONT ETE OBTENUES. Ce ne sont pas des soustractions : les bornes
natives sont INVERSEES depuis l'alea BRUT du tirage. `IdunBattle.Utils.PRNG.
IntBasedMersenneTwister$$NextInternal` rend `lo + ((genrand >> 1) % (hi + 1 - lo))` ; a `r` connu
(rejeu offline sur le MEME `dumpRng`) et degat natif connu, on enumere les (lo, hi) qui satisfont
l'egalite. Montage `probe_437r1_overwatch_offbyone.py --capture --dmg-target N` (board `MC1_67`,
seed 4321, `eldarRanger` -> `spaceStormcaller`) :

  base d'attaque | bornes brutes | bornes NATIVES  | chaine unique   | deux appels
  4518           | 3614 / 5422   | (1130, 1695)    | (1129, 1694) X  | (1130, 1695) OK
  4526           | 3621 / 5431   | (1132, 1697)    | (1132, 1697) OK | (1132, 1697) OK   <- TEMOIN
  4538           | 3630 / 5446   | (1135, 1702)    | (1134, 1702) X  | (1135, 1702) OK   <- UNIQUE

La base 4526 est le TEMOIN NON DISCRIMINANT : les deux modeles y coincident. Sans lui, on ne
saurait pas qu'un accord peut venir du REGIME et non du modele. La base 4538 est la seule dont
l'inversion rende UNE SEULE paire -- c'est elle qui porte la preuve.

Faces du regime : ATTAQUANT = `HeavyWeapon_ExtraDmg` (effet, `PercentIncrease` 25 -> x1.25),
DEFENSEUR = `TerminatorArmour_ReduceDmg` (effet, `PercentDecrease` 75 -> x0.25). Percage 30,
armure 0 (`--hp-player` met Armor/FixedArmor a 0) -> la branche `d - armure` gagne et la valeur
d'entree est ENTIERE : le regime ne doit RIEN a une fraction de percage, contrairement a #446-r2 /
#462-r4d. C'est un gisement distinct.

Ce cran appelle le FOYER REEL (`apply_pierce_and_modifiers`), jamais une reimplementation.
ASCII only.
"""
from __future__ import annotations

import pytest

from engine.services.damage_modifiers import DamageModifiers
from engine.services.damage_prediction import apply_pierce_and_modifiers, get_base_damage_fix64

PIERCE = 30
ARMOR = 0
ATT_PCT = 1.25          # HeavyWeapon_ExtraDmg  (PercentIncrease 25)
DEF_PCT = 0.25          # TerminatorArmour_ReduceDmg (PercentDecrease 75)

# (base d'attaque, bornes brutes attendues, bornes NATIVES, discriminant ?)
CELLS = [
    (4518, (3614, 5422), (1130, 1695), True),
    (4526, (3621, 5431), (1132, 1697), False),      # TEMOIN : les deux modeles coincident
    (4538, (3630, 5446), (1135, 1702), True),       # inversion a solution UNIQUE
]


def _mods():
    """L'accumulateur tel que le COMBAT le presente : face ATTAQUANT dans `pct_list`, face
    DEFENSEUR deja fusionnee dans `pct_list_defender` (ce que fait
    `AttackDamageOperation._apply_defender_flat_reductions`)."""
    m = DamageModifiers()
    m.pct_list.append((ATT_PCT, None))
    m.pct_list_defender.append((DEF_PCT, None))
    return m


def _bound(base_value: int, separate: bool) -> int:
    return int(apply_pierce_and_modifiers(base_value, PIERCE, ARMOR, _mods(),
                                          attacker_additive_pre=True,
                                          separate_face_lists=separate))


@pytest.mark.parametrize("attack,raw,native,_disc", CELLS)
def test_bornes_brutes_du_spread(attack, raw, native, _disc):
    """Etage AMONT : `GetBaseDamageFix64` (spread 20%). Si celui-ci derivait, les cellules
    ci-dessous ne mesureraient plus le meme etage."""
    mm = get_base_damage_fix64(attack, extra_max=0, spread_pct=20)
    assert (int(mm.min), int(mm.max)) == raw


@pytest.mark.parametrize("attack,raw,native,_disc", CELLS)
def test_cellules_natives_avec_faces_separees(attack, raw, native, _disc):
    """Le port COMBAT doit rendre les bornes NATIVES, a l'unite, sur les trois bases."""
    got = (_bound(raw[0], True), _bound(raw[1], True))
    assert got == native, ("base %d : bornes %s attendues %s (natives, inversees depuis l'alea "
                           "brut du tirage)" % (attack, got, native))


@pytest.mark.parametrize("attack,raw,native,disc", [c for c in CELLS if c[3]])
def test_la_chaine_unique_manque_la_cellule(attack, raw, native, disc):
    """CONTRE-EPREUVE : la sequence d'`origin/master` (UNE chaine, donc UN seul arrondi) rate la
    borne basse. Sans ce cran, un cas non discriminant pourrait faire croire que les deux modeles
    se valent."""
    got = (_bound(raw[0], False), _bound(raw[1], False))
    assert got != native, ("base %d : la chaine unique rend %s, or elle doit DIFFERER des bornes "
                           "natives %s -- sinon cette base n'est pas discriminante et n'a rien a "
                           "faire dans cette liste" % (attack, got, native))
    assert got[0] == native[0] - 1, ("base %d : l'ecart attendu sur la borne BASSE est -1 "
                                     "(un arrondi manquant), obtenu %s vs %s"
                                     % (attack, got, native))


def test_temoin_non_discriminant_coincide():
    """La base 4526 rend la MEME chose avec et sans le drapeau. C'est ce qui prouve qu'un accord
    ne vaut pas preuve de modele -- et c'est pour ca qu'elle est dans la liste."""
    attack, raw, native, disc = CELLS[1]
    assert disc is False
    assert (_bound(raw[0], True), _bound(raw[1], True)) == native
    assert (_bound(raw[0], False), _bound(raw[1], False)) == native


def test_no_op_quand_une_face_est_vide():
    """Le drapeau est STRICTEMENT NO-OP des qu'une des deux `%-list` est vide -- c'est ce qui
    conserve tous les regimes a UNE face deja mesures (#446-r2 `T` et `A`, le balayage d'armure de
    #462-r4a, les cellules #462-r4d). `apply_pct_entries([])` rend la valeur INCHANGEE, sans
    `Round` : il n'y a donc aucun arrondi surnumeraire a fabriquer."""
    for att, deff in (((1.25,), ()), ((), (0.25,)), ((), ())):
        m = DamageModifiers()
        m.pct_list.extend((v, None) for v in att)
        m.pct_list_defender.extend((v, None) for v in deff)
        for base in (3614, 3621, 3630, 5422, 5446, 1445, 907):
            a = apply_pierce_and_modifiers(base, PIERCE, ARMOR, m, attacker_additive_pre=True,
                                           separate_face_lists=True)
            b = apply_pierce_and_modifiers(base, PIERCE, ARMOR, m, attacker_additive_pre=True,
                                           separate_face_lists=False)
            assert int(a) == int(b), ("faces att=%s def=%s base=%d : le drapeau a DEPLACE une "
                                      "valeur alors qu'une face est vide (%s vs %s)"
                                      % (att, deff, base, a, b))
