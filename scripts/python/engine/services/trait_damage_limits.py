"""Port FIDÈLE de `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage
et de ses 5 sous-limites (gqfc5mff6c). Chaque fonction = sa jumelle native (même nom homonyme, VA citée).

CONTEXTE (RE) : dans `PredictAttackRaw`, le rawMM per-coup (après perçage/armure/modifiers, =
`CalculateBaseDamageWithAllModifiers`) est passé à **`ApplyTraitDamageLimitsToDamage` @IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x2a17**
qui le MODIFIE IN-PLACE **avant** la boucle multi-coups. Le port historique (`damage_prediction.py`)
SAUTAIT entièrement cette étape → trou. Ces limites sont surtout no-op pour un héros nu, mais comptent
pour : cibles multi-membres (member-cap), trait Resilient (1009), trait Impervious (28), boss
(BossEndFightUndefeated 1492).

⚠ Le dégât est un int (borne min ou max), traité séparément (le natif appelle chaque Apply 2× : une
fois sur *param_3=min, une fois sur *param_4=max). Ici on opère sur UNE borne (int) ; l'appelant boucle.

`UnitTrait.TwoManTeam` (0x3fa=1018) — RIEN À PORTER, le trait est un TAG DE TOOLTIP (#75). Preuve RE :
`HasTrait(x, 0x3fa)` n'existe NULLE PART dans le binaire (les 7 occurrences de `,0x3fa,` sont
ValkyrieStrike/ActOfFaith = `ActiveAbilityType` 1018, homonyme d'id). Le tooltip (« max 50% des PV max
d'un seul coup, hors Blast ; sous 50%, plus soignable au-dessus de 50% ») décrit EXACTEMENT le
comportement GROUP-UNIT à `nrOfMembers == 2`, keyé sur le NOMBRE DE MEMBRES : cap par-coup =
`apply_group_unit_damage_limit` (= 1 membre = 50% de maxHP à 2 membres), exclusion Blast = le
early-return `DamageTrait.HitsMultipleMembers` (seul le profil Blast le porte), plafond de soin =
`get_group_unit_heal_limit`/`is_at_group_unit_heal_limit`. Les 6 porteurs du trait ont TOUS
`nrOfMembers == 2`. Identité verrouillée par `tests/engine/test_two_man_team_group_cap.py`.

⚠ L'argument « pas de `HasTrait(0x3fa)` » est INSUFFISANT SEUL — `Diminutive` (0x408) n'est lui non plus
JAMAIS lu par `HasTrait` : il passe par le dict trait→ability dérivée. Le chemin manquant a été fermé
(validation adversariale #87) : dans `StaticBattleRules.Trait..idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor`, `0x3fa` n'est clé
d'AUCUN des 7 conteneurs (ni `GetTriggeredAbility`, ni `GetEffectToBeAddedToOwnerForTrait` — clés
0x41e/0x3e9/0x41f/0x424 —, ni les OrderedSets) ; il n'y apparaît qu'en VALEUR de la clé 0x3ef
(trait 1007 → triggered 1018). ⇒ ni ability dérivée, ni owner-effect. Ghidra écrivant les constantes
tantôt en hexa tantôt en décimal, la recherche `,1018,` a aussi été faite : 0 occurrence.

⚠ AUCUN cas discriminant n'existe LIVE : sur les 17 unités multi-membres du jeu, les 6 à `nrOfMembers == 2`
sont EXACTEMENT les 6 porteurs du trait ; les 11 autres (Swarm/Nurglings/Ripper) ont 4-5 membres et n'ont
PAS le trait. Le live ne pourrait donc jamais départager « cap dû aux membres » de « cap dû au trait » —
la conclusion ne tient QUE par le RE (la fonction native lit les membres, pas les traits). Porteurs =
4 npc + 2 summons invoqués par `EnvFactionSummons:AstraMilitarum` (ability d'ENVIRONNEMENT, aucun summoner
du pool) ⇒ non confrontable live de toute façon.
"""
from __future__ import annotations

