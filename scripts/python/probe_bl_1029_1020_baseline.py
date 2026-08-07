#!/usr/bin/env python
"""Probe BASELINE -- face COMBAT de Drachnyen (1029, blackAbaddon) et HeraldOfTheApocalypse
(1020, blackHaarken), AVANT port.

But (etape « verifier que le trou est bien celui-la ») : monter les DEUX casts LIVE dans un runner
isole, mesurer (a) ce que le natif fait reellement (degat par cible, PV du caster, effets poses),
(b) ce que le port fait AUJOURD'HUI sur le MEME message (`AbilityHandler.last`), pour prouver le
NO-OP silencieux (`ported:False`) plutot que de le supposer.

Geometries montees (drive des 2 camps, `applyAction` ignore propriete/portee) :
  - Drachnyen : Abaddon adjacent a une cible.
  - Herald    : Haarken adjacent a T, et B sur la tuile DERRIERE T dans l'axe caster->T
                (`TilesBehindInLine(from=CasterTile, to=TargetTile, maxCount=2)`).

⚠ NE JAMAIS deplacer le CASTER pour rien : son activation est consommee, la main passe a l'autre camp
et le cast suivant est REFUSE par le gate de cible (signature : `actionConsumed:false`, cascade a
2 events, `currentPlayer` != owner du caster). Les deux layouts ANCRENT donc sur la tuile courante du
caster et ne bougent que les ennemis.

MESURE DE REFERENCE (seed 777, board MC1_67, AVANT port) :
  DRACHNYEN offline `ported:false` deltas PV {} | live deltas PV {77: 14336, 83: 3558} (10038 -> 6480)
  HERALD    offline `ported:false` deltas PV {} | live {77:[2671,2973,2806], 79:[2755,2539,2419]}

ASCII only (cp1252). Usage: python probe_bl_1029_1020_baseline.py [--seed 777] [--board MC1_67]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.runner.snapshot import load_state  # noqa: E402
from engine.runner.runner import Runner  # noqa: E402
from engine.runner.messages import ActiveAbilityMessage  # noqa: E402
from engine.runner.components import HealthComponent, PositionComponent  # noqa: E402
from engine.entities.pathfinding.board import Board  # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister  # noqa: E402
from engine import battle_query  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_bl_1029_1020_baseline.json"
ABADDON, HAARKEN = "blackAbaddon", "blackHaarken"
ENEMIES = "necroWarden,necroDestroyer,necroOverlord"
DRACHNYEN, HERALD = 1029, 1020


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def build(seed, board, hp_target, p_units=None):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(STATE), "--board", board,
            "--p-units", p_units or f"{ABADDON},{HAARKEN}", "--a-units", ENEMIES]
    if hp_target:
        argv += ["--hp-target", str(hp_target)]
    proc = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[bl] build KO: {(proc.stderr or proc.stdout or '')[-500:]}")
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _cascade(r):
    out = list(r.get("cascade") or [])
    for a in (r.get("actions") or []):
        out += list(a.get("events") or [])
    return out


def _tags(ev):
    try:
        return json.loads(ev.get("tags") or "{}")
    except Exception:
        return {}


def _off_hp(state, uid):
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def _off_pos(state, uid):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _live_damage_by_target(cascade):
    """Amount par cible, tous groupes confondus (le cast Drachnyen enchaine attaque normale + extra)."""
    out = {}
    for ev in cascade:
        t = _tags(ev)
        if "Amount" in t and t.get("Target_Id") is not None:
            out.setdefault(t["Target_Id"], []).append(t["Amount"])
    return out


def _live_hp_after(cascade, uid):
    last = None
    for ev in cascade:
        t = _tags(ev)
        if ev.get("entity") == uid and "UnitStats_RemainingHealth" in t:
            last = int(t["UnitStats_RemainingHealth"])
    return last


def _dv(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 150)


def _alive(dec):
    return [u for u in (dec.get("units") or []) if u.get("alive")]


def _mine_turn(rpc, rid, owner):
    for _ in range(12):
        dec = _dv(rpc, rid)
        if dec.get("currentPlayer") == owner:
            return dec
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None


def _move(rpc, rid, uid, coord):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": coord[0], "row": coord[1]}}}, 90)


def _behind(board, frm, to):
    """`TilesBehindInLine(from, to, settings{1,1}, 2)` -> [to, tuile derriere]."""
    pos = battle_query.get_tiles_behind(
        frm, to, max_count=2, check_walkable=True, update_reference=True,
        walkable_at=lambda p: board.walkable(board.id_at(p[0], p[1])),
        elevation_at=lambda p: board.elevation(board.id_at(p[0], p[1])),
        tile_exists=lambda p: board.id_at(p[0], p[1]) is not None)
    return pos


def _wound_caster(rpc, rid, caster_id, enemy_ids, rounds=3):
    """Abime le caster (drive des ennemis adjacents) — tentative de rendre le SetHealth plus lisible.
    S'est averee INUTILE sur blackAbaddon (TerminatorArmour -75 % + attaques hors tour : PV inchanges),
    et SURTOUT superflue : `hp[level]` (6480 au rank 17) est INFERIEUR au MaxHealth (10038), donc le SET
    fait deja PERDRE des PV a PV pleins -- il est observable sans blesser qui que ce soit. Conservee
    telle quelle (inerte) parce qu'elle documente cette impasse."""
    for _ in range(rounds):
        for eid in enemy_ids:
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "attack", "unitId": eid, "targetId": caster_id}}, 120)


