"""Traits de combat exploités par le raw damage prediction — 1 classe par trait (gameconfig name, VA citée).

Override UNIQUEMENT les points du contrat (§17.17) réellement exploités, lus en ghidra. Magnitudes/formules
non encore RE'd → no-op + TODO (on n'invente pas). Traits confirmés présents seed-777 : GetStuckIn, Resilient,
Impervious, HeavyWeapon, TerminatorArmour, Parry, BigTarget, RapidAssault, MartialKatah…
"""
from __future__ import annotations

from collections.abc import Mapping

from .base import BaseTrait


class GetStuckInTrait(BaseTrait):
    """`GetStuckIn` (ork) — coups bonus. `GetStuckInAbility.CreateBehaviour` @180f83280 =
    `AddBonusHitsToCurrentHitGroup` sous `Maybe(GetBonusHitChance)` ; trigger @180f83350 = `On(8) &
    CurrentHitIndex IsOdd & OwnerIsCaster & !(MinDistance>2)` → **portée 2 (PAS mêlée-only)** : s'applique
    aussi au tir si la cible est à ≤2 hex ; `GetBonusHitChance` @180f83460 = `If(orks_adj≥2 OU
    units_adj≥4, chance_2[key0x33]=100, chance[key0x2a]=30)` ; les comptes = unités adjacentes à la CIBLE
    (AdjacentUnits(target) → UnitsFromFaction Orks=5 / Friends-of-caster).
    Ajoute **+1 coup par coup d'index IMPAIR** = `+floor(hits/2)` (hits = série APRÈS PowerTrip, AVANT
    GetStuckIn). VÉRIFIÉ live u90 : base 3 + PowerTrip 1 = 4 → +floor(4/2)=2 → **6** (per-bout ×6 = oracle,
    2 cibles §17.21). ⚠ N'est PAS ×2 (l'ancien doubling était faux : pour base impair il sur-comptait).

    **PRÉDICTION OPTIMISTE (clé) :** la prédiction compte ces coups bonus dès que la condition STRUCTURELLE
    du trigger tient (`!(MinDistance>2)` = cible ≤2 hex) — INDÉPENDAMMENT de la chance (`GetBonusHitChance` =
    30% défaut / 100% si ≥2 orks OU ≥4 amis ADJACENTS à la cible). La chance ne gate QUE le tirage réel à
    l'exécution ; oracle u90→u86 (dist 2, 1 ami adjacent = condition 30%) montre dmgMin ET dmgMax à 6 coups
    ⇒ le moteur de prédiction résout le `Maybe(chance)` comme « atterrit » (cf. predOptimistic). Donc on fire
    sur within-range-2 seul. Les comptes orks/amis restent dans ctx (informatifs : 30 vs 100% réel), non gate.
    ⚠ positionnel : sans `attacker_within_range2` (position d'attaque absente) → 0 (pas d'invention)."""

    def as_attacker_bonus_hits(self, ctx: Mapping | None = None) -> int:
        c = ctx or {}
        if not c.get("attacker_within_range2"):   # !(MinDistance>2) = cible à ≤2 hex (trigger structurel)
            return 0
        base_hits = int(c.get("base_hits") or 0)  # hits APRÈS PowerTrip, AVANT GetStuckIn
        if base_hits <= 0:
            return 0
        # +1 coup par coup d'index impair = floor(hits/2) ; prédiction optimiste (chance résolue « atterrit »).
        return base_hits // 2


class ResilientTrait(BaseTrait):
    """`Resilient` — plafond de dégât PAR COUP côté cible (`ApplyResilientTraitDamageLimit`, appelée par
    `ApplyTraitDamageLimitsToDamage` @18102c650). Doctrine : NE survit PAS au multi-coup (chaque coup capé,
    mais N coups cumulent). ⚠ formule exacte du cap NON encore RE'd (ApplyResilientTraitDamageLimit) → no-op + TODO."""

    def as_target_damage_cap(self, per_hit_damage: int, ctx: Mapping | None = None) -> int | None:
        # TODO: RE ApplyResilientTraitDamageLimit (cap = ? par coup) puis retourner le plafond.
        return None


class ImperviousTrait(BaseTrait):
    """`Impervious` — plafond de dégât côté cible (`ApplyImperviousTraitDamageLimit`, via
    `ApplyTraitDamageLimitsToDamage` @18102c650, branche `param_2==1`). ⚠ formule NON RE'd → no-op + TODO."""

    def as_target_damage_cap(self, per_hit_damage: int, ctx: Mapping | None = None) -> int | None:
        # TODO: RE ApplyImperviousTraitDamageLimit puis retourner le plafond.
        return None
