"""#419-r1-tr11-r4 -- le `Pinned` (1065) a `d == 3` de `SpecialIssueCombiMelta`, garde LIVE.

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpecialIssueCombiMelta_AddEffectAbility` :

    $$CreateTrigger   = On(0x26 = NormalAttack, 1) & get_OwnerIsCaster
                        & IsAtRange(Caster@DSLSelectors+0x48, Target@DSLSelectors+0x60,
                                    DSLFormulas.Get(3))
    $$CreateBehaviour = DSLBehaviors.AddEffect(0x429 = 1065 Pinned, AbilityStateReference,
                                               targets = Target@DSLSelectors+0x60, turns = null)

CE QUE CE FICHIER GARDE :

  1. **A d == 3, les DEUX moteurs posent `Pinned`** sur la cible de l'attaque normale.
  2. **A d == 2, AUCUN des deux ne le pose.** C'est ce second bras qui rend le premier
     discriminant : `IdunBattle.Entities.Triggers.IsAtRangeAbilityTrigger$$ShouldTrigger` compare
     par EGALITE (`return d == attendu`), donc un port ecrit en `<= 3` passerait (1) et tomberait
     ici. Sans lui, (1) serait aussi vert avec un port qui pose Pinned a TOUTE distance.
  3. **LE MONTAGE EST AU REGISTRE** (OFFLINE, derive) : la classe est bien accrochee a la
     passiveAbility `SpecialIssueCombiMelta` -- et PAS a un dict de derivation. Les DEUX dicts
     natifs ont ete lus sur `rnca9r7q6c` : `StaticBattleRules.ActiveAbility$$.cctor` est indexe
     par `ActiveAbilityType` (l'active du porteur est `SternguardFocus`), et
     `StaticBattleRules.TriggeredAbility$$.cctor` ne peuple son `<statics>+0x88` que de
     `0x3ef -> [0x3fc]` et `0x48e -> [0x491]` -- **jamais `0x609` (1545)**.

Porteur : `darkaSternguard` << Ramus >>, HERO HORS CATALOGUE (`catalog_inject --missing`), arme
`ranged r3`. Le montage DEPLACE le caster jusqu'a la distance voulue ; s'il n'y arrive pas il
ECHOUE FRANCHEMENT (`MontageError`), il ne skippe pas (#268 -- un skip sur un regime non atteint
est un vert qui ment).

ASCII only. Probe jumeau : `scripts/python/probe_419r1tr11_r4_pinned.py`.
"""
from __future__ import annotations

import uuid

import pytest

import probe_419r1tr11_r4_pinned as P
from engine.entities.effect_type import EffectType


def _arm(build_runner, rpc, dist):
    P.LOGS.mkdir(parents=True, exist_ok=True)
    bc = P.LOGS / ("tr11r4-seedbc-%s.json" % uuid.uuid4().hex[:8])
    P.write_seed_bc(bc)
    rid = build_runner(seed=str(P.SEED), extra=["--seed-bc", str(bc), *P.BUILD_ARGS])["rid"]
    try:
        return P._measure(rpc, rid, dist)
    except P.MontageError as e:
        pytest.fail("montage non exerce (d = %d) : %s" % (dist, e), pytrace=False)


@pytest.fixture(scope="module")
def at_three(build_runner, rpc):
    return _arm(build_runner, rpc, 3)


@pytest.fixture(scope="module")
def at_two(build_runner, rpc):
    return _arm(build_runner, rpc, 2)


