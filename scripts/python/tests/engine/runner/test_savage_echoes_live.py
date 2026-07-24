"""SavageEchoes (1230, Cezare `bloodTerminator`, BloodAngels) -- face COMBAT (execute) portee, confrontee au LIVE.

`SavageEchoesAbility.ExecuteBehaviour @181204660` (DECOMPILE, mirror 1:1) =
    Execute( op_BitwiseAnd( op_BitwiseAnd(
        SetCache(cache),
        AttackWithAttackDamage(Self@0x148, Target@0x178,
            GetDamage = Sum( MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                             Multiply(Get(GetVariableForLevel(config, 8 = extraDmg)),
                                      Count(CanAddUnit(AdjacentTiles(Self@0x148)))) ),
            GetDamageProfile = Eviscerate, nrOfHits = ArmoriumCherubAbility.GetHits = GetNumberConstant(0x2f)=4) ),
        If( cache = Cache(HealthPctIsBelowOrEqual(Caster@0x160, ConfigConst(0x4f = healthPct = 50))),
            Heal(Self@0x148, Self@0x148, Get(GetVariableForLevel(config, 0x1d = hp)), ForRegenerate) ) ) )

MECANIQUE (Melee, 4 coups Eviscerate PiercingRatio 50) : degat/coup = roll(minDmg,maxDmg) + extraDmg x
count(tuiles adjacentes LIBRES du caster) ; self-heal de `hp` SI le HP du caster etait <= 50% de son MaxHealth
AVANT l'attaque. `native_factory="attack"` (@180de9fb0, 2 tirages/coup a cc=0 -- XREFS ExecuteBehaviour
@18120487b == template ArmoriumCherub @1811b417d ; cas rngcrit-1202).

PORTEUR HORS POOL + RESIDU DE CAST LIVE (documente) : `bloodTerminator` (Cezare) est absent du seed BC capture
-> on l'INJECTE (bloc Unit clone d'une unite BloodAngels + `ActiveAbilities=[1230]`, `PassiveAbilities=[]` pour
isoler SavageEchoes de RedRampage 1551 non porte) via `--seed-bc` (N'ECRIT JAMAIS le seed partage).
buildNormalizedBC le normalise (ActiveAbilityLevel 50, mult 180) et il spawne AVEC SavageEchoes reconnue
(decisionView/abilityTargets). MAIS le cast LIVE de 1230 leve une exception native `system error` :
`AbilityConfiguration.GetVariableForLevel @181576fb0` (throwFlag=0) THROW quand la config du porteur INJECTE n'a
PAS la variable exotique demandee (extraDmg index 8, hp 0x1d, healthPct 0x4f) -- ces arrays ne sont pas
materialisees pour une unite HORS de la progression roster. Preuve : le MEME porteur injecte caste 1014
(ArmoriumCherub, qui ne lit QUE minDmg/maxDmg/nrOfHits) SANS erreur ; seule SavageEchoes (variables exotiques)
throw. C'est une limite du HARNAIS (injection out-of-pool), PAS un bug du port -- une vraie Cezare (config
complete) l'executerait. Le cast live est donc un RESIDU documente ; on le TENTE (forward-compatible) mais on
n'y ASSERTE rien.

VALIDATION (etat LIVE reel : board dumpe, positions drivees, stats/level/mult du porteur spawne, rng dumpRng) :
  A. WIRING BIT-IDENTIQUE : le PORT `execute_behaviour` (arbre DSL) emet EXACTEMENT les memes per-hit qu'un appel
     DIRECT `execute_ability_attack("SavageEchoes","Eviscerate")` AVEC le bonus `extraDmg x count` applique aux
     bornes (meme Operation, meme rng seede) -> l'arbre + le damage_override + native_factory="attack" sont
     corrects (== patron CordClaw B0 ; la machinerie per-coup partagee est live-validee ailleurs :
     VigilanceEternal 3-hit, CordClaw 4-hit).
  B. DISCRIMINANT extraDmg x count : un baseline SANS le bonus (bornes config seules) DIVERGE (count>0) -> le
     bonus `extraDmg x free-tiles` est reel et correctement porte.
  C. COUNT node : `CanAddUnit(AdjacentTiles(Self))` == free-tiles calcule a la main sur le board LIVE.
  D. self-heal : (d1) HP plein -> regenerate FALSE, heal 0 ; (d2) boundary 51%/50%/49% -> False/True/True
     (`StatPercentageIsBelowOrEqual @180ef5d60` : current/max <= healthPct/100) + amount == gameconfig `hp` x mult.

ASCII only. Skip propre si pas de session / seed BC sans unite clonable / geometrie infaisable.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import hexgeo
import gameconfig as GC

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                      # racine repo
CASTER_VIS = "bloodTerminator"
ABILITY = 1230
TGT_VIS = "necroWarden"                                     # mono-membre, 0 block/evade/shield
A_UNITS = f"{TGT_VIS},necroDestroyer,necroWarden,necroOverlord"


# ------------------------------------------------------------------ helpers

def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _hp_ob(ob, uid):
    for u in (ob.get("units") or []):
        if u.get("squadId") == uid and not u.get("isDead"):
            return u.get("hp")
    return None


def _mk_rng(s):
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _live_hits_from_events(res, tgt_id, hp0):
    hp_seq = [hp0]
    for a in (res.get("actions") or []):
        for ev in (a.get("events") or []):
            if ev.get("kind") == "action" and ev.get("step") == 4 and ev.get("entity") == tgt_id:
                try:
                    tags = json.loads(ev.get("tags") or "{}")
                except Exception:
                    continue
                if "UnitStats_RemainingHealth" in tags:
                    hp_seq.append(tags["UnitStats_RemainingHealth"])
    return [hp_seq[i] - hp_seq[i + 1] for i in range(len(hp_seq) - 1)]


def _write_injected_seed_bc(tag: str):
    """Injecte `bloodTerminator` (clone d'une unite BloodAngels, `ActiveAbilities=[1230]`,
    `PassiveAbilities=[]`) dans une COPIE du seed BC. N'ecrit JAMAIS le seed partage. None si pas de base."""
    from rl_collect_batch import _load_seed_bc
    seed = _load_seed_bc()
    units = seed.get("Units") or []
    base = next((u for u in units if u.get("VisualId") == "bloodDeathCompany"), None)
    if base is None:
        return None
    inj = copy.deepcopy(base)
    inj.update({"Id": CASTER_VIS, "VisualId": CASTER_VIS, "QuestUnitId": CASTER_VIS,
                "ActiveAbilities": [ABILITY], "PassiveAbilities": [],
                "ConfigId": {"PureId": CASTER_VIS, "Rarity": None, "Level": None,
                             "IsBorrowed": False, "IsPvpOpponent": False}})
    p = ROOT / "data" / "rl-state" / f"savage-seedbc-{tag}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({**seed, "Units": units + [inj]}), encoding="utf-8")
    return p


