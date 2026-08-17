"""PROBE case-130 SS5 -- les quatre sites de placement `First(<tri>(...), 1)` : COMBIEN de tirages,
et QUELLE tuile ?

RESIDU NOMME de #130 (SS4) : `_pick_placement_tile` consommait **1 `genrand_int32` des que le pool
depassait 1**, alors qu'AUCUN de ses quatre appelants ne construit un `PickRandomly`. Les noeuds
natifs, lus un par un au decompile :

  * `ScarabHiveAbility$$ExecuteBehaviour` :
        Cache(First(Get(SelectTiles(SortByDistance(SortByDistance(
          CanAddUnit(AdjacentTiles(target@0x178)), caster@0x160), caster@0x160))), count), 1)
    -> `SortByDistanceSelector$$Select` = `OrderBy(dist(origin, tile))` (LINQ, STABLE). **0 tirage**.
  * `SquigHoundSummonUnitAbility$$CreateBehaviour` / `ControlEdictAbility$$SummonMinion` :
        First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(...)), 7, caster@0x160), 1)
    -> `SortTilesByUtilitySelector$$Select` = `OrderBy(-utility)` (STABLE). **0 tirage**.
  * `PileInAbility$$CreateBehaviour` :
        First(SortByFormula(Randomize(CanAddUnit(AdjacentTiles(self@0x148))),
              If(HasTrait(@0x180, 0x1b), Direct(0), Direct(1)), ascending=false), 1)
    -> `IdunBattleLogic.Entities.DSLSelectors$$Randomize` = `PickRandomAmountSelector(amount = 0x7fffffff)` = MELANGE COMPLET :
       **`len(pool)` tirages**, bornes DECROISSANTES (loi #130).

MESURE DIRECTE, PAS UN FIT : on compte le nombre EXACT de `genrand_int32` consommes LIVE par une
action (dumpRng avant/apres + re-simulation du Mersenne Twister : le nombre de pas EST le nombre de
tirages) et on le compare au nombre consomme par le PORT rejouant la MEME action sur le MEME etat
seede, sous DEUX modeles :
    M0 « 1 tirage des que le pool > 1 »   (le port d'AVANT, `_pick_placement_tile`)
    M1 « 0 tirage, tri natif porte »      (le DECOMPILE / le port d'APRES)
On compare AUSSI la TUILE choisie (deux flux RNG decales peuvent placer la meme unite : le comptage
seul ne suffit pas, l'egalite de tuile seule non plus -- il faut les DEUX).

Trois vecteurs live (porteurs HERO presents dans `--list-pool`) :
    --case scarabhive   : `necroSpyder` caste ScarabHive -> 2 `necroSmnSwarm` adjacents a la cible
                          (SortByDistance -> pool > 1 la norme : M0 sur-tire de 2).
    --case controledict : `admecMarshall` attaque -> le passif ControlEdict spawne 1
                          `admecSmnVanguard` adjacent au CASTER (SortTilesByUtilityForSummon ->
                          M0 sur-tire de 1). Vecteur PROPRE : ce noeud n'a **aucune on-appearance**,
                          donc le comptage live est confrontable sans residu.
    --case squighound   : `orksRuntherd` attaque -> le passif SquigHound spawne 1 `orksGrot` adjacent
                          a la CIBLE (MEME noeud de tri). Ce vecteur porte un residu CONNU et
                          ETRANGER au tri : l'on-appearance `PerformAIAttackFromCurrentPosition` du
                          grot n'est pas portee -> le live consomme des tirages que le port ne
                          rejoue pas. Le discriminant y est donc `M0 - M1` (le tirage parasite),
                          pas l'egalite absolue.

Usage :  python probe_130_placement_sort_rng.py [--case scarabhive|controledict|squighound|all]
                                                [--seed 777] [--board MC1_67]
Depuis scripts/python. ASCII only. Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

# {case: (porteur, ennemi, origine du spawn, nb de tuiles a poser)} -- `origin` = l'entite dont
# `AdjacentTiles(...)` fournit le pool dans le noeud natif (target@0x178 ou caster/self@0x148/0x160).
CASES = {
    "scarabhive":   {"caster": "necroSpyder",   "enemy": "necroDestroyer", "origin": "target", "n": 2},
    "controledict": {"caster": "admecMarshall", "enemy": "necroDestroyer", "origin": "caster", "n": 1},
    "squighound":   {"caster": "orksRuntherd",  "enemy": "necroDestroyer", "origin": "target", "n": 1},
}
BOARD = "MC1_67"


class Rpc:
    """Meme voie que la conftest : `rl_collect_batch._rpc(sid, method, [body], timeout_s)`."""

    def __init__(self):
        import rl_collect_batch as R
        self.R = R
        self.sid = R._resolve_session()

    def __call__(self, method, args=None, timeout=60):
        out = self.R._rpc(self.sid, method, [args] if args is not None else [], timeout=timeout)
        return out.get("result") if isinstance(out, dict) and "result" in out else out


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


# ------------------------------------------------------------------ comptage des genrand

def count_genrand(before, after, cap=600):
    """Nombre de `genrand_int32` entre deux etats (mt, mti) du MT natif -- par re-simulation."""
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt = list(before["mt"]); r.mti = int(before["mti"])
    tgt_mt, tgt_mti = list(after["mt"]), int(after["mti"])
    for n in range(cap + 1):
        if r.mti == tgt_mti and r.mt == tgt_mt:
            return n
        r.genrand_int32()
    return None


class CountingRng:
    """Compteur de `genrand_int32` cote PORT (cf. `probe_130_pick_randomly_one_rng.py`)."""

    def __init__(self, mt, mti):
        from engine.runner.prng import IntBasedMersenneTwister
        self.r = IntBasedMersenneTwister()
        self.r.mt = list(mt); self.r.mti = int(mti)
        self.n = 0

    def genrand_int32(self):
        self.n += 1
        return self.r.genrand_int32()

    def genrand_real2(self):
        self.n += 1
        return self.r.genrand_real2()

    def __getattr__(self, k):
        return getattr(self.r, k)

    def next_internal(self, lo, hi):
        from engine.runner.prng import _i32
        rng = hi - lo
        if (-rng & rng) == rng:
            return ((rng * (self.genrand_int32() >> 1)) >> 31) + lo
        while True:
            v0 = self.genrand_int32() >> 1
            v = v0 % rng
            if _i32((rng - 1) + (v0 - v)) >= 0:
                return v + lo

    def next(self, bound):
        return self.next_internal(0, bound)

    def next_bool(self, chance):
        return self.next_internal(1, 100) <= chance


# ------------------------------------------------------------------ modele M0 (le port d'AVANT)

class _LegacyPlacement:
    """Restaure le comportement d'AVANT sur les SEULS helpers de placement : pool en ids tries, tri
    natif ABSENT, et **1 tirage des que le pool depasse 1** (l'ex-`_pick_placement_tile`). Reproduit
    ICI, jamais importe : le fichier de production n'en garde aucune trace.

    ⚠ IL S'ANCRE SUR LES MIRRORS NATIFS NOMMES, PAS SUR UNE FORME D'ECRITURE (#462-r6). Les quatre
    sites de placement resolvent leur tuile par un noeud `First(<tri>(...), n)` : `_first` pour les
    trois sites a n = 1, et `_first_n` pour le site ScarabHive, dont le `count` vient du behaviour.
    Ce dernier s'ecrivait `[:count]` en slice ANONYME depuis `54c04b59` (le tile-selecteur s'evalue
    UNE fois) : le simulacre, qui ne patchait que `_first`, n'interceptait plus le chemin ScarabHive
    -- M0 et M1 rendaient le MEME compte, et le contre-controle rougissait en accusant le port. La
    lecon est generale : substituer un modele exige un point d'ancrage qui soit le MIRROR D'UN NOEUD
    NATIF (stable par construction), jamais un detail de la facon dont le port l'ecrit."""

    def __init__(self, state):
        self.state = state
        self.saved = {}

    def __enter__(self):
        import engine.runner.operations.spawn as SP
        st = self.state
        self.SP = SP
        for k in ("_sort_by_distance", "_sort_tiles_by_utility_for_summon", "_randomize",
                  "_first", "_first_n"):
            self.saved[k] = getattr(SP, k)

        def _identity_sorted(_st, tiles, _origin_id):
            return sorted(tiles)

        def _pick_placement_tile(tiles):
            if not tiles:
                return None
            if len(tiles) == 1 or st.rng is None:
                return tiles[0]
            return tiles[st.rng.next_internal(0, len(tiles))]

        def _pick_placement_tiles(tiles, count):
            """Le port d'AVANT sur le site a COUNT : une boucle `for _ in range(count)` qui
            RE-CHERCHAIT sa tuile a chaque tour dans le pool restant -- donc `_pick_placement_tile`
            applique `count` fois, en retirant la tuile prise. C'est ce que faisait
            `SpawnUnitOperation.execute` avant `54c04b59` (`tile = _first(_sort_by_distance(...))`
            DANS la boucle des summons), transpose sur la structure d'aujourd'hui."""
            rest, out = list(tiles), []
            for _ in range(max(0, int(count))):
                t = _pick_placement_tile(rest)
                if t is None:
                    break
                out.append(t)
                rest.remove(t)
            return out

        SP._sort_by_distance = _identity_sorted
        SP._sort_tiles_by_utility_for_summon = _identity_sorted
        SP._randomize = lambda _st, tiles: sorted(tiles)
        SP._first = _pick_placement_tile
        SP._first_n = _pick_placement_tiles
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            setattr(self.SP, k, v)
        return False


# ------------------------------------------------------------------ scenario live

def build(seed, state_file, p_units, a_units, extra=()):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(state_file),
           "--board", BOARD, "--roster", "1", "--p-units", p_units, "--a-units", a_units,
           "--hp-target", "90000", "--hp-player", "90000"] + list(extra)
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-600:])
        return None
    return json.loads(state_file.read_text())["runnerId"]


