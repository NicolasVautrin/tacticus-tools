"""Prediction des abilities SPECIALES : `generate_multi_hit_attack_prediction` (per-cible de
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`), le registre d'overrides d'ENTREE per-ability
(`_MAKE_DMG_INPUT_OVERRIDES` / `_PLAYBOOK_PROFILE_OVERRIDE`), l'orchestrateur `make_damage_predictions`
(`<Ability>Playbook.MakeDamagePredictions` : cible + AoE + self) et le chemin dedie HammerOfWrath.
Consomme `_shared` (helpers mods/defenseur + vocabulaire) et `normal_attack` (via_normal).

C'est ICI qu'atterrissent les nouveaux handlers `_<ability>_inputs` de la phase de port case-220 (chaque
ability qui SURCHARGE la base/hits/profil generiques ajoute son handler HOMONYME + une entree registre)."""
from __future__ import annotations

from ._shared import *   # vocabulaire commun (GC, dsl, active_ability_for, ProbableDamageEvent, ...)
from ._shared import (_PROFILE_INDEX, _add_positional_and_defender_mods, _apply_ally_attack_dmg_bonus,
                      _prediction_is_charging, _target_damage_limits, _entity_traits)
from .normal_attack import make_normal_attack_predictions
# Les trois registres par-ability de ce module sont clees par `IdunBattle.Entities.Enum.ActiveAbilityType`
# (#270-r1 volet 2) : ce sont des ids d'abilities ACTIVES, jamais des `TriggeredAbilityType`.
from ...entities.active_ability_type import ActiveAbilityType
# `EffectType.Fire` (5) : effet de TUILE lu par le gate de selecteur de 1148 (`_MAKE_DMG_TARGET_GATE`).
from ...entities.effect_type import EffectType as _EffectType
# #948 : cles du contexte per-coup d'`EnmityForTheUnworthy` -- un seul foyer de nommage.
from ...entities.effects.loki.enmity_for_the_unworthy import (
    CTX_ADJACENT_UNITS as _ENMITY_CTX_UNITS, CTX_ADJACENT_DA as _ENMITY_CTX_DA)
# #953 : meme regle, meme foyer -- la cle du couple de PV du porteur vit dans la classe d'effet.
from ...entities.effects.loki.skullsmasher import CTX_OWNER_HEALTH as _SKULLSMASHER_CTX_HEALTH
# `UnitTrait.Summon` (2) : trait lu par le selecteur de 1147 (`UnitsWithTrait(..., 2)`), cote gate ET
# cote noeud DSL (`ctx.has_trait`, cable dans `make_damage_predictions`).
from ...entities.traits.unit_trait import (UnitTrait as _UnitTrait, has_trait as _has_trait,
                                           trait_name as _trait_name)
from engine.services.damage_prediction import DamagePredictionResult
from engine.services import current_player as _cp   # forme B (#359-r6) : foyer `current_player_team`
from engine import battle_query as _bq   # forme B (#485-r1-r1) : foyer des DEUX etages
#                                          d'`IterateAdjacentTiles` (#943-r7)
import engine.playbook.adjacency as _adjacency   # foyer PARTAGE multi-tuiles (#954)
# `_tactical_precision_inputs` : la TRONCATURE de la forme (b) (`RandomAmount` puis slot 4
# `AAmountFormula$$CalculateAverage`). MEME foyer que `AActiveAbility.get_damage`, pour que les
# deux paires de variables (`minDmg`/`maxDmg` et `minDmg_2`/`maxDmg_2`) partagent l'arrondi.
from engine.dsl.base import calculate_average
# ⚠ La forme `from engine.playbook import adjacency` declarerait le PAQUET (elle en lit
# l'attribut), pas le module -- et `engine.playbook` atteint deja ce module par `.base`, donc
# l'arete refermait un SCC de 16 (`test_270r4r2_cycles_imports_offline` etage 1, MESURE).
# `import <paquet>.<module> as x` declare le MODULE et garde la forme B (liaison de module,
# donc un patch mord).


def generate_multi_hit_attack_prediction(scene, uid, tgt, ability_id, ability_name, attack_pos=None,
                                         base_bonus: int = 0, base_override=None,
                                         hits_override=None, profile_override=None):
    """Per-cible de `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions` : `DamagePredictionResult`
    d'UNE cible via le `(damage, hits, profile, pierce)` PROPRE de l'ability (`<Ability>.PredictAttack`,
    slot +0x27). None si non-attaque.

    `base_override`/`hits_override`/`profile_override` (defaut None = comportement inchange) : substituent
    la base/hits/profil lus de l'ability. Requis par l'utilite de DECISION NonComparable de HammerOfWrath
    (#114), dont `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent/IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent appelle `PredictAttack(0x27)` avec
    `damage=GetMinDamage`(var12) + `hits=GetHits`(const47) [primary] / `GetMinDamage2`(var54)+
    `GetHitsToBonusTarget`(const50)+profil2 [secondary] au lieu de avg(minDmg,maxDmg)/hits config. Le RESTE
    du pipeline (spread ±20%, pierce, armure, mods attaquant/positionnels, bouclier per-coup) est identique."""
    ctx = scene.ctx(uid)
    if ctx is None:
        return None
    cfg = AbilityConfiguration.from_gameconfig(ability_name, GC.ability(ability_name))
    if cfg is None or not (cfg.has_variable("minDmg") or cfg.has_variable("maxDmg")):
        return None
    # AbilityState PER-ABILITY (#100) : le natif indexe les variables config par le couple
    # {Level, VariableMultiplierPercentage} PROPRE de l'ability (entree ActiveAbilityComponent
    # ._abilityState @0x4c, forwarde au playbook en 5e arg de MakeDamagePredictions) — consomme par
    # IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel (idx = Level.ToZeroBasedIndex clampe ; × mult/100 si
    # var ∈ variablesAffectedByRarityBonus). Le canal global (ctx.active_ability_level ×
    # scene.mult) est un AUTRE couple (mesure u80 PlasmaCannon : per-ability 65×120 → 1396 vs
    # global 50×180 → 1594, faux) → capteur combatSnapshot.abilityStates, fallback global.
    st = scene.ability_state(uid, ability_id)
    ab = active_ability_for(ability_name, ability_id, ctx, cfg, ability_state=st)
    # Base de la PREDICTION speciale = `GetDamageFormula` du playbook (PlasmaCannonPlaybook
    # IdunBattle.AI.Playbook.Loki.PlasmaCannonPlaybook$$MakeDamagePredictions) = `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage` (avgFlag) = **avg(minDmg, maxDmg)**
    # scales per-entree ×mult/100 (ab.get_damage, DECOMPOSE PAR ETAGE #100 : varLevelDumps
    # min 1197 + max 1595 → avg 1396 ; bouts prediction [1117,1675] = ±20% EXACT ; ×mods 1.875
    # → per-coup [2094,3141] == aiPlaybookPredict). Le « base = maxDmg seul » (#96) est REFUTE —
    # 1396 se decomposait AUSSI en maxDmg[65]×1.2 (sous-determination du degat final). Le couple
    # (level, mult) = AbilityState PER-ABILITY (capteur, fallback global via ab.level/ab.multiplier).
    lvl = ab.level
    base = ab.get_damage() if base_override is None else float(base_override)   # HammerOfWrath: GetMinDamage
    if base <= 0:
        return None
    # #108 GetCorrectDamage : clause conditionnelle sur le NB de cibles AJOUTEE A LA BASE avant spread/mods
    # (ex. MurderousSwing single-enemy +extraDmg). `base_bonus` fourni par `make_damage_predictions` (qui
    # connait le compte AoE) ; 0 pour toutes les abilities sans clause (get_correct_damage identite).
    base += int(base_bonus or 0)
    a = GC.ability(ability_name) or {}
    is_melee = (a.get("attackRangeType") or "").lower() == "melee"
    hits = max(1, ab.get_special_hits(is_melee) if hits_override is None else int(hits_override))
    profile_name = ab.get_damage_profile() if profile_override is None else profile_override
    profile_idx = _PROFILE_INDEX.get(profile_name, 0)
    dp = GC.damage_profile(profile_name) or {}
    dir_pierce = ctx.extra_pierce_melee if is_melee else ctx.extra_pierce_ranged
    pierce = max(0, min(100, int(dp.get("PiercingRatio") or 0) + ctx.extra_pierce + dir_pierce))
    # Mods attaquant : MEME builder IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction que la normale (le natif ne distingue pas par ability) —
    # threader la nature du coup + le flag has-moved de la tuile candidate (gates IsRangedAttack /
    # NOT HasMoved des effets, ex. HeavyWeapon +25% ranged not-moved s'applique aux speciales ranged).
    _hm = prediction_has_moved(scene, uid, attack_pos)
    # gate ConquerorImperative (#22) : +extraDmg s'applique AUSSI aux attaques SPECIALES du porteur (trigger
    # OwnerIsCaster & HasNegativeModifier, AUCUN IsNormalAttack) vs cible a armure reduite.
    _tctx = scene.ctx(tgt)
    _tgt_armor_reduced = (_tctx.stats.has_negative_modifier(ARMOR_STAT_TYPES)
                          if _tctx is not None and _tctx.stats is not None else None)
    # #316 : TRAITS DE LA CIBLE, sur le vecteur ABILITY comme sur la normale. Le natif n'a qu'UN
    # `AbilityEntities` pour ces deux chemins. `IdunBattle.Core.Services.DamagePrediction$$Predict
    # AttackRaw` appelle `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` avec
    # `target = request+0x50` -- le 3e argument que le playbook a passe au slot 0xb
    # (`IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction`, qui l'ecrit VERBATIM
    # dans la request, recopiee sans re-derivation par les deux `DamagePrediction$$PredictAttack`)
    # -- puis transmet cet objet au slot 0xd `CalculateAttackerModifiersForPrediction`, lequel ne
    # recoit AUCUN identifiant d'ability et recopie `Target@+0x10` tel quel dans le copy-ctor qui
    # alimente les arbres DSL des effets. Les gates `HasTrait(target, ...)` des effets d'ATTAQUANT
    # (`IdunBattle.Entities.Effects.Loki.BeastSlayer_ExtraDmgEffect$$CreateDamageModifier` = +20%
    # melee vs BigTarget/Vehicle ; `IdunBattle.Entities.Effects.Loki.MartialKatah_DmgBonusEffect$$
    # CreateEffectDamageBonusForAttack` = +100% vs Summon) s'y evaluent donc pour une ability
    # EXACTEMENT comme pour l'attaque normale.
    # Ce parametre etait absent ICI et present dans `make_normal_attack_predictions` : le defaut
    # `None` de `BaseEffect.create_effect_damage_bonus_for_attack` vaut "cible inconnue" -> AUCUN
    # bonus, degradation SILENCIEUSE et UNILATERALE (le port sous-estimait). C'etait AUSSI un fork
    # prediction<->combat : la face COMBAT du meme vecteur ability threade deja `target_traits`
    # (`runner/operations/damage_ops/ability.py`), donc le port ANNONCAIT moins qu'il n'EXECUTE.
    # MESURE (`probe_316_ability_prediction_target_traits.py` : caster `custoBladeChampion`, cible
    # mannequin dont la ligne `BC.Units[].Traits` est le SEUL curseur, oracle `aiPlaybookPredict`) --
    # sur 1191 le natif rend [1496,2244] sans trait, [1795,2692] avec `BigTarget` ou `Vehicle`
    # (x1.1996) et [2993,4488] avec `Summon` (x2.0) ; le port rendait [1496,2244] dans les QUATRE
    # bras. L'attaque normale du MEME caster, elle, etait deja bit-exacte dans les quatre.
    # #267-r1 : substrat d'ENTITE (`_entity_traits`), MEME source que la normale et que le combat.
    _tgt_traits = _entity_traits(scene, tgt)
    mods = calculate_attacker_modifiers_for_prediction(scene.effects(uid), is_ranged=not is_melee,
                                                       has_moved=_hm, is_normal_attack=False,
                                                       target_traits=_tgt_traits,
                                                       target_armor_reduced=_tgt_armor_reduced,
                                                       att_ctx={"att_pos": attack_pos or scene.pos(uid),
                                                                "tile_effects_by_pos":
                                                                    scene.tile_effects_by_pos,
                                                                # `IsCharging` depuis la tuile candidate
                                                                # (case-r32) — AvalancheOfMuscle 1025 n'a
                                                                # AUCUN gate IsNormalAttack, il entre donc
                                                                # aussi sur ce vecteur ABILITY.
                                                                "is_charging": _prediction_is_charging(
                                                                    scene, uid, attack_pos, tgt),
                                                                # branche `| HasFlag(Teleported)` du
                                                                # gate HeavyWeapon (cf.
                                                                # `prediction_has_teleported`).
                                                                "has_teleported":
                                                                    prediction_has_teleported(
                                                                        scene, uid, attack_pos),
                                                                # `TilesMovedThisTurn(Self)` depuis
                                                                # la tuile candidate (case-322) —
                                                                # `ModifiedExoarmour_ExtraDmg` n'a
                                                                # AUCUN gate IsNormalAttack, il
                                                                # entre donc AUSSI sur ce vecteur
                                                                # ABILITY (le seul autre gate est
                                                                # IsMeleeAttack, deja threade).
                                                                "tiles_moved_this_turn":
                                                                    prediction_tiles_moved_this_turn(
                                                                        scene, uid, attack_pos),
                                                                # `PsychicStalk_FriendlyChaos
                                                                # ExtraDamage` (#366-r1, 1435) :
                                                                # son trigger n'a AUCUN gate
                                                                # `IsNormalAttack`, il entre donc
                                                                # AUSSI sur ce vecteur ABILITY.
                                                                # MEMES CLES que la normale et que
                                                                # la face COMBAT.
                                                                "att_grand_alliance":
                                                                    (GC.unit(scene.vis_by_id.get(uid))
                                                                     or {}).get("GrandAllianceId"),
                                                                "damage_profile": profile_name,
                                                                "t_pos": scene.pos(tgt),
                                                                "tgt_team": scene.team(tgt),
                                                                # `HealthPctIsBelowOrEqual(Target
                                                                # @0x60, ConfigConst(0x4f))` = gate
                                                                # de DOUBLEMENT de
                                                                # `LightOfSanguinius` (1376, #510),
                                                                # sans gate `IsNormalAttack` -> il
                                                                # entre AUSSI sur ce vecteur.
                                                                "tgt_hp": scene.hp(tgt),
                                                                "tgt_hp_max": scene.hpmax(tgt),
                                                                # `Target@0x60` lu en IDENTITE :
                                                                # gate `AreEqual(Target@0x60,
                                                                # BondedEntityFromEffect(Effect))`
                                                                # de `HolyDuel_ExtraDmgEffect`
                                                                # (1092), sans gate
                                                                # `IsNormalAttack` -> il entre
                                                                # AUSSI sur ce vecteur. MEME cle
                                                                # que la normale et que la face
                                                                # COMBAT -- pas de fork.
                                                                "tgt_id": tgt,
                                                                # #919 -- `StatAmount(Owner@0x30,
                                                                # BlockDamage, Current)` de
                                                                # `IconOfObstinacy_ExtraDamage
                                                                # Effect`, PATTE SELF. AUCUN gate
                                                                # `IsNormalAttack` au decompile ->
                                                                # il entre AUSSI sur ce vecteur.
                                                                # MEME cle que la normale et que la
                                                                # face COMBAT -- pas de fork.
                                                                "owner_block_damage":
                                                                    prediction_block_damage(scene,
                                                                                            uid),
                                                                # #932 -- les TROIS noeuds de
                                                                # `DeathwingEffect$$GetDouble
                                                                # EffectCondition` sur la face
                                                                # ATTAQUE. Le trigger de
                                                                # `CreateEffectDamageBonusForAttack`
                                                                # est `IsMeleeAttack | NOT
                                                                # IsNormalAttack` : ce vecteur
                                                                # ABILITY y entre TOUJOURS (c'est
                                                                # exactement le << ou Plasma Cannon >>
                                                                # de l'i2). MEMES cles que la
                                                                # normale et que la face COMBAT.
                                                                "tgt_grand_alliance":
                                                                    (GC.unit(scene.vis_by_id.get(tgt))
                                                                     or {}).get("GrandAllianceId"),
                                                                "att_team": scene.team(uid),
                                                                "adjacent_dark_angels_friends":
                                                                    scene.adjacent_dark_angels_friends(
                                                                        uid),
                                                                # #948 -- les DEUX compteurs
                                                                # d'`EnmityForTheUnworthy`. Ses deux
                                                                # `CreateEffectDamageBonusForAttack`
                                                                # n'ont AUCUN gate de nature de coup
                                                                # (`get_OwnerIsCaster` seul) : ce
                                                                # vecteur ABILITY y entre comme la
                                                                # normale. MEMES cles que la face
                                                                # COMBAT -- pas de fork.
                                                                _ENMITY_CTX_UNITS:
                                                                    scene.enmity_adjacent_units(uid),
                                                                _ENMITY_CTX_DA:
                                                                    scene.enmity_adjacent_dark_angels_friends(
                                                                        uid),
                                                                # #953 -- le couple de PV du PORTEUR
                                                                # (`StatAmount(Owner, Health,
                                                                # {Missing, Maximum})`). Son
                                                                # `CreateEffectDamageBonusForAttack`
                                                                # n'a AUCUN gate de nature de coup
                                                                # (`get_OwnerIsCaster` seul) : ce
                                                                # vecteur ABILITY y entre comme la
                                                                # normale -- l'i2 dit << Macer deals
                                                                # +X Damage >>, sans restriction, et
                                                                # `JakhalStimms` est une ability.
                                                                # MEMES cles que la face COMBAT.
                                                                _SKULLSMASHER_CTX_HEALTH:
                                                                    (scene.hp(uid),
                                                                     scene.hpmax(uid))})
    t_pos = scene.pos(tgt)
    _add_positional_and_defender_mods(mods, scene, uid, tgt, is_melee, attack_pos, t_pos,
                                      damage_profile=profile_name, is_normal_attack=False)
    # AURA ALLIEE +extraDmg (ConquerorImperative #23 / BeaconOfRage #191) : le +extraDmg de Conqueror n'a AUCUN
    # gate IsNormalAttack -> s'applique aussi quand un ami Mechanical adjacent utilise une attaque SPECIALE vs
    # cible a armure reduite (symetrique de la normale). Gates dans le create_aura_ (Mechanical/adjacence/team/
    # target_armor_reduced ; BeaconOfRage : is_melee/Chaos).
    _apply_ally_attack_dmg_bonus(mods, scene, uid, attack_pos or scene.pos(uid), is_melee, _tgt_armor_reduced,
                                 tgt_id=tgt, is_normal_attack=False, damage_profile=profile_name)
    tgt_shield = scene.shield(tgt)
    # Base speciale = `base` (avg(minDmg,maxDmg) scale rarete) route par le MEME chemin que la normale
    # (GetBaseDamageFix64 ±20% dans predict_attack_raw). L'ancien chemin `get_multi_hit_attack_prediction(
    # damage=...)` (plage empirique 0.8/2.2·d/hits) etait FAUX (RE IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw : base = 1 int
    # -> ±20% [0.8/1.2], aucun 2.2) -> SUPPRIME. ⚠ La phrase « les specials Attack-based (PlasmaCannon/
    # SpiritLeech) ne passent PAS ici » est PERIMEE : #99 a REFUTE l'heredite Attack-based et retire les
    # deux du registre -- tout special passe bien ici. Le bouclier est deplete PAR COUP (prev).
    # MkXGravis (trait CIBLE 0x3f5) : armure traversee 2× aussi pour les speciales (CalculateBaseDamage
    # WithAllModifiers appele quel que soit l'ability). No-op (=1) si la cible n'a pas le trait hit-twice.
    # #267-r1 : MkXGravis lu sur l'ENTITE (`GetBaseDamageWithFixedPiercedArmor` -> HasTrait(defender, 0x3f5)),
    # comme le fait deja `_target_damage_limits` juste dessous et le COMBAT (`ctx.trait_objects()`).
    tgt_hit_mult = target_hit_multiplier(TraitFactory.create_many(_entity_traits(scene, tgt)))
    return get_attack_prediction(
        target_current_health=scene.hp(tgt) or 0, initial_damage=base, hits=hits,
        profile_type=profile_idx, pierce_pct=pierce, armor=scene.armor(tgt),
        mods=mods, target_shield=tgt_shield, hit_mult=tgt_hit_mult,
        target_limits=_target_damage_limits(scene, tgt, profile_name),
        target_prevents_overkill=scene.prevents_overkill(tgt),   # #195 : HasFlag(cible, 0x13)
        defender_block_amount=defender_prediction_block_amount(scene, tgt, profile_name),  # #69 gate NoBlocking
        attacker_effects=scene.effects(uid),   # #202 : max-out evalue DANS predict_attack_raw (specials aussi)
        attacker_ctx=ctx)                      # #R34 : MightCrit = CouldCrit(attaquant), specials aussi


