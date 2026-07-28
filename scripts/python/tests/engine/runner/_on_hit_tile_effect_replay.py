"""Helper REUTILISABLE de REPLAY-DIFF pour les poses de TILE-EFFECT on-hit (`OnFireDamageAbility`
5, `OnToxicDamageAbility` 1244, ...).

Ces canaux ont une forme commune : `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`
emet `On(0x10)` apres un coup, un gate `DamageProfileHasTrait(<trait>)` filtre sur le profil de
l'arme, et la feuille `AddEffect(<effectType>, stateRef, Tiles(Target()))` pose l'effet sur la
MainTile de la CIBLE. Les confronter au live demande toujours le meme montage : amener le porteur au
contact, rejouer LA MEME attaque normale live et offline sur le MEME etat MT, puis comparer PV,
presence de l'effet sur la tuile, et **etat MT**.

`replay_on_hit_tile_effect(...)` rend une liste de confrontations (aucun `assert` ici -- le test
appelant decide) :

    [{profile, hits, live_hp, off_hp, live_effect, off_effect, mt_same, tile, mti_before,
      mti_off, mti_live}, ...]

DEUX PIEGES que ce helper encapsule -- les deux ont deja produit des faux verts :

  1. **Activation** : `currentPlayer == <moi>` NE SUFFIT PAS. Une unite qui a deja consomme son
     activation (typiquement un SUMMON apparu pendant le tour) n'est pas jouable, et `applyAction`
     rend alors `ok=True` **sans rien muter ni tirer**. La porte reelle est `decisionView.toActivate`.
  2. **Ordre placer/tirer** : un `applyAction move` peut faire BASCULER le joueur courant, et le cast
     qui suit est refuse EN SILENCE. On place donc D'ABORD, et on ne tire qu'a une iteration ou le
     plan ne demande PLUS de deplacement (« placer d'abord, atteindre son tour ensuite »).

Filet en sortie : une confrontation dont le MT live n'a PAS avance est rapportee `mt_same=None` et
`noop=True` -- c'est un coup NON JOUE cote live, jamais un ecart imputable au canal teste.

ASCII only.
"""
from __future__ import annotations

from collections import deque

from engine.entities.pathfinding.board import Board
from engine.runner.components import HealthComponent, PositionComponent
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(s["mt"]), s["mti"]
    return rng


def _bfs(board, src):
    dist, q = {src: 0}, deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def tiles_with_effect(rpc, rid, board, effect_type):
    """Ids de tuiles portant `effect_type` (lecture LIVE via `tileMeta`)."""
    tm = rpc("tileMeta", {"runnerId": rid}, 60) or {}
    out = set()
    for t in (tm.get("tiles") or []):
        if any(e.get("effectType") == effect_type for e in (t.get("effects") or [])):
            tid = board.id_at(t["col"], t["row"])
            if tid is not None:
                out.add(tid)
    return out


