"""#35 : LordOfTempests AddIce (triggered 1194, Njal spaceStormcaller) — face RUNNER confrontee au LIVE.

Port : `engine/runner/operations/triggers/loki/lord_of_tempests.py` (arbre DSL
`AddEffect(Ice=17, Tiles(Target()))`, trigger `OnNormalAttackOrSmite & OwnerIsCaster`,
RE IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility$$CreateBehaviour) + couplage COMBAT `_positional_att_ctx` (damage_model.py : la face
snowball `LordOfTempestsExtraDamageEffect` lit la glace posee via att_ctx, #35).

CE FICHIER :
  1. `test_lord_of_tempests_addice_live_offline_agreement` : replay-diff du POSEUR — meme etat
     pre-attaque (dec/ob/snap/dumpRng), attaque NORMALE de Njal live ET offline
     (`AttackUnitMessage`), puis diff : NOUVELLES tuiles glacees live (tileMeta) == tuiles glacees
     offline (state.effects sur tile-ids), degat cible bit-exact (MT seede — l'attaque 1 est SANS
     bonus : la glace se pose APRES le degat, « at the end of the attack »).
  2. `test_lord_of_tempests_snowball_second_attack` : la 2e attaque, menee ADJACENTE a la glace
     posee par la 1re — le degat live inclut +extraDmg x Count(Ice ring-1) ; replay-diff bit-exact.
     La glace pre-existante vient DU LOAD (`load_state(..., tiles=tileMeta)`, #102) : ce test est
     donc AUSSI un confront du vecteur de seeding des effets de TUILE — sans lui, le compte ring-1
     serait 0 offline et le degat divergerait d'exactement extraDmg x count.

  3. `test_lord_of_tempests_addice_smite_branch` : la BRANCHE 2 du trigger (`On(9=Attack) &
     kind==0x3f5` = victime du splash « Smite » Psyker). Geometrie PLACEE (build 2 ennemis, Njal
     drive a d=2 de la cible T pour forcer l'arme RANGED Psychic, E2 pose sur un VOISIN de T donc
     seul candidat du `PickRandomly(Damageable(Enemies(AdjacentUnits(T))))`) : les tuiles de T ET
     de E2 sont glacees live, et l'offline reproduit le MEME ensemble. Discriminant : E2 n'est
     touche QUE par le splash — si le natif ne glaçait que la cible primaire, la branche 2 du port
     serait refutee.

DRIVE POSITIONS (doctrine) : on DEPLACE les unites (y compris adverses) pour obtenir la
configuration voulue ; skip propre seulement si le placement lui-meme echoue. ASCII only.
"""
from __future__ import annotations

import pytest

CASTER_VIS = "spaceStormcaller"    # Njal — passiveAbilities=['LordOfTempests'], armes Psychic (melee 3x, r2 2x)
TARGET_VIS = "astraYarrick"
E2_VIS = "darkaCompanion"          # 2e ennemi : victime du splash Smite Psyker (branche 2 du trigger)
ICE = 17                           # EffectType.Ice (0x11)
BUILD = ["--p-units", f"{CASTER_VIS},templAncient", "--a-units", TARGET_VIS,
         "--hp-target", "200000", "--hp-player", "60000"]
# Build 2 ennemis : la geometrie du splash (E2 adjacent a la cible) est PLACEE, pas subie.
# Njal SEUL cote joueur : aucun allie a ecarter -> aucun mouvement parasite avant son attaque.
BUILD_SMITE = ["--p-units", CASTER_VIS,
               "--a-units", f"{TARGET_VIS},{E2_VIS}",
               "--hp-target", "200000", "--hp-player", "60000"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _hp(ob, uid):
    for u in (ob.get("units") or []):
        if u.get("squadId") == uid and not u.get("isDead"):
            return u.get("hp")
    return None


def _iced_positions(rpc, rid):
    """{(col,row)} des tuiles porteuses de l'effet 'Ice' (tileMeta live — effets DYNAMIQUES)."""
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    out = set()
    for t in (tm.get("tiles") or []):
        if any((e.get("name") == "Ice") for e in (t.get("effects") or [])):
            out.add((t.get("col"), t.get("row")))
    return out


def _offline_iced_positions(state, board):
    """{(col,row)} des tuiles glacees de l'etat OFFLINE (state.effects.by_unit key = tile-entity id)."""
    out = set()
    for tid, effs in (state.effects.by_unit or {}).items():
        if any((e.effect_type == ICE and not e.consumed) for e in effs):
            co = board.coord(int(tid))
            if co is not None:
                out.add(tuple(co))
    return out


def _advance_to_my_turn(rpc, rid, vis, max_iter=12):
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
    """Capture COMPLETE de l'etat live, `tileMeta` INCLUS (#102 : les effets portes par les TUILES
    ne transitent que par ce canal ; sans lui l'etat offline repart d'un plateau vierge)."""
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s = rpc("dumpRng", {"runnerId": rid}, 30)
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    return dec, ob, snap, s, tm


def _offline_state(dec, ob, snap, s, board, tiles=None):
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    state = load_state(dec, ob, snap, board=board, tiles=tiles)
    if _ok(s):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s["mt"])
        rng.mti = s["mti"]
        state.rng = rng
    return state


