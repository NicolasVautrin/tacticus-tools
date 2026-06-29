"""RESET ActOfFaith au crit — OBSERVATION LIVE (`ActOfFaith_RemoveEffectAbility`).

Valide le volet C du trait : « Once this unit crits, this bonus resets » (`CreateTrigger` natif
`On(9,1) & OwnerIsCaster & WasCrit & HasEffect(0x3f9)` → `RemoveEffect(0x3f9)` tous stacks).

Scénario (Sister `adeptCanoness` forcée cc=100 → crite TOUJOURS) :
  phase 0 : lire la crit-stat de BASE de la Sister au déploiement (0 stack) ;
  phase 1 : un allié Imperial (`admecDestroyer`) TUE un ennemi → la Sister gagne un stack (crit > base) ;
  phase 2 : la Sister ATTAQUE un ennemi et CRITE → after-hit `WasCrit` → RemoveEffect → crit revient
            EXACTEMENT à la base.
On CONFRONTE la crit-stat live (combatSnapshot) : base -> boostée (>base) -> base. Indépendant des
valeurs `--crit` (la base est LUE au déploiement, pas supposée).

⚠ OBSERVATION live (pas de replay-diff moteur) : un stack SEEDÉ depuis le live n'a pas ses deltas
(cf. ActOfFaithBuffEffect) → le revert moteur d'un stack seedé n'est pas exact. La math du reset moteur
est validée offline (accumulate-depuis-0 puis reset) ; ici on confirme que le JEU reset bien au crit.
⚠ ADJACENCE/PORTÉE = mode **evenq**.
"""
from __future__ import annotations

from collections import deque

import pytest

