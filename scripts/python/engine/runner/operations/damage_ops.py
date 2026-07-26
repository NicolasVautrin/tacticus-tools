"""Vecteurs d'attaque (les 4 `execute*`) extraits d'`operations/damage.py` (scission du module
>1000 lignes, tache #60 -- deplacement VERBATIM, zero changement de comportement).

`_DamageOpsMixin` (mixin de `AttackDamageOperation`) porte :
  - `execute` : attaque normale (`IdunBattle.Operations.AttackDamageOperation$$Execute`) ;
  - `execute_ability_attack` : ability `AttackWithAttackDamage`/`AttackWithAbilityDamage` ;
  - `execute_normal_like` : node `StatAmount`/`PercentageOf` (splash Psyker...) ;
  - `execute_direct` : degat `Direct(...)` (DoT de tuile).

Les helpers `_*` (crit/block/limits/pipeline) et `_run_hits` restent portes par
`AttackDamageOperation` ; chaque `execute*` les atteint via un import LAZY
`from .damage import AttackDamageOperation` (meme convention que `additional_hits`/`displace`/
`summon_ai` -- rompt le cycle `damage` <-> `damage_ops`, `AttackDamageOperation` n'existant
qu'apres l'import de ce mixin comme classe de base)."""
from __future__ import annotations

from ...services.damage_prediction import get_base_damage_fix64, apply_pierce_and_modifiers
from ...services.damage_modifiers import apply_all_modifiers
from ...services.battle_query import are_tiles_adjacent
from ...services.attack_hits_formula import attack_hits_with_modifiers
from ...entities.stats import StatType
from ..state import State
from ..components import (StatsComponent, HealthComponent, PositionComponent, UnitComponent,
                          persistent_data_keys)
from ..damage_model import (select_weapon, select_weapon_pierce, attacker_modifiers,
                            defender_modifiers, build_hits_board, apply_elevation_bonus,
                            apply_trench_reduction, ice_crit_damage_addition,
                            target_trait_names, getstuckin_combat_chance, defender_fixed_armor,
                            tile_status_effects_by_pos)
from ...entities.effects import hits_bonus_from_effects
from ...entities.effects.loki import LIGHT_COVER_TILE_ID
from ...entities.traits import target_hit_multiplier
from .additional_hits import collect_additional_hit_groups, execute_additional_hits
from .damage_hits import HitDamage


