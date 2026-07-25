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

import hexgeo

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import op_add, op_and, AtomicGroup
from ...entities.selectors import (ActiveTarget, Caster, CasterTile, AdjacentUnits, FixedTileIds,
                                   Friends, Union, UnitsWithoutTrait, UnitsWithTrait, Target)
from ...entities.traits.unit_trait import UnitTrait
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effects.magnitude import ability_var
from ..components import PositionComponent, StatsComponent, UnitComponent
from .base import ActiveAbility
from .behaviours import (entities_from_state, Heal, healable_heal_type_0,
                        AttackWithAttackDamage, InformWeapon, PerformAIAttack, Spawn)

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


# ============ SpawnPoxwalkers (deathBlightbringer `Typhus`... `Blightbringer`, actif 1040) ============
#                                              case-220 P0-SUMMON
#
# `SpawnPoxwalkersAbility.ExecuteBehaviour @181208b80` (MIRROR du DECOMPILE) :
#     minPct = GetVariableForLevel(config, 0x3a, level)                        # "chance"
#     maxPct = GetVariableForLevel(config, 0x3b, level)                        # "chance_2"
#     unitId = GetStringConstant(config, 0)                                    # deathPoxwalker
#     range  = ContagionsOfNurgle_ArmorReduction_Effect.CalculateRange(<owner>) # @180f39940
#     tiles  = CanAddUnit(SurroundingTiles(owner@0x148, 0, range))
#     cnt    = <tiles>.Count(entities)                                          # EAGER (vslot +0x2b8)
#     amount = Divide(RandomAmount(cnt*minPct, cnt*maxPct), Get(100), mode=1=Ceiling)
#     picked = PickRandomly(tiles, amount, 0, 0x7fffffff, false)
#     opts   = SpawnUnitOptions.WithStatsFromConfig(config, level)
#     opts.+0x18 = PerformAIAttackFromCurrentPosition(activeTarget@0x180, 0, 0, false)
#     AActiveAbility.Execute(this, Spawn(owner@0x148, picked, unitId, opts), entities)
# UN SEUL `Execute` top-level. AUCUN `PerformAIAction` : l'on-appearance est un `PerformAIAttack`
# (routine IA mono-unite depuis la position courante), PAS un tour d'IA complet.
# SELF-CAST (`SpawnPoxwalkersPlaybook @18115c6f0` : cible eligible = SOI) -> owner@0x148 == caster.
VAR_POX_CHANCE = 0x3a       # GetVariableForLevel(0x3a) -> "chance"   (% mini de Poxwalker par tuile libre)
VAR_POX_CHANCE_2 = 0x3b     # GetVariableForLevel(0x3b) -> "chance_2" (% maxi)
CONST_POX_UNIT_ID = 0x00    # GetStringConstant(0)      -> "unitId"   = deathPoxwalker


def contagions_of_nurgle_range(state: "State", unit_id: int) -> int:
    """`IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect.CalculateRange
    @180f39940` -- MIRROR 1:1 :
        `s = UnitExtensions.GetStat(unit, 0xc=TurnsStarted, Current)`
        `if (s > 2) return (s > 4) ? 3 : 2 ; else return 1`
    -> rayon 1 aux tours 1-2, 2 aux tours 3-4, 3 a partir du tour 5. Le natif appelle cette methode
    STATIQUEMENT depuis `SpawnPoxwalkersAbility.ExecuteBehaviour @181208b80` (l'ability n'a pas d'effet
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
                Get(100), mode=1=Ceiling )` @181208b80 -- MIRROR.

    `cnt` = nombre de tuiles libres, evalue EAGER par le natif (appel virtuel `+0x2b8` du selecteur
    `CanAddUnit` AVANT la construction du noeud). `chance`/`chance_2` sont des POURCENTAGES par tuile
    (15..20 / 25..45 selon le niveau) -> le tirage porte sur `cnt*minPct .. cnt*maxPct` puis est divise
    par 100 avec arrondi **Ceiling** (`DivideAmount` mode 1, cf. `formulas.Divide`).

    `RandomAmount.Calculate @180f22160` = `rng.<slot 2>(min, max + 1)` -> borne haute INCLUSE ; le port
    consomme `state.rng.next_internal(min, max+1)` (meme primitive que `_pick_randomly`). `state.rng`
    non cale -> on retombe sur la borne BASSE (deterministe, documente ; le cout/ordre RNG exact reste
    le GAP deja flague sur `_pick_randomly_n`)."""
    from math import ceil
    sc = state.get_entity(caster_id).get_component(StatsComponent)
    cctx = sc.ctx if sc is not None else None
    level = getattr(cctx, "active_ability_level", None)
    mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
    lo = int(ability_var("Poxwalkers", "chance", level, multiplier_pct=mult) or 0) * int(nb_tiles)
    hi = int(ability_var("Poxwalkers", "chance_2", level, multiplier_pct=mult) or 0) * int(nb_tiles)
    if hi < lo:
        hi = lo
    raw = lo if state.rng is None else state.rng.next_internal(lo, hi + 1)   # max INCLUS (@180f22160)
    return int(ceil(raw / 100))                                              # Divide(..., 100, Ceiling)


