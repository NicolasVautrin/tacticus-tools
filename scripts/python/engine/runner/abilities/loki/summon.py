"""Abilities actives de SUMMON du namespace natif `Abilities.Active.Loki.*` — spawn d'unites :
ScarabHive (necroSpyder), ScarabSummon (auto-dedoublement necroSmnSwarm), GetEmRuntz (orksRuntherd).
+ le helper on-appearance partage `_summon_on_appearance_attack` (et `_nearest_enemy`, devenu un simple
outil GEOMETRIQUE de test depuis #338) consommes par
les feuilles `SpawnSummon`/`SpawnReplica`/`PerformAIAttack` (`../behaviours.py`). Cf. `loki/__init__.py`."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC
import hexgeo

from ..base import ActiveAbility
from ..targeting import (TargetingOptions, RANGE_ADJACENT, RANGE_SELF, RANGED_BOOL_FALSE)
import engine.runner.abilities.targeting as _targeting   # FORME B (#923), et ABSOLUE
# `valid_normal_attack_targets` est SUBSTITUE via le chemin PLEIN
# (`migrate_485r1_barils_reexport.py morsure` classe le couple HISSAGE_DESARMERAIT) : hisser en
# forme A (`from ..targeting import valid_normal_attack_targets`) gelerait la liaison a l'import
# et rendrait ces patchs INERTES. Le binding de MODULE, lui, est relu a chaque appel.
# ⚠ ABSOLUE, PAS `from .. import targeting` : cette derniere DECLARE une arete vers le PAQUET
# PARENT et referme un SCC (`engine.runner.abilities` / `.loki` / `.loki.summon`) -- meme mesure
# que pour `loki/attempted_possession.py` (#547-r2).
# ⚠ Le differe qui vivait a l'ancienne ligne 310 se DECLARAIT porteur ; il etait GRATUIT --
# l'arete `summon -> targeting` existe deja par la ligne ci-dessus, donc ni cycle possible ni
# cout. C'est le critere de `test_270r4r2r2_differes_offline::test_etage1_...`.
from ..targeting_rule import TargetingRule as TR
from ...operations.damage import AttackDamageOperation
from ...components import StatsComponent, OwnerComponent, PositionComponent, UnitComponent
from ....entities.stats import StatType
from ....entities.effect_type import EffectType
from ....entities.active_ability_type import ActiveAbilityType
from ....dsl.base import Const
from ....dsl.effects import ExecutionContext, AbilityBehaviour, OperationResult
from ....entities.behaviours import Seq, Foreach, If, AtomicGroup, op_add
from ....entities.selectors.accessors import Subject, Target
from ....entities.selectors.composites import get_spawn_tile_selector
from ....entities.selectors.geometry import Cache
from ....entities.selectors.tiles import Caster, Children, LastUnitAttackedBy
from ....entities.formulas import TotalAttacksMade, UnitTurnsStarted
from ....entities.triggers import AmountIsGreaterThanZero, AmountIsEqual, IsAlive, TriggerAnd
from ..behaviours.context import entities_from_state
from ..behaviours.effects import AddBondEffect, AddEffect
from ..behaviours.summon import PerformAIAttack, Spawn, SpawnReplica, SpawnSummon
from ...components import UnitComponent as _UC, PositionComponent as _PC
from ...events import EventBus
from ...messages import MoveUnitMessage
from ...operations.movement import MovementHandler
from ...operations.spawn import _spawn_config_grot
from ...operations.summon_ai import (ai_control_execute_ability_action_for,
                                         NORMAL_ATTACK_ID)

if TYPE_CHECKING:
    from ...state import State

TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)   # 27 — COMPOSITE -> 25/26/1237 ; bond (GetEmRuntz)


def scarab_hive_tree() -> SpawnSummon:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$ExecuteBehaviour` (id 1007, necroSpyder — MIRROR du DECOMPILE) :
        Execute( Spawn(caster@0x160, tileSel, unitId=necroSmnSwarm,
                       SpawnUnitOptions.WithStatsFromConfig(config)
                         .effect       = AddEffect(0x4a3 ScarabHive_OverrideDamageProfile=1187, target@0x178)
                         .onAppearance = UseNormalAttackIfAble(target@0x178)) )
    UN SEUL noeud `Spawn` (plain `Execute`, PAS `ExecuteAtomic`) portant DEUX sous-behaviours EMBARQUES dans
    ses options (+0x10 effet, +0x18 on-appearance) — le count-2, le placement (`First(SortByDistance(CanAddUnit(
    AdjacentTiles(target)), caster), i)`) et `WithStatsFromConfig` vivent DANS `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute` (GetUnitToSpawn/GetTileIds/GetStatsToOverride), HORS des DSL-selecteurs (`First`=PickAtIndex=1
    element IdunBattle.Entities.Selectors.PickAtIndexSelector$$Select — le count vient des options, pas du selecteur).

    Port = feuille `SpawnSummon` (cf. behaviours.py) qui delegue le SPAWN a l'Operation VALIDEE LIVE-BIT-EXACT
    `SpawnUnitOperation.execute` (2x necroSmnSwarm team/player du caster, stats `ability_var`, tuiles libres
    adjacentes a la cible) puis l'ON-APPEARANCE `UseNormalAttackIfAble(target)` = `_summon_on_appearance_attack`
    (profil override Piercing immediat). L'imperatif `ScarabHiveAbility.execute_behaviour` (spawn + boucle
    on-appearance cables a la main) est REMPLACE par cet arbre. GAP flagge (tache) : l'effet PERSISTANT 0x4a3
    (OverrideDamageProfile pour les attaques des TOURS SUIVANTS) n'est ni materialise ni lu par le pipeline
    d'attaque — l'attaque immediate porte deja le bon profil via `prof`, mais les attaques subsequentes du
    summon utiliseraient son arme Energy au lieu de Piercing. `count=2` = arg `.ctor AActiveAbility` (== l'ancien
    `COUNT`) ; `Target()` = `target@0x178`."""
    return SpawnSummon("ScarabHive", 2, Target())


