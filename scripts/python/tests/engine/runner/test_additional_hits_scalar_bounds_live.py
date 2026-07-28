"""R6-c -- BORNES COMBAT des groupes `amount` RESTANTS du canal #179, sur les DEUX formes.

QUESTION (binaire, DEUX axes) : un groupe de coups additionnels en mode `amount` tire-t-il, en
COMBAT, dans les MEMES BORNES que le natif, et consomme-t-il le MEME NOMBRE de tirages ?

RE (decompile = verite, gqfc5mff6c). `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create`
range DEUX noeuds, lu verbatim :

    param_1[1] = param_3                     # +0x08  ROLL
    if (param_8 != 0) param_3 = param_8;
    param_1[2] = param_3                     # +0x10  DISPLAY (repli = ROLL)

et `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits(this, entities, useDisplay)` lit le
slot 4 du DISPLAY, puis -- si `useDisplay == false`, ce que la face COMBAT impose toujours
(`IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType`
passe l'octet a zero) -- ECRASE les bornes par les slots 2/3 du ROLL.

DEUX FORMES, qui ne se generalisent PAS l'une a l'autre :

  (1) NOEUDS DISTINCTS -- `CyclicIonBlaster_AdditionalHitsEffect$$CreateAdditionalHits` :
        ROLL    = ConditionalAmount(cond, RandomAmount(Sum(minDmg,extraDmg), Sum(maxDmg,extraDmg)),
                                          RandomAmount(minDmg, maxDmg))
        DISPLAY = ConditionalAmount(cond, Sum(minDmg,extraDmg), minDmg)
        cond    = HasEffect(target@0x178, 0x462 Markerlight, 1, 6) | HasTrait(target@0x178, 5 Mechanical)
      Axe VALEUR. `IdunBattle.Entities.Formulas.ConditionalAmount$$CalculateMin` delegue
      `CalculateMin` a la branche retenue, et `RandomAmount$$CalculateMin`/`CalculateMax` rendent
      `Calculate` de leur sous-noeud -> bornes = [minDmg, maxDmg] (+extraDmg SUR LES DEUX si cond).

  (2) NOEUD UNIQUE SCALAIRE -- `ExplosiveMaladies_ExtraRangedAttackEffect$$CreateAdditionalHits`
      (`ConfigVar(8)`, `Create` INLINE : `param_1[1] == param_1[2]`) et
      `FoulInfusion_ExtraHitsEffect$$CreateAdditionalHits` (`ConfigVar(0xb)`, `param_8 = 0`
      EXPLICITE). Les slots 2 et 3 tapent le MEME `IdunBattle.Entities.Formulas.ConfigAmount`
      => cellule DEGENEREE [v, v]. Axe CONSOMMATION : `IdunBattle.Core.HitDamage$$GetDamage` ouvre
      sur `if (*param_1 == param_1[1]) return *param_1;` -> **0 tirage** au lieu de 1. La valeur
      seule ne suffirait pas a trancher (un tirage +-20 % peut tomber sur v) ; le delta de
      `genrand_int32` entre deux `dumpRng`, si.

MESURE D'ORIGINE (`probe_r6c_ah_bounds.py`, flux RNG cale par `dumpRng`) :
  * cyclic cond FAUX  (tauCrisis -> astraCreed)    4/4 port, 0/4 contrefactuel, 4/4 discriminants
  * cyclic cond VRAI  (tauCrisis -> admecMarshall) 4/4 port, 0/4 contrefactuel, 4/4 discriminants
  * maladies (deathPutrifier + admecMarshall)      4/4 valeur ET conso (natif 3, contrefactuel 4)
  * foul     (deathPutrifier melee)                4/4 valeur ET conso (natif 3, contrefactuel 4)
Cf. `docs/rl/case-r6c-amount-group-bounds.md`.

⚠ Le montage `foul` portait un residu ORTHOGONAL (VALEUR du coup d'ARME de `deathPutrifier`
divergente, ecart de SIGNE VARIABLE) : RESOLU depuis, cf. `case-dpw-deathputrifier-weapon-cell.md`
(l'attaque est re-resolue sur `astraSmnKell`, qui APPARAIT dans l'aura Contagion et y prend
`ContagionsOfNurgle_ArmorReduction1` -> armure 1496 -> 1197). La garde de CE fichier reste ancree
sur le GROUPE et sur la CONSOMMATION -- le coup d'arme a sa garde propre
(`test_contagions_of_nurgle_new_unit_live.py`).
"""
from __future__ import annotations

