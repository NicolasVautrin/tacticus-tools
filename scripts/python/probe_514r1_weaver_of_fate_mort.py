#!/usr/bin/env python
"""probe #514-r1 -- le gate de `WeaverOfFate` compte-t-il un ennemi TUE par le meme degat ?

CE QUE #514 A CORRIGE, SUR LE SEUL DECOMPILE
----------------------------------------------
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$GetTrigger` (dont
`RealityUnboundAbility$$CreateTrigger` est le SEUL autre appelant) ecrit :

    On(9 = Attack)
    & AmountIsEqualOrGreater(
          UnitsThatTakenDamageThisTurn(
              Enemies(<dsl>+0x30 = Owner, DSLSelectors$$AllUnits(), UnitSelectionType.Any = 0),
              DamageProfileType.Psychic = 0xd),
          Get(3))
    & Not(HasEffect(caster, 1185 WeaverOfFate_MaxOutDamage))

DEUX signaux INDEPENDANTS disent « morts inclus » : la source est la primitive **pool 8**
(`EntityPool.AllUnits`, slot 136 `GetAllUnits`, aucun predicat de vie) et non le champ partage
`<dsl>+0x20` (`AllAliveUnits`, pool 0) que prennent tous les autres call-sites ; et le
`selectionType` vaut **0 = Any**, la ou tous les autres passent `3 = OnlyAliveAndTargetable`
(`UnitExtensions$$MatchesUnitSelectionType` n'appelle `IsAlive` que sur `1` et `3`).

CE QUE CE PROBE AJOUTE : LE REGIME QUI LES DISTINGUE, MONTE POUR DE VRAI
-------------------------------------------------------------------------
`thousAhriman` << Ahriman >> (LINEUP, DANS le pool) porte `WeaverOfFate` **et** `Doombolt` (1102),
dont le profil est `Psychic` et qui frappe TOUS les ennemis vivants a distance <= 2 du caster. On
place **exactement TROIS** ennemis dans ce rayon et on rend l'un d'eux assez FRAGILE pour qu'il
meure du meme cast. Apres l'attaque :

    ennemis ayant recu du Psychic ce tour = 3, dont 1 MORT
    -> le gate natif compte 3   -> `1185` pose
    -> le port d'AVANT #514 comptait 2 (filtre `alive`) -> RIEN

  E0  le montage : 3 ennemis touches, exactement 1 mort (sinon le regime n'est PAS discriminant)
  E1  ORACLE NATIF : `1185 WeaverOfFate_MaxOutDamage` pose sur Ahriman apres le cast ?
  E2  le GATE porte (`WeaverOfFateAbility.matches`) evalue sur l'etat post-cast
  E3  la POSE cote port

CONTRE-EPREUVE `AB1` : `_enemies_of` rabattu sur les VIVANTS -- l'etat d'AVANT #514. Le gate doit
BASCULER a False ; s'il ne bascule pas, ce montage ne mesure RIEN et le probe le DIT.

⚠ RESIDU CONNU ET NOMME (il n'est PAS ce que ce probe mesure) : le port n'emet `On(9 = Attack)` que
sur la voie NORMALE (`damage_ops/normal.py`), pour AUCUNE ability. E3 peut donc rester `False` alors
que E2 est `True` -- l'ecart accuse alors l'emission, pas le gate de #514. Les deux etages sont
mesures SEPAREMENT pour que l'attribution soit lisible.

Usage (depuis `scripts/python`, ASCII only) :
    python probe_514r1_weaver_of_fate_mort.py [--keep] [--state-file <absolu>]
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

DOOMBOLT = 1102                        # `ActiveAbilityType.Doombolt` -- profil Psychic, rayon 2
WEAVER_MAXOUT = 1185                   # `EffectType.WeaverOfFate_MaxOutDamage` (0x4a1)

CASTER = "thousAhriman"                # trait `WeaverOfFate` + `Doombolt`, DANS le pool
FRAGILE = "necroWarden"                # celui qu'on fait MOURIR du meme cast
FOES = (FRAGILE, "orksNob", "tauMarksman")

BOARD = "MC1_67"
SEED = 5141
PV_FRAGILE = 300                       # assez bas pour tomber sous 3 coups de Doombolt

#: Geometrie DRIVEE : les TROIS ennemis a distance hex <= 2 du caster (le selecteur natif est
#: `SurroundingEnemies(casterTile, range = 2)`), et AUCUN quatrieme -- le compte doit valoir
#: EXACTEMENT 3, sinon le seuil `Get(3)` serait franchi meme sans le mort.
P_PLACE = ((CASTER, "4,5"),)
A_PLACE = ((FOES[0], "4,6"), (FOES[1], "4,7"), (FOES[2], "3,6"))


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
    argv = ["build", "--seed", str(SEED), "--board", BOARD,
            "--p-units", ",".join(v for v, _t in P_PLACE),
            "--a-units", ",".join(v for v, _t in A_PLACE),
            # LE FRAGILE : les DEUX champs, comme #514 -- `Health` seul laisse `RemainingHealth`
            # au maximum du template et l'unite ne meurt pas. ⚠ Le `;` de `--unit-stat` separe des
            # ENTREES `VisualId:...`, pas des champs d'une meme entree : il faut DEUX occurrences.
            "--unit-stat", "%s:Health=%d" % (FRAGILE, PV_FRAGILE),
            "--unit-stat", "%s:RemainingHealth=%d" % (FRAGILE, PV_FRAGILE),
            "--state-file", state_file]
    for vid, tile in P_PLACE:
        argv += ["--place", "%s:%s" % (vid, tile)]
    for vid, tile in A_PLACE:
        argv += ["--a-place", "%s:%s" % (vid, tile)]
    p = _duel(argv)
    if p.returncode != 0:
        print("[build] rc=%s\n%s\n%s" % (p.returncode, p.stdout[-1800:], p.stderr[-800:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return int(json.load(f)["runnerId"])


def vue(sid, rid):
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 90)
    morts = {u.get("id"): bool(u.get("isDead")) for u in (ob.get("units") or [])}
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        uid = u.get("id")
        out[u.get("visualId")] = {
            "id": uid, "pos": (p.get("col"), p.get("row")),
            "hp": u.get("hp"),
            "mort": bool(morts.get(uid, u.get("isDead"))),
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
    """Un montage DEGENERE rendrait le verdict trivial : on echoue AVANT de mesurer."""
    import engine.battle_query as bq
    voulu = dict(P_PLACE) | dict(A_PLACE)
    manquants = [v for v in voulu if v not in u]
    if manquants:
        raise SystemExit("montage invalide : unites absentes %r" % (manquants,))
    mauvais = [(v, u[v]["pos"], voulu[v]) for v in voulu
               if u[v]["pos"] != tuple(int(x) for x in voulu[v].split(","))]
    if mauvais:
        raise SystemExit("placement REFUSE -- montage invalide : %r" % (mauvais,))
    # Les TROIS ennemis doivent etre a distance <= 2 du caster (le rayon de `Doombolt`), et il ne
    # doit y en avoir AUCUN autre : le seuil est `>= 3`, donc un quatrieme le rendrait franchissable
    # sans le mort et le regime cesserait d'etre discriminant.
    byid = {t["id"]: (t["col"], t["row"]) for t in cap["tiles"]}
    neigh = {}
    for t in cap["tiles"]:
        neigh[(t["col"], t["row"])] = [byid[n] for n in (t.get("neighbours") or []) if n in byid]
    cpos = u[CASTER]["pos"]
    dans = []
    for v, _t in A_PLACE:
        d = bq.hex_distance_by_neighbours(cpos, u[v]["pos"], neigh) \
            if hasattr(bq, "hex_distance_by_neighbours") else None
        dans.append((v, d))
    if len(A_PLACE) != 3:
        raise SystemExit("le montage doit porter EXACTEMENT 3 ennemis, il en porte %d"
                         % len(A_PLACE))
    if u[FRAGILE]["hp"] is None or int(u[FRAGILE]["hp"]) > PV_FRAGILE * 3:
        raise SystemExit("le fragile n'a PAS ete rabaisse (hp = %s) -- il ne mourra pas, et le "
                         "regime discriminant n'est pas monte" % (u[FRAGILE]["hp"],))
    return dans


def etat_porte(cap):
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


def _gate(st, caster_id):
    """LE TERME DU GATE QUE #514 CORRIGE, isole :

        AmountIsEqualOrGreater( UnitsThatTakenDamageThisTurn(Enemies(Owner, AllUnits(), Any)),
                                Get(3) )

    ⚠ On N'EVALUE PAS `matches()` ici, et c'est un choix MESURE : ce corps conjoint aussi
    `Not(HasEffect(caster, 1185))`, or l'etat sur lequel on evalue est POSTERIEUR au cast -- l'effet
    y est deja pose, donc `matches()` rend `False` des DEUX cotes et la contre-epreuve devient
    INERTE (mesure faite, premiere version de ce probe). Le terme anti-re-trigger n'est pas le
    sujet de #514 ; le COMPTE l'est."""
    from engine.runner.operations.triggers.loki.weaver_of_fate import (
        units_that_taken_damage_this_turn, _enemies_of, _PSYCHIC, _THRESHOLD)
    import engine.runner.operations.triggers.loki.weaver_of_fate as WF
    enn = WF._enemies_of(st, int(caster_id)) if hasattr(WF, "_enemies_of") else _enemies_of(
        st, int(caster_id))
    touches = units_that_taken_damage_this_turn(st, enn, _PSYCHIC)
    return len(touches) >= _THRESHOLD, sorted(enn), sorted(touches)