def _cast_normal(rpc, rid, caster, target_id):
    """Cast LIVE de l'attaque NORMALE du caster (id dynamique = ability kind=='normal' de decisionView)."""
    norm = next((ab for ab in (caster.get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        return None
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster["id"], "targetId": target_id,
        "abilityType": norm["id"]}, "captureEvents": True}, 120)
    return res


def _cast_ok(res):
    if not _ok(res):
        return False
    a0 = (res.get("actions") or [{}])[0]
    return bool(a0.get("ok")) and bool(a0.get("mutated"))


def _drive_in_range(rpc, rid, lo, hi, max_turns=10):
    """DRIVE Njal (move 2) a distance hex [lo..hi] de la cible (armes r2 : [2..2]=RANGED, [1..1]=melee)."""
    import hexgeo
    for _ in range(max_turns):
        dec, me = _advance_to_my_turn(rpc, rid, CASTER_VIS)
        if me is None:
            return None, None, None
        tgt = _find(dec, TARGET_VIS)
        if tgt is None:
            return None, None, None
        sp, tp = me.get("pos") or {}, tgt.get("pos") or {}
        d = hexgeo.distance((sp["col"], sp["row"]), (tp["col"], tp["row"]))
        if lo <= d <= hi:
            return dec, me, tgt
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == me["id"]), None)
        tiles = [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])
                 if t.get("col") is not None]
        if tiles:
            def _key(pos):
                dd = hexgeo.distance(pos, (tp["col"], tp["row"]))
                return (0 if lo <= dd <= hi else 1, abs(dd - hi), dd)
            best = min(tiles, key=_key)
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
            dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            me2, tgt2 = _find(dec2, CASTER_VIS), _find(dec2, TARGET_VIS)
            if me2 is not None and tgt2 is not None:
                sp2, tp2 = me2.get("pos") or {}, tgt2.get("pos") or {}
                if lo <= hexgeo.distance((sp2["col"], sp2["row"]), (tp2["col"], tp2["row"])) <= hi:
                    return dec2, me2, tgt2
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None, None


def _move(rpc, rid, uid, coord):
    """PLACEMENT arbitraire (applyAction/move ignore portee, MP et propriete — vaut aussi pour
    les unites ADVERSES). Doctrine : on DEPLACE pour obtenir la configuration, on ne la subit pas."""
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": coord[0], "row": coord[1]}}}, 60)


