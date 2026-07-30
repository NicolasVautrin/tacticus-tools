"""#301 -- sur le vecteur MORT, `CurrentAbility` est VIDE et `TriggeringAbility` porte le killTrigger.

    `CurrentAbility`    `AbilityEntities+0x60`  ->  `state.triggering_ability`   (nom historique)
    `TriggeringAbility` `AbilityEntities+0x98`  ->  `state.trigger_ability_type`

`IdunBattle.Operations.KillUnitOperation$$Execute` batit UN SEUL `AbilityEntities` (value type de
0x128 octets) par un `memset(0)` suivi de quatre ecritures seulement -- killer, killed, les deux
listes de tuiles, et le bloc `+0x98..+0xb4` copie de `KillUnitOptions+0x04` -- puis publie CETTE
struct, jamais remodifiee, sur `On(1)`, `On(2)`, `On(0)`, `On(0x36 = 54)` et `On(0x35 = 53)`.

Consequence, et c'est ce que ces gardes verrouillent :
  * tout `CurrentAbilityIs` est FAUX sur les cinq evenements de mort -- le champ n'y est jamais ecrit ;
  * `TriggeringAbilityIs` / `TriggeringEffectIs` / `TriggeringAbilityIsNone` y comparent le
    `killTrigger` porte par l'entree de `IdunBattle.Core.MatchState$$AddDeath`.

Le port faisait l'INVERSE (le killTrigger sur `+0x60`, `+0x98` laisse vide). Degradation PERMISSIVE
donc muette : aucun test ne rougissait. Ces gardes sont ce qui la rend detectable.

TOUT EST OFFLINE et deterministe (zero RNG, zero runner) : la question posee est « quel canal porte
quoi », et elle se tranche sur un `State` nu. La non-regression du COMPORTEMENT observable, elle,
est portee par les tests live existants du vecteur mort (`test_haze_of_corruption_transfer_live.py`,
`test_death_queue_ordering_live.py`) et par `probe_220_haze_bonded_chain.py`, dont le gate
anti-chaine `NOT TriggeringEffectIs(0x435)` CONSOMME ce canal.
"""
from __future__ import annotations

import pytest

import probe_301_kill_unit_trigger_channels as KUC


def test_the_two_channels_are_distinct_slots_on_state():
    """Garde de structure : `+0x98` a son PROPRE slot. Si quelqu'un refond les deux canaux en un
    seul champ, ce fix redevient un no-op silencieux -- et ce test rougit avant."""
    from engine.runner.state import State
    assert "triggering_ability" in State.__slots__
    assert "trigger_ability_type" in State.__slots__
    st = State()
    st.triggering_ability = 1
    assert st.trigger_ability_type is None, "ecrire +0x60 a touche +0x98 : les canaux sont aliases"
    st.trigger_ability_type = 2
    assert st.triggering_ability == 1, "ecrire +0x98 a touche +0x60 : les canaux sont aliases"


def test_death_vector_leaves_current_ability_empty(kill_unit_trigger_channel_case):
    """LE FAIT PRINCIPAL : sur le vecteur mort, `+0x60` est VIDE pour un trigger sans id.

    Le montage place un observateur PUR (aucun `TRIGGERED_ABILITY_ID`, comme les 79 classes du
    registre qui n'en declarent pas) sur `On(1)` et `On(2)`. Le natif memset l'`AbilityEntities` :
    ces sites doivent voir `None`, quelle que soit la valeur ambiante d'avant le drain."""
    r = kill_unit_trigger_channel_case()
    for site in ("K.matches", "K.exec", "N.matches"):
        got = KUC.site(r, site)
        assert got[0] is None, (
            f"'{site}' voit +0x60 = {got[0]} ; le memset de "
            f"IdunBattle.Operations.KillUnitOperation$$Execute l'exige VIDE")


def test_death_vector_publishes_the_kill_trigger_on_the_0x98_channel(kill_unit_trigger_channel_case):
    """LE SECOND FAIT : `+0x98` porte le `killTrigger`, sur les DEUX evenements observes.

    Chaine de valeur re-derivee : `MatchState$$AddDeath(..., killTrigger, ...)` enqueue,
    `u003CVerifyDeathsu003Eb__0` n'ecrase que `options[0x04..0x20)` avec ce killTrigger,
    `OperationProcessor$$KillUnit` recopie les 0x48 octets, `KillUnitOperation$$Execute` pose
    `+0x98..+0xb4 = options[0x04..0x20)`."""
    r = kill_unit_trigger_channel_case()
    for site in ("K.matches", "K.exec", "N.matches", "N.exec"):
        got = KUC.site(r, site)
        assert got[1] == KUC.KILL_TRIGGER, (
            f"'{site}' voit +0x98 = {got[1]} ; attendu le killTrigger {KUC.KILL_TRIGGER}")


