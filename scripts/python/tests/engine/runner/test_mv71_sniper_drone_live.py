"""#61bis tranche 1 : MV71SniperDroneSquadAttack (1076, Sho'syl/tauMarksman) — EXECUTION confrontee au LIVE.

Port : `engine/runner/abilities/loki/mv71.py` (chaine `ExecuteBehaviour @181108900`, RE case-61bis §5).
GROUND TRUTH de reference : case-61bis §2 (runner 88, seed 61001, MC1_67).

CE FICHIER :
  1. `test_mv71_cast_live_offline_agreement` : replay-diff du cast a DISTANCE — meme etat pre-cast
     (dec/ob/snap/dumpRng), cast 1076 live ET offline, puis diff : TUILE du drone (confronte le
     tie-break PickTile), stats du drone (WithStatsFromConfig), degat cible (bit-exact via MT seede),
     Markerlight sur la cible, 1132/1133 consommes post-cast (overrides revertes).
  2. `test_mv71_cap_eviction_live` : exerce le cap maxSummons=3 (JAMAIS exerce par le GT §2) — au 4e
     cast, le drone le plus FAIBLE est retire AVANT le spawn (sens du tri SortByFormula dir=1, question
     ouverte §6) ; replay-diff du 4e cast (evince + tuile du nouveau drone).

NON couvert ici (tranches suivantes) : dispatch MELEE (slice 2 — exige de driver Sho'syl au contact),
prediction distance (slice 3), +15% Markerlight sur un tir de drone ULTERIEUR (AI-turn replay).
DRIVE POSITIONS/STATE (doctrine) : la geometrie du build MC1_67 place Sho'syl hors contact de la
cible -> skip propre sinon. ASCII only.
"""
from __future__ import annotations

import pytest

CASTER_VIS = "tauMarksman"         # Sho'syl — son attaque NORMALE est l'ability 1076
DRONE_VIS = "tauSmnDroneSniper"    # cle de config ET visualId live (GT §2)
TARGET_VIS = "astraYarrick"
ABILITY = 1076
INITIAL_DMG, RESET_INITIAL_DMG, MARKERLIGHT = 1132, 1133, 1122
BUILD = ["--p-units", f"{CASTER_VIS},templAncient", "--a-units", TARGET_VIS,
         "--hp-target", "200000"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _find_all(dec, vis):
    return [u for u in (dec.get("units") or []) if u.get("visualId") == vis and u.get("alive")]


def _effect_types(u):
    return {e.get("effectType") for e in (u.get("effects") or [])}


def _hp(ob, uid):
    for u in (ob.get("units") or []):
        if u.get("squadId") == uid and not u.get("isDead"):
            return u.get("hp")
    return None


def _advance_to_my_turn(rpc, rid, vis, max_iter=12):
    """Avance jusqu'au tour du proprietaire de `vis` (endturn ; tour adverse -> aiPlayTurn)."""
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if not _ok(dec):
            return None, None
        u = _find(dec, vis)
        if u is None:
            return dec, None
        if dec.get("currentPlayer") == u.get("owner"):
            return dec, u
        rpc("aiPlayTurn", {"runnerId": rid}, 180)
        dec2 = rpc("decisionView", {"runnerId": rid}, 150)
        if _ok(dec2) and dec2.get("currentPlayer") != (u or {}).get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def _capture(rpc, rid):
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s = rpc("dumpRng", {"runnerId": rid}, 30)
    return dec, ob, snap, s


def _offline_state(dec, ob, snap, s, board):
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    state = load_state(dec, ob, snap, board=board)
    if _ok(s):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s["mt"])
        rng.mti = s["mti"]
        state.rng = rng
    return state


def _cast_live(rpc, rid, caster_id, target_id):
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "targetId": target_id, "abilityType": ABILITY},
        "captureEvents": True}, 120)
    return res


def _cast_ok(res):
    """ok du RPC ET de l'action INTERNE (mutated : un cast hors-portee rend ok=True/mutated=False)."""
    if not _ok(res):
        return False
    a0 = (res.get("actions") or [{}])[0]
    return bool(a0.get("ok")) and bool(a0.get("mutated"))