# Abilities dont la PREDICTION de degat SANTE est Attack-based (== l'attaque NORMALE), PAS le config
# minDmg/maxDmg. Chemin natif (RE #92) : `IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$MakeDamagePredictions` calcule
# `IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetAttackDamage` (config) MAIS le passe a `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`,
# qui invoque le slot virtuel +0x27 (`PredictAttack`) — lequel RECALCULE Attack-based (`FindAttackWeapon`
# IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$FindAttackWeapon -> `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetAttackHitPrediction` = `GetStat(Attack,Current)`+arme), ignorant le config.
# PROUVE par le calcul : config-avg-scaled 2593 / config-max 2992 != base live 2670 / dmax live 3205 (==
# native normale(69) EXACT). Le `GetAttackDamage` config alimente le HEAL (`GetHealAmountForPrediction`)
# + le COMBAT reel (`ExecuteBehaviour`), PAS ce preview. On route donc l'event de degat principal vers
# `make_normal_attack_predictions` (mirror du slot 0x27 Attack-based : base/hits/mods/auras = la normale).
# ── Specials "Attack-based" : IL N'Y EN A AUCUN — set VIDE (reframing #99/#101a, decompile + live ;
#    detail : docs/rl/case-99-specials-attackbased-reframe.md). Prouve ARTEFACT-FREE via le RPC
#    `resolveVtableSlot` (slot vtable PredictAttack = byte 0x328) : les 5 specials audites (SpiritLeech,
#    PlasmaCannon, Doombolt, JakhalStimms, GauntletsOfUltramar) resolvent tous PredictAttack vers le STUB
#    ABSTRAIT QUI THROW `IdunBattle.Entities.Abilities.AActiveAbility$$PredictAttack` — AUCUN n'herite
#    `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$PredictAttack` (Attack-based). L'HYPOTHESE #92 « SpiritLeech
#    herite ALoki » (jamais lue au binaire) est REFUTEE. Le vrai chemin de prediction = chaque
#    `<Special>Playbook.MakeDamagePredictions → ComparablePlaybook.GenerateMultiHit(base = ability.GetAttackDamage(),
#    hits, profile)` ; `base` = CONFIG (`MinMaxDamage`) pour tous — `IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetAttackDamage`
#    = DSL `ConditionalAmount(¬HasEffect(Suppressed=1065), MinMaxDamage, +ConfigVar(8)=+1601)`, config.
# ⚠ Le "== normale 2670 bit-exact" historique (#90/#92) etait l'ARTEFACT du preview
#    `IdunBattle.Core.Services.DamagePredictionQuery$$GetAllPredictions` (Attack-based quel que soit l'abilityType — piege #96/#101a) — CONFIRME LIVE
#    (predict_sweep Neurothrope) : `aiPlaybookPredict(SpiritLeech)=[2074,3112]` (config) != `disp`/artefact
#    `GetAllPredictions=[3111,4668]`. ⇒ SpiritLeech RETIRE ; tout special passe par le chemin CONFIG generique.
#    (PlasmaCannon avait deja ete retire au #96.) La verite per-ability = `aiPlaybookPredict` (#102), JAMAIS aiPredict.
# #171/#351 — SorcerousFacade (1100, thousTzaangor) EST un membre LEGITIME (distinct des specials #99
#    ci-dessus). Son `IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$MakeDamagePredictions`
#    construit, pour la cible ENNEMIE (`TargetsSelector.SelectFirst`), un EVENT #1 = ATTAQUE NORMALE du
#    caster, via l'interface slot 0x21 — le MEME mecanisme que
#    `IdunBattle.AI.Playbook.Idun.NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$MakeDamagePredictions`
#    (= "profil d'attaque normale du caster vs target"). Ce N'EST PAS le cas #92 refute (heritage
#    vtable PredictAttack Attack-based) : ici le playbook EMET explicitement une prediction d'attaque
#    normale. Cf. docs/rl/case-171-sorcerousfacade-normal-attack.md.
#
# ⚠ LE NOM `_PREDICT_VIA_NORMAL_ATTACK` MENTAIT SUR LA STRUCTURE, et c'est ce qui a produit le residu
#    #351 (« le natif emet DEUX events, le port un seul »). Le natif ne REMPLACE pas la prediction par
#    l'attaque normale : il la MET EN TETE, puis AJOUTE le batch propre de l'ability. Relu VERBATIM sur
#    `rnca9r7q6c` (`...SorcerousFacadePlaybook$$MakeDamagePredictions`, la fin du corps) :
#
#        list = TExtensions.ToList([ new ProbableDamageEvent(sel, battleQuery.<slot 0x22>(caster, sel,
#                                                                                         casterPosition)) ])
#        list.AddRange( ComparablePlaybook<T>.GenerateMultiHitAttackPredictions(
#                           caster, casterPosition, sel,
#                           targets = DSLSelectors.Get(sel),
#                           damage  = Half(Sum(Get(GetVariableForLevel(0xc = minDmg)),
#                                              Get(GetVariableForLevel(0xd = maxDmg))), 0),
#                           hits    = GetNumberConstant(0x2f = nrOfHits),
#                           profil  = <vide>) )
#        return list
#
#    Les DEUX events portent sur `sel` (le MEME ennemi) : `AddRange` est un AJOUT, pas une substitution.
#    L'ancienne note « l'ORACLE ne remonte PAS l'event #2 (dedup aval) » est REFUTEE PAR LA MESURE
#    (#351, `probe_351_facade_event_count.py`) : `aiPlaybookPredict` rend `count = 2`, les deux events
#    sur le meme `targetId` — le decodeur `playbook-predict.ts` lit la `List<T>` entiere et ne
#    dedoublonne rien. D'ou le renommage : l'ensemble dit ce que le natif FAIT (mettre l'attaque
#    normale EN TETE), pas ce qu'on avait cru (s'y substituer).
_PREPEND_NORMAL_ATTACK_EVENT = frozenset({"SorcerousFacade"})


# ── Overrides d'ENTREE per-ability — mirror des `<Ability>Playbook.MakeDamagePredictions` qui SURCHARGENT
#    la base/hits generiques. Le natif dispatche par type d'ability (registre playbook / vtable) ; le port,
#    qui collapse tous les playbooks dans `make_damage_predictions`, dispatche par id via ce registre. Chaque
#    handler = HOMONYME du playbook natif + VA ; rend un dict `{base_override?, hits_override?, profile_override?}`
#    (kwargs de `generate_multi_hit_attack_prediction`) ou `{}`. La methode generique reste GENERIQUE : aucune
#    logique ability-specifique inline (ajouter une ability divergente = un handler + une entree registre).
#    Cle META supplementaire `aoe_overrides` (dict de MEMES kwargs) : entrees PROPRES au 2e batch, pour les
#    playbooks qui appellent `GenerateMultiHitAttackPredictions` deux fois avec des arguments differents
#    (FrenziedFiring). Consommee et RETIREE par `make_damage_predictions` — jamais transmise en kwarg.
def _martial_inspiration_inputs(scene, caster_id, target_id, ab, cfg) -> dict:  # target_id ignore (contrat registre)
    """`MartialInspirationPlaybook.MakeDamagePredictions` (yield machine `<MakeDamagePredictions>IdunBattle.AI.Playbook.Loki.MartialInspirationPlaybook.u003CMakeDamagePredictionsu003Ed__2$$MoveNext ; Kariyan/custoBladeChampion, ability 1191) — SURCHARGE la base/hits generiques (#106) :
    emet UN coup (hits=1 literal `*(puVar25+0x40)=1`) de base `round(var12 * buff)`, PAS `avg(minDmg,maxDmg)`
    sur `nrOfHits=3` config (d'ou l'ancienne sur-pred x3.3).
        var12 = minDmg (id 0xc, GetVariableForLevel, rarity-scaled) ; var10 = extraDmgPct (id 0xa, +33%/tour
        CAP, NON rarity-scaled -> mult no-op) ; buff = (var10*count + 100)/100 ; count = TotalAttacksMade
        (+0x20, capteur actorStats -- PAS TotalTurnsWithAttacksMade +0x30 qu'utilise le COMBAT GetBuffPct :
        divergence prediction<->combat portee telle quelle). count=0 debut de bataille -> buff=1 -> base=minDmg.
    slot0x10 = `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers` = `round(a*b)`. Le RESTE (x1.875
    = DamageModifiers.Multiplier attaquant ; spread +/-20% ; pierce/armure) = pipeline STANDARD en aval."""
    lvl, mult = ab.level, ab.multiplier
    minv = cfg.get_variable_for_level("minDmg", lvl, 0, mult)          # var12 (rarity-scaled)
    extra = cfg.get_variable_for_level("extraDmgPct", lvl, 0, mult)    # var10 (NON rarity -> mult no-op)
    count = scene.total_attacks_made(caster_id)                        # TotalAttacksMade (+0x20)
    buff = (extra * count + 100) / 100.0
    return {"base_override": round(minv * buff), "hits_override": 1}


def _talons_of_the_emperor_inputs(scene, caster_id, target_id, ab, cfg) -> dict:
    """`TalonsOfTheEmperorPlaybook.<MakeDamagePredictions>d__2$$MoveNext` (1195, `custoAtlacoya`
    « Atlacoya ») -- il SURCHARGE la base ET le profil, LU verbatim :

        base    = AbilityConfiguration.GetVariableForLevel(cfg, 0xc, level, null)   # minDmg SEUL
        extraN  = TalonsOfTheEmperorAbility$$GetExtraDamage(ability, level)         # un NOEUD
        extra   = IAmountFormula slot 1 (extraN, entities{ +0x08 = caster })        # caster SEUL
        prof1   = AbilityConfiguration$$GetDamageProfile(cfg)                       # damageProfile
        prof2   = AbilityConfiguration$$GetDamageProfile2(cfg)                      # damageProfile_2
        met     = TalonsOfTheEmperorAbility$$MeetSecondDamageProfileRequirement(ability)
                     .<slot>(entities{ +0x08 = caster, +0x10 = target, +0x40 = casterTile }, 0x20)
        hits    = AActiveAbility$$GetHits(ability)                                  # nrOfHits
        yield new ProbableDamageEvent(target,
                  GetAttackPrediction(caster, target, casterPosition, Nullable(AbilityOrEffect),
                                      extra + base, met ? prof2 : prof1, hits))

    DEUX ECARTS avec le chemin generique, et ils vont dans des sens OPPOSES -- c'est pourquoi
    aucune mesure scalaire ne pouvait les separer :

      1. **La BASE est `minDmg` SEUL, pas `avg(minDmg, maxDmg)`.** `GetVariableForLevel(0xc)` est
         appele DIRECTEMENT ; il n'y a AUCUN `MinMaxDamage` dans ce corps. Le generique
         SUR-evaluait donc (`1195` rejoint `HellfireShells`/`GreatFrostAxe`/`Stikkbomb`/
         `PlasmaGrenade`/`MartialInspiration` dans `_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE`, ou il
         MANQUAIT).
      2. **Un terme FLAT s'ajoute** (`extra`), que le generique ignorait -> il SOUS-evaluait.

    ⚠ **`GetHits` N'EST PAS SURCHARGE** : le natif rappelle `GetHits` (jamais `GetHits2`) et ne
    touche pas a `nrOfHits`. Aucun `hits_override` ici -- en poser un serait inventer.

    LE PROFIL EST CONDITIONNEL, DONC IL PASSE PAR CE HANDLER ET NON PAR
    `_PLAYBOOK_PROFILE_OVERRIDE`, qui ne sait porter qu'une CONSTANTE. Le predicat lui-meme n'est
    PAS re-ecrit : on appelle le foyer de la face COMBAT
    (`custodes.talons_meet_second_damage_profile_requirement`), deja confronte LIVE par #521 --
    `HasTrait(Target, Psyker) | HasFaction(<premier ami adjacent non-Steppable/Object>, Custodes)`,
    ou le volet faction porte sur **UNE** entite, la PREMIERE (mesure #521-r2 : un `any` rendait
    `DirectDamage` dans les deux regimes du couple `mixte`/`mixte_inv`).

    ⚠ **`ctx.faction_of` DOIT etre cable, sinon `HasFaction` rend `False` EN SILENCE**
    (`triggers.HasFaction.should_trigger` : `fo = ctx.faction_of ; if fo is None: return False`).
    Le substrat est le foyer `ai.action_generators._faction` (clef gameconfig `FactionId`), le MEME
    que `runner/abilities/behaviours/context.py` donne a la face COMBAT -- surtout pas
    `UnitContext.faction`, qui lit la clef `faction` et rend `None` pour les trois porteurs testes.

    DEGRADATIONS, toutes NOMMEES et toutes du cote du STATU QUO (jamais une valeur devinee) :
      * `cfg`/`ab` absents -> `{}` : le generique reprend la main ;
      * `damageProfile_2` absent de la config -> aucun `profile_override` : le natif lui-meme
         renoncerait (`Nullable<DamageProfile>` vide, cf. la face COMBAT qui rend `None`) ;
      * substrat DSL incomplet (`scene.units`/`board` vides) -> le predicat rend `False` -> profil
         `damageProfile`, la branche PAR DEFAUT du natif."""
    if ab is None or cfg is None:
        return {}
    import engine.runner.abilities.custodes as CUSTODES   # FORME B (liaison de MODULE), et le
    #   differe est CLASSE GRATUIT : charger `custodes` seul ne fait PAS atterrir ce module-ci dans
    #   `sys.modules` (mesure #974). Hisse en tete, ce serait une arete `playbook -> runner` que la
    #   couche prediction n'a nulle part ailleurs ; garde ici, il n'entraine aucune cascade au
    #   chargement. La liaison de MODULE (jamais `from ... import <nom>`) garde le point
    #   substituable par un patcheur.
    lvl, mult = ab.level, ab.multiplier
    # `GetVariableForLevel(0xc)` = `minDmg`, et RIEN d'autre : pas de moyenne min/max.
    base = cfg.get_variable_for_level("minDmg", lvl, 0, mult)
    # `GetExtraDamage` = `Multiply( ConfigVar(8 = extraDmg),
    #                               If(HasEffect(Caster, 0x58c, activeOnly = 0), EffectLevel(...), 0) )`
    per = cfg.get_variable_for_level("extraDmg", lvl, 0, mult)
    eff_state = getattr(scene, "eff_state", None)
    used = 0
    if eff_state is not None:
        # `activeOnly = 0` au call-site natif -> `by_unit` BRUT, pas `Scene.effects()` (qui filtre
        # sur `EffectComponent.IsActive`). Foyer PARTAGE avec la face COMBAT (#974).
        used = CUSTODES.talons_used_abilities_level_from_effects(
            eff_state.by_unit.get(int(caster_id), []))
    out = {"base_override": int(base or 0) + int(per or 0) * int(used)}
    consts = getattr(cfg, "constants", None) or {}
    prof_2 = consts.get("damageProfile_2")
    if prof_2:
        dctx = _talons_profile_context(scene, caster_id, target_id)
        if dctx is not None and \
                CUSTODES.talons_meet_second_damage_profile_requirement().should_trigger(dctx):
            out["profile_override"] = prof_2
    return out


