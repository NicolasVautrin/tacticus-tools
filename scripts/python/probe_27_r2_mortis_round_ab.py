"""probe #27-r2 -- A/B causal LIVE de MortisRound (1004) : le terme custom est le GAIN d'utilite
de TUILE que le PUSH inflige a la cible, TRONQUE vers `int`.

`IdunBattle.AI.Playbook.Loki.MortisRoundPlaybook$$CalculateCustomUtility` =
`(Fix64)(int) Playbook<T>$$GetTargetUtilityDiffOnDisplace(caster, casterTile, GetPushableTiles,
target).value`, ou le diff est `max(0, u0 - uN)` sur l'arc ARRIERE de la cible, avec
`u = GetUtility(UtilityType.Tile).EvaluateAttack(UtilityAttackCase$$Base(TARGET, ...))`.

MONTAGE (board MC1_67, elevations 1..4, max=4 min=1). DEUX geometries dont le custom differe par
la seule ELEVATION de la tuile d'arrivee, et dans chacune un levier d'OCCUPATION :

  geom A : caster (0,1) [elev 3], cible (0,3) [elev 4 = MAX] -> arc [(0,4)] [elev 3]
           u0 = 10*4 + HighestElevation(10) = 50 ; uN = 10*3 = 30  => custom = **20**
  geom B : caster (0,2) [elev 3], cible (0,4) [elev 3]        -> arc [(0,5)] [elev 2]
           u0 = 30 ; uN = 20                                   => custom = **10**

  Les DEUX casters sont a elevation 3 et a distance 2 de leur cible : le terme `Tile(7)` de la
  tuile de tir et les predictions de degat sont donc IDENTIQUES entre A et B -- seul le custom
  change. C'est ce qui rend la MAGNITUDE mesurable et pas seulement le signe.

  Dans chaque geometrie, deux bras :
    LIBRE   : l'appat ALLIE est relegue loin           -> arc non vide -> custom = 20 (A) / 10 (B)
    BLOQUE  : le MEME appat ALLIE occupe la tuile d'arc -> arc = []    -> custom = 0
  L'appat est un ALLIE du caster : jamais ciblable, donc il ne deplace aucun autre terme -- et il
  n'a pas le trait `Steppable`, donc `DSLSelectors.EmptyOrHasSteppableUnit` le rejette.

  Cinquieme bras, CONTROLE de `IdunBattle.Entities.UnitExtensions$$IsDisplaceable` : une unite
  `BigTarget` prend EXACTEMENT la tuile (0,3) que la cible deplacable occupait. Geometrie et arc
  identiques, mais le natif doit retomber a custom 0.

CALIBRAGE (`--hp-target`) : le natif choisit 1004 plutot que l'attaque normale quand
`pair1004 + custom > pair69 + 1` (le custom de la normale vaut `Fix64(1)`). En reglant
`ecart = pair69 + 1 - pair1004` DANS (10, 20) :
    geom A (custom 20) -> le natif prend **1004**
    geom B (custom 10) -> 10 ne suffit pas -> le natif reste sur **69**
=> la magnitude est ENCADREE par le natif seul, sans jamais fitter un scalaire.

Usage :
    python probe_27_r2_mortis_round_ab.py --build --engine [--hp-target=N]
    python probe_27_r2_mortis_round_ab.py --calib --hp-target=N   # paires seules, pas de bras
ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
STATE = LOGS / "rs_mortis_r2.json"
BOARD = "MC1_67"
SEED = 909
# `ecart = pair69 + 1 - pair1004` MESURE par `--calib` : 11046 (naturel) -> 2.774 ; 2200 -> 9.946 ;
# **1800 -> 11.932** (dans (10,20) : le point de fonctionnement) ; 1500 -> 58.856 (la normale TUE,
# le bonus Kill fait exploser l'ecart -- hors regime).
HP_TARGET = 1800

CASTER_VIS = "ultraEliminatorSgt"  # HERO du pool, aucun catalog_inject ni greffe
ALLY_VIS = "ultraCalgar"           # appat ALLIE (jamais ciblable) qui bouche la tuile de push
TARGET_VIS = "blackTerminator"     # DEPLACABLE (aucun de Immovable/Hulking/BigTarget)
# Controle `IsDisplaceable` : `tauCrisis` porte `BigTarget` (1017), l'un des trois traits que
# `IdunBattle.Entities.UnitExtensions$$IsDisplaceable` REFUSE. Mesure du 2026-08-01 : 8 des 97
# unites du pool sont dans ce cas (adeptMorvenn, astraBullgryn, blackObliterator,
# custoVexilusPraetor, orksKillaKan, orksWarboss, tauCrisis, tyranTyrantGuard).
IMMOVABLE_VIS = "tauCrisis"

GEOMS = {
    "a": {"caster": "0,1", "target": "0,3", "push": "0,4", "custom": 20},
    "b": {"caster": "0,2", "target": "0,4", "push": "0,5", "custom": 10},
}
FAR_A, FAR_B, FAR_C = "6,8", "5,8", "4,8"   # relegation, distance >= 6 du caster


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _runner_id() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _move(rid: int, unit: int, to: str) -> None:
    _run(["act", "move", "--unit", str(unit), "--to", to,
          "--state-file", str(STATE), "--runner", str(rid)])


def _units(rid: int) -> dict:
    """{visualId: (id, (col,row))} -- les ids ne sont PAS hardcodes, ils sont relus."""
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = (u.get("id"), (p.get("col"), p.get("row")))
    return out


def build(hp_target: int) -> tuple[int, dict]:
    _run(["build", "--seed", str(SEED), "--board", BOARD,
          "--hp-target", str(hp_target),
          "--p-units", "%s,%s" % (CASTER_VIS, ALLY_VIS),
          "--a-units", "%s,%s" % (TARGET_VIS, IMMOVABLE_VIS),
          "--state-file", str(STATE)])
    rid = _runner_id()
    ids = {v: i for v, (i, _p) in _units(rid).items()}
    place(rid, ids, "a")
    return rid, ids


def place(rid: int, ids: dict, geom: str) -> None:
    """Pose la geometrie `geom` : caster + cible sur leurs tuiles EXACTES, les appats au loin.

    Un `act move` est borne par la portee de deplacement : une relegation lointaine n'atterrit pas
    forcement sur la tuile demandee. Les tuiles STRUCTURANTES (caster, cible, et l'appat quand il
    bouche l'arc) sont donc verifiees a l'EGALITE ; les relegations, elles, seulement par une
    distance minimale aux tuiles du montage -- ce qui est exactement ce dont elles ont besoin."""
    g = GEOMS[geom]
    for unit, to in ((ids[IMMOVABLE_VIS], FAR_A), (ids[ALLY_VIS], FAR_B),
                     (ids[CASTER_VIS], g["caster"]), (ids[TARGET_VIS], g["target"])):
        _move(rid, unit, to)
    _assert_exact(rid, ((ids[CASTER_VIS], g["caster"]), (ids[TARGET_VIS], g["target"])))
    _assert_far(rid, (ids[IMMOVABLE_VIS], ids[ALLY_VIS]),
                (g["caster"], g["target"], g["push"]))


def _tile(s: str) -> tuple:
    c, r = s.split(",")
    return (int(c), int(r))


def _assert_exact(rid: int, want) -> None:
    """Un `act move` REFUSE ne leve rien : le montage se degraderait SILENCIEUSEMENT en deux bras
    identiques, ou l'accord moteur<->natif serait trivialement vrai (cf. probe_27_4)."""
    pos = {i: p for _v, (i, p) in _units(rid).items()}
    bad = [(u, to, pos.get(u)) for u, to in want if pos.get(u) != _tile(to)]
    if bad:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %s"
                         % ["u%s voulu=%s obtenu=%s" % (u, to, got) for u, to, got in bad])


