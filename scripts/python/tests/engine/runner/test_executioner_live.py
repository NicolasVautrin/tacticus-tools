"""Executioner (1066, eldarFarseer « Eldryon », Aeldari) -- face COMBAT (execute) portee, confrontee au LIVE.

`IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$ExecuteBehaviour` (DECOMPILE, mirror 1:1 -- namespace natif
`Abilities.Active.Loki.ExecutionerAbility`) =
    op_and( op_and(
        SetCache(cacheA = Cache(Damageable(Enemies(@0x160, AdjacentUnits(@0x190, 1, 3))))),          # prime pool
        AttackWithAttackDamage(actor@0x160, target@0x178, MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                               Nullable(0xd = Psychic), hits = RoundsStarted) ),                       # MAIN
        If( IsDead(target@0x178),
            AttackWithAttackDamage(actor@0x160, Cache(PickRandomly(Alive(cacheA), 1)), MEME MinMax,
                                   Nullable(0xd), hits = RoundsStarted) ) )                             # SECONDARY
    & Inform(0xc1, ...)                                                                                # AI/UI hint (fold)

i2 : « takes 582-2183 Psychic Damage FOR EACH ROUND THAT HAS STARTED. If the target is eliminated, an
adjacent enemy also takes 582-2183 for each round started. » Attaque RANGED Psychic (pierce 100, NoBlocking),
`hits = RoundsStarted` (`IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$GetHits` = stat 12 `turnsStarted` du CASTER, plancher max(1,.)).
`native_factory="attack"` (IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage, XREF ExecuteBehaviour ; 2 tirages/coup a cc=0, rngcrit-1202).

Ce que ces tests PROUVENT :
  (a) CAST LIVE bit-exact : la MAIN frappe la cible `hits = RoundsStarted` fois, per-coup == le port offline
      (arbre DSL), sous le meme rng seede -> la feuille appelle le pipeline d'attaque fidele.
  (c) FIDELITE A/B : arbre MAIN == sequence directe `execute_ability_attack(hits, "Psychic", "attack")` ->
      le port n'introduit AUCUN bug de degat.
  (d) NATIVE_FACTORY : la MAIN live == modele "attack" (2 tirages/coup), != modele "ability" (1 tirage/coup)
      -> `native_factory="attack"` est le bon choix (discriminant rngcrit-1202), sur 2 seeds.
  (b) If(IsDead) DISCRIMINANT (offline, drive positions/hp) : cible TUEE -> 2e attaque sur 1 ennemi VIVANT
      random adjacent a la CIBLE (hits = RoundsStarted) ; cible SURVIT -> AUCUNE 2e attaque ; cap-1 sur 2
      adjacents ; ancrage CIBLE (pas caster).

hits = RoundsStarted (`turnsStarted` du caster) : drive de plusieurs tours pour l'amener > 1 (multi-coups =
exerce le discriminant native_factory). cc=0 requis pour le bit-exact (skip sinon). Drive les positions
(memoire « drive positions »). Lit l'etat LIVE, aucune RVA/tuile hardcodee. ASCII only. State-file UNIQUE par
agent (chemin absolu). Skip propre si pas de session / geometrie / legalite infaisable.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import hexgeo

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                      # racine repo
AGENT = "af4e10ea29cc3cf81"                                  # id agent -> state-file unique (coexistence runners)
CASTER_VIS = "eldarFarseer"
ABILITY = 1066
A_UNITS = "necroWarden,necroDestroyer,necroOverlord"


# ------------------------------------------------------------------ helpers

def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _build(rpc_unused, seed: str):
    """Build un runner ISOLE (state-file unique agent+tag, chemin absolu). Renvoie (rid, state_file)."""
    tag = uuid.uuid4().hex[:8]
    state_file = ROOT / "logs" / "runners" / f"exec-{AGENT}-{seed}-{tag}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(state_file),
         "--board", "MC1_67", "--p-units", CASTER_VIS, "--a-units", A_UNITS, "--hp-target", "300000",
         # #933 -- LE REGIME « cc = 0 » SE CONSTRUIT. Le volet bit-exact ci-dessous SKIPPE quand le
         # caster a de la chance de crit ; depuis la bascule #419-r5/-r6 (items BiS par defaut),
         # `eldarFarseer` en porte 35 (MESURE), donc le skip etait SYSTEMATIQUE : 1 passed /
         # 2 skipped, rc 0, et le coeur du fichier n'etait plus jamais evalue. Le fichier n'etant
         # pas INTEGRALEMENT skippe, la garde #455 ne le voyait pas non plus.
         "--crit", "0,0"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        return None, state_file
    return json.loads(state_file.read_text())["runnerId"], state_file


def _cleanup(rpc, rid, state_file):
    if rid:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass
    try:
        if state_file is not None:
            state_file.unlink()
    except Exception:
        pass


def _mk_rng(s):
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _legal_fromhere(rpc, rid, cid):
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
    a = next((x for x in ((at.get("units") or [{}])[0].get("abilities") or [])
              if x.get("abilityId") == ABILITY), {})
    return set(x.get("targetId") for x in (a.get("fromHere") or []))


def _mv(rpc, rid, uid, c):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)


def _drive_and_position(rpc, rid, board, n_turns: int):
    """Avance jusqu'a `n_turns` tours du farseer (turnsStarted++), isole la cible sur une tuile ouverte,
    parque les autres ennemis LOIN, place le farseer ADJACENT et verifie la LEGALITE du cast. Renvoie
    (dv, cid, tid) ou (None,..) si infaisable (skip)."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    me = next((u for u in (dv.get("units") or []) if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
    if me is None:
        return None, None, None
    myp = me.get("owner"); cid = me["id"]
    tm = 0
    for _ in range(24):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        if dv.get("currentPlayer") == myp:
            tm += 1
            if tm >= n_turns:
                break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    else:
        return None, None, None
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    me = next((u for u in units if u.get("id") == cid), None)
    ens = [u for u in units if u.get("owner") != myp]
    if me is None or len(ens) < 1:
        return None, None, None
    T = next((t for t in sorted(board.by_id)
              if board.walkable(t) and sum(1 for n in board.neighbours(t) if board.walkable(n)) >= 3), None)
    if T is None:
        return None, None, None
    tc = board.coord(T)
    nb = [board.coord(n) for n in board.neighbours(T) if board.walkable(n)]
    tgt = ens[0]
    far = [board.coord(t) for t in sorted(board.by_id)
           if board.walkable(t) and hexgeo.distance(board.coord(t), tc) > 6]
    for i, e in enumerate(ens[1:]):
        if i < len(far):
            _mv(rpc, rid, e["id"], far[i])
    _mv(rpc, rid, tgt["id"], tc)
    # place le farseer sur un voisin d'ou la cible est LEGALE (parcourt les voisins)
    for c in nb:
        _mv(rpc, rid, cid, c)
        if tgt["id"] in _legal_fromhere(rpc, rid, cid):
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
            return dv, cid, tgt["id"]
    return None, None, None


