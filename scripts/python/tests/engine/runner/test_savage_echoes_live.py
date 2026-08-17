"""SavageEchoes (1230, Cezare `bloodTerminator`, BloodAngels) -- face COMBAT (execute) portee, confrontee au LIVE.

`IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$ExecuteBehaviour` (DECOMPILE, mirror 1:1) =
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
AVANT l'attaque. `native_factory="attack"` (IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage, 2 tirages/coup a cc=0 -- XREFS IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$ExecuteBehaviour+0x21b == template ArmoriumCherub IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$ExecuteBehaviour+0x17d ; cas rngcrit-1202).

PORTEUR HORS POOL : `bloodTerminator` (Cezare) est absent du seed BC capture -> on l'INJECTE via
`catalog_inject.write_augmented_seed_bc` (bloc `Units` + configs `Abilities`, `ActiveAbilities=[1230]` pour
isoler SavageEchoes de RedRampage 1551 non portee) et `--seed-bc` (N'ECRIT JAMAIS le seed partage).
buildNormalizedBC le normalise (ActiveAbilityLevel 50, mult 180) et il spawne AVEC SavageEchoes reconnue
(decisionView/abilityTargets). Le cast LIVE de 1230 REUSSIT et est ASSERTE (volet E) : le port est confronte
au natif de bout en bout, plus seulement offline.

  (#226 -- ce que l'ancien « residu de cast live » etait vraiment.) Le cast levait « system error » tant que
  le seed BC injecte n'embarquait QUE le bloc Unit : `BattleConfiguration.Abilities` du seed capture ne porte
  que les abilities des unites de CETTE bataille, donc `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel`
  tournait sur une config NULLE. Ce n'etait ni le rang du porteur, ni des arrays de variables « non
  materialisees hors progression roster » (les deux diagnostics anterieurs, FAUX). Mesure a bloc Unit
  CONSTANT (`probe_226_seed_bc_ability_configs.py`) : sans les configs `ok=False errors=['system error']` ;
  avec les configs `ok=True hits=[3825, 3598, 3975, 3445]`.

VALIDATION (etat LIVE reel : board dumpe, positions drivees, stats/level/mult du porteur spawne, rng dumpRng) :
  A. WIRING BIT-IDENTIQUE : le PORT `execute_behaviour` (arbre DSL) emet EXACTEMENT les memes per-hit qu'un appel
     DIRECT `execute_ability_attack("SavageEchoes","Eviscerate")` AVEC le bonus `extraDmg x count` applique aux
     bornes (meme Operation, meme rng seede) -> l'arbre + le damage_override + native_factory="attack" sont
     corrects (== patron CordClaw B0 ; la machinerie per-coup partagee est live-validee ailleurs :
     VigilanceEternal 3-hit, CordClaw 4-hit).
  B. DISCRIMINANT extraDmg x count : un baseline SANS le bonus (bornes config seules) DIVERGE (count>0) -> le
     bonus `extraDmg x free-tiles` est reel et correctement porte.
  C. COUNT node : `CanAddUnit(AdjacentTiles(Self))` == free-tiles calcule a la main sur le board LIVE.
  E. CAST LIVE : le cast natif de 1230 REUSSIT (`ok`), rend `nrOfHits` coups, et (si crit_chance=0) les
     montants sont BIT-EXACTS avec le per-hit du port sous le meme rng. C'est la garde de non-regression
     de #226 : un seed BC injecte sans ses configs d'ability rendrait `ok=False errors=['system error']`.
  D. self-heal : (d1) HP plein -> regenerate FALSE, heal 0 ; (d2) boundary EXACTE au seuil config
     `constants.healthPct` (thr+1 PV / thr / thr-1 -> False/True/True, granularite 1 PV)
     (`StatPercentageIsBelowOrEqual IdunBattle.Entities.Conditions.StatPercentageIsBelowOrEqualAbilityTrigger$$ShouldTrigger` : current/max <= healthPct/100) + amount == gameconfig `hp` x mult.

ORACLES (#96 -- aucun scalaire de gameplay fige ici). Le decompile TRANCHE, volet par volet, dans
`IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$ExecuteBehaviour` :
  - nb de coups = `IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits` =
    `GetNumberConstant(cfg, 0x2f)` passe DIRECTEMENT a `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`
    (aucune formule ; `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant` = `GetStringConstant`
    + `System.Int32.Parse`) -> valeur BRUTE, oracle = `gameconfig.ability("SavageEchoes").constants.nrOfHits` ;
  - seuil du self-heal = `IdunBattleLogic.Entities.DSLFormulas$$ConfigConst(0x4f)` consomme par `IdunBattleLogic.Entities.DSLTriggers$$HealthPctIsBelowOrEqual`
    (cf. aussi `SavageEchoesAbility$$GetRegenerateCondition`) -> BRUTE, oracle =
    `constants.healthPct` ;
  - le DEGAT, lui, est CALCULE (`Sum(MinMaxDamage, Multiply(Get(GetVariableForLevel(8)), Count(...)))`) : on
    ne fige donc AUCUN montant, on confronte port vs sequence directe sous le meme rng (A) et le bonus au
    discriminant (B).
Cle non ambigue : enum `AbilityConstantType` 0x2f=nrOfHits(47) (cf. `engine/entities/formulas.py::ConfigConst`).

ASCII only. Skip propre si pas de session / seed BC sans unite clonable / geometrie infaisable.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import hexgeo
import gameconfig as GC
import stream_events as SE

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                      # racine repo
CASTER_VIS = "bloodTerminator"
ABILITY = 1230
TGT_VIS = "necroWarden"                                     # mono-membre, 0 block/evade/shield
A_UNITS = f"{TGT_VIS},necroDestroyer,necroWarden,necroOverlord"


# ------------------------------------------------------------------ helpers

def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _const(key):
    """ORACLE : constante de config d'ability SavageEchoes (`GetNumberConstant`/`ConfigConst`, lecture
    BRUTE cote natif -- cf. en-tete). Fail explicite si la cle a disparu de la config."""
    v = ((GC.ability("SavageEchoes") or {}).get("constants") or {}).get(key)
    assert v is not None, (f"oracle introuvable : gameconfig.ability('SavageEchoes').constants.{key} "
                           f"absent -- le natif le lit en ConfigConst, il DOIT exister")
    return int(v)


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
            if ev.get("kind") == "action" and ev.get("step") == SE.step_id("UnitDamaged") \
                    and ev.get("entity") == tgt_id:
                try:
                    tags = json.loads(ev.get("tags") or "{}")
                except Exception:
                    continue
                if "UnitStats_RemainingHealth" in tags:
                    hp_seq.append(tags["UnitStats_RemainingHealth"])
    return [hp_seq[i] - hp_seq[i + 1] for i in range(len(hp_seq) - 1)]


def _write_injected_seed_bc(tag: str):
    """Seed BC augmente de `bloodTerminator` -- bloc `Units` **ET** configs `Abilities`
    (`SavageEchoes`, `RedRampage`) -- via `catalog_inject.write_augmented_seed_bc`, le mirror de
    `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration`. N'ECRIT JAMAIS le seed
    partage. `ActiveAbilities` est restreint a 1230 pour ISOLER SavageEchoes de la passive RedRampage
    (1551, non portee) ; les CONFIGS restent toutes posees (une config non portee est inerte).
    None si le seed BC de reference est absent.

    PAS DE CLONE DE BLOC UNIT (etat anterieur) : `BC.Abilities` du seed capture ne porte QUE les
    abilities des unites de CETTE bataille -- ni SavageEchoes ni RedRampage. Sans elles le porteur se
    deploie et expose son ability, mais le cast FAUTE (`GetVariableForLevel` sur config nulle ->
    « system error »). Mesure #226 (`probe_226_seed_bc_ability_configs.py`, MEME bloc Unit, seules
    les configs changent) : sans configs `ok=False errors=['system error']` / avec configs
    `ok=True hits=[3825, 3598, 3975, 3445]`."""
    import catalog_inject as CI
    if not CI.SEED_BC.exists():
        return None
    path, _units, _abilities = CI.write_augmented_seed_bc(
        ROOT / "logs" / "runners" / f"savage-seedbc-{tag}.json",
        [CASTER_VIS], restrict_abilities={CASTER_VIS: ([ABILITY], [])})
    return path


def _build(tag: str):
    bc_file = _write_injected_seed_bc(tag)
    if bc_file is None:
        return -1, None, None
    state_file = ROOT / "logs" / "runners" / f"savage-test-{tag}.json"
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777", "--state-file", str(state_file),
         "--seed-bc", str(bc_file), "--board", "MC1_67", "--roster", "1",
         "--p-units", CASTER_VIS, "--a-units", A_UNITS, "--hp-target", "300000",
         # #933 -- LE REGIME « SANS CRIT » SE CONSTRUIT, IL NE SE SUPPOSE PLUS. L'assertion
         # bit-exact port/live du volet (E) etait gardee par `if cc == 0:` ; depuis la bascule
         # #419-r5/-r6, `bloodTerminator` porte CritChance=20 (MESURE) et la garde SAUTAIT --
         # l'assertion la plus forte du fichier n'etait plus jamais evaluee, sans aucun rouge.
         # `--crit 0,0` epingle les p-units, dont le caster est la seule.
         "--crit", "0,0"],
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
    from engine.entities.selectors.tiles import AdjacentTiles, CanAddUnit, Caster
    from engine.runner.abilities.behaviours.context import entities_from_state
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
        pytest.skip("seed BC de reference absent (data/seed-bc.json)")
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
            st = load_state(dec0, ob0, snap0, board=Board(bg["tiles"], adjacency="native_sym"))
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
        want_hits = _const("nrOfHits")            # ORACLE config (cf. en-tete), jamais un litteral
        assert len(port_ph) == want_hits, \
            f"port per-hit {port_ph} = {len(port_ph)} coups != oracle config nrOfHits={want_hits}"
        st2 = mkstate()
        bmin, bmax, pierce, hits = ability_attack_params(st2, cid, "SavageEchoes", "Eviscerate", ranged=False)
        assert hits == want_hits, (
            f"nrOfHits lu {hits} != oracle config {want_hits} (constants.nrOfHits) -- le port ne lit pas la "
            f"CONSTANTE d'ability (0x2f) mais autre chose (variable per-niveau scalee ? mauvaise cle ?)")
        flat = extra_eff * count
        direct = AttackDamageOperation.execute_ability_attack(
            st2, cid, tid, bmin + flat, bmax + flat, pierce, hits,
            damage_profile="Eviscerate", is_melee=True, is_attack_damage_op=True)
        assert port_ph == (direct or {}).get("per_hit"), \
            (f"PORT per-hit {port_ph} != sequence directe+bonus {(direct or {}).get('per_hit')} "
             f"(wiring arbre/damage_override/native_factory)")
        print(f"[savage] WIRING bit-identique port==direct+bonus : {port_ph}")

        # (B) discriminant : baseline SANS bonus diverge (count>0)
        if count > 0:
            st3 = mkstate()
            base = AttackDamageOperation.execute_ability_attack(
                st3, cid, tid, bmin, bmax, pierce, hits,
                damage_profile="Eviscerate", is_melee=True, is_attack_damage_op=True)
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

        # (E) cast LIVE -- ASSERTE depuis #226 : le seed BC injecte porte les configs d'ability, donc
        # `GetVariableForLevel` ne tourne plus sur une config nulle. Un `system error` ici = regression
        # du harnais d'injection (bloc Unit sans ses configs), PAS une limite du jeu.
        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ABILITY},
            "captureEvents": True}, 120)
        errs = [a.get("error") for a in (cast.get("actions") or []) if a.get("error")]
        assert _ok(cast), (
            f"cast LIVE de {ABILITY} KO: errs={errs}. 'system error' = faute d'invoke il2cpp -- le seed "
            f"BC injecte n'embarque probablement plus les configs d'ability (cf. #226 / "
            f"catalog_inject.write_augmented_seed_bc)")
        live_hits = _live_hits_from_events(cast, tid, _hp_ob(ob0, tid))
        assert len(live_hits) == want_hits, \
            f"cast LIVE : {len(live_hits)} coups {live_hits} != oracle config nrOfHits={want_hits}"
        # PREMISSE DE REGIME, RENDUE EXPLICITE (#933). Le bit-exact port/live n'a de sens que si le
        # caster ne peut pas critiquer -- sinon un crit-roll cote natif ecarte legitimement les deux
        # per-hit. C'etait une GARDE (`if cc == 0:`), et depuis la bascule #419-r5/-r6 (items BiS
        # equipes par defaut) le caster porte du crit : la garde SAUTAIT, l'assertion la plus forte
        # du fichier n'etait PLUS JAMAIS evaluee, et le test restait VERT en ne mesurant rien.
        # Le regime « sans crit » se CONSTRUIT desormais (`--crit 0,0` au build, cf. `_build`) et la
        # premisse est ASSERTIONNEE : si le levier cesse de mordre, ce test rougit en NOMMANT le
        # levier au lieu d'accuser le port.
        cc_caster = int(getattr(csc.ctx, "crit_chance", 0) or 0)
        assert cc_caster == 0, (
            f"caster a CritChance={cc_caster} : le bit-exact port/live n'est pas concluant "
            f"(un crit-roll natif l'ecarte legitimement). Le levier `--crit 0,0` du build "
            f"ne mord plus.")
        assert port_ph == live_hits, f"PORT {port_ph} != LIVE {live_hits} (bit-exact cc=0)"
        print(f"[savage] cast LIVE OK per-hit={live_hits} (port={port_ph})")
    finally:
        _cleanup(rpc, rid, state_file, bc_file)


def test_savage_echoes_regenerate_heal(live_session, rpc):
    """D. self-heal (regenerate) sur etat LIVE : boundary EXACTE (granularite 1 PV) autour du seuil lu en
    config `constants.healthPct` -- thr+1 PV / thr / thr-1 -> False/True/True
    (`StatPercentageIsBelowOrEqual IdunBattle.Entities.Conditions.StatPercentageIsBelowOrEqualAbilityTrigger$$ShouldTrigger`) + heal amount == gameconfig `hp` x mult au niveau du porteur."""
    from engine.runner.snapshot import load_state
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import StatsComponent, HealthComponent
    from engine.runner.abilities.bloodangels import SavageEchoesAbility, _regenerate_precondition
    from engine.entities.effects.magnitude import ability_var

    tag = uuid.uuid4().hex[:8]
    rid, state_file, bc_file = _build(tag)
    if rid == -1:
        pytest.skip("seed BC de reference absent (data/seed-bc.json)")
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
            st = load_state(dec0, ob0, snap0, board=Board(bg["tiles"], adjacency="native_sym"))
            st.rng = _mk_rng(s0)
            return st

        st = mkstate()
        e = st.get_entity(cid)
        hc = e.get_component(HealthComponent)
        sc = e.get_component(StatsComponent)
        lvl = getattr(sc.ctx, "active_ability_level", 0)
        mult = int(getattr(sc.ctx, "ability_variables_multiplier", 100) or 100)
        hp_max = int(hc.hp_max)
        # BOUNDARY sur le seuil LU EN CONFIG (`ConfigConst(0x4f)=healthPct`), pas sur un 50% fige :
        # `thr_hp` = plus grand PV qui satisfait ENCORE `100*current <= healthPct*max`. On teste a 1 PV
        # pres de part et d'autre -> discrimine `<=` de `<` quel que soit le pourcentage configure.
        pct = _const("healthPct")
        thr_hp = (pct * hp_max) // 100
        assert 1 < thr_hp < hp_max, (f"setup non discriminant : seuil healthPct={pct}% -> thr_hp={thr_hp} "
                                     f"hors ]1, hp_max={hp_max}[ (impossible de tester les deux cotes)")
        hc.hp = thr_hp + 1
        assert _regenerate_precondition(st, cid) is False, \
            f"HP {hc.hp}/{hp_max} (1 PV AU-DESSUS du seuil {pct}%) -> regenerate devrait etre False"
        hc.hp = thr_hp
        assert _regenerate_precondition(st, cid) is True, \
            f"HP {hc.hp}/{hp_max} (AU seuil {pct}%) -> regenerate devrait etre True (comparateur <=)"
        hc.hp = thr_hp - 1
        assert _regenerate_precondition(st, cid) is True, \
            f"HP {hc.hp}/{hp_max} (1 PV SOUS le seuil {pct}%) -> regenerate devrait etre True"

        # amount == gameconfig hp x mult, heal fire (PV bas, sous le seuil config -> pas de cap)
        want_heal = int(ability_var("SavageEchoes", "hp", lvl, multiplier_pct=mult))
        st2 = mkstate()
        st2.get_entity(cid).get_component(HealthComponent).hp = max(1, min(hp_max // 4, thr_hp - 1))
        res = SavageEchoesAbility().execute_behaviour(st2, cid, tid)
        assert res.get("regenerate") is True, "HP sous le seuil config -> regenerate devrait etre True"
        assert int(res.get("heal_amount") or 0) == want_heal, \
            f"heal offline {res.get('heal_amount')} != gameconfig hp x mult {want_heal}"
        healed = next((h.get("healed") for h in (res.get("heals") or []) if h.get("target") == cid), None)
        assert healed and healed > 0, f"self-heal non applique (healed={healed})"
        print(f"[savage-heal] boundary healthPct={pct}% (thr_hp={thr_hp} +-1 PV) OK ; "
              f"heal amount={res.get('heal_amount')} (=hp[{lvl}]x{mult}) healed={healed}")
    finally:
        _cleanup(rpc, rid, state_file, bc_file)
