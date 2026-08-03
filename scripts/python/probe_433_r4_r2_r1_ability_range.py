"""probe #433-r4-r2-r1 -- la BRANCHE A d'`EarlyWarningOverridePlaybook` : `IsTileInRangeOfAnyAbility`.

LE CORPS NATIF, LU (`IdunBattle.Core.Services.BattleQuery$$IsTileInRangeOfAnyAbility`) :

    feet = UnitExtensions.GetFeetCount(unit, this.<state @+0x38>)
    if (feet > 1) return true;                                   // court-circuit MULTI-TUILES
    main = EntityExtensions.GetMainTile(unit, this.<state @+0x38>)
    set  = new OrderedSet<Tile>(main == null ? new List<Tile>() : main.ToList())
    tiles = <this.attack @+0x20>.<slot 0xe>(unit, set, true)
    return tiles != null && tiles.Contains(tile)

Le service a `BattleQuery+0x20` est le parametre `attack` de
`IdunBattle.Core.Services.BattleQuery$$Initialize(processor, movement, tileQuery, ATTACK, effects,
damagePrediction, ...)` -- c'est-a-dire l'`IAttackQuery` du runner (`<AttackQuery>k__BackingField`).
Son slot 0xe est `IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange(unit,
possiblePositions, includeNormalAttack)` : la surcharge a TROIS arguments, dont le 3e est le litteral
`1` du call site.

CE QUE CETTE LECTURE CORRIGE DANS LA FICHE HERITEE (`case-433-r4-r2` §7). Elle annoncait
« MOUVEMENT et LoS compris ». Le MOUVEMENT n'y est PAS : l'ensemble de positions passe est le
SINGLETON `{GetMainTile(unit)}`, donc la zone est celle de la tuile COURANTE. Ce qui explique le
`d = 5` mesure, c'est le kit : `tauMarksman` porte l'ability active `SeekerMissileFrequencyLock`
(`constants.range = 5`) en plus de son arme `Range = 3` -- `includeNormalAttack: true` ajoute
l'attaque normale a l'union des abilities, pas un rayon de deplacement.

CE QUE LE PROBE MESURE :

  * `--step seam` : la seam live candidate. `aiMovableTiles` publie deja
    `GetAllTilesInAbilityRange(unit, <movable set>, true)` sous le nom `threatTiles` ; avec
    `overrideRange: 0` le `MovementOptions` passe a `GetMovableTilesFor` borne le deplacement, donc
    le set d'entree se reduit -- reste a MESURER a quoi il se reduit (vide ? {tuile courante} ?), car
    c'est cela, et cela seul, qui decide si la seam EGALE le singleton natif.
    L'oracle est le NATIF contre LUI-MEME : sur le montage NON-adjacent (branche A pure), le bonus
    d'`ncEvaluate` vaut `0` exactement aux positions ou `IsTileInRangeOfAnyAbility` est VRAI. On
    compare donc `{P du sweep : bonus == 0}` a `threatTiles(E) ∩ sweep`, pour chaque variante.

  * `--step kit` : le contre-controle OFFLINE du modele « union des portees d'ability + arme »
    (gameconfig) contre la meme partition du natif -- pour chiffrer ce que le modele rate (LoS,
    gates par ability) plutot que de l'affirmer.

Usage (ASCII only, depuis scripts/python) :
  python probe_433_r4_r2_r1_ability_range.py --step seam
  python probe_433_r4_r2_r1_ability_range.py --step kit
  python probe_433_r4_r2_r1_ability_range.py --step all
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                     # noqa: E402
from rl_collect_batch import _resolve_session, _rpc               # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

CASTER = "tauCrisis"          # HERO du pool ; seul porteur `lineup` de 1077
ENEMY = "tauMarksman"         # arme Range=3 + ability SeekerMissileFrequencyLock range=5
ABILITY = 1077                # ActiveAbilityType.EarlyWarningOverride
BOARD = "MC1_67"
SEED = "777"


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(extra=None):
    state = ROOT / "logs" / "runners" / ("p433r4r2r1-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
            "--state-file", str(state), "--p-units", CASTER, "--a-units", ENEMY,
            "--hp-target", "90000", "--hp-player", "90000"] + list(extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return None, (p.stderr or p.stdout or "")[-1200:]
    return json.loads(state.read_text())["runnerId"], None


def _dispose(sid, rid):
    if rid is None:
        return
    try:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    except Exception:                                             # pragma: no cover - diagnostic
        pass


def _units(sid, rid):
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    c = next((u for u in (dv.get("units") or []) if u.get("visualId") == CASTER), None)
    e = next((u for u in (dv.get("units") or []) if u.get("visualId") == ENEMY), None)
    return dv, c, e


def _place(sid, rid, caster_id, enemy_id, O, Y):
    """Meme montage que `probe_433_r4_r2_adjacency_foyer._place` : on POSE les deux unites puis on
    rend au caster un set de move FRAIS (le `move` pose le drapeau `Moved`)."""
    for uid, p in ((enemy_id, Y), (caster_id, O)):
        _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": p[0], "row": p[1]}}}, 90)
    for _ in range(4):
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
        by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        if (by_unit.get(caster_id) or {}).get("tiles"):
            return True
    return False


def _board_maps(sid, rid):
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    tiles = bg.get("tiles") or []
    pos_of = {t["id"]: (t["col"], t["row"]) for t in tiles}
    elev = {pos_of[t["id"]]: t.get("elevation") for t in tiles}
    walk = {pos_of[t["id"]]: bool(t.get("walkable")) for t in tiles}
    return elev, walk


def _pick_far(elev, walk, want):
    """`(O, Y)` walkables a `hexdist == want`. Loin l'un de l'autre, l'ennemi n'est PAS adjacent au
    caster : TOUT le sweep passe donc par la BRANCHE A, sans avoir besoin de la porte d'elevation --
    et le sweep DEPASSE la portee du kit ennemi, ce qui est ce qu'on veut mesurer ici (le montage
    `--step partition` de #433-r4-r2 restait a `d <= 4`, donc entierement DANS la portee)."""
    cands = sorted(p for p in walk if walk[p] and elev.get(p) is not None)
    for O in cands:
        for Y in cands:
            if hexgeo.distance(O, Y) == want:
                return O, Y
    return None, None


