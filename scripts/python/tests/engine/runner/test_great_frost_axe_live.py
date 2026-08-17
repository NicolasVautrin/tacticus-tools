"""GreatFrostAxe (actif 1089, spaceWulfen «Ulf», Space Wolves) PORT -> arbre DSL, confronte au LIVE.

`GreatFrostAxeAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.GreatFrostAxeAbility$$ExecuteBehaviour` (DECOMPILE, mirror 1:1, cf. `spacewolves.py`) =
    op_BitwiseAnd(
        AddEffect(0x11=Ice, source=stateRef, owner@0x148,
                  op_Addition(AdjacentTiles(TargetTiles@0x190), TargetTiles@0x190), <Nullable ZEROE>),  # glace
        If(IsAlive(target@0x178),
           AttackWithAttackDamage(caster@0x160, target@0x178, RandomAmount(minDmg,maxDmg),
                                  GetDamageProfile=Piercing, GetNumberConstant(0x2f)=nrOfHits)) )         # attaque

Patron « Stormcaller inverse » : glace la tuile de la cible + ring-1 PUIS attaque la CIBLE DIRECTE
nrOfHits x Piercing (mono-cible, ATTACK-family IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage -- XREF from_address 1811e367f).

ORACLE DU NOMBRE DE COUPS (#96 / lot A) : le natif LIT la valeur telle quelle
(`AbilityConfiguration.GetNumberConstant(cfg, 0x2f)`, aucune formule) -> valeur BRUTE, oracle = la CONFIG
`gameconfig.ability("GreatFrostAxe").constants.nrOfHits` (helper `_cfg_hits`), jamais un litteral. Le nb de
coups EMIS, lui, est CALCULE (`attack_hits_with_modifiers`, plancher `max(1, ...)`) -> oracle = le LIVE :
port == natif, et l'egalite avec la constante CONSTATE l'absence de modificateur de canal dans ce setup.

CE QUE CE TEST VALIDE (parties FIDELES du port) :
  (A) STRUCTURE : cast LIVE glace 7 tuiles (cible + ring-1) + degate la cible ; le port pose iced_tiles
      + emet main_attack.
  (B) ZONE GLACE : `iced_tiles` offline == {tuile cible} UNION {voisins marchables de la tuile cible}
      (== le selecteur `Union(AdjacentTiles(Target()), Tiles(Target()))`), et == le nb de tuiles glacees
      LIVE (events Effect_SourceId=caster).
  (C) DEGAT BIT-EXACT par coup propre (live == offline, native_factory="attack") ; la variante
      native_factory="ability" (1 tirage/coup) DIVERGE des le coup 2 (discriminant #37/tip #2) ->
      classification XREF validee par contraste.

RESIDU x1.5 RESOLU (#45f, fable) : l'ex-« bonus crit-sur-glace +50% » etait un ARTEFACT DE CONFUSION —
la vraie cause etait le bonus d'ELEVATION (`Damage.ElevationBonus`=50, feuille du builder PARTAGE
`IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction`, gate elev(att) > elev(cible), AUCUN gate
normale/ability) que le vecteur offline `execute_ability_attack` n'appliquait pas ; ce test move sur
`aiAttackRank ranked[0]` qui PREFERE le surplomb sur MC1_67 -> ratio 1.5 systematique. PROUVE par
sonde discriminante (probe_45f_gfa_elevation : high=1.5x, flat/low=bit-exact pre-fix ; 16/16 coups
bit-exact post-fix). Le VRAI bonus crit-sur-Ice (`IdunBattle.Entities.Effects.IceEffect$$CreateEffectDamageBonusForAttack` = +PercentageOf(GetStat(10), IceCritDmgBonusPct=25) par coup CRIT vs cible gelee
non-Immune) vaut 0 ici (cd=0) et est porte + valide a part (probe --case crit : +175 = floor(700x25%),
4/4 bit-exact).

Lit l'etat LIVE (pas de tuile/valeur hardcodee), state-file UNIQUE, dispose au teardown. ASCII only.
Skip propre si session/geometrie/cast KO.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import gameconfig as GC
from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.spacewolves import (GreatFrostAxeAbility, great_frost_axe_ice_tiles,
                                                 ICE_TILE)
from engine.entities.behaviours import op_and, If
from engine.entities.selectors.accessors import Target
from engine.entities.triggers import IsAlive
from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.runner.abilities.behaviours.effects import AddEffect
from engine.dsl.effects import ExecutionContext

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                      # racine repo
CASTER_VIS = "spaceWulfen"
ABILITY = 1089
# plusieurs ennemis -> la bataille ne se termine pas au 1er kill ; necroOverlord (tanky) en tete de liste.
A_UNITS = "necroOverlord,necroWarden,necroWarden,necroWarden"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _cfg_hits(key: str = "nrOfHits") -> int:
    """ORACLE du nb de coups = la CONSTANTE de config de GreatFrostAxe, PAS un litteral.
    `IdunBattleLogic.Entities.Abilities.Active.Loki.GreatFrostAxeAbility$$ExecuteBehaviour` passe
    `hits = IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(cfg, 0x2f)` a
    `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` : valeur BRUTE (aucune formule), donc
    l'oracle est `gameconfig.ability("GreatFrostAxe").constants[<key>]`."""
    c = (GC.ability("GreatFrostAxe") or {}).get("constants") or {}
    v = c.get(key)
    assert v is not None, (f"oracle introuvable : constants.{key} absent de gameconfig pour GreatFrostAxe "
                           f"(GetNumberConstant(0x2f) non resolvable offline)")
    return int(v)