# ===================== EntropyCannons (deathCrawler, MACHINE OF WAR, actif 1168) =====================
#
# Porteur : `deathCrawler` « Plagueburst Crawler » = MACHINE OF WAR (pool `--list-pool`, 8 MoW) ->
# entite ECS hors-plateau (ni Position ni Health), chargee par `_load_machines` (case-mow-offboard-cast).
#
# CIBLAGE (face DECISION/eligibilite, HORS `ExecuteBehaviour`) — `EntropyCannonsAbility.
# GetDynamicInvalidTargetReason @1811bfc20`, MIRROR du decompile :
#     if !EntityExtensions.IsUnit(target) -> reason 0 (pas d'objection)
#     aura = IsInTeamContagionsOfNurgleAura(target@0x178, caster@0x160) @180df3ea0
#            -> `IsInAuraRangeTrigger(effectType=0x42f=1071 ContagionsOfNurgle_ArmorReduction1,
#                                     unit=target, teamReference=caster)`
#     armor = HasNegativeModifier(target@0x178, 0x10=FixedArmor) @180df11e0
#            -> `Triggers.HasNegativeModifier.ShouldTrigger @180f9db90` = il existe une modification
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
# existe deja pour la branche (b) : `UnitStats.has_negative_modifier({16})` (mirror @180f9db90).

ENTROPY_CANNONS_ID = "EntropyCannons"


def entropy_cannons_tree() -> AttackWithAttackDamage:
    """Arbre de `EntropyCannonsAbility$$ExecuteBehaviour @1811bfa40` (id 1168, deathCrawler MoW) —
    MIRROR du DECOMPILE (UN seul noeud, passe directement a `AActiveAbility.Execute`) :

        Execute( AttackWithAbilityDamage( caster@0x160, target@0x178,
                                          MinMaxDamage(this, entities),                # minDmg/maxDmg[level]
                                          Nullable(GetDamageProfile(this))=Energy,
                                          GetHits(this)=ConfigConst(0x2f)=nrOfHits=2,
                                          AbilityOrEffect(this+0x10 = 0x490 = 1168) ) )

    - **native_factory = "ability"** : le decompile appelle litteralement `DSLFactory.
      AttackWithAbilityDamage @180de9c90` (overload core @180de9e50), PAS `AttackWithAttackDamage
      @180de9fb0` -> `AbilityDamageBehaviour` -> `AbilityDamageOperation.ExecuteHits @180e2a860` :
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
                                  native_factory="ability",          # @180de9c90 (XREF), 1 tirage/coup
                                  ability_type=int(ActiveAbilityType.EntropyCannons))


class EntropyCannonsAbility(ActiveAbility):
    """`EntropyCannonsAbility$$ExecuteBehaviour @1811bfa40` (id 1168, `deathCrawler` « Plagueburst
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
    """Arbre de `SpawnPoxwalkersAbility.ExecuteBehaviour @181208b80` : UN noeud `Spawn` dont les options
    portent le sous-behaviour ON-APPEARANCE `PerformAIAttackFromCurrentPosition(activeTarget@0x180)`
    (`DSLFactory.PerformAIAttackFromCurrentPosition @180df8a10` -> `PerformAIAbilityUnitBehaviour.Execute
    @180fcb070`) = chaque Poxwalker fraichement pose attaque DEPUIS SA POSITION (sans bouger). La feuille
    portee `PerformAIAttack` accepte le domaine UNITE (l'`ActiveTarget` lie par le `Spawn`) aussi bien que
    le domaine TUILE (le `Cache` de GetEmRuntz)."""
    return Spawn(FixedTileIds(tiles), "Poxwalkers", on_appearance=PerformAIAttack(ActiveTarget()))


class SpawnPoxwalkersAbility(ActiveAbility):
    """`SpawnPoxwalkersAbility.ExecuteBehaviour @181208b80` (id 1040, `deathBlightbringer`, DeathGuard).
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