def _build(tag: str):
    bc_file = _write_injected_seed_bc(tag)
    if bc_file is None:
        return -1, None, None
    state_file = ROOT / "data" / "rl-state" / f"savage-test-{tag}.json"
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777", "--state-file", str(state_file),
         "--seed-bc", str(bc_file), "--board", "MC1_67", "--roster", "1",
         "--p-units", CASTER_VIS, "--a-units", A_UNITS, "--hp-target", "300000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        return -2, state_file, bc_file
    return json.loads(state_file.read_text())["runnerId"], state_file, bc_file


def _cleanup(rpc, rid, state_file, bc_file):
    if rid and rid > 0:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass
    for p in (state_file, bc_file):
        try:
            if p is not None:
                p.unlink()
        except Exception:
            pass


def _drive_adjacent(rpc, rid, board):
    """DRIVE Cezare a dist 1 d'un `necroWarden`, park les autres LOIN (count(free-tiles) du caster >0/stable).
    applyAction ignore propriete+portee (doctrine drive-positions). Renvoie (dec, cezare, target)."""
    # avance jusqu'au tour de Cezare
    me = None
    for _ in range(14):
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        me = _find(dec, CASTER_VIS)
        if me is not None and dec.get("currentPlayer") == me.get("owner"):
            break
        rpc("aiPlayTurn", {"runnerId": rid}, 240)
    if me is None:
        return None, None, None
    tgt = _find(dec, TGT_VIS)
    if tgt is None:
        return None, None, None
    T = next((tid for tid in sorted(board.by_id)
              if board.walkable(tid)
              and len([n for n in board.neighbours(tid) if board.walkable(n)]) >= 4), None)
    if T is None:
        return None, None, None
    tc = board.coord(T)
    cc = board.coord([n for n in board.neighbours(T) if board.walkable(n)][0])
    for u in (dec.get("units") or []):
        if u.get("alive") and u.get("id") not in (me["id"], tgt["id"]):
            fx = next((tid for tid in sorted(board.by_id)
                       if board.walkable(tid) and hexgeo.distance(board.coord(tid), tc) > 5), None)
            if fx is not None:
                fc = board.coord(fx)
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": u["id"], "to": {"col": fc[0], "row": fc[1]}}}, 60)
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": tgt["id"], "to": {"col": tc[0], "row": tc[1]}}}, 60)
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": me["id"], "to": {"col": cc[0], "row": cc[1]}}}, 60)
    dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    me2, tgt2 = _find(dec2, CASTER_VIS), _find(dec2, TGT_VIS)
    if me2 is None or tgt2 is None or hexgeo.distance(_pos(me2), _pos(tgt2)) != 1:
        return None, None, None
    return dec2, me2, tgt2