def _talons_profile_context(scene, caster_id, target_id):
    """`AbilityEntities` du predicat de profil de 1195 : le natif en construit un NEUF (memset
    0x128) dont il ne renseigne que `+0x08 = caster`, `+0x10 = target` et
    `+0x40 = casterPosition.get_MainTile()`.

    Les quatre canaux que le predicat consulte reellement, et leur foyer :
      * `caster` / `target` / `caster_pos` -- `AdjacentTiles(CasterTile())` ancre sur le CASTER,
        jamais sur la cible ;
      * `board` -- sans lui `AdjacentTiles` rend `[]`, donc le volet faction serait muet ;
      * `has_trait` -- `HasTrait(Target(), Psyker)` ; meme substrat `_entity_traits` que le reste
        de la face prediction ;
      * `faction_of` -- `_faction(visualId)` (clef `FactionId`), foyer commun avec la face COMBAT.
    """
    units = getattr(scene, "units", None)
    if not units:
        return None
    from engine.ai.action_generators import _faction     # foyer UNIQUE du `FactionId` gameconfig
    by_id = {u.get("id"): u for u in units}
    caster, target = by_id.get(caster_id), by_id.get(target_id)
    if caster is None or target is None:
        return None
    return dsl.DslContext(units=units, caster=caster, target=target,
                          caster_pos=scene.pos(caster_id), board=getattr(scene, "board", None),
                          elev_by_pos=getattr(scene, "elev_by_pos", None),
                          has_trait=lambda u, t: _trait_name(t) in _entity_traits(
                              scene, (u or {}).get("id")),
                          faction_of=lambda u: _faction((u or {}).get("visualId")))


def _crushing_claws_inputs(scene, caster_id, target_id, ab, cfg) -> dict:  # target_id ignore (contrat registre)
    """`IdunBattle.AI.Playbook.Loki.CrushingClawsPlaybook$$MakeDamagePredictions` (tyranTyrantGuard, ability 1105) — la
    PREDICTION ignore le `damageProfile` de l'ability : le playbook passe **`param_8 = null`**
    (`Nullable<DamageProfile>` sans valeur) a `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`, pour la cible
    principale ET chaque splash (les DEUX appels natifs passent 0). Le profil de prediction vient de CE
    param_8 (choix du playbook), PAS de `ability.damageProfile` -> null = profil `None` (enum -1) -> **pierce 0**
    (l'armure s'applique PLEINE), au lieu du `Piercing{PiercingRatio:80}` de l'ability. C'est un quirk NATIF
    (le playbook « oublie » de passer le profil) : l'IA SOUS-evalue CrushingClaws face a une cible blindee.
        Contraste `HarvesterOfSoulsPlaybook IdunBattle.AI.Playbook.Loki.HarvesterOfSoulsPlaybook$$MakeDamagePredictions` : passe `Nullable(0x13=19=HeavyRound)` -> pierce 55
        (le port le retrouve via `ab.get_damage_profile()`, d'ou sa justesse generique).
    PROUVE LIVE (2 niveaux d'armure, base avg 1746 = (minDmg1496+maxDmg1996)/2, pierce 0) :
      - cible armure 2312 : base±20% [1397,2095] − 2312 < 0 -> plancher 1/coup -> main [2,2] / splash [1,1] EXACT.
      - cible armure 1003 : [1397−1003, 2095−1003] = [394,1092]/coup -> main(2c) [788,2184] / splash(1c) [394,1092] EXACT.
    Le port appliquait `dp.PiercingRatio=80` -> [2236,3352] (sur-prediction). Fix = mirror param_8=null =
    profil `None` (pierce 0, profile_idx -1). Cf. docs/rl/case-164-crushingclaws-pierce.md."""
    return {"profile_override": "None"}


def _hellfire_shells_inputs(scene, caster_id, target_id, ab, cfg) -> dict:
    """`IdunBattle.AI.Playbook.Loki.HellfireShellsPlaybook$$MakeDamagePredictions` (carrier NPC/summon ultraNpc4Heavy-
    Intercessor / ultraSmnHeavyIntercessor, ability 1080) — mirror parfait de `CrushingClawsPlaybook
    IdunBattle.AI.Playbook.Loki.CrushingClawsPlaybook$$MakeDamagePredictions` (meme signature, meme appel `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`). SURCHARGE :
      - BASE = `IdunBattleLogic.Entities.DSLFactory$$Direct(GetVariableForLevel(0xc=minDmg)) = minDmg SEUL (rarity-scaled), PAS
        l'avg(minDmg,maxDmg) generique (@lvl65 mult100 : minDmg 582 vs avg 727 -> generique sur-pred +145/coup).
      - HITS = `GetNumberConstant(0x2f=nrOfHits)` + (`HasTrait(target, 0x3f9=BigTarget)` ?
        `GetNumberConstant(0x2b=extraHit)` : 0) = 2 vs cible normale, 4 vs BigTarget. Litteral (PAS +ExtraHits
        stat). Trait lu sur la CIBLE (`param_4`). Concorde avec le COMBAT `HellfireShellsAbility.Execute-
        Behaviour IdunBattleLogic.Entities.Abilities.Active.Loki.HellfireShellsAbility$$ExecuteBehaviour` (meme `If(HasTrait(target,BigTarget), base+bonus, base)`).
      - PROFIL = param_8 null -> `None` (pierce 0, armure PLEINE), MEME quirk que CrushingClaws #164.
    NON mesurable live (carrier NPC campagne + summon Environment, non-spawnable via rl_duel build) -> verdict
    decompile-proof (standard #169 HarbingerOfDestruction). Cf. docs/rl/case-173-hellfire-shells-base-hits.md."""
    lvl, mult = ab.level, ab.multiplier
    base = cfg.get_variable_for_level("minDmg", lvl, 0, mult)     # var 0xc = minDmg (Direct), rarity-scaled
    hits = int((cfg.constants or {}).get("nrOfHits") or 0)        # const 0x2f = nrOfHits
    # #267-r1 : le playbook natif appelle `IdunBattle.Entities.UnitExtensions$$HasTrait(target, 0x3f9)`
    # EN DIRECT (lu au decompile) -> substrat d'ENTITE, jamais le kit par visualId.
    tgt_traits = _entity_traits(scene, target_id)
    if "BigTarget" in tgt_traits:                                # HasTrait(target, 0x3f9=BigTarget)
        hits += int((cfg.constants or {}).get("extraHit") or 0)   # const 0x2b = extraHit (+2)
    return {"base_override": base, "hits_override": hits, "profile_override": "None"}


def _tactical_precision_inputs(scene, caster_id, target_id, ab, cfg) -> dict:  # ids ignores (contrat registre)
    """`IdunBattle.AI.Playbook.Loki.TacticalPrecisionPlaybook$$MakeDamagePredictions` (1154,
    `ultraTitus`) -- les entrees de la branche NON-CHARGING (#976).

    Le playbook natif bascule sur `battleQuery.<slot 0xcd>(caster, casterPosition.MainTile, target)`
    = `IdunBattle.Core.Services.BattleQuery$$WillBeCharging` (arite **3**, LUE dans
    `data/symbols/<build>/metadata/interface_slots.tsv`) :

        CHARGING      base = VigilanceEternalAbility$$GetDamage        = MinMaxDamage(minDmg, maxDmg)
                      hits = AActiveAbility$$GetHits                   = nrOfHits
                      prof = AActiveAbility$$GetDamageProfile          = damageProfile
        NON-CHARGING  base = AActiveAbility$$MinMaxDamage2             = avg(minDmg_2, maxDmg_2)
                      hits = AActiveAbility$$GetHits2                  = GetNumberConstant(0x32 = nrOfHits_2)
                      prof = AActiveAbility$$GetDamageProfile2         = damageProfile_2

    La branche CHARGING est EXACTEMENT le chemin generique du port -> ce handler rend `{}` pour
    elle, jamais un override qui recopierait le defaut (un tel override figerait le defaut et
    survivrait a sa correction ailleurs).

    ⚠ LA BRANCHE N'EST PAS RECALCULEE ICI. Elle est LUE sur l'instance
    (`ab.tp_will_be_charging`), posee par
    `entities.abilities.active_ability.TacticalPrecisionAbility.get_aoe_targets`, que
    `make_damage_predictions` appelle AVANT ce handler. Un second calcul, meme de la meme formule,
    prendrait un SUBSTRAT different (`scene` ici, `DslContext` la-bas) et pourrait rendre l'autre
    branche : le selecteur et les entrees se contrediraient alors sans qu'aucune erreur ne sorte.
    Attribut ABSENT (ability non construite par la sous-classe) -> on rend `{}` = branche CHARGING,
    c.-a-d. le comportement d'AVANT ce port : une degradation qui ne peut rien casser de neuf.

    ⚠ `hits` est la CONSTANTE NUE. `AActiveAbility$$GetHits2` est `GetNumberConstant(0x32)` et rien
    d'autre -- pas de `GetDefaultAttackHits`, donc ni `ExtraHits` ni `ExtraHitsMelee`. C'est le
    corps qui le dit, pas une symetrie avec `get_hits`.

    La base suit la forme **(b)** (`RandomAmount` puis slot 4 `CalculateAverage` = TRONCATURE) : la
    branche NON-CHARGING passe par `MinMaxDamage2`, dont le corps est le jumeau exact de
    `MinMaxDamage` a la paire de variables pres, et 1154 est deja rangee en (b) dans
    `_PREDICTION_MINMAX_AVERAGE` (registre `_A_VIA_VIGILANCE_ETERNAL_GET_DAMAGE`) pour sa branche
    CHARGING. Les deux branches partagent donc l'arrondi -- lu, pas suppose : le playbook prend le
    meme slot 4 sur les deux formules."""
    if not getattr(ab, "tp_will_be_charging", True):
        lvl, mult = ab.level, ab.multiplier
        mn = cfg.get_variable_for_level("minDmg_2", lvl, 0, mult)   # var 0x36 = minDmg_2
        mx = cfg.get_variable_for_level("maxDmg_2", lvl, 0, mult)   # var 0x37 = maxDmg_2
        out = {"base_override": calculate_average(mn, mx),
               "hits_override": int((cfg.constants or {}).get("nrOfHits_2") or 0)}
        prof = (cfg.constants or {}).get("damageProfile_2")
        if prof:
            out["profile_override"] = prof                          # `GetDamageProfile2`
        return out
    return {}                                                       # branche CHARGING = defaut


def _brazier_of_holy_fire_inputs(scene, caster_id, target_id, ab, cfg) -> dict:
    """`IdunBattle.AI.Playbook.Loki.BrazierOfHolyFirePlaybook$$MakeDamagePredictions` (ability 1041,
    `adeptCanoness`) -- HITS CONDITIONNELS AU TRAIT DE LA CIBLE (#945).

    Le playbook n'appelle PAS `AActiveAbility$$GetHits` : il evalue la formule
    `IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$GetNumberOfHits`
    (`ConditionalAmount(HasTrait(target, 0x3fb = UnitTrait.Daemon), nrOfHits_2, nrOfHits)`) sur un
    `AbilityEntities` dont la cible est `param_4`, puis passe le RESULTAT BRUT en 7e argument de
    `ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions`. Deux consequences, toutes deux
    absentes du chemin generique :

      * config `rnca9r7q6c` : `nrOfHits = 2`, `nrOfHits_2 = 4` -> **4 coups contre un Daemon**, 2
        sinon. Le port en predisait 2 dans les deux cas, soit la MOITIE du degat face aux 24 unites
        `Daemon` du gameconfig ;
      * `GetDefaultAttackHits` (donc `ExtraHits` / `ExtraHitsMelee`) n'intervient PAS -- le chemin
        generique l'appliquait. Meme quirk et meme correctif que `_hellfire_shells_inputs` (#173).

    La BASE n'est pas surchargee : `<BrazierOfHolyFireAbility>$$GetDamageAmountMain` est le corps
    DEDUPLIQUE etiquete `StranglethornCannonAbility$$GetDamageAmountMain` ->
    `AActiveAbility$$MinMaxDamageAverage`, et 1041 figure DEJA dans
    `entities.abilities.active_ability._A_VIA_GET_DAMAGE_AMOUNT_MAIN` (#344) : `ab.get_damage()`
    rend deja la moyenne demi-vers-le-pair. Le PROFIL non plus (`Flame` de la config).

    Le trait est lu sur l'ENTITE cible (`_entity_traits`, #267-r1), jamais sur le kit par visualId
    -- le natif appelle `DSLTriggers.HasTrait(<Entity(target)>, ...)` en direct.

    Formule portee dans `entities.abilities.active_ability.BrazierOfHolyFireAbility.
    get_number_of_hits` (mirror 1:1 de la methode d'ABILITY native), consommee ici : le registre
    `_SPECIAL_ABILITY_CLASSES` fait que `ab` EST une `BrazierOfHolyFireAbility`. Si un autre
    chemin instanciait la base, `hits <= 0` -> aucun override (statu quo, jamais un chiffre faux)."""
    fn = getattr(ab, "get_number_of_hits", None)
    if fn is None:
        return {}
    hits = int(fn(_entity_traits(scene, target_id)))
    return {"hits_override": hits} if hits > 0 else {}


def _great_frost_axe_inputs(scene, caster_id, target_id, ab, cfg) -> dict:  # target_id ignore (contrat registre)
    """`IdunBattle.AI.Playbook.Loki.GreatFrostAxePlaybook$$MakeDamagePredictions` (ability 1089) — BASE =
    `Get(GetVariableForLevel(0xc=minDmg, state))` = **minDmg SEUL** (rarity-scaled), PAS l'avg
    (minDmg+maxDmg)/2 generique. hits = GetNumberConstant(0x2f=nrOfHits=4) et profil =
    GetDamageProfile config (Piercing 80) = identiques au chemin generique -> pas d'override.
    Mesure 54321 s18 (u85 ab1089 -> t93) : off avg-based [4020,6032] vs nat minDmg-based
    [3576,5364] — centres per-hit 1256.4 vs 1117.5, ratio = (1+1.25)/2 = le maxDmg/minDmg
    config exact. Meme mold que HellfireShells #173 (Direct minDmg). #57e."""
    lvl, mult = ab.level, ab.multiplier
    base = cfg.get_variable_for_level("minDmg", lvl, 0, mult)     # var 0xc = minDmg (Get), rarity-scaled
    return {"base_override": base}


def _stikkbomb_inputs(scene, caster_id, target_id, ab, cfg) -> dict:  # target_id ignore (contrat registre)
    """`IdunBattle.AI.Playbook.Loki.StikkbombPlaybook$$MakeDamagePredictions` (ability 1051,
    orksOrkBoys / orksNpc2OrkBoy) — event PRINCIPAL. Deux SURCHARGES des entrees generiques, toutes
    deux lues au call-site :

      - BASE = `IdunBattleLogic.Entities.DSLFormulas$$Get(GetVariableForLevel(config, 0xc = minDmg))`
        = **minDmg SEUL** (rarity-scaled), PAS l'avg(minDmg, maxDmg) generique. La surcharge
        `DSLFormulas$$Get(this, amount)` a le MEME corps (meme classe instanciee, meme ctor) que
        `IdunBattleLogic.Entities.DSLFormulas$$Direct` : c'est le noeud `DirectAmount`. Meme mold que
        `_hellfire_shells_inputs` (#173) et `_great_frost_axe_inputs` (#57e).
        ⚠ CONTRASTE avec la face COMBAT : `...StikkbombAbility$$ExecuteBehaviour` passe, lui,
        `DSLFormulas$$RandomAmount(minDmg 0xc, maxDmg 0xd)` — le playbook de PREDICTION est plus
        pessimiste que l'execution. Ce n'est pas une incoherence de port : ce sont deux call-sites
        natifs distincts.
      - HITS = `GetNumberConstant(0x2f = nrOfHits)` **LITTERAL** (7e arg du call-site). Le chemin
        generique passe par `ab.get_special_hits` = `GetDefaultAttackHits(nrOfHits, ExtraHits, ...)`,
        qui AJOUTE la stat `ExtraHits` du caster — que ce playbook n'ajoute pas. Sans ExtraHits les
        deux coincident ; avec (les Orks en gagnent 1 par `Waaagh`) ils divergent.

    Le PROFIL n'est pas surcharge : le playbook passe `GetDamageProfile(config)` -> `Nullable` NON
    vide (Blast), pas le quirk `param_8 = null` de #164/#165."""
    lvl, mult = ab.level, ab.multiplier
    base = cfg.get_variable_for_level("minDmg", lvl, 0, mult)      # var 0xc = minDmg (Get == Direct)
    hits = int((cfg.constants or {}).get("nrOfHits") or 0)         # const 0x2f = nrOfHits (LITTERAL)
    out = {"base_override": base}
    if hits:
        out["hits_override"] = hits
    return out