def _tiles_of(dv, board, pred):
    """{unitId: tileId} des unites de `dv` satisfaisant `pred` (vivantes, positionnees)."""
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos")
        if not (u.get("alive") and p and pred(u)):
            continue
        t = board.id_at(p["col"], p["row"])
        if t is not None:
            out[u["id"]] = t
    return out


_WT = None


def _tile_utility(board, tile_id, emax, emin):
    """Composite `Tile(7)` (`engine/utilities/tile.py`) evalue sur la seule metadata que le board du
    runner porte : elevation (+ min/max BOARD ENTIER, cf. `ElevationUtility$$LoadRelevantTileElevations`)
    et effets apportes par le terrain statique (`terrain_tile_effects` : Loop2 des abilities HEBERGEES
    + repli Loop1 pour les effets qu'une ability de terrain pose SUR la tuile, #155). C'est EXACTEMENT
    ce que porte `operations/spawn.py::_sort_tiles_by_utility_for_summon` sur un etat NON hydrate
    (`load_state` sans `tiles=`) -- recopie ici pour pouvoir CONSTRUIRE une geometrie ou le tri par
    utilite et l'ordre source DESACCORDENT (`--discriminate`), donc pour rendre le scenario live
    discriminant au lieu de tautologique."""
    global _WT
    from engine.utilities.tile import tile_composite, terrain_tile_effects
    if _WT is None:
        from engine.weights import load
        _WT = load()
    t = board.by_id.get(tile_id) or {}
    terr = board.tile_def_id(tile_id)
    meta = {"elevation": t.get("elevation"), "elevation_max": emax, "elevation_min": emin,
            "effects": terrain_tile_effects(terr)}
    return tile_composite(tile_id, meta, {}, _WT)


