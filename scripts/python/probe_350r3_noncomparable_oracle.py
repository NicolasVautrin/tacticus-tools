#!/usr/bin/env python
"""Probe #350-r3 (a) -- l'ORACLE de la face NonComparable.

LA QUESTION
-----------
`#350-r3` mur (a) : les playbooks NonComparable rendent 0 event a `aiPlaybookPredict`. Existe-t-il
un point d'observation natif qui rende la prediction de degat d'un playbook NonComparable ?

CE QUE LE DECOMPILE ET LA TABLE VERSIONNEE DISENT (`rnca9r7q6c`)
---------------------------------------------------------------
1. `ComparablePlaybook`1` et `NonComparablePlaybook`1` sont deux enfants FRERES de `Playbook`1`
   (colonne parent de `data/symbols/<build>/frida/classes.tsv`). Les quatre `Make*Predictions` ne
   sont declarees QUE sur la branche Comparable
   (`ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$MakeDamagePredictions` + 3 soeurs).
   `NonComparablePlaybooku003C...u003E` ne declare que `$$EvaluateInternal`,
   `$$GenerateBucketWithActionForEveryEligibleTarget`, `$$GenerateBucketWithMultipleStrategies`.
   => sur un NonComparable, `playbook-predict.ts::makeDamagePredictions` ne RESOUT rien :
   `makeArity 0`, `listNull true`, `count -1`. Le "0 event" est la REPONSE JUSTE, pas un trou.

2. Mais la PREDICTION EXISTE. Les deux surcharges "triplet" de
   `Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent` appellent
   `IBattleQuery` slot 0x28 (`GetAttackPrediction`) puis
   `IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor` avant de scorer. Un playbook NonComparable
   construit donc le MEME `ProbableDamageEvent` qu'un Comparable -- il le CONSOMME au lieu de le
   RENDRE. D'ou l'ancrage du capteur `ncPlaybookPredict` (`frida/hooks/features/ai-step/
   rpc-nc-predict.ts`) sur ce ctor. Detail : `docs/rl/case-350r3-oracle-noncomparable.md`.

CE QUE CE PROBE MESURE
----------------------
  etape 0 (OFFLINE, aucune plateforme requise) : la STRUCTURE. Parents des playbooks, exclusivite
          des `Make*Predictions` sur la branche Comparable. C'est ce qui rend le "0 event" JUSTE.
  etape 1 (LIVE, aucun capteur requis) : la VALEUR DE RETOUR d'`aiPlaybookPredict` sur les quatre
          abilities du residu. La doctrine impose de trancher par le RETOUR, pas par le silence :
          on exige `makeArity == 0` ET le bon `playbookClass` (sans quoi `fallbackToDefault` aurait
          rendu le playbook d'attaque normale, et le zero n'accuserait pas la bonne classe).
          ⚠ Le caster n'importe PAS ici : `LoadPlaybook` charge par ABILITY et la resolution de
          methode echoue AVANT tout usage du caster. C'est une propriete de la CLASSE du playbook.
  etape 2 (LIVE, aucun capteur requis) : `ncEvaluate` (#46) rend-il une utilite pour la face NC ?
          C'est le verrou de NON-VACUITE : "0 event" ne doit pas se lire "rien ne se passe".
  etape 3 (LIVE, CAPTEUR REQUIS) : `ncPlaybookPredict`. D'abord son VERROU sur une ability
          COMPARABLE (`via=makeDamagePredictions` : la capture doit EGALER la liste rendue -- preuve
          que le capteur lit la bonne struct sur une face deja connue), puis `via=evaluate` sur les
          NC. Absent du bundle => SKIP NOMME, jamais un zero muet.

⚠ LE MONTAGE DOIT ATTEINDRE LE REGIME, ET LE PROUVER (#356)
-----------------------------------------------------------
`1202 VigilanceEternal` porte une PRECONDITION GEOMETRIQUE, lue au decompile dans
`IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$GetDynamicInvalidTargetReason` :
la cible est eligible si (a) ses tuiles sont ADJACENTES a celles du caster, ou (b) le selecteur
`IdunBattleLogic.Entities.DSLSelectors$$TilesUnitCanMoveToChargeTarget(caster, casterTiles, target,
movementRange = GetNumberConstant(0x16))` rend >= 1 tuile ; sinon il rend le flag `0x8000000`
(= `TargetIsInRange`). Aux positions de SPAWN de `MC1_67` aucune cible ne satisfait cela : le bucket
vide est alors la REPONSE JUSTE du natif, pas un trou de port. Le probe DOIT donc separer
  (a) MONTAGE non atteint  -> NON CONFRONTE, il le DIT ; ce n'est PAS un echec ;
  (b) PORT / HARNAIS       -> precondition PROUVEE et capture NULLE -> ECHEC.

Ce que la preuve N'EST PAS : `ncEvaluate.hvt` (`IBattleQuery.HasValidTargets`, slot 0x3f) rendait
**true aux 13/13 positions** du montage de spawn ou l'eligibilite etait VIDE (mesure 2026-07-31) --
ce gate ne traverse pas `GetDynamicInvalidTargetReason`. La preuve utilisee ici est
`abilityTargets` (`fromHere`/`targets` NON VIDES) confirmee par `abilityReason` (`targetReason.hex
== 0x0` au lieu de `0x8000000`), c.-a-d. exactement le flag du decompile.

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_350r3_noncomparable_oracle.py --offline
    python probe_350r3_noncomparable_oracle.py
    python probe_350r3_noncomparable_oracle.py --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]
SYMBOLS = ROOT / "data" / "symbols"          # entree VERSIONNEE (cf. CLAUDE.md invariant 3)

# --- FIXTURES NOMMEES (jamais de montage inline) ------------------------------------------------

# Les quatre abilities du residu #350-r3 (a), avec la classe de playbook attendue.
_FIXTURE_NC_ABILITIES = (
    (1132, "KillMaimBurn", "KillMaimBurnPlaybook"),
    (1111, "LivingBatteringRam", "LivingBatteringRamPlaybook"),
    (1173, "ArcScourge", "ArcScourgePlaybook"),
    (1202, "VigilanceEternal", "VigilanceEternalPlaybook"),
)

# Montage de l'etape 1 : DELIBEREMENT quelconque. `LoadPlaybook` charge par ABILITY, donc le
# caster n'entre pas dans le verdict ; le nommer evite de laisser croire qu'il le ferait.
_FIXTURE_RETURN = {
    "board": "MC1_67", "seed": 35031, "rank": 17,
    "p_units": "astraBullgryn,ultraTitus", "a_units": "necroWarden,necroWarden",
}

# Montage des etapes 2 et 3-NC : `custoKyrus` (Tyrith) porte 1202 VigilanceEternal, seule des
# quatre a avoir A LA FOIS un porteur lineup present au seed BC et un playbook NC PORTE cote
# Python (`engine/playbook/noncomparable/vigilance_eternal.py`).
_FIXTURE_NC = {
    "board": "MC1_67", "seed": 35032, "rank": 17,
    "caster": "custoKyrus", "victim": "necroWarden",
    "p_units": "custoKyrus,astraBullgryn", "a_units": "necroWarden,ultraTitus",
    "ability": 1202,
}

# Montage du VERROU de l'etape 3 : une ability COMPARABLE dont le port est deja confronte par
# `probe_344` (meme couple caster/ability que son montage par defaut).
_FIXTURE_LOCK = {
    "board": "MC1_67", "seed": 35033, "rank": 17,
    "caster": "deathBlightlord", "victim": "necroWarden",
    "p_units": "deathBlightlord,astraBullgryn", "a_units": "necroWarden,ultraTitus",
    "ability": 1042,
}

_MAKE_PREDICTIONS = ("MakeDamagePredictions", "MakeHealPredictions",
                     "MakeEffectPredictions", "MakeRepairPredictions")


# --- etape 0 : OFFLINE, la structure ------------------------------------------------------------

def _build_hash() -> str:
    return (SYMBOLS / "CURRENT").read_text(encoding="utf-8").strip()


def _parents(build: str) -> "dict[str, str]":
    """{classe: parent} depuis `data/symbols/<build>/frida/classes.tsv` (colonnes
    `nom\\ttaille\\tparent\\t...`, en-tete de provenance en 1re ligne)."""
    out: "dict[str, str]" = {}
    path = SYMBOLS / build / "frida" / "classes.tsv"
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith("#!"):
            continue
        cols = line.split("\t")
        if len(cols) >= 3:
            out[cols[0]] = cols[2]
    return out


def _ghidra_symbols(build: str) -> "list[str]":
    path = SYMBOLS / build / "ghidra" / "functions.tsv"
    names = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        cols = line.split("\t")
        if len(cols) >= 2:
            names.append(cols[1])
    return names


def step0_structure(verbose: bool = True) -> dict:
    build = _build_hash()
    par = _parents(build)
    syms = _ghidra_symbols(build)

    cmp_cls = "IdunBattle.AI.Playbook.ComparablePlaybook`1"
    nc_cls = "IdunBattle.AI.Playbook.NonComparablePlaybook`1"
    pb_cls = "IdunBattle.AI.Playbook.Playbook`1"

    siblings = (par.get(cmp_cls) == pb_cls and par.get(nc_cls) == pb_cls)
    n_nc = sum(1 for v in par.values() if v == nc_cls)
    n_cmp = sum(1 for v in par.values() if v == cmp_cls)

    # Exclusivite des Make*Predictions : sur la branche Comparable oui, sur la NC aucune.
    # ⚠ On lit la table GHIDRA : les generiques pleinement partages sont ABSENTS du dump frida
    # (methodPointer = un thunk), cf. CLAUDE.md / case-259.
    cmp_gen = "IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$"
    nc_gen = "IdunBattle.AI.Playbook.NonComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$"
    on_cmp = [m for m in _MAKE_PREDICTIONS if (cmp_gen + m) in syms]
    on_nc = [m for m in _MAKE_PREDICTIONS if (nc_gen + m) in syms]
    nc_members = sorted(s.split("$$")[-1] for s in syms if s.startswith(nc_gen))

    # Les quatre playbooks du residu sont-ils bien NonComparable ?
    fixtures = []
    for aid, name, pbname in _FIXTURE_NC_ABILITIES:
        hits = [k for k in par if k.rsplit(".", 1)[-1] == pbname]
        parent = par.get(hits[0]) if hits else None
        fixtures.append({"ability": aid, "name": name, "playbook": pbname,
                         "found": bool(hits), "parent": parent,
                         "is_nc": parent == nc_cls})

    ok = bool(siblings and on_cmp == list(_MAKE_PREDICTIONS) and not on_nc
              and all(f["is_nc"] for f in fixtures))

    if verbose:
        print("[350-r3/0] build = %s (data/symbols/CURRENT)" % build)
        print("  Comparable et NonComparable FRERES sous Playbook`1 : %s" % siblings)
        print("    parent(ComparablePlaybook`1)    = %s" % par.get(cmp_cls))
        print("    parent(NonComparablePlaybook`1) = %s" % par.get(nc_cls))
        print("  classes de parent direct : NonComparable=%d  Comparable=%d" % (n_nc, n_cmp))
        print("  Make*Predictions sur la branche Comparable    : %s" % (on_cmp or "AUCUNE"))
        print("  Make*Predictions sur la branche NonComparable : %s" % (on_nc or "AUCUNE"))
        print("  membres propres de NonComparablePlaybook`1 : %s" % ", ".join(nc_members))
        for f in fixtures:
            print("  %-5d %-20s -> %-28s parent=%s"
                  % (f["ability"], f["name"], f["playbook"],
                     (f["parent"] or "INTROUVABLE").rsplit(".", 1)[-1]))
        print("  -> %s" % ("OK" if ok else "ECHEC"))

    return {"ok": ok, "build": build, "siblings": siblings,
            "n_noncomparable": n_nc, "n_comparable": n_cmp,
            "make_on_comparable": on_cmp, "make_on_noncomparable": on_nc,
            "nc_members": nc_members, "fixtures": fixtures}


# --- plomberie LIVE ------------------------------------------------------------------------------

def _rpc_mod():
    from rl_collect_batch import _resolve_session, _rpc          # noqa: E402
    return _resolve_session, _rpc


def _r(rpc, sid, m, b, t=90):
    return (rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, fx: dict) -> int:
    """`rl_duel build` -- board CHOISI (runner.md sec.2), state-file ABSOLU dans logs/."""
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(fx["seed"]),
           "--state-file", str(state_file), "--board", fx["board"], "--rank", str(fx["rank"]),
           "--p-units", fx["p_units"], "--a-units", fx["a_units"], "--no-ai"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _units(rpc, sid, rid) -> "list[dict]":
    dv = _r(rpc, sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def _pick(units, visual) -> "int | None":
    u = next((x for x in units if x.get("visualId") == visual), None)
    return int(u["id"]) if u else None


# --- etape 1 : la VALEUR DE RETOUR d'aiPlaybookPredict -------------------------------------------

def step1_return_value(rpc, sid, logs: Path, verbose: bool = True) -> dict:
    sf = logs / "p350r3_return.json"
    rid = None
    rows = []
    try:
        rid = _build(sf, _FIXTURE_RETURN)
        units = _units(rpc, sid, rid)
        cid = _pick(units, "astraBullgryn")
        tid = _pick(units, "necroWarden")
        if cid is None or tid is None:
            return {"ok": False, "error": "montage : caster/cible absents du build"}
        for aid, name, pbname in _FIXTURE_NC_ABILITIES:
            r = _r(rpc, sid, "aiPlaybookPredict",
                   {"runnerId": rid, "unitId": cid, "targetId": tid, "abilityType": aid}, 120)
            cls = (r.get("playbookClass") or "")
            rows.append({
                "ability": aid, "name": name, "playbookClass": cls or None,
                # `fallbackToDefault=true` peut rendre le playbook d'attaque NORMALE : sans ce
                # controle, un `makeArity 0` n'accuserait pas forcement la classe visee.
                "class_ok": cls == pbname,
                "makeArity": r.get("makeArity"), "listNull": r.get("listNull"),
                "count": r.get("count"), "retClass": r.get("retClass"),
                "nEvents": len(r.get("events") or []),
                "error": r.get("error"),
            })
    finally:
        if rid is not None:
            _r(rpc, sid, "disposeRunner", {"runnerId": rid}, 30)

    ok = bool(rows) and all(x["class_ok"] and x["makeArity"] == 0 and x["listNull"] is True
                            and x["nEvents"] == 0 for x in rows)
    if verbose:
        print("\n[350-r3/1] VALEUR DE RETOUR d'aiPlaybookPredict (montage %s)"
              % _FIXTURE_RETURN["p_units"])
        for x in rows:
            print("  %-5d %-20s class=%-28s makeArity=%s listNull=%s count=%s events=%d"
                  % (x["ability"], x["name"], (x["playbookClass"] or "?"),
                     x["makeArity"], x["listNull"], x["count"], x["nEvents"]))
        print("  attendu : classe = le playbook NC vise, makeArity = 0, listNull = true")
        print("  -> %s" % ("OK" if ok else "ECHEC"))
    return {"ok": ok, "rows": rows}


# --- etape 2 : ncEvaluate, la face NC est-elle VIVANTE ? -----------------------------------------

def step2_nc_evaluate(rpc, sid, logs: Path, verbose: bool = True) -> dict:
    sf = logs / "p350r3_nceval.json"
    rid = None
    out = {}
    try:
        rid = _build(sf, _FIXTURE_NC)
        units = _units(rpc, sid, rid)
        cid = _pick(units, _FIXTURE_NC["caster"])
        if cid is None:
            return {"ok": False, "error": "montage : %s absent du build" % _FIXTURE_NC["caster"]}
        r = _r(rpc, sid, "ncEvaluate",
               {"runnerId": rid, "unitId": cid, "abilityType": _FIXTURE_NC["ability"],
                "sweep": True}, 180)
        positions = r.get("positions") or []
        scored = [p for p in positions if isinstance(p.get("util"), (int, float))]
        out = {"ok": bool(r.get("ok")) and bool(scored),
               "playbookClass": r.get("playbookClass"), "evalName": r.get("evalName"),
               "nPositions": len(positions), "nScored": len(scored),
               "utils": [round(float(p["util"]), 4) for p in scored[:8]],
               "error": r.get("error")}
    finally:
        if rid is not None:
            _r(rpc, sid, "disposeRunner", {"runnerId": rid}, 30)
    if verbose:
        print("\n[350-r3/2] ncEvaluate sur %s / ability %d"
              % (_FIXTURE_NC["caster"], _FIXTURE_NC["ability"]))
        print("  playbook=%s eval=%s positions=%s scorees=%s"
              % (out.get("playbookClass"), out.get("evalName"),
                 out.get("nPositions"), out.get("nScored")))
        print("  utilites (8 premieres) : %s" % out.get("utils"))
        print("  -> %s" % ("OK" if out.get("ok") else "ECHEC"))
    return out


# --- etape 3 : le CAPTEUR ------------------------------------------------------------------------

def _same_events(a: "list[dict]", b: "list[dict]") -> bool:
    key = lambda e: (e.get("targetId"), e.get("healthDmgMin"), e.get("healthDmgMax"),   # noqa: E731
                     e.get("appliedHits"))
    return [key(x) for x in a] == [key(x) for x in b]


def step3_capteur(rpc, sid, logs: Path, verbose: bool = True) -> dict:
    """VERROU d'abord (ability COMPARABLE : capture == liste rendue), puis les NC."""
    sf = logs / "p350r3_capteur.json"
    rid = None
    lock = {}
    nc_rows = []
    try:
        rid = _build(sf, _FIXTURE_LOCK)
        units = _units(rpc, sid, rid)
        cid = _pick(units, _FIXTURE_LOCK["caster"])
        tid = _pick(units, _FIXTURE_LOCK["victim"])
        if cid is None or tid is None:
            return {"ok": False, "error": "montage verrou : caster/cible absents"}
        r = _r(rpc, sid, "ncPlaybookPredict",
               {"runnerId": rid, "unitId": cid, "targetId": tid,
                "abilityType": _FIXTURE_LOCK["ability"], "via": "makeDamagePredictions"}, 120)
        if not r or (r.get("error") or "").startswith("unknown rpc") or r.get("ok") is None:
            return {"skipped": "capteur ncPlaybookPredict absent du bundle -- reinject a planifier",
                    "raw": r}
        cap = r.get("captured") or []
        ret = r.get("returned") or []
        lock = {"playbookClass": r.get("playbookClass"),
                "capturedCount": len(cap), "returnedCount": len(ret),
                "identical": _same_events(cap, ret),
                "nonEmpty": len(cap) > 0, "error": r.get("error")}
    finally:
        if rid is not None:
            _r(rpc, sid, "disposeRunner", {"runnerId": rid}, 30)

    sf2 = logs / "p350r3_capteur_nc.json"
    rid2 = None
    try:
        rid2 = _build(sf2, _FIXTURE_NC)
        units = _units(rpc, sid, rid2)
        cid = _pick(units, _FIXTURE_NC["caster"])
        if cid is not None:
            r = _r(rpc, sid, "ncPlaybookPredict",
                   {"runnerId": rid2, "unitId": cid,
                    "abilityType": _FIXTURE_NC["ability"], "via": "evaluate"}, 180)
            cap = r.get("captured") or []
            nc_rows.append({"ability": _FIXTURE_NC["ability"],
                            "playbookClass": r.get("playbookClass"),
                            "capturedCount": len(cap),
                            "first": cap[0] if cap else None,
                            "bucketUtil": r.get("bucketUtil"), "error": r.get("error")})
    finally:
        if rid2 is not None:
            _r(rpc, sid, "disposeRunner", {"runnerId": rid2}, 30)

    ok = bool(lock.get("identical") and lock.get("nonEmpty")
              and nc_rows and nc_rows[0]["capturedCount"] > 0)
    if verbose:
        print("\n[350-r3/3] capteur ncPlaybookPredict")
        print("  VERROU (%s / %d, COMPARABLE) : capture=%s rendue=%s identiques=%s"
              % (_FIXTURE_LOCK["caster"], _FIXTURE_LOCK["ability"],
                 lock.get("capturedCount"), lock.get("returnedCount"), lock.get("identical")))
        for x in nc_rows:
            print("  NC %-5d %-28s capture=%d util=%s"
                  % (x["ability"], (x["playbookClass"] or "?"), x["capturedCount"],
                     x.get("bucketUtil")))
            if x["first"]:
                print("     1er event : %s" % json.dumps(x["first"], sort_keys=True)[:220])
        print("  -> %s" % ("OK" if ok else "ECHEC"))
    return {"ok": ok, "lock": lock, "nc": nc_rows}


