"""#294 -- les DEUX canaux `AbilityEntities` du port, et la preuve qu'ils sont SEPARES.

    `CurrentAbility`    `AbilityEntities+0x60`  ->  `state.triggering_ability`   (nom historique)
    `TriggeringAbility` `AbilityEntities+0x98`  ->  `state.trigger_ability_type` (#294)

`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` ecrit la MEME
`AbilityOrEffect(this.Id)` dans les deux -- ce qui les separe est le MOMENT : `+0x60` AVANT l'appel
du behaviour, `+0x98` APRES, juste avant `On(0xd = EventTriggerType.UnitTriggeredAbility)`.

/!\ Poser un second canal SANS montage qui exerce la difference ne vaut rien : sur une triggered
ISOLEE les deux champs finissent egaux, et un canal `+0x98` cable par erreur sur `+0x60` passerait
tous les tests. Le montage qui les separe est donc le livrable, pas un accessoire -- il vit dans
`scripts/python/probe_294_trigger_ability_channels.py` et sa porte pytest est la fixture
`trigger_ability_channel_case`.

TOUT EST OFFLINE ici, et c'est un choix : aucune ability portee n'ecoute `On(0xd)` et aucun capteur
live ne lit `+0x98`, donc aucune observable de bataille n'en depend aujourd'hui. Ce qui est
verrouille est le MOMENT D'ECRITURE et la PORTEE de chaque canal -- deterministe, sans RNG.
"""
from __future__ import annotations

import pytest

import probe_294_trigger_ability_channels as TAC


def test_the_two_channels_are_distinct_slots_on_state():
    """Le canal `+0x98` a son PROPRE slot -- il ne peut pas etre un alias de `+0x60`.

    C'est la garde la plus bete et la plus utile : `case-292` sec.5 avertissait qu'"une ability future
    NE DOIT PAS reutiliser `State.triggering_ability`". Si quelqu'un les refond en un seul champ,
    ce test rougit avant que la confusion n'atteigne un gate."""
    from engine.runner.state import State
    assert "triggering_ability" in State.__slots__
    assert "trigger_ability_type" in State.__slots__
    st = State()
    assert st.triggering_ability is None and st.trigger_ability_type is None
    st.triggering_ability = 1
    assert st.trigger_ability_type is None, "ecrire +0x60 a touche +0x98 : les canaux sont aliases"
    st.trigger_ability_type = 2
    assert st.triggering_ability == 1, "ecrire +0x98 a touche +0x60 : les canaux sont aliases"


def test_channels_separate_in_a_chained_triggered_ability(trigger_ability_channel_case):
    """LE MONTAGE. Chaine `A --On(0xd)--> B --On(9)--> C`, et les cinq faits que le decompile impose.

    Le point qui compte est `B.exec` : `+0x60 = B` (B vient de l'y ecrire avant SON behaviour) et
    `+0x98 = A` (le natif ne reecrit `+0x98` qu'a la FIN de B). Deux valeurs non nulles differentes
    -- c'est la seule configuration ou un port qui confond les deux champs est detectable."""
    r = trigger_ability_channel_case()
    a, b = r["a_id"], r["b_id"]

    # (1) pendant le behaviour de A, `+0x98` n'est PAS encore ecrit -- etape 4 sur 6 du natif
    assert TAC.site(r, "A.exec") == (a, None)
    # (2) le gate `TriggeringAbilityIs(A)` de B lit `+0x98`, pas `+0x60`
    assert TAC.site(r, "B.matches") == (None, a)
    # (3) LE LIVRABLE : deux valeurs NON NULLES DIFFERENTES dans le behaviour chaine
    assert TAC.site(r, "B.exec") == (b, a)
    # (4) `+0x60` est herite par ce que le behaviour engendre, `+0x98` ne l'est pas
    assert TAC.site(r, "C.matches") == (b, a)
    # (5) aucun des deux ne fuit hors de son evaluation
    assert r["final"] == (None, None)

    # la garde complete du probe dit la meme chose -- on l'appelle pour que le probe et le test ne
    # puissent pas diverger (un seul foyer d'assertion, reutilisable par un futur consommateur)
    TAC.assert_channels_separated(r)


