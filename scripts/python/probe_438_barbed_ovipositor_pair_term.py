"""#438 -- MONTAGE NOMME des DEUX poids de `BarbedOvipositor` (1204) sur la face ATTACK, et mesure
natif contre port.

`IdunBattle.AI.Playbook.Loki.BarbedOvipositorPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__4$$MoveNext`
a QUATRE sorties, donc QUATRE regimes a reunir -- et c'est tout l'enjeu du montage, parce que trois
d'entre eux rendent 0 pour des RAISONS DIFFERENTES :

  R1  cible non `Mechanical`, kill GARANTI    -> `BARBEDOVIPOSITOR_DefinitelyKill` (50)
  R2  cible non `Mechanical`, kill POSSIBLE   -> `BARBEDOVIPOSITOR_PossibleKill`   (25)
  R3  cible non `Mechanical`, AUCUN kill      -> 0   (`get_MightBeKill` faux)
  R4  cible `Mechanical`, kill GARANTI        -> 0   (le trait 5 coupe AVANT le poids)

Un montage qui n'obtiendrait que R3/R4 serait DEGENERE : port et natif y rendent tous deux 0, ils
seraient parfaitement d'accord, et le port pourrait etre faux sur R1/R2 sans que rien ne rougisse.
C'est pourquoi le probe ECHOUE (il ne skippe pas, #268) si les quatre regimes ne sont pas reunis.

**Les PV ne s'obtiennent pas par chance** : au rank 17 les cibles ont des milliers de PV et
l'attaque normale du Parasite en retire quelques centaines -- AUCUN kill n'est possible
naturellement, donc le montage nu tombe entier dans R3. Les PV sont donc CALIBRES, en deux passes :

  passe A -- runner nu, on lit les bornes RAW de l'attaque normale contre chaque cible par
             `aiPlaybookPredict` (`willKillDmg` = rawMin@0x1c, `mightKillDmg` = rawMax@0x20 --
             les DEUX bornes que lisent `get_WillBeKill` et `get_MightBeKill`) ;
  passe B -- runner de mesure, `--unit-stat <cible>:Health=<calibre>` :
             R1/R4 a 1 PV (kill garanti quel que soit le block), R2 a `rawMin + 1` (au-dessus de
             la borne garantie, sous la borne possible), R3 a `rawMax + marge`.

Le poids NE VIENT PAS d'ici : les deux cles sont lues dans `Utilities.Default.TriggeredAbilities`
du BC SERVI, et le probe refuse de conclure si l'une est nulle ou si les deux sont EGALES (elles ne
discrimineraient plus la branche `WillBeKill`, qui est justement ce que la mesure doit trancher).

Usage :
    python scripts/python/probe_438_barbed_ovipositor_pair_term.py --state-file <chemin ABSOLU>

Le probe construit LUI-MEME ses deux runners sur CE state-file (le second remplace le premier :
un seul runner vivant a la fois). ASCII only.
Garde jumelle : `scripts/python/tests/engine/test_438_barbed_ovipositor_pair_term_live.py`.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import hexgeo                                                    # noqa: E402
import probe_124_line_elevation_decision as P124                 # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.entities.traits.unit_trait import (UnitTrait,        # noqa: E402
                                               entity_trait_ids)
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK        # noqa: E402

BOARD = "MC1_67"
SEED = "41504"
CASTER = "tyranParasite"        # HERO au pool ; `BarbedOvipositor` est dans son kit passif
TGT_SURE = "astraBullgryn"      # non `Mechanical`, PV cales a 1  -> R1 (kill GARANTI)
TGT_MAYBE = "astraCreed"        # non `Mechanical`, PV cales      -> R2 (kill POSSIBLE seulement)
TGT_NONE = "astraDreir"         # non `Mechanical`, PV releves    -> R3 (aucun kill)
TGT_MECH = "admecDestroyer"     # `Mechanical`, PV cales a 1      -> R4 (le trait coupe)
FOES = (TGT_SURE, TGT_MAYBE, TGT_NONE, TGT_MECH)
ABILITY = int(TriggeredAbilityType.BarbedOvipositor)          # 1204
KEY_DEFINITELY = "BARBEDOVIPOSITOR_DefinitelyKill"
KEY_POSSIBLE = "BARBEDOVIPOSITOR_PossibleKill"
MECHANICAL = int(UnitTrait.Mechanical)                        # 5
EPS = 1e-4                      # Fix64 natif contre float du port
NONE_MARGIN = 5000              # PV ajoutes au-dessus de rawMax pour fermer TOUT kill (R3)

BUILD_ARGS_CALIB = ["--board", BOARD, "--p-units", CASTER, "--a-units", ",".join(FOES)]


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


# --------------------------------------------------------------------------- oracles

def pair_native(rpc, rid, cid, tgt, ab, tile) -> float:
    r = rpc("pairUtility", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                            "abilityType": ab, "col": tile[0], "row": tile[1]}, 90)
    v = (r or {}).get("utility")
    if not isinstance(v, (int, float)):
        raise MontageError(f"pairUtility natif indisponible pour {tile} / cible {tgt}: {r}")
    return float(v)


def pair_port(ctx, ab, tgt, tile) -> float:
    cand = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, tgt, ab)
    if cand is None:
        raise MontageError(f"le port ne produit AUCUNE action depuis {tile} sur {tgt}")
    return float(cand["u"])


def native_bounds(rpc, rid, cid, tgt, ab, tile) -> dict:
    """Bornes NATIVES de la paire : `hpBefore`, `willKillDmg` (rawMin@0x1c) et `mightKillDmg`
    (rawMax@0x20) du premier event de degat d'`aiPlaybookPredict`. Ce sont EXACTEMENT les deux
    scalaires que comparent `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill` et
    `$$get_MightBeKill` a `CurrentHealth@0x00` -- calibrer dessus, c'est calibrer sur l'oracle."""
    r = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                                  "abilityType": ab, "col": tile[0], "row": tile[1]}, 60)
    if not (r or {}).get("ok"):
        raise MontageError(f"aiPlaybookPredict KO pour la cible {tgt} depuis {tile}: {r}")
    evs = [e for e in (r.get("events") or []) if e.get("targetId") == tgt]
    if not evs:
        raise MontageError(f"aucun event de degat natif sur la cible {tgt} depuis {tile} -- "
                           f"hors de portee ? events={r.get('events')}")
    e = evs[0]
    return {"hp": int(e.get("hpBefore") or 0),
            "raw_min": int(e.get("willKillDmg") or 0),
            "raw_max": int(e.get("mightKillDmg") or 0)}


# --------------------------------------------------------------------------- montage

def _stage(sid, rpc, rid: int) -> dict:
    """Place le caster au CENTRE et les quatre cibles sur quatre de ses voisins, puis rend le
    contexte de decision.

    Le drive est indispensable : hors portee d'arme, `pairUtility` ne rend que le terme triggered
    tandis que le port produit quand meme sa composante de degat -- les deux cotes ne parlent alors
    pas de la meme chose. On DEPLACE donc les unites plutot que d'accuser la geometrie de spawn
    (montage NOMME reutilise : `probe_124_line_elevation_decision._drive_to`)."""
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    cid = next((u["id"] for u in mine if u.get("visualId") == CASTER), None)
    if cid is None:
        raise MontageError(f"montage NON INSTALLE : {CASTER} absent du roster")
    myplayer = mine[0].get("owner")
    tgt = {}
    for vis in FOES:
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster adverse")
        tgt[vis] = u["id"]

    # (a) LE PASSIF EST-IL DANS L'AbilitiesComponent ? Sans 1204 dedans, le dispatcher ne l'itere
    #     pas et la mesure ne prouverait rien (moitie CABLAGE du patron #419).
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": cid}, 60) or {}
    live_ids = [i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)]
    if ABILITY not in live_ids:
        raise MontageError(
            f"montage NON INSTALLE : {ABILITY} n'est PAS dans l'AbilitiesComponent de {CASTER} "
            f"-- triggered live lus = {sorted(set(live_ids))}")

    # (b) Une tuile a >= 4 voisins accessibles : le caster au centre, une cible par voisin.
    cells = sorted(p for p, w in walk.items() if w and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    star = None
    for p in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        nb = [q for q in hexgeo.neighbors(p[0], p[1])
              if walk.get(q) and elev.get(q) is not None and abs(elev[q] - elev[p]) < 2]
        if len(nb) >= len(FOES):
            star = (p, nb[:len(FOES)])
            break
    if star is None:
        raise MontageError(f"montage NON INSTALLE : aucune tuile walkable a {len(FOES)} voisins "
                           f"walkables -- les quatre cibles ne peuvent pas etre au contact")
    cpos, ring = star
    wanted = {cid: cpos}
    for vis, pos in zip(FOES, ring):
        wanted[tgt[vis]] = pos
    if not P124._drive_to(sid, rid, walk, elev, wanted):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"montage NON INSTALLE : placement incomplet -- voulu {wanted}, "
                           f"obtenu { {u: pos.get(u) for u in wanted} }")
    P124._give_turn_back(sid, rid, myplayer)

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    ctx = _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), _scene.build_predictor(rpc, rid))
    ab = next(iter(ctx.normal_ids or ()), None)
    if ab is None:
        raise MontageError("montage NON INSTALLE : aucune attaque normale sur le caster")

    # Tuiles ACCEPTEES par l'oracle = `ctx.action_tiles`, restreintes au CONTACT des quatre cibles :
    # hors portee, natif et port ne mesurent pas la meme chose (ecart parasite).
    foe_pos = [p for _vis, p in zip(FOES, ring)]
    tiles = [t for t in (ctx.action_tiles or [])
             if t and t[0] is not None and all(hexgeo.distance(t, p) <= 1 for p in foe_pos)]
    if not tiles:
        raise MontageError("montage NON INSTALLE : aucune tuile au contact des QUATRE cibles -- "
                           "la mesure ne comparerait pas la meme chose")
    return {"rid": rid, "cid": cid, "tgt": tgt, "ab": ab, "ctx": ctx, "tiles": tiles[:1]}


def calibrate(sid, rpc, rid: int) -> dict:
    """Passe A -- rend `{visualId: {"hp", "raw_min", "raw_max"}}` lu du NATIF, de quoi caler les PV.

    Le regime R2 exige `rawMin < HP <= rawMax` : si les deux bornes sont EGALES (arme sans spread,
    ou degat plafonne), la fenetre est VIDE et le montage est impossible -- on le dit, on ne rend
    pas un R2 qui n'en est pas un."""
    st = _stage(sid, rpc, rid)
    out = {}
    for vis, uid in st["tgt"].items():
        out[vis] = native_bounds(rpc, rid, st["cid"], uid, st["ab"], st["tiles"][0])
    b = out[TGT_MAYBE]
    if b["raw_max"] <= b["raw_min"]:
        raise MontageError(
            f"montage IMPOSSIBLE : les bornes RAW de {TGT_MAYBE} ne laissent aucune fenetre pour "
            f"le regime « kill POSSIBLE mais pas garanti » (rawMin={b['raw_min']} "
            f"rawMax={b['raw_max']}) -- il faut rawMax > rawMin")
    return out


