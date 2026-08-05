"""`StreamDispatcher` -- mirror 1:1 de `IdunBattle.Streams.StreamDispatcher`.

C'est le point d'entree que TOUTE operation native utilise pour emettre :
`IdunBattle.Core.AOperation$$get_Events` rend ce dispatcher, et les operations y appellent
`StartGroup` / `Action` / `FinishGroup`. Il ne formate RIEN -- il empaquette ses arguments dans
un message et le diffuse a ses abonnes, dont `IdunBattle.BattleStream.Loggers.StreamCache`.

SIGNATURES, lues au decompile (le champ `+0x10` du dispatcher est la liste des abonnes, parcourue
par `List<T>.ForEach`) :

  `StreamDispatcher$$StartGroup(groupType, entityId, sourceId, initialTarget)`
      message.groupType     <- +0x10 (int)
      message.entityId      <- +0x14 (int)
      message.sourceId      <- +0x18 (reference : string)
      message.initialTarget <- +0x20 (8 octets : `int?`)
  `StreamDispatcher$$Action(actionType, entityId, tags)`
      message.actionType    <- +0x10 (int)
      message.entityId      <- +0x14 (int)
      message.tags          <- +0x18 (reference : IDictionary<TagKey,int>)
  `StreamDispatcher$$FinishGroup()`
      aucun argument -- le message est un singleton mis en cache
      (`StreamDispatcher.u003Cu003Ec$$u003CFinishGroupu003Eb__7_0`).

⚠ POURQUOI LE PORT NE MATERIALISE PAS LE MESSAGE. Nativement chaque appel alloue un objet de
message parce que la diffusion passe par `List<Action<T>>.ForEach`. Un mirror qui allouerait un
objet Python par ligne n'ajouterait aucune fidelite OBSERVABLE : ni le texte, ni l'ordre, ni la
profondeur n'en dependent. Les trois methodes appellent donc directement l'abonne. Ce qui est
PRESERVE, et qui compte : l'ordre d'abonnement, et le fait qu'un dispatcher SANS abonne
n'ecrit rien (le natif construit le message puis le jette).
"""
from __future__ import annotations

from typing import List, Mapping, Optional

from .stream_cache import StreamCache


class StreamDispatcher:
    """`IdunBattle.Streams.StreamDispatcher`."""

    __slots__ = ("_subscribers",)

    def __init__(self) -> None:
        self._subscribers: List[StreamCache] = []

    def subscribe(self, subscriber: StreamCache) -> None:
        """`StreamDispatcher$$Subscribe`."""
        self._subscribers.append(subscriber)

    def unsubscribe(self, subscriber: StreamCache) -> None:
        """`StreamDispatcher$$Unsubscribe`."""
        self._subscribers.remove(subscriber)

    def clear(self) -> None:
        """`StreamDispatcher$$Clear`."""
        self._subscribers = []

    # ---------------------------------------------------------------- diffusion

    def start_group(self, group_type: int, entity_id: int,
                    source_id: Optional[str] = None,
                    initial_target: Optional[int] = None) -> None:
        """`StreamDispatcher$$StartGroup`."""
        for sub in self._subscribers:
            sub.start_group(group_type, entity_id, source_id, initial_target)

    def action(self, action_type: int, entity_id: int,
               tags: Mapping[int, int]) -> None:
        """`StreamDispatcher$$Action`."""
        for sub in self._subscribers:
            sub.action(action_type, entity_id, tags)

    def finish_group(self) -> None:
        """`StreamDispatcher$$FinishGroup`."""
        for sub in self._subscribers:
            sub.finish_group()
