"""#932 -- GARDE live des deux faces de degat de `Deathwing` (`darkaTerminator` << Baraqiel >>).

Le probe MESURE (`probe_932_deathwing.py`), ce test GARDE : il rejoue les bras du probe et exige
`EGAL`, plus -- et c'est le cran qui compte -- que les MUTANTS MORDENT. Un bras vert dont le mutant
est inerte ne prouve rien : c'est la forme exacte du faux vert que la doctrine nomme.

TROIS bras, choisis pour couvrir les TROIS regimes du natif et rien de plus (le cout live est
reel) :

  * `defense`   -- la face `CreateEffectDamageMalusForDefense` et l'ACCUMULATION du stack
                   (`On(9) & OwnerIsTarget & WasBlock` -> `If(HasEffect, IncreaseEffectLevel,
                   AddEffect)`). Mutant exige : `trigger` (le stack ne monte plus).
  * `chaos`     -- le PREMIER disjoint de `GetDoubleEffectCondition` (`HasTrait(Actor, 0x7ea)`)
                   sur la face DEFENSE. Mutant exige : `double`.
  * `attaque`   -- la face `CreateEffectDamageBonusForAttack` (`get_OwnerIsActor & (IsMeleeAttack |
                   NOT IsNormalAttack)`). Mutant exige : `effet`.

⚠ CHAQUE bras compare AUSSI le NIVEAU (`EffectComponent+0x68`) des deux cotes : deux ports peuvent
rendre le meme degat sur un montage court et diverger sur le stack.

⚠ `verdict == "indisponible"` (montage impossible : session froide, Deep Strike non quitte, cascade
vide) fait ECHOUER le test, il ne le SKIPPE PAS : un montage en echec parti en skip est un vert qui
ment. La cause mesuree est remontee dans le message.

ASCII only dans les sorties (cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_932_deathwing as P                                       # noqa: E402


@pytest.fixture(scope="module")
def rpc():
    return P._mkrpc()


def _jouer(rpc, bras, mutate=None):
    if bras in ("attaque", "attaqueChaos"):
        return P._bras_attaque(rpc, P.BOARD, P.SEED, mutate, False,
                               chaos=(bras == "attaqueChaos"), nom=bras)
    return P._bras_defense(rpc, P.BOARD, P.SEED, mutate, False,
                           att_b=(P.ATT_CHAOS if bras == "chaos" else None),
                           allie_da=(P.ALLIE_DA if bras == "amiDA" else None), nom=bras)


def _exiger_mesure(res, bras):
    assert res.get("verdict") != "indisponible", \
        "bras %s NON MONTE : %s" % (bras, res.get("cause"))
    assert res.get("lignes"), "bras %s : aucune ligne mesuree" % bras


@pytest.mark.parametrize("bras,mutant", [("defense", "trigger"),
                                         ("chaos", "double"),
                                         ("attaque", "effet")])
def test_bras_egal_et_mutant_mord(rpc, bras, mutant):
    """Le bras SAIN doit rendre `EGAL` -- degat coup par coup ET niveau de stack -- et son mutant
    doit rendre `DIVERGE`. Les deux moities comptent : un bras vert dont le mutant reste vert ne
    mesure rien."""
    sain = _jouer(rpc, bras)
    _exiger_mesure(sain, bras)
    ecarts = [l["ecart"] for l in sain["lignes"]]
    assert sain["verdict"] == "EGAL", \
        "bras %s : port != natif (ecarts %s, niveau natif=%s port=%s)" % (
            bras, ecarts, sain.get("niveau_natif_fin"), sain.get("niveau_port_fin"))

    mute = _jouer(rpc, bras, mutate=mutant)
    _exiger_mesure(mute, bras)
    assert mute["verdict"] == "DIVERGE", \
        ("bras %s : le mutant `%s` est INERTE -- il rend le meme resultat que le port sain "
         "(ecarts %s). Un mutant inerte ne valide rien." % (bras, mutant,
                                                            [l["ecart"] for l in mute["lignes"]]))
