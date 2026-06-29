"""Composants ECS concrets — port FIDÈLE (noms 1:1 du natif, VA citée).

`IdunBattle.Entities.Components.*Component`. Tranche 0 : seuls les composants de
l'ÉTAT D'UNITÉ diffé (position/HP/owner/identité/effets) sont posés, avec les champs
qu'on peut peupler depuis la vérité live (decisionView/observeBattle, qui lisent
ces composants natifs). Les OFFSETS exacts (layout) seront RE'd quand une operation
les ÉCRIRA (tranche move/damage/effects) ; ici on porte la sémantique des champs.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from .state import Component

if TYPE_CHECKING:
    from ..entities import UnitContext


class UnitComponent(Component):
    """Identité d'unité — `UnitComponent` @180facf20 / `BaseUnitComponent` @180f96380.
    `visual_id` = id visuel (ex. 'necroNpc1Warrior'), `alive` = vivante."""
    __slots__ = ("visual_id", "alive")

    def __init__(self, visual_id: Optional[str], alive: bool):
        self.visual_id = visual_id
        self.alive = alive


class OwnerComponent(Component):
    """Propriétaire — `OwnerComponent` @180fa64c0. `team` = équipe (1/2) ; `player` = id du player
    (≠ team : team 1 = player 3, team 2 = player 4 ; un summon hérite team ET player du caster via
    `SpawnUnitOptions.CopyOwner`, cf. project_summon_team_model). `player` None si non capté."""
    __slots__ = ("team", "player")

    def __init__(self, team: Optional[int], player: Optional[int] = None):
        self.team = team
        self.player = player


class PositionComponent(Component):
    """Position sur le board — `PositionComponent` @180fa6db0 (et `UnitFootComponent`
    @180fad890 : UnitId@0x10, TileId@0x14). Coordonnées hex (col,row)."""
    __slots__ = ("col", "row")

    def __init__(self, col: int, row: int):
        self.col = col
        self.row = row


class HealthComponent(Component):
    """PV — `HealthComponent` @180f9f1b0. `hp` courant, `hp_max` plafond."""
    __slots__ = ("hp", "hp_max")

    def __init__(self, hp: Optional[int], hp_max: Optional[int]):
        self.hp = hp
        self.hp_max = hp_max


class EffectsOwnedComponent(Component):
    """Effets actifs portés — `EffectsOwnedComponent` @180f99a50 (chaque effet =
    `EffectComponent` @180f61990). Ici : liste des NOMS d'effets actifs (vue pour le
    diff structurel). Le détail STRUCTURÉ (type/durée/params, matérialisé + évoluable)
    vit dans `State.effects` (`EffectsState`), source des modifiers de dégât."""
    __slots__ = ("effects",)

    def __init__(self, effects: List[str]):
        self.effects = effects


class StatsComponent(Component):
    """Bloc de stats de combat RÉSOLUES de l'unité (Attack, FixedArmor, ExtraHits,
    ExtraPierce, crit/block, AbilityVariablesMultiplier, niveau d'ability…) + config
    d'arme de l'attaque normale. Porte le `UnitContext` validé (`engine.entities`),
    assemblé depuis `combatSnapshot` (stats one-shot) + gameconfig.

    C'est la SOURCE de la plage de tirage de dégât (`base = stat Attack`, spread BC),
    qui rend le runner autonome (calcul de la plage sans relecture live). Natif : les
    stats sont stockées sur l'unité (StatComponents) et lues par `BattleQuery`."""
    __slots__ = ("ctx",)

    def __init__(self, ctx: "UnitContext"):
        self.ctx = ctx
