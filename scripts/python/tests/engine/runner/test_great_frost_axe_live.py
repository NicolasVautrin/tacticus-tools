"""GreatFrostAxe (actif 1089, spaceWulfen «Ulf», Space Wolves) PORT -> arbre DSL, confronte au LIVE.

`GreatFrostAxeAbility$$ExecuteBehaviour @1811e3500` (DECOMPILE, mirror 1:1, cf. `spacewolves.py`) =
    op_BitwiseAnd(
        AddEffect(0x11=Ice, source=stateRef, owner@0x148,
                  op_Addition(AdjacentTiles(TargetTiles@0x190), TargetTiles@0x190), <Nullable ZEROE>),  # glace
        If(IsAlive(target@0x178),
           AttackWithAttackDamage(caster@0x160, target@0x178, RandomAmount(minDmg,maxDmg),
                                  GetDamageProfile=Piercing, GetNumberConstant(0x2f)=nrOfHits=4)) )       # attaque

Patron « Stormcaller inverse » : glace la tuile de la cible + ring-1 PUIS attaque la CIBLE DIRECTE 4x
Piercing (mono-cible, ATTACK-family @180de9fb0 -- XREF from_address 1811e367f).

CE QUE CE TEST VALIDE (parties FIDELES du port) :
  (A) STRUCTURE : cast LIVE glace 7 tuiles (cible + ring-1) + degate la cible ; le port pose iced_tiles
      + emet main_attack.
  (B) ZONE GLACE : `iced_tiles` offline == {tuile cible} UNION {voisins marchables de la tuile cible}
      (== le selecteur `Union(AdjacentTiles(Target()), Tiles(Target()))`), et == le nb de tuiles glacees
      LIVE (events Effect_SourceId=caster).
  (C) NATIVE_FACTORY (discriminant #37/tip #2) : les ROLLS per-coup du port (native_factory="attack")
      sont, apres division par le facteur crit-Ice x1.5 (cf. RESIDU ci-dessous), EGAUX au LIVE sur TOUS
      les coups propres (ratio live/off CONSTANT = 1.5) -> meme sequence RNG -> famille ATTACK confirmee.
      La variante native_factory="ability" (1 tirage/coup) DIVERGE des le coup 2 (ratio non-constant) ->
      classification XREF validee par contraste.

RESIDU MAJEUR PINNE (NON PORTE, candidat fable-solver) : le bonus crit-sur-glace +50%
(`IceEffect.CreateEffectDamageBonusForAttack @180f44940`) applique a CHAQUE coup (i2 « The Crit Damage
bonus of the Ice is already applied for this attack ») rend le degat LIVE = EXACTEMENT 1.5x le degat
OFFLINE (mesure : DidCrit=0 partout, ratio ~1.5000). Ce +50% est un SOUS-SYSTEME effect-damage-bonus
PARTAGE jamais modelise offline (cf. docstring `spacewolves.great_frost_axe_tree`). Ce test PIN le ratio
(le fige a ~1.5) pour la tranche future ; il n'asserte PAS le bit-exact du DEGAT (seulement des ROLLS).

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

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.spacewolves import (GreatFrostAxeAbility, great_frost_axe_ice_tiles,
                                                 ICE_TILE)
from engine.entities.behaviours import op_and, If
from engine.entities.selectors import Target
from engine.entities.triggers import IsAlive
from engine.runner.abilities.behaviours import AttackWithAttackDamage, AddEffect, entities_from_state
from engine.dsl.effects import ExecutionContext

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                      # racine repo
CASTER_VIS = "spaceWulfen"
ABILITY = 1089
# plusieurs ennemis -> la bataille ne se termine pas au 1er kill ; necroOverlord (tanky) en tete de liste.
A_UNITS = "necroOverlord,necroWarden,necroWarden,necroWarden"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


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
    st = load_state(dec1, ob1, snap1)
    st.board = Board(bg["tiles"], adjacency="native_sym")
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
    """Confronte le port GreatFrostAxe au LIVE : (A) structure, (B) zone glace, (C) native_factory,
    + PIN du residu crit-Ice x1.5. State-file UNIQUE -> dispose au teardown."""
    state_file = ROOT / "data" / "rl-state" / f"gfa-test-{uuid.uuid4().hex[:8]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "31337", "--state-file", str(state_file),
         "--board", "MC1_67", "--roster", "1", "--p-units", CASTER_VIS, "--a-units", A_UNITS],
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
        # A3 : 4 coups emis (nrOfHits=GetNumberConstant(0x2f)=4)
        assert len(live_ph) == 4, f"attaque LIVE {len(live_ph)} coups != 4 (nrOfHits)"

        # ============ (B) OFFLINE zone glace + structure ============
        off_ph_attack, iced_off = _replay_per_hit(dec1, ob1, snap1, bg, s_cast, cid, eid, "attack")
        assert len(off_ph_attack) == 4, f"port {len(off_ph_attack)} coups != 4"
        # zone = tuile cible + voisins marchables (== Union(AdjacentTiles(Target()), Tiles(Target())))
        tpc = _by_id(dec1, eid).get("pos") or {}
        ttile = board.id_at(tpc.get("col"), tpc.get("row"))
        expected_zone = {ttile} | {n for n in board.neighbours(ttile) if board.walkable(n)}
        assert set(iced_off) == expected_zone, \
            f"zone glace offline {sorted(iced_off)} != cible+ring1 {sorted(expected_zone)}"
        # B2 : meme nombre de tuiles glacees offline et live
        assert len(iced_off) == len(live_ice_ids), \
            f"nb tuiles glacees offline {len(iced_off)} != live {len(live_ice_ids)}"

        # ============ (C) native_factory + PIN residu crit-Ice x1.5 ============
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
        # tous les coups propres sont non-crit (cc=0) : le residu crit-Ice n'est PAS un crit-roll
        assert all(int(live_ph[i]["crit"] or 0) == 0 for i in clean), \
            f"un coup propre a crit (attendu cc=0) : {live_ph}"
        # C1 (PIN residu) : le ratio live/offline("attack") = ~1.5 CONSTANT sur les coups propres.
        ratios_attack = [int(live_ph[i]["amt"]) / off_ph_attack[i] for i in clean if off_ph_attack[i]]
        for r in ratios_attack:
            assert abs(r - 1.5) <= 0.01, \
                f"ratio live/off(attack) {ratios_attack} != ~1.5 (residu crit-Ice +50%) ; live={live_ph} off={off_ph_attack}"
        # C2 (native_factory discriminant) : le ratio "attack" est PLUS CONSTANT que "ability".
        # famille ATTACK -> memes rolls que live (ratio constant 1.5) ; famille ABILITY (draw count different)
        # -> rolls divergents des le coup 2 -> ratio NON constant. On mesure la dispersion des ratios.
        def _spread(off_ph):
            rs = [int(live_ph[i]["amt"]) / off_ph[i] for i in clean if i < len(off_ph) and off_ph[i]]
            return (max(rs) - min(rs)) if len(rs) >= 2 else 0.0
        spread_attack = _spread(off_ph_attack)
        spread_ability = _spread(off_ph_ability)
        assert spread_attack <= 0.01, \
            f"dispersion ratio(attack) {spread_attack:.4f} > 0.01 -> rolls attack != live (native_factory ?)"
        # discriminant : "ability" doit etre STRICTEMENT plus disperse (rolls divergents des le coup >=2).
        # (si les rolls etaient identiques attack==ability, la classification serait indistinguable ; ce test
        #  echoue alors -> signale qu'il faut un autre discriminant, cf. tip #2.)
        assert spread_ability > spread_attack, \
            (f"native_factory NON discrimine : spread(attack)={spread_attack:.4f} "
             f"spread(ability)={spread_ability:.4f} -- attendu ability strictement plus disperse "
             f"(rolls divergents). off_attack={off_ph_attack} off_ability={off_ph_ability} live={live_ph}")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            state_file.unlink()
        except Exception:
            pass
