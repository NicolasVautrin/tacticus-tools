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
                  L'IDENTIFICATION de l'etage est VERIFIEE, pas supposee : on exige que le
                  CENTRE `(min+max)/2` soit le MEME dans tous les bras (a l'arrondi de borne
                  pres : chaque borne est materialisee independamment) ET que la demi-amplitude
                  vaille `centre * pct/100` avec le pct DE LA BC. Si ces identites ne tiennent
                  pas, le probe REFUSE de conclure. Le centre n'est PAS suppose egal a la stat
                  Attack : `aiPredict` publie du degat DEJA reduit -- ce qu'on identifie ici est
                  le RAPPORT amplitude/centre, qui est exactement le champ cherche.

  etage PORT    : le pct que le port utiliserait pour CETTE bataille, obtenu par le CANAL REEL
                  (`load_state(damage_config=<section Damage du bras>)` -> `State` ->
                  `Runner.install_default_handlers()` -> `DamageHandler.spread_pct`).

  face COMBAT   : REPLAY-DIFF complet (meme montage que
                  `tests/engine/runner/test_runner_attack_live.py`) -- le runner PYTHON rejoue
                  l'attaque depuis son ECS avec `state.rng` cale sur le MT live (`dumpRng`),
                  DEUX FOIS : une avec le pct LU de la BC, une avec le MUTANT `#449-r2-r4`
                  (20 en dur, le port d'AVANT). Le PRNG est le MEME dans les deux bras : ce qui
                  change est la BORNE, pas la sequence. On EXIGE que les deux modeles DIFFERENT
                  (sinon regime DEGENERE, et l'accord ne prouverait rien).

Usage :
    python probe_449r2r4_spread_from_bc.py [--pct 60] [--seed 777] [--keep]
    python probe_449r2r4_spread_from_bc.py --pct 90 --seed 31337 --tag g90
    python probe_449r2r4_spread_from_bc.py --pct 5  --seed 123   --tag g5

Le montage est ENTIEREMENT parametre (`--board`, `--p-units`/`--a-units`, `--att`/`--tgt`,
`--att-tile`/`--tgt-tile`) : la generalisation se fait en le CHANGEANT, jamais en re-jouant le
meme point. `--tag` isole les fichiers `logs/` de deux runs concurrents.

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

# Montage PAR DEFAUT. Tuiles PILOTEES (on DEPLACE, on ne subit pas la geometrie de spawn) :
# (2,5) et (2,6) sont voisins ET marchables sur MC1_67 (repris de probe_216_savage_prediction).
# Tout est surchargeable en ligne de commande -- la generalisation se fait en CHANGEANT board,
# unites, tuiles et pct, pas en re-jouant le meme point.
BOARD = "MC1_67"
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
def _pick(sid, rid):
    """(decisionView, attaquant, cible, ability normale) du montage -- deterministe."""
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 3, "allAbilities": True}, 120)
    cur = dv.get("currentPlayer")
    units = list((dv.get("units") or []))
    att = next((u for u in units if u.get("visualId") == ATT_VIS and u.get("alive")), None)
    tgt = next((u for u in units if u.get("visualId") == TGT_VIS and u.get("alive")), None)
    if att is None or tgt is None:
        raise RuntimeError("montage KO: attaquant/cible absents (%s/%s)" % (ATT_VIS, TGT_VIS))
    if att.get("owner") != cur:
        raise RuntimeError("ce n'est pas le tour du camp de l'attaquant (owner=%s cur=%s)"
                           % (att.get("owner"), cur))
    norm = next((a for a in (att.get("abilities") or []) if a.get("kind") == "normal"), None)
    if norm is None:
        raise RuntimeError("aucune ability `normal` sur %s" % ATT_VIS)
    return dv, att, tgt, norm


