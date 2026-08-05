"""Probe #449-r2-r4 -- le spread de degat SUIT-IL `BattleConfiguration.Damage.DamageSpreadPercentage` ?

QUESTION BINAIRE. Le port codait `spread_pct = 20` en dur. Le natif lit le champ dans la BC
(`IdunBattle.Core.Services.DamageCalculations$$get_DamageSpreadPercentageFix64` -> `configuration
+0x20`, ou `configuration` = `BattleConfiguration.Damage` pose par `$$Init` depuis
`IdunBattle.Runner.IdunRunner$$Initialize`). Une BC portant une AUTRE valeur ferait-elle diverger
le port du natif -- et de combien ?

MONTAGE. On ECRIT la BC : chaque bras part d'une copie de `data/seed-bc.json` dont la seule
difference est la section `Damage`. Meme seed, meme board, memes unites, memes placements ->
la BASE de degat est identique d'un bras a l'autre, seule la VARIANCE change.

    bc20     : la seed telle quelle (DamageSpreadPercentage = 20)
    bcNN     : DamageSpreadPercentage = <--pct> (defaut 60 -- franchement eloigne de 20)
    absent   : le champ RETIRE           -> le natif a-t-il un defaut, et lequel ?
    ignore   : IgnoreDamageSpread = true -> le SECOND aiguillage vers la branche plate
                                            (`$$get_IgnoreDamageSpread` -> `configuration+0x31`)

DECOMPOSITION PAR ETAGE (jamais un scalaire fitte). Pour chaque bras :

  etage NATIF   : `aiPredict` publie les bornes PRE-armure du coup (healthDmgMin/Max). Elles
                  sortent de `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64` :
                      min = CalculateMinDamage(base) = base - Round(base * pct/100)
                      max = CalculateMaxDamage(base) + extraMax
                  L'IDENTIFICATION de l'etage est VERIFIEE, pas supposee : on exige
                  `min + max` CONSTANT a travers les bras (meme base, meme extraMax) ET
                  `max - min == 2 * Round(base * pct/100) + extraMax` avec le pct DE LA BC.
                  Si ces deux identites ne tiennent pas, le probe REFUSE de conclure.

  etage PORT    : le pct que le port utiliserait pour CETTE bataille, obtenu par le CANAL REEL
                  (`load_state(damage_config=<section Damage du bras>)` -> `State` ->
                  `Runner.install_default_handlers()` -> `DamageHandler.spread_pct`), et le
                  MUTANT `#449-r2-r4` (le port d'AVANT : 20 en dur) pour chiffrer l'ecart.

  face COMBAT   : l'attaque est APPLIQUEE, encadree par `dumpRng`. Le degat inflige est
                  reproduit depuis l'etat MT en rejouant `Next(min, max+1)` -- une fois avec les
                  bornes de la BC, une fois avec les bornes a 20. Le PRNG est le MEME dans les
                  deux modeles (meme etat de depart) : ce qui change est la BORNE, pas la
                  sequence. On EXIGE que les deux modeles different (sinon regime DEGENERE, et
                  l'accord ne prouverait rien).

Usage :
    python probe_449r2r4_spread_from_bc.py [--pct 60] [--seed 777] [--keep]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from rl_collect_batch import _rpc, _resolve_session

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
LOGS = ROOT / "logs"
SEED_BC = ROOT / "data" / "seed-bc.json"

BOARD = "MC1_67"
# Montage adjacent PILOTE (on DEPLACE, on ne subit pas la geometrie de spawn) : (2,5) et (2,6)
# sont voisins ET marchables sur MC1_67 (montage repris de probe_216_savage_prediction).
ATT_TILE, TGT_TILE = "2,5", "2,6"
P_UNITS = "ultraCalgar,ultraApothecary"
A_UNITS = "tauCrisis,blackTerminator"
ATT_VIS, TGT_VIS = "ultraCalgar", "tauCrisis"


def _unwrap(r):
    return r["result"] if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=120):
    return _unwrap(_rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


# ------------------------------------------------------------------ ecriture des BC des bras
def write_bc(path: Path, mutate) -> dict:
    """Copie `data/seed-bc.json` dont SEULE la section `Damage` differe. Rend la section ecrite."""
    bc = json.loads(SEED_BC.read_text(encoding="utf-8"))
    mutate(bc["Damage"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bc), encoding="utf-8")
    return bc["Damage"]


def arms(pct: int):
    """Les quatre bras, chacun = (nom, mutation de `BC.Damage`)."""
    return [
        ("bc20", lambda d: None),
        ("bc%d" % pct, lambda d, p=pct: d.__setitem__("DamageSpreadPercentage", p)),
        ("absent", lambda d: d.pop("DamageSpreadPercentage", None)),
        ("ignore", lambda d: d.__setitem__("IgnoreDamageSpread", True)),
    ]


# ------------------------------------------------------------------ runner
def build(state_file: Path, seed: int, bc_path: Path) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", BOARD,
           "--seed-bc", str(bc_path), "--p-units", P_UNITS, "--a-units", A_UNITS,
           "--place", "%s:%s" % (ATT_VIS, ATT_TILE),
           "--a-place", "%s:%s" % (TGT_VIS, TGT_TILE),
           # cible increvable ET SANS ARMURE (`--hp-target` met Armor/FixedArmor a 0) : le degat
           # inflige EST le tirage brut, donc la face COMBAT se lit sans etage de reduction.
           "--hp-target", "900000",
           "--crit", "0,0", "--crit-target", "0,0",
           "--block-target", "0,0", "--block-player", "0,0",
           "--state-file", str(state_file)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    try:
        st = json.loads(state_file.read_text(encoding="utf-8"))
    except OSError:
        raise RuntimeError("build KO:\n%s" % ((p.stderr or p.stdout or "")[-2500:],))
    rid = st.get("runnerId")
    if rid is None:
        raise RuntimeError("build sans runnerId:\n%s" % ((p.stderr or p.stdout or "")[-2500:],))
    return int(rid)


def dispose(state_file: Path, rid: int):
    subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(state_file),
                    "--runner", str(rid)], cwd=str(PYDIR),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


# ------------------------------------------------------------------ mesure d'un bras
def measure(sid, rid, bc_damage: dict) -> dict:
    """Bornes NATIVES du coup + pct que le PORT utiliserait, pour CE bras."""
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 3, "allAbilities": True}, 120)
    cur = dv.get("currentPlayer")
    units = {u["id"]: u for u in (dv.get("units") or [])}
    att = next((u for u in units.values()
                if u.get("visualId") == ATT_VIS and u.get("alive")), None)
    tgt = next((u for u in units.values()
                if u.get("visualId") == TGT_VIS and u.get("alive")), None)
    if att is None or tgt is None:
        raise RuntimeError("montage KO: attaquant/cible absents (%s/%s)" % (ATT_VIS, TGT_VIS))
    if att.get("owner") != cur:
        raise RuntimeError("ce n'est pas le tour du camp de l'attaquant (owner=%s cur=%s)"
                           % (att.get("owner"), cur))
    norm = next((a for a in (att.get("abilities") or []) if a.get("kind") == "normal"), None)
    if norm is None:
        raise RuntimeError("aucune ability `normal` sur %s" % ATT_VIS)

    ap = rpc(sid, "aiPredict", {"runnerId": rid, "unitId": att["id"], "targetId": tgt["id"],
                                "abilityType": norm["id"]}, 90)
    if not _ok(ap) or not ap.get("pred"):
        raise RuntimeError("aiPredict KO: %s" % (str(ap)[:200],))
    pred = ap["pred"]

    # Le pct que le PORT utiliserait pour CETTE bataille, par le CANAL REEL (pas une relecture
    # du JSON) : BC -> load_state -> State -> Runner -> DamageHandler.
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    st = load_state(dv, ob if isinstance(ob, dict) else {}, damage_config=bc_damage)
    port_pct = Runner(st).install_default_handlers().damage_handler.spread_pct

    return {"att": att["id"], "tgt": tgt["id"], "ability": norm["id"],
            "min": int(pred.get("healthDmgMin") or 0), "max": int(pred.get("healthDmgMax") or 0),
            "hits": int(pred.get("appliedHits") or 0),
            "might_crit": bool(pred.get("mightCrit")),
            "shield": int(pred.get("shieldBefore") or 0),
            "hp_before": int(pred.get("hpBefore") or 0),
            "port_pct": int(port_pct),
            "bc_pct": bc_damage.get("DamageSpreadPercentage"),
            "bc_ignore": bool(bc_damage.get("IgnoreDamageSpread") or False)}


def apply_attack(sid, rid, m: dict) -> dict:
    """Applique l'attaque, encadree par `dumpRng` -> etat MT avant + degat reellement inflige."""
    s1 = rpc(sid, "dumpRng", {"runnerId": rid}, 40)
    if not _ok(s1):
        return {"skip": "dumpRng indispo: %s" % (str(s1)[:160],)}
    res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": m["att"], "targetId": m["tgt"],
        "abilityType": m["ability"]}}, 60)
    if not _ok(res):
        return {"skip": "applyAction KO: %s" % (str(res)[:160],)}
    ar = (res.get("actions") or [{}])[0]
    if not ar.get("ok"):
        return {"skip": "cast refuse (portee ?): %s" % (str(ar)[:160],)}
    hp_after = next((u.get("hp") for u in (res.get("units") or [])
                     if u.get("squadId") == m["tgt"]), None)
    if hp_after is None:
        return {"skip": "hp de la cible absent du retour applyAction"}
    return {"mt": s1["mt"], "mti": s1["mti"], "actual": m["hp_before"] - int(hp_after)}


