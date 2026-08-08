#!/usr/bin/env python3
"""Client MCP minimal vers le serveur ghidra (HTTP streamable, 127.0.0.1:13337).

POURQUOI CE MODULE EXISTE (#594)
--------------------------------
L'outil d'agent `mcp__ghidra__decompile_function` rend son texte DANS LE CONTEXTE. Mesure du
2026-08-08 : les 139 `.ctor` d'ability du registre pesent 197 784 caracteres de decompile,
pour en extraire DEUX constantes par ability. Ce client parle au MEME serveur, en JSON-RPC,
et rend une structure Python -- l'appelant ecrit sur disque et n'imprime que des comptes.

Ce n'est donc PAS un manque de `pyghidra-mcp` (1.27.2), qui fait tres bien son travail et
accepte nativement le LOT : c'est le CANAL DE LIVRAISON vers l'agent qui est cher. La vraie
limite de l'outil, elle, est ailleurs et reste entiere : `decompile_function` n'a NI `offset`
NI `limit`, donc le cout est deja paye quand la sortie arrive.

TRI-ETAT. `disponible()` rend `None` si le serveur ne repond pas -- jamais un booleen
optimiste. Un appelant qui rabat une panne de serveur sur << rien a signaler >> fabrique
exactement le zero rassurant que le depot proscrit.

Le serveur ne demarre PAS tout seul :
    pwsh -File C:\\Users\\nicolasv\\ghidra-mcp\\start-ghidra-mcp.ps1

Sortie console ASCII stricte (cp1252).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

URL = "http://127.0.0.1:13337/mcp"

_ENTETES = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


class Mcp:
    """Session MCP. `ouvrir()` avant tout appel -- le serveur exige le handshake."""

    def __init__(self, url: str = URL, timeout: int = 300) -> None:
        self.url = url
        self.timeout = timeout
        self.session: str | None = None
        self._id = 0

    # ------------------------------------------------------------------ transport
    def _post(self, corps: dict) -> dict:
        e = dict(_ENTETES)
        if self.session:
            e["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(self.url, data=json.dumps(corps).encode("utf-8"),
                                     headers=e, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            sid = r.headers.get("Mcp-Session-Id")
            if sid:
                self.session = sid
            brut = r.read().decode("utf-8", "replace")
        return self._lire(brut)

    @staticmethod
    def _lire(brut: str) -> dict:
        """La reponse est soit du JSON nu, soit un flux SSE (lignes `data: {...}`)."""
        brut = brut.strip()
        if brut.startswith("{"):
            return json.loads(brut)
        for ligne in brut.splitlines():
            if ligne.startswith("data:"):
                charge = ligne[5:].strip()
                if charge:
                    return json.loads(charge)
        raise RuntimeError("reponse MCP illisible: " + brut[:200])

    def _appel(self, methode: str, params: dict | None = None) -> dict:
        self._id += 1
        return self._post({"jsonrpc": "2.0", "id": self._id,
                           "method": methode, "params": params or {}})

    # ------------------------------------------------------------------ api
    def ouvrir(self) -> dict:
        r = self._appel("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "tacticus-tools", "version": "1"},
        })
        try:                                   # notification, sans reponse attendue
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except Exception:                                            # noqa: BLE001
            pass
        return r

    def outils(self) -> list[str]:
        r = self._appel("tools/list")
        return [t["name"] for t in r.get("result", {}).get("tools", [])]

    def decompiler(self, binaire: str, noms, **kw) -> list[dict]:
        """`noms` accepte une LISTE : le lot est natif au serveur.

        Rend la liste de `structuredContent.result` -- un dict par cible, avec les cles
        `name`, `code`, `signature`, `callees`, `xrefs`, `referenced_strings`, `error`.
        ⚠ `callees` et `xrefs` ne sont peuples que si on les DEMANDE (`include_callees=True`,
        `include_xrefs=True`) ; sans ca ils arrivent VIDES, et les lire comme << aucun
        appelant >> est un faux negatif -- faute deja commise a la premiere mesure #594.
        """
        p = {"binary_name": binaire, "name_or_address": noms}
        p.update(kw)
        r = self._appel("tools/call", {"name": "decompile_function", "arguments": p})
        if "error" in r:
            raise RuntimeError(json.dumps(r["error"])[:300])
        return (r.get("result") or {}).get("structuredContent", {}).get("result", [])

    def binaires(self) -> dict:
        return self._appel("tools/call",
                           {"name": "list_project_binaries", "arguments": {}})


def disponible(url: str = URL) -> str | None:
    """Rend le nom+version du serveur, ou `None` si INJOIGNABLE. Jamais un booleen."""
    try:
        m = Mcp(url, timeout=8)
        o = m.ouvrir()
        srv = o.get("result", {}).get("serverInfo", {})
        return "%s %s" % (srv.get("name"), srv.get("version"))
    except Exception:                                                # noqa: BLE001
        return None


if __name__ == "__main__":
    v = disponible()
    if v is None:
        print("ghidra-mcp INJOIGNABLE sur %s -- PAS MESURE (le serveur ne demarre pas seul)"
              % URL)
        raise SystemExit(2)
    print("ghidra-mcp : %s" % v)
    m = Mcp()
    m.ouvrir()
    noms = sorted(m.outils())
    print("outils : %d" % len(noms))
    for n in noms:
        print("   " + n)
