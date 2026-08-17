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

from ..components import (StatsComponent, PositionComponent, UnitComponent,
                          OwnerComponent, unit_prevents_overkill, unit_state_for_effects,
                          can_be_overkilled, unit_is_overkilled)
from ..damage_model import target_trait_names
from ..state import State
from ...services.damage_prediction import get_base_damage_fix64, apply_pierce_and_modifiers
from ...services.damage_config import resolve_spread_pct
from ...services.damage_modifiers import apply_all_modifiers
from ...entities.effects import additional_hit_groups, aura_additional_hits_from_allies
from ...entities.damage_trait import DamageTrait
from engine.entities.effects.loki.hits import MAUGETAR_CTX_ATTACK_HAD_CRITICAL as _CTX_ATTACK_HAD_CRITICAL   # #1042-r5
from engine.entities.effects.ctx_keys import CTX_TERTIARY_ABILITY_STATE_OF as _CTX_TERTIARY_ABILITY_STATE_OF   # #1042-r5
from engine.entities.effects.ctx_keys import (CTX_TGT_FIXED_ARMOR_INITIAL as _CTX_TGT_FIXED_ARMOR_INITIAL,
                                              CTX_TGT_FIXED_ARMOR_NEGATIVE_MOD as _CTX_TGT_FIXED_ARMOR_NEGATIVE_MOD)   # #884-r2
from engine.entities.effects.loki.norn_crown import CTX_TGT_EFFECT_NAMES as _CTX_TGT_EFFECT_NAMES   # #1042-r5
from ...entities.stats import StatPart, StatType     # #884-r2 : `StatAmount(., FixedArmor, Initial)`


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
    # UN `Round` PAR FACE (#437-r1) : ces sous-operations retombent sur le MEME
    # `AttackDamageOperation$$ExecuteHit` que la phase d'arme, donc sur les MEMES deux etages
    # `CalculateBaseDamageWithModifiers`. Depuis #437-r1-r1-r1 la separation est INCONDITIONNELLE
    # dans `apply_pierce_and_modifiers` (plus de drapeau) : rien a poser ici.
    return apply_all_modifiers(
        apply_pierce_and_modifiers(value, g_pierce, armor, mods, hit_mult=hit_mult,
                                   attacker_additive_pre=True),
        def_mods, round_materialize=True)


def _target_fixed_armor_ctx(state: State, target_id: int) -> dict:
    """Les deux scalaires d'armure de la CIBLE, en TRI-ETAT (#884-r2).

    `StatAmount(Subject, 0x10 = FixedArmor, statPart 3 = Initial)` et
    `StatNegativeModification(Subject, 0x10)` -- les deux entrees de
    `...OrbsOfDecayAbility$$GetTriggerForAttack`. Cible sans `StatsComponent` -> les deux cles
    valent `None` (NON MESURE), et le gate se ferme cote effet."""
    tgt = state.get_entity(int(target_id)) if target_id is not None else None
    sc = tgt.get_component(StatsComponent) if tgt is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return {_CTX_TGT_FIXED_ARMOR_INITIAL: None, _CTX_TGT_FIXED_ARMOR_NEGATIVE_MOD: None}
    stats = getattr(ctx, "stats", None)
    initial = ctx.get_stat(int(StatType.FIXED_ARMOR), int(StatPart.INITIAL))
    neg = (stats.negative_stat_modification(int(StatType.FIXED_ARMOR))
           if stats is not None else None)
    return {_CTX_TGT_FIXED_ARMOR_INITIAL: (None if initial is None else int(initial)),
            _CTX_TGT_FIXED_ARMOR_NEGATIVE_MOD: (None if neg is None else int(neg))}


