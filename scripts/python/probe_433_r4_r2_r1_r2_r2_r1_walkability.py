"""probe #433-r4-r2-r1-r2-r2-r1 -- l'etage AMONT qui retire les tuiles NON MARCHABLES.

LA QUESTION BINAIRE, ET SA REPONSE LUE. << A quel etage exact le natif retire-t-il les tuiles non
marchables, et est-ce en amont ou en aval de la ligne de vue ? >> -- reponse : dans
`IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange`, donc **EN AMONT**, et ce n'est pas un
quatrieme predicat mais un `RemoveAll` INTERNE a la fonction qui CONSTRUIT la zone :

    GetTilesInRange(caster, casterTiles, options, range) :
        ... construction de la zone (5 branches : vide / GetAllTiles / casterTiles / adjacentes /
            GetTilesInRadius -- les deux dernieres recoivent DEJA `onlyWalkableTiles` = le meme bit)
        if ((options.Rules & AllowUnwalkableTargetTile) == 0)          # bit 43
            RemoveAll(zone, TargetingQuery.<>c.<GetTilesInRange>b__36_0)

    IdunBattle.Core.Services.TargetingQuery.u003Cu003Ec$$u003CGetTilesInRangeu003Eb__36_0(t)
        = !IdunBattle.Entities.TileExtensions$$IsWalkable(t, checkFog: true)

Les trois predicats de `GetPossibleTargetsForOptions` (`b__0` ami/portee, `b__1` LIGNE DE VUE,
`b__2` gate dynamique) s'appliquent ENSUITE, a la zone deja amputee.

DEUX VOLETS, DEUX CANAUX -- et c'est ce que la mesure impose :

    IsWalkable(tile, checkFog) : m = tile.<+0x40>; if (m.<+0x10> != 0) return false;
                                 if (!checkFog) return true;
                                 return tile.<TileComponent @+0x20>.<IsInFogOfWar @+0x40> == 0;

`IdunBattle.Core.Services.BattleQuery$$IsWalkableTile` -- la source du champ `walkable` du
`boardGraph` -- ne rend QUE le premier volet (elle n'a pas de parametre `checkFog`). Le second se
lit sur `isInFog` du meme `boardGraph` (`TileComponent+0x40`, publie par #403).

LE GISEMENT ETAIT MINCE, ET C'ETAIT LE PREMIER PROBLEME. La mesure heritee valait
<< 0 non-marchable dans la zone native, sur 1 presente >> : cohérent, mais pose sur UNE tuile.
Trois regimes sont donc balayes ici, choisis par un scan OFFLINE des 779 dumps puis confirmes live :

    C5_19   34 tuiles non marchables (Block) / 63, 0 mur, 0 fog   -> volet WALKABLE, PUR
    C6_02   22 non marchables + 31 tuiles `walkable && isInFog`   -> volet FOG, DISCRIMINANT
    MC1_67   1 non marchable                                      -> le regime maigre d'origine

Le montage est celui de `#433-r4-r2-r1-r2-r2` (dont il reprend l'oracle) : `1161
TwinSmartMissileSystem` (`UseWholeBoard`, `rules = 0x40004000` -- donc **sans** le bit 43) greffee
SEULE sur `custoBladeChampion` (arme de MELEE : le predicat de ligne de vue est structurellement
muet a `d = 1`), et l'oracle est `aiMovableTiles {threat: true}` =
`IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange`, dont la zone couvre TOUT le
plateau. `overrideRange` garde `casterTiles` petit A LA MESURE (cf. #433-r4-r2-r1-r2-r2).

Usage (ASCII only, depuis scripts/python) :
  python probe_433_r4_r2_r1_r2_r2_r1_walkability.py --step read
  python probe_433_r4_r2_r1_r2_r2_r1_walkability.py --step live --board C5_19
  python probe_433_r4_r2_r1_r2_r2_r1_walkability.py --step boards      # inventaire live des canaux
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

#: Meme greffon que `#433-r4-r2-r1-r2-r2` -- arme de MELEE seule (`unit_weapon_range == 1`).
GRAFT_HOST = "custoBladeChampion"
#: `1161 TwinSmartMissileSystem` : `UseWholeBoard`, `rules = 0x40004000` (TargetIsEnemy |
#: AllowNullCasterTile). Le bit 43 `AllowUnwalkableTargetTile` est ABSENT -> le natif RETIRE.
GRAFT_ABILITY = 1161
FOE = "tauMarksman"
CASTER_TEAM_UNITS = "tauCrisis"
ALLY = "necroWarden"
SEED = "777"
#: Le greffon est en TEAM 1, et ce n'est pas cosmetique : les 15 boards a FOG sont TOUS des
#: `C6_*` (space hulk), ou l'equipe 2 n'est **pas deployee** (mesure : `observeBattle` rend 0 unite
#: team 2 sur `C6_02`, `C6_13`, `C6_14`). Mettre le greffon du cote qui SPAWNE est ce qui rend le
#: regime FOG confrontable -- la zone de `GetAllTilesInAbilityRange` ne depend d'aucun ennemi.
MOVEMENT = 8
#: `MovementOptions.OverrideRange` a la MESURE (cf. `#433-r4-r2-r1-r2-r2` : un movable set complet
#: annule l'intersection de `MovementQuery$$GetTilesObscuringTerrain`, un movable set vide annule
#: la zone entiere).
MEASURE_RANGE = 1
#: Les trois regimes, du plus mordant au plus maigre (scan OFFLINE des 779 dumps + confirmation live).
BOARDS = ["C5_19", "C6_02", "MC1_67"]
#: Les 15 boards a FOG sont exactement ceux dont un `Tile.RoomID >= 0` (space hulk) -- correlation
#: EXACTE mesuree sur `C6_02` : 32 tuiles `RoomID >= 0`, 32 tuiles `isInFog`.


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _grafted_seed():
    import catalog_inject as CI
    from engine.entities.active_ability_type import ActiveAbilityType
    name = ActiveAbilityType(GRAFT_ABILITY).name
    out = ROOT / "logs" / "runners" / ("seedbc-walk-%s.json" % uuid.uuid4().hex[:6])
    out.parent.mkdir(parents=True, exist_ok=True)
    return CI.write_grafted_seed_bc(out, ["%s:%s" % (GRAFT_HOST, name)],
                                    replace=True, kind="active")


def _build(board, seed_bc=None):
    state = ROOT / "logs" / "runners" / ("p433walk-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", board,
            "--state-file", str(state),
            "--p-units", "%s,%s" % (GRAFT_HOST, CASTER_TEAM_UNITS),
            "--a-units", "%s,%s" % (FOE, ALLY),
            "--hp-target", "90000", "--hp-player", "90000",
            "--unit-stat", "%s:Movement=%d" % (GRAFT_HOST, MOVEMENT)]
    if seed_bc:
        argv += ["--seed-bc", str(seed_bc)]
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
    """`(elev, walk, wall, fog)` -- les quatre cartes du `boardGraph`, indexees par (col,row)."""
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


def _move(sid, rid, uid, to):
    _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": to[0], "row": to[1]}}}, 90)


def _place(sid, rid, wanted):
    for _ in range(8):
        cur = _obs(sid, rid)
        if all(cur.get(u, ((), None, None))[0] == p for u, p in wanted.items()):
            return cur
        for u, p in wanted.items():
            if cur.get(u, ((), None, None))[0] != p:
                _move(sid, rid, u, p)
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return _obs(sid, rid)


def _obscured(board, caster_tiles, rules, tiles, team_by_pos, caster_team):
    """Les tuiles que le predicat de LIGNE DE VUE retire -- gardes << ami >> ALIMENTEES
    (`#433-r4-r2-r1-r2-r2`). Foyer UNIQUE `engine.services.targeting_query`."""
    from engine.services import targeting_query as TQ
    out = set()
    for T in tiles:
        gf, gh = TQ.friend_gates_for_tile_target(caster_team, (team_by_pos or {}).get(T))
        if TQ.target_is_obscured(board, caster_tiles, T, rules,
                                 target_is_friend=gf, target_is_friend_or_has_friendly_unit=gh):
            out.add(T)
    return out


def _unwalkable(rules, tiles, walk, fog):
    """Les tuiles que l'etage AMONT retire -- foyer `targeting_query.tile_removed_by_walkability`."""
    from engine.services import targeting_query as TQ
    return {T for T in tiles if TQ.tile_removed_by_walkability(rules, walk.get(T), fog.get(T))}


