"""#267 -- la face PREDICTION consomme-t-elle `combatSnapshot.units[].traits` ?

LE MANQUE. #264 (`1d798015`) a fait consommer le canal a `load_state`, donc a la face COMBAT.
La face PREDICTION a son PROPRE seam live (`engine/playbook/scene.py` : `build_predictor` /
`refresh_shields` / `Scene.from_predictor_sctx`) et il RECONSTRUISAIT toujours les traits :
`_hydrate_static_unit` appelle `UnitContext.from_snapshot(u, GC.unit(vis), ...)`, qui pose
`traits = gameconfig.unit(vis).traits` et laisse `traits_measured` a faux -- si bien que
`entity_trait_names` re-derivait par-dessus le pseudo-trait de grande-alliance.

CE QUE LIT LE NATIF. La prediction ne lit PAS un substrat separe : `IdunBattle.Core.Services.
DamagePrediction$$ApplyTraitDamageLimitsToDamage` teste la cible par `IdunBattle.Entities.
UnitExtensions$$HasTrait` -- la MEME fonction que la face combat -- qui delegue a
`IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` :

    HasTrait(t) == !retires(+0x50).Contains(t)
                   && ( permanents(+0x40).Contains(t) || temporaires(+0x48).Contains(t) )

Le canal `combatSnapshot.units[].traits` (#233, `0231573`) est l'invoke de cette fonction par valeur
d'enum : il rend l'ensemble EFFECTIF. Une face qui le lit et l'autre qui le reconstruit, c'est le
fork « ce que le moteur fait != ce que la prediction annonce ».

CE QUE MESURE CETTE SONDE (le critere, binaire) : apres `build_predictor`, l'ensemble de traits que
rend la face prediction est-il EGAL a celui que publie `combatSnapshot`, sur chaque ligne ?

  1. MONTAGE A -- roster EXPLICITE portant le cas DISCRIMINANT `necroOverlord` : il porte
     `Resilient` au GAMECONFIG et PAS en bataille. Egalite ligne a ligne, puis l'effet
     OBSERVABLE de bout en bout : `_target_damage_limits(scene, u)["target_has_resilient"]`,
     le champ que `apply_trait_damage_limits_to_damage` consomme pour caper a `HP-1`.
  2. NON-VACUITE -- le MEME snapshot avec le canal EFFACE (`traits: null`, l'etat d'avant) doit
     DIVERGER. Sans ce controle, 1 passerait a vide.
  3. TRI-ETAT -- `null` n'est PAS `[]`. Canal efface => la face prediction garde sa
     RECONSTRUCTION intacte (`traits_measured` faux) ; `[]` => mesure, ensemble VIDE.
  4. MONTAGE B / DYNAMIQUE -- `refresh_shields` (1x/pas) doit propager les traits ACCORDES EN
     BATAILLE : cast de `DutyEternal` (1158) par `ultraDreadnought`, qui SPAWNE
     `ultraSmnDreadnought` avec un `AddTrait(Stationary)` on-appearance. Le seed du build est COLD
     (pas 0) : sans re-capture par pas, un trait pose apres le pas 0 resterait invisible pour
     toute la bataille.

Usage :  python scripts/python/probe_267_predictor_traits.py [--board MC1_67] [--seed 26701]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import uuid

HOST = "http://127.0.0.1:8765"
PYDIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(PYDIR))
LOGS = os.path.join(RACINE, "logs")
sys.path.insert(0, PYDIR)

DUTY_ETERNAL = 1158          # `ultraDreadnought` : Spawn(ultraSmnDreadnought) + AddTrait(Stationary)
DISCRIMINANT = "necroOverlord"       # `Resilient` au gameconfig, ABSENT en bataille
DISCRIMINANT_TRAIT = "Resilient"


def _http(chemin, methode="GET", corps=None, timeout=300):
    req = urllib.request.Request(
        HOST + chemin, method=methode,
        data=None if corps is None else json.dumps(corps).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def rpc(sid, methode, args, timeout=240.0):
    return _http("/api/scripts/%d/rpc" % sid, "POST",
                 {"method": methode, "args": args, "timeout": int(timeout * 1000)},
                 timeout + 20).get("result")


def build(nom, extra):
    """Construit un runner isole ; rend (runnerId, chemin du state-file) ou (None, msg)."""
    os.makedirs(LOGS, exist_ok=True)
    etat = os.path.join(LOGS, "_probe267_%s_%s.json" % (nom, uuid.uuid4().hex[:6]))
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--state-file", etat, *extra],
                       cwd=PYDIR, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if not os.path.exists(etat):
        return None, (p.stderr or p.stdout or "")[-600:]
    with open(etat, encoding="utf-8") as f:
        return json.load(f)["runnerId"], etat


def _scene_de(sid, rid, snap_force=None, dv=None):
    """Monte la Scene de la face PREDICTION exactement comme le spine de decision
    (`engine.ai.context`) : `build_predictor` + `step_context` + `from_predictor_sctx`.

    `snap_force` (optionnel) substitue le `combatSnapshot` -- sert aux etapes NON-VACUITE,
    TRI-ETAT et AGREEMENT, qui rejouent le MEME etat avec le canal mute (canal a `null` = l'etat
    d'AVANT le cablage, au bit pres). `dv` (optionnel) fige la vue de decision, pour que les deux
    regimes se comparent sur le MEME pas."""
    from engine.playbook import scene as SC
    from engine.playbook.scene import Scene

    def _rpc(m, b=None, t=120):
        if m == "combatSnapshot" and snap_force is not None:
            return snap_force
        return rpc(sid, m, [b] if b is not None else [], t)

    predictor = SC.build_predictor(_rpc, rid)
    if predictor is None:
        return None, None, None
    if dv is None:
        dv = rpc(sid, "decisionView", [{"runnerId": rid, "maxRank": 1}], 120)
    sctx = SC.step_context(predictor, dv)
    # MEME seam que le spine de decision (`engine.ai.context`) : `hpmax_by_id` vient d'`observeBattle`
    # (+ le MaxHealth EFFECTIF du predictor). Sans lui `scene.hpmax()` rend None, donc
    # `_target_damage_limits.max_health` vaut 0 et le cap Resilient est INERTE
    # (`ApplyResilientTraitDamageLimit` exige `initialHealth > 1`) -- un montage qui l'omet ne peut
    # PAS observer le cas discriminant, quel que soit le cablage des traits.
    obs = rpc(sid, "observeBattle", [{"runnerId": rid}], 90) or {}
    hpmax = {u.get("squadId"): (u.get("hpMax") or 0) for u in (obs.get("units") or [])}
    hpmax.update(predictor.get("hpmax_eff_by_id") or {})
    sctx["hpmax_by_id"] = hpmax
    return Scene.from_predictor_sctx(predictor, sctx, None), predictor, dv


def confronter(sid, rid, titre, snap=None, scene=None):
    """Compare, ligne a ligne, la MESURE au substrat que la face PREDICTION expose.

    Rend `(nb_lignes, ecarts, rate_par_la_reconstruction, scene, snap)`."""
    from engine.entities.traits.unit_trait import entity_trait_names, trait_names_from_ids

    if snap is None:
        snap = rpc(sid, "combatSnapshot", [{"runnerId": rid}], 90)
    if scene is None:
        scene, _pred, _dv = _scene_de(sid, rid)
    if scene is None:
        return 0, [("scene", None, "build_predictor", [], [])], 0, None, snap

    # L'etat d'AVANT (canal efface) : c'est la reconstruction pure, la reference de non-vacuite.
    snap0 = {**snap, "units": [{**u, "traits": None} for u in (snap.get("units") or [])]}
    scene0, _p0, _d0 = _scene_de(sid, rid, snap_force=snap0)

    ecarts, rates, n = [], 0, 0
    print("\n== %s" % titre)
    for su in (snap.get("units") or []):
        eid = su.get("entityId")
        if eid is None or not isinstance(su.get("traits"), list):
            continue
        ctx = scene.ctx(eid)
        if ctx is None:
            continue                       # MoW : hors tables prediction (canal `.mows` separe)
        n += 1
        mes = trait_names_from_ids(su["traits"])
        vis = scene.vis_by_id.get(eid)
        lus = {
            "entity_trait_names": frozenset(entity_trait_names(ctx, vis)),
            "scene.unit_state.traits": frozenset(scene.unit_state(eid).get("traits") or ()),
        }
        for nom, val in lus.items():
            if val != mes:
                ecarts.append((eid, vis, nom, sorted(mes - val), sorted(val - mes)))
        avant = frozenset(entity_trait_names(scene0.ctx(eid) if scene0 is not None else None, vis))
        if avant != mes:
            rates += 1
        print("  u%-4s %-24s mes=%2d  seede=%s  reconstruction_ecart=%r"
              % (eid, str(vis)[:24], len(mes),
                 "OK" if all(v == mes for v in lus.values()) else "DIV",
                 sorted(mes ^ avant)))
    for eid, vis, nom, manque, trop in ecarts:
        print("    ECART u%s %s via %s : MANQUE=%r EN_TROP=%r" % (eid, vis, nom, manque, trop))
    return n, ecarts, rates, scene, snap


def etape_discriminant(scene, snap):
    """`necroOverlord` / `Resilient` : de l'ensemble de traits jusqu'au champ que consomme
    `apply_trait_damage_limits_to_damage`. Si `target_has_resilient` ne bouge pas, le cablage
    n'est pas EFFECTIF -- c'est le controle que le brief impose."""
    from engine.entities.traits.unit_trait import unit_trait_names, trait_names_from_ids
    from engine.playbook.prediction._shared import _target_damage_limits

    uid = next((u for u in scene.vis_by_id if scene.vis_by_id[u] == DISCRIMINANT), None)
    if uid is None:
        return "NON MESURE (unite absente)"
    ligne = next((u for u in (snap.get("units") or []) if u.get("entityId") == uid), {})
    if not isinstance(ligne.get("traits"), list):
        return "NON MESURE (canal null)"
    mes = trait_names_from_ids(ligne["traits"])
    kit = unit_trait_names(DISCRIMINANT)
    lim = _target_damage_limits(scene, uid)
    print("  u%s %s : kit=%s" % (uid, DISCRIMINANT, sorted(kit)))
    print("            mesure=%s" % sorted(mes))
    print("            _target_damage_limits.target_has_resilient=%s (kit dit %s)"
          % (lim["target_has_resilient"], DISCRIMINANT_TRAIT in kit))
    if DISCRIMINANT_TRAIT not in kit:
        return "NON DISCRIMINANT (le kit ne porte pas %s)" % DISCRIMINANT_TRAIT
    if DISCRIMINANT_TRAIT in mes:
        return "NON DISCRIMINANT (la mesure porte %s)" % DISCRIMINANT_TRAIT
    return "OK" if lim["target_has_resilient"] is False else "ECHEC"


def etape_tri_etat(sid, rid, snap):
    """`null` n'est PAS `[]` : canal efface => reconstruction INTACTE ; `[]` => ensemble VIDE."""
    from engine.entities.traits.unit_trait import entity_trait_names, unit_trait_names

    cible = next((u.get("entityId") for u in (snap.get("units") or [])
                  if isinstance(u.get("traits"), list) and u.get("traits")), None)
    if cible is None:
        return "NON MESURE"

    def _lire(mut):
        s = {**snap, "units": [({**u, **mut} if u.get("entityId") == cible else u)
                               for u in (snap.get("units") or [])]}
        sc, _p, _d = _scene_de(sid, rid, snap_force=s)
        ctx = sc.ctx(cible) if sc is not None else None
        vis = sc.vis_by_id.get(cible) if sc is not None else None
        return (frozenset(entity_trait_names(ctx, vis)),
                bool(getattr(ctx, "traits_measured", False)) if ctx is not None else False,
                frozenset(unit_trait_names(vis)))

    nul, m_nul, reconstruit = _lire({"traits": None})
    vide, m_vide, _ = _lire({"traits": []})
    print("  u%s : canal null -> %d traits (mesure=%s, reconstruction=%d) ; canal [] -> %d traits "
          "(mesure=%s)" % (cible, len(nul), m_nul, len(reconstruit), len(vide), m_vide))
    ok = (nul == reconstruit) and (not m_nul) and (vide == frozenset()) and m_vide
    return "OK" if ok else "ECHEC"


def etape_dynamique(sid, rid):
    """Un trait ACCORDE EN BATAILLE apres le pas 0 doit devenir visible par `refresh_shields`.

    `DutyEternal` (1158) spawne `ultraSmnDreadnought` avec `AddTrait(Stationary)` a l'apparition :
    le seed COLD du build ne peut pas le connaitre. Rend (verdict, uid du summon)."""
    from engine.playbook import scene as SC
    from engine.playbook.scene import Scene
    from engine.entities.traits.unit_trait import entity_trait_names, trait_names_from_ids

    def _rpc(m, b=None, t=120):
        return rpc(sid, m, [b] if b is not None else [], t)

    predictor = SC.build_predictor(_rpc, rid)          # COLD : avant tout cast
    if predictor is None:
        return "ECHEC (build_predictor)", None
    dv = rpc(sid, "decisionView", [{"runnerId": rid, "maxRank": 1, "allAbilities": True}], 120)
    mow = next((m for m in (dv.get("mows") or [])
                if m.get("visualId") == "ultraDreadnought"), None)
    if mow is None:
        return "NON MESURE (MoW absente)", None
    at = rpc(sid, "abilityTargets", [{"runnerId": rid, "unitId": int(mow["casterId"]),
                                      "abilityType": DUTY_ETERNAL}], 90) or {}
    hexes = [(int(t["tile"]["col"]), int(t["tile"]["row"]))
             for u in (at.get("units") or [])
             for ab in (u.get("abilities") or [])
             for cle in ("fromHere", "targets")
             for t in (ab.get(cle) or [])
             if isinstance(t.get("tile"), dict) and t["tile"].get("col") is not None]
    spawned = None
    for col, row in hexes[:6]:
        rpc(sid, "applyAction", [{"runnerId": rid, "action": {
            "kind": "ability", "casterId": int(mow["casterId"]),
            "abilityType": DUTY_ETERNAL, "to": {"col": col, "row": row}}}], 90)
        dv2 = rpc(sid, "decisionView", [{"runnerId": rid, "maxRank": 1}]) or {}
        spawned = next((u.get("id") for u in (dv2.get("units") or [])
                        if u.get("visualId") == "ultraSmnDreadnought"), None)
        if spawned is not None:
            break
    if spawned is None:
        return "NON MESURE (pas de spawn)", None

    SC.refresh_shields(predictor, _rpc, rid)           # le pas SUIVANT de la boucle de decision
    dv3 = rpc(sid, "decisionView", [{"runnerId": rid, "maxRank": 1}], 120)
    scene = Scene.from_predictor_sctx(predictor, SC.step_context(predictor, dv3), None)
    snap = rpc(sid, "combatSnapshot", [{"runnerId": rid}], 90)

    ecarts, n = [], 0
    for su in (snap.get("units") or []):
        eid = su.get("entityId")
        if eid is None or not isinstance(su.get("traits"), list) or scene.ctx(eid) is None:
            continue
        n += 1
        mes = trait_names_from_ids(su["traits"])
        lu = frozenset(entity_trait_names(scene.ctx(eid), scene.vis_by_id.get(eid)))
        if lu != mes:
            ecarts.append((eid, scene.vis_by_id.get(eid), sorted(mes - lu), sorted(lu - mes)))
    lu_s = frozenset(entity_trait_names(scene.ctx(spawned), scene.vis_by_id.get(spawned))
                     ) if scene.ctx(spawned) is not None else frozenset()
    print("  summon u%s ultraSmnDreadnought apres refresh_shields : traits=%s (Stationary=%s)"
          % (spawned, sorted(lu_s), "Stationary" in lu_s))
    for eid, vis, manque, trop in ecarts:
        print("    ECART u%s %s : MANQUE=%r EN_TROP=%r" % (eid, vis, manque, trop))
    return ("OK" if (n and not ecarts and "Stationary" in lu_s) else "ECHEC"), spawned


def _rows_contre(dec, scene, cible_vis=None):
    """Rows d'AGREEMENT (attaque NORMALE) contre les unites de visual `cible_vis` (None = TOUTES,
    pour la mesure d'agreement GLOBALE du montage D) : oracle natif
    (`decisionView.attackPlans[].evals[].ranked[0].dmg{Min,Max}` = le preview
    `IdunBattle.Core.Services.DamagePredictionQuery$$GetAllPredictions`) vs prediction du port
    (`engine.playbook.prediction.make_normal_attack_predictions`) DEPUIS LA MEME TUILE."""
    from engine.playbook import prediction

    normales = {u.get("id"): {ab.get("id") for ab in (u.get("abilities") or [])
                              if ab.get("kind") == "normal"}
                for u in (dec.get("units") or [])}
    rows = []
    for ap_ in (dec.get("attackPlans") or []):
        a_id = ap_.get("unitId")
        if scene.ctx(a_id) is None:
            continue
        for ev in (ap_.get("evals") or []):
            if normales.get(a_id) and ev.get("abilityId") not in normales[a_id]:
                continue
            t_id = ev.get("targetId")
            if cible_vis is not None and scene.vis_by_id.get(t_id) != cible_vis:
                continue
            rk = ev.get("ranked") or []
            if not rk or rk[0].get("dmgMax") is None:
                continue
            r0 = rk[0]
            pos = ((r0.get("col"), r0.get("row")) if r0.get("col") is not None
                   else scene.pos(a_id))
            pe = prediction.make_normal_attack_predictions(scene, a_id, t_id, pos)
            if pe is None:
                continue
            res = pe.prediction.accurate_health_damage
            rows.append({"att": a_id, "tgt": t_id, "pos": pos,
                         "oracle": (r0.get("dmgMin"), r0.get("dmgMax")),
                         "offline": (res.min, res.max),
                         "killSure": bool(r0.get("killSure")),
                         "kill": bool(r0.get("kill")),
                         "predOpt": bool(r0.get("predOptimistic"))})
    return rows


def _decision(sid, rid):
    return rpc(sid, "decisionView", [{"runnerId": rid, "maxRank": 3, "allAbilities": True}], 120)


def _drive(sid, rid, att_vis, tgt_vis, max_turns=8):
    """Amene l'attaquant au contact de la cible et rend la vue de decision PENDANT SON TOUR.

    Ecrit sur mesure plutot que `predict_samples._drive_into_range` : ce dernier s'arrete a
    `>= 3` plans peuples (montage a rosters pleins) et, faute de les atteindre, rend une vue prise
    APRES un `endturn` -- donc celle du camp ADVERSE, ou l'attaquant voulu n'a aucun plan. Ici
    l'attaquant est UNIQUE et la mesure doit se faire de son cote."""
    import hexgeo

    def _u(dec, vis):
        return next((u for u in (dec.get("units") or [])
                     if u.get("visualId") == vis and u.get("alive")), None)

    def _p(u):
        q = (u or {}).get("pos") or {}
        return (q.get("col"), q.get("row")) if q.get("col") is not None else None

    dec = _decision(sid, rid)
    att = _u(dec, att_vis)
    if att is None:
        return dec
    owner = att.get("owner")
    for _ in range(max_turns):
        dec = _decision(sid, rid)
        if dec.get("stageName") != "Running":
            return dec
        if dec.get("currentPlayer") != owner:
            rpc(sid, "applyAction", [{"runnerId": rid, "action": {"kind": "endturn"}}], 60)
            continue
        att, tgt = _u(dec, att_vis), _u(dec, tgt_vis)
        if att is None or tgt is None:
            return dec
        # un plan de l'attaquant contre la cible, avec un degat chiffre -> on est a portee
        if any(e.get("targetId") == tgt["id"] and (e.get("ranked") or [{}])[0].get("dmgMax")
               is not None
               for ap_ in (dec.get("attackPlans") or []) if ap_.get("unitId") == att["id"]
               for e in (ap_.get("evals") or [])):
            return dec
        mt = rpc(sid, "aiMovableTiles", [{"runnerId": rid}], 60) or {}
        row = next((x for x in (mt.get("units") or []) if x.get("unitId") == att["id"]), None)
        tiles = [(t["col"], t["row"]) for t in ((row or {}).get("tiles") or [])
                 if t.get("col") is not None]
        tp = _p(tgt)
        if tiles and tp is not None:
            best = min(tiles, key=lambda c: hexgeo.distance(c, tp))
            if hexgeo.distance(best, tp) < hexgeo.distance(_p(att) or best, tp):
                rpc(sid, "applyAction", [{"runnerId": rid, "action": {
                    "kind": "move", "unitId": att["id"],
                    "to": {"col": best[0], "row": best[1]}}}], 60)
                continue
        rpc(sid, "applyAction", [{"runnerId": rid, "action": {"kind": "endturn"}}], 60)
    return _decision(sid, rid)


def etape_agreement(sid, board, seed, attaquant, keep):
    """AGREEMENT de la face PREDICTION sur le cas DISCRIMINANT, dans le regime ou le cap mord.

    `IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit` ne cape que si
    `HasTrait(defender, 0x3f1)` ET `damage > currentHealth - 1` ET pas d'overkill. Le seuil
    d'overkill (`overkillDmgPctOfHealth` = 100) rend la porte franchissable : avec une cible a PV
    PLEINS, `IsOverkill` est faux tant que `dmgMin < 2 x PV`. On calibre donc les PV de la cible a
    ~75 % du dmgMin natif -> `PV <= dmgMin < 2 x PV` : le cap MORD si (et seulement si) le port
    croit la cible `Resilient`.

    Deux builds : le premier MESURE le degat (PV enormes, aucun cap possible), le second confronte.
    Trois valeurs comparees sur le MEME pas et la MEME tuile :
      * ORACLE natif   -- `decisionView.attackPlans` ;
      * port MESURE    -- traits lus du canal (l'etat livre) ;
      * port RECONSTRUIT -- MEME etat, canal `traits` efface = l'etat d'AVANT, au bit pres.
    Rend (verdict, detail)."""
    runners = []
    try:
        rid, etat = build("sonde", ["--seed", seed, "--board", board,
                                    "--p-units", attaquant, "--a-units", DISCRIMINANT,
                                    "--hp-target", "300000"])
        if rid is None:
            return "NON MESURE (build sonde: %s)" % etat, None
        runners.append((rid, etat))
        dec = _drive(sid, rid, attaquant, DISCRIMINANT)
        scene, _p, _d = _scene_de(sid, rid, dv=dec)
        brut = _rows_contre(dec, scene, DISCRIMINANT)
        rows = [r for r in brut if not r["predOpt"]]
        print("  sonde : plans=%d evals-normales-vs-%s=%d dont non-predOpt=%d ; positions=%s"
              % (len(dec.get("attackPlans") or []), DISCRIMINANT, len(brut), len(rows),
                 {u.get("visualId"): (u.get("pos") or {}).get("col") for u in (dec.get("units") or [])}))
        if not rows:
            for ap_ in (dec.get("attackPlans") or []):
                print("    plan u%s : evals=%s" % (ap_.get("unitId"), [
                    {"ab": e.get("abilityId"), "tgt": e.get("targetId"),
                     "tgtVis": e.get("targetVis"), "rk0": (e.get("ranked") or [{}])[0]}
                    for e in (ap_.get("evals") or [])][:6]))
            print("    normales par unite = %s" % {
                u.get("id"): [ab.get("id") for ab in (u.get("abilities") or [])
                              if ab.get("kind") == "normal"] for u in (dec.get("units") or [])})
            return "NON MESURE (aucun plan d'attaque normale a portee)", None
        dmin = min(r["oracle"][0] for r in rows)
        pv = max(2, int(dmin * 0.75))
        print("  sonde : %d plan(s) contre %s, dmgMin natif=%d -> PV cible calibres a %d"
              % (len(rows), DISCRIMINANT, dmin, pv))

        rid2, etat2 = build("confront", ["--seed", seed, "--board", board,
                                         "--p-units", attaquant, "--a-units", DISCRIMINANT,
                                         "--hp-target", str(pv)])
        if rid2 is None:
            return "NON MESURE (build confront: %s)" % etat2, None
        runners.append((rid2, etat2))
        dec2 = _drive(sid, rid2, attaquant, DISCRIMINANT)
        snap = rpc(sid, "combatSnapshot", [{"runnerId": rid2}], 90)
        snap0 = {**snap, "units": [{**u, "traits": None} for u in (snap.get("units") or [])]}
        sc_new, _a, _b = _scene_de(sid, rid2, dv=dec2)
        sc_old, _c, _d2 = _scene_de(sid, rid2, snap_force=snap0, dv=dec2)
        r_new = {(r["att"], r["tgt"], r["pos"]): r for r in _rows_contre(dec2, sc_new, DISCRIMINANT)
                 if not r["predOpt"]}
        r_old = {(r["att"], r["tgt"], r["pos"]): r for r in _rows_contre(dec2, sc_old, DISCRIMINANT)
                 if not r["predOpt"]}
        cles = [k for k in r_new if k in r_old]
        if not cles:
            return "NON MESURE (aucun plan comparable apres calibrage)", None
        # Le cap `ApplyResilientTraitDamageLimit` borne a `currentHealth - 1` : l'ecart de DEGAT
        # qu'il induit vaut donc structurellement 1 PV, et une tolerance d'arrondi le masquerait.
        # On compare a l'EXACT, et on regarde surtout le retournement de DECISION qu'il porte :
        # `killSure` natif (le coup tue A COUP SUR) contre `dmgMin >= PV` cote port -- capee a
        # `PV-1`, la borne MIN du port dit « ne tue pas garanti » la ou le natif dit l'inverse.
        ok_new = ok_old = kill_new = kill_old = 0
        for k in cles:
            o = r_new[k]["oracle"]
            n_, v_ = r_new[k]["offline"], r_old[k]["offline"]
            e_new = max(abs(o[0] - n_[0]), abs(o[1] - n_[1]))
            e_old = max(abs(o[0] - v_[0]), abs(o[1] - v_[1]))
            ks = r_new[k]["killSure"]
            ks_new, ks_old = (n_[0] >= pv), (v_[0] >= pv)
            ok_new += int(e_new == 0)
            ok_old += int(e_old == 0)
            kill_new += int(ks_new == ks)
            kill_old += int(ks_old == ks)
            print("    att u%s -> u%s @%s  PV=%d | ORACLE=%s killSure=%s | port MESURE=%s (ecart %d,"
                  " killSure=%s) | port RECONSTRUIT=%s (ecart %d, killSure=%s)"
                  % (k[0], k[1], k[2], pv, o, ks, n_, e_new, ks_new, v_, e_old, ks_old))
        print("  AGREEMENT EXACT : MESURE %d/%d   RECONSTRUIT %d/%d"
              % (ok_new, len(cles), ok_old, len(cles)))
        print("  ACCORD killSure : MESURE %d/%d   RECONSTRUIT %d/%d"
              % (kill_new, len(cles), kill_old, len(cles)))
        detail = {"pv": pv, "n": len(cles), "ok_new": ok_new, "ok_old": ok_old,
                  "kill_new": kill_new, "kill_old": kill_old}
        if ok_old == len(cles) and kill_old == len(cles):
            return "NON DISCRIMINANT (la reconstruction agree aussi -- cap non exerce)", detail
        return ("OK" if (ok_new == len(cles) and kill_new == len(cles)) else "ECHEC"), detail
    finally:
        if not keep:
            for rid_, etat_ in runners:
                try:
                    rpc(sid, "disposeRunner", [{"runnerId": rid_}], 20)
                except Exception:                                    # noqa: BLE001
                    pass
                if etat_ and os.path.exists(etat_):
                    os.remove(etat_)


def etape_agreement_global(sid, board, seed, keep):
    """NON-REGRESSION A L'ECHELLE : sur un roster ALEATOIRE plein drive au contact, l'agreement de
    la face prediction contre l'oracle natif (`decisionView.attackPlans`) ne doit pas BAISSER quand
    les traits viennent de la mesure plutot que du kit.

    Le cablage deplace la source des traits SOUS TOUS les gates de prediction (limites de degat,
    conditions d'effets, pierce par trait, cardinal `Psyker`) : un cas discriminant vert ne dit rien
    des autres paires. Meme etat, meme pas, meme tuile ; seul le canal `traits` change."""
    runners = []
    try:
        rid, etat = build("global", ["--seed", seed, "--board", board, "--roster", "5"])
        if rid is None:
            return "NON MESURE (build: %s)" % etat, None
        runners.append((rid, etat))
        import predict_samples as PS
        dec = PS._drive_into_range(sid, rid, 1, 6)
        snap = rpc(sid, "combatSnapshot", [{"runnerId": rid}], 90)
        snap0 = {**snap, "units": [{**u, "traits": None} for u in (snap.get("units") or [])]}
        sc_new, _a, _b = _scene_de(sid, rid, dv=dec)
        sc_old, _c, _d = _scene_de(sid, rid, snap_force=snap0, dv=dec)
        r_new = {(r["att"], r["tgt"], r["pos"]): r for r in _rows_contre(dec, sc_new)
                 if not r["predOpt"]}
        r_old = {(r["att"], r["tgt"], r["pos"]): r for r in _rows_contre(dec, sc_old)
                 if not r["predOpt"]}
        cles = [k for k in r_new if k in r_old]
        if not cles:
            return "NON MESURE (aucune paire exploitable)", None
        ok_new = ok_old = 0
        diffs = []
        for k in cles:
            o = r_new[k]["oracle"]
            n_, v_ = r_new[k]["offline"], r_old[k]["offline"]
            e_new = max(abs(o[0] - n_[0]), abs(o[1] - n_[1]))
            e_old = max(abs(o[0] - v_[0]), abs(o[1] - v_[1]))
            ok_new += int(e_new <= 3)
            ok_old += int(e_old <= 3)
            if n_ != v_:
                diffs.append("u%s->u%s : MESURE=%s (ecart %d) RECONSTRUIT=%s (ecart %d) oracle=%s"
                             % (k[0], k[1], n_, e_new, v_, e_old, o))
        print("  %d paire(s) comparables ; AGREEMENT (+/-3) : MESURE %d/%d   RECONSTRUIT %d/%d"
              % (len(cles), ok_new, len(cles), ok_old, len(cles)))
        for d in diffs[:8]:
            print("    %s" % d)
        return ("OK" if ok_new >= ok_old else "ECHEC"), {"n": len(cles), "new": ok_new,
                                                         "old": ok_old, "diffs": len(diffs)}
    finally:
        if not keep:
            for rid_, etat_ in runners:
                try:
                    rpc(sid, "disposeRunner", [{"runnerId": rid_}], 20)
                except Exception:                                    # noqa: BLE001
                    pass
                if etat_ and os.path.exists(etat_):
                    os.remove(etat_)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="26701")
    ap.add_argument("--attaquant", default="ultraTitus",
                    help="montage C : l'attaquant dont le degat calibre les PV de la cible")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--only", choices=["ab", "c", "d"], default=None,
                    help="ne jouer qu'une partie des montages (mise au point)")
    a = ap.parse_args()

    sid = int((_http("/api/admin/status").get("session") or {}).get("id"))
    print("session=%d board=%s seed=%s" % (sid, a.board, a.seed))
    resultats = []
    runners = []
    if a.only == "c":
        print("\n== MONTAGE C -- agreement prediction (oracle natif vs port), cap Resilient exerce")
        v, _d = etape_agreement(sid, a.board, a.seed, a.attaquant, a.keep)
        print("\n  6 C agreement face prediction : %s" % v)
        return 0 if not v.startswith("ECHEC") else 1
    if a.only == "d":
        print("\n== MONTAGE D -- agreement GLOBAL (non-regression a l'echelle)")
        v, _d = etape_agreement_global(sid, a.board, a.seed, a.keep)
        print("\n  7 D agreement global : %s" % v)
        return 0 if not v.startswith("ECHEC") else 1
    try:
        # --- 1. MONTAGE A : egalite + cas discriminant ---------------------------------------
        rid, etat = build("a", ["--seed", a.seed, "--board", a.board,
                                "--p-units", "ultraTitus,ultraApothecary",
                                "--a-units", "%s,orksNob" % DISCRIMINANT])
        if rid is None:
            print("ECHEC build A: %s" % etat)
            return 3
        runners.append((rid, etat))
        n, ecarts, rates, scene, snap = confronter(
            sid, rid, "MONTAGE A -- face PREDICTION (build_predictor / Scene)")
        resultats.append(("1 A egalite prediction == mesure (%d lignes)" % n,
                          "OK" if (n and not ecarts) else "ECHEC"))
        resultats.append(("2 A non-vacuite (%d unites ratees par la reconstruction)" % rates,
                          "OK" if rates >= 1 else "ECHEC"))
        print("\n-- cas DISCRIMINANT")
        resultats.append(("3 discriminant %s / %s" % (DISCRIMINANT, DISCRIMINANT_TRAIT),
                          etape_discriminant(scene, snap)))
        print("\n-- tri-etat")
        resultats.append(("4 tri-etat null != []", etape_tri_etat(sid, rid, snap)))

        # --- 2. MONTAGE B : trait ACCORDE EN BATAILLE, propagation par-pas --------------------
        rid_b, etat_b = build("b", ["--seed", "31337", "--board", a.board,
                                    "--p-units", "ultraTitus,ultraApothecary",
                                    "--a-units", "%s,orksWarboss" % DISCRIMINANT,
                                    "--p-mow", "ultraDreadnought"])
        if rid_b is None:
            print("ECHEC build B: %s" % etat_b)
            return 3
        runners.append((rid_b, etat_b))
        print("\n== MONTAGE B -- AddTrait en bataille + refresh_shields")
        verdict_b, _sp = etape_dynamique(sid, rid_b)
        resultats.append(("5 B refresh par-pas (trait accorde en bataille)", verdict_b))

        # les runners A/B sont liberes AVANT le montage C (il en construit deux) -- discipline
        # runner : on n'affame pas les autres agents en tenant tout jusqu'au teardown.
        for rid_, etat_ in runners:
            try:
                rpc(sid, "disposeRunner", [{"runnerId": rid_}], 20)
            except Exception:                                        # noqa: BLE001
                pass
            if etat_ and os.path.exists(etat_):
                os.remove(etat_)
        runners = []

        # --- 3. MONTAGE C : AGREEMENT de la face prediction, cap Resilient exerce -------------
        if a.only != "ab":
            print("\n== MONTAGE C -- agreement prediction (oracle natif vs port), cap Resilient exerce")
            verdict_c, _det = etape_agreement(sid, a.board, a.seed, a.attaquant, a.keep)
            resultats.append(("6 C agreement face prediction (regime ou le cap mord)", verdict_c))
            print("\n== MONTAGE D -- agreement GLOBAL (non-regression a l'echelle)")
            verdict_d, _detd = etape_agreement_global(sid, a.board, a.seed, a.keep)
            resultats.append(("7 D agreement global (mesure >= reconstruit)", verdict_d))
    finally:
        if not a.keep:
            for rid_, etat_ in runners:
                try:
                    rpc(sid, "disposeRunner", [{"runnerId": rid_}], 20)
                except Exception:                                    # noqa: BLE001
                    pass
                if etat_ and os.path.exists(etat_):
                    os.remove(etat_)

    print("\n" + "=" * 78)
    for nom, v in resultats:
        print("  %-56s %s" % (nom, v))
    return 0 if not [n for n, v in resultats if v.startswith("ECHEC")] else 1


if __name__ == "__main__":
    sys.exit(main())
