#!/usr/bin/env python
"""Probe TimeFlux / volet REGEN (passif `thousTerminator` << Toth >>) — GROUND TRUTH LIVE isole
+ les DEUX cas discriminants (dont le cas NEGATIF : le terme `lastHit` NE MORD PAS).

i2 : « At the beginning of his turn, Toth regenerates {hpToHeal} Health plus an additional amount
equal to the Damage of the LAST HIT he received in the LAST ENEMY TURN. The total amount restored
cannot exceed {maxHpToHeal} Health. »
Natif : `OwnerIsActor & On(0x13=TurnStart_Other)` -> `Heal(self, Min(Sum(hpToHeal,
LastHitDamageTakenLastTurn(self)), maxHpToHeal))`.

PROTOCOLE (mesure du regen ISOLEE — patron `probe_203_livingmetal`) : au tour ENNEMI, un `endturn`
FLIPPE vers Toth et declenche le turn-start -> le delta de PV sur CE flip est le regen SEUL (aucun
degat n'a lieu pendant un flip).

  M+ (le terme lastHit MORD)      : cycles endturn+aiturn jusqu'a ce que Toth soit FRAPPE, puis
                                    endturn de flip -> regen = hpToHeal + <degat du DERNIER coup>,
                                    donc STRICTEMENT > hpToHeal.
  M- (cas NEGATIF, lastHit == 0)  : depuis le tour de Toth, `endturn` (P->A) puis `endturn` (A->P)
                                    SANS aiturn : le tour adverse se passe SANS AUCUNE action, donc
                                    aucun coup encaisse -> `ActorStatistics@+0x6c` vaut 0 au
                                    roulement -> regen = hpToHeal EXACTEMENT.
                                    C'est le cas qui prouve que le terme est bien LU (et pas un
                                    bonus inconditionnel), et que le roulement remet a zero.

ASCII only (cp1252). Usage: python probe_tf_time_flux.py [--seed 31337]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402
from engine.entities.effects.magnitude import ability_var                # noqa: E402

ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_tf_time_flux_state.json"
CARRIER, FOE, BOARD = "thousTerminator", "orksNob", "MC1_67"


def rpc(sid, m, args, t=90):
    return (_rpc(sid, m, [args], timeout=t).get("result") or {})


def build(seed):
    STATE.unlink(missing_ok=True)
    # `--hp-player` HAUT : Toth doit encaisser SANS mourir et rester TRES en dessous de son maximum
    # (sinon le heal est cape par `hp_max` et la mesure n'est plus discriminante).
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
           "--p-units", CARRIER, "--a-units", f"{FOE},{FOE}", "--board", BOARD,
           "--hp-player", "400000", "--state-file", str(STATE)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not STATE.exists():
        sys.stdout.write((p.stdout or "")[-900:]); sys.stdout.write((p.stderr or "")[-900:])
        raise SystemExit("build KO")
    return json.loads(STATE.read_text(encoding="utf-8"))["runnerId"]


def cp(sid, rid):
    return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60).get("currentPlayer")


def hp_of(sid, rid, vid=CARRIER):
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    for u in (ob.get("units") or []):
        if u.get("visualId") == vid:
            return int(u.get("hp") or 0), int(u.get("hpMax") or 0), u.get("id")
    return None, None, None


def endturn(sid, rid):
    rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    return cp(sid, rid)


def aiturn():
    subprocess.run([sys.executable, "rl_duel.py", "aiturn", "--state-file", str(STATE)],
                   cwd=str(PYDIR), capture_output=True, text=True,
                   encoding="utf-8", errors="replace")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=31337)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    ok = True
    try:
        hp0, hpmax, uid = hp_of(sid, rid)
        p_team = cp(sid, rid)
        # magnitudes attendues : le porteur est au rank 17 (level 50, multiplicateur 180).
        lvl, mult = 50, 180
        hp_to_heal = int(ability_var("TimeFlux", "hpToHeal", lvl, multiplier_pct=mult) or 0)
        max_hp = int(ability_var("TimeFlux", "maxHpToHeal", lvl, multiplier_pct=mult) or 0)
        print(f"[TF] runner={rid} Toth=u{uid} hp={hp0}/{hpmax} player={p_team} "
              f"hpToHeal={hp_to_heal} maxHpToHeal={max_hp}")

        # --- Phase 1 : faire ENCAISSER Toth (les orks sont melee, ils viennent au contact) --------
        damaged = False
        for rnd in range(12):
            before = hp_of(sid, rid)[0]
            endturn(sid, rid)          # P -> A
            aiturn()                   # A joue (et finit son tour -> turn-start de P + regen)
            after = hp_of(sid, rid)[0]
            print(f"[TF] r{rnd}: hp {before} -> {after} (cp={cp(sid, rid)})")
            if after < before:         # net NEGATIF => les coups ont depasse la regen
                damaged = True
                break
        if not damaged:
            print("[TF] Toth jamais frappe -> scenario non discriminant"); return 4

        # --- M+ : un tour ennemi AVEC coups, puis flip -> regen = hpToHeal + dernier coup ---------
        cur = cp(sid, rid)
        if cur == p_team:
            cur = endturn(sid, rid)    # P -> A
        aiturn()                       # A frappe Toth ; l'aiturn enchaine le turn-start de P
        # NB : `aiturn` a deja consomme le turn-start ; on refait donc un cycle PROPRE ou le flip
        # est SEUL. On repart du tour de P, on flippe sans laisser l'IA agir : cf. M-.
        hp_before_pos = hp_of(sid, rid)[0]
        print(f"[TF] M+ prepare : hp={hp_before_pos} cp={cp(sid, rid)}")

        # --- M- (cas NEGATIF) : P -> A -> P SANS aiturn => aucun coup encaisse au tour adverse ----
        if cp(sid, rid) != p_team:
            endturn(sid, rid)
        hp_a = hp_of(sid, rid)[0]
        endturn(sid, rid)              # P -> A (tour adverse, AUCUNE action)
        hp_b = hp_of(sid, rid)[0]
        endturn(sid, rid)              # A -> P : flip -> turn-start -> regen SEUL
        hp_c = hp_of(sid, rid)[0]
        regen_neg = hp_c - hp_b
        print(f"[TF] M- (aucun coup au tour adverse) : {hp_a} -> {hp_b} -> {hp_c} "
              f"=> regen={regen_neg} (attendu hpToHeal={hp_to_heal})")
        if regen_neg != hp_to_heal:
            print(f"[TF] **FAIL M-** regen={regen_neg} != hpToHeal={hp_to_heal} "
                  f"(terme lastHit non remis a zero, ou magnitude fausse)")
            ok = False

        # --- M+ ISOLE : on PILOTE l'attaque adverse a la main (pas `aiturn`, qui enchainerait le
        #     turn-start et melangerait degat et regen), puis on flippe SEUL. -------------------
        endturn(sid, rid)              # P -> A (tour adverse, l'IA n'a PAS joue)
        dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
        toth = next((u for u in (dv.get("units") or []) if u.get("visualId") == CARRIER), None)
        aid_pair = None
        for p in (dv.get("attackPlans") or []):
            for ev in (p.get("evals") or []):
                if (ev.get("targetId") == (toth or {}).get("id")
                        and ev.get("kind") == "normal" and not ev.get("err")):
                    aid_pair = (p.get("unitId"), ev.get("abilityId"))
                    break
            if aid_pair:
                break
        regen_pos = dmg = None
        if aid_pair is None:
            print("[TF] M+ : aucun plan d'attaque adverse sur Toth ce tour -> volet POSITIF isole "
                  "NON monte (residu de mesure, cf. case-doc)")
        else:
            ork, aid = aid_pair
            hp_x = hp_of(sid, rid)[0]
            rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": ork, "targetId": toth["id"],
                "abilityType": aid}}, 120)
            hp_y = hp_of(sid, rid)[0]
            dmg = hp_x - hp_y                       # degat de CETTE attaque (isole du regen)
            endturn(sid, rid)                       # A -> P : flip -> turn-start -> regen SEUL
            hp_z = hp_of(sid, rid)[0]
            regen_pos = hp_z - hp_y
            expect = min(hp_to_heal + dmg, max_hp)
            print(f"[TF] M+ (attaque PILOTEE u{ork} -> Toth) : {hp_x} -> {hp_y} (degat={dmg}) "
                  f"-> {hp_z} => regen={regen_pos} | attendu min({hp_to_heal}+lastHit, {max_hp})")
            if dmg > 0 and regen_pos == hp_to_heal:
                print("[TF] **FAIL M+** le terme lastHit n'a PAS ete ajoute (regen == hpToHeal)")
                ok = False
            elif regen_pos != expect:
                # l'attaque peut compter PLUSIEURS coups : `lastHit` est le DERNIER, pas le total.
                print(f"[TF] NOTE M+ : regen={regen_pos} != min(hpToHeal+TOTAL={expect}) -> "
                      f"lastHit={regen_pos - hp_to_heal} sur un total de {dmg} "
                      f"(attaque multi-coups : c'est le DERNIER coup qui compte)")
                if not (0 < regen_pos - hp_to_heal <= dmg):
                    print("[TF] **FAIL M+** lastHit hors bornes ]0, degat_total]")
                    ok = False
        print(f"[TF] BILAN -> {'OK' if ok else '** FAIL **'} "
              f"(M- isole={regen_neg}/{hp_to_heal} ; M+ isole regen={regen_pos} degat={dmg})")
        return 0 if ok else 1
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 15)
            print(f"[TF] runner {rid} dispose")
        except Exception as e:
            print(f"[TF] dispose KO: {e}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