import math

# Ability/trait ids (hex natifs). #157 : TRAIT_RESILIENT=1009 / TRAIT_IMPERVIOUS=28 (morts) retirés — la logique
# gate par bool name-based (target_has_resilient/impervious) ; ids dans `entities.traits.UnitTrait` (#146).
# #156 : le member-cap gate par le bool `profile_has_hits_multiple_members` (= `DamageTrait.HitsMultipleMembers`,
# entities/damage_trait.py). Quand il sera wiré, le calculer name-based sur gameconfig comme OnFire :
# `DamageTrait.HitsMultipleMembers.name in damage_profile(profile)["Traits"]` (Traits = liste de NOMS). Aucune
# constante int-brute ici (l'ex-`PROFILE_TRAIT_HITS_MULTIPLE_MEMBERS = int(...)` était morte + mauvais format → retirée).
# #158 : ex-`ABILITY_BOSS_END_FIGHT_UNDEFEATED = 0x5d4` (= TriggeredAbilityType.BossEndFightUndefeated, 1492) et
# `BOSS_CAP_CONSTANT_INDEX = 0x12` (index GetNumberConstant) retirés — morts (le cap boss gate par les params
# `target_has_boss_cap` / `boss_cap_const` de `apply_trait_damage_limits_to_damage`, jamais ces constantes).


def get_group_unit_max_health_with_remaining_members(total_hp: int, member_count: int,
                                                     remaining: int) -> int:
    """IdunBattle.Core.Services.DamageCalculations$$GetGroupUnitMaxHealthWithRemainingMembers : somme des PV des
    `remaining` premiers membres, PV repartis (total_hp / member_count, +1 pour les premiers restes)."""
    acc = 0
    if remaining <= 0:
        return 0
    for i in range(remaining):
        if i < member_count:
            per = total_hp // member_count
            if i < total_hp - per * member_count:   # reste de la division reparti sur les 1ers membres
                per += 1
        else:
            per = 0
        acc += per
    return acc


def get_group_unit_remaining_member_count(total_hp: int, member_count: int, damage: int) -> int:
    """IdunBattle.Core.Services.DamageCalculations$$GetGroupUnitRemainingMemberCount : nb de membres SURVIVANTS apres
    `damage` (retire des membres tant que la somme de leurs PV <= damage)."""
    m = member_count
    while m >= 1:
        acc = 0
        for i in range(m - 1):
            if i < member_count:
                per = total_hp // member_count
                if i < total_hp - per * member_count:
                    per += 1
            else:
                per = 0
            acc += per
        if acc < damage:
            break
        m -= 1
    else:
        return 0
    return m


def get_group_unit_heal_limit(member_total_hp: int, member_count: int, current_hp: int) -> int:
    """`IdunBattle.Core.Services.DamagePrediction$$GetGroupUnitHealLimit` : cap de soin « sans réveiller de membre »
    d'une unité multi-membres = `maxHealthWith(membres RESTANTS) − hp`. Héros (`nrOfMembers < 2`) →
    int.MaxValue (pas de cap). Consommé par `IdunBattle.Core.Services.DamagePrediction$$PredictHeal` / `IdunBattle.Core.Services.DamagePrediction$$PredictRepair`
    **UNIQUEMENT sous leur flag d'appel** (`param_6/param_7 == 1`) : `amount = Min(amount, healLimit)`
    AVANT le cap boss et le `MaxFillUp` (#60)."""
    if member_count < 2:
        return 0x7fffffff
    remaining = get_group_unit_remaining_member_count(member_total_hp, member_count, current_hp)
    return get_group_unit_max_health_with_remaining_members(
        member_total_hp, member_count, remaining) - int(current_hp)


