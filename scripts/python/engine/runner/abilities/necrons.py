"""Abilities Necrons (namespace natif `Abilities.Active.Loki.*`) — case-220 §6.7.

Module DEDIE a la faction Necrons (comme `blacklegion.py`/`genestealer.py`/`deathguard.py` : une classe
par ability, l'arbre SPECIFIQUE vit avec sa classe). RE ghidra gqfc5mff6c (VA citees). Doc :
docs/rl/case-220/necrons.md.

Contenu :
- `HarbingerOfDestruction` (1008, `necroPlasmancer`) — attaque la cible + N-1 ennemis ALEATOIRES dans un
  DISQUE rayon-2 du CASTER (non obscurcis, damageable, hors cible), 1 coup MinMaxDamage profil DirectDamage
  (pierce 100) chacun. Selecteur rayon-2 SurroundingEnemies (template splash `loki/splash.py`, adapte du
  BringerOfDespair caster-ancre `blacklegion.py`).
- `ResurrectionOrb` (1009, `necroOverlord`) — `Spawn(CanAddUnit(AdjacentTiles(casterTile)), N,
  'necroSmnWarrior', WithStatsFromConfig)` avec N = `Min(Count(amis MORTS mecaniques) +
  TURNS_STARTED(caster), maxSummons)`. ⚠ Sur `rnca9r7q6c` l'ability n'est PLUS un summon pur : elle a
  gagne `$$GetPossibleResurrectTargets` / `$$GetResurrectBehaviour` / `$$GetNumSummonsFormula` /
  `$$GetPossibleSpawnOrResurrectTiles` (absents de `gqfc5mff6c`). #289 porte les SELECTEURS et
  FORMULES (partages avec la face DECISION) ; le volet RESURRECTION d'`$$ExecuteBehaviour` reste un
  residu nomme, cf. `resurrection_orb_tree`.
- `Chronometron` (1226, `necroChronomancer`) — `Foreach(SurroundingEnemies(caster, range), (If(HasTrait(It,
  Summon), AddEffect(Stunned), AddEffect(Pinned)) & AddEffect(Chronometron_ExtraDamage)))`.
- `MultiThreatEliminator` (1006, `necroDestroyer`) — `ChainLeftOverHitsAttackDamage` : 6 coups Gauss sur la
  cible, report des coups NON consommes (kills) sur l'ennemi suivant, +1 coup par kill.
- `TunnelingHorror` (1011, `necroSmnDestroyer`) — cast TILE-TARGET : `RemoveUnitFromItsTiles(Caster, true)`
  (le caster QUITTE le plateau sans mourir) & `RemoveAllForcedAttackTargets(Caster)` &
  `AddBondEffect(0x459 -> la tuile visee, bondedEntity = Caster, PERMANENT)`. Vecteur de pose du
  marqueur `TunnelingHorror_PendingSummon` ; #366-r1.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import Foreach, If as IfBehaviour, op_and
from ...entities.formulas import Count, Min, StatAmount, Sum
from ...entities.selectors.accessors import ActiveTarget, CasterTile, FixedTileIds, Target
from ...entities.selectors.tiles import AdjacentTiles, CanAddUnit, Caster
from ...entities.selectors.units import (
    AdjacentUnits, AllDeadOrResurrectedUnits, And, Damageable, Enemies, Friends, Sub,
    SurroundingEnemies, SurroundingUnits, Union, UnitSet, UnitsWithTrait, Unobscured
)
from ...entities.stats import StatType
from ...entities.traits.unit_trait import UnitTrait
from ...entities.triggers import HasTrait
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from .base import ActiveAbility
from .targeting import (RANGE_FROM_CONFIG, RANGE_SELF, RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE,
                        RANGED_BOOL_TRUE, TargetingOptions)
from .targeting_rule import TargetingRule as TR
from .behaviours.combat import AttackWithAttackDamage, ChainLeftOverHitsAttackDamage
from .behaviours.context import entities_from_state
from .behaviours.effects import AddBondEffect, AddEffect
from .behaviours.lifecycle import RemoveAllForcedAttackTargets, RemoveUnitFromItsTiles
from .behaviours.summon import Spawn
from .loki import _pick_randomly_n
from ...entities.ability_constant_type import AbilityConstantType   # #270-r1-r1-r3
from ...entities.formulas import Difference, If as IfAmount
from ...entities.selectors.accessors import Subject
from ...entities.selectors.units import AllDeadUnits, Filter
from ...entities.triggers import AmountIsGreaterThanZero
from ...entities.triggers import TriggerAnd, is_mechanical
from ...entities.triggers import is_mechanical
from ..components import StatsComponent

if TYPE_CHECKING:
    from ..state import State


def harbinger_pool_selector(range_val: int):
    """Pool des cibles ADDITIONNELLES (mirror `HarbingerOfDestructionAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$GetEnemiesInRange`) :

        SurroundingTiles(casterTile@0x168, includeCenter=0, range)   # DISQUE dist<=range du caster, centre exclu
        |> Units(., 1, 3)                                            # unites DEBOUT dessus
        |> Enemies(caster@0x160, ., 3)                              # ennemis du caster
        |> op_Subtraction(., target@arg)                           # MOINS la cible principale
        |> Unobscured(caster@0x160, .)                             # ligne de vue depuis le caster (terrain)
        |> Damageable(.)                                           # vivants ciblables (PV>0)

    Le triplet `Enemies(Units(SurroundingTiles(tile, incl=0, range)))` == `IdunBattleLogic.Entities.DSLFactory$$SurroundingEnemies(tile,
    range)` (DECOMPILE : `SurroundingEnemies` = `Enemies(Units(SurroundingTiles(tile, incl=1,
    range) - Tiles(tile)))`, et `SurroundingTiles(incl=0)` == `SurroundingTiles(incl=1) - Tiles(tile)` par
    definition -> IDENTITE prouvee). D'ou le port `SurroundingEnemies(CasterTile(), Const(range))` (disque
    dist<=range, centre=caster exclu, team!=caster ; memes flags Units 1,3 inertes offline). Puis `Sub(.,
    Target())`, `Unobscured(., Caster())`, `Damageable(.)` — mirror 1:1 de l'ordre natif."""
    return Damageable(
        Unobscured(
            Sub(SurroundingEnemies(CasterTile(), Const(range_val)), Target()),
            Caster()))


def harbinger_of_destruction_tree(additional_units: list,
                                  include_main: bool = True) -> AttackWithAttackDamage:
    """UNE feuille `AttackWithAttackDamage` sur le selecteur COMBINE `op_Addition(Target(), <additional>)`
    (mirror `HarbingerOfDestructionAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$ExecuteBehaviour` : UN SEUL `AttackWithAttackDamage`,
    PAS deux volets separes -- CONTRASTE BringerOfDespair). Le natif construit :

        targets = If( AreEqual(caster@0x160, target@0x178),
                      GetAdditionalTargets,                             # then : caster==target (degenere)
                      op_Addition(target@0x178, GetAdditionalTargets) ) # else : cible + additionnels
        AttackWithAttackDamage(caster@0x160, targets, MinMaxDamage, Direct(GetDamageProfile(0)),
                               Direct(GetNumberConstant(0x2f)=nrOfHits))               # Execute (PAS ExecuteAtomic)

    `additional_units` = les cibles additionnelles DEJA pickees (collapse du `PickRandomly` natif, cf.
    `execute_behaviour`). `include_main` = la branche `If(AreEqual)` : True (else, target != caster =
    reachable) -> `Union(Target(), UnitSet(additional))` ; False (then, target == caster degenere) ->
    `UnitSet(additional)` seul (le natif n'ajoute pas la cible). La feuille `multi=True` resout le selecteur,
    `OrderBy` par id (== l'`OrderBy` de `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`) puis attaque CHAQUE cible 1 coup
    dans l'ordre id -> main et additionnels sont attaques dans UNE passe id-triee UNIQUE (mirror du leaf natif
    unique).

    - **MinMaxDamage(minDmg/maxDmg)** = bornes config brutes (aucun override `GetAttackDamage`), profil
      `GetDamageProfile(config, 0)` = "DirectDamage" (PiercingRatio 100 -> pierce 100), `GetNumberConstant(
      0x2f)` = nrOfHits = 1. `attackRangeType=Ranged` -> `is_melee=False`.
    - **native_factory = "attack"** (defaut, 2 tirages/coup a cc=0) : l'ExecuteBehaviour appelle
      `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (VERIFIE par les CALLEES de IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$ExecuteBehaviour, PAS
      `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` -- cf. rngcrit-1202/tip #2). "DirectDamage" est le NOM DU PROFIL,
      PAS l'effet direct-damage (montant fixe) -> la feuille route par `execute_ability_attack` (crit/block)."""
    add_sel = UnitSet(additional_units)
    target_sel = Union(Target(), add_sel) if include_main else add_sel
    return AttackWithAttackDamage(target_sel, "HarbingerOfDestruction", "DirectDamage",
                                  is_melee=False, multi=True)                # MinMaxDamage/DirectDamage/0x2f=1


