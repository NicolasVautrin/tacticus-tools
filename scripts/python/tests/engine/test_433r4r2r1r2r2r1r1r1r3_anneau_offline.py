"""#433-r4-r2-r1-r2-r2-r1-r1-r1-r3 -- la branche ANNEAU : le zero porte sur le BINAIRE, pas sur le
registre du port.

Ce que ces crans gardent, et pourquoi chacun peut ROUGIR :

  1. **LA COUVERTURE EST TOTALE** -- chacun des `IdunBattleLogic.Entities.Abilities.Active.*$$.ctor`
     de `data/symbols/<build>/ghidra/functions.tsv` tombe dans l'un des trois ensembles dont le
     masque est LU (registre + attaque normale, `CTORS_RELUS`, presets du `cctor`). Un ctor
     DECOUVERT est une ability dont personne n'a lu le masque : le zero de l'etape suivante
     cesserait d'etre fonde. C'est le cliquet qui survit au prochain build.
  2. **LA LECTURE EST FAITE SUR LE BUILD INSTALLE** -- `CTORS_RELUS` et `PRESETS_CCTOR` sont des
     valeurs relevees au decompile d'UN binaire. Les apparier aux noms d'un AUTRE serait la
     desynchronisation silencieuse que le CLAUDE.md interdit.
  3. **AUCUN PORTEUR DU BIT 9** dans aucune des quatre sources. S'il en apparait un, la branche
     ANNEAU devient ATTEIGNABLE et doit etre CONFRONTEE live -- pas chiffree, pas ajustee.
  4. **LE PORT MIRRORE BIEN L'ANNEAU**, cran SYNTHETIQUE : un masque FABRIQUE portant le bit doit
     donner `d == valeur` exactement, jamais `d <= valeur`. Sans lui, un balayage sur un gisement
     vide serait un inventaire deguise en garde-fou.

RE et mesures : `docs/rl/case-433-r4-r2-r1-r2-r2-r1-r1-r1-tuile-source.md`.
Probe jumeau : `probe_433r4r2r1r2r2r1r1r1r3_anneau_at_range.py`. ASCII only.
"""
from __future__ import annotations

import dataclasses

import pytest

import probe_433r4r2r1r2r2r1r1r1r3_anneau_at_range as P
from engine.runner.abilities.targeting import RANGED_BOOL_FALSE, TargetingRange
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.services import ability_range as AR

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/services/ability_range.py",            # la branche ANNEAU du port
        "scripts/python/engine/runner/abilities/targeting_rule.py",   # le bit 9
        "scripts/python/probe_433r4r2r1r2r2r1r1r1r3_anneau_at_range.py",
    ),
    # `True` : le recensement LIT `data/symbols/<build>/ghidra/functions.tsv`, par un `open` que
    # nul import ne revele -- et c'est justement ce fichier-la qui change au build suivant.
    "build": True,
    "toujours": False,
    "raison": ("le verdict depend de DEUX choses : le port (les chemins) et la population des "
               "ctors du binaire (le build). Omettre `build` ferait taire ce cran exactement "
               "quand une ability neuve apparait -- le seul moment ou il sert."),
}


def test_la_couverture_des_ctors_du_binaire_est_totale():
    r = P.recensement()
    if not r["table_de_symboles_presente"]:
        pytest.fail("NON MESURE : `data/symbols/%s/ghidra/functions.tsv` absent -- ce cran ne rend "
                    "PAS un zero faute d'entree" % r["build_installe"])
    assert r["ctors_recenses"] > 200, (
        "recensement anormalement court (%d ctors) : une table tronquee rendrait un faux vert"
        % r["ctors_recenses"])
    assert r["couverture_totale"], (
        "%d ctor(s) du binaire dont AUCUNE source ne porte le masque -- il faut les RELIRE au "
        "decompile et les inscrire dans `CTORS_RELUS` : %s"
        % (len(r["DECOUVERTS"]), r["DECOUVERTS"][:10]))


def test_la_lecture_a_ete_faite_sur_le_build_installe():
    r = P.recensement()
    assert r["lecture_sur_le_build_installe"], (
        "`CTORS_RELUS` a ete relu sur %s, le build installe est %s : les valeurs sont appariees a "
        "des noms d'un AUTRE binaire -- relire, ne pas supposer stable"
        % (r["build_de_lecture"], r["build_installe"]))


def test_aucune_ability_du_binaire_ne_porte_TargetIsAtRange():
    r = P.bits()
    assert r["masques_registre"] > 100 and r["presets_cctor"] >= 10, (
        "les sources visitees sont vides ou tronquees : %s" % r)
    assert r["gisement_vide"], (
        "la branche ANNEAU a desormais un porteur (%s) : elle devient CONFRONTABLE live -- "
        "monter le cast et mesurer, pas ajuster ce cran" % r["PORTEURS"])


def test_le_port_mirrore_l_anneau_sur_un_masque_synthetique():
    """SYNTHETIQUE par necessite (0 porteur natif) : le bit doit rendre `d == valeur`, pas `d <=`."""
    rng = TargetingRange(only_adjacent=RANGED_BOOL_FALSE, use_range_from_config=False,
                         use_whole_board=False, override_range=3, override_range_func=False)
    anneau = int(TR.TargetIsEnemy) | int(TR.TargetIsAtRange)
    disque = int(TR.TargetIsEnemy)
    for d, dans_anneau in ((1, False), (2, False), (3, True), (4, False)):
        assert AR._zone_contains_distance(anneau, 3, False, False, d) is dans_anneau, (
            "ANNEAU : d=%d devrait etre %s" % (d, dans_anneau))
        assert AR._zone_contains_distance(disque, 3, False, False, d) is (d <= 3), (
            "DISQUE (temoin, meme portee, bit 9 absent) : d=%d devrait etre %s" % (d, d <= 3))
    assert dataclasses.asdict(rng)["override_range"] == 3, "le TargetingRange temoin a derive"
