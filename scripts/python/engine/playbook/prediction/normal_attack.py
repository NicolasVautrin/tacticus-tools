"""Prediction de l'ATTAQUE NORMALE : `make_normal_attack_predictions` (`ALoki_NormalAttackPlaybook.
IdunBattle.AI.Playbook.Loki.ALoki_NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$MakeDamagePredictions`), la base display re-positionnee `_display_attack_base` (#49/#153/#57a),
l'override drone `_make_mv71_drone_predictions` (#61bis tranche 3) et les follow-ups de boss
(get_additional / get_klaw). Consomme le socle `_shared` (helpers mods/defenseur + vocabulaire commun)."""
from __future__ import annotations

from ._shared import *   # vocabulaire commun (GC, hexgeo, get_attack_prediction, ProbableDamageEvent, auras, ...)
from ._shared import (_PROFILE_INDEX, _weapon_pierce, _add_positional_and_defender_mods,
                      _prediction_is_charging, _target_damage_limits, _apply_ally_attack_dmg_bonus,
                      _round_fix64, _entity_traits, _entity_rarity)
# SLOT 4 d'`IAmountFormula` = `IdunBattle.DSL.AAmountFormula$$CalculateAverage` (division ENTIERE) —
# le foyer PARTAGE (#339/#350-r3b), consomme ici par le mold RANGED (#446-r1). Ne PAS substituer
# `MinMaxDamage$$Avg` ni `AActiveAbility$$MinMaxDamageAverage` : ils arrondissent demi-vers-le-PAIR.
from engine.dsl.base import calculate_average
from engine.entities.traits.unit_trait import entity_trait_names
# #948 : les cles du contexte per-coup d'`EnmityForTheUnworthy` viennent de la classe d'effet --
# un seul foyer de nommage pour les DEUX faces (PREDICTION ici, COMBAT dans `runner/damage_model`).
from engine.entities.effects.loki.enmity_for_the_unworthy import (
    CTX_ADJACENT_UNITS as _ENMITY_CTX_UNITS, CTX_ADJACENT_DA as _ENMITY_CTX_DA)
# #953 : meme regle, meme foyer -- la cle du couple de PV du porteur vit dans la classe d'effet.
from engine.entities.effects.loki.skullsmasher import CTX_OWNER_HEALTH as _SKULLSMASHER_CTX_HEALTH
# #1078-r3 : meme regle, meme foyer -- la cle vit dans la classe d'effet, une seule pour les
# DEUX faces.
from engine.entities.effects.loki.hunter_of_souls import (
    CTX_ADJACENT_PSYKER_FRIENDS as _HUNTER_CTX_PSYKER)
# #1015-r1 : meme foyer de nommage que la face COMBAT (`runner/damage_model.py`).
from engine.entities.effects.loki.close_combat_weakness import (
    CTX_ADJACENT_ENEMIES as _CCW_CTX_ADJACENT_ENEMIES)
# #1073 : meme regle, memes deux cles que la face COMBAT -- le canal COUPS de `SynapticInsight`
# (`CTX_ADJACENT_TYRANID`) et le substrat de synapse partage avec `NornCrownEffect` (#1011).
from engine.entities.effects.loki.synaptic_insight import (
    CTX_ADJACENT_TYRANID as _SI_CTX_ADJACENT_TYRANID)
from engine.entities.effects.loki.norn_crown import (
    CTX_TEAM_SYNAPSE_POSITIONS as _NORN_CTX_SYNAPSE, SYNAPSE_TRAIT as _SYNAPSE_TRAIT)
from engine.services.custom_normal_attack import substitutes_normal_attack
from engine.runner.abilities.loki.mv71 import pick_tile_scene
from engine.services.battle_query import get_attack_weapon_for_default_normal_attack
from engine.services.damage_modifiers import DamageModifiers
from engine.runner.abilities.loki import mv71 as _mv71
from engine.services.damage_prediction import DamagePredictionResult
from engine.entities.effects.loki.deathwing import CTX_ADJACENT_DA as _CTX_ADJACENT_DARK_ANGELS_FRIENDS   # #1042-r5
from engine.entities.effects.loki.daemonic_patrons import CTX_COUNT_KEY as _CTX_ADJACENT_TAUNTED_ENEMIES   # #1042-r5
from engine.entities.effects.loki.norn_crown import CTX_TGT_EFFECT_NAMES as _CTX_TGT_EFFECT_NAMES   # #1042-r5


# ── #57c-C : overrides `<Boss>_NormalAttackAbility.PredictAttack` (attaque normale + follow-up) ──
# Dispatch natif ActiveAbilityType→classe : l'attaque NORMALE de certains boss est instanciee sur une
# SOUS-CLASSE qui surcharge PredictAttack = base ALoki (IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$PredictAttack) + prediction ADDITIONNELLE calculee
# sur scenario VIERGE puis sommee via `IdunBattle.Core.Services.DamagePredictionResult$$Add` (appliedHits natif 1+1=2).
# TROIS molds (l'instance porte la CONFIG du passif du kit). Le balayage des surcharges est CLOS :
# `<X>_NormalAttackAbility$$PredictAttack` n'existe que pour `ALoki` (la base), `Boltstorm`,
# `ProperKilly` et `RighteousRepugnance` — et chacun des trois derives porte EXACTEMENT 2 xrefs DATA
# (table de methodes + vtable), donc AUCUN n'est un corps DEDUPLIQUE partage par plusieurs classes.
#  - RANGED (`IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$PredictAttack`, gate arme choisie `!IsMelee`) :
#    `IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$GetAdditionalDamagePrediction` = eval SLOT 4 (= `AAmountFormula$$CalculateAverage`,
#    donc `(min + max) / 2` TRONQUE) de `GetAdditionalDamageAmount
#    IdunBattleLogic.Entities.Abilities.Active.Loki.TalonOfHorus_NormalAttackAbility$$GetAdditionalDamageAmount` = `RandomAmount(var 0xc minDmg, var 0xd maxDmg)` → hits = ConfigConst(0x2f nrOfHits),
#    profil = `AbilityConfiguration.GetDamageProfile` du passif, et le pipeline de prediction du
#    slot appele APPLIQUE les modifiers de l'attaquant (aucun argument ne les transporte, mais le
#    service les recalcule : mesure #446-r1, cf. ci-dessous).
#    PORTEUR REEL CONFIRME (#446-r1) : `Boltstorm` (passif 1090 de `templAggressor`, dont l'attaque
#    normale concrete EST `1128 Boltstorm_NormalAttack`). L'ancienne hypothese « Gulgortz/LightImUp
#    = ce mold » reste REFUTEE (varTrace 2468 s14 : le +3×1496 de u89 = les 3 effets
#    FoulInfusion_ExtraHits du canal #179 GLOBAL ; la coincidence LightImUp.minDmg[50] ==
#    FoulInfusion.dmg[50] == 831 avait masque la vraie source) — c'est un AUTRE porteur qui a ferme
#    le registre, pas celle-la.
#  - MELEE ADDITIONAL-DAMAGE (`IdunBattleLogic.Entities.Abilities.Active.Loki.RighteousRepugnance_NormalAttackAbility$$PredictAttack`, gate arme
#    choisie `IsMelee` — la gate INVERSE de celle du mold RANGED) : son
#    `IdunBattleLogic.Entities.Abilities.Active.Loki.RighteousRepugnance_NormalAttackAbility$$GetAdditionalDamagePrediction` a le corps
#    IDENTIQUE a celui de `Boltstorm` (memes appels, memes slots, meme SLOT 4 ; seuls le guard
#    statique et l'adresse different — copies COMDAT non fusionnees), donc le MEME mold Python.
#    PORTEUR (#446-r3) : `RighteousRepugnance` (passif d'`adeptMorvenn`, HERO au pool, dont l'attaque
#    normale concrete EST `1182 RighteousRepugnance_NormalAttack`).
#  - MELEE KLAW (`IdunBattleLogic.Entities.Abilities.Active.Loki.ProperKilly_NormalAttackAbility$$PredictAttack`, gate `!IsRanged`) :
#    `IdunBattleLogic.Entities.Abilities.Active.Loki.ProperKilly_NormalAttackAbility$$GetKlawAttack1Prediction` = n = ConfigConst(0x2f nrOfHits=1) coups de
#    `IdunBattleLogic.Entities.Abilities.Active.Loki.ProperKilly_NormalAttackAbility$$GetFirstAttackDamage` = `PercentageOf(StatAmount(target, Health=5, part=2 Max),
#    ConfigConst(0x3b dmgPct=60), mode 0)`, profil Power(40), chaque coup via `GetKlawAttack1Hit-
#    Prediction IdunBattleLogic.Entities.Abilities.Active.Loki.ProperKilly_NormalAttackAbility$$GetKlawAttack1HitPrediction`. Ghazghkull — ZERO porteur dans ce
#    build (`unit_map find --ability ProperKilly` = 0 sur les 5 voies, ET balayage direct de tous les
#    `all_unit_ids()` du gameconfig = 0) : registre INERTE, mold NON CONFRONTABLE.
# ⚠ CLEAVE D'EXECUTION SANS ATTRIBUTION DE PREDICTION — asymetrie NATIVE a ne PAS « corriger »
#    (#446-r3b, CONFRONTE LIVE : `docs/rl/case-446-r3b-fealty-talon-asymetrie.md`) :
#    `<X>_NormalAttackAbility$$GetAdditionalDamageBehaviour` existe pour QUATRE abilities
#    (`Boltstorm`, `RighteousRepugnance`, `Fealty`, `TalonOfHorus`), mais
#    `$$GetAdditionalDamagePrediction` n'existe que pour les DEUX premieres, et ni `Fealty` ni
#    `TalonOfHorus` ne portent de `$$PredictAttack`.
#    ⚠ CE QUE CETTE ASYMETRIE EST VRAIMENT, ET SA CAUSE (RECTIFIE par #478, qui a LU le second
#    consommateur et l'a CONFRONTE) : `$$GetAdditionalDamageBehaviour` a **DEUX** consommateurs.
#      * `<X>_NormalAttackAbility$$GetAdditionalTargetsAttackBehavior` -> le **CLEAVE**, sur des
#        cibles ADDITIONNELLES (`Execute<X>` -> `IdunBattleLogic.Entities.DSLBehaviors$$Foreach` sur
#        `<X>Ability$$GetAdditionalTargets`). Il existe pour LES QUATRE.
#      * `<X>_NormalAttackAbility$$GetCustomNormalAttackBehaviour` (vslot 0x4a8, appele par
#        `ALoki_NormalAttackAbility$$ExecuteNormalAttack` et compose DANS l'attaque primaire) -> un
#        paquet sur la cible **PRIMAIRE**, gate par `IsMeleePosition` (`RighteousRepugnance`) ou
#        `DSLTriggers$$IsRangedPosition` (`Boltstorm`). **Il N'EXISTE PAS pour `Fealty` ni
#        `TalonOfHorus`** — le symbole est absent de la table.
#    ⇒ CE REGISTRE-CI est le mirror du SECOND consommateur, pas du cleave, et l'asymetrie n'est pas
#    un oubli : c'est un symbole qui existe pour deux abilities et pas pour les deux autres. Le
#    texte i2 le dit aussi : `RighteousRepugnance` porte la clause « **to the target** and to all
#    enemy units adjacent to both [...] » (les DEUX volets), `TalonOfHorus` ne porte que le second.
#    Inscrire `Fealty`/`TalonOfHorus` ici par analogie serait un fork de port : MESURE, la greffe
#    ajoute `+2700/+4050/+3 coups` a `Fealty` et `+1953/+2931/+3` a `TalonOfHorus`, et le cliquet
#    `tests/engine/test_446_r3b_fealty_talon_live.py` ROUGIT.
#    ⚠ Les DEUX volets sont desormais portes cote COMBAT (`runner/abilities/loki/additional_targets.py`,
#    #478) — y compris le paquet sur la cible primaire, qui valait **1565 PV** non infliges sur
#    `adeptMorvenn`. Ne pas relire ce commentaire comme « le combat ne fait rien de plus ».
# Cle de dispatch = le PASSIF de l'ENTITE (`UnitConfiguration.PassiveAbilities`, lu par
# `IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromPassive` ; l'instance
# native lit SA config = celle du passif). Le KIT gameconfig n'en est plus que le REPLI quand le
# canal de mesure est muet — cf. `engine.services.custom_normal_attack` (#419-r1-tr14-r5).
_RANGED_FOLLOWUP_PASSIVES = ("Boltstorm",)   # #446-r1 : porteur `templAggressor`, confronte live
_MELEE_FOLLOWUP_PASSIVES = ("RighteousRepugnance",)   # #446-r3 : porteur `adeptMorvenn`, confronte live
_MELEE_KLAW_PASSIVES = ("ProperKilly",)


