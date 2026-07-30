"""probe_298 -- OU s'arrete le rail de DECISION de la REPARATION (residu de #278).

QUESTION BINAIRE : quel generateur d'actions / quel playbook propose l'action de
REPARATION, et quelle condition d'entree n'est pas remplie dans le harnais runner ?

Le probe DECOMPOSE PAR ETAGE, il ne fitte rien. Quatre etages natifs, un capteur par
etage, tous DEJA armes (aucun nouveau hook, aucune reinjection) :

  E0  l'ability de reparation est-elle dans `ActiveAbilityComponent.Abilities` ?
      capteur : RPC `abilityTargets` -> `unitAbilityTypes` (internals.ts) qui lit
      `ActiveAbilityComponent$$GetActives` PUIS `ActiveAbilityComponent$$GetUnusedAbilities`.
      Les DEUX iterent la meme collection `Abilities` ; le champ `kind` dit LAQUELLE
      des deux l'a rendue ("active" vs "granted").

  E1  l'ability est-elle dans le jeu de types d'UN generateur ?
      capteur : trace L2 (`ai-trace/generators.ts`) -> event `candidates`, champ
      `abilities` = `ActiveAbilityActionGenerator._abilityTypes` (16 premiers).
      Natif : `IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists` remplit
      `_comparableAbilities` / `_nonComparableAbilities[priority]`, et
      `IdunBattle.AI.Tactics.ABaseAiActorTactic$$GetDefaultActiveAbilityActionGenerators`
      en fait 6 generateurs (5 priorites non-comparables + 1 comparable).

  E2  le playbook de l'ability est-il EVALUE ?
      capteur : trace L1 (`ai-trace/playbooks.ts`) -> `playbook_eval_begin`, champ
      `playbook` = nom de classe du playbook, `ability` = son `ActiveAbilityType`.
      Natif : `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator$$GetUnitAbilitiesInOrder`
      filtre les abilities de l'unite par `_abilityTypes.Contains(...)`.

  E3  la prediction de reparation est-elle calculee ?
      capteur : trace L1 -> `repair_prediction`, emis par le hook sur
      `IdunBattle.Core.Services.DamagePrediction$$PredictRepair`.
      Natif amont : `IdunBattle.AI.Playbook.Loki.Repair_GalvanicFieldPlaybook$$MakeRepairPredictions`
      (`RepairPlaybook$$MakeRepairPredictions` pour l'ability 28).

Le montage est la FIXTURE NOMMEE `_repair_stage.build_stage` (tests/engine/runner) --
jamais inline ici : ce probe et le test live consomment le MEME montage.

Usage (depuis scripts/python, `python` -- pas `py`, ASCII only) :
    python probe_298_repair_rail.py                  # monte, mesure, imprime le verdict
    python probe_298_repair_rail.py --runner 3       # reutilise un runner deja monte
    python probe_298_repair_rail.py --no-trace       # E0 seul (aucune trace activee)

NE REINJECTE PAS et n'active JAMAIS L3 (hooks session-globaux).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_PYDIR))
sys.path.insert(0, str(_PYDIR / "tests" / "engine" / "runner"))

import host_inputs  # noqa: E402  (#273 : entrees gitignorees, resolution tri-etat)

TRACES = "frida/data/ai-traces"

# Ids d'ActiveAbilityType de la reparation REGULIERE, tels que les enumere
# `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsRegularRepair`
# (compare a 0x1c puis 0x45f). Non devine : lu au decompile.
REGULAR_REPAIR_IDS = (28, 1119)


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


# ---- E0 : l'ability est-elle dans ActiveAbilityComponent.Abilities ? ------- #

def measure_e0(rpc, rid: int, unit_id: int) -> dict:
    """Retourne {abilities: [...], repair: <entree|None>}.

    `kind` vaut "normal" (NormalAttackType@0x28), "active" (GetActives) ou
    "granted" (GetUnusedAbilities). "granted" prouve que l'entree EST dans la
    collection `Abilities` mais que `GetActives` la FILTRE.
    """
    r = _unwrap(rpc("abilityTargets",
                    {"runnerId": rid, "unitId": unit_id, "allAbilities": True}))
    units = (r or {}).get("units") or []
    ab = units[0].get("abilities", []) if units else []
    repair = next((a for a in ab if a.get("abilityId") in REGULAR_REPAIR_IDS), None)
    return {"ok": bool(units), "abilities": ab, "repair": repair}


# ---- traces : marquer la queue, lire le delta ------------------------------ #

def trace_file(sid: int) -> Path | None:
    """JSONL le plus recent de la session `sid`, ou None si PAS MESURE."""
    try:
        files = host_inputs.find(TRACES, f"{sid}-*.jsonl")
    except host_inputs.HostInputUnavailable as e:
        print("[traces] " + str(e))
        return None
    return files[-1] if files else None


def tail_mark(p: Path | None) -> int:
    return p.stat().st_size if (p and p.exists()) else 0


def tail_read(p: Path | None, off: int) -> list[dict]:
    if not (p and p.exists()):
        return []
    out: list[dict] = []
    with p.open("r", encoding="utf-8", errors="replace") as f:
        f.seek(off)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


# ---- rapport --------------------------------------------------------------- #

def _ent_name(e) -> str | None:
    """Projection d'entite des traces : `{"name": "<visualId>"}`.

    PAS d'entityId dans la projection par defaut (`ai-trace/state.js`) -- et la trace
    est SESSION-GLOBALE (tous les runners de la session ecrivent le meme JSONL). Le
    `visualId` est donc le seul discriminant disponible sans reconfigurer la
    projection : d'ou le filtrage par ROSTER, pas par entityId.
    """
    if isinstance(e, dict):
        v = e.get("name")
        return v if isinstance(v, str) else None
    return None


def summarize(events: list[dict], roster: set[str] | None) -> dict:
    """Ventile les events des 4 etages, restreints au `roster` (visualIds) quand fourni."""
    cand: list[dict] = []
    evals: list[dict] = []
    repairs: list[dict] = []

    def mine(nm: str | None) -> bool:
        return roster is None or (nm is not None and nm in roster)

    for ev in events:
        kind = ev.get("evt")
        if kind == "candidates":
            nm = _ent_name(ev.get("unit"))
            if mine(nm):
                cand.append({"generator": ev.get("generator"), "unit": nm,
                             "abilities": ev.get("abilities")})
        elif kind == "playbook_eval_begin":
            nm = _ent_name(ev.get("caster"))
            if mine(nm):
                evals.append({"playbook": ev.get("playbook"),
                              "ability": ev.get("ability"), "caster": nm})
        elif kind == "repair_prediction":
            nm = _ent_name(ev.get("caster"))
            if mine(nm):
                repairs.append({"playbook": ev.get("playbook"),
                                "ability": ev.get("playbookAbility"),
                                "caster": nm,
                                "target": _ent_name(ev.get("target")),
                                "amount": ev.get("amount"),
                                "prediction": ev.get("prediction")})
    return {"candidates": cand, "evals": evals, "repairs": repairs}


def run_scenario(rpc, sid: int, rid: int, unit_id: int, roster: set[str],
                 repeat: int = 1, verbose: bool = True) -> dict:
    """Mesure E0..E3 sur un runner deja monte. Rend le resume chiffre.

    `repeat` > 1 rejoue `aiDryRunAllUnits` N fois : un rail dont l'entree dependrait
    d'un tirage (cf. `ActiveAbilityActionGenerator$$ShouldRandomizeOrder`) ne rendrait
    pas le meme compte a chaque passe.
    """
    e0 = measure_e0(rpc, rid, unit_id)
    if verbose:
        print("\n== E0 -- ActiveAbilityComponent.Abilities (RPC abilityTargets) ==")
        for a in e0["abilities"]:
            print("  id=%-5s %-28s kind=%-8s targets=%s fromHere=%s"
                  % (a.get("abilityId"), a.get("ability"), a.get("kind"),
                     a.get("targetCount"), a.get("fromHereCount")))
        rp = e0["repair"]
        print("  -> reparation reguliere dans Abilities: %s"
              % ("OUI" if rp else "NON"))

    # JAMAIS L3 (hooks session-globaux : crash si un autre agent walke l'IA).
    # L'argument est une CHAINE, pas un objet -- `ctx.rpc.aiTraceEnable(level: string)`.
    for lv in ("L1", "L2"):
        _unwrap(rpc("aiTraceEnable", lv))

    p = trace_file(sid)
    runs = []
    for _ in range(max(1, repeat)):
        off = tail_mark(p)
        dry = _unwrap(rpc("aiDryRunAllUnits", {"runnerId": rid}, timeout=240))
        s = summarize(tail_read(p, off), roster)
        u = _dry_for(dry, unit_id)
        runs.append({
            "repairs": len(s["repairs"]),
            "playbooks": sorted({c["playbook"] for c in s["evals"]}),
            "generators": len(s["candidates"]),
            "pumps": (u or {}).get("pumps"),
            "proposed": [a.get("abilityType")
                         for a in ((u or {}).get("proposed") or [])
                         if a.get("cls") == "ActiveAbilityMessage"],
            "sample": s["repairs"][:1],
        })

    if verbose:
        print("\n== E1/E2/E3 -- %d passe(s) de aiDryRunAllUnits ==" % len(runs))
        for i, r in enumerate(runs):
            print("  run%-2d repair_prediction=%-3d pumps=%-5s proposed_ability=%s"
                  % (i, r["repairs"], r["pumps"], r["proposed"]))
            print("        playbooks=%s" % (r["playbooks"],))
            if r["sample"]:
                print("        %s" % json.dumps(r["sample"][0], ensure_ascii=True))
    return {"e0": e0, "runs": runs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None,
                    help="runnerId deja monte (sinon: monte la fixture)")
    ap.add_argument("--unit", type=int, default=None,
                    help="entityId du repareur (sinon: auto par visualId)")
    ap.add_argument("--repairer", default=None,
                    help="visualId du repareur (defaut: celui du montage)")
    ap.add_argument("--repairee", default=None,
                    help="visualId de la cible (defaut: celui du montage)")
    ap.add_argument("--advance", type=int, default=2,
                    help="tours IA joues avant la mesure (0 = personne n'est blesse)")
    ap.add_argument("--hp-player", type=int, default=None,
                    help="force Health ET RemainingHealth de team 1 (=> 100 %%, PAS blesse)")
    ap.add_argument("--damaged", type=int, default=None,
                    help="RemainingHealth pose sur la CIBLE seule (=> blessee)")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--keep", action="store_true",
                    help="ne pas disposer le runner monte par le probe")
    ap.add_argument("--no-trace", action="store_true",
                    help="E0 seul, n'active aucune trace")
    args = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()
    print("session=%d" % sid)

    def rpc(method, body=None, timeout=90):
        return R._rpc(sid, method, [body] if body is not None else [],
                      timeout=timeout)

    built = False
    if args.runner is not None:
        rid = args.runner
        unit_id = args.unit or _find_repairer(rpc, rid)
        roster = None
    else:
        import _repair_stage as S                    # noqa: E402
        if args.repairer:
            S.REPAIRER_VIS = args.repairer
        if args.repairee:
            S.REPAIREE_VIS = args.repairee
        stage = S.build_stage(rpc, hp_player=args.hp_player,
                              advance=args.advance,
                              damaged_repairee=args.damaged)
        rid, unit_id, built = stage["rid"], stage["repairer"], True
        roster = {S.REPAIRER_VIS, S.REPAIREE_VIS}
    if roster is None:
        roster = _roster_of(rpc, rid)
    print("runner=%s repairer_unit=%s roster=%s" % (rid, unit_id, sorted(roster or [])))
    if unit_id is None:
        print("VERDICT: aucun repareur dans le montage -- montage a refaire")
        return 2

    st = _unwrap(rpc("aiTraceStatus")) or {}
    ist = st.get("installStatus") or {}
    print("== capteurs ==  installed=%s enabled=%s PredictRepair=%s L1=%s L2=%s"
          % (st.get("installed"), st.get("enabled"), ist.get("PredictRepair"),
             ist.get("L1_evaluate"), ist.get("L2_ActiveAbilityActionGenerator")))
    p = trace_file(sid)
    print("  trace file: %s" % (p.as_posix() if p else "(PAS MESURE)"))

    try:
        if args.no_trace:
            measure_e0(rpc, rid, unit_id)
            return 0
        run_scenario(rpc, sid, rid, unit_id, roster, repeat=args.repeat)
    finally:
        if built and not args.keep:
            _unwrap(rpc("disposeRunner", {"runnerId": rid}, timeout=30))
            print("\n[dispose] runner %s rendu" % rid)
    return 0


def _find_repairer(rpc, rid: int) -> int | None:
    """entityId de la 1re unite controlee qui porte une reparation reguliere."""
    r = _unwrap(rpc("abilityTargets", {"runnerId": rid, "allAbilities": True}))
    for u in (r or {}).get("units") or []:
        for a in u.get("abilities") or []:
            if a.get("abilityId") in REGULAR_REPAIR_IDS:
                return u.get("unitId")
    return None


def _roster_of(rpc, rid: int) -> set[str]:
    """visualIds des unites du runner -- discriminant du filtrage de trace."""
    ob = _unwrap(rpc("observeBattle", {"runnerId": rid})) or {}
    obs = ob.get("units") or ob.get("observations") or []
    return {o.get("visualId") for o in obs if o.get("visualId")}


def _dry_for(dry, unit_id):
    if not isinstance(dry, dict):
        return dry
    for u in dry.get("units") or []:
        if u.get("unitId") == unit_id:
            return u
    return {"note": "unite absente de aiDryRunAllUnits",
            "keys": sorted(dry.keys())[:12]}


if __name__ == "__main__":
    raise SystemExit(main())
