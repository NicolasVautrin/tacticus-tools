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

    **`Maybe(chance)` en PRÉDICTION : compté SSI chance == 100** (RESTAURÉ #98). GROUND TRUTH step-13
    seed777 (trace AllMods @18102d3f0, 28 paires (tuile,cible), u90 full-HP) : chance 30% (1 ami adjacent
    à la cible) → le groupe de coups bonus n'est JAMAIS compté (4 hits partout — la prédiction native
    donne exactement arme 3 + PowerTrip 1). L'entrée bonus-hits est évaluée en Nullable inclus/exclu
    (AdditionalHitsFromEffects.GetAdditionalHitsFromEffectsInternal @180e59150, flag prediction) — PAS
    de pondération fractionnaire. Chance = `GetBonusHitChance` @180f83460 = `If(orks_adj>=2 OU
    amis_adj>=4, chance_2=100, chance=30)` (gameconfig GetStuckIn). ⚠ L'épisode « fold inconditionnel »
    (l'observation u90→u86 « ×1.50 uniforme 4→6 » qui avait supersédé ce gate) était une MISATTRIBUTION :
    ce ×1.5 = le bonus d'ÉLÉVATION de la tuile de plan (5,4) elev3 > cible elev2 (#98) — 6 = 4×1.5,
    compensation exacte démasquée en portant l'élévation en prédiction (cf. as_attacker_bonus_hits).

    **Ce fold est PRÉDICTION-ONLY** (verdict validateur cluster, BITE 2) : `attack_hits_with_modifiers` ne
    l'invoque que si `include_bonus_hit_behaviours=True` (prédiction). En COMBAT le natif applique GetStuckIn
    via le behaviour d'exécution chance-gaté `AddBonusHitsToCurrentHitGroupBehaviour @180f93410`
    (roll `Maybe(GetBonusHitChance)` 30%/100%) NON encore porté (TODO #62c) → le combat OMET ce bonus au lieu
    de le folder inconditionnellement (folder sur-comptait : orksNob 1v1 chance=30 → natif 3 coups, port 4).

    La GÉOMÉTRIE du trigger vit ICI (contrat BaseTrait « chaque trait lit le ctx dont il a besoin »),
    pas chez l'appelant générique. `ctx` (board, fourni par `make_normal_attack_predictions` — prédiction) =
    {att_id, tgt_id, attack_pos (post-move), t_pos, pos_by_id, team_by_id, base_hits (série APRÈS PowerTrip)} ;
    portée/adjacence = proxy cheby (§17.21) ; le caster est compté à sa tuile d'ATTAQUE. Sans positions → 0
    (pas d'invention). NB : le comptage par faction (orks adjacents) ne s'évalue plus (n'affecte pas la
    prédiction, cf. plus bas) → PAS de `faction_of`/visual_id dans le ctx."""

    def as_attacker_bonus_hits(self, ctx: Mapping | None = None) -> int:
        c = ctx or {}
        apos, tpos = c.get("attack_pos"), c.get("t_pos")
        if not apos or not tpos:
            return 0
        if _cheby(apos, tpos) > 2:                # !(MinDistance>2) = cible à <=2 hex (trigger structurel)
            return 0
        # Maybe(chance) EN PRÉDICTION : compté SSI `GetBonusHitChance == 100` (branche chance_2 :
        # orks_adj >= 2 OU amis_adj >= 4 autour de la CIBLE, @180f83460). C'est le verdict ORIGINEL du
        # step-13 (« chance 30% -> jamais compté, 4 hits partout »), RESTAURÉ #98 : l'observation qui
        # l'avait « supersédé » (u90 Snappawrecka -> u86 ranged, oracle x1.50 uniforme 4->6 interprété
        # comme fold-a-30%) était une MISATTRIBUTION — le x1.50 était le BONUS D'ÉLÉVATION de la tuile
        # de plan (5,4) elev3 > cible elev2 (builder @181000590, inliné, cf. prediction.md MAJ #98) :
        # oracle plat (3,5) = [1364,5060] = 4 coups EXACTS (341/1265 per-coup), (5,4) = x1.5 EXACT.
        # Le fold inconditionnel + pas-d'élévation se compensaient EXACTEMENT (6 = 4 x 1.5) — bug
        # compensatoire classique, démasqué en portant l'élévation.
        base_hits = int(c.get("base_hits") or 0)  # hits APRÈS PowerTrip, AVANT GetStuckIn
        if base_hits <= 0:
            return 0
        # GetBonusHitChance @180f83460 : AdjacentUnits(target, ring 1) -> UnitsFromFaction(Orks=5) >= 2
        # OU Friends(caster) >= 4 -> chance_2 (=100) ; sinon chance (=30). Adjacence HEX (hexgeo, parité
        # validée vs boardGraph) ; l'attaquant est compté à sa tuile d'ATTAQUE (attack_pos).
        import hexgeo
        att_id, tgt_id = c.get("att_id"), c.get("tgt_id")
        team_by_id = c.get("team_by_id") or {}
        faction_by_id = c.get("faction_by_id") or {}
        att_team = team_by_id.get(att_id)
        orks_adj = 0
        friends_adj = 0
        for uid, pos in (c.get("pos_by_id") or {}).items():
            if uid == tgt_id or pos is None:
                continue
            p = apos if uid == att_id else pos    # le caster évalué à sa tuile d'attaque
            if hexgeo.distance(tuple(p), tuple(tpos)) != 1:
                continue
            if att_team is not None and team_by_id.get(uid) == att_team:
                friends_adj += 1
                if (faction_by_id.get(uid) or "") == "Orks":
                    orks_adj += 1
        if orks_adj < 2 and friends_adj < 4:      # chance = 30 -> Nullable EXCLU de la prédiction
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


class MkXGravisTrait(BaseTrait):
    """`MkXGravis` (trait 0x3f5 = 1013, `UnitTrait`, cf. #146) — côté CIBLE : les dégâts entrants
    TRAVERSENT L'ARMURE UNE 2ᵉ FOIS (i2 : « Any incoming Damage has to go through Armour a second time.
    Does not apply to Crits »). Lu DIRECTEMENT dans `DamagePrediction.GetBaseDamageWithFixedPiercedArmor
    @181030d10` : `HasTrait(cible, 0x3f5) && param_8(isCrit)==0` → `hit_multiplier=2` → la boucle
    `GetDamageWithPiercing(d, pierce, armor)` s'exécute 2× (armure appliquée deux fois). Ce helper est dans
    le chemin de PRÉDICTION IA (`CalculateBaseDamageWithAllModifiers @18102d3f0` ← `PredictAttackRaw
    @181032fb0`) ET de combat (`CalculateAbilityDamage @18102cb50`).

    ⚠ NON appliqué sur CRIT (param_8==1). La prédiction du port ne modélise PAS de branche crit séparée
    (le crit est exclu du dégât rapporté, #62b) → défaut non-crit = multiplicateur 2, exactement ce que
    l'oracle rapporte. VALIDÉ bit-exact #178 : u91→u79/ultraInceptorSgt (seed 500), hit_mult=2 → oracle
    (678,1254) EXACT sur min ET max. Si un jour la prédiction modélise le crit, gater via `ctx`."""

    def as_target_hit_multiplier(self, ctx: Mapping | None = None) -> int:
        return 2
