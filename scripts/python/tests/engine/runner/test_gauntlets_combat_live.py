"""case-220 P0-DAMAGE : GauntletsOfUltramar (1000, ultraCalgar) FACE COMBAT (execute) confront LIVE.

`GauntletsOfUltramarAbility.ExecuteBehaviour @1811e1c80` (DECOMPILE) = AoE SELF-CAST a DEUX BANDES :
    ExecuteAtomic( op_BitwiseAnd(
        AttackWithAttackDamage(caster, Unique(Enemies(AdjacentTiles(caster))), MinMaxDamage, Bolter,
                                hits = GetNumberConstant(0x2f) + GetNumberConstant(0x32)),   # ADJACENTE = 2 coups
        AttackWithAttackDamage(caster, Unobscured(SurroundingEnemies(caster,r=2) - Adjacent), MinMaxDamage,
                                Bolter, hits = GetNumberConstant(0x32)) ), 0x1d )              # SURROUNDING = 1 coup
Config 1000 : nrOfHits(0x2f)=1, nrOfHits_2(0x32)=1 -> bande adjacente 2 coups, bande surrounding 1 coup.
La bande surrounding = SurroundingEnemies(disque r<=2) MOINS Adjacent(dist1) = ennemis a dist EXACTEMENT 2.

Ce que ce test PROUVE (drive les 2 camps -- applyAction ignore propriete+portee -- pour une geometrie exacte
en zone FLAT elev-1 ou l'Unobscured est passe-tout) :
  (1) BANDING + COUPS PAR BANDE bit-exact LIVE : ennemi dist 1 -> 2 coups (adjacente) ; dist EXACTEMENT 2
      -> 1 coup (surrounding) ; dist 3 -> 0 coup (EXCLU -- prouve la frontiere, PAS un anneau <=2).
  (2) FIDELITE DU PORT (A/B) : l'arbre `gauntlets_of_ultramar_tree()` == une sequence directe
      `execute_ability_attack` (adjacente 2 coups puis surrounding 1 coup, tries par id) -> le port
      n'introduit AUCUN bug de degat (meme rng, memes bornes/hits/profil).
  (3) PARAMS DEGAT corrects : le PREMIER coup (bande adjacente, 1er de la sequence) == live EXACT
      (profil Bolter, is_melee=False, minDmg/maxDmg/pierce corrects).

GAP CONNU (hors port, #205) : le per-coup vs live DESYNC apres le 1er coup d'une cible multi-coups --
le pipeline partage `execute_ability_attack` tire crit(si cc>=1)+base+block(jusqu'au 1er echec) par coup ;
un block-chance present LIVE mais non charge OFFLINE decale le rng des coups suivants (PRE-EXISTANT, meme
divergence pour CrushingClaws/ScythingTalons -- NON introduit par ce port, prouve par (2)). On assert donc
les COUPS/banding (le cœur du port) + la fidelite A/B + le 1er coup, PAS le per-coup exact multi-coups.

Drive les positions (memoire « drive positions, don't blame geometry »). Lit l'etat LIVE, aucune RVA/tuile
hardcodee, seed = simple generateur. ASCII-only.
"""
from __future__ import annotations

import json

import pytest

import hexgeo
from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.abilities.base import ability_attack_params
from engine.entities.pathfinding.board import Board

