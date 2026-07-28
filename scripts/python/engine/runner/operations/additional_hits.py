"""Canal COUPS ADDITIONNELS HETEROGENES (#179/#202-B) — face COMBAT, extrait de
`AttackDamageOperation` (scission du module >1000 lignes, vecteur de croissance : chaque patron
custom normal-attack / effet declarant des coups additionnels atterrit ICI).

Deux fonctions LIBRES appelees par `AttackDamageOperation.execute` :
  - `collect_additional_hit_groups` : mirror `AdditionalHitsFromEffects.GetAdditionalHitsFromEffects
    Internal IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsFromEffectsInternal` (enumeration GLOBALE des descripteurs : effets du porteur + auras d'allies) ;
  - `execute_additional_hits` : mirror `IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute` (chaque groupe = sous-operation de degat au profil PROPRE, apres les coups d'arme).

`execute_additional_hits` rappelle les primitives de tirage de `AttackDamageOperation`
(`_apply_max_out`/`_run_hits`/`_target_limits`/`_deplete_shield`/`_apply_damage_pipeline`) : import
LAZY de la classe (rompt le cycle module `damage` <-> `additional_hits` — au moment de l'appel, en
pleine bataille, `damage` est entierement charge)."""
from __future__ import annotations

from ..components import (StatsComponent, HealthComponent, PositionComponent, UnitComponent,
                          OwnerComponent)
from ..damage_model import target_trait_names
from ..state import State
from ...services.damage_prediction import get_base_damage_fix64, apply_pierce_and_modifiers
from ...services.damage_modifiers import apply_all_modifiers
from ...entities.effects import additional_hit_groups, aura_additional_hits_from_allies


def reduce_group_damage(value, g_pierce: int, armor: int, mods, def_mods, hit_mult: int = 1) -> int:
    """ETAGE DE REDUCTION d'UN coup du canal #179 (percage/armure + %-mods attaquant/defenseur +
    MATERIALISATION finale) -- FOYER UNIQUE, extrait pour que la garde live puisse confronter
    EXACTEMENT ce que le port materialise (`test_additional_hits_rounding_live`).

    R6-b : ce foyer est desormais le `post_roll` de `_run_hits` -- il recoit la VALEUR TIREE, plus
    les bornes (cf. `execute_additional_hits`). Sa formule est INCHANGEE ; seul son call-site l'est.

    Mirror de `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`
    dans le per-coup `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`, qui est le MEME
    pour les coups d'arme et pour les coups additionnels (les deux voies natives y retombent :
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType`
    -> `ExecuteHits`, et `IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileType
    Operation$$Execute` -> slot 0x3c `Core.Services.OperationProcessor$$AttackDamage` ->
    `IdunBattle.Operations.AttackDamageOperation$$Execute` -> `ExecuteHits`).

    R6 -- MATERIALISATION = `Fix64$$Round(., AwayFromZero)`, PAS la troncature `op_Explicit`.
    `ExecuteHit` resout sa cellule par le slot 4 `IdunBattle.Core.Services.DamagePrediction$$
    PredictAttack` (cache -> `PredictAttackRaw`) puis le slot 8 `RandomlyResolveMinMaxDamage` ;
    le dernier etage de `CalculateBaseDamageWithAllModifiers` est le MULTIPLICATEUR (slot 0x10 ->
    `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`), LU verbatim :
        v = Mul(dmg, multiplier) ; v <= 0 -> 0 ; 0 < v < 1 -> 1 ; sinon Round(v, AwayFromZero)
    -- INCONDITIONNEL des qu'un `Nullable<DamageModifiers>` HasValue. C'est le MEME etage que
    l'attaque normale (#131) et que l'ability bounds-mode famille ATTACK (HeavyGravCannon) : un
    coup additionnel ne peut pas materialiser autrement que les coups d'arme de la MEME `ExecuteHit`.
    MESURE LIVE (probe_r6_round_materialize --case ah_matrix ; `orksRuntherd`/`SquigHound`, groupe
    predefined [2660,3988] profil Physical pierce 1, cible forcee a 6000 d'armure par
    `rl_duel build --armor-target` -- aucune armure du roster n'y suffisait) : 11 seeds, 14 coups
    reproduits, live == ARRONDI **14/14**, live == troncature **10/14**, les 4 ecarts tombant
    EXACTEMENT sur les tirages a partie fractionnaire >= .5 (ce qui refute « additif oublie », qui
    aurait donne un +1 systematique). Meme signature que la campagne HeavyGravCannon.
    STRICTEMENT NO-OP hors regime discriminant (valeur deja entiere -> Round == identite).

    L'etage AMONT (l'ORDRE tirage/reduction) est desormais porte lui aussi -- cf. le bloc R6-b de
    `execute_additional_hits`. Les deux etages restent DISTINCTS : celui-ci decide COMMENT un
    tirage se materialise, l'autre decide QUEL tirage sort."""
    return apply_all_modifiers(
        apply_pierce_and_modifiers(value, g_pierce, armor, mods, hit_mult=hit_mult,
                                   attacker_additive_pre=True),
        def_mods, round_materialize=True)


