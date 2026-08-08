"""EQUIPE du joueur COURANT -- foyer UNIQUE de la derivation `ctrl -> team`.

Le natif de reference est `IdunBattle.Entities.UnitExtensions$$IsControlledByCurrentPlayer` :

    if (GetEntityType(unit) != 1 && GetEntityType(unit) != 6) return false;   // UNITE ou MACHINE
    turn = state.<TurnComponent>;
    return OwnerComponent.get_CurrentPlayerEntityId(unit) == TurnComponent.get_CurrentPlayerId(turn);

Le hook publie ce predicat par ligne (`decisionView.units[].ctrl`, `decisionView.mows[].ctrl`), et le
seam offline le reconstitue des deux memes lectures. L'equipe d'une entite CONTROLEE est donc, par
construction, celle du joueur courant -- c'est `TeamComponent.<+0x24>`, l'entree de
`IdunBattle.Core.Services.BattleQuery$$GetPositionMachineForPlayer` -> `GroupForPlayer(teamIndex, ...)`.

POURQUOI CE MODULE EXISTE (#359-r6). La derivation vivait en DEUX exemplaires, sur deux substrats :
`engine/ai/context.py` (une `decisionView` : lignes `units` PUIS `mows`) et
`engine/playbook/prediction/abilities.py` (une `Scene` : `scene.units`). La duplication etait
motivee au site par un CYCLE -- `engine.ai.context` importe deja `engine.playbook.prediction.abilities`
(mesure : `import engine.ai.context` charge 356 modules `engine.*`, dont `prediction.abilities` ;
l'inverse est faux, `abilities` en charge 351 sans jamais toucher `ai.context`). La doctrine des
imports differes tranche : (1) DEPLACER avant (3) DIFFERER, et c'est ce que fait ce module.

Il est une FEUILLE PURE -- ZERO import `engine.*` -- donc il n'ajoute aucune arete au graphe : le
paquet `engine.services` est deja traverse par les DEUX cascades (mesure : `engine.services` dans
la cascade de `ai.context` ET dans celle de `prediction.abilities`, et son `__init__` ne charge
qu'un module, lui-meme).

LE TRI-ETAT SURVIT AU DEPLACEMENT, et c'est le point le plus fragile : `None` = AUCUNE ligne
controlee n'est mesuree, jamais une equipe DEVINEE. Les consommateurs le traduisent chacun en refus
(`CurrentPlayerIsOfTeam` rend False ; le calcul de position de MoW retombe sur son autre canal).
Rabattre `None` sur une equipe par defaut ferait passer pour une mesure ce qui est une ignorance.
"""
from __future__ import annotations


def current_player_team(*row_groups):
    """PREMIERE ligne CONTROLEE (`ctrl` vrai) portant une `team` -> sa `team` ; sinon `None`.

    `row_groups` = un ou plusieurs iterables de lignes-dict, balayes DANS L'ORDRE DONNE. C'est ce
    qui rend le foyer partageable sans imposer un substrat : l'appelant `decisionView` passe
    `(dv["units"], dv["mows"])` -- l'ordre compte, les unites d'abord --, l'appelant `Scene` passe
    `(scene.units,)`. Une ligne sans `team` (`None`) est SAUTEE, pas rendue : le natif ne connait pas
    d'equipe nulle, une telle ligne est une lacune de projection.

    `mows` n'est pas un ajout du port : le gate de tete du natif accepte DEUX types d'entite (1 et 6),
    donc une machine controlee porte le meme verdict qu'une unite controlee."""
    for rows in row_groups:
        for r in (rows or ()):
            if r.get("ctrl") and r.get("team") is not None:
                return r.get("team")
    return None
