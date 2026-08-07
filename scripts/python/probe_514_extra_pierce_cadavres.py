#!/usr/bin/env python
"""#514 -- la primitive pool-8 `AllUnits` CONFRONTEE au natif, AVEC DES CADAVRES SUR LE PLATEAU.

POURQUOI CE PROBE EXISTE
------------------------
#508 a livre `1204 LeadingTheCharge` avec un accord bit-exact sur le degat, mais dans un regime
**DEGENERE pour le terme qui nous interesse** : aucun allie de Dreir n'etait mort, donc

    GetExtraPierceRatio = Multiply( Direct(GetVariableForLevel(0x3f = extraPierceRatio)),
                                    Count(Filter(AllUnits(), IsNormalUnit & AreFriends(Owner)
                                                             & HasBeenDefeated)) )

valait `0` DES DEUX COTES -- et un selecteur qui filtre les mortes rend le MEME `0` qu'un selecteur
qui ne les filtre pas. C'est le residu `#508-r1`, volet `AllUnits`.

#514 a scinde les deux primitives (`AllUnits` = `DSLSelectors$$AllUnits`, `IBattleQuery` slot 136,
`EntityPool.AllUnits`, MORTS INCLUS ; `AllAliveUnits` = le champ partage `<dsl>+0x20`, slot 137,
`EntityPool.AliveUnits`) et re-ecrit `GetExtraPierceRatio` en ARBRE DSL sur la bonne. Ce probe
FABRIQUE le cadavre qui manquait et confronte le terme.

MONTAGE -- le cadavre est PRODUIT, pas espere
---------------------------------------------
Board `MC1_67`, seed 514, positions DRIVEES.

    astraDreir     (5,5)  le caster
    <FRAGILE>      (2,2)  allie NORMAL a `Health` rabaisse par `--unit-stat` : c'est LUI qui doit
                          mourir ; place au CONTACT du tueur pour que le tour IA le tue a coup sur
    <TUEUR>        (2,3)  ennemi adjacent au fragile
    necroWarden    (5,8)  la cible du cast -- a distance >= 2 de Dreir, avec des hex libres autour

Sequence : build -> `act endturn` (le joueur ne fait RIEN) -> `aiturn` (l'IA tue le fragile) ->
on VERIFIE le cadavre -> capture -> rejeu porte -> cast NATIF -> confrontation.

REGIME TEMOIN : le meme montage SANS le tour IA (personne n'est mort). Sans lui, un accord sur
`extraPierce != 0` ne dirait pas si le terme REAGIT au cadavre ou s'il vaut ca en permanence.

CE QUI EST CONFRONTE (jamais un scalaire nu)
--------------------------------------------
  E0  le compte PORTE `leading_the_charge_defeated_friends_count` : 0 (temoin) vs 1 (cadavre) ;
  E1  la modification de stat NATIVE `UnitStats_ExtraPierce_Modification` lue dans les events du
      cast, confrontee au `pierce` que le port pose ;
  E2  la SEQUENCE de degat coup par coup, port vs natif -- un `ExtraPierce` faux deplace les
      montants, et un total juste ne prouverait rien ;
  E3  les tirages `genrand_int32` consommes des deux cotes.

Usage (depuis `scripts/python`, ASCII only) :
    python probe_514_extra_pierce_cadavres.py
    python probe_514_extra_pierce_cadavres.py --regime cadavre
    python probe_514_extra_pierce_cadavres.py --keep
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import probe_508_leading_the_charge as P508   # noqa: E402 -- transport + rejeu deja mesures

BOARD = P508.BOARD
SEED = 514
CASTER = P508.CASTER               # astraDreir
FOE_MAIN = P508.FOE_MAIN           # necroWarden -- la cible
FRAGILE = "deathRotbone"           # allie NORMAL sacrifie (meme figurant que #508)
TUEUR = "orksNob"                  # ennemi charge de le tuer

#: cf. le commentaire de `build` : rend `ExtraPierce` OBSERVABLE SUR LE DEGAT.
ARMURE_CIBLE = 2400

PLACES = ((CASTER, "5,5"), (FRAGILE, "2,2"))
A_PLACES = ((FOE_MAIN, "5,8"), (TUEUR, "2,3"))

#: `UnitStats_ExtraPierce_Modification=<n>` -- l'observable NATIVE du terme mesure ici.
RE_PIERCE = re.compile(r"UnitStats_ExtraPierce_Modification=(-?\d+)")


def build(state_file: str, pv_fragile: int):
    argv = ["build", "--seed", str(SEED), "--board", BOARD, "--crit", "0,0",
            "--hp-target", "400000",
            # ARMURE de la cible -- sans elle, `ExtraPierce` est INERTE SUR LE DEGAT : le plancher
            # natif `Damage$$GetDamageWithPiercing` vaut `max(0, d - armure, d * pierce%)`, et avec
            # `armure = 0` (ce que pose `--hp-target`) c'est TOUJOURS `d` qui l'emporte. Mesure du
            # 2026-08-07 : sans armure, le port d'AVANT #514 (pierce = 0) rendait la MEME sequence
            # de degat que le natif (pierce = 10) -- accord en regime DEGENERE. La valeur est
            # choisie JUSTE SOUS le degat par coup (~2500) pour que la branche PERCAGE l'emporte.
            "--armor-target", str(ARMURE_CIBLE),
            # `Health` SEUL ne suffit pas : le BC porte AUSSI `RemainingHealth`, et c'est LUI que
            # la fabrique d'unite lit pour les PV courants (`--hp-player` ecrit les deux). Mesure
            # du 2026-08-07 : `Health=1` seul laissait le figurant a 12047 PV, montage RATE.
            "--unit-stat", "%s:Health=%d,RemainingHealth=%d,Armor=0,FixedArmor=0"
                           % (FRAGILE, pv_fragile, pv_fragile),
            "--p-units", ",".join(v for v, _t in PLACES),
            "--a-units", ",".join(v for v, _t in A_PLACES),
            "--state-file", state_file]
    for vid, tile in PLACES:
        argv += ["--place", "%s:%s" % (vid, tile)]
    for vid, tile in A_PLACES:
        argv += ["--a-place", "%s:%s" % (vid, tile)]
    p = P508._duel(argv)
    if p.returncode != 0:
        print("[514:build] rc=%s\n%s\n%s" % (p.returncode, p.stdout[-2000:], p.stderr[-800:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return int(json.load(f)["runnerId"])


def compte_porte(cap, owner_id: int) -> int:
    """Le compte du port, evalue sur l'etat CAPTURE -- c'est l'etage E0."""
    import engine.runner.abilities.loki.leading_the_charge as LTC
    return int(LTC.leading_the_charge_defeated_friends_count(P508.etat_porte(cap), int(owner_id)))


