"""GARDE #448-r1-r1-r3-r1 -- `movementStartPosition` est un argument DISTINCT de la position
COURANTE, et le port les confondait aux QUATRE places ou `MoveUnitOperation$$Execute` les separe.

LE NATIF, relu sur le build COURANT `t6dpr4k06g` (`IdunBattle.Operations.MoveUnitOperation$$Execute`,
puis `$$CalculatePaths` et `$$UpdateCharging` dont la signature ghidra NOMME le parametre) :

    currentPosition       = EntityExtensions.GetUnitPosition(unit, state);
    prevThisTurn          = EntityExtensions.GetPreviousPositionThisTurn(options, unit);
    movementStartPosition = currentPosition;
    if (UnitPosition.IsEmpty(currentPosition) && prevThisTurn.HasValue
        && !UnitPosition.IsEmpty(prevThisTurn.Value))
        movementStartPosition = prevThisTurn.Value;              // <- LE SECOND BRAS
    endTile   = position.MainTile;
    startTile = endTile;
    if (movementStartPosition != null && movementStartPosition.Count > 0)
        startTile = movementStartPosition[0];

    CalculatePaths(this, unit, movementStartPosition, currentPosition, startTile, endTile,
                   options, out path, out connectedPath);
    ...
    UpdateCharging(this, unit, position, movementStartPosition, unitComponent);

et, dans `CalculatePaths` :

    if (movementStartPosition.Count == 0) { path = connectedPath = [endTile, endTile]; return; }
    ...
    if (UnitPosition.IsEmpty(previousPosition)) pathfinderType = PathfinderType.Fly;   // 3e forceur
    if (options.<+0x8>.HasValue)               pathfinderType = options.<+0x8>.Value;
    path          = Pathfinders.GetPath(pathfinderType, unit, startTile, endTile, useTeleporter);
    connectedPath = BattleQuery.GetConnectedPathTo(unit, startTile, endTile);   // SANS options
    ...
    movementSteps = IsLikeFlying(unit, options) ? GetDistance(path.First(), path.Last())
                                                : path.Count;

CE QUE LA FICHE DU RESIDU DISAIT, ET CE QU'ELLE MANQUAIT. Sa premisse est CONFIRMEE :
`_movement_start_position` etait portee (#1082) et n'avait AUCUN appelant executable -- balayage de
tout `scripts/python`, les deux autres occurrences sont des commentaires. Mais sa << condition de
retournement >> (<< cabler `_movement_start_position` dans `execute` >>) n'aurait PAS suffi a
corriger l'ecart qu'elle CHIFFRE :

  * l'ecart `_num_tiles_moved` **0** au lieu de **1** vient de la branche DEGENEREE, prise quand
    `movementStartPosition` est VIDE -- c'est-a-dire justement quand le cablage ne change rien. Le
    court-circuit `from_pos is None -> 0` de `_num_tiles_moved` reste CORRECT (cette fonction porte
    `GetConnectedPathTo`, que le natif n'appelle jamais dans ce regime) : le defaut appartient au
    rang `CalculatePaths`, donc a `execute`.
  * ouvrir le SECOND BRAS sans porter le 3e forceur `Fly` aurait fait ABANDONNER des mouvements que
    le natif execute (le vol traverse ce que la marche refuse) ;
  * et sans porter `movementSteps = path.Count`, il aurait rendu **0** la ou le natif rend **2** --
    mesure ci-dessous, etage 6.

Et son SUBSTRAT manquait : `RemoveUnitFromTilesOperation` etape 6 (l'ecriture de `@+0x98`) etait
declaree << non portee, faute de lecteur >>, alors que `_movement_start_position` EST ce lecteur
depuis #1082. Sans elle, le second bras n'existait qu'a travers le SEEDING live.

ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

import probe_448r1r1r2r2_gates_abandon as P
from engine.entities.pathfinding import pathfinders as _pf
from engine.runner.components import (PositionComponent, UnitComponent, get_unit_feet,
                                      unit_tiles_moved_this_turn)
from engine.runner.events import EventBus
from engine.runner.operations import movement as MV
from engine.runner.operations.movement import (MoveUnitOperation, _calculate_path,
                                               _movement_start_position, _movement_steps,
                                               _num_tiles_moved)
from engine.runner.operations.remove_unit_from_tiles import RemoveUnitFromTilesOperation

#: Ce fichier ne peut pas changer de verdict sans qu'un de ces chemins bouge. `engine/**` en entier
#: parce que l'etage 0 y BALAIE les appelants de `_movement_start_position` (un module qui cesse de
#: l'appeler, ou qui commence, change le verdict) ; le probe dont on importe le montage ; et le dump
#: de board, dont ce fichier exige DEUX composantes de marche (le temoin non nul de l'etage 5).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/**/*.py",
        "scripts/python/probe_448r1r1r2r2_gates_abandon.py",
        "scripts/python/board.py",
        "data/boards/pvp/C4_09.json",
    ),
    "build": False,
    "toujours": False,
    "raison": "Il garde les QUATRE places ou `MoveUnitOperation$$Execute` distingue "
              "`movementStartPosition` de la position COURANTE (le test de vidite de "
              "`CalculatePaths`, son `startTile`, le 4e argument d'`UpdateCharging`, et le 3e "
              "forceur `Fly` qui lit la position courante) -- plus l'ECRIVAIN du substrat "
              "(`RemoveUnitFromTilesOperation` etape 6). Rien ne depend du build ni du jeu.",
}

BOARD_ID = "C4_09"          # 70 tuiles, DEUX composantes de marche -> le vol traverse, la marche non
ENGINE = pathlib.Path(__file__).resolve().parents[3] / "engine"


@pytest.fixture(scope="module")
def board():
    return P._load_board(BOARD_ID)


@pytest.fixture(scope="module")
def paire(board):
    """`(src, dst)` toutes deux WALKABLE, `dst` INJOIGNABLE A PIED depuis `src` -- mais joignable en
    VOL. C'est le temoin qui separe `path` de `connectedPath`."""
    pr = P.unreachable_pair(board)
    assert pr is not None, (
        "%s n'a qu'UNE composante de marche : les etages 5 et 6 ne mesureraient RIEN." % BOARD_ID)
    return pr


