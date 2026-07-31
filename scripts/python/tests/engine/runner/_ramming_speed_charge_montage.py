"""Montage NOMME de la CHARGE `RammingSpeed` (1059) — 100 % OFFLINE, deterministe (#353-r1).

Pourquoi un montage et pas un `@fixture` inline : les deux proprietes a garder sous cliquet
(`RammingSpeed_MostAdjacentEnemies(54)` TRANCHE / l'ORDRE des operandes de l'intersection TRANCHE)
exigent la MEME bataille a un detail pres — la position du SECOND ennemi. Un montage parametre par
cette seule position rend les deux cas comparables terme a terme.

Pourquoi OFFLINE : `IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$GetTileToMoveTo`
est une fonction PURE de l'etat (board + positions + camps). Le montage la fait tourner sur un board
hex SYNTHETIQUE plat, donc `Tile(7)` y est CONSTANT et le classement ne peut venir que du 2e terme du
bucket, ou — a egalite parfaite — de l'ordre du selecteur source. C'est exactement la separation par
etage que la doctrine demande : aucun scalaire n'est fitte, chaque cas nomme le terme qui tranche.

Le montage NE REMPLACE PAS la confrontation live (position d'arrivee du caster apres un cast natif
de 1059, cf. `probe_353r1_ramming_speed_charge_tile.py`) : il la PRECEDE et la rend interpretable.

GEOMETRIE (board 7x7 plat, `hexgeo` = even-q ; id de tuile = col*7 + row + 1)

    cible T  = (3,3)        ring(T) = hexgeo.neighbors(3,3)
                                    = [(3,4), (3,2), (4,3), (4,2), (2,3), (2,2)]
    caster C = (0,3)        distance >= 2 de T -> l'etage MOVE natif s'arme. Position CHOISIE, pas
                            subie : depuis (0,0) le pathfinder ne rejoint plus (3,4) quand (2,3) est
                            occupee par le 2e ennemi (un ennemi BLOQUE la traversee), et le pool
                            amputerait le cas B de sa 2e tuile ex aequo.
    ennemi E = <parametre>  une tuile DU ring, donc RETIREE des candidates par `CanAddUnit`,
                            et qui ajoute +1 ennemi adjacent aux deux candidates qui la touchent

Les deux ordres sources possibles, mesures sur ce board :
    `MovableTilesInRange` (l'operande GAUCHE de RammingSpeed)  -> ids CROISSANTS
    `CanAddUnit(AdjacentTiles(T))` (celui du helper `TilesUnitCanMoveToChargeTarget`, = Waaagh)
                                                               -> ordre `neighbours_native(T)`
Ils ne coincident PAS, et l'`OrderBy` de `SortTilesByUtilitySelector` etant STABLE, ils designent des
tuiles differentes des qu'il y a egalite d'utilite.

ASCII only.
"""
from __future__ import annotations

from dataclasses import dataclass

import hexgeo

COLS, ROWS = 7, 7
TARGET_POS = (3, 3)
CASTER_POS = (0, 3)
ALLY_POS = (0, 6)          # allie du caster, LOIN : ne touche aucune candidate

CASTER_VIS = "orksKillaKan"     # greffon etabli par #353 (case-92 sec.5bis) ; ici seul son camp compte
TARGET_VIS = "necroWarden"
ENEMY2_VIS = "ultraTitus"
ALLY_VIS = "astraBullgryn"

CASTER_ID, TARGET_ID, ENEMY2_ID, ALLY_ID = 10, 20, 30, 40


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    """Board 7x7 PLAT (elevation 0 partout, tout marchable). `neighbours` = `hexgeo.neighbors`,
    donc `neighbours_native` rend l'ordre hexgeo et `adjacency='evenq'` recalcule la meme
    topologie -- les deux vues du board sont coherentes par construction."""
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


@dataclass
class ChargeMontage:
    """Etat livre par le montage."""
    state: object
    board: object
    caster_id: int
    target_id: int
    enemy2_pos: tuple
    candidates: list          # ids de tuile, dans l'ordre du selecteur NATIF de RammingSpeed


def build_charge_montage(enemy2_pos: tuple, move_range: int = 5) -> ChargeMontage:
    """Monte la bataille synthetique et rend l'etat + le pool de charge.

    `enemy2_pos` DOIT etre une tuile du ring de la cible : c'est ce qui la retire des candidates
    (`CanAddUnit`) tout en donnant +1 ennemi adjacent aux deux candidates voisines. `move_range` = la
    constante `abilities.RammingSpeed.constants.range` (5) ; le board fait 7x7, donc toutes les
    candidates sont atteignables et le pool est le ring COMPLET prive des tuiles occupees."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.abilities.behaviours import entities_from_state
    from engine.runner.abilities.orks import ramming_speed_charge_tiles_selector

    if hexgeo.distance(tuple(enemy2_pos), TARGET_POS) != 1:
        raise ValueError("enemy2_pos doit etre un VOISIN de la cible (sinon elle ne quitte pas "
                         "les candidates et le montage ne teste pas ce qu'il annonce)")
    board = Board(_tiles(), adjacency="evenq")
    decision = {
        "currentPlayer": 1,
        "units": [
            {"id": CASTER_ID, "visualId": CASTER_VIS, "alive": True, "team": 1, "owner": 1,
             "pos": {"col": CASTER_POS[0], "row": CASTER_POS[1]}, "effects": []},
            {"id": ALLY_ID, "visualId": ALLY_VIS, "alive": True, "team": 1, "owner": 1,
             "pos": {"col": ALLY_POS[0], "row": ALLY_POS[1]}, "effects": []},
            {"id": TARGET_ID, "visualId": TARGET_VIS, "alive": True, "team": 2, "owner": 2,
             "pos": {"col": TARGET_POS[0], "row": TARGET_POS[1]}, "effects": []},
            {"id": ENEMY2_ID, "visualId": ENEMY2_VIS, "alive": True, "team": 2, "owner": 2,
             "pos": {"col": int(enemy2_pos[0]), "row": int(enemy2_pos[1])}, "effects": []},
        ],
    }
    observe = {"units": [{"squadId": u["id"], "hp": 100000, "hpMax": 100000}
                         for u in decision["units"]]}
    state = load_state(decision, observe, board=board)
    cands = ramming_speed_charge_tiles_selector(move_range).evaluate(
        entities_from_state(state, CASTER_ID, TARGET_ID))
    return ChargeMontage(state=state, board=board, caster_id=CASTER_ID, target_id=TARGET_ID,
                         enemy2_pos=tuple(enemy2_pos), candidates=list(cands))
