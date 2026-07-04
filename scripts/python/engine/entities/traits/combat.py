"""Traits de combat exploités par le raw damage prediction — 1 classe par trait (gameconfig name, VA citée).

Override UNIQUEMENT les points du contrat (§17.17) réellement exploités, lus en ghidra. Magnitudes/formules
non encore RE'd → no-op + TODO (on n'invente pas). Traits confirmés présents seed-777 : GetStuckIn, Resilient,
Impervious, HeavyWeapon, TerminatorArmour, Parry, BigTarget, RapidAssault, MartialKatah…
"""
from __future__ import annotations

from collections.abc import Mapping

from .base import BaseTrait


def _cheby(a, b):
    """Proxy distance (Chebyshev sur coordonnées offset) du MinDistance natif (pathfinding) — §17.21."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class GetStuckInTrait(BaseTrait):
    """`GetStuckIn` (ork) — coups bonus. `GetStuckInAbility.CreateBehaviour` @180f83280 =
    `AddBonusHitsToCurrentHitGroup` sous `Maybe(GetBonusHitChance)` ; trigger @180f83350 = `On(8) &
    CurrentHitIndex IsOdd & OwnerIsCaster & !(MinDistance>2)` → **portée 2 (PAS mêlée-only)** : s'applique
    aussi au tir si la cible est à ≤2 hex ; `GetBonusHitChance` @180f83460 = `If(orks_adj≥2 OU
    units_adj≥4, chance_2[key0x33]=100, chance[key0x2a]=30)` ; les comptes = unités adjacentes à la CIBLE
    (AdjacentUnits(target) → UnitsFromFaction Orks=5 / Friends-of-caster).
    Ajoute **+1 coup par coup d'index IMPAIR** = `+floor(hits/2)` (hits = série APRÈS PowerTrip, AVANT
    GetStuckIn). ⚠ N'est PAS ×2 (l'ancien doubling était faux : pour base impair il sur-comptait).

    **`Maybe(chance)` en PRÉDICTION : compté SSI chance == 100.** GROUND TRUTH step-13 seed777 (trace
    AllMods @18102d3f0, 28 paires (tuile,cible), u90 full-HP) : chance 30% (1 ami adjacent à la cible)
    → le groupe de coups bonus n'est JAMAIS compté (4 hits partout, y compris mêlée dist 1 — la
    prédiction native donne exactement arme 3 + PowerTrip 1). L'entrée bonus-hits est évaluée en
    Nullable inclus/exclu (AdditionalHitsFromEffects.GetAdditionalHitsFromEffectsInternal @180e59150,
    flag prediction) — PAS de pondération fractionnaire. Chance = `GetBonusHitChance` @180f83460 =
    `If(orks_adj>=2 OU amis_adj>=4, chance_2=100, chance=30)` (gameconfig GetStuckIn). ⚠ La branche
    100% = hypothèse cohérente (l'ancienne observation « 6 hits à 30% » datait d'AVANT le fix de
    parité hexgeo → lecture d'adjacence suspecte, SUPERSÉDÉE) ; à confirmer sur un cas live chance_2.

    La GÉOMÉTRIE du trigger vit ICI (contrat BaseTrait « chaque trait lit le ctx dont il a besoin »),
    pas chez l'appelant générique. `ctx` (board, fourni par `make_normal_attack_predictions`) =
    {att_id, tgt_id, attack_pos (post-move), t_pos, pos_by_id, team_by_id, faction_of(uid),
    base_hits (série APRÈS PowerTrip)} ; portée/adjacence = proxy cheby (§17.21) ; le caster est
    compté à sa tuile d'ATTAQUE. Sans positions → 0 (pas d'invention)."""

    def as_attacker_bonus_hits(self, ctx: Mapping | None = None) -> int:
        c = ctx or {}
        apos, tpos = c.get("attack_pos"), c.get("t_pos")
        if not apos or not tpos:
            return 0
        if _cheby(apos, tpos) > 2:                # !(MinDistance>2) = cible à <=2 hex (trigger structurel)
            return 0
        # Maybe(chance) EN PRÉDICTION = INCLUS INCONDITIONNELLEMENT (la chance 30/100 ne pilote QUE le
        # roll RNG d'exécution, pas la prédiction de dégât de l'IA). GROUND TRUTH seed777 u90(Snappawrecka)
        # ->u86 RANGED (chance=30 : 1 seul ami adjacent à u86, chance_2 hors d'atteinte) : natif = 6 coups
        # DÉTERMINISTES (oracle/offline = x1.50 uniforme sur min ET max = 4->6). Le gate `chance==100`
        # précédent était FAUX (issu de l'observation step-13 "exclure à 30%", SUPERSÉDÉE — raisonnement
        # d'adjacence pré-fix parité hexgeo, cf. [[project_hexgeo_parity_fix]]). La condition orks>=2/
        # amis>=4 (GetBonusHitChance @180f83460) n'affecte donc PAS la prédiction → on ne l'évalue plus ici.
        base_hits = int(c.get("base_hits") or 0)  # hits APRÈS PowerTrip, AVANT GetStuckIn
        if base_hits <= 0:
            return 0
        return base_hits // 2                     # +1 coup par coup d'index impair = floor(hits/2)


class ResilientTrait(BaseTrait):
    """`Resilient` (trait 0x3f1) — plafond de SURVIE côté cible. **Port fidèle = le SERVICE**
    `services.trait_damage_limits.apply_resilient_trait_damage_limit` (`ApplyResilientTraitDamageLimit @18102c3a0`,
    homonyme natif : cap `hp-1` hors overkill si `max_hp>1`). Structure native = service `DamagePrediction` +
    `HasTrait`, PAS un cap OO par-trait -> NE PAS re-porter la formule ici (une seule source). Le cap sera
    consommé par `apply_trait_damage_limits_to_damage` quand la chaîne sera wirée (#56)."""

    # as_target_damage_cap : intentionnellement no-op (hérité de BaseTrait). Le cap Resilient vit dans le
    # service trait_damage_limits (fidèle au natif) ; cette classe OO ne le duplique pas.


class ImperviousTrait(BaseTrait):
    """`Impervious` (trait 0x1c) — côté cible. **Port fidèle = le SERVICE**
    `services.trait_damage_limits.apply_impervious_trait_damage_limit` (`ApplyImperviousTraitDamageLimit @18102c190` :
    dégât=0 tant que la jauge `StatComponent.CurrentValue` < 100 ; StatType du composant `DAT_1831b6d48` encore à
    identifier). Comme Resilient : structure native = service, on ne duplique PAS la formule dans la classe OO."""

    # as_target_damage_cap : no-op (hérité). Cap dans services.trait_damage_limits (fidèle au natif).
