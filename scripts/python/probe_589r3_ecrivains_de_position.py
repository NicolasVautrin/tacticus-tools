"""#589-r3 -- LES ECRIVAINS DE POSITION, ET L'INVARIANT << une unite ne se tient jamais sur une
tuile NON MARCHABLE >>.

POURQUOI CE PROBE EXISTE. `#589-r2-r1` a etabli que la levee `BeelineSansChemin` est sure **par le
DEPART** du mouvement, pas par son gate de destination (61 sauts sous l'hypothese DESTINATION contre
**0** sous l'hypothese DEPART, sur le seul board a poche isolee des 779). Or le depart n'a AUCUN gate
de marchabilite : `movementStartPosition = GetUnitPosition(unit)` est la tuile ou l'unite SE TIENT,
et `IdunBattle.Operations.SetUnitPositionOperation$$Execute` n'a que DEUX gates -- LUS --
(`feet.Count == position.Count`, `!HasFlag(unit, 6 = Dead)`) : rien n'y teste `IsWalkableTile`.
La surete de la levee repose donc sur un INVARIANT non ecrit : personne ne DEPOSE jamais une unite
sur une tuile non marchable. Ce probe le rend EXECUTABLE.

RE CONDUITE POUR CETTE TRANCHE (build `t6dpr4k06g`, decompile = verite) -- le PUSH, chaine complete,
parce que c'est l'ecrivain que la fiche du residu nommait en premier :

    IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPush(this, caster, target) :
        list = <IBattleQuery slot 77 = GetMinimumTiles180Behind>(caster, target)
        list.RemoveAll(t => !<IBattleQuery slot 96 = AreEntitiesAdjacent>(target, t))
        if (list.Count == 1) return list[0]
        kept = list.Where(TileExtensions$$IsEmptyOrSteppable)
        return (kept.Count > 0 ? kept : list)[Random(...)]

    IdunBattle.Entities.TileExtensions$$IsEmptyOrSteppable(tile, matchState) :   # LU EN ENTIER
        if (TileContentComponent$$IsEmpty(tile.<+0x38>)) return true
        u = GetUnit(tile, matchState)
        return u != null && GetBaseUnitComponent(u).HasTrait(0x1b)               # 0x1b = Steppable
    -> **AUCUN test de marchabilite dans ce predicat**. Le gate est en AMONT, et il est LU :

    IdunBattle.Core.Services.BattleQuery$$GetMinimumTiles180BehindFromTile
        -> ... AddNewTileToList(this, row, col, originTile, list, board,
                                checkWalkability: 1, checkElevation: 1)
        -> IdunBattle.Core.Services.TileUtil$$IsTileValidForList(tile, originTile,
                                                                 checkWalkability, checkElevation) :
               tc = tile.<+0x20>                                   # TileComponent
               if (tc.<+0x41> != 0) return false                   # isWall
               if (!checkWalkability) return tc.<+0x40> == 0        # !isInFog
               if (!TileExtensions$$IsWalkable(tile, tc, tile.<+0x40>, checkFog: 1)) return false
               if (!checkElevation) return true
               return |originTile.<+0x20>.<+0x18> - tile.<+0x20>.<+0x18>| < 2    # delta d'elevation

    => LE PUSH NE PEUT PAS DEPOSER SUR UNE TUILE NON MARCHABLE. Les noms `checkWalkability` /
    `checkElevation` sont LUS dans la signature ghidra d'`AddNewTileToList`, pas devines.

CE QUE CE PROBE MESURE, ET COMMENT LE MONTAGE EVITE LE REGIME DEGENERE. Chaque ecrivain est joue
DEUX FOIS sur le MEME montage :

  (a) REPERAGE -- board integralement MARCHABLE. On note la tuile `D` ou l'unite atterrit
      REELLEMENT. Si elle ne bouge pas, le scenario est declare **NON MESURANT** et fait ROUGIR :
      un scenario qui refuse pour une autre raison (adjacence, deplacabilite, chemin absent)
      rendrait un vert VIDE a l'etape (b). C'est le vice que la premiere version de ce probe
      portait -- la direction hex n'est PAS invariante en colonne (even-q), donc un board d'une
      seule ligne faisait sortir le push du plateau et « refuser » pour la mauvaise raison.
  (b) PIEGE -- le MEME board, avec la SEULE tuile `D` rendue NON MARCHABLE. Verdict :
      `REFUSE` (l'unite n'y va pas) ou `DEPOSE` (l'invariant est FAUX pour cet ecrivain).

  Puis l'INVARIANT global sur l'etat final : aucune unite VIVANTE sur une tuile non marchable.

  ETAPE 1 -- RECENSEMENT DERIVE des ECRIVAINS de position dans `engine/**` (tout site qui construit
  un `PositionComponent(...)` ou affecte `<x>.col` / `<x>.row`). Jamais une liste recopiee : un
  ecrivain neuf apparait ici tout seul.

rc = 0 si tous les ecrivains VISES refusent ; rc = 1 si l'un depose, ou si un scenario est NON
MESURANT. C'est un CLIQUET.

Sortie ASCII pure (console cp1252). OFFLINE : aucun runner, aucune session.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.entities.unit_context import UnitContext                       # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,     # noqa: E402
                                      PositionComponent, StatsComponent, UnitComponent)
from engine.runner.events import EventBus                                  # noqa: E402
from engine.runner.state import State                                      # noqa: E402

LARGEUR, HAUTEUR = 9, 7


# ============================================================ ETAPE 1 : recensement DERIVE

def _ecrivains(racine: Path) -> list[tuple[str, int, str]]:
    """Tout site d'`engine/**` qui ECRIT une position : construction d'un `PositionComponent(...)`
    ou affectation d'un attribut `col` / `row`. On ne filtre PAS par module : un ecrivain qui
    apparaitrait ailleurs (une ability, un effet) doit se voir."""
    out: list[tuple[str, int, str]] = []
    for p in sorted((racine / "engine").rglob("*.py")):
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        rel = str(p.relative_to(racine))
        for n in ast.walk(arbre):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "PositionComponent":
                out.append((rel, n.lineno, "PositionComponent(...)"))
            elif isinstance(n, ast.Assign):
                for c in n.targets:
                    if isinstance(c, ast.Attribute) and c.attr in ("col", "row"):
                        out.append((rel, n.lineno, "affectation .%s" % c.attr))
    return out


# ============================================================ le montage

def _board(non_marchable=None) -> Board:
    """Une GRILLE pleine `LARGEUR x HAUTEUR`, toutes tuiles marchables sauf, eventuellement, `D`.
    Une grille (et non une ligne) est OBLIGATOIRE : la direction hex even-q alterne de rangee d'une
    colonne a l'autre, donc un board d'une ligne fait sortir tout push du plateau."""
    trou = tuple(non_marchable) if non_marchable is not None else None
    tiles = []
    for col in range(LARGEUR):
        for row in range(HAUTEUR):
            ds = ([(-1, 0), (-1, 1), (0, -1), (0, 1), (1, 0), (1, 1)] if col % 2 == 0
                  else [(-1, -1), (-1, 0), (0, -1), (0, 1), (1, -1), (1, 0)])
            tiles.append({
                "id": col * 100 + row, "col": col, "row": row, "elevation": 0,
                "walkable": (col, row) != trou, "isWall": False,
                "neighbours": [(col + dc) * 100 + (row + dr) for dc, dr in ds
                               if 0 <= col + dc < LARGEUR and 0 <= row + dr < HAUTEUR]})
    return Board(tiles, adjacency="native_sym")


def _etat(non_marchable, pos_a, pos_b):
    st = State()
    st.board = _board(non_marchable)
    ids = []
    for i, pos in enumerate((pos_a, pos_b)):
        e = st.add_entity()
        e.add_component(UnitComponent(visual_id="ultraEliminatorSgt", alive=True))
        e.add_component(HealthComponent(hp=10000, hp_max=10000))
        e.add_component(OwnerComponent(team=i, player=i))
        e.add_component(PositionComponent(pos[0], pos[1]))
        e.add_component(StatsComponent(
            ctx=UnitContext(entity_id=e.id, visual_id="ultraEliminatorSgt")))
        ids.append(e.id)
    return st, ids[0], ids[1]


def _pos(state: State, uid: int) -> tuple:
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (None, None) if pc is None else (pc.col, pc.row)


def _unites_hors_sol(state: State) -> list:
    """L'INVARIANT : toute unite VIVANTE occupe une tuile marchable."""
    mauvais = []
    for e in list(getattr(state, "entities", {}).values()):
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if uc is None or pc is None or not getattr(uc, "alive", True):
            continue
        tid = state.board.id_at(pc.col, pc.row)
        if tid is None or not state.board.walkable(tid):
            mauvais.append((e.id, (pc.col, pc.row)))
    return mauvais


