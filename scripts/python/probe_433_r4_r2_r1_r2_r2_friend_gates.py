"""probe #433-r4-r2-r1-r2-r2 -- les DEUX gardes << ami >> du predicat de LIGNE DE VUE.

LE CRITERE BINAIRE. Le port REFUSE-t-il des tuiles que le natif ACCEPTE, faute d'alimenter les
gardes << ami >> de `TargetingQuery$$GetTilesObscuringTerrain` ? C'est le seul ecart RESTRICTIF de
toute la cascade de ciblage : le moteur SOUS-JOUE, il ecarte des actions legitimes.

CE QUE LA LECTURE A DONNE, ET QUI N'ETAIT PAS CE QU'ON CROYAIT. Les deux gardes ne lisent PAS la
meme chose, et la fiche precedente se trompait sur la premiere :

  b__1(target) = !IsFriend(target, caster, state) && GetTilesObscuringTerrain(...).Count > 0
  GetTilesObscuringTerrain : ... && !IsFriendOrHasFriendlyUnitOnIt(target, caster, state) && ...

  * `IdunBattle.Entities.UnitExtensions$$IsFriend` compare `GetCurrentPlayer(target)` et
    `GetCurrentPlayer(caster)`, chacun rabattu sur `0` faute de joueur. Or
    `IdunBattle.Entities.EntityExtensions$$GetCurrentPlayer` ne branche que sur `PlayerEntity`
    (rend `this`), `FootEntity` (`GetUnit` puis recursion) et `UnitEntity` (`OwnerComponent`), et
    retombe sinon sur un `TryGetComponent<OwnerComponent>` que la `TileEntity` NE PORTE PAS.
    Sur une TUILE elle rend donc `null` : la garde vaut `TeamId(caster) == Environment(0)`, une
    CONSTANTE DU CASTER. L'identite des quatre classes est etablie par leurs XREFS
    (`Blueprints$$UnitFoot` / `FootEntity$$Copy` pour celle qu'on prenait pour la tuile,
    `Blueprints$$Tile` / `TileEntity$$Copy` pour la vraie).
  * `IdunBattle.Entities.UnitExtensions$$IsFriendOrHasFriendlyUnitOnIt` passe, elle, par
    `IdunBattle.Entities.UnitExtensions$$GetUnit(target, state)`, qui TESTE `TileEntity`
    (`TileContentComponent+0x38`, `IsFilled`) et RESOUT l'occupant. Elle vaut donc
    << la tuile porte une unite de la MEME equipe que le caster >>, et c'est elle qui mord.

`PlayerComponent+0x24` est le `TeamId` : `IdunBattle.Entities.StateExtensions.u003CGetTeamPlayersu003Ed__39$$MoveNext`
filtre les joueurs par EXACTEMENT ce champ contre son argument `teamId`. L'enum
`IdunBattle.Core.TeamId` vaut `0=Environment, 1=Team1_Default, 2=Team2_DefaultEnemy, 3=Team3`.

L'ORACLE, et pourquoi ce n'est PAS celui de #568/#574. Le sweep `ncEvaluate` ne balaie que
`GetCurrentAndMovablePositionsFor(caster du playbook)` -- des tuiles LIBRES, plus l'origine
(occupee par une unite ENNEMIE du caster natif). Aucune de ces tuiles ne peut porter un ALLIE du
caster natif : ce montage est structurellement AVEUGLE a la garde qu'on veut mesurer. On prend donc
l'autre entree du MEME slot : `aiMovableTiles {threat: true}` invoque
`IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange(unit, moveTiles, true)` -- le slot
`0xe` que `BattleQuery$$IsTileInRangeOfAnyAbility` appelle lui aussi -- et sa zone couvre TOUT le
plateau, tuiles OCCUPEES comprises.

Ce que cela change au modele, et c'est LU : `casterTiles` y est le movable set, pas le singleton
`{GetMainTile}`. La surcharge LISTE de `MovementQuery$$GetTilesObscuringTerrain` INTERSECTE alors
les ensembles par tuile de depart -- mirror deja porte (#444), consomme ici tel quel.

LE MONTAGE, et son anti-degenerescence. Ability `UseWholeBoard` SANS gate dynamique et a
`ObscuringType == 6` greffee SEULE sur un porteur a arme de MELEE (le predicat est structurellement
MUET a `d = 1`, donc l'arme ne peut pas masquer la mesure) : la zone attendue est alors EXACTEMENT
le complementaire de l'obscurcissement, sur tout le plateau. Trois tuiles portent le verdict, et il
faut les TROIS -- deux d'entre elles sont les temoins qui empechent l'accord degenere :

    T_ami     obscurcie, occupee par un ALLIE du caster   -> natif ACCEPTE (garde), port AVANT: NON
    T_ennemi  obscurcie, occupee par un ENNEMI du caster  -> natif REFUSE  (la garde ne mord pas)
    T_vide    obscurcie, VIDE                             -> natif REFUSE  (l'etage mord bien ici)

Usage (ASCII only, depuis scripts/python) :
  python probe_433_r4_r2_r1_r2_r2_friend_gates.py --step read
  python probe_433_r4_r2_r1_r2_r2_friend_gates.py --step live
  python probe_433_r4_r2_r1_r2_r2_friend_gates.py --step live --board MC1_67
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

#: `custoBladeChampion` -- arme de MELEE seule (`unit_weapon_range == 1`), le greffon de #568.
GRAFT_HOST = "custoBladeChampion"
#: `1161 TwinSmartMissileSystem` : `UseWholeBoard`, AUCUN bit `AllowObscuredTarget*` (donc
#: `ObscuringType == 6`) et AUCUN `TargetMatchesDynamicRule` -- le 3e predicat n'est meme pas
#: construit. C'est le temoin le plus PUR du lot #568 : tout ce qui manque a sa zone vient de `b__1`.
GRAFT_ABILITY = 1161
#: L'ALLIE du caster natif (meme equipe que le greffon) et l'unite de NOTRE camp qui sert de temoin.
ALLY = "necroWarden"
FOE = "tauMarksman"
CASTER_TEAM_UNITS = "tauCrisis"
BOARD = "C6_17"        # murs `HulkWall` -- le volet du predicat qui mord le plus fort
SEED = "777"
MOVEMENT = 8           # de quoi PLACER les unites la ou le montage l'exige
#: `MovementOptions.OverrideRange` passe a `aiMovableTiles` AU MOMENT DE LA MESURE (le RPC l'ecrit
#: dans le `Nullable<int>@+0x4` des options de `MovementQuery$$GetMovableTilesFor`).
#:
#: POURQUOI CE LEVIER, ET PAS `--unit-stat Movement`. `casterTiles` est le movable set, et la
#: surcharge LISTE de `MovementQuery$$GetTilesObscuringTerrain` INTERSECTE les ensembles obtenus
#: depuis chaque tuile de depart : plus il est large, moins il reste d'obscurcissement. MESURE du
#: 2026-08-04 sur `C6_17` -- movable set complet : **0** tuile obscurcie sur tout le plateau,
#: montage DEGENERE ; `Movement = 1` (6 voisines) : 6 obscurcies, toutes des MURS. Il faut donc un
#: `casterTiles` PETIT *a la position choisie*, ce qu'un `--unit-stat` ne donne pas (il faut le
#: Movement pour PLACER l'unite, et le reduire APRES est impossible). `overrideRange` decouple les
#: deux : Movement large pour placer, portee 1 pour mesurer.
#: ⚠ `Movement = 0` rend un movable set VIDE, et `GetAllTilesInAbilityRange` rend alors une zone
#: VIDE (mesure) -- ce n'est pas utilisable non plus.
MEASURE_RANGE = 1


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _grafted_seed():
    """Seed BC ou `GRAFT_HOST` ne porte QUE `GRAFT_ABILITY` en ACTIVE, et ou `ALLY` est present."""
    import catalog_inject as CI
    from engine.entities.active_ability_type import ActiveAbilityType
    name = ActiveAbilityType(GRAFT_ABILITY).name
    out = ROOT / "logs" / "runners" / ("seedbc-friendgates-%s.json" % uuid.uuid4().hex[:6])
    out.parent.mkdir(parents=True, exist_ok=True)
    return CI.write_grafted_seed_bc(out, ["%s:%s" % (GRAFT_HOST, name)],
                                    replace=True, kind="active")


def _build(seed_bc):
    state = ROOT / "logs" / "runners" / ("p433r4r2r1r2r2-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
            "--state-file", str(state),
            "--p-units", "%s,%s" % (CASTER_TEAM_UNITS, FOE),
            "--a-units", "%s,%s" % (GRAFT_HOST, ALLY),
            "--hp-target", "90000", "--hp-player", "90000",
            "--unit-stat", "%s:Movement=%d" % (ALLY, MOVEMENT),
            "--unit-stat", "%s:Movement=%d" % (FOE, MOVEMENT),
            "--unit-stat", "%s:Movement=%d" % (GRAFT_HOST, MOVEMENT)]
    if seed_bc:
        argv += ["--seed-bc", str(seed_bc)]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return None, (p.stderr or p.stdout or "")[-2000:]
    return json.loads(state.read_text())["runnerId"], None


def _dispose(sid, rid):
    if rid is None:
        return
    try:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    except Exception:                                                 # pragma: no cover
        pass


def _board_maps(sid, rid):
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    tiles = bg.get("tiles") or []
    pos_of = {t["id"]: (t["col"], t["row"]) for t in tiles}
    elev = {pos_of[t["id"]]: t.get("elevation") for t in tiles}
    walk = {pos_of[t["id"]]: bool(t.get("walkable")) for t in tiles}
    wall = {pos_of[t["id"]]: bool(t.get("isWall")) for t in tiles}
    return elev, walk, wall


def _obs(sid, rid):
    """`{squadId: (pos, teamId, visualId)}` des unites VIVANTES."""
    o = _r(sid, "observeBattle", {"runnerId": rid}, 120)
    out = {}
    for u in (o.get("units") or []):
        if u.get("isDead") or u.get("col") is None:
            continue
        out[u["squadId"]] = ((u["col"], u["row"]), u.get("teamId"), u.get("visualId"))
    return out


def _threat(sid, rid, override_range=None):
    """`{squadId: (moveTiles, threatTiles)}` -- l'oracle `GetAllTilesInAbilityRange` du slot 0xe."""
    body = {"runnerId": rid, "threat": True, "side": "all"}
    if override_range is not None:
        body["overrideRange"] = int(override_range)
    mov = _r(sid, "aiMovableTiles", body, 150)
    out = {}
    for u in (mov.get("units") or []):
        out[u.get("unitId")] = ([(t["col"], t["row"]) for t in (u.get("tiles") or [])],
                                {(t["col"], t["row"]) for t in (u.get("threatTiles") or [])})
    return out


