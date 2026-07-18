"""Ability-triggers gen-stealer — passif `DecoysAndMisdirection` d'Isaak (G2) + trait `Ambush` (G3).

## G2 — DecoysAndMisdirection
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
from ...components import (OwnerComponent, UnitComponent, PositionComponent, StatsComponent,
                          HealthComponent, UnitFlagsComponent)
from ....entities.traits.unit_trait import UnitTrait, has_trait
from ....entities.effect_type import EffectType
from ....dsl.event_trigger_type import EventTriggerType
from .base import TriggeredAbility, _faction_id, _pick_randomly

import hexgeo

DECOYS_EXTRA_DMG = int(EffectType.DecoysAndMisdirection_ExtraDamage)   # 1379 (0x563)
DECOY_TRAIT = UnitTrait.Decoy                        # 1053 (0x41d)
AMBUSH_TRAIT = UnitTrait.Ambush                      # 1052 (0x41c) — G3
HERO_TRAIT = UnitTrait.Hero                          # 16 (0x10) — Character-first (G3)
GENESTEALERS_FACTION = "Genestealers"                # HasFaction(0xf=GenestealerCults) (FactionId gameconfig)
ABILITY_ID = "DecoysAndMisdirection"
BLAST_PROFILE = "Blast"                              # profile=Blast{PiercingRatio:15, Traits:[HitsMultipleMembers]}
RESURRECT_TURN_DELAY = 1                             # G3 constants@0xc0 : Difference(turnsStarted, turnDefeated)==1


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


# =====================================================================================================
# G3 — trait Ambush (1052) : mort -> decoy + resurrection sur decoy allie + tour immediat
#
# Namespace natif `IdunBattleLogic.Entities.Abilities.Triggered.Loki`. Le trait 1052 = 2 abilities-triggers :
#   - `Ambush_SummonAbility`      (CreateTrigger @180e15970, GetSummonBehaviour @180e15a10) : mort -> decoy.
#   - `EnvAmbushResurrectAbility`  (CreateTrigger @180f79a10, CreateBehaviour @180f79760)   : resurrection.
# La feuille DSL `Resurrect` @180dfa420 appelle l'Operation imperative `ResurrectUnitOperation.Execute
# @180e8e4c0` (../resurrect.py) qui pose le flag one-shot 0xe + crushe le decoy + emet On(UnitResurrected=47).
# RE ghidra gqfc5mff6c ; doc docs/rl/genestealer-cults.md (verdict G3).
# =====================================================================================================

def _free_tile_or_adjacent(state: State, coord):
    """`First(FreeTilesOrAdjacentFreeTiles(Tiles(target), constants@0xf8))` (collapse S) : la tuile de `coord`
    si LIBRE (aucun vivant) et marchable, sinon la 1re tuile libre marchable ADJACENTE (hex, ordre id
    croissant = First). Renvoie un id de tuile (arg `spawn_decoy`) ou None. Le porteur mourant etant
    alive=False, sa PROPRE tuile est 'libre' -> le decoy se pose sur la tuile du mort."""
    board = state.board
    if board is None or coord is None:
        return None
    occ = set()
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None or (uc is not None and not uc.alive):     # occupants VIVANTS uniquement
            continue
        occ.add((pc.col, pc.row))
    center = (int(coord[0]), int(coord[1]))
    if center not in occ:                                        # FreeTiles(Tiles(target)) : la tuile du mort
        t = board.id_at(center[0], center[1])
        if t is not None and board.walkable(t):
            return t
    cands = []                                                   # AdjacentFreeTiles : voisins hex libres
    for (c, r) in hexgeo.disk(center[0], center[1], 1):
        if (c, r) == center or (c, r) in occ:
            continue
        t = board.id_at(c, r)
        if t is not None and board.walkable(t):
            cands.append(t)
    return sorted(cands)[0] if cands else None


def _valid_decoys(state: State, player) -> list:
    """`GetValidDecoys @180f79d80` (collapse S) : decoys VIVANTS (trait Decoy 1053) du joueur `player`, sur
    une tuile marchable (`IsCanAddUnit(Tiles(decoy))`). Le decoy est crushe a la resurrection (l'unite
    reapparait sur SA tuile). Le `Not(HasEffect(decoy, 1390))` natif (decoy deja reclame) est assure par la
    RE-EVALUATION entre iterations du behaviour (un decoy crushe passe alive=False -> exclu de l'appel suivant).
    `player`-based (CopyOwner : un decoy herite du player du caster => meme player == meme team, runner 2-team)."""
    board = state.board
    out = []
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is None or not uc.alive:                    # decoy VIVANT (token debout)
            continue
        sc = e.get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if not has_trait(traits or [], DECOY_TRAIT):      # HasTrait(decoy, Decoy=1053)
            continue
        oc = e.get_component(OwnerComponent)
        if oc is None or oc.player != player:             # AreFriends(decoy, CurrentPlayer)
            continue
        pc = e.get_component(PositionComponent)
        if pc is None:
            continue
        if board is not None:                             # IsCanAddUnit(Tiles(decoy)) ~ tuile marchable
            t = board.id_at(pc.col, pc.row)
            if t is None or not board.walkable(t):
                continue
        out.append(uid)
    return out


def _eligible_for_resurrect(state: State, player) -> list:
    """`GetUnitsEligibleForResurrect @180f79b90` (collapse S) : unites MORTES du joueur `player` portant le
    trait Ambush, PAS deja ressuscitees (`Not(HasFlag 0xe)`), mortes au tour PRECEDENT du joueur
    (`AmountIsEqual(Difference(CurrentPlayerTurnsStarted, TurnDefeated(u)), @0xc0=1)`). `turn_defeated` est
    pose a la mort par `AmbushSummonAbility`."""
    cur = state.turn_counts.get(int(player), 0)
    out = []
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is None or uc.alive:                        # IsDefeated(u)
            continue
        oc = e.get_component(OwnerComponent)
        if oc is None or oc.player != player:             # AreEqual(OriginalOwner(u), CurrentPlayer)
            continue
        sc = e.get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if not has_trait(traits or [], AMBUSH_TRAIT):     # HasTrait(u, Ambush=1052)
            continue
        fl = e.get_component(UnitFlagsComponent)
        if fl is not None and fl.has(UnitFlagsComponent.AMBUSH_CONSUMED):   # Not(HasFlag 0xe)
            continue
        td = uc.turn_defeated
        if td is None or (cur - int(td)) != RESURRECT_TURN_DELAY:           # Difference == @0xc0(=1)
            continue
        out.append(uid)
    return out


def _max_health(state: State, uid: int):
    """PV pleins de `uid` (`StatAmount(unit, Health=5, mode=2)` = max health) pour SetHealth a la resurrection."""
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp_max if hc is not None else None


class AmbushSummonAbility(TriggeredAbility):
    """`Ambush_SummonAbility` (CreateTrigger @180e15970, GetSummonBehaviour @180e15a10). A la MORT d'un porteur
    Ambush : `On(UnitDefeated=55) & OwnerIsTarget & Not(HasFlag(owner, 0xe))` -> pose 1 decoy genesSmnDecoy sur
    la tuile du mort (sinon adjacente libre), ForSteppable (feuille Spawn = G1). ENREGISTRE aussi `turn_defeated`
    (base du delai de resurrection). `fire_on_death` : l'owner EST l'unite morte (alive=False)."""
    event_id = int(EventTriggerType.UnitDefeated)         # 55 (0x37)
    fire_on_death = True

    def matches(self, state, ev):
        u = ev.dying_id if ev.dying_id is not None else ev.target_id
        if u != self.owner_id:                            # OwnerIsTarget (owner = unite morte)
            return False
        e = state.get_entity(u)
        sc = e.get_component(StatsComponent) if e is not None else None
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if not has_trait(traits or [], AMBUSH_TRAIT):     # HasTrait(owner, Ambush)
            return False
        fl = e.get_component(UnitFlagsComponent) if e is not None else None
        return not (fl is not None and fl.has(UnitFlagsComponent.AMBUSH_CONSUMED))   # Not(HasFlag 0xe)

    def execute_behaviour(self, state, ev):
        from ..spawn import spawn_decoy
        u = self.owner_id
        e = state.get_entity(u)
        uc = e.get_component(UnitComponent) if e is not None else None
        oc = e.get_component(OwnerComponent) if e is not None else None
        # TurnDefeated = compteur de tours du joueur du porteur A LA MORT (base du delai `Difference == 1`).
        if uc is not None:
            uc.turn_defeated = state.turn_counts.get(int(oc.player), 0) if (oc is not None and oc.player is not None) else 0
        tile = _free_tile_or_adjacent(state, _pos_of(state, u))     # FreeTilesOrAdjacentFreeTiles(Tiles(target))
        did = spawn_decoy(state, tile, u) if tile is not None else None
        return {"ability": "Ambush_Summon", "owner": u, "decoy": did,
                "turn_defeated": (uc.turn_defeated if uc is not None else None)}


class EnvAmbushResurrectAbility(TriggeredAbility):
    """`EnvAmbushResurrectAbility` (CreateTrigger @180f79a10, CreateBehaviour @180f79760). Au DEBUT du tour du
    joueur courant : `On(TurnStart_Actions=22) & AmountIsGreaterThanZero(GetValidDecoys) &
    AmountIsGreaterThanZero(GetUnitsEligibleForResurrect)` -> ressuscite chaque porteur Ambush eligible (mort
    au tour precedent, non deja ressuscite) sur un decoy allie ALEATOIRE, PV pleins, TOUR IMMEDIAT. Ordre
    CHARACTER-FIRST (Hero avant non-Hero, `SortByFormula(HasTrait Hero)`).

    `fire_on_death` : l'owner (porteur Ambush) est en general MORT quand il ressuscite. Le behaviour est GLOBAL
    (enumere TOUS les eligibles) -> IDEMPOTENT via le flag 0xe : la 1re instance a fire ressuscite tout le
    monde (pose 0xe sur chacun), les instances suivantes trouvent `_eligible_for_resurrect` vide (matches False)."""
    event_id = int(EventTriggerType.TurnStart_Actions)    # 22 (0x16)
    fire_on_death = True

    def matches(self, state, ev):
        player = ev.player_id
        if player is None:
            return False
        return (len(_valid_decoys(state, player)) > 0
                and len(_eligible_for_resurrect(state, player)) > 0)

    def execute_behaviour(self, state, ev):
        from ..resurrect import ResurrectUnitOperation
        player = ev.player_id
        eligible = _eligible_for_resurrect(state, player)
        if not eligible:
            return None

        def _hero_key(u):                                 # SortByFormula(HasTrait Hero) : Hero devant
            e = state.get_entity(u)
            sc = e.get_component(StatsComponent) if e is not None else None
            traits = getattr(sc.ctx, "traits", None) if sc is not None else None
            return (0 if has_trait(traits or [], HERO_TRAIT) else 1, u)
        eligible.sort(key=_hero_key)

        out = []
        for unit in eligible:
            decoys = _valid_decoys(state, player)         # re-eval : decoy crushe (resurrection precedente) exclu
            if not decoys:
                break
            decoy = _pick_randomly(state, decoys)          # PickRandomly(decoys, 1)
            dest = _pos_of(state, decoy)                   # tuile du decoy = point de reapparition
            r = ResurrectUnitOperation.execute(state, unit, dest, _max_health(state, unit), immediate_turn=True)
            if r is not None:
                out.append(r)
        return {"ability": "EnvAmbushResurrect", "player": player, "resurrections": out} if out else None