def get_additional_damage_prediction(scene, att_id, tgt_id, ability_name, mods=None, hits_ctx=None):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$GetAdditionalDamagePrediction` (et son JUMEAU au corps
    identique `IdunBattleLogic.Entities.Abilities.Active.Loki.RighteousRepugnance_NormalAttackAbility$$GetAdditionalDamagePrediction`) — le mold
    est le MEME des deux cotes de la gate : seul `PredictAttack` differe (`!IsMelee` pour `Boltstorm`,
    `IsMelee` pour `RighteousRepugnance`), et c'est l'APPELANT qui porte cette difference.
    amount = `CalculateAverage` du `RandomAmount(minDmg, maxDmg)` (SLOT 4 de `IAmountFormula` :
    `FUN_180025fb0(4, <IAmountFormula>, <noeud>, ...)` -> `IdunBattle.DSL.AAmountFormula$$CalculateAverage`,
    donc `(min + max) / 2` en division ENTIERE, cf. `engine.dsl.base.calculate_average`), hits =
    `GetAttackHits(caster, target, 0, <ability>, ConfigConst(0x2f nrOfHits))` (#419-r1-tr9-r4 : le
    constant est la BASE D'ARME du fold, pas son compte de coups — cf. le bloc ci-dessous), profil
    propre du passif, scenario VIERGE (armure/bouclier de la cible re-disponibles — quirk natif
    mirrore), et les MODIFIERS DE L'ATTAQUANT sont ceux de l'attaque porteuse.

    ⚠ DEUX corrections de #446-r1, toutes deux mesurees sur `templAggressor` (voir
    `docs/rl/case-446-r1-boltstorm-followup.md`) — le port lisait `minDmg` seul et passait
    `mods=None` :

    * le SLOT 4 n'est pas « le MIN » : c'est `CalculateAverage`, deja porte et deja documente comme
      tel par `engine.dsl.base` (#339/#350-r3b). Sur `Boltstorm` a (level 50, mult 180) :
      `minDmg = 1496`, `maxDmg = 2194` -> amount = `1845`, pas `1496` ;
    * les modifiers sont APPLIQUES. Aucun argument du slot appele ne les transporte — d'ou la
      lecture d'origine — mais le service de prediction les recalcule depuis l'attaquant. Mesure :
      sur la cible ISOLEE, le fold vaut exactement `(1329, 3183)` avec les mods de l'attaque
      porteuse (`[1.5]`, bonus d'ELEVATION sur `MC1_67`) contre `(885, 2121)` sans eux, et
      `natif - base_native_mesuree` vaut `(1329, 3183)`."""
    ctx = scene.ctx(att_id)
    if ctx is None:
        return None
    lvl = scene.ablvl_by_id.get(att_id)
    _mult = scene.mult(att_id)
    _mn = ability_var(ability_name, "minDmg", lvl, multiplier_pct=_mult)
    _mx = ability_var(ability_name, "maxDmg", lvl, multiplier_pct=_mult)
    n = ability_var(ability_name, "nrOfHits", is_constant=True)
    if not _mn or _mn <= 0 or not _mx or _mx <= 0 or not n or n <= 0:
        return None
    amount = calculate_average(int(_mn), int(_mx))
    if amount <= 0:
        return None
    # #419-r1-tr9-r4 : `nrOfHits` n'est PAS le compte de coups du fold, c'est sa BASE D'ARME. Le
    # natif la fait traverser la MEME facade que les coups de l'attaque porteuse -- le slot `0xb5`
    # de l'`IBattleQuery`, identifie par le proxy
    # `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass216_0$$u003CGetAttackHitsu003Eb__0`
    # (meme interface, meme forme d'arguments), c'est-a-dire
    # `IdunBattle.Core.Services.BattleQuery$$GetAttackHits(attacker, defender, hitGroupIndex, ability,
    # attackWeaponHits)` -> `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`, qui somme
    # `weaponHits + ExtraHits(0x11) [+ ExtraHitsMelee(0x17) si melee]` puis applique les descripteurs
    # de bonus/malus de coups et termine par `System.Math.Max(hits, 0)`.
    # Le couple passe est le MEME que celui de la base (`caster` = `AbilityEntities@+0x08`, `target` =
    # `@+0x10`), donc TOUS les canaux de coups s'appliquent au fold aussi -- y compris les malus
    # DEFENSEUR. `hits_ctx` = exactement les arguments de l'appel de base, `weapon_hits` mis a part.
    # MESURE (`probe_419r1tr9_r4_boltstorm_pred.py`, `templAggressor` -> `necroWarden` sur `LightCover`) :
    # le natif rend 2 coups au total (1 de base + 1 de fold, le malus -2 mordant DES DEUX COTES) la ou
    # le port en rendait 4 (1 + `nrOfHits` = 3) -- un facteur ~2 sur les deux bornes.
    # ABSENT du mold KLAW (`get_klaw_attack1_prediction`) : son decompile boucle `nrOfHits` fois sur
    # `GetKlawAttack1HitPrediction` et n'appelle JAMAIS `GetAttackHits` -- ne pas generaliser.
    #
    # #419-r1-tr9-r4-r1 -- LE CONTEXTE (`AbilityOrEffect`) DU FOLD EST CELUI DE L'ATTAQUE PORTEUSE.
    # Un residu affirmait que le natif y passe l'ability du PASSIF, donc `IsNormalAttack` FAUX ; il
    # est REFUTE, au decompile ET par mesure. La signature reelle est
    # `GetAdditionalDamagePrediction(entities:AbilityEntities, abilityState:AbilityState)` -- ghidra
    # INVERSE les noms (son `entities` est le `this` de l'ability, son `abilityState` est le vrai
    # `entities`, et le vrai `abilityState` est un 4e argument qu'il ne montre pas). Le contexte sort
    # de `IdunBattle.Core.AbilityOrEffect$$op_Implicit` (surcharge `activeAbility`) applique a CE
    # parametre, que `Boltstorm_NormalAttackAbility$$PredictAttack` recopie depuis SON PROPRE
    # parametre avant de le retransmettre -- il ne peut donc pas diverger de celui de la base.
    # Partager `hits_ctx` (defaut `is_normal_attack=True`) est ainsi le mirror EXACT, pas un raccourci.
    # MESURE (`probe_419r1tr9_r4_r1_fold_context.py`, `PowerTrip` greffe sur `templAggressor`, 4 bras
    # NATIFS) : le fold natif passe de 3 a 4 coups quand `PowerTrip_FullHealth` -- dont le trigger est
    # `IsNormalAttack & get_OwnerIsCaster` -- est actif, sur les 3 cibles. Un contexte de PASSIF
    # rendrait `StaticBattleRules.ActiveAbility$$IsRegularAttack` FAUX et le fold ne gagnerait rien.
    #
    # #419-r1-tr9-r4-r2 (`hitGroupIndex`, le `0` litteral du 3e argument) -- TRANCHE : ce n'est pas
    # une constante de facade mais un vrai parametre, que `DamagePrediction$$GetAttackHits` pose en
    # `Nullable<int>` dans l'`AbilityEntities` qu'il synthetise. Il n'atteint le DSL que par
    # `IdunBattle.Entities.Abilities.AbilityEntities$$get_IsFirstHitGroup` (`HasValue && Value == 0`),
    # lu par `Idun.Source.IdunBattle.Logic.Entities.Triggers.IsFirstHitGroupInAttackTrigger$$ShouldTrigger`,
    # dont l'unique consommateur est
    # `IdunBattle.Entities.Effects.Loki.LegendaryCommander_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`
    # -- NON PORTE. Balayage recoupe sur le dump GHIDRA (qui contient les gshared, contrairement au
    # dump Frida) : ZERO autre symbole `HitGroupIndex`. Le port n'a donc RIEN a modeliser tant que cet
    # effet n'entre pas au registre ; le jour ou il y entre, le fold vaut `IsFirstHitGroup == True`.
    hits = int(n)
    if hits_ctx is not None:
        hits = attack_hits_with_modifiers(weapon_hits=int(n), **hits_ctx)
    prof = ((GC.ability(ability_name) or {}).get("constants") or {}).get("damageProfile") or ""
    prof_ratio = int((GC.damage_profile(prof) or {}).get("PiercingRatio") or 0)
    # pierce = profil + ExtraPierce stat (IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio, meme pipeline 0x27)
    pierce = max(0, min(100, prof_ratio + ctx.extra_pierce + ctx.extra_pierce_ranged))
    # #267-r1 : MkXGravis lu sur l'ENTITE (`GetBaseDamageWithFixedPiercedArmor` -> HasTrait(defender, 0x3f5)).
    tgt_hit_mult = target_hit_multiplier(TraitFactory.create_many(_entity_traits(scene, tgt_id)))
    return get_attack_prediction(
        target_current_health=scene.hp(tgt_id) or 0, initial_damage=int(amount), hits=int(hits),
        profile_type=_PROFILE_INDEX.get(prof, 0), pierce_pct=pierce, armor=scene.armor(tgt_id),
        mods=mods, hit_mult=tgt_hit_mult, target_shield=scene.shield(tgt_id),
        target_limits=_target_damage_limits(scene, tgt_id, prof),
        target_prevents_overkill=scene.prevents_overkill(tgt_id),   # #195 : HasFlag(cible, 0x13)
        defender_block_amount=defender_prediction_block_amount(scene, tgt_id, prof),  # #69 gate NoBlocking
        attacker_effects=scene.effects(att_id),   # #202 : PredictAttackRaw universel
        attacker_ctx=ctx)                         # #R34 : MightCrit = CouldCrit(attaquant)


def get_klaw_attack1_prediction(scene, att_id, tgt_id, ability_name, mods=None):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ProperKilly_NormalAttackAbility$$GetKlawAttack1Prediction` — klaw MELEE : n coups de
    `PercentageOf(MaxHealth EFFECTIF de la cible, dmgPct, mode 0)` (`IdunBattleLogic.Entities.Abilities.Active.Loki.ProperKilly_NormalAttackAbility$$GetFirstAttackDamage`),
    profil propre (Power 40), scenario VIERGE, coups chaines (armure depletee entre coups — c'est le
    per-coup standard de get_attack_prediction).

    ⚠ `mods` (#446-r3) — le port passait `mods=None` en dur, la lecture d'origine du mold RANGED que
    #446-r1 a REFUTEE par mesure. Le decompile tranche pareil ICI, et c'est un mirror, pas une
    analogie : NI le slot appele par ce mold NI celui du mold additional-damage ne transporte de
    `DamageModifiers` en argument, et les DEUX surcharges de
    `IdunBattle.Core.Services.DamagePrediction$$PredictAttack` convergent sur le MEME
    `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` (xrefs mesurees : ses deux seuls
    appelants sont les closures `<PredictAttack>b__0` des `DisplayClass12_0` et `DisplayClass13_0`).
    C'est donc le service qui recalcule les modifiers, sur les deux chemins.
    NON CONFRONTE — `ProperKilly` n'a AUCUN porteur dans ce build (cf. bloc de registre ci-dessus),
    donc ce bras reste inatteignable et la mesure n'a lieu que sur le mold jumeau."""
    ctx = scene.ctx(att_id)
    if ctx is None:
        return None
    pct = ability_var(ability_name, "dmgPct", is_constant=True)
    n = ability_var(ability_name, "nrOfHits", is_constant=True)
    hpmax = scene.hpmax(tgt_id)
    if not pct or pct <= 0 or not n or n <= 0 or not hpmax:
        return None
    amount = _round_fix64(Fraction(int(pct) * int(hpmax), 100), 0)   # PercentageOf mode 0 (half-to-even)
    prof = ((GC.ability(ability_name) or {}).get("constants") or {}).get("damageProfile") or ""
    prof_ratio = int((GC.damage_profile(prof) or {}).get("PiercingRatio") or 0)
    pierce = max(0, min(100, prof_ratio + ctx.extra_pierce + ctx.extra_pierce_melee))
    # #267-r1 : MkXGravis lu sur l'ENTITE (`GetBaseDamageWithFixedPiercedArmor` -> HasTrait(defender, 0x3f5)).
    tgt_hit_mult = target_hit_multiplier(TraitFactory.create_many(_entity_traits(scene, tgt_id)))
    return get_attack_prediction(
        target_current_health=scene.hp(tgt_id) or 0, initial_damage=int(amount), hits=int(n),
        profile_type=_PROFILE_INDEX.get(prof, 0), pierce_pct=pierce, armor=scene.armor(tgt_id),
        mods=mods, hit_mult=tgt_hit_mult, target_shield=scene.shield(tgt_id),
        target_limits=_target_damage_limits(scene, tgt_id, prof),
        target_prevents_overkill=scene.prevents_overkill(tgt_id),   # #195 : HasFlag(cible, 0x13)
        defender_block_amount=defender_prediction_block_amount(scene, tgt_id, prof),  # #69 gate NoBlocking
        attacker_effects=scene.effects(att_id),   # #202 : PredictAttackRaw universel
        attacker_ctx=ctx)                         # #R34 : MightCrit = CouldCrit(attaquant)


def _normal_attack_followup_prediction(scene, att_id, tgt_id, is_melee, weapon_found, mods=None,
                                       hits_ctx=None):
    """Selecteur du mold follow-up de l'attaquant (cf. bloc ci-dessus). None = pas de fold
    (pas d'arme trouvee / kit sans passif concerne / gate melee-ranged non satisfaite).

    `mods` = les modifiers de l'ATTAQUE PORTEUSE, threades jusqu'aux molds (#446-r1, #446-r3) : le
    natif ne les passe pas en argument, son service de prediction les recalcule — meme resultat,
    et c'est ce que la mesure impose.

    `hits_ctx` = les arguments de l'appel de coups de l'ATTAQUE PORTEUSE, `weapon_hits` mis a part
    (#419-r1-tr9-r4). Les DEUX molds additional-damage font traverser `nrOfHits` a la meme facade
    `GetAttackHits` ; le mold KLAW, lui, ne l'appelle PAS (il boucle) — c'est pourquoi seul le
    premier le recoit.

    ⚠ La gate melee/ranged est la SEULE chose qui separe les deux molds additional-damage : le mold
    RANGED (`Boltstorm`) folde quand l'arme choisie n'est PAS melee, le mold MELEE
    (`RighteousRepugnance`) quand elle L'EST. Un porteur ne peut donc jamais folder par les deux."""
    if not weapon_found:
        return None                       # mirror `FindAttackWeapon != null` (IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$PredictAttack / IdunBattleLogic.Entities.Abilities.Active.Loki.RighteousRepugnance_NormalAttackAbility$$PredictAttack / IdunBattleLogic.Entities.Abilities.Active.Loki.ProperKilly_NormalAttackAbility$$PredictAttack)
    # #419-r1-tr14-r5 : `carries` mirrore `IdunBattle.Entities.Factories.UnitFactory$$
    # GetCustomNormalAttackTypeFromPassive` — la cle de dispatch est `UnitConfiguration.
    # PassiveAbilities` (fait d'ENTITE, mesure `UnitContext.passive_abilities`), et le KIT n'est
    # plus qu'un REPLI de canal muet. Un montage qui touche a la liste de passifs (toute greffe
    # `replace=True`) ramene l'attaque normale a `69` cote natif : le port doit le suivre.
    # #419-r1-tr14-r5-r2 : la cascade a DEUX voies (`GetCustomNormalAttackTypeFromPassive` puis,
    # si elle rend `null`, `GetCustomNormalAttackTypeFromActive` sur `UnitConfiguration.
    # ActiveAbilities`). Les deux listes sont threadees pour que le predicat decide de la cascade
    # ENTIERE -- meme si, sur ce build, l'unique entree de la table ACTIVE ne peut rendre que
    # `RogalDorn_NormalAttack`, qui n'est le mold d'aucun de ces trois passifs.
    # #419-r1-tr14-r5-r2-r1 : la TROISIEME branche (`Traits.Contains(0x7e7 Boss)` -> `1030
    # Loki_NormalBossAttack`). Meme substrat d'ENTITE que la garde `Erratic`/`Harmless` -- lu par
    # `entity_trait_names`, qui retombe sur le kit quand l'entite n'a pas de `UnitContext`.
    # #419-r1-tr14-r5-r2-r2-r1 : le QUATRIEME etage (la garde `FilterNewList` du repli generique)
    # lit `UnitConfiguration.ActiveAbilities`, l'etat AVANT la fabrique -- PAS `active_abilities`,
    # qui est l'etat APRES et rendrait la garde tautologique.
    _actx = scene.ctx(att_id)
    _pas = getattr(_actx, "passive_abilities", None)
    _act = getattr(_actx, "active_abilities", None)
    _cfg = getattr(_actx, "config_active_abilities", None)
    _vis = scene.vis_by_id.get(att_id)
    _tra = entity_trait_names(_actx, _vis)

    def carries(nm: str) -> bool:
        return substitutes_normal_attack(nm, passive_abilities=_pas, visual_id=_vis,
                                         active_abilities=_act, traits=_tra,
                                         config_active_abilities=_cfg)

    if not is_melee:
        for nm in _RANGED_FOLLOWUP_PASSIVES:
            if carries(nm):
                return get_additional_damage_prediction(scene, att_id, tgt_id, nm, mods=mods,
                                                        hits_ctx=hits_ctx)
    else:
        for nm in _MELEE_FOLLOWUP_PASSIVES:
            if carries(nm):
                return get_additional_damage_prediction(scene, att_id, tgt_id, nm, mods=mods,
                                                        hits_ctx=hits_ctx)
        for nm in _MELEE_KLAW_PASSIVES:
            if carries(nm):
                return get_klaw_attack1_prediction(scene, att_id, tgt_id, nm, mods=mods)
    return None


def _display_attack_base(scene, att_id, attack_pos, is_melee):
    """Base ATTACK de la chaine DISPLAY, re-positionnee a la tuile candidate (#49/#153/#57a) :
    base = CURRENT(du pas) − aura_modele(position reelle) + aura_modele(tuile candidate). Les AURAS
    stat-mod d'allies (RitesOfBattle IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfBattleAbility$$CreateBehaviour, PathOfCommand IdunBattleLogic.Entities.Abilities.Triggered.Loki.PathOfCommandAbility$$CreateBehaviour) sont re-evaluees a
    `attack_pos` ; les mods NON-positionnels (ex. SummaryExecution_BaseEffect 1043 +400, #57a)
    restent inclus via CURRENT. FOYER PARTAGE (#61bis tranche 3) : l'attaque normale ALoki
    (`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetAttackHitPrediction` = GetStat(Attack, Current) + arme) ET le chemin drone MV71
    (delegue b__1 IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility.u003Cu003Ec__DisplayClass7_0$$u003CPredictAttacku003Eb__1 = `StatAmount(Caster, ATTACK, CURRENT)`) font la MEME lecture native.
    Renvoie `(attack_base, carriers, att_grand, att_faction, _ap)` (carriers/gates reutilises par
    l'appelant normal pour les hits/auras)."""
    _ap = attack_pos or scene.pos(att_id)
    # #153 (tranche le flip-flop #45/#58/#67) : la chaine display threade la position candidate de bout
    # en bout — `IdunBattle.Core.Services.DamagePredictionQuery$$GetAllPredictions` construit `UnitPosition(tuile de
    # selection)` et la passe au service ; `IdunBattle.Core.Services.DamagePrediction$$PredictNormalAttack` en tire
    # `get_MainTile` et la pose comme CasterTile dans `AbilityEntities.ctor`. Les auras d'attaque-stat
    # sont donc re-evaluees PAR TUILE CANDIDATE (PAS la valeur bakee a la position reelle). MESURE
    # discriminante seed-31337 (1 decisionView, attaquant reel FIXE adjacent au porteur, seule la tuile
    # varie) : u92 out-ring 12/12 = base Initial (aura PERDUE malgre le stat-mod +1298 present live) ;
    # u96 (reel LOIN du porteur, aucun stat-mod) sur tuile in-ring = base Initial+aura (aura GAGNEE).
    # L'ancien verdict #67 (« aura bakee a la position reelle, GetStat sans position ») etait un artefact :
    # son test etait circulaire (port-vs-port) et son unique GetStat de IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetAttackHitPrediction
    # lit en realite `GetStat(AbilityEntities.Target@+0x10, Health=5, Current)` (HP cible), pas un Attack.
    _att_gu = GC.unit(scene.vis_by_id.get(att_id)) or {}
    att_grand = _att_gu.get("GrandAllianceId")           # gate RitesOfBattle (Imperial)
    att_faction = _att_gu.get("FactionId")               # gate PathOfCommand (IsSameFaction = FactionId)
    # #41 : gate de MATERIALISATION pour la MELEE SEULEMENT (att_real_pos=None -> gate inactif).
    # Mesures seed-31337 (2026-07-20) : RANGED suit purement la tuile CANDIDATE (#153 confirme, gain
    # inclus — u95 thousAhriman reel dist-3 de Calgar, candidate (4,5) in-ring : natif = base+898 sur
    # les 2 canaux ranked/aiPlaybookPredict) ; MELEE ne gagne PAS l'aura d'une tuile candidate (u93
    # deathRotbone s13 : candidate (2,3) in-ring, natif = base Initial ×1.5 elevation EXACT). Le seul
    # cas melee+materialise mesure ((6,5) u91) est candidate-out-ring (les deux modeles le couvrent) —
    # si un futur contre-cas melee+materialise+in-ring sort sans aura native, passer la melee en
    # « jamais d'aura » (v4) et RE le read natif du stat Attack en prediction.
    aura_ctx = {"att_id": att_id, "att_pos": _ap, "att_team": scene.team(att_id),
                "att_grand_alliance": att_grand, "att_faction": att_faction, "board": scene.board,
                "att_real_pos": scene.pos(att_id) if is_melee else None}
    carriers = [(uid, scene.pos(uid), scene.team(uid), scene.mult(uid), scene.ablvl_by_id.get(uid),
                 (GC.unit(scene.vis_by_id.get(uid)) or {}).get("GrandAllianceId"),   # owner grande-alliance
                 (GC.unit(scene.vis_by_id.get(uid)) or {}).get("FactionId"),         # owner faction
                 # #999-r3-r1-r1 -- univers BOARD-WIDE (`Scene.effect_carrier_ids`), pas
                 # `scene.pos_by_id` : le natif n'ecarte aucun porteur par sa position, et
                 # l'ancienne base excluait structurellement toute MACHINE OF WAR (hors-plateau).
                 # Ces `carriers` sont passes tels quels a `_apply_ally_attack_dmg_bonus` et a
                 # `aura_additional_hits_from_allies`. `scene.hp` en TRI-ETAT, comme la face COMBAT.
                 scene.effects(uid)) for uid in scene.effect_carrier_ids(exclude=att_id)
                if scene.hp(uid) is None or (scene.hp(uid) or 0) > 0]
    # #41 : tuile candidate NON-ENTRABLE (BlockEnteringUnits, ex. mur Thorns (1,3) MC1_67) -> le natif
    # perd l'aura MEME materialisee+in-ring (u89 s11 : candidate (1,3) = base Initial 803 ×1.5 elevation
    # EXACT, vs (3,3) propre = 2101 garde) : `GetUnitPositionAtTile` sur tuile bloquee rend une position
    # degeneree -> l'adjacence du re-check echoue. L'elevation, lue sur la TUILE, s'applique toujours.
    _cand_blocked = "BlockEnteringUnits" in ((scene.tile_effects_by_pos or {}).get(tuple(_ap)) or ())
    # #57a : la base CONSERVE les stat-mods NON-positionnels courants (SummaryExecution_BaseEffect
    # 1043 : +400 flat aux Friends(UnitsWithTrait), selecteur SANS noeud d'adjacence — decompile
    # `IdunBattle.Entities.Effects.Loki.SummaryExecutionEffect$$CreateTargetSelector` ; vecu 1357 s15 u135 : natif per-hit
    # = 1.2/1.8 × 1496 (CURRENT) et non ×1096 (INITIAL)). Modele : base = CURRENT(du pas)
    # − aura_modele(position reelle) + aura_modele(tuile candidate) — algebriquement
    # = INITIAL + mods-non-aura + auras re-evaluees (#153) ; identique a l'ancien INITIAL+aura
    # quand aucun mod non-aura n'est pose (aura_baked == aura_modele(reel), cf. #49 exact).
    _aura_cand = 0 if _cand_blocked else aura_attack_bonus_from_allies(carriers, aura_ctx)
    _rp = scene.pos(att_id)
    _aura_real = (aura_attack_bonus_from_allies(
        carriers, {**aura_ctx, "att_pos": _rp, "att_real_pos": _rp if is_melee else None})
        if _rp is not None else 0)
    attack_base = scene.attack_current(att_id) - _aura_real + _aura_cand
    return attack_base, carriers, att_grand, att_faction, _ap


_MV71_CONFIG = "MV71SniperDroneSquad"    # l'entree gameconfig (passif 1119) qui porte constants/variables


def _make_mv71_drone_predictions(scene, att_id, tgt_id, attack_pos, *, meta=False):
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$PredictAttack`, branche DISTANCE (#61bis
    tranche 3 — la branche melee delegue a ALoki et reste dans `make_normal_attack_predictions`).

    Mirror du decompile (re-lu 2026-07-22) :
      - tile = PickTile — delegue b__0 IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility.u003Cu003Ec__DisplayClass7_0$$u003CPredictAttacku003Eb__0 = `() => PickTile(entities, firstOnly=0)`, LE MEME
        PickTile que l'execution (memoise par un service de cache) -> `pick_tile_scene` (hydrateur
        scene du port runner, scoring partage). Parent = la POSITION CANDIDATE (#153).
        **Aucune tuile -> prediction VIDE**, et c'est LU verbatim (#506-r2, re-lu sur `rnca9r7q6c`) :

            local_4c0 = <PickTile>(...);
            if (local_4c0 == null) {
                FUN_1802abdd0(&result, 0, 0xa0);      // memset(&result, 0, 0xa0)
                result.<+0x38> = new List<...>();     // la seule ecriture non nulle
            }
            else { ... la vraie prediction ... }
            *this = result;                            // copie 0xa0 octets

        La structure rendue est donc ENTIEREMENT A ZERO -- `CurrentHealth@0`, `CurrentArmor@4`,
        `CurrentShield@8` compris -- avec pour seul contenu une liste de blocks VIDE. Ce n'est pas
        une absence d'event : c'est un event dont la prediction est nulle.

        ⚠ **NE PAS « REPARER » CETTE BRANCHE PAR ANALOGIE AVEC #506 §3.4.** La branche SANS ARME
        d'`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$PredictAttack`
        a la MEME FORME cote port (`DamagePredictionResult()` a zero) et c'etait un BUG : elle,
        le natif n'invente aucune structure, il appelle le slot `0x26` d'`IBattleQuery` contre la
        VRAIE cible, si bien que sa prediction porte les PV reels et que `get_WillBeKill` rend
        FAUX. **ICI le natif fait bien le `memset`**, donc `get_WillBeKill` (borne MIN >= PV
        courants) y lit `0 >= 0` = VRAI -- cote NATIF comme cote port. Le port est CONFORME, et le
        `killSure` vrai de ce chemin est le comportement du jeu. Les deux corps natifs sont
        DIFFERENTS ; seule leur silhouette Python se ressemblait. Garde :
        `tests/engine/runner/test_mv71_sniper_drone_live.py::test_506r2_*`.
      - hits = `ExtraHitsComponent(CASTER).CurrentValue + 1`, stocke DisplayClass@0x148 et consomme
        par le 3e delegue (DAT_183279860 — « b__2 » sans symbole ghidra, alias « m860 ») : role
        compte-de-coups tranche PAR ELIMINATION (b__0 = tile, b__1 = degat : aucun autre lecteur
        possible du champ @0x148) + position = celle du delegue hits par defaut du fallback ALoki
        (slot 0x25, DAT_183283000). Confronte live via `appliedHits` d'aiPlaybookPredict.
      - degat = delegue b__1 IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility.u003Cu003Ec__DisplayClass7_0$$u003CPredictAttacku003Eb__1 = `StatAmount(Caster, ATTACK, CURRENT)` ->
        `_display_attack_base` (MEME lecture display que la normale, re-positionnee #153).
      - arme = la config d'attaque du DRONE (service slot 0xc0 = unit-config par id, champ @0x18),
        resolue par la distance TUILE DU DRONE -> cible (le drone tire de SA tuile) ; pierce =
        PiercingRatio du profil + ExtraPierce de l'unite passee au service (`GetUnit(tile) ?? caster`
        -> le CASTER a la prediction, aucun drone encore pose — flag : au fallback-cap la tuile porte
        un drone, l'unite native serait CE drone, ExtraPierce 0 dans les deux cas).
      - attribution = Nullable<AbilityOrEffect>(1076) ; canal additional-hits keye sur l'attackTypeId
        du drone (unit-config @0x10) : `GetAdditionalHitsFromEffectsForPrediction` +
        `AddAdditionalHitsToPrediction` — MEME canal #179 que la normale (effets du CASTER + auras).
      - modifiers (ARBITRE LIVE, probe_61bis_pred seed 61011) : le widget attaquant est **ZEROE**
        (memset `&local_3f8` — le `param_4` du playbook N'EST PAS forwarde, contrairement a la
        branche melee qui le passe a ALoki) -> AUCUN mod ATTAQUANT-effets (builder IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction cote
        appelant ; residu flagge : aucun datapoint caster-avec-effet-d'attaque encore). MAIS les
        mods POSITIONNELS + DEFENSEUR sont calcules EN AVAL DANS le service et S'APPLIQUENT :
          . ELEVATION evaluee a la TUILE DU DRONE vs cible (rows x1.5 EXACT quand la tuile choisie
            est surelevee : (3,6)/(2,6)/(6,6) elev2 vs cible elev1 — le flip post-cast de (4,6)
            1.5->1.15 quand le drone reel occupe (3,6) le prouve) ;
          . DEFENSEUR : cible Markerlit -> x1.15 EXACT sur les rows plates (3694,5541 = 3212,4818
            x1.15), compose x1.725 = 1.5x1.15 sur les rows surelevees.
        -> port : `_add_positional_and_defender_mods(attack_pos = TUILE DU DRONE)` sur un
        `DamageModifiers()` vierge (l'attaquant du coup = le drone, identite/niveau = caster,
        mirror du `unit` passe au service)."""
    ctx = scene.ctx(att_id)
    if ctx is None:
        return None
    consts = (GC.ability(_MV71_CONFIG) or {}).get("constants") or {}
    unit_id = consts.get("unitId")                       # GetStringConstant(cfg, 0) = tauSmnDroneSniper
    max_summons = int(consts.get("maxSummons") or 3)
    t_pos = scene.pos(tgt_id)
    if unit_id is None or t_pos is None:
        return None
    tile_pos = pick_tile_scene(scene, att_id, tgt_id, unit_id, max_summons,
                               parent_pos=attack_pos or scene.pos(att_id))
    if tile_pos is None:
        ev = ProbableDamageEvent(target=tgt_id, prediction=DamagePredictionResult())
        return (ev, {"mv71": True, "tile": None}) if meta else ev
    # hits (delegue « m860 ») = ExtraHits CURRENT du CASTER + 1 — PAS la formule arme
    # (AttackHitsWithModifiersFormula n'est PAS appelee sur ce chemin : ni GetStuckIn, ni malus
    # defenseur LightCover/Parry, ni hits d'arme).
    _xh = scene.extra_hits_current(att_id)
    hits = 1 + int(_xh if _xh is not None else (ctx.stat(StatType.EXTRA_HITS) or 0))
    # degat (delegue b__1) = StatAmount(Caster, ATTACK, CURRENT) — foyer partage display (#153).
    attack_base, carriers, att_grand, att_faction, _ap = _display_attack_base(
        scene, att_id, attack_pos, is_melee=False)
    # arme du drone par distance tuile->cible (mirror config d'attaque @0x18 du unit-config drone).
    _adj = are_tiles_adjacent(tile_pos, t_pos, scene.board)
    _d = hexgeo.distance(tile_pos, t_pos)
    w, w_ranged = get_attack_weapon_for_default_normal_attack(unit_id, _adj, dist=_d)
    prof_name = (w or {}).get("DamageProfile")
    _dpw = GC.damage_profile(prof_name) or {}
    dir_pierce = ctx.extra_pierce_ranged if w_ranged else ctx.extra_pierce_melee
    pierce = max(0, min(100, int(_dpw.get("PiercingRatio") or 0) + ctx.extra_pierce + dir_pierce))
    mods = DamageModifiers()                             # widget attaquant ZEROE (cf. docstring)
    # POSITIONNELS + DEFENSEUR (service-side, arbitre live) : attack_pos = LA TUILE DU DRONE
    # (elevation drone->cible), defenseur incl. Markerlight (faction caster = T'au, threadee #61bis).
    _add_positional_and_defender_mods(mods, scene, att_id, tgt_id, not w_ranged, tuple(tile_pos),
                                      t_pos, damage_profile=prof_name)
    # canal additional-hits #179 (cle native = attackTypeId du drone) — memes sources que la normale.
    att_effects = scene.effects(att_id)
    # #267-r1 : traits de la CIBLE = substrat d'ENTITE (pendant du `tgt_traits` de
    # `runner/operations/additional_hits.py`, deja sur `target_trait_names`).
    _ah_ctx = {"is_melee": False,
               "tgt_traits": _entity_traits(scene, tgt_id),
               _CTX_TGT_EFFECT_NAMES: frozenset(
                   n for n in (getattr(_e, "name", None) for _e in (scene.effects(tgt_id) or [])) if n),
               # #419-r1-tr11-r3 : idem la facade normale, mais la tuile d'attaque est celle du
               # DRONE (`tile_pos`) -- c'est elle que ce chemin thread deja partout ailleurs
               # (`_add_positional_and_defender_mods`, selection d'arme, distance `_d`).
               "att_pos": tuple(tile_pos), "t_pos": t_pos}
    # #1065 -- ce chemin (attaque du DRONE `MV71SniperDroneSquad`) ne thread NI `owner_id`/`att_id`
    # NI `is_charging` / `is_normal_attack` : le tireur est une entite SPAWNEE dont la tuile
    # d'attaque n'est pas celle du caster, et aucun descripteur du canal #179 gate sur ces cles n'a
    # de porteur qui l'emprunte (`FragLanceEffect` vit sur `astraSmnDeathRider`, hors drone). Les
    # gates concernes rendent donc FAUX -- degradation MESUREE, pas oubli. A threader le jour ou un
    # porteur de ce chemin en aura besoin.
    _aura_hits = aura_additional_hits_from_allies(
        carriers, {"att_id": att_id, "att_pos": _ap, "att_team": scene.team(att_id),
                   "att_faction": att_faction, "att_grand_alliance": att_grand,
                   # #202-B : traits de l'ATTAQUANT — le CASTER, pas le drone (gate Daemon
                   # d'InfernalPacts : disjunct HasTrait(0x3fb) du trigger IdunBattle.Entities.Effects.Loki.InfernalPacts_AdditionalHitsEffect$$CreateAdditionalHits).
                   # #267-r1 : substrat d'ENTITE.
                   "att_traits": _entity_traits(scene, att_id),
                   "is_melee": False})
    _extra_groups = []
    for _g in list(additional_hit_groups(att_effects, _ah_ctx)) + _aura_hits:
        _dp2 = GC.damage_profile(_g["profile"]) or {}
        _gp = max(0, min(100, int(_dp2.get("PiercingRatio") or 0) + ctx.extra_pierce))
        _entry = {"count": _g["count"], "pierce_pct": _gp,
                  "profile_type": _PROFILE_INDEX.get(_g["profile"], 0), "mods": mods,
                  "profile_has_hits_multiple_members":
                      DamageTrait.HitsMultipleMembers.name in (_dp2.get("Traits") or [])}
        if "amount" in _g:
            _entry["amount"] = _g["amount"]
        else:
            _entry["predefined"] = MinMaxDamage(min=_g["min"], max=_g["max"])
        _extra_groups.append(_entry)
    # #267-r1 : MkXGravis lu sur l'ENTITE (`GetBaseDamageWithFixedPiercedArmor` -> HasTrait(defender, 0x3f5)).
    tgt_hit_mult = target_hit_multiplier(TraitFactory.create_many(_entity_traits(scene, tgt_id)))
    res = get_attack_prediction(
        target_current_health=scene.hp(tgt_id) or 0, initial_damage=attack_base, hits=hits,
        profile_type=_PROFILE_INDEX.get(prof_name, 0), pierce_pct=pierce, armor=scene.armor(tgt_id),
        mods=mods, hit_mult=tgt_hit_mult, target_shield=scene.shield(tgt_id),
        target_limits=_target_damage_limits(scene, tgt_id, prof_name),
        target_prevents_overkill=scene.prevents_overkill(tgt_id),   # #195 : HasFlag(cible, 0x13)
        extra_groups=_extra_groups,
        defender_block_amount=defender_prediction_block_amount(scene, tgt_id, prof_name),  # #69 gate NoBlocking
        attacker_effects=att_effects,   # #202 : max-out evalue DANS predict_attack_raw (foyer natif)
        attacker_ctx=ctx)               # #R34 : MightCrit = CouldCrit(attaquant), meme foyer
    ev = ProbableDamageEvent(target=tgt_id, prediction=res)
    if meta:
        return ev, {"mv71": True, "tile": tile_pos, "base": attack_base, "hits": hits,
                    "pierce": pierce, "profile": prof_name}
    return ev


def make_normal_attack_predictions(scene, att_id, tgt_id, attack_pos, *, meta=False):
    """`IdunBattle.AI.Playbook.Loki.ALoki_NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$MakeDamagePredictions` -> `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$PredictAttack` :
    base=Attack × hits + percage + armure + MODIFIER (effets attaquant + ElevationBonus + defenseur).
    Renvoie 1 `ProbableDamageEvent` (l'attaque normale n'est pas AoE) ou None. `meta=True` -> `(event,
    meta_dict)` (base/pierce/armure/hits/mods/effets — diagnostic pour le harnais de validation)."""
    ctx = scene.ctx(att_id)
    if ctx is None:
        return None
    att_effects = scene.effects(att_id)
    t_pos = scene.pos(tgt_id)
    # Selection d'arme melee<->ranged : service PARTAGE `BattleQuery.are_tiles_adjacent` (MEME que le
    # runner combat). ADJACENCE HEX, PAS Chebyshev — une unite a armes mixtes (u92 : melee 4x + ranged
    # 3x Blast) bascule melee UNIQUEMENT sur une tuile hex-adjacente ; les tuiles cheby=1 mais hex=2
    # (ex. (5,5)->(6,6)) restent ranged. `scene.board` (si fourni) = voisins natifs, sinon evenq.
    is_adjacent = are_tiles_adjacent(attack_pos, t_pos, scene.board)
    # --- #61bis tranche 3 : dispatch NormalAttackType CONCRET -> override `MV71SniperDroneSquad-
    # IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$PredictAttack` (1076). Le natif dispatche par vtable (l'attaque normale
    # per-unit EST l'instance MV71 pour un porteur du passif) ; le port dispatche par kit. MELEE
    # (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$IsMeleeAttack`, evaluee sur la POSITION CANDIDATE threadee par la chaine display) ->
    # delegation TOTALE a ALoki.PredictAttack AVEC les modifiers d'origine = on RESTE ici (chemin
    # arme) ; DISTANCE -> chemin drone (config du drone, degat StatAmount(caster), widget mods zeroe).
    if is_adjacent is not True:
        # forme MODULE : is_mv71_normal_attacker est SUBSTITUE (probe_419r1tr14r5) -- lie au
        # chargement, le stub cesserait de mordre en silence (#485-r1-r1).
        # #419-r1-tr14-r5 : la cle de dispatch est `UnitConfiguration.PassiveAbilities` (fait
        # d'ENTITE), pas le kit — cf. `engine.services.custom_normal_attack`.
        if _mv71.is_mv71_normal_attacker(
                scene.vis_by_id.get(att_id),
                passive_abilities=getattr(ctx, "passive_abilities", None),
                active_abilities=getattr(ctx, "active_abilities", None),
                # #419-r1-tr14-r5-r2-r2-r1 : la garde du repli generique lit l'etat PRE-fabrique.
                config_active_abilities=getattr(ctx, "config_active_abilities", None)):
            return _make_mv71_drone_predictions(scene, att_id, tgt_id, attack_pos, meta=meta)
    _dist = hexgeo.distance(attack_pos, t_pos) if (attack_pos and t_pos) else None   # porte portee ranged #188
    # #419-r1-tr14-r1-r1 -- LA BRANCHE SANS ARME. `ALoki_NormalAttackAbility$$PredictAttack` COMMENCE
    # par `weapon = FindAttackWeapon(entities)` (le slot `0xaf` d'`IBattleQuery`, cf.
    # `services.battle_query.get_attack_weapon_for_default_normal_attack`) et BRANCHE sur sa nullite :
    #
    #     weapon = FindAttackWeapon(entities);
    #     if (weapon != null && TryGet<DamageProfile>(GetDamageProfile(weapon.<+0x10>), out profile)) {
    #         ... GetAttackHitPrediction(...) ; AddAdditionalHitsToPrediction(...) ...
    #     } else {
    #         <IBattleQuery slot 0x26>(caster, target, casterPosition, ability, <widgets VIDES>,
    #                                  amount: 0, hits: 1, ...)      // prediction SANS arme
    #     }
    #
    # `FindAttackWeapon` rend `null` des qu'aucune arme n'est utilisable DEPUIS LA TUILE D'ATTAQUE :
    # non adjacent + aucune arme a distance en portee (`FindRangedWeapon` filtre `dist <= Range`, et
    # `SelectMaxRangeWeapon`/`SelectBestDamageWeapon` rendent `null` sur ensemble vide), ou adjacent +
    # aucune arme de melee. Le natif n'a AUCUN repli croise sur cette surcharge.
    # MESURE qui a ouvert le residu (porteur `templNpc1Initiate`, arme `Chain` melee 2 coups) :
    # tuile A adjacente -> natif `732..1098` en 2 coups ; tuile B a 2 hex -> natif **`0..0` en 1 coup**,
    # port `732..1098` en 2. Le `1` coup est LU au decompile : la facade de prediction sans arme passe
    # le litteral `1` en position `hits` (cf. `BattleQuery$$GetAttackPrediction`, argument `1`).
    _w, _ = get_attack_weapon_for_default_normal_attack(
        ctx.visual_id, is_adjacent, prefer_hits=ctx.normal_hits, dist=_dist)
    if _w is None:
        # #506 -- LA BRANCHE SANS ARME PASSE PAR LA MEME FACADE, ET CONTRE LA VRAIE CIBLE.
        # Le natif ne fabrique PAS une struct vide : il appelle le slot `0x26` d'`IBattleQuery`
        # (`GetAttackPrediction`) avec les DEUX listes de modifiers VIDES et les litteraux
        # `amount: 0` / `hits: 1`. Sa `DamagePredictionResult` porte donc `CurrentHealth@0`,
        # `CurrentArmor@4` et `CurrentShield@8` de la cible -- seul le DEGAT est nul.
        #
        # Construire `DamagePredictionResult(applied_hits=1)` laissait `current_health = 0`, et
        # `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill` (borne MIN >= PV
        # courants) rendait alors `0 >= 0` = VRAI : une prediction VIDE se lisait comme un KILL
        # CERTAIN. Deux consequences MESUREES sur `master` (seed 4242 / MC1_67, cible a 7530 PV) :
        #   * `BasePlaybook$$WillNormalAttackKill` rendait VRAI hors portee, donc les 15 playbooks
        #     du gate `#419-r1-tr14-r5-r2-r1-r1-r1` REFUSAIENT leur ability des que l'attaque
        #     normale ne portait pas depuis la tuile de cast (`ultraEliminatorSgt`/1004 sur les
        #     DEUX cibles, `astraPrimarisPsy`/1027 sur une) ;
        #   * `KillUnitUtility` lisait `killSure` et rendait `DefinitelyKill` -- l'utilite MAXIMALE
        #     -- pour une attaque qui n'atteint rien.
        # Le natif, lui, rend `0 >= 7530` = FAUX. Le `hp == 0` reste VRAI des deux cotes (cible
        # morte que `decisionView` conserve), et c'est le comportement deja documente dans
        # `probable_damage_event.composite_fields`.
        res = get_attack_prediction(
            target_current_health=scene.hp(tgt_id) or 0, initial_damage=0, hits=1,
            profile_type=0, armor=scene.armor(tgt_id), target_shield=scene.shield(tgt_id),
            target_prevents_overkill=scene.prevents_overkill(tgt_id),   # #195 : HasFlag(cible, 0x13)
            attacker_ctx=ctx)          # #R34 : MightCrit = CouldCrit(attaquant), ecrit par
                                       # `PredictAttackRaw` que cette voie traverse aussi
        ev = ProbableDamageEvent(target=tgt_id, prediction=res)
        return (ev, {"no_weapon": True, "dist": _dist, "is_adjacent": is_adjacent}) if meta else ev
    pierce, _ranged, whits, prof_name = _weapon_pierce(scene, att_id, is_adjacent, _dist)
    is_melee = not _ranged
    _hm = prediction_has_moved(scene, att_id, attack_pos)
    # PREDICTION (slot 0xd) — branche distincte du combat (runner). Le debuff stat-modifications
    # (IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications, prediction-only) reste GATE off : ce
    # N'EST PAS un modifier post-percage mais un effet AU NIVEAU DE LA BASE (cf. base=Initial ci-dessous).
    # BeastSlayer (target-conditionnel) : traits de la CIBLE (mirror HasTrait) -> gate BigTarget/Vehicle.
    # #267-r1 : substrat d'ENTITE — le natif `BeastSlayer_ExtraDmgEffect$$CreateDamageModifier` gate sur
    # `HasTraitTrigger$$Evaluate` (= `UnitExtensions$$HasTrait`), et le pendant COMBAT
    # (`damage_ops/normal.py`) threade deja `target_traits=target_trait_names(state, target_id)`.
    _tgt_traits = _entity_traits(scene, tgt_id)
    # gate ConquerorImperative (#22, self face) : la CIBLE a-t-elle l'armure REDUITE (>=1 mod <0 sur
    # ARMOR/FIXED_ARMOR) -> +extraDmg FLAT du porteur. OwnerIsCaster TRUE en display (cf. DecoysAndMisdirection).
    _tctx = scene.ctx(tgt_id)
    _tgt_armor_reduced = (_tctx.stats.has_negative_modifier(ARMOR_STAT_TYPES)
                          if _tctx is not None and _tctx.stats is not None else None)
    # att_ctx POSITIONNEL (#29) : magnitude re-countee a la TUILE CANDIDATE pour les bonus dont le DSL lit
    # la UnitPosition hypothetique (LordOfTempests : Count(Ice ring-1) IdunBattle.Entities.Effects.Loki.LordOfTempests_ExtraDamageEffect$$GetHexesIncreasingDamage — meme threading candidat
    # que les auras #153). tile_effects_by_pos = tileMeta FRAIS du pas (la glace s'accumule).
    # gate `IsCharging` (case-r32) : `BattleQuery$$IsCharging(caster, target)` evalue depuis la TUILE
    # CANDIDATE (mirror `UpdateCharging` du pas hypothetique). C'est un predicat DISTINCT de
    # `HasFlag(Moved)` (HeavyWeapon_ExtraDmg, CrushingStrike), que `_hm` porte : les deux existent,
    # ne pas les confondre.
    _att_ctx = {"att_pos": attack_pos or scene.pos(att_id),
                "tile_effects_by_pos": scene.tile_effects_by_pos,
                "is_charging": _prediction_is_charging(scene, att_id, attack_pos, tgt_id),
                # branche `| HasFlag(Self, Teleported)` du gate HeavyWeapon — pendant prediction du
                # threading de `damage_model.attacker_modifiers` (cf. `prediction_has_teleported`).
                "has_teleported": prediction_has_teleported(scene, att_id, attack_pos),
                # `TilesMovedThisTurn(Self)` evalue depuis la TUILE CANDIDATE (case-322) : compteur
                # REEL du tour + tuiles du pas SIMULE (`RecordTilesMoved` est un `+=`, et
                # `MoveUnitOperation$$Execute` l'appelle AUSSI en mode simulation). Consommateur :
                # `ModifiedExoarmour_ExtraDmg` (1544), dont la magnitude EST `extraDmg x ce compte`.
                # PREDICAT DISTINCT de `_hm` (`HasFlag(Moved)`) : un teleport pose `Moved` sans
                # enregistrer la moindre tuile, un `DisplaceUnitOperation` fait l'inverse.
                "tiles_moved_this_turn": prediction_tiles_moved_this_turn(scene, att_id, attack_pos),
                # `GetNumAdjacentTauntedEnemies()` (#911) evalue pour l'ATTAQUANT, qui EST le
                # porteur de `DaemonicPatrons_ExtraDamage` (1464, gate `get_OwnerIsCaster`).
                # ⚠ EVALUE A LA POSITION COURANTE, pas a la TUILE CANDIDATE -- contraste ASSUME avec
                # `tiles_moved_this_turn` juste au-dessus : `Scene.adjacent_taunted_enemies` lit
                # `pos_by_id`, donc un plan qui DEPLACE Hascule hors du contact predit encore le
                # bonus. Residu NOMME dans `docs/rl/case-911-daemonic-patrons.md` ; la face COMBAT,
                # elle, mesure la position REELLE au moment du coup.
                _CTX_ADJACENT_TAUNTED_ENEMIES: scene.adjacent_taunted_enemies(att_id),
                # `PsychicStalk_FriendlyChaosExtraDamage` (#366-r1, effet 1435) -- PATTE SELF du
                # slot `CreateEffectDamageBonusForAttack` : gates `HasTrait(Caster@0x48, Chaos)`,
                # `EntitiesWithAnyEffect(Tiles(Target@0x60), Fire)` (la MAIN TILE de la cible,
                # deja couverte par le `tile_effects_by_pos` PLATEAU-ENTIER ci-dessus) et
                # `DamageProfileIs([Flame, Psychic])`. MEMES CLES que le ctx du canal AURA
                # (`_apply_ally_attack_dmg_bonus`) et que la face COMBAT -- pas de fork.
                # `att_gu` = le KIT (GrandAllianceId est une donnee de CONFIGURATION, comme dans
                # `_apply_ally_attack_dmg_bonus`).
                "att_grand_alliance": (GC.unit(scene.vis_by_id.get(att_id)) or {}).get("GrandAllianceId"),
                "damage_profile": prof_name,
                "t_pos": t_pos,
                "tgt_team": scene.team(tgt_id),
                # #1025-r1 -- `HasRarity(Target@<DSLSelectors+0x60>, idun.meta.Rarity.Mythic = 5)` et
                # `AreFriends(Target@<DSLSelectors+0x60>, EffectSource(Effect@<DSLSelectors+0x38>))`,
                # les DEUX conjoints utiles d'`ElectrochaffBackups_DamageReductionPct` (1446). La
                # rarete porte sur le DEFENSEUR (symetrique de l'`attacker_ctx["rarity"]` du canal
                # DEFENSE, qui porte sur le caster) ; `team_by_id` resout la SOURCE de l'effet, qui
                # n'est ni l'attaquant ni la cible. MEMES cles et MEME semantique que la face COMBAT
                # (`damage_model.attacker_modifiers`) -- elargir un seul cote recreerait le fork.
                # TRI-ETAT sur la rarete (`None` = non mesure -> gate FERME), cf. `_entity_rarity`.
                "tgt_rarity": _entity_rarity(scene, tgt_id),
                "team_by_id": scene.team_by_id,
                # `HealthPctIsBelowOrEqual(Target@0x60, ConfigConst(0x4f))` -- gate de DOUBLEMENT de
                # `LightOfSanguinius_DamageReductionEffect$$CreateDamageModifier` (#510), qui porte
                # sur les PV de la CIBLE DU COUP. MEMES cles que la face COMBAT
                # (`damage_model.attacker_modifiers`) -- pas de fork.
                "tgt_hp": scene.hp(tgt_id),
                "tgt_hp_max": scene.hpmax(tgt_id),
                # `Target@DSLSelectors+0x60` lu en IDENTITE, pas en position : le gate
                # `AreEqual(Target@0x60, BondedEntityFromEffect(Effect@0x38))` de
                # `IdunBattle.Entities.Effects.Loki.HolyDuel_ExtraDmgEffect$$
                # CreateEffectDamageBonusForAttack` (1092) compare deux ENTITES. Le contexte portait
                # deja ce meme noeud sous trois autres lectures (`t_pos`, `tgt_team`, `tgt_hp`) ; il
                # lui manquait l'id. MEME cle et MEME semantique que la face COMBAT
                # (`damage_model.attacker_modifiers`) et que le canal AURA -- pas de fork.
                "tgt_id": tgt_id,
                # #919 -- `StatAmount(Owner@DSLSelectors+0x30, BlockDamage, Current)` de
                # `IconOfObstinacy_ExtraDamageEffect$$GetCurrentExtraDamage`, PATTE SELF : sur ce
                # canal l'OWNER de chaque effet parcouru EST l'attaquant (la boucle n'itere que SES
                # effets), exactement comme `tiles_moved_this_turn` / `adjacent_taunted_enemies`
                # au-dessus. MEME cle et MEME semantique que la face COMBAT
                # (`damage_model.attacker_modifiers`) et que le canal AURA -- pas de fork.
                "owner_block_damage": prediction_block_damage(scene, att_id),
                # #932 -- les TROIS noeuds de `IdunBattle.Entities.Effects.Loki.DeathwingEffect$$
                # GetDoubleEffectCondition` sur la face ATTAQUE (`isDefense: false`), ou l'entite
                # comparee est la CIBLE et l'Owner est l'ATTAQUANT :
                #   `HasTrait(Target@+0x60, 0x7ea = Chaos)`   -> `tgt_grand_alliance` ;
                #   `AreEnemies(Target@+0x60, Owner@+0x30)`   -> `tgt_team` (deja pose) + `att_team` ;
                #   `AmountIsGreaterThanZero(UnitsFromFaction(AdjacentFriends(Owner), DarkAngels))`
                #                                             -> `adjacent_dark_angels_friends`.
                # MEMES cles et MEME semantique que la face COMBAT (`damage_model.attacker_
                # modifiers`) -- elargir un seul cote recreerait le fork prediction/combat.
                # `att_gu` = le KIT (`GrandAllianceId` est une donnee de CONFIGURATION).
                "tgt_grand_alliance": (GC.unit(scene.vis_by_id.get(tgt_id)) or {}).get("GrandAllianceId"),
                "att_team": scene.team(att_id),
                _CTX_ADJACENT_DARK_ANGELS_FRIENDS: scene.adjacent_dark_angels_friends(att_id),
                # #948 -- les DEUX compteurs d'`EnmityForTheUnworthy` (`darkaCompanion` << Forcas >>),
                # PATTE SELF comme les cles ci-dessus (l'OWNER de chaque effet parcouru EST
                # l'attaquant, ce qu'exige leur `get_OwnerIsCaster`). MEMES cles et MEME semantique
                # que la face COMBAT (`damage_model.attacker_modifiers`).
                # ⚠ DISTINCTS d'`adjacent_dark_angels_friends` juste au-dessus : l'arbre d'Enmity
                # porte en plus l'etage `NonSteppableOrObjectUnits`, et sa face Pct ne filtre NI
                # l'equipe NI la faction.
                # ⚠ #948-r1 -- EVALUES A LA TUILE CANDIDATE, comme `tiles_moved_this_turn` et
                # `is_charging` au-dessus, et PAS a la position courante comme leurs deux voisins
                # `adjacent_taunted_enemies` / `adjacent_dark_angels_friends`. Ce n'est pas une
                # divergence de traitement mais une LECTURE : `IdunBattle.Operations.
                # SimulateEffectsOperation$$DoActionInSimulatedTile` DEPLACE reellement l'unite
                # (slot du processor + `SimulateMoveUnitTriggers` + `RefreshSimulatedEffects`)
                # AVANT d'invoquer l'action de prediction, puis restaure. `AdjacentUnits(Owner)`
                # descend sur `EntityExtensions$$IterateTiles(owner)`, donc sur la tuile ou
                # l'entite a ete posee. Les deux voisins relevent du MEME gisement, non ferme.
                _ENMITY_CTX_UNITS: scene.enmity_adjacent_units(att_id, attack_pos),
                _ENMITY_CTX_DA: scene.enmity_adjacent_dark_angels_friends(att_id, attack_pos),
                # #1078-r3 -- `Count(UnitsWithTrait(AdjacentFriends(Owner), Psyker))` de
                # `HunterOfSouls_ExtraDamageEffect$$GetUnits`. MEME cle, MEME semantique et MEME
                # tuile candidate que les deux voisins ci-dessus ; c'est ce qui empeche le fork
                # entre les deux faces (la face COMBAT la pose dans `runner/damage_model.py`).
                _HUNTER_CTX_PSYKER:
                    scene.hunter_of_souls_adjacent_psyker_friends(att_id, attack_pos),
                # #953 -- `StatAmount(Owner@DSLSelectors+0x30, Health, {Missing, Maximum})` de
                # `Skullsmasher_ExtraDamageEffect$$GetMissingHealthSteps`, PATTE SELF comme les cles
                # ci-dessus (l'OWNER de chaque effet parcouru EST l'attaquant, ce qu'exige son
                # `get_OwnerIsCaster`). MEME couple et MEME substrat que la face COMBAT
                # (`damage_model.attacker_modifiers`, `HealthComponent`) : `scene.hp`/`scene.hpmax`
                # sont alimentes par le MEME `HealthComponent`. Tri-etat `(None, None)` conserve.
                _SKULLSMASHER_CTX_HEALTH: (scene.hp(att_id), scene.hpmax(att_id)),
                # #1015-r1 -- `HasAdjacentEnemies(Caster@+0x48, CasterTile@+0x50, includeObjects:
                # false, includeSteppables: false)`, le terme GEOMETRIQUE de
                # `CloseCombatWeakness_ReduceDmg_Effect$$NearbyEnemiesCondition`. PATTE SELF comme
                # les cles ci-dessus (l'OWNER de chaque effet parcouru EST l'attaquant, et le
                # `Caster` du noeud designe cette meme unite). EVALUE A LA TUILE CANDIDATE, comme
                # les deux cles `_ENMITY_CTX_*` (#948-r1) : `CasterTile` suit l'unite deplacee par
                # `SimulateEffectsOperation$$DoActionInSimulatedTile`. MEME cle et MEME semantique
                # que la face COMBAT (`damage_model.attacker_modifiers`).
                _CCW_CTX_ADJACENT_ENEMIES: scene.close_combat_weakness_adjacent_enemies(
                    att_id, attack_pos)}
    mods = calculate_attacker_modifiers_for_prediction(att_effects, is_ranged=_ranged, has_moved=_hm,
                                                       target_traits=_tgt_traits,
                                                       target_armor_reduced=_tgt_armor_reduced,
                                                       att_ctx=_att_ctx)
    # #49/#153/#57a : base display re-positionnee a la tuile candidate — foyer PARTAGE `_display_
    # attack_base` (aussi consomme par le chemin drone MV71, #61bis tranche 3 : delegue b__1 = la
    # meme lecture native StatAmount(Caster, ATTACK, CURRENT)).
    attack_base, carriers, att_grand, att_faction, _ap = _display_attack_base(
        scene, att_id, attack_pos, is_melee)
    _add_positional_and_defender_mods(mods, scene, att_id, tgt_id, is_melee, attack_pos, t_pos,
                                      damage_profile=prof_name)
    # AURA ENNEMIE %-degat projetee sur l'ATTAQUANT : ShadowInTheWarp_LessDmg_Effect (-25% Psychic aux
    # ennemis a portee du porteur) — reutilise `carriers` (toutes les autres unites vivantes), gate Psychic
    # + team ennemie + portee dans le create_aura_. Ajoute aux modifiers %-list de l'attaquant.
    for _eb in aura_attack_damage_malus_from_enemies(
            carriers, {"att_id": att_id, "att_pos": _ap, "att_team": scene.team(att_id),
                       "damage_profile": prof_name}):
        add_modifier(mods, _eb)
    # AURA ALLIEE FLAT-degat projetee sur l'ATTAQUANT (canal cote SOURCE) : BeaconOfRage_FriendlyExtraDamage
    # (+50% rage aux amis Chaos adjacents en melee, #191) + ConquerorImperative (+extraDmg aux amis Mechanical
    # ring-1 vs cible a armure reduite, #23). Reutilise `carriers` (8-tuple) ; gates (is_melee/grande-alliance ;
    # Mechanical/target_armor_reduced) dans le create_aura_. Additif -> mods.additive (meme canal que le self,
    # deja bit-exact). NB : le self (le porteur attaque) et l'aura (un ami attaque) portent sur des ATTAQUANTS
    # distincts -> jamais cumules.
    _apply_ally_attack_dmg_bonus(mods, scene, att_id, _ap, is_melee, _tgt_armor_reduced, carriers,
                                 tgt_id=tgt_id, is_normal_attack=True, damage_profile=prof_name)
    # Nb de coups : cette prediction EST la facade `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` — elle
    # rassemble les entrees depuis la Scene puis appelle la FORMULE PARTAGEE `attack_hits_with_modifiers`
    # (`IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate`, MEME formule que la facade combat runner) :
    # base weapon+ExtraHits+effets, +GetStuckIn/traits, +malus defenseur (LightCover/Parry) + auras (BigTarget).
    # VIVANTS SEULEMENT (#57m) : le board natif = OCCUPATION DE TUILE (`IdunBattleLogic.Entities.DSLFactory$$AdjacentUnits` =
    # `Units(AdjacentTiles(.)) - .`) — les cadavres de scene.pos_by_id (decisionView les garde) n'y
    # sont plus : ni compte GetStuckIn (IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$GetBonusHitChance), ni porteur d'aura (idiome hp>0, cf. l.227/276).
    _alive_ids = [uid for uid in scene.pos_by_id
                  if uid in (att_id, tgt_id) or (scene.hp(uid) or 0) > 0]
    # #1073 -- `{team: ((col, row), ...)}` des unites VIVANTES portant le trait `Synapse`, substrat
    # d'`IsInTeamSynapseRange`. Pendant EXACT de `runner/damage_model.py::_team_synapse_positions`
    # (MEME critere : trait lu sur le substrat d'ENTITE, unites vivantes, position courante), monte
    # ICI parce que le trait n'est lisible que par `_entity_traits`, que `Scene` n'importe pas.
    _synapse_by_team: dict = {}
    for _uid in _alive_ids:
        if _SYNAPSE_TRAIT not in _entity_traits(scene, _uid):
            continue
        _p, _t = scene.pos(_uid), scene.team(_uid)
        if _p is not None and _t is not None:
            _synapse_by_team.setdefault(_t, []).append(tuple(_p))
    board = {"att_id": att_id, "tgt_id": tgt_id, "attack_pos": attack_pos, "t_pos": t_pos,
             "tgt_team": scene.team(tgt_id), "is_melee": is_melee,
             "pos_by_id": {uid: scene.pos_by_id[uid] for uid in _alive_ids},
             "team_by_id": scene.team_by_id,
             # faction par unite — gate GetBonusHitChance de GetStuckIn (orks_adj>=2, IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$GetBonusHitChance, #98)
             "faction_by_id": {uid: scene.faction(uid) for uid in _alive_ids},
             # `vid_by_id` (#1018) = l'id d'unite que `IdunBattle.Entities.UnitExtensions$$HasUnitId`
             # compare, donc le substrat du noeud `IdunBattleLogic.Entities.DSLSelectors$$UnitsWithIds`.
             # PENDANT EXACT du board COMBAT (`runner/damage_model.py::build_hits_board`), sur les
             # MEMES unites vivantes. Consommateur : `HungeringSwarm_ExtraHits` (1041).
             "vid_by_id": {uid: (scene.vis_by_id or {}).get(uid) for uid in _alive_ids},
             # SANTE (#1018) -- sans elle `engine/dsl/base.py::_is_alive` classe l'unite MORTE
             # (degradation NOMMEE << `hpMax` ABSENT du dict -> MORT >>) et tout selecteur
             # d'occupation rend l'ensemble VIDE. Meme source que `_alive_ids` ci-dessus.
             "hp_by_id": {uid: scene.hp(uid) for uid in _alive_ids},
             "hpmax_by_id": {uid: scene.hpmax(uid) for uid in _alive_ids},
             # `IsCharging` (case-ischarging-hits) sur le canal COUPS — MEME valeur que celle deja calculee pour
             # le canal DEGAT (`_att_ctx` ci-dessus) : un seul appel a `_prediction_is_charging` par
             # candidat, donc un seul mirror d'`UpdateCharging` sur la tuile evaluee. Consommateur :
             # `SagaOfTheWarriorBorn_Owner` (1223, +extraHits en charge).
             "is_charging": _att_ctx["is_charging"],
             # #372 — substrat du canal AURA de COUPS (`aura_hits_bonus_for_attack`), consommateur
             # `DefenderOfTheGreaterGood_ExtraHits` (1183 / 1307). Pendant EXACT du board COMBAT
             # (`runner/damage_model.py::build_hits_board`) :
             #  * `att_faction` = le tier T'au range-2 du selecteur
             #    `DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector` — MEME valeur que
             #    celle deja calculee pour le canal DEGAT (`_display_attack_base`), pas un 2e read ;
             #  * `turns_started_by_id` = `UnitTurnsStarted` = `GetStat(., 0xc)`, deja capte par la
             #    Scene (#46) ;
             #  * PAS de `rng` : cote PREDICTION `ANonDeterministicAbilityTrigger$$CanUseRandom` est
             #    FAUX, et `MaybeTrigger$$ShouldTrigger` y substitue `99 < chance` au tirage. L'absence
             #    de cle EST le mirror (cf. `entities.triggers.MaybeTrigger`, `rng is None`) ;
             #  * `parent_by_id` (#378) = le noeud `Parent(EffectSource)` du meme `If`. Le lien est
             #    desormais LU (`ChildComponent.ParentId` -> `combatSnapshot.units[].parentId` ->
             #    `Scene.parent_by_id`) la ou il etait OMIS : le jumeau DRONE lisait SES tours au
             #    lieu de ceux de son summoner, donc sa chance etait SOUS-ESTIMEE (residu nomme de
             #    #372). Table vide = capteur anterieur a #378 -> `pid is None` -> le noeud retombe
             #    sur la source, exactement le comportement d'avant.
             "att_faction": att_faction,
             # `HasTrait(Caster@DSLSelectors+0x48, …)` sur le canal COUPS. MEME cle, MEME resolveur
             # et MEME semantique que le `att_traits` deja pose par le canal DEGAT juste au-dessus et
             # par le board COMBAT (`runner/damage_model.py::build_hits_board`) : pas de fork.
             # Consommateur : `TerrorsLament_HitReduction`, dont le trigger porte
             # `NOT HasTrait(Caster, 0x19 = UnitTrait.Immune)` -- le SEUL conjoint qui separe sa
             # moitie COUPS de sa moitie DEGAT.
             "att_traits": _entity_traits(scene, att_id),
             "turns_started_by_id": scene.turns_started_by_id,
             "parent_by_id": scene.parent_by_id,
             # `HasFlag(Self, Moved)` sur le canal COUPS (case-366-r1) -- MEME valeur `_hm` que
             # celle deja calculee pour le canal DEGAT ci-dessus (`prediction_has_moved` : flag ECS
             # OU tuile candidate != tuile courante), pas un 2e read. Consommateur :
             # `InescapableAccuracy_overrideHits` (1117).
             "has_moved": _hm,
             # #1073 -- les DEUX disjoints de `SynapticInsight_ExtraHitsEffect$$
             # CreateEffectHitsBonusForAttack`. Pendant EXACT du board COMBAT
             # (`runner/damage_model.py::build_hits_board`), MEMES cles, MEME semantique :
             #  * `Any(AdjacentFriends(Owner@+0x30, Target@+0x60, unique), HasFaction(It@+0x68,
             #    Tyranids, 3))` -- recompose depuis les tables de `Scene` (elle n'a pas
             #    d'`AbilityEntities` pour executer l'arbre), MEME cablage d'adjacence que ses deux
             #    voisins `adjacent_taunted_enemies` / `adjacent_dark_angels_friends`. TRI-ETAT.
             #  * `IsInTeamSynapseRange(Target@+0x60, Owner@+0x30)` -- la POSITION des emetteurs
             #    `Synapse` par equipe ; la comparaison de distance reste chez le consommateur
             #    (`norn_crown._in_team_synapse_range`, foyer UNIQUE, #1011). Les traits viennent du
             #    substrat d'ENTITE (`_entity_traits`), jamais du kit gameconfig.
             #  ⚠ Ces deux cles n'entrent QUE dans le board COUPS : le ctx du canal DEGAT de la
             #    prediction ne les porte pas, et `NornCrownEffect` (canal DEGAT) reste donc
             #    exactement dans l'etat ou #1011 l'a laisse.
             _SI_CTX_ADJACENT_TYRANID: scene.synaptic_insight_adjacent_tyranid(att_id, tgt_id),
             _NORN_CTX_SYNAPSE: {t: tuple(ps) for t, ps in _synapse_by_team.items()}}
    tgt_effects = scene.effects(tgt_id)
    aura_sources = [(uid, scene.pos(uid), scene.team(uid), scene.effects(uid))
                    for uid in _alive_ids if uid != tgt_id]
    # #57a : EXTRA_HITS DU PAS (scene, refresh par-pas) et non le cold ctx — les stat-mods hits
    # dynamiques (Swarm_HitReduction : -1 hit/membre perdu) sont poses APRES l'hydratation.
    _xh = scene.extra_hits_current(att_id)
    # #62 : gates/branches TUILE compute-time des malus defenseur — le natif les evalue AUSSI en
    # prediction (formule PARTAGEE IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate) : LightCover `AreEqual(coverPatch, target)` IdunBattle.Entities.Effects.Loki.LightCoverEffect$$CreateEffectHitsBonusForAttack,
    # Camouflage branche -3 `HasTile(TilesWithTriggeredAbility(Tiles(Target), 57))` IdunBattleLogic.Entities.Abilities.Triggered.Loki.Camouflage_HitReductionEffect$$CreateEffectHitsBonusForAttack. Terrain
    # de la CIBLE (immobile : seule la tuile candidate de l'attaquant varie) via scene.board (#124),
    # mirror du call-site combat (operations/damage.py). Board KO -> None = applique-sur-presence.
    _t_terrain = scene.board.terrain_at(t_pos[0], t_pos[1]) if scene.board is not None else None
    _on_cover = (_t_terrain == LIGHT_COVER_TILE_ID) if _t_terrain is not None else None
    # #419-r1-tr9-r4 : les arguments de la facade de COUPS sont montes UNE fois et reutilises tels
    # quels par le fold `GetAdditionalDamagePrediction` (avec `weapon_hits = nrOfHits`). Le natif
    # rappelle le MEME `GetAttackHits` avec le MEME couple (caster, cible) et ne change que la base
    # d'arme : partager le dict est ce qui garantit qu'aucun canal ne diverge entre les deux etages.
    _hits_kw = dict(extra_hits=_xh if _xh is not None else ctx.stat(StatType.EXTRA_HITS),
                    extra_hits_melee=ctx.extra_hits_melee,
                    attacker_effects=att_effects, trait_objects=ctx.trait_objects(),
                    target_effects=tgt_effects, aura_sources=aura_sources, board=board,
                    is_melee=is_melee, damage_profile=prof_name,
                    include_bonus_hit_behaviours=True,  # prediction folde GetStuckIn (deterministe)
                    # #227 : `LetTheGalaxyBurn` a QUITTE cette formule (son
                    # artefact natif est un descripteur `EffectAdditionalHits`,
                    # canal #179). Cote PREDICTION il ne contribue RIEN :
                    # `IdunBattle.Entities.Abilities.AActiveAbility$$GetAdditional
                    # HitsFromEffectsForPrediction` tourne hors `OngoingAttack`,
                    # donc `FirstHitInCurrentAttackDamageRange` rend 0 -> coup a
                    # 0 degat. Cf. `LetTheGalaxyBurnEffect`.
                    defender_on_cover=_on_cover)
    hits = attack_hits_with_modifiers(weapon_hits=whits, **_hits_kw)
    # MkXGravis (trait CIBLE 0x3f5) : l'armure est traversee 2× → hit_mult=2 dans predict_attack_raw
    # (IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor). No-op (=1) pour toute cible sans trait hit-twice.
    tgt_hit_mult = target_hit_multiplier(TraitFactory.create_many(_tgt_traits))
    # #179 : coups additionnels HETEROGENES (SquigHound_AdditionalHits) — degat/profil PROPRE, prev-threades
    # APRES les coups d'arme (overkill continu). Chaine native (RE) : `AActiveAbility.AddAdditionalHitsTo-
    # Prediction IdunBattle.Entities.Abilities.AActiveAbility$$AddAdditionalHitsToPrediction` -> par coup `get_DefaultBlockScenario(result)` (prev threade) puis `GetEffect-
    # AdditionalHitPrediction IdunBattle.Entities.Abilities.AActiveAbility$$GetEffectAdditionalHitPrediction` -> le MEME delegate PredictAttack (slot 0x26) / `PredictAttackRaw
    # IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` que les coups d'arme, avec le CONTEXTE MODIFIERS COURANT. Donc chaque groupe : `count` coups
    # [min,max] (predefined, sans spread ±20% = RandomAmount natif) au profil propre (pierce = PiercingRatio du
    # profil + extra_pierce), MEME armure/hp/bouclier/hit_mult(MkXGravis) que la cible, ET `mods` COMPLET — le
    # coup subit le meme pipeline : reductions defenseur plates (Nightshroud_DmgReduction, fusionnees dans
    # mods.additive) + %-mods/additif attaquant. Mirror `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create`. [] hors carrier.
    # #57c-C : deux sources de groupes — (a) effets du PORTEUR (SquigHound/CordClaw/FoulInfusion,
    # triggers OwnerIsActor/OwnerIsCaster+IsMeleeAttack EVALUES : ctx is_melee threade) ; (b) effets-
    # AURA d'ALLIES adjacents (ExplosiveMaladies : adjacence re-evaluee a la TUILE CANDIDATE, mirror
    # de l'enumeration globale IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsFromEffectsInternal + selecteur IdunBattle.Entities.Effects.Loki.ExplosiveMaladies_ExtraRangedAttackEffect$$CreateTargetSelector). Les groupes "amount" (ConfigVar
    # seul) prennent le spread ±20% du pipeline ; TOUS les groupes recoivent les %-mods attaquant
    # (mesure 2468 s14 : le coup ExplosiveMaladies de u89 subit bien le x1.5 CrushingStrike).
    _extra_groups = []
    # #57e : gates CIBLE des descripteurs additional-hits (ex. CyclicIonBlaster ConditionalAmount
    # HasEffect(target, Markerlight) | HasTrait(target, Mechanical)) — traits gameconfig + noms
    # d'effets ACTIFS de la cible threades dans le ctx du canal #179.
    # #267-r1 : traits de la CIBLE = substrat d'ENTITE — MEME source que le `tgt_traits` du canal #179
    # cote COMBAT (`runner/operations/additional_hits.py` : `target_trait_names(state, target_id)`).
    _ah_ctx = {"is_melee": is_melee,
               "tgt_traits": _entity_traits(scene, tgt_id),
               _CTX_TGT_EFFECT_NAMES: frozenset(
                   n for n in (getattr(_e, "name", None) for _e in (scene.effects(tgt_id) or [])) if n),
               # #419-r1-tr11-r3 : les DEUX positions, sans lesquelles un gate `IsAtRange` du canal
               # #179 est inevaluable (`SpecialIssueCombiMelta_AdditionalHits` 1563, d == 2).
               # `att_pos` = la tuile CANDIDATE evaluee (`attack_pos`), MEME substrat que
               # `_att_ctx["att_pos"]` juste au-dessus : le `Caster@DSLSelectors+0x48` d'une
               # prediction est resolu contre la `UnitPosition` candidate threadee par la chaine
               # display, pas contre la position courante. Pas de fork entre les deux ctx.
               "att_pos": _att_ctx["att_pos"], "t_pos": t_pos,
               # #1065 -- les TROIS conjoints du trigger de `FragLanceEffect$$CreateAdditionalHits`,
               # pendant EXACT du cablage COMBAT (`runner/operations/additional_hits.py`) :
               #  * `owner_id`/`att_id` = `get_OwnerIsCaster`. Sur CETTE branche l'enumeration est
               #    deja restreinte a `att_effects` (les effets de l'attaquant), donc le porteur EST
               #    le caster -- meme raisonnement, meme paire de cles que la face COMBAT ;
               #  * `is_normal_attack` = `IsNormalAttack`. Cette facade EST la prediction de
               #    l'attaque NORMALE -> VRAI par construction ;
               #  * `is_charging` = la valeur DEJA calculee pour le canal DEGAT (`_att_ctx`), qui
               #    porte les DEUX termes (charge ACQUISE et pas CANDIDAT) -- un seul appel a
               #    `_prediction_is_charging` par prediction, exactement comme `att_hits_ctx`.
               "owner_id": att_id, "att_id": att_id, "is_normal_attack": True,
               "is_charging": _att_ctx["is_charging"]}
    _aura_hits = aura_additional_hits_from_allies(
        carriers, {"att_id": att_id, "att_pos": _ap, "att_team": scene.team(att_id),
                   "att_faction": att_faction, "att_grand_alliance": att_grand,
                   # #202-B : traits de l'ATTAQUANT (gate Daemon d'InfernalPacts — disjunct
                   # HasTrait(0x3fb) du trigger IdunBattle.Entities.Effects.Loki.InfernalPacts_AdditionalHitsEffect$$CreateAdditionalHits).
                   # #267-r1 : substrat d'ENTITE.
                   "att_traits": _entity_traits(scene, att_id),
                   "is_melee": is_melee})
    for _g in list(additional_hit_groups(att_effects, _ah_ctx)) + _aura_hits:
        _dp = GC.damage_profile(_g["profile"]) or {}
        _gp = max(0, min(100, int(_dp.get("PiercingRatio") or 0) + ctx.extra_pierce))
        _entry = {"count": _g["count"], "pierce_pct": _gp,
                  "profile_type": _PROFILE_INDEX.get(_g["profile"], 0), "mods": mods,
                  # #57d : le member-cap Swarm lit le profil DU COUP (param_5 d'IdunBattle.Core.Services.DamagePrediction$$ApplyGroupUnitDamageLimit) — un coup
                  # additionnel Blast (HitsMultipleMembers) skippe le cap meme si l'arme ne le fait pas.
                  "profile_has_hits_multiple_members":
                      DamageTrait.HitsMultipleMembers.name in (_dp.get("Traits") or [])}
        if "amount" in _g:
            # #65 : PAS de troncature int — un amount midpoint (Average natif, ex. FleshmetalGuns)
            # peut valoir x.5 ; le spread Fix64 (`calculate_damage_spread` from_number) le gere exact.
            _entry["amount"] = _g["amount"]
        else:
            _entry["predefined"] = MinMaxDamage(min=_g["min"], max=_g["max"])
        _extra_groups.append(_entry)
    res = get_attack_prediction(
        target_current_health=scene.hp(tgt_id) or 0, initial_damage=attack_base, hits=hits,
        profile_type=0, pierce_pct=pierce, armor=scene.armor(tgt_id), mods=mods, hit_mult=tgt_hit_mult,
        target_shield=scene.shield(tgt_id), target_limits=_target_damage_limits(scene, tgt_id, prof_name),
        extra_groups=_extra_groups,
        defender_block_amount=defender_prediction_block_amount(scene, tgt_id, prof_name),  # #69 gate NoBlocking
        attacker_effects=att_effects,   # #202 : max-out evalue DANS predict_attack_raw (foyer natif)
        attacker_ctx=ctx)               # #R34 : MightCrit = CouldCrit(attaquant), meme foyer
    # #57c-C : override PredictAttack des attaques normales de boss (Gulgortz/LightImUp, Ghazghkull/
    # ProperKilly) — prediction ADDITIONNELLE sur scenario VIERGE sommee via DamagePredictionResult.add
    # (IdunBattle.Core.Services.DamagePredictionResult$$Add), cf. bloc _RANGED_FOLLOWUP_PASSIVES ci-dessus.
    _fw = _normal_attack_followup_prediction(scene, att_id, tgt_id, is_melee,
                                             prof_name is not None, mods=mods, hits_ctx=_hits_kw)
    if _fw is not None:
        res.add(_fw)
    ev = ProbableDamageEvent(target=tgt_id, prediction=res)
    if meta:
        _m = {"base": attack_base, "pierce": pierce, "armor": scene.armor(tgt_id), "hits": hits,
              "mods": [round(m, 3) for m, _c in mods.pct_list] or None,
              # #446-r2 : QUELLE feuille produit chaque entree de la %-list. Sans ce detail, deux
              # sources distinctes de meme facteur (elevation vs modification de stat DEFENSE, toutes
              # deux x1.5) sont indiscernables -- et elles n'atterrissent PAS dans le meme champ natif.
              "mods_detail": [(e.kind, e.value, bool(e.owner_is_caster)) for e in mods.details] or None,
              "mods_def": [round(m, 3) for m, _c in mods.pct_list_defender] or None,
              # #462-r4a : le canal `Multiplier@0x30` des DEUX faces. Il est DISTINCT des %-list
              # ci-dessus (elles se composent sans arrondi entre elles, lui est precede d'un
              # `Fix64.Round`), et seules les MODIFICATIONS DE STAT y entrent. Sans ces deux cles,
              # un diagnostic qui ne lit que `mods`/`mods_def` rend une chaine AMPUTEE du x1.5 d'une
              # tuile Thorns -- exactement le faux signal que le rejeu de #446-r2 a exhibe.
              "mult_att": round(mods.multiplicative, 6) if mods.multiplicative != 1.0 else None,
              "mult_def": (round(mods.multiplicative_defender, 6)
                           if mods.multiplicative_defender != 1.0 else None),
              "effects": [e.name for e in att_effects] or None}
        if _fw is not None:
            # `hits` = le retour de la facade `GetAttackHits` pour le fold (#419-r1-tr9-r4) : sans
            # lui, un ecart de COMPTE DE COUPS du fold ne se distingue pas d'un ecart de montant.
            _m["followup"] = {"min": _fw.raw_health_damage.min, "max": _fw.raw_health_damage.max,
                              "hits": _fw.applied_hits}
        return ev, _m
    return ev
