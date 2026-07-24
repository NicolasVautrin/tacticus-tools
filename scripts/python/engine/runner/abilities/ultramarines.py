"""Abilities Ultramarines (namespace natif `Abilities.Active.Loki.*`, faction Imperial/Ultramarines).

Module DEDIE (org faction, comme `deathguard.py`/`genestealer.py`) : l'org native est 1 classe par
ability (`Abilities.Active.Loki.<X>Ability`) ; les arbres SPECIFIQUES vivent avec leur classe. RE ghidra
gqfc5mff6c (VA citees). Case-220 §1 P0-HEAL.

Arbre `CombatRestorativesAbility.ExecuteBehaviour @1811cc590` (id 1002, ultraApothecary) — MIRROR du
DECOMPILE (+ `HealTargets @1811cca50`, callback `<ExecuteBehaviour>b__0 @1811e3e90`). JUMEAU IMPERIAL du
Chaos 1037 RevitalizingMalignancy (`deathguard.py`), mais AVEC DEUX DIFFERENCES STRUCTURELLES lues au
decompile (pas devinees par symetrie) :

    base        = Healable( op_Addition( Friends(AdjacentUnits(casterTile, 1)), caster ) )   # PAS d'exclusion trait
    withImperial = SelectUniqueUnits( UnitsWithTrait( base, 0x1a Imperial ) )    heal Get(var0x22)   # allies Imperial
    sans         = SelectUniqueUnits( op_Subtraction( base, withImperial ) )     heal Get(var0x20)   # tout le reste
    ExecuteAtomic( op_Addition( Heal(withImperial, ...) , Heal(sans, ...) ) )                 # withImperial PUIS sans

DIFFERENCE 1 -- PAS DE CUMUL. Le natif lit var0x22 (`GetVariableForLevel(0x22)` @1811cc590 -> +0x20) ET
var0x20 (`GetVariableForLevel(0x20)` -> +0x160) SEPAREMENT, SANS les sommer (contraste le jumeau 1037 ou
+0x160 = `iVar14 + iVar13`, CUMUL Chaos). Chaque groupe recoit UN montant simple :
  - allie IMPERIAL(0x1a) : var0x22 = `hpToHeal_2[level]`  (le PLUS gros, 5456 max)   [callback: 1er Heal]
  - allie NON-Imperial   : var0x20 = `hpToHeal[level]`    (4365 max)                 [callback: 2e Heal]
Les deux vars sont dans `variablesAffectedByRarityBonus` -> scalees par `AbilityVariablesMultiplier`
(mirror `ability_var(..., multiplier_pct=mult)`). Chaque `GetVariableForLevel` est lu+arrondi SEPAREMENT.

DIFFERENCE 2 -- PAS D'EXCLUSION DE TRAIT AU TOP. Le jumeau 1037 exclut Imperial du set entier
(`WithoutTrait(0x1a)`) -> les allies Imperial recoivent 0. Ici 1002 n'exclut RIEN : le set est
`Healable(Union(adjacent friends, self))` puis splitte Imperial / non-Imperial ; TOUS les allies adjacents
+ self (blesses, non-mechanical) sont soignes. `sans = op_Subtraction(base, withImperial)` == non-Imperial
membres de base (Xenos ET Chaos allies inclus, contrairement au 1037 qui excluait Imperial).

La garde `Healable` (`HealableUnitsSelector`, kind 4 du wrapper natif `FUN_180025220(4, ...)` applique a
base AVANT le split) est portee COTE MUTATION (feuille `Heal(guard=healable_heal_type_0)`, cf.
`behaviours/stats.py`) : Healable(base) puis split == split puis Healable-par-feuille (Healable idempotent,
distribue sur l'intersection/soustraction -> sets finaux identiques ; demonstration : withImperial cap
Healable = Imperial cap base cap Healable = Imperial cap Healable(base) ; sans cap Healable = idem).

Le trait Imperial(0x1a) est ABSENT de `gameconfig.unit().traits` (0 unite le porte) -> DERIVE de la
GrandAlliance (`GrandAlliance.GetTrait @1815647a0`) via `_grand_alliance_trait` (context.py), DEJA cable
dans `_unit_dict` (ajoute le trait d'alliance au set runner). REUTILISE tel quel (jumeau 1037)."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import op_add, op_and, AtomicGroup
from ...entities.selectors import (Caster, CasterTile, AdjacentUnits, Friends, Union,
                                   UnitsWithTrait, Sub, Unique, Target)
from ...entities.traits.unit_trait import UnitTrait
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effects.magnitude import ability_var
from ..components import StatsComponent
from .base import ActiveAbility
from .behaviours import (entities_from_state, Heal, healable_heal_type_0,
                         AttackWithAttackDamage, PushUnit)

if TYPE_CHECKING:
    from ..state import State

ABILITY_ID = "CombatRestoratives"


def _heal_amounts(state: "State", caster_id: int) -> tuple[int, int]:
    """(imperial, sans) — mirror des lectures de `ExecuteBehaviour @1811cc590` :
        var0x22 = GetVariableForLevel(config, 0x22) = `hpToHeal_2`  -> withImperial (allies Imperial)   [+0x20]
        var0x20 = GetVariableForLevel(config, 0x20) = `hpToHeal`    -> sans (non-Imperial)               [+0x160]
    AUCUNE somme (contraste 1037 ou +0x160 = iVar14 + iVar13). Chaque var est lue+arrondie SEPAREMENT via
    `ability_var` (le natif bake le scaling rarete/progression `AbilityVariablesMultiplierPercentage` dans
    la config par-unite ; les DEUX vars sont dans `variablesAffectedByRarityBonus`). ANGLE VALIDATOR : ne
    pas fitter un scalaire -- imperial et sans sont deux vars distinctes (hpToHeal_2 != hpToHeal)."""
    e = state.get_entity(caster_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    level = getattr(ctx, "active_ability_level", 0) if ctx is not None else 0
    mult = getattr(ctx, "ability_variables_multiplier", 100) if ctx is not None else 100
    imperial = int(ability_var(ABILITY_ID, "hpToHeal_2", level, multiplier_pct=mult) or 0)  # var0x22 (Imperial)
    sans = int(ability_var(ABILITY_ID, "hpToHeal", level, multiplier_pct=mult) or 0)        # var0x20 (non-Imperial)
    return imperial, sans


def combat_restoratives_tree(imperial_amount: int, sans_amount: int) -> AtomicGroup:
    """Arbre de `CombatRestorativesAbility.ExecuteBehaviour @1811cc590` (MIRROR 1:1 du decompile + callback
    `b__0 @1811e3e90`). `base` = self + allies adjacents (hex 1), filtre `Healable` porte cote mutation
    (`Heal(guard=healable_heal_type_0)`). Split par trait Imperial(0x1a) : allies Imperial = `imperial_amount`
    (var0x22 = hpToHeal_2), tout le reste = `sans_amount` (var0x20 = hpToHeal). `withImperial` /`sans` sont
    chacun wrappes `SelectUniqueUnits` (dedup natif, no-op sur des sets deja uniques -> mirror fidele).
    `sans = op_Subtraction(base, withImperial)` = membres non-Imperial de base. `AtomicGroup` (`ExecuteAtomic`,
    id 0x1f). Ordre callback natif : Heal(withImperial) PUIS Heal(sans) ; feuilles pures (aucun rng) + sets
    DISJOINTS -> ordre sans effet observable (fidelite conservee)."""
    base = Union(Friends(AdjacentUnits(CasterTile(), Const(1))), Caster())    # op_Addition(Friends(AdjacentUnits(casterTile,1)), caster)
    with_imperial = Unique(UnitsWithTrait(base, int(UnitTrait.Imperial)))     # SelectUniqueUnits(UnitsWithTrait(base, 0x1a))
    sans = Unique(Sub(base, with_imperial))                                   # SelectUniqueUnits(op_Subtraction(base, withImperial))
    heal_imperial = Heal(with_imperial, lambda entities, ectx: imperial_amount,
                         guard=healable_heal_type_0)                          # Get(var0x22) = hpToHeal_2
    heal_sans = Heal(sans, lambda entities, ectx: sans_amount,
                     guard=healable_heal_type_0)                              # Get(var0x20) = hpToHeal
    return AtomicGroup(op_add(heal_imperial, heal_sans))                      # ExecuteAtomic( withImperial + sans )


class CombatRestorativesAbility(ActiveAbility):
    """`CombatRestorativesAbility.ExecuteBehaviour @1811cc590` (id 1002, ultraApothecary — Ultramarines).

    Heal-splitte-par-trait (jumeau IMPERIAL de 1037 RevitalizingMalignancy) : soigne le caster + ses allies
    adjacents (hex 1). Le montant depend du trait Imperial de la cible :
      - allie IMPERIAL(0x1a) : `hpToHeal_2[level]`  (var0x22)
      - allie NON-Imperial   : `hpToHeal[level]`    (var0x20)
    PAS de cumul (contraste 1037) ; PAS d'exclusion de trait (tous les allies adjacents + self, blesses +
    non-mechanical, sont soignes). Garde `Healable` (HP<max ET non-mechanical) portee cote mutation (feuille
    `Heal(guard=...)`). Behaviour = arbre DSL `combat_restoratives_tree` (mirror 1:1 du decompile + callback
    `b__0 @1811e3e90`). Deterministe (aucun rng)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.CombatRestoratives)  # 1002
    ABILITY_ID = ABILITY_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # Montants lus AU CAST (mirror : le natif lit var0x22/var0x20 dans ExecuteBehaviour et les fige dans
        # le closure de l'AtomicGroup) ; l'arbre cible Caster() (pas Target()) -> target_id indifferent.
        imperial_amount, sans_amount = _heal_amounts(state, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        combat_restoratives_tree(imperial_amount, sans_amount).execute(entities, ectx)
        heals = [p for n, p in ectx.emitted if n == "Heal"]
        return {"ability": ABILITY_ID, "caster": caster_id, "target": target_id,
                "imperial_amount": imperial_amount, "sans_amount": sans_amount,
                "heals": heals, "dsl": True}


MORTIS_ROUND_ID = "MortisRound"


def mortis_round_tree() -> AtomicGroup:
    """Arbre de `MortisRoundAbility.ExecuteBehaviour @1811f54a0` (id 1004, ultraEliminatorSgt — MIRROR du
    DECOMPILE + callback `<ExecuteBehaviour>b__0 @1811fd290`) :
        AtomicGroup( 0x3f, [callback b__0 = ] Execute(attack) PUIS Execute(push) )
      attack = AttackWithAttackDamage(caster@factory+0x160, target@factory+0x178, MinMaxDamage(minDmg 0xc/
               maxDmg 0xd), GetDamageProfile=HeavyRound, hitsNode@factory+0xc0, AbilityOrEffect(*this+0x10
               =1004))                                          # 1x HeavyRound ranged (i2 « 1x 3274-3638 »)
      push   = PushUnit(factory, caster@factory+0x160, target@factory+0x178, 0)   # recul 1 hex (i2)

    Structure = SOUS-ENSEMBLE de ThunderousAssault (`strike.py`) : attaque MONO-cible + push, SANS stun/
    kill-dead/charge. Le natif enroule l'attaque et le push dans un `AtomicGroup(0x3f, callback)` : le
    callback `b__0` execute `AActiveAbility.Execute(attack_node)` PUIS `AActiveAbility.Execute(push_node)`
    (ordre attaque-AVANT-push lu au decompile). Port : `AtomicGroup(op_and(Attack, Push))` — `op_and` =
    `CombinedBehaviour` (Seq gauche->droite, effets PURS) == l'ordre du callback ; `AtomicGroup` = inline
    pass-through (RE #201). `PushUnit` est DETERMINISTE (aucun tirage rng) -> ne decale PAS l'ordre RNG de
    l'attaque : bit-exact BY CONSTRUCTION vs un imperatif attaque->push.

    Overload d'attaque : le call-site @1811f5683 appelle `DSLFactory.AttackWithAttackDamage @180dea520`
    (famille ATTACK, resolu par XREF — PAS le nom ; @180dea520 != le @180de9fb0 de ThunderousAssault, mais
    MEME famille attack, precedents portes ScythingTalons/Executioner) -> `native_factory="attack"` (defaut,
    resolve slot-8 gaspille = 2 tirages/coup a cc=0). Profil `HeavyRound` (constants.damageProfile), attaque
    RANGED (attackRangeType=Ranged, range 3) -> `is_melee=False`. `nrOfHits` ABSENT de la config (constants
    n'a que damageProfile) -> `ability_attack_params` rend hits=1 (== i2 « 1x »). `ability_type=1004` threade
    l'AbilityOrEffect du coup (mirror `op_Implicit(*this+0x10)` natif = 7e arg de AttackWithAttackDamage) —
    c'est le VEHICULE du gate `TriggeringAbilityIs(0x3ec=1004)` du bonus HeavyWeapon_ExtraDmg (#47 :
    `execute_ability_attack` threade DESORMAIS is_ranged + trigger_ability_type -> +50% valide bit-exact)."""
    attack = AttackWithAttackDamage(Target(), MORTIS_ROUND_ID, "HeavyRound", is_melee=False,
                                    ability_type=int(ActiveAbilityType.MortisRound))
    push = PushUnit(Caster(), Target())
    return AtomicGroup(op_and(attack, push))


class MortisRoundAbility(ActiveAbility):
    """`MortisRoundAbility.ExecuteBehaviour @1811f54a0` (id 1004, ultraEliminatorSgt « Eliminator Sergeant »,
    Ultramarines — namespace natif `Abilities.Active.Loki.MortisRoundAbility`). MIRROR du DECOMPILE, arbre DSL
    (`mortis_round_tree`) :
        AtomicGroup( Attack(HeavyRound, 1x, caster->target) PUIS PushUnit(caster, target) )

    i2 : « Deals 1x 3274-3638 Heavy Round Damage to a single target within range 3, which is then pushed back
    1 hex. The Heavy Weapon trait applies double to this ability. » Le behaviour = attaque MONO-cible HeavyRound
    (1 coup) + recul 1 hex de la cible (`DisplaceUnitOperation`, no-op si BigTarget/Immovable/bord). SOUS-ENSEMBLE
    structurel de ThunderousAssault (attaque + push, sans stun/charge).

    QUIRK « Heavy Weapon applies double » (i2) — RESOLU #47 (2026-07-24) : n'est PAS dans
    l'ExecuteBehaviour. C'est un raffinement de l'effet `HeavyWeapon_ExtraDmgEffect.CreateDamageModifier
    @180f4f030` (accorde par le trait HeavyWeapon du carrier ; effet 1008 SEEDE dans le runner) :
    `amount = ConditionalAmount(TriggeringAbilityIs(0x3ec=1004) ? Multiply(base, Direct(2)) : base)`
    ou `base = ConfigConst 0xf = heavyWeaponExtraDmg` (=25). => le bonus +extraDmg% des attaques RANGED du
    porteur (gate `OwnerIsCaster & IsRangedAttack & no-move`) est DOUBLE (+50% au lieu de +25%) quand l'attaque
    declenchante est MortisRound. #47 : `execute_ability_attack` threade `is_ranged` + `trigger_ability_type`
    dans la collecte attacker-modifiers (gate famille ATTACK, cf. damage.py) -> le x2 s'applique via
    `att_ctx["trigger_ability_type"]` lu par `HeavyWeaponExtraDmgEffect`. L'ancien ratio live ~3.15x etait
    DEUX etages : x1.5 (HeavyWeapon double) + KNOCKBACK de collision du push BLOQUE au bord
    (`ApplyKnockbackTo @180e67fc0` = ceil(maxHealth x 10%), porte #47 dans displace.py) — PAS un crit-rng
    desync (refute par comptage mti : 2 tirages/cast = valeur + resolve, AUCUN crit-roll). VALIDE bit-exact
    live (probe_mortis_round C : 15256 push bloque ; probe_47 mortis-free : 7256 push libre sans knockback).

    Push DETERMINISTE (aucun rng) -> n'altere PAS l'ordre RNG de l'attaque : la SEQUENCE attaque->push est
    fidele BY CONSTRUCTION (l'attaque delegue au pipeline partage `execute_ability_attack`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.MortisRound)  # 1004
    ABILITY_ID = MORTIS_ROUND_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        mortis_round_tree().execute(entities, ectx)
        atk = next((p.get("attack") for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        push = next((p for n, p in ectx.emitted if n == "PushUnit"), None)
        return {"ability": MORTIS_ROUND_ID, "caster": caster_id, "target": target_id,
                "main_attack": atk, "push": push, "dsl": True}
