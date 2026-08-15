"""Traits de combat exploités par le raw damage prediction — 1 classe par trait (gameconfig name, VA citée).

Override UNIQUEMENT les points du contrat (§17.17) réellement exploités, lus en ghidra. Magnitudes/formules
non encore RE'd → no-op + TODO (on n'invente pas). Traits confirmés présents seed-777 : GetStuckIn, Resilient,
Impervious, HeavyWeapon, TerminatorArmour, Parry, BigTarget, RapidAssault, MartialKatah…
"""
from __future__ import annotations

from collections.abc import Mapping

import hexgeo

from .base import BaseTrait
# #943-r7 -- les deux canaux du substrat d'adjacence NATIF, en FORME B (#485-r1-r1).
# `pathfinding.board` n'importe RIEN de `engine` ; `engine.battle_query` n'importe que `hexgeo` +
# `.hex_corner` et INTERDIT explicitement d'importer `engine.entities` (cf. son en-tete), donc
# l'arete `entities.traits.combat -> battle_query` ne peut pas se refermer. Elle existe deja depuis
# `entities/selectors/units.py`.
from ..pathfinding import board as _board
from ... import battle_query as _bq


def min_distance(a, b) -> int:
    """`IdunBattleLogic.Entities.DSLFactory$$MinDistance` restreint au cas UNE entite <-> UNE entite
    (la forme qu'en prend le trigger `GetStuckIn`). **Distance HEX, PAS un pathfinding** — chaine LUE
    au decompile, appelant par appelant :

        DSLFactory$$MinDistance(ctx, selA, selB)  construit `IdunBattle.Entities.Formulas.MinDistanceFormula`
        `MinDistanceFormula$$Calculate` : `Min` sur TOUTES les paires (a de selA, b de selB) de
            `IdunBattle.Entities.Components.PositionComponent$$Distance(pb, pa)`
        `PositionComponent$$Distance` : `IdunBattle.Utils.Hex.AxialCoordinate$$ToCubeCoordinate` sur
            chacun des deux, puis `IdunBattle.Utils.Hex.CubeCoordinate$$Distance` = `Max(|dx|,|dy|,|dz|)`
        `AxialCoordinate$$ToCubeCoordinate` : `off = col + (col & 1)` (branche flag==0, celle que pose
            `PositionComponent$$.ctor`) ; `x = col ; z = row - off/2 ; y = -(x+z)`

    AUCUN graphe, aucune file, aucun cout de terrain, aucun obstacle : geometrie hexagonale pure en
    coordonnees cube, convention offset odd-q = exactement `hexgeo.to_cube` (`(|dx|+|dy|+|dz|)/2` et
    `Max(|dx|,|dy|,|dz|)` sont EGAUX sur tout cube valide, ou x+y+z=0).

    ⚠ Le natif HOMONYME `IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy`
    (utilite IA de MOUVEMENT), LUI, demande une ROUTE au pathfinding et en lit la longueur — c'est la
    glose « pathfinding » d'`engine/utilities/move.py`, qui vaut pour CE natif-la et pas pour le noeud
    DSL. La confondre avait fait ecrire ici un proxy Chebyshev sur coordonnees OFFSET, qui n'est PAS
    la distance hex : `hex >= cheby` TOUJOURS (0 violation sur un balayage exhaustif 24x24, ecart
    jusqu'a 12), donc sur un gate `!(MinDistance > 2)` le proxy OUVRAIT ce que le natif FERME —
    degradation PERMISSIVE et silencieuse. MESURE sur le board MC1_67 : 46,6 % des paires de tuiles
    jouables ont une distance differente, et **5,82 % font diverger le gate `<= 2`**.
    Divergence prouvee LIVE (`probe_min_distance_metric.py --stage live`, seed 777, caster (4,6)
    cible (6,8) : hex=3, cheby=2) : le natif FERME le gate (live bit-exact avec le modele `no_maybe`)
    la ou le proxy le laissait OUVERT (`shipped` MISMATCH sur 3 des 6 coups)."""
    return hexgeo.distance((a[0], a[1]), (b[0], b[1]))


