#!/usr/bin/env python
"""Validation #47 -- buffs RANGED du caster sur les attaques d'ABILITY (famille ATTACK) + gate famille.

FIX #47 (execute_ability_attack, damage.py) : threading `is_ranged` (derive d'is_melee) +
`trigger_ability_type` (AbilityOrEffect du coup) dans la collecte attacker-modifiers, GATE FAMILLE
(threades pour la famille ATTACK seulement -- l'ABILITY-family a des mods attaquant VIDES, #45f).
Effets concernes : `IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier` (+25% ranged,
x2 = +50% si `TriggeringAbilityIs(0x3ec=1004 MortisRound)`), `RangedSpecialistEffect IdunBattle.Entities.Effects.Loki.RangedSpecialistEffect$$CreateEffectDamageBonusForAttack`
(+33% ranged), + feuilles positionnelles deja gate-famille (#45f : elevation/trench).

CAS (1 build par cas, cible tanky 300000 pour survivre, caster JAMAIS deplace = gate no-move
HeavyWeapon intact, cible DEPLACEE a portee par applyAction) :
  plasma-flat : PlasmaCannon (1150, darkaTerminator HeavyWeapon, 3x Plasma ranged, famille ATTACK,
                cible elev == caster) -> attendu x1.25 ; ASSERT hpDelta live == offline + mti egal.
  plasma-high : idem, cible elev < caster (spawn elev 3, cible elev 2) -> attendu x1.25 x 1.5
                elevation = x1.875 (2e datapoint discriminant : une variable = la relation d'elev).
  cherub      : ArmoriumCherub (1014, adeptRetributor HeavyWeapon, 4x Flame ranged range 2,
                famille ATTACK) -> attendu x1.25 par coup ; ASSERT bit-exact.
  leech       : SpiritLeech (1104, tyranNeurothrope RangedSpecialist, 1x Psychic ranged, famille
                **ABILITY** IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage -> AbilityDamageOperation) -> les mods ATTAQUANT sont VIDES
                (#45f) : le +33% ne doit s'appliquer NI live NI offline (datapoint adversarial du
                gate famille -- un threading non-gate rendrait l'offline x1.33 TROP HAUT).

MESURE : hpDelta cible (changes du cast) vs replay offline meme rng (execute_behaviour), + delta
mti (consommation rng identique). State-files UNIQUES. ASCII only.
Usage : python probe_47_ranged_ability_buffs.py [--case plasma-flat|plasma-high|cherub|leech|all]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import hexgeo  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

CASES = {
    #  case         caster_vis          ability_id  type   range  elev_relation
    "plasma-flat": ("darkaTerminator",  "PlasmaCannon",  1150, 3, "flat"),
    "plasma-high": ("darkaTerminator",  "PlasmaCannon",  1150, 3, "high"),
    "cherub":      ("adeptRetributor",  "ArmoriumCherub", 1014, 2, "flat"),
    "leech":       ("tyranNeurothrope", "SpiritLeech",   1104, 3, "flat"),
    # mortis-free = CONTRE-CAS du knockback #47 (probe_mortis_round C = push BLOQUE bord ->
    # +ceil(maxHealth x 10%)) : cible placee avec tuile DERRIERE LIBRE -> push REUSSIT -> AUCUN
    # knockback (ni live ni offline). Garde anti-SUR-application du port displace.py.
    "mortis-free": ("ultraEliminatorSgt", "MortisRound", 1004, 3, "behind-free"),
}
# cible VANILLA (unit_map vanilla-target) SANS regen/mecanique parasite : necroWarden (LivingMetal)
# regenerait full au tick de fin de tour DANS le stream du cast (PlasmaCannon/SpiritLeech finissent
# le tour -> auto-advance -> le delta lu retombait a 0 ; ArmoriumCherub « does not end turn » y
# echappait). astraBullgryn = tanky, aucun trait/ability de modif de degat (mais BigTarget = non
# deplacable -> pour le contre-cas PUSH (mortis-free) la cible est astarCyrus, vanilla DEPLACABLE).
TARGET_VIS = "astraBullgryn"
# mortis-free : cible DEPLACABLE du pool rank-17 (astraBullgryn est BigTarget) ; necroWarden est
# LivingMetal (regen fin de tour) -> la mesure live prend min(serie RH) = etat POST-attaque AVANT
# le tick de regen (MortisRound finit le tour -> le tick tombe DANS le stream du cast).
TARGET_BY_CASE = {"mortis-free": "necroWarden"}


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _hp_of(ob, eid):
    """HP courant d'une unite depuis observeBattle (etat PRE-cast ; observeBattle peut etre STALE
    juste apres un applyAction -> la serie POST-cast vient des EVENTS, cf. _live_rh_series)."""
    for u in (ob.get("units") or []):
        if u.get("id") == eid or u.get("squadId") == eid:
            for k in ("hp", "health", "remainingHealth"):
                if u.get(k) is not None:
                    return int(u[k])
    return None


def _live_rh_series(cast, eid):
    """Serie des `UnitStats_RemainingHealth` de la cible dans les events du cast (1 entree par coup
    encaisse) — la SEULE source fiable du degat live per-coup (observeBattle est stale post-cast,
    et les casts sans push n'emettent pas de `changes` hp)."""
    out = []
    for act in (cast.get("actions") or []):
        for ev in (act.get("events") or []):
            if ev.get("kind") != "action" or ev.get("entity") != eid:
                continue
            try:
                tags = json.loads(ev.get("tags") or "{}")
            except Exception:
                continue
            if "UnitStats_RemainingHealth" in tags:
                out.append(int(tags["UnitStats_RemainingHealth"]))
    return out


def run_case(sid, case: str) -> bool:
    caster_vis, ability_id, ability_type, rng_range, relation = CASES[case]
    target_vis = TARGET_BY_CASE.get(case, TARGET_VIS)
    state = ROOT / "logs" / "runners" / f"p47-{case}-{uuid.uuid4().hex[:6]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "909", "--state-file", str(state),
         "--board", "MC1_67", "--roster", "1", "--p-units", caster_vis,
         "--a-units", f"{target_vis},necroDestroyer", "--hp-target", "300000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print(f"[47:{case}] BUILD KO: {(proc.stderr or proc.stdout or '')[-300:]}")
        return False
    rid = json.loads(state.read_text())["runnerId"]
    ok = False
    try:
        from engine.entities.pathfinding.board import Board
        from engine.runner.snapshot import load_state
        from engine.runner.prng import IntBasedMersenneTwister
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print(f"[47:{case}] boardGraph KO"); return False
        board = Board(bg["tiles"], adjacency="native_sym")
        # avancer jusqu'au tour du CASTER (patron probe_45f) : un cast hors-tour est SIMULE puis
        # ROLLBACK par le runner (action ok:true mais mutated:false, degats reverts dans les events).
        dec0 = caster = None
        for _ in range(16):
            dec0 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            caster = _find(dec0, caster_vis)
            if caster is None:
                print(f"[47:{case}] caster absent"); return False
            if caster.get("owner") == dec0.get("currentPlayer"):
                break
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        else:
            print(f"[47:{case}] tour caster jamais atteint"); return False
        target = _find(dec0, target_vis)
        if target is None:
            print(f"[47:{case}] cible absente"); return False
        cid, eid = caster["id"], target["id"]
        third = next((u for u in (dec0.get("units") or [])
                      if u.get("alive") and u["id"] not in (cid, eid)), None)
        cpos = (caster["pos"]["col"], caster["pos"]["row"])
        tiles = {(t["col"], t["row"]): t for t in bg["tiles"]}
        ce = tiles.get(cpos, {}).get("elevation") or 0
        # tuile cible : walkable, libre, dist<=range du SPAWN caster (caster ne bouge JAMAIS :
        # gate no-move de HeavyWeapon), relation d'elevation demandee. `behind-free` (mortis-free) =
        # cible ADJACENTE au spawn avec la tuile DERRIERE (opposee au caster) LIBRE -> push reussit.
        dest = None
        if relation == "behind-free":
            from engine.runner.operations.displace import _dir_index, _step
            for tid in board.neighbours(board.id_at(*cpos)):
                if not board.walkable(tid):
                    continue
                tc = board.coord(tid)
                di = _dir_index(cpos[0], cpos[1], tc[0], tc[1])
                if di is None:
                    continue
                bc, br = _step(tc[0], tc[1], di)
                bt = board.id_at(bc, br)
                if bt is not None and board.walkable(bt) and (bc, br) != cpos:
                    dest = tc; break
        else:
            for (c, r), t in sorted(tiles.items()):
                if not t.get("walkable") or (c, r) == cpos:
                    continue
                d = hexgeo.distance(cpos, (c, r))
                if not d or d > rng_range:
                    continue
                e = t.get("elevation") or 0
                if relation == "flat" and e == ce:
                    dest = (c, r); break
                if relation == "high" and e < ce:
                    dest = (c, r); break
        if dest is None:
            print(f"[47:{case}] aucune tuile {relation} a portee {rng_range} du spawn {cpos} (elev {ce})")
            return False
        if third is not None:                       # park le 3e LOIN (0 splash / pas d'adjacence parasite)
            far = next((tt for tt in sorted(board.by_id) if board.walkable(tt)
                        and hexgeo.distance(board.coord(tt), cpos) > 5
                        and hexgeo.distance(board.coord(tt), dest) > 3), None)
            if far is not None:
                fc = board.coord(far)
                _r(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": third["id"], "to": {"col": fc[0], "row": fc[1]}}}, 90)
        _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": eid, "to": {"col": dest[0], "row": dest[1]}}}, 90)
        dec1 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob1 = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap1 = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
        s_cast = _r(sid, "dumpRng", {"runnerId": rid}, 30)
        te = tiles.get(dest, {}).get("elevation") or 0
        print(f"[47:{case}] caster@{cpos} elev={ce} (spawn, NON deplace)  cible@{dest} elev={te} "
              f"dist={hexgeo.distance(cpos, dest)}")
        hp_live_before = _hp_of(ob1, eid)
        cast = _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": eid, "abilityType": ability_type},
            "captureEvents": True}, 120)
        s_post = _r(sid, "dumpRng", {"runnerId": rid}, 30)
        rh = _live_rh_series(cast, eid)
        # min(serie) = etat POST-degats AVANT tout tick de heal/regen de fin de tour glisse dans le
        # meme stream (ex. LivingMetal quand l'ability finit le tour) ; series decroissante -> == last.
        live = (hp_live_before - min(rh)) if (hp_live_before is not None and rh) else None
        live_per_hit = [a - b for a, b in zip([hp_live_before] + rh, rh)] if (rh and
                        hp_live_before is not None) else []
        # ---- replay OFFLINE meme rng ----
        st = load_state(dec1, ob1, snap1); st.board = board
        rng = IntBasedMersenneTwister()
        rng.mt = list(s_cast["mt"]); rng.mti = s_cast["mti"]
        st.rng = rng
        from engine.runner.components import HealthComponent
        e2 = st.get_entity(eid)
        h2 = e2.get_component(HealthComponent) if e2 is not None else None
        hp_before = h2.hp if h2 is not None else None
        if case.startswith("plasma"):
            from engine.runner.abilities.darkangels import PlasmaCannonAbility
            res = PlasmaCannonAbility().execute_behaviour(st, cid, eid)
        elif case == "cherub":
            from engine.runner.abilities.loki.strike import ArmoriumCherubAbility
            res = ArmoriumCherubAbility().execute_behaviour(st, cid, eid)
        elif case == "mortis-free":
            from engine.runner.abilities.ultramarines import MortisRoundAbility
            res = MortisRoundAbility().execute_behaviour(st, cid, eid)
        else:
            from engine.runner.abilities.loki.strike import SpiritLeechAbility
            res = SpiritLeechAbility().execute_behaviour(st, cid, eid)
        if case == "mortis-free":                     # contre-cas : push REUSSI => AUCUN knockback
            p = (res or {}).get("push") or {}
            if not p.get("moved") or p.get("knockback"):
                print(f"[47:{case}] FAIL push={p} (attendu moved=True sans knockback)")
                return False
        off = (hp_before - h2.hp) if (hp_before is not None and h2 is not None
                                      and h2.hp is not None) else None
        m = (res or {}).get("main_attack") or {}
        print(f"[47:{case}] LIVE hpDelta={live} per_hit={live_per_hit}  OFFLINE hpDelta={off} "
              f"per_hit={m.get('per_hit')} rolls={m.get('rolls')} crits={m.get('crits')}")
        print(f"[47:{case}] mti live {s_cast.get('mti')}->{s_post.get('mti')}  offline->{rng.mti}")
        if live is None or off is None:
            print(f"[47:{case}] FAIL mesure manquante")
        elif live != off:
            print(f"[47:{case}] FAIL hpDelta offline {off} != live {live}")
        elif s_post.get("mti") is not None and rng.mti != s_post.get("mti"):
            print(f"[47:{case}] FAIL conso rng offline mti={rng.mti} != live mti={s_post.get('mti')}")
        else:
            print(f"[47:{case}] PASS bit-exact (hpDelta {live}, mti {rng.mti})")
            ok = True
    finally:
        _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="all", choices=[*CASES.keys(), "all"])
    args = ap.parse_args()
    sid = _resolve_session()
    cases = list(CASES.keys()) if args.case == "all" else [args.case]
    results = {c: run_case(sid, c) for c in cases}
    print("\n==== RESULT ====")
    bad = [c for c, v in results.items() if not v]
    for c, v in results.items():
        print(("PASS " if v else "FAIL ") + c)
    return 2 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