class HarbingerOfDestructionAbility(ActiveAbility):
    """`HarbingerOfDestructionAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$ExecuteBehaviour` (id 1008, `necroPlasmancer`, namespace
    natif `Abilities.Active.Loki`).

    Attaque la CIBLE + N-1 ennemis ALEATOIRES dans un DISQUE rayon-2 du CASTER (non obscurcis, damageable,
    hors cible), 1 coup MinMaxDamage profil DirectDamage (pierce 100) chacun, dans UNE passe id-triee unique.
    Mirror 1:1 des 4 fonctions natives (VA gqfc5mff6c) :

      - `IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$ExecuteBehaviour` : UN `AttackWithAttackDamage(caster, If(AreEqual(caster,target),
        additional, Target()+additional), MinMaxDamage, Direct(profile 0), Direct(nrOfHits 0x2f))`.
      - `IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$GetAdditionalTargets` : count = `If(AreEqual(caster,target), Get(N), Get(N-1))` avec
        N = `GetVariableForLevel(config, 0x9a)` = `nrOfUnits`[level] ; range = `GetNumberConstant(0x16)` =
        `range` = 2 ; -> `GetEnemiesInRange(count, range, target, pickRandom=1)`.
      - `IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$GetEnemiesInRange` : `PickRandomly(Damageable(Unobscured(caster, SurroundingEnemies(
        casterTile, range) - target)), count)` (pickRandom=1 -> PickRandomly ; =0 -> First, chemin preview).
      - `IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$GetTargetAmount` : accessoire preview (meme `If(AreEqual, Get(N), Get(N-1))`).

    STRUCTURE = template splash `loki/splash.py`, adaptee de BringerOfDespair (`blacklegion.py`, caster-ancre
    + Sub(Target) + PickRandomly) SAUF que : (1) rayon-2 DISQUE (`SurroundingEnemies`, PAS `AdjacentUnits`
    ring-1) ; (2) filtre `Unobscured` ; (3) N-1 picks (up to 2, `nrOfUnits`-1) et non 1 ; (4) UN SEUL leaf
    combine (main+additionnels attaques ENSEMBLE id-triees), PAS deux volets.

    COLLAPSE du `PickRandomly` (doctrine slice-18/19 + Fragstorm/BringerOfDespair `pick_n`) : le `DslContext`
    des selecteurs ne porte PAS `state.rng` -> on resout le pool (selecteur DSL PUR `harbinger_pool_selector`),
    on id-trie, puis on FOLDE le `PickRandomly(pool, N-1)` via `_pick_randomly_n(state.rng)` (== BringerOfDespair)
    AVANT d'attaquer -> l'ordre de conso `state.rng` (pick D'ABORD, puis 1 coup/cible id-triee = 2 tirages/coup)
    mirror le natif (PickRandomly evalue a la RESOLUTION du selecteur, avant tout coup). Les cibles pickees
    alimentent `harbinger_of_destruction_tree` via `UnitSet` (vehicule de collapse).

    #130 (GAP #215 CLOS sur la CONSO) : `_pick_randomly_n` consomme `min(len(pool), N-1)` tirages -- MEME
    quand le pool tient dans `N-1` (le natif n'a aucun court-circuit ; cf. `_pick_randomly_n`). Le pick
    precede les coups -> sans lui TOUT le flux rng aval etait decale. Le SET, lui, reste le pool entier
    quand `len(pool) <= N-1` (== natif).
    R28-1 (2026-07-27) : l'ORDRE du pool est desormais celui du natif -- `SurroundingEnemies` enumere par
    TUILE dans l'ordre de `TileQuery$$IterateSurroundingTiles` (triple boucle CUBE), et le pick consomme
    cet ordre TEL QUEL (le `sorted(key=id)` pre-tirage qui vivait ici n'avait aucun homologue natif :
    `PickRandomAmountSelector$$Select` ne trie jamais son `candidates`). Observable des que
    `len(pool) > N-1` : l'ENSEMBLE pique change.

    Renvoie {ability, caster, target, main_attack, splash, dsl}. Termine le tour (1008 hors des frozensets
    base.py -> flags par defaut). `native_factory="attack"` (defaut) = 2 tirages/coup a cc=0 -> bit-exact BY
    CONSTRUCTION vs une sequence directe `execute_ability_attack` (memes bornes/hits/profil, cibles id-triees,
    meme `state.rng`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HarbingerOfDestruction)  # 1008
    ABILITY_ID = "HarbingerOfDestruction"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$.ctor`
    # n'appelle AUCUN `TargetingOptions..ctor` : il COPIE les 0x40 octets d'un PRESET STATIQUE de
    # `IdunBattle.Core.Services.TargetingOptions` (statics `+0x3c0`, pose par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor`), puis
    # `AActiveAbility..ctor(this, &opts, 0, 0)`. Le masque effectif est donc le champ `Rules` du preset,
    # a `preset+0x28` = statics `+0x3e8` -> `0x200000000000004` (litteral LU dans le `.cctor`).
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x4                 CasterMatchesDynamicRule  -> volet CASTER (regle-delegue), NON PORTE
    #     0x200000000000000   TargetIsCasterOrEnemy (`TargetingOptions$$get_IsCasterOrEnemyTargeting`
    #                         = `(rules >> 0x39) & 1`) -> PORTE : la cible doit etre le CASTER LUI-MEME
    #                         ou un ennemi attaquable. C'est ce bit qui explique la branche
    #                         `If(AreEqual(caster, target), ...)` de l'ExecuteBehaviour : le natif ACCEPTE
    #                         `target == caster` pour cette ability (d'ou `include_main=False`).
    # PORTEE (#241) : preset `TargetingOptions` statique `+0x3c0` -> `TargetingRange`
    # statique `+0x18` (`useRangeFromConfig` -> `HarbingerOfDestruction.constants.range` = 2)
    # + `forceMeleeTarget = False`.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.CasterMatchesDynamicRule
        | TR.TargetIsCasterOrEnemy
    ), range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_FALSE)

    def _params(self, state: "State", caster_id: int) -> tuple:
        """`(N, range)` lus du gameconfig au niveau du caster (mirror `GetVariableForLevel(config, 0x9a)` =
        `nrOfUnits`[level] et `GetNumberConstant(config, 0x16)` = `range`). N NON scale rarete (`nrOfUnits`
        hors `variablesAffectedByRarityBonus`). Cle config `nrOfUnits ` (espace final = quirk gameconfig)
        avec fallback sans espace. Defauts surs si absent (N>=1, range>=1)."""
        e = state.get_entity(caster_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        level = getattr(sc.ctx, "active_ability_level", 0) if sc is not None else 0
        n = (ability_var(self.ABILITY_ID, "nrOfUnits ", level)
             or ability_var(self.ABILITY_ID, "nrOfUnits", level) or 1)
        rng_range = ability_var(self.ABILITY_ID, "range", is_constant=True) or 1
        return int(n), int(rng_range)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        entities = entities_from_state(state, caster_id, target_id)
        n_total, range_val = self._params(state, caster_id)
        # count = If(AreEqual(caster,target), Get(N), Get(N-1)) : la cible occupe 1 des N slots quand
        # target != caster (cas reachable d'une ability ennemi-ciblee) -> N-1 picks + la cible ; sinon N.
        same = (int(target_id) == int(caster_id))
        n_pick = max(0, n_total if same else n_total - 1)
        # pool (selecteur DSL PUR) dans l'ORDRE SOURCE -> PickRandomly(N-1) folde. R28-1 : le natif
        # `PickRandomAmountSelector$$Select` fait `source.Select(entities).ToList()` et tire par
        # `ElementAt(idx)` SANS aucun tri prealable -- l'id-tri qui etait ici n'avait pas d'homologue
        # natif et decidait QUI etait pique des que |pool| > N-1. L'ordre source vient desormais de
        # `SurroundingEnemies` = enumeration CUBE d'`IterateSurroundingTiles` (cf. `_tile_enum_rank`).
        pool = [u for u in harbinger_pool_selector(range_val).evaluate(entities)
                if isinstance(u, dict) and u.get("id") is not None]
        picked = _pick_randomly_n(state, pool, n_pick)          # ordre source == natif ; conso exacte (#130)
        # additionnels != cible (le pool a deja soustrait Target() ; garde-fou par securite)
        additional = [u for u in picked if u.get("id") != target_id]
        ectx = ExecutionContext(state=state, rng=state.rng)
        # branche If(AreEqual) : include_main=False si target==caster (degenere, non reachable pour une
        # ability ennemi-ciblee), sinon Union(Target(), additionnels).
        harbinger_of_destruction_tree(additional, include_main=not same).execute(entities, ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]  # cibles additionnelles != cible principale
        return {"ability": "HarbingerOfDestruction", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "dsl": True}


# =================== ResurrectionOrb (Anuphet `necroOverlord`, actif 1009) — #116 ===================
#
# Indices de config (`AbilityConfiguration.Get*`) lus au decompile de
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$ExecuteBehaviour` :
RESURRECTION_ORB_CONST_UNIT_ID = 0x00     # GetStringConstant(0)  -> "unitId"     = necroSmnWarrior
RESURRECTION_ORB_CONST_MAX_SUMMONS = AbilityConstantType.maxSummons  # GetNumberConstant(0x3c) -> "maxSummons" (== behaviours.py)
RESURRECTION_ORB_CONFIG_ID = "ResurrectionOrb"


def resurrection_orb_max_summons_const() -> int:
    """`IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(config, 0x3c)` =
    `constants.maxSummons` du gameconfig (= 5). Lu de la CONFIG, jamais recopie : c'est la seule voie
    qui reste juste quand l'equilibrage bouge.

    ⚠ DRIFT DE BUILD, mesure le 2026-07-30 : sur `gqfc5mff6c` le cap etait un `Direct(6)` LITTERAL, et
    le port l'avait fige a 6 (`RESURRECTION_ORB_MAX_SUMMONS = 6`). Sur `rnca9r7q6c`,
    `$$GetMaxSummonsFormula` appelle `GetNumberConstant(this+0x60, 0x3c)` puis `Direct(<valeur lue>)`
    — le cap est passe LITTERAL -> CONFIG, et vaut 5. La constante figee etait donc devenue fausse."""
    import gameconfig as _GC                       # lazy : pas de lecture gameconfig a l'import
    c = (_GC.ability(RESURRECTION_ORB_CONFIG_ID) or {}).get("constants") or {}
    return int(c.get("maxSummons") or 0)


def resurrection_orb_possible_resurrect_targets():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$GetPossibleResurrectTargets`
    — MIRROR 1:1 du decompile `rnca9r7q6c` :

        Filter( Friends(AllDeadUnits, caster@0x48),
                HasTrait(It@0x68, 0x10) & IsMechanical(It@0x68) )

    = les allies MORTS qui sont a la fois **Hero** et **mecaniques**. Le `&` est
    `IdunBattle.DSL.AbilityTrigger$$op_BitwiseAnd` (-> `TriggerAnd`).

    ⚠ NOMS D'ENUM QUALIFIES : `0x10` = 16 = **UnitTrait.Hero** (surtout pas un EffectType ; et
    `UnitTrait.Resilient` vaut 1009, homonyme de l'ability elle-meme -- piege a ecarter).
    ⚠ `IsMechanical` n'est PAS `HasTrait(LivingMetal)` : c'est
    `HasTrait(5) | HasTrait(1000) | HasTrait(1029)` (cf. `UnitExtensions$$IsMechanical`).

    L'ensemble alimente DEUX consommateurs (xrefs relues) : `$$GetResurrectBehaviour` (la resurrection
    proprement dite, cote COMBAT) et `$$GetNumSummonsFormula` (cote DECISION). Un seul artefact natif,
    un seul port."""
    return Filter(Friends(AllDeadUnits(), Caster()),
                  TriggerAnd(HasTrait(Subject(), int(UnitTrait.Hero)), is_mechanical(Subject())))