# ------------------------------------------------------------------ (a)+(c)+(d) LIVE cast + A/B + native_factory

@pytest.mark.parametrize("seed", ["777", "31337"])
def test_executioner_live_main_bitexact_and_native_factory(live_session, rpc, seed):
    """(a) MAIN live per-coup == arbre DSL offline (bit-exact) ; (c) arbre == sequence directe
    `execute_ability_attack` ; (d) native_factory : live == "attack" (2 tirages/coup) != "ability" (1/coup).
    hits = RoundsStarted (drive plusieurs tours -> turnsStarted > 1 -> multi-coups discriminants)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.components import StatsComponent
    from engine.entities.stats import StatType
    from engine.runner.abilities.aeldari import ExecutionerAbility, _rounds_started
    from engine.runner.abilities.base import ability_attack_params
    from engine.runner.operations.damage import AttackDamageOperation

    rid, state_file = _build(rpc, seed)
    if rid is None:
        pytest.skip("build runner KO (rl_duel)")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        dv, cid, tid = _drive_and_position(rpc, rid, board, n_turns=3)
        if cid is None:
            pytest.skip("drive/position/legalite infaisable")

        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if snap is None or not _ok(s0):
            pytest.skip("combatSnapshot/dumpRng indispo")

        st = load_state(dv, ob, snap, board=board)
        off_hits = _rounds_started(st, cid)
        csc = st.get_entity(cid).get_component(StatsComponent)
        cc = int(getattr(csc.ctx, "crit_chance", 0) or 0)
        ts = st.get_entity(cid).get_component(StatsComponent).ctx.stats.get_stat(int(StatType.TURNS_STARTED), 0)
        # #933 -- PREMISSE DE MONTAGE, plus un skip. Un skip sur une premisse que le MONTAGE
        # garantit (`--crit 0,0`) ne protege de rien : il masque la perte du levier derriere un
        # vert. Si cc n'est plus nul, c'est le levier qui a lache, et il faut le VOIR.
        assert cc == 0, (
            f"crit_chance={cc} != 0 : le bit-exact requiert cc=0, et le levier `--crit 0,0` du "
            f"build ne mord plus (regime BiS, cf. #933)")
        if off_hits < 2:
            pytest.skip(f"turnsStarted={off_hits} < 2 (pas de multi-coups discriminant)")
        assert off_hits == max(1, int(ts)), \
            f"_rounds_started {off_hits} != max(1, turnsStarted {ts}) (RoundsStarted != stat 12)"

        # --- LIVE cast ---
        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ABILITY},
            "captureEvents": True}, 120)
        assert _ok(cast), f"cast Executioner non applique: {str(cast)[:200]}"
        live = {}
        for a in (cast.get("actions") or []):
            for e in (a.get("events") or []):
                td = e.get("tags")
                if not td:
                    continue
                td = json.loads(td) if isinstance(td, str) else td
                if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                    live.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
        live_main = live.get(tid) or []
        if not live_main:
            pytest.skip(f"aucun degat live Executioner (cast no-op ; targets live={sorted(live)})")

        # hits = RoundsStarted : le nb de coups LIVE == turnsStarted
        assert len(live_main) == off_hits, \
            f"coups live {len(live_main)} != RoundsStarted (turnsStarted) {off_hits}"

        # (c) A/B : arbre MAIN == sequence directe execute_ability_attack (hits, Psychic, "attack"), meme rng
        st_tree = load_state(dv, ob, snap, board=board); st_tree.rng = _mk_rng(s0)
        res = ExecutionerAbility().execute_behaviour(st_tree, cid, tid)
        assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
        assert res.get("hits") == off_hits, f"port hits {res.get('hits')} != RoundsStarted {off_hits}"
        tree_main = (res.get("main_attack") or {}).get("per_hit") or []

        st_dir = load_state(dv, ob, snap, board=board); st_dir.rng = _mk_rng(s0)
        bmin, bmax, pierce, _cfg_hits = ability_attack_params(st_dir, cid, "Executioner", "Psychic", ranged=True)
        direct = (AttackDamageOperation.execute_ability_attack(
            st_dir, cid, tid, bmin, bmax, pierce, off_hits,
            damage_profile="Psychic", is_melee=False, is_attack_damage_op=True) or {}).get("per_hit")   # "attack"
        assert tree_main == direct, \
            f"arbre MAIN {tree_main} != sequence directe execute_ability_attack {direct} (feuille/pipeline)"

        # (a) bit-exact vs LIVE
        assert tree_main == live_main, \
            f"arbre MAIN {tree_main} != LIVE {live_main} (bit-exact cc=0, native_factory attack)"

        # (d) native_factory discriminant : "ability" (1 tirage/coup) DIVERGE du live des le coup >=2
        st_ab = load_state(dv, ob, snap, board=board); st_ab.rng = _mk_rng(s0)
        off_ability = (AttackDamageOperation.execute_ability_attack(
            st_ab, cid, tid, bmin, bmax, pierce, off_hits,
            damage_profile="Psychic", is_melee=False, is_attack_damage_op=False) or {}).get("per_hit")   # "ability"
        assert off_ability != live_main, \
            (f"modele 'ability' {off_ability} == LIVE {live_main} : le discriminant native_factory ne separe "
             f"pas les familles sur ce cast (attendu: 'ability' desync des le coup 2)")
        print(f"[exec live seed={seed}] hits(RoundsStarted)={off_hits} cc=0 | LIVE main={live_main}")
        print(f"[exec live seed={seed}] tree(attack)={tree_main} == LIVE ; ability(1/coup)={off_ability} != LIVE")
        print(f"[exec live seed={seed}] A/B tree==direct OK ; native_factory=attack DISCRIMINE")
    finally:
        _cleanup(rpc, rid, state_file)


# ------------------------------------------------------------------ (b) If(IsDead) + secondary (offline, drive)

def _find_vis(state, vis):
    from engine.runner.components import UnitComponent
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.alive and uc.visual_id == vis:
            return uid
    return None


def _enemies_of(state, uid):
    from engine.runner.components import UnitComponent, OwnerComponent
    oc = state.get_entity(uid).get_component(OwnerComponent)
    out = []
    for oid, e in state.entities.items():
        u = e.get_component(UnitComponent); o = e.get_component(OwnerComponent)
        if u and o and u.alive and o.team != oc.team:
            out.append(oid)
    return sorted(out)


def _setpos(state, uid, c):
    from engine.runner.components import PositionComponent
    pc = state.get_entity(uid).get_component(PositionComponent)
    pc.col, pc.row = int(c[0]), int(c[1])


def _hp(state, uid):
    from engine.runner.components import HealthComponent
    hc = state.get_entity(uid).get_component(HealthComponent)
    return hc.hp if hc is not None else None


def _sethp(state, uid, v):
    from engine.runner.components import HealthComponent
    state.get_entity(uid).get_component(HealthComponent).hp = int(v)


def _set_turns_started(state, uid, k):
    from engine.runner.components import StatsComponent
    from engine.entities.stats import StatType
    us = state.get_entity(uid).get_component(StatsComponent).ctx.stats
    cur = us.get_stat(int(StatType.TURNS_STARTED), 0)
    us.increment_base(int(StatType.TURNS_STARTED), int(k) - int(cur))


def test_executioner_isdead_secondary_offline(live_session, rpc):
    """(b) DISCRIMINANTS If(IsDead) + secondary, drivees OFFLINE depuis un etat LIVE reel (deterministe) :
      [KILL]      cible TUEE (hp->1) -> 2e attaque sur 1 ennemi VIVANT adjacent a la CIBLE, hits=RoundsStarted.
      [SURVIVE]   cible VIVANTE (hp haut) -> AUCUNE 2e attaque (If(IsDead) faux).
      [CAP1]      2 ennemis adjacents-cible -> secondary sur 1 SEUL (PickRandomly(1)), l'autre intact.
      [ANCHOR]    ennemi adjacent a la CIBLE (loin du caster) touche ; decoy adjacent au CASTER (loin cible)
                  intact -> ancrage CIBLE (AdjacentUnits(TargetTile()), pas CasterTile)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.abilities.aeldari import ExecutionerAbility
    from engine.runner.abilities.base import ability_attack_params
    from engine.runner.operations.damage import AttackDamageOperation

    rid, state_file = _build(rpc, "777")
    if rid is None:
        pytest.skip("build runner KO (rl_duel)")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if snap is None or not _ok(s0):
            pytest.skip("capture indispo")

        def mkstate():
            st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
            r = IntBasedMersenneTwister(); r.mt = list(s0["mt"]); r.mti = s0["mti"]; st.rng = r
            return st

        cid = _find_vis(mkstate(), CASTER_VIS)
        ens = _enemies_of(mkstate(), cid)
        if cid is None or len(ens) < 3:
            pytest.skip("caster + 3 ennemis requis")
        tid, eid, e2 = ens[0], ens[1], ens[2]

        # tuile T (cible) avec >=3 voisins libres ; caster+ennemis places autour
        T = next((t for t in sorted(board.by_id)
                  if board.walkable(t) and sum(1 for n in board.neighbours(t) if board.walkable(n)) >= 3), None)
        if T is None:
            pytest.skip("aucune tuile a 3 voisins libres")
        tc = board.coord(T)
        nb = [board.coord(n) for n in board.neighbours(T) if board.walkable(n)]
        far = [board.coord(t) for t in sorted(board.by_id)
               if board.walkable(t) and hexgeo.distance(board.coord(t), tc) > 6]
        K = 4                                                       # RoundsStarted force -> 4 coups

        # [KILL] cible tuee -> secondary sur eid (adjacent cible), K coups ; per-hit == baseline
        st = mkstate(); _set_turns_started(st, cid, K)
        _setpos(st, cid, nb[0]); _setpos(st, tid, tc); _setpos(st, eid, nb[1]); _setpos(st, e2, far[0])
        _sethp(st, tid, 1)
        hp_e0 = _hp(st, eid)
        res = ExecutionerAbility().execute_behaviour(st, cid, tid)
        assert res is not None and res.get("dsl") is True and res.get("hits") == K
        assert _hp(st, tid) == 0, f"[KILL] cible non tuee (hp={_hp(st, tid)})"
        sec = res.get("secondary_attacks") or []
        assert len(sec) == 1 and sec[0]["target"] == eid, \
            f"[KILL] secondary {[x['target'] for x in sec]} != [eid={eid}] (1 ennemi adjacent-cible)"
        sec_ph = (sec[0]["attack"] or {}).get("per_hit") or []
        assert len(sec_ph) == K, f"[KILL] secondary {len(sec_ph)} coups != RoundsStarted {K}"
        assert _hp(st, eid) < hp_e0, f"[KILL] ennemi adjacent-cible non endommage ({hp_e0}->{_hp(st, eid)})"
        # A/B secondary : per-hit == sequence directe (meme rng consomme apres le main : re-derive le flux)
        st_b = mkstate(); _set_turns_started(st_b, cid, K)
        _setpos(st_b, cid, nb[0]); _setpos(st_b, tid, tc); _setpos(st_b, eid, nb[1]); _setpos(st_b, e2, far[0])
        _sethp(st_b, tid, 1)
        bmin, bmax, pierce, _h = ability_attack_params(st_b, cid, "Executioner", "Psychic", ranged=True)
        AttackDamageOperation.execute_ability_attack(st_b, cid, tid, bmin, bmax, pierce, K,
                                                     damage_profile="Psychic", is_melee=False, is_attack_damage_op=True)
        # `PickRandomly(Alive(Enemies(AdjacentUnits(TargetTile()))), 1)` s'intercale entre le MAIN et le
        # SECONDARY : il consomme `min(len(pool), 1)` tirages MEME quand le pool tient dans `amount`
        # (#130 -- aucun court-circuit dans `PickRandomAmountSelector$$Select`). Ici le setup ne laisse
        # QU'UN ennemi adjacent a la cible (`eid` ; `e2` est parque a >6 hex) -> pool==1, borne 1.
        st_b.rng.next_internal(0, 1)
        ref_sec = (AttackDamageOperation.execute_ability_attack(
            st_b, cid, eid, bmin, bmax, pierce, K,
            damage_profile="Psychic", is_melee=False, is_attack_damage_op=True) or {}).get("per_hit")
        assert sec_ph == ref_sec, f"[KILL] secondary per-hit {sec_ph} != baseline {ref_sec} (A/B)"

        # [SURVIVE] cible vivante -> aucune 2e attaque
        st = mkstate(); _set_turns_started(st, cid, K)
        _setpos(st, cid, nb[0]); _setpos(st, tid, tc); _setpos(st, eid, nb[1]); _setpos(st, e2, far[0])
        _sethp(st, tid, 10_000_000)
        hp_e0 = _hp(st, eid)
        res = ExecutionerAbility().execute_behaviour(st, cid, tid)
        assert _hp(st, tid) > 0, "[SURVIVE] la cible devait survivre"
        assert len(res.get("secondary_attacks") or []) == 0, \
            f"[SURVIVE] 2e attaque a tort (cible vivante) : {res.get('secondary_attacks')}"
        assert _hp(st, eid) == hp_e0, f"[SURVIVE] ennemi adjacent endommage a tort ({hp_e0}->{_hp(st, eid)})"

        # [CAP1] 2 ennemis adjacents-cible -> secondary sur 1 SEUL
        st = mkstate(); _set_turns_started(st, cid, K)
        _setpos(st, cid, nb[0]); _setpos(st, tid, tc); _setpos(st, eid, nb[1]); _setpos(st, e2, nb[2])
        _sethp(st, tid, 1)
        hp0 = {eid: _hp(st, eid), e2: _hp(st, e2)}
        res = ExecutionerAbility().execute_behaviour(st, cid, tid)
        hit = [x["target"] for x in (res.get("secondary_attacks") or [])]
        assert len(hit) == 1 and hit[0] in (eid, e2), f"[CAP1] secondary {hit} != 1 parmi {{{eid},{e2}}}"
        other = e2 if hit[0] == eid else eid
        assert _hp(st, other) == hp0[other], f"[CAP1] le 2e adjacent (non pick) touche a tort -> cap-1 viole"
        assert _hp(st, hit[0]) < hp0[hit[0]], "[CAP1] l'ennemi pick doit subir des degats"

        # [ANCHOR] ancrage CIBLE, pas caster : eid adjacent-cible (loin caster) touche ; decoy adjacent-caster
        #          (loin cible) intact. Geometrie : caster C, cible T adjacent C ; eid = voisin de T a dist>=2 de
        #          C ; decoy = voisin de C a dist>=2 de T.
        geom = _find_anchor_geom(board)
        if geom is not None:
            C, Tt, E_adjT, D_adjC = geom
            st = mkstate(); _set_turns_started(st, cid, K)
            _setpos(st, cid, C); _setpos(st, tid, Tt); _setpos(st, eid, E_adjT); _setpos(st, e2, D_adjC)
            _sethp(st, tid, 1)
            hp_e0, hp_d0 = _hp(st, eid), _hp(st, e2)
            res = ExecutionerAbility().execute_behaviour(st, cid, tid)
            hit = [x["target"] for x in (res.get("secondary_attacks") or [])]
            assert hit == [eid], f"[ANCHOR] secondary {hit} != [eid={eid}] (adjacent CIBLE)"
            assert _hp(st, eid) < hp_e0, "[ANCHOR] ennemi adjacent-cible non touche"
            assert _hp(st, e2) == hp_d0, \
                f"[ANCHOR] decoy adjacent-CASTER touche a tort -> ancrage caster (pas cible) ({hp_d0}->{_hp(st, e2)})"
            print(f"[exec offline] ANCHOR OK : secondary ancre CIBLE (eid adjacent-T touche, decoy adjacent-C intact)")
        else:
            print("[exec offline] ANCHOR : geometrie discriminante indispo (skip ce sous-cas)")

        print("[exec offline] If(IsDead) KILL/SURVIVE/CAP1 OK ; secondary hits=RoundsStarted ; A/B secondary OK")
    finally:
        _cleanup(rpc, rid, state_file)


def _find_anchor_geom(board):
    """(C, T, E, D) marchables distincts : dist(C,T)=1 ; E voisin de T avec dist(E,C)>=2 ; D voisin de C avec
    dist(D,T)>=2. E = adjacent CIBLE (pas caster) ; D = adjacent CASTER (pas cible) -> discriminant net."""
    coords = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]

    def nbrs(c):
        return [d for d in coords if hexgeo.distance(c, d) == 1]
    for C in coords:
        for T in nbrs(C):
            E = next((e for e in nbrs(T) if e != C and hexgeo.distance(e, C) >= 2), None)
            D = next((d for d in nbrs(C) if d not in (T, E) and hexgeo.distance(d, T) >= 2), None)
            if E is not None and D is not None:
                return C, T, E, D
    return None
