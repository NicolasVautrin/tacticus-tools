"""#348 -- l'APPROCHE d'un acteur de free-attack : `PerformAIAttack` (`+0x70 allowMoveAction = 1`,
`+0x78 moveAmount = null`) contre `...FromCurrentPosition` (`0` / `Direct(0)`).

CE QU'IL MESURE. Le corps unique
`IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute` passe le `Nullable<int>` de
`behaviour+0x78` TEL QUEL a `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles(unit,
ignoreFlags: true, overrideRange)` (lu VERBATIM dans
`...DefaultAiUnitTactic.u003CCalculateAbilityActionForUnitu003Ed__6$$MoveNext`) : `0` => la tuile
COURANTE seule, `null` => la PLAGE DE DEPLACEMENT normale de l'unite -- elle peut donc S'APPROCHER.
`allowMoveAction` (`+0x70`) ajoute en queue le `MovementActionGenerator` (`tactic+0x58`) : sans aucune
attaque possible, l'acteur fait un DEPLACEMENT PUR. Les messages rendus sont appliques par
`IdunBattle.Core.Services.AiControl$$ApplyAiMessages` dans l'ordre `MoveUnitMessage` puis
`ActiveAbilityMessage`.

PORTEUR CONFRONTABLE : `ForwardSpotter` (1143, MoW `astraOrdnanceBattery`). Son sous-behaviour
on-appearance est `PerformAIAttack(ActiveTarget@0x180, 1, 0, 0, 0)` -- le noeud allowMove/null. Et son
masque `0x40000422` porte `TargetIsFriendly` : le `astraSmnGuardsman` nait sur une tuile libre
ADJACENTE A UN ALLIE CHOISI, donc la distance spawn<->ennemi est ENTIEREMENT pilotable (on place
l'ancre, on bloque ses voisines sauf une, on marche l'ennemi a la distance voulue).

TROIS REGIMES, tous sur le MEME montage a une distance pres :
  * `approach`  : d(spawn, ennemi) dans [3 .. move+range]  -> le natif AVANCE puis FRAPPE
                  (le guardsman porte a 2 : Las range 2 ; Movement 3 -> portee effective 5) ;
  * `stay`      : d(spawn, ennemi) <= 2                    -> il FRAPPE SANS BOUGER (bras symetrique :
                  sans lui on ne mesure que « il bouge », pas « il bouge quand il faut ») ;
  * `move_only` : d(spawn, ennemi) > move+range            -> DEPLACEMENT PUR, aucun degat
                  (c'est le `MovementActionGenerator` d'`allowMoveAction`).

Le probe REFUSE de conclure si le montage n'est pas dans la fenetre du regime demande.

Re-derivation : `python probe_348_ai_approach.py --regime approach`
ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
_ROOT = _PYDIR.parents[1]

CARRIER_MOW = "astraOrdnanceBattery"   # MoW porteuse de 1143
ANCHOR_VIS = "astraBullgryn"           # cible FRIENDLY du cast -> ancre du spawn
#: `GC.ability("ForwardSpotter").constants.unitId` -- le jeu materialise `astraNpc1Guardsman`, meme
#: kit (Movement 3, arme Las portee 2). Le probe repere le summon comme NOUVELLE entite de la team,
#: jamais par ce nom.
SUMMON_VIS = "astraSmnGuardsman"       # l'acteur de la free-attack (Movement 3, Las range 2)
ENEMY_VIS = ("orksWarboss", "orksKillaKan")
ABILITY = 1143
SEED = "777"
BOARD = "MC1_67"
#: portee EFFECTIVE du guardsman = Movement + max(Range arme). Bornes des trois regimes.
REGIMES = {"approach": (3, 5), "stay": (1, 2), "move_only": (6, 99)}


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def build_args() -> list[str]:
    """Arguments `rl_duel build`. `--advance 0` : AUCUN tour joue -- toute la geometrie est POSEE
    par le probe (on deplace nos unites pendant notre tour, l'ennemi pendant le sien). `--dmg-target 1`
    neutralise la frappe adverse ; `--hp-target` garde les ennemis vivants sous l'attaque du summon."""
    return ["--p-mow", CARRIER_MOW,
            "--p-units", ",".join([ANCHOR_VIS] * 5),
            "--a-units", ",".join(ENEMY_VIS),
            "--board", BOARD,
            "--dmg-target", "1",
            "--hp-target", "900000",
            "--hp-player", "300000",
            "--advance", "0"]


def _build_subprocess() -> int:
    state = _ROOT / "logs" / ("_probe348-%d.json" % os.getpid())
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            "--state-file", str(state), *build_args()]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): "
                           + ((p.stderr or p.stdout or "")[-600:]))
    return json.loads(state.read_text())["runnerId"]