def resurrection_orb_possible_spawn_or_resurrect_tiles():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$GetPossibleSpawnOrResurrectTiles`
    — MIRROR 1:1 : `CanAddUnit( AdjacentTiles(casterTile@0x58) )` = les hex adjacents a la tuile du
    caster ou une unite peut etre posee.

    L'ancre est `DSLSelectors+0x58` = **CasterTile**, PAS `+0x48` = Caster (deux slots distincts de
    `DSLSelectors$$InitializeShared`, et le natif choisit +0x58 ici). La difference est INERTE cote
    runner (`ctx.caster_pos` None -> position courante) mais DECISIVE cote decision balayee : c'est
    `ctx.caster_pos` = la tuile candidate qui doit ancrer l'anneau, sinon les six voisins evalues sont
    ceux de la position de DEPART pour toutes les tuiles du sweep."""
    return CanAddUnit(AdjacentTiles(CasterTile()))


def resurrection_orb_max_summons_formula():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$GetMaxSummonsFormula` —
    MIRROR 1:1 du decompile `rnca9r7q6c` (formule V pure, aucun collapse) :

        Min( Sum( Count( Filter(Friends(AllDeadUnits, caster@0x48), IsMechanical(It@0x68)) ),
                  StatAmount(caster@0x48, 0xc = TURNS_STARTED) ),
             Direct(GetNumberConstant(0x3c) = maxSummons) )

    = i2 mot a mot : « summons 1 Necron Warrior **for each round that has started** » (le compteur
    per-unite `UnitComponent.turnsStarted@+0x58` du caster) « + 1 more for each friendly unit with the
    trait Living Metal **that was defeated** in this battle ». L'ordre des operandes du `Sum` est celui
    du natif (`Sum(Count, StatAmount)`).

    ⚠ TROIS ecarts par rapport au port ecrit sur `gqfc5mff6c`, tous relus au decompile du build
    COURANT (le natif a change, pas la lecture) :
      1. `AllDeadUnits` (`AllDefeatedUnitsSelector`) et **pas** `AllDeadOrResurrectedUnits` — deux
         factories natives distinctes ; la seconde ajoute les ressuscites (flag 0xe), qui sont VIVANTS.
      2. `Filter(..., IsMechanical)` et **pas** `UnitsWithTrait(LivingMetal)` — `IsMechanical` couvre
         AUSSI `Mechanical`(5) et `Vehicle`(1029) ; un allie mort `Mechanical` non-`LivingMetal`
         comptait a tort pour zero.
      3. cap = `ConfigConst(maxSummons)` = 5 et **pas** `Direct(6)` (cf.
         `resurrection_orb_max_summons_const`).

    ⚠ NOMS D'ENUM QUALIFIES : `0xc` est un **StatType** (TURNS_STARTED), pas un EffectType."""
    return Min(Sum(Count(Filter(Friends(AllDeadUnits(), Caster()), is_mechanical(Subject()))),
                   StatAmount(Caster(), int(StatType.TURNS_STARTED))),
               Const(resurrection_orb_max_summons_const()))


