"""GARDE des DEUX GATES D'ABANDON de `IdunBattle.Operations.MoveUnitOperation$$Execute`
(#448-r1-r1-r2-r2 pour `path` vide, #448-r1-r2 pour `TilesAreEmpty`) et de la TRACE du crush
(#462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r3).

Le montage vit dans le probe (`probe_448r1r1r2r2_gates_abandon.py`), que ce fichier IMPORTE : pas
de fork. Cinq etages, plus un CLIQUET qui est la vraie valeur du fichier.

⚠ LE CLIQUET (etage 6) est ce qui MAINTIENT le port, pas ce qui le vise. Les deux gates sont
PERMISSIFS quand ils manquent -- un call-site neuf qui n'aurait pas dit s'il mirroite
`MoveUnitOperation$$Execute` ou `SetUnitPositionOperation$$Execute` rouvrirait le gisement EN
SILENCE : rien ne casserait, l'unite bougerait simplement la ou le natif refuse. C'est la meme
forme de degradation que « entrer au registre SANS son masque de ciblage », et le meme remede :
DECLARER dans le meme commit.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

import probe_448r1r1r2r2_gates_abandon as P
from engine.entities.pathfinding.walk_pathfinder import (get_path_by_pos,
                                                         get_path_node_counts_by_pos)
from engine.entities.traits.unit_trait import UnitTrait
from engine.runner.components import PositionComponent, UnitComponent
from engine.runner.events import EventBus
from engine.runner.operations.movement import MoveUnitOperation

#: Ce fichier ne peut pas changer de verdict SANS qu'un de ces chemins bouge. Il est volontairement
#: LARGE (trop large est sain, trop etroit est un faux vert) : le cliquet AST de l'etage 6 balaie
#: `engine/**` en entier -- tout module qui INSTANCIE `MoveUnitOperation`, ou qui cesse de le faire,
#: le fait changer de verdict. S'y ajoutent les entrees LUES : le dump de board, et le probe dont ce
#: fichier importe le montage.
DECLENCHEUR = {
    "chemins": (
        # LA CASCADE DES `conftest.py` N'EST PLUS ICI (#531, arrive avec #823 pendant que cette
        # tranche etait en vol) : le foyer la DERIVE. Les quatre chemins recopies a cette place
        # etaient justes -- la derivation rend un sur-ensemble strict.
        "scripts/python/engine/**/*.py",
        "scripts/python/probe_448r1r1r2r2_gates_abandon.py",
        # `board.py` : la fermeture y passe PAR le probe ci-dessus (`_load_board`). Declarer le
        # probe ne declare PAS ce qu'il importe -- meme lecon que la cascade de harnais (#531),
        # sur une arete que le foyer ne derive pas (elle est PROPRE a ce fichier).
        "scripts/python/board.py",
        "data/boards/pvp/C4_09.json",
    ),
    "build": False,
    "toujours": False,
    "raison": "Tout `engine/**` : le cliquet AST de l'etage 6 y balaie chaque site qui INSTANCIE "
              "`MoveUnitOperation` -- un module qui cesse de le faire, ou qui commence, change le "
              "verdict. S'y ajoutent les deux entrees LUES : le probe dont ce fichier importe le "
              "montage, et le dump de board `C4_09` dont il exige les DEUX composantes de marche. "
              "Aucune dependance au build ni au jeu.",
}

BOARD_ID = "C4_09"          # 70 tuiles, DEUX composantes de marche dans le dump `data/boards/`


@pytest.fixture(scope="module")
def board():
    return P._load_board(BOARD_ID)


@pytest.fixture(scope="module")
def paire(board):
    """`(src, dst)` toutes deux WALKABLE, `dst` INJOIGNABLE a la marche depuis `src`."""
    pr = P.unreachable_pair(board)
    assert pr is not None, (
        "%s n'a qu'UNE composante de marche : le montage n'exerce RIEN. Choisir un autre board "
        "(242 des 779 dumps en ont plusieurs) plutot que d'affaiblir l'assertion." % BOARD_ID)
    return pr


def _voisine_libre(board):
    neigh, walk, _ = board.walk_maps_by_pos()
    a = next(p for p, w in sorted(walk.items()) if w and neigh.get(p))
    return a, next(q for q in neigh[a] if walk.get(q))


# ----------------------------------------------------------------- 1. le substrat MESURE
def test_1_la_destination_est_walkable_ET_injoignable(board, paire):
    """Le regime n'est pas degenere : la destination PASSE le gate AMONT `TilesAreWalkable` et
    echoue quand meme sur `CalculatePaths`. Sans ce controle, un `path` vide se lirait comme le
    refus d'un gate amont -- et le port n'aurait rien a ajouter."""
    src, dst = paire
    neigh, walk, elev = board.walk_maps_by_pos()
    assert walk.get(dst) is True, "dst non walkable : le gate AMONT suffirait, regime degenere"
    assert get_path_by_pos(src, dst, neigh_by_pos=neigh, walkable_by_pos=walk,
                           elev_by_pos=elev) is None


def test_1b_get_path_by_pos_est_le_MEME_moteur_que_les_comptes(board):
    """`get_path_by_pos` et `get_path_node_counts_by_pos` sortent d'un unique `_dijkstra_by_pos` :
    la LONGUEUR du chemin doit egaler le COMPTE, pour TOUTE destination joignable. Un second port
    du pathfinding divergerait ici -- c'est exactement ce que la factorisation interdit."""
    neigh, walk, elev = board.walk_maps_by_pos()
    src = next(p for p, w in sorted(walk.items()) if w and neigh.get(p))
    counts = get_path_node_counts_by_pos(src, neigh_by_pos=neigh, walkable_by_pos=walk,
                                         elev_by_pos=elev)
    assert len(counts) > 5, "moins de 6 destinations joignables : le montage n'exerce presque rien"
    for dst, n in counts.items():
        path = get_path_by_pos(src, dst, neigh_by_pos=neigh, walkable_by_pos=walk, elev_by_pos=elev)
        assert path is not None and len(path) == n, (dst, n, path)
        assert path[0] == src and path[-1] == dst