def _nc_partition(sid, rid, uid, enemy_pos: list):
    """`({P : bonus == 0}, {P : bonus == 50}, positions)` -- le bonus etant `util + 10*Sum_E d(P,E)`.

    VERROU DE MONTAGE : la partition n'est ATTRIBUABLE que s'il y a EXACTEMENT UN ennemi vivant.
    Le terme `-10*d` est somme sur TOUS les ennemis (`GetAllAliveUnits` + `IsEnemy`) et chacun verse
    son propre `+50/0` : a deux ennemis, un `bonus` de 50 ne dit plus LEQUEL est hors portee. Le
    probe REFUSE plutot que de lire un melange (un bonus de 0 y serait aussi un `+50 - 50` fortuit).
    """
    nat = _r(sid, "ncEvaluate", {"runnerId": rid, "unitId": uid, "abilityType": ABILITY,
                                 "sweep": True}, 180)
    in_range, out_range, allp = set(), set(), []
    for p in (nat.get("positions") or []):
        if p.get("util") is None:
            continue
        P = tuple(p["pos"])
        allp.append(P)
        b = round(p["util"] + 10 * sum(hexgeo.distance(P, e) for e in enemy_pos), 6)
        (in_range if b == 0 else out_range).add(P)
    return in_range, out_range, allp, nat