def _by_id(dec, uid):
    return next((u for u in (dec.get("units") or []) if u.get("id") == uid), None)


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _tags(e):
    tg = e.get("tags")
    return (json.loads(tg) if isinstance(tg, str) else tg) or {}


def _replay_per_hit(dec1, ob1, snap1, bg, s_cast, cid, eid, native_factory):
    """Rejoue l'arbre GreatFrostAxe (avec `native_factory` donne) depuis l'etat POST-move seede -> per_hit."""
    st = load_state(dec1, ob1, snap1, board=Board(bg["tiles"], adjacency="native_sym"))
    st.rng = _seed_rng(s_cast)
    tgt = Target()
    ice = AddEffect(ICE_TILE, "Ice", great_frost_axe_ice_tiles(), duration_rounds=None)
    attack = AttackWithAttackDamage(tgt, "GreatFrostAxe", "Piercing", is_melee=True,
                                    native_factory=native_factory, ability_type=ABILITY)
    tree = op_and(ice, If(IsAlive(tgt), attack))
    ectx = ExecutionContext(state=st, rng=st.rng)
    tree.execute(entities_from_state(st, cid, eid), ectx)
    ma = next((p.get("attack") for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
    iced = [p.get("target") for n, p in ectx.emitted
            if n == "AddEffect" and p.get("effect_type") == ICE_TILE and p.get("placed")]
    return (ma or {}).get("per_hit") or [], iced


def test_great_frost_axe_live(live_session, rpc):
    """Confronte le port GreatFrostAxe au LIVE : (A) structure, (B) zone glace, (C) degat BIT-EXACT
    par coup (residu x1.5 resolu #45f = elevation) + discriminant native_factory. State-file UNIQUE ->
    dispose au teardown."""
    state_file = ROOT / "logs" / "runners" / f"gfa-test-{uuid.uuid4().hex[:8]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "31337", "--state-file", str(state_file),
         "--board", "MC1_67", "--roster", "1", "--p-units", CASTER_VIS, "--a-units", A_UNITS,
         # Confonds NEUTRALISES AU BUILD (#419-r6). ARBITRAGE : le volet (C) confronte le degat
         # BIT-EXACT PAR COUP de l'ability ; un crit y ajoute un facteur hors axe et le fichier ne
         # sait qu'en skipper -- depuis que le defaut equipe, il tombait a 0 passed / 1 skipped
         # (inerte, garde #455). Les QUATRE faces : `--crit`/`--block-player` n'epinglent que les
         # p-units, `--crit-target`/`--block-target` que les a-units.
         "--crit", "0,0", "--crit-target", "0,0",
         "--block-target", "0,0", "--block-player", "0,0"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        pytest.skip(f"build runner KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    rid = json.loads(state_file.read_text())["runnerId"]
    try:
        # --- avance jusqu'a un MON-tour ou GreatFrostAxe atteint une tuile d'attaque (move inclus) ---
        cast_ctx = None
        for _ in range(24):
            dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            if not _ok(dec):
                pytest.skip("decisionView KO")
            caster = _find(dec, CASTER_VIS)
            if caster is None:
                break
            if caster.get("owner") == dec.get("currentPlayer"):
                at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster["id"],
                                            "abilityType": ABILITY}, 90)
                ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                           if a.get("abilityId") == ABILITY), {})
                for t in (ab.get("targets") or []):
                    tid = t.get("targetId")
                    if _by_id(dec, tid) is None:
                        continue
                    ar = rpc("aiAttackRank", {"runnerId": rid, "unitId": caster["id"],
                                              "targetId": tid, "abilityType": ABILITY, "maxRank": 8}, 90)
                    ev = next((e for e in ((ar.get("units") or [{}])[0].get("evals") or [])
                               if e.get("targetId") == tid), None)
                    ranked = (ev or {}).get("ranked") or []
                    if ranked:
                        cast_ctx = (caster, _by_id(dec, tid), ranked[0])
                        break
                if cast_ctx:
                    break
            adv = rpc("aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 1}, 120)
            if not _ok(adv):
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        if cast_ctx is None:
            pytest.skip("aucun tour castable atteint (geometrie/tour)")
        caster, target, atk_tile = cast_ctx
        cid, eid = caster["id"], target["id"]

        # move LIVE sur la tuile d'attaque, puis capture POST-move (== l'etat au cast)
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cid, "to": {"col": atk_tile["col"], "row": atk_tile["row"]}}}, 90)
        dec1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob1 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap1 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if snap1 is None or not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("combatSnapshot/boardGraph indispo")
        s_cast = rpc("dumpRng", {"runnerId": rid}, 30)
        if not _ok(s_cast):
            pytest.skip("dumpRng indispo (rebuild+reinject hooks ?)")

        # hp cible offline (pour detecter le coup clampe par la mort)
        st0 = load_state(dec1, ob1, snap1)
        te = st0.get_entity(eid)
        hp_tgt = te.get_component(HealthComponent).hp if (te and te.get_component(HealthComponent)) else None
        board = Board(bg["tiles"], adjacency="native_sym")

        # ============ (A) LIVE cast ============
        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": eid, "abilityType": ABILITY},
            "captureEvents": True}, 120)
        assert _ok(cast), f"cast GreatFrostAxe non applique: {str(cast)[:200]}"
        a0 = (cast.get("actions") or [{}])[0]
        live_ph = []
        live_ice_ids = set()
        for e in (a0.get("events") or []):
            tg = _tags(e)
            if tg.get("Target_Id") == eid and "Amount" in tg and tg.get("Active_Ability_Type") == ABILITY:
                live_ph.append({"amt": tg.get("Amount"), "crit": tg.get("Attack_DidCrit"),
                                "blk": tg.get("Attack_DidBlock")})
            if tg.get("Effect_Id") is not None and tg.get("Effect_SourceId") == cid:
                live_ice_ids.add(tg.get("Effect_Id"))
        live_total = None
        for ch in (a0.get("changes") or []):
            if ch.get("squadId") == eid and ch.get("hpDelta") is not None:
                live_total = -int(ch["hpDelta"])
        # A1 : la cible a subi des degats
        assert live_total is not None and live_total > 0, f"cible non degatee (dmg={live_total})"
        # A2 : la glace a ete posee (au moins la tuile cible)
        assert len(live_ice_ids) >= 1, "aucune tuile glacee live (Effect_SourceId=caster)"
        # A3 : le natif emet nrOfHits coups (oracle CONFIG : GetNumberConstant(0x2f) est lu tel quel).
        # Le nb REELLEMENT emis est calcule (modificateurs de canal) -> cette egalite CONSTATE aussi
        # qu'aucun modificateur n'agit ici, condition du bit-exact per-coup indice-par-indice en (C).
        cfg_hits = _cfg_hits()
        print(f"\n[GFA] oracle constants.nrOfHits={cfg_hits}")
        assert len(live_ph) == cfg_hits, (
            f"attaque LIVE {len(live_ph)} coups != oracle "
            f"gameconfig.ability('GreatFrostAxe').constants.nrOfHits={cfg_hits}")

        # ============ (B) OFFLINE zone glace + structure ============
        off_ph_attack, iced_off = _replay_per_hit(dec1, ob1, snap1, bg, s_cast, cid, eid, "attack")
        # oracle LIVE du cote CALCULE (le port doit suivre le natif) + oracle CONFIG de la constante
        assert len(off_ph_attack) == len(live_ph), \
            f"nb de coups port {len(off_ph_attack)} != live {len(live_ph)} (le port ne suit pas le natif)"
        assert len(off_ph_attack) == cfg_hits, \
            f"port {len(off_ph_attack)} coups != oracle constants.nrOfHits={cfg_hits}"
        # zone = tuile cible + voisins marchables (== Union(AdjacentTiles(Target()), Tiles(Target())))
        tpc = _by_id(dec1, eid).get("pos") or {}
        ttile = board.id_at(tpc.get("col"), tpc.get("row"))
        expected_zone = {ttile} | {n for n in board.neighbours(ttile) if board.walkable(n)}
        assert set(iced_off) == expected_zone, \
            f"zone glace offline {sorted(iced_off)} != cible+ring1 {sorted(expected_zone)}"
        # B2 : meme nombre de tuiles glacees offline et live
        assert len(iced_off) == len(live_ice_ids), \
            f"nb tuiles glacees offline {len(iced_off)} != live {len(live_ice_ids)}"

        # ============ (C) DEGAT BIT-EXACT (residu x1.5 RESOLU #45f) + native_factory ============
        off_ph_ability, _ = _replay_per_hit(dec1, ob1, snap1, bg, s_cast, cid, eid, "ability")
        # coups PROPRES = non clampes par la mort (somme live cumulee < hp cible)
        clean = []
        run = 0
        for i, lh in enumerate(live_ph):
            amt = int(lh["amt"] or 0)
            if hp_tgt is not None and run + amt >= hp_tgt:
                break                                       # ce coup (et les suivants) sont clampes
            clean.append(i); run += amt
        if len(clean) < 2:
            pytest.skip(f"pas assez de coups propres non clampes ({clean}, hp {hp_tgt}) -- cible trop fragile")
        # tous les coups propres sont non-crit (cc=0) : aucun crit-roll dans ce scenario
        assert all(int(live_ph[i]["crit"] or 0) == 0 for i in clean), \
            f"un coup propre a crit (attendu cc=0) : {live_ph}"
        # C1 (#45f) : degat BIT-EXACT par coup propre — l'elevation (feuille positionnelle du builder
        # partage IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction) est desormais appliquee au vecteur ability (`execute_ability_attack`),
        # que ranked[0] soit en surplomb ou non. Ex-PIN ~1.5 (artefact elevation) SUPPRIME.
        for i in clean:
            assert int(live_ph[i]["amt"]) == off_ph_attack[i], \
                (f"hit{i} NON bit-exact : live={live_ph[i]['amt']} off={off_ph_attack[i]} "
                 f"(live_all={[h['amt'] for h in live_ph]} off_all={off_ph_attack})")
        # C2 (native_factory discriminant, tip #2) : la famille ABILITY (1 tirage/coup) doit DIVERGER
        # du live des le coup 2 (draw count different), la famille ATTACK etant bit-exacte (C1).
        div_ability = any(i < len(off_ph_ability) and off_ph_ability[i] != int(live_ph[i]["amt"])
                          for i in clean)
        assert div_ability, \
            (f"native_factory NON discrimine : off_ability == live sur les coups propres "
             f"off_ability={off_ph_ability} live={[h['amt'] for h in live_ph]} -- cf. tip #2")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            state_file.unlink()
        except Exception:
            pass
