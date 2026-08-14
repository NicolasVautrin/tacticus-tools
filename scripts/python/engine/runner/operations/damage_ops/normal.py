"""Vecteur d'ATTAQUE NORMALE (`_DamageOpsMixin.execute`), extrait d'`operations/damage_ops.py`
(scission du module >1000 lignes, tache #169 -- deplacement VERBATIM, zero changement de
comportement).

Mirror `IdunBattle.Operations.AttackDamageOperation$$Execute` -> `ExecuteHits` -> `ExecuteHit`.

PATCH-POINT (tests/probes) : `execute` resout `apply_all_modifiers` dans les globals de CE
module -- un patch pose sur le `__init__` du package serait un NO-OP SILENCIEUX. Patcher
`damage_ops.normal.apply_all_modifiers`."""
from __future__ import annotations

import hexgeo

from ....services.damage_prediction import get_base_damage_fix64, apply_pierce_and_modifiers
from ....services.damage_config import resolve_spread_pct
from ....services.damage_modifiers import apply_all_modifiers
from ....services.battle_query import are_tiles_adjacent, weapon_is_melee
from ....services.attack_hits_formula import attack_hits_with_modifiers
from ....entities.stats import StatType
from ...state import State
from ...components import (StatsComponent, HealthComponent, PositionComponent,
                           persistent_data_keys, unit_prevents_overkill,
                           can_be_overkilled, unit_is_overkilled,
                           has_effect_of_type)                              # #484 : hisse
from ...damage_model import (select_weapon, select_weapon_pierce, attacker_modifiers,
                             defender_modifiers, build_hits_board, apply_elevation_bonus,
                             apply_trench_reduction, ice_crit_damage_addition,
                             target_trait_names, getstuckin_combat_chance, defender_fixed_armor,
                             tile_status_effects_by_pos, battle_query_is_charging)
from ....entities.effects import hits_bonus_from_effects
from ....entities.effects.loki.hits import LIGHT_COVER_TILE_ID
from ....entities.traits import target_hit_multiplier
from ..additional_hits import collect_additional_hit_groups, execute_additional_hits
from ..damage_hits import HitDamage, attack_state_out as _attack_state_out
from ._channel import _normal_attack_kind
from ...components import unit_is_dead
from ....entities.active_ability_type import ActiveAbilityType
from ....services import custom_normal_attack as _cna
from ..active_ability import (execute_for_replaced_target, get_tiles,
                                     resolve_replaced_target)
#: FORME B : `probe_429r1r1r1_ability_attack_dead_target.py` substitue
#: `active_ability.is_dead_unit_and_not_allowed_by_ability` ; hisse en forme A le stub serait
#: INERTE (gisement mesure de la famille #429-r1). L'import de module relit a l'appel.
from .. import active_ability as _active_ability