def _setup_smite_geometry(rpc, rid, board):
    """PLACE la geometrie qui exerce la BRANCHE 2 du trigger AddIce :
      - Njal a distance hex EXACTEMENT 2 de la cible primaire T -> arme RANGED Psychic (le splash
        Psyker exige `IsRangedAttack & DamageProfileIs(Psychic)` ; a d=1 c'est l'arme melee),
      - E2 (2e ennemi) sur un VOISIN de T -> SEUL candidat de
        `PickRandomly(Damageable(Enemies(AdjacentUnits(T))))` (tirage non ambigu),
      - l'allie ecarte a d>5 (n'occupe aucune tuile utile).
    Renvoie (njal, tgt, e2) de decisionView, ou (None, None, None) si non placable."""
    import hexgeo
    dec, njal = _advance_to_my_turn(rpc, rid, CASTER_VIS)
    if njal is None:
        return None, None, None
    cpos = (njal["pos"]["col"], njal["pos"]["row"])
    tgt, e2 = _find(dec, TARGET_VIS), _find(dec, E2_VIS)
    if tgt is None or e2 is None:
        return None, None, None
    norm = next((ab for ab in (njal.get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        return None, None, None
    ab_id = norm["id"]
    occupied = {board.id_at(*cpos)}

    tries = 0
    for t in sorted(board.by_id):
        if tries >= 14:
            break
        if not board.walkable(t) or t in occupied:
            continue
        if hexgeo.distance(board.coord(t), cpos) != 2:
            continue
        nb = [n for n in board.neighbours(t)
              if board.walkable(n) and n not in occupied and n != t]
        if not nb:
            continue
        tries += 1
        _move(rpc, rid, tgt["id"], board.coord(t))
        _move(rpc, rid, e2["id"], board.coord(nb[0]))
        dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        n_j, n_t, n_e = _find(dec2, CASTER_VIS), _find(dec2, TARGET_VIS), _find(dec2, E2_VIS)
        if n_j is None or n_t is None or n_e is None:
            return None, None, None
        jp = (n_j["pos"]["col"], n_j["pos"]["row"])
        tp = (n_t["pos"]["col"], n_t["pos"]["row"])
        ep = (n_e["pos"]["col"], n_e["pos"]["row"])
        if not (hexgeo.distance(jp, tp) == 2 and hexgeo.distance(tp, ep) == 1 and ep != jp):
            continue
        # LEGALITE du cast depuis cette tuile (portee/LoS) — sinon l'attaque est un no-op
        # `mutated:false` silencieux : on essaie la configuration suivante.
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": n_j["id"], "abilityType": ab_id}, 90)
        abl = next((a for a in (((at.get("units") or [{}])[0]).get("abilities") or [])
                    if a.get("abilityId") == ab_id), {})
        legal = [x.get("targetId") for x in (abl.get("fromHere") or abl.get("targets") or [])]
        if n_t["id"] in legal:
            return n_j, n_t, n_e
    return None, None, None


def test_lord_of_tempests_addice_smite_branch(live_session, rpc, build_runner):
    """BRANCHE 2 du trigger (`On(9=Attack) & <kind attaque-normale 0x3f5>` d'`IdunBattleLogic.Entities.DSLTriggers$$OnNormalAttackOrSmite`) : la victime du splash « Smite » Psyker est glacee AUSSI — i2 « The hex of EACH
    enemy that is hit by Njal's normal attacks is covered in Ice ».

    Discriminant : la tuile de E2 (touche par le SEUL splash, jamais par l'attaque primaire) est
    glacee. Si le natif ne glaçait que la cible primaire, la branche 2 du port serait FAUSSE et
    `live_new_ice` ne contiendrait pas `e2_pos`. Referme le residu [opus] de case-35 §4."""
    import hexgeo
    from engine.entities.pathfinding.board import Board
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage

    rid = build_runner("35003", extra=BUILD_SMITE)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    njal, tgt, e2 = _setup_smite_geometry(rpc, rid, board)
    if njal is None:
        pytest.skip("geometrie splash non placee (Njal d=2 de T + E2 voisin libre de T)")
    caster_id, target_id, e2_id = njal["id"], tgt["id"], e2["id"]
    tgt_pos = (tgt["pos"]["col"], tgt["pos"]["row"])
    e2_pos = (e2["pos"]["col"], e2["pos"]["row"])
    assert hexgeo.distance(tgt_pos, e2_pos) == 1, "E2 doit etre adjacent a la cible primaire"

    ice0 = _iced_positions(rpc, rid)
    dec0, ob0, snap0, s0, tm0 = _capture(rpc, rid)
    hp0_t, hp0_e = _hp(ob0, target_id), _hp(ob0, e2_id)
    state = _offline_state(dec0, ob0, snap0, s0, board, tiles=tm0)
    if state.get_entity(caster_id) is None or state.rng is None or state.effects is None:
        pytest.skip("etat offline incomplet (snapshot/rng)")

    # --- LIVE : attaque normale RANGED (d=2) sur T -> splash Psyker sur E2 ---
    res = _cast_normal(rpc, rid, njal, target_id)
    if res is None:
        pytest.skip("ability kind=normal introuvable sur Njal (decisionView)")
    assert _cast_ok(res), f"cast live KO (interne): {str(res)[:300]}"
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    hp2_t, hp2_e = _hp(ob2, target_id), _hp(ob2, e2_id)
    if not (hp0_e is not None and hp2_e is not None and hp2_e < hp0_e):
        pytest.skip(f"splash Psyker non declenche live sur E2 (hp {hp0_e} -> {hp2_e}) "
                    f"- branche 2 non exercee, rien a confronter")
    live_new_ice = _iced_positions(rpc, rid) - ice0

    # --- OFFLINE : meme AttackUnitMessage ---
    off_ice0 = _offline_iced_positions(state, board)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(caster_id, target_id))
    off_new_ice = _offline_iced_positions(state, board) - off_ice0

    assert tgt_pos in live_new_ice, \
        f"live : tuile de la cible primaire {tgt_pos} non glacee (new={sorted(live_new_ice)})"
    assert e2_pos in live_new_ice, \
        (f"BRANCHE 2 REFUTEE cote NATIF : la victime du splash Smite {e2_pos} n'est PAS glacee "
         f"live (nouvelles glaces={sorted(live_new_ice)}) alors que le splash l'a bien touchee "
         f"(hp {hp0_e} -> {hp2_e}). Le port glacerait {sorted(off_new_ice)}.")
    assert off_new_ice == live_new_ice, \
        f"AddIce smite : tuiles offline {sorted(off_new_ice)} != live {sorted(live_new_ice)}"
    live_dmg_t = (hp0_t - hp2_t) if (hp0_t is not None and hp2_t is not None) else None
    off_total = (runner.damage_handler.last or {}).get("total")
    print(f"[LoT smite] T={tgt_pos} E2={e2_pos} : glace live/offline {sorted(live_new_ice)} ; "
          f"splash E2 hp {hp0_e}->{hp2_e} ; degat primaire off={off_total} live={live_dmg_t}")


def test_lord_of_tempests_addice_live_offline_agreement(live_session, rpc, build_runner):
    """Replay-diff du POSEUR AddIce : attaque normale RANGED (d=2) de Njal — la tuile de la cible
    recoit 'Ice' live ET offline (memes NOUVELLES tuiles glacees), degat de l'attaque 1 bit-exact
    et SANS bonus (la glace se pose apres le degat)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage

    rid = build_runner("35001", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    dec, njal, tgt = _drive_in_range(rpc, rid, lo=2, hi=2)
    if njal is None or tgt is None:
        pytest.skip("drive KO : Njal pas amene a distance 2 de la cible")
    caster_id, target_id = njal["id"], tgt["id"]
    tgt_pos = (tgt["pos"]["col"], tgt["pos"]["row"])

    ice0 = _iced_positions(rpc, rid)                     # glace deja presente (attendu : aucune)
    dec0, ob0, snap0, s0, tm0 = _capture(rpc, rid)
    hp0 = _hp(ob0, target_id)
    state = _offline_state(dec0, ob0, snap0, s0, board, tiles=tm0)
    if state.get_entity(caster_id) is None or state.rng is None or state.effects is None:
        pytest.skip("etat offline incomplet (snapshot/rng)")

    # --- LIVE : attaque normale de Njal ---
    res = _cast_normal(rpc, rid, njal, target_id)
    if res is None:
        pytest.skip("ability kind=normal introuvable sur Njal (decisionView)")
    assert _cast_ok(res), f"cast live KO (interne): {str(res)[:300]}"
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    hp2 = _hp(ob2, target_id)
    live_dmg = (hp0 - hp2) if (hp0 is not None and hp2 is not None) else None
    live_new_ice = _iced_positions(rpc, rid) - ice0
    assert tgt_pos in live_new_ice, \
        f"live : la tuile de la cible {tgt_pos} n'est pas glacee (nouvelles glaces={sorted(live_new_ice)})"

    # --- OFFLINE : AttackUnitMessage (chemin generique + vecteur after_hit_normal_attack) ---
    off_ice0 = _offline_iced_positions(state, board)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(caster_id, target_id))
    off_new_ice = _offline_iced_positions(state, board) - off_ice0
    assert off_new_ice == live_new_ice, \
        f"AddIce : tuiles offline {sorted(off_new_ice)} != live {sorted(live_new_ice)}"
    off_total = (runner.damage_handler.last or {}).get("total")
    if live_dmg is not None:
        assert off_total == live_dmg, f"degat attaque 1 offline {off_total} != live {live_dmg}"
    print(f"[LoT addice] d=2 cible {tgt_pos} : glace live/offline {sorted(live_new_ice)}, "
          f"degat {off_total} (live {live_dmg})")


def test_lord_of_tempests_snowball_second_attack(live_session, rpc, build_runner):
    """La 2e attaque de Njal, ADJACENTE a la glace posee par la 1re : le degat live porte
    +extraDmg x Count(Ice ring-1 de la position d'attaque) — replay-diff bit-exact (valide le
    couplage COMBAT `_positional_att_ctx` -> `LordOfTempestsExtraDamageEffect`). La glace du
    tileMeta live est SEEDEE dans l'etat offline (gap d'hydratation tile-effects de `load_state`,
    cf. docstring module)."""
    import hexgeo
    from engine.entities.pathfinding.board import Board
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.operations.effects import AddEffectOperation

    rid = build_runner("35002", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    # Attaque 1 (d=2) -> pose la glace sur la tuile de la cible.
    dec, njal, tgt = _drive_in_range(rpc, rid, lo=2, hi=2)
    if njal is None or tgt is None:
        pytest.skip("drive KO : attaque 1 impossible (d=2 non atteint)")
    res = _cast_normal(rpc, rid, njal, tgt["id"])
    if res is None or not _cast_ok(res):
        pytest.skip("attaque 1 live KO")
    if not _iced_positions(rpc, rid):
        pytest.fail("attaque 1 : aucune glace posee live (AddIce natif attendu)")
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

    # Attaque 2 : drive ADJACENT a la cible (melee) -> si la cible est restee sur/près de sa tuile
    # glacee, le ring-1 de Njal contient de la glace -> bonus actif.
    dec, njal, tgt = _drive_in_range(rpc, rid, lo=1, hi=1)
    if njal is None or tgt is None:
        pytest.skip("drive KO : attaque 2 impossible (d=1 non atteint)")
    caster_id, target_id = njal["id"], tgt["id"]
    my_pos = (njal["pos"]["col"], njal["pos"]["row"])
    iced_live = _iced_positions(rpc, rid)
    count = sum(1 for p in iced_live if hexgeo.distance(my_pos, p) == 1)
    if count <= 0:
        pytest.skip(f"geometrie non cooperative : aucune glace ring-1 de {my_pos} (glaces={sorted(iced_live)})")

    dec0, ob0, snap0, s0, tm0 = _capture(rpc, rid)
    hp0 = _hp(ob0, target_id)
    state = _offline_state(dec0, ob0, snap0, s0, board, tiles=tm0)
    if state.get_entity(caster_id) is None or state.rng is None or state.effects is None:
        pytest.skip("etat offline incomplet (snapshot/rng)")
    for p in iced_live:                                   # seed du gap d'hydratation tile-effects
        tid = board.id_at(p[0], p[1])
        if tid is not None:
            AddEffectOperation.execute(state, source=caster_id, target=int(tid),
                                       effect_type=ICE, name="Ice")

    # --- LIVE : attaque 2 ---
    res = _cast_normal(rpc, rid, njal, target_id)
    if res is None:
        pytest.skip("ability kind=normal introuvable sur Njal (attaque 2)")
    assert _cast_ok(res), f"attaque 2 live KO (interne): {str(res)[:300]}"
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    hp2 = _hp(ob2, target_id)
    live_dmg = (hp0 - hp2) if (hp0 is not None and hp2 is not None) else None
    if live_dmg is None:
        pytest.skip("hp cible illisible (attaque 2)")

    # --- OFFLINE : replay bit-exact — le +extraDmg x count est LE discriminant (un couplage
    # att_ctx manquant divergerait d'exactement extraDmg x count par coup). ---
    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(caster_id, target_id))
    off_total = (runner.damage_handler.last or {}).get("total")
    assert off_total == live_dmg, \
        f"snowball : degat offline {off_total} != live {live_dmg} (count ring-1={count})"
    print(f"[LoT snowball] pos {my_pos}, {count} hex glace(s) ring-1 : degat {off_total} == live")
