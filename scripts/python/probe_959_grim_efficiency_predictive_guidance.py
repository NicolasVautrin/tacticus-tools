"""Probe #959 -- les DEUX passifs d'AURA du roster Leagues of Votann, confrontes LIVE.

  * `GrimEfficiency`     (TriggeredAbilityType 1490, `votanUthar`) -- aura STAT-MOD projetee,
    partitionnee par les deux marqueurs de stance du trait `PrioritisedEfficiency` ;
  * `PredictiveGuidance` (TriggeredAbilityType 1525, `votanMemnyr`) -- aura de DEGAT + de COUPS
    projetee sur les ENNEMIS, dont le bonus va a l'ATTAQUANT.

RE complete : `docs/rl/case-959-grim-efficiency-predictive-guidance.md` et l'en-tete des classes
dans `engine/entities/effects/loki/votann.py`.

Les deux porteurs sont HORS POOL -> `catalog_inject` les amene (case-92 §6). Ce n'est pas un
blocage : la mesure ci-dessous les spawne, avec leur kit complet.

MONTAGE (board MC1_67, geometrie CALCULEE puis ASSERTIONNEE, jamais subie) :

    U = votanUthar  (0,0)   source GrimEfficiency ; attaquant Leagues of Votann pour l'autre aura
    M = votanMemnyr (0,2)   source PredictiveGuidance ; d(U,M) = 2 -> DANS l'aura d'Uthar
    C = ultraTitus  (1,2)   d(U,C) = 2 -> DANS l'aura ; NI LoV NI Mechanical -> temoin de FACTION
    D = ultraCalgar (4,0)   d(U,D) = 4 -> HORS de l'aura -> temoin GEOMETRIQUE
    E = orksNob     (0,1)   d(M,E) = 1 -> DANS l'aura d'Ammuk  ; d(U,E) = 1
    F = orksNob     (1,0)   d(M,F) = 3 -> HORS de l'aura      ; d(U,F) = 1

E et F sont deux CLONES du meme id, tous deux ADJACENTS a Uthar : le seul discriminant entre les
deux bras est l'appartenance a l'aura d'Ammuk. C'est ce qui rend l'ecart ATTRIBUABLE.

ETAGES :
  [1] MONTAGE   -- les six distances sont celles voulues (sinon rien n'est mesure) ;
  [2] CANAL     -- qui PORTE quoi : Uthar la SEULE aura de sa stance courante, Ammuk les TROIS,
                   les ennemis AUCUNE (le selecteur n'est pas materialise chez la cible) ;
  [3] STAT-MOD  -- `statModSources` NATIF vs `refresh_aura_stat_modifiers` du port, par unite ;
  [4] PREDICTION-- `decisionView.attackPlans[].evals[].ranked[].dmg{Min,Max}` NATIF vs
                   `prediction.make_normal_attack_predictions` du port, par tuile candidate ;
  [5] MUTANTS   -- sept mutations du port doivent TOUTES faire rougir [3] ou [4]. Un mutant VERT
                   dit que le temoin est aveugle, pas que le port est bon.

Usage :
    python probe_959_grim_efficiency_predictive_guidance.py            # tout, montage compris
    python probe_959_grim_efficiency_predictive_guidance.py --runner <id>   # sur un runner monte

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import hexgeo                                                            # noqa: E402
import rl_duel as L                                                      # noqa: E402

BOARD = "MC1_67"
SEED = 777
#: (visualId, tuile) -- la geometrie est CALCULEE (cf. l'en-tete), pas cherchee a l'oeil.
P_PLACE = {"votanUthar": (0, 0), "votanMemnyr": (0, 2),
           "ultraTitus": (1, 2), "ultraCalgar": (4, 0)}
A_PLACE = [("orksNob", (0, 1)), ("orksNob", (1, 0))]
CARRIER_GE = "votanUthar"          # source GrimEfficiency
CARRIER_PG = "votanMemnyr"         # source PredictiveGuidance
#: tolerance de la confrontation de prediction (meme regime que #926 : la borne est ENTIERE).
TOL = 1

_LOGS = HERE.parent.parent / "logs"
STATE = _LOGS / "st959_probe.json"
SEED_BC = _LOGS / "seed_bc_959_probe.json"


def rpc(name, args, timeout=90, tolerate=False):
    sid = L._resolve_session()
    try:
        return L._rpc(sid, name, [args], timeout=timeout)["result"]
    except Exception as exc:                                   # noqa: BLE001
        if tolerate:
            return None
        raise SystemExit("RPC %s KO : %s" % (name, exc))


def ids_by_visual(dec) -> dict:
    """`visualId` -> liste des entity-ids (les DEUX clones `orksNob` en portent deux)."""
    out: dict = {}
    for u in (dec.get("units") or []):
        out.setdefault(u.get("visualId") or u.get("unitId"), []).append(u.get("id"))
    return out


# ------------------------------------------------------------------ etage 0 : le MONTAGE
def build() -> int:
    _LOGS.mkdir(parents=True, exist_ok=True)
    import catalog_inject as CI
    CI.write_augmented_seed_bc(str(SEED_BC), [CARRIER_GE, CARRIER_PG])
    argv = ["build", "--seed", str(SEED), "--board", BOARD,
            "--state-file", str(STATE), "--seed-bc", str(SEED_BC),
            "--p-units", ",".join(P_PLACE), "--a-units", ",".join(v for v, _ in A_PLACE)]
    for vid, (c, r) in P_PLACE.items():
        argv += ["--place", "%s:%d,%d" % (vid, c, r)]
    for vid, (c, r) in A_PLACE:
        argv += ["--a-place", "%s:%d,%d" % (vid, c, r)]
    p = subprocess.run([sys.executable, str(HERE / "rl_duel.py")] + argv,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print(p.stdout[-2500:])
        print(p.stderr[-1500:])
        raise SystemExit("[0] MONTAGE KO -- build rc=%d" % p.returncode)
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def etage1(dec) -> dict:
    """Les SIX distances du montage. Un montage non conforme ne mesure RIEN -- on le DIT."""
    by_vis = ids_by_visual(dec)
    # `decisionView.units[].pos` = `{col, row}` (et non deux champs plats).
    pos = {u.get("id"): ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
           for u in (dec.get("units") or [])}
    u = by_vis[CARRIER_GE][0]
    m = by_vis[CARRIER_PG][0]
    c = by_vis["ultraTitus"][0]
    d_ = by_vis["ultraCalgar"][0]
    foes = sorted(by_vis["orksNob"])
    dist = hexgeo.distance
    # E = celui des deux clones qui est DANS l'aura d'Ammuk ; F = l'autre.
    dm = {f: dist(pos[m], pos[f]) for f in foes}
    e = min(foes, key=lambda f: dm[f])
    f = max(foes, key=lambda f: dm[f])
    r = {"U": u, "M": m, "C": c, "D": d_, "E": e, "F": f, "pos": pos,
         "d_UM": dist(pos[u], pos[m]), "d_UC": dist(pos[u], pos[c]),
         "d_UD": dist(pos[u], pos[d_]), "d_ME": dm[e], "d_MF": dm[f],
         "d_UE": dist(pos[u], pos[e]), "d_UF": dist(pos[u], pos[f])}
    ok = (r["d_UM"] <= 2 and r["d_UC"] <= 2 and r["d_UD"] > 2
          and r["d_ME"] <= 2 and r["d_MF"] > 2 and r["d_UE"] == 1 and r["d_UF"] == 1)
    r["ok"] = bool(ok)
    print("[1] U=u%d M=u%d C=u%d D=u%d E=u%d F=u%d" % (u, m, c, d_, e, f))
    print("[1] d(U,M)=%d d(U,C)=%d d(U,D)=%d | d(M,E)=%d d(M,F)=%d | d(U,E)=%d d(U,F)=%d -> %s"
          % (r["d_UM"], r["d_UC"], r["d_UD"], r["d_ME"], r["d_MF"], r["d_UE"], r["d_UF"],
             "CONFORME" if ok else "NON CONFORME"))
    return r


# ------------------------------------------------- etage 2 : QUI PORTE QUOI (canal actif-only)
GE_ARMOR, GE_PIERCE = "GrimEfficiency_ExtraArmor", "GrimEfficiency_ExtraPierce"
PG_ALL = ("PredictiveGuidance_Melee", "PredictiveGuidance_Ranged", "PredictiveGuidance_ExtraHits")
STANCE_HOSTILE = "PrioritisedEfficiency_HostileAcquisition_Stance"
STANCE_FORTIFY = "PrioritisedEfficiency_FortifyTakeover_Stance"


def etage2(dec, g) -> dict:
    """Le canal `decisionView.effects` est ACTIF-ONLY : il dit donc DIRECTEMENT quelle stance est
    en cours, et il doit ne publier QU'UNE des deux auras de GrimEfficiency."""
    eff = {}
    for u in (dec.get("units") or []):
        eff[u.get("id")] = sorted({e.get("name") for e in (u.get("effects") or [])})
    uid, mid = g["U"], g["M"]
    r = {
        "uthar": eff.get(uid, []),
        "ammuk": eff.get(mid, []),
        "foes": {f: eff.get(f, []) for f in (g["E"], g["F"])},
    }
    hostile = STANCE_HOSTILE in r["uthar"]
    fortify = STANCE_FORTIFY in r["uthar"]
    r["stance"] = "hostile" if hostile else ("fortify" if fortify else None)
    r["ge_armor"] = GE_ARMOR in r["uthar"]
    r["ge_pierce"] = GE_PIERCE in r["uthar"]
    r["pg_on_carrier"] = [n for n in PG_ALL if n in r["ammuk"]]
    r["pg_on_foes"] = sorted({n for v in r["foes"].values() for n in v if n.startswith("Predictive")})
    # L'aura PUBLIEE doit etre celle de la stance PUBLIEE -- et l'autre doit etre ABSENTE.
    r["partition_ok"] = ((hostile and r["ge_armor"] and not r["ge_pierce"])
                         or (fortify and r["ge_pierce"] and not r["ge_armor"]))
    r["ok"] = bool(r["partition_ok"] and len(r["pg_on_carrier"]) == 3 and not r["pg_on_foes"])
    print("[2] Uthar stance=%s ge_armor=%s ge_pierce=%s -> partition %s"
          % (r["stance"], r["ge_armor"], r["ge_pierce"], "OK" if r["partition_ok"] else "KO"))
    print("[2] Ammuk porte %d/3 des effets PredictiveGuidance ; ennemis en portent %d (attendu 0)"
          % (len(r["pg_on_carrier"]), len(r["pg_on_foes"])))
    return r


