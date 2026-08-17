"""Abilities BlackLegion (namespace natif `Abilities.Active.Loki.*`) — case-220 §6.11.

Module DEDIE a la faction Black Legion (comme `genestealer.py`/`deathguard.py` : une classe par ability,
l'arbre SPECIFIQUE vit avec sa classe). RE ghidra gqfc5mff6c (VA citees). Doc : docs/rl/case-220/black-legion.md.

Contenu :
- `BringerOfDespair` (1022, Angrax `blackTerminator`) — attaque MAIN 4x Power sur la cible + bonus 4x Power
  sur UN ennemi aleatoire adjacent au CASTER (template splash `loki/splash.py`, factory attack).
- `Incursion` (1021, Vitruvius `blackPossession`) — `ChainBehaviour` de spawns Bloodletter adjacents a la
  cible + on-appearance `UseNormalAttackIfAble` (case-220 P0-SUMMON).
- `FrenziedFiring` (1036, Volk `blackObliterator`) — attaque ORIGINE a base GEOMETRIQUE + volet AoE 1 coup
  sur les ennemis de l'anneau de la cible (case-61, face COMBAT).
- `Drachnyen` (1029, Abaddon `blackAbaddon`) — SetHealth(Min(MaxHealth, hp)) & AddEffect(1471) & attaque
  NORMALE dirigee sur la cible (case-bl-1029-1020).
- `HeraldOfTheApocalypse` (1020, Haarken `blackHaarken`) — nrOfHits x Piercing sur la cible ET l'ennemi
  DIRECTEMENT DERRIERE elle & AddEffect(1027) sur les memes & TriggerAbility(BattleFatigue) sur les ennemis
  du disque rayon `range` autour de la cible (case-bl-1029-1020).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.abilities.active_ability import FrenziedFiringAbility
from ...entities.behaviours import (AtomicGroup, ChainBehaviour, If as IfBehaviour, SetCache,
                                    op_add, op_and)
from ...entities.formulas import (If as FormulaIf, Min, Multiply, StatAmount, Sum,
                                  TotalActiveAbilityUsed)
from ...entities.selectors.accessors import (
    ActiveTarget, CasterTile, FixedTileIds, SelectTile, Subject, Target
)
from ...entities.selectors.geometry import (
    Nothing, Null, PickFirstN, TilesBehindInLine, TilesInTriangleShape, TilesOnSameElevation
)
from ...entities.selectors.tiles import AdjacentTiles, CanAddUnit, Caster
from ...entities.selectors.units import (
    AdjacentUnits, Damageable, Enemies, Filter, Friends, SortByDistance, Sub, SurroundingUnits,
    Tiles, Union, Units
)
from ...entities.triggers import (HasEffect, IsAlive, IsInRange, IsPositionMachineForCurrentPlayer,
                                  TriggerAnd)
from ...entities.effect_type import EffectType
from ...entities.stats import StatPart, StatType
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.triggered_ability_type import TriggeredAbilityType
from ...entities.unit_selection_type import UnitSelectionType

#: `UnitSelectionType` LU au dernier argument des `DSLSelectors$$*` de ce fichier -- releve #585-r1,
#: build `rnca9r7q6c`, littéral par littéral (jamais par symetrie).
#: `OnlyAliveAndTargetable` = `IsAlive && !HasFlag(UnitFlag.Untargetable)`, applique PAR ELEMENT par
#: `IdunBattle.DSL.TargetsSelector$$SelectUnit` -> `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType`.
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3
from .base import ActiveAbility
from .behaviours.combat import AttackWithAttackDamage, UseActiveAbility
from .behaviours.context import entities_from_state
from .behaviours.effects import AddEffect, add_or_update_static_stat_modifier_effect
from .behaviours.lifecycle import TriggerAbility
from .behaviours.stats import ChangeStat, SetHealth
from .behaviours.summon import Spawn
from .targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGE_WHOLE_BOARD,
                        RANGED_BOOL_FALSE, RANGED_BOOL_IF_RANGED_CASTER, RANGED_BOOL_TRUE,
                        TargetingOptions)
from .targeting_rule import TargetingRule as TR
from ...entities.ability_constant_type import AbilityConstantType   # #270-r1-r1-r3
from ...entities.ability_variable_type import AbilityVariableType   # #270-r1-r1-r3
# #270-r4 : direction de BattleQuery.GetTilesInTriangleShape, type DECLARE lu dans
# rida/methods.tsv (IdunBattleLogic.Utils.Hex.Corner, pas l'un des cinq homonymes Unity).
from ...hex_corner import Corner
from ...entities.effects.magnitude import ability_var
from ...entities.selectors.accessors import TargetTile
from ...entities.selectors.units import SurroundingUnits, Tiles, Units, UnitsWithTrait
from ...entities.traits.unit_trait import UnitTrait
from ..components import StatsComponent
from ..abilities.loki.splash import _pick_randomly_n

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
      `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (VERIFIE par les CALLEES de IdunBattleLogic.Entities.Abilities.Active.Loki.BringerOfDespairAbility$$ExecuteBehaviour, PAS au nom du
      commentaire — cf. rngcrit-1202/tip #2), famille attack, JAMAIS `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage`.

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
    # #585-r1 : `AdjacentUnits(gs, gs@0x50, unique: 1, 3)` puis `Enemies(gs, gs@0x30, ., 3)` --
    # littéraux LUS. (Le `AdjacentUnits` du port ne porte pas encore le parametre : etage manquant,
    # sans consequence ici puisque l'`Enemies` enveloppant filtre la sortie.)
    bonus_sel = Sub(Damageable(Enemies(AdjacentUnits(CasterTile(), Const(1)),
                                       selection_type=SELECTION)), Target())  # adjacents-caster (ennemis, PV>0) − cible
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

    # GATE DE CIBLE (#115) — FORME 3 « PRESET STATIQUE COPIE » (la 3e des trois).
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.BringerOfDespairAbility$$.ctor` n'appelle
    # AUCUN `IdunBattle.Core.Services.TargetingOptions$$.ctor` : il recopie les 0x40 octets du champ
    # STATIQUE de `TargetingOptions` a l'offset RELATIF `+0x40` du bloc `<class>+0xb8`, puis :
    #     AActiveAbility..ctor(this, &opts, 0, 0)      # 3e arg = 0 = AbilityAttackType.DirectTargetAttack
    # Le masque EFFECTIF est donc la constante ecrite par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` = `*(statics+0x68)` =
    # **0x4000**, PAS un litteral du ctor. Decomposition EXHAUSTIVE (un seul bit, aucun residu) :
    #     0x4000  (bit 14) TargetIsEnemy -> PORTE (`TargetingQuery$$UnitsCanAttackEachOther`) :
    #             refus sur soi-meme et sur un allie.
    # `TargetMatchesDynamicRule` (0x2) est ABSENT -> le natif ne consulte AUCUNE regle dynamique.
    # PORTEE : le MEME preset porte `<preset>+0x08..0x1f` <- `TargetingRange` statique `+0x30`
    # (`TargetingRange$$.cctor` : `onlyAdjacent = 0 = RangedBool.True`, `overrideRange = Nullable(1)`)
    # = `RANGE_ADJACENT` -> branche `battleQuery.AreEntitiesAdjacent`, PAS un `dist <= N`.
    # `forceMeleeTarget` = `<preset>+0x20` = `*(statics+0x60)` = **1** = `RangedBool.False`.
    # Coherent avec `attackRangeType=Melee` et l'i2 (« 4x ... to an adjacent enemy »), et la config
    # 1022 ne porte AUCUNE cle `range` (damageProfile/nrOfHits/nrOfHits_2 seulement).
    # MEME PRESET que 1020 HeraldOfTheApocalypse (ci-dessous) et que 1122 CordClaw — mais PAS que
    # 1029 Drachnyen, qui recopie le meme `+0x40` et enchaine sur la surcharge PRESET + flags
    # (`0x200000000 | 0x4000`). C'est la FORME du ctor qui tranche, jamais le preset seul.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

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
CONST_INCURSION_RANGE = AbilityConstantType.range        # GetNumberConstant(0x16) -> "range"       = 2  (MEME index que 1028)
CONST_INCURSION_MAX_SUMMONS = AbilityConstantType.maxSummons  # GetNumberConstant(0x3c) -> "maxSummons"  = 6


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
CONST_HADES_RANGE = AbilityConstantType.range          # GetNumberConstant(0x16) -> "range" = 2
VAR_EXTRA_CRIT_DMG = AbilityVariableType.extraCritDmg         # GetVariableForLevel(0x42) -> "extraCritDmg"
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
    **CIBLE INCLUSE** (`IdunBattleLogic.Entities.DSLSelectors$$SurroundingTiles(..., includeCenter=1) : param!=0 -> selecteur direct,
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
    # #585-r1 : `SurroundingUnits(gs, gs@0x60, range, unique: 1, includeCenter: 1, 3)` -- littéral LU.
    ring = SurroundingUnits(TargetTile(), Const(int(range_)), include_center=True,
                            selection_type=SELECTION)                                # includeCenter=1
    # #585-r1 : `Friends(gs, gs@0x60 = Target, SurroundingUnits(..., 3), 3)` puis
    # `UnitsWithTrait(gs, ., 0x2 Summon, 3)` -- littéraux LUS au decompile de `$$GetAllTargets`.
    summons = UnitsWithTrait(Friends(ring, reference=Target(), selection_type=SELECTION),
                             int(UnitTrait.Summon), selection_type=SELECTION)
    # ⚠ Le `Units(...)` ci-dessous ne recoit RIEN : `$$GetAllTargets` enchaine `Tiles(sel)` ->
    # `SortByRow`/`SortReverse`/`If`, il n'y a AUCUN `Units(...)` natif a cet etage -- c'est la
    # materialisation du retour tuile -> occupant. Inventer un `selectionType` sur un noeud absent
    # du natif serait pire que l'absence ; et le filtre est deja arme en amont, sur les deux
    # selecteurs qui existent, eux.
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
    - Le buff crit est INERTE tant que la `CritChance` du caster est 0. C'est bien l'etat d'une MoW,
      et ce n'est PLUS un residu de capture : depuis `d9d0008` (#128) `combatSnapshot` remonte AUSSI les lignes
      `EntityType.Machine`, et `_load_machine_stats` les consomme (#174) -- la CritChance resolue
      d'une MoW y est MESUREE a 0 (comme ses 18 autres stats), conforme a son gameconfig
      (`stats={Health:0,Damage:0,FixedArmor:0}`). Le buff est neanmoins porte 1:1 : des que la
      CritChance devient > 0 (i2 : `DaemonicOrdnance` +20 %/usage), le +extraCritDmg s'applique par
      coup CRITIQUE."""
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

    # GATE DE CIBLE (#115) — FORME 1 « FLAGS DIRECTS » (la 1re des trois).
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$.ctor` :
    #     opts = {0}                                            # les 0x40 octets mis a zero d'abord
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, range=&<TargetingRange statics+0x48>,
    #                            forceMeleeTarget=1, rules=0x46006000, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 0, 0)      # 3e arg = 0 = AbilityAttackType.DirectTargetAttack
    # La surcharge appelee est celle a FLAGS DIRECTS (elle ecrit `*(options+0x28) = param_5`), PAS
    # l'overload PRESET + flags qui ferait `+0x28 = flags | preset.+0x28` : le litteral EST donc le
    # masque effectif. Decomposition EXHAUSTIVE (`IdunBattle.Core.Services.TargetingRule`) --
    # 0x2000 + 0x4000 + 0x6000000 + 0x40000000 = 0x46006000, aucun bit residuel :
    #     0x2000       (bit 13) TargetIsSummon      -> la cible doit porter `UnitTrait.Summon` (2).
    #                  NON PORTE (degradation permissive, cf. l'inventaire de `targeting.py`). C'est
    #                  le pendant DECISION du `UnitsWithTrait(..., 2 = Summon)` de
    #                  `IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets`.
    #     0x4000       (bit 14) TargetIsEnemy       -> PORTE : refus sur soi-meme et sur un allie.
    #     0x2000000    (bit 25) AllowObscuredTargetByElevation
    #     0x4000000    (bit 26) AllowObscuredTargetByWalls
    #                  (les deux ensemble = le composite natif `AllowObscuredTarget` = 0x6000000)
    #                  -> DESARMENT de la ligne de vue, elle-meme NON PORTEE : sans effet offline.
    #     0x40000000   (bit 30) AllowNullCasterTile -> volet CASTER, NON PORTE. Il est ici parce que
    #                  le caster est une MACHINE OF WAR hors-plateau (ni Position ni Health) : sans
    #                  ce bit le natif refuserait tout cast d'une MoW.
    # PORTEE : `TargetingRange` statique `+0x48` (`TargetingRange$$.cctor` : `useWholeBoard = true`,
    # `onlyAdjacent = 1 = RangedBool.False`, `overrideRange` nul) = `RANGE_WHOLE_BOARD` -> le filtre
    # statique NE TESTE PAS la portee. La constante `HadesAutocannons.constants.range` (2) n'est
    # donc PAS la portee de CIBLAGE : elle n'alimente que le disque `SurroundingUnits` de
    # `GetAllTargets`. `forceMeleeTarget` = 1 = `RangedBool.False` (jamais consulte sous
    # `UseWholeBoard`, qui court-circuite `GetRange` avant le clamp melee).
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetIsSummon
        | TR.TargetIsEnemy
        | TR.AllowObscuredTargetByElevation
        | TR.AllowObscuredTargetByWalls
        | TR.AllowNullCasterTile),
        range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
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

    # GATE DE CIBLE (#115) — FORME 1 « FLAGS DIRECTS ».
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$.ctor` :
    #     opts = {0}
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, range=&<TargetingRange statics+0x18>,
    #                            forceMeleeTarget=2, rules=0x4020, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 1, 0)     # 3e arg = 1 = AbilityAttackType.SummonAndAttackTarget
    # Surcharge FLAGS DIRECTS (`*(options+0x28) = param_5`) -> le litteral EST le masque.
    # Decomposition EXHAUSTIVE : 0x20 + 0x4000 = 0x4020, aucun bit residuel :
    #     0x20    (bit 5)  TargetHasFreeAdjacentTile -> PORTE : la cible doit avoir >= 1 tuile LIBRE
    #             au contact (`battleQuery` slot 0x51). C'est le pendant DECISION exact du
    #             `CanAddUnit(AdjacentTiles(Target()))` de
    #             `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$GetNextSpawnTile` :
    #             sans tuile libre autour de la cible, la chaine de spawns n'aurait rien a poser.
    #     0x4000  (bit 14) TargetIsEnemy -> PORTE : refus sur soi-meme et sur un allie.
    # `TargetMatchesDynamicRule` (0x2) est ABSENT -> aucune regle dynamique consultee.
    # PORTEE : `TargetingRange` statique `+0x18` (`TargetingRange$$.cctor` :
    # `onlyAdjacent = 1 = RangedBool.False`, `useRangeFromConfig = true`, `useWholeBoard = false`,
    # `overrideRange` nul) = `RANGE_FROM_CONFIG` -> `AActiveAbility$$SetConfigValuesInTargetingOptions`
    # pose `overrideRange = GetNumberConstant(0x16 range)` = `Incursion.constants.range` = **2**
    # (la MEME constante que celle lue par `GetContinueTrigger`/`incursion_next_spawn_tile`).
    # `forceMeleeTarget` = **2** = `RangedBool.IfRangedCaster` : `RangedBoolExtensions$$IsTrue` rend
    # `IsRanged(caster)`, et `blackPossession` PORTE une arme a `Range` 2 -> le terme est ARME. Des
    # qu'un ennemi est au contact du caster (`AttackQuery$$ShouldApplyRangedInMelee`), `GetRange`
    # clampe a `Math.Min(1, v)` + `onlyAdjacent = true` : la portee de ciblage tombe de 2 a
    # l'ADJACENCE. C'est le seul des cinq masques de ce module ou ce champ MORD.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetHasFreeAdjacentTile | TR.TargetIsEnemy,
        range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_IF_RANGED_CASTER)

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
    # #270-r4 : le 2e argument de BattleQuery\$\$GetTilesInTriangleShape est DECLARE
    # direction : IdunBattleLogic.Utils.Hex.Corner dans rida/methods.tsv (le nom court aurait
    # apparie l'un des CINQ autres Corner Unity/SimpleUI du build).
    direction = FormulaIf(IsPositionMachineForCurrentPlayer(DO_MACHINE_POSITION_BOTTOM),
                          Const(int(Corner.NorthEast)), Const(int(Corner.SouthWest)))
    return TilesOnSameElevation(target_sel, TilesInTriangleShape(target_sel, direction), 1)


