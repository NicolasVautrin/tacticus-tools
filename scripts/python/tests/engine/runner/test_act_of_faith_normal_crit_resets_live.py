"""CONFIRMATION LIVE (oracle natif) : un crit d'attaque NORMALE reset ActOfFaith.

Confronte le NATIF (pas le port) sur le point tranche par le re-expert (G6b) : `On(9)=Attack` est un event
GENERIQUE emis par `FinishAttackOperation @180e71310` pour TOUTE attaque, et `ActOfFaith_RemoveEffectAbility`
@181219f90 = `On(9) & OwnerIsCaster & WasCrit & HasEffect(0x3f9)` SANS gate normal/ability -> **le natif reset
sur un crit d'attaque NORMALE**. Corrige #151 (qui croyait On(9) ability-only via `OnNormalAttackOrSmite`).

Scenario (Sister `adeptCanoness` cc force -> crite toujours quand elle attaque) :
  phase 0 : lire la crit-stat de BASE au deploiement (0 stack) ;
  phase 1 : un allie Imperial (`admecDestroyer`) TUE un ennemi -> la Sister gagne un stack (crit > base) ;
  phase 2 : la Sister fait son ATTAQUE NORMALE **forcee** (ability 69 = `Loki_NormalAttack`, PAS son actif
            BrazierOfHolyFire 1041) sur un ennemi et CRITE -> lecture de la crit-stat LIVE -> RESET a la base.
On CONFRONTE la crit-stat live (combatSnapshot) : base -> boostee (>base) -> base. La cle du test = phase 2
utilise l'attaque NORMALE (id 69), pas l'actif -> discrimine le crit NORMAL (ce que #151 pretendait non-reset).

⚠ OBSERVATION live (pas de replay-diff moteur). ⚠ ADJACENCE/PORTEE = mode evenq.
"""
from __future__ import annotations

from collections import deque

import pytest

SISTER_VIS = "adeptCanoness"        # ActOfFaith ; normal attack = Loki_NormalAttack (id 69), actif = Brazier 1041
ALLY_VIS = "admecDestroyer"         # allie Imperial -> donne un stack a la Sister (sans la resetter)
ENEMY_VIS = "necroDestroyer"
ENEMY2_VIS = "necroOverlord"
ENEMY3_VIS = "necroWarden"
NORMAL_ATTACK_ID = 69               # Loki_NormalAttack (kind:"normal") — force l'attaque NORMALE, pas l'actif
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


def test_normal_crit_resets_actoffaith_live(live_session, rpc, build_runner):
    """LIVE : la crit-stat de la Sister base -> boostee (kill allie) -> RESET a la base quand elle CRITE via son
    attaque NORMALE (ability 69). Confirme que le natif reset ActOfFaith sur un crit NORMAL (corrige #151)."""
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
        pytest.skip(f"Sister sans crit de base (cc={base_cc} cd={base_cd}) - gate ActOfFaith")

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

    def _approach_and_attack(dec, attacker_id, R, force_ability=None):
        """Approche l'attaquant d'un ennemi VIVANT et l'attaque si en portee. `force_ability` = id d'ability
        impose (ex. 69 = attaque normale) au lieu de laisser l'attackPlan choisir. Renvoie True si une attaque
        a ete emise ce tour."""
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
        ability = force_ability if force_ability is not None else _ability_for(dec, attacker_id, tgt_id)
        if ability is None:
            return False
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": attacker_id, "targetId": tgt_id, "abilityType": ability}}, 60)
        return True

    boosted = None
    reset_seen = None
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
            # PHASE 1 : monter un stack via un kill de l'allie (la Sister n'attaque pas encore).
            if cc > base_cc or cd > base_cd:
                boosted = (cc, cd)
                continue
            acted = _approach_and_attack(dec, ally_id, R_ally)
            if acted is None:
                pytest.skip("plus assez d'ennemis pour la phase 1")
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue

        # PHASE 2 : la Sister attaque via son ATTAQUE NORMALE (id 69) et CRITE -> reset. Lire la crit APRES.
        acted = _approach_and_attack(dec, sister_id, R_sis, force_ability=NORMAL_ATTACK_ID)
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

    print(f"\n[AOF-NORMAL-CRIT-RESET-LIVE] base cc={base_cc} cd={base_cd} | boostee {boosted} | "
          f"apres crit NORMAL Sister {reset_seen}")
    assert boosted[0] > base_cc or boosted[1] > base_cd, \
        f"pas de stack acquis en phase 1 (boostee {boosted} <= base ({base_cc},{base_cd}))"
    # La Sister avait un stack ; apres un crit d'ATTAQUE NORMALE, son crit revient EXACTEMENT a la base.
    assert reset_seen == (base_cc, base_cd), (
        f"reset NORMAL KO : apres son crit d'attaque NORMALE la Sister a crit {reset_seen}, "
        f"attendu base ({base_cc},{base_cd}) -> le natif N'aurait PAS reset sur crit normal (contredirait le RE)")