def _discriminating_caster_tile(board, occupied, exclude_tile):
    """Tuile CASTER dont l'anneau LIBRE (ordre natif `AdjacentTiles`, moins la tuile reservee a la
    cible) a son MAXIMUM d'utilite Tile(7) ailleurs qu'en TETE -> le tri par utilite et l'ordre
    source rendent des tuiles DIFFERENTES. Rend (tuile_caster, tuile_cible, [(tuile, utilite)]).

    ⚠ **LA PREMIERE GEOMETRIE QUI << DESACCORDE >> NE SUFFIT PAS, et c'est ce qui a rendu le
    contre-controle INERTE** (`test_utility_sort_scenario_really_discriminates`, rouge sur
    `master`). Le modele M0 n'est pas l'identite : c'est `sorted(tiles)` **puis un TIRAGE** des
    que le pool depasse 1. Sur un pool de DEUX, il a donc une chance sur deux de tomber sur la
    meme tuile que le tri -- et c'est exactement ce qui s'est produit (`pool natif [17, 26, 25]`,
    donc deux candidats apres retrait de la cible ; M0 a tire 26, le live valait 26). Le rouge
    n'accusait ni le port ni le harnais : il accusait le TIRAGE.

    On ne se contente donc plus de la premiere : on prend celle qui maximise le nombre de
    candidats STRICTEMENT moins bons que le maximum -- c'est-a-dire le nombre de tuiles que M0
    peut tirer et qui le feraient diverger. La probabilite de coincidence tombe de `1/2` a
    `1/len(pool)`. Elle ne devient pas NULLE, et cela reste vrai par construction : M0 tire, donc
    aucune geometrie ne peut lui interdire de tomber juste. Le prix d'un contre-controle bati sur
    un modele STOCHASTIQUE.
    """
    from engine.runner.operations import spawn as SP
    elevs = [t.get("elevation") for t in board.by_id.values() if t.get("elevation") is not None]
    emax, emin = (max(elevs), min(elevs)) if elevs else (None, None)
    meilleur = None
    for C in sorted(board.by_id):
        if not board.walkable(C) or C in occupied or C == exclude_tile:
            continue
        ring = [n for n in SP._adjacent_tiles(board, C)
                if board.walkable(n) and n not in occupied and n != exclude_tile]
        if len(ring) < 3:
            continue
        enemy_tile = ring[-1]
        pool = [(t, _tile_utility(board, t, emax, emin)) for t in ring if t != enemy_tile]
        us = [u for _t, u in pool]
        if max(us) <= us[0]:
            continue
        # candidats que M0 peut tirer et qui le feraient DIVERGER du tri
        umax = max(us)
        divergents = sum(1 for u in us if u < umax)
        if meilleur is None or divergents > meilleur[0]:
            meilleur = (divergents, C, enemy_tile, pool)
    if meilleur is None:
        return None
    return meilleur[1], meilleur[2], meilleur[3]


