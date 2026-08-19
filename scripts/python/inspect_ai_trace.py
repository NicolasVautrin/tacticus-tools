"""
inspect_ai_trace.py — Caractérise les JSONL produits par `frida/host/ai-trace-store.ts`.

Objectif : sortir un rapport humain-lisible sur ce qu'on capture vraiment
afin de designer le candidate-first action space (étape 2 du plan RL) sur
des donnees mesurees plutot que sur des hypotheses.

Usage:
    python scripts/python/inspect_ai_trace.py              # toutes les sessions
    python scripts/python/inspect_ai_trace.py <file.jsonl> # un fichier precis

Sortie (stdout) :
  - inventaire des events par type, par session
  - schema reel des champs (presence, type) par evt
  - exemple d'une "decision window" (ai_turn_begin -> ai_action_applied)
  - stats : nb decisions, taille moyenne du candidate-set, distribution utilities

Aucune dependance externe — stdlib only.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import host_inputs  # noqa: E402  (#273 : entrees gitignorees, resolution tri-etat)

# Le store ecrit sous `frida/data/ai-traces` (cwd du host = frida/), PAS sous `data/`.
# Ce chemin pointait sur un repertoire inexistant : bug latent trouve le 2026-07-26.
# #273 : et il pointait sur le repertoire du WORKTREE, jamais sur celui du host --
# `.exists()` y rendait False, le script disait « Aucun fichier JSONL trouve » et
# renvoyait « demarre le host », alors que le host tournait et ecrivait ailleurs.
TRACES = "frida/data/ai-traces"


# ---- I/O ---------------------------------------------------------------- #

def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  [warn] {path.name}:{i} parse error: {e}",
                      file=sys.stderr)


def _list_sources(arg: str | None) -> list[Path] | None:
    """Fichiers JSONL a inspecter.

    Tri-etat (#273) : `None` = PAS MESURE (repertoire de traces introuvable, ou
    argument explicite qui n'existe pas), `[]` = MESURE et VIDE (repertoire du
    host present, aucun `.jsonl` dedans).
    """
    if arg:
        p = Path(arg)
        return [p] if p.exists() else None
    try:
        return host_inputs.find(TRACES, "*.jsonl")
    except host_inputs.HostInputUnavailable:
        return None


# ---- Schema inference --------------------------------------------------- #

def _type_of(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        if not v:
            return "list[]"
        return f"list[{_type_of(v[0])}]"
    if isinstance(v, dict):
        return "object"
    return "?"


def _walk_paths(obj: Any, prefix: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                yield from _walk_paths(v, path)
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                yield from _walk_paths(v[0], path + "[]")
            else:
                yield path, _type_of(v)


# ---- Decision-window slicing ------------------------------------------- #

DECISION_BOUNDARIES = {"ai_turn_begin", "ai_action_applied"}


def _slice_decisions(records: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group records into decision windows.

    Open window on ai_turn_begin, append until first ai_action_applied
    (inclusive), then start a new window. Records before any ai_turn_begin
    are skipped (amorce noise).
    """
    windows: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    in_window = False
    for r in records:
        evt = r.get("evt")
        if evt == "ai_turn_begin":
            if cur:
                windows.append(cur)
            cur = [r]
            in_window = True
            continue
        if not in_window:
            continue
        cur.append(r)
        if evt == "ai_action_applied":
            windows.append(cur)
            cur = []
            in_window = False
    if cur:
        windows.append(cur)
    return windows


# ---- Reporting ---------------------------------------------------------- #

def _report_evts(records: list[dict[str, Any]]) -> None:
    c = Counter(r.get("evt", "<no_evt>") for r in records)
    print("  events par type :")
    for evt, n in c.most_common():
        print(f"    {evt:<28} {n:>7}")


def _report_schema(records: list[dict[str, Any]], evt_filter: str) -> None:
    sample = [r for r in records if r.get("evt") == evt_filter]
    if not sample:
        return
    print(f"\n  schema {evt_filter!r} (n={len(sample)}) :")
    fields: dict[str, Counter] = defaultdict(Counter)
    for r in sample:
        for k, t in _walk_paths(r):
            if k == "evt":
                continue
            fields[k][t] += 1
    total = len(sample)
    for path in sorted(fields):
        types = fields[path]
        coverage = sum(types.values()) / total * 100
        tstr = ", ".join(f"{t}({n})" for t, n in types.most_common())
        print(f"    {path:<40} {coverage:5.1f}%  {tstr}")


