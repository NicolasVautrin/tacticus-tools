"""GameState — parse raw MatchState dict from get_state RPC into clean objects."""

from __future__ import annotations
import re
from dataclasses import dataclass, field


# Entity types in IL2CPP MatchState
ENTITY_TILE = 0
ENTITY_UNIT = 1
ENTITY_MATCH = 2
ENTITY_EFFECT = 3
ENTITY_PLAYER = 4
ENTITY_FOOT = 5

# Player types
PLAYER_HUMAN = 0
PLAYER_AI = 1
PLAYER_ENV = 2


@dataclass
class Pos:
    col: int
    row: int

    def __eq__(self, other):
        return isinstance(other, Pos) and self.col == other.col and self.row == other.row

    def __hash__(self):
        return hash((self.col, self.row))

    def __repr__(self):
        return f"({self.col},{self.row})"


@dataclass
class ActiveAbility:
    ability_type: int       # ActiveAbilityType enum (AbilityName)
    can_be_used: bool = True
    is_disabled: bool = False
    has_enough_ammo: bool = True
    remaining_cooldown: int | None = None
    amount_used: int = 0
    hierarchy: int = 0
    description: str = ""   # I2 template (from backend enrich_payload)

    @property
    def is_available(self) -> bool:
        return self.can_be_used and not self.is_disabled and self.has_enough_ammo


@dataclass
class TriggeredAbility:
    config_id: int          # TriggeredAbilityConfigId
    has_been_triggered: bool = False
    triggered_amount: int = 0
    hierarchy: int = 0
    description: str = ""


@dataclass
class Effect:
    id: int
    effect_type: int        # EffectType enum (643 types)
    source_unit_id: int = 0
    owner_id: int = 0
    is_active: bool = True
    has_turns: bool = False
    remaining_turns: int = 0
    initial_turns: int = 0
    level: int = 0
    times_applied: int = 0
    description: str = ""


@dataclass
class Unit:
    id: int
    name: str
    owner_id: int
    hp: int
    max_hp: int
    armor: int
    max_armor: int
    attack: int
    defense: int
    movement: int
    range_val: int
    crit_chance: int
    faction: str
    rank: int
    level: int
    power: int
    tile_id: int | None
    pos: Pos | None
    normal_attack_type: int = 0
    attacks_this_turn: int = 0
    started_turns: int = 0
    finished_turns: int = 0
    active_abilities: list[ActiveAbility] = field(default_factory=list)
    triggered_abilities: list[TriggeredAbility] = field(default_factory=list)
    effect_ids: list[int] = field(default_factory=list)

    @property
    def hp_pct(self) -> float:
        return self.hp / self.max_hp if self.max_hp > 0 else 0

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    @property
    def has_attacked(self) -> bool:
        return self.attacks_this_turn > 0


@dataclass
class Tile:
    id: int
    pos: Pos
    tile_name: str
    elevation: int
    walkable_type: int
    content_id: int
    neighbor_ids: list[int]
    owner_id: int
    triggered_abilities: list[TriggeredAbility] = field(default_factory=list)
    effect_ids: list[int] = field(default_factory=list)

    @property
    def is_walkable(self) -> bool:
        return self.walkable_type == 0


@dataclass
class Player:
    id: int
    name: str
    type: int
    team_id: int

    @property
    def is_human(self) -> bool:
        return self.type == PLAYER_HUMAN


def _parse_active_abilities(comp: dict) -> list[ActiveAbility]:
    """Parse ActiveAbilityComponent.Abilities list from serializeFlat output."""
    abilities = comp.get("Abilities", [])
    if not isinstance(abilities, list):
        return []
    result = []
    for a in abilities:
        if not isinstance(a, dict):
            continue
        result.append(ActiveAbility(
            ability_type=a.get("AbilityName", 0),
            can_be_used=a.get("CanStillBeUsed", True),
            is_disabled=a.get("IsDisabled", False),
            has_enough_ammo=a.get("HasEnoughAmmo", True),
            remaining_cooldown=a.get("RemainingCooldownTurns"),
            amount_used=a.get("AmountOfTimesUsed", 0),
            hierarchy=a.get("Hierarchy", 0),
            description=a.get("_description", ""),
        ))
    return result


def _parse_triggered_abilities(comp: dict) -> list[TriggeredAbility]:
    """Parse TriggeredAbilityComponent.Abilities list from serializeFlat output."""
    abilities = comp.get("Abilities", [])
    if not isinstance(abilities, list):
        return []
    result = []
    for a in abilities:
        if not isinstance(a, dict):
            continue
        result.append(TriggeredAbility(
            config_id=a.get("ConfigId", 0),
            has_been_triggered=a.get("HasBeenTriggered", False),
            triggered_amount=a.get("TriggeredAmount", 0),
            hierarchy=a.get("Hierarchy", 0),
            description=a.get("_description", ""),
        ))
    return result