def _forced_caster_tile(board, occupied, exclude_tile, C):
    """Meme sortie que `_discriminating_caster_tile`, mais sur une tuile CASTER IMPOSEE (`--caster-tile`)
    -- pour REJOUER une geometrie precise (ex. celle qui a impose le -25 Swamp)."""
    from engine.runner.operations import spawn as SP
    elevs = [t.get("elevation") for t in board.by_id.values() if t.get("elevation") is not None]
    emax, emin = (max(elevs), min(elevs)) if elevs else (None, None)
    ring = [n for n in SP._adjacent_tiles(board, C)
            if board.walkable(n) and n not in occupied and n != exclude_tile]
    if len(ring) < 3:
        return None
    enemy_tile = ring[-1]
    return C, enemy_tile, [(t, _tile_utility(board, t, emax, emin)) for t in ring if t != enemy_tile]


def run_case(rpc, seed, case, discriminate=False, force_caster_tile=None):
    """Monte la geometrie, declenche l'action LIVE, capture l'etat AVANT + les tuiles de spawn."""
    import hexgeo
    from engine.entities.pathfinding.board import Board

    spec = CASES[case]
    caster_vis, enemy_vis = spec["caster"], spec["enemy"]
    state_file = ROOT / "logs" / "runners" / f"probe130c-{case}-{uuid.uuid4().hex[:8]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    rid = build(seed, state_file, caster_vis, enemy_vis)
    if rid is None:
        return None
    out = {"rid": rid, "state_file": state_file, "case": case}
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        print("boardGraph indispo"); return out
    board = Board(bg["tiles"], adjacency="native_sym")     # mode de PRODUCTION (scene.py)

    def dview():
        return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)

    def me_of(dv):
        return next((u for u in (dv.get("units") or [])
                     if u.get("visualId") == caster_vis and u.get("alive")), None)

    dv = dview()
    if not _ok(dv) or me_of(dv) is None:
        print("caster absent"); return out
    myplayer = me_of(dv).get("owner")
    for _ in range(6):
        dv = dview()
        if dv.get("currentPlayer") == myplayer:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    dv = dview()
    me = me_of(dv)
    if me is None or dv.get("currentPlayer") != myplayer:
        print("pas notre tour"); return out
    cid = me["id"]
    enemy = next((u for u in (dv.get("units") or [])
                  if u.get("owner") != myplayer and u.get("alive")
                  and u.get("visualId") == enemy_vis), None)
    if enemy is None:
        print("ennemi absent"); return out
    eid = enemy["id"]

    # --- geometrie : coller la cible a portee, sur une tuile a >= 2 voisins LIBRES (pool > 1 :
    #     c'est la ou M0 et M1 divergent ; a pool == 1 les deux modeles coincident).
    cpos = (me["pos"]["col"], me["pos"]["row"])
    ctile = board.id_at(*cpos)
    occupied = set(_tiles_of(dv, board, lambda u: True).values())

    def free_ring(t):
        return [n for n in board.neighbours(t)
                if board.walkable(n) and n != ctile and n not in occupied]

    # Le POOL du noeud est `AdjacentTiles(origin)` : pour `origin == "caster"` il ne depend pas de
    # la cible -- on exige seulement >= 2 voisins libres autour du caster (sinon M0/M1 coincident).
    want = spec["n"]
    need = max(2, want + 1)                        # >= 2 libres => pool > 1 => M0 tire
    if spec["origin"] == "caster" and discriminate:
        # SCENARIO DISCRIMINANT du TRI : on cherche une tuile CASTER dont l'anneau libre, PRIS DANS
        # L'ORDRE NATIF, place le MAXIMUM d'utilite AILLEURS qu'en tete. La ou le tri par utilite et
        # l'ordre source DESACCORDENT, une identite (ou un tirage) rend une AUTRE tuile que le natif.
        pick = _forced_caster_tile(board, occupied, ctile, force_caster_tile) \
            if force_caster_tile is not None else \
            _discriminating_caster_tile(board, occupied, ctile)
        if pick is None:
            print("aucune tuile caster ne fait DESACCORDER utilite et ordre natif sur ce board")
            return out
        C, enemy_tile, pool_dbg = pick
        print("  [discriminant] caster -> t%s ; pool natif %s ; meilleur = t%s (pas en tete)"
              % (C, [p[0] for p in pool_dbg], max(pool_dbg, key=lambda p: p[1])[0]))
        cc = board.coord(C)
        if not _ok(rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": cid, "to": {"col": cc[0], "row": cc[1]}}}, 60)):
            print("move caster KO"); return out
        cpos, ctile = cc, C
        occupied = set(_tiles_of(dview(), board, lambda u: True).values())
        cand = enemy_tile
    elif spec["origin"] == "caster":
        if len(free_ring(ctile)) < 2:
            print("caster sans >=2 voisins libres (pool trivial : M0 et M1 coincideraient)"); return out
        cand = next((t for t in sorted(board.by_id)
                     if board.walkable(t) and t not in occupied
                     and hexgeo.distance(board.coord(t), cpos) == 1), None)
    else:
        cand = next((t for t in sorted(board.by_id)
                     if board.walkable(t) and t not in occupied
                     and hexgeo.distance(board.coord(t), cpos) == 1
                     and len(free_ring(t)) >= need), None)
    if cand is None:
        print("geometrie (cible adjacente + voisins libres) introuvable"); return out
    c = board.coord(cand)
    mv = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": eid, "to": {"col": c[0], "row": c[1]}}}, 60)
    if not _ok(mv):
        print("move cible KO", str(mv)[:200]); return out

    dv = dview()
    me = me_of(dv)
    ability_id = None
    if case == "scarabhive":
        ab = next((a for a in (me.get("abilities") or [])
                   if str(a.get("name") or a.get("id") or "").lower().startswith("scarabhive")), None)
        if ab is None:
            ab = next((a for a in (me.get("abilities") or []) if a.get("kind") == "active"), None)
        if ab is None:
            print("ScarabHive introuvable"); return out
        ability_id = ab.get("id")
    else:
        ab = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
        if ab is None:
            print("attaque normale introuvable"); return out
        ability_id = ab.get("id")

    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    before = _tiles_of(dv, board, lambda u: True)
    rng_before = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(rng_before):
        print("dumpRng KO"); return out

    cast = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": eid, "abilityType": ability_id},
        "captureEvents": True}, 150)
    if not _ok(cast):
        print("action KO", str(cast)[:300]); return out
    rng_after = rpc("dumpRng", {"runnerId": rid}, 30)
    dv_after = dview()
    after = _tiles_of(dv_after, board, lambda u: True)
    spawn_tiles = sorted(t for uid, t in after.items() if uid not in before)

    out.update({"board": board, "dv": dv, "ob": ob, "snap": snap, "cid": cid, "target": eid,
                "ability_id": ability_id, "rng_before": rng_before, "rng_after": rng_after,
                "live_spawn_tiles": spawn_tiles})
    return out