# ============================================================ les scenarios, un par ECRIVAIN
# Chaque scenario prend la tuile a PIEGER (ou `None` pour le REPERAGE) et rend (etat, unite visee).

A0, B0 = (3, 3), (4, 3)          # pousseur / pousse, adjacents en even-q (col 3 impaire, +1 col)


def _sc_push(trou):
    """`DisplaceUnitOperation` direction HEX -- la voie `FindTileToPush` du natif."""
    from engine.runner.operations.displace import DisplaceUnitOperation
    st, a, b = _etat(trou, A0, B0)
    DisplaceUnitOperation(a, b).execute(st, EventBus())
    return st, b


def _sc_push_vecteur(trou):
    """`DisplaceUnitOperation` direction VECTEUR (`AdjacentVector`) : le pas est IMPOSE, donc c'est
    le chemin ou un gate manquant se verrait le plus vite."""
    from engine.runner.operations.displace import DisplaceUnitOperation, _dir_index
    st, a, b = _etat(trou, A0, B0)
    op = DisplaceUnitOperation(a, b)
    op.vector_dir = _dir_index(A0[0], A0[1], B0[0], B0[1])
    op.execute(st, EventBus())
    return st, b


def _sc_pull(trou):
    """`PullUnitOneTileOperation` -- l'arc AVANT (`GetMinimumTiles180Front`)."""
    from engine.runner.operations.displace import PullUnitOneTileOperation
    st, a, b = _etat(trou, (3, 3), (5, 3))
    PullUnitOneTileOperation(a, b).execute(st, EventBus())
    return st, b


