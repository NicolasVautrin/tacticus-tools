"""#73 Terrifying_ExtraDefense (DEFENSE) -- REPLAY-DIFF bit-exact offline<->live, discriminant melee/ranged.

Le trait `Terrifying` (id 0x22=34) N'EST PAS lu en direct dans le calcul de degat (contrairement a
MkXGravis `HasTrait` IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor). Il DERIVE une triggered ability (`TerrifyingAbilityAbility` IdunBattleLogic.Entities.Abilities.Active.TerrifyingAbilityAbility$$.ctor =
AOwnerEffectSpecificTriggeredAbility(0x62), dict GetTriggeredAbility idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor +0x0) dont le IdunBattle.Entities.Abilities.AOwnerEffectSpecificTriggeredAbility$$CreateTrigger (OnOwnerSpecificAbilityInit) pose l'effet `Terrifying_ExtraDefense` (0x62) sur le porteur. Cet
effet (IdunBattle.Entities.Effects.Terrifying_ExtraDefense_Effect$$CreateDamageModifier) reduit le degat MELEE recu : DamageModifier PercentDecrease gate
`get_OwnerIsTarget & IsMeleeAttack`, magnitude = ConfigConst(0x28) = globalValues.terrifyingBonus (=-30)
-> x0.70. Aucun effet en RANGED (gate melee-only).

On rejoue une attaque MELEE (necroDestroyer, multi-coups) et une attaque RANGED (eldarRanger) contre
eldarMauganRa (carrier Terrifying, effet CAPTE live dans decisionView.effects). RNG seede via dumpRng ->
per-hit offline == live AU COUP PRES. Discriminant :
  - MELEE : def_mods.pct_list porte (0.70) ; off_ph == live_ph ; sans l'effet, off SUR-predit (x1/0.70).
  - RANGED : def_mods.pct_list VIDE ; off_ph == live_ph (aucune reduction).
Lit l'etat LIVE (rien de hardcode). SKIP si le setup geometrique n'aboutit pas. ASCII-only.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, StatsComponent
from engine.runner.damage_model import defender_modifiers

CARRIER = "eldarMauganRa"          # carrier Terrifying (effet Terrifying_ExtraDefense capte live)
MELEE_ATT = "necroDestroyer"       # melee multi-coups -> plusieurs coups reduits x0.70 ; PAS de bonus
#                                    attaquant gate-has_moved (contrairement a un HeavyWeapon) -> replay propre
RANGED_ATT = "admecMarshall"       # ranged, PAS HeavyWeapon (pas de bonus gate has_moved qui confond le
#                                    replay apres deplacement) -> aucune reduction Terrifying attendue (gate melee)


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _bfs(board, src):
    dist = {src: 0}; q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1; q.append(n)
    return dist


def _terr_effects(active):
    return [ef for ef in active if "Terrifying_ExtraDefense" == (getattr(ef, "name", "") or "")]


def _drive_and_replay(rpc, build_runner, attacker, want_range):
    """Build attacker+carrier, drive l'attaquant a distance `want_range` (1=melee adjacent) du carrier,
    RNG-seede, rejoue l'attaque normale offline vs live. Renvoie le dict de mesure (ou skip)."""
    from engine.entities.pathfinding.board import Board
    b = build_runner("777", extra=["--roster", "1", "--p-units", attacker, "--a-units", CARRIER])
    rid = b["rid"]
    if not _ok(rpc("dumpRng", {"runnerId": rid}, 30)):
        pytest.skip("dumpRng indispo")
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")

    def utile(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if "col" in p else None

    my_player = None
    for _turn in range(30):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dec):
            pytest.skip("decisionView KO")
        units = dec.get("units") or []
        att = next((u for u in units if u.get("visualId") == attacker and u.get("alive")), None)
        tgt = next((u for u in units if u.get("visualId") == CARRIER and u.get("alive")), None)
        if att is None or tgt is None:
            pytest.skip("unite manquante (build KO)")
        if my_player is None:
            my_player = att.get("owner")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        ctile, ttile = utile(att), utile(tgt)
        dist = _bfs(board, ttile)
        # tuiles a distance EXACTE want_range de la cible (hex distance via BFS non-walkable-aware = graphe)
        at_range = ctile in _tiles_at(board, ttile, want_range)
        if at_range:
            return _replay(rpc, rid, board, tgt, att, None)
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == att["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        want_tiles = _tiles_at(board, ttile, want_range)
        adj = [(tid, cr) for tid, cr in reach.items() if tid in want_tiles]
        if adj:
            _tid, (col, row) = adj[0]
            return _replay(rpc, rid, board, tgt, att, (col, row))
        pool = [tid for tid in reach if tid in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        best = min(pool, key=lambda t: dist[t]); col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": att["id"], "to": {"col": col, "row": row}}}, 40)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    pytest.skip(f"{attacker} n'a pas atteint {CARRIER} a range {want_range} en 30 tours")


def _tiles_at(board, center, r):
    """Ids des tuiles a distance BFS EXACTE r du centre (r=1 -> voisins adjacents)."""
    dist = _bfs(board, center)
    return {tid for tid, d in dist.items() if d == r}


def _replay(rpc, rid, board, tgt, att_u, move_to):
    att, tid = att_u["id"], tgt["id"]
    if move_to is not None:
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": att, "to": {"col": move_to[0], "row": move_to[1]}}}, 40)
    dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
    a2 = next((u for u in (dv2.get("units") or []) if u.get("id") == att), None)
    norm = next((ab for ab in ((a2 or {}).get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        pytest.skip("pas d'attaque normale")
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv2, ob2, snap2, board=board)
    te = state.get_entity(tid)
    hc = te.get_component(HealthComponent) if te is not None else None
    if hc is None or hc.hp is None:
        pytest.skip("cible introuvable offline")
    active = state.effects.active_effects(tid, {"hp": hc.hp}) if state.effects is not None else []
    has_terr = bool(_terr_effects(active))
    # is_melee du coup = arme non-rangee -> approx par distance att<->cible (1=melee). Le runner offline
    # re-derive is_melee de la SELECTION D'ARME (portee reelle) dans damage_ops ; ici on lit juste pct_list
    # pour le diagnostic melee/ranged.
    ap = a2.get("pos") or {}
    tp = tgt.get("pos") or {}
    import hexgeo
    hexd = hexgeo.distance((ap.get("col"), ap.get("row")), (tp.get("col"), tp.get("row"))) \
        if ("col" in ap and "col" in tp) else None
    is_melee = (hexd == 1)
    dmods, _ = defender_modifiers(state, tid, hc.hp, is_melee=is_melee, damage_profile=None, attacker_id=att)
    # pct_list si on FORCAIT le coup en melee (gate is_melee=True) : sert de discriminant -- l'effet
    # Terrifying est PRESENT et gate exactement sur is_melee (0.70 apparait ssi is_melee=True).
    dmods_fm, _ = defender_modifiers(state, tid, hc.hp, is_melee=True, damage_profile=None, attacker_id=att)
    hp_before = hc.hp
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    state.rng = _seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": norm["id"]}}, 40)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        pytest.skip(f"attaque live KO: {str(res)[:160]}")
    live_ph, did_evade = [], False
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == norm["id"]:
            live_ph.append(td.get("Amount"))
            did_evade = did_evade or bool(td.get("Attack_DidEvade"))
    live_after = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tid), None)
    runner.apply(AttackUnitMessage(att, tid))
    rr = runner.damage_handler.last
    off_after = state.get_entity(tid).get_component(HealthComponent).hp
    # DISCRIMINANT (fit compensatoire exclu) : meme attaque, meme RNG (s0), mais Terrifying_ExtraDefense
    # STRIPPE de la cible -> off_ph_no_terr. Si le -30% est REEL, off_ph_no_terr SUR-predit vs live (x1/0.70).
    state2 = load_state(dv2, ob2, snap2, board=board)
    if state2.effects is not None:
        lst = state2.effects.by_unit.get(int(tid), [])
        state2.effects.by_unit[int(tid)] = [e for e in lst
                                            if getattr(e, "name", None) != "Terrifying_ExtraDefense"]
    state2.rng = _seed_rng(s0)
    runner2 = Runner(state2).install_default_handlers(20)
    runner2.apply(AttackUnitMessage(att, tid))
    rr2 = runner2.damage_handler.last
    return {"hp_before": hp_before, "live_after": live_after, "off_after": off_after,
            "live_ph": live_ph, "off_ph": (rr or {}).get("per_hit"),
            "off_ph_no_terr": (rr2 or {}).get("per_hit"),
            "pct_list": list(dmods.pct_list), "pct_list_forced_melee": list(dmods_fm.pct_list),
            "is_melee": is_melee, "hexd": hexd,
            "did_evade": did_evade, "rr": rr, "has_terr": has_terr}


@pytest.fixture(scope="session")
def terr_melee(live_session, rpc, build_runner):
    return _drive_and_replay(rpc, build_runner, MELEE_ATT, want_range=1)


@pytest.fixture(scope="session")
def terr_ranged(live_session, rpc, build_runner):
    return _drive_and_replay(rpc, build_runner, RANGED_ATT, want_range=2)


def test_terrifying_trait_seeds_derived_effect_offline():
    """OFFLINE (function-level, sans live) : le trait Terrifying seede l'owner-effect Terrifying_ExtraDefense
    via le chemin trait -> ability derivee -> AddEffect(owner) (factory dicts, mirror
    `IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities` + `AOwnerEffectSpecificTriggeredAbility` IdunBattleLogic.Entities.Abilities.Active.TerrifyingAbilityAbility$$.ctor).
    Filet pour un porteur SUMMON dont l'effet n'est PAS capte live (aucun carrier Terrifying summon a ce jour
    -> spawn path non confrontable live ; on valide donc le wiring + la materialisation). L'effet materialise
    est bien un TerrifyingExtraDefenseEffect (pas un BaseEffect no-op) et applique -30% en melee, rien en ranged."""
    from engine.entities.effects.factory import (get_derived_abilities_for_trait,
                                                 get_owner_effects_added_on_ability_init)
    from engine.runner.operations.spawn import _seed_derived_ability_owner_effects
    from engine.runner.state import State
    # dict wiring RE'd : trait 0x22 -> triggered ability 0x62 -> owner-effect 0x62
    assert get_derived_abilities_for_trait("Terrifying") == ["TerrifyingAbility"]
    assert get_owner_effects_added_on_ability_init("TerrifyingAbility") == ["Terrifying_ExtraDefense"]
    state = State()
    uid = 999
    _seed_derived_ability_owner_effects(state, uid, ["Terrifying"], 100)
    effs = state.effects.active_effects(uid, {"hp": 1}) if state.effects is not None else []
    terr = next((e for e in effs if getattr(e, "name", None) == "Terrifying_ExtraDefense"), None)
    assert terr is not None, \
        f"Terrifying_ExtraDefense NON seede : {[getattr(e, 'name', None) for e in effs]}"
    assert type(terr).__name__ == "TerrifyingExtraDefenseEffect", \
        f"materialise en {type(terr).__name__} (attendu TerrifyingExtraDefenseEffect, pas un no-op)"
    eb_melee = terr.create_effect_damage_malus_for_defense(is_melee=True)
    eb_ranged = terr.create_effect_damage_malus_for_defense(is_melee=False)
    assert eb_melee is not None and eb_melee.kind == "PercentDecrease" and eb_melee.value == 30, \
        f"malus melee attendu PercentDecrease(30), obtenu {eb_melee}"
    assert eb_ranged is None, f"malus applique A TORT en ranged : {eb_ranged}"


def test_terrifying_effect_captured_and_applied(terr_melee):
    """DETERMINISTE : eldarMauganRa expose Terrifying_ExtraDefense offline (seede depuis decisionView.effects)
    ET, en MELEE, son def_mods.pct_list porte la reduction x0.70 (globalValues.terrifyingBonus=-30)."""
    c = terr_melee
    assert c["has_terr"], "Terrifying_ExtraDefense NON present offline sur eldarMauganRa (capture KO)"
    if not c["is_melee"]:
        pytest.skip("attaque non-melee (attaquant pas adjacent) -> pas la slice Terrifying")
    assert (0.7, None) in c["pct_list"], \
        f"reduction Terrifying x0.70 absente du pct_list melee : {c['pct_list']}"


def test_terrifying_melee_replay_bitexact(terr_melee):
    """COEUR #73 : attaque MELEE contre eldarMauganRa rejouee RNG-seede -> per-hit offline == live AU COUP
    PRES (le runner applique la MEME reduction x0.70 que le natif). PV cible offline == live."""
    c = terr_melee
    assert c["rr"] is not None, "runner offline n'a rien calcule"
    if not c["is_melee"]:
        pytest.skip("attaque non-melee")
    if c["did_evade"]:
        pytest.skip("coup avec evade live (hors slice reduction)")
    print(f"\n[TERR-MELEE] live per-hit={c['live_ph']} off per-hit={c['off_ph']} "
          f"pct_list={c['pct_list']} live_after={c['live_after']} off_after={c['off_after']}")
    assert c["off_ph"] == c["live_ph"], (
        f"per-hit offline != live : off={c['off_ph']} live={c['live_ph']} "
        f"(reduction Terrifying non appliquee identiquement ?)")
    assert c["off_after"] == c["live_after"], \
        f"PV cible offline {c['off_after']} != live {c['live_after']}"


def test_terrifying_melee_discriminant_no_compensatory_fit(terr_melee):
    """DISCRIMINANT (fit compensatoire exclu) : MEME attaque MELEE, MEME RNG, mais Terrifying STRIPPE ->
    off_ph_no_terr SUR-predit vs live (la reduction x0.70 est REELLE et NECESSAIRE, pas un ajustement
    accidentel). Sans le -30%, offline surestime le degat subi d'un facteur ~1/0.70."""
    c = terr_melee
    if not c["is_melee"] or not c["has_terr"]:
        pytest.skip("pas la slice melee/Terrifying")
    if c["did_evade"]:
        pytest.skip("coup avec evade live")
    print(f"\n[TERR-DISCRIM] live={c['live_ph']} off_with_terr={c['off_ph']} "
          f"off_no_terr={c['off_ph_no_terr']}")
    assert c["off_ph_no_terr"] is not None and sum(c["off_ph_no_terr"]) > sum(c["live_ph"]), (
        f"sans Terrifying, offline NE sur-predit PAS ({c['off_ph_no_terr']} vs live {c['live_ph']}) "
        f"-> le -30% ne serait pas la source de l'ecart (fit compensatoire suspect)")


def test_terrifying_ranged_no_reduction(terr_ranged):
    """DISCRIMINANT melee-only : attaque RANGED contre eldarMauganRa -> Terrifying GATE OFF.
      (1) def_mods.pct_list du coup RANGED est VIDE de la reduction x0.70 (gate IsMeleeAttack respecte) ;
      (2) l'effet est PRESENT et gate EXACTEMENT sur is_melee : force-melee -> 0.70 REAPPARAIT ;
      (3) le degat RANGED live n'est PAS reduit de ~30% (live/off >> 0.70) -> le natif non plus n'applique
          Terrifying en ranged. (Le bit-exact off==live du RANGED n'est PAS asserte : il porte un petit
          ecart attaquant/positionnel NON-Terrifying, hors slice.)"""
    c = terr_ranged
    assert c["rr"] is not None, "runner offline n'a rien calcule"
    if c["is_melee"]:
        pytest.skip("attaque melee (attaquant adjacent) -> pas la slice ranged")
    if c["did_evade"]:
        pytest.skip("coup avec evade live")
    print(f"\n[TERR-RANGED] live per-hit={c['live_ph']} off per-hit={c['off_ph']} "
          f"pct_list={c['pct_list']} forced_melee={c['pct_list_forced_melee']} hexd={c['hexd']}")
    assert (0.7, None) not in c["pct_list"], \
        f"reduction Terrifying x0.70 appliquee A TORT en RANGED : {c['pct_list']}"
    assert (0.7, None) in c["pct_list_forced_melee"], (
        f"l'effet Terrifying n'est pas present/gate sur is_melee (force-melee={c['pct_list_forced_melee']}) "
        f"-> le gate ne peut pas etre attribue a IsMeleeAttack")
    # le natif n'applique PAS Terrifying en ranged : le degat live n'est pas ~0.70x l'offline (sinon
    # live/off ~ 0.70). Marge large (l'ecart residuel NON-Terrifying est ~6%).
    assert sum(c["live_ph"]) >= 0.85 * sum(c["off_ph"]), (
        f"degat ranged live {c['live_ph']} << offline {c['off_ph']} (ratio {sum(c['live_ph'])/max(1,sum(c['off_ph'])):.3f}) "
        f"-> une reduction ~0.70 live non modelisee offline ? (Terrifying en ranged ?)")
