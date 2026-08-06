"""La branche SPECIALE de l'attaque normale de `FeederTendrils` (#419-r1-tr14-r4-r2-r1-r1).

`FeederTendrils_NormalAttack` (`ActiveAbilityType` 1120) est l'attaque normale que le PASSIF
`FeederTendrils` (`TriggeredAbilityType` 1197) substitue via
`IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromPassive` (cf.
`engine/services/custom_normal_attack.py`). Son `ExecuteBehaviour` n'est PAS l'attaque normale
generique : sous un gate de CHARGE AU CONTACT, il joue un bloc de plus.

`IdunBattleLogic.Entities.Abilities.Active.Loki.FeederTendrils_NormalAttackAbility$$ExecuteBehaviour`,
lu verbatim :

```csharp
weapon = FindAttackWeapon(entities);
if (weapon == null) return default;                              // NI Inform, NI attaque, NI triggers
charging = DSLTriggers.IsCharging(sel.Caster@+0x30, sel.Target@+0x60)
                      .Evaluate(entities, 0x20, ...);            // slot +0x188
isMelee  = WeaponProfile.get_IsMelee(weapon);
if ((charging & isMelee) == 0)
    return ALoki_NormalAttackAbility.ExecuteBehaviour(this, abilityState, entities);   // voie NORMALE
ExecuteInformWeapon(this, weapon, entities, useSpecial: 1);      // <- le TAG (deja porte)
ExecuteSpecialAttack(this, abilityState, entities, weapon);      // <- CE MODULE (inline au decompile)
ExecuteNormalAttack(this, abilityState, entities, weapon);       // l'attaque, INCHANGEE
return ExecuteTriggerAbilities(this, entities, weapon);
```

et le bloc, qui existe DEUX FOIS dans le binaire -- inline dans `ExecuteBehaviour` ET comme corps
autonome de `...FeederTendrils_NormalAttackAbility$$ExecuteSpecialAttack(this, abilityState,
entities, weapon)`. Les deux corps sont IDENTIQUES instruction pour instruction ; c'est une lecture
de controle gratuite, et elle concorde :

```csharp
amount  = DSLFormulas.ConfigVar(0x20, abilityState, this@+0x60);     // AbilityVariableType.hpToHeal
options = HealBehaviourOptions.ForHeal(AbilityOrEffect.op_Implicit(<this>));
b = DSLBehaviors.Heal(healer: sel@+0x30, selector: sel@+0x30, amount, options)      // le CASTER
  + DSLBehaviors.AddEffect(0x429, AbilityStateReference, targets: sel@+0x60, turns: null);  // la CIBLE
return ExecuteAtomic(this, b, entities, 0x2a);                       // GroupType.Ability_AtomicGroup
```

## Les DEUX ancres DIFFERENT, et c'est LU -- pas la meme unite des deux cotes

* `Heal` -> selecteur `+0x30`, passe DEUX FOIS (`healer` ET `selector` de
  `DSLBehaviors$$Heal(this, healer, selector, amount, options)`) : le caster se soigne LUI-MEME.
* `AddEffect(0x429)` -> selecteur `+0x60` : l'effet part sur la CIBLE.

Ce que `+0x30` et `+0x60` designent est etabli par le MEME `ExecuteBehaviour`, deux lignes plus
haut : `DSLTriggers$$IsCharging(this, caster, target)` (noms de parametres du dump) y recoit
`(*(sel+0x30), *(sel+0x60))`. Donc `+0x30` = CASTER et `+0x60` = TARGET. Lecture de controle
independante : `CordClawAbility$$ExecuteBehaviour` pose son self-buff via ce meme `+0x30`, et le
port l'ecrit deja `Caster()` (`strike.py`).

⚠ Ecrire les deux feuilles sur la MEME ancre serait la faute la plus facile ici : un `Pinned` sur le
caster au lieu de la cible, ou un soin de la cible, sont tous deux silencieux (aucune erreur), et
`Pinned` porte un malus de degat ATTAQUANT x0.70 -- donc la faute deplacerait un chiffre de degat au
tour suivant, pas celui-ci.

## Les litteraux, QUALIFIES sur le build courant (jamais infores d'un nom)

* `0x20` = 32 = `AbilityVariableType.hpToHeal`. ⚠ 32 est AUSSI `AbilityConstantType.hpForArmor` --
  deux enums, meme entier. Le discriminant n'est pas le nom mais la SURCHARGE appelee :
  `IdunBattleLogic.Entities.DSLFormulas$$ConfigVar` a cinq surcharges, et celle-ci a la signature
  `(this, variableType, abilityState, config)` (le 2e argument est le litteral, le 3e est
  l'`abilityState` copie, le 4e est `this@+0x60`). C'est donc bien un `variableType`.
* `0x429` = 1065 = `EffectType.Pinned` (UI « Suppressed »), effet DEJA porte et valide live
  (`engine/entities/effects/loki/status.py::PinnedEffect`).
* `0x2a` = 42 = `GroupType.Ability_AtomicGroup`. ⚠ 42 est AUSSI `StepType.RotateUnit` -- meme piege.
* `turns = null` (l'argument passe est `(void *)0x0`, SANS `TurnsFromRounds`) -> duree DEFAUT de
  l'effet (`DefaultAmountOfRounds`), exactement comme le `Pinned` de `CrushingClaws`/
  `SentinelDirectives`. Contraste LU dans le meme binaire : `CordClawAbility$$ExecuteBehaviour`, lui,
  passe `TurnsFromRounds(2)` a la meme position -- l'absence est donc un CHOIX du natif, pas un
  defaut de lecture.

## Le NIVEAU qui indexe `hpToHeal` -- passif d'abord

`hpToHeal` n'existe pas sous `FeederTendrils_NormalAttack` au gameconfig : l'entree qui la porte est
le PASSIF `FeederTendrils` (`variables = [extraDmg, hpToHeal]`). C'est coherent avec la fabrique,
qui monte l'attaque substituee avec l'`AbilityState` du passif
(`AddNormalAttackAbility` : `if (fromPassive.HasValue) { type = ...; state = triggeredAbilityState; }`)
-- c'est ce meme `abilityState` que `ExecuteBehaviour` passe a `ConfigVar`. Le port lit donc
`passive_ability_level`, fallback `active_ability_level` : MEME regle et MEME precedent que
`MV71SniperDroneSquad` (1076, derivee du passif 1119, `mv71.py`). Dans un runner rank-based les deux
coincident, mais on lit la BONNE source.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ....dsl.effects import ExecutionContext
from ....entities.behaviours import AtomicGroup, op_add
from ....entities.effect_type import EffectType
from ....entities.effects.magnitude import ability_var
from ....entities.selectors import Caster, Target
from ....streams.group_type import GroupType
from ...components import StatsComponent
from ..behaviours import AddEffect, Heal, entities_from_state, healable_heal_type_0

if TYPE_CHECKING:
    from ...state import State

#: L'entree GAMECONFIG qui porte `hpToHeal` : le PASSIF, pas l'attaque normale substituee.
CONFIG_ID = "FeederTendrils"

#: `AddEffect(0x429, ...)` -- `EffectType.Pinned` (1065), UI « Suppressed ».
PINNED = int(EffectType.Pinned)

#: `ExecuteAtomic(this, behaviour, entities, 0x2a)` -- `GroupType.Ability_AtomicGroup` (42).
ATOMIC_GROUP = int(GroupType.Ability_AtomicGroup)


def feeder_tendrils_heal_amount(state: "State", caster_id: int) -> int:
    """`DSLFormulas.ConfigVar(AbilityVariableType.hpToHeal, abilityState, config)` -- le montant du
    `Heal` de la branche speciale.

    Mirror de `ability_var` (qui bake le scaling rarete/progression `AbilityVariablesMultiplier`
    comme le natif le fait dans la config par-unite). Niveau = celui du PASSIF (cf. l'en-tete du
    module) ; fallback actif quand le canal passif est muet, MEME cascade que `mv71.py`."""
    e = state.get_entity(caster_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    level = getattr(ctx, "passive_ability_level", None) if ctx is not None else None
    if not level:
        level = getattr(ctx, "active_ability_level", None) if ctx is not None else None
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    return int(ability_var(CONFIG_ID, "hpToHeal", level, multiplier_pct=mult) or 0)


def feeder_tendrils_special_tree(heal_amount: int) -> AtomicGroup:
    """L'arbre DSL de `FeederTendrils_NormalAttackAbility$$ExecuteSpecialAttack` -- MIRROR 1:1 :

        ExecuteAtomic( op_Addition( Heal(caster, caster, ConfigVar(hpToHeal), ForHeal),
                                    AddEffect(0x429=Pinned, src=AbilityStateReference, target,
                                              turns: null) ),
                       entities, 0x2a )

    ORDRE : `Heal` PUIS `AddEffect` (volets gauche/droit de l'`op_Addition`). Les deux feuilles sont
    PURES (aucun tirage `state.rng`) et portent sur des unites DISTINCTES (caster / cible), donc
    l'ordre n'a aucun observable -- mais il mirrore le natif.

    ⚠ La garde `Healable` (`HealableUnitsSelector` : HP < max ET `IsAffectedByHealType(unit, 0)`)
    est portee COTE MUTATION par `healable_heal_type_0`, comme sur tous les autres `Heal` du port
    (`RevitalizingMalignancy`, `CombatRestoratives`). Un caster a PV pleins n'est donc pas soigne --
    et c'est le natif, pas une precaution : `HealUnitOperation` rend 0 sur une unite pleine.

    `source` de l'`AddEffect` = `AbilityStateReference` = le caster ; la feuille l'assigne
    implicitement (`entities.caster`), d'ou l'absence de `source_ref` ici."""
    heal = Heal(Caster(), heal_amount, guard=healable_heal_type_0)   # sel@+0x30, DEUX FOIS (healer+selector)
    pin = AddEffect(PINNED, "Pinned", Target(), None)                # sel@+0x60, duree DEFAUT (turns: null)
    return AtomicGroup(op_add(heal, pin))                            # ExecuteAtomic(.., 0x2a)


def execute_feeder_tendrils_special(state: "State", caster_id: int,
                                    target_id: Optional[int]) -> Optional[dict]:
    """Joue la branche speciale. APPELE PAR LE FOYER D'ATTAQUE NORMALE
    (`engine/runner/operations/damage_ops/normal.py`) au point EXACT du natif : apres
    `ExecuteInformWeapon`, AVANT `ExecuteNormalAttack`.

    ⚠ CET ORDRE EST OBSERVABLE, contrairement a celui des deux feuilles entre elles. `Pinned` porte
    un malus de degat ATTAQUANT (x0.70, `PinnedEffect.create_effect_damage_bonus_for_attack`, gate
    `OwnerIsCaster`) : il ne modifie donc PAS le degat de l'attaque qui suit (dont l'attaquant est le
    caster, pas la cible), mais il modifierait celui de la RIPOSTE / du tour suivant de la cible. Le
    jouer APRES l'attaque donnerait le meme chiffre aujourd'hui et un chiffre faux le jour ou un
    consommateur lirait l'etat entre les deux -- on mirrore la position, pas l'observable du jour.

    Rend un dict de trace (`None` si rien n'a pu etre joue), jamais leve : ce chemin est traverse par
    CHAQUE attaque normale du porteur."""
    if state is None or target_id is None:
        return None
    amount = feeder_tendrils_heal_amount(state, caster_id)
    ectx = ExecutionContext(state=state, rng=state.rng)
    feeder_tendrils_special_tree(amount).execute(
        entities_from_state(state, caster_id, target_id), ectx)
    healed = next((p for n, p in ectx.emitted if n == "Heal"), None) or {}
    pinned = next((p for n, p in ectx.emitted if n == "AddEffect"), None) or {}
    return {"ability": "FeederTendrils_NormalAttack", "caster": caster_id, "target": target_id,
            "heal_amount": amount, "heals": healed.get("heals"),
            "pinned_placed": pinned.get("placed"), "dsl": True}