def _sc_direct(trou, cible=(5, 5)):
    """`DirectDisplaceOperation` : la destination est DONNEE par la feuille DSL (`Direct(tiles)`).
    C'est l'ecrivain le plus DIRECT du port -- si un gate manque, il manque ici."""
    from engine.runner.operations.displace import DirectDisplaceOperation
    st, a, b = _etat(trou, A0, B0)
    DirectDisplaceOperation(a, b, [cible]).execute(st, EventBus())
    return st, b


def _sc_move_sans_gates(trou, cible=(5, 5)):
    """`MoveUnitOperation(enforce_native_gates=False)` -- LE call-site que `#589-r2-r1` nomme comme
    non protege (`displace`, `quickening`). Joue NU, avec une destination arbitraire."""
    from engine.runner.operations.movement import MoveUnitOperation
    st, _a, b = _etat(trou, A0, B0)
    MoveUnitOperation(b, cible, record_tiles=False, emit_after_move=False,
                      enforce_native_gates=False).execute(st, EventBus())
    return st, b


def _sc_move_avec_gates(trou, cible=(5, 5)):
    """Le TEMOIN : le meme `MoveUnitOperation` avec ses gates natifs."""
    from engine.runner.operations.movement import MoveUnitOperation
    st, _a, b = _etat(trou, A0, B0)
    MoveUnitOperation(b, cible, record_tiles=False, emit_after_move=False).execute(st, EventBus())
    return st, b


