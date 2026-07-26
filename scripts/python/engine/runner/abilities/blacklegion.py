"""Abilities BlackLegion (namespace natif `Abilities.Active.Loki.*`) — case-220 §6.11.

Module DEDIE a la faction Black Legion (comme `genestealer.py`/`deathguard.py` : une classe par ability,
l'arbre SPECIFIQUE vit avec sa classe). RE ghidra gqfc5mff6c (VA citees). Doc : docs/rl/case-220/black-legion.md.

Contenu :
- `BringerOfDespair` (1022, Angrax `blackTerminator`) — attaque MAIN 4x Power sur la cible + bonus 4x Power
  sur UN ennemi aleatoire adjacent au CASTER (template splash `loki/splash.py`, factory attack).
- `Incursion` (1021, Vitruvius `blackPossession`) — `ChainBehaviour` de spawns Bloodletter adjacents a la
  cible + on-appearance `UseNormalAttackIfAble` (case-220 P0-SUMMON).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import AtomicGroup, ChainBehaviour, If as IfBehaviour, op_add, op_and
from ...entities.formulas import (If as FormulaIf, Multiply, Sum, TotalActiveAbilityUsed)
from ...entities.selectors import (ActiveTarget, AdjacentTiles, AdjacentUnits, CanAddUnit, Caster,
                                   CasterTile, Damageable, Enemies, Filter, FixedTileIds, Friends,
                                   Nothing, Null, Sub, Subject, Target, TilesInTriangleShape,
                                   TilesOnSameElevation, Units)
from ...entities.triggers import (HasEffect, IsAlive, IsInRange, IsPositionMachineForCurrentPlayer,
                                  TriggerAnd)
from ...entities.effect_type import EffectType
from ...entities.stats import StatType
from ...entities.active_ability_type import ActiveAbilityType
from .base import ActiveAbility
from .behaviours import (entities_from_state, AddEffect, AttackWithAttackDamage, ChangeStat, Spawn,
                         UseActiveAbility, add_or_update_static_stat_modifier_effect)

if TYPE_CHECKING:
    from ..state import State


def bringer_of_despair_tree() -> AtomicGroup:
    """Arbre de `BringerOfDespairAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.BringerOfDespairAbility$$ExecuteBehaviour` (id 1022, Angrax `blackTerminator` —
    MIRROR du DECOMPILE + `IdunBattleLogic.Entities.Abilities.Active.Loki.BringerOfDespairAbility$$GetValidBonusTargets` / `IdunBattleLogic.Entities.Abilities.Active.Loki.BringerOfDespairAbility$$GetHitsToBonusTarget` /
    `IdunBattleLogic.Entities.Abilities.Active.Loki.BringerOfDespairAbility$$GetDamageProfile`) :

        bonusSel = PickRandomly(                                                          # IdunBattleLogic.Entities.Abilities.Active.Loki.BringerOfDespairAbility$$ExecuteBehaviour
                     Damageable( Enemies( caster@0x148, AdjacentUnits(casterTile@0x168, radius=1) ) )
                     op_Subtraction Target()@0x178,
                     nrOfTargets = 1 )
        ExecuteAtomic( op_BitwiseAnd(
            AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage, GetDamageProfile=Power,
                                    hits = GetNumberConstant(0x2f)=nrOfHits),               # [MAIN]
            AttackWithAttackDamage(caster@0x160, bonusSel,     MinMaxDamage, Power,
                                    hits = GetNumberConstant(0x32)=nrOfHits_2) ), 0x45 )     # [BONUS]

    - **Deux volets, MEME plage `MinMaxDamage`** : le decompile calcule `local_1f8 = MinMaxDamage(target)`
      UNE fois et le PARTAGE (`uVar7 = local_1f8`) entre les deux `AttackWithAttackDamage` (BringerOfDespair
      n'a AUCUN override `GetAttackDamage` -> MinMaxDamage = bornes config `minDmg`/`maxDmg` brutes,
      INDEPENDANTES de la cible). Seule la constante de coups differe : main = `nrOfHits`(0x2f), bonus =
      `nrOfHits_2`(0x32) — config 1022 : les DEUX valent 4 (i2 « 4x ... and 4x ... »). Profil `Power` (melee,
      PiercingRatio 40) pour les deux. `attackRangeType=Melee` -> `is_melee=True`.
    - **BONUS = ennemi adjacent au CASTER, PAS a la cible** : `AdjacentUnits(casterTile@0x168, radius=1)` —
      @0x168 = CasterTile (ANCRE : `IdunBattleLogic.Entities.Abilities.Active.Loki.GauntletsOfUltramarAbility$$GetAdjacentTargetsSelector` decompile
      `AdjacentTiles(@0x168)` = casterTile). `Enemies(caster@0x148, ...)` filtre a l'equipe adverse (@0x148 =
      Caster, meme role enemies-ref que @0x160 dans Gauntlets/CrushingClaws ; HeroicFusillade `caster@0x148`
      valide live). `Damageable` = vivants ciblables (PV>0). `op_Subtraction Target()@0x178` retire la cible
      MAIN (« ANOTHER random enemy »). i2 : « 4x ... to another random enemy adjacent to Angrax [le caster] ».
    - **PickRandomly(<set>, nrOfTargets=1)** FOLDE dans la feuille bonus via `pick_n=1` (== Fragstorm :
      `multi=True` folde l'`OrderBy` par id, `pick_n` folde le PickRandomly DANS la resolution du selecteur,
      `state.rng`). Evalue A L'EXECUTION du volet bonus = APRES les coups MAIN (op_BitwiseAnd = main puis bonus)
      -> l'ordre de conso `state.rng` (8 tirages main a cc=0, puis le pick, puis 8 tirages bonus) mirror le natif.
    - **native_factory = "attack"** (defaut, 2 tirages/coup a cc=0) : les DEUX volets appellent
      `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (VERIFIE par les CALLEES de IdunBattleLogic.Entities.Abilities.Active.Loki.BringerOfDespairAbility$$ExecuteBehaviour, PAS au nom du
      commentaire — cf. rngcrit-1202/tip #2), famille attack, JAMAIS `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage`.

    `op_BitwiseAnd` = `CombinedBehaviour` (effets PURS -> les deux volets s'executent) ; `ExecuteAtomic` ->
    `AtomicGroup` (inline #201 ; tag 0x45 = id du groupe atomique, aucun `EvaluateAbilities` implicite, cf.
    #209). Ordre = main PUIS bonus, cibles triees par id (OrderBy natif), meme `state.rng` -> bit-exact BY
    CONSTRUCTION (memes bornes/hits/profil que l'attaque generique). Le « Battle Fatigue triggered twice »
    de l'i2 est ABSENT de l'ExecuteBehaviour (aucun noeud effet) -> no-op degat (mecanique de trigger separee,
    hors face COMBAT).

    #130 (GAP #215 CLOS sur la CONSO) : `_pick_randomly_n` consomme desormais `min(len(pool), 1)` tirages,
    donc **1 tirage des qu'il y a >=1 candidat** (y compris le cas 1v1 ou le bonus est l'unique ennemi
    adjacent) -- le natif n'a AUCUN court-circuit « le pool tient dans amount » (cf. `_pick_randomly_n`).
    Le pick precede les coups BONUS : sans lui, TOUT le flux rng du volet bonus etait decale.
    ⚠ RESIDU #215 restant : quand >1 ennemi damageable adjacent au caster, l'ordre d'enumeration natif du
    pool (non id-trie) decide QUI est pique -> l'ennemi touche peut differer (la CONSO, elle, est exacte)."""
    tgt = Target()
    main = AttackWithAttackDamage(tgt, "BringerOfDespair", "Power", is_melee=True)      # MinMaxDamage/Power/0x2f=4
    bonus_sel = Sub(Damageable(Enemies(AdjacentUnits(CasterTile(), Const(1)))), Target())  # adjacents-caster (ennemis, PV>0) − cible
    bonus = AttackWithAttackDamage(bonus_sel, "BringerOfDespair", "Power", is_melee=True,
                                   hits_key="nrOfHits_2", multi=True, pick_n=1)          # MEME plage, PickRandomly(1), 0x32=4
    return AtomicGroup(op_and(main, bonus))


class BringerOfDespairAbility(ActiveAbility):
    """`BringerOfDespairAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.BringerOfDespairAbility$$ExecuteBehaviour` (id 1022, Angrax `blackTerminator`, namespace
    natif `Abilities.Active.Loki`).

    Arbre DSL `bringer_of_despair_tree()` = template splash `loki/splash.py` (MEME plage main/bonus, seuls les
    coups different) mais BONUS ANCRE SUR LE CASTER (pas la cible) : (1) 4x Power sur la cible melee ; (2) 4x
    Power sur UN ennemi damageable aleatoire adjacent au caster, excluant la cible (`PickRandomly(1)` folde via
    `pick_n=1`). Profil Power (melee). Selecteurs (CasterTile/Enemies/Damageable/Sub) portes, structure
    DSL (op_BitwiseAnd, ExecuteAtomic). Renvoie {main_attack, bonus, dsl}.

    Les deux volets = `AttackWithAttackDamage(multi/mono)` -> memes Operations (`AttackDamageOperation.
    execute_ability_attack`, `native_factory="attack"` = 2 tirages/coup a cc=0) que l'attaque generique ->
    bit-exact BY CONSTRUCTION. Termine le tour (1022 hors des frozensets base.py -> flags par defaut)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.BringerOfDespair)  # 1022
    ABILITY_ID = "BringerOfDespair"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        # behaviour = arbre DSL (main mono-cible + bonus multi=True/pick_n=1 ancre caster) ; emet les MEMES
        # Operations (execute_ability_attack) -> meme mutation, diag main/bonus par cible.
        ectx = ExecutionContext(state=state, rng=state.rng)
        bringer_of_despair_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        bonus = [{"target": p["target"], "attack": p["attack"]}
                 for p in atks if p.get("target") != target_id]     # cibles bonus != cible principale
        return {"ability": "BringerOfDespair", "caster": caster_id, "target": target_id,
                "main_attack": main, "bonus": bonus, "dsl": True}


# ================== Incursion (blackPossession `Vitruvius`, actif 1021) -- case-220 P0-SUMMON ==================
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE) :
#     unitId   = GetStringConstant(config, 0)                                    # blackSmnBloodletter
#     tgtUnit  = TargetsSelector.SelectUnit(target@0x178, entities, 3)           # cible resolue EAGER
#     opts     = SpawnUnitOptions.WithStatsFromConfig(config, level)
#     opts.+0x18 = UseNormalAttackIfAble(activeTarget@0x180, Entity(tgtUnit), <AbilityOrEffect>, ...)
#     spawnB   = Spawn(caster@0x160, activeTarget@0x180, unitId, opts)
#     chain    = ChainBehaviour(Null(), Func(this.GetNextSpawnTile), Direct(GetNumberConstant(0x3c)),
#                               spawnB, UnitTimelines.TypeToTimeline())
#     AActiveAbility.Execute(this, chain, entities)
# UN SEUL `Execute` top-level. AUCUN `PerformAIAction` : l'on-appearance est une attaque NORMALE dirigee.
CONST_INCURSION_UNIT_ID = 0x00      # GetStringConstant(0)    -> "unitId"      = blackSmnBloodletter
CONST_INCURSION_RANGE = 0x16        # GetNumberConstant(0x16) -> "range"       = 2  (MEME index que 1028)
CONST_INCURSION_MAX_SUMMONS = 0x3c  # GetNumberConstant(0x3c) -> "maxSummons"  = 6


def incursion_next_spawn_tile(state: "State", entities):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$GetNextSpawnTile` -- MIRROR ; RE-CONSTRUIT a CHAQUE ITERATION de la
    chaine (le natif passe un `System.Func<>` sur cette methode, donc une NOUVELLE instance de selecteur
    par tour -> aucune memoisation, l'etat LIVE est relu) :

        cond   = ( IsAlive(caster@0x160) op_BitwiseAnd IsAlive(target@0x178) )
                 op_BitwiseAnd IsInRange(caster@0x160, target@0x178, Direct(GetNumberConstant(0x16)))
        tiles  = CanAddUnit(AdjacentTiles(target@0x178))
        amount = ConditionalAmount(cond, 1@dsl+0xc0, 0@dsl+0xb8)
        return PickRandomly(tiles, amount, 0, 0x7fffffff, false)

    `cond` est EXACTEMENT `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$GetContinueTrigger` -> c'est la condition d'arret de
    la chaine : caster vivant ET cible vivante ET caster a <= `range` hex de la cible. Comme les
    Bloodletters ATTAQUENT la cible a l'apparition, une cible qui MEURT en cours de chaine rend `cond`
    faux -> selecteur vide -> `ChainBehaviour` s'arrete AVANT d'avoir consomme ses `maxSummons`.

    Le predicat reste du DSL (`IsAlive`/`IsInRange`/`TriggerAnd`) et le selecteur de tuiles aussi
    (`CanAddUnit(AdjacentTiles(Target()))`) ; seul le couple `ConditionalAmount`+`PickRandomly` est FOLDE
    (le tirage vit la ou l'on voit `state.rng`, meme doctrine que le `pick_n` de `Spawn`)."""
    from ..abilities.loki.splash import _pick_randomly_n
    rng_const = int(((GC.ability("Incursion") or {}).get("constants") or {}).get("range") or 0)
    cond = TriggerAnd(TriggerAnd(IsAlive(Caster()), IsAlive(Target())),
                      IsInRange(Caster(), Target(), Const(rng_const)))
    if not cond.evaluate(entities):                      # ConditionalAmount -> 0@dsl+0xb8 -> fin de chaine
        return Nothing()
    tiles = CanAddUnit(AdjacentTiles(Target())).evaluate(entities)
    return FixedTileIds(_pick_randomly_n(state, tiles, 1))   # ConditionalAmount -> 1@dsl+0xc0


def incursion_tree(state: "State", max_summons: int) -> ChainBehaviour:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$ExecuteBehaviour` : `ChainBehaviour` bornee a `maxSummons`
    iterations, chacune (a) re-evaluant `GetNextSpawnTile` (0 ou 1 tuile libre adjacente a la cible,
    gatee par la condition de continuation) puis (b) executant `Spawn(caster, ActiveTarget@0x180,
    blackSmnBloodletter, opts)` -- la tuile rendue par l'iteration est liee a `ActiveTarget`, que le
    `Spawn` lit comme tile-selecteur. Le sous-behaviour on-appearance des options
    (`UseNormalAttackIfAble(activeTarget@0x180, Entity(cible))`) fait ATTAQUER chaque Bloodletter
    fraichement pose sur la cible du cast -- ici `ActiveTarget` designe le SUMMON (rebind du `Spawn`),
    imbrique dans le bind de tuile de la chaine (mirror exact des deux niveaux natifs)."""
    return ChainBehaviour(next_selector=lambda ents: incursion_next_spawn_tile(state, ents),
                          times=Const(int(max_summons)),
                          body=Spawn(ActiveTarget(), "Incursion",
                                     on_appearance=UseActiveAbility(ActiveTarget(), Target())),
                          init=Null())


# ===================== HadesAutocannons (blackForgefiend, MACHINE OF WAR, actif 1147) =====================
#
# Porteur : `blackForgefiend` « Forgefiend » = MACHINE OF WAR (pool `--list-pool`, 8 MoW) -> entite ECS
# hors-plateau (ni Position ni Health), chargee par `_load_machines` (case-mow-offboard-cast).
#
# CIBLAGE (face DECISION/eligibilite) : 1147 n'a **AUCUN** `GetDynamicInvalidTargetReason` (contraste
# 1168/1200) -- son predicat vit dans les `TargetingOptions` du ctor `HadesAutocannonsAbility..ctor
# IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$.ctor` (`TargetingOptions(0, <filtre>, 1, 0x46006000, 0,0,0)`), ET il est REDIT par le selecteur
# d'execution `IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets` (`UnitsWithTrait(..., 2=Summon)`) : la cible doit etre un
# **SUMMON ennemi**. C'est CE predicat qui rend « 0 cible au spawn » (sweep case-mow §5) : il faut le
# MONTER (amener un summoner adverse a invoquer, puis viser un summon) pour obtenir une cible.
CONST_HADES_RANGE = 0x16          # GetNumberConstant(0x16) -> "range" = 2
VAR_EXTRA_CRIT_DMG = 0x42         # GetVariableForLevel(0x42) -> "extraCritDmg"
HADES_AUTOCANNONS_ID = "HadesAutocannons"


def hades_autocannons_get_all_targets(range_: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets` — MIRROR du DECOMPILE :

        sel   = UnitsWithTrait( Friends( target@0x178,                                   # allies DE LA CIBLE
                                         SurroundingUnits(target@0x178, GetNumberConstant(0x16)=range,
                                                          1, includeCenter=1, 3) ),
                                2 = Summon, 3 )
        asc   = SortByRow( Tiles(sel), 0, 0, false )
        desc  = SortReverse( SortByRow( Tiles(sel), 0, 0, false ) )
        return If( AreEqual(CurrentPlayer, Player(1)), asc, desc )                        # == IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$IsTopPlayer

    = les SUMMONS (trait 2) allies de la CIBLE, dans un disque de rayon `range` autour d'elle,
    **CIBLE INCLUSE** (`IdunBattleLogic.Entities.DSLFactory$$SurroundingTiles(..., includeCenter=1) : param!=0 -> selecteur direct,
    param==0 -> `- Tiles(center)`). i2 : « a targeted enemy summon AND all other enemy summons within 2
    hexes of the target ». Le referent de `Friends` est la **CIBLE** (1er arg natif), pas le caster : ce
    sont donc les summons du camp de la cible = les summons ENNEMIS du caster (d'ou le `Friends(reference=
    Target())` porte).

    **ORDRE** : le `SortByRow`/`SortReverse` (+ `If(IsTopPlayer)`) est un ordre de LECTURE du selecteur ;
    il est ECRASE en aval par l'`OrderBy` que `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` applique
    INCONDITIONNELLEMENT des que le set a >= 2 cibles (`if (1 < count) OrderBy(<>c.b__5_0 IdunBattle.Entities.Behaviours.AttackBehaviour.u003Cu003Ec$$u003CExecuteu003Eb__5_0)`
    = cle par-entite du slot vtable +0x158). Le port garde donc son tri par `id` (`multi=True`, == tous
    les autres multi-cibles valides bit-exact) et NE porte PAS les noeuds de tri — HYPOTHESE explicite
    (la cle +0x158 n'est pas relue ici) : discriminable live avec >= 2 summons dont l'ordre de `row`
    contredit l'ordre d'`id`."""
    from ...entities.selectors import SurroundingUnits, TargetTile, Tiles, Units, UnitsWithTrait
    from ...entities.traits.unit_trait import UnitTrait
    ring = SurroundingUnits(TargetTile(), Const(int(range_)), include_center=True)   # includeCenter=1
    summons = UnitsWithTrait(Friends(ring, reference=Target()), int(UnitTrait.Summon))
    return Units(Tiles(summons))     # aller-retour unites -> Tiles(sel) -> Units(...) du natif (mirror)


def hades_autocannons_tree(range_: int, crit_amount: int, caster_id: int):
    """Arbre de `HadesAutocannonsAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$ExecuteBehaviour` — MIRROR du DECOMPILE :

        crit  = GetVariableForLevel(config, 0x42 = extraCritDmg, abilityState)
        Execute( op_Addition( op_Addition(
            ChangeStat( Owner@0x148, Position(10=CriticalDamage, 0), mode=2=Add, Direct(crit) ),   # [1]
            AttackWithAttackDamage( Owner@0x148, Units(GetAllTargets()),                           # [2]
                                    MinMaxDamage, Direct(GetDamageProfile)=Flame,
                                    Direct(GetHits()=ConfigConst(0x2f)=nrOfHits=6),
                                    AbilityOrEffect(0x47b = 1147), <options> ) ),
            ChangeStat( Owner@0x148, Position(10, 0), mode=3=Subtract, Direct(crit) ) ) )          # [3]

    JUMEAU STRUCTUREL de `HeroicFusilladeAbility IdunBattleLogic.Entities.Abilities.Active.Loki.HeroicFusilladeAbility$$ExecuteBehaviour` (buff crit temporaire NET-NUL encadrant
    l'attaque, meme couple ChangeStat Add/Sub sur `CRIT_DAMAGE` avec source PARTAGEE) — d'ou la meme
    feuille portee `ChangeStat(..., "add"/"revert", src)`.

    - **native_factory = "attack"** (defaut) : le decompile appelle `DSLFactory.AttackWithAttackDamage`
      (VERIFIE par la CALLEE de IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$ExecuteBehaviour ; contraste EntropyCannons/SquigLaunchas =
      `AttackWithAbilityDamage`) -> `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`, 2 tirages/coup a cc=0,
      crit ACTIF (c'est justement ce que le buff [1] alimente).
    - `multi=True` : le selecteur resout N cibles -> `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` attaque CHACUNE
      (ordre = OrderBy par-entite, port = tri par id).
    - Profil `Flame` (PiercingRatio 25, trait OnFire), `nrOfHits`=6, `attackRangeType=Ranged` ->
      `is_melee=False`.
    - Le buff crit est INERTE tant que la `CritChance` du caster est 0 (cas d'une MoW seedee a 0 :
      `_load_machine_stats` ; `combatSnapshot` filtre `EntityType.Unit` -> la CritChance resolue d'une
      MoW n'est pas captable, residu case-mow §8). Il est neanmoins porte 1:1 : des que la CritChance
      devient > 0 (i2 : `DaemonicOrdnance` +20 %/usage), le +extraCritDmg s'applique par coup CRITIQUE."""
    from ...entities.behaviours import op_add
    from ...entities.stats import StatType
    from .behaviours import ChangeStat
    src = (f"{HADES_AUTOCANNONS_ID}_CritDamage", caster_id)            # source PARTAGEE add<->revert
    crit_add = ChangeStat(Caster(), int(StatType.CRIT_DAMAGE), "add", src, amount=int(crit_amount))
    attack = AttackWithAttackDamage(hades_autocannons_get_all_targets(range_), HADES_AUTOCANNONS_ID,
                                    "Flame", is_melee=False, multi=True,
                                    ability_type=int(ActiveAbilityType.HadesAutocannons))
    crit_revert = ChangeStat(Caster(), int(StatType.CRIT_DAMAGE), "revert", src)
    return op_add(op_add(crit_add, attack), crit_revert)


class HadesAutocannonsAbility(ActiveAbility):
    """`HadesAutocannonsAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$ExecuteBehaviour` (id 1147, `blackForgefiend` « Forgefiend »,
    MACHINE OF WAR Black Legion). Arbre DSL `hades_autocannons_tree()` (mirror 1:1) : buff CRIT_DAMAGE
    (+extraCritDmg[level]) -> 6 coups Flame sur la cible ET tous les summons de SON camp a <= range hex
    d'elle (`IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets`) -> retrait du buff.

    Caster = une **MoW hors-plateau** (ni Position ni Health) : `apply_elevation_bonus`/
    `apply_trench_reduction` (famille ATTACK) no-op sans position d'attaquant -> aucun chemin ne suppose
    une tuile de caster. Turn-flags = defauts base (1147 absent des overrides).
    Diag : {crit_amount, targets, attacks:[{target,total}]}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HadesAutocannons)   # 1147
    ABILITY_ID = HADES_AUTOCANNONS_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        from ...entities.effects.magnitude import ability_var
        from ..components import StatsComponent
        if target_id is None:
            return None
        sc = state.get_entity(caster_id).get_component(StatsComponent) if state.get_entity(caster_id) else None
        cctx = sc.ctx if sc is not None else None
        level = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        crit = int(ability_var(self.ABILITY_ID, "extraCritDmg", level, multiplier_pct=mult) or 0)
        rng_const = int(((GC.ability(self.ABILITY_ID) or {}).get("constants") or {}).get("range") or 0)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        hades_autocannons_tree(rng_const, crit, caster_id).execute(entities, ectx)
        attacks = [{"target": p.get("target"), "total": p.get("total")}
                   for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "crit_amount": crit, "range": rng_const,
                "targets": [a["target"] for a in attacks], "attacks": attacks, "dsl": True}


class IncursionAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$ExecuteBehaviour` (id 1021, `blackPossession` "Vitruvius",
    BlackLegion). Invoque JUSQU'A `maxSummons`=6 Bloodletters (`blackSmnBloodletter`), UN PAR ITERATION,
    sur des tuiles LIBRES adjacentes a la cible ; chaque Bloodletter attaque la cible a son apparition.
    La chaine s'arrete des qu'une tuile manque OU que la condition de continuation
    (`IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$GetContinueTrigger` : caster vivant & cible vivante & caster a <= `range`=2 hex) tombe --
    typiquement quand les Bloodletters ONT TUE la cible.

    N'utilise PAS `PerformAIAction` (contrairement a ce que suggerait le regroupement de tache : la face
    COMBAT de 1021 passe par `ChainBehaviour` + on-appearance `UseNormalAttackIfAble`).
    Retour : {spawned, attacks, max_summons, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Incursion)   # 1021
    ABILITY_ID = "Incursion"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(caster_id) is None:
            return None
        consts = (GC.ability(self.ABILITY_ID) or {}).get("constants") or {}
        max_summons = int(consts.get("maxSummons") or 0)      # GetNumberConstant(0x3c)
        ectx = ExecutionContext(state=state, rng=state.rng)
        incursion_tree(state, max_summons).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = [p for n, p in ectx.emitted if n == "UseActiveAbility"]
        return {"spawned": spawned, "attacks": attacks, "max_summons": max_summons, "dsl": True}


# =================================================================================================== #
# DaemonicOrdnance (1148, `blackForgefiend` -- Forgefiend, MachineOfWar) -- lot #90 groupe D
# Patron « COMPOSITE LOURD » : 5 etages heterogenes en UN seul behaviour-seq. Seul de son patron.
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$ExecuteBehaviour` (MIRROR) :
#   extraCritDmg    = GetVariableForLevel(config@0x60, 0x42 = 66 extraCritDmg,    entities)
#   extraCritChance = GetVariableForLevel(config@0x60, 0x41 = 65 extraCritChance, entities)
#   area            = GetTargetAreaTiles()                                    # cf. fonction NOMMEE ci-dessous
#   targets         = Enemies( caster@0x160,
#                              Units( Filter(area, HasEffect(Tiles(Subject@0x180), 5 = Fire)), 1 ), 3 )
#                     (== `DaemonicOrdnanceAbility$$GetAllDamageableTargets`)
#   [1] ChangeStat( owner@0x148, Position(10 = CriticalDamage, 0), mode 2 = Add,
#                   Direct(extraCritDmg), <sel par defaut>, 3, false, false )
#   [2] AttackWithAttackDamage( owner@0x148, targets, MinMaxDamage(this, entities),
#                               Direct(GetDamageProfile(config)) = Plasma,
#                               Direct(GetHits()) = ConfigConst(0x2f) = nrOfHits = 3,
#                               AbilityOrEffect(0x47c = 1148), <opts> )
#   [3] ChangeStat( owner@0x148, Position(10, 0), mode 3 = Subtract, Direct(extraCritDmg), ... )
#   [4] If( HasEffect(owner@0x148, 0x524 = 1316 DaemonicOrdnance_ExtraCritChance, 0, 6),
#           AddOrUpdateStaticStatModifierEffect( owner@0x148, 0x524, 9 = CriticalChance,
#               Multiply( Sum(TotalActiveAbilityUsed(owner@0x148, 0x47c), Get(1)),
#                         Direct(extraCritChance) ), 0, false ),
#           null )
#   [5] AddEffect( 5 = Fire, AbilityStateReference, source = owner@0x148, targets = area, options ZERO )
#   AActiveAbility.Execute( ((((1 + 2) + 3) + 4) + 5), entities )       # Execute PLAIN, op_Addition x4
#
# LECTURES A NE PAS INVERSER (le case doc les avait croisees) : c'est `extraCritDmg` (var 0x42) qui
# encadre l'attaque sur `CriticalDamage` (stat 10), et `extraCritChance` (var 0x41) qui alimente le
# stat-modifier CUMULATIF sur `CriticalChance` (stat 9).
#
# 2-PHASES PAR CONSTRUCTION : l'attaque ne frappe que les ennemis debout sur une tuile DEJA EN FEU ;
# le feu, lui, est pose EN FIN de ce meme cast ([5], apres l'attaque) -> un 1er cast ne fait AUCUN
# degat (il allume la zone), le SUIVANT frappe ce qui s'y trouve encore. C'est la structure native,
# pas une degradation du port.
#
# L'effet 1316 n'est PAS cree ici : sa creation/suppression appartient aux triggered
# `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnance_AddCritChance$$CreateBehaviour`
# (`AddStaticStatModifierEffectToOwner(0x524, 9, Get(0))`) et `..._RemoveCritChance$$CreateBehaviour`
# (`If(CriticalHitsThisTurn(owner) >= GetHits2, RemoveEffect(owner, 0x524))`) -- HORS de ce port ;
# d'ou le gate `If(HasEffect(owner, 0x524))` de l'etage [4], INERTE tant que ces triggered ne sont pas
# portes (residu documente).
# =================================================================================================== #

DAEMONIC_ORDNANCE_ID = "DaemonicOrdnance"
DO_EXTRA_CRIT_CHANCE_EFFECT = int(EffectType.DaemonicOrdnance_ExtraCritChance)   # 0x524 = 1316
DO_FIRE = int(EffectType.Fire)                                            # 5 = feu de tuile
# `MachineOfWarPosition.Bottom` = 2, litteral passe a `IsPositionMachineForCurrentPlayer(2)`
# (`DaemonicOrdnanceAbility$$IsBottomPlayer`, MEME construction que MacroPlasmaIncinerator).
DO_MACHINE_POSITION_BOTTOM = 2


def daemonic_ordnance_target_area_tiles(target_sel):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$GetTargetAreaTiles`
    (MIRROR 1:1) :

        dir = If( IsPositionMachineForCurrentPlayer(2), Direct(1), Direct(4) )     # == IsBottomPlayer
        return TilesOnSameElevation( target@0x178, TilesInTriangleShape(target@0x178, dir), maxDiff = 1 )

    = la tuile ciblee + les DEUX voisines du coin `dir` (`IdunBattle.Core.Services.BattleQuery$$GetTilesInTriangleShape` :
    dir=1 -> {S, SE}, dir=4 -> {NW, N}), filtrees sur un ecart d'elevation <= 1 avec la tuile ciblee.

    ⚠ CONTRASTE `MacroPlasmaIncineratorAbility$$ExecuteBehaviour` : AUCUN `Walkable` ici (le feu se pose
    sur des tuiles non marchables aussi). Ne pas recopier le filtre de l'autre MoW."""
    direction = FormulaIf(IsPositionMachineForCurrentPlayer(DO_MACHINE_POSITION_BOTTOM),
                          Const(1), Const(4))
    return TilesOnSameElevation(target_sel, TilesInTriangleShape(target_sel, direction), 1)


def daemonic_ordnance_all_damageable_targets(target_sel):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$GetAllDamageableTargets`
    (MIRROR) = `Enemies(caster@0x160, Units(Filter(GetTargetAreaTiles(), HasEffect(Tiles(Subject@0x180),
    5 = Fire)), 1), 3)` : les ENNEMIS debout sur une tuile de la zone qui PORTE DEJA l'effet de feu.

    Le `Filter` lie chaque TUILE de la zone au slot sujet et teste l'effet sur cette entite-tuile
    (`HasEffect` domaine mixte, cf. `entities/triggers.py`)."""
    area = daemonic_ordnance_target_area_tiles(target_sel)
    burning = Filter(area, HasEffect(Subject(), DO_FIRE))
    return Enemies(Units(burning))


def daemonic_ordnance_tree(target_sel, extra_crit_dmg: int, extra_crit_chance: int):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$ExecuteBehaviour`
    (MIRROR 1:1 des 5 etages, cf. le bloc de commentaire) :

        op_Addition x4 ( ChangeStat(+extraCritDmg sur CRITICAL_DAMAGE),
                         AttackWithAttackDamage(<ennemis sur tuiles en feu>),
                         ChangeStat(-extraCritDmg),
                         If(HasEffect(owner, 1316), AddOrUpdateStaticStatModifierEffect(...)),
                         AddEffect(Fire -> zone) )

    - le buff/debuff ENCADRE l'attaque (meme patron NET-NUL que HeroicFusillade) : la feuille `ChangeStat`
      `mode="add"` puis `mode="revert"` sur la MEME cle de source -> revert EXACT par-source.
    - l'attaque route `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (famille ATTACK :
      crit/block, 2 tirages/coup) -> `native_factory="attack"` (DEFAUT) -- c'est justement pourquoi le
      bonus de CriticalDamage est encadre.
    - `Fire` (5) : options natives ZERO -> `DefaultAmountOfRounds(5) = 2` rounds, converti DANS
      `AddEffectOperation` (`duration_rounds=None` cote port)."""
    src_key = f"DaemonicOrdnance:{id(target_sel)}"        # cle de source PARTAGEE add <-> revert
    buff = ChangeStat(Caster(), int(StatType.CRIT_DAMAGE), "add", src_key, extra_crit_dmg)
    attack = AttackWithAttackDamage(daemonic_ordnance_all_damageable_targets(target_sel),
                                    DAEMONIC_ORDNANCE_ID, "Plasma", is_melee=False, multi=True,
                                    ability_type=int(ActiveAbilityType.DaemonicOrdnance))
    unbuff = ChangeStat(Caster(), int(StatType.CRIT_DAMAGE), "revert", src_key)
    amount = Multiply(Sum(TotalActiveAbilityUsed(Caster(), int(ActiveAbilityType.DaemonicOrdnance)),
                          Const(1)),
                      Const(int(extra_crit_chance)))
    cumul = IfBehaviour(
        HasEffect(Caster(), DO_EXTRA_CRIT_CHANCE_EFFECT),
        add_or_update_static_stat_modifier_effect(
            Caster(), DO_EXTRA_CRIT_CHANCE_EFFECT, int(StatType.CRIT_CHANCE), amount,
            name=EffectType.DaemonicOrdnance_ExtraCritChance.name))
    fire = AddEffect(DO_FIRE, EffectType.Fire.name,
                     daemonic_ordnance_target_area_tiles(target_sel), duration_rounds=None)
    return op_add(op_add(op_add(op_add(buff, attack), unbuff), cumul), fire)


class DaemonicOrdnanceAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$ExecuteBehaviour` (id 1148,
    `blackForgefiend` -- Forgefiend, Black Legion, MACHINE OF WAR) — cf. le bloc de commentaire.

    Kit gameconfig 1148 : `damageProfile=Plasma`, `nrOfHits=3` (+`nrOfHits_2=3`, non lu par ce behaviour),
    `minDmg`/`maxDmg`/`extraCritDmg`[level] (rarity-affected), `extraCritChance`[level],
    `attackRangeType=Ranged`, `initialCooldownTurns=1`.

    OBSERVABLE : (1) la zone-triangle autour de la cible s'embrase (`EnvFireTile` 5, 2 rounds) ;
    (2) les ennemis DEJA sur une tuile en feu prennent 3 coups Plasma avec +extraCritDmg de degat critique
    (buff pose puis retire autour de l'attaque -- net nul sur la fiche apres le cast) ; (3) si la MoW porte
    deja `DaemonicOrdnance_ExtraCritChance` (1316), son montant est rafraichi a
    `(nbUsages + 1) x extraCritChance` sur `CriticalChance`.

    Turn-flags = defauts base (1148 absent des overrides). Retour : {attacks, burned_tiles, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.DaemonicOrdnance)   # 1148
    ABILITY_ID = DAEMONIC_ORDNANCE_ID

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        from ...entities.effects.magnitude import ability_var
        from ..components import StatsComponent
        if target_id is None:
            return None
        ce = state.get_entity(caster_id)
        sc = ce.get_component(StatsComponent) if ce is not None else None
        cctx = sc.ctx if sc is not None else None
        level = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        crit_dmg = int(ability_var(self.ABILITY_ID, "extraCritDmg", level, multiplier_pct=mult) or 0)
        crit_chance = int(ability_var(self.ABILITY_ID, "extraCritChance", level,
                                      multiplier_pct=mult) or 0)
        # `target@0x178` : l'ability cible une UNITE ; si le message porte un id de TUILE (cast
        # tile-target), on presente la tuile au domaine tile-selecteur (meme normalisation que Malleus).
        if state.get_entity(target_id) is not None:
            target_sel = Target()
        elif state.board is not None and target_id in state.board.by_id:
            target_sel = FixedTileIds([int(target_id)])
        else:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        daemonic_ordnance_tree(target_sel, crit_dmg, crit_chance).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        attacks = [{"target": p.get("target"), "total": p.get("total")}
                   for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        burned = [p.get("target") for n, p in ectx.emitted
                  if n == "AddEffect" and p.get("effect_type") == DO_FIRE and p.get("placed")]
        stat_mods = [p for n, p in ectx.emitted if n == "AddStaticStatModifierEffect"]
        return {"ability": DAEMONIC_ORDNANCE_ID, "caster": caster_id, "target": target_id,
                "attacks": attacks, "burned_tiles": burned, "stat_mods": stat_mods,
                "extra_crit_dmg": crit_dmg, "extra_crit_chance": crit_chance, "dsl": True}
