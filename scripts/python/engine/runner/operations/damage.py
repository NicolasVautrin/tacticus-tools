"""Operations de dégât — `IdunBattle.Operations.AttackDamageOperation` (gqfc5mff6c).

Tranche DAMAGE. **Palier 1 (porté + validé ici) : le TIRAGE de dégât par coup**
(`HitDamage.GetDamage`), bit-exact via le MT porté (`engine/runner/prng.py`).

Chaîne native RE'd (VA citées) :

    IdunBattle.Operations.AttackDamageOperation$$Execute
      → IdunBattle.Operations.AttackDamageOperation$$GetAttackHits   (nb de coups ; 1 par défaut)
      → ExecuteHits (boucle nbHits)      IdunBattle.Operations.AttackDamageOperation$$ExecuteHits
          → ExecuteHit (PAR COUP)        IdunBattle.Operations.AttackDamageOperation$$ExecuteHit   — per-coup PARTAGÉ : attaque NORMALE **et**
            attaques d'ABILITY `AttackWithAttackDamage` (IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget → stream slot 0x3c → même opération). Corrigé cas fable rngcrit-1202 :
              1. IdunBattle.Core.HitDamage$$GetDamage   sur le STRUCT d'entrée — tirage SSI min!=max :
                 NORMALE = struct DÉGÉNÉRÉ → 0 tirage ; ABILITY bounds = [minDmg,maxDmg] config
                 → 1 tirage = LA VALEUR BRUTE (roll-then-reduce).
              2. RollCritical (IDamagePrediction slot 0xa → IdunBattle.Core.Services.DamagePrediction$$RollCritical : gate `cc<1 → false SANS tirage` → IdunBattle.Core.Services.DamageCalculations$$RollCritical = NextBool brut, atteint seulement à travers le gate)  ← SI cc≥1
              3. slot 4 IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation : shield-part/armure/caps → cellules
                 min/max (0 RNG) — NORMALE : bornes RÉDUITES ; ABILITY : cellules DÉGÉNÉRÉES.
              4. slot 8 IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage : Next(min,max+1) — TOUJOURS
                 1 tirage (AUCUN gate min==max) : NORMALE = LA VALEUR (plage réduite) ;
                 ABILITY = tirage GASPILLÉ (largeur 1).
              5. sub-op 0x42 : block rolls + split bouclier/armure-pool (calculate_damage_operation)
              6. IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers (cascade)

**Ordre RNG CONFIRMÉ (genrand brut live, necroDestroyer CC=100 ; re-mesuré probe_rngcrit_1202
2026-07-23, custoKyrus 3-hit cc=0, 5 seeds x 2 cibles)** : attaque NORMALE par coup =
RollCritical si cc≥1 (tirage PAIR) PUIS valeur (resolve slot 8, tirage IMPAIR). À cc=0,
RollCritical ne tire RIEN (gate `cc<1` de IdunBattle.Core.Services.DamagePrediction$$RollCritical) → 1 tirage/coup (validé 18/18 + probe A).
Attaque d'ABILITY bounds-mode par coup à cc=0 : **2 tirages** = valeur BRUTE (GetDamage-top)
puis resolve GASPILLÉ — cf. `_one_hit`. La désync #220/#205 (« 6 rng pour 3 coups ») était ce
resolve dégénéré, PAS un crit-roll : aucun chemin natif ne consomme un tirage crit à cc=0.

**CRIT (combat ≠ prédiction)** : le crit du COMBAT s'ajoute à la BASE D'ATTAQUE AVANT
spread/perçage (`GetBaseDamageFix64` param_4=isCrit ⇒ `eff_attack=attack+critDamage`,
même pipeline) — PAS l'`ApplyCritDamage` post-réduction (base+bonus) de la PRÉDICTION.
Confirmé bit-exact : crit per-coup [675,1012] = non-crit [435,652]×(906+500)/906, et
next_internal(675,1013) aux tirages impairs = live [932,882,967,867,961,955] à l'unité.

**#73 (RE close, 2026-07-09) : le crit N'A PAS de gating inter-coups** (contrairement au block #72).
`IdunBattle.Core.Services.DamagePrediction$$RollCritical`→`IdunBattle.Core.Services.DamageCalculations$$RollCritical` = NextBool(GetStat(9)+bonus) SANS ETAT ; pas d'"AddFailedCrit"
dans `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (le block, lui, a `AddFailedBlockIds`). Chaque coup tire le crit INDÉPENDAMMENT
avec la même chance ⇒ `_run_hits` (crit par-coup, aucun accumulateur) est déjà fidèle. Le block gate PARCE
QUE multi-source (id par source) ; le crit est chance unique ⇒ rien à exclure. (Détail : docs/rl/case-68.)

    #74 (2026-07-09), **REFUTE le 2026-08-07 par #522-r1** : la crit-chance est RELUE PAR COUP par le
    natif -- ca, c'est exact et toujours vrai (`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`
    dispatche `RollCritical`, slot 0xa d'`IDamagePrediction`, A CHAQUE coup, et
    `IdunBattle.Core.Services.DamagePrediction$$RollCritical` y relit
    `UnitExtensions.GetStat(attacker, 0x9, 0)` + `GetCritChanceBonusFromEffects`). Ce qui etait FAUX,
    c'est la conclusion « MAIS constante sur les coups d'une attaque => `_crit_params` une fois ==
    valeur re-lue par coup => **rien a porter** ».

    ⚠ **POURQUOI LE FAUX A TENU** -- l'argument etait une recherche gameconfig sur **559 ABILITIES**
    (« AUCUNE cle per-hit/consecutive/timesAttacked ; les 19 abilities crit-chance sont des buffs
    per-attaque/aura/per-tour/on-kill, JAMAIS per-coup-intra-attaque »). Or le contre-exemple n'est
    PAS une ability : `ThrillSeekers` est un **TRAIT** (`UnitTrait` 1056, 5 porteurs Emperor's
    Children), donc structurellement HORS du corpus fouille. Un recenseur ne peut pas rendre zero
    sur ce qu'il ne visite pas -- et la ligne citait meme « ThrillSeekers=re-trigger PAR TOUR »,
    en le classant dans la mauvaise categorie sans etre allee lire son `CreateTrigger`.

    LA LOI, telle qu'elle est LUE : `ExecuteHit` appelle `RollCritical` **AVANT** d'emettre
    `On(PreAttackHit = 6)` / `On(PreAttackDamageHit = 7)`. Le stat-mod CRIT_CHANCE pose par
    `...ThrillSeekersAbility$$CreateBehaviour` sur `On(6) & IsFirstHitInSeries` ne mord donc PAS sur
    le coup 0, et mord sur **tous** les coups suivants de la MEME salve. Porte par le couple
    (`crit_chance`, `crit_chance_after`) de `damage_hits.py::_run_hits`, alimente par les trois
    vecteurs qui appellent `_crit_params` **avant** l'event (coup 0) puis **apres** (coups 1+).
    RESIDU qui, lui, RESTE : les triggers AFTER-HIT sont toujours appliques post-attaque par le
    port, la ou `EvaluateAfterHitTriggers` court en fin de CHAQUE coup -- axe separe, aucun
    consommateur crit connu (mesure #522-r1 : le registre ne porte qu'UN ecouteur de `On(6)/On(7)`).

**ORDRE réduction↔tirage (CORRIGÉ — confirmé live 18/18 coups, 3 seeds, necroDestroyer 6h**
**mêlée → eldarFarseer)** : la réduction perçage/armure/modifiers est appliquée aux BORNES
du `HitDamage` D'ABORD (le struct porte la plage RÉDUITE `[reduce(base−delta), reduce(base+delta)]`),
PUIS `GetDamage` tire DANS cette plage réduite : `next_internal(min_réduit, max_réduit+1)`.
⚠ PAS « spread brut puis réduit » : les deux donnent la MÊME plage totale, mais des valeurs
par coup DIFFÉRENTES (l'offset RNG ne dépend que de la LARGEUR de plage, qui diffère entre
brut et réduit). `delta = Round(base × DamageSpreadPercentage/100)` (cf.
`engine/services/damage_calculations.py`).
"""

from __future__ import annotations

from typing import Optional

from ...services.damage_combat import BlockSource
from ...services.damage_config import resolve_spread_pct
from ...entities.damage_trait import DamageTrait
from ...entities.damage_profile_type import DamageProfileType
from ...entities.damage_reason import DamageReason
from ...entities.stats import StatType
from ..prng import IntBasedMersenneTwister
from ..state import State
from ..components import (UnitComponent, ShieldComponent, UnitFlagsComponent, HealthComponent,
                          PendingDamage,
                          StatsComponent, unit_is_dead, can_be_overkilled, unit_prevents_overkill)
from ...services.trait_damage_limits import unit_is_overkill
from ...entities.effects import (crit_chance_bonus_from_effects, crit_damage_bonus_from_effects,
                                 defender_effect_block_sources)
from .damage_hits import HitDamage, _DamageHitsMixin
from .damage_ops import _DamageOpsMixin
from ...entities.effects import board_effect_carriers
from ...entities.effects.loki.obsessive_annunciation import (   # #954 -- un seul foyer de nommage
    CTX_ADJACENT_ENEMY_IDS_OF as _OA_CTX_ADJ_ENEMY_IDS)
from ...entities.traits.unit_trait import entity_trait_names
# `has_trait` / `UnitTrait` : le second bras du gate `PreventRevive` de
# `KillUnitOperation$$Execute` est `UnitExtensions.IsSteppable(killed)` = `HasTrait(0x1b)`.
from ...entities.traits.unit_trait import UnitTrait, has_trait
from ..components import (HealthComponent, OwnerComponent, StatsComponent, UnitComponent,
                                  adjacent_enemies_count,
                                  adjacent_enemy_ids,
                                  adjacent_friendly_mechanical_units_count,
                                  adjacent_friendly_summons_and_decoys_count,
                                  adjacent_mechanical_friends_count,
                                  adjacent_summons_count,
                                  debuffed_units_in_range_count)
from ..components import UnitComponent, unit_state_for_effects
from ..components import is_alive_and_not_fled
from ..components import unit_has_moved, unit_tiles_moved_this_turn
from ..components import register_attack_made
from ..components import register_defeated_unit           # #951 (KillUnitOperation$$Execute+0x8b9)
from ..damage_model import _unit_gameconfig
from ..damage_model import battle_query_is_charging
#: FORME B : `probe_429r1r1r1_ability_attack_dead_target.py` substitue
#: `active_ability.is_dead_unit_and_not_allowed_by_ability` ; hisse en forme A le stub serait
#: INERTE (gisement mesure de la famille #429-r1). L'import de module relit a l'appel.
from . import active_ability as _active_ability
from .left_over_damage import record_left_over_damages
from .minimal_health import record_attacked
from .refresh_effects import refresh_stat_modifier_effects
from ...entities.kill_unit_step import KillUnitStep
from .remove_effects import remove_effects_operation
from ...dsl.event_trigger_type import EventTriggerType
from engine.entities.effects.loki.supa_cybork_body import CTX_COUNT_OF as _CTX_ADJACENT_ENEMIES_OF   # #1042-r5
from engine.entities.effects.loki.nether_realm_casket import CTX_COUNT_OF as _CTX_ADJACENT_FRIENDLY_MECHANICAL_UNITS_OF   # #1042-r5
from engine.entities.effects.loki.amulet_of_the_voidwyrm import CTX_COUNT_OF as _CTX_ADJACENT_FRIENDLY_SUMMONS_AND_DECOYS_OF   # #1042-r5
from engine.entities.effects.loki.kardiocore_galvanus import CTX_COUNT_OF as _CTX_ADJACENT_MECHANICAL_FRIENDS_OF   # #1042-r5
from engine.entities.effects.loki.maw_claws_of_thyrax import CTX_COUNT_OF as _CTX_ADJACENT_SUMMONS_OF   # #1042-r5
from engine.entities.effects.loki.intoxicating_elixir import CTX_COUNT_OF as _CTX_DEBUFFED_UNITS_IN_RANGE_OF   # #1042-r5
from engine.entities.effects.ctx_keys import CTX_TERTIARY_ABILITY_STATE_OF as _CTX_TERTIARY_ABILITY_STATE_OF   # #1042-r5
from engine.entities.effects.loki.intoxicating_elixir import CTX_HEALTH_OF as _CTX_UNIT_HEALTH_OF   # #1042-r5


def _kill_unit_remove_effects(state: State, dead_id: int, step: int) -> list:
    """`IdunBattle.Operations.KillUnitOperation$$RemoveEffects(killed, step)` — l'adaptateur natif
    (emballe `step` dans un `Nullable<KillUnitStep>`, met le second champ d'options a 0, appelle le
    slot 0x5a de `Core.Services.OperationProcessor`). Le travail vit dans
    `operations/remove_effects.py` (`RemoveEffectsOperation$$Execute` + `RemoveEffectOperation$$
    Execute`), foyer partage avec la feuille DSL `RemoveEffect`."""
    return remove_effects_operation(state, int(dead_id), step=int(step))


def _health_of(state: State, unit_id) -> tuple:
    """`(GetStat(5 = Health, CURRENT), GetStat(5, MAXIMUM))` d'une entite, pour les noeuds
    `HealthPctIsBelowOrEqual(<selecteur>, <pct>)` du canal CRIT.

    Substrat UNIQUE : le `HealthComponent` (`hp` / `hp_max`), le MEME que les cles `hp` / `max_hp`
    du `unit_state` que lisent les `is_active` a seuil de vie (`VisionsOfHeresy`,
    `HammerOfWrath_ConditionalDamage`, `AnvilShield`) -- deux axes qui lisent la meme grandeur ne
    peuvent donc pas diverger.

    TRI-ETAT : `(None, None)` = **non mesure** (entite absente ou sans `HealthComponent`), jamais
    un zero invente -- un `hp = 0` ferait passer pour « au seuil » une unite dont on ignore la vie.
    Consommateur porte : `IntoxicatingElixirEffect._health_multiplier`."""
    if unit_id is None:
        return (None, None)
    e = state.entities.get(int(unit_id))
    hc = e.get_component(HealthComponent) if e is not None else None
    if hc is None:
        return (None, None)
    return (hc.hp, hc.hp_max)


class _PreDamageTakenSink:
    """#1020-r4 -- le chokepoint `On(0x39 = EventTriggerType.PreDamageTaken)` d'UN COUP, sous une
    forme que `damage_hits._run_hits` peut appeler A SA POSITION dans le flux PRNG, et qui PORTE
    son propre cumul.

    MEME CORPS que `AttackDamageOperation._pre_damage_taken_per_hit` (pose du pending -> gate
    `0 < DamageAppliedResult$$get_Damage` -> emission -> relecture `GetValueOrDefault` -> purge),
    mais joue coup par coup DANS la boucle au lieu d'etre re-deroule apres elle.

    ⚠ **LE CUMUL VIT ICI, PAS DANS LE RETOUR DE `_run_hits`.** Le publier sous une cle du dict rendu
    par le canal ELARGIT son CONTRAT DE SORTIE : toute substitution de `_run_hits` restee en arriere
    leve alors `KeyError`. Ce n'est pas theorique -- c'est la cause EXACTE des deux rouges de la
    premiere version de cette tranche, tous deux sur `additional_hits` :
    `test_failed_block_attack_scope_offline.py::test_execute_additional_hits_CHAINE_l_etat_de_groupe_en_groupe`
    et `test_additional_hits_variant_signatures_offline.py::test_toute_substitution_expose_le_contrat_de_SORTIE`,
    dont le stub rend deliberement le contrat COMPLET et documente du canal. Le cumul appartient a
    son PRODUCTEUR : l'appelant possede deja le sink, il n'a aucun besoin de le faire transiter.

    `isFirstDamagingHit` (`DamageAppliedResult+0x18`) reste PROPRE AU COUP : l'etat vit sur
    l'instance et tombe au premier coup qui emet, exactement comme dans la version par-groupe.

    `__call__(health, shield)` rend `(kept_health, kept_shield)`, ou `None` si le pending a ete
    CONSOMME (coup transfere). `cumul()` rend `(kept_health, kept_shield, transferts)` -- et
    `(0, 0, 0)` quand aucun coup n'a atteint le point d'ecriture, ce qui est exactement juste :
    zero coup pose => rien de garde, rien de transfere."""
    __slots__ = ("state", "attacker_id", "target_id", "thc", "profile", "source_ability",
                 "first", "kept_health", "kept_shield", "transfers", "calls")

    def __init__(self, state, attacker_id, target_id, thc, profile, is_first_damaging_hit,
                 source_ability=None):
        self.state, self.attacker_id, self.target_id = state, attacker_id, target_id
        self.thc, self.profile = thc, profile
        # #1020-r3 : le canal `AbilityEntities+0x98` (`DamageAppliedResult+0x40`), que les
        # `TriggeringAbilityIs` LISENT. Il vit sur le sink parce que l'emission a migre dans la
        # boucle : le laisser au seul chokepoint de groupe le rendrait aveugle pour les QUATRE
        # vecteurs qui ont une decomposition par coup -- c'est-a-dire pour tous ceux qui comptent.
        self.source_ability = source_ability
        self.first = bool(is_first_damaging_hit)
        self.kept_health = self.kept_shield = self.transfers = self.calls = 0

    def __call__(self, health: int, shield: int):
        # lazy : cycle damage<->triggers. Forme MODULE (comme `_apply_damage_pipeline`) :
        # l'attribut est relu a l'appel, donc une substitution posee sur `dispatch.attack` mord.
        from .triggers.dispatch import attack as attack_dispatch
        self.calls += 1
        thc = self.thc
        # `healthComp[+0x64] = Nullable<DamageAppliedResult>(result)` -- AVANT toute emission.
        thc.pending_damage = PendingDamage(self.profile, int(health), int(shield))
        if int(health) + int(shield) > 0:      # `0 < DamageAppliedResult.get_Damage(&result)`
            attack_dispatch.pre_damage_taken_triggers(
                self.state, self.attacker_id, self.target_id, profile=self.profile,
                is_first_damaging_hit=self.first, source_ability=self.source_ability)
            self.first = False                 # `+0x18` du coup SUIVANT : plus le premier damageant
        after = thc.pending_damage             # `GetValueOrDefault` : Nullable vide -> struct ZERO
        thc.pending_damage = None              # portee = `Execute` : le pending ne survit pas
        if after is None:
            self.transfers += 1                # pending CONSOMME -> coup transfere
            return None
        self.kept_health += int(after.health)
        self.kept_shield += int(after.shield)
        return int(after.health), int(after.shield)

    def cumul(self) -> tuple:
        return (self.kept_health, self.kept_shield, self.transfers)