def _plasma_grenade_inputs(scene, caster_id, target_id, ab, cfg) -> dict:  # target_id ignore (contrat registre)
    """`IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$MakeDamagePredictions` (ability 1098,
    `eldarSmnGuardian` / `eldarNpc1Guardian`) — event PRINCIPAL. MEME mold que `_stikkbomb_inputs`
    (#57e/#173), relu ability par ability sur `rnca9r7q6c` et NON deduit de la voisine :

        damage  = IdunBattleLogic.Entities.DSLFormulas$$Get(GetVariableForLevel(config, 0xc = minDmg, state))
        hits    = GetNumberConstant(config, 0x2f = nrOfHits)
        hits2   = GetNumberConstant(config, 0x32 = nrOfHits_2)      // volet secondaire (cf. playbook)
        profile = GetDamageProfile(config)                          // Nullable NON vide (Plasma)
        list    = GenerateMultiHitAttackPredictions(caster, casterPosition, target, <selecteur Target>,
                                                    damage, hits, profile, null, 0)

    DEUX surcharges des entrees generiques, toutes deux lues au call-site :

      - BASE = **minDmg SEUL** (rarity-scaled), PAS l'avg(minDmg, maxDmg) generique. La surcharge
        `DSLFormulas$$Get(this, amount)` a le MEME corps que `IdunBattleLogic.Entities.DSLFormulas$$Direct`
        (noeud `DirectAmount`). Config 1098 @lvl65 mult100 : minDmg 509 vs avg tronque 618
        -> le generique SUR-predisait de +109 par coup.
        CONTRASTE avec la face COMBAT : `...PlasmaGrenadeAbility$$ExecuteBehaviour` passe, lui,
        `RandomAmount(minDmg 0xc, maxDmg 0xd)` -- deux call-sites natifs distincts, pas une
        incoherence de port (meme forme que Stikkbomb #57e).
      - HITS = `GetNumberConstant(0x2f = nrOfHits)` **LITTERAL** (7e arg du call-site). Le chemin
        generique passe par `ab.get_special_hits` = `GetDefaultAttackHits(nrOfHits, ExtraHits, ...)`,
        qui AJOUTE la stat `ExtraHits` du caster -- que ce playbook n'ajoute pas.

    Le PROFIL n'est pas surcharge : `GetDamageProfile(config)` -> `Nullable` NON vide (Plasma), pas
    le quirk `param_8 = null` de #164/#165.

    ⚠ LE VOLET SECONDAIRE DE CE PLAYBOOK EST MORT -- ne pas le « reparer ». Le playbook boucle bien
    sur `TargetsSelector.SelectUniqueUnits(...GetOtherTargets, entities, 3)` avec `hits2`, mais il
    construit son contexte par
    `AbilityEntities..ctor(entities, caster: 0, actor: 0, target: target, ...)` -- **caster NUL**.
    Or `...PlasmaGrenadeAbility$$GetOtherTargets` = `Enemies(caster@0x30, AdjacentUnits(Target@0x60,
    1, 3), 1)` filtre par l'equipe du CASTER : le set est donc TOUJOURS vide, et 1098 n'emet JAMAIS
    qu'UN event. C'est la difference avec Stikkbomb (1051), dont le set
    `...StikkbombAbility$$GetAdjacentDamageTargets` = `AdjacentUnits(Target, unique, sel)` ne depend
    que de `Target` et reste VIVANT (son volet est porte dans
    `engine.playbook.loki_custom.StikkbombPlaybook.make_damage_predictions`).
    MESURE (`probe_352_grenade_prediction_base.py`, MEME geometrie -- 2 ennemis colles a la cible,
    deux couples board/seed) : natif 1051 = **3 events**, natif 1098 = **1 event**. Le port, qui
    n'en emet qu'un, est donc FIDELE ; y ajouter un volet le rendrait FAUX."""
    lvl, mult = ab.level, ab.multiplier
    base = cfg.get_variable_for_level("minDmg", lvl, 0, mult)      # var 0xc = minDmg (Get == Direct)
    hits = int((cfg.constants or {}).get("nrOfHits") or 0)         # const 0x2f = nrOfHits (LITTERAL)
    out = {"base_override": base}
    if hits:
        out["hits_override"] = hits
    return out


def _fragstorm_grenade_launcher_inputs(scene, caster_id, target_id, ab, cfg) -> dict:  # ids ignores (contrat registre)
    """`IdunBattle.AI.Playbook.Loki.FragstormGrenadeLauncherPlaybook$$MakeDamagePredictions`
    (ability 1048, `templAggressor` « Burchard ») — event PRINCIPAL.

    Ce playbook n'appelle PAS
    `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions` :
    il appelle DIRECTEMENT la surcharge « amount » de `IBattleQuery.GetAttackPrediction` (slot
    d'interface 0x24, la meme interface `Playbook<T>+0x28` que le generique, qui prend son slot 0x28) :

        maxDmg = GetVariableForLevel(config, 0xd = maxDmg, state);
        hits   = GetNumberConstant(config, 0x2f = nrOfHits);
        result = battleQuery.GetAttackPrediction(caster, target, casterPosition,
                                                 Nullable(AbilityOrEffect(ability)),
                                                 amount: hits * maxDmg,          // PRODUIT
                                                 GetDamageProfile(config), null, default);
        return new[] { new ProbableDamageEvent(target, result, null, null) }.ToList();

    DEUX lectures, aucune ne se devine :

      1. **La BASE est le PRODUIT `nrOfHits x maxDmg`, pas une moyenne.** Config 1048 @lvl65 mult100 :
         `6 x 2183 = 13098`, la ou le generique rendait `avg(1746, 2183) = 1964` (troncature).
      2. **Le nombre de coups est 1, LITTERAL** -- et c'est la surcharge appelee qui le pose, pas le
         playbook : `IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction` (forme « amount »,
         sans parametre `hits`) transmet `hits: 1` en dur a
         `IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction`
         (forme `(caster, casterPosition, target, ability, initialDamage, hits, damageProfile,
         defenderInitialHealth, previousHitsPrediction)`). Le generique, lui, passe les `nrOfHits`
         coups au slot 0x28.

    L'ecart n'est donc PAS un arrondi mais une GRANDEUR et une STRUCTURE : `1 x 13098` contre
    `6 x 1964`. Les deux ne coincident sur AUCUN axe -- ni le centre (13098 vs 11784), ni surtout
    l'armure, soustraite UNE fois au lieu de SIX (`predict_attack_raw` deduit l'armure par coup).

    ⚠ LE VOLET SECONDAIRE DE CE PLAYBOOK EST MORT LUI AUSSI -- ne pas le porter. Sous le gate
    `result.WillBeKill`, le playbook boucle sur
    `SelectUniqueUnits(...FragstormGrenadeLauncherAbility$$GetOtherTargets, entities, 3)`, mais son
    `entities` est un **memset(0) COMPLET** (`FUN_1802abdd0(&local_248, 0, 0x128)`) : ni caster ni
    target. Or ce set vaut
    `Damageable(SurroundingEnemies(caster@0x30, ConfigConst(0x16), 1, 3) - Target@0x60)` -- il
    depend des DEUX. Le set est donc toujours vide.
    MESURE (`probe_352_grenade_prediction_base.py`) : sur un montage ou le gate `WillBeKill` est
    FRANCHI (le natif rend `min == max == PV de la cible`) et ou deux ennemis sont a portee 2 du
    caster, le natif rend **1 event**. Le port, qui n'en emet qu'un, est FIDELE.
    Second quirk lu au passage, et sans effet tant que le set est vide : dans cette boucle le natif
    passe l'unite ITEREE en `caster` et garde `target` en cible (verifie a l'assembleur -- `r8` recoit
    `IEnumerator.get_Current()`, `r9` le home slot du 4e parametre), alors que le batch principal y
    passe le vrai `caster`. Les arguments sont inverses cote natif.

    Config absente -> `{}` = chemin generique inchange (aucune sur-prediction inventee), meme
    convention que `_frenzied_firing_inputs` / `_mass_driver_accelerator_inputs`. `nrOfHits` absent
    est IMPOSSIBLE nativement (`GetNumberConstant` THROW sur cle manquante) : garde-fou offline."""
    lvl, mult = ab.level, ab.multiplier
    mx = cfg.get_variable_for_level("maxDmg", lvl, 0, mult)        # var 0xd = maxDmg (rarity-scaled)
    hits = int((cfg.constants or {}).get("nrOfHits") or 0)         # const 0x2f = nrOfHits
    if not mx or not hits:
        return {}
    return {"base_override": int(mx) * hits, "hits_override": 1}


def make_secondary_multihit_event(scene, caster_id, target_id, ability_id, ability_name, attack_pos):
    """UN event de degat du VOLET SECONDAIRE d'une ability a splash — c'est-a-dire **sur la CIBLE
    PRINCIPALE**, avec le nombre de coups SECONDAIRE (`nrOfHits_2`) et la base `minDmg` SEULE.

    Trois playbooks natifs fabriquent cet event avec EXACTEMENT le meme call-site (memes 4 entrees :
    `Get(GetVariableForLevel(0xc = minDmg))`, `GetNumberConstant(0x32 = nrOfHits_2)`,
    `GetDamageProfile(config)`, selecteur `Target`) — d'ou UN SEUL foyer parametre par ability :

    - `IdunBattle.AI.Playbook.Loki.StikkbombPlaybook$$MakeDamagePredictions` (1051, cote ENNEMIS
      adjacents a la cible) ;
    - `IdunBattle.AI.Playbook.Loki.StikkbombPlaybook$$CalculateCustomUtility` (1051, cote AMIS) ;
    - `IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$CalculateCustomUtility` (1098, cote ENNEMIS
      adjacents a la cible).

    Les boucles natives appellent `...ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions` avec
    EXACTEMENT les memes arguments a chaque tour de boucle :

        GenerateMultiHitAttackPredictions(caster, casterPosition,
                                          target,                       // param_4
                                          <selecteur Target>,           // param_5 = DSLSelectors@0x60
                                          Get(minDmg), GetNumberConstant(0x32 = nrOfHits_2),
                                          GetDamageProfile(), null, null)

    `param_4` est la CIBLE PRINCIPALE et **jamais l'unite splash iteree** : lu au DECOMPILE puis
    CONFIRME a l'assembleur (`mov r9,[rsp+0x578]`, ou `rsp+0x578` est le home slot du 4e parametre
    ecrit par le prologue `mov [rax+0x20],r9` avec `rax = rsp_entree` et
    `rsp_courant = rsp_entree - 0x38 (7 push) - 0x520 (sub rsp)` ; meme lecture dans
    `MakeDamagePredictions`, `mov r9,[rsp+0x4a8]` avec `- 0x38 - 0x450`). Or dans
    `GenerateMultiHitAttackPredictions` le `param_4` ne sert qu'a peupler le contexte
    `AbilityEntities` (`Target` + `GetTiles(target)`) : ce sont les entites rendues par le SELECTEUR
    `param_5` qui recoivent les predictions. Avec `param_5` = le selecteur `Target`, la liste rendue
    vaut donc `[target]` a CHAQUE tour de boucle.

    => l'unite splash ne determine QUE le NOMBRE d'events ; leur contenu est invariant. Ce helper le
    calcule UNE fois, l'appelant le repete `n` fois (mirror numeriquement exact de la boucle native,
    sans en payer le cout N fois). Le cas 1098 est un mirror LITTERAL de cette invariance : sa boucle
    RECONSTRUIT la meme liste de predictions a chaque ennemi adjacent, sans qu'aucun argument ne
    depende de l'ennemi itere.

    None si la prediction est indisponible (scene/config incompletes) -> l'appelant degrade en no-op."""
    cfg = AbilityConfiguration.from_gameconfig(ability_name, GC.ability(ability_name))
    ctx0 = scene.ctx(caster_id) if scene is not None else None
    if cfg is None or ctx0 is None:
        return None
    ab = active_ability_for(ability_name, ability_id, ctx0, cfg,
                            ability_state=scene.ability_state(caster_id, ability_id))
    if ab is None:
        return None
    lvl, mult = ab.level, ab.multiplier
    base = cfg.get_variable_for_level("minDmg", lvl, 0, mult)       # var 0xc = minDmg (Get == Direct)
    hits = int((cfg.constants or {}).get("nrOfHits_2") or 0)        # const 0x32 = nrOfHits_2
    if not hits:
        return None
    dp = generate_multi_hit_attack_prediction(scene, caster_id, target_id, ability_id, ability_name,
                                              attack_pos=attack_pos, base_override=base,
                                              hits_override=hits)
    return ProbableDamageEvent(target=target_id, prediction=dp) if dp is not None else None


def _frenzied_firing_inputs(scene, caster_id, target_id, ab, cfg) -> dict:
    """`IdunBattle.AI.Playbook.Loki.FrenziedFiringPlaybook$$MakeDamagePredictions` (ability 1036,
    blackObliterator « Volk ») — le nb de coups de l'event PRINCIPAL n'est PAS `nrOfHits` : le playbook
    evalue le noeud `IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$GetHitsForOriginalTarget`
    et le passe en 7e arg de `GenerateMultiHitAttackPredictions`. Transcription EXACTE de l'arbre natif :

        Min( Cache( Sum( Get(GetHits),                       # GetHits = GetNumberConstant(0x2f=nrOfHits)=1
                         Count( Filter( Walkable(AdjacentTiles(target@0x178)),
                                        Not(HasUnit(tile)) | Not(AreEnemies(Units(tile), caster@0x160)) ) ) ) ),
             ConfigConst(0x48 = maxNrOfHits) )

    = `nrOfHits` + le nombre de tuiles ADJACENTES A LA CIBLE qui sont marchables ET **pas occupees par un
    ennemi du caster** (une tuile vide compte ; une tuile tenue par un ALLIE du caster compte AUSSI —
    seule la presence d'un ennemi l'exclut), plafonne a `maxNrOfHits`. C'est donc une base GEOMETRIQUE :
    plus la cible est degagee, plus Volk la crible.

    GROUND TRUTH live (case-61, runner isole, board MC1_67, oracle `aiPlaybookPredict.appliedHits`) :
      - cible en plein champ, 6 voisins marchables, 1 ALLIE du caster sur l'un d'eux -> natif **7** = 1+6
        (l'allie ne retranche RIEN) ;
      - un ENNEMI place sur un voisin -> natif **6** = 1+5 ; deplacer l'allie d'un voisin a un autre ne
        change RIEN (toujours 6) ; un CADAVRE sur un voisin ne compte pas comme unite (tuile comptee).
    Le port rendait **1** (= `nrOfHits` config seul) dans TOUS les cas -> l'IA sous-estimait FrenziedFiring
    d'un facteur ~7. C'est la vraie cause du datapoint « 4 ou 5 selon la cible » de #87 (geometrie), et non
    un effet de la cible : ni `Diminutive` ni `Camouflage` ne modifient ce compte (le canal de coups n'est
    PAS interpose en prediction, cf. `services/attack_hits_formula.py`).

    Vivants seulement (`Units(tile)` = occupation REELLE ; `decisionView` garde les cadavres, cf. #57m).
    Board/positions absents -> `{}` = base generique (degradation fidele, aucune sur-prediction).

    VOLET AoE (2e batch, porte) : le playbook enchaine un SECOND
    `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`
    sur `IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$GetTargets` (= ennemis du
    caster adjacents a la CIBLE, `get_aoe_targets` de `FrenziedFiringAbility`) avec `hits = 1` **LITTERAL**
    (7e arg immediat du call-site : le natif n'evalue AUCUN noeud de coups pour ce batch — `nrOfHits`
    vaut 1 en config, mais le recopier serait une coincidence, pas un mirror), puis CONCATENE ses events
    dans la liste du 1er batch. Meme `GetDamageFormula` et meme `Nullable(GetDamageProfile)` que le batch
    d'origine -> `aoe_overrides` ne surcharge QUE les coups. `param_10` (poids Fix64) = 0 sur les deux
    batchs -> probabilite 1, aucune ponderation `GetMaxSecondaryTargets`.

    L'ARBRE de coups est celui de `FrenziedFiringAbility.get_hits_for_original_target` (DEFINITION
    UNIQUE, partagee avec la face COMBAT `runner/abilities/blacklegion.py` — un seul artefact natif,
    un seul port). Ce handler ne fait que lui fournir son `DslContext` (units/caster/target/board de
    la SCENE) et les deux constantes de config resolues."""
    board = getattr(scene, "board", None)
    n = int((cfg.constants or {}).get("nrOfHits") or 0)          # Get(GetHits) = GetNumberConstant(0x2f)
    cap = int((cfg.constants or {}).get("maxNrOfHits") or 0)     # ConfigConst 0x48
    # `hits = 1` LITTERAL du 2e batch — porte par la classe d'ability (constante native, pas config).
    aoe = {"aoe_overrides": {"hits_override": FrenziedFiringAbility.AOE_HITS}}
    by_id = {u.get("id"): u for u in (scene.units or [])}
    caster, target = by_id.get(caster_id), by_id.get(target_id)
    # Board/positions/constantes absents -> `{}` = base generique (degradation fidele, aucune
    # sur-prediction). `cap` absent est IMPOSSIBLE nativement (`GetNumberConstant` THROW sur cle
    # manquante) : la garde est un garde-fou offline, pas une branche native.
    if board is None or caster is None or target is None or not scene.pos(target_id) \
            or not n or not cap:
        return aoe
    dctx = dsl.DslContext(units=scene.units, caster=caster, target=target, board=board)
    # Min(., ConfigConst(maxNrOfHits)) pour le batch d'ORIGINE ; `aoe_overrides` garde hits=1.
    hits = int(FrenziedFiringAbility.get_hits_for_original_target(n, cap).evaluate(dctx))
    return {"hits_override": hits, **aoe}


