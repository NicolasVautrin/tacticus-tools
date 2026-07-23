#!/usr/bin/env python
"""Probe #202-C — validation live de MasterOfTheTutelaries (active 1096 + effet 1197 + triggered 1173).

Setup crafte (case-202 §5-C) : Abraxas (thousInfernalMaster) + Toth-le-sorcier (thousSorcerer,
ranged r2 PSYCHIC — le re-trigger allie) vs 2x necroWarden, HP gonfles, MC1_67.

LOIS MESUREES (diag 202c, runners 181/182/183 — ce probe les fige) :
  A. EXECUTE (cast 1096 sur hex libre adjacent) — parse de la CASCADE BRUTE :
     A1. effet 1197 pose sur Abraxas (action s=16 Effect_SourceActiveAbility=1096, RemainingTurns=1)
         — decisionView le FILTRE (ne pas s'y fier) ;
     A2. Pink Horror sur LA tuile ciblee, MaxHealth == summonHp[lvl] x mult (cascade s=13/s=14) ;
     A3. chaque Screamer : MaxHealth == summonHp_2[lvl] x mult (vars suffixees _2 !), tuile
         ADJACENTE a Abraxas ;
     A4. #Screamers == #attaques QUALIFIANTES de la cascade (1 par ATTAQUE dont le SET de profils
         contient Psychic — arme OU bonus InfernalPacts (groupe 43) ; la chaine Horror->Screamer->...
         n'est bornee que par les positions).
  B. RE-TRIGGER ALLIE (meme tour) : attaque ranged Psychic du sorcier (HORS CONTACT — le ranged
     est desactive au contact d'un ennemi, diag v5) -> >=1 Screamer, et #spawns == #attaques
     qualifiantes de la cascade (le tir + la CHAINE des nouveaux Screamers adjacents a Abraxas).
     L'effet 1197 reste arme jusqu'a la FIN DU TOUR D'EQUIPE (pas du tour d'unite d'Abraxas).
  C. EXPIRY : au tour suivant, la MEME attaque Psychic du sorcier -> +0 (1197 expire/revert
     RemoveTriggeredAbility a la fin du tour d'equipe — cascade v1 : Effect_RemainingTurns 1->0).

ASCII only (cp1252). Usage: python probe_202c_tutelaries.py [--seed 20203]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.playbook import scene as SC  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_202c_tutelaries_state.json"
ABX_VIS = "thousInfernalMaster"
SORC_VIS = "thousSorcerer"                # allie Psychic ranged r2 (re-trigger B/C)
HORROR_VIS = "thousNpc1PinkHorror"        # visualId LIVE de thousSmnPinkHorror
SCREAMER_VIS = "thousNpc2Screamer"        # visualId LIVE de thousSmnScreamer
ABILITY = 1096
PSYCHIC_ID = 13                            # DamageProfileType.Psychic (Attack_Weapon_DamageProfile)
W, H = 7, 9


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int) -> int:
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67",
         "--p-units", f"{ABX_VIS},{SORC_VIS}",
         "--a-units", "necroWarden,necroWarden",
         "--hp-target", "300000", "--hp-player", "300000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[202c] build KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def _pos(u: dict) -> tuple:
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _units(dec: dict, vis=None) -> list:
    out = [u for u in (dec.get("units") or []) if u.get("alive")]
    if vis is not None:
        out = [u for u in out if u.get("visualId") == vis]
    return out


def _free_tiles(dec) -> set:
    occ = {_pos(u) for u in (dec.get("units") or []) if u.get("alive")}
    return {(c, r) for c in range(W) for r in range(H)} - occ


def _apply(rpc, rid, action, t=240) -> dict:
    return rpc("applyAction", {"runnerId": rid, "action": action}, t)


def _move(rpc, rid, unit_id, tile) -> bool:
    r = _apply(rpc, rid, {"kind": "move", "unitId": unit_id,
                          "to": {"col": int(tile[0]), "row": int(tile[1])}}, 120)
    return bool(((r or {}).get("actions") or [{}])[0].get("ok"))


def _my_turn(rpc, rid, vis, max_iter=12):
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid}, 150)
        u = next((x for x in (dec.get("units") or [])
                  if x.get("visualId") == vis and x.get("alive")), None)
        if u is not None and dec.get("currentPlayer") == u.get("owner"):
            return dec, u
        rpc("aiPlayTurn", {"runnerId": rid}, 240)
        d2 = rpc("decisionView", {"runnerId": rid}, 90)
        if u is not None and isinstance(d2, dict) and d2.get("currentPlayer") != u.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def _end_round(rpc, rid, my_owner) -> None:
    for _ in range(4):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        dec = rpc("decisionView", {"runnerId": rid}, 90)
        if isinstance(dec, dict) and dec.get("ok") and dec.get("currentPlayer") != my_owner:
            rpc("aiPlayTurn", {"runnerId": rid}, 300)
            return


def _cascade(r) -> list:
    out = list(r.get("cascade") or [])
    for a in (r.get("actions") or []):
        out += list(a.get("events") or [])
    return out


def _tags(ev) -> dict:
    try:
        return json.loads(ev.get("tags") or "{}")
    except Exception:
        return {}


def _psychic_shot_setup(rpc, rid, dec, sorc) -> "dict | None":
    """Prepare un TIR PSYCHIC legal du sorcier : le laisse (ou le deplace) sur une tuile HORS
    CONTACT (dist >= 2 de TOUT ennemi — le ranged est desactive au contact, regle Tacticus) avec
    un warden a distance EXACTEMENT 2. Renvoie la cible (dict warden) ou None."""
    enemies = [u for u in (dec.get("units") or [])
               if u.get("alive") and u.get("owner") != sorc.get("owner")]
    wardens = _units(dec, "necroWarden")
    spos = _pos(sorc)

    def _ok_tile(t):
        return (all(hexgeo.distance(t, _pos(e)) >= 2 for e in enemies)
                and any(hexgeo.distance(t, _pos(w)) == 2 for w in wardens))

    if _ok_tile(spos):
        return next(w for w in wardens if hexgeo.distance(spos, _pos(w)) == 2)
    ft = _free_tiles(dec)
    mv = next((t for t in sorted(hexgeo.disk(spos[0], spos[1], 3),
                                 key=lambda t: hexgeo.distance(t, spos))
               if t in ft and _ok_tile(t)), None)
    if mv is None or not _move(rpc, rid, sorc["id"], mv):
        return None
    return next((w for w in wardens if hexgeo.distance(mv, _pos(w)) == 2), None)


def _parse_cast(cascade: list, abx_id: int) -> dict:
    """Extrait de la cascade du cast : effet 1197, spawns (entity/tile/hp/lvl/mult), attaques
    qualifiantes (1 par groupe g=12 src=Loki_NormalAttack d'un summon, Psychic = profil d'arme 13
    OU groupe imbrique g=43 InfernalPacts)."""
    out = {"effect_1096": None, "spawns": [], "attacks": []}
    spawn_meta: dict = {}
    stack: list = []          # pile des groupes ouverts [(group, entity, source)]
    cur_attack = None
    for ev in cascade:
        k = ev.get("kind")
        if k == "group":
            g = (ev.get("group"), ev.get("entity"), ev.get("source"))
            stack.append(g)
            if g[0] == 12 and g[2] == "Loki_NormalAttack" and g[1] != abx_id:
                cur_attack = {"attacker": g[1], "psychic": False, "n_dmg": 0}
                out["attacks"].append(cur_attack)
            if g[0] == 43 and cur_attack is not None:
                cur_attack["psychic"] = True          # bonus InfernalPacts (profil Psychic)
        elif k == "finish":
            if stack:
                g = stack.pop()
                if cur_attack is not None and g[0] == 12 and g[1] == cur_attack["attacker"]:
                    cur_attack = None
        else:
            t = _tags(ev)
            if ev.get("step") == 16 and t.get("Effect_SourceActiveAbility") == ABILITY:
                out["effect_1096"] = t
            if ev.get("step") == 10 and t.get("Unit_Parent_Id") == abx_id:
                spawn_meta[ev.get("entity")] = {"entity": ev.get("entity"),
                                                "tile_id": t.get("Unit_Foot_Tile_Id_1")}
            if ev.get("step") == 13 and ev.get("entity") in spawn_meta \
                    and "UnitStats_MaxHealth" in t:
                spawn_meta[ev.get("entity")]["hp"] = t["UnitStats_MaxHealth"]
                spawn_meta[ev.get("entity")]["atk"] = t.get("UnitStats_Attack")
            if ev.get("step") == 14 and ev.get("entity") in spawn_meta \
                    and "UnitStats_ActiveAbility_Level" in t \
                    and "lvl" not in spawn_meta[ev.get("entity")]:
                spawn_meta[ev.get("entity")]["lvl"] = t["UnitStats_ActiveAbility_Level"]
                spawn_meta[ev.get("entity")]["mult"] = \
                    t.get("UnitStats_ActiveAbility_VariableMultiplierPercentage")
            if ev.get("step") == 30 and "Attack_Weapon_DamageProfile" in t \
                    and cur_attack is not None:
                if int(t["Attack_Weapon_DamageProfile"]) == PSYCHIC_ID:
                    cur_attack["psychic"] = True
            if ev.get("step") == 4 and cur_attack is not None:
                cur_attack["n_dmg"] += 1
    out["spawns"] = list(spawn_meta.values())
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20203)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    rpc = lambda m, b, t=90: _r(sid, m, b, t)   # noqa: E731
    print(f"[202c] seed={args.seed} runner={rid}")
    board = SC.build_board(rpc, rid)
    from engine.entities.effects.magnitude import ability_var
    fails: list = []
    try:
        # --- drive : Abraxas a dist <= 3 d'un warden ; le sorcier suit -------------------
        dec, abx = _my_turn(rpc, rid, ABX_VIS)
        if abx is None:
            print("[202c] Abraxas introuvable -> stop")
            return 2
        for rnd in range(8):
            wardens = _units(dec, "necroWarden")
            sorc = next(iter(_units(dec, SORC_VIS)), None)
            apos = _pos(abx)
            dmin = min(hexgeo.distance(apos, _pos(w)) for w in wardens)
            if dmin <= 3:
                break
            goal = min((_pos(w) for w in wardens), key=lambda p: hexgeo.distance(apos, p))
            for uu in (abx, sorc):
                if uu is None:
                    continue
                ft = _free_tiles(rpc("decisionView", {"runnerId": rid}, 90))
                upos = _pos(uu)
                cands = sorted([t for t in hexgeo.disk(upos[0], upos[1], 3) if t in ft],
                               key=lambda t: hexgeo.distance(t, goal))
                for t in cands[:6]:
                    if _move(rpc, rid, uu["id"], t):
                        break
            _end_round(rpc, rid, abx.get("owner"))
            dec, abx = _my_turn(rpc, rid, ABX_VIS)
            if abx is None:
                print("[202c] Abraxas perdu au drive -> stop")
                return 2
        wardens = _units(dec, "necroWarden")
        sorc = next(iter(_units(dec, SORC_VIS)), None)
        apos = _pos(abx)
        print(f"[202c] positions: abx={apos} sorc={_pos(sorc) if sorc else None} "
              f"wardens={[_pos(w) for w in wardens]}")

        # --- A. cast 1096 : tuile libre adjacente, a portee (<=2) d'un warden -----------
        ft = _free_tiles(dec)
        cast = next((tuple(t) for t in hexgeo.neighbors(*apos)
                     if tuple(t) in ft
                     and any(hexgeo.distance(tuple(t), _pos(w)) <= 2 for w in wardens)), None)
        if cast is None:
            print("[202c] pas de tuile de cast a portee -> stop")
            return 2
        r = _apply(rpc, rid, {"kind": "ability", "casterId": abx["id"],
                              "to": {"col": cast[0], "row": cast[1]}, "abilityType": ABILITY})
        if not ((r or {}).get("actions") or [{}])[0].get("ok"):
            print(f"[202c] A cast KO")
            return 2
        pc = _parse_cast(_cascade(r), abx["id"])
        # A1 : effet 1197
        e = pc["effect_1096"]
        ok1 = bool(e) and e.get("Effect_RemainingTurns") == 1
        print(f"[202c] A1 effet 1197 pose (RemainingTurns=1): {'OK' if ok1 else 'X'} {e}")
        if not ok1:
            fails.append("A1:effet")
        # A2/A3 : spawns (Horror puis Screamers) — stats offline vs cascade
        spawns = pc["spawns"]
        if not spawns:
            print("[202c] A2 AUCUN spawn X")
            fails.append("A2:no-spawn")
        for i, s in enumerate(spawns):
            kind = "Horror" if i == 0 else "Screamer"
            key = "summonHp" if i == 0 else "summonHp_2"
            exp = ability_var("MasterOfTheTutelaries", key, s.get("lvl"),
                              multiplier_pct=s.get("mult") or 100)
            ti = board.by_id.get(s.get("tile_id")) or {}
            tile = (ti.get("col"), ti.get("row"))
            hp_ok = exp is not None and int(exp) == int(s.get("hp") or -1)
            print(f"[202c] A{2 + min(i, 1)} {kind} e{s['entity']}: tile={tile} hp={s.get('hp')} "
                  f"(offline {key}[{s.get('lvl')}]x{s.get('mult')}={exp}: {'OK' if hp_ok else 'X'})")
            if not hp_ok:
                fails.append(f"A:{kind}-hp")
            if i == 0 and tile != cast:
                print(f"[202c] A2 Horror tile {tile} != cast {cast} X")
                fails.append("A2:horror-tile")
            if i >= 1 and hexgeo.distance(tile, apos) != 1:
                print(f"[202c] A3 Screamer tile {tile} NON adjacente a Abraxas {apos} X")
                fails.append("A3:screamer-tile")
        # A4 : 1 Screamer par attaque qualifiante
        n_scr = len(spawns) - 1 if spawns else 0
        n_qual = sum(1 for a in pc["attacks"] if a["psychic"])
        print(f"[202c] A4 attaques summons: {pc['attacks']}")
        print(f"[202c] A4 screamers={n_scr} vs attaques-Psychic={n_qual}: "
              f"{'OK' if n_scr == n_qual else 'X'}")
        if n_scr != n_qual:
            fails.append("A4:count")

        # --- B. re-trigger ALLIE (meme tour) : sorcier ranged Psychic -> +1 -------------
        dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        n_before = len(_units(dec2, SCREAMER_VIS))
        sorc2 = next(iter(_units(dec2, SORC_VIS)), None)
        b_done = False
        if sorc2 is not None and dec2.get("currentPlayer") == sorc2.get("owner"):
            # tir Psychic LEGAL = cible a distance EXACTEMENT 2 (dist 1 = arme melee FLAME) ET
            # sorcier HORS CONTACT (regle Tacticus : le ranged est desactive au contact d'un
            # ennemi — mesure diag v5 : actionConsumed=False colle a un warden).
            tgt = _psychic_shot_setup(rpc, rid, dec2, sorc2)
            dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            sorc2 = next(iter(_units(dec2, SORC_VIS)), None)
            if tgt is not None and sorc2 is not None \
                    and hexgeo.distance(_pos(sorc2), _pos(tgt)) == 2:
                nab = next((ab.get("id") for ab in (sorc2.get("abilities") or [])
                            if ab.get("kind") == "normal"), None)
                rb = _apply(rpc, rid, {"kind": "ability", "casterId": sorc2["id"],
                                       "targetId": tgt["id"], "abilityType": nab})
                okb = ((rb or {}).get("actions") or [{}])[0].get("ok")
                dec3 = rpc("decisionView", {"runnerId": rid}, 150)
                n_after = len(_units(dec3, SCREAMER_VIS))
                # loi = celle d'A4 sur la cascade de B : 1 Screamer par attaque QUALIFIANTE
                # (tir Psychic du sorcier + CHAINE des nouveaux Screamers dont l'attaque porte
                # le bonus InfernalPacts Psychic). Mesure seed 20203 : +2 (tir -> S2 ; S2 attaque
                # au contact avec bonus -> S3 ; S3 sans cible -> stop).
                pb = _parse_cast(_cascade(rb), abx["id"])
                n_new = len(pb["spawns"])
                n_qual_b = sum(1 for a in pb["attacks"] if a["psychic"])
                print(f"[202c] B sorcier Psychic (ab={nab} ok={okb}): screamers "
                      f"{n_before} -> {n_after} ; cascade spawns={n_new} vs "
                      f"attaques-Psychic={n_qual_b}")
                if n_after <= n_before:
                    fails.append("B:retrigger-allie")        # loi coeur : arme jusqu'a fin de tour d'EQUIPE
                if n_new != n_qual_b:
                    fails.append("B:chain-count")            # loi par-attaque sur la cascade B
                b_done = True
                n_before = n_after
        if not b_done:
            print("[202c] B SKIP (sorcier hors position/tour) — datapoint non mesure")
            fails.append("B:skip")

        # --- C. expiry : tour suivant, meme attaque -> +0 --------------------------------
        my_owner = abx.get("owner")
        _end_round(rpc, rid, my_owner)
        dec4, _abx4 = _my_turn(rpc, rid, ABX_VIS)
        sorc4 = next(iter(_units(dec4 or {}, SORC_VIS)), None)
        if dec4 is not None and sorc4 is not None:
            n_c0 = len(_units(dec4, SCREAMER_VIS))
            # meme discipline qu'en B : hors contact + cible a distance EXACTEMENT 2
            tgt = _psychic_shot_setup(rpc, rid, dec4, sorc4)
            dec4 = rpc("decisionView", {"runnerId": rid}, 150)
            sorc4 = next(iter(_units(dec4, SORC_VIS)), None)
            if tgt is not None and sorc4 is not None \
                    and hexgeo.distance(_pos(sorc4), _pos(tgt)) == 2:
                nab = next((ab.get("id") for u in (dec4.get("units") or [])
                            if u.get("id") == sorc4["id"]
                            for ab in (u.get("abilities") or []) if ab.get("kind") == "normal"),
                           None)
                rc = _apply(rpc, rid, {"kind": "ability", "casterId": sorc4["id"],
                                       "targetId": tgt["id"], "abilityType": nab})
                okc = ((rc or {}).get("actions") or [{}])[0].get("ok")
                dec5 = rpc("decisionView", {"runnerId": rid}, 150)
                n_c1 = len(_units(dec5, SCREAMER_VIS))
                print(f"[202c] C sorcier Psychic tour SUIVANT (ok={okc}): screamers "
                      f"{n_c0} -> {n_c1} (attendu +0, effet expire)")
                if n_c1 != n_c0:
                    fails.append("C:effet-persistant")
            else:
                print("[202c] C SKIP (sorcier hors portee au tour suivant)")
                fails.append("C:skip")
        else:
            print("[202c] C decisionView KO")
            fails.append("C:dec-ko")

        print(f"[202c] VERDICT: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}")
        return 0 if not fails else 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
