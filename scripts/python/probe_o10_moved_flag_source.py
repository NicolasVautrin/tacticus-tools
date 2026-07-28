#!/usr/bin/env python
"""Y a-t-il, dans ce que les RPC projettent DEJA, de quoi reconstruire `UnitFlag.Moved` ?

CONTEXTE. `engine/runner/components.py::unit_has_moved` est le LECTEUR UNIQUE du fait « a bouge ce
tour » (mirror `HasFlag(unit, UnitFlag.Moved=0)`), et sa docstring dit : « etat charge par
`load_state` : le RPC n'expose pas les UnitFlags ». Consequence MESUREE (case-o10 SS 6,
`probe_o10_volk_stage_split.py`) : dans un replay-diff monte depuis un snapshot LIVE, une unite qui
a BOUGE est vue « n'a pas bouge » par le port -> le gate no-move de
`IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier` ne mord jamais
et le bonus est TOUJOURS accorde.

Ce probe ne suppose rien : il DIFFE le JSON brut des trois sources de `load_state`
(`decisionView`, `observeBattle`, `combatSnapshot`) pour l'unite AVANT et APRES un `applyAction
move` reel, et imprime tout champ qui a change. Un champ qui bascule est une source candidate ;
aucun champ = il faut un capteur natif (nomme dans le rapport, pas bricole en proxy).

Usage : python probe_o10_moved_flag_source.py
ASCII only (cp1252).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc            # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_o10_movedflag_state.json"
CARRIER = "blackObliterator"


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _flat(o, pfx=""):
    """Aplatit un dict/list en {chemin: valeur scalaire} pour un diff lisible."""
    out = {}
    if isinstance(o, dict):
        for k, v in o.items():
            out.update(_flat(v, "%s.%s" % (pfx, k) if pfx else str(k)))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            out.update(_flat(v, "%s[%d]" % (pfx, i)))
    else:
        out[pfx] = o
    return out


def main():
    sid = _resolve_session()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.unlink(missing_ok=True)
    subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777", "--state-file", str(STATE),
         "--board", "MC1_67", "--roster", "2", "--p-units", "blackObliterator,adeptHospitaller",
         "--a-units", "necroWarden,necroWarden"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[movedflag] build KO"); return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    rpc = lambda m, b, t=90: _r(sid, m, b, t)          # noqa: E731
    print("[movedflag] runner=%s" % rid)
    try:
        def snap():
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            ob = rpc("observeBattle", {"runnerId": rid}, 60)
            cs = rpc("combatSnapshot", {"runnerId": rid}, 90)
            me = next((u for u in (dv.get("units") or [])
                       if u.get("visualId") == CARRIER), {})
            uid = me.get("id")
            ob_u = next((u for u in (ob.get("units") or [])
                         if u.get("squadId") == uid or u.get("id") == uid), {})
            cs_u = next((u for u in (cs.get("units") or [])
                         if u.get("squadId") == uid or u.get("id") == uid
                         or u.get("entityId") == uid or u.get("unitId") == uid), {})
            if not cs_u and (cs.get("units") or []):
                print("[movedflag] cles d'une ligne combatSnapshot = %s"
                      % sorted((cs["units"][0] or {}).keys()))
            print("[movedflag] combatSnapshot.unitFlagTypes = %s" % (cs.get("unitFlagTypes"),))
            return uid, {"dv": _flat(me), "ob": _flat(ob_u), "cs": _flat(cs_u),
                         "dv_top": {k: v for k, v in _flat(
                             {k2: v2 for k2, v2 in dv.items() if k2 != "units"}).items()}}

        uid, before = snap()
        print("[movedflag] unite Volk = u%s" % uid)
        # cle 'moved'-ish deja presente ?
        for src in ("dv", "ob", "cs"):
            hits = [k for k in before[src] if "mov" in k.lower() or "flag" in k.lower()
                    or "activ" in k.lower()]
            print("[movedflag] %s : champs 'mov|flag|activ' = %s" % (src, hits))

        pos = next((v for k, v in before["dv"].items() if k == "pos.col"), None)
        row = next((v for k, v in before["dv"].items() if k == "pos.row"), None)
        print("[movedflag] pos avant = (%s,%s)" % (pos, row))
        def _movable():
            mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60) or {}
            cu = next((x for x in (mt.get("units") or []) if x.get("unitId") == uid), None)
            return (cu or {}).get("tiles") or []

        tiles = _movable()
        print("[movedflag] aiMovableTiles avant : n=%d" % len(tiles))

        # MOVE REEL
        dest = None
        for t in tiles:
            if (t.get("col"), t.get("row")) != (pos, row):
                dest = (t.get("col"), t.get("row")); break
        if dest is None:
            print("[movedflag] aucune tuile de destination -> stop"); return 3
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": dest[0], "row": dest[1]}}}, 60)
        print("[movedflag] move -> %s : ok=%s" % (dest, (r or {}).get("ok")))

        _uid2, after = snap()
        print("[movedflag] aiMovableTiles apres : n=%d" % len(_movable()))

        for src in ("dv", "ob", "cs", "dv_top"):
            b, a = before[src], after[src]
            keys = sorted(set(b) | set(a))
            diffs = [(k, b.get(k, "<absent>"), a.get(k, "<absent>"))
                     for k in keys if b.get(k, "<absent>") != a.get(k, "<absent>")]
            print("\n[movedflag] === %s : %d champ(s) modifie(s) ===" % (src, len(diffs)))
            for k, x, y in diffs[:40]:
                print("[movedflag]    %-42s %r -> %r" % (k, x, y))
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print("\n[movedflag] runner %s dispose" % rid)
        except Exception as e:
            print("[movedflag] dispose KO: %s" % e)


if __name__ == "__main__":
    sys.exit(main())