# ------------------------------- etage 3 : AURA STAT-MOD (GrimEfficiency) -- natif vs port
FIXED_ARMOR, EXTRA_PIERCE = 16, 26


def _native_statmods(rid) -> dict:
    out = rpc("statModSources", {"runnerId": rid})
    res = {}
    for u in (out.get("units") or []):
        mods = u.get("mods") or {}
        res[u.get("entityId")] = {
            FIXED_ARMOR: int((mods.get("fixedArmor") or {}).get("total") or 0),
            EXTRA_PIERCE: int((mods.get("extraPierce") or {}).get("total") or 0)}
    return res


def _port_statmods(rid) -> dict:
    """Le MEME etat, cote port : `refresh_aura_stat_modifiers` (mirror `RefreshEffectsOperation`
    volet PROJETE) puis lecture des modifications SOUS LA CLE D'AURA -- on ne lit pas le total,
    qui contient aussi ce que la capture portait deja."""
    from engine.runner.snapshot import load_state
    from engine.runner.operations.aura_stat_mods import refresh_aura_stat_modifiers
    from engine.runner.components import StatsComponent
    dec = rpc("decisionView", {"runnerId": rid})
    ob = rpc("observeBattle", {"runnerId": rid})
    snap = rpc("combatSnapshot", {"runnerId": rid})
    state = load_state(dec, ob, snap)
    refresh_aura_stat_modifiers(state)
    res = {}
    for uid, ent in state.entities.items():
        sc = ent.get_component(StatsComponent)
        us = sc.ctx.stats if (sc is not None and sc.ctx is not None) else None
        if us is None:
            continue
        row = {}
        for st in (FIXED_ARMOR, EXTRA_PIERCE):
            comp = us.components.get(st)
            per = dict(getattr(comp.modification, "per_source", {}) or {}) if comp else {}
            row[st] = sum(v for k, v in per.items()
                          if isinstance(k, tuple) and k and k[0] == "aura_statmod")
        res[uid] = row
    return res


