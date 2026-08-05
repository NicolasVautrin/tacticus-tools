"""#419-r1-tr14-r1-r1 -- MESURE du rayon de souffle de la porte de PORTEE d'arme.

Question mesuree : `IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack`
(surcharge `(attacker, attackerTiles, target)`, slot `0xaf` -- CELLE que
`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$FindAttackWeapon`
invoque depuis `PredictAttack` **et** `ExecuteBehaviour`) n'a AUCUN repli croise :

    adjacent -> FindMeleeWeapon(attacker, attackerTiles, target)      // ensemble MELEE, null si vide
    sinon    -> FindRangedWeapon(attacker, attackerTiles, target, d)  // ensemble RANGED filtre par
                                                                     // `d <= Range + rangeStatBonus`,
                                                                     // null si vide

Le port, lui, repliait sur l'autre type dans les deux sens. Ce probe VENTILE le catalogue et
compte, avant/apres, les verdicts qui changent -- par unite et par distance.

Il mesure AUSSI le second tri : le port separe melee/ranged par `bool(w["Range"])`, le natif par
`IdunShared.Battle.WeaponProfile$$get_IsMelee` (`Range is None || Range < 2`). Les deux divergent
sur les armes `Range == 1`, et cette divergence devient VISIBLE des que le repli disparait.

Usage :
    python probe_419r1tr14r1r1_weapon_range_gate.py [--max-dist 8]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gameconfig as GC                                            # noqa: E402
from engine.services.battle_query import weapon_is_melee           # noqa: E402


def _weapons(uid: str) -> list:
    return (GC.unit(uid) or {}).get("weapons") or []


def _split_port(weapons):
    """Le tri HISTORIQUE du port : `bool(w["Range"])`."""
    return ([w for w in weapons if not w.get("Range")],
            [w for w in weapons if w.get("Range")])


def _split_natif(weapons):
    """Le tri NATIF : `WeaponProfile$$get_IsMelee` (`Range is None || Range < 2`)."""
    return ([w for w in weapons if weapon_is_melee(w)],
            [w for w in weapons if not weapon_is_melee(w)])


def _select_avant(weapons, is_adjacent, dist):
    """`get_attack_weapon_for_default_normal_attack` AVANT le fix (repli croise)."""
    if not weapons:
        return None
    melee, ranged = _split_port(weapons)
    if is_adjacent and melee:
        cand = melee
    elif ranged:
        if dist is not None:
            in_range = [w for w in ranged if dist <= int(w.get("Range") or 0)]
            cand = in_range or melee or ranged
        else:
            cand = ranged
    else:
        cand = melee or weapons
    return cand[0] if cand else None


def _select_apres(weapons, is_adjacent, dist):
    """APRES le fix : mirror 1:1 du slot 0xaf, tri natif, aucun repli croise."""
    if not weapons:
        return None
    melee, ranged = _split_natif(weapons)
    if is_adjacent:
        cand = melee
    else:
        cand = ranged if dist is None else [
            w for w in ranged if dist <= int(w.get("Range") or 0)]
    return cand[0] if cand else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-dist", type=int, default=8)
    args = ap.parse_args(argv)

    ids = GC.all_unit_ids()
    all_ids = [(k, u) for k in ("lineup", "npc", "summons") for u in ids[k]]
    print("ETAPE 1 -- CATALOGUE")
    print("  unites : %d (lineup %d / npc %d / summons %d)"
          % (len(all_ids), len(ids["lineup"]), len(ids["npc"]), len(ids["summons"])))

    # --- etape 2 : divergence des DEUX tris (armes Range == 1) -----------------------------------
    r1_weapons, r1_units = 0, []
    for _k, uid in all_ids:
        ws = _weapons(uid)
        n = sum(1 for w in ws if w.get("Range") is not None and int(w["Range"]) == 1)
        if n:
            r1_weapons += n
            r1_units.append(uid)
    print("ETAPE 2 -- ARMES `Range == 1` (melee pour le natif, DISTANCE pour le tri historique)")
    print("  armes : %d   unites : %d" % (r1_weapons, len(r1_units)))
    for uid in r1_units[:20]:
        print("    %s" % uid)
    if len(r1_units) > 20:
        print("    ... (+%d)" % (len(r1_units) - 20))

    # --- etape 3 : ventilation par le tri NATIF ---------------------------------------------------
    cat = {"sans_arme": [], "melee_only": [], "ranged_only": [], "mixte": []}
    for _k, uid in all_ids:
        ws = _weapons(uid)
        m, r = _split_natif(ws)
        if not ws:
            cat["sans_arme"].append(uid)
        elif m and r:
            cat["mixte"].append(uid)
        elif m:
            cat["melee_only"].append(uid)
        else:
            cat["ranged_only"].append(uid)
    print("ETAPE 3 -- VENTILATION (tri NATIF `get_IsMelee`)")
    total = 0
    for k in ("sans_arme", "melee_only", "ranged_only", "mixte"):
        print("  %-12s : %d" % (k, len(cat[k])))
        total += len(cat[k])
    assert total == len(all_ids), "partition non exhaustive : %d != %d" % (total, len(all_ids))
    print("  somme      : %d  (partition exhaustive)" % total)
    if cat["ranged_only"]:
        print("  ranged_only (regime ou l'ADJACENT bascule de `ranged` a VIDE) :")
        for uid in cat["ranged_only"][:20]:
            print("    %s  armes=%s" % (uid, [w.get("Range") for w in _weapons(uid)]))

    # --- etape 4 : diff avant/apres, unite x distance ----------------------------------------------
    print("ETAPE 4 -- DIFF AVANT/APRES (dist 1..%d ; is_adjacent = (dist == 1))" % args.max_dist)
    diffs = {}
    n_cases = 0
    for _k, uid in all_ids:
        ws = _weapons(uid)
        for d in range(1, args.max_dist + 1):
            adj = (d == 1)
            n_cases += 1
            a = _select_avant(ws, adj, d)
            b = _select_apres(ws, adj, d)
            if a is b:
                continue
            key = ("ARME->VIDE" if (a is not None and b is None) else
                   "VIDE->ARME" if (a is None and b is not None) else "ARME->AUTRE ARME")
            diffs.setdefault(key, []).append((uid, d, (a or {}).get("DamageProfile"),
                                              (b or {}).get("DamageProfile")))
    print("  cas evalues : %d" % n_cases)
    for key in sorted(diffs):
        rows = diffs[key]
        us = sorted({u for u, _d, _a, _b in rows})
        print("  %-16s : %d cas, %d unites" % (key, len(rows), len(us)))
        for row in rows[:8]:
            print("      %s d=%d  %s -> %s" % row)
        if len(rows) > 8:
            print("      ... (+%d)" % (len(rows) - 8))
    if not diffs:
        print("  AUCUNE divergence -- le lot ne discrimine PAS les deux hypotheses.")

    # --- etape 5 : contre-epreuve du porteur mesure (#419-r1-tr14-r1) ------------------------------
    print("ETAPE 5 -- PORTEUR MESURE `templNpc1Initiate`")
    ws = _weapons("templNpc1Initiate")
    print("  armes : %s" % [(w.get("DamageProfile"), w.get("Range"), w.get("hits")) for w in ws])
    for d, adj in ((1, True), (2, False)):
        a, b = _select_avant(ws, adj, d), _select_apres(ws, adj, d)
        print("  d=%d adj=%s  AVANT=%s  APRES=%s"
              % (d, adj, (a or {}).get("DamageProfile"), (b or {}).get("DamageProfile")))

    # --- etape 6 : LA MESURE DECRIT-ELLE LE CODE LIVRE ? --------------------------------------------
    # Une simulation qui a diverge du code reel mesure une hypothese, pas le port. On confronte donc
    # `_select_apres` a l'implementation VRAIE sur tous les cas de l'etape 4.
    from engine.services.battle_query import get_attack_weapon_for_default_normal_attack as REEL
    print("ETAPE 6 -- LA SIMULATION `_select_apres` CONTRE LE CODE LIVRE")
    ecarts = []
    for _k, uid in all_ids:
        for d in range(1, args.max_dist + 1):
            adj = (d == 1)
            sim = _select_apres(_weapons(uid), adj, d)
            reel, _r = REEL(uid, adj, dist=d)
            if (sim is None) != (reel is None) or (
                    sim is not None and sim.get("DamageProfile") != reel.get("DamageProfile")):
                ecarts.append((uid, d, (sim or {}).get("DamageProfile"),
                               (reel or {}).get("DamageProfile")))
    print("  ecarts : %d" % len(ecarts))
    for row in ecarts[:10]:
        print("    %s d=%d  sim=%s  reel=%s" % row)
    if ecarts:
        print("  ECHEC -- la mesure de l'etape 4 ne decrit PAS le code livre.")
        return 1
    print("  OK -- l'etape 4 mesure bien le code livre.")

    # --- etape 7 : la porte a-t-elle un effet PARTOUT ? ---------------------------------------------
    # Contre-epreuve du probe lui-meme : si `_select_avant` et `_select_apres` coincidaient, le lot
    # ne discriminerait rien et l'etape 4 serait un vert vide.
    print("ETAPE 7 -- NON-DEGENERESCENCE DU LOT")
    assert diffs, "le lot ne separe PAS les deux hypotheses : l'etape 4 ne conclut rien"
    print("  le lot separe les deux hypotheses (%d classes de divergence)" % len(diffs))

    # --- etape 8 : la DISTANCE BINAIRE du runner contre la distance REELLE -------------------------
    # Le combat rabattait `dist` sur `1 if adjacent else 2` : la porte `dist <= Range` ne pouvait
    # alors jamais mordre au-dela de 2. Ce volet compte, unite par unite, les distances ou le choix
    # d'arme change quand on passe au canal REEL.
    print("ETAPE 8 -- DISTANCE BINAIRE (1/2) CONTRE DISTANCE REELLE, cote COMBAT")
    chg_vide, chg_arme, uset = 0, 0, set()
    for _k, uid in all_ids:
        ws = _weapons(uid)
        for d in range(2, args.max_dist + 1):          # d == 1 : les deux canaux coincident
            bina = _select_apres(ws, False, 2)         # ce que le runner voyait
            reel = _select_apres(ws, False, d)         # ce que le natif voit
            if bina is reel:
                continue
            uset.add(uid)
            if reel is None:
                chg_vide += 1
            else:
                chg_arme += 1
    print("  cas ou le choix CHANGE : %d (dont %d ARME->VIDE, %d ARME->AUTRE ARME), %d unites"
          % (chg_vide + chg_arme, chg_vide, chg_arme, len(uset)))
    print("  -> ARME->VIDE = les no-op de combat que le port manquait (mesure live : natif 0 degat "
          "/ 0 tirage, port 1311 / 2)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
