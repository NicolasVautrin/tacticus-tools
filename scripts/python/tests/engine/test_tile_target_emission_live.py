"""GARDE LIVE (#343) : les deux routes NonComparable a domaine TUILE EMETTENT bien une cible.

Residu #336-r1 (`docs/rl/case-302-4-population-cible-tuile.md` §5.2) : `1166 AberrantHypermorph` et
`1194 NovaShield` LISAIENT le domaine tuile mais rendaient `{"target": None, ...}`. Le natif, lui,
passe TOUJOURS la cible eligible (`element+0x10` du selector) a
`IdunBattle.AI.ActionGenerators.UnitAction$$.ctor(position, target, abilityType)` -- et une action
d'ability sans cible ni deplacement retombe sur le `FinishUnitTurnMessage` d'
`IdunBattle.AI.InputBuilder$$GenerateInputMessagesFromUnitAction` : le port ne castait donc PAS
l'ability du tout.

Cette garde verrouille, PAR ITEM et sur DEUX bras qui different par la seule position des ennemis :
  1. le natif emet une cible, et cette cible est une TUILE du board ;
  2. le moteur emet la MEME cible, depuis la MEME position ;
  3. la tuile cible du natif CHANGE d'un bras a l'autre -- sans quoi l'accord serait trivial ;
  4. le bras ROUGE (le playbook remis a `target: None`, l'etat d'AVANT #343) DIVERGE.

Le montage (build, greffe de 1194 sur `tauCrisis`, drive des positions, tour IA observe via
`aiDryRunAllUnits`) vit dans `scripts/python/probe_343_tile_target_emission.py` : ce fichier n'en est
que la porte pytest. Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268).
ASCII only.
"""
from __future__ import annotations

import pytest

import probe_343_tile_target_emission as P


@pytest.fixture(scope="module")
def tile_target_case(live_session):
    """Fabrique : `tile_target_case(1166)` -> les deux bras mesures par le probe #343.

    Chaque item monte UN runner isole (build + drive) ; il est DISPOSE au teardown du module."""
    cache: dict = {}

    def _case(item: int) -> dict:
        if item not in cache:
            try:
                cache[item] = P.scenario(item, do_build=True)
            except SystemExit as exc:      # montage non installe -> ROUGE, jamais skip
                pytest.fail("montage tile-target NON INSTALLE (item=%d) : %s" % (item, exc),
                            pytrace=False)
        return cache[item]

    yield _case
    for item in cache:
        P.dispose(item)


def _assert_item(case, item: int) -> None:
    rows = case(item)["rows"]
    tiles = []
    for arm in ("A", "B"):
        r = rows[arm]
        nat_ab, nat_tgt = r["native"]
        assert nat_ab == item, \
            "bras %s : le natif ne propose pas %d (ability=%s) -- montage degenere" % (arm, item, nat_ab)
        # (1) le natif EMET une cible, et c'est une TUILE du board.
        assert nat_tgt is not None, "bras %s : cible NATIVE nulle (item %d)" % (arm, item)
        assert r["native_tile"] is not None, \
            "bras %s : la cible native %s n'est pas une tuile du boardGraph" % (arm, nat_tgt)
        # (2) le moteur emet la MEME cible depuis la MEME position.
        assert r["engine"] == r["native"], \
            "bras %s : moteur %s != natif %s" % (arm, r["engine"], r["native"])
        assert r["engine_to"] == r["native_to"], \
            "bras %s : position moteur %s != natif %s" % (arm, r["engine_to"], r["native_to"])
        # (4) l'etat d'AVANT le correctif diverge -- la garde mesure bien quelque chose.
        assert r["red"] != r["native"], \
            "bras %s : `target=None` donnerait le MEME resultat -> la garde ne prouve rien" % arm
        tiles.append(r["native_tile"])
    # (3) le montage n'a pas degenere en un seul etat.
    assert tiles[0] != tiles[1], \
        "les deux bras choisissent la MEME tuile %s -- accord trivial, pas une mesure" % (tiles[0],)


def test_aberrant_hypermorph_emits_tile_target(tile_target_case):
    """1166 : la cible emise est la TUILE DE SPAWN (`IdunBattle.AI.Playbook.Loki.
    AberrantHypermorphPlaybook$$GetUtility(caster, summonTile)`), porteur NATUREL `genesBiophagus`."""
    _assert_item(tile_target_case, P.ABERRANT)


def test_nova_shield_emits_tile_target(tile_target_case):
    """1194 : la cible emise est le CENTRE marque (`IdunBattleLogic.Entities.Abilities.Active.Loki.
    NovaShieldAbility$$GetMarkedTiles`). Seul porteur du gameconfig = `tauBossRiptide` (npc, hors
    pool) -> l'ability est GREFFEE sur `tauCrisis` (`case-92` §5bis)."""
    _assert_item(tile_target_case, P.NOVASHIELD)