class _Normal:
    """Vecteur d'attaque NORMALE. Sans etat (staticmethod) ; agrege par `_DamageOpsMixin`."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, attacker_id: int, target_id: int,
                spread_pct: Optional[int] = None, is_overwatch: bool = False,
                triggering_ability: Optional[int] = None,
                allow_dead_caster: bool = False,
                skip_hit_count_query: bool = False) -> Optional[dict]:
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
        # --- #429-r1-r1 GATE CIBLE-MORTE, PREMIER gate d'`IdunBattle.Operations.
        # ActiveAbilityOperation$$ExecuteInternal` (mirror ; #429-r1 l'avait pose sur la seule voie
        # d'ABILITY). L'attaque normale native EST une active ability (#139) : elle traverse le MEME
        # `ExecuteInternal`, donc le MEME gate. Il est ICI, au rang de l'OPERATION, et pas au rang du
        # message `AttackUnitMessage` (qui n'existe PAS en natif) parce que le natif n'a qu'UN site
        # d'execution : `Core.Services.OperationProcessor$$ActiveAbility` est le SEUL appelant CODE
        # d'`ActiveAbilityOperation$$Execute` (hors la re-entree `ExecuteForReplacedTarget`), et
        # `IdunBattle.Entities.Behaviours.UseActiveAbilityBehaviour$$Execute` -- la feuille DSL par
        # laquelle passent TOUTES les attaques normales DECLENCHEES (overwatch, riposte, drone
        # commande, summon) -- l'appelle exactement comme un cast commande. Poser le gate au rang du
        # message n'aurait ferme qu'une des ~12 portes du port ; ce foyer les ferme toutes, comme le
        # natif.
        # `ability_class=None` = le comportement natif de TOUTE attaque normale : `CanContinueOnDeadTarget`
        # (slot 0x11) n'a qu'UNE implementation (`AActiveAbility`), qui lit le bit 38 `AllowDeadTarget`
        # du masque de CONTINUE, et un SEUL site du binaire le pose --
        # `IdunBattleLogic.Entities.Abilities.Active.Loki.GreatFrostAxeAbility$$GetTargetingOptionsForContinue`,
        # qui n'est pas une attaque normale (scan d'instructions : `probe_429r1_bit_readers_scan.py`).
        # AUCUNE derogation cote CIBLE, contrairement a l'axe CASTER : le decompile du gate ne lit
        # AUCUN champ d'`AbilityOptions` (pas d'equivalent du `options@+0x4a` que `UseActiveAbility`
        # force a 1) -- d'ou l'absence de parametre `allow_dead_target`.
        if _active_ability.is_dead_unit_and_not_allowed_by_ability(state, None, target_id):
            return None
        if state.rng is None:
            raise ValueError("state.rng non calé (seed depuis dumpRng avant un replay-diff)")
        # #449-r2-r4 : `spread_pct=None` = LU de `BattleConfiguration.Damage.DamageSpreadPercentage`
        # (`IdunBattle.Core.Services.DamageCalculations$$get_DamageSpreadPercentageFix64` lit
        # `configuration+0x20`). Le défaut était `20` en dur — un couplage non lu.
        spread_pct = resolve_spread_pct(spread_pct, state)
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
        # #419-r1-tr14-r1-r1 -- LA DISTANCE EST LA VRAIE, ET L'ADJACENCE EST UN CANAL A PART.
        # `BattleQuery$$GetAttackWeaponForDefaultNormalAttack` (slot `0xaf`) lit DEUX choses :
        # `AreEntitiesAdjacent(casterTiles, target)` pour choisir la branche melee, et une DISTANCE
        # (rendue par le service de mouvement) pour la porte `dist <= Range` de `FindRangedWeapon`.
        # Ce site rabattait les deux sur un `dist = 1 if adj else 2` BINAIRE : la porte de portee ne
        # pouvait alors JAMAIS mordre au-dela de 2, et une unite tirait a 3 hex avec une arme de
        # portee 2. MESURE (`probe_419r1tr14r1r1_range_gate_generalisation.py --combat`,
        # `adeptCanoness` sur MC1_67, cible a 3 hex) : natif `0 degat / 0 tirage`, port
        # `1311 degats / 2 tirages` -- le natif NO-OPE (`ExecuteBehaviour`), le port frappait.
        adj = dist = None
        if ap is not None and tp is not None:
            adj = are_tiles_adjacent((ap.col, ap.row), (tp.col, tp.row), state.board)
            dist = hexgeo.distance((ap.col, ap.row), (tp.col, tp.row))
        pierce, _ranged, whits = select_weapon_pierce(ctx, dist, is_adjacent=adj)
        _w = select_weapon(ctx, dist, is_adjacent=adj)
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
        # `On(PreUnitAbility=0x2a)` (#100) — `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`
        # l'emet TOUT EN HAUT (`FUN_1800280e0(0x4d, .., 0x2a)` = `On(PreUnitAbility)`), AVANT
        # l'execution de l'ability : l'attaque
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
        # lazy : cycle damage<->triggers. Forme MODULE : l'attribut est relu a l'appel, donc une
        # substitution posee sur `dispatch.ability` mord quelle que soit la forme finale de cet
        # import (`probe_485r1r1_formes_dimport.py`). Hisse en `from ... import X`, il serait
        # INERTE -- et ce differe-ci est mesure GRATUIT, donc le cliquet #485 le prescrit.
        from ..triggers.dispatch import ability as ability_dispatch
        # #120bis SNAPSHOT DE TUILE de la cible (AVANT l'emission) — `IdunBattle.Operations.
        # ActiveAbilityOperation$$GetAbilityEntities` fige `AbilityEntities@+0x38 =
        # EntityExtensions.GetTiles(finalTarget)` en amont du `0x2b` ; la re-resolution qui SUIT
        # l'emission confronte ce fige a l'occupation reelle.
        _target_tiles = get_tiles(state, target_id)
        ability_dispatch.pre_unit_ability_triggers(state, attacker_id, target_id,
                                                   ranged=bool(_ranged), profile=_profile,
                                                   ability_type=1013)
        # #133 GATE ACTEUR-MORT **POST-`On(0x2a = PreUnitAbility)`** — mirror du test qui suit IMMEDIATEMENT
        # l'evenement dans `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` (lu
        # verbatim au decompile) :
        #     FUN_1800280e0(0x4d, .., 0x2a);          # On(PreUnitAbility)
        #     if (options@0x4a == 0 && IsUnit(caster) && IsDead(caster, state)) return 0;
        # Le natif teste DEUX FOIS la mort du caster : en TETE d'operation (#70, deja porte au niveau
        # MESSAGE dans `DamageHandler.visit_AttackUnitMessage`) et ICI, parce que la cascade de
        # triggers reveillee par `0x2b` peut l'avoir TUE entre-temps. C'est exactement ce que fait la
        # riposte `MartialSuperiority` (« before the enemy attack executes ») : si elle tue
        # l'attaquant, l'attaque entrante est ANNULEE (0 tirage RNG, 0 degat, aucun after-hit).
        # `options@0x4a` = le flag « caster mort autorise » des `AbilityOptions`.
        #
        # ⚠ #88 -- CE FLAG EST POSE PAR UNE VOIE DU PORT, ET SON ABSENCE RENDAIT `FinalJustice`
        # SILENCIEUSEMENT INERTE. `IdunBattle.Entities.Behaviours.UseActiveAbilityBehaviour$$Execute`
        # (la feuille `DSLFactory$$UseActiveAbility`, seule voie du death-rattle FinalJustice) assemble
        # ses `AbilityOptions` en RECOPIANT champ par champ les siens (`behaviour+0x68..0xac`) -- SAUF
        # un octet, force au LITTERAL `1` (`uStack_210._0_2_ = CONCAT11(*(behaviour + 0xa8), 1)`).
        # MESURE LIVE qui tranche (probe_88_fuelled_by_fury_revive) : `ultraTitus` a `hp = 0` porte bel
        # et bien sa riposte FinalJustice, pour 10502 de degat, et TUE. Le gate ci-dessous, porte pour
        # `MartialSuperiority` (#133), l'avalait donc entierement des que la mort passait par le VRAI
        # chokepoint `_fire_death_if_killed` (qui pose `alive=False` + `hp=0` avant `On(1)`). Le trou
        # n'etait visible dans AUCUN test : `test_finaljustice_live` appelle `after_death_triggers`
        # sur un Kharn encore VIVANT dans l'ECS.
        # `allow_dead_caster=True` n'est donc PAS une derogation de confort : c'est le mirror du flag,
        # pose par le SEUL appelant qui le pose cote natif (`UseActiveAbility`). Toutes les autres
        # voies (attaque normale d'un message, overwatch, re-entrees) gardent le gate.
        if not allow_dead_caster and unit_is_dead(state.get_entity(attacker_id)):
            return None
        # #120bis RE-RESOLUTION DE CIBLE — mirror du bloc qui suit IMMEDIATEMENT le `0x2b` dans
        # `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`. L'attaque normale EST une
        # active ability (`ALoki_NormalAttackAbility`) : elle traverse le MEME etage que le cast, et
        # c'est LUI qui envoie les coups sur Kell apres le switch de SwornProtector (le switch, seul,
        # ne fait que deplacer Creed). La re-entree = un `AttackDamageOperation.execute` NEUF sur la
        # nouvelle cible (mirror `ActiveAbilityOperation$$Execute`), donc selection d'arme, distance,
        # `On(0x2a = PreUnitAbility)`, coups et modificateurs sont TOUS recalcules contre elle. Cet appel-ci `return`e
        # aussitot, comme le natif. Cable sur les DEUX voies a la fois (cf. `active_ability.py`).
        _replaced, _new_target = resolve_replaced_target(state, target_id, _target_tiles)
        if _replaced:
            return execute_for_replaced_target(
                state, attacker_id, _new_target,
                lambda t: AttackDamageOperation.execute(state, attacker_id, t, spread_pct,
                                                        is_overwatch=is_overwatch,
                                                        # l'`AbilityOrEffect` DECLENCHANTE est celle
                                                        # de l'ATTAQUE, pas de la cible : la
                                                        # re-entree la conserve (sans quoi un tir
                                                        # d'overwatch re-cible perdrait en silence
                                                        # et sa `DamageSource` et le noeud
                                                        # `TriggeringAbilityIs` du canal COUPS).
                                                        triggering_ability=triggering_ability,
                                                        allow_dead_caster=allow_dead_caster))
        # #419-r1-tr14-r1-r1 -- PAS D'ARME UTILISABLE = PAS D'ATTAQUE, et c'est le natif qui le dit :
        # `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteBehaviour`
        # tient tout entier dans ce gate --
        #     weapon = FindAttackWeapon(entities);            // slot 0xaf d'IBattleQuery
        #     if (weapon == null) return default;             // NI ExecuteInformWeapon, NI
        #     ExecuteInformWeapon(weapon, ...);               // ExecuteNormalAttack, NI
        #     ExecuteNormalAttack(abilityState, ..., weapon); // ExecuteTriggerAbilities
        #     return ExecuteTriggerAbilities(entities, weapon);
        # -- et c'est le MEME `FindAttackWeapon` (donc le MEME slot `0xaf`) que
        # `ALoki_NormalAttackAbility$$PredictAttack` consulte : un seul foyer, deux faces.
        # PLACEMENT : APRES `On(0x2a = PreUnitAbility)`, le gate acteur-mort et la re-resolution de
        # cible -- tous trois vivent dans `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`,
        # donc EN AMONT d'`ExecuteBehaviour` : le natif les joue meme quand l'arme manque.
        # Sans ce gate, la suppression du repli croise (`battle_query`) ferait attaquer avec
        # `pierce = 100`, `weapon_hits = 1` et `profile = None` -- pire que l'ancien repli melee.
        if _w is None:
            return None
        # #419-r1-tr14-r4-r2-r1 -- `ExecuteInformWeapon(this, weapon, entities, useSpecial: 0)`, la
        # ligne qui suit IMMEDIATEMENT le gate d'arme dans
        # `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteBehaviour`
        # (avant `ExecuteNormalAttack`, avant `ExecuteTriggerAbilities`). Elle POSE deux tags de flux,
        # MESURES sur MC1_67 : `Action=Info Entity=NO_ENTITY` / `Attack_Weapon_IsMelee` +
        # `Attack_Weapon_DamageProfile`, premier enfant du `Group=Ability_Power ...
        # Source=Loki_NormalAttack`.
        #
        # `useSpecial` n'est PAS toujours `0` : sur les NEUF appelants d'`ExecuteInformWeapon`, sept
        # posent le litteral `0` et DEUX posent `1` dans une branche gardee. Le port n'a qu'UN foyer
        # d'attaque normale (celui-ci) la ou le natif a un `ExecuteBehaviour` par classe : la
        # decision est donc DELEGUEE au foyer unique `custom_normal_attack.inform_weapon_use_special`,
        # qui porte les DEUX gates LUS : `FeederTendrils` (`IsCharging(caster,target) &
        # weapon.IsMelee`) et `OptimizedGait` (`HasEffect(caster, CordClaw_AdditionHits)`, ancre
        # TRANCHEE #419-r1-tr14-r4-r2-r1-r2). MESURES LIVE du 2026-08-06 (MC1_67) : le flux natif
        # ecrit `Tag=Attack_Weapon_Use_Special:1` dans CHACUN des deux regimes, et dans aucun autre.
        #
        # ⚠ CE `Use_Special`-CI EST COMBAT-INERTE, PAS LA BRANCHE QUI LE POSE. La ligne
        # d'`InformWeapon` ne mute rien (`InformBehaviour$$Execute` -> pas `StepType.Info`) ; mais
        # chez `FeederTendrils` le MEME gate ouvre AUSSI un `Heal` + un `AddEffect`, joues juste
        # en dessous. Ne pas lire l'inertie du tag comme l'inertie de la branche.
        #
        # COMBAT-INERTE PAR CONSTRUCTION : `InformBehaviour$$Execute` ne mute rien et
        # `InformOperation$$Execute` ne fait que dispatcher un pas `StepType.Info` -- aucun tirage,
        # donc l'ordre `state.rng` de l'attaque qui suit est INCHANGE (bit-exactness preservee).
        from ...abilities.behaviours.combat import InformWeapon   # lazy : cycle damage<->abilities
        from ...abilities.targeting import normal_attack_type_for  # lazy : meme cycle
        # forme MODULE : les trois noms sont SUBSTITUES (probe_419r1tr14r4r2r1r1) -- lies au
        # chargement, ces mesures cesseraient de mordre en silence (#485-r1-r1).
        from ...abilities.loki.feeder_tendrils import execute_feeder_tendrils_special
        _na_type = normal_attack_type_for(state, attacker_id)
        _na_name = (ActiveAbilityType(_na_type).name
                    if _na_type is not None and _na_type in set(int(x) for x in ActiveAbilityType)
                    else None)
        # Le gate est evalue UNE FOIS et sert DEUX consommateurs (le tag, puis la branche
        # speciale) : le natif ne le teste qu'une fois non plus.
        _charging = battle_query_is_charging(state, attacker_id, target_id)
        _melee = weapon_is_melee(_w)
        # #419-r1-tr14-r4-r2-r1-r2 : le gate de `OptimizedGait_NormalAttackAbility$$ExecuteBehaviour`
        # est `EntityExtensions$$HasEffect(entities.caster, state, 0x4e2, null)` -- l'ANCRE est le
        # CASTER (`AbilityEntities` `+8`, cf. la RE dans `custom_normal_attack.py`). `onlyActive` est
        # `null` au call-site natif, donc PAS de filtre `IsActive` : c'est exactement ce que fait
        # `has_effect_of_type` (`EffectsState.has_effect`, qui ne filtre que `consumed`).
        _use_special = _cna.inform_weapon_use_special(
            _na_name, is_charging=_charging, weapon_melee=_melee,
            caster_has_gate_effect=has_effect_of_type(state, attacker_id,
                                                      _cna.USE_SPECIAL_GATE_EFFECT))
        _iw_tags = InformWeapon.from_weapon(_w, use_special=_use_special).tags()
        # #419-r1-tr14-r4-r2-r1-r1 : `FeederTendrils_NormalAttackAbility$$ExecuteBehaviour` execute,
        # ENTRE `ExecuteInformWeapon` et `ExecuteNormalAttack`, un `ExecuteAtomic(Heal(caster) +
        # AddEffect(Pinned, cible), 0x2a)`. La POSITION est celle du natif (pas apres l'attaque) :
        # `Pinned` porte un malus de degat ATTAQUANT, donc il ne touche pas l'attaque qui suit -- mais
        # on mirrore la position, pas l'observable du jour. Feuilles PURES (0 tirage) -> l'ordre
        # `state.rng` de l'attaque est INCHANGE, bit-exactness preservee.
        if _cna.feeder_tendrils_special_applies(_na_name, is_charging=_charging,
                                                weapon_melee=_melee):
            execute_feeder_tendrils_special(state, attacker_id, target_id)
        ahc = att.get_component(HealthComponent)
        mods, active = attacker_modifiers(state, attacker_id, ahc.hp if ahc else None, is_ranged=_ranged,
                                          target_traits=target_trait_names(state, target_id),
                                          target_id=target_id, damage_profile=_profile,
                                          # LionHelm_ExtraDmg : gate `IsOverwatchAttack` de l'aura
                                          # ALLIEE (meme flag que le bonus de percage Hailstrike).
                                          is_overwatch=bool(is_overwatch))
        # #924 : ce vecteur ne threade PAS `trigger_ability_type` vers `attacker_modifiers` (axe
        # DEGAT), alors que le natif n'a qu'UN contexte per-coup (`AbilityEntities`) dont le champ
        # +0x98 est lu indifferemment par les canaux COUPS et DEGAT. L'axe COUPS le recoit bien
        # (`build_hits_board` plus bas, consomme par `PurgeResponse`). Le threader est la PREMIERE
        # etape du residu **#924-r2** ; il n'est pas fait ici parce qu'aucun consommateur porte ne
        # le lit sur cet axe aujourd'hui -- l'ajouter seul serait un elargissement NON VALIDABLE
        # d'un foyer partage.
        # #58 : feuille positionnelle ELEVATION (+surplomb) ajoutee au `mods` de l'attaquant, comme la
        # prediction (service PARTAGE `calculate_elevation_bonus_modifier` de DamageCalculations ; positions
        # REELLES depuis l'ECS/board).
        apply_elevation_bonus(state, mods, attacker_id, target_id)
        # #181 : reduction TRENCH (feuille positionnelle soeur de l'elevation dans le meme builder natif) —
        # -50% si la cible porte l'effet Trench + conditions attaquant-tuile (calculate_trench_reduction).
        apply_trench_reduction(state, mods, attacker_id, target_id, _profile)
        # `On(PreAttack=5)` (#84) — vecteur natif emis par `IdunBattle.Operations.
        # StartAttackOperation$$Execute` (`EvaluateAbilitiesImmediately(5, ...)`, slot 80), que
        # `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` declenche (slot 58 `StartAttack`)
        # AVANT d'executer le behaviour enfant. Emis APRES la selection d'arme (le natif connait deja
        # la nature du coup) ; les deux consommateurs portes sont `LetTheGalaxyBurnArmAbility` (arme
        # un flag persistant relu par le canal de coups juste dessous) et
        # `SuppressiveFireAddEffectAbility` (pose `Pinned` -> `On(PreEffectAdded)` ->
        # `TerrifyingCrescendo_ExtraDmg` monte d'un niveau).
        #
        # ⚠ **PLACE REDESCENDUE SOUS `attacker_modifiers` (#953-r2), ET C'EST LE VECTEUR NORMALE
        # SEUL.** #512-r1 l'avait remontee AU-DESSUS en generalisant une mesure faite sur une
        # ABILITY (`1197 ExcruciatingFrequencies`). La mesure d'aujourd'hui, sur ce vecteur-ci,
        # dit l'INVERSE -- `probe_953r2_ecart_ranged_shiron.py`, board `MC1_67` / seed 777,
        # `emperNoiseMarine` en RANGED, TROIS attaques successives, meme etat et meme flux RNG :
        #
        #   passe | niveau 1424 AVANT (natif) | NATIF | PORT avec la place remontee
        #     0   |            -              | 4699  | 6396  (+36 %)
        #     1   |            1              | 6301  | 8541  (+35 %)
        #     2   |            2              | 8230  | 10526 (+28 %)
        #
        # Le natif applique donc le niveau D'AVANT l'attaque ; le port appliquait niveau+1. Avec le
        # seul canal degat de 1424 neutralise, le port rendait le ledger natif COUP PAR COUP sur les
        # trois passes -- l'ecart entier tient a ce seul cran, et le reste du pipeline etait juste.
        #
        # CE QUI SEPARE LES DEUX VOIES, LU AU DECOMPILE (pas deduit de l'ecart) :
        # `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteNormalAttack`
        # -- la base de TOUTE attaque normale -- termine par
        # `IdunBattle.Entities.Abilities.AActiveAbility$$ExecuteAtomic(behaviour, entities, 0x3d)`,
        # c.-a-d. `IdunBattleLogic.Entities.DSLBehaviors$$AtomicGroup`. Et
        # `IdunBattle.Operations.AtomicGroupOperation$$Execute` porte une FILE : apres l'action et la
        # cloture du groupe (slots 20/21 d'`IBattleQuery`), il DEPILE (slot 10) et rejoue chaque
        # entree par `IOperationProcessor.EvaluateAbilities` (slot 78) ou
        # `UnregisterEntityFromTriggers` (slot 85). `1197`, lui, passe par `Execute` et NON
        # `ExecuteAtomic` (case-512 §1) : ses triggers sont immediats, et `probe_512 --regime R1`
        # reste VERT bit-exact avec la place remontee sur `ability.py`.
        #
        # ⚠ Ce que cette place PORTE et ce qu'elle NE porte PAS : le natif emet bien `On(5)` avant
        # tout, et ce qui est differe est la CASCADE qui en decoule. Le port n'a pas de groupe
        # atomique ; descendre l'emission sous `attacker_modifiers` rend le MEME observable pour les
        # deux consommateurs portes (le flag `LetTheGalaxyBurn` est relu par `build_hits_board`, qui
        # suit ; le bonus de degat `TerrifyingCrescendo` est lu par `attacker_modifiers`, qui
        # precede) sans toucher l'ordre `state.rng` -- les trois etages sautes
        # (`attacker_modifiers`, elevation, trench) sont PURS. Un futur consommateur de `On(5)` qui
        # poserait un effet lu par le canal COUPS serait, lui, mal servi : c'est le residu #953-r4.
        if tp is not None:
            from ..triggers.dispatch.attack import pre_attack_triggers  # lazy : cycle damage<->triggers
            pre_attack_triggers(state, attacker_id, target_id, ranged=bool(_ranged), profile=_profile)
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
        # #227 SNAPSHOT DES ENTREES D'ETAT DU GATE `LetTheGalaxyBurn`, pris ICI = juste apres
        # `On(PreAttack=5)` et AVANT le premier coup. C'est l'etat que le natif voit : la tuile de la
        # cible est FIGEE par `IdunBattle.Operations.ActiveAbilityOperation$$GetAbilityEntities`
        # (`AbilityEntities@+0x38 = EntityExtensions.GetTiles(finalTarget)`, cf. `_target_tiles`
        # ci-dessus), donc les status-effects qu'une SOUS-OPERATION de cette meme attaque pose en
        # cours de route (ex. `FleshMetalGuns_TileEffectAbility` sur `On(0x10 = DamageDealt)`, #85)
        # ne l'arment PAS. Lire la tuile au moment du canal #179 (apres la boucle d'arme) armait le
        # coup la ou le natif ne l'arme pas -- MESURE : montage `case-159` WarpHail seeds 12345 et
        # 31337, live 6 coups d'arme + 2 coups du cycle, offline 6 + 1 + 2.
        _ltgb_tfx = (tile_status_effects_by_pos(state, [(tp.col, tp.row)])
                     if tp is not None else None)
        _ltgb_pd = persistent_data_keys(att)
        if ap is not None and tp is not None:
            # `trigger_ability_type` = l'`AbilityOrEffect` DECLENCHANTE de ce coup
            # (`AbilityEntities+0x98`), threadee ici depuis le MEME parametre qui alimente deja
            # `StaticBattleRules$$GetDamageSourceAbility`. Unique producteur cote port : le vecteur
            # OVERWATCH (`triggers/effect_triggers.py` -> `OVERWATCH_AUTO_ATTACK` = EffectType 1009).
            # Consommateur sur l'axe COUPS : `PurgeResponse` (1538), dont le trigger natif est
            # `TriggeringAbilityIs(EffectType 1009)` (case-366-r1-blockhits-purgeresponse).
            _board, _auras, _tgt_eff = build_hits_board(
                state, attacker_id, target_id, (ap.col, ap.row), (tp.col, tp.row),
                is_melee=not _ranged, trigger_ability_type=triggering_ability)
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
                defender_on_cover=_on_cover)
        else:                                     # positions manquantes -> base seule (pas de GetStuckIn/aura)
            hits = max(1, whits + ctx.stat(StatType.EXTRA_HITS) + hits_bonus_from_effects(active))
        if skip_hit_count_query:
            # #411 -- `AttackDamageOptions[+0x28]`. `IdunBattle.Operations.AttackDamageOperation$$
            # GetAttackHits` sort AVANT la requete de modificateurs quand cet octet est pose :
            #     if (options[+0x28] != 0) return <compte de base> ;
            # et le compte de base vaut `options[+0x18]` (`Nullable<int> hits`) ou **1** quand ce
            # Nullable est vide -- ce qui est exactement le cas du chemin de transfert, dont le
            # ctor `AttackDamageOptions$$.ctor(damage)` met tout a zero de +0x10 a +0x88.
            # Le coup transfere reste donc a 1 coup : ni LightCover -2, ni bonus d'effet, ni aura.
            hits = 1
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
        block_sources = AttackDamageOperation._block_sources(
            tsc, _def_active, armor, _profile,
            defender_max_health=int(getattr(thc, "hp_max", 0) or 0))   # #1015-r1 GetStat(5, Maximum)
        # ORDRE RÉEL (confirmé live 18/18 coups, 3 seeds, necroDestroyer 6h) : le HitDamage natif
        # porte la plage RÉDUITE — la réduction (perçage/armure/modifiers attaquant+défenseur) est
        # appliquée aux BORNES base±spread D'ABORD, puis le tirage `GetDamage` se fait DANS cette plage
        # réduite (next_internal(min_réduit, max_réduit+1)). PAS spread-brut-puis-réduit (qui donne la
        # bonne PLAGE totale mais de mauvaises valeurs par coup — le modulo dépend de la largeur).
        # CRIT — modèle CONFIRMÉ bit-exact (genrand brut live, necroDestroyer CC=100/CD=500 → 12 tirages
        # /6 coups : 1 crit-roll + 1 spread PAR COUP). Le crit du COMBAT n'est PAS l'`ApplyCritDamage`
        # post-réduction de la PRÉDICTION : il s'ajoute à la BASE D'ATTAQUE AVANT spread/perçage.
        # #986/#954-r3 — CHEMIN LU, et c'est le MÊME point de composition pour les DEUX familles :
        # `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` écrit
        #     `request+0x58 = Nullable<int>(isCrit ? CalculateCriticalDamage(D0) : D0)`
        # AVANT d'appeler `PredictAttack` (slot 4). `IdunBattle.Core.Services.DamagePrediction$$
        # PredictAttackRaw` relit ce champ (`Math.Max(0, GetValueOrDefault(request+0x58))`) puis
        # BRANCHE sur `request+0x6a` (= `AttackDamageOptions[+0x2f]`) :
        #     drapeau != 0 -> `GetBaseDamageFix64(D)`     # le SPREAD porte sur D, crit COMPRIS
        #     drapeau == 0 -> `MinMaxDamageFix64(D, D)`   # bornes dégénérées, AUCUN spread
        # `IdunBattle.Core.HitDamage$$GetDamage` dit lequel est lequel : `min == max -> return min`
        # (attaque NORMALE : options dégénérées, D0 = la stat d'attaque, aucun tirage) contre
        # `Next(min, max + 1)` (ABILITY : plage de config, D0 tiré) — d'où le vecteur ability qui
        # décale ses bornes brutes à plat (pas de spread à traverser), cf. `ability.py`.
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
        # `On(PreAttackHit=6)` — vecteur PER-COUP natif, emis par `IdunBattle.Operations.
        # AttackDamageOperation$$ExecuteHit` **APRES le `RollCritical` du coup** (#522-r1 : l'ordre
        # du decompile est slot 0xad profil -> `AttackHit..ctor` -> **slot 0xa `RollCritical`** ->
        # `AbilityEntities..ctor` -> `EnqueueOperation(6)` -> `EnqueueOperation(7)`). Son seul
        # consommateur porte (ThrillSeekers, branche « cible a pleine vie ») pose un stat-mod
        # CRIT_CHANCE : il ne doit donc PAS entrer dans la crit chance du coup 0, mais bien dans
        # celle des coups suivants -- `DamagePrediction$$RollCritical` relit `GetStat(9)` a chaque
        # appel, et `ExecuteHits` boucle sur `ExecuteHit`.
        # => on MESURE la crit chance AVANT l'event (celle du coup 0), on emet, puis on la RELIT.
        # `is_first_hit=True` = le coup 0 (le port n'a pas de boucle de coups au niveau trigger).
        crit_avant = AttackDamageOperation._crit_params(
            ctx, active, state, attacker_id, target_id,
            is_ranged=_ranged, is_normal_attack=True, hit_index=0)
        from ..triggers.dispatch.attack import pre_attack_hit_triggers  # lazy : cycle damage<->triggers
        pre_attack_hit_triggers(state, attacker_id, target_id, ranged=bool(_ranged),
                                profile=_profile, is_first_hit=True, ability_type=1013)
        # crit = GetStat(9/10) [DÉJÀ effet-inclusif : les effets StatModification sur la crit sont
        # cuits dans GetStat → dans le combatSnapshot → dans ctx] + couche calc-time SÉPARÉE
        # GetCritChanceBonusFromEffects/GetCritDamageBonusFromEffects (PAS dans GetStat → sommée ici
        # depuis les effets ACTIFS de l'attaquant). Mirror exact de RollCritical/CalculateCriticalDamage.
        # `state/attacker_id/target_id` = les IDENTITES du coup, threadees pour que la facade CRIT
        # construise son `att_ctx` (mirror de l'`AbilityEntities` que
        # `IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects` batit lui-meme a
        # partir de l'attaquant et de la cible). Le calcul du gate vit DANS `_crit_params`, pas ici.
        # `is_ranged`/`is_normal_attack` = la NATURE du coup, MEME valeur que celle passee a
        # `attacker_modifiers` ci-dessus (vecteur NORMALE : `_ranged` mesure, normal = True) ->
        # noeuds `IsMeleeAttack`/`IsNormalAttack` du canal CHANCE DE CRIT (case-366-r1).
        # RELECTURE post-event : ce sont les valeurs des coups 1+ (`crit_avant` reste celle du
        # coup 0). Hors ThrillSeekers les deux coincident -- aucun autre trigger porte n'ecoute
        # `On(6)`/`On(7)` (mesure #522-r1 : 1 seul ecouteur dans tout le registre).
        # `hit_index=1` : ces valeurs-la sont celles des coups 1+ (cf. `_roll_crit(idx)` de
        # `damage_hits.py`, qui bascule sur `crit_chance_after` des que `idx != 0`). Le port n'a que
        # DEUX points de mesure la ou le natif relit `GetCritChanceBonusFromEffects(..., hitIndex)` a
        # CHAQUE coup -- donc un `EffectBonus` qui discrimine un index >= 2 lirait `1` ici. Exact pour
        # toute serie de 1 ou 2 coups (le porteur du noeud, `TheLionsWrath`, a `nrOfHits = 2`) --
        # AU-DELA, c'est `crit_chance_at` ci-dessous qui rend l'index exact (#889-r1, RESOLU).
        crit_chance, crit_damage, crit_enabled = AttackDamageOperation._crit_params(
            ctx, active, state, attacker_id, target_id,
            is_ranged=_ranged, is_normal_attack=True, hit_index=1)
        crit_apres = (crit_chance, crit_damage, crit_enabled)

        def _crit_chance_at(_idx: int):
            """#889-r1 -- (chance, enabled) du canal CRIT A L'INDEX `_idx`, mirror de
            `DamagePrediction$$RollCritical(this, attaquant, defenseur, abilityOrEffect, hitIndex)`
            qui passe l'index a `GetCritChanceBonusFromEffects` a CHAQUE coup. Le port ne mesurait
            que deux points (0 et 1) : exact pour 1 ou 2 coups, faux au-dela des qu'un `EffectBonus`
            discrimine un index >= 2 (noeud `CurrentHitIndex()`).

            Rend UNIQUEMENT la chance et le gate : `CalculateCriticalDamage` appelle
            `GetCritDamageBonusFromEffects(this, attaquant, defenseur, abilityOrEffect)` **sans**
            `hitIndex` -- le canal crit-DEGAT n'est pas index-dependant, il n'est donc pas relu ici.

            Etat lu = le MEME que celui de `crit_apres` (post-`On(6)`, `state` non mute pendant
            `_run_hits`), donc l'appel a l'index de reference rendrait la meme valeur -- c'est
            pourquoi `_roll_crit` ne l'appelle pas pour cet index-la."""
            _cc, _cd, _en = AttackDamageOperation._crit_params(
                ctx, active, state, attacker_id, target_id,
                is_ranged=_ranged, is_normal_attack=True, hit_index=int(_idx))
            return (_cc, _en)
        crit_chance, crit_damage, crit_enabled = crit_avant
        # #922 -- LA CRIT CHANCE ET LA CRIT DAMAGE N'ONT PAS LA MEME PLACE DANS `ExecuteHit`, et
        # c'est LU : l'ordre du decompile est slot 0xad (profil) -> `AttackHit..ctor` -> slot 0xa
        # **`RollCritical`** -> `AbilityEntities..ctor` -> `EnqueueOperation(6)` ->
        # `EnqueueOperation(7)` -> slot 0xb **`CalculateCriticalDamage`** -> sub-op 0x42 ->
        # `EvaluateAfterHitTriggers`. `On(6)` tombe donc ENTRE les deux : ce qu'il pose ne mord pas
        # sur le tirage de crit du coup 0 (d'ou `crit_avant` pour la CHANCE), mais mord bien sur sa
        # MAGNITUDE (d'ou `crit_apres` pour la DAMAGE) -- coup 0 COMPRIS.
        # MESURE (#922, porteur `emperKakophonist` + relique `IntoxicatingElixir`, cible a pleine
        # vie -> `ThrillSeekersAbility` rend le porteur `Thrilled` a son propre coup 0, ce qui fait
        # passer le compteur de la relique de 0 a 1) : live `[6996, 6221, 5998]` contre port
        # `[6534, 4621, 5010]` AVANT ce correctif -- les TROIS coups divergeaient, le 0 compris.
        # STRICT NO-OP partout ailleurs : les deux mesures ne different que si un ecouteur d'`On(6)`
        # change la crit DAMAGE, et il n'en existait aucun avant cette tranche.
        crit_damage = crit_apres[1]
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
            # #986 : la citation JUSTE est desormais ecrite plus haut (`request+0x58` pose par
            # `ExecuteHit`, relu par `PredictAttackRaw`), et le placement est confronte live sur
            # les DEUX vecteurs par un discriminant SANS PARAMETRE — la LARGEUR de la plage :
            # `probe_986_crit_place_vs_spread.py` (normale : largeur non-crit 217 -> etendue
            # critique 1742 ; ability : 154 -> 151). Garde : `test_986_crit_place_vs_spread_offline`.
            _extra_max = int(ctx.stat(StatType.EXTRA_MAX_DAMAGE) or 0) if _ranged else 0
            mm = get_base_damage_fix64(eff_attack, extra_max=_extra_max, spread_pct=spread_pct)
            # UN `Round` PAR FACE (#437-r1) : `CalculateBaseDamageWithAllModifiers` appelle
            # `CalculateBaseDamageWithModifiers` UNE FOIS PAR ACCUMULATEUR non nul, donc la face
            # défenseur part d'une valeur DÉJÀ matérialisée. Mesuré sur le tir d'overwatch
            # `HeavyWeapon_ExtraDmg` x1.25 / `TerminatorArmour_ReduceDmg` x0.25 : bornes natives
            # INVERSÉES depuis l'aléa brut = (1130, 1695), la chaîne unique rendait (1129, 1694).
            # Depuis #437-r1-r1-r1 la séparation est INCONDITIONNELLE dans
            # `apply_pierce_and_modifiers` (le drapeau `separate_face_lists` a été retiré) : ce
            # qu'il compensait était une ATTRIBUTION DE FACE, désormais lue par effet.
            lo = apply_all_modifiers(apply_pierce_and_modifiers(
                mm.min + flat_add, pierce, armor, mods, hit_mult=hit_mult,
                attacker_additive_pre=True),
                def_mods, round_materialize=True)
            hi = apply_all_modifiers(apply_pierce_and_modifiers(
                mm.max + flat_add, pierce, armor, mods, hit_mult=hit_mult,
                attacker_additive_pre=True),
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
        # #1013 : SECONDE branche d'`IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage`
        # (`HasTriggeredAbility(1494 ParagonSpear)`), gatee PAR COUP sur `isCritical` -> elle ne
        # peut pas degenerer les bornes en amont ; on la transmet a `_run_hits`. Le predicat lit
        # le KIT DECLENCHE de l'ATTAQUANT, pas l'ability qui frappe : TOUT coup critique du
        # porteur de la lance est maxe, son attaque normale comprise.
        _max_out_crit = AttackDamageOperation._max_out_on_crit(state, attacker_id)
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
        # #366-r1 : les DEUX accroches per-coup d'`IdunBattle.Operations.AttackDamageOperation$$
        # ExecuteHit(s)` -- `On(6 = PreAttackHit)` -> relecture du flag `discard` de l'`AttackHit`
        # courant, et `On(0x3c = UnitBlocked)` -> `RegisterBlocks`. Le bus du port emet ces deux
        # vecteurs UNE FOIS PAR ATTAQUE (`dispatch/attack.py`) ; le cluster HarlequinsPanoply, lui,
        # est per-COUP et sans gate `IsFirstHitInSeries`. Cf. `triggers/loki/harlequins_panoply.py`.
        from ..triggers.loki.harlequins_panoply import make_hit_interceptor   # lazy (cycle)
        _hit_icept = make_hit_interceptor(state, attacker_id, target_id)
        # #1020-r4 : le chokepoint `On(0x39 = EventTriggerType.PreDamageTaken)` joue DANS la boucle,
        # a sa position dans le flux PRNG (cf. `damage_hits._run_hits`, bloc `POSITION DU TIRAGE`).
        # La phase d'arme est la PREMIERE serie de l'attaque -> aucun degat inflige avant elle.
        _first_damaging = True
        # #1020-r3 x #1020-r4 : le canal `AbilityEntities+0x98` doit suivre l'emission LA OU ELLE
        # A LIEU. Elle a migre dans la boucle, donc `source_ability` est resolu ICI, avant, et la
        # MEME valeur part au sink et au chokepoint (le rebase qui le laisserait au seul chokepoint
        # rendrait les `TriggeringAbilityIs` aveugles pour ce vecteur, sans erreur).
        # `GetDamageSourceAbility(currentAbility = l'attaque normale, triggeringAbility)` : la voie
        # NORMALE porte le marqueur de kind 0x3f5 comme `currentAbility` (cf. `attack_type.py`).
        _src_ability = AttackDamageOperation._damage_source_ability(
            _normal_attack_kind(), triggering_ability)
        _pdt_sink = AttackDamageOperation.make_pre_damage_taken_sink(
            state, attacker_id, target_id, thc, _profile, is_first_damaging_hit=_first_damaging,
            source_ability=_src_ability)
        r = AttackDamageOperation._run_hits(state.rng, hit_nc, hit_cr, crit_chance,
                                            crit_enabled, hits, block_sources, shield=shield_total,
                                            # #522-r1 : crit chance RELUE apres `On(PreAttackHit)`
                                            # -> coups 1+ seulement (le coup 0 garde `crit_avant`).
                                            max_out_on_crit=_max_out_crit,
                                            crit_chance_after=crit_apres[0],
                                            crit_enabled_after=crit_apres[2],
                                            # #889-r1 : axe INDEX (distinct de l'axe TEMPOREL
                                            # ci-dessus) -- `RollCritical(..., hitIndex)` relit le
                                            # canal a CHAQUE coup. Appelee seulement pour un index
                                            # que `crit_apres` ne couvre pas (cf. `_roll_crit`).
                                            crit_chance_at=_crit_chance_at,
                                            bonus_hit_chance=_gsi, hit_interceptor=_hit_icept,
                                            capped_reductions=def_mods.capped_reductions,
                                            # #67 : etage limites (member-cap/Resilient/bypass Blast) —
                                            # mode 1 = attaque (wrapper IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToAttackDamage/IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToAttackDamage)
                                            limits=AttackDamageOperation._target_limits(
                                                tgt, thc, _profile, is_special=1),
                                            limits_hp=int(thc.hp or 0),
                                            # #462-r4e-o : PV COURANTS + plancher, pour que `per_hit`
                                            # porte le tag `Amount` de l'event (retraits REELS) et non
                                            # le degat demande. `hp` None -> None (aucune borne).
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
                                            pending_sink=_pdt_sink)     # #1020-r4
        # #1020-r1 : plus de `_deplete_shield` ICI. `ApplyDamageOperation$$ReduceShield` lit le
        # pending RELU (apres `On(0x39)`), donc la depletion vit dans le chokepoint, avec `Reduce`.
        death = AttackDamageOperation._apply_damage_pipeline(           # chokepoint partage (#202)
            state, target_id, attacker_id, tgt, thc, r["total"], _profile,
            r["shield_dmg"], r["armor_dmg"],
            source_ability=_src_ability,   # #1020-r4 : la MEME que celle donnee au sink
            last_hit=(r["per_hit"][-1] if r.get("per_hit") else None),
            # #R33 : decomposition per-coup (crit / denied) pour `didOverkill` — le natif evalue
            # `IsOverkill` A CHAQUE coup. L'attaque normale n'a pas de flag `isForceOverkill`
            # (`AttackOptions@+4` n'est pose que par la voie DSL `AttackWithAttackDamage`).
            hits_result=r,
            # `On(0x10)` : la PHASE D'ARME contient le coup d'index 0 -> `IsFirstHitInSeries` VRAI
            # (payload `AbilityEntities+0x110`, lu par `OnToxicDamageAbility`).
            is_first_hit=True,
            # #1020-r4 : MEME etat que celui donne au `pending_sink` ci-dessus. Il n'est plus lu
            # quand le sink a joue (`r["pre_damage_taken"]` non nul), mais l'ecrire ici garde les
            # deux chemins apparies -- le repli implicite sur `is_first_hit` masquerait un ecart.
            is_first_damaging_hit=_first_damaging,
            pre_damage_taken=AttackDamageOperation.pre_damage_taken_of(_pdt_sink))
        # #202-B : coups additionnels HETEROGENES (canal #179, face COMBAT) — sous-operations APRES
        # les coups d'arme (mirror IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute), chacune son RegisterDamage au profil PROPRE.
        _ah = execute_additional_hits(
            state, attacker_id, target_id, tgt, thc,
            collect_additional_hit_groups(
                state, attacker_id, target_id, active, not _ranged, _def_active,
                # #227 `LetTheGalaxyBurn` : le canal #179 (et NON la formule de coups) porte son
                # « +1 coup ». Le degat du groupe = `FirstHitInCurrentAttackDamageRange` = le
                # `HitDamage` BRUT de l'AttackData de CETTE attaque, qui est DEGENERE pour une
                # attaque normale (c'est ce qui donne 1 tirage/coup, cf. `_one_hit`) : la base
                # d'attaque, AVANT spread/percage. Le gate lit la tuile de la cible
                # (`HasTileStatusEffect`) et le flag pose par `On(PreAttack=5)` juste au-dessus.
                attack_hit_damage=(int(ctx.stat(StatType.ATTACK)), int(ctx.stat(StatType.ATTACK))),
                t_pos=(tp.col, tp.row) if tp is not None else None,
                # snapshot PRE-attaque (cf. le bloc `_ltgb_tfx` plus haut) : la tuile figee.
                tile_effects_by_pos=_ltgb_tfx, persistent_data=_ltgb_pd,
                # #204 `MasterAnnihilator_AdditionalHitEffect` : noeud
                # `AreEqual(CurrentAttackDamageProfile, 0xd = Psychic)` du gate.
                damage_profile=_profile,
                # #1006 `Maugetar_HasNotMovedEffect` : `AttackDamageIsCritical`. Le natif recopie
                # `hitGroup+0x3d` dans l'`AbilityEntities` juste avant d'appeler
                # `GetAdditionalHitsFromEffectsInternal` (cf.
                # `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamage
                # ProfileType`) -- c'est l'etat du groupe d'ARME qu'on vient de resoudre, donc il
                # se lit sur `r`, JAMAIS sur un tirage a venir. `r["crits"]` est index-aligne sur
                # les coups EXECUTES (`damage_hits.py`), coups bonus compris.
                attack_had_critical=any(r.get("crits") or ())),
            mods, def_mods, armor, _tgt_hit_mult, block_sources, shc,
            spread_pct=spread_pct, extra_pierce=ctx.extra_pierce,
            # profil de l'ATTAQUE : ce qu'emprunte un groupe dont le `profileType` est NULL.
            attack_profile=_profile,
            # R6-b' : `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` est la
            # DERNIERE instruction de CHAQUE `IdunBattle.Operations.AttackDamageOperation$$
            # ExecuteHit` -- y compris ceux des sous-operations de groupe, qui partagent
            # l'`OngoingAttack` (donc son compteur `+0x30`) via `GetCurrentAttackOrDefault`.
            # On THREADE le meme `bonus_hit_chance` et l'index de sortie de la phase d'arme
            # (`next_hit_index`, coups bonus compris) : un seul site d'evaluation du `Maybe`.
            bonus_hit_chance=_gsi, hit_index0=r["next_hit_index"],
            # #366-r1-crit-multihit : `attack[+0x40] &= hitGroup[+0x3c]` -- l'etat
            # `isCriticalDamageAllowed` sort de la phase d'arme et entre dans les groupes.
            crit_allowed0=r["crit_allowed"],
            # #407 : le JUMEAU BLOCK -- `OngoingAttack+0x48` (`FailedBlockIds`), seme par reference
            # dans `OngoingHitGroup+0x60` par `ADamageOperation$$SetupHitGroup` et alimente par
            # `RegisterBlocks`. Une source ayant echoue en phase d'arme reste EXCLUE des groupes.
            failed_block0=r["failed_block"],
            # #963-r2 : TROISIEME etat de portee ATTAQUE (`isFirstDamagingHit`, `AbilityEntities
            # +0x118`) -- la phase d'arme a-t-elle deja inflige du degat ? A ZERO (salve entierement
            # bloquee), le flag revient au PREMIER groupe additionnel qui damage, comme le natif.
            damaging_done0=int(r["total"] or 0) > 0,
            hit_interceptor=_hit_icept)      # #366-r1 : meme attaque -> meme intercepteur per-coup
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
        # `On(FinalDamage = 0x42 = 66)` — emis par `IdunBattle.Operations.ADamageOperation$$
        # RegisterFinalDamage`, dont les xrefs sont EXHAUSTIVES : `IdunBattle.Operations.
        # AttackDamageOperation$$Execute` (ici) et `IdunBattle.Operations.AbilityDamageOperation$$
        # Execute` (cf. `execute_ability_attack`) — donc UNE fois par ATTAQUE / par degat d'ability,
        # JAMAIS pour un DoT ni un knockback. Place a la SORTIE de l'operation d'attaque, donc APRES
        # les coups additionnels (le compteur `received_damage_this_turn` que lisent ses consommateurs
        # est deja incremente) et AVANT `On(9)`/`On(10)` de `FinishAttackOperation`.
        # lazy. Forme MODULE, meme raison qu'au site de `pre_unit_ability_triggers` ci-dessus :
        # `finish_attack_triggers` est SUBSTITUE par `probe_437*` -- un hissage en forme
        # `from ... import` desarmerait ces mesures en silence.
        from ..triggers.dispatch import attack as attack_dispatch
        # #366-r1 : retrait du marqueur 1227 a la CLOTURE de l'attaque, MEME place que `On(9)`/`On(10)`
        # (les deux events de `FinishAttackOperation$$Execute`) et pour la MEME raison : une attaque
        # declenchee par un trigger (overwatch) ne traverse pas le niveau MESSAGE.
        # IDEMPOTENT avec `EFFECT_TRIGGERS[1227]`. Cf. `HitInterceptor.finish`.
        if _hit_icept is not None:
            _hit_icept.finish()
        attack_dispatch.final_damage_triggers(state, attacker_id, target_id,
                                             ranged=bool(_ranged), profile=_profile)
        # `On(Attack = 9)` (#437) — 1er event de `FinishAttackOperation$$Execute`, INCONDITIONNEL, et
        # emis ICI (sortie de l'operation) et non plus au niveau MESSAGE. Le foyer natif est le noeud
        # DSL `Attack(...)` (`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` : StartAttack
        # slot 0x3a -> inner -> FinishAttack slot 0x3b), que l'attaque normale traverse
        # (`ALoki_NormalAttackAbility$$GetAttackDamageBehaviour` se termine par
        # `IdunBattleLogic.Entities.DSLBehaviors$$Attack(...)`) -- DONC AUSSI le tir d'overwatch, qui
        # est `UseActiveAbility(NormalAttack)`. Emis AVANT `On(10)` : c'est l'ordre du natif.
        # `profiles` = arme + coups bonus #179 ; `health_damage` = `HealthDamageFromEvent()` (part
        # SANTE seule -- `_deplete_shield` a defalque le bouclier avant l'agregation) ; `was_block` =
        # `WasBlock()`. Ces trois canaux sont les conjoints de `TerminatorArmour_ReduceDmg_Effect$$
        # CreateTargetTrigger` (#432) : avant #437 ils n'etaient threades que par la voie MESSAGE,
        # donc un tir d'overwatch ne consommait pas l'armure alors que le natif la consomme.
        _fa_profiles = {_profile} - {None}
        _fa_profiles |= set((_ah or {}).get("profiles") or [])
        _fa = attack_dispatch.finish_attack_triggers(
            state, attacker_id, target_id,
            ranged=bool(_ranged), profile=_profile,
            is_crit=bool(r["did_crit"]), profiles=_fa_profiles,
            health_damage=int(r["total"] or 0),
            was_block=bool(r["did_block"]))
        attack_dispatch.attack_damage_attack_triggers(
                                      state, attacker_id, target_id,
                                      ranged=bool(_ranged), profile=_profile,
                                      # vecteur NORMAL : `IsNormalAttack(CurrentAbility@0x88)` VRAI,
                                      # MEME donnee que le `is_normal_attack` (defaut True) passe a
                                      # `attack_hits_with_modifiers` par cette meme facade.
                                      is_normal_attack=True,
                                      triggering_effect=state.trigger_ability_type)
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
                # #419-r1-tr14-r4-r2-r1 : les tags que `ExecuteInformWeapon` a poses pour CETTE
                # attaque. Canal d'OBSERVATION du port (le runner Python n'a pas de
                # `StreamDispatcher` : la face qui ECRIT le flux est `engine.streams`, alimentee
                # par des canaux independants). Les valeurs, elles, sont celles du natif -- c'est
                # ce que confronte `probe_419r1tr14r4r2r1_normal_attack_inform_weapon.py`.
                "inform_weapon_tags": _iw_tags,
                "additional_hits": _ah,          # #202-B : sous-operations #179 (None = aucun groupe)
                # #437 : les resultats du vecteur `On(9)` emis ci-dessus. CANAL DE DIAGNOSTIC pur --
                # avant #437 ils remontaient dans `DamageHandler.after_hit` (le vecteur vivait au
                # niveau MESSAGE). Les appelants qui exposent `after_hit` les remettent EN TETE,
                # ce qui est aussi l'ordre natif (`FinishAttack` precede l'`ExecuteTriggerAbilities`
                # qui porte `On(0x26)`). Sans ce canal, un trigger `On(9)` FIRE sans etre observable.
                "finish_attack": _fa,
                # #419-r3 : l'etat de l'`OngoingAttack` EN SORTIE de l'attaque primaire (`+0x30`,
                # `+0x40`, `+0x48`). C'est ce que lit toute feuille `IdunBattleLogic.Entities.
                # DSLBehaviors$$AttackDamage` NUE composee APRES elle dans le MEME `Attack(...)` --
                # au premier chef le FOLD de `<X>_NormalAttackAbility$$GetCustomNormalAttackBehaviour`,
                # que `ALoki_NormalAttackAbility$$GetAttackDamageBehaviour` compose entre les coups
                # d'arme et `ExecuteAdditionalHitsWithDamageProfileType`.
                "attack_state": _attack_state_out(r, _ah),
                "effects": [getattr(e, "name", None) for e in active]}