def is_at_group_unit_heal_limit(member_total_hp: int, member_count: int, current_hp: int) -> bool:
    """`IdunBattle.Core.Services.AttackQuery$$IsAtGroupUnitHealLimit` : l'unité multi-membres est « au plafond de soin »
    (hp >= max des membres RESTANTS — tout soin supplémentaire ne ferait QUE réveiller des membres).
    Héros → False. Consommé par les gates d'éligibilité `IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed` /
    `IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired/IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired` : sous leur flag d'appel (param 4/3), une cible « at
    limit » n'est PAS éligible au soin/repair (#60)."""
    if member_count < 2:
        return False
    remaining = get_group_unit_remaining_member_count(member_total_hp, member_count, current_hp)
    return get_group_unit_max_health_with_remaining_members(
        member_total_hp, member_count, remaining) <= int(current_hp)


def group_unit_stat_part(part: int, member_total_hp: int, member_count: int,
                         current_hp: int) -> int:
    """Résolution OFFLINE de `GetStat(unit, NUMBER_OF_MEMBERS=20, part)` (#60).

    Natif : `IdunBattle.Entities.UnitExtensions$$GetStat` case 0x14 (jumptable, handler IdunBattle.Entities.UnitExtensions$$GetStat+0x859) =
    `GetComponent<GroupUnitComponent>` puis **`IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart`** direct sur
    ce composant — layout fill-up : `+0x10` = nrOfMembers (base), `+0x18` = membres RESTANTS (champ
    MAINTENU par le jeu au fil des événements PV). Offline le champ « courant » est DÉRIVÉ de l'état
    PV — même invariant, les mainteneurs natifs étant exactement les événements de mutation PV :
    `current = GetGroupUnitRemainingMemberCount(hpMax, n, hp)` (IdunBattle.Core.Services.DamageCalculations$$GetGroupUnitRemainingMemberCount).

    Parts (mirror IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart) : 0=Current → membres restants ; 2=Maximum (`IdunBattle.Entities.Components.FillUpStatComponent$$get_CurrentMaximumValue` = base + mod clampé ; aucun mod de membres offline → n) ; 3=Initial → champ base
    `+0x10` = n ; 4=Missing → max − current = membres MORTS ; 1=CurrentPct → round(max(0, cur/max)·100).
    C'est la source des deux `StatAmount(Self, 20, part 3/4)` de `IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateBehaviour`."""
    n = max(1, int(member_count))
    p = int(part)
    if p in (2, 3):
        return n
    remaining = get_group_unit_remaining_member_count(int(member_total_hp), n, int(current_hp))
    if p == 0:
        return remaining
    if p == 4:
        return n - remaining
    if p == 1:
        return round(max(0.0, remaining / n) * 100)
    raise ValueError(f"StatPart {p} non implemente (GroupUnitComponent stat 20)")


def apply_group_unit_damage_limit(dmg: int, profile_has_hits_multiple_members: bool,
                                  member_count: int, member_total_hp: int,
                                  cumulative_damage: int, flag: bool = False) -> int:
    """IdunBattle.Core.Services.DamagePrediction$$ApplyGroupUnitDamageLimit : cape le degat a la frontiere de membre
    pour une cible MULTI-MEMBRE. Skip si le profil a HitsMultipleMembers (trait 2 = Blast). No-op si
    `member_count <= 1` (heros). `cumulative_damage` = param_5.

    /!\\ BORD CONFORME AU NATIF (#87) : a `remaining == 1` (un membre deja mort, donc PV < 50%), le gate
    `if (1 < remaining)` est FAUX -> **plus aucun cap**, le dernier membre peut etre one-shot. Le tooltip
    TwoManTeam (« max 50% d'un seul coup ») est donc inexact en fin de vie ; on mirror le natif."""
    if member_count <= 1:
        return dmg
    if profile_has_hits_multiple_members:   # HasTrait(profile, 2) -> return (pas de member-cap pour Blast)
        return dmg
    if flag:
        return dmg
    remaining = get_group_unit_remaining_member_count(member_total_hp, member_count, cumulative_damage)
    if remaining > 1:
        cap_health = get_group_unit_max_health_with_remaining_members(
            member_total_hp, member_count, remaining - 1)
        limit = cumulative_damage - cap_health
        if dmg > limit:
            dmg = limit
    return dmg