def _obscured_set(board, caster_tiles, rules, tiles, team_by_pos=None, caster_team=None):
    """Les tuiles que le port RETIRE -- avec ou sans les gardes, selon les deux derniers arguments.

    Foyer UNIQUE : `engine.services.targeting_query.target_is_obscured` (+ ses gardes). Le probe ne
    reecrit AUCUNE geometrie."""
    from engine.services import targeting_query as TQ
    out = set()
    for T in tiles:
        occ = (team_by_pos or {}).get(T)
        gf, gh = TQ.friend_gates_for_tile_target(caster_team, occ)
        if TQ.target_is_obscured(board, caster_tiles, T, rules,
                                 target_is_friend=gf, target_is_friend_or_has_friendly_unit=gh):
            out.add(T)
    return out


def _move(sid, rid, uid, to):
    _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": to[0], "row": to[1]}}}, 90)


def _place(sid, rid, wanted):
    """Amene chaque unite sur sa tuile voulue -- `{squadId: (col,row)}` -- en laissant tourner les
    tours. Rend les positions REELLEMENT atteintes (le verdict se lit sur l'etat FINAL, pas sur
    l'intention)."""
    for _ in range(8):
        cur = _obs(sid, rid)
        if all(cur.get(u, ((), None, None))[0] == p for u, p in wanted.items()):
            return cur
        for u, p in wanted.items():
            if cur.get(u, ((), None, None))[0] != p:
                _move(sid, rid, u, p)
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return _obs(sid, rid)


