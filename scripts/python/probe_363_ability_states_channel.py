#!/usr/bin/env python
"""Probe #363 -- le canal `load_state(ability_states=...)` (#357) : COMBIEN IL COUTE, PUIS S'IL PASSE.

LE RESIDU #357-r1. #357 pose le rail de la relique EQUIPEE et le confronte live, mais son canal
n'avait qu'UN producteur : hors de ce montage, une relique equipee restait INERTE cote port -- y
compris pour les QUATRE unites qui en portent une DES LE SEED BC. Brancher le canal par defaut coute
un RPC de plus par capture d'etat : ce probe MESURE ce cout AVANT de trancher, puis mesure que le
branchement fait ce qu'il pretend.

DEUX VOLETS, ET L'ORDRE COMPTE -- brancher d'abord et mesurer ensuite, ce serait decider sans critere.

VOLET `cost` (`run_cost`) -- LE CRITERE
  1. la LATENCE de `unitAbilityStates` (sans `unitId` : toutes les unites d'un coup) ;
  2. la latence des RPC que la MEME capture fait DEJA -- `decisionView` (allAbilities),
     `observeBattle`, `combatSnapshot`, `boardGraph` ;
  3. le cout Python de `load_state` lui-meme, AVEC et SANS le seed tertiaire.
  C'est le RAPPORT (1)/(2) qui tranche, pas (1) seul : un RPC de 30 ms est negligeable en face d'une
  capture de 900 ms et prohibitif en face d'une capture de 5 ms. La reponse est une FRACTION.

  DEUX TAILLES DE ROSTER, deliberement : `unitAbilityStates` sans `unitId` ENUMERE toutes les unites
  du runner (`rpc-snapshot.ts`), donc son cout pourrait scaler avec l'effectif -- comme
  `decisionView` le fait. Mesurer une seule taille laisserait ouvert « et sur une vraie bataille ? ».

  ⚠ PREMIER APPEL EXCLU. Le premier appel d'une methode RPC paie la resolution IL2CPP (cache
  `MethodInfo*` Frida-side) ; le mesurer melangerait un cout d'AMORCAGE une-fois-par-session avec le
  cout RECURRENT qu'on cherche. Chaque methode est appelee a blanc avant la serie.

VOLET `default` (`run_default`) -- LA MESURE DU BRANCHEMENT
  Monte les QUATRE porteurs de relique du seed BC et charge la MEME capture de TROIS facons, dont
  DEUX sont des contre-epreuves -- la lecture nominale seule serait un vert que rien ne ferait rougir :

    `auto`      `load_state(dv, ob, snap)` avec transport ambiant lie  -> DOIT voir les 4 reliques ;
    `refused`   `load_state(..., ability_states=False)`                -> n'en voit AUCUNE (l'etat
                d'avant #363, et la preuve que le bras `auto` ne doit rien a un autre chemin) ;
    `given`     `load_state(..., ability_states=<payload>)`            -> DOIT egaler `auto` (le
                canal explicite de #357 reste la reference).

  ORACLES, deux et independants : le payload `unitAbilityStates` (entrees de hierarchie 3 -- ce que
  le NATIF a reellement monte) et `data/seed-bc.json` (`BC.Units[].TertiaryAbility` -- ce que la
  CONFIG declare). Le port doit coincider avec les deux.

Reproduire :

    cd scripts/python
    python probe_363_ability_states_channel.py                 # cout (2v2, 5v5) puis branchement
    python probe_363_ability_states_channel.py --volet default
    python probe_363_ability_states_channel.py --volet cost --reps 25

Sorties dans `logs/` (jamais `data/`). ASCII only (cp1252). Discipline runner : `--state-file`
absolu, un runner a la fois, dispose en sortie.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
_ROOT = _PYDIR.parents[1]

BOARD = "MC1_67"
SEED = "777"

# Les QUATRE unites qui equipent une relique DES LE SEED BC (`BC.Units[].TertiaryAbility`) :
# necroSpyder 1462, orksRuntherd 1475, admecMarshall / admecRuststalker 1457. Toutes au pool rank 17.
SEED_RELIC_UNITS = ("necroSpyder", "orksRuntherd", "admecMarshall", "admecRuststalker")
SEED_RELIC_IDS = {"necroSpyder": 1462, "orksRuntherd": 1475,
                  "admecMarshall": 1457, "admecRuststalker": 1457}

# Roster ADVERSE -- sans relique, pour que le releve porte des DEUX cotes (porteur / non-porteur).
# TOUS au pool rank 17 (verifie par `rl_duel build --list-pool` : un `--a-units` hors pool fait
# ECHOUER le build, il ne degrade pas le roster en silence).
FOES = ("orksNob", "tauCrisis", "eldarRanger", "necroWarden", "orksWarboss")

ROSTERS = {
    "2v2": (("necroSpyder", "orksRuntherd"), FOES[:2]),
    "5v5": (SEED_RELIC_UNITS + ("orksNob",), FOES[:5]),
}


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _out_dir() -> Path:
    p = _ROOT / "logs" / ("probe_363-%d" % os.getpid())
    p.mkdir(parents=True, exist_ok=True)
    return p


def build_args(p_units, a_units) -> list[str]:
    return ["--board", BOARD, "--p-units", ",".join(p_units), "--a-units", ",".join(a_units)]


def _build_subprocess(p_units, a_units) -> int:
    state = _out_dir() / "runner.json"
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            "--state-file", str(state), *build_args(p_units, a_units)]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): " + ((p.stderr or p.stdout or "")[-600:]))
    return json.loads(state.read_text())["runnerId"]


def _time_rpc(rpc, method: str, body: dict, reps: int) -> dict:
    """Serie de `reps` appels, PREMIER APPEL EXCLU (amorcage IL2CPP). Rend ms min/median/mean."""
    rpc(method, body, 120)                       # a blanc : resolution de methode hors mesure
    ts = []
    payload = None
    for _ in range(reps):
        t0 = time.perf_counter()
        payload = rpc(method, body, 120)
        ts.append((time.perf_counter() - t0) * 1000.0)
    return {"min": min(ts), "median": statistics.median(ts), "mean": statistics.mean(ts),
            "max": max(ts), "n": reps, "payload": payload}


def _time_load_state(dv, ob, snap, board, uas, reps: int) -> dict:
    """Cout PYTHON de `load_state` -- sans, puis avec le seed tertiaire. Le delta isole
    `_load_tertiary_abilities` (le RPC, lui, est mesure separement)."""
    from engine.runner.snapshot import load_state
    out = {}
    for lab, arg in (("sans", None), ("avec", uas)):
        load_state(dv, ob, snap, board=board, ability_states=arg)   # a blanc (imports paresseux)
        ts = []
        for _ in range(reps):
            t0 = time.perf_counter()
            load_state(dv, ob, snap, board=board, ability_states=arg)
            ts.append((time.perf_counter() - t0) * 1000.0)
        out[lab] = {"min": min(ts), "median": statistics.median(ts), "n": reps}
    return out


def _tertiary_rows(uas: dict) -> list:
    """Entrees de hierarchie 3 du payload (`raw[10] == 3`, cf. `snapshot.TERTIARY_HIERARCHY`)."""
    rows = []
    for u in (uas or {}).get("units") or []:
        for t in u.get("triggered") or []:
            raw = t.get("raw") or []
            if len(raw) > 10 and raw[10] == 3:
                rows.append({"entityId": u.get("entityId"), "abilityId": raw[0],
                             "level": t.get("level"), "mult": t.get("mult")})
    return rows


def run_cost(rpc, roster: str = "2v2", reps: int = 12, build_runner=None, keep: bool = False) -> dict:
    """Monte le roster, chronometre, rend le releve. Ne LEVE pas -- l'appelant juge."""
    assert roster in ROSTERS, "roster inconnu : %s (connus : %s)" % (roster, sorted(ROSTERS))
    from engine.entities.pathfinding.board import Board

    p_units, a_units = ROSTERS[roster]
    out: dict = {"roster": roster, "reps": reps, "ok": False, "why": None,
                 "p_units": list(p_units), "a_units": list(a_units)}

    if build_runner is not None:
        rid = build_runner(SEED, extra=build_args(p_units, a_units))["rid"]
    else:
        rid = _build_subprocess(p_units, a_units)
    out["rid"] = rid
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            out["why"] = "boardGraph indispo"
            return out
        board = Board(bg["tiles"], adjacency="native_sym")

        calls = {
            "decisionView": {"runnerId": rid, "maxRank": 1, "allAbilities": True},
            "observeBattle": {"runnerId": rid},
            "combatSnapshot": {"runnerId": rid},
            "boardGraph": {"runnerId": rid},
            "unitAbilityStates": {"runnerId": rid},
        }
        timings = {}
        payloads = {}
        for m, body in calls.items():
            r = _time_rpc(rpc, m, body, reps)
            payloads[m] = r.pop("payload")
            timings[m] = r
        out["rpc_ms"] = timings

        dv, ob = payloads["decisionView"], payloads["observeBattle"]
        snap, uas = payloads["combatSnapshot"], payloads["unitAbilityStates"]
        out["units_live"] = len([u for u in (ob.get("units") or []) if not u.get("isDead")])
        out["tertiary_rows"] = _tertiary_rows(uas)
        out["load_state_ms"] = _time_load_state(dv, ob, snap, board, uas, reps)

        # LA FRACTION -- c'est elle qui tranche, pas la latence brute.
        capture = sum(timings[m]["median"] for m in ("decisionView", "observeBattle",
                                                     "combatSnapshot", "boardGraph"))
        uas_ms = timings["unitAbilityStates"]["median"]
        out["capture_median_ms"] = capture
        out["uas_median_ms"] = uas_ms
        out["overhead_pct"] = 100.0 * uas_ms / capture if capture else None
        out["ok"] = True
        return out
    finally:
        if not keep:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 40)
            except Exception:                                     # pragma: no cover - diagnostic
                pass


