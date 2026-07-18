"""Ability-triggers gen-stealer — passif `DecoysAndMisdirection` d'Isaak (`genesPrimus`), slice G2.

Namespace natif `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_*`. Le passif est
materialise par DEUX abilities-triggers DISTINCTES (2 entrees dans `AbilityAndEffectCache`), split par la
CONDITION DE FACTION (`AreEnemies` vs `AreFriends`), PAS par l'event :

- `DecoysAndMisdirection_DamageEnemiesAbility` (CreateTrigger @180e20310, CreateBehaviour @180e20190) :
    `On(0x1d=UnitPositionChanged_2) & AreEnemies(owner, actor) & AmountIsGreaterThanZero(GetValidDeadDecoys)`
    -> `Repeat( AttackWithAbilityDamage(owner, actor=stepper, MinMaxDamage, Blast, GetHits=1),
               Count(GetValidDeadDecoys) )`
- `DecoysAndMisdirection_BuffFriendsAbility` (CreateTrigger @180e20050, CreateBehaviour @180e1fe30) :
    `(On(0x2f=UnitResurrected) | On(0x1d)) & AreFriends(owner, actor) & AmountIsGreaterThanZero(GetValidDeadDecoys)`
    -> `AddEffect(1379 DecoysAndMisdirection_ExtraDamage +582, on=actor)` + `If(HasFaction(actor,
       GenestealerCults), spawn_decoy(First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(actor)))),
       ForSteppable))`

Base `ADecoysAndMisdirectionAbility.GetValidDeadDecoys @180e13550` = `Filter(AllDeadUnits, AreFriends(owner,
decoy) & HasTrait(decoy, 0x41d=1053 Decoy) & IsKilledThisTurn(decoy) & AreEqual(Killer(decoy), actor) &
Contains(Tiles(actor), MainTileOfUnits(decoy)))` -> collapse `_valid_dead_decoys`.

VECTEUR : le natif `MoveUnitOperation.EvaluateAfterMoveTriggers @180e79770` emet On(0x24) puis On(4=
UnitAfterMove, overwatch) puis On(0x1d=UnitPositionChanged_2) ; le decoy est crushe INLINE (`_kill_steppable_
units`, G1) AVANT -> `GetValidDeadDecoys` le lit deja mort. `dispatch.after_move_triggers` emet On(4) PUIS
On(0x1d) (le path resurrect On(0x2f) viendra avec G3-Ambush).

FEUILLE Blast (decompile @180e20190 VERIFIE) : `DSLFactory$$AttackWithAbilityDamage @180de9c90` -> base
@180de9e50 = `AttackBehaviour(AbilityDamageBehaviour(MinMaxDamage, Blast, source))` = pipeline crit/block
COMPLET (PAS le direct pierce-only). Portee par le leaf `AttackWithAttackDamage` (`execute_ability_attack`,
config MinMaxDamage) -> meme pipeline que les autres Blast d'ability (Stikkbomb/Fragstorm/Plasma). Le profil
Blast porte `HitsMultipleMembers` (splash) -> le leaf attaque le stepper SEUL ; le splash multi-membres n'est
PAS re-derive ici (FLAG, verdict RE G2 point #2 : geometrie a confirmer live). RE ghidra gqfc5mff6c.
Doc : docs/rl/genestealer-cults.md.
"""
from __future__ import annotations

from ...state import State
from ...components import OwnerComponent, UnitComponent, PositionComponent, StatsComponent
from ....entities.traits.unit_trait import UnitTrait, has_trait
from ....entities.effect_type import EffectType
from ....dsl.event_trigger_type import EventTriggerType
from .base import TriggeredAbility, _faction_id

import hexgeo

DECOYS_EXTRA_DMG = int(EffectType.DecoysAndMisdirection_ExtraDamage)   # 1379 (0x563)
DECOY_TRAIT = UnitTrait.Decoy                        # 1053 (0x41d)
GENESTEALERS_FACTION = "Genestealers"                # HasFaction(0xf=GenestealerCults) (FactionId gameconfig)
ABILITY_ID = "DecoysAndMisdirection"
BLAST_PROFILE = "Blast"                              # profile=Blast{PiercingRatio:15, Traits:[HitsMultipleMembers]}


# ----- selecteurs S collapses (AreFriends/AreEnemies, GetValidDeadDecoys, AdjacentFreeTiles) -----

def _team_of(state: State, uid: int):
    e = state.get_entity(uid)
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _are_friends(state: State, a: int, b: int) -> bool:
    """`AreFriends(a, b)` — meme team (allies)."""
    ta, tb = _team_of(state, a), _team_of(state, b)
    return ta is not None and ta == tb