def drive_to_firing_position(rpc, rid, board, carrier_vis, rounds=14):
    """DRIVE les positions (doctrine : jamais « bloque par la geometrie de spawn ») jusqu'a ce que
    `carrier_vis` puisse TIRER SANS BOUGER pendant SON activation. Rend
    `(unitId, targetId, abilityType normal)`, ou None si aucun contact en `rounds` iterations.

    Encapsule les deux pieges de l'en-tete : gate `toActivate` (pas seulement `currentPlayer`) et
    « placer d'abord, tirer ensuite » (apres un move on RE-EVALUE au lieu de tirer dans la foulee)."""
    my = None
    for _ in range(rounds):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        units = dv.get("units") or []
        me = next((u for u in units if u.get("visualId") == carrier_vis and u.get("alive")), None)
        if me is None:
            return None
        if my is None:
            my = me.get("owner")
        if dv.get("currentPlayer") != my or me["id"] not in (dv.get("toActivate") or []):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        norm = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
        if norm is None:
            return None
        plan = next((p for p in (dv.get("attackPlans") or []) if p.get("unitId") == me["id"]), None)
        ev = next((e for e in ((plan or {}).get("evals") or [])
                   if e.get("targetId") is not None and (e.get("ranked") or [])), None)
        if ev is not None:
            rk = ev["ranked"][0]
            here = me.get("pos") or {}
            if rk.get("col") is None or (rk["col"], rk["row"]) == (here.get("col"), here.get("row")):
                return me["id"], ev["targetId"], norm["id"]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": rk["col"], "row": rk["row"]}}}, 60)
            continue                                   # RE-EVALUE : on ne tire pas juste apres un move
        pos = me.get("pos") or {}
        enemies = [u for u in units if u.get("owner") != my and u.get("alive") and (u.get("pos") or {})]
        if pos.get("col") is None or not enemies:
            return None
        tp = min(((u["pos"]["col"], u["pos"]["row"]) for u in enemies),
                 key=lambda p: abs(p[0] - pos["col"]) + abs(p[1] - pos["row"]))
        dist = _bfs(board, board.id_at(*tp))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60) or {}
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == me["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist]
        if pool:
            col, row = reach[min(pool, key=lambda t: dist[t])]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": col, "row": row}}}, 60)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None


def replay_on_hit_tile_effect(rpc, build_runner, carrier_vis, effect_type, p_units, a_units,
                              seed="777", board_id="MC1_67", max_attacks=12, stop_on_placement=True):
    """Confronte, attaque par attaque, la pose on-hit de `effect_type` par `carrier_vis`.

    Monte son propre runner (`build_runner`), amene le porteur en position de tir, puis pour chaque
    attaque : lit l'etat offline + le MT live (`dumpRng`), joue l'attaque LIVE, la rejoue OFFLINE sur
    ce MEME MT, et compare. S'arrete des qu'une POSE a ete confrontee (`stop_on_placement`) -- c'est
    le cas discriminant : sans elle on n'aurait valide que le NON-declenchement.

    Renvoie `(confrontations, rid)`. Une entree `noop=True` signale un coup NON JOUE cote live
    (MT inchange) : a ignorer, jamais a compter comme divergence."""
    b = build_runner(seed, extra=["--roster", "2", "--board", board_id,
                                  "--p-units", p_units, "--a-units", a_units])
    rid = b["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return [], rid
    board = Board(bg["tiles"], adjacency="evenq")

    out = []
    for _ in range(max_attacks):
        drive = drive_to_firing_position(rpc, rid, board, carrier_vis)
        if drive is None:
            break
        me_id, tgt_id, norm_id = drive

        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s1 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not _ok(s1):
            break
        state = load_state(dv2, ob2, snap, board=board)
        if state.effects is None:
            break
        state.rng = _seed_rng(s1)

        pc = state.get_entity(tgt_id).get_component(PositionComponent)
        tile = board.id_at(pc.col, pc.row) if pc is not None else None
        if tile is None or tile in tiles_with_effect(rpc, rid, board, effect_type):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue                                   # tuile deja porteuse -> non discriminant

        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": me_id, "targetId": tgt_id, "abilityType": norm_id}}, 60)
        if not (_ok(res) and (res.get("actions") or [{}])[0].get("ok")):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        live_hp = next((u.get("hp") for u in (res.get("units") or [])
                        if u.get("squadId") == tgt_id), None)
        live_eff = tile in tiles_with_effect(rpc, rid, board, effect_type)
        s2 = rpc("dumpRng", {"runnerId": rid}, 30)
        live_mt = (list(s2["mt"]), s2["mti"]) if _ok(s2) else None

        if live_mt is not None and live_mt[1] == s1["mti"] and live_mt[0] == list(s1["mt"]):
            out.append({"noop": True, "tile": tile, "mti_before": s1["mti"]})
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue

        runner = Runner(state).install_default_handlers(20)
        runner.apply(AttackUnitMessage(me_id, tgt_id))
        off_hp = state.get_entity(tgt_id).get_component(HealthComponent).hp
        off_eff = state.effects.has_effect(tile, effect_type=effect_type)
        last = runner.damage_handler.last or {}
        out.append({
            "noop": False, "profile": last.get("profile"), "hits": last.get("hits"),
            "rolls": last.get("rolls"), "live_hp": live_hp, "off_hp": off_hp,
            "live_effect": live_eff, "off_effect": off_eff, "tile": tile,
            "mti_before": s1["mti"], "mti_off": state.rng.mti,
            "mti_live": live_mt[1] if live_mt else None,
            "mt_same": (live_mt is not None
                        and (list(state.rng.mt), state.rng.mti) == (live_mt[0], live_mt[1])),
        })
        if stop_on_placement and live_eff:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return out, rid
