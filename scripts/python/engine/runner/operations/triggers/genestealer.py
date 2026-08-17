"""Ability-triggers gen-stealer — passif `DecoysAndMisdirection` d'Isaak (G2) + trait `Ambush` (G3).

## G2 — DecoysAndMisdirection
Namespace natif `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_*`. Le passif est
materialise par DEUX abilities-triggers DISTINCTES (2 entrees dans `AbilityAndEffectCache`), split par la
CONDITION DE FACTION (`AreEnemies` vs `AreFriends`), PAS par l'event :

- `DecoysAndMisdirection_DamageEnemiesAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_DamageEnemiesAbility$$CreateTrigger, IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_DamageEnemiesAbility$$CreateBehaviour) :
    `On(0x1d=UnitPositionChanged_2) & AreEnemies(owner, actor) & AmountIsGreaterThanZero(GetValidDeadDecoys)`
    -> `Repeat( AttackWithAbilityDamage(owner, actor=stepper, MinMaxDamage, Blast, GetHits=1),
               Count(GetValidDeadDecoys) )`
- `DecoysAndMisdirection_BuffFriendsAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_BuffFriendsAbility$$CreateTrigger, IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_BuffFriendsAbility$$CreateBehaviour) :
    `(On(0x2e=UnitResurrected) | On(0x1d)) & AreFriends(owner, actor) & AmountIsGreaterThanZero(GetValidDeadDecoys)`
    -> `AddEffect(1379 DecoysAndMisdirection_ExtraDamage +582, on=actor)` + `If(HasFaction(actor,
       GenestealerCults), spawn_decoy(First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(actor)))),
       ForSteppable))`

Base `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ADecoysAndMisdirectionAbility$$GetValidDeadDecoys` = `Filter(AllDeadUnits, AreFriends(owner,
decoy) & HasTrait(decoy, 0x41d=1053 Decoy) & IsKilledThisTurn(decoy) & AreEqual(Killer(decoy), actor) &
Contains(Tiles(actor), MainTileOfUnits(decoy)))` -> collapse `_valid_dead_decoys`.

VECTEUR : le natif `IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers` emet On(0x24) puis On(4=
UnitAfterMove, overwatch) puis On(0x1d=UnitPositionChanged_2) ; le decoy est crushe INLINE (`_kill_steppable_
units`, G1) AVANT -> `GetValidDeadDecoys` le lit deja mort. `dispatch.after_move_triggers` emet On(4) PUIS
On(0x1d) (le path resurrect On(0x2e = UnitResurrected) viendra avec G3-Ambush).

FEUILLE Blast (decompile IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_DamageEnemiesAbility$$CreateBehaviour VERIFIE) : `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` -> base
IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage = `AttackBehaviour(AbilityDamageBehaviour(MinMaxDamage, Blast, source))` = pipeline crit/block
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
from ....entities.traits.unit_trait import UnitTrait, entity_trait_names, has_trait
from ....entities.effect_type import EffectType
from ....entities.effects.magnitude import ability_var
from ....entities.pathfinding.walk_pathfinder import get_movable_positions
from ....dsl.event_trigger_type import EventTriggerType
from .base import TriggeredAbility, _faction_id, _pick_randomly

import hexgeo
from ....dsl.effects import ExecutionContext
from ....entities.selectors.accessors import Target
from ...abilities.base import profile_pierce
from ...abilities.behaviours.combat import AttackWithAttackDamage
from ...abilities.behaviours.context import entities_from_state
from ...events import EventBus
from ..damage import AttackDamageOperation
from ..effects import AddEffectOperation
from ..movement import MoveUnitOperation
from ..spawn import spawn_decoy

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
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ADecoysAndMisdirectionAbility$$GetValidDeadDecoys`,
    relu conjoint par conjoint sur le build `rnca9r7q6c` :

        Filter( AllDeadUnits,
                  AreFriends(sel@0x30 owner, sel@0x68 it)
                & HasTrait(sel@0x68 it, 0x41d = 1053 Decoy)
                & IsKilledThisTurn(sel@0x68 it)
                & AreEqual(Killer(it), sel@0x40 stepper)
                & Contains(Tiles(sel@0x40 stepper), MainTileOfUnits(it)) )

    LES CINQ SONT PORTES (#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r3). Les deux du milieu ne l'etaient
    pas : le port les COLLAPSAIT en co-localisation, et leur seul discriminant etait la presence du
    `StatsComponent` -- un artefact du port, pas un concept natif. Les deux ont desormais leur
    substrat, et ce sont DEUX champs DISTINCTS du `UnitComponent`, pas un seul :

      * `IsKilledThisTurn(it)` -> `UnitComponent.killed_this_turn` (`+0x17a`, un BOOLEEN), pose par
        `IdunBattle.Operations.KillUnitOperation$$Execute+0x828` et efface par
        `IdunBattle.Operations.StartTurnOperation$$ResetUnit` -- qui ne visite QUE les vivants
        (`PlayerComponent.CurrentlyOwnedUnitIds`), d'ou la semantique reelle « tuee, et n'a pas
        redemarre de tour depuis ». (Ce n'est PAS `turn_defeated`/`+0x17c`, un ENTIER dont le
        lecteur est `IdunBattle.Entities.Formulas.TurnDefeatedFormula$$Calculate`.)
      * `AreEqual(Killer(it), stepper)` -> `UnitComponent.death_source[0]`.
        `IdunBattle.Entities.Selectors.UnitKillerSelector$$Select` lit exactement ce champ : pour
        chaque unite selectionnee, `uc = GetComponent<UnitComponent>(unit)`, puis
        `Nullable<DamageSource>@+0x108` ; si `HasValue` ET
        `IdunBattle.Operations.DamageSource$$get_KillerId() != 0`, il resout l'entite de cet id et ne
        la retient que si `IdunBattle.Entities.EntityExtensions$$IsActor(entity)`.

    CE QUE LE COLLAPSE LAISSAIT PASSER, et qui est ferme ici : un decoy tue au tour N par une AUTRE
    unite reste MORT SUR SA TUILE cote port ; si un stepper ami marche sur cette tuile au tour N+k,
    la co-localisation seule le rendait valide et faisait BLASTER. Le natif le refuse par
    `AreEqual(Killer(it), stepper)`. La docstring precedente affirmait l'inverse (« un decoy mort
    d'un tour anterieur est sur une AUTRE tuile ») -- rien ne libere sa tuile.

    TRI-ETAT sur `killed_this_turn` : `None` = NON MESURE (cadavre-AU-CHARGEMENT ; aucun canal ne
    publie `+0x17a`). On REFUSE, et c'est value-preserving par rapport au gate `sc is None` qu'on
    remplace -- mais la raison change de mains : ce n'est plus « pas de `StatsComponent` », c'est
    « on ne sait pas s'il a ete tue ». Le conjoint `AreEqual(Killer(it), stepper)` le refuserait de
    toute facon (`death_source is None` sur un cadavre-au-chargement).

    FLAG conserve : le cas multi-decoys-meme-tuile (`Repeat` count>1) n'est pas atteignable
    (positions exclusives -> count 1)."""
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
        # `IsKilledThisTurn(sel@0x68)` -- 3e conjoint natif, PORTE (cf. docstring). Tri-etat :
        # `None` = non mesure (cadavre-AU-CHARGEMENT) -> on refuse.
        if uc.killed_this_turn is not True:
            continue
        # `AreEqual(Killer(it), sel@0x40)` -- 4e conjoint natif, PORTE (cf. docstring).
        # `UnitKillerSelector$$Select` ne retient un tueur que si `KillerId != 0` ; cote port,
        # `death_source is None` (jamais tuee dans ce run) et `death_source[0] is None` (tueur
        # inconnu) sont les deux formes de ce zero.
        ds = uc.death_source
        if ds is None or ds[0] is None or int(ds[0]) != int(stepper_id):
            continue
        # Le substrat de traits exige un `StatsComponent` ; un cadavre-AU-CHARGEMENT n'en a pas,
        # mais il est deja sorti par les deux conjoints ci-dessus.
        sc = e.get_component(StatsComponent)
        if sc is None:
            continue
        # Substrat de traits = le foyer `entity_trait_names` (#264/#226), plus la lecture brute
        # de `ctx.traits` : cf.
        # `docs/rl/case-462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-substrat-traits-inventaire.md`.
        traits = entity_trait_names(sc.ctx, uc.visual_id)
        if not has_trait(traits, DECOY_TRAIT):        # HasTrait(decoy, Decoy=1053)
            continue
        oc = e.get_component(OwnerComponent)
        if oc is None or oc.team != o_team:           # AreFriends(owner, decoy)
            continue
        pc = e.get_component(PositionComponent)
        if pc is None or (pc.col, pc.row) != spos:    # Contains(Tiles(stepper), MainTileOfUnits(it))
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
    """`DecoysAndMisdirection_DamageEnemiesAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_DamageEnemiesAbility$$CreateTrigger, IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_DamageEnemiesAbility$$CreateBehaviour).
    Un ENNEMI (de l'owner Isaak) qui MOVE sur un decoy allie crushe -> `Repeat(Blast sur le stepper,
    count=nb decoys morts valides)`. On(0x1d). Blast = leaf `AttackWithAttackDamage` (pipeline crit/block, config
    MinMaxDamage 1455-1746@L65, nrOfHits=1, profil Blast) sur le stepper (`ev.actor_id`)."""
    event_id = int(EventTriggerType.UnitPositionChanged_2)   # 29 (0x1d)

    def matches(self, state, ev):
        return (_are_enemies(state, self.owner_id, ev.actor_id)
                and len(_valid_dead_decoys(state, self.owner_id, ev.actor_id)) > 0)

    def execute_behaviour(self, state, ev):
        stepper = ev.actor_id
        n = len(_valid_dead_decoys(state, self.owner_id, stepper))
        blasts = []
        for _ in range(n):                            # Repeat( ... , Count(GetValidDeadDecoys) )
            ectx = ExecutionContext(state=state, rng=state.rng)
            AttackWithAttackDamage(Target(), ABILITY_ID, BLAST_PROFILE, is_melee=False,
                                   native_factory="ability").execute(   # IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_DamageEnemiesAbility$$CreateBehaviour+0x11f -> IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage = AbilityDamageOperation
                entities_from_state(state, self.owner_id, stepper), ectx)
            atk = next((p for nm, p in ectx.emitted if nm == "AttackWithAttackDamage"), None)
            blasts.append(atk)
        return {"ability": "DecoysAndMisdirection_DamageEnemies", "owner": self.owner_id,
                "target": stepper, "count": n, "blasts": blasts}


