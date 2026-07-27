"""Helper REUTILISABLE de montage « cible AU CENTRE d'un hexagone plein » + confront d'un cast.

Beaucoup de ports AoE/splash exigent la MEME geometrie : une cible posee sur une tuile a **6 voisins
tous marchables**, entouree d'unites CHOISIES (dont un ALLIE du caster, seul moyen d'exercer le
friendly-fire), le caster place ou non au contact, et un nombre controle de ROUNDS ecoules avant le
cast (`TurnsStarted` du caster est une entree de plusieurs formules natives). Le montage est ecrit
UNE fois ici plutot que recopie dans chaque test.

    ring_scenario(rpc, rid, caster_visual_id, ...) -> dict | None
    cast_and_confront(rpc, rid, sc, ability, ...)  -> (live, empty, offline, diag)

`ring_scenario` rend `None` + une `reason` quand la geometrie n'est pas atteignable (le test appelant
decide skip/fail — aucun `pytest.skip` ici, meme discipline que `_combat_replay`).

Ce que le montage garantit, et pourquoi chaque point compte :
  * **6 voisins TOUS marchables** : un spawn en bord/coin sous-exerce silencieusement toute mecanique
    d'anneau ou d'adjacence, et un `move` vers une tuile non marchable ECHOUE sans le dire -- le test
    mesurerait alors une geometrie qu'il croit avoir posee (vecu sur `C3_01`, 14 tuiles
    `walkable=false`).
  * **un ALLIE dans l'anneau** : sans lui, un splash enemies-only et un splash friendly-fire rendent
    le MEME resultat -- le test ne discrimine rien.
  * **`rounds` fins de tour completes** : fait monter `TurnsStarted`, et surtout garantit que le
    caster N'A PAS BOUGE au tour du cast (sinon les bonus gates `IsCharging` s'invitent dans le
    degat, cf. residu R32 de `port-residuals-inventory.md`).

Lit l'etat LIVE, aucune tuile/RVA hardcodee. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import json

from engine.entities.pathfinding.board import Board
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state


def seed_rng(dump: dict) -> IntBasedMersenneTwister:
    """MT du port cale sur l'etat rendu par `dumpRng` (pris JUSTE avant le cast)."""
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"]); rng.mti = dump["mti"]
    return rng


def alive(dv: dict) -> list:
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def counts(seq) -> dict:
    """[(target_id, amount)] -> {target_id: nb de coups}."""
    out: dict = {}
    for tid, _amount in seq:
        out[tid] = out.get(tid, 0) + 1
    return out