def daemonic_ordnance_all_damageable_targets(target_sel):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$GetAllDamageableTargets`
    (MIRROR) = `Enemies(caster@0x160, Units(Filter(GetTargetAreaTiles(), HasEffect(Tiles(Subject@0x180),
    5 = Fire)), 1), 3)` : les ENNEMIS debout sur une tuile de la zone qui PORTE DEJA l'effet de feu.

    Le `Filter` lie chaque TUILE de la zone au slot sujet et teste l'effet sur cette entite-tuile
    (`HasEffect` domaine mixte, cf. `entities/triggers.py`)."""
    area = daemonic_ordnance_target_area_tiles(target_sel)
    burning = Filter(area, HasEffect(Subject(), DO_FIRE))
    # #585-r1 : `Units(gs, Filter(...), unique: 1, 3)` puis `Enemies(gs, gs@0x48, ., 3)` -- les DEUX
    # littéraux LUS au decompile de `$$GetAllDamageableTargets`.
    return Enemies(Units(burning, selection_type=SELECTION), selection_type=SELECTION)


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
    - l'attaque route `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (famille ATTACK :
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

    # GATE DE CIBLE (#115) — FORME 1 « FLAGS DIRECTS ».
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$.ctor` :
    #     opts = {0}
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, range=&<TargetingRange statics+0x48>,
    #                            forceMeleeTarget=1, rules=0x46000040, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 0, 0)      # 3e arg = 0 = AbilityAttackType.DirectTargetAttack
    # Surcharge FLAGS DIRECTS -> le litteral EST le masque. Decomposition EXHAUSTIVE :
    # 0x40 + 0x6000000 + 0x40000000 = 0x46000040, aucun bit residuel :
    #     0x40         (bit 6)  TargetIsTile -> PORTE : l'ability cible une TUILE, et la cascade
    #                  REFUSE (litteral `1` = `TargetingRule.ValidRequest`, cf. `targeting.py`) une
    #                  tuile-cible NON MARCHABLE, `AllowUnwalkableTargetTile` (bit 43) etant ABSENT.
    #                  C'est ce bit qui explique le `FixedTileIds` d'`execute_behaviour` ci-dessous,
    #                  et il CONTRASTE avec le `TargetIsEnemy` de 1147 : le triangle de feu se pose
    #                  sur une TUILE, pas sur une unite.
    #     0x2000000    (bit 25) AllowObscuredTargetByElevation
    #     0x4000000    (bit 26) AllowObscuredTargetByWalls   (composite natif `AllowObscuredTarget`)
    #                  -> DESARMENT de la ligne de vue, elle-meme NON PORTEE : sans effet offline.
    #     0x40000000   (bit 30) AllowNullCasterTile -> volet CASTER, NON PORTE ; present parce que
    #                  le caster est une MACHINE OF WAR hors-plateau.
    # AUCUNE regle de CAMP : ni `TargetIsEnemy` ni `TargetIsFriendly`. Le natif accepte donc toute
    # tuile marchable des DEUX camps -- c'est bien ce que fait l'ExecuteBehaviour, qui embrase la
    # zone puis ne frappe que les ENNEMIS deja en feu (`GetAllDamageableTargets`, filtre d'EXECUTION,
    # pas de ciblage). Ne PAS inventer un refus par camp ici.
    # PORTEE : `TargetingRange` statique `+0x48` = `RANGE_WHOLE_BOARD` -> aucun test de portee.
    # `forceMeleeTarget` = 1 = `RangedBool.False` (jamais consulte sous `UseWholeBoard`).
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetIsTile
        | TR.AllowObscuredTargetByElevation
        | TR.AllowObscuredTargetByWalls
        | TR.AllowNullCasterTile),
        range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

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


# ================== FrenziedFiring (blackObliterator `Volk`, actif 1036) -- case-61 volet AoE COMBAT =========
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$ExecuteBehaviour`
# (MIRROR du DECOMPILE -- l'artefact qui manquait au cas #61, jamais lu jusqu'ici) :
#
#     hitsNode = GetHitsForOriginalTarget(this)                                  # noeud VALEUR geometrique
#     dmg      = AActiveAbility.MinMaxDamage(this, level)                        # bornes minDmg/maxDmg
#     prof     = Nullable(AActiveAbility.GetDamageProfile(this))                 # profil config = HeavyRound
#     src      = AbilityOrEffect.op_Implicit(this+0x10)                          # = ActiveAbilityType 1036
#     A = op_BitwiseAnd( SetCache(hitsNode),                                             # displayClass+0x10
#                        AttackWithAttackDamage(caster@0x160, target@0x178, dmg, prof,
#                                               hits = hitsNode,      src, opts=0) )
#     B = op_BitwiseAnd( SetCache(hitsNode),                                             # displayClass+0x18
#                        AttackWithAttackDamage(caster@0x160,
#                                               AdjacentEnemies(caster@0x160, targetTiles@0x190, 1),
#                                               dmg, prof,
#                                               hits = DSLFactory.Direct(1), src, opts=0) )
#     AtomicGroup( 0x4e, OnProjectileFinishedCallback(displayClass, <ExecuteBehaviour>b__0) )
#         ou `<ExecuteBehaviour>b__0` = Execute( op_Addition(A, B) )              # A PUIS B, dans l'ordre
#
# CE QUE LA LECTURE APPREND, ET QU'ON NE POUVAIT PAS DEDUIRE DE LA FACE DECISION :
#   1. la face COMBAT emet bien DEUX volets (elle N'EST PAS mono-cible) ; le 2e reprend le MEME selecteur
#      `AdjacentEnemies(caster, TargetTiles@0x190, 1)` que `FrenziedFiringAbility$$GetTargets` que le
#      playbook consomme -> la feuille `_AOE` deja portee est REUTILISEE telle quelle (aucun 2e port) ;
#   2. le nb de coups du volet AoE est un `DSLFactory.Direct(1)` -- un noeud CONSTANT construit au
#      call-site, PAS `GetNumberConstant(0x2f)` (qui vaut aussi 1 : le recopier serait une coincidence).
#      C'est la MEME constante native que le `hits = 1` LITTERAL du 2e batch du playbook -> `AOE_HITS` ;
#   3. les DEUX volets partagent le MEME noeud `hitsNode`, et chacun est PRECEDE de son propre
#      `SetCache(hitsNode)` : la geometrie est FIGEE avant la 1re attaque, donc le batch AoE ne peut pas
#      la re-mesurer apres que les coups du batch 1 ont mute l'etat (le 2e SetCache retombe sur le cache) ;
#   4. `AttackWithAttackDamage` sur les DEUX volets => famille ATTACK => le canal de coups partage
#      (`GetAttackHits`, case-61 §1.2) s'interpose sur les DEUX -- y compris sur la base 1 de l'AoE ;
#   5. AUCUN `Foreach` : le selecteur multi-cible est passe DIRECTEMENT a UNE feuille d'attaque (patron
#      HarvesterOfSouls/PlasmaGrenade) -> `multi=True` (l'`OrderBy` de `AttackBehaviour$$Execute` folde
#      en un tri par id) ;
#   6. AUCUN noeud d'effet, AUCUN spawn, AUCUN stat-mod : la face COMBAT de 1036 est PUREMENT deux
#      attaques. (`SuppressiveFire`/`LetTheGalaxyBurn` de Volk sont des TRAITS, hors de cet arbre.)
FRENZIED_FIRING_ID = "FrenziedFiring"
CONST_FF_NR_OF_HITS = AbilityConstantType.nrOfHits        # GetNumberConstant(0x2f) -> "nrOfHits"    = 1  (via ArmoriumCherub.GetHits)
CONST_FF_MAX_NR_OF_HITS = AbilityConstantType.maxNrOfHits    # ConfigConst(0x48)       -> "maxNrOfHits" = 10


def frenzied_firing_tree(n_hits: int, max_hits: int) -> AtomicGroup:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$ExecuteBehaviour`
    (MIRROR du DECOMPILE ; cf. le bloc de commentaire ci-dessus) :

        AtomicGroup( op_Addition(
            op_BitwiseAnd( SetCache(hitsNode),
                           AttackWithAttackDamage(Target(), hits = hitsNode) ),          # [ORIGINE]
            op_BitwiseAnd( SetCache(hitsNode),
                           AttackWithAttackDamage(AdjacentEnemies(TargetTile(), 1),
                                                  hits = Direct(1), multi) ) ) )         # [AoE]

    - `hitsNode` = `FrenziedFiringAbility.get_hits_for_original_target(nrOfHits, maxNrOfHits)` =
      L'ARBRE PARTAGE avec la face DECISION (definition UNIQUE ; instance FRAICHE par cast car son
      `Cache` est stateful). Passe TEL QUEL (noeud, pas int) a la feuille d'ORIGINE : c'est
      `AttackDamageBehaviour$$ExecuteTarget` qui l'evalue -- et il tombe sur le cache que le
      `SetCache` amont vient de figer, exactement comme le natif.
    - le volet AoE reutilise `FrenziedFiringAbility._AOE` (= `GetTargets`, deja porte et live-valide
      sur la face DECISION) et `FrenziedFiringAbility.AOE_HITS` enveloppe en `Const` (= `Direct(1)`).
      Le selecteur est NU (sans `Damageable`) : le filtre VIVANT vient de `UnitsOnTilesSelector$$Select`
      (occupation de tuile), que `_within` mirrore.
    - profil `HeavyRound` (`GetDamageProfile` config), `attackRangeType=Ranged` -> `is_melee=False` sur
      les DEUX volets ; `native_factory="attack"` (defaut) = la factory VERIFIEE au decompile
      (`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`, 2 tirages/coup a cc=0), JAMAIS `AttackWithAbilityDamage`.
    - `ability_type=1036` (`AbilityOrEffect(this+0x10)`) threade sur les deux feuilles (payload after-hit).
    - ordre = ORIGINE puis AoE (`op_Addition` gauche->droite, cibles AoE triees par id = `OrderBy` natif)
      -> meme sequence `state.rng` que le natif ; `AtomicGroup` (tag 0x4e) inline (#201)."""
    ability_type = int(ActiveAbilityType.FrenziedFiring)
    hits_node = FrenziedFiringAbility.get_hits_for_original_target(n_hits, max_hits)   # uVar10 (PARTAGE)
    origin = AttackWithAttackDamage(Target(), FRENZIED_FIRING_ID, "HeavyRound", is_melee=False,
                                    hits_override=hits_node, ability_type=ability_type)
    aoe = AttackWithAttackDamage(FrenziedFiringAbility._AOE, FRENZIED_FIRING_ID, "HeavyRound",
                                 is_melee=False, multi=True,
                                 hits_override=Const(FrenziedFiringAbility.AOE_HITS),  # Direct(1)
                                 ability_type=ability_type)
    return AtomicGroup(op_add(op_and(SetCache(hits_node), origin),
                              op_and(SetCache(hits_node), aoe)))


class FrenziedFiringAbilityCombat(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$ExecuteBehaviour` (id 1036,
    `blackObliterator` « Volk », Black Legion) — face COMBAT, arbre DSL (`frenzied_firing_tree`).

    Kit gameconfig 1036 : `damageProfile=HeavyRound` (pierce 55), `attackRangeType=Ranged`, `nrOfHits=1`,
    `maxNrOfHits=10`, `range=3`, `minDmg`/`maxDmg`[level] (rarity-affected).

    OBSERVABLE : (1) la CIBLE encaisse `min(nrOfHits + <tuiles adjacentes marchables non tenues par un
    ennemi du caster>, maxNrOfHits)` coups HeavyRound -- base GEOMETRIQUE, donc 7 coups sur une cible en
    plein champ et moins des qu'elle est adossee/entouree d'ennemis ; (2) CHAQUE ennemi du caster pose sur
    l'anneau hex de la cible encaisse EN PLUS **1** coup HeavyRound. Les deux volets sont ANTI-CORRELES :
    un ennemi sur l'anneau retire une tuile du compte du volet 1 ET ajoute une cible au volet 2.

    Le suffixe `Combat` distingue cette classe de son HOMONYME de la face DECISION
    (`entities/abilities/active_ability.FrenziedFiringAbility`, dont ce module importe le noeud de coups et
    la feuille `_AOE`) : UN artefact natif, DEUX faces, mais un SEUL port de chaque noeud.

    Turn-flags = defauts base (1036 absent des overrides). Retour : {origin_attack, aoe, hits, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.FrenziedFiring)      # 1036
    ABILITY_ID = FRENZIED_FIRING_ID

    # GATE DE CIBLE (#115) — FORME 3 « PRESET STATIQUE COPIE ».
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$.ctor` n'appelle AUCUN
    # `TargetingOptions..ctor` : il recopie les 0x40 octets du champ STATIQUE `+0x140` du bloc
    # `<class>+0xb8`, puis `AActiveAbility..ctor(this, &opts, 0, 0)` (3e arg = 0 =
    # AbilityAttackType.DirectTargetAttack -- litteral CONFIRME, il etait deja pose par le lot #61).
    # Masque EFFECTIF = `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28`
    # = `*(statics+0x168)` = **0x4002**. Decomposition EXHAUSTIVE (0x2 + 0x4000, aucun residu) :
    #     0x2     (bit 1)  TargetMatchesDynamicRule -> le natif INVOQUE le slot vtable `+0x480`.
    #             1036 ne surcharge PAS `GetDynamicInvalidTargetReason` (aucun symbole, et le corps
    #             de base `return 0` est de toute facon deduplique) -> le defaut 0 de
    #             `ActiveAbility.get_dynamic_invalid_target_reason` est le mirror exact. Ce bit est
    #             donc INERTE ici, et la mesure live le confirme (contrefactuel `sansDynamic`).
    #     0x4000  (bit 14) TargetIsEnemy -> PORTE : refus sur soi-meme et sur un allie.
    # PORTEE : le MEME preset porte `<preset>+0x08..0x1f` <- `TargetingRange` statique `+0x18` =
    # `RANGE_FROM_CONFIG` -> `overrideRange = FrenziedFiring.constants.range` = **3**.
    # `forceMeleeTarget` = `<preset>+0x20` = `*(statics+0x160)` = **0** = `RangedBool.True` : le
    # clamp `Math.Min(1, v)` + `onlyAdjacent` de `TargetingQuery$$GetRange` s'applique DES qu'un
    # ennemi est au contact du caster (`AttackQuery$$ShouldApplyRangedInMelee`, `ignoreTrait = 1`).
    # Volk au contact ne porte donc plus qu'a 1, malgre `attackRangeType=Ranged` et `range=3`.
    # ⚠ MEME preset `+0x140` que 1014 ArmoriumCherub / 1078 Executioner / 1098 HarvesterOfSouls /
    # PlasmaCannon — mais PAS le preset `+0x180` de 1104 SpiritLeech, qui n'en differe QUE par
    # `forceMeleeTarget` (`*(statics+0x1a0)` = 1 = `RangedBool.False`). Recopier le voisin donnerait
    # le bon `Rules` et le MAUVAIS regime de portee au contact.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_TRUE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        # `Get(GetHits)` = `GetNumberConstant(0x2f)` et `ConfigConst(0x48)` : constantes de config resolues
        # ICI (le DslContext runner ne porte ni `config` ni `ability_level`) -- meme convention que
        # `harvester_of_souls_tree(n_hits, range_r)`.
        n_hits = int(ability_var(self.ABILITY_ID, "nrOfHits", is_constant=True) or 1)
        max_hits = int(ability_var(self.ABILITY_ID, "maxNrOfHits", is_constant=True) or n_hits)
        ectx = ExecutionContext(state=state, rng=state.rng)
        frenzied_firing_tree(n_hits, max_hits).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        origin = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        aoe = [{"target": p["target"], "attack": p["attack"]}
               for p in atks if p.get("target") != target_id]      # volet AoE = cibles != cible d'origine
        return {"ability": FRENZIED_FIRING_ID, "caster": caster_id, "target": target_id,
                "hits": (origin or {}).get("hits"), "origin_attack": origin, "aoe": aoe, "dsl": True}


def _ability_state(state: "State", caster_id: int):
    """(niveau d'ability ACTIVE, multiplicateur de rarete %) du caster -- l'`AbilityStateReference` natif
    contre lequel `GetVariableForLevel`/`ConfigVar` resolvent (== HadesAutocannons/DaemonicOrdnance)."""
    e = state.get_entity(caster_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    cctx = sc.ctx if sc is not None else None
    return (getattr(cctx, "active_ability_level", None),
            int(getattr(cctx, "ability_variables_multiplier", 100) or 100))


# =================================================================================================== #
# Drachnyen (1029, `blackAbaddon` -- Abaddon the Despoiler, HERO) -- case-bl-1029-1020
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.DrachnyenAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE) :
#   hpNode  = Direct( GetVariableForLevel(config@0x60, 0x1d = hp, abilityState) )    # == ...$$HealthAmount
#   maxHp   = StatAmount( Owner@0x148, 5 = Health, 2 = MAXIMUM, 0 )
#   [1] setHp  = ChangeStat( Owner@0x148, Position(5 = Health, 0), mode 0 = SetAbsolute,
#                            Min(maxHp, hpNode) )                                    # == ...$$GetSetHealthBehaviour
#   [2] addEff = AddEffect( 0x5bf = 1471 Drachnyen_ExtraAttack, AbilityStateReference,
#                           targets = Owner@0x148, options ZERO )                    # overload 5-args (source null
#                                                                                    #  -> source = la cible = Abaddon)
#   [3] attack = UseActiveAbility( subject = Caster@0x160, targets = Target@0x178,
#                                  abilityType = UnitNormalAttackType(Caster@0x160),
#                                  source = AbilityOrEffect(this+0x10 = 0x405 = 1029), <opts> )
#   AActiveAbility.Execute( op_BitwiseAnd( op_BitwiseAnd([1], [2]), [3] ) )
#
# i2 : « Abaddon is set to 4729 Health and immediately performs a normal melee attack against an adjacent
# enemy unit. After this attack and for the rest of the battle, after performing a normal melee attack,
# Abaddon performs a second attack against an adjacent enemy unit, dealing 3x 873-1091 Piercing Damage.
# Abaddon cannot be set to higher Health than his maximum Health. »
#
# LE `Min` EST LE POINT DE FIDELITE : `hp` est une variable RARITY-SCALED, elle peut depasser le MaxHealth
# reel ; le natif CAPE (« cannot be set to higher Health than his maximum Health »). Et c'est un SET, pas
# un heal : mesure live (rank 17, seed 777) Abaddon 10038 -> 6480 PV, soit une PERTE de 3558 -- porter un
# `max(hp, current)` serait faux dans le sens le plus visible.
#
# [2] pose l'effet AVANT [3] : la triggered `Drachnyen_ExtraAttackAbility` (1485), gatee par
# `HasEffect(Owner, 0x5bf)` sur `On(0x26 = NormalAttack)`, fire donc DES l'attaque normale de CE cast
# (cascade live : groupes `Drachnyen` > `Drachnyen_ExtraAttack` > `Loki_NormalAttack`). Cette triggered
# n'est PAS portee -- residu NOMME, hors perimetre (cf. docs/rl/case-bl-1029-1020.md §Residus).
# =================================================================================================== #

DRACHNYEN_ID = "Drachnyen"
VAR_DRACHNYEN_HP = AbilityVariableType.hp               # GetVariableForLevel(0x1d) -> "hp" (rarity-scaled)
DRACHNYEN_EXTRA_ATTACK = int(EffectType.Drachnyen_ExtraAttack)      # 0x5bf = 1471


def drachnyen_tree(hp_amount: int):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.DrachnyenAbility$$ExecuteBehaviour`
    (MIRROR 1:1, cf. le bloc de commentaire) :

        op_BitwiseAnd( op_BitwiseAnd(
            ChangeStat(Owner, Health, SetAbsolute, Min(StatAmount(Owner, Health, MAX), Direct(hp))),
            AddEffect(1471 Drachnyen_ExtraAttack -> Owner) ),
            UseActiveAbility(Caster, Target, UnitNormalAttackType(Caster)) )

    - `SetHealth(amount=...)` = la feuille partagee `ChangeStat(Position(Health,0), mode 0 SetAbsolute)`
      (MEME overload/mode que `BlackRageAbility$$GetSetHealthBehaviour`, live-valide bit-exact) ; seul le
      noeud MONTANT change, ici `Min(StatAmount(Owner@0x148, Health=5, MAXIMUM=2), Direct(hp[level]))`.
      `hp_amount` est resolu par l'appelant (`ability_var`, == HadesAutocannons/DaemonicOrdnance : le
      `ConfigVar` natif lit l'`AbilityStateReference` du caster, non capte par `ctx.config` offline).
    - `AddEffect(..., duration_rounds=None)` = les options natives ZERO (aucun `TurnsFromRounds`) ->
      `DefaultAmountOfRounds` ; live : `remaining=0` (permanent, « for the rest of the battle »).
      La cible de l'effet est `Owner@0x148` = Abaddon lui-meme (overload 5-args de
      `IdunBattleLogic.Entities.DSLBehaviors$$AddEffect` : le selecteur SOURCE est null -> `AddEffectBehaviour
      $$Execute` retombe sur la cible, `lVar14 = lVar7; if (lVar8 != 0) lVar14 = lVar8;`).
    - `UseActiveAbility(Caster(), Target())` = la feuille deja portee, specialisee au dispatch d'ATTAQUE
      NORMALE (`UnitNormalAttackType(Caster)` -> `AttackDamageOperation.execute`, resolveur d'arme par
      distance) -- exactement le groupe `Loki_NormalAttack` de la cascade live.
    - AUCUN tirage RNG avant l'attaque ([1] et [2] sont deterministes) -> le flux `state.rng` de l'attaque
      normale est celui d'une attaque normale nue."""
    max_hp = StatAmount(Caster(), int(StatType.HEALTH), int(StatPart.MAXIMUM))   # StatAmount(@0x148,5,2)
    set_hp = SetHealth(Caster(), amount=Min(max_hp, Const(int(hp_amount))))      # ChangeStat mode 0
    add_eff = AddEffect(DRACHNYEN_EXTRA_ATTACK, EffectType.Drachnyen_ExtraAttack.name,
                        Caster(), duration_rounds=None)                          # AddEffect(0x5bf -> Owner)
    attack = UseActiveAbility(Caster(), Target())                                # UnitNormalAttackType
    return op_and(op_and(set_hp, add_eff), attack)


class DrachnyenAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DrachnyenAbility$$ExecuteBehaviour` (id 1029,
    `blackAbaddon` « Abaddon the Despoiler », HERO Black Legion) — cf. le bloc de commentaire.

    Kit gameconfig 1029 : `attackRangeType=Melee`, `damageProfile=Piercing`, `nrOfHits=3`,
    `minDmg`/`maxDmg`/`hp`[level] (les TROIS rarity-scaled). ⚠ `damageProfile`/`nrOfHits`/`minDmg`/`maxDmg`
    ne sont PAS lus par cet `ExecuteBehaviour` : ils alimentent la TRIGGERED `Drachnyen_ExtraAttack` (1485),
    hors port. L'attaque de CE cast est l'attaque NORMALE de l'unite (arme melee), pas une attaque
    d'ability.

    OBSERVABLE porte : (1) PV d'Abaddon SETES a `min(MaxHealth, hp[level])` (deterministe, bit-exact) ;
    (2) effet 1471 `Drachnyen_ExtraAttack` pose sur Abaddon, permanent ; (3) attaque normale dirigee sur la
    cible. Turn-flags = defauts base (1029 absent des overrides). Retour :
    {set_health, effect, attack, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Drachnyen)   # 1029
    ABILITY_ID = DRACHNYEN_ID

    # GATE DE CIBLE. `IdunBattleLogic.Entities.Abilities.Active.Loki.DrachnyenAbility$$.ctor` :
    #   1. il recopie les 0x40 octets du PRESET STATIQUE `TargetingOptions` `statics+0x40` (aucun
    #      litteral de masque n'apparait dans le ctor) ;
    #   2. il passe ce preset a l'overload **COPIE PURE** `TargetingOptions..ctor(&out, &template)`,
    #      qui recopie les 8 qwords verbatim -- il n'ajoute AUCUN flag.
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit pour ce preset : `+0x68` (= +0x28
    # relatif) `Rules = 0x4000`, `+0x60` (= +0x20) `forceMeleeTarget = 1` (RangedBool.False) et
    # `+0x48..0x5f` (= +0x08) le `TargetingRange` statique `+0x30`.
    # MASQUE EFFECTIF = `0x4000` = `TargetIsEnemy` seul -> refus sur soi-meme et sur un allie.
    #
    # ⚠ CORRECTION #336 (balayage exhaustif du bit `TargetIsTile`, `case-302-4`). Ce masque portait
    # `TargetIsNotAnObject` (`0x200000000`), sur la foi d'un `TargetingOptions..ctor(&out, &preset,
    # 0x200000000, 0)` — l'overload PRESET + flags. Ce n'est PAS l'overload appele : les xrefs
    # ENTRANTES des trois surcharges tranchent sans ambiguite sur le build courant --
    # `DrachnyenAbility$$.ctor` appelle la surcharge **2 arguments** (copie pure), et n'apparait pas
    # dans les appelants de la surcharge 3 arguments. Le decompile du ctor le confirme :
    # `TargetingOptions___ctor(&local_88, &local_48);`, deux arguments, aucun litteral de flags.
    # Le bit retire n'est de toute facon PAS porte (regle `TargetIsNotAnObject` non implementee),
    # donc la correction ne change AUCUN verdict de ciblage -- elle retire une fausse verite.
    # PORTEE : MEME preset `+0x40` que JakhalStimms (1131) -- `onlyAdjacent = True` +
    # `overrideRange = 1` -> cible ADJACENTE obligatoire, et la constante de config `range` n'est
    # PAS consultee (`overrideRange` deja pose court-circuite
    # `AActiveAbility$$SetConfigValuesInTargetingOptions`). Coherent avec `attackRangeType=Melee` et
    # l'i2 (« a normal melee attack against an adjacent enemy unit »).
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(caster_id) is None:
            return None
        level, mult = _ability_state(state, caster_id)
        hp_amount = int(ability_var(self.ABILITY_ID, "hp", level, multiplier_pct=mult) or 0)
        ectx = ExecutionContext(state=state, rng=state.rng)
        drachnyen_tree(hp_amount).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        set_hp = next((p for n, p in ectx.emitted if n == "SetHealth"), None)
        eff = next((p for n, p in ectx.emitted if n == "AddEffect"), None)
        atk = next((p for n, p in ectx.emitted if n == "UseActiveAbility"), None)
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "hp_amount": hp_amount, "set_health": set_hp, "effect": eff, "attack": atk,
                "dsl": True}


