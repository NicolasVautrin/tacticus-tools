"""#338 -- le CHOIX DE CIBLE de `PerformAIAbilityUnitBehaviour$$Execute`, sur un regime INDEPENDANT
de celui de #334 (`DefendTheDivineWork`).

CE QU'IL MESURE. Le corps unique `IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute`
ne choisit pas de cible : il delegue a
`IdunBattle.Core.Services.AiControl$$ExecuteAbilityActionFor(unit, GetNormalAttackType(unit), options)`
-> `IdunBattle.AI.Tactics.DefaultAiUnitTactic.u003CCalculateAbilityActionForUnitu003Ed__6$$MoveNext`
-> `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator` -> `Bucket.ChooseAction`. Le port
l'approximait par « ennemi vivant le plus proche, tie-break id » (`_nearest_enemy`).

MONTAGE DISCRIMINANT (`AberrantHypermorph` 1166, `genesBiophagus` -- AUCUN rapport avec 1117/1119) :
DEUX ennemis ADJACENTS a la tuile de spawn du `genesSmnAberrant` (arme MELEE portee 1), donc a
DISTANCE EGALE du summon. `_nearest_enemy` ne peut alors les departager que par son tie-break `id`
-> il elit le PLUS PETIT id, quoi qu'il arrive. Le moteur d'utilite, lui, compare l'utilite de degat
`healthDmg / (maxHP + 1) * 100` : on donne aux deux ennemis des `Health` d'un ORDRE DE GRANDEUR
d'ecart (`--unit-stat`), si bien que le PETIT maxHP domine largement -- sans qu'aucun des deux ne
soit tuable (le summon frappe pour quelques milliers de PV), ce qui garde le montage stable pendant
l'`--advance`.

Le probe REFUSE de conclure si le montage n'est pas discriminant : il verifie que la cible du
tie-break `_nearest_enemy` DIFFERE de la cible elue. Si le tirage des ids tombe du mauvais cote, il
REJOUE en echangeant les deux `Health` (le petit maxHP passe sur l'autre ennemi).

Re-derivation : `python probe_338_ai_target_choice.py`
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

CARRIER = "genesBiophagus"          # porteur de l'active 1166
SUMMON_VIS = "genesSmnAberrant"     # le summon qui attaque a l'apparition
ENEMY_VIS = ("orksWarboss", "orksKillaKan")
ABILITY = 1166
SEED = "777"
BOARD = "MC1_67"
BIG_HP = 400000                     # maxHP ELEVE  -> utilite de degat FAIBLE
SMALL_HP = 40000                    # maxHP 10x plus petit -> utilite de degat ELEVEE


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def build_args(low_vis: str, advance: int) -> list[str]:
    """Arguments `rl_duel build` du montage. `low_vis` = l'ennemi qui porte le PETIT maxHP."""
    hi_vis = next(v for v in ENEMY_VIS if v != low_vis)
    stats = ";".join([
        "%s:Health=%d,RemainingHealth=%d" % (low_vis, SMALL_HP, SMALL_HP),
        "%s:Health=%d,RemainingHealth=%d" % (hi_vis, BIG_HP, BIG_HP)])
    return ["--p-units", CARRIER,
            "--a-units", ",".join(ENEMY_VIS),
            "--board", BOARD,
            "--unit-stat", stats,
            "--advance", str(advance),
            # la frappe adverse est neutralisee : sans ca le Biophagus meurt avant la mesure.
            "--dmg-target", "1"]


def _build_subprocess(low_vis: str, advance: int) -> int:
    state = _ROOT / "logs" / ("_probe338-%d.json" % os.getpid())
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            "--state-file", str(state), *build_args(low_vis, advance)]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): "
                           + ((p.stderr or p.stdout or "")[-500:]))
    return json.loads(state.read_text())["runnerId"]


def _move_to(rpc, rid, sq, tile, board):
    c, r = board.coord(tile)
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": sq, "to": {"col": c, "row": r}}}, 60)