def apply_resilient_trait_damage_limit(dmg: int, target_has_resilient: bool,
                                       current_health: int, max_health: int,
                                       overkill: bool = False) -> int:
    """IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit : trait Resilient (0x3f1=1009). Si la
    cible a Resilient ET max_health(param_5) > 1 ET current_health(param_4) > 0 ET PAS overkill : cape le
    degat a `current_health - 1` (ne peut pas one-shot ; laisse 1 PV). (param_4=param_9=currentHealth,
    param_5=param_11=maxHealth, param_6=flag overkill.)"""
    if not overkill:
        if target_has_resilient and max_health > 1 and current_health > 0:
            cap = current_health - 1
            if dmg > cap:
                return cap
    return dmg


def apply_impervious_trait_damage_limit(dmg: int, target_has_impervious: bool,
                                        impervious_stat_current: int | None,
                                        param_6: int, param_7: int) -> int:
    """IdunBattle.Core.Services.DamagePrediction$$ApplyImperviousTraitDamageLimit : trait Impervious (0x1c=28). Lit un
    StatComponent (charge Impervious) : si absent -> pas de cible valide ; CurrentValue < 1 OU < 100 ->
    degat = 0 (bloque) ; sinon degat = param_6 + param_7. (`impervious_stat_current` = None -> pas
    d'Impervious sur cette cible -> no-op.)"""
    if not target_has_impervious or impervious_stat_current is None:
        return dmg
    if impervious_stat_current < 1 or impervious_stat_current < 100:
        return 0
    return param_6 + param_7


def is_overkill(current_health: int, damage: int, default_flag: int,
                allow_flag: int, suppress: int, cond: int, threshold_pct: int) -> int:
    """IdunBattle.Core.Services.DamagePrediction$$IsOverkill : le degat depasse-t-il la sante d'un ratio > seuil ?
    (param_1=currentHealth, param_2=damage, param_7=threshold%). Simplifie : renvoie 1 si overkill
    au-dela du seuil, sinon default/0. (Gate `cond`=param_6 ; `suppress`=param_5.)"""
    if not cond:
        return 0
    if damage >= current_health:
        if allow_flag:
            return 1
    if not suppress and current_health > 0:
        pct = int((damage - current_health) / current_health * 100)
        if damage >= current_health:
            return default_flag if pct < threshold_pct else 1
    return 0


def _overkill_threshold_pct() -> int:
    """Seuil % de la porte overkill du chemin PREDICTION. Le natif le lit dans le composant DI
    `DamagePrediction+0x10 @0x34` (config asset-driven, PAS un litteral binaire ; VERDICT RE : borne live
    (33,101]). On le source de gameconfig `overkillDmgPctOfHealth` (=100) : MEME global que le `is_overkill`
    death-riposte (FinalJustice/TheBetrayer, meme fn native IdunBattle.Core.Services.DamagePrediction$$IsOverkill), et == la borne live => HYPOTHESE
    forte config-DI == overkillDmgPctOfHealth (les deux valent 100). Derivable offline, pas de hardcode."""
    import gameconfig as GC
    return int(GC.global_value("overkillDmgPctOfHealth") or 100)