def _report_decisions(windows: list[list[dict[str, Any]]]) -> None:
    if not windows:
        print("\n  (aucune decision window — pas de ai_turn_begin OU pas de tour AI termine)")
        return
    closed = [w for w in windows if w[-1].get("evt") == "ai_action_applied"]
    print(f"\n  decision windows : {len(windows)} ouvertures, "
          f"{len(closed)} fermees (avec ai_action_applied)")

    cand_counts: list[int] = []
    action_counts: list[int] = []
    cand_pos_counts: list[int] = []
    utility_sample: list[float] = []
    for w in closed:
        cand_counts.append(sum(1 for r in w if r.get("evt") == "candidates"))
        action_counts.append(sum(1 for r in w if r.get("evt") == "playbook_action"))
        for r in w:
            if r.get("evt") == "candidates":
                pc = r.get("possibleCount")
                if isinstance(pc, int) and pc >= 0:
                    cand_pos_counts.append(pc)
            elif r.get("evt") == "playbook_action":
                u = r.get("utility")
                if isinstance(u, (int, float)):
                    utility_sample.append(float(u))

    def _stat(label: str, xs: list) -> None:
        if not xs:
            print(f"    {label}: <vide>")
            return
        xs2 = sorted(xs)
        n = len(xs2)
        avg = sum(xs2) / n
        p50 = xs2[n // 2]
        p95 = xs2[min(n - 1, int(n * 0.95))]
        mn, mx = xs2[0], xs2[-1]
        print(f"    {label:<30} n={n:<6} avg={avg:.2f} p50={p50} p95={p95} "
              f"min={mn} max={mx}")

    print("  par decision fermee :")
    _stat("candidates events / win.", cand_counts)
    _stat("playbook_actions / win.", action_counts)
    _stat("candidates.possibleCount", cand_pos_counts)
    _stat("playbook_action.utility", utility_sample)


def _report_sample_window(
    windows: list[list[dict[str, Any]]], max_lines: int = 30,
) -> None:
    closed = [w for w in windows if w[-1].get("evt") == "ai_action_applied"]
    if not closed:
        return
    w = closed[0]
    print("\n  exemple decision window (premiere fermee) :")
    print(f"    span: seq {w[0].get('seq')} -> seq {w[-1].get('seq')}, "
          f"size={len(w)} events")
    counts = Counter(r.get("evt") for r in w)
    for evt, n in counts.most_common():
        print(f"      {evt:<28} {n:>4}")
    print("    ai_action_applied final :")
    final = w[-1]
    for k, v in final.items():
        if k in ("seq", "evt"):
            continue
        print(f"      {k} = {v!r}")


def _report_winner_kinds(records: list[dict[str, Any]]) -> None:
    kinds = Counter(
        r.get("kind", "<no_kind>")
        for r in records if r.get("evt") == "ai_action_applied"
    )
    if not kinds:
        return
    print("\n  ai_action_applied.kind (= action type choisi par l'IA) :")
    for k, n in kinds.most_common():
        print(f"    {k:<28} {n:>5}")


# ---- Main --------------------------------------------------------------- #

def main(argv: list[str]) -> int:
    arg = argv[1] if len(argv) > 1 else None
    sources = _list_sources(arg)
    if sources is None:                      # PAS MESURE -- rc 2
        if arg:
            print(f"Chemin introuvable : {arg}")
        else:
            try:
                host_inputs.require(TRACES)
            except host_inputs.HostInputUnavailable as e:
                print(str(e))
        return 2
    if not sources:                          # MESURE et VIDE -- rc 1
        print(f"MESURE et VIDE : aucun .jsonl sous "
              f"{host_inputs.resolve(TRACES).label()}")
        print("Demarre le host, fait jouer une battle, puis relance.")
        return 1

    print(f"== inspect_ai_trace.py — {len(sources)} fichier(s) ==")
    for path in sources:
        print(f"\n-- {path.name} ({path.stat().st_size:,} bytes) --")
        records = list(_iter_jsonl(path))
        if not records:
            print("  (vide)")
            continue
        print(f"  total records : {len(records)}")
        _report_evts(records)
        for evt in (
            "ai_turn_begin",
            "playbook_eval_begin",
            "playbook_action",
            "playbook_eval_end",
            "candidates",
            "ai_action_applied",
        ):
            _report_schema(records, evt)
        _report_winner_kinds(records)
        windows = _slice_decisions(records)
        _report_decisions(windows)
        _report_sample_window(windows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
