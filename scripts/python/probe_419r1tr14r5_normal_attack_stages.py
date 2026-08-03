"""#419-r1-tr14-r5 -- DECOMPOSITION PAR ETAGE de l'ecart de NIVEAU du composite d'attaque NORMALE.

Le residu (case-419-r1-tr14 §7, confirme independamment par `#419-r1-tr13-r1`) est un ecart
`port - natif` sur le composite d'ATTAQUE NORMALE du couple (`tauMarksman`, `astraBullgryn`),
mesure aux quatre crans du montage de la tranche 14 :

    tuile A (adjacente a la cible) : +0.000001 sans mouvement, 0.000000 apres mouvement
    tuile B (a distance)           : +5.458908 sans mouvement, +16.056789 apres mouvement

Ce probe ne FITTE aucun scalaire : il mesure, cran par cran, les TROIS etages qui composent ce
nombre, et il ajoute un SECOND CAS DISCRIMINANT qui separe les modeles concurrents.

## Les trois etages mesures

1. **DISPATCH** -- l'id de l'attaque normale LIVE (`decisionView`, `kind == "normal"`). C'est ce
   que `IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromPassive` produit :
   la fonction balaie la LISTE `PassiveAbilities` de l'`UnitConfiguration` (`config@+0xa8`) et rend
   le premier `StaticBattleRules.TriggeredAbility.GetCustomNormalAttack(<passif>)` non vide (puis,
   a defaut, le `Nullable` `config@+0xb0`). Le NormalAttackType custom est donc une fonction de
   l'ETAT de la configuration, pas du catalogue.
2. **PREDICTION** -- `aiPlaybookPredict` natif (`healthDmgMin/Max`, `appliedHits`) contre
   `engine.playbook.prediction.make_normal_attack_predictions` du port, a la MEME tuile.
3. **UTILITE** -- `pairUtility` natif (`ComparablePlaybook<T>$$CalculateUtilityFromPredictions`)
   contre `NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(...)["u"]` du port.

Un ecart qui apparait des l'etage 2 est un ecart de PREDICTION ; un ecart qui n'apparait qu'a
l'etage 3 est un ecart d'UTILITE. Les deux ne se corrigent pas au meme endroit.

## Le SECOND CAS DISCRIMINANT -- deux bras qui ne different QUE par la liste de passifs

    `kit`   : le seed BC NATIF -- `tauMarksman` garde `PassiveAbilities = [1119]`
              (`MV71SniperDroneSquad`), donc le natif garde son NormalAttackType custom.
    `strip` : le MEME seed BC, `PassiveAbilities = []` -- exactement ce que le montage de la
              tranche 14 installe (`catalog_inject.write_grafted_seed_bc(..., replace=True)`).

Le port, lui, resout son dispatch par le KIT gameconfig
(`engine.runner.abilities.loki.mv71.is_mv71_normal_attacker(visualId)`) : il rend la MEME reponse
sur les deux bras. Si l'ecart n'existe que sur `strip`, la cause est le DISPATCH (le port lit le
catalogue la ou le natif lit la configuration) ; s'il existe des deux cotes, la cause est ailleurs
et le dispatch est disculpe.

Usage :
    python scripts/python/probe_419r1tr14r5_normal_attack_stages.py \
        --state-file <ABSOLU>_kit.json --state-file-strip <ABSOLU>_strip.json

ASCII only.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import probe_124_line_elevation_decision as P124                 # noqa: E402
import probe_380_seed_bc_patch_survival as P380                  # noqa: E402
import probe_419r1tr14_heavy_bolt_pistol as P14                  # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.playbook import prediction as PV                     # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK        # noqa: E402

BOARD = P14.BOARD
SEED = "4141405"
HOST = P14.HOST                 # `tauMarksman` -- kit porteur de `MV71SniperDroneSquad` (1119)
ALLY = P14.ALLY
T_MAIN = P14.T_MAIN
FOE1 = P14.FOE1
FOES = P14.FOES
MINE = P14.MINE
HP = P14.HP
STEPS = P14.STEPS               # les QUATRE crans de la tranche 14, a l'identique

MontageError = P14.MontageError


# --------------------------------------------------------------------------- seed BC (2 bras)

def seed_bc(logs_dir: str, arm: str) -> str:
    """Le seed BC du bras `kit` (seed NATIF, passifs intacts) ou `strip` (`PassiveAbilities = []`
    sur l'hote SEUL -- l'unique difference entre les deux bras)."""
    import catalog_inject
    out = os.path.join(logs_dir, f"tr14r5_{arm}_seedbc.json")
    bc = catalog_inject._load_seed(None)
    before = None
    for u in (bc.get("Units") or ()):
        if u.get("Id") == HOST:
            before = list(u.get("PassiveAbilities") or ())
            if arm == "strip":
                u["PassiveAbilities"] = []
    if before is None:
        raise MontageError(f"{HOST} absent du seed BC -- montage NON INSTALLE")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(bc))
    P380.assert_survives(out)
    return out, before


def build_args(logs_dir: str, arm: str) -> tuple:
    stats = ";".join(f"{v}:Health={HP},RemainingHealth={HP}" for v in MINE + FOES)
    path, before = seed_bc(logs_dir, arm)
    return ["--board", BOARD, "--p-units", ",".join(MINE), "--a-units", ",".join(FOES),
            "--unit-stat", stats, "--seed-bc", path], before


# --------------------------------------------------------------------------- montage

def stage(sid, rpc, rid: int, layout) -> dict:
    elev, walk, _tid = P124._board(sid, rid)
    _dv, ids, myplayer = P14._roster(rpc, rid)
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    lay = layout if layout is not None else P14.find_layout(cells, elev)
    if lay is None:
        raise MontageError(f"montage NON INSTALLE : aucune configuration (T,A,B,K1,K2) sur {BOARD}")
    P14.attest_layout(lay, elev)
    return {"rid": rid, "cid": ids["C"], "ids": ids, "myplayer": myplayer,
            "layout": lay, "walk": walk, "elev": elev}


def _normal_ability(ctx) -> int:
    ab = next(iter(ctx.normal_ids or ()), None)
    if ab is None:
        raise MontageError("montage NON INSTALLE : aucune attaque normale sur le caster")
    return int(ab)


def _native_prediction(rpc, rid, cid, tgt, ab, tile) -> dict:
    r = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                                  "abilityType": ab, "col": int(tile[0]), "row": int(tile[1])}, 90)
    if not (isinstance(r, dict) and r.get("ok")):
        raise MontageError(f"aiPlaybookPredict indisponible {tile}: {str(r)[:200]}")
    ev = [e for e in (r.get("events") or []) if e.get("targetId") == tgt]
    if not ev:
        return {"dmin": None, "dmax": None, "hits": None, "count": r.get("count")}
    e = ev[0]
    return {"dmin": e.get("healthDmgMin"), "dmax": e.get("healthDmgMax"),
            "hits": e.get("appliedHits"), "count": r.get("count")}


def _port_prediction(scene, cid, tgt, tile) -> dict:
    out = PV.make_normal_attack_predictions(scene, cid, tgt, tile, meta=True)
    if not out:
        return {"dmin": None, "dmax": None, "hits": None}
    p = out[0].prediction
    ahd = p.accurate_health_damage
    return {"dmin": None if ahd is None else ahd.min, "dmax": None if ahd is None else ahd.max,
            "hits": getattr(p, "applied_hits", None)}


def _with_arm_dispatch(fn):
    """Rejoue `fn()` avec le dispatch MV71 du port FORCE sur le chemin ARME.

    C'est le CONTRE-BRAS de diagnostic : si, dispatch force, le port reproduit le natif du bras
    `strip`, alors le SEUL foyer de l'ecart est le dispatch (`is_mv71_normal_attacker`, resolu
    depuis le KIT gameconfig la ou `IdunBattle.Entities.Factories.UnitFactory$$
    GetCustomNormalAttackTypeFromPassive` lit `UnitConfiguration.PassiveAbilities`). S'il en reste,
    le chemin arme porte un SECOND gap, distinct."""
    from engine.runner.abilities.loki import mv71 as MV
    saved = MV.is_mv71_normal_attacker
    MV.is_mv71_normal_attacker = lambda *a, **k: False
    try:
        return fn()
    finally:
        MV.is_mv71_normal_attacker = saved


def measure(sid, rpc, arms: dict) -> list:
    rows = []
    placed = None
    for step, spot, tile_key, _expect in STEPS:
        if placed != spot:
            for case in arms.values():
                P14.place(sid, case, spot)
            placed = spot
        for arm, case in arms.items():
            lay = case["layout"]
            tile = lay[tile_key]
            dv = rpc("decisionView", {"runnerId": case["rid"], "allAbilities": True,
                                      "maxRank": 32}, 180)
            mov = rpc("aiMovableTiles", {"runnerId": case["rid"]}, 60)
            mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
            ctx = _ai_ctx.build(rpc, case["rid"], dv, mbu, case["cid"], W.load(),
                                _scene.build_predictor(rpc, case["rid"]))
            ab = _normal_ability(ctx)
            tgt = case["ids"]["T"]
            if tile not in [t for t in (ctx.action_tiles or []) if t and t[0] is not None]:
                raise MontageError(f"cran {step}/{arm} NON MESURABLE : tuile {tile} hors des "
                                   f"tuiles d'action du caster (emplacement {spot})")
            nat_p = _native_prediction(rpc, case["rid"], case["cid"], tgt, ab, tile)
            port_p = _port_prediction(ctx.scene, case["cid"], tgt, tile)
            nat_u = P14.pair_native(rpc, case["rid"], case["cid"], tgt, ab, tile)
            cand = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, tgt, ab)
            port_u = None if cand is None else float(cand["u"])
            arm_p = _with_arm_dispatch(lambda: _port_prediction(ctx.scene, case["cid"], tgt, tile))
            arm_c = _with_arm_dispatch(
                lambda: NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, tgt, ab))
            arm_u = None if arm_c is None else float(arm_c["u"])
            rows.append({"step": step, "arm": arm, "spot": spot, "tile": tile, "ab": ab,
                         "nat_pred": nat_p, "port_pred": port_p, "arm_pred": arm_p,
                         "nat_u": nat_u, "port_u": port_u, "arm_u": arm_u})
    return rows


# --------------------------------------------------------------------------- CLI

def _seed_build(state_file: str, argv_tail: list) -> int:
    """`rl_duel build` avec un `--seed` DEJA dans `argv_tail` (le volet generalisation le fournit
    lui-meme). Jumeau de `P14._build`, qui, lui, impose le seed de la tranche 14."""
    argv = [sys.executable, "rl_duel.py", "build", "--state-file", state_file, *argv_tail]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def run(sid, rpc, sf_kit: str, sf_strip: str, verbose: bool = True) -> dict:
    """Monte les DEUX bras, installe le layout commun, mesure les quatre crans. Rend
    `{"rows": [...], "arms": {...}}`. Point d'entree partage avec la garde jumelle
    `tests/engine/test_419r1tr14r5_normal_attack_dispatch_live.py`."""
    logs = os.path.dirname(os.path.abspath(sf_kit))
    os.makedirs(logs, exist_ok=True)
    arms = {}
    layout = None
    for arm, sf in (("kit", sf_kit), ("strip", sf_strip)):
        extra, before = build_args(logs, arm)
        rid = P14._build(sf, extra)
        case = stage(sid, rpc, rid, layout)
        layout = case["layout"]
        arms[arm] = case
        if verbose:
            print(f"bras {arm:<5} runner={rid} hote {HOST} u{case['cid']} "
                  f"PassiveAbilities(seed)={before if arm == 'kit' else []}")
    lay = arms["kit"]["layout"]
    if verbose:
        print(f"  layout T={lay['T']} A={lay['A']} B={lay['B']} K1={lay['K1']} K2={lay['K2']}")
    return {"rows": measure(sid, rpc, arms), "arms": arms}


# --------------------------------------------------------------------------- generalisation

# SECOND porteur, SECOND mold, SECOND board. `templAggressor` porte `Boltstorm` (1090), dont la
# substitution est `1128 Boltstorm_NormalAttack` -- le mold `GetAdditionalDamagePrediction` de
# #446-r1, pas le chemin drone de MV71. Le montage MV71 seul ne prouverait rien au-dela de son
# propre mold ; celui-ci exerce le SECOND call-site corrige
# (`_normal_attack_followup_prediction`), sur un board DIFFERENT (discipline de generalisation :
# un resultat sur un seul couple (board, seed) est peut-etre un artefact de ce board).
G_BOARD = "C2_02"
G_SEED = "4141412"
G_HOST = "templAggressor"       # HERO au pool, arme distance `Bolter` portee 2, passif `Boltstorm`
G_ALLY = "necroWarden"
G_TARGET = "astraBullgryn"
G_FOE1 = "astraCreed"
G_ATTACK_RANGE = 2
G_ABILITY_KIT = 1128            # `ActiveAbilityType.Boltstorm_NormalAttack`
G_ABILITY_STRIP = 69            # `ActiveAbilityType.Loki_NormalAttack`


@contextlib.contextmanager
def _kit_fallback(scene, uid):
    """COUPE le canal de mesure du caster (`UnitContext.passive_abilities = None`) le temps du
    bloc : le predicat de dispatch retombe alors sur le KIT gameconfig, ce qui EST le comportement
    d'avant #419-r1-tr14-r5. On mute la SOURCE, jamais le code livre."""
    c = scene.ctx(uid)
    saved = getattr(c, "passive_abilities", None)
    if c is not None:
        c.passive_abilities = None
    try:
        yield
    finally:
        if c is not None:
            c.passive_abilities = saved


