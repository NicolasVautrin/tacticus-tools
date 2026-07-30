#!/usr/bin/env python
"""probe_309_movement_null_action -- MONTAGE NOMME de l'ACTION NULLE : les pas ou le natif emet
`FinishUnitTurnMessage` SEUL.

QUESTION BINAIRE
----------------
Dans un etat ou le natif emet `FinishUnitTurnMessage` (aucun `MoveUnitMessage`, aucun
`ActiveAbilityMessage`), le port emet-il lui aussi une action NULLE ?

CE QUE LE DECOMPILE DIT -- ET CE QU'IL REFUTE (build `rnca9r7q6c`, lu de premiere main)
--------------------------------------------------------------------------------------
L'hypothese de travail etait "le generateur de mouvement porte un gate d'entree, comme
`ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` porte son
`if (HasFlag(unit, 2)) return 0`". **C'est FAUX, et la lecture le tranche** :

1. `IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CGenerateActionsu003Ed__6$$MoveNext`
   ne teste AUCUN flag d'unite. Ses seules sorties a zero action sont
   `UnitPosition.op_Equality(startPosition, null)`, `UnitPosition.IsEmpty(startPosition)`, et
   `<chooser>.Current == null` apres
   `UtilityMovementCase[]` -> le service d'utilite (`<generator+0x28>`).
2. Or `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles` -- ce qui alimente
   l'argument `positions` -- part de `GetMovableTilesFor(unit, ignoreFlags: false, null)` et le
   natif y adjoint la position COURANTE (`BattleQuery$$GetCurrentAndMovablePositionsFor`). Pour une
   unite VIVANTE l'ensemble n'est donc jamais vide : le chooser rend toujours un cas, et le
   generateur rend toujours UNE action. **Le natif se comporte ici exactement comme le port.**

Le filtre est UN CRAN PLUS BAS, dans
`IdunBattle.AI.ActionGenerators.InputBuilder$$GenerateInputMessagesFromUnitAction(action, unit,
currentPosition, options)`, appele par
`IdunBattle.AI.Tactics.DefaultAiUnitTactic.u003CCalculateNextActionForUnitu003Ed__5$$MoveNext`
AVEC UNE ACTION EVENTUELLEMENT NULLE :

    msgs = new List<>()
    if (action != null) {
        if (action.Position != null && !currentPosition.Equals(action.Position))
            msgs.Add(MoveUnitMessage{ unitId, positions })          # <- PAS de move vers SA tuile
        if (action.Target != null)
            msgs.Add(ActiveAbilityMessage{ unitId, targetId, abilityType })
    }
    if (options[0] != 0) return msgs                                # court-circuit (options = {0,0,0} ici)
    if (msgs.Count != 0) return msgs
    msgs.Add(FinishUnitTurnMessage{ unitId })                       # <=== L'ACTION NULLE
    return msgs

**Trois enseignements, tous lus, aucun deduit :**

* le tactic sort de sa double boucle avec `action == null` quand AUCUN generateur ne produit --
  il appelle quand meme `ABaseAiActorTactic$$LogInvalidUnitAction(this, unit, action)` puis
  `InputBuilder`, qui rend le `FinishUnitTurnMessage` ;
* une action NON nulle rend AUSSI `FinishUnitTurnMessage` des lors qu'elle ne bouge pas
  (`action.Position` == position courante) et ne cible rien. C'est le cas MAJORITAIRE, et c'est
  celui que l'analogie "gate d'entree" aurait manque ;
* une action d'ability porte toujours `action.Target != null` -- **y compris la route a cibles
  TUILE de #302** (`UnitAction..ctor(position, target, abilityType)` prend un `IEntity` non type,
  une entite-tuile passe par le MEME slot). Le mirror pose ici ne peut donc pas la couvrir par
  accident. Le probe ne le SUPPOSE pas : le mode `--noreg` INSTRUMENTE le mirror et ventile PAR
  KIND ce qu'il intercepte -- une seule interception de kind `ability` serait une regression.

L'ANGLE MORT QUI L'A CACHE
--------------------------
`engine_validate.run_agreement` ne compare que `if (nat["move"] or nat["ability"])` : un pas
`finish` seul est logge "non compare, on avance". Aucune metrique existante ne pouvait donc
rougir -- degradation strictement PERMISSIVE.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_309_movement_null_action.py                       # MC1_67 / 12100, DEUX bras
    python probe_309_movement_null_action.py --seed 909            # le second montage nomme
    python probe_309_movement_null_action.py --noreg               # non-regression par MUTATION
    python probe_309_movement_null_action.py --scan 777,909,31337  # choisir un montage, sur MESURE

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc            # noqa: E402

BOARD = "MC1_67"
SEED = 12100
RANK = 17
STEPS = 40


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed: int, board: str) -> int:
    """Runner ISOLE au roster tire par la SEED (pas de `--p-units`) : le montage nomme est le
    couple (board, seed), et il est reproductible tel quel."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state_file), "--board", board, "--rank", str(RANK)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-500:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _origin_of(dv, uid):
    row = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
    p = (row or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _classify(eng, origin) -> str:
    """A QUEL ETAGE se joue ce pas ? Decouvert A LA MESURE, et decisif : "le natif finit le tour"
    recouvre TROIS situations qui se corrigent a des endroits OPPOSES.

    * `mirror`  -- le port propose une action qui n'emettrait AUCUN message natif (destination
                   absente, ou EGALE a la tuile courante). C'est le perimetre de #309 : avec le
                   mirror actif, ces pas doivent devenir `finish`.
    * `scoring` -- le port propose un deplacement REEL vers une AUTRE tuile. `InputBuilder`
                   emettrait alors un `MoveUnitMessage` : le mirror est FIDELE en le laissant
                   passer. Le desaccord est en AMONT, dans le CHOIX de tuile
                   (`move.best_move_faithful` vs le chooser d'utilite natif). Hors perimetre.
    * `ability` -- le port propose un cast. `InputBuilder` emet toujours un `ActiveAbilityMessage`
                   des que `action.Target != null` ; si le natif n'emet rien, ses generateurs
                   d'ability n'ont rien produit. Hors perimetre, en amont lui aussi.

    Un mirror qui "corrigerait" `scoring` ou `ability` masquerait un defaut derriere un autre."""
    kind = eng.get("kind")
    if kind == "ability":
        return "ability"
    if kind == "finish":
        return "mirror"
    to = eng.get("to")
    if to is None or (origin is not None and tuple(to) == tuple(origin)):
        return "mirror"
    return "scoring"


def _why(eng, origin, mov_row) -> str:
    """Le detail lisible du pas, pour qu'un desaccord se diagnostique sans relancer."""
    if eng.get("kind") == "finish":
        return "accord"
    if eng.get("kind") == "ability":
        return "ability proposee (cible=%s) -- AMONT, pas la traduction en messages" % eng.get("target")
    to = eng.get("to")
    if to is None:
        return "move vers None (branche `not move_tiles or not enemies`)"
    if origin is not None and tuple(to) == tuple(origin):
        return "move vers SA PROPRE tuile %s (InputBuilder n'emet pas de MoveUnitMessage)" % (to,)
    return "move REEL vers %s (origine %s, movable=%d) -- SCORING, pas la traduction" % (
        to, origin, len((mov_row or {}).get("tiles") or []))


def _native_chunk(action: dict) -> dict:
    import engine_validate as EV
    return EV.native_chunk(action or {})


def _apply_native(sid, rid, messages) -> None:
    acts = []
    for m in (messages or []):
        cls = m.get("cls")
        if cls == "MoveUnitMessage":
            acts.append({"kind": "move", "unitId": m["unitId"],
                         "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
        elif cls == "ActiveAbilityMessage":
            acts.append({"kind": "ability", "casterId": m["casterId"],
                         "targetId": m.get("targetId"), "abilityType": m["abilityType"]})
        elif cls == "FinishUnitTurnMessage":
            acts.append({"kind": "finish", "unitId": m["unitId"]})
    if acts:
        _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 40)


def walk(sid, rid, steps: int, neutralise: bool = False, verbose: bool = True) -> dict:
    """Marche la trajectoire NATIVE et confronte le port **sur les pas que `run_agreement` ne
    compare pas** : ceux ou le chunk natif est un `FinishUnitTurnMessage` SEUL.

    `neutralise` = CONTRE-EPREUVE : le mirror d'`InputBuilder` est court-circuite, ce qui rejoue
    exactement le port d'AVANT le correctif. Sans elle, "le port rend finish" pourrait venir de
    n'importe ou et la garde serait vide."""
    import engine_validate as EV
    from engine.ai import tactic as T
    from engine import weights
    from engine.playbook import scene as _scene

    wt = weights.load()
    predictor = _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t), rid)
    orig_builder = getattr(T, "input_messages_from_unit_action", None)
    if neutralise:
        if orig_builder is None:
            raise RuntimeError("`tactic.input_messages_from_unit_action` absent -- rien a "
                               "neutraliser : ce bras ne mesure pas ce qu'il pretend")
        T.input_messages_from_unit_action = lambda ctx, action: (
            action if action is not None else {"kind": "move", "to": None})
    rows: list = []
    n_finish = n_move = n_ab = 0
    try:
        for step in range(steps):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 40)
            if not dry.get("ok") or not dry.get("hasNext"):
                break
            act = dry.get("action") or {}
            nat = _native_chunk(act)
            uid = dry.get("activatedUnitId") or nat.get("unit")
            if nat["move"]:
                n_move += 1
            if nat["ability"]:
                n_ab += 1
            # LE PAS QUI NOUS INTERESSE : action NULLE cote natif.
            if nat["finish"] and not nat["move"] and not nat["ability"] and uid is not None:
                n_finish += 1
                dv = _r(sid, "decisionView",
                        {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
                mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
                mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
                if predictor is not None:
                    _scene.refresh_shields(predictor, lambda m, b, t: _r(sid, m, b, t), rid)
                eng = EV.engine_decide(sid, rid, dv, mov_by_unit, uid, wt, predictor)
                origin = _origin_of(dv, uid)
                row = {"step": step, "uid": uid, "origin": origin,
                       "engine_kind": eng.get("kind"), "engine_to": eng.get("to"),
                       "engine_ability": eng.get("ability"), "engine_target": eng.get("target"),
                       "movable": len((mov_by_unit.get(uid) or {}).get("tiles") or []),
                       "agree": eng.get("kind") == "finish",
                       "scope": _classify(eng, origin),
                       "why": _why(eng, origin, mov_by_unit.get(uid))}
                rows.append(row)
                if verbose:
                    print("  step %2d u%s: natif=FINISH SEUL | port=%s to=%s [%s/%s] %s"
                          % (step, uid, row["engine_kind"], row["engine_to"],
                             "ACCORD" if row["agree"] else "MISS", row["scope"], row["why"]))
            _apply_native(sid, rid, act.get("messages"))
    finally:
        if neutralise and orig_builder is not None:
            T.input_messages_from_unit_action = orig_builder
    # VENTILATION DES MISS PAR CAUSE -- decisive, et decouverte a la mesure (C1_03/4242 step 13).
    # "le natif finit le tour" a PLUSIEURS causes, et elles se corrigent a des etages opposes :
    #   * le port propose un MOVE  -> c'est le perimetre de #309 : `InputBuilder` n'emet pas de
    #     `MoveUnitMessage` vers la tuile courante (ni pour une destination absente), donc la liste
    #     est vide et le natif finit le tour. C'est ce que le mirror corrige.
    #   * le port propose une ABILITY -> HORS PERIMETRE. `InputBuilder` emet TOUJOURS un
    #     `ActiveAbilityMessage` des que `action.Target != null` ; si le natif n'emet rien, c'est
    #     que SES generateurs d'ability n'ont rien produit. Le desaccord est donc en AMONT (gate
    #     d'ability, cooldown, cible refusee), pas dans la traduction en messages. Le mirror ne
    #     doit surtout PAS l'avaler : ce serait masquer un defaut derriere un autre.
    miss = [r for r in rows if not r["agree"]]
    return {"rows": rows, "n_finish": n_finish, "n_move": n_move, "n_ability": n_ab,
            "n_agree": sum(1 for r in rows if r["agree"]),
            "n_miss_move": sum(1 for r in miss if r["engine_kind"] == "move"),
            "n_miss_ability": sum(1 for r in miss if r["engine_kind"] == "ability"),
            # PERIMETRE DU MIRROR (cf. `_classify`) : les pas dont l'action du port n'emettrait
            # AUCUN message natif. Les pas `scoring` et `ability` sont d'autres etages -- les
            # compter ici gonflerait artificiellement ce que cette tranche pretend couvrir.
            "n_in_scope": sum(1 for r in rows if r["scope"] == "mirror"),
            "by_scope": {s: sum(1 for r in rows if r["scope"] == s)
                         for s in ("mirror", "scoring", "ability")}}


def scan(seeds, board: str, steps: int, verbose: bool = True) -> list:
    """Balaie des couples (board, seed) et rend, pour chacun, le nombre de pas d'ACTION NULLE et
    leur ventilation. Sert a CHOISIR un second montage qui exhibe reellement le cas de #309 (port
    proposant un MOVE) plutot que le cas hors perimetre (port proposant une ABILITY).

    Un runner a la fois (bras cable seul), dispose immediatement."""
    sid = _resolve_session()
    out = []
    for seed in seeds:
        rid = None
        try:
            rid = _build(ROOT / "logs" / ("probe_309_scan_%s_%d.json" % (board, seed)), seed, board)
            w = walk(sid, rid, steps, neutralise=False, verbose=False)
            row = {"board": board, "seed": seed, "n_finish": w["n_finish"],
                   "in_scope": w["n_in_scope"], "miss_move": w["n_miss_move"],
                   "miss_ability": w["n_miss_ability"], "agree": w["n_agree"],
                   "by_scope": w["by_scope"]}
            out.append(row)
            if verbose:
                print("  %-8s seed %-6d : finish=%d | par etage %s | agree=%d"
                      % (board, seed, row["n_finish"], row["by_scope"], row["agree"]))
        except RuntimeError as exc:
            if verbose:
                print("  %-8s seed %-6d : MONTAGE KO (%s)" % (board, seed, exc))
        finally:
            if rid is not None:
                _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    return out


def noreg(sid, rid, steps: int, mirror: bool, verbose: bool = True) -> dict:
    """NON-REGRESSION PAR MUTATION. Rejoue le walk d'agreement de reference
    (`engine_validate.run_agreement`, les metriques pos/ability/stay) avec le mirror ACTIF puis
    NEUTRALISE. Les deux doivent rendre des chiffres IDENTIQUES : le mirror ne doit toucher QUE des
    pas que cette metrique ne compare pas (`if (nat["move"] or nat["ability"])`).

    En prime il INSTRUMENTE le mirror et ventile PAR KIND ce qu'il intercepte. Une interception de
    kind `ability` signifierait qu'une action de cast (route a cibles TUILE #302 comprise) a ete
    transformee en fin de tour -- exactement la regression que ce port ne doit pas introduire."""
    import engine_validate as EV
    from engine.ai import tactic as T
    from engine import weights

    orig = T.input_messages_from_unit_action
    tally = {"calls": 0, "intercepted": {}, "kept": {}}

    def counted(ctx, action):
        tally["calls"] += 1
        out = orig(ctx, action) if mirror else (
            action if action is not None else {"kind": "move", "to": None})
        k = "none" if action is None else str(action.get("kind"))
        bucket = "intercepted" if out is not action else "kept"
        tally[bucket][k] = tally[bucket].get(k, 0) + 1
        return out

    T.input_messages_from_unit_action = counted
    try:
        res = EV.run_agreement(sid, rid, steps, weights.load(),
                               log=(print if verbose else (lambda *_a, **_k: None)))
    finally:
        T.input_messages_from_unit_action = orig
    return {"pos": res["pos"], "ability": res["ability"], "stay": res["stay"], "tally": tally}


def run(seed: int = SEED, board: str = BOARD, steps: int = STEPS, keep: bool = False,
        both_arms: bool = True, verbose: bool = True) -> dict:
    """Monte le runner, marche, mesure. Deux bras sur DEUX runners identiques (le walk MUTE
    l'etat : rejouer le second bras sur le meme runner ne mesurerait pas le meme etat)."""
    sid = _resolve_session()
    out: dict = {"seed": seed, "board": board, "steps": steps}
    rids: list = []
    try:
        sf = ROOT / "logs" / ("probe_309_%s_%d.json" % (board, seed))
        rid = _build(sf, seed, board)
        rids.append(rid)
        if verbose:
            print("[309] runner=%d seed=%d board=%s -- bras CABLE" % (rid, seed, board))
        out["cable"] = walk(sid, rid, steps, neutralise=False, verbose=verbose)
        out["rid_cable"] = rid
        if both_arms:
            sf2 = ROOT / "logs" / ("probe_309_%s_%d_n.json" % (board, seed))
            rid2 = _build(sf2, seed, board)
            rids.append(rid2)
            if verbose:
                print("[309] runner=%d -- bras NEUTRALISE (le port d'AVANT le correctif)" % rid2)
            out["neutralise"] = walk(sid, rid2, steps, neutralise=True, verbose=verbose)
            out["rid_neutralise"] = rid2
        return out
    except RuntimeError as exc:
        return {"error": str(exc), "seed": seed, "board": board}
    finally:
        if not keep:
            for rid in rids:
                _r(sid, "disposeRunner", {"runnerId": rid}, 30)


def run_noreg(seed: int = SEED, board: str = BOARD, steps: int = STEPS,
              keep: bool = False, verbose: bool = True) -> dict:
    """Les DEUX bras de non-regression, sur deux runners identiques (le walk MUTE l'etat)."""
    sid = _resolve_session()
    rids: list = []
    try:
        a = _build(ROOT / "logs" / ("probe_309_nr_%s_%d_a.json" % (board, seed)), seed, board)
        rids.append(a)
        with_mirror = noreg(sid, a, steps, mirror=True, verbose=verbose)
        b = _build(ROOT / "logs" / ("probe_309_nr_%s_%d_b.json" % (board, seed)), seed, board)
        rids.append(b)
        without = noreg(sid, b, steps, mirror=False, verbose=verbose)
        return {"seed": seed, "board": board, "steps": steps,
                "with_mirror": with_mirror, "without_mirror": without}
    except RuntimeError as exc:
        return {"error": str(exc), "seed": seed, "board": board}
    finally:
        if not keep:
            for rid in rids:
                _r(sid, "disposeRunner", {"runnerId": rid}, 30)


def _print_noreg(res: dict) -> int:
    a, b = res["with_mirror"], res["without_mirror"]
    print("\n=== NON-REGRESSION (%s / seed %d, %d pas) ===" % (res["board"], res["seed"],
                                                              res["steps"]))
    same = True
    for k in ("pos", "ability", "stay"):
        print("  %-8s AVEC mirror=%s | SANS=%s%s"
              % (k, a[k], b[k], "" if a[k] == b[k] else "   <== DIVERGE"))
        same = same and a[k] == b[k]
    print("  mirror : %d appels | intercepte=%s | conserve=%s"
          % (a["tally"]["calls"], a["tally"]["intercepted"], a["tally"]["kept"]))
    bad = a["tally"]["intercepted"].get("ability", 0)
    print("  interceptions de kind `ability` = %d (doit etre 0 -- sinon un cast est perdu)" % bad)
    return 0 if (same and bad == 0) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--steps", type=int, default=STEPS)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--one-arm", action="store_true", help="bras CABLE seul (pas de contre-epreuve)")
    ap.add_argument("--noreg", action="store_true",
                    help="non-regression par MUTATION sur le walk d'agreement de reference")
    ap.add_argument("--scan", help="liste de seeds separees par des virgules (choix d'un montage)")
    a = ap.parse_args()
    if a.scan:
        rows = scan([int(s) for s in a.scan.split(",") if s.strip()], a.board, a.steps)
        cand = [r for r in rows if r["in_scope"] > 0]
        print("\n  montages exhibant le cas DE #309 (port -> move/finish) : %s"
              % ([(r["board"], r["seed"], r["in_scope"]) for r in cand] or "AUCUN"))
        return 0 if cand else 1
    if a.noreg:
        res = run_noreg(seed=a.seed, board=a.board, steps=a.steps, keep=a.keep)
        if "error" in res:
            print("[309] MONTAGE NON INSTALLE : %s" % res["error"], file=sys.stderr)
            return 2
        return _print_noreg(res)
    res = run(seed=a.seed, board=a.board, steps=a.steps, keep=a.keep, both_arms=not a.one_arm)
    if "error" in res:
        print("[309] MONTAGE NON INSTALLE : %s" % res["error"], file=sys.stderr)
        return 2
    c = res["cable"]
    print("\n=== VERDICT (%s / seed %d, %d pas) ===" % (res["board"], res["seed"], res["steps"]))
    print("  pas natifs      : move=%d ability=%d FINISH SEUL=%d"
          % (c["n_move"], c["n_ability"], c["n_finish"]))
    print("  ventilation     : %s" % c["by_scope"])
    if not c["n_finish"]:
        print("  AUCUN pas d'action nulle sur ce montage -- il ne mesure RIEN, en changer")
        return 3
    if not c["n_in_scope"]:
        print("  aucun pas DANS LE PERIMETRE du mirror (les %d pas sont d'un autre etage)"
              % c["n_finish"])
        return 3
    print("  bras CABLE      : %d/%d accords DANS LE PERIMETRE" % (c["n_agree"], c["n_in_scope"]))
    if "neutralise" in res:
        n = res["neutralise"]
        print("  bras NEUTRALISE : %d/%d accords (contre-epreuve : doit etre 0)"
              % (n["n_agree"], n["n_in_scope"]))
    return 0 if c["n_agree"] == c["n_in_scope"] else 1


if __name__ == "__main__":
    sys.exit(main())