def run_scan() -> dict:
    """VOLET `scan` (offline, sans runner) : QUI appelle `snapshot.load_state`, et qui ne l'appelle
    PAS ?

    POURQUOI CE VOLET EXISTE. Le residu #357-r1 designait « `engine_validate`, `rl_collect_batch` et
    les ~200 call-sites » comme prives du canal. Pour les deux premiers c'est une NON-QUESTION, et
    l'ecrire sans le mesurer serait le meme geste que celui qu'on corrige : ils ne construisent
    JAMAIS de `State` ECS. La face DECISION lit deja le kit declenche par un autre chemin
    (`engine/ai/context.py::live_triggered_ability_ids`, MEME RPC `unitAbilityStates`). Le cout du
    branchement sur un batch est donc NUL -- et ce balayage est ce qui le montre, plutot que de le
    dire.

    L'AST plutot qu'un grep : `rl_duel.py` definit un HOMONYME `_load_state()` (l'etat du duel sur
    disque) qui n'a aucun rapport, et un grep textuel le compterait."""
    import ast as _ast
    root = _PYDIR
    out = {"engine": {}, "outils": {}, "tests": 0, "probes": 0,
           "fichiers_tests": 0, "fichiers_probes": 0}
    for p in sorted(root.rglob("*.py")):
        try:
            tree = _ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:                                   # pragma: no cover - fichier casse
            continue
        n = 0
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Call):
                f = node.func
                name = f.id if isinstance(f, _ast.Name) else (
                    f.attr if isinstance(f, _ast.Attribute) else None)
                if name == "load_state":                      # `_load_state` EXCLU (homonyme)
                    n += 1
        if not n:
            continue
        rel = p.relative_to(root).as_posix()
        if rel.startswith("tests/"):
            out["tests"] += n
            out["fichiers_tests"] += 1
        elif p.name.startswith("probe_"):
            out["probes"] += n
            out["fichiers_probes"] += 1
        elif rel.startswith("engine/"):
            out["engine"][rel] = n
        else:
            out["outils"][rel] = n
    out["total"] = (out["tests"] + out["probes"]
                    + sum(out["engine"].values()) + sum(out["outils"].values()))
    out["batch_tools_sans_load_state"] = [
        f for f in ("rl_collect_batch.py", "engine_validate.py")
        if f not in out["outils"]]
    out["ok"] = True
    return out


