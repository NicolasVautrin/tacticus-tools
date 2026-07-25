"""FlailSwing (actif 1042, deathBlightlord DeathGuard/Chaos) PORT -> arbre DSL, confronte au LIVE (#220).

`FlailSwingAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.FlailSwingAbility$$ExecuteBehaviour` (DECOMPILE, mirror 1:1 -- cf. `abilities/deathguard.py`) =
    Execute( op_BitwiseAnd(
        InformWeapon(GetDamageProfile=Power, 1),                                  # metadata arme (no-op combat)
        AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                               GetDamageProfile=Power, nrOfHits=GetNumberConstant(0x2f),
                               alwaysOverkilled=Nullable(true)) ) )
plain `Execute` (PAS `ExecuteAtomic` -- l'op_BitwiseAnd est passe DIRECTEMENT a `AActiveAbility.Execute`).
`native_factory="attack"` (la CALLEE de IdunBattleLogic.Entities.Abilities.Active.Loki.FlailSwingAbility$$ExecuteBehaviour = symbole `DSLFactory$$IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`,
JAMAIS `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage`) = 2 tirages/coup a cc=0 (tip #2 / rngcrit-1202). PAS de splash,
PAS de move/gate, PAS de trigger interne (le declenchement `HazeOfCorruption` = passif SEPARE, hors scope).

Ce que ces tests PROUVENT (drive les positions -- `applyAction move` ignore portee/propriete ; `--hp-target`
= armure nulle pour un per-coup bit-exact) :
  (1) CAST LIVE bit-exact : 3 coups Power sur la cible == offline per-coup (melee, board plat MC1_67, aucun
      buff scalaire ranged/high-ground -> ratio 1.0 EXACT) ; A/B tree == sequence directe execute_ability_attack ;
      mono-cible (un 2e ennemi voisin de la cible n'est PAS touche).
  (2) native_factory="attack" : ratio live/offline CONSTANT (== 1.0, 2 tirages/coup) en famille "attack",
      NON-CONSTANT en famille "ability" (1 tirage/coup -> desync des le coup 2). Discriminant rngcrit-1202,
      2 seeds (tip #7).
  (3) OVERKILL (flag alwaysOverkilled, `force_overkill=True`) : cible Resilient (custoKyrus) HP tune 10000
      (total FlailSwing ~14400 < 2x seuil overkill=100%) -> LIVE TUE a travers Resilient (sum des coups ==
      PV full, PAS PV-1) ; le port (force_overkill=True) laisse la cible a 0 PV (morte) == live ; le CONTROL
      SANS le flag laisse 1 PV (cap Resilient tient) -> le flag est le SEUL ecart (bypass du cap
      `IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit`).

ORACLE DU NOMBRE DE COUPS (#96 / lot A) : le natif ne DERIVE pas le nb de coups, il le LIT tel quel --
`AbilityConfiguration.GetNumberConstant(cfg, 0x2f)` (DECOMPILE ci-dessus), et `GetNumberConstant` =
`Int32.Parse(GetStringConstant(...))` sur le dictionnaire de constantes de l'ability. La valeur est donc
BRUTE -> l'oracle est la CONFIG, `gameconfig.ability("FlailSwing").constants.nrOfHits` (helper `_cfg_hits`),
jamais un litteral : un re-equilibrage deplace l'attendu AVEC le jeu au lieu de rougir (ou pire, de rester
vert sur une verite perimee). Le nb de coups REELLEMENT emis, lui, est CALCULE (`attack_hits_with_modifiers`
= constante +/- extraHits/malus defenseur/cover, plancher `max(1, ...)`) -> son oracle est le LIVE : on
confronte port-vs-live, et l'egalite avec la constante ne vaut que parce que ce setup n'a aucun modificateur
de canal de coups (elle le CONSTATE).

Lit l'etat LIVE, aucune tuile/RVA hardcodee. ASCII only. State-file UNIQUE -> dispose au teardown. Skip si
build/geometrie/deathBlightlord|custoKyrus indispo.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import gameconfig as GC
import hexgeo
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, PositionComponent
from engine.runner.abilities.deathguard import FlailSwingAbility
from engine.runner.abilities.base import ability_attack_params
from engine.runner.operations.damage import AttackDamageOperation

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                      # racine repo
CASTER_VIS = "deathBlightlord"
ABILITY = 1042
A_UNITS = "necroWarden,necroWarden,necroWarden,necroOverlord"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _cfg_hits(key: str = "nrOfHits") -> int:
    """ORACLE du nb de coups = la CONSTANTE de config de FlailSwing, PAS un litteral.
    `IdunBattleLogic.Entities.Abilities.Active.Loki.FlailSwingAbility$$ExecuteBehaviour` passe
    `hits = IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(cfg, 0x2f)` a
    `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` : valeur BRUTE (aucune formule), donc
    l'oracle est `gameconfig.ability("FlailSwing").constants[<key>]`."""
    c = (GC.ability("FlailSwing") or {}).get("constants") or {}
    v = c.get(key)
    assert v is not None, (f"oracle introuvable : constants.{key} absent de gameconfig pour FlailSwing "
                           f"(GetNumberConstant(0x2f) non resolvable offline)")
    return int(v)


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _find(dv, vis):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vis and u.get("alive")), None)