class DecoysAndMisdirectionBuffFriendsAbility(TriggeredAbility):
    """`DecoysAndMisdirection_BuffFriendsAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_BuffFriendsAbility$$CreateTrigger, IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_BuffFriendsAbility$$CreateBehaviour).
    Un ALLIE (de l'owner Isaak) qui MOVE/RESURRECT sur un decoy allie crushe -> `AddEffect(1379
    DecoysAndMisdirection_ExtraDamage +582, on=stepper)` (jusqu'a fin de son tour, `remaining_turns=1`) +
    `If(HasFaction(stepper, GenestealerCults), spawn_decoy(hex adjacent libre du stepper, ForSteppable))`.
    On(0x2e = UnitResurrected)|On(0x1d).

    ⚠ Le path RESURRECT (On(0x2e = UnitResurrected)) fire aussi ce trigger MAIS aucun vecteur resurrect n'est encore porte
    (G3-Ambush) -> en pratique seul le path MOVE (On(0x1d)) le declenche aujourd'hui."""
    event_id = int(EventTriggerType.UnitPositionChanged_2)   # 29 (0x1d, move)
    event_ids = (int(EventTriggerType.UnitResurrected),      # 47 (0x2f, resurrect -> G3)
                 int(EventTriggerType.UnitPositionChanged_2))  # 29 (0x1d, move)

    def matches(self, state, ev):
        return (_are_friends(state, self.owner_id, ev.actor_id)
                and len(_valid_dead_decoys(state, self.owner_id, ev.actor_id)) > 0)

    def execute_behaviour(self, state, ev):
        stepper = ev.actor_id
        # AddEffect(1379) sur le stepper : l'effet DecoysAndMisdirectionExtraDamageEffect lit extraDmg AU
        # QUERY-TIME depuis le niveau/mult PORTÉS -> on les initialise depuis le SOURCE (owner Isaak) après la
        # pose (docstring effet : "niveau/multiplier = ceux du SOURCE genesPrimus"). remaining_turns=1 (fin de
        # tour). AddEffectOperation no-op si un même-type est déjà présent sur le stepper (refresh-équivalent).
        eff = AddEffectOperation.execute(state, self.owner_id, stepper, DECOYS_EXTRA_DMG,
                                         name="DecoysAndMisdirection_ExtraDamage",
                                         duration_override=1)   # duree = df@0xc0 = Direct(1) (IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_BuffFriendsAbility$$CreateBehaviour) : deja en TOURS, pas de conversion (#98)
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
#   - `Ambush_SummonAbility`      (IdunBattleLogic.Entities.Abilities.Triggered.Loki.Ambush_SummonAbility$$CreateTrigger, IdunBattleLogic.Entities.Abilities.Triggered.Loki.Ambush_SummonAbility$$GetSummonBehaviour) : mort -> decoy.
#   - `EnvAmbushResurrectAbility`  (IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnvAmbushResurrectAbility$$CreateTrigger, IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnvAmbushResurrectAbility$$CreateBehaviour)   : resurrection.
# La feuille DSL `IdunBattleLogic.Entities.DSLBehaviors$$Resurrect appelle l'Operation imperative `ResurrectUnitOperation.Execute
# IdunBattle.Operations.ResurrectUnitOperation$$Execute` (../resurrect.py) qui pose le flag one-shot 0xe + crushe le decoy + emet On(UnitResurrected=46).
# RE ghidra gqfc5mff6c ; doc docs/rl/genestealer-cults.md (verdict G3).
# =====================================================================================================

