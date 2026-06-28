"""Outil d'AUTORING (offline) : résout les clés de poids d'un playbook / utility.

Pipeline prouvé (cf. docs/rl/playbook-engine.md §14.6) :
  décompile (ghidra) le playbook → relève les `DAT_<VA>` passés à `GetUtilityValue`
  → cet outil mappe chaque VA → clé string-literal (via Il2CppDumper `stringliteral.json`)
  → valeur de poids BC (via `Utilities.Default.<catégorie>.<clé>`).

⇒ les poids des playbooks sont **extractibles offline** (PAS de capture live) : `stringliteral.json`
est sur disque par build, et les valeurs sont dans la `BattleConfiguration`.

Usage :
  python playbook_keys.py 0x18325a560 0x18325a2e0 0x18325a420      # résout des VAs
  python playbook_keys.py --grep SAVIORPROTOCOLS                    # liste les littéraux + valeurs BC
  python playbook_keys.py --hash gqfc5mff6c 0x18325a560            # build explicite

Note : `DAT_<VA>` est une VA (base image 0x180000000). RVA = VA - base. `stringliteral.json`
indexe par RVA hex (ex. "0x325A560").
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

IMAGE_BASE = 0x180000000
_REPO = Path(__file__).resolve().parents[2]
_DUMPS = _REPO / "data" / "dumps"
_BC = _REPO / "data" / "arena-battle-config-newtonsoft.json"


def _current_hash() -> str | None:
    """Hash du build courant (dossier games), sinon le dump le plus récent avec stringliteral.json."""
    games = glob.glob("C:/Users/nicolasv/AppData/Local/tacticus/games/*/")
    if games:
        h = Path(games[0].rstrip("/\\")).name
        if (_DUMPS / h / "stringliteral.json").exists():
            return h
    cands = sorted(_DUMPS.glob("*/stringliteral.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0].parent.name if cands else None


def load_strlit(build_hash: str) -> dict[int, str]:
    """address(RVA int) -> value. stringliteral.json = [{value, address:"0x..."}]."""
    p = _DUMPS / build_hash / "stringliteral.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    return {int(e["address"], 16): e["value"] for e in raw}


def load_bc_index() -> dict[str, list[tuple[str, float]]]:
    """clé de poids -> [(catégorie, valeur)] sur tout Utilities.Default (clés non uniques entre catégories)."""
    bc = json.loads(_BC.read_text(encoding="utf-8"))
    idx: dict[str, list[tuple[str, float]]] = {}
    for cat, sub in (bc.get("Utilities", {}).get("Default", {}) or {}).items():
        if isinstance(sub, dict):
            for k, v in sub.items():
                if isinstance(v, (int, float)):
                    idx.setdefault(k, []).append((cat, v))
    return idx


def resolve_va(va: int, strlit: dict[int, str], bc: dict) -> dict:
    rva = va - IMAGE_BASE if va >= IMAGE_BASE else va
    key = strlit.get(rva)
    return {"va": hex(va), "rva": hex(rva), "key": key,
            "bc": bc.get(key, []) if key else []}


def main(argv: list[str]) -> int:
    build_hash = None
    grep = None
    vas: list[int] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--hash":
            i += 1; build_hash = argv[i]
        elif a == "--grep":
            i += 1; grep = argv[i]
        else:
            vas.append(int(a, 16))
        i += 1

    build_hash = build_hash or _current_hash()
    if not build_hash:
        print("aucun dump stringliteral.json trouvé sous data/dumps/", file=sys.stderr)
        return 2
    strlit = load_strlit(build_hash)
    bc = load_bc_index()
    print(f"[playbook_keys] build={build_hash}  literals={len(strlit)}  bc_keys={len(bc)}")

    if grep:
        g = grep.lower()
        hits = sorted({v for v in strlit.values() if g in v.lower()})
        for v in hits:
            print(f"  {v!r:60} bc={bc.get(v, [])}")
        print(f"  ({len(hits)} littéraux)")
        return 0

    for va in vas:
        r = resolve_va(va, strlit, bc)
        print(f"  {r['va']} (rva {r['rva']}) -> {r['key']!r}  bc={r['bc']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