class GetStuckInTrait(BaseTrait):
    """`GetStuckIn` (ork) — coups bonus. `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateBehaviour =
    `AddBonusHitsToCurrentHitGroup` sous `Maybe(GetBonusHitChance)` ; trigger IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger = `On(8) &
    CurrentHitIndex IsOdd & OwnerIsCaster & !(MinDistance>2)` → **portée 2 (PAS mêlée-only)** : s'applique
    aussi au tir si la cible est à ≤2 hex ; `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$GetBonusHitChance = `If(orks_adj≥2 OU
    units_adj≥4, chance_2[key0x33]=100, chance[key0x2a]=30)` ; les comptes = unités adjacentes à la CIBLE
    (AdjacentUnits(target) → UnitsFromFaction Orks=5 / Friends-of-caster).
    Ajoute **+1 coup par coup d'index IMPAIR** = `+floor(hits/2)` (hits = série APRÈS PowerTrip, AVANT
    GetStuckIn). ⚠ N'est PAS ×2 (l'ancien doubling était faux : pour base impair il sur-comptait).

    **`Maybe(chance)` en PRÉDICTION : compté SSI chance == 100** (RESTAURÉ #98). GROUND TRUTH step-13
    seed777 (trace AllMods IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers, 28 paires (tuile,cible), u90 full-HP) : chance 30% (1 ami adjacent
    à la cible) → le groupe de coups bonus n'est JAMAIS compté (4 hits partout — la prédiction native
    donne exactement arme 3 + PowerTrip 1). L'entrée bonus-hits est évaluée en Nullable inclus/exclu
    (IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsFromEffectsInternal, flag prediction) — PAS
    de pondération fractionnaire. Chance = `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$GetBonusHitChance = `If(orks_adj>=2 OU
    amis_adj>=4, chance_2=100, chance=30)` (gameconfig GetStuckIn). ⚠ L'épisode « fold inconditionnel »
    (l'observation u90→u86 « ×1.50 uniforme 4→6 » qui avait supersédé ce gate) était une MISATTRIBUTION :
    ce ×1.5 = le bonus d'ÉLÉVATION de la tuile de plan (5,4) elev3 > cible elev2 (#98) — 6 = 4×1.5,
    compensation exacte démasquée en portant l'élévation en prédiction (cf. as_attacker_bonus_hits).

    **Ce fold est PRÉDICTION-ONLY** (verdict validateur cluster, BITE 2) : `attack_hits_with_modifiers` ne
    l'invoque que si `include_bonus_hit_behaviours=True` (prédiction). En COMBAT le natif applique GetStuckIn
    via le behaviour d'exécution chance-gaté `AddBonusHitsToCurrentHitGroupBehaviour IdunBattle.Entities.Behaviours.AddBonusHitsToCurrentHitGroupBehaviour$$Execute`
    (roll `Maybe(GetBonusHitChance)` 30%/100%), PORTÉ (#62c, commit 3997793) HORS de cette formule : à
    l'EXÉCUTION dans `runner.operations.damage_hits._run_hits` (param `bonus_hit_chance`, alimenté par
    `runner.damage_model.getstuckin_combat_chance`), qui roll le `Maybe` après le block de chaque coup
    d'index IMPAIR et exécute les coups bonus déférés. Le fold en dur DANS la formule sur-comptait (orksNob
    1v1 chance=30 → natif 3 coups, folder 4) → combat=False côté formule est CORRECT (le bonus vient de
    l'exécution). VALIDÉ bit-exact live (case-67, orksNob base-3 + orksBigMek base-4, 0/1/2 coups bonus).

    La GÉOMÉTRIE du trigger vit ICI (contrat BaseTrait « chaque trait lit le ctx dont il a besoin »),
    pas chez l'appelant générique. `ctx` (board, fourni par `make_normal_attack_predictions` — prédiction) =
    {att_id, tgt_id, attack_pos (post-move), t_pos, pos_by_id, team_by_id, base_hits (série APRÈS PowerTrip)} ;
    portée = `min_distance` (distance HEX, mirror du nœud DSL — cf. sa docstring), adjacence =
    `hexgeo.distance == 1` ; le caster est compté à sa tuile d'ATTAQUE. Sans positions → 0
    (pas d'invention). NB : le comptage par faction (orks adjacents) ne s'évalue plus (n'affecte pas la
    prédiction, cf. plus bas) → PAS de `faction_of`/visual_id dans le ctx."""

    def as_attacker_bonus_hits(self, ctx: Mapping | None = None) -> int:
        c = ctx or {}
        apos, tpos = c.get("attack_pos"), c.get("t_pos")
        if not apos or not tpos:
            return 0
        if min_distance(apos, tpos) > 2:          # !(MinDistance>2) = cible à <=2 hex (trigger structurel)
            return 0
        # Maybe(chance) EN PRÉDICTION : compté SSI `GetBonusHitChance == 100` (branche chance_2 :
        # orks_adj >= 2 OU amis_adj >= 4 autour de la CIBLE, IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$GetBonusHitChance). C'est le verdict ORIGINEL du
        # step-13 (« chance 30% -> jamais compté, 4 hits partout »), RESTAURÉ #98 : l'observation qui
        # l'avait « supersédé » (u90 Snappawrecka -> u86 ranged, oracle x1.50 uniforme 4->6 interprété
        # comme fold-a-30%) était une MISATTRIBUTION — le x1.50 était le BONUS D'ÉLÉVATION de la tuile
        # de plan (5,4) elev3 > cible elev2 (builder IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction, inliné, cf. prediction.md MAJ #98) :
        # oracle plat (3,5) = [1364,5060] = 4 coups EXACTS (341/1265 per-coup), (5,4) = x1.5 EXACT.
        # Le fold inconditionnel + pas-d'élévation se compensaient EXACTEMENT (6 = 4 x 1.5) — bug
        # compensatoire classique, démasqué en portant l'élévation.
        base_hits = int(c.get("base_hits") or 0)  # hits APRÈS PowerTrip, AVANT GetStuckIn
        if base_hits <= 0:
            return 0
        # IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$GetBonusHitChance : AdjacentUnits(target, ring 1) -> UnitsFromFaction(Orks=5) >= 2
        # OU Friends(caster) >= 4 -> chance_2 (=100) ; sinon chance (=30). Adjacence HEX (hexgeo, parité
        # validée vs boardGraph) ; l'attaquant est compté à sa tuile d'ATTAQUE (attack_pos).
        att_id, tgt_id = c.get("att_id"), c.get("tgt_id")
        team_by_id = c.get("team_by_id") or {}
        faction_by_id = c.get("faction_by_id") or {}
        att_team = team_by_id.get(att_id)
        orks_adj = 0
        friends_adj = 0
        # #943-r7 -- `AdjacentUnits(Target@DSLSelectors+0x60, unique, 3)` (LU : le 2e argument du
        # call-site de `GetBonusHitChance` est `<dsl>+0x90 -> +0x60`, donc la CIBLE, pas le caster)
        # = `Units(AdjacentTiles(Target), unique, 3) - Target`. L'ENUMERATION part donc de la TUILE
        # DE LA CIBLE, sur la liste STOCKEE du `ConnectivityComponent` puis la porte `|dElev| < 2` --
        # `is_adjacent(cible, unite)`, pas l'inverse. Board absent du ctx -> repli geometrique NOMME.
        elev_by_pos, neigh_by_pos = _board.adjacency_channels(c.get("board"))
        for uid, pos in (c.get("pos_by_id") or {}).items():
            if uid == tgt_id or pos is None:
                continue
            p = apos if uid == att_id else pos    # le caster évalué à sa tuile d'attaque
            if not _bq.is_adjacent(tuple(tpos), tuple(p), elev_by_pos, neigh_by_pos):
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
    `services.trait_damage_limits.apply_resilient_trait_damage_limit` (`IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit`,
    homonyme natif : cap `hp-1` hors overkill si `max_hp>1`). Structure native = service `DamagePrediction` +
    `HasTrait`, PAS un cap OO par-trait -> NE PAS re-porter la formule ici (une seule source). Le cap sera
    consommé par `apply_trait_damage_limits_to_damage` quand la chaîne sera wirée (#56)."""

    # as_target_damage_cap : intentionnellement no-op (hérité de BaseTrait). Le cap Resilient vit dans le
    # service trait_damage_limits (fidèle au natif) ; cette classe OO ne le duplique pas.


class ImperviousTrait(BaseTrait):
    """`Impervious` (trait 0x1c) — côté cible. **Port fidèle = le SERVICE**
    `services.trait_damage_limits.apply_impervious_trait_damage_limit` (`IdunBattle.Core.Services.DamagePrediction$$ApplyImperviousTraitDamageLimit` :
    dégât=0 tant que la jauge `StatComponent.CurrentValue` < 100 ; StatType du composant `DAT_1831b6d48` encore à
    identifier). Comme Resilient : structure native = service, on ne duplique PAS la formule dans la classe OO."""

    # as_target_damage_cap : no-op (hérité). Cap dans services.trait_damage_limits (fidèle au natif).


class MkXGravisTrait(BaseTrait):
    """`MkXGravis` (trait 0x3f5 = 1013, `UnitTrait`, cf. #146) — côté CIBLE : les dégâts entrants
    TRAVERSENT L'ARMURE UNE 2ᵉ FOIS (i2 : « Any incoming Damage has to go through Armour a second time.
    Does not apply to Crits »). Lu DIRECTEMENT dans `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor` : `HasTrait(cible, 0x3f5) && param_8(isCrit)==0` → `hit_multiplier=2` → la boucle
    `GetDamageWithPiercing(d, pierce, armor)` s'exécute 2× (armure appliquée deux fois). Ce helper est dans
    le chemin de PRÉDICTION IA (`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` ← `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw`) ET de combat (`IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`).

    ⚠ NON appliqué sur CRIT (param_8==1). La prédiction du port ne modélise PAS de branche crit séparée
    (le crit est exclu du dégât rapporté, #62b) → défaut non-crit = multiplicateur 2, exactement ce que
    l'oracle rapporte. VALIDÉ bit-exact #178 : u91→u79/ultraInceptorSgt (seed 500), hit_mult=2 → oracle
    (678,1254) EXACT sur min ET max. Si un jour la prédiction modélise le crit, gater via `ctx`."""

    def as_target_hit_multiplier(self, ctx: Mapping | None = None) -> int:
        return 2
