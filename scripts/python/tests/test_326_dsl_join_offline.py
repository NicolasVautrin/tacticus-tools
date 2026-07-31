"""#326 -- le lecteur de la table PHASE 1 (#325) tient-il ses promesses, AVANT que la table existe ?

La jointure de l'etage C consomme une table `primitive <-> abilities` produite par un AUTRE agent.
Tant qu'elle n'a pas atterri, la seule chose qu'on puisse valider est le CONTRAT : les formes de
nom acceptees, la normalisation, et -- le point qui compte -- que ce qui ne se resout PAS soit
COMPTE et NOMME au lieu d'etre jete. Un element silencieusement ignore ampute le denominateur et
se lit ensuite comme « cette primitive a peu de levier », ce qui est exactement l'inverse de la
verite qu'on cherche.

Ces tests sont OFFLINE (tables de symboles versionnees + gameconfig), aucune session Frida.

AUTO-PORTANTS : ils ne lisent RIEN de `logs/`
---------------------------------------------
`logs/` est gitignore -- il meurt avec le worktree et n'existe pas dans un checkout frais. Un
test qui y puise passe chez son auteur (ou un probe a tourne) et ECHOUE partout ailleurs : c'est
exactement ce qui est arrive a quatre de ces tests, verts uniquement grace a la table de
couverture laissee la par une execution anterieure de l'inventaire.
(Ce fichier n'ecrit nulle part le motif en clair : le cliquet du bas se ferait attraper par son
propre balayage -- meme dispositif que `test_314_absolute_repo_path_offline.py`.)

Deux parades, selon ce que le test interroge :
  * il verifie une propriete du VOCABULAIRE -> il la re-derive de `data/symbols/<CURRENT>/`
    (VERSIONNE) via `probe_326_dsl_primitive_inventory.native_primitives`, pas du TSV de sortie.
    C'est meme plus juste : on teste la source, pas un cache.
  * il exerce la JOINTURE -> il FABRIQUE ses entrees minimales dans `tmp_path` et redirige TOUTES
    les E/S du probe (`--coverage`, `--reach`, `--out`, `--map-out`, `--doc`).
Un `skip` conditionnel serait pire que le rouge : il rendrait vert un checkout ou la jointure ne
marche pas.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PYDIR))

import probe_326_dsl_join as J                      # noqa: E402
import probe_326_dsl_primitive_inventory as INV     # noqa: E402


@pytest.fixture
def coverage_file(tmp_path):
    """Couverture MINIMALE fabriquee -- l'entree que la jointure consomme. Deux primitives
    suffisent : une par famille utilisee dans les cas de test."""
    p = tmp_path / "coverage.tsv"
    with io.open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# schema=326.coverage.v1 (fixture de test)\n")
        fh.write("family\tname\tsymbol\toverloads_frida\toverloads_ghidra\tverdict\tevidence\tport_site\n")
        fh.write("DSLSelectors\tFilter\tIdunBattleLogic.Entities.DSLSelectors$$Filter\t1\t1\t"
                 "PORTE\t-\tengine/entities/selectors/units.py:173\n")
        fh.write("DSLBehaviors\tAddEffect\tIdunBattleLogic.Entities.DSLBehaviors$$AddEffect\t4\t4\t"
                 "PORTE\t-\tengine/runner/abilities/behaviours/effects.py:1\n")
    return p


@pytest.fixture
def reach_file(tmp_path):
    """Joignabilite MINIMALE fabriquee, avec les deux abilities citees par les cas de test."""
    p = tmp_path / "reach.tsv"
    cols = ("ability\tverdict\trelic_state\thero_pool\thero_offpool\tn_hero\tn_mow\tn_summon\t"
            "n_npc\tvoies\tsummoners\tsample_carrier\tvariante_portee\tvoies_non_couvertes\n")
    with io.open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# schema=326.reachability.v2 (fixture de test)\n")
        fh.write(cols)
        for aid in ("DawnBlade", "BrazierOfHolyFire"):
            fh.write("%s\tCONFRONTABLE_POOL\t-\t1\t0\t1\t0\t0\t0\tactive\t-\t-\t-\t-\n" % aid)
    return p


def _argv(tmp_path, coverage, reach, *extra):
    """Toutes les E/S du probe redirigees dans `tmp_path`. `--doc` compris : sans lui le test
    REGENERE le document versionne `docs/rl/dsl-primitive-leverage.md` avec ses donnees jouet."""
    return ["probe_326_dsl_join.py",
            "--coverage", str(coverage), "--reach", str(reach),
            "--out", str(tmp_path / "lev.tsv"), "--map-out", str(tmp_path / "map.tsv"),
            "--doc", str(tmp_path / "doc.md")] + list(extra)


def test_norm_primitive_accepte_les_trois_formes():
    """Nom nu, symbole `$$`, forme pointee -- meme primitive, et la FAMILLE est conservee."""
    assert J.norm_primitive("Filter") == ("", "Filter")
    assert J.norm_primitive("IdunBattleLogic.Entities.DSLSelectors$$Filter") == ("DSLSelectors", "Filter")
    assert J.norm_primitive("DSLSelectors.Filter") == ("", "Filter")
    assert J.norm_primitive("IdunBattleLogic.Entities.DSLBehaviors$$AddEffect") == ("DSLBehaviors", "AddEffect")
    # La famille DECLAREE par la table prime sur celle deduite du symbole.
    assert J.norm_primitive("IdunBattleLogic.Entities.DSLSelectors$$If", "DSLSelectors") == ("DSLSelectors", "If")


def test_famille_discrimine_les_homonymes():
    """`If` existe dans QUATRE familles et `op_BitwiseAnd` dans TROIS. Keyer par le seul nom
    fusionnerait leurs leviers -- chaque famille heriterait de la somme des autres.

    Re-derive de `data/symbols/<CURRENT>/` (VERSIONNE), pas du TSV de sortie : la propriete est
    celle du BUILD, et la lire dans `logs/` ne testait que le dernier run local."""
    prim = INV.native_primitives(INV._current_build())
    fams_if = {fam for (fam, name) in prim if name == "If"}
    fams_and = {fam for (fam, name) in prim if name == "op_BitwiseAnd"}
    assert len(fams_if) >= 3, fams_if
    assert len(fams_and) >= 3, fams_and


def test_les_operateurs_sont_dans_le_vocabulaire():
    """Les combinateurs `a & b` / `!a` ne sont pas des methodes de factory mais des OPERATEURS des
    bases. Les omettre retirait du vocabulaire la primitive la plus utilisee du binaire."""
    prim = INV.native_primitives(INV._current_build())
    assert ("AbilityTrigger", "op_BitwiseAnd") in prim
    assert ("TargetsSelector", "op_Subtraction") in prim
    assert ("AbilityBehaviour", "op_Addition") in prim


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
    traits = J.trait_names()
    _fwd, rev = J.ability_class_map(build)
    assert J.norm_ability("DawnBlade", rev, gc_names) == "DawnBlade"
    assert J.norm_ability("DawnBlade_HealAbility", rev, gc_names) == "DawnBlade"
    assert J.norm_ability(
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.DawnBlade_HealAbility$$CreateTrigger",
        rev, gc_names) == "DawnBlade"
    # Voie TRAIT : le composeur natif existe, mais AUCUN nom d'ability gameconfig ne lui repond.
    assert J.norm_ability("FinalJusticeAbility", rev, gc_names, traits) == "trait:FinalJustice"
    # ... et sans la table des traits, il reste NON RESOLU (on ne devine pas).
    assert J.norm_ability("FinalJusticeAbility", rev, gc_names) is None
    # inconnu -> None, JAMAIS une valeur inventee
    assert J.norm_ability("CeciNEstPasUneAbility", rev, gc_names, traits) is None


def test_jointure_compte_les_non_resolus(tmp_path, capsys, coverage_file, reach_file):
    """Une relation dont la primitive ou l'ability ne se resout pas doit etre COMPTEE, pas jetee."""
    p1 = tmp_path / "p1.tsv"
    with io.open(p1, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("primitive\tability\n")
        fh.write("IdunBattleLogic.Entities.DSLSelectors$$Filter\tDawnBlade_HealAbility\n")
        fh.write("DSLBehaviors.AddEffect\tBrazierOfHolyFire\n")
        fh.write("PrimitiveQuiNExistePas\tBrazierOfHolyFire\n")
        fh.write("Filter\tAbilityQuiNExistePas\n")
    argv = sys.argv
    sys.argv = _argv(tmp_path, coverage_file, reach_file, "--p1", str(p1))
    try:
        J.main()
    finally:
        sys.argv = argv
    txt = capsys.readouterr().out
    assert "aretes phase 1 : 4 | retenues : 2" in txt
    assert "rejetees primitive : 1" in txt
    assert "rejetees owner : 1" in txt
    assert "PrimitiveQuiNExistePas" in txt
    assert "AbilityQuiNExistePas" in txt


def test_sans_p1_le_leverage_est_non_mesurable(tmp_path, coverage_file, reach_file):
    """Sans table phase 1, le script ne DEVINE pas un classement : il ecrit NON_MESURABLE_P1."""
    argv = sys.argv
    sys.argv = _argv(tmp_path, coverage_file, reach_file)
    try:
        J.main()
    finally:
        sys.argv = argv
    body = io.open(tmp_path / "lev.tsv", encoding="utf-8").read()
    assert "p1=ABSENTE" in body
    assert "NON_MESURABLE_P1" in body
    assert "\t0\t" not in body.split("\n", 2)[2][:2000]      # aucun faux zero de levier


def test_aucun_test_de_ce_fichier_ne_lit_logs():
    """CLIQUET -- ce fichier ne doit JAMAIS puiser dans `logs/`.

    `logs/` est gitignore : il n'existe pas dans un checkout frais. Quatre tests d'ici en
    dependaient et etaient verts uniquement grace a un artefact laisse par un run anterieur --
    defaut invisible pour son auteur, rouge pour tout le monde. Le motif est compose par
    CONCATENATION pour que le cliquet ne s'attrape pas lui-meme."""
    needle = "logs" + "/" + "326_"
    offenders = [i for i, ln in enumerate(io.open(Path(__file__), encoding="utf-8"), 1)
                 if needle in ln and "needle =" not in ln]
    assert not offenders, "lignes lisant logs/ : %s" % offenders