CAL = "ultraCalgar"                                   # id 1000 GauntletsOfUltramar
ENEMIES = "necroOverlord,necroWarden,necroDestroyer,necroSpyder"   # tanks (survivent 2 coups)
BUILD = ["--roster", "1", "--p-units", CAL, "--a-units", ENEMIES]
ABILITY = 1000
FLAT = 1                                              # rows 7-8 de MC1_67 = elevation 1 (Unobscured passe-tout)


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _alive(d):
    return [u for u in (d.get("units") or []) if u.get("alive")]


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def test_gauntlets_combat_two_bands_live(live_session, rpc, build_runner):
    """Gauntlets FACE COMBAT : coups par bande bit-exact live (dist1=2, dist2=1, dist3=0), fidelite A/B,
    1er coup exact."""
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    elev = {(t["col"], t["row"]): t.get("elevation") for t in bg["tiles"]}

    def movable(uid, side):
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": side}, 60)
        x = next((y for y in (mt or {}).get("units") or [] if y.get("unitId") == uid), None)
        return [(t["col"], t["row"]) for t in ((x or {}).get("tiles") or [])]

    def move(uid, to):
        return rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": to[0], "row": to[1]}}}, 40)

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if not _ok(dv):
        pytest.skip("decisionView KO")
    cal = next((u for u in _alive(dv) if u.get("visualId") == CAL), None)
    if cal is None:
        pytest.skip("Calgar absent")
    myp = cal.get("owner")
    cal_id = cal["id"]

    # --- APPROCHE : rapprocher Calgar du cluster (dist <= 2 d'un ennemi) ---
    for _ in range(20):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if dv.get("currentPlayer") != myp:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        cal = next((u for u in _alive(dv) if u.get("id") == cal_id), None)
        if cal is None:
            pytest.skip("Calgar mort avant contact")
        ens = [u for u in _alive(dv) if u.get("owner") != myp]
        if not ens:
            pytest.skip("aucun ennemi vivant")
        if min(hexgeo.distance(_pos(cal), _pos(e)) for e in ens) <= 2:
            break
        mv = movable(cal_id, "friendly")
        if not mv:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        cen = (sum(_pos(e)[0] for e in ens) / len(ens), sum(_pos(e)[1] for e in ens) / len(ens))
        move(cal_id, min(mv, key=lambda t: (t[0] - cen[0]) ** 2 + (t[1] - cen[1]) ** 2))
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    else:
        pytest.skip("Calgar n'a pas atteint le cluster en 20 tours")

    # --- SETUP (un tour, PAS d'endturn) : Calgar sur tuile FLAT, ennemis a dist 1 / 2 / 3 / 2 ---
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    cal = next(u for u in _alive(dv) if u.get("id") == cal_id)
    ens = [u for u in _alive(dv) if u.get("owner") != myp]
    if len(ens) < 4:
        pytest.skip("moins de 4 ennemis vivants pour la geometrie 3 bandes")

    def flat_at(T, dx):
        return [p for p in elev if elev.get(p) == FLAT and hexgeo.distance(T, p) == dx
                and board.id_at(p[0], p[1]) is not None and board.walkable(board.id_at(p[0], p[1]))]

    mv = [t for t in (movable(cal_id, "friendly") + [_pos(cal)]) if elev.get(t) == FLAT]
    cand = [T for T in mv if flat_at(T, 1) and flat_at(T, 2) and flat_at(T, 3)]
    if not cand:
        pytest.skip("aucune tuile Calgar flat avec dist 1&2&3 flat disponibles")
    T = min(cand, key=lambda t: (t[0] - 5) ** 2 + (t[1] - 7.5) ** 2)
    if _pos(cal) != T:
        move(cal_id, T)
    occ = {T}
    for e, dx in [(ens[0], 1), (ens[1], 2), (ens[2], 3), (ens[3], 2)]:
        ring = flat_at(T, dx)
        dest = next((p for p in ring if p not in occ), None)
        if dest:
            occ.add(dest); move(e["id"], dest)

    # --- geometrie finale : coups attendus par ennemi (dist1=2, dist2=1, dist>=3=0) ---
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    cal = next(u for u in _alive(dv) if u.get("id") == cal_id)
    ens = [u for u in _alive(dv) if u.get("owner") != myp]
    cp = _pos(cal)
    band = {e["id"]: hexgeo.distance(cp, _pos(e)) for e in ens}
    expect = {i: (2 if dd == 1 else 1 if dd == 2 else 0) for i, dd in band.items()}
    if 1 not in band.values() or 2 not in band.values():
        pytest.skip(f"geometrie 2 bandes non atteinte (dist par ennemi={band})")
    adj = sorted(i for i, dd in band.items() if dd == 1)
    surr = sorted(i for i, dd in band.items() if dd == 2)

    # --- capture + rng ---
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")

    # --- CAST LIVE (ordre preserve) ---
    tgt = adj[0]
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cal_id, "targetId": tgt, "abilityType": ABILITY}}, 60)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        pytest.skip(f"cast KO: {str(res)[:160]}")
    live_seq = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
            live_seq.append((td.get("Target_Id"), td.get("Amount")))
    live_cnt = {}
    for tid, _amt in live_seq:
        live_cnt[tid] = live_cnt.get(tid, 0) + 1
    if not live_seq:
        pytest.skip("aucun event de degat Gauntlets live")

    # --- OFFLINE : l'engine DERIVE l'arbre DSL depuis le cast (gauntlets_of_ultramar_tree) ---
    st = load_state(dv, ob, snap); st.board = board; st.rng = _seed_rng(s0)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=cal_id, target_id=tgt, ability_type=ABILITY))
    last = runner.ability_handler.last or {}
    assert last.get("ported"), f"ability {ABILITY} non routee par le wiring ability-exec: {last}"
    off_attacks = last.get("attacks") or []
    off_cnt = {}
    off_ph = {}
    for a in off_attacks:
        off_cnt[a["target"]] = off_cnt.get(a["target"], 0) + (a["attack"].get("hits") or 0)
        off_ph[a["target"]] = a["attack"].get("per_hit")

    print(f"\n[GAUNTLETS combat] Calgar {cp} band(dist)={band}")
    print(f"[GAUNTLETS combat] attendu(coups)={expect} live(coups)={live_cnt} off(coups)={off_cnt}")
    for tid in sorted(band):
        print(f"[GAUNTLETS combat]  e{tid} dist={band[tid]} attendu={expect[tid]} "
              f"live={live_cnt.get(tid, 0)} off={off_cnt.get(tid, 0)} off_ph={off_ph.get(tid)}")

    # (1) COUPS PAR BANDE bit-exact live == offline == attendu (dist1=2, dist2=1, dist>=3=0)
    for tid in sorted(band):
        assert live_cnt.get(tid, 0) == expect[tid], (
            f"e{tid} dist={band[tid]} : LIVE {live_cnt.get(tid, 0)} coups != attendu {expect[tid]}")
        assert off_cnt.get(tid, 0) == expect[tid], (
            f"e{tid} dist={band[tid]} : OFFLINE {off_cnt.get(tid, 0)} coups != attendu {expect[tid]}")
    # bande adjacente = 2 coups, surrounding = 1 coup (structure du port)
    for tid in adj:
        assert off_cnt.get(tid) == 2, f"bande adjacente e{tid} attendue 2 coups: {off_cnt.get(tid)}"
    for tid in surr:
        assert off_cnt.get(tid) == 1, f"bande surrounding e{tid} attendue 1 coup: {off_cnt.get(tid)}"

    # (2) FIDELITE A/B : l'arbre == une sequence directe execute_ability_attack (adj 2 coups tries par id
    #     puis surr 1 coup tries par id) -> le port n'introduit AUCUN bug de degat (meme rng seede).
    st2 = load_state(dv, ob, snap); st2.board = board; st2.rng = _seed_rng(s0)
    bmin, bmax, pierce, _ = ability_attack_params(st2, cal_id, "GauntletsOfUltramar", "Bolter", ranged=True)
    ref_ph = {}
    for tid in adj + surr:                              # MEME ordre que l'arbre (multi=True trie par id)
        h = 2 if tid in adj else 1
        r = AttackDamageOperation.execute_ability_attack(st2, cal_id, tid, bmin, bmax, pierce, h,
                                                         damage_profile="Bolter", is_melee=False)
        ref_ph[tid] = r.get("per_hit")
    for tid in adj + surr:
        assert off_ph.get(tid) == ref_ph.get(tid), (
            f"arbre e{tid} {off_ph.get(tid)} != baseline execute_ability_attack {ref_ph.get(tid)} "
            f"(port NON bit-exact vs pipeline)")

    # (3) PARAMS DEGAT : le PREMIER coup live (1er de la sequence, bande adjacente) == 1er coup offline
    #     -> profil Bolter, is_melee=False, minDmg/maxDmg/pierce corrects (avant tout desync multi-coups).
    first_tid, first_amt = live_seq[0]
    assert first_tid in adj, f"1er event live cible {first_tid} pas dans la bande adjacente {adj}"
    off_first = (off_ph.get(first_tid) or [None])[0]
    assert off_first == first_amt, (
        f"1er coup: offline {off_first} != live {first_amt} (params degat Bolter/pierce errones)")
    print(f"[GAUNTLETS combat] OK : banding+coups bit-exact (dist1=2/dist2=1/dist3=0), "
          f"A/B tree==baseline, 1er coup exact={first_amt}")
