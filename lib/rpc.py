"""RPC client — call Frida IDE backend endpoints, return parsed GameState."""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any

from .state import GameState


class RpcClient:
    """Synchronous client for the Frida IDE backend RPC endpoints."""

    def __init__(self, base_url: str = "http://127.0.0.1:8765", session_id: int | None = None):
        self.base_url = base_url.rstrip("/")
        self.session_id = session_id

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _post(self, path: str, data: dict | None = None, timeout: float = 15.0) -> Any:
        body = json.dumps(data or {}).encode()
        req = urllib.request.Request(
            self._url(path),
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())

    def _rpc(self, method: str, args: dict | None = None, timeout: float = 15.0) -> Any:
        if self.session_id is None:
            raise ValueError("session_id required for RPC calls")
        result = self._post(
            f"/api/scripts/{self.session_id}/rpc",
            {"method": method, "args": args or {}, "timeout": timeout},
            timeout=timeout + 2,
        )
        return result.get("result", result)

    # -- State --

    def get_state(self, depth: int = 6) -> GameState:
        raw = self._rpc("get_state", {"depth": depth})
        return GameState(raw)

    def get_raw_state(self, depth: int = 6) -> dict:
        return self._rpc("get_state", {"depth": depth})

    # -- Actions --

    def play(self, action: str, **kwargs) -> GameState:
        """Execute an action and wait for player turn. Returns new state + events."""
        args = {"action": action, **kwargs}
        raw = self._rpc("play", args, timeout=30.0)
        return GameState(raw)

    def move(self, unit_id: int, col: int, row: int) -> GameState:
        return self.play("move", unitId=unit_id, positions=[{"col": col, "row": row}])

    def attack(self, caster_id: int, target_id: int, ability_type: int) -> GameState:
        """Attack a target. ability_type is required — use unit.normal_attack_type."""
        return self.play("ability", casterId=caster_id, targetId=target_id, abilityType=ability_type)

    def end_turn(self) -> GameState:
        return self.play("end_turn")

    # -- Queries --

    def get_reachable_tiles(self, unit_id: int) -> list[int]:
        result = self._rpc("get_reachable_tiles", {"unitId": unit_id})
        return result.get("tileIds", [])

    def get_abilities_info(self) -> dict:
        """Get localization data for all abilities in the match.

        Returns dict keyed by unit entity ID (str), each with:
          active: {abilityType: {paramName: value, ...}}
          triggered: {configId: {paramName: value, ...}}
        Also includes "effect_N" keys for effect localization data.
        """
        return self._rpc("get_abilities_info")

    # -- Session management --

    def find_session(self) -> int | None:
        """Find the latest running script session."""
        # The backend doesn't have a list endpoint yet, so we probe recent IDs
        for sid in range(200, 0, -1):
            try:
                resp = self._post(f"/api/scripts/{sid}/rpc",
                                  {"method": "get_state", "args": {"depth": 1}, "timeout": 3},
                                  timeout=5)
                if "result" in resp:
                    self.session_id = sid
                    return sid
            except urllib.error.HTTPError:
                continue
            except Exception:
                continue
        return None