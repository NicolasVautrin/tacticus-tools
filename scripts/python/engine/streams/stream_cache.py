"""`StreamCache` -- mirror 1:1 de `IdunBattle.BattleStream.Loggers.StreamCache`.

C'est LE writer de la grammaire du flux de replay : il formate les quatre formes de ligne,
tient la profondeur d'indentation, et flushe le groupe RACINE a ses listeners quand la pile
revient a zero.

DISPOSITION NATIVE, lue au decompile (offsets relatifs, jamais une VA) :

    +0x10   int              profondeur courante        (`_depth` ici)
    +0x18   StringBuilder    tampon du groupe racine    (`_stream` ici)
    +0x20   List<IStreamCacheListener>                  (`_listeners` ici)

LES QUATRE METHODES, telles que le decompile les ecrit :

  `StreamCache$$StartGroup(groupType, entityId, sourceId, initialTarget)`
      Log(String.Format(<gabarit groupe>, groupType, entityId, sourceId, initialTarget));
      _depth += 1;                                     <- l'increment est APRES le Log

  `StreamCache$$Action(actionType, entityId, tags)`
      log = new StringBuilder();
      text = String.Format(<gabarit action>, actionType, entityId);
      for (i = 0; i < _depth; i++) log.Append(<indent>);
      log.Append(text);
      foreach (kv in new SortedDictionary<TagKey,int>(tags)) {
          line = String.Format(<gabarit tag>, kv.Key, kv.Value);
          for (i = 0; i < _depth + 1; i++) log.Append(<indent>);
          log.Append(line);
      }
      CommitBatchedLog(log);
      SendRootGroupIfFinished();

  `StreamCache$$FinishGroup()`
      _depth -= 1;                                     <- le decrement est AVANT le Log
      Log(<litteral fin de groupe>);
      SendRootGroupIfFinished();

  `StreamCache$$SendRootGroupIfFinished()`
      if (_depth != 0) return;
      var text = _stream.ToString();
      foreach (l in _listeners) l.<slot 0>(text);
      _stream.Clear(); _depth = 0;                     <- c'est `Clear()`, inline

LES CINQ LITTERAUX SONT DESORMAIS **LUS**, PLUS DEDUITS DU FLUX (#477-r15-r1).

Ils l'ont longtemps ete : les chaines .NET vivent dans `global-metadata.dat`, pas dans le PE,
donc Ghidra ne rend au site d'utilisation qu'un `DAT_<slot>`. C'etait le seul endroit du mirror
qui ne venait pas du decompile -- la RE offline (`case-477` § 10.7) en avait meme deduit
« tabulations », ce qui etait FAUX.

`data/symbols/<build>/metadata/string_literals.tsv` resout ces slots. Chaque littéral est
attribue a sa methode par un scan des references RIP-relatives du PE, INDEPENDANT de Ghidra :

    StreamCache$$Log / $$AddToBatchedLog / $$Action  ->  INDENT        (4 espaces)
    StreamCache$$StartGroup                         ->  FMT_GROUP
    StreamCache$$Action                             ->  FMT_ACTION, FMT_TAG
    StreamCache$$FinishGroup                        ->  FINISH_GROUP

Les valeurs LUES sont identiques CARACTERE PAR CARACTERE a celles qui avaient ete mesurees sur
le flux (#477-r11, puis C1_02 : 11 645 octets, 0 CR, 0 TAB, 319 LF) -- 5/5. Les deux canaux sont
independants, donc leur accord est une vraie confirmation, et le cliquet
`test_477r15r1_string_literals_offline.py` le tient a chaque build.

⚠ L'ORDRE DES TAGS EST CELUI DES ORDINAUX, PAS L'ALPHABETIQUE : le `SortedDictionary<TagKey,int>`
trie sur la VALEUR de l'enum. Mesure de controle sur le meme flux : 66 blocs d'action, **0** hors
de l'ordre des ordinaux, **49** hors de l'ordre alphabetique.

⚠ LE SEPARATEUR EST `LF`, ET IL EST DANS LES GABARITS -- pas ajoute par un `join`. Ne jamais le
mesurer sur un fichier : `Path.write_text` traduit `\\n` en `\\r\\n` sous Windows et fabriquerait
un CRLF qui n'existe pas dans le natif.
"""
from __future__ import annotations

