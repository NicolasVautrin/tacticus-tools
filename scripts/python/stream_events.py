#!/usr/bin/env python
"""stream_events — décodage des events StreamDispatcher capturés par applyAction.

Les events bruts (RPC) portent `step` (StepType) et `group` (GroupType) en
ORDINAUX, plus `tags` = Dict<TagKey,int> déjà sérialisé avec les NOMS de TagKey
(StringEnumConverter côté jeu → clés lisibles « Attacker_Id », « Amount »…).
Ici on mappe `step`/`group` → noms via `enums.json` (dumpé par le host à
l'inject, source = mêmes enums que dump.cs, vérifié : 4=UnitDamaged,
3=ChangePosition, …) et on flagge l'overwatch (dégât SUBI = réaction ennemie).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_META = ROOT / "frida" / "data" / "meta"

# Effect_Type tags (cf. project_effect_type_attribution, confirmé live).
# L'overwatch n'est PAS un cas spécial : c'est un UnitDamaged avec ce tag, au
# même titre que le DoT. On se contente de LABELLISER l'effect_type pour la
# lecture humaine — la classification se fait par direction (subi / infligé).
OVERWATCH_EFFECT_TYPE = 1009
DOT_EFFECT_TYPE = 5
EFFECT_TYPE_NAMES = {OVERWATCH_EFFECT_TYPE: "overwatch", DOT_EFFECT_TYPE: "dot"}


def effect_label(et) -> str | None:
    """Nom lisible d'un Effect_Type (overwatch/dot), sinon None."""
    return EFFECT_TYPE_NAMES.get(et) if et else None


def _version_key(name: str) -> tuple:
    try:
        return tuple(int(x) for x in name.split("."))
    except ValueError:
        return (0,)


@lru_cache(maxsize=1)
def _enums() -> dict:
    cands = list(_META.glob("*/enums.json"))
    if not cands:
        return {}
    best = max(cands, key=lambda p: _version_key(p.parent.name))
    return json.loads(best.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _step_map() -> dict:
    return (_enums().get("StepType") or {}).get("values") or {}


@lru_cache(maxsize=1)
def _group_map() -> dict:
    return (_enums().get("GroupType") or {}).get("values") or {}


def step_name(i) -> str:
    return _step_map().get(str(i), f"Step#{i}")


def group_name(i) -> str:
    return _group_map().get(str(i), f"Group#{i}")


def _tags(ev: dict) -> dict:
    t = ev.get("tags")
    if not t:
        return {}
    try:
        return json.loads(t) if isinstance(t, str) else dict(t)
    except (ValueError, TypeError):
        return {}


def decode_event(ev: dict) -> str:
    """Une ligne lisible pour un event (group ouvrant / action / group fermant),
    avec indentation par profondeur de scope (suivie par le caller)."""
    k = ev.get("kind")
    if k == "group":
        src = ev.get("source")
        return (f"[{group_name(ev.get('group'))} e={ev.get('entity')}"
                + (f" «{src}»" if src else "") + "]")
    if k == "finish":
        return "[/]"
    tags = _tags(ev)
    tg = " ".join(f"{kk}={vv}" for kk, vv in tags.items())
    return (f"{step_name(ev.get('step'))} e={ev.get('entity')}"
            + (f"  {tg}" if tg else ""))


def decode_lines(events: list, max_lines: int = 60) -> list[str]:
    """Cascade décodée + indentée par nesting de groupes (group ouvre, /  ferme)."""
    out: list[str] = []
    depth = 0
    for ev in (events or [])[:max_lines]:
        k = ev.get("kind")
        if k == "finish":
            depth = max(0, depth - 1)
            out.append("  " * depth + decode_event(ev))
        elif k == "group":
            out.append("  " * depth + decode_event(ev))
            depth += 1
        else:
            out.append("  " * depth + decode_event(ev))
    if events and len(events) > max_lines:
        out.append(f"… (+{len(events) - max_lines} events)")
    return out


def analyze(events: list, my_ids) -> dict:
    """Décode la cascade UNIFORMÉMENT — aucun cas spécial overwatch : c'est un
    UnitDamaged taggé Effect_Type=1009 comme un autre, on le classe par DIRECTION
    et on labellise son effet. my_ids = squadId que JE contrôle.
      - damage   : toutes les UnitDamaged (attacker/target/amount/crit/killed/effect)
      - received : dégâts SUBIS par mes units (target∈moi, attacker∉moi) — inclut
                   l'attaque adverse ET les réactions (overwatch/counter/aura via
                   `effect`). DoT-sur-moi (attacker absent/None) compte aussi.
      - dealt    : dégâts que J'INFLIGE (attacker∈moi) — pendant le tour adverse,
                   c'est ma riposte/overwatch/aura (chacun avec son `effect`).
      - deaths   : entités retirées (RemoveUnit)
      - effects  : Effect_Id reçus (ReceiveEffect)
    `effect` = label de l'Effect_Type (overwatch/dot/None)."""
    my = set(my_ids or [])
    out = {"damage": [], "received": [], "dealt": [],
           "deaths": [], "effects": []}
    # Pile de GROUPES (suivie en marchant la cascade) : c'est le signal qui
    # distingue une attaque MANUELLE (sous un groupe `User_*` = activation
    # commandée) d'une attaque AUTO/PASSIVE (StartTurn, triggered, riposte…).
    # Ex. Kharn = 4 hits sous `StartTurn` (auto TheBetrayer) + 4 sous
    # `User_UseAbility` (manuel) — sans ça on ne voyait pas le « auto + manuel ».
    stack: list[str] = []
    for ev in events or []:
        k = ev.get("kind")
        if k == "group":
            stack.append(group_name(ev.get("group")))
            continue
        if k == "finish":
            if stack:
                stack.pop()
            continue
        if k != "action":
            continue
        step = ev.get("step")
        tags = _tags(ev)
        if step == 4:  # UnitDamaged — événement uniforme
            atk, tgt = tags.get("Attacker_Id"), tags.get("Target_Id")
            manual = any(g.startswith("User_") for g in stack)
            d = {
                "attacker": atk, "target": tgt,
                "amount": tags.get("Amount"),
                "crit": bool(tags.get("Attack_DidCrit")),
                "killed": bool(tags.get("Attack_WasMemberKilled")),
                "ability": tags.get("Active_Ability_Type"),
                "effect_type": tags.get("Effect_Type"),
                "effect": effect_label(tags.get("Effect_Type")),
                # auto/passif = hors activation commandée (StartTurn auto de
                # TheBetrayer, triggered, riposte…). group = groupe englobant
                # le plus externe (StartTurn / User_UseAbility / …).
                "auto": not manual,
                "group": stack[0] if stack else None,
            }
            out["damage"].append(d)
            if atk in my:
                out["dealt"].append(d)
            elif tgt in my:
                out["received"].append(d)
        elif step == 12:  # RemoveUnit
            out["deaths"].append(ev.get("entity"))
        elif step == 16:  # ReceiveEffect
            out["effects"].append(tags.get("Effect_Id"))
    return out


if __name__ == "__main__":
    # Smoke test : map non vide + ordinaux connus.
    assert step_name(4) == "UnitDamaged", step_name(4)
    assert step_name(3) == "ChangePosition"
    assert group_name(11) == "User_MoveUnit"
    assert group_name(12) == "User_UseAbility"
    print(f"stream_events OK — StepType({len(_step_map())}) "
          f"GroupType({len(_group_map())}) chargés ; 4=UnitDamaged, "
          f"11=User_MoveUnit")
