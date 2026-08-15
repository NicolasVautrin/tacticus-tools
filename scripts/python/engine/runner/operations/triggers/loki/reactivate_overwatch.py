"""`IdunBattle.Entities.Effects.AReactivateOverwatchEffect` -- la RE-ENTREE EN OVERWATCH apres un kill,
avec sa reduction de coups. Porte ici pour `EarlyWarningOverride_ReactivateOverwatch` (0x479 = 1145),
le 3e des quatre effets poses par l'active 1077 de `tauCrisis` (Re'vas) -- residu #114 §5.3.

i2 (1077) : « If she kills a unit with her Overwatch attack, she remains in Overwatch, retaining 1
fewer hits ».

## Hierarchie native (table de symboles FRIDA -- Ghidra MISLABELLE ce voisinage, cf. §Pieges)

    IdunBattle.Entities.Effects.DamageModifierAbilityEffect
      +- IdunBattle.Entities.Effects.AReactivateOverwatchEffect            (toute la logique)
           +- Loki.EarlyWarningOverride_ReactivateOverwatchEffect  (1145)  <- PORTE ICI
           +- Loki.FiringPosition_ReactivateOverwatchEffect        (1150)  <- PORTE ICI (#1077)
           +- Loki.CalibaniteGreatsword_StrikeOverwatchingEffect
           +- Loki.InescapableDeathEffect

`EarlyWarningOverride_ReactivateOverwatchEffect$$.ctor` = `AReactivateOverwatchEffect..ctor(this,
0x435 = 1077 EarlyWarningOverride)` -> l'effet resout ses `ConfigVar` contre la config de 1077.

## `AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal` (MIRROR 1:1 du decompile)

    # --- Triggered #1 : la RE-ENTREE ------------------------------------------------------------
    Triggered(
        On(1 = PreUnitDeath) & get_OwnerIsActor
          & NOT df@0xa0                                              # `IsTurnOf(owner@0x148)`
          & AmountIsGreater( Max( RangedAttackHits(Owner@0x148),
                                  MeleeAttackHits(Owner@0x148) ),
                             HitReductionValue() )                   # vtable +0x748
          & LegitDeathReasons(),                                     # vtable +0x738
        # == GetReactivateOverwatchBehaviour() & GetAddHitReductionBehaviour()
        ActivateEffect(Owner@0x148, 0x3f1 = 1009 Overwatch_AutoAttack)
        & AddStaticStatModifierEffect( Owner@0x148,
                                       GetHitReductionEffectType(),  # vtable +0x758
                                       0x11 = EXTRA_HITS,
                                       Negative(HitReductionValue()),
                                       TurnsUntilUnitOwnerTurn(Owner@0x148), isHidden=0 ) )

    # --- Triggered #2 : la PURGE de la reduction -------------------------------------------------
    Triggered(
        ( On(0 = UnitDeath) | On(0x11 = PostDamageTaken) )
          & NOT HasEffect(Owner@0x148, 0x3f1, onlyActive=1, targetType=6=Both),
        RemoveEffect(Owner@0x148, Nullable(GetHitReductionEffectType())) )

Les sous-fonctions NOMMEES `GetReactivateOverwatchCondition` / `GetReactivateOverwatchBehaviour` /
`GetAddHitReductionBehaviour` / `GetDeactivateHitsReductionCondition` /
`GetDeactivateHitsReductionBehaviour` ont EXACTEMENT ces corps : `CreateHandleTriggerAbilitiesInternal`
les reprend INLINE (meme patron que `FightingRetreatAbility$$GetAttackTargets`).

Overrides de la sous-classe 1145 :

  * `EarlyWarningOverride_ReactivateOverwatchEffect$$GetHitReductionEffectType` = `return 0x47a`
    = **1146 `EarlyWarningOverride_HitReduction`** (corps = `mov eax,0x47a ; ret`, lu en OCTETS : la
    fonction est trop petite pour que Ghidra la reconnaisse -- son RVA vient de la table FRIDA).
  * `EarlyWarningOverride_ReactivateOverwatchEffect$$LegitDeathReasons` (override) =
        `HasDeathReason(query@0x178, DamageReason.Ability = 0, AbilityOrEffect(0x3f1 = 1009))`
        `| HasDeathReason(query@0x178, DamageReason.Ability = 0, AbilityOrEffect(0x47c = 1148))`
    la base ne garde que la 1re branche. **1148 = `CyclicIonBlaster_AdditionalHits`** = l'effet du
    passif de Re'vas (triggered 1133) qui ajoute 3 coups Particle : un kill porte par CES coups-la
    compte AUSSI. C'est le point que « toute mort re-arme » aurait rate.

`AReactivateOverwatchEffect$$HitReductionValue` = `Direct(GetNumberConstant(config@0x60, 0x2c))` =
la constante `hitsReduction` de l'ability source (=1 pour 1077).

## Le canal DEATH-REASON (ce qui manquait au port)

`HasDeathReason(selector, deathReason, abilityOrEffect)` -> `HasDeathReasonTrigger$$ShouldTrigger` :
resout le SELECTEUR, prend le `UnitComponent` de chaque unite selectionnee, lit son
`Nullable<DamageSource>` @`+0x108` et delegue a `$$IsMatchingDeathReason` :

    if (!src.HasValue) return false
    if (src.DamageReason != this.deathReason) return false
    if (!this.abilityOrEffect.HasValue) return true            # pas de filtre d'ability
    return src.AbilityOrEffect.HasValue && src.AbilityOrEffect == this.abilityOrEffect

Le champ est ecrit par `KillUnitOperation$$RecordDeathReason(killer, killed, killedUnitComponent,
deathReason)`, appelee par `KillUnitOperation$$Execute` **AVANT** l'emission de `On(PreUnitDeath=1)`
(ordre lu au decompile). Son `AbilityOrEffect` vient de la `DamageSource` construite PAR COUP par
`AttackDamageOperation$$ExecuteHit` / `AbilityDamageOperation$$ExecuteHit` via

    idun...StaticBattleRules$$GetDamageSourceAbility(currentAbility, triggeringAbility) =
        IsRegularAttack(currentAbility) && triggeringAbility.HasValue ? triggeringAbility
                                                                     : currentAbility

=> pour un tir d'OVERWATCH (`Overwatch_AutoAttackEffect$$GetAttackBehaviour` =
`UseActiveAbility(NormalAttack)`, donc `currentAbility` = une attaque REGULIERE, declenchee par
l'effet 1009) la source enregistree est **l'effet declencheur 1009**, pas l'attaque normale. C'est
exactement ce que `LegitDeathReasons` teste. Cf. `runner/operations/damage.py`
(`_damage_source_ability` + `_record_death_reason`).

## Ce que le port MODELISE et ce qu'il ne modelise pas

* `ActivateEffect(Owner, 1009)` = `GetReactivateOverwatchBehaviour`. C'est le CONTREPOIDS EXACT du 3e
  `Triggered()` de `RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal`
  (`On(AttackDamageAttack=10) & OwnerIsActor -> DeactivateEffect` = « un seul tir par activation »,
  porte par #127 avec le flag `BaseEffect.active` = `EffectComponent.IsActive @+0x5c`) : le tir
  d'overwatch CONSOMME l'instance 1009, ce behaviour-ci la RE-ARME quand le tir a tue. La feuille
  `ActivateEffect` pose desormais ce flag (elle ne faisait que materialiser la presence avant #127).
  GROUND TRUTH LIVE (test de garde) : apres le kill en overwatch, 1009 est TOUJOURS present dans
  `decisionView` (donc `IsActive != 0`) -- « she remains in Overwatch ».
* la REDUCTION DE COUPS, elle, est PLEINEMENT observable : l'effet 1146 apparait sur le porteur avec
  un stat-mod `EXTRA_HITS = -hitsReduction` que `attack_hits_with_modifiers` consomme -> le tir
  d'overwatch SUIVANT a un coup de moins.
* `On(PostDamageTaken = 0x11)` (2e disjonct du Triggered #2) : le port n'a PAS de vecteur pour cet
  evenement (site d'emission natif non localise -- ni `ApplyDamageOperation$$Execute`, qui n'emet que
  0x3a/0xf/0x10, ni `KillUnitOperation$$Execute`). La classe l'ECOUTE (`event_ids`) pour rester
  fidele ; elle ne fire aujourd'hui que sur `On(UnitDeath = 0)`. Aucun port speculatif du vecteur.

## Pieges de RE traverses (a ne pas re-payer)

* ⚠ **CE POINT PORTAIT UNE CONCLUSION FAUSSE, ET ELLE A SURVECU A SA PROPRE CORRECTION.** Il disait :
  << la table FRIDA dit que ce corps est `InescapableDeathEffect.GetOverwatchExtraDamage`, donc
  **1145 n'override PAS `GetOverwatchExtraDamage`** >>. `inescapable_death.py` §5 annonce depuis #924
  avoir corrige cette phrase << dans le meme commit >> -- elle etait pourtant restee ici, mot pour
  mot. Re-mesuree et REFUTEE le 2026-08-15 (#924-r1) sur `t6dpr4k06g` : le bloc `methodPointers` de
  `EarlyWarningOverride_ReactivateOverwatchEffect` porte QUATRE entrees, et la troisieme EST ce
  corps partage. **1145 l'override.**
  Ce que le point voulait dire, et qui reste VRAI : la table FRIDA est indexee par ADRESSE et l'ICF
  fusionne les corps identiques, donc un seul PROPRIETAIRE y est nomme -- Ghidra n'invente rien, il
  herite de cette table. Ce qu'on n'a PAS le droit d'en conclure, c'est l'absence d'override : il
  faut compter les slots du bloc `methodPointers`, ou `class_get_methods` (voie METADATA, qui voit
  aussi les corps triviaux dedupliques -- cf. `LifewardsBondEffect`, #963-r3, ou le bloc a DEUX
  entrees et la metadata TROIS virtuels declares).
  Consequence : la face DEGAT de 1145 est **VIVANTE et NON PORTEE** -> residu **#924-r1**, dont la
  prochaine tranche a desormais son montage ECRIT (ci-dessous) et son RE complet.
* **MONTAGE de 1145, MESURE et IMMEDIAT** (la fiche #924-r1 l'annoncait << DISTINCT >>, ce qui a fait
  croire a un cout) : `tauCrisis` porte `EarlyWarningOverride` en **`kind: active`** (id 1077,
  `abilityStates` = `[{id: 1077, kind: active, level: 50, multiplier: 180}]`) et il est **AU POOL** --
  ni injection catalogue, ni greffe. Le cast fait tout :
  `...Active.Loki.EarlyWarningOverrideAbility$$ExecuteBehaviour` pose QUATRE effets sur
  `Owner@<DSLSelectors+0x30>` -- le CASTER lui-meme -- tous en `TurnsFromRounds(1)` :
  `0x3f1 = 1009 Overwatch_AutoAttack`, `0x478 = 1144 SuppressCloseCombatWeakness`,
  `0x479 = **1145**`, `0x47d = 1149 EarlyWarningOverride_Visual` ; puis `Spawn(GetStringConstant(0),
  First(CanAddUnit(AdjacentTiles(Owner)), GetNumberConstant(0x10)), WithStatsFromConfig(...))`.
  Autrement dit : `tauCrisis` caste 1077, entre en overwatch AVEC 1145 actif, et son tir d'overwatch
  passe par le canal `AReactivateOverwatchEffect$$CreateDamageModifier`. C'est le SECOND porteur que
  #924-r2 demande pour localiser sa magnitude.
* ⚠ **NE PAS RECOPIER LE 3e CONJOINT D'`InescapableDeath`** : les deux soeurs sont des MIROIRS
  CROISES (comptage des slots, #924-r1). `InescapableDeathEffect` override
  `GetAdditionalExtraDamageTrigger` (= `IsOverwatchAttack()`) et PAS `LegitDeathReasons` ; 1145
  override `LegitDeathReasons` et PAS `GetAdditionalExtraDamageTrigger`. Le `<vtable +0x768>` de
  1145 est donc celui de la BASE.
* Les ctors gshared (`IsUnitWIthIdTrigger`, `ModuloAbilityTrigger`) sont mislabeles : c'est la
  STRUCTURE des arguments qui identifie `RangedAttackHits` / `MeleeAttackHits` (meme classe, flag
  ranged 1/0) et `TurnsUntilUnitOwnerTurn`.
* Qualification d'enum : `1145` est AUSSI `ActiveAbilityType.SporeMineLauncher` (deja portee,
  tyranids.py) et `1148` AUSSI `ActiveAbilityType.DaemonicOrdnance`. Le contexte ici est
  `EffectType` des DEUX cotes.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent, StatsComponent, unit_state_for_effects
from ....abilities.base import turns_until_unit_owner_turn
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import (
    ActivateEffect, AddStaticStatModifierEffect, RemoveEffect
)
from .....entities.behaviours import op_and
from .....entities.damage_reason import DamageReason
from .....entities.effect_type import EffectType
from .....entities.selectors.tiles import Caster
from .....entities.stats import StatType
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import EffectTrigger, TriggerEvent
from ....components import UnitComponent
from ....damage_model import select_weapon, select_weapon_pierce

EWO_REACTIVATE_OVERWATCH = int(EffectType.EarlyWarningOverride_ReactivateOverwatch)   # 0x479 = 1145
EWO_HIT_REDUCTION = int(EffectType.EarlyWarningOverride_HitReduction)                 # 0x47a = 1146
OVERWATCH_AUTO_ATTACK = int(EffectType.Overwatch_AutoAttack)                          # 0x3f1 = 1009
CYCLIC_ION_BLASTER_HITS = int(EffectType.CyclicIonBlaster_AdditionalHits)             # 0x47c = 1148
EARLY_WARNING_OVERRIDE_ABILITY = "EarlyWarningOverride"     # config source (ctor `..(this, 0x435)`)
# --- #924 : la 2e sous-classe portee de `AReactivateOverwatchEffect` ------------------------------
# `InescapableDeathEffect$$.ctor` = `AReactivateOverwatchEffect..ctor(this, 0x3ed)` (TriggeredAbilityType
# `InescapableDeath`), `$$GetHitReductionEffectType` = `return 0x3fb`. Elle n'override NI
# `LegitDeathReasons` NI `HitReductionValue` : comptage des entrees `methodPointers` de la classe
# (4 exactement, aucune sur ces deux slots) -- cf. `entities/effects/loki/inescapable_death.py` §2.
INESCAPABLE_DEATH_EFFECT = int(EffectType.InescapableDeath_Effect)                    # 0x3fa = 1018
INESCAPABLE_DEATH_HITS_REDUCTION = int(EffectType.InescapableDeath_HitsReduction)     # 0x3fb = 1019
INESCAPABLE_DEATH_ABILITY = "InescapableDeath"              # config source (ctor `..(this, 0x3ed)`)
# --- #1077 : la 3e sous-classe portee de `AReactivateOverwatchEffect` -----------------------------
# `FiringPosition_ReactivateOverwatchEffect$$.ctor` = `AReactivateOverwatchEffect..ctor(this, 0x478)`.
# ⚠ L'OVERLOAD DU CTOR DE BASE EST TRANCHE PAR LA CIBLE DU `jmp`, PAS PAR L'ORDINAL : la base en
# declare DEUX (`baseAbility:ActiveAbilityType` et `baseAbility:TriggeredAbilityType`), et c'est le
# SECOND qui est appele. Donc `0x478` = **1144 `TriggeredAbilityType.FiringPosition`** -- le lire en
# `ActiveAbilityType` nommerait `BioMinefield` (1144 y est un membre VALIDE, deja au registre
# `ABILITY_CLASSES`), sans lever la moindre erreur.
FIRING_POSITION_REACTIVATE_OVERWATCH = int(EffectType.FiringPosition_ReactivateOverwatch)  # 0x47e = 1150
FIRING_POSITION_HIT_REDUCTION = int(EffectType.FiringPosition_HitReduction)                # 0x47f = 1151
FIRING_POSITION_ABILITY = "FiringPosition"                  # config source (ctor `..(this, 0x478)`)
# `IdunBattle.Operations.DamageReason.Ability` -- membre NOMME, plus l'ordinal nu (regle ENUM du
# CLAUDE.md). Le crush d'un `Steppable` grave `DamageReason.Steppable` : ce gate le REFUSE, et c'est
# le comportement natif (`LegitDeathReasons` ne cite que des morts par ABILITY).
DAMAGE_REASON_ABILITY = int(DamageReason.Ability)


def _hit_reduction_value(ability_id: str) -> int:
    """`AReactivateOverwatchEffect$$HitReductionValue` = `Direct(AbilityConfiguration.
    GetNumberConstant(config@0x60, 0x2c))` -- la CONSTANTE (hors niveau) `hitsReduction` de l'ability
    source de l'effet (0x435 = 1077 pour 1145). Lue dans gameconfig, jamais en dur."""
    import gameconfig as GC
    consts = (GC.ability(ability_id) or {}).get("constants") or {}
    return int(consts.get("hitsReduction") or 0)


