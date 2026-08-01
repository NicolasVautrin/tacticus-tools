"""Vecteur d'ATTAQUE D'ABILITY (`_DamageOpsMixin.execute_ability_attack`), extrait d'
`operations/damage_ops.py` (scission du module >1000 lignes, tache #169 -- deplacement
VERBATIM, zero changement de comportement).

Mirror `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` /
`$$AttackWithAbilityDamage` -> `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit`.

PATCH-POINT (tests/probes) : `execute_ability_attack` resout `apply_all_modifiers` ET
`hits_channel_is_melee` dans les globals de CE module -- un patch pose sur le `__init__` du
package serait un NO-OP SILENCIEUX. Patcher `damage_ops.ability.<nom>`.
"""
from __future__ import annotations

from ....services.damage_prediction import apply_pierce_and_modifiers
from ....services.damage_modifiers import apply_all_modifiers, DamageModifiers
from ....services.attack_hits_formula import attack_hits_with_modifiers
from ....entities.stats import StatType
from ...state import State
from ...components import (StatsComponent, HealthComponent, PositionComponent,
                           persistent_data_keys, unit_prevents_overkill, unit_state_for_effects)
from ...damage_model import (attacker_modifiers, defender_modifiers, build_hits_board,
                             apply_elevation_bonus, apply_trench_reduction,
                             ice_crit_damage_addition, target_trait_names,
                             getstuckin_combat_chance, defender_fixed_armor,
                             tile_status_effects_by_pos)
from ....entities.effects.loki import LIGHT_COVER_TILE_ID
from ....entities.traits import target_hit_multiplier
from ..additional_hits import collect_additional_hit_groups, execute_additional_hits
from ..damage_hits import HitDamage
from ._channel import hits_channel_is_melee