def _spread(ratios):
    return (max(ratios) - min(ratios)) if ratios else 0.0


def _build(seed, a_units, hp):
    sf = ROOT / "data" / "rl-state" / f"flail-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", "MC1_67", "--roster", "1", "--p-units", CASTER_VIS, "--a-units", a_units,
         "--hp-target", str(hp)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, None, (proc.stderr or proc.stdout or "")[-300:]
    return int(json.loads(sf.read_text())["runnerId"]), sf, None


def _advance_and_place(rpc, rid, board, target_vis, second_vis=None):
    """Avance jusqu'a mon tour, parque les ennemis LOIN, place la cible sur un voisin marchable du caster
    (melee castable). `second_vis` != None -> place un 2e ennemi sur un AUTRE voisin de la cible (test
    mono-cible). Renvoie (cid, target_id, second_id|None) ou None si infaisable."""
    def dview():
        return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)

    myp = None
    for _ in range(20):
        dv = dview()
        c = _find(dv, CASTER_VIS)
        if c is None:
            return None
        myp = c.get("owner")
        if dv.get("currentPlayer") == myp:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    else:
        return None

    dv = dview()
    c = _find(dv, CASTER_VIS)
    cid = c["id"]
    cpos = (c["pos"]["col"], c["pos"]["row"])
    ctile = board.id_at(*cpos)
    tgt = _find(dv, target_vis)
    if tgt is None:
        return None
    enemies = [u for u in (dv.get("units") or []) if u.get("owner") != myp and u.get("alive")]
    sec = _find(dv, second_vis) if second_vis else None
    keep = {tgt["id"]} | ({sec["id"]} if sec else set())
    far = [t for t in sorted(board.by_id) if board.walkable(t) and hexgeo.distance(board.coord(t), cpos) > 5]
    it = iter(far)
    for e in enemies:
        if e["id"] in keep:
            continue
        ft = next(it, None)
        if ft is None:
            break
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": e["id"], "to": {"col": board.coord(ft)[0], "row": board.coord(ft)[1]}}}, 60)
    nbrs = [n for n in board.neighbours(ctile) if board.walkable(n)]
    if not nbrs:
        return None
    tcoord = board.coord(nbrs[0])
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": tgt["id"], "to": {"col": tcoord[0], "row": tcoord[1]}}}, 60)
    sec_id = None
    if sec is not None:
        # 2e ennemi sur un voisin de la CIBLE distinct de la tuile du caster (test mono-cible / pas de splash)
        tnbrs = [n for n in board.neighbours(board.id_at(*tcoord))
                 if board.walkable(n) and board.coord(n) != cpos
                 and hexgeo.distance(board.coord(n), cpos) > 1]
        if tnbrs:
            sc = board.coord(tnbrs[0])
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": sec["id"], "to": {"col": sc[0], "row": sc[1]}}}, 60)
            sec_id = sec["id"]
    # legalite du cast
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
    ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
               if a.get("abilityId") == ABILITY), {})
    fh = [x.get("targetId") for x in (ab.get("fromHere") or ab.get("targets") or [])]
    if tgt["id"] not in fh:
        return None
    return cid, tgt["id"], sec_id