def _savage_echoes_inputs(scene, caster_id, target_id, ab, cfg) -> dict:  # target_id ignore (contrat registre)
    """`IdunBattle.AI.Playbook.Loki.SavageEchoesPlaybook$$MakeDamagePredictions` (ability 1230,
    bloodTerminator « Cezare ») — SURCHARGE la BASE : le playbook ne passe PAS la
    `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage` generique en 6e arg de
    `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`,
    mais la formule PROPRE de l'ability,
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$GetDamage` :

        Sum( MinMaxDamage(minDmg 0xc, maxDmg 0xd),                   # = `ab.get_damage()` (avg)
             Multiply( Get(GetVariableForLevel(config, 8 = extraDmg)),
                       Count( CanAddUnit( AdjacentTiles(Owner@0x148) ) ) ) )

    Le terme `extraDmg x <nb de tuiles adjacentes LIBRES du porteur>` etait IGNORE par le chemin de
    prediction generique (qui s'arrete a `MinMaxDamage`), alors que la face COMBAT le porte deja
    (`runner/abilities/bloodangels.py`) — l'IA SOUS-evaluait donc systematiquement SavageEchoes.

    Les 3 autres entrees du call-site sont generiques (relues au decompile du playbook, aucune n'est
    surchargee) : profil = `AActiveAbility$$GetDamageProfile` -> `Nullable` NON vide (Eviscerate, PAS le
    quirk `param_8 = null` de #164/#165) ; hits = `ArmoriumCherubAbility$$GetHits`
    = `GetNumberConstant(0x2f = nrOfHits)` ; cibles = `DSLFactory$$Entity(target)` -> mono-cible.

    L'ARBRE est celui de `SavageEchoesAbility.get_damage_formula` (DEFINITION UNIQUE, partagee avec la
    face COMBAT — un seul artefact natif, un seul port). Ce handler ne fait que lui fournir son
    `DslContext` (units/caster/board de la SCENE) et les deux valeurs resolues : `ab.get_damage()`
    (l'avg config rarity-scaled) et `extraDmg` au niveau PER-ABILITY.

    Board/positions absents -> `{}` = base generique (degradation fidele, aucune sur-prediction),
    meme convention que `_frenzied_firing_inputs`."""
    board = getattr(scene, "board", None)
    by_id = {u.get("id"): u for u in (scene.units or [])}
    caster = by_id.get(caster_id)
    if board is None or caster is None or scene.pos(caster_id) is None:
        return {}
    lvl, mult = ab.level, ab.multiplier
    extra = cfg.get_variable_for_level("extraDmg", lvl, 0, mult)   # var 8 = extraDmg (rarity-scaled)
    dctx = dsl.DslContext(units=scene.units, caster=caster, target=by_id.get(target_id), board=board)
    base = SavageEchoesAbility.get_damage_formula(ab.get_damage(), extra).evaluate(dctx)
    return {"base_override": int(base)}


def _mass_driver_accelerator_inputs(scene, caster_id, target_id, ab, cfg) -> dict:  # ids ignores (contrat registre)
    """`IdunBattle.AI.Playbook.Loki.MassDriverAcceleratorPlaybook$$MakeDamagePredictions` (ability 1222,
    votanChampion « Kimm ») — le volet SPLASH **par ennemi adjacent a la CIBLE**, jamais chiffre jusqu'ici.

    Le playbook enchaine DEUX batchs `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`
    et concatene le second dans la liste du premier (`List.AddRange` en boucle) :

        damage = <GetDamage>                                  // AActiveAbility$$MinMaxDamage(state, isPrediction: false)
        list   = GenerateMultiHitAttackPredictions(caster, casterPosition, target, <Target>,
                     damage, AActiveAbility$$GetHits, Nullable(AActiveAbility$$GetDamageProfile), null, 0)
        foreach (e in <GetAdjacentAttackTargets>.Select(AbilityEntities(caster: caster, target: target)))
            list.AddRange( GenerateMultiHitAttackPredictions(caster, casterPosition, e,
                               DSLSelectors$$Entity(e), damage, AActiveAbility$$GetHits2,
                               Nullable(AActiveAbility$$GetDamageProfile2), null, 0) )
        return list;

    Le SET et les trois lectures de RE qui le gouvernent (splash porte sur l'ENNEMI et pas sur la cible ;
    degat = celui du batch PRINCIPAL et non `MinMaxDamage2` ; seuls coups+profil changent) sont
    documentes sur `MassDriverAcceleratorAbility` -- ce handler ne fait que RESOUDRE les entrees :

      - **batch PRINCIPAL** : `hits` = `AActiveAbility$$GetHits` = `GetNumberConstant(0x2f = nrOfHits)`
        **LITTERAL**. Le chemin generique passe, lui, par `ab.get_special_hits` =
        `GetDefaultAttackHits(nrOfHits, ExtraHits[, Melee])`, qui AJOUTE la stat `ExtraHits` du caster --
        que ce playbook n'ajoute pas (meme ecart, meme correctif que `_stikkbomb_inputs`). Sans
        `ExtraHits` les deux coincident ; avec, ils divergent. La BASE et le PROFIL du batch principal
        restent generiques (`MinMaxDamage` -> `ab.get_damage()` ; `Nullable(GetDamageProfile)` NON vide
        -> `damageProfile` = DirectDamage), donc aucun override.
      - **batch SPLASH** (`aoe_overrides`) : `hits` = `AActiveAbility$$GetHits2` =
        `GetNumberConstant(0x32 = nrOfHits_2)` et `profil` = `AActiveAbility$$GetDamageProfile2` =
        `AbilityConfiguration$$GetDamageProfile2` = `GetEnumConstant(0x3f = damageProfile_2)`. La base
        n'est PAS surchargee : elle est HERITEE du batch principal, ce qui est exactement le mirror du
        `param_6` partage (relire le point 2 de `MassDriverAcceleratorAbility`).

    C'est le profil qui rend le volet OBSERVABLE : sur 1222, `damageProfile` = `DirectDamage` et
    `damageProfile_2` = `Physical` -- deux `PiercingRatio` distincts, donc un degat predit distinct
    contre une meme armure. Les coups, eux, sont egaux (1 et 1), et `minDmg_2`/`maxDmg_2` egaux a
    `minDmg`/`maxDmg` : le volet ne se distingue NI par les coups NI par la base, seulement par le
    profil et par la CIBLE (chaque ennemi adjacent recoit SON propre event, contre SES PV/armure).

    Config absente -> `{}` = chemin generique inchange (aucune sur-prediction inventee), meme
    convention que `_frenzied_firing_inputs` / `_savage_echoes_inputs`."""
    consts = (cfg.constants or {}) if cfg is not None else {}
    hits = int(consts.get("nrOfHits") or 0)          # const 0x2f = nrOfHits (LITTERAL, batch principal)
    hits2 = int(consts.get("nrOfHits_2") or 0)       # const 0x32 = nrOfHits_2 (batch SPLASH)
    prof2 = consts.get("damageProfile_2")            # const 0x3f = damageProfile_2 (batch SPLASH)
    out: dict = {}
    if hits:
        out["hits_override"] = hits
    aoe: dict = {}
    if hits2:
        aoe["hits_override"] = hits2
    if prof2:
        aoe["profile_override"] = prof2
    if aoe:
        out["aoe_overrides"] = aoe
    return out


def _frag_bomb_inputs(scene, caster_id, target_id, ab, cfg) -> dict:  # ids ignores (contrat registre)
    """`IdunBattle.AI.Playbook.Loki.FragBombPlaybook$$MakeDamagePredictions` (ability 1017,
    `astraBullgryn` « Kut Skoden ») -- le volet SPLASH **par unite adjacente a la CIBLE**, jamais
    chiffre jusqu'ici. MEME forme que `_mass_driver_accelerator_inputs`, a DEUX ecarts pres, LUS :

      - le SET n'a AUCUN wrapper `Enemies` (`AdjacentUnits` NU moins le caster) -> FRIENDLY-FIRE.
        Il vit sur `FragBombAbility._AOE` (`entities/abilities/active_ability.py`), avec sa RE ;
      - le `param_8` (`Nullable<DamageProfile>`) est **0 sur les DEUX batchs** : il n'y a donc PAS de
        `profile_override` propre au splash. Le profil VIDE est deja porte pour les deux par
        `_PLAYBOOK_PROFILE_OVERRIDE[FragBomb] = "None"` (#168, valide live) -- l'ajouter ici le
        dupliquerait.

    Ce handler ne resout donc que les COUPS :

      - **batch PRINCIPAL** : `hits` = `AActiveAbility$$GetHits` = `GetNumberConstant(0x2f =
        nrOfHits)` **LITTERAL** (= 6 sur cette config). Le chemin generique passe, lui, par
        `ab.get_special_hits` = `GetDefaultAttackHits(nrOfHits, ExtraHits[, Melee])`, qui AJOUTE la
        stat `ExtraHits` du caster -- que ce playbook n'ajoute pas (meme ecart, meme correctif que
        `_stikkbomb_inputs` / `_mass_driver_accelerator_inputs`). Sans `ExtraHits` les deux
        coincident, ce qui explique que la mesure #168 ait valide `[6, 6]` sans le voir.
      - **batch SPLASH** (`aoe_overrides`) : `hits` = `AActiveAbility$$GetHits2` =
        `GetNumberConstant(0x32 = nrOfHits_2)` (= 3). La BASE n'est PAS surchargee : elle est
        HERITEE du batch principal, mirror du `param_6` partage (le playbook evalue
        `GetDamageAmountMain` UNE fois, hors boucle).

    Config absente -> `{}` = chemin generique inchange (aucune sur-prediction inventee)."""
    consts = (cfg.constants or {}) if cfg is not None else {}
    hits = int(consts.get("nrOfHits") or 0)          # const 0x2f = nrOfHits (LITTERAL, batch principal)
    hits2 = int(consts.get("nrOfHits_2") or 0)       # const 0x32 = nrOfHits_2 (batch SPLASH)
    out: dict = {}
    if hits:
        out["hits_override"] = hits
    if hits2:
        out["aoe_overrides"] = {"hits_override": hits2}
    return out


def _ramming_speed_inputs(scene, caster_id, target_id, ab, cfg) -> dict:  # ids ignores (contrat registre)
    """`IdunBattle.AI.Playbook.Loki.RammingSpeedPlaybook$$MakeDamagePredictions` (ability 1059) --
    batch de la CIBLE PRINCIPALE. DEUX surcharges, lues au call-site :

      - BASE = `IdunBattleLogic.Entities.DSLFormulas$$Get(GetVariableForLevel(config, 0xc = minDmg,
        abilityState))` = **minDmg SEUL** (rarity-scaled), PAS l'avg(minDmg, maxDmg) generique. Meme
        mold que `_great_frost_axe_inputs` (#57e), `_stikkbomb_inputs` et `_hellfire_shells_inputs`
        (#173). ⚠ CONTRASTE avec la face COMBAT :
        `IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$ExecuteBehaviour` passe
        `DSLFormulas$$RandomAmount(minDmg 0xc, maxDmg 0xd)` -- deux call-sites natifs distincts, comme
        pour Stikkbomb.
      - HITS = `GetNumberConstant(0x2f = nrOfHits)` **LITTERAL** (7e arg du call-site). Le chemin
        generique passe par `ab.get_special_hits` = `GetDefaultAttackHits(nrOfHits, ExtraHits, Melee)`,
        qui AJOUTE la stat `ExtraHits` du caster -- que ce playbook n'ajoute pas.

    Le PROFIL n'est PAS surcharge : le 8e arg est `AbilityConfiguration$$GetDamageProfile(config)`,
    `Nullable` NON vide (`damageProfile` = Physical), pas le quirk `param_8 = null` de #164/#165.

    ⚠ RECTIFICATION #353 de la ligne 1059 de `_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE` : #350 avait
    inscrit `ExplodesAbility$$GetDamage` = `PercentageOf(StatAmount(Health), ...)` comme LA formule de
    1059. C'est une lecture PARTIELLE -- ce corps n'alimente que le TROISIEME batch (l'explosion), et
    seulement quand l'auto-degat du ram TUE le caster. La formule du batch principal est `Get(minDmg)`.
    Les deux autres batchs : `_ramming_speed_self_events` (porte) et le batch EXPLOSION (residu nomme,
    cf. cette fonction et `docs/rl/case-353-ramming-speed-prediction.md`)."""
    lvl, mult = ab.level, ab.multiplier
    base = cfg.get_variable_for_level("minDmg", lvl, 0, mult)      # var 0xc = minDmg (Get == Direct)
    hits = int((cfg.constants or {}).get("nrOfHits") or 0)         # const 0x2f = nrOfHits (LITTERAL)
    out = {"base_override": base}
    if hits:
        out["hits_override"] = hits
    return out


# {ability_id: handler(scene, caster_id, target_id, ability_id, ability_name, attack_pos, ab, cfg)
#  -> [ProbableDamageEvent]}. Batchs SUPPLEMENTAIRES d'un playbook : un
# `GenerateMultiHitAttackPredictions` de plus, sur un selecteur qui n'est NI `<Target>` NI l'AoE de
# l'ability (les deux que `make_damage_predictions` couvre deja). Consomme APRES la boucle AoE --
# c'est l'ordre du natif pour le seul membre actuel (1059 : la boucle AoE y est vide).
def _ramming_speed_self_events(scene, caster_id, target_id, ability_id, ability_name,
                               attack_pos, ab, cfg) -> list:
    """`RammingSpeedPlaybook$$MakeDamagePredictions` -- **2e batch (le CASTER LUI-MEME) + les batchs
    3/4 (EXPLOSION)**, c.-a-d. tout ce que le playbook emet APRES le batch de la cible principale.

    Le playbook enchaine un SECOND `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullyShared
    GenericTypeu003E$$GenerateMultiHitAttackPredictions` dont le `param_4` ET le selecteur `param_5`
    sont le CASTER (`DSLSelectors@+0x48`, celui-la meme que `RammingSpeedAbility$$ExecuteBehaviour`
    passe a `MoveUnit`), puis `List.AddRange` dans la liste du 1er batch :

        self = GenerateMultiHitAttackPredictions(caster, casterPosition, CASTER, <Caster>,
                   Get(minDmg 0xc), GetNumberConstant(0x32 = nrOfHits_2),
                   AbilityConfiguration$$GetDamageProfile(), null, 0)
        list.AddRange(self)

    C'est le RECUL du ram : le caster s'inflige `nrOfHits_2` coups de sa propre base. La face COMBAT
    porte le MEME terme -- `RammingSpeedAbility$$ExecuteBehaviour` construit
    `AttackWithAttackDamage(Owner@0x30, Owner@0x30, RandomAmount(minDmg, maxDmg), profile, nrOfHits_2)`
    (caster == cible), somme a l'attaque de la cible. Base/profil sont ceux du batch principal ; seuls
    les COUPS changent.

    `friendly = True` : mirror de la negation NATIVE, pas une convention de port --
    `IdunBattle.AI.Utilities.DamageUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext` termine par
    `if (IsFriend(caster, actor)) u = u * -1` (branche `HasFriendlyFire` -> `IsEnemy` sinon). Le caster
    est son propre ami : l'utilite de ce batch est NEGATIVE, exactement comme l'event de cout self.

    Config incomplete -> `[]` (degradation fidele, aucun event invente), meme convention que
    `_frenzied_firing_inputs`.

    ── BATCHS 3/4 (EXPLOSION), #383 ────────────────────────────────────────────────────────────
    Le natif enchaine, DANS CETTE FONCTION-CI parce que c'est le meme `MakeDamagePredictions` :

        list.AddRange(self)
        if (!self.Any(p => p.Prediction.WillBeKill)) return list;   // <>c$$<MakeDamagePredictions>b__2_0
        <les deux batchs EXPLOSION>                                 // cf. `prediction/ramming_speed.py`

    La gate est portee ICI, sur l'event du CASTER qu'on vient de construire : `will_be_kill()` est
    le mirror de `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill`
    (`CannotBeGuaranteedKilled@0x89` -> false ; sinon `CurrentHealth <= BlockScenarios[0]+0x0c ??
    rawMin@0x1c`). `Enumerable.Any` sur une liste d'UN element == ce predicat sur cet element.

    Elle a ete MESUREE gouvernante et NON causale du verrou (`#372` : capteur `get_WillBeKill ->
    TRUE`, 1 appel, `blockScenarioCount = 0`, `cannotBeGuaranteedKilled = 0`) ; le verrou etait un
    ARTEFACT DE MONTAGE (le caster n'avait pas la main, donc `MovementQuery$$
    FindAnyOrAllMoveableTiles` repartait sur un `OrderedSet` VIDE) -- cf. `case-361`."""
    lvl, mult = ab.level, ab.multiplier
    base = cfg.get_variable_for_level("minDmg", lvl, 0, mult)       # var 0xc = minDmg (Get == Direct)
    hits2 = int((cfg.constants or {}).get("nrOfHits_2") or 0)       # const 0x32 = nrOfHits_2
    if not hits2 or not base:
        return []
    dp = generate_multi_hit_attack_prediction(scene, caster_id, caster_id, ability_id, ability_name,
                                              attack_pos=attack_pos, base_override=base,
                                              hits_override=hits2)
    if dp is None:
        return []
    events = [ProbableDamageEvent(target=caster_id, prediction=dp, friendly=True)]
    # `if (!self.Any(p => p.Prediction.WillBeKill)) return list;` — le recul doit TUER le caster.
    if not any(e.prediction.will_be_kill() for e in events):
        return events
    from .ramming_speed import explosion_events
    return events + explosion_events(scene, caster_id, target_id, ability_id, ability_name,
                                     attack_pos)