# ----------------------------------------------------------------- 2. GATE `path` vide
def test_2_le_gate_path_vide_ABANDONNE_le_mouvement(board, paire):
    src, dst = paire
    st = P._state(board, [(1, src, 1, [])])
    op = MoveUnitOperation(1, dst)
    op.execute(st, EventBus())
    assert P._pos(st, 1) == src, "le mouvement a eu lieu : le gate `path` vide ne mord pas"
    assert op.last_abandoned == "path-empty"
    assert op.last_path is None


def test_2b_CONTRE_EPREUVE_sans_le_gate_le_port_TELEPORTE(board, paire):
    """Le temoin NON NUL : le port d'AVANT (`enforce_native_gates=False`) pose la position finale
    sur une tuile qu'AUCUN chemin n'atteint. Sans ce bras, le vert ci-dessus ne dirait pas si le
    gate mord ou si le montage est inerte."""
    src, dst = paire
    st = P._state(board, [(1, src, 1, [])])
    MoveUnitOperation(1, dst, enforce_native_gates=False).execute(st, EventBus())
    assert P._pos(st, 1) == dst


# ----------------------------------------------------------------- 3. GATE `TilesAreEmpty`
#
# ⚠ L'OCCUPANT EST UN **ALLIE**, et ce n'est pas un detail de montage -- c'est ce qui ISOLE le gate.
# Un occupant ENNEMI est refuse par les DEUX gates : `WalkPathfinder$$UnitIsBlockedByEnemyUnit`
# interdit l'arete qui y mene, donc `CalculatePaths` rendrait `path = null` de toute facon. Un
# ALLIE, lui, laisse PASSER le pathfinding (le predicat ne regarde que les ennemis non-Steppable) :
# seul `TilesAreEmpty` peut alors refuser. Monter le bras avec un ennemi le rendrait vert par
# RECOUVREMENT -- et un retrait du gate ne le ferait pas rougir.
def test_3_le_gate_tiles_are_empty_ABANDONNE_le_mouvement(board):
    a, b = _voisine_libre(board)
    st = P._state(board, [(1, a, 1, []), (2, b, 1, [])])          # meme team = ALLIE
    op = MoveUnitOperation(1, b)
    op.execute(st, EventBus())
    assert P._pos(st, 1) == a
    assert op.last_abandoned == "tiles-not-empty"


