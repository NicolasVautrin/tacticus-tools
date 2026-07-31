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
    # Aux tuiles de SPAWN de ce board le caster est a 10-11 hex des cibles : la precondition
    # geometrique (cf. en-tete) est FAUSSE, et le bucket vide est la reponse JUSTE du natif.
    # Le montage PILOTE donc les positions (`_approach`) jusqu'au regime, et le PROUVE.
    "max_rounds": 6,
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


# --- PILOTAGE DES POSITIONS + PREUVE DE PRECONDITION (#356) -------------------------------------
#
# Ces deux fonctions sont ce qui SEPARE les deux lectures d'une capture nulle. Elles sont donc
# appelees AVANT toute mesure d'oracle, et leur resultat est publie tel quel dans le verdict.

def _alive(rpc, sid, rid) -> "tuple[dict, list]":
    """`observeBattle` -- la seule vue qui porte (col,row) ET `teamId` pour TOUTES les unites."""
    o = _r(rpc, sid, "observeBattle", {"runnerId": rid}, 120)
    return o, [u for u in (o.get("units") or []) if not u.get("isDead")]


def _movable(rpc, sid, rid) -> dict:
    mv = _r(rpc, sid, "aiMovableTiles", {"runnerId": rid}, 120)
    return {int(e["unitId"]): [(t["col"], t["row"]) for t in (e.get("tiles") or [])]
            for e in (mv.get("units") or []) if e.get("unitId") is not None}


def _precondition(rpc, sid, rid, cid: int, ability: int, foes: list) -> dict:
    """La PREUVE que le regime est atteint, par DEUX voies independantes.

    * `abilityTargets` : `fromHere` = `AttackQuery.GetValidTargets(caster, position COURANTE,
      ability)` ; `targets` = l'union sur les tuiles de move. NON VIDE = au moins une cible passe
      le filtre d'eligibilite complet -- donc `BasePlaybook$$GetEligibleTargetsSelectable`, qui
      appelle le MEME slot (0x42), rendra une liste non vide.
    * `abilityReason` : le flag EXACT rendu par
      `IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$GetDynamicInvalidTargetReason` --
      `0x8000000` (`TargetIsInRange`) quand la charge est impossible, `0x0` quand elle l'est.

    ⚠ `ncEvaluate.hvt` (`HasValidTargets`, slot 0x3f) n'est PAS une preuve : mesure 2026-07-31,
    il valait `true` aux 13/13 positions d'un montage dont l'eligibilite etait VIDE."""
    at = _r(rpc, sid, "abilityTargets",
            {"runnerId": rid, "unitId": int(cid), "abilityType": int(ability)}, 120)
    ab = {}
    for u in (at.get("units") or []):
        for a in (u.get("abilities") or []):
            if a.get("abilityId") == int(ability):
                ab = a
    reasons = []
    for f in foes:
        rr = _r(rpc, sid, "abilityReason",
                {"runnerId": rid, "casterId": int(cid), "abilityType": int(ability),
                 "targetId": int(f["squadId"])}, 60)
        tr = rr.get("targetReason") or {}
        reasons.append({"targetId": int(f["squadId"]), "visualId": f.get("visualId"),
                        "hex": tr.get("hex"), "reasons": tr.get("reasons"),
                        "eligible": (tr.get("hex") in ("0x0", "0x0000000000000000", 0))})
    n_here = len(ab.get("fromHere") or [])
    n_move = len(ab.get("targets") or [])
    return {"reached": bool(n_here or n_move), "fromHereCount": n_here, "targetsCount": n_move,
            "fromHere": [t.get("targetId") for t in (ab.get("fromHere") or [])],
            "targets": [t.get("targetId") for t in (ab.get("targets") or [])],
            "reasons": reasons}


