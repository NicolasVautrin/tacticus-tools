"""#419-r1-tr9-r4-r1-r2 -- les deux effets a gate `IsNormalAttack` entres au canal COUPS.

Le residu recensait QUATRE consommateurs non portes du noeud
`IdunBattleLogic.Entities.DSLTriggers$$IsNormalAttack`. Deux entrent au registre ici, chacun avec
sa confrontation ; les deux autres ont leur verdict dans `docs/rl/case-419-r1-tr9-r4-r1-r2-*.md`
(`Dakka_ExtraHits` 1105 = registered-but-DEAD, `LegendaryCommander_ExtraHits` 1395 = residu).

CE QUE CE FICHIER GARDE, par effet, TROIS crans (le meme protocole que la garde jumelle
`test_419r1tr9_r4_r1_fold_context_live.py`) :

  1. **LE MONTAGE EST INSTALLE** -- mesure 100 % NATIVE, avec un TEMOIN INTERNE. Sans ce cran, un
     accord port/natif serait celui d'un montage vide.
     * `ShroudPsalm` : le cast retire exactement `hitsReduction` coups a l'allie affecte et RIEN au
       caster (que le selecteur natif EXCLUT).
     * `VoltagheistField_ExtraHit` : le bras greffe rend exactement `extraHit` coup de plus au
       porteur, et rien au temoin.
  2. **LE PORT SUIT** -- `appliedHits`, natif == port, dans les deux etats et sur les deux cibles /
     les deux attaquants. Entiers, aucune tolerance.
  3. **LA CONTRE-EPREUVE MORD** -- le port prive du comportement se DEPLACE exactement la ou
     l'effet est actif, et NULLE PART ailleurs. Sans ce cran, l'accord ne distinguerait pas « le
     port modelise l'effet » de « l'effet ne change rien ici ».

⚠ Le mutant patche la METHODE de la classe, jamais le registre `EFFECT_CLASSES` : la scene est
deja hydratee quand le mutant tourne, donc retirer la cle du registre ne defait RIEN et rend un
vert menteur (mesure du 2026-08-02, piege `feedback_verify_the_mutation_applied`).

ASCII only. Probes jumeaux : `scripts/python/probe_419r1tr9_r4_r1_r2_shroud_psalm.py` et
`scripts/python/probe_419r1tr9_r4_r1_r2_voltagheist.py`.
"""
from __future__ import annotations

import os
import tempfile

import pytest

import probe_419r1tr9_r4_r1_r2_shroud_psalm as SP
import probe_419r1tr9_r4_r1_r2_voltagheist as VF


@pytest.fixture(scope="module")
def shroud(live_session, rpc, build_runner, host):
    """UN runner : mesure avant le cast, cast de `ShroudPsalm`, mesure apres."""
    tmp = tempfile.mkdtemp(prefix="tacticus_419r1r2_sp_")   # tmpdir SYSTEME (#455)
    bc = SP.write_bc(os.path.join(tmp, "seed_shroud.json"))
    rid = build_runner(SP.SEED, SP.build_args(bc))["rid"]
    try:
        return SP.run(live_session, rpc, rid, SP.hits_reduction())
    except SP.MontageError as e:
        pytest.fail(str(e), pytrace=False)
    finally:
        host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)


@pytest.fixture(scope="module")
def volt(live_session, rpc, build_runner, host):
    """DEUX bras (`graft` / `none`), un runner a la fois, libere avant le suivant. Le premier bras
    FIXE la geometrie ; le second la rejoue, appariee par `visualId`."""
    tmp = tempfile.mkdtemp(prefix="tacticus_419r1r2_vf_")
    out, layout_vis = {}, None
    for arm in VF.ARMS:
        bc = VF.write_bc(os.path.join(tmp, f"seed_volt_{arm}.json"), arm)
        rid = build_runner(VF.SEED, VF.build_args(bc))["rid"]
        try:
            out[arm] = VF.run(live_session, rpc, rid, arm, layout_vis)
            layout_vis = out[arm]["layout_vis"]
        except VF.MontageError as e:
            pytest.fail(f"[{arm}] {e}", pytrace=False)
        finally:
            host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)
    return out


# --------------------------------------------------------------- ShroudPsalm (1366), MALUS DEFENSE

def test_shroud_montage_installed(shroud):
    """Cran 1 : mesure NATIVE seule. Le cast retire `hitsReduction` coups a l'ALLIE et rien au
    CASTER -- `ShroudPsalmAbility$$ExecuteBehaviour` vise `Friends(Caster, AllUnits - Caster, 3)`,
    donc le caster est le TEMOIN INTERNE."""
    red = SP.hits_reduction()
    assert red > 0, f"hitsReduction lu au gameconfig = {red}"
    assert "ShroudPsalm" in shroud["ally_effects"], (
        f"l'effet ShroudPsalm n'est pas actif sur l'allie : {shroud['ally_effects']}")
    assert "ShroudPsalm" not in shroud["caster_effects"], (
        f"le caster porte l'effet alors que le selecteur natif l'EXCLUT : "
        f"{shroud['caster_effects']}")
    d_ally = shroud["after"]["ally"]["native"]["hits"] - shroud["before"]["ally"]["native"]["hits"]
    d_cast = (shroud["after"]["caster"]["native"]["hits"]
              - shroud["before"]["caster"]["native"]["hits"])
    assert d_ally == -red, f"le natif ne retire pas {red} coups a l'allie (d = {d_ally})"
    assert d_cast == 0, f"le natif touche au TEMOIN (caster), d = {d_cast}"


