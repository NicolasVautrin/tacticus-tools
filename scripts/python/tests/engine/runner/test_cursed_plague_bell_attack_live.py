"""case-224 item 5 -- `CursedPlagueBellAttackAbility` (1071) : la riposte Psychique de Corrodius.

i2 : « Enemy PSYKER units within Corrodius' Contagion aura deal {nrOfHits}x {dmg} Psychic Damage
       TO THEMSELVES each time one of their attacks deals Psychic Damage. »

Ces gardes verrouillent, dans l'ordre :
  * OFFLINE  le SUBSTRAT du port -- entree au registre, parametres de la feuille d'attaque, et la
             SEPARATION des deux sources de « Psychic » (le litteral 0xd du gate de trigger vs
             `GetAffectedDamageProfile()` du profil de la riposte) ;
  * OFFLINE  le fait que le montant vient du PORTEUR (config de la cloche) et non du psyker ;
  * LIVE     l'accord bit-exact port/natif sur la riposte, avec au moins un cas DISCRIMINANT-POSITIF
             (dans l'aura + ennemi + attaque Psychic) -- sans lui l'accord serait vide ;
  * LIVE     le contre-cas de PORTEE (hors aura) dans le meme montage.

Mesure et contre-epreuves : `scripts/python/probe_224_cursed_plague_bell_attack.py`
(5 mutations, dont `strict` qui rougit EXACTEMENT sur `d == range` -- le verrou du renversement
documente dans `docs/rl/case-224-cursed-plague-bell-attack.md`).
"""
from __future__ import annotations

import argparse

import pytest

pytestmark = pytest.mark.usefixtures("live_session")

BOARD = "C1_02"
SEED = "4242"


# ------------------------------------------------------------------ gardes OFFLINE

def test_attack_ability_is_registered_with_its_native_parameters():
    """La classe entre au registre des TRIGGERED (`ABILITY_TRIGGERS`, cle = `passiveAbilities`) et
    sa feuille porte les parametres LUS au decompile de `...CursedPlagueBellAttackAbility$$
    CreateBehaviour` : mode `amount` (le natif passe `DSLFormulas.Get(int)`, pas des bornes d'arme),
    `nrOfHits` de la config, profil `GetAffectedDamageProfile()`, `attackRangeType = Ranged`,
    options natives VIDES (donc aucune variance) et factory `AttackWithAttackDamage`."""
    import gameconfig as GC
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    from engine.runner.operations.triggers.loki.cursed_plague_bell import (
        CursedPlagueBellAttackAbility, cursed_plague_bell_attack_hits,
        cursed_plague_bell_attack_tree)
    from engine.runner.abilities.deathguard import cursed_plague_bell_damage_profile

    assert CursedPlagueBellAttackAbility in ABILITY_TRIGGERS["CursedPlagueBell"]
    assert CursedPlagueBellAttackAbility.event_id == 9          # On(9) = EventTriggerType.Attack
    assert CursedPlagueBellAttackAbility.TRIGGERED_ABILITY_ID == 1071

    tree = cursed_plague_bell_attack_tree(123)
    assert tree.profile == cursed_plague_bell_damage_profile()
    assert tree.is_melee is False                               # attackRangeType = "Ranged"
    assert tree.hits == cursed_plague_bell_attack_hits()
    assert tree.hits == int((GC.ability("CursedPlagueBell")["constants"])["nrOfHits"])
    assert tree.amount_spread_pct == 0                          # options natives VIDES
    assert tree.native_factory == "attack"
    assert int(tree.amount.evaluate(None)) == 123               # `DSLFormulas.Get(int)` = constante
    # `ability_type` NON threade : 1071 vaut `AnnihilatorBeam` dans l'espace `ActiveAbilityType`,
    # sur lequel ce canal est keye -- y injecter le `TriggeredAbilityType` ferait lire une AUTRE
    # ability par tous les gates de kind (meme refus que MartialSuperiority / MartialApotheosis).
    assert tree.ability_type is None


def test_the_two_psychic_sources_are_distinct_reads():
    """Le gate du trigger lit un LITTERAL (`CurrentAttackDamageProfilesContain(0xd)`) ; le profil de
    la riposte lit `GetAffectedDamageProfile().GetValueOrDefault(0xd)`. Deux artefacts natifs
    distincts, qui coincident au gameconfig courant -- le port les tient SEPARES."""
    from engine.runner.operations.triggers.loki.cursed_plague_bell import ATTACK_GATE_PROFILE
    from engine.runner.abilities.deathguard import cursed_plague_bell_damage_profile
    from engine.entities.damage_profile_type import DamageProfileType
    assert ATTACK_GATE_PROFILE == DamageProfileType(0xd).name   # litteral du CreateTrigger
    assert cursed_plague_bell_damage_profile() == "Psychic"     # constante d'ability, relue
    # anti-fork : la face DECISION (playbook) DELEGUE au meme foyer, elle n'a pas sa copie.
    from engine.playbook.adjacent_unit_preference import _cursed_plague_bell_damage_profile
    assert _cursed_plague_bell_damage_profile() == cursed_plague_bell_damage_profile()


def test_unit_aura_predicate_is_inclusive_like_the_team_one():
    """VERROU DU RENVERSEMENT (case-224 item 5). Le predicat par UNITE accepte `dist == range` --
    mesure live a deux paliers, cf. le probe. La lecture STRICTE d'origine rendrait False ici."""
    from engine.entities.triggers import IsInUnitAura
    node = IsInUnitAura.__new__(IsInUnitAura)
    node.range_formula = type("R", (), {"calculate": staticmethod(lambda ctx: 3)})()
    node.distance_formula = type("D", (), {"calculate": staticmethod(lambda ctx: 3)})()
    assert node.should_trigger(None) is True                    # d == range -> DANS l'aura
    node.distance_formula = type("D", (), {"calculate": staticmethod(lambda ctx: 4)})()
    assert node.should_trigger(None) is False                   # d > range -> dehors


# ------------------------------------------------------------------ garde LIVE

def _args(**kw):
    base = dict(board=BOARD, seed=SEED, advance=10, dists="2,3,4",
                psykers="astraPrimarisPsy,bloodMephiston,spaceStormcaller",
                tanks="custoKyrus,astraBullgryn,ultraTitus", allies=False, mutate=None,
                tgt_dist=None, keep=False, verbose=False)
    base.update(kw)
    return argparse.Namespace(**base)


def test_bell_recoil_agrees_with_native_live():
    """Le montage nominal : trois psykers ENNEMIS du porteur, a d=2 / 3 / 4 d'une aura de rayon 3.
    Le probe REFUSE de conclure si aucun cas ne reunit les trois gates (aura + ennemi + Psychic) --
    un accord sur zero cas exerce ne prouverait rien. L'attribution du recul se fait par le tag natif
    `Passive_Ability_Type = 1071`, jamais par un delta de PV (contamine par l'overwatch)."""
    import probe_224_cursed_plague_bell_attack as P
    assert P.offline_guard() == 0
    assert P.scenario(_args()) == 0


def test_bell_does_not_fire_on_an_ally_of_the_carrier_live():
    """Gate `AreEnemies(Actor, Owner)` : le MEME psyker, mais du camp du porteur et DANS son aura,
    n'encaisse rien. Le probe exige qu'au moins un cas soit dans l'aura, sinon c'est la geometrie
    et non le gate qui expliquerait l'absence de riposte."""
    import probe_224_cursed_plague_bell_attack as P
    assert P.scenario(_args(dists="2,3", allies=True)) == 0
