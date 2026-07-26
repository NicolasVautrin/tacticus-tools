"""Abilities Necrons (namespace natif `Abilities.Active.Loki.*`) — case-220 §6.7.

Module DEDIE a la faction Necrons (comme `blacklegion.py`/`genestealer.py`/`deathguard.py` : une classe
par ability, l'arbre SPECIFIQUE vit avec sa classe). RE ghidra gqfc5mff6c (VA citees). Doc :
docs/rl/case-220/necrons.md.

Contenu :
- `HarbingerOfDestruction` (1008, `necroPlasmancer`) — attaque la cible + N-1 ennemis ALEATOIRES dans un
  DISQUE rayon-2 du CASTER (non obscurcis, damageable, hors cible), 1 coup MinMaxDamage profil DirectDamage
  (pierce 100) chacun. Selecteur rayon-2 SurroundingEnemies (template splash `loki/splash.py`, adapte du
  BringerOfDespair caster-ancre `blacklegion.py`).
- `ResurrectionOrb` (1009, `necroOverlord`) — SUMMON pur (aucune resurrection : le nom est du flavor) :
  `Spawn(PickRandomly(CanAddUnit(AdjacentTiles(caster)), N), 'necroSmnWarrior', WithStatsFromConfig)` avec
  N = `Min(Count(amis morts/ressuscites LivingMetal) + TURNS_STARTED(caster), 6)`.
- `Chronometron` (1226, `necroChronomancer`) — `Foreach(SurroundingEnemies(caster, range), (If(HasTrait(It,
  Summon), AddEffect(Stunned), AddEffect(Pinned)) & AddEffect(Chronometron_ExtraDamage)))`.
- `MultiThreatEliminator` (1006, `necroDestroyer`) — `ChainLeftOverHitsAttackDamage` : 6 coups Gauss sur la
  cible, report des coups NON consommes (kills) sur l'ennemi suivant, +1 coup par kill.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import Foreach, If as IfBehaviour, op_and
from ...entities.formulas import Count, Min, StatAmount, Sum
from ...entities.selectors import (Target, Caster, CasterTile, SurroundingEnemies, Unobscured,
                                    Damageable, Sub, Union, UnitSet, ActiveTarget, AdjacentTiles,
                                    AdjacentUnits, AllDeadOrResurrectedUnits, And, CanAddUnit,
                                    Enemies, Friends, SurroundingUnits, UnitsWithTrait)
from ...entities.stats import StatType
from ...entities.traits.unit_trait import UnitTrait
from ...entities.triggers import HasTrait
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from .base import ActiveAbility
from .behaviours import (entities_from_state, AddEffect, AttackWithAttackDamage,
                         ChainLeftOverHitsAttackDamage, Spawn)
from .loki import _pick_randomly_n

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

    ⚠ GAP #215 (RNG-exact PickRandomly) : le natif tire dans l'ORDRE d'enumeration du pool (SurroundingTiles->
    Units, PAS id-trie) et le cout/ordre exact de `PickRandomlySelector.Select` ne sont pas cales ; le port
    id-trie le pool avant `_pick_randomly_n` -> quand `len(pool) > N-1`, l'ENSEMBLE pické ET la conso
    `state.rng` peuvent differer. DETERMINISTE (aucun tirage de pick) quand `len(pool) <= N-1` : le pool tient
    -> toutes les cibles additionnelles == le pool (== le natif : `PickRandomly` ne roll pas si le set tient).
    Valide en `len(pool) <= N-1` ; residuel `len(pool) > N-1` = raffinement flagge (NON root-cause).

    Renvoie {ability, caster, target, main_attack, splash, dsl}. Termine le tour (1008 hors des frozensets
    base.py -> flags par defaut). `native_factory="attack"` (defaut) = 2 tirages/coup a cc=0 -> bit-exact BY
    CONSTRUCTION vs une sequence directe `execute_ability_attack` (memes bornes/hits/profil, cibles id-triees,
    meme `state.rng`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HarbingerOfDestruction)  # 1008
    ABILITY_ID = "HarbingerOfDestruction"

    def _params(self, state: "State", caster_id: int) -> tuple:
        """`(N, range)` lus du gameconfig au niveau du caster (mirror `GetVariableForLevel(config, 0x9a)` =
        `nrOfUnits`[level] et `GetNumberConstant(config, 0x16)` = `range`). N NON scale rarete (`nrOfUnits`
        hors `variablesAffectedByRarityBonus`). Cle config `nrOfUnits ` (espace final = quirk gameconfig)
        avec fallback sans espace. Defauts surs si absent (N>=1, range>=1)."""
        from ..components import StatsComponent
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
        # pool (selecteur DSL PUR) -> id-trie (== l'OrderBy pre-pick du leaf) -> PickRandomly(N-1) folde
        pool = sorted((u for u in harbinger_pool_selector(range_val).evaluate(entities)
                       if isinstance(u, dict) and u.get("id") is not None), key=lambda u: u["id"])
        picked = _pick_randomly_n(state, pool, n_pick)          # GAP #215 si len(pool) > n_pick ; sinon = pool
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
RESURRECTION_ORB_CONST_UNIT_ID = 0x00   # GetStringConstant(0) -> "unitId" = necroSmnWarrior
RESURRECTION_ORB_MAX_SUMMONS = 6        # Direct(6) litteral de GetMaxSummonsFormula (cap, PAS une config)


def resurrection_orb_max_summons_formula():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$GetMaxSummonsFormula` —
    MIRROR 1:1 du decompile (formule V pure, aucun collapse) :

        Min( Sum( Count( Friends(caster@0x160, UnitsWithTrait(AllDeadOrResurrectedUnits, 1000=LivingMetal)) ),
                  StatAmount(caster@0x160, 0xc = TURNS_STARTED) ),
             Direct(6) )

    = « 1 Necron Warrior par ROUND commence (le compteur per-unite `UnitComponent.turnsStarted@+0x58` du
    caster, meme node que `DeathFromAboveAbility.GetNumSummons`) + 1 par allie porteur du trait LivingMetal
    MORT (ou ressuscite) dans cette bataille », cap 6 — i2 mot a mot. L'ordre des operandes du `Sum` est
    celui du natif (`Sum(Count, StatAmount)`).

    ⚠ NOMS D'ENUM QUALIFIES : `1000` est un **UnitTrait** (LivingMetal), `0xc` un **StatType**
    (TURNS_STARTED) et `6` un litteral `Direct` — aucun n'est un EffectType/AbilityType."""
    return Min(Sum(Count(Friends(UnitsWithTrait(AllDeadOrResurrectedUnits(),
                                                int(UnitTrait.LivingMetal)), Caster())),
                   StatAmount(Caster(), int(StatType.TURNS_STARTED))),
               Const(RESURRECTION_ORB_MAX_SUMMONS))


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
    feuille `Spawn`, qui seule voit `ectx.state.rng` -- MEME convention que SupremeCommander)."""
    return Spawn(CanAddUnit(AdjacentTiles(Caster())), "ResurrectionOrb", pick_n=count)


class ResurrectionOrbAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$ExecuteBehaviour` (id 1009,
    `necroOverlord` « Anuphet »).

    **SUMMON PUR — AUCUNE resurrection** : malgre son nom, l'arbre natif ne contient NI `Revive` NI
    `Resurrect` (aucun appel a `IdunBattleLogic.Entities.DSLFactory$$Revive` / `$$Resurrect`, aucun
    `ReviveEffect`) ; le seul rapport aux morts est le COMPTEUR `AllDeadOrResurrectedUnits` de la formule de
    count. La base REVIVE portee (#66/#79, `operations/revive.py`) n'a donc rien a faire ici — verifie au
    decompile AVANT de coder, cf. le point d'attention de la tache #116.

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
CHRONOMETRON_CONST_RANGE = 0x16          # GetNumberConstant(0x16)  -> "range"      = 2
CHRONOMETRON_CONST_NR_OF_ROUNDS = 0x45   # GetNumberConstant(0x45)  -> "nrOfRounds" = 1 (== SquigMine)
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

    RESIDU DOCUMENTE (hors perimetre de CE port, tache separee) : la CONTRIBUTION AU DEGAT de l'effet 1550.
    `IdunBattle.Entities.Effects.Loki.Chronometron_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` =
        EffectBonus( OwnerIsTarget & IsUnit(caster@0x160)
                       & AreFriends(caster@0x160, EffectSource(Effect@0x150)),
                     Multiply( If(IsMechanical(caster@0x160), ConfigVar(9 = extraDmg_2),
                                                              ConfigVar(8 = extraDmg)),
                               TimesEffectApplied(Effect@0x150) ),
                     AbilityOrEffect(0x4ca = 1226) )
    et `$$CreateRemoveEffectTrigger` = `On(9) & OwnerIsTarget & IsUnit(caster) & AreFriends(caster,
    EffectSource)` (l'effet est CONSOMME au 1er coup d'un allie du Chronomancer). Les TROIS entrees dont
    depend la magnitude — equipe de l'ATTAQUANT vs equipe de la SOURCE de l'effet, trait `Mechanical` de
    l'attaquant, compteur `TimesEffectApplied` — sont ABSENTES du contexte que le port passe au hook
    defenseur (`attacker_ctx` = {id, is_normal_attack, faction}). Les cabler est un chantier transverse
    (elargissement d'`attacker_ctx` cote prediction ET runner + compteur d'applications par instance
    d'effet), volontairement NON entrepris ici : l'effet est MATERIALISE (visible `decisionView`) mais
    INERTE — degradation fidele documentee (« present != applique »), pas une invention de magnitude."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Chronometron)   # 1226
    ABILITY_ID = "Chronometron"

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
MTE_CONST_RANGE = 0x16        # GetNumberConstant(0x16) -> "range"    = 2
MTE_CONST_EXTRA_HIT = 0x2b    # GetNumberConstant(0x2b) -> "extraHit" = 1  (== ConfigConst 43, formulas.py)
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