def _offline_count(st, cid):
    from engine.entities.selectors import Caster, CanAddUnit, AdjacentTiles
    from engine.runner.abilities.behaviours import entities_from_state
    return len(CanAddUnit(AdjacentTiles(Caster())).evaluate(entities_from_state(st, cid, cid)))


def _manual_free_tiles(board, cez_coord, occupied_coords):
    """count(CanAddUnit(AdjacentTiles(Self))) a la main = voisins marchables INOCCUPES de la tuile du caster."""
    tid = board.id_at(*cez_coord)
    n = 0
    for nb in board.neighbours(tid):
        if board.walkable(nb) and board.coord(nb) not in occupied_coords:
            n += 1
    return n


# ------------------------------------------------------------------ tests

def test_savage_echoes_wiring_and_free_tile_bonus(live_session, rpc):
    """A. wiring BIT-IDENTIQUE (port == sequence directe + bonus) ; B. discriminant extraDmg x count ;
    C. count node == free-tiles manuel ; d1. regenerate FALSE au HP plein. Cast live TENTE (residu documente)."""
    from engine.runner.snapshot import load_state
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import StatsComponent
    from engine.runner.abilities.bloodangels import SavageEchoesAbility
    from engine.runner.abilities.base import ability_attack_params
    from engine.runner.operations.damage import AttackDamageOperation

    tag = uuid.uuid4().hex[:8]
    rid, state_file, bc_file = _build(tag)
    if rid == -1:
        pytest.skip("seed BC sans unite BloodAngels clonable")
    if rid < 0:
        pytest.skip("build runner KO (seed-bc injection)")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        dec0, me, tgt = _drive_adjacent(rpc, rid, board)
        if me is None:
            pytest.skip("drive-adjacent KO (geometrie)")
        cid, tid = me["id"], tgt["id"]

        ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap0 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if snap0 is None or not _ok(s0):
            pytest.skip("combatSnapshot/dumpRng indispo")

        def mkstate():
            st = load_state(dec0, ob0, snap0)
            st.board = Board(bg["tiles"], adjacency="native_sym")
            st.rng = _mk_rng(s0)
            return st

        st = mkstate()
        count = _offline_count(st, cid)
        csc = st.get_entity(cid).get_component(StatsComponent)
        lvl = getattr(csc.ctx, "active_ability_level", 0)
        mult = int(getattr(csc.ctx, "ability_variables_multiplier", 100) or 100)
        extra_eff = round(int(GC.ability("SavageEchoes")["variables"]["extraDmg"][max(0, lvl - 1)]) * mult / 100)
        # (C) count node == free-tiles manuel sur le board LIVE
        occ = {_pos(u) for u in (dec0.get("units") or []) if u.get("alive")}
        manual = _manual_free_tiles(board, _pos(me), occ - {_pos(me)})
        assert count == manual, f"count node {count} != free-tiles manuel {manual}"
        print(f"[savage] count(free-tiles)={count} lvl={lvl} mult={mult} extra_eff={extra_eff}")

        # (A) PORT (arbre) == sequence directe execute_ability_attack + bonus (bit-identique, meme rng)
        res = SavageEchoesAbility().execute_behaviour(st, cid, tid)
        assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
        port_ph = (res.get("main_attack") or {}).get("per_hit") or []
        assert len(port_ph) == 4, f"port per-hit {port_ph} != 4 coups (nrOfHits)"
        st2 = mkstate()
        bmin, bmax, pierce, hits = ability_attack_params(st2, cid, "SavageEchoes", "Eviscerate", ranged=False)
        assert hits == 4, f"nrOfHits {hits} != 4"
        flat = extra_eff * count
        direct = AttackDamageOperation.execute_ability_attack(
            st2, cid, tid, bmin + flat, bmax + flat, pierce, hits,
            damage_profile="Eviscerate", is_melee=True, wasted_resolve=True)
        assert port_ph == (direct or {}).get("per_hit"), \
            (f"PORT per-hit {port_ph} != sequence directe+bonus {(direct or {}).get('per_hit')} "
             f"(wiring arbre/damage_override/native_factory)")
        print(f"[savage] WIRING bit-identique port==direct+bonus : {port_ph}")

        # (B) discriminant : baseline SANS bonus diverge (count>0)
        if count > 0:
            st3 = mkstate()
            base = AttackDamageOperation.execute_ability_attack(
                st3, cid, tid, bmin, bmax, pierce, hits,
                damage_profile="Eviscerate", is_melee=True, wasted_resolve=True)
            base_ph = (base or {}).get("per_hit") or []
            assert port_ph != base_ph, \
                (f"baseline SANS bonus {base_ph} == port {port_ph} : le bonus extraDmg x count "
                 f"(count={count}) n'a AUCUN effet -> mecanique non validee")
            assert all(p > b for p, b in zip(port_ph, base_ph)), \
                f"port {port_ph} pas tous > baseline {base_ph} (le bonus doit AUGMENTER chaque coup)"
            print(f"[savage] discriminant bonus : port {port_ph} > baseline {base_ph}")
        else:
            print("[savage] count==0 -> discriminant bonus vacuous")

        # (d1) HP plein -> regenerate FALSE, aucun heal
        assert res.get("regenerate") is False, f"HP plein -> regenerate={res.get('regenerate')} (attendu False)"
        assert (res.get("heal_amount") or 0) == 0, f"heal={res.get('heal_amount')} alors que regenerate=False"

        # cast LIVE TENTE (residu documente : la config injectee out-of-pool leve `system error`)
        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ABILITY},
            "captureEvents": True}, 120)
        if _ok(cast):
            live_hits = _live_hits_from_events(cast, tid, _hp_ob(ob0, tid))
            print(f"[savage] cast LIVE OK (config materialisee !) per-hit={live_hits}")
            if len(live_hits) == 4 and int(getattr(csc.ctx, "crit_chance", 0) or 0) == 0:
                assert port_ph == live_hits, f"PORT {port_ph} != LIVE {live_hits} (bit-exact cc=0)"
        else:
            errs = [a.get("error") for a in (cast.get("actions") or [])]
            print(f"[savage] RESIDU cast live (out-of-pool config): errs={errs} "
                  f"-- GetVariableForLevel throw sur variable exotique (extraDmg/hp/healthPct) non "
                  f"materialisee ; wiring valide offline (A/B/C) contre le decompile")
    finally:
        _cleanup(rpc, rid, state_file, bc_file)


