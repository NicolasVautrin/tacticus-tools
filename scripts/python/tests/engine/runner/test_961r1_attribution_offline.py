"""#961-r1 -- CLIQUET du SEPARATEUR, purement OFFLINE (aucun runner, aucun RPC).

Ce que garde ce fichier n'est pas une valeur de degat : c'est ce qui a permis de TRANCHER
l'attribution, et que la version d'avant ne portait pas.

  1. Le montage de `measure_ll` doit offrir les QUATRE cellules du carre `distance x elevation`.
     Avant #961-r1 il n'en offrait que trois : la tuile de la cible etant prise comme la PREMIERE
     libre a la distance voulue, `adjacent` tombait sur une elevation EGALE et `range2` sur une
     tuile PLUS BASSE -- les deux regimes differaient donc par DEUX variables, et l'ecart paraissait
     MULTIPLICATIF alors qu'il est ADDITIF. Retirer `range2_flat` re-confondrait les deux axes.
  2. Le probe d'attribution doit substituer les foyers que `damage_ops/ability.py` resout dans SES
     globals. Un nom qui disparaitrait de la liste (renommage, deplacement) rendrait la trace
     SILENCIEUSEMENT incomplete -- exactement le mode de panne qui a fait croire a un facteur.

Ce cliquet ne mesure PAS le degat : la mesure est dans `docs/rl/case-961-r1-ecart-crit-au-contact.md`
et se rejoue par `python probe_961r1_attribution.py --seeds 777 --regimes adjacent,range2_flat`.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: Trop LARGE est sain, trop ETROIT est un faux vert : ce fichier lit le SOURCE de deux probes et
#: importe deux modules du pipeline, et il doit se rejouer des que l'un d'eux bouge.
DECLENCHEUR = {
    "chemins": (
        # Le montage dont ce cliquet garde le carre `distance x elevation`.
        "scripts/python/probe_961_necron_passives.py",
        # Le probe d'attribution dont il verifie que les foyers substitues existent ENCORE.
        "scripts/python/probe_961r1_attribution.py",
        # Les deux modules du pipeline ou vivent ces foyers : un RENOMMAGE ou un deplacement y
        # rendrait la trace silencieusement incomplete, et c'est precisement le mode de panne
        # qui a fait conclure a un facteur multiplicatif.
        "scripts/python/engine/runner/operations/damage_ops/ability.py",
        "scripts/python/engine/runner/operations/damage.py",
    ),
    "toujours": False,
    # Ce cliquet est PUREMENT STRUCTUREL : il lit un litteral par AST et teste la presence
    # d'attributs de module. Il ne resout aucun symbole natif et ne lit aucune table de
    # `data/symbols/**` -- un changement de build ne peut donc pas changer son verdict.
    "build": False,
    "raison": ("Garde le SEPARATEUR de l'attribution #961-r1 : le carre `distance x elevation` du "
               "montage (`range2_flat`, sans lequel les deux axes se re-confondent et l'ecart "
               "reparait comme un facteur) et l'existence des foyers que le probe d'attribution "
               "substitue dans les globals de `damage_ops/ability.py`. Il se rejoue donc des que "
               "l'un des deux probes ou l'un des deux modules de pipeline bouge -- un renommage y "
               "rendrait la trace silencieusement incomplete."),
}

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

PROBE_LL = PYDIR / "probe_961_necron_passives.py"
PROBE_ATTR = PYDIR / "probe_961r1_attribution.py"

#: Les QUATRE cellules du carre `distance x elevation` + la contre-epreuve negative. `range2_flat`
#: est celle qui manquait ; `adjacent` y tient la cellule << distance 1, elevation egale >>.
REGIMES_ATTENDUS = {"adjacent", "adjacent_low", "range2", "range2_flat", "none"}


def _dict_want(source: str) -> dict:
    """Recupere le litteral `want = {...}[regime]` de `measure_ll` par l'AST -- pas par un regex,
    qui accepterait une occurrence en commentaire."""
    arbre = ast.parse(source)
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Assign):
            continue
        cibles = [t.id for t in noeud.targets if isinstance(t, ast.Name)]
        if "want" not in cibles:
            continue
        val = noeud.value
        # `want = {<dict>}[regime]`
        sub = val.value if isinstance(val, ast.Subscript) else val
        if isinstance(sub, ast.Dict):
            return {k.value: v.value for k, v in zip(sub.keys, sub.values)
                    if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)}
    return {}


def test_le_carre_distance_x_elevation_est_complet():
    assert PROBE_LL.exists(), "probe_961_necron_passives.py a disparu"
    want = _dict_want(PROBE_LL.read_text(encoding="utf-8"))
    assert want, "le litteral `want` de `measure_ll` n'est plus lisible a l'AST"
    manquants = REGIMES_ATTENDUS - set(want)
    assert not manquants, (
        "regime(s) de montage disparu(s) : %s. `range2_flat` (distance 2, elevation EGALE) est ce "
        "qui separe l'axe DISTANCE de l'axe ELEVATION -- sans lui l'ecart de #961-r1 reparait comme "
        "un FACTEUR alors qu'il est ADDITIF." % sorted(manquants))
    # Les DEUX distances doivent etre representees a elevation EGALE comme a elevation VARIABLE :
    # c'est cela, le carre.
    assert want["adjacent"] == 1 and want["adjacent_low"] == 1, want
    assert want["range2"] == 2 and want["range2_flat"] == 2, want


def test_le_probe_d_attribution_substitue_des_foyers_qui_existent():
    assert PROBE_ATTR.exists(), "probe_961r1_attribution.py a disparu"
    from engine.runner.operations.damage_ops import ability as ABIL
    from engine.runner.operations.damage import AttackDamageOperation as ADO

    # Les foyers substitues dans les globals de `damage_ops.ability` (cf. `Trace.install`).
    foyers_module = ("attacker_modifiers", "defender_modifiers", "defender_fixed_armor",
                     "apply_pierce_and_modifiers", "apply_all_modifiers",
                     "apply_elevation_bonus", "apply_trench_reduction",
                     "attack_hits_with_modifiers", "HitDamage", "ice_crit_damage_addition")
    absents = [n for n in foyers_module if not hasattr(ABIL, n)]
    assert not absents, (
        "foyer(s) absent(s) des globals de `damage_ops.ability` : %s -- la trace de "
        "`probe_961r1_attribution.py` serait SILENCIEUSEMENT incomplete (le patch ne mordrait "
        "plus), et c'est ce mode de panne qui fait conclure a un facteur." % absents)

    foyers_classe = ("_block_sources", "_crit_params")
    absents_c = [n for n in foyers_classe if not hasattr(ADO, n)]
    assert not absents_c, ("foyer(s) absent(s) d'`AttackDamageOperation` : %s" % absents_c)

    # NON-DEGENERESCENCE du controle lui-meme : la liste ne doit pas etre vide, sinon le test
    # passerait sans rien avoir verifie.
    assert len(foyers_module) >= 8 and len(foyers_classe) == 2


def test_le_source_du_probe_cite_bien_ces_foyers():
    """Le test precedent verifie que les foyers EXISTENT ; celui-ci qu'ils sont bien ceux que le
    probe substitue. Sans lui, on pourrait vider `Trace.install` sans rien faire rougir."""
    src = PROBE_ATTR.read_text(encoding="utf-8")
    for nom in ("apply_pierce_and_modifiers", "apply_all_modifiers", "_crit_params",
                "crit_damage_bonus_from_effects", "HitDamage", "Attack_DidCrit"):
        assert nom in src, "le probe d'attribution ne trace plus `%s`" % nom


if __name__ == "__main__":                                   # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
