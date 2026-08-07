#!/usr/bin/env python
"""Generalisation #490 -- le port de `1027 PsychicMaelstrom` hors du montage qui l'a valide.

`probe_490_psychic_maelstrom.py` mesure UN montage (seed 49001, board MC1_67, cible
`necroWarden`). Un port peut y etre bit-exact et faux ailleurs. Ce probe DEPLACE trois axes, en
choisissant a chaque fois un regime ou le comportement porte CHANGE le resultat observable :

  G1 -- GEOMETRIE : board DIFFERENT (`C1_74`) et seed different. Replay-diff bit-exact.
        Ce que ca exerce : rien du montage precedent n'est reutilise (positions, ordre de tour,
        etat initial du PRNG).

  G2 -- CAP `Resilient` + MORT PAR NOMBRE DE COUPS. Cible `blackAbaddon` (trait `Resilient`) a
        BAS PV : `IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit` cape
        CHAQUE coup a `hp - 1`, donc le premier coup ne tue jamais et c'est le NOMBRE DE COUPS qui
        decide de la mort. Le resultat observable devient QUALITATIF (vivante / morte), pas
        seulement un total -- et un port qui figerait `hits=1` laisserait la cible vivante a 1 PV
        la ou le natif la tue. Ce cap est le SEUL etage defensif que le profil `Psychic`
        (PiercingRatio 100 + `NoBlocking`) laisse mordre : ni l'armure ni le block ne peuvent le
        faire, ce qui rend ce montage-la obligatoire pour exercer la route ABILITY.

  G3 -- GATE DE CIBLE (non-regression de la MIGRATION du masque, `TARGETING_OPTIONS_UNPORTED` ->
        classe). Le masque `TargetIsEnemy | TargetMatchesDynamicRule` + `RANGE_FROM_CONFIG`
        (range 2) doit refuser un ALLIE et une cible HORS PORTEE. On confronte l'ensemble des
        cibles que le PORT juge legales a celui que le NATIF rend (`abilityTargets`). Une
        divergence ici serait la degradation PERMISSIVE que le contrat de disjonction protege.

ASCII only (cp1252).
Usage: python probe_490_generalisation.py [--volet G1|G2|G3|tous]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
CASTER_VIS = "astraPrimarisPsy"
ABILITY = 1027
RANGE = 2


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _hp(ob, uid):
    for u in (ob.get("units") or []):
        if u.get("squadId") == uid and not u.get("isDead"):
            return u.get("hp")
    return None


def _build(seed, board, tag, extra):
    state = ROOT / "logs" / "runners" / f"_a490_gen_{tag}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", str(seed),
                        "--state-file", str(state), "--board", board] + extra,
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print(f"[490-gen] build {tag} KO: {(p.stderr or p.stdout or '')[-400:]}", file=sys.stderr)
        return None
    return json.loads(state.read_text())["runnerId"]


def _advance(rpc, rid, vis, max_iter=12):
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if not _ok(dec):
            return None, None
        u = next((x for x in (dec.get("units") or [])
                  if x.get("visualId") == vis and x.get("alive")), None)
        if u is None:
            return dec, None
        if dec.get("currentPlayer") == u.get("owner"):
            return dec, u
        rpc("aiPlayTurn", {"runnerId": rid}, 240)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def _drive(rpc, rid, max_turns=10):
    for _ in range(max_turns):
        dec, me = _advance(rpc, rid, CASTER_VIS)
        if me is None:
            return None, None, None
        en = [u for u in (dec.get("units") or [])
              if u.get("alive") and u.get("owner") != me.get("owner")]
        if not en:
            return None, None, None
        tgt = min(en, key=lambda e: hexgeo.distance(_pos(me), _pos(e)))
        if 1 <= hexgeo.distance(_pos(me), _pos(tgt)) <= RANGE:
            return dec, me, tgt
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == me["id"]), None)
        tiles = [(t["col"], t["row"]) for t in ((cmt or {}).get("tiles") or [])
                 if t.get("col") is not None]
        if tiles:
            tp = _pos(tgt)
            best = min(tiles, key=lambda p: (0 if 1 <= hexgeo.distance(p, tp) <= RANGE else 1,
                                             hexgeo.distance(p, tp)))
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
            dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            me2 = next((x for x in (dec2.get("units") or [])
                        if x.get("visualId") == CASTER_VIS and x.get("alive")), None)
            if me2 is not None:
                e2 = [u for u in (dec2.get("units") or [])
                      if u.get("alive") and u.get("owner") != me2.get("owner")]
                t2 = min(e2, key=lambda e: hexgeo.distance(_pos(me2), _pos(e))) if e2 else None
                if t2 is not None and 1 <= hexgeo.distance(_pos(me2), _pos(t2)) <= RANGE:
                    return dec2, me2, t2
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None, None


def _replay_one(rpc, rid, board, me, tgt, tag, fails, expect_dead=None):
    """Un cast : capture -> live -> offline sur le MEME etat/rng -> diff des deltas HP.
    `expect_dead` (G2) : verdict QUALITATIF attendu sur la cible, confronte des DEUX cotes."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.components import HealthComponent

    cid, tid = me["id"], tgt["id"]
    dec0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        fails.append(f"{tag}:dumpRng")
        return None
    en = [u for u in (dec0.get("units") or [])
          if u.get("alive") and u.get("owner") != me.get("owner")]
    hp0 = {u["id"]: _hp(ob0, u["id"]) for u in en}
    state = load_state(dec0, ob0, snap0, board=board)
    if state.get_entity(cid) is None:
        fails.append(f"{tag}:etat-offline")
        return None
    rng = IntBasedMersenneTwister()
    rng.mt = list(s0["mt"]); rng.mti = s0["mti"]
    state.rng = rng

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ABILITY}}, 240)
    a0 = ((res or {}).get("actions") or [{}])[0]
    if not (a0.get("ok") and a0.get("mutated")):
        fails.append(f"{tag}:cast-live")
        return None
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    live_hp2 = _hp(ob2, tid)
    live_dead = live_hp2 is None
    live = {uid: (hp0[uid] - _hp(ob2, uid))
            for uid in hp0 if hp0.get(uid) is not None and _hp(ob2, uid) is not None}

    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(cid, tid, ABILITY))
    diag = runner.ability_handler.last or {}
    if diag.get("ported") is not True:
        fails.append(f"{tag}:ported")
        return None
    off = {}
    for uid in live:
        e = state.get_entity(uid)
        hc = e.get_component(HealthComponent) if e is not None else None
        if hc is not None:
            off[uid] = hp0[uid] - hc.hp
    te = state.get_entity(tid)
    thc = te.get_component(HealthComponent) if te is not None else None
    off_dead = (thc is None) or (thc.hp is not None and thc.hp <= 0)
    hits = ((diag.get("attacks") or [{}])[0] or {}).get("hits")

    same = live == off
    print(f"[490-gen] {tag} hits={hits} hp0={hp0.get(tid)} live={live} offline={off} "
          f"mort live={live_dead}/offline={off_dead} : {'OK' if same else 'X'}")
    if not same:
        fails.append(f"{tag}:diff")
    if live_dead != off_dead:
        fails.append(f"{tag}:mort-divergente(live={live_dead} off={off_dead})")
    if expect_dead is not None and live_dead != expect_dead:
        print(f"[490-gen] {tag} : regime attendu non atteint (mort={live_dead}, "
              f"attendu {expect_dead}) -- ce cast ne discrimine pas")
    return hits


