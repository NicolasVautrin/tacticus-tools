"""#498-r3 -- LIVE : la tete `IsDisplaceable` s'applique AUSSI au `SwitchPosition` (case 5).

CE QUE CE FICHIER GARDE, et pourquoi chaque bras est necessaire

`IdunBattle.Operations.DisplaceUnitOperation$$Execute` teste `IdunBattle.Entities.UnitExtensions$$
IsDisplaceable(target)` AVANT son `switch(direction)` -- donc pour ses SEPT cases, y compris le
case 5 (`SwitchPosition`). `SwitchPositionOperation` ne portait AUCUNE des quatre conditions : le
port echangeait les tuiles d'une unite que le natif refuse de deplacer. C'est une degradation
PERMISSIVE, silencieuse (ni erreur ni crash), donc invisible en self-play.

Le montage (`probe_498r3_switch_position_gate.py`) reprend celui de #287 et lui AJOUTE une seule
chose : `BigTarget` dans `BC.Units[thousSorcerer].Traits`, par seed BC custom. Sans cette ecriture,
la condition serait trivialement satisfaite sur toute configuration atteignable de ce montage, et
l'accord ne prouverait RIEN.

TROIS BRAS :
  * `base` -- TEMOIN NON DEGENERE : le natif ECHANGE bien. Sans lui, un refus systematique du port
    (ou un cast qui echoue) passerait pour un gate qui fonctionne.
  * `big`  -- le natif N'ECHANGE PAS. C'est LA mesure.
  * MUTANT -- le meme etat pre-cast rejoue offline avec le foyer force a `True` (= l'etat d'AVANT
    #498-r3) ECHANGE. C'est l'A/B causal : il interdit d'attribuer l'accord du bras `big` a autre
    chose que ce gate.

Mesure du 2026-08-07 (board MC1_67, seed 49831) : traits natifs de l'allie
`[4, 16, 1002, 1041, 2026]` (base) vs `[4, 16, 1002, 1017, 1041, 2026]` (big) -- `1017` =
`UnitTrait.BigTarget`, ajoute par le seed BC et LU par le natif.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_498r3_switch_position_gate as P                 # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait      # noqa: E402


@pytest.fixture(scope="module")
def bras(live_session):
    """Les deux bras, montes UNE fois pour tout le fichier.

    Montage NON installe => ECHEC, jamais skip (#455/#268) : un skip ici serait un vert qui ment."""
    custom = P.LOGS / "seed_bc_498r3_bigtarget_test.json"
    w = P.write_seed_bc_with_trait(custom, P.ALLY_VID, P.TRAIT_AJOUTE)
    assert w["touched"] == 1, "seed BC custom : l'allie n'a pas ete touche"
    cache = {}

    def _get(name):
        if name not in cache:
            r = P._arm(name, None if name == "base" else custom, keep=False)
            if r.get("error"):
                pytest.fail("montage #498-r3 NON INSTALLE (%s) : %s" % (name, r["error"]))
            cache[name] = r
        return cache[name]
    return _get


def test_le_trait_ajoute_est_LU_par_le_natif(bras):
    """Sans ce controle, une ecriture de seed BC silencieusement perdue rendrait le bras `big`
    identique au bras `base` -- et les deux verdicts suivants seraient vides de sens."""
    base, big = bras("base"), bras("big")
    assert int(UnitTrait.BigTarget) not in base["traits_ally_natif"]
    assert int(UnitTrait.BigTarget) in big["traits_ally_natif"], (
        "traits natifs de l'allie : %s" % (big["traits_ally_natif"],))


def test_temoin_le_natif_echange_quand_la_cible_est_deplacable(bras):
    r = bras("base")
    assert r["live"]["ok"], "le natif a REFUSE le cast : montage invalide, aucune mesure"
    assert r["live"]["switched"] is True, (
        "le natif n'a pas echange dans le bras temoin : le bras `big` ne mesurerait rien")
    assert r["offline"]["switched"] is True


def test_le_natif_refuse_le_switch_sur_une_cible_BigTarget(bras):
    r = bras("big")
    assert r["live"]["ok"], "le cast lui-meme doit rester accepte (c'est le SWITCH qui est gate)"
    assert r["live"]["switched"] is False, (
        "le natif a echange les positions d'une unite BigTarget : pre=%s post=%s"
        % (r["live"]["pre"], r["live"]["post"]))
    assert r["offline"]["switched"] is False, "le port a echange la ou le natif refuse"


def test_ab_causal_le_port_d_AVANT_le_fix_echangeait(bras):
    """MUTANT = `unit_extensions_is_displaceable -> True`, soit exactement l'etat d'avant #498-r3
    sur ce site. S'il n'echangeait pas non plus, la divergence n'aurait jamais existe et ce
    fichier garderait du vide."""
    big = bras("big")
    assert big["offline_mutant"]["switched"] is True, (
        "le mutant pre-fix n'echange pas : la divergence mesuree n'est pas attribuable au gate")
    base = bras("base")
    assert base["offline_mutant"]["switched"] is True, (
        "le gate ne doit RIEN changer quand la cible est deplacable")
