"""`engine.entities.traits` — exploitation des TRAITS dans le raw damage prediction (§17.17), en hiérarchie
de classes (BaseTrait + sous-classes + factory + registre), même patron que `entities.effects`.

API :
  • `BaseTrait` / sous-classes (combat.py) — 1 classe par trait, override des points du contrat exploités.
  • `TraitFactory` / `TRAIT_CLASSES` — instancie depuis un nom gameconfig.
  • agrégateurs (itèrent une liste de traits, somment/combinent leur contribution à un point du contrat) :
    `attacker_bonus_hits`, `attacker_pierce_bonus`, `attacker_ignores_armor`,
    `target_hit_multiplier`, `target_damage_cap`.
"""
from __future__ import annotations

from collections.abc import Mapping


__all__ = [
    "attacker_bonus_hits", "attacker_pierce_bonus", "attacker_ignores_armor",
    "target_hit_multiplier", "target_damage_cap",
]


def attacker_bonus_hits(traits, ctx: Mapping | None = None) -> int:
    return sum(t.as_attacker_bonus_hits(ctx) for t in (traits or []))


def attacker_pierce_bonus(traits, ctx: Mapping | None = None) -> int:
    return sum(t.as_attacker_pierce_bonus(ctx) for t in (traits or []))


def attacker_ignores_armor(traits, ctx: Mapping | None = None) -> bool:
    return any(t.as_attacker_ignores_armor(ctx) for t in (traits or []))


def target_hit_multiplier(traits, ctx: Mapping | None = None) -> int:
    """Multiplicateur de coups si la CIBLE a un trait hit-twice (max des traits ; 1 par défaut)."""
    return max([1, *[t.as_target_hit_multiplier(ctx) for t in (traits or [])]])


def target_damage_cap(traits, per_hit_damage: int, ctx: Mapping | None = None) -> int | None:
    """Plafond dégât/coup le PLUS BAS imposé par les traits de la cible (Resilient/Impervious). None si aucun."""
    caps = [c for c in (t.as_target_damage_cap(per_hit_damage, ctx) for t in (traits or []))
            if c is not None]
    return min(caps) if caps else None
