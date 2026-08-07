#!/usr/bin/env python
"""probe #512-r1 -- GENERALISATION : `SuppressiveFire` suppresse-t-il CHAQUE cible d'une attaque
d'ABILITY, y compris celle qui est ADJACENTE au caster ?

POURQUOI CE PROBE EN PLUS DE `probe_512` -- CE QU'IL AJOUTE, ET CE QU'IL EXCLUT
--------------------------------------------------------------------------------
`probe_512` mesure l'ecart de DEGAT sur `emperNoiseMarine`, dont la chaine
`SuppressiveFire -> Pinned -> TerrifyingCrescendo` transforme la pose en montant. Un vert y prouve
que la chaine COMPLETE est juste, mais il ne separe pas ses maillons, et il ne vaut que pour UN
porteur qui a la particularite rare de porter les deux (trait + passif).

Ce probe-ci isole le maillon d'ENTREE, sur un AUTRE porteur, et prend la POSE elle-meme pour
observable :

  * porteur `blackObliterator` << Volk >> (LINEUP, DANS le pool) -- traits `SuppressiveFire` ET
    `LetTheGalaxyBurn`, c.-a-d. **les deux seuls consommateurs portes de `On(PreAttack = 5)`** ;
    il n'a PAS `TerrifyingCrescendo`, donc la pose ne se paie pas en degat : elle se LIT.
  * ability `1036 FrenziedFiring` -- `attackRangeType = Ranged` (gameconfig), famille de factory
    ATTACK, `ability_type` threade sur ses DEUX feuilles, et MULTI-CIBLE (volet AoE autour de la
    cible d'origine). Le cast produit donc plusieurs `StartAttack`, donc plusieurs `On(5)`.

DEUX LECTURES SONT MESUREES, ET CHACUNE A SA CONTRE-EPREUVE
------------------------------------------------------------
  L1 « `AttackRangeType.Ranged` (2) ne lit AUCUNE position » -- la cible d'ORIGINE est placee
     ADJACENTE au caster. Le mirror d'avant `#512-r1` (`_is_ranged_position` seul, la branche
     `Normal(3)`) la declarerait MELEE et ne la suppresserait pas.
     Contre-epreuve `AB1` : le gate rabattu sur `_is_ranged_position`. Si `AB1` rend le MEME
     ensemble que `REF`, ce montage ne mesure PAS L1 (la cible n'est pas vraiment au contact) et son
     vert ne prouve rien -- le probe le DIT.
  L2 « `On(5)` part PAR CIBLE » -- le volet AoE ajoute des cibles ; toutes doivent etre suppressees.
     Contre-epreuve `AB2` : l'ancien vecteur `On(NormalAttack = 38)`. Un cast d'ability n'en emet
     aucun -> ensemble VIDE. C'est l'etat d'avant le fix.

Le NATIF est l'oracle : l'ensemble attendu n'est jamais ecrit en dur, il est LU dans la cascade.

Usage (depuis `scripts/python`, ASCII only) :
    python probe_512r1_suppressive_par_cible.py
    python probe_512r1_suppressive_par_cible.py --keep      # ne dispose PAS le runner
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

HOST = "http://127.0.0.1:8765"
PYDIR = os.path.dirname(os.path.abspath(__file__))

FRENZIED_FIRING = 1036                 # `ActiveAbilityType.FrenziedFiring`
PINNED = 1065                          # `EffectType.Pinned` (0x429) -- UI << Suppressed >>

CASTER = "blackObliterator"            # traits SuppressiveFire + LetTheGalaxyBurn, DANS le pool
FOES = ("necroWarden", "orksNob", "tauMarksman")

BOARD = "MC1_67"
SEED = 5121

#: Geometrie DRIVEE (jamais subie) : le caster en (4,5), la cible d'ORIGINE sur la tuile VOISINE
#: (4,6) -- c'est elle qui porte la lecture L1 -- et deux ennemis ADJACENTS a elle, qui forment le
#: volet AoE. Les positions sont RE-VERIFIEES a l'execution contre `decisionView`.
P_PLACE = ((CASTER, "4,5"),)
A_PLACE = ((FOES[0], "4,6"), (FOES[1], "4,7"), (FOES[2], "3,6"))
ORIGINE = FOES[0]


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


def build(state_file: str):
    argv = ["build", "--seed", str(SEED), "--board", BOARD, "--hp-target", "400000",
            "--p-units", ",".join(v for v, _t in P_PLACE),
            "--a-units", ",".join(v for v, _t in A_PLACE),
            "--state-file", state_file]
    for vid, tile in P_PLACE:
        argv += ["--place", "%s:%s" % (vid, tile)]
    for vid, tile in A_PLACE:
        argv += ["--a-place", "%s:%s" % (vid, tile)]
    p = _duel(argv)
    if p.returncode != 0:
        print("[build] rc=%s\n%s\n%s" % (p.returncode, p.stdout[-1500:], p.stderr[-800:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return int(json.load(f)["runnerId"])


def vue(sid, rid):
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = {
            "id": u.get("id"), "pos": (p.get("col"), p.get("row")),
            "alive": not u.get("isDead"),
            "effets": sorted(e.get("effectType") for e in (u.get("effects") or [])
                             if isinstance(e, dict) and e.get("effectType") is not None)}
    return out


def capture(sid, rid):
    return {
        "dv": _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150),
        "ob": _rpc(sid, "observeBattle", {"runnerId": rid}, 90),
        "snap": _rpc(sid, "combatSnapshot", {"runnerId": rid}, 120),
        "tm": _rpc(sid, "tileMeta", {"runnerId": rid}, 120),
        "tiles": _rpc(sid, "boardGraph", {"runnerId": rid}, 90)["tiles"],
        "rng": _rpc(sid, "dumpRng", {"runnerId": rid}, 60),
    }


def assert_montage(u, cap):
    """Un montage DEGENERE rendrait l'accord trivial : on echoue AVANT de mesurer."""
    import engine.battle_query as bq
    voulu = dict(P_PLACE) | dict(A_PLACE)
    manquants = [v for v in voulu if v not in u]
    if manquants:
        raise SystemExit("montage invalide : unites absentes %r" % (manquants,))
    mauvais = [(v, u[v]["pos"], voulu[v]) for v in voulu
               if u[v]["pos"] != tuple(int(x) for x in voulu[v].split(","))]
    if mauvais:
        raise SystemExit("placement REFUSE -- montage invalide : %r" % (mauvais,))
    # L1 n'est mesuree QUE si la cible d'origine est REELLEMENT au contact -- adjacence NATIVE,
    # re-derivee du board capture, jamais la distance hex a l'oeil.
    neigh, elev = {}, {}
    byid = {t["id"]: (t["col"], t["row"]) for t in cap["tiles"]}
    for t in cap["tiles"]:
        elev[(t["col"], t["row"])] = t.get("elevation", 0)
        neigh[(t["col"], t["row"])] = [byid[n] for n in (t.get("neighbours") or []) if n in byid]
    if not bq.are_entities_adjacent(u[CASTER]["pos"], u[ORIGINE]["pos"], elev, neigh):
        raise SystemExit("la cible d'ORIGINE n'est PAS adjacente au caster -- la lecture "
                         "`Ranged(2) ne lit aucune position` ne serait PAS mesuree")
    # L2 n'est mesuree que si le volet AoE a de quoi mordre : au moins un AUTRE ennemi adjacent a
    # l'origine (et vivant).
    autres = [v for v, _t in A_PLACE if v != ORIGINE
              and bq.are_entities_adjacent(u[v]["pos"], u[ORIGINE]["pos"], elev, neigh)]
    if not autres:
        raise SystemExit("aucun ennemi adjacent a l'ORIGINE -- le volet AoE serait vide, la lecture "
                         "`On(5) par cible` ne serait PAS mesuree")
    return autres