def volet_g1(rpc, fails):
    """GEOMETRIE : autre board, autre seed."""
    from engine.entities.pathfinding.board import Board
    rid = _build(59001, "C1_74", "g1",
                 ["--p-units", f"{CASTER_VIS},templAncient",
                  "--a-units", "ultraTitus,necroWarden",
                  "--hp-target", "400000", "--hp-player", "400000"])
    if rid is None:
        fails.append("G1:build")
        return
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        seen = []
        for i in range(5):
            dec, me, tgt = _drive(rpc, rid)
            if me is None or tgt is None:
                break
            h = _replay_one(rpc, rid, board, me, tgt, f"G1#{i}", fails)
            if h is not None:
                seen.append(h)
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        print(f"[490-gen] G1 coups observes = {seen}")
        if len(seen) < 3:
            fails.append("G1:trop-peu-de-casts")
        elif len({h for h in seen}) < 2:
            print("[490-gen] G1 : temoin degenere (coups constants) -- accord non discriminant")
            fails.append("G1:temoin-degenere")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)


def volet_g2(rpc, fails):
    """CAP Resilient + mort decidee par le NOMBRE DE COUPS."""
    from engine.entities.pathfinding.board import Board
    # `blackAbaddon` porte `Resilient` (unit_map find --trait Resilient). PV bas : ~3500 par coup
    # -> un coup ne tue pas (cap `hp-1`), deux tuent. Le nombre de coups devient le discriminant.
    rid = _build(59002, "MC1_67", "g2",
                 ["--p-units", f"{CASTER_VIS},templAncient",
                  "--a-units", "blackAbaddon,necroWarden",
                  "--hp-target", "6000", "--hp-player", "400000"])
    if rid is None:
        fails.append("G2:build")
        return
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        seen = []
        for i in range(6):
            dec, me, tgt = _drive(rpc, rid)
            if me is None or tgt is None:
                break
            h = _replay_one(rpc, rid, board, me, tgt, f"G2#{i}", fails)
            if h is not None:
                seen.append(h)
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        print(f"[490-gen] G2 coups observes = {seen}")
        if not seen:
            fails.append("G2:aucun-cast")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)