def g_build_args(arm: str) -> list:
    """Les DEUX bras de generalisation. Ici le passif n'est pas retire par une greffe mais par
    `--unit-stat` -- le MEME levier que le controle apparie de #446-r1 §4, qui avait deja mesure
    que vider `PassiveAbilities` ramene l'attaque normale native a `69`."""
    stats = [f"{v}:Health={HP},RemainingHealth={HP}"
             for v in (G_HOST, G_ALLY, G_TARGET, G_FOE1)]
    if arm == "strip":
        stats.append(f"{G_HOST}:PassiveAbilities=[]")
    return ["--board", G_BOARD, "--p-units", f"{G_HOST},{G_ALLY}",
            "--a-units", f"{G_TARGET},{G_FOE1}", "--unit-stat", ";".join(stats)]


def g_stage(sid, rpc, rid: int, layout) -> dict:
    """Meme forme que `stage`, avec le roster de generalisation et la portee de `templAggressor`."""
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee")
    myplayer = mine[0].get("owner")
    ids = {}
    for key, vis in (("C", G_HOST), ("F", G_ALLY)):
        u = next((x for x in mine if x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster ami")
        ids[key] = u["id"]
    for key, vis in (("T", G_TARGET), ("E1", G_FOE1)):
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster adverse")
        ids[key] = u["id"]
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    saved = P14.ATTACK_RANGE
    P14.ATTACK_RANGE = G_ATTACK_RANGE
    try:
        lay = layout if layout is not None else P14.find_layout(cells, elev)
    finally:
        P14.ATTACK_RANGE = saved
    if lay is None:
        raise MontageError(f"montage NON INSTALLE : aucune configuration (T,A,B,K1,K2) sur "
                           f"{G_BOARD} a portee {G_ATTACK_RANGE}")
    P14.attest_layout(lay, elev)
    return {"rid": rid, "cid": ids["C"], "ids": ids, "myplayer": myplayer,
            "layout": lay, "walk": walk, "elev": elev}


def g_measure(sid, rpc, arms: dict) -> list:
    """Un seul cran par bras : le caster sur `B` (a distance de `T`), tuile d'attaque `B`. C'est le
    regime OU le fold RANGED de `Boltstorm` mord ; la melee delegue et ne discriminerait rien."""
    rows = []
    for case in arms.values():
        P14.place(sid, case, "B")
    for arm, case in arms.items():
        tile = case["layout"]["B"]
        dv = rpc("decisionView", {"runnerId": case["rid"], "allAbilities": True, "maxRank": 32}, 180)
        mov = rpc("aiMovableTiles", {"runnerId": case["rid"]}, 60)
        mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
        ctx = _ai_ctx.build(rpc, case["rid"], dv, mbu, case["cid"], W.load(),
                            _scene.build_predictor(rpc, case["rid"]))
        ab = _normal_ability(ctx)
        tgt = case["ids"]["T"]
        if tile not in [t for t in (ctx.action_tiles or []) if t and t[0] is not None]:
            raise MontageError(f"generalisation/{arm} NON MESURABLE : tuile {tile} hors des tuiles "
                               f"d'action du caster")
        nat_p = _native_prediction(rpc, case["rid"], case["cid"], tgt, ab, tile)
        port_p = _port_prediction(ctx.scene, case["cid"], tgt, tile)
        nat_u = P14.pair_native(rpc, case["rid"], case["cid"], tgt, ab, tile)
        cand = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, tgt, ab)
        # CONTRE-EPREUVE : le canal de mesure COUPE (`passive_abilities = None`) -- le predicat
        # retombe sur le KIT gameconfig, c'est-a-dire STRICTEMENT le comportement d'avant le fix.
        # C'est la mutation qui doit MORDRE sur le bras `strip` (le kit dit toujours `Boltstorm`,
        # alors que l'entite ne le porte plus) et rester INERTE sur le bras `kit`.
        with _kit_fallback(ctx.scene, case["cid"]):
            arm_p = _port_prediction(ctx.scene, case["cid"], tgt, tile)
            arm_c = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, tgt, ab)
        rows.append({"step": "ranged", "arm": arm, "spot": "B", "tile": tile, "ab": ab,
                     "nat_pred": nat_p, "port_pred": port_p, "arm_pred": arm_p,
                     "nat_u": nat_u, "port_u": None if cand is None else float(cand["u"]),
                     "arm_u": None if arm_c is None else float(arm_c["u"])})
    return rows