def etat_porte(cap):
    """`State` charge depuis la capture, PRNG cale (a appeler sous `snapshot.live_rpc`)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    board = Board(cap["tiles"], adjacency="native_sym")
    st = load_state(cap["dv"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"])
    d = cap["rng"]
    if not (isinstance(d, dict) and d.get("mt")):
        raise SystemExit("dumpRng VIDE -- MT non calable")
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(d["mt"]), d["mti"]
    st.rng = rng
    return st


def _pinned_du_port(st, ids):
    from engine.runner.components import has_effect_of_type
    return sorted(i for i in ids if has_effect_of_type(st, int(i), PINNED))


def rejeu_porte(cap, caster_id, target_id, ids):
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner
    st = etat_porte(cap)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=int(caster_id), target_id=int(target_id),
                                      ability_type=FRENZIED_FIRING))
    last = getattr(runner.ability_handler, "last", None) or {}
    return {"ported": last.get("ported"), "pinned": _pinned_du_port(st, ids)}


def contre_epreuves(cap, caster_id, target_id, ids):
    """Chaque variante ne change QU'UNE lecture, sur la MEME capture."""
    import engine.runner.operations.triggers.base as TB
    import engine.runner.operations.triggers.loki.suppressive_fire as SF
    from engine.dsl.event_trigger_type import EventTriggerType
    out = {}

    def _joue():
        return rejeu_porte(cap, caster_id, target_id, ids)["pinned"]

    out["REF"] = _joue()
    # AB1 -- le gate rabattu sur la seule branche `Normal(3)` (l'etat d'AVANT `#512-r1`).
    prev = TB._is_ranged_attack
    try:
        SF._is_ranged_attack = lambda st, at, a, t: TB._is_ranged_position(st, a, t)
        out["AB1 gate positionnel (branche Normal(3) seule)"] = _joue()
    finally:
        SF._is_ranged_attack = prev
    # AB2 -- l'ANCIEN vecteur : `On(NormalAttack = 38)`, qu'un cast d'ability n'emet jamais.
    prev_ev = SF.SuppressiveFireAddEffectAbility.event_id
    try:
        SF.SuppressiveFireAddEffectAbility.event_id = int(EventTriggerType.NormalAttack)
        out["AB2 ancien vecteur On(NormalAttack = 38)"] = _joue()
    finally:
        SF.SuppressiveFireAddEffectAbility.event_id = prev_ev
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="probe #512-r1 -- SuppressiveFire par cible")
    ap.add_argument("--keep", action="store_true", help="ne dispose PAS le runner")
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()
    sf = a.state_file or os.path.join(tempfile.gettempdir(), "p512r1_%d.json" % os.getpid())
    sid = _sid()
    rid = build(sf)
    if rid is None:
        print("[512-r1] build KO -- rien mesure")
        return 99
    try:
        u = vue(sid, rid)
        cap = capture(sid, rid)
        autres = assert_montage(u, cap)
        ids = [u[v]["id"] for v in u]
        cid, tid = u[CASTER]["id"], u[ORIGINE]["id"]
        inv = {u[v]["id"]: v for v in u}
        from engine.runner.snapshot import live_rpc
        with live_rpc(lambda m, b=None, t=120: _rpc(sid, m, b, t)):
            port = rejeu_porte(cap, cid, tid, ids)
            ab = contre_epreuves(cap, cid, tid, ids)
        p = _duel(["act", "ability", "--caster", str(cid), "--ability", str(FRENZIED_FIRING),
                   "--target", str(tid), "--state-file", sf, "--runner", str(rid)])
        apres = vue(sid, rid)
        natif = sorted(apres[v]["id"] for v in apres if PINNED in (apres[v]["effets"] or []))
        nom = lambda s: [("%s/u%s" % (inv.get(i, "?"), i)) for i in s]
        print("[512-r1] runner=%s caster=%s@%s origine=%s@%s (ADJACENTE) AoE=%s"
              % (rid, CASTER, u[CASTER]["pos"], ORIGINE, u[ORIGINE]["pos"], autres))
        print("        unites : " + " ".join("%s=u%s@%s" % (v, u[v]["id"], u[v]["pos"])
                                             for v in sorted(u)))
        print("  E0 ported = %s" % (port["ported"],))
        print("  E1 PINNED (1065)   PORT =%s" % (nom(port["pinned"]),))
        print("                     NATIF=%s" % (nom(natif),))
        print("  -- contre-epreuves (hors-ligne, meme capture) --")
        for k, v in ab.items():
            marque = "" if k == "REF" else ("  <- INERTE (ne mesure rien)"
                                            if v == ab["REF"] else "")
            print("     %-46s pinned=%s%s" % (k, nom(v), marque))
        # VERDICT. Le natif est l'oracle ; on exige en plus que le montage ne soit pas DEGENERE
        # (un ensemble vide des deux cotes serait un accord qui ne prouve rien) et que les DEUX
        # contre-epreuves MORDENT -- sinon les lectures L1/L2 ne sont pas mesurees ici.
        ok = bool(port["ported"]) and port["pinned"] == natif and len(natif) >= 2
        mordent = {k: (v != ab["REF"]) for k, v in ab.items() if k != "REF"}
        if not ok:
            print("     sortie du cast NATIF (diagnostic) :\n%s" % ((p.stdout or "")[-2500:],))
        for k, m in mordent.items():
            if not m:
                print("     !! %s est INERTE : la lecture qu'elle garde n'est PAS mesuree ici" % k)
        print("[512-r1] %s (contre-epreuves qui mordent : %d/%d)"
              % ("ACCORD port/natif" if ok else "DESACCORD",
                 sum(1 for m in mordent.values() if m), len(mordent)))
        return 0 if (ok and all(mordent.values())) else 1
    finally:
        if not a.keep:
            _duel(["dispose", "--state-file", sf, "--runner", str(rid)], timeout=120)


if __name__ == "__main__":
    raise SystemExit(main())
