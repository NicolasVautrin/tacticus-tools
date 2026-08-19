#!/usr/bin/env python
"""dump_boards - regenere les artefacts LIVE du harnais sur disque.

Regenere DEUX artefacts que le harnais de tests live + `rl_duel build`
attendent dans `data/` (gitignore -> jamais versionnes, PURGES par tout menage
de `data/` : git clean -fdx, nettoyage disque) :

  1. `data/boards/{pvp,syncPvp,global}/<id>.json` : les board dumps (records
     `{id, kind, spawnPointsSet, board}` via `rl_collect_batch._load_board_dump`),
     lus par `rl_duel build --board/--board-pool`.
  2. `data/seed-bc.json` : le seed BC template (skeleton Players/Utilities/mode)
     que `buildNormalizedBC` normalise pour extraire le pool + swapper le board.
     Lu par `rl_collect_batch._load_seed_bc`.

Sans eux : tous les tests live SKIPent SILENCIEUSEMENT (skip vert = couverture
nulle masquee) et `--board` echoue. Ce script les REGENERE en une commande, de
facon reproductible, a REFAIRE au changement de hash du build (cf. #159).

SOURCES (live) :
  - boards : RPC `dumpPvpAndSyncBoards` (hook dump-pvp-boards.ts) -> enumere
    gameConfig.battles.{pvpBoards,syncPvpBoards} + gameConfig.boardsToInclude
    (global), charge chaque board via IdunAssetsUtil.LoadBoard(string), serialise
    (Newtonsoft). Sortie BoardDump[] = {id, kind, spawnPointsSet, json, err?} ->
    on parse `json` -> `board`.
  - seed BC : RPC `dumpBattleConfig` (getLiveBattleConfig, priorite PvP>MoW>Campaign)
    -> configJson (BC live serialisee).

PRE-REQUIS : session Frida warmee (les RPC ont besoin de lastGameConfig +
serializer prets). Le script fait l'amorce lui-meme (idempotent).

USAGE (depuis scripts/python) :
    python dump_boards.py                 # boards (3 kinds) + seed-bc.json
    python dump_boards.py --kinds pvp     # un seul kind de boards
    python dump_boards.py --no-seed-bc    # boards seulement
    python dump_boards.py --seed-bc-only  # seed-bc.json seulement
"""
from __future__ import annotations

import argparse
import json
import sys

import rl_collect_batch as R

KINDS = ("pvp", "syncPvp", "global")


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def dump_seed_bc(sid: int) -> int:
    """Capture le seed BC live -> data/seed-bc.json. Retourne sa taille (bytes)."""
    res = _unwrap(R._rpc(sid, "dumpBattleConfig", [], timeout=60))
    if not (isinstance(res, dict) and res.get("ok") and res.get("configJson")):
        raise RuntimeError(f"dumpBattleConfig KO: {str(res)[:200]}")
    cfg = res["configJson"]
    R.SEED_BC.parent.mkdir(parents=True, exist_ok=True)
    R.SEED_BC.write_text(cfg, encoding="utf-8")
    return len(cfg)


def dump_kind(sid: int, kind: str) -> tuple[int, int, list[str]]:
    """Dump un seul kind (chunk pour limiter le payload / la duree main-thread).
    Retourne (ecrits, erreurs, liste_ids_en_erreur)."""
    opts = {k: (k == kind) for k in KINDS}
    res = _unwrap(R._rpc(sid, "dumpPvpAndSyncBoards", [opts], timeout=300))
    if not (isinstance(res, dict) and res.get("ok")):
        raise RuntimeError(f"dumpPvpAndSyncBoards({kind}) KO: {str(res)[:200]}")
    out_dir = R.BOARDS_DIR / kind
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    errs: list[str] = []
    for b in res.get("boards", []):
        bid = b.get("id")
        if b.get("err") or not b.get("json"):
            errs.append(f"{bid}: {b.get('err') or 'json vide'}")
            continue
        try:
            board = json.loads(b["json"])
        except Exception as e:
            errs.append(f"{bid}: parse json KO ({e})")
            continue
        record = {
            "id": bid,
            "kind": b.get("kind", kind),
            "spawnPointsSet": b.get("spawnPointsSet"),
            "board": board,
        }
        (out_dir / f"{bid}.json").write_text(
            json.dumps(record), encoding="utf-8")
        written += 1
    return written, len(errs), errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kinds", default=",".join(KINDS),
                    help="kinds a dumper (csv parmi pvp,syncPvp,global)")
    ap.add_argument("--no-seed-bc", action="store_true",
                    help="ne pas (re)capturer data/seed-bc.json")
    ap.add_argument("--seed-bc-only", action="store_true",
                    help="capturer UNIQUEMENT data/seed-bc.json (pas de boards)")
    ap.add_argument("--no-amorce", action="store_true",
                    help="sauter l'amorce (deja fait cette session)")
    a = ap.parse_args()
    kinds = [] if a.seed_bc_only else [k.strip() for k in a.kinds.split(",") if k.strip()]
    bad = [k for k in kinds if k not in KINDS]
    if bad:
        print(f"[error] kinds inconnus: {bad} (attendu parmi {KINDS})",
              file=sys.stderr)
        return 2

    try:
        sid = R._resolve_session()
    except Exception as e:
        print(f"[error] pas de session Frida (lance Tacticus + inject): {e}",
              file=sys.stderr)
        return 2
    print(f"[dump_boards] session={sid} kinds={kinds} -> {R.BOARDS_DIR}")

    if not a.no_amorce:
        print("[dump_boards] amorce (idempotent)...")
        w = _unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=180))
        if not (isinstance(w, dict) and w.get("ok")):
            print(f"[error] amorce KO: {str(w)[:200]}", file=sys.stderr)
            return 2

    total_w = total_e = 0
    for kind in kinds:
        w, e, errs = dump_kind(sid, kind)
        total_w += w
        total_e += e
        print(f"[dump_boards] {kind}: {w} ecrits, {e} erreurs")
        for msg in errs[:8]:
            print(f"    - {msg}")
        if len(errs) > 8:
            print(f"    ... (+{len(errs) - 8} autres)")
    if kinds:
        print(f"[dump_boards] boards: {total_w} ecrits, {total_e} erreurs "
              f"dans {R.BOARDS_DIR}")

    if not a.no_seed_bc:
        n = dump_seed_bc(sid)
        print(f"[dump_boards] seed BC: {n} bytes -> {R.SEED_BC}")

    ok = (total_w > 0) or a.seed_bc_only or a.no_seed_bc is False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