def etage3(rid, g) -> dict:
    nat, port = _native_statmods(rid), _port_statmods(rid)
    rows, bad = [], []
    labels = {g["U"]: "U (SOURCE, exclue)", g["M"]: "M d<=2", g["C"]: "C d<=2",
              g["D"]: "D d>2", g["E"]: "E ennemi", g["F"]: "F ennemi"}
    for uid, lab in labels.items():
        n, p = nat.get(uid, {}), port.get(uid, {})
        for st in (FIXED_ARMOR, EXTRA_PIERCE):
            nv, pv = int(n.get(st) or 0), int(p.get(st) or 0)
            rows.append({"uid": uid, "label": lab, "stat": st, "natif": nv, "port": pv})
            if nv != pv:
                bad.append("u%d %s stat=%d natif=%d port=%d" % (uid, lab, st, nv, pv))
    beneficiaires = [r for r in rows if r["stat"] == FIXED_ARMOR and r["natif"] > 0]
    print("[3] %d ligne(s), %d ecart(s) ; %d beneficiaire(s) natif(s) FixedArmor"
          % (len(rows), len(bad), len(beneficiaires)))
    for r in rows:
        if r["natif"] or r["port"]:
            print("[3]   u%-3d %-20s stat=%-3d natif=%-6d port=%-6d" %
                  (r["uid"], r["label"], r["stat"], r["natif"], r["port"]))
    for b in bad:
        print("[3] ECART %s" % b)
    return {"rows": rows, "bad": bad, "beneficiaires": beneficiaires}


