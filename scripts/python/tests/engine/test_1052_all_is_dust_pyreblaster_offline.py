"""#1052 -- CLIQUETS OFFLINE des deux passifs portes : `AllIsDust` (1189) et `Pyreblaster` (1098).

Ce que ces tests GARDENT, et qui n'est garde nulle part ailleurs :

  1. **le SEUIL et le SENS du gate d'`AllIsDust`** -- `NOT AmountIsGreater(total, ConfigConst(0x49))`
     est STRICT et NIE, donc `total <= 35` : le cas `total == 35` DOIT rendre un bonus. Un port
     ecrit avec `<` aurait passe tous les tests de la vie courante et rate exactement ce cas -- il
     est CONFRONTE LIVE (`necroSpyder`, profil `Particle` 35) ;
  2. **le MONTANT** `-(total - 1)`, qui ramene le percage effectif a **1** et pas a 0 ;
  3. **le TRI-ETAT** : un terme non mesure FERME le gate (jamais un 0 devine) ;
  4. **la GEOMETRIE** de `TileBehindFilled` : un pas AU-DELA de la cible, et VIDE hors ligne droite
     (la branche `RoundDirection`, residu `#1052-r1`) ;
  5. **l'INSCRIPTION** des deux passifs a leur registre, et les ORDINAUX ECRITS AU SITE (`probe_313`
     compare le mirror au build ; il redevient vert des qu'on regenere le mirror, alors que la
     valeur ecrite au site, elle, aurait change).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PY = Path(__file__).resolve().parents[2]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))

from engine.battle_query import get_tiles_behind_filled, is_on_straight_line   # noqa: E402
from engine.entities.effect_type import EffectType                            # noqa: E402
from engine.entities.effects.factory import (ABILITY_INIT_OWNER_EFFECTS,      # noqa: E402
                                             EFFECT_CLASSES)
from engine.entities.effects.loki.all_is_dust import (AllIsDustEffect,        # noqa: E402
                                                      pierce_ratio_threshold)
from engine.entities.triggered_ability_type import TriggeredAbilityType       # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS  # noqa: E402
from engine.runner.operations.triggers.loki.pyreblaster import (              # noqa: E402
    PyreblasterAbility, PYREBLASTER_KEY)

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/all_is_dust.py",
        "scripts/python/engine/runner/operations/triggers/loki/pyreblaster.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/battle_query.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/entities/effects/magnitude.py",
    ),
    # `build: True` -- le seuil (`units.abilities.AllIsDust.constants.pierceRatio`) et les percages
    # de profil (`damageProfiles[].PiercingRatio`) sont LUS au gameconfig, pas ecrits ici.
    "build": True,
    "toujours": False,
    "raison": "Les deux ports, les deux mirrors d'enum dont ce fichier FIGE les ordinaux ecrits au "
              "site, la geometrie `TileBehindFilled`, les deux registres, et le gameconfig d'ou "
              "viennent le seuil et les percages de profil.",
}

#: ORDINAUX MESURES A LA CONVERSION (build `rnca9r7q6c`). Figes ICI parce que `probe_313` compare
#: le MIRROR au BUILD : il redevient vert des qu'on regenere le mirror apres un renumerotage,
#: pendant que la valeur ecrite au site, elle, a change en silence (cf. CLAUDE.md).
ALL_IS_DUST_TRIGGERED = 1158        # `TriggeredAbilityType.AllIsDust`   = 0x486
ALL_IS_DUST_EFFECT = 1189           # `EffectType.AllIsDust`             = 0x4a5
PYREBLASTER_TRIGGERED = 1098        # `TriggeredAbilityType.Pyreblaster` = 0x44a
FIRE_EFFECT = 5                     # `EffectType.Fire`
ATTACK_IN_ATOMIC_GROUP = 0x4a       # `EventTriggerType.AttackInAtomicGroup` = 74


def _ctx(extra=0, dir_=0, add=0):
    return {"extra_pierce": extra, "extra_pierce_dir": dir_, "effect_pierce_addition": add}


def _eff():
    return AllIsDustEffect({"name": "AllIsDust", "effectType": ALL_IS_DUST_EFFECT})


# --------------------------------------------------------------------- 1. ordinaux ECRITS AU SITE

def test_ordinaux_figes_a_la_conversion():
    assert int(TriggeredAbilityType.AllIsDust) == ALL_IS_DUST_TRIGGERED
    assert int(TriggeredAbilityType.Pyreblaster) == PYREBLASTER_TRIGGERED
    assert int(EffectType.AllIsDust) == ALL_IS_DUST_EFFECT
    assert int(EffectType.Fire) == FIRE_EFFECT


# ------------------------------------------------------------------------ 2. AllIsDust -- le gate

def test_seuil_lu_au_gameconfig():
    """`ConfigConst(0x49 = pierceRatio)` -- LU, jamais un litteral au site."""
    assert pierce_ratio_threshold() == 35


@pytest.mark.parametrize("base_profil,attendu", [
    ("Physical", 0),      # percage 1  -> montant `-(1-1)` = 0 : REGIME DEGENERE, no-op EXACT
    ("Bolter", -19),      # percage 20 -> ramene a 1
    ("Flame", -24),       # percage 25 -> ramene a 1
    ("Particle", -34),    # percage 35 -> CAS LIMITE : `NOT AmountIsGreater(35, 35)` est VRAI
])
def test_montant_ramene_le_percage_a_un(base_profil, attendu):
    b = _eff().create_piercing_bonus_for_attack(base_profil, True, _ctx())
    assert b is not None, "le gate devait s'ouvrir pour %s" % base_profil
    assert b.kind == "Piercing"
    assert b.owner_is_caster is False          # trigger `get_OwnerIsTarget`
    assert b.value == attendu


@pytest.mark.parametrize("profil", ["Power", "Eviscerate", "Plasma", "Psychic"])
def test_gate_ferme_au_dessus_du_seuil(profil):
    """Percage de profil > 35 -> AUCUN bonus. Confronte live (`darkaTerminator`, `Power` 40)."""
    assert _eff().create_piercing_bonus_for_attack(profil, True, _ctx()) is None


def test_les_termes_du_caster_entrent_dans_le_total():
    """`GetPierceStatModifier()` + `CasterEffectPierceAddition()` sont DANS le total gate : un
    attaquant a +20 de percage stat sur un profil `Bolter` (20) atteint 40 -> le gate se FERME."""
    e = _eff()
    assert e.create_piercing_bonus_for_attack("Bolter", True, _ctx(extra=20)) is None
    assert e.create_piercing_bonus_for_attack("Bolter", True, _ctx(dir_=20)) is None
    assert e.create_piercing_bonus_for_attack("Bolter", True, _ctx(add=20)) is None
    # ... et un total de 30 reste SOUS le seuil, montant `-(30 - 1)`.
    b = e.create_piercing_bonus_for_attack("Bolter", True, _ctx(extra=5, dir_=3, add=2))
    assert b is not None and b.value == -29


@pytest.mark.parametrize("ctx,is_melee,profil", [
    (None, True, "Bolter"),                                   # aucun terme mesure
    ({"extra_pierce": 0, "extra_pierce_dir": 0}, True, "Bolter"),          # somme d'effets absente
    ({"extra_pierce": 0, "effect_pierce_addition": 0}, True, "Bolter"),    # branche du `If` absente
    (_ctx(), None, "Bolter"),                                 # `IsMeleeAttack` non threade
    (_ctx(), True, None),                                     # profil non threade
])
def test_tri_etat_ferme_le_gate(ctx, is_melee, profil):
    """Un terme NON MESURE ferme le gate -- jamais un 0 devine, qui l'ouvrirait a coup sur."""
    assert _eff().create_piercing_bonus_for_attack(profil, is_melee, ctx) is None