def resurrection_orb_num_summons_formula():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$GetNumSummonsFormula` —
    MIRROR 1:1 du decompile `rnca9r7q6c` :

        tiles = CanAddUnit(AdjacentTiles(casterTile@0x58))
        amount = If( AmountIsGreaterThanZero(GetPossibleResurrectTargets()),
                     Difference(Count(tiles), formulas+0x20 = Direct(1)),      # une tuile RESERVEE
                     Count(tiles) )
        return Min( GetMaxSummonsFormula(), amount )

    = « autant de Warriors que de hex libres adjacents, MOINS un si un heros mecanique allie mort peut
    etre ressuscite (sa tuile est reservee), le tout plafonne par maxSummons ». `formulas+0x20` est la
    constante partagee `Direct(1)` allouee par `DSLFormulas$$.ctor` (`+0x18`=0, `+0x20`=1, `+0x28`=2,
    `+0x30`=100, `+0x38`=-1) -- d'ou le `-1`, lu et non devine.

    ⚠ Cette formule est PUREMENT AI : son unique xref native est
    `IdunBattle.AI.Playbook.Loki.ResurrectionOrbPlaybook$$CalculateCustomUtility`. `ExecuteBehaviour`,
    lui, cape par `GetMaxSummonsFormula` DIRECTEMENT (`First(tiles, GetMaxSummonsFormula(), 0)`) — les
    deux faces n'utilisent donc PAS le meme compte, et c'est le natif qui le veut."""
    tiles = resurrection_orb_possible_spawn_or_resurrect_tiles()
    amount = IfAmount(AmountIsGreaterThanZero(Count(resurrection_orb_possible_resurrect_targets())),
                      Difference(Count(tiles), Const(1)),
                      Count(tiles))
    return Min(resurrection_orb_max_summons_formula(), amount)


def resurrection_orb_tree(count: int) -> Spawn:
    """UNIQUE noeud natif de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$ExecuteBehaviour` :

        Execute( Spawn(caster@0x160,
                       PickRandomly(CanAddUnit(AdjacentTiles(caster@0x160)), <count>, 0, 0x7fffffff, false),
                       unitId = GetStringConstant(0) = 'necroSmnWarrior',
                       SpawnUnitOptions.WithStatsFromConfig(config, entities)),
                 entities )

    `Execute` PLAIN (PAS `ExecuteAtomic`, PAS de `Group`) -> aucun `AtomicGroup` (contraste
    SupremeCommander `ExecuteAtomic(0x48)`). AUCUN sous-behaviour on-appearance dans les options (le natif
    passe `WithStatsFromConfig(config, execCtx, 0, 0)` : pas de `+0x10` AddEffect ni `+0x18` attaque) -> le
    Warrior n'agit PAS a l'apparition.

    Le `count` natif est evalue EAGERLY (la formule `GetMaxSummonsFormula` est `Calculate`e AVANT la
    construction du `PickRandomly`, cf. le decompile : le resultat int est passe au factory) -> le port
    l'evalue de meme dans `execute_behaviour` puis le passe en `pick_n` (FOLD du PickRandomly dans la
    feuille `Spawn`, qui seule voit `ectx.state.rng` -- MEME convention que SupremeCommander).

    ⚠ RESIDU DE BUILD (`rnca9r7q6c`, non porte -- hors perimetre #289, qui ne traite que la face
    DECISION) : `$$ExecuteBehaviour` a ete REECRIT entre `gqfc5mff6c` et le build courant. Il fait
    desormais `SortByFormula(tiles, MinDistance(It, NormalUnits(Enemies(caster))), asc)` puis
    `SortTilesByUtilityForSummon(., 7, caster)` puis `First(., GetMaxSummonsFormula(), 0)` -- un TRI
    deterministe la ou le port a garde le `PickRandomly` de l'ancien build ; et il PRECEDE le spawn
    d'un `GetResurrectBehaviour(...)` (resurrection d'un heros mecanique allie mort, `PickRandomly(1)`,
    PV = `PercentageOf(StatAmount(cible, Health, max), variable 0x26)`), entierement absent du port.
    L'ancre reste `casterTile@0x58` (cf. `resurrection_orb_possible_spawn_or_resurrect_tiles`)."""
    return Spawn(resurrection_orb_possible_spawn_or_resurrect_tiles(), "ResurrectionOrb",
                 pick_n=count)


class ResurrectionOrbAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$ExecuteBehaviour` (id 1009,
    `necroOverlord` « Anuphet »).

    ⚠ **VERDICT « SUMMON PUR » PERIME — relu le 2026-07-30 sur `rnca9r7q6c` (#289).** Il etait juste
    sur `gqfc5mff6c` : l'arbre n'y contenait NI `Revive` NI `Resurrect`. Le build COURANT a ajoute
    `$$GetResurrectBehaviour`, qui appelle bien `IdunBattleLogic.Entities.DSLBehaviors$$Resurrect` —
    `ExecuteBehaviour` y fait `op_Addition(GetResurrectBehaviour(...), Spawn(...))`. Le volet
    resurrection n'est PAS porte (residu nomme sur `resurrection_orb_tree`) ; ce qui EST porte ici,
    ce sont les selecteurs/formules que la face DECISION partage avec lui.

    Corps natif (ordre de lecture) :
        unitId  = GetStringConstant(config, 0)                       # necroSmnWarrior
        formula = GetMaxSummonsFormula(this)                         # cf. resurrection_orb_max_summons_formula
        tiles   = CanAddUnit(AdjacentTiles(caster@0x160))
        count   = formula.Calculate(entities)                        # EAGER (int), pas un noeud
        picked  = PickRandomly(tiles, count, 0, 0x7fffffff, false)
        opts    = SpawnUnitOptions.WithStatsFromConfig(config, entities)
        AActiveAbility.Execute(this, Spawn(caster@0x160, picked, unitId, opts), entities)

    Stats du summon = `WithStatsFromConfig` -> `summonHp`/`summonDmg`/`summonArmor`[level] x multiplier de
    rarete (les 3 sont dans `variablesAffectedByRarityBonus`) — c'est exactement ce que
    `Spawn`/`_spawn_config_grot` lit via `build_summon_context(summon_ability='ResurrectionOrb')`.

    Renvoie {ability, caster, count, spawned, dsl}. Termine le tour (1009 hors des frozensets de base.py)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ResurrectionOrb)   # 1009
    ABILITY_ID = "ResurrectionOrb"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, 1, &statsFromClass, 1, 0x8000000020, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)
    # Overload « flags DIRECTS » (`IdunBattle.Core.Services.TargetingOptions$$.ctor` 7 params : le 5e
    # argument atterrit tel quel a `options+0x28` = Rules) -> le litteral EST le masque effectif ; ce
    # n'est PAS l'overload preset+flags (qui, lui, a 3 params et fait `param_3 | preset.Rules`).
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x20          TargetHasFreeAdjacentTile  -> il faut un hex libre adjacent (ou spawner), NON PORTE
    #     0x8000000000  TargetIsCaster « la cible DOIT etre le caster » -> PORTE : ResurrectionOrb est un
    #                   SELF-CAST STRICT (le natif refuse tout target != caster).
    # `self_cast` = le BYTE `options+0x00`, ici le 2e argument du ctor (= 1) : il aiguille le cast
    # SUR SOI-MEME vers `TargetingQuery$$GetCasterNotAddedReason` au lieu du filtre statique.
    # PORTEE (#241) : `range = TargetingRange` statique `+0x60` = `overrideRange = 0`,
    # `forceMeleeTarget = False` -- portee NULLE, coherent avec un cast SELF.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetHasFreeAdjacentTile
        | TR.TargetIsCaster
    ), self_cast=True, range=RANGE_SELF, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        entities = entities_from_state(state, caster_id, target_id)
        # `GetMaxSummonsFormula(...).Calculate(entities)` — EAGER cote natif (le int alimente PickRandomly).
        count = int(resurrection_orb_max_summons_formula().evaluate(entities) or 0)
        ectx = ExecutionContext(state=state, rng=state.rng)
        resurrection_orb_tree(count).execute(entities, ectx)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        return {"ability": "ResurrectionOrb", "caster": caster_id, "target": target_id,
                "count": count, "spawned": spawned, "dsl": True}


# =================== Chronometron (Thothmek `necroChronomancer`, actif 1226) — #116 ===================
#
# Indices de config lus au decompile de
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ChronometronAbility$$ExecuteBehaviour` :
CHRONOMETRON_CONST_RANGE = AbilityConstantType.range          # GetNumberConstant(0x16)  -> "range"      = 2
CHRONOMETRON_CONST_NR_OF_ROUNDS = AbilityConstantType.nrOfRounds   # GetNumberConstant(0x45)  -> "nrOfRounds" = 1 (== SquigMine)
CHRONOMETRON_TRAIT_SUMMON = int(UnitTrait.Summon)   # 2 — `HasTrait(It@0x180, 2)` du If natif