# ------------------------------ etage 4 : PREDICTION (PredictiveGuidance) -- natif vs port
def _scene(rid, dec):
    from engine.playbook import scene as SC
    from engine.playbook.scene import Scene
    predictor = SC.build_predictor(lambda m, b, t: rpc(m, b, t), rid)
    if predictor is None:
        raise SystemExit("[4] combatSnapshot KO (MONTAGE)")
    sctx = SC.step_context(predictor, dec)
    return Scene.from_predictor_sctx(predictor, sctx, None), sctx


def _rows_pred(dec, scene, sctx) -> list:
    from engine.playbook import prediction
    pos_by_id = sctx["pos_by_id"]
    out = []
    for ap in (dec.get("attackPlans") or []):
        a_id = ap.get("unitId")
        norm = {ab.get("id") for u in (dec.get("units") or []) if u.get("id") == a_id
                for ab in (u.get("abilities") or []) if ab.get("kind") == "normal"}
        for ev in (ap.get("evals") or []):
            if norm and ev.get("abilityId") not in norm:
                continue
            for rk in (ev.get("ranked") or []):
                if rk.get("dmgMax") is None or rk.get("predOptimistic"):
                    continue
                tile = ((rk["col"], rk["row"]) if rk.get("col") is not None
                        else pos_by_id.get(a_id))
                off = prediction.make_normal_attack_predictions(
                    scene, a_id, ev.get("targetId"), tile)
                res = off.prediction.accurate_health_damage
                out.append({"att": a_id, "tgt": ev.get("targetId"), "tile": tile,
                            "oracle": (rk.get("dmgMin"), rk.get("dmgMax")),
                            "offline": (res.min, res.max)})
    return out


