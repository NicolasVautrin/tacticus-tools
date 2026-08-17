"""ORDRE `part bouclier` x `limites de degat` sur la voie ABILITY -- confronte LIVE (residu case-67 SS5).

Artefact natif : `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` (famille ABILITY =
`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` -> `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit`) :

    dmg        = Math.Max(param_2, 0)
    shieldPart = Math.Min(dmg, UnitExtensions.GetShield(cible))          # `iVar20`
    v          = CalculateBaseDamageWithAllModifiers(dmg - shieldPart)   # `iVar17 - iVar20`
    v          = Fix64.Max(v, 0)
    v          = ApplyTraitDamageLimitsToDamage(2, &v, &v, ...)          # cap sur le RESTE
    return       (int)(Fix64(shieldPart) + v)

=> ce que le BOUCLIER absorbe echappe aux caps (member-cap / Resilient / cap boss). Le port capait AVANT
le split (ordre de la famille ATTACK, ou les caps portent sur les cellules en amont de
`IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation`) -> divergence des qu'une cible a
un bouclier NON NUL. Identique bit-a-bit quand shield == 0.

MONTAGE (le seul confrontable, cf. probe_67b_shield_ability_limits.py) :
  - cible   `deathRotbone` : HERO du pool, trait `Resilient`, CHAOS (ArcaneShield ne cible qu'un allie
            Chaos -- avec un allie Imperial le natif se protege LUI-MEME), aucune reduction du degat RECU ;
  - bouclier `thousSorcerer` : passive `ArcaneShield` -> bouclier a l'ami <= 2 hex APRES SON MOVE. Le move
            d'une unite ENNEMIE est accepte hors de son tour -> pose A LA DEMANDE, sans `endturn` (donc
            sans `IdunBattle.Operations.EndTurnOperation$$RemoveOneTurnOnShields`) ;
  - attaque `tyranNeurothrope` / `SpiritLeech` (1104) : famille ABILITY, RANGED r3, 1 coup, profil
            `Psychic` (perce 100 %, `NoBlocking`) -> le coup isole l'etage conteste ;
  - `eldarRanger` : unite qui n'agit jamais -> le cast ne CLOT pas mon tour, donc le bouclier restant
            reste LISIBLE apres le coup (sinon il expire dans la foulee et le live rend 0).

Le test confronte per-coup + PV + bouclier restant, et exige que le scenario soit DISCRIMINANT : il
rejoue le MEME etat sous l'ANCIEN ordre (famille ATTACK forcee) et verifie qu'il donne autre chose.
`--hp-target` cale le regime du cap Resilient : `hp-1 < degat` (le cap mord) ET `degat < 2 x hp`
(la porte overkill reste fermee, sinon le cap est bypasse).
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, ShieldComponent

CASTER_VIS = "tyranNeurothrope"
TARGET_VIS = "deathRotbone"
WARD_VIS = "thousSorcerer"
FILLER_VIS = "eldarRanger"
ABILITY = 1104
ARCANE_RANGE = 2                 # `ArcaneShield.constants.range`
HP_TARGET = 1500                 # hp-1 < SpiritLeech(~1950-2990) < 2 x hp


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _bfs(board, src):
    dist, q = {src: 0}, deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def _tile(board, u):
    p = (u or {}).get("pos") or {}
    return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None


def _unit(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _shields(rpc, rid):
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    return ({u.get("entityId"): sum(int(s.get("amount") or 0) for s in (u.get("shields") or []))
             for u in (snap.get("units") or [])}, snap)


def _movement(rpc, rid, uid):
    """`decisionView` ne porte pas le stat Movement -- `combatSnapshot.stats.movement` si."""
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    for u in (snap.get("units") or []):
        if u.get("entityId") == uid:
            return max(1, int((u.get("stats") or {}).get("movement") or 2))
    return 2


def _reachable(rpc, rid, board, dec, mover):
    """`aiMovableTiles` ne rend RIEN pour une unite dont ce n'est pas le tour (mesure : side=enemy ->
    0 tuiles) alors qu'`applyAction move` l'accepte -> disque de mouvement calcule ici pour un ENNEMI."""
    if mover.get("mine"):
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == mover["id"]), None)
        return {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                for t in ((cmt or {}).get("tiles") or [])}
    src = _tile(board, mover)
    mv = _movement(rpc, rid, mover["id"])
    occupied = {_tile(board, u) for u in (dec.get("units") or []) if u.get("alive")}
    dist, q, out = {src: 0}, deque([src]), {}
    while q:
        x = q.popleft()
        if dist[x] >= mv:
            continue
        for n in board.neighbours(x):
            if n in dist or not board.walkable(n):
                continue
            dist[n] = dist[x] + 1
            q.append(n)
            if n not in occupied:
                out[n] = board.coord(n)
    return out


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _live_hits(res, tid):
    a0 = (res.get("actions") or [{}])[0]
    out, flags = [], [False, False, False]
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
            out.append(td.get("Amount"))
            flags = [flags[0] or bool(td.get("Attack_DidCrit")),
                     flags[1] or bool(td.get("Attack_DidBlock")),
                     flags[2] or bool(td.get("Attack_DidEvade"))]
    return out, flags, a0


def _approach(rpc, rid, board, my_player):
    """Amene le caster a portee 3 de la cible (seul MON caster bouge : deplacer la cible la separerait
    du ward, or ArcaneShield exige <= 2 hex)."""
    for _ in range(40):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        if not _ok(dec):
            pytest.skip("decisionView KO")
        caster, tgt = _unit(dec, CASTER_VIS), _unit(dec, TARGET_VIS)
        if caster is None or tgt is None:
            pytest.skip("caster/cible absents")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        ct, tt = _tile(board, caster), _tile(board, tgt)
        if _bfs(board, tt).get(ct, 99) <= 3:
            return dec, caster, tgt
        caster["mine"] = True
        reach = _reachable(rpc, rid, board, dec, caster)
        d = _bfs(board, tt)
        pool = [t for t in reach if d.get(t, 99) < d.get(ct, 99)]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        col, row = reach[min(pool, key=lambda t: d[t])]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": caster["id"], "to": {"col": col, "row": row}}}, 60)
    pytest.skip("caster jamais a portee 3 de la cible")


def _cast_and_compare(rpc, rid, dec, my_player, want_shield: bool):
    """Capture (decisionView/observeBattle/combatSnapshot + dumpRng) -> cast LIVE -> replay offline.
    Renvoie (live, offline, legacy) ou skip si le coup n'est pas propre."""
    if dec.get("currentPlayer") != my_player:
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    caster, tgt = _unit(dec, CASTER_VIS), _unit(dec, TARGET_VIS)
    att, tid = caster["id"], tgt["id"]
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    sh_before, snap = _shields(rpc, rid)
    if want_shield and not int(sh_before.get(tid) or 0):
        pytest.skip("bouclier absent sur la cible au moment du cast")
    if (not want_shield) and int(sh_before.get(tid) or 0):
        pytest.skip("bouclier PRESENT alors que le regime shield==0 est demande")
    state = load_state(dec, ob, snap)
    te = state.get_entity(tid)
    thc = te.get_component(HealthComponent) if te is not None else None
    if thc is None or thc.hp is None:
        pytest.skip("cible introuvable offline")
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    state.rng = _seed_rng(s0)

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": ABILITY}}, 60)
    lph, (dc, db, de), a0 = _live_hits(res, tid)
    if not (_ok(res) and a0.get("ok")):
        pytest.skip(f"cast KO: {str(res)[:160]}")
    if dc or db or de:
        pytest.skip(f"coup non propre (crit/block/evade live) : c={dc} b={db} e={de}")
    if not lph:
        pytest.skip("aucun event de degat live")
    live_hp = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tid), None)
    sh_after, _ = _shields(rpc, rid)

    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=att, target_id=tid, ability_type=ABILITY))
    last = runner.ability_handler.last or {}
    atk = last.get("main_attack") or last.get("attack")
    assert atk is not None, f"pas d'attaque offline : {last}"
    shc = state.get_entity(tid).get_component(ShieldComponent)

    # CONTROLE « ancien ordre » : meme etat, famille ATTACK forcee (cap sur le TOTAL puis split).
    # Sert a prouver que le scenario est DISCRIMINANT -- sans lui, un OK ne vaudrait rien.
    from engine.runner.operations.damage import AttackDamageOperation as _ADO
    state_l = load_state(dec, ob, snap)
    state_l.rng = _seed_rng(s0)
    _orig = _ADO._run_hits
    try:
        _ADO._run_hits = staticmethod(
            lambda *ar, **kw: _orig(*ar, **{**kw, "is_attack_damage_op": True}))
        Runner(state_l).install_default_handlers(20).apply(
            ActiveAbilityMessage(caster_id=att, target_id=tid, ability_type=ABILITY))
    finally:
        _ADO._run_hits = _orig
    shc_l = state_l.get_entity(tid).get_component(ShieldComponent)

    live = {"per_hit": lph, "hp": live_hp, "shield": int(sh_after.get(tid) or 0)}
    off = {"per_hit": atk["per_hit"], "hp": state.get_entity(tid).get_component(HealthComponent).hp,
           "shield": shc.get_total_shield() if shc is not None else 0}
    legacy = {"hp": state_l.get_entity(tid).get_component(HealthComponent).hp,
              "shield": shc_l.get_total_shield() if shc_l is not None else 0}
    return live, off, legacy, int(sh_before.get(tid) or 0), int(thc.hp)