class AttackDamageOperation(_DamageOpsMixin, _DamageHitsMixin):
    """`IdunBattle.Operations.AttackDamageOperation` IdunBattle.Operations.AttackDamageOperation$$Execute (squelette fidèle).

    Palier 1 : seul le TIRAGE par coup (`execute_hit`) est porté+validé. Les paliers
    suivants (crit, block, réduction, triggers after-hit) sont marqués TODO avec leur
    VA, en miroir 1:1 de la structure native (cf. en-tête de module)."""
    __slots__ = ()

    @staticmethod
    def get_attack_hits(default_hits: int = 1) -> int:
        """`IdunBattle.Operations.AttackDamageOperation$$GetAttackHits — nb de coups. Mono-coup → 1 (sans requête, donc
        sans RNG avant le 1er coup). Le cas multi-coups (requête composant 0xb5) =
        palier ultérieur."""
        return default_hits

    @staticmethod
    def execute_hit(hit: HitDamage, rng: IntBasedMersenneTwister,
                    use_midpoint: bool = False) -> int:
        """`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit — PALIER 1 : renvoie le dégât de BASE tiré du coup
        (`HitDamage.GetDamage`). Crit (composant 0xb), block (composant 10), réduction
        perçage/armure et EvaluateAfterHitTriggers = paliers 2-4 (non portés ici)."""
        return hit.get_damage(rng, use_midpoint)

    @staticmethod
    def _damage_source_ability(current_ability, triggering_ability):
        """`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules$$GetDamageSourceAbility
        (currentAbility, triggeringAbility)` (MIRROR du decompile) :

            if (currentAbility.<Nullable<ActiveAbilityType>>.HasValue
                && ActiveAbility.IsRegularAttack(currentAbility.Value)
                && triggeringAbility.HasValue)   return triggeringAbility.Value
            return currentAbility

        = « une ATTAQUE REGULIERE declenchee par autre chose s'attribue a son DECLENCHEUR ». Appelee
        PAR COUP par `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` et
        `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit` pour renseigner l'`AbilityOrEffect`
        de la `DamageSource` du coup -- c'est LUI que `HasDeathReasonTrigger` compare.

        Consequence load-bearing : un tir d'OVERWATCH (`Overwatch_AutoAttackEffect$$GetAttackBehaviour`
        = `UseActiveAbility(NormalAttack)`, donc une attaque REGULIERE, declenchee par l'effet
        `Overwatch_AutoAttack` 1009) s'enregistre comme venant de **1009**, pas de l'attaque normale.

        Le test natif est `IsRegularAttack` sur l'`ActiveAbilityType` CONCRET de l'attaque normale
        (per-unite : 69, 1030, ...). Le port ne materialise PAS cet id sur la voie normale : il y
        thread le marqueur de KIND `0x3f5` (cf. `abilities/attack_type.py`, 2e branche de
        `DSLFactory$$IsNormalAttack`). On teste donc la DISJONCTION `is_normal_attack` = « id concret
        d'attaque reguliere OU marqueur de kind » -- meme extension sur les deux voies du port."""
        from ..abilities.attack_type import is_normal_attack   # lazy : cycle damage<->abilities
        if current_ability is not None and is_normal_attack(current_ability) \
                and triggering_ability is not None:
            return int(triggering_ability)
        return None if current_ability is None else int(current_ability)

    @staticmethod
    def _record_death_reason(state: State, dying_id: int, killer_id: Optional[int],
                             source_ability,
                             damage_reason: int = int(DamageReason.Ability)) -> None:
        """`IdunBattle.Operations.KillUnitOperation$$RecordDeathReason(killer, killed,
        killedUnitComponent, deathReason)` : ecrit le `Nullable<DamageSource>` @`UnitComponent+0x108`
        de la victime. Appelee par `KillUnitOperation$$Execute` **AVANT** l'emission d'`On(PreUnitDeath
        = 1)` (ordre lu au decompile) -- c'est ce qui rend le champ lisible par les
        `HasDeathReasonTrigger` de ce vecteur.

        COLLAPSE ASSUME : le natif tient DEUX morceaux (le `RecordDeathReason` ci-dessus pose
        killer + `DamageReason` ; l'`AbilityOrEffect` vient de la `DamageSource` du coup letal,
        construite par `A*DamageOperation$$ExecuteHit` via `GetDamageSourceAbility` et transportee
        dans le `DamageAppliedResult`). Le port n'a pas ce transport : il FUSIONNE les deux au moment
        du kill, avec l'`AbilityOrEffect` deja resolue par `_damage_source_ability`.

        `damage_reason` = le 5e argument natif, LU par `KillUnitOperation$$Execute` dans
        `options+0x00` (`KillUnitOperationOptions`) et pousse tel quel :

            uVar18   = *(options + 0x40)                       # les 8 octets +0x40..+0x47
            cStack_304 = (char)(uVar18 >> 0x20)                # = options+0x44
            if (cStack_304 != '\\0')
                RecordDeathReason(this, killer, killed, uc, *(undefined4 *)options)   # = options+0x00

        Il vaut donc `DamageReason.Ability` (0) pour toute mort par DEGAT (`ForDefault` met la struct
        entiere a zero) et **`DamageReason.Steppable` (2)** pour le CRUSH d'un `Steppable`
        (`ForSteppable` : `+0x00 = 2`, `+0x44 = +0x45 = 1`, `+0x46 = 0`) -- ce que
        `movement.py::_kill_steppable_units` passe desormais (#462-r4b-r1-r1-r1-r1-c-r3-r1-r2).
        `DamageReason.Knockback` (1) n'a aucun call-site porte."""
        uc = tgt_uc = None
        e = state.get_entity(int(dying_id))
        if e is not None:
            tgt_uc = e.get_component(UnitComponent)
        uc = tgt_uc
        if uc is None:
            return
        uc.death_source = (None if killer_id is None else int(killer_id), int(damage_reason),
                           None if source_ability is None else int(source_ability))

    @staticmethod
    def _did_overkill(state: State, target_id: int, tgt, hp_before, damage,
                      hits_result=None, is_force_overkill: bool = False) -> bool:
        """`didOverkill` du chemin COMBAT — RE-JOUE la sequence des coups, parce que le natif appelle
        `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` (surcharge d'INSTANCE, inlinee dans
        `...$$CalculateDamageOperation`) **UNE FOIS PAR COUP**, et que
        `IdunBattle.Operations.ApplyDamageOperation$$Execute+0x17d5` pose `UnitFlag.Overkilled (8)` des
        qu'UN coup rend vrai. Deux des trois arguments qui decident VARIENT d'un coup a l'autre :

            IsOverkill(target, hitDamage       = degat SANTE de CE coup,
                               deniedDamage    = degat REFUSE par l'etage limites aux coups PRECEDENTS,
                               isCritical      = crit de CE coup,
                               isForceOverkill = flag d'attaque (constant sur l'attaque),
                               targetHealthBeforeAttack = PV au debut de l'attaque,
                               minimumHealth   = plancher Hypersensory de la cible)

        et la surcharge d'instance re-agrege elle-meme le degat des coups precedents
        (`hitDamage += targetHealthBeforeAttack.Value - currentHealth`) : l'argument compare est donc le
        CUMUL. On boucle ici sur `(degat sante du coup, denied AVANT le coup, crit du coup)`.

        `hits_result` = le dict rendu par `_run_hits` (`per_hit_health` / `crits` / `denied_before`).
        Absent (DoT, knockback, coups additionnels) -> degenerescence en UN coup non-critique sans
        denied : strictement l'ancien comportement.

        #462-r4e-o-r1 -- FOYER UNIQUE : quand `_run_hits` a pu evaluer la porte (PV captes), c'est
        SON verdict qui fait foi. Non parce que le re-jeu ci-dessous serait faux -- il ne l'est
        pas : la surcharge d'instance d'`IdunBattle.Core.Services.DamagePrediction$$IsOverkill`
        accumule `(targetHealthBeforeAttack - GetStat(Health)) + healthComponent@+0x24`, or ces deux
        termes valent respectivement le degat APPLIQUE et le degat GASPILLE des coups precedents :
        leur somme EST le degat DEMANDE cumule, exactement ce que ce re-jeu calcule. Mais `_run_hits`
        le mesure a la forme NATIVE, donc il voit ce que ce re-jeu ne peut pas voir : un `+0x24`
        HERITE d'une attaque anterieure (le compteur n'est jamais remis a zero, cf.
        `HealthComponent.over_reduce`) et un SOIN intercale. Le re-jeu reste le repli des appelants
        sans decomposition (DoT, knockback, groupes de coups additionnels)."""
        cbo = can_be_overkilled(tgt)
        if not cbo or hp_before is None or damage is None:
            return False
        if hits_result is not None and hits_result.get("overkilled") is not None:
            return bool(hits_result["overkilled"])
        prv = unit_prevents_overkill(state, target_id)
        thc = tgt.get_component(HealthComponent) if tgt is not None else None
        floor = getattr(thc, "minimal_health", None) if thc is not None else None
        seq = None
        if hits_result:
            hh = hits_result.get("per_hit_health") or []
            cr = hits_result.get("crits") or []
            db = hits_result.get("denied_before") or []
            if hh:
                seq = [(int(hh[i]),
                        int(db[i]) if i < len(db) else 0,
                        bool(cr[i]) if i < len(cr) else False) for i in range(len(hh))]
        if not seq:
            seq = [(int(damage), 0, False)]
        cum = 0
        for health_dmg, denied_before, crit in seq:
            cum += health_dmg
            if unit_is_overkill(hp_before, cum, can_be_overkilled=cbo,
                                denied_damage=denied_before, prevent_overkill=prv,
                                is_critical=crit, is_force_overkill=is_force_overkill,
                                target_minimum_health=floor):
                return True
        return False

    @staticmethod
    def _fire_death_if_killed(state: State, target_id: int, attacker_id: int,
                             hp_before, hp_after, tgt, damage=None,
                             source_ability=None, hits_result=None,
                             is_force_overkill: bool = False) -> Optional[list]:
        """Si le coup a fait passer la cible de >0 à 0 PV → elle meurt : marque `alive=False`,
        ENREGISTRE le kill puis ENQUEUE la mort, et draine la file. `damage` = dégât LÉTAL total du
        coup (pour le flag OVERKILL = `dmg >= 2*PV`). No-op si pas de mort.

        **DEUX OPERATIONS NATIVES, PAS UNE (case-haze-ord)** — le corps ci-dessous est
        `IdunBattle.Operations.RecordKillOperation$$Execute` (flag `Overkilled`, `RecordDeathReason`,
        `On(PendingDeathAdded = 3)`, `IdunBattle.Core.MatchState$$AddDeath`) ; l'APPLICATION de la mort
        vit dans `_kill_unit_operation` (`IdunBattle.Operations.KillUnitOperation$$Execute`) et n'est
        atteinte que par le DRAIN `_verify_deaths`
        (`IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths`). Le drain est NON REENTRANT : une
        mort causee PENDANT une sequence de mort (death-nova, riposte `FinalJustice`, report
        `HazeOfCorruption`) est traitee APRES elle, jamais en son milieu. Au premier appel de la pile,
        enqueue et drain restent consecutifs -> comportement inchange pour tout appelant top-level.

        ORDRE DES ÉVÉNEMENTS — RE TRANCHÉE au décompilé (2026-07-25). L'émetteur réel est
        **`KillUnitOperation$$IdunBattle.Operations.KillUnitOperation$$Execute** (et NON `ApplyDamageOperation$$IdunBattle.Operations.ApplyDamageOperation$$Execute, qui
        n'émet que 0x3a/0xf/0x10, ni les lambdas de `InputMessageProcessor$$IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths, qui ne
        font qu'appeler `OperationProcessor$$Core.Services.OperationProcessor$$KillUnit). Ordre des INSTRUCTIONS dans
        `KillUnitOperation$$Execute` (adresses de retour des call-sites de dispatch) :

            On(1  = PreUnitDeath)    ret IdunBattle.Operations.KillUnitOperation$$Execute+0x7dc   <- AVANT la garde `if (*pcVar21 == '\\0')` @IdunBattle.Operations.KillUnitOperation$$Execute+0x82e
            On(2  = PreUnitDeath_2)  ret IdunBattle.Operations.KillUnitOperation$$Execute+0x97a   <- sous la garde
            On(0  = UnitDeath)       ret IdunBattle.Operations.KillUnitOperation$$Execute+0xdf9   (aucun consommateur porté)
            On(54 = UnitDefeated)    ret IdunBattle.Operations.KillUnitOperation$$Execute+0xeac
            On(53 = PostUnitKill)    ret IdunBattle.Operations.KillUnitOperation$$Execute+0x102c   (aucun consommateur porté)

        => **1 -> 2 -> 55** est CONFIRMÉ (auparavant une simple inférence par numérotation). Les 3 vecteurs
        portés sont donc émis dans cet ordre ci-dessous.

        - `On(PreUnitDeath)` : accumulations ActOfFaith (allié Imperial qui meurt/tue), FinalJustice (riposte du
          mourant, gate overkill dans son BEHAVIOUR), TaintedNarthecium (revive).
        - `On(PreUnitDeath_2)` : famille DEATH-NOVA (`Explodes` 1008->1021, `PutridExplosion` 2028->1074) — `IdunBattleLogic.Entities.DSLFactory$$OnPreDeath2. Les deux passent `a=1` => **AUCUN gate overkill** : la nova part même en overkill.
        - `On(UnitDeath)` : TerrifyingCrescendo branche OVERKILL (`On(UnitDeath) & OwnerIsActor & TargetIsOverkilled`).
        - `On(UnitDefeated)` : Ambush_SummonAbility (mort -> decoy) + `turn_defeated`.

        **SÉMANTIQUE DE LA GARDE @IdunBattle.Operations.KillUnitOperation$$Execute+0x82e — TRANCHÉE (case-89 volet C, 2026-07-25).** Elle lit le
        `hasValue` du `Nullable<ReviveData>` @`UnitComponent + 0xa8` (même champ, même helper
        `thunk_FUN_1801f3000(ptr, <fieldInfo hasValue>)`, que `IdunBattle.Operations.ReviveUnitOperation$$Execute`
        qui le DRAINE puis le remet à 0, et que `IdunBattle.Entities.Behaviours.ReviveBehaviour$$Execute` qui l'ÉCRIT) :

            if (!unitComponent.PendingRevive.HasValue) { ...tout le reste de la mort... }

        ⇒ **un REVIVE posé pendant `On(PreUnitDeath)` COURT-CIRCUITE `On(PreUnitDeath_2)`, `On(UnitDeath)`, `On(UnitDefeated)`, `On(PostUnitKill)`**, ainsi
        que `RegisterDefeatedUnit`, `Remove(flag 0xf)` / `Add(flag 6)` et `RemoveEffects`. Vérifié à la
        profondeur d'accolades du décompilé : `On(PreUnitDeath)` est au niveau 7, les quatre autres au niveau 9,
        et AUCUN de ces cinq vecteurs n'a de contrepartie dans la branche `else`.

        ⚠ **IL Y A BIEN UN `else`, ET C'EST LUI QUI APPLIQUE LE REVIVE (#477-r24).** La branche
        `pendingRevive.HasValue == true` appelle `Core.Services.OperationProcessor$$ReviveUnit(killed)`
        -- DANS `IdunBattle.Operations.KillUnitOperation$$Execute` MEME, pas dans une phase ; les deux branches
        purgent ensuite les 9 qwords `+0xa8 .. +0xe8`. Le port applique donc la garde ci-dessous
        (`kill_unit_revive_gate`), qui applique aussi le revive : c'est le mirror de cette branche
        `else`, PAS d'un drain de phase. **`RunPhase(PhaseType.ProcessRemovals /*0xd*/)` d'
        `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` draine les RETRAITS** (lambda
        `<VerifyRemovedUnits>b__0`), et aucun `IdunBattle.Core.PhaseType` ne nomme un revive --
        cf. `engine/streams/phase_type.py` et l'entete de `revive.py`."""
        if hp_before is None or hp_before <= 0 or hp_after != 0:
            return None
        uc = tgt.get_component(UnitComponent) if tgt is not None else None
        if uc is not None:
            uc.alive = False
        from .triggers.dispatch.move_death import pending_death_added_triggers
        # #178 — le `didOverkill` du chemin COMBAT est la surcharge d'INSTANCE de
        # `IdunBattle.Core.Services.DamagePrediction$$IsOverkill`, inlinee par
        # `IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation` : elle applique DEUX gates
        # d'unite AVANT la formule (`CanBeOverkilled` = pas de trait Steppable, et `HasFlag(target, 0x13)`
        # = `UnitFlag.PreventOverkill`). Le port appelait ici un doublon 2-args qui les avait perdus : il
        # declarait « overkill » des `dmg >= 2*PV`, y compris sur une cible que le natif refuse d'overkiller.
        # #R33 — les TROIS champs restants du `DealDamageInfo` natif descendent maintenant jusqu'ici :
        # `isCritical` (@+0x1c), `isForceOverkill` (@+0x2c) et `deniedDamage` (@+0x18). Le premier est
        # le plus lourd : `IsOverkill` RENVOIE `isCritical` dans le cas « letal mais sous le seuil »,
        # donc tout crit qui tue sans doubler les PV EST un overkill -- le port, qui passait 0 en dur,
        # ne marquait jamais ces morts-la. cf. `_did_overkill`.
        overkill = AttackDamageOperation._did_overkill(
            state, target_id, tgt, hp_before, damage,
            hits_result=hits_result, is_force_overkill=is_force_overkill)
        # `UnitFlag.Overkilled (8)` — le natif le pose dans `IdunBattle.Operations.ApplyDamageOperation$$
        # Execute+0x17d5` (`if (result.didOverkill) UnitFlagsComponent.Add(target, 8)` : le `mov edx,8`
        # precede immediatement le call a `IdunBattle.Entities.Components.UnitFlagsComponent$$Add`), donc
        # AVANT le kill. Cote port l'overkill n'est resolu qu'ici -> on pose le flag ICI, en tete de la
        # sequence de mort et AVANT tout vecteur `On(...)`. DIVERGENCE D'ORDRE NOMMEE : un consommateur
        # natif qui lirait le flag ENTRE l'application du degat et le kill le verrait plus tot ; aucun
        # consommateur porte n'est dans cette fenetre (`DoomSiren` lit le flag APRES tout son volet
        # d'attaque). DIVERGENCE DE GRANULARITE NOMMEE (pre-existante) : le natif calcule `didOverkill`
        # PAR COUP dans `CalculateDamageOperation` ; le port n'a qu'un chokepoint PAR ATTAQUE
        # (`_apply_damage_pipeline`), donc `hp_before`/`damage` sont ceux de l'attaque entiere.
        if overkill:
            fl = tgt.get_component(UnitFlagsComponent) if tgt is not None else None
            if fl is None and tgt is not None:
                fl = tgt.add_component(UnitFlagsComponent())
            if fl is not None:
                fl.add(UnitFlagsComponent.OVERKILLED)
        # `KillUnitOperation$$RecordDeathReason` : la `DamageSource` de la victime est enregistree
        # AVANT `On(PreUnitDeath)` -- c'est la seule raison pour laquelle `HasDeathReason` peut matcher sur ce
        # vecteur (`AReactivateOverwatchEffect$$LegitDeathReasons`, #114).
        AttackDamageOperation._record_death_reason(state, target_id, attacker_id, source_ability)
        # `On(PendingDeathAdded = 3)` — emis par `IdunBattle.Operations.RecordKillOperation$$Execute`
        # (`Core.Services.OperationProcessor$$RecordKill`), qui ENREGISTRE le kill puis ENQUEUE la mort
        # (`MatchState.AddDeath`). La file n'est drainee que plus tard par
        # `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` -> `KillUnitOperation$$Execute`, qui
        # emet `On(PreUnitDeath)` : `On(PendingDeathAdded)` PRECEDE donc strictement `On(PreUnitDeath)` pour une meme mort, d'ou sa place ici.
        # {acteur = caster = le TUEUR, cible = la VICTIME} + le `TriggeringAbility` courant.
        # Consommateur porte : `FuelledByFury_ReviveAbility` (Titus se revive quand SA riposte
        # FinalJustice tue) -- et c'est ce revive-la qui, pose sur Titus pendant SON `On(PreUnitDeath)`, fait
        # ECHOUER la garde `kill_unit_revive_gate` plus bas et ANNULE sa propre mort.
        out = pending_death_added_triggers(state, target_id, attacker_id)
        # `IdunBattle.Core.MatchState$$AddDeath(killer, killed, killTrigger, attackTrigger,
        # AttackRangeType)` : la mort est ENQUEUEE, pas appliquee.
        # Le 5e argument (#951-r1) est calcule ICI et pas au drain, parce que c'est ICI que le natif
        # le calcule : `IdunBattle.Operations.ApplyDamageOperation$$Execute` appelle le slot 4
        # d'`IBattleQuery` (`GetAttackRangeType`) avec l'`AbilityOrEffect` de la `DamageSource` du
        # coup (`DamageAppliedResult+0x40` = `source_ability` cote port), la SOURCE du degat en
        # caster, sa position, et la VICTIME -- puis pose le resultat dans le `KillUnitContext@+0x38`
        # que `RecordKillOperation` relaie tel quel. Calculer au drain lirait la position du tueur
        # APRES d'eventuels deplacements du vecteur de mort.
        from .triggers.base import _attack_range_type       # lazy : cycle damage<->triggers
        AttackDamageOperation._add_death(
            state, target_id, attacker_id, overkill,
            attack_range_type=_attack_range_type(state, source_ability, attacker_id, target_id))
        # `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` : le DRAIN. No-op si un drain est
        # deja en cours (cette mort-ci sera prise par son tour de boucle).
        return out + AttackDamageOperation._verify_deaths(state)

    @staticmethod
    def _add_death(state: State, dying_id: int, killer_id, overkill: bool,
                   attack_range_type: Optional[str] = None) -> None:
        """`IdunBattle.Core.MatchState$$AddDeath(killer, killed, killTrigger, attackTrigger,
        AttackRangeType)` -- l'ENQUEUE, seul effet « mort » de
        `IdunBattle.Operations.RecordKillOperation$$Execute` (qui, autour, pose
        `UnitFlag.PendingDeath = 0xf`, incremente les compteurs de kills du `PlayerComponent` et publie
        `On(PendingDeathAdded = 3)` -- residus deja nommes pour les deux premiers).

        Le 3e argument, `killTrigger`, est LU DANS le `KillUnitContext` a CET instant
        (`RecordKillOperation$$Execute` le recopie tel quel dans l'appel) : c'est lui que
        `IdunBattle.Operations.KillUnitOperation$$Execute` rejoue ensuite dans le champ
        `TriggeringAbility` (`AbilityEntities+0x98`) des evenements de mort, donc lui que comparent
        `IdunBattleLogic.Entities.DSLFactory$$TriggeringAbilityIs` / `$$TriggeringEffectIs`.
        Cote port on le CAPTURE ici depuis `state.triggering_ability` (le canal `+0x60` AMBIANT --
        approximation deja nommee par `case-292` : le natif lit le `KillUnitContext`, pas
        `CurrentAbility`, et les deux coincident dans tous les regimes portes), et `_verify_deaths`
        le REPOSE sur `state.trigger_ability_type` (le canal `+0x98`) le temps du drain -- **pas** sur
        `state.triggering_ability`, que `KillUnitOperation` laisse VIDE (#301).
        Sans cette capture, une mort causee DANS le behaviour d'une triggered-ability (le report
        `HazeOfCorruption` 1077) serait drainee hors de ce behaviour et perdrait son declencheur --
        c'est-a-dire exactement le gate anti-chaine que case-haze-bonded a etabli.

        `attack_range_type` (#951-r1) -- le **5e argument natif**, longtemps cru inaccessible. La
        chaine est LUE de bout en bout, et elle passe par TROIS fonctions :

            IdunBattle.Operations.ApplyDamageOperation$$Execute
                rt = BattleQuery.<slot 4 = GetAttackRangeType>(
                         ability        = DamageAppliedResult+0x40,      # = `source_ability`
                         caster         = la SOURCE du degat,
                         casterPosition = EntityExtensions$$GetUnitPosition(source),
                         target         = la VICTIME)
                ... pose `rt` dans le `KillUnitContext@+0x38` ...
            IdunBattle.Operations.RecordKillOperation$$Execute
                if (context+0x38 .HasValue) rangeType = context+0x38            # <- CE cas
                else                        rangeType = <meme slot 4, sur le killTrigger>
                matchState.<slot 1 = AddDeath>(killer, killed, killTrigger, attackTrigger,
                                               Nullable<AttackRangeType>(rangeType))
            lambda `...u003CVerifyDeathsu003Eb__0` : recopie l'entree dans `KillUnitOptions+0x3c`
            IdunBattle.Operations.KillUnitOperation$$Execute
                inMelee = rangeType.HasValue && rangeType.GetValueOrDefault() == Melee(1)
                          # LU aux octets : `local_378[0] = local_370[0] == 1 & *pbVar22`

        ⚠ C'est le MEME booleen des DEUX cotes : `KillUnitOperation` l'ecrit dans
        `UnitComponent+0x178` de la VICTIME (`DefeatedByMeleeAttack`) **puis** le passe en `inMelee`
        a `RegisterDefeatedUnit` sur le TUEUR. Le port a deja la face SEEDING de ce couple
        (`snapshot._load_death_sources` lit `decisionView.units[].defeatedByMelee`) ; ce canal-ci
        est la face SIMULATION, et les deux ecrivent desormais la meme chose.

        `None` = l'appelant ne l'a pas mesure. Ce n'est PAS une degradation sur les voies qui le
        laissent ainsi : `KillUnitOperationOptions$$ForSteppable` (crush) et `$$ForDefault`
        (feuille DSL `Kill`) laissent `+0x3c` a ZERO, donc le `Nullable` y est VIDE cote natif
        aussi, et `inMelee` y vaut FAUX -- la branche par defaut, pas un choix du port.

        Gate `UnitFlagsComponent.Has(dying, 6)` du natif (« deja retire ») : cote port le gate
        equivalent est en amont (`hp_before > 0 and hp_after == 0` dans `_fire_death_if_killed`, qu'une
        cible a 0 PV ne repasse jamais) ; on double d'une deduplication sur la file, parce qu'entre
        l'enqueue et le drain la cible reste JOIGNABLE par d'autres coups."""
        q = state.pending_deaths
        if any(int(d[0]) == int(dying_id) for d in q):
            return
        q.append((int(dying_id), None if killer_id is None else int(killer_id), bool(overkill),
                  state.triggering_ability, attack_range_type))

    @staticmethod
    def _verify_deaths(state: State) -> list:
        """`IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` -- le DRAIN de la file remplie par
        `MatchState.AddDeath` : `RunPhase(PhaseType.ProcessDeaths /*0xc*/)` -> lambda `IdunBattle.Messages.InputMessageProcessor.
        u003Cu003Ec__DisplayClass49_0$$u003CVerifyDeathsu003Eb__0` -> `Core.Services.
        OperationProcessor$$KillUnit` -> `IdunBattle.Operations.KillUnitOperation$$Execute`, **une mort
        a la fois, tant que la file n'est pas vide**.

        NON REENTRANT (case-haze-ord). Une mort ENQUEUEE pendant un drain est traitee au tour de boucle
        SUIVANT -- jamais au milieu du `KillUnitOperation` en cours, ni au milieu du behaviour qui l'a
        causee. C'est ce qui separe le port du natif au regime OVERKILL : les **N** feuilles
        `AttackDamage` d'un `IdunBattle.Entities.Behaviours.AttackBehaviour` UNIQUE (le
        `Attack(bonded, Owner@0x148, N x AttackDamage)` de
        `IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$
        CreateTargetTriggerBehaviour`) partent TOUTES avant que la mort de leur cible ne soit traitee,
        donc la `List<LeftOverDamage>` que lit le bond SUIVANT est COMPLETE. Le port drainait a chaque
        feuille : le 2e relais ne recevait qu'UN report au lieu de quatre (mesure seed 777 / PV 1200,
        board MC1_67 : natif 14 `genrand_int32`, port 12).

        LES DEUX CANAUX `AbilityEntities`, ET UN SEUL PORTE LE `killTrigger` (#301). L'`AbilityEntities`
        que `IdunBattle.Operations.KillUnitOperation$$Execute` publie sur ses CINQ evenements est bati
        en deux temps, LUS au decompile :

            1. memset(&entities, 0, 0x128)            -> **tous** les champs a ZERO, dont
                                                         `CurrentAbility` (`+0x60`) et `ParentAbility`
                                                         (`+0x7c`)
            2. +0x00 = +0x08 = killer ; +0x10 = killed ; +0x38 = Tiles(killed) ; +0x48 = Tiles(killer)
            3. **+0x98..+0xb4 = les 0x1c octets de `KillUnitOptions+0x04`** = `TriggeringAbility`

        La struct n'est plus TOUCHEE ensuite : elle est recopiee telle quelle avant chacune des cinq
        publications (`On(1)`, `On(2)`, `On(0)`, `On(54 = UnitDefeated)`, `On(53 = PostUnitKill)`). Donc, sur tout le vecteur MORT :

            `CurrentAbility`   (`+0x60`, lu par `AbilityTypeSelector.CurrentAbilitySelector$$Select`)
                               = **VIDE** -> tout `CurrentAbilityIs` y est FAUX cote natif ;
            `TriggeringAbility`(`+0x98`, lu par `AbilityTypeSelector.TriggeringAbilitySelector$$Select`)
                               = le `killTrigger` -> c'est LUI que comparent `TriggeringAbilityIs`,
                               `TriggeringEffectIs` et `TriggeringAbilityIsNone`.

        Chaine de la VALEUR, re-derivee de bout en bout : `IdunBattle.Core.MatchState$$AddDeath(this,
        killer, killed, killTrigger, attackTrigger, AttackRangeType)` enqueue une entree dont les
        octets `+0x08..+0x24` sont le `killTrigger` ; la lambda de drain
        `IdunBattle.Messages.InputMessageProcessor.u003Cu003Ec__DisplayClass49_0$$u003CVerifyDeathsu003Eb__0`
        part de `IdunBattle.Operations.KillUnitOperationOptions$$ForDefault()` et n'ECRASE que
        `options[0x04..0x20)` avec ce meme `killTrigger` ; `Core.Services.OperationProcessor$$KillUnit`
        recopie les 0x48 octets d'options tels quels. => `+0x98` EST le `killTrigger` de la file.

        Le port pose donc ici `state.trigger_ability_type` (le canal `+0x98`) et FORCE
        `state.triggering_ability` (le canal `+0x60`) a `None` -- le mirror du memset. Il posait
        auparavant le `killTrigger` sur `+0x60` et laissait `+0x98` vide : degradation PERMISSIVE
        (un `CurrentAbilityIs` voyait une valeur la ou le natif n'en publie aucune) et gates
        `Triggering*` alimentes par le mauvais canal. Les deux sont restaures en sortie de drain."""
        if state.draining_deaths:
            return []
        state.draining_deaths = True
        saved_current = state.triggering_ability
        saved_trigger = state.trigger_ability_type
        out: list = []
        try:
            while state.pending_deaths:
                # `KillUnitOptions+0x3c` (l'`AttackRangeType` de la mort) est le CINQUIEME champ de
                # l'entree depuis #951-r1. Les entrees a 4 champs restent lisibles : un etat
                # SERIALISE avant ce commit, ou un appelant qui construit la file a la main, ne
                # doit pas lever -- il retombe sur `None`, la branche `Nullable` vide du natif.
                _entry = state.pending_deaths.pop(0)
                dying_id, killer_id, overkill, kill_trigger = _entry[:4]
                attack_range_type = _entry[4] if len(_entry) > 4 else None
                # mirror du memset 0x128 : `CurrentAbility` (+0x60) est VIDE sur les cinq evenements.
                state.triggering_ability = None
                # `+0x98..+0xb4 = KillUnitOptions+0x04` = le `killTrigger` porte par l'entree de file.
                state.trigger_ability_type = kill_trigger
                out = out + (AttackDamageOperation._kill_unit_operation(
                    state, dying_id, killer_id, overkill,
                    attack_range_type=attack_range_type) or [])
        finally:
            state.triggering_ability = saved_current
            state.trigger_ability_type = saved_trigger
            state.draining_deaths = False
        return out

    @staticmethod
    def _kill_unit_operation(state: State, target_id: int, attacker_id,
                             overkill: bool,
                             attack_range_type: Optional[str] = None,
                             prevent_revive_option: bool = False) -> list:
        """`IdunBattle.Operations.KillUnitOperation$$Execute` -- l'APPLICATION d'une mort deja
        enqueuee. Emet la SEQUENCE COMPLETE 1 -> 2 -> 0 -> 0x36 -> 0x35 ; les CINQ sont portes,
        DANS CET ORDRE. La garde revive (`if (!unitComponent.PendingRevive@+0xa8 .HasValue)`)
        court-circuite tout ce qui suit `On(PreUnitDeath)` -- SAUF `On(0x35 = PostUnitKill)`, qui
        est APRES son `if/else` -- cf. la docstring de `_fire_death_if_killed`.

        ORDRE COMPLET, RE-DERIVE au decompile du build `rnca9r7q6c` (#389-r2). Les offsets sont
        les adresses de RETOUR des call-sites, relatives a `KillUnitOperation$$Execute` :

            +0x505  health = killed.HealthComponent ; savedHp = health.hp ; health.hp = 0
            +0x7cc  On(PreUnitDeath = 1)
            +0x81c  GARDE REVIVE : if (!unitComponent.PendingRevive@+0xa8 .HasValue) {
            +0x8be      if (IsActor(killer) && !IsSteppable(killed)) RegisterDefeatedUnit(...)
            +0x979      On(PreUnitDeath_2 = 2)
            +0x999      unitFlags.Remove(0xf = PendingDeath) ; +0x9ad unitFlags.Add(6 = Dead)
            +0x9be      RemoveEffects(killed, KillUnitStep.PreUnitRemove = 0)      <-- STEP 0
            +0xa26      if (HasTrait(0x10)) DraftingComponent.AddUnitDeadForDrafting(...)
            +0xd34      processor.<slot 6>(killed, 0, 1) ; +0xd88 matchState.<slot 0x31>(killed)
            +0xd9c      RemoveEffects(killed, KillUnitStep.AfterUnitRemove = 1)    <-- STEP 1
            +0xe49      On(UnitDeath = 0)
            +0xefc      On(UnitDefeated = 0x36 = 54)
            +0xf35      GARDE HEAL : if (health.hp > 0) RETURN         (aucun step 2, aucun On(53 = PostUnitKill))
            +0xf59      RemoveEffects(killed, KillUnitStep.AfterDeathTrigger = 2)  <-- STEP 2
            +0xf7f      processor.<slot 0x55>(killed, false)
                    } else { +0xfcc matchState.<slot 0x63>(killed) }
                    unitComponent.PendingRevive@+0xa8..+0xe8 = 0
            +0x10ac On(PostUnitKill = 0x35 = 53)

        DEUX CORRECTIONS D'ORDRE que ce foyer apporte, toutes deux LUES a la profondeur d'accolades :
          * le retrait des effets du mort etait emis ENTRE `On(UnitDeath)` et `On(UnitDefeated)` ;
            le natif le fait AVANT `On(UnitDeath)` (steps 0 et 1) ;
          * `On(PostUnitKill)` n'est PAS sous la garde revive (il est apres le `if/else`).

        `On(0x35 = PostUnitKill)` EST DESORMAIS EMIS ICI (#462-r4b-r1-r1-r1-r1-c-r3-r1-r4). Il ne
        l'etait que par `move_death.py::post_unit_kill_triggers_for_move`, donc PLUS TARD dans le
        pipeline de move (apres `UpdateCharging`/`SetMovedFlag`) et pour le SEUL crush-par-move :
        double ecart, d'ORDRE et de COUVERTURE. La lecture qui tranche son rang est la PILE
        d'accolades, pas la PROFONDEUR -- `On(0x35)` et les trois du milieu sont tous a la
        profondeur 9, mais leurs piles different :

            L1111  if (unitComponent != null) {
            L1131      if (!PendingRevive.HasValue) {      <- pile de On(2), On(0), On(0x36)
            L1971          if (health.hp > 0) return;
            L1997      } else { ... }
            L2033      if (dispatcher != null) {           <- pile de On(0x35) : PAS L1131

        TROIS consequences PORTEES, toutes lues, aucune deduite :
          1. la branche REVIVE publie `On(0x35)` elle aussi (le natif sort du `if/else` avant lui) ;
          2. la GARDE HEAL le saute (son `return` precede) ;
          3. aucun octet de `KillUnitOptions` ne le gate => il part pour TOUTES les voies qui
             traversent `Execute` : degat (drain), crush (`_kill_steppable_kill_unit`, donc move ET
             revive/resurrect/spiritual_leader) et `KillUnitBehaviour` (feuille DSL `Kill`).
        """
        # PORTEUR (cycle `operations` <-> `triggers`) ET forme MODULE : les cinq vecteurs sont
        # relus a l'appel, donc une substitution posee sur `move_death` mord quelle que soit la
        # forme finale de cet import. `probe_485r1r1_formes_dimport.py` mesure les trois formes ;
        # un `from ... import unit_death_triggers` hisse deviendrait INERTE, en silence.
        from .triggers.dispatch import move_death
        from .revive import kill_unit_revive_gate
        # ── `flags.Add(0x0d = UnitFlag.PreventRevive)` -- AVANT `On(1 = PreUnitDeath)` ────────────
        # RANG NATIF EXACT, lu aux adresses de retour de `KillUnitOperation$$Execute` :
        # `RecordDeathReason` -> `Add(0x08 = Overkilled)` -> **`Add(0x0d)`** -> `On(1)`. Le flag est
        # donc DEJA pose quand le vecteur qui porte les revives s'execute.
        # Le gate, LU :
        #     bool preventRevive = options.<+0x45> ? true : UnitExtensions.IsSteppable(killed);
        #     if (preventRevive) flags.Add(0x0d);
        # `prevent_revive_option` mirroite `KillUnitOptions+0x45` : `False` sous `ForDefault` (toutes
        # les morts par degat, la feuille DSL `Kill`), `True` sous
        # `IdunBattle.Operations.KillUnitOperationOptions$$ForSteppable`, qui ecrit
        # `*(undefined2 *)(opts + 0x44) = 0x101`. Un CRUSHE le recoit donc SANS CONDITION, et un
        # `Steppable` mort autrement le recoit par le second bras.
        # ⚠ CE N'EST PAS COSMETIQUE : son lecteur est le 3e etage de
        # `IdunBattle.Core.Services.BattleQuery$$CanBeRevived` (`!HasFlag(target, 0xd)`), que le port
        # ne jouait pas -- il ressuscitait donc un crushe que le natif refuse
        # (#462-r4b-r1-r1-r1-r1-c-r3-r1-r6). Le flag `Dead` (6), lui, reste POSE PLUS BAS, dans la
        # branche non-revive : les deux n'ont pas le meme rang cote natif et n'ont pas a l'avoir ici.
        _e_pr = state.get_entity(int(target_id))
        _fl_pr = _e_pr.get_component(UnitFlagsComponent) if _e_pr is not None else None
        if _fl_pr is not None:
            _sc_pr = _e_pr.get_component(StatsComponent)
            _tr_pr = getattr(_sc_pr.ctx, "traits", None) if _sc_pr is not None else None
            if prevent_revive_option or has_trait(_tr_pr or [], UnitTrait.Steppable):
                _fl_pr.add(UnitFlagsComponent.PREVENT_REVIVE)
        out = move_death.after_death_triggers(state, target_id, attacker_id, overkill=overkill)
        # `unitComponent.DefeatedByMeleeAttack@+0x178 = inMelee` (#951-r1), LU aux octets :
        #
        #     +0x8xx  local_378[0] = local_370[0] == 1 & *pbVar22
        #                            # rangeType.GetValueOrDefault() == Melee(1)  &  HasValue
        #     +0x8xx  *(byte *)(victime.UnitComponent + 0x178) = local_378[0]
        #
        # ⚠ SA PLACE : APRES `On(PreUnitDeath)` et **AVANT la garde revive** -- lue a la pile
        # d'accolades, comme `On(0x35)`. Une mort ANNULEE par un revive pose donc quand meme le
        # marqueur, contrairement a `KilledThisTurn@+0x17a` (qui, lui, est DANS la branche
        # non-revive). C'est pourquoi les deux ecritures ne sont pas au meme endroit ici.
        # C'est le MEME octet que l'`inMelee` passe plus bas a `register_defeated_unit` : le natif
        # ne le calcule qu'une fois. Lecteurs portes du marqueur : `PossessionAbility` et
        # `DawnBladeHealAbility` (`IsDefeatedByMeleeAttack(Target)`), qui l'approximaient
        # positionnellement.
        _melee_kill = (None if attack_range_type is None else (attack_range_type == "Melee"))
        _ent_marker = state.get_entity(int(target_id))
        _uc_marker = (_ent_marker.get_component(UnitComponent)
                      if _ent_marker is not None else None)
        if _uc_marker is not None and _melee_kill is not None:
            _uc_marker.defeated_by_melee = bool(_melee_kill)
        # GARDE @`KillUnitOperation$$Execute+0x81c` : `if (!unitComponent.PendingRevive.HasValue)`. Un `Revive` posé par un
        # consommateur d'`On(PreUnitDeath)` (ReviveEffect, PhoenixGem, ...) fait ÉCHOUER la garde -> la mort est
        # ANNULÉE : on applique le revive (phase 0xd) et on n'émet NI On(PreUnitDeath_2), NI On(UnitDeath), NI On(UnitDefeated) — et AUCUN des trois `RemoveEffects`.
        revived = kill_unit_revive_gate(state, target_id)
        if revived is not None:
            # Branche `else` @`KillUnitOperation$$Execute+0xfcc` (`matchState.<slot 0x63>`) : le revive
            # s'applique... et l'execution REJOINT le tronc commun, ou `On(0x35)` est publie @+0x10ac.
            # C'est le SEUL des cinq events que la garde revive n'annule pas (pile d'accolades ci-dessus).
            return ((out or []) + [{"kill_cancelled_by_revive": revived}]
                    + move_death.post_unit_kill_triggers(state, target_id, attacker_id))
        # `unitComponent.KilledThisTurn@+0x17a = 1` @`KillUnitOperation$$Execute+0x828` -- la
        # PREMIERE instruction de la branche non-revive, entre la garde @+0x81c et le
        # `RegisterDefeatedUnit` @+0x8be. C'est le substrat du noeud DSL
        # `IdunBattleLogic.Entities.DSLTriggers$$IsKilledThisTurn` (lecteur unique :
        # `IdunBattle.Entities.Triggers.KilledThisTurnTrigger$$ShouldTrigger`, qui rend ce seul
        # octet). Il est DANS la branche non-revive : une mort ANNULEE par un revive ne le pose pas
        # -- c'est pourquoi il est ecrit ici et non avant `kill_unit_revive_gate`.
        _ent_killed = state.get_entity(int(target_id))
        _uc_killed = (_ent_killed.get_component(UnitComponent)
                      if _ent_killed is not None else None)
        if _uc_killed is not None:
            _uc_killed.killed_this_turn = True
        # `RegisterDefeatedUnit` @`KillUnitOperation$$Execute+0x8b9` (#951) -- inscrit la victime au
        # compteur du TUEUR, sous ses deux gates natifs (`IsActor(killer)`, `!IsSteppable(killed)`).
        # ⚠ SA PLACE EST LOAD-BEARING : le natif l'appelle ICI, donc AVANT les cinq publications
        # d'evenement ci-dessous. `TrophyTakerAbility`, consommateur d'`On(UnitDefeated)`, compte
        # donc la victime COURANTE -- l'inscrire apres rendrait `n` la ou le natif rend `n+1`.
        # ⚠ `in_melee` EST DESORMAIS PASSE (#951-r1 ferme). Ce n'etait pas une invention a faire mais
        # un ETAGE a lire : `options.inMelee` des `KillUnitOptions` vient de `KillUnitOptions+0x3c`
        # (`Nullable<AttackRangeType>`), que `IdunBattle.Operations.RecordKillOperation$$Execute`
        # enfile via `IdunBattle.Core.MatchState$$AddDeath(..., AttackRangeType)` et que, sur la voie
        # DEGAT, `IdunBattle.Operations.ApplyDamageOperation$$Execute` a deja calcule par le slot 4
        # d'`IBattleQuery` (`GetAttackRangeType`). Chaine complete et citations : docstring d'
        # `_add_death`. C'est LE MEME octet que le marqueur `@+0x178` pose ci-dessus.
        # `None` -> branche par DEFAUT du decompile (`if ((char)inMelee == '\0')` -> `@+0xb0`), qui
        # est aussi ce que le natif fait pour les voies dont les `KillUnitOptions` laissent `+0x3c`
        # a zero (crush `ForSteppable`, feuille DSL `Kill` via `ForDefault`).
        register_defeated_unit(state, attacker_id, target_id, in_melee=_melee_kill)
        # `On(PreUnitDeath_2 = 2)` — vecteur des death-novas Explodes/PutridExplosion. Il PRECEDE
        # tout retrait : c'est pourquoi `ExplodesAbility$$GetDamage` voit encore les effets du mort
        # (`HasEffect(Owner, 1098)` de RammingSpeed, #389).
        out = (out or []) + move_death.pre_unit_death_2_triggers(state, target_id, attacker_id,
                                                            overkill=overkill)
        # `RemoveEffects(killed, PreUnitRemove)` puis `RemoveEffects(killed, AfterUnitRemove)` — les
        # deux premiers des TROIS appels natifs, tous deux AVANT `On(UnitDeath)`. Le natif intercale
        # entre eux le retrait de l'unite du plateau (`processor.<slot 6>` + `matchState.<slot 0x31>`),
        # que le port collapse deja dans `uc.alive = False` (pose en amont, `_fire_death_if_killed`).
        out = out + [{"kill_remove_effects": {
            "step": int(KillUnitStep.PreUnitRemove),
            "removed": _kill_unit_remove_effects(state, target_id, KillUnitStep.PreUnitRemove)}}]
        out = out + [{"kill_remove_effects": {
            "step": int(KillUnitStep.AfterUnitRemove),
            "removed": _kill_unit_remove_effects(state, target_id, KillUnitStep.AfterUnitRemove)}}]
        # `On(UnitDeath = 0)` — consommateur : TerrifyingCrescendo branche OVERKILL
        # (cf. loki/terrifying_crescendo.py).
        out = out + move_death.unit_death_triggers(state, target_id, attacker_id, overkill=overkill)
        # #G3 : `On(UnitDefeated=54)` (event DISTINCT de 1, 2 et 0) -> Ambush_SummonAbility (mort -> decoy +
        # record turn_defeated). L'unité est déjà alive=False (fire-on-death).
        out = out + move_death.unit_defeated_triggers(state, target_id, attacker_id)
        # GARDE HEAL @`KillUnitOperation$$Execute+0xf35` : le natif relit le `HealthComponent` du mort
        # (dont il avait mis les PV a 0 en tete d'operation) et RETOURNE si `hp > 0`. Un consommateur
        # de `On(UnitDeath)`/`On(UnitDefeated)` qui SOIGNE le mourant annule donc le 3e retrait.
        thc = None
        ent = state.get_entity(int(target_id))
        if ent is not None:
            thc = ent.get_component(HealthComponent)
        if thc is not None and thc.hp is not None and int(thc.hp) > 0:
            return out                       # le `return` natif saute AUSSI `On(0x35 = PostUnitKill)`
        out = out + [{"kill_remove_effects": {
            "step": int(KillUnitStep.AfterDeathTrigger),
            "removed": _kill_unit_remove_effects(state, target_id, KillUnitStep.AfterDeathTrigger)}}]
        # `On(PostUnitKill = 0x35 = 53)` @`KillUnitOperation$$Execute+0x10ac` -- 5e et DERNIER event,
        # publie sous le seul null-check du dispatcher (`if (dispatcher != null)` @L2033), hors de la
        # garde revive. Consommateur porte : `CosmicHorrorOnMoveAbility`.
        out = out + move_death.post_unit_kill_triggers(state, target_id, attacker_id)
        return out

    @staticmethod
    def _refresh_swarm(state: State, target_id: int) -> None:
        """#60 : bras `On(UnitMemberDeath=47) & OwnerIsTarget` du `IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateTrigger` — apres toute baisse de PV de la cible, re-evalue le stat-mod EXTRA_HITS du trait
        Swarm (`AddOrUpdateStaticStatModifierEffect 0x3fd`, cf. runner/abilities/loki/swarm.py). No-op
        rapide pour une cible non-swarm ou morte. Lazy import (cycle damage <-> abilities)."""
        from ..abilities.loki.swarm import on_group_unit_hp_changed
        on_group_unit_hp_changed(state, target_id)

    @staticmethod
    def _pre_damage_taken_per_hit(state: State, attacker_id: int, target_id: int, thc,
                                  total: int, shield_dmg: int, profile: Optional[str],
                                  hits_result: Optional[dict], attack_dispatch,
                                  *, is_first_damaging_hit, source_ability=None) -> tuple:
        """#1020 -- l'etage `On(0x39 = EventTriggerType.PreDamageTaken)`, PAR COUP et A RETOUR LU.

        MIRROR de la sequence d'`IdunBattle.Operations.ApplyDamageOperation$$Execute`, relue aux
        octets (l'operation native est appelee UNE FOIS PAR COUP, par
        `IdunBattle.Core.Services.OperationProcessor$$ApplyDamage`) :

            healthComp[+0x64] = Nullable<DamageAppliedResult>(result);      // ECRITURE du pending
            ...
            if (0 < DamageAppliedResult.get_Damage(&result))                // le GATE d'emission
                <publish 0x39>                                             // les triggers ont la main
            ...
            GetValueOrDefault(healthComp[+0x64], &pending);                 // RELECTURE
            local_7dc = FillUpStatComponent.Reduce(hp, pending.healthDamage);
            ReduceShield(.., pending.shieldDamage);

        **LE CANAL DE DETOURNEMENT N'EST PAS LE RETOUR DU DISPATCH -- c'est le CHAMP PENDANT.**
        `IdunBattle.Operations.TransferDamageOperation$$GetDamage` lit `healthComp[+0x64]`, en tire
        `DamageAppliedResult$$get_Damage`, puis ECRIT `*(qword*)(comp+0x64) = 0` et
        `*(qword*)(comp+0x6c) = 0` : la valeur pendante est **CONSOMMEE**. La relecture native etant
        un `System.Nullable<T>$$GetValueOrDefault`, un pending vide rend la struct ZERO et le
        `Reduce` qui suit n'enleve RIEN. C'est ce qui fait de `SaviorProtocols` un DEPLACEMENT de
        degat et non un bonus : confondre les deux DOUBLE le degat au lieu de le deplacer.

        GRANULARITE. `hits_result["per_hit_pending"]` (#1020, `damage_hits.py`) porte le
        `(healthDamage, shieldDamage)` de chaque coup qui atteint le point d'ecriture -- meme
        population que `per_hit`, donc deja filtree par le SITE (A) (`overkill_hit_emits` : le natif
        `return` AVANT de poser le pending). Absent (`None`) = vecteur SANS decomposition par coup
        (DoT, knockback, degat direct) : le natif n'y appelle `ApplyDamageOperation` qu'une fois,
        donc le groupe EST le coup et la liste degenere a un seul element -- rigoureusement le
        comportement d'avant ce commit.

        `isFirstDamagingHit` (`DamageAppliedResult+0x18`) est PROPRE AU COUP : seul le PREMIER coup
        damageant de la serie le porte. Le flag threade en argument dit « aucun degat n'a encore ete
        inflige dans CETTE attaque » ; on le consomme au premier coup qui emet, les suivants
        recoivent FAUX. Effet mesure sur `GeminaeSuperia` (#963, seul consommateur porte du
        vecteur) : AUCUN -- son `matches` commence par `if not ev.is_first_damaging_hit: return
        False`, donc les coups 2..N sortent avant toute evaluation de `SummonLimit` ou de
        `GetPossibleSpawnTiles`. Le passage par-groupe -> par-coup ne lui ajoute ni spawn, ni
        evaluation, ni tirage.

        Rend `(kept_health, kept_shield, transfers)`. Sans aucun consommateur qui consomme le
        pending, `kept_health == total` et `kept_shield == shield_dmg` A L'IDENTIQUE -- c'est
        l'invariant de non-regression du chokepoint des QUATRE vecteurs de degat.

        `#1020-r1` -- FERME. Le natif annule AUSSI `ReduceShield` sur un coup transfere : il lit
        `pending.shieldDamage`, donc 0, exactement comme son voisin `Reduce` lit
        `pending.healthDamage` -- les deux valeurs sortent du MEME `GetValueOrDefault`, celui
        d'APRES l'emission. Le port depletait le bouclier chez les APPELANTS, avant ce chokepoint
        et sur le degat CALCULE : la victime d'un transfert perdait un bouclier qu'elle aurait du
        garder. `_deplete_shield` vit desormais dans `_apply_damage_pipeline`, juste apres
        `thc.reduce`, et consomme `kept_shield`."""
        pend = (hits_result or {}).get("per_hit_pending")
        if not pend:
            pend = [(int(total or 0), int(shield_dmg or 0))]
        kept_h = kept_s = 0
        transfers = 0
        first_dmg = bool(is_first_damaging_hit)
        for (h, s) in pend:
            # `healthComp[+0x64] = Nullable<DamageAppliedResult>(result)` -- AVANT toute emission.
            thc.pending_damage = PendingDamage(profile, int(h), int(s))
            if int(h) + int(s) > 0:            # `0 < DamageAppliedResult.get_Damage(&result)`
                attack_dispatch.pre_damage_taken_triggers(
                    state, attacker_id, target_id, profile=profile,
                    is_first_damaging_hit=first_dmg, source_ability=source_ability)
                first_dmg = False              # `+0x18` du coup SUIVANT : plus le premier damageant
            after = thc.pending_damage         # `GetValueOrDefault` : Nullable vide -> struct ZERO
            if after is None:
                transfers += 1
            else:
                kept_h += int(after.health)
                kept_s += int(after.shield)
            thc.pending_damage = None          # le pending ne survit pas au coup (portee = `Execute`)
        return kept_h, kept_s, transfers

    @staticmethod
    def pre_damage_taken_of(sink):
        """Le cumul `(kept_health, kept_shield, transferts)` d'un sink, ou `None` s'il n'y en a pas.

        FOYER UNIQUE de la lecture, pour que les quatre call-sites moteur ne l'ecrivent pas chacun
        a leur facon. `None` = aucun sink threade (`thc` inexploitable) -> `_apply_damage_pipeline`
        emet lui-meme, comme pour les vecteurs sans decomposition par coup."""
        return None if sink is None else sink.cumul()

    @staticmethod
    def make_pre_damage_taken_sink(state: State, attacker_id: Optional[int], target_id: int, thc,
                                   profile: Optional[str], *, is_first_damaging_hit,
                                   source_ability=None):
        """#1020-r4 -- le chokepoint `On(0x39 = EventTriggerType.PreDamageTaken)` d'UN COUP, sous
        une forme que `damage_hits._run_hits` peut appeler A SA POSITION dans le flux PRNG.

        MEME CORPS que `_pre_damage_taken_per_hit` (pose du pending -> gate `0 <
        DamageAppliedResult$$get_Damage` -> emission -> relecture `GetValueOrDefault` -> purge),
        mais joue coup par coup DANS la boucle au lieu d'etre re-deroule apres elle. La granularite
        etait deja juste ; c'est la POSITION qui ne l'etait pas -- cf. le bloc `POSITION DU TIRAGE`
        de `damage_hits._run_hits`, qui porte la lecture native.

        `isFirstDamagingHit` (`DamageAppliedResult+0x18`) reste PROPRE AU COUP : l'etat vit dans la
        closure et tombe au premier coup qui emet, exactement comme dans la version par-groupe.

        Rend `None` quand il n'y a pas de `HealthComponent` exploitable : l'appelant ne threade
        alors aucun sink et le chokepoint de groupe reprend la main (il a ses propres gardes
        `thc is None or thc.hp is None`).

        ⚠ LE CUMUL VIT SUR LE SINK, PAS DANS LE RETOUR DE `_run_hits` -- et c'est une correction,
        pas un gout. Un premier jet le publiait sous la cle `pre_damage_taken` du dict rendu par
        `damage_hits._run_hits`, ce qui ELARGISSAIT le CONTRAT DE SORTIE de ce canal sans le
        declarer : toute substitution de `_run_hits` restee en arriere levait alors `KeyError`.
        Deux gardes EXISTANTES l'ont attrape (`test_failed_block_attack_scope_offline.py::
        test_execute_additional_hits_CHAINE_l_etat_de_groupe_en_groupe` et
        `test_additional_hits_variant_signatures_offline.py::
        test_toute_substitution_expose_le_contrat_de_SORTIE`, dont le stub rend exactement le
        contrat documente). Le cumul appartient a son PRODUCTEUR : l'appelant possede deja le
        sink, il n'a aucun besoin de le faire transiter par le canal."""
        if thc is None or thc.hp is None:
            return None
        return _PreDamageTakenSink(state, attacker_id, target_id, thc, profile,
                                   is_first_damaging_hit, source_ability)

    @staticmethod
    def _apply_damage_pipeline(state: State, target_id: int, attacker_id: int, tgt, thc,
                               total: int, profile: Optional[str],
                               shield_dmg: int = 0, armor_dmg: int = 0,
                               is_attack: bool = True,
                               source_ability=None, last_hit: Optional[int] = None,
                               hits_result: Optional[dict] = None,
                               is_force_overkill: bool = False,
                               is_first_hit: Optional[bool] = None,
                               triggering_effect: Optional[int] = None,
                               is_first_damaging_hit: Optional[bool] = None,
                               # #1020-r4 : `(kept_health, kept_shield, transferts)` rendu par
                               # `damage_hits._run_hits` quand l'appelant lui a threade un
                               # `pending_sink` -- c.-a-d. quand l'emission `On(0x39)` a DEJA ete
                               # jouee coup par coup, a sa position dans le flux PRNG. ARGUMENT
                               # PROPRE, et non une cle de `hits_result` : `additional_hits.py`
                               # ne threade PAS `hits_result`, et l'y cacher aurait produit une
                               # DOUBLE emission sur ce vecteur (silencieuse : ni erreur ni crash,
                               # juste un tirage de trigger de trop par groupe).
                               pre_damage_taken: Optional[tuple] = None) -> Optional[list]:
        """#202 : CHOKEPOINT post-resolution PARTAGE des 4 vecteurs de degat — mirror du pipeline natif
        unique qui suit toute application de degat : `ApplyDamageOperation` (mutation HP, clamp HP-floor)
        -> OnDeathEvent (`_fire_death_if_killed`) -> compteurs per-tour (`_record_attacked`, attaques
        seulement) -> `RegisterDamageOperation IdunBattle.Operations.RegisterDamageOperation$$Execute` (`_register_received_damage`) -> re-eval Swarm
        (`_refresh_swarm`, On(UnitMemberDeath=47)). Avant ce foyer, chaque vecteur inlinait le meme bloc
        x4 (divergence structurelle vs le chokepoint natif). `is_attack=False` = degat DIRECT (DoT) :
        pas de `_record_attacked` (un DoT n'est PAS une attaque, compteur HasBeenAttackedAmountThisTurn).

        `is_first_hit` / `triggering_effect` = payload du vecteur `On(DamageDealt = 0x10)` emis ci-dessous
        (mirror du champ `AbilityEntities+0x110` et du gate `TriggeringEffectIs` natif). `is_first_hit=True`
        signifie « ce GROUPE de degat contient le coup d'index 0 » : la phase d'arme d'une attaque et la
        1re serie sur une cible le portent ; un groupe de coups ADDITIONNELS (#179, index de sortie > 0)
        ne le porte pas. `None` (defaut) = aucun index de coup dans cet evenement (degat DIRECT / DoT /
        knockback) -> `IsFirstHitInSeries` FAUX, mirror du `Nullable<int>` vide natif.
        Renvoie la liste d'events de mort (ou None si pas de mort / pas de HP)."""
        if thc is None or thc.hp is None:
            return None
        hp_before = thc.hp
        # case-209 : `IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit` -- les degats
        # GASPILLES du groupe (coup fatal : reste d'overkill ; coups sur cadavre : la base
        # nominale). AVANT la mutation de PV, parce que le re-jeu part de `hp_before`. Purement
        # additif : aucune branche existante n'en depend, seul `HazeOfCorruption_DamageTransferEffect`
        # relit la liste.
        record_left_over_damages(state, target_id, tgt, hp_before, total, profile, hits_result,
                                 (hits_result or {}).get("base_nominal"))
        # SITE (A) d'`IdunBattle.Operations.ApplyDamageOperation$$Execute` -- RELU VERBATIM :
        #
        #     cVar15 = IdunBattle_Entities_UnitExtensions__HasFlag(param_4, 8, 0);   // 8 = Overkilled
        #     if (cVar15 != '\0') {
        #       ApplyDamageOperation__RecordHitStatistics(...);
        #       ApplyDamageOperation__AddLeftoverHit(param_2, param_4, &dmg, &hit, 1, 0);
        #       return param_1;                                   // <- TOUT LE RESTE EST SAUTE
        #     }
        #
        # Le `return` precede l'emission d'`On(0x39 = PreDamageTaken)`, la mutation de PV (`FillUpStatComponent$$Reduce`),
        # `On(DamageTaken = 0xf)`, l'ecriture `lastHitDamageTaken` (`stats+0x68` / `+0x6c`) et
        # `On(DamageDealt = 0x10)` : un coup porte sur une cible DEJA OVERKILLEE ne fait qu'empiler sa
        # `LeftOverDamage` (base nominale) et n'emet RIEN. Le port emettait `On(0x10)` -- donc, sur un
        # profil Toxic, le `Maybe(25)` d'`OnToxicDamageAbility` : UN TIRAGE `genrand_int32` de trop.
        # MESURE qui le tranche (`probe_hazeord_death_queue.py`, seed 777 / PV 1200 / MC1_67) : le coup
        # bonus de `HazeCorruption_BonusHitAbility` tombe sur une cible overkillee des le 1er coup
        # d'arme -- le flux natif ne contient AUCUN evenement pour lui, le port en tirait un.
        # GRANULARITE : le natif teste le flag PAR COUP, le port n'a qu'un chokepoint PAR GROUPE -- mais
        # le flag n'est POSE qu'a la fin d'un groupe (`_fire_death_if_killed`), donc « pose a l'entree du
        # groupe » vaut pour TOUS ses coups. Le flag est RETIRE par un revive
        # (`IdunBattle.Operations.ReviveUnitOperation$$Execute` : `Remove(0xf)`, `Remove(8)`,
        # `Add(0x14)`, porte dans `revive.py`) -> une unite ressuscitee redevient frappable.
        fl_entry = tgt.get_component(UnitFlagsComponent) if tgt is not None else None
        if fl_entry is not None and fl_entry.has(UnitFlagsComponent.OVERKILLED):
            return None
        # `On(PreDamageTaken = 0x39)` — #963. PREMIER des TROIS events d'`IdunBattle.Operations.
        # ApplyDamageOperation$$Execute` (`0x39` -> `0xf` -> `0x10`, LU aux octets : les trois
        # publications sont aux memes points de sortie du decompile). Il vit ICI, entre le gate
        # `Overkilled` du SITE (A) ci-dessus et la mutation de PV : la victime est encore a PLEINE
        # VIE quand il part. Gate natif = `0 < DamageAppliedResult.get_Damage(result)`, donc le
        # degat de CE coup, pas le degat demande.
        # ⚠ Ce vecteur n'existait PAS avant ce commit (0 emetteur sur 40 types) : le trigger de
        # `GeminaeSuperia` y serait entre MORT. Aucun autre consommateur ne l'ecoute -> no-op (et
        # ZERO conso RNG) pour toute unite non-porteuse.
        # GRANULARITE : le natif emet PAR COUP, le port a un chokepoint PAR GROUPE -- meme regime,
        # deja assume, que ses deux freres `On(0xf)` / `On(0x10)`.
        # lazy : cycle damage<->triggers. Forme MODULE (cf. le meme import quelques lignes plus bas) :
        # l'attribut est relu a l'appel, donc une substitution posee sur `dispatch.attack` mord.
        from .triggers.dispatch import attack as attack_dispatch
        # #1020 -- L'EMISSION EST DESORMAIS PAR COUP, ET SON RETOUR EST LU.
        # `isFirstDamagingHit` (`AbilityEntities+0x118`, 29e parametre nomme du ctor
        # `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` ; lu SANS getter par
        # `IdunBattle.Entities.Triggers.IsFirstDamagingHitInSeriesTrigger$$ShouldTrigger`,
        # qui teste `HasValue` puis `get_Value` -> un Nullable vide vaut FAUX).
        #
        # #963-r2 -- L'ENONCE DU RESIDU ETAIT PARTIELLEMENT FAUX, et le re-mesurer a
        # DEPLACE le trou. Il disait : « si le coup d'index 0 inflige 0, le port ne marque
        # AUCUN groupe ». C'est inexact -- le gate d'emission etait `total > 0` sur le GROUPE,
        # donc un groupe dont le coup 0 est bloque mais dont un coup suivant damage emettait
        # DEJA avec le flag vrai. Le seul regime qui divergeait est plus etroit d'un cran :
        # le groupe portant l'index 0 entierement a ZERO (tous ses coups bloques, donc
        # AUCUNE emission), suivi d'un groupe qui damage -- ce second groupe ne contient pas
        # l'index 0, et rendait donc FAUX la ou le natif marque le premier coup damageant.
        #
        # D'ou un flag PROPRE, threade comme `crit_allowed` et `failed_block` : « aucun
        # degat n'a encore ete inflige dans CETTE attaque ». `None` = appelant qui ne le
        # thread pas -> repli sur l'ancien `is_first_hit` (rigoureusement l'ancien
        # comportement, pour les vecteurs qui n'ont pas de sous-operations).
        #
        # #1020-r4 -- ET SON EMISSION A DESORMAIS UNE POSITION. Quand l'appelant a threade un
        # `pending_sink` a `damage_hits._run_hits`, le chokepoint a DEJA ete joue coup par coup, au
        # point exact du flux PRNG ou le natif le joue (entre le split d'un coup et le tirage du
        # suivant) : on ne fait plus que LIRE son cumul. Sinon (`None` : DoT, knockback, degat
        # direct, ou tout appelant qui ne threade pas), on emet ici, comme avant.
        #
        # ⚠ LES DEUX BRANCHES DOIVENT PORTER LE MEME CANAL `source_ability` (#1020-r3). Le sink le
        # recoit a sa construction et le passe a CHAQUE emission -- resoudre ce rebase en ne le
        # laissant que dans la branche `else` aurait fait perdre le canal aux QUATRE vecteurs
        # moteur, c'est-a-dire a tous ceux qui ont une decomposition par coup : les deux
        # `!TriggeringAbilityIs` de `SaviorProtocols` seraient redevenus aveugles, sans erreur.
        if pre_damage_taken is not None:
            kept_health, kept_shield, transfers = (int(pre_damage_taken[0]),
                                                   int(pre_damage_taken[1]),
                                                   int(pre_damage_taken[2]))
        else:
            kept_health, kept_shield, transfers = AttackDamageOperation._pre_damage_taken_per_hit(
                state, attacker_id, target_id, thc, int(total or 0), int(shield_dmg or 0), profile,
                hits_result, attack_dispatch,
                is_first_damaging_hit=(is_first_hit if is_first_damaging_hit is None
                                       else is_first_damaging_hit),
                # #1020-r3 -- LE CANAL `AbilityEntities+0x98`, LU au ctor nomme.
                # `ApplyDamageOperation$$Execute` construit son `AbilityEntities` avec
                # `currentAbilityOrEffect` (13e param) ET `triggerAbilityOrEffect` (15e param) tous
                # deux recopies du MEME bloc `DamageAppliedResult+0x40` (le
                # `Nullable<AbilityOrEffect>` de son champ `source: IdunBattle.Operations.
                # DamageSource`). Cote port ce bloc EST `source_ability`, deja resolu par
                # `_damage_source_ability` (mirror d'`idun.Idun.Source.Shared.Battle.
                # StaticBattleRules.StaticBattleRules$$GetDamageSourceAbility`).
                source_ability=source_ability)
        # `FillUpStatComponent$$Reduce(hp, pending.healthDamage)` : le natif reduit ce que le
        # PENDING RELU porte, pas le degat calcule. Sans consommateur, `kept_health == total`
        # (mesure du no-op : voir `probe_1020_pipeline_par_coup.py` etage 1).
        applied = thc.reduce(kept_health)   # #G6a : clamp au HP-floor Hypersensory, pas de PV<0
        # `ApplyDamageOperation$$ReduceShield(this, target, pending.shieldDamage)` -- #1020-r1.
        # JUSTE APRES `Reduce`, et sur le pending RELU comme lui (les deux valeurs sortent du meme
        # `GetValueOrDefault`). Avant ce commit la depletion vivait chez les APPELANTS, avant le
        # chokepoint et sur le degat CALCULE : un coup transfere annulait les PV mais laissait la
        # victime perdre son bouclier. Le `ShieldComponent` est relu ICI depuis `tgt` -- c'est le
        # meme composant que celui des appelants (`_target_shield` le resout de la meme facon).
        AttackDamageOperation._deplete_shield(
            tgt.get_component(ShieldComponent) if tgt is not None else None, kept_shield)
        # Les etages EN AVAL lisent le pending relu, pas le calcule : tout ce qui suit consomme
        # `kept_*`. Egalite stricte avec l'ancien code des qu'aucun trigger ne consomme.
        total = kept_health
        shield_dmg = kept_shield
        # #462-r4e-o-r1 : `HealthComponent.reduce` a accumule `+0x24` sur le total du GROUPE ; le
        # natif l'accumule PAR COUP et n'appelle pas `Reduce` pour un coup gate par le SITE (A).
        # Quand la decomposition existe, on repose la valeur EXACTE calculee coup par coup.
        if hits_result is not None and hits_result.get("over_reduce") is not None:
            thc.over_reduce = int(hits_result["over_reduce"])
        # `On(DamageTaken=0xf)` — `IdunBattle.Operations.ApplyDamageOperation$$Execute` emet cet event
        # JUSTE APRES la mutation de PV (`FillUpStatComponent.Reduce`), sous le gate `0 < reduction
        # REELLEMENT appliquee` (variable `local_7dc` du decompile = la valeur de retour de Reduce, PAS
        # le degat demande) -- d'ou `applied > 0` ici. AVANT `_fire_death_if_killed` : cote natif la mort
        # n'est traitee qu'ensuite (`VerifyDeaths` -> `KillUnitOperation`), donc une victime tombee a 0 PV
        # est encore vivante quand l'event part. Seul consommateur porte : ThrillSeekers (branche 2).
        # lazy : cycle damage<->triggers. Forme MODULE : l'attribut est relu a l'appel, donc une
        # substitution posee sur `dispatch.attack` mord quelle que soit la forme finale.
        from .triggers.dispatch import attack as attack_dispatch
        if applied > 0:
            # #1025-r2 : `source_ability` = le canal `AbilityEntities+0x60` (`CurrentAbility`). Le
            # natif ne construit qu'UN `AbilityEntities` pour ses trois publications, donc ce vecteur
            # porte EXACTEMENT ce que porte deja `On(0x39)` juste au-dessus. C'est le canal que lit
            # `IsRangedAttack()` (selecteur `DSLSelectors+0x88` = `CurrentAbilitySelector`) --
            # sans lui, le predicat retombait sur l'adjacence et refusait une attaque d'ability
            # `attackRangeType: Ranged` portee au CONTACT. Cf. `damage_taken_triggers`.
            attack_dispatch.damage_taken_triggers(state, attacker_id, target_id, profile=profile,
                                                  source_ability=source_ability)
        # `On(DamageDealt=0x10)` (#85) — le TROISIEME et DERNIER event de
        # `IdunBattle.Operations.ApplyDamageOperation$$Execute` (sequence `0x39` -> `0xf` -> `0x10`).
        # (`0x3a` ecrit ici jusqu'a #963 etait une COQUILLE : `0x3a` = `PhaseEnd`, pas
        # `PreDamageTaken`. Les trois publications ont ete relues aux octets, cf. le bloc `On(0x39)`
        # ci-dessus.)
        #
        # case-221 : son gate n'est PAS celui de `On(0xf)`. RELECTURE du decompile — les deux emissions
        # vivent dans des blocs DISTINCTS, avec des conditions distinctes :
        #   * `On(0xf)`  sous `(0 < local_7dc) || !HealthComponent.IsUnitWithHealthStat(cible)`
        #                 -> `local_7dc` = la valeur de retour de `FillUpStatComponent.Reduce`, donc
        #                    bien « reduction REELLEMENT appliquee > 0 » (porte ci-dessus, inchange) ;
        #   * `On(0x10)` sous `local_7e8 == 0` SEUL (plus le composant de stats et la liste d'events
        #                 non nuls) -- AUCUN terme `0 < local_7dc`. Et `local_7e8` vaut 1 des que
        #                 `degat_sante_demande < 1`, ou que l'octet `hitInfo+0x94` est non nul.
        # => le gate porte est le degat SANTE **DEMANDE** >= 1, PAS l'applique. La difference ne se voit
        # QUE sur un coup qui tombe sur une cible deja a 0 PV : le natif emet, le port ne le faisait pas.
        # MESURE qui tranche (`probe_221_haze_rng_flow.py`, `HazeCorruption_BonusHitAbility` : un coup
        # Toxic sur le cadavre, `Amount 0`) -- 19 confrontations (2 regimes k=0/k=1 x 15 seeds) : le
        # rang du flux qui suit le jet du coup bonus est un `Maybe(25)` d'`OnToxicDamageAbility`, et la
        # tuile de la CIBLE devient `Contaminated` exactement quand `NextBool` <= 25. Les bornes sont
        # exercees des DEUX cotes (seed 55 : valeur 25 -> pose ; seeds 123/64 : valeur 26 -> rien).
        # L'octet `hitInfo+0x94` reste NON modelise (residu nomme : il ne peut que RESTREINDRE).
        if int(total or 0) >= 1:
            # Consommateurs portes : `FleshmetalGunsTileEffectAbility` (pose DespoiledGround 0x5c4
            # pendant le round WarpHail) et, DEPUIS LE DE-FORK, les deux abilities GLOBALES de profil
            # `OnFireDamageAbility` (1016) / `OnToxicDamageAbility` (1203) — qui etaient appelees
            # IMPERATIVEMENT apres l'attaque, donc APRES les vecteurs de mort emis quelques lignes plus
            # bas. Cette place-ci est la place NATIVE, et l'ecart est OBSERVABLE (arbitrage live : ordre
            # bus 6/6 vs ordre imperatif 3/6, cf. la docstring de `damage_dealt_triggers`).
            # `is_first_hit` = « CE groupe de degat contient le coup d'index 0 » -> reproduit le gate
            # natif `IsFirstHitInSeries` sans derouler les coups.
            attack_dispatch.damage_dealt_triggers(
                state, attacker_id, target_id, profile=profile,
                is_first_hit=is_first_hit, triggering_effect=triggering_effect)
        death = AttackDamageOperation._fire_death_if_killed(
            state, target_id, attacker_id, hp_before, thc.hp, tgt, damage=total,
            # `AbilityOrEffect` de la `DamageSource` du coup letal (`GetDamageSourceAbility`) : ce que
            # `KillUnitOperation$$RecordDeathReason` grave sur la victime pour `HasDeathReason`.
            source_ability=source_ability,
            # #R33 : decomposition PAR COUP (`_run_hits`) — le natif evalue `didOverkill` coup par coup
            # avec le crit ET le `deniedDamage` DE CE COUP. `None` (DoT, knockback, coups additionnels)
            # -> degenerescence en un coup non-critique, = comportement anterieur.
            hits_result=hits_result, is_force_overkill=is_force_overkill)
        if is_attack:
            AttackDamageOperation._record_attacked(state, target_id)    # #G6a : compteur + revert du floor
            # #509 : le VOLET ATTAQUANT de la MEME operation native. `IdunBattle.Operations.
            # RegisterAttackOperation$$Execute` appelle `ActorStatisticsComponent$$RegisterAttackMade`
            # (attaquant) PUIS `...$$RegisterAttackReceived` (defenseur) -- `_record_attacked`
            # ci-dessus ne portait que le second. Meme gate `is_attack` (meme operation, donc meme
            # gate par FAMILLE : un DoT n'est pas une attaque). Ecrit `turns_with_attacks_made`
            # (+0x30), `attacks_made_this_turn` (+0x24), `total_attacks_made` (+0x20, #926) et
            # `units_attacked_this_turn` (+0x40) ; lecteurs portes :
            # `MartialInspiration_ExtraDamageEffect` via `TotalTurnsWithAttacksMadeFormula`, et
            # `FirstAmongTraitors_ExtraDmgEffect` via `TotalAttacksMadeFormula` (#926).
            register_attack_made(state, attacker_id, target_id)
        AttackDamageOperation._register_received_damage(
            state, target_id, profile, total, shield_dmg, armor_dmg)
        AttackDamageOperation._record_last_hit_damage_taken(
            state, target_id, total, shield_dmg, armor_dmg, last_hit)
        AttackDamageOperation._register_damaged_this_phase(
            state, attacker_id, target_id, total, shield_dmg, armor_dmg)
        AttackDamageOperation._refresh_swarm(state, target_id)          # #60 : On(UnitMemberDeath=47)
        # #100 : `IdunBattle.Operations.RefreshEffectsOperation` (volet stat-modifier) — les PV viennent
        # de changer, donc les `CreateActiveCondition` qui lisent `StatAmount(Self, HEALTH, CURRENT_PCT)`
        # peuvent basculer. Cas porte : `AnvilShield_BlockChanceBelowHealthCap` (1200) dont la
        # contribution BLOCK_CHANCE (+20) doit ENTRER quand Arjac tombe sous 35 % PV (et sortir s'il
        # repasse au-dessus). Idempotent/no-op pour tout autre effet (cf. refresh_effects.py).
        refresh_stat_modifier_effects(state, target_id)
        return death

    @staticmethod
    def _register_received_damage(state: State, target_id: int, profile: Optional[str],
                                  health: int, shield: int = 0, armor: int = 0) -> None:
        """#202 : mirror `IdunBattle.Operations.RegisterDamageOperation$$Execute` -> `ActorStatisticsComponent.
        IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterReceivedDamage` : incremente `received_damage_this_turn[profil]` de la CIBLE
        (TryAdd(profil,1) sinon +1). Consomme par le selecteur `UnitsThatTakenDamageThisTurn IdunBattle.Entities.Formulas.UnitsThatTakenDamageThisTurnSelector$$Select`
        (WeaverOfFate : ContainsKey(Psychic) — seule la PRESENCE de la cle compte). Enregistre quand du
        degat a ete inflige (sante OU bouclier OU armure-pool > 0) — le gate exact du natif (enqueue de
        l'op par le pipeline, dispatch virtuel invisible aux xrefs) est un RESIDU documente (case-202 §6),
        sans effet tant que seul WeaverOfFate lit le dict (cle Psychic posee par de VRAIS degats)."""
        if not profile or (health <= 0 and shield <= 0 and armor <= 0):
            return
        ent = state.get_entity(target_id)
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if uc is None:
            return
        try:
            pid = int(DamageProfileType[profile])
        except KeyError:
            return                                  # profil inconnu -> pas de cle (fidele : enum natif)
        d = uc.received_damage_this_turn
        d[pid] = d.get(pid, 0) + 1

    @staticmethod
    def _record_last_hit_damage_taken(state: State, target_id: int, health: int,
                                      shield: int = 0, armor: int = 0,
                                      last_hit: Optional[int] = None) -> None:
        """Mirror des DEUX ecritures que `IdunBattle.Operations.ApplyDamageOperation$$Execute` fait
        sur l'`ActorStatisticsComponent` de la VICTIME (`local_528` = le composant de `param_4`) :

            *(int *)(stats + 0x68) = (int)*param_1;   # lastHitDamageTaken (all-time, non porte)
            *(int *)(stats + 0x6c) = (int)*param_1;   # lastHitDamageTaken THIS TURN  <- porte ici

        `(int)*param_1` = 1er champ du `DamageAppliedResult` = la SOMME des reductions REELLEMENT
        appliquees par CE COUP (`FillUpStatComponent$$Reduce` sante + 2e pool +
        `IdunBattle.Operations.ApplyDamageOperation$$ReduceShield`) -> `last_hit` = `per_hit[-1]` de
        `AttackDamageOperation._run_hits` (qui somme exactement PV + bouclier + armure-pool par coup).

        GRANULARITE : le natif ecrit PAR COUP, le port n'a qu'un chokepoint PAR ATTAQUE -> les callers
        qui connaissent la decomposition passent `last_hit` (le DERNIER coup) ; ceux qui n'ont qu'un
        coup unique (DoT `execute_direct`, knockback `displace`) laissent None et la degenerescence
        `health + shield + armor` est alors EXACTE. Un caller multi-coups qui oublierait `last_hit`
        surestimerait (total de l'attaque au lieu du dernier coup) -- c'est pour ca que la valeur est
        explicite, jamais devinee.

        Le roulement `@+0x6c -> @+0x70` est fait au turn-start du proprietaire
        (`StartTurnOperation.execute`, mirror `IdunBattle.Operations.StartTurnOperation$$ResetUnit`).
        Consommateur : la regen `TimeFlux` (`LastHitDamageTakenLastTurn`)."""
        # INCONDITIONNEL — la chaine de gardes au-dessus de l'ecriture native (remontee au decompile :
        # `if (local_768 != 0)` puis 4 tests de NON-NULLITE de pointeurs) ne contient AUCUN
        # `if (degat > 0)` : un coup entierement bloque ECRASE la valeur precedente par 0.
        amount = int(last_hit) if last_hit is not None else int(health) + int(shield) + int(armor)
        ent = state.get_entity(target_id)
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if uc is not None:
            uc.last_hit_damage_taken_this_turn = amount

    @staticmethod
    def _register_damaged_this_phase(state: State, attacker_id: Optional[int], target_id: int,
                                     health: int, shield: int = 0, armor: int = 0) -> None:
        """Alimente la `List<BEntityId>` @`ActorStatisticsComponent + 0x48` de l'ATTAQUANT (« unites
        endommagees pendant CETTE phase ») -- la source du selecteur
        `IdunBattle.Entities.Formulas.UnitsDamagedThisPhaseSelector$$Select`
        (`IdunBattleLogic.Entities.DSLFactory$$UnitsDamagedThisPhase(attacker)`). Cote port la liste vit
        sur le `UnitComponent` de l'attaquant (`damaged_units_this_phase`, meme residu structurel que
        `received_damage_this_turn`, case-202 §6) et se vide au boundary de phase
        (`State.reset_trigger_phases`, mirror `IdunBattle.Operations.EndPhaseOperation$$ResetEntityPhase`
        qui `Clear()` CE champ dans la MEME boucle que `TriggeredAbilityComponent$$ResetPhase`).

        MEME gate que `_register_received_damage` (du degat a REELLEMENT ete inflige : sante OU bouclier
        OU armure) : le call-site natif exact (l'op enqueue par le pipeline) n'est pas isolable aux xrefs
        -- residu documente, sans effet observable tant que le seul consommateur porte (DoomSiren) tourne
        APRES son propre volet d'attaque. Liste SANS doublon (`OrderedSet`-like : un meme cible frappee
        par plusieurs coups n'y figure qu'une fois), ordre = ordre de premiere frappe."""
        if attacker_id is None or (health <= 0 and shield <= 0 and armor <= 0):
            return
        ent = state.get_entity(int(attacker_id))
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if uc is None:
            return
        if int(target_id) not in uc.damaged_units_this_phase:
            uc.damaged_units_this_phase.append(int(target_id))

    @staticmethod
    def _apply_max_out(state: State, attacker_id: int, hit_nc: "HitDamage",
                       hit_cr: "HitDamage") -> tuple:
        """#202 WeaverOfFate : mirror de la branche max-out des DEUX foyers de degat natifs
        (`IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$GetDamage` / `IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$GetDamage`) :
        si `IsAttackMaxOutDamage(attaquant) == true`, le HitDamage est construit `(max, null)` — le noeud
        est invoque sur son slot GetMaxDamage, AUCUN tirage. Port = degenerer les bornes a (max, max) :
        - voie `get_damage` (limits None / ability roll-then-reduce) : min==max -> AUCUN tirage consomme,
          comme le natif (`IdunBattle.Core.HitDamage$$GetDamage` gate min==max) ;
        - voie slot-8 mode-1 (#67, limits actifs) : le tirage TOUJOURS consomme tire dans [max, max] —
          consommation RNG bit-exacte preservee (IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage sans gate).
        La branche crit d'`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` prend aussi le max comme base (uVar26 = struct.max) —
        couvert par la degenerescence de `hit_cr`. No-op (retourne les bornes inchangees) si l'attaquant
        n'a pas l'effet 1185 (cas courant).

        ⚠ CE FOYER NE PORTE QUE LA BRANCHE EFFET. La SECONDE branche du meme natif
        (`HasTriggeredAbility(1494 ParagonSpear)`, #1013) n'a PAS la meme portee : elle rend le champ
        `isCritical` de l'`AbilityEntities`, donc elle ne vaut QUE pour un coup CRITIQUE et se decide
        PAR COUP. La degenerer ici serait faux dans les deux sens -- degenerer `hit_nc` maxerait les
        coups NON critiques (que la mesure live montre VARIABLES et deja bit-exacts), et degenerer
        `hit_cr` seul ne maxe rien du tout, `hit_cr` ne servant que de SHIFT (`hit_cr - hit_nc`).
        Elle vit donc dans `damage_hits._run_hits(max_out_on_crit=...)`, au point exact ou
        `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` l'intercale : apres le tirage et
        le crit-roll, avant `CalculateCriticalDamage`."""
        from .triggers.loki.weaver_of_fate import is_attack_max_out_damage   # lazy : cycle damage<->triggers
        if not is_attack_max_out_damage(state, attacker_id):
            return hit_nc, hit_cr
        return HitDamage(hit_nc.max, hit_nc.max), HitDamage(hit_cr.max, hit_cr.max)

    @staticmethod
    def _max_out_on_crit(state: State, attacker_id: int) -> bool:
        """#1013 -- pendant PAR COUP d'`_apply_max_out` : la branche
        `HasTriggeredAbility(1494 ParagonSpear)` d'
        `IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage`, que le natif gate sur le champ
        `isCritical` de l'`AbilityEntities`. Les trois vecteurs d'attaque la transmettent a
        `damage_hits._run_hits(max_out_on_crit=...)`, qui l'applique au point exact ou
        `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` l'intercale.

        Meme import LAZY que `_apply_max_out` ci-dessus, et pour la MEME raison mesuree (cycle
        `damage <-> triggers`) -- pas un idiome recopie."""
        from .triggers.loki.weaver_of_fate import is_attack_max_out_damage_on_crit  # lazy : idem
        return is_attack_max_out_damage_on_crit(state, attacker_id)

    @staticmethod
    def _record_attacked(state: State, target_id: int) -> None:
        """#G6a : la cible vient d'encaisser une ATTAQUE (via `execute`/`execute_ability_attack`/
        `execute_normal_like` ; PAS un DoT `execute_direct`) -> incremente son compteur d'attaques du tour +
        re-eval l'ActiveCondition du HP-floor Hypersensory (attacked>=1 -> RevertInternal efface le plancher ->
        le coup SUIVANT peut tuer). Lazy import (cycle damage<->minimal_health)."""
        record_attacked(state, target_id)

    @staticmethod
    def _target_shield(tgt) -> tuple:
        """(ShieldComponent|None, total) du bouclier COURANT de la cible — `IdunBattle.Entities.UnitExtensions$$GetShield /
        `IdunBattle.Entities.Components.ShieldComponent$$GetTotalShield. 0 si pas de composant (rétro-compat : cibles sans bouclier)."""
        shc = tgt.get_component(ShieldComponent) if tgt is not None else None
        return shc, (shc.get_total_shield() if shc is not None else 0)

    @staticmethod
    def _deplete_shield(shc, shield_dmg) -> None:
        """`IdunBattle.Operations.ApplyDamageOperation$$ReduceShield(unit, amount)` -- la depletion
        du bouclier de l'absorbe. Le coup reduit l'instance, l'expiration a 0 passe par `deplete`.

        #1020-r1 -- CE FOYER A CHANGE DE PLACE, ET C'EST LA CORRECTION. Il etait appele par les
        APPELANTS, **avant** le chokepoint, sur le degat CALCULE (`run_result['shield_dmg']`). Le
        natif, lui, l'appelle **apres** l'emission d'`On(0x39 = EventTriggerType.PreDamageTaken)`,
        sur le pending RELU -- exactement comme son voisin `Reduce`, et depuis le MEME
        `GetValueOrDefault` :

            GetValueOrDefault(healthComp[+0x64], &pending);        // relecture APRES l'emission
            local_7c8 = FillUpStatComponent$$Reduce(hp, pending.healthDamage);
            ApplyDamageOperation$$ReduceShield(this, target, pending.shieldDamage);

        Un coup CONSOMME par `IdunBattle.Operations.TransferDamageOperation$$GetDamage` met les DEUX
        parts a zero (`*(qword*)(comp+0x64) = 0` et `+0x6c`), donc le natif n'enleve NI PV NI
        BOUCLIER. Le port n'annulait que les PV : la victime d'un transfert perdait un bouclier
        qu'elle aurait du garder.

        SECOND EFFET, LU AU MEME ENDROIT : ce foyer passe desormais SOUS le gate `Overkilled` du
        SITE (A), qui `return` **avant** l'ecriture du pending. Une cible deja overkillee ne perd
        donc plus son bouclier -- ce que le natif ne faisait deja pas.

        `shield_dmg` est un ENTIER (le montant RELU), plus un `run_result` : le dict portait le
        degat calcule, et c'est precisement la valeur qu'il ne faut plus lire ici."""
        if shc is not None and int(shield_dmg or 0) > 0:
            shc.deplete(int(shield_dmg))

    @staticmethod
    def _block_sources(tsc, tgt_active_effects, defender_armor: int, damage_profile=None,
                       defender_max_health: int = 0):
        """Sources de block du DEFENSEUR pour `apply_random_block_damage` : block de BASE (scalaire
        `GetStat(7/8)` -> ctx.block_chance/block_damage) PUIS les sources SUPPLEMENTAIRES posees par ses
        effets (`AddExtraBlockEffectToOwner`, ex. BeastSlayer IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSlayerAbility$$CreateAddBlockEffectBehaviour : chance beastSlayerBlockChance /
        amount = blockDmgPct% du FixedArmor courant) — ABSENTES du scalaire (verifie live orksNob
        blockChance=0), que le natif tient dans `GetMultiValueStat(7)` (`IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances`).
        ORDRE : base d'abord, effets ensuite (cible sans block de base -> effet = seule source, ordre moot).
        None si aucune source (retro-compat : 0 tirage). Consomme par les 3 vecteurs (normale/ability/splash). #72.

        #65 : GATE `NoBlocking` (DamageTrait 0) du PROFIL de degat — un profil NoBlocking (ex. `Psychic`,
        Traits=['NoBlocking'], PiercingRatio 100 ; cf. wiki « Cannot be blocked ») BYPASSE le block. Mirror
        de `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` : `DamageProfile.HasTrait(0=NoBlocking)` pose le flag
        (metadata +0x2a) qui SKIP toute la branche block/evade de `IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation`
        (`if ((metadata>>0x30)==0) { ...block/evade... }`). AUCUN tirage block consomme => 0 tirage RNG (le
        natif ne roule pas le block). Sans ce gate, l'offline sur-roulait un block spurious sur les attaques
        Psychic (seed 123 u95 astraPrimarisPsy -> u79 genesKelermorph BeastSlayer : off 1569 vs live 2873).
        Cable dans les 3 vecteurs (execute/execute_ability_attack/execute_normal_like) via `damage_profile`.

        #221 : l'`Attack` COURANTE du defenseur est THREADEE aux sources d'effet. Le natif construit la
        liste par `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances(attacker, defender,
        failedBlockIds)` = `defender.GetMultiValueStat(7)` -> `IdunBattle.Entities.Components.
        MultiValueStatComponent$$GetAllValues`, qui ajoute D'ABORD l'entree PAR DEFAUT
        `{entityId 0, GetStatPart(comp7, Current)}` (= le scalaire GetStat(7)) puis les entrees
        PAR-ENTITE du dictionnaire (une par effet ExtraBlock). L'amount d'une entree vient de
        `IdunBattle.Entities.UnitExtensions$$GetBlockDamageForBlockChance` = `comp8.GetValueByEntity(
        entityId)` avec fallback `comp8.GetDefaultEntry()` (= GetStat(8)).
        `Daemon_ExtraBlock` (0x40a) est pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.
        DaemonAbility$$CreateUpdateEffectBehaviour` = `AddExtraBlockEffectToOwner(0x40a,
        Direct(GetNumberConstant(0x2d=daemonBlockChance)), GetBlockDamage())` avec
        `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonAbility$$GetBlockDamage` =
        `PercentageOf(StatAmount(Self@0x148, statType=0=Attack, statPart=0=Current),
        Direct(GetNumberConstant(0x36=daemonBlockDamagePercentage)))`. Sans cette Attack, l'amount
        tombait a 0 -> `DaemonExtraBlockEffect.create_effect_block_source_for_defense` renvoyait None
        -> la source DISPARAISSAIT et le port SAUTAIT le jet de block que le natif roule
        (+1 tirage natif par attaque contre toute unite Daemon, et desync RNG de tout l'aval).
        `ctx.attack` == `GetStat(ATTACK=0, Current)` == le `StatAmount` du DSL (fold documente : le
        natif fige l'amount dans le MultiValueStat a la pose et le RAFRAICHIT sur l'event 0x3b via
        `DaemonAbility$$GetUpdateEffectCondition` = `Not(AmountIsEqual(MultiStatValueFromEffect(0x40a,
        8), GetBlockDamage()))` -- l'entree vaut donc TOUJOURS l'Attack courante).

        `block_id` = le `BEntityId` natif de la source (`BlockChanceInfo.entityId` @+0x0, la cle du
        `failedBlockIds: List<BEntityId>` teste par `Contains`), PAS la chance : entree par defaut =
        **0** (les 4 octets bas laisses a zero par `GetAllValues`), source d'effet = son entite-effet
        (offline : son `effect_type`, cf. `BaseEffect.block_source_id`). Deux sources de MEME chance
        (ex. defenseur Daemon dont le scalaire vaudrait 25) etaient auparavant confondues par le filtre
        d'exclusion inter-coups de `_run_hits` -> un tirage perdu des le coup 2.

        TRI : `CalculateBlockChances` termine par `list.Sort(DamageCalculations.<>c.
        <CalculateBlockChances>b__15_0)` dont le corps est `mov eax,[r8+8]; sub eax,[rdx+8]; ret` =
        `b.blockDamage - a.blockDamage` => **decroissant par AMOUNT**. C'est l'ordre dans lequel
        `ApplyRandomBlockDamage` tente les sources, donc l'ordre des tirages. Tri STABLE ici (Python)
        -> a amount egal, l'ordre pre-tri (base puis effets, = l'ordre de `GetAllValues`) est conserve ;
        le `List.Sort` natif est un introsort NON stable, ecart possible seulement a >=3 sources de
        meme amount (jamais observe -- residu documente)."""
        if damage_profile is not None:
            import gameconfig as GC
            _dp_traits = (GC.damage_profile(damage_profile) or {}).get("Traits") or []
            if DamageTrait.NoBlocking.name in _dp_traits:
                return None            # profil NoBlocking -> block bypasse (0 tirage), mirror ExecuteHit
        if tsc is None:
            return None
        block_chance = int(getattr(tsc.ctx, "block_chance", 0) or 0)
        block_amount = int(getattr(tsc.ctx, "block_damage", 0) or 0)
        sources = []
        if block_chance > 0 and block_amount > 0:
            # entree PAR DEFAUT de `GetAllValues` : entityId = 0, chance = GetStat(7), amount = GetStat(8).
            sources.append(BlockSource(chance=block_chance, amount=block_amount, block_id=0))
        # #1015-r1 : `defender_max_health` = `GetStat(cible, Health, Maximum)` = `HealthComponent.
        # hp_max` (le maximum COURANT, modifications comprises), threade par les 3 vecteurs depuis
        # leur `thc`. MEME raison que l'Attack de #221 : sans lui, `BeastSnagga_ExtraBlock` rendrait
        # `None`, la source DISPARAITRAIT et le port sauterait un jet de block que le natif roule
        # (desync RNG de tout l'aval, pas seulement du block).
        sources.extend(defender_effect_block_sources(
            tgt_active_effects, defender_armor,
            defender_attack=int(getattr(tsc.ctx, "attack", 0) or 0),
            defender_max_health=int(defender_max_health or 0)))
        # `list.Sort((a,b) => b.blockDamage - a.blockDamage)` de CalculateBlockChances (decroissant).
        sources.sort(key=lambda s: -int(s.amount or 0))
        return sources or None

    @staticmethod
    def _crit_params(ctx, attacker_effects, state: Optional[State] = None,
                     att_id: Optional[int] = None, tgt_id: Optional[int] = None,
                     is_ranged: Optional[bool] = None,
                     is_normal_attack: Optional[bool] = None,
                     hit_index: Optional[int] = None) -> tuple:
        """(crit_chance, crit_damage, crit_enabled) de l'ATTAQUANT — GetStat(9/10) + bonus calc-time des
        effets (`IdunBattle.Core.Services.DamagePrediction$$GetCritChanceBonusFromEffects` / `IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects`) ;
        `crit_enabled` = le gate de `IdunBattle.Core.Services.DamagePrediction$$RollCritical`
        (`cc post-bonus >= 1`), et NON `IdunBattle.Core.Services.DamageCalculations$$CouldCrit`, qui
        n'est pas sur le chemin d'execution d'un coup (#950, cf. le bloc en fin de fonction).
        Partage par les 3 vecteurs (normale/ability/splash).

        CONTEXTE DU CANAL CRIT (`att_ctx`) -- **FOYER UNIQUE**, pose ICI et nulle part ailleurs.
        `_crit_params` est a l'axe CRIT ce que `runner/damage_model.py::build_hits_board` est a l'axe
        COUPS : la facade COMBAT PARTAGEE des trois vecteurs d'attaque (`damage_ops/normal.py`,
        `damage_ops/ability.py`, `damage_ops/normal_like.py`). Un seul point de calcul, pas un par
        call-site ; les vecteurs ne transmettent que les IDENTITES du coup.

        C'est aussi la place NATIVE. `IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage(
        this, attaquant, cible, ...)` passe **les deux entites** a `GetCritDamageBonusFromEffects`, qui
        construit LUI-MEME l'`IdunBattle.Entities.Abilities.AbilityEntities` (caster = owner =
        l'attaquant, target = la cible) avant d'evaluer le trigger de chaque `EffectBonus` via le slot
        d'interface `IdunBattle.Entities.Effects.BaseEffect$$CritDamageBonus`. Le canal natif n'est donc
        PAS aveugle : `get_OwnerIsCaster`, `IsCharging(owner@0x148, target@0x178)`, `HasTrait(target, ...)`
        y sont tous evaluables. C'etait le PORT qui perdait le contexte (residu `N14`).

        `state`/`att_id`/`tgt_id` absents (appelant historique, probe) -> la cle `is_charging` n'est
        PAS posee et son gate se tait (« present != applique ») : aucune contribution
        inconditionnelle possible. Le gate reutilise le FOYER du predicat, il ne le duplique pas :
        `damage_model.battle_query_is_charging` -> `engine/battle_query.py::is_charging`, le MEME que
        les canaux DEGAT et COUPS.

        MEME FOYER POUR LA CHANCE DE CRIT (case-366-r1). `IdunBattle.Core.Services.DamagePrediction$$
        GetCritChanceBonusFromEffects(this, attaquant, defenseur, abilityOrEffect, hitIndex)` batit
        LUI AUSSI son `IdunBattle.Entities.Abilities.AbilityEntities` (caster = owner = l'attaquant,
        target = le defenseur) avant d'evaluer le trigger de chaque `EffectBonus` : le canal natif
        n'est donc pas plus aveugle que celui du DEGAT de crit. Trois cles de plus, chacune UN noeud
        DSL et non un besoin d'effet :
          * `is_ranged`          -> `IsMeleeAttack` / `IsRangedAttack` (tri-etat #106 : `None` =
            nature non threadee par le vecteur appelant -> les DEUX gates se taisent) ;
          * `is_normal_attack`   -> `IsNormalAttack` (meme valeur que celle passee a
            `attacker_modifiers` par le MEME vecteur, pour que les deux canaux ne divergent pas) ;
          * `caster_crit_chance` -> `StatAmount(Caster, 0x9 CriticalChance, StatPart.Current)`.
            LU ICI et pas chez l'appelant : c'est le seul point qui voit le `UnitContext` de
            l'attaquant APRES l'event `On(PreAttackHit=6)` (ThrillSeekers pose un stat-mod de crit
            juste avant), donc la meme valeur que celle que le natif lit dans `RollCritical`.
        Porteur : `WarHowl_ExtraDamage_Unstoppable` (1222), dont le trigger porte les trois.
          * `has_moved` -> `HasFlag(Owner, 0 = UnitFlag.Moved)`, le predicat de la
            `CreateActiveCondition` de `InescapableAccuracy_extraCritChance` (1115). Pose des que
            l'ATTAQUANT est identifie ; lu du store UNIQUE `UnitFlagsComponent` (`unit_has_moved`),
            le MEME que le gate deja porte de `CrushingStrike`/`HeavyWeapon_ExtraDmg` sur l'axe
            DEGAT -- les deux axes ne peuvent donc pas diverger.

        BALAYAGE BOARD-WIDE (#589-r1-r1). Les deux canaux natifs construisent leur `AbilityEntities`
        en `(attacker, attacker, defender)` puis, dans leur boucle sur les effets, **ECRASENT
        `AbilityEntities+0x18` (`Owner`) par le porteur de l'effet courant** -- exactement la boucle
        `effets x cibles` que `case-366-r1-blockhits-purgeresponse` a relue sur
        `DamagePrediction$$GetAttackHits`. Le porteur n'est donc PAS forcement l'attaquant, et
        `EmpyricAmbush` (1578) est justement porte par la CIBLE (`get_OwnerIsTarget`). L'univers du
        balayage est aligne sur `EffectsQuery$$GetActiveEffectsWithBonuses` via
        `board_effect_carriers`, et `get_OwnerIsCaster` a MIGRE dans les classes qui le portent
        (1115, 1116, 1222, `SagaOfTheWarriorBorn_Owner`).

        Les cles du trigger de 1578 sont posees ICI, au meme foyer, chacune UN noeud DSL :
          * `att_id` / `tgt_id`      -> `get_OwnerIsTarget` (via `owner_id`) et
            `NOT AreEqual(Caster, EffectSource)` ;
          * `att_team` / `tgt_team`  -> `AreEnemies(Caster, Target, 0 = ByCurrentTeam)` ;
          * `team_by_id`             -> `AreFriends(Caster, EffectSource)` -- la SOURCE de l'effet
            est un id quelconque du board, seul un mapping peut rendre son equipe (meme substrat que
            `build_hits_board`, qui pose deja `team_by_id` sur l'axe COUPS) ;
          * `att_faction`            -> `HasFaction(Caster, 8 = Aeldari)`. MEME source
            (`FactionId` du gameconfig) que les canaux DEGAT et COUPS ;
          * `att_traits`             -> `HasTrait(Caster, 0x10 = Hero)`. Substrat d'ENTITE
            (`entity_trait_names`), pas le kit gameconfig -- #264 ;
          * `tiles_moved_this_turn`  -> `TilesMovedThisTurn(Caster)`, lu du compteur REEL de l'ECS
            (`unit_tiles_moved_this_turn`), le MEME store que l'axe DEGAT (`attacker_modifiers`)."""
        att_ctx = {"is_ranged": is_ranged, "is_normal_attack": is_normal_attack,
                   "caster_crit_chance": int(ctx.stat(StatType.CRIT_CHANCE) or 0),
                   "att_id": att_id, "tgt_id": tgt_id,
                   # #889 -- `hit_index` = le **5e argument natif** de `IdunBattle.Core.Services.
                   # DamagePrediction$$GetCritChanceBonusFromEffects(this, attaquant, defenseur,
                   # abilityOrEffect, hitIndex)`, que la couche `EffectBonus` expose au noeud
                   # `IdunBattleLogic.Entities.DSLFormulas$$CurrentHitIndex`. Porteur :
                   # `IdunBattle.Entities.Effects.Loki.TheLionsWrath_ExtraCritChanceEffect$$
                   # CreateCritChanceBonus` = `ForAddition(get_OwnerIsCaster & AmountIsEqual(
                   # CurrentHitIndex(), <DSLFormulas+0x20> = Direct(1)), ConfigVar(0x3a = chance))`.
                   # Tri-etat : `None` = index NON THREADE par le vecteur appelant -> le noeud est
                   # FAUX, jamais permissif (meme discipline que `is_ranged` / `caster_crit_chance`).
                   "hit_index": hit_index}
        carriers = [(att_id, attacker_effects)]
        if state is not None and att_id is not None:
            att_ctx["has_moved"] = unit_has_moved(state, int(att_id))
            att_ctx["tiles_moved_this_turn"] = unit_tiles_moved_this_turn(state, int(att_id))
        if state is not None and att_id is not None and tgt_id is not None:
            att_ctx["is_charging"] = battle_query_is_charging(state, int(att_id), int(tgt_id))
        if state is not None:
            att_ctx.update(AttackDamageOperation._crit_board(state, att_id, tgt_id))
            carriers = AttackDamageOperation._crit_carriers(state, att_id, attacker_effects, tgt_id)
        # #950 -- LA CRIT-DAMAGE NE GATE PAS LE TIRAGE, ELLE EST CLAMPEE A ZERO. Les deux lectures
        # natives sont relues VERBATIM sur `rnca9r7q6c`, et elles portent sur des AXES DIFFERENTS :
        #
        #   `IdunBattle.Core.Services.DamagePrediction$$RollCritical(attacker, defender, ability,
        #    hitIndex)` = `cc = GetStat(9) + GetCritChanceBonusFromEffects(...)` puis
        #        `if (cc < 0) false ; if (cc >= 101) cc = 100 ; if (cc < 1) false ; NextBool(cc)`
        #        -- la SEULE grandeur qui puisse supprimer le TIRAGE est la CHANCE post-bonus ;
        #   `IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage`
        #        = `System.Math.Max(0, GetStat(10) + GetCritDamageBonusFromEffects(...))`
        #        -- la crit-DEGAT est simplement PLANCHEE a 0, jamais un gate.
        #
        # (`IdunBattle.Core.Services.DamageCalculations$$CouldCrit(attacker)` = `GetStat(9) > 0 &&
        # GetStat(10) > 0` n'a QUE des xrefs DATA : il n'est invoque que par slot d'interface, PAS
        # sur le chemin d'execution d'un coup -- constat deja etabli et MESURE par
        # `entities/effects/loki/inescapable_accuracy.py`, ou `GetStat(9) == 0` crite quand meme.)
        #
        # Le port passait `could_crit(cc, cd)` : le conjoint `cd > 0` y SUPPRIMAIT le tirage des
        # qu'une reduction de crit-DEGAT rendait `cd <= 0`, donc DESYNCHRONISAIT le flux PRNG de
        # toute l'attaque (un `NextBool` de moins par coup) -- pas seulement le degat. Le gisement
        # etait INATTEIGNABLE tant qu'aucun effet porte ne poussait `cd` sous zero ; `ToughToKill`
        # (1472) le fait (`critDmgReduction[50] x 160 % = 1330` contre un `GetStat(10) = 700`).
        # MESURE (probe_950, bras `ttk`) : natif `[1619, 1789, 1355, 1624, 1215, 1352]` avec
        # `Attack_DidCrit = 1` sur les deux premiers coups, port `[1415, 1619, 1515, 1789, 1397,
        # 1355]` -- SIX coups divergents, dont l'ORDRE trahit le decalage de flux. Apres correctif :
        # egalite a l'unite.
        # ⚠ Le conjoint CHANCE, lui, RESTE post-bonus : c'est exactement le gate de `RollCritical`,
        # et c'est ce qui fait criter un `eldarMauganRa` a `GetStat(9) == 0` porte a 15 par
        # `InescapableAccuracy_extraCritChance` (mesure live, `test_inescapable_accuracy_crit_chance
        # _live.py`). Le remplacer par les stats BRUTES eteindrait ce canal -- essaye, et les quatre
        # cas de ce fichier rougissent.
        cc = ctx.stat(StatType.CRIT_CHANCE) + crit_chance_bonus_from_effects(carriers, att_ctx)
        cd = max(0, ctx.stat(StatType.CRIT_DAMAGE)
                 + crit_damage_bonus_from_effects(carriers, att_ctx))
        return cc, cd, cc >= 1

    @staticmethod
    def _crit_board(state: State, att_id, tgt_id) -> dict:
        """Substrat d'ETAT du canal CRIT : les cles que le trigger d'un `EffectBonus` peut lire sur
        les DEUX entites du coup. Mirror des slots `Caster@DSLSelectors+0x48` /
        `Target@+0x60` de l'`AbilityEntities` que les canaux natifs batissent.

        Meme sources que les canaux DEGAT et COUPS, jamais re-derivees : `OwnerComponent.team`,
        `FactionId` du gameconfig, `entity_trait_names` (substrat d'ENTITE -- #264 : les traits en
        bataille != le kit).

        DEUX CALLABLES PAR-PORTEUR (#589-r1-r1-r2-r1), et ce sont des CALLABLES parce que la boucle
        native ECRASE `AbilityEntities+0x18` (`Owner`) a chaque iteration : la grandeur depend de
        l'INSTANCE d'effet qui interroge, pas seulement des deux entites du coup. Meme forme que
        `contagions_of_nurgle_amount` dans `UnitEffectStateView` (paresseux par construction : rien
        n'est calcule tant qu'aucune instance ne les appelle) :
          * `adjacent_friendly_summons_and_decoys_of(owner_id)` -> `...AmuletOfTheVoidwyrm_
            CritDamageReductionEffect$$GetAdjacentFriendlySummonsAndDecoysCount` (le MEME foyer que
            la cle du `unit_state`, donc la CONDITION et la MAGNITUDE ne peuvent pas diverger) ;
          * `tertiary_ability_state_of(owner_id, ability)` -> `GetAbilityState(effect)`, delegue au
            foyer UNIQUE `operations/triggers/base.py::triggered_ability_state` (#357) : etat
            TERTIAIRE pour une relique EQUIPEE, etat PASSIF pour un kit npc. Sans lui, une relique
            de niveau 3 lirait le niveau des PASSIFS du porteur (50 en runner normalise), donc le
            dernier palier -- un ecart SILENCIEUX de magnitude."""
        from .triggers.base import triggered_ability_state
        team_by_id: dict = {}
        for uid, e in state.entities.items():
            oc = e.get_component(OwnerComponent)
            if oc is not None:
                team_by_id[uid] = oc.team
        def _traits_of(eid):
            if eid is None:
                return None
            e = state.entities.get(int(eid))
            uc = e.get_component(UnitComponent) if e is not None else None
            sc = e.get_component(StatsComponent) if e is not None else None
            if uc is None:
                return None
            return entity_trait_names(sc.ctx if sc is not None else None, uc.visual_id)

        att_traits = _traits_of(att_id)
        # `tgt_traits` -- le PENDANT de `att_traits` sur le slot `Target@DSLSelectors+0x60`, meme
        # substrat d'ENTITE (`entity_trait_names`, jamais le kit gameconfig -- #264). Demandeur :
        # `IdunBattle.Entities.Effects.Loki.MartialExemplar_ExtraCritChanceEffect$$
        # CreateCritChanceBonus` = `ForAddition(get_OwnerIsCaster & HasTrait(Target@+0x60,
        # 0x2 = UnitTrait.Summon), ConfigVar(0x41 = extraCritChance))` -- le SEUL noeud CRIT du
        # depot dont le predicat porte sur un trait du DEFENSEUR. Tri-etat : `None` = NON MESURE,
        # et le porteur rend alors FAUX (jamais permissif). #889-r5.
        tgt_traits = _traits_of(tgt_id)
        return {"team_by_id": team_by_id,
                "att_team": team_by_id.get(att_id), "tgt_team": team_by_id.get(tgt_id),
                "att_faction": (_unit_gameconfig(state, att_id) or {}).get("FactionId"),
                "att_traits": att_traits, "tgt_traits": tgt_traits,
                _CTX_ADJACENT_FRIENDLY_SUMMONS_AND_DECOYS_OF:
                    lambda oid: adjacent_friendly_summons_and_decoys_count(state, int(oid)),
                # `...SupaCyborkBody_CritDmgReductionEffect$$GetCalculateLevel` (#503-r4) -- le
                # niveau que `RefreshEffectsOperation$$UpdateLevel` ECRIT dans
                # `EffectComponent+0x68`, donc celui que `DSLFormulas.EffectLevel` relit dans
                # `$$GetCritDamageReduction`. MEME forme paresseuse et MEME raison que le compteur
                # d'`AmuletOfTheVoidwyrm` : la grandeur depend de l'INSTANCE d'effet qui interroge
                # (la boucle native ECRASE `AbilityEntities+0x18` a chaque iteration).
                _CTX_ADJACENT_ENEMIES_OF:
                    lambda oid: adjacent_enemies_count(state, int(oid)),
                # #954 -- le `CreateTargetSelector` PARTAGE des deux effets d'`ObsessiveAnnunciation`
                # (`AdjacentEnemies(Owner@+0x30, unique: true, UnitSelectionType 3)`, corps FONDU par
                # l'ICF entre 1432 et 1433). CALLABLE, et PAR PORTEUR, pour la MEME raison que les
                # six compteurs ci-dessus : la boucle native ECRASE `AbilityEntities+0x18` (`Owner`)
                # par CHAQUE CIBLE de l'effet courant, donc `get_OwnerIsTarget` demande une
                # APPARTENANCE a cet ensemble -- pas un compte, et pas une identite avec le porteur.
                # C'est la SEULE cle de contexte neuve du lot #953/#954 sur cet axe.
                _OA_CTX_ADJ_ENEMY_IDS:
                    lambda oid: adjacent_enemy_ids(state, int(oid)),
                # `...NetherRealmCasket_CritDamageReductionEffect$$AdjacentMechanicalUnits` (#908) --
                # le slot virtuel `+0x5f8` que `$$CreateCritDamageBonus` appelle comme 2e facteur de
                # son `Multiply`, et que `$$CreateActiveCondition` compare a zero. MEME forme
                # paresseuse et MEME raison que les deux compteurs ci-dessus : la grandeur depend de
                # l'INSTANCE d'effet qui interroge (la boucle native ECRASE `AbilityEntities+0x18`).
                _CTX_ADJACENT_FRIENDLY_MECHANICAL_UNITS_OF:
                    lambda oid: adjacent_friendly_mechanical_units_count(state, int(oid)),
                # `...KardiocoreGalvanus_ExtraCritDmgEffect$$GetCalculateLevel` (#913) -- MEME role
                # et MEME forme paresseuse que les compteurs ci-dessus. DEUX differences, toutes
                # deux LUES : son porteur est du cote CASTER (`get_OwnerIsCaster`, pas TARGET), et
                # son arbre n'a **aucun** `NormalUnits` -- c'est pourquoi il ne reutilise PAS
                # `adjacent_friendly_mechanical_units_of` juste au-dessus, malgre des noms voisins.
                _CTX_ADJACENT_MECHANICAL_FRIENDS_OF:
                    lambda oid: adjacent_mechanical_friends_count(state, int(oid)),
                # `...MawClawsOfThyrax_ExtraCritDmgEffect$$GetCalculateLevel` (#920) -- MEME role
                # et MEME forme paresseuse que les compteurs ci-dessus. La difference est LUE et
                # elle est structurelle : son etage de voisinage est `AdjacentUnits`, dont le corps
                # (`Units(AdjacentTiles(origin), unique, sel) op_Subtraction origin`) ne filtre
                # AUCUN camp -- un summon ENNEMI adjacent compte. C'est pourquoi il ne reutilise ni
                # `adjacent_friendly_summons_and_decoys_of` (AMIS, et Decoy en plus) ni
                # `adjacent_mechanical_friends_of`, malgre des noms voisins.
                _CTX_ADJACENT_SUMMONS_OF:
                    lambda oid: adjacent_summons_count(state, int(oid)),
                # `...IntoxicatingElixir_ExtraCritDmgEffect$$GetCalculateLevel` (#922) -- MEME role
                # et MEME forme paresseuse que les compteurs ci-dessus. QUATRE differences, toutes
                # LUES : son disque est `SurroundingUnits(Tiles(Owner), range = 2, includeCenter:
                # 1)` (donc le PORTEUR se compte lui-meme), il n'a AUCUN filtre d'equipe (comme
                # celui de 1461 juste au-dessus, contre les trois autres), il filtre par EFFET
                # (`EntitiesWithAnyEffect`) et non par trait, et il est PLAFONNE (`Min(..., 6)`).
                _CTX_DEBUFFED_UNITS_IN_RANGE_OF:
                    lambda oid: debuffed_units_in_range_count(state, int(oid)),
                # `HealthPctIsBelowOrEqual(Owner@DSLSelectors+0x30, Get(healthPct))` --
                # `StatPercentageIsBelowOrEqualAbilityTrigger$$ShouldTrigger` lit `GetStat(5 =
                # Health, CURRENT)` et `GetStat(5, MAXIMUM)`. CALLABLE pour la MEME raison que les
                # compteurs : la grandeur porte sur le PORTEUR de l'instance d'effet, que la boucle
                # native reecrit dans `AbilityEntities+0x18` a chaque iteration -- pas sur les deux
                # entites du coup. Tri-etat : `(None, None)` = non mesure (aucun `HealthComponent`).
                # MEME substrat que la cle `hp`/`max_hp` du `unit_state`, pour que la MAGNITUDE et
                # les `is_active` a seuil de vie ne puissent pas diverger.
                _CTX_UNIT_HEALTH_OF: lambda oid: _health_of(state, oid),
                # #951 -- `StatAmount(Target@DSLSelectors+0x60, StatType.Health = 5,
                # StatPart.CurrentPct = 1)`, le premier operande du gate
                # `...TrophyTaker_ExtraCritDamageEffect$$HealthLowerThanPct`. Ce sont les PV de la
                # CIBLE DU COUP -- deux entites fixes, pas le porteur -> une PAIRE DE VALEURS et
                # non un callable, contrairement a `unit_health_of` juste au-dessus (qui, lui,
                # porte sur le PORTEUR que la boucle native reecrit a chaque iteration).
                # MEMES CLES et MEME substrat (`_unit_hp_and_max`) que le canal DEGAT, qui les
                # thread deja : les deux canaux du meme effet ne peuvent donc pas diverger sur le
                # seuil de vie. Tri-etat `(None, None)` = non mesure -> le gate se TAIT.
                "tgt_hp": _health_of(state, tgt_id)[0] if tgt_id is not None else None,
                "tgt_hp_max": _health_of(state, tgt_id)[1] if tgt_id is not None else None,
                _CTX_TERTIARY_ABILITY_STATE_OF:
                    lambda oid, ability: triggered_ability_state(state, int(oid), ability)}

    @staticmethod
    def _crit_carriers(state: State, att_id, attacker_effects, tgt_id) -> list:
        """Univers du balayage des deux canaux CRIT -- mirror de
        `IdunBattle.Core.Services.EffectsQuery$$GetActiveEffectsWithBonuses`, qui ne prend AUCUN
        argument de portee : elle enumere les entites-effet du monde, filtre sur
        `EffectComponent+0x5c` (`IsActive`) et rend `(effet, cibles)`.

        Meme construction que celle de l'axe COUPS (`build_hits_board` + `board_effect_carriers`) :
        VIVANTS seulement (#57m -- un mort n'est plus sur le board), cible conservee (vivante par
        construction d'une attaque), attaquant et cible en TETE, dedup par `owner_id`.

        ⚠ NON COUVERT, comme sur l'axe COUPS : les effets portes par une TUILE."""
        others: list = []
        target_effects: list = []
        for uid, e in state.entities.items():
            if uid == att_id:
                continue
            uc = e.get_component(UnitComponent)
            if uid != tgt_id and uc is not None and not uc.alive:
                continue
            effs = (state.effects.active_effects(uid, unit_state_for_effects(state, uid))
                    if state.effects is not None else [])
            if uid == tgt_id:
                target_effects = effs
            else:
                others.append((uid, effs))
        return board_effect_carriers(att_id, attacker_effects, tgt_id, target_effects, others)

    @staticmethod
    def _target_limits(tgt, thc, damage_profile: Optional[str] = None,
                       is_special: int = 1) -> Optional[dict]:
        """#67 : champs STATIQUES cible de l'etage LIMITES du COMBAT (`IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage`) — mirror ECS du `_target_damage_limits` de la PREDICTION (playbook/prediction.py),
        MEME etage partage (`services/trait_damage_limits.py`). Le natif applique cet etage a
        l'EXECUTION aussi : attaque normale via le per-coup d'`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (wrappers mode-1
        `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToAttackDamage/IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToAttackDamage`, virtual-only — l'execution
        reutilise la routine per-coup de prediction, cellules min/max capees AVANT la resolution),
        ability/splash via `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` (mode 2 : `ApplyTraitDamageLimitsTo
        Damage(2, &dmg, &dmg, profil, cible, ..., hp=hc+0x18, ...)`). `is_special` = le mode natif
        (1=attack -> Impervious applique ; 2=ability) — sans effet offline tant que
        `impervious_stat_current=None` (no-op documente, comme la prediction).
        None = fast-path retro-compat : cible mono-membre sans Resilient -> etage strictement no-op
        (Impervious charge / boss 0x5d4 = no-op documentes de toute facon).

        #264 -- les TRAITS viennent du substrat d'ENTITE (`entity_trait_names`), pas d'une relecture
        du kit gameconfig par visualId. Le natif lit `HasTrait(cible, Resilient)` sur le
        `BaseUnitComponent`, dont le contenu est celui de `BC.Units[].Traits` plus/moins ce que la
        bataille a accorde/retire -- pas le kit (les deux different, cf. `_load_unit_traits`). MESURE
        (2026-07-30) : `necroOverlord` porte `Resilient` au gameconfig et NE le porte PAS en
        bataille ; ce lecteur capait donc son degat a `HP-1` et le rendait IMPOSSIBLE A TUER
        offline, alors que le natif le tue. `nrOfMembers` reste gameconfig : ce n'est pas un trait
        (c'est `NumberOfMembersComponent`, autre canal, hors #264)."""
        tuc = tgt.get_component(UnitComponent) if tgt is not None else None
        if tuc is None or thc is None or not thc.hp_max:
            return None
        import gameconfig as GC
        gu = GC.unit(tuc.visual_id) or {}
        tsc = tgt.get_component(StatsComponent)
        utraits = entity_trait_names(tsc.ctx if tsc is not None else None, tuc.visual_id)
        n = int(gu.get("nrOfMembers") or 1)
        has_res = "Resilient" in utraits
        if n <= 1 and not has_res:
            return None
        _dp_traits = ((GC.damage_profile(damage_profile) or {}).get("Traits") or []
                      ) if damage_profile else []
        return {
            "is_special": int(is_special),
            "target_has_resilient": has_res,
            "target_has_impervious": "Impervious" in utraits,
            "impervious_stat_current": None,   # charge Impervious non captee offline -> no-op (comme la prediction)
            "member_count": n,                 # NumberOfMembersComponent (IdunBattle.Core.Services.DamagePrediction$$ApplyGroupUnitDamageLimit lit le composant cible)
            "member_total_hp": int(thc.hp_max),
            "profile_has_hits_multiple_members": DamageTrait.HitsMultipleMembers.name in _dp_traits,
            # `max_health` = param_11 du core : pour l'EXECUTION c'est le HP AU DEBUT DE L'ATTAQUE
            # (ancre per-attaque de l'executeur), PAS hpMax — discrimine live par probe 67201
            # (tour letal hp_depart 784 != hpMax 7530 : le coup rem=1 a TUE, seuil 2x784 ouvert ;
            # contre-datapoint 67111 hp_depart 1513 : rem=1 TENU a 0, seuil 2x1513 ferme). La
            # PREDICTION garde hpMax (son propre appelant PredictAttackRaw, valide tel quel).
            "max_health": int(thc.hp if thc.hp is not None else thc.hp_max),
            "target_has_boss_cap": False,      # HasTriggeredAbility(0x5d4) non verifie offline -> no-op
            "boss_cap_const": 0,
        }

    @staticmethod
    def _apply_defender_flat_reductions(mods, def_mods) -> None:
        """#120 : additif DÉFENSEUR plat PRÉ-perçage (Nightshroud_DmgReduction IdunBattle.Entities.Effects.Loki.Nightshroud_DmgReduction_Effect$$CreateDamageDefenseModifier =
        `ForSubtraction(OwnerIsTarget, ConfigVar 0x12=dmgReduction×mult)`) fusionné dans le slot additif
        @+0x10 — le MÊME que l'additif ATTAQUANT #75. `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` ne
        consomme @+0x10 qu'UNE fois, AVANT perçage. Mirror EXACT du merge PRÉDICTION
        (`_add_positional_and_defender_mods`, prediction.py:172) : on SOUSTRAIT de `mods.additive`
        (l'accumulateur ATTAQUANT, consommé pré-perçage via `attacker_additive_pre=True`) → la réduction
        est DILUÉE par perçage/armure PUIS scalée ×%-list UNE fois, comme l'additif #75. SANS pré-scale ×M
        (≠ ForAddition Neuroparasite, qui compense le placement post-%-list). Vide → no-op (rétro-compat)."""
        if def_mods.flat_reductions:
            mods.additive -= sum(def_mods.flat_reductions)
        # #462-r4b-r1 — L'ADDITIF DEFENSEUR (`Addition@+0x10` de `defenseModifiers`) EST DANS LE
        # MEME SLOT PRE-PERCAGE QUE CELUI DE L'ATTAQUANT. LU au decompile dans l'appelant
        # `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` : il resout les DEUX
        # accumulateurs par les slots d'interface 0xd et 0xe, lit le champ `+0x10` de CHACUN
        # (`FixMath.NET.Fix64$$op_Explicit` sur `<mods>+0x10`) et passe a
        # `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` la SOMME
        # `base + Addition(0xd) + Addition(0xe)` -- aux DEUX call-sites (borne MIN et borne MAX).
        # `CalculateBaseDamageWithAllModifiers` NE re-consomme PAS `+0x10` : il commence par
        # `GetBaseDamageWithFixedPiercedArmor`. L'additif defenseur traverse donc percage/armure PUIS
        # les %-list, EXACTEMENT comme l'additif attaquant (#75) -- ce que la PREDICTION fait deja
        # (`_add_positional_and_defender_mods` : `mods.additive += def_mods.additive`).
        # Le COMBAT, lui, le laissait a `apply_all_modifiers(., def_mods)`, qui l'ajoute APRES les
        # %-list et les deux `Multiplier` : un additif NI dilue par l'armure NI reduit par la face
        # defenseur. MESURE (`probe_462_r4b_r1_terminator_commanded_attack.py`, chaine
        # `ExemplarOfHate` sur `blackAbaddon`, trait `TerminatorArmour` x0.25) : port 7730 degats
        # contre 2596 natif, facteur 2,98 -- le `+997` d'`ExemplarOfHate_Target` echappait a la
        # reduction ET a l'armure. On DEPLACE donc l'entree (et on VIDE la source), comme pour
        # `flat_reductions` ci-dessus : `apply_all_modifiers(def_mods)` en aval devient un no-op sur
        # cet axe -- pas une double-application.
        # ⚠ Le natif tronque CHAQUE `Addition` separement (`op_Explicit` = `raw >> 32`) avant de
        # sommer ; le port somme des flottants puis arrondit dans `apply_pierce_and_modifiers`.
        # Aucun producteur porte ne rend une valeur fractionnaire (les trois passent par `int(...)`),
        # donc les deux se confondent aujourd'hui.
        if def_mods.additive:
            mods.additive += def_mods.additive
            def_mods.additive = 0.0
        # #462-r4a — LA FACE DEFENSEUR ENTRE DANS LA MEME CHAINE QUE LA FACE ATTAQUANT.
        # `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` compose
        # les listes `@0x18` des DEUX faces (etapes 1 puis 2) AVANT le moindre `Round`, et ne fait
        # intervenir un arrondi qu'aux etages MULTIPLICATEUR (`Multiplier@0x30`, etapes 3 et 4).
        # Le port appliquait la face defenseur dans un SECOND appel (`apply_all_modifiers`), donc
        # derriere l'arrondi de la premiere -- un `Round` surnumeraire des que les deux faces sont
        # non neutres. MESURE (`probe_462_r4a_terrifying_rounding.py --two-faces`, elevation x1.50
        # cote ATTAQUANT et `Terrifying_ExtraDefense` x0.70 cote DEFENSEUR, unites DEPLACEES pour
        # fabriquer le denivele) : natif 761/1141, chaine unique 761/1141, deux chaines 762/1142.
        # On DEPLACE donc les entrees (et on VIDE la source) : `def_mods` est un accumulateur local
        # reconstruit a chaque execution, exactement comme pour `flat_reductions` ci-dessus, et
        # `apply_all_modifiers(def_mods)` en aval devient un no-op sur cet axe -- pas une
        # double-application.
        # #437-r1-r1-r1 — LA FUSION NE DECIDE PLUS DE LA FACE, ELLE LA PRESERVE. `def_mods` porte
        # desormais SES DEUX faces separement (`add_modifier` route sur `EffectBonus.native_face`,
        # pose par le builder depuis la classe d'effet) : un effet que le natif verse dans
        # `attackModifiers` bien qu'il soit porte par la CIBLE -- `Terrifying_ExtraDefense`,
        # `MartialKatah_DmgReduction`, `Markerlight`, `DaughterOfTheAbyss_ExtraDamagePct` -- sort
        # d'ici dans `mods.pct_list`, pas dans `mods.pct_list_defender`. Le deplacement EN BLOC
        # d'avant les rangeait tous cote defenseur, ce qui coutait un `Round` de trop des que la
        # face attaquante etait elle aussi non neutre (mesure #462-r4a `--two-faces` : natif
        # 761/1141, deux chaines 762/1142).
        if def_mods.pct_list:
            mods.pct_list.extend(def_mods.pct_list)
            def_mods.pct_list = []
        if def_mods.pct_list_defender:
            mods.pct_list_defender.extend(def_mods.pct_list_defender)
            def_mods.pct_list_defender = []
        if def_mods.multiplicative != 1.0:
            mods.multiplicative *= def_mods.multiplicative
            def_mods.multiplicative = 1.0
        if def_mods.multiplicative_defender != 1.0:
            mods.multiplicative_defender *= def_mods.multiplicative_defender
            def_mods.multiplicative_defender = 1.0
        # #112 : axe PERCAGE porte par un effet de la CIBLE (`<Effect>.CreatePiercingBonusForAttack`
        # avec trigger `OwnerIsTarget`, ex. `IdunBattle.Entities.Effects.Loki.
        # Supercharge_ExtraPiercingEffect$$CreatePiercingBonusForAttack` = `ForPiercing(
        # DamageProfileIs(Plasma) & OwnerIsTarget, ConfigVar(0x3f=extraPierceRatio))`). Le natif SOMME
        # le champ Piercing@+0x20 de l'accumulateur ATTAQUANT ET de l'accumulateur DEFENSEUR avant
        # `GetBaseDamageWithFixedPiercedArmor` (`pierce_eff = clamp(pierce + extra, 0, 100)`) ; le port
        # ne passe que `mods` (attaquant) a `apply_pierce_and_modifiers` -> on FUSIONNE ici, au MEME
        # endroit que la reduction plate defenseur. Vide -> no-op strict (aucun effet PREEXISTANT
        # n'alimentait ce canal : `create_piercing_bonus_for_attack` par defaut = None).
        if def_mods.extra_pierce:
            mods.extra_pierce += def_mods.extra_pierce