def chronometron_affected_enemies(range_val: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ChronometronAbility$$GetAffectedEnemies` — MIRROR :

        SurroundingEnemies(caster@0x160, GetNumberConstant(0x16)=range, 1, 3)

    surcharge 5-args de `IdunBattleLogic.Entities.DSLFactory$$SurroundingEnemies` : le MEME noeud sert de
    CENTRE **et** de reference d'equipe (`Enemies(param_2, Units(SurroundingTiles(param_2, incl=1, range) -
    Tiles(param_2)))`) -> ennemis DU CASTER dans le DISQUE rayon `range` autour de SA tuile, caster exclu.
    Le port l'exprime avec le centre `CasterTile()` (le noeud porte prend une POSITION en centre) et la
    reference d'equipe implicite = le caster — identique par construction (`Caster` et `CasterTile`
    designent la meme tuile), meme forme que `harbinger_pool_selector`."""
    return SurroundingEnemies(CasterTile(), Const(range_val))


def chronometron_tree(range_val: int, rounds: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ChronometronAbility$$ExecuteBehaviour` — MIRROR 1:1 :

        Execute( Foreach( GetAffectedEnemies,
                          op_BitwiseAnd( GetApplyStunOrPinToActiveTarget,
                                         GetAddExtraDamageEffectToActiveTarget ) ),
                 entities )

    avec (les DEUX sous-arbres sont des methodes natives NOMMEES, re-inlinees dans ExecuteBehaviour) :

      `$$GetApplyStunOrPinToActiveTarget` =
          If( HasTrait(It@0x180, 2 = UnitTrait.Summon),
              AddEffect(0x48a = EffectType.Stunned, stateRef, caster@0x160, It@0x180, TurnsFromRounds(nrOfRounds)),
              AddEffect(0x429 = EffectType.Pinned,  stateRef, caster@0x160, It@0x180, TurnsFromRounds(nrOfRounds)) )

      `$$GetAddExtraDamageEffectToActiveTarget` =
          AddEffect(0x60e = EffectType.Chronometron_ExtraDamage, stateRef, Owner@0x148, It@0x180, <duree ZERO>)

    Points LUS (jamais devines) :
      * `It@0x180` = le slot **ActiveTarget** : le `ForeachBehaviour` a corps STATIQUE ecrit
        `entities[slot 4] = element` avant d'executer (cf. `Foreach` cote port, qui lie desormais
        `active_target`). D'ou `ActiveTarget()` — PAS `Target()` (l'ability est SELF-castee : le `target`
        du message n'intervient nulle part dans l'arbre).
      * la SOURCE des 2 premiers AddEffect est `caster@0x160`, celle du 3e est `Owner@0x148` — dans un cast
        d'active Owner == Caster (le port pose la source = caster dans les deux cas, comportement par defaut
        d'`AddEffect`).
      * la duree du 3e AddEffect est la struct ZERO-INITIALISEE (`local_198..uStack_180 = 0`), PAS un
        `TurnsFromRounds` -> `duration_rounds=None` = duree DEFAUT de l'effet (`DefaultAmountOfRounds`),
        exactement la convention deja en place pour le `Pinned` de CrushingClaws.
      * ENUMS QUALIFIES : `0x48a`/`0x429`/`0x60e` sont des **EffectType** (Stunned / Pinned /
        Chronometron_ExtraDamage) et `2` un **UnitTrait** (Summon).

    L'ordre du `op_BitwiseAnd` est stun-ou-pin D'ABORD, extra-damage ENSUITE (mirror `op_and`)."""
    stun_or_pin = IfBehaviour(
        HasTrait(ActiveTarget(), CHRONOMETRON_TRAIT_SUMMON),
        AddEffect(int(EffectType.Stunned), "Stunned", ActiveTarget(), duration_rounds=rounds),
        AddEffect(int(EffectType.Pinned), "Pinned", ActiveTarget(), duration_rounds=rounds))
    extra_damage = AddEffect(int(EffectType.Chronometron_ExtraDamage), "Chronometron_ExtraDamage",
                             ActiveTarget(), duration_rounds=None, scale_from_source=True)
    return Foreach(chronometron_affected_enemies(range_val), op_and(stun_or_pin, extra_damage))


class ChronometronAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ChronometronAbility$$ExecuteBehaviour` (id 1226,
    `necroChronomancer` « Thothmek »).

    Pose sur CHAQUE ennemi du disque rayon `range`(=2) autour du caster : `Stunned` (1162) si l'ennemi a le
    trait `Summon`, sinon `Pinned` (1065), pour `TurnsFromRounds(nrOfRounds=1)` ; ET l'effet
    `Chronometron_ExtraDamage` (1550) a duree DEFAUT. Aucune attaque, aucun degat, aucun spawn — c'est un
    pur poseur d'effets (patron « MoW effect-poser » de case-90, ici sur une ACTIVE de hero).

    Structure = `Foreach(selecteur, If(...) & AddEffect(...))` (cf. `chronometron_tree`).

    GROUND TRUTH LIVE deja au dossier (case-92 §4, session 78, porteur INJECTE par `catalog_inject.py` car
    `necroChronomancer` est hors du seed BC capture) : « necroChronomancer 1226 Chronometron -> effets 1065
    Pinned + 1550 Chronometron_ExtraDamage ».

    CONTRIBUTION AU DEGAT de l'effet 1550 : PORTEE (residu transverse R9 ferme).
    `IdunBattle.Entities.Effects.Loki.Chronometron_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` =
        EffectBonus.ForAddition( OwnerIsTarget & IsUnit(caster@0x160)
                                   & AreFriends(caster@0x160, EffectSource(Effect@0x150)),
                                 Multiply( If(IsMechanical(caster@0x160), ConfigVar(9 = extraDmg_2),
                                                                          ConfigVar(8 = extraDmg)),
                                           TimesEffectApplied(Effect@0x150) ),
                                 AbilityOrEffect(0x4ca = 1226) )
    et `$$CreateRemoveEffectTrigger` = `On(9) & OwnerIsTarget & IsUnit(caster) & AreFriends(caster,
    EffectSource)` (l'effet est CONSOMME au 1er coup d'un allie du Chronomancer). Les TROIS entrees dont
    depend la magnitude sont desormais dans l'`attacker_ctx` PARTAGE des deux faces (combat
    `damage_model.defender_modifiers` + prediction `playbook/prediction/_shared.py`) : `team` +
    `team_by_id` (`AreFriends(caster, EffectSource)`), `traits` (`IsMechanical(caster)`), et le compteur
    `EffectComponent.TimesApplied @+0x6c` porte par l'instance (`BaseEffect.times_applied`).
    Classe d'effet : `entities/effects/loki/damage_reduction.py::ChronometronExtraDamageEffect` (canal
    `create_effect_damage_malus_for_defense`, mold `OwnerIsTarget` d'ExemplarOfHate) ; trigger de
    retrait : `runner/operations/triggers/loki/chronometron.py` (`EFFECT_TRIGGERS[1550]`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Chronometron)   # 1226
    ABILITY_ID = "Chronometron"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.ChronometronAbility$$.ctor`
    # n'appelle pas `TargetingOptions..ctor` : IL2CPP a INLINE la construction et ecrit les champs
    # directement sur la pile avant `AActiveAbility..ctor(this, &opts, 2, 0)`. Le champ Rules
    # (`options+0x28`, ecrit en deux dwords `0x6004000` / `0`) donne le masque effectif.
    # Le BYTE `options+0x00` vaut **1** (`local_48 = 1` avant l'appel a `AActiveAbility..ctor`) ->
    # `self_cast=True`. Combinaison LUE TELLE QUELLE dans la factory native
    # `IdunBattle.Core.Services.TargetingOptions$$SelfCastIfEnemyInCustomRangeOptions`, qui pose
    # exactement `byte0 = 1` + `Rules = TargetIsEnemy` + un `Range` : l'ability est **SELF-CASTEE**,
    # et `TargetIsEnemy`/`Range` servent au PREDICAT « existe-t-il au moins un ennemi a portee ? »
    # (evalue par `GetCasterNotAddedReason` -> `GetValidTargets`, qui rend `0x800`
    # `AddCasterIfAtLeastOneTarget` si l'ensemble est vide -- MESURE live).
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x4000      TargetIsEnemy        -> PORTE, mais SEULEMENT sur le chemin « cible = un TIERS »
    #                                         (un allie est refuse) ; le self-cast ne passe PAS par la.
    #     0x6000000   AllowObscuredTarget  -> permissif (aucune contrainte de ligne de vue)
    # => l'ability accepte DEUX formes de cast : sur SOI (self-cast, forme naturelle -- l'arbre est
    # caster-ancre `Foreach(SurroundingEnemies(caster, range))`), ou sur un ENNEMI a portee.
    # PORTEE (#241) : le ctor construit les `TargetingOptions` INLINE (aucun appel a
    # `TargetingOptions..ctor`) mais recopie le `TargetingRange` statique `+0x18`
    # (`useRangeFromConfig` -> `Chronometron.constants.range` = 2) ; `forceMeleeTarget =
    # False`, `isSelfCasting = 1`.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetIsEnemy
        | TR.AllowObscuredTargetByElevation
        | TR.AllowObscuredTargetByWalls
    ), self_cast=True, range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_FALSE)

    def _params(self) -> tuple:
        """`(range, nrOfRounds)` = `GetNumberConstant(config, 0x16 / 0x45)` — DEUX constantes de config
        (jamais des scalaires figes). Defauts surs si absentes (range>=1, rounds>=1)."""
        rng_range = ability_var(self.ABILITY_ID, "range", is_constant=True) or 1
        rounds = ability_var(self.ABILITY_ID, "nrOfRounds", is_constant=True) or 1
        return int(rng_range), int(rounds)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        entities = entities_from_state(state, caster_id, target_id)
        range_val, rounds = self._params()
        ectx = ExecutionContext(state=state, rng=state.rng)
        chronometron_tree(range_val, rounds).execute(entities, ectx)
        posed = [{"target": p["target"], "effect_type": p["effect_type"], "placed": p["placed"]}
                 for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": "Chronometron", "caster": caster_id, "target": target_id,
                "range": range_val, "rounds": rounds, "effects": posed, "dsl": True}


# ============ MultiThreatEliminator (Imospekh `necroDestroyer`, actif 1006) — #116 ============
#
MTE_CONST_RANGE = AbilityConstantType.range        # GetNumberConstant(0x16) -> "range"    = 2
MTE_CONST_EXTRA_HIT = AbilityConstantType.extraHit    # GetNumberConstant(0x2b) -> "extraHit" = 1  (== ConfigConst 43, formulas.py)
# `nrOfHits` N'EST PAS dans la config de 1006 : le nombre de coups est un CHAMP STATIQUE de la classe
# native, pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$.cctor`
# (`**(class+0xb8) = 6`) et lu par `$$ExecuteBehaviour` (`Direct(<static>)`). Deja etabli cote DECISION
# (case-166-168 : `MultiThreatEliminatorAbility.get_special_hits -> 6`). C'est une constante NATIVE, pas
# un scalaire invente ni une valeur de gameconfig.
MTE_NR_OF_HITS = 6


def multi_threat_next_target_selector(range_val: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$GetNextHitTargetSelector`
    — MIRROR 1:1 :

        op_BitwiseAnd(
            Unobscured( caster@0x160,
                        Enemies(caster@0x160,
                                SurroundingUnits(casterTile@0x168, range, 1, includeCenter=false, 3)) ),
            AdjacentUnits( Last(It@0x180, 1), 1, 3 ) )

    = « ennemi du caster, dans le DISQUE `range` autour de la tuile du caster (caster exclu), non obscurci
    depuis le caster, ET adjacent (hex 1) a la DERNIERE cible frappee ». `Last(It@0x180, 1)` sur un
    selecteur MONO-ENTITE (`ActiveTarget`, que la boucle vient de lier) rend cette entite -> porte comme
    `ActiveTarget()` (le noeud `Last` n'a pas d'autre effet sur un singleton).

    ⚠ GAP d'ORDRE (documente, non root-cause) : le natif prend `SelectSingle` = le PREMIER element dans
    SON ordre d'enumeration (tuiles via `UnitsOnTilesSelector`) ; le port prend le premier dans l'ordre de
    `ctx.units` (ordre d'entite ECS). Quand PLUSIEURS candidats satisfont l'intersection, la cible suivante
    peut differer. Deterministe et identique des que l'intersection a <= 1 element."""
    return And(Unobscured(Enemies(SurroundingUnits(CasterTile(), Const(range_val))), Caster()),
               AdjacentUnits(ActiveTarget(), Const(1)))


