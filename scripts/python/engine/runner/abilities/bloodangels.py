"""Abilities Blood Angels -- SavageEchoes (1230, Cezare `bloodTerminator`), HammerOfWrath (1153,
Mataneo `bloodIntercessor`, 2e section) et LightOfSanguinius (1177, Dante `bloodDante`, 3e section).

Module DEDIE (org native = 1 classe par ability, `Abilities.Active.Loki.*` ; `loki/` et `behaviours.py`
deja > seuil de split). RE ghidra gqfc5mff6c (VA citees). Case-220 §6.12 (docs/rl/case-220/blood-angels.md).

`IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE) :
    Execute( op_BitwiseAnd( op_BitwiseAnd(
        SetCache(cache),                                                                  # prime la memoisation
        AttackWithAttackDamage(Self@0x148, Target@0x178,
            GetDamage = Sum( MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                             Multiply( Get(GetVariableForLevel(config, 8 = extraDmg)),
                                       Count(CanAddUnit(AdjacentTiles(Self@0x148))) ) ),   # +extraDmg x free-tiles
            GetDamageProfile = Eviscerate, nrOfHits = ArmoriumCherubAbility.GetHits = GetNumberConstant(0x2f)=4) ),
        If( cache = Cache(HealthPctIsBelowOrEqual(Caster@0x160, ConfigConst(0x4f = healthPct = 50))),
            Heal(Self@0x148, Self@0x148, Get(GetVariableForLevel(config, 0x1d = hp)),
                 HealBehaviourOptions.ForRegenerate) ) ) )                                 # self-heal SI HP<=50%

Attaque MELEE (attackRangeType=Melee), 4 coups Eviscerate (PiercingRatio 50), degat = bornes minDmg/maxDmg
PLUS un bonus FLAT `extraDmg x count(tuiles adjacentes LIBRES du caster)` sur chaque coup. Si le HP du caster
etait <= 50% de son MaxHealth AVANT l'attaque, il se soigne de `hp` (variable per-niveau). REUTILISE
`ArmoriumCherubAbility.GetHits` (handler 1014) -- meme patron structurel (attaque multi-coups + volet).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import hexgeo

from ...dsl.base import AbilityTrigger, Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import op_add, op_and, If, AtomicGroup
from ...entities.selectors.accessors import FixedTiles, Owner, Target
from ...entities.selectors.tiles import AdjacentTiles, CanAddUnit, Caster
from ...entities.selectors.units import (AdjacentFriends, AdjacentUnits, Enemies, MechanicalUnits,
                                         Sub, SurroundingUnits, Union, UnitsWithoutTrait,
                                         non_steppable_or_object_units)
from ...entities.stats import StatType
from ...entities.traits.unit_trait import UnitTrait
from ...entities.abilities.active_ability import SavageEchoesAbility as SavageEchoesAbilityDecision
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from ...entities.triggers import HasEffect, IsAlive
from ..components import HealthComponent, PositionComponent, StatsComponent, UnitComponent
from .base import ActiveAbility
from . import targeting as _targeting   # FORME B : le binding de module garde un patch MORDANT
from .targeting import RANGE_ADJACENT, RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE, TargetingOptions
from .targeting_rule import TargetingRule as TR
from .behaviours.combat import AttackWithAttackDamage
from .behaviours.context import entities_from_state
from .behaviours.effects import AddEffect, AddStaticStatModifierEffect
from .behaviours.movement import FlyUnit, MoveUnit
from .behaviours.stats import Heal, SetHealth
from ...utilities.tile import first_tile_by_utility
from ...entities.unit_selection_type import UnitSelectionType

#: `UnitSelectionType` LU au dernier argument des `DSLSelectors$$*` de ce fichier -- releve
#: #585-r1, build `rnca9r7q6c`, littéral par littéral (JAMAIS par symetrie : deux call-sites
#: du releve passent `Any` parce que leur source est un ensemble de MORTS).
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3


if TYPE_CHECKING:
    from ..state import State

INFILTRATE_UNIT = int(EffectType.Infiltrate_UnitEffect)                  # 0x416=1046
HOW_CONDITIONAL_DAMAGE = int(EffectType.HammerOfWrath_ConditionalDamage)  # 0x534=1332


def _caster_level_mult(state: "State", caster_id: int):
    """`(active_ability_level, AbilityVariablesMultiplierPercentage)` du caster -- MEME source que
    `ability_attack_params` (`GetVariableForLevel(config, idx, level)` scale par le multiplier rarete)."""
    ce = state.get_entity(caster_id)
    sc = ce.get_component(StatsComponent) if ce is not None else None
    ctx = sc.ctx if sc is not None else None
    level = getattr(ctx, "active_ability_level", 0) if ctx is not None else 0
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    return level, mult


class _RegenerateCondition(AbilityTrigger):
    """Predicat FIGE (booleen pre-attaque) = fold de `SetCache(Cache(HealthPctIsBelowOrEqual(Caster@0x160,
    ConfigConst(0x4f = healthPct)))) IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$GetRegenerateCondition`. Le natif MEMOISE (`SetCache`) la condition au DEBUT du tree
    (avant l'attaque) et le `If(cache, Heal)` relit la valeur cachee -> on capture le booleen PRE-attaque
    dans `execute_behaviour` (plumbing pur, precedent SpiritLeech `SetCache`/`Cache` foldes). `Stat
    IdunBattle.Entities.Conditions.StatPercentageIsBelowOrEqualAbilityTrigger$$ShouldTrigger` = `(current/max) <= (healthPct/100)` en
    Fix64 (stat Health=5, variant 0=Current, variant 2=Maximum), equivalent entier EXACT
    `100*current <= healthPct*max` (cf. `_regenerate_precondition`)."""
    __slots__ = ("value",)

    def __init__(self, value: bool):
        self.value = bool(value)

    def should_trigger(self, ctx) -> bool:
        return self.value


def _regenerate_precondition(state: "State", caster_id: int) -> bool:
    """`HealthPctIsBelowOrEqual(Caster, ConfigConst(healthPct)) IdunBattle.Entities.Conditions.StatPercentageIsBelowOrEqualAbilityTrigger$$ShouldTrigger` evalue PRE-attaque : True ssi
    `current_hp / max_hp <= healthPct / 100`. Le HP courant vit dans `HealthComponent` (muté par les degats)
    -- `get_stat(Health, Current)` rendrait le HP INIT du snapshot (unit_context.py:108), donc on lit
    `HealthComponent` directement (== `SetHealth` @stats.py). Comparaison entiere exacte : pour des PV entiers,
    la division Fix64 `current/max` ne bascule JAMAIS `<= healthPct/100` autrement que `100*current <=
    healthPct*max` (granularite `1/(2*max)` >> precision Fix64 `2^-32`) -- egalite au bord `2*current == max`
    rendue Fix64 = 0.5 exact -> `<=` vrai."""
    ce = state.get_entity(caster_id)
    hc = ce.get_component(HealthComponent) if ce is not None else None
    if hc is None or hc.hp is None or not hc.hp_max:
        return False
    pct = ability_var("SavageEchoes", "healthPct", is_constant=True)   # ConfigConst(0x4f) = 50
    if pct is None:
        return False
    return 100 * int(hc.hp) <= int(pct) * int(hc.hp_max)


def savage_echoes_heal_amount(entities, ectx) -> int:
    """`Get(GetVariableForLevel(config, 0x1d = hp))` -- montant du `Heal(Self, ForRegenerate)`. `hp` = variable
    per-niveau (rarity-affected -> multiplier applique par `ability_var`). Montant FIXE (independant de
    l'attaque -- contraste avec le lifesteal `PercentageOf(LastAttackDamageMade)` de SpiritLeech)."""
    caster = (entities.caster or {}).get("id")
    if caster is None or ectx.state is None:
        return 0
    level, mult = _caster_level_mult(ectx.state, caster)
    return int(ability_var("SavageEchoes", "hp", level, multiplier_pct=mult) or 0)


def savage_echoes_tree(regenerate: bool, damage_override):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$ExecuteBehaviour` (id 1230, `bloodTerminator` Cezare -- MIRROR
    du DECOMPILE ; cf. en-tete module). Port (plain `Execute`, PAS `ExecuteAtomic`) :
        op_and( AttackWithAttackDamage(Target(), "SavageEchoes", "Eviscerate", melee, damage_override),
                If( _RegenerateCondition(regenerate), Heal(Caster(), savage_echoes_heal_amount) ) )
    - `SetCache`/`Cache(HealthPctIsBelowOrEqual)` FOLDES : la memoisation fige la condition HP<=50% PRE-attaque
      -> capturee en amont (`regenerate`), relue par le `If` (plumbing pur, precedent SpiritLeech).
    - le degat `Sum(MinMax, Multiply(extraDmg, count))` = un bonus FLAT `extraDmg x free-adjacent-tiles` ajoute
      a chaque coup, porte via `damage_override` (mirror `IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetAttackDamage`, meme point
      d'injection : le natif passe la node de degat calculee a `AttackWithAttackDamage`).
    - `native_factory="attack"` (defaut) : l'`IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$ExecuteBehaviour+0x21b appelle `DSLFactory.AttackWith
      AttackDamage IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (famille ATTACK, 2 tirages/coup a cc=0 -- verifie par XREFS, cas rngcrit-1202) ;
      IDENTIQUE au template ArmoriumCherub (IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$ExecuteBehaviour+0x17d -> IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage). Bit-exact multi-coups by construction.
    L'ordre `op_and` (Attack PUIS Heal) n'insere aucun tirage RNG hors l'attaque (Heal deterministe) ->
    l'ordre RNG de l'attaque est inchange."""
    attack = AttackWithAttackDamage(Target(), "SavageEchoes", "Eviscerate", is_melee=True,
                                    damage_override=damage_override, native_factory="attack")
    # `Heal(Self, Self, Get(hp), ForRegenerate)` -- `HealBehaviourOptions$$ForRegenerate` = `(scope 1,
    # removeEffects 0)`. La fabrique etait DEJA ecrite dans ce commentaire, et le port l'IGNORAIT :
    # jusqu'a #520 la feuille `Heal` n'avait aucun champ d'options, donc ce call-site tournait en
    # `scope 0` -- le cap de GROUPE `GetGroupUnitHealLimit` n'etait jamais consulte. Ecart observable
    # sur une cible MULTI-MEMBRES seulement (`nrOfMembers >= 2`) ; `bloodTerminator` en a 1, donc
    # l'ecart est nul sur le porteur, et le declarer est ce qui le garde vrai si le kit change.
    heal = Heal(Caster(), savage_echoes_heal_amount, scope=1, remove_effects=False)
    return op_and(attack, If(_RegenerateCondition(regenerate), heal))


class SavageEchoesAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$ExecuteBehaviour` (id 1230, `bloodTerminator` « Cezare »).

    Le behaviour est l'arbre DSL `savage_echoes_tree` : la feuille `AttackWithAttackDamage` emet la MEME
    Operation d'attaque d'ability (4 coups Eviscerate melee, degat + `extraDmg x free-tiles`) que le pipeline
    combat porte, et le `If(RegenCond, Heal)` pose un self-heal SI le HP etait <= 50% AVANT l'attaque (fige
    pre-attaque, mirror SetCache). Deterministe hors l'attaque -> bit-exact BY CONSTRUCTION vs l'imperatif."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SavageEchoes)   # 1230
    ABILITY_ID = "SavageEchoes"
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$.ctor` -- FORME
    # « PRESET STATIQUE » : AUCUN `TargetingOptions$$.ctor`, copie des 0x40 octets du preset
    # `<TargetingOptions statics>+0x40`. Masque = ce que
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` y ecrit :
    #   +0x40 isSelfCasting = 0
    #   +0x48 range <- `TargetingRange` statics+0x30 = RANGE_ADJACENT
    #   +0x60 forceMeleeTarget = 1 = RangedBool.False
    #   +0x68 rules = 0x4000 = TargetIsEnemy
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        level, mult = _caster_level_mult(state, caster_id)
        extra = int(ability_var("SavageEchoes", "extraDmg", level, multiplier_pct=mult) or 0)
        # `Count(CanAddUnit(AdjacentTiles(Owner@0x148)))` = nb de tuiles adjacentes LIBRES (walkable +
        # inoccupees) du porteur. Evalue au timing GetDamage (== l'appel unique de `damage_override` par le
        # leaf, AVANT la boucle de coups) : `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$GetDamage`
        # calcule les bornes UNE fois par cible (Calculate index 2=Min / 3=Max) -> `flat = extraDmg x count`
        # CONSTANT sur les 4 coups (== modele bornes-figees deja valide bit-exact multi-coups). `entities`
        # (LiveUnit) porte l'occupation PRE-attaque.
        # L'ARBRE vient de `SavageEchoesAbility.get_damage_formula` (entities/abilities) : DEFINITION UNIQUE
        # de `IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$GetDamage`, partagee avec la
        # face PREDICTION (`_savage_echoes_inputs`) -- un seul artefact natif, un seul port. Ici l'appelant
        # resout `MinMaxDamage` en la borne min PUIS la borne max (le natif fait de meme, Calculate 2 puis 3).
        free_sel = CanAddUnit(AdjacentTiles(Caster()))       # diag `free_tiles_after` uniquement

        def damage_override(_st, _caster, _target, bmin, bmax):
            return (int(SavageEchoesAbilityDecision.get_damage_formula(bmin, extra).evaluate(entities)),
                    int(SavageEchoesAbilityDecision.get_damage_formula(bmax, extra).evaluate(entities)))

        regenerate = _regenerate_precondition(state, caster_id)       # SetCache : fige HP<=50% pre-attaque
        savage_echoes_tree(regenerate, damage_override).execute(entities, ectx)
        main = next((p["attack"] for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        heal_amount, heals = 0, []
        for name, p in ectx.emitted:
            if name == "Heal":
                heal_amount = p.get("amount") or 0
                heals = p.get("heals") or []
        free_tiles = len(free_sel.evaluate(entities))                 # diag (POST-attaque : occupation a pu bouger)
        return {"ability": "SavageEchoes", "caster": caster_id, "target": target_id,
                "main_attack": main, "regenerate": regenerate, "extra_per_tile": extra,
                "free_tiles_after": free_tiles, "heal_amount": heal_amount, "heals": heals, "dsl": True}


# ====================== HammerOfWrath (bloodIntercessor «Mataneo», actif 1153) ======================
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$ExecuteBehaviour` (MIRROR du
# DECOMPILE, build gqfc5mff6c) :
#
#   Execute( op_BitwiseAnd( op_BitwiseAnd(
#       AddEffect( 0x416 = Infiltrate_UnitEffect, AbilityStateReference,
#                  source = Self@0x148, cible = Self@0x148, duree = Direct(1)@dsl+0xc0 ),      # [1]
#       MoveUnit( caster@0x160,                                                                 # [2] CHARGE
#           First( SortTilesByUtility(
#                    Filter( CanAddUnit(AdjacentTiles(target@0x178)),
#                            NOT( AmountIsGreater( MinDistance(It@0x180, CasterTiles@0x170),
#                                                  Get(GetNumberConstant(0x16 = range)) ) ) ),
#                    caster@0x160, UtilityDefinition(7 = Tile) ), 1 ),
#           <options ZEROEES> ) ),
#       If( IsAlive(caster@0x160),
#           AtomicGroup( 0x1d, op_BitwiseAnd(
#               AttackWithAbilityDamage( caster@0x160, target@0x178, GetDamage,                  # [3]
#                   Nullable(GetDamageProfile()) = Power, GetHits() = GetNumberConstant(0x2f) = nrOfHits,
#                   AbilityOrEffect(this@+0x10 = 1153) ),
#               AttackWithAbilityDamage( caster@0x160, GetAdjacentTargets, GetDamage2,           # [4]
#                   Nullable(GetDamageProfile2()) = Physical,
#                   GetHitsToBonusTarget() = GetNumberConstant(0x32 = nrOfHits_2),
#                   AbilityOrEffect(this@+0x10 = 1153) ) ) ) ) ) )
#
# avec (fonctions natives NOMMEES, decompilees une a une) :
#   * `HammerOfWrathAbility$$GetDamage`  = ConditionalAmount( GetDoubleCondition,
#                                              Multiply(MinMaxDamage,  Get(2)), MinMaxDamage )
#   * `HammerOfWrathAbility$$GetDamage2` = ConditionalAmount( GetDoubleCondition,
#                                              Multiply(MinMaxDamage2, Get(2)), MinMaxDamage2 )
#   * `HammerOfWrathAbility$$GetDoubleCondition`  = HasEffect(Self@0x148, 0x534, activeOnly=1, flags=6)
#   * `HammerOfWrathAbility$$GetAdjacentTargets`  = Enemies(caster@0x160, AdjacentUnits(target@0x178, 1))
#   * `GetHits` / `GetHitsToBonusTarget` : corps DEDUPLIQUES IL2CPP (ghidra les affiche
#     `ArmoriumCherubAbility$$GetHits` / `BringerOfDespairAbility$$GetHitsToBonusTarget`) =
#     `GetNumberConstant(0x2f)` et `GetNumberConstant(0x32)` -- la STRUCTURE est lue, jamais le nom.
#
# Le `Multiply(MinMaxDamage, 2)` DOUBLE LES BORNES (pas la valeur tiree) : `IdunBattle.Entities.
# Behaviours.AbilityDamageBehaviour$$GetDamage` teste si le node de degat implemente l'interface
# min/max et, si oui, appelle ses slots `CalculateMin`/`CalculateMax` -- or `IdunBattle.Entities.
# Formulas.MultiplyAmount` et `ConditionalAmount` implementent TOUS DEUX ces slots (symboles
# `MultiplyAmount$$CalculateMin/Max`, `ConditionalAmount$$CalculateMin/Max`) et delegguent a leurs
# operandes. Le port double donc `(bmin, bmax)` via `damage_override`.
#
# `HammerOfWrath_ConditionalDamage` (0x534=1332) est un OWNER-EFFECT permanent pose a l'INIT de
# l'ability par la triggered 1258 (`AOwnerEffectTriggeredAbility$$CreateBehaviour` =
# `If(<cond>, AddEffect(effectType, AbilityState(owner), owner, owner, <duree ZEROE>))`, trigger
# `OnOwnerSpecificAbilityInit`), dont l'ACTIVE-CONDITION est
# `IdunBattle.Entities.Effects.Loki.HammerOfWrath_ConditionalDamageEffect$$CreateActiveCondition` =
# `HealthPctIsBelowOrEqual(Self@0x148, ConfigConst(1153, Self, 0x4f = healthPct))`. C'est le MEME
# patron qu'`AnvilShield_BlockChanceBelowHealthCap` : l'entite-effet existe en permanence, seul son
# flag `IsActive` bascule -> cf. `entities/effects/loki/status.py` + `ABILITY_INIT_OWNER_EFFECTS`.
#
# RESIDU NOMME (hors perimetre de CE port) : le passif `AggressiveOnslaught` (triggered 1248) invoque
# 2 `bloodSmnIntercessor` quand Mataneo CHARGE. Son trigger est
# `On(0xb = UnitAbility) & OwnerIsCaster & (IsPersistentData | IsCharging(caster, target))`
# (`AggressiveOnslaught_SummonAbility$$CreateTrigger`) -- `On(0xb)` est emis par
# `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` **APRES** l'execution de la
# behaviour, donc APRES les deux volets d'attaque : le flux `state.rng` des coups de HammerOfWrath
# n'est PAS pollue par le summon. La face COMBAT du summon n'est pas portee (seule sa face DECISION
# l'est, `playbook/aggressive_onslaught.py`).


def hammer_of_wrath_get_double_condition() -> HasEffect:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$GetDoubleCondition` — MIRROR :
    `HasEffect(Self@0x148, 0x534 = HammerOfWrath_ConditionalDamage, activeOnly = 1, sourceFlags = 6)`.
    Pour une ability ACTIVE, `Self@0x148` == le caster -> `Caster()`. `active_only=True` (defaut du port
    == le `1` natif) fait respecter l'`ActiveCondition` de l'effet (HP% <= healthPct)."""
    return HasEffect(Caster(), HOW_CONDITIONAL_DAMAGE)


def hammer_of_wrath_get_adjacent_targets() -> Enemies:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$GetAdjacentTargets` — MIRROR :
    `Enemies( caster@0x160, AdjacentUnits(target@0x178, 1) )` = les unites d'equipe != celle du caster a
    distance hex 1 de la CIBLE (la cible elle-meme exclue, `_within` d>0). i2 : « 1x ... Physical Damage
    to all enemies adjacent to it »."""
    return Enemies(AdjacentUnits(Target(), Const(1)))


def _how_pos_of(state: "State", uid: int):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _how_occupied_positions(state: "State") -> set:
    """Occupation LIVE (unites VIVANTES) — `CanAddUnit` natif teste le CONTENU de tuile."""
    occ: set = set()
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None or (uc is not None and not uc.alive):
            continue
        occ.add((pc.col, pc.row))
    return occ


def charge_dest_tile(state: "State", caster_id: int, target_id: int, ability_id: str):
    """COLLAPSE (doctrine slice-18/19) du selecteur de destination de la charge, mirror du DECOMPILE :

        First( SortTilesByUtility(
                 Filter( CanAddUnit(AdjacentTiles(target@0x178)),
                         NOT( AmountIsGreater( MinDistance(It@0x180, CasterTiles@0x170),
                                               Get(GetNumberConstant(0x16 = range)) ) ) ),
                 caster@0x160, UtilityDefinition(7 = Tile) ), 1 )

    -> tuile LIBRE + marchable ADJACENTE a la cible, a distance hex <= `range` de la tuile du caster,
    la PLUS PROCHE du caster (tie-break id de tuile). i2 : « charges an enemy target that has a free
    adjacent hex within movement range 5 ».

    FOYER PARTAGE PAR DEUX ARTEFACTS NATIFS DISTINCTS, terme a terme IDENTIQUES (#510) :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$ExecuteBehaviour` (1153,
    `bloodIntercessor`) et `IdunBattleLogic.Entities.Abilities.Active.LightOfSanguiniusAbility$$Execute
    Behaviour` (1177, `bloodDante`) construisent la MEME chaine de noeuds -- meme `Filter`, meme
    `MinDistance(It@0x180, CasterTiles@0x170)`, meme `GetNumberConstant(0x16 = range)`, meme
    `SortTilesByUtility(..., caster@0x160, 7 = Tile)`, meme `First(..., 1)`. Seule la CONFIG lue
    change, d'ou le parametre `ability_id` (`range` vaut 5 pour les DEUX au gameconfig, mais c'est
    une coincidence de valeur, pas une donnee partagee). Les deux `GetDynamicInvalidTargetReason`
    natifs sont d'ailleurs, eux aussi, le meme predicat (`ability_range.GATE_FREE_ADJACENT_IN_
    CONFIG_RANGE` les range ensemble).

    `MinDistance(It, CasterTiles)` = distance HEX (pas une longueur de chemin) entre la tuile candidate
    et la tuile du caster (`@0x170` = `CasterTiles`, cf. `RadSaturationAbility$$CreateBehaviour`).

    `SortTilesByUtility(sel, caster@0x160, UtilityDefinition(7 = Tile))` ->
    `IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select` = tri DECROISSANT par
    `IdunBattleLogic.AI.Utilities.UtilityDecider$$CalculateUtility` sur le composite **Tile(7)**, DEJA
    PORTE. Appel du FOYER UNIQUE `engine/utilities/tile.py::first_tile_by_utility` (#165) au lieu du
    collapse « la plus proche du caster » : sur une carte plate toutes les feuilles rendent 0 sauf
    `ElevationUtility` (BC `Elevation.Multiplier=10`, `HighestElevation=+10`, `LowestElevation=-5`), et
    c'est PRECISEMENT elle qui tranche.

    ⚠ MESURE (#226, MC1_67, Mataneo @(4,7), cible necroWarden @(6,7)) : les deux tuiles libres du
    ring-1 sont (5,7) elev 1 (a distance 1 du caster) et (6,6) elev **2** (a distance 2) — le natif
    charge sur **(6,6)** (`Unit_Foot_Tile_Id_1 = 72`), donc SUR LA PLUS ELEVEE, pas sur la plus proche.
    C'est cette mesure qui a REFUTE le collapse « plus proche » ; les ports freres
    (`SkyStrikeAbility$$ExecuteBehaviour`, `HeroicFusilladeAbility$$ExecuteBehaviour`,
    `ForwardSpotterAbility$$PickTiles`) sont de-forkes sur le meme foyer depuis #165.

    Le tri est STABLE sur l'ordre du SELECTEUR : `AdjacentTiles(target)` =
    `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` -> `BattleQuery$$GetAdjacentTiles`,
    donc `board.neighbours_native` (liste d'adjacence STOCKEE, ni triee ni symetrisee — cf. la docstring
    de `Board.neighbours_native` : ordre etabli case-130 SS5 / #117 / FragBomb). C'est lui qui donne le
    tie-break quand les utilites sont EGALES (carte plate). Renvoie (col,row) ou None (aucune tuile ->
    `MoveUnitBehaviour` no-op, garde `local_308 == 0`)."""
    board = state.board
    cpos = _how_pos_of(state, caster_id)
    tpos = _how_pos_of(state, target_id)
    if board is None or cpos is None or tpos is None:
        return None
    ttile = board.id_at(tpos[0], tpos[1])
    if ttile is None:
        return None
    rng_max = ability_var(ability_id, "range", is_constant=True)        # GetNumberConstant(0x16) = 5
    occ = _how_occupied_positions(state)
    cands = []
    for t in board.neighbours_native(ttile):               # AdjacentTiles(target) — ORDRE DU SELECTEUR
        pos = board.coord(t)
        if pos in occ or not board.walkable(t):            # CanAddUnit : tuile LIBRE et marchable
            continue
        if rng_max is not None and hexgeo.distance(cpos, pos) > int(rng_max):
            continue                                       # Filter(NOT(AmountIsGreater(MinDistance, range)))
        cands.append(t)
    # `caster@0x160` = `dc.units` (case-165b) : les feuilles gatees sur l'unite le voient. Mataneo
    # n'a AUCUN playbook de mouvement enregistre -> terme nul, et la mesure #226 ci-dessus (natif
    # (6,6), la plus ELEVEE) reste expliquee par la seule feuille Elevation. C'est le TEMOIN qui
    # attribue le residu #165 §4 au KIT DU CASTER : meme board, meme cible (6,7), meme couple de
    # tuiles candidates, mais un caster SANS `GeminaeSuperia` -> le natif y suit l'elevation.
    best = first_tile_by_utility(state, cands, unit_id=caster_id)   # First(SortTilesByUtility(...), 1)
    return board.coord(best) if best is not None else None


def hammer_of_wrath_dest_tile(state: "State", caster_id: int, target_id: int):
    """Destination de la charge de `HammerOfWrathAbility$$ExecuteBehaviour` (1153) -- l'appel du foyer
    `charge_dest_tile` avec la config `HammerOfWrath`. Chemin INCHANGE (meme corps, meme `range`)."""
    return charge_dest_tile(state, caster_id, target_id, "HammerOfWrath")


def hammer_of_wrath_tree(dest, damage_override):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$ExecuteBehaviour`
    (id 1153, `bloodIntercessor` « Mataneo » — MIRROR 1:1 ; cf. le bloc de decompile en tete de section) :

        op_and( op_and( AddEffect(Infiltrate_UnitEffect, Caster(), duree = 1 TOUR),
                        MoveUnit(Caster(), FixedTiles([dest])) ),
                If( IsAlive(Caster()),
                    AtomicGroup( op_and( AttackWithAttackDamage(Target(), Power, nrOfHits),
                                         AttackWithAttackDamage(GetAdjacentTargets, Physical,
                                                                nrOfHits_2, multi=True) ) ) ) )

    ORDRE natif : Infiltrate -> CHARGE -> (attaque principale -> attaque des adjacents). La charge
    precede les attaques, donc la position du caster au moment du degat est celle D'ARRIVEE (elevation
    et adjacence lues post-move) ; le selecteur `GetAdjacentTargets` est evalue A L'ATTAQUE.

    `native_factory="ability"` pour les DEUX volets : `HammerOfWrathAbility$$ExecuteBehaviour` appelle
    `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` (famille ABILITY ->
    `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHits` : 1 tirage/coup, aucun crit, aucune
    feuille positionnelle) — classe PAR LE DECOMPILE, jamais au juge. La classe Python porte le nom
    `AttackWithAttackDamage` (mode BORNES) et c'est son flag `native_factory` qui designe l'Operation,
    == le port SpiritLeech (1104), meme situation.

    `duration_turns=1` pour l'Infiltrate : le 6e argument natif est le noeud `Direct(1)` du DSLFactory
    (`dsl+0xc0`), DEJA en TOURS — pas un `TurnsFromRounds` (contraste Foehammer). i2 : « gains Infiltrate
    until the end of this turn ».

    `Infiltrate_UnitEffect` (1046) n'a pas de classe d'effet portee -> `BaseEffect` nu (effet PRESENT,
    sans contribution) : degradation fidele §17.4. Il ne porte aucun terme de degat.

    `AtomicGroup` = pass-through d'execution cote port (RE #201) ; il est conserve pour le mirror
    STRUCTUREL. Aucun `KillDeadUnits` dans ce natif."""
    infiltrate = AddEffect(INFILTRATE_UNIT, "Infiltrate_UnitEffect", Caster(),
                           duration_rounds=None, duration_turns=1)      # Direct(1)@dsl+0xc0 = 1 TOUR
    move = MoveUnit(Caster(), FixedTiles([dest] if dest is not None else []))
    main = AttackWithAttackDamage(Target(), "HammerOfWrath", "Power", is_melee=True,
                                  damage_override=damage_override,
                                  native_factory="ability",   # -> `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage`
                                  ability_type=int(ActiveAbilityType.HammerOfWrath))
    adjacent = AttackWithAttackDamage(hammer_of_wrath_get_adjacent_targets(), "HammerOfWrath",
                                      "Physical", is_melee=True, multi=True,
                                      min_key="minDmg_2", max_key="maxDmg_2", hits_key="nrOfHits_2",
                                      damage_override=damage_override,
                                      native_factory="ability",
                                      ability_type=int(ActiveAbilityType.HammerOfWrath))
    return op_and(op_and(infiltrate, move),
                  If(IsAlive(Caster()), AtomicGroup(op_and(main, adjacent))))


class HammerOfWrathAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$ExecuteBehaviour` (id 1153,
    `bloodIntercessor` « Mataneo », Blood Angels) — cf. `hammer_of_wrath_tree()`.

    i2 : « If Mataneo has not moved, he gains Infiltrate until the end of this turn, charges an enemy
    target that has a free adjacent hex within movement range 5, dealing 2x <dmg> Power Damage to the
    target and 1x <dmg> Physical Damage to all enemies adjacent to it. If Mataneo is at or below 50%
    Health, doubles the damage dealt by this ability. »

    ⚠ le « If Mataneo has not moved » de l'i2 n'est PAS une branche de l'`ExecuteBehaviour` (l'`AddEffect`
    Infiltrate y est INCONDITIONNEL, lu au decompile) : c'est une condition de la couche de ciblage/UI, hors
    de la face COMBAT. Le port mirror le DECOMPILE.

    Turn-flags = defauts base (1153 ABSENT des overrides `NO_END_TURN`/`NO_ABILITY_USED_FLAG`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HammerOfWrath)   # 1153
    ABILITY_ID = "HammerOfWrath"

    # GATE DE CIBLE (#115). `HammerOfWrathAbility$$.ctor` n'appelle PAS `TargetingOptions..ctor` : il
    # COPIE VERBATIM un PRESET statique de `IdunBattle.Core.Services.TargetingOptions` (struct 0x40 aux
    # champs statiques `+0x240..0x27f`) puis `AActiveAbility..ctor(this, &opts, 0)`. Masque EFFECTIF LU
    # dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` : `*(statics + 0x268) = 0x102004032`
    # (0x268 = 0x240 + 0x28 = le champ `rules`). Aucun flag OR'e apres la copie -> le preset EST le
    # masque (ce n'est PAS l'overload « preset + flags »). Decomposition :
    #     0x2         TargetMatchesDynamicRule  -> PORTE (`get_dynamic_invalid_target_reason` ci-dessous)
    #     0x10        CasterHasNotMoved         -> PORTE (volet CASTER, `get_invalid_caster_reason`) ;
    #                                              c'est le « If Mataneo has not moved » de l'i2
    #     0x20        TargetHasFreeAdjacentTile -> SUBSUME par la regle dynamique (qui teste le MEME
    #                                              predicat PLUS la contrainte de portee) ; le volet
    #                                              statique reste non porte (cf. `targeting.py`)
    #     0x4000      TargetIsEnemy             -> PORTE
    #     0x2000000   AllowObscuredTargetByElevation -> permissif (aucune contrainte portee ici)
    #     0x100000000 TargetIsNotAdjacent       -> PORTE (#243 ; battleQuery slot 0x61) : la cible
    #                                              DEJA au contact est refusee, AVANT la regle
    #                                              dynamique ci-dessous
    # PORTEE (#241) : le preset `TargetingOptions` statique `+0x240` embarque le
    # `TargetingRange` statique `+0x48` = `useWholeBoard` -> AUCUN test de portee dans le
    # filtre statique. La constante `HammerOfWrath.constants.range` (5) n'est donc PAS la
    # portee de ciblage : elle est consommee ailleurs, pas par `TargetingQuery$$GetRange`.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.CasterHasNotMoved
        | TR.TargetHasFreeAdjacentTile
        | TR.TargetIsEnemy
        | TR.AllowObscuredTargetByElevation
        | TR.TargetIsNotAdjacent
    ), range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$GetDynamicInvalidTargetReason`
        — MIRROR du decompile :

            dc.ability = this ; dc.target = <cible> ; dc.range = GetNumberConstant(config, 0x16)
            tiles = battleQuery.<slot 0x52>(casterTiles)
            return (tiles != null && Enumerable.Any(tiles, dc.<lambda>)) ? 0 : 0x20

        `0x20` = `TargetingRule.TargetHasFreeAdjacentTile` — et c'est EXACTEMENT le predicat que
        l'`ExecuteBehaviour` re-utilise pour choisir sa tuile de charge
        (`Filter(CanAddUnit(AdjacentTiles(target)), NOT(AmountIsGreater(MinDistance(It, CasterTiles),
        Get(range))))`). On mirror donc en REUTILISANT le meme selecteur (`hammer_of_wrath_dest_tile`) :
        s'il ne rend AUCUNE tuile, la cible est refusee. i2 : « charges an enemy target **that has a
        free adjacent hex within movement range 5** ».

        GROUND TRUTH LIVE (#226, MC1_67) : sur un necroWarden dont TOUTES les tuiles ring-1 sont
        occupees, `abilityTargets(...).fromHere` EXCLUT la cible cote natif — et l'inclut des qu'une
        tuile se libere (mesure : deplacer u81 hors de (5,8) rend u77 ET u81 legaux d'un coup).
        Cible/caster non resolvables -> 0 (permissif, jamais de refus invente).

        ###### LE REFUS A d=1 : `TargetIsNotAdjacent`, PORTE DEPUIS #243 (residu #226 ferme) ######
        MESURE (#226, meme runner, u83 DEPLACE autour de Mataneo @(4,7), 3 ennemis ecartes du champ) :
            d=1 @(4,8) refuse · d=1 @(5,7) refuse · d=2 @(6,6) accepte · d=2 @(2,7) accepte
            d=3 @(1,7) accepte · d=4 @(0,7) accepte · d=6 @(0,3) accepte
        La bande acceptee est donc `d >= 2` (et PAS `d <= range` : d=6 passe, parce que la contrainte
        `MinDistance(tuile, CasterTiles) <= range` porte sur la TUILE de charge, pas sur la cible).
        AUCUNE lecture de la lambda ci-dessus ne produit ce refus a d=1 (a d=1 les tuiles libres du
        ring-1 de la cible sont a distance <= 2 du caster, donc `Any` est VRAI). Le refus vient d'un
        AUTRE etage de la cascade statique — l'hypothese `TargetIsNotAdjacent` a ete CONFIRMEE au
        decompile (#243) : le bit 32 gate `battleQuery.<slot 0x61>(targetTiles, casterTiles)` et
        rompt sur l'ADJACENCE. Il est desormais porte dans le maillon GENERIQUE (`targeting.py`),
        pas ici : c'est une regle PARTAGEE, que `WaaaghAbility` (l'autre ability de CHARGE portee)
        porte aussi. Ordre natif : le bit 32 est evalue AVANT cette regle dynamique, donc une cible
        adjacente rend `TargetIsNotAdjacent` et non `TargetHasFreeAdjacentTile`."""
        if target_id is None:
            return 0
        dest = hammer_of_wrath_dest_tile(state, int(caster_id), int(target_id))
        return 0 if dest is not None else int(TR.TargetHasFreeAdjacentTile)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        cond = hammer_of_wrath_get_double_condition()

        def damage_override(_st, _caster, _target, bmin, bmax):
            # `ConditionalAmount(GetDoubleCondition, Multiply(node, Get(2)), node)` — le predicat est
            # RELU a chaque `GetDamage` (noeud lazy, `entities` = vue LiveUnit) ; `Multiply` double les
            # DEUX bornes (`MultiplyAmount$$CalculateMin`/`$$CalculateMax` compositionnels).
            return (2 * bmin, 2 * bmax) if cond.evaluate(entities) else (bmin, bmax)

        dest = hammer_of_wrath_dest_tile(state, caster_id, target_id)   # collapse SortTilesByUtility+First
        doubled = bool(cond.evaluate(entities))                          # diag (etat PRE-charge)
        hammer_of_wrath_tree(dest, damage_override).execute(entities, ectx)
        main_attack, splash, moved_to = None, [], None
        for name, p in ectx.emitted:
            if name == "MoveUnit":
                moved_to = p.get("to") if p.get("moved") else None
            elif name == "AttackWithAttackDamage":
                if p.get("target") == target_id and main_attack is None:
                    main_attack = p.get("attack")            # volet PRINCIPAL (1er emis)
                else:
                    splash.append({"target": p.get("target"), "attack": p.get("attack")})
        return {"ability": "HammerOfWrath", "caster": caster_id, "target": target_id,
                "main_attack": main_attack, "splash": splash, "moved_to": moved_to,
                "dest": dest, "doubled": doubled, "dsl": True}


# ====================== LightOfSanguinius (bloodDante «Dante», actif 1177) ==========================
#
# `IdunBattleLogic.Entities.Abilities.Active.LightOfSanguiniusAbility$$ExecuteBehaviour` -- MIRROR 1:1
# du DECOMPILE (build `rnca9r7q6c`), terme a terme et dans l'ORDRE des `op_Addition` du natif.
# ⚠ La classe est hors namespace `Loki` (contraste `HammerOfWrathAbility`), et le module natif des
# slots de role est `IdunBattleLogic.Entities.DSLSelectors` / `DSLFormulas` / `DSLTriggers` /
# `DSLBehaviors` (le contexte `this@+0x30` porte `+0x78 Behaviors · +0x80 Formulas · +0x88 Triggers ·
# +0x90 Selectors`) :
#
#   infiltrate = AddEffect( 0x416 = Infiltrate_UnitEffect, AbilityStateReference,
#                           source = Owner@Selectors+0x30, targets = Owner@+0x30,
#                           turns  = <DSLFormulas+0x20> = Direct(1) )                        # [1]
#   tuiles     = First( SortTilesByUtility(
#                         Filter( CanAddUnit(AdjacentTiles(Target@+0x60)),
#                                 NOT( AmountIsGreater(
#                                        MinDistance(ActiveTarget@+0x68, CasterTiles@+0x58),
#                                        ConfigConst(0x16 = range) ) ) ),
#                         Caster@+0x48, UtilityDefinition(7 = Tile) ), 1 )
#   vol        = FlyUnit( Caster@+0x48, tuiles )                                             # [2]
#   attaque    = AttackWithAttackDamage( Caster@+0x48, Target@+0x60,
#                    MinMaxDamage(abilityState), Nullable(GetDamageProfile()) = Melta,
#                    GetHits() = nrOfHits, AbilityOrEffect(this), <options ZERO>, 2 )        # [3]
#   aura       = AddEffect( 0x560 = LightOfSanguinius, AbilityStateReference,
#                    source  = Owner@+0x30,
#                    targets = op_Addition( Target@+0x60,
#                                NonSteppableOrObjectUnits(
#                                  Enemies( Owner@+0x30,
#                                    SurroundingUnits(Target@+0x60, ConfigConst(0x44 = range_2),
#                                                     unique: 1, includeCenter: 0, 3), 3), 3) ),
#                    turns   = TurnsFromRounds(ConfigConst(0x45 = nrOfRounds)) )             # [4]
#   Execute( op_Addition( op_Addition(infiltrate, vol),
#                         IfAlive(Owner@+0x30, op_Addition(attaque, aura)) ) )
#
# `IfAlive(selector, ifBehaviour, else)` = `IdunBattleLogic.Entities.DSLBehaviors$$IfAlive`, dont le
# corps est litteralement `If(DSLTriggers.IsAlive(selector), ifBehaviour, elseBehaviour)` -- meme
# forme que le `If(IsAlive(caster), ...)` de HammerOfWrath, et meme place : APRES le deplacement,
# AVANT l'attaque (« le porteur a-t-il SURVECU au vol ? », overwatch/pieges de la charge).
#
# TROIS LECTURES QUE LE DECOMPILE IMPOSE :
#  * `FlyUnit`, PAS `MoveUnit` (contraste 1153) : `DSLBehaviors$$FlyUnit` pose `Nullable(3)` dans les
#    options du `MoveUnitBehaviour` -- le chemin est calcule par le `FlyPathfinder` et `movementSteps`
#    devient la DISTANCE (cf. `behaviours/movement.py::FlyUnit`, qui NOMME deja ce call-site).
#  * la famille de degat est ATTACK (`DSLBehaviors$$AttackWithAttackDamage`, surcharge 9 arguments),
#    donc `native_factory="attack"` : crit/block et 2 tirages par coup -- ce n'est PAS
#    `AttackWithAbilityDamage` comme les deux volets de 1153.
#  * l'`AddEffect` de l'aura est DANS la branche `IfAlive`, APRES l'attaque : un Dante mort au vol ne
#    pose NI degat NI debuff.
#
# i2 (`Abilities/LightOfSanguinius_CurrentLevelDescription`) : « If Dante has not moved, he gains
# Infiltrate until the end of this turn, then charges an enemy target that has a free adjacent hex
# within movement range {range} and deals {nrOfHits}x {minDmg}-{maxDmg} Melta Damage to it. The target
# and enemy units surrounding it deal -{dmgReductionPct}% Damage for {nrOfRounds} round. This effect is
# doubled if they attack friendly units that are at or below {healthPct}% Health. »
# ⚠ comme chez 1153, le « If Dante has not moved » n'est PAS une branche de l'`ExecuteBehaviour` :
# c'est le bit `CasterHasNotMoved` du masque de ciblage.
#
# Le volet « -dmgReductionPct % de degat, double sous healthPct » vit ENTIEREMENT dans l'effet 1376
# (`IdunBattle.Entities.Effects.Loki.LightOfSanguinius_DamageReductionEffect$$CreateDamageModifier`),
# porte SEPAREMENT dans `entities/effects/loki/damage_reduction.py` -- la feuille DSL ci-dessous ne
# fait que le POSER (frontiere behaviour / `ApplyModification`, doctrine #149).

LIGHT_OF_SANGUINIUS = int(EffectType.LightOfSanguinius)                  # 0x560=1376


def light_of_sanguinius_dest_tile(state: "State", caster_id: int, target_id: int):
    """Destination du VOL de `LightOfSanguiniusAbility$$ExecuteBehaviour` (1177) -- l'appel du foyer
    `charge_dest_tile` avec la config `LightOfSanguinius` (`GetNumberConstant(0x16 = range)` = 5)."""
    return charge_dest_tile(state, caster_id, target_id, "LightOfSanguinius")


def light_of_sanguinius_aura_targets():
    """Selecteur-cible de l'`AddEffect(0x560)` -- MIRROR du decompile :

        op_Addition( Target@+0x60,
                     NonSteppableOrObjectUnits(
                       Enemies( Owner@+0x30,
                                SurroundingUnits(Target@+0x60, ConfigConst(0x44 = range_2),
                                                 unique: 1, includeCenter: 0, 3), 3), 3) )

    -> la CIBLE, plus les ennemis (equipe != celle de l'Owner) a distance hex <= `range_2` d'elle,
    Steppable et Object exclus. i2 : « The target and enemy units surrounding it ».

    `Enemies(of = Owner@+0x30, ...)` : le port lit l'equipe de `ctx.caster` (`selectors/units.py`), et
    pour une ability ACTIVE `Owner@+0x30` EST le caster -- meme collapse que partout ailleurs.
    `includeCenter = 0` : la cible n'est pas re-comptee par le voisinage (elle arrive par le premier
    operande du `op_Addition`, donc UNE fois -- l'`AddEffect` natif itere son selecteur et
    `AddEffectOperation` ne re-pose pas un effet deja present).
    `range_2` absent du gameconfig -> `Const(0)` : rayon nul = aucun voisin, jamais un rayon invente."""
    r2 = ability_var("LightOfSanguinius", "range_2", is_constant=True)   # ConfigConst(0x44) = 1
    voisins = SurroundingUnits(Target(), Const(int(r2 or 0)), include_center=False)
    return Union(Target(), non_steppable_or_object_units(Enemies(voisins)))


def light_of_sanguinius_tree(dest, rounds):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.LightOfSanguiniusAbility$$ExecuteBehaviour`
    (id 1177, `bloodDante` « Dante ») -- MIRROR 1:1 ; cf. le bloc de decompile en tete de section :

        op_and( op_and( AddEffect(Infiltrate_UnitEffect, Owner(), duree = 1 TOUR),
                        FlyUnit(Caster(), FixedTiles([dest])) ),
                If( IsAlive(Owner()),
                    op_and( AttackWithAttackDamage(Target(), Melta, nrOfHits),
                            AddEffect(LightOfSanguinius, aura_targets,
                                      duree = TurnsFromRounds(nrOfRounds)) ) ) )

    `duration_turns=1` pour l'Infiltrate : le 6e argument natif est `<DSLFormulas+0x20>` = `Direct(1)`
    (la constante partagee que `IdunBattleLogic.Entities.DSLFormulas$$.ctor` alloue en `+0x20`), DEJA
    en TOURS -- pas un `TurnsFromRounds`. Identique a 1153, qui prend le `Direct(1)` du `DSLFactory`.

    `duration_rounds=rounds` pour l'aura : le natif enveloppe, lui, `TurnsFromRounds(ConfigConst(0x45
    = nrOfRounds))` -- c'est le parametre ROUNDS de la feuille, converti par
    `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns`.

    `scale_from_source=True` sur l'aura = le PORT de l'`AbilityStateReference` : l'effet materialise
    resout son `ConfigVar(0x46 = dmgReductionPct)` contre l'etat d'ability de sa SOURCE (Dante), ce que
    fait litteralement `GetAbilityState(effect)` dans `LightOfSanguinius_DamageReductionEffect$$
    CreateDamageModifier`. Sans lui, un debuff pose sur un ENNEMI lirait le niveau du PORTEUR.

    `Infiltrate_UnitEffect` (1046) n'a pas de classe d'effet portee -> `BaseEffect` nu (effet PRESENT,
    sans contribution) : degradation fidele §17.4, exactement comme chez 1153."""
    infiltrate = AddEffect(INFILTRATE_UNIT, "Infiltrate_UnitEffect", Owner(),
                           duration_rounds=None, duration_turns=1)      # <DSLFormulas+0x20> = 1 TOUR
    fly = FlyUnit(Caster(), FixedTiles([dest] if dest is not None else []))
    attack = AttackWithAttackDamage(Target(), "LightOfSanguinius", "Melta", is_melee=True,
                                    native_factory="attack",   # `DSLBehaviors$$AttackWithAttackDamage`
                                    ability_type=int(ActiveAbilityType.LightOfSanguinius))
    aura = AddEffect(LIGHT_OF_SANGUINIUS, EffectType.LightOfSanguinius.name,
                     light_of_sanguinius_aura_targets(), duration_rounds=rounds,
                     scale_from_source=True)
    return op_and(op_and(infiltrate, fly),
                  If(IsAlive(Owner()), op_and(attack, aura)))            # `DSLBehaviors$$IfAlive`


class LightOfSanguiniusAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.LightOfSanguiniusAbility$$ExecuteBehaviour` (id 1177,
    `bloodDante` « Dante », Blood Angels) -- cf. `light_of_sanguinius_tree()`.

    Turn-flags = defauts base (1177 ABSENT des overrides `NO_END_TURN`/`NO_ABILITY_USED_FLAG`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.LightOfSanguinius)   # 1177
    ABILITY_ID = "LightOfSanguinius"

    # `IdunBattleLogic.Entities.Abilities.Active.LightOfSanguiniusAbility$$.ctor` -- FORME
    # « PRESET STATIQUE COPIE » : AUCUN appel a `TargetingOptions$$.ctor`, le ctor recopie les
    # 0x40 octets du preset `<TargetingOptions statics>+0x240` puis appelle
    # `AActiveAbility..ctor(this, &opts, 0)`. Le masque EFFECTIF est donc la constante que
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit a `<preset>+0x28` = `statics+0x268`,
    # RELUE pour #510 : `*(statics + 0x268) = 0x102004032`. Aucun `|` apres la copie.
    # Champs du meme preset, tous relus dans le `.cctor` :
    #   +0x240 isSelfCasting    = 0
    #   +0x248 range            <- `TargetingRange` statics+0x48 = RANGE_WHOLE_BOARD (useWholeBoard)
    #   +0x260 forceMeleeTarget = 1 = RangedBool.False
    #   +0x268 rules            = 0x102004032
    # C'est le MEME preset que `HammerOfWrathAbility` (1153) et `LeadingTheChargeAbility` (1204) --
    # decomposition EXHAUSTIVE, somme exacte, aucun bit residuel :
    #     0x2         TargetMatchesDynamicRule       -> `get_dynamic_invalid_target_reason` ci-dessous
    #     0x10        CasterHasNotMoved              (le « If Dante has not moved » de l'i2)
    #     0x20        TargetHasFreeAdjacentTile      (le volet STATIQUE ; la regle dynamique ajoute
    #                                                 la contrainte de DISTANCE au caster)
    #     0x4000      TargetIsEnemy
    #     0x2000000   AllowObscuredTargetByElevation
    #     0x100000000 TargetIsNotAdjacent            (bit 32 ; cible deja au contact = refusee)
    # ⚠ Ce masque MIGRE depuis `TARGETING_OPTIONS_UNPORTED` (contrat de DISJONCTION : porter la face
    # COMBAT d'une entree de cette table EXIGE d'en retirer la ligne, sinon
    # `tests/engine/runner/test_targeting_options_sources.py` rougit). VALEUR INCHANGEE par la
    # migration -- seule la SOURCE bouge.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.CasterHasNotMoved
        | TR.TargetHasFreeAdjacentTile
        | TR.TargetIsEnemy
        | TR.AllowObscuredTargetByElevation
        | TR.TargetIsNotAdjacent
    ), self_cast=False, range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`LightOfSanguiniusAbility$$GetDynamicInvalidTargetReason` -- le corps est DEJA porte
        (#287-r5) dans `abilities/targeting.py::_dynamic_rule_light_of_sanguinius`, et confronte live
        contre l'oracle natif `abilityReason` (`probe_287r5_light_of_sanguinius_live.py`). Cette
        surcharge l'APPELLE, et l'entree `DYNAMIC_TARGET_RULE_UNPORTED[1177]` sort dans le meme
        commit -- meme mouvement que 1087 (#488) et 1038 (#500).

        ⚠ Le code rendu est `0x20 = TargetHasFreeAdjacentTile`, PAS `TargetMatchesDynamicRule` : le
        natif REUTILISE un bit du volet statique comme code de refus."""
        return int(_targeting._dynamic_rule_light_of_sanguinius(
            state, caster_id, target_id) or 0)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        dest = light_of_sanguinius_dest_tile(state, caster_id, target_id)  # collapse SortTiles+First
        rounds = ability_var("LightOfSanguinius", "nrOfRounds", is_constant=True)  # ConfigConst(0x45)
        light_of_sanguinius_tree(dest, int(rounds) if rounds is not None else 1).execute(entities, ectx)
        main_attack, flew_to, debuffed = None, None, []
        for name, p in ectx.emitted:
            if name == "FlyUnit":
                flew_to = p.get("to") if p.get("moved") else None
            elif name == "AttackWithAttackDamage" and main_attack is None:
                main_attack = p.get("attack")
            elif name == "AddEffect" and p.get("effect_type") == LIGHT_OF_SANGUINIUS:
                debuffed.append({"target": p.get("target"), "placed": p.get("placed")})
        return {"ability": "LightOfSanguinius", "caster": caster_id, "target": target_id,
                "main_attack": main_attack, "flew_to": flew_to, "dest": dest,
                "debuffed": debuffed, "dsl": True}


# ===================== BloodChalice (Sanguinary Priest `bloodSanguinary`, actif 1175) -- #576 =====
#
# ⚠ CATEGORIE REELLE = **SET-HEALTH + 2 POSES D'EFFET**, soit TROIS mecaniques -- et l'audit
# `docs/rl/combat-ability-coverage.md` n'en annoncait qu'UNE (`HEAL`, colonne derivee du
# `damageProfile` de l'ARME du porteur, pas du behaviour). Le volet 1 n'est meme pas un SOIN : c'est
# un `ChangeStat` mode 0 = **SetAbsolute**, qui peut FAIRE BAISSER les PV d'un allie au-dessus du
# seuil. Le tooltip le dit mot pour mot (« are set to »), le decompile aussi.
#
# Indices de config LUS au decompile d'`IdunBattleLogic.Entities.Abilities.Active.
# BloodChaliceAbility$$ExecuteBehaviour` (membres NOMMES, jamais l'ordinal nu) :
#   `DSLFormulas$$ConfigConst(0x4f, ...)` -> `AbilityConstantType.healthPct`      (79) = 50 (CONSTANTE)
#   `DSLFormulas$$ConfigVar(0x3f, ...)`   -> `AbilityVariableType.extraPierceRatio` (63) : le +percage
#   `DSLFormulas$$ConfigVar(0x20, ...)`   -> `AbilityVariableType.hpToHeal`       (32) : le soin, LU
#                                            dans l'EFFET 1368, PAS dans l'ability
#
# `...BloodChaliceAbility$$ExecuteBehaviour` -- MIRROR du decompile :
#
#     b1 = ChangeStat( GetTargets(), Position(HEALTH=5, 0, 0), mode **0** = SetAbsolute,
#                      PercentageOf( StatAmount(It@DSLSelectors+0x68, HEALTH=5, MAXIMUM=2),
#                                    ConfigConst(0x4f healthPct), roundingRule **2** = Floor ) )
#     b2 = AddEffect( 0x558 = BloodChalice_HealOnAttack, AbilityStateReference,
#                     source = Owner@DSLSelectors+0x30, targets = GetTargets(), TurnsFromRounds(1) )
#     b3 = AddStaticStatModifierEffect( GetTargets(), 0x559 = BloodChalice_ExtraPiercing,
#                                       0x15 = StatType.ExtraPierceMelee,
#                                       ConfigVar(0x3f extraPierceRatio), TurnsFromRounds(1),
#                                       isHidden = false )
#     return AActiveAbility.Execute(this, op_Addition(op_Addition(b1, b2), b3))
#
# `Execute` PLAIN (PAS d'`ExecuteAtomic`, aucun `Group`) -> aucun `AtomicGroup`. Les trois volets
# sont DETERMINISTES (aucun tirage), donc l'ordre ne decale pas le PRNG ; il est transcrit tel que lu.
# ⚠ `GetTargets()` est appele DEUX fois par le natif (une instance pour b1, une autre partagee par
# b2/b3) : deux sous-arbres distincts, meme resultat -- transcrit en deux constructions.
#
# i2 (`Abilities/BloodChalice_CurrentLevelDescription`) : « All adjacent friendly non-mechanical
# units are set to {healthPct}% Health. Until the start of their next turn, affected units gain
# +{extraPierceRatio}% pierce ratio with melee attacks and heal for {hpToHeal} Health if they
# perform a melee attack. » -- appariement UN A UN avec les trois noeuds ci-dessus.
#
# La face DECISION est, elle, portee DEPUIS #82 (`playbook/bespoke.py::BloodChalicePlaybook`, override
# total d'`EvaluateInternal`) : AVANT cette tranche, 1175 SCORAIT donc son cast et ne FAISAIT RIEN --
# NO-OP silencieux (absente d'`ABILITY_CLASSES`, `ported: False`, 0 PV touche, aucune erreur).

BLOOD_CHALICE_ID = "BloodChalice"
BLOOD_CHALICE_HEAL_ON_ATTACK = int(EffectType.BloodChalice_HealOnAttack)    # 0x558 = 1368
BLOOD_CHALICE_EXTRA_PIERCING = int(EffectType.BloodChalice_ExtraPiercing)   # 0x559 = 1369


def blood_chalice_targets():
    """`IdunBattleLogic.Entities.Abilities.Active.BloodChaliceAbility$$GetTargets` -- MIRROR 1:1 :

        adj  = AdjacentFriends(Caster@DSLSelectors+0x48, unique: true, selectionType 3)
        mech = MechanicalUnits(adj, selectionType 3)
        return UnitsWithoutTrait(adj op_Subtraction mech, 0x19, selectionType 3)

    ⚠ SURCHARGE D'`AdjacentFriends` TRANCHEE PAR SES XREFS ENTRANTES : le build en porte DEUX, et
    `GetTargets` appelle la 4-args **UNIT-ancree** `AdjacentFriends(this, unit, unique,
    selectionType)`, qui se deplie en `Friends(unit, Units(AdjacentTiles(unit), unique, sel) - unit,
    sel)` -- PAS la TILE-ancree `(this, unit, unitTile, unique)` qu'appelle
    `...RitesOfRestorationAbility$$GetHealTargets`. La reference d'equipe EST le centre (le caster),
    donc le collapse `reference=None` du port est exact ici.

    ⚠ `0x19` est un `UnitTrait.Immune` (25), surtout pas un `EffectType` ni un `ActiveAbilityType` --
    l'ordinal est valide dans les trois enums. Il n'apparait PAS dans le tooltip i2 : c'est une
    exclusion muette, et la lire au decompile est la seule facon de l'avoir.

    ⚠ Le retrait des mecaniques est un `op_Subtraction` sur l'ENSEMBLE `adj`, pas un predicat
    applique en aval -- meme resultat ici (les deux etages sont des filtres purs), transcrit tel que lu.
    Il DOUBLE le gate non-mecanique de la regle dynamique (`_dynamic_rule_blood_chalice`, qui teste
    `IsAffectedByHealType(target, 0)`) : le premier borne l'ENSEMBLE EFFECTIVEMENT AFFECTE, le second
    borne les cibles LEGALES du message. Les deux existent, on porte les deux."""
    # #585-r1 -- les TROIS litteraux LUS dans `...BloodChaliceAbility$$GetTargets` :
    #   AdjacentFriends(gs, gs@0x48, unique: 1, 3) ; MechanicalUnits(gs, ., 3) ; UnitsWithoutTrait(gs, ., 0x19, 3)
    # La surcharge d'`AdjacentFriends` est la VARIANTE A (le 3e argument est le booleen `unique`),
    # tranchee par XREF ENTRANTE : `$$GetTargets` n'appelle pas la variante a `3` implicite.
    adj = AdjacentFriends(Caster(), selection_type=SELECTION)
    return UnitsWithoutTrait(Sub(adj, MechanicalUnits(adj, selection_type=SELECTION)),
                             int(UnitTrait.Immune), selection_type=SELECTION)


def blood_chalice_tree(extra_pierce_ratio: int):
    """UNIQUE noeud d'`...BloodChaliceAbility$$ExecuteBehaviour` (cf. le bloc RE ci-dessus).

    ⚠ VOLET 1 = `ChangeStat(..., mode **0** = SetAbsolute, ...)`, PAS un soin. `IdunBattle.Entities.
    Behaviours.ChangeStatBehaviour$$Execute` case 0 (relu pour cette tranche) :

        cur = UnitExtensions.GetStat(unit, stat, 0);
        statModifiers.Add(new StatModifier(stat, **amount**, ...));   // la valeur FINALE, absolue
        this+0x18 += amount - cur;                                    // le delta RAPPORTE

    -- le modifier impose `GetStat(stat) == amount`. Health etant une stat FILL-UP
    (`HealthComponent`, PAS un `StatComponent`), le SetAbsolute s'y lit `hc.hp = amount`. C'est
    exactement ce que fait la feuille `SetHealth` (`behaviours/stats.py`), deja mirror de ce meme
    `ChangeStat(Position(HEALTH,0,0), mode 0, .)` pour BlackRage et Drachnyen.

    ⚠ CONSEQUENCE OBSERVABLE, ET ELLE EST CONTRE-INTUITIVE POUR UNE ABILITY CLASSEE « HEAL » : un
    allie adjacent AU-DESSUS de `healthPct`% de son max est **RAMENE VERS LE BAS**. Ce n'est ni un
    bug de port ni un garde-fou a ajouter -- c'est le mode 0, et l'i2 l'ecrit (« are set to »).
    Le gate `EntityCanBeHealed` n'intervient PAS sur ce volet : la feuille n'est pas un `Heal`.

    ⚠ DEUX LITTERAUX du `PercentageOf` natif, LUS et non supposes (ils different de BlackRage sur les
    DEUX axes, cf. la docstring de `SetHealth`) :
      * base    = `StatAmount(It@DSLSelectors+0x68, HEALTH, **MAXIMUM=2**)` -- le max de CHAQUE cible
                  (`It` = l'unite en cours d'iteration), jamais celui du caster ;
      * pct     = `ConfigConst(0x4f)` = `GetNumberConstant` -> `constants.healthPct` = 50 (CONSTANTE,
                  pas une variable per-niveau) ;
      * arrondi = `roundingRule **2**` -> `AAmountFormula$$RoundFix64Result` mode 2 = **Floor**.
    Sur un `hp_max` impair a 50 %, Floor et half-to-even different d'exactement 1 PV.

    VOLET 2 : la SOURCE natice est `Owner@DSLSelectors+0x30`, pas `Caster@+0x48`. Pour une ability
    ACTIVE les deux slots designent la meme entite (`AActiveAbility` pose l'owner = le caster), donc
    le defaut `source_ref=None` du port (= le caster) est exact -- l'ecart est NOMME ici plutot que tu.
    `scale_from_source=True` : la magnitude du soin de l'effet 1368 est un `ConfigVar(0x20 hpToHeal)`
    resolu contre l'`AbilityState` du POSEUR, et `hpToHeal` EST dans `variablesAffectedByRarityBonus`
    -- sans ce flag le multiplier de rarete du porteur serait perdu (meme motif que Supercharge 1208).

    VOLET 3 : `isHidden = false` (litteral du call-site) = le defaut du port. `extraPierceRatio` n'est
    PAS dans `variablesAffectedByRarityBonus` -> le multiplier y est inerte, et la valeur est resolue
    par l'appelant puis passee en `Const` (meme patron que le `+CritChance` d'ExcruciatingFrequencies)."""
    set_hp = SetHealth(blood_chalice_targets(), BLOOD_CHALICE_ID, "healthPct",
                       pct_rounding=2, pct_is_constant=True)   # PercentageOf(., ., 2=Floor) ; ConfigConst
    cibles = blood_chalice_targets()                           # 2e instance du sous-arbre, comme le natif
    heal_eff = AddEffect(BLOOD_CHALICE_HEAL_ON_ATTACK, EffectType.BloodChalice_HealOnAttack.name,
                         cibles, duration_rounds=1, scale_from_source=True)
    pierce_eff = AddStaticStatModifierEffect(
        cibles, BLOOD_CHALICE_EXTRA_PIERCING, int(StatType.EXTRA_PIERCE_MELEE),
        Const(int(extra_pierce_ratio)), name=EffectType.BloodChalice_ExtraPiercing.name,
        duration_rounds=1)
    return op_add(op_add(set_hp, heal_eff), pierce_eff)        # op_Addition, op_Addition -- ordre du natif


class BloodChaliceAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.BloodChaliceAbility$$ExecuteBehaviour` (id 1175,
    `bloodSanguinary` « Sanguinary Priest », Blood Angels -- UNIQUE porteur).

    Renvoie {ability, caster, target, set_health, heal_on_attack, extra_piercing, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.BloodChalice)   # 1175
    ABILITY_ID = BLOOD_CHALICE_ID

    # GATE DE CIBLE. `IdunBattleLogic.Entities.Abilities.Active.BloodChaliceAbility$$.ctor` -- forme
    # « FLAGS DIRECTS » (`IdunBattle.Core.Services.TargetingOptions$$.ctor`, le 5e argument atterrit
    # tel quel a `options+0x28` = Rules) : le litteral EST le masque effectif. Ce n'est NI l'overload
    # PRESET+FLAGS, NI une recopie de champ statique -- le `statics+0xb8` copie ici alimente le 3e
    # argument (`range`, 24 octets depuis `<TargetingRange statics>+0x30` = RANGE_ADJACENT), pas les
    # regles.
    #     TargetingOptions..ctor(&opts, 1, &<TargetingRange statics+0x30>, 1, 0xc02, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2)
    #       isSelfCasting    = 1
    #       range            = `TargetingRange` statics+0x30 = RANGE_ADJACENT
    #       forceMeleeTarget = 1 = RangedBool.False
    #       rules            = 0xc02
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x0002  TargetMatchesDynamicRule    -> route vers `GetDynamicInvalidTargetReason` (porte) ;
    #     0x0400  TargetIsFriendly            -> ALLIE uniquement ;
    #     0x0800  AddCasterIfAtLeastOneTarget -> le caster est adjoint des qu'il y a une cible.
    # ⚠ PAS de `TargetIsHealable` (0x0100) -- contraste avec 1002/1039, qui sont de VRAIS soins. Ici
    # le volet 1 est un SetAbsolute, et le gate non-mecanique passe par la REGLE DYNAMIQUE seule.
    # ⚠ Masque RE-LU au decompile pour cette migration ; bit-identique a celui qui vivait dans
    # `TARGETING_OPTIONS_UNPORTED` (`targeting.py`), d'ou la ligne est retiree par le CONTRAT DE
    # DISJONCTION (une ability a UNE source de masque, jamais deux).
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.TargetIsFriendly
        | TR.AddCasterIfAtLeastOneTarget
    ), self_cast=True, range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`...BloodChaliceAbility$$GetDynamicInvalidTargetReason` -- le corps est DEJA porte
        (#287-r5) dans `abilities/targeting.py::_dynamic_rule_blood_chalice`, et confronte live
        contre l'oracle natif `abilityReason` (`probe_287r5_blood_chalice_live.py`). Cette surcharge
        l'APPELLE, et l'entree `DYNAMIC_TARGET_RULE_UNPORTED[1175]` sort dans le meme commit -- meme
        mouvement que 1177 (#510), 1087 (#488) et 1038 (#500).

        Le corps a ete RE-LU pour cette tranche et concorde bit a bit :
            tiles = EntityExtensions.GetTiles(target, state);
            if (battleQuery.AreEntitiesAdjacent(tiles, casterTiles)   // this+0x20, slot 0x62
                && UnitExtensions.IsAffectedByHealType(target, 0))    // HealType.NonMechanical
                return 0;
            return (caster != target) ? 2 : 0;                        // 2 = TargetMatchesDynamicRule"""
        return int(_targeting._dynamic_rule_blood_chalice(state, caster_id, target_id) or 0)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # SELF-CAST AoE : `target_id` ne selectionne AUCUNE cible -- l'ensemble affecte sort
        # entierement de `GetTargets()` (allies adjacents du CASTER). Un `target_id` None est donc
        # legitime et ne court-circuite rien (contraste 1177, qui exige sa cible).
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        sc = state.get_entity(caster_id)
        sc = sc.get_component(StatsComponent) if sc is not None else None
        level = getattr(sc.ctx, "active_ability_level", None) if sc is not None else None
        ratio = ability_var(BLOOD_CHALICE_ID, "extraPierceRatio", level)   # ConfigVar(0x3f)
        blood_chalice_tree(int(ratio) if ratio is not None else 0).execute(entities, ectx)
        set_health, heal_on_attack, extra_piercing = [], [], []
        for name, p in ectx.emitted:
            if name == "SetHealth":
                set_health.append({"target": p.get("unit"), "hp": p.get("hp")})
            elif name == "AddEffect" and p.get("effect_type") == BLOOD_CHALICE_HEAL_ON_ATTACK:
                heal_on_attack.append({"target": p.get("target"), "placed": p.get("placed")})
            elif (name == "AddStaticStatModifierEffect"
                  and p.get("effect_type") == BLOOD_CHALICE_EXTRA_PIERCING):
                extra_piercing.append({"target": p.get("unit"), "stat": p.get("stat"),
                                       "amount": p.get("amount")})
        return {"ability": BLOOD_CHALICE_ID, "caster": caster_id, "target": target_id,
                "set_health": set_health, "heal_on_attack": heal_on_attack,
                "extra_piercing": extra_piercing, "dsl": True}