# --------------------------------------------------------------------------------------------- #
# Pilotage de geometrie
# --------------------------------------------------------------------------------------------- #

def _cur_player(rpc, rid):
    return (rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60) or {}).get("currentPlayer")


def _hand_to(rpc, rid, owner: int, tries: int = 6) -> bool:
    """Rend la main au joueur `owner`. L'IA ne joue PAS sur un `endturn` -> la geometrie ne bouge
    pas, seuls les flags de tour sont purges (ce qui redonne son deplacement a chaque unite)."""
    for _ in range(tries):
        if _cur_player(rpc, rid) == owner:
            return True
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return False


def _cycle_turn(rpc, rid, owner: int, tries: int = 8) -> bool:
    """Passe la main a l'AUTRE joueur puis la reprend : c'est le `StartTurnOperation` du retour qui
    purge les flags de tour (`RemoveTurnFlags`) et rend son deplacement a chaque unite. Un simple
    `_hand_to` ne suffit pas quand on est DEJA le joueur courant."""
    for _ in range(tries):
        if _cur_player(rpc, rid) != owner:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return _hand_to(rpc, rid, owner, tries)


def _live(rpc, rid):
    return {u["squadId"]: u for u in (rpc("observeBattle", {"runnerId": rid}, 40).get("units") or [])
            if not u.get("isDead")}


def _tile_of(board, u):
    return board.id_at(u["col"], u["row"])


def _movable(rpc, rid, sq: int) -> set:
    """Tuiles LEGALES de `sq` ce tour = RPC `aiMovableTiles` (`MovementQuery$$GetMovableTilesFor`).
    C'est la source du MOTEUR : viser une tuile hors de cet ensemble se solde par un refus SILENCIEUX
    (l'action est ignoree, `observeBattle` montre l'unite immobile) -- d'ou la lecture prealable
    plutot qu'une rafale d'essais."""
    r = rpc("aiMovableTiles", {"runnerId": rid, "side": "all"}, 60) or {}
    for u in (r.get("units") or []):
        if u.get("squadId") == sq or u.get("unitId") == sq or u.get("id") == sq:
            return {(t["col"], t["row"]) for t in (u.get("tiles") or u.get("movableTiles") or [])}
    return set()


def _bfs_from(board, dest: int) -> dict:
    """{tile: distance de CHEMIN a `dest`} sur les tuiles walkable, occupants IGNORES (ils bougeront).
    La distance HEX ne suffit pas a guider la marche : un mur la rend non monotone, et le pas glouton
    se coince dans un minimum local (mesure : bloqueur immobilise a 2 hex de sa tuile)."""
    from collections import deque
    seen = {dest: 0}
    q = deque([dest])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in seen and board.walkable(n):
                seen[n] = seen[x] + 1
                q.append(n)
    return seen


def _walk_to(rpc, rid, board, sq: int, dest: int, owner: int, max_turns: int = 10):
    """Amene l'unite `sq` sur la tuile `dest`, en autant de TOURS que necessaire (une unite ne
    dispose que de son `Movement` par tour ; `endturn` purge ses flags et lui rend son deplacement).
    A chaque tour : la tuile LEGALE dont la distance de CHEMIN a `dest` est la plus courte. Rend la
    tuile FINALEMENT atteinte (et non un booleen) : quand la marche echoue, c'est elle qui dit
    POURQUOI."""
    dist = _bfs_from(board, dest)
    here = None
    for _ in range(max_turns):
        U = _live(rpc, rid)
        if sq not in U:
            return None
        here = _tile_of(board, U[sq])
        if here == dest:
            return here
        if not _hand_to(rpc, rid, owner):
            return here
        legal = _movable(rpc, rid, sq)
        if not legal:
            # L'unite a DEJA bouge ce tour (`UnitFlag.Moved` -> `GetMovableTilesFor` rend un
            # ensemble VIDE). Il faut un VRAI cycle de tour : c'est `StartTurnOperation` qui purge
            # les flags (`RemoveTurnFlags`), pas le simple retour de la main.
            _cycle_turn(rpc, rid, owner)
            legal = _movable(rpc, rid, sq)
            if not legal:
                return here
        occ = {(u["col"], u["row"]) for s, u in U.items() if s != sq}
        cands = sorted((p for p in legal if p not in occ and board.id_at(*p) in dist),
                       key=lambda p: dist[board.id_at(*p)])
        if not cands or dist[board.id_at(*cands[0])] >= dist.get(here, 10 ** 6):
            return here
        c, r = cands[0]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": sq, "to": {"col": c, "row": r}}}, 60)
        U2 = _live(rpc, rid)
        if sq not in U2 or _tile_of(board, U2[sq]) == here:
            return here
    return _tile_of(board, _live(rpc, rid).get(sq, {}))