def etage4(rid, dec, g) -> dict:
    scene, sctx = _scene(rid, dec)
    rows = _rows_pred(dec, scene, sctx)
    bad = ["u%s -> u%s tuile=%s natif=%s port=%s"
           % (r["att"], r["tgt"], r["tile"], r["oracle"], r["offline"])
           for r in rows
           if abs((r["oracle"][0] or 0) - r["offline"][0]) > TOL
           or abs((r["oracle"][1] or 0) - r["offline"][1]) > TOL]
    # NON-DEGENERESCENCE : le bras « dedans » doit differer du bras « dehors » POUR L'ATTAQUANT
    # LoV, et etre IDENTIQUE pour les temoins -- sinon l'accord ne prouve rien.
    def _pair(att):
        ins = {r["tile"]: r["oracle"] for r in rows if r["att"] == att and r["tgt"] == g["E"]}
        out = {r["tile"]: r["oracle"] for r in rows if r["att"] == att and r["tgt"] == g["F"]}
        common = sorted(set(ins) & set(out))
        return [(t, ins[t], out[t]) for t in common]

    lov = _pair(g["U"])                      # Leagues of Votann, != source -> DOIT differer
    src = _pair(g["M"])                      # la SOURCE elle-meme      -> DOIT etre identique
    wit = _pair(g["C"]) + _pair(g["D"])      # ni LoV ni Mechanical     -> DOIT etre identique
    r = {"rows": rows, "bad": bad,
         "lov_differe": [x for x in lov if x[1] != x[2]],
         "src_identique": all(x[1] == x[2] for x in src) if src else None,
         "wit_identique": all(x[1] == x[2] for x in wit) if wit else None,
         "lov_pairs": lov, "src_pairs": src, "wit_pairs": wit}
    print("[4] %d tuile(s) candidate(s), %d ecart(s) (tolerance %d)" % (len(rows), len(bad), TOL))
    print("[4] attaquant LoV : %d paire(s) comparables, %d ou le bonus MORD %s"
          % (len(lov), len(r["lov_differe"]), [x for x in lov][:4]))
    print("[4] la SOURCE (Ammuk) : identique dedans/dehors = %s (%d paire(s))"
          % (r["src_identique"], len(src)))
    print("[4] temoins NI LoV NI Mechanical : identique dedans/dehors = %s (%d paire(s))"
          % (r["wit_identique"], len(wit)))
    for b in bad[:10]:
        print("[4] ECART %s" % b)
    return r