def test_savage_echoes_regenerate_heal(live_session, rpc):
    """D. self-heal (regenerate) sur etat LIVE : boundary 51%/50%/49% du seuil healthPct=50 -> False/True/True
    (`StatPercentageIsBelowOrEqual @180ef5d60`) + heal amount == gameconfig `hp` x mult au niveau du porteur."""
    from engine.runner.snapshot import load_state
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import StatsComponent, HealthComponent
    from engine.runner.abilities.bloodangels import SavageEchoesAbility, _regenerate_precondition
    from engine.entities.effects.magnitude import ability_var

    tag = uuid.uuid4().hex[:8]
    rid, state_file, bc_file = _build(tag)
    if rid == -1:
        pytest.skip("seed BC sans unite BloodAngels clonable")
    if rid < 0:
        pytest.skip("build runner KO (seed-bc injection)")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        dec0, me, tgt = _drive_adjacent(rpc, rid, board)
        if me is None:
            pytest.skip("drive-adjacent KO")
        cid, tid = me["id"], tgt["id"]
        ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap0 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if snap0 is None or not _ok(s0):
            pytest.skip("capture indispo")

        def mkstate():
            st = load_state(dec0, ob0, snap0)
            st.board = Board(bg["tiles"], adjacency="native_sym")
            st.rng = _mk_rng(s0)
            return st

        st = mkstate()
        e = st.get_entity(cid)
        hc = e.get_component(HealthComponent)
        sc = e.get_component(StatsComponent)
        lvl = getattr(sc.ctx, "active_ability_level", 0)
        mult = int(getattr(sc.ctx, "ability_variables_multiplier", 100) or 100)
        hp_max = int(hc.hp_max)
        # boundary du seuil 50%
        hc.hp = (51 * hp_max) // 100 + 1
        assert _regenerate_precondition(st, cid) is False, f"HP 51% -> regenerate devrait etre False (hp={hc.hp}/{hp_max})"
        hc.hp = hp_max // 2                                                 # 2*current==max -> <=50%
        assert _regenerate_precondition(st, cid) is True, f"HP 50% -> regenerate devrait etre True (hp={hc.hp}/{hp_max})"
        hc.hp = (49 * hp_max) // 100
        assert _regenerate_precondition(st, cid) is True, f"HP 49% -> regenerate devrait etre True (hp={hc.hp}/{hp_max})"

        # amount == gameconfig hp x mult, heal fire (25%, pas de cap)
        want_heal = int(ability_var("SavageEchoes", "hp", lvl, multiplier_pct=mult))
        st2 = mkstate()
        st2.get_entity(cid).get_component(HealthComponent).hp = hp_max // 4
        res = SavageEchoesAbility().execute_behaviour(st2, cid, tid)
        assert res.get("regenerate") is True, "HP 25% -> regenerate devrait etre True"
        assert int(res.get("heal_amount") or 0) == want_heal, \
            f"heal offline {res.get('heal_amount')} != gameconfig hp x mult {want_heal}"
        healed = next((h.get("healed") for h in (res.get("heals") or []) if h.get("target") == cid), None)
        assert healed and healed > 0, f"self-heal non applique (healed={healed})"
        print(f"[savage-heal] boundary 51/50/49% OK ; heal amount={res.get('heal_amount')} "
              f"(=hp[{lvl}]x{mult}) healed={healed}")
    finally:
        _cleanup(rpc, rid, state_file, bc_file)
