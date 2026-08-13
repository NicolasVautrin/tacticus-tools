"""#1003 -- CONFRONTATION LIVE des deux reliques Death Guard : NATIF <-> PORT.

L'observable est le volet INCONDITIONNEL des deux abilities -- `AddEffect(0x4dc = 1244
Contaminated, targets = TargetTiles@DSLSelectors+0x78)` -- parce que c'est le seul qui ne depend
d'aucun etat prealable. Le volet ATTAQUE d'`OrbsOfDecay` exige un voisin dont l'armure est reduite
de PLUS de 30 % de sa base ; il est garde OFFLINE (predicat + selecteur, cliquet
`test_1003_reliques_death_guard_offline.py`) et sa confrontation LIVE reste NON COUVERTE -- dit
dans le rapport de la tranche, pas passe sous silence.

TROIS BRAS PAR RELIQUE, chacun tombant pour une raison DIFFERENTE (montage :
`probe_1003_reliques_death_guard.py`) :
  * POSITIF : relique equipee -> la tuile de la cible porte `Contaminated` apres l'attaque ;
  * TEMOIN  : MEME montage, MEME attaque, SANS relique -> aucune contamination. Sans lui, un
              `Contaminated` observe ne prouverait rien (le confond `OnToxicDamageAbility` 1203
              pose le MEME effet sur la MEME tuile -- il est ECARTE par le choix du porteur, dont
              l'arme de melee n'est pas `Toxic`, mais c'est ce bras qui le VERIFIE) ;
  * PORT    : la MEME capture pre-attaque, rejouee OFFLINE, contamine la MEME tuile dans le bras
              positif et RIEN dans le temoin.

⚠ Montage non installe => ECHEC, jamais skip (#268).

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

_PYDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PYDIR not in sys.path:
    sys.path.insert(0, _PYDIR)

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LE MONTAGE de ce fichier.
        "scripts/python/probe_1003_reliques_death_guard.py",
        # LES DEUX MIRRORS et leur registre.
        "scripts/python/engine/runner/operations/triggers/loki/orbs_of_decay.py",
        "scripts/python/engine/runner/operations/triggers/loki/lakrimae.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/core.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/ability.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        # LE RAIL de la relique EQUIPEE (#357/#363) -- sans lui le port est inerte.
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        # LA FEUILLE qui pose l'effet de TUILE et son operation.
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effect_type.py",
        # LE MONTAGE #237 de la relique.
        "scripts/python/rl_duel.py", "scripts/python/catalog_inject.py",
    ),
    "build": True,
    "toujours": False,
    "raison": (
        "Ce fichier confronte au NATIF le volet contamination des deux reliques Death Guard "
        "`OrbsOfDecay` (1465) et `Lakrimae` (1541). Les chemins listes sont ceux dont une "
        "modification peut faire changer un verdict : le montage, les deux mirrors, leur registre, "
        "les deux vecteurs de dispatch, le rail de la relique EQUIPEE et la feuille `AddEffect`."),
}

import probe_1003_reliques_death_guard as P                                  # noqa: E402


@pytest.fixture(scope="module")
def cas(build_runner, rpc):
    """Fabrique : `cas("Lakrimae", True)` -> le releve du montage. Portee MODULE (un build par
    couple relique/regime, quatre au total)."""
    cache: dict = {}

    def _case(relic_key: str, avec_relique: bool) -> dict:
        key = (relic_key, bool(avec_relique))
        if key not in cache:
            r = P.run(rpc, relic_key, avec_relique, build_runner=build_runner, keep=True)
            if not r.get("ok"):
                pytest.fail("montage #1003 NON INSTALLE (%s, relique=%s) : %s"
                            % (relic_key, avec_relique, r.get("why")))
            cache[key] = r
        return cache[key]

    return _case


@pytest.mark.parametrize("relic_key", ["Lakrimae", "OrbsOfDecay"])
def test_le_natif_contamine_la_tuile_de_la_cible(cas, relic_key):
    """POSITIF -- `AddEffect(1244 Contaminated, targets = TargetTiles@+0x78)`, mesure sur le NATIF.

    La tuile de la CIBLE doit apparaitre dans `tileMeta.tiles[].effects` apres l'attaque et pas
    avant. C'est l'observable du volet INCONDITIONNEL des deux abilities."""
    r = cas(relic_key, True)
    assert (r.get("attack_ack") or {}).get("ok") is not False, (
        "l'attaque normale a ete REFUSEE par le natif : %r -- le bras est VIDE" % (r["attack_ack"],))
    assert r["tuile_cible"] is not None, "tuile de la cible introuvable -- montage a reparer"
    assert r["tuile_cible"] in r["natif_nouvelles_tuiles"], (
        "NATIF : la tuile de la cible (%s) n'a PAS ete contaminee. Nouvelles tuiles contaminees : "
        "%r (avant : %r)" % (r["tuile_cible"], r["natif_nouvelles_tuiles"], r["tuiles_avant"]))


@pytest.mark.parametrize("relic_key", ["Lakrimae", "OrbsOfDecay"])
def test_sans_la_relique_la_meme_attaque_ne_contamine_rien(cas, relic_key):
    """TEMOIN -- MEME porteur, MEME cible, MEME attaque, SANS `--equip-relic`.

    C'est ce bras qui exclut le confond `OnToxicDamageAbility` (1203), qui pose LE MEME effet 1244
    sur LA MEME tuile quand le coup porte le trait de profil `OnToxic`. Les deux porteurs ont ete
    choisis pour que leur arme de melee ne soit pas `Toxic` (`Power` / `Plasma`, LU au gameconfig) --
    ce bras le VERIFIE au lieu de le supposer. Sans lui, le bras positif serait un vert que rien ne
    fait rougir."""
    r = cas(relic_key, False)
    assert (r.get("attack_ack") or {}).get("ok") is not False, (
        "l'attaque normale du TEMOIN a ete REFUSEE : %r -- le bras est VIDE" % (r["attack_ack"],))
    assert r["natif_nouvelles_tuiles"] == [], (
        "TEMOIN : la meme attaque SANS relique a contamine %r. Ce n'est donc pas la relique qui "
        "contamine -- soit un autre poseur fire (1203 ?), soit le montage est faux"
        % (r["natif_nouvelles_tuiles"],))


@pytest.mark.parametrize("relic_key", ["Lakrimae", "OrbsOfDecay"])
def test_le_port_contamine_la_meme_tuile(cas, relic_key):
    """PORT -- la MEME capture pre-attaque rejouee OFFLINE contamine la MEME tuile.

    Le rail de la relique EQUIPEE (#357/#363) doit avoir seede `UnitContext.tertiary_ability` :
    sans lui le trigger n'est meme pas inscrit, et le port serait inerte EN SILENCE."""
    r = cas(relic_key, True)
    port = r["port"]
    assert "error" not in port, port
    assert port["tertiary"] == P.CAS[relic_key][1], (
        "le rail #357 n'a pas seede `tertiary_ability` (lu : %r) -- le trigger n'est pas inscrit, "
        "et le port serait inerte SANS erreur" % (port["tertiary"],))
    assert port["events"] >= 1, (
        "PORT : le trigger de la relique n'a pas fire (%r)" % (port,))
    assert r["tuile_cible"] in port["nouvelles_tuiles"], (
        "PORT : la tuile de la cible (%s) n'est pas contaminee offline. Nouvelles tuiles : %r"
        % (r["tuile_cible"], port["nouvelles_tuiles"]))
    # ACCORD des deux cotes, sur le MEME ensemble.
    assert set(port["nouvelles_tuiles"]) == set(r["natif_nouvelles_tuiles"]), (
        "DESACCORD natif/port sur les tuiles contaminees : natif %r vs port %r"
        % (r["natif_nouvelles_tuiles"], port["nouvelles_tuiles"]))


@pytest.mark.parametrize("relic_key", ["Lakrimae", "OrbsOfDecay"])
def test_sans_la_relique_le_port_est_inerte_lui_aussi(cas, relic_key):
    """CONTRE-EPREUVE cote PORT : pas de relique -> pas de `tertiary_ability`, pas de trigger,
    aucune tuile contaminee. Le port ne doit pas etre devenu PERMISSIF."""
    port = cas(relic_key, False)["port"]
    assert "error" not in port, port
    assert port["tertiary"] is None, (
        "sans `--equip-relic`, `tertiary_ability` devrait rester None, lu %r" % (port["tertiary"],))
    assert port["events"] == 0 and port["nouvelles_tuiles"] == [], (
        "PORT : le trigger a fire SANS relique (%r) -- inscription permissive" % (port,))
