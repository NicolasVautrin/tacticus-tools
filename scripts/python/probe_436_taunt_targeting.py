#!/usr/bin/env python
"""probe_436_taunt_targeting -- la regle de ciblage `TargetIsAllowedForCaster` (bit 23, le TAUNT).

CE QUE CE PROBE MESURE
----------------------
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (surcharge 7 arguments) porte une
regle qui n'est PAS armee par son propre bit :

    if ((rules >> 0xe & 1) != 0 || (rules >> 0x39 & 1) != 0) {     // TargetIsEnemy | TargetIsCasterOrEnemy
        if ((rules >> 0x28 & 1) == 0) {                            // !AllowIgnoreForcedAttackTarget
            list = UnitExtensions.GetOnlyTargets(caster);
            if (0 < list.Count && la cible resolue n'y figure pas) -> broken(0x800000);
        }
    }

Son bit 23 n'est JAMAIS teste : il n'est que le CODE RENDU. D'ou le compte « 0 porteur » que
rendait tout recensement PAR LE BIT (#429) alors que **59** abilities du registre l'ARMENT -- plus
l'ATTAQUE NORMALE, dont le preset vaut `0x4002` (`TargetIsEnemy | TargetMatchesDynamicRule`).

LA DEGRADATION EST PERMISSIVE : sans la regle, `get_invalid_target_reason` ACCEPTE des casts que le
natif REFUSE. Un accord sur un cast ACCEPTE ne prouve donc RIEN. Ce probe est construit autour du
REFUS : il faut une ligne ou le natif rend `0x800000` et ou le port, avant la tranche, rendait `0`.

LE MONTAGE, ET POURQUOI CELUI-LA
--------------------------------
La liste `GetOnlyTargets` a QUATRE ecrivains natifs ; le seul dont un porteur soit confrontable est
`IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal` (effet 27 `Taunted_OnlySpecificTargets`),
qui pose `liste := [ABondEffect.BondedEntityId]`. Deux abilities PORTEES le castent, et
`CrushingClaws` (1105) l'a sur un HEROS du pool : `tyranTyrantGuard`.

    tyranTyrantGuard  --CrushingClaws(1105)-->  necroWarden  (effet 27, bonded = le CASTER)
    puis : le necroWarden TAUNTE ne peut plus attaquer que tyranTyrantGuard.

Le canal d'observation est l'ATTAQUE NORMALE (`Loki_NormalAttack`, id 69 sur ces unites) : le taunt
pose aussi `Taunted_CantUseAbility` (26), donc les abilities ACTIVES du taunte sont fermees par un
autre chemin -- l'attaque normale, elle, reste ouverte et son masque ARME la regle.

⚠ L'ORDRE DE LA CASCADE FAIT LE TRAVAIL : la regle 23 precede le volet PORTEE. Une cible hors
portee rend donc `0x800000`, pas `TargetIsInRange`. On place quand meme le second ennemi A PORTEE
(necroWarden est ranged r3) pour que le refus ne puisse pas etre confondu avec un refus de portee.

TROIS ETAGES, mesures separement (jamais un scalaire global)
------------------------------------------------------------
  A. VECTEUR DE POSE (offline) -- l'arbre DSL `crushing_claws_tree` du port, rejoue sur l'etat
     PRE-cast, doit produire `get_only_targets(taunte) == [caster]`. C'est le 5e argument
     `bondedEntity` d'`IdunBattleLogic.Entities.DSLBehaviors$$AddBondEffect` qui le decide.
  B. LA REGLE (live) -- accord natif/port du gate d'attaque normale du TAUNTE, cible par cible.
     Le natif = `abilityReason(casterId=taunte, abilityType=69, targetId=X)` ; le port =
     `get_invalid_target_reason` sur l'etat que le PORT a mute (etage A), donc les DEUX faces font
     tout le chemin cast -> taunt -> gate.
  C. LE DESARMEMENT (offline) -- le meme etat avec `AllowIgnoreForcedAttackTarget` (bit 40) pose
     sur le masque : le port doit ACCEPTER. NON CONFRONTE au natif : aucune ability du registre ne
     pose ce bit, donc aucun cast live ne l'exerce.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_436_taunt_targeting.py
    python probe_436_taunt_targeting.py --seed 31337 --board C4_09

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace as _replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

import probe_247_splash_targeting as P247                            # noqa: E402

from engine.entities.effect_type import EffectType                   # noqa: E402
from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import (                      # noqa: E402
    NORMAL_ATTACK_TARGETING_OPTIONS, _NormalAttackTargeting,
    get_invalid_target_reason, get_only_targets)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

CRUSHING = 1105                       # `CrushingClaws`, porteur `tyranTyrantGuard` (HERO, au pool)
NORMAL_ATTACK = 69                    # `Loki_NormalAttack` -- l'id CONCRET, jamais l'abstrait 17
TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)      # 27
P_UNITS = ["tyranTyrantGuard", "ultraCalgar"]
A_UNITS = ["necroWarden", "necroWarden"]


class _NormalAttackIgnoringTaunt(_NormalAttackTargeting):
    """Etage C : le masque de l'attaque normale + `AllowIgnoreForcedAttackTarget` (bit 40). Le natif
    DESARME la regle des que ce bit est pose -- contrefactuel du champ, pas du code."""
    TARGETING_OPTIONS = _replace(
        NORMAL_ATTACK_TARGETING_OPTIONS,
        rules=int(NORMAL_ATTACK_TARGETING_OPTIONS.rules) | int(TR.AllowIgnoreForcedAttackTarget))


def _capture(sid, rid):
    """dv / observeBattle / combatSnapshot / boardGraph -> (dv, State)."""
    dv = P247._dv(sid, rid)
    ob = P247._r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = P247._r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    bg = P247._r(sid, "boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible")
    return dv, load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))


def _place(sid, rid, pivot_vis, wants):
    """Amene chaque `(visualId, distance)` de `wants` a la distance voulue du PIVOT. On DEPLACE les
    deux camps (`applyAction` ne verifie pas la propriete du `unitId`) -- « bloque par la geometrie
    de spawn » n'est pas un verdict."""
    for _ in range(10):
        d = P247._dv(sid, rid)
        piv = P247._by_vis(d, pivot_vis)
        if piv is None:
            raise RuntimeError("pivot %s absent" % pivot_vis)
        pp = P247._pos(piv)
        todo = []
        for vis, want in wants:
            u = P247._by_vis(d, vis)
            if u is None:
                raise RuntimeError("unite %s absente" % vis)
            got = hexgeo.distance(pp, P247._pos(u))
            if got != want:
                todo.append((int(u["id"]), want, got))
        print("  [place] pivot=%s@%s  %s" % (pivot_vis, pp,
                                             " ".join("%s:d=%d(vise %d)" % (v, g, w)
                                                      for (v, w), (_i, _w, g)
                                                      in zip(wants, todo)) or "OK"))
        if not todo:
            return
        moved = False
        for uid, want, _got in todo:
            moved = P247._step_toward(sid, rid, uid, pp, want) or moved
        if not moved:
            P247._act(sid, rid, {"kind": "endturn"}, 60)
    print("  [place] geometrie PARTIELLE acceptee (les distances REELLES sont mesurees)")


