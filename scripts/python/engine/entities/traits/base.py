"""`BaseTrait` — mirror de l'exploitation des TRAITS dans le raw damage prediction (gqfc5mff6c, §17.17).

Contrairement aux effets (matérialisés + évolutifs), un trait est **inné/statique** : il vient de
`gameconfig.unit(id).traits` (présent tout le combat, jamais retiré). Le jeu l'exploite de DEUX façons
(§17.17) : (1) il accorde des abilities/effets (chemin effets, déjà porté) ; (2) il est **lu DIRECTEMENT
dans `PredictAttackRaw` + ses helpers** via `HasTrait` à des points précis. Cette hiérarchie porte le
chemin (2) : 1 classe par trait (namespace = module), override des points du contrat qu'il exploite.

Contrat (points NOMMÉS du raw prediction où un trait agit — défaut = no-op) :
  • as_attacker_bonus_hits      — coups bonus attaquant (GetStuckIn : AddBonusHitsToCurrentHitGroup).
  • as_attacker_pierce_bonus    — +pierce attaquant (`GetPiercingRatio(profil, traits)` : lasCannon 0x3e9/0x3f8).
  • as_attacker_ignores_armor   — flag ignore-armure (PredictAttackRaw @2227 `HasTrait 0x420 & HasEffect 0x59a`).
  • as_target_hit_multiplier    — cible « frappée 2× » (`GetBaseDamageWithFixedPiercedArmor` HasTrait 0x3f5=1013).
  • as_target_damage_cap        — plafond dégât/coup côté cible (`ApplyTraitDamageLimitsToDamage` @18102c650 :
                                  Resilient/Impervious/GroupUnit + cap triggered 0x5d4).
`ctx` = contexte de prédiction (dict : rôle, positions/adjacence, max_hp, profil, effets actifs…) — chaque
trait lit ce dont il a besoin.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass
class BaseTrait:
    """Un trait matérialisé (inné). `name` = nom gameconfig (clé du registre). Sous-classe = 1 trait."""
    name: str

    # ── attaquant ───────────────────────────────────────────────────────────────────────────────────
    def as_attacker_bonus_hits(self, ctx: Mapping | None = None) -> int:
        """Coups bonus accordés à l'attaque (transitoire). 0 par défaut."""
        return 0

    def as_attacker_pierce_bonus(self, ctx: Mapping | None = None) -> int:
        """+pierce ratio attaquant (clampé 0..100 en aval). 0 par défaut."""
        return 0

    def as_attacker_ignores_armor(self, ctx: Mapping | None = None) -> bool:
        """Flag ignore-armure/true-damage (cf. PredictAttackRaw @2227). False par défaut."""
        return False

    # ── cible / défenseur ─────────────────────────────────────────────────────────────────────────────
    def as_target_hit_multiplier(self, ctx: Mapping | None = None) -> int:
        """Multiplicateur de coups quand l'unité est CIBLE (hit-twice = 2). 1 par défaut."""
        return 1

    def as_target_damage_cap(self, per_hit_damage: int, ctx: Mapping | None = None) -> int | None:
        """Plafond du dégât PAR COUP subi (Resilient/Impervious). None = pas de plafond."""
        return None
