"""Vecteurs NORMAL-LIKE et DIRECT (`_DamageOpsMixin.execute_normal_like` /
`execute_direct`), extraits d'`operations/damage_ops.py` (scission du module >1000 lignes,
tache #169 -- deplacement VERBATIM, zero changement de comportement).

  - `execute_normal_like` : node `StatAmount`/`PercentageOf` (splash Psyker...) ;
  - `execute_direct` : degat `Direct(...)` (DoT de tuile).

PATCH-POINT (tests/probes) : ces deux vecteurs resolvent leurs dependances dans les globals
de CE module -- patcher `damage_ops.normal_like.<nom>`, jamais le `__init__` du package.
"""
from __future__ import annotations

from ....services.damage_prediction import get_base_damage_fix64, apply_pierce_and_modifiers
from ....services.damage_modifiers import apply_all_modifiers
from ...state import State
from ...components import (StatsComponent, HealthComponent, UnitComponent,
                           unit_prevents_overkill)
from ...damage_model import (attacker_modifiers, defender_modifiers, apply_elevation_bonus,
                             apply_trench_reduction, ice_crit_damage_addition,
                             defender_fixed_armor)
from ..damage_hits import HitDamage


class _NormalLike:
    """Vecteurs `normal-like` et `direct`. Sans etat (staticmethods) ; agrege par
    `_DamageOpsMixin`."""
    __slots__ = ()

    @staticmethod
    def execute_normal_like(state: State, attacker_id: int, target_id: int, base: int,
                            profile_pierce: int, hits: int = 1, spread_pct: int = 20,
                            damage_profile: Optional[str] = None,
                            is_melee: Optional[bool] = None,
                            ability_type: Optional[int] = None,
                            is_attack_damage_op: bool = True) -> Optional[dict]:
        """Attaque dont le node de dégât est un `StatAmount`/`PercentageOf(StatAmount(...))` (ex. splash
        Psyker = `PercentageOf(StatAmount(Attack), psykerExtraDmg%)`, profil Psychic). Pipeline
        **reduce-then-roll** (bornes pré-réduites puis tirage, post_roll=None), comme l'attaque normale
        (≠ ability RandomAmount), avec base + perçage de profil DONNÉS. Mute les PV de la cible.
        `spread_pct` = variance d'arme (DamageSpreadPercentage) : **0 pour un montant `StatAmount`**
        (mono-valeur, AUCUNE variance — confirmé live, splash Psyker = base exact) ; 20 seulement si le
        node porte de vraies bornes min/max d'arme. Renvoie le dict résultat (per_hit/total/...) ou None.

        `is_attack_damage_op` = LA FAMILLE DE FACTORY NATIVE du coup (cf. `_run_hits`) — threadé par la
        feuille DSL depuis son `native_factory`. Il ne pilote ICI qu'une seule chose : l'ORDRE bouclier ×
        limites (famille ABILITY = `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`,
        cap sur le RESTE post-bouclier ; famille ATTACK = cap sur le total, split en aval). Le resolve
        slot-8 qu'il gate aussi dans `_run_hits` n'existe pas sur ce vecteur (bornes pré-réduites,
        `post_roll=None`) → défaut `True` = comportement historique strictement inchangé pour les
        appelants qui ne le renseignent pas (attaque normale d'un summon, …)."""
        from ..damage import AttackDamageOperation  # lazy : rompt le cycle damage<->damage_ops
        if state.rng is None:
            return None
        att = state.get_entity(attacker_id)
        tgt = state.get_entity(target_id)
        sc = att.get_component(StatsComponent) if att is not None else None
        thc = tgt.get_component(HealthComponent) if tgt is not None else None
        if sc is None or thc is None:
            return None
        ctx = sc.ctx
        ahc = att.get_component(HealthComponent)
        # #106 (fork IsMeleeAttack) : NATURE DU COUP threadee dans la collecte attacker-modifiers, comme
        # `execute` (attaque normale, `_ranged` de l'arme) et `execute_ability_attack` (#47, `not is_melee`).
        # CETTE facade RECEVAIT deja `is_melee` (elle le passe a `defender_modifiers` et au perçage de
        # profil du caller) mais NE le threadait PAS a l'axe ATTAQUANT -> `is_ranged=None` remontait
        # jusqu'aux gates `IsMeleeAttack`/`IsRangedAttack` des effets. Le natif ne connait PAS cet etat :
        # `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` / `IdunBattle.Core.Services.BattleQuery$$IsRangedAttack`
        # rendent un BOOL depuis l'`AttackRangeType` de l'ability du coup (None=0 -> les DEUX faux ;
        # Melee=1 -> melee ; Ranged=2 -> ranged ; Both=3 -> `AreUnitsInMelee` position-based sauf flag 0x15).
        # Consequence du gap : le splash Psyker (`is_melee=False`, RANGED) recevait les bonus MELEE-only
        # (Waaagh_ExtraDamage/CrushingStrike : `if is_ranged:` avec None FALSY -> appliques) et PERDAIT les
        # bonus RANGED-only (RangedSpecialist/HeavyWeapon), a l'inverse de la face PREDICTION du meme coup
        # (`playbook/psyker.py` passe `is_ranged=True`). `is_melee is None` (appel direct hors des deux
        # call-sites portes, qui passent tous un bool) -> None conserve = gates inertes.
        _ranged = (not is_melee) if is_melee is not None else None
        mods, active = attacker_modifiers(state, attacker_id, ahc.hp if ahc else None, target_id=target_id,
                                          is_ranged=_ranged)
        # #45f : feuilles POSITIONNELLES du builder PARTAGE IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction (elevation/trench) — appliquees
        # a TOUT vecteur d'attaque par le natif (aucun gate normale/ability ; cf. execute_ability_attack,
        # meme fix, probe_45f_gfa_elevation). Le vecteur normal-like (splash Psyker / amount-mode) les
        # sautait aussi -> splash caste en surplomb ~33% bas.
        apply_elevation_bonus(state, mods, attacker_id, target_id)
        apply_trench_reduction(state, mods, attacker_id, target_id, damage_profile)
        tsc = tgt.get_component(StatsComponent)
        armor = defender_fixed_armor(state, target_id)   # FOYER partagé (base GetStat(16) + aura Protector allié)
        # #59 suite : threade is_melee + profil -> malus DÉFENSEUR gatés (cf. execute_ability_attack).
        # None (caller non mis à jour) = comportement historique — INERTE sans effet de défense gaté.
        def_mods, _da = defender_modifiers(state, target_id, thc.hp,
                                           is_melee=is_melee, damage_profile=damage_profile,
                                           attacker_id=attacker_id, is_normal_attack=False)  # #112 spéciale
        # BLOCK (cible) = base (GetStat 7/8) + sources d'effet (BeastSlayer...) via le helper PARTAGE
        # `_block_sources` (mirror du GetMultiValueStat(7)/IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances unique du natif).
        # #65 : `damage_profile` gate le trait NoBlocking (profil Psychic bypasse le block, mirror ExecuteHit).
        block_sources = AttackDamageOperation._block_sources(tsc, _da, armor, damage_profile)
        # `On(PreAttackHit=6)` — meme vecteur per-coup natif (ExecuteHit, en tete du coup, avant le crit).
        from ..triggers.dispatch import pre_attack_hit_triggers   # lazy : cycle damage<->triggers
        pre_attack_hit_triggers(state, attacker_id, target_id,
                                ranged=not bool(is_melee) if is_melee is not None else False,
                                profile=damage_profile, is_first_hit=True, ability_type=ability_type)
        # Identites du coup -> `att_ctx` du canal CRIT, bati DANS `_crit_params` (foyer unique, mirror
        # de l'`AbilityEntities` de `GetCritDamageBonusFromEffects`).
        crit_chance, crit_damage, crit_enabled = AttackDamageOperation._crit_params(
            ctx, active, state, attacker_id, target_id)
        # #120 : réduction PLATE défenseur (Nightshroud, ungated -> splash/normal-like aussi) fusionnée pré-perçage.
        AttackDamageOperation._apply_defender_flat_reductions(mods, def_mods)

        def _reduced(eff_base: int, flat_add: int = 0) -> "HitDamage":
            # #75 (case-68 MAJ 13) : additif ForAddition ATTAQUANT = PRÉ-perçage en COMBAT.
            # `flat_add` (#45f) = EffectBonus.addition PER-BRANCHE (Ice crit-only) : POST-spread
            # PRE-perçage, sans polluer `mods` (applique aux deux branches).
            # R6 MATERIALISATION DES BORNES REDUITES = `Fix64$$Round(., AwayFromZero)`, PAS la
            # troncature -- MEME etage, MEME fonction native que l'attaque NORMALE (#131) et que
            # l'ability bounds-mode famille ATTACK (campagne HeavyGravCannon). Ce vecteur porte le
            # mode `amount` de la feuille `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`
            # ET le `UseNormalAttackIfAble` on-appearance d'un summon : famille ATTACK dans les deux
            # cas -> `IdunBattle.Operations.AttackDamageOperation$$Execute` -> `ExecuteHits` ->
            # `ExecuteHit`, dont la cellule vient du slot 4
            # `IdunBattle.Core.Services.DamagePrediction$$PredictAttack` (cache -> `PredictAttackRaw`)
            # resolu par le slot 8 `IdunBattle.Core.Services.DamagePrediction$$
            # RandomlyResolveMinMaxDamage`. Le dernier etage de `CalculateBaseDamageWithAllModifiers`
            # est le MULTIPLICATEUR (slot 0x10 -> `IdunBattle.Core.Services.DamageCalculations$$
            # CalculateBaseDamageWithModifiers`), LU verbatim :
            #     v = Mul(dmg, multiplier) ; v <= 0 -> 0 ; 0 < v < 1 -> 1 ; sinon Round(v, 1)
            # traverse des qu'un `Nullable<DamageModifiers>` HasValue. Tronquer ici etait donc un
            # FORK DE PORT (une operation native, deux facades offline dont une fausse).
            # MESURE LIVE (probe_r6_round_materialize --case normal_like ; `ultraInceptorSgt` caste
            # DeathFromAbove -> l'`ultraSmnInceptor` frappe 6x Bolter pierce 20 sur `necroWarden`
            # force en regime percage-dominant, bornes brutes [798,1196] -> cellules [159,239]
            # tronquees vs [160,239] arrondies) : 5 seeds x 6 coups, live == ARRONDI **30/30**,
            # live == troncature **0/30** ; GENERALISATION regime MIXTE (armure 800 : bord bas en
            # branche percage, bord haut en branche armure) +18/18 arrondi, 0/18 troncature ;
            # TEMOIN (armure 300 -> branche `d - armure` des DEUX cotes, valeurs ENTIERES) :
            # 2 seeds x 6 coups, les deux modeles coincident ET valent le live 12/12 -- ce qui
            # REFUTE « l'arrondi collait par chance » / « un additif oublie ».
            # BILAN : 60 coups, live == arrondi 60/60, live == troncature 12/60.
            # STRICTEMENT NO-OP hors regime discriminant (valeur deja entiere -> Round == identite).
            mm = get_base_damage_fix64(eff_base, spread_pct=spread_pct)
            lo = apply_all_modifiers(apply_pierce_and_modifiers(
                mm.min + flat_add, profile_pierce, armor, mods, attacker_additive_pre=True),
                def_mods, round_materialize=True)
            hi = apply_all_modifiers(apply_pierce_and_modifiers(
                mm.max + flat_add, profile_pierce, armor, mods, attacker_additive_pre=True),
                def_mods, round_materialize=True)
            return HitDamage(lo, hi)

        # #45f : bonus crit-sur-Ice per-coup-CRIT (cf. execute_ability_attack, meme mirror IdunBattle.Entities.Effects.IceEffect$$CreateEffectDamageBonusForAttack).
        _ice_add = ice_crit_damage_addition(state, attacker_id, target_id, ctx) if crit_enabled else 0
        hit_nc = _reduced(base)
        hit_cr = _reduced(base + crit_damage, flat_add=_ice_add) if crit_enabled else hit_nc
        # #202 WeaverOfFate : attaquant max-out (effet 1185) -> bornes degenerees a (max, max) — le
        # splash Psyker / smite passe par `IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$GetDamage` (meme gate).
        hit_nc, hit_cr = AttackDamageOperation._apply_max_out(state, attacker_id, hit_nc, hit_cr)
        hits = max(1, int(hits))
        shc, shield_total = AttackDamageOperation._target_shield(tgt)      # bouclier shield-first
        r = AttackDamageOperation._run_hits(state.rng, hit_nc, hit_cr, crit_chance,
                                            crit_enabled, hits, block_sources,
                                            shield=shield_total,   # post_roll=None (reduce-then-roll)
                                            capped_reductions=def_mods.capped_reductions,
                                            # #67 : etage limites — mode 2 = ability/splash
                                            # (`IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`)
                                            limits=AttackDamageOperation._target_limits(
                                                tgt, thc, damage_profile, is_special=2),
                                            limits_hp=int(thc.hp or 0),
                                            # #195 : `HasFlag(defender, 0x13)` — le 5e argument
                                            # `isPreventOverkill` que `ApplyTraitDamageLimitsToDamage`
                                            # lit lui-meme sur son parametre `defender`.
                                            prevent_overkill=unit_prevents_overkill(state, target_id),
                                            # famille de factory native : pilote l'ordre bouclier x limites
                                            is_attack_damage_op=is_attack_damage_op)
        AttackDamageOperation._deplete_shield(shc, r)
        AttackDamageOperation._apply_damage_pipeline(                   # chokepoint partage (#202)
            state, target_id, attacker_id, tgt, thc, r["total"], damage_profile,
            r["shield_dmg"], r["armor_dmg"],
            last_hit=(r["per_hit"][-1] if r.get("per_hit") else None),
            # #R33 : decomposition per-coup (crit / denied) pour `didOverkill`.
            hits_result=r,
            # `On(0x10)` : cet appel EST la serie de coups sur CETTE cible -> il contient le coup
            # d'index 0 (`IsFirstHitInSeries` VRAI, mirror `AbilityEntities+0x110`).
            is_first_hit=True)
        # VECTEUR AFTER-HIT (splash StatAmount) : idem execute_ability_attack — reset ActOfFaith au crit
        # (#138) + vecteur complet (#140). `ranged` = POSITION-based (mirror IsRangedAttack), calculé dedans.
        # `ability_type` = kind AbilityOrEffect du coup (smite Psyker 0x3f5 -> branche 2 AddIce #35).
        from ..triggers import after_hit_ability_attack
        after_hit = after_hit_ability_attack(state, attacker_id, target_id, r["did_crit"],
                                             profile=damage_profile, ability_type=ability_type,
                                             did_block=r["did_block"])
        return {"hits": hits, "total": r["total"], "base": base, "pierce": profile_pierce,
                "armor": armor, "after_hit": after_hit,
                "clean_min": hit_nc.min * hits, "clean_max": hit_nc.max * hits,
                "did_crit": r["did_crit"], "did_block": r["did_block"], "did_evade": r["did_evade"],
                "crits": r["crits"], "rolls": r["rolls"], "per_hit": r["per_hit"]}

    @staticmethod
    def execute_direct(state: State, source_id: int, target_id: int, base: int,
                       profile_pierce: int,
                       damage_profile: Optional[str] = None) -> Optional[dict]:
        """Dégât DIRECT d'un nœud `Direct(...)` (mirror `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage`
        + `AttackDamageBehaviour` sur nœud `Direct` — factory DISTINCTE de `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage). La `base` (déjà calculée par le dégât-node, ex. `PercentageOf(StatAmount(Health,
        Max), fireDmgPct)` du DoT feu) est routée par le SEUL perçage/armure (`apply_pierce_and_modifiers`,
        mods=None) — AUCUN crit / block / bouclier / spread / tirage RNG / after-hit (≠ l'attaque
        d'ability `execute_ability_attack`/`execute_normal_like`). Utilisé par le DoT de tuile `EnvFireTile`
        (`IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour`) : occupant non-immune → `PercentageOf(20%, PV max)`
        percée par le PiercingRatio du profil (Flame=25), l'armure absorbant le non-percé. Mute les PV de la
        cible + route la mort (`_fire_death_if_killed`, source = la tuile). `<= 0 dmg` → no-op (return None).
        `source_id` = l'entité-source (tuile) pour l'attribution de mort ; `profile_pierce` = perçage effectif
        (le caller passe `profile_pierce(None, profile)` = PiercingRatio brut — la tuile n'a pas de stats
        ExtraPierce)."""
        from ..damage import AttackDamageOperation  # lazy : rompt le cycle damage<->damage_ops
        tgt = state.get_entity(target_id)
        thc = tgt.get_component(HealthComponent) if tgt is not None else None
        if thc is None or thc.hp is None:
            return None
        armor = defender_fixed_armor(state, target_id)   # FOYER partagé (DoT tuile réduit par l'armure défenseur)
        dmg = int(round(apply_pierce_and_modifiers(int(base), pierce_pct=int(profile_pierce),
                                                   armor=armor, mods=None)))
        if dmg <= 0:
            return None
        # #30 (#60bis) MEMBER-CAP du degat DIRECT — mirror `ApplyTraitDamageLimitsToDirectDamage
        # IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDirectDamage` (= `IdunBattle.Core.Services.DamagePrediction$$ApplyGroupUnitDamageLimit` avec profile=NULL : PAS de bypass
        # Blast possible), meme wrapper que le chemin `IdunBattle.Core.Services.DamagePrediction$$CalculateDirectDamage` de
        # `IdunBattle.Operations.DirectDamageOperation$$Execute`. Un degat direct ne tue AU PLUS qu'UN membre :
        # cap = hp - maxHealthWith(remaining-1), applique au montant NET (post percage/armure —
        # l'etage limites de `IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation` opere apres la FixedArmor plate).
        # PROUVE LIVE (probe_60bis seeds 60112/60113) : scarab PLEIN (2218, 5 membres) sur tuile en
        # feu -> tick natif 443 = cap exact (vs 444 non-cape, modele verifie par ailleurs a 444 nu
        # rem=1 et 111 sous aura +886). Doc : case-60 par. 5 (resolu).
        tuc = tgt.get_component(UnitComponent)
        if tuc is not None and thc.hp_max:
            import gameconfig as GC
            n = int((GC.unit(tuc.visual_id) or {}).get("nrOfMembers") or 1)
            if n > 1:
                from ....services.trait_damage_limits import apply_group_unit_damage_limit
                dmg = apply_group_unit_damage_limit(dmg, False, n, int(thc.hp_max), int(thc.hp))
        hp_before = thc.hp
        # Chokepoint partage (#202), `is_attack=False` : PAS de `_record_attacked` (un DoT n'est PAS une
        # attaque — compteur HasBeenAttackedAmountThisTurn) ; la cle profil "recu ce tour" est posee
        # (le natif route tout HP-loss par ApplyDamage -> RegisterDamage) ; `damage_profile` None
        # (caller non threade) = pas de cle. NB : execute_direct ne consulte PAS IsAttackMaxOutDamage
        # (aucun call site natif sur la voie DirectDamage).
        AttackDamageOperation._apply_damage_pipeline(
            state, target_id, source_id, tgt, thc, dmg, damage_profile, is_attack=False)
        return {"total": dmg, "base": int(base), "pierce": int(profile_pierce), "armor": armor,
                "hp_before": hp_before, "hp_after": thc.hp}