def _hors_plateau(board, passe=None, traits=()):
    """Une unite VIVANTE sans `PositionComponent` -- l'etat que produisent `TeleportingIn` (1035,
    1140, 1238, 1573) et tout `RemoveUnitFromItsTiles`. `passe` seede `@+0x98`."""
    st = P._state(board, [(1, None, 1, list(traits))])
    if passe is not None:
        st.get_entity(1).get_component(UnitComponent).previous_position_this_turn = [tuple(passe)]
    return st


# ------------------------------------------------------------------ 0. LE TEMOIN : un APPELANT
def test_0_movement_start_position_a_desormais_un_appelant_EXECUTABLE():
    """LE RESIDU LUI-MEME, rendu executable. Il disait << PORTEE mais n'a AUCUN appelant >>, et
    c'etait vrai : la fonction etait du code mort, donc AUCUNE des assertions de ce fichier
    n'aurait pu la faire rougir. Le compte est DERIVE de l'AST de tout `engine/**` -- pas d'une
    liste blanche de fichiers, qui ne pourrait pas montrer l'appelant qu'elle a oublie."""
    appels = []
    for p in sorted(ENGINE.rglob("*.py")):
        arbre = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(arbre):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id == "_movement_start_position":
                appels.append("%s:%d" % (p.relative_to(ENGINE.parent).as_posix(), n.lineno))
    assert appels, (
        "`_movement_start_position` n'a AUCUN appelant executable dans `engine/**` : elle est "
        "redevenue le code mort que #448-r1-r1-r3-r1 decrivait, et tout ce fichier mesure alors "
        "des fonctions que `MoveUnitOperation.execute` n'emprunte pas.")


# ------------------------------------------------------- 1. VALUE-PRESERVING dans le NOMINAL
def test_1_sur_le_plateau_le_start_tile_EST_la_position_courante(board):
    """Ce qui rend le cablage sur -- et ce n'est pas un espoir, c'est une propriete de l'ECRIVAIN
    UNIQUE : `set_unit_feet` recale `pc.col,pc.row = feet[0]`, donc `feet[0] == (pc.col, pc.row)`
    pour TOUTE unite posee. Balaye tout le board, pas un echantillon."""
    neigh, walk, _ = board.walk_maps_by_pos()
    poses = [p for p, w in sorted(walk.items()) if w]
    assert len(poses) > 20, "moins de 21 tuiles marchables : balayage trop maigre"
    for pos in poses:
        st = P._state(board, [(1, pos, 1, [])])
        pc = st.get_entity(1).get_component(PositionComponent)
        assert _movement_start_position(st, 1) == [(pc.col, pc.row)] == get_unit_feet(st, 1)