from typing import Iterable, List, Mapping, Optional

from .entity_id import BEntityId, format_enum_value
from .group_type import GroupType
from .step_type import StepType
from .tag_key import TagKey


class StreamCacheListener:
    """Mirror de `IdunBattle.BattleStream.Loggers.IStreamCacheListener` (2 slots).

    Le decompile distingue les deux slots par le PREMIER argument du thunk d'invocation
    d'interface : `SendRootGroupIfFinished` appelle le slot 0, `Log` / `CommitBatchedLog`
    appellent le slot 1.

      * slot 0 -- le GROUPE RACINE complet, une fois la pile revenue a zero. Son unique
        consommateur connu est `IdunBattleLogic.Replay.ReplayRecorder$$OnStreamCacheRootGroupFinished`,
        qui l'APPEND au tampon rendu par `IdunBattleLogic.Replay.Replay$$GetWholeBattleOutputStream`.
        C'est ce canal-la qui produit le flux compare par `Runner.ReplayValidator$$CompareOutputStream`.
      * slot 1 -- chaque MORCEAU au fil de l'eau (une ligne de groupe, ou un bloc action+tags).

    ⚠ LE NOM DES DEUX METHODES N'EST PAS RESOLU : une interface IL2CPP n'a pas de corps, donc ni
    `frida/methods.tsv` ni `ghidra/functions.tsv` ne les nomment (l'absence dans les tables ne
    prouve rien -- cf. CLAUDE.md). Seul le nom du CONSOMMATEUR du slot 0 est lu. Les noms ci-dessous
    decrivent donc le ROLE MESURE de chaque slot, et ce paragraphe est la pour qu'on ne les prenne
    pas pour du verbatim."""

    def on_root_group_finished(self, group: str) -> None:
        """slot 0 -- le groupe racine complet."""

    def on_log(self, chunk: str) -> None:
        """slot 1 -- un morceau, au fil de l'eau."""


