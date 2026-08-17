"""ArcaneShield (thousSorcerer/Thaumachus) — behaviour MIGRE en arbre DSL (#149 slice-23), confronte LIVE.

Valide la feuille NEUVE `CreateShield` (`IdunBattleLogic.Entities.DSLBehaviors$$CreateShield` -> `IdunBattle.Entities.Behaviours.CreateShieldBehaviour$$Execute`) + la migration de `_arcaneshield_grant` en `CreateShield(Target(), ConfigVar(0x27=shieldHp),
self.Id, TurnsFromRounds(1))`. L'arbre natif (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$CreateBehaviour`) accorde un
bouclier 1 round a l'ami prefere (SurroundingFriends sans trait 0x1b, priorite faction > distance > pas-soi)
sinon soi. Le selecteur AI-target LOURD (S) reste imperatif (`_arcaneshield_target`) COLLAPSE en `Target()`,
le montant `ConfigVar(0x27)` (formule V) est calcule imperativement (`ability_var`) -- meme collapse que
FinalJustice (doctrine slice-18/19).

PROTOCOLE (live, deterministe) : build thousSorcerer + 1 allie ThousandSons vs 1 ennemi ; capture l'etat REEL
(stats/PV live). L'oracle du MONTANT = `ability_var("ArcaneShield","shieldHp",...)` (meme gameconfig live que
le behaviour). On confronte :
  - CAS ALLIE : allie REPOSITIONNE adjacent (dans le rayon) -> `_arcaneshield_target` choisit l'allie ->
    `_arcaneshield_grant` pose un bouclier `amount` (source ArcaneShield, remaining 1) SUR L'ALLIE ;
    `shield_total` de l'allie augmente de `amount` ; la valeur de retour porte target=allie, amount, remaining=1.
  - CAS SOI : allie adjacent mais MORT (exclu des candidats) -> `_arcaneshield_target` = soi -> le bouclier
    est pose SUR L'OWNER (fallback << lastly casting it on himself >>).

DRIVE POSITIONS (doctrine) : on place l'allie sur une tuile voisine de l'owner (HP/stats REELS conserves) ->
adjacence garantie sans dependre du deploiement. Board+stats REELS, seules les positions controlees. ASCII only.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.abilities.base import convert_rounds_to_turns
from engine.runner.operations import triggers as T
from engine.runner.components import (UnitComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, ShieldComponent)

OWNER_VIS = "thousSorcerer"          # Thaumachus, passive ArcaneShield (mech:shield)
ALLY_VIS = "thousTerminator"         # allie ThousandSons (meme faction -> priorite 0)
BUILD = ["--roster", "1", "--p-units", f"{OWNER_VIS},{ALLY_VIS}", "--a-units", "necroWarden"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _tile(state, board, uid):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return board.id_at(pc.col, pc.row) if pc is not None else None


def _shield_total(state, uid):
    e = state.get_entity(uid)
    shc = e.get_component(ShieldComponent) if e is not None else None
    return shc.get_total_shield() if shc is not None else 0


def _place_adjacent(state, board, owner_id, ally_id):
    """DRIVE : place l'allie sur une tuile VOISINE walkable de l'owner (dans le rayon). Renvoie la tuile."""
    opc = state.get_entity(owner_id).get_component(PositionComponent)
    otile = board.id_at(opc.col, opc.row)
    for n in board.neighbours(otile):
        if board.walkable(n):
            col, row = board.coord(n)
            apc = state.get_entity(ally_id).get_component(PositionComponent)
            apc.col, apc.row = col, row
            return n
    return None


def _expected_amount(state, owner_id):
    from engine.entities.effects.magnitude import ability_var
    sc = state.get_entity(owner_id).get_component(StatsComponent)
    if sc is None:
        return 0
    ctx = sc.ctx
    return int(ability_var("ArcaneShield", "shieldHp", int(getattr(ctx, "passive_ability_level", 0) or 0),
                           multiplier_pct=int(getattr(ctx, "ability_variables_multiplier", 100) or 100)) or 0)


def test_arcaneshield_grant_live(live_session, rpc, build_runner):
    """ArcaneShield migre : la feuille `CreateShield` pose le bouclier sur la cible AI-choisie (allie in-range)
    avec le montant `shieldHp` correct ; fallback SOI quand aucun allie eligible. Chaine feuille CreateShield
    -> ShieldComponent.add_or_update_shield (bit-exact vs l'imperatif : meme appel)."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    if not _ok(dec):
        pytest.skip("decisionView KO")
    od = next((u for u in (dec.get("units") or []) if u.get("visualId") == OWNER_VIS and u.get("alive")), None)
    ad = next((u for u in (dec.get("units") or []) if u.get("visualId") == ALLY_VIS and u.get("alive")), None)
    if od is None or ad is None:
        pytest.skip("owner/allie absents de l'etat capture")
    owner_id, ally_id = od["id"], ad["id"]

    # --- CAS ALLIE : allie adjacent vivant -> cible = allie, bouclier sur l'allie -----------------
    state = load_state(dec, ob, snap, board=board)
    if state.get_entity(owner_id) is None or state.get_entity(ally_id) is None:
        pytest.skip("owner/allie absents offline (snapshot incomplet)")
    amount = _expected_amount(state, owner_id)
    if amount <= 0:
        pytest.skip("shieldHp indispo (config/level) -> montant non calculable")

    if _place_adjacent(state, board, owner_id, ally_id) is None:
        pytest.skip("aucune tuile voisine walkable (owner en coin)")
    # verifie que l'owner et l'allie sont bien sur des equipes AMIES (meme team)
    oo = state.get_entity(owner_id).get_component(OwnerComponent)
    ao = state.get_entity(ally_id).get_component(OwnerComponent)
    assert oo is not None and ao is not None and oo.team == ao.team, "owner/allie pas sur la meme team"

    tgt = T._arcaneshield_target(state, owner_id)
    assert tgt == ally_id, f"_arcaneshield_target={tgt} != allie in-range {ally_id} (attendu : non-soi prefere)"

    before = _shield_total(state, ally_id)
    res = T._arcaneshield_grant(state, owner_id)
    assert res is not None and res.get("target") == ally_id, f"bouclier pas pose sur l'allie (res={res})"
    assert res.get("amount") == amount, f"montant {res.get('amount')} != shieldHp attendu {amount}"
    # #98 : le 4e arg natif de `CreateShield` est `TurnsFromRounds(1)` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$CreateBehaviour, verifie au
    # decompile) -> la duree passe par `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` = `count(joueurs
    # non-Environment) x 1`. L'ancienne attente `== 1` gravait l'IDENTITE (fausse des 2 joueurs).
    exp_dur = convert_rounds_to_turns(state, 1)
    assert res.get("remaining") == exp_dur, (
        f"duree {res.get('remaining')} != ConvertRoundsToTurns(TurnsFromRounds(1))={exp_dur} "
        f"(facteur={state.turn_order_player_count})")
    after = _shield_total(state, ally_id)
    assert after == before + amount, f"shield_total allie {before}->{after} != +{amount}"
    # instance posee : source ArcaneShield, remaining = ConvertRoundsToTurns(1), amount
    ashc = state.get_entity(ally_id).get_component(ShieldComponent)
    inst = next((s for s in ashc.shields if s.source == "ArcaneShield"), None)
    assert inst is not None and int(inst.amount) == amount and inst.remaining == exp_dur, \
        f"instance de bouclier ArcaneShield incorrecte ({inst})"
    print(f"[ArcaneShield ALLIE] OK : bouclier {amount} (1 round) pose sur allie {ally_id}, total {before}->{after}")

    # --- CAS SOI : allie mort -> exclu des candidats -> cible = soi -------------------------------
    state2 = load_state(dec, ob, snap, board=board)
    _place_adjacent(state2, board, owner_id, ally_id)
    auc = state2.get_entity(ally_id).get_component(UnitComponent)
    if auc is not None:
        auc.alive = False                                  # allie DOWN -> exclu de SurroundingFriends
    tgt2 = T._arcaneshield_target(state2, owner_id)
    assert tgt2 == owner_id, f"_arcaneshield_target={tgt2} != soi (fallback attendu, seul allie mort)"
    before_self = _shield_total(state2, owner_id)
    res2 = T._arcaneshield_grant(state2, owner_id)
    assert res2 is not None and res2.get("target") == owner_id, f"fallback SOI KO (res={res2})"
    after_self = _shield_total(state2, owner_id)
    assert after_self == before_self + amount, f"shield_total owner {before_self}->{after_self} != +{amount}"
    print(f"[ArcaneShield SOI] OK : fallback -> bouclier {amount} sur owner {owner_id}, total {before_self}->{after_self}")