def build_args_measure(calib: dict) -> list[str]:
    """Passe B -- les args de build qui INSTALLENT les quatre regimes (PV calibres sur le natif)."""
    stats = [f"{TGT_SURE}:Health=1",
             f"{TGT_MAYBE}:Health={calib[TGT_MAYBE]['raw_min'] + 1}",
             f"{TGT_NONE}:Health={calib[TGT_NONE]['raw_max'] + NONE_MARGIN}",
             f"{TGT_MECH}:Health=1"]
    return BUILD_ARGS_CALIB + ["--unit-stat", ";".join(stats)]


def build_case(sid, rpc, rid: int) -> dict:
    """Passe B -- monte le cas de MESURE et ATTESTE que les quatre regimes sont bien installes.

    L'attestation est prise sur le NATIF (`aiPlaybookPredict`) ET sur le PORT (les mirrors
    `might_be_kill`/`will_be_kill`) : si les deux ne disent pas la meme chose du regime, la mesure
    d'utilite qui suivrait comparerait deux situations differentes -- on refuse."""
    st = _stage(sid, rpc, rid)
    ctx, tile = st["ctx"], st["tiles"][0]
    sc = ctx.scene
    vis_by_id = getattr(sc, "vis_by_id", None) or {}
    from engine.services.damage_prediction import DamagePredictionResult
    from engine.services.min_max_damage import MinMaxDamage

    regimes = {}
    for vis, uid in st["tgt"].items():
        b = native_bounds(rpc, st["rid"], st["cid"], uid, st["ab"], tile)
        nat_might = b["hp"] <= b["raw_max"]
        nat_will = b["hp"] <= b["raw_min"]
        p = DamagePredictionResult(current_health=b["hp"],
                                   raw_health_damage=MinMaxDamage(min=b["raw_min"],
                                                                  max=b["raw_max"]))
        if (p.might_be_kill(), p.will_be_kill()) != (nat_might, nat_will):
            raise MontageError(
                f"montage NON ATTESTE : sur {vis}, le natif dit might={nat_might} will={nat_will} "
                f"et le mirror dit might={p.might_be_kill()} will={p.will_be_kill()} "
                f"(hp={b['hp']} rawMin={b['raw_min']} rawMax={b['raw_max']})")
        tr = entity_trait_ids(sc.ctx(uid) if hasattr(sc, "ctx") else None, vis_by_id.get(uid))
        regimes[vis] = {"mechanical": MECHANICAL in tr, "might": nat_might, "will": nat_will,
                        "hp": b["hp"], "raw_min": b["raw_min"], "raw_max": b["raw_max"]}

    want = {TGT_SURE: (False, True, True), TGT_MAYBE: (False, True, False),
            TGT_NONE: (False, False, False), TGT_MECH: (True, True, True)}
    for vis, exp in want.items():
        got = (regimes[vis]["mechanical"], regimes[vis]["might"], regimes[vis]["will"])
        if got != exp:
            raise MontageError(
                f"montage NON INSTALLE : {vis} devait etre (mechanical, might, will)={exp} et vaut "
                f"{got} -- {regimes[vis]}")

    w_def = float(ctx.wt.triggered(KEY_DEFINITELY))
    w_pos = float(ctx.wt.triggered(KEY_POSSIBLE))
    if w_def == 0 or w_pos == 0:
        raise MontageError(f"montage NON INSTALLE : le BC servi porte {KEY_DEFINITELY}={w_def} "
                           f"{KEY_POSSIBLE}={w_pos} -- un poids nul ne discrimine rien")
    if w_def == w_pos:
        raise MontageError(f"montage DEGENERE : {KEY_DEFINITELY} == {KEY_POSSIBLE} == {w_def} -- la "
                           f"branche `WillBeKill` ne serait plus discriminee par la mesure")
    st.update({"regimes": regimes, "w_def": w_def, "w_pos": w_pos})
    return st