def _free_tile_or_adjacent(state: State, coord):
    """`First(FreeTilesOrAdjacentFreeTiles(Tiles(target), <DSLTriggers>+0x40))` (collapse S) : la
    tuile de `coord` si LIBRE (aucun vivant) et marchable, sinon la 1re tuile libre marchable
    ADJACENTE (hex, ordre id croissant = First). Renvoie un id de tuile (arg `spawn_decoy`) ou None.
    Le porteur mourant etant alive=False, sa PROPRE tuile est 'libre' -> le decoy se pose sur la
    tuile du mort.

    ⚠ **PAS DE BRANCHE `allowSteppable` ICI, ET C'EST FIDELE** (#955-r2, ferme EN REFUS). Le noeud
    natif a DEUX surcharges : celle a 3 arguments -- la seule qu'atteignent les DEUX call-sites de
    cette fonction (`Ambush_SummonAbility$$GetSummonBehaviour` et
    `HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour`) -- recoit son trigger de
    l'APPELANT, et les deux passent `<DSLTriggers>+0x40`, LU aux octets (`mov r8, [reg+0x40]`).
    `DSLTriggers$$.ctor` pose `+0x40` = le trigger NU (`ShouldTrigger` toujours VRAI) et `+0x48` =
    `op_LogicalNot(<le meme type>)` ; `CanAddUnitTileSelector$$Select` INVERSE ce qu'il recoit
    (`allowSteppable = !ShouldTrigger`). Donc ici `allowSteppable` est **FAUX** : une tuile occupee
    par un `Steppable` est OCCUPEE. Seule `PossessionAbility` -- qui passe par la surcharge a DEUX
    arguments, laquelle lit `+0x48` -- porte `allow_steppable=True`. Garde :
    `tests/engine/runner/test_955r2_free_tiles_steppable_offline.py`."""
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
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnvAmbushResurrectAbility$$GetValidDecoys` (collapse S) : decoys VIVANTS (trait Decoy 1053) du joueur `player`, sur
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
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnvAmbushResurrectAbility$$GetUnitsEligibleForResurrect` (collapse S) : unites MORTES du joueur `player` portant le
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
    """`Ambush_SummonAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.Ambush_SummonAbility$$CreateTrigger, IdunBattleLogic.Entities.Abilities.Triggered.Loki.Ambush_SummonAbility$$GetSummonBehaviour). A la MORT d'un porteur
    Ambush : `On(UnitDefeated=54) & OwnerIsTarget & Not(HasFlag(owner, 0xe))` -> pose 1 decoy genesSmnDecoy sur
    la tuile du mort (sinon adjacente libre), ForSteppable (feuille Spawn = G1). ENREGISTRE aussi `turn_defeated`
    (base du delai de resurrection).

    `fire_on_death` : l'owner EST l'unite morte (alive=False). CONFRONTE au build (#10015) --
    `Ambush_SummonAbility` SURCHARGE `get_AllowForDeadOwner` (`ITriggeredAbility` slot 8) et son corps
    rend VRAI (`b0 01 c3`). Accord port/natif."""
    event_id = int(EventTriggerType.UnitDefeated)         # 54 (0x36) -- litteral re-derive en #301
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
        u = self.owner_id
        e = state.get_entity(u)
        uc = e.get_component(UnitComponent) if e is not None else None
        # ⚠ **LA COMPENSATION `turn_defeated` EST RETIREE ICI (#10015-r3) -- SON ECRIVAIN NATIF EST
        # DESORMAIS SUR LE CHEMIN.** Elle etait gardee au motif que
        # `IdunBattle.Operations.KillUnitOperation$$Execute` << n'appelle jamais `IOperationProcessor`
        # slot 6 = `RemoveUnit` (ses appels sont 77/80/85/99/130/143) >>. **CETTE PREMISSE EST
        # FAUSSE** : il l'appelle a `KillUnitOperation$$Execute+0xd34`, par la forme WALK D'ITABLE
        # (slot en TROISIEME argument), que le recensement des seuls appels de la forme DISPATCHER
        # ne pouvait pas voir. Mesure, contre-exemples et offsets : en-tete de
        # `runner/operations/remove_unit.py`.
        # Le port appelle donc `RemoveUnitOperation` depuis `_kill_unit_operation`, et cette
        # Operation ecrit `TurnDefeated` a l'etape 10 -- a `+0xd34`, donc AVANT l'`On(0x36 =
        # UnitDefeated)` de `+0xeac` qui amene ici. La valeur est deja posee quand ce behaviour
        # s'execute, et c'est le MIRROR : `Ambush_SummonAbility$$GetSummonBehaviour` n'ecrit rien
        # de tel. On la RELIT pour la trace, on ne la REECRIT plus.
        tile = _free_tile_or_adjacent(state, _pos_of(state, u))     # FreeTilesOrAdjacentFreeTiles(Tiles(target))
        did = spawn_decoy(state, tile, u) if tile is not None else None
        return {"ability": "Ambush_Summon", "owner": u, "decoy": did,
                "turn_defeated": (uc.turn_defeated if uc is not None else None)}