class _DamageOpsMixin:
    """Mixin des vecteurs d'attaque de `AttackDamageOperation`. Sans etat (staticmethods) ; herite
    tel quel. Chaque methode lazy-importe `AttackDamageOperation` pour ses helpers/`_run_hits`."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, attacker_id: int, target_id: int,
                spread_pct: int = 20) -> Optional[dict]:
        """Résolution d'une attaque normale (mirror Execute→ExecuteHits→ExecuteHit) depuis
        l'ECS : tire CHAQUE coup sur la plage BRUTE (`stat Attack` ± spread) avec le MT du
        runner (`state.rng`), réduit (perçage de l'arme par distance + armure cible, mods
        d'effet), puis MUTE les PV de la cible. Renvoie `{hits, total, base, pierce, armor,
        clean_min, clean_max, effects}` ou None si stats/positions manquantes.

        PALIER ACTUEL : crit/block NON tirés (paliers 2). Pour un coup MONO propre (no-crit/
        no-block), `total` == dégât réel live (le tirage de dégât est le 1er conso RNG).
        Multi-coups : tire `hits` fois (valable seulement si le live ne tire pas crit/block
        entre les coups — sinon désync RNG ; couvert au palier crit/block)."""
        from .damage import AttackDamageOperation  # lazy : rompt le cycle damage<->damage_ops
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
        # `On(PreUnitAbility=0x2b)` (#100) — `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`
        # l'emet TOUT EN HAUT (`FUN_180026490(0x4d, .., 0x2b)`), AVANT l'execution de l'ability : l'attaque
        # normale EST une active ability (`NormalAttackType`, cf. #139 plus bas). Emis ICI, juste apres la
        # selection d'arme (lecture pure : le natif connait deja la nature du coup) et AVANT tout calcul
        # de coups / modificateurs / **block** — c'est indispensable : son seul consommateur porte
        # (`AnvilShieldFrozenAttackerAdvantageAbility`) pose un stat-mod BLOCK_CHANCE que `_block_sources`
        # doit voir sur CETTE attaque, sinon le port serait un no-op silencieux. Le gate natif
        # `IsNormalAttack` est satisfait STRUCTURELLEMENT (ce vecteur n'est emis que par l'operation
        # d'attaque NORMALE) ; `ability_type` porte quand meme l'id natif du kind attaque-normale
        # (0x3f5=1013) pour les futurs consommateurs a gate `kind`. Aucun autre trigger porte n'ecoute
        # `0x2b` -> no-op (et zero conso RNG) pour toute unite non-porteuse.
        from .triggers.dispatch import pre_unit_ability_triggers   # lazy : cycle damage<->triggers
        pre_unit_ability_triggers(state, attacker_id, target_id, ranged=bool(_ranged),
                                  profile=_profile, ability_type=1013)
        ahc = att.get_component(HealthComponent)
        mods, active = attacker_modifiers(state, attacker_id, ahc.hp if ahc else None, is_ranged=_ranged,
                                          target_traits=target_trait_names(state, target_id),
                                          target_id=target_id, damage_profile=_profile)
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
            from .triggers.dispatch import pre_attack_triggers   # lazy : cycle damage<->triggers
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
        from .triggers.dispatch import pre_attack_hit_triggers   # lazy : cycle damage<->triggers
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
            mm = get_base_damage_fix64(eff_attack, spread_pct=spread_pct)
            lo = apply_all_modifiers(apply_pierce_and_modifiers(
                mm.min + flat_add, pierce, armor, mods, hit_mult=hit_mult, attacker_additive_pre=True), def_mods)
            hi = apply_all_modifiers(apply_pierce_and_modifiers(
                mm.max + flat_add, pierce, armor, mods, hit_mult=hit_mult, attacker_additive_pre=True), def_mods)
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
            r["shield_dmg"], r["armor_dmg"])
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
        return {"hits": hits, "total": r["total"], "base": ctx.stat(StatType.ATTACK), "pierce": pierce,
                "armor": armor, "clean_min": clean_min, "clean_max": clean_max, "death": death,
                "shield_dmg": r["shield_dmg"], "armor_dmg": r["armor_dmg"],
                "did_crit": r["did_crit"], "did_block": r["did_block"], "did_evade": r["did_evade"],
                "crits": r["crits"], "rolls": r["rolls"], "per_hit": r["per_hit"],
                "ranged": _ranged, "profile": _profile,
                "additional_hits": _ah,          # #202-B : sous-operations #179 (None = aucun groupe)
                "effects": [getattr(e, "name", None) for e in active]}

    @staticmethod
    def execute_ability_attack(state: State, attacker_id: int, target_id: int,
                               base_min: int, base_max: int, profile_pierce: int,
                               hits: int, damage_profile: Optional[str] = None,
                               is_melee: Optional[bool] = None,
                               ability_type: Optional[int] = None,
                               is_attack_damage_op: bool = True,
                               force_overkill: bool = False,
                               round_materialize: bool = False) -> Optional[dict]:
        """Attaque d'une ABILITY active (mirror `AttackWithAttackDamage` + `MinMaxDamage`/`GetHits`/
        `GetDamageProfile`). DIFFÈRE de l'attaque normale par la BASE : les bornes du coup = `[base_min,
        base_max]` données par la config d'ability (`GetVariableForLevel` clés 0xc/0xd = minDmg/maxDmg),
        PAS `Attack ± spread%`. Le perçage = celui du PROFIL de l'ability (`GetDamageProfile`). Même
        per-coup natif partagé (`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`) via `_run_hits`, mais en mode ROLL-THEN-REDUCE :
        valeur = tirage BRUT dans [base_min, base_max] puis réduction, + 1 resolve GASPILLÉ par coup
        (cf. `_one_hit`, cas fable rngcrit-1202). Mute les PV de la cible.

        `RandomAmount(min,max)` natif = tirage uniforme dans [min,max] (= `get_damage` sur des bornes
        déjà = [min,max]). Perçage de l'arme normale + ExtraPierce stats : ici on applique le perçage du
        PROFIL d'ability + ExtraPierce de la cible-source comme l'attaque normale (réduction commune).

        DÉFENSIF : si `state.rng` n'est pas calé (replay effet-seul, sans dumpRng), on SKIP le dégât
        (return None) au lieu de lever — le wiring d'ability reste utilisable pour matérialiser un effet
        sans replay de dégât. Un replay de DÉGÂT doit caler rng (dumpRng) avant le cast."""
        from .damage import AttackDamageOperation  # lazy : rompt le cycle damage<->damage_ops
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
        # #217 : vecteur ABILITY -> is_normal_attack=False côté ATTAQUANT aussi (symétrique du #112
        # défenseur ci-dessous). MESURÉ live (probe_217 B, cast Stormcaller avec effet LordOfTempests
        # ACTIF + 3 hexes glacés ring-1 à l'attaque) : natif +0, offline-sans-gate +extraDmg x3 x3 hits
        # -> le natif n'applique PAS les bonus attaquant normal-only aux attaques d'ability.
        # #47 : NATURE DU COUP threadée dans la collecte attacker-modifiers — le natif évalue chaque
        # effet contre le MÊME contexte d'attaque per-coup (`IdunBattle.Entities.Effects.BaseEffect$$DamageBonusForAttack`
        # reçoit l'AbilityEntities du coup : caster/cible/ability déclenchante/arme), quel que soit le
        # VECTEUR (normale OU ability — même collecteur, aucun collecteur ability séparé). Le port ne
        # passait NI `is_ranged` NI l'ability déclenchante -> les bonus attaquant gated `IsRangedAttack`
        # (HeavyWeapon_ExtraDmg IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier +25%, RangedSpecialist IdunBattle.Entities.Effects.Loki.RangedSpecialistEffect$$CreateEffectDamageBonusForAttack +33%, ...) rendaient None
        # pour TOUTE attaque d'ability (MESURÉ live : PlasmaCannon x1.25, MortisRound x1.5 vs offline x1).
        #   - `is_ranged` dérivé d'`is_melee` (nature déclarée du coup, mirror attackRangeType lu au
        #     décompilé de chaque ExecuteBehaviour) ; None (caller historique non classé) = gates inertes
        #     (comportement inchangé — fidèle « inconnu != ranged »).
        #   - `trigger_ability_type` = l'AbilityOrEffect du coup (7e arg d'`AttackWithAttackDamage`
        #     natif, `op_Implicit(*this+0x10)`) -> gate `TriggeringAbilityIs` des amounts conditionnels
        #     (HeavyWeapon x2 quand 0x3ec=1004 MortisRound, cf. HeavyWeaponExtraDmgEffect).
        #   - GATE FAMILLE (== le gate #45f des feuilles positionnelles ci-dessous) : la famille ABILITY
        #     (`AbilityDamageOperation`) recoit des mods ATTAQUANT VIDES (struct zeroee, mesure #45f
        #     Stormcaller) -> is_ranged/trigger NE SONT threades que pour la famille ATTACK
        #     (`is_attack_damage_op=True`) ; ability-family = None (gates inertes, comportement inchange).
        _ranged = (not is_melee) if (is_melee is not None and is_attack_damage_op) else None
        mods, active = attacker_modifiers(state, attacker_id, ahc.hp if ahc else None, target_id=target_id,
                                          is_ranged=_ranged, is_normal_attack=False,
                                          trigger_ability_type=(ability_type if is_attack_damage_op else None))
        # #45f (fable, cause racine du residu x1.5 GreatFrostAxe case-220) : les feuilles POSITIONNELLES
        # (elevation +ElevationBonus=50% si elev(att) > elev(cible), gate effet 0x423 ; trench -50%) du
        # builder de mods ATTAQUANT s'appliquent a la famille ATTACK **SEULEMENT** — gate par FAMILLE de
        # factory native (== `is_attack_damage_op`, cf. _one_hit) :
        #   - ATTACK (`IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` -> `AttackDamageOperation.ExecuteHit
        #     IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`) : le per-coup construit les mods attaquant COMPLETS (slot +4, positional
        #     leaves incluses). MESURE (probe_45f_gfa_elevation, GreatFrostAxe, une variable = la
        #     relation d'elevation) : pre-fix high = live 1.5000x offline sur CHAQUE coup (DidCrit=0),
        #     flat/low = bit-exact ; post-fix 16/16 bit-exact. #47 (2e datapoint INDEPENDANT, vecteur
        #     ability-ATTACK ranged) : PlasmaCannon caster surplomb -> live = x1.25 (HeavyWeapon)
        #     x 1.5 (elevation) = x1.875 offline-avec-feuilles, a plat x1.25 seul.
        #   - ABILITY (`IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` -> `AbilityDamageOperation.ExecuteHit
        #     IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit`) : `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` recoit des mods ATTAQUANT **VIDES**
        #     (struct zeroee) — seuls les mods DEFENSEUR (slot 0xf) s'appliquent. AUCUNE elevation.
        #     MESURE (probe_217_stormcaller A : Njal elev 2 > cibles elev 1) : live SANS elevation ;
        #     un fix non-gate rendait l'offline 1.5006x TROP HAUT — le gate famille retablit bit-exact.
        # Le chemin attaque NORMALE (`execute`, #58/#181) reste inchange (IdunBattle.Operations.AttackDamageOperation$$ExecuteHit aussi).
        if is_attack_damage_op:                                   # famille ATTACK only
            apply_elevation_bonus(state, mods, attacker_id, target_id)
            apply_trench_reduction(state, mods, attacker_id, target_id, damage_profile)
        tsc = tgt.get_component(StatsComponent)
        armor = defender_fixed_armor(state, target_id)   # FOYER partagé (base GetStat(16) + aura Protector allié)
        # #59 suite : threade is_melee + profil de l'ability -> malus DÉFENSEUR gatés (Terrifying_ExtraDefense
        # IsMeleeAttack ; TerminatorArmour DamageProfileIs). None (caller non mis à jour) = comportement
        # historique (gates non appliqués) — INERTE pour une cible sans effet de défense gaté.
        def_mods, _da = defender_modifiers(state, target_id, thc.hp,
                                           is_melee=is_melee, damage_profile=damage_profile,
                                           attacker_id=attacker_id, is_normal_attack=False)  # #112 spéciale
        # BLOCK (cible) = base (GetStat 7/8) + sources d'effet (BeastSlayer...) via le helper PARTAGE
        # `_block_sources` (mirror du GetMultiValueStat(7)/IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances unique du natif).
        # #65 : `damage_profile` gate le trait NoBlocking (profil Psychic bypasse le block, mirror ExecuteHit).
        block_sources = AttackDamageOperation._block_sources(tsc, _da, armor, damage_profile)
        # `On(PreAttackHit=6)` — `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit` emet le MEME
        # trio d'events {6, 8, 0x3d} que la voie normale (verdict RE #147/#150), donc ThrillSeekers se
        # declenche aussi sur une attaque d'ABILITY du porteur contre une cible a pleine vie.
        from .triggers.dispatch import pre_attack_hit_triggers   # lazy : cycle damage<->triggers
        pre_attack_hit_triggers(state, attacker_id, target_id,
                                ranged=not bool(is_melee) if is_melee is not None else False,
                                profile=damage_profile, is_first_hit=True, ability_type=ability_type)
        crit_chance, crit_damage, crit_enabled = AttackDamageOperation._crit_params(ctx, active)
        # #45f : la famille ABILITY (`IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit`) n'a AUCUN chemin
        # crit — pas d'appel RollCritical (le slot crit n'existe que dans `AttackDamageOperation.
        # IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`), l'AttackHit est construit isCrit=0, et `CalculateAbilityDamage
        # IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` est 0-RNG. MESURE (probe_45f --case scrit : Njal --crit 100,700, Stormcaller) :
        # live crits=[0,0,0] et 1 tirage/coup (valeurs = draws consecutifs) la ou l'offline non-gate
        # brulait 1 crit-roll/coup + ajoutait crit flat. cc=0 (tous les porteurs actuels) : strict
        # no-op (roll_critical deja gate cc<1). Le bonus crit-Ice suit (crit_enabled=False -> 0).
        if not is_attack_damage_op:                               # famille ABILITY : crit inexistant
            crit_chance, crit_damage, crit_enabled = 0, 0, False
        # #120 : réduction PLATE défenseur (Nightshroud, ungated -> spéciales aussi) fusionnée pré-perçage.
        AttackDamageOperation._apply_defender_flat_reductions(mods, def_mods)
        # MkXGravis (trait CIBLE 0x3f5) : armure traversée 2× aussi pour les spéciales (CBDWAM IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers
        # partagé quel que soit l'ability, #180). ⚠ `_reduce` (post_roll) ne connaît pas le flag crit du
        # coup, donc le hit_mult s'applique à TOUS les rolls sans exemption crit ici ; un porteur ability
        # cc>=1 + cible MkXGravis exigerait l'exemption (non exercé live). No-op (=1) hors cible hit-twice.
        _tgt_hit_mult = target_hit_multiplier(tsc.ctx.trait_objects()) if tsc is not None else 1

        # #90 : étage MULTIPLICATEUR de CBDWAM IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers (slot 0x10 = `Round(dmg x multiplier,
        # AwayFromZero)` IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers) — INCONDITIONNEL dès qu'un `Nullable<DamageModifiers>` HasValue.
        # Dans `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` (famille ABILITY) le `param_7` défenseur est TOUJOURS
        # construit (slot 0xf) => l'arrondi passe TOUJOURS pour ce vecteur, **mode bornes INCLUS** (et
        # pas seulement le mode `amount` de la feuille `AttackWithAbilityDamage`, seul câblé jusqu'ici).
        # MESURE (probe_mow_targeting_predicate `decomp`, SquigLaunchas 1200 = famille ABILITY mode
        # bornes, profil Physical pierce=1 %, cible astraBullgryn armure 3513, 3 coups, 4 seeds) :
        #   seed 12345 off 86 [28,29,29] live 86 (+0) · 4242 off 87 live 89 (+2) · 777 off 91 live 93
        #   (+2) · 31337 off 87 live 90 (+3) -> l'écart VARIE dans [0, hits] = signature d'un ARRONDI
        #   par coup (un additif systématique donnerait +hits constant). floor -> live == round.
        # La famille ATTACK (`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`, `is_attack_damage_op=True`)
        # reste TRONQUANTE : ces chemins sont live-validés bit-exact ainsi (chantier séparé).
        _round_mat = bool(round_materialize) or not is_attack_damage_op

        def _reduce(value: int) -> int:
            # #75 (case-68 MAJ 13) : additif ForAddition ATTAQUANT = PRÉ-perçage en COMBAT (idem
            # attaque normale — même pipeline natif CalculateAbilityDamage/CBDWAM par coup).
            return apply_all_modifiers(
                apply_pierce_and_modifiers(value, profile_pierce, armor, mods,
                                           hit_mult=_tgt_hit_mult, attacker_additive_pre=True),
                def_mods, round_materialize=_round_mat)

        # ABILITY = roll-then-reduce : on tire dans les bornes BRUTES config (RandomAmount(min,max)) PUIS
        # on réduit (perçage/armure/mods) via `post_roll`. (≠ attaque normale reduce-then-roll.) Confirmé
        # bit-exact live (ThunderousAssault necroOverlord : roll-then-reduce = live 6948, à l'unité ;
        # re-confirmé probe_rngcrit_1202 : VigilanceEternal 3-hit, per-hit bit-exact 5 seeds x 2 cibles).
        # CONSOMMATION (cas fable rngcrit-1202) : ce vecteur = IdunBattle.Operations.AttackDamageOperation$$ExecuteHit
        # avec un STRUCT NON dégénéré → 2 tirages/coup à cc=0 (valeur BRUTE + resolve slot-8 GASPILLÉ),
        # cf. `_one_hit`. ≠ attaque normale (struct dégénéré → 1 tirage/coup).
        hit_nc = HitDamage(base_min, base_max)                            # bornes BRUTES
        # CRIT ability : `IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage` → `IdunBattle.Core.Services.DamageCalculations$$ApplyCritDamage` = critBonus
        # FLAT sur la valeur ROULÉE, PRE-reduce (appliqué dans `_one_hit` branche post_roll via le SHIFT
        # `hit_cr - hit_nc`). `hit_cr` sert aussi au flat #91 (`_capped_flat_cr`, centre bornes+cd) —
        # numériquement == l'ancien modèle bornes-décalées (largeurs égales → même modulo).
        # #45f : + bonus crit-sur-Ice (`IdunBattle.Entities.Effects.IceEffect$$CreateEffectDamageBonusForAttack`) =
        # EffectBonus.addition per-coup-CRIT (PercentageOf(GetStat(10), IceCritDmgBonusPct=25) si cible
        # sur tuile Ice active et non-Immune) — MEME position pipeline (flat PRE-reduce). VALIDE live
        # bit-exact (probe_45f --case crit : GreatFrostAxe cc=100/cd=700 -> +175/coup crit, 4/4).
        _ice_add = ice_crit_damage_addition(state, attacker_id, target_id, ctx) if crit_enabled else 0
        hit_cr = HitDamage(base_min + crit_damage + _ice_add,
                           base_max + crit_damage + _ice_add) if crit_enabled else hit_nc
        # #202 WeaverOfFate : attaquant max-out (effet 1185) -> bornes BRUTES degenerees a (max, max),
        # mirror HitDamage(GetMax, null) d'`IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$GetDamage` (le tirage de
        # VALEUR est court-circuité par min==max — get_damage — mais le resolve slot-8 consomme TOUJOURS
        # 1 tirage/coup, désormais mirroré par `_one_hit` ; puis post_roll reduit le max, roll-then-reduce).
        hit_nc, hit_cr = AttackDamageOperation._apply_max_out(state, attacker_id, hit_nc, hit_cr)
        # #61 CANAL DE COUPS DU VECTEUR ABILITY. `hits` recu ici = la valeur du noeud `hits` du DSL
        # (champ +0x80 du `AttackDamageBehaviour`, evalue en `Nullable<int>` de l'AttackData par
        # `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget`) = la BASE, pas le total.
        #   - famille ATTACK (`is_attack_damage_op=True`) : `IdunBattle.Operations.AttackDamageOperation$$Execute`
        #     passe cette base a `IdunBattle.Operations.AttackDamageOperation$$GetAttackHits` (slot d'interface
        #     0xb5 -> `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`), EXACTEMENT comme l'attaque
        #     normale : `base + ExtraHits(0x11) + (melee ? ExtraHitsMelee(0x17))`, clamp Max(.,0), puis la
        #     boucle des effets (bonus attaquant `OwnerIsCaster` / malus cible `OwnerIsTarget` / auras).
        #     GROUND TRUTH live (case-61, runner isole, une seule variable = le trait de la cible) :
        #     FlailSwing (`nrOfHits`=3) -> **2** coups sur une cible `Parry_ReduceHits`, **3** sur le temoin.
        #     Le port ne traversait PAS ce canal : ni la base (ExtraHits) ni AUCUN bonus/malus.
        #   - famille ABILITY (`is_attack_damage_op=False`) : `IdunBattle.Operations.AbilityDamageOperation$$Execute`
        #     n'appelle PAS `GetAttackHits` (decompile : il lit le `Nullable<int>` et l'utilise BRUT, defaut 1)
        #     -> base SEULE, canal NON traverse. C'est pourquoi le fold est GATE par la famille.
        # `is_melee` de la formule = POSITIONNEL (`IdunBattle.Core.Services.DamagePrediction$$IsMeleeAttack` que
        # `GetAttackHits` appelle lui-meme, et `IdunBattleLogic.Entities.DSLFactory$$IsMeleeAttack` des triggers
        # d'effet), PAS la nature declaree de l'ability : une ability "melee" castee a distance 2 est RANGED
        # pour ce canal. Positions/board absents -> on GARDE la base brute (aucune sur-application).
        _ap_h = att.get_component(PositionComponent)
        _tp_h = tgt.get_component(PositionComponent)
        if is_attack_damage_op and _ap_h is not None and _tp_h is not None and state.board is not None:
            from .triggers.base import _is_ranged_position   # lazy : cycle damage<->triggers
            _melee_pos = not _is_ranged_position(state, attacker_id, target_id)
            _board_h, _auras_h, _tgt_eff_h = build_hits_board(
                state, attacker_id, target_id, (_ap_h.col, _ap_h.row), (_tp_h.col, _tp_h.row),
                is_melee=_melee_pos)
            # A3 (#113) : gate compute-time LightCover, mirror du call-site de l'attaque normale.
            _t_terrain_h = state.board.terrain_at(_tp_h.col, _tp_h.row)
            _on_cover_h = (_t_terrain_h == LIGHT_COVER_TILE_ID) if _t_terrain_h is not None else None
            hits = attack_hits_with_modifiers(
                weapon_hits=int(hits), extra_hits=ctx.stat(StatType.EXTRA_HITS),
                extra_hits_melee=ctx.extra_hits_melee,
                attacker_effects=active, trait_objects=ctx.trait_objects(),
                target_effects=_tgt_eff_h, aura_sources=_auras_h, board=_board_h,
                is_melee=_melee_pos, damage_profile=damage_profile,
                # combat : GetStuckIn n'est PAS dans la formule (behaviour d'exec chance-gate, #62c).
                # Le vecteur ability ne roule pas non plus de coup bonus (aucun `bonus_hit_chance`
                # passe a `_run_hits` ici) -> gate False, comme la facade combat de l'attaque normale.
                include_bonus_hit_behaviours=False,
                defender_on_cover=_on_cover_h,
                # #84 : memes DEUX entrees d'etat que la facade normale pour le gate LetTheGalaxyBurn.
                # `IsPersistentData` reste faux sur ce vecteur (le natif n'emet PAS `On(PreAttack=5)`
                # depuis le chemin ability -- il est emis par `ExecuteNormalAttack`) ; seule la branche
                # `TargetHasTileEffect` peut armer le +1 ici. Fidele, documente en residu (case-61).
                tile_effects_by_pos=tile_status_effects_by_pos(state, [(_tp_h.col, _tp_h.row)]),
                attacker_persistent_data=persistent_data_keys(att),
                is_normal_attack=False)     # gate `IsNormalAttack` (PowerTrip) : vecteur ABILITY
        hits = max(1, int(hits))
        _hp_before_chain = int(thc.hp or 0)     # PV AVANT l'attaque (#116, cf. le retour `hp_before`)
        shc, shield_total = AttackDamageOperation._target_shield(tgt)      # bouclier shield-first
        r = AttackDamageOperation._run_hits(state.rng, hit_nc, hit_cr, crit_chance,
                                            crit_enabled, hits, block_sources, shield=shield_total,
                                            post_roll=_reduce,
                                            capped_reductions=def_mods.capped_reductions,
                                            # #67 : etage limites — mode 2 = ability
                                            # (`IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`)
                                            limits=AttackDamageOperation._target_limits(
                                                tgt, thc, damage_profile, is_special=2),
                                            limits_hp=int(thc.hp or 0),
                                            # famille de factory native (cf. _one_hit) : True =
                                            # AttackWithAttackDamage (resolve gaspille) ; False =
                                            # AttackWithAbilityDamage (AbilityDamageOperation, sans).
                                            is_attack_damage_op=is_attack_damage_op,
                                            # flag « always overkilled » (FlailSwing) : bypasse le cap
                                            # Resilient a chaque coup (no-op cible non-Resilient).
                                            force_overkill=force_overkill)
        AttackDamageOperation._deplete_shield(shc, r)
        AttackDamageOperation._apply_damage_pipeline(                   # chokepoint partage (#202)
            state, target_id, attacker_id, tgt, thc, r["total"], damage_profile,
            r["shield_dmg"], r["armor_dmg"])
        # POSE DE FEU (OnFireDamageAbility) — `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` tourne après CHAQUE coup
        # d'attaque, NORMALE **et** ability. Le port ne câblait ce vecteur que pour l'attaque normale
        # (DamageHandler) ; ici on porte la pose on-hit des tile-effects de profil pour les attaques
        # d'ABILITY à profil OnFire (ArmoriumCherub, splash FireOfAbsolution, BrazierOfHolyFire…). #136.
        # Idempotent (no-op si la tuile brûle déjà) → une pose post-attaque == per-coup pour le feu.
        from .triggers import _on_fire_damage_ability, after_hit_ability_attack  # lazy : cycle damage<->triggers
        fire = _on_fire_damage_ability(state, attacker_id, target_id, damage_profile)
        # VECTEUR AFTER-HIT (ability/splash) : dispatch générique — reset ActOfFaith au crit (#138) + tout
        # after-hit trigger (#140 : splash Psyker sur ability/splash psychique, chain borné par le cap).
        # `ranged` = POSITION-based (calculé dans after_hit_ability_attack, mirror IsRangedAttack).
        after_hit = after_hit_ability_attack(state, attacker_id, target_id, r["did_crit"],
                                             profile=damage_profile, ability_type=ability_type,
                                             did_block=r["did_block"])
        return {"hits": hits, "total": r["total"], "base_min": base_min, "base_max": base_max,
                "pierce": profile_pierce, "armor": armor, "fire": fire, "after_hit": after_hit,
                "clean_min": hit_nc.min * hits, "clean_max": hit_nc.max * hits,
                "did_crit": r["did_crit"], "did_block": r["did_block"], "did_evade": r["did_evade"],
                "crits": r["crits"], "rolls": r["rolls"], "per_hit": r["per_hit"],
                # part PV par coup + PV AVANT l'attaque (#116 `ChainLeftOverHitsAttackDamage` : localiser
                # le coup qui met la cible a 0 PV -> compter les coups GASPILLES sur le cadavre).
                "per_hit_health": r["per_hit_health"], "hp_before": _hp_before_chain}

    @staticmethod
    def execute_normal_like(state: State, attacker_id: int, target_id: int, base: int,
                            profile_pierce: int, hits: int = 1, spread_pct: int = 20,
                            damage_profile: Optional[str] = None,
                            is_melee: Optional[bool] = None,
                            ability_type: Optional[int] = None) -> Optional[dict]:
        """Attaque dont le node de dégât est un `StatAmount`/`PercentageOf(StatAmount(...))` (ex. splash
        Psyker = `PercentageOf(StatAmount(Attack), psykerExtraDmg%)`, profil Psychic). Pipeline
        **reduce-then-roll** (bornes pré-réduites puis tirage, post_roll=None), comme l'attaque normale
        (≠ ability RandomAmount), avec base + perçage de profil DONNÉS. Mute les PV de la cible.
        `spread_pct` = variance d'arme (DamageSpreadPercentage) : **0 pour un montant `StatAmount`**
        (mono-valeur, AUCUNE variance — confirmé live, splash Psyker = base exact) ; 20 seulement si le
        node porte de vraies bornes min/max d'arme. Renvoie le dict résultat (per_hit/total/...) ou None."""
        from .damage import AttackDamageOperation  # lazy : rompt le cycle damage<->damage_ops
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
        from .triggers.dispatch import pre_attack_hit_triggers   # lazy : cycle damage<->triggers
        pre_attack_hit_triggers(state, attacker_id, target_id,
                                ranged=not bool(is_melee) if is_melee is not None else False,
                                profile=damage_profile, is_first_hit=True, ability_type=ability_type)
        crit_chance, crit_damage, crit_enabled = AttackDamageOperation._crit_params(ctx, active)
        # #120 : réduction PLATE défenseur (Nightshroud, ungated -> splash/normal-like aussi) fusionnée pré-perçage.
        AttackDamageOperation._apply_defender_flat_reductions(mods, def_mods)

        def _reduced(eff_base: int, flat_add: int = 0) -> "HitDamage":
            # #75 (case-68 MAJ 13) : additif ForAddition ATTAQUANT = PRÉ-perçage en COMBAT.
            # `flat_add` (#45f) = EffectBonus.addition PER-BRANCHE (Ice crit-only) : POST-spread
            # PRE-perçage, sans polluer `mods` (applique aux deux branches).
            mm = get_base_damage_fix64(eff_base, spread_pct=spread_pct)
            lo = apply_all_modifiers(apply_pierce_and_modifiers(
                mm.min + flat_add, profile_pierce, armor, mods, attacker_additive_pre=True), def_mods)
            hi = apply_all_modifiers(apply_pierce_and_modifiers(
                mm.max + flat_add, profile_pierce, armor, mods, attacker_additive_pre=True), def_mods)
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
                                            limits_hp=int(thc.hp or 0))
        AttackDamageOperation._deplete_shield(shc, r)
        AttackDamageOperation._apply_damage_pipeline(                   # chokepoint partage (#202)
            state, target_id, attacker_id, tgt, thc, r["total"], damage_profile,
            r["shield_dmg"], r["armor_dmg"])
        # VECTEUR AFTER-HIT (splash StatAmount) : idem execute_ability_attack — reset ActOfFaith au crit
        # (#138) + vecteur complet (#140). `ranged` = POSITION-based (mirror IsRangedAttack), calculé dedans.
        # `ability_type` = kind AbilityOrEffect du coup (smite Psyker 0x3f5 -> branche 2 AddIce #35).
        from .triggers import after_hit_ability_attack
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
        from .damage import AttackDamageOperation  # lazy : rompt le cycle damage<->damage_ops
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
                from ...services.trait_damage_limits import apply_group_unit_damage_limit
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
