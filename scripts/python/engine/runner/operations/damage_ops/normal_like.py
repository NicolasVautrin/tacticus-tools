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
from ....services.damage_config import resolve_spread_pct
from ....services.damage_modifiers import apply_all_modifiers
from ...state import State
from ...components import (StatsComponent, HealthComponent, UnitComponent,
                           unit_prevents_overkill, can_be_overkilled, unit_is_overkilled)
from ...damage_model import (attacker_modifiers, defender_modifiers, apply_elevation_bonus,
                             apply_trench_reduction, ice_crit_damage_addition,
                             defender_fixed_armor)
from ..damage_hits import HitDamage
from ....services.trait_damage_limits import apply_group_unit_damage_limit


class _NormalLike:
    """Vecteurs `normal-like` et `direct`. Sans etat (staticmethods) ; agrege par
    `_DamageOpsMixin`."""
    __slots__ = ()

    @staticmethod
    def execute_normal_like(state: State, attacker_id: int, target_id: int, base: int,
                            profile_pierce: int, hits: int = 1,
                            spread_pct: Optional[int] = None,
                            damage_profile: Optional[str] = None,
                            is_melee: Optional[bool] = None,
                            ability_type: Optional[int] = None,
                            is_attack_damage_op: bool = True,
                            is_first_hit: bool = True,
                            is_outside_attack: bool = True) -> Optional[dict]:
        """Attaque dont le node de dégât est un `StatAmount`/`PercentageOf(StatAmount(...))` (ex. splash
        Psyker = `PercentageOf(StatAmount(Attack), psykerExtraDmg%)`, profil Psychic). Pipeline
        **reduce-then-roll** (bornes pré-réduites puis tirage, post_roll=None), comme l'attaque normale
        (≠ ability RandomAmount), avec base + perçage de profil DONNÉS. Mute les PV de la cible.
        `spread_pct` = variance d'arme (DamageSpreadPercentage) : **0 pour un montant `StatAmount`**
        (mono-valeur, AUCUNE variance — confirmé live, splash Psyker = base exact) ; `None` (défaut)
        = la variance d'arme LUE dans `BattleConfiguration.Damage.DamageSpreadPercentage`
        (#449-r2-r4 ; le défaut portait `20` en dur). Aucun call-site ne prend ce défaut aujourd'hui
        — les deux régimes sont écrits explicitement. Renvoie le dict résultat (per_hit/total/...) ou None.

        `is_attack_damage_op` = LA FAMILLE DE FACTORY NATIVE du coup (cf. `_run_hits`) — threadé par la
        feuille DSL depuis son `native_factory`. Il ne pilote ICI qu'une seule chose : l'ORDRE bouclier ×
        limites (famille ABILITY = `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`,
        cap sur le RESTE post-bouclier ; famille ATTACK = cap sur le total, split en aval). Le resolve
        slot-8 qu'il gate aussi dans `_run_hits` n'existe pas sur ce vecteur (bornes pré-réduites,
        `post_roll=None`) → défaut `True` = comportement historique strictement inchangé pour les
        appelants qui ne le renseignent pas (attaque normale d'un summon, …).

        `is_outside_attack` (#925-r2, câblé par #944) = le LITTÉRAL natif du même nom, et il pilote
        ICI la même chose que sur son jumeau `execute_ability_attack` : l'émission d'
        `On(PreAttack = 5)`. Ce vecteur ne l'exprimait **pas du tout** — donc il n'émettait
        **JAMAIS** `On(5)`, alors que ses appelants portent des feuilles EMBALLÉES.

        ⚠ **LE RÉSIDU #925-r2 ÉTAIT ÉCRIT À L'ENVERS, et c'est la lecture du code qui le dit** : il
        annonçait « la voie `amount` émet `On(5)` INCONDITIONNELLEMENT » et prédisait donc **N**
        émissions pour `HazeOfCorruption`. Le compte réel était **0** — la fiche avait confondu
        `pre_attack_hit_triggers` (`On(PreAttackHit = 6)`, per-coup, bien présent lignes plus bas)
        avec `pre_attack_triggers` (`On(5)`, per-cible, absent). Le sens de la divergence est donc
        l'INVERSE de ce qui était écrit : il manquait des émissions, il n'y en avait pas en trop.

        LES QUATRE CALL-SITES du mode `amount`, chacun tranché sur SA factory native (jamais par
        famille ni par ressemblance) :

          * `PsykerExtraAttackAbility$$CreateBehaviour`      -> `DSLBehaviors$$AttackWithAttackDamage`
          * `CursedPlagueBellAttackAbility$$CreateBehaviour` -> `DSLBehaviors$$AttackWithAttackDamage`
          * `SkyStrikeAbility$$ExecuteBehaviour`             -> `DSLBehaviors$$AttackWithAttackDamage`
                ... les trois EMBALLÉES : la factory construit `AttackDamageBehaviour` **puis**
                `IdunBattle.Entities.Behaviours.AttackBehaviour$$.ctor` et RETOURNE ce dernier (lu
                verbatim sur la surcharge à 9 arguments, celle que les xrefs entrantes désignent)
                -> `AttackBehaviour$$Execute` pousse `StartAttack` -> `On(5)`. `True`.
          * `HazeOfCorruption_DamageTransferEffect$$CreateTargetTriggerBehaviour` -> **N** feuilles
                `DSLBehaviors$$AttackDamage` **NUES**, accumulées par `op_Addition` dans **UN SEUL**
                `DSLBehaviors$$Attack(bonded, Owner@0x148, beh)`. Le natif émet donc **1** `On(5)`,
                porté par l'englobant, et **0** par feuille -> `False` sur chaque feuille, et
                l'appelant émet l'unique `On(5)` lui-même (cf. `triggers/loki/haze_of_corruption.py`).

        Défaut `True` = la sémantique de la factory EMBALLANTE, identique au défaut du jumeau."""
        from ..damage import AttackDamageOperation  # lazy : rompt le cycle damage<->damage_ops
        if state.rng is None:
            return None
        # #449-r2-r4 : `None` = LU de la BC de cette bataille (foyer `damage_config`).
        spread_pct = resolve_spread_pct(spread_pct, state)
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
        # `On(PreAttack = 5)` -- EMIS ICI, **AVANT** la collecte des mods ATTAQUANT, exactement a la
        # place ou son jumeau `execute_ability_attack` l'emet, et pour la meme raison NATIVE :
        # `AttackBehaviour$$Execute` pousse `processor.StartAttack` (slot 58) ->
        # `IdunBattle.Operations.StartAttackOperation$$Execute` ->
        # `EvaluateAbilitiesImmediately(EventTriggerType.PreAttack = 5, ...)` AVANT d'executer le
        # behaviour enfant. La place PORTE (#512-r1) : `SuppressiveFire` ecoute ce vecteur et pose
        # `Pinned`, ce qui monte `TerrifyingCrescendo_ExtraDmg` d'un niveau -- un bonus de degat
        # ATTAQUANT, que le coup EN COURS doit voir.
        # ⚠ Ce vecteur ne l'emettait PAS DU TOUT (#925-r2, cf. la docstring) : ce n'est donc pas un
        # deplacement mais une emission NEUVE, et elle CONSOMME un tirage `state.rng` chez un
        # porteur de `LetTheGalaxyBurn` (son `Maybe(ConfigConst(0x2a))`). Cout pour toute unite qui
        # n'ecoute pas l'event 5 : NUL (zero mutation, zero tirage -- seuls
        # `SuppressiveFireAddEffectAbility` et `LetTheGalaxyBurnArmAbility` y sont abonnes).
        from ..triggers.dispatch.attack import pre_attack_triggers  # lazy : cycle damage<->triggers
        if is_outside_attack:
            pre_attack_triggers(state, attacker_id, target_id,
                                ranged=not bool(is_melee) if is_melee is not None else False,
                                profile=damage_profile, ability_type=ability_type)
        mods, active = attacker_modifiers(state, attacker_id, ahc.hp if ahc else None, target_id=target_id,
                                          is_ranged=_ranged,
                                          # `DamageProfileIs(...)` du collecteur attaquant unique
                                          # (`BaseEffect$$DamageBonusForAttack`) -- ce vecteur le
                                          # threadait deja au DEFENSEUR (ligne dessous) mais pas a
                                          # l'ATTAQUANT. Consommateur porte :
                                          # `PsychicStalk_FriendlyChaosExtraDamage` (#366-r1, 1435).
                                          damage_profile=damage_profile)
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
        block_sources = AttackDamageOperation._block_sources(
            tsc, _da, armor, damage_profile,
            defender_max_health=int(getattr(thc, "hp_max", 0) or 0))   # #1015-r1 GetStat(5, Maximum)
        # `On(PreAttackHit=6)` — meme vecteur per-coup natif, emis par `ExecuteHit` **APRES** le
        # `RollCritical` du coup (#522-r1). On mesure donc la crit chance AVANT l'event (celle du
        # coup 0), on emet, puis on la RELIT pour les coups 1+.
        crit_avant = AttackDamageOperation._crit_params(
            ctx, active, state, attacker_id, target_id,
            is_ranged=_ranged, is_normal_attack=False, hit_index=0)
        from ..triggers.dispatch.attack import pre_attack_hit_triggers  # lazy : cycle damage<->triggers
        pre_attack_hit_triggers(state, attacker_id, target_id,
                                ranged=not bool(is_melee) if is_melee is not None else False,
                                profile=damage_profile, is_first_hit=True, ability_type=ability_type)
        # Identites du coup -> `att_ctx` du canal CRIT, bati DANS `_crit_params` (foyer unique, mirror
        # de l'`AbilityEntities` de `GetCritDamageBonusFromEffects`).
        # `hit_index=1` : valeurs des coups 1+ (cf. `_roll_crit(idx)`) -- au-dela, c'est
        # `crit_chance_at` ci-dessous qui rend l'index exact (#889-r1, RESOLU).
        crit_chance, crit_damage, crit_enabled = AttackDamageOperation._crit_params(
            ctx, active, state, attacker_id, target_id,
            is_ranged=_ranged, is_normal_attack=False, hit_index=1)   # #112 : ce vecteur porte une SPECIALE
        crit_apres = (crit_chance, crit_damage, crit_enabled)

        def _crit_chance_at(_idx: int):
            """#889-r1 -- (chance, enabled) du canal CRIT A L'INDEX `_idx` (jumelle de
            `damage_ops/normal.py`, meme mirror de `RollCritical(..., hitIndex)`). La crit-DEGAT
            n'est pas relue : `GetCritDamageBonusFromEffects` ne recoit PAS de `hitIndex`."""
            _cc, _cd, _en = AttackDamageOperation._crit_params(
                ctx, active, state, attacker_id, target_id,
                is_ranged=_ranged, is_normal_attack=False, hit_index=int(_idx))
            return (_cc, _en)
        crit_chance, crit_damage, crit_enabled = crit_avant
        # #922 : `On(6)` tombe ENTRE `RollCritical` (slot 0xa) et `CalculateCriticalDamage`
        # (slot 0xb) dans `AttackDamageOperation$$ExecuteHit` -> la CHANCE du coup 0 est celle
        # d'AVANT, sa MAGNITUDE celle d'APRES. Meme correctif et meme mesure que `normal.py`.
        crit_damage = crit_apres[1]
        # #120 : réduction PLATE défenseur (Nightshroud, ungated -> splash/normal-like aussi) fusionnée pré-perçage.
        AttackDamageOperation._apply_defender_flat_reductions(mods, def_mods)

        def _reduced(eff_base: int, flat_add: int = 0) -> "HitDamage":
            # #75 (case-68 MAJ 13) : additif ForAddition ATTAQUANT = PRÉ-perçage en COMBAT.
            # `flat_add` (#45f) = EffectBonus.addition PER-BRANCHE (Ice crit-only) : POST-spread
            # PRE-perçage, sans polluer `mods` (applique aux deux branches).
            # R6 MATERIALISATION DES BORNES REDUITES = `Fix64$$Round(., AwayFromZero)`, PAS la
            # troncature -- MEME etage, MEME fonction native que l'attaque NORMALE (#131) et que
            # l'ability bounds-mode famille ATTACK (campagne HeavyGravCannon). Ce vecteur porte le
            # mode `amount` de la feuille `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`
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
            # UN `Round` PAR FACE (#437-r1) : MEME `ExecuteHit` natif que le vecteur d'arme, donc
            # MEMES deux etages `CalculateBaseDamageWithModifiers`. Depuis #437-r1-r1-r1 la
            # separation est INCONDITIONNELLE dans `apply_pierce_and_modifiers` (plus de drapeau).
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
        # #1013 : SECONDE branche d'`IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage`
        # (`HasTriggeredAbility(1494 ParagonSpear)`), gatee PAR COUP sur `isCritical` -> elle ne
        # peut pas degenerer les bornes en amont ; on la transmet a `_run_hits`. Le predicat lit
        # le KIT DECLENCHE de l'ATTAQUANT, pas l'ability qui frappe : TOUT coup critique du
        # porteur de la lance est maxe, son attaque normale comprise.
        _max_out_crit = AttackDamageOperation._max_out_on_crit(state, attacker_id)
        hits = max(1, int(hits))
        shc, shield_total = AttackDamageOperation._target_shield(tgt)      # bouclier shield-first
        # #366-r1 : intercepteur per-coup (`ExecuteHit` etape 5 = flag `discard` ; `On(0x3c = UnitBlocked)` +
        # `RegisterBlocks`). Cf. `triggers/loki/harlequins_panoply.py`.
        from ..triggers.loki.harlequins_panoply import make_hit_interceptor   # lazy (cycle)
        # #1020-r4 : chokepoint `On(0x39 = EventTriggerType.PreDamageTaken)` joue DANS la boucle
        # (cf. `damage_hits._run_hits`, bloc `POSITION DU TIRAGE`). `is_first_hit` porte ici le
        # meme etat que le repli implicite d'`_apply_damage_pipeline` : cette voie ne threade pas
        # d'`is_first_damaging_hit` propre (case-221 : N feuilles peuvent se partager la serie).
        _first_damaging = bool(is_first_hit)
        # #1020-r3 x #1020-r4 : `source_ability` resolu ICI, avant la boucle, et donne au sink ET
        # au chokepoint -- l'emission ayant migre dans la boucle, le canal `AbilityEntities+0x98`
        # doit l'y suivre.
        _src_ability = AttackDamageOperation._damage_source_ability(ability_type, None)
        _pdt_sink = AttackDamageOperation.make_pre_damage_taken_sink(
            state, attacker_id, target_id, thc, damage_profile,
            is_first_damaging_hit=_first_damaging, source_ability=_src_ability)
        r = AttackDamageOperation._run_hits(state.rng, hit_nc, hit_cr, crit_chance,
                                            crit_enabled, hits, block_sources,
                                            # #522-r1 : crit chance RELUE apres `On(PreAttackHit)`.
                                            max_out_on_crit=_max_out_crit,
                                            crit_chance_after=crit_apres[0],
                                            crit_enabled_after=crit_apres[2],
                                            # #889-r1 : axe INDEX (cf. `_roll_crit`).
                                            crit_chance_at=_crit_chance_at,
                                            shield=shield_total,   # post_roll=None (reduce-then-roll)
                                            hit_interceptor=make_hit_interceptor(
                                                state, attacker_id, target_id),
                                            capped_reductions=def_mods.capped_reductions,
                                            # #67 : etage limites — mode 2 = ability/splash
                                            # (`IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`)
                                            limits=AttackDamageOperation._target_limits(
                                                tgt, thc, damage_profile, is_special=2),
                                            limits_hp=int(thc.hp or 0),
                                            # #462-r4e-o : PV COURANTS + plancher -> `per_hit` = le tag
                                            # `Amount` de l'event (retraits REELS), pas le demande.
                                            hp_current=(None if thc.hp is None else int(thc.hp)),
                                            hp_floor=thc.minimal_health,
                                            # #462-r4e-o-r1 : SITE (A) — `HasFlag(target, 8)` relu
                                            # PAR COUP + son gate `CanBeOverkilled`.
                                            overkilled0=unit_is_overkilled(tgt),
                                            can_be_overkilled=can_be_overkilled(tgt),
                                            over_reduce0=int(thc.over_reduce or 0),
                                            # #195 : `HasFlag(defender, 0x13)` — le 5e argument
                                            # `isPreventOverkill` que `ApplyTraitDamageLimitsToDamage`
                                            # lit lui-meme sur son parametre `defender`.
                                            prevent_overkill=unit_prevents_overkill(state, target_id),
                                            # famille de factory native : pilote l'ordre bouclier x limites
                                            is_attack_damage_op=is_attack_damage_op,
                                            pending_sink=_pdt_sink)     # #1020-r4
        # #1020-r1 : plus de `_deplete_shield` ICI. `ApplyDamageOperation$$ReduceShield` lit le
        # pending RELU (apres `On(0x39)`), donc la depletion vit dans le chokepoint, avec `Reduce`.
        AttackDamageOperation._apply_damage_pipeline(                   # chokepoint partage (#202)
            state, target_id, attacker_id, tgt, thc, r["total"], damage_profile,
            r["shield_dmg"], r["armor_dmg"],
            # #1020-r3 : le canal `AbilityEntities+0x98` (`DamageAppliedResult.source`), que le
            # vecteur `On(0x39 = PreDamageTaken)` publie et que lisent les `TriggeringAbilityIs`.
            # Meme foyer que les deux autres vecteurs : `_damage_source_ability` est le mirror de
            # `StaticBattleRules$$GetDamageSourceAbility`, appele PAR COUP par les `ExecuteHit`
            # natifs -- donc par CE vecteur aussi.
            source_ability=_src_ability,   # #1020-r4 : la MEME que celle donnee au sink
            last_hit=(r["per_hit"][-1] if r.get("per_hit") else None),
            # #R33 : decomposition per-coup (crit / denied) pour `didOverkill`.
            hits_result=r,
            # `On(0x10)` : cet appel EST la serie de coups sur CETTE cible -> il contient le coup
            # d'index 0 (`IsFirstHitInSeries` VRAI, mirror `AbilityEntities+0x110`).
            # case-221 : SAUF quand l'appelant sait que N feuilles `AttackDamage` d'un MEME
            # `IdunBattle.Entities.Behaviours.AttackBehaviour` se partagent la serie (le natif y
            # incremente le hitIndex d'une feuille a l'autre) -- il passe alors `is_first_hit=False`
            # pour toutes sauf la premiere. Defaut `True` = comportement inchange pour tout appelant
            # dont l'appel EST la serie entiere.
            is_first_hit=bool(is_first_hit),
            # #1020-r4 : MEME etat que celui donne au `pending_sink` ci-dessus (cf. `normal.py`).
            is_first_damaging_hit=_first_damaging,
            pre_damage_taken=AttackDamageOperation.pre_damage_taken_of(_pdt_sink))
        # VECTEUR AFTER-HIT (splash StatAmount) : idem execute_ability_attack — reset ActOfFaith au crit
        # (#138) + vecteur complet (#140). `ranged` = POSITION-based (mirror IsRangedAttack), calculé dedans.
        # `ability_type` = kind AbilityOrEffect du coup (smite Psyker 0x3f5 -> branche 2 AddIce #35).
        # lazy + forme MODULE : `finish_attack_triggers` est SUBSTITUE par `probe_437*` -- une
        # liaison `from ... import` (forme A) desarmerait ces mesures en SILENCE.
        from ..triggers.dispatch import attack as attack_dispatch
        # #512-r7 -- LA FACADE AFTER-HIT N'EMET PLUS QUE LES VECTEURS DE L'OPERATION
        # (`On(0x3c = UnitBlocked)`, `On(8 = AttackHit)`), qui sortent d'`IdunBattle.Operations.
        # ADamageOperation$$EvaluateAfterHitTriggers`, appelee PAR COUP depuis `ExecuteHit`. La
        # CLOTURE (`On(9)`) vient du slot 59 que pousse le NOEUD, donc APRES -- elle est emise juste
        # en dessous.
        after_hit = attack_dispatch.after_hit_ability_attack(
            state, attacker_id, target_id, r["did_crit"],
            profile=damage_profile, did_block=r["did_block"])
        # `On(Attack = 9)` — cloture, `IdunBattle.Operations.FinishAttackOperation$$Execute`.
        # #512-r4 (gate INCHANGE, seule sa PLACE bouge) : MEME gate que l'`On(PreAttack = 5)` de
        # cette facade (#925-r2) -- une feuille NUE ne pousse ni `StartAttack` ni `FinishAttack`,
        # donc ni `On(5)` ni `On(9)`. Porte ici pour les N feuilles de transfert
        # d'`HazeOfCorruption`, qui vivent sous UN SEUL `Attack(bonded, Owner@0x148, beh)`.
        # #432 : `health_damage` = `HealthDamageFromEvent()` (part SANTE seule) ; `profiles` = le SET
        # des profils de l'attaque (ici le seul profil d'arme -- cette voie n'a pas de groupe #179).
        # ⚠ NON COUVERT, ET C'EST UN ECART CONNU DE CE VECTEUR (residu #512-r8) : cette facade
        # n'emet AUCUN `On(0x42 = FinalDamage)`, alors que `RegisterFinalDamage` est appelee par les
        # DEUX `Execute` natives. Le rang relatif `8` -> `9` repare ici est donc juste ; ce qui
        # manque est un evenement ENTIER, pas son ordre.
        if is_outside_attack:
            from ..triggers.base import _is_ranged_position
            after_hit = after_hit + attack_dispatch.finish_attack_triggers(
                state, attacker_id, target_id,
                ranged=_is_ranged_position(state, attacker_id, target_id),
                profile=damage_profile,
                is_crit=bool(r["did_crit"]), profiles={damage_profile} - {None},
                health_damage=int(r["total"] or 0), was_block=bool(r["did_block"]),
                # `ability_type` = kind AbilityOrEffect du coup (smite Psyker 0x3f5 -> branche 2
                # LordOfTempests AddIce #35).
                ability_type=ability_type,
                # `!IsNormalAttack(CurrentAbility@<DSLSelectors+0x88>)` : ce vecteur n'est jamais
                # l'attaque normale (`is_normal_attack=False` est deja ce que passent ses appels a
                # `defender_modifiers` / `_crit_params`).
                is_normal_attack=False,
                # `AttackUsedAttackDamage` (`AbilityEntities+0xf9`) = `currentAttack@+0x2c` : pose
                # par la seule `AttackDamageOperation$$Execute` -> la famille de factory, comme
                # dans `damage_ops/ability.py`.
                attack_used_attack_damage=bool(is_attack_damage_op))
        return {"hits": hits, "total": r["total"], "base": base, "pierce": profile_pierce,
                "armor": armor, "after_hit": after_hit,
                "clean_min": hit_nc.min * hits, "clean_max": hit_nc.max * hits,
                "did_crit": r["did_crit"], "did_block": r["did_block"], "did_evade": r["did_evade"],
                "crits": r["crits"], "rolls": r["rolls"], "per_hit": r["per_hit"]}

    @staticmethod
    def execute_direct(state: State, source_id: int, target_id: int, base: int,
                       profile_pierce: int,
                       damage_profile: Optional[str] = None) -> Optional[dict]:
        """Dégât DIRECT d'un nœud `Direct(...)` (mirror `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage`
        + `AttackDamageBehaviour` sur nœud `Direct` — factory DISTINCTE de `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage). La `base` (déjà calculée par le dégât-node, ex. `PercentageOf(StatAmount(Health,
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