def _threat(sid, rid, enemy_id, body_extra):
    body = {"runnerId": rid, "side": "all", "threat": True}
    body.update(body_extra)
    mv = _r(sid, "aiMovableTiles", body, 120)
    row = next((u for u in (mv.get("units") or []) if u.get("unitId") == enemy_id), None)
    if row is None:
        return None, None, mv.get("error")
    return ({(t["col"], t["row"]) for t in (row.get("threatTiles") or [])},
            {(t["col"], t["row"]) for t in (row.get("tiles") or [])}, row.get("err"))


# ------------------------------------------------------------------------------------------------
# etape SEAM
# ------------------------------------------------------------------------------------------------
def step_seam(verbose=True, enemy=None, want=8, movement=6) -> dict:
    global ENEMY
    if enemy:
        ENEMY = enemy
    sid = _resolve_session()
    if not sid:
        return {"error": "aucune session Frida"}
    rid, err = _build()
    if rid is None:
        return {"error": "build KO : %s" % err}
    try:
        elev, walk = _board_maps(sid, rid)
    finally:
        _dispose(sid, rid)
    O, Y = _pick_far(elev, walk, want)
    if O is None:
        return {"error": "aucune paire walkable a distance %d sur %s" % (want, BOARD)}

    sid = _resolve_session()
    rid, err = _build(["--unit-stat", "%s:Movement=%d" % (CASTER, movement)])
    if rid is None:
        return {"error": "build KO (seam) : %s" % err}
    try:
        _dv, c, e = _units(sid, rid)
        if c is None or e is None:
            return {"error": "caster/ennemi absent"}
        if not _place(sid, rid, c["id"], e["id"], O, Y):
            return {"error": "montage non installe (pas de tuile candidate)"}
        dv, c, e = _units(sid, rid)
        posn = {u["id"]: (u["pos"]["col"], u["pos"]["row"])
                for u in (dv.get("units") or []) if u.get("pos")}
        if posn.get(c["id"]) != O or posn.get(e["id"]) != Y:
            return {"error": "positions non atteintes : %r" % posn}
        # VERROU DE MONTAGE (cf. `_nc_partition`) : la partition n'est attribuable qu'a UN ennemi.
        foes = [(u.get("visualId"), (u["pos"]["col"], u["pos"]["row"]))
                for u in (dv.get("units") or [])
                if u.get("pos") and u.get("alive") and not u.get("ctrl")]
        if len(foes) != 1:
            return {"error": "montage IMPUR : %d ennemis vivants %r (la partition n'est pas "
                             "attribuable a un seul kit)" % (len(foes), foes)}
        in_range, out_range, allp, _nat = _nc_partition(sid, rid, c["id"], [Y])
        sweep = set(allp)
        variants = {
            "range0": {"overrideRange": 0},
            "range1": {"overrideRange": 1},
            "plein": {},
        }
        by_d: dict = {}
        for P in sweep:
            by_d.setdefault(hexgeo.distance(P, Y), set()).add(P in in_range)
        out = {"O": O, "Y": Y, "elev_O": elev[O], "elev_Y": elev[Y], "enemy_visual": ENEMY,
               "caster": c["id"], "enemy": e["id"], "n_sweep": len(sweep),
               "natif_in_range": sorted(in_range), "natif_out_range": sorted(out_range),
               "in_range_par_distance": {d: sorted(v) for d, v in sorted(by_d.items())},
               "d_max": max(hexgeo.distance(P, Y) for P in sweep) if sweep else None,
               "variants": {}}
        for tag, extra in variants.items():
            th, mv, e_err = _threat(sid, rid, e["id"], extra)
            if th is None:
                out["variants"][tag] = {"error": e_err or "ligne ennemie absente"}
                continue
            inter = th & sweep
            out["variants"][tag] = {
                "n_threat": len(th), "n_move_in": len(mv),
                "faux_positifs": sorted(inter - in_range),     # seam dit en portee, natif non
                "faux_negatifs": sorted(in_range - inter),     # natif dit en portee, seam non
                "exact": inter == in_range, "err": e_err,
            }
        if verbose:
            print("[seam] ennemi=%s O=%s Y=%s hexdist=%d -> BRANCHE A pure ; sweep n=%d d_max=%s"
                  % (ENEMY, O, Y, hexgeo.distance(O, Y), out["n_sweep"], out["d_max"]))
            print("[seam] `IsTileInRangeOfAnyAbility` par DISTANCE a l'ennemi "
                  "(True = en portee) :")
            for d, v in sorted(out["in_range_par_distance"].items()):
                print("[seam]   d=%d -> %r" % (d, v))
            for tag in variants:
                v = out["variants"][tag]
                if "error" in v:
                    print("[seam] %-7s REFUS : %s" % (tag, v["error"]))
                    continue
                print("[seam] %-7s threat=%3d move_in=%3d  FP=%d FN=%d  %s"
                      % (tag, v["n_threat"], v["n_move_in"], len(v["faux_positifs"]),
                         len(v["faux_negatifs"]), "EXACT" if v["exact"] else "DIVERGE"))
        return out
    finally:
        _dispose(sid, rid)