def _build(build_runner, seed, with_ward: bool):
    """`with_ward=False` : le ward est HORS de la bataille -- ArcaneShield se declenche aussi « at the
    end of his turn » quand Thaumachus ne bouge pas, donc le garder rendrait shield==0 inatteignable."""
    a_units = ([WARD_VIS, TARGET_VIS] if with_ward else [TARGET_VIS])
    return build_runner(seed, extra=[
        "--roster", "1", "--p-units", f"{CASTER_VIS},{FILLER_VIS}",
        "--a-units", ",".join(a_units), "--hp-target", str(HP_TARGET)])["rid"]


def test_ability_limits_without_shield_bit_exact(live_session, rpc, build_runner):
    """NON-REGRESSION : shield == 0 -> le nouvel ordre est bit-identique a l'ancien (le cap porte sur
    la totalite du coup) et colle au live. C'est le regime de TOUTES les validations #67."""
    from engine.entities.pathfinding.board import Board
    rid = _build(build_runner, "6741", with_ward=False)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    dec0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    my_player = (_unit(dec0, CASTER_VIS) or {}).get("owner")
    dec, _c, _t = _approach(rpc, rid, board, my_player)
    live, off, legacy, sh0, hp0 = _cast_and_compare(rpc, rid, dec, my_player, want_shield=False)
    print(f"\n[shield=0] hp={hp0} live={live} off={off} legacy={legacy}")
    assert off["per_hit"] == live["per_hit"], f"per-coup offline {off['per_hit']} != live {live['per_hit']}"
    assert off["hp"] == live["hp"], f"PV offline {off['hp']} != live {live['hp']}"
    assert (legacy["hp"], legacy["shield"]) == (off["hp"], off["shield"]), \
        "shield==0 doit rester bit-identique a l'ancien ordre"