def test_1b_un_pas_NOMINAL_rend_exactement_ce_qu_il_rendait(board):
    """Non-regression du regime CONFRONTE LIVE (#448-r1-r1-r1, la greffe de `FullThrottle`). Un pas
    d'une tuile : `path` a deux noeuds, `movementSteps = path.Count = 2`, `tilesMoved = 1`."""
    neigh, walk, _ = board.walk_maps_by_pos()
    a = next(p for p, w in sorted(walk.items()) if w and neigh.get(p))
    b = next(q for q in neigh[a] if walk.get(q))
    st = P._state(board, [(1, a, 1, [])])
    op = MoveUnitOperation(1, b)
    op.execute(st, EventBus())
    assert op.last_path == [a, b]
    assert op.last_movement_steps == 2
    assert unit_tiles_moved_this_turn(st, 1) == 1
    assert P._pos(st, 1) == b


# --------------------------------------------------- 2. LA BRANCHE DEGENEREE (`Count == 0`)
def test_2_hors_plateau_SANS_passe_les_DEUX_listes_valent_end_end(board, paire):
    """`if (movementStartPosition.Count == 0) { path = connectedPath = [endTile, endTile]; }`

    Le port ne portait cette branche que pour `path`. Cote `connectedPath`, `_num_tiles_moved`
    court-circuitait a `0` sur `from_pos is None` -- donc `RecordTilesMoved(0)` la ou le natif
    ecrit `GetNumTilesMoved([end, end]) = 1`, et `movementSteps = 0` la ou il rend `path.Count = 2`.
    C'est l'ecart CHIFFRE par la fiche du residu."""
    _, dst = paire
    st = _hors_plateau(board)
    assert _movement_start_position(st, 1) == [], "montage inerte : l'unite a un passe"
    op = MoveUnitOperation(1, dst)
    op.execute(st, EventBus())
    assert op.last_path == [dst, dst], (
        "la branche degeneree ne rend pas `[endTile, endTile]` : %r" % (op.last_path,))
    assert unit_tiles_moved_this_turn(st, 1) == 1, (
        "`RecordTilesMoved` a recu %d au lieu de 1 : la branche degeneree de `CalculatePaths` n'est "
        "portee que pour `path`, pas pour `connectedPath` (#448-r1-r1-r3-r1 E2)."
        % unit_tiles_moved_this_turn(st, 1))
    assert op.last_movement_steps == 2, (
        "`movementSteps` vaut %r au lieu de `path.Count` = 2 (#448-r1-r1-r3-r1 E2)."
        % (op.last_movement_steps,))


def test_2b_le_court_circuit_de_num_tiles_moved_reste_CORRECT(board, paire):
    """CONTRE-EPREUVE, et elle protege un port qu'on serait tente de << corriger >>.
    `_num_tiles_moved` porte `GetNumTilesMoved(GetConnectedPathTo(unit, startTile, endTile))`, et
    le natif n'appelle JAMAIS `GetConnectedPathTo` quand `movementStartPosition` est vide : la
    branche degeneree court-circuite AVANT. Son `0` n'est donc pas le bug -- le rang l'etait."""
    _, dst = paire
    st = _hors_plateau(board)
    assert _num_tiles_moved(st, 1, None, dst) == 0


def test_2c_un_VOLANT_degenere_rend_0_pas_2(board, paire):
    """L'autre bras de `movementSteps` sur la MEME liste : `GetDistance(path.First(), path.Last())`
    = `GetDistance(endTile, endTile)` = **0**. Il n'est juste que si la distance est prise sur les
    extremites du CHEMIN et non sur `(from_pos, to_pos)`, qui vaudraient `(None, dst)`."""
    _, dst = paire
    st = _hors_plateau(board, traits=["Flying"])
    op = MoveUnitOperation(1, dst)
    op.execute(st, EventBus())
    assert op.last_path == [dst, dst]
    assert op.last_movement_steps == 0, (
        "un volant hors plateau rend %r au lieu de `GetDistance(end, end)` = 0"
        % (op.last_movement_steps,))