def multi_threat_eliminator_tree(range_val: int, extra_hit: int) -> ChainLeftOverHitsAttackDamage:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$ExecuteBehaviour` —
    MIRROR 1:1 (UN SEUL noeud, `ExecuteAtomic(this, tree, entities, 0x41)`) :

        ChainLeftOverHitsAttackDamage(
            caster@0x160, target@0x178,
            MinMaxDamage(minDmg/maxDmg[level]),                   # +0x68
            Direct(Nullable(GetDamageProfile(this)))              # +0xa0  -> config "damageProfile"=Gauss
            Direct(<champ statique de la classe> = 6),            # +0x98  hits
            AbilityOrEffect(this+0x10),                           # +0x70  source du coup
            GetNextHitTargetSelector(this),                       # +0x88
            Get(GetNumberConstant(0x2b) = extraHit))              # +0x90  extraHits

    `attackRangeType = Ranged` (gameconfig) -> `is_melee=False`. Famille de factory = **ATTACK** (le nom
    natif est `...AttackDamage`, et le behaviour construit par iteration porte le meme mold de champs que
    `AttackDamageBehaviour`) -> `native_factory="attack"` (2 tirages/coup a cc=0)."""
    return ChainLeftOverHitsAttackDamage(
        Caster(), Target(), multi_threat_next_target_selector(range_val),
        "MultiThreatEliminator", "Gauss", MTE_NR_OF_HITS, extra_hit, is_melee=False)


class MultiThreatEliminatorAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$ExecuteBehaviour`
    (id 1006, `necroDestroyer` « Imospekh »).

    6 coups Gauss (`minDmg`/`maxDmg`[level]) sur la cible ; les coups qui tombent sur le CADAVRE sont
    REPORTES (+1 par ennemi tue) sur l'ennemi suivant — adjacent a la derniere cible ET dans le disque
    rayon `range`(=2) du caster, non obscurci — et ainsi de suite. i2 mot a mot : « Deals 6x ... Molecular
    Damage to an enemy within range 2. Any leftover hits are allocated to another enemy adjacent to the
    target and in range 2. Each enemy killed adds +1 hit and the ability keeps targeting new enemies until
    there are no more enemies or hits left. »

    Le report vit dans la feuille `ChainLeftOverHitsAttackDamage` (`behaviours/combat.py`) — mirror du
    `ChainLeftOverHitsAttackDamageBehaviour` natif, y compris son `GetLeftOverHits` (coups gaspilles sur le
    cadavre + `extraHit` si la cible est morte) et sa garde de 100 iterations. Ici, seule la CONSTRUCTION
    de l'arbre (`multi_threat_eliminator_tree`).

    Renvoie {ability, caster, target, chain, dsl}. Termine le tour (1006 hors des frozensets base.py)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.MultiThreatEliminator)   # 1006
    ABILITY_ID = "MultiThreatEliminator"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$.ctor`
    # COPIE le PRESET STATIQUE `IdunBattle.Core.Services.TargetingOptions` statics `+0x140` (pose par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor`), puis `AActiveAbility..ctor(this, &opts, 0, 0)`.
    # Masque effectif = `preset+0x28` = statics `+0x168` -> `0x4002`. Le MEME preset alimente
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.GravitonRifleAbility$$.ctor` (cf. votann.py).
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x2      TargetMatchesDynamicRule -> consulte `GetDynamicInvalidTargetReason` (non surcharge
    #              ici -> defaut 0 = pas de refus dynamique, degradation PERMISSIVE assumee)
    #     0x4000   TargetIsEnemy            -> PORTE (refus sur soi-meme / un allie)
    # PORTEE (#241) : preset `TargetingOptions` statique `+0x140` -> `TargetingRange`
    # statique `+0x18` (`useRangeFromConfig` -> `MultiThreatEliminator.constants.range` = 2)
    # + `forceMeleeTarget = True`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_TRUE)

    def _params(self) -> tuple:
        """`(range, extraHit)` = `GetNumberConstant(config, 0x16 / 0x2b)`."""
        rng_range = ability_var(self.ABILITY_ID, "range", is_constant=True) or 1
        extra_hit = ability_var(self.ABILITY_ID, "extraHit", is_constant=True) or 0
        return int(rng_range), int(extra_hit)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        entities = entities_from_state(state, caster_id, target_id)
        range_val, extra_hit = self._params()
        ectx = ExecutionContext(state=state, rng=state.rng)
        multi_threat_eliminator_tree(range_val, extra_hit).execute(entities, ectx)
        chain = next((p["chain"] for n, p in ectx.emitted if n == "ChainLeftOverHits"), [])
        return {"ability": "MultiThreatEliminator", "caster": caster_id, "target": target_id,
                "range": range_val, "extra_hit": extra_hit, "chain": chain, "dsl": True}


# ================== TunnelingHorror (necroSmnDestroyer, actif 1011) -- #366-r1 ====================
#
# Le VECTEUR DE POSE du marqueur `TunnelingHorror_PendingSummon` (EffectType 0x459 = 1113). Le porteur
# `necroSmnDestroyer` (« Ophydian Destroyer ») est un SUMMON **sans invocateur d'unite** : la seule
# reference du gameconfig hors de sa propre entree est `abilities["EnvFactionSummons:Necrons"]
# .constants.unitId`, une ability d'ENVIRONNEMENT que AUCUNE unite ne porte. La voie confrontee est
# donc la GREFFE de 1011 sur un heros DU POOL (recours 3 de `docs/rl/case-92-catalog-injection.md`
# §5bis) -- legitime : `gameconfig.ability("TunnelingHorror")` n'a AUCUNE variable ni constante, et
# le behaviour ne lit ni stat, ni trait, ni arme du caster.
#
# i2 : « This unit may use tunnelling to move. It is then removed from the battlefield and emerges in
# its chosen hex at the start of its next turn, pushing any unit in that hex aside. »
#
# RE complete + les cinq mesures live : `docs/rl/case-366-r1-tunneling-horror-pending-summon.md`.

