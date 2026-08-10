"""#503-r4 -- LA VENTILATION PAR COUP NATIVE DU TIR DIFFERE `1237`, prise par `hit-trace`.

CE QUE CE PROBE REFUTE. La fiche `#503-r4` declare `BLOCAGE: capteur` et nomme
`IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget` comme « point d'ancrage a
hooker ». Mesure du 2026-08-10 : **le capteur EXISTE DEJA et repond**. C'est
`frida/hooks/features/hit-trace.ts`, qui hooke
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` -- l'etage EN DESSOUS de celui qu'on
croyait devoir poser -- et son en-tete nomme litteralement le blocage de #503-r4 :

    « Certains vecteurs ne rendent RIEN d'observable : `martial_apotheosis` (declenchement au debut
      de tour) donne `applyAction endturn` + `captureEvents` = 1 action / 0 event, donc aucun coup
      individuel visible. »

Il s'arme par RPC (`hitTraceArm`), donc **sans reinject** :

    hitTraceArm -> {"ok": true, "installed": true, "on": true}

Le residu n'etait donc pas bloque par un capteur manquant, mais par le fait que ce capteur-la
n'avait pas ete essaye. `BLOCAGE: capteur` -> `BLOCAGE: aucun`.

================================================================================================
CE QUE CE CAPTEUR REND, ET CE QU'IL NE REND PAS
================================================================================================
REND : par coup, `hitIndex`, `attackerId`, `defenderId`, `profile` (DamageProfileType brut), dans
l'ORDRE d'execution. C'est exactement la ventilation que la fiche declarait inaccessible : elle
tranche le CARDINAL par cible et l'ORDRE des cibles.

NE REND PAS : le MONTANT du coup. `ExecuteHit(hitIndex, attacker, defender, damageProfileType,
abilityOrEffect, attackDamageOptions, initialHealth, deniedDamage)` porte pourtant `initialHealth`
en 7e argument -- les PV AVANT le coup, donc le montant par difference -- mais le hook calibre
seulement trois slots (`hitIndex = attacker-1`, `profile = attacker+2`) et ne le lit pas. L'y
ajouter est une edition de `frida/hooks/*`, donc une FENETRE DE REINJECT : c'est dit dans le
rapport, pas contourne.

CE QUE LA MESURE SANS MONTANT TRANCHE QUAND MEME, et c'est le point : l'ecart de #503-r4 est
`u83` port **12049** vs natif **10957**, `u81` **bit-exact**. Deux causes restaient ouvertes apres
l'elimination de block / ordre / crit :
  (a) le natif n'a pas fait le MEME NOMBRE de coups sur `u83` ;
  (b) il en a fait autant, et l'ecart est un etage d'APPLICATION du montant.
Le cardinal par cible SEPARE (a) de (b) -- sans lui, les deux restent indistinguables, et c'est
exactement la position ou la fiche s'est arretee.

================================================================================================
DISCIPLINE
================================================================================================
`hit-trace` est sur le chemin de degat le plus chaud du jeu et n'est JAMAIS auto-arme. Ce probe
l'arme JUSTE AVANT l'`endturn` qui declenche le tir et le desarme dans un `finally` -- y compris
sur exception. Il dispose SON runner, jamais ceux des autres.

    python probe_503r4_ventilation_par_coup.py [--state-file <chemin ABSOLU>]

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import probe_503r1_overwhelming_wrath_phase2 as P

LOGS = Path(__file__).resolve().parents[2] / "logs"


def _rpc(sid: int, method: str, body: dict, timeout: int = 90):
    return P.rpc(sid, method, body, timeout)


def mesurer(sid: int, state_name: str = "probe_503r4_ventilation_par_coup") -> dict:
    """Rejoue le montage de #503-r1 en ARMANT `hit-trace` sur le seul `endturn` du tir.

    Le montage (board, seed, placements, unites) est celui de
    `probe_503r1_overwhelming_wrath_phase2.measure` -- on ne le re-invente pas : une divergence de
    montage rendrait les deux mesures incomparables, et c'est la comparaison qui est tout l'objet.
    """
    LOGS.mkdir(parents=True, exist_ok=True)
    state_path = LOGS / ("%s.json" % state_name)
    rid = P.build(state_path, [
        "--seed", "777", "--board", P.BOARD,
        "--p-units", "worldEightbound,worldJakhal",
        "--a-units", "orksNob,orksRuntherd",
        "--place", "worldEightbound:2,3", "--place", "worldJakhal:1,1",
        "--a-place", "orksNob:2,4", "--a-place", "orksRuntherd:3,3"])
    arme = False
    try:
        P.bind_transport(sid)
        dec0 = P.decision(sid, rid)
        caster = P.find(dec0, "worldEightbound")
        if caster is None:
            raise AssertionError("SCENARIO NON MONTE : worldEightbound absent du decisionView")
        caster_id = int(caster["id"])
        at = _rpc(sid, "abilityTargets",
                  {"runnerId": rid, "unitId": caster_id,
                   "abilityType": P.OVERWHELMING_WRATH}) or {}
        row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster_id), None)
        ab = next((a for a in ((row or {}).get("abilities") or [])
                   if int(a.get("abilityId", -1)) == P.OVERWHELMING_WRATH), {})
        from_here = [t.get("targetId") for t in (ab.get("fromHere") or [])]
        if not from_here:
            raise AssertionError("SCENARIO NON MONTE : aucune cible legale SUR PLACE pour 1141")
        target_id = int(from_here[0])

        # --- le CAST, puis le tour ENNEMI (temoin negatif : rien ne doit partir) -------------
        _rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster_id,
            "abilityType": P.OVERWHELMING_WRATH, "targetId": target_id}})
        _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}})
        hp_avant = P.hp_live(sid, rid)

        # --- ARMEMENT juste avant le tir, et RESET pour ne capter QUE ce pas ------------------
        _rpc(sid, "hitTraceReset", {"runnerId": rid}, 30)
        _rpc(sid, "hitTraceArm", {"runnerId": rid}, 30)
        arme = True
        act = _rpc(sid, "applyAction",
                   {"runnerId": rid, "captureEvents": True,
                    "action": {"kind": "endturn"}}) or {}
        trace = _rpc(sid, "hitTrace", {"runnerId": rid, "limit": 200}, 30) or {}
        hp_apres = P.hp_live(sid, rid)

        coups = trace.get("hits") or trace.get("entries") or trace.get("items") or []
        par_cible: dict = {}
        for h in coups:
            d = h.get("defenderId")
            if d is None:
                continue
            par_cible.setdefault(int(d), []).append(
                {"hitIndex": h.get("hitIndex"), "attacker": h.get("attackerId"),
                 "profile": h.get("profile")})
        return {
            "rid": rid, "caster": caster_id, "target": target_id,
            "hp_avant": hp_avant, "hp_apres": hp_apres,
            "delta_hp": {k: int(hp_avant.get(k, 0)) - int(v)
                         for k, v in (hp_apres or {}).items()
                         if int(hp_avant.get(k, 0)) != int(v)},
            "coups_natifs": coups,
            "cardinal_par_cible": {k: len(v) for k, v in par_cible.items()},
            "ordre_des_cibles": [h.get("defenderId") for h in coups],
            "par_cible": par_cible,
            "events_endturn": (act.get("events") or act.get("actions") or None),
            "trace_brute": {k: trace.get(k) for k in ("fires", "layout", "installed", "on")},
        }
    finally:
        if arme:
            try:
                _rpc(sid, "hitTraceDisarm", {"runnerId": rid}, 30)
            except Exception as e:                       # pragma: no cover
                print("[warn] hitTraceDisarm a echoue : %s" % e)
        try:
            _rpc(sid, "disposeRunner", {"runnerId": rid}, 20)   # MES runners, jamais les autres
        except Exception as e:                           # pragma: no cover
            print("[warn] disposeRunner a echoue : %s" % e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=None,
                    help="chemin ABSOLU du state-file (defaut : logs/<nom du probe>.json)")
    a = ap.parse_args()
    sid = P._session()
    nom = Path(a.state_file).stem if a.state_file else "probe_503r4_ventilation_par_coup"
    m = mesurer(sid, nom)
    print("[503-r4] cardinal par cible (NATIF) : %s" % json.dumps(m["cardinal_par_cible"]))
    print("[503-r4] ordre des cibles           : %s" % json.dumps(m["ordre_des_cibles"]))
    print("[503-r4] delta PV                   : %s" % json.dumps(m["delta_hp"]))
    print("[503-r4] fires du capteur           : %s" % json.dumps(m["trace_brute"]))
    if not m["coups_natifs"]:
        print("[503-r4] AUCUN coup capte -- soit le tir n'est pas parti, soit le capteur n'a pas "
              "vu ce vecteur. Ne RIEN conclure de ce zero sans regarder `delta PV`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