def _plague_wind_inputs(scene, caster_id, target_id, ab, cfg) -> dict:
    """Entrees du batch 1 de `PlagueWindPlaybook$$MakeDamagePredictions` (1035) et de
    `MortarionsPlagueWindPlaybook$$MakeDamagePredictions` (1093) -- `hits` LITTERAL pour les deux,
    et pour 1093 la base sous le `If(HasTrait(<Target>, Summon), x Direct(2), .)`.

    Le corps vit dans `prediction/plague_wind.py`, avec les vagues 2 et 3 : les trois batchs sont
    UN SEUL `MakeDamagePredictions`, et leurs formules ne different que par la paire de variables.
    Ce wrapper n'existe que pour le registre (import PARESSEUX -- `plague_wind` consomme
    `generate_multi_hit_attack_prediction`, defini ici : meme protocole que `ramming_speed`)."""
    from .plague_wind import main_batch_inputs
    return main_batch_inputs(scene, caster_id, target_id, ab, cfg)


def _plague_wind_wave_events(scene, caster_id, target_id, ability_id, ability_name,
                             attack_pos, ab, cfg) -> list:
    """Batchs 2 et 3 de 1035/1093 : `Enemies(Caster, AdjacentUnits(<Target>))` puis
    `Unique(Enemies(Caster, AdjacentUnits(<vague 2>))) - <Target> - <vague 2>`, chacun avec sa
    propre base (`MinMaxDamage2Average` / `MinMaxDamage3Average`, sous le meme `If(Summon)` pour
    1093). Corps + RE dans `prediction/plague_wind.py`."""
    from .plague_wind import wave_events
    return wave_events(scene, caster_id, target_id, ability_id, ability_name, attack_pos, ab, cfg)


# `EffectType.Fire` (5) — `scene.tile_effects_by_pos` est indexee par NOM d'effet (`tileMeta`
# `effects[].name`, cf. `ai/context.py`), jamais par id : on compare donc au nom de l'enum.
_EFFECT_FIRE_NAME = _EffectType.Fire.name


def _tile_has_effect_from_scene(scene):
    """`ctx.tile_has_effect(tileId, effectType)` de la face PREDICTION -- branche TUILE de
    `IdunBattle.Entities.EntityExtensions$$HasOneOfEffects`, lue par `HasEffect(<entite-tuile>, ...)`.

    Le substrat est `Scene.tile_effects_by_pos` (tileMeta, indexe par POSITION et par NOM d'effet) :
    on traduit donc l'ID d'entite-tuile en position par `Scene.board`, comme `unit_on_tile`. C'est le
    MEME substrat que `_daemonic_ordnance_target_gate` -- foyer unique, donc le gate de la cible
    PRINCIPALE et le SET AoE ne peuvent pas se contredire.

    Rend `None` (et non un accesseur qui repondrait `False`) quand la carte d'effets ou le board
    manquent : le noeud `HasEffect` distingue alors « accesseur absent » et rend False lui-meme --
    le regime du natif sur tout board frais --, sans qu'aucune couche n'invente de feu."""
    fx, board = scene.tile_effects_by_pos, scene.board
    if not fx or board is None:
        return None
    names_by_id = {}

    def _tile_has_effect(tile_id, effect_type) -> bool:
        key = int(tile_id)
        names = names_by_id.get(key)
        if names is None:
            c = board.coord(key) if key in board.by_id else None
            names = set(fx.get((int(c[0]), int(c[1]))) or ()) if c is not None else set()
            names_by_id[key] = names
        try:
            return _EffectType(int(effect_type)).name in names
        except ValueError:                       # type d'effet hors enum -> jamais porte par la carte
            return False

    return _tile_has_effect


def _daemonic_ordnance_target_gate(scene, caster_id: int, target_id: int) -> bool:
    """#350-r3 -- SELECTEUR de `DaemonicOrdnancePlaybook$$MakeDamagePredictions`, qui n'etait pas porte.

    Le playbook ne boucle PAS sur `<Target>` : il boucle sur
    `GetEntitiesFromSelector(DaemonicOrdnanceAbility$$GetAllDamageableTargets, ...)` =

        Enemies( caster@0x160,
                 Units( Filter( GetTargetAreaTiles(), HasEffect(Tiles(Subject@0x180), 5 = Fire) ), 1 ),
                 3 )

    soit **les ennemis debout sur une tuile qui PORTE DEJA le feu**. Or c'est ce meme cast qui pose le
    feu, en DERNIER etage de son behaviour (`DaemonicOrdnanceAbility$$ExecuteBehaviour` [5]
    `AddEffect(Fire -> zone)`, cf. `runner/abilities/blacklegion.py`). Sur une zone qui ne brule pas
    encore, le selecteur rend l'ensemble VIDE et le natif n'emet AUCUN event.

    `GetTargetAreaTiles` = `TilesOnSameElevation(target, TilesInTriangleShape(target, dir), 1)` est
    ancre SUR LA CIBLE et contient donc toujours la tuile de la cible : pour la cible principale la
    conjonction se reduit exactement a « ennemi du caster ET sa tuile porte `Fire` ».

    MESURE (#350-r3, `blackForgefiend` / MC1_67, board sans feu) : natif `count = 0`, port
    `(81, 123, 3)` -- le port INVENTAIT un event. C'est une sur-prediction silencieuse : ni erreur ni
    crash, et elle gonfle l'utilite de 1148 dans toute decision portee.

    `tile_effects_by_pos = None` (chemins sans `tileMeta`) = feu INCONNU -> on rend `False`, c.-a-d.
    le regime du natif sur tout board frais. Un faux negatif reste possible si une zone brule
    reellement et que la carte d'effets n'a pas ete chargee ; il est BORNE et explicite, la ou
    l'ancien comportement etait faux sur TOUT board."""
    if scene.team(caster_id) is None or scene.team(target_id) is None:
        return False
    if scene.team(caster_id) == scene.team(target_id):      # `Enemies(caster@0x160, ., 3)`
        return False
    p = scene.pos(target_id)                                # `(col, row)` — cf. `Scene.pos`
    fx = scene.tile_effects_by_pos
    if not p or not fx:
        return False
    return _EFFECT_FIRE_NAME in (fx.get(tuple(p)) or [])


def _hades_autocannons_target_gate(scene, caster_id: int, target_id: int) -> bool:
    """#359 -- appartenance de la CIBLE au selecteur de `HadesAutocannonsPlaybook$$MakeDamagePredictions`.

    Le playbook ne boucle pas sur `<Target>` : il boucle sur
    `GetEntitiesFromSelector(HadesAutocannonsAbility$$GetAllTargets, ...)` =

        UnitsWithTrait( Friends( of: Target@0x60,
                                 SurroundingUnits(Target@0x60, ConfigConst(0x16 = range),
                                                  unique: 1, includeCenter: 1, sel: 3) ),
                        2 = Summon, 3 )                       # + SortByRow / SortReverse (ordre)

    Une cible que ce selecteur ne retient pas n'a donc AUCUN event -- exactement le regime mesure en
    #350-r3 : sans summon en jeu, `aiPlaybookPredict(1147)` rend `count = 0`, **16 fois** (8 cibles x
    2 abilities x {MoW, unite greffee}), quel que soit le caster.

    L'appartenance de LA CIBLE a son PROPRE selecteur se reduit a UN predicat, et c'est une
    reduction EXACTE, pas une heuristique -- les trois conjonctions du selecteur, prises sur la
    cible elle-meme :
      * `SurroundingUnits(Target, range, includeCenter: 1)` : distance(cible, cible) = 0 <= range,
        et le centre est INCLUS -> vrai (le seul residu serait une cible morte, que `_within` ecarte
        deja par `_is_alive`, d'ou le test de vie explicite ici) ;
      * `Friends(of: Target)` : une entite est toujours de son propre camp -> vrai ;
      * `UnitsWithTrait(2 = Summon)` -> **le seul discriminant**.
    Le referent d'equipe est la CIBLE (`DSLSelectors+0x60`), pas le caster : ce gate ne teste donc
    PAS l'inimitie (c'est `TargetingOptions.TargetIsEnemy` qui la porte, face ELIGIBILITE).

    Substrat de traits = `_entity_traits` (#267-r1), le meme foyer que tous les autres gates de
    trait de la face prediction -- jamais une relecture du kit gameconfig par visualId."""
    if not scene.units:
        return False
    u = next((x for x in scene.units if x.get("id") == target_id), None)
    if u is None or not bool(u.get("alive", True)) or (u.get("hp") or 0) <= 0:
        return False
    return _has_trait(_entity_traits(scene, target_id), _UnitTrait.Summon)


# {ability_id: gate(scene, caster_id, target_id) -> bool}. Mirror des playbooks dont
# `MakeDamagePredictions` boucle sur un SELECTEUR (`GetEntitiesFromSelector`) au lieu de `<Target>` :
# une cible que le selecteur ne retient pas n'a AUCUN event. Sans ce gate, le port emet un event
# generique par cible demandee -- une sur-prediction muette. Registre distinct de
# `_MAKE_DMG_INPUT_OVERRIDES` (qui, lui, ne change QUE les entrees d'un event deja acquis).
# #270-r3 : ce dict etait le SEUL du fichier reste en ordinaux nus -- il a DEUX cles, et la
# couverture de dict du recenseur filtrait a `>= 3`. Le nom est au site, dans celui de chaque
# handler (`_daemonic_ordnance_...`, `_hades_autocannons_...`) : 2/2 `ActiveAbilityType`.
_MAKE_DMG_TARGET_GATE = {ActiveAbilityType.DaemonicOrdnance: _daemonic_ordnance_target_gate,   # 1148
                         ActiveAbilityType.HadesAutocannons: _hades_autocannons_target_gate}   # 1147


# ── Les playbooks qui N'EMETTENT AUCUN event pour `<Target>` separement (#359-r5) ────────────────
# Ils BOUCLENT sur leur selecteur et rien d'autre : la cible principale n'y a droit a un event que si
# le SELECTEUR la contient, et alors A SA PLACE dans l'ordre du selecteur -- jamais en tete.
#
#   for e in GetEntitiesFromSelector(<selecteur>, caster, casterPosition, target):
#       list.AddRange(GenerateMultiHitAttackPredictions(caster, casterPosition, e, Entity(e), ...))
#
# C'est ce que #359 a MESURE sur `1147` : natif `[113, 110, 116]`, la cible `110` en 2e position
# (`SurroundingUnits(..., includeCenter: 1)` l'a mise dans le selecteur, le `SortByRow` l'a classee).
# Le port emettait `[main] + (selecteur - main)`, donc la cible toujours en tete.
#
# ⚠ CE N'EST PAS LE CAS GENERAL, et une correction NON REGISTREE aurait CASSE les cinq autres. Sur
# les huit abilities du port qui surchargent `get_aoe_targets`, cinq ont bien un batch `<Target>`
# EXPLICITE avant leur boucle -- lu au decompile, une par une :
#
#   `IdunBattle.AI.Playbook.Loki.HarvesterOfSoulsPlaybook$$MakeDamagePredictions`
#       GenerateMultiHit(target, Get(sel, target), GetDamageAmountMain) PUIS AddRange(GetSurroundingUnits)
#   `IdunBattle.AI.Playbook.Loki.PlasmaCannonPlaybook$$MakeDamagePredictions`
#       GenerateMultiHit(target, sel+0x60) PUIS AddRange(GetValidSecondaryTargetsSelector)
#   `IdunBattle.AI.Playbook.Loki.FrenziedFiringPlaybook$$MakeDamagePredictions`      (cf. `_frenzied_firing_inputs`)
#   `IdunBattle.AI.Playbook.Loki.MassDriverAcceleratorPlaybook$$MakeDamagePredictions`
#       GenerateMultiHit(target, sel+0x60, GetHits) PUIS boucle GetAdjacentAttackTargets (GetHits2)
#   `IdunBattle.AI.Playbook.Loki.FragBombPlaybook$$MakeDamagePredictions`            (meme forme, temoin hors get_aoe_targets)
#
# `BloodyFury` (1129) est hors du sujet : son playbook est un `NonComparablePlaybook`
# (`IdunBattle.AI.Playbook.Loki.BloodyFuryPlaybook$$EvaluateNonComparable`), il n'a PAS de
# `MakeDamagePredictions` -- son `get_aoe_targets` est consomme par un autre chemin.
#
# EFFET SUR LE SCORE, mesure du rayon : AUCUN aujourd'hui. Le consommateur du terme degat SOMME
# (`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`),
# et les deux seuls lecteurs de POSITION du port sont `playbook/base.py::calculate_action_utility`
# (`main = events[0]` -> cle `pred`, puis `aoe = events[1:]`) et, en aval, `_spiritleech_lifesteal_util`
# -- or `SpiritLeech` (1104) ne surcharge AUCUN `get_aoe_targets`, donc son `events[0]` est et reste
# la cible. Le reste des lectures de `pred`/`aoe` est du DEBUG. Ce qui change ici est donc la
# FIDELITE de la liste emise, pas un score : c'est la raison pour laquelle rien ne le signalait.
_MAKE_DMG_SELECTOR_ONLY = frozenset({
    ActiveAbilityType.HadesAutocannons,    # 1147 IdunBattle.AI.Playbook.Loki.HadesAutocannonsPlaybook$$MakeDamagePredictions
    ActiveAbilityType.DaemonicOrdnance,    # 1148 IdunBattle.AI.Playbook.Loki.DaemonicOrdnancePlaybook$$MakeDamagePredictions
    ActiveAbilityType.MurderousSwing,      # 1137 IdunBattle.AI.Playbook.MurderousSwingPlaybook$$MakeDamagePredictions
    # 1154 (#976) : le natif ne construit AUCUN batch `<Target>`. Il fait UN SEUL appel a
    # `GenerateMultiHitAttackPredictions` avec UN selecteur, dont l'identite depend de la branche
    # `WillBeCharging` -- `DSLSelectors+0x60 = Target` en CHARGING, `AdjacentEnemies(Caster)` sinon.
    # `TacticalPrecisionAbility.get_aoe_targets` rend ce selecteur-la dans les deux cas (donc
    # `[target]` en CHARGING) : l'appartenance a ce registre est ce qui evite de DOUBLER la cible
    # dans la 1re branche et de l'INVENTER dans la 2de.
    ActiveAbilityType.TacticalPrecision,   # 1154 IdunBattle.AI.Playbook.Loki.TacticalPrecisionPlaybook$$MakeDamagePredictions
})


# {ability_id: handler(scene, caster_id, target_id, ab, cfg) -> {base/hits/profile_override}}. Mirror du dispatch
# playbook natif (par type d'ability). HammerOfWrath (1153) a son propre chemin (make_hammer_wrath_events,
# NonComparable) ; ici = les playbooks Comparable qui surchargent juste les INPUTS de GenerateMultiHit.
_MAKE_DMG_INPUT_OVERRIDES = {
    ActiveAbilityType.MartialInspiration: _martial_inspiration_inputs,            # 1191
    # #974 -- base `minDmg` SEUL + terme flat `extraDmg x niveau(effet 1420)`, et profil
    # CONDITIONNEL (`damageProfile_2` si `MeetSecondDamageProfileRequirement`). Le profil passe par
    # CE registre et non par `_PLAYBOOK_PROFILE_OVERRIDE`, qui ne porte que des constantes.
    ActiveAbilityType.TalonsOfTheEmperor: _talons_of_the_emperor_inputs,           # 1195
    ActiveAbilityType.CrushingClaws: _crushing_claws_inputs,                      # 1105
    ActiveAbilityType.HellfireShells: _hellfire_shells_inputs,                    # 1080
    ActiveAbilityType.BrazierOfHolyFire: _brazier_of_holy_fire_inputs,            # 1041
    ActiveAbilityType.GreatFrostAxe: _great_frost_axe_inputs,                     # 1089
    ActiveAbilityType.FrenziedFiring: _frenzied_firing_inputs,                    # 1036
    ActiveAbilityType.SavageEchoes: _savage_echoes_inputs,                        # 1230
    ActiveAbilityType.Stikkbomb: _stikkbomb_inputs,                               # 1051
    ActiveAbilityType.PlasmaGrenade: _plasma_grenade_inputs,                      # 1098
    ActiveAbilityType.FragstormGrenadeLauncher: _fragstorm_grenade_launcher_inputs,  # 1048
    ActiveAbilityType.MassDriverAccelerator: _mass_driver_accelerator_inputs,     # 1222
    ActiveAbilityType.FragBomb: _frag_bomb_inputs,                                # 1017
    ActiveAbilityType.RammingSpeed: _ramming_speed_inputs,                        # 1059
    ActiveAbilityType.PlagueWind: _plague_wind_inputs,                            # 1035
    ActiveAbilityType.MortarionsPlagueWind: _plague_wind_inputs,                  # 1093
    ActiveAbilityType.TacticalPrecision: _tactical_precision_inputs,              # 1154
}

