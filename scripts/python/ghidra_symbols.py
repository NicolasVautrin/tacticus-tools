#!/usr/bin/env python3
"""Table de symboles du build courant : extraction, resolution, verification.

SOURCE DE VERITE = le serveur `ghidra-mcp` (HTTP 127.0.0.1:13337), qui a charge le
`GameAssembly.dll` du build INSTALLE et lui a applique les noms IL2CPP. C'est la seule
source verifiee : les tables `data/il2cpp_*.tsv` heritees d'un dump Il2CppDumper sont
PERIMEES (mesure 2026-07-25 : `BattleQuery.ConvertRoundsToTurns` y est a la RVA 0x10e25f0
alors que le build courant la place a 0x1058af0).

FORME CANONIQUE d'un symbole = EXACTEMENT ce que Ghidra emet, sans retouche :
    IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns
    IdunBattle.Entities.Effects.Loki.SmashaEadEffect$$CreateEffectDamageBonusForAttack
Les lambdas generes gardent leur echappement Ghidra (`u003C` = `<`, `u003E` = `>`) : c'est
ce qui rend le grep code <-> table immediat. Un point INTERNE a une fonction se cite
`<symbole>+0x<offset>` (offset RELATIF, il ne peut pas perimer sur un simple relogement).

Sous-commandes :
    dump      -> ecrit data/symbols/<HASH>/ghidra/functions.tsv (adresse, symbole)
    resolve   -> symbole (ou regex) -> adresse
    whereis   -> adresse -> symbole + offset interne
    build     -> le hash du build charge par ghidra-mcp
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

MCP_URL = "http://127.0.0.1:13337/mcp"
BINARY = "GameAssembly.dll"
IMAGE_BASE = 0x180000000
REPO = Path(__file__).resolve().parents[2]
SYMBOLS_DIR = REPO / "data" / "symbols"

_HDRS = {"Content-Type": "application/json",
         "Accept": "application/json, text/event-stream"}


class GhidraDown(RuntimeError):
    """ghidra-mcp injoignable : message ACTIONNABLE (le lancement est manuel)."""


class GhidraMCP:
    """Client MCP/HTTP minimal — juste ce qu'il faut pour interroger les symboles."""

    def __init__(self, url: str = MCP_URL, timeout: float = 120):
        self.url = url
        self.session = None
        # 120 s convient a un `dump` (des dizaines de milliers de symboles pagines). Un appelant
        # qui ne fait qu'INTERROGER (ex. la garde de synchro au demarrage de session) doit pouvoir
        # BORNER son attente : sans ca, un serveur a moitie mort bloque l'appelant deux minutes.
        self.timeout = timeout

    def _post(self, payload: dict) -> str:
        h = dict(_HDRS)
        if self.session:
            h["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode(),
                                     headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                if not self.session:
                    self.session = r.headers.get("Mcp-Session-Id")
                return r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, OSError) as exc:
            raise GhidraDown(
                "ghidra-mcp injoignable sur %s (%s).\n"
                "  Le serveur ne demarre PAS tout seul :\n"
                "    pwsh -File C:\\Users\\nicolasv\\ghidra-mcp\\start-ghidra-mcp.ps1\n"
                "  Boot ~2 min ; le port n'ecoute qu'une fois l'analyse terminee." % (self.url, exc))

    @staticmethod
    def _frames(body: str) -> list:
        out = []
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    out.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    pass
        if not out and body.strip().startswith("{"):
            out.append(json.loads(body))
        return out

    def connect(self) -> "GhidraMCP":
        self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "ghidra_symbols", "version": "1"}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    def call(self, tool: str, args: dict):
        body = self._post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                           "params": {"name": tool, "arguments": args}})
        frames = self._frames(body)
        if not frames:
            raise GhidraDown("reponse vide de ghidra-mcp pour %s" % tool)
        res = frames[0].get("result") or {}
        if frames[0].get("error"):
            raise RuntimeError("ghidra-mcp %s : %s" % (tool, frames[0]["error"]))
        txt = (res.get("content") or [{}])[0].get("text", "")
        return json.loads(txt) if txt.strip().startswith(("{", "[")) else txt


