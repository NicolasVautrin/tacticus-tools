"""probe #267-r1 (montage DISCRIMINANT) -- `MartialKatah` x un summon dont le `Summon` du BC
CONTREDIT le kit gameconfig : la face PREDICTION suit-elle la MESURE ou le kit ?

POURQUOI CE COUPLE. `IdunBattle.Entities.Effects.Loki.MartialKatahDamageEffect$$
CreateEffectDamageBonusForAttack` = `ForPercentIncrease(HasTrait(target, Summon=2),
Direct(GetNumberConstant(cfg 0xf) = martialKatahExtraDmgPct = 100))` -- **+100 % de degat**, sans
aucun gate melee/ranged/normal. Le `HasTrait` y est `IdunBattle.Entities.UnitExtensions$$HasTrait`
sur l'ENTITE (il passe par `IdunBattle.Entities.Triggers.HasTraitTrigger$$Evaluate`, qui resout
l'entite du selecteur puis appelle cette fonction), jamais le gameconfig.

Et `Summon` est justement l'un des traits ou `BC.Units[].Traits` CONTREDIT le kit, DANS LES DEUX
SENS (mesure offline `data/seed-bc.json`, 175 unites -- cf. `probe_267r1_consumer_traits.py`) :
  * `blackSmnBloodletter` / `necroSmnSwarm` / `thousSmnBlueHorror` : `Summon` au KIT, ABSENT du BC
    -> un port qui relit le kit accorde un x2 que le natif REFUSE (degradation PERMISSIVE) ;
  * les 42 npc : `Summon` au BC, ABSENT du kit -> un port qui relit le kit RATE le x2.

Le montage prend la premiere polarite (la seule spawnable) : `necroSpyder` invoque `necroSmnSwarm`
(`ScarabHive`, `constants.unitId`), et `custoTrajann` porte le trait `MartialKatah`. Le summoner est
en team 1 (il joue en premier), le porteur MartialKatah en team 2 -- et on DRIVE la position de ce
dernier au contact du summon (`applyAction` ne verifie pas la propriete du casterId).

ETAGES :
  1 -- le summon existe et sa MESURE (`combatSnapshot.units[].traits`) contredit bien son kit
       (sinon le montage n'est PAS discriminant, et on le DIT au lieu de conclure) ;
  2 -- prediction du port, MEME etat / MEME pas / MEME tuile, seul le CANAL change :
         . canal MESURE (l'etat livre)   -> attendu : PAS de x2 ;
         . canal EFFACE (`traits: null`) -> rejoue l'AVANT (kit) -> attendu : x2.
       Un ecart NUL entre les deux = accord trivial : le montage ne prouve rien, on le DIT ;
  3 -- ORACLE NATIF `aiPlaybookPredict` sur le MEME couple (caster, cible, tuile courante). C'est
       LUI qui tranche laquelle des deux valeurs est juste -- pas nous.

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
from engine.entities.traits.unit_trait import (trait_names_from_ids,           # noqa: E402
                                               unit_trait_names)
from engine.playbook import scene as SC                                        # noqa: E402
from engine.playbook.scene import Scene                                        # noqa: E402

KATAH = "custoTrajann"          # porte le trait MartialKatah
SUMMONER = "necroSpyder"        # ScarabHive -> necroSmnSwarm
SUMMON = "necroSmnSwarm"        # `Summon` au KIT, ABSENT du BC


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
            "--p-units", "%s,necroWarden" % SUMMONER,     # team 1 : joue en PREMIER -> peut caster
            "--a-units", "%s,ultraApothecary" % KATAH]    # team 2 : on drive sa position
    p = subprocess.run(argv, cwd=os.path.dirname(os.path.abspath(__file__)),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.exists(state):
        print("BUILD KO :\n%s" % ((p.stderr or p.stdout or "")[-1200:]))
        raise SystemExit(2)
    st = json.loads(open(state, encoding="utf-8").read())
    return int(st["runnerId"]), state


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


def _efface(snap):
    """Le MEME snapshot, canal `traits` a `null` = l'etat d'AVANT (non mesure -> kit)."""
    return {**snap, "units": [{**u, "traits": None} for u in (snap.get("units") or [])]}


def _hexes(at) -> list:
    out = []
    for u in ((at or {}).get("units") or []):
        for ab in (u.get("abilities") or []):
            for cle in ("fromHere", "targets"):
                for t in (ab.get(cle) or []):
                    tile = t.get("tile") if isinstance(t, dict) else None
                    if isinstance(tile, dict) and tile.get("col") is not None:
                        out.append((int(tile["col"]), int(tile["row"])))
    return out


def _pos_by_id(dv) -> dict:
    return {u.get("id"): ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
            for u in ((dv or {}).get("units") or [])}


def _rapprocher(rpc, rid, a_id, b_id, tours=8) -> tuple:
    """Amene `a_id` et `b_id` au CONTACT en pilotant les DEUX camps (`applyAction` ne verifie pas
    la propriete du casterId, cf. runner.md §4) : a chaque tour, l'unite du camp courant va sur la
    tuile de son movable set qui MINIMISE la distance hex a l'autre, puis `endturn`. Rend les deux
    positions finales. C'est du DRIVE de positions, pas une geometrie subie."""
    for _ in range(tours):
        pos = _pos_by_id(rpc("decisionView", {"runnerId": rid}, 150))
        pa, pb = pos.get(a_id), pos.get(b_id)
        if pa and pb and pa[0] is not None and pb[0] is not None \
                and hexgeo.distance(pa, pb) <= 2:
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


