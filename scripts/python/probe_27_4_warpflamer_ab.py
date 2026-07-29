"""probe #27-4 -- A/B causal LIVE de HeavyWarpFlamer (1227) : le terme custom
`HeavyWarpFlamer_LikesAdjacentEnemies`, et surtout sa LINEARITE.

`IdunBattle.AI.Playbook.Loki.HeavyWarpFlamerPlaybook$$CalculateCustomUtility` vaut
`W * Count(GetAdjacentEnemies(target, caster))` -- c'est le MEME ensemble que le second terme de
`DoomSirenPlaybook` (ennemis du caster adjacents a la tuile de la CIBLE), mais MULTIPLIE par le
compte au lieu d'etre teste `> 0`. Un A/B a 0 vs 1 voisin ne saurait donc PAS distinguer ce port
d'un port booleen : le montage ci-dessous est calibre pour que **seul le passage de 1 a 2 voisins
bascule le natif**.

MONTAGE (board MC1_67, seed 909, stats NATURELLES -- ni --hp-target ni --armor-target) :
  caster thousSekhetar en (2,6) ; DEUX cibles legales a distance 2, non adjacentes entre elles :
    T_haut = orksWarboss en (2,8)  -- pair(1227) NATIVE la plus forte, reste ISOLEE
    T_bas  = tauCrisis   en (2,4)  -- pair(1227) plus faible, recoit les voisins
  appats : necroWarden -> (2,3) puis astraOrdnance -> (3,4). Les deux tuiles sont ADJACENTES a
  T_bas, a distance 3 du caster et 5 de T_haut : elles ne changent l'adjacence d'AUCUNE autre
  entite du montage.

  L'ecart de paire natif mesure `pair(1227,T_haut) - pair(1227,T_bas)` tombe dans (10, 20) :
    n=0 voisins -> le natif cible T_haut
    n=1 voisin  -> +10 ne suffit pas -> le natif cible ENCORE T_haut   (un port BOOLEEN dirait T_bas)
    n=2 voisins -> +20 suffit        -> le natif bascule sur T_bas
  => la LINEARITE est mesuree, pas supposee, et W est encadre : 10 < ecart < 20.

Le probe mesure dans CHAQUE bras les QUATRE `pairUtility` natives (2 abilities x 2 cibles) :
bit-identiques d'un bras a l'autre = confond de prediction MESURE et NUL (la prediction de 1227
est mono-cible, cf. `HeavyWarpFlamerPlaybook$$MakeDamagePredictions`).

Usage :
    python catalog_inject.py --units thousSekhetar --out <abs>/bc_warpflamer.json
    python probe_27_4_warpflamer_ab.py --build [--engine]
    python probe_27_4_warpflamer_ab.py --engine          # re-joue sur le runner du state-file
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
SEED_BC = LOGS / "bc_warpflamer.json"
STATE = LOGS / "rs_wf.json"
BOARD = "MC1_67"
SEED = 909

# ids stables du montage (ordre de spawn deterministe : p-units puis a-units)
CASTER = 85          # thousSekhetar
ALLY = 87            # ultraCalgar  -- controle « les ALLIES ne comptent pas »
T_LOW = 77           # tauCrisis      -- recoit les voisins
T_HIGH = 79          # orksWarboss    -- reste isolee
BAIT1, BAIT2 = 81, 83   # necroWarden, astraOrdnance

FAR1, FAR2, FAR3 = "6,0", "5,0", "4,0"

# Deux GEOMETRIES, l'une en colonne PAIRE l'autre en colonne IMPAIRE : la table de voisinage hex
# offset depend de la parite de la colonne (`hexgeo._NEIGHBORS_EVEN` / `_ODD`), donc les deux
# exercent des chemins DIFFERENTS de `battle_query.is_adjacent`. Dans les deux cas T_low et T_high
# sont a distance 2 du caster et a distance 4 l'une de l'autre, et les tuiles d'appat sont a
# distance 3 du caster et 5 de T_high (elles ne changent l'adjacence d'aucune autre entite).
GEOMS = {
    "a": {"caster": "2,6", "t_low": "2,4", "t_high": "2,8", "adj1": "2,3", "adj2": "3,4"},
    "b": {"caster": "3,5", "t_low": "3,3", "t_high": "3,7", "adj1": "3,2", "adj2": "4,2"},
}


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _runner_id() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _move(rid: int, unit: int, to: str) -> None:
    _run(["act", "move", "--unit", str(unit), "--to", to,
          "--state-file", str(STATE), "--runner", str(rid)])


def build(board: str, seed: int, g: dict) -> int:
    if not SEED_BC.exists():
        raise SystemExit(
            "seed BC augmentee absente : lancer d'abord\n"
            "  python catalog_inject.py --units thousSekhetar --out %s" % SEED_BC)
    _run(["build", "--seed", str(seed), "--board", board, "--seed-bc", str(SEED_BC),
          "--p-units", "thousSekhetar,ultraCalgar",
          "--a-units", "tauCrisis,orksWarboss,necroWarden,astraOrdnance",
          "--state-file", str(STATE)])
    rid = _runner_id()
    want = ((CASTER, g["caster"]), (T_LOW, g["t_low"]), (T_HIGH, g["t_high"]),
            (BAIT1, FAR1), (BAIT2, FAR2), (ALLY, FAR3))
    for unit, to in want:
        _move(rid, unit, to)
    _assert_placed(rid, want)
    return rid


def _assert_placed(rid: int, want) -> None:
    """Un `act move` REFUSE (tuile injouable/occupee sur ce board) ne leve rien : l'unite reste
    ou elle est et le montage se degrade SILENCIEUSEMENT en un scenario ou les trois bras sont
    identiques -- l'accord moteur<->natif y devient trivialement vrai. Mesure du 2026-07-30 sur
    `C2_02` : T_low restee en (0,7), appats jamais deplaces, 4/4 « MATCH » sans aucune valeur."""
    pos = _positions(rid)
    bad = [(u, to, pos.get(u)) for u, to in want
           if pos.get(u) != tuple(int(x) for x in to.split(","))]
    if bad:
        raise SystemExit(
            "placement REFUSE sur ce board -- montage invalide, pas de mesure : %s"
            % ["u%s voulu=%s obtenu=%s" % (u, to, got) for u, to, got in bad])


def _positions(rid: int) -> dict:
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("id")] = (p.get("col"), p.get("row"))
    return out


def _native(rid: int) -> tuple[dict, tuple, list]:
    pairs = {}
    for tgt in (T_LOW, T_HIGH):
        for ab in (69, 1227):
            r = L._rpc("pairUtility", [{"runnerId": rid, "unitId": CASTER,
                                        "targetId": tgt, "abilityType": ab}])
            pairs[(ab, tgt)] = r.get("utility")
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    chosen, msgs = (None, None), []
    for u in (dr.get("units") or []):
        if u.get("unitId") != CASTER:
            continue
        msgs = u.get("proposed") or []
        for m in msgs:
            if m.get("cls") == "ActiveAbilityMessage":
                chosen = (m.get("abilityType"), m.get("targetId"))
    return pairs, chosen, msgs


def _engine(rid: int) -> tuple[tuple, tuple, dict]:
    """Decision MOTEUR : telle quelle, puis avec le custom 1227 FORCE a 0 (test de NECESSITE).
    Rend ((ability, target), (ability0, target0), {tgt: custom})."""
    import engine_validate as EV
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX

    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)          # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)

    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, CASTER, wt, predictor)
    mp = (ctx.me or {}).get("pos") or {}
    here = (mp.get("col"), mp.get("row"))
    pb = PB.REGISTRY.get(1227)
    customs = {t: pb.calculate_custom_utility(ctx, here, t, 1227) for t in (T_LOW, T_HIGH)}

    a = EV.engine_decide(sid, rid, dv, mov_by_unit, CASTER, wt, predictor)
    orig = type(pb).calculate_custom_utility
    type(pb).calculate_custom_utility = (
        lambda self, ctx, tile, target, ability_id: 0.0)
    try:
        b = EV.engine_decide(sid, rid, dv, mov_by_unit, CASTER, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig
    return ((a.get("ability"), a.get("target")),
            (b.get("ability"), b.get("target")), customs)


def measure(rid: int, label: str, engine: bool) -> dict:
    pos = _positions(rid)
    pairs, chosen, msgs = _native(rid)
    print("  --- %s ---" % label)
    print("      positions : caster=%s T_low=%s T_high=%s bait1=%s bait2=%s ally=%s"
          % (pos.get(CASTER), pos.get(T_LOW), pos.get(T_HIGH),
             pos.get(BAIT1), pos.get(BAIT2), pos.get(ALLY)))
    for tgt, nm in ((T_LOW, "T_low "), (T_HIGH, "T_high")):
        print("      %s  pair69=%-20r pair1227=%-20r"
              % (nm, pairs[(69, tgt)], pairs[(1227, tgt)]))
    print("      ecart natif pair1227(T_high) - pair1227(T_low) = %.6f"
          % (pairs[(1227, T_HIGH)] - pairs[(1227, T_LOW)]))
    print("      natif  : ability=%s target=%s  (messages=%s)"
          % (chosen[0], chosen[1], [m.get("cls") for m in msgs]))
    row = {"pairs": pairs, "native": chosen}
    if engine:
        eng, eng0, customs = _engine(rid)
        print("      moteur : ability=%s target=%s | custom(T_low)=%s custom(T_high)=%s"
              % (eng[0], eng[1], customs[T_LOW], customs[T_HIGH]))
        print("      moteur [custom 1227 force a 0] : ability=%s target=%s" % eng0)
        row.update({"engine": eng, "engine0": eng0, "customs": customs})
    return row


def main() -> int:
    argv = sys.argv[1:]
    engine = "--engine" in argv
    board = next((a.split("=", 1)[1] for a in argv if a.startswith("--board=")), BOARD)
    seed = int(next((a.split("=", 1)[1] for a in argv if a.startswith("--seed=")), SEED))
    gname = next((a.split("=", 1)[1] for a in argv if a.startswith("--geom=")), "a")
    g = GEOMS[gname]
    rid = build(board, seed, g) if "--build" in argv else _runner_id()
    print("runner=%d board=%s seed=%d geom=%s (stats naturelles)"
          % (rid, board, seed, gname))
    rows = {}
    rows["n=0"] = measure(rid, "n=0 voisin  (appats loin)", engine)
    _move(rid, BAIT1, g["adj1"])
    rows["n=1"] = measure(rid, "n=1 voisin  (necroWarden adjacent a T_low)", engine)
    _move(rid, BAIT2, g["adj2"])
    rows["n=2"] = measure(rid, "n=2 voisins (astraOrdnance adjacent a T_low)", engine)
    # CONTROLE : le 2e voisin ENNEMI repart, un ALLIE prend sa place sur la MEME tuile.
    # `GetAdjacentEnemies` scope aux ennemis du joueur du caster -> le compte doit RETOMBER a 1
    # et le natif REVENIR sur T_high. Sans ce bras, un port qui compterait « unites adjacentes »
    # (slot `GetAdjacentUnits`, voisin immediat du bon slot dans la vtable) passerait inapercu.
    _move(rid, BAIT2, FAR2)
    _move(rid, ALLY, g["adj2"])
    rows["ally"] = measure(rid, "n=1 ennemi + 1 ALLIE adjacents a T_low (controle)", engine)

    print("\n=== SYNTHESE ===")
    # Sur un board/seed AUTRE que la reference, l'ecart de paire n'est plus garanti dans (10, 20) :
    # le scenario scripte devient INDICATIF et seul l'accord moteur<->natif fait foi.
    ref = (board == BOARD and seed == SEED)
    ok = True
    for k, want in (("n=0", T_HIGH), ("n=1", T_HIGH), ("n=2", T_LOW), ("ally", T_HIGH)):
        got_ab, got_tgt = rows[k]["native"]
        good = (got_tgt == want)
        ok = ok and (good or not ref)
        print("  %-5s : natif -> ability=%s target=%s (attendu target=%s) %s"
              % (k, got_ab, got_tgt, want,
                 ("OK" if good else "MISMATCH") if ref else
                 ("conforme" if good else "hors scenario (board non-reference)")))
        if engine:
            e_ab, e_tgt = rows[k]["engine"]
            agree = (e_ab == got_ab and e_tgt == got_tgt)
            ok = ok and agree
            print("          moteur -> ability=%s target=%s %s"
                  % (e_ab, e_tgt, "MATCH" if agree else "DIVERGE"))
    # LINEARITE : n=1 ne bascule PAS, n=2 bascule -> un terme booleen est EXCLU.
    lin = (rows["n=1"]["native"][1] == T_HIGH and rows["n=2"]["native"][1] == T_LOW)
    print("  linearite (n=1 ne bascule pas, n=2 bascule) : %s"
          % ("PROUVEE -- un terme booleen est exclu" if lin else "NON ETABLIE"))
    print("  allies ignores (bras `ally` revient sur T_high) : %s"
          % ("OUI" if rows["ally"]["native"][1] == T_HIGH else "NON"))
    if lin:
        gap = rows["n=2"]["pairs"][(1227, T_HIGH)] - rows["n=2"]["pairs"][(1227, T_LOW)]
        print("  encadrement du poids (forme lineaire W*n) : %.4f < W < %.4f"
              % (gap / 2.0, gap))
    print("(pense a disposer le runner : disposeRunner)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