TUNNELING_HORROR_ID = "TunnelingHorror"
TUNNELING_HORROR_PENDING = int(EffectType.TunnelingHorror_PendingSummon)   # 0x459 = 1113


def tunneling_horror_remove_tree() -> RemoveUnitFromItsTiles:
    """1er des TROIS `AActiveAbility$$Execute` de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.TunnelingHorrorAbility$$ExecuteBehaviour` :

        RemoveUnitFromItsTiles( <selecteur pre-construit du contexte DSL>, removeTileFromUnit: true )

    Le selecteur est un champ PRE-CONSTRUIT du contexte (`<ctx>+0x90` -> `+0x30`), pas une chaine
    lisible dans ce corps ; la MESURE live le tranche sans ambiguite -- l'event est
    `RemoveUnitFromTiles e=<caster> Clear_Unit_Tiles=1`, et le caster passe a `pos = null`,
    `alive = true`. D'ou `Caster()`."""
    return RemoveUnitFromItsTiles(Caster(), remove_tile_from_unit=True)


def tunneling_horror_forced_targets_tree() -> RemoveAllForcedAttackTargets:
    """2e `Execute` : `RemoveAllForcedAttackTargets(<meme selecteur +0x30>)` = le caster. N'a emis
    AUCUN event dans les cinq mesures (la liste de cibles forcees du caster etait VIDE) : porte pour
    la STRUCTURE de l'arbre ; observable seulement si le caster est sous Taunt /
    `InstinctiveBehaviour` au moment du cast."""
    return RemoveAllForcedAttackTargets(Caster())


def tunneling_horror_bond_tree(target_tile_id: int) -> AddBondEffect:
    """3e `Execute`, lu sur la surcharge `options` d'`IdunBattleLogic.Entities.DSLBehaviors$$
    AddBondEffect` (`effectType, abilityState, source, targets, bondedEntity, options`) :

        AddBondEffect( 0x459, AbilityStateReference,
                       source: <ctx+0x90 +0x48>, targets: <ctx+0x90 +0x78>,
                       bondedEntity: <ctx+0x90 +0x48>, options: <struct ZERO> )

    `source` et `bondedEntity` sont LE MEME champ -- la mesure live les donne tous deux egaux au
    caster (`Effect_SourceId = BondEffect_BondedId = <caster>`), et `targets` = la TUILE ciblee (le
    cast est TILE-TARGET).

    ⚠ La struct d'options est ZERO-initialisee : **aucun `TurnsFromRounds`**, donc pas d'override de
    duree -> `DefaultAmountOfRounds` -> `remaining = 0` = PERMANENT (mesure : l'effet survit a un
    tour complet, et n'est retire que par le cast de 1060). `docs/rl/summon-abilities-port-spec.md`
    annoncait « default -> 1 round » : REFUTE. D'ou `duration_rounds=None`.

    LIMITE DE CANAL cote CHARGEMENT (pas cote pose) : une instance SEEDEE depuis `tileMeta` a
    `bonded = None` (le canal ne publie pas le `BondEffect_BondedId`). La POSE offline, elle, le
    renseigne -- c'est precisement ce que ce vecteur ajoute."""
    return AddBondEffect(TUNNELING_HORROR_PENDING,
                         EffectType.TunnelingHorror_PendingSummon.name,
                         Caster(), FixedTileIds([int(target_tile_id)]),
                         duration_rounds=None, bonded_ref=Caster())


class TunnelingHorrorAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.TunnelingHorrorAbility$$ExecuteBehaviour`
    (id 1011, `necroSmnDestroyer`, namespace natif `Abilities.Active.Loki`). Cast TILE-TARGET.

    TROIS `AActiveAbility$$Execute` SUCCESSIFS (pas un `op_Addition` : le decompile re-copie les
    0x148 octets du contexte `entities` AVANT chacun -- meme forme que `WaaaghAbility`), dans cet
    ordre LOAD-BEARING : le caster quitte le plateau AVANT que le bond ne soit pose, donc au moment
    du bond `source`/`bondedEntity` designent une unite SANS position. Le port re-materialise
    `entities_from_state` avant chaque etage, comme le natif re-copie son contexte.

      1. `RemoveUnitFromItsTiles(Caster, removeTileFromUnit: true)`
      2. `RemoveAllForcedAttackTargets(Caster)`
      3. `AddBondEffect(0x459, ..., source: Caster, targets: TargetTiles, bondedEntity: Caster,
                        <options SANS TurnsFromRounds>)`

    OBSERVABLE DU CAST (mesure live #366-r1, greffe sur `necroDestroyer`, board MC1_67, seed 777) :

        [User_UseAbility e=<caster> «TunnelingHorror»]
          [Ability_Power e=<caster> «TunnelingHorror»]
            RemoveUnitFromTiles e=<caster>  Clear_Unit_Tiles=1
            [Effect_Refresh e=<effet> «TunnelingHorror_PendingSummon»]
              ReceiveEffect e=<tuile>  BondEffect_BondedId=<caster> Effect_SourceId=<caster>
                                       Effect_SourceActiveAbility=1011
          ChangeStats e=<caster>  UnitStats_TurnFinished=1

    et `tileMeta` ne marque QUE la tuile ciblee. Le caster passe a `pos = null` / `alive = true` :
    il est HORS PLATEAU, **pas mort**. (⚠ `rl_duel` l'affiche « TUE » -- son heuristique lit
    `hp = null` comme 0 ; faux positif d'AFFICHAGE, cf. la fiche.)

    L'ability 1060 `TunnelingHorror_Appear` (le retour sur la tuile marquee) est un arbre nettement
    plus gros, SANS aucune config au gameconfig : hors perimetre, residu nomme dans la fiche.

    Renvoie {ability, caster, tile, removed_from_tiles, posed, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.TunnelingHorror)         # 1011
    ABILITY_ID = TUNNELING_HORROR_ID

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.TunnelingHorrorAbility$$.ctor` :
    #     range = <TargetingRange statics+0x48> = `useWholeBoard = true`   (copie de 0x18 octets)
    #     TargetingOptions..ctor(&opts, isSelfCasting=0, &range, forceMeleeTarget=1,
    #                            rules=0x8000000001042, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2)                              # AbilityAttackType.Others
    # FORME DIRECTE a 6 arguments -> le litteral EST le masque effectif (aucun preset).
    #   0x8000000001042 = TargetMatchesDynamicRule (1<<1)  | TargetIsTile         (1<<6)
    #                   | TargetTileIsFree         (1<<12) | TargetIsNotSteppable (1<<51)
    #                                                              -> somme EXACTE, 0 bit residuel
    #   forceMeleeTarget = 1 = RangedBool.False
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.TargetIsTile
        | TR.TargetTileIsFree
        | TR.TargetIsNotSteppable
    ), range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`...TunnelingHorrorAbility$$GetDynamicInvalidTargetReason` -- MIRROR du decompile, qui
        porte **DEUX** refus (et non un seul) :

            if ( HasEffect(Get(target), 0x459, onlyActive: false, targetType: 6) )
                return 2;                                   // (a) tuile DEJA marquee
            foreach (t in casterTiles)
                if (IdunBattle.Entities.TileExtensions$$IsTemporary(t)) return 2;   // (b)
            return 0;

        (a) est PORTE : c'est le refus DISCRIMINANT mesure live (E3 -- sur 58 cibles legales du
        second porteur, la tuile marquee est la seule exclue, le temoin adjacent reste legal).

        (b) est un RESIDU NOMME : `IsTemporary` lit le champ booleen `@+0x2c` du `TileComponent`, que
        le port ne materialise PAS cote RUNNER (`state.board` ne porte que la geometrie et
        `walkable` ; le canal `tileMeta.isTemporary` n'est seede que du cote DECISION, cf.
        `engine/ai/context.py::is_temporary_by_pos`). Degradation PERMISSIVE, jamais un refus
        invente. Pour le fermer il faudrait seeder `isTemporary` dans le board du runner.

        Le port cherche l'effet 1113 sur l'ENTITE-TUILE (`state.effects.by_unit[tile_id]`), la meme
        cle que `snapshot._load_tile_effects` et `AddEffectOperation` -- il n'y a qu'un modele
        d'effet de tuile, alimente par la pose et par le chargement."""
        if target_id is None or state is None or state.effects is None:
            return 0
        for eff in state.effects.by_unit.get(int(target_id), []):
            if int(getattr(eff, "effect_type", -1)) == TUNNELING_HORROR_PENDING and not eff.consumed:
                return int(TR.TargetMatchesDynamicRule)
        return 0

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        board = state.board
        tile_id = target_id if (board is not None and target_id in board.by_id) else None
        if tile_id is None:
            # Cast TILE-TARGET : sans tuile resolue il n'y a AUCUN `targets` pour l'`AddBondEffect`.
            # On ne joue alors NI le retrait de tuiles NI le bond (le natif, lui, n'arrive pas la :
            # `TargetIsTile` est dans son masque, donc le gate statique a deja refuse).
            return {"ability": TUNNELING_HORROR_ID, "caster": caster_id, "tile": None,
                    "removed_from_tiles": None, "posed": [], "dsl": True}
        ectx = ExecutionContext(state=state, rng=state.rng)
        # 1) Execute(RemoveUnitFromItsTiles(Caster, true))
        tunneling_horror_remove_tree().execute(entities_from_state(state, caster_id), ectx)
        # 2) Execute(RemoveAllForcedAttackTargets(Caster))
        tunneling_horror_forced_targets_tree().execute(entities_from_state(state, caster_id), ectx)
        # 3) Execute(AddBondEffect(...)) -- `entities` RE-MATERIALISE : le caster n'a plus de tuile.
        tunneling_horror_bond_tree(tile_id).execute(entities_from_state(state, caster_id), ectx)
        removed = next((p for n, p in ectx.emitted if n == "RemoveUnitFromItsTiles"), None)
        posed = [{"target": p["target"], "effect": p["effect_type"], "bonded": p.get("bonded")}
                 for n, p in ectx.emitted if n == "AddBondEffect"]
        return {"ability": TUNNELING_HORROR_ID, "caster": caster_id, "tile": tile_id,
                "removed_from_tiles": removed, "posed": posed, "dsl": True}

