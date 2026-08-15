"""#175-r3 -- `get_CanBeImmuneTo` ECRIT PAR LE `.ctor` : la classe qui vaut `true`, et le port.

## CE QUE CE FICHIER GARDE

`probe_175r2_can_be_immune_to.py` REFUSE de conclure pour **49** classes : leur getter est
`movzx eax, byte ptr [rcx+0x480] ; ret`, donc la valeur n'est pas une constante de classe mais un
CHAMP D'INSTANCE ecrit par le `.ctor`. Le port, lui, modelise `can_be_immune_to` comme un attribut
de CLASSE -- ce qui est exact SI et SEULEMENT SI toutes les instances d'une meme classe passent la
meme valeur, ce qui est le cas ici (chaque `.ctor` passe un LITTERAL).

`probe_175r3_can_be_immune_to_ctor.py` va lire ce litteral. Mesure (build `t6dpr4k06g`) :
**1 classe a `canBeImmuneTo = 1`** -- `Loki.ChampionOfTheFeast_ReduceArmorEffect` --, 32 a `0`,
16 INDETERMINEES (`.ctor` fondu par l'ICF, ou `.ctor` FORWARDER dont la valeur vient de l'appelant).

L'etage 1 est OFFLINE et tourne partout ; l'etage 2 lit le jeu et se DIT non mesure sans lui. Ce
fichier ne peut donc jamais rendre `passed == 0 and skipped > 0` (le regime que #455 fait rougir).

ASCII only (console cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.entities.effects.base import BaseEffect                            # noqa: E402
from engine.entities.effects.loki.champion_of_the_feast import (               # noqa: E402
    ChampionOfTheFeastReduceArmorEffect)
from engine.entities.effects.loki.status import ContaminatedEffect             # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_175r3_can_be_immune_to_ctor.py",
        "scripts/python/probe_175r2_can_be_immune_to.py",
        # Le defaut du port et la classe qui le contredit.
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/loki/champion_of_the_feast.py",
        "scripts/python/engine/entities/effects/loki/status.py",
        # Le CONSOMMATEUR du drapeau : le gate de pose.
        "scripts/python/engine/runner/operations/effects.py",
        # L'entree versionnee de `probe_175r2` : elle change au changement de JEU.
        "data/symbols/*/metadata/can_be_immune_to.tsv",
    ),
    # L'etage 2 lit `GameAssembly.dll` + `global-metadata.dat` du build courant.
    "build": True,
    "toujours": False,
    "raison": ("Le litteral `canBeImmuneTo` de chaque `.ctor` est LU dans le binaire ; le defaut du "
               "port et la seule classe a `true` sont figes ici. Tout changement de build, du "
               "defaut de `BaseEffect` ou du gate de pose peut retourner le verdict."),
}


# ------------------------------------------------------------------- etage 1 : le PORT (offline)

def test_le_defaut_du_port_reste_FAUX():
    """`BaseEffect$$get_CanBeImmuneTo` = `xor al,al ; ret`. Le retourner ferait mordre le gate
    d'immunite sur les ~450 classes qui l'heritent."""
    assert BaseEffect.can_be_immune_to is False


def test_ChampionOfTheFeast_ReduceArmor_porte_le_VRAI():
    """LA classe que la mesure #175-r3 a trouvee, et la SEULE des 49.

    Son `.ctor` appelle `AStatModifierEffect..ctor(..., canBeImmuneTo = 1, ...)` (`mov r9b,0x1`),
    la ou les 32 autres classes lues passent `0` (`xor r9d,r9d`)."""
    assert ChampionOfTheFeastReduceArmorEffect.can_be_immune_to is True


def test_le_gate_d_immunite_MORD_alors_qu_il_ne_mordait_pas():
    """LA CONSEQUENCE OBSERVABLE, pas seulement l'attribut. `BaseEffect$$EntityIsImmuneToEffect` =
    `HasTrait(entity, UnitTrait.Immune) && CanBeImmuneTo` : avec le defaut `False`, une cible
    `Immune` recevait quand meme le malus d'armure."""
    e = ChampionOfTheFeastReduceArmorEffect("ChampionOfTheFeast_ReduceArmor")
    assert e.entity_is_immune_to_effect(["Immune"]) is True
    assert e.entity_is_immune_to_effect([]) is False
    # Contre-temoin NON DEGENERE : une classe au defaut ne mord PAS sur la meme entree.
    nu = BaseEffect("X")
    assert nu.entity_is_immune_to_effect(["Immune"]) is False
    # et une classe deja connue a `true` (#175-r2) mord, elle aussi -- la mecanique est la meme.
    assert ContaminatedEffect("Contaminated").entity_is_immune_to_effect(["Immune"]) is True


# --------------------------------------------------------- etage 2 : la MESURE (lit le binaire)

def test_la_mesure_du_binaire_designe_EXACTEMENT_cette_classe():
    """Confronte l'attribut du port a ce que le `.ctor` passe REELLEMENT, sur le build installe.

    ⚠ Sans le jeu, on SKIPPE en le disant -- un `0 classe a true` faute de binaire serait un vert
    qui ment (c'est exactement la faute que `probe_224` avait commise avec ses VA en dur)."""
    import probe_175r3_can_be_immune_to_ctor as P
    res = P.mesurer()
    if res is None:
        pytest.skip("NON MESURE : jeu non installe / table de symboles absente (ce n'est PAS "
                    "'aucune classe a true')")
    vrais = sorted(n for n, r in res.items() if r["valeur"] == 1)
    assert vrais == ["IdunBattle.Entities.Effects.Loki.ChampionOfTheFeast_ReduceArmorEffect"], \
        ("le jeu de classes a `canBeImmuneTo = 1` a CHANGE : %s -- porter les nouvelles, "
         "retirer celles qui sont tombees" % vrais)
    # Le gisement est EXERCE : sans classes a `0`, l'unicite du `1` ne dirait rien.
    assert sum(1 for r in res.values() if r["valeur"] == 0) >= 20, \
        "trop peu de classes lues a `0` -- la lecture du prologue a probablement decroche"


def test_les_INDETERMINEES_sont_NOMMEES_jamais_rabattues_sur_zero():
    """Un `.ctor` fondu par l'ICF ou un FORWARDER (`canBeImmuneTo` en parametre) n'a pas de
    litteral a lire. Le probe doit le DIRE -- les compter comme `0` fabriquerait un faux vert
    exactement la ou la mesure manque."""
    import probe_175r3_can_be_immune_to_ctor as P
    res = P.mesurer()
    if res is None:
        pytest.skip("NON MESURE : jeu non installe / table de symboles absente")
    indet = {n: r["forme"] for n, r in res.items() if r["valeur"] is None}
    assert indet, "aucune INDETERMINEE -- le tri-etat de ce probe n'est plus exerce"
    for n, forme in indet.items():
        assert forme and forme != "0", (n, forme)      # chacune porte SA raison
