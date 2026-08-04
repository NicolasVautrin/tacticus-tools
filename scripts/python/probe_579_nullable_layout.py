"""#579-r1 -- le capteur `IsAlreadyUsedThisTurn` publiait le bit `hasValue` a la place du TOUR.

CE QUE CE PROBE TRANCHE, et pourquoi il fallait DEUX casts
----------------------------------------------------------

`frida/hooks/features/ai-step/internals.ts::readAbilityState` publie
`unresetedLastTurnUsed` / `lastTurnUsed` : les deux `Nullable<int>` de
`IdunBattle.Entities.Components.ActiveAbility` (`@+0x20` et `@+0x18`) que lit la marche (f) de
`IdunBattle.Core.Services.AttackQuery$$GetInvalidCasterReason`.

Le foyer les lisait a la disposition `{ int value @+0 ; bool hasValue @+4 }`. C'est FAUX :
`System.Nullable`1` declare `hasValue` PUIS `value`, donc `{ bool hasValue @+0 (+3 de bourrage) ;
T value @+4 }`.

UN SEUL cast ne pouvait pas le voir. Sous la disposition fausse, ce qui sort en `value` est le bit
`hasValue`, c'est-a-dire TOUJOURS `1` -- et `1` est un tour parfaitement plausible. Le discriminant
est donc de caster DEUX fois dans la MEME bataille, a DEUX valeurs distinctes du compteur
`IdunBattle.Entities.Components.TurnComponent$$GetAmountOfTurnsEnded` :

  * `IdunBattle.Operations.SetActiveAbilityUsedOperation$$Execute` et
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` ecrivent TOUS DEUX
    `Nullable(GetAmountOfTurnsEnded(GetMatchTurn(state), 0))` dans `LastTurnUsed@+0x18` ET
    `UnresetedLastTurnUsed@+0x20` -- lu verbatim, les deux corps, sur `rnca9r7q6c` ;
  * `GetAmountOfTurnsEnded(this, turnsToAdd)` = `Sum(this.<Dictionary @+0x40>.Values) + turnsToAdd`,
    donc MONOTONE : deux casts separes par au moins un tour termine ne peuvent PAS avoir stocke la
    meme valeur.

=> si le capteur publie la MEME valeur aux deux casts, cette valeur n'est pas le tour.

MESURE DU 2026-08-04 (session 3, build `rnca9r7q6c`, capteur d'origine) :

  | cast | unite            | ability | `turnsEnded` au cast | `unresetedLastTurnUsed` publie |
  |------|------------------|---------|----------------------|--------------------------------|
  | 1    | `tauMarksman`    | 1069    | **6**                | **1**                          |
  | 2    | `templAggressor` | 1048    | **19**               | **1**                          |

CE QUE LE PROBE REND (`rc`)
---------------------------

  * `0` -- les DEUX casts publient `value == turnsEnded` du moment du cast : le capteur est FIDELE.
  * `1` -- au moins un ecart, OU les deux casts publient la meme valeur a deux compteurs
    differents (la signature exacte de la disposition inversee).
  * `2` -- montage non installe (pas deux casts) : rien n'est tranche, et ce n'est PAS un vert.

ANTI-DEGENERESCENCE, explicite : le probe REFUSE de conclure si les deux casts tombent au meme
`turnsEnded` (les deux modeles y coincident), et si le compteur vaut `0` au cast (0 == 0 des deux
cotes, et sous la disposition fausse `hasValue` sortirait meme a `false`).

⚠ Le compteur est publie par `decisionView.turnsEnded` (#466). Il n'est PAS `decisionView.turn` :
mesure du 2026-08-04 -- `turn` vaut 3 puis 4 puis 3 pendant que `turnsEnded` va 0,3,4,6,...,
c'est-a-dire que `turn` suit `currentPlayer` (`projectMatch` pose `turn: status.currentTurnPlayer`,
= `TurnComponent._currentPlayerId`), et non un compteur de tours.

Usage :
    python scripts/python/probe_579_nullable_layout.py --state-file <ABSOLU>.json

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import hexgeo                                             # noqa: E402
import probe_419r1tr14_heavy_bolt_pistol as P14           # noqa: E402

MontageError = P14.MontageError

BOARD = "MC1_67"
SEED = "777"
P_UNITS = ("tauMarksman", "necroWarden")
A_UNITS = ("templAggressor", "eldarRanger")

#: (visualId, abilityId) -- le PREMIER cast est le mien, le SECOND celui d'en face. Piloter les
#: DEUX camps est legitime : `applyAction` ne verifie pas la propriete du `casterId`, et c'est ce
#: qui donne deux casters distincts sans monter un second runner.
CAST1 = ("tauMarksman", 1069)
CAST2 = ("templAggressor", 1048)

#: Tours brules entre les deux casts -- ils font DIVERGER le compteur, ce qui est tout le probe.
BURN_ENDTURNS = 8


def _dv(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 4}, 300)


def _ability_of(dv, vis, ab):
    for u in (dv.get("units") or ()):
        if u.get("visualId") != vis:
            continue
        for a in (u.get("abilities") or ()):
            if a.get("id") == ab:
                return u.get("id"), a
    return None, None


def _from_here(rpc, rid, caster_id, ab):
    t = rpc("abilityTargets", {"runnerId": rid, "casterId": caster_id}, 120)
    for u in (t.get("units") or ()):
        if u.get("unitId") != caster_id:
            continue
        for a in (u.get("abilities") or ()):
            if a.get("abilityId") == ab:
                return a.get("fromHere") or []
    return []


def _act(state_file, rid, tail):
    argv = [sys.executable, "rl_duel.py", "act", *tail,
            "--state-file", state_file, "--runner", str(rid)]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode


def _approach(rpc, state_file, rid, vis, ab, max_steps, verbose):
    """Drive les positions des DEUX camps jusqu'a ce que `vis` puisse caster `ab` SANS bouger.

    Le seul but est la GEOMETRIE : la ou l'unite se trouve ne change rien a ce qui est mesure.
    Ancre par visualId (pas par le flag `ctrl`, qui bascule avec le joueur courant)."""
    for step in range(max_steps):
        dv = _dv(rpc, rid)
        pos = {u.get("visualId"): ((u.get("pos") or {}).get("col"),
                                   (u.get("pos") or {}).get("row"))
               for u in (dv.get("units") or ())}
        cid, st = _ability_of(dv, vis, ab)
        if cid is None:
            return None
        fh = _from_here(rpc, rid, cid, ab)
        if verbose:
            print("     approche step=%d turnsEnded=%s player=%s usable=%s cibles=%d"
                  % (step, dv.get("turnsEnded"), dv.get("currentPlayer"),
                     st.get("usable"), len(fh)))
        if fh and st.get("usable"):
            return cid, fh, dv
        if pos.get(CAST1[0]) is None or pos.get(CAST2[0]) is None:
            return None
        anchor = pos[CAST2[0]] if dv.get("currentPlayer") == 3 else pos[CAST1[0]]
        mv = rpc("aiMovableTiles", {"runnerId": rid}, 90)
        for mu in (mv.get("units") or ()):
            tiles = [t for t in (mu.get("tiles") or ()) if t.get("col") is not None]
            if not tiles:
                continue
            best = min(tiles, key=lambda t: hexgeo.distance((t["col"], t["row"]), anchor))
            _act(state_file, rid, ["move", "--unit", str(mu.get("unitId")),
                                   "--to", "%d,%d" % (best["col"], best["row"])])
        _act(state_file, rid, ["endturn"])
    return None


def _cast_and_read(rpc, state_file, rid, vis, ab, hit):
    cid, fh, dv = hit
    before = dv.get("turnsEnded")
    tid = fh[0].get("targetId") if isinstance(fh[0], dict) else fh[0]
    _act(state_file, rid, ["ability", "--caster", str(cid), "--target", str(tid),
                           "--ability", str(ab)])
    dv2 = _dv(rpc, rid)
    _, st = _ability_of(dv2, vis, ab)
    st = st or {}
    return {
        "unit": vis, "ability": ab, "casterId": cid, "targetId": tid,
        "turnsEnded_at_cast": before, "turnsEnded_after": dv2.get("turnsEnded"),
        "turn": dv2.get("turn"), "currentPlayer": dv2.get("currentPlayer"),
        "unresetedLastTurnUsed": st.get("unresetedLastTurnUsed"),
        "unresetedLastTurnUsedHasValue": st.get("unresetedLastTurnUsedHasValue"),
        "lastTurnUsed": st.get("lastTurnUsed"),
        "lastTurnUsedHasValue": st.get("lastTurnUsedHasValue"),
        "usable": st.get("usable"), "cooldown": st.get("cooldown"),
        "abilityStateLayout": dv2.get("abilityStateLayout"),
    }


def run(rpc, build, state_file, verbose: bool = True) -> dict:
    """UN runner, DEUX casts a DEUX compteurs. Rend `{casts, verdict, ...}`."""
    rid = build(SEED, ["--board", BOARD, "--p-units", ",".join(P_UNITS),
                       "--a-units", ",".join(A_UNITS)])
    casts = []
    if verbose:
        print("   cast 1 : %s / %d" % CAST1)
    hit = _approach(rpc, state_file, rid, CAST1[0], CAST1[1], 10, verbose)
    if hit is None:
        raise MontageError("montage NON INSTALLE : %s n'a jamais pu caster %d" % CAST1)
    casts.append(_cast_and_read(rpc, state_file, rid, CAST1[0], CAST1[1], hit))
    for _ in range(BURN_ENDTURNS):
        _act(state_file, rid, ["endturn"])
    if verbose:
        print("   cast 2 : %s / %d (apres %d endturns)" % (CAST2[0], CAST2[1], BURN_ENDTURNS))
    hit2 = _approach(rpc, state_file, rid, CAST2[0], CAST2[1], 8, verbose)
    if hit2 is None:
        raise MontageError("montage NON INSTALLE : %s n'a jamais pu caster %d" % CAST2)
    casts.append(_cast_and_read(rpc, state_file, rid, CAST2[0], CAST2[1], hit2))

    counters = [c["turnsEnded_at_cast"] for c in casts]
    values = [c["unresetedLastTurnUsed"] for c in casts]
    out = {"rid": rid, "casts": casts, "counters": counters, "values": values}
    if any(c is None for c in counters):
        out["verdict"] = "NON MESURE (turnsEnded absent)"
    elif len(set(counters)) < 2:
        out["verdict"] = ("REGIME DEGENERE : les deux casts sont au meme compteur (%s) -- "
                          "les deux dispositions y coincident, rien n'est tranche" % counters)
    elif 0 in counters:
        out["verdict"] = ("REGIME DEGENERE : un cast a compteur ZERO -- 0 == 0 des deux cotes")
    elif values == counters:
        out["verdict"] = "FIDELE : value == turnsEnded aux deux casts"
    elif len(set(v for v in values if v is not None)) == 1:
        out["verdict"] = ("INFIDELE : meme valeur publiee (%s) a deux compteurs differents (%s) "
                          "-- le champ publie n'est pas le tour" % (values, counters))
    else:
        out["verdict"] = "INFIDELE : %s publie contre %s attendu" % (values, counters)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU (prefixe des state-files)")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=120):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    logs = os.path.dirname(os.path.abspath(args.state_file))
    os.makedirs(logs, exist_ok=True)
    stem = os.path.splitext(os.path.basename(args.state_file))[0]
    seq, rids = {"n": 0}, []
    sf_holder = {"path": args.state_file}

    def build(seed, extra):
        seq["n"] += 1
        sf = os.path.join(logs, "%s_%d.json" % (stem, seq["n"]))
        sf_holder["path"] = sf
        rid = P14._build(sf, ["--seed", str(seed), *extra])
        rids.append(rid)
        return rid

    print("session", sid)
    rc = 0
    try:
        print("== #579-r1 : la disposition du Nullable<int>, tranchee par DEUX casts ==")
        try:
            out = run(rpc, build, sf_holder["path"])
        except MontageError as e:
            print("   MONTAGE : %s" % e)
            return 2
        for c in out["casts"]:
            print("   [%-16s ab%-5d] turnsEnded=%-3s -> unreseted=%s/%s last=%s/%s"
                  % (c["unit"], c["ability"], c["turnsEnded_at_cast"],
                     c["unresetedLastTurnUsed"], c["unresetedLastTurnUsedHasValue"],
                     c["lastTurnUsed"], c["lastTurnUsedHasValue"]))
        print("   -> %s" % out["verdict"])
        rc = 0 if out["verdict"].startswith("FIDELE") else (
            2 if out["verdict"].startswith(("REGIME", "NON MESURE")) else 1)
    finally:
        for rid in rids:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 60)
            except Exception:
                pass
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
