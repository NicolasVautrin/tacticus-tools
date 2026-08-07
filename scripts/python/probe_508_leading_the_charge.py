#!/usr/bin/env python
"""probe #508 -- `LeadingTheCharge` (1204, `astraDreir`) CONFRONTEE au natif, etage par etage.

CE QUI EST MESURE
-----------------
Avant #508 l'ability etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, donc le cast
partait, l'`AbilityHandler` rendait `ported=False` et RIEN ne se passait -- 0 deplacement, 0 degat,
0 summon, AUCUNE erreur. Le probe monte plusieurs regimes, prend une capture complete
(`decisionView`/`observeBattle`/`combatSnapshot`/`tileMeta`/`boardGraph` + `dumpRng`), rejoue le cast
HORS LIGNE par le CHEMIN COMPLET du moteur (`Runner.apply`), lance le cast NATIF sur le MEME runner,
et confronte les CINQ etages -- jamais un scalaire :

  E0  `ported`                 -- l'observable qui distingue le port du no-op ;
  E1  la TUILE D'ATTERRISSAGE  -- `GetMoveTile` = `First(SortTilesByUtility(<charge>, caster,
      UtilityBucket[MovementSuggestion(33), LeadingTheCharge_ChargeTile(67)]))`. C'est l'etage que la
      feuille d'utilite 67 (`engine/utilities/leading_the_charge.py`) decide, et le SEUL ou elle est
      observable : la porter de travers deplace Dreir d'une tuile sans rien changer au total ;
  E2  la SEQUENCE coup par coup -- les `UnitDamaged` natifs (`Active_Ability_Type=1204`) confrontes
      aux `per_hit_health` du port, CAPES comme le natif cape. Un COMPTE de coups juste ne prouve
      rien : c'est la sequence qui montre l'ordre et les montants ;
  E3  les SUMMONS              -- combien (`nrOfSummons`), SUR QUELLES TUILES, et ce que chacun
      frappe (`PerformAIAttackFromCurrentPosition`). Les `UnitDamaged` dont l'attaquant N'EST PAS le
      caster sont exactement les attaques des Death Riders ;
  E4  les TIRAGES `genrand_int32` consommes, PORT vs NATIF (`dumpRng` avant/apres). C'est l'etage qui
      LOCALISE une divergence : meme compte + montants differents = arithmetique ; comptes differents
      = STRUCTURE (un tirage en trop ou en moins decale TOUT l'aval).

MONTAGE (board `MC1_67`) -- les positions sont DRIVEES, jamais subies
---------------------------------------------------------------------
Le masque de 1204 (preset `TargetingOptions statics+0x240`, `rules = 0x102004032`) impose trois
contraintes AVANT toute mesure, et un montage qui les viole ne mesure RIEN :
  * `CasterHasNotMoved`      -> caster n'a pas bouge (vrai au 1er tour) ;
  * `TargetIsNotAdjacent`    -> la cible doit etre a distance >= 2 ;
  * `TargetHasFreeAdjacentTile` + `GetDynamicInvalidTargetReason` -> il faut au moins une tuile
    LIBRE adjacente a la cible, atteignable en <= `range` = 4 pas depuis le caster.

    astraDreir      (5,5)   le caster (HERO, DANS le pool `--list-pool` rank 17)
    <FILLER>        (1,1)   FIGURANT allie -- garde le tour au camp joueur apres le cast, sinon le
                            turn-start ennemi rend a la cible les PV qu'on vient de lui prendre et
                            le delta lu vaut un FAUX ZERO (mesure #504, meme piege ici)
    necroWarden     (5,8)   la CIBLE -- distance 3, hors adjacence, avec des hex libres autour

REGIMES
-------
    R1 `charge`      geometrie ouverte : Dreir charge, frappe 3x Power, et pose ses Death Riders sur
       les hex libres autour de sa tuile d'ARRIVEE.
    R2 `encercle`    la cible est entouree d'ennemis sauf UN hex : la tuile d'atterrissage est
       FORCEE, donc E1 devient un test a une seule reponse possible -- et le compte de tuiles de
       summon chute, ce qui exerce le `First(..., nrOfSummons)`.

Usage (depuis `scripts/python`, ASCII only) :
    python probe_508_leading_the_charge.py                # les deux regimes
    python probe_508_leading_the_charge.py --regime R1
    python probe_508_leading_the_charge.py --tables       # etage OFFLINE des registres (sans runner)
    python probe_508_leading_the_charge.py --ab           # + les contre-epreuves hors-ligne
    python probe_508_leading_the_charge.py --keep         # ne dispose PAS les runners
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

HOST = "http://127.0.0.1:8765"
PYDIR = os.path.dirname(os.path.abspath(__file__))

LEADING_THE_CHARGE = 1204                  # `ActiveAbilityType.LeadingTheCharge`

CASTER = "astraDreir"                      # « Dreir », seul porteur LINEUP de 1204
FILLER = "deathRotbone"                    # FIGURANT allie (cf. l'en-tete : garde le tour)
FOE_MAIN = "necroWarden"                   # la cible du message, a distance 3
FOE_A = "orksNob"                          # encerclement (R2)
FOE_B = "tauMarksman"                      # encerclement (R2)
FOE_C = "ultraApothecary"                  # encerclement (R2)

BOARD = "MC1_67"
SEED = 508
PLACES = ((CASTER, "5,5"), (FILLER, "1,1"))
A_PLACES_R1 = ((FOE_MAIN, "5,8"),)
#: R2 -- la cible garde UN SEUL hex libre adjacent, `(5,7)` : la tuile d'atterrissage n'a plus
#: qu'une reponse possible. DEUX etages deviennent alors discriminants :
#:  * `First(<tuiles de summon>, nrOfSummons)` doit rendre **3** tuiles pour **4** summons demandes
#:    (les voisins libres de `(5,7)` sont `(4,6)`, `(5,6)`, `(6,6)`) ;
#:  * le `SortByFormula(ConditionalAmount(HasAdjacentEnemies, 1, 0), ascending = 0)` doit rejeter
#:    `(5,6)` EN DERNIER -- c'est le seul des trois qui n'a AUCUN ennemi adjacent, la ou `(4,6)`
#:    touche `(4,7)` et `(6,6)` touche `(6,7)`. Un tri inerte les laisserait dans l'ordre source.
#: `(5,9)` serait HORS BOARD (`MC1_67` = 7x9, rows 0..8) -- mesure du 2026-08-07, le build refuse.
A_PLACES_R2 = ((FOE_MAIN, "5,8"), (FOE_A, "4,7"), (FOE_B, "6,7"), (FOE_C, "6,8"))
UNITES = {"R1": (CASTER, FILLER, FOE_MAIN),
          "R2": (CASTER, FILLER, FOE_MAIN, FOE_A, FOE_B, FOE_C)}
A_PLACES = {"R1": A_PLACES_R1, "R2": A_PLACES_R2}

#: `UnitDamaged` natif : on lit la SEQUENCE coup par coup (attaquant, cible, montant), pas un total.
RE_DMG = re.compile(
    r"UnitDamaged e=(\d+).*?Attacker_Id=(\d+) Target_Id=(\d+) Amount=(-?\d+) "
    r"DamageProfileType=(\d+) Active_Ability_Type=(\d+)")
#: `AddUnit` natif -- les Death Riders poses par le `Spawn`, avec LEUR TUILE (`Unit_Foot_Tile_Id_1`).
#: C'est l'observable de `GetSummonTiles`, et le SEUL qui distingue les deux lectures possibles du
#: seuil de `HasAdjacentEnemies` (`Count > 1` contre `Count >= 1`).
RE_ADD = re.compile(r"AddUnit e=(\d+)\s+Unit_Owner_Id=\d+[^\n]*?Unit_Parent_Id=(\d+) "
                    r"Unit_Foot_Tile_Id_1=(\d+)")


# ------------------------------------------------------------------ transport

def _sid():
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))["session"]["id"]


def _rpc(sid, method, body=None, timeout=120):
    payload = json.dumps({"method": method,
                          "args": [body] if body is not None else []}).encode("utf-8")
    req = urllib.request.Request("%s/api/scripts/%s/rpc" % (HOST, sid), data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode("utf-8"))
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _duel(args, timeout=400):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=PYDIR,
                          capture_output=True, text=True, timeout=timeout)


# ------------------------------------------------------------------ montage

def build(state_file: str, regime: str):
    """Monte le runner du regime demande. Rend `runnerId`, ou `None` si le build echoue."""
    argv = ["build", "--seed", str(SEED), "--board", BOARD, "--crit", "0,0",
            "--hp-target", "400000",
            "--p-units", ",".join(v for v, _t in PLACES),
            "--a-units", ",".join(v for v, _t in A_PLACES[regime]),
            "--state-file", state_file]
    for vid, tile in PLACES:
        argv += ["--place", "%s:%s" % (vid, tile)]
    for vid, tile in A_PLACES[regime]:
        argv += ["--a-place", "%s:%s" % (vid, tile)]
    p = _duel(argv)
    if p.returncode != 0:
        print("[build %s] rc=%s\n%s\n%s" % (regime, p.returncode, p.stdout[-1500:], p.stderr[-800:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return int(json.load(f)["runnerId"])


def unites(sid, rid):
    """{visualId: {'id','pos','hp','alive'}} -- aucun id d'entite en dur."""
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = {"id": u.get("id"), "pos": (p.get("col"), p.get("row")),
                                  "hp": u.get("hp"), "alive": not u.get("isDead")}
    return out


