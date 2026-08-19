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

#: LA GENERALISATION, et elle est gratuite en runner : `bloodIntercessor` est DEJA au roster, et il
#: porte `1153 HammerOfWrath`, dont le masque est `0x102004032` -- DIFFERENT de celui de 1163
#: (`0x106004012`), meme bit `CasterHasNotMoved` mis a part. Le prefixe ne depend NI de l'ability NI
#: de son masque : deux couples a masques distincts le montrent, un seul ne le montrerait pas.
#: Chaque bras est mesure pour LES DEUX couples, sur le MEME etat fige.
COUPLES = ((BLACK_RAGE, LUCIEN), (1153, ALLY))
A_UNITS = "necroWarden,necroWarden,necroWarden"
BOARD = "MC1_67"
SEED = "777"
TOURS_DE_CHAUFFE = 6                # purge les `initialCooldownTurns` (sinon `ValidRequest` partout)

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


def _caster_reason(sid, rid, caster_id, ability_id) -> int:
    """`casterReason` du RPC `abilityReason` = `AttackQuery$$GetInvalidCasterReason(caster,
    casterTile, abilityType)`. AUCUN `targetId` n'est passe : le volet CASTER n'en lit pas."""
    r = _r(sid, "abilityReason", {"runnerId": rid, "casterId": caster_id,
                                  "abilityType": int(ability_id)}, 90) or {}
    cr = r.get("casterReason") or {}
    return int(cr.get("hex") or "0x0", 16)


# --------------------------------------------------------------------------- les deux ports

def _port(state, caster_id, ability_id, *, prefixe_porte: bool) -> int:
    """`get_invalid_caster_reason` sur l'etat fige, dans les DEUX versions.

    `prefixe_porte=False` = l'etat de `master` AVANT cette tranche : la clause `CasterHasNotMoved`
    etait evaluee inconditionnellement. On l'obtient en substituant l'attribut
    `engine.runner.abilities.targeting.is_turn_of_unit` -- le module CONSOMMATEUR, seule forme qui
    morde une liaison `from ..components import is_turn_of_unit`."""
    ability = ABILITY_CLASSES[int(ability_id)]()
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