def _effects_of(dv, uid):
    out = []
    for e in (dv.get("effects") or []):
        if int(e.get("unitId") or -1) == int(uid):
            out.append((e.get("name"), e.get("effectType"), e.get("source")))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args(argv)

    sid = _resolve_session()
    rid, state_file = P247._build(sid, a.seed, a.board, P_UNITS)
    print("[build] runner=%d board=%s seed=%s p_units=%s a_units=%s"
          % (rid, a.board, a.seed, ",".join(P_UNITS), ",".join(A_UNITS)))
    try:
        for _ in range(P247.WARMUP_ENDTURNS):
            P247._act(sid, rid, {"kind": "endturn"}, 60)

        # GEOMETRIE : le futur TAUNTE est le pivot. Le tauntant au CONTACT (CrushingClaws =
        # RANGE_ADJACENT), l'autre ennemi a d=2 (dans la portee r3 du necroWarden : le refus qu'on
        # attend ne pourra pas etre confondu avec un refus de PORTEE).
        d0 = P247._dv(sid, rid)
        foes = sorted((u for u in d0["units"]
                       if u.get("alive") and u.get("visualId") == "necroWarden"),
                      key=lambda u: int(u["id"]))
        if len(foes) < 2:
            print("[FAIL] il faut 2 necroWarden vivants")
            return 2
        tauntee_id = int(foes[0]["id"])
        pivot_vis = "necroWarden"
        # le pivot est le PREMIER necroWarden : on place les deux unites de team 1 autour de lui.
        for _ in range(10):
            d = P247._dv(sid, rid)
            piv = next((u for u in d["units"] if int(u["id"]) == tauntee_id and u.get("alive")),
                       None)
            if piv is None:
                print("[FAIL] taunte u%d mort/absent avant le cast" % tauntee_id)
                return 2
            pp = P247._pos(piv)
            todo = []
            for vis, want in (("tyranTyrantGuard", 1), ("ultraCalgar", 2)):
                u = P247._by_vis(d, vis)
                if u is None:
                    print("[FAIL] %s absent" % vis)
                    return 2
                got = hexgeo.distance(pp, P247._pos(u))
                if got != want:
                    todo.append((int(u["id"]), want, got, vis))
            print("  [place] taunte=u%d@%s  %s" % (tauntee_id, pp,
                                                   " ".join("%s d=%d(vise %d)" % (v, g, w)
                                                            for _i, w, g, v in todo) or "OK"))
            if not todo:
                break
            moved = False
            for uid, want, _got, _vis in todo:
                moved = P247._step_toward(sid, rid, uid, pp, want) or moved
            if not moved:
                P247._act(sid, rid, {"kind": "endturn"}, 60)

        P247._give_turn_to(sid, rid, "tyranTyrantGuard")
        dv_pre, st_pre = _capture(sid, rid)
        guard = P247._by_vis(dv_pre, "tyranTyrantGuard")
        calgar = P247._by_vis(dv_pre, "ultraCalgar")
        if guard is None or calgar is None:
            print("[FAIL] casters absents apres montage")
            return 2
        cid = int(guard["id"])
        print("[geometrie] tauntant u%d(tyranTyrantGuard) d=%d ; autre-ennemi u%d(ultraCalgar) d=%d"
              % (cid, hexgeo.distance(P247._pos(guard), P247._pos(foes[0])),
                 int(calgar["id"]), hexgeo.distance(P247._pos(calgar), P247._pos(foes[0]))))

        # ---------------------------------------------------------------- BASELINE (avant taunt)
        base = {}
        for u in dv_pre["units"]:
            if not u.get("alive"):
                continue
            tid = int(u["id"])
            nat = P247._nat(sid, rid, tauntee_id, NORMAL_ATTACK, tid)
            base[tid] = P247._hexval((nat or {}).get("targetReason") or {})
        print("[baseline attaque normale du futur taunte] %s"
              % {k: (None if v is None else hex(v)) for k, v in sorted(base.items())})

        # ---------------------------------------------------------------- ETAGE A : vecteur de pose
        klass = ABILITY_CLASSES[CRUSHING]
        st_port = st_pre
        res = klass().execute_behaviour(st_port, cid, tauntee_id)
        only_port = get_only_targets(st_port, tauntee_id)
        okA = (only_port == [cid])
        print("\n=== ETAGE A -- vecteur de pose (offline, arbre `crushing_claws_tree`)")
        print("  get_only_targets(port, u%d) = %s   attendu [%d] (le CASTER = `bondedEntity`)"
              % (tauntee_id, only_port, cid))
        print("  execute_behaviour -> %s" % (json.dumps(res)[:160] if res else res))
        print("  [A] %s" % ("PASS" if okA else "FAIL"))

        # ---------------------------------------------------------------- LE CAST NATIF
        act = {"kind": "ability", "casterId": cid, "abilityType": CRUSHING,
               "targetId": tauntee_id}
        r = P247._act(sid, rid, act, 120)
        acts = ((r or {}).get("actions") or [{}])[0]
        print("\n[cast natif] CrushingClaws u%d -> u%d : mutated=%s"
              % (cid, tauntee_id, acts.get("mutated")))
        if not acts.get("mutated"):
            print("[FAIL] le cast natif n'a pas mute l'etat -> pas de taunt, rien a mesurer")
            return 2
        dv_post, st_post = _capture(sid, rid)
        eff = _effects_of(dv_post, tauntee_id)
        has27 = any(int(e[1] or -1) == TAUNTED for e in eff)
        print("[effets natifs sur u%d] %s" % (tauntee_id, eff))
        alive_nat = any(int(u["id"]) == tauntee_id and u.get("alive") for u in dv_post["units"])
        if not (has27 and alive_nat):
            print("[FAIL] taunte : effet27=%s vivant=%s -> montage rate" % (has27, alive_nat))
            return 2

        # ---------------------------------------------------------------- ETAGE B : la regle
        print("\n=== ETAGE B -- la REGLE (natif vs port, attaque normale %d du TAUNTE u%d)"
              % (NORMAL_ATTACK, tauntee_id))
        print("  %-30s %-5s %-3s %-12s %-28s %-11s %-11s %-11s"
              % ("cible", "id", "d", "natif", "regle natif", "port", "AVANT", "desarme"))
        probe_apres = _NormalAttackTargeting()
        probe_desarme = _NormalAttackIgnoringTaunt()
        n_agree = n_rows = n_refus23 = n_gain = 0
        cf_desarme = 0
        rows = []
        tpos = P247._pos(next(u for u in dv_post["units"] if int(u["id"]) == tauntee_id))
        for u in dv_post["units"]:
            if not u.get("alive"):
                continue
            tid = int(u["id"])
            nat = P247._nat(sid, rid, tauntee_id, NORMAL_ATTACK, tid)
            tr = (nat or {}).get("targetReason") or {}
            nv = P247._hexval(tr)
            pv = int(get_invalid_target_reason(st_port, tauntee_id, tid, probe_apres))
            dv_ = int(get_invalid_target_reason(st_port, tauntee_id, tid, probe_desarme))
            av = base.get(tid)
            agree = (nv == pv)
            n_rows += 1
            n_agree += 1 if agree else 0
            if nv == int(TR.TargetIsAllowedForCaster):
                n_refus23 += 1
                if av == 0:
                    n_gain += 1
            if dv_ != pv:
                cf_desarme += 1
            print("  %-30s %-5d %-3d %-12s %-28s %-11s %-11s %-11s %s"
                  % (("%s%s" % ("CASTER " if tid == tauntee_id else "",
                                u.get("visualId")))[:30],
                     tid, hexgeo.distance(tpos, P247._pos(u)),
                     "-" if nv is None else hex(nv),
                     ",".join(tr.get("reasons") or [])[:28] or "-",
                     hex(pv), "-" if av is None else hex(av), hex(dv_),
                     "OK" if agree else "MISMATCH"))
            rows.append({"target": tid, "vis": u.get("visualId"), "nat": nv, "port": pv,
                         "avant": av, "desarme": dv_})

        okB = (n_agree == n_rows and n_refus23 > 0 and n_gain > 0
               and any(r["nat"] == 0 for r in rows))
        print("  [bilan B] accord %d/%d ; lignes refusees 0x800000 par le natif : %d ; "
              "dont le port AVANT acceptait : %d ; au moins une ligne ACCEPTEE : %s"
              % (n_agree, n_rows, n_refus23, n_gain,
                 "OUI" if any(r["nat"] == 0 for r in rows) else "NON"))
        print("  [B] %s" % ("PASS" if okB else "FAIL"))

        # ---------------------------------------------------------------- ETAGE C : desarmement
        okC = (cf_desarme > 0)
        print("\n=== ETAGE C -- DESARMEMENT `AllowIgnoreForcedAttackTarget` (offline, NON CONFRONTE)")
        print("  lignes que le bit 40 fait basculer : %d / %d  -> %s"
              % (cf_desarme, n_rows, "PASS" if okC else "FAIL"))
        print("  NON CONFRONTE au natif : aucune ability du registre ne pose ce bit "
              "(probe_429 : PERMISSION testee, 0 porteur) -- aucun cast live ne l'exerce.")

        allok = okA and okB and okC
        print("\n[VERDICT] %s" % ("PASS" if allok else "FAIL"))
        print("[RAW] " + json.dumps({"tauntee": tauntee_id, "caster": cid,
                                     "only_targets_port": only_port, "rows": rows}))
        return 0 if allok else 1
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            state_file.unlink(missing_ok=True)
            print("[cleanup] runner %d dispose" % rid)
        except Exception as e:                                       # noqa: BLE001
            print("[cleanup] dispose KO: %s" % e)


if __name__ == "__main__":
    sys.exit(main())
