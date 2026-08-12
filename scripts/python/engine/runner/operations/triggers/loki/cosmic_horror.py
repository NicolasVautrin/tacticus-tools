"""`Abilities.Triggered.Loki.CosmicHorror_*` — passif `CosmicHorror` du Patermine
(`genesPatriarch.passiveAbilities=['CosmicHorror']`, HERO Genestealers du pool). Le passif est
materialise par DEUX abilities-triggers NATIVES DISTINCTES (2 entrees d'`AbilityAndEffectCache`),
splittees par l'EVENEMENT. RE (decompile ghidra, build gqfc5mff6c) :

## Volet 1 -- `CosmicHorror_OnKillAbility` (le Patermine acheve un ennemi)

  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnKillAbility$$CreateTrigger` (conjonction `op_BitwiseAnd`) =
        On(0x36=UnitDefeated=54) & get_OwnerIsActor
          & AreEnemies(caster@0x148, target@0x178)
          & NOT HasTrait(target@0x178, 0x1b=27=Steppable)
    Le gate `NOT Steppable` est ce qui empeche le volet de re-partir sur le CRUSH d'un decoy
    (`KillUnitOperation$$Execute` emet la MEME sequence de morts pour un steppable, cf. dispatch.py
    `pre_unit_death_2_triggers` : On(1)->On(2)->On(0)->On(0x36 = UnitDefeated)->On(0x35 = PostUnitKill)).
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnKillAbility$$CreateBehaviour` (arbre lu de bas en haut) =
        unitToSpawn = GetStringConstant(config, 8=unitToSpawn)                  -> `genesSmnDecoy`
        tile   = First( Nearest( FreeTilesOrAdjacentFreeTiles(Tiles(target@0x178), @0xf8),
                                 caster@0x148 ), 1 )
        spawn  = Spawn(caster@0x148, tile, unitToSpawn, SpawnUnitOptions.ForSteppable())
        chance = ConfigVar(0x3a=58=chance, config)                              -> 60 @L65
        victims= Enemies(caster@0x148, SurroundingTiles(target@0x178, 0, 1), 3)
        body   = TriggerAbility(subject@0x180, 0x401=1025=TriggeredAbilityType.BattleFatigue, ...)
                 op_BitwiseAnd If( IsAlive(subject@0x180),
                                   AddEffect(0x429=1065=Pinned, AbilityStateReference,
                                             caster@0x148, subject@0x180, <struct duree ZERO>) )
        result = spawn op_BitwiseAnd Foreach(victims, Maybe(body, chance))
    == i2 : « Whenever the Patermine defeats an enemy, it places a decoy on the hex of that enemy.
    Other enemies surrounding the defeated unit have a 60% chance to be Suppressed for 1 round, and
    have a 60% chance to trigger Battle Fatigue a second time, if they have it. »

    ATTENTION -- DIVERGENCE PROSE vs DECOMPILE, tranchee par le DECOMPILE : l'i2 annonce DEUX chances de 60 %
    independantes ; le natif n'a qu'UN SEUL `Maybe(body, chance)` qui englobe les DEUX volets
    (BattleFatigue ET Pinned). Un ennemi rate le tirage -> il ne subit NI l'un NI l'autre ; il le
    passe -> il subit les DEUX. Un seul `next_bool` par victime.

## Volet 2 -- `CosmicHorror_OnMoveAbility` (le Patermine marche sur un decoy ami)

  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnMoveAbility$$CreateTrigger` =
        On(0x35=PostUnitKill=53, ignoreOverkill=1) & get_OwnerIsActor
          & AreFriends(caster@0x148, target@0x178)
          & HasTrait(target@0x178, 0x41d=1053=Decoy)
    L'evenement n'est PAS un evenement de mouvement malgre le nom de la classe : marcher sur un
    decoy = le CRUSHER (`IdunBattle.Operations.MoveUnitOperation$$KillSteppableUnits` ->
    `IdunBattle.Operations.KillUnitOperation$$Execute` avec `KillUnitOperationOptions$$ForSteppable`),
    et `KillUnitOperation$$Execute` termine sa sequence par `On(0x35=PostUnitKill)` {actor=le tueur =
    le mover, target=le crushe}. `OwnerIsActor` => c'est bien le PATERMINE qui doit avoir tue.

    ⚠ ET C'EST TOUT : le trigger ne porte AUCUNE gate de mouvement, aucun `NOT HasTrait(Steppable)`,
    aucun `TriggeringAbilityIsNone` -- relu nœud par nœud sur `rnca9r7q6c`. Le CRUSH n'est donc que
    la voie la plus FREQUENTE, pas la condition : le Patermine se soigne des qu'il est le TUEUR d'un
    allie `Decoy`, y compris par DEGAT (une AoE qui eclabousse son propre decoy) ou par le crush
    d'un `revive`/`resurrect`/`spiritual_leader`. Le port ne couvrait que le crush-par-move jusqu'a
    #462-r4b-r1-r1-r1-r1-c-r3-r1-r4 ; `damage.py::_kill_unit_operation` publie desormais l'event
    pour toutes les voies, a son rang natif.
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnMoveAbility$$CreateBehaviour` (feuille UNIQUE) =
        Heal( caster@0x148, caster@0x148, ConfigVar(0x1d=29=hp, config) )       -> 2910 @L65
    == i2 : « When the Patermine moves onto a decoy, it heals itself for 2910 Health. »

Enums qualifies (piege homonymie a trois faces, cf. docs/rl/passive-ability-coverage.md) :
  - `0x429=1065` = **EffectType**.Pinned (UI « Suppressed »), PAS TriggeredAbilityType 1065
    (=FleshmetalGuns) ni ActiveAbilityType 1065 (=ScythingTalons) ;
  - `0x401=1025` = **TriggeredAbilityType**.BattleFatigue, PAS EffectType 1025
    (=AvalancheOfMuscle_ExtraDamage) ni ActiveAbilityType 1025 (=SkyStrike) ;
  - `0x41d=1053` = **UnitTrait**.Decoy ; `0x1b=27` = **UnitTrait**.Steppable ;
  - `8` / `0x3a` / `0x1d` = index d'enum `IdunBattle.Configuration.AbilityConstantType.unitToSpawn` /
    `AbilityVariableType.chance` / `AbilityVariableType.hp` (verifies contre le gameconfig :
    `CosmicHorror.constants={'unitToSpawn':'genesSmnDecoy'}`, `variables.chance[64]=60`,
    `variables.hp[64]=2910` -- exactement les nombres de l'i2).

DOCTRINE #149 : les predicats/selecteurs des DEUX triggers sont COLLAPSES imperativement (lecture
d'etat : OwnerIsActor, AreEnemies/AreFriends, HasTrait) ; les FEUILLES delegent aux Operations deja
portees -- `AddEffect(Pinned)` par l'arbre DSL `cosmic_horror_pin_tree()` (meme feuille que
SuppressiveFire), `Heal` par l'arbre `cosmic_horror_heal_tree()`, `Spawn(ForSteppable)` par
`spawn_decoy` (primitive G1). Les selecteurs S manquants au vocabulaire DSL du port
(`FreeTilesOrAdjacentFreeTiles`, `Nearest`, `SurroundingTiles`+`Enemies` compose, `TriggerAbility`)
sont collapses ici, comme le fait deja `triggers/genestealer.py` pour la meme famille de selecteurs.

DISPATCH :
  - volet 1 -> vecteur EXISTANT `unit_defeated_triggers` (`On(0x36 = UnitDefeated)`, emis par `damage.py` apres
    `after_death_triggers`) : aucun cablage neuf ;
  - volet 2 -> vecteur `post_unit_kill_triggers` (`On(0x35 = PostUnitKill)`), emis par le FOYER
    `damage.py::_kill_unit_operation` a son rang natif (@`KillUnitOperation$$Execute+0x10ac`), donc
    pour TOUTES les voies de mort. Il l'etait auparavant en tete d'`after_move_triggers`, pour le
    seul crush-par-move et APRES `UpdateCharging`/`SetMovedFlag` -- double ecart d'ORDRE et de
    COUVERTURE, ferme par #462-r4b-r1-r1-r1-r1-c-r3-r1-r4.

RESIDUS (honnetes) :
  - le blast radius de ce volet est desormais celui de TOUTE mort ou le Patermine est le tueur.
    Le cas le plus visible, et il est NATIF : un decoy ALLIE tue par une AoE du Patermine le
    soigne aussi -- le trigger ne distingue pas la voie. Cote port, la mort par degat n'a pas
    d'AoE friendly-fire au catalogue du Patermine (`Eviscerate`, 5 coups melee) ; les voies
    reellement ouvertes sont les QUATRE crushs (`move`, `revive`, `resurrect`, `spiritual_leader`).
  - `variables.extraDmg` de `CosmicHorror` n'est lue par AUCUN des deux `CreateBehaviour` decompiles
    (ni par un 3e symbole `CosmicHorror*` -- la recherche par nom n'en rend que 2 + le playbook + les
    visuals). Non portee, non inventee.
  - `CosmicHorrorPlaybook` (`CalculateAttackUtilityInStepsInternal` / `...MovementUtility...`) = face
    DECISION (l'IA cherche a achever pour poser un decoy / a marcher sur ses decoys) : hors perimetre.
"""
from __future__ import annotations