# =================================================================================================== #
# HeraldOfTheApocalypse (1020, `blackHaarken` -- Haarken Worldclaimer, HERO) -- case-bl-1029-1020
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.HeraldOfTheApocalypseAbility$$ExecuteBehaviour`
# (MIRROR du DECOMPILE) :
#   hits    = GetNumberConstant(config@0x60, 0x2f = nrOfHits)                       # 2
#   profile = GetDamageProfile(config@0x60)                                         # Piercing
#   tgtTile = First( SortByDistance( Tiles(Target@0x178), CasterTile@0x168 ), 1 )
#   line    = TilesBehindInLine( from = CasterTile@0x168, to = tgtTile,
#                                settings{+0x10 = 1 checkWalkable, +0x11 = 1 updateReference},
#                                maxCount = Get(2) @dsl+0xc8 )
#   behind  = Enemies( Owner@0x148, Units(line, 1, 3) op_Subtraction Target@0x178, 3 )
#   targets = Target@0x178 op_Addition behind
#   [1] AttackWithAttackDamage( Caster@0x160, targets, MinMaxDamage(this, level), Direct(profile),
#                               Direct(hits), AbilityOrEffect(0x3fc = 1020), <opts> )
#   [2] AddEffect( 0x403 = 1027 HeraldOfTheApocalypse, AbilityStateReference,
#                  source = Owner@0x148, targets = targets, options ZERO )
#   [3] TriggerAbility( Enemies( Owner@0x148,
#                                SurroundingUnits(Target@0x178, GetNumberConstant(0x16 = range) = 2,
#                                                 1, includeCenter = 1, 3), 3 ),
#                       0x401 = TriggeredAbilityType.BattleFatigue,
#                       actor@0x158, caster@0x160, target@0x178, null, 3, false )
#   AActiveAbility.Execute( op_Addition( op_Addition([1], [2]), [3] ) )
#
# i2 : « Deals 2x 1310-1892 Piercing Damage to an adjacent enemy and an additional enemy directly behind
# the target. Affected enemies receive +1310 Damage from the next attack made by a unit against them. Also
# triggers Battle Fatigue for all enemy units within 2 hexes of the original target. »
#
# LE POINT DE FIDELITE = LE 2e VOLET DE CIBLES. « directly behind » n'est PAS un anneau : c'est la tuile
# `cube(target) + (cube(target) - cube(caster))` (une seule, `maxCount = Get(2)` = [tuile cible, tuile
# derriere]), gatee walkable + ecart d'elevation < 2 pas-a-pas (settings 1/1). L'occupant n'est retenu que
# s'il est ENNEMI du caster (`Enemies(Owner@0x148, ...)`) et n'est pas la cible elle-meme
# (`op_Subtraction Target`). Un allie du caster derriere la cible n'est donc PAS touche.
#
# ⚠ NE PAS confondre avec `UnitsDirectlyBehind` (Supercharge/PlasmaCannon) : ce noeud-la rend jusqu'a
# N unites d'un CONE ; ici c'est la ligne stricte a UNE tuile, construite par `TilesBehindInLine`.
# =================================================================================================== #

HERALD_ID = "HeraldOfTheApocalypse"
CONST_HERALD_RANGE = AbilityConstantType.range             # GetNumberConstant(0x16) -> "range" = 2 (disque BattleFatigue)
CONST_HERALD_HITS = AbilityConstantType.nrOfHits              # GetNumberConstant(0x2f) -> "nrOfHits" = 2
HERALD_EFFECT = int(EffectType.HeraldOfTheApocalypse)               # 0x403 = 1027
TILES_BEHIND_COUNT = 2                # `Get(2)` = dsl+0xc8 (DSLFactory..ctor : 0xb8=0, 0xc0=1, 0xc8=2)


def herald_of_the_apocalypse_targets():
    """Selecteur de cibles de `HeraldOfTheApocalypseAbility$$ExecuteBehaviour` (MIRROR) :

        Target()  op_Addition  Enemies( Units( TilesBehindInLine(CasterTile, First(SortByDistance(
                                   Tiles(Target), CasterTile), 1), {1,1}, Get(2)) )
                                op_Subtraction Target() )

    `First(SortByDistance(Tiles(Target), CasterTile), 1)` est un `First` sur un SINGLETON (la cible n'a
    qu'une MainTile) -> IDENTITE ; on le mirror quand meme (`PickFirstN(..., 1)` = `IdunBattleLogic.Entities.DSLSelectors$$First`
    avec noeud-montant, cf. la classe) plutot que de le collapser silencieusement.

    `TilesBehindInLine(from=CasterTile, to=<tuile cible>, maxCount=2)` rend `[tuileCible, tuileDerriere]`
    (la 1re tuile rendue EST `to`) ; `Units` en prend les occupants VIVANTS, `- Target()` retire la cible,
    `Enemies` filtre a l'equipe adverse du caster."""
    # Les DEUX consommateurs sont SCALAIRES au decompile (`SortByDistanceSelector` ferme son
    # comparateur sur UN `PositionComponent` ; `TilesBehindInLineSelector` resout origin ET direction
    # par `TargetsSelector$$SelectTile`) -> `SelectTile` autour de l'accesseur d'empreinte (#459).
    tgt_tile = PickFirstN(SortByDistance(Tiles(Target()), SelectTile(CasterTile())), 1)
    line = TilesBehindInLine(SelectTile(CasterTile()), tgt_tile, Const(TILES_BEHIND_COUNT),
                             check_walkable=True, update_reference=True)   # settings +0x10=1 / +0x11=1
    behind = Enemies(Sub(Units(line), Target()))
    return Union(Target(), behind)


def herald_of_the_apocalypse_tree(range_: int):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.HeraldOfTheApocalypseAbility$$
    ExecuteBehaviour` (MIRROR 1:1, cf. le bloc de commentaire) :

        op_Addition x2 ( AttackWithAttackDamage(<cible + ennemi derriere>),
                         AddEffect(1027 -> les MEMES cibles),
                         TriggerAbility(BattleFatigue -> ennemis du disque rayon `range` autour de la cible) )

    - **native_factory = "attack"** (defaut) : le decompile appelle bien
      `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (VERIFIE sur les callees de
      l'`ExecuteBehaviour`, pas au nom) -> famille ATTACK, crit/block, 2 tirages/coup a cc=0.
    - `multi=True` : le selecteur resout 1 ou 2 cibles -> `IdunBattle.Entities.Behaviours.AttackBehaviour
      $$Execute` attaque CHACUNE (`OrderBy` par-entite quand count > 1 ; port = tri par id, convention
      partagee par tous les multi-cibles valides bit-exact).
    - `attackRangeType=Melee` -> `is_melee=True` ; profil `Piercing` ; coups = `nrOfHits` (config).
    - `AddEffect(..., duration_rounds=None)` = options natives ZERO -> `DefaultAmountOfRounds` (live :
      `remaining=0`). Le selecteur de cibles est le MEME OBJET que celui de l'attaque, RE-EVALUE apres
      elle (mirror : le natif partage `uVar10` entre les deux feuilles, l'evaluation est lazy).
    - `TriggerAbility` : cf. sa docstring — le SET declenche est porte et trace, la fuite elle-meme reste
      un residu nomme (chance `GetNumberConstant` d'une config absente du gameconfig)."""
    targets = herald_of_the_apocalypse_targets()
    attack = AttackWithAttackDamage(targets, HERALD_ID, "Piercing", is_melee=True, multi=True,
                                    ability_type=int(ActiveAbilityType.HeraldOfTheApocalypse))
    # `scale_from_source=True` = le PORT de l'`AbilityStateReference` (3e argument natif d'`AddEffect`) :
    # la magnitude de l'effet 1027 est un `ConfigVar(8 = extraDmg)` que
    # `IdunBattle.Entities.Effects.Loki.HeraldOfTheApocalypse_ExtraDamageEffect$$
    # CreateEffectDamageBonusForAttack` resout contre l'`AbilityState` de la SOURCE (Haarken), pas de la
    # victime. `extraDmg` est dans `variablesAffectedByRarityBonus` -> le multiplier du POSEUR compte.
    # #BL-1020r (sans ce flag l'effet lisait le niveau/multiplier de l'unite qui le PORTE).
    add_eff = AddEffect(HERALD_EFFECT, EffectType.HeraldOfTheApocalypse.name, targets,
                        duration_rounds=None, scale_from_source=True)
    fatigue = TriggerAbility(
        Enemies(SurroundingUnits(Target(), Const(int(range_)), include_center=True)),
        int(TriggeredAbilityType.BattleFatigue))
    return op_add(op_add(attack, add_eff), fatigue)


class HeraldOfTheApocalypseAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HeraldOfTheApocalypseAbility$$ExecuteBehaviour`
    (id 1020, `blackHaarken` « Haarken Worldclaimer », HERO Black Legion) — cf. le bloc de commentaire.

    Kit gameconfig 1020 : `attackRangeType=Melee`, `damageProfile=Piercing`, `nrOfHits=2`, `range=2`,
    `minDmg`/`maxDmg`/`armorReduction`/`extraDmg`[level] (rarity-scaled). ⚠ `extraDmg` n'est PAS lu ici :
    c'est la magnitude de l'EFFET 1027 (`IdunBattle.Entities.Effects.Loki.HeraldOfTheApocalypse_ExtraDamage
    Effect$$CreateEffectDamageBonusForAttack` = `EffectBonus.ForAddition(OwnerIsTarget & IsUnit(Caster),
    ConfigVar(8 = extraDmg), AbilityOrEffect(0x3fc))`), phase 2 hors port. `armorReduction` n'est lu NI par
    l'`ExecuteBehaviour` NI par l'effet 1027 (residu d'inventaire, cf. le case doc).

    OBSERVABLE porte : (1) `nrOfHits` coups Piercing sur la cible ET sur l'ennemi DIRECTEMENT DERRIERE
    elle ; (2) effet 1027 pose sur ces memes unites ; (3) le set d'ennemis eligibles a Battle Fatigue
    (disque rayon `range` autour de la cible, cible INCLUSE) resolu et trace. Turn-flags = defauts base
    (1020 absent des overrides). Retour : {attacks, targets, effects, fatigue, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HeraldOfTheApocalypse)   # 1020
    ABILITY_ID = HERALD_ID

    # GATE DE CIBLE. `IdunBattleLogic.Entities.Abilities.Active.Loki.HeraldOfTheApocalypseAbility$$
    # .ctor` n'appelle AUCUN `TargetingOptions..ctor` : il recopie les 0x40 octets du PRESET STATIQUE
    # `statics+0x40` et les passe tels quels a `AActiveAbility..ctor`. Le masque effectif est donc la
    # constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28`
    # (= `statics+0x68`) = **0x4000**, PAS un litteral du ctor.
    #     0x4000  TargetIsEnemy -> PORTE : refus sur soi-meme et sur un allie. SEUL bit du masque --
    #             en particulier PAS de `TargetMatchesDynamicRule`, et 1020 n'a effectivement aucun
    #             `GetDynamicInvalidTargetReason` natif.
    # CONTRASTE avec Drachnyen (1029) : MEME preset, mais 1029 y ajoute `0x200000000` via l'overload
    # PRESET + flags. Deux abilities du MEME module, meme preset, masques DIFFERENTS -> lecture
    # ability par ability, jamais de generalisation.
    # PORTEE : preset `+0x40` -> `TargetingRange` statique `+0x30` = `onlyAdjacent = True` +
    # `overrideRange = 1`. La constante `range = 2` de la config 1020 n'est donc PAS la portee de
    # CIBLAGE (elle ne sert qu'au disque `SurroundingUnits` du volet BattleFatigue) : i2 dit bien
    # « an adjacent enemy ».
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(caster_id) is None:
            return None
        consts = (GC.ability(self.ABILITY_ID) or {}).get("constants") or {}
        range_ = int(consts.get("range") or 0)             # GetNumberConstant(0x16)
        ectx = ExecutionContext(state=state, rng=state.rng)
        herald_of_the_apocalypse_tree(range_).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        # `clean_min`/`clean_max` = plage NON-CRIT de l'attaque (x coups) telle que la calcule le
        # pipeline porte : c'est l'ORACLE DE MAGNITUDE du confront live.
        # `additional_hits` (#227) = les coups des groupes du canal #179 emis APRES les coups d'arme
        # par la MEME `IdunBattle.Operations.AttackDamageOperation$$Execute` -- dont le coup
        # `LetTheGalaxyBurn` du porteur. Sans cette cle, la sequence d'evenements de degat rendue par
        # ce diag est TRONQUEE et le confront per-coup vs live est faussement rouge.
        attacks = [{"target": p.get("target"), "total": p.get("total"),
                    "per_hit": (p.get("attack") or {}).get("per_hit"),
                    "additional_hits": (p.get("attack") or {}).get("additional_hits"),
                    "clean_min": (p.get("attack") or {}).get("clean_min"),
                    "clean_max": (p.get("attack") or {}).get("clean_max")}
                   for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        effects = [p.get("target") for n, p in ectx.emitted
                   if n == "AddEffect" and p.get("effect_type") == HERALD_EFFECT and p.get("placed")]
        fatigue = next((p for n, p in ectx.emitted if n == "TriggerAbility"), None)
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "range": range_, "attacks": attacks, "targets": [a["target"] for a in attacks],
                "effects": effects, "fatigue": fatigue, "dsl": True}