def _print_scan(r: dict) -> None:
    print("--- volet scan : %d appels a `snapshot.load_state` (AST, homonyme `_load_state` exclu)"
          % r["total"])
    print("  tests  : %d appels dans %d fichiers" % (r["tests"], r["fichiers_tests"]))
    print("  probes : %d appels dans %d fichiers" % (r["probes"], r["fichiers_probes"]))
    print("  engine/: %s" % (r["engine"] or "AUCUN"))
    print("  outils : %s" % (r["outils"] or "AUCUN"))
    print("  outils de BATCH sans aucun `load_state` : %s"
          % (r["batch_tools_sans_load_state"] or "AUCUN -- le cout du branchement n'est plus nul !"))


def seed_bc_relics() -> dict:
    """ORACLE CONFIG : `{unitId: nom d'ability}` des unites qui portent une `TertiaryAbility` DES LE
    SEED BC. Lu de `data/seed-bc.json` (ENTREE versionnee), pas recopie ici -- une liste en dur se
    perimerait au prochain build sans que rien ne rougisse."""
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    bc = json.loads((_ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    out = {}
    for u in (bc.get("Units") or []):
        ta = u.get("TertiaryAbility")
        if ta:
            try:
                out[u.get("Id")] = TriggeredAbilityType(int(ta)).name
            except ValueError:                        # id hors enum du build -> non nommable
                out[u.get("Id")] = "id:%s" % ta
    return out


def _port_tertiary(dv, ob, snap, board, ability_states) -> dict:
    """`{visualId: (ability, level, mult)}` que le PORT voit apres `load_state`, plus la TRACE du
    canal (`State.ability_states_seed`). `ability_states` suit le tri-etat de `load_state` :
    payload / `None` (AUTO) / `False` (REFUS explicite)."""
    from engine.runner.components import StatsComponent
    from engine.runner.snapshot import load_state

    state = load_state(dv, ob, snap, board=board, ability_states=ability_states)
    seen = {}
    for _uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        ctx = getattr(sc, "ctx", None) if sc is not None else None
        if ctx is None:
            continue
        ta = getattr(ctx, "tertiary_ability", None)
        if ta:
            seen[getattr(ctx, "visual_id", None)] = (
                ta, int(getattr(ctx, "tertiary_ability_level", 0) or 0),
                int(getattr(ctx, "tertiary_ability_variables_multiplier", 100) or 100))
    return {"seen": seen, "trace": state.ability_states_seed}


def run_default(rpc, build_runner=None, keep: bool = False, bind_if_unbound: bool = True) -> dict:
    """VOLET `default` : les QUATRE porteurs de relique du seed arrivent-ils cote port SANS que
    l'appelant demande quoi que ce soit ? Ne LEVE pas -- l'appelant juge.

    Le roster tient les 4 d'un coup (5 slots par camp) : c'est le montage le plus dense possible, et
    il exerce les DEUX camps (deux porteurs joueur, deux porteurs adverses) -- le seed ne doit pas
    dependre du proprietaire.

    ⚠ `bind_if_unbound` -- CE QUE CE PROBE MESURE DEPEND DE LUI, et c'est deliberé :

      `True`  (CLI)   le probe lie le transport ambiant lui-meme s'il ne l'est pas. Il mesure alors
                      le MECANISME (`_auto_ability_states` fait-il ce qu'il dit ?), utile en isolé ;
      `False` (pytest) le probe NE LIE RIEN. Le bras `auto` s'appuie sur le transport que le HARNAIS
                      a lie (`conftest.live_session`). Il mesure alors le BRANCHEMENT -- et c'est
                      lui que la garde doit tenir : un probe qui se lie tout seul resterait vert
                      meme si le conftest debranchait, donc il ne garderait rien.

    Le releve porte `ambient_bound_by` pour que le bras lu soit sans ambiguite."""
    from engine.entities.pathfinding.board import Board
    from engine.runner import snapshot as S

    p_units = SEED_RELIC_UNITS[:2]
    a_units = SEED_RELIC_UNITS[2:]
    out: dict = {"ok": False, "why": None, "p_units": list(p_units), "a_units": list(a_units)}
    out["oracle_config"] = seed_bc_relics()
    out["ambient_bound_by"] = "probe" if (S._LIVE_RPC is None and bind_if_unbound) else \
        ("caller" if S._LIVE_RPC is not None else "personne")

    if build_runner is not None:
        rid = build_runner(SEED, extra=build_args(p_units, a_units))["rid"]
    else:
        rid = _build_subprocess(p_units, a_units)
    out["rid"] = rid
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            out["why"] = "boardGraph indispo"
            return out
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
        uas = rpc("unitAbilityStates", {"runnerId": rid}, 60)

        # ORACLE NATIF : ce que le jeu a REELLEMENT monte (hierarchie 3), par visualId.
        from engine.entities.triggered_ability_type import TriggeredAbilityType
        vis_by_eid = {u.get("entityId"): (u.get("unitConfig") or {}).get("visualId")
                      for u in (snap.get("units") or [])}
        native = {}
        for row in _tertiary_rows(uas):
            try:
                name = TriggeredAbilityType(int(row["abilityId"])).name
            except ValueError:
                name = "id:%s" % row["abilityId"]
            native[vis_by_eid.get(row["entityId"])] = (name, row["level"], row["mult"])
        out["oracle_native"] = native

        # TROIS lectures de la MEME capture. Le cache est purge avant le bras `auto` : le runner
        # vient d'etre bati, aucune entree ne peut valoir pour lui, et une entree d'un rid RECYCLE
        # ferait lire les reliques du runner precedent.
        S.clear_ability_states_cache(S.runner_label(dv, ob, snap) or "")
        pose_par_le_probe = out["ambient_bound_by"] == "probe"
        prev = S.bind_live_rpc(rpc) if pose_par_le_probe else None
        try:
            out["auto"] = _port_tertiary(dv, ob, snap, board, None)
        finally:
            if pose_par_le_probe:
                S.bind_live_rpc(prev)
        out["refused"] = _port_tertiary(dv, ob, snap, board, False)
        out["given"] = _port_tertiary(dv, ob, snap, board, uas)
        out["ok"] = True
        return out
    finally:
        if not keep:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 40)
            except Exception:                                     # pragma: no cover - diagnostic
                pass


def _print_default(r: dict) -> None:
    print("--- volet default : runner=%s ok=%s why=%s" % (r.get("rid"), r.get("ok"), r.get("why")))
    print("  oracle CONFIG (seed-bc) : %s" % (r.get("oracle_config"),))
    if not r.get("ok"):
        return
    print("  oracle NATIF  (hier. 3) : %s" % (r.get("oracle_native"),))
    for bras in ("auto", "refused", "given"):
        b = r[bras]
        print("  [%-8s] trace=%-24s vu=%s"
              % (bras, b["trace"].get("source") if b["trace"] else None, b["seen"]))


def _print(r: dict) -> None:
    print("--- roster %s : runner=%s ok=%s why=%s (unites vivantes=%s)"
          % (r.get("roster"), r.get("rid"), r.get("ok"), r.get("why"), r.get("units_live")))
    if not r.get("ok"):
        return
    print("  RPC (ms, %d mesures, 1er appel exclu) :" % r["reps"])
    for m, t in r["rpc_ms"].items():
        print("    %-18s min=%7.1f  median=%7.1f  mean=%7.1f  max=%7.1f"
              % (m, t["min"], t["median"], t["mean"], t["max"]))
    print("  capture DEJA faite (dv+ob+snap+bg, medianes) = %.1f ms" % r["capture_median_ms"])
    print("  unitAbilityStates                            = %.1f ms  -> +%.1f %% de la capture"
          % (r["uas_median_ms"], r["overhead_pct"]))
    ls = r["load_state_ms"]
    print("  load_state python : sans=%.1f ms  avec=%.1f ms  (delta=%.2f ms)"
          % (ls["sans"]["median"], ls["avec"]["median"],
             ls["avec"]["median"] - ls["sans"]["median"]))
    print("  entrees de hierarchie 3 vues : %s" % (r["tertiary_rows"],))


def main() -> int:
    ap = argparse.ArgumentParser(description="#363 -- cout PUIS branchement du canal ability_states")
    ap.add_argument("--reps", type=int, default=12)
    ap.add_argument("--roster", choices=sorted(ROSTERS), action="append")
    ap.add_argument("--volet", choices=("scan", "cost", "default"), action="append")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    volets = a.volet or ["scan", "cost", "default"]

    rpc = None
    if volets != ["scan"]:                       # le volet `scan` est OFFLINE : pas de session requise
        import rl_collect_batch as R
        sid = R._resolve_session()

        def rpc(method, body=None, timeout=90):  # noqa: F811 - liaison conditionnelle assumee
            return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    results = []
    if "scan" in volets:
        r = run_scan()
        _print_scan(r)
        results.append(r)
    if "cost" in volets:
        for rname in (a.roster or ["2v2", "5v5"]):
            r = run_cost(rpc, roster=rname, reps=a.reps, keep=a.keep)
            _print(r)
            results.append(r)
    if "default" in volets:
        r = run_default(rpc, keep=a.keep)
        _print_default(r)
        results.append(r)
    (_out_dir() / "channel.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 0 if all(r.get("ok") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