def _pick_caster_tile(board, elev, walk, wall, rules):
    """Choisit la tuile du GREFFON pour MAXIMISER le nombre de tuiles obscurcies -- au lieu de
    subir sa position de spawn.

    `casterTiles` a la mesure sera son movable set a portee 1, approxime ici par ses voisines
    walkables non-murales. Une position ouverte (6 voisines) fait une intersection qui ne retire
    rien ; une position de couloir (1-2 voisines) la rend mordante. Le port ne sert ici qu'a CHOISIR
    le montage : le verdict, lui, est la partition NATIVE, relue sur l'etat FINAL.

    Meme doctrine que `_pick_discriminant` de #574 -- on DEPLACE les unites pour obtenir la
    configuration voulue, on ne conclut pas << la geometrie de spawn ne le permet pas >>."""
    free = sorted(p for p in walk if walk[p] and not wall.get(p) and elev.get(p) is not None)
    best, best_n, best_nb = None, -1, None
    for X in free:
        nbrs = [tuple(n) for n in hexgeo.neighbors(X[0], X[1])
                if walk.get(tuple(n)) and not wall.get(tuple(n))]
        if not nbrs:
            continue                       # movable set vide -> zone vide (mesure), inutilisable
        dark = _obscured_set(board, nbrs, rules, free)
        n = len(dark)
        if n > best_n:                     # `>` strict : premiere position en ordre trie a egalite
            best, best_n, best_nb = X, n, nbrs
    return best, best_n, best_nb