def test_ability_limits_shield_absorbs_uncapped(live_session, rpc, build_runner):
    """Cible `Resilient` AVEC bouclier : le natif consomme du bouclier le degat ENTIER du coup, PAS le
    degat cape -- la part absorbee n'est jamais soumise aux limites (`CalculateAbilityDamage` retire
    `min(dmg, shield)` AVANT le core limites). L'ancien ordre ne consommait que `hp-1`."""
    from engine.entities.pathfinding.board import Board
    rid = _build(build_runner, "6741", with_ward=True)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    dec0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    my_player = (_unit(dec0, CASTER_VIS) or {}).get("owner")
    dec, _c, _t = _approach(rpc, rid, board, my_player)

    # bouclier : le ward est adjacent a la cible au spawn ; chaque `endturn` traverse le declenchement
    # « fin de tour » d'ArcaneShield, sinon on le fait BOUGER (l'autre bras du trigger).
    for _ in range(20):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        tgt, ward = _unit(dec, TARGET_VIS), _unit(dec, WARD_VIS)
        if tgt is None or ward is None:
            pytest.skip("cible/ward absents")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        sh, _ = _shields(rpc, rid)
        if int(sh.get(tgt["id"]) or 0) > 0:
            break
        ward["mine"] = False
        tt = _tile(board, tgt)
        d = _bfs(board, tt)
        reach = _reachable(rpc, rid, board, dec, ward)
        src = _tile(board, ward)
        pool = [t for t in reach if t != src and d.get(t, 99) <= ARCANE_RANGE] \
            or [t for t in reach if t != src and d.get(t, 99) < d.get(src, 99)]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        col, row = reach[min(pool, key=lambda t: d.get(t, 99))]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": ward["id"], "to": {"col": col, "row": row}}}, 60)

    live, off, legacy, sh0, hp0 = _cast_and_compare(rpc, rid, dec, my_player, want_shield=True)
    print(f"\n[shield>0] hp={hp0} shield_avant={sh0} live={live} off={off} legacy={legacy}")
    assert off["per_hit"] == live["per_hit"], f"per-coup offline {off['per_hit']} != live {live['per_hit']}"
    assert off["hp"] == live["hp"], f"PV offline {off['hp']} != live {live['hp']}"
    assert off["shield"] == live["shield"], \
        f"bouclier restant offline {off['shield']} != live {live['shield']}"
    assert (legacy["hp"], legacy["shield"]) != (off["hp"], off["shield"]), (
        "scenario NON discriminant : l'ancien ordre (cap avant le split) rend le meme etat, "
        "le test ne prouve rien")
