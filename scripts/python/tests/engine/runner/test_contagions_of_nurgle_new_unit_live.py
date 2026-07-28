"""GARDE case-dpw — `ContagionsOfNurgle_AddEffectToNewUnit` : une unite qui APPARAIT dans une aura
Contagion ENNEMIE prend le debuff `-20 %` de `FixedArmor`, et cette armure entre dans les BORNES du
coup qui la frappe.

Ce que la garde PROUVE (et pas « le code est atteint ») : un OBSERVABLE bit-exact et un
CONTREFACTUEL qui echoue sur le meme montage.

MONTAGE (`probe_dpw_weapon_cell._run_seed`, board MC1_67, `--crit 0,0 --block-target 0,0
--hp-target 90000 --armor-target 6000`) : `deathPutrifier` caste `FoulInfusion` (1038) puis attaque
`astraCreed` en MELEE. L'attaque reveille `On(PreUnitAbility)` -> `SwornProtector` INVOQUE
`astraSmnKell` a 1 hex de `deathPutrifier` (donc DANS son aura Contagion) et lui fait prendre le
coup a la place de Creed (re-resolution de cible #120bis).

  * armure de Kell SANS le vecteur : 1496 -> cellule d'arme reduite `[2248, 3373]`
  * armure de Kell AVEC le vecteur : **1197** -> cellule **`[2248, 3621]`**

La cellule NATIVE `[2248, 3621]` a ete RESOLUE (unique) depuis les 4 valeurs live et les 4 flux RNG
(`probe_dpw_weapon_cell --solve`). Le BAS est le MEME dans les deux modeles : seul le HAUT bouge,
parce que `idun...StaticBattleRules.Damage$$GetDamageWithPiercing` = `max(0, d - armure,
d x percage%)` est affine PAR MORCEAUX -- baisser l'armure fait basculer le HAUT sur la branche
ARMURE sans toucher le BAS. C'est pour ca que l'ecart CHANGE DE SIGNE selon le flux, et c'est ce qui
rend les DEUX seeds ci-dessous complementaires (777 : contrefactuel SOUS le live ; 88 : contrefactuel
AU-DESSUS). Un facteur d'ajustement cale sur l'un se trahirait sur l'autre.

Chaines natives portees (symboles) :
  `IdunBattleLogic.Entities.Abilities.Active.Loki.ContagionsOfNurgle_AddEffectToNewUnit_Ability$$CreateTrigger` / `$$CreateBehaviour`
  `IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect$$.ctor` /
  `$$GetStatModificationAmount` / `$$CreateActiveCondition` / `$$CalculateRange`
  `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor`
Cf. `docs/rl/case-dpw-deathputrifier-weapon-cell.md`.

ASCII-only. Skip si pas de session live.
"""
from __future__ import annotations

import argparse
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                  # scripts/python
from probe_dpw_weapon_cell import _run_seed                          # noqa: E402

CONTAGIONS_ARMOR_REDUCTION_1 = 1071          # 0x42f
SUMMON_VIS = "astraSmnKell"


def _args():
    return argparse.Namespace(target="astraCreed", rank=None, hp=90000, armor=6000,
                              max_turns=30)


def _measure(rpc, seed):
    row = _run_seed(rpc, seed, _args())
    if row is None:
        pytest.skip(f"montage foul seed {seed} non monte")
    return row


@pytest.mark.parametrize("seed", ["777", "88"])
def test_weapon_cell_uses_summon_armor_debuffed_by_aura_live(live_session, rpc, seed):
    """Le coup d'ARME est bit-exact avec le live, et le CONTREFACTUEL (vecteur `On(UnitAdded)`
    neutralise, = le port d'avant ce cas) ne l'est PAS."""
    row = _measure(rpc, seed)
    live, off, cf = row["live"], row["off"], row["off_cf"]
    print(f"\n[dpw] seed={seed} live={live[:1]} port={off['per_hit'][:1]} "
          f"contrefactuel={cf['per_hit'][:1]} cellule={off['cell']} cf={cf['cell']}")
    assert off["per_hit"], "aucun coup d'arme rejoue offline"
    assert row["n_native"] == off["n_genrand"], (
        f"flux RNG desaligne (natif={row['n_native']} port={off['n_genrand']}) : la comparaison de "
        "VALEUR ne prouverait rien.")
    assert off["cell"] != cf["cell"], (
        f"seed {seed} : montage NON discriminant (meme cellule {off['cell']}) -- le vecteur ne "
        "change rien ici, re-selectionner la seed.")
    assert off["per_hit"][0] == live[0], (
        f"coup d'ARME != live : port={off['per_hit'][0]} live={live[0]} "
        f"(cellule port {off['cell']}, contrefactuel {cf['cell']})")
    assert cf["per_hit"][0] != live[0], (
        f"le contrefactuel reproduit AUSSI le live ({cf['per_hit'][0]}) : garde AVEUGLE.")
    # Le GROUPE de coups additionnels du meme coup reste bit-exact (non-regression R6-c) : sa valeur
    # est armure-INDEPENDANTE (branche percage gagnante des deux cotes), elle ne doit pas bouger.
    assert off["per_hit"][1:] == live[1:len(off["per_hit"])], (
        f"le canal #179 a bouge : port={off['per_hit'][1:]} live={live[1:]}")


@pytest.mark.parametrize("seed", ["777"])
def test_summoned_unit_carries_contagion_debuff_live(live_session, rpc, seed):
    """L'ECS du port donne au summon la MEME `FixedArmor` que le live apres l'attaque, et l'effet
    `ContagionsOfNurgle_ArmorReduction1` (1071) y est bien pose."""
    row = _measure(rpc, seed)
    live_kell = next((u for u in row["roster_after"] if u.get("vis") == SUMMON_VIS), None)
    off_kell = next((e for e in row["off"]["entities"] if e.get("vis") == SUMMON_VIS), None)
    print(f"\n[dpw] summon live={live_kell} offline={off_kell} "
          f"vecteur={row['off']['oua']}")
    assert live_kell is not None, (
        "aucun `astraSmnKell` live apres l'attaque : `SwornProtector` n'a pas invoque -- montage KO")
    assert off_kell is not None, "aucun summon offline : le port n'a pas invoque Kell"
    assert CONTAGIONS_ARMOR_REDUCTION_1 in (live_kell.get("eff") or []), (
        f"le summon LIVE ne porte pas l'effet {CONTAGIONS_ARMOR_REDUCTION_1} ({live_kell}) : "
        "le montage ne teste plus l'aura Contagion.")
    assert off_kell["fixed_armor"] == live_kell["fixedArmor"], (
        f"FixedArmor du summon : port={off_kell['fixed_armor']} live={live_kell['fixedArmor']}")
    posed = [r for c in (row["off"]["oua"] or []) for r in (c.get("res") or [])]
    assert any(p.get("effect") == "ContagionsOfNurgle_ArmorReduction1" for p in posed), (
        f"le vecteur `On(UnitAdded)` n'a rien pose ({row['off']['oua']})")