def _pick_caster_tile(board, elev, walk, wall, fog, rules, tiles):
    """La tuile du greffon qui MAXIMISE le gisement -- le nombre de tuiles NON MARCHABLES que le
    port d'AVANT attribuerait a tort (non marchables ET non obscurcies depuis le movable set).

    Le port ne sert qu'a CHOISIR le montage ; le verdict reste la partition NATIVE, relue sur
    l'etat FINAL. Meme doctrine que `#433-r4-r2-r1-r2-r2` : on DEPLACE l'unite pour obtenir la
    configuration voulue, on ne subit pas la geometrie de spawn."""
    from engine.services import targeting_query as TQ
    dead = {T for T in tiles if TQ.tile_removed_by_walkability(rules, walk.get(T), fog.get(T))}
    free = sorted(p for p in tiles if walk.get(p) and not wall.get(p) and elev.get(p) is not None)
    best, best_n, best_nb = None, -1, None
    for X in free:
        nbrs = [tuple(n) for n in hexgeo.neighbors(X[0], X[1])
                if walk.get(tuple(n)) and not wall.get(tuple(n))]
        if not nbrs:
            continue                       # movable set vide -> zone vide (mesure), inutilisable
        dark = _obscured(board, nbrs, rules, dead, {}, None)
        n = len(dead) - len(dark)          # non marchables NON obscurcies = le gisement
        if n > best_n:                     # `>` strict : premiere position en ordre trie a egalite
            best, best_n, best_nb = X, n, nbrs
    return best, best_n, best_nb