class GameState:
    """Parsed game state from the raw MatchState RPC response."""

    def __init__(self, raw: dict):
        self._raw = raw
        self._entities = [e for e in raw.get("_entities", []) if isinstance(e, dict)]
        self.events: list[dict] = raw.get("_events", [])

        self.players: list[Player] = []
        self.units: list[Unit] = []
        self.tiles: dict[int, Tile] = {}
        self.effects: list[Effect] = []
        self._foot_map: dict[int, int] = {}  # unit_id -> tile_id
        self._current_player_id = 0

        self._parse_players()
        self._parse_match()
        self._parse_tiles()
        self._parse_feet()
        self._parse_units()
        self._parse_effects()

    # -- Parsing --

    def _parse_players(self):
        for e in self._entities:
            if e.get("Type") != ENTITY_PLAYER:
                continue
            pc = e.get("Component", {})
            self.players.append(Player(
                id=e["Id"],
                name=pc.get("Name", ""),
                type=pc.get("Type", -1),
                team_id=pc.get("TeamId", 0),
            ))

    def _parse_match(self):
        for e in self._entities:
            if e.get("Type") != ENTITY_MATCH:
                continue
            tc = e.get("Turn", {})
            self._current_player_id = tc.get("_currentPlayerId", 0)

    def _parse_tiles(self):
        for e in self._entities:
            if e.get("Type") != ENTITY_TILE:
                continue
            tc = e.get("Component", {})
            pos_comp = e.get("Position", {})
            coord = pos_comp.get("Coordinate", {})
            conn = e.get("Connectivity", {})
            content = e.get("Content", {})
            movement = e.get("TileMovement", {})
            owner = e.get("Owner", {})
            ta = e.get("TriggeredAbility", {})
            eo = e.get("EffectsOwned", {})
            self.tiles[e["Id"]] = Tile(
                id=e["Id"],
                pos=Pos(coord.get("Column", 0), coord.get("Row", 0)),
                tile_name=tc.get("Id", ""),
                elevation=tc.get("Elevation", 0),
                walkable_type=movement.get("WalkableType", 0),
                content_id=content.get("ContentId", 0),
                neighbor_ids=conn.get("NeighbourIds", []),
                owner_id=owner.get("PlayerEntityId", 0),
                triggered_abilities=_parse_triggered_abilities(ta),
                effect_ids=eo.get("ActiveEffectIds", []) or [],
            )

    def _parse_feet(self):
        for e in self._entities:
            if e.get("Type") != ENTITY_FOOT:
                continue
            fc = e.get("Component", {})
            uid = fc.get("UnitId", 0)
            tid = fc.get("TileId", 0)
            if uid and tid:
                self._foot_map[uid] = tid

    def _parse_units(self):
        for e in self._entities:
            if e.get("Type") != ENTITY_UNIT:
                continue
            uc = e.get("Component", {})
            owner = e.get("Owner", {})
            health = e.get("Health", {})
            armor = e.get("Armor", {})
            atk = e.get("Attack", {})
            dfn = e.get("Defense", {})
            mov = e.get("Movement", {})
            rng = e.get("Range", {})
            crit = e.get("CritChance", {})
            uid = e["Id"]
            tile_id = self._foot_map.get(uid)
            pos = self.tiles[tile_id].pos if tile_id and tile_id in self.tiles else None
            aa = e.get("ActiveAbility", {})
            ta = e.get("TriggeredAbility", {})
            eo = e.get("EffectsOwned", {})
            stats = e.get("ActorStatistics", {})
            self.units.append(Unit(
                id=uid,
                name=uc.get("Id", ""),
                owner_id=owner.get("PlayerEntityId", 0),
                hp=health.get("RemainingValue", 0),
                max_hp=health.get("InitialValue", 0),
                armor=armor.get("RemainingValue", 0),
                max_armor=armor.get("InitialValue", 0),
                attack=atk.get("InitialValue", 0),
                defense=dfn.get("InitialValue", 0),
                movement=mov.get("InitialValue", 0),
                range_val=rng.get("InitialValue", 0),
                crit_chance=crit.get("InitialValue", 0),
                faction=uc.get("Faction", ""),
                rank=uc.get("Rank", 0),
                level=uc.get("Level", 0),
                power=uc.get("Power", 0),
                tile_id=tile_id,
                pos=pos,
                normal_attack_type=aa.get("NormalAttackType", 0),
                attacks_this_turn=stats.get("TotalAttacksMadeThisTurn", 0),
                started_turns=uc.get("StartedTurns", 0),
                finished_turns=uc.get("FinishedTurns", 0),
                active_abilities=_parse_active_abilities(aa),
                triggered_abilities=_parse_triggered_abilities(ta),
                effect_ids=eo.get("ActiveEffectIds", []) or [],
            ))

    def _parse_effects(self):
        for e in self._entities:
            if e.get("Type") != ENTITY_EFFECT:
                continue
            ec = e.get("Component", {})
            self.effects.append(Effect(
                id=e["Id"],
                effect_type=ec.get("EffectType", 0),
                source_unit_id=ec.get("SourceUnitId", 0),
                owner_id=ec.get("OwnerId", 0),
                is_active=ec.get("IsActive", True),
                has_turns=ec.get("HasTurns", False),
                remaining_turns=ec.get("RemainingTurns", 0),
                initial_turns=ec.get("InitialTurns", 0),
                level=ec.get("Level", 0),
                times_applied=ec.get("TimesApplied", 0),
                description=ec.get("_description", ""),
            ))

    # -- Accessors --

    @property
    def human_player(self) -> Player | None:
        for p in self.players:
            if p.is_human:
                return p
        return None

    @property
    def is_player_turn(self) -> bool:
        hp = self.human_player
        return hp is not None and self._current_player_id == hp.id

    @property
    def player_units(self) -> list[Unit]:
        hp = self.human_player
        if hp is None:
            return []
        return [u for u in self.units if u.owner_id == hp.id and u.is_alive]

    @property
    def enemy_units(self) -> list[Unit]:
        hp = self.human_player
        if hp is None:
            return []
        return [u for u in self.units if u.owner_id != hp.id and u.is_alive]

    def unit_by_id(self, unit_id: int) -> Unit | None:
        for u in self.units:
            if u.id == unit_id:
                return u
        return None

    def tile_at(self, col: int, row: int) -> Tile | None:
        for t in self.tiles.values():
            if t.pos.col == col and t.pos.row == row:
                return t
        return None

    def unit_at(self, col: int, row: int) -> Unit | None:
        for u in self.units:
            if u.pos and u.pos.col == col and u.pos.row == row:
                return u
        return None

    def walkable_tiles(self) -> list[Tile]:
        return [t for t in self.tiles.values() if t.is_walkable]

    def enrich_abilities(self, info: dict) -> None:
        """Substitute {[param]} placeholders in descriptions with values from get_abilities_info.

        info: result of RpcClient.get_abilities_info() — after backend enum resolution,
              keys are param names (e.g. "extraDmg"), values are ints.
              Structure: {unitId_str: {active: {abilityType: {param: val}}, triggered: {configId: {param: val}}}}
        """
        def _sub(template: str, params: dict) -> str:
            return re.sub(
                r"\{\[((?:[^\[\]]*|\[[^\]]*\])*)\]\}",
                lambda m: str(params.get(m.group(1), m.group(0))),
                template,
            )

        for u in self.units:
            unit_info = info.get(str(u.id), {})
            for a in u.active_abilities:
                params = unit_info.get("active", {}).get(str(a.ability_type))
                if params and a.description:
                    a.description = _sub(a.description, params)
            for t in u.triggered_abilities:
                params = unit_info.get("triggered", {}).get(str(t.config_id))
                if params and t.description:
                    t.description = _sub(t.description, params)
        for eff in self.effects:
            params = info.get(f"effect_{eff.id}")
            if params and eff.description:
                eff.description = _sub(eff.description, params)

    def effects_on(self, entity_id: int) -> list[Effect]:
        """Get all effects owned by a unit or tile (via EffectsOwnedComponent.ActiveEffectIds)."""
        # Find the entity (unit or tile)
        unit = self.unit_by_id(entity_id)
        if unit:
            eids = unit.effect_ids
        elif entity_id in self.tiles:
            eids = self.tiles[entity_id].effect_ids
        else:
            return []
        effects_by_id = {e.id: e for e in self.effects}
        return [effects_by_id[eid] for eid in eids if eid in effects_by_id]

    def effect_by_id(self, effect_id: int) -> Effect | None:
        for e in self.effects:
            if e.id == effect_id:
                return e
        return None

    def __repr__(self):
        hp = self.human_player
        return (
            f"GameState(players={len(self.players)}, units={len(self.units)}, "
            f"tiles={len(self.tiles)}, effects={len(self.effects)}, "
            f"turn={'player' if self.is_player_turn else 'enemy'})"
        )