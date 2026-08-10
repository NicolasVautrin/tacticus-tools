"""CONFRONTATION LIVE du gate G2 `IdunBattle.Operations.MoveUnitOperation$$UnitIsOnTiles`
(#448-r1-r1-r2-r2-r1).

**C'est le SEUL des sept gates amont qui soit drivable de l'exterieur.** Les six autres exigent une
destination qu'`applyAction {kind:"move"}` ne laisse pas passer (non walkable, reservee, vide) --
la validation d'entree native filtre AVANT `Execute`, mesure #448-r1-r1-r2-r2 §7.2. G2, lui, se
demande avec une coordonnee parfaitement legale : la tuile COURANTE de l'unite.

DISCRIMINANT, OBSERVABLE, et il MORD (mesure `MC1_67`/777) :

    natif           move (1,0) -> (1,0) : pos inchangee, unitFlags []      -> []
    CONTROLE        move (1,0) -> (2,0) : pos (2,0),     unitFlags []      -> [0, 1, 4]
    port gates ON   idem (1,0) -> (1,0) : Moved=False, abandon='unit-is-on-tiles'   ACCORD
    port gates OFF  idem                : Moved=True                                DESACCORD

`gates OFF` est litteralement le port d'AVANT cette tranche. Le flag `Moved` n'est pas cosmetique :
il ferme la regle de ciblage `CasterHasNotMoved` de tout cast ulterieur du MEME tour -- la
degradation etait silencieuse ET consequente.

Le montage vit dans `probe_448r1r1r2r2r1_gates_amont.volet_live` (fixture NOMMEE, reutilisable) :
build du runner, dispose garanti par `finally`, controle positif obligatoire.
"""
from __future__ import annotations

import probe_448r1r1r2r2r1_gates_amont as P

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/operations/movement.py",
        "scripts/python/engine/runner/operations/tile_reservation.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/probe_448r1r1r2r2r1_gates_amont.py",
        "scripts/python/probe_448r1r1r2r2_gates_abandon.py",
        "scripts/python/rl_duel.py",
        # `scripts/python/board.py` (le choix de board du runner) est importe par ce
        # fichier ; son absence rendait le declencheur TROP ETROIT --
        # `probe_486r15_declencheurs_tests.py` le disait, sur `master`, depuis #869.
        # Ne pas le confondre avec `engine/entities/pathfinding/board.py`, homonyme.
        "scripts/python/board.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confronte le PORT (`movement.py`) au NATIF sur un runner reel : depend du build du "
              "jeu (canal `combatSnapshot.units[].unitFlags`) et du montage de runner (`rl_duel`).",
}

BOARD = "MC1_67"
SEED = 777


def test_g2_unit_is_on_tiles_accord_avec_le_natif():
    """Trois bras, dont le CONTROLE POSITIF -- sans lui, « le natif n'a pas pose Moved » se lirait
    comme un verdict alors que ce pourrait etre un montage inerte."""
    assert P.volet_live(BOARD, SEED) == 0