def _pick_geometry(board, d_lo: int, d_hi: int, max_blockers: int, mine_pos, foe_pos):
    """(anchor_tile, spawn_tile, blockers, enemy_tile) -- purement GEOMETRIQUE (pas d'occupation) :
      * `anchor_tile` a `n` voisines walkable, dont on bloquera `n-1` -> la tuile de spawn est
        DETERMINISTE (le natif prend `First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(
        target)), 7, owner), 1)` ; avec une seule candidate le tri ne tranche plus rien) ;
      * `spawn_tile` garde au moins 2 voisines LIBRES -> l'acteur peut reellement s'approcher ;
      * `enemy_tile` est a distance `d_lo..d_hi` de `spawn_tile` (fenetre du regime).
    La figure retenue MINIMISE le chemin a parcourir depuis les positions de depart (`mine_pos`,
    `foe_pos`) : chaque pas coute un tour de jeu, et un tour de plus est un tour de plus a rater.
    Rend None si le board n'offre pas la figure."""
    import hexgeo

    def _near(p, pts):
        return min((hexgeo.distance(p, q) for q in pts), default=0)

    best = None
    for a in sorted(board.by_id):
        if not board.walkable(a):
            continue
        nb = [n for n in board.neighbours(a) if board.walkable(n)]
        if not (2 <= len(nb) <= max_blockers + 1):
            continue
        for sp in nb:
            free_around = [n for n in board.neighbours(sp)
                           if board.walkable(n) and n != a and n not in nb]
            if len(free_around) < 2:
                continue
            blockers = [n for n in nb if n != sp]
            spp = board.coord(sp)
            ens = [t for t in sorted(board.by_id)
                   if board.walkable(t) and t not in (a, sp) and t not in blockers
                   and d_lo <= hexgeo.distance(board.coord(t), spp) <= d_hi]
            if not ens:
                continue
            e = min(ens, key=lambda t: _near(board.coord(t), foe_pos))
            cost = (_near(board.coord(a), mine_pos)
                    + sum(_near(board.coord(t), mine_pos) for t in blockers) / max(1, len(blockers))
                    + _near(board.coord(e), foe_pos))
            if best is None or cost < best[0]:
                best = (cost, (a, sp, blockers, e))
    return None if best is None else best[1]


# --------------------------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------------------------- #

def run(rpc, regime: str = "approach", build_runner=None, keep: bool = False) -> dict:
    r = _run(rpc, regime, build_runner, keep)
    if not keep and r.get("rid") is not None and not r.get("disposed"):
        try:
            rpc("disposeRunner", {"runnerId": r["rid"]}, 40)
        except Exception:                                # pragma: no cover (nettoyage best-effort)
            pass
    return r