def scarab_summon_tree() -> SpawnReplica:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$ExecuteBehaviour` (id 1047, necroSmnSwarm — MIRROR du DECOMPILE) :
        Execute( Spawn(self@0x160, PickRandomly(CanAddUnit(AdjacentTiles(self@0x160)), 1),
                       unitId=GetStringConstant(config,0)=necroSmnSwarm,
                       SpawnUnitOptions.CopyOwner(caster)
                         .onAppearance = PerformAIAttack(Spawned@0x180, 1, 0, 0, 0)) )
    UN SEUL noeud `Spawn` (plain `Execute`, PAS `ExecuteAtomic`) portant UN sous-behaviour EMBARQUE (+0x18
    on-appearance) — PAS de +0x10 effet (contrairement a ScarabHive : ScarabSummon n'a pas l'effet persistant
    0x4a3). Le count-1, le placement (`PickRandomly(CanAddUnit(AdjacentTiles(self)))` = 1 tuile LIBRE adjacente
    a SOI) et `CopyOwner` (clone owner+stats du parent) vivent DANS `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute`,
    HORS des DSL-selecteurs.

    L'on-appearance est le noeud `IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAttack` — le MEME
    `PerformAIAbilityUnitBehaviour` que `...FromCurrentPosition`, a `+0x70` (`allowMoveAction = 1`) et `+0x78`
    (budget de deplacement = **null**, la ou `...FromCurrentPosition` pose `factory+0xb8 = Direct(0)`) pres.
    D'ou l'i2 « which then immediately **takes a turn** » : le double PEUT se DEPLACER avant d'agir, contrairement
    aux summons de GetEmRuntz/AberrantHypermorph (« cannot move this turn »).

    Port = feuille `SpawnReplica` (cf. behaviours.py) qui delegue le SPAWN a l'Operation VALIDEE
    `SpawnUnitOperation.execute_self_replica` (`IdunBattle.Entities.Behaviours.SpawnUnitOptions$$CopyOwner` = clone owner+stats du parent, tuiles
    libres adjacentes au caster) puis l'ON-APPEARANCE via le CORPS UNIQUE `perform_ai_attack(..., True, None)`
    (gate de portee `_in_attack_range` + attaque normale complete + dispatch after-hit ; cible choisie par le
    MOTEUR D'UTILITE natif depuis #338). L'imperatif `ScarabSummonAbility.execute_behaviour` (spawn + boucle on-appearance cables
    a la main) est REMPLACE par cet arbre. DISTINCT de `scarab_hive_tree` (WithStatsFromConfig summoner-scaled +
    AddEffect(0x4a3) + attaque de la CIBLE ; ici CopyOwner clone-du-parent + tour AI du double, sans effet).
    GAP (inchange) : le cap de duplication (`UnitDuplicationLimitSelector`) n'est pas porte — recurrence non
    bornee offline. Le DEPLACEMENT du double avant son attaque EST porte depuis #348
    (`docs/rl/case-348-ai-approach.md`)."""
    return SpawnReplica("ScarabSummon", 1)


def getemruntz_taunt_tree() -> If:
    """Corps `Func<entities,behaviour>` de `IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$TauntWithNewChildrenWhoDidDamage` (DECOMPILE) pour
    l'enfant COURANT (`Subject()`, pose par le `Foreach(Children)`) :
        If( AmountIsGreaterThanZero(TotalAttacksMade(child))            # le grot a attaque
            & AmountIsEqual(capturedTurns, UnitTurnsStarted(child))     # enfant NEUF de ce cast
            & IsAlive(LastUnitAttackedBy(child)),                       # l'ennemi frappe est vivant
            AddBondEffect(0x1b Taunted, source=child, target=LastUnitAttackedBy(child), TurnsFromRounds(1)) )
    `op_BitwiseAnd` (2x) = `TriggerAnd`. Nœud STATIQUE (lit `Subject()` a l'eval) -> passe en body de
    `Foreach`. `capturedTurns` = `Const(0)` (owner fraichement, cf. `UnitTurnsStarted`)."""
    child = Subject()
    cond = TriggerAnd(
        TriggerAnd(AmountIsGreaterThanZero(TotalAttacksMade(child)),
                   AmountIsEqual(Const(0), UnitTurnsStarted(child))),
        IsAlive(LastUnitAttackedBy(child)))
    # duree = `TurnsFromRounds(1)` natif -> convertie par `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns (#98)
    # `bonded_ref = child` = le **5e argument** de `IdunBattleLogic.Entities.DSLBehaviors$$AddBondEffect`
    # au call-site (`GetEmRuntzAbility$$TauntWithNewChildrenWhoDidDamage` :
    # `AddBondEffect(ctx, 0x1b, stateRef, child, LastUnitAttackedBy(child), child, TurnsFromRounds(1))`).
    # C'est ce que relit `IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId`, donc la SEULE
    # cible que l'ennemi taunte aura le droit d'attaquer (`TargetIsAllowedForCaster`, #436).
    return If(cond, AddBondEffect(TAUNTED, "Taunted_OnlySpecificTargets",
                                  child, LastUnitAttackedBy(child), duration_rounds=1,
                                  bonded_ref=child))


def getemruntz_tree() -> Seq:
    """Arbre COMPLET de `IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$ExecuteBehaviour` (id 1045, MIRROR 1:1 du DECOMPILE) :
        cache = Cache(IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$GetSpawnTileSelector)             # IdunBattleLogic.Entities.DSLSelectors$$Cache -- PARTAGE Spawn/Attack (memoise)
        ExecuteAtomic( Spawn(cache) )                             # IdunBattle.Entities.Abilities.AActiveAbility$$ExecuteAtomic inline -> grots materialises
        Execute( op_Addition( PerformAIAttackFromCurrentPosition(cache),   # les grots (sur les tuiles cache) attaquent
                              Foreach(Children, Taunt) ) )        # + Taunt de la cible frappee
    Port : `Seq(AtomicGroup(Spawn(cache)), op_add(PerformAIAttack(cache), Foreach(Children(), taunt)))`.
    Le `cache` est PARTAGE entre `Spawn` et `PerformAIAttack` (mirror natif : le MEME `Cache(GetSpawnTileSelector)`
    est passe aux deux nœuds) -> memoise les tuiles LIBRES PRE-spawn (RE #200 : le CacheSelector memoise ;
    sans ca `PerformAIAttack` relirait `CanAddUnit` post-spawn et exclurait les tuiles occupees par les grots).
    `AtomicGroup` = inline (RE #201 : `AtomicGroupOperation.Execute` invoque son child sur-le-champ, PAS
    differe). `op_add`/`Seq` = `CombinedBehaviour` (effets PURS -> pas de court-circuit -> les 3 volets
    s'executent). Ordre = tous les spawns (inline dans l'AtomicGroup) PUIS toutes les attaques PUIS tous les
    Taunts (NATIF, prouve RE #200). CONFRONTE LIVE (tracer-v2 DSLFactory #200 : arbre natif capture == ce
    mirror) ; l'imperatif `SpawnUnitOperation.execute_getemruntz` a ete RETIRE (#199)."""
    cache = Cache(get_spawn_tile_selector())                       # IdunBattleLogic.Entities.DSLSelectors$$Cache -- PARTAGE (memoise pre-spawn)
    return Seq(
        AtomicGroup(Spawn(cache, "GetEmRuntz")),                   # ExecuteAtomic(Spawn(cache)) -- inline
        op_add(PerformAIAttack(cache),                             # Execute( op_Addition(
               Foreach(Children(), getemruntz_taunt_tree())))      #   PerformAIAttack(cache), Foreach(Children, Taunt) ))


def _summon_on_appearance_attack(state: "State", summon_id: int, target_id: int,
                                 profile_name):
    """`UseNormalAttackIfAble(Spawned, Target)` à l'apparition : le summon attaque la cible avec son
    attaque NORMALE. `profile_name` = OVERRIDE optionnel du profil (ex. ScarabHive `unitDamageProfile`
    = Piercing, i2 « immediately attack using Piercing ; subsequent attacks use their normal type »).
    `profile_name is None` (aucun override, ex. DeathFromAbove) -> FALLBACK sur le profil de l'arme
    NORMALE du summon (`ctx.normal_profile` + son PiercingRatio) : `UseNormalAttackIfAble` = attaque
    normale, l'override n'est PAS obligatoire (ScarabHive passe "Piercing" -> branche inchangee, aucune
    regression). base = stat Attack du summon, hits = arme du summon, pipeline normal (reduce-then-roll).
    No-op si rng non calé (return None)."""
    e = state.get_entity(summon_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return None
    ctx = sc.ctx
    prof = profile_name if profile_name is not None else getattr(ctx, "normal_profile", None)
    dp = GC.damage_profile(prof) or {}
    pierce = max(0, min(100, int(dp.get("PiercingRatio") or 0) + int(ctx.extra_pierce)))
    hits = max(1, int(ctx.normal_weapon_hits))
    return AttackDamageOperation.execute_normal_like(
        state, summon_id, target_id, int(ctx.stat(StatType.ATTACK)), pierce, hits=hits, spread_pct=20,
        damage_profile=prof, is_melee=ctx.is_melee)


def perform_ai_ability_unit_behaviour(state: "State", unit_id: int, allow_move_action: bool,
                                      move_amount: Optional[int],
                                      allowed_targets: "Optional[set]" = None,
                                      ability_type: Optional[int] = None) -> Optional[dict]:
    """**L'UNIQUE port du corps natif `IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute`**
    (un acteur), partage par les DEUX noeuds `DSLFactory` qui l'instancient — cf. les deux constructeurs
    homonymes juste en dessous (`perform_ai_attack_from_current_position`, `perform_ai_attack`). Tous les
    call-sites passent par ici : la feuille DSL `PerformAIAttack` (domaine TUILE ou UNITE, cf.
    `../behaviours/summon.py`), les on-appearance embarques dans `SpawnUnitOptions+0x18`
    (MasterOfTheTutelaries/AberrantHypermorph/AlphaWarrior/IronkinSteeljack/Screamer/ScarabSummon) et la
    free-attack de `IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetTriggerAttackBehaviour`.

    STRUCTURE NATIVE (decompile) — les noeuds `DSLFactory` ne sont que des CONSTRUCTEURS ; ils allouent un
    `IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour` dont les champs sont
        `+0x50` = `unit`            (le selecteur d'ACTEURS, itere par `Execute`) ;
        `+0x68` = le `Func<IEntity,int>` CACHE du `<>c` de `DSLFactory` (= resolveur de l'ability
                  d'ATTAQUE de l'acteur ; c'est le point qui distingue ces noeuds de
                  `IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAbility`, ou le Func est fourni) ;
        `+0x70` = **`allowMoveAction`** (bool) ; `+0x71` = `skipAtomicCheck` ;
        `+0x78` = **le noeud d'AMOUNT du budget de deplacement** (`IAmount`, evalue par `Execute` en un
                  `Nullable<int>` : noeud absent => `null`) ;
        `+0x80` = `utilityEntity`, `+0x90` = `customUtility` (surcharges d'UTILITE du choix de cible) ;
        `+0x88` = 0 -> `Execute` prend la branche « pas de cible imposee » (appel IA slot 0x37, options
                  `{allowMoveAction, skipAtomic, true, Nullable<int> moveAmount, customUtility}`) :
                  **c'est l'IA qui CHOISIT la cible**, aucune contrainte d'adjacence n'est cablee.

    CE QUE FONT LES DEUX CHAMPS QUI VARIENT — chaine lue jusqu'au consommateur :
      `Execute` -> `IdunBattle.Core.Services.AiControl$$ExecuteAbilityActionFor(unit, abilityId, options)`
      -> `IdunBattle.AI.Tactics.DefaultAiUnitTactic$$CalculateAbilityActionForUnit` ->
      `IdunBattle.AI.Tactics.DefaultAiUnitTactic.u003CCalculateAbilityActionForUnitu003Ed__6$$MoveNext`, ou :
        * le `Nullable<int>` (issu de `+0x78`) est passe TEL QUEL a
          `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles(unit, true, maxDistance)` = la
          plage de tuiles depuis lesquelles l'acteur peut AGIR. `0` => la tuile COURANTE seule ;
          `null` => la plage de deplacement NORMALE de l'unite (elle peut donc s'approcher) ;
        * `allowMoveAction` (issu de `+0x70`) ajoute le `MovementActionGenerator` (`tactic+0x58`, ecrit
          par `IdunBattle.AI.Tactics.DefaultAiUnitTactic$$.ctor`) a la liste des generateurs d'action :
          l'IA peut alors choisir un DEPLACEMENT PUR si aucune attaque n'est bonne.
      i2 confirme la lecture, et c'est le discriminant le plus net : `PerformAIAttack` => « which then
      immediately **takes a turn** » (ScarabSummon), « The Cadian Guardsman immediately **takes a turn** »
      (ForwardSpotter, CallInReinforcements) ; `...FromCurrentPosition` => « can immediately **attack**,
      but **cannot move this turn** » (AberrantHypermorph, GetEmRuntz).

    CE QUI EN DECOULE, ET QUI EST LE MEME POUR TOUS LES APPELANTS :
      * **attaque NORMALE COMPLETE** via `AttackDamageOperation.execute` (selection d'arme par distance ->
        le Horror tire son ranged r2 PSYCHIC si non-adjacent, melee Physical si adjacent ; auras
        InfernalPacts/WeaverOfFate incluses) ;
      * **dispatch after-hit INCONDITIONNEL** : l'IA execute une VRAIE ability d'attaque, donc
        `IdunBattle.Operations.FinishAttackOperation$$Execute` emet `On(0x26)`/`On(8)`/`On(9)` comme sur
        n'importe quelle attaque normale. AUCUN champ du behaviour ne le gate. MESURE live (diag 202c) : le
        bonus InfernalPacts PSYCHIC (summon Daemon adjacent a Abraxas) met Psychic dans le SET de profils
        -> CHAQUE attaque de summon adjacent a Abraxas re-declenche un Screamer (trigger 1173 sur `On(9)`).
        C'est la PREUVE live que le vecteur after-hit part depuis ce corps ;
      * **domaine de cible = CONTEXTE, jamais un choix du port** : la portee utilisable est celle de
        `IdunBattle.Core.Services.TargetingQuery$$GetRange`, qui clampe `Math.Min(1, range)` si l'acteur
        porte `ForcedInMelee (0x529)`. La free-attack de TheQuickening pose cet effet AVANT d'appeler ce
        corps -> son domaine se REDUIT tout seul a l'adjacence, sans variante de code (`_in_attack_range`
        porte le clamp, cf. `operations/triggers/base.py::_forced_in_melee`).

    CHOIX DE CIBLE — LE MOTEUR D'UTILITE NATIF (#338, plus d'approximation) : l'appel IA slot 0x37 est
    porte par `operations/summon_ai.py::ai_control_execute_ability_action_for` (mirror
    `IdunBattle.Core.Services.AiControl$$ExecuteAbilityActionFor`), qui construit le contexte de decision
    offline (`engine.ai.state_bridge.build_from_state`, `max_distance=0` = `GenerateActionTiles` sur la
    seule tuile courante) puis appelle `engine.ai.tactic.calculate_ability_action_for_unit` (mirror
    `DefaultAiUnitTactic.u003CCalculateAbilityActionForUnitu003Ed__6$$MoveNext`) : UN generateur
    `ActiveAbilityActionGenerator` sur le set d'UNE ability, `Bucket.ChooseAction`.

    L'ability imposee est celle du `Func` `+0x68` : son corps NATIF est
    `IdunBattle.Entities.UnitExtensions$$GetNormalAttackType(unit)` (= `ActiveAbilityComponent+0x28`),
    corps DEDUPLIQUE dont Ghidra ne nomme qu'un proprietaire
    (`...ShockAssaultAbility.u003Cu003Ec$$u003CCreateBehaviouru003Eb__1_0`, 7 slots de delegate y
    pointent) — c'est l'ATTAQUE NORMALE de l'acteur pour les DEUX noeuds. Offline elle porte l'id
    SYNTHETIQUE 17 (`state_bridge.NORMAL_ATTACK_ID` ; le type concret per-unite, ex. `Loki_NormalAttack`
    69, est un etat runtime non derivable de gameconfig — sans impact, la prediction lit l'arme du `ctx`).

    AVANT #338 : `_nearest_enemy` (ennemi vivant le plus proche, tie-break id). MESURE de l'ecart, montage
    `two` de #334 (deux allies mecaniques attaquant chacun une fois) : total identique de part et d'autre
    (18038), mais le natif le VENTILE 7795 + 10243 sur DEUX ennemis la ou le port concentrait 18038 sur un
    seul. Aucun test ne l'attrapait — seule la REPARTITION trahissait le raccourci.

    RESIDUS (communs a tous les appelants) : gate « if able » = `_in_attack_range` (mirror `GetRange`,
    clamp `ForcedInMelee` inclus) evalue depuis la tuile COURANTE — il est desormais passe au moteur comme
    `range_gate`, donc il BORNE l'enumeration des cibles au lieu de couper apres coup (mirror de
    `GetEligibleTargetsForNormalAttack`), et il reste applique a la cible elue (double filet).
    TheQuickening passe en plus un `customUtility` (lambda du display-class de l'ability) : il est threade
    jusqu'a `calculate_ability_action_for_unit` mais IGNORE (non mirrore) — le residu est desormais
    LOCALISE la, pas ici.

    APPROCHE (#348, ex-residu R31) : `move_amount` est passe TEL QUEL a `GenerateActionTiles` (via
    `build_from_state(max_distance=...)`), donc `None` (noeud `PerformAIAttack`) ouvre la PLAGE DE
    DEPLACEMENT NORMALE de l'acteur, et `allow_move_action` ajoute le `MovementActionGenerator` (l'IA
    peut alors choisir un DEPLACEMENT PUR si aucune attaque n'est possible). Les messages rendus par
    `InputBuilder$$GenerateInputMessagesFromUnitAction` sont appliques ICI dans l'ORDRE NATIF
    (`AiControl$$ApplyAiMessages` : `MoveUnitMessage` PUIS `ActiveAbilityMessage`) -- le move passe par
    le handler de message du runner (`MovementHandler.visit_MoveUnitMessage` =
    `IdunBattle.Operations.MoveUnitOperation$$Execute` + `EvaluateAfterMoveTriggers`), donc l'overwatch
    du deplacement s'applique, et l'attaque est calculee depuis la tuile OU L'UNITE EST.
    i2, le discriminant : `PerformAIAttack` => « which then immediately **takes a turn** » ;
    `...FromCurrentPosition` (`move_amount == 0`) => « can immediately **attack**, but **cannot move
    this turn** » -- cette branche-la garde donc la tuile courante pour seul domaine d'action.

    CONTRAT DE RETOUR (inchange) : `None` = AUCUNE ATTAQUE. Un DEPLACEMENT PUR (ou un deplacement suivi
    d'une mort par overwatch) rend donc `None` **apres avoir mute l'etat** -- ses huit consommateurs ne
    tiennent que la comptabilite des ATTAQUES (`_attacks_made`, `_last_attacked`, `attacks[]`), et un
    move n'en est pas une. La cle `moved` du diag porte le deplacement quand l'attaque a bien eu lieu.

    `allowed_targets` (#590, defaut `None` = INCHANGE pour les huit appelants existants) : le
    `customUtility` (`behaviour+0x90`), materialise. Seul `PerformAIAbility` (la surcharge a 6
    arguments de `DSLBehaviors$$PerformAIAbility`) le remplit ; les trois autres noeuds natifs de
    cette famille passent `null` sur ce champ. Cf. l'ecart NOMME (score -> exclusion) dans
    `behaviours/ai_control.py::PerformAIAbility`."""
    from ...operations.triggers.base import _in_attack_range
    # `abilityId = getAbilityType(actor)` (`behaviour+0x68`) = `UnitExtensions$$GetNormalAttackType`.
    # `aiControl.ExecuteAbilityActionFor(actor, abilityId, {allowOnlyMove, skipAtomic, true,
    #                                    Nullable<int> moveAmount, customUtility})` -- slot 0x37.
    # `allowed_targets` (#590) : la materialisation du `customUtility` (`behaviour+0x90`) quand le
    # call-site en fournit un -- `IdunBattle.AI.Utilities.OnlyCertainTargetUtility` restreint les
    # cibles, et le port l'exprime en BORNANT l'enumeration plutot qu'en scorant (ecart NOMME dans
    # `behaviours/ai_control.py::PerformAIAbility`). `None` = aucune contrainte : le gate se reduit
    # exactement au `range_gate` d'avant, donc les huit appelants existants sont INCHANGES.
    # ⚠ LE DOMAINE NATIF EST LA CASCADE DE CIBLAGE COMPLETE, PAS LE SEUL VOLET PORTEE (#334-r2).
    # `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsForNormalAttack(caster, casterPosition)`
    # tient en une ligne : `battleQuery.<slot 0x42>(caster, casterPosition,
    # UnitExtensions$$GetNormalAttackType(caster))` -- et cette surcharge,
    # `IdunBattle.Core.Services.BattleQuery$$GetValidTargets(unit, from, abilityType)`, delegue au
    # slot 6 de son `ITargetingQuery` : la MEME cascade que `get_invalid_target_reason`, pas une
    # comparaison de distance. Le port ne bornait que par `_in_attack_range`
    # (`TargetingQuery$$GetRange` + clamp `ForcedInMelee`), donc il soumettait a l'utilite des cibles
    # que la cascade REFUSE -- et l'argmax en elisait.
    # MESURE (`probe_334_defend_the_divine_work.py --scenario two`, board MC1_67, 2026-08-11) :
    # `admecDestroyer` avait `max_range = 3`, donc `_in_attack_range` acceptait l'ennemi `110` a
    # distance 2 ; la cascade le refuse par `TargetingRule.TargetIsInRange` (`only_adjacent` de ses
    # `TargetingOptions` d'attaque normale), et `valid_normal_attack_targets` ne rendait que `[79]`.
    # Le port faisait frapper `110`, le natif `79`.
    # Mirror utilise : `IdunBattle.Entities.Selectors.ValidNormalAttackTargetsSelector$$Select`
    # (`valid_normal_attack_targets`), qui applique la cascade avec les `TargetingOptions` du TYPE
    # d'attaque normale du caster -- exactement l'`abilityType` que passe le natif.
    # HISSE (#923) au preambule en FORME B (`_targeting`) : ce differe se declarait PORTEUR, mais
    # l'arete `summon -> targeting` etait DEJA posee au niveau module par l'import de
    # `TargetingOptions`/`RANGE_*` -- ni cycle possible, ni cout. Il etait donc GRATUIT.
    _e0 = state.get_entity(int(unit_id))
    _pc0 = _e0.get_component(_PC) if _e0 is not None else None
    _here = (_pc0.col, _pc0.row) if _pc0 is not None else None
    # ⚠ ECART NOMME, et il est BORNE au regime d'APPROCHE : la cascade du port mesure la portee
    # depuis la position REELLE (`get_invalid_target_reason` n'a pas de variante « depuis une tuile
    # hypothetique », cf. la docstring de `valid_normal_attack_targets`), la ou le natif re-evalue
    # `GetEligibleTargetsForNormalAttack` POUR CHAQUE position candidate. On applique donc la cascade
    # sur la tuile COURANTE -- le seul domaine de `...FromCurrentPosition` (`move_amount == 0`) --
    # et on retombe sur le seul volet PORTEE pour les tuiles d'approche de `PerformAIAttack`.
    # `ability_type` (#964-r1) = le `Func<IEntity,int>` `+0x68` MATERIALISE. Les quatre noeuds de
    # cette famille le CACHENT dans leur `<>c` et il vaut alors `GetNormalAttackType(unit)` -- c'est
    # le `None` par defaut, comportement STRICTEMENT inchange pour les huit appelants d'avant. Seule
    # la surcharge a SIX arguments de `DSLBehaviors$$PerformAIAbility` le recoit du call-site, et
    # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ECogSupportAbility$$CreateBehaviour` y passe
    # `<>c$$<CreateBehaviour>b__3_0` = `IdunBattle.Entities.UnitExtensions$$GetRepairType(e)`. L'IA
    # joue donc une REPARATION, pas une attaque.
    _aid = NORMAL_ATTACK_ID if ability_type is None else int(ability_type)
    if ability_type is None:
        _eligible_here = set(int(x) for x in
                             (_targeting.valid_normal_attack_targets(state, int(unit_id)) or ()))
    else:
        # Meme cascade, masque de CETTE ability. `None` (masque non RE-lu) laisse `_eligible_here`
        # a `None` = « le port ne sait pas » -> on ne fabrique pas un domaine vide.
        _vt = _targeting.valid_targets_for(state, int(unit_id), _aid)
        _eligible_here = None if _vt is None else set(int(x) for x in _vt)

    def _gate(t, tile):
        # ⚠ Le clamp `_in_attack_range` (`TargetingQuery$$GetRange` + `ForcedInMelee`) est le volet
        # PORTEE DE L'ARME : il n'a de sens que pour l'attaque normale. Sous une ability EXPLICITE,
        # la portee vit dans le masque de l'ability, donc la cascade seule fait foi.
        if t is None:
            return False
        if ability_type is None and not _in_attack_range(state, unit_id, t, from_pos=tile):
            return False
        tid = t.get("id") if isinstance(t, dict) else t
        if tid is None:
            return False
        if (_eligible_here is not None and _here is not None and tile is not None
                and tuple(tile) == _here and int(tid) not in _eligible_here):
            return False
        if allowed_targets is None:
            return True
        return int(tid) in allowed_targets

    action = ai_control_execute_ability_action_for(
        state, unit_id, _aid, allow_only_move=bool(allow_move_action),
        move_amount=move_amount, range_gate=_gate)
    # --- `AiControl$$ApplyAiMessages(msgs)` : 1. `MoveUnitMessage` -----------------------------------
    _e = state.get_entity(unit_id)
    _pc = _e.get_component(_PC) if _e is not None else None
    origin = (_pc.col, _pc.row) if _pc is not None else None
    moved = _apply_move_message(state, unit_id, (action or {}).get("to"), origin)
    _uc = _e.get_component(_UC) if _e is not None else None
    if _uc is not None and not _uc.alive:
        return None                       # tue par l'overwatch pendant l'approche -> aucune attaque
    # --- 2. `ActiveAbilityMessage` (l'attaque normale imposee) ---------------------------------------
    tgt = action.get("target") if (action or {}).get("kind") == "ability" else None
    # Double filet : la portee EFFECTIVE est re-evaluee depuis la tuile FINALE (post-move), et la
    # contrainte `customUtility` (#590) est re-appliquee au MEME rang -- une cible elue puis devenue
    # hors-liste (le port n'a pas de tel chemin aujourd'hui, mais le filet est symetrique du gate).
    if tgt is None or not _in_attack_range(state, unit_id, tgt):
        return None
    # ⚠ `tgt` est un ID (`action["target"]`), PAS un dict -- l'ecrire `tgt.get("id")` levait un
    # `AttributeError` a la premiere cible retenue. Meme domaine que le `_in_attack_range`
    # ci-dessus, qui prend un id lui aussi.
    if allowed_targets is not None and int(tgt) not in allowed_targets:
        return None
    r = AttackDamageOperation.execute(state, unit_id, tgt)
    if r is None:
        return None
    # L'attaque du summon est une attaque NORMALE COMPLETE cote natif -> dispatcher le vecteur
    # after-attack comme le handler de message (damage.py visit_AttackUnitMessage / summon_ai.py).
    # ⚠ #437 : le `On(9)` qui porte la cascade (Horror ranged Psychic -> trigger 1173 -> Screamer)
    # N'EST PLUS emis par ce vecteur -- il l'est a la SORTIE de `AttackDamageOperation.execute`
    # ci-dessus (`finish_attack_triggers`), qui est le foyer natif (`AttackBehaviour$$Execute` ->
    # `FinishAttack`). La cascade est donc DEJA jouee quand on arrive ici ; ce vecteur ne porte plus
    # que `On(0x26)` / `On(8)` / `On(0x3c)` / `On(0xe)`.
    from ...operations.triggers.dispatch.attack import after_hit_normal_attack
    after = (r.get("finish_attack") or []) + after_hit_normal_attack(
        state, unit_id, tgt, bool(r.get("ranged")),
        r.get("profile"), is_crit=bool(r.get("did_crit")),
        did_block=bool(r.get("did_block")))
    return {"summon": unit_id, "target": tgt, "total": r.get("total"), "after_hit": after,
            "moved": moved, "move_amount": move_amount,
            "allow_move_action": bool(allow_move_action)}


def _apply_move_message(state: "State", unit_id: int, to, origin) -> Optional[tuple]:
    """Volet `MoveUnitMessage` d'`IdunBattle.Core.Services.AiControl$$ApplyAiMessages` : le message
    est POSTE au routeur d'input (`AiControl$$ApplyAiMessage` -> `this+0x40`), donc traite par le MEME
    handler que n'importe quel deplacement -- `MoveUnitOperation$$Execute` + `EvaluateAfterMoveTriggers`.
    Le port passe donc par `MovementHandler.visit_MoveUnitMessage`, jamais par un `MoveUnitOperation`
    recable a la main : c'est ce qui garantit que l'overwatch de l'approche part.

    Gate = celui d'`InputBuilder$$GenerateInputMessagesFromUnitAction` :
    `UnitPosition.op_Inequality(action.Position, null) && !currentPosition.Equals(action.Position)`
    -- destination absente ou EGALE a la tuile courante => AUCUN message emis (l'acteur reste sur
    place, et `MovementActionGenerator` le fait explicitement : la tuile courante est la GRAINE de son
    ensemble de candidats et l'argmax natif remplace en `>` STRICT).
    Rend la tuile atteinte, ou `None` si aucun deplacement n'a eu lieu."""
    if to is None or origin is None or tuple(to) == tuple(origin):
        return None
    MovementHandler(state, EventBus()).visit_MoveUnitMessage(MoveUnitMessage(unit_id, tuple(to)))
    return tuple(to)


def perform_ai_attack_from_current_position(state: "State", unit_id: int) -> Optional[dict]:
    """`IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAttackFromCurrentPosition(unit, utilityEntity,
    customUtility, skipAtomicCheck)` — CONSTRUCTEUR : il pose `+0x70 = 0` (pas de deplacement pur) et
    `+0x78 = factory+0xb8`, le singleton **`Direct(0)`** alloue par
    `IdunBattleLogic.Entities.DSLFactory$$.ctor` (meme famille que `+0xc0 = Direct(1)`). Budget de
    deplacement **0** : c'est LITTERALEMENT le « FromCurrentPosition ».

    Le corps est `perform_ai_ability_unit_behaviour` — il n'y a qu'UN corps pour les deux noeuds."""
    return perform_ai_ability_unit_behaviour(state, unit_id, allow_move_action=False, move_amount=0)


def perform_ai_attack(state: "State", unit_id: int, allow_move_action: bool,
                      move_amount: Optional[int]) -> Optional[dict]:
    """`IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAttack(unit, allowMoveAction, moveAmount,
    utilityEntity, customUtility)` — CONSTRUCTEUR du noeud COUSIN : MEME
    `PerformAIAbilityUnitBehaviour` que `...FromCurrentPosition`, mais `+0x70` et `+0x78` viennent de
    L'APPELANT (et `+0x71 skipAtomicCheck` retombe a 0).

    XREFS EXHAUSTIVES du noeud (`list_xrefs` sur `IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAttack`,
    build `rnca9r7q6c`) : **SEPT** call-sites. SIX passent le MEME couple
    `PerformAIAttack(<selecteur>, 1, 0, 0, 0)` — `ScarabSummonAbility$$ExecuteBehaviour` (@0x180),
    `ForwardSpotterAbility$$ExecuteBehaviour` (@0x180), `CallInReinforcementsAbility$$CreateBehaviour`,
    `HunterOfSoulsAbility$$CreateBehaviour` (@0x30), `TheArdentBlade_TriggerAbility$$CreateBehaviour`,
    `CallRipperSwarms_SpawnAbility$$CreateBehaviour` (@0x68). Donc **`allowMoveAction = true`** et
    **`moveAmount = null`** (le litteral `1` de `PerformAIAttack(1)` est le BOOL `+0x70`, PAS un budget de
    deplacement de 1 — piege de lecture : c'est le 2e argument, l'amount est le 3e et vaut 0/nul).

    ⚠ **LE SEPTIEME EST DIFFERENT, et il ouvre une TROISIEME forme du couple** :
    `AetherStrideAbility$$ExecuteBehaviour` fait `PerformAIAttack(targets@0x68, 0, <DSLFormulas+0x18>,
    0, 0)` — `allowMoveAction = FALSE` et un `moveAmount` NON NUL qui est un noeud `IAmount` cache du
    DSL. `GenerateActionTiles` recevrait donc un budget de deplacement ENTIER, ni `0` ni `null` : ni
    `build_from_state(max_distance=...)` ni le pathfinder ne portent cet override (toute valeur autre
    que `0`/`None` y retombe sur `0`). RESIDU NOMME, INERTE ICI : 1208 `AetherStride`
    (`thousDaemonPrince`) n'est pas portee, donc aucun appelant du port n'emprunte cette branche.

    Le corps est `perform_ai_ability_unit_behaviour` — il n'y a qu'UN corps pour les deux noeuds."""
    return perform_ai_ability_unit_behaviour(state, unit_id, allow_move_action=bool(allow_move_action),
                                             move_amount=move_amount)


def _nearest_enemy(state: "State", unit_id: int) -> Optional[int]:
    """Ennemi VIVANT le plus proche (distance hex) de `unit_id`. None si pas de position/board ou aucun
    ennemi. Tie-break `id` (déterministe).

    ⚠ **Ce n'est PLUS le choix de cible de `PerformAIAttack`** (#338) : ce corps le tenait pour une
    approximation du moteur d'utilité natif, mesurée FAUSSE sur la répartition (cf.
    `perform_ai_ability_unit_behaviour`). Il ne reste qu'un helper GEOMETRIQUE, consommé par les tests
    (établir qu'un montage est discriminant : quel ennemi le raccourci aurait élu). Aucun chemin
    d'exécution du moteur ne l'appelle."""
    e = state.get_entity(unit_id)
    pc = e.get_component(PositionComponent) if e is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    if pc is None or oc is None:
        return None
    src = (pc.col, pc.row)
    best = None
    best_key = None
    for eid, o in state.entities.items():
        if eid == unit_id:
            continue
        ooc = o.get_component(OwnerComponent)
        ouc = o.get_component(UnitComponent)
        opc = o.get_component(PositionComponent)
        if ooc is None or opc is None or ooc.team == oc.team:      # ennemis uniquement
            continue
        if ouc is not None and not ouc.alive:
            continue
        key = (hexgeo.distance(src, (opc.col, opc.row)), eid)
        if best_key is None or key < best_key:
            best_key, best = key, eid
    return best


class ScarabHiveAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$ExecuteBehaviour (id 1007, necroSpyder — le SUMMONER).

    #149 slice-10 : la behaviour EST l'**arbre DSL** `scarab_hive_tree()` (mirror 1:1 du décompilé IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$ExecuteBehaviour :
    un noeud `Spawn` UNIQUE en plain `Execute` portant `WithStatsFromConfig` + AddEffect(0x4a3) + on-appearance
    `UseNormalAttackIfAble` embarqués — cf. la feuille `SpawnSummon`), en remplacement du portage impératif
    (spawn + boucle on-appearance câblés à la main). La feuille délègue le SPAWN à l'Operation VALIDÉE
    LIVE-BIT-EXACT `SpawnUnitOperation.execute` (2× necroSmnSwarm team/player du caster, stats `ability_var`,
    tuiles libres adjacentes à la cible — le count-2/placement/`WithStatsFromConfig` vivent dans
    `SpawnUnitBehaviour`, hors DSL-sélecteurs) puis l'on-appearance `UseNormalAttackIfAble(target)` (profil
    Piercing override immédiat). VALIDÉ live : spawn bit-exact (cf. test_summon_spawn_live, via l'Operation) ;
    wiring message + on-appearance (cf. test_summon_trigger_live, via cette classe -> l'arbre). GAP flaggé
    (tâche) : l'effet PERSISTANT 0x4a3 (OverrideDamageProfile des attaques des TOURS SUIVANTS) non matérialisé/lu.

    ⚠ DISTINCT de `ScarabSummonAbility` IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$ExecuteBehaviour (id 1047) = l'auto-DÉDOUBLEMENT porté par le scarab
    SPAWNÉ lui-même (spawn adjacent à SOI, stats clonées du parent via CopyOwner, on-appearance
    PerformAIAttack) — encore impératif. Ne PAS confondre les deux (même unitId necroSmnSwarm, mais
    summoner-scaled vs clone-du-parent)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ScarabHive)  # 1007

    # GATE DE CIBLE + PORTEE -- forme de ctor = **FLAGS DIRECTS**, la 1re des trois (le litteral EST
    # le masque : cette surcharge ecrit `Rules` tel quel, il n'y a aucun preset a OR-er).
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$.ctor` recopie d'abord les
    # 0x18 octets du `TargetingRange` STATIQUE +0x30 du bloc `<TargetingRange class>+0xb8`, puis :
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, &range, forceMeleeTarget=1, 0x4020, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 1, 0)   # 3e arg = 1 = AbilityAttackType.SummonAndAttackTarget
    # Decomposition EXHAUSTIVE de 0x4020 (0x20 + 0x4000 = 0x4020, aucun bit residuel) :
    #     0x20    (bit 5)  TargetHasFreeAdjacentTile -> PORTE. Filtre statique :
    #                      `if ((rules & 0x20) && battleQuery.<slot 0x52>GetFreeAdjacentTiles(target)
    #                      .Count == 0) -> broken(0x20)`. C'est la precondition MECANIQUE de
    #                      l'ability : les deux necroSmnSwarm naissent sur des tuiles LIBRES
    #                      ADJACENTES A LA CIBLE (`First(SortByDistance(CanAddUnit(AdjacentTiles(
    #                      target)), caster), i)` dans `SpawnUnitBehaviour$$Execute`) -- une cible
    #                      encerclee n'offre nulle part ou les poser.
    #     0x4000  (bit 14) TargetIsEnemy -> PORTE (`TargetingQuery$$UnitsCanAttackEachOther`) : refus
    #                      sur soi-meme et sur un allie.
    # PORTEE : `TargetingRange` statique +0x30, ecrit par
    # `IdunBattle.Core.Services.TargetingRange$$.cctor` (`+0x30` = 0 -> onlyAdjacent = `RangedBool.True`,
    # useRangeFromConfig = useWholeBoard = false ; `+0x38` = `Nullable(1)` overrideRange ; `+0x40` = null
    # overrideRangeFunc) = `RANGE_ADJACENT`. Le filtre prend donc la branche
    # `battleQuery.AreEntitiesAdjacent(casterTiles, target)` : le necroSpyder doit etre AU CONTACT de sa
    # cible. `forceMeleeTarget` (4e arg) = 1 = `RangedBool.False` : aucun clamp melee a poser, la portee
    # EST deja l'adjacence.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetHasFreeAdjacentTile | TR.TargetIsEnemy,
        self_cast=False, range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        # behaviour = arbre DSL (feuille SpawnSummon) : émet les MÊMES Operations que l'impératif
        # (`SpawnUnitOperation.execute` + `_summon_on_appearance_attack`) -> même mutation, même diag.
        ectx = ExecutionContext(state=state, rng=state.rng)
        scarab_hive_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = [{"summon": p["summon"], "total": p["total"]}
                   for n, p in ectx.emitted if n == "SummonOnAppearance"]
        visual_id = ((GC.ability("ScarabHive") or {}).get("constants") or {}).get("unitId")
        return {"summon": visual_id, "spawned": spawned, "attacks": attacks, "dsl": True}


class ScarabSummonAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$ExecuteBehaviour` (id 1047, necroSmnSwarm — auto-DÉDOUBLEMENT).

    #149 slice-11 : la behaviour EST l'**arbre DSL** `scarab_summon_tree()` (mirror 1:1 du décompilé IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$ExecuteBehaviour :
    un noeud `Spawn` UNIQUE en plain `Execute` portant `SpawnUnitOptions.CopyOwner(caster)` + un seul
    sous-behaviour embarqué `+0x18 = PerformAIAttack(1)` on-appearance — cf. la feuille `SpawnReplica`), en
    remplacement du portage impératif (spawn + boucle on-appearance câblés à la main). La feuille délègue le
    SPAWN à l'Operation VALIDÉE `SpawnUnitOperation.execute_self_replica` (`IdunBattle.Entities.Behaviours.SpawnUnitOptions$$CopyOwner` = clone
    owner+stats du parent, count-1, tuiles libres adjacentes à SOI) puis l'on-appearance
    `PerformAIAttack(Spawned@0x180, 1, 0, 0, 0)` — routé sur le CORPS UNIQUE
    `perform_ai_ability_unit_behaviour` via `perform_ai_attack(state, sid, True, None)` : gate de portée
    (`_in_attack_range`, mirror `TargetingQuery$$GetRange`) + attaque normale complète + dispatch after-hit
    `On(0x26)`/`On(8)`/`On(9)`. Avant le de-fork résiduel, cette feuille recâblait `_nearest_enemy` +
    `AttackDamageOperation.execute` À LA MAIN — sans gate de portée (le double frappait un ennemi à 5 hex avec
    une arme de mêlée) et sans vecteur after-hit (aucun trigger post-attaque ne partait du double).

    Chance gameconfig = 50 ; playbook `ScarabSummonPlaybook`. ⚠ DISTINCT de `ScarabHiveAbility` IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$ExecuteBehaviour (id
    1007, necroSpyder) = spawn summoner-scaled `WithStatsFromConfig` + AddEffect(0x4a3) + attaque de la CIBLE ;
    ici clone-du-parent `CopyOwner` + attaque AI du double, sans effet. GAP (inchangé) : cap de duplication
    (`UnitDuplicationLimitSelector`/`LimitUnitDuplications`) non porté (récurrence non bornée offline)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ScarabSummon)  # 1047

    # GATE DE CIBLE + PORTEE -- forme de ctor = **FLAGS DIRECTS**, la 1re des trois.
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$.ctor` recopie le
    # `TargetingRange` STATIQUE +0x60 (PAS le +0x30 de ScarabHive : deux abilities du MEME fichier,
    # meme forme de ctor, `TargetingRange` DIFFERENTS), puis :
    #     TargetingOptions..ctor(&opts, isSelfCasting=1, &range, forceMeleeTarget=1, 0x208000, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)   # 3e arg = 2 = AbilityAttackType.Others
    # Decomposition EXHAUSTIVE de 0x208000 (0x8000 + 0x200000, aucun bit residuel) :
    #     0x8000    (bit 15) CasterIsPossibleTarget -> DECLARATIF, jamais une regle de refus (il
    #                        n'apparait NI dans le filtre statique NI dans `GetInvalidCasterReason`) :
    #                        `TargetingOptions$$get_CanTargetCaster` le lit pour les consommateurs de
    #                        ciblage (preview / IA). En faire un refus INVENTERAIT une regle.
    #     0x200000  (bit 21) CasterHasFreeAdjacentTile -> regle REELLE du filtre statique, jumelle
    #                        exacte du bit 5 mais appliquee au CASTER :
    #                        `if ((rules & 0x200000) && battleQuery.<slot 0x52>GetFreeAdjacentTiles(
    #                        CASTER).Count == 0) -> broken(0x200000)` (immediatement APRES la clause
    #                        du bit 5, AVANT `TargetTileIsFree`). Semantiquement : le scarab ne peut se
    #                        dedoubler que s'il a une tuile libre au contact (`PickRandomly(CanAddUnit(
    #                        AdjacentTiles(self)), 1)`). NON PORTEE, et INATTEIGNABLE par la cascade du
    #                        port pour CE porteur -- cf. le residu documente dans la fiche du cas :
    #                        cible == caster -> l'aiguillage self-cast branche sur
    #                        `GetCasterNotAddedReason` AVANT le filtre ; cible != caster -> le volet
    #                        PORTEE (range 0) refuse deja sur `TargetIsInRange`, qui PRECEDE le bit 21
    #                        dans la cascade. Un port serait donc du code mort non invalidable.
    # PORTEE : `TargetingRange` statique +0x60 (`TargetingRange$$.cctor` : `+0x60` = 1 -> onlyAdjacent =
    # `RangedBool.False`, `+0x68` = `Nullable(0)` overrideRange, `+0x70` = null) = `RANGE_SELF`. Portee
    # **0** : le filtre calcule `GetDistance(casterTiles, target)` et refuse `TargetIsInRange` des que
    # d > 0 -- l'auto-dedoublement ne se cible QUE lui-meme. `forceMeleeTarget` = 1 = `RangedBool.False`.
    # `isSelfCasting = 1` (`options+0x00`) : quand la cible EST le caster, l'overload 5 arguments de
    # `TargetingQuery$$GetInvalidTargetReason` branche sur `GetCasterNotAddedReason` et n'evalue JAMAIS
    # la cascade (cf. `_targets_the_caster`).
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.CasterIsPossibleTarget | TR.CasterHasFreeAdjacentTile,
        self_cast=True, range=RANGE_SELF, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # behaviour = arbre DSL (feuille SpawnReplica) : émet les MÊMES Operations que l'impératif
        # (`SpawnUnitOperation.execute_self_replica` + `AttackDamageOperation.execute`) -> même mutation, même diag.
        ectx = ExecutionContext(state=state, rng=state.rng)
        scarab_summon_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        # Tuile d'ATTERRISSAGE par clone : depuis #348 le double PEUT se deplacer avant de frapper
        # (`+0x78 moveAmount = null`), donc sa position finale n'est plus son point de chute -- et
        # c'est le point de chute que verifie le placement `AdjacentTiles(self)`.
        spawn_pos = {p["unit"]: p.get("pos") for n, p in ectx.emitted if n == "SpawnUnit"}
        attacks = [{"summon": p["summon"], "target": p["target"], "total": p["total"],
                    "moved": p.get("moved")}
                   for n, p in ectx.emitted if n == "ReplicaOnAppearance"]
        visual_id = ((GC.ability("ScarabSummon") or {}).get("constants") or {}).get("unitId")
        return {"summon": visual_id, "spawned": spawned, "spawn_pos": spawn_pos,
                "attacks": attacks, "replica": True, "dsl": True}


class GetEmRuntzAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$ExecuteBehaviour` (id 1045, orksRuntherd/Snotflogga). Spawn UN grot par
    hex LIBRE adjacent au caster **ET** adjacent à un ennemi, chaque grot attaque à l'apparition
    (`PerformAIAttackFromCurrentPosition`) puis Taunte l'ennemi frappé (`TauntWithNewChildrenWhoDidDamage`).

    #149 slice-2b : la behaviour EST l'**arbre DSL** `getemruntz_tree()` (mirror 1:1 du décompilé
    IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$ExecuteBehaviour : `ExecuteAtomic(Spawn) ; Execute(PerformAIAttack + Foreach(Children, Taunt))`), en
    remplacement du portage impératif (spawn + on-appearance + Taunt câblés à la main). **PROUVÉ bit-exact**
    (replay-diff DSL == impératif) puis **CONFRONTÉ LIVE** (tracer-v2 DSLFactory #200 : arbre natif capturé
    == ce mirror, cf. docs/rl/dsl-effect-nodes.md). L'impératif `SpawnUnitOperation.execute_getemruntz` a été
    **RETIRÉ** (#199) — la behaviour est le seul arbre DSL."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.GetEmRuntz)  # 1045

    # GATE DE CIBLE + PORTEE -- forme de ctor = **PRESET STATIQUE COPIE**, la 3e des trois :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$.ctor` n'appelle AUCUN
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor`. Il recopie les 0x40 octets du champ STATIQUE
    # de `TargetingOptions` a l'offset RELATIF +0x280 du bloc `<TargetingOptions class>+0xb8`, puis :
    #     AActiveAbility..ctor(this, &opts, 2, 0)   # 3e arg = 2 = AbilityAttackType.Others
    # Aucun litteral de masque n'est visible dans le ctor : le contenu est ecrit par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` (bloc statics+0x280) --
    #     <preset>+0x00 isSelfCasting    = 1
    #     <preset>+0x08 range            <- `TargetingRange` statics+0x60 = RANGE_SELF
    #     <preset>+0x20 forceMeleeTarget = 1 = RangedBool.False
    #     <preset>+0x28 rules            = 0x8004
    #     <preset>+0x30/+0x38 delegues   = 0 (ecrases par `AActiveAbility$$.ctor`)
    # Decomposition EXHAUSTIVE de 0x8004 (0x4 + 0x8000, aucun bit residuel) :
    #     0x4     (bit 2)  CasterMatchesDynamicRule -> regle du volet CASTER
    #                      (`TargetingQuery$$GetInvalidCasterReason`, regle-delegue `options+0x30`
    #                      liee au slot vtable `this+0x470`). NON PORTEE (le port n'a de point
    #                      d'extension que pour la regle dynamique de CIBLE). Le corps EXISTE et est
    #                      lu : `IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$GetDynamicInvalidCasterReason`
    #                      evalue `GetEmRuntzAbility$$GetSpawnTileSelector` sur `(caster, casterTiles)`
    #                      et rend le litteral **2** si la liste est VIDE, 0 sinon -- « pas une seule
    #                      tuile libre adjacente au caster ET adjacente a un ennemi => cast refuse ».
    #                      Residu NOMME dans la fiche du cas.
    #     0x8000  (bit 15) CasterIsPossibleTarget -> DECLARATIF (lu par
    #                      `TargetingOptions$$get_CanTargetCaster`), jamais une regle de refus.
    # PORTEE : `TargetingRange` statics+0x60 (`TargetingRange$$.cctor` : onlyAdjacent = `RangedBool.False`,
    # overrideRange = `Nullable(0)`) = `RANGE_SELF` -> portee **0** : toute cible autre que le caster est
    # refusee sur `TargetIsInRange`. `isSelfCasting = 1` -> cible == caster : aiguillage
    # `GetCasterNotAddedReason` (non porte -> 0, permissif).
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.CasterMatchesDynamicRule | TR.CasterIsPossibleTarget,
        self_cast=True, range=RANGE_SELF, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_caster_reason(self, state: "State", caster_id: int) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$GetDynamicInvalidCasterReason`
        — MIRROR 1:1 du decompile (la regle-delegue `options+0x30` armee par le bit
        `CasterMatchesDynamicRule` du masque ci-dessus) :

            ctx = default(SelectorContext); ctx.subject = caster; ctx.casterTiles = casterTiles;
            sel = this.GetSpawnTileSelector();
            list = sel.Select(ctx);
            return (list.Count > 0) ? 0 : 2;

        Le litteral rendu est **2** — que l'enum genere nomme `TargetMatchesDynamicRule`. Ce n'est
        PAS une erreur de transcription : le natif reutilise ce code pour la regle dynamique du volet
        CASTER (`GetInvalidCasterReason` le re-emballe tel quel via `GenericBrokenTargetingRule(r)`),
        et l'oracle `abilityReason` le rend litteralement `TargetMatchesDynamicRule`.

        Semantique : « Get 'Em Runtz » ne peut pas etre caste s'il n'existe AUCUNE tuile libre
        adjacente au Runtherd **ET** adjacente a un ennemi vivant non-Steppable -- c'est-a-dire
        aucune place ou poser un grot. Le selecteur est le MEME objet que celui de l'arbre de
        behaviour (`get_spawn_tile_selector()`, mirror confirme live #200), donc le gate et
        l'execution ne peuvent pas diverger.

        MESURE #250 (board `C3_26`, seed 31337) : le Runtherd finit sur une tuile sans spawn tile
        valide, le natif rend `casterReason = 0x2` ET le repercute en `targetReason` sur les 5
        lignes (l'overload 5 arguments de `TargetingQuery$$GetInvalidTargetReason` rend la raison
        CASTER telle quelle). Sans ce port, le moteur acceptait le cast."""
        tiles = get_spawn_tile_selector().evaluate(entities_from_state(state, caster_id)) or []
        return 0 if tiles else int(TR.TargetMatchesDynamicRule)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # behaviour = arbre DSL (couche effet-nœuds) ; les feuilles émettent les MÊMES Operations que
        # l'impératif (`AttackDamageOperation`/`AddEffectOperation`/`_spawn_config_grot`) -> même mutation.
        ectx = ExecutionContext(state=state, rng=state.rng)
        getemruntz_tree().execute(entities_from_state(state, caster_id), ectx)
        # diag depuis les émissions de l'arbre (mêmes champs que l'ancien retour impératif)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = next((p["attacks"] for n, p in ectx.emitted if n == "PerformAIAttack"), [])
        taunted = [p["target"] for n, p in ectx.emitted if n == "AddBondEffect"]
        return {"summon": "orksGrot", "spawned": spawned, "attacks": attacks, "taunted": taunted,
                "getemruntz": True, "dsl": True}


MASTER_EFFECT = int(EffectType.MasterOfTheTutelaries)   # 1197 (0x4ad) — marqueur until-EoT (arme 1173)


class SpawnTutelaryHorror(AbilityBehaviour):
    """Feuille `Spawn` du volet Pink Horror de `IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$ExecuteBehaviour` :
        Spawn( caster@0x160, TARGET@0x178 = la TUILE ciblée par le cast (hex libre adjacent),
               unitId = GetStringConstant(config, 0) = "thousSmnPinkHorror",
               SpawnUnitOptions.WithStatsFromConfig(config 1096,
                                                    AbilityLevelAmount(Self@0x148, AbilityType(1096)))
                 .onAppearance(+0x18) = PerformAIAttackFromCurrentPosition(Spawned@0x180) )
    Le placement N'EST PAS un sélecteur ici : la tuile EST la cible du cast (choisie par le joueur/l'IA,
    légalité = abilityTargets kind="tile") → la feuille porte `tile_id` résolu par la classe d'ability.
    Spawn délégué à `_spawn_config_grot` (WithStatsFromConfig = summonHp/summonDmg[level actif du caster],
    CopyOwner team+player) puis on-appearance `perform_ai_attack_from_current_position` (pipeline attaque
    normale COMPLET, arme par distance → ranged r2 PSYCHIC si non-adjacent, melee Physical+bonus
    InfernalPacts Psychic si adjacent → déclenche le Screamer dans les DEUX cas, l'effet 1197 étant
    posé AVANT ce Spawn dans l'arbre). Émet 'SpawnUnit'/'SummonOnAppearance'."""
    __slots__ = ("tile_id",)

    def __init__(self, tile_id):
        self.tile_id = tile_id

    def execute(self, entities, ectx):
        state = ectx.state
        caster_id = (entities.caster or {}).get("id")
        if state is None or caster_id is None or self.tile_id is None:
            return OperationResult.ok()
        consts = (GC.ability("MasterOfTheTutelaries") or {}).get("constants") or {}
        vid = consts.get("unitId")                       # thousSmnPinkHorror (GetStringConstant(config, 0))
        ce = state.get_entity(caster_id)
        coc = ce.get_component(OwnerComponent) if ce is not None else None
        csc = ce.get_component(StatsComponent) if ce is not None else None
        c_ctx = csc.ctx if csc is not None else None
        if vid is None or coc is None or c_ctx is None:
            return OperationResult.ok()
        level = getattr(c_ctx, "active_ability_level", None)   # AbilityLevelAmount(Self, 1096)
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100)
        gid = _spawn_config_grot(state, vid, self.tile_id, "MasterOfTheTutelaries", level, mult,
                                 coc.team, coc.player)
        if gid is None:
            return OperationResult.ok()
        ectx.emit("SpawnUnit", unit=gid)
        att = perform_ai_attack_from_current_position(state, gid)
        if att is not None:
            ectx.emit("SummonOnAppearance", summon=gid, target=att["target"], total=att["total"])
        return OperationResult.ok()


def master_of_the_tutelaries_tree(tile_id) -> Seq:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$ExecuteBehaviour` (id 1096, thousInfernalMaster
    Abraxas — MIRROR 1:1 du DÉCOMPILÉ) :
        op_BitwiseAnd( AddEffect(0x4ad=1197, AbilityStateReference, caster@0x160, caster@0x160,
                                 durée @dsl+0xc0),
                       Spawn(caster@0x160, Target@0x178=TUILE, "thousSmnPinkHorror",
                             WithStatsFromConfig(config, AbilityLevelAmount(Self@0x148, 1096))
                               .onAppearance = PerformAIAttackFromCurrentPosition) )
    ORDRE NATIF : AddEffect PUIS Spawn (op_BitwiseAnd gauche→droite, les deux exécutent) — l'effet 1197
    est ACTIF avant l'attaque immédiate du Horror → son attaque déclenche DÉJÀ un Screamer (ranged
    Psychic OU melee+bonus InfernalPacts Psychic — mesure live diag 202c ; la chaîne se poursuit tant
    que chaque summon adjacent à Abraxas attaque). Port : `Seq(AddEffect, SpawnTutelaryHorror)`.
    Durée : nœud `@dsl+0xc0` = **`Direct(1)`** (#98 — le singleton constant alloué par
    `DSLFactory..IdunBattleLogic.Entities.DSLFactory$$.ctor` ; MÊME nœud que le `duree@0xc0` de Waaagh IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour et que le
    `amount = df@0xc0 = Const(1)` d'AddEffectOrIncreaseLevel). Ce n'est donc PAS un `TurnsFromRounds`
    (résidu « non résolu » FERMÉ) : la valeur arrive telle quelle dans le `param_6` d'`AddEffect
    IdunBattle.Operations.AddEffectOperation$$Execute`, qui ne la convertit pas → **1 TOUR** (`duration_turns=1`,
    comportement inchangé)."""
    return Seq(AddEffect(MASTER_EFFECT, "MasterOfTheTutelaries", Caster(), duration_turns=1),
               SpawnTutelaryHorror(tile_id))


class MasterOfTheTutelariesAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$ExecuteBehaviour` (id 1096, Abraxas thousInfernalMaster —
    #202-C). Cast TILE-TARGET (« Summon a Pink Horror on a free hex adjacent to Abraxas ») :
    pose l'effet-marqueur 1197 sur SOI (arme la triggered 1173 = Screamer sur attaque Psychic vs ennemi,
    cf. `EFFECT_TRIGGERS[1197]` + `MasterOfTheTutelariesEffect`) PUIS spawn le Pink Horror sur la tuile
    ciblée, qui attaque immédiatement sans bouger (`PerformAIAttackFromCurrentPosition`).

    `target_id` = id de TUILE (cast tile-target, abilityTargets kind="tile" — même convention que la
    cible d'une self-cast AoE, cf. NCContext.tile_id_by_pos). Un target_id qui n'est pas une tuile du
    board → Spawn no-op (le AddEffect s'exécute quand même : ordre d'arbre préservé, diag `spawned=[]`).
    IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$.ctor : `TargetingOptions(0, statsFromClass, 1, 0x1040)` + `AActiveAbility(…, 2)`."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.MasterOfTheTutelaries)  # 1096

    # GATE DE CIBLE + PORTEE -- forme de ctor = **FLAGS DIRECTS**, la 1re des trois. Le ctor recopie
    # d'abord les 0x18 octets du `TargetingRange` STATIQUE +0x30 (le MEME que ScarabHive -- ce que la
    # ligne « statsFromClass » de l'ancienne docstring designait par erreur), puis :
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, &range, forceMeleeTarget=1, 0x1040, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)   # 3e arg = 2 = AbilityAttackType.Others
    # Decomposition EXHAUSTIVE de 0x1040 (0x40 + 0x1000, aucun bit residuel) :
    #     0x40    (bit 6)  TargetIsTile -> DOMAINE TUILE, et 1re regle de refus de la cascade :
    #                      `mainTile = GetMainTile(target); if (!TileExtensions.IsWalkable(mainTile,
    #                      true) && !(rules & AllowUnwalkableTargetTile)) -> broken(1)`. ⚠ le natif
    #                      rend le LITTERAL 1 (`TargetingRule.ValidRequest`) : une tuile-cible non
    #                      marchable se lit `0x1`, pas `0x40`. `AllowUnwalkableTargetTile` (bit 43)
    #                      n'est PAS pose.
    #     0x1000  (bit 12) TargetTileIsFree -> `if (!TileExtensions.CanAddUnit(mainTile, state, 1, 0,
    #                      0)) -> broken(0x1000)` : la tuile doit pouvoir ACCUEILLIR le Pink Horror.
    # PORTEE : `TargetingRange` statique +0x30 (`IdunBattle.Core.Services.TargetingRange$$.cctor` :
    # onlyAdjacent = 0 = `RangedBool.True`, overrideRange = `Nullable(1)`) = `RANGE_ADJACENT` -> le
    # filtre prend la branche `battleQuery.AreEntitiesAdjacent(casterTiles, target)` : la tuile visee
    # doit etre AU CONTACT d'Abraxas -- c'est litteralement le « on a free hex adjacent to Abraxas »
    # de l'i2. `forceMeleeTarget` = 1 = `RangedBool.False`. AUCUNE regle de camp (`TargetIsFriendly` /
    # `TargetIsCaster` absents) -> `refuses_all_enemy_targets` reste False, le veto de routage IA est
    # inchange.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetIsTile | TR.TargetTileIsFree,
        self_cast=False, range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
        board = state.board
        tile_id = target_id if (board is not None and target_id in board.by_id) else None
        ectx = ExecutionContext(state=state, rng=state.rng)
        master_of_the_tutelaries_tree(tile_id).execute(entities_from_state(state, caster_id), ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = [{"summon": p["summon"], "target": p["target"], "total": p["total"]}
                   for n, p in ectx.emitted if n == "SummonOnAppearance"]
        effect = next((True for n, _p in ectx.emitted if n == "AddEffect"), False)
        return {"summon": "thousSmnPinkHorror", "spawned": spawned, "attacks": attacks,
                "effect_1197": effect, "tile": tile_id, "dsl": True}


class SpawnAberrant(AbilityBehaviour):
    """Feuille `Spawn` de `IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour` (id 1166, genesBiophagus) :
        Spawn( caster@0x160, TARGET@0x178 = la TUILE ciblee par le cast (hex libre adjacent au caster),
               unitId = GetStringConstant(config, 0) = "genesSmnAberrant",
               SpawnUnitOptions.WithStatsFromConfig(config 1166,
                                                    AbilityLevelAmount(Self@0x148, AbilityType(1166)))
                 .onAppearance(+0x18) = PerformAIAttackFromCurrentPosition(Target@0x178) )
    Mirror 1:1 de `SpawnTutelaryHorror` (IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$ExecuteBehaviour volet Spawn) SANS le AddEffect(1197) et avec la config
    1166. Le placement N'EST PAS un selecteur : la tuile EST la cible du cast (choisie par le joueur/l'IA,
    legalite = abilityTargets kind="tile", hex libre adjacent au caster via TargetingOptions 0x1040 --
    ctor IDENTIQUE a MasterOfTheTutelaries IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$.ctor) -> la feuille porte `tile_id` resolu par la classe.
    Spawn delegue a `_spawn_config_grot` (WithStatsFromConfig = summonHp/summonDmg/summonArmor[level actif
    du caster] x mult, CopyOwner team+player du caster).

    ON-APPEARANCE : le natif passe `Target@0x178` (le MEME selecteur que la tuile de spawn) comme SUJET de
    `PerformAIAttackFromCurrentPosition`, la ou MasterOfTheTutelaries passe `Spawned@0x180` -- les DEUX
    resolvent au MEME summon (Target@0x178 apres le spawn = l'unite POSEE sur la tuile-cible = le summon
    fraichement cree, la tuile etant libre AVANT le spawn par la legalite du cast). Outcome identique ->
    port = `perform_ai_attack_from_current_position(state, gid)` (pipeline attaque normale COMPLET, arme par
    distance : le genesSmnAberrant n'a qu'une arme melee 1-hit Physical -> attaque l'ennemi le plus proche
    s'il est A PORTEE melee, sinon no-op fidele). Emet 'SpawnUnit'/'SummonOnAppearance'. Effet PUR."""
    __slots__ = ("tile_id",)

    def __init__(self, tile_id):
        self.tile_id = tile_id

    def execute(self, entities, ectx):
        state = ectx.state
        caster_id = (entities.caster or {}).get("id")
        if state is None or caster_id is None or self.tile_id is None:
            return OperationResult.ok()
        consts = (GC.ability("AberrantHypermorph") or {}).get("constants") or {}
        vid = consts.get("unitId")                       # genesSmnAberrant (GetStringConstant(config, 0))
        ce = state.get_entity(caster_id)
        coc = ce.get_component(OwnerComponent) if ce is not None else None
        csc = ce.get_component(StatsComponent) if ce is not None else None
        c_ctx = csc.ctx if csc is not None else None
        if vid is None or coc is None or c_ctx is None:
            return OperationResult.ok()
        level = getattr(c_ctx, "active_ability_level", None)   # AbilityLevelAmount(Self, 1166)
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100)
        gid = _spawn_config_grot(state, vid, self.tile_id, "AberrantHypermorph", level, mult,
                                 coc.team, coc.player)
        if gid is None:
            return OperationResult.ok()
        ectx.emit("SpawnUnit", unit=gid)
        att = perform_ai_attack_from_current_position(state, gid)
        if att is not None:
            ectx.emit("SummonOnAppearance", summon=gid, target=att["target"], total=att["total"])
        return OperationResult.ok()


def aberrant_hypermorph_tree(tile_id) -> SpawnAberrant:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour` (id 1166, genesBiophagus -- MIRROR
    1:1 du DECOMPILE) :
        Execute( Spawn(caster@0x160, Target@0x178=TUILE, "genesSmnAberrant",
                       WithStatsFromConfig(config, AbilityLevelAmount(Self@0x148, 1166))
                         .onAppearance = PerformAIAttackFromCurrentPosition(Target@0x178)) )
    UN SEUL noeud `Spawn` (plain `AActiveAbility.Execute`, PAS `ExecuteAtomic`, PAS d'AddEffect, PAS de
    op_BitwiseAnd -- le noeud top-level passe a Execute EST le Spawn seul). Count=1 (une seule tuile-cible).
    DISTINCT de MasterOfTheTutelaries IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$ExecuteBehaviour (op_BitwiseAnd(AddEffect(1197), Spawn) + onAppearance
    Spawned@0x180) : ici PAS d'effet-marqueur et l'onAppearance = Target@0x178 (resout au meme summon).
    Port : feuille `SpawnAberrant` (mirror de `SpawnTutelaryHorror` sans le AddEffect)."""
    return SpawnAberrant(tile_id)


class AberrantHypermorphAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour` (id 1166, genesBiophagus -- le summon le plus
    simple). Cast TILE-TARGET (« Summon a genesSmnAberrant on a free hex adjacent to Biophagus ») : spawn UN
    Aberrant Hypermorph sur la tuile ciblee (hex libre adjacent au caster), qui attaque immediatement sans
    bouger (`PerformAIAttackFromCurrentPosition`). Pas de triggered, pas d'effet pose sur le caster.

    La behaviour EST l'arbre DSL `aberrant_hypermorph_tree(tile_id)` (mirror 1:1 du decompile IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$ExecuteBehaviour :
    un noeud `Spawn` UNIQUE portant `WithStatsFromConfig` + on-appearance `PerformAIAttackFromCurrentPosition`
    embarque dans ses options -- cf. la feuille `SpawnAberrant`). La feuille delegue le SPAWN a l'Operation
    VALIDEE `_spawn_config_grot` (genesSmnAberrant team/player du caster, stats summonHp/summonDmg/summonArmor
    [level actif] x mult) puis l'on-appearance (le summon attaque l'ennemi le plus proche a portee melee).

    `target_id` = id de TUILE (cast tile-target, abilityTargets kind="tile" -- meme convention que
    MasterOfTheTutelaries : IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$.ctor = TargetingOptions(0, statsFromClass, 1, 0x1040) IDENTIQUE).
    Un target_id qui n'est pas une tuile du board -> Spawn no-op (diag `spawned=[]`).

    Flags de tour : defauts base (`SetsEndTurnFlags`/`SetsActiveAbilityUsedFlag` = True ; 1166 absent des
    inventaires d'override) -> l'ability termine le tour du caster + pose ActiveAbilityUsed. Le
    « cannot-move-this-turn » que le natif pose SUR LE SUMMON (`IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours :
    flag 0x23 si le summon spawn pendant le tour du joueur courant et n'a ni trait 0x1b ni 0x10) est un
    NO-OP runner : le summon a agi a l'apparition et n'est pas rejoue ce tour dans notre modele (aucune
    boucle qui le referait bouger), donc le flag n'a aucun consommateur offline."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.AberrantHypermorph)  # 1166

    # GATE DE CIBLE + PORTEE -- forme de ctor = **FLAGS DIRECTS**, la 1re des trois.
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility$$.ctor` est
    # BIT-IDENTIQUE a celui de MasterOfTheTutelaries (meme `TargetingRange` statique +0x30, meme
    # litteral, meme `AbilityAttackType`) -- et c'est LU, pas deduit de la voisine :
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, &range, forceMeleeTarget=1, 0x1040, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)   # 3e arg = 2 = AbilityAttackType.Others
    # Decomposition EXHAUSTIVE de 0x1040 (0x40 + 0x1000, aucun bit residuel) :
    #     0x40    (bit 6)  TargetIsTile     -> domaine TUILE ; tuile non marchable => le natif rend le
    #                                         LITTERAL 1 (`ValidRequest`), `AllowUnwalkableTargetTile`
    #                                         (bit 43) n'etant pas pose.
    #     0x1000  (bit 12) TargetTileIsFree -> `!TileExtensions.CanAddUnit(mainTile, state, 1, 0, 0)`
    #                                         => refus : la tuile doit accueillir le genesSmnAberrant.
    # PORTEE : `TargetingRange` statique +0x30 = `RANGE_ADJACENT` -> `AreEntitiesAdjacent(casterTiles,
    # target)` : la tuile doit etre AU CONTACT du Biophagus (« on a free hex adjacent to Biophagus »).
    # `forceMeleeTarget` = 1 = `RangedBool.False`.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetIsTile | TR.TargetTileIsFree,
        self_cast=False, range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
        board = state.board
        tile_id = target_id if (board is not None and target_id in board.by_id) else None
        ectx = ExecutionContext(state=state, rng=state.rng)
        aberrant_hypermorph_tree(tile_id).execute(entities_from_state(state, caster_id), ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        attacks = [{"summon": p["summon"], "target": p["target"], "total": p["total"]}
                   for n, p in ectx.emitted if n == "SummonOnAppearance"]
        return {"summon": "genesSmnAberrant", "spawned": spawned, "attacks": attacks,
                "tile": tile_id, "dsl": True}