def live(sid, board) -> dict:
    """La MESURE, rendue en donnees (`{"error": ...}` sur refus). Elle n'existe qu'a UN endroit :
    `--step live` l'imprime, le test live l'assertionne."""
    from engine.services import movement_query as MQ
    from engine.runner.abilities.targeting import targeting_options_for, unit_weapon_range

    wr = unit_weapon_range(GRAFT_HOST, None)
    if wr is None or int(wr) > 1:
        return {"error": "anti-degenerescence : le greffon %s a une arme de portee %s -- le "
                         "predicat de ligne de vue est MUET a d=1, une arme plus longue "
                         "masquerait la mesure" % (GRAFT_HOST, wr)}
    from engine.services import targeting_query as TQ
    rules = getattr(targeting_options_for(GRAFT_ABILITY), "rules", None)
    if rules is None or (int(rules) & TQ.ALLOW_UNWALKABLE_TARGET_TILE):
        return {"error": "montage IMPUR : l'ability %d porte AllowUnwalkableTargetTile (ou son "
                         "masque n'est pas lu) -- l'etage ne mordrait pas" % GRAFT_ABILITY}
    seed, reports = _grafted_seed()
    rid, err = _build(board, seed)
    if rid is None:
        return {"error": "build KO -- %s" % err}
    try:
        elev, walk, wall, fog = _board_maps(sid, rid)
        board_obj = MQ.PositionBoard(elev, wall)
        allp = sorted(elev)
        u0 = _obs(sid, rid)
        by_vis = {v[2]: k for k, v in u0.items()}
        if GRAFT_HOST not in by_vis:
            return {"error": "greffon %s absent du runner (%r)" % (GRAFT_HOST, sorted(by_vis))}
        e_id = by_vis[GRAFT_HOST]
        e_team = u0[e_id][1]

        x_caster, gisement, nbrs = _pick_caster_tile(board_obj, elev, walk, wall, fog, rules, allp)
        if x_caster is None:
            return {"error": "aucune position de caster utilisable sur %s" % board}
        _place(sid, rid, {e_id: x_caster})

        # `GetMovableTilesFor(unit, ignoreUnitFlags: false, ...)` rend un ensemble VIDE pour une
        # unite qui a deja consomme son mouvement : on laisse tourner les tours SANS la deplacer.
        u1, mt, zone = _obs(sid, rid), [], set()
        for _ in range(6):
            th = _threat(sid, rid, MEASURE_RANGE)
            mt, zone = (th.get(e_id) or ([], set()))
            if mt:
                break
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            u1 = _obs(sid, rid)
        if not mt:
            return {"error": "movable set du greffon VIDE -- `GetAllTilesInAbilityRange` rend une "
                             "zone vide, ce montage ne mesure rien"}

        team_by_pos = {p: t for (p, t, _v) in u1.values() if t is not None}
        dark = _obscured(board_obj, mt, rules, allp, team_by_pos, e_team)
        dead_full = _unwalkable(rules, allp, walk, fog)          # les DEUX volets
        dead_walk = _unwalkable(rules, allp, walk, {})           # volet WALKABLE seul
        modeled_before = set(allp) - dark                        # port d'AVANT la tranche
        modeled_walk = modeled_before - dead_walk                # port a UN SEUL volet (contre-cas)
        modeled_after = modeled_before - dead_full               # port d'APRES

        nonwalk = [t for t in allp if not walk.get(t)]
        onlyfog = [t for t in allp if walk.get(t) and fog.get(t)]

        def _why(ts):
            return [{"pos": t, "walkable": walk.get(t), "isInFog": fog.get(t),
                     "isWall": wall.get(t), "elev": elev.get(t),
                     "d_caster": hexgeo.distance(t, u1[e_id][0])} for t in ts]

        return {
            "board": board, "rules": rules, "reports": reports,
            "caster": GRAFT_HOST, "caster_team": e_team, "caster_pos": u1[e_id][0],
            "caster_wanted": x_caster, "gisement_prevu": gisement, "n_nbrs_prevu": len(nbrs or []),
            "n_move_tiles": len(mt), "n_tiles": len(allp),
            "n_nonwalkable": len(nonwalk), "n_walkable_and_fog": len(onlyfog),
            "n_obscurcies": len(dark), "n_zone_native": len(zone),
            # LE VERDICT NATIF sur les tuiles NON MARCHABLES
            "n_nonwalkable_in_zone": len([t for t in nonwalk if t in zone]),
            "n_walkable_and_fog_in_zone": len([t for t in onlyfog if t in zone]),
            # LES TROIS MODELES
            "n_avant_fp": len(modeled_before - zone), "n_avant_fn": len(zone - modeled_before),
            "n_volet1_fp": len(modeled_walk - zone), "n_volet1_fn": len(zone - modeled_walk),
            "n_apres_fp": len(modeled_after - zone), "n_apres_fn": len(zone - modeled_after),
            "avant_fp": _why(sorted(modeled_before - zone)[:8]),
            "avant_fn": _why(sorted(zone - modeled_before)[:8]),
            "apres_fp": _why(sorted(modeled_after - zone)[:8]),
            "apres_fn": _why(sorted(zone - modeled_after)[:8]),
            # VENTILATION des faux positifs d'AVANT : par CAUSE, jamais un total nu
            "n_avant_fp_nonwalkable": len({t for t in (modeled_before - zone) if not walk.get(t)}),
            "n_avant_fp_onlyfog": len({t for t in (modeled_before - zone)
                                       if walk.get(t) and fog.get(t)}),
            "n_avant_fp_autre": len({t for t in (modeled_before - zone)
                                     if walk.get(t) and not fog.get(t)}),
        }
    finally:
        _dispose(sid, rid)