# ------------------------------------------- 3. LE SECOND BRAS + le 3e forceur `Fly` (E1, E3)
def test_3_le_second_bras_prend_la_tuile_QUITTEE_CE_TOUR(board, paire):
    """`movementStartPosition = prevThisTurn.Value` quand la position courante est VIDE."""
    src, _ = paire
    st = _hors_plateau(board, passe=src)
    assert _movement_start_position(st, 1) == [src]


def test_3b_le_forceur_Fly_fait_ABOUTIR_un_mouvement_que_la_MARCHE_refuse(board, paire):
    """LE TEMOIN NON NUL du 3e forceur, et il est binaire : `dst` est dans une AUTRE composante de
    marche que `src`. Sans `if (IsEmpty(previousPosition)) pathfinderType = Fly`, `CalculatePaths`
    rendrait `path = null` et `Execute` ABANDONNERAIT le mouvement (`RemoveReservation ; return`).
    Avec, le vol traverse et l'unite arrive."""
    src, dst = paire
    neigh, walk, elev = board.walk_maps_by_pos()
    assert walk.get(dst) is True, "dst non marchable : le gate AMONT suffirait, regime degenere"
    assert _calculate_path(_hors_plateau(board, passe=src), 1, src, dst) is None, (
        "SANS le forceur, la marche doit rendre `None` -- sinon les deux tuiles sont dans la meme "
        "composante et cet etage ne mesure rien")
    st = _hors_plateau(board, passe=src)
    op = MoveUnitOperation(1, dst)
    op.execute(st, EventBus())
    assert op.last_abandoned == "", (
        "le mouvement a ete ABANDONNE (%r) : le 3e forceur `Fly` de `CalculatePaths` n'est pas "
        "porte, ou `previous_position_is_empty` ne remonte pas jusqu'a lui (#448-r1-r1-r3-r1 E3)."
        % (op.last_abandoned,))
    assert P._pos(st, 1) == dst
    # ⚠ ABOUTIR NE SUFFIT PAS -- et sans ce cran ce test etait VERT sur le port d'AVANT, pour la
    # mauvaise raison : il prenait la branche DEGENEREE (`movementStartPosition` cru vide parce que
    # la position courante l'est), qui rend `[endTile, endTile]` et n'abandonne donc jamais. On
    # exige que le chemin soit un VRAI vol, c'est-a-dire qu'il parte d'ailleurs que de l'arrivee.
    assert op.last_path != [dst, dst], (
        "le mouvement aboutit par la branche DEGENEREE, pas par le vol : `movementStartPosition` "
        "n'a pas pris son second bras (#448-r1-r1-r3-r1 E1).")


def test_3c_le_chemin_du_second_bras_part_de_la_tuile_QUITTEE(board, paire):
    """Le `startTile = movementStartPosition[0]` : le chemin ne part PAS de la destination."""
    src, dst = paire
    st = _hors_plateau(board, passe=src)
    op = MoveUnitOperation(1, dst)
    op.execute(st, EventBus())
    assert op.last_path and op.last_path[0] == src and op.last_path[-1] == dst, (
        "chemin %r : il devrait partir de la tuile quittee %r" % (op.last_path, src))


# --------------------------------------------------------------- 4. LE SUBSTRAT (etape 6)
def test_4_remove_unit_from_tiles_ECRIT_la_position_quittee(board):
    """Etape 6 de `RemoveUnitFromTilesOperation$$Execute` : les deux `Nullable<UnitPositionId>`
    recoivent la position sauvegardee en etape 2. Sans elle, le second bras ci-dessus n'existe QUE
    par le seeding live -- une simulation pure ne le produit jamais."""
    neigh, walk, _ = board.walk_maps_by_pos()
    a = next(p for p, w in sorted(walk.items()) if w and neigh.get(p))
    st = P._state(board, [(1, a, 1, [])])
    uc = st.get_entity(1).get_component(UnitComponent)
    assert not uc.previous_position_this_turn, "montage inerte : la position est deja seedee"
    RemoveUnitFromTilesOperation.execute(st, 1)
    assert P._pos(st, 1) is None, "l'unite est encore sur le plateau : le retrait n'a pas mordu"
    assert uc.previous_position_this_turn == [a], (
        "`@+0x98` vaut %r au lieu de la tuile quittee %r -- l'etape 6 n'est pas portee, et "
        "`_movement_start_position` n'a alors aucun substrat en simulation pure."
        % (uc.previous_position_this_turn, a))
    # ... et le chainage : l'unite retiree peut REPARTIR de la tuile qu'elle vient de quitter.
    assert _movement_start_position(st, 1) == [a]


