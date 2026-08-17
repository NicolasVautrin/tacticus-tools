"""`MachineOfWarPosition` d'un JOUEUR — le slot de plateau, PAS une machine deployee.

Pourquoi ce module existe (RE #302 tranche 3, mesuree le 2026-07-30)
--------------------------------------------------------------------
Le predicat `IdunBattleLogic.Entities.DSLTriggers$$IsPositionMachineForCurrentPlayer` ->
`IdunBattle.Entities.Triggers.IsPositionMachineForPlayerTrigger$$ShouldTrigger` :

    turn   = state.GetMatchTurn()
    player = state.GetEntity(turn.CurrentPlayerId)
    if (player == null) return false
    return battleQuery.GetPositionMachineForPlayer(player) == this.Position@+0x20

et `IdunBattle.Core.Services.BattleQuery$$GetPositionMachineForPlayer(player)` :

    teamIndex = player.GetComponent<TeamComponent>().<+0x24>
    t         = StateExtensions.GetTeam(state)              // Nullable<(teamId, playerNr)>
    if (!t.HasValue) return 0                                // MachineOfWarPosition.None
    grp = spawnPointSet@+0x78.GroupForPlayer(teamIndex, playerNr)
    if (grp != null) return grp.<+0x14>                      // MachineOfWarPosition du GROUPE
    // aucun groupe pour ce (team, playerNr) :
    if (teamIndex != 1) return (teamIndex == 2) ? 1 : 0
    return 2

et `IdunBattle.Configuration.SpawnPointSetConfiguration$$GroupForPlayer(teamId, playerNr)` :

    twpi = teamId == 0 ? 6
         : teamId == 1 ? (playerNr != 0 ? 2 : 0)
         : teamId == 2 ? (playerNr != 0 ? 3 : 1)
         : teamId == 3 ? (playerNr != 0 ? 5 : 4)
         : throw ArgumentOutOfRange
    return SpawnPointGroups.FirstOrDefault(g => g.TeamWithPlayerIndex@+0x10 == twpi)

⇒ **La valeur est une propriete du PLATEAU** (`BattleConfiguration.Board.SpawnPointSets[
SpawnPointSetIndex].SpawnPointGroups[].MachineOfWarPosition`), disponible qu'une Machine of War
soit deployee ou NON. Le port lisait jusqu'ici `MachineComponent.Position` de la MoW deployee : un
PROXY qui coincide quand la machine existe, et qui rend « inconnu » sinon — alors que le natif, lui,
repond toujours.

MESURE qui a fait tomber l'erreur (runner 802, board `MC1_67`, `SpawnPointSetIndex = 1`, AUCUNE MoW
deployee) : le natif a vise la tuile (4,4), c'est-a-dire le triangle `{S, SE}` (`dir = 1`), donc
predicat VRAI, donc `MachineOfWarPosition(joueur courant) == 2`. La BC du runner le confirme :
`SpawnPointSets[1].SpawnPointGroups = [(TWPI 0 -> 2), (TWPI 1 -> 1)]`.

Le fallback natif n'est PAS un defaut raisonnable : balayage des 675 boards du depot (le dump que
`_load_board_dump` retiendrait, sur son `spawnPointsSet` paire) -- **502 declarent (0, 0)** et
**173 declarent (2, 1)**. Appliquer le fallback sans avoir lu le groupe serait donc faux sur ~74 %
des plateaux.

⚠ Ce « 502 » compte les ids qui portent `(0, 0)` **EXCLUSIVEMENT**. Re-mesure #302-5 : `data/boards`
porte **779 fichiers** pour **675 ids**, **552** ids portent `(0, 0)` dans au moins un pool, **173**
portent `(2, 1)`, et **50 ids portent les DEUX selon le pool** (`552 + 173 - 50 = 675`). Pour ces 50,
`--board <id>` ne suffit pas a fixer la valeur : le `--board-pool` la change. Les trois comptes sont
re-derivables par `probe_302_5_mow_position_channel.py --boards` -- ne pas citer cette ligne. Le port ne devine pas : il lit les groupes quand on les lui donne, et rend `None`
(= inconnu) sinon (cf. `engine.ai.context.AiDecisionContext.machine_of_war_position`).

CE MIRROR N'EST PLUS LE PREMIER CANAL (#302 tranche 5)
------------------------------------------------------
`boardGraph.mowPositions` (#311) publie le retour de `GetPositionMachineForPlayer(player)`
**INVOQUE** par joueur sur le runner. `AiDecisionContext` le lit en priorite, et c'est plus fidele
que ce module sur un point PRECIS : le natif tire `playerNr` du `Nullable` rendu par
`StateExtensions$$GetTeam(state)` (`local_res10 >> 0x20` au decompile), la ou `team_with_player_index`
le **defaut a 0**. Ce mirror reste la SEULE voie du chemin OFFLINE (`build_from_state`, sans RPC),
et le TEMOIN qui permet de confronter le canal.

Concordance MESUREE (2026-08-06, build `rnca9r7q6c`) : **6/6** valeurs identiques au natif sur deux
boards, dont le regime DISCRIMINANT. Elle tranche aussi le residu de #311 (« on ne peut pas
distinguer "lit la declaration" de "le repli a tire" ») : sur `C1_01`, qui declare (0, 0), le natif
rend **0/0** quand le repli seul rendrait **2/1** -> `GetPositionMachineForPlayer` **LIT la
declaration du groupe**.

Corollaire mesure, qui explique pourquoi le repli `decisionView.mows` ne pouvait pas suffire : un
groupe declarant `MachineOfWarPosition.None_` ne deploie **aucune** MoW, donc `mows` est **vide**
exactement sur les plateaux ou le natif diverge du fallback.
"""
from __future__ import annotations

