"""probe #27 -- triage des overrides CalculateCustomUtility NON portes.

Pour chaque ability id candidate : nom, presence dans le registre du moteur
(`engine.playbook.REGISTRY`), route de dispatch offline (`state_bridge.
_is_attack_ability` = `constants.damageProfile` present ET non-NonComparable),
et PORTEURS (unites du gameconfig qui referencent l'ability) avec leur `kind`
et leur presence dans le pool spawnable du rank courant.

Sortie ASCII pure. Usage : python probe_27_residual_triage.py
"""
from __future__ import annotations

import json
import sys
import urllib.request

import gameconfig as GC
import engine.playbook as PB
from engine.ai import state_bridge as SB

HOST = "http://127.0.0.1:8765"

# Overrides CalculateCustomUtility recenses (inventaire re-derive du binaire).
CANDIDATES = [
    ("MortisRound", 1004),
    ("SorcerousFacade", 1100),
    ("PlagueburstMortar", 1169),
    ("DaemonicOrdnance", 1148),
    ("Stikkbomb", 1051),
    ("MalleusRocketLauncher", 1142),
    ("PlasmaGrenade", 1098),
    ("Chronometron", 1226),
    ("DevoutPush", 1053),
    ("ForwardObservers", 1185),
    ("HealingBalms_Heal", 1212),
    ("SavageEchoes", 1230),
    ("AmuletOfTheVoidwyrm", None),          # id resolu par nom ci-dessous
    ("MortarionsPlagueWind", 1093),
    ("InstrumentsOfVengeance", 1215),
    ("MartialExemplar", 1216),
    ("TheLionsWrath", 1217),
]


def _pool() -> set:
    """Pool spawnable du rank courant (rl_duel --list-pool passe par le live ;
    ici on lit le catalogue de la seed BC, meme source)."""
    import rl_duel
    try:
        bc = rl_duel._load_seed_bc()
    except Exception as exc:  # noqa: BLE001
        print("WARN seed-bc indisponible: %s" % exc)
        return set()
    ids = set()
    for p in (bc.get("Players") or []):
        for u in (p.get("Units") or []):
            uid = (u.get("UnitId") or "").split(":")[0]
            if uid:
                ids.add(uid)
    return ids


def main() -> int:
    idx = GC._index()
    pool = _pool()
    print("catalogue seed-bc : %d unites" % len(pool))

    for label, aid in CANDIDATES:
        if aid is None:
            aid = GC.ability_id(label)
        name = GC.ability_name(int(aid)) if aid else None
        a = GC.ability(label) or (GC.ability(name) if name else None) or {}
        acfg = {"constants": a.get("constants") or {},
                "variables": a.get("variables") or {}}
        try:
            is_atk = SB._is_attack_ability(int(aid), acfg) if aid else False
        except Exception:  # noqa: BLE001
            is_atk = False
        ported = aid in PB.REGISTRY if aid else False
        carriers = []
        for kind in ("lineup", "npc", "summons"):
            for uid, u in (idx[kind] or {}).items():
                if label in (u.get("activeAbilities") or []):
                    carriers.append("%s[%s%s]" % (
                        uid, kind, ",POOL" if uid in pool else ""))
        print("%-24s id=%-6s gc=%-5s dp=%-5s attack_route=%-5s PORTE=%-5s"
              " porteurs=%s"
              % (label, aid, bool(a),
                 bool((a.get("constants") or {}).get("damageProfile")),
                 is_atk, ported,
                 ", ".join(carriers) or "AUCUN (granted/passif/env ?)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
