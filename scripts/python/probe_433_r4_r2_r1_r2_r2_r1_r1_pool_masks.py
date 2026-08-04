"""probe #433-r4-r2-r1-r2-r2-r1-r1 -- les 32 masques du POOL, confrontes au natif.

LA QUESTION BINAIRE. Les 32 abilities ACTIVES du pool spawnable hors `ABILITY_CLASSES` n'avaient
que leur volet PORTEE de lu ; leur masque `rules` etant absent, TROIS etages du port etaient
DESARMES par la convention permissive (`rules is None` -> aucun retrait) :

  1. le court-circuit AMONT `TargetIsFriendly && !TargetIsEnemy` de
     `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetTiles` -- l'ability ne verse AUCUNE
     tuile a `IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange` ;
  2. le `RemoveAll` de `IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange`, gate par le bit 43
     `AllowUnwalkableTargetTile` -- que **AUCUNE des 32** ne porte ;
  3. le predicat de LIGNE DE VUE (`b__1`), dont les bits `AllowObscuredTargetBy*` decident de ce que
     `TargetingQuery$$GetTilesObscuringTerrain` regarde.

Le masque etant desormais LU, ces trois etages mordent. Ce probe demande au NATIF s'il a raison.

L'ORACLE, et pourquoi c'est celui-la. `aiMovableTiles {threat: true}` publie `threatTiles` =
`AttackQuery$$GetAllTilesInAbilityRange(unit, <movable set>, includeNormalAttack: true)` -- le MEME
slot 0xe que `BattleQuery$$IsTileInRangeOfAnyAbility` interroge. Le port est donc compare a la
fonction qu'il mirrore, pas a un proxy. `overrideRange` borne le movable set A LA MESURE (cf.
`#433-r4-r2-r1-r2-r2`) : un set complet noie la mesure, un set vide annule la zone.

⚠ L'ensemble d'entree du natif est le MOVABLE SET, pas le singleton `{GetMainTile}`. Le port est
donc evalue en UNION sur ce meme set -- sinon on comparerait deux questions differentes.

DEUX MONTAGES, choisis pour que chacun isole UN etage :

  * `--step friendly` : `templAncient`, dont le kit tient en UNE ability active, `1061
    UnbreakableDuty` (`rules = 0x8400` = `TargetIsFriendly | CasterIsPossibleTarget`, SANS
    `TargetIsEnemy` -> court-circuit) et une arme de portee 1 alors que `constants.range = 2`. Le
    port d'AVANT rendait `unit_threat_reach = 2`, celui d'APRES rend `1` : la frontiere est
    DIFFERENTE, donc observable. Aucun autre etage ne peut expliquer l'ecart -- le kit n'a rien
    d'autre.
  * `--step walkability` : `tauMarksman`, ability `1069 SeekerMissileFrequencyLock`
    (`rules = 0x4002`, `constants.range = 5`), sur un board a fort taux de tuiles NON MARCHABLES.
    Le masque etant lu, l'etage 2 mord ; sans lui le port attribuait ces tuiles.

Usage (ASCII only, depuis scripts/python) :
  python probe_433_r4_r2_r1_r2_r2_r1_r1_pool_masks.py --step friendly
  python probe_433_r4_r2_r1_r2_r2_r1_r1_pool_masks.py --step walkability --board C5_19
  python probe_433_r4_r2_r1_r2_r2_r1_r1_pool_masks.py --step all
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

SEED = "777"
#: `MovementOptions.OverrideRange` a la MESURE -- meme valeur et meme raison que la tranche
#: precedente : borne le movable set sans l'annuler.
MEASURE_RANGE = 1

#: Montage 1 -- le court-circuit. UNE seule ability active, friendly-only, `constants.range` STRICTEMENT
#: superieur a la portee d'arme : c'est ce qui rend les deux modeles SEPARABLES.
FRIENDLY_CASTER = "templAncient"
FRIENDLY_ABILITY = 1061
FRIENDLY_BOARD = "MC1_67"

#: Montage 2 -- la walkability. Ability a portee 5 (`RANGE_FROM_CONFIG`) sur un board dont 34 tuiles
#: sur 63 sont non marchables (scan de la tranche precedente).
WALK_CASTER = "tauMarksman"
WALK_ABILITY = 1069
WALK_BOARD = "C5_19"

FILLER = "necroWarden"


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(board, p_units, a_units):
    state = ROOT / "logs" / "runners" / ("p433poolmask-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", board,
            "--state-file", str(state), "--p-units", p_units, "--a-units", a_units,
            "--hp-target", "90000", "--hp-player", "90000"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return None, (p.stderr or p.stdout or "")[-1500:]
    return json.loads(state.read_text())["runnerId"], None


def _dispose(sid, rid):
    if rid is None:
        return
    try:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    except Exception:                                                 # pragma: no cover
        pass


def _board_maps(sid, rid):
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    tiles = bg.get("tiles") or []
    pos = {t["id"]: (t["col"], t["row"]) for t in tiles}
    return ({pos[t["id"]]: t.get("elevation") for t in tiles},
            {pos[t["id"]]: bool(t.get("walkable")) for t in tiles},
            {pos[t["id"]]: bool(t.get("isWall")) for t in tiles},
            {pos[t["id"]]: bool(t.get("isInFog")) for t in tiles})


def _obs(sid, rid):
    o = _r(sid, "observeBattle", {"runnerId": rid}, 120)
    out = {}
    for u in (o.get("units") or []):
        if u.get("isDead") or u.get("col") is None:
            continue
        out[u["squadId"]] = ((u["col"], u["row"]), u.get("teamId"), u.get("visualId"))
    return out


def _threat(sid, rid, override_range=None):
    body = {"runnerId": rid, "threat": True, "side": "all"}
    if override_range is not None:
        body["overrideRange"] = int(override_range)
    mov = _r(sid, "aiMovableTiles", body, 150)
    out = {}
    for u in (mov.get("units") or []):
        out[u.get("unitId")] = ([(t["col"], t["row"]) for t in (u.get("tiles") or [])],
                                {(t["col"], t["row"]) for t in (u.get("threatTiles") or [])})
    return out


class _RangeOnly:
    """Le substrat d'AVANT la tranche : la PORTEE lue, le masque NON lu (`rules is None`).

    C'est ce que portait `engine.services.ability_range.TARGETING_RANGE_BY_ABILITY`, et c'est le
    contre-factuel exact -- retirer l'entree entiere simulerait « aucune portee », un AUTRE regime."""

    rules = None
    self_cast = False
    force_melee_target = 1

    def __init__(self, rng):
        self.range = rng

    def has(self, _rule):
        return False