def test_shroud_port_matches_native(shroud):
    """Cran 2 : accord EXACT sur `appliedHits`, avant ET apres, sur les deux cibles."""
    bad = []
    for phase in ("before", "after"):
        for label in ("ally", "caster"):
            n = shroud[phase][label]["native"]["hits"]
            p = shroud[phase][label]["port"]["hits"]
            if n != p:
                bad.append(f"[{phase}/{label}] natif h{n} vs port h{p}")
    assert not bad, "divergences port/natif : " + "; ".join(bad)


def test_shroud_counter_probe_bites(shroud):
    """Cran 3 : le port prive du comportement `ShroudPsalm` REMONTE de `hitsReduction` coups sur
    l'allie affecte, et ne bouge pas sur le temoin."""
    red = SP.hits_reduction()
    b_a = shroud["mutant"]["ally"] - shroud["after"]["ally"]["port"]["hits"]
    b_c = shroud["mutant"]["caster"] - shroud["after"]["caster"]["port"]["hits"]
    assert b_a == red, (
        f"le mutant ne retire pas le malus de coups sur l'allie (deplacement {b_a}, attendu {red}) "
        f"-- il ne teste donc pas ce qu'il pretend")
    assert b_c == 0, f"le mutant mord sur le TEMOIN (deplacement {b_c})"


# ------------------------------------------------ VoltagheistField_ExtraHit (1381), BONUS ATTAQUANT

def test_volt_montage_installed(volt):
    """Cran 1 : mesure NATIVE seule. La greffe du passif rend `extraHit` coup de plus au porteur
    (qui recoit un repair de `LivingMetal` au debut de son tour), et rien au temoin."""
    bump = VF.extra_hit()
    assert bump > 0, f"extraHit lu au gameconfig = {bump}"
    assert "VoltagheistField_ExtraHit" in volt["graft"]["rows"]["carrier"]["effects"], (
        f"l'effet n'est pas actif dans le bras `graft` : "
        f"{volt['graft']['rows']['carrier']['effects']}")
    assert "VoltagheistField_ExtraHit" not in volt["none"]["rows"]["carrier"]["effects"], (
        f"l'effet est actif dans le bras `none` -- la greffe n'a pas ete retiree : "
        f"{volt['none']['rows']['carrier']['effects']}")
    d_c = (volt["graft"]["rows"]["carrier"]["native"]["hits"]
           - volt["none"]["rows"]["carrier"]["native"]["hits"])
    d_w = (volt["graft"]["rows"]["witness"]["native"]["hits"]
           - volt["none"]["rows"]["witness"]["native"]["hits"])
    assert d_c == bump, f"le natif ne rend pas {bump} coup de plus au porteur (d = {d_c})"
    assert d_w == 0, f"le natif touche au TEMOIN, d = {d_w}"


def test_volt_port_matches_native(volt):
    """Cran 2 : accord EXACT sur `appliedHits`, dans les deux bras, sur les deux attaquants."""
    bad = []
    for arm in VF.ARMS:
        for label in ("carrier", "witness"):
            n = volt[arm]["rows"][label]["native"]["hits"]
            p = volt[arm]["rows"][label]["port"]["hits"]
            if n != p:
                bad.append(f"[{arm}/{label}] natif h{n} vs port h{p}")
    assert not bad, "divergences port/natif : " + "; ".join(bad)


def test_volt_counter_probe_bites(volt):
    """Cran 3 : le port prive du comportement `VoltagheistField_ExtraHit` perd `extraHit` coup dans
    le bras `graft` sur le porteur, et ne bouge NI sur le temoin NI dans le bras `none`."""
    bump = VF.extra_hit()
    b_c = volt["graft"]["mutant"]["carrier"] - volt["graft"]["rows"]["carrier"]["port"]["hits"]
    b_w = volt["graft"]["mutant"]["witness"] - volt["graft"]["rows"]["witness"]["port"]["hits"]
    n_c = volt["none"]["mutant"]["carrier"] - volt["none"]["rows"]["carrier"]["port"]["hits"]
    assert b_c == -bump, (
        f"le mutant ne retire pas le coup bonus du porteur (deplacement {b_c}, attendu {-bump})")
    assert b_w == 0, f"le mutant mord sur le TEMOIN (deplacement {b_w})"
    assert n_c == 0, f"le mutant mord SANS porteur, bras `none` (deplacement {n_c})"
