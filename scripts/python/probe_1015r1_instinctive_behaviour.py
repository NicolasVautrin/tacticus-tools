#!/usr/bin/env python
"""probe_1015r1_instinctive_behaviour -- le trait `InstinctiveBehaviour` (UnitTrait 0x7e5 = 2021),
ses DEUX faces, confrontees au natif.

CE QUE CE PROBE MESURE
----------------------
Le trait derive l'ability `TriggeredAbilityType.InstinctiveBehaviour` (0x413 = 1043) et l'owner-effet
`InstinctiveBehaviour_BlockMovement` (0x4d3 = 1235). Les deux faces sont SEPAREES, et elles se
mesurent separement -- DECIDER != EXECUTER :

  * **CIBLAGE** : `InstinctiveBehaviour_UpdateTargetAbility$$CreateBehaviour` ecrit le
    `ForcedAttackTargetsComponent` du porteur, que `UnitExtensions$$GetOnlyTargets` publie et que la
    regle `TargetIsAllowedForCaster` (bit 23) lit -> le porteur ne peut plus attaquer QUE l'ennemi le
    plus proche. Oracle natif : `abilityReason(caster, <attaque normale>, target)`.
  * **MOUVEMENT** : l'effet 1235 (`BlockUnitMovementEffect`) inscrit son id dans
    `MovementComponent+0x50` quand sa `CreateActiveCondition` est vraie -> `IsAllowedToMove` FAUX ->
    `UnitExtensions$$CanMove` FAUX -> `FindAnyOrAllMoveableTiles` sort a VIDE. Oracle natif :
    `aiMovableTiles` (= `MovementQuery$$GetMovableTilesFor`).

DEUX REGIMES, ET C'EST EUX QUI DISCRIMINENT
-------------------------------------------
La `CreateActiveCondition` de 1235 exige `Any(ForcedAttackTargets, IsInAttackOrAbilityRange(Owner,
It))` : la cible forcee doit etre DEJA a portee. Or `GetUpdatedForcedTarget` la cherche a
`NormalAttackRange + Movement`. Les deux ne coincident pas, et c'est la tout le sens du texte i2
(<< **If there are targets in range**, this unit does not move and attacks the closest target >>) :

    LOIN  (portee < d <= portee + mouvement) : cible forcee POSEE, mouvement LIBRE
    PRES  (d <= portee)                      : cible forcee POSEE, mouvement BLOQUE

Un probe qui ne mesurerait que le regime PRES ne distinguerait pas << l'effet bloque >> de
<< le port bloque tout porteur du trait >>.

TEMOIN NON NUL
--------------
Une unite SANS le trait, sur le MEME plateau et au MEME contact, doit rendre l'inverse sur les deux
faces (aucune cible forcee, mouvement libre). Sans ce temoin, un accord obtenu en regime degenere
(tout le monde bloque / personne n'est bloque) ne prouverait rien.

LE MONTAGE
----------
Le trait est FORCE sur une unite du pool (`--unit-stat "<vis>:Traits=[...]"`, levier qui mord sur
104 des 105 membres de l'enum) plutot que d'aller chercher un porteur naturel : les 23 porteurs sont
18 npc + 5 summons Tyranides, et un summon s'OBSERVE mais ne se COMMANDE pas (#291) -- on ne pourrait
pas le conduire aux deux regimes. Le forcage est LEGITIME ici parce que le natif derive l'ability DU
TRAIT (`AddTraitOperation$$AddDerivedAbilities`) : donner le trait, c'est exactement donner la
mecanique. La liste `Traits` est REMPLACEE, donc on la reconstruit depuis le gameconfig + 2021.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_1015r1_instinctive_behaviour.py
    python probe_1015r1_instinctive_behaviour.py --seed 31337 --board C4_09 \
        --carrier-vis tyranTyrantGuard --witness-vis ultraCalgar

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session                        # noqa: E402

import probe_247_splash_targeting as P247                            # noqa: E402

from engine.dsl.event_trigger_type import EventTriggerType           # noqa: E402
from engine.entities.effect_type import EffectType                   # noqa: E402
from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait              # noqa: E402
from engine.runner.abilities.targeting import get_only_targets       # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner import components as _components                  # noqa: E402
from engine.runner.operations.triggers.base import TriggerEvent      # noqa: E402
from engine.runner.operations.triggers.dispatch.core import (        # noqa: E402
    collect_triggered_abilities, evaluate_trigger_operation)
from engine.runner.snapshot import load_state                        # noqa: E402

NORMAL_ATTACK = 69                    # `Loki_NormalAttack` -- l'id CONCRET, jamais l'abstrait 17
BLOCK_MOVEMENT = int(EffectType.InstinctiveBehaviour_BlockMovement)   # 0x4d3 = 1235
INSTINCTIVE = int(UnitTrait.InstinctiveBehaviour)                     # 0x7e5 = 2021


def _traits_plus_instinctive(vis: str) -> str:
    """La liste `Traits` du gameconfig + `2021`, en JSON. `--unit-stat` REMPLACE le champ : omettre
    les traits d'origine ferait perdre `Hero`/faction/etc. et changerait autre chose que la variable
    testee."""
    import gameconfig as GC
    kit = GC.unit(vis) or {}
    noms = list(kit.get("traits") or [])
    ids = []
    for n in noms:
        m = getattr(UnitTrait, str(n), None)
        if m is not None:
            ids.append(int(m))
    if INSTINCTIVE not in ids:
        ids.append(INSTINCTIVE)
    return json.dumps(ids, separators=(",", ":"))


def _build(seed, board, p_units, a_units, unit_stats):
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais sous `data/`)."""
    state = P247.ROOT / "logs" / ("_probe1015r1-%d-%d.json" % (os.getpid(), next(P247._seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", ",".join(p_units), "--a-units", ",".join(a_units)]
    for us in unit_stats:
        argv += ["--unit-stat", us]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(P247.PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"]), state
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-800:])
        time.sleep(10)


def _capture(sid, rid):
    dv = P247._dv(sid, rid)
    ob = P247._r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = P247._r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    bg = P247._r(sid, "boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible")
    st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
    return dv, st


def _fire_port(st, uid: int) -> dict:
    """Fait tourner le PORT sur l'etat capte : inscription au registre, puis le vecteur
    `On(0x12 = TurnStart_EffectActivation)` (le bras INCONDITIONNEL d'`$$IsValidTrigger`, celui que
    `StartTurnOperation` emet a chaque tour). Rend le diagnostic + la liste forcee resultante."""
    inscrites = [type(a).__name__ for a in collect_triggered_abilities(st)
                 if type(a).__name__ == "InstinctiveBehaviourUpdateTargetAbility"
                 and int(a.owner_id) == int(uid)]
    res = evaluate_trigger_operation(st, TriggerEvent(
        int(EventTriggerType.TurnStart_EffectActivation), int(uid), int(uid),
        ranged=False, profile=None))
    mine = [r for r in res if r.get("trait") == "InstinctiveBehaviour"
            and int(r.get("owner", -1)) == int(uid)]
    return {"inscrite": bool(inscrites), "resultats": mine,
            "only_targets": [int(x) for x in (get_only_targets(st, int(uid)) or ())],
            # #590-r6-r2 : le foyer a demenage de `operations/turnflow.py` vers `runner/components.py`
            "can_move": _components.unit_extensions_can_move(st, int(uid)),
            "effets_actifs": sorted({int(e.effect_type) for e in
                                     (st.effects.active_effects(
                                         int(uid),
                                         __import__("engine.runner.components", fromlist=["x"])
                                         .unit_state_for_effects(st, int(uid)))
                                      if st.effects is not None else ())})}


def _live_traits(sid, rid, uid) -> list:
    """Les traits REELLEMENT montes sur l'entite, lus au canal `combatSnapshot`
    (`BaseUnitComponent` -> `UnitContext.traits`). `decisionView` ne les publie PAS ; s'y fier
    rendrait `[]` et ferait conclure a tort que le levier `--unit-stat Traits` ne mord pas."""
    snap = P247._r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    for u in (snap.get("units") or []):
        # ⚠ la cle d'identite de CE canal est `entityId` (pas `id`, qui n'existe pas ici) : lire
        # `id` rendait `None` sur les 4 unites et faisait conclure « trait non monte ».
        if int(u.get("entityId", -1)) == int(uid):
            raw = u.get("traits") or (u.get("ctx") or {}).get("traits") or []
            out = []
            for t in raw:
                if isinstance(t, int):
                    out.append(int(t))
                else:
                    m = getattr(UnitTrait, str(t), None)
                    if m is not None:
                        out.append(int(m))
            return out
    return []


def _nat_reason(sid, rid, cid, tid):
    """`abilityReason(caster, <attaque normale>, target)` -> le code de la regle CASSEE, en entier.

    On garde le payload BRUT dans le retour : un `None` de `_hexval` ne distingue pas << aucune
    regle cassee >> de << la reponse n'a pas la forme attendue >>, et c'est exactement le genre de
    silence qui ferait lire un montage rate comme un accord."""
    r = P247._nat(sid, rid, int(cid), NORMAL_ATTACK, int(tid))
    node = (r or {}).get("targetReason") if isinstance(r, dict) else None
    return P247._hexval(node), r


def _regime(sid, rid, carrier_vis, witness_vis, foe_id, want_d, label):
    """Amene le porteur a la distance `want_d` de `foe_id`, rend la main a son camp, puis MESURE les
    deux faces des DEUX cotes (natif / port) pour le porteur ET pour le temoin."""
    P247._bring_to_contact  # noqa: B018 (documente : on n'utilise pas le helper generique ici)
    for _ in range(12):
        d = P247._dv(sid, rid)
        u = P247._by_vis(d, carrier_vis)
        foe = next((x for x in (d.get("units") or []) if int(x["id"]) == int(foe_id)), None)
        if u is None or foe is None:
            break
        got = hexgeo.distance(P247._pos(u), P247._pos(foe))
        if got == want_d:
            break
        # On DEPLACE L'ENNEMI vers le porteur (jamais le porteur) : des qu'il est bloque, il ne
        # peut plus s'approcher -- c'est precisement le comportement mesure. `applyAction` ne
        # verifie pas la propriete du `unitId`.
        if not P247._step_toward(sid, rid, int(foe_id), P247._pos(u), want_d):
            P247._act(sid, rid, {"kind": "endturn"}, 60)
    P247._give_turn_to(sid, rid, carrier_vis)
    dv, st = _capture(sid, rid)
    cu, wu = P247._by_vis(dv, carrier_vis), P247._by_vis(dv, witness_vis)
    if cu is None:
        raise RuntimeError("porteur %s absent du plateau" % carrier_vis)
    cid = int(cu["id"])
    foe = next((x for x in (dv.get("units") or []) if int(x["id"]) == int(foe_id)), None)
    dist = hexgeo.distance(P247._pos(cu), P247._pos(foe)) if foe else None
    autres = [int(x["id"]) for x in (dv.get("units") or [])
              if x.get("alive") and x.get("owner") != cu.get("owner") and int(x["id"]) != int(foe_id)]
    port = _fire_port(st, cid)
    out = {
        "regime": label, "carrier": cid, "foe": int(foe_id), "dist": dist,
        "nat_movable": len(P247._movable(sid, rid, cid)),
        "port_can_move": port["can_move"],
        "port_only_targets": port["only_targets"],
        "port_inscrite": port["inscrite"],
        "port_effets_actifs": port["effets_actifs"],
        "port_resultats": port["resultats"],
        "autre": (autres[0] if autres else None),
    }
    rf, raw_f = _nat_reason(sid, rid, cid, foe_id)
    out["nat_reason_foe"] = rf
    out["nat_raw_foe"] = raw_f
    if autres:
        ra, raw_a = _nat_reason(sid, rid, cid, autres[0])
        out["nat_reason_autre"] = ra
        out["nat_raw_autre"] = raw_a
    else:
        out["nat_reason_autre"] = None
        out["nat_raw_autre"] = None
    if wu is not None:
        wid = int(wu["id"])
        wport = _fire_port(st, wid)
        out.update({"witness": wid, "wit_nat_movable": len(P247._movable(sid, rid, wid)),
                    "wit_port_can_move": wport["can_move"],
                    "wit_port_only_targets": wport["only_targets"],
                    "wit_dist": (hexgeo.distance(P247._pos(wu), P247._pos(foe)) if foe else None)})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--carrier-vis", default="tyranTyrantGuard")
    ap.add_argument("--witness-vis", default="ultraCalgar")
    ap.add_argument("--a-units", default="necroWarden,necroWarden")
    ap.add_argument("--far", type=int, default=3, help="distance du regime LOIN")
    a = ap.parse_args(argv)

    sid = _resolve_session()
    p_units = [a.carrier_vis, a.witness_vis]
    us = ["%s:Traits=%s" % (a.carrier_vis, _traits_plus_instinctive(a.carrier_vis))]
    rid, state_file = _build(a.seed, a.board, p_units, a.a_units.split(","), us)
    print("[build] runner=%d board=%s seed=%s porteur=%s temoin=%s"
          % (rid, a.board, a.seed, a.carrier_vis, a.witness_vis))
    print("[build] unit-stat = %s" % us[0])
    try:
        dv = P247._give_turn_to(sid, rid, a.carrier_vis)
        cu = P247._by_vis(dv, a.carrier_vis)
        if cu is None:
            print("[KO] porteur absent du plateau")
            return 1
        # LE TRAIT EST-IL REELLEMENT MONTE ? (le levier `--unit-stat Traits` mord-il ?)
        # ⚠ le canal des traits est `combatSnapshot` (`BaseUnitComponent`), PAS `decisionView` --
        # verifier la MUTATION avant de mesurer, jamais la supposer.
        traits = _live_traits(sid, rid, int(cu["id"]))
        print("[montage] traits LIVE du porteur u%s = %s" % (cu["id"], traits))
        if INSTINCTIVE not in traits:
            print("[KO] le trait 2021 n'est PAS monte cote natif -- montage rate")
            return 2
        foes = [x for x in (dv.get("units") or [])
                if x.get("alive") and x.get("owner") != cu.get("owner")]
        if not foes:
            print("[KO] aucun ennemi")
            return 3
        foe = min(foes, key=lambda f: hexgeo.distance(P247._pos(cu), P247._pos(f)))
        loin = _regime(sid, rid, a.carrier_vis, a.witness_vis, int(foe["id"]), a.far, "LOIN")
        print("[LOIN] " + json.dumps(loin, sort_keys=True))
        pres = _regime(sid, rid, a.carrier_vis, a.witness_vis, int(foe["id"]), 1, "PRES")
        print("[PRES] " + json.dumps(pres, sort_keys=True))
        data = {"loin": loin, "pres": pres, "runner": rid, "board": a.board, "seed": a.seed}
        print("[RAW] " + json.dumps(data, sort_keys=True))
        return _verdict(data)
    finally:
        try:
            P247._r(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception as exc:                                        # noqa: BLE001
            print("[warn] disposeRunner : %s" % exc)


def _verdict(data) -> int:
    """Les CINQ crans, chacun sur son etage. Aucun n'est un scalaire global."""
    loin, pres = data["loin"], data["pres"]
    ko = []
    if not (loin["port_inscrite"] and pres["port_inscrite"]):
        ko.append("le registre n'inscrit pas InstinctiveBehaviourUpdateTargetAbility")
    # 1. CIBLAGE -- le port pose une cible forcee dans les DEUX regimes.
    for r in (loin, pres):
        if not r["port_only_targets"]:
            ko.append("%s : port_only_targets VIDE" % r["regime"])
    # 2. CIBLAGE natif -- le refus `TargetIsAllowedForCaster` sur une AUTRE cible que la forcee.
    #    C'est LE cran qui prouve que le natif a, lui aussi, pose une cible forcee : sans une ligne
    #    REFUSEE, un accord ne distinguerait pas << le natif restreint comme nous >> de << personne
    #    ne restreint >>.
    for r in (loin, pres):
        if r["autre"] is not None and r["nat_reason_autre"] != int(TR.TargetIsAllowedForCaster):
            ko.append("%s : le natif ne refuse PAS l'autre cible (%s)"
                      % (r["regime"], r["nat_reason_autre"]))
        # 2bis. ET LA CIBLE FORCEE DU PORT EST CELLE DU NATIF : le natif ne pose PAS 0x800000 sur
        #       elle (elle peut etre refusee pour une AUTRE raison -- hors portee en regime LOIN).
        if r["nat_reason_foe"] == int(TR.TargetIsAllowedForCaster):
            ko.append("%s : le natif REFUSE aussi la cible que le port force (u%s) -- les deux "
                      "listes divergent" % (r["regime"], r["foe"]))
        if r["port_only_targets"] and int(r["port_only_targets"][0]) != int(r["foe"]):
            ko.append("%s : port_only_targets=%s alors que le natif force u%s"
                      % (r["regime"], r["port_only_targets"], r["foe"]))
    # 3. MOUVEMENT -- LOIN libre / PRES bloque, des DEUX cotes.
    if loin["nat_movable"] <= 0:
        ko.append("LOIN : le natif rend 0 tuile -- le regime n'est pas exerce")
    if loin["port_can_move"] is False:
        ko.append("LOIN : le port BLOQUE alors que le natif laisse bouger")
    if pres["nat_movable"] != 0:
        ko.append("PRES : le natif rend %d tuiles -- l'effet 1235 ne bloque pas"
                  % pres["nat_movable"])
    if pres["port_can_move"] is not False:
        ko.append("PRES : le port laisse bouger alors que le natif bloque")
    # 4. L'EFFET 1235 est bien porte cote port.
    for r in (loin, pres):
        if BLOCK_MOVEMENT not in (r["port_effets_actifs"] or []) and r["regime"] == "PRES":
            ko.append("PRES : 1235 n'est pas ACTIF cote port (%s)" % r["port_effets_actifs"])
    # 5. TEMOIN NON NUL -- l'unite sans le trait n'est ni ciblee-forcee ni bloquee.
    for r in (loin, pres):
        if r.get("witness") is None:
            ko.append("%s : temoin absent" % r["regime"])
            continue
        if r["wit_port_only_targets"]:
            ko.append("%s : le TEMOIN a des cibles forcees %s"
                      % (r["regime"], r["wit_port_only_targets"]))
        if r["wit_port_can_move"] is False or r["wit_nat_movable"] <= 0:
            ko.append("%s : le TEMOIN est bloque (nat=%s port=%s)"
                      % (r["regime"], r["wit_nat_movable"], r["wit_port_can_move"]))
    for m in ko:
        print("[KO] " + m)
    print("[OK] les cinq crans passent" if not ko else "[VERDICT] %d ecart(s)" % len(ko))
    return 0 if not ko else 1


if __name__ == "__main__":
    raise SystemExit(main())
