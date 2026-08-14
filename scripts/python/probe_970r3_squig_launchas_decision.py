"""#970-r3 -- MESURE de la face DECISION `1200 SquigLaunchas` : le gate SEPARE-t-il vraiment ?

CE QUE CE PROBE ETABLIT, ET POURQUOI IL EXISTE
================================================================================================
Le port de la face DECISION de 1200 (`engine/playbook/noncomparable/squig_launchas.py`) ne peut
PAS etre juge sur l'utilite : elle est un TIRAGE (`IPseudoRNG` slot 2 `Next(1, 10)`, refait A
CHAQUE CIBLE), donc la cible retenue par le natif est indeterminable dans un moteur deterministe
(residu `#970-r6`). Ce qui EST determinable, et ce que ce probe mesure :

  1. **LE GATE SEPARE.** `...SquigLaunchasAbility$$FulfillsSummonCriteria` (seuils `nrOfUnits_3`
     0x81 / `nrOfUnits_4` 0x82) est PLUS STRICT que le gate de CIBLAGE
     (`...SquigLaunchasAbility$$GetDynamicInvalidTargetReason`, seuils `nrOfUnits` 0x78 /
     `nrOfUnits_2` 0x79), qui est celui qui filtre deja `abilityTargets`. Il existe donc des
     cibles LEGALES sur lesquelles le natif ne propose PAS 1200. C'est le TEMOIN NON NUL : sans la
     face DECISION, le port les proposait.
  2. **LE SEUIL NE FILTRE RIEN.** `Next(min, max)` exclut la borne HAUTE
     (`IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal` : `min + (g % (max - min))`),
     donc le tirage est dans `[1, 9]` ; le gate du bucket est un `>=`
     (`...Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction` -> `Fix64.op_GreaterThanOrEqual`)
     et `MIN_UTILITY = 1`. Toute cible qui passe le gate produit donc une action.
  3. **L'ARGMAX EST KEEP-FIRST.** `AddAction` ne remplace que sur `>` STRICT et l'utilite portee
     est CONSTANTE, donc la PREMIERE cible de l'ordre natif (`fromHere`) gagne. Une permutation de
     `fromHere` doit changer la cible emise.

Tout est OFFLINE : `NCContext` est bati a la main, aucun runner, aucun RPC. ASCII only (cp1252).

    python probe_970r3_squig_launchas_decision.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                      # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402
from engine.playbook import noncomparable as NC                    # noqa: E402

SQUIG = int(ActiveAbilityType.SquigLaunchas)      # 0x4b0 = 1200

#: `visualId` REELS du gameconfig -- la faction est LUE (`FactionId`), jamais ecrite en dur.
#: ⚠ ILS SONT VERIFIES RESOLUS (`_visuals_resolus`) : un `visualId` inexistant rend un `_unit_cfg`
#: VIDE, donc `FactionId is None`, donc le regime << N Orks >> devient silencieusement un regime
#: << N non-Orks >> -- une mesure CREUSE qui accuserait le port a la place du montage. C'est
#: exactement la faute commise a la premiere passe de ce probe (`orksBoy` n'existe pas).
ORK = "orksNob"           # FactionId = "Orks", kind = lineup, sans Steppable/Object
NON_ORK = "adeptCanoness"  # FactionId = "Sisterhood"
#: Porteur du trait que `NonSteppableOrObjectUnits` RETIRE -- la contre-epreuve du filtre.
OBJET = "LootObj_AmmoBox"  # traits = ["Object"]


def _neigh(cols: int = 10, rows: int = 10) -> dict:
    """Voisinage NATIF d'un plateau plat, derive de `hexgeo` (celui que `battle_query` consomme)."""
    out = {}
    for c in range(cols):
        for r in range(rows):
            out[(c, r)] = [(x, y) for (x, y) in hexgeo.disk(c, r, 1)
                           if (x, y) != (c, r) and 0 <= x < cols and 0 <= y < rows]
    return out


def _targets_rpc(entries: list):
    """Callable `ctx.ability_targets` : rend `entries` (format `fromHere`) pour le couple (uid, 1200)."""
    def _f(uid, aid):
        if aid != SQUIG:
            return {}
        return {"units": [{"unitId": uid,
                           "abilities": [{"abilityId": aid, "fromHere": list(entries)}]}]}
    return _f


def ctx_pour(cibles: list, allies: list) -> "NC.NCContext":
    """Un `NCContext` de MoW (caster hors plateau : `origin=None`, `reach_nc=[]`).

    `cibles` = `[(targetId, (col, row)), ...]` dans l'ORDRE du selecteur natif.
    `allies` = `[(unitId, (col, row), visualId), ...]` -- ils peuplent `fpos` ET `units`.
    """
    neigh = _neigh()
    fpos = [p for _i, p, _v in allies]
    units = [{"id": i, "pos": {"col": p[0], "row": p[1]}, "alive": True, "visualId": v}
             for i, p, v in allies]
    units += [{"id": t, "pos": {"col": p[0], "row": p[1]}, "alive": True, "visualId": NON_ORK}
              for t, p in cibles]
    entries = [{"kind": "unit", "targetId": t, "pos": {"col": p[0], "row": p[1]}}
               for t, p in cibles]
    return NC.NCContext(
        uid=1, origin=None, reach_nc=[], epos=[p for _t, p in cibles], fpos=fpos,
        plan={}, hp_cur_by_id={}, ability_targets=_targets_rpc(entries),
        units=units, neigh_by_pos=neigh, walkable_by_pos={p: True for p in neigh},
        elev_by_pos={p: 0 for p in neigh})