def _port_zone(move_tiles, all_tiles, visual, elev, walk, wall, fog, team_by_pos, caster_team):
    """Le port, evalue en UNION sur le MOVABLE SET -- l'ensemble d'entree que le natif recoit.

    C'est `AttackQuery$$GetAllTilesInAbilityRange(unit, possiblePositions, true)` : la zone est
    l'union, sur chaque position possible, de ce que chaque ability couvre depuis elle."""
    from engine.services import ability_range as AR
    out = set()
    for T in all_tiles:
        for X in move_tiles:
            if AR.is_tile_in_range_of_any_ability(
                    X, T, visual, elev_by_pos=elev, is_wall_by_pos=wall,
                    caster_team=caster_team, team_by_pos=team_by_pos,
                    walkable_by_pos=walk, is_in_fog_by_pos=fog):
                out.add(T)
                break
    return out


def _weapon(visual):
    from engine.runner.abilities.targeting import unit_weapon_range
    return unit_weapon_range(visual, None)


def _reach_with(visual, ability_id, substitute):
    """`unit_threat_reach` sous un substrat donne (`None` = le substrat courant)."""
    import engine.runner.abilities.targeting as T
    from engine.services import ability_range as AR
    prev = T.TARGETING_OPTIONS_UNPORTED[ability_id]
    try:
        if substitute is not None:
            T.TARGETING_OPTIONS_UNPORTED[ability_id] = substitute
        AR._REACH_CACHE.clear()
        return AR.unit_threat_reach(visual)
    finally:
        T.TARGETING_OPTIONS_UNPORTED[ability_id] = prev
        AR._REACH_CACHE.clear()


