"""Abilities actives Aeldari (porteurs `eldar*`). Module DEDIE (isolation de faction ; org native = 1 classe
par ability). RE ghidra gqfc5mff6c (VAs citees). Case-220 §6.19 (docs/rl/case-220/aeldari.md).

Executioner (1066, `eldarFarseer` « Eldryon »). Namespace natif `Abilities.Active.Loki.ExecutionerAbility`.
`ExecutionerAbility.ExecuteBehaviour @1811d9f10` (MIRROR du DECOMPILE) :
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

- `hits = RoundsStarted` (`GetHits @1811da4a0` = `DSLFactory.RoundsStarted @180dfa6c0` -> `RoundsStartedFormula.
  Calculate @180f223e0` = SUM `UnitComponent.turnsStarted@+0x58` sur units-in-scope = le CASTER @0x160) =
  stat 12 (`GetStat(caster, 0xc)`), plancher `max(1,.)` (StartTurn incremente AVANT l'action -> round 1 = 1
  coup). Valeur DYNAMIQUE calculee au cast (le runner offline la maintient per-unit, #123 turnflow) — passee
  aux DEUX attaques (main + secondary), == le natif (uVar9 unique reutilise). `_rounds_started` mirror 1:1 de
  la face prediction (`ExecutionerAbility.get_special_hits`).
- `native_factory="attack"` : l'`ExecuteBehaviour @1811d9f10` appelle `DSLFactory.AttackWithAttackDamage
  @180de9fb0` (famille ATTACK, 2 tirages/coup a cc=0 — verifie par XREF du decompile : symbole appele =
  `DSLFactory__AttackWithAttackDamage`, PAS `AttackWithAbilityDamage @180de9c90/dd0`), pour le MAIN comme le
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
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.effects import ExecutionContext
from ...entities.behaviours import op_and, If
from ...entities.selectors import Target, TargetTile, AdjacentUnits, Enemies, Damageable, Alive
from ...entities.triggers import IsDead
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.stats import StatType
from ..components import StatsComponent
from .base import ActiveAbility
from .behaviours import entities_from_state, AttackWithAttackDamage

if TYPE_CHECKING:
    from ..state import State


def _rounds_started(state: "State", caster_id: int) -> int:
    """`ExecutionerAbility.GetHits @1811da4a0` = `DSLFactory.RoundsStarted @180dfa6c0` -> `RoundsStartedFormula.
    Calculate @180f223e0` = SUM `UnitComponent.turnsStarted@+0x58` sur units-in-scope (scope = le CASTER
    @0x160) = stat 12 (`GetStat(caster, 0xc)`, `UnitTurnsStartedFormula.Calculate @180f2d6c0`). Plancher
    `max(1,.)` (StartTurn incremente AVANT l'action -> round 1 = 1 coup, jamais 0). MIROIR 1:1 de la face
    prediction (`ExecutionerAbility.get_special_hits`, active_ability.py). Le runner offline maintient
    `turnsStarted` per-unit (#123, `StartTurnOperation.execute` bumpe `UnitComponent+0x58`)."""
    ce = state.get_entity(caster_id)
    sc = ce.get_component(StatsComponent) if ce is not None else None
    us = getattr(sc.ctx, "stats", None) if sc is not None else None
    ts = us.get_stat(int(StatType.TURNS_STARTED), 0) if us is not None else 0
    return max(1, int(ts or 0))


def executioner_tree(n_hits: int):
    """Arbre de `ExecutionerAbility.ExecuteBehaviour @1811d9f10` (MIRROR du DECOMPILE ; cf. en-tete module) :
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
    `native_factory="attack"` par defaut (XREF @180de9fb0). `If(IsDead(Target()))` s'evalue APRES le MAIN
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
    """`ExecutionerAbility.ExecuteBehaviour @1811d9f10` (id 1066, `eldarFarseer` « Eldryon », Aeldari) —
    MIRROR du DECOMPILE, arbre DSL (`executioner_tree`). Attaque RANGED Psychic (pierce 100) `hits=RoundsStarted`
    sur la cible ; SI la cible MEURT, meme attaque sur 1 ennemi VIVANT random adjacent a la cible (`If(IsDead)`
    evalue APRES le main). Le behaviour est l'arbre DSL : la feuille `AttackWithAttackDamage` (mode bornes,
    `hits` override = RoundsStarted) emet la MEME Operation d'attaque d'ability que le pipeline combat porte
    -> bit-exact BY CONSTRUCTION vs une sequence directe sous meme rng. `native_factory="attack"` (@180de9fb0,
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
