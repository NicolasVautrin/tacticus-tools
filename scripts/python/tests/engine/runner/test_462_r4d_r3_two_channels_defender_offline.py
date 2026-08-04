"""#462-r4d-r3 -- CRAN OFFLINE : les DEUX CANAUX du MEME cote (defenseur), en COMBAT.

Regime : `necroDestroyer` (melee, 6 coups, percage 60) -> `custoTrajann` (armure 2510) CONDUIT sur
une tuile Swamp de `MC1_67`. La face DEFENSEUR porte alors, SUR LE MEME COUP, les deux canaux que
`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` consomme a des
etages DIFFERENTS :

  * `MartialKatah` (`IdunBattle.Entities.Effects.Loki.MartialKatah_DmgReductionEffect$$
    CreateDamageModifier` = `ForPercentDecrease(20)`, gate `IsNormalAttack`) -- un EFFET, donc la
    LISTE `@0x18`, etape 2 ;
  * `Thorns_DefenseReduction` (pose sur la tuile par `IdunBattleLogic.Entities.Abilities.Tiles.
    ThornsBlockMovementAbility$$CreateBehaviour`, -50 nege par
    `IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications` -> x1.5)
    -- une MODIFICATION DE STAT, donc `Multiplier@0x30`, etape 4.

CE QUE CE CRAN AJOUTE. `test_446_r2_inter_face_rounding_offline.py` exerce UN canal par face ;
`test_462_r4d_nightshroud_cells_offline.py` exerce la LISTE defenseur seule (plus un plat). Aucune
garde n'exercait les DEUX canaux du MEME cote -- et #462-r4a n'avait mesure que « deux FACES »
(attaquant x defenseur), un regime different.

LES VALEURS SONT NATIVES, obtenues par INVERSION du tirage a etat PRNG connu
(`probe_462_r4d_r3_two_channels_defender.py --sweep`, qui n'infere rien), jamais par recollement.

LES TEMOINS COMPTENT AUTANT QUE LES CAS. Sur `884` et `910` les QUATRE compositions envisageables
rendent la MEME chose : l'accord y vient du REGIME, pas du modele. Sans eux on croirait que chaque
ligne verte prouve quelque chose. Ils sont donc gardes comme BORNES (`test_temoins_*`), et le test
de refutation les SKIPPE en le disant.

⚠ CE QUE CE CRAN NE TRANCHE PAS : « `attackModifiers` NULL en combat » contre « present a
multiplicateur neutre » (residu `#462-r4d-r1`). Apres l'etape 2 la valeur est deja ENTIERE
(`ApplyCappedModifiers` arrondit en fin d'appel des que la liste est non vide), donc l'etape 3 est
un no-op qu'elle existe ou non.

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
from engine.services.damage_modifiers import (                             # noqa: E402
    DamageModifiers, apply_all_modifiers)
from engine.services.damage_prediction import (                            # noqa: E402
    apply_pierce_and_modifiers, get_base_damage_fix64)
from engine.services.static_battle_rules import get_damage_with_piercing   # noqa: E402

PIERCE = 60            # arme melee de `necroDestroyer`
ARMOR = 2510           # `custoTrajann` -- branche PERCAGE gagnante sur les deux bornes
PCT_DEF = 0.8          # MartialKatah (EFFET -> liste @0x18)
MULT_DEF = 1.5         # Thorns (MODIFICATION DE STAT -> Multiplier@0x30)
ELEV = 1.5             # bonus d'ELEVATION de l'attaquant (EFFET -> liste @0x18, face ATTAQUANT)

# stat DAMAGE de l'attaquant -> bornes NATIVES du tirage, face attaquant NEUTRE.
NATIVE = {861: (497, 744), 866: (500, 749), 876: (504, 756), 884: (509, 764),
          900: (519, 777), 906: (522, 783), 910: (524, 786)}
# Le cas a TROIS entrees : les deux canaux defenseur PLUS la liste attaquant (l'attaquant tire d'une
# tuile en surplomb). Mesure : `probe_462d_nightshroud_stage_diff.py --thorns --solve`.
NATIVE_AVEC_ELEVATION = {906: (783, 1175)}


def _models(pierced, pct_att: float | None = None) -> dict:
    """Les compositions ENVISAGEABLES des deux canaux, ECRITES (jamais monkeypatchees) :

      `A` -- le port : liste `@0x18` (etapes 1+2, UNE chaine) PUIS `Multiplier@0x30` (etapes 3+4).
      `B` -- les deux canaux FUSIONNES dans la meme liste.
      `C` -- ordre INVERSE : multiplicateur d'abord, liste ensuite.
      `D` -- une seule chaine multiplicative, UN SEUL `Round` final.
      `E` -- la regression #446-r2 : un `Round` intercale entre les faces de la LISTE.
    """
    from engine.services.damage_modifiers import (apply_pct_entries,
                                                  calculate_base_damage_with_modifiers)
    lst = ([(pct_att, None)] if pct_att else []) + [(PCT_DEF, None)]
    out = {}
    x = apply_pct_entries(pierced, lst)
    x = calculate_base_damage_with_modifiers(x, 1.0)
    out["A"] = calculate_base_damage_with_modifiers(x, MULT_DEF)
    out["B"] = apply_pct_entries(pierced, lst + [(MULT_DEF, None)])
    out["C"] = apply_pct_entries(calculate_base_damage_with_modifiers(pierced, MULT_DEF), lst)
    raw = fx.from_number(pierced)
    for m in [m for m, _c in lst] + [MULT_DEF]:
        raw = fx.mul(raw, fx.mult_raw_from_float(m))
    out["D"] = fx.Fix64(fx.round_raw(raw, 1))
    z = pierced
    if pct_att:
        z = calculate_base_damage_with_modifiers(apply_pct_entries(z, [(pct_att, None)]), 1.0)
    z = apply_pct_entries(z, [(PCT_DEF, None)])
    out["E"] = calculate_base_damage_with_modifiers(z, MULT_DEF)
    return {k: fx.to_int(fx.round_raw(fx.from_number(v), 1)) for k, v in out.items()}


def _faces(pct_att: float | None = None):
    """Les DEUX `DamageModifiers` bruts du coup, AVANT le pont entre faces.

    ⚠ MONTAGE MIS A JOUR (#437-r1-r1-r1), et c'est ce cran qui CONFIRME la mise a jour. Le
    `DamageModifiers` que rend le builder DEFENSEUR porte desormais SES DEUX faces separement :
      * `MartialKatah_DmgReductionEffect` derive de `DamageModifierAbilityEffect` et n'implemente
        que `CreateDamageModifier` -> sa contribution sort par le forwarder
        `CreateEffectDamageBonusForAttack`, donc dans l'accumulateur **ATTAQUANT** (`pct_list`),
        bien que l'effet vive sur la CIBLE ;
      * le stat-mod `Thorns` est folde par `CalculateDefenderModifiersForPrediction` lui-meme ->
        `defenseModifiers.Multiplier@0x30` (`multiplicative_defender`).
    C'est la ligne `NATIVE_AVEC_ELEVATION` qui TRANCHE : avec `MartialKatah` range cote defenseur,
    la chaine rend 1173 sur la borne haute ; le natif vaut **1175**, qui exige `x1.5` (elevation)
    et `x0.8` (MartialKatah) dans le MEME `Multiplier@0x30` -- exactement ce que dit le decompile.
    C'est un TROISIEME canal de confirmation de l'attribution de face, independant du capteur et du
    decompile : l'inversion PRNG d'un tir natif reel."""
    att = DamageModifiers()
    if pct_att:
        att.pct_list.append((pct_att, None))       # ELEVATION : feuille du builder ATTAQUANT
    deff = DamageModifiers()
    deff.pct_list.append((PCT_DEF, None))          # MartialKatah -> face ATTAQUANT (slot natif)
    deff.multiplicative_defender *= MULT_DEF       # Thorns (stat-mod) -> face DEFENSEUR
    return att, deff


def _cell(base: int, pct_att: float | None = None) -> tuple:
    """La chaine COMBAT exacte des quatre vecteurs (`damage_ops/normal.py` et ses jumeaux).

    ⚠ Le pont entre les deux faces est APPELE, pas reproduit :
    `AttackDamageOperation._apply_defender_flat_reductions` est le foyer qui DEPLACE la `%-list`
    defenseur dans `mods.pct_list_defender` ET son `Multiplier` dans `mods.multiplicative_defender`
    (#462-r4a), en VIDANT la source pour que l'appel aval ne double pas. Le simuler a la main ferait
    de ce cran une garde de FICTION -- la premiere version de son voisin #462-r4d recopiait le merge
    #120 seul et rendait 109 la ou le moteur rend 108."""
    from engine.runner.operations.damage import AttackDamageOperation
    att, deff = _faces(pct_att)
    AttackDamageOperation._apply_defender_flat_reductions(att, deff)
    mm = get_base_damage_fix64(base, spread_pct=20)
    return tuple(apply_all_modifiers(
        apply_pierce_and_modifiers(v, PIERCE, ARMOR, att, attacker_additive_pre=True),
        deff, round_materialize=True) for v in (mm.min, mm.max))


def test_le_regime_porte_bien_DEUX_canaux():
    """Sans cette attestation, une regression qui viderait un canal rendrait ce fichier VERT pour
    de mauvaises raisons : c'est la co-presence des deux entrees qui fait l'objet du cran."""
    _att, deff = _faces()
    assert deff.pct_list, "canal LISTE @0x18 vide -- le regime n'est plus DEUX canaux"
    assert deff.multiplicative_defender != 1.0, (
        "canal Multiplier@0x30 neutre -- le regime n'est plus DEUX canaux")


def test_le_pont_deplace_les_deux_canaux_et_vide_la_source():
    """`_apply_defender_flat_reductions` doit DEPLACER (pas copier) : une source non videe ferait
    appliquer la face defenseur DEUX fois par l'`apply_all_modifiers` aval.

    ⚠ Depuis #437-r1-r1-r1 le pont PRESERVE la face au lieu de la decider : `pct_list` (face
    ATTAQUANT du builder defenseur -- MartialKatah) va dans `att.pct_list`, et le
    `multiplicative_defender` (le stat-mod Thorns) dans `att.multiplicative_defender`."""
    from engine.runner.operations.damage import AttackDamageOperation
    att, deff = _faces()
    AttackDamageOperation._apply_defender_flat_reductions(att, deff)
    assert att.pct_list == [(PCT_DEF, None)], (
        f"MartialKatah (face NATIVE attaquante) n'a pas atterri dans pct_list ({att.pct_list})")
    assert att.pct_list_defender == [], (
        f"une entree a atterri cote defenseur alors qu'aucune n'y a sa face ({att.pct_list_defender})")
    assert att.multiplicative_defender == MULT_DEF, (
        f"le Multiplier defenseur n'a pas atterri dans multiplicative_defender "
        f"({att.multiplicative_defender})")
    assert deff.pct_list == [] and deff.multiplicative_defender == 1.0, (
        "la SOURCE n'a pas ete videe -- la face defenseur serait appliquee deux fois")


@pytest.mark.parametrize("base", sorted(NATIVE))
def test_percage_fractionnaire(base):
    """Le regime ne verrouille quelque chose QUE si la valeur post-percage est FRACTIONNAIRE :
    sinon l'ordre des etages ne change rien. On la MESURE, on ne la suppose pas."""
    mm = get_base_damage_fix64(base, spread_pct=20)
    fracs = []
    for v in (mm.min, mm.max):
        raw = get_damage_with_piercing(round(v), PIERCE, ARMOR).raw
        fracs.append(raw - (fx.to_int(raw) << 32))
    assert any(f != 0 for f in fracs), (
        f"base {base} : percage ENTIER sur les deux bornes ({fracs}) -- cette ligne ne verrouille rien")


@pytest.mark.parametrize("base", sorted(NATIVE))
def test_cellules_egalent_le_natif(base):
    """Le COEUR : les bornes du coup valent le natif a l'unite, face attaquant NEUTRE."""
    got = _cell(base)
    assert got == NATIVE[base], f"base {base} : cellules {got} != natif {NATIVE[base]}"


@pytest.mark.parametrize("base", sorted(NATIVE_AVEC_ELEVATION))
def test_cellules_egalent_le_natif_avec_face_attaquant(base):
    """TROIS entrees sur le meme coup : liste ATTAQUANT (elevation x1.5) + les deux canaux
    DEFENSEUR. Ce point est le seul du corpus ou les cinq compositions se separent sur la borne
    HAUTE (natif 1175 ; 1174 pour trois d'entre elles, 1173 pour la regression #446-r2)."""
    got = _cell(base, pct_att=ELEV)
    assert got == NATIVE_AVEC_ELEVATION[base], (
        f"base {base} (elevation x{ELEV}) : cellules {got} != natif {NATIVE_AVEC_ELEVATION[base]}")


def _native_of(base, pct_att=None):
    mm = get_base_damage_fix64(base, spread_pct=20)
    per = []
    for v in (mm.min, mm.max):
        per.append(_models(get_damage_with_piercing(round(v), PIERCE, ARMOR), pct_att))
    return {k: (per[0][k], per[1][k]) for k in per[0]}


@pytest.mark.parametrize("base", sorted(NATIVE))
def test_les_modeles_concurrents_sont_refutes(base):
    """Le cran NOMME ce qu'il refute. `B` = les deux canaux refusionnes (la regression #462-r4a),
    `C` = l'ordre des etages inverse, `D` = un seul `Round` final, `E` = un `Round` intercale entre
    les faces de la LISTE (la regression #446-r2)."""
    pred = _native_of(base)
    assert pred["A"] == NATIVE[base], (
        f"base {base} : le modele A ne reproduit plus le natif ({pred['A']} != {NATIVE[base]})")
    others = {k: v for k, v in pred.items() if k != "A"}
    if all(v == NATIVE[base] for v in others.values()):
        pytest.skip(f"base {base} : TEMOIN -- les cinq compositions coincident, l'accord vient du "
                    f"REGIME et non du modele (c'est une BORNE, pas une confirmation)")
    for k, v in others.items():
        if v == NATIVE[base]:
            continue
        assert _cell(base) != v, (
            f"base {base} : les cellules valent celles du modele {k} ({v}) -- la composition des "
            f"deux canaux du MEME cote a change")


@pytest.mark.parametrize("base", sorted(NATIVE_AVEC_ELEVATION))
def test_le_cas_a_trois_entrees_separe_les_cinq_modeles(base):
    """Contre-epreuve du point le plus riche : il DOIT separer, sinon il ne verrouille rien de plus
    que les autres lignes."""
    pred = _native_of(base, pct_att=ELEV)
    nat = NATIVE_AVEC_ELEVATION[base]
    assert pred["A"] == nat, f"base {base} : modele A {pred['A']} != natif {nat}"
    dissidents = [k for k, v in pred.items() if k != "A" and v != nat]
    assert len(dissidents) == 4, (
        f"base {base} : seulement {dissidents} se separent du natif -- le cas a TROIS entrees a "
        f"cesse d'etre discriminant ({pred})")


@pytest.mark.parametrize("base", [884, 910])
def test_temoins_non_discriminants(base):
    """Les temoins sont gardes EXPLICITEMENT : si l'un d'eux devenait discriminant, la lecture des
    autres lignes changerait (un vert cesserait d'etre « gratuit »), et on veut le savoir."""
    pred = _native_of(base)
    assert len(set(pred.values())) == 1, (
        f"base {base} n'est PLUS un temoin : les modeles se separent ({pred}) -- reclasser cette "
        f"ligne parmi les cas discriminants")
