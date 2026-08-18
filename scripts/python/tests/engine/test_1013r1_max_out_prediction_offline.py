"""#1013-r1 -- LA BRANCHE `ParagonSpear` NE VAUT RIEN COTE PREDICTION, et ce cliquet garde le
`RIEN`.

## Ce que le decompile dit, et pourquoi << rien >> est un RESULTAT

`IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage(attacker, entities, state)` a deux
branches :

    if (IsOwnerOfEffect(attacker, 0x4a1) || IsTargetOfEffect(attacker, 0x4a1))  return true;
    if (HasTriggeredAbility(attacker, 0x5d6 = 1494 ParagonSpear))  return <entities + 0xf8>;
    return false;

`+0xf8` est le parametre **`wasCrit`** d'`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor`
(LU dans la signature a 32 parametres : `*(undefined1 *)(this + 0xf8) = wasCrit`).

Et `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` NE PASSE PAS son
`AbilityEntities` d'entree : il en construit un NEUF, `memset` a 0 sur 0x128 octets puis `.ctor`
avec `caster = actor = <attaquant>`, `target = <cible>` et TOUS les autres parametres a ZERO. Donc
`wasCrit == false`, donc la branche rend `false` -- **pour tout porteur, sur toute prevision**.

## Ce que ce cliquet garde, et pourquoi ce n'est pas un test vide

Un test qui se contenterait d'affirmer << la prediction ne maxe pas >> serait vert sur un port
qui ne saurait rien maxer du tout. Les trois etages ci-dessous sont donc construits autour d'un
TEMOIN NON VIDE : la branche EFFET (`1185 WeaverOfFate_MaxOutDamage`), elle, DOIT degenerer les
bornes. Si elle cessait de le faire, l'etage 2 rougit et les etages 1 et 3 perdent leur sens --
ils l'assertionnent explicitement.

CONTRE-EPREUVE (jouee) : ajouter au foyer la branche kit, sous la forme la plus naturelle
(`or any(e.name == "ParagonSpear" ...)`), fait ROUGIR l'etage 1 ; ajouter un canal de kit en
PARAMETRE fait rougir l'etage 3.

ASCII only.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.services import damage_prediction as DP        # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
#: Trop LARGE est sain ; trop ETROIT est un faux vert -- le fichier ne se rejouerait pas sous
#: `--since` quand ce qu'il garde a bouge.
DECLENCHEUR = {
    "chemins": (
        # LE FOYER GARDE : `is_attack_max_out_damage` et son cablage dans `predict_attack_raw`.
        "scripts/python/engine/services/damage_prediction.py",
        # Le mirror d'ou vient l'ordinal 1494 assertionne a l'etage 1.
        "scripts/python/engine/entities/triggered_ability_type.py",
        # Le pendant COMBAT : si la branche `wasCrit` y bougeait, la frontiere entre les deux
        # faces bougerait aussi et ce fichier doit se rejouer.
        "scripts/python/engine/runner/operations/damage_hits.py",
        "scripts/python/tests/engine/test_1013r1_max_out_prediction_offline.py",
    ),
    # L'etage 1 ASSERTIONNE l'ordinal `1494`, qui est derive du build via le mirror d'enum.
    "build": True,
    "toujours": False,
    "raison": ("Ces trois chemins sont ceux dont une modification peut faire basculer le verdict : "
               "le FOYER garde (`is_attack_max_out_damage` et son cablage dans "
               "`predict_attack_raw`), le mirror d'ou vient l'ordinal 1494, et le pendant COMBAT "
               "(`damage_hits`) dont la branche `wasCrit` definit la frontiere entre les deux "
               "faces. `build: True` parce que l'etage 1 fige un ordinal LU du build."),
}


class _Effet:
    """Le seul contrat que `is_attack_max_out_damage` lit : `getattr(e, "name", None)`."""

    def __init__(self, name):
        self.name = name


def _bornes(effets):
    """Les bornes de `predict_attack_raw` sur un montage NEUTRE (ni armure, ni bouclier, ni mods),
    ou seul le max-out peut degenerer la cellule."""
    from engine.services.damage_prediction import BlockScenario
    r = DP.predict_attack_raw(BlockScenario(), 1000, spread_pct=20,
                              target_current_health=10 ** 6, attacker_effects=effets)
    d = r.raw_health_damage      # @0x24/@0x28 -- NON cape par la sante restante
    return int(d.min), int(d.max)


# --------------------------------------------------------------------------------------------
# Etage 1 -- AUCUN canal de KIT ne maxe la prevision.
# --------------------------------------------------------------------------------------------

def test_aucun_marqueur_de_kit_ne_maxe_la_prevision():
    """Les formes qu'un correctif naif prendrait, toutes refusees.

    `1494 ParagonSpear` est un `TriggeredAbilityType` : il n'a AUCUNE raison d'apparaitre dans le
    canal des EFFETS. On passe ici les trois ecritures possibles d'un tel marqueur ; toutes
    doivent laisser la prevision NON degeneree."""
    marqueurs = ["ParagonSpear",
                 TriggeredAbilityType.ParagonSpear.name,
                 str(int(TriggeredAbilityType.ParagonSpear))]
    assert int(TriggeredAbilityType.ParagonSpear) == 1494, \
        "le mirror a bouge : re-lire `0x5d6` au decompile avant de toucher a ce test"
    lo0, hi0 = _bornes(None)
    assert lo0 < hi0, ("TEMOIN DEGENERE : la prevision de reference doit avoir une AMPLITUDE, "
                       "sinon les etages ci-dessous ne discriminent rien (%d, %d)" % (lo0, hi0))
    for m in marqueurs:
        assert DP.is_attack_max_out_damage([_Effet(m)]) is False, \
            "le canal EFFET a accepte un marqueur de KIT : %r" % m
        assert _bornes([_Effet(m)]) == (lo0, hi0), \
            "la prevision a bouge sur un marqueur de KIT : %r" % m


# --------------------------------------------------------------------------------------------
# Etage 2 -- LE TEMOIN NON VIDE : la branche EFFET, elle, degenere.
# --------------------------------------------------------------------------------------------

def test_la_branche_effet_degenere_bien_les_bornes():
    """Sans ce bras, l'etage 1 serait vert sur un port incapable de maxer QUOI QUE CE SOIT."""
    assert DP.is_attack_max_out_damage([_Effet("WeaverOfFate_MaxOutDamage")]) is True
    lo0, hi0 = _bornes(None)
    lo1, hi1 = _bornes([_Effet("WeaverOfFate_MaxOutDamage")])
    assert lo1 == hi1 == hi0, ("la branche EFFET doit degenerer la cellule sur le MAX : "
                               "reference (%d, %d), max-out (%d, %d)" % (lo0, hi0, lo1, hi1))


# --------------------------------------------------------------------------------------------
# Etage 3 -- LE CONTRAT DU FOYER : un seul canal, et c'est celui des EFFETS.
# --------------------------------------------------------------------------------------------

def test_le_foyer_prediction_n_expose_qu_un_canal_d_effets():
    """Un correctif qui AJOUTERAIT le kit ne passerait pas par les effets : il ajouterait un
    parametre. C'est cet axe-la que garde cet etage.

    Ce n'est pas une preference de style : le natif de la PREVISION construit son
    `AbilityEntities` a zero, donc il n'a RIEN a lire sur le kit -- lui donner un canal, c'est
    lui donner de quoi maxer ce que le jeu ne maxe pas."""
    params = list(inspect.signature(DP.is_attack_max_out_damage).parameters)
    assert params == ["attacker_effects"], (
        "le foyer PREDICTION du max-out a gagne un canal : %s. La branche "
        "`HasTriggeredAbility(1494 ParagonSpear)` rend `AbilityEntities+0xf8` (`wasCrit`), et "
        "`PredictAttackRaw` construit cet `AbilityEntities` a ZERO -- relire le decompile avant "
        "d'elargir ce contrat (#1013-r1)." % params)
