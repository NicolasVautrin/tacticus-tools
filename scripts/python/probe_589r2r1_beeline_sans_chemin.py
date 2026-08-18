#!/usr/bin/env python
"""`#589-r2-r1` -- LA BEELINE PEUT-ELLE NE PAS TROUVER DE CHEMIN ? Mesure sur TOUS les boards.

    python probe_589r2r1_beeline_sans_chemin.py --only INV                 # inventaire OFFLINE
    python probe_589r2r1_beeline_sans_chemin.py --only CAPTURE [--boards a,b]   # LIVE (1 runner/board)
    python probe_589r2r1_beeline_sans_chemin.py --only MASQUES [--regenerer]    # derive + valide
    python probe_589r2r1_beeline_sans_chemin.py --only SCAN                # les 779 boards, OFFLINE
    python probe_589r2r1_beeline_sans_chemin.py --only REGIME [--board X]  # le regime est-il ATTEINT ?

## La question, et pourquoi elle etait bornee a DEUX boards

`engine/services/movement_query.py::get_connected_path_to` recoud les sauts d'un chemin de VOL par
la beeline. Quand la beeline ne trouve PAS de chemin, les deux cotes divergent :

  * le NATIF ne degrade pas -- `IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo` fait
    `if (<beeline> == 0) goto <raise>`, c'est-a-dire un DEREFERENCEMENT NUL sur `sub.Count` ;
  * le PORT ecrit `for mid in (sub or [])[1:-1]` : il avale l'absence et compte le saut pour **1**
    arete.

C'est le SEUL regime ou `n_C < n_G`. `#589-r2` l'a mesure NON ATTEINT sur **2** boards (`C1_74`,
`C3_14`, 0 echec sur 3590 couples chacun) -- mais **285 des 287 boards a `Bridge`** n'etaient pas
mesures, et pour cause : chaque mesure exigeait une CAPTURE LIVE du `boardGraph` (un runner par
board), le champ `connectivity` n'existant que sur une bataille montee.

## Ce que ce module change : la connectivite devient DERIVABLE OFFLINE

`IdunBattle.Operations.InitializeConnectivityOperation$$Execute`, relu verbatim, construit le
`ConnectivityComponent` sur un critere purement TOPOLOGIQUE, sans aucune elevation :

    foreach (tile in board.Tiles)
      foreach (edge in Enum.GetValues(typeof(Edge)))            // 6 valeurs
        if (!tile.TileComponent.HasEdge(edge))                  continue
        (col, row) = (PositionComponent.ColumnAt(edge), RowAt(edge))
        if (!board.IsPositionInside(col, row))                  continue
        nid = board.<grille>[col, row] ; if (nid == 0)           continue
        if (!GetEntity(nid).TileComponent.HasEdge((n/2 + edge) % n))  continue   // n = 6 -> +3
        connectivity.Add(nid)

et `IdunBattle.Entities.Components.TileComponent$$HasEdge(edge)` n'est qu'un `Contains` sur le
tableau d'aretes STOCKE a `TileComponent+0x20`, tableau que
`IdunBattle.Operations.AddTileOperation$$RotateTileEdges` a fait tourner de `Rotation` crans.

⇒ le masque d'aretes est une fonction de **(TileId, Rotation, ForceUnplayable)**, et rien d'autre.
Il y en a **43** distincts sur les 779 boards de `data/boards/**` (11 `TileId`), et **10 boards**
suffisent a tous les rencontrer. On les capte UNE fois, on INVERSE, et la connectivite des 779
autres se derive sans le jeu.

⚠ **L'INVERSION NE DONNE QU'UNE BORNE INFERIEURE, ET C'EST CE QUI REND SES CONCLUSIONS SURES.**
La capture ne montre que les aretes presentes des DEUX cotes : si `A` porte l'arete `e` mais
qu'aucun de ses voisins ne porte l'opposee, `e` reste invisible. Le masque derive est donc
`<= ` le vrai, donc la connectivite derivee est `<=` la vraie, donc le graphe derive est PLUS
morcele que le vrai. Consequence, et c'est le tri qui compte :

  * un board dont le graphe DERIVE est CONNEXE l'est VRAIMENT -> le regime y est IMPOSSIBLE ;
  * un board dont le graphe DERIVE est MORCELE est un CANDIDAT, a confirmer par une capture.

Le controle qui rend la borne credible est une VALIDATION CROISEE : on rejoue le masque contre les
boards captes eux-memes et on exige que la connectivite DERIVEE egale la connectivite OBSERVEE,
arete par arete. Un board tenu HORS de l'ajustement (`--holdout`) mesure la generalisation.

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
ROOT = HERE.parents[1]
BOARDS = ROOT / "data" / "boards"
LOGSDIR = ROOT / "logs" / "p589r2r1"

import build_pin                                                          # noqa: E402

TSV_REL = ("metadata", "tile_edges.tsv")

#: Les SIX directions ABSOLUES, ordonnees pour que l'opposee de `i` soit `(i + 3) % 6` -- ce que le
#: natif calcule litteralement (`(n / 2 + edge) % n` avec `n = 6`). L'INDEX n'est PAS l'ordinal de
#: l'enum `Edge` du jeu et n'a pas a l'etre : ce qu'on derive est le masque des directions
#: ABSOLUES, seul objet dont depend le critere des deux cotes.
#: Convention even-q (parite par COLONNE), la meme que `Board.EVENQ_EVEN/EVENQ_ODD`.
NOMS_DIR = ("N", "NE", "SE", "S", "SW", "NW")
DIR_EVEN = ((0, 1), (1, 1), (1, 0), (0, -1), (-1, 0), (-1, 1))
DIR_ODD = ((0, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0))


def voisin(col: int, row: int, d: int) -> tuple:
    dc, dr = (DIR_EVEN if col % 2 == 0 else DIR_ODD)[d]
    return (col + dc, row + dr)


# ------------------------------------------------------------------ boards de `data/boards/**`

def _effective_elevation(tile_id, brut) -> int:
    """Mirror de `board.py::_effective_elevation` (Trench = terrain CREUSE -> champ BC - 1)."""
    e = int(brut or 0)
    return e - 1 if tile_id == "Trench" else e


def charger_boards() -> dict:
    """`{cle: {"id", "kind", "fichier", "tiles": {(col,row): {...}}}}` -- les 779 definitions.

    ⚠ La cle est le CHEMIN (kind + stem), pas le champ `id` : plusieurs fichiers partagent le meme
    `id` d'un `kind` a l'autre, et keyer par `id` en avait fait DISPARAITRE 104 d'un inventaire
    precedent (779 fichiers rendus comme 675 boards)."""
    out = {}
    for p in sorted(BOARDS.rglob("*.json")):
        j = json.loads(p.read_text(encoding="utf-8"))
        b = j.get("board") or {}
        tiles = {}
        for c, col in enumerate(b.get("Tiles") or []):
            for r, t in enumerate((col or {}).get("Tile") or []):
                if t is None:
                    continue
                tiles[(c, r)] = {
                    "tileId": t.get("TileId"),
                    "rotation": int(t.get("Rotation") or 0),
                    "unplayable": bool(t.get("ForceUnplayable")),
                    "elevation": _effective_elevation(t.get("TileId"), t.get("Elevation", 0)),
                }
        out["%s/%s" % (p.parent.name, p.stem)] = {
            "id": j.get("id") or p.stem, "kind": j.get("kind") or p.parent.name,
            "fichier": p, "tiles": tiles}
    return out


def cle_tuile(t: dict) -> tuple:
    return (t["tileId"], t["rotation"], t["unplayable"])


# ------------------------------------------------------------------ INV : l'inventaire offline

def run_inv() -> int:
    bds = charger_boards()
    paires = Counter()
    par_board = {}
    for k, b in bds.items():
        s = set()
        for t in b["tiles"].values():
            paires[cle_tuile(t)] += 1
            s.add(cle_tuile(t))
        par_board[k] = s
    print("== INV  %d board(s) dans data/boards/**  %d cle(s) (TileId, Rotation, ForceUnplayable)"
          % (len(bds), len(paires)))
    print("   %d TileId distincts : %s"
          % (len({c[0] for c in paires}), ", ".join(sorted({str(c[0]) for c in paires}))))
    restant, choix, dispo = set(paires), [], dict(par_board)
    while restant:
        k = max(dispo, key=lambda x: len(dispo[x] & restant))
        gain = len(dispo[k] & restant)
        if gain == 0:
            break
        choix.append((k, gain))
        restant -= dispo.pop(k)
    print("   COUVERTURE GLOUTONNE : %d board(s) rencontrent les %d cles"
          % (len(choix), len(paires) - len(restant)))
    for k, g in choix:
        print("      %-40s +%d" % (k, g))
    if restant:
        print("   NON COUVERT : %s" % sorted(restant))
        return 1
    return 0


def cover_boards() -> list:
    """Les ids de board de la couverture gloutonne, DERIVES (jamais une liste ecrite a la main)."""
    bds = charger_boards()
    paires = set()
    par_board = {}
    for k, b in bds.items():
        s = {cle_tuile(t) for t in b["tiles"].values()}
        paires |= s
        par_board[k] = s
    restant, choix = set(paires), []
    while restant:
        k = max(par_board, key=lambda x: len(par_board[x] & restant))
        if len(par_board[k] & restant) == 0:
            break
        choix.append(k)
        restant -= par_board.pop(k)
    return [bds[k]["id"] for k in choix]


# ------------------------------------------------------------------ CAPTURE : le `boardGraph`

def _bg_path(board_id: str) -> Path:
    return LOGSDIR / ("bg_%s.json" % board_id)


def _rpc_factory():
    from rl_collect_batch import _resolve_session, _rpc

    def rpc(sid, m, args, t=180):
        r = _rpc(sid, m, [args], timeout=t)
        return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}
    return _resolve_session(), rpc


def _build(board: str, seed: int):
    LOGSDIR.mkdir(parents=True, exist_ok=True)
    state_file = LOGSDIR / ("p589r2r1_state_%s_%d.json" % (board, os.getpid()))
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
           "--board", board, "--p-units", "blackHaarken,bloodIntercessor,necroWarden",
           "--a-units", "necroWarden", "--no-ai", "--state-file", str(state_file)]
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if state_file.exists():
        rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
        return rid, state_file, None
    return None, state_file, ((p.stdout or "") + (p.stderr or ""))[-400:]


def run_capture(ids: list, seed: int, reuse: bool) -> int:
    """Capture le `boardGraph` de chaque board. UN runner a la fois, dispose immediatement."""
    sid, rpc = _rpc_factory()
    LOGSDIR.mkdir(parents=True, exist_ok=True)
    ok, ko = 0, []
    for bid in ids:
        p = _bg_path(bid)
        if reuse and p.exists():
            print("   %-28s deja capte" % bid)
            ok += 1
            continue
        rid, state_file, err = _build(bid, seed)
        if rid is None:
            print("   %-28s BUILD KO : %s" % (bid, (err or "").replace("\n", " ")[-160:]))
            ko.append(bid)
            state_file.unlink(missing_ok=True)
            continue
        try:
            bg = rpc(sid, "boardGraph", {"runnerId": rid}, 180)
            n_conn = sum(1 for t in (bg.get("tiles") or []) if t.get("connectivity") is not None)
            if not n_conn:
                print("   %-28s CANAL `connectivity` ABSENT -- NON MESURE" % bid)
                ko.append(bid)
                continue
            p.write_text(json.dumps(bg), encoding="utf-8")
            print("   %-28s %d tuiles, %d avec connectivity" % (bid, len(bg.get("tiles") or []),
                                                               n_conn))
            ok += 1
        finally:
            try:
                rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
            except Exception:                                            # noqa: BLE001
                pass
            state_file.unlink(missing_ok=True)
    print("== CAPTURE  %d capte(s), %d echec(s) %s" % (ok, len(ko), ko or ""))
    return 1 if ko else 0


# ------------------------------------------------------------------ MASQUES : l'inversion

def _board_par_id(bds: dict, bid: str):
    for k, b in bds.items():
        if b["id"] == bid:
            return b
    return None


def deriver_marchabilite(ids: list, bds: dict) -> tuple:
    """`({cle: bool}, ambigus)` -- `walkable` en fonction de (TileId, Rotation, ForceUnplayable).

    Contrairement au masque d'aretes, ce n'est PAS une borne : `walkable` est publie par le capteur
    pour CHAQUE tuile, donc une cle rencontree une fois est tranchee. Ce qui est falsifiable, c'est
    que ce soit une FONCTION -- une cle qui rendrait les deux valeurs sort en `ambigus`, et alors
    le modele est faux (la marchabilite dependrait d'autre chose)."""
    vus = defaultdict(set)
    for bid in ids:
        p = _bg_path(bid)
        b = _board_par_id(bds, bid)
        if not p.is_file() or b is None:
            continue
        bg = json.loads(p.read_text(encoding="utf-8"))
        for t in (bg.get("tiles") or []):
            pos = (int(t["col"]), int(t["row"]))
            d = b["tiles"].get(pos)
            if d is None:
                continue
            vus[cle_tuile(d)].add(bool(t.get("walkable")))
    ambigus = sorted(k for k, v in vus.items() if len(v) != 1)
    return {k: next(iter(v)) for k, v in vus.items() if len(v) == 1}, ambigus


def deriver_masques(ids: list, bds: dict) -> tuple:
    """`({cle: set(directions)}, diagnostics)` -- la BORNE INFERIEURE lue dans les captures."""
    masques = defaultdict(set)
    diag = []
    for bid in ids:
        p = _bg_path(bid)
        if not p.is_file():
            diag.append((bid, "capture ABSENTE"))
            continue
        bg = json.loads(p.read_text(encoding="utf-8"))
        b = _board_par_id(bds, bid)
        if b is None:
            diag.append((bid, "definition ABSENTE de data/boards/**"))
            continue
        par_pos = {(int(t["col"]), int(t["row"])): t for t in (bg.get("tiles") or [])}
        ids_pos = {int(t["id"]): (int(t["col"]), int(t["row"])) for t in (bg.get("tiles") or [])}
        for pos, t in par_pos.items():
            conn = t.get("connectivity")
            if conn is None:
                continue
            src = b["tiles"].get(pos)
            if src is None:
                diag.append((bid, "tuile %s captee mais absente de la definition" % (pos,)))
                continue
            for nid in conn:
                npos = ids_pos.get(int(nid))
                if npos is None:
                    continue
                d = next((i for i in range(6) if voisin(pos[0], pos[1], i) == npos), None)
                if d is None:
                    diag.append((bid, "voisin %s de %s n'est dans AUCUNE direction hex"
                                 % (npos, pos)))
                    continue
                ndef = b["tiles"].get(npos)
                if ndef is None:
                    continue
                masques[cle_tuile(src)].add(d)
                masques[cle_tuile(ndef)].add((d + 3) % 6)
    return dict(masques), diag


def consolider_par_rotation(masques: dict) -> tuple:
    """Referme la borne inferieure par la SEULE contrainte structurelle disponible : la ROTATION.

    `IdunBattle.Operations.AddTileOperation$$RotateTileEdges` fait tourner le tableau d'aretes du
    prefab de `Rotation` crans, donc

        masque(TileId, r, unplayable) == masque(TileId, 0, unplayable) decale de +r

    -- une identite qu'on VERIFIE avant de s'en servir, elle n'est pas postulee. Le sens du decalage
    est LU dans les donnees et non suppose : `Bridge` l'exhibe seul (rot 0 = {NE, SW}, rot 1 =
    {SE, NW}, rot 2 = {N, S}, puis periode 3), et le controle ci-dessous rejette l'autre sens.

    On prend l'UNION des six temoins ramenes a la rotation 0, puis on redistribue. Chaque temoin
    etant une borne INFERIEURE, l'union en est une meilleure ; et la seule facon qu'elle a de
    SURESTIMER serait que l'identite soit fausse -- ce que la validation croisee (`en_trop != 0`)
    ferait rougir immediatement.

    Rend `(masques consolides, incoherences)`. `incoherences` est VIDE quand chaque temoin observe
    est un sous-ensemble de sa base consolidee -- vrai par construction, donc c'est un controle de
    l'implementation, pas de l'hypothese."""
    bases = defaultdict(set)
    for (tid, rot, unp), dirs in masques.items():
        for d in dirs:
            bases[(tid, unp)].add((d - rot) % 6)
    out, incoh = {}, []
    for (tid, rot, unp), dirs in masques.items():
        plein = {(d + rot) % 6 for d in bases[(tid, unp)]}
        if not dirs <= plein:
            incoh.append((tid, rot, unp, sorted(dirs - plein)))
        out[(tid, rot, unp)] = plein
    return out, incoh


def connectivite_derivee(b: dict, masques: dict) -> tuple:
    """`({(col,row): [(col,row)...]}, inconnues)` -- la connectivite DERIVEE d'une definition.

    `inconnues` = les cles (TileId, Rotation, ForceUnplayable) qu'aucune capture n'a rencontrees :
    tri-etat, un board qui en porte n'est PAS mesure (jamais rendu comme un zero)."""
    adj = {pos: [] for pos in b["tiles"]}
    inconnues = set()
    for pos, t in b["tiles"].items():
        k = cle_tuile(t)
        m = masques.get(k)
        if m is None:
            inconnues.add(k)
            continue
        for d in m:
            npos = voisin(pos[0], pos[1], d)
            nt = b["tiles"].get(npos)
            if nt is None:
                continue
            nm = masques.get(cle_tuile(nt))
            if nm is None:
                inconnues.add(cle_tuile(nt))
                continue
            if (d + 3) % 6 in nm:
                adj[pos].append(npos)
    return adj, inconnues


def run_masques(ids: list, holdout: list, regenerer: bool, brut: bool = False) -> int:
    bds = charger_boards()
    ajust = [b for b in ids if b not in holdout]
    masques, diag = deriver_masques(ajust, bds)
    if not brut:
        masques, incoh = consolider_par_rotation(masques)
        print("   CONSOLIDATION PAR ROTATION : %d incoherence(s)" % len(incoh))
        for x in incoh[:6]:
            print("      %s rot=%d unplayable=%s : directions hors base %s" % x)
        if incoh:
            return 1
    print("== MASQUES  ajustes sur %d board(s), %d cle(s) rencontree(s)" % (len(ajust), len(masques)))
    for k in sorted(masques, key=lambda x: (str(x[0]), x[1], x[2])):
        print("   %-14s rot=%d unplayable=%-5s  %s"
              % (k[0], k[1], k[2], "".join(NOMS_DIR[d] + " " for d in sorted(masques[k])) or "(aucune)"))
    for bid, why in diag[:10]:
        print("   DIAG %-24s %s" % (bid, why))

    # --- VALIDATION : la connectivite DERIVEE egale-t-elle l'OBSERVEE, arete par arete ?
    bad = 0
    for bid in ids:
        p = _bg_path(bid)
        b = _board_par_id(bds, bid)
        if not p.is_file() or b is None:
            continue
        bg = json.loads(p.read_text(encoding="utf-8"))
        ids_pos = {int(t["id"]): (int(t["col"]), int(t["row"])) for t in (bg.get("tiles") or [])}
        obs = set()
        for t in (bg.get("tiles") or []):
            pos = (int(t["col"]), int(t["row"]))
            for nid in (t.get("connectivity") or []):
                npos = ids_pos.get(int(nid))
                if npos is not None:
                    obs.add((pos, npos))
        adj, inconnues = connectivite_derivee(b, masques)
        # on ne compare que sur les tuiles REELLEMENT captees (le board peut porter des positions
        # que la bataille ne materialise pas).
        captees = set(ids_pos.values())
        der = {(a, x) for a, l in adj.items() for x in l if a in captees and x in captees}
        obs = {e for e in obs if e[0] in captees and e[1] in captees}
        manquantes, en_trop = obs - der, der - obs
        marque = "HOLDOUT" if bid in holdout else "ajuste "
        etat = "OK" if not manquantes and not en_trop else "ECART"
        print("   [%s] %-28s %-5s obs=%4d der=%4d  manquantes=%d en_trop=%d%s"
              % (marque, bid, etat, len(obs), len(der), len(manquantes), len(en_trop),
                 "  INCONNUES=%d" % len(inconnues) if inconnues else ""))
        if manquantes or en_trop:
            bad += 1
            for e in sorted(manquantes)[:4]:
                print("        MANQUANTE %s -> %s" % e)
            for e in sorted(en_trop)[:4]:
                print("        EN TROP   %s -> %s" % e)
    if not masques:
        print("   AUCUN masque derive -- rien n'est mesure")
        return 1
    marche, ambigus = deriver_marchabilite(ids, bds)
    print("   MARCHABILITE : %d cle(s) tranchee(s), %d AMBIGUE(S)" % (len(marche), len(ambigus)))
    if ambigus:
        print("      %s" % ambigus[:6])
        bad += 1
    if regenerer:
        print("   ecrit : %s" % ecrire_tsv(masques, ajust, marche).as_posix())
    return 1 if bad else 0


def tsv_path(build: str | None = None) -> Path:
    return ROOT / "data" / "symbols" / (build or build_pin.current_build()) / Path(*TSV_REL)


def ecrire_tsv(masques: dict, ajust: list, marchable: dict | None = None) -> Path:
    marchable = marchable or {}
    p = tsv_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lignes = [
        "# Masque d'aretes par (TileId, Rotation, ForceUnplayable) -- build %s."
        % build_pin.current_build(),
        "# DERIVE par INVERSION du champ `connectivity` du `boardGraph` de %d board(s) : %s"
        % (len(ajust), ", ".join(sorted(ajust))),
        "# Ce que le natif en fait : `IdunBattle.Operations.InitializeConnectivityOperation$$Execute`",
        "# relie deux tuiles voisines ssi CHACUNE porte l'arete vers l'autre",
        "# (`IdunBattle.Entities.Components.TileComponent$$HasEdge`, opposee = `(edge + 3) % 6`).",
        "# Directions ABSOLUES even-q, index i oppose a (i+3)%%6 : %s" % " ".join(NOMS_DIR),
        "# BORNE INFERIEURE : une arete que la capture n'a jamais vue des DEUX cotes n'y est pas.",
        "# Regenerer : python scripts/python/probe_589r2r1_beeline_sans_chemin.py --only MASQUES"
        " --regenerer",
        "# `walkable` est LU tel quel par tuile (pas une borne) ; il est ici parce que le meme",
        "# couple (TileId, ForceUnplayable) le determine -- verifie FONCTION sur les captures.",
        "#tileId\trotation\tunplayable\tdirections\twalkable",
    ]
    for k in sorted(masques, key=lambda x: (str(x[0]), x[1], x[2])):
        w = marchable.get(k)
        lignes.append("%s\t%d\t%d\t%s\t%s" % (k[0], k[1], 1 if k[2] else 0,
                                              ",".join(NOMS_DIR[d] for d in sorted(masques[k])),
                                              "" if w is None else (1 if w else 0)))
    p.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return p


def lire_tsv(avec_marche: bool = False):
    """`{cle: set(directions)}`, ou `({cle: dirs}, {cle: walkable})` si `avec_marche`."""
    p = tsv_path()
    if not p.is_file():
        raise SystemExit(
            "ROUGE : l'entree versionnee est absente (%s).\n"
            "  La regenerer sur une machine ou le jeu tourne :\n"
            "  python scripts/python/probe_589r2r1_beeline_sans_chemin.py --only CAPTURE\n"
            "  python scripts/python/probe_589r2r1_beeline_sans_chemin.py --only MASQUES"
            " --regenerer" % p.as_posix())
    idx = {n: i for i, n in enumerate(NOMS_DIR)}
    out, marche = {}, {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        c = line.split("\t")
        if len(c) < 4:
            continue
        cle = (c[0], int(c[1]), bool(int(c[2])))
        out[cle] = {idx[x] for x in c[3].split(",") if x}
        if len(c) >= 5 and c[4] != "":
            marche[cle] = bool(int(c[4]))
    return (out, marche) if avec_marche else out


def board_derive(bid: str):
    """Un `engine.entities.pathfinding.board.Board` DERIVE, sans aucune capture.

    Les quatre champs que les pathfinders lisent sont tous derivables de `data/boards/**` et de
    l'entree versionnee : `col`/`row`/`elevation` de la definition, `walkable` de la table,
    `connectivity` du masque d'aretes (critere natif des DEUX cotes), et `neighbours` = la meme
    liste passee par la porte `|dElev| < 2` que `TileQuery$$IterateAdjacentTiles` applique
    INCONDITIONNELLEMENT au champ que le capteur lit.

    ⚠ Il n'invente RIEN : il rend `None` des qu'une cle de tuile du board n'est pas dans la table
    (tri-etat), pour qu'un appelant DISE << non mesure >> au lieu de rendre un graphe partiel."""
    from engine.entities.pathfinding.board import Board
    masques, marche = lire_tsv(avec_marche=True)
    b = _board_par_id(charger_boards(), bid)
    if b is None:
        return None, "definition absente de data/boards/**"
    inconnues = {cle_tuile(t) for t in b["tiles"].values() if cle_tuile(t) not in masques}
    if inconnues:
        return None, "cle(s) de tuile hors table : %s" % sorted(inconnues)[:4]
    idof = {pos: i + 1 for i, pos in enumerate(sorted(b["tiles"]))}
    adj, _ = connectivite_derivee(b, masques)
    tiles = []
    for pos in sorted(b["tiles"]):
        t = b["tiles"][pos]
        conn = [idof[x] for x in adj[pos]]
        # `neighbours` = `connectivity` INTERSECTE {|dElev| < 2} -- l'identite MESUREE de
        # `board.py::base_add_neighbours` (le capteur passe par `IterateAdjacentTiles`).
        nb = [idof[x] for x in adj[pos] if abs(b["tiles"][x]["elevation"] - t["elevation"]) < 2]
        tiles.append({"id": idof[pos], "col": pos[0], "row": pos[1],
                      "elevation": t["elevation"],
                      "walkable": bool(marche.get(cle_tuile(t), True)), "isWall": False,
                      "neighbours": nb, "connectivity": conn})
    return Board(tiles, adjacency="native_sym"), None


# ------------------------------------------------------------------ SCAN : les 779 boards

def _composantes(adj: dict) -> list:
    """Composantes de la relation d'ACCESSIBILITE non orientee. Le critere du natif est symetrique
    par construction (arete exigee des DEUX cotes), et la capture le confirme : 0 arete one-way."""
    vus, comps = set(), []
    for s in adj:
        if s in vus:
            continue
        q, comp = deque([s]), set()
        vus.add(s)
        while q:
            x = q.popleft()
            comp.add(x)
            for y in adj.get(x, ()):
                if y not in vus:
                    vus.add(y)
                    q.append(y)
        comps.append(comp)
    return comps


def run_scan(seuil_bavard: int) -> int:
    masques = lire_tsv()
    bds = charger_boards()
    n_mesures = n_non = 0
    morceles = []
    for k in sorted(bds):
        b = bds[k]
        adj, inconnues = connectivite_derivee(b, masques)
        if inconnues:
            n_non += 1
            continue
        n_mesures += 1
        comps = _composantes(adj)
        # les tuiles ISOLEES (0 arete) sont le cas degenere : elles morcellent le graphe, mais un
        # waypoint de vol ne peut pas y atterrir sans que le vol lui-meme y accede -- on les COMPTE
        # a part au lieu de les confondre avec une VRAIE poche.
        grosses = [c for c in comps if len(c) > 1]
        isolees = [c for c in comps if len(c) == 1]
        if len(grosses) > 1 or (grosses and isolees):
            morceles.append((k, len(b["tiles"]), sorted((len(c) for c in comps), reverse=True)))
    print("== SCAN  %d board(s) MESURE(S), %d NON MESURE(S) (cle de tuile jamais captee)"
          % (n_mesures, n_non))
    print("   %d board(s) dont la connectivite DERIVEE est MORCELEE" % len(morceles))
    for k, n, tailles in morceles[:seuil_bavard]:
        print("      %-40s %3d tuiles  composantes=%s" % (k, n, tailles[:8]))
    if len(morceles) > seuil_bavard:
        print("      ... et %d de plus" % (len(morceles) - seuil_bavard))
    if n_mesures == 0:
        print("   AUCUN board mesure -- le masque ne couvre rien")
        return 1
    print("   RAPPEL DE PORTEE : le masque est une BORNE INFERIEURE, donc")
    print("     * CONNEXE derive => CONNEXE reel  => le regime `#589-r2-r1` y est IMPOSSIBLE ;")
    print("     * MORCELE derive => CANDIDAT seulement, a confirmer par une capture.")
    return 0


# ------------------------------------------------------------------ REGIME : est-il ATTEINT ?

def mesurer_regime(bd) -> dict:
    """Les TROIS etages du regime sur un `Board` donne (capte ou derive).

    [1] la beeline echoue-t-elle sur un couple quelconque a `d_hex > 1` ?
    [2] un chemin de VOL produit-il un saut que la beeline ne recoud pas ?
    [3] **et ce saut nait-il d'un MOUVEMENT LEGAL** ? C'est le seul etage qui reponde a
        << le moteur peut-il y arriver >> : `MovementQuery$$GetConnectedPathTo` n'est appele que
        par `UnitExtensions$$RecordTilesMoved`, APRES un deplacement -- donc `from` est la tuile ou
        l'unite se tenait (MARCHABLE) et `to` celle ou elle arrive (MARCHABLE aussi, un
        `IsMovableTile` l'exige). Un saut dont les extremites du MOUVEMENT ne sont pas marchables
        est geometriquement reel et INATTEIGNABLE en jeu -- les confondre serait exactement le
        << bloque par la geometrie de spawn >> que la doctrine interdit, a l'envers."""
    from engine.entities.pathfinding import beeline_pathfinder as BL
    from engine.entities.pathfinding import pathfinders as PF
    import hexgeo

    ids = sorted(bd.by_id)
    marchables = {i for i in ids if bd.walkable(i)}
    r = {"tuiles": len(ids), "marchables": len(marchables), "couples": 0, "sans_chemin": 0,
         "sauts": 0, "sauts_sans": 0, "sauts_sans_legaux": 0, "exemples": [], "legaux": []}
    for a in ids:
        for b in ids:
            if a == b or hexgeo.distance(bd.coord(a), bd.coord(b)) <= 1:
                continue
            r["couples"] += 1
            if BL.find_path(bd, a, b) is None:
                r["sans_chemin"] += 1
                if len(r["exemples"]) < 6:
                    r["exemples"].append((bd.coord(a), bd.coord(b)))
    for a in ids:
        for b in ids:
            if a == b:
                continue
            path = PF.find_path(bd, 3, a, b)          # PathfinderType.Fly
            if not path:
                continue
            legal = a in marchables and b in marchables
            for x, y in zip(path, path[1:]):
                if hexgeo.distance(bd.coord(x), bd.coord(y)) <= 1:
                    continue
                r["sauts"] += 1
                if BL.find_path(bd, x, y) is None:
                    r["sauts_sans"] += 1
                    if legal:
                        r["sauts_sans_legaux"] += 1
                        if len(r["legaux"]) < 6:
                            r["legaux"].append((bd.coord(a), bd.coord(b),
                                                bd.coord(x), bd.coord(y)))
    return r


def run_regime(board_id: str, seed: int, reuse: bool, derive: bool = False) -> int:
    from engine.entities.pathfinding.board import Board

    if derive:
        bd, why = board_derive(board_id)
        if bd is None:
            print("   NON MESURE (%s)" % why)
            return 1
        source = "DERIVE de l'entree versionnee"
    else:
        p = _bg_path(board_id)
        if not p.is_file():
            if reuse:
                print("   capture absente pour %s -- relancer --only CAPTURE" % board_id)
                return 1
            run_capture([board_id], seed, reuse=False)
        bg = json.loads(p.read_text(encoding="utf-8"))
        bd = Board(bg["tiles"], adjacency="native_sym")
        if not bd.has_connectivity_channel():
            print("   CANAL ABSENT -- NON MESURE")
            return 1
        source = "CAPTURE live"

    r = mesurer_regime(bd)
    print("== REGIME  board=%s  %s  %d tuiles (%d marchables)"
          % (board_id, source, r["tuiles"], r["marchables"]))
    print("   [1] BEELINE : %d couple(s) a d_hex > 1 ; %d SANS chemin"
          % (r["couples"], r["sans_chemin"]))
    for e in r["exemples"]:
        print("        %s -> %s" % e)
    print("   [2] VOL : %d saut(s) a recoudre ; %d SANS chemin beeline"
          % (r["sauts"], r["sauts_sans"]))
    if r["sauts"] == 0:
        print("       ECART : aucun saut -- ce board ne fait PAS jouer la beeline, la mesure [2]")
        print("               ne sait rien voir ici (elle n'est pas un zero)")
    print("   [3] dont issus d'un MOUVEMENT LEGAL (deux extremites marchables) : %d"
          % r["sauts_sans_legaux"])
    for e in r["legaux"]:
        print("        move %s -> %s   saut %s -> %s" % e)
    if r["sauts_sans_legaux"]:
        print("   REGIME ATTEINT EN JEU : le port avalerait %d absence(s) et compterait 1 arete"
              % r["sauts_sans_legaux"])
        return 1
    if r["sauts_sans"]:
        print("   REGIME GEOMETRIQUEMENT REEL, INATTEIGNABLE PAR UN MOUVEMENT LEGAL")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="INV",
                    choices=["INV", "CAPTURE", "MASQUES", "SCAN", "REGIME"])
    ap.add_argument("--boards", default=None, help="liste d'ids ; defaut = la couverture DERIVEE")
    ap.add_argument("--holdout", default="", help="ids tenus HORS de l'ajustement des masques")
    ap.add_argument("--board", default="C1_74")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--regenerer", action="store_true")
    ap.add_argument("--brut", action="store_true",
                    help="n'applique PAS la consolidation par rotation (borne inferieure NUE)")
    ap.add_argument("--no-reuse", action="store_true")
    ap.add_argument("--bavard", type=int, default=25)
    ap.add_argument("--derive", action="store_true",
                    help="REGIME sur un board DERIVE de l'entree versionnee (aucune capture)")
    a = ap.parse_args()

    ids = ([x.strip() for x in a.boards.split(",") if x.strip()] if a.boards else cover_boards())
    holdout = [x.strip() for x in a.holdout.split(",") if x.strip()]
    if a.only == "INV":
        return run_inv()
    if a.only == "CAPTURE":
        return run_capture(ids, a.seed, not a.no_reuse)
    if a.only == "MASQUES":
        return run_masques(ids, holdout, a.regenerer, a.brut)
    if a.only == "SCAN":
        return run_scan(a.bavard)
    return run_regime(a.board, a.seed, not a.no_reuse, a.derive)


if __name__ == "__main__":
    raise SystemExit(main())
