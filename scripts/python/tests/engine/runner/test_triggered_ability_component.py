"""TriggeredAbilityComponent (#140 Slice 1) — semantique du compteur phase, test PURE offline.

Mirror natif TriggeredAbilityComponent (@180faba40) : try_add / get_times_triggered_this_phase /
mark_as_triggered / reset_phase / has_been_triggered. Pas de live (structure de donnees pure) ; la
validation COMPORTEMENTALE du cap (borne la recursion Psyker + non-regression) vient en Slice 4.
"""
from __future__ import annotations

from engine.runner.components import TriggeredAbilityComponent


def test_try_add_idempotent():
    c = TriggeredAbilityComponent()
    assert c.try_add("Psyker") is True
    assert c.try_add("Psyker") is False        # deja present -> no-op
    assert c.try_add("ActOfFaith") is True
    assert set(c.entries) == {"Psyker", "ActOfFaith"}


def test_get_times_absent_key_is_zero():
    c = TriggeredAbilityComponent()
    # cle absente -> 0 (TryGetValue echoue), pas d'exception
    assert c.get_times_triggered_this_phase("Nope") == 0
    c.try_add("Psyker")
    assert c.get_times_triggered_this_phase("Psyker") == 0


def test_mark_increments_total_and_phase():
    c = TriggeredAbilityComponent()
    c.try_add("Psyker")
    c.mark_as_triggered("Psyker")
    c.mark_as_triggered("Psyker")
    assert c.get_times_triggered_this_phase("Psyker") == 2
    assert c.entries["Psyker"].total == 2
    assert c.has_been_triggered("Psyker") is True


def test_mark_absent_key_is_noop():
    c = TriggeredAbilityComponent()
    c.mark_as_triggered("Nope")                # no-op (pas d'entree) : pas d'exception, rien cree
    assert "Nope" not in c.entries
    assert c.has_been_triggered("Nope") is False


def test_reset_phase_zeroes_phase_not_total():
    c = TriggeredAbilityComponent()
    c.try_add("Psyker"); c.try_add("ActOfFaith")
    for _ in range(5):
        c.mark_as_triggered("Psyker")
    c.mark_as_triggered("ActOfFaith")
    c.reset_phase()
    # times_this_phase remis a 0 pour TOUTES les entrees...
    assert c.get_times_triggered_this_phase("Psyker") == 0
    assert c.get_times_triggered_this_phase("ActOfFaith") == 0
    # ...mais total ET has_triggered conserves.
    assert c.entries["Psyker"].total == 5
    assert c.entries["ActOfFaith"].total == 1
    assert c.has_been_triggered("Psyker") is True


def test_cap_semantics_51():
    """Le gate natif = get_times_triggered_this_phase < 0x33 (51). Apres 51 marques, le compteur
    atteint 51 -> le gate `< 51` bloque le 52e fire ; reset_phase rouvre."""
    c = TriggeredAbilityComponent()
    c.try_add("Psyker")
    fired = 0
    for _ in range(200):
        if c.get_times_triggered_this_phase("Psyker") < 0x33:   # gate <51
            c.mark_as_triggered("Psyker")
            fired += 1
        else:
            break
    assert fired == 51, f"cap devrait autoriser exactement 51 fires/phase, obtenu {fired}"
    assert c.get_times_triggered_this_phase("Psyker") == 51
    c.reset_phase()
    assert c.get_times_triggered_this_phase("Psyker") == 0      # phase suivante : compteur rouvert