def _row(sid, rid, state, dec, caster_id, ability_id, label) -> dict:
    """UNE mesure : oracle natif, port APRES, port AVANT, PLUS le substrat des deux etages."""
    natif = _caster_reason(sid, rid, caster_id, ability_id)
    apres = _port(state, caster_id, ability_id, prefixe_porte=True)
    avant = _port(state, caster_id, ability_id, prefixe_porte=False)
    itou = T.is_turn_of_unit(state, int(caster_id))
    return {
        "bras": label,
        "ability": int(ability_id),
        "caster": int(caster_id),
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


def _rows(sid, rid, state, dec, ids_par_visual, label) -> list:
    """LE MEME bras, mesure pour les DEUX couples (ability, porteur) -- la generalisation."""
    out = []
    for aid, vis in COUPLES:
        cid = ids_par_visual.get(vis)
        if cid is None:
            continue
        out.append(_row(sid, rid, state, dec, cid, aid, "%s [%d/%s]" % (label, aid, vis)))
    return out


def run(seed: str = SEED, board_id: str = BOARD, sid=None, rid=None, keep: bool = False) -> dict:
    sid = sid or _resolve_session()
    own = rid is None
    rid = rid if rid is not None else _build(sid, seed, board_id)
    rows: list[dict] = []
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        _my_turn(sid, rid)

        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            raise RuntimeError("boardGraph indisponible")
        board = Board(bg["tiles"], adjacency="native_sym")

        dec = _dv(sid, rid)
        ids = {}
        for aid, vis in COUPLES:
            u = next((x for x in (dec.get("units") or [])
                      if x.get("visualId") == vis and x.get("alive")), None)
            if u is None:
                raise RuntimeError("porteur %r absent du roster monte" % (vis,))
            ids[vis] = int(u["id"])

        # LA SEQUENCE NE SUPPOSE RIEN DE LA MECANIQUE DE TOUR, et c'est une correction MESUREE :
        # bouger les DEUX porteurs d'un coup faisait BASCULER le tour tout seul
        # (`VerifyUnitsTurnFinishedOperation` termine une unite sans option), si bien que le bras
        # etiquete « en-tour » etait en fait un bras hors-tour -- le probe l'a REFUSE (ventilation
        # degeneree), ce qui est exactement son travail. On CAPTURE donc apres chaque geste, et le
        # ROLE de chaque ligne est DERIVE du substrat mesure (`has_moved`, `is_turn_of_unit`),
        # jamais suppose.
        dec, state = _capture(sid, rid, board)
        rows += _rows(sid, rid, state, dec, ids, "initial")

        for vis, uid in ids.items():
            tiles = _movable(sid, rid, uid)
            if not tiles:
                raise RuntimeError("aucune tuile de deplacement pour %s" % (vis,))
            d0 = _dv(sid, rid)
            u0 = next((x for x in (d0.get("units") or []) if x.get("id") == uid), None)
            cible = min(tiles, key=lambda t: (hexgeo.distance(t, _pos(u0)) != 1, t))
            res = _act(sid, rid, {"kind": "move", "unitId": uid,
                                  "to": {"col": cible[0], "row": cible[1]}}, 90)
            if not bool(((res or {}).get("actions") or [{}])[0].get("ok")):
                raise RuntimeError("le move de %s a echoue : %r" % (vis, res))
            dec, state = _capture(sid, rid, board)
            rows += _rows(sid, rid, state, dec, ids, "apres-move(%s)" % vis)

        # ... et si le tour n'a pas bascule tout seul, on le fait basculer.
        d = _dv(sid, rid)
        mien = next((u for u in (d.get("units") or []) if u.get("id") in ids.values()), None)
        if mien is not None and d.get("currentPlayer") == mien.get("owner"):
            _act(sid, rid, {"kind": "endturn"}, 60)
            dec, state = _capture(sid, rid, board)
            rows += _rows(sid, rid, state, dec, ids, "apres-endturn")
    finally:
        if own and not keep:
            try:
                _r(sid, "disposeRunner", {"runnerId": rid}, 60)
            except Exception:
                pass

    joues = [r for r in rows if not r["ecarte"]]
    verdicts = sorted({r["natif"] for r in joues})
    # LE ROLE EST DERIVE DU SUBSTRAT, jamais de l'etiquette (cf. la sequence ci-dessus).
    #   * DISCRIMINANT = a bouge ET ce n'est PAS son tour -> le prefixe fait SAUTER la clause ;
    #   * ARME         = a bouge ET c'est son tour        -> la clause s'evalue, verdict `0x10`.
    for r in rows:
        r["role"] = ("discriminant" if (r["has_moved"] and r["is_turn_of_unit"] is False)
                     else "arme" if (r["has_moved"] and r["is_turn_of_unit"] is True)
                     else "temoin")
    disc = [r for r in joues if r["role"] == "discriminant"]
    arme = [r for r in joues if r["role"] == "arme"]
    ferme = [r for r in disc
             if r["natif"] == 0 and r["avant"] == int(TR.CasterHasNotMoved) and r["apres"] == 0]
    couples = ["%d/%s" % (a, v) for (a, v) in COUPLES]
    # La regression doit etre fermee sur TOUS les couples, pas sur au moins un : c'est ce qui fait
    # de la seconde ability une GENERALISATION et non un decor.
    couples_disc = {(r["ability"], r["caster"]) for r in ferme}
    bilan = {
        "runner": rid, "board": board_id, "seed": seed, "rows": rows, "couples": couples,
        "ecartes": len(rows) - len(joues),
        "ventilation_native": [hex(v) for v in verdicts],
        "degenere": len(verdicts) < 2,
        "accord_apres": all(r["accord_apres"] for r in joues),
        "desaccord_avant": [r["bras"] for r in joues if not r["accord_avant"]],
        "n_discriminant": len(disc), "n_arme": len(arme),
        # Sans bras ARME, on ne saurait pas que la clause mord VRAIMENT quelque part -- l'accord du
        # bras discriminant serait alors compatible avec un port qui ne teste plus rien.
        "substrat_ok": bool(disc and arme),
        "regression_fermee": bool(disc and len(ferme) == len(disc)
                                  and len(couples_disc) == len(COUPLES)),
        "couples_fermes": sorted("%d/u%d" % c for c in couples_disc),
    }
    return bilan


def _print(b: dict) -> None:
    print("== #287-r11-r1-r1-r2  prefixe IsTurnOfUnit de CasterHasNotMoved (face RUNNER) ==")
    print("runner=%s board=%s seed=%s couples=%s"
          % (b["runner"], b["board"], b["seed"], ",".join(b["couples"])))
    print("%-46s %-13s %-8s %-8s %-8s %-7s %-9s %s"
          % ("bras", "role", "natif", "apres", "avant", "moved", "isTurnOf", "curPlayer"))
    for r in b["rows"]:
        print("%-46s %-13s %-8s %-8s %-8s %-7s %-9s %s%s"
              % (r["bras"], r["role"], hex(r["natif"]), hex(r["apres"]), hex(r["avant"]),
                 r["has_moved"], r["is_turn_of_unit"], r["currentPlayer"],
                 "   [ECARTE ValidRequest]" if r["ecarte"] else ""))
    print("")
    print("ventilation des verdicts NATIFS (bras joues) : %s" % (b["ventilation_native"],))
    print("bras ECARTES (etage amont, ValidRequest)      : %d" % b["ecartes"])
    print("bras DISCRIMINANTS / ARMES                    : %d / %d"
          % (b["n_discriminant"], b["n_arme"]))
    print("accord port APRES / natif sur tous les bras   : %s" % b["accord_apres"])
    print("bras ou le port AVANT etait en desaccord      : %s" % (b["desaccord_avant"] or "aucun"))
    print("substrat (au moins un DISCRIMINANT et un ARME): %s" % b["substrat_ok"])
    print("couples dont la regression est FERMEE         : %s" % (b["couples_fermes"],))
    print("REGRESSION FERMEE sur TOUS les couples        : %s" % b["regression_fermee"])


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
    if not b["substrat_ok"]:
        print("REFUS : il manque un bras DISCRIMINANT (a bouge, pas son tour) ou un bras ARME "
              "(a bouge, son tour) -- l'accord ne serait pas probant.")
        return 3
    if not b["accord_apres"]:
        print("ECHEC : le port APRES diverge du natif sur au moins un bras.")
        return 1
    if not b["regression_fermee"]:
        print("ECHEC : la regression n'est pas fermee sur TOUS les couples.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
