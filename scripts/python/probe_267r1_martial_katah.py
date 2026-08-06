"""probe #267-r1 (montage END-TO-END) -- un gate de trait de la face PREDICTION suit-il le CANAL
de mesure, ou le kit gameconfig ? Mesure sur `MartialKatah` : **+100 % de degat**.

L'ARTEFACT. `IdunBattle.Entities.Effects.Loki.MartialKatahDamageEffect$$
CreateEffectDamageBonusForAttack` = `ForPercentIncrease(HasTrait(target, Summon = 2),
Direct(GetNumberConstant(cfg 0xf) = martialKatahExtraDmgPct = 100))`. Le `HasTrait` y est
`IdunBattle.Entities.UnitExtensions$$HasTrait` sur l'ENTITE : il passe par
`IdunBattle.Entities.Triggers.HasTraitTrigger$$Evaluate`, qui resout l'entite du selecteur puis
appelle cette fonction, laquelle delegue a
`IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`. Aucun gameconfig sur ce chemin.

POURQUOI CE GATE-LA. Le balayage exhaustif `probe_267r1_gate_sweep.py` (123 classes d'effet x 105
valeurs d'enum) rend SIX traits qui font basculer un consommateur des 12 sites : `BigTarget` /
`Vehicle` (BeastSlayer +20 %), `Psyker` (CondemnorStake +30 flat), `Summon` (MartialKatah +100 %),
`Imperial` / `Xenos` (DespoiledGround +15 %). `Summon` est le plus MORDANT des six.

LE MONTAGE. On ne cherche pas un ecart naturel (mesure : sur le pool spawnable il n'y en a pas sur
ce trait -- un summon invoque en bataille porte bien `Summon`). On fait ce que fait deja la
contre-epreuve de #267 : **on SUBSTITUE le canal**. MEME etat, MEME pas, MEME tuile, seule la ligne
`traits` de la CIBLE change :

    canal A : la mesure SANS `Summon` (id 2 retire)
    canal B : la mesure AVEC `Summon`

Le port cable doit rendre B = 2 x A. Puis on NEUTRALISE le cablage (`_entity_traits` re-branche sur
`gameconfig.unit(visualId).traits`, l'AVANT de #267-r1) : les deux canaux doivent alors rendre la
MEME valeur -- le gate ne voit plus le canal. C'est le ROUGE.

Enfin, sur l'etat NON MUTE, on confronte l'ORACLE NATIF (`aiPlaybookPredict`) : le cablage ne doit
RIEN avoir change la ou kit et mesure concordent.

ASCII only (console cp1252). Usage :
    python probe_267r1_martial_katah.py [--seed 4242] [--board MC1_67] [--keep]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hexgeo                                                                  # noqa: E402
import rl_collect_batch as R                                                   # noqa: E402
import gameconfig as GC                                                        # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                        # noqa: E402
from engine.playbook import scene as SC                                        # noqa: E402
from engine.playbook.scene import Scene                                        # noqa: E402

KATAH = "custoTrajann"          # porte le trait MartialKatah
CIBLE = "orksWarboss"           # cible ennemie quelconque (aucun `Summon` au kit ni au BC)
SUMMON_ID = int(UnitTrait.Summon)        # 2


def _mk_rpc(sid):
    def rpc(method, body=None, timeout=120):
        r = R._rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r.get("result") if isinstance(r, dict) and "result" in r else r
    return rpc


def _build(seed: str, board: str) -> tuple[int, str]:
    state = os.path.join(tempfile.gettempdir(), "rs_267r1_katah.json")
    if os.path.exists(state):
        os.unlink(state)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
            "--state-file", state,
            "--p-units", "%s,ultraApothecary" % KATAH,
            "--a-units", "%s,necroWarden" % CIBLE]
    p = subprocess.run(argv, cwd=os.path.dirname(os.path.abspath(__file__)),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.exists(state):
        print("BUILD KO :\n%s" % ((p.stderr or p.stdout or "")[-1200:]))
        raise SystemExit(2)
    return int(json.loads(open(state, encoding="utf-8").read())["runnerId"]), state


def _scene(rpc, rid, force=None):
    def _r(m, b=None, t=120):
        return force if (m == "combatSnapshot" and force is not None) else rpc(m, b, t)
    pred = SC.build_predictor(_r, rid)
    assert pred is not None, "build_predictor KO"
    vue = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 150)
    sctx = SC.step_context(pred, vue)
    obs = rpc("observeBattle", {"runnerId": rid}, 60) or {}
    hp = {u.get("squadId"): (u.get("hpMax") or 0) for u in (obs.get("units") or [])}
    hp.update(pred.get("hpmax_eff_by_id") or {})
    sctx["hpmax_by_id"] = hp
    return Scene.from_predictor_sctx(pred, sctx, None)


def canal(snap, eid, avec_summon: bool) -> dict:
    """Le MEME snapshot, la ligne `traits` de `eid` forcee AVEC / SANS `UnitTrait.Summon`.
    C'est la substitution de CANAL -- exactement le levier de la contre-epreuve `_efface` de #267,
    applique a une valeur de mesure differente au lieu de `null`."""
    out = []
    for u in (snap.get("units") or []):
        if u.get("entityId") != eid or not isinstance(u.get("traits"), list):
            out.append(u)
            continue
        t = [x for x in u["traits"] if int(x) != SUMMON_ID]
        if avec_summon:
            t = t + [SUMMON_ID]
        out.append({**u, "traits": t})
    return {**snap, "units": out}


def _pos_by_id(dv) -> dict:
    return {u.get("id"): ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
            for u in ((dv or {}).get("units") or [])}


def _rapprocher(rpc, rid, a_id, b_id, tours=8) -> tuple:
    """Amene `a_id` et `b_id` au CONTACT en pilotant les DEUX camps (`applyAction` ne verifie pas la
    propriete du casterId, cf. runner.md §4) : a chaque tour, chaque unite va sur la tuile de son
    movable set qui MINIMISE la distance hex a l'autre, puis `endturn`. DRIVE de positions, pas une
    geometrie subie."""
    for _ in range(tours):
        pos = _pos_by_id(rpc("decisionView", {"runnerId": rid}, 150))
        pa, pb = pos.get(a_id), pos.get(b_id)
        if pa and pb and pa[0] is not None and pb[0] is not None and hexgeo.distance(pa, pb) <= 1:
            return pa, pb
        mv = rpc("aiMovableTiles", {"runnerId": rid}, 120) or {}
        for u in (mv.get("units") or []):
            uid = u.get("unitId")
            if uid not in (a_id, b_id):
                continue
            autre = pos.get(b_id if uid == a_id else a_id)
            tiles = [(t.get("col"), t.get("row")) for t in (u.get("tiles") or [])]
            tiles = [t for t in tiles if t[0] is not None]
            if not tiles or not autre or autre[0] is None:
                continue
            best = min(tiles, key=lambda t: hexgeo.distance(t, autre))
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": int(uid),
                "to": {"col": best[0], "row": best[1]}}}, 120)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
    pos = _pos_by_id(rpc("decisionView", {"runnerId": rid}, 150))
    return pos.get(a_id), pos.get(b_id)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="4242")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    rpc = _mk_rpc(R._resolve_session())
    rid, state = _build(a.seed, a.board)
    print("runner %d (seed %s, board %s)" % (rid, a.seed, a.board))
    try:
        return _run(rpc, rid)
    finally:
        if not a.keep:
            rpc("disposeRunner", {"runnerId": rid}, 30)
            if os.path.exists(state):
                os.unlink(state)
            print("[dispose] runner %d" % rid)


def _run(rpc, rid) -> int:
    from engine.playbook.prediction.normal_attack import make_normal_attack_predictions
    from engine.playbook.prediction import _shared
    bad = 0
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 200) or {}
    by_vis = {u.get("visualId"): u for u in (dec.get("units") or [])}
    if KATAH not in by_vis or CIBLE not in by_vis:
        print("montage KO : %r absents" % sorted(by_vis))
        return 1
    aid, tid = int(by_vis[KATAH]["id"]), int(by_vis[CIBLE]["id"])
    pa, pb = _rapprocher(rpc, rid, aid, tid)
    print("[approche] %s en %r, %s en %r (dist hex %r)"
          % (KATAH, pa, CIBLE, pb,
             hexgeo.distance(pa, pb) if (pa and pb and pa[0] is not None) else None))

    snap = rpc("combatSnapshot", {"runnerId": rid}, 150)
    ligne = next((u for u in (snap.get("units") or []) if u.get("entityId") == tid), None)
    if ligne is None or not isinstance(ligne.get("traits"), list):
        print("montage KO : la cible u%d n'a pas de ligne `traits` MESUREE" % tid)
        return 1
    kit = frozenset((GC.unit(CIBLE) or {}).get("traits") or ())
    print("")
    print("== ETAGE 0 -- l'attaquant porte-t-il bien le canal MartialKatah ? ==")
    sc_ref = _scene(rpc, rid)
    effs = [getattr(e, "name", None) for e in (sc_ref.effects(aid) or [])]
    print("  effets ACTIFS de u%d (%s) : %r" % (aid, KATAH, effs))
    if not any("MartialKatah" in (n or "") for n in effs):
        print("  montage KO : l'effet MartialKatah_DmgBonus n'est pas actif sur l'attaquant")
        return 1
    print("  cible u%d (%s) : `Summon` au kit = %s" % (tid, CIBLE, "Summon" in kit))

    def _pred(scene):
        ev = make_normal_attack_predictions(scene, aid, tid, pa)
        if ev is None:
            return None
        r = ev.prediction.raw_health_damage
        return (int(r.min), int(r.max))

    sc_sans = _scene(rpc, rid, force=canal(snap, tid, avec_summon=False))
    sc_avec = _scene(rpc, rid, force=canal(snap, tid, avec_summon=True))
    sans, avec = _pred(sc_sans), _pred(sc_avec)
    print("")
    print("== ETAGE 1 -- CABLE : le gate suit-il le canal ? (MEME etat, MEME tuile %r) ==" % (pa,))
    print("  canal SANS `Summon` : %r" % (sans,))
    print("  canal AVEC `Summon` : %r" % (avec,))
    if not sans or not avec:
        print("  prediction indisponible -> montage inexploitable")
        return 1
    if avec == sans:
        print("  ACCORD TRIVIAL : le gate ne bouge pas -- MartialKatah ne mord pas ici. RIEN de prouve.")
        bad += 1
    else:
        print("  ECART : x%.4f (min) x%.4f (max)  [attendu ~x2 : +100 %% MartialKatah]"
              % (avec[0] / sans[0] if sans[0] else 0, avec[1] / sans[1] if sans[1] else 0))

    # -- ETAGE 2 : CABLAGE NEUTRALISE = l'AVANT de #267-r1 (relecture du kit BRUT) --------------
    # ⚠ `normal_attack` / `abilities` importent le helper PAR NOM (`from ._shared import ...`) :
    # rebinder le seul `_shared._entity_traits` ne les atteint PAS. On patche les TROIS modules.
    from engine.playbook.prediction import normal_attack as _na, abilities as _abm
    kit_brut = lambda scene, uid: frozenset(                            # noqa: E731
        (GC.unit(scene.vis_by_id.get(uid)) or {}).get("traits") or ())
    cibles = (_shared, _na, _abm)
    vrais = [m._entity_traits for m in cibles]
    try:
        for m in cibles:
            m._entity_traits = kit_brut
        sans0, avec0 = _pred(sc_sans), _pred(sc_avec)
    finally:
        for m, f in zip(cibles, vrais):
            m._entity_traits = f
    print("")
    print("== ETAGE 2 -- CABLAGE NEUTRALISE (`_entity_traits` -> kit BRUT, l'AVANT) ==")
    print("  canal SANS `Summon` : %r" % (sans0,))
    print("  canal AVEC `Summon` : %r" % (avec0,))
    if sans0 != avec0:
        print("  CONTRE-EPREUVE INOPERANTE : le gate bouge encore sans le cablage -- le montage ne")
        print("  mesure donc PAS ce qu'il pretend mesurer.")
        bad += 1
    else:
        print("  OK : sans le cablage, le gate est SOURD au canal (les deux valeurs sont egales).")
        print("  ROUGE PROVOQUE : c'est exactement la prediction que le port rendait avant #267-r1.")

    # -- ETAGE 3 : l'ORACLE natif, sur l'etat NON MUTE -----------------------------------------
    na = None
    for ab in (by_vis[KATAH].get("abilities") or []):
        if "normalattack" in (ab.get("name") or "").lower():
            na = int(ab.get("abilityType") or ab.get("id"))
    orc = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": aid, "targetId": tid,
                                    "abilityType": na}, 150)
    _liste = ((orc or {}).get("events") or (orc or {}).get("predictions")
              or (orc or {}).get("damageEvents") or [])
    evs = [e for e in _liste if e.get("target") in (tid, None) or e.get("targetId") == tid]
    ref = _pred(sc_ref)
    print("")
    print("== ETAGE 3 -- ORACLE NATIF sur l'etat NON MUTE (ability %r) ==" % na)
    if not evs:
        print("  aucun event pour la cible -- brut : %s" % (json.dumps(orc, ensure_ascii=True)[:1600],))
        bad += 1
    else:
        e = evs[0]
        nat = (int(e.get("healthDmgMin") or 0), int(e.get("healthDmgMax") or 0))
        print("  ORACLE      : %r (appliedHits=%r)" % (nat, e.get("appliedHits")))
        print("  port CABLE  : %r   ecart %r" % (ref, (ref[0] - nat[0], ref[1] - nat[1])))
        if ref != nat:
            print("  NOTE : ecart non nul -- a decomposer par etage (il peut etre ANTERIEUR a ce")
            print("  cablage : le kit et la mesure concordent sur `Summon` pour cette cible).")
    return bad


if __name__ == "__main__":
    raise SystemExit(main())
