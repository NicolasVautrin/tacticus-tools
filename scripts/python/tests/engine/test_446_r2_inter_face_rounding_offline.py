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
    """#462-r4a -- LE CANAL DU MONTAGE A CHANGE, PAS LES VALEURS NATIVES ATTENDUES.

    Le `x1.5` de ce cas est une MODIFICATION DE STAT (defense -50 de la tuile Thorns, negee), et
    c'est ce qui le place dans `Multiplier@0x30` (`DamageModifiers$$Add` surcharge 1-ARG), donc
    DERRIERE le `Round` de l'etage MULTIPLICATEUR. Les %-list d'EFFETS, elles, vivent dans la liste
    `@0x18` et se composent SANS arrondi entre les faces -- mesure #462-r4a, 12 bornes de balayage
    d'armure plus le seul cas jamais monte avec les DEUX faces non neutres. Le montage pose donc
    desormais la face DEFENSEUR dans `multiplicative_defender` ; les bornes attendues (434 / 650 /
    433) sont INCHANGEES, ce sont toujours les valeurs natives de #446-r2."""
    m = DamageModifiers()
    m.pct_list.extend((v, None) for v in att)
    for v in deff:
        m.multiplicative_defender *= v
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
    l'ASYMETRIE mesuree live, et c'est elle qui interdit de " corriger " en arrondissant partout."""
    m = _mods(att=(1.5,), deff=())
    lo = apply_pierce_and_modifiers(BASE_MIN, PIERCE, ARMOR, m, attacker_additive_pre=True)
    hi = apply_pierce_and_modifiers(BASE_MAX, PIERCE, ARMOR, m, attacker_additive_pre=True)
    assert fx.to_int(fx.from_number(lo)) == 433, f"MIN attendu 433 (natif), obtenu {float(lo)}"
    assert fx.to_int(fx.from_number(hi)) == 650, f"MAX attendu 650 (natif), obtenu {float(hi)}"


def test_effet_defenseur_reste_dans_la_meme_chaine():
    """#462-r4a -- LE PENDANT du cas ci-dessus, et il est INDISPENSABLE : une face DEFENSEUR issue
    d'un EFFET (et non d'une modification de stat) reste dans la LISTE `@0x18`, donc dans la MEME
    chaine que la face attaquant, SANS `Round` entre les deux.

    Le regime est celui de `Terrifying_ExtraDefense` (`x0.70`) : sur le percage `fix(0.60) x 725`
    du montage #462-r4a, `Round(435.000000068 x 0.70)` = **305** (natif), tandis qu'un arrondi
    intercale rendrait `Round(Round(435.000000068) x 0.70)` = 304. Mesure : 12 bornes sur un
    balayage d'armure (`probe_462_r4a_terrifying_rounding.py --sweep`)."""
    m = DamageModifiers()
    m.pct_list_defender.append((0.7, None))
    lo = apply_pierce_and_modifiers(725, 60, 2208, m, attacker_additive_pre=True)
    assert fx.to_int(fx.from_number(lo)) == 305, (
        f"MIN attendu 305 (natif), obtenu {float(lo)} -- un `Round` s'est glisse entre le percage "
        f"et la face DEFENSEUR, alors que celle-ci vient d'un EFFET (liste @0x18)")


def test_chaine_unique_quand_les_deux_faces_sont_non_neutres():
    """#462-r4a -- LE CAS QUE #446-r2 N'AVAIT PAS PU MONTER : elevation `x1.50` ET
    `Terrifying_ExtraDefense` `x0.70` sur le MEME coup. Mesure live `--two-faces` (unites DEPLACEES
    pour fabriquer le denivele) : natif **761/1141**, soit UN SEUL `Round`.

    ⚠ MONTAGE CORRIGE (#437-r1-r1-r1) -- LES VALEURS NATIVES N'ONT PAS BOUGE, LA FACE SI. Ce cran
    posait `x0.70` dans `pct_list_defender`, ce qui etait l'attribution du PORT et non celle du
    natif. Le capteur `effect-bonus-trace` lit sur CE montage UN SEUL accumulateur qui COMPOSE
    (`1 -> 0.6999999999534339 -> 1.0499999998137355`), les DEUX bonus etiquetes `face=attacker` :
    `Terrifying_ExtraDefense_Effect` derive de `DamageModifierAbilityEffect` et n'implemente que
    `CreateDamageModifier`, donc sa contribution sort par le forwarder
    `CreateEffectDamageBonusForAttack` -- le slot que seul `CalculateAttackerModifiersForPrediction`
    invoque. Les deux bonus vivent donc dans le MEME `Multiplier@0x30`, d'ou UN seul `Round` --
    et non parce qu'un drapeau fusionnait deux faces distinctes."""
    m = DamageModifiers()
    m.pct_list.extend([(1.5, None), (0.7, None)])          # les DEUX en face ATTAQUANTE (mesure)
    lo = apply_pierce_and_modifiers(725, 100, 0, m, attacker_additive_pre=True)
    hi = apply_pierce_and_modifiers(1087, 100, 0, m, attacker_additive_pre=True)
    assert fx.to_int(fx.from_number(lo)) == 761, f"MIN attendu 761 (natif), obtenu {float(lo)}"
    assert fx.to_int(fx.from_number(hi)) == 1141, f"MAX attendu 1141 (natif), obtenu {float(hi)}"

    # CONTRE-EPREUVE : sous l'attribution ABANDONNEE (une face chacun), la separation -- desormais
    # INCONDITIONNELLE -- rend 762/1142. C'est le `+1` que le drapeau `separate_face_lists=False`
    # masquait, et c'est ce qui prouve que ce cran discrimine encore quelque chose.
    m2 = DamageModifiers()
    m2.pct_list.append((1.5, None))
    m2.pct_list_defender.append((0.7, None))
    got = tuple(fx.to_int(fx.from_number(
        apply_pierce_and_modifiers(b, 100, 0, m2, attacker_additive_pre=True)))
        for b in (725, 1087))
    assert got == (762, 1142), (
        "l'attribution ABANDONNEE devait rendre 762/1142 (un `Round` de trop), obtenu %s -- si elle "
        "rend 761/1141, les deux faces sont refusionnees et ce cran ne mesure plus rien" % (got,))


def test_les_deux_canaux_ne_sont_pas_commutables():
    """La preuve que la SEPARATION des CANAUX est ce qui compte : le MEME produit `1.5`, pose comme
    modification de STAT du defenseur (`Multiplier@0x30`, arrondi intercale) ou comme %-list de
    l'attaquant (liste `@0x18`, pas d'arrondi), rend 434 ou 433. Une regression qui remettrait les
    modifications de stat dans la %-list rendrait la MEME valeur des deux cotes."""
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
