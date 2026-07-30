"""Probe #N8b -- INVENTAIRE des consommateurs du vecteur `On(0x17 = TurnEnd = 23)`.

Enonce du cas : `IdunBattle.Operations.EndTurnOperation$$Execute` execute le vecteur de triggers
`On(0x17)` AVANT `IdunBattle.Operations.EndTurnOperation$$RefreshEffects` (le tick d'un tour des
effets a duree). Le port faisait l'inverse. Deplacer le tick change le verdict de TOUS les
consommateurs de ce vecteur, pas seulement de PileIn (bespoke) -- ce probe les ENUMERE depuis les
registres reels (`TRAIT_TRIGGERS`, `ABILITY_TRIGGERS`, `ACTIVE_ABILITY_TRIGGERS`, `EFFECT_TRIGGERS`,
`BEHAVIOUR_TRAIT_TRIGGERS`) plutot que de citer un commentaire.

Sortie ASCII stricte (cp1252). Aucune session live requise : lecture pure des registres.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.dsl.event_trigger_type import EventTriggerType  # noqa: E402

# #283 : etait `TURN_END = 23`. Juste sur les deux builds versionnes (23 < 40, sous le point de
# retrait d'`ArmorChanged`) -- et c'est precisement ce qui le rendait dangereux : rien n'aurait
# signale son invalidation au prochain build, exactement comme `CAPTURE_POINT = 24` de #272.
TURN_END = int(EventTriggerType.TurnEnd)


def _events_of(cls) -> list[int]:
    """Instancie l'entree du registre (owner_id fictif) et rend les event ids ECOUTES.
    `event_id` est un attribut de CLASSE sur la plupart des entrees ; `event_ids` (tuple) existe
    sur les tile-effects multi-events. On tente la classe d'abord, l'instance en repli."""
    ids: list[int] = []
    for holder in (cls, None):
        src = holder
        if src is None:
            try:
                src = cls(1)
            except Exception:
                return ids
        eid = getattr(src, "event_id", None)
        eids = getattr(src, "event_ids", None)
        if eid is not None:
            try:
                ids.append(int(eid))
            except Exception:
                pass
        if eids:
            for x in eids:
                try:
                    ids.append(int(x))
                except Exception:
                    pass
        if ids:
            return ids
    return ids


def main() -> int:
    from engine.runner.operations.triggers.dispatch.registry import (
        TRAIT_TRIGGERS, ABILITY_TRIGGERS, ACTIVE_ABILITY_TRIGGERS, EFFECT_TRIGGERS)
    from engine.runner.operations.behaviour import BEHAVIOUR_TRAIT_TRIGGERS

    registries = [
        ("TRAIT_TRIGGERS", TRAIT_TRIGGERS),
        ("ABILITY_TRIGGERS", ABILITY_TRIGGERS),
        ("ACTIVE_ABILITY_TRIGGERS", ACTIVE_ABILITY_TRIGGERS),
        ("BEHAVIOUR_TRAIT_TRIGGERS", BEHAVIOUR_TRAIT_TRIGGERS),
        ("EFFECT_TRIGGERS", EFFECT_TRIGGERS),
    ]
    total = 0
    hits: list[tuple] = []
    for label, reg in registries:
        for key, classes in reg.items():
            for cls in classes:
                total += 1
                ids = _events_of(cls)
                if TURN_END in ids:
                    hits.append((label, key, cls.__name__, ids))
    print("== probe N8b : consommateurs de On(0x17 = TurnEnd = 23) ==")
    print("entrees de registre balayees : %d" % total)
    print("consommateurs On(TurnEnd) trouves : %d" % len(hits))
    for (label, key, name, ids) in sorted(hits):
        print("  %-24s %-28s %-42s events=%s" % (label, key, name, ids))
    print("")
    print("+ BESPOKE (hors registre, code en dur dans end_turn_summon_triggers) : PileIn")
    print("  gate = OwnerHasFinishedMinTurns(2) & IsUnitWithStatAmount(Health Cur == Max)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