class _AbilityAttack:
    """Vecteur d'attaque d'ABILITY. Sans etat (staticmethod) ; agrege par `_DamageOpsMixin`."""
    __slots__ = ()

    @staticmethod
    def execute_ability_attack(state: State, attacker_id: int, target_id: int,
                               base_min: int, base_max: int, profile_pierce: int,
                               hits: int, damage_profile: Optional[str] = None,
                               is_melee: Optional[bool] = None,
                               ability_type: Optional[int] = None,
                               is_attack_damage_op: bool = True,
                               force_overkill: bool = False,
                               force_crit: bool = False,
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
        sans replay de dégât. Un replay de DÉGÂT doit caler rng (dumpRng) avant le cast.

        `force_crit` : flag « always crit » du `Nullable<AttackOptions>` d'`AttackWithAttackDamage`
        (octet +5 de la struct, cf. `_run_hits`). Le natif saute `RollCritical` -> crit ACQUIS sans
        tirage, MEME quand `CouldCrit` est faux (cc = 0). Ici : (a) les bornes crit `hit_cr` sont
        construites même si `crit_enabled` est faux, (b) `_run_hits` force `crit=True` par coup sans
        consommer de RNG. Défaut False = comportement historique strictement inchangé.

        `round_materialize` : REDONDANT depuis la campagne HeavyGravCannon (2026-07-26) — l'étage
        `Fix64.Round(·, AwayFromZero)` est désormais INCONDITIONNEL sur ce vecteur (cf. `_round_mat`
        plus bas). Conservé pour la signature des callers existants ; ce n'est plus un knob."""
        from ..damage import AttackDamageOperation  # lazy : rompt le cycle damage<->damage_ops
        # GARDE-FOU rng (PAS un mirror natif) : sans `state.rng` cale (replay effet-seul, etat
        # `load_state` sans dumpRng) on SKIP au lieu de lever. RAFFINE a la migration du DoT de tuile :
        # ce vecteur ne consomme un tirage QUE si (a) les bornes sont non degenerees (`HitDamage$$
        # GetDamage` gate min==max), (b) un crit peut etre roule, (c) une source de block existe, ou
        # (d) le resolve slot-8 GASPILLE de la famille ATTACK tourne (`is_attack_damage_op`). Un DoT de
        # tuile (amount FIXE, famille ABILITY, cible sans block) est 0-tirage : le skipper le rendrait
        # NO-OP hors runner, ce qu'il n'etait pas sur la route `execute_direct`. Les deux termes
        # connus ici gardent l'entree ; les deux autres sont testes juste avant `_run_hits`.
        if state.rng is None and (int(base_min) != int(base_max) or is_attack_damage_op):
            return None
        att = state.get_entity(attacker_id)
        tgt = state.get_entity(target_id)
        sc = att.get_component(StatsComponent) if att is not None else None
        thc = tgt.get_component(HealthComponent) if tgt is not None else None
        if thc is None:
            return None
        # CASTER NON-UNITE (entite TUILE) — `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`
        # resout son champ +0x50 (le CASTER) en UNE entite qui n'est PAS forcement une unite : le DoT
        # de tuile (`IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour`)
        # passe `Tiles(<occupant>)` en caster, donc l'entite-TUILE. Elle n'a ni `StatsComponent` ni
        # `HealthComponent` (le port ne la materialise meme pas dans `State.entities` : la cle d'une
        # tuile ne vit que dans `EffectsState`). Le natif s'en accommode parce que la famille ABILITY
        # (`IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit` ->
        # `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`) recoit des mods
        # ATTAQUANT **VIDES** (struct zeroee, MESURE #45f probe_217) : aucune stat du caster n'entre
        # dans le calcul. On mirror : `sc is None` -> mods attaquant vides + crit inexistant, au lieu
        # d'abandonner. La CIBLE, elle, reste obligatoire (`thc`). INERTE pour tous les appelants
        # historiques (leur caster est une unite -> `sc` non nul -> chemin inchange).
        ctx = sc.ctx if sc is not None else None
        ahc = att.get_component(HealthComponent) if att is not None else None
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
        #   - `target_traits` (case HeavyGravCannon) : les gates `HasTrait(target@0x178, X)` lisent la CIBLE
        #     du contexte d'attaque, que le natif remplit sur TOUT vecteur -- il n'y a qu'UN collecteur
        #     (`IdunBattle.Entities.Effects.BaseEffect$$DamageBonusForAttack`), pas un par famille. Ce site
        #     ne le threadait PAS (seule l'attaque NORMALE le faisait, damage_ops `execute`) -> tout bonus
        #     target-conditionnel etait MORT sur la voie ability. GROUND TRUTH (case-101 §3.2, cast
        #     SentinelDirectives = vecteur ABILITY famille ATTACK) : live 3510 - offline 3067 = +443 =
        #     `extraDmg[50] x 160%` de `HeavyGravCannon`, dont la condition est precisement
        #     `HasTrait(target, 5=Mechanical)` -> le natif EVALUE bien les traits de la cible ici.
        #     Meme gate FAMILLE que `is_ranged`/`trigger_ability_type` : la famille ABILITY recoit des mods
        #     attaquant VIDES (#45f) -> None hors `is_attack_damage_op` (comportement inchange).
        _ranged = (not is_melee) if (is_melee is not None and is_attack_damage_op) else None
        _tgt_traits = target_trait_names(state, target_id) if is_attack_damage_op else None
        if sc is None:
            # caster NON-UNITE (tuile) : mods attaquant VIDES == ce que `CalculateAbilityDamage`
            # recoit (mesure #45f). On NE passe PAS par `attacker_modifiers`, dont la collecte
            # `state.effects.active_effects(<id de tuile>)` rendrait les effets DE LA TUILE (le FEU
            # lui-meme) comme s'ils etaient des effets d'ATTAQUANT.
            mods, active = DamageModifiers(), []
        else:
            mods, active = attacker_modifiers(state, attacker_id, ahc.hp if ahc else None, target_id=target_id,
                                              is_ranged=_ranged, is_normal_attack=False,
                                              target_traits=_tgt_traits,
                                              # `DamageProfileIs(...)` -- meme collecteur unique
                                              # (`BaseEffect$$DamageBonusForAttack`) que `target_traits`
                                              # ci-dessus, donc MEME gate FAMILLE : threade pour la
                                              # famille ATTACK, None pour la famille ABILITY (dont les
                                              # mods attaquant sont zeroes, #226). Consommateur porte :
                                              # `PsychicStalk_FriendlyChaosExtraDamage` (#366-r1, 1435),
                                              # dont le trigger n'a AUCUN gate `IsNormalAttack`.
                                              damage_profile=(damage_profile if is_attack_damage_op else None),
                                              trigger_ability_type=(ability_type if is_attack_damage_op else None))
            # #226 — STRUCT ATTAQUANT ZEROEE POUR LA FAMILLE ABILITY (generalisation de la mesure #45f,
            # desormais LUE AU DECOMPILE). `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`
            # ne construit QUE les mods DEFENSEUR (slot d'interface 0xf) et passe a
            # `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` un
            # `DamageModifiers` ATTAQUANT **memset a 0** (`local_498..uStack_460 = 0` juste avant l'appel) :
            # il n'existe AUCUN appel a `CalculateAttackerModifiersForPrediction` sur ce vecteur. #45f avait
            # deja gate les feuilles POSITIONNELLES (elevation/trench) et les threads `is_ranged`/
            # `trigger_ability_type`/`target_traits` sur cette base, mais les bonus attaquant issus des EFFETS
            # NON GATES (et les auras alliees) continuaient de passer -- invisible tant qu'aucun porteur
            # ability-family n'en avait.
            # DISCRIMINANT MESURE (#226, HammerOfWrath / `bloodIntercessor` Mataneo, porteur du trait
            # `RapidAssault` -> effet 1229 `ForPercentIncrease(get_OwnerIsCaster, 25)` SANS aucun gate) :
            # offline = round(live x 1.25) sur les 4 coups des DEUX volets (main 1930/1544, 2144/1715 ;
            # splash 2309/1847, 2415/1932) ; struct zeroee -> bit-exact.
            if not is_attack_damage_op:
                mods = DamageModifiers()
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
        # `On(PreAttack=5)` SUR LE VECTEUR ABILITY (famille ATTACK) — MEME raisonnement que le canal
        # #179 plus bas : le natif n'a QU'UNE `IdunBattle.Operations.AttackDamageOperation$$Execute`,
        # empruntee par l'attaque NORMALE et par toute ability `AttackWithAttackDamage` (case-61 §1.2),
        # et c'est ELLE qui emet l'event 5 avant `GetAttackHits`. Le port ne l'emettait que dans
        # `execute` -> 2e branche du meme fork de port.
        #   REFUTE le residu case-61 §6 (« `On(PreAttack=5)` n'est pas emis par le vecteur ability ->
        #   `LetTheGalaxyBurn` ne peut s'armer que par sa branche `TargetHasTileEffect` »), qui n'avait
        #   jamais ete mesure. MESURE (probe_61d_frenzy_aoe_combat, `blackObliterator` porteur du trait
        #   `LetTheGalaxyBurn`, cast de FrenziedFiring 1036, roster TEMOIN sans modificateur de coups) :
        #   le natif applique **+1 coup sur une PARTIE des cibles, et la partie CHANGE d'un run a
        #   l'autre a geometrie identique** (k=3 : {77:4,79:1,81:1,83:1} puis {77:5,79:2,81:2,83:1}) =
        #   signature d'un chance-gate par attaque -- exactement le `Maybe(ConfigConst(0x2a))` de
        #   `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger`
        #   (`On(5) & OwnerIsCaster & Maybe(chance) & !HasTileStatusEffect(TargetTiles@0x190)`).
        #   Emis ICI = AVANT le canal de coups (qui relit le flag via `attacker_persistent_data`) et
        #   avant tout degat, comme le natif. `ability_type` threade (l'`AbilityOrEffect` du coup).
        #   COUT pour une unite NON porteuse : nul -- aucun autre trigger porte n'ecoute l'event 5
        #   (cf. `pre_attack_triggers`), donc 0 conso RNG et 0 mutation.
        from ..triggers.dispatch import pre_attack_triggers       # lazy : cycle damage<->triggers
        if is_attack_damage_op:
            pre_attack_triggers(state, attacker_id, target_id,
                                ranged=not bool(is_melee) if is_melee is not None else False,
                                profile=damage_profile, ability_type=ability_type)
        # `On(PreAttackHit=6)` — `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit` emet le MEME
        # trio d'events {6, 8, 0x3d} que la voie normale (verdict RE #147/#150), donc ThrillSeekers se
        # declenche aussi sur une attaque d'ABILITY du porteur contre une cible a pleine vie.
        from ..triggers.dispatch import pre_attack_hit_triggers   # lazy : cycle damage<->triggers
        pre_attack_hit_triggers(state, attacker_id, target_id,
                                ranged=not bool(is_melee) if is_melee is not None else False,
                                profile=damage_profile, is_first_hit=True, ability_type=ability_type)
        # Identites du coup -> `att_ctx` du canal CRIT, bati DANS `_crit_params` (foyer unique, mirror
        # de l'`AbilityEntities` de `GetCritDamageBonusFromEffects`). Le gate famille ABILITY juste
        # en-dessous remet (0,0,False) : ce vecteur-la n'a AUCUN chemin crit natif.
        crit_chance, crit_damage, crit_enabled = (
            AttackDamageOperation._crit_params(ctx, active, state, attacker_id, target_id,
                                               is_ranged=_ranged, is_normal_attack=False)
            if ctx is not None else (0, 0, False))
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
        #
        # CAMPAGNE HeavyGravCannon (2026-07-26) -- la famille ATTACK **AUSSI**, mesure faite. Elle etait restee
        # TRONQUANTE avec la note « suspects du meme ±1, campagne de mesure propre a faire avant de
        # basculer » (`apply_all_modifiers`, residu nomme) : les validations bit-exact historiques de ce
        # vecteur portaient toutes sur un regime NON DISCRIMINANT, ou la valeur finale est ENTIERE. Elle
        # ne peut etre FRACTIONNAIRE que si les DEUX %-list (attaquant ET defenseur) sont vides -- sinon
        # `IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers` arrondit deja en fin
        # d'appel -- ET que la branche PERCAGE du plancher `max(0, d - armure, d x pierce%)` l'emporte.
        # Le canal percage de `HeavyGravCannonEffect` (+extraPierceRatio=60 sur un profil a
        # PiercingRatio=1) fabrique exactement ce regime.
        # CAMPAGNE (probe_hgc_1291 --case round, SentinelDirectives = ability bounds-mode famille ATTACK,
        # 14 casts / 2 regimes d'armure, une seule variable = la materialisation finale) :
        #   armure 2411 (adeptMorvenn) : d=4976 exact 3305.59 floor 3305 round 3306 -> live **3306**
        #                                d=4812 exact 3205.55 floor 3205 round 3206 -> live **3206**
        #                                d=4839/4554/4480/4905 frac .02/.17/.03/.28 -> floor==round==live
        #   armure 2008 (necroWarden)  : 8 casts, frac 0 ou < .5 -> floor==round==live (temoin : PAS de
        #                                +1 systematique, ce qui refute l'hypothese « additif oublie »)
        # => live == Round(AwayFromZero) 14/14, live == floor 12/14, les 2 ecarts tombant EXACTEMENT sur
        # les tirages a partie fractionnaire >= .5. C'est l'etage `Fix64.Round(Mul(v, multiplier),
        # AwayFromZero)` de `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`
        # (slot 0x10), INCONDITIONNEL des qu'un `Nullable<DamageModifiers>` HasValue.
        # STRICTEMENT NO-OP hors de ce regime (valeur deja entiere -> Round == floor == identite).
        # `execute_normal_like` et `additional_hits` restent tronquants : PAS de mesure sur eux (backlog).
        _round_mat = True

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
        # `_crit_materialized` = « ce vecteur peut produire un coup CRITIQUE » : soit la voie normale
        # (`CouldCrit` -> roll), soit le flag `force_crit` (options+5) qui rend le crit ACQUIS SANS
        # roll. Le natif ne consulte `CouldCrit` que pour DECIDER DU TIRAGE ; le montant de crit, lui,
        # sort de `CalculateCriticalDamage` des que `isCrit` est vrai -> les bornes crit doivent
        # exister dans les deux cas (a cc = 0, `crit_enabled` est faux : c'est TacticalPrecision).
        _crit_materialized = bool(crit_enabled or force_crit)
        _ice_add = ice_crit_damage_addition(state, attacker_id, target_id, ctx) if _crit_materialized else 0
        hit_cr = HitDamage(base_min + crit_damage + _ice_add,
                           base_max + crit_damage + _ice_add) if _crit_materialized else hit_nc
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
        # #122 : `is_melee` de la formule = `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack`, que
        # `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` appelle sur l'`AbilityOrEffect` de
        # l'AttackData -- donc la nature **DECLAREE** (`attackRangeType`) de l'ability, PAS l'adjacence
        # (seul `rangeType = Normal` est positionnel, non porte). Foyer unique : `hits_channel_is_melee`
        # ci-dessus, qui documente la table de verite native. Le port recalculait ici la nature
        # POSITIONNELLEMENT (`_is_ranged_position`) -> 3e fork de `IsMeleeAttack` (apres #101/#106) :
        # une ability RANGED castee au contact taisait `Camouflage_HitReduction`/`BigTarget`/`LightCover`
        # et sur-appliquait `Parry`. Positions/board absents -> on GARDE la base brute (aucune
        # sur-application).
        # BASE de coups DEMANDEE par l'appelant (avant tout passage par la formule). Elle borne le
        # plancher : `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` termine par
        # `System.Math.Max(hits, 0)` et son clamp par-effet est `Math.Max(hits, Math.Min(base, cap))`
        # -> avec une base de 0, RIEN ne peut remonter au-dessus de 0. Cf. le bloc `_floor` de
        # `services/attack_hits_formula.py` (mesure live Doombolt, case-psychic-aoe §3). Base >= 1 ->
        # plancher 1, comportement historique STRICTEMENT inchange.
        _hits_floor = min(1, int(hits))
        _ap_h = att.get_component(PositionComponent) if att is not None else None
        _tp_h = tgt.get_component(PositionComponent)
        # #227 SNAPSHOT DES ENTREES D'ETAT DU GATE `LetTheGalaxyBurn` — pris ICI, juste apres
        # `On(PreAttack=5)` et AVANT le premier coup (MEME position que la facade normale). La tuile
        # de la cible est FIGEE par `IdunBattle.Operations.ActiveAbilityOperation$$GetAbilityEntities`
        # : un status-effect pose PENDANT l'attaque (`FleshMetalGuns_TileEffectAbility` sur
        # `On(0x10 = DamageDealt)`, #85) n'arme donc PAS le coup. Cf. `damage_ops/normal.py`.
        _ltgb_tfx = (tile_status_effects_by_pos(state, [(_tp_h.col, _tp_h.row)])
                     if _tp_h is not None else None)
        _ltgb_pd = persistent_data_keys(att)
        if is_attack_damage_op and _ap_h is not None and _tp_h is not None and state.board is not None:
            _melee_ch = hits_channel_is_melee(state, attacker_id, target_id, is_melee)
            _board_h, _auras_h, _tgt_eff_h = build_hits_board(
                state, attacker_id, target_id, (_ap_h.col, _ap_h.row), (_tp_h.col, _tp_h.row),
                is_melee=_melee_ch)
            # A3 (#113) : gate compute-time LightCover, mirror du call-site de l'attaque normale.
            _t_terrain_h = state.board.terrain_at(_tp_h.col, _tp_h.row)
            _on_cover_h = (_t_terrain_h == LIGHT_COVER_TILE_ID) if _t_terrain_h is not None else None
            hits = attack_hits_with_modifiers(
                weapon_hits=int(hits), extra_hits=ctx.stat(StatType.EXTRA_HITS),
                extra_hits_melee=ctx.extra_hits_melee,
                attacker_effects=active, trait_objects=ctx.trait_objects(),
                target_effects=_tgt_eff_h, aura_sources=_auras_h, board=_board_h,
                is_melee=_melee_ch, damage_profile=damage_profile,
                # combat : GetStuckIn n'est PAS dans la formule (behaviour d'exec chance-gate, #62c).
                # Le coup bonus est ajoute A L'EXECUTION, par `_run_hits(bonus_hit_chance=_gsi)`
                # plus bas (R6-b'') -- exactement comme la facade combat de l'attaque normale.
                include_bonus_hit_behaviours=False,
                defender_on_cover=_on_cover_h,
                is_normal_attack=False)     # gate `IsNormalAttack` (PowerTrip) : vecteur ABILITY
        hits = max(_hits_floor, int(hits))  # `Math.Max(·, 0)` natif, borne par la BASE (cf. ci-dessus)
        # 2e volet du garde-fou rng (cf. l'entree) : crit-roll et block sont les deux SEULS tirages
        # restants de ce vecteur, et ils ne sont connus qu'ici.
        if state.rng is None and (crit_enabled or block_sources):
            return None
        _hp_before_chain = int(thc.hp or 0)     # PV AVANT l'attaque (#116, cf. le retour `hp_before`)
        shc, shield_total = AttackDamageOperation._target_shield(tgt)      # bouclier shield-first
        # R6-b'' — LE `Maybe` AFTER-HIT ROULE AUSSI SUR LES COUPS D'UNE ATTAQUE D'ABILITY.
        # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger` (LU
        # verbatim, gqfc5mff6c) = `On(8,1) & AmountIsOdd(CurrentHitIndex()) & get_OwnerIsCaster &
        # !AmountIsGreater(MinDistance(owner@0x160, target@0x178), Direct(2))` : AUCUN gate
        # `IsNormalAttack`, AUCUN `CurrentAbilityIs` -> le vecteur d'attaque ne le filtre pas.
        # L'emetteur `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` a TROIS
        # appelants, tous en appel INCONDITIONNEL (xref) et tous en DERNIERE instruction de leur
        # `ExecuteHit` : `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (famille ATTACK
        # = `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`, LA MEME fonction que
        # l'attaque normale), `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit` (famille
        # ABILITY = `$$AttackWithAbilityDamage`) et `MachineDamageOperation$$ExecuteHit`.
        # => AUCUN gate de famille ici (contraste avec les mods attaquant / le crit / le canal
        # #179 ci-dessous, qui eux sont bien gates par `is_attack_damage_op`).
        # L'INDEX passe au trigger est `currentAttack+0x30`, relu FRAIS a chaque tour de boucle :
        # `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHits` le passe en 2e argument de
        # son `ExecuteHit` et fait `+0x30 += 1` apres CHAQUE coup (mirror inline
        # d'`ADamageOperation$$UpdateCurrentAttackAfterHit`), exactement comme
        # `AttackDamageOperation$$ExecuteHits`.
        # L'INDEX DEMARRE A 0 POUR CHAQUE CIBLE : les DEUX factories emballent leur behaviour de
        # degat dans un `IdunBattle.Entities.Behaviours.AttackBehaviour` (lu : les deux
        # `DSLFactory$$AttackWith*Damage` finissent par `AttackBehaviour$$.ctor(caster, targets,
        # <behaviour>, options)`), et `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`
        # emet `Core.Services.OperationProcessor$$StartAttack` (slot 0x3a) avant CHAQUE cible et
        # `$$FinishAttack` (0x3b) apres -- donc un `IdunBattle.Operations.StartAttackOperation$$
        # Execute` (= `new OngoingAttack` + `MatchState$$StartAttack` = Push sur `MatchState+0x60`)
        # par cible. `hit_index0` reste donc son defaut 0, comme le vecteur normal.
        _gsi = getstuckin_combat_chance(
            state, attacker_id, target_id,
            (_ap_h.col, _ap_h.row) if _ap_h is not None else None,
            (_tp_h.col, _tp_h.row) if _tp_h is not None else None, state.board)
        # #366-r1 : intercepteur per-coup (`ExecuteHit` etape 5 = flag `discard` ; `On(0x3c)` +
        # `RegisterBlocks`). `ADamageOperation` est la BASE PARTAGEE des deux familles -- la voie
        # ABILITY passe par `AbilityDamageOperation$$ExecuteHit`, qui emet les MEMES vecteurs.
        from ..triggers.loki.harlequins_panoply import make_hit_interceptor   # lazy (cycle)
        r = AttackDamageOperation._run_hits(state.rng, hit_nc, hit_cr, crit_chance,
                                            crit_enabled, hits, block_sources, shield=shield_total,
                                            bonus_hit_chance=_gsi,
                                            hit_interceptor=make_hit_interceptor(
                                                state, attacker_id, target_id),
                                            post_roll=_reduce,
                                            capped_reductions=def_mods.capped_reductions,
                                            # #67 : etage limites — mode 2 = ability
                                            # (`IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`)
                                            limits=AttackDamageOperation._target_limits(
                                                tgt, thc, damage_profile, is_special=2),
                                            limits_hp=int(thc.hp or 0),
                                            # #195 : `HasFlag(defender, 0x13)` — le 5e argument
                                            # `isPreventOverkill` que `ApplyTraitDamageLimitsToDamage`
                                            # lit lui-meme sur son parametre `defender`.
                                            prevent_overkill=unit_prevents_overkill(state, target_id),
                                            # famille de factory native (cf. _one_hit) : True =
                                            # AttackWithAttackDamage (resolve gaspille) ; False =
                                            # AttackWithAbilityDamage (AbilityDamageOperation, sans).
                                            is_attack_damage_op=is_attack_damage_op,
                                            # flag « always overkilled » (FlailSwing) : bypasse le cap
                                            # Resilient a chaque coup (no-op cible non-Resilient).
                                            force_overkill=force_overkill,
                                            # flag « always crit » (TacticalPrecision branche CHARGE) :
                                            # crit acquis par coup, SANS tirage (le natif saute
                                            # RollCritical quand l'octet options+5 est pose).
                                            force_crit=force_crit)
        AttackDamageOperation._deplete_shield(shc, r)
        # `is_attack` = COMPTABILITE d'attaque (`_record_attacked` -> `ActorStatisticsComponent$$
        # RegisterAttackReceived`, dont le SEUL appelant natif est `IdunBattle.Operations.
        # RegisterAttackOperation$$Execute`). GATE PAR FAMILLE : le corps d'`IdunBattle.Operations.
        # AbilityDamageOperation$$Execute` (LU : boucle `ExecuteHits` + chain + `IdunBattle.Operations.
        # ADamageOperation$$RegisterFinalDamage`) n'enqueue JAMAIS `RegisterAttackOperation` -> la
        # famille ABILITY n'incremente PAS le compteur `HasBeenAttackedAmountThisTurn` de la cible.
        # Le gate ne change rien au DEGAT ; il evite qu'un tick de DoT de tuile (migre sur cette
        # route) soit compte comme une ATTAQUE recue (plancher PV Hypersensory, MoveAndSpawnDecoy,
        # formule `TimesReceivedAttackedThisTurn`). Effet de bord ASSUME et fonde RE sur les autres
        # consommateurs de la famille (Hailstrike, PutridExplosion) : eux non plus n'ont de
        # `RegisterAttackOperation` dans leur chemin natif.
        AttackDamageOperation._apply_damage_pipeline(                   # chokepoint partage (#202)
            state, target_id, attacker_id, tgt, thc, r["total"], damage_profile,
            r["shield_dmg"], r["armor_dmg"], is_attack=bool(is_attack_damage_op),
            # `GetDamageSourceAbility(currentAbility = l'ABILITY, triggeringAbility = null)` : une
            # ability n'est pas une attaque REGULIERE -> la source est l'ability elle-meme.
            source_ability=AttackDamageOperation._damage_source_ability(ability_type, None),
            # `ApplyDamageOperation$$Execute` ecrit le « dernier coup encaisse » PAR COUP -> le
            # chokepoint par-attaque du port recoit le DERNIER coup (cf. `_record_last_hit_damage_taken`).
            last_hit=(r["per_hit"][-1] if r.get("per_hit") else None),
            # #R33 : decomposition per-coup (crit / denied) + le flag `isForceOverkill`
            # (`AttackOptions@+4`, 8e arg d'`AttackWithAttackDamage` ; porteur FlailSwing 1042) ->
            # `DealDamageInfo@+0x2c`, lu par la surcharge d'instance d'`IsOverkill`. Le port ne le
            # cablait QUE sur le cap Resilient ; il decide AUSSI `UnitFlag.Overkilled`.
            hits_result=r, is_force_overkill=bool(force_overkill),
            # `On(0x10)` : cet appel EST la serie de coups portee sur CETTE cible, donc il contient le
            # coup d'index 0 -> `IsFirstHitInSeries` VRAI (mirror `AbilityEntities+0x110`). Sur une
            # ability MULTI-CIBLES, `execute_ability_attack` est appelee une fois PAR cible, et
            # `IdunBattle.Operations.ADamageOperation$$SetupHitGroup` construit lui aussi un groupe par
            # cible -> un tirage 1203 par cible, des deux cotes.
            is_first_hit=True)
        # #179 SUR LE VECTEUR ABILITY (famille ATTACK) — le natif n'a QU'UNE Operation d'attaque :
        # `IdunBattle.Operations.AttackDamageOperation$$Execute`, empruntee par l'attaque NORMALE **et**
        # par toute ability `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (case-61 §1.2 :
        # « MEME `Execute`, MEME `GetAttackHits` »). Or c'est CETTE `Execute` qui appelle
        # `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType`
        # (son SEUL appelant, XREF) -> les coups additionnels HETEROGENES du canal #179 se greffent aussi
        # sur les attaques d'ability. Le port ne les cablait que dans `execute` (attaque normale) : FORK
        # de port (1 Execute native -> 2 facades offline dont 1 muette).
        # MESURE (probe_61d_frenzy_aoe_combat, blackObliterator « Volk » porteur permanent d'un effet du
        # cycle `FleshmetalGuns`, cast de FrenziedFiring 1036) : le natif applique, APRES les coups
        # HeavyRound de l'arbre, 2 coups au profil du cycle (Melta ~2000/coup) SUR CHAQUE cible touchee
        # -- absents du port, qui s'arretait aux coups d'arme.
        # GATE FAMILLE : la famille ABILITY (`IdunBattle.Operations.AbilityDamageOperation$$Execute`) est
        # une Operation DISTINCTE, qui n'appelle PAS ce canal -> `is_attack_damage_op` seul (meme gate que
        # les mods attaquant / le crit ci-dessus). Aucun groupe qualifie -> no-op strict, 0 conso RNG.
        _ah = None
        if is_attack_damage_op:
            _ah = execute_additional_hits(
                state, attacker_id, target_id, tgt, thc,
                collect_additional_hit_groups(
                    state, attacker_id, target_id, active, bool(is_melee),
                    (state.effects.active_effects(target_id,
                                                  unit_state_for_effects(state, target_id))
                     if state.effects is not None else []),
                    # #227 `LetTheGalaxyBurn` sur CE vecteur : meme canal #179, mais l'AttackData
                    # d'une ability bounds-mode porte un `HitDamage` NON degenere -> le groupe TIRE
                    # dans `[base_min, base_max]` BRUTS (puis reduce + resolve). C'est EXACTEMENT ce
                    # que produisait l'ancien modele « +1 coup d'arme » : meme valeur, meme
                    # consommation RNG -- d'ou le bit-exact de `case-bl-1029-1020` §5.4, qui n'est
                    # donc PAS en contradiction avec la mesure du vecteur normal (case-159 §3.2).
                    # Bornes AVANT max-out (le natif applique `IsAttackMaxOutDamage` dans
                    # `ExecuteHit`, pas sur l'AttackData enregistree).
                    attack_hit_damage=(int(base_min), int(base_max)),
                    t_pos=(_tp_h.col, _tp_h.row) if _tp_h is not None else None,
                    # snapshot PRE-attaque (cf. le bloc `_ltgb_tfx` plus haut). `IsPersistentData` :
                    # `On(PreAttack=5)` EST emis par ce vecteur (famille ATTACK, cf. plus haut) ->
                    # les DEUX branches du gate sont armables ici.
                    tile_effects_by_pos=_ltgb_tfx, persistent_data=_ltgb_pd,
                    # #204 `MasterAnnihilator_AdditionalHitEffect` : noeud
                    # `AreEqual(CurrentAttackDamageProfile, 0xd = Psychic)` du gate.
                    damage_profile=damage_profile),
                mods, def_mods, armor, _tgt_hit_mult, block_sources, shc,
                extra_pierce=ctx.extra_pierce,
                attack_profile=damage_profile,
                # R6-b'' : les sous-operations de groupe partagent l'`OngoingAttack` de CETTE
                # attaque (`GetCurrentAttackOrDefault` = `Peek`) -> MEME site d'evaluation du
                # `Maybe` et index CONTINU, threade depuis la sortie de la phase d'arme (coups
                # bonus compris). Strictement le cablage de `damage_ops/normal.py` (R6-b').
                bonus_hit_chance=_gsi, hit_index0=r["next_hit_index"],
                # #366-r1-crit-multihit : idem `damage_ops/normal.py` -- `isCriticalDamageAllowed`
                # est porte par l'`OngoingAttack`, donc il traverse les sous-operations de groupe.
                crit_allowed0=r["crit_allowed"],
                # #407 : JUMEAU BLOCK -- `OngoingAttack+0x48` (`FailedBlockIds`), meme portee et
                # meme threading (`SetupHitGroup` le seme par reference dans `OngoingHitGroup+0x60`).
                failed_block0=r["failed_block"])
        # DE-FORK — la POSE on-hit des tile-effects de profil (`OnFireDamageAbility` 1016,
        # `OnToxicDamageAbility` 1203) N'EST PLUS appelee ici. Leur vecteur natif est
        # `On(DamageDealt = 0x10)`, emis par `IdunBattle.Operations.ApplyDamageOperation$$Execute`
        # DEPUIS `_apply_damage_pipeline` ci-dessus -- c.-a-d. AVANT le traitement de la mort, alors
        # que ce point-ci est APRES. L'ecart est OBSERVABLE et a ete arbitre LIVE (bus 6/6 vs
        # imperatif 3/6, cf. la docstring de `damage_dealt_triggers`). Les deux abilities sont
        # desormais des consommatrices GLOBALES du bus (`GLOBAL_TRIGGERS`), donc couvertes pour les
        # DEUX familles d'attaque sans cablage par famille.
        from ..triggers import after_hit_ability_attack          # lazy : cycle damage<->triggers
        # VECTEUR AFTER-HIT (ability/splash) : dispatch générique — reset ActOfFaith au crit (#138) + tout
        # after-hit trigger (#140 : splash Psyker sur ability/splash psychique, chain borné par le cap).
        # `ranged` = POSITION-based (calculé dans after_hit_ability_attack, mirror IsRangedAttack).
        after_hit = after_hit_ability_attack(state, attacker_id, target_id, r["did_crit"],
                                             profile=damage_profile, ability_type=ability_type,
                                             did_block=r["did_block"])
        # `On(FinalDamage = 0x42 = 66)` — 2e (et DERNIER) call-site natif de `IdunBattle.Operations.
        # ADamageOperation$$RegisterFinalDamage` : `IdunBattle.Operations.AbilityDamageOperation$$
        # Execute`. Emis pour les DEUX familles (`is_attack_damage_op` ou non) : la fonction est sur la
        # base commune `ADamageOperation` et les deux `Execute` l'appellent — contraste avec `On(10)`
        # ci-dessous, qui est bien gate par famille.
        from ..triggers.dispatch import final_damage_triggers
        from ..triggers.base import _is_ranged_position as _irp
        final_damage_triggers(state, attacker_id, target_id,
                              ranged=_irp(state, attacker_id, target_id), profile=damage_profile)
        # `On(AttackDamageAttack = 10)` : `FinishAttackOperation$$Execute` l'emet APRES `On(9)` et
        # SEULEMENT si `currentAttack@+0x2c` est pose, c'est-a-dire si l'attaque a traverse
        # `AttackDamageOperation$$Execute`. Cote port, ce gate EST `is_attack_damage_op` (famille de
        # factory : `AttackWithAttackDamage` vs `AttackWithAbilityDamage`). Une attaque d'ability de la
        # famille ABILITY n'emet donc RIEN ici, comme le natif.
        if is_attack_damage_op:
            from ..triggers.dispatch import attack_damage_attack_triggers
            from ..triggers.base import _is_ranged_position
            # `ranged` POSITION-based, comme le vecteur frere `after_hit_ability_attack` (mirror
            # `IdunBattleLogic.Entities.DSLFactory$$IsRangedAttack`) — aucun consommateur d'`On(10)` ne
            # le lit aujourd'hui, mais le payload reste coherent entre les deux events de cloture.
            attack_damage_attack_triggers(state, attacker_id, target_id,
                                          ranged=_is_ranged_position(state, attacker_id, target_id),
                                          profile=damage_profile)
        # NB (de-fork) : les cles diagnostiques `fire`/`toxic` ont disparu de ce retour -- la pose
        # on-hit ne passe plus par ici mais par le bus `On(0x10)` emis dans `_apply_damage_pipeline`.
        # L'observable reste `state.effects` (la tuile porte l'effet), qui est la VRAIE source et celle
        # que le live expose (`tileMeta`) ; les tests confrontent desormais l'etat, pas un champ de diag.
        return {"hits": hits, "total": r["total"], "base_min": base_min, "base_max": base_max,
                "pierce": profile_pierce, "armor": armor,
                "after_hit": after_hit,
                "clean_min": hit_nc.min * hits, "clean_max": hit_nc.max * hits,
                "did_crit": r["did_crit"], "did_block": r["did_block"], "did_evade": r["did_evade"],
                "crits": r["crits"], "rolls": r["rolls"], "per_hit": r["per_hit"],
                "additional_hits": _ah,          # #179 sur le vecteur ability (None = aucun groupe)
                # part PV par coup + PV AVANT l'attaque (#116 `ChainLeftOverHitsAttackDamage` : localiser
                # le coup qui met la cible a 0 PV -> compter les coups GASPILLES sur le cadavre).
                # `hp_after` = PV APRES la mutation (purement ADDITIF, aucune branche modifiee) : le DoT
                # de tuile en a besoin pour son emit, et le total ne suffit pas des qu'un cap (Resilient)
                # ou un bouclier s'interpose.
                "per_hit_health": r["per_hit_health"], "hp_before": _hp_before_chain,
                "hp_after": int(thc.hp or 0)}