def collect_additional_hit_groups(state: State, attacker_id: int, target_id: int,
                                  att_active, is_melee: bool, tgt_active,
                                  attack_hit_damage: "Optional[tuple]" = None,
                                  t_pos: "Optional[tuple]" = None,
                                  tile_effects_by_pos: "Optional[dict]" = None,
                                  persistent_data=None,
                                  damage_profile: "Optional[str]" = None,
                                  attack_had_critical: "Optional[bool]" = None,
                                  is_normal_attack: "Optional[bool]" = None,
                                  is_charging: "Optional[bool]" = None) -> list:
    """#202-B : mirror `IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsFromEffectsInternal`
    cote ECS — enumeration GLOBALE des effets declarant des coups additionnels HETEROGENES (canal
    #179) : (a) effets du PORTEUR (`additional_hit_groups`, ex. SquigHound/CordClaw/FoulInfusion) ;
    (b) effets-AURA hostes sur d'AUTRES unites VIVANTES (`create_aura_additional_hits_for_ally`,
    ex. ExplosiveMaladies/InfernalPacts) — adjacence evaluee aux positions REELLES de l'ECS, mirror
    du refresh natif `PreAttack(5)` (l'aura est reevaluee au moment de l'attaque, IdunBattle.Entities.Effects.Loki.InfernalPacts_AdditionalHitsEffect$$GetRefreshTriggers).
    Retour [] strict (aucun carrier -> no-op, AUCUNE conso RNG).

    #227 — trois entrees d'ETAT supplementaires, exigees par `LetTheGalaxyBurnEffect` (le natif les
    lit sur l'`AbilityEntities` que `GetAdditionalHitsFromEffectsInternal` recoit ; ici elles sont
    threadees explicitement par les deux facades COMBAT) :
      - `attack_hit_damage` = `(min, max)` BRUTS du `IdunBattle.Core.HitDamage` de l'AttackData de
        CETTE attaque = ce que rend `IdunBattle.Entities.Formulas.
        FirstHitInCurrentAttackDamageRange$$CalculateMin/Max` (la liste `currentAttack@+0x50` est
        alimentee par `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` avec les 16
        premiers octets de l'AttackData, dont le champ 0 EST ce `HitDamage`) ;
      - `t_pos` + `tile_effects_by_pos` = noeud `HasTileStatusEffect(Targets@0x190)` ;
      - `persistent_data` = cles du `PersistentDataComponent` de l'ATTAQUANT -> `IsPersistentData`.
    Non fournies -> les descripteurs qui en dependent se taisent (aucun autre n'y touche).

    #204 — la branche (b) N'EST PAS « les auras d'ALLIES » : c'est **tout descripteur porte par une
    entite AUTRE que l'attaquant**, exactement comme l'enumeration native, qui est GLOBALE et laisse
    la CONDITION du descripteur trancher. Deux conditions coexistent desormais :
      - `get_OwnerIsCaster` (le porteur de l'effet EST l'attaquant : ExplosiveMaladies, InfernalPacts,
        `AstartesBanner_AdditionalHitsEffect` dont le `CreateTargetSelector` = `SurroundingFriends`
        designe les BENEFICIAIRES) ;
      - `get_OwnerIsTarget` (le porteur de l'effet EST la CIBLE de l'attaque :
        `IdunBattle.Entities.Effects.Loki.MasterAnnihilator_AdditionalHitEffect$$CreateAdditionalHits`).
    D'ou `tgt_id` et `damage_profile` dans le ctx : le premier EST le predicat `OwnerIsTarget`, le
    second le noeud `AreEqual(CurrentAttackDamageProfile, 0xd=Psychic)`. `attack_hit_damage` y est
    aussi relaye : `FirstHitInCurrentAttackDamageRange` ne depend pas de QUI porte l'effet."""
    import gameconfig as GC
    # DIFFERE PORTEUR : `triggers.base` importe `..components` / `..state`, qui re-entrent ce paquet
    # d'operations -- meme forme que le differe du meme foyer dans `damage.py::_positional_att_ctx`.
    from .triggers.base import triggered_ability_state as _triggered_ability_state
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
              _CTX_TGT_EFFECT_NAMES: frozenset(
                  n for n in (getattr(e, "name", None) for e in (tgt_active or [])) if n),
              # #227 : etat lu par `LetTheGalaxyBurnEffect` (gate + degat), cf. docstring.
              "attack_hit_damage": attack_hit_damage,
              "t_pos": t_pos,
              # #419-r1-tr11-r3 : la tuile d'ATTAQUE. Le `ctx` portait deja `t_pos` mais PAS
              # `att_pos`, donc tout gate de DISTANCE y etait inevaluable -- c'est ce qui bloquait
              # le port de `SpecialIssueCombiMelta_AdditionalHits` (1563, `IsAtRange(Caster@+0x48,
              # Target@+0x60, DSLFormulas+0x28 = Const(2))`). Lue sur l'ECS comme `t_pos` : cote
              # COMBAT la tuile d'attaque EST la position reelle de l'attaquant (le pendant
              # PREDICTION thread, lui, la tuile CANDIDATE). Absente -> le gate rend FAUX.
              "att_pos": (ap.col, ap.row),
              "tile_effects_by_pos": tile_effects_by_pos,
              "persistent_data": persistent_data,
              # #1006 -- IDENTITE des deux slots que la boucle native ecrit dans l'`AbilityEntities`
              # qu'elle passe a chaque descripteur : `Owner@+0x18` et `Caster@+0x48`. Sur CETTE
              # branche le porteur EST l'attaquant (le natif enumere globalement et laisse la
              # condition du descripteur trancher ; ici l'enumeration est deja restreinte a
              # `att_active`), donc les deux valent `attacker_id`. Sans elles, tout gate
              # `get_OwnerIsCaster` -- et surtout toute lecture d'`AbilityState` PAR PORTEUR --
              # etait inevaluable sur cette branche, alors que le canal AURA les portait deja.
              "owner_id": attacker_id, "att_id": attacker_id,
              # #1065 -- les DEUX conjoints restants du trigger de
              # `IdunBattle.Entities.Effects.Loki.FragLanceEffect$$CreateAdditionalHits`
              # (`get_OwnerIsCaster & IsNormalAttack & IsCharging(Caster@+0x60, Target@+0x78)`).
              # `is_normal_attack` = nature du VECTEUR (MEME donnee, meme nom et meme tri-etat que
              # le parametre homonyme des canaux COUPS-D'ARME et PENETRATION) : les deux facades
              # COMBAT la connaissent par construction (`damage_ops/normal.py` = True,
              # `damage_ops/ability.py` = False). `is_charging` = foyer UNIQUE
              # `runner.damage_model.battle_query_is_charging`, MEME cle que le canal DEGAT
              # (`att_ctx["is_charging"]`) et que le canal COUPS D'ARME -- aucun predicat
              # re-derive. Tri-etat : `None` = NON MESURE -> le gate rend FAUX (`is_charging_attack`
              # est la forme POSITIVE, cf. `entities/effects/base.py`), jamais permissif.
              "is_normal_attack": is_normal_attack, "is_charging": is_charging,
              # #1006 -- `IdunBattleLogic.Entities.DSLTriggers$$AttackDamageIsCritical`. Le natif
              # l'evalue sur l'`AbilityEntities` que
              # `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamage
              # ProfileType` remplit AVANT d'appeler `GetAdditionalHitsFromEffectsInternal` : il y
              # recopie `hitGroup+0x3d` (le groupe de coups d'ARME qui vient d'etre resolu) juste
              # apres `currentAttack+0x50`. C'est donc un etat de PORTEE ATTAQUE (« cette attaque
              # contient-elle un crit ? »), pas un tirage per-coup -- ce que dit aussi l'i2 de
              # `Maugetar` (« his attacks that CONTAIN a Crit »). Tri-etat : `None` = NON MESURE
              # (appelant qui ne thread pas), et le descripteur rend alors FAUX, jamais permissif.
              _CTX_ATTACK_HAD_CRITICAL: attack_had_critical,
              # #1006 -- `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState`, delegue au foyer
              # UNIQUE `triggered_ability_state` (#357) : etat TERTIAIRE pour une relique EQUIPEE,
              # etat PASSIF pour un kit npc. MESURE (probe_959) : l'instance d'effet captee publie
              # `ability_level = 50` quel que soit le niveau de la relique -- sans ce callable, un
              # descripteur de relique lirait TOUJOURS le dernier palier.
              _CTX_TERTIARY_ABILITY_STATE_OF:
                  lambda oid, ability: _triggered_ability_state(state, int(oid), ability),
              # #884-r2 / #1003-r1 -- les DEUX scalaires d'armure de la CIBLE, que
              # `...OrbsOfDecayAbility$$GetTriggerForAttack` lit sur son `Subject@+0x68`. HORS
              # `Filter` -- ce qui est le cas de ce canal -- ce slot vaut la cible ORIGINALE de
              # l'attaque : c'est le << **on** the target's hex >> de l'i2, par opposition au
              # << adjacent to >> que porte le volet ABILITY (`triggers/loki/orbs_of_decay.py`,
              # dont le `Filter` lie chaque VOISIN au meme slot). Les deux moities de la meme
              # phrase, deux artefacts natifs.
              # `StatAmount(., 0x10 = FixedArmor, 3 = Initial)` et `StatNegativeModification(., 0x10)`
              # -- MEMES foyers que partout (`UnitStats.get_stat` / `.negative_stat_modification`),
              # aucun predicat re-derive. TRI-ETAT : `None` = cible sans `StatsComponent` -> le gate
              # se FERME cote effet, jamais un 0 rabattu (qui, avec `initial = 0`, ferait diviser
              # par zero la ou le natif court-circuite).
              **_target_fixed_armor_ctx(state, target_id)}
    groups = list(additional_hit_groups(att_active, ah_ctx))
    carriers = []
    for uid, e in state.entities.items():
        if uid == attacker_id:
            continue
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or pc is None or oc is None or not uc.alive:
            continue
        effs = (state.effects.active_effects(uid, unit_state_for_effects(state, uid))
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
                   "is_melee": is_melee,
                   # #204 : entrees des descripteurs `OwnerIsTarget` / a degat
                   # `FirstHitInCurrentAttackDamageRange` portes hors de l'attaquant.
                   "tgt_id": target_id, "t_pos": t_pos, "damage_profile": damage_profile,
                   "attack_hit_damage": attack_hit_damage,
                   # #943-r7 -- le BOARD, d'ou les descripteurs derivent les DEUX canaux du substrat
                   # d'adjacence NATIF (`AdjacentFriends(owner, 1)` -> `AdjacentTiles` -> la liste
                   # STOCKEE). MEME cle et MEME semantique que le ctx du canal DEGAT
                   # (`damage_model._apply_ally_attack_damage_auras`) et que les DEUX ctx de la face
                   # PREDICTION (`playbook/prediction/normal_attack.py`) -- pas de fork.
                   # Consommateurs : `ExplosiveMaladies_Extra(Ranged|Melee)AttackEffect`,
                   # `InfernalPacts_AdditionalHitsEffect`. `None` -> repli geometrique NOMME.
                   "board": state.board})
    return groups


