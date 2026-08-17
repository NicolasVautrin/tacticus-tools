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

⚠ RE-MESURE SUR LE BUILD COURANT `rnca9r7q6c` (#1015-r1, 2026-08-14) — le verdict TIENT, et le `.cctor`
compte désormais **8** conteneurs (le 8ᵉ, `statics+0x38`, est un `HashSet` construit, JAMAIS alimenté et
JAMAIS lu : 1 seule occurrence de son offset dans tout le binaire, le `.cctor` lui-même). `0x3fa` reste
clé d'aucun des huit. S'y ajoute une TROISIÈME lecture, indépendante des deux ci-dessus : **0 symbole**
portant `TwoManTeam` sur les 154 177 fonctions de `data/symbols/<build>/ghidra/functions.tsv`
(`BeastSnagga` en a 4, `BeastSlayer` 11) — cran EXÉCUTABLE et offline, `SANS_ARTEFACT_NATIF` de
`scripts/python/tests/test_1015_trait_channels_offline.py` étage 6. Ce cran ne DÉMONTRE pas le verdict
(l'absence de symbole homonyme n'implique pas l'absence de lecture, cf. `Diminutive` ci-dessus) : il en
garde la PÉREMPTION. Détail : `docs/rl/case-1015-r1-beast-snagga.md` § 2.

⚠ AUCUN cas discriminant n'existe LIVE : sur les 17 unités multi-membres du jeu, les 6 à `nrOfMembers == 2`
sont EXACTEMENT les 6 porteurs du trait ; les 11 autres (Swarm/Nurglings/Ripper) ont 4-5 membres et n'ont
PAS le trait. Le live ne pourrait donc jamais départager « cap dû aux membres » de « cap dû au trait » —
la conclusion ne tient QUE par le RE (la fonction native lit les membres, pas les traits). Porteurs =
4 npc + 2 summons invoqués par `EnvFactionSummons:AstraMilitarum` (ability d'ENVIRONNEMENT, aucun summoner
du pool) ⇒ non confrontable live de toute façon.
"""
from __future__ import annotations

import math
from typing import Optional

from ..entities.stats import StatPart
from .damage_config import resolve_damage_field

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
                         current_hp: int, member_maximum: "Optional[int]" = None) -> int:
    """Résolution OFFLINE de `GetStat(unit, NUMBER_OF_MEMBERS=20, part)` (#60).

    Natif : `IdunBattle.Entities.UnitExtensions$$GetStat` case 0x14 (jumptable, handler
    IdunBattle.Entities.UnitExtensions$$GetStat+0x859) = `GetComponent<`
    `IdunBattle.Entities.Components.NumberOfMembersComponent``>` puis
    **`IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart`** direct sur ce composant —
    layout fill-up : `+0x10` = nrOfMembers (Initial), `+0x14` = base, `+0x18` = membres RESTANTS
    (champ MAINTENU par le jeu au fil des événements PV).

    ⚠ **Le composant s'appelle `NumberOfMembersComponent`, pas `GroupUnitComponent`** : ce dernier
    n'existe PAS dans le build (0 ligne dans `data/symbols/<build>/frida/classes.tsv`) — seul le
    PRÉFIXE `GroupUnit` existe, et uniquement sur des fonctions de `DamageCalculations` /
    `BattleQuery`. Nom corrigé par #572-r3.

    Le mainteneur natif du champ courant est NOMMÉ, et c'est ce qui autorise la dérivation offline :
    `IdunBattle.Operations.UpdateUnitMembersOperation$$Execute` pose
    `+0x18 = IBattleQuery.<slot 184 GetGroupUnitRemainingMemberCount>(unit, null)`, et
    `IdunBattle.Operations.ApplyDamageOperation$$UpdateNumberOfMembersStat` l'appelle après chaque
    dégât (il en rend `avant − après` = les membres morts). La surcharge d'`IBattleQuery` lit le
    `HealthComponent` (`get_CurrentMaximumValue()` + `+0x18`) et le **`+0x10`** du
    `NumberOfMembersComponent` — donc `totalMembers` est bien l'**Initial**, PAS le maximum.

    Parts (mirror `FillUpStatComponent$$GetStatPart`) : 0=Current → membres restants ;
    **2=Maximum → `get_CurrentMaximumValue()`** ; **3=Initial → champ `+0x10` = n** ;
    4=Missing → max − current = membres MORTS ; 1=CurrentPct → round(max(0, cur/max)·100).
    C'est la source des deux `StatAmount(Self, 20, part 3/4)` de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateBehaviour`.

    ⚠ **`member_maximum` (#572-r3) SÉPARE les parts 2 et 3**, que ce mirror confondait (`if p in
    (2, 3): return n`) — le piège exact de #873, transposé du `HealthComponent` : elles coïncident
    tant qu'aucune modification `+0x28` ni override `+0x38` n'existe, et divergent ensuite. `None`
    = le maximum n'est pas capté ⇒ on retombe sur `n`, ce qui EST l'état posé par
    `FillUpStatComponent$$Initialize` (`+0x10 = +0x14 = +0x18`)."""
    n = max(1, int(member_count))
    mx = n if member_maximum is None else int(member_maximum)
    p = int(part)
    if p == StatPart.MAXIMUM:                     # 2 -> get_CurrentMaximumValue()
        return mx
    if p == StatPart.INITIAL:                     # 3 -> champ `+0x10`
        return n
    remaining = get_group_unit_remaining_member_count(int(member_total_hp), n, int(current_hp))
    if p == StatPart.CURRENT:                     # 0
        return remaining
    if p == StatPart.MISSING:                     # 4 -> membres MORTS (max - current)
        return mx - remaining
    if p == StatPart.CURRENT_PCT:                 # 1
        if mx <= 0:
            return 0
        return round(max(0.0, remaining / mx) * 100)
    raise ValueError(f"StatPart {p} non implemente (NumberOfMembersComponent, stat 20)")


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


def is_overkill(target_initial_health: int, health_damage: int, is_critical: int,
                is_force_overkill: int, is_prevent_overkill: int, allow_overkill: int,
                overkill_dmg_pct_of_health: int,
                target_minimum_health: int | None = None) -> int:
    """`IdunBattle.Core.Services.DamagePrediction$$IsOverkill` — **surcharge PRIVEE, 8 parametres**
    (celle qui porte la FORMULE). Signature VERBATIM (methods.tsv du build) :

        IsOverkill(targetInitialHealth:int, healthDamage:int, isCritical:bool, isForceOverkill:bool,
                   isPreventOverkill:bool, allowOverkill:bool, overkillDmgPctOfHealth:int,
                   targetMinimumHealth:Nullable<int>)

    ⚠ Les noms de parametres du port etaient jusqu'ici des PLACEHOLDERS opaques
    (`default_flag`/`allow_flag`/`cond`/`suppress`/`extra_damage`) : c'est CE flou qui a fait classer
    trois d'entre eux en « residu non descendu » alors qu'ils portent une SEMANTIQUE ordinaire et
    ATTEIGNABLE. Ils sont desormais nommes comme le natif.

    Corps (mirror) :

        if (!allowOverkill) return false;                                   // gate global
        if (targetMinimumHealth.HasValue && targetMinimumHealth.Value >= 1) return false;
        if (targetInitialHealth <= healthDamage && isForceOverkill) return true;
        if (!isPreventOverkill && targetInitialHealth <= healthDamage) {
            pct = (int)((healthDamage - targetInitialHealth) / targetInitialHealth * 100);   // Fix64
            return pct < overkillDmgPctOfHealth ? isCritical : true;        // <- LE point cle
        }
        return false;

    **`isCritical` est la valeur de RETOUR du cas « letal mais sous le seuil »** : un coup CRITIQUE qui
    tue sans atteindre `overkillDmgPctOfHealth`% de sur-degat EST un overkill, un coup normal ne l'est
    pas. Ce n'est pas un « flag par defaut » : c'est la regle de jeu « un crit letal overkille ».

    ⚠ TROIS surcharges natives homonymes existent, et c'est CE corps que les trois atteignent :
      * la privee ci-dessous  <- LE calcul ;
      * la surcharge d'INSTANCE `(this, target, hitDamage, deniedDamage, isCritical, isForceOverkill,
        targetHealthBeforeAttack, minimumHealth)`, qui ajoute les GATES d'unite avant de deleguer ici
        -> portee par `unit_is_overkill` ;
      * une surcharge mince `(this, targetInitialHealth, healthDamage, isCritical, isForceOverkill,
        isPreventOverkill, minimumHealth)` qui resout `allowOverkill`/`pct` depuis la config DI
        (`this+0x10 @+0x30/@+0x34`) et delegue ici.

    `allowOverkill`/`overkill_dmg_pct_of_health` : la surcharge d'instance et
    `ApplyTraitDamageLimitsToDamage` les lisent dans la config DI (`cfg@+0x30` bool / `cfg@+0x34` int) ;
    `DamagePredictionResult$$WillBeOverkill` / `$$MightBeOverkill` les prennent des deux moities d'un
    `Nullable<int>` (`HasValue(result@+0xb4)` puis `GetValueOrDefault`). Les deux lectures sont vraies,
    sur des sources differentes. `allowOverkill` faux => JAMAIS d'overkill.

    `target_minimum_health` = plancher de PV Hypersensory (`HealthComponent.minimal_health`, natif
    `MinimalHealth@+0x1c`, pose par
    `IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$ApplyInternal`) :
    **une unite sous plancher n'est JAMAIS overkillee**. `None` = pas de plancher (Nullable vide).

    `target_initial_health > 0` = garde de port (le natif divise par `param_1` en Fix64 ; PV<=0
    n'atteint jamais ce chemin, la cible etant deja morte)."""
    if not allow_overkill:
        return 0
    if target_minimum_health is not None and int(target_minimum_health) >= 1:
        return 0
    if health_damage >= target_initial_health:
        if is_force_overkill:
            return 1
    if not is_prevent_overkill and target_initial_health > 0:
        pct = int((health_damage - target_initial_health) / target_initial_health * 100)
        if health_damage >= target_initial_health:
            return (1 if is_critical else 0) if pct < overkill_dmg_pct_of_health else 1
    return 0


def unit_is_overkill(current_health: int, damage: int, *,
                     can_be_overkilled: bool = True, denied_damage: int = 0,
                     prevent_overkill: bool = False, is_critical: bool = False,
                     is_force_overkill: bool = False, allow_overkill: int | None = None,
                     target_minimum_health: int | None = None) -> bool:
    """`IdunBattle.Core.Services.DamagePrediction$$IsOverkill` — **surcharge d'INSTANCE**
    `(this, IEntity target, int hitDamage, int deniedDamage, bool isCritical, bool isForceOverkill,
    Nullable<int> targetHealthBeforeAttack, Nullable<int> minimumHealth)`. C'est LA porte du chemin
    COMBAT : son corps est INLINE dans
    `IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation`, dont le resultat est ecrit en
    `didOverkill` du `DamageAppliedResult` (@+0x13) et consomme par
    `IdunBattle.Operations.ApplyDamageOperation$$Execute+0x17d5` -> `UnitFlagsComponent.Add(target, 8)`
    (= `UnitFlag.Overkilled`, lu par le noeud DSL `IdunBattleLogic.Entities.DSLTriggers$$TargetIsOverkilled`
    = `HasFlagAbilityTrigger(target, 8)`).

    Mirror du corps natif, dans l'ordre :

        if (!UnitExtensions.CanBeOverkilled(target)) return false;      // trait Steppable 0x1b
        hitDamage += deniedDamage;
        currentHealth = UnitExtensions.GetStat(target, Health = 5);
        if (targetHealthBeforeAttack.HasValue) {                        // TOUJOURS pose sur la voie attaque
            hitDamage  += (targetHealthBeforeAttack.Value - currentHealth)   // degat APPLIQUE des coups precedents
                        + healthComponent@+0x24;                        // degat GASPILLE (cf. plus bas)
            currentHealth = targetHealthBeforeAttack.Value;             // base pct = PV AU DEBUT DE L'ATTAQUE
        }
        isPreventOverkill = UnitExtensions.HasFlag(target, 0x13);       // UnitFlag.PreventOverkill = 19
        return IsOverkill(currentHealth, hitDamage, isCritical, isForceOverkill, isPreventOverkill,
                          cfg@+0x30, cfg@+0x34, minimumHealth);

    **COLLAPSE PER-COUP -> PER-ATTAQUE, et pourquoi il est EXACT.** Le natif appelle cette surcharge a
    CHAQUE coup, mais avec `targetHealthBeforeAttack` = les PV au DEBUT DE L'ATTAQUE : le terme
    `(initialHealth - currentHealth) + @+0x24` re-agrege le degat des coups precedents -- **applique
    PLUS gaspille**, donc le DEMANDE cumule (cf. l'identite ci-dessous) --, donc l'argument compare a
    `initialHealth` est le CUMUL de l'attaque. Le port n'a qu'un chokepoint par attaque
    (`AttackDamageOperation._apply_damage_pipeline`) : lui passer `current_health = hp au debut de
    l'attaque` et `damage = cumul` reproduit donc EXACTEMENT l'appel du coup considere. Le seul ecart
    restant est que le natif evalue la condition COUP PAR COUP (et pose le flag des qu'UN coup rend
    vrai) : c'est pour ca que `AttackDamageOperation._did_overkill` re-joue la sequence des coups au
    lieu d'un appel unique -- `isCritical` et `deniedDamage`, eux, VARIENT d'un coup a l'autre.
    ⚠ #462-r4e-o-r1 : ce collapse ne suffit PAS pour la CARDINALITE des events. Le flag `Overkilled`
    coupe l'emission des coups SUIVANTS (SITE (A)), donc il faut le poser AU BON COUP, dans la boucle
    -- c'est `damage_hits.overkill_flag_posted_by_hit`, qui mirrore la forme NATIVE (les trois
    termes separes) plutot que l'identite, et dont ce chokepoint-ci consomme desormais le verdict.

    `allow_overkill` / seuil = les deux moities de la config DI (`DamagePrediction+0x10`, bool @+0x30 /
    int @+0x34) : `allow_overkill` = 1 en bataille reelle (VERDICT RE), seuil = le MEME global
    `overkillDmgPctOfHealth` (=100 -> overkill ssi `dmg >= 2*PV`, cf. `_overkill_threshold_pct`).

    Les lectures d'entite du natif arrivent ici en valeurs deja resolues, parce que `services/` ne
    connait pas les entites du runner -- leurs mirrors vivent avec les autres `UnitExtensions`
    (`runner/components.py`) : `can_be_overkilled` = `IdunBattle.Entities.UnitExtensions$$CanBeOverkilled`,
    `prevent_overkill` = `UnitExtensions.HasFlag(target, 0x13)`, `target_minimum_health` =
    `HealthComponent.minimal_health` (natif `MinimalHealth@+0x1c`, meme composant que celui d'ou
    `CalculateDamageOperation` tire le 8e argument).

    Etat des gates :
      * `prevent_overkill` -- MESURE LIVE (#178, `probe_178_overkill_gate.py --case titus`) : `ultraTitus`
        porte `FuelledByFury_BlockOverkill` des le deploiement ; 1452 de degat sur 400 PV le TUE sans le
        marquer overkill, la ou la MEME attaque sur `genesPrimus` (400 PV) le marque.
      * `is_critical` -- MESURE LIVE (#R33, `probe_178_overkill_gate.py --case crit/nocrit`) : a degat
        LETAL mais SOUS le seuil (`PV <= dmg < 2 x PV`), un coup CRITIQUE marque overkill et un coup
        normal non. C'est le champ que le port passait a 0 en dur.
      * `is_force_overkill` -- flag `AttackOptions@+4` (`AttackWithAttackDamage` 8e arg) et
        `EffectAdditionalHits.forceOverkill` : « des que letal, overkill », meme tres en-dessous du
        seuil. Porteur d'attaque : `FlailSwing` (1042, deathBlightlord).
      * `denied_damage` -- degat REFUSE par l'etage limites aux coups PRECEDENTS
        (`previousHitsDeniedDamage` d'`ApplyTraitDamageLimitsToDamage` = le `_rogne` de `_run_hits`) :
        il compte dans le total d'overkill bien qu'il n'ait jamais touche les PV.
      * `can_be_overkilled` -- porte, et **STRUCTURELLEMENT QUIESCENT au chokepoint de mort** (verdict
        MESURE, pas suppose) : `python unit_map.py find --trait Steppable` rend **27 porteurs, tous a
        `HP 0`** (25 npc de decor/power-ups + les 2 decoys `genesDecoy`/`genesSmnDecoy`). Le gate de
        mort du port est `hp_before > 0 and hp_after == 0` : une entite a 0 PV ne l'atteint jamais.
        Le natif ne les tue pas par degat mais par ECRASEMENT (`DamageReason.Steppable = 2`, chemin
        `movement.py::_kill_steppable_units`, hors `_fire_death_if_killed`). Ce n'est donc PAS un trou
        de montage : aucun scenario ne peut distinguer ce gate sur la face COMBAT.
      * `target_minimum_health` -- porte, et **quiescent au chokepoint de mort par construction** : un
        plancher de PV actif empeche `HealthComponent.reduce` d'amener les PV a 0, donc la sequence de
        mort n'est jamais atteinte tant qu'il tient. Il compte en revanche sur la face PREDICTION.

    ⚠ **`@+0x24` N'EST PLUS UN RESIDU — il est NOMME, MESURE et LOAD-BEARING (#462-r4e-o-r1).**
    L'ancienne redaction en faisait une hypothese (« accumulateur du degat refuse par le PLANCHER de
    PV, nul tant qu'aucun plancher n'est actif ») : **c'est faux dans les deux moities**. Le composant
    que `IsOverkill` va chercher est le `HealthComponent` lui-meme (meme `GetComponent(target, ...)`
    qu'`ApplyDamageOperation$$Execute`), et `+0x24` est l'accumulateur de SUR-REDUCTION alimente en
    queue d'`IdunBattle.Entities.Components.FillUpStatComponent$$Reduce`
    (`this[0x24] += Math.Max(0, damage - applied)`) -- donc non nul des qu'un coup est ECRETE, avec ou
    sans plancher. Son nom vient du natif : `...$$ResetOverReduce` (`this+0x24 = 0`), **sans aucun
    xref de code** -> le compteur n'est JAMAIS remis a zero. Le plancher, lui, fait l'inverse de ce
    qu'affirmait l'hypothese : quand `Minimum > 0`, `Reduce` **SAUTE** l'accumulation.

    Cote port il vit sur `HealthComponent.over_reduce` et arrive ici par `denied_damage` /
    l'appelant. Ce que ce terme change, MESURE (MC1_67/31337, `--hp-target 4000`) : sans lui le flag
    `UnitFlag.Overkilled` tombe UN COUP TROP TARD et le port emet un event `Amount` de trop.

    IDENTITE : `(targetHealthBeforeAttack - currentHealth)` = degat APPLIQUE des coups precedents,
    `+0x24` = degat GASPILLE -> leur somme est le degat DEMANDE cumule. C'est ce qui rend le collapse
    ci-dessus exact, y compris apres la mort de la cible."""
    if current_health is None or damage is None:
        return False                      # garde de port : le natif n'a jamais de degat/PV nul
    if not can_be_overkilled:
        return False
    total = int(damage) + int(denied_damage)
    return bool(is_overkill(target_initial_health=int(current_health), health_damage=total,
                            is_critical=1 if is_critical else 0,
                            is_force_overkill=1 if is_force_overkill else 0,
                            is_prevent_overkill=1 if prevent_overkill else 0,
                            allow_overkill=(_allow_overkill() if allow_overkill is None
                                            else allow_overkill),
                            overkill_dmg_pct_of_health=_overkill_threshold_pct(),
                            target_minimum_health=target_minimum_health))


def _overkill_threshold_pct(state=None) -> int:
    """Seuil % de la porte overkill. Le natif le lit dans `DamagePrediction+0x10 @+0x34`, et le NOM
    du champ est LU, pas suppose : la surcharge statique
    `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` recoit cet octet-la sous le nom de
    parametre `overkillDmgPctOfHealth`, et les deux surcharges d'instance le lui passent depuis
    `configuration+0x34` = `BC.Damage.OverkillDmgPctOfHealth`.

    #449-r2-r4-r4 -- CORRECTION DE SOURCE. Ce seuil etait lu dans `gameconfig.globalValues
    ["overkillDmgPctOfHealth"]`, c'est-a-dire une AUTRE TABLE que celle que lit le natif. Les deux
    valent 100, donc l'accord etait parfait -- et ne prouvait rien : c'est un accord en REGIME
    DEGENERE, qui se serait tu le jour ou une BC porte une autre valeur. La source est desormais
    `BC.Damage`, via le foyer, avec le meme ordre que partout (explicite > BC de la bataille >
    defaut DERIVE de la seed).
    ⚠ Cette correction n'est pas MESURABLE aujourd'hui, precisement parce que les deux tables
    coincident : elle est justifiee par le decompile, pas par un ecart observe."""
    return int(resolve_damage_field("overkill_dmg_pct_of_health", state=state))


def _allow_overkill(state=None) -> int:
    """`BC.Damage.AllowOverkill` (`+0x30`) -- le GATE GLOBAL de `IsOverkill` (a faux, la fonction
    rend toujours `false`). Meme lecture nominative que le seuil ci-dessus : c'est le parametre
    `allowOverkill` de la surcharge statique.

    #449-r2-r4-r4 -- il etait ecrit `1` en dur a quatre endroits. Le natif, lui, le LIT : un `1`
    du port etait une invention, meme si `Idun.Source.IdunBattle.View.BattleConfigBuilder$$CreateBattleConfig`
    ecrit bien `1` en dur dans les BC qu'IL construit -- ce chemin-la n'est pas le seul par lequel
    une BC arrive (les runners partent d'une seed sur disque, dont la section `Damage` est
    modifiable)."""
    return 1 if resolve_damage_field("allow_overkill", state=state) else 0


def compute_prediction_overkill(cur_hp: int, max_hp: int, dmg_min: int, *,
                                suppress: bool = False, p12: int = 0,
                                is_crit: bool = False, is_forced_overkill: bool = False,
                                minimum_health: int | None = None) -> bool:
    """Flag overkill du chemin PREDICTION — `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage` calcule
    `IdunBattle.Core.Services.DamagePrediction$$IsOverkill(maxHP, accum, ...)` UNE fois depuis la borne **MIN** et le passe aux 2 bornes du
    cap Resilient/member. accum = `(maxHP - curHP) + dmgMin (+p12)` ; base pct = maxHP (troncature Fix64).
    Defauts bataille reelle (VERDICT RE) : allowOverkill=1, global-override absent. `suppress` =
    flag runtime BlockOverkill `HasFlag(target,0x13)` pose par `FuelledByFury_BlockOverkillEffect IdunBattle.Entities.Effects.Loki.FuelledByFury_BlockOverkillEffect$$ApplyInternal`
    (effet Loki, normalement False -> derivable via la couche effets si un roster Loki entre en jeu).
    Renvoie True => cap Resilient BYPASSE (l'unite meurt : dmg non cape a HP-1). Confirme live (u78 Resilient :
    over-kill massif PV=10 -> skip=meurt=HP ; modere PV=4700/6000/6900 -> cape=HP-1).

    NOMS NATIFS (signature relue au build) : `cur_hp` = `currentHealth`, `max_hp` = `initialHealth`
    (PV au DEBUT de l'attaque, PAS hpMax -- cf. `_target_limits`), `dmg_min` = la cellule MIN,
    `p12` = `previousHitsDeniedDamage`. `is_crit` = le 7e parametre `isCrit` d'
    `ApplyTraitDamageLimitsToDamage`, `is_forced_overkill` son 12e : les DEUX descendent tels quels
    dans `IsOverkill`. Ils sont exposes ici pour que l'etage limites soit un mirror complet ; le
    call-site `_run_hits` passe deja `force_overkill` par un `or` en amont (equivalent sur le seul
    consommateur, le cap Resilient : le cap ne mord que si `dmg >= curHP`, cas ou l'accum atteint
    forcement `initialHealth`)."""
    if max_hp <= 0:
        return False
    accum = (max_hp - cur_hp) + dmg_min + p12
    return bool(is_overkill(target_initial_health=max_hp, health_damage=accum,
                            is_critical=1 if is_crit else 0,
                            is_force_overkill=1 if is_forced_overkill else 0,
                            is_prevent_overkill=1 if suppress else 0, allow_overkill=_allow_overkill(),
                            overkill_dmg_pct_of_health=_overkill_threshold_pct(),
                            target_minimum_health=minimum_health))


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
