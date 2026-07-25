"""Abilities actives Aeldari (porteurs `eldar*`). Module DEDIE (isolation de faction ; org native = 1 classe
par ability). RE ghidra gqfc5mff6c (VAs citees). Case-220 §6.19 (docs/rl/case-220/aeldari.md).

Executioner (1066, `eldarFarseer` « Eldryon »). Namespace natif `Abilities.Active.Loki.ExecutionerAbility`.
`IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE) :
    Execute( op_BitwiseAnd( op_BitwiseAnd( op_BitwiseAnd(
        SetCache( cacheA = Cache(Damageable(Enemies(@0x160, AdjacentUnits(@0x190, 1, 3)))) ),        # prime pool
        AttackWithAttackDamage( actor@0x160, target@0x178, MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                                damageProfile = Nullable(0xd = 13 = Psychic), hits = RoundsStarted ) ),  # [MAIN]
        If( IsDead(target@0x178),
            AttackWithAttackDamage( actor@0x160, Cache(PickRandomly(Alive(cacheA), 1)), MEME MinMaxDamage,
                                    Nullable(0xd=Psychic), hits = RoundsStarted ) ) ),                    # [SECONDARY]
        Inform( 0xc1, First( CanAddUnit(AdjacentTiles(target@0x178) & AdjacentTiles(picked)), EntityId ) ) ) )

i2 : « takes 582-2183 Psychic Damage FOR EACH ROUND THAT HAS STARTED. If the target is eliminated, an
adjacent enemy also takes 582-2183 for each round started. ». Attaque RANGED (range 2, `is_melee=False`),
profil Psychic (pierce 100). Decision DEJA portee+validee (#122/#166, prediction `ExecutionerAbility` +
`_PLAYBOOK_PROFILE_OVERRIDE[1066]="Psychic"`).

- `hits = RoundsStarted` (`IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$GetHits` = `IdunBattleLogic.Entities.DSLFactory$$RoundsStarted` -> `RoundsStartedFormula.
  IdunBattle.Entities.Formulas.RoundsStartedFormula$$Calculate` = SUM `UnitComponent.turnsStarted@+0x58` sur units-in-scope = le CASTER @0x160) =
  stat 12 (`GetStat(caster, 0xc)`), plancher `max(1,.)` (StartTurn incremente AVANT l'action -> round 1 = 1
  coup). Valeur DYNAMIQUE calculee au cast (le runner offline la maintient per-unit, #123 turnflow) — passee
  aux DEUX attaques (main + secondary), == le natif (uVar9 unique reutilise). `_rounds_started` mirror 1:1 de
  la face prediction (`ExecutionerAbility.get_special_hits`).
- `native_factory="attack"` : l'`IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$ExecuteBehaviour` appelle `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (famille ATTACK, 2 tirages/coup a cc=0 — verifie par XREF du decompile : symbole appele =
  `DSLFactory__AttackWithAttackDamage`, PAS `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage/dd0`), pour le MAIN comme le
  SECONDARY. Multi-coups (hits=RoundsStarted) -> classification factory OBLIGATOIRE (tip #2) : "attack".
- SECONDARY : ne fire QUE si la cible est MORTE apres le MAIN (`If(IsDead(Target()))`, evalue APRES le main
  dans la sequence `op_and`). Cible = 1 ennemi VIVANT tire au hasard adjacent (hex 1) a la cible
  (`PickRandomly(Alive(Enemies(AdjacentUnits(TargetTile()))), 1)`) — porte via la feuille `multi=True,
  pick_n=1` (fold du `PickRandomly` natif : pool trie par id -> `_pick_randomly_n(state.rng, 1)`, MEME conso
  rng ; pas de tuile VIDE = pas de gap #215, la pool est des UNITES). Ordre RNG = main (hits) -> pick ->
  secondary (hits).
- `SetCache(cacheA)` (prime la pool PRE-main) FOLD : mono-cible (le main ne frappe QUE la cible, pas les
  voisins) + le cadavre GARDE sa position (`damage.py` : `alive=False` seulement, pas de retrait board) ->
  recalculer la pool POST-main via `TargetTile()`/`AdjacentUnits` rend le MEME ensemble (no-op observable,
  precedent SetCache-fold SpiritLeech/SavageEchoes). Le priming ne consomme AUCUN rng -> l'ordre rng est
  preserve.
- `Inform(0xc1=193, ...)` (dernier volet) FOLD : noeud AI/UI (hint de tuile intermediaire entre la cible et
  le secondary) -> le runner ne modelise PAS le bus de messages (`Inform` = no-op documente, precedent
  FireOfAbsolution). Aucune mutation de combat -> non porte (residu documente).

HarvesterOfSouls (1067, `eldarMauganRa` « Maugan Ra »). Namespace natif `Abilities.Active.Loki.
HarvesterOfSoulsAbility`. `IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE) :
    hits = If( HasFlag(caster@0x160, Moved=0),                                   # IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetHits
               ConfigConst(nrOfHits=0x2f),                                       #   a bouge -> nrOfHits
               Sum(ConfigConst(nrOfHits=0x2f), ConfigConst(extraHit=0x2b)) )     #   pas bouge -> nrOfHits+extraHit
    surrSel = SurroundingUnits(caster@0x160, GetNumberConstant(range=0x16))      # A : unites <= range hex du caster
    enemSel = Enemies(caster@0x160, AdjacentFriends(target@0x178, 1))            # B : ennemis ring-1 de la cible
    ExecuteAtomic( op_BitwiseAnd(
        AttackWithAttackDamage( caster@0x160, target@0x178, MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                                damageProfile = Nullable(0x13 = 19 = HeavyRound), hits ),          # [MAIN]
        AttackWithAttackDamage( caster@0x160, op_BitwiseAnd(surrSel, enemSel),
                                MinMaxDamage2(minDmg_2 0x36/maxDmg_2 0x37),
                                damageProfile = Nullable(0x13 = HeavyRound), hits ) ), 0x2a )       # [SPLASH]

i2 : « 3x [dmg] HeavyRound + 1 extra hit if hasn't moved a un ennemi, ET aux ennemis adjacents dans un rayon ».
Attaque RANGED (`attackRangeType=Ranged`, `is_melee=False`), profil HeavyRound (pierce 55). Config 1067 :
nrOfHits=2, extraHit=1, range=3 ; minDmg_2/maxDmg_2 == minDmg/maxDmg (bornes PARTAGEES). Decision DEJA
portee+validee (#122, `active_ability.HarvesterOfSoulsAbility.GetHits`/`_AOE` ; ground-truth seed777 step-17
per-coup 987/1481 = entree x 0.55 = pierce 55 = HeavyRound).

- `hits = If(HasFlag(caster, Moved=0), nrOfHits, Sum(nrOfHits, extraHit))` (`IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetHits` = `IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetHitFormula`). `HasFlag(caster@0x160, 0)` (`IdunBattleLogic.Entities.DSLFactory$$HasFlag` -> `IdunBattle.Entities.Conditions.HasFlagAbilityTrigger$$ShouldTrigger` = `UnitFlagsComponent.Has(caster, flag)`, expected=1) = le caster a le flag `UnitFlag.Moved=0`
  (`UnitFlagsComponent.MOVED`, pose par `SetMovedFlag`). Le natif = `If(a_bouge, nrOfHits, nrOfHits+extraHit)` :
  A BOUGE -> nrOfHits=2 coups ; PAS BOUGE -> nrOfHits+extraHit=3 coups (i2 « +1 extra hit if hasn't moved »).
  Valeur DYNAMIQUE calculee au cast, passee aux DEUX attaques (main + splash) == le natif (uVar10 unique reutilise).
  Miroir 1:1 de la face prediction (`HarvesterOfSoulsAbility.GetHits` = MEME arbre `If(HasFlag, ...)`).
- `damageProfile = Nullable(0x13 = 19 = HeavyRound)` : le combat passe un OVERRIDE de profil EXPLICITE (stocke
  `AttackDamageBehaviour+0x88`, `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$.ctor`) = HeavyRound (`DamageProfileType.HeavyRound=19`, pierce 55),
  pour le MAIN comme le SPLASH. Coincide numeriquement avec la face prediction (config SANS damageProfile ->
  fallback arme RANGED = HeavyRound de Maugan, pierce 55, ground-truth seed777) -> profil combat "HeavyRound".
  (Contraste Executioner : `Nullable(0xd=13=Psychic)`.)
- `native_factory="attack"` : l'`IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$ExecuteBehaviour` appelle `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (famille ATTACK, 2 tirages/coup a cc=0 — XREF du decompile = `DSLFactory__AttackWithAttackDamage`,
  PAS `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage/dd0`), pour le MAIN comme le SPLASH. Multi-coups (hits=2/3) ->
  classification factory OBLIGATOIRE (tip #2) : "attack" (== Executioner).
- SPLASH (selecteur MULTI-cible passe DIRECTEMENT a UN `AttackWithAttackDamage`, PAS un `Foreach` -> patron
  PlasmaGrenade/ScythingTalons ; `multi=True`) = `And(SurroundingUnits(caster, range=3), AdjacentEnemies(target,
  1))` : ennemis du caster (1) a dist hex <= range(3) de la tuile COURANTE du caster ET (2) adjacents (ring-1)
  a la tuile de la cible. Le natif B = `Enemies(caster, AdjacentFriends(target,1))` = ennemis-du-caster adjacents
  a la cible ; PORTE via `AdjacentEnemies(TargetTile(), Const(1))` -- le runner `AdjacentFriends` filtre
  `team==CASTER` (PAS subject-relatif comme le natif), donc `Enemies(AdjacentFriends(target))` serait VIDE en
  runner ; `AdjacentEnemies(TargetTile())` = ennemis-du-caster ring-1 de la cible = l'equivalent CORRECT
  (convention etablie #122, active_ability._AOE). A & B PRUNE ASYMETRIQUEMENT (ground-truth seed777 step-17 :
  A dist<=3 exclut les ennemis a dist 4 du caster). `Alive` compense les cadavres offline (mirror : le natif
  `Units(SurroundingTiles)` n'a que les unites DEBOUT = vivantes, convention #202/#148). La cible principale est
  hors splash (B exclut le centre = tuile-cible). Bornes splash = `MinMaxDamage2` (minDmg_2/maxDmg_2 = cles
  0x36/0x37 ; == minDmg/maxDmg ici) ; MEMES hits que le main.
- `ExecuteAtomic(op_BitwiseAnd(main, splash), 0x2a)` -> `AtomicGroup(op_and(main, splash))` (inline #201 ; tag
  0x2a = id du groupe atomique, aucun `EvaluateAbilities` implicite, cf. #209). Ordre = main PUIS splash (cibles
  triees par id, `OrderBy` natif) -> meme `state.rng` -> bit-exact BY CONSTRUCTION vs une sequence directe.
- Passif `InescapableAccuracy` (eldarMauganRa, gated « n'a pas bouge » : +crit-chance/+crit-dmg/override-hits)
  = item SEPARE ([opus]+prerequis), NON porte -> le runner offline l'ignore. Consequence validation : le cas
  A BOUGE (hits=2) gate le passif OFF (cc=0, bit-exact propre) ; le cas PAS BOUGE (hits=3) : le live applique
  le passif (crits) -> divergence per-coup ATTENDUE cote live (non un bug de ce port), la structure (3 coups +
  splash) reste porte fidele.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import op_and, If, AtomicGroup
from ...entities.selectors import (Target, TargetTile, CasterTile, AdjacentUnits, AdjacentEnemies,
                                   Enemies, SurroundingUnits, And, Damageable, Alive)
from ...entities.triggers import IsDead
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.stats import StatType
from ..components import StatsComponent, UnitFlagsComponent
from .base import ActiveAbility
from .behaviours import entities_from_state, AttackWithAttackDamage

if TYPE_CHECKING:
    from ..state import State


def _rounds_started(state: "State", caster_id: int) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$GetHits` = `IdunBattleLogic.Entities.DSLFactory$$RoundsStarted` -> `RoundsStartedFormula.
    IdunBattle.Entities.Formulas.RoundsStartedFormula$$Calculate` = SUM `UnitComponent.turnsStarted@+0x58` sur units-in-scope (scope = le CASTER
    @0x160) = stat 12 (`GetStat(caster, 0xc)`, `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate`). Plancher
    `max(1,.)` (StartTurn incremente AVANT l'action -> round 1 = 1 coup, jamais 0). MIROIR 1:1 de la face
    prediction (`ExecutionerAbility.get_special_hits`, active_ability.py). Le runner offline maintient
    `turnsStarted` per-unit (#123, `StartTurnOperation.execute` bumpe `UnitComponent+0x58`)."""
    ce = state.get_entity(caster_id)
    sc = ce.get_component(StatsComponent) if ce is not None else None
    us = getattr(sc.ctx, "stats", None) if sc is not None else None
    ts = us.get_stat(int(StatType.TURNS_STARTED), 0) if us is not None else 0
    return max(1, int(ts or 0))