def measure(sid, rid, bc_damage: dict) -> dict:
    """Bornes NATIVES du coup + pct que le PORT utiliserait + REPLAY-DIFF des deux modeles."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent

    dv, att, tgt, norm = _pick(sid, rid)
    ap = rpc(sid, "aiPredict", {"runnerId": rid, "unitId": att["id"], "targetId": tgt["id"],
                                "abilityType": norm["id"]}, 90)
    if not _ok(ap) or not ap.get("pred"):
        # `ok` SANS `pred` = le natif n'a rendu aucune prediction pour ce couple (typiquement
        # hors portee apres placement, ou `dictNull`). Ce n'est pas une panne du probe : c'est
        # un montage a corriger -- DEPLACER les unites, pas subir la geometrie.
        raise RuntimeError(
            "aiPredict n'a rendu AUCUNE prediction pour %s(%s) -> %s(%s) : montage a corriger "
            "(portee ? placement ?). ok=%s dictNull=%s pred=%s"
            % (ATT_VIS, att["id"], TGT_VIS, tgt["id"], ap.get("ok"), ap.get("dictNull"),
               ap.get("pred")))
    pred = ap["pred"]
    out = {"att": att["id"], "tgt": tgt["id"], "ability": norm["id"],
           "min": int(pred.get("healthDmgMin") or 0), "max": int(pred.get("healthDmgMax") or 0),
           "hits": int(pred.get("appliedHits") or 0),
           "might_crit": bool(pred.get("mightCrit")),
           "shield": int(pred.get("shieldBefore") or 0),
           "bc_pct": bc_damage.get("DamageSpreadPercentage"),
           "bc_ignore": bool(bc_damage.get("IgnoreDamageSpread") or False)}

    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    ob = ob if isinstance(ob, dict) else {}
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    snap = snap if _ok(snap) else None

    # Le pct que le PORT utiliserait pour CETTE bataille, par le CANAL REEL (pas une relecture
    # du JSON) : BC -> load_state -> State -> Runner -> DamageHandler.
    st_probe = load_state(dv, ob, snap, damage_config=bc_damage)
    out["port_pct"] = int(Runner(st_probe).install_default_handlers().damage_handler.spread_pct)

    # --- REPLAY-DIFF : deux runners offline partant du MEME etat MT, un par MODELE -------------
    s1 = rpc(sid, "dumpRng", {"runnerId": rid}, 40)
    if snap is None or not _ok(s1):
        out["combat_skip"] = "combatSnapshot/dumpRng indisponible"
        return out

    def _off(spread_arg):
        st = load_state(dv, ob, snap, damage_config=bc_damage)
        te = st.get_entity(tgt["id"])
        hc = te.get_component(HealthComponent) if te is not None else None
        if hc is None or hc.hp is None:
            return None, None
        hp0 = int(hc.hp)                    # AVANT l'apply -- `hc.hp` est MUTE par le pipeline
        rng = IntBasedMersenneTwister()
        rng.mt = list(s1["mt"])
        rng.mti = s1["mti"]
        st.rng = rng
        r = Runner(st).install_default_handlers(spread_arg)
        r.apply(AttackUnitMessage(att["id"], tgt["id"]))
        last = r.damage_handler.last
        return (None if last is None else int(last["total"])), hp0

    off_bc, hp_before = _off(None)          # le port CORRIGE : pct LU de la BC
    off_20, _ = _off(20)                    # le MUTANT #449-r2-r4 : 20 en dur
    res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att["id"], "targetId": tgt["id"],
        "abilityType": norm["id"]}}, 60)
    if not _ok(res) or not (res.get("actions") or [{}])[0].get("ok"):
        out["combat_skip"] = "cast refuse: %s" % (str(res)[:160],)
        return out
    hp_after = next((u.get("hp") for u in (res.get("units") or [])
                     if u.get("squadId") == tgt["id"]), None)
    if hp_after is None or hp_before is None:
        out["combat_skip"] = "hp de la cible indisponible"
        return out
    out.update({"live_dmg": int(hp_before) - int(hp_after), "off_bc": off_bc, "off_20": off_20})
    return out


# ------------------------------------------------------------------ verdicts
def _effective_pct(r: dict) -> int:
    """Le pct que le NATIF doit appliquer pour ce bras, LU de la BC ecrite.

    Champ ABSENT -> 0 : `IdunBattle.Configuration.DamageConfiguration$$.ctor` n'initialise QUE le
    `Dictionary` `+0x40` (DamageProfiles), donc un champ absent du JSON reste a la valeur par
    defaut de son type C#. `IgnoreDamageSpread` -> 0 : second aiguillage vers la branche plate de
    `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` (`configuration+0x31`)."""
    if r["bc_ignore"] or r["bc_pct"] is None:
        return 0
    return int(r["bc_pct"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pct", type=int, default=60,
                    help="valeur DISCRIMINANTE ecrite dans BC.Damage.DamageSpreadPercentage")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--p-units", dest="p_units", default=P_UNITS)
    ap.add_argument("--a-units", dest="a_units", default=A_UNITS)
    ap.add_argument("--att", default=ATT_VIS, help="visualId de l'attaquant (dans --p-units)")
    ap.add_argument("--tgt", default=TGT_VIS, help="visualId de la cible (dans --a-units)")
    ap.add_argument("--att-tile", dest="att_tile", default=ATT_TILE)
    ap.add_argument("--tgt-tile", dest="tgt_tile", default=TGT_TILE)
    ap.add_argument("--tag", default="", help="suffixe des fichiers logs/ (runs concurrents)")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer les runners")
    a = ap.parse_args()

    # Le montage est un PARAMETRE, pas une constante : la generalisation se fait en changeant
    # board/unites/tuiles/pct, jamais en re-jouant le meme point.
    globals().update(BOARD=a.board, P_UNITS=a.p_units, A_UNITS=a.a_units,
                     ATT_VIS=a.att, TGT_VIS=a.tgt, ATT_TILE=a.att_tile, TGT_TILE=a.tgt_tile)
    suffix = ("_" + a.tag) if a.tag else ""

    sid = _resolve_session()
    rows = []
    for name, mut in arms(a.pct):
        bcp = LOGS / ("bc_449r2r4_%s%s.json" % (name, suffix))
        section = write_bc(bcp, mut)
        sf = LOGS / ("rs_449r2r4_%s%s.json" % (name, suffix))
        rid = build(sf, a.seed, bcp)
        try:
            m = measure(sid, rid, section)
            m["arm"] = name
            rows.append(m)
            print("[%s] runner=%d BC.pct=%r ignore=%s -> natif [%d, %d] hits=%d | port_pct=%d"
                  % (name, rid, m["bc_pct"], m["bc_ignore"], m["min"], m["max"], m["hits"],
                     m["port_pct"]))
            print("     face COMBAT: %s"
                  % (m.get("combat_skip")
                     or ("live=%d  port(BC)=%s  port(mutant 20 en dur)=%s"
                         % (m["live_dmg"], m["off_bc"], m["off_20"]))))
        finally:
            if not a.keep:
                dispose(sf, rid)

    verdict = 0
    print("=== ETAGE 1 -- IDENTIFICATION (le probe refuse de conclure si ca ne tient pas) ===")
    centres = {r["arm"]: (r["min"] + r["max"]) / 2.0 for r in rows}
    print("  centre (min+max)/2 par bras : %s" % ({k: round(v, 1) for k, v in centres.items()},))
    lo, hi = min(centres.values()), max(centres.values())
    if hi - lo > 2.0:
        print("  NON CONSTANT (ecart %.1f > 2) -> la base a bouge entre les bras : l'ecart de"
              % (hi - lo,))
        print("  bornes n'est PAS imputable au seul spread. VERDICT INDETERMINE.")
        return 2
    centre = (lo + hi) / 2.0
    print("  CONSTANT a +-1 de materialisation de borne -> meme base ; centre = %.1f" % centre)

    print("=== ETAGE 2 -- le NATIF suit-il le champ de la BC ? ===")
    for r in rows:
        pct_bc = _effective_pct(r)
        att = centre * pct_bc / 100.0
        obs = (r["max"] - r["min"]) / 2.0
        ok = abs(obs - att) <= 1.5          # <=1 par borne materialisee independamment
        tag = "OK" if ok else "ECART"
        print("  %-8s BC.pct=%-5s ignore=%-5s -> demi-amplitude natif=%-8.1f attendu(BC)=%-8.1f %s"
              % (r["arm"], r["bc_pct"], r["bc_ignore"], obs, att, tag))
        if not ok:
            verdict = 1

    print("=== ETAGE 3 -- le PORT lit-il le meme champ ? ===")
    for r in rows:
        pct_bc = _effective_pct(r)
        tag = "OK" if r["port_pct"] == pct_bc else "ECART"
        print("  %-8s port_pct=%-4d attendu=%-4d %s   (mutant `20 en dur` : %d)"
              % (r["arm"], r["port_pct"], pct_bc, tag, 20))
        if r["port_pct"] != pct_bc:
            verdict = 1

    print("=== ETAGE 4 -- face COMBAT (replay-diff, PRNG cale sur le MT live) ===")
    for r in rows:
        if r.get("combat_skip"):
            print("  %-8s NON CONFRONTE : %s" % (r["arm"], r["combat_skip"]))
            continue
        live, obc, o20 = r["live_dmg"], r["off_bc"], r["off_20"]
        deg = ""
        if obc == o20:
            deg = "  [REGIME DEGENERE -- les deux modeles coincident, l'accord ne prouve rien]"
        print("  %-8s live=%-8d port(BC)=%-8s port(mutant)=%-8s ecart_modeles=%s%s"
              % (r["arm"], live, obc, o20,
                 ("?" if obc is None or o20 is None else abs(obc - o20)), deg))
        if obc != live:
            verdict = 1

    print("=== VERDICT === %s" % ("VERT" if verdict == 0 else "ROUGE"))
    return verdict


if __name__ == "__main__":
    raise SystemExit(main())