def _assert_far(rid: int, units, tiles, mind: int = 3) -> None:
    """Les appats relegues doivent etre a >= `mind` hex de TOUTES les tuiles du montage : sinon ils
    entrent dans un voisinage et deviennent un confond silencieux."""
    import hexgeo
    pos = {i: p for _v, (i, p) in _units(rid).items()}
    bad = []
    for u in units:
        p = pos.get(u)
        for t in tiles:
            if p is None or hexgeo.distance(p, _tile(t)) < mind:
                bad.append((u, p, t))
    if bad:
        raise SystemExit("relegation INSUFFISANTE (confond possible) : %s" % bad)


def _native(rid: int, caster: int, targets: list) -> tuple[dict, tuple, list]:
    pairs = {}
    for tgt in targets:
        for ab in (69, 1004):
            r = L._rpc("pairUtility", [{"runnerId": rid, "unitId": caster,
                                        "targetId": tgt, "abilityType": ab}])
            pairs[(ab, tgt)] = r.get("utility")
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    chosen, msgs = (None, None), []
    for u in (dr.get("units") or []):
        if u.get("unitId") != caster:
            continue
        msgs = u.get("proposed") or []
        for m in msgs:
            if m.get("cls") in ("ActiveAbilityMessage", "NormalAttackMessage"):
                chosen = (m.get("abilityType"), m.get("targetId"))
    return pairs, chosen, msgs