class EnvAmbushResurrectAbility(TriggeredAbility):
    """`EnvAmbushResurrectAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnvAmbushResurrectAbility$$CreateTrigger, IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnvAmbushResurrectAbility$$CreateBehaviour). Au DEBUT du tour du
    joueur courant : `On(TurnStart_Actions=22) & AmountIsGreaterThanZero(GetValidDecoys) &
    AmountIsGreaterThanZero(GetUnitsEligibleForResurrect)` -> ressuscite chaque porteur Ambush eligible (mort
    au tour precedent, non deja ressuscite) sur un decoy allie ALEATOIRE, PV pleins, TOUR IMMEDIAT. Ordre
    CHARACTER-FIRST (Hero avant non-Hero, `SortByFormula(HasTrait Hero)`).

    `fire_on_death` : l'owner (porteur Ambush) est en general MORT quand il ressuscite. Le behaviour est GLOBAL
    (enumere TOUS les eligibles) -> IDEMPOTENT via le flag 0xe : la 1re instance a fire ressuscite tout le
    monde (pose 0xe sur chacun), les instances suivantes trouvent `_eligible_for_resurrect` vide (matches False).

    ⚠ **ET C'EST UN DESACCORD MESURE AVEC LE BUILD -- #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r2-r1
    RE-ENONCE.** La fiche du residu affirmait << elle est ATOMIQUE, donc dispensee du gate `IsAlive`
    de `CanGetAbilityTrigger` >>. **FAUX** : `EnvAmbushResurrectAbility` ne declare PAS
    `get_AllowForDeadOwner` (sa table de methodes ne porte que `CreateTrigger`, `CreateBehaviour`,
    `GetValidDecoys`, `GetUnitsEligibleForResurrect`, `GetIsAlliedWithCurrentPlayerUnitTrigger`,
    `GetIsCurrentPlayerUnitTrigger`, `.ctor`), donc elle HERITE celui de `BaseTriggeredAbility`, dont
    le corps rend **FAUX** (`32 c0 c3`). Si son owner natif etait une UNITE, un porteur mort serait
    donc gate DEHORS -- l'inverse exact de ce que la fiche disait.

    L'attribut est GARDE malgre ce desaccord, et la raison est nommee : `Env*Ability` est une famille
    de **25** classes d'environnement, et le port les attache a la seule voie qu'il connaisse (le
    trait `Ambush`). Si l'owner natif n'est PAS une unite -- ce que `EnvAmbushResurrectAbility$$
    CreateTrigger` laisse ouvert, son arbre ne portant AUCUN predicat d'owner --, alors
    `IsUnit(owner)` est faux et les DEUX gates de `CanGetAbilityTrigger` sont sautes : le natif fire,
    et `fire_on_death = True` est la bonne compensation. Le retirer sur la seule foi d'une valeur
    heritee alignerait le code sur une premisse NON ETABLIE (l'identite de l'owner), exactement le
    vice que #1045-r2 documente. Ce qui reste a trancher est donc l'OWNER, pas l'atomicite."""
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
            # `heal_type = 2` : le LITTERAL du `Resurrect(...)` d'
            # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnvAmbushResurrectAbility$$CreateBehaviour`
            # (5e argument de `IdunBattleLogic.Entities.DSLBehaviors$$Resurrect`), relu au decompile
            # avec le gate `CanBeResurrected` de #564. C'est le `HealType` « aucun filtre » --
            # `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType` ne branche que sur 0 et 1,
            # donc 2 laisse passer mecaniques ET non-mecaniques. Ecrit EXPLICITEMENT : le defaut de
            # l'Operation (0) restreindrait Ambush aux non-mecaniques, ce que le natif ne fait pas.
            r = ResurrectUnitOperation.execute(state, unit, dest, _max_health(state, unit),
                                               immediate_turn=True, heal_type=2)
            if r is not None:
                out.append(r)
        return {"ability": "EnvAmbushResurrect", "player": player, "resurrections": out} if out else None