def test_the_two_channels_separate_under_a_chained_triggered(kill_unit_trigger_channel_case):
    """LE LIVRABLE : deux valeurs NON NULLES DIFFERENTES au meme instant.

    Une triggered QUI PORTE UN ID (`N`) declenchee par `On(2)` : `BaseTriggeredAbility$$Execute`
    ecrit `+0x60 = this.Id` avant son behaviour, tandis que `+0x98` garde le killTrigger publie par
    `KillUnitOperation`. C'est la seule configuration ou un port qui confond les deux champs -- ou
    qui les alimenterait tous deux avec le killTrigger -- est detectable."""
    r = kill_unit_trigger_channel_case()
    assert KUC.site(r, "N.exec") == (KUC.N_ID, KUC.KILL_TRIGGER)
    assert r["separated"], "aucun site ne separe les canaux (deux non-nuls differents)"


def test_both_channels_are_restored_after_the_drain(kill_unit_trigger_channel_case):
    """PORTEE : le drain ne fait fuir NI l'un NI l'autre.

    Le natif jette l'`AbilityEntities` du `KillUnitOperation` avec l'operation ; le port n'a que des
    canaux globaux, donc il doit restaurer. `+0x60` revient a l'AMBIANT d'avant le drain (une
    triggered englobante peut etre en cours), `+0x98` revient a `None`."""
    r = kill_unit_trigger_channel_case()
    assert r["final"] == (KUC.AMBIENT, None)


def test_the_probe_verdict_agrees(kill_unit_trigger_channel_case):
    """Un seul foyer d'assertion : le verdict du probe dit la MEME chose que les gardes ci-dessus.
    Sans ce test, probe et suite peuvent diverger silencieusement."""
    ok, msg = KUC.verdict(kill_unit_trigger_channel_case())
    assert ok, msg


@pytest.mark.parametrize("mutation", sorted(KUC.MUTATIONS))
def test_each_mutation_reddens_the_montage(kill_unit_trigger_channel_case, mutation):
    """CONTRE-EPREUVES : chacune neutralise une moitie du fix et DOIT rougir.

    `legacy` = l'etat exact d'avant #301 (killTrigger sur `+0x60`, `+0x98` vide) ; `both` = les deux
    canaux alimentes (ce qui rendrait `CurrentAbilityIs` satisfiable sur la mort) ; `nowipe` =
    `+0x98` correct mais `+0x60` non efface (l'ambiant fuit dans la mort) ; `persist` = pas de
    restauration de `+0x98`. Une garde qui ne rougit sur aucune mutation ne garde rien."""
    ok, msg = KUC.verdict(kill_unit_trigger_channel_case(mutate=mutation))
    assert not ok, f"la mutation '{mutation}' n'a RIEN casse -- le montage ne discrimine pas"
    assert msg.startswith("ROUGE"), msg


def test_mutations_have_distinct_signatures(kill_unit_trigger_channel_case):
    """ANTI-CONTRE-EPREUVE FOURRE-TOUT : les quatre mutations doivent rougir pour QUATRE raisons
    differentes. Si deux d'entre elles rendaient le meme message, l'une des deux ne testerait rien
    de propre et le montage serait plus faible qu'il n'en a l'air."""
    msgs = {m: KUC.verdict(kill_unit_trigger_channel_case(mutate=m))[1]
            for m in KUC.MUTATIONS}
    assert len(set(msgs.values())) == len(KUC.MUTATIONS), \
        f"signatures non distinctes : {msgs}"


def test_haze_gate_reads_the_0x98_channel_not_0x60():
    """LE CONSOMMATEUR PORTE. `HazeCorruption_BonusHitAbility` porte
    `NOT TriggeringEffectIs(0x435)` sur `On(1)` : ce predicat prend le slot `DSLSelectors+0x90`,
    donc `AbilityTypeSelector.TriggeringAbilitySelector$$Select`, donc `AbilityEntities+0x98`.

    `_triggering_ability_or_effect` doit donc lire `state.trigger_ability_type`. Un port qui lirait
    `state.triggering_ability` (ce que faisait le code d'avant #301) resterait FONCTIONNEL tant que
    `_verify_deaths` alimentait CE canal-la -- c'est exactement pourquoi l'erreur etait muette, et
    pourquoi cette garde est cablee sur le canal et non sur le comportement."""
    from engine.runner.state import State
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.loki.haze_of_corruption import (
        _triggering_ability_or_effect, HAZE_DAMAGE_TRANSFER)

    st = State()
    ev = TriggerEvent(int(EventTriggerType.PreUnitDeath), 1, 2,
                      ranged=False, profile=None, killer_id=1, dying_id=2)
    # canal +0x60 seul renseigne -> le gate ne doit RIEN y voir
    st.triggering_ability = HAZE_DAMAGE_TRANSFER
    assert _triggering_ability_or_effect(st, ev) is None, \
        "le gate lit +0x60 : il verrait un declencheur la ou KillUnitOperation n'en publie aucun"
    # canal +0x98 renseigne -> c'est CELUI-LA que le gate lit
    st.triggering_ability = None
    st.trigger_ability_type = HAZE_DAMAGE_TRANSFER
    assert _triggering_ability_or_effect(st, ev) == HAZE_DAMAGE_TRANSFER
    # `ev.triggering_effect` reste PRIORITAIRE (les vecteurs qui le portent explicitement)
    ev2 = TriggerEvent(int(EventTriggerType.PreEffectAdded), 1, 2,
                       ranged=False, profile=None, triggering_effect=999)
    assert _triggering_ability_or_effect(st, ev2) == 999
