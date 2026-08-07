"""`MartialInspiration_ExtraDamage` (EffectType 0x580 = 1408) -- l'effet que l'active
`1191 MartialInspiration` pose SUR SON PROPRE CASTER avant de frapper. Porte #509.

Porteur unique : `custoBladeChampion` << Kariyan >> (Adeptus Custodes, lineup, dans le pool
`rl_duel build --list-pool` au rank 17).

i2 `Abilities/MartialInspiration_CurrentLevelDescription` : « Deals 3x <minDmg>-<maxDmg>
Eviscerating Damage to an adjacent enemy. **This attack and attacks from <i>Legacy of Combat</i>
this turn deal +<extraDmgPct>% Damage for each turn in which Kariyan performed an attack this
battle.** »

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- decompile = verite, live = confirmation
================================================================================================

## `IdunBattle.Entities.Effects.Loki.MartialInspiration_ExtraDamageEffect$$.ctor`

    BaseEffect..ctor(this, AbilityOrEffect(<0x580>), hasAutomaticActivation = 1)

## `IdunBattle.Entities.Effects.Loki.MartialInspiration_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`

MIRROR 1:1, terme a terme (slots `DSLFactory` : `+0x80 Formulas`, `+0x88 Triggers`,
`+0x90 Selectors` ; slot `DSLSelectors+0x30` = `Owner`) :

    pct    = DSLFormulas.ConfigVar( 0xa = 10 extraDmgPct, GetAbilityState(this), config@this+0x60 )
    turns  = DSLFormulas.TotalTurnsWithAttacksMade( Owner@DSLSelectors+0x30 )
    amount = DSLFormulas.Multiply( pct, turns )
    gate   = DSLTriggers.get_OwnerIsCaster
             op_BitwiseAnd (   DSLTriggers.CurrentAbilityIs( AbilityOrEffect(0x4a7) )
                            op_BitwiseOr
                               DSLTriggers.CurrentAbilityIs( AbilityOrEffect(0x527) ) )
    return Nullable( EffectBonus.ForPercentIncrease( gate, amount, AbilityOrEffect(0x580) ) )

`...$$GetBuffPct(dsl, config, abilityState)` est le MEME couple `ConfigVar(0xa) x
TotalTurnsWithAttacksMade(Owner)`, expose a part (2e lecteur du meme noeud).

### QUALIFICATION DES TROIS CONSTANTES -- trois SURCHARGES DIFFERENTES d'`op_Implicit`

Les trois `mov edx, imm32` du corps sont suivis de trois `call` DISTINCTS, lus a l'assembleur
(l'argument est perdu par la decompilation) :

  * `0x4a7 = 1191` -> `IdunBattle.Core.AbilityOrEffect$$op_Implicit` qui appelle
    `AbilityOrEffect$$set_ActiveAbility`   -> **`ActiveAbilityType.MartialInspiration`** ;
  * `0x527 = 1319` -> la surcharge qui appelle `AbilityOrEffect$$set_TriggeredAbility`
    -> **`TriggeredAbilityType.LegacyOfCombat`** (le passif homonyme de Kariyan) ;
  * `0x580 = 1408` -> la surcharge qui appelle `AbilityOrEffect$$set_Effect`
    -> **`EffectType.MartialInspiration_ExtraDamage`** (l'effet lui-meme, 3e arg de
    `ForPercentIncrease`).

Les rabattre sur un seul enum aurait ete SILENCIEUX : `1191` est aussi
`TriggeredAbilityType.HyperAggression` et `EffectType.HuntersBeyondDeathPsykerSuppression`, `1319`
est aussi `EffectType.SmashaEad`.

### ETAGE

`EffectBonus.ForPercentIncrease` ecrit la **%-list** du `DamageModifiers` ATTAQUANT
(`IdunBattle.Core.Services.DamageModifiers$$Add`), consommee par
`IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers` **APRES** percage/armure --
ce n'est NI un scale des bornes d'arme, NI un additif (meme etage que
`PrioritisedEfficiency_ExtraDmg`, cf. `extra_damage.py`).

### `TotalTurnsWithAttacksMade`

`IdunBattle.Entities.Formulas.TotalTurnsWithAttacksMadeFormula$$Calculate` rend
`ActorStatisticsComponent + 0x30` de l'unite selectionnee. Ce compteur est INCREMENTE par
`IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterAttackMade` **seulement quand le
set `+0x40` (`unitsAttackedThisTurn`) est VIDE** -- donc UNE FOIS par tour ou l'unite attaque -- et
le set est vide par `...$$ResetUnitsAttackedThisTurn`, appele par
`IdunBattle.Operations.StartTurnOperation$$Execute` / `$$ResetUnit` / `$$ResetMachine`.
Port : `runner/components.py::unit_turns_with_attacks_made`, threade dans `att_ctx` par
`runner/damage_model.py::attacker_modifiers` (meme regime que `tiles_moved_this_turn`).

================================================================================================
RESIDUS EXPLICITES (nommes, jamais lisses)
================================================================================================
 * **Branche `CurrentAbilityIs(TriggeredAbilityType.LegacyOfCombat)` INATTEIGNABLE cote port** :
   la triggered `1319 LegacyOfCombat` n'est pas portee (aucune entree de registre), et le canal
   `att_ctx["ability_type"]` n'est renseigne que par la voie ACTIVE
   (`damage_ops/ability.py`). Le gate se referme donc, ce qui est la degradation RESTRICTIVE
   attendue : le port ne fabrique pas de bonus sur une attaque qu'il ne joue pas.
 * `get_OwnerIsCaster` : ce canal (`build_attacker_modifiers_from_effects`) n'itere QUE les effets
   de l'ATTAQUANT -> le predicat est VRAI par construction, exactement comme pour
   `HeavyGravCannonEffect` / `PrioritisedEfficiency_ExtraDmg` (meme note, meme foyer).
 * Le compteur `turns_with_attacks_made` a DEUX ecrivains cote port, et c'est voulu : les
   operations OFFLINE (`components.register_attack_made`, appele par le chokepoint de degat) et le
   SEED depuis le RPC `actorStats` (`snapshot._load_actor_statistics`, champ
   `totalTurnsWithAttacksMade` que le hook publiait DEJA -- aucun capteur neuf n'a ete requis).
   Un etat recharge mid-bataille SANS `actor_stats=` repart donc a 0 : le bonus est alors NUL, pas
   faux (degradation restrictive), exactement comme les trois compteurs de tuiles voisins.
"""
from __future__ import annotations