from typing import Optional

import hexgeo

from ....state import State
from ....components import (OwnerComponent, UnitComponent, PositionComponent, StatsComponent)
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from ....abilities.behaviours.stats import Heal
from .....entities.traits.unit_trait import UnitTrait, has_trait
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.selectors.accessors import Target
from .....entities.selectors.tiles import Caster
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent
from ...spawn import spawn_decoy

ABILITY_ID = "CosmicHorror"
DECOY_UNIT_KEY = "unitToSpawn"                     # AbilityConstantType 8 (GetStringConstant(config, 8))
DECOY_TRAIT = UnitTrait.Decoy                      # 0x41d = 1053
STEPPABLE_TRAIT = UnitTrait.Steppable              # 0x1b  = 27
FATIGUE_TRAIT = UnitTrait.BattleFatigue            # 1015 -> derive la triggered 1025 re-declenchee
PINNED = int(EffectType.Pinned)                    # 0x429 = 1065 (UI « Suppressed »)
SURROUND_RADIUS = 1                                # SurroundingTiles(target@0x178, 0, 1) = anneau adjacent

_ON_KILL = int(EventTriggerType.UnitDefeated)      # 0x36 = 54 — volet 1
_ON_CRUSH = int(EventTriggerType.PostUnitKill)     # 0x35 = 53 — volet 2
# (Les deux commentaires portaient `0x37 = 55` / `0x36 = 54`, hex FAUX pour les valeurs justes que
# les membres d'enum rendent — meme glissement d'un cran que celui corrige en #301 dans
# `pre_unit_death_2_triggers`. Les LITTERAUX, eux, n'ont jamais ete ecrits : le port lit l'enum.)


