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

CE QU'IL NE FAIT PAS. Il ne simule aucun composant ECS : les STATS et les ETATS D'ABILITY de la
tranche D (`unit_extensions`) sont recus resolus.

LES IDENTIFIANTS D'ENTITE, EUX, SE DERIVENT (`entity_allocator`, `#477-r21-r3`) -- ce module
n'est PAS dans cette liste. `MatchComponent$$NextId` est porte, ainsi que la sequence de
`SetupGameOperation$$Execute` : `game_setup.assign_entity_ids` produit tous les ids du
deploiement et rend le compteur pour le deroule. Ce qui reste hors de portee n'est plus la
REGLE mais la SEQUENCE des creations d'effet -- `#477-r21-r2`.
"""
from __future__ import annotations

from .dispatcher import StreamDispatcher
from .entity_id import BEntityId, NO_ENTITY, format_enum_value
from .group_type import GroupType
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
]

# ⚠ `game_setup` ET `input_messages` NE SONT PAS REEXPORTES ICI, et ce n'est pas un oubli --
# c'est la convention deja en place, qu'aucun texte ne disait. Tous deux tirent
# `engine.services.machine_of_war_position` ; les mettre dans cet `__init__` ferait grossir le
# graphe d'imports de tout `import engine.streams`. MESURE du 2026-08-05 (#477-r18-r5) :
# `origin/master` charge 99 modules `engine.*` dont 11 `engine.services` ; avec le reexport,
# 104 dont 12 ; sans lui, 99 / 11 -- STRICTEMENT INCHANGE. Cet `__init__` reste donc le WRITER
# seul (grammaire, enums, cache, dispatcher). Les emetteurs s'importent par leur module :
#     from engine.streams.game_setup import emit_game_setup
#     from engine.streams.input_messages import visit_add_unit_message