def collect_additional_hit_groups(state: State, attacker_id: int, target_id: int,
                                  att_active, is_melee: bool, tgt_active) -> list:
    """#202-B : mirror `IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsFromEffectsInternal`
    cote ECS — enumeration GLOBALE des effets declarant des coups additionnels HETEROGENES (canal
    #179) : (a) effets du PORTEUR (`additional_hit_groups`, ex. SquigHound/CordClaw/FoulInfusion) ;
    (b) effets-AURA hostes sur d'AUTRES unites VIVANTES (`create_aura_additional_hits_for_ally`,
    ex. ExplosiveMaladies/InfernalPacts) — adjacence evaluee aux positions REELLES de l'ECS, mirror
    du refresh natif `PreAttack(5)` (l'aura est reevaluee au moment de l'attaque, IdunBattle.Entities.Effects.Loki.InfernalPacts_AdditionalHitsEffect$$GetRefreshTriggers).
    Retour [] strict (aucun carrier -> no-op, AUCUNE conso RNG)."""
    import gameconfig as GC
    att = state.get_entity(attacker_id)
    ap = att.get_component(PositionComponent) if att is not None else None
    aoc = att.get_component(OwnerComponent) if att is not None else None
    auc = att.get_component(UnitComponent) if att is not None else None
    asc = att.get_component(StatsComponent) if att is not None else None
    if ap is None or aoc is None:
        return []
    gu = (GC.unit(auc.visual_id) or {}) if auc is not None else {}
    # gates CIBLE des descripteurs du porteur (#57e, ex. CyclicIonBlaster HasEffect(Markerlight)).
    ah_ctx = {"is_melee": is_melee,
              "tgt_traits": frozenset(target_trait_names(state, target_id) or ()),
              "tgt_effect_names": frozenset(
                  n for n in (getattr(e, "name", None) for e in (tgt_active or [])) if n)}
    groups = list(additional_hit_groups(att_active, ah_ctx))
    carriers = []
    for uid, e in state.entities.items():
        if uid == attacker_id:
            continue
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        oc = e.get_component(OwnerComponent)
        hc = e.get_component(HealthComponent)
        if uc is None or pc is None or oc is None or not uc.alive:
            continue
        effs = (state.effects.active_effects(uid, {"hp": hc.hp if hc is not None else None})
                if state.effects is not None else [])
        if not effs:
            continue
        sc2 = e.get_component(StatsComponent)
        ctx2 = sc2.ctx if sc2 is not None else None
        gu2 = GC.unit(uc.visual_id) or {}
        carriers.append((uid, (pc.col, pc.row), oc.team,
                         int(getattr(ctx2, "ability_variables_multiplier", 100) or 100),
                         getattr(ctx2, "passive_ability_level", None),
                         gu2.get("GrandAllianceId"), gu2.get("FactionId"), effs))
    groups += aura_additional_hits_from_allies(
        carriers, {"att_id": attacker_id, "att_pos": (ap.col, ap.row), "att_team": aoc.team,
                   "att_faction": gu.get("FactionId"),
                   "att_grand_alliance": gu.get("GrandAllianceId"),
                   "att_traits": frozenset(getattr(asc.ctx, "traits", None) or ())
                   if asc is not None else frozenset(),
                   "is_melee": is_melee})
    return groups