def mesure(sid, state_file, regime, garder=False):
    """`regime` = 'temoin' (personne ne meurt) ou 'cadavre' (un tour IA tue le fragile)."""
    rid = build(state_file, 200 if regime == "cadavre" else 400000)
    if rid is None:
        return None
    try:
        if regime == "cadavre":
            # Le joueur ne fait RIEN : on rend la main a l'IA, qui tue le fragile au contact.
            P508._duel(["act", "endturn", "--state-file", state_file, "--runner", str(rid)])
            P508._duel(["aiturn", "--state-file", state_file, "--runner", str(rid)], timeout=400)
        u = P508.unites(sid, rid)
        if CASTER not in u or FOE_MAIN not in u:
            return {"erreur": "unites absentes : %r" % (sorted(u),)}
        # ⚠ `decisionView` CONSERVE les unites mortes, et son `isDead` n'est pas toujours pose :
        # le discriminant sur ce canal est donc « PV <= 0 » AUTANT que le drapeau. Sans les deux,
        # un cadavre a 0 PV se lisait « vivant » et le montage etait declare RATE a tort (mesure
        # du 2026-08-07).
        def _mort(e):
            return (not e["alive"]) or (e["hp"] is not None and int(e["hp"]) <= 0)

        morts = sorted(v for v in u if _mort(u[v]))
        cadavre_present = FRAGILE in u and _mort(u[FRAGILE])
        if regime == "cadavre" and not cadavre_present:
            return {"erreur": "MONTAGE RATE -- %s n'est pas mort (hp=%s). Aucune mesure : un "
                              "regime sans cadavre ne distingue pas les deux primitives."
                              % (FRAGILE, (u.get(FRAGILE) or {}).get("hp"))}
        if regime == "temoin" and morts:
            return {"erreur": "TEMOIN pollue : %r deja mort(s)" % (morts,)}
        if _mort(u[CASTER]):
            return {"erreur": "le caster est mort pendant le tour IA -- pas de cast possible"}
        import hexgeo
        d = hexgeo.distance(u[CASTER]["pos"], u[FOE_MAIN]["pos"])
        if d < 2:
            return {"erreur": "cible ADJACENTE (d=%d) : `TargetIsNotAdjacent` refuserait le cast" % d}

        cid, tid = u[CASTER]["id"], u[FOE_MAIN]["id"]
        ids = [u[v]["id"] for v in u]
        cap = P508.capture(sid, rid)
        n_defaits = compte_porte(cap, cid)
        port = P508.rejeu_porte(cap, cid, tid, ids)
        # CONTRE-EPREUVE : le port d'AVANT #514, ou `AllUnits` filtrait les mortes. Si sa sequence
        # est IDENTIQUE, ce montage ne DISCRIMINE PAS les deux primitives et l'accord ci-dessus ne
        # prouve rien -- exactement le piege du regime degenere de #508.
        from engine.entities.selectors import tiles as _tiles
        _orig = _tiles.AllUnits.select
        try:
            _tiles.AllUnits.select = (
                lambda self, c: [x for x in c.units
                                 if bool(x.get("alive", True)) and (x.get("hp") or 0) > 0])
            avant514 = P508.rejeu_porte(cap, cid, tid, ids)
        finally:
            _tiles.AllUnits.select = _orig
        p = P508._duel(["act", "ability", "--caster", str(cid),
                        "--ability", str(P508.LEADING_THE_CHARGE), "--target", str(tid),
                        "--state-file", state_file, "--runner", str(rid)])
        sortie = (p.stdout or "")
        apres = P508.unites(sid, rid)
        dmg = [(int(at), int(t), int(a)) for _e, at, t, a, _pr, _aid in P508.RE_DMG.findall(sortie)]
        rng_apres = P508._rpc(sid, "dumpRng", {"runnerId": rid}, 60)
        return {
            "regime": regime, "rid": rid, "caster": cid, "cible": tid,
            "morts_avant_cast": morts,
            "pos": {v: u[v]["pos"] for v in sorted(u)},
            "hp": {v: u[v]["hp"] for v in sorted(u)},
            "n_defaits_port": n_defaits,
            "pierce_port": port.get("pierce"),
            "pierce_avant514": avant514.get("pierce"),
            "seq_avant514": avant514["seq"],
            "pierce_natif": [int(x) for x in RE_PIERCE.findall(sortie)],
            "seq_port": port["seq"],
            "seq_natif": [(t, a) for at, t, a in dmg if at == int(cid)],
            "pos_apres_port": port["pos_apres"],
            "pos_apres_natif": (apres.get(CASTER) or {}).get("pos"),
            "tirages_port": P508.tirages(cap["rng"], port["mt"][0], port["mt"][1]),
            "tirages_natif": (P508.tirages(cap["rng"], rng_apres.get("mt"), rng_apres.get("mti"))
                              if isinstance(rng_apres, dict) and rng_apres.get("mt") else None),
            "rc": p.returncode, "out": sortie[-2500:] + (p.stderr or "")[-600:],
        }
    finally:
        if not garder:
            P508._duel(["dispose", "--state-file", state_file, "--runner", str(rid)], timeout=120)