# ----- selecteurs S collapses (AreEnemies/AreFriends, tuile de pose, victimes de l'anneau) -----

def _team_of(state: State, uid) -> Optional[int]:
    e = state.get_entity(uid) if uid is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _traits_of(state: State, uid) -> list:
    e = state.get_entity(uid) if uid is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    return list(getattr(sc.ctx, "traits", None) or []) if sc is not None else []


def _pos_of(state: State, uid):
    e = state.get_entity(uid) if uid is not None else None
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _occupied(state: State) -> set:
    """Positions des occupants VIVANTS (une unite morte ne bloque plus sa tuile)."""
    occ = set()
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None or (uc is not None and not uc.alive):
            continue
        occ.add((pc.col, pc.row))
    return occ


def _decoy_tile_for_kill(state: State, dying_id: int, caster_id: int):
    """`First( Nearest( FreeTilesOrAdjacentFreeTiles(Tiles(target@0x178), @0xf8), caster@0x148 ), 1 )`
    (collapse S) -> id de tuile ou None.

    `FreeTilesOrAdjacentFreeTiles` : la tuile de la victime SI libre et marchable, SINON les tuiles
    hex-adjacentes libres et marchables (meme collapse que `triggers/genestealer.py::
    _free_tile_or_adjacent`, deja porte pour `Ambush_SummonAbility`). La victime etant `alive=False`
    au dispatch de `On(0x36 = UnitDefeated)`, sa propre tuile est « libre » -> cas nominal = « places a decoy on the
    hex of that enemy ».

    `Nearest(..., caster)` = tri ASCENDANT par distance hex au Patermine, LINQ donc STABLE (ex aequo
    departages par l'ordre source = ids de tuile croissants) ; `First` prend la tete. Sur le cas
    nominal l'ensemble est un singleton -> `Nearest` est l'identite.

    ⚠ **PAS DE BRANCHE `allowSteppable`, ET C'EST FIDELE** (#955-r2, ferme EN REFUS). Le `@0xf8` de
    la signature ci-dessus est `<DSLTriggers>+0x40` -- LU aux octets du call-site
    (`CosmicHorror_OnKillAbility$$CreateBehaviour` : `mov r8, [reg+0x40]`), et c'est le trigger NU.
    `CanAddUnitTileSelector$$Select` INVERSE (`allowSteppable = !ShouldTrigger`), donc ici
    `allowSteppable` est **FAUX** : une tuile occupee par un `Steppable` est OCCUPEE. Le `+0x48`
    voisin, lui, est `op_LogicalNot(<le meme type>)` et donne l'inverse -- c'est le trigger que la
    surcharge a DEUX arguments lit dans son propre corps, pour `PossessionAbility` seule. Garde :
    `tests/engine/runner/test_955r2_free_tiles_steppable_offline.py`."""
    board = state.board
    coord = _pos_of(state, dying_id)
    cpos = _pos_of(state, caster_id)
    if board is None or coord is None:
        return None
    occ = _occupied(state)
    center = (int(coord[0]), int(coord[1]))
    cands: list = []
    if center not in occ:                                   # FreeTiles(Tiles(target))
        t = board.id_at(center[0], center[1])
        if t is not None and board.walkable(t):
            cands.append(t)
    if not cands:                                           # ... Or AdjacentFreeTiles
        for (c, r) in hexgeo.disk(center[0], center[1], 1):
            if (c, r) == center or (c, r) in occ:
                continue
            t = board.id_at(c, r)
            if t is not None and board.walkable(t):
                cands.append(t)
    if not cands:
        return None
    cands.sort()                                            # ordre SOURCE (ids croissants)
    if cpos is not None:                                    # Nearest(caster) : tri stable par distance
        cands.sort(key=lambda t: hexgeo.distance((cpos[0], cpos[1]), board.coord(t)))
    return cands[0]                                         # First(., 1)