def step_read() -> int:
    """La table de verite du foyer -- aucun runner. Chaque ligne est un FAIT du decompile."""
    from engine.services import targeting_query as TQ
    print("tile_removed_by_walkability(rules, walkable, is_in_fog)  --  True = tuile RETIREE")
    print("  %-14s %-10s %-10s %s" % ("rules", "walkable", "is_in_fog", "retiree"))
    B = TQ.ALLOW_UNWALKABLE_TARGET_TILE
    cases = [
        # (rules, walkable, fog, attendu, pourquoi)
        (0x4002, False, False, True, "volet 1 : m.<+0x10> != 0"),
        (0x4002, False, None, True, "volet 1, canal fog muet"),
        (0x4002, True, True, True, "volet 2 : IsInFogOfWar (checkFog: true)"),
        (0x4002, True, False, False, "marchable et hors fog"),
        (0x4002, True, None, False, "volet 2 muet -> inerte"),
        (0x4002, None, True, True, "volet 1 muet, volet 2 mord"),
        (0x4002, None, None, False, "les DEUX canaux muets -> statu quo"),
        (0x4002 | B, False, True, False, "bit 43 AllowUnwalkableTargetTile -> aucun RemoveAll"),
        (None, False, True, False, "masque non RE-lu -> convention permissive"),
    ]
    bad = 0
    for rules, w, f, want, why in cases:
        got = TQ.tile_removed_by_walkability(rules, w, f)
        ok = (got == want)
        bad += 0 if ok else 1
        print("  %-14s %-10s %-10s %-8s %s  %s"
              % ("None" if rules is None else hex(int(rules)), w, f, got,
                 "OK" if ok else "KO", why))
    print("")
    print("AllowUnwalkableTargetTile = bit 43 = %s" % hex(B))
    print("INCOHERENCES : %d" % bad)
    return 1 if bad else 0