from ....services.effect_bonus import EffectBonus, for_percent_increase
from ...ability_variable_type import AbilityVariableType
from ...active_ability_type import ActiveAbilityType
from ...triggered_ability_type import TriggeredAbilityType
from ..base import BaseEffect
from ..magnitude import ability_var

#: cle gameconfig de l'ability 1191 -- la config que `ConfigVar` resout (`this+0x60`).
MARTIAL_INSPIRATION = "MartialInspiration"
#: `ConfigVar(0xa)` -> `AbilityVariableType.extraDmgPct` (= 25..33 selon le niveau ; hors
#: `variablesAffectedByRarityBonus` -> le multiplier de rarete y est inerte).
VAR_EXTRA_DMG_PCT = AbilityVariableType.extraDmgPct                       # 0xa = 10
#: `CurrentAbilityIs(AbilityOrEffect(0x4a7))` -- surcharge `set_ActiveAbility`.
CURRENT_ACTIVE_ABILITY = int(ActiveAbilityType.MartialInspiration)        # 0x4a7 = 1191
#: `CurrentAbilityIs(AbilityOrEffect(0x527))` -- surcharge `set_TriggeredAbility`.
CURRENT_TRIGGERED_ABILITY = int(TriggeredAbilityType.LegacyOfCombat)      # 0x527 = 1319


class MartialInspirationExtraDamageEffect(BaseEffect):
    """`MartialInspiration_ExtraDamage` (0x580 = 1408) -- cf. l'en-tete de module pour la RE.

    `create_effect_damage_bonus_for_attack` =
    `ForPercentIncrease( OwnerIsCaster & (CurrentAbilityIs(1191) | CurrentAbilityIs(1319)),
    ConfigVar(extraDmgPct) x TotalTurnsWithAttacksMade(Owner) )`.

    Le produit vaut **0** tant que le porteur n'a attaque a aucun tour -- et c'est alors un bonus
    NUL, pas une absence de bonus : `for_percent_increase(True, 0)` serait un `EffectBonus` de
    valeur 0, indistinguable du None au niveau du scalaire. Le port rend `None` dans ce cas
    (aucune contribution a l'accumulateur), ce qui est bit-identique et evite un terme parasite
    dans les diagnostics."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        c = att_ctx or {}
        # `CurrentAbilityIs(0x4a7) | CurrentAbilityIs(0x527)`. Cle ABSENTE = canal non threade ->
        # gate FERME (degradation restrictive, convention du module : « present != applique »).
        cur = c.get("ability_type")
        if cur is None or int(cur) not in (CURRENT_ACTIVE_ABILITY, CURRENT_TRIGGERED_ABILITY):
            return None
        # `TotalTurnsWithAttacksMade(Owner@DSLSelectors+0x30)` : sur ce canal l'OWNER de l'effet EST
        # l'attaquant (l'agregateur n'itere que ses effets), donc le compteur threade est le sien.
        turns = c.get("turns_with_attacks_made")
        if not turns:
            return None                                   # produit nul -> aucune contribution
        # `ConfigVar(0xa, GetAbilityState(this), this+0x60)` : le niveau vient de l'ETAT D'ABILITY DE
        # LA SOURCE (le caster qui a pose l'effet), seede par `AddEffect(scale_from_source=True)`.
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else self.ability_level)
        if lvl is None:
            return None                                   # ConfigVar sans AbilityState -> inerte
        pct = ability_var(MARTIAL_INSPIRATION, VAR_EXTRA_DMG_PCT.name, lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not pct:
            return None
        return for_percent_increase(True, int(pct) * int(turns))   # `Multiply(pct, turns)`
