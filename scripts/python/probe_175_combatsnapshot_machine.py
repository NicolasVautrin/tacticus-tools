#!/usr/bin/env python3
"""#175 -- BISSECTION : quelle sous-lecture de `combatSnapshot` empoisonne un runner MoW ?

SYMPTOME (mesure #162) : appeler `combatSnapshot` sur un runner contenant une entite
`EntityType.Machine` rend TOUTE pose d'effet ULTERIEURE un no-op SILENCIEUX -- l'action est
consommee, `applyAction` rend ok=true, le degat passe, mais `AddEffect` n'ecrit plus rien.

OU CA SORT, COTE NATIF (decompile, pas suppose) --
`IdunBattle.Operations.AddEffectOperation$$Execute` a TROIS sorties precoces :
  * cible nulle                         -> LOGUE
  * `UnitExtensions.HasFlag(cible, 6)`  -> LOGUE
  * interface slot +0x28 sur la DEFINITION de l'effet, argument = la CIBLE -> `return 0`, MUET.
Seule la 3e est silencieuse : c'est le gate d'immunite (`BaseEffect$$EntityIsImmuneToEffect`,
cf. #137). La corruption fait donc repondre « immunise » a ce gate.

METHODE -- on teste la SUFFISANCE, pas la necessite. Le RPC accepte `debugOnly: [...]` qui le
restreint aux sous-lectures nommees ; on part de l'ensemble VIDE (aucun invoke natif) et on
ajoute UNE sous-lecture a la fois. La premiere qui reproduit le no-op est la coupable. Tester
l'inverse (« tout sauf X ») ne distingue pas une cause unique de causes redondantes.

`readShields` n'a PAS de bouton : c'est une lecture memoire pure, sans `invokeMethod` -- elle
ne peut rien muter, l'exclure du protocole est un fait, pas un raccourci.

Chaque cas monte un runner NEUF : la corruption n'est pas reversible, un runner reutilise
donnerait un faux positif a tous les cas suivants.

RESULTAT DE LA BISSECTION (2026-07-28, session 8) -- `readNormalAttack` designee SEULE coupable
(les 5 autres sous-lectures POSENT normalement). Resserrage DANS readNormalAttack, via des
boutons temporaires depuis RETIRES (le correctif les a rendus caducs) :
    GetUnitPosition seul, sans boucle de prediction  -> POSE
    Machine exclue comme ATTAQUANTE                  -> NO-OP   <- le fix propose par la fiche
    Machine exclue comme CIBLE                       -> POSE    <- le fix REEL
Le vecteur est la Machine en CIBLE de `GetNormalAttackPrediction`. Le correctif que la fiche
#175 recommandait (gater sur l'attaquant) etait donc INERTE : applique sans mesure, il aurait
ferme la tache sans rien reparer.

DEPUIS LE CORRECTIF, CE PROBE EST UNE GARDE DE NON-REGRESSION : tous les cas doivent rendre
POSE. Un seul NO-OP = la prediction contre une Machine est revenue.

GENERALISATION -- tentee sur `aiPlaybookPredict` (unite predisant CONTRE la MoW) : NON
CONCLUANTE, le RPC repond `ok:false, "target <casterId> not found"`, il ne sait pas adresser
une MoW en cible. Ce n'est PAS une preuve d'innocuite, c'est une inatteignabilite. Le probe
declare donc `GEN-INERTE` plutot que de compter ce cas comme un succes -- sans cette garde,
un RPC qui n'a rien calcule est indiscernable du temoin sain.

Sortie ASCII pure (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

HOST = "http://127.0.0.1:8765"
PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
STATE = ROOT / "logs" / "_probe175.json"

BOARD = "C1_02"          # board MoW-capable (slot MachineOfWarPosition des deux cotes)
SEED = "4242"
CARRIER = "tauBroadside"  # MoW porteuse de 1160 HeavyRailRifle
ABILITY = 1160            # cast = PURE pose d'effets : 1334 sur la cible, 1333 sur la MoW

# Ensemble VIDE d'abord (temoin negatif), puis une sous-lecture a la fois.
CASES: list[tuple[str, list[str] | None]] = [
    ("SANS-SNAPSHOT", None),          # temoin POSITIF : la pose doit marcher
    ("only=[]", []),                  # temoin NEGATIF : snapshot sans aucun invoke natif
    ("only=stats", ["stats"]),
    ("only=ctrl", ["ctrl"]),
    ("only=turnsFinished", ["turnsFinished"]),
    ("only=normalAttack", ["normalAttack"]),
    ("only=unitConfig", ["unitConfig"]),
    ("only=abilityStates", ["abilityStates"]),
    ("COMPLET", ["stats", "ctrl", "turnsFinished", "normalAttack",
                 "unitConfig", "abilityStates"]),
]


def rpc(sid: int, method: str, args: dict, timeout_ms: int = 90000):
    body = json.dumps({"method": method, "args": [args], "timeout": timeout_ms}).encode()
    req = urllib.request.Request(f"{HOST}/api/scripts/{sid}/rpc", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_ms / 1000 + 30) as r:
        return json.loads(r.read()).get("result")


def live_session() -> int:
    with urllib.request.urlopen(f"{HOST}/api/admin/status", timeout=15) as r:
        st = json.loads(r.read())
    s = st.get("session")
    if not s or s.get("status") != "running":
        sys.exit("[error] aucune session Frida vivante -- injecter puis amorce")
    return int(s["id"])


def build() -> tuple[int | None, str]:
    if STATE.exists():
        STATE.unlink()
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
         "--p-units", "necroDestroyer,necroWarden", "--a-units", "necroDestroyer,necroWarden",
         "--p-mow", CARRIER, "--state-file", str(STATE)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        return None, (proc.stderr or proc.stdout or "")[-400:]
    return json.loads(STATE.read_text())["runnerId"], ""


def footprint(sid: int, rid: int) -> dict:
    """{id ECS -> {effectType: remaining}} pour unites ET MoW (cle MoW = casterId)."""
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}) or {}
    rows = [(u.get("id"), u) for u in (dec.get("units") or [])]
    rows += [(m.get("casterId"), m) for m in (dec.get("mows") or [])]
    out: dict = {}
    for key, u in rows:
        if key is None:
            continue
        effs = {int(e["effectType"]): e.get("remaining") for e in (u.get("effects") or [])
                if e.get("effectType") is not None}
        if effs:
            out[int(key)] = effs
    return out


def delta(before: dict, after: dict) -> dict:
    out: dict = {}
    for key, effs in after.items():
        new = {et: rem for et, rem in effs.items() if et not in (before.get(key) or {})}
        if new:
            out[int(key)] = new
    return out


def run_case(sid: int, label: str, only: list[str] | None,
             gen: str | None = None) -> tuple[str, dict]:
    rid, err = build()
    if rid is None:
        return "BUILD-KO", {"err": err}
    gen_info: dict = {}
    try:
        dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}) or {}
        mow = next((m for m in (dec.get("mows") or []) if m.get("visualId") == CARRIER), None)
        if mow is None:
            return "MOW-ABSENTE", {}
        caster = mow["casterId"]

        if gen is not None:
            # GENERALISATION : le poison est-il atteignable AUTREMENT que par combatSnapshot ?
            # #162 avait teste `aiPlaybookPredict` avec la MoW en CASTER (sain) -- mais la
            # bissection montre que le vecteur est la MoW en CIBLE. On rejoue donc la direction
            # NON testee : une unite ordinaire predit CONTRE la MoW.
            units = [u for u in (dec.get("units") or []) if not u.get("isDead")]
            atk = next((u for u in units if u.get("team") != mow.get("team")), None)
            if atk is None:
                return "PAS-D-ATTAQUANT", {}
            g = rpc(sid, gen, {"runnerId": rid, "unitId": atk["id"],
                               "targetId": caster, "abilityType": 17})
            # Un appel de generalisation qui n'a RIEN calcule ne prouve rien : un « POSE » qui
            # suit un RPC inerte est indiscernable du temoin SANS-SNAPSHOT. On EXIGE donc que
            # la prediction ait produit des events, sinon le cas est declare non concluant.
            nev = len((g or {}).get("events") or [])
            if not isinstance(g, dict) or g.get("ok") is False or nev == 0:
                return "GEN-INERTE", {"gen": str(g)[:220]}
            gen_info = {"genEvents": nev}

        if only is not None:
            snap = rpc(sid, "combatSnapshot", {"runnerId": rid, "debugOnly": only})
            if not (snap or {}).get("ok"):
                return "SNAPSHOT-KO", {"snap": str(snap)[:200]}

        at = rpc(sid, "abilityTargets",
                 {"runnerId": rid, "unitId": caster, "abilityType": ABILITY}) or {}
        row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster), None)
        tgts = ((row.get("abilities") or [{}])[0].get("targets") or []) if row else []
        units = [t for t in tgts if t.get("kind") == "unit"]
        if not units:
            return "AUCUNE-CIBLE", {"nTargets": len(tgts)}
        target = units[0]["targetId"]

        before = footprint(sid, rid)
        res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster, "abilityType": ABILITY,
            "targetId": target}}) or {}
        if res.get("ok") is False or not res.get("actions"):
            return "CAST-KO", {"res": str(res)[:200]}
        d = delta(before, footprint(sid, rid))
        return ("POSE" if d else "NO-OP"), {"caster": caster, "target": target,
                                            "delta": d, **gen_info}
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 20000)
        except Exception:                                          # noqa: BLE001
            pass


def check_channel_alive(sid: int) -> tuple[bool, str]:
    """Le correctif exclut les Machines des CIBLES de prediction. Un correctif qui « repare »
    en VIDANT le canal qu'il mesure serait le meme defaut sous un autre nom : `normalAttack`
    doit continuer a rendre un degat d'arme reel. On exige donc au moins une unite avec un
    `maxDmg > 0`, et on regarde ce que rend la MoW (attaquante legitime : elle garde toutes
    ses cibles UNIT)."""
    rid, err = build()
    if rid is None:
        return False, "build KO: " + err
    try:
        snap = rpc(sid, "combatSnapshot", {"runnerId": rid}) or {}
        rows = snap.get("units") or []
        live = [u for u in rows if isinstance(u.get("normalAttack"), dict)
                and isinstance(u["normalAttack"].get("maxDmg"), int)
                and u["normalAttack"]["maxDmg"] > 0]
        mows = [u for u in rows if u.get("entityType") == 6]
        detail = "%d/%d lignes portent un maxDmg>0 ; %d Machine(s) presente(s)" % (
            len(live), len(rows), len(mows))
        if mows:
            detail += " ; MoW.normalAttack=%s" % json.dumps(mows[0].get("normalAttack"))[:120]
        return bool(live), detail
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 20000)
        except Exception:                                          # noqa: BLE001
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", default=None, help="ne jouer QU'UN cas (label exact)")
    a = ap.parse_args()

    sid = live_session()
    print("session=%d  board=%s seed=%s mow=%s ability=%d" % (sid, BOARD, SEED, CARRIER, ABILITY))
    print("-" * 78)
    verdicts = {}
    cases: list[tuple[str, list[str] | None, str | None]] = [(l, o, None) for l, o in CASES]
    # GENERALISATION : prediction CONTRE la MoW par un autre RPC, sans aucun combatSnapshot.
    cases.append(("GEN:playbookPredictVsMoW", None, "aiPlaybookPredict"))
    for label, only, gen in cases:
        if a.case and label != a.case:
            continue
        verdict, info = run_case(sid, label, only, gen)
        verdicts[label] = verdict
        print("%-26s -> %-12s %s" % (label, verdict, json.dumps(info.get("delta", info))[:140]))
    print("-" * 78)
    # Garde de non-regression : depuis le correctif #175, AUCUN cas ne doit rendre NO-OP.
    # Un cas non concluant (GEN-INERTE, BUILD-KO...) n'est pas un succes non plus -- on ne
    # valide QUE sur POSE, sinon un montage casse passerait pour une absence de bug.
    # `GEN:` est INFORMATIF, hors verdict : il documente une inatteignabilite (le RPC ne sait
    # pas adresser une MoW en cible), pas un comportement a garder vert. L'inclure ferait
    # echouer la garde en permanence -- et une garde toujours rouge finit ignoree.
    if not a.case:
        alive, detail = check_channel_alive(sid)
        print("CANAL normalAttack VIVANT : %s -- %s" % ("OUI" if alive else "NON", detail))
        if not alive:
            verdicts["canal-normalAttack"] = "MORT"
    bad = {k: v for k, v in verdicts.items() if v != "POSE" and not k.startswith("GEN:")}
    print("VERDICT : " + ("OK -- tous les cas POSENT" if not bad
                          else "ECHEC -- %s" % json.dumps(bad)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