def capture(sid, rid):
    """L'etat COMPLET juste avant le cast natif -- le substrat du rejeu porte."""
    return {
        "dv": _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150),
        "ob": _rpc(sid, "observeBattle", {"runnerId": rid}, 90),
        "snap": _rpc(sid, "combatSnapshot", {"runnerId": rid}, 120),
        "tm": _rpc(sid, "tileMeta", {"runnerId": rid}, 120),
        "tiles": _rpc(sid, "boardGraph", {"runnerId": rid}, 90)["tiles"],
        "rng": _rpc(sid, "dumpRng", {"runnerId": rid}, 60),
    }


def assert_montage(u, regime):
    """Un montage DEGENERE rendrait l'accord trivial : on echoue AVANT de mesurer, jamais apres."""
    manquants = [v for v in UNITES[regime] if v not in u]
    if manquants:
        raise SystemExit("montage invalide : unites absentes %r" % (manquants,))
    voulu = dict(PLACES) | dict(A_PLACES[regime])
    mauvais = [(v, u[v]["pos"], voulu[v]) for v in voulu
               if u[v]["pos"] != tuple(int(x) for x in voulu[v].split(","))]
    if mauvais:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %r" % (mauvais,))
    # `TargetIsNotAdjacent` : une cible ADJACENTE serait refusee par le masque -> aucune mesure.
    import hexgeo
    d = hexgeo.distance(u[CASTER]["pos"], u[FOE_MAIN]["pos"])
    if d < 2:
        raise SystemExit("montage DEGENERE : cible ADJACENTE (d=%d), `TargetIsNotAdjacent` "
                         "refuserait le cast" % d)