def test_4b_un_SECOND_retrait_EFFACE_la_position_gardee(board):
    """L'ecriture native est INCONDITIONNELLE (pas de gate `Count < 1`, contrairement a
    `SetUnitPositionOperation$$SavePreviousPosition`). Conserver l'ancienne valeur ferait prendre au
    second bras une tuile quittee il y a longtemps."""
    neigh, walk, _ = board.walk_maps_by_pos()
    a = next(p for p, w in sorted(walk.items()) if w and neigh.get(p))
    st = P._state(board, [(1, a, 1, [])])
    RemoveUnitFromTilesOperation.execute(st, 1)
    assert st.get_entity(1).get_component(UnitComponent).previous_position_this_turn == [a]
    RemoveUnitFromTilesOperation.execute(st, 1)
    assert st.get_entity(1).get_component(UnitComponent).previous_position_this_turn == [], (
        "le second retrait a CONSERVE la position : `_movement_start_position` prendrait son second "
        "bras sur une tuile que l'unite ne quitte pas maintenant.")


# ------------------------------------------------- 5. `UpdateCharging` recoit le MEME argument
def test_5_update_charging_compare_a_la_tuile_QUITTEE_pas_a_du_vide(board):
    """`UpdateCharging(this, unit, position, movementStartPosition, unitComponent)` -- la signature
    ghidra NOMME son 4e parametre. Une unite deja au contact AVANT le pas ne doit pas compter comme
    << chargee >>. Avec `old_pos = None`, `before` etait VIDE et tout voisin de l'arrivee comptait.

    Le montage exige un triangle `a -- b -- c` : le mover part de `a` (sa tuile quittee), arrive en
    `b`, et l'ennemi en `c` est adjacent aux DEUX."""
    neigh, walk, _ = board.walk_maps_by_pos()
    triangle = None
    for a in sorted(walk):
        if not walk.get(a):
            continue
        vois = [q for q in (neigh.get(a) or ()) if walk.get(q)]
        for b in vois:
            for c in vois:
                if c != b and c in (neigh.get(b) or ()):
                    triangle = (a, b, c)
                    break
            if triangle:
                break
        if triangle:
            break
    assert triangle is not None, "pas de triangle de tuiles marchables sur %s" % BOARD_ID
    a, b, c = triangle

    st = P._state(board, [(1, None, 1, []), (2, c, 2, [])])       # 1 hors plateau, 2 = ENNEMI
    st.get_entity(1).get_component(UnitComponent).previous_position_this_turn = [a]
    MoveUnitOperation(1, b).execute(st, EventBus())
    charges = list(st.get_entity(1).get_component(UnitComponent).charged_unit_ids or ())
    assert 2 not in charges, (
        "l'ennemi %r, DEJA adjacent a la tuile quittee %r, est compte comme charge -- "
        "`UpdateCharging` a recu la position COURANTE (vide) au lieu de `movementStartPosition` "
        "(#448-r1-r1-r3-r1 E5). charged=%r" % (c, a, charges))


# ------------------------------------------ 6. `movementSteps` vient de `path`, pas du COMPTE
def test_6_movement_steps_lit_path_Count_pas_le_compte_de_connectedPath(board, paire):
    """`movementSteps = path.Count` -- la liste que `CalculatePaths` a produite AVEC les forceurs.
    `connectedPath`, lui, vient de `GetConnectedPathTo(unit, from, to)` (TROIS arguments) et ne les
    voit PAS. Dans le second bras les deux DIVERGENT jusqu'a l'extreme : le vol aboutit, la marche
    n'aboutit pas du tout.

    TEMOIN NON NUL exige : le compte de marche doit valoir 0 ici, sinon les deux sources
    coincideraient et l'assertion serait vide."""
    src, dst = paire
    st = _hors_plateau(board, passe=src)
    assert _num_tiles_moved(st, 1, src, dst) == 0, (
        "le compte de MARCHE n'est pas nul : les deux sources coincident et cet etage ne separe "
        "rien -- choisir une autre paire.")
    op = MoveUnitOperation(1, dst)
    op.execute(st, EventBus())
    assert op.last_path is not None
    assert op.last_movement_steps == len(op.last_path), (
        "`movementSteps` = %r au lieu de `path.Count` = %d : il est encore derive de "
        "`connectedPath` (#448-r1-r1-r3-r1 E4)." % (op.last_movement_steps, len(op.last_path)))
    assert op.last_movement_steps >= 2