def _engine(rid: int, caster: int, targets: list):
    """Decision MOTEUR, puis avec le custom 1004 FORCE a 0 (test de NECESSITE)."""
    import engine_validate as EV
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX

    sid = L.INV._session_id()

    def rpc(m, b, t):
        return EV._r(sid, m, b, t)

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)

    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, caster, wt, predictor)
    mp = (ctx.me or {}).get("pos") or {}
    here = (mp.get("col"), mp.get("row"))
    pb = PB.REGISTRY.get(1004)
    customs = {t: pb.calculate_custom_utility(ctx, here, t, 1004) for t in targets}

    a = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    orig = type(pb).calculate_custom_utility
    type(pb).calculate_custom_utility = (
        lambda self, ctx, tile, target, ability_id: 0.0)
    try:
        b = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig
    return ((a.get("ability"), a.get("target")),
            (b.get("ability"), b.get("target")), customs)


def measure(rid: int, ids: dict, label: str, engine: bool, target_vis: str) -> dict:
    caster = ids[CASTER_VIS]
    tgt = ids[target_vis]
    pos = {i: p for _v, (i, p) in _units(rid).items()}
    pairs, chosen, msgs = _native(rid, caster, [tgt])
    gap = (pairs[(69, tgt)] + 1.0) - pairs[(1004, tgt)]
    print("  --- %s ---" % label)
    print("      positions : caster=%s cible=u%d%s ally=%s"
          % (pos.get(caster), tgt, pos.get(tgt), pos.get(ids[ALLY_VIS])))
    print("      pair69=%-22r pair1004=%-22r  ecart(pair69+1-pair1004)=%.6f"
          % (pairs[(69, tgt)], pairs[(1004, tgt)], gap))
    print("      natif  : ability=%s target=%s  (messages=%s)"
          % (chosen[0], chosen[1], [m.get("cls") for m in msgs]))
    row = {"pairs": {"%d,%d" % k: v for k, v in pairs.items()}, "native": chosen, "gap": gap,
           "target": tgt}
    if engine:
        eng, eng0, customs = _engine(rid, caster, [tgt])
        print("      moteur : ability=%s target=%s | custom(u%d)=%s"
              % (eng[0], eng[1], tgt, customs.get(tgt)))
        print("      moteur [custom 1004 force a 0] : ability=%s target=%s" % eng0)
        row.update({"engine": eng, "engine0": eng0, "custom": customs.get(tgt)})
    return row