def run_generalize(sid, rpc, build, verbose: bool = True) -> dict:
    """Le volet GENERALISATION. `build(seed, extra) -> rid`."""
    arms, layout = {}, None
    for arm in ("kit", "strip"):
        rid = build(G_SEED, g_build_args(arm))
        case = g_stage(sid, rpc, rid, layout)
        layout = case["layout"]
        arms[arm] = case
        if verbose:
            print(f"[gen] bras {arm:<5} runner={rid} hote {G_HOST} u{case['cid']}")
    if verbose:
        lay = arms["kit"]["layout"]
        print(f"[gen]   board {G_BOARD} layout T={lay['T']} A={lay['A']} B={lay['B']}")
    return {"rows": g_measure(sid, rpc, arms), "arms": arms}


def dispose(rpc, arms: dict) -> None:
    for case in (arms or {}).values():
        try:
            rpc("disposeRunner", {"runnerId": case["rid"]}, 60)
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU, bras `kit`")
    ap.add_argument("--state-file-strip", help="chemin ABSOLU, bras `strip`")
    ap.add_argument("--generalize", action="store_true",
                    help="joue le SECOND porteur (`templAggressor`/`Boltstorm`) sur un AUTRE board")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    sf_k = args.state_file
    sf_s = args.state_file_strip or (os.path.splitext(sf_k)[0] + "_strip.json")
    if args.generalize:
        logs = os.path.dirname(os.path.abspath(sf_k))
        os.makedirs(logs, exist_ok=True)
        seq = {"n": 0}

        def _build(seed, extra):
            """Builder du volet CLI. Sous pytest c'est la fixture `build_runner` qui est injectee
            a `run_generalize` a la place -- meme signature, gestion des runners du harnais."""
            seq["n"] += 1
            sf = os.path.join(logs, f"tr14r5_gen_{seq['n']}.json")
            return _seed_build(sf, ["--seed", str(seed), *extra])

        rows = run_generalize(sid, rpc, _build)["rows"]
    else:
        rows = run(sid, rpc, sf_k, sf_s)["rows"]
    for r in rows:
        np_, pp, ap = r["nat_pred"], r["port_pred"], r["arm_pred"]
        du = None if (r["port_u"] is None or r["nat_u"] is None) else r["port_u"] - r["nat_u"]
        da = None if (r["arm_u"] is None or r["nat_u"] is None) else r["arm_u"] - r["nat_u"]
        print(f"  [{r['step']:<16}|{r['arm']:<5}] spot={r['spot']} tile={r['tile']} ab={r['ab']} "
              f"| NAT dmg=({np_['dmin']},{np_['dmax']}) hits={np_['hits']} "
              f"| PORT dmg=({pp['dmin']},{pp['dmax']}) hits={pp['hits']} "
              f"| PORT_ARM dmg=({ap['dmin']},{ap['dmax']}) hits={ap['hits']} "
              f"| nat_u={r['nat_u']:.6f} port_u={'None' if r['port_u'] is None else format(r['port_u'], '.6f')} "
              f"ECART_U={'None' if du is None else format(du, '+.6f')} "
              f"ECART_U_ARM={'None' if da is None else format(da, '+.6f')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
