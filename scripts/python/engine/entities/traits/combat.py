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
        att_id, tgt_id = c.get("att_id"), c.get("tgt_id")
        pos_by_id = c.get("pos_by_id") or {}
        team_by_id = c.get("team_by_id") or {}
        faction_of = c.get("faction_of") or (lambda uid: None)

        def _p(uid):                              # caster compté à sa tuile d'attaque (post-move)
            return apos if uid == att_id else pos_by_id.get(uid)

        adj = [uid for uid in pos_by_id
               if uid != tgt_id and _p(uid) and _cheby(_p(uid), tpos) == 1]
        # Maybe(chance) : la prédiction n'inclut le groupe que si la chance est CERTAINE (100 =
        # condition chance_2 : >=2 orks OU >=4 amis adjacents à la cible). 30% → exclu (step-13 trace).
        # Les DEUX comptes sont FRIENDLY-filtrés (i2 : « 2 or more friendly Orks or 4 or more friendly
        # units » ; DSL @180f83460 : UnitsFromFaction(5) + Friends(owner)). GROUND TRUTH step-13 :
        # u90→80@(3,4) mêlée, Ork ENNEMI 86 adjacent à 80 → natif 4 coups (pas de GetStuckIn) — sans
        # le filtre équipe l'Ork ennemi comptait pour la condition 100%.
        friends = [uid for uid in adj if team_by_id.get(uid) == team_by_id.get(att_id)]
        orks = sum(1 for uid in friends if faction_of(uid) == "Orks")
        if not (orks >= 2 or len(friends) >= 4):
            return 0
        base_hits = int(c.get("base_hits") or 0)  # hits APRÈS PowerTrip, AVANT GetStuckIn
        if base_hits <= 0:
            return 0
        return base_hits // 2                     # +1 coup par coup d'index impair = floor(hits/2)


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