def _are_enemies(state: State, a: int, b: int) -> bool:
    """`AreEnemies(a, b)` — teams differentes."""
    ta, tb = _team_of(state, a), _team_of(state, b)
    return ta is not None and tb is not None and ta != tb


def _pos_of(state: State, uid: int):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _valid_dead_decoys(state: State, owner_id: int, stepper_id: int) -> list:
    """`GetValidDeadDecoys @180e13550` (collapse S) : decoys (trait Decoy 1053) MORTS, amis de owner, tues CE
    TOUR PAR le stepper, sur une tuile occupee par le stepper.

    Collapse : le stepper vient de MOVE sur la tuile d'un decoy, crushe INLINE (`_kill_steppable_units` G1) ->
    le decoy DEAD co-localise avec le stepper == celui qu'il a ecrase par CE move. `_kill_steppable_units` est
    un kill PROPRE (pas de trace killer/killed-this-turn) -> `AreEqual(Killer, stepper)` & `IsKilledThisTurn`
    sont APPROXIMES par la co-localisation dead-decoy/stepper (positions exclusives : la tuile est liberee au
    crush puis reoccupee par le stepper -> au plus 1 decoy mort la ; un decoy mort d'un tour anterieur est sur
    une AUTRE tuile). FLAG : le cas multi-decoys-meme-tuile (`Repeat` count>1) n'est pas atteignable (positions
    exclusives -> count 1). Cf. verdict RE G2 point #5."""
    spos = _pos_of(state, stepper_id)
    o_team = _team_of(state, owner_id)
    if spos is None or o_team is None:
        return []
    out = []
    for uid, e in state.entities.items():
        if uid == stepper_id:
            continue
        uc = e.get_component(UnitComponent)
        if uc is None or uc.alive:                    # decoy MORT (crushe)
            continue
        sc = e.get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if not has_trait(traits or [], DECOY_TRAIT):  # HasTrait(decoy, Decoy=1053)
            continue
        oc = e.get_component(OwnerComponent)
        if oc is None or oc.team != o_team:           # AreFriends(owner, decoy)
            continue
        pc = e.get_component(PositionComponent)
        if pc is None or (pc.col, pc.row) != spos:    # Contains(Tiles(stepper), decoy tile) + Killer==stepper
            continue
        out.append(uid)
    return out


def _adjacent_free_tile(state: State, unit_id: int):
    """`First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(unit)), 7, owner))` (collapse S) : 1re tuile
    LIBRE marchable adjacente (hex dist 1) a `unit`. Le tri par utilite-summon est collapse en ordre
    deterministe (id de tuile croissant) -> First. Renvoie un id de tuile (arg `spawn_decoy`) ou None."""
    board = state.board
    pos = _pos_of(state, unit_id)
    if board is None or pos is None:
        return None
    occ = set()
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None or (uc is not None and not uc.alive):
            continue
        occ.add((pc.col, pc.row))
    cands = []
    for (c, r) in hexgeo.disk(pos[0], pos[1], 1):
        if (c, r) == pos or (c, r) in occ:
            continue
        t = board.id_at(c, r)
        if t is None or not board.walkable(t):
            continue
        cands.append(t)
    return sorted(cands)[0] if cands else None