def test_pinned_is_registered_on_the_passive_ability():
    """(3) OFFLINE, DERIVE du registre -- la classe est accrochee a `ABILITY_TRIGGERS`, cle = le NOM
    gameconfig de la passiveAbility du porteur, et ce nom est bien celui que le kit porte."""
    import gameconfig as GC
    from engine.runner.operations.triggers.dispatch.registry import (ABILITY_TRIGGERS,
                                                                     ACTIVE_ABILITY_TRIGGERS)
    from engine.runner.operations.triggers.loki.special_issue_combi_melta import (
        SpecialIssueCombiMeltaAddEffectAbility, SPECIAL_ISSUE_COMBI_MELTA)

    kit = GC.unit(P.CASTER) or {}
    assert SPECIAL_ISSUE_COMBI_MELTA in (kit.get("passiveAbilities") or []), (
        "%s ne porte plus la passiveAbility %s (kit lu : %r) -- le montage du port n'a plus de "
        "substrat" % (P.CASTER, SPECIAL_ISSUE_COMBI_MELTA, kit.get("passiveAbilities")))
    assert SpecialIssueCombiMeltaAddEffectAbility in \
        (ABILITY_TRIGGERS.get(SPECIAL_ISSUE_COMBI_MELTA) or []), (
        "la classe n'est plus dans `ABILITY_TRIGGERS[%r]` : le Pinned ne sera plus jamais pose"
        % SPECIAL_ISSUE_COMBI_MELTA)
    # Le montage NE PASSE PAS par la derivation d'ability ACTIVE (les deux dicts natifs ont ete
    # lus, cf. l'en-tete) : une entree ici serait un chemin que le natif n'emprunte pas.
    for aa in (kit.get("activeAbilities") or []):
        assert SpecialIssueCombiMeltaAddEffectAbility not in \
            (ACTIVE_ABILITY_TRIGGERS.get(aa) or []), (
            "la classe est inscrite dans `ACTIVE_ABILITY_TRIGGERS[%r]` -- ce dict est le mirror de "
            "`StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities`, qui ne contient PAS "
            "1545. Le porteur la porterait DEUX fois." % aa)


def test_pinned_is_applied_at_range_three(at_three):
    """(1) A d == 3 : `Pinned` pose des DEUX cotes."""
    assert at_three["dist"] == 3
    assert at_three["live_pinned"], (
        "le NATIF ne pose pas Pinned a d == 3 (effets cible : %r) -- la RE de "
        "`SpecialIssueCombiMelta_AddEffectAbility` serait fausse, ou le montage n'exerce pas le "
        "regime" % (at_three["live_effects"],))
    assert at_three["offline_pinned"], (
        "le PORT ne pose pas Pinned a d == 3 alors que le natif le fait (effets offline : %r) -- "
        "verifier `ABILITY_TRIGGERS['SpecialIssueCombiMelta']` et le vecteur `On(0x26)`"
        % (at_three["offline_effects"],))


def test_pinned_is_not_applied_at_range_two(at_two):
    """(2) CONTRE-EPREUVE -- a d == 2, ni le natif ni le port ne posent `Pinned`.

    `IsAtRange` compare par EGALITE : c'est ce test, et lui seul, qui separe le port juste d'un
    port ecrit en `<= 3` ou sans gate du tout."""
    assert at_two["dist"] == 2
    assert not at_two["live_pinned"], (
        "le NATIF pose Pinned a d == 2 : le litteral de portee n'est pas 3, ou `IsAtRange` n'est "
        "pas une egalite (effets cible : %r)" % (at_two["live_effects"],))
    assert not at_two["offline_pinned"], (
        "le PORT pose Pinned a d == 2 alors que le natif ne le fait pas (effets offline : %r) -- "
        "le gate `is_at_range(..., 3)` a ete relache en `<=`" % (at_two["offline_effects"],))


def test_the_two_arms_disagree_with_each_other(at_three, at_two):
    """Reciproque explicite : les deux bras doivent RENDRE DES VERDICTS OPPOSES. Un montage ou les
    deux repondraient pareil (Pinned partout, ou nulle part) rendrait les deux tests ci-dessus
    verts sans rien mesurer -- exactement le vice d'un temoin non discriminant."""
    assert at_three["live_pinned"] != at_two["live_pinned"], (
        "les deux bras rendent le MEME verdict natif (%r) : le montage ne discrimine pas la "
        "distance" % at_three["live_pinned"])
    assert EffectType.Pinned.name not in (at_three["effects_before"] or []), (
        "la cible portait deja Pinned avant l'attaque du bras d == 3")