def test_6b_sans_board_le_port_ne_FABRIQUE_pas_un_pas(board):
    """TRI-ETAT. Sans board, `_calculate_path` rend son repli PERMISSIF `[from, to]` : en tirer
    `path.Count = 2` transformerait une NON-MESURE en pas parcouru. `MoveUnitOperation.execute` ne
    fournit donc `path` a `_movement_steps` que si le port a un board."""
    st = P._state(board, [(1, (0, 0), 1, [])])
    st.board = None
    op = MoveUnitOperation(1, (0, 1))
    op.execute(st, EventBus())
    assert op.last_path == [(0, 0), (0, 1)]          # le repli PERMISSIF, pour que le gate ne morde pas
    assert op.last_movement_steps == 0, (
        "sans board, `movementSteps` vaut %r : le port fabrique un pas depuis une non-mesure."
        % (op.last_movement_steps,))


def test_6c_appele_SANS_path_la_fonction_garde_son_contrat(board):
    """Les probes et tests qui invoquent `_movement_steps` hors `Execute` ne fournissent pas de
    chemin : leur contrat ne bouge pas (c'est ce qui rend `path` un AJOUT, pas une reecriture)."""
    neigh, walk, _ = board.walk_maps_by_pos()
    a = next(p for p, w in sorted(walk.items()) if w and neigh.get(p))
    b = next(q for q in neigh[a] if walk.get(q))
    st = P._state(board, [(1, a, 1, [])])
    assert _movement_steps(st, 1, a, b) == 2
    assert _movement_steps(st, 1, a, b, path=[a, b]) == 2
    assert _movement_steps(st, 1, None, b) == 0


# ------------------------------------------------------ 7. GENERALISATION (anti sur-ajustement)
def test_7_la_CHAINE_COMPLETE_bouger_puis_QUITTER_puis_revenir(board):
    """LE SCENARIO QUE PERSONNE N'AVAIT MONTE, et il enchaine les trois etages a la suite --
    c'est le regime que produisent `GhostRevive`, `EchoesFromTheWarp` et `StormboyzStrike_Fallback`
    en bataille reelle, pas un montage synthetique :

        1. l'unite bouge NORMALEMENT       -> `save_previous_position` ecrit `@+0x98`
        2. elle est RETIREE du plateau     -> l'etape 6 REECRIT `@+0x98` avec la tuile QUITTEE
        3. elle bouge de nouveau           -> le SECOND BRAS part de cette tuile-la

    Le cran qui compte est l'etape 2 : sans elle, l'etape 3 repartirait de la position d'AVANT le
    mouvement de l'etape 1, c'est-a-dire d'une tuile que l'unite a quittee DEUX fois."""
    neigh, walk, _ = board.walk_maps_by_pos()
    a = next(p for p, w in sorted(walk.items()) if w and len(neigh.get(p) or ()) >= 2)
    voisins = [q for q in neigh[a] if walk.get(q)]
    b, c = voisins[0], voisins[1]
    st = P._state(board, [(1, a, 1, [])])
    uc = st.get_entity(1).get_component(UnitComponent)

    MoveUnitOperation(1, b).execute(st, EventBus())                  # 1
    assert P._pos(st, 1) == b
    assert uc.previous_position_this_turn == [a], uc.previous_position_this_turn

    RemoveUnitFromTilesOperation.execute(st, 1)                      # 2
    assert uc.previous_position_this_turn == [b], (
        "apres le retrait, `@+0x98` vaut %r au lieu de la tuile QUITTEE %r -- l'etape 6 n'a pas "
        "reecrit, et le pas suivant repartirait de la position d'AVANT le 1er mouvement."
        % (uc.previous_position_this_turn, b))

    op = MoveUnitOperation(1, c)                                     # 3
    op.execute(st, EventBus())
    assert op.last_path and op.last_path[0] == b, (
        "le second bras part de %r au lieu de la tuile quittee %r" % (op.last_path, b))
    assert P._pos(st, 1) == c