def _cast_live_perhit(rpc, rid, cid, tid):
    cast = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ABILITY},
        "captureEvents": True}, 120)
    if not _ok(cast):
        return None, cast
    by_tgt = {}
    for act in (cast.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                by_tgt.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
    return by_tgt, cast


# ==================================================================== (1)+(2) core + native_factory

def test_flail_swing_live(live_session, rpc):
    """CAST LIVE bit-exact (per-coup == offline, melee flat) + A/B (tree==pipeline) + mono-cible + native_factory
    (attack ratio-constant vs ability desync). State-file UNIQUE -> dispose au teardown."""
    rid, sf, err = _build("777", A_UNITS, "90000")           # cibles armure 0 + PV hauts (survivent 3 coups)
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        placed = _advance_and_place(rpc, rid, board, "necroWarden", second_vis="necroOverlord")
        if placed is None:
            pytest.skip("geometrie melee castable non atteinte")
        cid, tid, sec_id = placed

        # capture PRE-cast + config
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        st = load_state(dv2, ob2, snap2, board=board)
        cfg_hits = _cfg_hits()
        bmin, bmax, pierce, hits = ability_attack_params(st, cid, "FlailSwing", "Power", ranged=False)
        assert hits == cfg_hits, (
            f"ability_attack_params rend nrOfHits={hits} != oracle "
            f"gameconfig.ability('FlailSwing').constants.nrOfHits={cfg_hits} (GetNumberConstant 0x2f)")
        # Le DISCRIMINANT native_factory (2) exige au moins 2 coups : a 1 coup, familles "attack" et
        # "ability" tirent la meme premiere valeur et le test ne separerait plus rien. On le dit fort
        # plutot que de laisser un vert non discriminant si la config etait re-equilibree a 1.
        assert cfg_hits >= 2, (
            f"setup NON discriminant : nrOfHits={cfg_hits} < 2 -> la desync native_factory commence au "
            f"coup 2, le volet (2) de ce test ne peut plus rougir")
        assert pierce == 40, f"pierce {pierce} != 40 (profil Power PiercingRatio)"
        sec_hp0 = None
        if sec_id is not None:
            se = st.get_entity(sec_id)
            sec_hp0 = se.get_component(HealthComponent).hp if se else None
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not _ok(s0):
            pytest.skip("dumpRng KO")

        # --- LIVE cast ---
        live, cast = _cast_live_perhit(rpc, rid, cid, tid)
        live_main = (live or {}).get(tid)
        if not live_main:
            pytest.skip(f"aucun degat live FlailSwing (cast={str(cast)[:160]})")

        # --- OFFLINE port (arbre DSL) ---
        stp = load_state(dv2, ob2, snap2, board=board); stp.rng = _seed_rng(s0)
        res = FlailSwingAbility().execute_behaviour(stp, cid, tid)
        assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
        assert res.get("informed_weapon") == "Power", f"InformWeapon(Power) non emis: {res.get('informed_weapon')}"
        tree_ph = (res.get("attack") or {}).get("per_hit") or []

        # --- A/B : arbre == sequence directe execute_ability_attack (attack), meme rng ---
        st_ab = load_state(dv2, ob2, snap2, board=board); st_ab.rng = _seed_rng(s0)
        direct = AttackDamageOperation.execute_ability_attack(
            st_ab, cid, tid, bmin, bmax, pierce, hits, damage_profile="Power", is_melee=True,
            is_attack_damage_op=True, force_overkill=True)
        print(f"\n[FLAIL] config [{bmin},{bmax}] pierce={pierce} hits={hits}")
        print(f"[FLAIL] live={live_main} port={tree_ph} A/B={(direct or {}).get('per_hit')}")

        # (1a) per-coup LIVE == port (melee flat -> bit-exact). Le NOMBRE de coups emis est CALCULE
        # (`attack_hits_with_modifiers` : constante +/- extraHits/malus/cover, plancher max(1,..)) ->
        # son oracle est le LIVE (port == natif). L'egalite avec la constante de config, elle, CONSTATE
        # qu'aucun modificateur de canal n'agit dans ce setup (sinon le bit-exact per-coup ci-dessous
        # comparerait des indices desalignes).
        assert len(tree_ph) == len(live_main), \
            f"nb de coups port {len(tree_ph)} != live {len(live_main)} (le port ne suit pas le natif)"
        assert len(live_main) == cfg_hits, (
            f"le natif emet {len(live_main)} coups != nrOfHits={cfg_hits} (oracle config) -> un "
            f"modificateur de canal de coups agit dans ce setup, le bit-exact per-coup n'est plus aligne")
        assert tree_ph == live_main, \
            f"port per_hit {tree_ph} != live {live_main} (melee flat board -> devrait etre bit-exact)"
        # (1b) A/B bit-exact
        assert tree_ph == (direct or {}).get("per_hit"), \
            f"arbre {tree_ph} != sequence directe execute_ability_attack {(direct or {}).get('per_hit')}"
        # (1c) mono-cible : le 2e ennemi voisin de la cible n'est PAS touche
        if sec_id is not None and sec_hp0 is not None:
            assert sec_id not in (live or {}), \
                f"2e ennemi t{sec_id} touche live -> splash inattendu (FlailSwing est mono-cible)"
            se_off = stp.get_entity(sec_id)
            assert se_off is None or se_off.get_component(HealthComponent).hp == sec_hp0, \
                "2e ennemi endommage offline -> l'arbre n'est pas mono-cible"

        # (2) native_factory : attack (2 tirages/coup) ratio-constant vs live ; ability (1 tirage/coup) desync
        st_abty = load_state(dv2, ob2, snap2, board=board); st_abty.rng = _seed_rng(s0)
        off_ability = (AttackDamageOperation.execute_ability_attack(
            st_abty, cid, tid, bmin, bmax, pierce, hits, damage_profile="Power", is_melee=True,
            is_attack_damage_op=False, force_overkill=True) or {}).get("per_hit") or []
        r_attack = [lm / om for lm, om in zip(live_main, tree_ph)]
        r_ability = [lm / om for lm, om in zip(live_main, off_ability)]
        print(f"[FLAIL] native_factory attack={off_ability and tree_ph} ability={off_ability} "
              f"r_attack={r_attack} r_ability={r_ability}")
        assert _spread(r_attack) < 0.01, \
            f"native_factory=attack : ratio live/offline NON constant {r_attack} (spread {_spread(r_attack):.4f})"
        assert _spread(r_ability) > 0.02, \
            f"native_factory=ability NE desynchronise PAS ({r_ability}, spread {_spread(r_ability):.4f})"
        assert _spread(r_ability) > 5 * _spread(r_attack), \
            f"attack spread {_spread(r_attack):.4f} vs ability spread {_spread(r_ability):.4f} : non discrimine"
        print("[FLAIL] OK : per-coup live==port bit-exact, A/B tree==pipeline, mono-cible, native_factory=attack")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


# ==================================================================== (2bis) native_factory 2e seed (offline)

def test_flail_swing_native_factory_second_seed(live_session, rpc):
    """DISCRIMINANT native_factory OFFLINE sur un 2e seed (tip #7) : sur une cible non-Resilient, la famille
    'attack' (2 tirages/coup) et la famille 'ability' (1 tirage/coup) DIVERGENT des le coup 2 (per_hit !=)
    -> prouve que le choix de factory CHANGE le resultat, et que FlailSwing utilise bien 'attack'."""
    rid, sf, err = _build("31337", A_UNITS, "90000")
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        placed = _advance_and_place(rpc, rid, board, "necroWarden")
        if placed is None:
            pytest.skip("geometrie melee castable non atteinte")
        cid, tid, _ = placed
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        st = load_state(dv2, ob2, snap2, board=board)
        bmin, bmax, pierce, hits = ability_attack_params(st, cid, "FlailSwing", "Power", ranged=False)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not _ok(s0):
            pytest.skip("dumpRng KO")
        st_a = load_state(dv2, ob2, snap2, board=board); st_a.rng = _seed_rng(s0)
        attack = (AttackDamageOperation.execute_ability_attack(
            st_a, cid, tid, bmin, bmax, pierce, hits, damage_profile="Power", is_melee=True,
            is_attack_damage_op=True, force_overkill=True) or {}).get("per_hit")
        st_b = load_state(dv2, ob2, snap2, board=board); st_b.rng = _seed_rng(s0)
        ability = (AttackDamageOperation.execute_ability_attack(
            st_b, cid, tid, bmin, bmax, pierce, hits, damage_profile="Power", is_melee=True,
            is_attack_damage_op=False, force_overkill=True) or {}).get("per_hit")
        cfg_hits = _cfg_hits()
        print(f"\n[FLAIL s2] oracle nrOfHits={cfg_hits} attack={attack} ability={ability}")
        assert cfg_hits >= 2, (
            f"setup NON discriminant : nrOfHits={cfg_hits} < 2 -> les deux familles ne peuvent pas "
            f"diverger (la desync commence au coup 2)")
        assert attack and ability and len(attack) == cfg_hits, \
            f"coups offline {len(attack or [])} != oracle constants.nrOfHits={cfg_hits}"
        assert attack[0] == ability[0], f"coup 1 devrait etre identique (meme 1er tirage): {attack} vs {ability}"
        assert attack != ability, \
            f"attack {attack} == ability {ability} : le choix de factory ne change RIEN (discriminant KO)"
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


# ==================================================================== (3) overkill flag vs Resilient

def test_flail_swing_overkill_resilient(live_session, rpc):
    """FLAG `alwaysOverkilled` : cible Resilient (custoKyrus) HP tune 10000 (total ~14400 < 2x seuil overkill)
    -> LIVE TUE a travers Resilient (sum des coups == PV full, PAS PV-1) ; le port (force_overkill=True) laisse
    la cible a 0 PV (morte) == live ; le CONTROL force_overkill=False laisse 1 PV (cap Resilient tient) = le
    flag est le SEUL ecart (bypass `ApplyResilientTraitDamageLimit`)."""
    HPN = 10000
    rid, sf, err = _build("777", "custoKyrus,necroWarden", str(HPN))
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        placed = _advance_and_place(rpc, rid, board, "custoKyrus")
        if placed is None:
            pytest.skip("custoKyrus non spawne / geometrie melee non atteinte")
        cid, tid, _ = placed

        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        st0 = load_state(dv2, ob2, snap2, board=board)
        te = st0.get_entity(tid)
        hp_pre = te.get_component(HealthComponent).hp if te else None
        if not hp_pre or hp_pre != HPN:
            pytest.skip(f"HP cible non tune a {HPN} (hp_pre={hp_pre})")
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not _ok(s0):
            pytest.skip("dumpRng KO")
        bmin, bmax, pierce, hits = ability_attack_params(st0, cid, "FlailSwing", "Power", ranged=False)

        # --- LIVE cast ---
        live, cast = _cast_live_perhit(rpc, rid, cid, tid)
        live_main = (live or {}).get(tid)
        if not live_main:
            pytest.skip(f"aucun degat live (cast={str(cast)[:160]})")
        live_sum = sum(live_main)
        print(f"\n[FLAIL ovk] hp_pre={hp_pre} live={live_main} sum={live_sum} config[{bmin},{bmax}]x{hits}")

        # LIVE tue a travers Resilient : sum == PV full (PAS PV-1). Si sum==hp_pre-1 -> Resilient a tenu (le
        # flag n'aurait PAS force l'overkill) ; si sum==hp_pre -> overkill force (kill). Garde-fou : total
        # sous le seuil overkill NATUREL (2x) pour que le flag soit le SEUL responsable du kill.
        assert live_sum <= hp_pre, f"sum live {live_sum} > PV {hp_pre} (impossible)"
        # borne haute config (max per-coup x 3) < 2x PV -> le kill n'est PAS un overkill naturel (>2x)
        assert bmax * hits < 2 * hp_pre, \
            f"degat max config {bmax * hits} >= 2x PV {2*hp_pre} : overkill NATUREL possible (scenario non discriminant)"
        assert live_sum == hp_pre, \
            f"live sum {live_sum} != PV full {hp_pre} : la cible Resilient a SURVECU live (le flag ne force pas l'overkill ?)"

        # --- OFFLINE port (force_overkill=True) : hp -> 0 (morte) == live ---
        stp = load_state(dv2, ob2, snap2, board=board); stp.rng = _seed_rng(s0)
        FlailSwingAbility().execute_behaviour(stp, cid, tid)
        hp_port = stp.get_entity(tid).get_component(HealthComponent).hp
        # --- CONTROL (force_overkill=False, meme rng) : hp -> 1 (survit, Resilient cap) ---
        stc = load_state(dv2, ob2, snap2, board=board); stc.rng = _seed_rng(s0)
        AttackDamageOperation.execute_ability_attack(
            stc, cid, tid, bmin, bmax, pierce, hits, damage_profile="Power", is_melee=True,
            is_attack_damage_op=True, force_overkill=False)
        hp_ctrl = stc.get_entity(tid).get_component(HealthComponent).hp
        print(f"[FLAIL ovk] port(force_overkill=True) hp->{hp_port} | control(False) hp->{hp_ctrl}")

        assert hp_port == 0, \
            f"port (force_overkill=True) laisse {hp_port} PV != 0 (devrait TUER a travers Resilient comme live)"
        assert hp_ctrl >= 1, \
            f"control (force_overkill=False) laisse {hp_ctrl} PV : Resilient devrait CAPER a >=1 (discriminant KO)"
        assert hp_port != hp_ctrl, \
            "port et control identiques -> le flag force_overkill ne change RIEN (le flag n'est pas discriminant)"
        print(f"[FLAIL ovk] OK : flag alwaysOverkilled porte -> tue a travers Resilient (live==port hp0), "
              f"control (sans flag) survit a {hp_ctrl} PV = le flag est le seul ecart")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass
