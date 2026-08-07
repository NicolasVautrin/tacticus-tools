#!/usr/bin/env python
"""#287-r10 -- le capteur qui rend « CIBLE VALIDE » pour un REFUS : `InFogOfWarBrokenTargetingRule`.

CE QUE CE PROBE ETABLIT, et pourquoi il ne pouvait pas s'etablir offline.

`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (surcharge 7 arguments) commence
-- AVANT le moindre test de masque -- par balayer les tuiles de la cible et boxer une regle des que
l'une d'elles porte `TileComponent+0x40` (`IsInFogOfWar`) :

    foreach (tile in EntityExtensions.GetTiles(targetUnitOrTile, state))
        if (tile.<TileComponent>.IsInFogOfWar) return <box InFogOfWarBrokenTargetingRule>;

Le hook `frida/hooks/features/ai-step/rpc-targeting.ts` (`decodeRule`) ne sait extraire un flag que
d'un `GenericBrokenTargetingRule`, et sa table `NON_GENERIC_RULE_CODES` ne connait que
`NoBrokenTargetingRule` et `ObscuredTerrainBrokenTargetingRule`. Toute autre classe sort en
`hex: "0x0"` -- soit, pour un lecteur qui fait `int(payload["hex"], 16)`, **« cible valide »**.

⚠ POURQUOI LE RECENSEMENT DU HOOK ETAIT FAUX, ET LA FAUTE EST CELLE QUE `CLAUDE.md` NOMME :
`InFogOfWarBrokenTargetingRule$$get_Type` est ABSENTE des deux tables de symboles -- IL2CPP
DEDUPLIQUE les corps triviaux, et son `return 1` est publie sous le nom
`AK.Wwise.AuxBus$$get_WwiseObjectType`. « Le symbole n'existe pas » a donc ete lu comme « la classe
n'a pas de get_Type ». Les quatre `ToString` du groupe boxent EXACTEMENT le `Type` de leur classe
(`NoBrokenTargetingRule` -> 0, `GenericBrokenTargetingRule` -> le champ, `ObscuredTerrain...` ->
0x1000000 -- valeur CONFIRMEE par son `get_Type` NOMME) ; celui d'`InFogOfWar...` boxe **1**.

CE QUE MESURE CE PROBE, sur un board a SALLES (les 15 `C6_*` du catalogue, seuls a porter plusieurs
`RoomID` et des `Doors`) :

    etage 1  `boardGraph` publie-t-il des tuiles `isInFog` ? (sinon le regime est INATTEIGNABLE ici)
    etage 2  `abilityReason` sur une de ces tuiles : quelle `ruleClass`, quel `hex` ?
    etage 3  le CONTRASTE : la meme ability, une tuile HORS brouillard -> `NoBrokenTargetingRule`.

Un etage 1 vide est un RESULTAT, pas un echec : il dit que le mensonge du capteur n'est pas
atteignable par nos runners, ce qui BORNE la dette au lieu de la nier.

Usage (session warmee ; le probe monte et DISPOSE son propre runner) :
    python scripts/python/probe_287r10_fog_capteur_live.py
    python scripts/python/probe_287r10_fog_capteur_live.py --board C6_04 --seed 31337
ASCII only ; exit 0 = la mesure a abouti (que le brouillard soit atteint ou non).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import oracle_targeting as O                                             # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402

ROOT = HERE.parents[1]

#: Les boards a SALLES du catalogue, derives OFFLINE (plusieurs `RoomID` distincts + des `Doors`).
#: Ce sont les seuls candidats au brouillard : ailleurs tout le plateau est une seule piece.
BOARDS_A_SALLES = ("C6_09", "C6_18", "C6_24", "C6_04", "C6_06", "C6_08", "C6_12", "C6_02")


def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _build(seed, board, p_units, a_units):
    state = ROOT / "logs" / ("_probe287r10fog-%d.json" % os.getpid())
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", p_units, "--a-units", a_units]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(HERE), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"]), state
        out = (p.stderr or p.stdout or "")
        if ("runner cap reached" not in out and "runner creation paused" not in out) \
                or time.time() >= deadline:
            return None, out[-400:]
        time.sleep(10)


def _mesure(sid, rid, board):
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 120) or {}
    tiles = bg.get("tiles") or []
    if not tiles:
        print("[%s] PAS MESURE : boardGraph vide" % board)
        return None
    fog = [t for t in tiles if t.get("isInFog")]
    clair = [t for t in tiles if not t.get("isInFog") and t.get("walkable")]
    print("[%s] tuiles=%d  isInFog=%d  claires marchables=%d"
          % (board, len(tiles), len(fog), len(clair)))
    if not fog:
        return {"board": board, "n_tiles": len(tiles), "n_fog": 0}

    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 120) or {}
    caster = ab = None
    for u in (dv.get("units") or []):
        for a in (u.get("abilities") or []):
            if a.get("usable") and not (a.get("cooldown") or 0):
                caster, ab = u, a
                break
        if caster is not None:
            break
    if caster is None:
        print("[%s] PAS MESURE : aucune ability disponible sur ce montage" % board)
        return {"board": board, "n_tiles": len(tiles), "n_fog": len(fog), "sans_caster": True}

    def lire(tid):
        r = _r(sid, "abilityReason", {"runnerId": rid, "casterId": int(caster["id"]),
                                      "abilityType": int(ab["id"]), "targetId": int(tid)}, 60) or {}
        # LE CRAN (#287-r6) : si `AttackQuery` court-circuite en amont, `targetReason` vaut `1` pour
        # TOUTE cible et ne dit rien du ciblage -- la mesure du brouillard ne voudrait plus rien.
        if O.oracle_court_circuite(r):
            print("[%s] !! ORACLE COURT-CIRCUITE (%s) -- cette lecture ne dit RIEN du ciblage"
                  % (board, O.cause_du_court_circuit(r)))
        return (r.get("targetReason") or {}), (r.get("casterReason") or {})

    tr_fog, cr = lire(fog[0]["id"])
    print("[%s] caster u%s ability %s ; casterReason=%s"
          % (board, caster["id"], ab.get("id"), cr.get("hex")))
    print("[%s] TUILE EN BROUILLARD  t%s -> ruleClass=%r hex=%r reasons=%s"
          % (board, fog[0]["id"], tr_fog.get("ruleClass"), tr_fog.get("hex"),
             tr_fog.get("reasons")))
    tr_clair = {}
    if clair:
        tr_clair, _ = lire(clair[0]["id"])
        print("[%s] TUILE CLAIRE         t%s -> ruleClass=%r hex=%r"
              % (board, clair[0]["id"], tr_clair.get("ruleClass"), tr_clair.get("hex")))
    return {"board": board, "n_tiles": len(tiles), "n_fog": len(fog),
            "caster": caster["id"], "ability": ab.get("id"),
            "caster_reason": cr.get("hex"),
            "fog": {"tile": fog[0]["id"], "ruleClass": tr_fog.get("ruleClass"),
                    "hex": tr_fog.get("hex")},
            "clair": {"ruleClass": tr_clair.get("ruleClass"), "hex": tr_clair.get("hex")}}


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r10 : le capteur de la ligne de vue en brouillard")
    ap.add_argument("--board", default=None, help="un seul board (defaut : balaye BOARDS_A_SALLES)")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--p-units", default="orksWarboss,orksNob")
    ap.add_argument("--a-units", default="necroWarden,necroWarden")
    ap.add_argument("--max-boards", type=int, default=3)
    a = ap.parse_args()

    sid = _resolve_session()
    if not sid:
        print("[287r10] PAS MESURE : pas de session Frida")
        return 2
    boards = [a.board] if a.board else list(BOARDS_A_SALLES)[:max(1, a.max_boards)]
    res = []
    for b in boards:
        rid, err = _build(a.seed, b, a.p_units, a.a_units)
        if rid is None:
            print("[%s] build KO : %s" % (b, err))
            continue
        try:
            r = _mesure(sid, rid, b)
            if r:
                res.append(r)
        finally:
            try:
                _r(sid, "disposeRunner", {"runnerId": rid}, 60)
            except Exception:                                            # noqa: BLE001
                pass
        if res and res[-1].get("n_fog"):
            break

    print("\n=== VERDICT ==========================================================")
    if not res:
        print("  PAS MESURE : aucun board n'a rendu de boardGraph exploitable")
        return 1
    atteints = [r for r in res if r.get("n_fog")]
    if not atteints:
        print("  BROUILLARD NON ATTEINT sur %d board(s) a salles : %s"
              % (len(res), {r["board"]: r["n_fog"] for r in res}))
        print("  -> le mensonge du capteur (`hex: \"0x0\"` pour un refus) EXISTE au decompile mais "
              "n'est pas atteignable par ce montage. C'est une BORNE, pas une refutation.")
    else:
        r = atteints[0]
        ment = (r["fog"]["ruleClass"] == "InFogOfWarBrokenTargetingRule"
                and int(str(r["fog"]["hex"] or "0x0"), 16) == 0)
        print("  BROUILLARD ATTEINT sur %s : %d tuiles" % (r["board"], r["n_fog"]))
        print("  capteur MENT (`%s` publie hex=%s) : %s"
              % (r["fog"]["ruleClass"], r["fog"]["hex"], "OUI" if ment else "non"))
    print("[RAW] " + json.dumps(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