def executioner_tree(n_hits: int):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE ; cf. en-tete module) :
        op_and( AttackWithAttackDamage(Target(), "Executioner", "Psychic", ranged, hits=n),               # MAIN
                If( IsDead(Target()),
                    AttackWithAttackDamage(pool, "Executioner", "Psychic", ranged, multi, pick_n=1,
                                           hits=n) ) )                                                     # SECONDARY

    `pool = Alive(Damageable(Enemies(AdjacentUnits(TargetTile()))))` = ennemis (team != caster) VIVANTS
    adjacents (hex 1) a la tuile de la cible (mirror `Damageable(Enemies(@0x160, AdjacentUnits(@0x190,1,3)))`
    + `Alive` du PickRandomly natif ; `AdjacentUnits` radius defaut 1). `TargetTile()` = tuile de la cible
    (@0x190 = role tuile-cible, distinct de @0x178=Target-unit mais MEME position ; le cadavre garde sa
    tuile). `multi=True, pick_n=1` folde le `PickRandomly(., 1)` (tri par id -> `_pick_randomly_n`, no-draw si
    <=1 candidat, == natif). `hits=n` (RoundsStarted) OVERRIDE la config `nrOfHits` sur les 2 feuilles.
    `native_factory="attack"` par defaut (XREF IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage). `If(IsDead(Target()))` s'evalue APRES le MAIN
    (sequence gauche->droite `op_and`) : le secondary ne fire que si le main a tue la cible. `Inform(0xc1)` et
    `SetCache` FOLDES (cf. en-tete)."""
    ability_type = int(ActiveAbilityType.Executioner)               # AbilityOrEffect(this+0x10) threade after-hit
    main = AttackWithAttackDamage(Target(), "Executioner", "Psychic", is_melee=False,
                                  hits=n_hits, native_factory="attack", ability_type=ability_type)
    pool = Alive(Damageable(Enemies(AdjacentUnits(TargetTile()))))  # ennemis vivants adjacents a la cible
    secondary = AttackWithAttackDamage(pool, "Executioner", "Psychic", is_melee=False,
                                       multi=True, pick_n=1, hits=n_hits, native_factory="attack",
                                       ability_type=ability_type)
    return op_and(main, If(IsDead(Target()), secondary))


class ExecutionerAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$ExecuteBehaviour` (id 1066, `eldarFarseer` « Eldryon », Aeldari) —
    MIRROR du DECOMPILE, arbre DSL (`executioner_tree`). Attaque RANGED Psychic (pierce 100) `hits=RoundsStarted`
    sur la cible ; SI la cible MEURT, meme attaque sur 1 ennemi VIVANT random adjacent a la cible (`If(IsDead)`
    evalue APRES le main). Le behaviour est l'arbre DSL : la feuille `AttackWithAttackDamage` (mode bornes,
    `hits` override = RoundsStarted) emet la MEME Operation d'attaque d'ability que le pipeline combat porte
    -> bit-exact BY CONSTRUCTION vs une sequence directe sous meme rng. `native_factory="attack"` (IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage,
    XREF) -> conso rng per-coup correcte (2 tirages/coup a cc=0). Decision DEJA portee+validee (#122/#166)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Executioner)   # 1066
    ABILITY_ID = "Executioner"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        n_hits = _rounds_started(state, caster_id)                  # GetHits = RoundsStarted (uVar9 unique)
        ectx = ExecutionContext(state=state, rng=state.rng)
        executioner_tree(n_hits).execute(entities_from_state(state, caster_id, target_id), ectx)
        attacks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = attacks[0].get("attack") if attacks else None        # MAIN = 1er volet emis (Target())
        secondary = [{"target": a.get("target"), "attack": a.get("attack")} for a in attacks[1:]]
        return {"ability": "Executioner", "caster": caster_id, "target": target_id,
                "hits": n_hits, "main_attack": main, "secondary_attacks": secondary, "dsl": True}


def _harvester_hits(state: "State", caster_id: int) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetHits` = `IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetHitFormula` = arbre DSL
    `If(HasFlag(caster@0x160, Moved=0), ConfigConst(nrOfHits), Sum(ConfigConst(nrOfHits), ConfigConst(extraHit)))`.
    `HasFlag(caster, 0)` (`IdunBattleLogic.Entities.DSLFactory$$HasFlag` -> `IdunBattle.Entities.Conditions.HasFlagAbilityTrigger$$ShouldTrigger` =
    `UnitFlagsComponent.Has(caster, flag=0)`, expected=1) = le caster porte `UnitFlag.Moved=0` (a bouge ce tour).
    Donc : A BOUGE -> nrOfHits ; PAS BOUGE -> nrOfHits + extraHit (i2 « +1 extra hit if hasn't moved »). MIROIR
    1:1 de la face prediction (`active_ability.HarvesterOfSoulsAbility.GetHits`). `nrOfHits`/`extraHit` lus via
    `ability_var(is_constant=True)` = `GetNumberConstant` (config 1067 : nrOfHits=2, extraHit=1)."""
    from ...entities.effects.magnitude import ability_var
    n = int(ability_var("HarvesterOfSouls", "nrOfHits", is_constant=True) or 1)
    extra = int(ability_var("HarvesterOfSouls", "extraHit", is_constant=True) or 0)
    ce = state.get_entity(caster_id)
    fc = ce.get_component(UnitFlagsComponent) if ce is not None else None
    moved = bool(fc.has(UnitFlagsComponent.MOVED)) if fc is not None else False
    return n if moved else (n + extra)