def test_3b_CONTRE_EPREUVE_sans_le_gate_les_deux_unites_se_SUPERPOSENT(board):
    a, b = _voisine_libre(board)
    st = P._state(board, [(1, a, 1, []), (2, b, 1, [])])
    MoveUnitOperation(1, b, enforce_native_gates=False).execute(st, EventBus())
    assert P._pos(st, 1) == b and P._pos(st, 2) == b, "pas de superposition : montage inerte"


def test_3b2_un_occupant_ENNEMI_est_refuse_par_les_DEUX_gates(board):
    """Le RECOUVREMENT, assertionne plutot que subi : sur un ennemi, `TilesAreEmpty` refuse (il est
    joue le PREMIER, donc c'est lui qu'on lit) ET le chemin serait vide de toute facon."""
    a, b = _voisine_libre(board)
    st = P._state(board, [(1, a, 1, []), (2, b, 2, [])])           # team differente = ENNEMI
    op = MoveUnitOperation(1, b)
    op.execute(st, EventBus())
    assert op.last_abandoned == "tiles-not-empty"
    st2 = P._state(board, [(1, a, 1, []), (2, b, 2, [])])
    op2 = MoveUnitOperation(1, b, skip_pre_move_triggers=True)     # saute `TilesAreEmpty`
    op2.execute(st2, EventBus())
    assert op2.last_abandoned == "path-empty", (
        "sans `TilesAreEmpty`, l'occupant ENNEMI doit encore couper le chemin "
        "(`WalkPathfinder$$UnitIsBlockedByEnemyUnit`)")


@pytest.mark.parametrize("regime", ["steppable", "mort", "vide"])
def test_3c_les_trois_exemptions_natives_laissent_PASSER(board, regime):
    """Les trois `continue` de `TilesAreEmpty`, un par regime. `steppable` est load-bearing : sans
    lui, un decoy bloquerait le mouvement que `KillSteppableUnits` est justement la pour ecraser."""
    a, b = _voisine_libre(board)
    if regime == "vide":
        st = P._state(board, [(1, a, 1, [])])
    elif regime == "steppable":
        st = P._state(board, [(1, a, 1, []), (2, b, 2, [UnitTrait.Steppable])])
    else:
        st = P._state(board, [(1, a, 1, []), (2, b, 1, [])])
        st.get_entity(2).get_component(UnitComponent).alive = False
    op = MoveUnitOperation(1, b)
    op.execute(st, EventBus())
    assert P._pos(st, 1) == b, "regime %s : le gate refuse alors que le natif exempte" % regime
    assert op.last_abandoned == ""


def test_3d_le_gate_ne_se_rejoue_PAS_sur_la_RELANCE(board):
    """`TilesAreEmpty` vit DANS le bloc `!skipPreMoveTriggers` : la relance apres deviation
    (`options+0x12 = 1`) ne le rejoue pas. C'est LU au decompile, pas choisi -- le gate est a
    l'interieur des accolades du `if`, comme `On(0x1f)`. Occupant ALLIE, cf. le bloc ci-dessus."""
    a, b = _voisine_libre(board)
    st = P._state(board, [(1, a, 1, []), (2, b, 1, [])])
    op = MoveUnitOperation(1, b, skip_pre_move_triggers=True)
    op.execute(st, EventBus())
    assert P._pos(st, 1) == b, "le gate a mordu sur une relance -- il n'est pas au bon rang"
    assert op.last_abandoned == ""


# ----------------------------------------------------------------- 4. hors plateau
def test_4_une_unite_HORS_PLATEAU_n_est_JAMAIS_abandonnee(board):
    """`CalculatePaths` rend `[endTile, endTile]` quand `movementStartPosition.Count == 0` -- une
    liste NON VIDE, donc le gate ne mord pas. C'est ce qui protege `GhostRevive`,
    `EchoesFromTheWarp` et `StormboyzStrike_Fallback`, dont le caster arrive de nulle part."""
    _, b = _voisine_libre(board)
    st = P._state(board, [(1, None, 1, [])])
    op = MoveUnitOperation(1, b)
    op.execute(st, EventBus())
    assert P._pos(st, 1) == b
    assert op.last_path == [b, b] and op.last_abandoned == ""


