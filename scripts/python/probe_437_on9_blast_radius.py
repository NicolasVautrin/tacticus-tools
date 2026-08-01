"""#437 -- RAYON DE SOUFFLE du foyer d'emission `On(9 = EventTriggerType.Attack)`.

Le natif emet `On(9)` depuis `IdunBattle.Operations.FinishAttackOperation$$Execute`,
INCONDITIONNELLEMENT, pour TOUTE attaque -- y compris celle qu'un TRIGGER declenche (tir
d'overwatch, riposte). Le port l'emet au niveau MESSAGE / sortie d'operation
(`dispatch/attack.py::after_hit_normal_attack` et `::after_hit_ability_attack`), donc une
attaque nee d'un trigger ne le traverse pas.

AVANT de toucher au foyer d'emission, il faut savoir QUI ecoute -- un correctif au foyer les
touche TOUS a la fois. Ce probe recense, DEPUIS LE CODE (jamais une liste recopiee) :

  etape 1 : toutes les classes-triggers du port qui ecoutent `event_id == 9` (ou dont
            `event_ids` contient 9), avec leur VOIE de registration et la CLE du registre ;
  etape 2 : les porteurs de chaque cle (gameconfig : trait / passiveAbility / activeAbility /
            relicAbility), ventiles kind (lineup HERO / MoW / npc / summon) ;
  etape 3 : les SITES d'emission de `On(9)` cote port (`TriggerEvent(EventTriggerType.Attack`),
            pour verifier qu'aucun site neuf n'a ete ajoute hors des deux foyers connus.

Sortie ASCII pure (console cp1252). rc = 0 (inventaire, pas un cliquet).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import gameconfig as GC  # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType  # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import (  # noqa: E402
    TRAIT_TRIGGERS, ABILITY_TRIGGERS, ACTIVE_ABILITY_TRIGGERS,
    RELIC_ABILITY_TRIGGERS, GLOBAL_TRIGGERS, EFFECT_TRIGGERS)

ON_ATTACK = int(EventTriggerType.Attack)          # 9


def _listens(cls) -> bool:
    """La classe ecoute-t-elle `On(9)` ? Mirror du gate de `evaluate_trigger_operation` :
    `entry.event_id != ev.event_id and ev.event_id not in getattr(entry, 'event_ids', ())`."""
    ev_id = getattr(cls, "event_id", None)
    if ev_id is not None and int(ev_id) == ON_ATTACK:
        return True
    return ON_ATTACK in tuple(int(x) for x in (getattr(cls, "event_ids", ()) or ()))


def _collect() -> list[tuple[str, str, type]]:
    """(voie, cle, classe) pour toute classe-trigger qui ecoute On(9)."""
    out: list[tuple[str, str, type]] = []
    for voie, reg in (("trait", TRAIT_TRIGGERS), ("passive", ABILITY_TRIGGERS),
                      ("active", ACTIVE_ABILITY_TRIGGERS), ("relic", RELIC_ABILITY_TRIGGERS)):
        for key, classes in reg.items():
            for cls in classes:
                if _listens(cls):
                    out.append((voie, str(key), cls))
    for cls in GLOBAL_TRIGGERS:
        if _listens(cls):
            out.append(("global", "-", cls))
    for eff_type, classes in EFFECT_TRIGGERS.items():
        for cls in classes:
            if _listens(cls):
                out.append(("effect", str(int(eff_type)), cls))
    return out


def _carriers(voie: str, key: str) -> dict[str, list[str]]:
    """Porteurs gameconfig de la cle, ventiles par `kind`. Vide pour les voies non derivables
    du gameconfig (`global`, `effect` : l'effet est POSE en bataille, son porteur se remonte par
    son poseur -- fait a la main dans le rapport)."""
    field = {"trait": "traits", "passive": "passiveAbilities",
             "active": "activeAbilities", "relic": "relicAbilities"}.get(voie)
    if field is None:
        return {}
    out: dict[str, list[str]] = {}
    for kind, uids in (GC.all_unit_ids() or {}).items():
        for uid in uids:
            u = GC.unit(uid) or {}
            if key in (u.get(field) or []):
                out.setdefault(str(kind), []).append(str(uid))
    return out


_EMIT_RE = re.compile(r"TriggerEvent\(\s*(?:int\()?EventTriggerType\.Attack(?![A-Za-z0-9_])")


def _emission_sites(root: Path) -> list[tuple[str, int, str]]:
    """Les sites qui CONSTRUISENT un `TriggerEvent(EventTriggerType.Attack, ...)` dans `engine/`."""
    hits: list[tuple[str, int, str]] = []
    for p in sorted((root / "engine").rglob("*.py")):
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(lines, 1):
            if _EMIT_RE.search(line):
                hits.append((str(p.relative_to(root)), i, line.strip()))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="#437 blast radius of On(9 = Attack)")
    ap.add_argument("--no-carriers", action="store_true", help="skip gameconfig carrier lookup")
    args = ap.parse_args()

    print("=" * 78)
    print("ETAPE 1 -- ECOUTEURS de On(9 = EventTriggerType.Attack) dans le port")
    print("=" * 78)
    listeners = _collect()
    print("total: %d classes-triggers" % len(listeners))
    print("")
    for voie, key, cls in sorted(listeners, key=lambda t: (t[0], t[1], t[2].__name__)):
        print("  [%-7s] %-28s %s" % (voie, key, cls.__name__))
        print("            module: %s" % cls.__module__)
    print("")

    if not args.no_carriers:
        print("=" * 78)
        print("ETAPE 2 -- PORTEURS gameconfig par cle (kind: nb, exemples)")
        print("=" * 78)
        for voie, key, cls in sorted(listeners, key=lambda t: (t[0], t[1], t[2].__name__)):
            if voie in ("global", "effect"):
                print("  [%-7s] %-28s -> voie NON derivable du gameconfig (poseur a remonter)"
                      % (voie, key))
                continue
            car = _carriers(voie, key)
            if not car:
                print("  [%-7s] %-28s -> 0 porteur gameconfig" % (voie, key))
                continue
            tot = sum(len(v) for v in car.values())
            print("  [%-7s] %-28s -> %d porteurs" % (voie, key, tot))
            for kind in sorted(car):
                ids = sorted(car[kind])
                print("            %-8s %3d  %s" % (kind, len(ids), ", ".join(ids[:6])
                                                    + (" ..." if len(ids) > 6 else "")))
        print("")

    print("=" * 78)
    print("ETAPE 3 -- SITES D'EMISSION de On(9) cote port")
    print("=" * 78)
    for rel, ln, txt in _emission_sites(_HERE):
        print("  %s:%d" % (rel, ln))
        print("      %s" % txt)
    print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
