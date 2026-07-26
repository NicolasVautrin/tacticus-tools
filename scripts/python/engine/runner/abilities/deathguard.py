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
from ...entities.behaviours import op_add, op_and, AtomicGroup
from ...entities.selectors import (ActiveTarget, Caster, CasterTile, AdjacentTiles, AdjacentUnits,
                                   Enemies, Filter, FixedTileIds, Friends, Subject, Union, Unique,
                                   Units, UnitsWithoutTrait, UnitsWithTrait, Target)
from ...entities.triggers import (AmountIsGreaterThanZero, HasNegativeModifier, IsInTeamAura,
                                  TriggerAnd, TriggerOr)
from ...entities.formulas import StatAmount
from ...entities.effect_type import EffectType
from ...entities.stats import StatType, StatPart
from ...entities.traits.unit_trait import UnitTrait
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effects.magnitude import ability_var
from ..components import PositionComponent, StatsComponent, UnitComponent
from .base import ActiveAbility
from .behaviours import (entities_from_state, Heal, healable_heal_type_0, AddEffect,
                        AttackWithAttackDamage, InformWeapon, PerformAIAttack, Spawn)

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
    all_heal = UnitsWithoutTrait(
        Union(Friends(AdjacentUnits(CasterTile(), Const(1))), Caster()),
        int(UnitTrait.Imperial))                              # WithoutTrait(0x1a, Union(Friends(AdjacentUnits(self,1)), self))
    regular_sel = UnitsWithoutTrait(all_heal, int(UnitTrait.Chaos))   # regular = WithoutTrait(0x7ea)
    chaos_sel = UnitsWithTrait(all_heal, int(UnitTrait.Chaos))        # chaos   = WithTrait(0x7ea)
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
      `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (famille attack, VERIFIE par la CALLEE de IdunBattleLogic.Entities.Abilities.Active.Loki.FlailSwingAbility$$ExecuteBehaviour =
      symbole `DSLFactory$$AttackWithAttackDamage`, JAMAIS `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` ; tip #2 /
      rngcrit-1202). Attaque MULTI-COUPS (3x) -> classification par XREF OBLIGATOIRE, faite ici.
    - `InformWeapon` = `op_BitwiseAnd` volet GAUCHE (execute EN PREMIER) : canal weapon-inform (metadata,
      `ActivateEffectBehaviour`) COMBAT-INERTE (0 RNG, 0 mutation PV/stat) -> n'altere PAS l'ordre `state.rng`
      de l'attaque : bit-exact BY CONSTRUCTION. Le trigger consommateur (`HazeOfCorruption`) est un passif
      SEPARE (hors face COMBAT) -- le declenchement Haze n'est PAS dans cet ExecuteBehaviour.
    - **`alwaysOverkilled` (Nullable=true) PORTE via `force_overkill=True`** : le 8e arg de
      `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (`&local_198` = `Nullable<bool>` HasValue=1, cf. `local_1e8=0x100000000`
      + `System.Nullable<...>.ctor`) = flag « always overkilled » passe a `AttackDamageBehaviour` puis a l'etage
      `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage` (`overkill=true` bypasse le cap Resilient
      `IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit`). La feuille passe `force_overkill=True` -> `_run_hits` force
      `overkill=True` a chaque coup. VALIDE LIVE (deathBlightlord vs custoKyrus Resilient HP 10000 : live tue
      [5070,4555,375] sum=10000 == PV full ; le port SANS le flag laissait 1 PV [5070,4555,374] sum=9999 -> le
      flag est le seul ecart). No-op sur cible non-Resilient -> coeur 3x Power bit-exact partout."""
    return op_and(InformWeapon("Power"),
                  AttackWithAttackDamage(Target(), "FlailSwing", "Power", is_melee=True, force_overkill=True))


class FlailSwingAbility(ActiveAbility):
    """`FlailSwingAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.FlailSwingAbility$$ExecuteBehaviour` (id 1042, deathBlightlord — Death Guard/Chaos, namespace
    natif `Abilities.Active.Loki`). Arbre DSL `flail_swing_tree()` (MIRROR 1:1 du decompile) :
        Execute( op_BitwiseAnd(
            InformWeapon(Power),                                                    # metadata arme (no-op combat)
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
VAR_POX_CHANCE = 0x3a       # GetVariableForLevel(0x3a) -> "chance"   (% mini de Poxwalker par tuile libre)
VAR_POX_CHANCE_2 = 0x3b     # GetVariableForLevel(0x3b) -> "chance_2" (% maxi)
CONST_POX_UNIT_ID = 0x00    # GetStringConstant(0)      -> "unitId"   = deathPoxwalker


def contagions_of_nurgle_range(state: "State", unit_id: int) -> int:
    """`IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect$$CalculateRange` -- MIRROR 1:1 :
        `s = UnitExtensions.GetStat(unit, 0xc=TurnsStarted, Current)`
        `if (s > 2) return (s > 4) ? 3 : 2 ; else return 1`
    -> rayon 1 aux tours 1-2, 2 aux tours 3-4, 3 a partir du tour 5. Le natif appelle cette methode
    STATIQUEMENT depuis `IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$ExecuteBehaviour` (l'ability n'a pas d'effet
    Nurgle a ce point : c'est un helper de portee PARTAGE avec l'aura ContagionsOfNurgle)."""
    from ...entities.stats import StatType
    e = state.get_entity(unit_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    stats = getattr(sc.ctx, "stats", None) if sc is not None else None
    s = int(stats.get_stat(int(StatType.TURNS_STARTED), 0)) if stats is not None else 0
    if s > 2:
        return 3 if s > 4 else 2
    return 1


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
#     aura = IdunBattleLogic.Entities.DSLFactory$$IsInTeamContagionsOfNurgleAura(target@0x178, caster@0x160)
#            -> `IsInAuraRangeTrigger(effectType=0x42f=1071 ContagionsOfNurgle_ArmorReduction1,
#                                     unit=target, teamReference=caster)`
#     armor = IdunBattleLogic.Entities.DSLFactory$$HasNegativeModifier(target@0x178, 0x10=FixedArmor)
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
      IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` (overload core IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage), PAS `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` -> `AbilityDamageBehaviour` -> `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHits` :
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
                                  native_factory="ability",          # IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage (XREF), 1 tirage/coup
                                  ability_type=int(ActiveAbilityType.EntropyCannons))


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


def spawn_poxwalkers_tree(tiles: list) -> Spawn:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$ExecuteBehaviour` : UN noeud `Spawn` dont les options
    portent le sous-behaviour ON-APPEARANCE `PerformAIAttackFromCurrentPosition(activeTarget@0x180)`
    (`IdunBattleLogic.Entities.DSLFactory$$PerformAIAttackFromCurrentPosition` -> `IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute`) = chaque Poxwalker fraichement pose attaque DEPUIS SA POSITION (sans bouger). La feuille
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

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if state.get_entity(caster_id) is None:
            return None
        radius = contagions_of_nurgle_range(state, caster_id)
        tiles = poxwalkers_spawn_tiles(state, caster_id, radius)
        n = poxwalkers_count(state, caster_id, len(tiles))
        from .loki.splash import _pick_randomly_n
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
# NOTE `Difference` : la factory native est `IdunBattleLogic.Entities.DSLFactory$$Difference(a, b)` = `a - b` ;
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

    RESIDU : la branche AURA (`IsInTeamAura`) est INERTE offline (canal d'aura non materialise, cf.
    `entities/triggers.py::IsInTeamAura`) -> seule la branche ARMURE discrimine. Le natif, lui, accepte
    aussi une cible sous aura Contagion alliee."""
    aura = IsInTeamAura(Subject(), CONTAGIONS_OF_NURGLE_ARMOR_REDUCTION1, Caster())
    armor = TriggerAnd(
        HasNegativeModifier(Subject(), (int(StatType.FIXED_ARMOR),)),
        AmountIsGreaterThanZero(StatAmount(Subject(), int(StatType.FIXED_ARMOR),
                                           int(StatPart.INITIAL))))
    return TriggerOr(aura, armor)


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
    pred = plagueburst_is_valid_adjacent_enemy_trigger()
    main = Filter(Enemies(Units(target_sel)), pred)
    adj = Filter(Enemies(Units(AdjacentTiles(target_sel))), pred)
    return Unique(Union(main, adj))


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
    """Id de la TUILE ciblee : le cast est TILE-TARGET (mesure live), mais on accepte aussi un id
    d'UNITE (on prend alors sa MainTile) -- `target@0x178` designe une ENTITE et le natif en lit la
    MainTile partout ou il l'utilise en domaine tuile."""
    board = state.board
    if board is None or target_id is None:
        return None
    if int(target_id) in board.by_id:
        return int(target_id)
    te = state.get_entity(target_id)
    tpc = te.get_component(PositionComponent) if te is not None else None
    return board.id_at(tpc.col, tpc.row) if tpc is not None else None


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
    from .loki.splash import _pick_randomly_n
    return _pick_randomly_n(state, pool, max(0, int(n_tiles) - 1))


def plagueburst_mortar_tree(target_sel, picked_tiles: list):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$ExecuteBehaviour`
    (MIRROR 1:1) :

        op_BitwiseAnd( op_BitwiseAnd( AttackWithAbilityDamage(<cibles valides>),
                                      AddEffect(Pinned -> <les MEMES cibles>) ),
                       AddEffect(Contaminated -> cible + <tuiles tirees>) )

    - l'attaque route `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` (famille ABILITY :
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

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
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