def _approach(rpc, sid, rid, fx: dict, verbose: bool = True) -> dict:
    """PILOTE LES POSITIONS jusqu'a ce que la precondition soit satisfaite AU DEBUT de mon tour.

    Les deux camps avancent l'un vers l'autre (le runner est monte `--no-ai`, donc AUCUN driver
    natif ne joue : chaque deplacement est le notre). On s'arrete des que `_precondition` est
    atteinte alors que c'est MON tour et que le caster n'a pas encore bouge -- c'est le seul etat
    ou l'oracle mesure la meme chose que le generateur natif (sweep depuis la position d'origine).

    Effet de bord VOULU : au round N le caster a `turnsStarted = N`, donc le gate natif
    `VigilanceEternalPlaybook$$ShouldEvaluate` (`GetStat(unit, 0xc) > 1`) est lui aussi franchi --
    le montage est dans le regime ou le generateur natif evaluerait REELLEMENT ce playbook."""
    import hexgeo
    cid = None
    for rnd in range(1, int(fx.get("max_rounds") or 6) + 1):
        o, us = _alive(rpc, sid, rid)
        caster = next((u for u in us if u.get("visualId") == fx["caster"]), None)
        if caster is None:
            return {"reached": False, "error": "caster %s absent du build" % fx["caster"]}
        cid = int(caster["squadId"])
        kpos = (caster["col"], caster["row"])
        foes = [u for u in us if u.get("teamId") != caster.get("teamId")]
        mine = [u for u in us if u.get("teamId") == caster.get("teamId")]
        my_turn = (o.get("currentPlayer") == caster.get("playerId"))
        pre = _precondition(rpc, sid, rid, cid, fx["ability"], foes)
        if verbose:
            print("  [approche] round %d cp=%s caster=%s dmin=%s fromHere=%d targets=%d"
                  % (rnd, o.get("currentPlayer"), kpos,
                     min([hexgeo.distance(kpos, (f["col"], f["row"])) for f in foes] or [-1]),
                     pre["fromHereCount"], pre["targetsCount"]))
        if my_turn and pre["reached"]:
            return {"reached": True, "rounds": rnd, "casterId": cid, "casterPos": kpos,
                    "foes": [(f.get("visualId"), f["col"], f["row"]) for f in foes],
                    "precondition": pre}
        # avancer : mon camp vers l'ennemi le plus proche, puis l'ennemi vers le caster
        mv = _movable(rpc, sid, rid)
        if my_turn:
            tgt = min(foes, key=lambda f: hexgeo.distance(kpos, (f["col"], f["row"])))
            tp = (tgt["col"], tgt["row"])
            tiles = mv.get(cid) or []
            if tiles:
                best = min(tiles, key=lambda t: hexgeo.distance(t, tp))
                _r(rpc, sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": cid, "to": {"col": best[0], "row": best[1]}}}, 90)
            _r(rpc, sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
        o2, us2 = _alive(rpc, sid, rid)
        caster = next((u for u in us2 if u.get("visualId") == fx["caster"]), None)
        if caster is None or o2.get("currentPlayer") == caster.get("playerId"):
            continue
        kpos = (caster["col"], caster["row"])
        mv2 = _movable(rpc, sid, rid)
        for f in [u for u in us2 if u.get("teamId") != caster.get("teamId")]:
            tiles = mv2.get(int(f["squadId"])) or []
            if not tiles:
                continue
            best = min(tiles, key=lambda t: hexgeo.distance(t, kpos))
            _r(rpc, sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": int(f["squadId"]),
                "to": {"col": best[0], "row": best[1]}}}, 90)
        _r(rpc, sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
        _ = mine
    return {"reached": False, "rounds": int(fx.get("max_rounds") or 6), "casterId": cid}


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

def step2_nc_evaluate(rpc, sid, rid: int, appr: dict, verbose: bool = True) -> dict:
    """`ncEvaluate` sur le montage PILOTE. Trois issues, jamais deux :
       * regime NON atteint      -> `regime_reached: False`, `ok: None` = NON CONFRONTE ;
       * regime atteint + scores -> OK ;
       * regime atteint + AUCUN score -> ECHEC (et c'est alors le port/harnais qui est en cause)."""
    out = {"regime_reached": bool(appr.get("reached")),
           "precondition": appr.get("precondition")}
    if not appr.get("reached"):
        out["ok"] = None
        out["skipped"] = ("MONTAGE NON ATTEINT en %s rounds -- precondition geometrique de "
                          "GetDynamicInvalidTargetReason non satisfaite" % appr.get("rounds"))
        if verbose:
            print("\n[350-r3/2] ncEvaluate -- %s" % out["skipped"])
            print("  -> NON CONFRONTE (ce n'est PAS un echec de port)")
        return out
    cid = int(appr["casterId"])
    r = _r(rpc, sid, "ncEvaluate",
           {"runnerId": rid, "unitId": cid, "abilityType": _FIXTURE_NC["ability"],
            "sweep": True}, 240)
    positions = r.get("positions") or []
    scored = [p for p in positions if isinstance(p.get("util"), (int, float))]
    # `hvt` est publie POUR MEMOIRE : il valait true 13/13 sur un montage a eligibilite VIDE.
    hvt_true = sum(1 for p in positions if p.get("hvt") is True)
    out.update({"ok": bool(r.get("ok")) and bool(scored),
                "playbookClass": r.get("playbookClass"), "evalName": r.get("evalName"),
                "nPositions": len(positions), "nScored": len(scored), "nHvtTrue": hvt_true,
                "utils": [round(float(p["util"]), 4) for p in scored[:8]],
                "error": r.get("error")})
    if verbose:
        print("\n[350-r3/2] ncEvaluate sur %s / ability %d (regime ATTEINT en %s rounds)"
              % (_FIXTURE_NC["caster"], _FIXTURE_NC["ability"], appr.get("rounds")))
        print("  playbook=%s eval=%s positions=%s scorees=%s hvt_true=%s"
              % (out.get("playbookClass"), out.get("evalName"),
                 out.get("nPositions"), out.get("nScored"), hvt_true))
        print("  utilites (8 premieres) : %s" % out.get("utils"))
        print("  -> %s" % ("OK" if out.get("ok") else "ECHEC"))
    return out


# --- etape 3 : le CAPTEUR ------------------------------------------------------------------------

def _same_events(a: "list[dict]", b: "list[dict]") -> bool:
    key = lambda e: (e.get("targetId"), e.get("healthDmgMin"), e.get("healthDmgMax"),   # noqa: E731
                     e.get("appliedHits"))
    return [key(x) for x in a] == [key(x) for x in b]


def step3_lock(rpc, sid, logs: Path, verbose: bool = True) -> dict:
    """VERROU d'AUTO-VALIDATION du capteur, sur une ability COMPARABLE : la capture (par le
    trampoline sur `ProbableDamageEvent$$.ctor`) doit EGALER la liste RENDUE par
    `MakeDamagePredictions`. C'est ce qui prouve que le capteur lit la BONNE struct."""
    sf = logs / "p350r3_capteur.json"
    rid = None
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
    lock["ok"] = bool(lock.get("identical") and lock.get("nonEmpty"))
    if verbose:
        print("\n[350-r3/3a] VERROU du capteur (%s / %d, COMPARABLE)"
              % (_FIXTURE_LOCK["caster"], _FIXTURE_LOCK["ability"]))
        print("  capture=%s rendue=%s identiques=%s"
              % (lock.get("capturedCount"), lock.get("returnedCount"), lock.get("identical")))
        print("  -> %s" % ("OK" if lock["ok"] else "ECHEC"))
    return lock


def step3_nc(rpc, sid, rid: int, appr: dict, verbose: bool = True) -> dict:
    """L'ORACLE NC lui-meme, sur le montage PILOTE. Memes trois issues qu'a l'etape 2 : un montage
    qui n'atteint pas le regime se DIT `NON CONFRONTE`, il ne rougit pas comme un bug de port."""
    out = {"regime_reached": bool(appr.get("reached")),
           "precondition": appr.get("precondition")}
    if not appr.get("reached"):
        out["ok"] = None
        out["skipped"] = "MONTAGE NON ATTEINT -- cf. etape 2"
        if verbose:
            print("\n[350-r3/3b] oracle NC -- %s" % out["skipped"])
            print("  -> NON CONFRONTE (ce n'est PAS un echec de port)")
        return out
    cid = int(appr["casterId"])
    r = _r(rpc, sid, "ncPlaybookPredict",
           {"runnerId": rid, "unitId": cid,
            "abilityType": _FIXTURE_NC["ability"], "via": "evaluate"}, 240)
    cap = r.get("captured") or []
    out.update({"ability": _FIXTURE_NC["ability"], "playbookClass": r.get("playbookClass"),
                "capturedCount": len(cap), "events": cap, "first": cap[0] if cap else None,
                "bucketUtil": r.get("bucketUtil"), "error": r.get("error"),
                "ok": bool(cap)})
    if verbose:
        print("\n[350-r3/3b] oracle NC %d %s (regime ATTEINT)"
              % (out["ability"], out.get("playbookClass") or "?"))
        print("  capture=%d bucketUtil=%s" % (out["capturedCount"], out.get("bucketUtil")))
        for e in cap[:4]:
            print("     event : tgt=%s dmg=[%s,%s] hits=%s prob=%s"
                  % (e.get("targetId"), e.get("healthDmgMin"), e.get("healthDmgMax"),
                     e.get("appliedHits"), e.get("probability")))
        if not cap:
            print("  !! capture NULLE alors que la precondition est PROUVEE -> lecture (b) :")
            print("     le triplet est consomme sans passer par ProbableDamageEvent$$.ctor")
        print("  -> %s" % ("OK" if out["ok"] else "ECHEC"))
    return out


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
    out["step3a"] = step3_lock(rpc, sid, logs, verbose)
    # UN SEUL runner pour les etapes 2 et 3b : le pilotage de positions coute plusieurs rounds,
    # et les deux oracles doivent parler du MEME etat.
    sf = logs / "p350r3_nc.json"
    rid = None
    try:
        rid = _build(sf, _FIXTURE_NC)
        if verbose:
            print("\n[350-r3] montage NC : pilotage des positions (board %s, %s vs %s)"
                  % (_FIXTURE_NC["board"], _FIXTURE_NC["p_units"], _FIXTURE_NC["a_units"]))
        appr = _approach(rpc, sid, rid, _FIXTURE_NC, verbose)
        out["approach"] = {k: v for k, v in appr.items() if k != "precondition"}
        out["step2"] = step2_nc_evaluate(rpc, sid, rid, appr, verbose)
        out["step3b"] = step3_nc(rpc, sid, rid, appr, verbose)
    finally:
        if rid is not None:
            _r(rpc, sid, "disposeRunner", {"runnerId": rid}, 30)

    # Verdict : un `None` (NON CONFRONTE) ne vaut ni OK ni ECHEC -- il est REPORTE tel quel.
    steps = {"0 structure": out["step0"].get("ok"),
             "1 valeur de retour": out["step1"].get("ok"),
             "3a verrou capteur": (out["step3a"].get("skipped") or out["step3a"].get("ok")),
             "2 ncEvaluate (vie NC)": out["step2"].get("ok"),
             "3b oracle NC": out["step3b"].get("ok")}
    hard = [v for v in steps.values() if v is not None and not isinstance(v, str)]
    out["ok"] = all(hard)
    out["not_confronted"] = [k for k, v in steps.items() if v is None or isinstance(v, str)]
    if verbose:
        print("\n=== VERDICT ===")
        for k, v in steps.items():
            print("  %-22s : %s" % (k, "NON CONFRONTE" if v is None else v))
        if out["not_confronted"]:
            print("  (non confronte : %s)" % ", ".join(out["not_confronted"]))
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