# ------------------------------------------------------------------------------------------------
# etape KIT -- le modele OFFLINE (union des portees) contre la meme partition
# ------------------------------------------------------------------------------------------------
def step_kit(verbose=True, enemy=None, want=8, movement=6) -> dict:
    """Le MIRROR PORTE (`engine.services.ability_range.is_tile_in_range_of_any_ability`) confronte
    tuile par tuile a la partition du natif -- meme montage que `--step seam`, seul le predicat
    compare change. C'est ce qui chiffre le residu de la branche A plutot que de l'affirmer."""
    res = step_seam(verbose=verbose, enemy=enemy, want=want, movement=movement)
    if "error" in res:
        return res
    from engine.services import ability_range as ar
    vid = res["enemy_visual"]
    reach = ar.unit_threat_reach(vid)
    Y = tuple(res["Y"])
    in_range = {tuple(p) for p in res["natif_in_range"]}
    out_range = {tuple(p) for p in res["natif_out_range"]}
    sweep = in_range | out_range
    modeled = {P for P in sweep if ar.is_tile_in_range_of_any_ability(Y, P, vid)}
    out = {"enemy_visual": vid, "reach": reach, "n_sweep": len(sweep),
           "faux_positifs": sorted(modeled - in_range),
           "faux_negatifs": sorted(in_range - modeled),
           "exact": modeled == in_range}
    if verbose:
        print("[kit] %s : reach modelise = %d ; sweep n=%d ; FP=%d FN=%d -> %s"
              % (vid, reach, out["n_sweep"], len(out["faux_positifs"]),
                 len(out["faux_negatifs"]), "EXACT" if out["exact"] else "DIVERGE"))
        if out["faux_positifs"]:
            print("[kit] faux positifs (modele dit en portee, natif non) : %r"
                  % (out["faux_positifs"],))
        if out["faux_negatifs"]:
            print("[kit] faux negatifs : %r" % (out["faux_negatifs"],))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="all", choices=["seam", "kit", "all"])
    ap.add_argument("--enemy", default=None,
                    help="visualId ennemi (2e cas discriminant : portee de kit DIFFERENTE)")
    ap.add_argument("--dist", type=int, default=8, help="hexdist entre O et Y")
    ap.add_argument("--movement", type=int, default=6, help="Movement force du caster")
    a = ap.parse_args()
    rc = 0
    if a.step == "seam":
        res = step_seam(enemy=a.enemy, want=a.dist, movement=a.movement)
        if "error" in res:
            print("[seam] REFUS : %s" % res["error"])
            rc |= 1
    if a.step in ("kit", "all"):
        # `--step all` = `kit` SEUL : `kit` rejoue deja `seam` (meme montage), donc les enchainer
        # monterait DEUX fois le meme runner pour la meme mesure.
        res = step_kit(enemy=a.enemy, want=a.dist, movement=a.movement, verbose=True)
        if "error" in res:
            print("[kit] REFUS : %s" % res["error"])
            rc |= 1
        elif not res.get("exact"):
            rc |= 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