def expected_term(case: dict, vis: str) -> float:
    """Ce que la face ATTACK DOIT verser sur cette cible, selon les quatre sorties natives."""
    r = case["regimes"][vis]
    if not r["might"] or r["mechanical"]:
        return 0.0
    return case["w_def"] if r["will"] else case["w_pos"]


def measure(rpc, case: dict) -> list[dict]:
    """Une ligne par (cible, tuile) : natif, port, port SANS le playbook 1204."""
    import engine.playbook.psyker as PSY
    out = []
    for vis, uid in case["tgt"].items():
        for tile in case["tiles"]:
            nat = pair_native(rpc, case["rid"], case["cid"], uid, case["ab"], tile)
            port = pair_port(case["ctx"], case["ab"], uid, tile)
            saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS.pop(ABILITY, None)
            if saved is None:
                raise MontageError("le playbook 1204 n'est PAS au registre -- rien a muter")
            try:
                muted = pair_port(case["ctx"], case["ab"], uid, tile)
            finally:
                PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved
            out.append({"target": vis, "regime": case["regimes"][vis], "tile": tile,
                        "expected": expected_term(case, vis),
                        "native": nat, "port": port, "port_muted": muted})
    return out


# --------------------------------------------------------------------------- CLI

def _build(state_file: str, extra: list[str]) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            "--state-file", state_file, *extra]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    import json
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU du state-file (le probe construit SES deux runners dessus)")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = _build(args.state_file, BUILD_ARGS_CALIB)
    calib = calibrate(sid, rpc, rid)
    print("[calib] bornes RAW natives par cible (passe A) :")
    for vis, b in calib.items():
        print(f"  {vis:<16} hp={b['hp']:<8} rawMin={b['raw_min']:<6} rawMax={b['raw_max']}")

    rid = _build(args.state_file, build_args_measure(calib))
    case = build_case(sid, rpc, rid)
    print(f"runner {rid} | caster u{case['cid']} | poids {KEY_DEFINITELY}={case['w_def']} "
          f"{KEY_POSSIBLE}={case['w_pos']}")
    for row in measure(rpc, case):
        r = row["regime"]
        d = row["port"] - row["native"]
        dm = row["native"] - row["port_muted"]
        print(f"  {row['target']:<16} mech={str(r['mechanical']):<5} might={str(r['might']):<5} "
              f"will={str(r['will']):<5} hp={r['hp']:<7} @{row['tile']} "
              f"nat={row['native']:.6f} port={row['port']:.6f} d={d:+.6f} | "
              f"mute={row['port_muted']:.6f} manque={dm:+.6f} attendu={row['expected']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