def execute_additional_hits(state: State, attacker_id: int, target_id: int, tgt, thc,
                            groups: list, mods, def_mods, armor: int, hit_mult: int,
                            block_sources, shc, spread_pct: int = 20,
                            extra_pierce: int = 0, bonus_hit_chance: "Optional[int]" = None,
                            hit_index0: int = 0) -> "Optional[dict]":
    """#202-B : face COMBAT du canal #179 — mirror `ExecuteAdditionalHitsWithDamageProfileType
    IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute` (schedule : `OperationProcessor.ExecuteAdditionalHitsWith
    DamageProfileType Core.Services.OperationProcessor$$ExecuteAdditionalHitsWithDamageProfileType`) : chaque groupe qualifie execute ses coups comme SOUS-OPERATION
    de degat APRES les coups d'arme. Bornes = plage PREDEFINED [min,max] (RandomAmount natif —
    PAS de spread ±20% ; forme `amount` = spread standard) REDUITE par perce(profil du GROUPE)
    + armure + mods — MEMES mods attaquant/defenseur que l'arme (mirror de la prediction #179,
    mesure 2468 s14 : le coup ExplosiveMaladies subit le x1.5 CrushingStrike). Tirage TOUJOURS
    consomme (mode-1 attaque, etage limites au profil DU GROUPE #57d). Max-out WeaverOfFate
    (#202-A) : bornes degenerees (max,max), symetrique de la degenerescence `predefined` de
    `predict_attack_raw`.

    Chaque groupe passe par `_apply_damage_pipeline` avec SON profil (mirror RegisterDamage
    per-sous-operation -> un coup Psychic d'InfernalPacts alimente `received_damage_this_turn`
    donc WeaverOfFate) et `is_attack=False` (le compteur d'attaque est celui de l'ATTAQUE,
    deja pose par la phase d'arme).

    R6-b — ORDRE : ROLL-THEN-REDUCE, 2 tirages/coup (mirror `IdunBattle.Operations.
    AttackDamageOperation$$ExecuteHit`, LU verbatim dans l'ordre du corps natif) :

      1. `IdunBattle.Core.HitDamage$$GetDamage(attackData.HitDamage, rng, useAverage)` —
         `if (min == max) return min ; if (useAverage) return (min+max)/2 ;
          return rng.Range(min, max+1)`. L'AttackData de CHAQUE groupe est bati par
         `IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsData`, dont
         l'instruction utile est `IdunBattle.Core.HitDamage$$.ctor(min = descripteur.minDmg,
         max = Nullable(descripteur.maxDmg))` : un groupe PREDEFINED y arrive donc NON DEGENERE
         -> ce tirage EST la valeur BRUTE du coup ;
      2. crit -> `CritDamageInfo`, dont le champ 0 est CE degat ;
      3. slot 4 `IdunBattle.Core.Services.DamagePrediction$$PredictAttack` (le `Nullable<int>`
         damage de sa struct d'entree = `CritDamageInfo.Damage`) -> reduction percage/armure/mods
         = `reduce_group_damage`, cellule DEGENEREE ;
      4. slot 8 `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` :
         `rng.Range(pred.min, pred.max+1)` **SANS aucun gate min == max** (contraste EXACT avec
         `HitDamage$$GetDamage`, qui en a un) -> 1 tirage GASPILLE.

    C'est EXACTEMENT la branche `post_roll` de `damage_hits.py::_one_hit`
    (`is_attack_damage_op=True`), deja mirroree et validee bit-exact pour le vecteur ability
    bounds-mode de la MEME famille ATTACK — un coup additionnel `predefined` est structurellement
    le meme objet (`HitDamage` non degenere pose dans l'AttackData). Le port faisait
    REDUCE-THEN-ROLL (bornes pre-reduites, `post_roll=None`, 1 tirage/coup).
    MESURE LIVE (`probe_r6_round_materialize --case ah_matrix` ; `orksRuntherd`/SquigHound,
    groupe predefined [2660,3988] Physical p1, cible forcee a 6000 d'armure) : le 1er coup de
    chaque groupe est reproduit **5/5** par roll-then-reduce + resolve et **0/5** par
    reduce-then-roll (11/11 vs 0/11 sur la campagne d'origine a 11 seeds) ; sur les seeds ou le
    2e coup est lui aussi reproduit, c'est TOUJOURS la variante AVEC le resolve gaspille (3/3 ;
    `resolve=False` echoue sur les 3).

    R6-b' — RESIDU FERME : le `Maybe` after-hit est ROULE SUR LES COUPS D'UN GROUPE comme sur
    les coups d'ARME, avec le MEME compteur d'index, CONTINU a travers les sous-operations.
    Chaine natif LUE (gqfc5mff6c), de l'index au tirage :

      * `IdunBattle.Core.OngoingAttack$$.ctor` initialise `+0x30` (index de coup) et `+0x34`
        (compteur de series) a 0. L'objet est POUSSE **une seule fois par attaque** sur la pile
        `MatchState+0x60` (`IdunBattle.Core.MatchState$$StartAttack`, appelee par
        `IdunBattle.Operations.StartAttackOperation$$Execute`) et depile par
        `IdunBattle.Core.MatchState$$FinishAttack` ;
      * toute sous-operation le RECUPERE par `Peek` : `IdunBattle.Operations.ADamageOperation$$
        GetCurrentAttackOrDefault` -> `IdunBattle.Core.Services.BattleQuery$$
        GetCurrentAttackOrDefault` -> `IdunBattle.Core.MatchState$$GetCurrentAttack` ;
      * `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` relit `currentAttack+0x30`
        FRAIS a chaque tour de boucle et le passe a `ExecuteHit` ; `IdunBattle.Operations.
        ADamageOperation$$UpdateCurrentAttackAfterHit` fait `currentAttack+0x30 += 1` apres
        CHAQUE coup (`+0x34 += 1` seulement en fin de serie) ;
      * DERNIERE instruction d'`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (appel
        INCONDITIONNEL, xref) : `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`,
        qui construit `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` avec cet index en
        `Nullable<int>` au champ **+0x110** puis dispatche l'event **`On(8)`** (et `On(0x3d)` si
        crit) ; `IdunBattle.Entities.Formulas.CurrentHitIndexFormula$$Calculate` lit exactement
        `AbilityEntities+0x110` ;
      * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger` =
        `On(8) & AmountIsOdd(CurrentHitIndex()) & OwnerIsCaster & !(MinDistance(caster,target) >
        Direct(2))` ; `...GetStuckInAbility$$CreateBehaviour` = `Maybe(AddBonusHitsToCurrentHitGroup
        (..., AbilityOrEffect(0x4d2)), GetBonusHitChance())` -> 1 `NextBool(chance)`
        (`IdunBattle.Entities.Behaviours.MaybeBehaviour$$Execute`) a chaque passage du trigger ;
      * la voie GROUPES (`ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute` -> slot
        0x3c -> `AttackDamageOperation$$Execute` -> `ExecuteHits`) passe donc par le MEME
        `OngoingAttack` : l'index n'y repart PAS de 0.

    D'ou `bonus_hit_chance` + `hit_index0` : MEME site d'evaluation que les coups d'arme
    (`damage_hits._run_hits`), threade — AUCUN deuxieme site (le fork de port que #110 avait deja
    coute). `hit_index0` entre a `r["next_hit_index"]` de la phase d'arme (coups bonus compris) et
    se THREADE de groupe en groupe. `bonus_hit_chance is None` -> strict no-op (attaquant sans
    GetStuckIn, ou cible a plus de 2 hex).
    Consequence portee gratuitement, et FIDELE : un succes pendant un groupe defere un coup bonus
    DANS CE GROUPE (le natif a une boucle de fin sur `hitGroup+0x58` par sous-operation, et
    `SetupHitGroup` cree un hitGroup PAR sous-operation).

    R6-b'' — RESIDU « VECTEUR ABILITY » FERME : `damage_ops/ability.py` thread DESORMAIS
    `bonus_hit_chance` sur SES coups d'arme ET ici. Le trigger n'a AUCUN gate `IsNormalAttack`, et
    `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` est appele en DERNIERE
    instruction, INCONDITIONNELLEMENT, par ses TROIS appelants (xref) :
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (famille ATTACK, la MEME fonction que
    l'attaque normale), `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit` (famille ABILITY)
    et `IdunBattle.Operations.MachineDamageOperation$$ExecuteHit`. Cf.
    `docs/rl/case-r6bp2-after-hit-maybe-ability-vector.md`.

    A CONFIRMER LIVE (case-202 §7) : (1) gate `hp > 0` (cible morte pendant la phase d'arme ->
    sous-operations non emises) ; (2) `failed_block` remis a zero entre phase d'arme et groupes
    (le natif persiste la failedList PAR ATTAQUE — residu).
    None si aucun groupe qualifie (strict no-op retro-compat).

    Rappelle les primitives de tirage de `AttackDamageOperation` : import LAZY (cycle module
    damage <-> additional_hits ; `damage` est charge au moment de l'appel en bataille)."""
    if not groups or thc is None or int(thc.hp or 0) <= 0:
        return None
    import gameconfig as GC
    from .damage import AttackDamageOperation, HitDamage
    from ...entities.damage_trait import DamageTrait
    death = None
    out = {"groups": 0, "hits": 0, "total": 0, "per_hit": [], "rolls": [], "profiles": []}
    hit_index = int(hit_index0)      # `currentAttack+0x30` — CONTINU d'un groupe a l'autre (R6-b')
    for g in groups:
        if int(thc.hp or 0) <= 0:
            break
        g_profile = g.get("profile")
        dp = GC.damage_profile(g_profile) or {}
        g_pierce = max(0, min(100, int(dp.get("PiercingRatio") or 0) + int(extra_pierce or 0)))
        # bi-canal (mesure 202b) : la face COMBAT resout le noeud RandomAmount du descripteur
        # (field[1] -> plage DIRECTE min/max) ; `amount` (field[2] Average) = canal PREDICTION.
        # Un groupe amount-seul (ex. FoulInfusion ConfigVar) prend le spread ±20% standard.
        if "min" in g and "max" in g:
            g_min, g_max = int(g.get("min") or 0), int(g.get("max") or 0)
        else:
            mm = get_base_damage_fix64(g.get("amount") or 0, spread_pct=spread_pct)
            g_min, g_max = mm.min, mm.max
        def _reduce(value, _p=g_pierce):
            """`post_roll` = etage 3 d'`ExecuteHit` (slot 4 `PredictAttack`), applique a la
            VALEUR TIREE et non aux bornes (R6-b, cf. docstring)."""
            return reduce_group_damage(value, _p, armor, mods, def_mods, hit_mult=hit_mult)

        # R6-b : bornes BRUTES du descripteur (= le `HitDamage` NON degenere que
        # `AdditionalHitsFromEffects$$GetAdditionalHitsData` pose dans l'AttackData) -> le tirage
        # de `HitDamage$$GetDamage` porte sur ELLES, la reduction vient APRES via `post_roll`.
        hd = HitDamage(g_min, g_max)
        # #202-A WeaverOfFate : bornes degenerees a (max, max). Le natif, lui, evalue
        # `IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage` APRES `GetDamage` et remplace
        # le degat tire par `attackData.HitDamage.max` -> meme VALEUR ici (post_roll(max)), mais
        # le tirage brut y est consomme alors que `get_damage` le court-circuite a min == max.
        # Residu de CONSOMMATION strictement identique a celui du vecteur ability bounds-mode
        # (`damage_ops/ability.py`, meme appel) ; no-op tant que l'attaquant n'a pas l'effet 1185.
        hd, _ = AttackDamageOperation._apply_max_out(state, attacker_id, hd, hd)
        shield_total = shc.get_total_shield() if shc is not None else 0
        # #65 : le flag NoBlocking est PER SOUS-OPERATION (IdunBattle.Operations.AttackDamageOperation$$ExecuteHit relit
        # DamageProfile.HasTrait(0=NoBlocking) du profil DU COUP courant) -> un groupe au profil
        # NoBlocking (ex. coup Psychic InfernalPacts) bypasse le block, meme si l'arme principale ne
        # l'etait pas. On re-gate block_sources sur le profil DU GROUPE (l'arg est deja gate sur l'arme).
        g_block = (None if DamageTrait.NoBlocking.name in (dp.get("Traits") or [])
                   else block_sources)
        r = AttackDamageOperation._run_hits(
            state.rng, hd, hd, 0, False, max(0, int(g.get("count") or 0)), g_block,
            shield=shield_total,
            # R6-b : `post_roll` = branche ROLL-THEN-REDUCE de `_one_hit` (tirage BRUT + resolve
            # slot-8 gaspille) ; `is_attack_damage_op=True` = famille ATTACK, les DEUX voies
            # natives de coups additionnels retombant sur `AttackDamageOperation$$ExecuteHits`.
            post_roll=_reduce, is_attack_damage_op=True,
            # R6-b' : MEME site d'evaluation du `Maybe` after-hit que les coups d'arme, avec
            # l'index CONTINU de l'ATTAQUE (`currentAttack+0x30`). Voir la docstring.
            bonus_hit_chance=bonus_hit_chance, hit_index0=hit_index,
            limits=AttackDamageOperation._target_limits(tgt, thc, g_profile, is_special=1),
            limits_hp=int(thc.hp or 0))
        hit_index = r["next_hit_index"]
        AttackDamageOperation._deplete_shield(shc, r)
        d = AttackDamageOperation._apply_damage_pipeline(
            state, target_id, attacker_id, tgt, thc, r["total"], g_profile,
            r["shield_dmg"], r["armor_dmg"], is_attack=False)
        death = death or d
        out["groups"] += 1
        # coups REELLEMENT emis (R6-b' : un succes du `Maybe` defere un coup bonus DANS ce groupe,
        # donc `count` seul sous-compte).
        out["hits"] += len(r["per_hit"])
        out["total"] += r["total"]
        out["per_hit"] += r["per_hit"]
        out["rolls"] += r["rolls"]
        out["profiles"].append(g_profile)
    out["death"] = death
    out["next_hit_index"] = hit_index
    return out if out["groups"] else None
