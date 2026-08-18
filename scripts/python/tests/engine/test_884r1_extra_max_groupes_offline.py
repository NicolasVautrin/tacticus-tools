"""#884-r1 -- `EXTRA_MAX_DAMAGE` descend AUSSI aux groupes du canal #179, et SEULEMENT par une voie.

## Ce que le decompile dit

`IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64(damage, isMaxOut, extraMaxDamage)`,
LU verbatim sur le build charge :

    min = isMaxOut ? slot9(damage) + extraMax : slot8(damage)
    max = slot9(damage) + extraMax                      # INCONDITIONNEL

(slots 8/9 = `IdunBattle.Core.Services.DamageCalculations$$CalculateMinDamage` / `$$CalculateMaxDamage`).
L'extra-max n'existe donc QUE sur cette voie -- il gonfle le BOUT HAUT, et le bas seulement quand
le max-out l'a deja degenere.

L'AUTRE voie de `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` -- celle que le byte
`AttackPredictionRequest+0x6a` ouvre a `0` -- construit une cellule PLATE
`MinMaxDamageFix64(damage, maxOverride ?? damage)` et ne touche JAMAIS `ExtraMaxDamage`. C'est
elle que le port appelle `predefined`.

D'ou l'invariant garde ici, en DEUX volets qui se contredisent l'un l'autre si on se trompe :

  * forme `amount` (spread +-20 %) -> l'extra-max MORD sur la borne MAX, et sur elle seule ;
  * forme `predefined` (cellule plate) -> l'extra-max est INERTE.

## Le temoin qui rend ces etages non vides

Un test qui ne regarderait que << le max a bouge >> serait vert sur un port qui ajouterait
l'extra-max partout. Chaque etage confronte donc la forme `amount` A la forme `predefined` sur le
MEME montage : l'une doit bouger, l'autre PAS.

CONTRE-EPREUVE (jouee) : retirer `extra_max=extra_max` du `_ghit` fait rougir l'etage 1 ;
l'appliquer aussi au `predefined` (dans `predict_attack_raw`) fait rougir l'etage 2.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.services import damage_prediction as DP        # noqa: E402
from engine.services.damage_prediction import MinMaxDamage  # noqa: E402

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/services/damage_prediction.py",
        "scripts/python/tests/engine/test_884r1_extra_max_groupes_offline.py",
    ),
}

_HP = 10 ** 6          # cible inepuisable : aucun cap d'overkill ne doit brouiller les bornes
_EXTRA = 332           # la valeur MESUREE de l'ecart live (#884), pas un nombre rond


def _pred(extra_max: int, groupe: dict):
    return DP.get_multi_hit_attack_prediction(
        target_current_health=_HP, initial_damage=1000, hits=1, spread_pct=20,
        extra_max=extra_max, extra_groups=[groupe])


def _bornes(r):
    d = r.raw_health_damage
    return int(d.min), int(d.max)


# --------------------------------------------------------------------------------------------
# Etage 1 -- forme `amount` : l'extra-max MORD, sur la borne MAX et sur elle seule.
# --------------------------------------------------------------------------------------------

def test_forme_amount_le_groupe_recoit_l_extra_max():
    grp = {"count": 1, "amount": 2000}
    sans = _bornes(_pred(0, grp))
    avec = _bornes(_pred(_EXTRA, grp))
    assert sans[0] < sans[1], \
        "TEMOIN DEGENERE : la reference doit avoir une amplitude (%s)" % (sans,)
    # 1 coup d'arme + 1 coup de groupe : chacun prend l'extra-max sur SA borne haute.
    assert avec[0] == sans[0], \
        "la borne MIN a bouge : l'extra-max ne doit gonfler que le BOUT HAUT (%s -> %s)" % (
            sans, avec)
    assert avec[1] == sans[1] + 2 * _EXTRA, \
        "le groupe n'a pas recu l'extra-max : %s -> %s (attendu +%d sur la borne MAX)" % (
            sans, avec, 2 * _EXTRA)


# --------------------------------------------------------------------------------------------
# Etage 2 -- forme `predefined` : cellule PLATE, l'extra-max est INERTE.
# --------------------------------------------------------------------------------------------

def test_forme_predefined_le_groupe_est_INERTE_a_l_extra_max():
    """C'est le CONTRE-TEMOIN de l'etage 1, et il n'est pas decoratif : c'est lui qui separe
    << l'extra-max descend >> de << l'extra-max s'ajoute partout >>. La cellule `predefined` EST
    la branche PLATE du natif (`request+0x6a == 0`), qui ne lit pas `ExtraMaxDamage`."""
    grp = {"count": 1, "predefined": MinMaxDamage(min=1600, max=2400)}
    sans = _bornes(_pred(0, grp))
    avec = _bornes(_pred(_EXTRA, grp))
    # Le coup d'ARME, lui, passe par `GetBaseDamageFix64` -> il prend l'extra-max. Le GROUPE non.
    assert avec[1] - sans[1] == _EXTRA, (
        "la cellule PLATE du groupe a bouge : %s -> %s. Seul le coup d'ARME doit prendre "
        "l'extra-max (+%d), le `predefined` est la branche qui ne lit PAS `ExtraMaxDamage`."
        % (sans, avec, _EXTRA))
    assert avec[0] == sans[0], "la borne MIN a bouge : %s -> %s" % (sans, avec)


# --------------------------------------------------------------------------------------------
# Etage 3 -- sans extra-max, le port est INCHANGE (non-regression du foyer partage).
# --------------------------------------------------------------------------------------------

def test_sans_extra_max_le_correctif_est_un_no_op_strict():
    for grp in ({"count": 2, "amount": 2000},
                {"count": 2, "predefined": MinMaxDamage(min=1600, max=2400)}):
        r0 = _pred(0, grp)
        assert _bornes(r0) == _bornes(_pred(0, grp)), "instabilite du montage"
        assert int(r0.total_damage.min) <= int(r0.total_damage.max)
