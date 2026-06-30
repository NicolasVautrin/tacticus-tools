"""ECS — état de bataille (entités + composants).

Port FIDÈLE au niveau SÉMANTIQUE de l'ECS natif (PAS du layout mémoire octet par
octet — inutile pour la fidélité comportementale) :
  • Native : entité = table de composants `entity+0xb0` {typeToken, slot}, count
    `+0x12e`, base `+0x138` ; ajout `Entity$$AddComponent` @181006990.
  • Python : `Entity` = id + dict {type_de_composant -> instance}.

`Component` = classe de base ; chaque composant concret (UnitFootComponent,
EffectsOwnedComponent, TriggeredAbilityComponent, ActiveAbilityComponent, …) sera
porté avec ses champs exacts RE'd, au fil des tranches.

⚠ TODO (tâche #23) : RE de la struct Entity native + des composants (layout/champs
exacts) avant de figer les composants concrets. Ce fichier ne pose que les
primitives génériques (Entity/Component/State) dont la sémantique est confirmée.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Optional, TypeVar

if TYPE_CHECKING:
    from ..entities import EffectsState
    from .prng import IntBasedMersenneTwister

C = TypeVar("C", bound="Component")


class Component:
    """Base de tout composant ECS. Les composants concrets en héritent avec leurs
    champs exacts (RE'd, VA citée dans chaque sous-classe)."""
    __slots__ = ()


class Entity:
    """Entité ECS = id + composants typés (mirror Entity$$AddComponent @181006990)."""
    __slots__ = ("id", "_components")

    def __init__(self, entity_id: int):
        self.id = entity_id
        self._components: dict[type, Component] = {}

    def add_component(self, comp: Component) -> Component:
        """mirror Entity$$AddComponent @181006990 (1 composant par type)."""
        self._components[type(comp)] = comp
        return comp

    def get_component(self, comp_type: type[C]) -> Optional[C]:
        return self._components.get(comp_type)  # type: ignore[return-value]

    def has_component(self, comp_type: type) -> bool:
        return comp_type in self._components

    def remove_component(self, comp_type: type) -> None:
        self._components.pop(comp_type, None)

    def __repr__(self) -> str:
        names = ",".join(t.__name__ for t in self._components)
        return f"Entity(#{self.id}: {names})"


class State:
    """État de bataille = ensemble d'entités + méta (tour/joueur courant).

    `current_player_id` mirror `StateExtensions.GetCurrentPlayerId(state)` (lu par
    IdunRunner.Apply). Les requêtes riches (par owner, par tuile, vivantes, …) seront
    ajoutées au fil des tranches en miroir de `IdunBattle.Entities.*Extensions`.

    `effects` = état STRUCTURÉ + évoluable des effets actifs (`EffectsState`, instances
    `BaseEffect` par unité), peuplé par `load_state` quand un `combatSnapshot` est fourni
    (sinon None ; l'identité reste en NOMS via `EffectsOwnedComponent` pour le diff).
    Source des modifiers de dégât (couche `engine.entities.effects`).

    `rng` = RNG de combat du runner (`IntBasedMersenneTwister`). Pour un replay-diff
    bit-exact vs live, on le CALE sur l'état MT live (`dumpRng`) avant de rejouer un
    message qui tire (attaque). None tant qu'aucun RNG n'est posé.

    `board` = graphe hex (`engine.entities.pathfinding.board.Board`) optionnel, posé pour
    les mécaniques qui ont besoin de l'ADJACENCE hex (ex. splash Psyker = ennemis adjacents
    à la cible). None = pas d'adjacence dispo → ces mécaniques dégradent en no-op.

    `turn_counts` = nb de tours DÉMARRÉS par joueur (mirror `TurnComponent.turnsStartedByCurrentPlayer`,
    dict @+0x38) ; incrémenté par `StartTurnOperation`. Source de `GetAmountOfTurnsStartedByCurrentPlayer`
    (gate « 1er tour » de certaines mécaniques). Vide tant qu'aucun tour n'a été joué via le runner."""
    __slots__ = ("entities", "current_player_id", "_next_entity_id", "effects", "rng", "board",
                 "turn_counts")

    def __init__(self):
        self.entities: dict[int, Entity] = {}
        self.current_player_id: Optional[int] = None
        self._next_entity_id = 1
        self.effects: Optional["EffectsState"] = None
        self.rng: Optional["IntBasedMersenneTwister"] = None
        self.board = None
        self.turn_counts: dict[int, int] = {}

    def add_entity(self, entity_id: Optional[int] = None) -> Entity:
        if entity_id is None:
            entity_id = self._next_entity_id
            self._next_entity_id += 1
        e = Entity(entity_id)
        self.entities[entity_id] = e
        return e

    def get_entity(self, entity_id: int) -> Optional[Entity]:
        return self.entities.get(entity_id)

    def with_component(self, comp_type: type[C]) -> Iterator[tuple[Entity, C]]:
        """Itère (entité, composant) pour toute entité portant `comp_type`."""
        for e in self.entities.values():
            c = e.get_component(comp_type)
            if c is not None:
                yield e, c  # type: ignore[misc]
