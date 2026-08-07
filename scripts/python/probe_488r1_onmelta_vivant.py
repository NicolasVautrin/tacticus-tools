"""#488-r1 -- `1211 OnMeltaDamageAbility` est-elle VIVANTE, et si non par quel MECANISME ?

QUESTION BINAIRE, posee AVANT la methode. `case-72` l'a classee DEAD-CODE sur `gqfc5mff6c` avec
pour racine « elle n'override pas `CreateTrigger` ». #519 a FALSIFIE cette racine au decompile sur
`rnca9r7q6c`. Reste :

    VIVANTE     : le trigger est materialise ET l'effet 1297 `Melta_ExtraDmg` atteint le pipeline
                  de degat de l'ATTAQUANT -> le +50 % vs `Vehicle` de l'i2 existe.
    MORTE       : n'importe quel maillon rompu -- mais alors DIRE LEQUEL.

ETAGES MESURES (chacun a son oracle natif -- jamais un scalaire fitte) :

  [0] SLOT DE VTABLE (RPC `resolveMethodPtr`).  La table est indexee par ADRESSE et IL2CPP
      DEDUPLIQUE les corps triviaux : la presence du symbole ne prouve pas plus l'override que son
      absence ne prouve la non-surcharge. Le seul discriminant est la PROFONDEUR du premier corps
      dans la chaine de parents -- `0` = la classe DECLARE la methode. On interroge les TROIS
      membres de la famille (`OnFire`, `OnToxic`, `OnMelta`) : les deux premiers sont les TEMOINS
      DE MORSURE (ils overrident, c'est etabli), et on ajoute `GetTargetTiles` -- que seul `OnFire`
      declare -- pour montrer que l'etage sait aussi rendre « pas a la profondeur 0 ».

  [1] EFFET DE TUILE AU `MatchInit`.  `$$CreateBehaviour` pose `AddEffect(1297, targets =
      First(AllTiles(), 1))` : le support est une TUILE, pas une unite. `decisionView.effects` est
      une vue PAR UNITE -- son silence (la contre-observation de #519) ne prouve donc rien.
      L'oracle est la vue TUILE (`tileMeta` / effets de tuile du runner).

  [2] MORSURE SUR LE DEGAT.  Un attaquant a profil `Melta` frappe un `Vehicle` DEPUIS la tuile qui
      porte l'effet, puis depuis une AUTRE tuile. Si l'effet mord, les deux regimes different.
      C'est ce qui separe « pose mais inerte » de « pose et lu ».

Usage :
    python scripts/python/probe_488r1_onmelta_vivant.py --step vtable
    python scripts/python/probe_488r1_onmelta_vivant.py --step tuile
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import sys
import urllib.request

HOST = "http://127.0.0.1:8765"
RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NS_DMG = "IdunBattleLogic.Entities.Abilities.Damage.Loki"

# Les TROIS membres de la famille. `OnFire`/`OnToxic` sont les temoins de morsure de l'etage 0 :
# leur override de `CreateTrigger` est etabli (corps NOMMES et NON partages dans la table).
FAMILLE = ["OnFireDamageAbility", "OnToxicDamageAbility", "OnMeltaDamageAbility"]

# `GetTargetTiles` n'est declaree que par `OnFireDamageAbility` -> l'etage doit rendre une
# profondeur > 0 (ou rien) pour les deux autres. Sans ce contre-cas, un etage qui rendrait
# « profondeur 0 » pour tout passerait pour vert.
METHODES = ["CreateTrigger", "CreateBehaviour", "GetTargetTiles"]


def _http(chemin, methode="GET", corps=None, timeout=60):
    req = urllib.request.Request(
        HOST + chemin, method=methode,
        data=None if corps is None else json.dumps(corps).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def session_id():
    st = _http("/api/admin/status")
    sess = st.get("session") or {}
    return int(sess["id"]) if sess.get("id") is not None else None


def rpc(sid, methode, args, timeout=90.0):
    out = _http("/api/scripts/%d/rpc" % sid, "POST",
                {"method": methode, "args": args, "timeout": int(timeout * 1000)},
                timeout + 10)
    return out.get("result")


def build_courant():
    with open(os.path.join(RACINE, "data", "symbols", "CURRENT"), encoding="utf-8") as f:
        return f.read().strip()


def charge_table(build):
    chemin = os.path.join(RACINE, "data", "symbols", build, "ghidra", "functions.tsv")
    paires = []
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            if ligne.startswith("#"):
                continue
            m = ligne.rstrip("\n").split("\t")
            if len(m) < 2:
                continue
            try:
                paires.append((int(m[0], 16), m[1]))
            except ValueError:
                continue
    paires.sort()
    return [a for a, _ in paires], [s for _, s in paires]


def whereis(adresses, symboles, va):
    if va == 0:
        return None
    i = bisect.bisect_right(adresses, va) - 1
    if i < 0:
        return None
    delta = va - adresses[i]
    return symboles[i] if delta == 0 else "%s+0x%x" % (symboles[i], delta)


def etape_vtable():
    """[0] La classe DECLARE-t-elle `CreateTrigger` ? -> profondeur du 1er corps."""
    build = build_courant()
    adresses, symboles = charge_table(build)
    print("build=%s  table=%d fonctions" % (build, len(adresses)))

    sid = session_id()
    if sid is None:
        print("ECHEC: aucune session Frida vivante")
        return 2
    print("session=%d" % sid)

    cibles = [{"ns": NS_DMG, "cls": c, "method": m} for c in FAMILLE for m in METHODES]
    res = rpc(sid, "resolveMethodPtr", [{"targets": cibles, "maxDepth": 6}], 90)
    if not res or not res.get("ok"):
        print("ECHEC RPC: %r" % (res,))
        return 3

    # (classe, methode) -> (profondeur, classe porteuse, symbole du corps)
    trouve = {}
    for t in res["targets"]:
        cle = (t["cls"], t["method"])
        if not t.get("ok"):
            trouve[cle] = None
            continue
        premier = None
        for niveau in t["levels"]:
            if not niveau["methods"]:
                continue
            entree = niveau["methods"][0]
            va = int(entree["entry"]["ghidraVA"], 16)
            premier = (niveau["depth"], niveau["name"], whereis(adresses, symboles, va), va)
            break
        trouve[cle] = premier

    print("\n--- [0] PROFONDEUR DU PREMIER CORPS (0 = la classe DECLARE) ---")
    for cls in FAMILLE:
        print("\n%s" % cls)
        for m in METHODES:
            v = trouve.get((cls, m))
            if v is None:
                print("  %-18s : ABSENTE de toute la chaine" % m)
            else:
                prof, porteuse, sym, va = v
                print("  %-18s : profondeur %d  chez %s" % (m, prof, porteuse))
                print("  %-18s   corps -> %s" % ("", sym))

    # VERDICT de l'etage : la question binaire de la reserve (a).
    melta = trouve.get(("OnMeltaDamageAbility", "CreateTrigger"))
    print("\n--- VERDICT [0] ---")
    if melta is None:
        print("OnMeltaDamageAbility.CreateTrigger : ABSENTE -> `case-72` tiendrait")
        return 1
    prof, porteuse, sym, _ = melta
    if prof == 0:
        print("OnMeltaDamageAbility DECLARE CreateTrigger (profondeur 0, porteuse %s)" % porteuse)
        print("  -> la racine de `case-72` (« n'override pas CreateTrigger ») est FALSIFIEE")
    else:
        print("OnMeltaDamageAbility HERITE CreateTrigger (profondeur %d, chez %s)" % (prof, porteuse))
        print("  -> `case-72` tiendrait, mais pour une raison a re-enoncer")

    # CONTRE-CAS : l'etage sait-il rendre autre chose que « profondeur 0 » ?
    print("\n--- CONTRE-CAS (l'etage MORD-il ?) ---")
    non_zero = [(c, m, v) for (c, m), v in sorted(trouve.items())
                if v is None or v[0] != 0]
    if not non_zero:
        print("AUCUN : tous les couples rendent profondeur 0 -> l'etage NE DISCRIMINE PAS,")
        print("        son « profondeur 0 » ne vaut rien. Ajouter un couple non declare.")
        return 4
    for c, m, v in non_zero:
        print("  %s.%s : %s" % (c, m, "ABSENTE" if v is None else "profondeur %d chez %s" % (v[0], v[1])))

    # PARTAGE DU CORPS : quels couples rendent la MEME adresse d'entree ?
    print("\n--- PARTAGE DU CORPS (la deduplication, mesuree) ---")
    par_va = {}
    for (c, m), v in trouve.items():
        if v is not None:
            par_va.setdefault(v[3], []).append("%s.%s" % (c, m))
    for va, membres in sorted(par_va.items()):
        if len(membres) > 1:
            print("  %s partage par %d : %s"
                  % (whereis(adresses, symboles, va), len(membres), ", ".join(sorted(membres))))
    return 0


def etape_tuile(runner_id):
    """[1] L'effet 1297 est-il POSE au `MatchInit`, et sur QUEL support ?

    `decisionView.effects` est une vue PAR UNITE : son silence (la contre-observation de #519) ne
    peut pas distinguer « pas pose » de « pose sur une TUILE ». L'oracle est donc `tileMeta`, la
    MEME lecture native cote tuile (`readEffectsByTile`)."""
    sid = session_id()
    if sid is None:
        print("ECHEC: aucune session Frida vivante")
        return 2
    res = rpc(sid, "tileMeta", [{"runnerId": runner_id}], 60)
    if not res or not res.get("ok"):
        print("ECHEC RPC tileMeta: %r" % (res,))
        return 3
    tuiles = res.get("tiles") or []
    print("--- [1] EFFETS PORTES PAR LES TUILES (runner %d, %d tuiles) ---"
          % (runner_id, len(tuiles)))
    porteuses = []
    for t in tuiles:
        noms = [e.get("name") if isinstance(e, dict) else str(e) for e in (t.get("effects") or [])]
        if noms:
            print("  (%s,%s) : %s" % (t.get("col"), t.get("row"), ", ".join(noms)))
            if "Melta_ExtraDmg" in noms:
                porteuses.append((t.get("col"), t.get("row")))
    print("\n--- VERDICT [1] ---")
    if not porteuses:
        print("AUCUNE tuile ne porte Melta_ExtraDmg -> le behaviour n'a rien pose")
        return 1
    print("Melta_ExtraDmg pose sur %d tuile(s) : %s" % (len(porteuses), porteuses))
    print("  -> conforme a `AddEffect(1297, targets = First(AllTiles(), 1))` : UNE tuile,")
    print("     et le support est une TUILE, pas une unite. La contre-observation de #519")
    print("     (`decisionView.effects` muette) mesurait le MAUVAIS support.")
    return 0


def etape_morsure(runner_id, attaquant, cibles, tuiles):
    """[2] L'effet MORD-il ? Bande de prediction NATIVE depuis chaque tuile.

    `Melta_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` est un `ForPercentIncrease` : s'il
    entrait dans le pipeline, la bande predite contre un `Vehicle` serait 1,5x plus haute DEPUIS la
    tuile porteuse. On balaie donc les MEMES tuiles pour une cible `Vehicle` ET une cible
    non-`Vehicle` -- la seconde est le TEMOIN : elle ne doit varier avec AUCUNE tuile porteuse,
    parce que le gate `HasTrait(target, Vehicle)` l'exclut."""
    sid = session_id()
    if sid is None:
        print("ECHEC: aucune session Frida vivante")
        return 2
    print("--- [2] BANDE NATIVE (`aiPredict`) PAR TUILE DE TIR ---")
    print("attaquant u%d ; tuiles balayees : %s" % (attaquant, tuiles))
    table = {}
    for cible, etiquette in cibles:
        print("\n  vs u%d (%s)" % (cible, etiquette))
        for (c, r) in tuiles:
            res = rpc(sid, "aiPredict", [{"runnerId": runner_id, "unitId": attaquant,
                                          "targetId": cible, "col": c, "row": r,
                                          "fresh": True}], 60)
            if not res or not res.get("ok"):
                print("    (%d,%d) : RPC KO %r" % (c, r, res))
                continue
            p = res.get("pred") or {}
            bande = (p.get("healthDmgMin"), p.get("healthDmgMax"), p.get("appliedHits"))
            table[(etiquette, c, r)] = bande
            print("    (%d,%d) : min=%s max=%s hits=%s   [%s]"
                  % (c, r, bande[0], bande[1], bande[2], res.get("abilityName")))
    return table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="vtable", choices=["vtable", "tuile", "morsure"])
    ap.add_argument("--runner", type=int)
    ap.add_argument("--attaquant", type=int)
    ap.add_argument("--vehicle", type=int)
    ap.add_argument("--autre", type=int)
    ap.add_argument("--tuiles", default="0,0;1,0;2,0;0,1;0,2")
    a = ap.parse_args()
    if a.step == "vtable":
        return etape_vtable()
    if a.step == "tuile":
        return etape_tuile(a.runner)
    if a.step == "morsure":
        tuiles = [tuple(int(x) for x in t.split(",")) for t in a.tuiles.split(";")]
        cibles = [(a.vehicle, "Vehicle"), (a.autre, "non-Vehicle")]
        etape_morsure(a.runner, a.attaquant, cibles, tuiles)
        return 0
    return 9


if __name__ == "__main__":
    sys.exit(main())
