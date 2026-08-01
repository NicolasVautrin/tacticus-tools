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
    """dv / observeBattle / combatSnapshot / boardGraph -> (dv, payloads). Le State se construit a
    part (`_mk_state`) parce qu'on en veut DEUX depuis les MEMES payloads : l'un que le port MUTE,
    l'autre laisse VIERGE (la baseline « ce que master rendait », sur la MEME geometrie)."""
    dv = P247._dv(sid, rid)
    ob = P247._r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = P247._r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    bg = P247._r(sid, "boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible")
    return dv, (dv, ob, snap, bg)


def _mk_state(payloads):
    dv, ob, snap, bg = payloads
    return load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))


def _make_adjacent(sid, rid, vis, rounds=14):
    """Amene `vis` AU CONTACT d'un ennemi, et rend l'id de cet ennemi (ou None).

    On DEPLACE LES DEUX (`applyAction` ne verifie pas la propriete du `unitId`) : le porteur VERS
    l'ennemi le plus proche, ET cet ennemi VERS le porteur. La geometrie de spawn n'est jamais une
    excuse -- et le seul mouvement du porteur ne suffit pas quand les tuiles a d=1 sont occupees par
    les autres ennemis (MESURE : premier jet bloque a d=2, cast refuse, `mutated=false`)."""
    for _ in range(rounds):
        d = P247._dv(sid, rid)
        u = P247._by_vis(d, vis)
        if u is None:
            return None
        foes = [f for f in d["units"]
                if f.get("alive") and f.get("owner") != u.get("owner")]
        if not foes:
            return None
        near = min(foes, key=lambda f: hexgeo.distance(P247._pos(u), P247._pos(f)))
        dd = hexgeo.distance(P247._pos(u), P247._pos(near))
        print("  [contact] %s@%s  cible u%s@%s  d=%d"
              % (vis, P247._pos(u), near["id"], P247._pos(near), dd))
        if dd <= 1:
            return int(near["id"])
        moved = P247._step_toward(sid, rid, int(near["id"]), P247._pos(u), 1)
        d = P247._dv(sid, rid)
        u2 = P247._by_vis(d, vis)
        n2 = next((f for f in d["units"] if int(f["id"]) == int(near["id"])), None)
        if u2 is not None and n2 is not None:
            moved = P247._step_toward(sid, rid, int(u2["id"]), P247._pos(n2), 1) or moved
        if not moved:
            P247._act(sid, rid, {"kind": "endturn"}, 60)
    return None


def _bring_within(sid, rid, vis, pivot_id, want, rounds=8):
    """Amene `vis` a la distance `want` de l'entite `pivot_id` (best effort). Rend la distance
    ATTEINTE, mesuree -- jamais supposee."""
    for _ in range(rounds):
        d = P247._dv(sid, rid)
        u = P247._by_vis(d, vis)
        piv = next((x for x in d["units"] if int(x["id"]) == int(pivot_id)), None)
        if u is None or piv is None:
            return None
        got = hexgeo.distance(P247._pos(u), P247._pos(piv))
        if got == want:
            return got
        if not P247._step_toward(sid, rid, int(u["id"]), P247._pos(piv), want):
            P247._act(sid, rid, {"kind": "endturn"}, 60)
    d = P247._dv(sid, rid)
    u = P247._by_vis(d, vis)
    piv = next((x for x in d["units"] if int(x["id"]) == int(pivot_id)), None)
    return None if (u is None or piv is None) else hexgeo.distance(P247._pos(u), P247._pos(piv))