# ------------------------------------------------------------------ rejeu hors-ligne

def etat_porte(cap):
    """`State` charge depuis la capture, PRNG cale sur `dumpRng`.

    ⚠ Sans ce calage `execute_ability_attack` SKIPPE le degat par repli defensif : on lirait un
    faux `0` et l'accord ne prouverait rien."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    board = Board(cap["tiles"], adjacency="native_sym")
    st = load_state(cap["dv"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"])
    d = cap["rng"]
    if not (isinstance(d, dict) and d.get("mt")):
        raise SystemExit("dumpRng VIDE -- MT non calable, aucune mesure de degat n'a de sens")
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(d["mt"]), d["mti"]
    st.rng = rng
    return st


def _hp(st, ids):
    from engine.runner.components import HealthComponent
    out = {}
    for i in ids:
        e = st.get_entity(int(i))
        h = e.get_component(HealthComponent) if e is not None else None
        out[int(i)] = None if h is None else h.hp
    return out


def _pos(st, uid):
    from engine.runner.components import PositionComponent
    e = st.get_entity(int(uid))
    p = e.get_component(PositionComponent) if e is not None else None
    return None if p is None else (p.col, p.row)


def rejeu_porte(cap, caster_id, target_id, ids):
    """Rejoue le cast par le CHEMIN COMPLET du moteur (`Runner.apply(ActiveAbilityMessage)`), pas
    par un appel direct a `execute_behaviour` : c'est ce qui exerce le registre `ABILITY_CLASSES`
    et rend `ability_handler.last['ported']` -- l'observable qui distingue le port du NO-OP."""
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner
    st = etat_porte(cap)
    avant = _hp(st, ids)
    pos_avant = _pos(st, caster_id)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=int(caster_id), target_id=int(target_id),
                                      ability_type=LEADING_THE_CHARGE))
    last = getattr(runner.ability_handler, "last", None) or {}   # `diag` est SPREAD dans `last`
    apres = _hp(st, ids)
    # `AttackWithAttackDamage` emet `{caster, target, total, attack}` ; l'attaque de la CHARGE est
    # celle dont le `caster` est le caster du message (les autres sont les
    # `PerformAIAttackFromCurrentPosition` des Death Riders, qui passent par un AUTRE canal).
    atk = ((last.get("attack") or {}).get("attack")
           if isinstance(last.get("attack"), dict) and "attack" in (last.get("attack") or {})
           else (last.get("attack") or {}))
    hp_run, seq = dict(avant), []
    for m in ((atk or {}).get("per_hit_health") or []):
        t = int(target_id)
        applique = max(0, min(int(m), int(hp_run.get(t) or 0)))
        hp_run[t] = int(hp_run.get(t) or 0) - applique
        seq.append((t, applique))
    return {
        "ported": last.get("ported"),
        "pos_avant": pos_avant, "pos_apres": _pos(st, caster_id), "dest": last.get("dest"),
        "delta": {i: (avant[i] - apres[i]) for i in avant
                  if avant[i] is not None and apres[i] is not None and avant[i] != apres[i]},
        "seq": seq,
        "total_charge": (atk or {}).get("total"),
        # Les attaques des Death Riders passent par la feuille `PerformAIAttack` (on-appearance) :
        # le diag de l'ability les remonte sous `rider_attacks`.
        "attaques_summons": last.get("rider_attacks"),
        "pierce": last.get("pierce"), "n_summons": last.get("n_summons"),
        "summon_tiles": [tuple(st.board.coord(t)) if isinstance(t, int) else tuple(t)
                         for t in (last.get("summon_tiles") or [])],
        "spawned": last.get("spawned") or [],
        "attacked": last.get("attacked"),
        "mt": (list(st.rng.mt), st.rng.mti),
    }


