"""Tranche 0 — modèle d'état du runner CONFRONTÉ au LIVE.

Le runner Python charge son état initial depuis un snapshot live (decisionView +
observeBattle) du runner fraîchement bâti. Ce harnais valide que le modèle ECS
REPRÉSENTE FIDÈLEMENT l'état live (aucun champ perdu/faussé) — fondation des tranches
suivantes (move/damage/… réutiliseront load_state + snapshot + diff pour le replay-diff).

Property-based, indépendant version/seed : on lit l'état live et on vérifie
génériquement sur toutes les unités. Skip si pas de session (cf. conftest).
"""
from __future__ import annotations

import pytest

from engine.runner.components import PositionComponent, HealthComponent, OwnerComponent
from engine.runner.snapshot import load_state, snapshot, snapshot_live, diff


@pytest.fixture(scope="session")
def live_views(rpc, live_runner):
    """Snapshot live (decisionView + observeBattle) du runner bâti."""
    rid = live_runner
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    if not (isinstance(dv, dict) and dv.get("ok") and (dv.get("units"))):
        pytest.skip(f"decisionView KO/vide: {str(dv)[:200]}")
    if not (isinstance(ob, dict) and ob.get("ok")):
        pytest.skip(f"observeBattle KO: {str(ob)[:200]}")
    return dv, ob


def test_state_loads_every_live_unit(live_views):
    """load_state reconstruit une entité par unité live, avec ses composants d'état."""
    dv, ob = live_views
    st = load_state(dv, ob)
    live_units = [u for u in (dv.get("units") or []) if u.get("id") is not None]
    assert len(st.entities) == len(live_units), "comptes d'unités divergents"
    assert st.current_player_id == dv.get("currentPlayer")
    for u in live_units:
        e = st.get_entity(u["id"])
        assert e is not None, f"u{u['id']} absente de l'état chargé"
        assert e.has_component(OwnerComponent)
        if u.get("alive") and (u.get("pos") or {}).get("col") is not None:
            assert e.has_component(PositionComponent), f"u{u['id']} sans position"
            assert e.has_component(HealthComponent), f"u{u['id']} sans HP"


def test_load_snapshot_consistent_with_live(live_views):
    """Cross-check : snapshot(load_state(...)) == snapshot_live(...) (chemins
    indépendants). Garantit que loader + snapshot capturent l'état sans le fausser."""
    dv, ob = live_views
    via_state = snapshot(load_state(dv, ob))
    direct = snapshot_live(dv, ob)
    d = diff(direct, via_state)
    assert not d, "loader/snapshot incohérents vs live:\n  " + "\n  ".join(d[:20])


def test_health_is_sane(live_views):
    """Garde-fou : hp <= hpMax et hp >= 0 pour toute unité vivante chargée."""
    dv, ob = live_views
    st = load_state(dv, ob)
    for eid, e in st.entities.items():
        hc = e.get_component(HealthComponent)
        if hc is None or hc.hp is None or hc.hp_max is None:
            continue
        assert 0 <= hc.hp <= hc.hp_max, f"u{eid} hp={hc.hp} hpMax={hc.hp_max} incohérent"
