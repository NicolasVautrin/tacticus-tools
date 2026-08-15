"""#1008-r2 -- la penetration d'armure portee par un effet du DEFENSEUR (`Helspear_IgnoreArmor`).

## Ce que ce fichier garde

Le residu affirmait que le lecteur natif d'`IgnoreArmor` pour un effet DEFENSEUR << restait a
localiser >>. Il est localise, et il n'etait pas la ou la fiche le cherchait : ce n'est pas un
quatrieme slot d'interface, c'est un appel virtuel fait DEPUIS le slot `0x1a`.
`IdunBattle.Entities.Effects.BaseEffect$$DamageMalusForDefense` evalue `this.IgnoreArmor()`
(vtable `+0x718`) et range le resultat dans `DamageBonus+0x38`, que
`IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` accumule
dans `DamageModifiers+0x28`.

Deux proprietes sont gardees ici, et la seconde est celle qui casse en premier si on << simplifie >>
le port :

  1. la magnitude ARRIVE (elle etait exposee et non branchee) ;
  2. elle est SOUS LA GATE du malus -- le natif evalue `IgnoreArmor()` a l'interieur du bloc garde
     par le trigger de l'`EffectBonus`, jamais a cote.

ASCII only (console cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.entities.effects import build_defender_modifiers_from_effects   # noqa: E402
from engine.entities.effects.base import BaseEffect                         # noqa: E402
from engine.entities.effects.loki.helspear import HelspearIgnoreArmorEffect  # noqa: E402
from engine.entities.effects.loki.hits import (                             # noqa: E402
    KanOpenerEffect, PowerTripIgnoreArmorEffect)

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # Le branchement lui-meme (la boucle defenseur) et le canal qu'il lit.
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effects/base.py",
        # Le porteur : gate + magnitude.
        "scripts/python/engine/entities/effects/loki/helspear.py",
        # Les deux porteurs de la face ATTAQUANT, dont ce test verifie qu'ils ne fuient PAS
        # dans la boucle defenseur.
        "scripts/python/engine/entities/effects/loki/hits.py",
        # L'accumulateur et le consommateur de l'axe armure.
        "scripts/python/engine/services/damage_modifiers.py",
        "scripts/python/engine/services/effect_bonus.py",
        "scripts/python/engine/services/damage_prediction.py",
    ),
    # La magnitude est LUE dans le gameconfig (`Helspear.armorIgnored`).
    "build": True,
    "toujours": False,
    "raison": ("la boucle defenseur, le porteur Helspear (gate + magnitude), les deux porteurs de "
               "la face attaquant qui ne doivent pas y fuir, et l'axe armure de bout en bout"),
}

NIVEAU = 10                      # palier TERTIAIRE (relique) -- jamais le palier passif (#1007)


def _helspear():
    e = HelspearIgnoreArmorEffect(name="Helspear_IgnoreArmor", effect_type=1583,
                                  target=7, level=1)
    e.ability_level = NIVEAU
    return e


def test_la_magnitude_atteint_l_axe_armure():
    """L'ECART DE #1008-r2, chiffre. Le port EXPOSAIT `ignore_armor()` sans le brancher : la boucle
    defenseur rendait `armor_penetration = 0` alors que le natif y verse `DamageBonus+0x38`."""
    e = _helspear()
    attendu = e.ignore_armor()
    assert attendu, "temoin DEGENERE : la magnitude lue au gameconfig est nulle ou absente"
    mods = build_defender_modifiers_from_effects([e], is_melee=True, attacker_ctx={"id": 42})
    assert mods.armor_penetration == attendu, (mods.armor_penetration, attendu)


def test_la_penetration_est_sous_la_gate_du_malus():
    """LA PROPRIETE QUI CASSE EN PREMIER si on sort la lecture du bloc garde.

    `Helspear_IgnoreArmorEffect$$CreateEffectDamageMalusForDefense` porte
    `get_OwnerIsTarget & IsUnit(Caster)`. Sans attaquant qualifie, le natif rend un
    `Nullable<DamageBonus>` VIDE et n'evalue JAMAIS `IgnoreArmor()`. Un port qui lirait la
    penetration a cote du bloc l'accorderait face a une source non-unite."""
    e = _helspear()
    ouvert = build_defender_modifiers_from_effects([e], is_melee=True, attacker_ctx={"id": 42})
    ferme = build_defender_modifiers_from_effects([e], is_melee=True, attacker_ctx=None)
    assert ferme.armor_penetration == 0, ferme.armor_penetration
    # NON-DEGENERESCENCE : les deux bras doivent DIFFERER, sinon le test passerait aussi sur un
    # port qui ne branche rien du tout.
    assert ouvert.armor_penetration != ferme.armor_penetration


def test_les_penetrations_de_la_face_attaquant_ne_fuient_pas_dans_la_boucle_defenseur():
    """LE RISQUE DE DOUBLE COMPTABILISATION, ecarte PAR CONSTRUCTION -- et verifie.

    `PowerTripIgnoreArmorEffect` et `KanOpenerEffect` surchargent `get_armor_penetration` pour la
    face ATTAQUANT (`CreateEffectDamageBonusForAttack` cote natif). Elles ne surchargent PAS
    `create_effect_damage_malus_for_defense`, donc le malus est `None` et la nouvelle lecture --
    qui vit DANS ce bloc -- ne les atteint jamais. C'est la seconde raison d'avoir mis la lecture
    la, et non a cote."""
    for cls, et in ((PowerTripIgnoreArmorEffect, 1119), (KanOpenerEffect, 1102)):
        e = cls(name=cls.__name__, effect_type=et, target=7, level=1)
        e.ability_level = NIVEAU
        mods = build_defender_modifiers_from_effects([e], is_melee=True, attacker_ctx={"id": 42})
        assert mods.armor_penetration == 0, (cls.__name__, mods.armor_penetration)
    # TEMOIN NON DEGENERE : au moins une des deux DOIT exposer une penetration non nulle par son
    # canal propre, sinon le zero ci-dessus ne prouverait rien.
    pens = [cls(name=cls.__name__, effect_type=et, target=7, level=1)
            for cls, et in ((PowerTripIgnoreArmorEffect, 1119), (KanOpenerEffect, 1102))]
    for p in pens:
        p.ability_level = NIVEAU
    assert any(p.get_armor_penetration() for p in pens), \
        "temoin DEGENERE : aucune des deux classes attaquant n'expose de penetration"


def test_un_effet_defenseur_ordinaire_n_ajoute_aucune_penetration():
    """NO-OP EXACT HORS REGIME. Un effet qui rend un malus mais aucune `IgnoreArmor` ne doit rien
    changer sur l'axe armure -- c'est le cas de TOUS les effets defenseur preexistants."""
    class _MalusSansPenetration(BaseEffect):
        def create_effect_damage_malus_for_defense(self, is_melee=None, damage_profile=None,
                                                   attacker_ctx=None):
            from engine.services.effect_bonus import for_addition
            return for_addition(False, 0)

    e = _MalusSansPenetration(name="ordinaire", effect_type=1, target=7)
    assert e.get_armor_penetration() is None
    mods = build_defender_modifiers_from_effects([e], is_melee=True, attacker_ctx={"id": 42})
    assert mods.armor_penetration == 0