def tirages(rng_initial, mt_cible, mti_cible, cap=1200):
    """Nombre de `genrand_int32` consommes pour aller de l'etat INITIAL a l'etat CIBLE.

    C'est l'etage qui LOCALISE une divergence de sequence : deux moteurs qui rendent des montants
    differents mais consomment le MEME nombre de tirages ont un bug d'ARITHMETIQUE ; s'ils n'en
    consomment pas le meme nombre, c'est la STRUCTURE. Rend None si non atteint."""
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt, r.mti = list(rng_initial["mt"]), rng_initial["mti"]
    for n in range(cap + 1):
        if r.mti == mti_cible and r.mt == mt_cible:
            return n
        r.genrand_int32()
    return None


# ------------------------------------------------------------------ etage OFFLINE des registres

def etage_tables() -> bool:
    """Le CONTRAT DE DISJONCTION, RE-COMPTE par le code (jamais par soustraction) -- c'est ce que
    demande le paragraphe « CE COMPTE SE RE-COMPTE » de `runner/abilities/targeting.py`."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,
                                                   TARGETING_OPTIONS_UNPORTED)
    ok = True
    print("[508:tables] ABILITY_CLASSES=%d  TARGETING_OPTIONS_UNPORTED=%d  "
          "DYNAMIC_TARGET_RULE_UNPORTED=%d"
          % (len(ABILITY_CLASSES), len(TARGETING_OPTIONS_UNPORTED),
             len(DYNAMIC_TARGET_RULE_UNPORTED)))
    inter = sorted(set(ABILITY_CLASSES) & set(TARGETING_OPTIONS_UNPORTED))
    if inter:
        print("  KO disjonction rompue (deux sources de masque) : %r" % (inter,))
        ok = False
    cls = ABILITY_CLASSES.get(LEADING_THE_CHARGE)
    if cls is None:
        print("  KO 1204 ABSENTE d'ABILITY_CLASSES -- le no-op n'est pas leve")
        ok = False
    else:
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        if opts is None or int(opts.rules) != 0x102004032:
            print("  KO masque de 1204 : %r (attendu 0x102004032, preset statics+0x240)"
                  % (None if opts is None else hex(int(opts.rules)),))
            ok = False
        else:
            print("  OK masque 1204 = 0x%x (preset `TargetingOptions statics+0x240`)"
                  % int(opts.rules))
    at = ABILITY_ATTACK_TYPE.get(LEADING_THE_CHARGE)
    if at != AbilityAttackType.DirectTargetAttack:
        print("  KO ABILITY_ATTACK_TYPE[1204]=%r (attendu DirectTargetAttack=0, 3e arg du ctor)"
              % (at,))
        ok = False
    else:
        print("  OK ABILITY_ATTACK_TYPE[1204] = DirectTargetAttack (3e argument du ctor)")
    if LEADING_THE_CHARGE in DYNAMIC_TARGET_RULE_UNPORTED:
        print("  KO 1204 encore dans DYNAMIC_TARGET_RULE_UNPORTED alors que la classe SURCHARGE")
        ok = False
    # La feuille d'utilite 67 doit etre au registre, sinon `calculate_utility` LEVE au 1er cast.
    from engine.utilities.tile import utilities_database
    from engine.utilities.utility_type import UtilityType
    u67 = utilities_database(int(UtilityType.LeadingTheCharge_ChargeTile))
    if u67 is None:
        print("  KO UtilityType.LeadingTheCharge_ChargeTile (67) hors UtilitiesDatabase")
        ok = False
    else:
        print("  OK utilite 67 enregistree : %s" % type(u67).__name__)
    print("[508:tables] %s" % ("OK" if ok else "KO"))
    return ok


# ------------------------------------------------------------------ contre-epreuves

def contre_epreuves(cap, caster_id, target_id, ids):
    """Chaque variante ne change QU'UNE lecture du mirror. Si l'une rendait le MEME resultat que
    REF, la lecture correspondante ne serait pas mesuree par ce montage."""
    import engine.runner.abilities.loki.leading_the_charge as LTC
    from engine.utilities.decider import UtilityBucket, UtilityDefinition, WeightedUtility
    from engine.utilities.tile import first_tile_by_utility
    from engine.utilities.utility_type import UtilityType

    st = etat_porte(cap)
    cands = LTC.leading_the_charge_possible_move_tiles_selector(4).evaluate(
        __import__("engine.runner.abilities.behaviours.context", fromlist=["x"])
        .entities_from_state(st, int(caster_id), int(target_id)))
    board = st.board
    out = {}

    def _first(defn):
        t = first_tile_by_utility(st, cands, unit_id=int(caster_id), utility_definition=defn)
        return None if t is None else tuple(board.coord(t))

    out["REF bucket [33, 67]"] = _first(LTC.LEADING_THE_CHARGE_TILE_UTILITY)
    out["AB1 MovementSuggestion seule"] = _first(
        UtilityDefinition.from_utility_type(int(UtilityType.MovementSuggestion)))
    out["AB2 ChargeTile seule"] = _first(
        UtilityDefinition.from_utility_type(int(UtilityType.LeadingTheCharge_ChargeTile)))
    out["AB3 Tile(7) seule"] = _first(UtilityDefinition.from_utility_type(int(UtilityType.Tile)))
    out["AB4 bucket [33, 7]"] = _first(UtilityDefinition(UtilityBucket([
        WeightedUtility(utility_type=int(UtilityType.MovementSuggestion)),
        WeightedUtility(utility_type=int(UtilityType.Tile))])))
    out["--- candidats"] = len(cands)
    return out


# ------------------------------------------------------------------ mesure

def mesure(sid, state_file, regime, avec_ab=False, garder=False):
    rid = build(state_file, regime)
    if rid is None:
        return None
    try:
        u = unites(sid, rid)
        assert_montage(u, regime)
        ids = [u[v]["id"] for v in UNITES[regime]]
        cid, tid = u[CASTER]["id"], u[FOE_MAIN]["id"]
        cap = capture(sid, rid)
        port = rejeu_porte(cap, cid, tid, ids)
        ab = contre_epreuves(cap, cid, tid, ids) if avec_ab else None
        p = _duel(["act", "ability", "--caster", str(cid), "--ability", str(LEADING_THE_CHARGE),
                   "--target", str(tid), "--state-file", state_file, "--runner", str(rid)])
        apres = unites(sid, rid)
        dmg = [(int(at), int(t), int(a), int(pr))
               for _e, at, t, a, pr, aid in RE_DMG.findall(p.stdout or "")
               if int(aid) in (LEADING_THE_CHARGE, 0) or True]
        natif = {
            "pos_apres": (apres.get(CASTER) or {}).get("pos"),
            "delta": {u[v]["id"]: u[v]["hp"] - apres[v]["hp"] for v in u
                      if v in apres and u[v]["hp"] is not None and apres[v]["hp"] is not None
                      and u[v]["hp"] != apres[v]["hp"]},
            # Les coups du CASTER = l'attaque de la charge ; ceux d'un AUTRE attaquant = les
            # `PerformAIAttackFromCurrentPosition` des Death Riders.
            "seq": [(t, a) for at, t, a, _pr in dmg if at == int(cid)],
            "seq_summons": [(at, t, a) for at, t, a, _pr in dmg if at != int(cid)],
            "profils": [pr for at, _t, _a, pr in dmg if at == int(cid)],
            "ajoutes": [(int(e), int(par), int(t)) for e, par, t in RE_ADD.findall(p.stdout or "")],
            "unites_apres": {v: apres[v]["id"] for v in apres},
            "tronque": "(+" in (p.stdout or "") and "events)" in (p.stdout or ""),
            "rc": p.returncode, "out": (p.stdout or "")[-3000:] + (p.stderr or "")[-800:]}
        # Les tuiles natives de summon, EN (col,row) -- l'observable de `GetSummonTiles`.
        _bg = {int(t["id"]): (int(t["col"]), int(t["row"])) for t in cap["tiles"]}
        natif["tuiles_summon"] = [_bg.get(t) for _e, _par, t in natif["ajoutes"]]
        rng_apres = _rpc(sid, "dumpRng", {"runnerId": rid}, 60)
        natif["tirages"] = (tirages(cap["rng"], rng_apres.get("mt"), rng_apres.get("mti"))
                            if isinstance(rng_apres, dict) and rng_apres.get("mt") else None)
        port["tirages"] = tirages(cap["rng"], port["mt"][0], port["mt"][1])
        return {"regime": regime, "rid": rid, "caster": cid, "cible": tid,
                "ids": {v: u[v]["id"] for v in u},
                "hp_avant": {v: u[v]["hp"] for v in u},
                "pos_avant": {v: u[v]["pos"] for v in u},
                "port": port, "natif": natif, "ab": ab}
    finally:
        if not garder:
            _duel(["dispose", "--state-file", state_file, "--runner", str(rid)], timeout=120)


def _rapport(m) -> bool:
    ids = m["ids"]
    inv = {i: v for v, i in ids.items()}
    print("[508:%s] runner=%s caster=u%s cible=u%s" % (m["regime"], m["rid"], m["caster"],
                                                       m["cible"]))
    print("        unites : " + " ".join("%s=u%s@%s(hp%s)" % (v, ids[v], m["pos_avant"][v],
                                                              m["hp_avant"][v])
                                         for v in sorted(ids)))
    fmt = lambda d: {("%s/u%s" % (inv.get(i, "?"), i)): v for i, v in sorted(d.items())}
    p, n = m["port"], m["natif"]
    print("  E0 ported = %s   (False = le NO-OP n'est pas leve)" % (p["ported"],))
    print("  E1 tuile d'atterrissage  PORT=%s (dest=%s, depart=%s)   NATIF=%s"
          % (p["pos_apres"], p["dest"], p["pos_avant"], n["pos_apres"]))
    print("  E2 delta hp PORT =%s" % (fmt(p["delta"]),))
    print("             NATIF=%s" % (fmt(n["delta"]),))
    print("     SEQUENCE  PORT (%d coups) =%s" % (len(p["seq"]), [("u%s" % t, a)
                                                                  for t, a in p["seq"]]))
    print("               NATIF(%d coups) =%s   profils=%s (tronque=%s)"
          % (len(n["seq"]), [("u%s" % t, a) for t, a in n["seq"]], n["profils"], n["tronque"]))
    print("     total de la CHARGE seule : PORT=%s   NATIF=%s"
          % (p.get("total_charge"), sum(a for _t, a in n["seq"])))
    print("  E3 summons  PORT n=%s tuiles=%s spawned=%s pierce=%s attacked=%s"
          % (p["n_summons"], p["summon_tiles"], p["spawned"], p["pierce"], p["attacked"]))
    print("     PORT attaques des Death Riders = %s" % (p.get("attaques_summons"),))
    print("     NATIF AddUnit=%s tuiles=%s   attaques des summons=%s"
          % (n["ajoutes"], n.get("tuiles_summon"),
             [("u%s->u%s" % (a, t), d) for a, t, d in n["seq_summons"]]))
    print("  E4 TIRAGES genrand_int32 consommes : PORT=%s  NATIF=%s"
          % (p.get("tirages"), n.get("tirages")))
    if m["ab"]:
        print("  -- contre-epreuves (hors-ligne, meme capture) : tuile choisie par definition --")
        for nom, r in m["ab"].items():
            print("     %-32s %s" % (nom, r))
    ok = (bool(p["ported"]) and p["pos_apres"] == n["pos_apres"]
          and p["seq"] == n["seq"] and len(n["seq"]) > 0)
    if not ok:
        print("  -- sortie du cast NATIF (diagnostic) --")
        print(n.get("out", ""))
    print("[508:%s] %s" % (m["regime"], "ACCORD port/natif sur E0+E1+E2" if ok else "DESACCORD"))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="probe #508 -- LeadingTheCharge (1204) vs natif")
    ap.add_argument("--regime", default="all", choices=("all", "R1", "R2"))
    ap.add_argument("--tables", action="store_true", help="etage OFFLINE des registres, sans runner")
    ap.add_argument("--ab", action="store_true", help="joue aussi les contre-epreuves")
    ap.add_argument("--keep", action="store_true", help="ne dispose PAS les runners")
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()
    if a.tables:
        return 0 if etage_tables() else 1
    base = a.state_file or os.path.join(tempfile.gettempdir(), "p508_ltc_%d" % os.getpid())
    sid = _sid()
    regimes = ("R1", "R2") if a.regime == "all" else (a.regime,)
    verdicts = [etage_tables()]
    for reg in regimes:
        sf = "%s_%s.json" % (base[:-5] if base.endswith(".json") else base, reg)
        m = mesure(sid, sf, reg, avec_ab=a.ab, garder=a.keep)
        if m is None:
            print("[508:%s] build KO -- rien mesure" % reg)
            return 99
        verdicts.append(_rapport(m))
    return 0 if all(verdicts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
