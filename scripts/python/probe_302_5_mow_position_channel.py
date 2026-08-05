"""#302 tranche 5 -- le canal `MachineOfWarPosition` d'un RUNNER, et ce qu'il TRANCHE.

Ce que la fiche affirmait, et qui est FAUX
------------------------------------------
`case-302-route-cible-tuile.md` §7 point 3 : « AUCUN RPC n'expose la config de spawn D'UN RUNNER
[...] Point d'ancrage le plus economique : `boardGraph`, qui n'aurait qu'a ajouter
`spawnGroups: [{teamWithPlayerIndex, machineOfWarPosition}]` ». La tranche etait donc classee
« exige un reinject ».

MESURE (2026-08-06, session 1, build `rnca9r7q6c`) : `boardGraph` publie DEJA `mowPositions`,
livre par #311 dans le meme commit hooks (`de7879b2`), deploye par le meme reinject, et present
dans le bundle injecte. Le champ est STRICTEMENT MEILLEUR que celui que la fiche reclamait : au
lieu des groupes BRUTS -- que le port devrait re-traverser par un mirror de `GroupForPlayer` --
il porte le retour de `IdunBattle.Core.Services.BattleQuery$$GetPositionMachineForPlayer(player)`
INVOQUE, donc la valeur EFFECTIVE, repli natif compris.

Il n'y avait rien a instrumenter : `engine.ai.context` appelait deja `boardGraph` (cache par rid)
et jetait tout sauf `tiles`. La tranche est un FIL A BRANCHER, en Python pur.

Ce que le probe mesure
----------------------
1. `--canal`   : le champ existe sur un runner, avec son TRI-ETAT (`null` != `[]`).
2. `--cascade` : le contexte rend la valeur NATIVE sans qu'on lui passe `spawn_groups` --
                 avec son BRAS TEMOIN (l'ancienne cascade) et un `a_mordu` SEPARE du verdict.
3. `--311`     : tranche le residu de #311 (« sur ce seul plateau on ne peut pas distinguer
                 'lit la declaration' de 'le repli a tire' ») sur un board DISCRIMINANT.

Boards, choisis pour leur DECLARATION (balayage des 675 dumps, cf. `--boards`) :
  - `MC1_67` declare (TWPI 0 -> 2, TWPI 1 -> 1) == le repli natif  -> REGIME DEGENERE, celui de #311
  - `C1_01`  declare (TWPI 1 -> 0, TWPI 0 -> 0) != le repli (2, 1) -> REGIME DISCRIMINANT
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LOGS = ROOT / "logs"
BOARDS_DIR = ROOT / "data" / "boards"

sys.path.insert(0, str(HERE))

import probe_27_3_live as L                                    # noqa: E402
import engine.ai.context as AICTX                              # noqa: E402
from engine.services.machine_of_war_position import (          # noqa: E402
    MachineOfWarPosition, group_for_player, machine_of_war_position_for_player,
    spawn_groups_from_battle_config,
)

BOARD_DEGENERE = "MC1_67"      # declare == repli  -> le plateau de #311
BOARD_DISCRIMINANT = "C1_01"   # declare != repli  -> tranche #311
SEED = "31337"
RANK = "17"


# ------------------------------------------------------------------ montage

def _build(board: str, tag: str, mow: bool = False) -> tuple[int, dict]:
    """Monte un runner et rend `(runnerId, state)`. `--state-file` ABSOLU + nom UNIQUE."""
    LOGS.mkdir(parents=True, exist_ok=True)
    state = LOGS / ("probe_302_5_%s.json" % tag)
    if state.exists():
        state.unlink()
    args = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", board,
            "--rank", RANK, "--roster", "3", "--state-file", str(state)]
    if mow:
        args.append("--mow")
    r = subprocess.run(args, cwd=str(HERE), capture_output=True, text=True)
    if not state.exists():
        raise SystemExit("build FAIL board=%s rc=%s\n%s\n%s"
                         % (board, r.returncode, (r.stdout or "")[-1200:], (r.stderr or "")[-1200:]))
    st = json.loads(state.read_text(encoding="utf-8"))
    return int(st["runnerId"]), st


def _rpc(method: str, body: dict, timeout: float = 60.0) -> dict:
    return L._rpc(method, [dict(body)])


def _dispose(rid: int) -> None:
    try:
        L._rpc("disposeRunner", [{"runnerId": rid}])
    except Exception as e:                                     # pragma: no cover - diagnostic
        print("  [warn] dispose runner %d: %s" % (rid, e))


def _repli_seul(team: int) -> int:
    """La branche FALLBACK de `GetPositionMachineForPlayer`, ISOLEE (aucun groupe trouve) :
    `if (uVar1 != 1) return (uVar1 == 2); return 2;` au decompile."""
    t = int(team)
    if t != 1:
        return int(MachineOfWarPosition.Top) if t == 2 else int(MachineOfWarPosition.None_)
    return int(MachineOfWarPosition.Bottom)


# ------------------------------------------------------------------ etape 1 : le canal

def etape_canal(board: str) -> int:
    """Le champ `mowPositions` existe-t-il sur un RUNNER, et porte-t-il son tri-etat ?"""
    print("=" * 78)
    print("ETAPE 1 -- le canal `boardGraph.mowPositions` sur un runner (board %s)" % board)
    rid, _st = _build(board, "canal")
    rouge = 0
    try:
        bg = _rpc("boardGraph", {"runnerId": rid}) or {}
        mp = bg.get("mowPositions")
        print("  mowPositions =", json.dumps(mp))
        if mp is None:
            print("  ROUGE : `mowPositions` ABSENT -- le hook ne resout pas "
                  "`GetPositionMachineForPlayer`, ou le bundle injecte est anterieur a #311.")
            return 1
        if not isinstance(mp, list):
            print("  ROUGE : `mowPositions` n'est pas une liste (%r)" % type(mp).__name__)
            return 1
        if not mp:
            print("  ROUGE : liste VIDE -- un runner porte toujours ses entites Player.")
            return 1
        for e in mp:
            for k in ("playerId", "teamId", "machineOfWarPosition"):
                if k not in e:
                    print("  ROUGE : entree sans `%s` : %r" % (k, e))
                    rouge = 1
            v = e.get("machineOfWarPosition")
            if v is not None and v not in tuple(int(x) for x in MachineOfWarPosition):
                print("  ROUGE : %r hors de `MachineOfWarPosition` %r"
                      % (v, [int(x) for x in MachineOfWarPosition]))
                rouge = 1
        # Le tri-etat est PRESERVE par le lecteur : `None` = pas mesure, `{}` = mesure et vide.
        table = AICTX._board_mow_positions(lambda m, b, to=60: _rpc(m, b), rid)
        print("  _board_mow_positions ->", table)
        if not table:
            print("  ROUGE : le lecteur rend une table vide/None sur un canal pourtant peuple.")
            rouge = 1
        vide = AICTX._board_mow_positions(lambda m, b, to=60: {}, -1)
        if vide is not None:
            print("  ROUGE : canal ABSENT doit rendre None (pas mesure), rendu %r" % (vide,))
            rouge = 1
        else:
            print("  tri-etat OK : canal absent -> None (pas mesure), jamais {} ni 0")
        print("  VERDICT etape 1 :", "ROUGE" if rouge else "VERT")
        return rouge
    finally:
        _dispose(rid)


# ------------------------------------------------------------------ etape 2 : le fil MORD

def etape_cascade(board: str) -> int:
    """Le contexte rend-il la valeur NATIVE SANS qu'on lui passe `spawn_groups` ?

    BRAS TEMOIN = l'ancienne cascade (le canal coupe). `a_mordu` est calcule SEPAREMENT du
    verdict : un temoin qui rend la MEME valeur ne prouve rien -- il dit que le regime est
    degenere, et le probe l'ECRIT au lieu de se declarer vert.
    """
    print("=" * 78)
    print("ETAPE 2 -- le fil MORD : `machine_of_war_position()` sans `spawn_groups` (board %s)" % board)
    rid, st = _build(board, "cascade")
    rouge = 0
    try:
        rpc = lambda m, b, to=60: _rpc(m, b)                   # noqa: E731
        dv = _rpc("decisionView", {"runnerId": rid, "allAbilities": True}) or {}
        cur = dv.get("currentPlayer")
        groups = spawn_groups_from_battle_config(st.get("bc") or {})
        team = AICTX._current_player_team(dv)
        table = AICTX._board_mow_positions(rpc, rid)
        natif = (table or {}).get(cur)

        # Bras MESURE (le port livre) et bras TEMOIN (le port d'AVANT, canal coupe).
        mesure = AICTX._machine_of_war_position(None, team, AICTX._mow_slot_by_player(dv), cur, table)
        temoin = AICTX._machine_of_war_position(None, team, AICTX._mow_slot_by_player(dv), cur, None)
        a_mordu = (mesure != temoin)

        print("  currentPlayer=%r team=%r  mows=%r" % (cur, team, dv.get("mows") or []))
        print("  BC declare :", [(g.get("TeamWithPlayerIndex"), g.get("MachineOfWarPosition"))
                                 for g in (groups or [])])
        print("  NATIF (mowPositions)     = %r" % (natif,))
        print("  MESURE  (port livre)     = %r" % (mesure,))
        print("  TEMOIN  (canal coupe)    = %r" % (temoin,))
        print("  a_mordu (mesure!=temoin) = %r" % (a_mordu,))

        if natif is None:
            print("  ROUGE : le canal ne porte pas le joueur courant.")
            rouge = 1
        elif mesure != natif:
            print("  ROUGE : le port ne rend PAS la valeur native (%r != %r)" % (mesure, natif))
            rouge = 1
        else:
            print("  OK : le port rend la valeur NATIVE sans qu'on lui passe la BC.")
        # Le mirror de la BC doit CONCORDER avec le natif -- sinon c'est le mirror qui est faux.
        if groups and team is not None:
            miroir = machine_of_war_position_for_player(groups, int(team))
            print("  mirror BC (`machine_of_war_position_for_player`) = %r" % (miroir,))
            if natif is not None and miroir != natif:
                print("  ROUGE : le mirror DIVERGE du natif (%r != %r) -- lire "
                      "`GetPositionMachineForPlayer` au decompile." % (miroir, natif))
                rouge = 1
        if not a_mordu:
            print("  [INERTE] le temoin rend la MEME valeur : sur CE board le fil ne se voit pas. "
                  "Ce n'est pas un vert -- rejouer sur un board ou le port d'avant rendait None.")
        print("  VERDICT etape 2 :", "ROUGE" if rouge else ("VERT (a_mordu=%r)" % a_mordu))
        return rouge
    finally:
        _dispose(rid)


# ------------------------------------------------------------------ etape 3 : trancher #311

def etape_311(board: str) -> int:
    """#311 laissait ouvert : « ces valeurs sont IDENTIQUES au repli -- sur ce seul plateau on ne
    peut pas distinguer 'lit la declaration' de 'le repli a tire'. Trancher exige un plateau qui
    declare (0,0). » Ce plateau existe : 502 des 675 boards."""
    print("=" * 78)
    print("ETAPE 3 -- trancher #311 sur un board DISCRIMINANT (%s)" % board)
    rid, st = _build(board, "d311")
    rouge = 0
    try:
        groups = spawn_groups_from_battle_config(st.get("bc") or {})
        bg = _rpc("boardGraph", {"runnerId": rid}) or {}
        mp = bg.get("mowPositions") or []
        print("  BC declare :", [(g.get("TeamWithPlayerIndex"), g.get("MachineOfWarPosition"))
                                 for g in (groups or [])])
        discrimine = 0
        for e in mp:
            team, natif = e.get("teamId"), e.get("machineOfWarPosition")
            if team is None or natif is None:
                continue
            grp = group_for_player(groups, int(team))
            declare = machine_of_war_position_for_player(groups, int(team))
            repli = _repli_seul(int(team))
            marque = ""
            if grp is not None and declare != repli:
                discrimine += 1
                marque = "  <-- DISCRIMINANT"
                if natif != declare:
                    print("  ROUGE : le natif suit le REPLI (%r) et non la DECLARATION (%r), team=%s"
                          % (natif, declare, team))
                    rouge = 1
            print("    team=%s NATIF=%r declare=%r repli_seul=%r%s"
                  % (team, natif, declare, repli, marque))
        if not discrimine:
            print("  [INERTE] aucun couple discriminant sur ce board -- la mesure ne tranche RIEN. "
                  "Choisir un board dont un groupe declare une valeur != du repli (cf. --boards).")
            rouge = 1
        elif not rouge:
            print("  VERT : sur %d couple(s) discriminant(s), le natif suit la DECLARATION du "
                  "groupe. #311 est tranche : `GetPositionMachineForPlayer` LIT la config, le "
                  "repli ne tire pas." % discrimine)
        print("  VERDICT etape 3 :", "ROUGE" if rouge else "VERT")
        return rouge
    finally:
        _dispose(rid)


# ------------------------------------------------------------------ inventaire (offline)

def etape_boards() -> int:
    """Balayage OFFLINE des dumps : quels boards DISCRIMINENT (declaration != repli) ?

    Ce compte est ce qui rend l'etape 3 possible -- et ce qui montre que le cran de repli
    `decisionView.mows` est structurellement MUET la ou le natif diverge."""
    print("=" * 78)
    print("INVENTAIRE OFFLINE -- boards discriminants (declaration != repli)")
    if not BOARDS_DIR.exists():
        print("  data/boards absent -- `python dump_boards.py` le regenere.")
        return 1
    total, disc_par_team, deux, ids = 0, {1: 0, 2: 0}, 0, set()
    ids_deux = set()
    sig_par_id: dict = {}      # {id: {(mow_team1, mow_team2)}} — un id peut vivre dans 2 pools
    for p in sorted(BOARDS_DIR.rglob("*.json")):
        j = json.loads(p.read_text(encoding="utf-8"))
        sets = (j.get("board") or {}).get("SpawnPointSets")
        if not isinstance(sets, list) or not sets:
            continue
        idx = int(j.get("spawnPointsSet") or 0)
        if not 0 <= idx < len(sets):
            continue
        groups = (sets[idx] or {}).get("SpawnPointGroups")
        if not isinstance(groups, list):
            continue
        total += 1
        bid = j.get("id") or p.stem
        ids.add(bid)
        n = 0
        for team in (1, 2):
            grp = group_for_player(groups, team)
            if grp is not None and machine_of_war_position_for_player(groups, team) != _repli_seul(team):
                disc_par_team[team] += 1
                n += 1
        if n == 2:
            deux += 1
            ids_deux.add(bid)
        sig_par_id.setdefault(bid, set()).add(
            tuple(machine_of_war_position_for_player(groups, t) for t in (1, 2)))
    # DEUX denominateurs, et les confondre fait lire une contradiction la ou il n'y en a pas :
    # `data/boards` porte 779 FICHIERS pour 675 ids DISTINCTS (un meme id est dumpe dans plusieurs
    # pools). Le compte DIT donc lequel il rend.
    ambigus = sorted(b for b, s in sig_par_id.items() if len(s) > 1)
    print("  fichiers lus (set ACTIF) : %d  |  ids de board DISTINCTS : %d" % (total, len(ids)))
    print("  discriminants team=1 : %d fichiers | team=2 : %d | LES DEUX : %d fichiers (%d ids)"
          % (disc_par_team[1], disc_par_team[2], deux, len(ids_deux)))
    sig_counts: dict = {}
    for sigs in sig_par_id.values():
        for s in sigs:
            sig_counts[s] = sig_counts.get(s, 0) + 1
    print("  signature (team1, team2) -> nb d'IDS qui la portent DANS AU MOINS UN POOL :")
    for s, n in sorted(sig_counts.items(), key=lambda x: -x[1]):
        marque = "== repli" if (s[0] == _repli_seul(1) and s[1] == _repli_seul(2)) else "DISCRIMINANTE"
        print("      %-8s -> %4d ids   %s" % (str(s), n, marque))
    # ⚠ La somme de ces lignes DEPASSE le nombre d'ids, et ce n'est pas une faute de comptage :
    # un meme id de board porte une declaration DIFFERENTE selon le pool ou il est dumpe. C'est
    # exactement l'ecart entre « 502 » (ids portant (0,0) EXCLUSIVEMENT) et « 552 » (ids la portant
    # dans au moins un pool) : 552 + 173 - 50 = 675.
    print("  ids dont la declaration DIFFERE d'un pool a l'autre : %d" % len(ambigus))
    if ambigus:
        print("      -> pour ces ids, `--board <id>` NE SUFFIT PAS a fixer la "
              "`MachineOfWarPosition` : le POOL la change. Echantillon : %s" % (ambigus[:6],))
    print("  -> sur les %d ids discriminants, un groupe declare `MachineOfWarPosition.None_` :"
          % len(ids_deux))
    print("     AUCUNE MoW n'y est deployee, donc `decisionView.mows` est VIDE et le cran de repli")
    print("     est MUET -- exactement la ou le natif diverge du fallback.")
    return 0 if total else 1


# ------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--canal", action="store_true", help="etape 1 : le champ existe (live)")
    ap.add_argument("--cascade", action="store_true", help="etape 2 : le fil mord (live)")
    ap.add_argument("--d311", action="store_true", help="etape 3 : trancher #311 (live)")
    ap.add_argument("--boards", action="store_true", help="inventaire OFFLINE des discriminants")
    ap.add_argument("--all", action="store_true", help="tout")
    ap.add_argument("--board", default=BOARD_DEGENERE)
    ap.add_argument("--board-discriminant", default=BOARD_DISCRIMINANT)
    a = ap.parse_args()
    if not any((a.canal, a.cascade, a.d311, a.boards, a.all)):
        ap.print_help()
        return 2
    rc = 0
    if a.boards or a.all:
        rc |= etape_boards()
    if a.canal or a.all:
        rc |= etape_canal(a.board)
    if a.cascade or a.all:
        rc |= etape_cascade(a.board)
    if a.d311 or a.all:
        rc |= etape_311(a.board_discriminant)
    print("=" * 78)
    print("RC =", rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