def _hand_back(rpc, rid, owner: int, tries: int = 8) -> bool:
    """Rend la main au joueur `owner`. Deux raisons de devoir le faire, MESUREES :
    l'`--advance` laisse la partie a un tour arbitraire, et un `move` peut TERMINER le tour tout
    seul (« le tour se finit SEUL quand toutes tes units ont agi ») -- un cast hors tour rend
    `mutated:false` + un event `finish`, donc un ZERO qui se lirait comme une mesure.
    L'IA ne joue PAS sur un `endturn` (il faut `aiturn`), donc la geometrie ne bouge pas."""
    for _ in range(tries):
        cur = (rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60) or {}).get("currentPlayer")
        if cur == owner:
            return True
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return False


def _find_spawn_tile(board, live, sq_caster, enemy_tiles):
    """(spawn_tile, caster_tile) : une tuile T LIBRE adjacente aux DEUX ennemis, et un voisin LIBRE
    de T ou poser le caster (le cast 1166 exige `TargetIsTile|TargetTileIsFree` + range ADJACENT).
    On ne DEPLACE que le caster -- les ennemis, eux, sont amenes par l'`--advance`."""
    U = live()
    if len(enemy_tiles) < 2:
        return None
    occ = {board.id_at(u["col"], u["row"]) for u in U.values()}
    ctile = board.id_at(U[sq_caster]["col"], U[sq_caster]["row"])
    e0, e1 = enemy_tiles[0], enemy_tiles[1]
    shared = [t for t in board.neighbours(e0)
              if t in board.neighbours(e1) and t in board.by_id and board.walkable(t)
              and (t not in occ or t == ctile)]
    for T in shared:
        if T == ctile:
            continue                       # la tuile de spawn doit etre LIBRE
        for C in board.neighbours(T):
            if C not in board.by_id or not board.walkable(C):
                continue
            if C in occ and C != ctile:
                continue
            return T, C
    return None


