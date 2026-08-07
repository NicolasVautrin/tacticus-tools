"""#287-r11-r1-r1-r2 -- le PREFIXE `IsTurnOfUnit` de `CasterHasNotMoved`, face RUNNER.

CE QUE CE PROBE MESURE
----------------------
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` garde sa clause 1 par
`<IBattleQuery slot 0x35>(this.<+0x18>, caster)` = `IdunBattle.Core.Services.BattleQuery$$IsTurnOfUnit`
(slot 53, arite 1, `data/symbols/<build>/metadata/interface_slots.tsv`). Quand ce n'est PAS le tour
du proprietaire d'ORIGINE, la regle `CasterHasNotMoved` est ENTIEREMENT sautee -- flag
`UnitFlag.Moved` compris. Le port RUNNER ne le portait pas : il rendait `CasterHasNotMoved` la ou
le natif rend `0` (ecart RESTRICTIF).

L'ORACLE est le RPC `abilityReason`, dont le champ `casterReason` est
`AttackQuery$$GetInvalidCasterReason(caster, casterTile, abilityType)` -- il ne prend AUCUNE cible,
donc il isole le volet CASTER (lu dans `frida/hooks/features/ai-step/rpc-targeting.ts`).

LE REGIME QUI FAIT MORDRE LE PREFIXE, et pourquoi il est atteignable
--------------------------------------------------------------------
`UnitFlag.Moved` SURVIT a la fin du tour : `RemoveTurnFlags(new_activation=1)` est joue par le
`StartTurnOperation` du JOUEUR ENTRANT, pas globalement. Une unite qui bouge puis passe la main
porte donc encore le flag pendant tout le tour adverse -- et pendant ce tour, `IsTurnOfUnit(elle)`
est FAUX. Les deux termes de la clause sont alors en opposition, ce qui est exactement le
discriminant.

TROIS BRAS, et le probe REFUSE de conclure si la ventilation est degeneree
--------------------------------------------------------------------------
  * `avant-move`  -- tour de Lucien, il n'a PAS bouge      -> natif 0, port 0 des deux cotes
  * `en-tour`     -- tour de Lucien, il A bouge            -> natif `CasterHasNotMoved`, port idem
                     (le prefixe est VRAI : la clause s'evalue, rien ne change)
  * `hors-tour`   -- MEME unite, tour ADVERSE, flag encore pose
                     -> natif `0`, port AVANT `CasterHasNotMoved`, port APRES `0`

Le bras `hors-tour` n'a de valeur que si le port voit REELLEMENT « a bouge » : le probe imprime
`unit_has_moved` et `is_turn_of_unit` a chaque bras (decomposition par etage), et rend `rc != 0` si
le substrat s'est evapore (auquel cas l'accord serait un accord de regime DEGENERE).

Les deux ports sont obtenus sur le MEME etat fige : `apres` = le code du commit, `avant` = le meme
code avec `targeting.is_turn_of_unit` substituee par `lambda: True` -- c'est-a-dire la clause
TOUJOURS evaluee, l'etat de `master` avant cette tranche. La substitution porte sur l'attribut du
module CONSOMMATEUR (`engine.runner.abilities.targeting`), la seule forme qui morde une liaison
`from X import foo`.

    python probe_287r11r1r1r2_is_turn_of_unit.py [--board MC1_67] [--seed 777] [--json]
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.abilities import targeting as T                   # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.components import unit_has_moved                  # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

#: `1163 BlackRage`, masque `0x106004012` -> porte `CasterHasNotMoved` (0x10). Porteur `bloodDeathCompany`
#: (`Lucien`, HERO du pool). MEME couple que `probe_210_blackrage_targeting.py`, qui a etabli que le
#: flag `Moved` arrive dans l'etat charge SANS pose manuelle.
BLACK_RAGE = 1163
LUCIEN = "bloodDeathCompany"
ALLY = "bloodIntercessor"
A_UNITS = "necroWarden,necroWarden,necroWarden"
BOARD = "MC1_67"
SEED = "777"
WARMUP_ENDTURNS = 6                # purge les `initialCooldownTurns` (sinon `ValidRequest` partout)

#: `TargetingRule.ValidRequest` -- le code que `AttackQuery$$GetInvalidCasterReason` rend AVANT la
#: cascade quand un etage AMONT mord (ability indisponible, cooldown, munitions). Un bras qui le
#: recoit ne dit RIEN de la regle : il est ECARTE, et compte comme tel.
VALID_REQUEST = int(TR.ValidRequest)

_seq = itertools.count()


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _build(sid, seed: str, board: str) -> int:
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe287r11r1r1r2-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", "%s,%s" % (LUCIEN, ALLY), "--a-units", A_UNITS]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"])
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-400:])
        time.sleep(10)


def _dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)


def _act(sid, rid, action, timeout=90):
    return _r(sid, "applyAction", {"runnerId": rid, "action": action}, timeout)


def _pos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])
                    if t.get("col") is not None]
    return []


def _my_turn(sid, rid, maxit=8):
    """Rend la main au joueur qui possede mes heros (chaine de `endturn`, runner `--no-ai`)."""
    for _ in range(maxit):
        d = _dv(sid, rid)
        mine = next((u for u in (d.get("units") or []) if u.get("ctrl")), None)
        if mine is not None and d.get("currentPlayer") == mine.get("owner"):
            return d
        _act(sid, rid, {"kind": "endturn"}, 60)
    return _dv(sid, rid)


def _caster_reason(sid, rid, caster_id) -> int:
    """`casterReason` du RPC `abilityReason` = `AttackQuery$$GetInvalidCasterReason(caster,
    casterTile, abilityType)`. AUCUN `targetId` n'est passe : le volet CASTER n'en lit pas."""
    r = _r(sid, "abilityReason", {"runnerId": rid, "casterId": caster_id,
                                  "abilityType": BLACK_RAGE}, 90) or {}
    cr = r.get("casterReason") or {}
    return int(cr.get("hex") or "0x0", 16)


# --------------------------------------------------------------------------- les deux ports

def _port(state, caster_id, *, prefixe_porte: bool) -> int:
    """`get_invalid_caster_reason` sur l'etat fige, dans les DEUX versions.

    `prefixe_porte=False` = l'etat de `master` AVANT cette tranche : la clause `CasterHasNotMoved`
    etait evaluee inconditionnellement. On l'obtient en substituant l'attribut
    `engine.runner.abilities.targeting.is_turn_of_unit` -- le module CONSOMMATEUR, seule forme qui
    morde une liaison `from ..components import is_turn_of_unit`."""
    ability = ABILITY_CLASSES[BLACK_RAGE]()
    if prefixe_porte:
        return int(T.get_invalid_caster_reason(state, int(caster_id), ability) or 0)
    origine = T.is_turn_of_unit
    T.is_turn_of_unit = lambda *a, **k: True
    try:
        return int(T.get_invalid_caster_reason(state, int(caster_id), ability) or 0)
    finally:
        T.is_turn_of_unit = origine


# --------------------------------------------------------------------------- montage

def _capture(sid, rid, board):
    dec = _dv(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
    return dec, load_state(dec, ob, snap, board=board)


def _row(sid, rid, state, dec, caster_id, label) -> dict:
    """UNE mesure : oracle natif, port APRES, port AVANT, PLUS le substrat des deux etages."""
    natif = _caster_reason(sid, rid, caster_id)
    apres = _port(state, caster_id, prefixe_porte=True)
    avant = _port(state, caster_id, prefixe_porte=False)
    itou = T.is_turn_of_unit(state, int(caster_id))
    return {
        "bras": label,
        "natif": natif,
        "apres": apres,
        "avant": avant,
        "is_turn_of_unit": itou,
        "has_moved": bool(unit_has_moved(state, int(caster_id))),
        "currentPlayer": dec.get("currentPlayer"),
        "ecarte": natif == VALID_REQUEST,
        "accord_apres": apres == natif,
        "accord_avant": avant == natif,
    }


def run(seed: str = SEED, board_id: str = BOARD, sid=None, rid=None, keep: bool = False) -> dict:
    sid = sid or _resolve_session()
    own = rid is None
    rid = rid if rid is not None else _build(sid, seed, board_id)
    rows: list[dict] = []
    try:
        for _ in range(WARMUP_ENDTURNS):
            _act(sid, rid, {"kind": "endturn"}, 60)
        _my_turn(sid, rid)

        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            raise RuntimeError("boardGraph indisponible")
        board = Board(bg["tiles"], adjacency="native_sym")

        dec = _dv(sid, rid)
        luc = next((u for u in (dec.get("units") or [])
                    if u.get("visualId") == LUCIEN and u.get("alive")), None)
        if luc is None:
            raise RuntimeError("Lucien absent du roster monte")
        luc_id = int(luc["id"])

        # ---- bras 1 : AVANT le move -- temoin a verdict NUL des deux cotes ------------------
        dec, state = _capture(sid, rid, board)
        rows.append(_row(sid, rid, state, dec, luc_id, "avant-move (tour de Lucien)"))

        # ---- bras 2 : EN-TOUR, apres le move -- la clause MORD, prefixe VRAI ----------------
        tiles = _movable(sid, rid, luc_id)
        if not tiles:
            raise RuntimeError("aucune tuile de deplacement pour Lucien")
        dec0 = _dv(sid, rid)
        luc0 = next((u for u in (dec0.get("units") or []) if u.get("id") == luc_id), None)
        cible = min(tiles, key=lambda t: (hexgeo.distance(t, _pos(luc0)) != 1, t))
        res = _act(sid, rid, {"kind": "move", "unitId": luc_id,
                              "to": {"col": cible[0], "row": cible[1]}}, 90)
        if not bool(((res or {}).get("actions") or [{}])[0].get("ok")):
            raise RuntimeError("le move de Lucien a echoue : %r" % (res,))
        dec, state = _capture(sid, rid, board)
        rows.append(_row(sid, rid, state, dec, luc_id, "en-tour + a bouge"))

        # ---- bras 3 : HORS-TOUR, MEME unite, flag `Moved` encore pose -----------------------
        _act(sid, rid, {"kind": "endturn"}, 60)
        dec, state = _capture(sid, rid, board)
        rows.append(_row(sid, rid, state, dec, luc_id, "hors-tour + a bouge"))
    finally:
        if own and not keep:
            try:
                _r(sid, "disposeRunner", {"runnerId": rid}, 60)
            except Exception:
                pass

    joues = [r for r in rows if not r["ecarte"]]
    verdicts = sorted({r["natif"] for r in joues})
    hors = next((r for r in rows if r["bras"].startswith("hors-tour")), None)
    bilan = {
        "runner": rid, "board": board_id, "seed": seed, "rows": rows,
        "ecartes": len(rows) - len(joues),
        "ventilation_native": [hex(v) for v in verdicts],
        "degenere": len(verdicts) < 2,
        "accord_apres": all(r["accord_apres"] for r in joues),
        "desaccord_avant": [r["bras"] for r in joues if not r["accord_avant"]],
        # Le bras `hors-tour` ne PROUVE quelque chose que si le substrat des DEUX etages est
        # celui qu'on croit : `Moved` pose ET `IsTurnOfUnit` faux. Sans ca, l'accord serait un
        # accord de regime degenere.
        "substrat_hors_tour_ok": bool(
            hors is not None and hors["has_moved"] is True
            and hors["is_turn_of_unit"] is False and not hors["ecarte"]),
        "regression_fermee": bool(
            hors is not None and not hors["ecarte"]
            and hors["natif"] == 0 and hors["avant"] == int(TR.CasterHasNotMoved)
            and hors["apres"] == 0),
    }
    return bilan


def _print(b: dict) -> None:
    print("== #287-r11-r1-r1-r2  prefixe IsTurnOfUnit de CasterHasNotMoved (face RUNNER) ==")
    print("runner=%s board=%s seed=%s" % (b["runner"], b["board"], b["seed"]))
    print("%-30s %-10s %-10s %-10s %-8s %-9s %s"
          % ("bras", "natif", "apres", "avant", "moved", "isTurnOf", "curPlayer"))
    for r in b["rows"]:
        print("%-30s %-10s %-10s %-10s %-8s %-9s %s%s"
              % (r["bras"], hex(r["natif"]), hex(r["apres"]), hex(r["avant"]),
                 r["has_moved"], r["is_turn_of_unit"], r["currentPlayer"],
                 "   [ECARTE ValidRequest]" if r["ecarte"] else ""))
    print("")
    print("ventilation des verdicts NATIFS (bras joues) : %s" % (b["ventilation_native"],))
    print("bras ECARTES (etage amont, ValidRequest)      : %d" % b["ecartes"])
    print("accord port APRES / natif sur tous les bras   : %s" % b["accord_apres"])
    print("bras ou le port AVANT etait en desaccord      : %s" % (b["desaccord_avant"] or "aucun"))
    print("substrat du bras hors-tour (moved + !isTurnOf): %s" % b["substrat_hors_tour_ok"])
    print("REGRESSION FERMEE (natif 0 / avant 0x10 / apres 0) : %s" % b["regression_fermee"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    b = run(seed=a.seed, board_id=a.board, rid=a.runner, keep=a.keep)
    if a.json:
        print(json.dumps(b, indent=2, default=str))
    else:
        _print(b)
    if b["degenere"]:
        print("REFUS : la ventilation native est DEGENEREE -- ce montage ne separe rien.")
        return 2
    if not b["substrat_hors_tour_ok"]:
        print("REFUS : le substrat du bras hors-tour n'est pas celui attendu "
              "(flag `Moved` absent, ou `IsTurnOfUnit` non FAUX) -- accord non probant.")
        return 3
    if not b["accord_apres"]:
        print("ECHEC : le port APRES diverge du natif sur au moins un bras.")
        return 1
    if not b["regression_fermee"]:
        print("ECHEC : le bras hors-tour ne montre pas la regression fermee.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