def test_7b_une_unite_MULTI_HEX_reste_value_preservante(board):
    """`_movement_start_position` rend l'EMPREINTE ENTIERE (`GetUnitFeet`), et `startTile` en prend
    le PREMIER element -- `movementStartPosition[0]`, c'est-a-dire la main tile. Sur une unite
    multi-hex, `set_unit_feet` recale `pc.col,pc.row = tiles[0]` : le cablage doit donc rendre
    exactement `old_pos`, comme en mono-hex. Sans ce controle, le `[0]` pourrait designer un pied
    quelconque et l'ecart ne se verrait que sur une unite a trois pieds."""
    from engine.runner.components import set_unit_feet
    neigh, walk, _ = board.walk_maps_by_pos()
    a = next(p for p, w in sorted(walk.items()) if w and len(neigh.get(p) or ()) >= 2)
    pieds = [a] + [q for q in neigh[a] if walk.get(q)][:1]
    st = P._state(board, [(1, a, 1, [])])
    set_unit_feet(st, 1, pieds)
    assert len(get_unit_feet(st, 1)) == len(pieds) > 1, "montage inerte : l'unite est mono-hex"
    pc = st.get_entity(1).get_component(PositionComponent)
    assert _movement_start_position(st, 1) == pieds
    assert _movement_start_position(st, 1)[0] == (pc.col, pc.row)


@pytest.mark.parametrize("autre_board", ["MC1_67", "C3_26"])
def test_7c_le_verdict_ne_depend_pas_de_CE_board(autre_board):
    """GENERALISATION GEOMETRIQUE. `C4_09` a ete choisi pour ses DEUX composantes de marche -- une
    propriete rare (242 dumps sur 779). Les etages 1, 2 et 4 ne dependent pas d'elle : on les
    rejoue sur deux boards ORDINAIRES pour verifier qu'on n'a pas ajuste le port a une geometrie.

    ⚠ Ce que ce parametrage NE couvre pas, et c'est dit : le bras `Fly` de l'etage 3b exige deux
    composantes, donc il reste mesure sur `C4_09` seul."""
    from engine.runner.operations.triggers.tiles import tile_defense_mod
    bd = P._load_board(autre_board)
    neigh, walk, _ = bd.walk_maps_by_pos()

    def _neutre(p):
        """Tuile SANS stat-mod DEFENSE de terrain. ⚠ MONTAGE, pas fidelite : le `_state` du probe
        #448-r2b construit un `UnitContext` NU (`__new__`, seuls `traits` comptent), et le vecteur
        `apply_tile_defense_on_move` y leve des qu'une transition change le mod -- `C3_26` en porte,
        `C4_09` et `MC1_67` n'en ont pas sur leurs premieres tuiles. Restreindre la paire aux
        tuiles neutres garde ce test sur SON sujet ; le vecteur terrain a ses propres gardes."""
        return tile_defense_mod(bd.terrain_at(p[0], p[1])) == 0

    paires = ((p, q) for p, w in sorted(walk.items()) if w and _neutre(p)
              for q in (neigh.get(p) or ()) if walk.get(q) and _neutre(q))
    a, b = next(paires, (None, None))
    assert a is not None, "aucune paire de tuiles neutres sur %s : montage impossible" % autre_board
    # 1. nominal : value-preservant
    st = P._state(bd, [(1, a, 1, [])])
    assert _movement_start_position(st, 1) == [a]
    op = MoveUnitOperation(1, b)
    op.execute(st, EventBus())
    assert (op.last_path, op.last_movement_steps, unit_tiles_moved_this_turn(st, 1)) == ([a, b], 2, 1)
    # 2. degenere : `[end, end]`, 2 pas, 1 tuile
    st2 = P._state(bd, [(1, None, 1, [])])
    op2 = MoveUnitOperation(1, b)
    op2.execute(st2, EventBus())
    assert (op2.last_path, op2.last_movement_steps, unit_tiles_moved_this_turn(st2, 1)) \
        == ([b, b], 2, 1)
    # 4. substrat : le retrait ecrit la tuile quittee
    st3 = P._state(bd, [(1, a, 1, [])])
    RemoveUnitFromTilesOperation.execute(st3, 1)
    assert st3.get_entity(1).get_component(UnitComponent).previous_position_this_turn == [a]


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
