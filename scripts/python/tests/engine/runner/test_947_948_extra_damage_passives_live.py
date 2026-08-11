"""#947 / #948 -- GARDE live des DEUX passifs `_ExtraDamageEffect`.

Le probe MESURE (`probe_947_948_extra_damage_passives.py`), ce test GARDE : il rejoue les bras et
exige `EGAL`, plus -- et c'est le cran qui compte -- que les MUTANTS MORDENT. Un bras vert dont le
mutant est inerte ne prouve rien.

DEUX bras, cinq mutants, chacun visant UN etage precis :

  * `enmity`      -- DEUX geometries CALCULEES puis ASSERTIONNEES (units=1/DA=0 puis units=4/DA=2)
                     sur une tuile a 6 voisins JOUABLES. Les deux faces du passif y sont exercees
                     ensemble ; le probe REFUSE de conclure si les deux regimes rendent le meme
                     total natif (mesure vide).
                     Mutants : `en_da` (compteur d'amis DARK ANGELS a 0 -> la face ADDITIVE tombe),
                     `en_units` (compteur d'unites adjacentes a 0 -> la face POURCENTAGE tombe).
  * `headclaimer` -- DEUX kills de HERO puis une attaque de mesure. Le verdict porte sur TROIS
                     observables a la fois : le degat total, le NOMBRE de coups (`1029` ajoute
                     `extraHit x level` coups) et les NIVEAUX des deux stacks.
                     Mutants : `hc_effet` (magnitude de `1028`), `hc_hits` (les coups de `1029`),
                     `hc_trigger` (l'accumulation elle-meme).

⚠ `verdict == "indisponible"` (montage impossible) fait ECHOUER le test, il ne le SKIPPE PAS : un
montage en echec parti en skip est un vert qui ment. La cause mesuree est remontee dans le message.

ASCII only dans les sorties (cp1252).
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        # Le montage et les bras eux-memes.
        "scripts/python/probe_947_948_extra_damage_passives.py",
        # Le port confronte : les deux familles d'effets et le trigger d'accumulation.
        "scripts/python/engine/entities/effects/loki/head_claimer.py",
        "scripts/python/engine/entities/effects/loki/enmity_for_the_unworthy.py",
        "scripts/python/engine/runner/operations/triggers/loki/head_claimer.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        # Le SUBSTRAT des deux compteurs d'Enmity et ses deux foyers.
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/playbook/scene.py",
        # Le pipeline que la comparaison coup-par-coup traverse (degat ET coups).
        "scripts/python/engine/services/damage_modifiers.py",
        "scripts/python/engine/services/effect_bonus.py",
        "scripts/python/engine/services/attack_hits_formula.py",
        "scripts/python/engine/runner/operations/damage_ops/normal.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        # Le rejeu offline depuis capture (etat + flux RNG).
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/runner/prng.py",
    ),
    "build": True,
    "toujours": False,
    "raison": (
        "Le seul garde qui confronte ces deux ports au NATIF, et le seul qui exige qu'un MUTANT "
        "MORDE. `build: True` : le montage lit les `EffectType` 1028/1029/1399/1400, les traits "
        "`Hero`/`Steppable`/`Object` et le gameconfig du hash courant -- un renumerotage rend le "
        "bras muet, pas faux, et c'est ce fichier qui doit le voir."
    ),
}

import sys        # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)
from pathlib import Path                                               # noqa: E402

import pytest                                                          # noqa: E402

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_947_948_extra_damage_passives as P                        # noqa: E402


@pytest.fixture(scope="module")
def rpc():
    return P._mkrpc()


def _jouer(rpc, bras, mutate=None):
    fn = P._bras_enmity if bras == "enmity" else P._bras_headclaimer
    return fn(rpc, P.BOARD, P.SEED, mutate, False)


def _exiger_mesure(res, bras, mutate=None):
    assert res.get("verdict") != "indisponible", \
        "bras %s (mutate=%s) NON MONTE : %s" % (bras, mutate, res.get("cause"))
    assert res.get("lignes"), "bras %s : aucune ligne mesuree" % bras


@pytest.mark.parametrize("bras,mutants", [
    ("enmity", ["en_da", "en_units"]),
    ("headclaimer", ["hc_effet", "hc_hits", "hc_trigger"]),
])
def test_bras_egal_et_mutants_mordent(rpc, bras, mutants):
    """Le bras SAIN doit rendre `EGAL` -- degat coup par coup, nombre de COUPS et NIVEAUX -- et
    CHACUN de ses mutants doit rendre `DIVERGE`. Les deux moities comptent."""
    sain = _jouer(rpc, bras)
    _exiger_mesure(sain, bras)
    assert sain["verdict"] == "EGAL", \
        "bras %s : port != natif -- lignes=%s niveaux(natif=%s port=%s) coups(%s/%s)" % (
            bras, [(l["natif"], l["port"], l["ecart"]) for l in sain["lignes"]],
            sain.get("niveaux_natif"), sain.get("niveaux_port"),
            sain.get("coups_natif"), sain.get("coups_port"))
    for m in mutants:
        mute = _jouer(rpc, bras, mutate=m)
        _exiger_mesure(mute, bras, m)
        assert mute["verdict"] == "DIVERGE", \
            ("bras %s : le mutant `%s` est INERTE -- il rend le meme resultat que le port sain "
             "(ecarts %s, coups %s/%s, niveaux %s). Un mutant inerte ne valide rien."
             % (bras, m, [l["ecart"] for l in mute["lignes"]],
                mute.get("coups_natif"), mute.get("coups_port"), mute.get("niveaux_port")))
