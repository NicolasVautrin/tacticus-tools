"""#106 -- NATURE DU COUP threadee par le vecteur `execute_normal_like` : replay-diff LIVE.

CE QUI EST VALIDE. `AttackDamageOperation.execute_normal_like` (splash Psyker, attaque on-appearance de
summon, degat-node `amount` de `AttackWithAttackDamage`) RECEVAIT `is_melee` mais ne le threadait PAS a la
collecte des modifiers ATTAQUANT -> `is_ranged=None` remontait jusqu'aux gates `IsMeleeAttack`/
`IsRangedAttack` des effets. Le natif ne connait pas cet etat : `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack`
et `IdunBattle.Core.Services.BattleQuery$$IsRangedAttack` rendent un BOOL depuis
`IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType` (None/absent -> les DEUX faux ; Melee ->
melee ; Ranged -> ranged ; Both -> `AreUnitsInMelee` sauf flag 0x15).

PORTEUR DISCRIMINANT. `tyranNeurothrope` cumule le trait **Psyker** (splash `PsykerExtraAttackAbility`
-> vecteur after-hit -> `execute_normal_like(is_melee=False)`) et le trait **RangedSpecialist**
(`IdunBattle.Entities.Effects.Loki.RangedSpecialistEffect$$CreateEffectDamageBonusForAttack` = +33 %
gate `IsRangedAttack`). Son arme ranged (portee 3, profil Psychic, pierce 100) declenche le splash.
AVANT #106 le splash offline PERDAIT les +33 % (gate ranged faux sur nature inconnue) ; le natif, lui,
resout la nature du coup -> divergence directement mesurable sur le montant du splash.

Le test refuse de se declarer vert sans etre DISCRIMINANT : il exige que les modifiers attaquant calcules
avec `is_ranged=True` DIFFERENT de ceux calcules avec `is_ranged=None` sur l'etat capture (sinon aucun
effet gate-nature n'est actif -> le scenario ne prouverait rien -> skip explicite).

ADJACENCE = evenq (cf. `test_psyker_splash_live.py` : la capture native de `boardGraph.neighbours` est
partielle ; le jeu splashe un ennemi evenq-adjacent que le graphe natif ne liste pas).
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import StatsComponent

CASTER_VIS = "tyranNeurothrope"          # Psyker + RangedSpecialist, arme ranged R3 Psychic pierce100
# cluster melee : ennemis qui spawnent groupes (adjacents entre eux en evenq), tanky => survivent au coup.
ENEMIES = "darkaCompanion,tyranWingedPrime,ultraInceptorSgt,spaceBlackmane,necroSpyder"
BUILD = ["--roster", "1", "--p-units", CASTER_VIS, "--a-units", ENEMIES]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _bfs(board, src):
    dist = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def _mods_signature(mods):
    """Signature comparable d'un `DamageModifiers` (additif + %-list triee)."""
    return (getattr(mods, "additive", 0), tuple(sorted(getattr(mods, "pct_list", []) or [])),
            getattr(mods, "armor_penetration", 0))