def run(rpc, low_vis: str = ENEMY_VIS[1], advance: int = 4, build_runner=None,
        keep: bool = False) -> dict:
    """Monte le regime, caste 1166 OFFLINE puis LIVE, rend les mesures.

    Rend un dict : `ok`/`why`, `nearest` (ce que le RACCOURCI aurait elu), `off_target` /
    `live_victim` (la cible reellement frappee), `discriminant`, `geometry`."""
    import hexgeo
    from engine.entities.pathfinding.board import Board
    from engine.runner.abilities.loki import _nearest_enemy
    from engine.runner.components import (HealthComponent, PositionComponent, StatsComponent,
                                          UnitComponent)
    from engine.runner.operations.summon_ai import _apply_active_ability
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state

    if build_runner is not None:
        rid = build_runner(SEED, extra=build_args(low_vis, advance))["rid"]
    else:
        rid = _build_subprocess(low_vis, advance)
    out = {"rid": rid, "low_vis": low_vis, "advance": advance, "ok": False, "why": None}

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        out["why"] = "boardGraph indispo"
        return out
    board = Board(bg["tiles"], adjacency="native_sym")

    def live():
        return {u["squadId"]: u
                for u in (rpc("observeBattle", {"runnerId": rid}, 40).get("units") or [])
                if not u.get("isDead")}

    U = live()
    sq = {u.get("visualId"): s for s, u in U.items()}
    if CARRIER not in sq:
        out["why"] = "%s absent du live (mort pendant --advance ?)" % CARRIER
        return out

    dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60) or {}
    owner = next((u.get("owner") for u in (dv0.get("units") or [])
                  if u.get("visualId") == CARRIER), None)
    if owner is None:
        out["why"] = "owner du caster illisible (decisionView)"
        return out
    out["owner"] = owner
    if not _hand_back(rpc, rid, owner):
        out["why"] = "impossible de rendre la main au joueur %s du caster" % owner
        return out
    U = live()
    sq = {u.get("visualId"): s for s, u in U.items()}
    if CARRIER not in sq:
        out["why"] = "%s mort en rendant la main" % CARRIER
        return out
    enemy_sq = [s for s, u in sorted(U.items()) if u.get("teamId") == 2]
    if len(enemy_sq) < 2:
        out["why"] = "moins de 2 ennemis vivants"
        return out
    enemy_tiles = [board.id_at(U[s]["col"], U[s]["row"]) for s in enemy_sq]

    picked = _find_spawn_tile(board, live, sq[CARRIER], enemy_tiles)
    if picked is None:
        out["why"] = "aucune tuile libre adjacente aux DEUX ennemis avec un voisin libre"
        return out
    spawn_tile, caster_tile = picked
    _move_to(rpc, rid, sq[CARRIER], caster_tile, board)
    U = live()
    if board.id_at(U[sq[CARRIER]]["col"], U[sq[CARRIER]]["row"]) != caster_tile:
        out["why"] = "le caster n'a pas atteint la tuile voulue"
        return out
    # le `move` a pu TERMINER le tour (une seule unite agissante cote joueur) -> on le reprend.
    if not _hand_back(rpc, rid, owner):
        out["why"] = "main non rendue apres le deplacement du caster"
        return out

    sp = board.coord(spawn_tile)
    out["geometry"] = {
        "spawn_tile": spawn_tile, "spawn_pos": sp,
        "caster_pos": (U[sq[CARRIER]]["col"], U[sq[CARRIER]]["row"]),
        "enemies": [{"squadId": s, "visualId": U[s].get("visualId"),
                     "pos": (U[s]["col"], U[s]["row"]),
                     "hp": U[s].get("hp"), "hpMax": U[s].get("hpMax"),
                     "d_spawn": hexgeo.distance(sp, (U[s]["col"], U[s]["row"]))}
                    for s in enemy_sq]}
    if any(e["d_spawn"] != 1 for e in out["geometry"]["enemies"]):
        out["why"] = "les deux ennemis ne sont pas a d=1 de la tuile de spawn"
        return out

    # --- capture PRE-cast + cast OFFLINE ---------------------------------------------------------
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    state = load_state(dv, ob, snap, board=board)
    if isinstance(rng0, dict) and rng0.get("mt"):
        r = IntBasedMersenneTwister()
        r.mt = list(rng0["mt"])
        r.mti = rng0["mti"]
        state.rng = r

    def by_vis(vis):
        for uid, e in state.entities.items():
            uc = e.get_component(UnitComponent)
            if uc is not None and uc.visual_id == vis and uc.alive:
                return uid
        return None

    cid = by_vis(CARRIER)
    if cid is None:
        out["why"] = "caster absent offline"
        return out

    # CE QUE LE RACCOURCI AURAIT ELU. `_nearest_enemy` ne depend que des POSITIONS et du camp :
    # on l'evalue depuis une sonde POSEE sur la tuile de spawn (meme tuile, meme equipe que le
    # summon a naitre) -- donc sans avoir a caster d'abord.
    probe_uid = max(state.entities) + 1
    from engine.runner.components import OwnerComponent
    from engine.runner.state import Entity
    probe = Entity(probe_uid)
    coc = state.get_entity(cid).get_component(OwnerComponent)
    probe.add_component(OwnerComponent(team=coc.team, player=coc.player))
    probe.add_component(PositionComponent(col=sp[0], row=sp[1]))
    probe.add_component(UnitComponent(visual_id=SUMMON_VIS, alive=True))
    state.entities[probe_uid] = probe
    nearest = _nearest_enemy(state, probe_uid)
    del state.entities[probe_uid]
    out["nearest"] = nearest
    out["nearest_vis"] = (state.get_entity(nearest).get_component(UnitComponent).visual_id
                          if nearest is not None else None)

    hp_pre = {uid: int(e.get_component(HealthComponent).hp)
              for uid, e in state.entities.items()
              if e.get_component(HealthComponent) is not None
              and e.get_component(HealthComponent).hp is not None}
    res = _apply_active_ability(state, cid, spawn_tile, ABILITY)
    diag = (res or {}).get("diag") or {}
    out["ported"] = diag.get("ported")
    out["spawned"] = diag.get("spawned")
    out["off_attacks"] = diag.get("attacks")
    out["off_target"] = (diag.get("attacks") or [{}])[0].get("target")
    out["off_target_vis"] = None
    if out["off_target"] is not None:
        e = state.get_entity(out["off_target"])
        uc = e.get_component(UnitComponent) if e is not None else None
        out["off_target_vis"] = uc.visual_id if uc is not None else None
    out["off"] = {}
    for uid, pre in hp_pre.items():
        sc = state.get_entity(uid).get_component(StatsComponent)
        d = int(state.get_entity(uid).get_component(HealthComponent).hp) - pre
        vis = getattr(sc.ctx, "visual_id", None) if sc is not None else None
        if vis:
            out["off"][vis] = d

    # --- cast LIVE -------------------------------------------------------------------------------
    pre = {s: u["hp"] for s, u in live().items()}
    ap = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": sq[CARRIER], "abilityType": ABILITY,
        "to": {"col": sp[0], "row": sp[1]}}}, 120)
    # `mutated` FAUX = le cast n'a PAS eu lieu (hors tour, cible illegale...). Sans ce temoin, un
    # « zero degat live » se lirait comme une mesure du natif.
    out["live_mutated"] = bool(((ap or {}).get("actions") or [{}])[0].get("mutated"))
    post = live()
    out["live_summons"] = [(s, u.get("col"), u.get("row"))
                           for s, u in post.items() if u.get("visualId") == SUMMON_VIS]
    out["live"] = {u.get("visualId"): u["hp"] - pre.get(s, u["hp"]) for s, u in post.items()}
    hurt = [u.get("visualId") for s, u in post.items()
            if u.get("teamId") == 2 and (u["hp"] - pre.get(s, u["hp"])) < 0]
    out["live_victim"] = hurt[0] if len(hurt) == 1 else hurt
    out["live_enemy_loss"] = -sum(min(0, u["hp"] - pre.get(s, u["hp"]))
                                  for s, u in post.items() if u.get("teamId") == 2)
    out["off_enemy_loss"] = -sum(min(0, d) for v, d in out["off"].items() if v in ENEMY_VIS)
    # DISCRIMINANCE : le raccourci et le NATIF doivent designer des cibles DIFFERENTES. On la mesure
    # contre la victime LIVE, jamais contre celle du port -- sinon un port revenu au raccourci ferait
    # dire au montage « je ne discrimine plus », ce qui masquerait la regression au lieu de la lever.
    out["discriminant"] = (out["nearest_vis"] is not None
                           and isinstance(out["live_victim"], str)
                           and out["nearest_vis"] != out["live_victim"])
    out["ok"] = True

    if not keep:
        rpc("disposeRunner", {"runnerId": rid}, 40)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--advance", type=int, default=4)
    ap.add_argument("--low", default=None, help="visualId de l'ennemi a PETIT maxHP")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    lows = [a.low] if a.low else [ENEMY_VIS[1], ENEMY_VIS[0]]
    r = None
    for low in lows:
        r = run(rpc, low_vis=low, advance=a.advance, keep=a.keep)
        if r.get("ok") and r.get("discriminant"):
            break
        print("[retry] low=%s ok=%s why=%s discriminant=%s"
              % (low, r.get("ok"), r.get("why"), r.get("discriminant")))
    print("runner=%s low=%s ok=%s why=%s" % (r["rid"], r["low_vis"], r["ok"], r["why"]))
    if not r.get("ok"):
        return 1
    g = r["geometry"]
    print("tuile de spawn %s %s | caster %s" % (g["spawn_tile"], g["spawn_pos"], g["caster_pos"]))
    for e in g["enemies"]:
        print("   ennemi u%-4s %-14s %s d(spawn)=%s hp=%s/%s"
              % (e["squadId"], e["visualId"], e["pos"], e["d_spawn"], e["hp"], e["hpMax"]))
    print("RACCOURCI `_nearest_enemy` aurait elu : %s (u%s)" % (r["nearest_vis"], r["nearest"]))
    print("[PORT] ported=%s spawned=%s attaque=%s -> cible %s"
          % (r["ported"], r["spawned"], r["off_attacks"], r["off_target_vis"]))
    print("[PORT] deltas HP : %s" % ({k: v for k, v in r["off"].items() if v},))
    print("[LIVE] deltas HP : %s" % ({k: v for k, v in r["live"].items() if v},))
    print("victime LIVE = %s | victime PORT = %s | discriminant=%s"
          % (r["live_victim"], r["off_target_vis"], r["discriminant"]))
    print("perte ENNEMIE totale : live=%s port=%s" % (r["live_enemy_loss"], r["off_enemy_loss"]))
    print("[LIVE] summons=%s mutated=%s" % (r.get("live_summons"), r.get("live_mutated")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