def candidats(ctx) -> list:
    return NC.PLAYBOOKS[SQUIG].generate_candidates(ctx)


# ================================================================================================
#  REGIMES -- la cible est en (5,5) ; on fait varier les ALLIES adjacents a ELLE
# ================================================================================================
T = (5, 5)
CIBLE_ID = 900


def _anneau(n: int, visual: str) -> list:
    """`n` allies sur le ring-1 de la cible, dans l'ordre de `hexgeo.disk`."""
    ring = [p for p in hexgeo.disk(T[0], T[1], 1) if p != T]
    return [(10 + i, ring[i], visual) for i in range(n)]


def _anneau_mixte(visuals: list) -> list:
    """Un allie par element de `visuals`, sur le ring-1 de la cible, dans l'ordre de `hexgeo.disk`."""
    ring = [p for p in hexgeo.disk(T[0], T[1], 1) if p != T]
    return [(10 + i, ring[i], v) for i, v in enumerate(visuals)]


def _loin(n: int, visual: str) -> list:
    """`n` allies a distance >= 2 de la cible -- HORS du ring-1.

    Sans ce regime, le montage ne contient QUE des voisins immediats : neutraliser le test
    `AdjacentUnits` ne changerait alors AUCUN verdict, et la garde serait MUETTE dessus. Trou
    trouve par mutation, pas suppose."""
    ring1 = set(hexgeo.disk(T[0], T[1], 1))
    hors = [p for p in hexgeo.disk(T[0], T[1], 3) if p not in ring1]
    return [(30 + i, hors[i], visual) for i in range(n)]


#: (libelle, allies, passe le CIBLAGE natif (>=1 Ork ou >=2 allies), passe le SUMMON (>=2 Ork ou >=4))
REGIMES = [
    ("0 allie adjacent",              _anneau(0, ORK),      False, False),
    ("1 Ork adjacent",                _anneau(1, ORK),      True,  False),   # <-- SEPARANT
    ("2 Orks adjacents",              _anneau(2, ORK),      True,  True),
    ("2 allies NON-Orks",             _anneau(2, NON_ORK),  True,  False),   # <-- SEPARANT
    ("3 allies NON-Orks",             _anneau(3, NON_ORK),  True,  False),   # <-- SEPARANT
    ("4 allies NON-Orks",             _anneau(4, NON_ORK),  True,  True),
    # `NonSteppableOrObjectUnits` : l'`Object` est RETIRE avant le comptage -> 3 effectifs sur 4.
    ("3 non-Orks + 1 Object",         _anneau_mixte([NON_ORK] * 3 + [OBJET]), True, False),
    # ... et le remplacer par une unite ORDINAIRE fait basculer : le filtre de trait est bien
    # ce qui decide, pas le nombre brut de voisins.
    ("4 non-Orks (temoin du filtre)", _anneau_mixte([NON_ORK] * 4), True, True),
    # Meme contre-epreuve cote ORKS : 2 voisins dont un `Object` -> 1 Ork effectif.
    ("1 Ork + 1 Object",              _anneau_mixte([ORK, OBJET]), True, False),
    # `AdjacentUnits(<tuile de la CIBLE>)` : ces allies sont HORS du ring-1, ils ne comptent pas.
    # Couple de contre-epreuve avec << 4 non-Orks >> ci-dessus (memes unites, autre distance).
    ("4 non-Orks a distance >= 2",    _loin(4, NON_ORK),    False, False),
    ("4 Orks a distance >= 2",        _loin(4, ORK),        False, False),
]


def _visuals_resolus() -> dict:
    """Les trois `visualId` du montage RESOLVENT-ils au gameconfig, et portent-ils ce qu'on croit ?

    Sans ce cran la mesure serait CREUSE : un `visualId` inexistant rend un `_unit_cfg` VIDE, donc
    `FactionId is None` et `traits == []`, donc TOUS les regimes << N Orks >> deviennent des
    regimes << N non-Orks >> et le probe accuse le port a la place du montage."""
    from engine.playbook.noncomparable._base import _unit_cfg
    o, n, obj = _unit_cfg(ORK), _unit_cfg(NON_ORK), _unit_cfg(OBJET)
    return {
        "ork_faction": o.get("FactionId"),
        "non_ork_faction": n.get("FactionId"),
        "objet_traits": [t for t in (obj.get("traits") or []) if t in ("Steppable", "Object")],
        "ork_traits_propres": not [t for t in (o.get("traits") or [])
                                   if t in ("Steppable", "Object")],
    }