def _drive_sho_in_range(rpc, rid, board, max_turns=10, lo=2, hi=3):
    """DRIVE Sho'syl (move 2, r3) a distance hex [lo..hi] de la cible — defaut [2..3] = la branche
    RANGED de 1076 (adjacent => dispatch melee, hors r3 => cast no-op TargetIsInRange) ; [1..1] = la
    branche MELEE. Le build MC1_67 les spawn loin l'un de l'autre -> approche par moves successifs
    (aiMovableTiles), l'ennemi (IA) approchant en face via `_advance_to_my_turn`.
    Renvoie (dec, sho, tgt) prets a caster, ou (None,)*3."""
    import hexgeo
    for _ in range(max_turns):
        dec, sho = _advance_to_my_turn(rpc, rid, CASTER_VIS)
        if sho is None:
            return None, None, None
        tgt = _find(dec, TARGET_VIS)
        if tgt is None:
            return None, None, None
        sp, tp = sho.get("pos") or {}, tgt.get("pos") or {}
        d = hexgeo.distance((sp["col"], sp["row"]), (tp["col"], tp["row"]))
        if lo <= d <= hi:
            return dec, sho, tgt
        # move vers une tuile atteignable a distance cible dans [lo..hi] sinon minimisant |d-hi|
        # (trop loin -> approche ; trop pres -> recule), puis re-eval au MEME tour.
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == sho["id"]), None)
        tiles = [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])
                 if t.get("col") is not None]
        if tiles:
            def _key(pos):
                dd = hexgeo.distance(pos, (tp["col"], tp["row"]))
                return (0 if lo <= dd <= hi else 1, abs(dd - hi), dd)
            best = min(tiles, key=_key)
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": sho["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
            dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            sho2, tgt2 = _find(dec2, CASTER_VIS), _find(dec2, TARGET_VIS)
            if sho2 is not None and tgt2 is not None:
                sp2, tp2 = sho2.get("pos") or {}, tgt2.get("pos") or {}
                if lo <= hexgeo.distance((sp2["col"], sp2["row"]), (tp2["col"], tp2["row"])) <= hi:
                    return dec2, sho2, tgt2
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None, None


def _snap_unit_stats(snap, vis):
    """Stats natives d'une unite du combatSnapshot par visualId (drone : 1 seule instance visee -> la
    DERNIERE ajoutee si plusieurs)."""
    out = None
    for u in (snap.get("units") or []):
        v = u.get("visualId") or (u.get("unitConfig") or {}).get("visualId")
        if v == vis:
            out = u
    return out