SISTER_VIS = "adeptCanoness"        # crit 100 → crite toujours (reset deterministe quand elle attaque)
ALLY_VIS = "admecDestroyer"         # allie Imperial = donne un stack a la Sister (sans la resetter)
ENEMY_VIS = "necroDestroyer"
ENEMY2_VIS = "necroOverlord"
ENEMY3_VIS = "necroWarden"          # 3e ennemi : la bataille survit aux kills (snapshot lisible)
# cc=90 → un stack la porte a 100 (visible : +10, sous le cap) PUIS elle crite toujours (cc=100) en
# phase 2 → reset deterministe ; cd=250 != 0 (gate). base lue au deploiement (pas supposee).
BUILD = ["--roster", "1", "--p-units", f"{SISTER_VIS},{ALLY_VIS}",
         "--a-units", f"{ENEMY_VIS},{ENEMY2_VIS},{ENEMY3_VIS}", "--crit", "90,250", "--hp-target", "200"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _bfs(board, src):
    dist = {src: 0}; q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist:
                dist[n] = dist[x] + 1; q.append(n)
    return dist


def _crit(snap, eid):
    for u in (snap.get("units") or []):
        if u.get("entityId") == eid:
            s = u.get("stats") or {}
            return s.get("critChance"), s.get("critDamage")
    return None, None


def _alive_enemies(units, my_team):
    return [u for u in units if u.get("team") != my_team and u.get("alive") and u.get("pos")]


def test_act_of_faith_resets_on_crit_live(live_session, rpc, build_runner):
    """La crit-stat de la Sister : base -> boostée par un kill allié -> RESET à la base quand elle crite."""
    from engine.entities.pathfinding.board import Board
    import gameconfig as GC
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    def tof(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None

    dec0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if not _ok(dec0):
        pytest.skip("decisionView KO")
    units0 = dec0.get("units") or []
    sister = next((u for u in units0 if u.get("visualId") == SISTER_VIS and u.get("alive")), None)
    ally = next((u for u in units0 if u.get("visualId") == ALLY_VIS and u.get("alive")), None)
    if sister is None or ally is None:
        pytest.skip(f"unite absente (sister={bool(sister)} ally={bool(ally)})")
    my_player, my_team = ally.get("owner"), ally.get("team")
    sister_id, ally_id = sister["id"], ally["id"]

    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 60)
    base_cc, base_cd = _crit(snap0, sister_id)
    if not base_cc or not base_cd:
        pytest.skip(f"Sister sans crit de base (cc={base_cc} cd={base_cd}) — gate ActOfFaith")

    def weap_range(vis):
        ws = (GC.unit(vis) or {}).get("weapons") or []
        return max([int(w.get("Range") or 0) for w in ws] or [0]) or 1
    R_ally, R_sis = weap_range(ALLY_VIS), weap_range(SISTER_VIS)

    def _ability_for(dec, caster_id, tgt_id):
        for p in (dec.get("attackPlans") or []):
            if p.get("unitId") == caster_id:
                for ev in (p.get("evals") or []):
                    if ev.get("targetId") == tgt_id:
                        return ev.get("abilityId")
        return None

    def _approach_and_attack(dec, attacker_id, R):
        """Approche l'attaquant d'un ennemi VIVANT et l'attaque si en portee. Renvoie True si une
        attaque a ete emise ce tour (sinon a bouge / fin de tour)."""
        us = dec.get("units") or []
        me = next((u for u in us if u["id"] == attacker_id and u.get("alive")), None)
        ens = _alive_enemies(us, my_team)
        if me is None or len(ens) < 2:           # garder >=1 ennemi apres un kill
            return None
        target = ens[0]; tgt_id = target["id"]
        a_tile, t_tile = tof(me), tof(target)
        if a_tile is None or t_tile is None:
            return False
        dgoal = _bfs(board, t_tile)
        if dgoal.get(a_tile, 99) > R:
            mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == attacker_id), None)
            reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                     for t in ((cmt or {}).get("tiles") or [])}
            pool = [t for t in reach if t in dgoal and dgoal[t] >= 1]
            if not pool:
                return False
            best = min(pool, key=lambda t: dgoal[t]); col, row = reach[best]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": attacker_id, "to": {"col": col, "row": row}}}, 40)
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            me = next((u for u in (dec.get("units") or []) if u["id"] == attacker_id), None)
            a_tile = tof(me) if me else None
            if a_tile is None or dgoal.get(a_tile, 99) > R:
                return False
        ability = _ability_for(dec, attacker_id, tgt_id)
        if ability is None:
            return False
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": attacker_id, "targetId": tgt_id, "abilityType": ability}}, 60)
        return True

    boosted = None       # crit Sister apres un kill allie (avant qu'elle attaque)
    reset_seen = None     # crit Sister apres qu'elle a crite
    for _turn in range(60):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dec):
            break
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
        cc, cd = _crit(snap, sister_id)
        if cc is None:
            pytest.skip("Sister disparue")

        if boosted is None:
            # PHASE 1 : faire monter un stack via un kill de l'allie (la Sister n'attaque pas encore).
            if cc > base_cc or cd > base_cd:         # un stack a ete acquis (cd toujours visible)
                boosted = (cc, cd)
                continue
            acted = _approach_and_attack(dec, ally_id, R_ally)
            if acted is None:
                pytest.skip("plus assez d'ennemis pour la phase 1")
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue

        # PHASE 2 : la Sister (cc=100) attaque et CRITE → reset. On lit la crit APRES son attaque.
        acted = _approach_and_attack(dec, sister_id, R_sis)
        if acted is None:
            pytest.skip("plus assez d'ennemis pour la phase 2")
        if acted:
            snap_a = rpc("combatSnapshot", {"runnerId": rid}, 60)
            cc_a, cd_a = _crit(snap_a, sister_id)
            reset_seen = (cc_a, cd_a)
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    if boosted is None:
        pytest.skip("la Sister n'a pas gagne de stack en phase 1 (kill allie non obtenu)")
    if reset_seen is None:
        pytest.skip("la Sister n'a pas pu attaquer en phase 2")

    print(f"\n[ACTOFFAITH-RESET] base cc={base_cc} cd={base_cd} | boostee {boosted} | "
          f"apres crit Sister {reset_seen}")
    # La Sister avait un stack (crit > base) ; apres avoir crite, son crit revient EXACTEMENT a la base.
    assert boosted[0] > base_cc or boosted[1] > base_cd, \
        f"pas de stack acquis en phase 1 (boostee {boosted} <= base ({base_cc},{base_cd}))"
    assert reset_seen == (base_cc, base_cd), (
        f"reset KO : apres crit la Sister a crit {reset_seen}, attendu base ({base_cc},{base_cd})")