def test_inscrit_aux_deux_registres_dans_le_meme_commit():
    assert EFFECT_CLASSES.get("AllIsDust") is AllIsDustEffect
    assert ABILITY_INIT_OWNER_EFFECTS.get("AllIsDust") == ["AllIsDust"]


# ------------------------------------------------------------- 3. Pyreblaster -- geometrie/registre

def test_tile_behind_est_un_pas_au_dela_de_la_cible():
    """`GetTilesBehindFilled` branche ALIGNEE : `cube(cible) - DirectionTo(cube(origine),
    cube(cible))`. Verifie sur les deux axes de la grille odd-q."""
    assert get_tiles_behind_filled((0, 0), (0, 1)) == [(0, 2)]
    assert get_tiles_behind_filled((0, 0), (0, 2)) == [(0, 3)]
    assert get_tiles_behind_filled((1, 1), (1, 3)) == [(1, 4)]


def test_hors_ligne_droite_rend_vide_et_c_est_le_residu_1052_r1():
    """La branche `MovementUtil$$RoundDirection` (DEUX tuiles) n'est pas portee -> `[]`. Le test
    FIGE cette degradation RESTRICTIVE : si un jour elle est portee, il rougit et on le sait."""
    assert not is_on_straight_line((3, 3), (5, 3))
    assert get_tiles_behind_filled((3, 3), (5, 3)) == []


def test_deux_hexes_adjacents_sont_toujours_alignes():
    """Corollaire MESURE : le residu `#1052-r1` est INATTEIGNABLE a distance 1. Deux voisins
    partagent toujours une composante cube."""
    import hexgeo
    src = (4, 4)
    voisins = [(c, r) for c in range(2, 7) for r in range(2, 7)
               if hexgeo.distance(src, (c, r)) == 1]
    assert len(voisins) == 6, voisins
    assert all(is_on_straight_line(src, v) for v in voisins)


def test_pyreblaster_inscrit_au_registre_des_passifs():
    assert PYREBLASTER_KEY == "Pyreblaster"
    assert ABILITY_TRIGGERS.get(PYREBLASTER_KEY) == [PyreblasterAbility]
    assert PyreblasterAbility.event_id == ATTACK_IN_ATOMIC_GROUP
    assert PyreblasterAbility.TRIGGERED_ABILITY_ID == PYREBLASTER_TRIGGERED


def test_l_arbre_porte_les_deux_volets_et_dans_l_ordre_natif():
    """`op_Addition(attaque, feu)` : l'attaque D'ABORD. Le noeud `AddEffect` est CONSTRUIT en
    premier dans le decompile, mais compose en SECOND -- c'est l'ordre d'EXECUTION qui est
    mirrore."""
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
    from engine.runner.abilities.behaviours.effects import AddEffect
    from engine.runner.operations.triggers.loki.pyreblaster import pyreblaster_tree
    t = pyreblaster_tree()                       # `op_and` -> noeud `Seq(left, right)`
    gauche, droite = t.left, t.right
    assert isinstance(gauche, AttackWithAttackDamage)
    assert isinstance(droite, AddEffect)
    assert droite.effect_type == FIRE_EFFECT
    assert droite.source_from_target is True      # surcharge 4-args : source litterale `0`
    assert droite.duration_rounds is None         # `turns = null`
    assert gauche.profile == "Flame"              # `constants.damageProfile`, LU au gameconfig
    assert gauche.multi is True
    assert gauche.level_slot == "passive"
    assert gauche.is_melee is False
