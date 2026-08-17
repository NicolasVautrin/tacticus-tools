"""Abilities Death Guard (namespace natif `Abilities.Active.Loki.*`, faction Nurgle/Chaos).

Module DEDIE (org faction, comme `genestealer.py`) : l'org native est 1 classe par ability
(`Abilities.Active.Loki.<X>Ability`) ; les arbres SPECIFIQUES vivent avec leur classe. RE ghidra
gqfc5mff6c (VA citees). Case-220 §1 P0-HEAL, jumeau heal 1002 CombatRestoratives cote Chaos.

Arbre `IdunBattleLogic.Entities.Abilities.Active.Loki.RevitalizingMalignancyAbility$$ExecuteBehaviour` (id 1037, deathRotbone) — MIRROR
du DECOMPILE (+ `IdunBattleLogic.Entities.Abilities.Active.Loki.RevitalizingMalignancyAbility$$GetAllHealTargets`, `IdunBattleLogic.Entities.Abilities.Active.Loki.RevitalizingMalignancyAbility$$GetChaosHealTargets`,
`IdunBattleLogic.Entities.Abilities.Active.Loki.RevitalizingMalignancyAbility$$GetRegularHealTargets`, callback `<ExecuteBehaviour>b__0 IdunBattleLogic.Entities.Abilities.Active.Loki.RevitalizingMalignancyAbility.u003Cu003Ec__DisplayClass2_0$$u003CExecuteBehaviouru003Eb__0`) :

    AllHealTargets = Healable( UnitsWithoutTrait( 0x1a Imperial,
                                op_Addition( Friends(AdjacentUnits(caster, 1)), caster ) ) )
    regular = UnitsWithoutTrait(0x7ea Chaos, AllHealTargets)   heal Direct(var0x20)             # non-Chaos
    chaos   = UnitsWithTrait(0x7ea Chaos, AllHealTargets)      heal Direct(var0x22 + var0x20)   # Chaos (CUMUL)
    ExecuteAtomic( op_Addition( Heal(regular, ...) , Heal(chaos, ...) ) )                       # regular PUIS chaos

var0x20 = `GetVariableForLevel(config, 0x20)` = `hpToHeal` (regular) ; var0x22 =
`GetVariableForLevel(config, 0x22)` = `hpToHeal_2`. Le montant Chaos est la SOMME de DEUX vars lues
et arrondies SEPAREMENT (`iVar14 + iVar13` IdunBattleLogic.Entities.Abilities.Active.Loki.RevitalizingMalignancyAbility$$ExecuteBehaviour), PAS un scalaire cale ni `round((a+b)*mult)`.
La garde `Healable` (`HealableUnitsSelector`, prerequis case-220 manquant) est portee COTE MUTATION
(feuille `Heal(guard=...)`, cf. `_healable_heal_type_0`)."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import hexgeo

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import op_add, op_and, AtomicGroup, Group
from ...entities.selectors.accessors import (
    ActiveTarget, Actor, CasterTile, FixedTileIds, Subject, SurroundingTiles, Target
)
from ...entities.selectors.tiles import TileIntersect, TileUnion, TileUnique
from ...entities.selectors.composites import adjacent_units
from ...entities.selectors.geometry import Cache
from ...entities.selectors.tiles import AdjacentTiles, Caster
from ...entities.selectors.units import (
    AdjacentUnits, Enemies, Filter, Friends, Sub, Union, Unique, Units, UnitsDirectlyBehind,
    UnitsWithTrait, UnitsWithoutTrait
)
from ...entities.selectors.units import AdjacentFriends
from ...entities.triggers import (AmountIsGreaterThanZero, HasNegativeModifier, HasTrait,
                                  IsInTeamAura, IsInUnitAura, TriggerAnd, TriggerOr)
from ...entities.formulas import Half, If, Multiply, StatAmount, Sum
from ...entities.effect_type import EffectType
from ...entities.stats import StatType, StatPart
from ...entities.traits.unit_trait import UnitTrait
from ...entities.unit_selection_type import UnitSelectionType

#: `UnitSelectionType` LU au dernier argument des `DSLSelectors$$*` de ce fichier -- releve #585-r1,
#: build `rnca9r7q6c`, littéral par littéral (jamais par symetrie).
#: `OnlyAliveAndTargetable` = `IsAlive && !HasFlag(UnitFlag.Untargetable)`, applique PAR ELEMENT par
#: `IdunBattle.DSL.TargetsSelector$$SelectUnit` -> `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType`.
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effects.magnitude import ability_var
from ..components import PositionComponent, StatsComponent, UnitComponent, get_unit_feet
from .base import ActiveAbility
# FORME B (#485-r1-r1) : on lie le MODULE, pas le nom -- c'est la seule des trois ecritures ou un
# `monkeypatch.setattr("....targeting.get_adjacent_tiles", ...)` MORD. Aucun cycle : `targeting` ne
# reimporte pas `deathguard`, et ce module l'importe deja par la ligne suivante.
from . import targeting as _targeting
from .targeting import (custom_range, custom_range_func, RANGE_ADJACENT, RANGE_FROM_CONFIG,
                        RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE, RANGED_BOOL_TRUE, TargetingOptions)
from .targeting_rule import TargetingRule as TR
from .behaviours.combat import AttackWithAbilityDamage, AttackWithAttackDamage, InformWeapon
from .behaviours.context import entities_from_state, main_tile_id
from .behaviours.effects import AddEffect
from .behaviours.stats import Heal, healable_heal_type_0
from .behaviours.summon import PerformAIAttack, Spawn
from ...entities.ability_variable_type import AbilityVariableType   # #270-r1-r1-r3
# `GetNumberConstant(<idx>)` lit `AbilityConstantType`, jamais `AbilityVariableType` -- les deux
# enums partagent des ordinaux (`47` = `nrOfHits` des DEUX cotes ici, mais `22` = `range` /
# `blockDmg_2`), donc seul le NOM discrimine.
from ...entities.ability_constant_type import AbilityConstantType
# #270-r4 : groupType de DSLBehaviors.Group, type DECLARE lu dans rida/methods.tsv.
from ...streams.group_type import GroupType
from .loki.splash import _pick_randomly_n

if TYPE_CHECKING:
    from ..state import State

ABILITY_ID = "RevitalizingMalignancy"


def _heal_amounts(state: "State", caster_id: int) -> tuple[int, int]:
    """(regular, chaos) — mirror des lectures de `IdunBattleLogic.Entities.Abilities.Active.Loki.RevitalizingMalignancyAbility$$ExecuteBehaviour` :
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
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.RevitalizingMalignancyAbility$$ExecuteBehaviour` (MIRROR 1:1 du decompile +
    callback `b__0 IdunBattleLogic.Entities.Abilities.Active.Loki.RevitalizingMalignancyAbility.u003Cu003Ec__DisplayClass2_0$$u003CExecuteBehaviouru003Eb__0`). `AllHealTargets` = self + allies adjacents (hex 1) NON-Imperial, filtre
    `Healable` porte cote mutation (`Heal(guard=healable_heal_type_0)`). Split par trait Chaos(0x7ea) :
    non-Chaos = `regular_amount` (var0x20), Chaos = `chaos_amount` (var0x20+var0x22). `AtomicGroup`
    (`ExecuteAtomic`, id 0x1f) inline (RE #201). Ordre callback natif : Heal(regular) PUIS Heal(chaos) ;
    les deux feuilles sont pures (aucun rng) et les sets DISJOINTS -> ordre sans effet observable."""
    # #585-r1 -- les littéraux `selectionType` sont LUS, un par un, sur DEUX fonctions natives :
    #   `...RevitalizingMalignancyAbility$$GetAllHealTargets` :
    #       AdjacentUnits(gs, gs@0x58, unique: 1, 3) ; Friends(gs, gs@0x30, ., 3) ;
    #       UnitsWithoutTrait(gs, ., 0x1a Imperial, 3)
    #   `...RevitalizingMalignancyAbility$$ExecuteBehaviour` :
    #       UnitsWithoutTrait(gs, ., 0x7ea Chaos, 3) ; UnitsWithTrait(gs, ., 0x7ea, 3)
    # ⚠ Le `AdjacentUnits` du port (classe de `entities/selectors/units.py`, mirror de
    # `IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits(target, radius, mask)`) ne porte PAS encore le parametre -- son
    # `mask` natif vaut ici 3 aussi, mais l'ETAGE MANQUE. Sans consequence sur CE site : le
    # `Friends` qui l'enveloppe filtre la sortie. Residu note dans `case-585r1-releve-des-litteraux.md`.
    all_heal = UnitsWithoutTrait(
        Union(Friends(AdjacentUnits(CasterTile(), Const(1)), selection_type=SELECTION), Caster()),
        int(UnitTrait.Imperial), selection_type=SELECTION)     # WithoutTrait(0x1a, Union(Friends(AdjacentUnits(self,1)), self))
    regular_sel = UnitsWithoutTrait(all_heal, int(UnitTrait.Chaos),
                                    selection_type=SELECTION)  # regular = WithoutTrait(0x7ea)
    chaos_sel = UnitsWithTrait(all_heal, int(UnitTrait.Chaos),
                               selection_type=SELECTION)       # chaos   = WithTrait(0x7ea)
    regular = Heal(regular_sel, lambda entities, ectx: regular_amount, guard=healable_heal_type_0)  # Direct(var0x20)
    chaos = Heal(chaos_sel, lambda entities, ectx: chaos_amount, guard=healable_heal_type_0)        # Direct(var0x22+var0x20)
    return AtomicGroup(op_add(regular, chaos))                # ExecuteAtomic( regular + chaos )


class RevitalizingMalignancyAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RevitalizingMalignancyAbility$$ExecuteBehaviour` (id 1037, deathRotbone — Death Guard).

    Heal-splitte-par-trait (jumeau Chaos de 1002 CombatRestoratives) : soigne le caster + ses allies
    adjacents (hex 1) NON-Imperial. Le montant depend du trait Chaos de la cible :
      - allie NON-Chaos : `hpToHeal[level]`                      (var0x20)
      - allie Chaos     : `hpToHeal[level] + hpToHeal_2[level]`  (var0x22 + var0x20, CUMUL)
    Garde `Healable` (HP<max ET non-mechanical) portee cote mutation (feuille `Heal(guard=...)`). Behaviour
    = arbre DSL `revitalizing_malignancy_tree` (mirror 1:1 du decompile + callback `b__0 IdunBattleLogic.Entities.Abilities.Active.Loki.RevitalizingMalignancyAbility.u003Cu003Ec__DisplayClass2_0$$u003CExecuteBehaviouru003Eb__0`).
    Deterministe (aucun rng)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.RevitalizingMalignancy)  # 1037
    ABILITY_ID = ABILITY_ID

    # `IdunBattleLogic.Entities.Abilities.Active.Loki.RevitalizingMalignancyAbility$$.ctor` --
    # forme FLAGS DIRECTS (la 1re des trois) : le ctor recopie les 0x18 octets du `TargetingRange`
    # STATIQUE `statics+0x30` puis appelle
    #     TargetingOptions..ctor(&opts, isSelfCasting=1, &range, forceMeleeTarget=1, 0x8500, 0,0,0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)          # 3e arg = 2 = AbilityAttackType.Others
    # Le litteral EST le masque (aucun preset, aucune combinaison).
    #
    # Decomposition de 0x8500 -- EXHAUSTIVE, aucun bit residuel (0x100+0x400+0x8000 = 0x8500) :
    #   bit  8  0x100   TargetIsHealable            NON PORTEE (cf. inventaire de targeting.py)
    #   bit 10  0x400   TargetIsFriendly            PORTEE -> refuse tout ENNEMI
    #   bit 15  0x8000  CasterIsPossibleTarget      flag DECLARATIF, jamais une regle de refus
    #
    # `range` = `TargetingRange statics+0x30` (`TargetingRange$$.cctor` : les 8 premiers octets a 0
    # -> onlyAdjacent = 0 = RangedBool.True, useRangeFromConfig/useWholeBoard = false ; `+0x38` =
    # Nullable(1)) = RANGE_ADJACENT -> le volet portee prend la branche `AreEntitiesAdjacent`.
    # `forceMeleeTarget` = 1 = RANGED_BOOL_FALSE (l'enum natif est INVERSE : True=0, False=1).
    # `isSelfCasting = 1` -> l'aiguillage SELF-CAST de l'overload 5 arguments de
    # `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` branche sur
    # `TargetingQuery$$GetCasterNotAddedReason` des que la cible EST le caster (non portee -> 0).
    TARGETING_OPTIONS = TargetingOptions(
        rules=(TR.TargetIsHealable | TR.TargetIsFriendly | TR.CasterIsPossibleTarget),
        self_cast=True, range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

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
    """Arbre de `FlailSwingAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.FlailSwingAbility$$ExecuteBehaviour` (id 1042, deathBlightlord — MIRROR du
    DECOMPILE) :
        Execute( op_BitwiseAnd(
            InformWeapon(GetDamageProfile=Power, 1),                                        # metadata arme
            AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                                   GetDamageProfile=Power, nrOfHits=GetNumberConstant(0x2f)=3,
                                   source=AbilityOrEffect(FlailSwing),
                                   alwaysOverkilled=Nullable(true)) ) )

    Port : `op_and( InformWeapon("Power"), AttackWithAttackDamage(Target(), "FlailSwing", "Power", melee) )`
    -- plain `Execute` (PAS `ExecuteAtomic` : le decompile passe l'`op_BitwiseAnd` DIRECTEMENT a
    `AActiveAbility.Execute`, aucun AtomicGroup autour -- contraste BringerOfDespair IdunBattleLogic.Entities.Abilities.Active.Loki.BringerOfDespairAbility$$ExecuteBehaviour). Details RE :

    - `nrOfHits` = `GetNumberConstant(config, 0x2f)` = 3 (config FlailSwing `constants.nrOfHits`="3", verifie
      gameconfig). `MinMaxDamage(param_1, ...)` @... = bornes `minDmg`(0xc)/`maxDmg`(0xd)[level] brutes de la
      config (aucun `GetAttackDamage` surcharge -> pas de `damage_override`). Profil `GetDamageProfile(config,0)`
      = `Power` (`constants.damageProfile`="Power" ; melee, PiercingRatio 40). `attackRangeType=Melee` ->
      `is_melee=True`.
    - **native_factory = "attack"** (defaut, 2 tirages/coup a cc=0) : le decompile appelle litteralement
      `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (famille attack, VERIFIE par la CALLEE de IdunBattleLogic.Entities.Abilities.Active.Loki.FlailSwingAbility$$ExecuteBehaviour =
      symbole `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`, JAMAIS `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` ; tip #2 /
      rngcrit-1202). Attaque MULTI-COUPS (3x) -> classification par XREF OBLIGATOIRE, faite ici.
    - `InformWeapon` = `op_BitwiseAnd` volet GAUCHE (execute EN PREMIER) : canal weapon-inform (TAGS DE
      FLUX, `InformBehaviour`) COMBAT-INERTE (0 RNG, 0 mutation PV/stat) -> n'altere PAS l'ordre `state.rng`
      de l'attaque : bit-exact BY CONSTRUCTION. Le trigger consommateur (`HazeOfCorruption`) est un passif
      SEPARE (hors face COMBAT) -- le declenchement Haze n'est PAS dans cet ExecuteBehaviour.
      Le decompile passe `isMelee: 1` (2e argument, `CONCAT71(..., 1)`) et `useSpecial: 0` -> le tag
      `TagKey.Attack_Weapon_IsMelee` vaut **1** et `..._Use_Special` est ABSENT. Porte litteralement
      (`is_melee=True`) ; il CONCORDE avec l'`attackRangeType=Melee` de l'attaque, mais il est LU, pas deduit.
    - **`alwaysOverkilled` (Nullable=true) PORTE via `force_overkill=True`** : le 8e arg de
      `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (`&local_198` = `Nullable<bool>` HasValue=1, cf. `local_1e8=0x100000000`
      + `System.Nullable<...>.ctor`) = flag « always overkilled » passe a `AttackDamageBehaviour` puis a l'etage
      `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage` (`overkill=true` bypasse le cap Resilient
      `IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit`). La feuille passe `force_overkill=True` -> `_run_hits` force
      `overkill=True` a chaque coup. VALIDE LIVE (deathBlightlord vs custoKyrus Resilient HP 10000 : live tue
      [5070,4555,375] sum=10000 == PV full ; le port SANS le flag laissait 1 PV [5070,4555,374] sum=9999 -> le
      flag est le seul ecart). No-op sur cible non-Resilient -> coeur 3x Power bit-exact partout."""
    return op_and(InformWeapon("Power", is_melee=True),   # `InformWeapon(profile, isMelee: 1, useSpecial: 0)`
                  AttackWithAttackDamage(Target(), "FlailSwing", "Power", is_melee=True, force_overkill=True))


class FlailSwingAbility(ActiveAbility):
    """`FlailSwingAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.FlailSwingAbility$$ExecuteBehaviour` (id 1042, deathBlightlord — Death Guard/Chaos, namespace
    natif `Abilities.Active.Loki`). Arbre DSL `flail_swing_tree()` (MIRROR 1:1 du decompile) :
        Execute( op_BitwiseAnd(
            InformWeapon(Power, isMelee: 1, useSpecial: 0),                          # tags de flux (inerte combat)
            AttackWithAttackDamage(caster, target, MinMaxDamage, Power, nrOfHits=3, alwaysOverkilled=1) ) )

    Attaque MELEE MONO-CIBLE : 3 coups Power (PiercingRatio 40) sur la cible du message. PAS de splash, PAS de
    move/gate, PAS de trigger interne. La feuille `AttackWithAttackDamage` (native_factory="attack", VERIFIE
    par XREF de IdunBattleLogic.Entities.Abilities.Active.Loki.FlailSwingAbility$$ExecuteBehaviour) emet la MEME Operation que l'attaque generique (`AttackDamageOperation.
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

    # `IdunBattleLogic.Entities.Abilities.Active.Loki.FlailSwingAbility$$.ctor` -- forme PRESET
    # STATIQUE COPIE (la 3e des trois) : il n'appelle AUCUN
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor`. Il recopie les 0x40 octets du champ
    # STATIQUE `TargetingOptions statics+0x40` (`lVar1 + 0x40 .. +0x7c`) puis
    #     AActiveAbility..ctor(this, &opts, 0, 0)     # 3e arg = 0 = DirectTargetAttack
    # Le masque effectif est donc la constante ecrite par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` = `*(statics+0x68)` :
    #
    #   bit 14  0x4000  TargetIsEnemy   PORTEE (`UnitsCanAttackEachOther`) -- refuse allie ET soi
    #
    # 0x4000 : un seul bit, la somme est exacte.
    #
    # Le meme preset lu EN ENTIER dans le cctor (`lVar4+0x40..0x7f`) :
    #   isSelfCasting  <preset>+0x00 = statics+0x40 -> 0
    #   range          <preset>+0x08 = statics+0x48 -> copie de `TargetingRange statics+0x30`
    #                                                  = RANGE_ADJACENT
    #   forceMeleeTarget <preset>+0x20 = statics+0x60 -> 1 = RANGED_BOOL_FALSE
    #   rules          <preset>+0x28 = statics+0x68 -> 0x4000
    #   les 2 regles-deleguees +0x30/+0x38 -> 0 (ecrasees par `AActiveAbility$$.ctor`)
    #
    # C'est le MEME preset que 1043 ThunderousAssault (case-246) -- mais 1043 le passe a la
    # surcharge PRESET + FLAGS, qui OR-e `0x10000000`, la ou 1042 le prend TEL QUEL. Deux abilities,
    # meme preset, masques differents : le preset ne suffit jamais, il faut lire QUELLE forme.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetIsEnemy, self_cast=False,
        range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

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


# ============ SpawnPoxwalkers (deathBlightbringer `Typhus`... `Blightbringer`, actif 1040) ============
#                                              case-220 P0-SUMMON
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE) :
#     minPct = GetVariableForLevel(config, 0x3a, level)                        # "chance"
#     maxPct = GetVariableForLevel(config, 0x3b, level)                        # "chance_2"
#     unitId = GetStringConstant(config, 0)                                    # deathPoxwalker
#     range  = ContagionsOfNurgle_ArmorReduction_Effect.CalculateRange(<owner>) # IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect$$CalculateRange
#     tiles  = CanAddUnit(SurroundingTiles(owner@0x148, 0, range))
#     cnt    = <tiles>.Count(entities)                                          # EAGER (vslot +0x2b8)
#     amount = Divide(RandomAmount(cnt*minPct, cnt*maxPct), Get(100), mode=1=Ceiling)
#     picked = PickRandomly(tiles, amount, 0, 0x7fffffff, false)
#     opts   = SpawnUnitOptions.WithStatsFromConfig(config, level)
#     opts.+0x18 = PerformAIAttackFromCurrentPosition(activeTarget@0x180, 0, 0, false)
#     AActiveAbility.Execute(this, Spawn(owner@0x148, picked, unitId, opts), entities)
# UN SEUL `Execute` top-level. AUCUN `PerformAIAction` : l'on-appearance est un `PerformAIAttack`
# (routine IA mono-unite depuis la position courante), PAS un tour d'IA complet.
# SELF-CAST (`SpawnPoxwalkersPlaybook IdunBattle.AI.Playbook.Loki.SpawnPoxwalkersPlaybook$$EvaluateNonComparable` : cible eligible = SOI) -> owner@0x148 == caster.
VAR_POX_CHANCE = AbilityVariableType.chance       # GetVariableForLevel(0x3a) -> "chance"   (% mini de Poxwalker par tuile libre)
VAR_POX_CHANCE_2 = AbilityVariableType.chance_2     # GetVariableForLevel(0x3b) -> "chance_2" (% maxi)
CONST_POX_UNIT_ID = 0x00    # GetStringConstant(0)      -> "unitId"   = deathPoxwalker


def contagions_of_nurgle_range_for_turns(turns_started: int) -> int:
    """La TABLE de rayon de l'aura Contagion, isolee du canal qui lit le compteur.

    Le natif l'ecrit DEUX FOIS, a l'identique, sous deux formes :
      * imperative -- `IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect$$CalculateRange(unit)`
        = `s = UnitExtensions.GetStat(unit, 0xc=TurnsStarted, Current) ; s > 2 ? (s > 4 ? 3 : 2) : 1` ;
      * DSL -- `IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect$$GetRangeOnOwnerTurn(numRounds)`
        = `ConditionalAmount( Not(AmountIsGreater(numRounds, Direct(2))), Direct(1),
             ConditionalAmount( Not(AmountIsGreater(numRounds, Direct(4))), Direct(2), Direct(3) ) )`
        (lu au decompile : les trois `Direct` 1/2/3 et les deux seuils 2/4 y sont litteraux).
    -> rayon 1 aux tours 1-2, 2 aux tours 3-4, 3 a partir du tour 5.

    Le FOYER est ici pour que les deux consommateurs du port partagent la meme table :
    `contagions_of_nurgle_range` (voie imperative, `SpawnPoxwalkersAbility` + pose de l'aura) et le
    noeud DSL `ContagionsOfNurgleRange` (voie formule, `CursedPlagueBellMovementAbility`), qui lit
    lui-meme son `numRounds` par `StatAmount(Owner, TurnsStarted, Current)` comme
    `...$$GetCurrentRange`."""
    s = int(turns_started)
    if s > 2:
        return 3 if s > 4 else 2
    return 1


def contagions_of_nurgle_range(state: "State", unit_id: int) -> int:
    """`IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect$$CalculateRange` -- MIRROR 1:1
    (lecture `GetStat(unit, 0xc=TurnsStarted, Current)` + table `contagions_of_nurgle_range_for_turns`).
    Le natif appelle cette methode STATIQUEMENT depuis
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$ExecuteBehaviour` (l'ability
    n'a pas d'effet Nurgle a ce point : c'est un helper de portee PARTAGE avec l'aura
    ContagionsOfNurgle)."""
    e = state.get_entity(unit_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    stats = getattr(sc.ctx, "stats", None) if sc is not None else None
    s = int(stats.get_stat(int(StatType.TURNS_STARTED), 0)) if stats is not None else 0
    return contagions_of_nurgle_range_for_turns(s)


# ====== CursedPlagueBell — le PREDICAT d'aura (deathBlightbringer `Corrodius`, triggered 1071) ======
#                                              case-224 item 4
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility$$CreateTrigger`
# (MIRROR du decompile ; slots de `IdunBattleLogic.Entities.DSLSelectors` du build `rnca9r7q6c` --
# `+0x30 Owner · +0x40 Actor · +0x48 Caster · +0x60 Target · +0x68 ActiveTarget/Subject`, mapping
# ETABLI par recoupement sur `Lakrimae_SummonPoxwalker_Ability$$CreateTrigger`, pas devine) :
#
#     On(9 = EventTriggerType.Attack, ownerNeedsToBeAlive = 0)
#   & ( OwnerIsTarget  |  OwnerIsAlive<DSLTriggers+0x20>  )
#   & NOT CasterIsTarget
#   & CurrentAttackDamageProfilesContain(0xd = Psychic)
#   & AreEnemies(Actor@0x40, Owner@0x30)
#   & HasTrait(Actor@0x40, 0x3ea = UnitTrait.Psyker)
#   & IsInContagionsOfNurgleRange                        <-- CE predicat (inline dans CreateTrigger)
#   & NOT CurrentAbilityIs(this)
#
# `<DSLTriggers+0x20>` est NOMME depuis case-224 item 5 : c'est le conjoint « OWNER VIVANT », lu au
# decompile de `IdunBattleLogic.Entities.DSLTriggers$$On(triggerType, ownerNeedsToBeAlive)`, qui
# choisit litteralement le slot `+0x20` quand le drapeau est VRAI et le slot `+0x70` (trigger neutre)
# sinon. Recoupement : `DSLTriggers$$InitializeShared` construit `+0x20` avec le seul `state` (ce dont
# `IdunBattle.Entities.Triggers.OwnerIsAliveAbilityTrigger$$ShouldTrigger` a besoin : `IsUnit(owner)
# ? UnitExtensions.IsAlive(owner, state) : true`) et `+0x70` SANS argument. Ce `CreateTrigger`-ci
# passe `ownerNeedsToBeAlive = 0` a `On(9)` et remet le conjoint en OU avec `OwnerIsTarget`.
#
# `...CursedPlagueBellAttackAbility$$IsInContagionsOfNurgleRange` est une PROPRIETE de la classe dont
# le corps compile est EXACTEMENT `DSLTriggers.IsInUnitContagionsOfNurgleAura(Actor@0x40, Owner@0x30)`
# (le compilateur l'INLINE dans `CreateTrigger`, d'ou les deux xrefs de la propriete qui ne sont que
# des entrees de table de methodes). C'est donc un **NOEUD DSL** (kind T), PAS un helper imperatif :
# le port le construit comme un arbre, il ne recable rien a la main.
#
# `IdunBattleLogic.Entities.DSLTriggers$$IsInUnitContagionsOfNurgleAura(target, unit)` =
#     AmountIsEqualOrGreater( ContagionsOfNurgleRange(unit, unitSelectionType=0, isNextTurn=false),
#                             MinDistance(target, unit) )               # INCLUSIF : dist <= range
# -> `entities/triggers.py::IsInUnitAura` au-dessus de `entities/formulas.py::AuraEffectRange` +
# `MinDistance`. ⚠ Le comparateur ne se lit PAS sur le NOM du `.ctor` (`AmountIsGreater...` : corps
# TRIVIAL DEDUPLIQUE par IL2CPP, un seul proprietaire dans la table) mais sur le POINTEUR DE CLASSE
# charge juste avant `il2cpp_object_new` -- c'est celui d'`AmountIsEqualOrGreaterAbilityTrigger`
# (#293 ; re-derivation : `python scripts/python/probe_293_aura_predicate_comparator.py`).
#
# SUR QUOI PORTE LA « RANGE » (la question qui change la forme du port) : sur l'UNITE `Owner@0x30`,
# c'est-a-dire le porteur de la cloche. Pas une entite-effet posee, pas un ensemble de tuiles.
# `AuraEffectRangeFormula` lit la **DEFINITION** de l'effet 1071 dans l'`EffectsDatabase`, verifie
# `HasTrait(owner, 0x7eb = ContagionsOfNurgle)` et evalue `GetCurrentRange()` SUR l'owner
# (= `GetRangeOnOwnerTurn(TurnsStarted(owner))` = 1/2/3). Detail : `entities/effects/aura.py`.

CONTAGIONS_OF_NURGLE_AURA = int(EffectType.ContagionsOfNurgle_ArmorReduction1)    # 0x42f = 1071


def is_in_contagions_of_nurgle_range() -> IsInUnitAura:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility$$
    IsInContagionsOfNurgleRange` — MIRROR 1:1 : `IsInUnitContagionsOfNurgleAura(Actor@0x40,
    Owner@0x30)`, un unique noeud DSL.

    `Owner@0x30` est rendu par `Caster()` : le port ne materialise pas de selecteur `Owner` distinct
    (`ctx.owner` retombe sur `ctx.caster`, hypothese Owner==Caster deja actee pour les triggered, cf.
    `entities/selectors/accessors.py::OwnerTile` et `triggers.OwnerIsTarget`). `Actor@0x40` = l'ACTEUR
    de l'evenement declencheur = `Actor()` (`ctx.actor`).

    Verdict de portee (INCLUSIF `dist <= range`) : un attaquant ADJACENT (dist 1) est DEJA dans
    l'aura des `TurnsStarted(owner) <= 2` (range 1). Le rayon effectif est le MEME que celui de la
    version d'EQUIPE (`BattleQuery$$GetInRangeAuraAmount`, cf.
    `battle_query.get_in_range_aura_amount`) -- les deux etages de portee sont deja le MEME code,
    et les deux comparateurs sont inclusifs (#293).

    L'ability 1071 elle-meme (`CreateBehaviour` : `AttackWithAttackDamage` Psychic) est portee par
    `runner/operations/triggers/loki/cursed_plague_bell.CursedPlagueBellAttackAbility` (case-224
    item 5), qui est le PREMIER consommateur MOTEUR de ce predicat ; cf.
    `docs/rl/case-224-is-in-contagions-of-nurgle-range.md` et
    `docs/rl/case-224-cursed-plague-bell-attack.md`."""
    return IsInUnitAura(Actor(), CONTAGIONS_OF_NURGLE_AURA, Caster())


def cursed_plague_bell_damage_profile() -> str:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility$$GetDamageProfile`
    = `AbilityConfiguration.GetAffectedDamageProfile().GetValueOrDefault(0xd)` (litteral lu au
    decompile ; `DamageProfileType(13) = Psychic`).

    `IdunBattle.Configuration.AbilityConfiguration$$GetAffectedDamageProfile` = la constante d'ability
    `affectedDamageProfile` (`GetEnumConstant`), qui vaut `"Psychic"` pour `CursedPlagueBell` au
    gameconfig courant. On la RELIT plutot que de figer `Psychic` : le natif la relit aussi, et le
    defaut ne s'applique que si la constante disparait.

    FOYER UNIQUE (anti-fork `check-own-port`) : le natif n'a qu'UN `GetDamageProfile` pour DEUX
    consommateurs, et le port doit faire pareil --
      * face DECISION : `playbook/adjacent_unit_preference.CursedPlagueBellPlaybook.
        get_adjacent_enemy_utility` (le predicat `b__4_0` compare l'arme du voisin a CE profil) ;
      * face COMBAT : `CursedPlagueBellAttackAbility$$CreateBehaviour`, qui passe le MEME appel comme
        `damageProfile` de son `AttackWithAttackDamage` (case-224 item 5).
    La fonction vit cote `runner/` parce que la dependance etablie du depot va playbook -> runner."""
    import gameconfig as GC
    consts = ((GC.ability("CursedPlagueBell") or {}).get("constants")) or {}
    return consts.get("affectedDamageProfile") or "Psychic"     # DamageProfileType.Psychic (0xd)


def poxwalkers_spawn_tiles(state: "State", caster_id: int, radius: int) -> list:
    """`CanAddUnit(SurroundingTiles(owner@0x148, includeCenter=0, range))` : tuiles LIBRES et marchables du
    disque hex de rayon `range` autour du caster (centre exclu -- il est occupe par le caster de toute
    facon). Ordre `hexgeo.disk` deterministe."""
    board = state.board
    ce = state.get_entity(caster_id)
    cpc = ce.get_component(PositionComponent) if ce is not None else None
    if board is None or cpc is None:
        return []
    occ = set()
    for e in state.entities.values():
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if pc is None or (uc is not None and not uc.alive):
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None:
            occ.add(t)
    out = []
    for (col, row) in hexgeo.disk(cpc.col, cpc.row, int(radius)):
        if (col, row) == (cpc.col, cpc.row):
            continue
        t = board.id_at(col, row)
        if t is not None and t not in occ and board.walkable(t):
            out.append(t)
    return out


def poxwalkers_count(state: "State", caster_id: int, nb_tiles: int) -> int:
    """`Divide( RandomAmount(cnt*GetVariableForLevel(0x3a), cnt*GetVariableForLevel(0x3b)),
                Get(100), mode=1=Ceiling )` IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$ExecuteBehaviour -- MIRROR.

    `cnt` = nombre de tuiles libres, evalue EAGER par le natif (appel virtuel `+0x2b8` du selecteur
    `CanAddUnit` AVANT la construction du noeud). `chance`/`chance_2` sont des POURCENTAGES par tuile
    (15..20 / 25..45 selon le niveau) -> le tirage porte sur `cnt*minPct .. cnt*maxPct` puis est divise
    par 100 avec arrondi **Ceiling** (`DivideAmount` mode 1, cf. `formulas.Divide`).

    `IdunBattle.Entities.Formulas.RandomAmount$$Calculate` = `rng.<slot 2>(min, max + 1)` -> borne haute INCLUSE ; le port
    consomme `state.rng.next_internal(min, max+1)` (meme primitive que `_pick_randomly`). `state.rng`
    non cale -> on retombe sur la borne BASSE (deterministe, documente). Le cout du `PickRandomly` aval,
    lui, est desormais EXACT (`min(len(pool), n)` tirages, cf. `_pick_randomly_n` -- #130)."""
    from math import ceil
    sc = state.get_entity(caster_id).get_component(StatsComponent)
    cctx = sc.ctx if sc is not None else None
    level = getattr(cctx, "active_ability_level", None)
    mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
    lo = int(ability_var("Poxwalkers", "chance", level, multiplier_pct=mult) or 0) * int(nb_tiles)
    hi = int(ability_var("Poxwalkers", "chance_2", level, multiplier_pct=mult) or 0) * int(nb_tiles)
    if hi < lo:
        hi = lo
    raw = lo if state.rng is None else state.rng.next_internal(lo, hi + 1)   # max INCLUS (IdunBattle.Entities.Formulas.RandomAmount$$Calculate)
    return int(ceil(raw / 100))                                              # Divide(..., 100, Ceiling)


# ===================== EntropyCannons (deathCrawler, MACHINE OF WAR, actif 1168) =====================
#
# Porteur : `deathCrawler` « Plagueburst Crawler » = MACHINE OF WAR (pool `--list-pool`, 8 MoW) ->
# entite ECS hors-plateau (ni Position ni Health), chargee par `_load_machines` (case-mow-offboard-cast).
#
# CIBLAGE (face DECISION/eligibilite, HORS `ExecuteBehaviour`) — `EntropyCannonsAbility.
# IdunBattleLogic.Entities.Abilities.Active.EntropyCannonsAbility$$GetDynamicInvalidTargetReason`, MIRROR du decompile :
#     if !EntityExtensions.IsUnit(target) -> reason 0 (pas d'objection)
#     aura = IdunBattleLogic.Entities.DSLTriggers$$IsInTeamContagionsOfNurgleAura(target@0x178, caster@0x160)
#            -> `IsInAuraRangeTrigger(effectType=0x42f=1071 ContagionsOfNurgle_ArmorReduction1,
#                                     unit=target, teamReference=caster)`
#     armor = IdunBattleLogic.Entities.DSLTriggers$$HasNegativeModifier(target@0x178, 0x10=FixedArmor)
#            -> `IdunBattle.Entities.Triggers.HasNegativeModifier$$ShouldTrigger` = il existe une modification
#               PER-SOURCE < 0 sur le StatType du filtre (array a 1 element = {16 FixedArmor})
#     comp = <StatComponent de la cible>            # lu par dispatch d'interface, gate `comp+0x48 > 0`
#     return (aura ? 0 : ((comp+0x48 > 0 && armor) ? 0 : 2))
# => la cible n'est LEGALE que si elle est (a) dans une aura Contagion d'un allie du CASTER, OU
#    (b) porteuse d'une modification NEGATIVE de FixedArmor (« Armour reduced » de l'i2).
# C'est CE predicat qui rend « 0 cible au spawn » (sweep case-mow §5) : il faut le MONTER (reducteur
# d'armure sur la cible, ou allie Death Guard porteur de Contagion) pour obtenir une cible.
# Le port n'a PAS de face DECISION pour les MoW (le natif ne met que `EntityType.Unit` dans
# `decisionView.units` -> les MoW en sont EXCLUES, case-mow §4) : le predicat est donc RE + documente
# ici et exerce LIVE (`abilityTargets`), pas re-porte offline en code mort. Son homologue OFFLINE
# existe deja pour la branche (b) : `UnitStats.has_negative_modifier({16})` (mirror IdunBattle.Entities.Triggers.HasNegativeModifier$$ShouldTrigger).

ENTROPY_CANNONS_ID = "EntropyCannons"


def entropy_cannons_tree() -> AttackWithAttackDamage:
    """Arbre de `EntropyCannonsAbility$$IdunBattleLogic.Entities.Abilities.Active.EntropyCannonsAbility$$ExecuteBehaviour` (id 1168, deathCrawler MoW) —
    MIRROR du DECOMPILE (UN seul noeud, passe directement a `AActiveAbility.Execute`) :

        Execute( AttackWithAbilityDamage( caster@0x160, target@0x178,
                                          MinMaxDamage(this, entities),                # minDmg/maxDmg[level]
                                          Nullable(GetDamageProfile(this))=Energy,
                                          GetHits(this)=ConfigConst(0x2f)=nrOfHits=2,
                                          AbilityOrEffect(this+0x10 = 0x490 = 1168) ) )

    - **native_factory = "ability"** : le decompile appelle litteralement `DSLFactory.
      IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` (overload core IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage), PAS `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` -> `AbilityDamageBehaviour` -> `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHits` :
      1 tirage/coup, AUCUN crit, AUCUNE feuille positionnelle (elevation/trench) — MEME route que
      Stormcaller/SpiritLeech (classification par XREF, jamais au juge).
    - `MinMaxDamage` = bornes `minDmg`(0xc)/`maxDmg`(0xd)[activeAbilityLevel] scalees par
      `AbilityVariablesMultiplier` ; pour une MoW le couple {level, mult} vient de son `AbilityState`
      PER-ABILITY (`_load_machine_stats`), seul canal de niveau d'une Machine.
    - Profil `Energy` (`constants.damageProfile`, PiercingRatio 30) ; `nrOfHits`=2 (constante config).
    - `is_melee=None` : la config 1168 n'a **PAS** d'`attackRangeType` (contraste 1147/1200 = `Ranged`)
      -> nature du coup NON declaree -> convention `execute_ability_attack(is_melee=None)` = gates
      defenseur melee/ranged INERTES (`Terrifying_ExtraDefense` IsMeleeAttack, ...). Ne rien inventer.
    - AUCUN effet pose, AUCUN spawn, AUCUNE 2e phase : l'ability EST cette seule attaque (le volet
      « armure reduite / Contagion » de l'i2 est le PREDICAT DE CIBLAGE ci-dessus, pas un volet degat)."""
    return AttackWithAttackDamage(Target(), ENTROPY_CANNONS_ID, "Energy", is_melee=None,
                                  native_factory="ability",          # IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage (XREF), 1 tirage/coup
                                  ability_type=int(ActiveAbilityType.EntropyCannons))


def entropy_cannons_is_valid_target_trigger() -> TriggerOr:
    """Predicat de CIBLAGE de 1168 -- MIRROR du corps de
    `IdunBattleLogic.Entities.Abilities.Active.EntropyCannonsAbility$$GetDynamicInvalidTargetReason`,
    dont les deux termes sont montes sur les selecteurs memoises du `DSLSelectors` de l'ability :

        aura  = DSLTriggers.IsInTeamContagionsOfNurgleAura(sel+0x60 = Target, sel+0x48 = Caster)
                    .ShouldTrigger(entities, 0x20)
        neg   = DSLTriggers.HasNegativeModifier(sel+0x60 = Target, 0x10 = StatType.FixedArmor)
                    .ShouldTrigger(entities, 0x20)
        comp  = target.GetComponent<FixedArmorComponent>()
        return aura || (comp.<+0x48> > 0 && neg)

    STRUCTURELLEMENT IDENTIQUE a `plagueburst_is_valid_adjacent_enemy_trigger` (meme famille Death
    Guard, meme couple aura/armure), a UN detail pres : le sujet est ici `Target()` (le
    `AbilityEntities+0x178` de la cible evaluee), pas le `Subject()` lie par un `Filter`.

    ⚠ `comp.<+0x48>` EST `StatPart.Initial`, PAS la valeur courante. Lu au decompile, deux fois :
    `IdunBattle.Entities.Components.StatComponent$$GetStatPart` `case 3: return *(uint*)(this+0x48)`,
    et `IdunBattle.Entities.Components.StatComponent$$get_CurrentValue` qui vaut
    `*(this+0x48) + *(this+0x10)` (initial + total des modifications), clampe. Consequence NON
    triviale : une cible dont le FixedArmor a ete reduit A ZERO par un modificateur reste VALIDE --
    c'est l'armure de BASE qui doit etre non nulle. Lire la valeur COURANTE fabriquerait un
    SUR-refus exactement dans le regime que l'ability vise.

    ⚠ Le composant est identifie par la PAIRE de globales du call-site, croisee avec
    `IdunBattle.Entities.UnitExtensions$$GetStatComponent` : `case 0x10` (StatType.FixedArmor) y
    appelle le MEME `GetComponent` generique avec le MEME `FixedArmorComponent.ComponentId`. Ce
    n'est donc pas un composant tiers -- c'est le composant de stat de `FixedArmor`, et le port le
    lit par `StatAmount(., FIXED_ARMOR, INITIAL)` comme son jumeau Plagueburst."""
    aura = IsInTeamAura(Target(), int(EffectType.ContagionsOfNurgle_ArmorReduction1), Caster())
    armor = TriggerAnd(
        HasNegativeModifier(Target(), (int(StatType.FIXED_ARMOR),)),
        AmountIsGreaterThanZero(StatAmount(Target(), int(StatType.FIXED_ARMOR),
                                           int(StatPart.INITIAL))))
    return TriggerOr(aura, armor)


class EntropyCannonsAbility(ActiveAbility):
    """`EntropyCannonsAbility$$IdunBattleLogic.Entities.Abilities.Active.EntropyCannonsAbility$$ExecuteBehaviour` (id 1168, `deathCrawler` « Plagueburst
    Crawler », MACHINE OF WAR Death Guard). Arbre DSL `entropy_cannons_tree()` (mirror 1:1) : 2 coups
    Energy (pierce 30) sur la cible du message, via la famille ABILITY (pas de crit, pas d'elevation).

    Caster = une **MoW hors-plateau** (ni Position ni Health) : les feuilles positionnelles du builder
    de mods attaquant sont de toute facon gatees OFF pour la famille ABILITY (#45f), et `apply_elevation
    _bonus`/`apply_trench_reduction` no-op sans position -> aucun chemin ne suppose une tuile de caster.

    Turn-flags = defauts base (1168 absent des overrides `SetsEndTurnFlags`/`SetsActiveAbilityUsedFlag`).
    Diag : {attacks:[{target,total}]}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.EntropyCannons)   # 1168
    ABILITY_ID = ENTROPY_CANNONS_ID

    # `IdunBattleLogic.Entities.Abilities.Active.EntropyCannonsAbility$$.ctor` -- forme FLAGS
    # DIRECTS : recopie des 0x18 octets du `TargetingRange` STATIQUE `statics+0x48` puis
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, &range, forceMeleeTarget=1, 0x40004002, 0,0,0)
    #     AActiveAbility..ctor(this, &opts, 0, 0)     # 3e arg = 0 = DirectTargetAttack
    #
    # Decomposition de 0x40004002 -- EXHAUSTIVE (0x2 + 0x4000 + 0x40000000, rien ne reste) :
    #   bit  1  0x2          TargetMatchesDynamicRule  point d'extension -> voir ci-dessous
    #   bit 14  0x4000       TargetIsEnemy             PORTEE -> refuse allie ET soi-meme
    #   bit 30  0x40000000   AllowNullCasterTile       ALLOW du volet CASTER, jamais un refus
    #
    # `AllowNullCasterTile` est la signature d'une ability de MACHINE OF WAR : le caster est
    # hors-plateau, il n'a PAS de tuile (cf. `_load_machines`). Ce n'est pas une regle du filtre
    # cible.
    # `range` = `TargetingRange statics+0x48` (`TargetingRange$$.cctor` : `+0x48`=1 -> onlyAdjacent
    # = RangedBool.False, `+0x4c`=0x100 -> l'octet `+0x4d` = useWholeBoard = TRUE) =
    # RANGE_WHOLE_BOARD -> `TargetingQuery$$GetRange` court-circuite, AUCUN test de portee.
    # `forceMeleeTarget` = 1 = RANGED_BOOL_FALSE.
    #
    # `TargetMatchesDynamicRule` : la regle-delegue est
    # `IdunBattleLogic.Entities.Abilities.Active.EntropyCannonsAbility$$GetDynamicInvalidTargetReason`
    # -- elle rend `2` sauf si la cible est sous aura Contagion ALLIEE ou porte une modification
    # NEGATIVE de FixedArmor sur une armure de BASE non nulle. PORTEE depuis #287-r11 (cf. la
    # surcharge ci-dessous) : les DEUX branches etaient portables depuis case-224
    # (`plagueburst_is_valid_adjacent_enemy_trigger`, qui evalue exactement le meme couple), seul le
    # call-site manquait. C'est d'ailleurs CE predicat natif qui sert d'ORACLE LIVE au port de l'aura
    # (`tests/engine/runner/test_contagions_aura_range_live.py`, via `abilityTargets`).
    TARGETING_OPTIONS = TargetingOptions(
        rules=(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy | TR.AllowNullCasterTile),
        self_cast=False, range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)
    # `IdunBattleLogic.Entities.Abilities.Active.EntropyCannonsAbility$$GetTargetingOptionsForContinue`
    # (#429-r1) -- l'un des DEUX seuls overrides du binaire. Forme FLAGS DIRECTS, meme `TargetingRange`
    # statique `+0x48` que le masque principal :
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, &range, forceMeleeTarget=1, 0x40004000, 0, 0)
    # Soit le masque principal MOINS `TargetMatchesDynamicRule` (0x2) : au CONTINUE, la regle
    # dynamique de l'ability n'est plus consultee. N'arme PAS `AllowDeadTarget`
    # -> `can_continue_on_dead_target()` = False (mesure, pas defaut).
    TARGETING_OPTIONS_FOR_CONTINUE = TargetingOptions(
        rules=(TR.TargetIsEnemy | TR.AllowNullCasterTile),
        self_cast=False, range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entropy_cannons_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        attacks = [{"target": p.get("target"), "total": p.get("total")}
                   for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        return {"ability": ENTROPY_CANNONS_ID, "caster": caster_id, "target": target_id,
                "attacks": attacks, "dsl": True}

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.EntropyCannonsAbility$$GetDynamicInvalidTargetReason`
        -- MIRROR du decompile, ligne a ligne (#287-r11) :

            if (!EntityExtensions.IsUnit(target)) return 0;
            entities = new AbilityEntities(caster, caster, target, null, ...);
            ... cf. `entropy_cannons_is_valid_target_trigger` ...
            return (aura || (fixedArmor.Initial > 0 && hasNegativeModifier)) ? 0 : 2;

        `2` = `TargetingRule.TargetMatchesDynamicRule`.

        ⚠ Le 4e argument de l'`AbilityEntities` (`owner`) est **NUL** ici -- contraste avec
        `SquigLaunchas`, qui y passe le caster. C'est sans effet sur CE predicat : les deux
        selecteurs memoises qu'il utilise sont `Target` (`sel+0x60`) et `Caster` (`sel+0x48`),
        jamais `Owner` (`sel+0x30`). L'ecrire evite de croire que le role est libre.

        `IsUnit(target)` : cote port `state.entities` ne contient que des unites/MoW, donc un
        `target_id` qui n'y resout pas n'est pas une unite -> `0`, mirror du garde d'entree natif
        (permissif, pas un refus)."""
        if target_id is None:
            return 0
        ents = entities_from_state(state, int(caster_id), int(target_id))
        if ents.target is None:
            return 0                                   # !EntityExtensions.IsUnit(target) -> 0
        ok = bool(entropy_cannons_is_valid_target_trigger().should_trigger(ents))
        return 0 if ok else int(TR.TargetMatchesDynamicRule)


def spawn_poxwalkers_tree(tiles: list) -> Spawn:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$ExecuteBehaviour` : UN noeud `Spawn` dont les options
    portent le sous-behaviour ON-APPEARANCE `PerformAIAttackFromCurrentPosition(activeTarget@0x180)`
    (`IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAttackFromCurrentPosition` -> `IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute`) = chaque Poxwalker fraichement pose attaque DEPUIS SA POSITION (sans bouger). La feuille
    portee `PerformAIAttack` accepte le domaine UNITE (l'`ActiveTarget` lie par le `Spawn`) aussi bien que
    le domaine TUILE (le `Cache` de GetEmRuntz)."""
    return Spawn(FixedTileIds(tiles), "Poxwalkers", on_appearance=PerformAIAttack(ActiveTarget()))


class SpawnPoxwalkersAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$ExecuteBehaviour` (id 1040, `deathBlightbringer`, DeathGuard).
    SELF-CAST : fait apparaitre `ceil(rand(n*chance, n*chance_2)/100)` Poxwalkers (`deathPoxwalker`) sur
    des tuiles libres du disque de rayon `ContagionsOfNurgle_ArmorReduction_Effect.CalculateRange(caster)`
    (1/2/3 selon `TurnsStarted`) autour du caster, puis chacun attaque depuis sa position.

    N'utilise PAS `PerformAIAction` (l'on-appearance est un `PerformAIAttackFromCurrentPosition`).
    Retour : {spawned, attacks, radius, tiles, count, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Poxwalkers)   # 1040
    ABILITY_ID = "Poxwalkers"

    # `IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$.ctor` -- forme FLAGS
    # DIRECTS, mais avec le SEUL `TargetingRange` du registre qui ne soit pas un statique :
    #     func  = new IdunBattle.Core.Services.GetRange(target = NULL, <MethodInfo>)   # STATIQUE
    #     range = IdunBattle.Core.Services.TargetingRange$$CustomRange(func)           # surcharge
    #     TargetingOptions..ctor(&opts, isSelfCasting=1, &range, forceMeleeTarget=1,
    #                            0x8000000004, 0,0,0)
    #     AActiveAbility..ctor(this, &opts, 1, 0)   # 3e arg = 1 = SummonAndAttackTarget
    #
    # Decomposition de 0x8000000004 -- EXHAUSTIVE (0x4 + 0x8000000000, aucun bit residuel) :
    #   bit  2  0x4            CasterMatchesDynamicRule  volet CASTER, NON PORTE (cf. ci-dessous)
    #   bit 39  0x8000000000   TargetIsCaster            PORTEE -> la cible DOIT etre le caster
    #
    # `range` = `CustomRange(GetRange)` (surcharge DELEGUE, mirror `custom_range_func`) :
    # `{onlyAdjacent = RangedBool.False, useRangeFromConfig = false, useWholeBoard = false,
    #   overrideRange = <vide>, overrideRangeFunc = <le delegue>}`. `TargetingQuery$$GetRange`
    # ECRASE la portee par ce delegue -> le port ne sait PAS la calculer -> aucun gate de portee
    # (permissif). RESIDU NOMME : la methode cible du delegue n'est pas resolue (metadata-usage,
    # invisible a ghidra) ; le seul candidat de signature `int(IEntity)` du voisinage est
    # `IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect$$CalculateRange`
    # (que `...SpawnPoxwalkersAbility$$ExecuteBehaviour` ET
    # `...SpawnPoxwalkersAbility$$GetDynamicInvalidCasterReason` appellent tous deux) -- HYPOTHESE
    # NON LUE, donc NON PORTEE. Sans consequence mesurable ici : le volet portee est INATTEIGNABLE
    # pour 1040 (self-cast -> aiguillage `GetCasterNotAddedReason` ; sinon `TargetIsCaster` refuse
    # AVANT la portee dans la cascade).
    #
    # `CasterMatchesDynamicRule` non porte -- la regle-delegue `options+0x30` (slot vtable +0x470)
    # est `IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$GetDynamicInvalidCasterReason`,
    # dont le decompile rend `4` s'il n'existe AUCUNE tuile posable dans le disque
    # `CalculateRange(caster)` autour d'une des tuiles du caster, `0` sinon. Le port ne porte AUCUNE
    # regle-delegue CASTER (`get_invalid_caster_reason` ne porte que `CasterHasNotMoved`) -> le seul
    # ecart possible est PERMISSIF (le port accepte un cast que le natif refuserait faute de place).
    TARGETING_OPTIONS = TargetingOptions(
        rules=(TR.CasterMatchesDynamicRule | TR.TargetIsCaster),
        self_cast=True, range=custom_range_func(), force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if state.get_entity(caster_id) is None:
            return None
        radius = contagions_of_nurgle_range(state, caster_id)
        tiles = poxwalkers_spawn_tiles(state, caster_id, radius)
        n = poxwalkers_count(state, caster_id, len(tiles))
        picked = _pick_randomly_n(state, tiles, n)          # PickRandomly(tiles, amount)
        ectx = ExecutionContext(state=state, rng=state.rng)
        spawn_poxwalkers_tree(picked).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        spawned = [p["unit"] for nm, p in ectx.emitted if nm == "SpawnUnit"]
        attacks = [p for nm, p in ectx.emitted if nm == "PerformAIAttack"]
        return {"spawned": spawned, "attacks": attacks, "radius": radius, "tiles": picked,
                "count": n, "dsl": True}


# ============== PlagueburstMortar (deathCrawler, MACHINE OF WAR, actif 1169) ==============
#                                 case #90 lot B — « attaque filtree par un ETAT »
#
# `IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$ExecuteBehaviour` (MIRROR du
# DECOMPILE ; namespace `Active` SANS `.Loki`, comme EntropyCannons -- meme porteur) :
#
#   adjTiles = AdjacentTiles(target@0x178)                                       # capture AVANT tout
#   pred     = PlagueburstMortarAbility.GetIsValidAdjacentEnemyTrigger           # cf. ci-dessous
#   main     = Filter( Enemies(caster@0x160, target@0x178, 3), pred )
#              (== `IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$GetMainDamageTarget`)
#   adj      = Filter( Enemies(caster@0x160, Units(AdjacentTiles(target@0x178), 1), 3), pred )
#              (== `IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$GetAdjacentDamageTargets`)
#   targets  = Unique( main op_Addition adj )
#   attack   = AttackWithAbilityDamage( caster@0x160, targets, MinMaxDamage(this, entities),
#                                       Nullable(GetDamageProfile())=Toxic, GetHits()=ConfigConst(0x2f)=3,
#                                       AbilityOrEffect(this+0x10 = 0x491 = 1169) )
#   pin      = AddEffect( 0x429 = 1065 Pinned, AbilityStateReference, source=caster@0x160,
#                         targets = <les MEMES `targets`>, options ZERO )
#   n        = Difference( ConfigVar(0x66 = nrOfTiles, entities, config@0x60), factory+0xc0 = Get(1) )
#   tiles    = target@0x178  op_Addition  PickRandomly(adjTiles, n, 0, 0x7fffffff, false)
#   contam   = AddEffect( 0x4dc = 1244 Contaminated, AbilityStateReference,
#                         source = **target@0x178** (PAS le caster), targets = tiles, options ZERO )
#   AActiveAbility.Execute( (attack & pin) & contam, entities )     # Execute PLAIN (pas ExecuteAtomic)
#
# `IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$GetIsValidAdjacentEnemyTrigger`
# (MIRROR) — evalue sur le SUJET (`@0x180`, l'element courant lie par le `Filter`) :
#
#   IsInTeamContagionsOfNurgleAura(subject@0x180, caster@0x160)                       # aura Contagion ALLIEE
#   op_BitwiseOr
#   ( HasNegativeModifier(subject@0x180, 0x10=FixedArmor)
#     op_BitwiseAnd  AmountIsGreaterThanZero(StatAmount(subject@0x180, 0x10, part 3=Initial)) )
#
# = MEME predicat de legalite que `IdunBattleLogic.Entities.Abilities.Active.EntropyCannonsAbility$$GetDynamicInvalidTargetReason`
# (l'autre active du deathCrawler), ici applique COMME FILTRE DE CIBLES au sein du behaviour (donc face
# COMBAT, portee) et non comme gate de ciblage.
#
# NOTE `Difference` : la factory native est `IdunBattleLogic.Entities.DSLFormulas$$Difference(a, b)` = `a - b` ;
# `factory+0xc0` est le noeud constante `Get(1)` (`IdunBattleLogic.Entities.DSLFactory$$.ctor` : +0xb8=Get(0),
# +0xc0=Get(1), +0xc8=Get(2), +0xd0=Get(100), +0xd8=Get(-1)) -> `nrOfTiles - 1` tuiles TIREES, la tuile de la
# cible etant deja dans l'union -> `nrOfTiles` entites contaminees au total.

PLAGUEBURST_MORTAR_ID = "PlagueburstMortar"
CONTAGIONS_OF_NURGLE_ARMOR_REDUCTION1 = int(EffectType.ContagionsOfNurgle_ArmorReduction1)   # 0x42f
PINNED = int(EffectType.Pinned)                                                             # 0x429
CONTAMINATED = int(EffectType.Contaminated)                                                 # 0x4dc


def plagueburst_is_valid_adjacent_enemy_trigger() -> TriggerOr:
    """`IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$GetIsValidAdjacentEnemyTrigger`
    (MIRROR 1:1 du decompile, cf. le bloc ci-dessus). Le sujet est `Subject()` (= `@0x180`, l'element lie
    par le `Filter`), la reference d'equipe de l'aura est `Caster()` (= `@0x160`).

    Les DEUX branches sont desormais actives : la branche AURA a ete portee en case-224
    (`battle_query.get_in_range_aura_amount`, mirror de `BattleQuery$$GetInRangeAuraAmount`, cable au
    contexte DSL par `entities_from_state`) -- avant cela elle etait inerte et le port REFUSAIT des
    cibles que le natif accepte. La branche ARMURE (`HasNegativeModifier` FixedArmor) est inchangee."""
    aura = IsInTeamAura(Subject(), CONTAGIONS_OF_NURGLE_ARMOR_REDUCTION1, Caster())
    armor = TriggerAnd(
        HasNegativeModifier(Subject(), (int(StatType.FIXED_ARMOR),)),
        AmountIsGreaterThanZero(StatAmount(Subject(), int(StatType.FIXED_ARMOR),
                                           int(StatPart.INITIAL))))
    return TriggerOr(aura, armor)


def plagueburst_main_damage_target(target_sel) -> Filter:
    """`IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$GetMainDamageTarget`
    = `Filter( Enemies(caster@0x48, target@0x60, 3), GetIsValidAdjacentEnemyTrigger )` (MIRROR 1:1).

    UN artefact natif, DEUX consommateurs -- d'ou la fonction nommee a part :

      * face COMBAT   -> 1er terme de `plagueburst_damage_targets` (qui l'unit aux adjacents) ;
      * face DECISION -> le `targetsSelector` que
        `IdunBattle.AI.Playbook.PlagueburstMortarPlaybook$$MakeDamagePredictions` passe a
        `...ComparablePlaybook...$$GenerateMultiHitAttackPredictions` -- et c'est le SEUL ensemble
        que la PREDICTION couvre : `GetAdjacentDamageTargets` n'entre PAS dans le batch de
        prediction, alors qu'il entre dans `ExecuteBehaviour`.

    Le `Units(target_sel)` materialise la resolution tuile -> occupant que le natif fait dans
    `IdunBattle.Entities.Selectors.UnitsByTeamSelector$$CountOrAdd` (`GetUnitOrMachine(entity)` pour
    le test d'equipe, `Add(entity)` pour le resultat) : cf. la note de `plagueburst_damage_targets`.
    MESURE (probe #302-2) : le natif rend la MEME utilite de paire qu'on lui passe la TUILE (entite
    de type `Tile`) ou l'UNITE qui l'occupe -- 1.1779941 dans les deux cas sur `orksWarboss` --,
    donc la resolution materialisee est value-identique sur ce chemin."""
    # #585-r1 : `Enemies(gs@0x48, gs@0x60, 3)` -- littéral LU. Le `Units(...)` interne, lui, est la
    # MATERIALISATION documentee ci-dessus : il n'a AUCUN equivalent natif dans cette fonction, donc
    # il ne recoit RIEN (inventer un `selectionType` sur un noeud absent du natif serait pire que
    # l'absence). Le filtre est arme au bon etage -- `Enemies` filtre sa SORTIE.
    return Filter(Enemies(Units(target_sel), selection_type=SELECTION),
                  plagueburst_is_valid_adjacent_enemy_trigger())


def plagueburst_adjacent_damage_targets(target_sel) -> Filter:
    """`IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$GetAdjacentDamageTargets`
    = `Filter( Enemies(caster@0x48, Units(AdjacentTiles(target@0x60), 1), 3),
    GetIsValidAdjacentEnemyTrigger )` (MIRROR 1:1). C'est `plagueburst_adjacent_enemies` AVEC le
    Filter -- la face COMBAT l'utilise, la face DECISION ne l'utilise PAS (cf. ci-dessus)."""
    return Filter(plagueburst_adjacent_enemies(target_sel),
                  plagueburst_is_valid_adjacent_enemy_trigger())


def plagueburst_damage_targets(target_sel) -> Unique:
    """`Unique(GetMainDamageTarget + GetAdjacentDamageTargets)` (MIRROR) : l'occupant de la tuile ciblee
    ET les ennemis des tuiles adjacentes, TOUS filtres par le predicat de validite. Le `Unique` natif
    dedup l'intersection.

    REDUCTION NOTEE : le cast est TILE-TARGET (mesure live `abilityTargets` : `kind="tile"`), donc le
    natif passe une entite-TUILE a `Enemies(caster, target@0x178, 3)` ; son `UnitsByTeamSelector.CountOrAdd`
    resout l'entite par `IdunBattle.Entities.UnitExtensions$$GetUnitOrMachine` (la tuile -> son occupant)
    pour le TEST d'equipe, mais ajoute l'entite BRUTE au resultat. Le port materialise la resolution
    (`Units(target_sel)`) et travaille donc en domaine UNITE de bout en bout : identique pour le volet
    DEGAT, et pour le volet `Pinned` cela pose l'effet sur l'UNITE plutot que sur la TUILE.
    RESIDU EXPLICITE (non discriminable sur un runner frais, ou le predicat vide l'ensemble) : si le
    natif posait `Pinned` sur l'entite-tuile, l'empreinte differerait sur ce point precis."""
    return Unique(Union(plagueburst_main_damage_target(target_sel),
                        plagueburst_adjacent_damage_targets(target_sel)))


def plagueburst_adjacent_enemies(target_sel) -> Enemies:
    """`IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$GetAdjacentEnemies`
    = `Enemies(caster@0x160, Units(AdjacentTiles(target@0x178), unique: 1), 3)` (MIRROR 1:1).

    C'est EXACTEMENT le terme `adj` de `plagueburst_damage_targets` **sans** son
    `Filter(GetIsValidAdjacentEnemyTrigger)` -- un seul artefact natif, deux consommateurs :

      * face COMBAT  -> `plagueburst_damage_targets` (avec le Filter) : QUI encaisse ;
      * face DECISION -> `IdunBattle.AI.Playbook.PlagueburstMortarPlaybook$$CalculateCustomUtility`
        (sans le Filter) : COMBIEN d'ennemis borde la tuile visee.

    Le natif appelle `TargetsSelector.Count(sel, AbilityEntities(owner: caster, caster: caster,
    target: target))` -- l'`AbilityEntities` construit ne porte PAS `casterPosition`, donc ce compte
    est INDEPENDANT de la tuile depuis laquelle le caster tire."""
    # #585-r1 : `Units(gs, AdjacentTiles(target), unique: 1, 3)` puis `Enemies(gs, gs@0x48, ., 3)`
    # -- les DEUX littéraux LUS au decompile de `$$GetAdjacentEnemies`.
    return Enemies(Units(AdjacentTiles(target_sel), selection_type=SELECTION),
                   selection_type=SELECTION)


def plagueburst_nr_of_tiles(state: "State", caster_id: int) -> int:
    """`ConfigVar(0x66 = nrOfTiles)` de 1169, au niveau d'ability ACTIVE du caster et scale par son
    `AbilityVariablesMultiplier` (mirror `ConfigAmount.Calculate` -> `GetVariableForLevel`). Pour une MoW
    le couple {level, mult} vient de son `AbilityState` PER-ABILITY (`_load_machine_stats`)."""
    e = state.get_entity(caster_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    cctx = sc.ctx if sc is not None else None
    level = getattr(cctx, "active_ability_level", None)
    mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
    return int(ability_var(PLAGUEBURST_MORTAR_ID, "nrOfTiles", level, multiplier_pct=mult) or 0)


def plagueburst_target_tile(state: "State", target_id: Optional[int]) -> Optional[int]:
    """Id de la TUILE ciblee : le cast est TILE-TARGET (`TargetIsTile` au masque), mais on accepte
    aussi un id d'UNITE (on prend alors sa MainTile) -- `target@0x178` designe une ENTITE et le natif
    en lit la MainTile partout ou il l'utilise en domaine tuile.

    DELEGUE au foyer `main_tile_id` (#287-r12), qui mirrore
    `IdunBattle.Entities.EntityExtensions$$GetMainTileId`. Ce corps testait la branche TUILE
    D'ABORD ; le natif la teste EN DERNIER, en repli du composant de pied puis de l'unite. L'ordre
    n'est pas academique : les deux espaces d'ids se chevauchent (residu nomme dans
    `operations/active_ability.py`), donc il decide de ce que rend un id ambigu."""
    return main_tile_id(state, target_id)


def plagueburst_contaminated_tiles(state: "State", target_id: int, n_tiles: int) -> list:
    """COLLAPSE imperatif du `PickRandomly(AdjacentTiles(target@0x178), Difference(nrOfTiles, Get(1)),
    0, 0x7fffffff, false)` natif : le tirage vit ICI (seul endroit qui voit `state.rng`), meme patron que
    Poxwalkers/Fragstorm/SquigMine. Rend les ids de tuile TIRES (`nrOfTiles - 1` au plus).

    La CONSO rng du tirage est calee depuis #130 (`min(|pool|, n)` tirages, bornes decroissantes, MEME
    quand le pool tient dans `n` -- cf. `_pick_randomly_n`). ⚠ RESIDU #215 (idem SquigMine) : quand
    `|pool| > n`, l'ordre d'ENUMERATION natif (non trie) decide QUELLES tuiles sont tirees."""
    board = state.board
    tid = plagueburst_target_tile(state, target_id)
    if board is None or tid is None:
        return []
    pool = list(board.neighbours(tid))
    return _pick_randomly_n(state, pool, max(0, int(n_tiles) - 1))


def plagueburst_mortar_tree(target_sel, picked_tiles: list):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$ExecuteBehaviour`
    (MIRROR 1:1) :

        op_BitwiseAnd( op_BitwiseAnd( AttackWithAbilityDamage(<cibles valides>),
                                      AddEffect(Pinned -> <les MEMES cibles>) ),
                       AddEffect(Contaminated -> cible + <tuiles tirees>) )

    - l'attaque route `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` (famille ABILITY :
      1 tirage/coup, pas de crit) -> `native_factory="ability"` ; profil `Toxic`, `nrOfHits`=3.
    - `Pinned` : options natives ZERO -> duree = `DefaultAmountOfRounds(0x429)=1` convertie DANS
      `AddEffectOperation` (`duration_rounds=None` cote port).
    - `Contaminated` : options ZERO aussi (-> `DefaultAmountOfRounds(0x4dc)=2`), et **source = la CIBLE**
      (`target@0x178`, 4e argument natif d'AddEffect) et non le caster -> `source_ref=Target()`.
    - le 1er terme de l'union `Contaminated` est `target@0x178` LUI-MEME = la TUILE ciblee (cast
      tile-target) : la zone contaminee est donc `{tuile ciblee} + <tuiles tirees>`, toutes en domaine
      TUILE. `source_ref = target@0x178` = la MEME entite (4e argument natif d'AddEffect)."""
    targets = plagueburst_damage_targets(target_sel)
    attack = AttackWithAttackDamage(targets, PLAGUEBURST_MORTAR_ID, "Toxic", is_melee=False,
                                    multi=True, native_factory="ability",
                                    ability_type=int(ActiveAbilityType.PlagueburstMortar))
    pin = AddEffect(PINNED, EffectType.Pinned.name, targets, duration_rounds=None)
    contam = AddEffect(CONTAMINATED, EffectType.Contaminated.name,
                       Union(target_sel, FixedTileIds(picked_tiles)),
                       duration_rounds=None, source_ref=target_sel)
    return op_and(op_and(attack, pin), contam)


class PlagueburstMortarAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$ExecuteBehaviour` (id 1169,
    `deathCrawler` « Plagueburst Crawler », MACHINE OF WAR Death Guard) — cf. le bloc de commentaire.

    Kit gameconfig 1169 : `damageProfile=Toxic`, `nrOfHits=3`, `minDmg`/`maxDmg`[level] (rarity-affected),
    `nrOfTiles`[level] (3..7), `initialCooldownTurns=1`. PAS d'`attackRangeType` -> `is_melee=None`
    (gates defenseur melee/ranged INERTES, meme convention qu'EntropyCannons : ne rien inventer).

    OBSERVABLE : (1) 3 coups Toxic + `Pinned` sur les ennemis VALIDES (cible + adjacents de la cible qui
    passent le predicat armure/aura -- ensemble souvent VIDE sur un runner frais, exactement comme le
    « 0 cible au spawn » d'EntropyCannons) ; (2) `Contaminated` sur la CIBLE + `nrOfTiles-1` tuiles tirees
    parmi les adjacentes de la cible -- ce volet, lui, est INCONDITIONNEL.

    Turn-flags = defauts base (1169 absent des overrides)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.PlagueburstMortar)   # 1169
    ABILITY_ID = PLAGUEBURST_MORTAR_ID

    # `IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$.ctor` -- forme FLAGS
    # DIRECTS, MEME `TargetingRange` statique que 1168 (l'autre active du meme deathCrawler) mais
    # masque DIFFERENT :
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, &range, forceMeleeTarget=1, 0x40000042, 0,0,0)
    #     AActiveAbility..ctor(this, &opts, 0, 0)     # 3e arg = 0 = DirectTargetAttack
    #
    # Decomposition de 0x40000042 -- EXHAUSTIVE (0x2 + 0x40 + 0x40000000, rien ne reste) :
    #   bit  1  0x2          TargetMatchesDynamicRule  point d'extension -> voir ci-dessous
    #   bit  6  0x40         TargetIsTile              PORTEE -- domaine TUILE ; une tuile-cible NON
    #                                                  MARCHABLE rompt et rend le litteral 1
    #                                                  (`ValidRequest`), faute d'AllowUnwalkable
    #                                                  TargetTile (bit 43, absent)
    #   bit 30  0x40000000   AllowNullCasterTile       ALLOW du volet CASTER (MoW hors-plateau)
    #
    # `TargetIsTile` CONFIRME AU DECOMPILE le cast tile-target que le port avait deduit d'une mesure
    # live `abilityTargets` (`kind="tile"`, cf. `plagueburst_damage_targets`) : la deduction devient
    # une lecture. Corollaire du meme bit : `_targets_the_caster` n'a pas a resoudre l'unite, et
    # `TargetIsEnemy` est ABSENT -> aucune regle de CAMP, le natif n'objecte pas sur l'appartenance
    # de l'occupant (c'est le predicat du behaviour, `GetIsValidAdjacentEnemyTrigger`, qui filtre les
    # cibles a l'EXECUTION -- pas le gate de ciblage).
    #
    # `range` = `TargetingRange statics+0x48` = RANGE_WHOLE_BOARD -> aucun test de portee.
    # `forceMeleeTarget` = 1 = RANGED_BOOL_FALSE.
    #
    # `TargetMatchesDynamicRule` : AUCUN `PlagueburstMortarAbility$$GetDynamicInvalidTargetReason`
    # n'est nomme dans les tables -- ce qui ne prouve RIEN (corps triviaux DEDUPLIQUES). Le port
    # garde le defaut 0 de `ActiveAbility.get_dynamic_invalid_target_reason` : permissif dans les
    # deux hypotheses (pas d'override -> 0 est le verdict natif ; override dedupliquee -> le port
    # accepte ce que le natif refuserait, jamais l'inverse). Ecart MESURE en live, cf. case-249.
    TARGETING_OPTIONS = TargetingOptions(
        rules=(TR.TargetMatchesDynamicRule | TR.TargetIsTile | TR.AllowNullCasterTile),
        self_cast=False, range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
        if target_id is None:
            return None
        tile_id = plagueburst_target_tile(state, target_id)
        if tile_id is None:
            return None
        n_tiles = plagueburst_nr_of_tiles(state, caster_id)
        picked = plagueburst_contaminated_tiles(state, target_id, n_tiles)
        # `target@0x178` = l'ENTITE ciblee. Cast TILE-TARGET -> on la presente en domaine TUILE
        # (`FixedTileIds`), ce que consomment `AdjacentTiles`/`Units`/`AddEffect` indifferemment.
        target_sel = FixedTileIds([tile_id])
        ectx = ExecutionContext(state=state, rng=state.rng)
        plagueburst_mortar_tree(target_sel, picked).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        attacks = [{"target": p.get("target"), "total": p.get("total")}
                   for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        pinned = [p.get("target") for n, p in ectx.emitted
                  if n == "AddEffect" and p.get("effect_type") == PINNED and p.get("placed")]
        contaminated = [p.get("target") for n, p in ectx.emitted
                        if n == "AddEffect" and p.get("effect_type") == CONTAMINATED and p.get("placed")]
        return {"ability": PLAGUEBURST_MORTAR_ID, "caster": caster_id, "target": target_id,
                "tile": tile_id, "attacks": attacks, "pinned": pinned, "contaminated": contaminated,
                "nr_of_tiles": n_tiles, "picked_tiles": picked, "dsl": True}


# ===================== PlagueWind (deathTyphus « Typhus », actif 1035) =====================
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.PlagueWindAbility$$ExecuteBehaviour` — MIRROR du
# DECOMPILE (le lambda `<ExecuteBehaviour>b__0` de son `DisplayClass1_0` n'est que le
# `AActiveAbility.Execute(this, behaviour@+0x18, entities@+0x20)` differe par l'AtomicGroup) :
#
#     t1 = Cache( target@0x178 )                                                  # cible PRINCIPALE
#     t2 = Cache( Enemies(caster@0x160, AdjacentUnits(t1, 1, 3), 3) )              # SECONDAIRES
#     t3 = Cache( Unique(Enemies(caster@0x160, AdjacentUnits(t2, 1, 3), 3))
#                 op_Subtraction t1
#                 op_Subtraction t2 )                                             # TERTIAIRES
#     d1 = MinMaxDamage (this, level) = RandomAmount(var 0x0c minDmg  , var 0x0d maxDmg  )
#     d2 = MinMaxDamage2(this, level) = RandomAmount(var 0x36 minDmg_2, var 0x37 maxDmg_2)
#     d3 = MinMaxDamage3(this, level) = RandomAmount(var 0x38 minDmg_3, var 0x39 maxDmg_3)
#     a_i = AttackWithAbilityDamage( caster@0x160, t_i, d_i,
#                                    GetDamageProfile(config, 0) = Psychic,
#                                    GetNumberConstant(config, 0x2f) = nrOfHits,   # LA MEME pour les 3
#                                    AbilityOrEffect(this+0x10 = 0x40b = 1035) )
#     b  = Group(a1, target@0x178, 0x4b) & Group(a2, target@0x178, 0x4c) & Group(a3, target@0x178, 0x4d)
#     ExecuteAtomic( 0x4a, <lambda qui Execute(b)>, target@0x178 )
#
# TROIS bandes concentriques (i2 : « ... to a target within 2 hexes. Any enemies ADJACENT to the
# initial target ... Any FURTHER enemies adjacent to AT LEAST ONE secondary target ... »), chacune
# avec SA PROPRE plage de degat et le MEME nombre de coups. Aucun effet pose, aucun spawn : l'ability
# EST ces trois attaques.
#
# ⚠ FAMILLE = `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` (et NON
# `...$$AttackWithAttackDamage`) — classification par la CALLEE du decompile, jamais au juge
# (rngcrit-1202) : `AbilityDamageBehaviour` -> `IdunBattle.Operations.AbilityDamageOperation$$
# ExecuteHits`, 1 tirage par coup, AUCUN crit, AUCUNE feuille positionnelle (elevation/trench), et
# l'ordre « bouclier x limites » de `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`
# (le cap porte sur le RESTE post-bouclier, #67b/#120).

PLAGUE_WIND_ID = "PlagueWind"


def plague_wind_target_selectors() -> tuple:
    """Les TROIS `Cache` de `PlagueWindAbility$$ExecuteBehaviour` (t1/t2/t3), dans l'ordre ou le
    decompile les construit. Rendus a part pour que l'ability puisse LIRE leur memo apres execution
    (ventilation du diagnostic par bande) sans re-deriver la geometrie.

      * `t1` = `Cache(Target())` — la cible du message (`target@0x178`).
      * `t2` = `Cache(Enemies(AdjacentUnits(t1)))` — ennemis DU CASTER occupant les hexes adjacents a
        la cible. `adjacent_units` = mirror TEXTUEL de la factory native (`Units(AdjacentTiles(s)) - s`,
        cf. `entities/selectors/composites.py`) : aucun filtre `Alive` ajoute, c'est `Units`
        (= `UnitsOnTilesSelector`) qui ne rend que les unites DEBOUT.
      * `t3` = `Cache( Unique(Enemies(AdjacentUnits(t2))) - t1 - t2 )` — ennemis adjacents a AU MOINS
        UN secondaire, prives de la cible et des secondaires. C'est CE call-site qui exige le helper
        `adjacent_units` (la source est un ENSEMBLE, cf. sa docstring : l'exclusion native est
        « appartenance a la source », pas « distance > 0 » par-centre).

    MEMOISATION (le `Cache` natif n'est PAS un pass-through) : chaque noeud est evalue PARESSEUSEMENT,
    a l'execution de SA bande. `t2` est donc fige APRES le degat de la bande 1 et `t3` APRES celui de
    la bande 2 — exactement comme le natif. Consequence portee et VOULUE : un secondaire tue par la
    bande 2 reste dans le memo `t2` (l'ensemble est fige) et sa TUILE sert encore d'ancre a `t3` ;
    il est de toute facon retire par le `- t2` final. Les noeuds sont reconstruits A CHAQUE cast
    -> memo PAR-CAST, comme les `Cache` alloues dans `ExecuteBehaviour`."""
    t1 = Cache(Target())                                                 # Cache(target@0x178)
    t2 = Cache(Enemies(adjacent_units(t1)))                              # Cache(Enemies(AdjacentUnits(t1)))
    t3 = Cache(Sub(Sub(Unique(Enemies(adjacent_units(t2))),              # Unique(Enemies(AdjacentUnits(t2)))
                        t1),                                             #   op_Subtraction t1
                   t2))                                                  #   op_Subtraction t2
    return t1, t2, t3


def plague_wind_tree(selectors: Optional[tuple] = None) -> AtomicGroup:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.PlagueWindAbility$$ExecuteBehaviour`
    (id 1035, deathTyphus) — MIRROR 1:1 du decompile (cf. le bloc ci-dessus).

    DEGAT : trois plages DISTINCTES (`minDmg`/`maxDmg`, `minDmg_2`/`maxDmg_2`, `minDmg_3`/`maxDmg_3`
    = variables 0xc/0xd, 0x36/0x37, 0x38/0x39 — LU dans `IdunBattle.Entities.Abilities.AActiveAbility$$
    MinMaxDamage`, `...$$MinMaxDamage2`, `...$$MinMaxDamage3`), toutes dans
    `variablesAffectedByRarityBonus` (scaling `AbilityVariablesMultiplier` via `ability_var`). Le
    nombre de coups est la MEME constante `GetNumberConstant(0x2f)=nrOfHits`=1 pour les trois bandes
    (le decompile relit litteralement `0x2f` a chacun des trois call-sites). Profil `Psychic`
    (PiercingRatio 100, trait `NoBlocking`), `attackRangeType=Ranged` -> `is_melee=False`.

    `multi=True` sur les trois : le natif passe TOUJOURS par `IdunBattle.Entities.Behaviours.
    AttackBehaviour$$Execute` (resolution de la LISTE + `OrderBy`), y compris pour la bande 1 dont
    l'ensemble est un singleton -> le mode multi est le mirror exact (et un no-op pour la bande 1).

    `Group(..., 0x4b/0x4c/0x4d)` = les groupes de PRESENTATION natifs (`GroupBehaviour` = pass-through
    d'etat) ; `AtomicGroup` = l'`ExecuteAtomic(0x4a)` (inline, #201). Portes pour le mirror structurel :
    aucun n'a d'effet observable sur l'etat ni sur `state.rng`."""
    t1, t2, t3 = selectors if selectors is not None else plague_wind_target_selectors()
    band1 = AttackWithAttackDamage(t1, PLAGUE_WIND_ID, "Psychic", is_melee=False, multi=True,
                                   native_factory="ability",              # IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage
                                   ability_type=int(ActiveAbilityType.PlagueWind))
    band2 = AttackWithAttackDamage(t2, PLAGUE_WIND_ID, "Psychic", is_melee=False, multi=True,
                                   min_key="minDmg_2", max_key="maxDmg_2",   # MinMaxDamage2 (0x36/0x37)
                                   native_factory="ability",
                                   ability_type=int(ActiveAbilityType.PlagueWind))
    band3 = AttackWithAttackDamage(t3, PLAGUE_WIND_ID, "Psychic", is_melee=False, multi=True,
                                   min_key="minDmg_3", max_key="maxDmg_3",   # MinMaxDamage3 (0x38/0x39)
                                   native_factory="ability",
                                   ability_type=int(ActiveAbilityType.PlagueWind))
    # #270-r4 : le 3e argument de `DSLBehaviors.Group` est DECLARE
    # `groupType : IdunBattle.Streams.GroupType` dans `frida/methods.tsv` -- 0x4b/0x4c/0x4d sont
    # les trois bandes d'attaque de PlagueWind, nommees comme telles par le build.
    return AtomicGroup(op_and(op_and(Group(band1, int(GroupType.PlagueWind_Attack1), t1),
                                     Group(band2, int(GroupType.PlagueWind_Attack2), t1)),
                              Group(band3, int(GroupType.PlagueWind_Attack3), t1)))


class PlagueWindAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.PlagueWindAbility$$ExecuteBehaviour` (id 1035,
    `deathTyphus` « Typhus », Death Guard/Chaos — HERO, present dans `rl_duel build --list-pool`).

    AoE CONCENTRIQUE a TROIS bandes, ancree sur la CIBLE (range 2) :
      1. la cible                                -> 1x Psychic `minDmg`  /`maxDmg`
      2. les ennemis ADJACENTS a la cible        -> 1x Psychic `minDmg_2`/`maxDmg_2`
      3. les ennemis adjacents a >=1 SECONDAIRE  -> 1x Psychic `minDmg_3`/`maxDmg_3`
         (cible et secondaires exclus)
    Profil `Psychic` (pierce 100, `NoBlocking`), famille ABILITY (pas de crit, 1 tirage/coup).
    Behaviour = arbre DSL `plague_wind_tree()` (mirror 1:1 du decompile). Termine le tour (1035 hors
    des frozensets de `base.py` -> flags par defaut).

    Diag : `{attacks, main, secondary, tertiary}` — la ventilation par bande vient des memos `Cache`
    (l'ensemble EXACT que chaque bande a frappe), pas d'un re-calcul de geometrie."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.PlagueWind)   # 1035
    ABILITY_ID = PLAGUE_WIND_ID

    # MASQUE — `IdunBattleLogic.Entities.Abilities.Active.Loki.PlagueWindAbility$$.ctor` n'appelle
    # AUCUN `TargetingOptions$$.ctor` : il RECOPIE les 0x40 octets du champ STATIQUE `statics+0x180`
    # puis fait `AActiveAbility..ctor(this, &opts, 0, 0)`. Le masque EFFECTIF est donc la constante
    # ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28`
    # (= `statics+0x1a8`) : **0x4002** (LU, pas deduit ; meme preset-classe que Foehammer 1097).
    #     0x4000  TargetIsEnemy            -> gate porte (`units_can_attack_each_other`)
    #     0x0002  TargetMatchesDynamicRule -> consulte `GetDynamicInvalidTargetReason`. PlagueWind
    #             n'en SURCHARGE aucun (aucun symbole `PlagueWindAbility$$GetDynamicInvalidTarget
    #             Reason` : le slot vtable +0x480 reste le defaut d'`AActiveAbility`, qui rend 0)
    #             -> le defaut 0 de `ActiveAbility.get_dynamic_invalid_target_reason` est FIDELE.
    # PORTEE — le preset copie son `TargetingRange` (`<preset>+0x08..0x1f`) depuis le statique
    # `TargetingRange statics+0x18` (le cctor lit `*(lVar3+0x18)/+0x20/+0x28`) = `RANGE_FROM_CONFIG`
    # (`useRangeFromConfig = true`) -> `SetConfigValuesInTargetingOptions` y pose
    # `overrideRange = GetNumberConstant(0x16 range)` = 2 (config 1035). `forceMeleeTarget` =
    # `*(preset+0x20)` = **1** = `RANGED_BOOL_FALSE` (⚠ l'enum natif est INVERSE : True=0, False=1)
    # -> aucun clamp RangedInMelee.
    TARGETING_OPTIONS = TargetingOptions(
        rules=(TR.TargetIsEnemy | TR.TargetMatchesDynamicRule),
        range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        selectors = plague_wind_target_selectors()     # noeuds NEUFS -> memos par-cast (== le natif)
        ectx = ExecutionContext(state=state, rng=state.rng)
        plague_wind_tree(selectors).execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [{"target": p.get("target"), "total": p.get("total"), "attack": p.get("attack")}
                for n, p in ectx.emitted if n == "AttackWithAttackDamage"]

        def _ids(cache_node) -> set:
            """Ids memoises par un `Cache` APRES execution (`_cached` = le slot +0x28 natif)."""
            memo = cache_node._cached
            if memo is None:
                return set()
            items = [memo] if isinstance(memo, dict) else list(memo)
            return {u.get("id") for u in items if isinstance(u, dict)}

        main_ids, sec_ids, ter_ids = (_ids(s) for s in selectors)
        return {"ability": PLAGUE_WIND_ID, "caster": caster_id, "target": target_id,
                "attacks": atks,
                "main": [a for a in atks if a["target"] in main_ids],
                "secondary": [a for a in atks if a["target"] in sec_ids],
                "tertiary": [a for a in atks if a["target"] in ter_ids],
                "dsl": True}


# ========== Vagues de la face DECISION -- PARTAGEES par PlagueWind (1035) et 1093 ==========
#
# Les TROIS methodes de l'ability que `IdunBattle.AI.Playbook.Loki.MortarionsPlagueWindPlaybook$$
# CalculateCustomUtility`, `...MortarionsPlagueWindPlaybook$$MakeDamagePredictions` ET
# `IdunBattle.AI.Playbook.Loki.PlagueWindPlaybook$$MakeDamagePredictions` appellent pour
# reconstruire leurs vagues. Leurs corps sont DEDUPLIQUES par IL2CPP -- ghidra les nomme d'apres UN
# proprietaire arbitraire, jamais d'apres l'appelant. On les cite donc sous le nom que ghidra rend,
# et on lit leur STRUCTURE :
#
#   t1 = `...StrikeFromTheShadowsAbility$$GetTarget(ability)`
#        = `return *(*(ability+0x30)+0x90) + 0x60` = le selecteur partage `<DSLSelectors+0x60>`
#   t2 = `...StormOfWrathAbility$$u003CExecuteBehaviouru003Eb__1_0(ability, t1)`
#        = `DSLSelectors$$Enemies(of = <DSLSelectors+0x48>, DSLSelectors$$AdjacentUnits(t1, 1, 3), 3)`
#   t3 = `...PlagueWindAbility$$GetTargets3(ability, t1, t2)`
#        = `Unique(Enemies(<+0x48>, AdjacentUnits(t2, 1, 3), 3))
#           op_Subtraction t1 op_Subtraction t2`
#
# SLOTS PARTAGES, etablis par plusieurs lectures independantes du depot (cf. `case-418-r1`,
# `case-411-r3`, `case-459`) : `<DSLSelectors+0x30>` = Owner, `<+0x48>` = Caster, `<+0x60>` = Target.
#
# PIEGE #419 -- le 3e argument d'`IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits(this, origin,
# unique, selectionType)` est `unique`, PAS `includeCenter` : son corps est
# `op_Subtraction(Units(AdjacentTiles(origin), unique, selectionType), origin)`, donc le centre est
# TOUJOURS exclu et le `1` du call-site ne le reintroduit pas. Lire ce `1` comme un `includeCenter`
# inverserait la semantique de la vague 1 vers la vague 2.
#
# MEME CHAINE que la face COMBAT de 1035 ET de 1093 -- mais l'ARTEFACT DIFFERE, et c'est la seule
# raison pour laquelle cette fonction n'est pas `plague_wind_target_selectors` :
# `...MortarionsPlagueWindAbility$$ExecuteBehaviour` (comme `...PlagueWindAbility$$ExecuteBehaviour`)
# enveloppe CHACUNE des trois vagues dans un `DSLSelectors$$Cache` -- la memoisation qui fige un
# ensemble entre les bandes de degat. Les trois methodes ci-dessus n'en ont AUCUN : les playbooks
# les appellent a froid, sur un etat que rien ne mute (aucune attaque n'est executee pendant
# l'evaluation d'une utilite). Porter le `Cache` cote decision serait donc un mirror INFIDELE, sans
# consequence observable ici -- on porte ce que le decompile montre.
#
# ⚠ CES TROIS CORPS SONT APPELES PAR LES DEUX PLAYBOOKS, aux MEMES adresses (lecture directe des
# deux `MakeDamagePredictions` : `PlagueWindPlaybook$$MakeDamagePredictions` et
# `MortarionsPlagueWindPlaybook$$MakeDamagePredictions` appellent litteralement les MEMES fonctions).
# C'est pourquoi cette fonction ne porte PAS le nom de 1093 : elle est le mirror d'un artefact
# PARTAGE, et 1035 le consomme autant que 1093. Ce que la deduplication IL2CPP masque, ce n'est pas
# une ressemblance -- c'est l'IDENTITE du code.


def plague_wind_wave_selectors() -> tuple:
    """Les TROIS vagues de la face DECISION de `PlagueWind` (1035) et `MortarionsPlagueWind` (1093)
    -- `...PlagueWindPlaybook$$MakeDamagePredictions`,
    `...MortarionsPlagueWindPlaybook$$MakeDamagePredictions` et
    `...MortarionsPlagueWindPlaybook$$CalculateCustomUtility` -- cf. le bloc ci-dessus.

      * `t1` = `Target()` -- le selecteur partage `<DSLSelectors+0x60>`, evalue sur le `target` de
        l'`AbilityEntities` que le playbook construit.
      * `t2` = `Enemies(AdjacentUnits(t1))` -- les ennemis DU CASTER occupant les hexes adjacents a
        la cible. `Enemies` referme `<DSLSelectors+0x48>` = Caster : le port lit `ctx.caster`.
      * `t3` = `Unique(Enemies(AdjacentUnits(t2))) - t1 - t2` -- les ennemis adjacents a AU MOINS UN
        secondaire, prives de la cible et des secondaires. C'est ce call-site qui exige le helper
        `adjacent_units` (source = un ENSEMBLE) : l'exclusion native y est l'APPARTENANCE a la
        source, pas une distance par-centre.

    Nœuds NEUFS a chaque appel (le natif reconstruit les trois selecteurs a chaque appel de
    playbook), donc aucun etat porte d'une evaluation a la suivante."""
    t1 = Target()                                                # <DSLSelectors+0x60>
    t2 = Enemies(adjacent_units(t1))                             # Enemies(<+0x48>, AdjacentUnits(t1, 1, 3), 3)
    t3 = Sub(Sub(Unique(Enemies(adjacent_units(t2))),            # Unique(Enemies(AdjacentUnits(t2)))
                 t1),                                            #   op_Subtraction t1
             t2)                                                 #   op_Subtraction t2
    return t1, t2, t3


def mortarions_plague_wind_psyker_selector() -> "UnitsWithTrait":
    """`DSLSelectors$$UnitsWithTrait(t1 + t2 + t3, 0x3ea = Psyker, 3)` -- l'ensemble COMPLET dont
    `IdunBattle.DSL.TargetsSelector$$Count` rend l'utilite de 1093.

    `IdunBattle.Entities.Selectors.UnitsWithTraitSelector$$.ctor(state, entities, trait,
    shouldHave, selectionType)` recoit `shouldHave = 1` (le `mov r9b, 1` du call-site de
    `DSLSelectors$$UnitsWithTrait`), et son `$$Select` garde l'unite quand
    `IdunBattle.Entities.UnitExtensions$$HasTrait(unit, trait) == shouldHave` -> filtre POSITIF.

    L'union est le `IdunBattle.DSL.TargetsSelector$$op_Addition(op_Addition(t1, t2), t3)` du
    decompile, dans cet ordre. AUCUN `Unique` par-dessus : les trois vagues sont deja disjointes par
    construction (`t3` retranche `t1` et `t2` ; `t2` exclut `t1` via le `- origin` d'`AdjacentUnits`),
    et le natif n'en insere pas."""
    t1, t2, t3 = plague_wind_wave_selectors()
    return UnitsWithTrait(Union(Union(t1, t2), t3), int(UnitTrait.Psyker))   # 0x3ea = 1002


# ============ MortarionsPlagueWind (deathBossMortarion, GUILD BOSS, actif 1093) ============
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.MortarionsPlagueWindAbility$$ExecuteBehaviour`
# -- MIRROR du DECOMPILE (le lambda `<ExecuteBehaviour>b__0` de son `DisplayClass1_0` n'est que
# l'`AActiveAbility.Execute(this, Group(bande_i, <Target>, 0x5d/0x5e/0x5f))` differe par
# l'AtomicGroup 0x5c) :
#
#     t1 = Cache( <DSLSelectors+0x60> = Target )
#     t2 = Cache( Enemies(<+0x48> = Caster, AdjacentUnits(t1, 1, 3), 3) )
#     t3 = Cache( Unique(Enemies(<+0x48>, AdjacentUnits(t2, 1, 3), 3))
#                 op_Subtraction t1 op_Subtraction t2 )
#     d_i = If( DSLTriggers$$HasTrait(<DSLSelectors+0x60> = Target, 2 = Summon),
#               Multiply( MinMaxDamage{,2,3}Average, <DSLFormulas+0x28> = Direct(2) ),
#               MinMaxDamage{,2,3}Average )
#     a_i = AttackWithAbilityDamage( <+0x78 behaviors>, <+0x48> = Caster, t_i, d_i,
#                                    Nullable(AActiveAbility$$GetDamageProfile(this)),
#                                    AActiveAbility$$GetHits(this) = GetNumberConstant(0x2f),
#                                    AbilityOrEffect(this), 2 )
#     b   = Group(a1, Target, 0x5d) & Group(a2, Target, 0x5e) & Group(a3, Target, 0x5f)
#     return AtomicGroup( 0x5c, <lambda qui Execute(b)>, <entities+0x10> )
#
# JUMEAU STRUCTUREL de `1035 PlagueWind` (meme chaine de trois vagues concentriques, MEMES corps de
# selecteur -- cf. `plague_wind_wave_selectors` plus haut), et DEUX differences LUES, aucune devinee :
#
#  1. **LA MOYENNE, PAS LE TIRAGE.** 1035 passe `MinMaxDamage{,2,3}` = `RandomAmount(min, max)` ;
#     1093 passe `MinMaxDamage{,2,3}Average` = `Half(Sum(Direct(min), Direct(max)), 0)`. Le degat de
#     1093 est donc DETERMINISTE et ne consomme AUCUN tirage de valeur -- ce qui est aussi ce que
#     `active_ability._PREDICTION_MINMAX_AVERAGE` inscrit deja pour sa face DECISION.
#  2. **LE GATE `Summon` x2.** `<DSLFormulas+0x28>` est LU : `IdunBattleLogic.Entities.DSLFormulas$$
#     .ctor` alloue cinq constantes partagees (`+0x18 Direct(0)`, `+0x20 Direct(1)`,
#     `+0x28 Direct(2)`, `+0x30 Direct(100)`, `+0x38 Direct(-1)`), donc le facteur vaut **2**.
#     Le `HasTrait` porte sur `<DSLSelectors+0x60>` = **la CIBLE PRINCIPALE du cast**, jamais l'unite
#     frappee : si la cible est un `Summon`, les TROIS vagues entieres sont doublees, y compris sur
#     des unites qui n'en sont pas ; sinon aucune ne l'est, meme si toute la vague 2 est faite de
#     summons. Meme quirk, meme foyer et meme lecture que la face DECISION
#     (`playbook/prediction/plague_wind.py`).
#
# ⚠ FAMILLE = `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` (classification par la
# CALLEE du decompile, jamais au juge) -> `AbilityDamageBehaviour` -> `IdunBattle.Operations.
# AbilityDamageOperation$$ExecuteHits` : AUCUN crit, AUCUNE feuille positionnelle, et l'ordre
# « bouclier x limites » de `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`.
# Le port passe par la feuille HOMONYME `AttackWithAbilityDamage(native_operation="ability")`, dont
# le corps est `execute_ability_attack(base, base, ..., is_attack_damage_op=False)` -- la MEME
# operation que la feuille de 1035, avec des bornes DEGENEREES parce que le node est deterministe.
#
# CONFIG (gameconfig `MortarionsPlagueWind`) : `damageProfile = Psychic`, `nrOfHits = 1` (la MEME
# constante pour les trois vagues -- le decompile relit litteralement `GetHits` a chacun des trois
# call-sites), `range = 2`, `attackRangeType = Ranged` -> `is_melee=False`. Les six variables de
# degat sont dans `variablesAffectedByRarityBonus` (scaling `AbilityVariablesMultiplier`).
# ⚠ Le degat CROIT avec la bande (20-25 / 30-35 / 50-70 au niveau 1), a l'INVERSE de 1035
# (36-45 / 27-34 / 20-25) : la vague 3 est la plus forte. Aucune symetrie a supposer entre les deux.

MORTARIONS_PLAGUE_WIND_ID = "MortarionsPlagueWind"

#: Les trois couples `(min, max)` que lisent `AActiveAbility$$MinMaxDamage{,2,3}Average`, dans
#: l'ordre des trois vagues -- MEME table que `playbook/prediction/plague_wind.WAVE_DAMAGE_VARS`
#: (variables 0xc/0xd, 0x36/0x37, 0x38/0x39).
MORTARIONS_PLAGUE_WIND_WAVE_VARS = ((AbilityVariableType.minDmg, AbilityVariableType.maxDmg),
                                    (AbilityVariableType.minDmg_2, AbilityVariableType.maxDmg_2),
                                    (AbilityVariableType.minDmg_3, AbilityVariableType.maxDmg_3))


def mortarions_plague_wind_target_selectors() -> tuple:
    """Les TROIS `Cache` de `MortarionsPlagueWindAbility$$ExecuteBehaviour` (t1/t2/t3), dans l'ordre
    ou le decompile les construit -- STRICTEMENT la meme chaine que `plague_wind_target_selectors`
    (les corps de selecteur sont litteralement les MEMES fonctions natives, cf. le bloc
    « Vagues de la face DECISION » plus haut).

    Rendus par une fonction PROPRE a 1093, et non par un alias, parce que l'appelant doit obtenir des
    noeuds NEUFS a chaque cast : le `Cache` natif est alloue DANS `ExecuteBehaviour`, donc son memo
    est PAR-CAST. C'est ce memo qui fige `t2` apres le degat de la bande 1 et `t3` apres celui de la
    bande 2 -- exactement le natif."""
    t1 = Cache(Target())                                                 # Cache(<+0x60> Target)
    t2 = Cache(Enemies(adjacent_units(t1)))                              # Cache(Enemies(AdjacentUnits(t1)))
    t3 = Cache(Sub(Sub(Unique(Enemies(adjacent_units(t2))),              # Unique(Enemies(AdjacentUnits(t2)))
                       t1),                                              #   op_Subtraction t1
                   t2))                                                  #   op_Subtraction t2
    return t1, t2, t3


def mortarions_plague_wind_damage_nodes(state: "State", caster_id: int) -> tuple:
    """Les TROIS noeuds `MortarionsPlagueWindAbility$$GetDamage{1,2,3}` -- mirror 1:1 :

        If( HasTrait(Target, 2 = Summon), Multiply(<avg>, Direct(2)), <avg> )
        <avg> = MinMaxDamage{,2,3}Average = Half(Sum(Direct(min), Direct(max)), 0)

    Les deux variables sont lues au niveau de l'ability ACTIVE du caster et scalees par
    `AbilityVariablesMultiplier` -- c'est le `GetVariableForLevel(config, <var>, abilityState, 0)`
    du decompile, et la MEME lecture que `ability_attack_params` fait pour le mode bornes.
    Caster sans `StatsComponent` -> niveau 0 / multiplicateur 100 (meme degradation qu'ailleurs :
    aucune valeur inventee, la config repond ce qu'elle a a l'index 0)."""
    e = state.get_entity(caster_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    level = (ctx.active_ability_level if ctx is not None else 0) or 0
    mult = (ctx.ability_variables_multiplier if ctx is not None else 100)
    nodes = []
    for mn_key, mx_key in MORTARIONS_PLAGUE_WIND_WAVE_VARS:
        mn = int(ability_var(MORTARIONS_PLAGUE_WIND_ID, str(mn_key.name), level,
                             multiplier_pct=mult) or 0)
        mx = int(ability_var(MORTARIONS_PLAGUE_WIND_ID, str(mx_key.name), level,
                             multiplier_pct=mult) or 0)
        avg = Half(Sum(Const(mn), Const(mx)))                # MinMaxDamage{,2,3}Average
        nodes.append(If(HasTrait(Target(), int(UnitTrait.Summon)),        # <+0x60> = CIBLE PRINCIPALE
                        Multiply(avg, Const(2)),             # <DSLFormulas+0x28> = Direct(2)
                        avg))
    return tuple(nodes)


def mortarions_plague_wind_tree(selectors: tuple, damages: tuple, hits: int) -> AtomicGroup:
    """Arbre de `MortarionsPlagueWindAbility$$ExecuteBehaviour` -- MIRROR 1:1 du decompile
    (cf. le bloc ci-dessus).

    `multi=True` sur les trois : le natif passe TOUJOURS par `IdunBattle.Entities.Behaviours.
    AttackBehaviour$$Execute` (resolution de la LISTE + `OrderBy`), y compris pour la bande 1 dont
    l'ensemble est un singleton -> le mode multi est le mirror exact (et un no-op pour la bande 1).

    `Group(..., 0x5d/0x5e/0x5f)` = les groupes de PRESENTATION natifs (pass-through d'etat) ;
    `AtomicGroup` = l'`ExecuteAtomic(0x5c)`. Les quatre `GroupType` sont NOMMES par le build
    (`MortarionsPlagueWind_Attack{,1,2,3}` = 92/93/94/95), aucun n'a d'effet observable sur l'etat
    ni sur `state.rng`."""
    t1, _t2, _t3 = selectors
    bands = [AttackWithAbilityDamage(sel, "Psychic", node, is_melee=False, hits=hits, multi=True,
                                     native_operation="ability",     # AbilityDamageOperation
                                     ability_type=int(ActiveAbilityType.MortarionsPlagueWind))
             for sel, node in zip(selectors, damages)]
    return AtomicGroup(
        op_and(op_and(Group(bands[0], int(GroupType.MortarionsPlagueWind_Attack1), t1),
                      Group(bands[1], int(GroupType.MortarionsPlagueWind_Attack2), t1)),
               Group(bands[2], int(GroupType.MortarionsPlagueWind_Attack3), t1)))


class MortarionsPlagueWindAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.MortarionsPlagueWindAbility$$ExecuteBehaviour`
    (id 1093, `deathBossMortarion` « Mortarion » -- GUILD BOSS, kind `npc`).

    AoE CONCENTRIQUE a TROIS bandes, ancree sur la CIBLE (range 2) :
      1. la cible                                -> 1x Psychic avg(`minDmg`  ,`maxDmg`  )
      2. les ennemis ADJACENTS a la cible        -> 1x Psychic avg(`minDmg_2`,`maxDmg_2`)
      3. les ennemis adjacents a >=1 SECONDAIRE  -> 1x Psychic avg(`minDmg_3`,`maxDmg_3`)
         (cible et secondaires exclus)
    Chaque bande est DOUBLEE quand la CIBLE PRINCIPALE porte le trait `Summon` (le gate est sur elle,
    pas sur l'unite frappee). Profil `Psychic`, famille ABILITY (pas de crit, degat DETERMINISTE).
    Behaviour = arbre DSL `mortarions_plague_wind_tree()`.

    CONFRONTABILITE : porteur `npc`, monte par `rl_duel build --explicit-stats
    "deathBossMortarion:<palier>" --p-units "deathBossMortarion:<palier>"` (le jeu le publie sous
    l'id d'entite REMAPPE `GuildBoss5Boss1DeathMortarion`, ce que le garde de roster lit comme un
    deficit -> `TACTICUS_ALLOW_ROSTER_DEFICIT=1`).

    Diag : `{attacks, main, secondary, tertiary}` -- la ventilation par bande vient des memos `Cache`
    (l'ensemble EXACT que chaque bande a frappe), pas d'un re-calcul de geometrie."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.MortarionsPlagueWind)   # 1093
    ABILITY_ID = MORTARIONS_PLAGUE_WIND_ID

    # MASQUE -- FORME STATIC-COPY : `MortarionsPlagueWindAbility$$.ctor` n'appelle AUCUN
    # `TargetingOptions$$.ctor` ; il RECOPIE les 0x40 octets du champ statique
    # `<TargetingOptions statics>+0x180` puis fait `AActiveAbility$$.ctor(this, &opts, 0)`. Le masque
    # EFFECTIF est donc la constante que `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit a
    # `<preset>+0x28` (= `statics+0x1a8`) : **0x4002**, RELU dans le cctor sur le build courant.
    #     0x4000  TargetIsEnemy            -> gate porte (`units_can_attack_each_other`)
    #     0x0002  TargetMatchesDynamicRule -> consulte `GetDynamicInvalidTargetReason`, qu'aucun
    #             symbole `MortarionsPlagueWindAbility$$GetDynamicInvalidTargetReason` ne surcharge
    #             -> le slot vtable reste le defaut d'`AActiveAbility`, qui rend 0.
    # Le preset est LE MEME (`statics+0x180`) que celui de son jumeau `PlagueWindAbility$$.ctor`
    # (1035). Champs relus dans le cctor : `<preset>+0x180` isSelfCasting = 0 ;
    # `<preset>+0x188..0x19f` range <- `TargetingRange statics+0x18` = RANGE_FROM_CONFIG (donc
    # `overrideRange = GetNumberConstant(0x16 range)` = 2) ; `<preset>+0x1a0` forceMeleeTarget = 1
    # = RANGED_BOOL_FALSE (l'enum natif est INVERSE : True=0, False=1) -> aucun clamp RangedInMelee.
    # Cette entree MIGRE depuis `TARGETING_OPTIONS_UNPORTED` (contrat de disjonction de cette table :
    # porter la face COMBAT EXIGE d'en retirer la ligne).
    TARGETING_OPTIONS = TargetingOptions(
        rules=(TR.TargetIsEnemy | TR.TargetMatchesDynamicRule),
        range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        selectors = mortarions_plague_wind_target_selectors()   # noeuds NEUFS -> memos par-cast
        damages = mortarions_plague_wind_damage_nodes(state, caster_id)
        # `AActiveAbility$$GetHits` = `GetNumberConstant(0x2f)` -> `AbilityConstantType`, PAS
        # `AbilityVariableType` (les deux portent l'ordinal 47, et confondre les deux serait
        # SILENCIEUX en ordinal : c'est le nom qui tranche).
        hits = int(ability_var(MORTARIONS_PLAGUE_WIND_ID, str(AbilityConstantType.nrOfHits.name),
                               is_constant=True) or 1)
        ectx = ExecutionContext(state=state, rng=state.rng)
        mortarions_plague_wind_tree(selectors, damages, hits).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        atks = [{"target": p.get("target"), "total": p.get("total"), "attack": p.get("attack")}
                for n, p in ectx.emitted if n == "AttackWithAbilityDamage"]

        def _ids(cache_node) -> set:
            """Ids memoises par un `Cache` APRES execution (`_cached` = le slot +0x28 natif)."""
            memo = cache_node._cached
            if memo is None:
                return set()
            items = [memo] if isinstance(memo, dict) else list(memo)
            return {u.get("id") for u in items if isinstance(u, dict)}

        main_ids, sec_ids, ter_ids = (_ids(s) for s in selectors)
        return {"ability": MORTARIONS_PLAGUE_WIND_ID, "caster": caster_id, "target": target_id,
                "attacks": atks,
                "main": [a for a in atks if a["target"] in main_ids],
                "secondary": [a for a in atks if a["target"] in sec_ids],
                "tertiary": [a for a in atks if a["target"] in ter_ids],
                "dsl": True}


# ============ ReapingScythe (deathBossMortarion, GUILD BOSS, actif 1095) ============
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ReapingScytheAbility$$ExecuteBehaviour`
# -- MIRROR du DECOMPILE, qui tient en TROIS lignes (aucun lambda, aucun groupe) :
#
#     targets = op_Addition( <DSLSelectors+0x60> = Target,
#                            DSLSelectors$$AdjacentFriends(<+0x60>, unique = 1, selectionType = 3) )
#     b = AttackWithAttackDamage( <+0x78 behaviors>, <+0x48> = Caster, targets,
#                                 AActiveAbility$$MinMaxDamage(this, abilityState, 0),
#                                 Nullable(AActiveAbility$$GetDamageProfile(this)),
#                                 AActiveAbility$$GetHits(this) = GetNumberConstant(0x2f),
#                                 AbilityOrEffect(this), <AttackOptions VIDE>, 2 )
#     return AActiveAbility$$Execute(this, b)
#
# Le meme selecteur est publie a part par `ReapingScytheAbility$$GetDamageTargetsSelector`, mot pour
# mot -- c'est la face que lit `IdunBattle.AI.Playbook.Loki.ReapingScythePlaybook$$
# MakeDamagePredictions`.
#
# ⚠ **`AdjacentFriends` ANCRE SUR LA CIBLE = les ENNEMIS DU CASTER.** La surcharge lue est la
# VARIANTE A (`DSLSelectors$$AdjacentFriends(this, unit, unique, selectionType)` =
# `Friends(unit, Units(AdjacentTiles(unit), unique, selectionType) - unit, selectionType)`) --
# tranchee par ses XREFS ENTRANTES, `ReapingScytheAbility$$ExecuteBehaviour` etant ABSENTE de la
# liste des appelants de la variante B. La REFERENCE d'equipe y est le CENTRE, donc `Target` : les
# « amis » sont ceux de la CIBLE. Collapser la reference sur le caster (le defaut du port) rendrait
# exactement le camp INVERSE -- les allies de Mortarion au lieu de ses victimes.
#
# ⚠ **FAMILLE = ATTACK.** La callee est `DSLBehaviors$$AttackWithAttackDamage` (et NON
# `...$$AttackWithAbilityDamage`, celle de 1093) -> `AttackDamageBehaviour` ->
# `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` : crit et block ACTIFS, 2 tirages par
# coup. Le 8e argument `Nullable<AttackDamageBehaviourOptions>` est passe VIDE (`local_1b8..local_198
# = 0`) -> ni `alwaysOverkilled`, ni `alwaysCrit`, ni le drapeau de variance d'arme.
#
# CONFIG (gameconfig `ReapingScythe`) : `damageProfile = Chain`, **`nrOfHits = 7`**,
# `attackRangeType = Melee` -> `is_melee=True`. Aucune constante `range` : la portee vient du preset.

REAPING_SCYTHE_ID = "ReapingScythe"


def reaping_scythe_damage_targets_selector() -> Union:
    """`ReapingScytheAbility$$GetDamageTargetsSelector` (= le selecteur de cibles de son
    `ExecuteBehaviour`, mot pour mot) : `Target op_Addition AdjacentFriends(Target, 1, 3)`.

    `reference=Target()` est OBLIGATOIRE et non decoratif : la variante A native referme
    `Friends(unit = <le centre>, ...)`, donc l'equipe de reference est celle de la CIBLE. Le defaut
    du port (`reference=None` -> `ctx.caster`) selectionnerait les allies du CASTER."""
    t = Target()                                             # <DSLSelectors+0x60>
    return Union(t, AdjacentFriends(t, reference=t, selection_type=SELECTION))


def reaping_scythe_tree(hits: Optional[int] = None) -> AttackWithAttackDamage:
    """Arbre de `ReapingScytheAbility$$ExecuteBehaviour` -- MIRROR 1:1 (cf. le bloc ci-dessus).

    `multi=True` : le selecteur resout N unites (la cible + ses voisins allies), et le natif passe
    par `AttackBehaviour$$Execute` (resolution de la LISTE puis `OrderBy`).
    `hits=None` (defaut) = coups lus de la config par `ability_attack_params` (`nrOfHits` = 7)."""
    return AttackWithAttackDamage(reaping_scythe_damage_targets_selector(), REAPING_SCYTHE_ID,
                                  "Chain", is_melee=True, multi=True,
                                  native_factory="attack",   # DSLBehaviors$$AttackWithAttackDamage
                                  hits_override=hits,
                                  ability_type=int(ActiveAbilityType.ReapingScythe))


class ReapingScytheAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ReapingScytheAbility$$ExecuteBehaviour`
    (id 1095, `deathBossMortarion` « Mortarion » -- GUILD BOSS, kind `npc`).

    Faux au contact : **7 coups** `Chain` (`minDmg`/`maxDmg`) portes sur la cible ADJACENTE **et sur
    tous les allies de la cible qui lui sont adjacents** -- une propagation en ETOILE autour de la
    victime, pas une chaine de proche en proche. Famille ATTACK (crit et block actifs).

    CONFRONTABILITE : identique a 1093 (meme porteur `npc`, meme montage).

    Diag : `{attacks}` -- une entree par cible frappee, dans l'ordre `OrderBy` natif (id croissant)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ReapingScythe)   # 1095
    ABILITY_ID = REAPING_SCYTHE_ID

    # MASQUE -- FORME STATIC-COPY : `ReapingScytheAbility$$.ctor` n'appelle AUCUN
    # `TargetingOptions$$.ctor` ; il recopie les 0x40 octets de `<TargetingOptions statics>+0x40`
    # puis fait `AActiveAbility$$.ctor(this, &opts, 0)`. Champs RELUS dans
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` sur le build courant :
    #   `<preset>+0x40` isSelfCasting    = 0
    #   `<preset>+0x48..0x5f` range      <- `TargetingRange statics+0x30` = RANGE_ADJACENT
    #   `<preset>+0x60` forceMeleeTarget = 1 = RANGED_BOOL_FALSE (enum natif INVERSE)
    #   `<preset>+0x68` rules            = **0x4000** = TargetIsEnemy, et RIEN d'autre
    # C'est le MEME preset que `1217 TheLionsWrath` -- et donc PAS de `TargetMatchesDynamicRule` :
    # aucun `ReapingScytheAbility$$GetDynamicInvalidTargetReason` n'existe, ce qui est coherent.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy, self_cast=False,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        reaping_scythe_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [{"target": p.get("target"), "total": p.get("total"), "attack": p.get("attack")}
                for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        return {"ability": REAPING_SCYTHE_ID, "caster": caster_id, "target": target_id,
                "attacks": atks, "dsl": True}


# =================================================================================================== #
# BlightGrenades (1176, `deathNpc2PlagueMarine` -- npc) -- #997.
#
# ⚠ Namespace natif SANS `Loki` : `IdunBattleLogic.Entities.Abilities.Active.BlightGrenadesAbility`
# (contraste tout le reste de ce module). Range ici par FACTION du porteur, comme le module l'annonce.
#
# L'audit de couverture l'annoncait `DAMAGE(Toxic)` en derivant la categorie du `damageProfile` de
# l'ARME du porteur (residu #491-r2) ; ici c'est **CONFIRME** par le decompile -- le cast frappe.
# Cf. `docs/rl/case-997-six-noop-la-categorie-annoncee-ment-4-fois-sur-6.md`.
# =================================================================================================== #

BLIGHT_GRENADES_ID = "BlightGrenades"
#: `PickRandomly(., amount=2, ...)` -- LITTERAL du corps natif, PAS une constante gameconfig (la
#: config 1176 ne porte ni `nrOfTargets` ni `nrOfHits_2`). Corrobore par l'i2 : « up to two enemy
#: units behind the target ».
BG_BEHIND_TARGETS = 2
BG_CONTAMINATED = int(EffectType.Contaminated)     # 0x4dc = 1244 -- l'effet de tuile du gate dynamique


def blight_grenades_tree() -> AtomicGroup:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.BlightGrenadesAbility$$ExecuteBehaviour`
    (id 1176, `deathNpc2PlagueMarine`) -- MIRROR du DECOMPILE :

        behind = PickRandomly( UnitsDirectlyBehind(caster@0x48, target@0x60),
                               2, allowRepeat:0, maxRepeats:0x7fffffff, skipForced:false )
        ExecuteAtomic( op_BitwiseAnd(
            AttackWithAbilityDamage(caster, target, MinMaxDamage(abilityState), GetDamageProfile(),
                                    GetHits(), this, 2),                                   # [MAIN]
            AttackWithAbilityDamage(caster, behind, MinMaxDamage(abilityState), GetDamageProfile(),
                                    GetHits(), this, 2) )                                  # [DERRIERE]
          , 0x2a )

    ⚠ PLAGE ET COUPS IDENTIQUES sur les DEUX volets -- et ce n'est pas une hypothese de symetrie :
    le corps natif appelle DEUX FOIS `AActiveAbility$$MinMaxDamage(this, abilityState, 0)` et DEUX
    FOIS `AActiveAbility$$GetHits(this)`, sans jamais toucher a un index secondaire. La config 1176
    n'a d'ailleurs ni `minDmg_2`/`maxDmg_2` ni `nrOfHits_2`. C'est le CONTRASTE du patron splash
    habituel (`loki/splash.py`), ou le volet secondaire lit `nrOfHits_2` (0x32) -- recopier ce
    template ici ecrirait un nombre de coups FAUX.

    SELECTEUR DERRIERE = `UnitsDirectlyBehind(caster, target)` : ennemis-du-caster VIVANTS sur
    l'anneau R1 de la cible, du COTE OPPOSE au caster (`MinDistance(caster, cand) > MinDistance(caster,
    target)`, comparateur STRICT -- la laterale a distance EGALE est EXCLUE, case #48), meme elevation
    a +-1 pres. Deja porte et confronte live (PlasmaCannon 1150). Le `PickRandomly(., 2)` est FOLDE
    dans la feuille via `pick_n=2` : le natif tire `min(len(pool), 2)` fois MEME quand le pool tient
    dans 2 (#130, `_pick_randomly_n`) -- court-circuiter desaligne tout le flux RNG aval.

    FACTORY NATIVE = `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` (symbole resolu
    tel quel dans le corps decompile) -> `native_factory="ability"` = `AbilityDamageOperation` = 1
    tirage/coup, PAS les 2 tirages/coup de `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (piege rngcrit-1202 :
    PlasmaCannon, dont cet arbre est le jumeau STRUCTUREL, est de l'autre famille).
    RANGED (`attackRangeType: Ranged`, `constants.range` = 2), profil Toxic, `nrOfHits` = 1.

    `op_BitwiseAnd` = `CombinedBehaviour` (effets PURS -> les deux volets s'executent) ;
    `ExecuteAtomic(., 0x2a)` -> `AtomicGroup` (inline #201, cf. #209). Ordre = MAIN puis DERRIERE."""
    tgt = Target()
    main = AttackWithAttackDamage(tgt, BLIGHT_GRENADES_ID, "Toxic", is_melee=False,
                                  native_factory="ability")                     # MinMaxDamage/GetHits
    behind = AttackWithAttackDamage(UnitsDirectlyBehind(), BLIGHT_GRENADES_ID, "Toxic",
                                    is_melee=False, multi=True, pick_n=BG_BEHIND_TARGETS,
                                    native_factory="ability")                   # MEME plage, MEMES coups
    return AtomicGroup(op_and(main, behind))


class BlightGrenadesAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.BlightGrenadesAbility$$ExecuteBehaviour`
    (id 1176, `deathNpc2PlagueMarine` -- npc ; faction Death Guard).

    Deux volets d'attaque a plage ET coups IDENTIQUES : la cible, puis jusqu'a 2 ennemis tires au
    hasard directement DERRIERE elle (cf. `blight_grenades_tree`).

    CONFRONTABILITE : porteur `deathNpc2PlagueMarine`, npc -- montable par `--explicit-stats` (toute
    entree `units.npc` porte une table `stats[]`). « npc-only » n'implique pas « non confrontable »."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.BlightGrenades)   # 1176
    ABILITY_ID = BLIGHT_GRENADES_ID

    # GATE DE CIBLE (#115) -- forme (B) PRESET + FLAGS, DEUX ctors enchaines.
    # `IdunBattleLogic.Entities.Abilities.Active.BlightGrenadesAbility$$.ctor` :
    #     TargetingOptions..ctor(&preset, 0, &<TargetingRange statics+0x18>, 0, 0x4002, 0, 0)
    #     TargetingOptions..ctor(&opts, &preset, 0x2000000)      <- surcharge PRESET+FLAGS
    #     AActiveAbility..ctor(this, &opts, 0)
    # Cette surcharge recopie le preset champ par champ SAUF `Rules`, qu'elle **COMBINE**
    # (`dst+0x28 = flags | preset+0x28`). Le masque effectif n'est donc NI `0x4002` NI `0x2000000` :
    # c'est leur OU = `0x2004002`. Lire le seul litteral visible donnerait un masque FAUX.
    # Decomposition EXHAUSTIVE de 0x2004002 (aucun bit residuel) :
    #     0x2         (bit 1)  TargetMatchesDynamicRule       -> consulte
    #                          `get_dynamic_invalid_target_reason` ci-dessous (PORTEE)
    #     0x4000      (bit 14) TargetIsEnemy                  -> refus sur soi-meme / un allie
    #     0x2000000   (bit 25) AllowObscuredTargetByElevation -> l'elevation n'obscurcit pas
    # C'est le MEME masque effectif que 1048 `FragstormGrenadeLauncher` (preset statique `+0x180` =
    # `0x4002` + les memes flags `0x2000000`) -- mais par une AUTRE forme : ici le preset est
    # construit INLINE par un premier ctor, pas recopie d'un champ statique.
    # PORTEE : `TargetingRange` statique `+0x18` = `useRangeFromConfig` -> `constants.range` = 2 ;
    # `forceMeleeTarget = 0` = `RangedBool.True` (l'enum natif est INVERSE).
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy | TR.AllowObscuredTargetByElevation,
        self_cast=False, range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_TRUE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int, target_id) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.BlightGrenadesAbility$$GetDynamicInvalidTargetReason`
        -- la regle-delegue posee a `options+0x38`, consultee parce que le masque porte
        `TargetMatchesDynamicRule`. Corps natif, LU (5 parametres `caster, casterTiles, target,
        targetTiles`) :

            for (i = 0; i < targetTiles.Count; i++)
                if (EntityExtensions.IsOnTileWithEffect(targetTiles[i], 0x4dc, this.state))
                    return 2
            return 0

        => la cible est REFUSEE (raison 2) des qu'UNE de ses tuiles porte
        `EffectType.Contaminated` (1244). L'i2 le dit mot pour mot : « to an enemy unit within range
        **that is not on a hex with Contamination** ». C'est un gate EXISTENTIEL sur les pieds, pas
        sur la seule main tile -- `IsOnTileWithEffect` itere `EntityExtensions$$IterateTiles`.

        Le predicat par-tuile est le MEME que celui de `UnitsOnTilesWithEffect` cote DSL :
        `state.effects.has_effect(<tile-id>, effect_type)`, avec la meme cle tile-id que la pose
        `AddEffectOperation` (case-35). Sans `board` ou sans `state.effects` -> 0 (permissif), ce qui
        est la degradation fidele : le port ne fabrique pas un refus sur une donnee qu'il n'a pas.

        NB `Contaminated` n'a, a ce jour, aucun POSEUR porte cote runner : ce gate rend donc 0 dans
        tout montage actuel. Il est porte quand meme -- une regle dynamique absente rend `0` par le
        chemin de repli, ce qui est la MEME valeur mais pour une MAUVAISE raison, et cesserait d'etre
        juste des que l'effet 1244 entrera au port."""
        board = getattr(state, "board", None)
        effects = getattr(state, "effects", None)
        if board is None or effects is None or target_id is None:
            return 0
        for pos in get_unit_feet(state, int(target_id)):          # IterateTiles(target) -- EXISTENTIEL
            tid = board.id_at(pos[0], pos[1])
            if tid is not None and effects.has_effect(int(tid), effect_type=BG_CONTAMINATED):
                return 2
        return 0

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        blight_grenades_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        behind = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]
        return {"ability": BLIGHT_GRENADES_ID, "caster": caster_id, "target": target_id,
                "main_attack": main, "behind": behind, "dsl": True}


# ============ TheLantern (1094, `deathBossMortarion` « Mortarion », GuildBoss) -- #1030 =========
#
# PHASE 1 du patron 2-PHASES, et **LE CAST NE FRAPPE PAS**. La colonne `DAMAGE(Energy)` de l'audit
# de couverture derive du `damageProfile` de la CONFIG, pas du behaviour : celui-ci pose TROIS
# effets et zero degat. La PHASE 2 (la triggered 1167) vit dans
# `runner/operations/triggers/loki/the_lantern_attack.py`, avec les triggers -- meme emplacement et
# meme cause que les phases 2 de 1069, 1141 et 1217 (#503-r3).
#
#: `EffectType.TheLantern_PendingTarget` -- la MARQUE, posee sur une ZONE DE TUILES.
TL_PENDING_TARGET = int(EffectType.TheLantern_PendingTarget)        # 0x4ab = 1195
#: `EffectType.Pinned` -- le MEME effet 27-like que posent CrushingClaws/ThunderousAssault.
TL_PINNED = int(EffectType.Pinned)                                  # 0x429 = 1065
#: `EffectType.TheLantern_PendingAttack` -- l'ARMEMENT de la phase 2, pose sur le CASTER.
TL_PENDING_ATTACK = int(EffectType.TheLantern_PendingAttack)        # 0x4aa = 1194
THE_LANTERN_ID = ActiveAbilityType.TheLantern.name                  # "TheLantern"


def the_lantern_area_selector(target_tile_id: int) -> TileUnique:
    """La ZONE de `IdunBattleLogic.Entities.Abilities.Active.Loki.TheLanternAbility$$ExecuteBehaviour`
    -- MIRROR 1:1, et la MEME chaine que republie
    `...TheLanternAbility$$GetTilesForTargetAreaFromTargetTile` (la face que lit le ciblage) :

        ring1  = SurroundingTiles(<+0x60> = Target, includeCenter = 0, range = 1,
                                  onlyMovable = 0, includeNonWalkable = 0)
        ring2  = SurroundingTiles(<+0x60>,          includeCenter = 0, range = 2, 0, 0)
        cring1 = SurroundingTiles(<+0x58> = CasterTiles, includeCenter = 0, range = 1, 0, 0)
        area   = Unique( (<+0x60> op_Addition ring1) op_Addition (ring2 op_BitwiseAnd cring1) )

    Le disque de rayon 1 autour de la TUILE CIBLEE, etendu aux tuiles a distance 2 de la cible qui
    sont ADJACENTES a l'empreinte du caster -- le « pont » entre Mortarion et la zone.

    TROIS points de transcription :

    * **`Target@+0x60` est ICI une TUILE** (le masque porte `TargetIsTile`) -> vehicule
      `FixedTileIds([target_tile_id])`, comme `SquigMineAbility` et `FragBomb`. `Target()` (domaine
      UNITE) rendrait `None` sur un cast tile-target.
    * **`includeNonWalkable = 0` ARME le filtre de marchabilite** (`checkWalkable =
      (includeNonWalkable == 0)`, cf. `SurroundingTiles`). Les deux booleens de queue sont LUS a la
      forme meme du decompile : l'octet bas des deux registres est mis a zero au call-site
      (`... << 8` / `... & 0xffffffffffffff00`), donc `onlyMovable = false` ET
      `includeNonWalkable = false`. Ce n'est PAS le defaut du noeud porte (`True`), et l'ecrire au
      defaut elargirait la zone aux tuiles non marchables.
    * **`Unique` est ici le PENDANT TILE** (`TileUnique`) : le natif n'a qu'un `DSLSelectors$$Unique`,
      le port en a deux ecritures parce que le domaine n'est pas type cote port -- `units.Unique`
      dedoublonne par id d'ENTITE et rendrait n'importe quoi sur des ids de tuile. Idem pour
      `op_Addition` (`TileUnion`) et `op_BitwiseAnd` (`TileIntersect`)."""
    tgt = FixedTileIds([int(target_tile_id)])                    # `<DSLSelectors+0x60>` = la TUILE
    ring1 = SurroundingTiles(tgt, Const(1), include_center=False, include_non_walkable=False)
    ring2 = SurroundingTiles(tgt, Const(2), include_center=False, include_non_walkable=False)
    cring1 = SurroundingTiles(CasterTile(as_ids=True), Const(1),
                              include_center=False, include_non_walkable=False)
    return TileUnique(TileUnion(TileUnion(tgt, ring1), TileIntersect(ring2, cring1)))


def the_lantern_tree(target_tile_id: int):
    """Arbre de `...TheLanternAbility$$ExecuteBehaviour` -- MIRROR 1:1 du DECOMPILE
    (build `rnca9r7q6c`) :

        area = <cf. `the_lantern_area_selector`>
        foes = DSLSelectors$$Enemies( of = <+0x48> = Caster, entities = area, selectionType = 3 )
        b1 = DSLBehaviors$$AddEffect( 0x4ab = 1195 TheLantern_PendingTarget,
                                      AActiveAbility$$get_AbilityStateReference(this),
                                      source = Caster@+0x48, targets = area,
                                      options = <Nullable ZEROEE> )
        b2 = DSLBehaviors$$AddEffect( 0x429 = 1065 Pinned, AbilityStateReference,
                                      source = Caster@+0x48, targets = foes,
                                      options = <Nullable ZEROEE> )
        b3 = DSLBehaviors$$AddEffect( 0x4aa = 1194 TheLantern_PendingAttack, AbilityStateReference,
                                      source = Caster@+0x48, targets = Caster@+0x48,
                                      options = <Nullable ZEROEE> )
        AActiveAbility$$Execute( (b1 op_BitwiseAnd b2) op_BitwiseAnd b3 )

    ZERO ATTAQUE : la surcharge appelee est
    `AddEffect(effectType, abilityState, source, targets, options)` (5 parametres, `options` =
    32 octets ZEROES sur la pile -- pas la surcharge `turns:IAmountFormula`), donc **aucune duree
    explicite** -> `duration_rounds=None` = `DefaultAmountOfRounds` de chaque effet, exactement
    comme le `Pinned` de `CrushingClaws`.

    `source_ref=Caster()` transcrit le 4e argument natif. Il coincide ici avec le defaut du port
    (`source = entities.caster`), mais on l'ecrit : c'est ce qui rend la ligne re-verifiable, et
    c'est ce champ que la PHASE 2 relit (`GetAttackingUnitSelector` surchargee en
    `EffectSource(Effect)`, cf. `triggers/pending_attack.py`).

    `scale_from_source` reste FAUX sur les trois : aucun des trois effets ne lit de `ConfigVar` cote
    port (1195 et 1194 sont des marqueurs, 1065 `Pinned` est un statut sans magnitude). Le degat,
    lui, est lu au tour SUIVANT par la phase 2, sur l'etat courant de l'attaquant.

    ⚠ **L'ORDRE `b1 & b2` EST LOAD-BEARING** : `foes` = `Enemies(Caster, area)` est evalue au
    moment ou `b2` s'execute, donc APRES que `b1` a pose la marque -- mais `area` est un selecteur
    GEOMETRIQUE, pas un `EntitiesWithAnyEffect` : les deux ensembles sont independants. Ce qui
    compte, et que le port preserve, c'est que `b2` frappe les ENNEMIS DU CASTER presents dans la
    zone AU CAST, la ou la phase 2 relira les occupants COURANTS des tuiles marquees."""
    area = the_lantern_area_selector(target_tile_id)
    foes = Enemies(area, selection_type=SELECTION)
    b1 = AddEffect(TL_PENDING_TARGET, EffectType.TheLantern_PendingTarget.name, area,
                   duration_rounds=None, source_ref=Caster())
    b2 = AddEffect(TL_PINNED, EffectType.Pinned.name, foes,
                   duration_rounds=None, source_ref=Caster())
    b3 = AddEffect(TL_PENDING_ATTACK, EffectType.TheLantern_PendingAttack.name, Caster(),
                   duration_rounds=None, source_ref=Caster())
    return op_and(op_and(b1, b2), b3)


class TheLanternAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.TheLanternAbility$$ExecuteBehaviour`
    (id 1094, `deathBossMortarion` « Mortarion » -- GUILD BOSS Death Guard, kind `npc`).
    Arbre DSL `the_lantern_tree`.

    ROUGE MESURE AVANT CE PORT : 1094 etait ABSENTE d'`ABILITY_CLASSES` -> `AbilityHandler`
    acceptait le cast, posait les flags de tour, et n'executait RIEN. Zero effet, zero degat, zero
    erreur -- un NO-OP SILENCIEUX, dont la face DECISION peut pourtant choisir l'ability.

    LE CAST NE FRAPPE PAS. Il pose `1195 TheLantern_PendingTarget` sur une ZONE DE TUILES,
    `1065 Pinned` sur les ennemis qui s'y trouvent, et `1194 TheLantern_PendingAttack` sur le
    CASTER. Le DEGAT appartient a la phase 2 (`1167 TheLantern_Attack`), qui part au debut du tour
    SUIVANT du caster et frappe les occupants COURANTS des tuiles marquees -- une unite qui sort de
    la zone y echappe, une unite qui y entre la prend.

    CONFRONTABILITE : porteur `npc`, monte comme ses deux voisins de kit (1093/1095) par
    `rl_duel build --explicit-stats "deathBossMortarion:<palier>"`.

    Turn-flags = defauts base (1094 ABSENT des overrides `NO_END_TURN_ABILITY_TYPES` /
    `NO_ABILITY_USED_FLAG_ABILITY_TYPES`) -> le cast termine le tour et pose `ActiveAbilityUsed`.

    Diag : `{posed: [...], area: [...], dsl: True}`."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.TheLantern)   # 1094
    ABILITY_ID = THE_LANTERN_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme **FLAGS DIRECTS** : le litteral EST le masque.
    # `...TheLanternAbility$$.ctor` appelle la surcharge a 6 parametres
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor(isSelfCasting, range, forceMeleeTarget,
    # rules, getDynamicInvalidCasterReason, getDynamicInvalidTargetReason)` -- signature LUE dans
    # `frida/methods.tsv`, forme tranchee par les XREFS ENTRANTES :
    #     TargetingOptions..ctor(&opts, 0, &CustomRange(2), 1, 0x2000100042, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2)                    // AbilityAttackType.Others
    # Decomposition du masque (COMPLETE : la somme des quatre bits REND le litteral) :
    #     0x2            TargetMatchesDynamicRule -> consulte `GetDynamicInvalidTargetReason`, que
    #                    la classe SURCHARGE (avec `$$IsValidCenterTileForTargetArea`).
    #                    **PORTE (#1030-r1, leve par #287-r11)** -- cf. la methode ci-dessous. Le
    #                    corps natif, VERBATIM :
    #                        A = battleQuery.<slot 0x51 GetAdjacentTiles>(casterTiles, 0, 1, 1)
    #                        B = battleQuery.<slot 0x4f GetAdjacentTiles>(targetTile, 0, 1, 1)
    #                        A.<ISet<T> slot 1>(B) ; return (A.Count == 1) ? 0 : 2
    #                    Les deux slots sont NOMMES par `metadata/interface_slots.tsv` (entree
    #                    VERSIONNEE, derivee du `global-metadata.dat`) : 0x51 = 81 est la surcharge
    #                    `from:IList<IEntity>`, 0x4f = 79 la surcharge `from:IEntity` -- les deux
    #                    d'arite 4, departagees par le TYPE DECLARE lu dans `frida/methods.tsv`, pas
    #                    par leur position. `$$GetDynamicInvalidTargetReason` a EXACTEMENT le meme
    #                    corps que `$$IsValidCenterTileForTargetArea` a l'encodage du retour pres.
    #     0x40           TargetIsTile             -> cast TILE-TARGET (`target_id` = id de TUILE)
    #     0x100000       AllowSteppableUnit       -> permissif
    #     0x2000000000   CasterHas7Tiles          -> Mortarion occupe 7 tuiles
    # `range` : `TargetingRange$$CustomRange(int range)` -- surcharge INT tranchee par XREF
    # ENTRANTE (`...TheLanternAbility$$.ctor` est appelante de la surcharge `range:System.Int32`,
    # ABSENTE de la liste des appelants de la surcharge `getRange:GetRange`), littéral **2** relu
    # aux octets du call-site (`mov edx, 2` juste avant le `call`).
    # `forceMeleeTarget = 1` = `RangedBool.False` (l'enum natif est INVERSE : True=0, False=1)
    # -> aucun clamp RangedInMelee.
    TARGETING_OPTIONS = TargetingOptions(
        rules=(TR.TargetMatchesDynamicRule | TR.TargetIsTile | TR.AllowSteppableUnit
               | TR.CasterHas7Tiles),
        self_cast=False, range=custom_range(2), force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id) -> int:
        """`...TheLanternAbility$$GetDynamicInvalidTargetReason` -- MIRROR du DECOMPILE :

            A = battleQuery.<IBattleQuery 81 GetAdjacentTiles>(casterTiles, onlyEmptyOrSteppable: 0,
                                                               onlyWalkableTiles: 1,
                                                               allowTemporary: 1)
            B = battleQuery.<IBattleQuery 79 GetAdjacentTiles>(targetTile,  0, 1, 1)
            A.<ISet<T> slot 1>(B)
            return (A.Count == 1) ? 0 : 2

        ⚠ LE SLOT 1 D'`ISet<T>` EST `IntersectWith`, ET C'EST UNE REFUTATION, PAS UN CHOIX. La
        fiche #1030-r1 laissait `ExceptWith` / `IntersectWith` non departagees et refusait d'ecrire
        -- a raison, tant que rien ne tranchait. Ce qui tranche :

          * `ExceptWith` est IMPOSSIBLE. `|A \\ B| >= |A| - |B|`, et `|B| <= 6` (B est le voisinage
            d'UNE tuile). Or `A` est le voisinage de l'empreinte SEPT tuiles du caster (le masque
            pose `CasterHas7Tiles`), donc `A` contient au minimum ces sept tuiles elles-memes --
            chacune est voisine d'une autre. Au regime nominal (plateau ouvert) `|A| = 19`, d'ou
            `|A \\ B| >= 13`, JAMAIS 1 : la regle refuserait TOUT cast, y compris ceux que le jeu
            execute (les effets 1194/1195 et la phase 2 existent et sont observes).
          * `IntersectWith` rend EXACTEMENT le predicat de l'i2. Texte verbatim de
            `Abilities/TheLantern_CurrentLevelDescription` : << Conjures a miasma of pestilence in
            **one of six directions** that fills a 3x3 hex area adjacent to Mortarion >>. Une tuile
            a distance 3 du centre ALIGNEE sur un axe n'a qu'UNE voisine a distance 2 (donc dans
            `A`) ; une tuile de milieu d'arete en a DEUX. `|A inter B| == 1` selectionne donc les
            six tuiles alignees -- les six directions, une pour une.

        Seconde source INDEPENDANTE de la premiere : l'une est geometrique, l'autre est le texte
        de l'ability. Les deux nomment le meme ensemble.

        Le code de refus est le `TargetingRule` brut `0x2` (`TargetMatchesDynamicRule`), comme dans
        tous les gates dynamiques du port.

        Cible non resolue / board absent -> `0` : la convention PERMISSIVE du module (on ne fabrique
        pas un refus sur un substrat non mesure)."""
        if target_id is None or getattr(state, "board", None) is None:
            return 0
        a = _targeting.get_adjacent_tiles(state, int(caster_id), False, True, True)
        b = _targeting.get_adjacent_tiles(state, target_id, False, True, True)
        if not a or not b:
            return 0                       # empreinte ou cible non resolue -> pas de refus invente
        # `A.IntersectWith(B)` puis `A.Count` : seul le CARDINAL est lu, donc l'ordre d'insertion
        # que preserve l'`OrderedSet` natif est sans effet ici.
        return 0 if len(set(a) & set(b)) == 1 else int(TR.TargetMatchesDynamicRule)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility`. 1094 pose `TargetIsTile` (0x40) dans son masque, donc
        # le role `target` du natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile
        # ou son occupant. `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` resout
        # AVANT ses deux gates : la resolution passe donc devant le garde `is None`, pas apres.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a deja
        # resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        tree = the_lantern_tree(int(target_id))
        tree.execute(entities, ectx)
        posed = [{"effect": p.get("effect_type"), "target": p.get("target"),
                  "source": p.get("source"), "placed": p.get("placed")}
                 for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "posed": posed,
                "area": [p.get("target") for p in posed
                         if p.get("effect") == TL_PENDING_TARGET],
                "pinned": [p.get("target") for p in posed if p.get("effect") == TL_PINNED],
                "dsl": True}