def _ab_id(unit_dict, name_part) -> int | None:
    for ab in (unit_dict.get("abilities") or []):
        if name_part.lower() in (ab.get("name") or "").lower():
            v = ab.get("abilityType") or ab.get("id")
            return int(v) if v is not None else None
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="4242")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    sid = R._resolve_session()
    rpc = _mk_rpc(sid)
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
    from engine.playbook.prediction import make_normal_attack_predictions
    bad = 0
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 200) or {}
    by_vis = {u.get("visualId"): u for u in (dec.get("units") or [])}
    spyder, katah = by_vis.get(SUMMONER), by_vis.get(KATAH)
    if spyder is None or katah is None:
        print("montage KO : %s / %s absents (%r)" % (SUMMONER, KATAH, sorted(by_vis)))
        return 1

    # -- ETAGE 1 : faire apparaitre le summon, puis LIRE sa mesure -----------------------------
    hive = _ab_id(spyder, "ScarabHive")
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": int(spyder["id"]),
                                "abilityType": hive}, 120)
    hexes = _hexes(at)
    spawned = None
    for col, row in hexes[:8]:
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": int(spyder["id"]), "abilityType": hive,
            "to": {"col": col, "row": row}}}, 120)
        dv = rpc("decisionView", {"runnerId": rid}, 120) or {}
        spawned = next((u.get("id") for u in (dv.get("units") or [])
                        if u.get("visualId") == SUMMON), None)
        if spawned is not None:
            break
    if spawned is None:
        print("montage KO : ScarabHive (%r) sur %d hex(es) n'a fait apparaitre aucun %s"
              % (hive, len(hexes), SUMMON))
        return 1

    snap = rpc("combatSnapshot", {"runnerId": rid}, 150)
    ligne = next((u for u in (snap.get("units") or []) if u.get("entityId") == spawned), None)
    if ligne is None or not isinstance(ligne.get("traits"), list):
        print("montage KO : le summon u%s n'a pas de ligne `traits` MESUREE" % spawned)
        return 1
    mes, kit = trait_names_from_ids(ligne["traits"]), frozenset(unit_trait_names(SUMMON))
    print("")
    print("== ETAGE 1 -- le montage est-il DISCRIMINANT ? ==")
    print("  summon u%s (%s)" % (spawned, SUMMON))
    print("    MESURE (combatSnapshot) : %s" % sorted(mes))
    print("    KIT    (gameconfig)     : %s" % sorted(kit))
    print("    kit SEUL : %s   |   BC SEUL : %s" % (sorted(kit - mes), sorted(mes - kit)))
    if ("Summon" in kit) == ("Summon" in mes):
        print("  NON DISCRIMINANT : `Summon` est du MEME cote des deux sources -- ce montage ne")
        print("  peut RIEN prouver sur MartialKatah. (Ce n'est PAS un succes.)")
        return 1
    print("  DISCRIMINANT : `Summon` au kit=%s / mesure=%s"
          % ("Summon" in kit, "Summon" in mes))

    # -- driver la position du porteur MartialKatah AU CONTACT du summon ------------------------
    dv = rpc("decisionView", {"runnerId": rid}, 150) or {}
    pos = {u.get("id"): ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
           for u in (dv.get("units") or [])}
    tpos = pos.get(spawned)
    aid = int(katah["id"])
    board = rpc("boardGraph", {"runnerId": rid}, 120) or {}
    occupees = {p for u, p in pos.items() if u != aid and p and p[0] is not None}
    cible_tuile = None
    for t in (board.get("tiles") or []):
        p = (t.get("col"), t.get("row"))
        if p[0] is None or p in occupees or t.get("forceUnplayable"):
            continue
        if tpos and tpos[0] is not None and hexgeo.distance(p, tpos) == 1:
            cible_tuile = p
            break
    if cible_tuile is not None:
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": aid,
            "to": {"col": cible_tuile[0], "row": cible_tuile[1]}}}, 120)
    dv = rpc("decisionView", {"runnerId": rid}, 150) or {}
    pos = {u.get("id"): ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
           for u in (dv.get("units") or [])}
    apos, tpos = pos.get(aid), pos.get(spawned)
    print("  attaquant u%d (%s) en %r ; cible u%s en %r ; dist hex = %r"
          % (aid, KATAH, apos, spawned, tpos,
             hexgeo.distance(apos, tpos) if (apos and tpos and apos[0] is not None) else None))

    # -- ETAGE 2 : prediction du port, MEME pas, seul le CANAL change ---------------------------
    snap = rpc("combatSnapshot", {"runnerId": rid}, 150)
    sc = _scene(rpc, rid)
    sc0 = _scene(rpc, rid, force=_efface(snap))
    print("  effets ACTIFS de l'attaquant : %r"
          % ([getattr(e, "name", None) for e in (sc.effects(aid) or [])],))

    def _pred(scene):
        ev = make_normal_attack_predictions(scene, aid, spawned, apos)
        if ev is None:
            return None
        r = ev.prediction.raw_health_damage
        return (int(r.min), int(r.max))

    mesuree, reconstruite = _pred(sc), _pred(sc0)
    print("")
    print("== ETAGE 2 -- prediction du port (MEME etat, MEME tuile %r, seul le CANAL change) =="
          % (apos,))
    print("  canal MESURE     : %r" % (mesuree,))
    print("  canal EFFACE/kit : %r" % (reconstruite,))
    if mesuree is None or reconstruite is None:
        print("  prediction indisponible -> montage inexploitable")
        return 1
    if mesuree == reconstruite:
        print("  ACCORD TRIVIAL : les deux canaux donnent la MEME valeur -- le +100 % MartialKatah")
        print("  ne mord pas ici. Rien de prouve par ce montage.")
        bad += 1
    else:
        print("  ECART kit/mesure : x%.4f (min) x%.4f (max)"
              % (reconstruite[0] / mesuree[0] if mesuree[0] else 0,
                 reconstruite[1] / mesuree[1] if mesuree[1] else 0))

    # -- ETAGE 3 : l'ORACLE natif tranche -------------------------------------------------------
    na = _ab_id(katah, "NormalAttack")
    orc = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": aid, "targetId": spawned,
                                    "abilityType": na}, 150)
    evs = [e for e in ((orc or {}).get("events") or []) if e.get("target") == spawned]
    print("")
    print("== ETAGE 3 -- ORACLE NATIF `aiPlaybookPredict` (ability %r, tuile courante) ==" % na)
    if not evs:
        print("  aucun event pour la cible -- brut : %s"
              % (json.dumps(orc, ensure_ascii=True)[:500],))
        bad += 1
    else:
        e = evs[0]
        nat = (int(e.get("healthDmgMin") or 0), int(e.get("healthDmgMax") or 0))
        print("  ORACLE          : %r (appliedHits=%r)" % (nat, e.get("appliedHits")))
        print("  port MESURE     : %r   ecart %r" % (mesuree, (mesuree[0] - nat[0],
                                                               mesuree[1] - nat[1])))
        print("  port kit (avant): %r   ecart %r" % (reconstruite, (reconstruite[0] - nat[0],
                                                                    reconstruite[1] - nat[1])))
        if mesuree != nat:
            print("  ROUGE : le port MESURE ne colle pas a l'oracle")
            bad += 1
        if reconstruite == nat:
            print("  NON DISCRIMINANT vs oracle : le kit collait DEJA -- rien de gagne ici")
            bad += 1
    return bad


if __name__ == "__main__":
    raise SystemExit(main())