from enum import IntEnum


class MachineOfWarPosition(IntEnum):
    """`IdunBattle.Configuration.MachineOfWarPosition` -- VERBATIM du build (3 valeurs).

    Re-derivable : `data/symbols/<CURRENT>/frida/enums.tsv`. Le mirror est entre au registre
    `probe_313` avec #477-r15, quand `TagKey.MachinePosition` a eu besoin de le NOMMER : le
    fichier portait jusque-la trois constantes libres, donc un entier qui DESIGNE sans enum.
    """

    None_ = 0
    Top = 1
    Bottom = 2


# Les trois noms historiques, conserves : ils sont lus ailleurs dans le moteur. Ils DERIVENT
# desormais du mirror -- aucune valeur ne peut plus diverger de la table.
MOW_POSITION_NONE = int(MachineOfWarPosition.None_)
MOW_POSITION_TOP = int(MachineOfWarPosition.Top)
MOW_POSITION_BOTTOM = int(MachineOfWarPosition.Bottom)


def team_with_player_index(team_index: int, player_nr: int = 0) -> int:
    """`SpawnPointSetConfiguration$$GroupForPlayer` — l'index compose, transcrit LITTERALEMENT.

    `player_nr` vaut 0 dans un duel a un joueur par equipe (le cas de tous nos runners : la BC
    declare `Players = {p1: TeamId 1, p2: TeamId 2, env: TeamId 0}`). Le natif le tire du
    `Nullable<...>` rendu par `StateExtensions.GetTeam(state)` ; il n'a aucun canal cote port, d'ou
    le defaut EXPLICITE plutot qu'une valeur cachee.

    `team_index` hors {0,1,2,3} : le natif leve `ArgumentOutOfRangeException`. Le port rend `None`
    (aucun groupe ne peut correspondre) plutot que de lever dans un chemin de decision."""
    t, second = int(team_index), (int(player_nr) != 0)
    if t == 0:
        return 6
    if t == 1:
        return 2 if second else 0
    if t == 2:
        return 3 if second else 1
    if t == 3:
        return 5 if second else 4
    return None


def group_for_player(spawn_groups, team_index: int, player_nr: int = 0):
    """`SpawnPointSetConfiguration$$GroupForPlayer` : le PREMIER groupe dont
    `TeamWithPlayerIndex` vaut l'index compose (`FirstOrDefault`), ou `None`.

    `spawn_groups` = les `SpawnPointGroups` du SpawnPointSet ACTIF, sous la forme de la BC JSON
    (`{"TeamWithPlayerIndex": int, "MachineOfWarPosition": int, ...}`)."""
    twpi = team_with_player_index(team_index, player_nr)
    if twpi is None or not spawn_groups:
        return None
    for g in spawn_groups:
        if (g or {}).get("TeamWithPlayerIndex") == twpi:
            return g
    return None


def machine_of_war_position_for_player(spawn_groups, team_index: int, player_nr: int = 0) -> int:
    """`IdunBattle.Core.Services.BattleQuery$$GetPositionMachineForPlayer` — mirror 1:1 de la
    cascade GROUPE puis FALLBACK.

    ⚠ N'appeler qu'avec des `spawn_groups` REELLEMENT LUS (la BC du runner). Le fallback n'est le
    comportement natif que lorsque le groupe est ABSENT de la config -- pas lorsque le port ignore
    la config. Cette distinction est portee par l'appelant
    (`AiDecisionContext.machine_of_war_position`), qui rend `None` tant qu'il n'a rien lu."""
    grp = group_for_player(spawn_groups, team_index, player_nr)
    if grp is not None:
        return int(grp.get("MachineOfWarPosition") or 0)
    t = int(team_index)
    if t != 1:
        return MOW_POSITION_TOP if t == 2 else MOW_POSITION_NONE
    return MOW_POSITION_BOTTOM


def spawn_groups_from_battle_config(bc: dict):
    """Les `SpawnPointGroups` du SpawnPointSet ACTIF d'une `BattleConfiguration` JSON.

    C'est exactement ce que le natif referme dans `BattleQuery+0x78` :
    `Board.SpawnPointSets[BattleConfiguration.SpawnPointSetIndex].SpawnPointGroups`. Rend `None`
    (et non `[]`) si la BC ne porte pas la structure -- `[]` signifierait « set actif SANS groupe »,
    ce qui declencherait le fallback natif, alors que « pas lu » ne doit rien declencher."""
    board = (bc or {}).get("Board") or {}
    sets = board.get("SpawnPointSets")
    if not isinstance(sets, list):
        return None
    idx = int((bc or {}).get("SpawnPointSetIndex") or 0)
    if not 0 <= idx < len(sets):
        return None
    groups = (sets[idx] or {}).get("SpawnPointGroups")
    return groups if isinstance(groups, list) else None