def step_read() -> int:
    """La table de verite des DEUX gardes, et la REFUTATION -- aucun runner."""
    from engine.services import targeting_query as TQ
    print("friend_gates_for_tile_target(caster_team, occupant_team) -> (IsFriend, IsFriendOrHas)")
    print("  %-14s %-14s %s" % ("caster_team", "occupant_team", "(g1, g2)"))
    cases = [(1, None), (1, 1), (1, 2), (2, 2), (2, 1), (0, None), (0, 1), (0, 0), (None, 1)]
    bad = 0
    for ct, ot in cases:
        g1, g2 = TQ.friend_gates_for_tile_target(ct, ot)
        print("  %-14s %-14s (%s, %s)" % (ct, ot, g1, g2))
        # Le seul invariant falsifiable ici : g1 ne depend QUE du caster, g2 QUE de l'egalite.
        if g1 != (ct == TQ.TEAM_ENVIRONMENT if ct is not None else False):
            bad += 1
        if g2 != (ct is not None and ot is not None and ct == ot):
            bad += 1
    print("")
    print("TeamId.Environment = %d (IdunBattle.Core.TeamId : 0=Environment, 1=Team1_Default, "
          "2=Team2_DefaultEnemy, 3=Team3)" % TQ.TEAM_ENVIRONMENT)
    print("=> `IsFriend` sur une TUILE ne resout PAS l'occupant : elle vaut TeamId(caster)==0.")
    print("=> `IsFriendOrHasFriendlyUnitOnIt` le resout : c'est ELLE qui mord.")
    print("")
    print("INCOHERENCES : %d" % bad)
    return 1 if bad else 0