def _surrounding_enemies(state: State, caster_id: int, dying_id: int) -> list:
    """`Enemies(caster@0x148, SurroundingTiles(target@0x178, 0, 1), 3)` (collapse S) : les unites
    VIVANTES ennemies du Patermine occupant l'anneau hex de rayon 1 autour de la tuile de la VICTIME
    (« Other enemies surrounding the defeated unit »). La victime elle-meme est exclue (elle est
    morte) ; le decoy qu'on vient de poser est un ALLIE -> hors `Enemies`. Ordre = ids d'entite
    croissants (l'ordre d'enumeration natif des tuiles de l'anneau n'est pas observable ici ; sans
    incidence : le `Foreach` applique le meme corps a chaque victime, un tirage RNG chacune -- seul
    l'ORDRE DE CONSOMMATION du PRNG en depend, cf. RESIDUS de l'en-tete de module)."""
    dpos = _pos_of(state, dying_id)
    c_team = _team_of(state, caster_id)
    if dpos is None or c_team is None:
        return []
    ring = {(c, r) for (c, r) in hexgeo.disk(int(dpos[0]), int(dpos[1]), SURROUND_RADIUS)
            if (c, r) != (int(dpos[0]), int(dpos[1]))}
    out: list = []
    for uid, e in sorted(state.entities.items()):
        if uid == dying_id or uid == caster_id:
            continue
        uc = e.get_component(UnitComponent)
        if uc is None or not uc.alive:
            continue
        oc = e.get_component(OwnerComponent)
        if oc is None or oc.team == c_team:                 # Enemies(caster, ...) : team adverse
            continue
        pc = e.get_component(PositionComponent)
        if pc is None or (pc.col, pc.row) not in ring:
            continue
        out.append(uid)
    return out