@pytest.mark.parametrize("seed,board", [("777", "MC1_67"), ("31337", "C3_01")])
def test_normal_like_vector_threads_attack_nature(live_session, rpc, build_runner, seed, board):
    """Splash Psyker (vecteur normal-like RANGED) d'un porteur RangedSpecialist : bit-exact vs live."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.damage_model import attacker_modifiers
    rid = build_runner(seed, extra=BUILD, board=board)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    b = Board(bg["tiles"], adjacency="evenq")

    def tile_of(u):
        p = u.get("pos") or {}
        return b.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None

    def enemies(dec, mp):
        return [u for u in (dec.get("units") or []) if u.get("owner") != mp and u.get("alive")]

    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if not _ok(dec):
        pytest.skip("decisionView KO")
    ps0 = next((u for u in (dec.get("units") or [])
                if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
    if ps0 is None:
        pytest.skip("caster absent")
    my_player = ps0.get("owner")
    norm = next((ab for ab in (ps0.get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        pytest.skip("ability normale introuvable")
    norm_id = norm.get("id")

    # Conduire le caster a d>=2 (arme RANGED psychique) d'une cible ayant EXACTEMENT 1 ennemi adjacent
    # (pas d'ambiguite sur le `PickRandomly(1)` du splash).
    chosen = None
    for _turn in range(60):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dec):
            pytest.skip("decisionView KO")
        ps = next((u for u in (dec.get("units") or []) if u["id"] == ps0["id"] and u.get("alive")), None)
        if ps is None:
            pytest.skip("caster mort pendant l'approche")
        ens = enemies(dec, my_player)
        if len(ens) < 2:
            pytest.skip("moins de 2 ennemis vivants")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": ps["id"], "allAbilities": True}, 90)
        fh = set()
        for unit in (at.get("units") or []):
            if unit.get("unitId") != ps["id"]:
                continue
            for ab in (unit.get("abilities") or []):
                if ab.get("abilityId") != norm_id:
                    continue
                for tg in (ab.get("fromHere") or []):
                    if tg.get("kind") == "unit":
                        fh.add(tg.get("targetId"))
        dist_ps = _bfs(b, tile_of(ps))
        cands = []
        for T in ens:
            if T["id"] not in fh or dist_ps.get(tile_of(T), 99) < 2:
                continue
            nb = set(b.neighbours(tile_of(T)))
            adjE = [e for e in ens if tile_of(e) in nb]
            if len(adjE) == 1:
                cands.append((T, adjE[0]))
        if cands:
            chosen = cands[0]
            break
        goals = [T for T in ens
                 if set(b.neighbours(tile_of(T))) & {tile_of(e) for e in ens if e is not T}]
        goal = min(goals or ens, key=lambda T: dist_ps.get(tile_of(T), 99))
        dgoal = _bfs(b, tile_of(goal))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == ps["id"]), None)
        reach = {b.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dgoal and dgoal[t] >= 2] or [t for t in reach if t in dgoal]
        if pool:
            best = min(pool, key=lambda t: dgoal[t])
            col, row = reach[best]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": ps["id"], "to": {"col": col, "row": row}}}, 40)
        dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        if dv2.get("currentPlayer") == my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    if chosen is None:
        pytest.skip("aucun scenario splash (cible RANGED avec 1 voisin ennemi) atteint en 60 tours")

    T, adjE = chosen
    att, tid, eid = ps0["id"], T["id"], adjE["id"]

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv, ob, snap, board=b)
    ae = state.get_entity(att)
    if ae is None or ae.get_component(StatsComponent) is None:
        pytest.skip("caster sans StatsComponent")
    if "Psyker" not in (ae.get_component(StatsComponent).ctx.traits or []):
        pytest.skip("le caster n'a pas le trait Psyker offline")

    # GARDE DE DISCRIMINANCE : sans effet gate-nature actif, ce scenario ne prouverait rien.
    hp_att = None
    mods_ranged, _ = attacker_modifiers(state, att, hp_att, is_ranged=True, target_id=eid)
    mods_unknown, _ = attacker_modifiers(state, att, hp_att, is_ranged=None, target_id=eid)
    if _mods_signature(mods_ranged) == _mods_signature(mods_unknown):
        pytest.skip("aucun effet gate-nature actif sur le caster -> scenario NON discriminant "
                    f"(mods {_mods_signature(mods_ranged)})")

    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    state.rng = _seed_rng(s0)

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": norm_id}}, 60)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        pytest.skip(f"cast KO: {str(res)[:160]}")
    by_target: dict[int, list[int]] = {}
    dirty = False
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" in td and td.get("Target_Id") is not None:
            by_target.setdefault(td["Target_Id"], []).append(td["Amount"])
            if td.get("Attack_DidCrit") or td.get("Attack_DidBlock") or td.get("Attack_DidEvade"):
                dirty = True
    live_primary = by_target.get(tid)
    live_splash = by_target.get(eid)
    if not live_primary:
        pytest.skip("aucun degat primaire live capture")
    if dirty:
        pytest.skip("coup non propre (crit/block/evade) hors axe")
    assert live_splash, (f"splash Psyker n'a PAS fire live (by_target={by_target}, primary={tid}, "
                         f"adjE={eid}) -- trigger ranged-psychic attendu")

    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(att, tid))
    dh = runner.damage_handler
    off_primary = (dh.last or {}).get("per_hit")
    splash = [a for a in (dh.after_hit or []) if a.get("trait") == "Psyker"]
    off_splash_tid = splash[0]["target"] if splash else None
    off_splash_ph = splash[0]["result"]["per_hit"] if splash else None
    print(f"\n[#106 nature] seed={seed} board={board} primary T={tid} live={live_primary} "
          f"off={off_primary} | splash live tgt={eid} amt={live_splash} | off tgt={off_splash_tid} "
          f"amt={off_splash_ph} | ranged={dh.last.get('ranged')} profile={dh.last.get('profile')}")
    assert dh.last.get("ranged") is True, "l'attaque offline doit etre RANGED (arme psychique d>=2)"
    assert off_primary == live_primary, f"per-coup primaire offline {off_primary} != live {live_primary}"
    assert off_splash_tid == eid, f"cible splash offline {off_splash_tid} != live {eid}"
    # LE VERROU #106 : sans la nature threadee dans `execute_normal_like`, le splash perd le +33 %
    # RangedSpecialist et ce montant diverge.
    assert off_splash_ph == live_splash, (
        f"degat splash offline {off_splash_ph} != live {live_splash} -- la NATURE du coup n'a pas ete "
        f"threadee jusqu'aux gates d'effet du vecteur normal-like")