import argparse
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                  # scripts/python
from probe_r6c_ah_bounds import _run_seed                            # noqa: E402


def _args(case, target):
    return argparse.Namespace(case=case, target=target, rank=None, hp=90000, armor=6000,
                              max_turns=30, verbose=False)


def _measure(rpc, seed, case, target):
    row = _run_seed(rpc, seed, _args(case, target))
    if row is None:
        pytest.skip(f"montage {case}/{target} seed {seed} non monte")
    arme_s, grp_s, bnd_s, n_s = row["off"]["shipped"]
    _ad, grp_d, _bd, n_d = row["off"]["display"]
    k = len(arme_s)
    return {"live": row["live"], "arme": arme_s, "k": k,
            "grp_live": row["live"][k:k + len(grp_s)], "grp_shipped": grp_s, "grp_display": grp_d,
            "bounds": bnd_s, "n_native": row["n_native"], "n_shipped": n_s, "n_display": n_d}


# ---------------------------------------------------------------- forme 1 : noeuds DISTINCTS


@pytest.mark.parametrize("seed", ["777", "12345"])
def test_cyclic_ion_blaster_roll_bounds_condition_false_live(live_session, rpc, seed):
    """Branche FAUSSE du `ConditionalAmount` (cible sans Markerlight ni Mechanical) : la face
    COMBAT doit tirer dans `[minDmg, maxDmg]`, PAS etaler `minDmg` a +-20 %. `astraCreed` ne porte
    AUCUN trait (hors Hero) -> rien d'autre ne bouge."""
    r = _measure(rpc, seed, "cyclic", "astraCreed")
    print(f"\n[R6-c cyclic/FALSE] seed={seed} bornes={r['bounds']} "
          f"shipped={r['grp_shipped']} display={r['grp_display']} live={r['grp_live']}")
    assert r["grp_shipped"], "aucun coup du canal #179 rejoue offline"
    b = (r["bounds"] or [{}])[0]
    assert b.get("min") is not None and b.get("max") is not None, (
        f"le descripteur CyclicIonBlaster ne porte pas les bornes du noeud ROLL ({b}) : "
        "`CyclicIonBlasterAdditionalHitsEffect.additional_hit_groups` rend-il encore `amount` SEUL ?")
    assert r["arme"] == r["live"][:r["k"]], (
        f"coups d'ARME desalignes (live={r['live'][:r['k']]} off={r['arme']}) : le flux RNG n'est "
        "pas aligne a l'entree du groupe, la mesure des bornes ne prouverait rien.")
    assert r["grp_shipped"] != r["grp_display"], (
        f"seed {seed} : montage NON discriminant ({r['grp_shipped']}) -- re-selectionner la seed.")
    assert r["grp_shipped"] == r["grp_live"], (
        f"port LIVRE != live : shipped={r['grp_shipped']} live={r['grp_live']} "
        f"(display={r['grp_display']})")
    assert r["grp_display"] != r["grp_live"], (
        f"le contrefactuel `amount +-20 %` reproduit AUSSI le live ({r['grp_display']}) : "
        "garde AVEUGLE.")