def test_mv71_cast_live_offline_agreement(live_session, rpc, build_runner):
    """Replay-diff du cast 1076 a DISTANCE : tuile du drone (tie-break PickTile), stats
    WithStatsFromConfig, degat cible (bit-exact, MT seede), Markerlight, 1132/1133 consommes."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import (StatsComponent, PositionComponent, UnitComponent,
                                          HealthComponent)
    from engine.runner.abilities.loki import MV71SniperDroneSquadAttackAbility
    from engine.runner.operations.spawn import build_summon_context
    from engine.entities.stats import StatType

    rid = build_runner("61001", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec, sho, tgt = _drive_sho_in_range(rpc, rid, board)
    if sho is None or tgt is None:
        pytest.skip("drive KO : Sho'syl pas amene a distance [2..3] de la cible")
    caster_id, target_id = sho["id"], tgt["id"]
    n_drones0 = len(_find_all(dec, DRONE_VIS))

    dec0, ob0, snap0, s0 = _capture(rpc, rid)
    hp0 = _hp(ob0, target_id)
    state = _offline_state(dec0, ob0, snap0, s0, board)
    if state.get_entity(caster_id) is None or state.rng is None or state.effects is None:
        pytest.skip("etat offline incomplet (snapshot/rng)")

    # --- LIVE ---
    res = _cast_live(rpc, rid, caster_id, target_id)
    assert _cast_ok(res), f"cast live KO (interne): {str(res)[:300]}"
    dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    drones2 = _find_all(dec2, DRONE_VIS)
    assert len(drones2) == n_drones0 + 1, \
        f"live : attendu +1 drone ({n_drones0 + 1}), obtenu {len(drones2)}"
    live_drone = drones2[-1]
    live_dpos = live_drone.get("pos") or {}
    hp2 = _hp(ob2, target_id)
    live_dmg = (hp0 - hp2) if (hp0 is not None and hp2 is not None) else None

    # --- OFFLINE (meme etat pre-cast) ---
    diag = MV71SniperDroneSquadAttackAbility().execute_behaviour(state, caster_id, target_id) or {}
    assert diag.get("melee") is False, f"branche melee inattendue: {diag}"
    assert len(diag.get("spawned") or []) == 1, f"offline : pas de drone spawne ({diag})"
    off_drone = diag["spawned"][0]
    ode = state.get_entity(off_drone)
    opc = ode.get_component(PositionComponent)
    osc = ode.get_component(StatsComponent)

    # 1) TUILE : le tie-break PickTile (utilite Tile + ClosestToParent collapses) == le natif.
    assert (opc.col, opc.row) == (live_dpos.get("col"), live_dpos.get("row")), \
        (f"PickTile : tuile offline ({opc.col},{opc.row}) != live "
         f"({live_dpos.get('col')},{live_dpos.get('row')}) — tie-break a raffiner "
         f"(SpawnTileUtility @1810eff90)")

    # 2) STATS du drone (WithStatsFromConfig, niveau passif du caster) == natives.
    live_stats = ((_snap_unit_stats(snap2, DRONE_VIS) or {}).get("stats") or {})
    if live_stats:
        assert int(osc.ctx.stat(StatType.ATTACK)) == int(live_stats.get("attack")), \
            f"attack drone offline {osc.ctx.stat(StatType.ATTACK)} != live {live_stats.get('attack')}"
        assert int(osc.ctx.stat(StatType.FIXED_ARMOR)) == int(live_stats.get("fixedArmor")), \
            (f"fixedArmor drone offline {osc.ctx.stat(StatType.FIXED_ARMOR)} != live "
             f"{live_stats.get('fixedArmor')}")
    ohc = ode.get_component(HealthComponent)
    live_dhp = _hp(ob2, live_drone["id"])
    if live_dhp is not None and int(live_dhp) > 0:
        # PV du drone live encore pleins juste apres le cast (personne ne l'a frappe).
        assert int(ohc.hp_max) == int(live_dhp), \
            f"hp drone offline {ohc.hp_max} != live {live_dhp} (summonHp KO)"

    # 3) DEGAT cible : bit-exact via le MT seede (1er conso RNG = les rolls de l'attaque commandee).
    off_total = ((diag.get("attack") or {}).get("total"))
    if live_dmg is not None:
        assert off_total == live_dmg, \
            f"degat commande offline {off_total} != live {live_dmg} (rolls {((diag.get('attack') or {}).get('rolls'))})"

    # 4) MARKERLIGHT sur la cible (les deux faces).
    tgt2 = next((u for u in (dec2.get("units") or []) if u.get("id") == target_id), None)
    assert MARKERLIGHT in _effect_types(tgt2 or {}), "live : Markerlight absent de la cible"
    assert state.effects.has_effect(target_id, effect_type=MARKERLIGHT), \
        "offline : Markerlight absent de la cible"

    # 5) 1132/1133 CONSOMMES post-cast (TargetTrigger On(10)&OwnerIsCaster) + overrides revertes.
    assert not (_effect_types(live_drone) & {INITIAL_DMG, RESET_INITIAL_DMG}), \
        f"live : 1132/1133 encore presents sur le drone ({_effect_types(live_drone)})"
    assert not state.effects.has_effect(off_drone, effect_type=INITIAL_DMG), "offline : 1132 non consomme"
    assert not state.effects.has_effect(off_drone, effect_type=RESET_INITIAL_DMG), \
        "offline : 1133 non consomme"
    # post-revert : l'ATTACK du drone offline == sa stat PROPRE (summonDmg), plus l'override du parent.
    cctx = state.get_entity(caster_id).get_component(StatsComponent).ctx
    lvl = getattr(cctx, "passive_ability_level", None) or getattr(cctx, "active_ability_level", None)
    mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
    own = build_summon_context(0, DRONE_VIS, "MV71SniperDroneSquad", lvl, mult)
    assert int(osc.ctx.stat(StatType.ATTACK)) == int(own.attack), \
        f"override non reverte : attack drone {osc.ctx.stat(StatType.ATTACK)} != propre {own.attack}"

    print(f"[MV71 cast] tuile=({opc.col},{opc.row}) degat={off_total} (live {live_dmg}) "
          f"drone hp={ohc.hp_max} atk={osc.ctx.stat(StatType.ATTACK)} markerlight OK 1132/1133 consommes")


def test_mv71_cap_eviction_live(live_session, rpc, build_runner):
    """Cap maxSummons=3 (question ouverte §6 : sens du tri + double eviction) : 3 casts posent 3 drones ;
    au 4e cast, le drone le plus FAIBLE (SortByFormula Health dir=1 -> First) est RETIRE avant le spawn.
    Replay-diff du 4e cast : meme evince, meme tuile du nouveau drone, total drones == 3 des deux cotes."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import PositionComponent, UnitComponent
    from engine.runner.abilities.loki import MV71SniperDroneSquadAttackAbility

    rid = build_runner("61002", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    # 3 casts (un par tour de Sho'syl, apres drive a distance [2..3]) -> 3 drones au cap.
    for shot in range(3):
        dec, sho, tgt = _drive_sho_in_range(rpc, rid, board)
        if sho is None or tgt is None:
            pytest.skip(f"drive KO au tir {shot + 1}")
        res = _cast_live(rpc, rid, sho["id"], tgt["id"])
        if not _cast_ok(res):
            pytest.skip(f"cast live {shot + 1} KO: {str(res)[:150]}")
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

    dec, sho, tgt = _drive_sho_in_range(rpc, rid, board)
    if sho is None or tgt is None:
        pytest.skip("drive KO au 4e tir")
    drones3 = _find_all(dec, DRONE_VIS)
    if len(drones3) != 3:
        pytest.skip(f"cap non atteint ({len(drones3)}/3 drones vivants — l'ennemi en a tue ?)")
    caster_id, target_id = sho["id"], tgt["id"]

    dec0, ob0, snap0, s0 = _capture(rpc, rid)
    state = _offline_state(dec0, ob0, snap0, s0, board)
    if state.get_entity(caster_id) is None or state.rng is None or state.effects is None:
        pytest.skip("etat offline incomplet (snapshot/rng)")
    ids3 = {u["id"] for u in drones3}

    # --- LIVE 4e cast ---
    res = _cast_live(rpc, rid, caster_id, target_id)
    assert _cast_ok(res), f"4e cast live KO (interne): {str(res)[:300]}"
    dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    drones4 = _find_all(dec2, DRONE_VIS)
    assert len(drones4) == 3, f"live : {len(drones4)} drones apres le 4e cast (attendu 3 = cap)"
    live_gone = ids3 - {u["id"] for u in drones4}
    assert len(live_gone) == 1, f"live : evinces = {live_gone} (attendu exactement 1 — double eviction ?)"
    live_new = next(u for u in drones4 if u["id"] not in ids3)

    # --- OFFLINE 4e cast ---
    diag = MV71SniperDroneSquadAttackAbility().execute_behaviour(state, caster_id, target_id) or {}
    assert len(diag.get("spawned") or []) == 1, f"offline : pas de spawn au 4e cast ({diag})"
    assert diag.get("evicted"), "offline : aucune eviction au cap"
    assert set(diag["evicted"]) == live_gone, \
        f"eviction : offline {diag['evicted']} != live {live_gone} (sens du tri Health ?)"
    ode = state.get_entity(diag["spawned"][0])
    opc = ode.get_component(PositionComponent)
    lp = live_new.get("pos") or {}
    assert (opc.col, opc.row) == (lp.get("col"), lp.get("row")), \
        f"tuile du 4e drone : offline ({opc.col},{opc.row}) != live ({lp.get('col')},{lp.get('row')})"
    n_off = sum(1 for e in state.entities.values()
                if (uc := e.get_component(UnitComponent)) is not None and uc.alive
                and uc.visual_id == DRONE_VIS)
    assert n_off == 3, f"offline : {n_off} drones vivants apres le 4e cast (attendu 3)"
    print(f"[MV71 cap] evince live/offline={live_gone} nouveau=({opc.col},{opc.row}) — cap 3 respecte")


def test_mv71_melee_dispatch_live_offline_agreement(live_session, rpc, build_runner):
    """Tranche 2 — dispatch MELEE (`IsMeleeAttack @181109960`, H53 infirmee) : cible ADJACENTE ->
    1076 DELEGUE integralement a l'attaque normale (`ALoki_NormalAttackAbility.ExecuteBehaviour`) —
    AUCUN drone, AUCUN Markerlight, degat = attaque normale melee de Sho'syl (bit-exact, MT seede)."""
    from engine.entities.pathfinding.board import Board

    rid = build_runner("61003", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec, sho, tgt = _drive_sho_in_range(rpc, rid, board, lo=1, hi=1)
    if sho is None or tgt is None:
        pytest.skip("drive KO : Sho'syl pas amene au CONTACT de la cible")
    caster_id, target_id = sho["id"], tgt["id"]
    n_drones0 = len(_find_all(dec, DRONE_VIS))

    dec0, ob0, snap0, s0 = _capture(rpc, rid)
    hp0 = _hp(ob0, target_id)
    state = _offline_state(dec0, ob0, snap0, s0, board)
    if state.get_entity(caster_id) is None or state.rng is None or state.effects is None:
        pytest.skip("etat offline incomplet (snapshot/rng)")

    res = _cast_live(rpc, rid, caster_id, target_id)
    assert _cast_ok(res), f"cast melee live KO (interne): {str(res)[:300]}"
    dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    hp2 = _hp(ob2, target_id)
    live_dmg = (hp0 - hp2) if (hp0 is not None and hp2 is not None) else None

    # live : PAS de drone, PAS de Markerlight (dispatch, pas la branche summon).
    assert len(_find_all(dec2, DRONE_VIS)) == n_drones0, "live : un drone a spawne sur un cast MELEE"
    tgt2 = next((u for u in (dec2.get("units") or []) if u.get("id") == target_id), None)
    assert MARKERLIGHT not in _effect_types(tgt2 or {}), "live : Markerlight pose sur un cast MELEE"

    from engine.runner.abilities.loki import MV71SniperDroneSquadAttackAbility
    diag = MV71SniperDroneSquadAttackAbility().execute_behaviour(state, caster_id, target_id) or {}
    assert diag.get("melee") is True, f"offline : branche melee non prise ({diag})"
    assert not state.effects.has_effect(target_id, effect_type=MARKERLIGHT), \
        "offline : Markerlight pose sur un cast MELEE"
    off_total = ((diag.get("attack") or {}).get("total"))
    if live_dmg is not None:
        assert off_total == live_dmg, \
            f"degat melee offline {off_total} != live {live_dmg} (delegation attaque normale)"
    print(f"[MV71 melee] dispatch OK degat={off_total} (live {live_dmg}) — pas de drone/Markerlight")


def _collect_pred_rows(dec, scene, att_id, tgt_id, tgt_pos):
    """Rows (tuile candidate, oracle natif ranked, offline) de l'attaque NORMALE 1076 vs la cible.
    Oracle = canal `ranked` de decisionView (dmgMin/dmgMax par position candidate, #102)."""
    import hexgeo
    from engine.playbook import prediction
    rows = []
    norm_ids = {ab.get("id") for u in (dec.get("units") or []) if u.get("id") == att_id
                for ab in (u.get("abilities") or []) if ab.get("kind") == "normal"}
    for ap in (dec.get("attackPlans") or []):
        if ap.get("unitId") != att_id:
            continue
        for ev in (ap.get("evals") or []):
            if ev.get("targetId") != tgt_id or (norm_ids and ev.get("abilityId") not in norm_ids):
                continue
            for rk in (ev.get("ranked") or []):
                if rk.get("dmgMax") is None or rk.get("col") is None:
                    continue
                tile = (rk["col"], rk["row"])
                out = prediction.make_normal_attack_predictions(scene, att_id, tgt_id, tile,
                                                                meta=True)
                if out is None:
                    continue
                res = out[0].prediction.accurate_health_damage
                rows.append({"tile": tile, "d_tgt": hexgeo.distance(tile, tgt_pos),
                             "oracle": (rk.get("dmgMin"), rk.get("dmgMax")),
                             "offline": (res.min, res.max), "meta": out[1]})
    return rows


def _scene_for(rpc, rid, dec):
    from engine.playbook import scene as SC
    from engine.playbook.scene import Scene
    predictor = SC.build_predictor(rpc, rid)
    if predictor is None:
        return None
    return Scene.from_predictor_sctx(predictor, SC.step_context(predictor, dec), None)


def test_mv71_prediction_live_offline_agreement(live_session, rpc, build_runner):
    """Tranche 3 — PREDICTION distance (`PredictAttack @18110a5f0`, arbitrage probe_61bis_pred
    seed 61011/61013 = 15/15 EXACT) : confrontation PER-TUILE (canal ranked) offline vs natif.
      - modele : PickTile scene-side (caster VIRTUELLEMENT sur la tuile candidate : exclusion
        !Contains + adjacence hypothetique), degat = StatAmount(caster, ATTACK, CURRENT), hits =
        1+ExtraHits(caster) (delegue m860), arme du DRONE, widget attaquant ZEROE mais mods
        POSITIONNELS (elevation A LA TUILE DU DRONE) + DEFENSEUR calcules dans le service ;
      - datapoint B : apres un cast (cible Markerlit), les rows natives montent de x1.15 EXACT
        (MarkerlightDmgBonusPct, gate HasFaction(9=T'au) & IsRangedAttack) — l'offline suit via
        le threading faction de l'att_ctx defenseur."""
    from engine.entities.pathfinding.board import Board

    rid = build_runner("61004", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    # --- A : rows PRE-cast (cible sans Markerlight), ACCUMULEES sur <=3 tours (le nombre de
    # rows rankees par tour depend de la geometrie du moment — cf. skip seed 61004 a 1 row) ---
    rows, caster_id, target_id = [], None, None
    for _ in range(3):
        dec, sho, tgt = _drive_sho_in_range(rpc, rid, board)
        if sho is None or tgt is None:
            break
        caster_id, target_id = sho["id"], tgt["id"]
        tp = tgt.get("pos") or {}
        dec_r = rpc("decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True}, 150)
        if not _ok(dec_r):
            break
        scene = _scene_for(rpc, rid, dec_r)
        if scene is None:
            pytest.skip("combatSnapshot/predictor KO")
        rows += _collect_pred_rows(dec_r, scene, caster_id, target_id, (tp["col"], tp["row"]))
        if len(rows) >= 3:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    if caster_id is None:
        pytest.skip("drive KO : Sho'syl pas amene a distance [2..3] de la cible")
    if not rows:
        pytest.skip("aucune row rankee pre-cast")
    bad = [r for r in rows if r["oracle"] != r["offline"]]
    assert not bad, f"pred PRE-cast : {len(bad)}/{len(rows)} rows divergentes, ex. {bad[:3]}"

    # --- B : cast (pose Markerlight) puis rows du tour SUIVANT ---
    res = _cast_live(rpc, rid, caster_id, target_id)
    if not _cast_ok(res):
        pytest.skip(f"cast live KO: {str(res)[:150]}")
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    _d, sho2, _t = _drive_sho_in_range(rpc, rid, board)   # re-drive = retour au tour + en portee
    if sho2 is None:
        pytest.skip("retour au tour de Sho'syl KO apres le cast")
    dec2 = rpc("decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True}, 150)
    if not _ok(dec2):
        pytest.skip("decisionView maxRank 99 KO au tour suivant")
    sho2, tgt2 = _find(dec2, CASTER_VIS), _find(dec2, TARGET_VIS)
    if sho2 is None or tgt2 is None:
        pytest.skip("retour au tour de Sho'syl KO apres le cast")
    if MARKERLIGHT not in _effect_types(tgt2):
        pytest.skip("Markerlight absent de la cible au tour suivant (duree ecoulee ?)")
    scene2 = _scene_for(rpc, rid, dec2)
    if scene2 is None:
        pytest.skip("predictor KO au tour suivant")
    tp2 = tgt2.get("pos") or {}
    rows2 = _collect_pred_rows(dec2, scene2, sho2["id"], tgt2["id"], (tp2["col"], tp2["row"]))
    if len(rows2) < 2:
        pytest.skip(f"pas assez de rows rankees post-Markerlight ({len(rows2)})")
    bad2 = [r for r in rows2 if r["oracle"] != r["offline"]]
    assert not bad2, \
        f"pred POST-Markerlight : {len(bad2)}/{len(rows2)} rows divergentes, ex. {bad2[:3]}"
    print(f"[MV71 pred] pre {len(rows)}/{len(rows)} EXACT ; post-Markerlight "
          f"{len(rows2)}/{len(rows2)} EXACT")


def test_mv71_normal_attack_dispatch_sim(live_session, rpc, build_runner):
    """Tranche 3 — dispatch runner : un `AttackUnitMessage` (attaque normale des tours SIMULES)
    d'un porteur MV71 route vers `MV71SniperDroneSquadAttackAbility.execute_behaviour` (drone +
    attaque commandee + Markerlight) — replay-diff vs le cast live 1076 (meme etat pre-cast) :
    meme tuile de drone, degat bit-exact, Markerlight des deux cotes."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.components import PositionComponent, UnitComponent

    rid = build_runner("61005", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec, sho, tgt = _drive_sho_in_range(rpc, rid, board)
    if sho is None or tgt is None:
        pytest.skip("drive KO : Sho'syl pas amene a distance [2..3] de la cible")
    caster_id, target_id = sho["id"], tgt["id"]
    n_drones0 = len(_find_all(dec, DRONE_VIS))

    dec0, ob0, snap0, s0 = _capture(rpc, rid)
    hp0 = _hp(ob0, target_id)
    state = _offline_state(dec0, ob0, snap0, s0, board)
    if state.get_entity(caster_id) is None or state.rng is None or state.effects is None:
        pytest.skip("etat offline incomplet (snapshot/rng)")

    # --- LIVE : cast 1076 (l'attaque normale native de Sho'syl) ---
    res = _cast_live(rpc, rid, caster_id, target_id)
    assert _cast_ok(res), f"cast live KO (interne): {str(res)[:300]}"
    dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    drones2 = _find_all(dec2, DRONE_VIS)
    assert len(drones2) == n_drones0 + 1, f"live : attendu +1 drone, obtenu {len(drones2)}"
    live_dpos = drones2[-1].get("pos") or {}
    hp2 = _hp(ob2, target_id)
    live_dmg = (hp0 - hp2) if (hp0 is not None and hp2 is not None) else None

    # --- OFFLINE : le MESSAGE d'attaque normale (chemin des tours simules) ---
    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(caster_id, target_id))
    off_drone = next((eid for eid, e in state.entities.items()
                      if (uc := e.get_component(UnitComponent)) is not None and uc.alive
                      and uc.visual_id == DRONE_VIS), None)
    assert off_drone is not None, "offline : AttackUnitMessage n'a pas route vers MV71 (pas de drone)"
    opc = state.get_entity(off_drone).get_component(PositionComponent)
    assert (opc.col, opc.row) == (live_dpos.get("col"), live_dpos.get("row")), \
        f"dispatch : tuile offline ({opc.col},{opc.row}) != live ({live_dpos.get('col')},{live_dpos.get('row')})"
    off_total = (runner.damage_handler.last or {}).get("total")
    if live_dmg is not None:
        assert off_total == live_dmg, \
            f"dispatch : degat commande offline {off_total} != live {live_dmg}"
    assert state.effects.has_effect(target_id, effect_type=MARKERLIGHT), \
        "offline : Markerlight absent apres AttackUnitMessage"
    print(f"[MV71 dispatch] AttackUnitMessage -> drone ({opc.col},{opc.row}) degat={off_total} "
          f"(live {live_dmg}) markerlight OK")