def _phase_gate(rpc, rid, board, phase, fails):
    """Confronte, cible par cible, le verdict du PORT (`ActiveAbilityOperation$$IsInvalidTarget`)
    a celui du NATIF (`abilityReason`), a la position COURANTE du caster.

    ⚠ L'ORACLE EST `abilityReason`, PAS `abilityTargets`. Mesure du 2026-08-07 : au spawn,
    `abilityTargets` rend `fromHere = []` -- ce qui est CORRECT (aucun ennemi a portee 2) mais
    ne dit RIEN par cible, donc un port muet y serait d'accord pour la mauvaise raison.
    `abilityReason` rend le code par (caster, cible), c'est-a-dire exactement ce que le port
    calcule.

    ⚠ ET LE COURT-CIRCUIT AMONT EST VERIFIE AVANT TOUTE COMPARAISON (#287-r6) : le RPC passe par
    `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`, qui a DEUX etages que
    `ActiveAbilityOperation$$IsInvalidTarget` n'a pas (disponibilite de l'ability, machine
    endommagee). Quand ils mordent, `targetReason` vaut `ValidRequest` pour TOUTE cible et le
    confronter au port compare deux fonctions natives differentes. On le DIT et on n'en conclut
    rien -- jamais un vert, jamais un rouge."""
    from engine.runner.snapshot import load_state
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import is_invalid_target
    from oracle_targeting import oracle_court_circuite, cause_du_court_circuit

    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    me = next((u for u in (dec.get("units") or [])
               if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
    if me is None:
        fails.append(f"G3/{phase}:caster")
        return
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    state = load_state(dec, ob, snap, board=board)
    ability = ABILITY_CLASSES[ABILITY]()   # INSTANCE (la cascade appelle une METHODE de l'ability)
    cid = me["id"]

    accepte_natif, accepte_port, lignes = set(), set(), []
    for u in (dec.get("units") or []):
        uid = u.get("id")
        if uid is None or uid == cid or not u.get("alive"):
            continue
        rep = rpc("abilityReason", {"runnerId": rid, "casterId": cid,
                                    "abilityType": ABILITY, "targetId": uid}, 60)
        if oracle_court_circuite(rep):
            print(f"[490-gen] G3/{phase} : ORACLE COURT-CIRCUITE EN AMONT "
                  f"({cause_du_court_circuit(rep)}) -- NON MESURE, aucune conclusion")
            fails.append(f"G3/{phase}:oracle-amont")
            return
        # `targetReason` est une STRUCTURE (`{ruleClass, hex, reasons}`), pas un scalaire : le
        # champ `hex` porte le masque `TargetingRule` rompu, sur 64 bits.
        tr = rep.get("targetReason") or {}
        if not isinstance(tr, dict) or "hex" not in tr:
            print(f"[490-gen] G3/{phase} : targetReason non mesure pour {uid} ({tr!r})")
            fails.append(f"G3/{phase}:targetReason-absent")
            return
        natif_code = int(str(tr.get("hex")), 16)
        port_code = int(is_invalid_target(state, cid, uid, ability))
        if natif_code == 0:
            accepte_natif.add(uid)
        if port_code == 0:
            accepte_port.add(uid)
        # On compare le CODE, pas seulement le verdict binaire : deux refus pour des raisons
        # DIFFERENTES seraient un accord de facade.
        if natif_code != port_code:
            fails.append(f"G3/{phase}:code({uid} natif={hex(natif_code)} port={hex(port_code)})")
        lignes.append((uid, u.get("visualId"), u.get("owner") == me.get("owner"),
                       hexgeo.distance(_pos(me), _pos(u)),
                       ",".join(tr.get("reasons") or []) or "-", hex(natif_code), hex(port_code)))

    for uid, vis, allie, d, why, nc, pc in sorted(lignes):
        print(f"[490-gen] G3/{phase} {uid:>3} {vis:<18} allie={str(allie):<5} d={d:>2} "
              f"natif={nc} ({why}) port={pc}")
    if accepte_natif != accepte_port:
        print(f"[490-gen] G3/{phase} DIVERGENCE : port\\natif={sorted(accepte_port - accepte_natif)}"
              f" natif\\port={sorted(accepte_natif - accepte_port)}")
        fails.append(f"G3/{phase}:desaccord")
    return {"me": me, "dec": dec, "natif": accepte_natif, "port": accepte_port,
            "lignes": lignes, "cid": cid}


def volet_g3(rpc, fails):
    """GATE DE CIBLE : le masque MIGRE (de `TARGETING_OPTIONS_UNPORTED` vers la classe) refuse
    toujours l'ALLIE (`TargetIsEnemy`) et le HORS-PORTEE (`RANGE_FROM_CONFIG` = 2), en accord
    avec le natif. Deux phases, parce qu'aucune geometrie unique ne garantit les deux axes :
      - AU SPAWN : tous les ennemis sont hors portee -> l'axe PORTEE est exerce ;
      - APRES DRIVE : au moins un ennemi a portee -> l'axe ACCEPTE l'est, et les allies restent
        refuses. Sans cette seconde phase, l'accord porterait sur deux ensembles VIDES."""
    from engine.entities.pathfinding.board import Board

    rid = _build(59003, "MC1_67", "g3",
                 ["--p-units", f"{CASTER_VIS},templAncient,ultraCalgar",
                  "--a-units", "ultraTitus,necroWarden,templAncient",
                  "--hp-target", "400000", "--hp-player", "400000"])
    if rid is None:
        fails.append("G3:build")
        return
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")

        # --- phase SPAWN : l'axe PORTEE -------------------------------------------------------
        r0 = _phase_gate(rpc, rid, board, "spawn", fails)
        if r0 is None:
            return
        loin = {ln[0] for ln in r0["lignes"] if not ln[2] and ln[3] > RANGE}   # ln = (uid, vis, allie, d, ...)
        if not loin:
            print("[490-gen] G3/spawn : aucun ennemi hors portee -- l'axe PORTEE n'est pas exerce")
            fails.append("G3:pas-de-hors-portee")
        if loin & r0["port"]:
            fails.append(f"G3:hors-portee-accepte-par-le-port({sorted(loin & r0['port'])})")

        # --- phase DRIVE : l'axe ACCEPTE + l'axe AMI ------------------------------------------
        dec, me, tgt = _drive(rpc, rid)
        if me is None or tgt is None:
            fails.append("G3:drive")
            return
        r1 = _phase_gate(rpc, rid, board, "drive", fails)
        if r1 is None:
            return
        allies = {ln[0] for ln in r1["lignes"] if ln[2]}
        if not allies:
            print("[490-gen] G3/drive : aucun allie vivant -- l'axe AMI n'est pas exerce")
            fails.append("G3:pas-d-allie")
        if allies & r1["port"]:
            fails.append(f"G3:allie-accepte-par-le-port({sorted(allies & r1['port'])})")
        if allies & r1["natif"]:
            fails.append(f"G3:allie-accepte-par-le-natif({sorted(allies & r1['natif'])})")
        # TEMOIN NON DEGENERE : un accord sur deux ensembles VIDES ne prouverait rien.
        if not r1["natif"]:
            print("[490-gen] G3/drive : le natif n'accepte AUCUNE cible -- accord non discriminant")
            fails.append("G3:temoin-degenere")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--volet", default="tous", choices=["G1", "G2", "G3", "tous"])
    args = ap.parse_args()
    sid = _resolve_session()

    def rpc(method, body, t=90):
        return (_rpc(sid, method, [body], timeout=t).get("result") or {})

    fails: list = []
    if args.volet in ("G1", "tous"):
        volet_g1(rpc, fails)
    if args.volet in ("G2", "tous"):
        volet_g2(rpc, fails)
    if args.volet in ("G3", "tous"):
        volet_g3(rpc, fails)
    if fails:
        print(f"[490-gen] ECHECS : {fails}")
        return 1
    print("[490-gen] PROBE OK -- les trois axes de generalisation tiennent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