def harvester_of_souls_tree(n_hits: int, range_r: int) -> AtomicGroup:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE ; cf. en-tete module) :
        AtomicGroup( op_and(
            AttackWithAttackDamage(Target(), "HarvesterOfSouls", "HeavyRound", ranged, hits=n),          # MAIN
            AttackWithAttackDamage( And(SurroundingUnits(CasterTile(), Const(range)),                     # SPLASH
                                        AdjacentEnemies(TargetTile(), Const(1))),
                                    "HarvesterOfSouls", "HeavyRound", ranged, min_key="minDmg_2",
                                    max_key="maxDmg_2", multi=True, hits=n ) ) )

    MAIN = attaque RANGED HeavyRound (pierce 55) sur la cible du message, `hits=n` (RoundsStarted-like : hits
    dynamique = 2 si a bouge / 3 sinon, override la config nrOfHits sur la feuille). SPLASH = MEME attaque sur les
    ennemis du caster a la fois <= `range`(3) hex de la tuile COURANTE du caster ET adjacents (ring-1) a la cible
    (`And(SurroundingUnits(CasterTile(), range), AdjacentEnemies(TargetTile(), 1))`, wrap `Alive` = compense les
    cadavres offline), bornes `MinMaxDamage2` (minDmg_2/maxDmg_2). `damageProfile = Nullable(0x13=HeavyRound)` sur
    les DEUX feuilles (override explicite du combat, pierce 55). `native_factory="attack"` par defaut (XREF
    IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage, 2 tirages/coup a cc=0 == Executioner). `multi=True` folde le selecteur multi-cible (tri par id =
    ordre de lecture natif). `ExecuteAtomic(., 0x2a)` -> `AtomicGroup` (inline #201, aucun EvaluateAbilities #209).
    Ordre = main PUIS splash -> meme `state.rng` -> bit-exact BY CONSTRUCTION."""
    ability_type = int(ActiveAbilityType.HarvesterOfSouls)          # AbilityOrEffect(this+0x10) threade after-hit
    main = AttackWithAttackDamage(Target(), "HarvesterOfSouls", "HeavyRound", is_melee=False,
                                  hits=n_hits, native_factory="attack", ability_type=ability_type)
    splash_sel = Alive(And(SurroundingUnits(CasterTile(), Const(int(range_r))),     # A : <= range hex du caster
                           AdjacentEnemies(TargetTile(), Const(1))))                # B : ennemis ring-1 de la cible
    splash = AttackWithAttackDamage(splash_sel, "HarvesterOfSouls", "HeavyRound", is_melee=False,
                                    min_key="minDmg_2", max_key="maxDmg_2", multi=True, hits=n_hits,
                                    native_factory="attack", ability_type=ability_type)
    return AtomicGroup(op_and(main, splash))


class HarvesterOfSoulsAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$ExecuteBehaviour` (id 1067, `eldarMauganRa` « Maugan Ra », Aeldari) —
    MIRROR du DECOMPILE, arbre DSL (`harvester_of_souls_tree`). Attaque RANGED HeavyRound (pierce 55)
    `hits = If(HasFlag(caster, Moved), nrOfHits=2, nrOfHits+extraHit=3)` sur la cible + MEME attaque sur les
    ennemis adjacents-cible ∩ rayon-`range`(3) du caster (splash `MinMaxDamage2`). Le behaviour est l'arbre DSL :
    les feuilles `AttackWithAttackDamage` (mode bornes, `hits` override = la formule not-moved) emettent la MEME
    Operation d'attaque d'ability que le pipeline combat porte -> bit-exact BY CONSTRUCTION vs une sequence
    directe sous meme rng. `native_factory="attack"` (IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage, XREF) -> conso rng per-coup correcte (2
    tirages/coup a cc=0). `damageProfile` override explicite = HeavyRound (`Nullable(0x13=19)`). `ExecuteAtomic`
    (tag 0x2a) -> `AtomicGroup`. Decision DEJA portee+validee (#122). Passif `InescapableAccuracy` (crit gated
    not-moved) NON porte = item separe -> le cas A BOUGE (hits=2) est le canal de validation bit-exact propre."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HarvesterOfSouls)   # 1067
    ABILITY_ID = "HarvesterOfSouls"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        n_hits = _harvester_hits(state, caster_id)                  # GetHits = If(HasFlag(Moved), nrOfHits, +extraHit)
        from ...entities.effects.magnitude import ability_var
        range_r = int(ability_var("HarvesterOfSouls", "range", is_constant=True) or 3)   # GetNumberConstant(0x16)
        ectx = ExecutionContext(state=state, rng=state.rng)
        harvester_of_souls_tree(n_hits, range_r).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)  # MAIN = feuille Target()
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]   # cibles splash != cible principale
        return {"ability": "HarvesterOfSouls", "caster": caster_id, "target": target_id,
                "hits": n_hits, "main_attack": main, "splash": splash, "dsl": True}