def _run(rpc, regime: str, build_runner, keep: bool) -> dict:
    import hexgeo
    from engine.entities.pathfinding.board import Board
    from engine.runner.abilities.astramilitarum import ForwardSpotterAbility
    from engine.runner.components import PositionComponent, UnitComponent
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state

    d_lo, d_hi = REGIMES[regime]
    rid = (build_runner(SEED, extra=build_args())["rid"] if build_runner is not None
           else _build_subprocess())
    out = {"rid": rid, "regime": regime, "ok": False, "why": None}

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        out["why"] = "boardGraph indispo"
        return out
    board = Board(bg["tiles"], adjacency="native_sym")

    dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    mow = next((m for m in (dv0.get("mows") or []) if m.get("visualId") == CARRIER_MOW), None)
    if mow is None:
        out["why"] = "MoW %s absente" % CARRIER_MOW
        return out
    mow_id, owner = int(mow["casterId"]), int(mow.get("owner"))
    out["mow"] = mow_id

    U = _live(rpc, rid)
    mine = [s for s, u in sorted(U.items()) if u.get("teamId") == 1]
    foes = [s for s, u in sorted(U.items()) if u.get("teamId") == 2]
    if len(mine) < 2 or not foes:
        out["why"] = "roster live incomplet (mine=%d foes=%d)" % (len(mine), len(foes))
        return out

    geo = _pick_geometry(board, d_lo, d_hi, len(mine) - 1,
                         [(U[s]["col"], U[s]["row"]) for s in mine],
                         [(U[s]["col"], U[s]["row"]) for s in foes])
    if geo is None:
        out["why"] = "aucune figure (ancre, spawn, ennemi a d=%d..%d) sur %s" % (d_lo, d_hi, BOARD)
        return out
    a_tile, sp_tile, block_tiles, e_tile = geo
    if len(block_tiles) > len(mine) - 1:
        out["why"] = ("il faut %d bloqueurs, %d allies disponibles"
                      % (len(block_tiles), len(mine) - 1))
        return out
    out["plan"] = {"anchor": a_tile, "spawn": sp_tile, "blockers": block_tiles, "enemy": e_tile}

    # --- placement : ancre + bloqueurs (notre tour), puis l'ennemi (le sien), puis le 2e ennemi loin
    # AFFECTATION avant marche : chaque tuile de la figure va a l'allie qui en est le plus proche.
    # Sans elle, l'unite qui occupe DEJA la tuile visee par une autre bloque la figure pour toujours
    # (constate : le bloqueur vise 13, l'ancre y campe deja, plus personne n'avance).
    slots = [a_tile] + list(block_tiles)
    free_sq = list(mine)
    assign: dict = {}
    for t in slots:
        tp = board.coord(t)
        sq = min(free_sq, key=lambda s: hexgeo.distance((U[s]["col"], U[s]["row"]), tp))
        free_sq.remove(sq)
        assign[sq] = t
    anchor = next(s for s, t in assign.items() if t == a_tile)
    for _ in range(4):                              # quelques passes : les blocages mutuels se denouent
        todo = [s for s, t in assign.items()
                if _tile_of(board, _live(rpc, rid).get(s, {})) != t]
        if not todo:
            break
        for sq in todo:
            _walk_to(rpc, rid, board, sq, assign[sq], owner)
    bad = [(s, _tile_of(board, _live(rpc, rid).get(s, {})), t) for s, t in assign.items()
           if _tile_of(board, _live(rpc, rid).get(s, {})) != t]
    if bad:
        out["why"] = "figure alliee non tenue (u, atteint, vise) = %s" % (bad,)
        return out
    foe_owner = int((next(u for u in (dv0.get("units") or [])
                          if u.get("id") == foes[0]) or {}).get("owner"))
    for extra in foes[1:]:                          # les autres ennemis : PARQUES hors de tout
        far = max((t for t in board.by_id if board.walkable(t)),
                  key=lambda t: hexgeo.distance(board.coord(t), board.coord(sp_tile)))
        _walk_to(rpc, rid, board, extra, far, foe_owner)
    got = _walk_to(rpc, rid, board, foes[0], e_tile, foe_owner)
    if got != e_tile:
        out["why"] = "l'ennemi u%s bloque en %s, visait %s" % (foes[0], got, e_tile)
        return out

    if not _hand_to(rpc, rid, owner):
        out["why"] = "main non rendue au joueur %s avant le cast" % owner
        return out

    U = _live(rpc, rid)
    occ = {_tile_of(board, u): s for s, u in U.items()}
    out["geometry"] = {
        "anchor": {"squadId": anchor, "tile": _tile_of(board, U[anchor])},
        "spawn_tile": sp_tile, "spawn_free": sp_tile not in occ,
        "blocked": [(t, occ.get(t)) for t in block_tiles],
        "enemies": [{"squadId": s, "visualId": U[s].get("visualId"),
                     "tile": _tile_of(board, U[s]),
                     "d_spawn": hexgeo.distance(board.coord(sp_tile),
                                                (U[s]["col"], U[s]["row"]))}
                    for s in foes if s in U]}
    if _tile_of(board, U[anchor]) != a_tile or not out["geometry"]["spawn_free"]:
        out["why"] = "geometrie non tenue (ancre ou tuile de spawn)"
        return out
    if any(t not in occ for t in block_tiles):
        out["why"] = "voisines de l'ancre non toutes bloquees -> spawn non deterministe"
        return out
    d_near = min((e["d_spawn"] for e in out["geometry"]["enemies"]), default=99)
    out["d_near"] = d_near
    if not (d_lo <= d_near <= d_hi):
        out["why"] = "ennemi le plus proche a d=%s, hors fenetre %d..%d du regime %s" % (
            d_near, d_lo, d_hi, regime)
        return out

    # --- capture PRE-cast + execution OFFLINE (le PORT) ------------------------------------------
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    state = load_state(dv, ob, snap, board=board)
    if isinstance(rng0, dict) and rng0.get("mt"):
        mt = IntBasedMersenneTwister()
        mt.mt = list(rng0["mt"])
        mt.mti = rng0["mti"]
        state.rng = mt
    if state.get_entity(mow_id) is None or state.get_entity(anchor) is None:
        out["why"] = "MoW ou ancre absente offline"
        return out
    hp_pre_off = {s: U[s]["hp"] for s in foes if s in U}
    res = ForwardSpotterAbility().execute_behaviour(state, mow_id, anchor)
    spawned_off = (res or {}).get("spawned") or []
    out["off_tiles"] = (res or {}).get("tiles")
    out["off_spawned"] = spawned_off
    if spawned_off:
        pc = state.get_entity(spawned_off[0]).get_component(PositionComponent)
        out["off_pos"] = (pc.col, pc.row) if pc is not None else None
        out["off_tile"] = board.id_at(*out["off_pos"]) if out["off_pos"] else None
    out["off_moved"] = (out.get("off_tile") is not None and out["off_tile"] != sp_tile)
    out["off_dmg"] = {}
    for s in foes:
        e = state.get_entity(s)
        if e is None:
            continue
        from engine.runner.components import HealthComponent
        hc = e.get_component(HealthComponent)
        if hc is not None and hc.hp is not None:
            d = int(hc.hp) - int(hp_pre_off.get(s, hc.hp))
            if d:
                out["off_dmg"][U[s].get("visualId")] = d
    out["off_victim"] = next(iter(out["off_dmg"]), None)

    # --- cast LIVE (le NATIF) ---------------------------------------------------------------------
    pre = {s: u["hp"] for s, u in U.items()}
    ap = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": mow_id, "abilityType": ABILITY, "targetId": anchor}}, 120)
    out["live_mutated"] = bool(((ap or {}).get("actions") or [{}])[0].get("mutated"))
    post = _live(rpc, rid)
    # Le summon est identifie comme « nouvelle entite de MA team », PAS par son visualId : le
    # gameconfig annonce `unitId = astraSmnGuardsman`, le jeu materialise `astraNpc1Guardsman`
    # (meme kit -- Movement 3, arme Las portee 2). Gater sur le nom aurait rendu un ZERO qui se lit
    # comme « le natif n'a rien fait ».
    news = [s for s in post if s not in U and post[s].get("teamId") == 1]
    out["live_spawned"] = [(s, post[s].get("visualId")) for s in news]
    if not news:
        out["why"] = "aucun summon spawne live (mutated=%s)" % out["live_mutated"]
        return out
    g = post[news[0]]
    out["live_pos"] = (g["col"], g["row"])
    out["live_tile"] = board.id_at(g["col"], g["row"])
    out["live_moved"] = out["live_tile"] != sp_tile
    out["live_dmg"] = {u.get("visualId"): u["hp"] - pre.get(s, u["hp"])
                       for s, u in post.items()
                       if s in pre and u["hp"] - pre.get(s, u["hp"]) < 0}
    out["live_victim"] = next(iter(out["live_dmg"]), None)
    out["agree_moved"] = (out["off_moved"] == out["live_moved"])
    out["agree_tile"] = (out.get("off_tile") == out["live_tile"])
    out["agree_victim"] = (out["off_victim"] == out["live_victim"])
    out["ok"] = True
    if not keep:
        rpc("disposeRunner", {"runnerId": rid}, 40)
        out["disposed"] = True
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regime", default="approach", choices=sorted(REGIMES))
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    r = run(rpc, regime=a.regime, keep=a.keep)
    print("runner=%s regime=%s ok=%s why=%s" % (r["rid"], r["regime"], r["ok"], r.get("why")))
    if r.get("plan"):
        print("plan %s" % (r["plan"],))
    if not r.get("ok"):
        return 1
    g = r["geometry"]
    print("ancre u%s@%s | tuile de spawn %s (libre=%s) | bloquees %s"
          % (g["anchor"]["squadId"], g["anchor"]["tile"], g["spawn_tile"], g["spawn_free"],
             g["blocked"]))
    for e in g["enemies"]:
        print("   ennemi u%-4s %-14s tuile %s d(spawn)=%s" % (e["squadId"], e["visualId"],
                                                             e["tile"], e["d_spawn"]))
    print("[PORT] tuiles=%s spawn=%s -> tuile finale %s (bouge=%s) degats=%s"
          % (r["off_tiles"], r["off_spawned"], r.get("off_tile"), r["off_moved"], r["off_dmg"]))
    print("[LIVE] spawn=%s -> tuile finale %s (bouge=%s) degats=%s mutated=%s"
          % (r["live_spawned"], r["live_tile"], r["live_moved"], r["live_dmg"],
             r["live_mutated"]))
    print("ACCORD bouge=%s tuile=%s victime=%s"
          % (r["agree_moved"], r["agree_tile"], r["agree_victim"]))
    return 0 if (r["agree_moved"] and r["agree_tile"] and r["agree_victim"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