def _attack_hits(state: State, unit_id: int, is_melee: bool) -> int:
    """`DSLFormulas$$RangedAttackHits(unit)` / `$$MeleeAttackHits(unit)` -- MEME classe de formule
    (`IdunBattle.Entities.Formulas.AttackHitsFormula`), seul le flag ranged/melee du ctor change (la
    STRUCTURE des arguments le montre ; le nom de ctor rendu par Ghidra est mislabele).

    `AttackHitsFormula$$Calculate` (decompile) : pour chaque unite du selecteur, resout l'arme du
    profil demande puis somme `BattleQuery.<slot 0xb6>(unit, weapon.Hits, weapon.IsMelee)` -- la facade
    `GetAttackHits` deja portee. COLLAPSE ASSUME (formule V, doctrine slice-18/19) : le port evalue le
    selecteur mono-unite et prend `nb de coups de l'arme + ExtraHits(0x11) [+ ExtraHitsMelee(0x17) en
    melee]` = `DamagePrediction$$GetDefaultAttackHits`, la base EXACTE de la facade. Les termes qui
    dependent d'une CIBLE (Parry/LightCover/BigTarget) sont hors de portee ici : le natif non plus
    n'en a pas (la formule est evaluee sans defenseur, sur le seul selecteur `Owner`).

    Le call-site est un GARDE (`Max(ranged, melee) > hitsReduction`) : il empeche la reduction de
    ramener une attaque a 0 coup."""
    e = state.get_entity(int(unit_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return 0
    ctx = sc.ctx
    dist = 1 if is_melee else 2                          # selection d'arme par portee (melee=adjacent)
    _p, _r, whits = select_weapon_pierce(ctx, dist)
    if select_weapon(ctx, dist) is None:
        return 0                                         # pas d'arme de ce profil -> 0 coup
    extra = int(ctx.stat(StatType.EXTRA_HITS))
    if is_melee:
        extra += int(ctx.stat(StatType.EXTRA_HITS_MELEE))
    return max(0, int(whits) + extra)


def has_death_reason(state: State, unit_id: int, damage_reason: int,
                     ability_or_effect: Optional[int]) -> bool:
    """`IdunBattle.Entities.Triggers.HasDeathReasonTrigger$$IsMatchingDeathReason` (MIRROR) applique a
    la `DamageSource` enregistree sur le `UnitComponent` de `unit_id` (`death_source`, cf.
    `runner/components.py`). `ability_or_effect=None` = le `Nullable` VIDE du natif (aucun filtre
    d'ability)."""
    e = state.get_entity(int(unit_id))
    uc = e.get_component(UnitComponent) if e is not None else None
    src = getattr(uc, "death_source", None) if uc is not None else None
    if not src:                                          # `!deathReason.HasValue` -> false
        return False
    _killer, reason, abil = src
    if int(reason) != int(damage_reason):
        return False
    if ability_or_effect is None:
        return True                                      # `!this.abilityOrEffect.HasValue` -> true
    return abil is not None and int(abil) == int(ability_or_effect)


class AReactivateOverwatch(EffectTrigger):
    """Triggered #1 de `AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal` -- le corps
    de la BASE, partage par toutes ses sous-classes. Les trois points de variation sont exactement
    les trois slots de vtable que le decompile appelle, et rien d'autre :

      * `HIT_REDUCTION_EFFECT_TYPE` = `GetHitReductionEffectType()`      (vtable +0x758)
      * `SOURCE_ABILITY`            = l'argument du `..ctor(this, <baseAbility>)`, donc le
                                      `config@0x60` que lit `HitReductionValue()` (vtable +0x748)
      * `_legit_death_reasons`      = `LegitDeathReasons()`              (vtable +0x738)

    Une sous-classe qui n'override PAS l'un d'eux prend celui de la base -- et c'est le comptage des
    entrees `methodPointers` (une par proprietaire, meme quand l'ICF fusionne les corps) qui dit
    lequel, jamais l'absence dans `frida/methods.tsv`."""
    event_id = EventTriggerType.PreUnitDeath            # On(1)
    #: `GetHitReductionEffectType()` -- l'effet stat-mod pose par `GetAddHitReductionBehaviour`.
    HIT_REDUCTION_EFFECT_TYPE: int = -1
    #: L'ability dont `HitReductionValue()` lit la constante `hitsReduction` (`AbilityConstantType` 0x2c).
    SOURCE_ABILITY: str = ""
    #: Nom d'`EffectType` de l'effet de reduction (pour `AddStaticStatModifierEffect`).
    HIT_REDUCTION_NAME: str = ""
    #: Nom d'`EffectType` du porteur du trigger (pour le journal d'evenement).
    EFFECT_NAME: str = ""

    def _legit_death_reasons(self, state: State, dying_id: Optional[int]) -> bool:
        """`AReactivateOverwatchEffect$$LegitDeathReasons` -- **le corps de la BASE**, un seul terme :
        `HasDeathReason(query@0x178, DamageReason.Ability, AbilityOrEffect(0x3f1 = 1009))`. Le
        selecteur natif est l'unite MOURANTE de l'`AbilityEntities` de `On(PreUnitDeath)`.

        Autrement dit : seule une mort causee par le TIR D'OVERWATCH lui-meme re-arme l'overwatch."""
        if dying_id is None:
            return False
        return has_death_reason(state, dying_id, DAMAGE_REASON_ABILITY, OVERWATCH_AUTO_ATTACK)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False                                 # `get_OwnerIsActor` : le porteur est le TUEUR
        # `NOT df@0xa0` = `NOT IsTurnOf(owner@0x148)` (le MEME champ pre-cache que lit
        # `RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal`, cf. `_ranged_auto_attack_is_active`).
        if state.current_player_id is not None:
            ow = state.get_entity(int(self.owner_id))
            oc = ow.get_component(OwnerComponent) if ow is not None else None
            if oc is not None and oc.player is not None \
                    and int(oc.player) == int(state.current_player_id):
                return False
        # `AmountIsGreater(Max(RangedAttackHits(Owner), MeleeAttackHits(Owner)), HitReductionValue())`
        red = _hit_reduction_value(self.SOURCE_ABILITY)
        best = max(_attack_hits(state, self.owner_id, is_melee=False),
                   _attack_hits(state, self.owner_id, is_melee=True))
        if not best > red:
            return False
        return self._legit_death_reasons(state, ev.dying_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        red = _hit_reduction_value(self.SOURCE_ABILITY)
        turns = turns_until_unit_owner_turn(state, self.owner_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `GetReactivateOverwatchBehaviour() & GetAddHitReductionBehaviour()` (`op_BitwiseAnd`).
        op_and(
            ActivateEffect(Caster(), OVERWATCH_AUTO_ATTACK,
                           EffectType.Overwatch_AutoAttack.name),
            AddStaticStatModifierEffect(Caster(), self.HIT_REDUCTION_EFFECT_TYPE,
                                        int(StatType.EXTRA_HITS), Const(-int(red)),
                                        name=self.HIT_REDUCTION_NAME,
                                        duration_turns=turns),
        ).execute(entities_from_state(state, self.owner_id, ev.dying_id), ectx)
        posed = [p for n, p in ectx.emitted if n == "AddStaticStatModifierEffect"]
        if not posed:
            return None                                  # deja pose (gate << deja present >>) -> muet
        return {"effect": self.EFFECT_NAME, "owner": int(self.owner_id),
                "killed": ev.dying_id, "hits_reduction": int(red), "turns": turns,
                "reactivated": [p for n, p in ectx.emitted if n == "ActivateEffect"]}


class EarlyWarningOverrideReactivateOverwatch(AReactivateOverwatch):
    """`EarlyWarningOverride_ReactivateOverwatchEffect` (1145) -- la sous-classe qui override
    `GetHitReductionEffectType` ET `LegitDeathReasons` (2 des 4 entrees `methodPointers` de la
    classe, les deux autres etant `.ctor` et `GetOverwatchExtraDamage`, cf. #924-r1).

    OBSERVABLE : quand Re'vas TUE en overwatch (ou avec les coups additionnels de son
    `CyclicIonBlaster`), pendant un tour qui n'est PAS le sien, elle recoit l'effet 1146
    `EarlyWarningOverride_HitReduction` = `EXTRA_HITS -hitsReduction` jusqu'a SON prochain tour."""
    effect_type = EWO_REACTIVATE_OVERWATCH
    HIT_REDUCTION_EFFECT_TYPE = EWO_HIT_REDUCTION
    SOURCE_ABILITY = EARLY_WARNING_OVERRIDE_ABILITY
    HIT_REDUCTION_NAME = EffectType.EarlyWarningOverride_HitReduction.name
    EFFECT_NAME = EffectType.EarlyWarningOverride_ReactivateOverwatch.name

    def _legit_death_reasons(self, state: State, dying_id: Optional[int]) -> bool:
        """`EarlyWarningOverride_ReactivateOverwatchEffect$$LegitDeathReasons` (**override**) =
        `HasDeathReason(dying, Ability, 1009) | HasDeathReason(dying, Ability, 1148)`. La base
        ne garde que la 1re branche. **1148 = `CyclicIonBlaster_AdditionalHits`** = l'effet du
        passif de Re'vas (triggered 1133) qui ajoute 3 coups Particle : un kill porte par CES
        coups-la compte AUSSI. C'est le point que « toute mort re-arme » aurait rate."""
        if dying_id is None:
            return False
        return (has_death_reason(state, dying_id, DAMAGE_REASON_ABILITY, OVERWATCH_AUTO_ATTACK)
                or has_death_reason(state, dying_id, DAMAGE_REASON_ABILITY, CYCLIC_ION_BLASTER_HITS))


class InescapableDeathReactivateOverwatch(AReactivateOverwatch):
    """`InescapableDeathEffect` (1018) -- la sous-classe qui n'override QUE
    `GetHitReductionEffectType` (`return 0x3fb` = 1019) sur cet axe.

    **Elle n'override PAS `LegitDeathReasons`** : ses 4 entrees `methodPointers` sont `.ctor`,
    `GetHitReductionEffectType`, `GetOverwatchExtraDamage` et `GetAdditionalExtraDamageTrigger`
    (`entities/effects/loki/inescapable_death.py` §2). Elle prend donc le corps de la BASE -- un
    SEUL terme, `HasDeathReason(dying, Ability, 1009)`. Recopier la version 1145 (deux termes)
    aurait re-arme l'overwatch sur des morts que le natif refuse ici.

    OBSERVABLE : quand `necroDestroyer` (Imospekh) TUE avec son tir d'overwatch, pendant un tour
    qui n'est PAS le sien, il reste en overwatch et recoit 1019 `InescapableDeath_HitsReduction`
    = `EXTRA_HITS -hitsReduction` jusqu'a SON prochain tour."""
    effect_type = INESCAPABLE_DEATH_EFFECT
    HIT_REDUCTION_EFFECT_TYPE = INESCAPABLE_DEATH_HITS_REDUCTION
    SOURCE_ABILITY = INESCAPABLE_DEATH_ABILITY
    HIT_REDUCTION_NAME = EffectType.InescapableDeath_HitsReduction.name
    EFFECT_NAME = EffectType.InescapableDeath_Effect.name


class FiringPositionReactivateOverwatch(AReactivateOverwatch):
    """`FiringPosition_ReactivateOverwatchEffect` (1150) -- la 3e sous-classe portee. Comme
    `InescapableDeath`, elle n'override QUE `GetHitReductionEffectType` sur cet axe.

    **SON BLOC `methodPointers` FAIT EXACTEMENT DEUX ENTREES**, et c'est ce comptage -- pas
    l'absence dans `frida/methods.tsv` -- qui etablit qu'elle n'override NI `LegitDeathReasons`,
    NI `HitReductionValue`, NI `GetOverwatchExtraDamage` :

      * `<bloc+0x0>` -> `FiringPosition_ReactivateOverwatchEffect$$.ctor` ;
      * `<bloc+0x8>` -> un corps `mov eax,0x47f ; ret` = `GetHitReductionEffectType` -> **1151
        `FiringPosition_HitReduction`**.

    ⚠ **CE SECOND CORPS N'EXISTE PAS SOUS SON NOM** : l'ICF le partage avec
    `IdunBattle.Entities.Effects.Loki.NeedsMoreDakka_PendingAttackEffect$$GetTriggeredAbilityType`,
    qui rend le MEME `0x47f` lu en `TriggeredAbilityType` (= `NeedsMoreDakka_Attack`). La table de
    symboles, indexee par ADRESSE, n'en nomme donc qu'UN SEUL proprietaire, et c'est l'autre. Ce
    sont les DEUX xrefs DATA du corps -- l'une adjacente au `.ctor` de CETTE classe -- qui donnent
    l'appartenance. L'entree qui suit le bloc appartient a `Unity.Services.Core.Device.
    UnityAdsIdentifier$$get_UserId`, donc le bloc s'arrete bien a deux.

    Elle prend en consequence le `LegitDeathReasons` de la BASE -- **un seul terme**,
    `HasDeathReason(dying, Ability, 1009)`. Recopier la version 1145 (deux termes, dont l'effet
    1148 de Re'vas) aurait re-arme l'overwatch sur des morts que le natif refuse ici : c'est le
    piege << voisin de forme >>, et le voisin est litteralement la classe soeur ci-dessus.

    `HitReductionValue()` (base) lit `GetNumberConstant(config, 0x2c = hitsReduction)` sur la config
    de l'ability passee au `.ctor`, donc celle de `FiringPosition` -> **2**, ce que l'i2 confirme
    mot pour mot (<< retaining 2 fewer hits >>) et que le port ne code PAS en dur.

    OBSERVABLE : quand le Havoc (`blackNpc4Havoc` / summon `blackSmnHavoc`) TUE avec son tir
    d'overwatch, pendant un tour qui n'est PAS le sien, il reste en overwatch et recoit 1151
    `FiringPosition_HitReduction` = `EXTRA_HITS -2` jusqu'a SON prochain tour."""
    effect_type = FIRING_POSITION_REACTIVATE_OVERWATCH
    HIT_REDUCTION_EFFECT_TYPE = FIRING_POSITION_HIT_REDUCTION
    SOURCE_ABILITY = FIRING_POSITION_ABILITY
    HIT_REDUCTION_NAME = EffectType.FiringPosition_HitReduction.name
    EFFECT_NAME = EffectType.FiringPosition_ReactivateOverwatch.name


class AReactivateOverwatchHitReductionPurge(EffectTrigger):
    """Triggered #2 de `AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal` :

        ( On(0 = UnitDeath) | On(0x11 = PostDamageTaken) )
          & NOT HasEffect(Owner@0x148, 0x3f1, onlyActive=1, targetType=Both)
        -> RemoveEffect(Owner@0x148, Nullable(GetHitReductionEffectType()))

    « des que le porteur n'a plus d'overwatch ACTIF, la reduction de coups saute » (sans attendre son
    expiration). `onlyActive=1` se lit, cote port, avec le modele presence + le gate d'activation deja
    porte (`_ranged_auto_attack_is_active`, case-127) : c'est LA meme condition que celle qui autorise
    le tir.

    Enregistre sur l'effet PORTEUR du trigger (1145 / 1018), pas sur l'effet de reduction : c'est
    `CreateHandleTriggerAbilitiesInternal` du porteur qui rend les DEUX `Triggered`.

    Comme le Triggered #1, le seul point de variation est `GetHitReductionEffectType()` (vtable
    +0x758) -- ici l'argument du `RemoveEffect`."""
    event_id = EventTriggerType.UnitDeath                                  # On(0)
    # 2e disjonct : `On(PostDamageTaken=0x11)`. AUCUN vecteur du port ne l'emet aujourd'hui (site
    # d'emission natif non localise) -- l'ecoute est declaree pour rester fidele, elle est dormante.
    event_ids = (int(EventTriggerType.UnitDeath), int(EventTriggerType.PostDamageTaken))
    #: `GetHitReductionEffectType()` -- l'effet que `RemoveEffect` retire.
    HIT_REDUCTION_EFFECT_TYPE: int = -1
    #: Nom d'`EffectType` correspondant (journal d'evenement).
    HIT_REDUCTION_NAME: str = ""

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if state.effects is None:
            return False
        if not state.effects.has_effect(int(self.owner_id),
                                        effect_type=self.HIT_REDUCTION_EFFECT_TYPE):
            return False                                 # rien a retirer -> le natif no-op aussi
        # `NOT HasEffect(Owner, Overwatch_AutoAttack, onlyActive=true, targetType=Both)` : `onlyActive`
        # se lit sur `EffectsState.active_effects`, qui conjugue le FLAG `EffectComponent.IsActive
        # @+0x5c` (#127) et la `CreateActiveCondition` -- exactement les deux conjoints natifs.
        active = any(int(e.effect_type) == OVERWATCH_AUTO_ATTACK
                     for e in state.effects.active_effects(
                         int(self.owner_id), unit_state_for_effects(state, int(self.owner_id))))
        return not active

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        RemoveEffect(self.HIT_REDUCTION_EFFECT_TYPE, Caster()).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        if not removed:
            return None
        return {"effect": self.HIT_REDUCTION_NAME, "owner": int(self.owner_id),
                "removed": removed}


class EarlyWarningOverrideHitReductionPurge(AReactivateOverwatchHitReductionPurge):
    """Triggered #2 de `EarlyWarningOverride_ReactivateOverwatchEffect` (1145 -> retire 1146)."""
    effect_type = EWO_REACTIVATE_OVERWATCH
    HIT_REDUCTION_EFFECT_TYPE = EWO_HIT_REDUCTION
    HIT_REDUCTION_NAME = EffectType.EarlyWarningOverride_HitReduction.name


class InescapableDeathHitReductionPurge(AReactivateOverwatchHitReductionPurge):
    """Triggered #2 de `InescapableDeathEffect` (1018 -> retire 1019)."""
    effect_type = INESCAPABLE_DEATH_EFFECT
    HIT_REDUCTION_EFFECT_TYPE = INESCAPABLE_DEATH_HITS_REDUCTION
    HIT_REDUCTION_NAME = EffectType.InescapableDeath_HitsReduction.name


class FiringPositionHitReductionPurge(AReactivateOverwatchHitReductionPurge):
    """Triggered #2 de `FiringPosition_ReactivateOverwatchEffect` (1150 -> retire 1151). #1077."""
    effect_type = FIRING_POSITION_REACTIVATE_OVERWATCH
    HIT_REDUCTION_EFFECT_TYPE = FIRING_POSITION_HIT_REDUCTION
    HIT_REDUCTION_NAME = EffectType.FiringPosition_HitReduction.name