# ============================================================ LA TABLE DE VENTILATION
#
# Le verdict attendu n'est PAS « refuse » partout -- ce serait un voeu, pas une lecture. Chaque
# ecrivain porte le verdict que son NATIF impose, avec la piece qui l'etablit. Le cliquet mord sur
# une DIVERGENCE port/natif, jamais sur le depot en soi : un ecrivain que le natif ne gate pas et
# que le port refuserait serait tout aussi FAUX qu'un ecrivain que le natif gate et que le port
# laisse passer.
#
#   `REFUSE` = le natif a un gate de marchabilite sur ce chemin (piece LUE citee) ;
#   `DEPOSE` = le natif n'en a AUCUN -- la surete vient alors de l'AMONT (le selecteur qui fournit
#              la tuile), et c'est ce qui reste a etablir feuille par feuille.
SCENARIOS = (
    ("DisplaceUnitOperation (direction hex)", _sc_push, "REFUSE",
     "FindTileToPush -> GetMinimumTiles180Behind -> AddNewTileToList(checkWalkability: 1) -> "
     "TileUtil$$IsTileValidForList -> TileExtensions$$IsWalkable  [LU]"),
    ("DisplaceUnitOperation (AdjacentVector)", _sc_push_vecteur, "REFUSE",
     "FindTileWithVector : `if (tile == null || !TileExtensions$$IsWalkable(tile, checkFog: 1)) "
     "return null` -- gate EXPLICITE dans la fonction meme  [LU]"),
    ("PullUnitOneTileOperation", _sc_pull, "REFUSE",
     "FindTileToPullOnce -> GetMinimumTiles180Front, meme famille `AddNewTileToList` que le push. "
     "HERITE du port (#589-r2-r1) -- NON RELU dans cette tranche"),
    ("DirectDisplaceOperation", _sc_direct, "DEPOSE",
     "case 4 (`Direct`, seul producteur `DSLBehaviors$$Teleport`) : `tile = options.<+0x20>[0]` "
     "SANS recherche ni filtre ; la queue commune ne teste que `IsFilled(tile)` et "
     "`TileComponent.<+0x2c>` (tuile TEMPORAIRE). AUCUN `IsWalkableTile`  [LU]"),
    ("MoveUnitOperation (enforce_native_gates=False)", _sc_move_sans_gates, "DEPOSE",
     "parametre de PORT, pas un natif : il dit `ce call-site ne mirroite PAS MoveUnitOperation`. "
     "Ses appelants reels (push/pull/switch/direct de `displace.py`, `quickening.py`) ont TOUS "
     "filtre en amont ou visent une tuile OCCUPEE -- donc marchable par l'invariant lui-meme"),
    ("MoveUnitOperation (gates natifs)", _sc_move_avec_gates, "REFUSE",
     "les sept gates d'abandon de `MoveUnitOperation$$Execute`, dont le chemin `CalculatePaths`"),
)


