"""`MachineOfWarPosition` d'un JOUEUR — le slot de plateau, PAS une machine deployee.

Pourquoi ce module existe (RE #302 tranche 3, mesuree le 2026-07-30)
--------------------------------------------------------------------
Le predicat `IdunBattleLogic.Entities.DSLFactory$$IsPositionMachineForCurrentPlayer` ->
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
des plateaux. Le port ne devine pas : il lit les groupes quand on les lui donne, et rend `None`
(= inconnu) sinon (cf. `engine.ai.context.AiDecisionContext.machine_of_war_position`).
"""
from __future__ import annotations

# `MachineOfWarPosition` (enum natif) : 0 = None, 1 = Top, 2 = Bottom.
MOW_POSITION_NONE = 0
MOW_POSITION_TOP = 1
MOW_POSITION_BOTTOM = 2


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