# Batchs SUPPLEMENTAIRES per-ability (cf. `_ramming_speed_self_events`) : le playbook emet des events
# sur un selecteur AUTRE que la cible principale et l'AoE de l'ability. Pour 1059 le handler rend les
# TROIS batchs restants -- le CASTER, puis (sous la gate `WillBeKill`) les deux batchs EXPLOSION --
# parce qu'ils sortent du MEME `MakeDamagePredictions` et que leur ordre y est significatif. Pour
# 1035/1093 il rend les vagues 2 et 3, chacune avec SON selecteur et SA base.
_MAKE_DMG_EXTRA_EVENTS = {
    ActiveAbilityType.RammingSpeed: _ramming_speed_self_events,      # 1059
    ActiveAbilityType.PlagueWind: _plague_wind_wave_events,          # 1035
    ActiveAbilityType.MortarionsPlagueWind: _plague_wind_wave_events,  # 1093
}


# Override de PROFIL DE PREDICTION par-ability (audit #165) — mirror du `param_8`
# (`Nullable<DamageProfile>`) que le `<Ability>Playbook.MakeDamagePredictions` bespoke passe a
# `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`. Le port derive par defaut le profil de
# `ab.get_damage_profile()` (damageProfile config, sinon arme ranged-first) ; ces playbooks passent
# EXPLICITEMENT un autre profil (ou `null` = profil `None`, enum -1 -> pierce 0, armure PLEINE). Sans
# override, le port applique le PiercingRatio du profil derive -> sur/sous-prediction vs le natif.
# {ability_id: nom de profil passe par le playbook natif}. "None" = param_8 null (pierce 0). VA = playbook.
# CrushingClaws (1105) reste dans _crushing_claws_inputs (case-164, bit-exact live). Les autres candidats de
# l'audit #165 (param_8=null confirme par decompile) NE sont retenus QUE s'ils sont VALIDES LIVE OK sur cible
# blindee (ultraTitus armure 2312) : le seul override pierce ne corrige que les abilities dont le pierce est le
# SEUL gap. La confrontation live a montre que la majorite des candidats null ont un gap PLUS PROFOND (hits/base)
# que l'override ne touche pas -> NON retenus (taches dediees). Cf. docs/rl/case-165-playbook-param8-profile.md.
_PLAYBOOK_PROFILE_OVERRIDE = {
    ActiveAbilityType.HeraldOfTheApocalypse: "None",     # 1020 IdunBattle.AI.Playbook.Loki.HeraldOfTheApocalypsePlaybook$$MakeDamagePredictions (blackHaarken ; null ; Piercing 80) — VALIDE LIVE OK
    ActiveAbilityType.SanctorumMissile: "None",     # 1062 IdunBattle.AI.Playbook.Loki.SanctorumMissilePlaybook$$MakeDamagePredictions (adeptMorvenn ; null, main+bonus ; Blast 15) — VALIDE LIVE OK
    ActiveAbilityType.FragBomb: "None",     # 1017 IdunBattle.AI.Playbook.Loki.FragBombPlaybook$$MakeDamagePredictions (astraBullgryn ; null ; Blast 15) — hits config 6 OK, pierce SEUL gap. VALIDE LIVE [6,6] [#168]
    ActiveAbilityType.MultiThreatEliminator: "None",     # 1006 IdunBattle.AI.Playbook.Loki.MultiThreatEliminatorPlaybook$$MakeDamagePredictions (necroDestroyer ; null ; Gauss 60) — + hits static 6 (subclass). VALIDE LIVE [6,6] [#167]
    ActiveAbilityType.Executioner: "Psychic",  # 1066 IdunBattle.AI.Playbook.Loki.ExecutionerPlaybook$$GeneratePredictions (eldarFarseer ; Nullable(0xd=13=Psychic, pierce 100)) — hits=RoundsStarted (subclass) [#166]
    ActiveAbilityType.HarbingerOfDestruction: "None",     # 1008 IdunBattle.AI.Playbook.Loki.HarbingerOfDestructionPlaybook$$MakeDamagePredictions (necroPlasmancer ; nullIdunBattle.AI.Playbook.Loki.HarbingerOfDestructionPlaybook$$MakeDamagePredictions+0x1cc ; ability DirectDamage pierce 100) [#169]
    #   RE PROUVE pierce-SEUL gap : base=ArcScourge.GetDamage=avgIdunBattle.AI.Playbook.Loki.HarbingerOfDestructionPlaybook$$MakeDamagePredictions+0x13c OK, hits=ArmoriumCherub.GetHits configIdunBattle.AI.Playbook.Loki.HarbingerOfDestructionPlaybook$$MakeDamagePredictions+0x16e OK.
    #   NON confronte live (necroPlasmancer = UNSPAWNABLE_FALLBACK ; autres carriers = NPC necroBoss*). Retenu sur preuve
    #   decompile (structure IDENTIQUE aux 1020/1062 valides live) — le deep-read RE a explicitement exclu tout gap base/hits.
    # --- audit #165 param_8=null : les 5 AUTRES candidats NE sont PAS des overrides pierce (confronte #169) :
    #   1027 PsychicMaelstrom IdunBattle.AI.Playbook.Loki.PsychicMaelstromPlaybook$$MakeDamagePredictions : param_8 = Nullable(BasiliskBarrage.GetDamageProfile) EXPLICITE (PAS null ; l'audit
    #     d'arite confondait param_8=profil et param_9=poids Fix64). Live OK bit-exact [2792,4188] (astraPrimarisPsy). AUCUN override.
    ActiveAbilityType.SorcerousFacade: "None",     # 1100 IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$MakeDamagePredictions (thousTzaangor) ; profil du 2e batch VIDE -> pierce 0/armure pleine [#351]
    #   ^ ENTREE POSEE PAR #351, et elle n'est plus inerte. L'ancienne note disait « PAS d'entree
    #   ici, et c'est DELIBERE : `SorcerousFacade` est dans `_PREDICT_VIA_NORMAL_ATTACK`, donc
    #   `_event` court-circuite AVANT de consommer `overrides` ». Ce court-circuit ETAIT le residu
    #   #351 : le natif AJOUTE le batch a l'attaque normale (`AddRange`), il ne s'y substitue pas.
    #   Depuis que le port mirror l'ajout, le 2e event EXISTE et son profil VIDE (`param_8` nul, meme
    #   quirk que 1020/1062/1147/1148) est LU ICI -- plus dans un appel bespoke du playbook.
    #   ⚠ RECTIFICATION de l'ancienne note « base=Half(Sum(var0xc,var0xd)) DSL != avg -> gap BASE » :
    #   faux positif de lecture, tranche par le meme raisonnement que 1147/1148 (#172) --
    #   `Half(Sum(GetVariableForLevel(0xc = minDmg), GetVariableForLevel(0xd = maxDmg)))` EST
    #   `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage(avgFlag)`, c.-a-d. l'avg config
    #   GENERIQUE (== `ab.get_damage()` = 1496 mesure). Les hits sont `GetNumberConstant(0x2f =
    #   nrOfHits)`, eux aussi generiques, et les cibles `DSLSelectors.Get(sel)` = mono-cible.
    ActiveAbilityType.DaemonicOrdnance: "None",     # 1148 IdunBattle.AI.Playbook.Loki.DaemonicOrdnancePlaybook$$MakeDamagePredictions (blackForgefiend MoW) ; param_8=null -> pierce 0/armure pleine [#172]
    ActiveAbilityType.HadesAutocannons: "None",     # 1147 IdunBattle.AI.Playbook.Loki.HadesAutocannonsPlaybook$$MakeDamagePredictions (blackForgefiend MoW) ; param_8=null -> pierce 0/armure pleine [#172]
    #   ^1148/1147 : RE #172 REFUTE l'ancienne hypothese "gap BASE". base = IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$GetDamage /
    #   IdunBattleLogic.Entities.Abilities.Active.LightOfSanguiniusAbility$$GetDamage = IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage(avgFlag) = Half(Sum(minDmg 0xc,maxDmg 0xd))
    #   = avg GENERIQUE (== ab.get_damage) ; hits = IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits = nrOfHits GENERIQUE. Seul gap = param_8=null.
    #   param_8 (GenerateMultiHit sig IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions) = profil passe a PredictAttack slot 0x27 ; 1147/1148 ont 0 en param_8 ET param_10
    #   (poids Fix64) -> l'arite qui confondait 1027 (param_8 vs param_10) est ici tranchee. Decompile-proof (base/hits exclus,
    #   meme standard que 1008) ; carrier MoW -> confront live via aiPlaybookPredict (harnais #172) = gate ideal residuel.
    #   1080 HellfireShells IdunBattle.AI.Playbook.Loki.HellfireShellsPlaybook$$MakeDamagePredictions : base=Direct(0xc=minDmg SEUL) + hits=nrOfHits(+extraHit si cible BigTarget)
    #     + param_8=null -> PORTE #173 via _hellfire_shells_inputs (base+hits+profile ensemble). Cf. case-173.
}


def _current_player_team(scene):
    """EQUIPE du joueur courant (`TeamComponent.<+0x24>`), derivee de `units[].ctrl`.

    `ctrl` EST l'invocation native `IdunBattle.Entities.UnitExtensions$$IsControlledByCurrentPlayer`
    (le hook la publie, le seam offline la reconstitue des deux memes lectures) : l'equipe d'une
    unite CONTROLEE est celle du joueur courant. On prend la premiere ; `None` si aucune ligne
    `ctrl` n'est mesuree -- le consommateur (`CurrentPlayerIsOfTeam`) rend alors False, jamais une
    equipe devinee.

    #359-r6 -- LA DUPLICATION EST RESORBEE, ET PAS PAR UN IMPORT DIFFERE. La regle vit dans
    `engine/services/current_player.py`, une FEUILLE PURE (zero import `engine.*`) que les deux
    consommateurs partagent : c'est l'option (1) de la doctrine (DEPLACER), pas l'option (3).
    Importer `engine.ai.context` d'ici aurait ferme un cycle -- mesure : `import engine.ai.context`
    charge `engine.playbook.prediction.abilities`, l'inverse est faux --, mais le foyer, lui,
    n'est dans la cascade de personne : `engine.services` etait DEJA traverse par les deux.
    Ce site ne garde que l'adaptation de substrat (`Scene` -> lignes)."""
    return _cp.current_player_team(getattr(scene, "units", None))