# ----------------------------------------------------------------- 5. la TRACE du crush
def test_5_la_trace_du_crush_est_PUBLIEE_et_l_etat_INCHANGE(board):
    """#462-...-r4-r3 : ecart d'OBSERVABILITE, pas de comportement. On assertionne les DEUX --
    la trace apparait ET l'etat produit est celui d'avant (le mover arrive, le steppable meurt)."""
    a, b = _voisine_libre(board)
    st = P._state(board, [(1, a, 1, []), (2, b, 2, [UnitTrait.Steppable])])
    op = MoveUnitOperation(1, b)
    op.execute(st, EventBus())
    # `Steppable` exempte le crushe des DEUX predicats a la fois -- `TilesAreEmpty` (troisieme
    # `continue`) et `WalkPathfinder$$UnitIsBlockedByEnemyUnit` -- donc le mouvement passe meme sur
    # un ennemi. C'est LU des deux cotes : les deux testent `HasTrait(occ, 0x1b)`.
    from engine.entities.damage_reason import DamageReason
    assert len(op.last_crushed) == 1
    tr = op.last_crushed[0]
    assert tr["unit"] == 2 and tr["killer"] == 1
    assert tr["reason"] == int(DamageReason.Steppable)
    assert isinstance(tr["vectors"], list)
    assert P._pos(st, 1) == b
    assert st.get_entity(2).get_component(UnitComponent).alive is False


def test_5b_aucun_crush_rend_une_trace_VIDE_pas_None(board):
    a, b = _voisine_libre(board)
    st = P._state(board, [(1, a, 1, [])])
    op = MoveUnitOperation(1, b)
    op.execute(st, EventBus())
    assert op.last_crushed == []


# ----------------------------------------------------------------- 6. LE CLIQUET
#: Chaque call-site de `MoveUnitOperation` dans `engine/**`, et le NATIF qu'il mirroite.
#:   `True`  -> `MoveUnitOperation$$Execute` : il DOIT jouer les deux gates (defaut, aucun kwarg) ;
#:   `False` -> il doit les ETEINDRE explicitement (`enforce_native_gates=False`) ;
#:   `None`  -> la RELANCE interne, qui PROPAGE la valeur de son appelant.
CALL_SITES: dict[tuple[str, str, int], object] = {
    # --- les feuilles DSL de mouvement : `DSLBehaviors$$MoveUnit` / `$$FlyUnit` -> `MoveUnit` slot
    ("runner/abilities/behaviours/movement.py", "execute", 1): True,   # FlyUnit
    ("runner/abilities/behaviours/movement.py", "execute", 2): True,   # MoveUnit
    # --- `TheQuickening` : le port COLLAPSE le lift-off natif, geometrie que le natif ne voit pas
    ("runner/abilities/loki/quickening.py", "execute_behaviour", 1): False,
    ("runner/abilities/loki/quickening.py", "execute_behaviour", 2): False,
    # --- `FleeOperation$$Execute` n'appelle NI `MoveUnit` NI `SetUnitPosition` : son call-site du
    #     port a donc ete SUPPRIME (#429-r1-r3-r1-r2-r1), pas re-classe. L'entree qui vivait ici
    #     (`("runner/operations/behaviour.py", "execute", 1): False`) est retiree AVEC lui -- c'est
    #     exactement ce que le message de `test_6` demande d'un retrait de site.
    # --- push / pull / switch : STAND-INS de `SetUnitPositionOperation$$Execute`
    ("runner/operations/displace.py", "execute", 1): False,
    ("runner/operations/displace.py", "execute", 2): False,
    ("runner/operations/displace.py", "execute", 3): False,
    ("runner/operations/displace.py", "execute", 4): False,
    ("runner/operations/displace.py", "execute", 5): False,
    # --- le mouvement JOUEUR (`Visit(MoveUnitMessage)`) et la RELANCE interne
    ("runner/operations/movement.py", "visit_MoveUnitMessage", 1): True,
    ("runner/operations/movement.py", "execute", 1): None,
    # --- le summon bouge par le MEME chemin que le mouvement joueur
    ("runner/operations/summon_ai.py", "apply_action", 1): True,
    # --- `MoveAndSpawnDecoy$$CreateBehaviour` est un call-site de `DSLBehaviors$$MoveUnit`
    ("runner/operations/triggers/genestealer.py", "execute_behaviour", 1): True,
}