def ring_scenario(rpc, rid: int, caster_visual_id: str, ally_visual_id: str,
                  rounds: int = 0, place_caster_adjacent: bool = False,
                  isolate_target: bool = False, min_enemies: int = 4):
    """Pose la geometrie et rend le contexte de confront, ou `{"reason": ...}` si impossible.

    `place_caster_adjacent` : le caster va dans l'anneau (cast MELEE). Sinon il n'est PAS deplace --
    ce qu'exige un porteur gate `CasterHasNotMoved` (BasiliskBarrage 1026).
    `isolate_target` : tout le monde SAUF le caster part a >= 4 hex -> anneau VIDE (contre-cas
    « splash reellement vide », qui prouve que le volet splash n'est pas un forfait).

    Retour : {board, dv, ob, snap, rng, me, ally, target, tpos, ttile, pos, ring_units} ou
    `ring_units` = les occupants des voisins NATIFS de la tuile ciblee, CASTER EXCLU, **dans l'ordre
    natif** (c'est l'ordre qu'un `SortedAttackSeries` consomme, donc l'ordre des tirages)."""
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return {"reason": "boardGraph indispo"}
    byid = {t["id"]: t for t in bg["tiles"]}
    board = Board(bg["tiles"], adjacency="native_sym")

    def nb(tid):
        return [n for n in (byid[tid].get("neighbours") or []) if n in byid]

    def move(uid, tid):
        c = byid[tid]
        return rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": c["col"], "row": c["row"]}}}, 40)

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    units = alive(dv)
    me = next((u for u in units if u.get("visualId") == caster_visual_id), None)
    ally = next((u for u in units if u.get("visualId") == ally_visual_id), None)
    if me is None or ally is None:
        return {"reason": "porteur/allie absent du build"}
    myp = me.get("owner")
    ens = [u for u in units if u.get("owner") != myp]
    if len(ens) < min_enemies:
        return {"reason": f"moins de {min_enemies} ennemis vivants"}
    # tuile a 6 voisins TOUS marchables (cf. en-tete : sinon un `move` echoue en silence)
    cands = sorted(t for t in byid if len(nb(t)) == 6 and byid[t].get("walkable")
                   and all(byid[n].get("walkable") for n in nb(t)))
    if not cands:
        return {"reason": "aucune tuile a 6 voisins tous marchables"}
    centre = cands[len(cands) // 2]
    ring = nb(centre)
    tgt = ens[0]
    place = [(tgt["id"], centre)]
    if isolate_target:
        import hexgeo
        cc = (byid[centre]["col"], byid[centre]["row"])
        far = [t for t in cands
               if hexgeo.distance((byid[t]["col"], byid[t]["row"]), cc) >= 4]
        if len(far) < len(ens):
            return {"reason": "pas assez de tuiles eloignees pour isoler la cible"}
        place += [(u["id"], far[i]) for i, u in enumerate([ally] + ens[1:])]
    else:
        place += [(ally["id"], ring[1]), (ens[1]["id"], ring[2]),
                  (ens[2]["id"], ring[3]), (ens[3]["id"], ring[5])]
    if place_caster_adjacent:
        place.append((me["id"], ring[0]))
    for uid, tid in place:
        move(uid, tid)
    for _ in range(max(0, rounds)):                    # 2 endturn = 1 round complet (2 camps)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if dv.get("currentPlayer") != myp:
        return {"reason": "le tour n'est pas revenu au camp du caster"}
    units = alive(dv)
    pos = {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in units}
    if me["id"] not in pos or tgt["id"] not in pos:
        return {"reason": "caster ou cible mort avant le cast"}
    tp = pos[tgt["id"]]
    ttile = board.id_at(*tp)
    occ = {(p[0], p[1]): uid for uid, p in pos.items()}
    ring_units = [occ[board.coord(t)] for t in board.neighbours_native(ttile)
                  if board.coord(t) in occ and occ[board.coord(t)] != me["id"]]
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(s0, dict) and s0.get("ok")):
        return {"reason": "dumpRng KO"}
    return {"board": board, "dv": dv, "ob": ob, "snap": snap, "rng": s0, "me": me["id"],
            "ally": ally["id"], "target": tgt["id"], "tpos": tp, "ttile": ttile,
            "pos": pos, "ring_units": ring_units}


def cast_and_confront(rpc, rid: int, sc: dict, ability: int, off_extract):
    """Joue le cast LIVE puis le REJOUE offline depuis l'etat capture et le MEME MT.

    `off_extract(diag) -> [(target_id, amount)]` : extracteur per-coup propre a l'ability (le
    diagnostic d'`execute_behaviour` differe d'un port a l'autre).
    Retour `(live_seq, live_empty_tiles, off_seq, diag)` ; `diag["ported"]` est a verifier par le
    test appelant (c'est LUI le garde du no-op silencieux)."""
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": sc["me"], "targetId": sc["target"],
        "abilityType": ability}}, 90)
    a0 = (res.get("actions") or [{}])[0]
    if not (isinstance(res, dict) and res.get("ok") and a0.get("ok")):
        return None, None, None, {"cast_ko": str(res)[:200]}
    live, empty = [], []
    for a in (res.get("actions") or []):
        for e in (a.get("events") or []):
            td = e.get("tags")
            if isinstance(td, str):
                td = json.loads(td)
            if not td:
                continue
            if "Damage_Empty_Target_Tile_Id" in td:
                empty.append(td["Damage_Empty_Target_Tile_Id"])
            elif td.get("Active_Ability_Type") == ability and "Amount" in td:
                live.append((td["Target_Id"], td["Amount"]))
    st = load_state(sc["dv"], sc["ob"], sc["snap"], board=sc["board"])
    st.rng = seed_rng(sc["rng"])
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=sc["me"], target_id=sc["target"],
                                      ability_type=ability))
    diag = runner.ability_handler.last or {}
    return live, empty, (off_extract(diag) if diag.get("ported") else []), diag