def make_damage_predictions(scene, caster_id, main_tgt_id, ability_id, ability_name, attack_pos=None):
    """`<Ability>Playbook.MakeDamagePredictions` : LISTE de `ProbableDamageEvent` = cible PRINCIPALE + AoE
    (`GetSurroundingUnits`/`GetOtherTargets`) + event SELF negatif (cout PV). `[]` si non-attaque."""
    if not makes_damage_predictions(ability_name):
        return []
    # #99 REFRAMING (case-99) : les specials ne sont PAS Attack-based. L'hypothese historique
    # « SpiritLeech herite ALoki_NormalAttackAbility.PredictAttack (slot vtable 0x27) » est REFUTEE — les
    # 5 specials audites resolvent `PredictAttack` vers le STUB ABSTRAIT `AActiveAbility.PredictAttack
    # IdunBattle.Entities.Abilities.AActiveAbility$$PredictAttack` (qui THROW). Le vrai chemin = `<Special>Playbook.MakeDamagePredictions` ->
    # `GenerateMultiHitAttackPredictions(base = ability.GetAttackDamage() = CONFIG minmax)`.
    # ⚠ CORRECTION (#27-4e) : ce commentaire affirmait « l'ensemble est VIDE ; la branche est
    # conservee morte ». C'est FAUX depuis #171 -- il contient `SorcerousFacade`, et la branche est
    # bien VIVANTE pour elle.
    # ⚠⚠ CORRECTION (#351) : la branche SUBSTITUAIT l'attaque normale au batch, ce qui rendait UN
    # event la ou le natif en rend DEUX. Le natif AJOUTE : `[ProbableDamageEvent(normale)]` PUIS
    # `AddRange(GenerateMultiHitAttackPredictions(...))`. Le port fait desormais pareil -- et c'est
    # ce qui rend le registre `_A_INLINE_IN_PLAYBOOK` (l'arrondi demi-vers-le-pair de 1100, #350)
    # ACTIF au lieu d'inerte.
    prepend_normal = ability_name in _PREPEND_NORMAL_ATTACK_EVENT
    # #359-r5 -- ce playbook natif emet-il un event pour `<Target>` SEPAREMENT, ou boucle-t-il
    # uniquement sur son selecteur ? Registre `_MAKE_DMG_SELECTOR_ONLY` (lu au decompile, ability par
    # ability, contre-temoins nommes). C'est la SEULE chose qui distingue les deux formes ; la deduire
    # dynamiquement (« le set contient-il la cible ? ») serait faux : `FrenziedFiring` a un batch
    # `<Target>` explicite ET un selecteur qui peut contenir la cible.
    selector_only = int(ability_id) in _MAKE_DMG_SELECTOR_ONLY

    def n_targets(aoe_list) -> int:
        """`nrEnemies` = `Enumerable.Count(<le set sur lequel le natif boucle>)`, l'argument de
        `<Ability>.GetCorrectDamage` et de la boucle EXTERNE (`get_prediction_set_repeat`).

        Famille a batch `<Target>` : le natif compte le selecteur SECONDAIRE plus la cible.
        Famille `_MAKE_DMG_SELECTOR_ONLY` : il compte le selecteur, POINT -- ce qui, pour
        `MurderousSwing`, est litteralement le `Enumerable.Count(entities)` que
        `IdunBattle.AI.Playbook.MurderousSwingPlaybook$$MakeDamagePredictions` passe a
        `IdunBattleLogic.Entities.Abilities.Active.MurderousSwingAbility$$GetCorrectDamage`. Les deux
        coincident tant que la cible est DANS le selecteur (le regime ordinaire d'une melee), et
        divergent d'exactement 1 quand elle n'y est pas -- c'est le second ecart que #359-r5 fermait
        sans l'avoir nomme."""
        return len(aoe_list) if selector_only else 1 + len(aoe_list)
    # ab/cfg/aoe construits ICI (AVANT le main event) car le compte AoE TOTAL (nrEnemies = 1 + secondaires)
    # est requis pour la clause `GetCorrectDamage` (MurderousSwing : +extraDmg AJOUTE A LA BASE si UN seul
    # ennemi touche, #108). `base_bonus` = delta de base, 0 pour toute ability sans clause (get_correct_damage
    # = identite) -> aucun autre chemin affecte. Le natif calcule `nrEnemies=Count(targets)` de meme AVANT
    # d'appeler GetCorrectDamage puis GenerateMultiHitAttackPredictions par cible (MakeDamagePredictions).
    ctx0 = scene.ctx(caster_id)
    cfg = AbilityConfiguration.from_gameconfig(ability_name, GC.ability(ability_name))
    ab = active_ability_for(ability_name, ability_id, ctx0, cfg,
                            ability_state=scene.ability_state(caster_id, ability_id)) \
        if (ctx0 is not None and cfg is not None) else None
    aoe = []
    if ab is not None:
        by_id = {u.get("id"): u for u in scene.units}
        dctx = dsl.DslContext(units=scene.units, caster=by_id.get(caster_id),
                              target=by_id.get(main_tgt_id), config=cfg, ability_level=ab.level,
                              times_attacked=getattr(ctx0, "times_attacked", 0) or 0,
                              caster_pos=attack_pos, elev_by_pos=scene.elev_by_pos,
                              # `HasFlag(unit, traitId)` du natif -- requis par tout set AoE qui
                              # passe par `UnitsWithTrait`/`UnitsWithoutTrait` (1147 :
                              # `UnitsWithTrait(..., 2 = Summon)`). Sans lui, `ctx.has_trait` vaut
                              # None et ces noeuds rendent VIDE par degradation, c.-a-d. un volet
                              # AoE muet. Substrat = `_entity_traits` (#267-r1), le foyer unique de
                              # la face prediction. Inerte pour les sets AoE deja portes (aucun ne
                              # lit de trait) : le champ n'etait tout simplement pas consulte.
                              has_trait=lambda u, t: _trait_name(t) in _entity_traits(
                                  scene, (u or {}).get("id")),
                              # --- les TROIS canaux du set AoE TILE-DOMAIN de 1148 (#359-r1) ------
                              # `board` : requis par TOUT selecteur de tuiles (`TilesInTriangleShape`
                              # -> `board.id_at`/`neighbour_at`, `TilesOnSameElevation` ->
                              # `board.elevation`, `Units(<tuiles>)` -> `board.coord`). Absent, ils
                              # rendent `[]` par degradation -- volet muet, ni erreur ni crash.
                              # Pour les sets AoE UNIT-DOMAIN deja portes il ne change QUE L'ORDRE
                              # d'enumeration (`_within` trie de facon STABLE par le rang de tuile
                              # natif ; l'ENSEMBLE et les valeurs sont inchanges) -- il les rend
                              # donc PLUS fideles, jamais differents en contenu.
                              board=scene.board,
                              # `HasEffect(<entite-tuile>, 5 = Fire)` -> branche TUILE de
                              # `EntityExtensions$$HasOneOfEffects`. Substrat = le MEME
                              # `scene.tile_effects_by_pos` (indexe par NOM d'effet) que
                              # `_daemonic_ordnance_target_gate` : un seul foyer, donc gate de cible
                              # principale et SET ne peuvent pas diverger. Table absente = feu
                              # INCONNU -> accesseur None -> le noeud rend False (regime du natif
                              # sur tout board frais), jamais un feu suppose.
                              tile_has_effect=_tile_has_effect_from_scene(scene),
                              # `IsPositionMachineForCurrentPlayer(2)` -> `dir` de la zone-triangle.
                              # None = non mesure -> predicat False -> `dir = 4`, la branche `else`
                              # NATIVE (degradation NOMMEE). Canal : `Scene.machine_of_war_position`.
                              current_player_machine_position=getattr(
                                  scene, "machine_of_war_position", None),
                              # #359-r2 -- `AreEqual(CurrentPlayer, Player(<team>))`, l'ancre qui
                              # choisit le SENS du `SortByRow` de
                              # `...HadesAutocannonsAbility$$GetAllTargets`. Derive de `units[].ctrl`,
                              # qui EST l'invocation native
                              # `IdunBattle.Entities.UnitExtensions$$IsControlledByCurrentPlayer` :
                              # l'equipe d'une unite controlee est celle du joueur courant. TRI-ETAT
                              # -- aucune ligne `ctrl` mesuree -> None -> le noeud rend False, jamais
                              # une equipe devinee.
                              current_player_team=_current_player_team(scene))
        aoe = [t for t in ab.get_aoe_targets(dctx) if t.get("id") is not None]
        if not selector_only:
            # Famille a batch `<Target>` EXPLICITE : la cible est emise a part, en tete -- on la
            # retire donc du batch secondaire. Pour `_MAKE_DMG_SELECTOR_ONLY`, au contraire, le
            # selecteur EST la seule boucle du natif : il part TEL QUEL, cible incluse a sa place.
            aoe = [t for t in aoe if t.get("id") != main_tgt_id]
    base_bonus = 0
    if ab is not None:                               # GetCorrectDamage(base, nrEnemies) - base (>= 0)
        _b = ab.get_damage()
        base_bonus = max(0, ab.get_correct_damage(_b, n_targets(aoe)) - _b)

    # Dispatch per-ability (mirror du registre playbook natif) : un handler ability-specifique fournit ses
    # overrides d'ENTREE (base/hits/profile) ; sinon `{}` -> chemin generique config inchange. La logique
    # ability-specifique vit dans son handler HOMONYME (cf. `_MAKE_DMG_INPUT_OVERRIDES`), jamais inline ici.
    _ovr_fn = _MAKE_DMG_INPUT_OVERRIDES.get(ability_id)
    overrides = _ovr_fn(scene, caster_id, main_tgt_id, ab, cfg) if (_ovr_fn and ab is not None and cfg is not None) else {}
    # BATCH SECONDAIRE a entrees PROPRES (`aoe_overrides`) — mirror des playbooks qui appellent
    # `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`
    # DEUX fois avec des arguments differents (ex. FrenziedFiring : `hits` = noeud geometrique pour la cible
    # d'origine, `hits = 1` LITTERAL pour `FrenziedFiringAbility$$GetTargets`). Cle META consommee ici, JAMAIS
    # transmise en kwarg. Absente -> le batch AoE herite exactement des entrees du batch principal (cas de
    # tous les autres playbooks portes, qui repassent les memes formule/hits/profil aux deux boucles).
    _aoe_ovr = overrides.pop("aoe_overrides", None) if overrides else None
    # Profil de prediction par-ability (audit #165) : le playbook natif passe un param_8 explicite (ou null).
    _prof_ovr = _PLAYBOOK_PROFILE_OVERRIDE.get(ability_id)
    if _prof_ovr is not None and "profile_override" not in overrides:
        overrides = {**overrides, "profile_override": _prof_ovr}
    aoe_overrides = {**overrides, **_aoe_ovr} if _aoe_ovr else overrides

    # Gate de SELECTEUR (#350-r3) : pour les playbooks qui bouclent sur `GetEntitiesFromSelector`,
    # une cible hors du selecteur n'a AUCUN event (cf. `_MAKE_DMG_TARGET_GATE`). Applique a la cible
    # PRINCIPALE comme a l'AoE, puisque le natif ne connait que la liste rendue par son selecteur.
    _gate_fn = _MAKE_DMG_TARGET_GATE.get(ability_id)

    def _event(tid, prob1=1.0, ovr=None):
        if _gate_fn is not None and not _gate_fn(scene, caster_id, tid):
            return None
        dp = generate_multi_hit_attack_prediction(scene, caster_id, tid, ability_id, ability_name,
                                                  attack_pos=attack_pos, base_bonus=base_bonus,
                                                  **(overrides if ovr is None else ovr))
        return ProbableDamageEvent(target=tid, prediction=dp, probability1=prob1) if dp is not None else None

    # TERME EN TETE (`_PREPEND_NORMAL_ATTACK_EVENT`) : le `new ProbableDamageEvent(sel,
    # battleQuery.<slot 0x22>(caster, sel, casterPosition))` que le playbook construit AVANT son
    # `AddRange`. Il est INDEPENDANT du batch (le natif ne le conditionne a rien), d'ou son ajout
    # hors du gate `main is None` qui, lui, garde le regime batch de toutes les autres abilities.
    events = []
    if prepend_normal:
        nev = make_normal_attack_predictions(scene, caster_id, main_tgt_id, attack_pos)
        if nev is not None:
            events.append(nev)

    if selector_only:
        # #359-r5 -- AUCUN event `<Target>` : ces playbooks n'en construisent pas. La cible n'a droit
        # a un event que si le SELECTEUR la porte, et alors A SA PLACE, par la boucle ci-dessous.
        # C'est ce qui reproduit la mesure de #359 sur `1147` (natif `[113, 110, 116]`, cible en 2e).
        # Il n'y a rien a court-circuiter ici : un selecteur VIDE rend une liste vide, exactement
        # comme le natif -- et c'est `playbook/base.py::calculate_action_utility` qui decide ensuite
        # (garde de PORT `not events -> None`, deja documentee comme divergente du natif, qui
        # sommerait 0). Ne pas la deplacer ici : elle vaut pour TOUTES les abilities.
        pass
    else:
        main = _event(main_tgt_id)
        if main is not None:
            events.append(main)
        elif _gate_fn is None:
            # Sans gate de SELECTEUR, la cible principale EST la boucle du natif : pas d'event
            # principal = non-attaque, et le batch AoE n'a pas lieu d'etre. Historique, inchange.
            return events
    # AVEC un gate de selecteur (#359), l'absence d'event PRINCIPAL ne dit RIEN des autres membres :
    # le playbook ne boucle pas sur `<Target>`, il boucle sur les entites de SON selecteur, et la
    # cible demandee peut n'y etre pas alors que d'autres y sont. MESURE (#359, R3, `1147` greffee
    # sur `necroWarden`, cible = le SUMMONER, trois `deathPoxwalker` autour de lui) :
    # `aiPlaybookPredict` rend **3** events -- un par summon --, la cible demandee n'y figurant pas.
    # Court-circuiter ici aurait rendu 0. Inerte pour `1148`, dont le set AoE est vide.
    if ab is None:
        return events
    # Plafond secondaire (`GetMaxSecondaryTargets`) -> poids batch `min(1, max/n)` = probability1.
    maxsec = ab.get_max_secondary_targets()
    prob1 = (min(1.0, maxsec / len(aoe)) if (maxsec is not None and aoe) else 1.0)
    for t in aoe:
        aev = _event(t.get("id"), prob1, aoe_overrides)
        if aev is not None:
            events.append(aev)
    # BATCH SUPPLEMENTAIRE a SELECTEUR PROPRE (`_MAKE_DMG_EXTRA_EVENTS`) — mirror des playbooks qui
    # enchainent un `GenerateMultiHitAttackPredictions` sur un selecteur qui n'est NI `<Target>` NI
    # l'AoE de l'ability (RammingSpeed 1059 : `<Caster>`, le recul du ram). Consomme ICI, apres la
    # boucle AoE : c'est l'ordre du natif pour le seul membre actuel, dont la boucle AoE est vide.
    _extra_fn = _MAKE_DMG_EXTRA_EVENTS.get(ability_id)
    # `prepend_normal` s'appelait `via_normal` quand ce gate a ete ecrit (#353) : RENOMME par #351,
    # MEME appartenance au MEME frozenset -- rename mecanique au rebase, aucun changement de sens.
    if _extra_fn is not None and not prepend_normal and cfg is not None:
        events.extend(_extra_fn(scene, caster_id, main_tgt_id, ability_id, ability_name,
                                attack_pos, ab, cfg))
    # #108 count² : les abilities AoE SELF-centrees (MurderousSwing) RE-EMETTENT la liste d'events de degat
    # `count` fois — le playbook natif boucle sur le set `AdjacentEnemies(caster)` (EXTERNE) ET
    # `GenerateMultiHitAttackPredictions` re-boucle sur ce MEME set (INTERNE) -> count² events, chaque cible
    # `count` fois (CONFIRME LIVE : K=1->1, K=2->4, K=3->9). `get_prediction_set_repeat` = count (= 1+len(aoe),
    # taille du set) pour ces abilities, 1 sinon (lineaire INCHANGE pour toutes les autres). Ordre = blocs
    # [main,aoe...] repetes (mirror boucle externe). Refs partagees OK (util Sigma read-only). AVANT l'event SELF.
    rep = ab.get_prediction_set_repeat(n_targets(aoe))
    if rep > 1:
        events = events * rep
    # Event SELF negatif — cout en PV (`ability.GetHealthToLose`), utilite NEGEE (friendly).
    hp_c = scene.hp(caster_id) or 0
    max_c = scene.hpmax(caster_id) or hp_c
    hl = ab.get_health_to_lose(max_c)
    if hl:
        self_dp = _self_damage_prediction(hp_c, hl)
        events.append(ProbableDamageEvent(target=caster_id, prediction=self_dp, friendly=True))
    return events


_HAMMER_ABILITY_NAME = "HammerOfWrath"
_HAMMER_MAX_SECONDARY = 3   # SelectUniqueUnits(GetAdjacentTargets, 3)


def make_hammer_wrath_events(scene, caster_id, target_id, attack_pos):
    """Events degat INTERNES de HammerOfWrath (id 1153) pour scorer son utilite de DECISION NonComparable
    (`IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$EvaluateNonComparable`), depuis `attack_pos` (tuile ou le caster
    charge). Bypass du gate d'affichage #109 (Hammer n'emet AUCUN ProbableDamageEvent affiche ; le degat est
    consomme EN INTERNE par l'utilite). Chaque event = `PredictAttack(0x27)` avec les `(damage, hits, profile)`
    PROPRES de Hammer (config gqfc5mff6c verifiee) :
      - PRIMARY (cible) : base=`minDmg` (AbilityVariableType 12, IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$GetMinDamage), hits=`nrOfHits`
        (AbilityConstantType 47, IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits = 2), profil=`damageProfile` (Power).
      - SECONDARY (chaque ennemi VIVANT adjacent a la cible, `IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$GetAdjacentTargets` =
        `Enemies(AdjacentUnits(TARGET, r=1))` ou `IdunBattleLogic.Entities.DSLFactory$$AdjacentUnits` = `Units(AdjacentTiles(target))
        − target` : unites lues par OCCUPATION DE TUILE → un mort n'est plus sur le board (notre
        pos_by_id garde les cadavres, d'ou le filtre hp>0 explicite — #57m, corpse u95 +120 a 54321 s8),
        plafond `SelectUniqueUnits(3)`) : base=`minDmg_2` (var 54,
        IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$GetMinDamage2), hits=`nrOfHits_2` (const 50, BringerOfDespair.GetHitsToBonusTarget = 1),
        profil=`damageProfile_2` (Physical).
    Le reste du pipeline (spread ±20%, pierce, armure, mods attaquant/positionnels, bouclier) est identique au
    chemin normal via `generate_multi_hit_attack_prediction` (base/hits/profile override). `[]` si indisponible.

    ⚠ L'ADJACENCE DU SECONDARY N'EST PAS LA COURONNE HEX (#943-r7). `AdjacentTiles` descend sur
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` : ENUMERATION
    de la liste STOCKEE (`ConnectivityComponent+0x10`) puis porte `|dElev| < 2` INCONDITIONNELLE.
    La face COMBAT du MEME noeud (`runner/abilities/bloodangels.py::
    hammer_of_wrath_get_adjacent_targets` = `Enemies(AdjacentUnits(Target(), Const(1)))`) l'execute
    en DSL, donc par `dsl/base._within(order='adjacent')` -> `_adjacent_tiles_native` : elle lit
    DEJA la liste stockee. Cabler ici **RESORBE** la divergence de faces au lieu d'en creer une.

    Le predicat passe par le foyer PARTAGE `playbook.adjacency.unit_in_adjacent_tiles` (#954) =
    `Units(AdjacentTiles(subject), unique, sel).Contains(other)`, qui porte en plus l'axe
    MULTI-TUILES et se reduit a `is_adjacent(pos(subject), pos(other))` sur des unites a un pied.
    Canaux tri-etat : absents -> degradation SEULE en couronne hex (comportement d'avant)."""
    ctx0 = scene.ctx(caster_id)
    cfg = AbilityConfiguration.from_gameconfig(_HAMMER_ABILITY_NAME, GC.ability(_HAMMER_ABILITY_NAME))
    if ctx0 is None or cfg is None:
        return []
    ab = active_ability_for(_HAMMER_ABILITY_NAME, int(ActiveAbilityType.HammerOfWrath), ctx0, cfg,
                            ability_state=scene.ability_state(
                                caster_id, int(ActiveAbilityType.HammerOfWrath)))
    lvl, mult = ab.level, ab.multiplier
    minv = cfg.get_variable_for_level("minDmg", lvl, 0, mult)         # var 12 (GetMinDamage)
    minv2 = cfg.get_variable_for_level("minDmg_2", lvl, 0, mult)      # var 54 (GetMinDamage2)
    consts = cfg.constants or {}
    hits1 = max(1, int(consts.get("nrOfHits") or 1))                  # const 47 (GetHits = 2)
    hits2 = max(1, int(consts.get("nrOfHits_2") or 1))               # const 50 (GetHitsToBonusTarget = 1)
    prof1 = consts.get("damageProfile")                              # Power
    prof2 = consts.get("damageProfile_2")                            # Physical
    dp = generate_multi_hit_attack_prediction(scene, caster_id, target_id,
                                              int(ActiveAbilityType.HammerOfWrath),
                                              _HAMMER_ABILITY_NAME,
                                              attack_pos=attack_pos, base_override=minv,
                                              hits_override=hits1, profile_override=prof1)
    if dp is None:
        return []
    events = [ProbableDamageEvent(target=target_id, prediction=dp)]
    # SECONDARIES : Enemies(du caster) adjacents a la CIBLE (hex dist 1), plafond 3.
    caster_team = scene.team(caster_id)
    t_pos = scene.pos(target_id)
    if t_pos is not None:
        # `IdunBattleLogic.Entities.DSLFactory$$AdjacentUnits` = Units(AdjacentTiles(target)) − target : occupation de TUILE
        # → vivants seulement (pos_by_id garde les cadavres ; idiome hp>0 = IsAlive, cf. l.227/276).
        _elev, _neigh = scene.elev_by_pos, _bq.neigh_map(scene)
        adj = [u for u in scene.pos_by_id
               if u != target_id and scene.team(u) != caster_team
               and (scene.hp(u) or 0) > 0
               and scene.pos(u) is not None
               and _adjacency.unit_in_adjacent_tiles(scene, target_id, u, _elev, _neigh)]
        for sid in adj[:_HAMMER_MAX_SECONDARY]:
            sdp = generate_multi_hit_attack_prediction(scene, caster_id, sid,
                                                      int(ActiveAbilityType.HammerOfWrath),
                                                      _HAMMER_ABILITY_NAME,
                                                      attack_pos=attack_pos, base_override=minv2,
                                                      hits_override=hits2, profile_override=prof2)
            if sdp is not None:
                events.append(ProbableDamageEvent(target=sid, prediction=sdp))
    return events


def _self_damage_prediction(hp_c: int, hl: int):
    """`DamagePredictionResult` du cout self (sante perdue `hl`, pas de bouclier, appliedHits=0)."""
    return DamagePredictionResult(
        current_health=hp_c, shield=0,
        accurate_health_damage=MinMaxDamage(min=min(hl, hp_c), max=min(hl, hp_c)),
        accurate_shield_damage=MinMaxDamage(min=0, max=0), applied_hits=0)
