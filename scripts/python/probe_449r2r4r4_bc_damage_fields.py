"""#449-r2-r4-r4 -- CHIFFRAGE de l'ecart, champ par champ, sur `BattleConfiguration.Damage`.

La tranche parente `#449-r2-r4` a montre que `DamageSpreadPercentage` etait code en dur a 20 en
13 endroits, et l'a chiffre : a `pct = 60` le natif inflige 7774 la ou le port en dur calcule 9388.
Ce probe fait la MEME chose pour les autres champs de la meme section.

CE QU'IL MESURE, et pourquoi ce montage
---------------------------------------
Un bras = une copie de `data/seed-bc.json` dont SEULE la section `Damage` differe, passee au
runner par `rl_duel build --seed-bc`. On lit ensuite, sur le MEME couple attaquant/cible et la
MEME geometrie :

  * ce que le NATIF fait (degat live d'un cast reel, et bornes de `aiPredict`) ;
  * ce que le PORT calcule, par REPLAY-DIFF : un Runner offline reparti du MEME etat de Mersenne
    Twister (`dumpRng`), donc bit-comparable au live.

L'ecart entre bras EST le chiffrage : si le natif bouge quand le champ bouge et que le port ne
bouge pas, le port porte un litteral, et l'ampleur du decrochage est mesuree, pas estimee.

CHAMPS COUVERTS (`--field`)
---------------------------
`elevation` -- `BC.Damage.ElevationBonus` (`+0x10`,
  `IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier`). Le port le lit
  dans `engine/services/damage_modifiers.py::ELEVATION_BONUS_PCT`, mais depuis la SEED figee au
  chargement du module -- jamais depuis la BC de la bataille. Montage : attaquant RANGED place en
  SURPLOMB de la cible (le gate natif est `target.elev < attackTile.elev`), tuiles PILOTEES.

`knockback`  -- `BC.Damage.KnockbackPercentage` (`+0x24`,
  `IdunBattle.Core.Services.DamageCalculations$$get_KnockbackPercentageFix64`). Le port le code en
  dur (`engine/runner/operations/displace.py::_KNOCKBACK_PCT = 20`). Montage : push BLOQUE.

Le montage est PARAMETRE (board, unites, tuiles, valeur discriminante) : la generalisation se fait
en changeant ces parametres, jamais en re-jouant le meme point.

Usage :
    python probe_449r2r4r4_bc_damage_fields.py --field elevation
    python probe_449r2r4r4_bc_damage_fields.py --field elevation --value 100 --tag x1

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

# --- Montage ELEVATION -------------------------------------------------------------------
# Tuiles PILOTEES sur MC1_67, choisies en LISANT `data/boards/global/MC1_67.json` : (0,3) est a
# l'elevation 4, (0,5) a l'elevation 2, distance hex 2. Le gate natif du bonus est
# `target.elev < attackTile.elev` -- on le met donc en regime ACTIF par construction, on ne
# subit pas la geometrie de spawn.
ELEV_BOARD = "MC1_67"
ELEV_ATT_TILE, ELEV_TGT_TILE = "0,3", "0,5"
ELEV_P_UNITS = "necroDestroyer,ultraApothecary"
ELEV_A_UNITS = "ultraApothecary,tauCrisis"
ELEV_ATT_VIS, ELEV_TGT_VIS = "necroDestroyer", "ultraApothecary"

FIELDS = {
    "elevation": {
        "key": "ElevationBonus",
        "board": ELEV_BOARD, "att_tile": ELEV_ATT_TILE, "tgt_tile": ELEV_TGT_TILE,
        "p_units": ELEV_P_UNITS, "a_units": ELEV_A_UNITS,
        "att": ELEV_ATT_VIS, "tgt": ELEV_TGT_VIS,
        "default_value": 100,
        "port_symbol": "engine/services/damage_modifiers.py::ELEVATION_BONUS_PCT",
    },
}


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


def arms(key: str, value: int):
    """Trois bras : la seed telle quelle, une valeur DISCRIMINANTE, et le champ ABSENT.

    Le bras `absent` est le plus important : `IdunBattle.Configuration.DamageConfiguration$$.ctor`
    n'initialise QUE le `Dictionary` `+0x40`, donc un champ absent du JSON vaut **0** cote natif --
    jamais le litteral que le port ecrit en repli."""
    return [
        ("seed", lambda d: None),
        ("v%d" % value, lambda d, k=key, v=value: d.__setitem__(k, v)),
        ("absent", lambda d, k=key: d.pop(k, None)),
    ]


# ------------------------------------------------------------------ runner
def build(state_file: Path, seed: int, bc_path: Path, cfg: dict) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", cfg["board"],
           "--seed-bc", str(bc_path),
           "--p-units", cfg["p_units"], "--a-units", cfg["a_units"],
           "--place", "%s:%s" % (cfg["att"], cfg["att_tile"]),
           "--a-place", "%s:%s" % (cfg["tgt"], cfg["tgt_tile"]),
           # cible increvable ET SANS ARMURE (`--hp-target` met Armor/FixedArmor a 0) : le degat
           # inflige EST le tirage brut, donc l'etage mesure se lit sans reduction parasite.
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
def _pick(sid, rid, cfg):
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 3, "allAbilities": True}, 120)
    cur = dv.get("currentPlayer")
    units = list((dv.get("units") or []))
    att = next((u for u in units if u.get("visualId") == cfg["att"] and u.get("alive")), None)
    tgt = next((u for u in units
                if u.get("visualId") == cfg["tgt"] and u.get("alive") and u.get("owner") != cur),
               None)
    if att is None or tgt is None:
        raise RuntimeError("montage KO: attaquant/cible absents (%s/%s)" % (cfg["att"], cfg["tgt"]))
    if att.get("owner") != cur:
        raise RuntimeError("ce n'est pas le tour du camp de l'attaquant (owner=%s cur=%s)"
                           % (att.get("owner"), cur))
    norm = next((a for a in (att.get("abilities") or []) if a.get("kind") == "normal"), None)
    if norm is None:
        raise RuntimeError("aucune ability `normal` sur %s" % cfg["att"])
    return dv, att, tgt, norm


def measure(sid, rid, bc_damage: dict, cfg: dict) -> dict:
    """Bornes NATIVES + degat live + replay-diff du PORT sur le meme etat de PRNG."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent

    dv, att, tgt, norm = _pick(sid, rid, cfg)
    out = {"att": att["id"], "tgt": tgt["id"], "ability": norm["id"],
           "bc_value": bc_damage.get(cfg["key"])}

    ap = rpc(sid, "aiPredict", {"runnerId": rid, "unitId": att["id"], "targetId": tgt["id"],
                                "abilityType": norm["id"]}, 90)
    if _ok(ap) and ap.get("pred"):
        pred = ap["pred"]
        out.update({"min": int(pred.get("healthDmgMin") or 0),
                    "max": int(pred.get("healthDmgMax") or 0),
                    "hits": int(pred.get("appliedHits") or 0)})
    else:
        out["pred_skip"] = "aiPredict sans pred (portee ? placement ?) ok=%s" % (ap.get("ok"),)

    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    ob = ob if isinstance(ob, dict) else {}
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    snap = snap if _ok(snap) else None

    s1 = rpc(sid, "dumpRng", {"runnerId": rid}, 40)
    if snap is None or not _ok(s1):
        out["combat_skip"] = "combatSnapshot/dumpRng indisponible"
        return out

    st = load_state(dv, ob, snap, damage_config=bc_damage)
    te = st.get_entity(tgt["id"])
    hc = te.get_component(HealthComponent) if te is not None else None
    if hc is None or hc.hp is None:
        out["combat_skip"] = "HealthComponent de la cible indisponible"
        return out
    hp_before = int(hc.hp)
    rng = IntBasedMersenneTwister()
    rng.mt = list(s1["mt"])
    rng.mti = s1["mti"]
    st.rng = rng
    r = Runner(st).install_default_handlers()
    r.apply(AttackUnitMessage(att["id"], tgt["id"]))
    last = r.damage_handler.last
    out["off"] = None if last is None else int(last["total"])

    res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att["id"], "targetId": tgt["id"],
        "abilityType": norm["id"]}}, 60)
    if not _ok(res) or not (res.get("actions") or [{}])[0].get("ok"):
        out["combat_skip"] = "cast refuse: %s" % (str(res)[:160],)
        return out
    hp_after = next((u.get("hp") for u in (res.get("units") or [])
                     if u.get("squadId") == tgt["id"]), None)
    if hp_after is None:
        out["combat_skip"] = "hp de la cible indisponible"
        return out
    out["live"] = int(hp_before) - int(hp_after)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--field", choices=sorted(FIELDS), default="elevation")
    ap.add_argument("--value", type=int, default=None,
                    help="valeur DISCRIMINANTE ecrite dans le champ (defaut : celui du champ)")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default=None)
    ap.add_argument("--p-units", dest="p_units", default=None)
    ap.add_argument("--a-units", dest="a_units", default=None)
    ap.add_argument("--att", default=None)
    ap.add_argument("--tgt", default=None)
    ap.add_argument("--att-tile", dest="att_tile", default=None)
    ap.add_argument("--tgt-tile", dest="tgt_tile", default=None)
    ap.add_argument("--tag", default="", help="suffixe des fichiers logs/ (runs concurrents)")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    cfg = dict(FIELDS[a.field])
    for k in ("board", "p_units", "a_units", "att", "tgt", "att_tile", "tgt_tile"):
        if getattr(a, k) is not None:
            cfg[k] = getattr(a, k)
    value = a.value if a.value is not None else cfg["default_value"]
    suffix = ("_" + a.tag) if a.tag else ""

    sid = _resolve_session()
    rows = []
    for name, mut in arms(cfg["key"], value):
        bcp = LOGS / ("bc_449r2r4r4_%s_%s%s.json" % (a.field, name, suffix))
        section = write_bc(bcp, mut)
        sf = LOGS / ("rs_449r2r4r4_%s_%s%s.json" % (a.field, name, suffix))
        rid = build(sf, a.seed, bcp, cfg)
        try:
            m = measure(sid, rid, section, cfg)
            m["arm"] = name
            rows.append(m)
            print("[%-7s] runner=%-4d BC.%s=%-6r -> natif live=%-8s pred=[%s, %s] | port=%s"
                  % (name, rid, cfg["key"], m["bc_value"],
                     m.get("live", m.get("combat_skip", "?")),
                     m.get("min", "?"), m.get("max", "?"), m.get("off", "?")))
        finally:
            if not a.keep:
                dispose(sf, rid)

    print("=== ETAGE 1 -- le NATIF suit-il `BC.Damage.%s` ? ===" % cfg["key"])
    lives = {r["arm"]: r.get("live") for r in rows}
    print("  degat live par bras : %s" % (lives,))
    vals = [v for v in lives.values() if v is not None]
    natif_bouge = len(set(vals)) > 1
    print("  -> le natif %s avec le champ" % ("BOUGE" if natif_bouge else "NE BOUGE PAS"))

    print("=== ETAGE 2 -- le PORT suit-il le meme champ ? ===")
    offs = {r["arm"]: r.get("off") for r in rows}
    print("  degat port par bras  : %s" % (offs,))
    ovals = [v for v in offs.values() if v is not None]
    port_bouge = len(set(ovals)) > 1
    print("  -> le port %s (%s)" % ("BOUGE" if port_bouge else "NE BOUGE PAS", cfg["port_symbol"]))

    verdict = 0
    print("=== ETAGE 3 -- ECART CHIFFRE, bras par bras ===")
    for r in rows:
        live, off = r.get("live"), r.get("off")
        if live is None or off is None:
            print("  %-8s NON CONFRONTE : %s" % (r["arm"], r.get("combat_skip", "?")))
            continue
        d = off - live
        print("  %-8s BC.%s=%-6r  natif=%-8d port=%-8d  ECART=%+d (%.1f%%)"
              % (r["arm"], cfg["key"], r["bc_value"], live, off, d,
                 (100.0 * d / live) if live else 0.0))
        if d != 0:
            verdict = 1

    if natif_bouge and not port_bouge:
        print("  => LE PORT PORTE UN LITTERAL sur ce champ : le natif le suit, le port l'ignore.")
    print("=== VERDICT === %s" % ("VERT" if verdict == 0 else "ROUGE"))
    return verdict


if __name__ == "__main__":
    raise SystemExit(main())