def roll_from(mt_state, mti, lo, hi) -> int:
    """Rejoue `Next(lo, hi+1)` depuis l'etat MT donne (mirror `RandomlyResolveMinMaxDamage`)."""
    from engine.runner.prng import IntBasedMersenneTwister
    mt = IntBasedMersenneTwister()
    mt.mt = list(mt_state)
    mt.mti = mti
    return lo + mt.next_internal(0, hi - lo + 1)


# ------------------------------------------------------------------ verdicts
def expected_spread(base: int, pct: int) -> int:
    """`IdunBattle.Core.Services.DamageCalculations$$CalculateDamageSpread` -- arithmetique Fix64."""
    from engine.services.damage_calculations import calculate_damage_spread
    return calculate_damage_spread(base, pct)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pct", type=int, default=60,
                    help="valeur DISCRIMINANTE ecrite dans BC.Damage.DamageSpreadPercentage")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--keep", action="store_true", help="ne pas disposer les runners")
    a = ap.parse_args()

    sid = _resolve_session()
    rows = []
    combat = {}
    for name, mut in arms(a.pct):
        bcp = LOGS / ("bc_449r2r4_%s.json" % name)
        section = write_bc(bcp, mut)
        sf = LOGS / ("rs_449r2r4_%s.json" % name)
        rid = build(sf, a.seed, bcp)
        try:
            m = measure(sid, rid, section)
            m["arm"] = name
            rows.append(m)
            print("[%s] runner=%d BC.pct=%r ignore=%s -> natif [%d, %d] hits=%d | port_pct=%d"
                  % (name, rid, m["bc_pct"], m["bc_ignore"], m["min"], m["max"], m["hits"],
                     m["port_pct"]))
            if name in ("bc20", "bc%d" % a.pct):
                combat[name] = apply_attack(sid, rid, m)
                print("     face COMBAT: %s" % (combat[name].get("skip")
                                                or ("degat inflige = %d" % combat[name]["actual"])))
        finally:
            if not a.keep:
                dispose(sf, rid)

    print("=== ETAGE 1 -- IDENTIFICATION (le probe refuse de conclure si ca ne tient pas) ===")
    sums = {r["arm"]: r["min"] + r["max"] for r in rows}
    print("  min+max par bras : %s" % (sums,))
    base_ref = None
    if len(set(sums.values())) == 1:
        base_ref = list(sums.values())[0] // 2
        print("  CONSTANT -> meme base de degat dans tous les bras ; base = (min+max)/2 = %d"
              % base_ref)
    else:
        print("  NON CONSTANT -> la base a bouge entre les bras : l'ecart de bornes n'est PAS")
        print("  imputable au seul spread. VERDICT INDETERMINE.")
        return 2

    print("=== ETAGE 2 -- le natif SUIT-IL le champ de la BC ? ===")
    verdict = 0
    for r in rows:
        pct_bc = 0 if (r["bc_ignore"] or r["bc_pct"] is None) else int(r["bc_pct"])
        att = expected_spread(base_ref, pct_bc)
        obs = (r["max"] - r["min"]) // 2
        tag = "OK" if obs == att else "ECART"
        print("  %-8s BC.pct=%-4s ignore=%-5s -> demi-amplitude natif=%-6d attendu(BC)=%-6d %s"
              % (r["arm"], r["bc_pct"], r["bc_ignore"], obs, att, tag))
        if obs != att:
            verdict = 1

    print("=== ETAGE 3 -- le PORT suit-il, et de combien le litteral 20 se trompait-il ? ===")
    for r in rows:
        pct_bc = 0 if (r["bc_ignore"] or r["bc_pct"] is None) else int(r["bc_pct"])
        mut20 = expected_spread(base_ref, 20)
        att = expected_spread(base_ref, pct_bc)
        print("  %-8s port_pct=%-4d (attendu %-4d) | demi-amplitude portee=%-6d "
              "mutant `20 en dur`=%-6d ecart=%d"
              % (r["arm"], r["port_pct"], pct_bc, expected_spread(base_ref, r["port_pct"]),
                 mut20, abs(mut20 - att)))
        if r["port_pct"] != pct_bc:
            verdict = 1

    print("=== ETAGE 4 -- face COMBAT (degat REELLEMENT inflige, PRNG rejoue) ===")
    for name, c in combat.items():
        if c.get("skip"):
            print("  %-8s NON CONFRONTE : %s" % (name, c["skip"]))
            continue
        r = next(x for x in rows if x["arm"] == name)
        pct_bc = 0 if (r["bc_ignore"] or r["bc_pct"] is None) else int(r["bc_pct"])
        d_bc, d20 = expected_spread(base_ref, pct_bc), expected_spread(base_ref, 20)
        roll_bc = roll_from(c["mt"], c["mti"], base_ref - d_bc, base_ref + d_bc)
        roll_20 = roll_from(c["mt"], c["mti"], base_ref - d20, base_ref + d20)
        deg = " [REGIME DEGENERE -- les deux modeles coincident, l'accord ne prouve rien]" \
            if roll_bc == roll_20 else ""
        print("  %-8s inflige=%-7d | modele BC=%-7d | modele `20 en dur`=%-7d ecart=%d%s"
              % (name, c["actual"], roll_bc, roll_20, abs(roll_bc - roll_20), deg))
        if c["actual"] != roll_bc:
            verdict = 1

    print("=== VERDICT === %s" % ("VERT" if verdict == 0 else "ROUGE"))
    return verdict


if __name__ == "__main__":
    raise SystemExit(main())