def live(sid, board=None) -> dict:
    """La MESURE, rendue en donnees (`{"error": ...}` sur refus) -- imprimee par `--step live`,
    assertionnee par le test live. La mesure n'existe qu'a UN endroit."""
    global BOARD
    if board:
        BOARD = board
    from engine.services import movement_query as MQ
    from engine.runner.abilities.targeting import targeting_options_for, unit_weapon_range

    wr = unit_weapon_range(GRAFT_HOST, None)
    if wr is None or int(wr) > 1:
        return {"error": "anti-degenerescence : le greffon %s a une arme de portee %s -- le "
                         "predicat est MUET a d=1, une arme plus longue masquerait la mesure"
                         % (GRAFT_HOST, wr)}
    rules = getattr(targeting_options_for(GRAFT_ABILITY), "rules", None)
    seed, reports = _grafted_seed()
    rid, err = _build(seed)
    if rid is None:
        return {"error": "build KO -- %s" % err}
    try:
        elev, walk, wall = _board_maps(sid, rid)
        board_obj = MQ.PositionBoard(elev, wall)
        allp = sorted(elev)
        u0 = _obs(sid, rid)
        by_vis = {v[2]: k for k, v in u0.items()}
        for need in (GRAFT_HOST, ALLY, FOE):
            if need not in by_vis:
                return {"error": "unite %s absente du runner (%r)" % (need, sorted(by_vis))}
        e_id, a_id, f_id = by_vis[GRAFT_HOST], by_vis[ALLY], by_vis[FOE]
        e_team = u0[e_id][1]
        if u0[a_id][1] != e_team:
            return {"error": "montage IMPUR : %s (team %s) n'est pas allie de %s (team %s)"
                    % (ALLY, u0[a_id][1], GRAFT_HOST, e_team)}
        if u0[f_id][1] == e_team:
            return {"error": "montage IMPUR : %s doit etre ENNEMI du greffon" % FOE}

        # 1) CHOIX du montage : la tuile du greffon qui maximise l'obscurcissement (le port ne
        #    sert qu'a choisir ; le verdict est la partition NATIVE, relue sur l'etat FINAL).
        x_caster, n_dark_pred, nbrs_pred = _pick_caster_tile(board_obj, elev, walk, wall, rules)
        if x_caster is None or n_dark_pred < 3:
            return {"error": "aucune position de caster ne rend >= 3 tuiles obscurcies sur %s "
                             "(meilleure = %r, %s obscurcies)" % (BOARD, x_caster, n_dark_pred)}
        _place(sid, rid, {e_id: x_caster})
        u_mid = _obs(sid, rid)
        if u_mid.get(e_id, ((), None, None))[0] != x_caster:
            return {"error": "greffon non amene en %r (reste en %r)"
                    % (x_caster, u_mid.get(e_id, ((), None, None))[0])}
        th0 = _threat(sid, rid, MEASURE_RANGE)
        mt0 = (th0.get(e_id) or ([], set()))[0]
        if not mt0:
            return {"error": "movable set du greffon VIDE -- `GetAllTilesInAbilityRange` rend un "
                             "ensemble vide, ce montage ne mesure rien"}
        occupied0 = {p for (p, _t, _v) in u_mid.values()}
        dark0 = _obscured_set(board_obj, mt0, rules, allp)
        cands = sorted(t for t in dark0
                       if walk.get(t) and not wall.get(t) and t not in occupied0)
        if len(cands) < 3:
            return {"error": "seulement %d tuile(s) obscurcie(s) libre(s) et walkable(s) sur %s -- "
                             "montage non discriminant (caster=%r, casterTiles=%d %r, plateau=%d, "
                             "obscurcies=%d, prevu=%d depuis %r)"
                             % (len(cands), BOARD, x_caster, len(mt0), sorted(mt0)[:8], len(allp),
                                len(dark0), n_dark_pred, nbrs_pred)}

        # 2) placer l'ALLIE et l'ENNEMI sur deux tuiles obscurcies, en gardant une 3e VIDE.
        #    On prend les plus PROCHES de chaque unite : elles doivent etre atteignables.
        a_from, f_from = u_mid[a_id][0], u_mid[f_id][0]
        t_ami = min(cands, key=lambda t: hexgeo.distance(t, a_from))
        rest = [t for t in cands if t != t_ami]
        t_foe = min(rest, key=lambda t: hexgeo.distance(t, f_from))
        got = _place(sid, rid, {a_id: t_ami, f_id: t_foe})

        # 3) VERDICT sur l'etat FINAL mesure -- positions relues, movable set relu, zone relue.
        #    ⚠ `GetMovableTilesFor(unit, ignoreUnitFlags: false, ...)` rend un ensemble VIDE pour
        #    une unite qui a deja consomme son mouvement ce tour-ci -- et les `endturn` du
        #    placement en laissent le greffon dans cet etat. On laisse donc tourner les tours
        #    jusqu'a ce qu'il redevienne mobile, SANS le deplacer, en verifiant a chaque passe que
        #    le montage tient toujours.
        u1, th1, mt1, zone = got, {}, [], set()
        for _ in range(6):
            th1 = _threat(sid, rid, MEASURE_RANGE)
            mt1 = (th1.get(e_id) or ([], set()))[0]
            zone = (th1.get(e_id) or ([], set()))[1]
            if mt1:
                break
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            u1 = _obs(sid, rid)
        if not mt1:
            return {"error": "movable set du greffon VIDE apres placement (unite non mobile sur "
                             "6 tours) -- `GetAllTilesInAbilityRange` rend une zone vide"}
        team_by_pos = {p: t for (p, t, _v) in u1.values() if t is not None}
        occupied1 = {p for (p, _t, _v) in u1.values()}
        # PERIMETRE DU SWEEP : les tuiles MARCHABLES. Le natif retire les non-marchables a un
        # etage AMONT de la ligne de vue (mesure ci-dessous : `n_nonwalkable_in_zone`), que ce
        # probe ne modelise pas -- il mesurerait alors un ecart qui n'est pas le sien.
        sweep = [t for t in allp if walk.get(t)]
        nonwalk = [t for t in allp if not walk.get(t)]
        n_nonwalk_in_zone = len([t for t in nonwalk if t in zone])
        dark1 = _obscured_set(board_obj, mt1, rules, sweep)     # port AVANT (gardes non lues)
        modeled_before = set(sweep) - dark1
        dark2 = _obscured_set(board_obj, mt1, rules, sweep,
                              team_by_pos=team_by_pos, caster_team=e_team)
        modeled_after = set(sweep) - dark2
        zone = zone & set(sweep)

        p_ami = u1[a_id][0]
        p_foe = u1[f_id][0]
        vides = sorted(t for t in dark1 if t not in occupied1)

        def _why(ts):
            """Chaque ecart NOMME par ce que le plateau en dit -- un `(col,row)` nu ne se
            diagnostique pas."""
            return [{"pos": t, "walkable": walk.get(t), "isWall": wall.get(t),
                     "elev": elev.get(t), "occupant_team": team_by_pos.get(t),
                     "d_caster": hexgeo.distance(t, u1[e_id][0])} for t in ts]

        return {
            "board": BOARD, "rules": rules, "reports": reports,
            "caster": GRAFT_HOST, "caster_team": e_team, "caster_pos": u1[e_id][0],
            "n_move_tiles": len(mt1), "move_tiles": sorted(mt1)[:8],
            "n_tiles": len(allp), "n_obscurcies": len(dark1),
            "n_sweep": len(sweep), "n_nonwalkable": len(nonwalk),
            "n_nonwalkable_in_zone": n_nonwalk_in_zone,
            "ally_pos": p_ami, "ally_wanted": t_ami, "ally_obscured": p_ami in dark1,
            "foe_pos": p_foe, "foe_wanted": t_foe, "foe_obscured": p_foe in dark1,
            "empty_dark_sample": vides[:6], "n_empty_dark": len(vides),
            # LES TROIS VERDICTS NATIFS
            "natif_accepte_T_ami": p_ami in zone,
            "natif_accepte_T_ennemi": p_foe in zone,
            "natif_accepte_T_vide": [t in zone for t in vides[:6]],
            # LES DEUX MODELES
            "avant_accepte_T_ami": p_ami in modeled_before,
            "apres_accepte_T_ami": p_ami in modeled_after,
            "avant_fp": _why(sorted(modeled_before - zone)[:8]),
            "avant_fn": _why(sorted(zone - modeled_before)[:8]),
            "apres_fp": _why(sorted(modeled_after - zone)[:8]),
            "apres_fn": _why(sorted(zone - modeled_after)[:8]),
            "n_avant_fp": len(modeled_before - zone), "n_avant_fn": len(zone - modeled_before),
            "n_apres_fp": len(modeled_after - zone), "n_apres_fn": len(zone - modeled_after),
        }
    finally:
        _dispose(sid, rid)