def port_replay(reg, legacy: bool):
    """Rejoue l'action par le PORT REEL en modele M1 (helpers courants) ou M0 (placement d'avant),
    et rend (nb genrand, tuiles de spawn triees)."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import PositionComponent

    st = load_state(reg["dv"], reg["ob"], reg["snap"], board=reg["board"])
    st.rng = CountingRng(reg["rng_before"]["mt"], reg["rng_before"]["mti"])
    board = reg["board"]
    before_ids = set(st.entities.keys())

    def _run():
        if reg["case"] == "scarabhive":
            from engine.runner.abilities.loki import ScarabHiveAbility
            ScarabHiveAbility().execute_behaviour(st, reg["cid"], reg["target"])
        else:
            from engine.runner.runner import Runner
            from engine.runner.messages import AttackUnitMessage
            Runner(st).install_default_handlers(20).apply(
                AttackUnitMessage(reg["cid"], reg["target"]))

    if legacy:
        with _LegacyPlacement(st):
            _run()
    else:
        _run()

    tiles = []
    for eid in st.entities:
        if eid in before_ids:
            continue
        pc = st.get_entity(eid).get_component(PositionComponent)
        if pc is not None:
            t = board.id_at(pc.col, pc.row)
            if t is not None:
                tiles.append(t)
    return st.rng.n, sorted(tiles)


def dump_pool(reg):
    """Le POOL `CanAddUnit(AdjacentTiles(origin))` tel que le port le voit, dans l'ORDRE NATIF, avec
    l'elevation et l'utilite Tile(7) de chaque candidat -- pour savoir si le tri a REELLEMENT
    departage (elevations distinctes) ou s'il est retombe sur l'ordre source (toutes egales)."""
    from engine.runner.snapshot import load_state
    from engine.runner.operations import spawn as SP
    st = load_state(reg["dv"], reg["ob"], reg["snap"], board=reg["board"])
    origin = reg["cid"] if CASES[reg["case"]]["origin"] == "caster" else reg["target"]
    pool = SP._free_tiles_adjacent(st, origin, set(), native_order=True)
    board = reg["board"]
    elevs = [t.get("elevation") for t in board.by_id.values() if t.get("elevation") is not None]
    emax, emin = (max(elevs), min(elevs)) if elevs else (None, None)
    rows = [(t, (board.by_id.get(t) or {}).get("elevation"), board.tile_def_id(t),
             _tile_utility(board, t, emax, emin)) for t in pool]
    print("  pool (ordre natif AdjacentTiles) : " +
          " | ".join("t%s elev=%s %s u_candidat=%.0f" % r for r in rows))
    print("  ordre source (= identite)      : %s" % pool)
    print("  tri par distance-caster        : %s" % SP._sort_by_distance(st, pool, reg["cid"]))
    print("  tri par utilite-summon (porte) : %s"
          % SP._sort_tiles_by_utility_for_summon(st, pool, reg["cid"]))


def report(reg):
    dump_pool(reg)
    live_n = count_genrand(reg["rng_before"], reg["rng_after"])
    n1, tiles1 = port_replay(reg, legacy=False)
    n0, tiles0 = port_replay(reg, legacy=True)
    live_t = reg["live_spawn_tiles"]
    print("\n=== CASE %s ===" % reg["case"])
    print("  LIVE  genrand=%-4s spawn_tiles=%s" % (live_n, live_t))
    print("  M1 (tri natif porte, 0 tirage) genrand=%-4s spawn_tiles=%s  %s / %s"
          % (n1, tiles1, "COUNT OK" if n1 == live_n else "COUNT MISMATCH",
             "TILES OK" if tiles1 == live_t else "TILES MISMATCH"))
    print("  M0 (ex-_pick_placement_tile)   genrand=%-4s spawn_tiles=%s  %s / %s"
          % (n0, tiles0, "COUNT OK" if n0 == live_n else "COUNT MISMATCH",
             "TILES OK" if tiles0 == live_t else "TILES MISMATCH"))
    return {"case": reg["case"], "live_n": live_n, "m1_n": n1, "m0_n": n0,
            "live_tiles": live_t, "m1_tiles": tiles1, "m0_tiles": tiles0}


def main():
    global BOARD
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="all",
                    choices=["scarabhive", "controledict", "squighound", "all"])
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--discriminate", action="store_true",
                    help="place le caster pour que le TRI et l'ordre natif DESACCORDENT (origin=caster)")
    ap.add_argument("--caster-tile", type=int, default=None,
                    help="impose la tuile CASTER (avec --discriminate) pour rejouer une geometrie precise")
    args = ap.parse_args()
    BOARD = args.board
    rpc = Rpc()
    print("session=%s seed=%s board=%s" % (rpc.sid, args.seed, BOARD))

    cases = list(CASES) if args.case == "all" else [args.case]
    results = []
    for case in cases:
        reg = run_case(rpc, args.seed, case, discriminate=args.discriminate,
                       force_caster_tile=args.caster_tile)
        if reg is None:
            print("CASE %s : build KO" % case)
            continue
        try:
            if "rng_after" not in reg:
                print("CASE %s : setup KO" % case)
                continue
            results.append(report(reg))
        finally:
            try:
                rpc("disposeRunner", {"runnerId": reg["rid"]}, 20)
            except Exception:
                pass
            try:
                reg["state_file"].unlink()
            except Exception:
                pass

    print("\n=== VERDICT ===")
    for r in results:
        print("  %-11s live=%s | M1=%s (delta %s) | M0=%s (delta %s) | tiles M1 %s M0 %s"
              % (r["case"], r["live_n"], r["m1_n"],
                 None if r["live_n"] is None else r["m1_n"] - r["live_n"], r["m0_n"],
                 None if r["live_n"] is None else r["m0_n"] - r["live_n"],
                 "OK" if r["m1_tiles"] == r["live_tiles"] else "KO",
                 "OK" if r["m0_tiles"] == r["live_tiles"] else "KO"))
    print("  attendu : delta M1 = 0 ; delta M0 > 0 (1 tirage parasite par tuile placee)")


if __name__ == "__main__":
    main()
