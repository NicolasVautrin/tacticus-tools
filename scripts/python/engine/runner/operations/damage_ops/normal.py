"""Vecteur d'ATTAQUE NORMALE (`_DamageOpsMixin.execute`), extrait d'`operations/damage_ops.py`
(scission du module >1000 lignes, tache #169 -- deplacement VERBATIM, zero changement de
comportement).

Mirror `IdunBattle.Operations.AttackDamageOperation$$Execute` -> `ExecuteHits` -> `ExecuteHit`.

PATCH-POINT (tests/probes) : `execute` resout `apply_all_modifiers` dans les globals de CE
module -- un patch pose sur le `__init__` du package serait un NO-OP SILENCIEUX. Patcher
`damage_ops.normal.apply_all_modifiers`."""
from __future__ import annotations

from ....services.damage_prediction import get_base_damage_fix64, apply_pierce_and_modifiers
from ....services.damage_modifiers import apply_all_modifiers
from ....services.battle_query import are_tiles_adjacent
from ....services.attack_hits_formula import attack_hits_with_modifiers
from ....entities.stats import StatType
from ...state import State
from ...components import (StatsComponent, HealthComponent, PositionComponent,
                           persistent_data_keys)
from ...damage_model import (select_weapon, select_weapon_pierce, attacker_modifiers,
                             defender_modifiers, build_hits_board, apply_elevation_bonus,
                             apply_trench_reduction, ice_crit_damage_addition,
                             target_trait_names, getstuckin_combat_chance, defender_fixed_armor,
                             tile_status_effects_by_pos)
from ....entities.effects import hits_bonus_from_effects
from ....entities.effects.loki import LIGHT_COVER_TILE_ID
from ....entities.traits import target_hit_multiplier
from ..additional_hits import collect_additional_hit_groups, execute_additional_hits
from ..damage_hits import HitDamage
from ._channel import _normal_attack_kind