def rapport(m) -> bool:
    if m is None:
        print("[514] build KO -- rien mesure")
        return False
    if "erreur" in m:
        print("[514:%s] %s" % (m.get("regime", "?"), m["erreur"]))
        return False
    print("[514:%s] runner=%s caster=u%s cible=u%s" % (m["regime"], m["rid"], m["caster"],
                                                       m["cible"]))
    print("        positions=%s" % (m["pos"],))
    print("        hp=%s   morts AVANT le cast=%s" % (m["hp"], m["morts_avant_cast"]))
    print("  E0 Count(Filter(AllUnits, IsNormalUnit & AreFriends & HasBeenDefeated)) = %d"
          % m["n_defaits_port"])
    print("  E1 ExtraPierce  PORT=%s   NATIF (UnitStats_ExtraPierce_Modification)=%s"
          % (m["pierce_port"], m["pierce_natif"]))
    print("  E2 SEQUENCE de la charge  PORT (%d coups)=%s"
          % (len(m["seq_port"]), [("u%s" % t, a) for t, a in m["seq_port"]]))
    print("                            NATIF(%d coups)=%s"
          % (len(m["seq_natif"]), [("u%s" % t, a) for t, a in m["seq_natif"]]))
    print("     tuile d'atterrissage  PORT=%s  NATIF=%s"
          % (m["pos_apres_port"], m["pos_apres_natif"]))
    print("  E3 tirages genrand_int32  PORT=%s  NATIF=%s"
          % (m["tirages_port"], m["tirages_natif"]))
    print("  CE  contre-epreuve : port d'AVANT #514 (AllUnits filtrait les mortes) --")
    print("        pierce=%s  sequence=%s"
          % (m["pierce_avant514"], [("u%s" % t, a) for t, a in m["seq_avant514"]]))

    attendu = 1 if m["regime"] == "cadavre" else 0
    fails = []
    if m["n_defaits_port"] != attendu:
        fails.append("E0 : compte porte = %d, attendu %d" % (m["n_defaits_port"], attendu))
    # Le natif emet une modification par `AddStaticStatModifierEffect` (pose + retrait) ; on
    # compare la VALEUR POSEE, pas le nombre d'emissions.
    poses = sorted(set(abs(x) for x in m["pierce_natif"]))
    if int(m["pierce_port"] or 0) not in poses and not (poses == [] and not m["pierce_port"]):
        fails.append("E1 : pierce porte %r absent des modifications natives %r"
                     % (m["pierce_port"], m["pierce_natif"]))
    if m["regime"] == "cadavre" and int(m["pierce_port"] or 0) == 0:
        fails.append("E1 : regime CADAVRE mais ExtraPierce = 0 -- terme non exerce, la mesure ne "
                     "distingue toujours pas les deux primitives")
    if m["seq_port"] != m["seq_natif"] or not m["seq_natif"]:
        fails.append("E2 : sequence PORT %r != NATIF %r" % (m["seq_port"], m["seq_natif"]))
    if m["pos_apres_port"] != m["pos_apres_natif"]:
        fails.append("E2 : tuile d'atterrissage PORT %r != NATIF %r"
                     % (m["pos_apres_port"], m["pos_apres_natif"]))
    if m["tirages_port"] != m["tirages_natif"]:
        fails.append("E3 : tirages PORT %r != NATIF %r" % (m["tirages_port"], m["tirages_natif"]))
    if m["regime"] == "cadavre" and (int(m["pierce_avant514"] or 0), m["seq_avant514"]) == \
            (int(m["pierce_port"] or 0), m["seq_natif"]):
        fails.append("CE : le port d'AVANT #514 rend le MEME (pierce, sequence) que le natif -- ce "
                     "montage ne DISCRIMINE pas les deux primitives, l'accord est degenere")
    if fails:
        print("  -- sortie du cast NATIF (diagnostic) --")
        print(m.get("out", ""))
        for f in fails:
            print("  KO %s" % f)
    print("[514:%s] %s" % (m["regime"], "ACCORD port/natif" if not fails else "DESACCORD"))
    return not fails


def main() -> int:
    ap = argparse.ArgumentParser(description="#514 -- AllUnits pool-8 confronte AVEC cadavres")
    ap.add_argument("--regime", default="all", choices=("all", "temoin", "cadavre"))
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()
    base = a.state_file or os.path.join(tempfile.gettempdir(), "p514_pierce_%d" % os.getpid())
    sid = P508._sid()
    regimes = ("temoin", "cadavre") if a.regime == "all" else (a.regime,)
    verdicts = []
    for reg in regimes:
        sf = "%s_%s.json" % (base[:-5] if base.endswith(".json") else base, reg)
        verdicts.append(rapport(mesure(sid, sf, reg, garder=a.keep)))
    return 0 if all(verdicts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