def _passive_level_mult(state: State, owner_id: int):
    """(niveau, multiplier) du PASSIF du porteur -- `ConfigVar` lit `GetVariableForLevel(key, level)`
    sur l'`abilityState` du passif (`passive_ability_level`, pas `active_ability_level`)."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    if ctx is None:
        return None, 100
    return ctx.passive_ability_level, int(getattr(ctx, "ability_variables_multiplier", 100) or 100)


# ----- feuilles DSL (mirror 1:1 des noeuds E natifs) -----

def cosmic_horror_pin_tree():
    """Feuille `AddEffect(0x429=Pinned, AbilityStateReference, caster@0x148, subject@0x180,
    <struct duree ZERO>)` de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnKillAbility$$CreateBehaviour`.
    `duration_rounds=None` = pas de `TurnsFromRounds` -> `DefaultAmountOfRounds(0x429)` (« Suppressed
    for 1 round »). `Target()` (unit-domain) = le `subject@0x180` courant du `Foreach`, cable par
    `entities_from_state(state, owner, victim)`. MEME feuille que `suppressive_fire_tree()`."""
    return AddEffect(PINNED, "Pinned", Target(), duration_rounds=None)


def cosmic_horror_heal_tree(amount: int):
    """Feuille `Heal(caster@0x148, caster@0x148, ConfigVar(0x1d=hp))` de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnMoveAbility$$CreateBehaviour`.
    Source ET cible = le Patermine (`Caster()`), montant = `hp[niveau passif]` deja resolu (fold du
    noeud `ConfigVar`, meme convention que `InspiredToGreatness`). Aucune garde `Healable` dans le
    decompile -> pas de `guard` (le plafond `hp_max` est celui de `HealUnitOperation`)."""
    return Heal(Caster(), int(amount))


# ----- les 2 abilities-triggers -----

class CosmicHorrorOnKillAbility(TriggeredAbility):
    """`CosmicHorror_OnKillAbility` (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnKillAbility$$CreateTrigger`
    / `...$$CreateBehaviour`). Le Patermine acheve un ennemi NON-steppable -> pose un decoy
    `genesSmnDecoy` sur la tuile du mort (sinon la 1re tuile libre adjacente la plus proche de lui),
    puis pour CHAQUE ennemi de l'anneau adjacent au mort, un tirage `chance` (60 % @L65) :
    re-declenchement de son `BattleFatigue` + (s'il est vivant) pose de `Pinned` (1065)."""
    event_id = _ON_KILL

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # get_OwnerIsActor : l'ACTEUR de l'event UnitDefeated est le TUEUR (`unit_defeated_triggers`
        # passe `killer_id` en actor). Le Patermine doit etre ce tueur.
        if ev.actor_id != self.owner_id:
            return False
        victim = ev.dying_id if ev.dying_id is not None else ev.target_id
        if victim is None or victim == self.owner_id:
            return False
        c_team, v_team = _team_of(state, self.owner_id), _team_of(state, victim)
        if c_team is None or v_team is None or c_team == v_team:      # AreEnemies(caster, target)
            return False
        if has_trait(_traits_of(state, victim), STEPPABLE_TRAIT):     # NOT HasTrait(target, Steppable)
            return False
        owner = state.get_entity(self.owner_id)
        ouc = owner.get_component(UnitComponent) if owner is not None else None
        return not (ouc is not None and not ouc.alive)                # un acteur mort n'agit pas (#70)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        import gameconfig as GC
        victim = ev.dying_id if ev.dying_id is not None else ev.target_id
        # (1) `Spawn(caster, tile, GetStringConstant(config, 8=unitToSpawn), ForSteppable())`.
        consts = (GC.ability(ABILITY_ID) or {}).get("constants") or {}
        visual = consts.get(DECOY_UNIT_KEY) or "genesSmnDecoy"
        tile = _decoy_tile_for_kill(state, victim, self.owner_id)
        decoy = spawn_decoy(state, tile, self.owner_id, visual_id=visual) if tile is not None else None
        # (2) `Foreach(Enemies(caster, SurroundingTiles(target,0,1), 3), Maybe(body, ConfigVar(chance)))`.
        lvl, mult = _passive_level_mult(state, self.owner_id)
        chance = ability_var(ABILITY_ID, "chance", lvl, multiplier_pct=mult)
        victims = _surrounding_enemies(state, self.owner_id, victim)
        hits: list = []
        for vid in victims:
            # `MaybeBehaviour.Execute` : UN `next_bool(chance)` par victime, AVANT le child. rng non
            # cale -> no-op documente (meme convention que le noeud `Maybe` du port).
            if state.rng is None or chance is None:
                hits.append({"enemy": vid, "rolled": None, "fatigue": None, "pinned": False})
                continue
            if not state.rng.next_bool(int(chance)):
                hits.append({"enemy": vid, "rolled": False, "fatigue": None, "pinned": False})
                continue
            fatigue = self._retrigger_battle_fatigue(state, ev, vid)
            pinned = self._pin(state, vid)
            hits.append({"enemy": vid, "rolled": True, "fatigue": fatigue, "pinned": pinned})
        return {"passive": ABILITY_ID, "ability": "CosmicHorror_OnKill", "owner": self.owner_id,
                "victim": victim, "decoy": decoy, "decoy_tile": tile, "chance": chance,
                "surrounding": victims, "hits": hits}

    @staticmethod
    def _retrigger_battle_fatigue(state: State, ev: TriggerEvent, enemy_id: int):
        """`TriggerAbility(subject@0x180, 0x401=TriggeredAbilityType.BattleFatigue, ...)` : execute le
        BEHAVIOUR de l'ability `BattleFatigue` de la VICTIME (« trigger Battle Fatigue a second time,
        **if they have it** ») sans re-evaluer son trigger. No-op si l'ennemi ne porte pas le trait
        `BattleFatigue` (1015), qui est ce qui lui accorde la triggered 1025."""
        if not has_trait(_traits_of(state, enemy_id), FATIGUE_TRAIT):
            return None
        from ...behaviour import BattleFatigueAbility
        return BattleFatigueAbility(enemy_id).execute_behaviour(state, ev)

    @staticmethod
    def _pin(state: State, enemy_id: int) -> bool:
        """`If(IsAlive(subject@0x180), AddEffect(0x429=Pinned, ...))` -> arbre `cosmic_horror_pin_tree()`.

        LE GATE MORD, et c'est MESURE (#429-r1-r3-r1-r2). Cette docstring affirmait que la victime
        qui fuit « reste vivante », donc que le gate ne servait a rien ici. C'est **FAUX** :
        `IdunBattle.Operations.FleeOperation$$Execute` appelle le slot 6 de
        `Core.Services.OperationProcessor` (= `$$RemoveUnit`) AVANT de poser `UnitFlag.Fled`, et
        l'unite enfuie SORT du pool `EntityPool.AliveUnits` que lit
        `IdunBattle.Entities.UnitExtensions$$IsAlive`. Live (2026-08-05, MC1_67 et C1_74) : une
        enfuie porte `unitFlags = [9, 26]` et `IsAlive` rend FAUX sur elle **a PV PLEINS**.
        Donc : un porteur `BattleFatigue` qui FUIT au `TriggerAbility` precedent ne recoit PAS
        `Pinned` ; un ennemi qui n'a pas fui, si. Le port posait `Pinned` aux deux tant que sa
        `FleeOperation` ne sortait pas l'unite du plateau -- le gate etait ecrit mais INERTE."""
        e = state.get_entity(enemy_id)
        uc = e.get_component(UnitComponent) if e is not None else None
        if e is None or (uc is not None and not uc.alive):            # IsAlive(subject)
            return False
        if state.effects is None:
            return False
        ectx = ExecutionContext(state=state, rng=state.rng)
        cosmic_horror_pin_tree().execute(entities_from_state(state, enemy_id, enemy_id), ectx)
        return any(p.get("placed") for n, p in ectx.emitted if n == "AddEffect")


class CosmicHorrorOnMoveAbility(TriggeredAbility):
    """`CosmicHorror_OnMoveAbility` (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnMoveAbility$$CreateTrigger`
    / `...$$CreateBehaviour`). Le Patermine marche sur un decoy ALLIE (le crush emet
    `On(0x35=PostUnitKill)` {actor=mover, target=crushe}) -> il se soigne de `hp` PV (2910 @L65)."""
    event_id = _ON_CRUSH

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id != self.owner_id:                              # get_OwnerIsActor (le mover)
            return False
        crushed = ev.target_id
        if crushed is None or crushed == self.owner_id:
            return False
        c_team, t_team = _team_of(state, self.owner_id), _team_of(state, crushed)
        if c_team is None or t_team is None or c_team != t_team:      # AreFriends(caster, target)
            return False
        return has_trait(_traits_of(state, crushed), DECOY_TRAIT)     # HasTrait(target, Decoy)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        lvl, mult = _passive_level_mult(state, self.owner_id)
        amount = ability_var(ABILITY_ID, "hp", lvl, multiplier_pct=mult)   # ConfigVar(0x1d=hp)
        if not amount:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        cosmic_horror_heal_tree(int(amount)).execute(
            entities_from_state(state, self.owner_id, self.owner_id), ectx)
        heal = next((p for n, p in ectx.emitted if n == "Heal"), None)
        return {"passive": ABILITY_ID, "ability": "CosmicHorror_OnMove", "owner": self.owner_id,
                "decoy": ev.target_id, "amount": int(amount), "heal": heal}