class _Normal:
    """Vecteur d'attaque NORMALE. Sans etat (staticmethod) ; agrege par `_DamageOpsMixin`."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, attacker_id: int, target_id: int,
                spread_pct: int = 20, is_overwatch: bool = False,
                triggering_ability: Optional[int] = None) -> Optional[dict]:
        """Résolution d'une attaque normale (mirror Execute→ExecuteHits→ExecuteHit) depuis
        l'ECS : tire CHAQUE coup sur la plage BRUTE (`stat Attack` ± spread) avec le MT du
        runner (`state.rng`), réduit (perçage de l'arme par distance + armure cible, mods
        d'effet), puis MUTE les PV de la cible. Renvoie `{hits, total, base, pierce, armor,
        clean_min, clean_max, effects}` ou None si stats/positions manquantes.

        PALIER ACTUEL : crit/block NON tirés (paliers 2). Pour un coup MONO propre (no-crit/
        no-block), `total` == dégât réel live (le tirage de dégât est le 1er conso RNG).
        Multi-coups : tire `hits` fois (valable seulement si le live ne tire pas crit/block
        entre les coups — sinon désync RNG ; couvert au palier crit/block).

        `triggering_ability` (#114) = l'`AbilityOrEffect` DECLENCHEUSE quand cette attaque normale est
        jouee POUR LE COMPTE d'un effet/trigger (`UseActiveAbility(NormalAttack)`). Elle n'a qu'un
        consommateur : `StaticBattleRules$$GetDamageSourceAbility(currentAbility, triggeringAbility)`,
        qui l'utilise comme `AbilityOrEffect` de la `DamageSource` du coup -- et donc comme raison de
        mort gravee sur la victime (`KillUnitOperation$$RecordDeathReason`, lue par
        `HasDeathReasonTrigger`). Defaut None = attaque normale ordinaire (la source reste l'attaque).

        `is_overwatch` (case-117 phase 2) = ce coup est l'auto-attaque d'un OVERWATCH
        (`Overwatch_AutoAttackEffect.GetAttackBehaviour` = `UseActiveAbility(NormalAttack)` : côté natif
        c'est bien une attaque NORMALE, mais le prédicat `IsOverwatchAttack` la distingue). Threadé ici
        parce que `Hailstrike_ExtraPierceEffect.CreatePiercingBonusForAttack` gate sur la DISJONCTION
        `IsRangedAttack | IsOverwatchAttack` : sans ce flag, un overwatch de MÊLÉE (le mover arrive
        adjacent) perdrait le bonus de perçage que le natif accorde. Défaut False = tous les autres
        appelants (attaque normale ordinaire)."""
        from ..damage import AttackDamageOperation  # lazy : rompt le cycle damage<->damage_ops
        if state.rng is None:
            raise ValueError("state.rng non calé (seed depuis dumpRng avant un replay-diff)")
        att = state.get_entity(attacker_id)
        tgt = state.get_entity(target_id)
        sc = att.get_component(StatsComponent) if att is not None else None
        thc = tgt.get_component(HealthComponent) if tgt is not None else None
        if sc is None or thc is None:
            return None
        ctx = sc.ctx
        ap = att.get_component(PositionComponent)
        tp = tgt.get_component(PositionComponent)
        # DISTANCE pour la sélection d'arme (mêlée si adjacent, sinon tir). Adjacence HEX via le service
        # PARTAGÉ `BattleQuery.are_tiles_adjacent` (MÊME que la prédiction) : `state.board` → voisins
        # natifs (evenq), fallback géométrie evenq — PAS chebyshev (cheby==1 peut être hex-dist-2 → fausse
        # sélection mêlée d'un tir, ex. overwatch ranged à dist 2).
        dist = None
        if ap is not None and tp is not None:
            adj = are_tiles_adjacent((ap.col, ap.row), (tp.col, tp.row), state.board)
            dist = 1 if adj else 2
        pierce, _ranged, whits = select_weapon_pierce(ctx, dist)
        _w = select_weapon(ctx, dist)
        _profile = _w.get("DamageProfile") if _w else None     # profil du coup (pour vecteurs after-hit)
        # `BaseEffect$$PiercingBonusForAttack` sur la voie NORMALE (case-117 phase 2) : le natif somme
        # ces `EffectBonus` DANS `GetAttackPiercingDamageRatio` quel que soit le vecteur — l'attaque
        # normale n'y échappe pas. Le porteur du lot est `Hailstrike_ExtraPierce` (1509), dont le gate
        # est `OwnerIsCaster & (IsRangedAttack | IsOverwatchAttack)` : AUCUN `CurrentAbilityIs`, donc
        # l'attaque normale ranged de l'allié buffé EST la cible principale de ce bonus (i2 : « Ranged
        # and Overwatch attacks have +X% pierce ratio »). Calculé APRÈS la sélection d'arme (la nature
        # `_ranged` du coup alimente le gate) ; second appel PUR au service (aucun RNG, aucun effet de
        # bord) pour que le bonus entre dans le clamp UNIQUE du natif, pas dans un second clamp.
        # `ability_type=None` : une attaque normale n'a pas d'AbilityOrEffect d'ability -> les effets
        # gatés `CurrentAbilityIs` (GravitonRifle) se taisent, comme le natif.
        from ...abilities.base import ability_pierce_effect_bonus   # lazy : cycle damage<->abilities
        _pbonus = ability_pierce_effect_bonus(state, attacker_id, target_id, None,
                                              is_ranged=bool(_ranged), is_overwatch=bool(is_overwatch))
        if _pbonus:
            pierce, _ranged, whits = select_weapon_pierce(ctx, dist, effect_bonus=_pbonus)
        # `On(PreUnitAbility=0x2b)` (#100) — `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`
        # l'emet TOUT EN HAUT (`FUN_180026490(0x4d, .., 0x2b)`), AVANT l'execution de l'ability : l'attaque
        # normale EST une active ability (`NormalAttackType`, cf. #139 plus bas). Emis ICI, juste apres la
        # selection d'arme (lecture pure : le natif connait deja la nature du coup) et AVANT tout calcul
        # de coups / modificateurs / **block** — c'est indispensable : `AnvilShieldFrozenAttackerAdvantageAbility`
        # pose un stat-mod BLOCK_CHANCE que `_block_sources` doit voir sur CETTE attaque, sinon le port
        # serait un no-op silencieux. #120 : ce site n'est PLUS le seul emetteur de `0x2b` — la voie
        # d'ABILITY (`AbilityHandler.visit_ActiveAbilityMessage`) l'emet aussi, comme le natif, qui n'a
        # qu'UN site (`ExecuteInternal`) commun aux deux. Le gate natif `IsNormalAttack` n'est donc plus
        # satisfait structurellement : il est PORTE (`abilities/attack_type.is_normal_attack`), et c'est
        # `ability_type = 0x3f5 = 1013` (le marqueur « kind attaque-normale » du `DirectAbilitySelector`
        # natif, cf. `attack_type.NORMAL_ATTACK_KIND`) qui le satisfait sur CETTE voie.
        from ..triggers.dispatch import pre_unit_ability_triggers   # lazy : cycle damage<->triggers
        # #120bis SNAPSHOT DE TUILE de la cible (AVANT l'emission) — `IdunBattle.Operations.
        # ActiveAbilityOperation$$GetAbilityEntities` fige `AbilityEntities@+0x38 =
        # EntityExtensions.GetTiles(finalTarget)` en amont du `0x2b` ; la re-resolution qui SUIT
        # l'emission confronte ce fige a l'occupation reelle.
        from ..active_ability import (execute_for_replaced_target, get_tiles,
                                     resolve_replaced_target)
        _target_tiles = get_tiles(state, target_id)
        pre_unit_ability_triggers(state, attacker_id, target_id, ranged=bool(_ranged),
                                  profile=_profile, ability_type=1013)
        # #133 GATE ACTEUR-MORT **POST-`On(0x2b)`** — mirror du test qui suit IMMEDIATEMENT
        # l'evenement dans `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` (lu
        # verbatim au decompile) :
        #     FUN_180026490(0x4d, .., 0x2b);
        #     if (options@0x4a == 0 && IsUnit(caster) && IsDead(caster, state)) return 0;
        # Le natif teste DEUX FOIS la mort du caster : en TETE d'operation (#70, deja porte au niveau
        # MESSAGE dans `DamageHandler.visit_AttackUnitMessage`) et ICI, parce que la cascade de
        # triggers reveillee par `0x2b` peut l'avoir TUE entre-temps. C'est exactement ce que fait la
        # riposte `MartialSuperiority` (« before the enemy attack executes ») : si elle tue
        # l'attaquant, l'attaque entrante est ANNULEE (0 tirage RNG, 0 degat, aucun after-hit).
        # `options@0x4a` = le flag « caster mort autorise » des `AbilityOptions` : aucune voie du port
        # ne le pose -> gate toujours actif. Inerte pour toute cascade qui ne tue pas l'attaquant.
        from ...components import unit_is_dead                  # lazy : coherent avec les autres gates
        if unit_is_dead(state.get_entity(attacker_id)):
            return None
        # #120bis RE-RESOLUTION DE CIBLE — mirror du bloc qui suit IMMEDIATEMENT le `0x2b` dans
        # `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`. L'attaque normale EST une
        # active ability (`ALoki_NormalAttackAbility`) : elle traverse le MEME etage que le cast, et
        # c'est LUI qui envoie les coups sur Kell apres le switch de SwornProtector (le switch, seul,
        # ne fait que deplacer Creed). La re-entree = un `AttackDamageOperation.execute` NEUF sur la
        # nouvelle cible (mirror `ActiveAbilityOperation$$Execute`), donc selection d'arme, distance,
        # `On(0x2b)`, coups et modificateurs sont TOUS recalcules contre elle. Cet appel-ci `return`e
        # aussitot, comme le natif. Cable sur les DEUX voies a la fois (cf. `active_ability.py`).
        _replaced, _new_target = resolve_replaced_target(state, target_id, _target_tiles)
        if _replaced:
            return execute_for_replaced_target(
                state, attacker_id, _new_target,
                lambda t: AttackDamageOperation.execute(state, attacker_id, t, spread_pct,
                                                        is_overwatch=is_overwatch))
        ahc = att.get_component(HealthComponent)
        mods, active = attacker_modifiers(state, attacker_id, ahc.hp if ahc else None, is_ranged=_ranged,
                                          target_traits=target_trait_names(state, target_id),
                                          target_id=target_id, damage_profile=_profile,
                                          # LionHelm_ExtraDmg : gate `IsOverwatchAttack` de l'aura
                                          # ALLIEE (meme flag que le bonus de percage Hailstrike).
                                          is_overwatch=bool(is_overwatch))
        # #58 : feuille positionnelle ELEVATION (+surplomb) ajoutee au `mods` de l'attaquant, comme la
        # prediction (service PARTAGE `calculate_elevation_bonus_modifier` de DamageCalculations ; positions
        # REELLES depuis l'ECS/board).
        apply_elevation_bonus(state, mods, attacker_id, target_id)
        # #181 : reduction TRENCH (feuille positionnelle soeur de l'elevation dans le meme builder natif) —
        # -50% si la cible porte l'effet Trench + conditions attaquant-tuile (calculate_trench_reduction).
        apply_trench_reduction(state, mods, attacker_id, target_id, _profile)
        # Nb de coups : cette execution EST la facade `IdunBattle.Operations.AttackDamageOperation$$GetAttackHits` — elle
        # rassemble les entrees depuis l'ECS puis appelle la FORMULE PARTAGEE `attack_hits_with_modifiers`
        # (`IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate`, MEME formule que la facade prediction) :
        # base weapon+ExtraHits+effets, +malus defenseur (LightCover/Parry) + auras (BigTarget). #62a : le
        # combat ne sommait que weapon+ExtraHits+effets -> divergeait sur (3). BITE 2 (verdict validateur) :
        # GetStuckIn est un behaviour d'exec chance-gate (`AddBonusHitsToCurrentHitGroupBehaviour IdunBattle.Entities.Behaviours.AddBonusHitsToCurrentHitGroupBehaviour$$Execute`,
        # roll `Maybe(GetBonusHitChance)` 30%/100%) -> `include_bonus_hit_behaviours=False` DANS la formule (le
        # coup bonus n'est PAS un coup de la formule : folder en dur sur-comptait, orksNob 1v1 chance=30 ->
        # natif 3 coups, folder 4). Le coup bonus est ajoute PLUS BAS a l'EXECUTION (#62c, commit 3997793) :
        # `_gsi = getstuckin_combat_chance(...)` -> `_run_hits(bonus_hit_chance=_gsi)`. Bit-exact live case-67.
        # `On(PreAttack=5)` (#84) — vecteur natif emis AVANT `GetAttackHits`. Le SEUL consommateur porte
        # est `LetTheGalaxyBurnArmAbility` (arme le flag persistant lu 3 lignes plus bas par le canal de
        # coups de CETTE attaque) ; aucun autre trigger n'ecoute l'event 5 -> no-op (et zero conso RNG)
        # pour toute unite non-porteuse. Emis APRES la selection d'arme (le natif connait deja la nature
        # du coup) et AVANT la formule, comme le natif.
        if tp is not None:
            from ..triggers.dispatch import pre_attack_triggers   # lazy : cycle damage<->triggers
            pre_attack_triggers(state, attacker_id, target_id, ranged=bool(_ranged), profile=_profile)
        if ap is not None and tp is not None:
            _board, _auras, _tgt_eff = build_hits_board(
                state, attacker_id, target_id, (ap.col, ap.row), (tp.col, tp.row), is_melee=not _ranged)
            # A3 (#113) : gate compute-time LightCover -- `AreEqual(coverPatch, target)` IdunBattle.Entities.Effects.Loki.LightCoverEffect$$CreateEffectHitsBonusForAttack = la CIBLE
            # est-elle sur SA tuile de cover (DryBush) ? state.board porte le terrain (tileDefId, capteur
            # boardGraph #124). Terrain INCONNU (board None / build sans tileDefId) -> None = applique-sur-
            # presence (retro-compat). Empeche un LightCover PERIME (cible ayant quitte la tuile, effet non
            # encore retire faute de B1) de sur-reduire les coups en runner-sim multi-step.
            _t_terrain = state.board.terrain_at(tp.col, tp.row) if state.board is not None else None
            _on_cover = (_t_terrain == LIGHT_COVER_TILE_ID) if _t_terrain is not None else None
            hits = attack_hits_with_modifiers(
                weapon_hits=whits, extra_hits=ctx.stat(StatType.EXTRA_HITS),
                extra_hits_melee=ctx.extra_hits_melee,
                attacker_effects=active, trait_objects=ctx.trait_objects(),
                target_effects=_tgt_eff, aura_sources=_auras, board=_board,
                is_melee=not _ranged, damage_profile=_profile,
                include_bonus_hit_behaviours=False,  # combat: GetStuckIn NON compte dans la formule -- ajoute a l'exec (_run_hits, #62c)
                defender_on_cover=_on_cover,
                # #84 : contexte CIBLE du canal (1) -- `HasTileStatusEffect` (status-effects DYNAMIQUES
                # de la tuile de la cible) + `IsPersistentData` (flag arme juste au-dessus par le vecteur
                # PreAttack). MEME couple d'entrees que la facade PREDICTION.
                tile_effects_by_pos=tile_status_effects_by_pos(state, [(tp.col, tp.row)]),
                attacker_persistent_data=persistent_data_keys(att))
        else:                                     # positions manquantes -> base seule (pas de GetStuckIn/aura)
            hits = max(1, whits + ctx.stat(StatType.EXTRA_HITS) + hits_bonus_from_effects(active))
        tsc = tgt.get_component(StatsComponent)
        # armure défenseur = FOYER PARTAGÉ `defender_fixed_armor` : GetStat(16) [effet-inclusif : les stat-mods
        # +armor d'effet, dont le stat-mod EAGER self de ProtectorImperative, sont cuits dans GetStat] + AURA
        # +FixedArmor d'un ALLIÉ Mechanical ADJACENT porteur de ProtectorImperative (self auto-exclu ⇒ pas de
        # double-compte), ré-évaluée par adjacence. Court-circuit non-Mechanical ⇒ base seule (cas courant).
        armor = defender_fixed_armor(state, target_id)
        # DÉFENSEUR : réductions de dégât reçu portées par les effets de la CIBLE (symétrique attaquant ;
        # CalculateDefenderModifiersForPrediction). Vide → no-op (apply_all_modifiers identité). Couvre la
        # famille ADamageDefenseModifierAbilityEffect ; STAT/Parry/triggers = axes séparés (cf. §1.8).
        # #59 : threade is_melee (= coup mêlée = arme non-rangée) + profil de dégât → malus gatés corrects
        # (Terrifying_ExtraDefense gate IsMeleeAttack ; TerminatorArmour exclut Psychic/DirectDamage). Mirror
        # de la prédiction. #59 suite : les chemins ABILITY (execute_ability_attack/execute_normal_like)
        # câblent DÉSORMAIS ces gates aussi (params damage_profile/is_melee threadés par tous leurs callers).
        def_mods, _def_active = defender_modifiers(state, target_id, thc.hp,
                                                   is_melee=not _ranged, damage_profile=_profile,
                                                   attacker_id=attacker_id, is_normal_attack=True)  # #112
        # BLOCK (cible) = base (scalaire GetStat 7/8) + sources d'effet (ex. BeastSlayer) — helper PARTAGE
        # par les 3 vecteurs (normale/ability/splash), mirror du `GetMultiValueStat(7)`/CalculateBlockChances
        # IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances unique du natif. Besoin des effets actifs de la cible -> apres defender_modifiers.
        # #65 : `_profile` gate le trait NoBlocking (profil Psychic bypasse le block, mirror ExecuteHit).
        block_sources = AttackDamageOperation._block_sources(tsc, _def_active, armor, _profile)
        # ORDRE RÉEL (confirmé live 18/18 coups, 3 seeds, necroDestroyer 6h) : le HitDamage natif
        # porte la plage RÉDUITE — la réduction (perçage/armure/modifiers attaquant+défenseur) est
        # appliquée aux BORNES base±spread D'ABORD, puis le tirage `GetDamage` se fait DANS cette plage
        # réduite (next_internal(min_réduit, max_réduit+1)). PAS spread-brut-puis-réduit (qui donne la
        # bonne PLAGE totale mais de mauvaises valeurs par coup — le modulo dépend de la largeur).
        # CRIT — modèle CONFIRMÉ bit-exact (genrand brut live, necroDestroyer CC=100/CD=500 → 12 tirages
        # /6 coups : 1 crit-roll + 1 spread PAR COUP). Le crit du COMBAT n'est PAS l'`ApplyCritDamage`
        # post-réduction de la PRÉDICTION : il s'ajoute à la BASE D'ATTAQUE AVANT spread/perçage
        # (chemin `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64 param_4=isCrit/param_5=critBonus = +FromInt(critDamage)).
        # ⇒ `eff_attack = attack + critDamage` PAR COUP qui crite, puis MÊME pipeline (spread→perçage→mods).
        # Preuve : non-crit spread(906)=181→{725,1087}×0.6=[435,652] ; crit eff=1406, spread=281→
        # {1125,1687}×0.6=[675,1012] (=W338 du solveur, ×1.552=(906+500)/906) ; next_internal(675,1013)
        # aux tirages IMPAIRS = live [932,882,967,867,961,955] À L'UNITÉ.
        # ORDRE PAR COUP (confirmé par positions genrand) : RollCritical D'ABORD (tirage pair), spread APRÈS
        # (tirage impair). `roll_critical` ne tire QUE si cc≥1 — gate `cc<1 → false SANS tirage` de
        # `IdunBattle.Core.Services.DamagePrediction$$RollCritical` (l'UNIQUE chemin crit d'`ExecuteHit`, slot 0xa ;
        # `IdunBattle.Core.Services.DamageCalculations$$RollCritical` = le NextBool brut DERRIÈRE ce gate) — cc=0 ⇒ 0 tirage
        # ⇒ rétro-compat exacte du multi-coups non-crit validé (18/18 + probe_rngcrit_1202 branche A).
        # NB cas fable rngcrit-1202 : le « crit-roll fantôme » mesuré par #220/#205 sur les attaques
        # d'ABILITY multi-coups à cc=0 n'était PAS un crit-roll (réfuté décompile + live M1/M2) mais le
        # resolve slot-8 GASPILLÉ du vecteur ability — cf. `_one_hit`. Gate `could_crit` = cc>0 ET cd>0
        # (IdunBattle.Core.Services.DamageCalculations$$CouldCrit).
        # `On(PreAttackHit=6)` — vecteur PER-COUP natif emis TOUT EN HAUT d'`IdunBattle.Operations.
        # AttackDamageOperation$$ExecuteHit`, donc APRES `GetAttackHits` et AVANT le calcul du crit du
        # coup. Emis ICI a la MEME place : son seul consommateur porte (ThrillSeekers, branche
        # « cible a pleine vie ») pose un stat-mod CRIT_CHANCE que `_crit_params` (ligne suivante) DOIT
        # voir sur CETTE attaque -- le router apres serait un no-op silencieux. `is_first_hit=True` =
        # le coup 0 (le port n'a pas de boucle de coups au niveau trigger ; cf. l'en-tete du vecteur).
        from ..triggers.dispatch import pre_attack_hit_triggers   # lazy : cycle damage<->triggers
        pre_attack_hit_triggers(state, attacker_id, target_id, ranged=bool(_ranged),
                                profile=_profile, is_first_hit=True, ability_type=1013)
        # crit = GetStat(9/10) [DÉJÀ effet-inclusif : les effets StatModification sur la crit sont
        # cuits dans GetStat → dans le combatSnapshot → dans ctx] + couche calc-time SÉPARÉE
        # GetCritChanceBonusFromEffects/GetCritDamageBonusFromEffects (PAS dans GetStat → sommée ici
        # depuis les effets ACTIFS de l'attaquant). Mirror exact de RollCritical/CalculateCriticalDamage.
        crit_chance, crit_damage, crit_enabled = AttackDamageOperation._crit_params(ctx, active)
        # #120 : réduction PLATE défenseur (Nightshroud) fusionnée dans l'additif pré-perçage (mirror prédiction).
        AttackDamageOperation._apply_defender_flat_reductions(mods, def_mods)

        def _reduced_bounds(eff_attack: int, hit_mult: int = 1, flat_add: int = 0) -> "HitDamage":
            # #75 (case-68 MAJ 13) : additif ForAddition ATTAQUANT = PRÉ-perçage en COMBAT
            # (attacker_additive_pre=True : bornes (base±spread)+additif → GDWP → %-list ; le natif
            # passe à IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage un dégât DÉJÀ additivé, CBDWAM IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers ne
            # consomme pas Addition@+0x10). Bit-exact 3/3 orksNob SmashaEad (599, pierce 50, armure 2208).
            # `flat_add` (#45f) = EffectBonus.addition PER-BRANCHE (Ice crit-only) : POST-spread
            # PRE-perçage (même position que mods.additive #75), sans poluer `mods` (qui s'applique
            # aux DEUX branches nc/cr).
            # #131 MATERIALISATION DES BORNES REDUITES = `Fix64$$Round(., AwayFromZero)`, PAS la
            # troncature. Ces cellules ne sont PAS produites par un calcul propre au combat : le
            # per-coup natif `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` appelle le
            # slot 4 `IdunBattle.Core.Services.DamagePrediction$$PredictAttack` (cache ->
            # `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw`, SEUL appelant de CBDWAM
            # avec `CalculateAbilityDamage`) puis resout la cellule par le slot 8
            # `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` = Next(min,max+1).
            # C'est donc LA MEME fonction native que la PREDICTION -> meme materialisation. Le dernier
            # etage de `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`
            # est le MULTIPLICATEUR (slot 0x10 ->
            # `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`) :
            #     v = Mul(dmg, multiplier) ; v<=0 -> 0 ; 0<v<1 -> 1 ; sinon Round(v, AwayFromZero)
            # traverse des qu'un `Nullable<DamageModifiers>` HasValue (attaquant OU defenseur).
            # MESURE LIVE (probe_131, per-COUP, tirage brut IDENTIQUE entre les 2 modeles) :
            #   - Azrael Plasma p=80 / armure 3513 : cellules floor [1800,2700] vs round [1800,2701]
            #     -> live 6/6 = round, 1/6 = floor (le datapoint case-117 5ter live 1921 / offline 2301
            #        est exactement ce +1 de borne haute : 2700.8 tronque a 2700) ;
            #   - Azrael Power p=40 / armure 3513, 3 coups, SANS buff : [899,1350] vs [900,1350]
            #     -> live 17/18 coups = round, 0/18 = floor (le 18e = coup letal ecrete aux PV restants).
            # Le controle p=65 de case-117 etait bit-exact parce que ce regime n'est PAS discriminant
            # (2250x0.65 -> 1462.4999, 3376x0.65 -> 2194.4 : floor == round).
            # EXTRA_MAX_DAMAGE (stat 0x19=25) — 5e argument natif de
            # `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64` (`max += Fix64(param_5)` ;
            # en mode max-out `min` prend AUSSI cette valeur). LU dans son UNIQUE appelant
            # `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` :
            #     if (!IsMeleeAttack(...)) extra = GetStat(attaquant, 0x19, 0) ; else extra = 0 ;
            # => le bonus ne mord QUE sur les attaques NON-MELEE (i2 RealityUnbound : « +181 Maximum
            # Damage with his normal RANGED attacks »). Le port suit sa convention etablie
            # `is_melee == not _ranged` (celle de `defender_modifiers` ci-dessus). Le parametre
            # `extra_max` existait deja cote prediction mais AUCUN appelant ne le renseignait : le stat
            # etait un no-op silencieux tant qu'aucun porteur ne le posait. Poseur : le volet
            # ExtraMaxDamage de `RealityUnbound` (effet 1207, cf. triggers/loki/reality_unbound.py).
            # ⚠ RECTIFICATION d'attribution : le bloc de commentaire ci-dessus (modele de crit) prete a
            # `GetBaseDamageFix64` « param_4=isCrit / param_5=critBonus ». Lecture DIRECTE du decompile :
            # `param_4 = IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage(...)` et
            # `param_5 = GetStat(attaquant, 0x19)`. Le modele de crit du port (crit ajoute a la BASE,
            # valide bit-exact live) est INCHANGE — seule la citation du symbole etait fausse.
            _extra_max = int(ctx.stat(StatType.EXTRA_MAX_DAMAGE) or 0) if _ranged else 0
            mm = get_base_damage_fix64(eff_attack, extra_max=_extra_max, spread_pct=spread_pct)
            lo = apply_all_modifiers(apply_pierce_and_modifiers(
                mm.min + flat_add, pierce, armor, mods, hit_mult=hit_mult, attacker_additive_pre=True),
                def_mods, round_materialize=True)
            hi = apply_all_modifiers(apply_pierce_and_modifiers(
                mm.max + flat_add, pierce, armor, mods, hit_mult=hit_mult, attacker_additive_pre=True),
                def_mods, round_materialize=True)
            return HitDamage(lo, hi)

        # MkXGravis (trait CIBLE 0x3f5=1013) : les dégâts entrants traversent l'armure 2× SAUF au crit
        # (i2 « Does not apply to Crits ») → hit_mult=2 sur la plage NON-crit, =1 (défaut) sur la plage
        # crit. Mirror `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor` (HasTrait(0x3f5) && !isCrit) dans
        # le chemin COMBAT `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` → `CalculateBaseDamageWithAllModifiers
        # IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` (décompile-confirmé, #180). No-op (=1) hors cible hit-twice.
        _tgt_hit_mult = target_hit_multiplier(tsc.ctx.trait_objects()) if tsc is not None else 1
        # #45f : bonus crit-sur-Ice (`IdunBattle.Entities.Effects.IceEffect$$CreateEffectDamageBonusForAttack`) — flat
        # PER-COUP-CRIT = PercentageOf(GetStat(10), IceCritDmgBonusPct) si cible sur tuile Ice active
        # et non-Immune. 0 hors gate / cd=0 (no-op rétro-compat, mesuré +175 probe_45f --case crit).
        _ice_add = ice_crit_damage_addition(state, attacker_id, target_id, ctx) if crit_enabled else 0
        hit_nc = _reduced_bounds(ctx.stat(StatType.ATTACK), hit_mult=_tgt_hit_mult)   # NON-crit → double-armure MkXGravis
        hit_cr = _reduced_bounds(ctx.stat(StatType.ATTACK) + crit_damage,
                                 flat_add=_ice_add) if crit_enabled else hit_nc  # crit: hit_mult=1 (exempt)
        # #202 WeaverOfFate : attaquant max-out (effet 1185) -> bornes degenerees a (max, max), mirror
        # HitDamage(max, null) de `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$GetDamage` (cf. _apply_max_out).
        hit_nc, hit_cr = AttackDamageOperation._apply_max_out(state, attacker_id, hit_nc, hit_cr)
        clean_min = hit_nc.min * hits          # référence affichée = plage non-crit (× hits)
        clean_max = hit_nc.max * hits
        # BOUCLIER cible : absorbe le coup réduit AVANT les PV (CalculateDamageOperation shield-first) ;
        # _run_hits déplète le bouclier entre coups (shield -= dmg.shield), total = part SANTÉ seule.
        shc, shield_total = AttackDamageOperation._target_shield(tgt)
        # #62c GetStuckIn (combat) : chance des coups bonus (behaviour Maybe chance-gate IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateBehaviour) — None si
        # l'attaquant ne porte pas GetStuckIn ou si la cible est a >2 hex. cf. getstuckin_combat_chance + _run_hits.
        _gsi = getstuckin_combat_chance(state, attacker_id, target_id,
                                        (ap.col, ap.row) if ap is not None else None,
                                        (tp.col, tp.row) if tp is not None else None, state.board)
        r = AttackDamageOperation._run_hits(state.rng, hit_nc, hit_cr, crit_chance,
                                            crit_enabled, hits, block_sources, shield=shield_total,
                                            bonus_hit_chance=_gsi,
                                            capped_reductions=def_mods.capped_reductions,
                                            # #67 : etage limites (member-cap/Resilient/bypass Blast) —
                                            # mode 1 = attaque (wrapper IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToAttackDamage/IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToAttackDamage)
                                            limits=AttackDamageOperation._target_limits(
                                                tgt, thc, _profile, is_special=1),
                                            limits_hp=int(thc.hp or 0))
        AttackDamageOperation._deplete_shield(shc, r)
        death = AttackDamageOperation._apply_damage_pipeline(           # chokepoint partage (#202)
            state, target_id, attacker_id, tgt, thc, r["total"], _profile,
            r["shield_dmg"], r["armor_dmg"],
            # `GetDamageSourceAbility(currentAbility = l'attaque normale, triggeringAbility)` : la voie
            # NORMALE porte le marqueur de kind 0x3f5 comme `currentAbility` (cf. `attack_type.py`).
            source_ability=AttackDamageOperation._damage_source_ability(
                _normal_attack_kind(), triggering_ability),
            last_hit=(r["per_hit"][-1] if r.get("per_hit") else None))
        # #202-B : coups additionnels HETEROGENES (canal #179, face COMBAT) — sous-operations APRES
        # les coups d'arme (mirror IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute), chacune son RegisterDamage au profil PROPRE.
        _ah = execute_additional_hits(
            state, attacker_id, target_id, tgt, thc,
            collect_additional_hit_groups(
                state, attacker_id, target_id, active, not _ranged, _def_active),
            mods, def_mods, armor, _tgt_hit_mult, block_sources, shc,
            spread_pct=spread_pct, extra_pierce=ctx.extra_pierce)
        if _ah is not None:
            death = death or _ah.get("death")
        # `On(AttackDamageAttack = 10)` — 2e event de cloture d'`IdunBattle.Operations.
        # FinishAttackOperation$$Execute`, gate `currentAttack@+0x2c` que CETTE operation vient de poser
        # (`AttackDamageOperation$$Execute` : `*(lVar6 + 0x2c) = 1`). Emis a la SORTIE de l'operation
        # parce que le vecteur de cloture du port (`after_hit_normal_attack`) vit au niveau MESSAGE et
        # n'est PAS traverse par les attaques declenchees par un trigger — dont le TIR D'OVERWATCH, qui
        # est justement le porteur du seul consommateur (cf. `attack_damage_attack_triggers`).
        # `target_id` est ici la cible REELLEMENT frappee (#120bis, cf. le commentaire du champ `target`
        # ci-dessous) : le natif emet cet event depuis l'AttackData de l'attaque effectivement resolue.
        # `On(FinalDamage = 0x43 = 67)` — emis par `IdunBattle.Operations.ADamageOperation$$
        # RegisterFinalDamage`, dont les xrefs sont EXHAUSTIVES : `IdunBattle.Operations.
        # AttackDamageOperation$$Execute` (ici) et `IdunBattle.Operations.AbilityDamageOperation$$
        # Execute` (cf. `execute_ability_attack`) — donc UNE fois par ATTAQUE / par degat d'ability,
        # JAMAIS pour un DoT ni un knockback. Place a la SORTIE de l'operation d'attaque, donc APRES
        # les coups additionnels (le compteur `received_damage_this_turn` que lisent ses consommateurs
        # est deja incremente) et AVANT `On(9)`/`On(10)` de `FinishAttackOperation`.
        from ..triggers.dispatch import final_damage_triggers, attack_damage_attack_triggers  # lazy
        final_damage_triggers(state, attacker_id, target_id, ranged=bool(_ranged), profile=_profile)
        attack_damage_attack_triggers(state, attacker_id, target_id,
                                      ranged=bool(_ranged), profile=_profile)
        # `target` (#120bis) = la cible REELLEMENT frappee. Elle differe de celle du message quand la
        # re-resolution d'`ExecuteInternal` a bascule l'attaque sur une remplacante (SwornProtector) :
        # les vecteurs AVAL du natif (after-hit d'`ExecuteHit`) portent l'AttackData de CETTE
        # attaque-la, pas celle du message -> `DamageHandler` la relit ici.
        return {"hits": hits, "total": r["total"], "base": ctx.stat(StatType.ATTACK), "pierce": pierce,
                "target": int(target_id),
                "armor": armor, "clean_min": clean_min, "clean_max": clean_max, "death": death,
                "shield_dmg": r["shield_dmg"], "armor_dmg": r["armor_dmg"],
                "did_crit": r["did_crit"], "did_block": r["did_block"], "did_evade": r["did_evade"],
                "crits": r["crits"], "rolls": r["rolls"], "per_hit": r["per_hit"],
                "ranged": _ranged, "profile": _profile,
                "additional_hits": _ah,          # #202-B : sous-operations #179 (None = aucun groupe)
                "effects": [getattr(e, "name", None) for e in active]}