def execute_additional_hits(state: State, attacker_id: int, target_id: int, tgt, thc,
                            groups: list, mods, def_mods, armor: int, hit_mult: int,
                            block_sources, shc, spread_pct: "Optional[int]" = None,
                            extra_pierce: int = 0, bonus_hit_chance: "Optional[int]" = None,
                            hit_index0: int = 0, crit_allowed0: bool = True,
                            attack_profile: "Optional[str]" = None,
                            hit_interceptor=None, failed_block0=None,
                            damaging_done0: bool = False,
                            source_ability: "Optional[int]" = None) -> "Optional[dict]":
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
        `Nullable<int>` au champ **+0x110** puis dispatche l'event **`On(8)`** (et `On(0x3c = UnitBlocked)` si
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

    #407 -- RESIDU « failed_block remis a zero entre phase d'arme et groupes » FERME. Le natif
    persiste la failed-list PAR ATTAQUE, et c'est LU, pas suppose : `IdunBattle.Core.OngoingAttack$$
    .ctor` cree `+0x48 = new List<int>()` (FailedBlockIds, NEUVE par attaque) ;
    `IdunBattle.Operations.ADamageOperation$$GetFailedBlockIds` la rend (`HasCurrentAttack() ?
    GetCurrentAttack().FailedBlockIds : new List<int>()`) ; `IdunBattle.Operations.ADamageOperation$$
    SetupHitGroup` la seme PAR REFERENCE dans `OngoingHitGroup+0x60` ; `IdunBattle.Operations.
    ADamageOperation$$RegisterBlocks` y AddRange les ids echoues de chaque coup. Les DEUX voies de
    coups additionnels retombent dessus : la voie SANS profil recoit le hitGroup de la phase d'arme
    TEL QUEL (`AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType`, appelee inline
    par `Execute` avec son `hitGroup`), et la voie A PROFIL passe par une nouvelle
    `AttackDamageOperation$$Execute` dont le `SetupHitGroup` RE-LIT la meme liste de l'`OngoingAttack`.
    D'ou `failed_block0`, threade de groupe en groupe et rendu dans `out["failed_block"]`, EXACTEMENT
    comme `crit_allowed0`/`hit_index0`. Sans lui, une source de block ayant echoue pendant la phase
    d'arme etait RE-TIREE a chaque groupe -> tirages RNG en TROP (desynchronisation du flux).
    Residu (1) de case-202 §7 (gate `hp > 0`) toujours ouvert.
    None si aucun groupe qualifie (strict no-op retro-compat).

    Rappelle les primitives de tirage de `AttackDamageOperation` : import LAZY (cycle module
    damage <-> additional_hits ; `damage` est charge au moment de l'appel en bataille)."""
    if not groups or thc is None or int(thc.hp or 0) <= 0:
        return None
    # #449-r2-r4 : `spread_pct=None` = LU de `BattleConfiguration.Damage.DamageSpreadPercentage`
    # (le `state` porte la BC de CETTE bataille). Le defaut etait `20` en dur.
    spread_pct = resolve_spread_pct(spread_pct, state)
    import gameconfig as GC
    from .damage import AttackDamageOperation, HitDamage
    death = None
    out = {"groups": 0, "hits": 0, "total": 0, "per_hit": [], "rolls": [], "profiles": []}
    hit_index = int(hit_index0)      # `currentAttack+0x30` — CONTINU d'un groupe a l'autre (R6-b')
    # #366-r1-crit-multihit : `OngoingAttack+0x40` (`isCriticalDamageAllowed`) est porte par l'ATTAQUE
    # et re-seme dans chaque `OngoingHitGroup` par `SetupHitGroup` -> il traverse les groupes de coups
    # additionnels comme `hit_index`. Inerte tant que ces groupes tournent a `crit_enabled=False`,
    # threade pour que l'etat ne se recree pas a chaque sous-operation.
    crit_allowed = bool(crit_allowed0)
    # #407 : `OngoingAttack+0x48` (`FailedBlockIds`) -- JUMEAU BLOCK de `crit_allowed`, meme portee
    # (l'ATTAQUE) et meme threading. La liste est PARTAGEE PAR REFERENCE avec `OngoingHitGroup+0x60`.
    failed_block = set(failed_block0 or ())
    # #963-r2 : `isFirstDamagingHit` -- TROISIEME etat de portee ATTAQUE, threade comme les deux
    # ci-dessus. `damaging_done0` = « la phase d'arme a deja inflige du degat », mesure par
    # l'appelant sur SON total. Sans lui, un premier groupe entierement bloque ferait porter le flag
    # a AUCUN groupe suivant.
    _damaging_done = bool(damaging_done0)
    # #227 ORDRE DES DEUX CALL-SITES NATIFS. Un descripteur dont le `profileType` est un
    # `Nullable<DamageProfileType>` NULL (`EffectAdditionalHits$$Create(param_5 = -1)`, ex.
    # `LetTheGalaxyBurnEffect`) n'est PAS execute par la meme fonction que les autres :
    #   - profil NULL -> `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithout
    #     DamageProfileType` (il filtre justement sur ce champ), appelee INLINE par
    #     `IdunBattle.Operations.AttackDamageOperation$$Execute` (son SEUL appelant, xref) ;
    #   - profil pose -> `IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$
    #     Execute`, une SOUS-OPERATION planifiee, donc executee APRES le corps de l'`Execute`.
    # D'ou : groupes sans profil D'ABORD, tri STABLE (l'ordre d'enumeration des effets est conserve
    # a l'interieur de chaque famille). MESURE case-159 §2.c : le coup LetTheGalaxyBurn (1 tirage)
    # tombe bien AVANT les 2 coups du groupe FleshmetalGuns (4 tirages).
    groups = ([g for g in groups if g.get("profile") is None]
              + [g for g in groups if g.get("profile") is not None])
    for g in groups:
        if int(thc.hp or 0) <= 0:
            break
        # profil NULL -> le coup emprunte le profil de l'ATTAQUE (percage, trait NoBlocking et
        # `RegisterDamage` de l'arme) : c'est ce que fait `ExecuteHits` quand le `Nullable` du
        # groupe n'a pas de valeur (il retombe sur le profil deja porte par l'AttackData).
        g_profile = g.get("profile")
        if g_profile is None:
            g_profile = attack_profile
        dp = GC.damage_profile(g_profile) or {}
        g_pierce = max(0, min(100, int(dp.get("PiercingRatio") or 0) + int(extra_pierce or 0)))
        # BI-CANAL (#202-B, RE COMPLETEE par #159) — c'est ICI que se joue le `useDisplay` natif.
        # `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits(this, entities, useDisplay)` pose
        #     min = max = minNode.<slot 4>            (noeud DISPLAY)     si useDisplay
        #     min = amountNode.<slot 2> ; max = amountNode.<slot 3>       sinon (FACE COMBAT)
        # et `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamage
        # ProfileType` passe l'octet EXPLICITEMENT A ZERO -> la face COMBAT lit TOUJOURS le noeud
        # ROLL. D'ou la PRECEDENCE ci-dessous, qui EST le mirror de ce gate : `min`/`max` (noeud
        # ROLL) l'emportent des qu'ils existent ; `amount` (noeud DISPLAY) n'est que le repli.
        #
        # R6-c — ce repli n'est plus emprunte par AUCUN descripteur porte : ceux dont les DEUX
        # noeuds sont le MEME (`EffectAdditionalHits$$Create` param_8 = 0 -> minNode retombe sur
        # amountNode : FoulInfusion `ConfigVar(0xb)`, ExplosiveMaladies `ConfigVar(8)`) rendent
        # desormais `min == max == v`, ce qui est la lecture NATIVE de leur cellule : le noeud
        # unique est un SCALAIRE (`IdunBattle.Entities.Formulas.ConfigAmount`), donc les slots 2
        # et 3 lus par la face COMBAT rendent la MEME valeur. Cela change la CONSOMMATION autant
        # que la valeur -- `IdunBattle.Core.HitDamage$$GetDamage` ouvre sur
        # `if (*param_1 == param_1[1]) return *param_1;` -> 0 tirage la ou le spread ±20% en
        # consommait 1 (mesure live : natif 3 tirages, port 3, contrefactuel 4 ; 8/8 montages,
        # cf. `docs/rl/case-r6c-amount-group-bounds.md`).
        # Le repli reste en place comme DEGRADATION FIDELE pour un futur descripteur qui n'aurait
        # que sa face DISPLAY portee -- il n'est pas un chemin nominal.
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
        # #1020-r4 : chokepoint `On(0x39 = EventTriggerType.PreDamageTaken)` joue DANS la boucle
        # (cf. `damage_hits._run_hits`, bloc `POSITION DU TIRAGE`). `_damaging_done` est l'etat
        # THREADE de groupe en groupe -- il est deja LU ici, avant `_run_hits`, exactement comme
        # `crit_allowed` / `failed_block` / `hit_index`.
        _first_damaging = (not _damaging_done)
        _pdt_sink = AttackDamageOperation.make_pre_damage_taken_sink(
            state, attacker_id, target_id, thc, g_profile,
            is_first_damaging_hit=_first_damaging,
            # #1020-r6 : le groupe HERITE de l'`AbilityOrEffect` de son attaque parente. MEME
            # valeur que celle donnee au chokepoint ci-dessous, pour les memes raisons que dans
            # les trois autres vecteurs (`damage_ops/*.py`) : un seul point de resolution.
            source_ability=source_ability)
        r = AttackDamageOperation._run_hits(
            state.rng, hd, hd, 0, False, max(0, int(g.get("count") or 0)), g_block,
            shield=shield_total, pending_sink=_pdt_sink,
            # R6-b : `post_roll` = branche ROLL-THEN-REDUCE de `_one_hit` (tirage BRUT + resolve
            # slot-8 gaspille) ; `is_attack_damage_op=True` = famille ATTACK, les DEUX voies
            # natives de coups additionnels retombant sur `AttackDamageOperation$$ExecuteHits`.
            post_roll=_reduce, is_attack_damage_op=True,
            # R6-b' : MEME site d'evaluation du `Maybe` after-hit que les coups d'arme, avec
            # l'index CONTINU de l'ATTAQUE (`currentAttack+0x30`). Voir la docstring.
            bonus_hit_chance=bonus_hit_chance, hit_index0=hit_index,
            crit_allowed0=crit_allowed,   # #366-r1-crit-multihit (cf. ci-dessus)
            failed_block0=failed_block,   # #407 : `OngoingAttack+0x48` (cf. docstring)
            # #366-r1 : les groupes additionnels sont des SOUS-OPERATIONS de la MEME attaque et
            # repassent par `AttackDamageOperation$$ExecuteHit(s)` -> MEME intercepteur per-coup
            # (donc meme marqueur 1227, meme compteur de blocks), threade par l'appelant.
            hit_interceptor=hit_interceptor,
            limits=AttackDamageOperation._target_limits(tgt, thc, g_profile, is_special=1),
            limits_hp=int(thc.hp or 0),
            # #462-r4e-o : PV COURANTS + plancher -> `per_hit` = le tag `Amount` de l'event (retraits
            # REELS). Les PV sont A JOUR : chaque groupe passe par `_apply_damage_pipeline` avant le
            # suivant, comme le natif enchaine ses sous-operations.
            hp_current=(None if thc.hp is None else int(thc.hp)),
            hp_floor=thc.minimal_health,
            # #462-r4e-o-r1 : SITE (A) — `HasFlag(target, 8 = Overkilled)` relu PAR COUP. C'est
            # LE cas ou l'etat d'entree compte : le flag pose pendant la phase d'arme gate
            # TOUS les coups de ce groupe (le natif enchaine ses sous-operations sur la MEME cible).
            overkilled0=unit_is_overkilled(tgt),
            can_be_overkilled=can_be_overkilled(tgt),
            over_reduce0=int(thc.over_reduce or 0),
            # #195 : `HasFlag(defender, 0x13)` — le 5e argument `isPreventOverkill` que
            # `ApplyTraitDamageLimitsToDamage` lit lui-meme sur son parametre `defender`.
            prevent_overkill=unit_prevents_overkill(state, target_id))
        g_first_hit = (hit_index == 0)      # index d'ENTREE du groupe (avant `_run_hits`)
        hit_index = r["next_hit_index"]
        crit_allowed = r["crit_allowed"]    # #366-r1-crit-multihit : `attack[+0x40] &= hitGroup[+0x3c]`
        failed_block = r["failed_block"]    # #407 : `RegisterBlocks` -> `hitGroup[+0x60].AddRange(.)`
        # #1020-r1 : plus de `_deplete_shield` ICI. `ApplyDamageOperation$$ReduceShield` lit le
        # pending RELU (apres `On(0x39)`), donc la depletion vit dans le chokepoint, avec `Reduce`.
        d = AttackDamageOperation._apply_damage_pipeline(
            state, target_id, attacker_id, tgt, thc, r["total"], g_profile,
            r["shield_dmg"], r["armor_dmg"], is_attack=False,
            # #1020-r6 (FERME) : `source_ability` est desormais THREADE, et sa valeur n'est pas
            # devinee au site -- elle DESCEND de l'appelant, exactement comme le natif la fait
            # descendre. LU dans `IdunBattle.Operations.AttackDamageOperation$$
            # ExecuteAdditionalHitsWithoutDamageProfileType` : la fonction batit l'`AbilityEntities`
            # des groupes en construisant DEUX `Nullable<AbilityOrEffect>` a partir du MEME
            # `abilityOrEffect` recu de l'attaque parente, et les pose en `+0x60`
            # (`CurrentAbility`) ET en `+0x98` (`TriggeringAbility`) -- deux `Nullable$$.ctor`
            # consecutifs sur le meme bloc de 0x18 octets. La voie A PROFIL fait de meme :
            # `Core.Services.OperationProcessor$$ExecuteAdditionalHitsWithDamageProfileType`
            # RECOPIE son bloc d'options (0x18) et l'`AbilityEntities` (0x128) tels quels vers
            # `IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute`,
            # qui les repasse au slot `0x3c` sans les reconstruire. Un groupe additionnel ne porte
            # donc JAMAIS d'`AbilityOrEffect` propre : il porte celui de son attaque.
            # Ce canal alimente `AbilityEntities+0x98`, donc les `TriggeringAbilityIs` du vecteur
            # `On(0x39 = PreDamageTaken)` ET le gate `HasValue` d'`IdunBattle.Entities.Behaviours.
            # TransferDamageBehaviour$$Execute` (#1020-r2, qui `return` SANS RIEN FAIRE si l'un des
            # deux `Nullable<AbilityOrEffect>` est vide). Avant ce correctif, un transfert declenche
            # par un groupe de coups ADDITIONNELS etait REFUSE cote port alors que le natif
            # l'accepte -- divergence RESTRICTIVE, l'inverse de celle que #1020-r2 ferme.
            source_ability=source_ability,
            # `On(0x10)` : un groupe de coups ADDITIONNELS partage l'`OngoingAttack` de l'attaque (donc
            # son compteur `+0x30`, threade par `hit_index0`). Il ne contient le coup d'index 0 que si
            # la phase d'arme n'a rien emis avant lui -> `IsFirstHitInSeries` FAUX dans le cas usuel,
            # et donc AUCUN tirage 1203 sur ces coups (mirror du court-circuit natif).
            is_first_hit=g_first_hit,
            # #963-r2 : `isFirstDamagingHit` (`AbilityEntities+0x118`) -- l'etat « aucun degat
            # inflige jusqu'ici dans CETTE attaque », threade comme `crit_allowed`/`failed_block`.
            # Distinct de `g_first_hit`, qui ne parle QUE de l'index de coup : un groupe qui ne
            # porte pas l'index 0 est tout de meme le PREMIER a damager si la phase d'arme et les
            # groupes precedents ont ete entierement bloques.
            # #1020-r4 : MEME etat que celui donne au `pending_sink` ci-dessus.
            is_first_damaging_hit=_first_damaging,
            pre_damage_taken=AttackDamageOperation.pre_damage_taken_of(_pdt_sink))
        if int(r["total"] or 0) > 0:
            _damaging_done = True
        death = death or d
        out["groups"] += 1
        # coups REELLEMENT EXECUTES (R6-b' : un succes du `Maybe` defere un coup bonus DANS ce
        # groupe, donc `count` seul sous-compte). #462-r4e-o-r1 : ce n'est PLUS `len(per_hit)` --
        # depuis le port du SITE (A), un coup gate s'execute sans emettre d'event.
        out["hits"] += r["hits_executed"]
        out["total"] += r["total"]
        out["per_hit"] += r["per_hit"]
        out["rolls"] += r["rolls"]
        out["profiles"].append(g_profile)
    out["death"] = death
    out["next_hit_index"] = hit_index
    out["crit_allowed"] = crit_allowed
    out["failed_block"] = failed_block      # #407 : etat block de l'ATTAQUE en sortie
    out["damaging_done"] = _damaging_done   # #963-r2 : etat `isFirstDamagingHit` en sortie
    return out if out["groups"] else None
