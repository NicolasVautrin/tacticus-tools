#!/usr/bin/env python
"""Probe R1-b (etage NATIF) -- l'ORDRE d'evaluation des positions candidates, LU SUR LE NATIF.

QUESTION BINAIRE : dans quel ORDRE `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`
presente-t-il les positions candidates au `Bucket` (keep-first), et deux positions a utilite EGALE
cote PORT le sont-elles aussi cote NATIF ?

Sans cette mesure on ne peut PAS distinguer les deux diagnostics concurrents d'une divergence de
tuile a utilite portee egale :
  (1) ORDRE DE SWEEP faux  -- le natif evalue les tuiles dans un autre ordre ;
  (2) UTILITE PAR TUILE fausse -- le natif SEPARE strictement deux tuiles que le port egalise.
Fitter l'ordre pour couvrir (2) est exactement l'anti-pattern " ajuster un scalaire ".

CE QUE LA PROBE LIT (hooks EXISTANTS, aucune reinjection) :
  * `scorerUtilTraceDump` -> un event par appel de `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`,
    avec la TUILE CASTER decodee (`UnitPosition` param_4) et l'utilite rendue. La SEQUENCE de ces
    events EST l'ordre d'evaluation natif -- `EvaluateInternal` boucle les cibles a position fixe,
    donc la suite des tuiles DISTINCTES par premiere apparition = l'ordre de la liste `tiles`.
  * `scorerTileTermTraceDump` -> le terme de TUILE complet (composite Tile(7) via
    `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromTilePrediction`)
    par candidat : c'est LUI qui separe (ou non) deux tuiles a meme degat et meme elevation.

Les hooks RVA sont BUILD-SPECIFIQUES (gqfc5mff6c) : la probe verifie le hash avant d'armer, arme
pour UN SEUL `aiStepDryRun`, puis DESARME (`scorerDamageTraceOff`).

ASCII only. Usage :
  python probe_r1b_native_sweep_order.py --seed 999 --board C4_09 --step 14
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_193c_move_playbook_terms as P193C  # noqa: E402
from build_pin import BuildPinRefused  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]


def _exiger_build_des_rva() -> None:
    """Refuse si les RVA en dur du hook ne valent pas pour le build INSTALLE.

    ⚠ DELEGUE a la declaration unique de #193c, et surtout PAS une copie. Ce corps portait
    le litteral `rnca9r7q6c` et le refus l'a SURVECU : la docstring d'alors racontait
    justement cette faute -- << il valait `gqfc5mff6c` alors que #257 avait deja migre les RVA
    vers `rnca9r7q6c` >> -- puis a ete recopiee telle quelle, litteral compris, et la migration
    #1129 vers `t6dpr4k06g` l'a perimee a son tour. Une prose qui raconte le vice ne l'empeche
    pas ; seule la delegation le rend impossible.
    """
    P193C._exiger_build_des_rva()


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(seed, board, extra):
    state = ROOT / "logs" / "runners" / f"probeR1bN-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--board", board, "--state-file", str(state)] + list(extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO:", (p.stderr or p.stdout or "")[-400:])
        return None, None
    return json.loads(state.read_text())["runnerId"], state


def _apply_native(sid, rid, dry):
    acts = []
    for m in (dry["action"]["messages"]):
        if m.get("cls") == "MoveUnitMessage":
            acts.append({"kind": "move", "unitId": m["unitId"],
                         "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
        elif m.get("cls") == "ActiveAbilityMessage":
            acts.append({"kind": "ability", "casterId": m["casterId"],
                         "targetId": m.get("targetId"), "abilityType": m["abilityType"]})
        elif m.get("cls") == "FinishUnitTurnMessage":
            acts.append({"kind": "finish", "unitId": m["unitId"]})
    for a in acts:
        _r(sid, "applyAction", {"runnerId": rid, "action": a}, 90)
    return len(acts)


def _first_seen(seq_tiles):
    out, seen = [], set()
    for t in seq_tiles:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _dry_signature(dry):
    """Empreinte d'un pas natif : (unite activee, messages). Sert de GARDE contre le no-op
    d'`applyAction` (ok=True sans muter) : deux pas consecutifs a empreinte IDENTIQUE = l'etat
    n'a pas bouge, la trajectoire est fausse et tout ce qu'on mesurerait ensuite est du bruit."""
    msgs = ((dry.get("action") or {}).get("messages") or [])
    return (dry.get("activatedUnitId"),
            tuple(sorted(json.dumps(m, sort_keys=True) for m in msgs)))


def run(sid, rid, target_step):
    # --- avance jusqu'au pas cible sur la trajectoire NATIVE -------------------
    uid = None
    prev_sig = None
    for step in range(target_step):
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            print(f"native epuise au pas {step} ({dry.get('error')})")
            return 1
        sig = _dry_signature(dry)
        if sig == prev_sig:
            print(f"GARDE NO-OP : pas {step} identique au precedent (u{dry.get('activatedUnitId')}) "
                  f"-- applyAction n'a rien mute, mesure ABANDONNEE")
            return 1
        prev_sig = sig
        _apply_native(sid, rid, dry)

    # --- etat de DECISION du pas cible ---------------------------------------
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    plans = {p.get("unitId"): p for p in (dv.get("attackPlans") or [])}

    # --- ARME les hooks RVA le temps d'UN SEUL dry-run ------------------------
    on = _r(sid, "scorerDamageTraceOn", {"runnerId": rid}, 90)
    print("scorerDamageTraceOn:", json.dumps(on)[:200])
    _r(sid, "scorerDamageTraceClear", {"runnerId": rid, "stacks": 0}, 60)
    try:
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 90)
        util = _r(sid, "scorerUtilTraceDump", {"runnerId": rid, "max": 4000}, 90)
        tterm = _r(sid, "scorerTileTermTraceDump", {"runnerId": rid, "max": 4000}, 90)
        elev = _r(sid, "scorerElevTraceDump", {"runnerId": rid, "max": 4000}, 90)
        leaf = _r(sid, "scorerLeafTraceDump", {"runnerId": rid, "max": 4000}, 90)
        comp = _r(sid, "scorerComposedDump", {}, 90)
    finally:
        _r(sid, "scorerDamageTraceOff", {"runnerId": rid}, 60)

    uid = dry.get("activatedUnitId")
    msgs = (dry.get("action") or {}).get("messages") or []
    nat_move = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
    nat_ab = next((m for m in msgs if m.get("cls") == "ActiveAbilityMessage"), None)
    me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
    mpos = ((me or {}).get("pos") or {})
    origin = (mpos.get("col"), mpos.get("row")) if mpos.get("col") is not None else None
    nat_tile = ((nat_move["to"]["col"], nat_move["to"]["row"]) if nat_move else origin)

    print(f"\n===== PAS {target_step} : u{uid} ({(me or {}).get('visualId')}) origin={origin} =====")
    print(f"  natif : move={nat_tile if nat_move else None} "
          f"ability={(nat_ab or {}).get('abilityType')} tgt={(nat_ab or {}).get('targetId')}")

    # --- ROSTER (correlation des feuilles de tuile qui comptent des unites voisines) ----------
    # `alive` vient de decisionView (les CADAVRES y restent -- cf. decisionview_keeps_dead) :
    # c'est le champ que lit le port (`engine.ai.context._enemies`/`fpos`), pas une absence.
    print("\n  UNITES (id / visualId / camp / pos / alive / effets) :")
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        effs = [e.get("name") if isinstance(e, dict) else e for e in (u.get("effects") or [])]
        print(f"    u{u.get('id'):<4} {str(u.get('visualId')):<22} "
              f"{'ALLY ' if u.get('ctrl') else 'ENEMY'} "
              f"pos=({p.get('col')},{p.get('row')}) alive={bool(u.get('alive'))} eff={effs}")

    move_tiles = [(t["col"], t["row"]) for t in ((mov_by_unit.get(uid) or {}).get("tiles") or [])]
    action_tiles = ([origin] if origin else []) + [t for t in move_tiles if t != origin]
    print(f"\n  action_tiles (PORT = [origine] + aiMovableTiles) :\n    {action_tiles}")

    seen, ranked_union = set(), []
    for ev in ((plans.get(uid) or {}).get("evals") or []):
        for rk in (ev.get("ranked") or []):
            t = (rk.get("col"), rk.get("row"))
            if t[0] is not None and t not in seen:
                seen.add(t)
                ranked_union.append(t)
    print(f"\n  ranked (union, ordre GetBestTileToAttackFrom) :\n    {ranked_union}")

    ents = util.get("entries") or []
    print(f"\n  scorerUtilTrace : utilInstalled={util.get('utilInstalled')} "
          f"bufferSize={util.get('bufferSize')} entries={len(ents)}")
    if not ents:
        print("  !! AUCUN event -- hook non arme / RVA fausse / pas de tier Comparable a ce pas")
        return 1
    seq_tiles = [(e.get("casterCol"), e.get("casterRow")) for e in ents]
    native_order = _first_seen([t for t in seq_tiles if t[0] is not None and t[0] >= 0])
    print(f"\n  ORDRE NATIF d'evaluation (1re apparition par tuile, {len(ents)} appels) :\n"
          f"    {native_order}")
    print(f"  == action_tiles ? {native_order == [t for t in action_tiles if t in set(native_order)]}")
    print(f"  == ranked ?      {native_order == [t for t in ranked_union if t in set(native_order)]}")

    print("\n  UTILITE NATIVE par appel (seq, tuile, cibles, utility) :")
    for e in ents:
        print(f"    #{e.get('seq'):<5} {(e.get('casterCol'), e.get('casterRow'))} "
              f"tgts={e.get('targets')} u={e.get('utility')}")

    tents = tterm.get("entries") or []
    print(f"\n  scorerTileTermTrace : tileTermInstalled={tterm.get('tileTermInstalled')} "
          f"entries={len(tents)}")
    for e in tents:
        print(f"    #{e.get('seq'):<5} {(e.get('casterCol'), e.get('casterRow'))} "
              f"tileTerm={e.get('tileTerm', e.get('value'))}")

    # --- DECOMPOSITION du terme de tuile : feuille Elevation + feuilles situationnelles -------
    eents = elev.get("entries") or []
    print(f"\n  scorerElevTrace : elevInstalled={elev.get('elevInstalled')} entries={len(eents)}")
    for e in eents[:40]:
        print(f"    #{e.get('seq'):<5} {e}")
    lents = leaf.get("entries") or []
    print(f"\n  scorerLeafTrace : leafInstalled={leaf.get('leafInstalled')} entries={len(lents)}")
    for e in lents[:60]:
        print(f"    #{e.get('seq'):<5} {e}")
    print(f"\n  scorerComposedDump : composedInstalled={comp.get('composedInstalled')}")
    for c in (comp.get("composites") or []):
        print(f"    ptr={c.get('ptr')} count={c.get('count')}")
        print(f"      children={c.get('children')}")

    # --- DECOMPOSITION PAR ETAGE du terme de tuile ------------------------------------------
    # Tile(7) = SOMME des feuilles du composite. Les hooks existants en donnent DEUX
    # (`Elevation` via scorerElevTrace, `TileEffects` via scorerLeafTrace) + le TOTAL
    # (scorerTileTermTrace). Le RESTE = X, la somme des feuilles NON instrumentees --
    # c'est exactement le residu N13 (0..25 par tuile, position-dependant). On ne fitte
    # AUCUN scalaire : on isole l'etage, on le nomme ensuite au decompile.
    def _by_tile(entries, ck, rk, vk):
        out = {}
        for e in entries:
            t = (e.get(ck), e.get(rk))
            if t[0] is None or t[0] < 0:
                continue
            out.setdefault(t, set()).add(round(float(e.get(vk) or 0.0), 4))
        return out

    # NB : le champ `ret` du hook de feuille generique n'est PAS fiable (registre non nettoye
    # sur ces corps d'iterateur) -- on ne le filtre PAS ; la valeur yieldee, elle, est stable
    # sur les 2 events emis par tuile (verifie : ensembles a 1 element).
    tt = _by_tile(tents, "casterCol", "casterRow", "tileTerm")
    el = _by_tile(eents, "col", "row", "leaf")
    te = _by_tile([e for e in lents if e.get("leaf") == "TileEffects"], "col", "row", "value")
    print("\n  DECOMPOSITION Tile(7) par tuile (X = total - Elevation - TileEffects) :")
    print("    tuile      Tile(7)      Elevation   TileEffects   X(residu)")
    for t in native_order:
        def one(d, default=None):
            v = d.get(t)
            if not v:
                return default
            return sorted(v)[0] if len(v) == 1 else sorted(v)
        vt, ve, vf = one(tt), one(el), one(te, 0.0)
        x = (vt - ve - vf) if isinstance(vt, float) and isinstance(ve, float) \
            and isinstance(vf, float) else None
        print(f"    {str(t):<10} {str(vt):<12} {str(ve):<11} {str(vf):<13} {x}")

    # --- VOISINAGE par tuile candidate : de quoi confronter TOUTE feuille qui compte des
    # unites autour de la tuile (TriggeredAbilities(2) AdjacentUnitPreference R1,
    # AstartesBanner/FirstAmongTraitors R=range hex, KustomForceField/Savior R1, ...).
    # `selfIn2` = le MOVER lui-meme (il est encore a son origine pendant l'evaluation :
    # les queries natives sont par TUILE, elles ne l'excluent pas d'office).
    import hexgeo   # noqa: E402
    alive = [u for u in (dv.get("units") or [])
             if u.get("alive") and (u.get("pos") or {}).get("col") is not None]
    mine = bool((me or {}).get("ctrl"))
    others = [u for u in alive if u.get("id") != uid]
    friends = [u for u in others if bool(u.get("ctrl")) == mine]
    foes = [u for u in others if bool(u.get("ctrl")) != mine]
    print("\n  VOISINAGE par tuile (d = hexgeo.distance, unites VIVANTES, self exclu) :")
    print("    tuile      amis<=1 amis<=2 enn<=1 enn<=2 d(origine)  | distance a chaque ami")
    hdr = "  ".join(f"u{u.get('id')}" for u in friends)
    print(f"    {'':<10} {'':<38}| {hdr}")
    for t in native_order:
        def cnt(us, rad):
            return sum(1 for u in us
                       if hexgeo.distance(t, (u["pos"]["col"], u["pos"]["row"])) <= rad)
        ds = "  ".join(f"{hexgeo.distance(t, (u['pos']['col'], u['pos']['row'])):>3}"
                       for u in friends)
        print(f"    {str(t):<10} {cnt(friends,1):<7} {cnt(friends,2):<7} {cnt(foes,1):<6} "
              f"{cnt(foes,2):<6} {hexgeo.distance(t, origin) if origin else -1:<11} | {ds}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--seed", default="999")
    ap.add_argument("--board", default="C4_09")
    ap.add_argument("--step", type=int, default=14)
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[])
    args = ap.parse_args()
    try:
        _exiger_build_des_rva()
    except BuildPinRefused as exc:
        print(str(exc))
        return 2
    sid = _resolve_session()
    if args.runner is not None:
        print(f"runner {args.runner} (existant, non dispose)")
        return run(sid, args.runner, args.step)
    rid, state = _build(args.seed, args.board, args.extra)
    if rid is None:
        return 1
    print(f"runner {rid} seed={args.seed} board={args.board} step={args.step}")
    try:
        return run(sid, rid, args.step)
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        try:
            state.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
