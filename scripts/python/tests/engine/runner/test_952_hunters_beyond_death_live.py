"""#952 -- GARDE live du passif `HuntersBeyondDeath` (`spaceHound` << Tjark >>).

Le probe MESURE (`probe_952_hunters_beyond_death.py`), ce test GARDE : il rejoue les QUATRE bras et
exige `EGAL` COUP PAR COUP, plus -- et c'est le cran qui compte -- que les CINQ mutants MORDENT, et
qu'ils mordent SUR LE BON BRAS. Un bras vert dont le mutant est inerte ne prouve rien ; un mutant
qui mord PARTOUT ne prouve pas que les deux pattes sont disjointes.

  * `self`      -- un psyker ennemi frappe TJARK a d = 1 : patte SELF (`create_effect_damage_malus_
                   for_defense`), la SEULE que les agregateurs d'aura ne servent pas ;
  * `aura_pres` -- il frappe l'ALLIE, Tjark a d = 2 : patte AURA, BORNE INCLUSIVE du gate ;
  * `aura_loin` -- MEME attaque, Tjark deplace hors de portee : le malus doit se TAIRE ;
  * `extra`     -- l'autre face du kit : TJARK frappe le psyker (+`extraDmg` contre `Psyker`).

⚠ `verdict == "indisponible"` (montage impossible) fait ECHOUER le test, il ne le SKIPPE PAS : un
montage en echec parti en skip est un vert qui ment. La cause mesuree est remontee dans le message.
Le probe REFUSE aussi de conclure si `aura_pres` et `aura_loin` rendent le MEME total natif -- la
position de Tjark n'aurait alors rien change, et la mesure serait vide.

ASCII only dans les sorties (cp1252).
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        # Le montage et les bras eux-memes.
        "scripts/python/probe_952_hunters_beyond_death.py",
        "scripts/python/probe_r6_round_materialize.py",
        # Le port confronte.
        "scripts/python/engine/entities/effects/loki/hunters_beyond_death.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/entities/effects/__init__.py",
        # Les DEUX foyers qui threadent le contexte des gates (`att_pos` / `owner_pos` / `att_team`
        # posees par #950, `att_traits` par cette tranche) -- COMBAT et PREDICTION.
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/playbook/prediction/_shared.py",
        # Le pipeline que la comparaison coup-par-coup traverse.
        "scripts/python/engine/services/damage_modifiers.py",
        "scripts/python/engine/services/effect_bonus.py",
        "scripts/python/engine/runner/operations/damage_ops/normal.py",
        # Le rejeu offline depuis capture (etat + flux RNG).
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/runner/prng.py",
    ),
    "build": True,
    "toujours": False,
    "raison": (
        "Le seul garde qui confronte ce port au NATIF, et le seul qui exige qu'un MUTANT MORDE "
        "SUR LE BON BRAS (c'est ce qui etablit que les pattes SELF et AURA sont disjointes). "
        "`build: True` : le montage lit les `EffectType` 1172/1190/1191, le trait `Psyker` et le "
        "gameconfig du hash courant -- un renumerotage rend le bras muet, pas faux, et c'est ce "
        "fichier qui doit le voir."
    ),
}

import sys        # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)
from pathlib import Path                                               # noqa: E402

import pytest                                                          # noqa: E402

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from probe_r6_round_materialize import _mkrpc                          # noqa: E402
import probe_952_hunters_beyond_death as P                             # noqa: E402


@pytest.fixture(scope="module")
def mesure_saine():
    return P.mesurer(_mkrpc(), P.BOARD, P.SEED, None, False)


def _exiger_mesure(res, quoi):
    assert res.get("verdict") != "indisponible", \
        "%s NON MONTE : %s" % (quoi, res.get("cause"))
    assert res.get("lignes"), "%s : aucune ligne mesuree" % quoi


def test_les_quatre_bras_sont_EGAUX(mesure_saine):
    """Coup par coup, natif == port sur les QUATRE bras -- et la position de Tjark doit avoir
    CHANGE le resultat natif entre `aura_pres` et `aura_loin` (sinon la mesure est vide, et le
    probe l'a deja refusee)."""
    _exiger_mesure(mesure_saine, "bras sain")
    assert mesure_saine["verdict"] == "EGAL", \
        "port != natif : %s" % [(l["bras"], l["natif"], l["port"], l["ecart"],
                                 l["natif_hits"], l["port_hits"])
                                for l in mesure_saine["lignes"]]
    assert mesure_saine["delta_natif_pres_loin"] != 0


def test_les_trois_effets_sont_MATERIALISES_sous_leur_classe(mesure_saine):
    """Avant #952 les trois instances etaient POSEES (captees par `decisionView.effects`) et
    materialisees en `BaseEffect` nu -- donc INERTES. Ce garde exige la CLASSE, pas la presence."""
    _exiger_mesure(mesure_saine, "bras sain")
    portes = {nom: cls for l in mesure_saine["lignes"]
              for nom, _et, cls in l["effets_tjark"]}
    assert portes.get("HuntersBeyondDeath") == "HuntersBeyondDeathEffect"
    assert portes.get("HuntersBeyondDeath_ExtraDamage") == "HuntersBeyondDeathExtraDamageEffect"
    assert portes.get("HuntersBeyondDeathPsykerSuppression") \
        == "HuntersBeyondDeathPsykerSuppressionEffect"


#: mutant -> les bras qu'il DOIT faire diverger (et, par complement, ceux ou il doit etre INERTE).
#: C'est cette table qui etablit que les DEUX pattes de 1190 sont DISJOINTES : `m_self` ne doit
#: mordre QUE `self`, `m_aura` QUE `aura_pres`.
MUTANTS = [
    ("m_effet", {"self", "aura_pres"}),     # l'effet 1190 hors registre -> les DEUX pattes tombent
    ("m_self", {"self"}),                   # patte SELF neutralisee
    ("m_aura", {"aura_pres"}),              # patte AURA neutralisee
    ("m_dist", {"aura_pres"}),              # borne STRICTE au lieu d'inclusive (Tjark est a d == 2)
    ("m_extra", {"extra"}),                 # la face ATTAQUANT 1172 hors registre
]


@pytest.mark.parametrize("mutant,attendus", MUTANTS)
def test_le_mutant_mord_et_SUR_LE_BON_BRAS(mutant, attendus):
    res = P.mesurer(_mkrpc(), P.BOARD, P.SEED, mutant, False)
    _exiger_mesure(res, "mutant %s" % mutant)
    diverges = {l["bras"] for l in res["lignes"] if l["verdict"] == "DIVERGE"}
    assert diverges == attendus, \
        ("mutant `%s` : bras divergents %s, attendu %s. Un mutant INERTE ne valide rien ; un "
         "mutant qui mord AILLEURS dit que les foyers ne sont pas ceux qu'on croit. Lignes : %s"
         % (mutant, sorted(diverges), sorted(attendus),
            [(l["bras"], l["natif"], l["port"], l["ecart"]) for l in res["lignes"]]))