def main() -> int:
    argv = sys.argv[1:]
    engine = "--engine" in argv
    hp = int(next((a.split("=", 1)[1] for a in argv if a.startswith("--hp-target=")),
                  HP_TARGET))
    if "--build" in argv or "--calib" in argv:
        rid, ids = build(hp)
    else:
        rid = _runner_id()
        ids = {v: i for v, (i, _p) in _units(rid).items()}
    print("runner=%d board=%s seed=%d hp-target=%d  caster=%s(%d)"
          % (rid, BOARD, SEED, hp, CASTER_VIS, ids[CASTER_VIS]))
    if "--calib" in argv:
        measure(rid, ids, "calibration (geom a, arc libre)", False, TARGET_VIS)
        print("(vise ecart dans (10, 20) ; ajuste --hp-target puis relance)")
        return 0

    rows = {}
    for g in ("a", "b"):
        place(rid, ids, g)
        rows[g + "-libre"] = measure(
            rid, ids, "geom %s LIBRE  -> custom attendu %d" % (g.upper(), GEOMS[g]["custom"]),
            engine, TARGET_VIS)
        _move(rid, ids[ALLY_VIS], GEOMS[g]["push"])
        _assert_exact(rid, ((ids[ALLY_VIS], GEOMS[g]["push"]),))   # le levier DOIT avoir mordu
        rows[g + "-bloque"] = measure(
            rid, ids, "geom %s BLOQUE -> custom attendu 0" % g.upper(), engine, TARGET_VIS)
        _move(rid, ids[ALLY_VIS], FAR_B)
    # CONTROLE `IsDisplaceable` : la cible deplacable degage, l'unite `BigTarget` prend la tuile
    # (0,3) de la geom A. Meme geometrie, meme arc -- seul le TRAIT de la cible change.
    place(rid, ids, "a")
    _move(rid, ids[TARGET_VIS], FAR_C)
    _move(rid, ids[IMMOVABLE_VIS], GEOMS["a"]["target"])
    rows["bigtarget"] = measure(
        rid, ids, "geom A, cible BigTarget (arc LIBRE) -> custom attendu 0", engine,
        IMMOVABLE_VIS)

    print("\n=== SYNTHESE ===")
    ref = rows["a-libre"]["pairs"]
    same = all(rows[k]["pairs"] == ref for k in ("a-bloque", "b-libre", "b-bloque"))
    print("  pair69/pair1004 bit-identiques sur les 4 bras a cible DEPLACABLE : %s"
          % ("OUI -- confond de prediction NUL" if same else "NON -- confond present"))
    ok = True
    want = {"a-libre": 1004, "a-bloque": 69, "b-libre": 69, "b-bloque": 69, "bigtarget": 69}
    for k in ("a-libre", "a-bloque", "b-libre", "b-bloque", "bigtarget"):
        got_ab, got_tgt = rows[k]["native"]
        good = (got_ab == want[k])
        print("  %-10s : natif -> ability=%s (attendu %s) %s"
              % (k, got_ab, want[k], "OK" if good else "HORS SCENARIO"))
        if engine:
            e_ab, e_tgt = rows[k]["engine"]
            agree = (e_ab == got_ab and e_tgt == got_tgt)
            ok = ok and agree
            print("               moteur -> ability=%s target=%s %s | custom=%s"
                  % (e_ab, e_tgt, "MATCH" if agree else "DIVERGE", rows[k]["custom"]))
            print("               moteur [custom=0] -> ability=%s target=%s" % rows[k]["engine0"])
    gap = rows["a-libre"]["gap"]
    disc = (rows["a-libre"]["native"][0] == 1004 and rows["b-libre"]["native"][0] == 69)
    print("  MAGNITUDE : geom A (20) bascule ET geom B (10) ne bascule PAS : %s"
          % ("PROUVEE -- une magnitude <= %.4f est exclue, une magnitude >= %.4f aussi"
             % (gap, gap) if disc else "NON ETABLIE (ecart=%.4f hors (10,20) ?)" % gap))
    if disc:
        print("            encadrement 100%% natif : %.4f < custom(geom A) et"
              " custom(geom B) < %.4f" % (gap, gap))
    print("(pense a disposer le runner : disposeRunner)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