class DamageHandler:
    """Visiteur des messages d'attaque (mirror du handler natif lançant AttackDamageOperation).

    `spread_pct` = `BattleConfiguration.Damage.DamageSpreadPercentage`, LU de la BC de cette
    bataille quand il vaut `None` (foyer `engine.services.damage_config.resolve_spread_pct`,
    #449-r2-r4). Le natif ne le connaît que par la configuration :
    `IdunBattle.Core.Services.DamageCalculations$$get_DamageSpreadPercentageFix64` lit
    `configuration+0x20`, où `configuration` est `BattleConfiguration.Damage` posé par
    `IdunBattle.Core.Services.DamageCalculations$$Init`."""
    __slots__ = ("state", "spread_pct", "last", "after_hit")

    def __init__(self, state: State, spread_pct: Optional[int] = None):
        self.state = state
        self.spread_pct = resolve_spread_pct(spread_pct, state)
        self.last: Optional[dict] = None       # résultat du dernier coup (diagnostic/test)
        self.after_hit: list = []              # extra-attaques after-hit (traits) du dernier coup

    def visit_AttackUnitMessage(self, msg) -> None:
        """#429-r1-r3-r1 -- LE GATE DE MESSAGE, POSE ICI AUSSI, ET POURQUOI.

        `AttackUnitMessage` N'EXISTE PAS EN NATIF -- mesure exhaustive sur `rnca9r7q6c` :
        `IdunBattle.Messages` publie 41 classes de message, `InputMessageProcessor` porte 37
        surcharges de `Visit`, et AUCUNE ne prend un `AttackUnitMessage`. L'attaque normale
        COMMANDEE est un `IdunBattle.Messages.ActiveAbilityMessage` dont l'`ActiveAbilityType` est
        le `NormalAttackType` PER-UNITE (#139) : elle traverse donc
        `IdunBattle.Messages.InputMessageProcessor$$Visit(ActiveAbilityMessage)` et SON gate.

        Le port a DEUX portes pour cet unique site natif (`AbilityHandler.visit_ActiveAbilityMessage`
        et celle-ci, cf. l'en-tete d'`abilities/handler.py` #120) ; seule la premiere portait le gate
        de message. C'est le meme FORK que #120, sur l'axe LIVENESS.

        PERIMETRE, mesure par les XREFS de `IdunBattle.Entities.UnitExtensions$$IsAliveAndNotFled` :
        **2 appels dans tout le binaire**, tous deux dans `Visit(ActiveAbilityMessage)` -- le CASTER
        puis la CIBLE. Aucune autre surcharge de `Visit` ne le teste : `Visit(MoveUnitMessage)`, lu
        au decompile, n'a AUCUN gate de liveness (il resout l'unite, construit la liste de tuiles et
        entre en `RunPhase(PhaseType.MoveUnit /*5*/)`). Le gate porte donc sur UN SEUL message, sur SES DEUX bouts.

        CE QUI SEPARE CE GATE DE CEUX D'EN DESSOUS : sur la MORT ils CONVERGENT (le gate #70
        refuse deja l'attaquant mort, `is_dead_unit_and_not_allowed_by_ability(None, ...)` deja tout
        cadavre). Sur `UnitFlag.Fled` (9) ils NE CONVERGENT PAS -- `IdunBattle.Entities.
        UnitExtensions$$IsDead` exclut EXPRESSEMENT ce flag (`!IsAlive && !HasFlag(9)`), donc une
        unite ENFUIE (hp > 0, retiree du plateau par `IdunBattle.Operations.FleeOperation$$Execute`,
        seul ecrivain du flag 9 dans le binaire) n'est morte pour AUCUN des deux gates du dessous :
        sans cette pose, le port frappait une unite que le natif refuse au rang du message.

        IMPORT PARESSEUX VOULU : la contre-epreuve des tests substitue le FOYER
        (`engine.runner.components.is_alive_and_not_fled`) -- un import de module resolu a chaque
        appel est ce qui fait MORDRE la mutation.

        CONVENTION PERMISSIVE, identique a `visit_ActiveAbilityMessage` : entite non resolue (id
        `None`, ou absente de l'etat) -> aucun refus."""
        for eid in (msg.attacker_id, msg.target_id):
            if eid is None:
                continue
            ent = self.state.get_entity(int(eid))
            if ent is None or is_alive_and_not_fled(ent):
                continue
            self.last = None
            self.after_hit = []
            return
        # --- #70 GATE ACTEUR-MORT (mirror `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` :
        # `if (EntityExtensions.IsUnit(caster) && UnitExtensions.IsDead(caster)) return 0;`). L'attaque
        # normale native EST une ActiveAbility per-unite (#139) -> passe par le MEME gate. Un attaquant MORT
        # (hp<1, non-Fled ; `IdunBattle.Entities.UnitExtensions$$IsDead`) => NO-OP complet (0 tirage RNG, 0 degat,
        # aucun after-hit, aucun flag), AVANT toute selection d'arme / boucle de coups. Le port `execute`
        # mirror `IdunBattle.Operations.AttackDamageOperation$$Execute` qui n'a AUCUN gate liveness natif -> le gate vit
        # au niveau OPERATION ici (upstream de la boucle RNG). Inerte pour tout attaquant vivant (replay/AI :
        # les tours sont pris sur des unites vivantes) -> zero regression. Repro : seed 123, u95 (mort en
        # attaquant u79) -> u81/u83 : live 0 tirage/0 degat, offline sur-executait 2924. cf. case-70.
        _att = self.state.get_entity(msg.attacker_id)
        if unit_is_dead(_att):
            self.last = None
            self.after_hit = []
            return
        # --- #429-r1-r1 GATE CIBLE-MORTE, le gate qui SUIT immediatement le gate acteur-mort dans
        # `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` (et qui PRECEDE
        # `IsInvalidTarget`). Le foyer commun est en tete d'`AttackDamageOperation.execute` (il couvre
        # les ~11 portes DECLENCHEES, qui n'empruntent pas ce visiteur) ; il est RE-pose ici parce que
        # le dispatch `NormalAttackType` CONCRET qui suit (MV71SniperDroneSquad) n'est PAS une simple
        # attaque : il SPAWNE un drone avant d'attaquer. Cote natif ce dispatch est le corps de
        # l'ability 1076, donc EN AVAL du gate d'`ExecuteInternal` -- sans cette pose, un cast sur un
        # cadavre spawnerait le drone puis n'attaquerait pas, alors que le natif ne fait RIEN.
        # Meme dedoublement, et pour la meme raison, que le gate acteur-mort (#70 au rang du message,
        # #133 au rang de l'operation).
        if _active_ability.is_dead_unit_and_not_allowed_by_ability(
                self.state, None, msg.target_id):
            self.last = None
            self.after_hit = []
            return
        # --- #61bis tranche 3 : dispatch NormalAttackType CONCRET. L'attaque normale native est une
        # ActiveAbility PER-UNIT (`ActiveAbilityComponent.NormalAttackType@0x28`) ; pour un porteur du
        # passif MV71SniperDroneSquad (Sho'syl/tauMarksman), c'est `MV71SniperDroneSquadAttackAbility`
        # (1076) : à DISTANCE elle invoque un DRONE (spawn + attaque commandée + Markerlight), en MÊLÉE
        # elle délègue au pipeline normal. Les tours simulés (AttackUnitMessage) routent donc comme le
        # cast live 1076. `self.last` = l'attaque du VECTEUR (mêlée : celle du caster ; distance :
        # l'attaque commandée du drone) — même shape que le chemin générique.
        _ae = self.state.get_entity(msg.attacker_id)
        _uc = _ae.get_component(UnitComponent) if _ae is not None else None
        if _uc is not None:
            # forme MODULE : is_mv71_normal_attacker est SUBSTITUE (probe_419r1tr14r5) --
            # lie au chargement, le stub cesserait de mordre en silence (#485-r1-r1).
            from ..abilities.loki import mv71 as _mv71
            # #419-r1-tr14-r5 : la cle de dispatch est `UnitConfiguration.PassiveAbilities` (fait
            # d'ENTITE, mesure `UnitContext.passive_abilities` par `snapshot._load_passive_
            # abilities`), pas le KIT — MEME predicat et MEME source que la face DECISION, sans quoi
            # « ce que la prediction annonce » et « ce que le moteur fait » divergeraient.
            # #419-r1-tr14-r5-r2 : la SECONDE voie de la cascade, threadee ici aussi -- les deux
            # faces doivent decider de la MEME cascade, pas chacune d'une moitie.
            # #419-r1-tr14-r5-r2-r1 : la TROISIEME branche de la meme cascade
            # (`Traits.Contains(0x7e7 Boss)`), threadee ici aussi -- une face qui ne connaitrait
            # qu'une PARTIE de la cascade est exactement ce que les deux tranches precedentes ont
            # ferme. Substrat d'ENTITE : `entity_trait_names` sur le `UnitContext`.
            _asc = _ae.get_component(StatsComponent)
            _actx = getattr(_asc, "ctx", None)
            _apas = getattr(_actx, "passive_abilities", None)
            _aact = getattr(_actx, "active_abilities", None)
            # #419-r1-tr14-r5-r2-r2-r1 : la QUATRIEME (la garde du repli generique) lit
            # `UnitConfiguration.ActiveAbilities`, l'etat AVANT la fabrique -- pas `_aact`, qui est
            # l'etat APRES. Meme motif que ci-dessus : les deux faces decident de la MEME cascade.
            _acfg = getattr(_actx, "config_active_abilities", None)
            _atra = entity_trait_names(_actx, _uc.visual_id)
            if _mv71.is_mv71_normal_attacker(_uc.visual_id, passive_abilities=_apas,
                                       active_abilities=_aact, traits=_atra,
                                       config_active_abilities=_acfg):
                res = _mv71.MV71SniperDroneSquadAttackAbility().execute_behaviour(
                    self.state, msg.attacker_id, msg.target_id) or {}
                self.last = res.get("attack")
                self.after_hit = res.get("after_hit") or []
                # flags du CASTER (#139) — même queue que le chemin générique ci-dessous (les flags
                # du DRONE sont posés par execute_behaviour lui-même).
                from .turnflow import add_flags_after_ability_execution
                _fl = add_flags_after_ability_execution(
                    self.state, int(msg.attacker_id), skip_ability_used=False, skip_end_turn=False)
                if isinstance(self.last, dict):
                    self.last["flags"] = _fl
                return
        self.last = AttackDamageOperation.execute(
            self.state, msg.attacker_id, msg.target_id, self.spread_pct)
        # --- #521-r7 `EvaluateAbilities(0x4a = AttackInAtomicGroup, immediately: true)` -----------
        # C'est le vecteur qui MANQUAIT au port, et son emetteur n'est pas celui qu'on croyait.
        # `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$
        # ExecuteNormalAttack` -- la passe PRIMAIRE de TOUTE attaque normale, base commune de toutes
        # les `<X>_NormalAttackAbility` (la generique `Loki_NormalAttackAbility` comprise) -- fait :
        #     b = GetAttackDamageBehaviour(this, abilityState, entities, attackWeapon,
        #                                  <vslot 0x4a8 GetTarget>)   # #1050-r1 : le SELECTEUR
        #     b = b op_BitwiseAnd DSLBehaviors$$EvaluateAbilities(dsl, 0x4a, null, null, null,
        #                                                         immediately: true)
        #     return AActiveAbility$$ExecuteAtomic(this, b, entities, 0x3d)
        # -> l'emission est INCONDITIONNELLE, et c'est ce qui donne son nom a l'evenement (l'attaque
        # a eu lieu DANS un groupe atomique). #521-r4 avait conclu « aucun emetteur sur la voie
        # normale » en lisant le SIBLING `...$$ExecuteTriggerAbilities`, qui emet `0x26`.
        # Contraste LU : `IdunBattleLogic.Entities.Abilities.Active.NormalAttackAbility$$
        # CreateBehaviour` (l'AUTRE classe d'attaque normale, hors namespace `Loki`) emet
        # `EvaluateAbilities(0x26, immediately: false)`.
        # RANG : apres les coups d'ARME et le FOLD primaire (tous deux dans `GetAttackDamage
        # Behaviour`), AVANT le CLEAVE (`ExecuteAtomic(0x2a)` de `Execute<X>`) et avant
        # `ExecuteTriggerAbilities` (`On(0x26)`) -- d'ou le `after_primary` passe au volet #478 et
        # l'appel (IDEMPOTENT) juste apres, qui couvre le cas SANS cleave.
        # ⚠ Ce site est le JUMEAU de ceux de MV71 / du cleave / de HeavyBoltPistol : comme eux il ne
        # couvre que la voie MESSAGE, pas les portes qui appellent `AttackDamageOperation.execute`
        # directement (overwatch, `UseActiveAbility`, summon AI) -- meme residu `#478-r3`.
        # ⚠ #521-r8 -- CE SITE PORTE DESORMAIS `FireOfAbsolution`, ET SA COUVERTURE EST LE PRIX
        # ASSUME DE LA MIGRATION. Le passif etait joue IMPERATIVEMENT par `after_hit_normal_attack`,
        # donc depuis les CINQ portes qui appellent ce vecteur (voie MESSAGE, feuille DSL
        # `UseActiveAbility`/`UseNormalAttack`, MV71, summon, summon AI) et APRES toute la cloture.
        # Il est desormais sur son vecteur natif `On(0x4a)`, a son rang natif -- mais ce vecteur-ci
        # ne couvre que la voie MESSAGE (residu `#478-r3`, partage avec MV71 / le cleave /
        # HeavyBoltPistol). Sur le SEUL porteur (`adeptRetributor`), les quatre portes perdues sont :
        # MV71 / summon / summon AI (structurellement inatteignables pour lui) et la feuille DSL
        # `UseNormalAttack` (free-attack accordee -- ETROITE, et c'est la seule perte reelle).
        _atomic_group_done = []

        def _evaluate_attack_in_atomic_group():
            if _atomic_group_done or self.last is None:
                return
            _atomic_group_done.append(True)
            from .triggers.dispatch import ability as _atomic_dispatch   # lazy : cycle damage<->triggers
            from ..abilities.attack_type import NORMAL_ATTACK_KIND       # lazy : meme cycle
            _r = _atomic_dispatch.evaluate_abilities_for_event(
                self.state, msg.attacker_id, self.last.get("target", msg.target_id),
                int(EventTriggerType.AttackInAtomicGroup), bool(self.last.get("ranged")),
                profile=self.last.get("profile"),
                # `CurrentAbility` = le marqueur de kind attaque-normale, comme partout ailleurs sur
                # cette voie (`pre_unit_ability_triggers(ability_type=1013)`) : c'est LUI qui
                # satisfait le gate `IsNormalAttack` de `1316`.
                # #521-r8 : plus d'`fire_of_absolution=False`. L'anti-double-fire n'a plus lieu
                # d'etre, l'appel imperatif d'`after_hit_normal_attack` ayant ete retire dans le
                # MEME commit -- les deux vont toujours par paire, sous peine de double splash
                # (ou de zero splash).
                ability_type=NORMAL_ATTACK_KIND)
            if _r:
                self.last["attack_in_atomic_group"] = _r
        # --- #478 les DEUX volets de `<X>_NormalAttackAbility$$GetAdditionalDamageBehaviour`. Les
        # quatre attaques normales CONCRETES `Boltstorm`/`RighteousRepugnance`/`Fealty`/
        # `TalonOfHorus` frappent des cibles ADDITIONNELLES (le CLEAVE) ; les DEUX PREMIERES
        # ajoutent en plus un paquet sur la cible PRIMAIRE (`$$GetCustomNormalAttackBehaviour`,
        # vslot 0x4e8 lu par `GetAttackDamageBehaviour` -- #1050-r1 : ce n'est PAS `0x4a8`, qui est
        # `$$GetTarget`, le SELECTEUR de cibles) :
        #     Execute<X> = InformWeapon
        #                + ExecuteNormalAttack        -> coups d'ARME + le FOLD primaire, meme 0x3d
        #                + ExecuteAtomic(Foreach(GetAdditionalTargets, Attack), 0x2a)   -> le CLEAVE
        #                + ExecuteTriggerAbilities
        # Le rang est celui du natif -- APRES l'attaque primaire (donc apres son `FinishAttack`/
        # `On(9)`, emis dans l'operation) et AVANT `ExecuteTriggerAbilities` (`On(0x26)`), que le
        # port joue juste en dessous via `after_hit_normal_attack`. Detail des deux gates (l'ARME
        # pour le cleave, la POSITION pour le fold) : `abilities/loki/additional_targets.py`.
        # `self.last is None` couvre le `weapon == null` natif (`Execute<X>` n'est pas atteint) ET
        # les gates amont ; `ranged` est la nature de l'arme REELLEMENT choisie par
        # `ALoki_NormalAttackAbility$$FindAttackWeapon`, c'est-a-dire l'entree exacte de la gate
        # `IsMelee` -- on ne la re-derive pas d'une adjacence.
        # ⚠ Ce site est le JUMEAU de celui de MV71 ci-dessus : comme lui, il ne couvre que la voie
        # MESSAGE, pas les ~11 portes qui appellent `AttackDamageOperation.execute` directement
        # (overwatch, `UseActiveAbility`, summon AI...). Residu `#478-r3`, jumeau non nomme de celui
        # de MV71 : le natif n'a qu'un site parce que l'ability EST le corps de l'attaque normale.
        if self.last is not None and _uc is not None:
            from ..abilities.loki.additional_targets import (cleave_for, selected_weapon_range,
                                                             execute_additional_targets_attacks,
                                                             fold_inherits_attack_state)
            _cl = cleave_for(_apas, active_abilities=_aact, visual_id=_uc.visual_id,
                             traits=_atra, config_active_abilities=_acfg)
            if _cl is not None:
                _wr = None
                if _cl.needs_weapon_range:
                    # `Direct(attackWeapon.Range.Value)` : la portee de l'ARME CHOISIE par
                    # `ALoki_NormalAttackAbility$$FindAttackWeapon`. On la relit par le MEME service
                    # et avec le MEME argument `dist` que la selection d'arme de l'attaque primaire
                    # (`damage_ops/normal.py` : `are_tiles_adjacent -> 1 sinon 2`), pour qu'il n'y
                    # ait qu'UNE selection d'arme par cast, comme au natif.
                    _wr = selected_weapon_range(self.state, msg.attacker_id,
                                                self.last.get("target", msg.target_id), _actx)
                _adds = execute_additional_targets_attacks(
                    self.state, msg.attacker_id, self.last.get("target", msg.target_id),
                    _cl, is_melee=not bool(self.last.get("ranged")), weapon_range=_wr,
                    # #419-r3 : le FOLD est un `DSLBehaviors$$AttackDamage` NU compose DANS le
                    # `Attack(...)` de l'attaque primaire (`ALoki_NormalAttackAbility$$
                    # GetAttackDamageBehaviour`), et son call-site pose `isOutsideAttack = false`.
                    # Il lit donc l'`OngoingAttack` que les coups d'arme viennent de muter, pas une
                    # neuve. `fold_inherits_attack_state()` est le point de MUTATION de la
                    # contre-epreuve : `probe_419r3_fold_attack_state.py` SUBSTITUE cet attribut
                    # de module et joue les deux regimes en une passe (aucun drapeau a passer).
                    attack_state0=(self.last.get("attack_state")
                                   if fold_inherits_attack_state() else None),
                    # #521-r7 : `EvaluateAbilities(0x4a)` s'intercale ENTRE le fold et le cleave
                    # (cf. le bloc ci-dessus). L'appel est idempotent.
                    after_primary=_evaluate_attack_in_atomic_group)
                if _adds.get("primary_fold"):
                    self.last["primary_fold"] = _adds["primary_fold"]
                if _adds.get("additional_targets"):
                    self.last["additional_targets"] = _adds["additional_targets"]
        # --- #1050-r1 l'ELARGISSEMENT MULTI-CIBLE de `AncientFury_NormalAttack`. AUTRE famille que
        # le cleave ci-dessus, et le discriminant est le SLOT SURCHARGE :
        #   * #478 surcharge `$$GetCustomNormalAttackBehaviour` (vslot 0x4e8) et/ou pose un
        #     `Execute<X>` qui ajoute un SECOND `Attack(...)` aux BORNES DE CONFIG du passif ;
        #   * ICI c'est `$$GetTarget` (vslot 0x4a8) qui est surcharge -- le `Attack(caster, <sel>,
        #     ...)` reste UNIQUE, et `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`
        #     boucle sur les N cibles TRIEES en donnant a CHACUNE l'attaque d'ARME COMPLETE
        #     (`StartAttack` / `AttackDamage(Caster@0x48, Target@0x60, ...)` / `FinishAttack`).
        # Les deux familles sont MUTUELLEMENT EXCLUSIVES : la cascade
        # `UnitFactory$$AddNormalAttackAbility` ne monte qu'UN passif substituant par unite, et le
        # cran `test_1050_optimized_gait_offline.py` etage 4 interdit d'inscrire `AncientFury` dans
        # `NORMAL_ATTACK_CLEAVES`, ou il recevrait les bornes de config au lieu des coups d'arme.
        # RANG : la boucle native vit DANS `ExecuteNormalAttack`, donc APRES la primaire et AVANT le
        # `EvaluateAbilities(0x4a)` que `ExecuteNormalAttack` compose ensuite -- d'ou cette place,
        # juste au-dessus de l'appel idempotent ci-dessous.
        # ⚠ MEME JUMELAGE que MV71 / le cleave / HeavyBoltPistol : voie MESSAGE seulement, pas les
        # portes qui appellent `AttackDamageOperation.execute` directement (residu `#478-r3`).
        # ⚠ RESIDU `#1076` : le natif trie la cible PRIMAIRE **avec** les additionnelles ; le port la
        # frappe toujours en tete (le preambule d'`ActiveAbilityOperation$$ExecuteInternal` n'est pas
        # separable du premier coup). Detail : `abilities/loki/ancient_fury.py`.
        if self.last is not None and _uc is not None:
            from ..abilities.loki import ancient_fury as _af
            _wd = _af.widened_for(_apas, active_abilities=_aact, visual_id=_uc.visual_id,
                                  traits=_atra, config_active_abilities=_acfg)
            if _wd is not None:
                _wt = _af.execute_widened_normal_attack(
                    self.state, msg.attacker_id, self.last.get("target", msg.target_id), _wd,
                    # `is_melee` = la nature de l'ARME REELLEMENT choisie par `FindAttackWeapon`,
                    # l'entree exacte de `IsMeleeAttack` du `ConditionalSelector` -- on ne la
                    # re-derive pas d'une adjacence (meme regle que la gate du cleave).
                    is_melee=not bool(self.last.get("ranged")), spread_pct=self.spread_pct)
                if _wt:
                    self.last["widened_targets"] = _wt
        # #521-r7 : le cas SANS cleave (l'immense majorite -- la cascade `AddNormalAttackAbility`
        # rend un passif substituant pour 4 abilities seulement). Idempotent avec le `after_primary`
        # ci-dessus.
        _evaluate_attack_in_atomic_group()
        # --- #419-r1-tr14-r4 le SECOND VOLET de `TemplarInitiateNormalAttackAbility` : le COUP DE
        # PISTOLET de `HeavyBoltPistol` (1083). Ce n'est PAS un trigger d'evenement -- l'ability n'a
        # AUCUN `$$CreateTrigger` (verifie dans les DEUX tables de symboles) : elle est appelee en
        # dur par l'attaque normale qu'elle substitue.
        #     ExecuteBehaviour = ExecuteAtomic( Group(<ExecuteNormalAttack>, 0x20)      -> coups d'ARME
        #                                     & Group(<ExecuteBonusAttack>,  0x20),     -> TriggerAbility(1083)
        #                                       GroupType.TemplarInitiateNormalAttack_AtomicGroup = 0x52 )
        # Le rang est donc celui du natif : APRES les coups d'arme (et apres le cleave #478, dont le
        # dispatch est EXCLUSIF de celui-ci -- la cascade `UnitFactory$$AddNormalAttackAbility` rend
        # UN seul passif substituant) et AVANT `ExecuteTriggerAbilities` (`On(0x26)`), joue juste en
        # dessous par `after_hit_normal_attack`. La gate `IsMeleeAttack` et l'arbre :
        # `abilities/loki/heavy_bolt_pistol.py`.
        # ⚠ Ce site est le JUMEAU de ceux de MV71 et du cleave : comme eux il ne couvre que la voie
        # MESSAGE, pas les portes qui appellent `AttackDamageOperation.execute` directement
        # (overwatch, `UseActiveAbility`, summon AI) -- meme residu `#478-r3`, meme cause (le natif
        # n'a qu'un site parce que l'ability EST le corps de l'attaque normale).
        if self.last is not None and _uc is not None:
            from ..abilities.loki.heavy_bolt_pistol import (has_bonus_attack,
                                                            execute_bonus_attack)
            if has_bonus_attack(_apas, active_abilities=_aact, visual_id=_uc.visual_id,
                                traits=_atra, config_active_abilities=_acfg):
                _bonus = execute_bonus_attack(self.state, msg.attacker_id,
                                              self.last.get("target", msg.target_id))
                if _bonus is not None:
                    self.last["bonus_attack"] = _bonus
        # VECTEUR AFTER-HIT : dispatcher GÉNÉRIQUE de triggers (mirror `EvaluateAfterHitTriggers` →
        # `EvaluateTriggerOperation`). Itère le registre des triggers (traits/effets) ; chaque entrée
        # scope elle-même via sa condition (ex. Psyker OwnerIsActor). No-op si aucun trigger ne matche.
        if self.last is not None:
            from .triggers.dispatch.attack import after_hit_normal_attack
            # #437 : `profiles` / `health_damage` NE sont plus threades ici -- ils appartenaient au
            # seul `On(9)`, desormais emis a la SORTIE de `AttackDamageOperation.execute`
            # (`finish_attack_triggers`), le foyer natif (`AttackBehaviour$$Execute` -> FinishAttack).
            # #120bis : la cible du vecteur after-hit = celle que l'attaque a REELLEMENT frappee
            # (`last["target"]`), pas celle du message — la re-resolution d'`ActiveAbilityOperation$$
            # ExecuteInternal` peut avoir bascule l'attaque sur une remplacante (SwornProtector/Kell).
            # Le natif emet ces vecteurs depuis `AttackDamageOperation$$ExecuteHit`, donc avec
            # l'AttackData de l'attaque re-entrante. Defaut = la cible du message (retro-compat).
            # `finish_attack` (#437) = les resultats du vecteur `On(9)`, desormais emis DANS
            # l'operation. On les remet EN TETE d'`after_hit` : c'est l'ORDRE NATIF (`FinishAttack`
            # precede `ALoki_NormalAttackAbility$$ExecuteTriggerAbilities`, qui porte `On(0x26)`) et
            # ca preserve l'observabilite du canal pour les tests/probes qui lisent `after_hit`.
            # #139 : l'attaque normale native EST une ActiveAbility (NormalAttack per-unite ;
            # AttackUnitMessage n'existe pas en natif — c'est la simplification port de
            # l'ActiveAbilityMessage) et traverse la MEME queue
            # `IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution` — base
            # `SetsEndTurnFlags`/`SetsActiveAbilityUsedFlag` = `_dsl.True`
            # `IdunBattle.Entities.Abilities.AActiveAbility$$SetsEndTurnFlags` (aucune classe
            # NormalAttack dans la famille d'overrides) -> flag ActiveAbilityUsed(2) +
            # FinishUnitTurn (flags 1+3).
            # ⚠ #1020-r5 : la pose se fait DANS `after_hit_normal_attack`, a son rang natif (entre
            # `On(0xc)` et `On(0xe)`), et non plus APRES son retour. L'inversion rendait INERTE tout
            # consommateur de `On(0xe)` qui RETIRE un drapeau de tour (`ResetTurn` de `RapidFire`,
            # `ResetMovement` de `Maugetar`) : la pose qui suivait les remettait aussitot. Mesure et
            # citation du decompile dans la docstring d'`after_hit_normal_attack`. Ce n'est donc PAS
            # qu'un bookkeeping observable : deux consommateurs portes en dependent.
            from .turnflow import add_flags_after_ability_execution
            _drapeaux: dict = {}

            def _poser_les_drapeaux():
                _drapeaux["flags"] = add_flags_after_ability_execution(
                    self.state, int(msg.attacker_id),
                    skip_ability_used=False, skip_end_turn=False)

            self.after_hit = (self.last.get("finish_attack") or []) + after_hit_normal_attack(
                self.state, msg.attacker_id, self.last.get("target", msg.target_id),
                bool(self.last.get("ranged")), self.last.get("profile"),
                is_crit=bool(self.last.get("did_crit")),
                did_block=bool(self.last.get("did_block")),
                avant_post_ability=_poser_les_drapeaux)
            self.last["flags"] = _drapeaux.get("flags")