# =====================================================================================================
# G6b — HypersensoryAbilities MoveAndSpawnDecoy (passif de Judh genesKelermorph, seconde moitie du passif)
#
# Namespace natif `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy`.
# IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateTrigger, IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour, IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$GetTilePriority. RE ghidra gqfc5mff6c
# (verdict re-expert #16). i2 : « After the attack [1re du tour ennemi], she moves to a free adjacent hex and
# places a decoy on the hex she moved from. Then, if she is within 2 hexes of the unit that attacked her, she
# deals 3x <MinMax> Projectile Damage to that unit. » Reutilise le compteur d'attaques recues de G6a.
#
# TRIGGER IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateTrigger (arbre PROUVE, tous op_BitwiseAnd) :
#     On(9=Attack) BRUT & OwnerOrOwnerTileIsTarget(owner) & IsEnemyTurn(owner)
#       & Not(HasEffect(owner, 0x57f=1407))                                      # flag once/turn
#       & Not(HasBeenAttackedAmountThisTurnIsEqualOrGreater(owner, seuil=Direct(2)))   # SEUIL = 2 (pas 1)
#   `On(9)` est emis par `FinishAttackOperation IdunBattle.Operations.FinishAttackOperation$$Execute` pour TOUTE attaque (normale ET ability) -> le
#   dispatch `after_hit_normal_attack` l'emet desormais aussi (dispatch.py) => Judh reagit a n'importe quelle
#   attaque la ciblant. Le seuil 2 (et non 1 comme le HP-floor G6a) : au moment ou On(9) fire, le compteur
#   vaut deja 1 (record_attacked l'a incremente AVANT le vecteur after-hit) -> Not(1>=2)=True a la 1re attaque ;
#   la 2e (compteur=2, + flag pose) est bloquee.
#
# BEHAVIOUR IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour (ordre PROUVE) : (1) MOVE vers la meilleure tuile adjacente libre (GetTilePriority) ->
#   (2) DECOY sur PreviousTile (la tuile QUITTEE) -> (3) CONTRE-ATTAQUE gatee IsInRange(range) & IsAlive x2 &
#   Not(IsObscured) -> (4) AddEffect(0x57f=1407) EN DERNIER (flag once/turn). Le compteur n'est ni lu ni
#   incremente ici (maintenu par le pipeline d'attaque).
#
# IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$GetTilePriority (PROUVE, tri ASCENDANT + First -> plus bas = meilleur) :
#     prio = If( AmountIsEqual(MinDistance(tile, attaquant), Direct(range)) & Not(IsObscured(tile, attaquant)),
#                Direct(0),
#                If( IsSurrounding(tile, attaquant, radius 1), Direct(1), Direct(2) ) )
#   => prefere une tuile a EXACTEMENT `range` (=2) hex de l'attaquant et non obscurcie (prio 0), sinon une
#   tuile adjacente a l'attaquant (prio 1), sinon n'importe laquelle (prio 2). `Not(IsObscured)` / `Unobscured`
#   = passe-tout v1 (LoS absente offline, cf. battle_query). `MoveUnit` options NULL -> position + KillSteppable
#   inline SANS vecteur after-move overwatch (== leaf DSL MoveUnit, cf. task #4 / G5).
# =====================================================================================================

