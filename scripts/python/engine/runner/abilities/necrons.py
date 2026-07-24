"""Abilities Necrons (namespace natif `Abilities.Active.Loki.*`) — case-220 §6.7.

Module DEDIE a la faction Necrons (comme `blacklegion.py`/`genestealer.py`/`deathguard.py` : une classe
par ability, l'arbre SPECIFIQUE vit avec sa classe). RE ghidra gqfc5mff6c (VA citees). Doc :
docs/rl/case-220/necrons.md.

Contenu :
- `HarbingerOfDestruction` (1008, `necroPlasmancer`) — attaque la cible + N-1 ennemis ALEATOIRES dans un
  DISQUE rayon-2 du CASTER (non obscurcis, damageable, hors cible), 1 coup MinMaxDamage profil DirectDamage
  (pierce 100) chacun. Selecteur rayon-2 SurroundingEnemies (template splash `loki/splash.py`, adapte du
  BringerOfDespair caster-ancre `blacklegion.py`).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.selectors import (Target, Caster, CasterTile, SurroundingEnemies, Unobscured,
                                    Damageable, Sub, Union, UnitSet)
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effects.magnitude import ability_var
from .base import ActiveAbility
from .behaviours import entities_from_state, AttackWithAttackDamage
from .loki import _pick_randomly_n

if TYPE_CHECKING:
    from ..state import State


def harbinger_pool_selector(range_val: int):
    """Pool des cibles ADDITIONNELLES (mirror `HarbingerOfDestructionAbility$$GetEnemiesInRange @1811e6e50`) :

        SurroundingTiles(casterTile@0x168, includeCenter=0, range)   # DISQUE dist<=range du caster, centre exclu
        |> Units(., 1, 3)                                            # unites DEBOUT dessus
        |> Enemies(caster@0x160, ., 3)                              # ennemis du caster
        |> op_Subtraction(., target@arg)                           # MOINS la cible principale
        |> Unobscured(caster@0x160, .)                             # ligne de vue depuis le caster (terrain)
        |> Damageable(.)                                           # vivants ciblables (PV>0)

    Le triplet `Enemies(Units(SurroundingTiles(tile, incl=0, range)))` == `DSLFactory.SurroundingEnemies(tile,
    range) @180dfc570` (DECOMPILE : `SurroundingEnemies` = `Enemies(Units(SurroundingTiles(tile, incl=1,
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
    (mirror `HarbingerOfDestructionAbility$$ExecuteBehaviour @1811e6750` : UN SEUL `AttackWithAttackDamage`,
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
    `OrderBy` par id (== l'`OrderBy` de `AttackBehaviour.Execute @180fb91a0`) puis attaque CHAQUE cible 1 coup
    dans l'ordre id -> main et additionnels sont attaques dans UNE passe id-triee UNIQUE (mirror du leaf natif
    unique).

    - **MinMaxDamage(minDmg/maxDmg)** = bornes config brutes (aucun override `GetAttackDamage`), profil
      `GetDamageProfile(config, 0)` = "DirectDamage" (PiercingRatio 100 -> pierce 100), `GetNumberConstant(
      0x2f)` = nrOfHits = 1. `attackRangeType=Ranged` -> `is_melee=False`.
    - **native_factory = "attack"** (defaut, 2 tirages/coup a cc=0) : l'ExecuteBehaviour appelle
      `DSLFactory.AttackWithAttackDamage @180de9fb0` (VERIFIE par les CALLEES de @1811e6750, PAS
      `AttackWithAbilityDamage @180de9c90` -- cf. rngcrit-1202/tip #2). "DirectDamage" est le NOM DU PROFIL,
      PAS l'effet direct-damage (montant fixe) -> la feuille route par `execute_ability_attack` (crit/block)."""
    add_sel = UnitSet(additional_units)
    target_sel = Union(Target(), add_sel) if include_main else add_sel
    return AttackWithAttackDamage(target_sel, "HarbingerOfDestruction", "DirectDamage",
                                  is_melee=False, multi=True)                # MinMaxDamage/DirectDamage/0x2f=1


class HarbingerOfDestructionAbility(ActiveAbility):
    """`HarbingerOfDestructionAbility$$ExecuteBehaviour @1811e6750` (id 1008, `necroPlasmancer`, namespace
    natif `Abilities.Active.Loki`).

    Attaque la CIBLE + N-1 ennemis ALEATOIRES dans un DISQUE rayon-2 du CASTER (non obscurcis, damageable,
    hors cible), 1 coup MinMaxDamage profil DirectDamage (pierce 100) chacun, dans UNE passe id-triee unique.
    Mirror 1:1 des 4 fonctions natives (VA gqfc5mff6c) :

      - `ExecuteBehaviour @1811e6750` : UN `AttackWithAttackDamage(caster, If(AreEqual(caster,target),
        additional, Target()+additional), MinMaxDamage, Direct(profile 0), Direct(nrOfHits 0x2f))`.
      - `GetAdditionalTargets @1811e6a40` : count = `If(AreEqual(caster,target), Get(N), Get(N-1))` avec
        N = `GetVariableForLevel(config, 0x9a)` = `nrOfUnits`[level] ; range = `GetNumberConstant(0x16)` =
        `range` = 2 ; -> `GetEnemiesInRange(count, range, target, pickRandom=1)`.
      - `GetEnemiesInRange @1811e6e50` : `PickRandomly(Damageable(Unobscured(caster, SurroundingEnemies(
        casterTile, range) - target)), count)` (pickRandom=1 -> PickRandomly ; =0 -> First, chemin preview).
      - `GetTargetAmount @1811e6fa0` : accessoire preview (meme `If(AreEqual, Get(N), Get(N-1))`).

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