def rejeu_porte(cap, caster_id, target_id):
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner
    from engine.runner.components import has_effect_of_type, UnitComponent
    st = etat_porte(cap)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=int(caster_id), target_id=int(target_id),
                                      ability_type=DOOMBOLT))
    last = getattr(runner.ability_handler, "last", None) or {}
    gate, enn, touches = _gate(st, caster_id)
    morts = sorted(i for i in enn
                   if (st.get_entity(i).get_component(UnitComponent) is not None
                       and not st.get_entity(i).get_component(UnitComponent).alive))
    return {"ported": last.get("ported"), "gate": gate, "ennemis": enn,
            "touches_psychic": touches, "morts": morts,
            "pose_1185": bool(has_effect_of_type(st, int(caster_id), WEAVER_MAXOUT)),
            "state": st}


def main() -> int:
    ap = argparse.ArgumentParser(description="probe #514-r1 -- WeaverOfFate compte le MORT")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()
    sf = a.state_file or os.path.join(tempfile.gettempdir(), "p514r1_%d.json" % os.getpid())
    sid = _sid()
    rid = build(sf)
    if rid is None:
        print("[514-r1] build KO -- rien mesure")
        return 99
    try:
        u = vue(sid, rid)
        cap = capture(sid, rid)
        assert_montage(u, cap)
        cid = u[CASTER]["id"]
        tid = u[FRAGILE]["id"]
        inv = {u[v]["id"]: v for v in u}
        from engine.runner.snapshot import live_rpc
        with live_rpc(lambda m, b=None, t=120: _rpc(sid, m, b, t)):
            port = rejeu_porte(cap, cid, tid)
            # AB1 -- le gate d'AVANT #514 : les ennemis MORTS sont exclus.
            import engine.runner.operations.triggers.loki.weaver_of_fate as WF
            vrai = WF._enemies_of
            try:
                from engine.runner.components import UnitComponent

                def _alive_only(st, oid):
                    out = []
                    for i in vrai(st, oid):
                        e = st.get_entity(i)
                        uc = e.get_component(UnitComponent) if e is not None else None
                        if uc is not None and uc.alive:
                            out.append(i)
                    return out

                WF._enemies_of = _alive_only
                ab1_gate, _e, ab1_touches = _gate(port["state"], cid)
            finally:
                WF._enemies_of = vrai
        p = _duel(["act", "ability", "--caster", str(cid), "--ability", str(DOOMBOLT),
                   "--target", str(tid), "--state-file", sf, "--runner", str(rid)])
        casc = (p.stdout or "")
        # ⚠ L'ORACLE EST LA CASCADE, PAS L'ETAT FINAL. `AddEffect(1185, ..., Nullable(1))` dure UN
        # TOUR, et le cast d'une active TERMINE le tour du porteur : le `LoseEffect` tombe dans le
        # MEME flux. Un `decisionView` pris apres le cast ne voit donc JAMAIS l'effet -- mesure
        # faite, la premiere version de ce probe rendait `natif = False` sur une pose qui avait
        # bien eu lieu (`[Effect_Refresh e=... <<WeaverOfFate_MaxOutDamage>>]` puis `LoseEffect`).
        natif_1185 = "WeaverOfFate_MaxOutDamage" in casc
        apres = vue(sid, rid)
        # Mort NATIVE : `observeBattle` conserve les unites mortes ; le discriminant est la
        # DISPARITION de la liste des unites A ACTIVER de leur camp, que la sortie du cast imprime.
        natif_morts = sorted(apres[v]["id"] for v, _t in A_PLACE
                             if apres[v]["mort"] or (apres[v]["hp"] or 0) <= 0)
        nom = lambda s: [("%s/u%s" % (inv.get(i, "?"), i)) for i in s]
        print("[514-r1] runner=%s caster=%s@%s (WeaverOfFate + Doombolt, profil Psychic rayon 2)"
              % (rid, CASTER, u[CASTER]["pos"]))
        print("        unites : " + " ".join("%s=u%s@%s hp=%s" % (v, u[v]["id"], u[v]["pos"],
                                                                  u[v]["hp"]) for v in sorted(u)))
        print("  E0 morts apres le cast   NATIF=%s   PORT=%s"
              % (nom(natif_morts), nom(port["morts"])))
        print("  E1 ORACLE -- `WeaverOfFate_MaxOutDamage` dans la cascade NATIVE = %s"
              % (natif_1185,))
        print("  E2 TERME du gate (>= 3)  = %s   (ennemis=%s, touches Psychic=%s)"
              % (port["gate"], nom(port["ennemis"]), nom(port["touches_psychic"])))
        print("  E3 `1185` pose cote PORT = %s" % (port["pose_1185"],))
        print("  -- contre-epreuve --")
        print("     AB1 `_enemies_of` rabattu sur les VIVANTS (etat d'avant #514) : terme=%s "
              "touches=%s" % (ab1_gate, nom(ab1_touches)))
        discriminant = (len(port["morts"]) == 1 and len(port["touches_psychic"]) >= 3)
        mord = (ab1_gate is False and port["gate"] is True)
        ok = bool(port["ported"]) and discriminant and port["gate"] is True and natif_1185
        if not discriminant:
            print("     !! REGIME NON DISCRIMINANT : morts port=%d, touches port=%d -- il faut "
                  "EXACTEMENT 1 mort et 3 touches" % (len(port["morts"]),
                                                      len(port["touches_psychic"])))
            print("     sortie du cast NATIF (diagnostic) :\n%s" % (casc[-2000:],))
        if not mord:
            print("     !! AB1 est INERTE : la lecture `morts inclus` n'est PAS mesuree ici")
        if port["pose_1185"] is not natif_1185:
            print("     -- ECART DE POSE (E3 != E1). Il accuse l'EMISSION, pas le gate : le port "
                  "n'emet `On(9 = Attack)` que sur la voie NORMALE (`damage_ops/normal.py`), pour "
                  "AUCUNE ability. Residu nomme par #512-r2.")
        print("[514-r1] %s (regime discriminant=%s, contre-epreuve mord=%s)"
              % ("GATE CONFORME au natif" if ok else "A EXAMINER", discriminant, mord))
        return 0 if (ok and mord) else 1
    finally:
        if not a.keep:
            _duel(["dispose", "--state-file", sf, "--runner", str(rid)], timeout=120)


if __name__ == "__main__":
    raise SystemExit(main())