def main() -> int:
    ap = argparse.ArgumentParser(description="#589-r3 ecrivains de position vs marchabilite")
    ap.add_argument("--no-recensement", action="store_true")
    args = ap.parse_args()

    if not args.no_recensement:
        print("=" * 78)
        print("ETAPE 1 -- ECRIVAINS de position dans engine/** (recensement DERIVE)")
        print("=" * 78)
        ecr = _ecrivains(_HERE)
        par_fichier: dict = {}
        for rel, ln, quoi in ecr:
            par_fichier.setdefault(rel, []).append((ln, quoi))
        print("sites: %d  dans %d fichiers" % (len(ecr), len(par_fichier)))
        for rel in sorted(par_fichier):
            print("  %-64s %d" % (rel, len(par_fichier[rel])))
        print("")

    print("=" * 78)
    print("ETAPE 2 -- REPERAGE (board tout marchable) puis PIEGE (la destination rendue NON")
    print("           MARCHABLE). Un scenario qui ne BOUGE PAS au reperage est NON MESURANT.")
    print("=" * 78)
    divergents, non_mesurants, deposent = [], [], []
    for nom, sc, attendu, piece in SCENARIOS:
        try:
            st0, uid = sc(None)
            d = _pos(st0, uid)
        except Exception as exc:                                          # noqa: BLE001
            print("  %-48s REPERAGE EXC %s: %s" % (nom, type(exc).__name__, exc))
            non_mesurants.append(nom)
            continue
        st_ref, _a, b_ref = _etat(None, A0, B0)
        avant = _pos(st_ref, b_ref)
        if d == avant:
            print("  %-48s NON MESURANT (aucun deplacement au reperage, pos=%r)" % (nom, d))
            non_mesurants.append(nom)
            continue
        try:
            st1, uid1 = sc(d)
            apres = _pos(st1, uid1)
        except Exception as exc:                                          # noqa: BLE001
            print("  %-48s PIEGE EXC %s: %s" % (nom, type(exc).__name__, exc))
            divergents.append((nom, "EXC", attendu))
            continue
        obtenu = "DEPOSE" if apres == d else "REFUSE"
        hors = _unites_hors_sol(st1)
        marque = "  " if obtenu == attendu else "!!"
        print("%s%-48s reperage=%-8r attendu=%-6s obtenu=%-6s hors-sol=%r"
              % (marque, nom, d, attendu, obtenu, hors))
        if obtenu != attendu:
            divergents.append((nom, obtenu, attendu))
        if obtenu == "DEPOSE":
            deposent.append((nom, piece))
    print("")

    print("=" * 78)
    print("VERDICT")
    print("=" * 78)
    if non_mesurants:
        print("ECHEC -- %d scenario(s) NON MESURANTS (le reperage ne deplace rien) :"
              % len(non_mesurants))
        for nom in non_mesurants:
            print("   %s" % nom)
        print("Un vert obtenu avec ces scenarios-la ne prouverait RIEN : ils refusent pour une")
        print("autre raison que la marchabilite. REPARER LE MONTAGE, jamais retirer le scenario.")
        return 1
    if divergents:
        print("ECHEC -- %d ecrivain(s) DIVERGENT de leur verdict NATIF LU :" % len(divergents))
        for nom, obtenu, attendu in divergents:
            print("   %-48s obtenu=%s  attendu=%s" % (nom, obtenu, attendu))
        return 1
    print("OK -- les %d ecrivains de DEPLACEMENT concordent avec leur verdict NATIF, et le reperage"
          % len(SCENARIOS))
    print("     prouve qu'ils deplacent vraiment quand la tuile est marchable.")
    print("")
    print("CE QUE CA ETABLIT POUR #589-r2-r1, ET CE QUE CA N'ETABLIT PAS :")
    print("  L'invariant << une unite ne se tient jamais sur une tuile non marchable >> N'EST PAS")
    print("  garanti PAR CONSTRUCTION. %d ecrivain(s) DEPOSENT, et c'est le NATIF :" % len(deposent))
    for nom, piece in deposent:
        print("   * %s" % nom)
        print("     %s" % piece)
    print("  La surete de la levee `BeelineSansChemin` par le DEPART repose donc sur les SELECTEURS")
    print("  qui alimentent ces voies, PAS sur un gate d'ecriture. Etablir feuille par feuille que")
    print("  le selecteur d'un `DSLBehaviors$$Teleport` ne rend que des tuiles marchables reste")
    print("  OUVERT -- c'est ce que ce probe delimite, il ne le tranche pas.")
    print("PORTEE -- ce probe couvre les ecrivains de DEPLACEMENT. Il ne couvre PAS le SPAWN /")
    print("          DRAFTING (`TileExtensions$$CanAddUnit`) ni le placement initial de la BC :")
    print("          ceux-la ecrivent une position sans passer par ces operations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