def _effects_of(dv, uid):
    """Les effets LIVE de l'unite -- `decisionView.units[].effects` (canal `readEffectsByUnit`).
    ⚠ Ce canal ne publie NI le `BondComponent` de l'entite-effet NI son `BondedEntityId` : il n'a
    que `source` (`EffectComponent.SourceUnitId @+0x10`). Cf. le residu nomme dans l'en-tete."""
    for u in (dv.get("units") or []):
        if int(u.get("id") or -1) == int(uid):
            return [(e.get("name"), e.get("effectType"), e.get("source"))
                    for e in (u.get("effects") or [])]
    return []


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

        # GEOMETRIE. Le futur TAUNTE n'est PAS choisi d'avance : on amene le tauntant au CONTACT
        # (CrushingClaws = `RANGE_ADJACENT`) et on prend l'ennemi qu'il touche. Le second ennemi du
        # taunte -- `ultraCalgar` -- est ensuite amene A PORTEE de son attaque normale (necroWarden
        # est ranged r3), pour que le refus attendu ne puisse pas etre confondu avec un refus de
        # PORTEE. Ce n'est pas indispensable (la regle 23 PRECEDE le volet portee dans la cascade),
        # c'est ce qui rend la mesure non ambigue.
        tauntee_id = _make_adjacent(sid, rid, "tyranTyrantGuard")
        if tauntee_id is None:
            print("[FAIL] impossible d'amener tyranTyrantGuard au contact")
            return 2
        # `ultraCalgar` AU CONTACT lui aussi, et c'est LOAD-BEARING : `necroWarden` est RANGED, et
        # un caster ranged ADJACENT a un ennemi est clampe en melee
        # (`TargetingOptions.forceMeleeTarget = RangedBool.IfRangedCaster` du preset d'attaque
        # normale -> `should_apply_ranged_in_melee`). MESURE du premier jet, avec Calgar a d=2 : le
        # natif rendait deja `0x8000000 TargetIsInRange` AVANT tout taunt -- la ligne restait
        # discriminante (le taunt la fait passer a `0x800000`, ce qui prouve au passage que la
        # regle 23 PRECEDE le volet portee) mais elle ne montrait plus la degradation PERMISSIVE.
        # A d=1 les deux ennemis sont acceptes avant le taunt : c'est la ligne « le port acceptait,
        # le natif refuse » que le brief exige.
        d_cal = _bring_within(sid, rid, "ultraCalgar", tauntee_id, 1)
        print("[geometrie] taunte=u%d ; ultraCalgar a d=%s du taunte" % (tauntee_id, d_cal))

        P247._give_turn_to(sid, rid, "tyranTyrantGuard")
        dv_pre, pre_payloads = _capture(sid, rid)
        guard = P247._by_vis(dv_pre, "tyranTyrantGuard")
        calgar = P247._by_vis(dv_pre, "ultraCalgar")
        tgt_u = next((u for u in dv_pre["units"]
                      if int(u["id"]) == tauntee_id and u.get("alive")), None)
        if guard is None or calgar is None or tgt_u is None:
            print("[FAIL] casters/cible absents apres montage")
            return 2
        cid = int(guard["id"])
        print("[geometrie] tauntant u%d(tyranTyrantGuard) d=%d ; autre-ennemi u%d(ultraCalgar) d=%d"
              % (cid, hexgeo.distance(P247._pos(guard), P247._pos(tgt_u)),
                 int(calgar["id"]), hexgeo.distance(P247._pos(calgar), P247._pos(tgt_u))))

        # ---------------------------------------------------------------- BASELINE (avant taunt)
        # DEUX baselines, et elles ne disent pas la meme chose :
        #   `natAvant` = le NATIF avant le cast -> montre qu'il ACCEPTAIT les deux ennemis ;
        #   `portAvant` = le PORT sur un etat VIERGE (le meme snapshot, jamais mute) -> c'est
        #                 EXACTEMENT ce que `master` rendait, sur la MEME geometrie.
        probe_apres = _NormalAttackTargeting()
        probe_desarme = _NormalAttackIgnoringTaunt()
        st_vierge = _mk_state(pre_payloads)
        nat_avant, port_avant = {}, {}
        for u in dv_pre["units"]:
            if not u.get("alive"):
                continue
            tid = int(u["id"])
            nat = P247._nat(sid, rid, tauntee_id, NORMAL_ATTACK, tid)
            nat_avant[tid] = P247._hexval((nat or {}).get("targetReason") or {})
            port_avant[tid] = int(get_invalid_target_reason(st_vierge, tauntee_id, tid,
                                                            probe_apres))
        print("[baseline natif  ] %s"
              % {k: (None if v is None else hex(v)) for k, v in sorted(nat_avant.items())})
        print("[baseline port   ] %s" % {k: hex(v) for k, v in sorted(port_avant.items())})
        accord_avant = sum(1 for t in nat_avant if nat_avant[t] == port_avant.get(t))
        print("[baseline accord ] %d/%d" % (accord_avant, len(nat_avant)))

        # ---------------------------------------------------------------- ETAGE A : vecteur de pose
        klass = ABILITY_CLASSES[CRUSHING]
        st_port = _mk_state(pre_payloads)
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
        dv_post, post_payloads = _capture(sid, rid)
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
        print("  %-28s %-5s %-3s %-12s %-26s %-11s %-11s %-11s %-11s"
              % ("cible", "id", "d", "natif", "regle natif", "port", "natAvant", "portAvant",
                 "desarme"))
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
            na, pa = nat_avant.get(tid), port_avant.get(tid)
            agree = (nv == pv)
            n_rows += 1
            n_agree += 1 if agree else 0
            if nv == int(TR.TargetIsAllowedForCaster):
                n_refus23 += 1
                if pa == 0:
                    n_gain += 1
            if dv_ != pv:
                cf_desarme += 1
            print("  %-28s %-5d %-3d %-12s %-26s %-11s %-11s %-11s %-11s %s"
                  % (("%s%s" % ("CASTER " if tid == tauntee_id else "",
                                u.get("visualId")))[:28],
                     tid, hexgeo.distance(tpos, P247._pos(u)),
                     "-" if nv is None else hex(nv),
                     ",".join(tr.get("reasons") or [])[:26] or "-",
                     hex(pv), "-" if na is None else hex(na),
                     "-" if pa is None else hex(pa), hex(dv_),
                     "OK" if agree else "MISMATCH"))
            rows.append({"target": tid, "vis": u.get("visualId"), "nat": nv, "port": pv,
                         "natAvant": na, "portAvant": pa, "desarme": dv_})

        okB = (n_agree == n_rows and n_refus23 > 0 and n_gain > 0
               and any(r["nat"] == 0 for r in rows))
        print("  [bilan B] accord %d/%d ; lignes refusees 0x800000 par le natif : %d ; "
              "dont le port AVANT ACCEPTAIT (0x0) : %d ; au moins une ligne ACCEPTEE : %s"
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