def _report(tag, rpc, rid, board, caster_vis, ability, layout, wound=False):
    """layout(dec, caster, enemies) -> (caster_coord, {enemy_id: coord}, target_id) ou None."""
    dec = _dv(rpc, rid)
    cst = next((u for u in _alive(dec) if u.get("visualId") == caster_vis), None)
    if cst is None:
        print(f"[bl] {tag}: caster {caster_vis} absent"); return None
    dec = _mine_turn(rpc, rid, cst.get("owner"))
    if dec is None:
        print(f"[bl] {tag}: jamais mon tour"); return None
    cst = next((u for u in _alive(dec) if u.get("visualId") == caster_vis), None)
    ens = [u for u in _alive(dec) if u.get("owner") != cst.get("owner")]
    plan = layout(dec, cst, ens)
    if plan is None:
        print(f"[bl] {tag}: geometrie introuvable"); return None
    ccoord, ecoords, tgt_vis_idx = plan
    if _pos(cst) != ccoord:                   # ne JAMAIS bouger le caster pour rien : ca consomme son
        _move(rpc, rid, cst["id"], ccoord)    # activation et fait passer la main a l'autre camp
    for eid, c in ecoords.items():
        _move(rpc, rid, eid, c)
    dec = _dv(rpc, rid)
    cst = next((u for u in _alive(dec) if u.get("id") == cst["id"]), None)
    ens = {u["id"]: _pos(u) for u in _alive(dec) if u.get("owner") != cst.get("owner")}
    print(f"[bl] {tag}: caster={cst['id']}@{_pos(cst)} enemies={ens}")
    tgt = tgt_vis_idx
    if _pos(cst) != ccoord or ens.get(tgt) != ecoords.get(tgt):
        print(f"[bl] {tag}: WARN geometrie partielle (voulu caster={ccoord} enemies={ecoords})")
    if wound:
        _wound_caster(rpc, rid, cst["id"], list(ecoords))
        dec = _dv(rpc, rid)
        cst = next((u for u in _alive(dec) if u.get("id") == cst["id"]), None)
        if cst is None:
            print(f"[bl] {tag}: caster mort pendant le wound"); return None
        print(f"[bl] {tag}: caster abime -> hp={cst.get('hp')}")

    print(f"[bl] {tag}: caster dv-entry = {json.dumps({k: v for k, v in cst.items() if k in ('id','visualId','owner','hp','pos','abilities','flags','canAct','finished','moved')})[:900]}")
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    pre_hp = {u["id"]: u.get("hp") for u in _alive(dec)}
    state = load_state(dec, ob, snap, board=board)
    if s0 and s0.get("mt"):
        state.rng = _seed_rng(s0)

    # --- OFFLINE d'abord (etat pre-cast) : que fait le port AUJOURD'HUI ? ---
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=cst["id"], target_id=tgt, ability_type=ability))
    last = runner.ability_handler.last or {}
    off_hp = {uid: _off_hp(state, uid) for uid in pre_hp}
    off_delta = {uid: (pre_hp[uid] - off_hp[uid]) for uid in pre_hp
                 if pre_hp[uid] is not None and off_hp[uid] is not None and off_hp[uid] != pre_hp[uid]}
    # `default=str` : le retour d'une ability porte, en profondeur, l'`attack_state` d'un
    # `AttackDamageOperation` (`operations/damage_hits.attack_state_out`), dont `failed_block` est un
    # **`set`**. Sans ce `default`, l'oracle tombe sur un `TypeError` -- un echec de MONTAGE qui
    # ressemble a une mesure. #BL-1029r : le canal est devenu non vide le jour ou une triggered
    # `On(0x26 = NormalAttack)` est entree au registre pour ce caster.
    print(f"[bl] {tag}: OFFLINE handler.last={json.dumps(last, default=str)[:1400]}")
    # Canal AFTER-HIT de la voie `UseActiveAbility` (#BL-1029r) : c'est la que remontent les
    # triggers `On(0x26 = NormalAttack)` d'une attaque normale DISPATCHEE par une ability. Sans
    # cette ligne, un trigger qui fire n'est visible que par son effet sur les PV.
    _uaa = ((last.get("attack") or {}) if isinstance(last, dict) else {})
    if isinstance(_uaa, dict) and _uaa.get("after_hit"):
        print(f"[bl] {tag}: OFFLINE after_hit(UseActiveAbility)="
              f"{json.dumps(_uaa.get('after_hit'), default=str)[:1600]}")
    print(f"[bl] {tag}: OFFLINE deltas PV = {off_delta}")

    # --- CAST LIVE ---
    r = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cst["id"], "targetId": tgt, "abilityType": ability}}, 240)
    a0 = ((r or {}).get("actions") or [{}])[0]
    if not a0.get("ok"):
        print(f"[bl] {tag}: cast LIVE KO {str(r)[:300]}")
        return None
    casc = _cascade(r)
    dmg = _live_damage_by_target(casc)
    if not dmg:
        print(f"[bl] {tag}: RAW action = {json.dumps(a0)[:1500]}")
    dec2 = _dv(rpc, rid)
    post = {u["id"]: u.get("hp") for u in (dec2.get("units") or [])}
    live_delta = {uid: (pre_hp[uid] - post.get(uid)) for uid in pre_hp
                  if post.get(uid) is not None and pre_hp[uid] is not None and post[uid] != pre_hp[uid]}
    print(f"[bl] {tag}: LIVE amounts par cible = {json.dumps(dmg)}")
    print(f"[bl] {tag}: LIVE deltas PV = {live_delta}  (caster {cst['id']}: {pre_hp.get(cst['id'])} -> {post.get(cst['id'])})")
    ceff = next((u.get("effects") for u in (dec2.get("units") or []) if u.get("id") == cst["id"]), None)
    print(f"[bl] {tag}: LIVE effets du caster apres cast = {json.dumps(ceff)[:600]}")
    for uid in ens:
        e = next((u.get("effects") for u in (dec2.get("units") or []) if u.get("id") == uid), None)
        print(f"[bl] {tag}: LIVE effets ennemi {uid} = {json.dumps(e)[:400]}")
    # groupes de la cascade (structure des sous-attaques)
    groups = [ev.get("source") for ev in casc if ev.get("kind") == "group"]
    print(f"[bl] {tag}: LIVE groupes = {groups}")
    return {"live": dmg, "off": last}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--hp-target", default="500000")
    ap.add_argument("--only", default="both", choices=("both", "drachnyen", "herald"))
    ap.add_argument("--p-units", default=None,
                    help="roster joueur explicite (ex. blackHaarken SEUL = pas d'aura FirstAmongTraitors)")
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed, args.board, args.hp_target, args.p_units)
    rpc = lambda m, b, t=90: _r(sid, m, b, t)  # noqa: E731
    print(f"[bl] seed={args.seed} board={args.board} runner={rid} hp_target={args.hp_target}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print("[bl] boardGraph KO"); return 2
        board = Board(bg["tiles"], adjacency="native_sym")

        def layout_adjacent(dec, cst, ens):
            """ANCRE sur la tuile COURANTE du caster (les tuiles lointaines sont hors portee de move) :
            2 ennemis sur deux voisins libres."""
            C = _pos(cst)
            occ = {_pos(u) for u in _alive(dec)} - {C}
            nb = [board.coord(t) for t in sorted(board.by_id)
                  if board.walkable(t) and hexgeo.distance(board.coord(t), C) == 1
                  and board.coord(t) not in occ]
            if len(nb) < 2:
                return None
            return C, {ens[0]["id"]: nb[0], ens[1]["id"]: nb[1]}, ens[0]["id"]

        def layout_line(dec, cst, ens):
            """ANCRE sur la tuile COURANTE du caster (bouger le caster CONSOMME son activation -> la
            main passe a l'autre camp et le cast est refuse) : cible T adjacente, B sur la tuile
            DERRIERE T dans l'axe C->T."""
            C = _pos(cst)
            cands = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]
            cset = set(cands)
            for T in [c for c in cands if hexgeo.distance(c, C) == 1]:
                line = _behind(board, C, T)
                if len(line) >= 2 and line[0] == T and line[1] in cset and line[1] != C:
                    return C, {ens[0]["id"]: T, ens[1]["id"]: line[1]}, ens[0]["id"]
            return None

        if args.only in ("both", "drachnyen"):
            _report("DRACHNYEN", rpc, rid, board, ABADDON, DRACHNYEN, layout_adjacent, wound=True)
        if args.only in ("both", "herald"):
            _report("HERALD", rpc, rid, board, HAARKEN, HERALD, layout_line)
        return 0
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