def loaded_build(g: GhidraMCP) -> str:
    """Hash du build effectivement charge par ghidra-mcp (lu du chemin du binaire)."""
    progs = (g.call("list_project_binaries", {}) or {}).get("programs") or []
    for p in progs:
        m = re.search(r"/tacticus/games/([^/]+)/", p.get("file_path") or "")
        if m:
            return m.group(1)
    raise RuntimeError("impossible de deduire le build depuis ghidra-mcp : %r" % progs)


def iter_functions(g: GhidraMCP, page: int = 2000):
    """Toutes les fonctions nommees, par pages (ne charge jamais tout en memoire d'un coup)."""
    offset = 0
    seen = set()
    while True:
        res = g.call("search_symbols_by_name",
                     {"binary_name": BINARY, "query": ".*", "functions_only": True,
                      "limit": page, "offset": offset})
        syms = (res or {}).get("symbols") or []
        if not syms:
            return
        for s in syms:
            key = (s.get("address"), s.get("name"))
            if key in seen:
                continue
            seen.add(key)
            yield s
        if len(syms) < page:
            return
        offset += len(syms)


def cmd_build(_args) -> int:
    g = GhidraMCP().connect()
    print(loaded_build(g))
    return 0


def cmd_dump(args) -> int:
    g = GhidraMCP().connect()
    build = loaded_build(g)
    out_dir = SYMBOLS_DIR / build / "ghidra"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "functions.tsv"
    n = 0
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("# build=%s  source=ghidra-mcp(%s)  forme=<adresse VA hexa>\\t<symbole Ghidra verbatim>\n"
                 % (build, BINARY))
        for s in iter_functions(g, page=args.page):
            fh.write("%s\t%s\n" % (s["address"], s["name"]))
            n += 1
            if n % 20000 == 0:
                print("  ... %d symboles" % n, flush=True)
    (out_dir / "BUILD").write_text(build + "\n", encoding="utf-8")
    print("OK  %d symboles -> %s" % (n, out.relative_to(REPO)))
    print("    marqueur build -> %s" % (out_dir / "BUILD").relative_to(REPO))
    return 0


def _table_for(build: str) -> Path:
    p = SYMBOLS_DIR / build / "ghidra" / "functions.tsv"
    if not p.exists():
        raise SystemExit("table absente pour le build %s : lancer `ghidra_symbols.py dump`" % build)
    return p


def load_table(build: str) -> dict:
    """symbole -> adresse (int). Table du build donne."""
    out = {}
    with _table_for(build).open(encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            addr, _, name = line.rstrip("\n").partition("\t")
            if name:
                out[name] = int(addr, 16)
    return out


def cmd_resolve(args) -> int:
    g = GhidraMCP().connect()
    res = g.call("search_symbols_by_name",
                 {"binary_name": BINARY, "query": args.query,
                  "functions_only": True, "limit": args.limit})
    syms = (res or {}).get("symbols") or []
    if not syms:
        print("AUCUN symbole ne matche %r" % args.query)
        return 1
    for s in syms:
        print("%s\t%s" % (s["address"], s["name"]))
    return 0


def cmd_whereis(args) -> int:
    """adresse -> symbole englobant + offset interne (forme de citation `<symbole>+0x<off>`)."""
    va = int(args.address.lstrip("@").replace("0x", ""), 16)
    g = GhidraMCP().connect()
    build = loaded_build(g)
    table = load_table(build)
    best_name, best_addr = None, -1
    for name, addr in table.items():
        if addr <= va and addr > best_addr:
            best_name, best_addr = name, addr
    if best_name is None:
        print("@%x : aucun symbole a cette adresse ou avant (table du build %s)" % (va, build))
        return 1
    off = va - best_addr
    print("%s%s" % (best_name, ("+0x%x" % off) if off else ""))
    print("  (debut de fonction @%x, offset interne 0x%x, build %s)" % (best_addr, off, build))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("dump", help="ecrit data/symbols/<HASH>/ghidra/functions.tsv")
    p.add_argument("--page", type=int, default=2000)
    p.set_defaults(func=cmd_dump)

    p = sub.add_parser("resolve", help="symbole/regex -> adresse (interroge ghidra en direct)")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("whereis", help="adresse -> <symbole>+0x<offset>")
    p.add_argument("address")
    p.set_defaults(func=cmd_whereis)

    p = sub.add_parser("build", help="hash du build charge par ghidra-mcp")
    p.set_defaults(func=cmd_build)

    args = ap.parse_args()
    try:
        return args.func(args)
    except GhidraDown as exc:
        print("ERREUR : %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