@pytest.mark.parametrize("seed", ["777", "12345"])
def test_cyclic_ion_blaster_roll_bounds_condition_true_live(live_session, rpc, seed):
    """Branche VRAIE du `ConditionalAmount` (cible `Mechanical`) : `extraDmg` doit s'ajouter aux
    DEUX bornes (`Sum(minDmg,extraDmg)`, `Sum(maxDmg,extraDmg)`), pas au seul minimum.

    2e AXE DISCRIMINANT, et pas une redite : la largeur RELATIVE s'INVERSE entre les deux montages
    (cond FAUX -> ROLL 299 vs contrefactuel 240 ; cond VRAI -> ROLL 299 vs contrefactuel 479), donc
    un facteur cale sur l'un se trahirait sur l'autre. `admecMarshall` ne porte que `Mechanical`."""
    r = _measure(rpc, seed, "cyclic", "admecMarshall")
    print(f"\n[R6-c cyclic/TRUE] seed={seed} bornes={r['bounds']} "
          f"shipped={r['grp_shipped']} display={r['grp_display']} live={r['grp_live']}")
    assert r["grp_shipped"], "aucun coup du canal #179 rejoue offline"
    b = (r["bounds"] or [{}])[0]
    assert b.get("min") is not None and b.get("max") is not None, f"bornes ROLL absentes ({b})"
    assert b["max"] > b["min"], (
        f"bornes degenerees en branche VRAIE ({b}) : `extraDmg` n'a-t-il ete ajoute qu'au MIN ?")
    assert r["arme"] == r["live"][:r["k"]], "coups d'ARME desalignes -> flux non aligne"
    assert r["grp_shipped"] != r["grp_display"], f"seed {seed} : montage NON discriminant"
    assert r["grp_shipped"] == r["grp_live"], (
        f"port LIVRE != live : shipped={r['grp_shipped']} live={r['grp_live']} "
        f"(display={r['grp_display']})")
    assert r["grp_display"] != r["grp_live"], "garde AVEUGLE (le contrefactuel reproduit aussi)"


# ------------------------------------------------- forme 2 : noeud SCALAIRE (axe CONSOMMATION)


@pytest.mark.parametrize("case,target,seed", [("maladies", "astraCreed", "777"),
                                              ("foul", "astraCreed", "777")])
def test_scalar_node_degenerate_cell_consumes_no_roll_live(live_session, rpc, case, target, seed):
    """Descripteur a noeud UNIQUE SCALAIRE : cellule COMBAT DEGENEREE -> `HitDamage$$GetDamage`
    court-circuite, donc **un tirage de MOINS** que le contrefactuel `amount +-20 %`.

    Le verdict porte sur les DEUX axes : le nombre de `genrand_int32` consommes par le natif entre
    deux `dumpRng` (re-simulation du Mersenne Twister = le compte exact) ET la valeur du groupe.
    Un port qui rendrait la bonne valeur en consommant un tirage de trop desynchroniserait tout
    l'aval -- c'est precisement ce que cette garde interdit."""
    r = _measure(rpc, seed, case, target)
    print(f"\n[R6-c {case}] seed={seed} bornes={r['bounds']} shipped={r['grp_shipped']} "
          f"display={r['grp_display']} live={r['grp_live']} | genrand natif={r['n_native']} "
          f"shipped={r['n_shipped']} display={r['n_display']}")
    assert r["grp_shipped"], "aucun coup du canal #179 rejoue offline"
    b = (r["bounds"] or [{}])[0]
    assert b.get("min") is not None and b.get("min") == b.get("max"), (
        f"le descripteur scalaire ne rend pas une cellule DEGENEREE ({b}) : `param_8 == 0` -> "
        "`minNode` retombe sur `amountNode`, et ce noeud est un `ConfigAmount`.")
    # (1) CONSOMMATION -- l'axe que la valeur seule ne tranche pas.
    assert r["n_native"] > 0, "compte de tirages natif non re-simule (dumpRng indispo ?)"
    assert r["n_shipped"] == r["n_native"], (
        f"le port LIVRE consomme {r['n_shipped']} tirages contre {r['n_native']} au natif")
    assert r["n_display"] != r["n_native"], (
        f"le contrefactuel consomme AUSSI {r['n_display']} tirages : garde AVEUGLE sur l'axe "
        "CONSOMMATION.")
    # (2) VALEUR -- la cellule degeneree rend une constante, independante du flux.
    assert r["grp_shipped"] == r["grp_live"], (
        f"port LIVRE != live : shipped={r['grp_shipped']} live={r['grp_live']}")
