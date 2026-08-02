"""#446-r2 -- GARDE OFFLINE : l'ARRONDI INTER-FACES de
`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`.

Le natif consomme SEPAREMENT les modifiers de l'ATTAQUANT et ceux du DEFENSEUR, et intercale entre
les deux faces un `Fix64.Round(., AwayFromZero)` INCONDITIONNEL
(`IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`, slot 0x10, appele
une fois par face -- donc MEME a multiplicateur neutre). Le port fusionnait les deux faces dans une
seule `%-list`, donc un seul arrondi.

CE QUE CETTE GARDE VERROUILLE, avec les valeurs EXACTES du cas mesure (`MC1_67`/`41504`,
`templAggressor` -> `astraBullgryn` sur tuile Thorns) :

  * face DEFENSEUR seule (`x1.5` = modification de stat DEFENSE -50 negee) sur un percage
    fractionnaire `1445 x fix(0.20) = 288.99999993` -> `Round(Round(288.99999993) x 1.5)`
    = `Round(433.5)` = **434** (le port fusionne rendait 433) ;
  * face ATTAQUANT seule (`x1.5` = bonus d'ELEVATION) sur le MEME percage ->
    `Round(288.99999993 x 1.5)` = `Round(433.49999990)` = **433**.

Les DEUX cotes comptent : une regression qui remettrait les faces dans une seule liste casse le
premier, une qui arrondirait deux fois la face attaquant casse le second. ASCII only.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PY = os.path.dirname(os.path.dirname(_HERE))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

from engine.services import fix64 as fx                                    # noqa: E402
from engine.services.damage_modifiers import (                             # noqa: E402
    DamageModifiers, calculate_base_damage_with_modifiers)
from engine.services.damage_prediction import apply_pierce_and_modifiers   # noqa: E402
from engine.services.static_battle_rules import get_damage_with_piercing   # noqa: E402

BASE_MIN = 1445        # borne MIN de `GetBaseDamageFix64(1806)` (spread 20 -> 361)
BASE_MAX = 2167        # borne MAX
PIERCE = 20            # `Bolter` de `templAggressor`
ARMOR = 3513           # `astraBullgryn` -- branche PERCAGE gagnante sur les deux bornes


def _mods(att=(), deff=()):
    m = DamageModifiers()
    m.pct_list.extend((v, None) for v in att)
    m.pct_list_defender.extend((v, None) for v in deff)
    return m


def test_percage_est_juste_sous_l_entier():
    """Le regime n'est discriminant QUE parce que le Fix64 du percage tombe SOUS 289 : sans ca,
    arrondir avant ou apres la face defenseur donnerait le meme resultat et la garde ne verrouille
    plus rien. On mesure la fraction, on ne la suppose pas."""
    v = get_damage_with_piercing(BASE_MIN, PIERCE, ARMOR)
    assert fx.to_int(v.raw) == 288, f"partie entiere attendue 288, obtenue {fx.to_int(v.raw)}"
    assert v.raw < fx.from_int(289), "le percage doit tomber SOUS 289 (Fix64 Div(20,100) arrondi)"
    assert fx.from_int(289) - v.raw < (1 << 20), "et a moins d'un cheveu -- sinon autre regime"


def test_face_defenseur_seule_arrondi_intermediaire():
    """`T` : AUCUN modifier attaquant (le caster tire d'en BAS -> pas d'elevation), `x1.5` DEFENSEUR
    (tuile Thorns). L'arrondi de la face ATTAQUANT (multiplicateur NEUTRE) materialise 289 AVANT que
    le `x1.5` defenseur ne s'applique."""
    m = _mods(att=(), deff=(1.5,))
    lo = apply_pierce_and_modifiers(BASE_MIN, PIERCE, ARMOR, m, attacker_additive_pre=True)
    hi = apply_pierce_and_modifiers(BASE_MAX, PIERCE, ARMOR, m, attacker_additive_pre=True)
    assert fx.to_int(fx.from_number(lo)) == 434, f"MIN attendu 434 (natif), obtenu {float(lo)}"
    assert fx.to_int(fx.from_number(hi)) == 650, f"MAX attendu 650 (natif), obtenu {float(hi)}"


def test_face_attaquant_seule_pas_d_arrondi_intermediaire():
    """`A` : `x1.5` ATTAQUANT (elevation), rien cote defenseur. Le MEME percage donne 433 -- c'est
    l'ASYMETRIE mesuree live, et c'est elle qui interdit de « corriger » en arrondissant partout."""
    m = _mods(att=(1.5,), deff=())
    lo = apply_pierce_and_modifiers(BASE_MIN, PIERCE, ARMOR, m, attacker_additive_pre=True)
    hi = apply_pierce_and_modifiers(BASE_MAX, PIERCE, ARMOR, m, attacker_additive_pre=True)
    assert fx.to_int(fx.from_number(lo)) == 433, f"MIN attendu 433 (natif), obtenu {float(lo)}"
    assert fx.to_int(fx.from_number(hi)) == 650, f"MAX attendu 650 (natif), obtenu {float(hi)}"


def test_les_deux_faces_ne_sont_pas_commutables():
    """La preuve que la SEPARATION des faces est ce qui compte : le MEME produit `1.5`, place d'un
    cote ou de l'autre, rend 434 ou 433. Une regression qui refusionnerait les listes rendrait la
    MEME valeur des deux cotes."""
    d = _mods(att=(), deff=(1.5,))
    a = _mods(att=(1.5,), deff=())
    lo_d = apply_pierce_and_modifiers(BASE_MIN, PIERCE, ARMOR, d, attacker_additive_pre=True)
    lo_a = apply_pierce_and_modifiers(BASE_MIN, PIERCE, ARMOR, a, attacker_additive_pre=True)
    assert fx.to_int(fx.from_number(lo_d)) != fx.to_int(fx.from_number(lo_a)), (
        "les deux faces rendent la MEME borne : les listes sont refusionnees (regression #446-r2)")


def test_calculate_base_damage_with_modifiers_mirror():
    """Mirror LU de `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers` :
    `<= Zero -> Zero`, `0 < x < One -> One`, sinon `Round(x, AwayFromZero)`."""
    assert float(calculate_base_damage_with_modifiers(0)) == 0.0
    assert float(calculate_base_damage_with_modifiers(-5)) == 0.0
    assert float(calculate_base_damage_with_modifiers(10, 0.0)) == 0.0
    # 0 < x < 1 -> One (plancher natif, PAS un floor a 0)
    petit = fx.Fix64(fx.from_int(1) // 2)          # 0.5
    assert float(calculate_base_damage_with_modifiers(petit)) == 1.0
    # AwayFromZero sur la frontiere .5
    demi = fx.Fix64(fx.from_int(433) + (1 << 31))  # 433.5
    assert float(calculate_base_damage_with_modifiers(demi)) == 434.0
    # multiplicateur NEUTRE : ce n'est PAS l'identite, c'est un arrondi
    presque = fx.Fix64(fx.from_int(289) - 1)
    assert float(calculate_base_damage_with_modifiers(presque)) == 289.0
