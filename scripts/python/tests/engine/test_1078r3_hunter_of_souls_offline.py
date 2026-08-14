"""#1078-r3 -- `HunterOfSouls_ExtraDamage` (1495) : le port, et surtout ce qui le SEPARE de son
jumeau structurel `EnmityForTheUnworthy_ExtraDamage` (1400, #948).

Les deux effets ont la MEME forme (`ForAddition(get_OwnerIsCaster, Multiply(ConfigVar(extraDmg),
Count(<voisins>)))`) et c'est precisement ce qui rend la recopie dangereuse : DEUX etages different,
tous deux LUS au decompile et non supposes --

  * `HunterOfSouls` filtre par **TRAIT** (`UnitsWithTrait(..., UnitTrait.Psyker = 0x3ea, 3)`),
    `Enmity` par **FACTION** (`UnitsFromFaction(..., DarkAngels, 3)`) ;
  * `HunterOfSouls` n'a **AUCUN** etage `NonSteppableOrObjectUnits`, `Enmity` en a un.

Un ami Psyker portant `Steppable` ou `Object` est donc **COMPTE** par HunterOfSouls et **ECARTE**
par Enmity. L'etage 3 ci-dessous mesure exactement cette separation : sans elle, le test passerait
aussi bien sur un port qui aurait recopie le filtre de son voisin.

Troisieme ecart : `HunterOfSouls` n'a **aucune** `CreateActiveCondition` (aucun symbole de ce nom
pour la classe), la ou Enmity en porte une. Le port ne pose donc pas `active_condition_ported`.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from engine.entities.effects.factory import EFFECT_CLASSES
from engine.entities.effects.loki.hunter_of_souls import (
    ABILITY_ID, CTX_ADJACENT_PSYKER_FRIENDS, HunterOfSoulsExtraDamageEffect)
from engine.entities.effects.magnitude import ability_var

_RACINE = Path(__file__).resolve().parents[2] / "engine"
_NOM = "HunterOfSouls_ExtraDamage"

#: Ce qui doit changer pour que ce fichier puisse changer de verdict. Volontairement LARGE : le
#: gameconfig y entre parce que l'etage 1 lit `extraDmg` par `ability_var`, et les DEUX vecteurs de
#: prediction parce que l'etage 4 exige que la cle soit posee des DEUX cotes.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/hunter_of_souls.py",
        "scripts/python/engine/entities/effects/loki/enmity_for_the_unworthy.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/playbook/scene.py",
        "scripts/python/engine/playbook/prediction/normal_attack.py",
        "scripts/python/engine/playbook/prediction/abilities.py",
        "scripts/python/engine/services/effect_bonus.py",
        "data/gameconfig.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "port de 1495, sa cle de ctx sur les DEUX faces, et l'ARBRE de son compteur "
              "confronte a celui de son jumeau 1400 (l'etage 3 lit les deux) ; `build` VRAI "
              "parce que l'etage 1 lit `extraDmg` du gameconfig et que `UnitTrait.Psyker` "
              "vient du dump d'enums",
}


def _effet(level=50, mult=100):
    return HunterOfSoulsExtraDamageEffect(_NOM, ability_level=level,
                                          ability_variables_multiplier=mult)


def test_etage0_l_effet_est_au_registre_par_son_NOM():
    """Le registre est cle par NOM, jamais par ordinal -- l'interroger par `1495` rend un faux
    negatif (mesure #1084 : `1400 in EFFECT_CLASSES` est `False` alors que l'effet EST porte)."""
    assert _NOM in EFFECT_CLASSES
    assert EFFECT_CLASSES[_NOM] is HunterOfSoulsExtraDamageEffect
    assert 1495 not in EFFECT_CLASSES        # le piege, fige pour qu'on ne le re-paye pas


def test_etage1_magnitude_est_extraDmg_fois_le_compte():
    """`Multiply(ConfigVar(8 = extraDmg, GetAbilityState(this)), Count(<compteur>))`."""
    e = _effet()
    per = ability_var(ABILITY_ID, "extraDmg", 50, multiplier_pct=100)
    assert per, per                          # le temoin doit etre NON NUL, sinon on ne mesure rien
    for n in (1, 2, 3):
        b = e.create_effect_damage_bonus_for_attack(att_ctx={CTX_ADJACENT_PSYKER_FRIENDS: n})
        assert b is not None, n
        assert b.kind == "Addition", b.kind          # canal `+0x10`, pas un pourcentage
        assert b.value == per * n, (n, b.value, per)


def test_etage2_tri_etat_cle_absente_et_compte_nul():
    """Cle ABSENTE = non mesure -> aucune contribution ; compte 0 -> aucune contribution.

    Les deux rendent `None`, mais pour des raisons differentes : l'absence est une DEGRADATION
    (le substrat n'a pas repondu), le zero est le comportement NATIF (`ForAddition(gate, 0)`)."""
    e = _effet()
    assert e.create_effect_damage_bonus_for_attack(att_ctx=None) is None
    assert e.create_effect_damage_bonus_for_attack(att_ctx={}) is None
    assert e.create_effect_damage_bonus_for_attack(
        att_ctx={CTX_ADJACENT_PSYKER_FRIENDS: None}) is None
    assert e.create_effect_damage_bonus_for_attack(
        att_ctx={CTX_ADJACENT_PSYKER_FRIENDS: 0}) is None


def test_etage2bis_sans_AbilityState_la_magnitude_est_inerte():
    """`ConfigVar` sans `GetAbilityState` ne peut pas resoudre le niveau -> aucune contribution,
    jamais une valeur devinee."""
    e = HunterOfSoulsExtraDamageEffect(_NOM, ability_level=None)
    assert e.create_effect_damage_bonus_for_attack(
        att_ctx={CTX_ADJACENT_PSYKER_FRIENDS: 3}) is None


def test_etage3_le_selecteur_NE_RETIRE_PAS_les_Steppable_ni_les_Object():
    """LA contre-epreuve : c'est ce qui separe ce compteur de celui d'Enmity.

    On lit l'ARBRE, pas le comportement : un `NonSteppableOrObjectUnits` recopie du voisin
    apparaitrait comme un `UnitsWithoutTrait` dans le sous-arbre. Le test assertionne AUSSI que
    l'arbre d'Enmity, lui, EN PORTE -- sinon << aucun `UnitsWithoutTrait` >> pourrait vouloir dire
    << le detecteur ne voit rien >>, et ce serait un vert qui ment."""
    from engine.entities.effects.loki.enmity_for_the_unworthy import (
        adjacent_dark_angels_friends_selector)
    from engine.entities.effects.loki.hunter_of_souls import adjacent_psyker_friends_selector

    def _noms(noeud, vus=None):
        vus = [] if vus is None else vus
        vus.append(type(noeud).__name__)
        for v in vars(noeud).values():
            if hasattr(v, "__dict__") and not isinstance(v, type):
                _noms(v, vus)
        return vus

    hunter = _noms(adjacent_psyker_friends_selector())
    enmity = _noms(adjacent_dark_angels_friends_selector())
    assert "UnitsWithoutTrait" in enmity, enmity      # temoin NON DEGENERE
    assert "UnitsWithoutTrait" not in hunter, hunter  # l'ecart LU au decompile
    assert "UnitsWithTrait" in hunter, hunter
    assert "UnitsFromFaction" not in hunter, hunter   # l'autre ecart : trait, pas faction


def test_etage4_la_cle_est_posee_sur_les_DEUX_faces():
    """Une cle posee d'un seul cote cree un fork silencieux entre COMBAT et DECISION -- c'est
    exactement ce que #1025-r1 a du reparer pour `tgt_rarity`/`team_by_id`.

    Perimetre DERIVE : on cherche la constante par son NOM d'import dans les trois foyers, pas une
    liste ecrite a la main."""
    foyers = ["runner/damage_model.py",
              "playbook/prediction/normal_attack.py",
              "playbook/prediction/abilities.py"]
    manquants = []
    for rel in foyers:
        src = (_RACINE / rel).read_text(encoding="utf-8")
        arbre = ast.parse(src)
        importe = any(isinstance(n, ast.ImportFrom)
                      and any(a.name == "CTX_ADJACENT_PSYKER_FRIENDS" for a in n.names)
                      for n in ast.walk(arbre))
        utilise = "_HUNTER_CTX_PSYKER" in src
        if not (importe and utilise):
            manquants.append((rel, importe, utilise))
    assert not manquants, manquants


def test_etage5_le_compteur_a_UN_foyer_par_face():
    """Deux substrats (l'ECS cote runner, les tables de `Scene` cote decision), UN arbre natif."""
    from engine.playbook.scene import Scene
    from engine.runner import components

    assert hasattr(components, "hunter_of_souls_adjacent_psyker_friends_count")
    assert hasattr(Scene, "hunter_of_souls_adjacent_psyker_friends")