def step_boards(sid) -> int:
    """Inventaire LIVE des deux canaux, board par board -- ce qui justifie le choix des regimes."""
    rc = 0
    for b in BOARDS:
        rid, err = _build(b)
        if rid is None:
            print("  %-8s BUILD KO : %s" % (b, err.replace("\n", " ")[:200]))
            rc = 1
            continue
        try:
            _elev, walk, wall, fog = _board_maps(sid, rid)
            n = len(walk)
            nw = sum(1 for p in walk if not walk[p])
            wf = sum(1 for p in walk if walk[p] and fog.get(p))
            print("  %-8s tiles=%-4d nonwalkable=%-3d walkable_et_fog=%-3d murs=%d"
                  % (b, n, nw, wf, sum(1 for p in wall if wall[p])))
        finally:
            _dispose(sid, rid)
    return rc


def step_live(sid, board) -> int:
    res = live(sid, board)
    if "error" in res:
        print("  REFUS : %s" % res["error"])
        return 1
    print("  board=%s greffe=%s rules=%s caster=%s(team %s) pos=%r (voulue %r) moveTiles=%d"
          % (res["board"], res["reports"], hex(int(res["rules"])), res["caster"],
             res["caster_team"], res["caster_pos"], res["caster_wanted"], res["n_move_tiles"]))
    print("  plateau=%d tuiles : NON MARCHABLES=%d, marchables MAIS en FOG=%d, obscurcies=%d"
          % (res["n_tiles"], res["n_nonwalkable"], res["n_walkable_and_fog"], res["n_obscurcies"]))
    print("  zone NATIVE=%d tuiles ; elle en contient %d non marchables et %d en fog"
          % (res["n_zone_native"], res["n_nonwalkable_in_zone"],
             res["n_walkable_and_fog_in_zone"]))
    print("  port AVANT   : FP=%d FN=%d   (dont FP non marchables=%d, FP en fog=%d, FP autre=%d)"
          % (res["n_avant_fp"], res["n_avant_fn"], res["n_avant_fp_nonwalkable"],
             res["n_avant_fp_onlyfog"], res["n_avant_fp_autre"]))
    print("  port 1 VOLET : FP=%d FN=%d   (walkable seul -- le fog reste attribue a tort)"
          % (res["n_volet1_fp"], res["n_volet1_fn"]))
    print("  port APRES   : FP=%d FN=%d" % (res["n_apres_fp"], res["n_apres_fn"]))
    if res["apres_fp"]:
        print("    faux POSITIFS apres : %r" % (res["apres_fp"],))
    if res["apres_fn"]:
        print("    faux NEGATIFS apres : %r" % (res["apres_fn"],))
    return 0 if (res["n_apres_fp"] == 0 and res["n_apres_fn"] == 0) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="read", choices=["read", "live", "boards"])
    ap.add_argument("--board", default=BOARDS[0])
    a = ap.parse_args()
    if a.step == "read":
        return step_read()
    sid = _resolve_session()
    if not sid:
        print("aucune session Frida")
        return 1
    if a.step == "boards":
        return step_boards(sid)
    return step_live(sid, a.board)


if __name__ == "__main__":
    sys.exit(main())