def _owner_level_mult(state: State, owner_id: int):
    """(niveau, multiplier) de l'ability PASSIVE de l'owner Isaak — portés sur l'effet 1379 posé pour que
    `DecoysAndMisdirectionExtraDamageEffect.create_effect_damage_bonus_for_attack` (query-time) lise
    `extraDmg[niveau du SOURCE]` (docstring effet : "niveau/multiplier = ceux du SOURCE genesPrimus"). Niveau
    passif non exposé offline -> approximé par `active_ability_level` (FLAG : à confirmer par validation live
    du path ALLIÉ ; mon test cible le path ENNEMI)."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    level = getattr(ctx, "active_ability_level", None) if ctx is not None else None
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    return level, mult


# ----- les 2 abilities-triggers -----

class DecoysAndMisdirectionDamageEnemiesAbility(TriggeredAbility):
    """`DecoysAndMisdirection_DamageEnemiesAbility` (CreateTrigger @180e20310, CreateBehaviour @180e20190).
    Un ENNEMI (de l'owner Isaak) qui MOVE sur un decoy allie crushe -> `Repeat(Blast sur le stepper,
    count=nb decoys morts valides)`. On(0x1d). Blast = leaf `AttackWithAttackDamage` (pipeline crit/block, config
    MinMaxDamage 1455-1746@L65, nrOfHits=1, profil Blast) sur le stepper (`ev.actor_id`)."""
    event_id = int(EventTriggerType.UnitPositionChanged_2)   # 29 (0x1d)

    def matches(self, state, ev):
        return (_are_enemies(state, self.owner_id, ev.actor_id)
                and len(_valid_dead_decoys(state, self.owner_id, ev.actor_id)) > 0)

    def execute_behaviour(self, state, ev):
        from ...abilities.behaviours import AttackWithAttackDamage, entities_from_state
        from ....dsl.effects import ExecutionContext
        from ....entities.selectors import Target
        stepper = ev.actor_id
        n = len(_valid_dead_decoys(state, self.owner_id, stepper))
        blasts = []
        for _ in range(n):                            # Repeat( ... , Count(GetValidDeadDecoys) )
            ectx = ExecutionContext(state=state, rng=state.rng)
            AttackWithAttackDamage(Target(), ABILITY_ID, BLAST_PROFILE, is_melee=False).execute(
                entities_from_state(state, self.owner_id, stepper), ectx)
            atk = next((p for nm, p in ectx.emitted if nm == "AttackWithAttackDamage"), None)
            blasts.append(atk)
        return {"ability": "DecoysAndMisdirection_DamageEnemies", "owner": self.owner_id,
                "target": stepper, "count": n, "blasts": blasts}


class DecoysAndMisdirectionBuffFriendsAbility(TriggeredAbility):
    """`DecoysAndMisdirection_BuffFriendsAbility` (CreateTrigger @180e20050, CreateBehaviour @180e1fe30).
    Un ALLIE (de l'owner Isaak) qui MOVE/RESURRECT sur un decoy allie crushe -> `AddEffect(1379
    DecoysAndMisdirection_ExtraDamage +582, on=stepper)` (jusqu'a fin de son tour, `remaining_turns=1`) +
    `If(HasFaction(stepper, GenestealerCults), spawn_decoy(hex adjacent libre du stepper, ForSteppable))`.
    On(0x2f)|On(0x1d).

    ⚠ Le path RESURRECT (On(0x2f)) fire aussi ce trigger MAIS aucun vecteur resurrect n'est encore porte
    (G3-Ambush) -> en pratique seul le path MOVE (On(0x1d)) le declenche aujourd'hui."""
    event_id = int(EventTriggerType.UnitPositionChanged_2)   # 29 (0x1d, move)
    event_ids = (int(EventTriggerType.UnitResurrected),      # 47 (0x2f, resurrect -> G3)
                 int(EventTriggerType.UnitPositionChanged_2))  # 29 (0x1d, move)

    def matches(self, state, ev):
        return (_are_friends(state, self.owner_id, ev.actor_id)
                and len(_valid_dead_decoys(state, self.owner_id, ev.actor_id)) > 0)

    def execute_behaviour(self, state, ev):
        from ..effects import AddEffectOperation
        from ..spawn import spawn_decoy
        stepper = ev.actor_id
        # AddEffect(1379) sur le stepper : l'effet DecoysAndMisdirectionExtraDamageEffect lit extraDmg AU
        # QUERY-TIME depuis le niveau/mult PORTÉS -> on les initialise depuis le SOURCE (owner Isaak) après la
        # pose (docstring effet : "niveau/multiplier = ceux du SOURCE genesPrimus"). remaining_turns=1 (fin de
        # tour). AddEffectOperation no-op si un même-type est déjà présent sur le stepper (refresh-équivalent).
        eff = AddEffectOperation.execute(state, self.owner_id, stepper, DECOYS_EXTRA_DMG,
                                         name="DecoysAndMisdirection_ExtraDamage", duration_override=1)
        if eff is not None:
            lvl, mult = _owner_level_mult(state, self.owner_id)
            eff.ability_level = lvl                       # niveau du passif de l'owner (proxy, FLAG path allié)
            eff.ability_variables_multiplier = mult
        spawned = None
        if _faction_id(state, stepper) == GENESTEALERS_FACTION:   # If(HasFaction(stepper, GS Cult))
            tile = _adjacent_free_tile(state, stepper)
            if tile is not None:
                spawned = spawn_decoy(state, tile, self.owner_id)
        return {"ability": "DecoysAndMisdirection_BuffFriends", "owner": self.owner_id,
                "target": stepper, "effect": DECOYS_EXTRA_DMG, "spawned_decoy": spawned}