def run(offline: bool = False, verbose: bool = True) -> dict:
    out = {"step0": step0_structure(verbose)}
    if offline:
        out["live"] = "SKIP -- --offline"
        out["ok"] = out["step0"]["ok"]
        if verbose:
            print("\n=== VERDICT (offline) === structure : %s"
                  % ("OK" if out["ok"] else "ECHEC"))
        return out
    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    try:
        resolve_session, rpc = _rpc_mod()
        sid = resolve_session()
    except Exception as e:                                          # noqa: BLE001
        out["live"] = "NON CONFRONTE -- plateforme indisponible : %s" % e
        out["ok"] = None
        if verbose:
            print("\n[350-r3] LIVE NON CONFRONTE : %s" % e)
            print("  (les etapes 1-3 exigent une session Frida ; l'etape 0 est offline)")
        return out
    out["step1"] = step1_return_value(rpc, sid, logs, verbose)
    out["step2"] = step2_nc_evaluate(rpc, sid, logs, verbose)
    out["step3"] = step3_capteur(rpc, sid, logs, verbose)
    parts = [out["step0"].get("ok"), out["step1"].get("ok"), out["step2"].get("ok")]
    if "skipped" in out["step3"]:
        out["ok"] = all(parts)
    else:
        out["ok"] = all(parts + [out["step3"].get("ok")])
    if verbose:
        print("\n=== VERDICT ===")
        print("  0 structure           : %s" % out["step0"].get("ok"))
        print("  1 valeur de retour    : %s" % out["step1"].get("ok"))
        print("  2 ncEvaluate (vie NC) : %s" % out["step2"].get("ok"))
        print("  3 capteur             : %s" % (out["step3"].get("skipped")
                                                or out["step3"].get("ok")))
        print("  -> %s" % ("OK" if out["ok"] else "ECHEC"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true",
                    help="etape 0 seule (structure) -- aucune plateforme requise")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(offline=a.offline)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