def mesurer() -> dict:
    pb = NC.PLAYBOOKS[SQUIG]
    out = {
        "visuals": _visuals_resolus(),
        "seuils": {"orks_min": pb._threshold(pb.VAR_ORKS_MIN),
                   "friends_min": pb._threshold(pb.VAR_FRIENDS_MIN)},
        "min_utility": pb.MIN_UTILITY, "priority": pb.PRIORITY, "rng_term": pb.RNG_TERM,
        "regimes": [], "separants": [], "keep_first": None,
    }
    for libelle, allies, ciblable, attendu in REGIMES:
        ctx = ctx_pour([(CIBLE_ID, T)], allies)
        c = candidats(ctx)
        emis = bool(c)
        out["regimes"].append({"libelle": libelle, "ciblable": ciblable,
                               "attendu": attendu, "emis": emis,
                               "pred": (c[0]["pred"] if c else None)})
        if ciblable and not attendu:
            out["separants"].append({"libelle": libelle, "emis": emis})

    # ORDRE : deux cibles qui passent TOUTES DEUX le gate -> keep-first sur `fromHere`.
    T2 = (2, 2)
    allies = _anneau(2, ORK) + [(20 + i, p, ORK) for i, p in
                                enumerate([q for q in hexgeo.disk(T2[0], T2[1], 1) if q != T2][:2])]
    a = candidats(ctx_pour([(CIBLE_ID, T), (901, T2)], allies))
    b = candidats(ctx_pour([(901, T2), (CIBLE_ID, T)], allies))
    out["keep_first"] = {"ordre_A": (a[0]["target"] if a else None),
                         "ordre_B": (b[0]["target"] if b else None)}
    return out


def main() -> int:
    m = mesurer()
    faute_montage = 0
    v = m["visuals"]
    print("[970-r3] MONTAGE -- les `visualId` resolvent-ils ? %s=%s ; %s=%s ; %s traits=%s"
          % (ORK, v["ork_faction"], NON_ORK, v["non_ork_faction"], OBJET, v["objet_traits"]))
    if v["ork_faction"] != "Orks":
        faute_montage += 1
        print("   *** `%s` n'est pas de faction Orks : la mesure serait CREUSE ***" % ORK)
    if not v["non_ork_faction"] or v["non_ork_faction"] == "Orks":
        faute_montage += 1
        print("   *** `%s` n'est pas un non-Ork resolu : la mesure serait CREUSE ***" % NON_ORK)
    if not v["objet_traits"]:
        faute_montage += 1
        print("   *** `%s` ne porte ni Object ni Steppable : le filtre n'est pas exerce ***" % OBJET)
    if not v["ork_traits_propres"]:
        faute_montage += 1
        print("   *** `%s` porte Object/Steppable : il serait filtre, regimes fausses ***" % ORK)
    print()
    print("[970-r3] SEUILS LUS au gameconfig : orks_min=%s (nrOfUnits_3 0x81), friends_min=%s "
          "(nrOfUnits_4 0x82)" % (m["seuils"]["orks_min"], m["seuils"]["friends_min"]))
    print("[970-r3] MIN_UTILITY=%s (cctor Fix64(1)) ; PRIORITY=%s (First) ; RNG_TERM=%s "
          "(borne BASSE LUE de Next(1,10) = [1,9])"
          % (m["min_utility"], m["priority"], m["rng_term"]))
    print()
    print("%-30s %-10s %-10s %-8s %s" % ("regime", "ciblable", "attendu", "emis", "pred"))
    faute = faute_montage
    for r in m["regimes"]:
        ok = (r["emis"] == r["attendu"])
        faute += 0 if ok else 1
        print("%-30s %-10s %-10s %-8s %-6s %s"
              % (r["libelle"], r["ciblable"], r["attendu"], r["emis"], r["pred"],
                 "OK" if ok else "*** DIVERGE ***"))
    print()
    print("[970-r3] REGIMES SEPARANTS (cible LEGALE, gate de summon REFUSE) : %d"
          % len(m["separants"]))
    for s in m["separants"]:
        print("   %-24s emis=%s   (le natif ne propose PAS 1200 ici)" % (s["libelle"], s["emis"]))
    if not m["separants"]:
        faute += 1
        print("   *** AUCUN regime separant : la mesure ne prouve RIEN ***")
    if any(s["emis"] for s in m["separants"]):
        faute += 1
        print("   *** un regime separant EMET : le gate ne mord pas ***")
    print()
    kf = m["keep_first"]
    print("[970-r3] KEEP-FIRST (deux cibles eligibles) : ordre A -> %s ; ordre B -> %s"
          % (kf["ordre_A"], kf["ordre_B"]))
    if kf["ordre_A"] is None or kf["ordre_B"] is None or kf["ordre_A"] == kf["ordre_B"]:
        faute += 1
        print("   *** l'ordre de `fromHere` ne decide PAS la cible : argmax non keep-first ***")
    print()
    print("[970-r3] VERDICT : %s" % ("OK" if faute == 0 else "FAUTES (%d)" % faute))
    return 0 if faute == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
