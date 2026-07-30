"""MassDriverAccelerator (1222, Kimm `votanChampion`) -- terme `CalculateCustomUtility`, LIVE.

CE QUE CE TEST GARDE, et pourquoi il ne peut pas passer par accident :

A. **Le terme natif est IDENTIQUEMENT NUL.** `IdunBattle.AI.Playbook.Loki.MassDriverAcceleratorPlaybook$$CalculateCustomUtility`
   evalue `MassDriverAcceleratorAbility$$GetBuffTargets` = `Owner + AdjacentFriends(Owner, 1, 3)`
   contre un `AbilityEntities` dont le champ `owner` est NULL (`AbilityEntities$$.ctor` ecrit
   `+0x18 = owner` ; `IdunBattle.Entities.Selectors.OwnerSelector$$Select` lit `+0x18` et rend une
   liste VIDE) -> `Math.Max(0, 0 - 1) = 0`. Le natif ne bouge donc PAS quand le nombre d'allies
   adjacents au caster passe de 0 a 1 a 2 (`test_native_is_invariant_across_adjacency_arms`).
B. **Le montage EST sensible** -- sans quoi A serait un angle mort et non une mesure. Deux gardes :
   * `test_montage_brackets_the_native_flip` : entre les deux valeurs de `Damage` du montage, le
     natif CHANGE d'action -- le duel 1222 / attaque normale est donc bien a l'equilibre ;
   * `test_inherited_formula_would_have_been_visible` : le moteur PORTANT la formule heritee de
     `case-27` (`W x |amis adjacents|`, W = 5) DIVERGE du natif des n=1. C'est la mutation
     adversariale du mecanisme sous test, pas un raisonnement.
C. **Le port rend 0 quelle que soit l'adjacence** et le moteur suit le natif dans les 6 cellules.

CONFONDS NEUTRALISES (tous MESURES, cf. la docstring de `probe_27_r1_massdriver_custom`) :
  * Kimm reste sur sa tuile de SPAWN -- un `act move` consomme son mouvement et rend 1222 illegale ;
  * la cible est a distance 2 (1222 refuse une cible adjacente) et n'a AUCUN ennemi adjacent, ce qui
    rend inerte le residu `MassDriverAcceleratorPlaybook$$MakeDamagePredictions` ;
  * les deux allies porteurs d'aura de degat sont FIGES loin dans tous les bras ;
  * le passif `ModifiedExoarmour` est retire du seed BC : son playbook porte un terme de TUILE
    (`ModifiedExoarmour_LikesMovingPerTile`) que le port n'a pas. Le bras `--passive-on` du probe
    rejoue A avec le kit REEL et le natif y est invariant aussi.

Aucun scalaire de gameplay n'est fige : le poids vient de la BC re-synthetisee, l'encadrement des
`pairUtility` natives du montage.

PORTEUR HORS POOL : `votanChampion` est absent du seed BC capture -> injecte par `catalog_inject.py`
dans une COPIE sous `logs/` (jamais le seed partage).

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_27_r1_massdriver_custom as AB                  # noqa: E402

MDA = AB.MDA
DAMAGES = (AB.D_LOW, AB.D_HIGH)


@pytest.fixture(scope="module")
def rows():
    try:
        AB.ensure_seed_bcs()
    except Exception as exc:                                # noqa: BLE001
        pytest.skip("catalog_inject KO : porteur votanChampion non injectable (%s)" % exc)
    data, rid = AB.scenario(list(DAMAGES), with_passive=False)
    try:
        yield data
    finally:
        if rid is not None:
            try:
                AB.L._rpc("disposeRunner", [{"runnerId": rid}])
            except Exception:                               # noqa: BLE001
                pass


def test_adjacency_arms_are_actually_distinct(rows):
    """Les trois bras posent bien 0 / 1 / 2 allies ADJACENTS au caster. Sans cela, l'invariance du
    natif serait triviale et ne conclurait rien (deux configurations a ecart NUL ne prouvent rien)."""
    for d in DAMAGES:
        got = [rows[(d, n)]["n_adj"] for n in (0, 1, 2)]
        assert got == [0, 1, 2], (
            "Damage=%d : amis adjacents mesures %s != [0, 1, 2] -- le montage n'a pas pose "
            "les appats, l'A/B ne varie rien" % (d, got))


def test_montage_brackets_the_native_flip(rows):
    """Le duel 1222 vs attaque normale est A L'EQUILIBRE : le natif change d'action entre les deux
    valeurs de `Damage`. C'est ce qui rend un ecart de 5 points d'utilite OBSERVABLE."""
    lo = rows[(AB.D_LOW, 0)]["native"]
    hi = rows[(AB.D_HIGH, 0)]["native"]
    assert lo != hi, (
        "le natif rend la MEME action a Damage=%d et %d (%s) -- montage hors zone de bascule, "
        "il ne peut RIEN mesurer" % (AB.D_LOW, AB.D_HIGH, lo))
    assert lo == MDA, "a Damage=%d le natif devrait preferer 1222, il rend %s" % (AB.D_LOW, lo)


def test_native_is_invariant_across_adjacency_arms(rows):
    """LE VERDICT : le natif rend la MEME action a n=0, n=1 et n=2. Le terme custom de 1222 est nul."""
    for d in DAMAGES:
        got = [rows[(d, n)]["native"] for n in (0, 1, 2)]
        assert len(set(got)) == 1, (
            "Damage=%d : natif(n=0,1,2) = %s -- l'action CHANGE avec le nombre d'allies adjacents, "
            "donc le terme custom n'est PAS nul et le port (0) est faux" % (d, got))


def test_ported_term_is_zero_whatever_the_adjacency(rows):
    """Mirror du natif : `Owner` etant NULL, `Math.Max(0, Count - 1)` vaut 0 en toute configuration."""
    for d in DAMAGES:
        for n in (0, 1, 2):
            v = rows[(d, n)]["ported"]
            assert v == 0.0, (
                "Damage=%d n=%d : terme porte = %r != 0.0 -- le port applique un bonus que le natif "
                "n'applique pas" % (d, n, v))


def test_engine_matches_native_on_all_cells(rows):
    """Accord moteur <-> natif dans les 6 cellules (2 Damage x 3 configurations d'adjacence)."""
    bad = [(d, n, rows[(d, n)]["engine"], rows[(d, n)]["native"])
           for d in DAMAGES for n in (0, 1, 2)
           if rows[(d, n)]["engine"] != rows[(d, n)]["native"]]
    assert not bad, "cellules divergentes (Damage, n, moteur, natif) : %s" % bad


def test_inherited_formula_would_have_been_visible(rows):
    """MUTATION ADVERSARIALE : rejoue la decision moteur avec la formule HERITEE de `case-27`
    (`W x |amis adjacents|`). Elle DOIT diverger du natif -- sinon le montage ne distinguerait pas
    les deux hypotheses et l'invariance mesuree ne prouverait rien."""
    seen = [(d, n) for d in DAMAGES for n in (1, 2)
            if rows[(d, n)]["engine_mutated"] != rows[(d, n)]["native"]]
    assert seen, (
        "la formule heritee `W x n` rend EXACTEMENT le meme choix que le natif dans tous les bras : "
        "le montage ne discrimine pas les deux hypotheses, il faut le re-calibrer avant de conclure")
