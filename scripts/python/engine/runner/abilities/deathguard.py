"""Abilities Death Guard (namespace natif `Abilities.Active.Loki.*`, faction Nurgle/Chaos).

Module DEDIE (org faction, comme `genestealer.py`) : l'org native est 1 classe par ability
(`Abilities.Active.Loki.<X>Ability`) ; les arbres SPECIFIQUES vivent avec leur classe. RE ghidra
gqfc5mff6c (VA citees). Case-220 §1 P0-HEAL, jumeau heal 1002 CombatRestoratives cote Chaos.

Arbre `RevitalizingMalignancyAbility.ExecuteBehaviour @181200eb0` (id 1037, deathRotbone) — MIRROR
du DECOMPILE (+ `GetAllHealTargets @181201150`, `GetChaosHealTargets @181201230`,
`GetRegularHealTargets @181201280`, callback `<ExecuteBehaviour>b__0 @181218d00`) :

    AllHealTargets = Healable( UnitsWithoutTrait( 0x1a Imperial,
                                op_Addition( Friends(AdjacentUnits(caster, 1)), caster ) ) )
    regular = UnitsWithoutTrait(0x7ea Chaos, AllHealTargets)   heal Direct(var0x20)             # non-Chaos
    chaos   = UnitsWithTrait(0x7ea Chaos, AllHealTargets)      heal Direct(var0x22 + var0x20)   # Chaos (CUMUL)
    ExecuteAtomic( op_Addition( Heal(regular, ...) , Heal(chaos, ...) ) )                       # regular PUIS chaos

var0x20 = `GetVariableForLevel(config, 0x20)` = `hpToHeal` (regular) ; var0x22 =
`GetVariableForLevel(config, 0x22)` = `hpToHeal_2`. Le montant Chaos est la SOMME de DEUX vars lues
et arrondies SEPAREMENT (`iVar14 + iVar13` @181200eb0), PAS un scalaire cale ni `round((a+b)*mult)`.
La garde `Healable` (`HealableUnitsSelector`, prerequis case-220 manquant) est portee COTE MUTATION
(feuille `Heal(guard=...)`, cf. `_healable_heal_type_0`)."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import op_add, op_and, AtomicGroup
from ...entities.selectors import (Caster, CasterTile, AdjacentUnits, Friends, Union,
                                   UnitsWithoutTrait, UnitsWithTrait, Target)
from ...entities.traits.unit_trait import UnitTrait
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effects.magnitude import ability_var
from ..components import StatsComponent
from .base import ActiveAbility
from .behaviours import (entities_from_state, Heal, healable_heal_type_0,
                        AttackWithAttackDamage, InformWeapon)

if TYPE_CHECKING:
    from ..state import State

ABILITY_ID = "RevitalizingMalignancy"


def _heal_amounts(state: "State", caster_id: int) -> tuple[int, int]:
    """(regular, chaos) — mirror des lectures de `ExecuteBehaviour @181200eb0` :
        iVar13 = GetVariableForLevel(config, 0x20) = `hpToHeal`   -> regular
        iVar14 = GetVariableForLevel(config, 0x22) = `hpToHeal_2`
        chaos  = iVar14 + iVar13                                  (CUMUL des DEUX vars)
    Chaque `GetVariableForLevel` est lu + arrondi SEPAREMENT (le natif bake le scaling rarete/progression
    `AbilityVariablesMultiplierPercentage` dans la config par-unite) via `ability_var` : la somme Chaos =
    round(hpToHeal*mult) + round(hpToHeal_2*mult), PAS round((hpToHeal+hpToHeal_2)*mult) (ANGLE VALIDATOR :
    ne pas fitter un scalaire ; `hpToHeal`/`hpToHeal_2` sont dans `variablesAffectedByRarityBonus`)."""
    e = state.get_entity(caster_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    level = getattr(ctx, "active_ability_level", 0) if ctx is not None else 0
    mult = getattr(ctx, "ability_variables_multiplier", 100) if ctx is not None else 100
    reg = int(ability_var(ABILITY_ID, "hpToHeal", level, multiplier_pct=mult) or 0)      # var0x20 (iVar13)
    bonus = int(ability_var(ABILITY_ID, "hpToHeal_2", level, multiplier_pct=mult) or 0)  # var0x22 (iVar14)
    return reg, reg + bonus                                                              # regular, chaos = iVar14 + iVar13


def revitalizing_malignancy_tree(regular_amount: int, chaos_amount: int) -> AtomicGroup:
    """Arbre de `RevitalizingMalignancyAbility.ExecuteBehaviour @181200eb0` (MIRROR 1:1 du decompile +
    callback `b__0 @181218d00`). `AllHealTargets` = self + allies adjacents (hex 1) NON-Imperial, filtre
    `Healable` porte cote mutation (`Heal(guard=healable_heal_type_0)`). Split par trait Chaos(0x7ea) :
    non-Chaos = `regular_amount` (var0x20), Chaos = `chaos_amount` (var0x20+var0x22). `AtomicGroup`
    (`ExecuteAtomic`, id 0x1f) inline (RE #201). Ordre callback natif : Heal(regular) PUIS Heal(chaos) ;
    les deux feuilles sont pures (aucun rng) et les sets DISJOINTS -> ordre sans effet observable."""
    all_heal = UnitsWithoutTrait(
        Union(Friends(AdjacentUnits(CasterTile(), Const(1))), Caster()),
        int(UnitTrait.Imperial))                              # WithoutTrait(0x1a, Union(Friends(AdjacentUnits(self,1)), self))
    regular_sel = UnitsWithoutTrait(all_heal, int(UnitTrait.Chaos))   # regular = WithoutTrait(0x7ea)
    chaos_sel = UnitsWithTrait(all_heal, int(UnitTrait.Chaos))        # chaos   = WithTrait(0x7ea)
    regular = Heal(regular_sel, lambda entities, ectx: regular_amount, guard=healable_heal_type_0)  # Direct(var0x20)
    chaos = Heal(chaos_sel, lambda entities, ectx: chaos_amount, guard=healable_heal_type_0)        # Direct(var0x22+var0x20)
    return AtomicGroup(op_add(regular, chaos))                # ExecuteAtomic( regular + chaos )


class RevitalizingMalignancyAbility(ActiveAbility):
    """`RevitalizingMalignancyAbility.ExecuteBehaviour @181200eb0` (id 1037, deathRotbone — Death Guard).

    Heal-splitte-par-trait (jumeau Chaos de 1002 CombatRestoratives) : soigne le caster + ses allies
    adjacents (hex 1) NON-Imperial. Le montant depend du trait Chaos de la cible :
      - allie NON-Chaos : `hpToHeal[level]`                      (var0x20)
      - allie Chaos     : `hpToHeal[level] + hpToHeal_2[level]`  (var0x22 + var0x20, CUMUL)
    Garde `Healable` (HP<max ET non-mechanical) portee cote mutation (feuille `Heal(guard=...)`). Behaviour
    = arbre DSL `revitalizing_malignancy_tree` (mirror 1:1 du decompile + callback `b__0 @181218d00`).
    Deterministe (aucun rng)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.RevitalizingMalignancy)  # 1037
    ABILITY_ID = ABILITY_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # Montants lus AU CAST (mirror : le natif lit var0x20/var0x22 dans ExecuteBehaviour et les fige dans
        # le closure de l'AtomicGroup) ; l'arbre cible Caster() (pas Target()) -> target_id indifferent.
        regular_amount, chaos_amount = _heal_amounts(state, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        revitalizing_malignancy_tree(regular_amount, chaos_amount).execute(entities, ectx)
        heals = [p for n, p in ectx.emitted if n == "Heal"]
        return {"ability": ABILITY_ID, "caster": caster_id, "target": target_id,
                "regular_amount": regular_amount, "chaos_amount": chaos_amount,
                "heals": heals, "dsl": True}


# ===================== FlailSwing (deathBlightlord, actif 1042) =====================

def flail_swing_tree() -> "op_and":
    """Arbre de `FlailSwingAbility$$ExecuteBehaviour @1811ded80` (id 1042, deathBlightlord — MIRROR du
    DECOMPILE) :
        Execute( op_BitwiseAnd(
            InformWeapon(GetDamageProfile=Power, 1),                                        # metadata arme
            AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                                   GetDamageProfile=Power, nrOfHits=GetNumberConstant(0x2f)=3,
                                   source=AbilityOrEffect(FlailSwing),
                                   alwaysOverkilled=Nullable(true)) ) )

    Port : `op_and( InformWeapon("Power"), AttackWithAttackDamage(Target(), "FlailSwing", "Power", melee) )`
    -- plain `Execute` (PAS `ExecuteAtomic` : le decompile passe l'`op_BitwiseAnd` DIRECTEMENT a
    `AActiveAbility.Execute`, aucun AtomicGroup autour -- contraste BringerOfDespair @1811be740). Details RE :

    - `nrOfHits` = `GetNumberConstant(config, 0x2f)` = 3 (config FlailSwing `constants.nrOfHits`="3", verifie
      gameconfig). `MinMaxDamage(param_1, ...)` @... = bornes `minDmg`(0xc)/`maxDmg`(0xd)[level] brutes de la
      config (aucun `GetAttackDamage` surcharge -> pas de `damage_override`). Profil `GetDamageProfile(config,0)`
      = `Power` (`constants.damageProfile`="Power" ; melee, PiercingRatio 40). `attackRangeType=Melee` ->
      `is_melee=True`.
    - **native_factory = "attack"** (defaut, 2 tirages/coup a cc=0) : le decompile appelle litteralement
      `DSLFactory.AttackWithAttackDamage @180de9fb0` (famille attack, VERIFIE par la CALLEE de @1811ded80 =
      symbole `DSLFactory$$AttackWithAttackDamage`, JAMAIS `AttackWithAbilityDamage @180de9c90` ; tip #2 /
      rngcrit-1202). Attaque MULTI-COUPS (3x) -> classification par XREF OBLIGATOIRE, faite ici.
    - `InformWeapon` = `op_BitwiseAnd` volet GAUCHE (execute EN PREMIER) : canal weapon-inform (metadata,
      `ActivateEffectBehaviour`) COMBAT-INERTE (0 RNG, 0 mutation PV/stat) -> n'altere PAS l'ordre `state.rng`
      de l'attaque : bit-exact BY CONSTRUCTION. Le trigger consommateur (`HazeOfCorruption`) est un passif
      SEPARE (hors face COMBAT) -- le declenchement Haze n'est PAS dans cet ExecuteBehaviour.
    - **`alwaysOverkilled` (Nullable=true) PORTE via `force_overkill=True`** : le 8e arg de
      `AttackWithAttackDamage @180de9fb0` (`&local_198` = `Nullable<bool>` HasValue=1, cf. `local_1e8=0x100000000`
      + `System.Nullable<...>.ctor`) = flag « always overkilled » passe a `AttackDamageBehaviour` puis a l'etage
      `ApplyTraitDamageLimitsToDamage @18102c650` (`overkill=true` bypasse le cap Resilient
      `ApplyResilientTraitDamageLimit @18102c3a0`). La feuille passe `force_overkill=True` -> `_run_hits` force
      `overkill=True` a chaque coup. VALIDE LIVE (deathBlightlord vs custoKyrus Resilient HP 10000 : live tue
      [5070,4555,375] sum=10000 == PV full ; le port SANS le flag laissait 1 PV [5070,4555,374] sum=9999 -> le
      flag est le seul ecart). No-op sur cible non-Resilient -> coeur 3x Power bit-exact partout."""
    return op_and(InformWeapon("Power"),
                  AttackWithAttackDamage(Target(), "FlailSwing", "Power", is_melee=True, force_overkill=True))


class FlailSwingAbility(ActiveAbility):
    """`FlailSwingAbility$$ExecuteBehaviour @1811ded80` (id 1042, deathBlightlord — Death Guard/Chaos, namespace
    natif `Abilities.Active.Loki`). Arbre DSL `flail_swing_tree()` (MIRROR 1:1 du decompile) :
        Execute( op_BitwiseAnd(
            InformWeapon(Power),                                                    # metadata arme (no-op combat)
            AttackWithAttackDamage(caster, target, MinMaxDamage, Power, nrOfHits=3, alwaysOverkilled=1) ) )

    Attaque MELEE MONO-CIBLE : 3 coups Power (PiercingRatio 40) sur la cible du message. PAS de splash, PAS de
    move/gate, PAS de trigger interne. La feuille `AttackWithAttackDamage` (native_factory="attack", VERIFIE
    par XREF de @1811ded80) emet la MEME Operation que l'attaque generique (`AttackDamageOperation.
    execute_ability_attack`, 2 tirages/coup a cc=0) -> bit-exact BY CONSTRUCTION (memes bornes/hits/profil/
    state.rng). `InformWeapon` (volet gauche du op_and) = canal weapon-inform combat-inerte (consommateur =
    passif `HazeOfCorruption`, hors scope). Termine le tour (1042 hors des frozensets base.py -> flags defaut).

    Flag `alwaysOverkilled` (Nullable=1) PORTE via `force_overkill=True` (feuille -> `execute_ability_attack`
    -> `_run_hits` force `overkill=True` par coup, bypasse le cap Resilient `ApplyResilientTraitDamageLimit`).
    Ne change de resultat QUE vs cible Resilient/revive (no-op numerique sinon). VALIDE LIVE (custoKyrus
    Resilient HP 10000 : live tue = sum 10000 == PV full ; port sans flag laissait 1 PV = le seul ecart)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.FlailSwing)  # 1042
    ABILITY_ID = "FlailSwing"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        flail_swing_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atk = next((p["attack"] for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        informed = next((p.get("profile") for n, p in ectx.emitted if n == "InformWeapon"), None)
        return {"ability": "FlailSwing", "caster": caster_id, "target": target_id,
                "attack": atk, "informed_weapon": informed, "dsl": True}
