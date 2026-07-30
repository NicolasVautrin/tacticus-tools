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


def test_triggered_ability_id_channel_mirrors_current_ability_not_triggering_ability():
    """case-292 -- SEMANTIQUE du canal que lit `!CurrentAbilityIs(this)`.

    `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` ecrit
    `Nullable<AbilityOrEffect>(this.Id)` dans DEUX champs distincts de l'`AbilityEntities`, a des
    moments differents : `CurrentAbility` (`+0x60`, lu par
    `IdunBattleLogic.Entities.DSLTriggers$$CurrentAbilityIs` via le slot `DSLSelectors+0x88`)
    **AVANT** l'appel du behaviour, et `TriggeringAbility` (`+0x98`, slot `DSLSelectors+0x90`, rendu
    par `IdunBattle.Entities.Abilities.AbilityEntities$$get_TriggerAbilityType`) **APRES**, pour la
    seule emission d'`On(0xd = UnitTriggeredAbility)`.

    Cette garde verrouille les deux moities de la semantique `+0x60` cote port :
      1. l'id est VISIBLE pendant `execute_behaviour` (donc par tout ce que le behaviour engendre) ;
      2. il est RESTAURE apres -- le natif ne fuit pas d'une evaluation a la suivante, chaque
         `IdunBattle.Operations.EvaluateTriggerOperation` batissant son propre `AbilityEntities`.
    C'est la moitie (2) qui distingue ce champ de l'autre, et elle est OBSERVABLE : la supprimer fait
    disparaitre le second coup de cloche du smite (`probe_224 --mutate persist`, mesure ci-dessous).
    """
    from engine.runner.state import State
    from engine.runner.components import UnitComponent
    from engine.runner.operations.triggers.base import TriggeredAbility, TriggerEvent
    import engine.runner.operations.triggers.dispatch.core as CORE

    seen = {}

    class _Spy(TriggeredAbility):
        event_id = 9
        TRIGGERED_ABILITY_ID = 4242

        def matches(self, state, ev):
            seen.setdefault("at_matches", []).append(
                getattr(state, "triggering_ability", None))
            return True

        def execute_behaviour(self, state, ev):
            seen["inside"] = getattr(state, "triggering_ability", None)
            return {"ok": True}

    state = State()
    e = state.add_entity(1)
    e.add_component(UnitComponent("spy", True))
    saved = (CORE.collect_triggered_abilities, CORE.collect_global_triggers,
             CORE.collect_effect_triggers)
    CORE.collect_triggered_abilities = lambda s: [_Spy(1)]
    CORE.collect_global_triggers = lambda: []
    CORE.collect_effect_triggers = lambda s: []
    try:
        state.triggering_ability = 777          # valeur AMBIANTE (behaviour imbrique dans un autre)
        out = CORE.evaluate_trigger_operation(state, TriggerEvent(9, 1, 2, ranged=False,
                                                                  profile=None))
    finally:
        (CORE.collect_triggered_abilities, CORE.collect_global_triggers,
         CORE.collect_effect_triggers) = saved

    assert out == [{"ok": True}]
    # (1) l'id de la triggered EN COURS est visible DANS le behaviour -- `CurrentAbility` @+0x60
    assert seen["inside"] == 4242
    # le gate `matches`, lui, s'evalue AVANT l'ecriture : il voit la valeur ambiante, jamais la sienne
    assert seen["at_matches"] == [777]
    # (2) la valeur ambiante est RESTAUREE apres le behaviour (imbrication native reproduite)
    assert state.triggering_ability == 777


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


def test_double_trigger_regime_is_reached_and_agrees_live():
    """case-292 -- la garde qui EXERCE le regime discriminant du canal `!CurrentAbilityIs(this)`.

    Regime : `bloodMephiston` produit DEUX declenchements pour UNE action -- l'attaque primaire, puis
    le smite `PsykerExtraAttack` (tag natif `Passive_Ability_Type = 1013`), qui est une attaque
    DISTINCTE emise APRES le behaviour de la cloche et fait donc un SECOND `On(9)`. C'est le seul
    montage ou la RESTAURATION du canal (l'`AbilityEntities` de chaque evaluation etant jete) devient
    OBSERVABLE : sans elle, ce second `On(9)` verrait encore `CurrentAbility == 1071` et serait gate.

    On verifie le NOMBRE de declenchements des deux cotes, pas seulement le total agrege : c'est
    l'ETAGE, et c'est lui qui distingue les deux modeles.

    Contre-epreuve MESUREE (`docs/rl/case-292-current-vs-triggering-ability.md`) :
      `--mutate persist` (restauration supprimee) -> natif 4860 / 2 fires vs port 2430 / 1 fire ;
      `--mutate nogate`  (gate seul neutralise)   -> 0 desaccord (il est REDONDANT avec
                                                    `!CasterIsTarget`, la riposte etant une
                                                    auto-attaque).
    """
    import probe_224_cursed_plague_bell_attack as P
    rows = []
    assert P.scenario(_args(), rows_out=rows) == 0
    ex = [r for r in rows if r.get("exercised")]
    assert ex, "aucun cas exerce -- un accord vide ne garde rien"
    multi = [r for r in ex if r["live_fires"] >= 2]
    assert multi, ("le regime DOUBLE DECLENCHEMENT n'a pas ete atteint : "
                   + repr([(r["unit"], r["live_fires"]) for r in ex]))
    for r in multi:
        assert r["port_fires"] == r["live_fires"], (r["unit"], r["port_fires"], r["live_fires"])
        # le second coup vient bien d'une attaque NATIVE distincte, pas d'un second coup d'arme
        srcs = [e.get("pass") for e in r["all_dmg"] if e.get("pass") is not None]
        assert 1013 in srcs, ("le smite PsykerExtraAttack (1013) n'est pas dans le flot : "
                              + repr(srcs))


def test_bell_does_not_fire_on_an_ally_of_the_carrier_live():
    """Gate `AreEnemies(Actor, Owner)` : le MEME psyker, mais du camp du porteur et DANS son aura,
    n'encaisse rien. Le probe exige qu'au moins un cas soit dans l'aura, sinon c'est la geometrie
    et non le gate qui expliquerait l'absence de riposte."""
    import probe_224_cursed_plague_bell_attack as P
    assert P.scenario(_args(dists="2,3", allies=True)) == 0
