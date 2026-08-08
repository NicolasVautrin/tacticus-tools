"""#567 -- `1057 GrotTank` (`orksBigMek`) : NATIF vs PORT, etage par etage.

CE QUE CE PROBE MESURE, ET POURQUOI CES ETAGES-LA. `IdunBattleLogic.Entities.Abilities.Active.
Loki.GrotTankAbility$$ExecuteBehaviour` n'a qu'UN `AActiveAbility.Execute`, mais il compose CINQ
mecaniques dans les options de spawn. Un critere unique ("un summon est apparu") serait VERT sur
un port qui n'en porterait qu'une seule -- en particulier sur un port qui OUBLIERAIT l'override de
PV, puisque le summon apparaitrait quand meme, avec les PV du `summonHp` de config.

  E1 SPAWN     : une unite NEUVE apparait, sur la tuile CIBLEE (`Spawn(Caster@0x48, Target@0x60)`).
  E2 PV        : `StatModifierFormula(Health, Initial, TankHealth(), null)` -- l'etage NEUF.
                 `TankHealth = summonHp + RoundsStarted(Caster) x extraHp`. Le probe imprime les
                 TROIS grandeurs (natif, port, et les deux hypotheses concurrentes `summonHp` seul
                 et `summonHp + extraHp`) : c'est ce qui rend l'etage DISCRIMINANT. Il n'est
                 informatif que si `turnsStarted(caster) >= 1`, ce que le probe VERIFIE et DIT.
  E3 STATS     : Attack / FixedArmor du tank = `summonDmg` / `summonArmor`
                 (`WithStatsFromConfig`), volet LITTERAL, deja porte -- temoin de non-regression :
                 si l'override de E2 debordait sur les autres stats, c'est ici qu'on le verrait.
  E4 ON-APPEAR : `PerformAIAttackFromCurrentPosition(ActiveTarget@0x68)` -- le tank tire des son
                 apparition, SANS bouger. Mesure = les deltas de PV ENNEMIS du cast, cote a cote
                 avec les `attacks` rendus par le port.
  E5 #291      : le tank n'entre PAS dans `decisionView.toActivate` (`TriggerSpawnedUnitBehaviours`
                 -> `FinishUnitTurn(spawned, isTerminated: true)`). C'est la REPONSE CORRECTE du
                 natif, pas un trou -- on la mesure pour qu'un futur port ne la "repare" pas.

Le port est execute sur l'etat AVANT (charge par `load_state`), le natif sur le meme etat via
`applyAction` -- les deux verdicts sont imprimes cote a cote.

Usage (depuis scripts/python) :
    python probe_567_grot_tank.py --state-file <ABSOLU> [--board MC1_67] [--seed 777]
                                  [--turns 12] [--keep]

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
CASTER = "orksBigMek"
ENEMIES = "orksNob,orksRuntherd,tyranWingedPrime"
GROT_TANK = 1057
ABILITY_ID = "GrotTank"


def sid() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60):
    r = requests.post(f"{HOST}/api/scripts/{s}/rpc",
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def build(state_file: Path, board: str, seed: str, caster_pos: str | None,
          enemy_pos: str | None) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    if state_file.exists():
        state_file.unlink()
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
           "--p-units", CASTER, "--a-units", ENEMIES,
           "--state-file", str(state_file)]
    # PLACEMENT CRAFTE (cf. runner.md, "tu as la maitrise totale du setup") : sans lui, les spawn
    # points de MC1_67 mettent 7 hex entre le Big Mek et l'ennemi le plus proche -> le Grot Tank
    # apparait HORS de sa portee (3) et l'etage E4 reste INERTE, ce qui n'est pas une mesure.
    if caster_pos:
        cmd += ["--place", "%s:%s" % (CASTER, caster_pos)]
    if enemy_pos:
        cmd += ["--a-place", "orksNob:%s" % enemy_pos]
    proc = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parent),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise SystemExit("[567] build KO: %s" % ((proc.stderr or proc.stdout or "")[-800:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def live_units(s: int, rid: int) -> list:
    ob = rpc(s, "observeBattle", {"runnerId": rid}, 40) or {}
    return list(ob.get("units") or [])


def load_port_state(s: int, rid: int):
    from engine.entities.pathfinding.board import Board
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(s, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc(s, "dumpRng", {"runnerId": rid}, 30)
    st = load_state(dec, ob, snap, board=board)
    if isinstance(s0, dict) and s0.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        st.rng = rng
    return st, board


def positions(units: list) -> dict:
    return {u.get("squadId"): (u.get("visualId"), u.get("col"), u.get("row"),
                               bool(u.get("isDead")), u.get("hp"), u.get("maxHp"))
            for u in units}


def grot_tank_targets(s: int, rid: int, uid: int) -> list:
    """Les tuiles que le NATIF publie comme cibles legales de 1057 depuis la position COURANTE."""
    at = rpc(s, "abilityTargets", {"runnerId": rid, "unitId": uid, "allAbilities": True}, 90) or {}
    out = []
    for unit in (at.get("units") or []):
        if unit.get("unitId") != uid:
            continue
        for ab in (unit.get("abilities") or []):
            if ab.get("abilityId") != GROT_TANK:
                continue
            for t in (ab.get("fromHere") or []):
                tile = t.get("tile") or {}
                if t.get("kind") == "tile" and tile.get("col") is not None:
                    out.append((tile["col"], tile["row"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--turns", type=int, default=12,
                    help="tours max a passer pour que le natif publie une cible legale")
    ap.add_argument("--wait-turns", type=int, default=0,
                    help="tours de MON camp a passer AVANT de caster -- fait monter "
                         "`turnsStarted(caster)`, ce qui rend l'etage E2 discriminant sur la PENTE "
                         "(`extraHp`) et pas seulement sur l'ordonnee a l'origine")
    ap.add_argument("--caster-pos", default=None, help="'col,row' -- place le Big Mek (crafte E4)")
    ap.add_argument("--enemy-pos", default=None, help="'col,row' -- place orksNob (crafte E4)")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    s = sid()
    rid = build(Path(a.state_file), a.board, a.seed, a.caster_pos, a.enemy_pos)
    print("[567] runner %d monte (board %s, seed %s)" % (rid, a.board, a.seed))
    rc = 0
    try:
        from engine.entities.effects.magnitude import ability_var
        from engine.entities.active_ability_type import ActiveAbilityType
        from engine.runner.abilities.handler import ABILITY_CLASSES
        from engine.runner.components import (HealthComponent, PositionComponent, StatsComponent,
                                              UnitComponent)
        from engine.entities.stats import StatType

        cls = ABILITY_CLASSES.get(int(ActiveAbilityType.GrotTank))
        if cls is None:
            print("[567] ECHEC : 1057 absente d'ABILITY_CLASSES")
            return 1

        # ---- E0 : attendre que le natif publie une cible legale pour 1057 -------------------- #
        before = live_units(s, rid)
        caster = next((u for u in before if u.get("visualId") == CASTER
                       and not u.get("isDead")), None)
        if caster is None:
            print("[567] ECHEC : caster absent")
            return 1
        cid = caster["squadId"]
        dv0 = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 60) or {}
        me = next((u.get("owner") for u in (dv0.get("units") or []) if u.get("id") == cid), None)
        tgt = None
        waited = 0
        for _ in range(int(a.turns) + 2 * int(a.wait_turns) + 2):
            sn = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 60) or {}
            if sn.get("currentPlayer") != me:
                rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            if waited < int(a.wait_turns):
                # `endturn` fait passer le tour SANS jouer l'IA -> les positions ne bougent pas,
                # seul `turnsStarted` monte. C'est le levier qui rend E2 discriminant sur la pente.
                waited += 1
                rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            cands = grot_tank_targets(s, rid, cid)
            if cands:
                tgt = cands[0]
                break
            rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        if tgt is None:
            print("[567] NON CONFRONTE : le natif n'a publie aucune tuile legale en %d tours"
                  % a.turns)
            return 2

        before = live_units(s, rid)
        pos_before = positions(before)
        snap0 = rpc(s, "combatSnapshot", {"runnerId": rid}, 60) or {}
        print("[567] AVANT (cible = tuile %s) :" % (tgt,))
        for uid, (vid, col, row, dead, hp, mx) in sorted(pos_before.items()):
            print("    u%-4s %-18s (%s,%s) hp=%s/%s%s"
                  % (uid, vid, col, row, hp, mx, " MORT" if dead else ""))

        # ---------------- PORT : execute l'arbre sur l'etat AVANT ----------------
        st, board = load_port_state(s, rid)
        tile_id = board.id_at(tgt[0], tgt[1])
        ce = st.get_entity(cid)
        csc = ce.get_component(StatsComponent) if ce is not None else None
        level = getattr(csc.ctx, "active_ability_level", None) if csc is not None else None
        mult = int(getattr(csc.ctx, "ability_variables_multiplier", 100) or 100) if csc else 100
        turns_started = int(csc.ctx.get_stat(int(StatType.TURNS_STARTED)) or 0) if csc else 0
        v_hp = int(ability_var(ABILITY_ID, "summonHp", level, multiplier_pct=mult) or 0)
        v_extra = int(ability_var(ABILITY_ID, "extraHp", level, multiplier_pct=mult) or 0)
        v_dmg = int(ability_var(ABILITY_ID, "summonDmg", level, multiplier_pct=mult) or 0)
        v_arm = int(ability_var(ABILITY_ID, "summonArmor", level, multiplier_pct=mult) or 0)
        known_ids = set(st.entities)
        port_res = cls().execute_behaviour(st, cid, tile_id) or {}
        port_spawn = []
        for gid in (port_res.get("spawned") or []):
            e = st.get_entity(int(gid))
            pc = e.get_component(PositionComponent) if e is not None else None
            hc = e.get_component(HealthComponent) if e is not None else None
            sc = e.get_component(StatsComponent) if e is not None else None
            uc = e.get_component(UnitComponent) if e is not None else None
            port_spawn.append({
                "id": int(gid), "vid": None if uc is None else uc.visual_id,
                "pos": None if pc is None else (pc.col, pc.row),
                "hp": None if hc is None else hc.hp, "max": None if hc is None else hc.hp_max,
                "atk": None if sc is None else sc.ctx.get_stat(int(StatType.ATTACK)),
                "arm": None if sc is None else sc.ctx.get_stat(int(StatType.FIXED_ARMOR)),
            })
        print("[567] PORT  : tile=%s spawned=%s tank_hp=%s attacks=%s"
              % (port_res.get("tile"), port_res.get("spawned"), port_res.get("tank_hp"),
                 port_res.get("attacks")))

        # ---------------- NATIF : le meme cast via applyAction ----------------
        res = rpc(s, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "abilityType": GROT_TANK,
            "to": {"col": tgt[0], "row": tgt[1]}}}, 90) or {}
        act = (res.get("actions") or [{}])[0]
        if act.get("error"):
            print("[567] cast natif REFUSE : %s" % act.get("error"))
            return 1
        after = live_units(s, rid)
        pos_after = positions(after)
        snap1 = rpc(s, "combatSnapshot", {"runnerId": rid}, 60) or {}
        nat_new = [u for u in after if u.get("squadId") not in pos_before]
        print("[567] APRES (natif) :")
        for uid, (vid, col, row, dead, hp, mx) in sorted(pos_after.items()):
            was = pos_before.get(uid)
            mark = "   <- APPARU" if was is None else (
                "   <- HP %s -> %s" % (was[4], hp) if was[4] != hp else "")
            print("    u%-4s %-18s (%s,%s) hp=%s/%s%s%s"
                  % (uid, vid, col, row, hp, mx, " MORT" if dead else "", mark))

        # ---------------- CONFRONTATION etage par etage ----------------
        print("\n[567] CONFRONTATION  (niveau=%s mult=%s%%  turnsStarted(caster)=%d)"
              % (level, mult, turns_started))
        print("      variables lues : summonHp=%d extraHp=%d summonDmg=%d summonArmor=%d"
              % (v_hp, v_extra, v_dmg, v_arm))

        # E1 -- le spawn, et SA TUILE.
        nat_pos = sorted((u.get("col"), u.get("row")) for u in nat_new if not u.get("isDead"))
        port_pos = sorted(p["pos"] for p in port_spawn if p["pos"] is not None)
        ok_e1 = (len(nat_new) == len(port_spawn) and nat_pos == port_pos
                 and nat_pos == [tuple(tgt)])
        print("    E1 SPAWN     natif=%d %s  port=%d %s  cible=%s -> %s"
              % (len(nat_new), nat_pos, len(port_spawn), port_pos, [tuple(tgt)],
                 "OK" if ok_e1 else "DIVERGE"))
        rc = rc or (0 if ok_e1 else 1)

        # E2 -- LES PV, l'etage `StatModifierFormula`. Trois hypotheses imprimees cote a cote.
        # ⚠ On lit `hp`, PAS `maxHp` : `observeBattle` ne publie pas `maxHp` sur ce chemin (il rend
        # None), et l'unite VIENT d'apparaitre -> `hp == hp_max`. Cote port on compare donc au
        # `hp_max` du `HealthComponent`, que `_spawn_config_grot` seede a la meme grandeur.
        attendu = v_hp + turns_started * v_extra
        nat_hp = [u.get("hp") for u in nat_new]
        port_hp = [p["max"] for p in port_spawn]
        ok_e2 = bool(nat_hp) and nat_hp == port_hp
        print("    E2 PV        natif=%s  port=%s" % (nat_hp, port_hp))
        print("       hypotheses : summonHp seul=%d | summonHp+1x extraHp=%d | "
              "summonHp+%d x extraHp=%d (= ce que le port calcule)"
              % (v_hp, v_hp + v_extra, turns_started, attendu))
        if turns_started < 1:
            print("       ATTENTION turnsStarted=0 -> l'etage n'est PAS discriminant "
                  "(les trois hypotheses coincident)")
        if nat_hp and nat_hp[0] is not None and int(nat_hp[0]) == v_hp and v_extra:
            print("       ATTENTION le natif rend `summonHp` SEUL -> l'override de PV ne mordrait "
                  "PAS, re-lire `TankHealth` avant de conclure")
        print("       -> %s" % ("OK" if ok_e2 else "DIVERGE"))
        rc = rc or (0 if ok_e2 else 1)

        # E3 -- les stats de config, temoin de non-regression de l'override.
        def snap_stat(sn, uid, key):
            """`combatSnapshot.units[]` est keye par `entityId` (cf. `snapshot.load_state`), et ses
            stats vivent sous `stats` -- un dict {nom: {current, delta, ...}} OU {nom: valeur}."""
            for u in (sn.get("units") or []):
                if u.get("entityId") != uid:
                    continue
                v = (u.get("stats") or {}).get(key)
                if isinstance(v, dict):
                    return v.get("current", v.get("value"))
                return v
            return None

        nat_stats = [(snap_stat(snap1, u.get("squadId"), "Attack"),
                      snap_stat(snap1, u.get("squadId"), "FixedArmor")) for u in nat_new]
        port_stats = [(p["atk"], p["arm"]) for p in port_spawn]
        # TRI-ETAT (regle « None = PAS mesure, jamais un zero ») : `combatSnapshot` ne publie pas
        # les entites NPC fraichement spawnees sur ce chemin -> on le DIT, on ne le rend pas comme
        # un desaccord. Le port, lui, est confronte a la CONFIG (la source que le natif lit aussi).
        if any(x == (None, None) for x in nat_stats):
            print("    E3 STATS     natif = NON MESURE (`combatSnapshot` ne publie pas le summon "
                  "NPC) ; port=%s ; config (summonDmg,summonArmor)=(%d,%d) -> %s"
                  % (port_stats, v_dmg, v_arm,
                     "port CONFORME A LA CONFIG"
                     if all(x == (v_dmg, v_arm) for x in port_stats) else "PORT != CONFIG"))
            if not all(x == (v_dmg, v_arm) for x in port_stats):
                rc = 1
        else:
            ok_e3 = nat_stats == port_stats
            print("    E3 STATS     natif(Attack,FixedArmor)=%s  port=%s  config=(%d,%d) -> %s"
                  % (nat_stats, port_stats, v_dmg, v_arm, "OK" if ok_e3 else "DIVERGE"))
            rc = rc or (0 if ok_e3 else 1)

        # E4 -- l'on-appearance.
        nat_dmg = {}
        for uid, (vid, col, row, dead, hp, mx) in pos_after.items():
            was = pos_before.get(uid)
            if was is not None and was[4] is not None and hp is not None and was[4] != hp:
                nat_dmg[uid] = was[4] - hp
        port_dmg = {}
        for at in (port_res.get("attacks") or []):
            port_dmg[at.get("target")] = port_dmg.get(at.get("target"), 0) + int(at.get("total") or 0)
        ok_e4 = nat_dmg == port_dmg
        print("    E4 ON-APPEAR degats par cible : natif=%s  port=%s -> %s"
              % (nat_dmg, port_dmg, "BIT-EXACT" if ok_e4 else "DIVERGE"))
        if not nat_dmg and not port_dmg:
            print("       (aucun ennemi a portee 3 du tank -> etage INERTE des deux cotes ; "
                  "ce n'est pas une confirmation)")
        rc = rc or (0 if ok_e4 else 1)

        # E5 -- #291 : le summon n'est PAS activable.
        dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 60) or {}
        act_ids = list(dv.get("toActivate") or [])
        new_ids = [u.get("squadId") for u in nat_new]
        ok_e5 = not any(i in act_ids for i in new_ids)
        print("    E5 #291      toActivate=%s  summons=%s -> %s"
              % (act_ids, new_ids, "OK (summon non activable)" if ok_e5 else "INATTENDU"))

        print("\n[567] %s" % ("PROBE OK" if rc == 0 else "PROBE : DIVERGENCE"))
    finally:
        if not a.keep:
            try:
                rpc(s, "disposeRunner", {"runnerId": rid}, 20)
                print("[567] runner %d dispose" % rid)
            except Exception as exc:
                print("[567] dispose KO: %s" % str(exc)[:200])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