def step_live(sid, board) -> int:
    res = live(sid, board)
    if "error" in res:
        print("  REFUS : %s" % res["error"])
        return 1
    print("  board=%s greffe=%s rules=%s caster=%s(team %s) pos=%r moveTiles=%d %r"
          % (res["board"], res["reports"], hex(int(res["rules"])), res["caster"],
             res["caster_team"], res["caster_pos"], res["n_move_tiles"], res["move_tiles"]))
    print("  plateau=%d tuiles dont %d MARCHABLES (sweep) ; %d non-marchables, dont %d dans la "
          "zone NATIVE" % (res["n_tiles"], res["n_sweep"], res["n_nonwalkable"],
                           res["n_nonwalkable_in_zone"]))
    print("  obscurcies depuis le movable set=%d (dont VIDES=%d)"
          % (res["n_obscurcies"], res["n_empty_dark"]))
    print("  T_ami    = %r (voulue %r) obscurcie=%s -> NATIF accepte ? %s"
          % (res["ally_pos"], res["ally_wanted"], res["ally_obscured"],
             res["natif_accepte_T_ami"]))
    print("  T_ennemi = %r (voulue %r) obscurcie=%s -> NATIF accepte ? %s"
          % (res["foe_pos"], res["foe_wanted"], res["foe_obscured"],
             res["natif_accepte_T_ennemi"]))
    print("  T_vide   = %r -> NATIF accepte ? %r"
          % (res["empty_dark_sample"], res["natif_accepte_T_vide"]))
    print("  PORT sur T_ami : AVANT=%s  APRES=%s"
          % (res["avant_accepte_T_ami"], res["apres_accepte_T_ami"]))
    print("  ecart global  : AVANT FP=%d FN=%d | APRES FP=%d FN=%d"
          % (res["n_avant_fp"], res["n_avant_fn"], res["n_apres_fp"], res["n_apres_fn"]))
    if res["avant_fn"]:
        print("    faux NEGATIFS avant : %r" % (res["avant_fn"],))
    if res["apres_fn"]:
        print("    faux NEGATIFS apres : %r" % (res["apres_fn"],))
    if res["apres_fp"]:
        print("    faux POSITIFS apres : %r" % (res["apres_fp"],))
    return 0 if (res["n_apres_fp"] == 0 and res["n_apres_fn"] == 0) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="read", choices=["read", "live"])
    ap.add_argument("--board", default=None)
    a = ap.parse_args()
    if a.step == "read":
        return step_read()
    sid = _resolve_session()
    if not sid:
        print("aucune session Frida")
        return 1
    return step_live(sid, a.board)


if __name__ == "__main__":
    sys.exit(main())
