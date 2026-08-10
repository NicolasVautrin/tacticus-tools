"""#503-r4 -- LA VENTILATION PAR COUP NATIVE DU TIR DIFFERE `1237`, prise par `hit-trace`.

CE QUE CE PROBE A REFUTE (2026-08-10, premier passage). La fiche `#503-r4` declarait
`BLOCAGE: capteur` et nommait
`IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget` comme « point d'ancrage a
hooker ». **C'etait faux** : le capteur EXISTE et repond. C'est
`frida/hooks/features/hit-trace.ts`, qui hooke
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` -- l'etage EN DESSOUS de celui qu'on
croyait devoir poser -- et son en-tete nommait litteralement le blocage de #503-r4. Il s'arme par
RPC (`hitTraceArm`), donc **sans reinject**. `BLOCAGE: capteur` -> `BLOCAGE: aucun`.

CE QUE LE CAPTEUR REND MAINTENANT, ET QU'IL NE RENDAIT PAS AU PREMIER PASSAGE
=============================================================================
`ExecuteHit(hitIndex, attacker, defender, damageProfileType, abilityOrEffect, attackDamageOptions,
initialHealth, deniedDamage)` porte les PV de la cible **AVANT** chaque coup en 7e argument. Le
hook ne calibrait que trois slots ; il publie desormais `initialHealth` et `deniedDamage`
(`initialHealthSlot = attackerSlot + 5`, DERIVE de la calibration -- hors plage -> `null`, jamais
un entier non valide). Le MONTANT PAR COUP natif se lit donc par DIFFERENCE :

    coup i sur une cible :  montant = initialHealth[i] - initialHealth[i+1]
    dernier coup          :  montant = initialHealth[dernier] - PV finaux (observeBattle)

C'est la ventilation que la fiche declarait inaccessible, et c'est l'etage qui manquait : le
cardinal et l'ordre etaient DEJA identiques (natif `{81: 2, 83: 2}`, ordre `[81,81,83,83]`), donc
« pas le meme nombre de coups » et « pas le meme ordre » sont ELIMINES. Reste l'etage
d'APPLICATION du montant, que seul `initialHealth` decompose.

CE PROBE MESURE LES DEUX COTES SUR LE MEME RUNNER
==================================================
Le montage (board, seed, placements, unites) est celui de
`probe_503r1_overwhelming_wrath_phase2.measure` -- on ne le re-invente pas, on l'INSTRUMENTE par
son point d'extension `hooks` : une divergence de montage rendrait les deux mesures
incomparables, et c'est la comparaison qui est tout l'objet. Le port publie deja sa propre
ventilation (`rolls`, `crits`, `per_hit`, `per_hit_health`, `hp_before`, `hp_after` --
`engine/runner/operations/triggers/loki/overwhelming_wrath_attack.py`), donc les deux colonnes se
confrontent COUP A COUP.

DISCIPLINE
==========
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


def _rpc(sid: int, method: str, body: dict, timeout: int = 90):
    return P.rpc(sid, method, body, timeout)


def _hooks(etat: dict) -> dict:
    """Arme `hit-trace` sur le SEUL pas qui declenche le tir, et le desarme juste apres.

    `etat` porte l'armement pour que l'appelant puisse desarmer dans son `finally` meme si le pas
    natif leve : un hook laisse arme couterait a tous les autres agents."""
    def avant(sid, rid):
        # Les effets BRUTS des cibles, AU MOMENT DU TIR -- `footprint_live` ne garde que `remaining`,
        # or c'est le `level` qui porte la magnitude d'un `EffectLevel` (#503-r4).
        dec = P.decision(sid, rid)
        etat["effets_bruts"] = {int(u["id"]): {"visualId": u.get("visualId"),
                                               "effets": u.get("effects")}
                                for u in (dec.get("units") or []) if u.get("id") is not None}
        _rpc(sid, "hitTraceReset", {"runnerId": rid}, 30)
        r = _rpc(sid, "hitTraceArm", {"runnerId": rid}, 30) or {}
        etat["rid"] = rid
        etat["arme"] = bool(r.get("installed"))
        etat["arm_report"] = r

    def apres(sid, rid):
        trace = _rpc(sid, "hitTrace", {"runnerId": rid, "limit": 200}, 30) or {}
        try:
            _rpc(sid, "hitTraceDisarm", {"runnerId": rid}, 30)
            etat["arme"] = False
        except Exception as e:                              # pragma: no cover
            print("[warn] hitTraceDisarm a echoue : %s" % e)
        return trace

    return {"avant_tir": avant, "apres_tir": apres}


def ventiler_natif(coups: list, hp_final: dict) -> dict:
    """`{defenderId: [montant, ...]}` -- le montant NATIF par coup, par DIFFERENCE d'`initialHealth`.

    ⚠ Un `initialHealth` a `null` (slot hors plage de plausibilite, cf. `readHealthSlot`) rend
    `None` pour le coup concerne : on ne fabrique JAMAIS un montant a partir d'une lecture qui a
    echoue. Un `None` DIT que la lecture a echoue ; un `0` mentirait."""
    par_cible: dict = {}
    for h in coups:
        d = h.get("defenderId")
        if d is None:
            continue
        par_cible.setdefault(int(d), []).append(h)
    out: dict = {}
    for d, hs in par_cible.items():
        montants = []
        for i, h in enumerate(hs):
            ih = h.get("initialHealth")
            suivant = (hs[i + 1].get("initialHealth") if i + 1 < len(hs)
                       else hp_final.get(int(d)))
            montants.append(None if (ih is None or suivant is None)
                            else int(ih) - int(suivant))
        out[int(d)] = montants
    return out


def ventiler_port(m: dict) -> dict:
    """`{targetId: {...etages...}}` -- ce que le PORT a produit pour le meme tir."""
    out: dict = {}
    for t in (m.get("off_tir") or []):
        for f in ((t or {}).get("fired") or []):
            for r in (f.get("results") or []):
                for d in ((r or {}).get("damage") or []):
                    out[int(d.get("target"))] = d
    return out


def mesurer(sid: int, state_name: str = "probe_503r4_ventilation_par_coup") -> dict:
    etat: dict = {"arme": False, "rid": None}
    try:
        m, dispose = P.measure(sid, state_name=state_name, hooks=_hooks(etat))
    except Exception:
        if etat.get("arme") and etat.get("rid") is not None:
            try:
                _rpc(sid, "hitTraceDisarm", {"runnerId": etat["rid"]}, 30)
            except Exception:                               # pragma: no cover
                pass
        raise
    try:
        m["effets_bruts"] = etat.get("effets_bruts") or {}
        trace = m.get("extra") or {}
        coups = trace.get("hits") or []
        hp_avant, hp_apres = m["live_hp"]
        m["coups_natifs"] = coups
        m["cardinal_par_cible"] = {}
        for h in coups:
            d = h.get("defenderId")
            if d is not None:
                m["cardinal_par_cible"][int(d)] = m["cardinal_par_cible"].get(int(d), 0) + 1
        m["ordre_des_cibles"] = [h.get("defenderId") for h in coups]
        m["montants_natifs"] = ventiler_natif(coups, hp_apres)
        m["ventilation_port"] = ventiler_port(m)
        m["trace_brute"] = {k: trace.get(k) for k in
                            ("fires", "captured", "layout", "installed", "on",
                             "calibrationFailures")}
        m["hp_tir"] = (hp_avant, hp_apres)
        return m
    finally:
        dispose()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=None,
                    help="chemin ABSOLU du state-file (defaut : logs/runners/<nom du probe>.json)")
    a = ap.parse_args()
    sid = P._session()
    nom = Path(a.state_file).stem if a.state_file else "probe_503r4_ventilation_par_coup"
    m = mesurer(sid, nom)

    print("[503-r4] capteur                    : %s" % json.dumps(m["trace_brute"]))
    print("[503-r4] cardinal par cible (NATIF) : %s" % json.dumps(m["cardinal_par_cible"]))
    print("[503-r4] ordre des cibles           : %s" % json.dumps(m["ordre_des_cibles"]))
    hp_avant, hp_apres = m["hp_tir"]
    delta = {k: int(hp_avant[k]) - int(hp_apres.get(k, hp_avant[k]))
             for k in hp_avant if int(hp_apres.get(k, hp_avant[k])) != int(hp_avant[k])}
    print("[503-r4] delta PV (NATIF)           : %s" % json.dumps(delta))
    if not m["coups_natifs"]:
        print("[503-r4] AUCUN coup capte -- soit le tir n'est pas parti, soit le capteur n'a pas "
              "vu ce vecteur. Ne RIEN conclure de ce zero sans regarder `delta PV`.")
        return 1

    print("\n[503-r4] COUPS NATIFS BRUTS (hitIndex, attaquant, cible, profil, PV avant, refuse)")
    for h in m["coups_natifs"]:
        print("    seq=%-3s hitIndex=%-3s att=%-5s def=%-5s profil=%-4s initialHealth=%-8s "
              "deniedDamage=%s"
              % (h.get("seq"), h.get("hitIndex"), h.get("attackerId"), h.get("defenderId"),
                 h.get("profile"), h.get("initialHealth"), h.get("deniedDamage")))

    print("\n[503-r4] `initialHealth` EST CONSTANT SUR LES COUPS D'UNE MEME CIBLE, ET C'EST LU.")
    print("    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` passe "
          "`*(int*)(hitGroup + 0x50)`")
    print("    a CHAQUE `ExecuteHit` et ne le REECRIT JAMAIS dans la boucle -> ce sont les PV avant")
    print("    le GROUPE de coups, pas avant chaque coup. La ventilation par MONTANT ne s'en deduit")
    print("    donc PAS ; ce que le capteur tranche reste le CARDINAL et l'ORDRE.")

    print("\n[503-r4] TOTAL PAR CIBLE -- natif (delta PV) vs port (etages COMPLETS)")
    vp = m["ventilation_port"]
    rc = 0
    for cible in sorted(delta):
        d = vp.get(cible) or {}
        et = d.get("etages") or {}
        nat = int(delta[cible])
        port = d.get("total")
        verdict = "OK" if port == nat else ("ECART %s" % (None if port is None else port - nat))
        print("    u%-4d natif %-8d port %-8s  %s" % (cible, nat, port, verdict))
        print("         etages port : %s" % json.dumps(et, ensure_ascii=True, sort_keys=True))
        print("         stats def.  : %s"
              % json.dumps((m.get("stats_cibles") or {}).get(cible), ensure_ascii=True,
                           sort_keys=True))
        if port != nat:
            rc = 1
    print("\n[503-r4] EFFETS poses par le CAST (port | natif) : %s | %s"
          % (json.dumps(m["off_cast"]), json.dumps(m["live_cast"])))
    print("[503-r4] EFFETS portes AVANT le tir (natif) : %s"
          % json.dumps(m["live_foot"][0], sort_keys=True))
    print("[503-r4] cible du CAST = u%s ; caster = u%s" % (m["target"], m["caster"]))
    print("\n[503-r4] EFFETS BRUTS AU MOMENT DU TIR (le `level` porte la magnitude d'un EffectLevel)")
    for uid in sorted(m.get("effets_bruts") or {}):
        row = m["effets_bruts"][uid]
        print("    u%-4d %-22s %s" % (uid, row.get("visualId"),
                                      json.dumps(row.get("effets"), ensure_ascii=True)))
    print("\nVERDICT : %s" % ("port == natif" if rc == 0 else
                              "ECART -- voir la ventilation ci-dessus"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