HYPERSENSORY_ABILITY = "HypersensoryAbilities"
HYPERSENSORY_HASBEENATTACKED = int(EffectType.HypersensoryAbilities_HasBeenAttacked)   # 1407 (0x57f) flag once/turn
HYPERSENSORY_ATTACK_CAP = 2            # Not(HasBeenAttackedAmountThisTurn >= 2), seuil @0xc8 = Direct(2)
HYPERSENSORY_MOVE_RANGE = 1            # MovableTilesInRange(self, Direct(1)) = hex adjacent (i2 « free adjacent hex »)
HYPERSENSORY_SURROUND_RADIUS = 1       # IsSurrounding(tile, attaquant, radius 1) dans GetTilePriority
PROJECTILE_PROFILE = "Projectile"      # profil de la contre-attaque (PiercingRatio 15)


def _living_occupants_map(state: State) -> dict:
    """`{tile_id -> team}` des unites VIVANTES (occupation lue par le pathfinder `MovableTilesInRange`).
    board None -> {}. (Meme collapse que abilities/genestealer.py, cote triggers.)"""
    board = state.board
    if board is None:
        return {}
    occ: dict = {}
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if pc is None or oc is None or (uc is not None and not uc.alive):
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None:
            occ[t] = oc.team
    return occ


def _hypersensory_move_dest(state: State, judh_id: int, attacker_id: int, cfg_range: int):
    """`First(SortByFormula(Randomize(MovableTilesInRange(self, Direct(1))), IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$GetTilePriority))` :
    la MEILLEURE tuile LIBRE adjacente (portee de move 1) atteignable par Judh, triee par GetTilePriority.
    Priorite (ASC, plus bas = mieux) : 0 si dist(tile, attaquant)==cfg_range & Not(IsObscured) ; 1 si la tuile
    entoure l'attaquant (radius 1) ; 2 sinon. Le `Randomize` (tie-break PRNG amont) COLLAPSE en tri
    deterministe (id de tuile croissant) -> First. Renvoie (col,row) ou None si aucune tuile libre atteignable.
    `Not(IsObscured)` = passe-tout v1 (LoS absente offline).

    `#381-r4` -- POURQUOI CE COLLAPSE N'APPELLE PAS LE FOYER `get_movable_tiles_for`
    ------------------------------------------------------------------------------
    Ses deux freres (`abilities/genestealer._charge_candidate_tiles`,
    `triggers/loki/betrayer._betrayer_stop_tile`) y passent depuis `#381-r4` pour recevoir le gate
    d'expansion #131 et le dispatch fly. Ici les DEUX etages sont INERTES, et c'est MESURE :

      * le gate est STRUCTURELLEMENT inerte a portee 1. `overrideRange` est le champ `+0x20` de
        `IdunBattleLogic.Entities.DSLFormulas` = la formule partagee `Direct(1)` que son `.ctor`
        alloue (`+0x18`=0, `+0x20`=1, `+0x28`=2, `+0x30`=100, `+0x38`=-1), et
        `BasePathfinder$$NodesInNextLevel` teste `currentTile != startTile` AVANT
        `IsValidContinuePathTile` : au seul niveau de BFS parcouru, la seule tuile qui s'etend EST
        le start, donc le predicat n'est jamais consulte. CONFRONTE au balayage :
        `probe_381r4_imperative_collapses.py --site hypersensory`, boards `C2_26` et `EMC2_02`
        (les deux plus bloquants du dump), **2960 configurations (Judh, attaquant), 0 difference** ;
      * le dispatch `IsLikeFlying` : AUCUN des 5 porteurs de `HypersensoryAbilities`
        (`genesKelermorph` + 4 variantes npc) ne porte `Flying` ni `Burrow`.

    Le brancher serait un no-op non mesurable ; il est donc laisse tel quel, et la garde
    `tests/engine/runner/test_381r4_imperative_collapses_offline.py` ROUGIT si
    `HYPERSENSORY_MOVE_RANGE` cesse de valoir 1 (la premisse de l'inertie)."""
    board = state.board
    jpos = _pos_of(state, judh_id)
    apos = _pos_of(state, attacker_id)
    if board is None or jpos is None or apos is None:
        return None
    jtile = board.id_at(jpos[0], jpos[1])
    if jtile is None:
        return None
    _visited, stop = get_movable_positions(board, jtile, HYPERSENSORY_MOVE_RANGE,
                                           _living_occupants_map(state), _team_of(state, judh_id))
    cands = [t for t in stop if t != jtile]                 # tuiles libres atteignables (hors tuile courante)
    if not cands:
        return None

    def _prio(t):
        d = hexgeo.distance(board.coord(t), apos)
        if d == cfg_range:                                  # AmountIsEqual(MinDistance, Direct(range)) & Not(IsObscured)
            return 0
        if d <= HYPERSENSORY_SURROUND_RADIUS:               # IsSurrounding(tile, attaquant, radius 1)
            return 1
        return 2

    cands.sort(key=lambda t: (_prio(t), t))                 # tri ASC + First ; Randomize collapse -> id-order
    return board.coord(cands[0])