def compute_prediction_overkill(cur_hp: int, max_hp: int, dmg_min: int, *,
                                suppress: bool = False, p12: int = 0) -> bool:
    """Flag overkill du chemin PREDICTION — `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage` calcule
    `IdunBattle.Core.Services.DamagePrediction$$IsOverkill(maxHP, accum, ...)` UNE fois depuis la borne **MIN** et le passe aux 2 bornes du
    cap Resilient/member. accum = `(maxHP - curHP) + dmgMin (+p12)` ; base pct = maxHP (troncature Fix64).
    Defauts bataille reelle (VERDICT RE) : cond=1, default=0, allow=0, global-override absent. `suppress` =
    flag runtime BlockOverkill `HasFlag(target,0x13)` pose par `FuelledByFury_BlockOverkillEffect IdunBattle.Entities.Effects.Loki.FuelledByFury_BlockOverkillEffect$$ApplyInternal`
    (effet Loki, normalement False -> derivable via la couche effets si un roster Loki entre en jeu).
    Renvoie True => cap Resilient BYPASSE (l'unite meurt : dmg non cape a HP-1). Confirme live (u78 Resilient :
    over-kill massif PV=10 -> skip=meurt=HP ; modere PV=4700/6000/6900 -> cape=HP-1)."""
    if max_hp <= 0:
        return False
    accum = (max_hp - cur_hp) + dmg_min + p12
    return bool(is_overkill(current_health=max_hp, damage=accum, default_flag=0, allow_flag=0,
                            suppress=1 if suppress else 0, cond=1,
                            threshold_pct=_overkill_threshold_pct()))


def apply_trait_damage_limits_to_damage(
        dmg: int, *, is_special: int = 1,
        target_has_resilient: bool = False, target_has_impervious: bool = False,
        impervious_stat_current: int | None = None,
        member_count: int = 1, member_total_hp: int = 0,
        profile_has_hits_multiple_members: bool = False,
        current_health: int = 0, max_health: int = 0,
        target_has_boss_cap: bool = False, boss_cap_const: int = 0,
        cumulative_damage: int | None = None, overkill: bool = False) -> int:
    """IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage — orchestre les 5 limites sur UNE borne
    de degat (int). Ordre natif :
      1. ApplyGroupUnitDamageLimit (member-cap)         IdunBattle.Core.Services.DamagePrediction$$ApplyGroupUnitDamageLimit
      2. ApplyResilientTraitDamageLimit (Resilient)     IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit
      3. si is_special==1 : IdunBattle.Core.Services.DamagePrediction$$ApplyImperviousTraitDamageLimit
      4. si HasTriggeredAbility(0x5d4=1492) : cap boss  = Min(dmg, param_9 - maxHealth*const/100)
    `cumulative_damage` (param_5 member-cap / param_9 boss) defaut = current_health si None."""
    cum = current_health if cumulative_damage is None else cumulative_damage
    # 1. member-cap — flag natif = octet 0 CONSTANT aux deux appels du core (IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage :
    # `in_stack_...b0 & 0xffffff00` -> byte 0) : l'overkill ne bypasse JAMAIS le member-cap
    # (seul le cap Resilient est gate par IsOverkill, calcule APRES les group caps). #67 :
    # l'ex-passage d'`overkill` ici etait une deviation inexercee (overkill exige dmg >=
    # ~2x hpMax, jamais combine a une cible multi-membre dans les validations).
    dmg = apply_group_unit_damage_limit(
        dmg, profile_has_hits_multiple_members, member_count, member_total_hp, cum, False)
    # 2. Resilient
    dmg = apply_resilient_trait_damage_limit(
        dmg, target_has_resilient, current_health, max_health, overkill)
    # 3. Impervious (seulement chemin special is_special==1)
    if is_special == 1:
        dmg = apply_impervious_trait_damage_limit(
            dmg, target_has_impervious, impervious_stat_current, current_health, 0)
    # 4. cap BossEndFightUndefeated (0x5d4=1492)
    if target_has_boss_cap:
        # uVar3 = Max(param_9 - maxHealth * const/100, 0) ; dmg = Min(dmg, uVar3)
        cap = max(cum - int(math.floor(max_health * boss_cap_const / 100.0)), 0)
        if dmg > cap:
            dmg = cap
    return dmg
