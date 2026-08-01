"""GARDE #366-r1 (OFFLINE PURE) -- `TunnelingHorror_PendingSummon` (EffectType 0x459 = 1113).

CE QU'ELLE PROTEGE, et pourquoi ce n'est pas une tautologie de registre.

L'effet est un MARQUEUR de bond pose sur la TUILE de destination par
`IdunBattleLogic.Entities.Abilities.Active.Loki.TunnelingHorrorAbility$$ExecuteBehaviour` (active
1011) et retire par `...TunnelingHorror_AppearAbility$$ExecuteBehaviour` (active 1060). Il n'a AUCUNE
contribution -- ce qui rend son port fragile a deux fautes symetriques, que cette garde fige :

  1. **La hierarchie**. Ghidra attribue le corps appele par
     `IdunBattle.Entities.Effects.Loki.TunnelingHorror_PendingSummonEffect$$.ctor` a
     `IdunBattle.Entities.Effects.BaseEffect$$.ctor` : c'est un corps DEDUPLIQUE (la surcharge a 4
     arguments d'`IdunBattle.Entities.Effects.ABondEffect` est instruction pour instruction celle de
     la base). Le parent REEL n'est lisible que dans la table de symboles VERSIONNEE. On l'asserte
     donc DEPUIS `data/symbols/<CURRENT>/frida/classes.tsv`, pas depuis le mirror Python : si un
     build deplace la classe sous une autre base, la garde rougit au lieu de laisser la docstring
     mentir.
  2. **L'ABSENCE de trigger de retrait**. `IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal`
     bat it un `ArraySet` de triggered-abilities `Triggered(<cond>, RemoveEffect(EffectSelf))`, une par
     condition VRAIE parmi `get_RemoveOnBondedEntityDeath`, `get_Range.HasValue`, `get_Adjacent`. La
     classe surcharge les TROIS a false/null/false (corps triviaux, releves au runtime par le RPC
     `resolveMethodPtr` -- les tables de symboles dedupliquent ces corps et ne les nomment pas), donc
     l'`ArraySet` est VIDE. `EFFECT_TRIGGERS[1113]` doit rester ABSENT : c'est une MESURE, et sans
     cette garde une inscription ulterieure passerait pour une amelioration.

Le lien registre -> classe est asserte par sa CONSEQUENCE (`EffectFactory.create` sur une capture au
format `tileMeta`), avec le CONTRE-EXEMPLE dans le meme test : un nom inconnu retombe sur
`BaseEffect`. Sans ce second bras, l'assertion ne discriminerait rien.

Mesure live de bout en bout (pose / seed offline / lecture par le gate de ciblage / persistance /
retrait) : `python scripts/python/probe_366_r1_tunneling_horror.py`.
RE : `docs/rl/case-366-r1-tunneling-horror-pending-summon.md`. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from engine.entities.effect_type import EffectType                      # noqa: E402
from engine.entities.effects.factory import EFFECT_CLASSES, EffectFactory  # noqa: E402
from engine.entities.effects.base import BaseEffect                     # noqa: E402
from engine.entities.effects.loki import TunnelingHorrorPendingSummonEffect  # noqa: E402
from engine.runner.operations.triggers import EFFECT_TRIGGERS           # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
SYMBOLS = ROOT / "data" / "symbols"

PENDING = 1113
EFFECT_NAME = "TunnelingHorror_PendingSummon"
NATIVE_CLASS = "IdunBattle.Entities.Effects.Loki.TunnelingHorror_PendingSummonEffect"
NATIVE_PARENT = "IdunBattle.Entities.Effects.ABondEffect"
# La capture telle que `tileMeta` (`readEffectsByTile`) la publie -- PAS de `bonded` : le canal ne
# porte pas le `BondEffect_BondedId` (le flux d'EVENTS, lui, le porte). Mesure du 2026-08-01.
CAPTURED = {"name": EFFECT_NAME, "effectType": PENDING, "source": 81, "remaining": 0, "level": 1}


def _build() -> str:
    return (SYMBOLS / "CURRENT").read_text(encoding="utf-8").strip()


def test_enum_member_matches_versioned_symbol_table():
    """`EffectType.TunnelingHorror_PendingSummon` == la valeur de `frida/enums.tsv` du build COURANT.
    Ce build a deja renumerote des membres en silence (#318) : ancrer par NOM, pas par le mirror."""
    tsv = SYMBOLS / _build() / "frida" / "enums.tsv"
    if not tsv.exists():
        pytest.skip("table d'enums absente pour le build %s" % _build())
    # Format `enums.tsv` : `<nom complet de l'enum>\t<k=v,k=v,...>` sur UNE ligne.
    found = None
    for line in tsv.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 2 or parts[0] != "IdunBattle.Entities.Enum.EffectType":
            continue
        for kv in parts[1].split(","):
            k, _, v = kv.partition("=")
            if v == EFFECT_NAME:
                found = int(k)
        break
    assert found == PENDING, "enums.tsv donne %r pour %s" % (found, EFFECT_NAME)
    assert int(EffectType.TunnelingHorror_PendingSummon) == PENDING


def test_native_parent_is_abond_effect_not_base_effect():
    """Le parent REEL de la classe native, lu dans la table VERSIONNEE -- c'est le seul endroit ou
    il est lisible (le `$$.ctor` est un corps deduplique attribue a `BaseEffect`)."""
    tsv = SYMBOLS / _build() / "frida" / "classes.tsv"
    if not tsv.exists():
        pytest.skip("table de classes absente pour le build %s" % _build())
    parent = None
    for line in tsv.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split("\t")
        if parts and parts[0] == NATIVE_CLASS:
            parent = parts[2] if len(parts) > 2 else None
            break
    assert parent == NATIVE_PARENT, (
        "classes.tsv donne parent=%r pour %s (attendu %s) -- si le build a bouge, RELIRE la classe "
        "avant de toucher au port" % (parent, NATIVE_CLASS, NATIVE_PARENT))


def test_registry_materialises_the_ported_class_and_discriminates():
    """Le registre est asserte par sa CONSEQUENCE, avec le contre-exemple dans le meme test."""
    assert EFFECT_CLASSES.get(EFFECT_NAME) is TunnelingHorrorPendingSummonEffect
    got = EffectFactory.create(dict(CAPTURED), None, None, None)
    assert isinstance(got, TunnelingHorrorPendingSummonEffect)
    assert got.effect_type == PENDING and got.source == 81
    # remaining = 0 cote capteur == PERMANENT (`AddBondEffect` sans `TurnsFromRounds`).
    assert got.remaining_turns in (0, None)
    # `bonded` reste None : LIMITE DE CANAL (`tileMeta` ne publie pas le bond), pas un bug de port.
    assert got.bonded is None
    # CONTRE-BRAS : sans entree de registre, la fabrique retombe sur `BaseEffect`.
    unknown = EffectFactory.create(
        {"name": EFFECT_NAME + "_NotRegistered", "effectType": PENDING}, None, None, None)
    assert type(unknown) is BaseEffect


def test_bond_knobs_mirror_the_three_native_getters():
    """Les trois getters surcharges (corps triviaux, releves au runtime) -- ce sont eux, et eux
    seuls, que lit `ABondEffect$$CreateHandleTriggerAbilitiesInternal`."""
    T = TunnelingHorrorPendingSummonEffect
    assert T.BOND_ADJACENT is False                      # get_Adjacent -> false
    assert T.BOND_RANGE is None                          # get_Range -> Nullable<int> vide
    assert T.BOND_REMOVE_ON_BONDED_ENTITY_DEATH is False  # get_RemoveOnBondedEntityDeath -> false
    assert T.HAS_AUTOMATIC_ACTIVATION is True            # ABondEffect..ctor(hasAutomaticActivation=1)


def test_no_effect_trigger_registered_for_1113():
    """`ArraySet` natif VIDE => aucune entree. Mesure, pas oubli."""
    assert not EFFECT_TRIGGERS.get(PENDING), (
        "EFFECT_TRIGGERS[%d] = %r : les trois conditions d'`ABondEffect$$"
        "CreateHandleTriggerAbilitiesInternal` sont ETEINTES chez cette classe -- toute inscription "
        "ici ajoute un retrait que le natif ne fait PAS" % (PENDING, EFFECT_TRIGGERS.get(PENDING)))


def test_effect_contributes_nothing():
    """Marqueur PUR : aucun canal de contribution ne doit rendre autre chose que le defaut."""
    e = EffectFactory.create(dict(CAPTURED), None, None, None)
    assert e.applied_stat_mods(None) == []
    assert e.create_effect_damage_bonus_for_attack() is None
    assert e.create_effect_damage_malus_for_defense() is None
    assert e.get_stat_modification_stat() is None
    assert e.is_active() is True          # aucune `CreateActiveCondition` surchargee