# ------------------------------------------------------------------- etage 5 : les MUTANTS
def etage5(rid, dec, g) -> dict:
    """Chaque mutation doit faire ROUGIR l'etage qu'elle vise. Un mutant VERT = temoin aveugle.

    Les mutations portent sur les CLASSES (attributs et methodes), jamais sur les mesures : c'est
    le port qu'on casse, pas l'oracle."""
    from engine.entities.effects import factory as F
    from engine.entities.effects.loki import votann as V

    def _e3_bad():
        return len(etage3(rid, g)["bad"])

    def _e4_bad():
        return len(etage4(rid, dec, g)["bad"])

    mutants = {}

    # M1 -- la stance n'est plus lue : les DEUX auras de GrimEfficiency contribuent.
    saved = V._GrimEfficiencyAuraStatModEffect.is_active
    try:
        V._GrimEfficiencyAuraStatModEffect.is_active = lambda self, unit_state=None: True
        mutants["M1 is_active neutralisee (GE)"] = _e3_bad() > 0
    finally:
        V._GrimEfficiencyAuraStatModEffect.is_active = saved

    # M2 -- les deux stances ECHANGEES entre les deux classes.
    a, b = (V.GrimEfficiencyExtraArmorEffect._STANCE, V.GrimEfficiencyExtraPierceEffect._STANCE)
    try:
        V.GrimEfficiencyExtraArmorEffect._STANCE = b
        V.GrimEfficiencyExtraPierceEffect._STANCE = a
        mutants["M2 stances echangees (GE)"] = _e3_bad() > 0
    finally:
        V.GrimEfficiencyExtraArmorEffect._STANCE = a
        V.GrimEfficiencyExtraPierceEffect._STANCE = b

    # M3 -- le mauvais StatType (ExtraPierceMelee 21 au lieu d'ExtraPierce 26 / FixedArmor).
    st = V.GrimEfficiencyExtraArmorEffect._STAT
    try:
        V.GrimEfficiencyExtraArmorEffect._STAT = 21
        mutants["M3 StatType faux (GE)"] = _e3_bad() > 0
    finally:
        V.GrimEfficiencyExtraArmorEffect._STAT = st

    # M4 -- PredictiveGuidance_Melee retire du registre.
    k = F.EFFECT_CLASSES.pop("PredictiveGuidance_Melee", None)
    try:
        mutants["M4 sans PredictiveGuidance_Melee"] = _e4_bad() > 0
    finally:
        if k is not None:
            F.EFFECT_CLASSES["PredictiveGuidance_Melee"] = k

    # M5 -- PredictiveGuidance_ExtraHits retire du registre.
    k = F.EFFECT_CLASSES.pop("PredictiveGuidance_ExtraHits", None)
    try:
        mutants["M5 sans PredictiveGuidance_ExtraHits"] = _e4_bad() > 0
    finally:
        if k is not None:
            F.EFFECT_CLASSES["PredictiveGuidance_ExtraHits"] = k

    # M6 -- le filtre `UnitFlag.Moved` INVERSE sur la moitie melee.
    rm = V.PredictiveGuidanceMeleeEffect._REQUIRE_MOVED
    try:
        V.PredictiveGuidanceMeleeEffect._REQUIRE_MOVED = not rm
        mutants["M6 filtre Moved inverse (PG melee)"] = _e4_bad() > 0
    finally:
        V.PredictiveGuidanceMeleeEffect._REQUIRE_MOVED = rm

    # M7 -- le gate de FACTION/MECANIQUE toujours vrai : les temoins recevraient le bonus.
    saved_bc = V._pg_bonus_condition
    try:
        V._pg_bonus_condition = lambda c, req: (c.get("att_id") is not None
                                                and c.get("att_id") != c.get("owner_id"))
        mutants["M7 gate faction neutralise (PG)"] = _e4_bad() > 0
    finally:
        V._pg_bonus_condition = saved_bc

    for name, red in mutants.items():
        print("[5] %-40s -> %s" % (name, "ROUGE (bon)" if red else "VERT (TEMOIN AVEUGLE)"))
    return {"mutants": mutants, "ok": all(mutants.values())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner monte")
    a = ap.parse_args()
    rid = a.runner if a.runner is not None else build()
    print("[0] runner=%d" % rid)
    try:
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
        g = etage1(dec)
        if not g["ok"]:
            print("[0] MONTAGE NON CONFORME -- rien n'est conclu")
            return 2
        e2 = etage2(dec, g)
        e3 = etage3(rid, g)
        e4 = etage4(rid, dec, g)
        e5 = etage5(rid, dec, g)
        ok = (e2["ok"] and not e3["bad"] and not e4["bad"] and e4["lov_differe"]
              and e4["src_identique"] and e4["wit_identique"] and e5["ok"])
        print("[=] VERDICT : %s" % ("OK" if ok else "KO"))
        return 0 if ok else 1
    finally:
        if a.runner is None and not a.keep:
            subprocess.run([sys.executable, str(HERE / "rl_duel.py"), "dispose",
                            "--runner", str(rid), "--state-file", str(STATE)],
                           capture_output=True, text=True)


if __name__ == "__main__":
    raise SystemExit(main())
