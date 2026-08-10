"""`#419-r6-r1-r1` -- CONFRONTATION du capteur `sortUtilityTrace` : l'utilite PAR CIBLE.

## Le critere binaire, enonce AVANT la mesure

`#419-r6-r1` a MESURE que `IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$Select`
ne fait PAS entrer `MightCrit` dans son classement. Ce qui n'etait pas isole, c'est l'ETAGE qui le
neutralise. Le capteur ancre la LAMBDA de tri
(`SortUnitsByDamageUtilitySelector.u003Cu003Ec__DisplayClass9_0$$u003CSelectu003Eb__0`, dont le
corps EST `return -this.<+0x28 = Dictionary<IEntity, Fix64>>[unit]`) et `$$Select` (pour delimiter
les sessions et publier l'ORDRE natif rendu).

Le montage est joue DEUX FOIS, avec le meme regime de PV :

  * `--crit 100,700`  -> `MightCrit` est pose de facon INCONTESTABLE ;
  * `--no-bis-items`  -> le TEMOIN, ou `CouldCrit` est faux.

et la question est :

  * `pairs[].utility` IDENTIQUES entre les deux regimes ⇒ l'etage neutralisant est EN AVAL de la
    prediction (le decideur, ou l'utilite elle-meme) ;
  * `pairs[].utility` DIFFERENTES alors que `sessions[].ordered` ne bouge pas ⇒ la neutralisation
    est dans le TRI (egalites, arrondi de la cle).

⚠ **`diag.lambdaFires == 0` avec `resolution.lambda == true` n'est PAS un verdict** : c'est un
montage qui n'a pas traverse ce chemin. Le probe le DIT et sort en rc 2, jamais en rc 0/1.

## Discipline

Le capteur est un `Interceptor` GLOBAL a la session (pas par runner) : il est arme juste avant le
montage, lu juste apres, et **DESARME dans un `finally`** -- deux autres agents partagent cette
session. Le montage lui-meme n'est pas retranscrit : il est IMPORTE de
`probe_419r6r1_face_decision.py` (`etage_regime` + `etage_live`), donc les deux probes ne peuvent
pas diverger.

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


class MontageError(RuntimeError):
    """Un capteur qui n'a pas fire n'est pas un verdict -- on REFUSE de conclure."""


def _resume(lu: dict) -> dict:
    """Les paires, groupees par session `$$Select`. La cle de tri est `-utilite` : on republie
    l'utilite telle que `UtilityDecider$$CalculateUtility` l'a rendue, ET le brut Fix64 (base 10),
    parce qu'une comparaison << identique / different >> doit pouvoir se faire sur l'entier exact
    (la conversion Q32.32 perd des bits de poids faible sur un `double`)."""
    par_seq: dict = {}
    for p in (lu.get("pairs") or []):
        par_seq.setdefault(p.get("seq"), []).append(p)
    out = {}
    for s in (lu.get("sessions") or []):
        seq = s.get("seq")
        out[seq] = {
            "ordered": s.get("ordered"),
            "pairs": [{"unitId": p.get("unitId"), "entityType": p.get("entityType"),
                       "utility": p.get("utility"), "keyRaw": p.get("keyRaw")}
                      for p in sorted(par_seq.get(seq, []), key=lambda x: (x.get("unitId") or -1))],
        }
    return out


def _cle_comparable(res: dict) -> dict:
    """`{unitId: keyRaw}` de la DERNIERE session -- la seule directement comparable entre deux
    montages (les sessions anterieures peuvent venir d'un autre runner de la meme session Frida)."""
    if not res:
        return {}
    seq = max(res.keys())
    return {p["unitId"]: p["keyRaw"] for p in res[seq]["pairs"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="31337")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--a-units", default="necroOverlord,necroWarden,eldarRanger,orksNob")
    ap.add_argument("--crit", default="100,700")
    ap.add_argument("--level", type=int, default=50)
    ap.add_argument("--mult", type=int, default=100)
    a = ap.parse_args()

    import rl_collect_batch as R
    import probe_419r6r1_face_decision as FD

    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        r = R._rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    print("== #419-r6-r1-r1 -- l'utilite PAR CIBLE du selecteur de tri par degat")

    print("")
    print("=== etape 0 -- ARMEMENT (la resolution AVANT tout montage) ===")
    st = rpc("sortUtilityTrace", {"action": "status"}, 30)
    print("  status initial : armed=%s diag=%s" % (st.get("armed"), st.get("diag")))
    if st.get("armed"):
        # Un capteur DEJA arme n'est pas le notre : on ne le desarme pas sous les pieds d'un autre
        # agent, mais on ne peut pas non plus lui attribuer nos fires -> on VIDE l'anneau et on
        # continue, en le disant.
        print("  ATTENTION : capteur DEJA arme (un autre agent ?) -- l'anneau est vide avant"
              " mesure, le capteur n'est PAS re-arme et ne sera PAS desarme par nous.")
        rpc("sortUtilityTrace", {"action": "read", "clear": True}, 30)
        armed_by_us = False
    else:
        arm = rpc("sortUtilityTrace", {"action": "arm"}, 60)
        print("  arm -> %s" % json.dumps(arm, sort_keys=True))
        reso = arm.get("resolution") or {}
        if not (arm.get("ok") and reso.get("select") and reso.get("lambda")):
            raise MontageError("resolution INCOMPLETE (%s) -- aucun hook pose, rien ne peut firer"
                               % json.dumps(reso, sort_keys=True))
        armed_by_us = True

    try:
        print("")
        print("=== etape 1 -- le REGIME de PV (offline, partage par les deux bras) ===")
        reco = FD._reco_du_runner(a.a_units, "defaut", a.seed, a.board)
        d = None if reco is None else reco["d"]
        if d is None:
            d = FD._dmg_min(a.level, a.mult)
            print("  degat du noeud de tri SUPPOSE : %d (la reconnaissance a echoue)" % d)
        else:
            print("  degat du noeud de tri LU sur un runner : %d" % d)
        reg = FD.etage_regime(d, verbose=False, reco=reco)
        if not reg.get("ok"):
            raise MontageError("aucun regime de PV discriminant -- le montage ne separerait rien")
        print("  regime : %s" % {k: v for k, v in reg.items() if k != "ok"})

        bras = {}
        for tag, items in (("AVEC_CRIT", "defaut"), ("TEMOIN_no_bis_items", "0")):
            print("")
            print("=== etape 2 -- bras %s ===" % tag)
            rpc("sortUtilityTrace", {"action": "read", "clear": True}, 60)   # anneau propre
            crit = a.crit if items == "defaut" else None
            r = FD.etage_live(reg, a.a_units, items, a.seed, a.board, verbose=True, crit=crit)
            if r.get("error"):
                raise MontageError("bras %s : %s" % (tag, r["error"]))
            lu = rpc("sortUtilityTrace", {"action": "read", "clear": True}, 60)
            diag = lu.get("diag") or {}
            print("  capteur : diag=%s sessions=%s paires=%s"
                  % (json.dumps(diag, sort_keys=True), lu.get("sessionCount"), lu.get("pairCount")))
            if int(diag.get("lambdaFires") or 0) == 0:
                raise MontageError(
                    "bras %s : `lambdaFires == 0` alors que la resolution est complete -- le "
                    "montage n'a PAS traverse `SortUnitsByDamageUtilitySelector$$Select`. Ce "
                    "n'est PAS un verdict : c'est un montage a refaire." % tag)
            # ⚠ Le cliquet du hook (`#419-r7`). `keysAtInt64Max > 0` veut dire que la lecture de
            # RAX a SATURE : une cle de tri `-utilite` ne vaut pas 2^63-1. Comparer des cles
            # saturees rendrait << identiques >> deux regimes qui different -- le verdict
            # EXACTEMENT INVERSE. Sur un bundle anterieur au correctif, le champ est ABSENT : on
            # retombe alors sur la detection directe, qui ne depend d'aucun champ neuf.
            sat = diag.get("keysAtInt64Max")
            brutes = [p.get("keyRaw") for p in (lu.get("pairs") or [])]
            sat_vu = sum(1 for b in brutes if str(b) == "9223372036854775807")
            cles_valides = ((sat or 0) == 0 and sat_vu == 0)
            if not cles_valides:
                print("  ⚠ LECTURE SATUREE : %d cle(s) a Int64.MaxValue (diag=%r). Le bundle"
                      % (sat_vu, sat))
                print("    charge est anterieur au correctif `#419-r7` (`raxToInt64` dans")
                print("    `sort-utility-trace.ts`) : le volet CLE est NON MESURE. L'ORDRE natif")
                print("    (`sessions[].ordered`), lui, ne passe par aucune conversion -- il TIENT.")
            res = _resume(lu)
            for seq in sorted(res):
                print("  session %s : ordered=%s" % (seq, res[seq]["ordered"]))
                for p in res[seq]["pairs"]:
                    print("     u%-4s type=%s utility=%s keyRaw=%s"
                          % (p["unitId"], p["entityType"], p["utility"], p["keyRaw"]))
            bras[tag] = {"res": res, "might_crit": r.get("might_crit_owner"),
                         "oracle": r.get("oracle_natif"), "cles_valides": cles_valides,
                         "ordre_port": r.get("ordre_production"),
                         "exact_production": r.get("exact_production"),
                         "exact_contrefactuel": r.get("exact_contrefactuel"),
                         "discriminant": r.get("montage_discriminant")}

        print("")
        print("=== etape 3 -- VERDICT BINAIRE ===")
        a_cles = _cle_comparable(bras["AVEC_CRIT"]["res"])
        t_cles = _cle_comparable(bras["TEMOIN_no_bis_items"]["res"])
        print("  CouldCrit(owner) : AVEC=%s TEMOIN=%s"
              % (bras["AVEC_CRIT"]["might_crit"], bras["TEMOIN_no_bis_items"]["might_crit"]))
        print("  oracle natif AVEC   : %s" % bras["AVEC_CRIT"]["oracle"])
        print("  oracle natif TEMOIN : %s" % bras["TEMOIN_no_bis_items"]["oracle"])
        print("  cles AVEC   : %s" % a_cles)
        print("  cles TEMOIN : %s" % t_cles)
        communs = sorted(set(a_cles) & set(t_cles))
        ordre_a = bras["AVEC_CRIT"]["res"][max(bras["AVEC_CRIT"]["res"])]["ordered"]
        ordre_t = (bras["TEMOIN_no_bis_items"]["res"]
                   [max(bras["TEMOIN_no_bis_items"]["res"])]["ordered"])
        cles_lisibles = all(bras[t]["cles_valides"] for t in bras)
        print("  ordre natif AVEC=%s TEMOIN=%s" % (ordre_a, ordre_t))
        print("  bit-exact vs live -- AVEC : production=%s contrefactuel=%s (discriminant=%s)"
              % (bras["AVEC_CRIT"]["exact_production"],
                 bras["AVEC_CRIT"]["exact_contrefactuel"], bras["AVEC_CRIT"]["discriminant"]))

        # --- VOLET 1 : l'ORDRE natif. Il ne passe par AUCUNE conversion, donc il tient meme
        #     quand les cles saturent. C'est lui qui repond a la question du residu.
        if ordre_a != ordre_t:
            print("VOLET ORDRE : l'ordre natif CHANGE entre les deux regimes (%s -> %s) alors que"
                  % (ordre_a, ordre_t))
            print("  seul le canal crit du caster a bouge (CouldCrit %s -> %s)."
                  % (bras["AVEC_CRIT"]["might_crit"], bras["TEMOIN_no_bis_items"]["might_crit"]))
            print("  ⇒ il n'y a AUCUN etage neutralisant a trouver : le flag EST classant, et la")
            print("  premisse du residu (`MightCrit` n'entre pas dans ce classement) est REFUTEE.")
            rc = 1
        else:
            print("VOLET ORDRE : l'ordre natif ne bouge PAS entre les deux regimes.")
            rc = 0

        # --- VOLET 2 : les CLES. Il ne dit quelque chose que si la lecture n'a pas sature.
        if not cles_lisibles:
            print("VOLET CLE : NON MESURE (lecture saturee -- cf. l'avertissement ci-dessus).")
            print("  Ce n'est pas un resultat negatif : c'est l'absence de mesure. Il se rejoue")
            print("  tel quel une fois le bundle corrige recharge.")
            return rc
        if not communs:
            raise MontageError("les deux bras n'ont AUCUNE unite en commun dans leur derniere "
                               "session -- les cles ne sont pas comparables")
        identiques = all(a_cles[u] == t_cles[u] for u in communs)
        print("VOLET CLE : %d unite(s) comparable(s) ; cles IDENTIQUES : %s"
              % (len(communs), identiques))
        if identiques and ordre_a == ordre_t:
            print("  ⇒ utilites IDENTIQUES quand le flag change : l'etage neutralisant est EN AVAL")
            print("  de la prediction (le decideur, ou l'utilite elle-meme).")
        elif not identiques and ordre_a == ordre_t:
            print("  ⇒ utilites DIFFERENTES a ORDRE CONSTANT : la neutralisation est dans le TRI")
            print("  (egalites, arrondi de la cle).")
        else:
            print("  ⇒ utilites ET ordre bougent : cf. le VOLET ORDRE ci-dessus.")
        return rc
    finally:
        if armed_by_us:
            d = rpc("sortUtilityTrace", {"action": "disarm"}, 30)
            print("")
            print("[disarm] %s" % json.dumps(d, sort_keys=True))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MontageError as e:
        print("MONTAGE : %s" % e)
        # Le `finally` de `main` a deja desarme -- mais si l'exception est levee AVANT l'armement,
        # il n'y a rien a desarmer, et si elle l'est apres, le desarmement a eu lieu.
        sys.exit(2)