def _releve_call_sites() -> dict:
    """Tous les `MoveUnitOperation(...)` d'`engine/**`, releves par AST (jamais par grep), avec
    leurs KWARGS. Cle = `(module, fonction englobante, rang dans la fonction)`."""
    root = pathlib.Path(__file__).resolve().parents[3] / "engine"
    out = {}
    for p in sorted(root.rglob("*.py")):
        src = p.read_text(encoding="utf-8")
        if "MoveUnitOperation(" not in src:
            continue
        tree = ast.parse(src)
        parents = {}
        for n in ast.walk(tree):
            for c in ast.iter_child_nodes(n):
                parents[c] = n
        rangs: dict = {}
        appels = []
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            nom = getattr(n.func, "attr", getattr(n.func, "id", None))
            if nom != "MoveUnitOperation":
                continue
            f = n
            while f in parents and not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                f = parents[f]
            appels.append((n.lineno, getattr(f, "name", "<module>"), n))
        for lineno, fn, n in sorted(appels):
            mod = p.relative_to(root).as_posix()
            rangs[(mod, fn)] = rangs.get((mod, fn), 0) + 1
            kw = {k.arg: k.value for k in n.keywords}
            out[(mod, fn, rangs[(mod, fn)])] = (lineno, kw)
    return out


def test_6_cliquet_tout_call_site_DECLARE_le_natif_qu_il_mirroite():
    releve = _releve_call_sites()
    inconnus = sorted(k for k in releve if k not in CALL_SITES)
    disparus = sorted(k for k in CALL_SITES if k not in releve)
    assert not inconnus, (
        "%d call-site(s) de `MoveUnitOperation` que ce fichier ne classe PAS : %r. Un call-site "
        "neuf doit DIRE quel natif il mirroite -- `MoveUnitOperation$$Execute` (les deux gates "
        "d'abandon s'appliquent, defaut) ou `SetUnitPositionOperation$$Execute` / un collapse "
        "assume (`enforce_native_gates=False`). Les deux gates sont PERMISSIFS quand ils manquent : "
        "l'omission ne casse rien, elle fait seulement bouger le port la ou le natif refuse."
        % (len(inconnus), inconnus))
    assert not disparus, (
        "%d call-site(s) classe(s) ici mais DISPARU(s) du code : %r. Retirer l'entree fait partie "
        "du changement qui a supprime le site." % (len(disparus), disparus))


@pytest.mark.parametrize("cle", sorted(CALL_SITES, key=str))
def test_6b_le_kwarg_ECRIT_au_site_correspond_a_sa_declaration(cle):
    releve = _releve_call_sites()
    assert cle in releve, "call-site disparu : %r (cf. le cliquet ci-dessus)" % (cle,)
    lineno, kw = releve[cle]
    attendu = CALL_SITES[cle]
    val = kw.get("enforce_native_gates")
    if attendu is True:
        assert val is None, (
            "%r (L%d) est declare `MoveUnitOperation$$Execute` : il ne doit PAS poser "
            "`enforce_native_gates` (le defaut est True)." % (cle, lineno))
    elif attendu is False:
        assert isinstance(val, ast.Constant) and val.value is False, (
            "%r (L%d) doit poser `enforce_native_gates=False` -- il mirroite un natif qui n'a NI "
            "`CalculatePaths` NI `TilesAreEmpty`, ou collapse une etape." % (cle, lineno))
    else:
        assert isinstance(val, ast.Attribute) and val.attr == "enforce_native_gates", (
            "%r (L%d) est la RELANCE : elle doit PROPAGER `self.enforce_native_gates` (le natif "
            "recopie la struct `options` telle quelle, il n'y touche que pour `+0x12 = 1`)."
            % (cle, lineno))
