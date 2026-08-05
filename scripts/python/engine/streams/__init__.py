"""`engine.streams` -- l'EMETTEUR du flux de replay natif (tranches A + B + D du #477-r15).

Le jeu produit, pendant une bataille, un flux texte **deterministe au caractere pres**
(#477-r11 : 3 rejeux, 2 boards, 2 sessions Frida, zero divergence -- la barre de comparaison
est l'egalite BRUTE). Ce paquet donne au port la capacite d'emettre ce meme flux.

LA CHAINE NATIVE, dans l'ordre :

    <Operation>.Events            -> `IdunBattle.Core.AOperation$$get_Events`
      IdunBattle.Streams.StreamDispatcher    diffuse StartGroup/Action/FinishGroup a ses listeners
        IdunBattle.BattleStream.Loggers.StreamCache   FORMATE le texte + tient la profondeur
          IdunBattleLogic.Replay.ReplayRecorder$$OnStreamCacheRootGroupFinished
                                                      concatene chaque GROUPE RACINE flushe

`IdunBattleLogic.Replay.Replay$$GetWholeBattleOutputStream` rend cette concatenation : c'est
exactement ce que le RPC `replayOutputStream` publie, et ce que
`Runner.ReplayValidator$$CompareOutputStream` compare caractere par caractere.

CE QUE CE PAQUET REMPLACE. `engine/runner/events.py` (`EventBus`/`BattleEvent`) etait un STUB
MORT : 3 methodes definies, 0 appel, 0 sous-classe d'evenement, instancie six fois pour remplir
le parametre `execute(state, bus)` (mesure #477-r15). Il n'est PAS supprime ici -- 25 modules
d'operation l'importent -- mais l'emission passe desormais par `StreamDispatcher`.

CE QU'IL NE FAIT PAS. Il ne fabrique aucun identifiant d'entite ECS : l'ordre d'allocation natif
(tuiles, puis unites par pas de 2, puis effets) n'est pas retro-ingenierie -- c'est `#477-r16`.
Tout emetteur recoit donc ses ids, il ne les invente pas. Meme regle pour les STATS et les ETATS
D'ABILITY de la tranche D (`unit_extensions`) : le port les recoit resolus, il ne simule aucun
composant ECS.
"""
from __future__ import annotations

from .dispatcher import StreamDispatcher
from .entity_id import BEntityId, NO_ENTITY, format_enum_value
from .group_type import GroupType
from .input_messages import visit_add_unit_message
from .step_type import StepType
from .stream_cache import StreamCache
from .tag_key import TagKey
from .unit_extensions import (ActiveAbilityState, TriggeredAbilityState, UnitFullState,
                              get_full_state_update_tags,
                              get_full_state_update_tags_for_active,
                              get_full_state_update_tags_for_triggered)

__all__ = [
    "ActiveAbilityState",
    "BEntityId",
    "GroupType",
    "NO_ENTITY",
    "StepType",
    "StreamCache",
    "StreamDispatcher",
    "TagKey",
    "TriggeredAbilityState",
    "UnitFullState",
    "format_enum_value",
    "get_full_state_update_tags",
    "get_full_state_update_tags_for_active",
    "get_full_state_update_tags_for_triggered",
    "visit_add_unit_message",
]
