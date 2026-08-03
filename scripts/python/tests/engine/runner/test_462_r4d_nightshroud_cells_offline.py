"""#462-r4d -- CRAN OFFLINE : les cellules du coup sous un `EffectBonus %` DEFENSEUR.

Regime : `necroDestroyer` (melee, 6 coups, percage 60) -> `custoTrajann` (armure 2510), qui porte
`MartialKatah` (`EffectBonus.ForPercentDecrease(20)` gate `IsNormalAttack` -> x0.8) pendant que
l'aura `Nightshroud` d'`astraPrimarisPsy` lui ajoute un `ForSubtraction` de 499. Board `MC1_67`,
seed 777.

CE QUE CE CRAN AJOUTE AUX GARDES EXISTANTES. `test_446_r2_inter_face_rounding_offline.py` verrouille
l'etage MULTIPLICATEUR sur une modification de STAT (tuile Thorns, x1.5, `from_stat_mod`) ; ici la
face defenseur est un **EFFET** (donc la `%-list`, pas `Multiplier@0x30`) **et** porte en plus une
soustraction PLATE -- une combinaison qu'aucune autre garde n'exerce. C'est le regime qui a fait
rougir `test_nightshroud_combat_live.py` du 2026-08-02 au 2026-08-03.

Les huit valeurs attendues sont les BORNES NATIVES, obtenues par INVERSION du tirage a etat PRNG
connu (`probe_462d_nightshroud_stage_diff.py --sweep 906,907,911,1000`), pas par recollement d'un
scalaire. L'inversion est necessaire ici : l'ecart port/natif n'etait PAS constant (le coup est un
modulo, donc une borne basse decalee de 1 diffracte les six coups), donc la soustraction
`live - off` n'aurait rien mesure.

⚠ Ce cran est offline PAR CONSTRUCTION : les huit cellules se reproduisent hors runner, la chaine
COMBAT etant une fonction pure de (base, percage, armure, faces). Il ne remplace pas le test live,
il le rend REJOUABLE en 5 s.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PY = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

from engine.services import fix64 as fx                                    # noqa: E402
from engine.services.damage_modifiers import DamageModifiers, apply_all_modifiers   # noqa: E402
from engine.services.damage_prediction import (                            # noqa: E402
    get_base_damage_fix64, apply_pierce_and_modifiers)
from engine.services.static_battle_rules import get_damage_with_piercing   # noqa: E402

PIERCE = 60            # arme melee de `necroDestroyer`
ARMOR = 2510           # `custoTrajann` -- branche PERCAGE gagnante sur les deux bornes
FLAT = 499             # Nightshroud_DmgReduction (ForSubtraction, defenseur)
PCT = 0.8              # MartialKatah (ForPercentDecrease 20, defenseur, gate IsNormalAttack)

# base (stat DAMAGE de l'attaquant) -> bornes NATIVES du tirage, INVERSEES a etat PRNG connu.
# 906 et 1000 separent les modeles d'arrondi sur les DEUX bornes ; 907 sur la borne haute seule ;
# 911 est le TEMOIN non discriminant -- sans lui on ne saurait pas que l'accord vient parfois du
# REGIME et non du modele.
NATIVE = {906: (108, 282), 907: (109, 283), 911: (110, 285), 1000: (144, 336)}
# Ce que rendait le port ENTRE `0ad4b9e8` (#446-r2) et son correctif : un `Round` INTERMEDIAIRE de
# la face attaquant, a multiplicateur pourtant NEUTRE, materialisait la sortie fractionnaire du
# percage avant que le x0.8 defenseur ne s'applique.
REGRESSE = {906: (109, 282), 907: (109, 282), 911: (110, 285), 1000: (145, 337)}


def _faces():
    """Les DEUX `DamageModifiers` bruts du coup : attaquant NEUTRE, defenseur portant le `x0.8`
    (`MartialKatah`) et la soustraction plate 499 (`Nightshroud`)."""
    att = DamageModifiers()
    deff = DamageModifiers()
    deff.pct_list.append((PCT, None))
    deff.flat_reductions.append(FLAT)
    return att, deff


def _cell(base: int) -> tuple:
    """La chaine COMBAT exacte des quatre vecteurs (`damage_ops/normal.py` et ses trois jumeaux).

    ⚠ Le pont entre les deux faces est APPELE, pas reproduit :
    `AttackDamageOperation._apply_defender_flat_reductions` est le foyer qui fusionne la reduction
    PLATE dans l'additif ATTAQUANT (#120) **et**, depuis #462-r4a, DEPLACE la `%-list` defenseur
    dans `mods.pct_list_defender` pour que les deux faces composent AVANT le moindre `Round`. Le
    simuler a la main ferait de ce cran une garde de FICTION : la premiere version de ce fichier
    recopiait le merge de #120 seul et rendait (109, 282) la ou le moteur rend (108, 282)."""
    from engine.runner.operations.damage import AttackDamageOperation
    att, deff = _faces()
    AttackDamageOperation._apply_defender_flat_reductions(att, deff)
    mm = get_base_damage_fix64(base, spread_pct=20)
    return tuple(apply_all_modifiers(
        apply_pierce_and_modifiers(v, PIERCE, ARMOR, att, attacker_additive_pre=True),
        deff, round_materialize=True) for v in (mm.min, mm.max))


@pytest.mark.parametrize("base", sorted(NATIVE))
def test_regime_discriminant(base):
    """Le regime ne verrouille quelque chose QUE si la valeur post-percage est FRACTIONNAIRE :
    sinon arrondir avant ou apres le x0.8 donne la meme chose. On la MESURE."""
    mm = get_base_damage_fix64(base, spread_pct=20)
    fracs = []
    for v in (mm.min, mm.max):
        raw = get_damage_with_piercing(round(v - FLAT), PIERCE, ARMOR).raw
        fracs.append(raw - (fx.to_int(raw) << 32))
    assert any(f != 0 for f in fracs), (
        f"base {base} : percage ENTIER sur les deux bornes ({fracs}) -- regime NON discriminant, "
        "cette ligne ne verrouille rien")


@pytest.mark.parametrize("base", sorted(NATIVE))
def test_cellules_egalent_le_natif(base):
    """Le COEUR : les bornes du coup valent le natif a l'unite."""
    got = _cell(base)
    assert got == NATIVE[base], (
        f"base {base} : cellules du coup {got} != natif {NATIVE[base]}")


@pytest.mark.parametrize("base", sorted(NATIVE))
def test_la_regression_de_446r2_ne_revient_pas(base):
    """Le cran NOMME sa regression : un `Round` de la face ATTAQUANT intercale avant le `x0.8`
    DEFENSEUR. Si les cellules valaient CA, c'est ce `Round`-la qui est revenu."""
    if NATIVE[base] == REGRESSE[base]:
        pytest.skip(f"base {base} : TEMOIN non discriminant (les deux modeles coincident)")
    assert _cell(base) != REGRESSE[base], (
        f"base {base} : cellules {REGRESSE[base]} -- l'arrondi INTERMEDIAIRE a multiplicateur "
        "neutre est revenu sur la chaine COMBAT (regression de la forme #462-r4d)")