class StreamCache:
    """`IdunBattle.BattleStream.Loggers.StreamCache`."""

    #: Unite d'indentation. MESUREE (cf. docstring du module), pas lue du decompile.
    INDENT = "    "
    #: Les quatre gabarits `String.Format`. MESURES, pas lus.
    FMT_GROUP = "Group={0} Entity={1} Source={2} InitialTarget={3}\n"
    FMT_ACTION = "Action={0} Entity={1}\n"
    FMT_TAG = "Tag={0}:{1}\n"
    FINISH_GROUP = "Finish_Group\n"

    __slots__ = ("_depth", "_stream", "_listeners")

    def __init__(self) -> None:
        # `StreamCache$$.ctor` : new StringBuilder(), new List<...>(), puis Clear().
        self._stream: List[str] = []
        self._listeners: List[StreamCacheListener] = []
        self.clear()

    # ---------------------------------------------------------------- etat / listeners

    @property
    def depth(self) -> int:
        """`StreamCache+0x10`. Lecture seule -- seuls `StartGroup`/`FinishGroup` la bougent."""
        return self._depth

    def clear(self) -> None:
        """`StreamCache$$Clear` : vide le tampon et remet la profondeur a zero."""
        self._stream = []
        self._depth = 0

    def add_listener(self, listener: StreamCacheListener) -> None:
        """`StreamCache$$AddListener`."""
        self._listeners.append(listener)

    # ---------------------------------------------------------------- ecriture

    def log(self, message: str, extra_tab: bool = False) -> None:
        """`StreamCache$$Log(message, extraTab)`.

        `extraTab` est un `bool` (le decompile le lit `(uint)extraTab & 0xff`) qui ajoute UN
        niveau d'indentation. Aucun appelant porte de la couche `StreamCache` ne le passe a
        vrai -- `StartGroup` et `FinishGroup` appellent tous deux `Log(message, false)`."""
        chunk = self.INDENT * (self._depth + (1 if extra_tab else 0)) + message
        self._stream.append(chunk)
        for listener in self._listeners:
            listener.on_log(chunk)

    def add_to_batched_log(self, log: List[str], message: str,
                           extra_tab: bool = False) -> None:
        """`StreamCache$$AddToBatchedLog(log, message, extraTab)` -- indente puis appende dans
        un tampon LOCAL, sans toucher au flux ni aux listeners."""
        log.append(self.INDENT * (self._depth + (1 if extra_tab else 0)))
        log.append(message)

    def commit_batched_log(self, log: Iterable[str]) -> None:
        """`StreamCache$$CommitBatchedLog(log)` -- verse le tampon local dans le flux et le
        diffuse aux listeners."""
        chunk = "".join(log)
        self._stream.append(chunk)
        for listener in self._listeners:
            listener.on_log(chunk)

    # ---------------------------------------------------------------- les trois formes

    def start_group(self, group_type: int, entity_id: int,
                    source_id: Optional[str] = None,
                    initial_target: Optional[int] = None) -> None:
        """`StreamCache$$StartGroup(groupType, entityId, sourceId, initialTarget)`.

        `sourceId` est une `string` (le nom SYMBOLIQUE de la source : `AvalancheOfMuscle`,
        `BlockEnteringUnits`, ...) et `initialTarget` un `int?`. `null` des deux cotes s'ecrit
        chaine VIDE -- c'est `String.Format` de .NET, pas une branche du writer."""
        self.log(self.FMT_GROUP.format(
            format_enum_value(GroupType, group_type),
            format_enum_value(BEntityId, entity_id),
            "" if source_id is None else str(source_id),
            "" if initial_target is None else str(int(initial_target))))
        self._depth += 1

    def action(self, action_type: int, entity_id: int,
               tags: Mapping[int, int]) -> None:
        """`StreamCache$$Action(actionType, entityId, tags)`.

        L'action s'ecrit a la profondeur COURANTE, ses tags a `depth + 1`. Elle n'exige AUCUN
        groupe ouvert : a profondeur 0 elle produit une ligne `Action=` en tete de flux, et
        `SendRootGroupIfFinished` la flushe aussitot (mesure #477-r11 : `PrepareTurn`,
        `ChangeStats`, `FinishMatch`)."""
        log: List[str] = []
        text = self.FMT_ACTION.format(
            format_enum_value(StepType, action_type),
            format_enum_value(BEntityId, entity_id))
        log.append(self.INDENT * self._depth)
        log.append(text)
        # `new SortedDictionary<TagKey,int>(tags)` : tri sur la VALEUR de l'enum, pas sur le nom.
        for key in sorted(int(k) for k in tags):
            line = self.FMT_TAG.format(format_enum_value(TagKey, key),
                                       str(int(tags[key])))
            log.append(self.INDENT * (self._depth + 1))
            log.append(line)
        self.commit_batched_log(log)
        self.send_root_group_if_finished()

    def finish_group(self) -> None:
        """`StreamCache$$FinishGroup()`.

        Le decrement precede le `Log` : `Finish_Group` s'ecrit donc a la profondeur du `Group=`
        qu'il ferme, pas a celle de son contenu."""
        self._depth -= 1
        self.log(self.FINISH_GROUP)
        self.send_root_group_if_finished()

    # ---------------------------------------------------------------- flush racine

    def send_root_group_if_finished(self) -> str:
        """`StreamCache$$SendRootGroupIfFinished()`.

        Rend le texte flushe (chaine vide si rien ne l'a ete) -- le natif ne rend rien, mais le
        port a besoin d'un retour testable ; aucun appelant du mirror ne s'en sert pour DECIDER."""
        if self._depth != 0:
            return ""
        text = "".join(self._stream)
        for listener in self._listeners:
            listener.on_root_group_finished(text)
        self.clear()
        return text
