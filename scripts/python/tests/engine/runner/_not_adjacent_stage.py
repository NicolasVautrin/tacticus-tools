"""MONTAGE NOMME du volet ADJACENCE du gate de ciblage (#243) — la porte pytest de
`scripts/python/probe_243_not_adjacent.py`.

Le montage lui-meme (build isole, purge des cooldowns, DRIVE des heros au contact d'ennemis
distincts + double `endturn` pour purger le flag `Moved`, choix des trois tuiles discriminantes,
lecture de l'oracle natif `abilityReason`, replay OFFLINE du gate sur le MEME etat fige, et calcul
du verdict d'AVANT via un masque prive des quatre bits portes) vit dans le probe. Ce module n'est
que la fabrique : un seul point qui traduit « harnais indisponible » en echec franc et qui garde le
test lisible.

MEME CONVENTION que `_arcane_shield_stage.py` / `psychic_aoe_case` : ajouter un cas = ajouter une
mesure dans le probe, pas dupliquer un montage inline dans un test.
"""
from __future__ import annotations

import pytest

import probe_243_not_adjacent as P


def build_stage(seed: str = P.SEED, board_id: str = P.BOARD):
    """Monte la bataille et rend le dict de mesures du probe. Le runner est DISPOSE par le probe en
    sortie de `run()` -- rien a liberer au teardown."""
    try:
        return P.run(seed=seed, board_id=board_id)
    except RuntimeError as exc:
        pytest.fail("build runner KO / harnais indisponible : %s" % exc, pytrace=False)


def rows_for(stage, ability_type: int) -> list:
    return [r for r in stage["rows"] if r["ability"] == ability_type]


def pick(stage, ability_type: int, native_rule: int):
    """Le 1er couple (caster, cible) que le NATIF refuse pour EXACTEMENT `native_rule`, ou None.
    Les cas sont choisis sur la MESURE, jamais sur une geometrie supposee."""
    return next((r for r in rows_for(stage, ability_type)
                 if r["native"]["target_hex"] == int(native_rule)), None)
