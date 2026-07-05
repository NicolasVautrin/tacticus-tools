"""Agrement offline<->natif du systeme de stats porte (`UnitExtensions.GetStat`).

`combatSnapshot` EST l'oracle natif : il appelle `GetStat` par stat et emet `stats` (Current) +
`statDelta` (Current-Initial) pour toutes les unites. Pour chaque unite de la bataille LIVE : on
seed `UnitStats` offline puis on compare offline `get_stat(Current/Initial/modification)` vs natif
via `compare_unit_stats` (la primitive "comparer offline<->natif a tout moment").

Property-based, version- et seed-independant : agrement EXACT sur TOUTES les unites/stats, quelle
que soit la bataille. Le seed n'est qu'un generateur. Skip si pas de session / snapshot KO.

NB : sur un etat fraichement seede depuis la capture, l'egalite tient par construction -> ce test
est un GARDE-FOU wiring/index/arithmetique/clamp du port. La confrontation "profonde" (offline
evolue independamment, ex. stat-mod applique par une operation) reutilisera `compare_unit_stats`
sur un combatSnapshot FRAIS post-mutation (non-circulaire) quand la couche stat-mod sera cablee.
"""
from __future__ import annotations

import os

from engine.entities import seed_unit_stats, compare_unit_stats


def test_getstat_offline_matches_native(rpc, build_runner):
    """Offline `get_stat` == natif (`combatSnapshot`) pour Current/Initial/modification, exact,
    sur toutes les unites de la bataille."""
    rid = build_runner(os.environ.get("GETSTAT_SEED", "777"))["rid"]
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    assert isinstance(snap, dict) and snap.get("ok"), f"combatSnapshot KO: {str(snap)[:200]}"
    stat_ids = snap.get("statTypes") or {}
    assert stat_ids, "statTypes absent du combatSnapshot (mapping nom->StatType requis)"
    units = snap.get("units") or []
    assert units, "aucune unite dans le combatSnapshot"

    mismatches = []
    checked = 0
    for su in units:
        stats = su.get("stats") or {}
        if not stats:
            continue
        delta = su.get("statDelta") or {}
        us = seed_unit_stats(stats, delta, stat_ids)
        for m in compare_unit_stats(us, stats, delta, stat_ids):
            mismatches.append(f"u{su.get('entityId')}: {m}")
        checked += 1

    assert checked > 0, "aucune unite avec des stats a comparer"
    assert not mismatches, (
        f"ecarts offline<->natif GetStat ({len(mismatches)}) sur {checked} unites:\n"
        + "\n".join(mismatches[:40]))
