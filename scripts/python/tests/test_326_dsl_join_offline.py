"""#326 -- le lecteur de la table PHASE 1 (#325) tient-il ses promesses, AVANT que la table existe ?

La jointure de l'etage C consomme une table `primitive <-> abilities` produite par un AUTRE agent.
Tant qu'elle n'a pas atterri, la seule chose qu'on puisse valider est le CONTRAT : les formes de
nom acceptees, la normalisation, et -- le point qui compte -- que ce qui ne se resout PAS soit
COMPTE et NOMME au lieu d'etre jete. Un element silencieusement ignore ampute le denominateur et
se lit ensuite comme « cette primitive a peu de levier », ce qui est exactement l'inverse de la
verite qu'on cherche.

Ces tests sont OFFLINE (tables de symboles versionnees + gameconfig), aucune session Frida.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PYDIR))

import probe_326_dsl_join as J     # noqa: E402


def test_norm_primitive_accepte_les_trois_formes():
    """Nom nu, symbole `$$`, forme pointee -- meme primitive."""
    assert J.norm_primitive("Filter") == "Filter"
    assert J.norm_primitive("IdunBattleLogic.Entities.DSLSelectors$$Filter") == "Filter"
    assert J.norm_primitive("DSLSelectors.Filter") == "Filter"
    assert J.norm_primitive("IdunBattleLogic.Entities.DSLBehaviors$$AddEffect") == "AddEffect"


def test_ability_class_map_couvre_les_formes_composees():
    """Une ability gameconfig se materialise en 1..N classes natives ; le mapping doit les
    prendre TOUTES, y compris quand la casse differe et quand la classe n'a aucune methode
    nommee (donc absente de `methods.tsv`)."""
    build = J._current_build()
    fwd, rev = J.ability_class_map(build)
    # 1:N par suffixe `_X`
    assert "DawnBlade_HealAbility" in fwd["DawnBlade"]
    assert "DawnBlade_InitAbility" in fwd["DawnBlade"]
    # 1:N par suffixe accole
    assert "CursedPlagueBellAttackAbility" in fwd["CursedPlagueBell"]
    # casse divergente gameconfig <-> natif
    assert "MonsterSlayerofCalibanAbility" in fwd["MonsterSlayerOfCaliban"]
    # classe SANS methode nommee : presente dans classes.tsv, absente de methods.tsv
    assert "AblativePlatingAbility" in fwd["AblativePlating"]
    # garde anti-prefixe : `Heal` ne doit pas avaler `HealingBalms*`
    assert not any(s.startswith("HealingBalms") for s in fwd.get("Heal", ()))


def test_norm_ability_resout_les_trois_formes():
    build = J._current_build()
    import gameconfig as gc
    gc_names = set(gc._cfg()["units"]["abilities"])
    _fwd, rev = J.ability_class_map(build)
    assert J.norm_ability("DawnBlade", rev, gc_names) == "DawnBlade"
    assert J.norm_ability("DawnBlade_HealAbility", rev, gc_names) == "DawnBlade"
    assert J.norm_ability(
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.DawnBlade_HealAbility$$CreateTrigger",
        rev, gc_names) == "DawnBlade"
    # inconnu -> None, JAMAIS une valeur inventee
    assert J.norm_ability("CeciNEstPasUneAbility", rev, gc_names) is None


def test_jointure_compte_les_non_resolus(tmp_path, capsys):
    """Une relation dont la primitive ou l'ability ne se resout pas doit etre COMPTEE, pas jetee."""
    p1 = tmp_path / "p1.tsv"
    with io.open(p1, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("primitive\tability\n")
        fh.write("IdunBattleLogic.Entities.DSLSelectors$$Filter\tDawnBlade_HealAbility\n")
        fh.write("DSLBehaviors.AddEffect\tBrazierOfHolyFire\n")
        fh.write("PrimitiveQuiNExistePas\tBrazierOfHolyFire\n")
        fh.write("Filter\tAbilityQuiNExistePas\n")
    out = tmp_path / "lev.tsv"
    argv = sys.argv
    sys.argv = ["probe_326_dsl_join.py", "--p1", str(p1), "--out", str(out),
                "--map-out", str(tmp_path / "map.tsv")]
    try:
        J.main()
    finally:
        sys.argv = argv
    txt = capsys.readouterr().out
    assert "relations phase 1 retenues : 2" in txt
    assert "primitives non resolues : 1" in txt
    assert "abilities non resolues : 1" in txt
    assert "PrimitiveQuiNExistePas" in txt
    assert "AbilityQuiNExistePas" in txt


def test_sans_p1_le_leverage_est_non_mesurable(tmp_path):
    """Sans table phase 1, le script ne DEVINE pas un classement : il ecrit NON_MESURABLE_P1."""
    out = tmp_path / "lev.tsv"
    argv = sys.argv
    sys.argv = ["probe_326_dsl_join.py", "--out", str(out), "--map-out", str(tmp_path / "map.tsv")]
    try:
        J.main()
    finally:
        sys.argv = argv
    body = io.open(out, encoding="utf-8").read()
    assert "p1=ABSENTE" in body
    assert "NON_MESURABLE_P1" in body
    assert "\t0\t" not in body.split("\n", 2)[2][:2000]      # aucun faux zero de levier
