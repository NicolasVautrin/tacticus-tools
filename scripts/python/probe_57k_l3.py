#!/usr/bin/env python
"""Probe #57k : passe L3 UNIQUE (session CALME) sur les 4 residuels tile-term/NC du batch gen.

⛔ L3 est SESSION-GLOBALE (hooks des 41 *Utility.MoveNext du hot-path IA) : NE LANCER QUE SOLO
(aucun autre agent/runner ne walke l'IA — le probe REFUSE si listRunners voit des runners
etrangers, sauf --force). Cf. garde-fou --l3 du harness stages (crash IL2CPP vecu 2026-07-19).

Cas couverts (un runner par cas, walk N pas natifs, L3 autour du dry-run du pas N, SANS apply) :
  S14  12345 s14 u87 necroOverlord : terme Tile natif a (3,5)/(4,3)/(3,4) — contrainte #57h
       T(4,3)-T(3,5) < 5.665 (le notre : +30 vs +20, 100 % Elevation).
  S16  2468 s16 u79 necroSpyder : terme Tile natif a (3,4)/(4,2) — contrainte T(3,4)-T(4,2) > 5.25
       (le notre : +30 vs +50) -> quelle feuille negative sur (4,2) ?
  S8   54321 s8 u81 bloodIntercessor : utilites de DECISION natives HammerOfWrath t89/t91/t93
       (events non-tile aussi dumpes — les utilites NC n'ont pas de RPC).
  S5   12345 s5 u89 worldExecutions : move-formula — terme >= +100 a (0,4) vs (1,4) (case-52).

Sortie : pour chaque cas, TOUS les events utility_score de l'acteur dans la fenetre, groupes
par caseTile (tuiles d'interet d'abord), + le decompte des AUTRES types d'events de la fenetre
(decouverte du vocabulaire trace pour les utilites NC/action-level).

Usage: python probe_57k_l3.py [--only S14,S8] [--force]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_57k_state.json"
TRACES_DIR = ROOT / "frida" / "data" / "ai-traces"   # host cwd = frida/ (cf. engine_agreement_stages TRACES_DIR)

#        tag: (seed, stop, uid, visual_hint, tuiles d'interet)
CASES = {"S14": ("12345", 14, 87, "necroOverlord", [(3, 5), (4, 3), (3, 4)]),
         "S16": ("2468", 16, 79, "necroSpyder", [(3, 4), (4, 2), (4, 3)]),
         "S8":  ("54321", 8, 81, "bloodIntercessor", [(5, 8)]),
         "S5":  ("12345", 5, 89, "worldExecutions", [(0, 4), (1, 4)]),
         # S18 (#64) : biais cross-generateur MartialInspiration 1191 — le natif joue 69
         # alors que SON pairUtility prefere 1191 (21.73 vs 20.98, meme tuile (4,3), meme
         # cible u91). vis=None : garder TOUS les events (la cible = le merge, pas les
         # termes tuile). Necessite L1 (playbook_action = utilite d'ACTION du merge).
         "S18": ("2468", 18, 77, None, [(4, 3)])}


def _r(sid: int, method: str, body, t: float = 90) -> dict:
    return (_rpc(sid, method, [body] if isinstance(body, dict) else body,
                 timeout=t).get("result") or {})


def _tile_of(ct):
    if isinstance(ct, dict):
        return (ct.get("col"), ct.get("row"))
    if isinstance(ct, (list, tuple)) and len(ct) >= 2:
        return (ct[0], ct[1])
    return None


def _trace_file(sid: int):
    files = sorted(TRACES_DIR.glob(f"{sid}-*.jsonl"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def run_case(sid: int, tag: str, seed: str, stop: int, uid: int, vis: str, tiles: list) -> None:
    # Purger le state-file AVANT le build : un STATE residuel d'une passe precedente
    # ferait lire un runnerId mort si le build echoue (vecu : faux « epuise au pas 0 »
    # alors que le build criait « Board not found » dans le stderr avale).
    STATE.unlink(missing_ok=True)
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", seed,
                           "--state-file", str(STATE), "--board", "MC1_67"],
                          cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[57k:{tag}] build KO: {(proc.stderr or proc.stdout or '')[-400:]}",
              file=sys.stderr)
        return
    rid = json.loads(STATE.read_text())["runnerId"]
    print(f"[57k:{tag}] seed={seed} runner={rid} -> walk s{stop}")
    try:
        for step in range(stop):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[57k:{tag}] natif epuise au pas {step} "
                      f"(ok={dry.get('ok')} hasNext={dry.get('hasNext')} "
                      f"err={dry.get('error')})")
                return
            acts = []
            for m in (dry["action"]["messages"] or []):
                if m.get("cls") == "MoveUnitMessage":
                    acts.append({"kind": "move", "unitId": m["unitId"],
                                 "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
                elif m.get("cls") == "ActiveAbilityMessage":
                    acts.append({"kind": "ability", "casterId": m["casterId"],
                                 "targetId": m.get("targetId"), "abilityType": m["abilityType"]})
                elif m.get("cls") == "FinishUnitTurnMessage":
                    acts.append({"kind": "finish", "unitId": m["unitId"]})
            if acts:
                _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 60)

        # fenetre L3 autour du dry-run de decision (PAS d'apply : etat intact)
        st0 = _r(sid, "aiTraceStatus", [], 20)
        lo = st0.get("seq")
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 120)
        st1 = _r(sid, "aiTraceStatus", [], 20)
        hi = st1.get("seq")
        msgs = (dry.get("action") or {}).get("messages") or []
        nat_move = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
        nat_ab = next((m for m in msgs if m.get("cls") == "ActiveAbilityMessage"), None)
        print(f"[57k:{tag}] NATIF: move={nat_move and (nat_move['to']['col'], nat_move['to']['row'])} "
              f"ability={nat_ab and (nat_ab.get('casterId'), nat_ab.get('abilityType'), nat_ab.get('targetId'))} "
              f"seq_win=({lo},{hi})")

        tf = _trace_file(sid)
        if tf is None:
            print(f"[57k:{tag}] AUCUN fichier trace {sid}-*.jsonl", file=sys.stderr)
            return
        tset = {tuple(t) for t in tiles}
        by_tile: dict = {}
        others: Counter = Counter()
        win: list = []
        with open(tf, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                sq = e.get("seq")
                if sq is None or (lo is not None and sq <= lo) or (hi is not None and sq > hi):
                    continue
                win.append(e)
                if e.get("evt") != "utility_score":
                    others[e.get("evt")] += 1
                    continue
                eu = e.get("unit")
                eun = eu.get("name") if isinstance(eu, dict) else eu
                if eun is not None and vis is not None and eun != vis:
                    continue
                t = _tile_of(e.get("caseTile"))
                by_tile.setdefault(t, []).append((e.get("utility"), e.get("score")))
        # dump brut de la fenetre : re-analyse offline sans re-payer une passe L3
        dump = ROOT / "data" / f"l3_57k_{tag.lower()}.jsonl"
        with open(dump, "w", encoding="utf-8") as f:
            for e in win:
                f.write(json.dumps(e) + "\n")
        print(f"[57k:{tag}] fenetre brute: {len(win)} events -> {dump}")
        print(f"[57k:{tag}] autres events fenetre: {dict(others)}")
        # resume playbook (#64) : utilites d'ACTION du merge cross-generateur (L1)
        pb = [e for e in win if e.get("evt") == "playbook_action"]
        for e in pb[:200]:
            cast = e.get("caster")
            cast = cast.get("name") if isinstance(cast, dict) else cast
            tgt = e.get("target")
            tgt = tgt.get("name") if isinstance(tgt, dict) else tgt
            at = _tile_of(e.get("actionTile"))
            print(f"[57k:{tag}] PB {e.get('playbook')} ab={e.get('ability')} caster={cast} "
                  f"tile={at} tgt={tgt} u={e.get('utility')}")
        if len(pb) > 200:
            print(f"[57k:{tag}] ... {len(pb) - 200} playbook_action de plus (voir dump)")
        for t in sorted(by_tile, key=lambda x: (x not in tset, str(x))):
            star = "*" if t in tset else " "
            terms = by_tile[t]
            tot = sum(s for (_n, s) in terms if isinstance(s, (int, float)))
            print(f"[57k:{tag}] {star}tuile {t}: total={tot:+.3f} " +
                  " ".join(f"{n}={s:+g}" for (n, s) in terms if s))
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print(f"[57k:{tag}] runner {rid} dispose")
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=str, default=None, help="tags separes par des virgules")
    ap.add_argument("--force", action="store_true",
                    help="passe outre le refus runners-etrangers (danger IL2CPP)")
    args = ap.parse_args()
    sid = _resolve_session()
    pre = _rpc(sid, "listRunners", [], timeout=10).get("result") or []
    if pre and not args.force:
        ids = [(r.get("runnerId") if isinstance(r, dict) else r) for r in pre]
        print(f"[57k] REFUS : {len(pre)} runner(s) preexistant(s) {ids} — L3 est SESSION-GLOBALE, "
              f"lancer SOLO (ou --force si certain d'etre seul).", file=sys.stderr)
        return 2
    tags = [t.strip().upper() for t in args.only.split(",")] if args.only else list(CASES)
    # L1 (playbook actions/utilites du merge) + L2 (inputs generateurs) + L3 (feuilles
    # utility_score). Les 3 niveaux sont INDEPENDANTS cote hooks (ai-trace.ts) — L3 seul
    # ne dumpe PAS playbook_action, indispensable pour S18/#64.
    for lv in ("L1", "L2", "L3"):
        _r(sid, "aiTraceEnable", [lv], 20)
    try:
        for tag in tags:
            if tag not in CASES:
                print(f"[57k] tag inconnu {tag}", file=sys.stderr)
                continue
            run_case(sid, tag, *CASES[tag])
    finally:
        for lv in ("L1", "L2", "L3"):
            _r(sid, "aiTraceDisable", [lv], 20)
        print("[57k] L1+L2+L3 disabled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