class HypersensoryMoveAndSpawnDecoyAbility(TriggeredAbility):
    """`HypersensoryAbilitiesAbility_MoveAndSpawnDecoy` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateTrigger, IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour,
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$GetTilePriority). A la 1re attaque de chaque tour ennemi qui cible Judh : elle se deplace vers un
    hex adjacent libre (le plus loin de l'attaquant), pose un decoy sur la tuile QUITTEE, et si l'attaquant est
    a <= `range` hex contre-attaque 3x Projectile. `On(9=Attack)` BRUT (emis par FinishAttackOperation pour
    TOUTE attaque) & OwnerOrOwnerTileIsTarget & IsEnemyTurn & Not(HasEffect 1407) & Not(HasBeenAttacked>=2)."""
    event_id = int(EventTriggerType.Attack)          # 9 (BRUT, generique)

    def matches(self, state, ev):
        if self.owner_id != ev.target_id:                        # OwnerOrOwnerTileIsTarget (Judh = cible)
            return False
        if not _are_enemies(state, self.owner_id, ev.actor_id):  # IsEnemyTurn(owner) : attaquant = ennemi (tour courant)
            return False
        if state.effects is not None and state.effects.has_effect(   # Not(HasEffect 0x57f=1407) flag once/turn
                self.owner_id, effect_type=HYPERSENSORY_HASBEENATTACKED):
            return False
        e = state.get_entity(self.owner_id)
        uc = e.get_component(UnitComponent) if e is not None else None
        if uc is not None and uc.times_attacked_this_turn >= HYPERSENSORY_ATTACK_CAP:   # Not(HasBeenAttacked>=2)
            return False
        return True

    def execute_behaviour(self, state, ev):
        judh, attacker = self.owner_id, ev.actor_id
        cfg_range = int(ability_var(HYPERSENSORY_ABILITY, "range", is_constant=True) or 2)   # GetNumberConstant(0x16)
        # (1) MOVE : dest = meilleure tuile adjacente libre (GetTilePriority). PreviousTile = tuile QUITTEE.
        prev_pos = _pos_of(state, judh)
        dest = _hypersensory_move_dest(state, judh, attacker, cfg_range)
        moved = False
        if dest is not None:                                     # gate AmountIsGreaterThanZero(dest) & CanMove
            # `...MoveAndSpawnDecoy$$CreateBehaviour` est l'un des 30 call-sites de
            # `IdunBattleLogic.Entities.DSLBehaviors$$MoveUnit` (xrefs exhaustives) : ce move passe
            # donc par `MoveUnitOperation$$Execute`, qui JOUE le vecteur after-move -- la mention
            # « PAS after-move » portee ici est REFUTEE (#448-r1-r1-r2-r1). `arrive_at_final_tile`
            # suit le defaut de feuille DSL (octet `MoveUnitOptions+0x10` = 1 sur selecteur nul).
            MoveUnitOperation(judh, dest,
                              arrive_at_final_tile=False).execute(state, EventBus())
            moved = True
        # (2) DECOY sur PreviousTile (la tuile quittee, desormais libre) : Spawn(genesSmnDecoy, ForSteppable).
        decoy = None
        if moved and prev_pos is not None:
            prev_tile = _free_tile_or_adjacent(state, prev_pos)   # First(FreeTilesOrAdjacentFreeTiles(PreviousTile))
            if prev_tile is not None:
                decoy = spawn_decoy(state, prev_tile, judh)
        # (3) CONTRE-ATTAQUE : gate IsInRange(judh, attaquant, cfg_range) & IsAlive x2 & Not(IsObscured passe-tout).
        counter = None
        if self._counter_gate(state, judh, attacker, cfg_range):
            counter = self._counter_attack(state, judh, attacker)
        # (4) FLAG once/turn (0x57f=1407) pose EN DERNIER (op_BitwiseAnd final du behaviour). Retire au
        # prochain start_turn (reset_times_attacked) -> la reaction se re-arme chaque tour ennemi.
        AddEffectOperation.execute(state, judh, judh, HYPERSENSORY_HASBEENATTACKED,
                                   name="HypersensoryAbilities_HasBeenAttacked",
                                   duration_override=1)   # duree = df@0xc0 = Direct(1) (IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour) : deja en TOURS (#98)
        return {"ability": "HypersensoryAbilities_MoveAndSpawnDecoy", "owner": judh, "attacker": attacker,
                "moved_to": dest, "decoy": decoy, "counter": counter}

    def _counter_gate(self, state, judh, attacker, cfg_range) -> bool:
        """`IsInRange(judh, attaquant, GetNumberConstant(0x16)) & IsAlive(attaquant) & IsAlive(judh) &
        Not(IsObscured(judh, attaquant))` (passe-tout v1). `IsInRange` = dist hex <= cfg_range."""
        je, ae = state.get_entity(judh), state.get_entity(attacker)
        ju = je.get_component(UnitComponent) if je is not None else None
        au = ae.get_component(UnitComponent) if ae is not None else None
        if ju is None or not ju.alive or au is None or not au.alive:
            return False
        jpos, apos = _pos_of(state, judh), _pos_of(state, attacker)
        if jpos is None or apos is None:
            return False
        return hexgeo.distance(jpos, apos) <= cfg_range

    def _counter_attack(self, state, judh, attacker):
        """`AttackWithAttackDamage(judh, attaquant, MinMaxDamage(minDmg/maxDmg[niveau PASSIF]), Projectile,
        hits=GetNumberConstant(0x2f=nrOfHits))` -> `execute_ability_attack`. Le degat scale au niveau PASSIF de
        Judh (pas `active_ability_level` : c'est un PASSIF) -> `ability_var(..., passive_ability_level)`. Pierce
        du profil Projectile (15) + ExtraPierce du caster (profile_pierce)."""
        e = state.get_entity(judh)
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = sc.ctx if sc is not None else None
        if ctx is None:
            return None
        lvl = ctx.passive_ability_level
        mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
        bmin = int(ability_var(HYPERSENSORY_ABILITY, "minDmg", lvl, multiplier_pct=mult) or 0)
        bmax = int(ability_var(HYPERSENSORY_ABILITY, "maxDmg", lvl, multiplier_pct=mult) or 0)
        hits = int(ability_var(HYPERSENSORY_ABILITY, "nrOfHits", is_constant=True) or 3)
        pierce = profile_pierce(ctx, PROJECTILE_PROFILE, ranged=True)
        return AttackDamageOperation.execute_ability_attack(
            state, judh, attacker, bmin, bmax, pierce, hits,
            damage_profile=PROJECTILE_PROFILE, is_melee=False)

