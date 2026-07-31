"""CLIQUET du REPLI PORTEUR d'`EffectsState.seed` (case-366-r1) : son troisieme membre.

`#382` a fait de `EffectsState.seed` un consommateur d'`ability_state_by_unit` =
`{uid: (multiplier, abilityLevel, activeAbilityLevel)}`, consulte **par la SOURCE** de chaque effet
(`baked_ability_state`, mirror du bake natif `AddEffectBehaviour$$DefaultEffectBuilder`). Mais son
**REPLI PORTEUR** -- celui que prend tout owner-effect, ou `source == porteur` -- forcait
`activeAbilityLevel = None` (« l'elargir ici deborderait du cas »).

Consequence : les **19 classes d'effet** qui ecrivent la cascade
`active_ability_level -> ability_level -> level` (parce que `GetAbilityState(effet)` resout
l'AbilityState d'une ability **ACTIVE** : leur `$$.ctor` ecrit l'`ActiveAbilityType` puis la
surcharge d'`IdunBattle.Core.AbilityOrEffect$$op_Implicit` qui appelle `set_ActiveAbility`)
retombaient TOUJOURS sur le niveau PASSIF.

POURQUOI CA N'AVAIT JAMAIS ROUGI -- meme raison que `#382` : `buildNormalizedBC` ecrit le MEME
`targetAbilityLevel` dans `ActiveAbilityLevel` ET `PassiveAbilityLevel`. Toute garde montee sur un
seed normalise est VERTE ET VIDE sur cet axe. La confrontation LIVE dissocie les deux
(`--unit-stat "eldarRanger:ActiveAbilityLevel=30"`, passif 50) et vit dans
`tests/engine/runner/test_fire_and_reposition_reduce_dmg_live.py` ; CE fichier tient la meme
propriete SANS runner, au niveau de la fonction.

ASCII only (cp1252).
"""
from __future__ import annotations

from engine.entities.effects_state import EffectsState

CARRIER = 79
SOURCE = 81
# `(multiplier, abilityLevel, activeAbilityLevel)` -- le triple d'`_ability_state_from_config`
# (COMBAT) / `_effect_source_ability_states` (DECISION). Les DEUX niveaux DIFFERENT : c'est la
# seule configuration ou la lecture est discriminante.
STATES = {CARRIER: (180, 50, 30), SOURCE: (200, 41, 12)}


def _owner_effect(name="FireAndReposition_ReduceDmg", etype=1110, source=CARRIER):
    return {"name": name, "effectType": etype, "remaining": 2, "level": 1, "source": source}


def _inst(st, uid=CARRIER):
    effs = st.by_unit.get(uid) or []
    assert effs, "aucun effet materialise pour u%s" % uid
    return effs[0]


def test_carrier_fallback_carries_active_ability_level():
    """REPLI PORTEUR (source == porteur) : le 3e membre du triple DOIT arriver sur l'instance.

    C'est le cas de tout owner-effect -- `AddEffect(..., source=Owner, targets=Owner, ...)`."""
    st = EffectsState.seed({CARRIER: [_owner_effect()]},
                           {CARRIER: 180}, {CARRIER: 50}, STATES)
    e = _inst(st)
    assert e.active_ability_level == 30, (
        "le REPLI PORTEUR n'a pas propage `activeAbilityLevel` (rendu %s, attendu 30) : toute "
        "classe dont la SOURCE est une ability ACTIVE retombe alors sur le niveau PASSIF"
        % (e.active_ability_level,))
    assert e.ability_level == 50 and e.ability_variables_multiplier == 180, (
        "le repli a change les DEUX autres membres (%s, %s) -- regression sur le comportement "
        "anterieur" % (e.ability_level, e.ability_variables_multiplier))


def test_source_state_still_wins_over_carrier():
    """NON-REGRESSION `#382` : quand la source DIFFERE du porteur, c'est SON triple qui gagne --
    les trois membres, pas seulement les deux premiers."""
    st = EffectsState.seed({CARRIER: [_owner_effect(source=SOURCE)]},
                           {CARRIER: 180}, {CARRIER: 50}, STATES)
    e = _inst(st)
    assert (e.ability_variables_multiplier, e.ability_level, e.active_ability_level) \
        == (200, 41, 12), (
        "l'effet pose par u%s lit (%s, %s, %s) au lieu du triple de sa SOURCE (200, 41, 12)"
        % (SOURCE, e.ability_variables_multiplier, e.ability_level, e.active_ability_level))


def test_no_state_table_keeps_prior_behaviour():
    """Appelant qui ne passe PAS la table (tests, harnais anciens) : comportement STRICTEMENT
    anterieur -- les deux tables par porteur, et `activeAbilityLevel` inconnu -> None (jamais un
    niveau devine)."""
    st = EffectsState.seed({CARRIER: [_owner_effect()]}, {CARRIER: 180}, {CARRIER: 50})
    e = _inst(st)
    assert (e.ability_variables_multiplier, e.ability_level, e.active_ability_level) \
        == (180, 50, None), (
        "sans `ability_state_by_unit`, le seed rend (%s, %s, %s) au lieu de (180, 50, None)"
        % (e.ability_variables_multiplier, e.ability_level, e.active_ability_level))


def test_source_absent_from_table_falls_back_to_carrier_triple():
    """Source RESOLVABLE dans la capture mais ABSENTE de la table d'etats (entite non chargee) :
    on retombe sur le PORTEUR -- et ce repli porte lui aussi son niveau ACTIF."""
    st = EffectsState.seed({CARRIER: [_owner_effect(source=9999)]},
                           {CARRIER: 180}, {CARRIER: 50}, STATES)
    e = _inst(st)
    assert (e.ability_variables_multiplier, e.ability_level, e.active_ability_level) \
        == (180, 50, 30), (
        "source inconnue -> attendu le triple du PORTEUR (180, 50, 30), rendu (%s, %s, %s)"
        % (e.ability_variables_multiplier, e.ability_level, e.active_ability_level))