@pytest.mark.parametrize("mutation", TAC.MUTATIONS)
def test_each_mutation_reddens_the_montage(mutation, trigger_ability_channel_case):
    """CONTRE-EPREUVES : chaque moitie du port, neutralisee, doit faire ROUGIR le montage.

    Sans ce test, la garde ci-dessus pourrait etre VERTE pour une raison qui n'a rien a voir avec
    les canaux (par exemple parce que la chaine ne monte pas du tout et que toutes les lectures
    rendent `None`). Les quatre mutations couvrent les quatre facons de rater le port :

      `before`   ecrire `+0x98` AVANT le behaviour  -> les deux canaux redeviennent egaux
      `alias`    reutiliser le slot de `+0x60`      -> le gate de B lit `None`, B ne fire jamais
      `persist`  ne pas restaurer `+0x98`           -> l'id fuit d'une evaluation a la suivante
      `noevent`  ne pas publier `On(0xd)`           -> B ne fire jamais (= l'etat d'AVANT #294)
    """
    r = trigger_ability_channel_case(mutation)
    with pytest.raises(AssertionError):
        TAC.assert_channels_separated(r)


def test_nominal_and_mutations_do_not_agree_by_accident(trigger_ability_channel_case):
    """Anti-accord-vide : le nominal et CHAQUE mutation doivent produire des traces DIFFERENTES.

    Une mutation qui rendrait la MEME trace que le nominal serait un no-op deguise en contre-epreuve
    -- elle ferait rougir la garde pour une raison etrangere au canal."""
    base = trigger_ability_channel_case()["obs"]
    for m in TAC.MUTATIONS:
        assert trigger_ability_channel_case(m)["obs"] != base, \
            f"la mutation '{m}' ne change RIEN a la trace : ce n'est pas une contre-epreuve"


def test_publish_is_a_no_op_for_an_entry_without_id():
    """`BaseTriggeredAbility$$Execute` ecrit `AbilityOrEffect(this.Id)` : sans id, rien a poser.

    Cote port, une entree dont `TRIGGERED_ABILITY_ID is None` (le cas des triggers qui n'ont pas
    encore leur id relu) ne doit ni ecrire `+0x98` ni publier `On(0xd)` -- la meme regle que pour
    `+0x60`, ou l'absence d'id laisse le canal a `None`."""
    from engine.runner.state import State
    from engine.runner.components import UnitComponent
    from engine.runner.operations.triggers.base import TriggeredAbility, TriggerEvent
    from engine.dsl.event_trigger_type import EventTriggerType
    import engine.runner.operations.triggers.dispatch.core as CORE

    seen = []

    class _NoId(TriggeredAbility):
        event_id = EventTriggerType.Attack
        TRIGGERED_ABILITY_ID = None

        def matches(self, state, ev):
            return True

        def execute_behaviour(self, state, ev):
            return {"ok": True}

    class _Listener(TriggeredAbility):
        event_id = EventTriggerType.UnitTriggeredAbility
        TRIGGERED_ABILITY_ID = None

        def matches(self, state, ev):
            seen.append(getattr(state, "trigger_ability_type", None))
            return False

    state = State()
    state.add_entity(1).add_component(UnitComponent("spy", True))
    saved = (CORE.collect_triggered_abilities, CORE.collect_global_triggers,
             CORE.collect_effect_triggers)
    CORE.collect_triggered_abilities = lambda s: [_NoId(1), _Listener(1)]
    CORE.collect_global_triggers = lambda: []
    CORE.collect_effect_triggers = lambda s: []
    try:
        out = CORE.evaluate_trigger_operation(state, TriggerEvent(
            EventTriggerType.Attack, 1, 2, ranged=False, profile=None))
    finally:
        (CORE.collect_triggered_abilities, CORE.collect_global_triggers,
         CORE.collect_effect_triggers) = saved

    assert out == [{"ok": True}]
    assert seen == [], "un On(0xd) a ete publie pour une entree sans TRIGGERED_ABILITY_ID"
    assert state.trigger_ability_type is None