def _measure(sid, board, caster, ability_id, p_units, a_units):
    """La MESURE, rendue en donnees. AVANT = masque retire a chaud, APRES = masque lu."""
    import engine.runner.abilities.targeting as T
    from engine.services import ability_range as AR

    if T.targeting_options_for(ability_id) is None:
        return {"error": "montage IMPUR : le masque de %d n'est pas lu" % ability_id}
    rid, err = _build(board, p_units, a_units)
    if rid is None:
        return {"error": "build KO -- %s" % err}
    try:
        elev, walk, wall, fog = _board_maps(sid, rid)
        allp = sorted(elev)
        u0 = _obs(sid, rid)
        by_vis = {v[2]: k for k, v in u0.items()}
        if caster not in by_vis:
            return {"error": "caster %s absent du runner (%r)" % (caster, sorted(by_vis))}
        e_id = by_vis[caster]
        e_team = u0[e_id][1]

        mt, native = [], set()
        for _ in range(6):
            th = _threat(sid, rid, MEASURE_RANGE)
            mt, native = (th.get(e_id) or ([], set()))
            if mt:
                break
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        if not mt:
            return {"error": "movable set VIDE -- ce montage ne mesure rien"}
        u1 = _obs(sid, rid)
        team_by_pos = {p: t for (p, t, _v) in u1.values() if t is not None}
        cpos = u1[e_id][0]

        def _zone():
            AR._REACH_CACHE.clear()
            return _port_zone(mt, allp, caster, elev, walk, wall, fog, team_by_pos, e_team)

        after = _zone()
        # L'etat d'AVANT n'est PAS « aucune option » : c'etait « PORTEE lue, masque NON lu ». Retirer
        # l'entree simulerait une ability sans portee, qui ne verse rien -- un autre regime, et la
        # mesure ne dirait alors rien du masque. On remet donc EXACTEMENT le substrat d'avant :
        # le `TargetingRange` de la table supprimee, et `rules = None` (la convention permissive).
        prev = T.TARGETING_OPTIONS_UNPORTED[ability_id]
        try:
            T.TARGETING_OPTIONS_UNPORTED[ability_id] = _RangeOnly(prev.range)
            before = _zone()
        finally:
            T.TARGETING_OPTIONS_UNPORTED[ability_id] = prev
            AR._REACH_CACHE.clear()

        native &= set(allp)
        return {
            "board": board, "caster": caster, "caster_pos": cpos, "ability": ability_id,
            "rules": T.targeting_options_for(ability_id).rules,
            "n_tiles": len(allp), "n_move_tiles": len(mt),
            "n_nonwalkable": len([t for t in allp if not walk.get(t)]),
            "move_tiles": sorted(mt), "weapon_range": _weapon(caster),
            "occupied": sorted(team_by_pos),
            "reach_before": _reach_with(caster, ability_id, _RangeOnly(
                T.targeting_options_for(ability_id).range)),
            "reach_after": _reach_with(caster, ability_id, None),
            "n_native": len(native), "n_before": len(before), "n_after": len(after),
            "fp_before": sorted(before - native), "fn_before": sorted(native - before),
            "fp_after": sorted(after - native), "fn_after": sorted(native - after),
            "maxd_native": max([hexgeo.distance(t, cpos) for t in native] or [-1]),
            "maxd_before": max([hexgeo.distance(t, cpos) for t in before] or [-1]),
            "maxd_after": max([hexgeo.distance(t, cpos) for t in after] or [-1]),
        }
    finally:
        _dispose(sid, rid)


def friendly(sid, board=None) -> dict:
    """Le court-circuit `GetPossibleTargetTiles` -- `templAncient`, kit d'UNE ability friendly-only."""
    return _measure(sid, board or FRIENDLY_BOARD, FRIENDLY_CASTER, FRIENDLY_ABILITY,
                    "%s,%s" % (FILLER, WALK_CASTER), "%s,%s" % (FRIENDLY_CASTER, FILLER))


def walkability(sid, board=None) -> dict:
    """L'etage AMONT `GetTilesInRange` -- `tauMarksman`, portee 5, board a non marchables."""
    return _measure(sid, board or WALK_BOARD, WALK_CASTER, WALK_ABILITY,
                    "%s,%s" % (FILLER, FRIENDLY_CASTER), "%s,%s" % (WALK_CASTER, FILLER))


def _print(tag, res):
    print("-- %s" % tag)
    if res.get("error"):
        print("   ERROR: %s" % res["error"])
        return
    print("   board=%s caster=%s@%s ability=%d rules=0x%x"
          % (res["board"], res["caster"], res["caster_pos"], res["ability"], res["rules"]))
    print("   tuiles=%d movable=%d %s non-marchables=%d arme=%s"
          % (res["n_tiles"], res["n_move_tiles"], res["move_tiles"][:6],
             res["n_nonwalkable"], res["weapon_range"]))
    print("   unit_threat_reach : AVANT=%s APRES=%s"
          % (res["reach_before"], res["reach_after"]))
    print("   natif=%d  port AVANT=%d  port APRES=%d"
          % (res["n_native"], res["n_before"], res["n_after"]))
    print("   AVANT : FP=%d FN=%d   |   APRES : FP=%d FN=%d"
          % (len(res["fp_before"]), len(res["fn_before"]),
             len(res["fp_after"]), len(res["fn_after"])))
    print("   dmax natif=%d avant=%d apres=%d"
          % (res["maxd_native"], res["maxd_before"], res["maxd_after"]))
    if res["fp_after"] or res["fn_after"]:
        print("   residu APRES : FP=%s FN=%s" % (res["fp_after"][:8], res["fn_after"][:8]))
        print("   occupants    : %s" % (res.get("occupied") or [],))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=["friendly", "walkability", "all"], default="all")
    ap.add_argument("--board", default=None)
    a = ap.parse_args()
    sid = _resolve_session()
    rc = 0
    if a.step in ("friendly", "all"):
        res = friendly(sid, a.board if a.step == "friendly" else None)
        _print("friendly (court-circuit GetPossibleTargetTiles)", res)
        rc |= 1 if res.get("error") else 0
    if a.step in ("walkability", "all"):
        res = walkability(sid, a.board if a.step == "walkability" else None)
        _print("walkability (RemoveAll de GetTilesInRange)", res)
        rc |= 1 if res.get("error") else 0
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
