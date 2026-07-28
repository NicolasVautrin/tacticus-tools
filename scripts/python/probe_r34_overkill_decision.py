#!/usr/bin/env python
"""Probe R34 -- la face DECISION de l'overkill.

`IdunBattle.Core.Services.DamagePredictionResult$$MightBeOverkill` appelle la surcharge PRIVEE
8-args `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` en lui passant, au 3e argument
(`isCritical`), le champ `MightCrit@+0xb1` du resultat -- la ou
`IdunBattle.Core.Services.DamagePredictionResult$$WillBeOverkill` passe **0 EN DUR** (litteral lu au
desassemblage). Le port passait 0 des DEUX cotes : la borne OPTIMISTE de l'IA
(`PossibleOverkill` = utilite 37) sous-estimait tout kill CRITIQUE sous le seuil.

TROIS MESURES, TROIS ETAGES (aucune ne suffit seule) :

  A. SOURCE du flag (`--part source`) -- d'ou vient `MightCrit` ? Correlation LIVE entre
     `aiPredict.pred.mightCrit` (= `DamagePredictionResult.MightCrit@+0xb1`, lu par le hook
     `rpc-predict.ts`) et `IdunBattle.Core.Services.DamageCalculations$$CouldCrit(attacker)` =
     `GetStat(CritChance=9) >= 1 && GetStat(CritDamage=10) > 0`, calcule des stats
     `combatSnapshot`. Deux builds contrastes (`--crit 0,0` / `--crit 100,1`) + un build NATUREL
     (stats de roster non patchees) : c'est la paire contrastee qui interdit de conclure d'une
     correlation triviale (tout a 1 ou tout a 0).

  B. CANAL D'UTILITE (`--part utility`) -- le flag change-t-il l'utilite que le port attribue a
     une paire (unite, cible) ? On isole la FORMULE du FEED : les DEUX cotes sont nourris des
     **memes predictions NATIVES** (`aiPlaybookPredict`, dont le decodeur expose deja
     `mightCrit@event+0xb9`), et le natif est le scorer invoque en direct
     (`pairUtility` = `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`).
     Tout ecart est donc un gap de LOGIQUE, jamais de prediction.
     REGIME OBLIGATOIRE : `PV <= degat < 2 x PV` (letal MAIS sous `overkillDmgPctOfHealth` = 100).
     Hors de ce regime l'overkill est NATUREL et le flag ne sert a rien -- c'est exactement le
     piege paye sur la face COMBAT (#R33).

  C. CLASSEMENT (`--part rank`) -- le terme `PossibleOverkill` deplace-t-il le CHOIX ? Deux cibles
     dont une seule est dans le regime letal-sous-le-seuil : on compare l'ORDRE natif
     (`pairUtility`) a l'ORDRE du port, avant et apres. Un fix qui bouge un scalaire sans jamais
     changer un choix ne se prouve pas.

ASCII only (cp1252). Usage :
  python probe_r34_overkill_decision.py --part source
  python probe_r34_overkill_decision.py --part utility
  python probe_r34_overkill_decision.py --part rank
  python probe_r34_overkill_decision.py --part all
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                          # noqa: E402
from engine.weights import load as load_weights                             # noqa: E402
from engine.utilities import damage_composite                               # noqa: E402
from engine.utilities.damage import might_be_overkill, will_be_overkill     # noqa: E402
from engine_agreement_stages import _fields_from_native_event               # noqa: E402
from engine.playbook import scene as scene_mod                              # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK                   # noqa: E402
from engine.ai import context as _ai_ctx                                    # noqa: E402

BOARD = "MC1_67"
NORMAL_ATTACK = 69                 # `Loki_NormalAttack` (id CONCRET, cf. NormalAttackType@0x28)

# Rosters : des HEROS du pool rank 17 (verifies par `rl_duel.py --list-pool`).
P_UNITS = ("emperNoiseMarine", "ultraInceptorSgt")
A_UNITS = ("genesPrimus", "astraBullgryn")


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def build(state_file: Path, seed: int, p_units, a_units, *, hp_target=None,
          crit_spec=None, rank=17, no_ai=False, armor_target=None) -> int:
    """`rl_duel build` -- board FIXE (variable experimentale choisie, cf. runner.md §2)."""
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", BOARD, "--rank", str(rank),
           "--p-units", ",".join(p_units), "--a-units", ",".join(a_units)]
    if hp_target is not None:
        cmd += ["--hp-target", str(hp_target)]
    if crit_spec is not None:
        cmd += ["--crit", crit_spec]
    if no_ai:
        cmd += ["--no-ai"]
    if armor_target is not None:
        # #R34 montage C : l'ARMURE amortit le degat REEL des coups de descente (combat) SANS
        # toucher la prediction IA, qui est PRE-ARMURE -> c'est le levier qui rend la descente de
        # PV FINE (sinon un seul coup du remplissage tue la cible et le montage ne demarre pas).
        cmd += ["--armor-target", str(armor_target)]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[r34] build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
        sys.exit(2)
    return int(json.loads(state_file.read_text())["runnerId"])


def view(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)


def normal_attack_id(dv, uid, default=NORMAL_ATTACK) -> int:
    """L'attaque normale est un `ActiveAbilityType` **CONCRET PER-UNIT** (`NormalAttackType@0x28`),
    pas la constante 17 -- et pas non plus 69 pour tout le monde. On le lit dans `decisionView`
    (`abilities[].kind == "normal"`). Sans ca, `applyAction` rend `ok=True` et NE MUTE RIEN."""
    for u in (dv.get("units") or []):
        if int(u.get("id") or -1) != int(uid):
            continue
        for ab in (u.get("abilities") or []):
            if ab.get("kind") == "normal":
                return int(ab.get("id"))
    return int(default)


def by_visual(dv, vis, alive=True):
    for u in (dv.get("units") or []):
        if u.get("visualId") == vis and (bool(u.get("alive")) or not alive):
            return u
    return None


def move(sid, rid, uid, col, row):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def place_ring(sid, rid, ids, center_visual, center=(3, 4)):
    """GEOMETRIE DRIVEE (jamais subie, cf. runner.md §4) : `center_visual` au centre, tous les
    autres acteurs sur son ring 1 -> toute paire (attaquant, cible) est au CONTACT, donc
    `GetAllPredictions` rend une entree pour chaque cible."""
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    ccol, crow = center
    ring = [board.coord(t) for t in board.neighbours(board.id_at(ccol, crow))]
    if len(ring) < len(ids) - 1:
        raise RuntimeError("centre (%d,%d) trop pauvre en voisins (%d)" % (ccol, crow, len(ring)))
    move(sid, rid, ids[center_visual], ccol, crow)
    slot = 0
    for v, uid in ids.items():
        if v == center_visual:
            continue
        move(sid, rid, uid, *ring[slot])
        slot += 1


def move_adjacent_to(sid, rid, mover_id, target_id):
    """Place `mover_id` sur une tuile LIBRE voisine de `target_id` (geometrie DRIVEE : un coup de
    melee refuse par la portee rend `applyAction ok=True` SANS RIEN MUTER)."""
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dv = view(sid, rid)
    def _pos(u):
        p = u.get("pos")
        if isinstance(p, dict):
            return (p.get("col"), p.get("row"))
        return (u.get("col"), u.get("row"))

    occupied, tpos = set(), None
    for u in (dv.get("units") or []):
        p = _pos(u)
        if int(u["id"]) == int(target_id):
            tpos = p
        elif bool(u.get("alive")):
            occupied.add(p)
    if tpos is None or tpos[0] is None:
        raise RuntimeError("cible %s sans position" % target_id)
    for t in board.neighbours(board.id_at(int(tpos[0]), int(tpos[1]))):
        c = board.coord(t)
        if tuple(c) not in occupied:
            move(sid, rid, mover_id, *c)
            return tuple(c)
    raise RuntimeError("aucune tuile libre autour de %s" % target_id)


def could_crit_from_snapshot(snap_unit: dict) -> bool:
    """`IdunBattle.Core.Services.DamageCalculations$$CouldCrit(attacker)` : `GetStat(attacker, 9)`
    (CritChance) `>= 1` ET `GetStat(attacker, 10)` (CritDamage) `> 0`. Lu des stats RESOLUES de
    `combatSnapshot` (= `GetStat`), pas d'une config."""
    s = snap_unit.get("stats") or {}
    return int(s.get("critChance") or 0) >= 1 and int(s.get("critDamage") or 0) > 0


def _snap_by_id(sid, rid) -> dict:
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 120)
    return {int(u.get("entityId")): u for u in (snap.get("units") or [])
            if u.get("entityId") is not None}


def ai_predict(sid, rid, att_id, tgt_id, ability=NORMAL_ATTACK) -> dict | None:
    p = _r(sid, "aiPredict", {"runnerId": rid, "unitId": int(att_id),
                              "targetId": int(tgt_id), "abilityType": int(ability)}, 90)
    return p.get("pred")


# --------------------------------------------------------------------------------------------
# A. SOURCE du flag `MightCrit@+0xb1`
# --------------------------------------------------------------------------------------------

def offline_might_crit(sid, rid, wt, att_id, tgt_id, ability=NORMAL_ATTACK):
    """Le flag que le PORT pose lui-meme, bout de chaine PRODUCTEUR : ctx offline ->
    `<Playbook>.MakeDamagePredictions` -> `DamagePredictionResult.might_crit` ->
    `ProbableDamageEvent.composite_fields()["mightCrit"]`. `None` = pas d'event offline."""
    rpc = lambda m, b, t=60: _r(sid, m, b, t)                       # noqa: E731
    predictor = scene_mod.build_predictor(rpc, rid)
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    ctx = _ai_ctx.build(rpc, rid, dv, mov_by_unit, int(att_id), wt, predictor)
    tile = ctx.scene.pos(int(att_id))
    evs = NORMAL_ATTACK_PLAYBOOK.make_damage_predictions(ctx, tile, int(tgt_id), int(ability)) or []
    main = next((e for e in evs if e.target == int(tgt_id)), evs[0] if evs else None)
    if main is None:
        return None
    return main.composite_fields().get("mightCrit")


SOURCE_REGIMES = (("natural", None), ("crit-on", "100,1"), ("crit-off", "0,0"),
                  ("chance-only", "100,0"), ("dmg-only", "0,1"))


def run_source(seed: int = 34011, state_file=None, keep=False, verbose=True,
               regimes=None) -> dict:
    """Correlation LIVE `pred.mightCrit` <-> `CouldCrit(attacker)` sur CINQ regimes de stats, ET
    confrontation du PRODUCTEUR OFFLINE (`composite_fields()["mightCrit"]`) au flag NATIF de
    l'event `aiPlaybookPredict`. Rend `{"rows", "agree", "total", "regimes"}`."""
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parent.parent / "logs" / "r34src.json")
    sf.parent.mkdir(parents=True, exist_ok=True)
    rows, regimes = [], {}
    # Les CINQ regimes couvrent les QUATRE cadrans de la conjonction `CritChance >= 1 && CritDamage > 0`
    # -- sans `chance-only` / `dmg-only`, une correlation « tout a 1 / tout a 0 » ne prouverait PAS que
    # les DEUX conjonctions sont lues (un `MightCrit = CritDamage > 0` seul passerait aussi).
    for tag, crit in (regimes or SOURCE_REGIMES):
        rid = None
        try:
            rid = build(sf, seed, P_UNITS, A_UNITS, crit_spec=crit)
            dv = view(sid, rid)
            snaps = _snap_by_id(sid, rid)
            ids = {}
            for v in list(P_UNITS) + list(A_UNITS):
                u = by_visual(dv, v)
                if u is None:
                    raise RuntimeError("unite absente du build : %s" % v)
                ids[v] = int(u["id"])
            place_ring(sid, rid, ids, A_UNITS[0])
            snaps = _snap_by_id(sid, rid)
            wt = load_weights()
            seen = []
            for a in P_UNITS:
                for t in A_UNITS:
                    pred = ai_predict(sid, rid, ids[a], ids[t])
                    if not pred:
                        continue
                    live = bool(pred.get("mightCrit"))
                    sn = snaps.get(ids[a]) or {}
                    cc = could_crit_from_snapshot(sn)
                    st = sn.get("stats") or {}
                    nat_ev = next((e for e in playbook_events(sid, rid, ids[a], ids[t])
                                   if e.get("targetId") == ids[t]), None)
                    nat = None if nat_ev is None else bool(nat_ev.get("mightCrit"))
                    off = offline_might_crit(sid, rid, wt, ids[a], ids[t])
                    off = None if off is None else bool(off)
                    row = {"regime": tag, "attacker": a, "target": t,
                           "critChance": int(st.get("critChance") or 0),
                           "critDamage": int(st.get("critDamage") or 0),
                           "live_might_crit": live, "could_crit": cc,
                           "native_event_might_crit": nat, "offline_might_crit": off,
                           "agree": live == cc,
                           "producer_agree": (nat is not None and off is not None and nat == off)}
                    rows.append(row)
                    seen.append(live)
            regimes[tag] = seen
        finally:
            if rid is not None and not keep:
                _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    agree = sum(1 for r in rows if r["agree"])
    prod = sum(1 for r in rows if r["producer_agree"])
    if verbose:
        for r in rows:
            print("[r34A] %-11s %-18s -> %-16s cc=%-3d cd=%-4d live=%-5s CouldCrit=%-5s %s"
                  % (r["regime"], r["attacker"], r["target"], r["critChance"], r["critDamage"],
                     r["live_might_crit"], r["could_crit"], "OK" if r["agree"] else "MISMATCH"))
            print("[r34A]     PRODUCTEUR : natif(event)=%-5s port(offline)=%-5s %s"
                  % (r["native_event_might_crit"], r["offline_might_crit"],
                     "OK" if r["producer_agree"] else "MISMATCH"))
        print("[r34A] source %d/%d ; producteur %d/%d ; regimes %s"
              % (agree, len(rows), prod, len(rows),
                 {k: sorted(set(v)) for k, v in regimes.items()}))
    return {"rows": rows, "agree": agree, "producer_agree": prod, "total": len(rows),
            "regimes": regimes}


# --------------------------------------------------------------------------------------------
# B/C. CANAL D'UTILITE et CLASSEMENT -- formule ISOLEE (les 2 cotes sur predictions NATIVES)
# --------------------------------------------------------------------------------------------

# Attaquant SANS le trait `ThrillSeekers` (1056) : son rider « defeats an enemy with a Crit ->
# always overkilled » forcerait `isForceOverkill` et rendrait l'observation AMBIGUE (c'est
# exactement le confond que #R33 a du lever cote COMBAT).
UTIL_ATTACKER = "ultraInceptorSgt"
UTIL_VICTIM = "genesPrimus"
UTIL_P_UNITS = (UTIL_ATTACKER, "astraBullgryn")
UTIL_A_UNITS = (UTIL_VICTIM, "necroWarden")


def playbook_events(sid, rid, att_id, tgt_id, ability=NORMAL_ATTACK) -> list:
    """`aiPlaybookPredict` = `<Ability>Playbook.MakeDamagePredictions` invoque en direct --
    l'oracle que le scoreur de DECISION consomme reellement (PAS le preview `aiPredict`). Le
    decodeur expose `mightCrit` (event+0xb9 = `DamagePredictionResult.MightCrit@+0xb1`)."""
    r = _r(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": int(att_id),
                                      "targetId": int(tgt_id), "abilityType": int(ability)}, 120)
    return list(r.get("events") or [])


def native_pair_utility(sid, rid, att_id, tgt_id, ability=NORMAL_ATTACK):
    """`pairUtility` = `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`
    invoque en direct = la valeur EXACTE que le bucket natif attribue a la paire."""
    r = _r(sid, "pairUtility", {"runnerId": rid, "unitId": int(att_id),
                                "targetId": int(tgt_id), "abilityType": int(ability)}, 120)
    return r.get("utility")


def port_pair_utility(events, hpmax_by_id, team_by_id, my_team, wt) -> float:
    """Terme DEGAT du scoreur, cote PORT, nourri des events NATIFS -- mirror de
    `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent`
    (`prob1 x prob2 x composite Damage(34)`, event FRIENDLY -> NEGE). Formule ISOLEE : le feed est
    identique des deux cotes, donc tout ecart est un gap de LOGIQUE."""
    u = 0.0
    for ev in events:
        t_id = ev.get("targetId")
        sign = -1.0 if (t_id is not None and team_by_id.get(t_id) == my_team) else 1.0
        prob = (ev.get("probability") or 1.0) * (ev.get("probMult") or 1.0)
        u += sign * prob * damage_composite(_fields_from_native_event(ev),
                                            hpmax_by_id.get(t_id), wt)
    return u


def _hpmax_by_id(sid, rid) -> dict:
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    return {int(u.get("squadId")): int(u.get("hpMax") or 0)
            for u in (ob.get("units") or []) if u.get("squadId") is not None}


def _setup(sid, sf, seed, p_units, a_units, hp_target, crit_spec, center_visual, center=(3, 4),
           no_ai=False, armor_target=None):
    rid = build(sf, seed, p_units, a_units, hp_target=hp_target, crit_spec=crit_spec, no_ai=no_ai,
                armor_target=armor_target)
    dv = view(sid, rid)
    ids = {}
    for v in list(p_units) + list(a_units):
        u = by_visual(dv, v)
        if u is None:
            raise RuntimeError("unite absente du build : %s" % v)
        ids[v] = int(u["id"])
    place_ring(sid, rid, ids, center_visual, center)
    return rid, ids


def _measure(sid, rid, ids, wt, att, tgt) -> dict:
    dv = view(sid, rid)
    team_by_id = {int(u["id"]): u.get("team") for u in (dv.get("units") or [])}
    hpmax = _hpmax_by_id(sid, rid)
    evs = playbook_events(sid, rid, ids[att], ids[tgt])
    main = next((e for e in evs if e.get("targetId") == ids[tgt]), None)
    nat = native_pair_utility(sid, rid, ids[att], ids[tgt])
    prt = port_pair_utility(evs, hpmax, team_by_id, team_by_id.get(ids[att]), wt)
    f = _fields_from_native_event(main) if main else {}
    return {"events": len(evs), "native_utility": nat, "port_utility": prt,
            "hp": (main or {}).get("hpBefore"), "raw_min": (main or {}).get("willKillDmg"),
            "raw_max": (main or {}).get("mightKillDmg"),
            "might_crit": bool((main or {}).get("mightCrit")),
            "force_overkill": bool((main or {}).get("forceOverkill")),
            "port_might_overkill": bool(might_be_overkill(f)) if f else None,
            "port_will_overkill": bool(will_be_overkill(f)) if f else None}


def run_utility(seed: int = 34101, state_file=None, keep=False, verbose=True) -> dict:
    """MONTAGE B -- le canal d'utilite, en regime LETAL SOUS LE SEUIL.

    PASSE 1 (crit OFF, PV hauts) : lit les bornes RAW natives -> PV du regime = `rawMax`
    (`PV <= rawMax < 2 x PV` ET `rawMin < PV` => `MightBeOverkill` est le SEUL terme d'overkill
    en jeu ; `WillBeOverkill`, qui passe `isCritical = 0` en dur, reste FAUX des deux cotes).
    PASSE 2 : deux builds identiques a une seule variable pres (`--crit`), et on confronte
    `pairUtility` NATIF au terme degat du PORT nourri des MEMES events natifs."""
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parent.parent / "logs" / "r34util.json")
    sf.parent.mkdir(parents=True, exist_ok=True)
    wt = load_weights()
    rid = None
    try:
        rid, ids = _setup(sid, sf, seed + 500, UTIL_P_UNITS, UTIL_A_UNITS, 20000, "0,0",
                          UTIL_VICTIM)
        evs = playbook_events(sid, rid, ids[UTIL_ATTACKER], ids[UTIL_VICTIM])
        main = next((e for e in evs if e.get("targetId") == ids[UTIL_VICTIM]), None)
        if main is None:
            return {"error": "passe 1 : aucun event natif pour la paire"}
        raw_min, raw_max = int(main.get("willKillDmg") or 0), int(main.get("mightKillDmg") or 0)
    finally:
        if rid is not None and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    hp = raw_max
    if not (raw_min < hp <= raw_max < 2 * hp):
        return {"error": "regime letal-sous-le-seuil inatteignable : bornes [%d,%d]"
                         % (raw_min, raw_max)}
    if verbose:
        print("[r34B] tune : bornes RAW natives [%d,%d] => PV = %d (2 x PV = %d)"
              % (raw_min, raw_max, hp, 2 * hp))
    out = {"hp": hp, "tune_raw_min": raw_min, "tune_raw_max": raw_max,
           "possible_overkill_weight": wt.overkill(definite=False),
           "definite_overkill_weight": wt.overkill(definite=True)}
    # 3e regime `crit-on-min` : PV = borne RAW **MIN**. Les DEUX bornes sont alors letales et sous
    # le seuil -> `WillBeOverkill` ATTEINT le cas « pct < seuil » et son verdict serait `isCritical`
    # s'il le lisait. Le natif y passe **0 EN DUR** : ce regime est la garde qui interdit
    # d'« harmoniser » les deux bornes (a PV = rawMax, `WillBeOverkill` sort avant le test et la
    # mutation est QUIESCENTE -- verifie).
    for tag, crit, hp_of in (("crit-off", "0,0", hp), ("crit-on", "100,1", hp),
                             ("crit-on-min", "100,1", raw_min)):
        rid = None
        try:
            rid, ids = _setup(sid, sf, seed, UTIL_P_UNITS, UTIL_A_UNITS, hp_of, crit, UTIL_VICTIM)
            m = _measure(sid, rid, ids, wt, UTIL_ATTACKER, UTIL_VICTIM)
        finally:
            if rid is not None and not keep:
                _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        m["lethal_below_threshold"] = bool(
            m["raw_max"] is not None and m["hp"] is not None
            and m["hp"] <= m["raw_max"] < 2 * m["hp"] and m["raw_min"] < m["hp"])
        # regime « borne MIN letale sous le seuil » : `WillBeOverkill` ATTEINT le test de pct
        m["min_lethal_below_threshold"] = bool(
            m["raw_min"] is not None and m["hp"] is not None
            and m["hp"] <= m["raw_min"] < 2 * m["hp"])
        out[tag] = m
        if verbose:
            print("[r34B] %-11s PV=%s raw=[%s,%s] mightCrit=%s forceOverkill=%s regime=%s minRegime=%s"
                  % (tag, m["hp"], m["raw_min"], m["raw_max"], m["might_crit"],
                     m["force_overkill"], m["lethal_below_threshold"],
                     m["min_lethal_below_threshold"]))
            print("[r34B]   port  MightBeOverkill=%s WillBeOverkill=%s"
                  % (m["port_might_overkill"], m["port_will_overkill"]))
            print("[r34B]   utilite NATIVE=%s  PORT(events natifs)=%s  ecart=%s"
                  % (_f(m["native_utility"]), _f(m["port_utility"]),
                     _f(None if m["native_utility"] is None or m["port_utility"] is None
                        else m["native_utility"] - m["port_utility"])))
    if "crit-on" in out and "crit-off" in out:
        a, b = out["crit-on"], out["crit-off"]
        if a["native_utility"] is not None and b["native_utility"] is not None:
            out["native_delta"] = a["native_utility"] - b["native_utility"]
        out["port_delta"] = a["port_utility"] - b["port_utility"]
        if verbose:
            print("[r34B] DELTA crit-on - crit-off : natif=%s  port=%s  (PossibleOverkill=%s)"
                  % (_f(out.get("native_delta")), _f(out.get("port_delta")),
                     _f(out["possible_overkill_weight"])))
    return out


def _f(x):
    return "None" if x is None else ("%.4f" % float(x))


# --------------------------------------------------------------------------------------------
# C. CLASSEMENT -- le terme `PossibleOverkill` deplace-t-il le CHOIX ?
# --------------------------------------------------------------------------------------------

# MONTAGE C -- 2e PORTEUR (le montage B tourne sur `ultraInceptorSgt`) : l'attaquant mesure est
# `orksRuntherd`, [12545, 18817] sur `genesPrimus` => PV communs H = R = 18817.
#
# POURQUOI IL FAUT DESCENDRE **LES DEUX** CIBLES, et dans DEUX bandes distinctes : le composite
# Damage(34) est DISCONTINU. Poids BC re-derives de la mesure : DamageDealt <= 100,
# PossibleKill 33.33, DefinitelyKill 100, PossibleOverkill 15, DefinitelyOverkill 40. Passer de
# PossibleKill a DefinitelyKill vaut +66.67 -- QUATRE FOIS le terme sous test. Une cible qu'on
# descend saute donc PAR-DESSUS la fenetre de 15 points au lieu d'y entrer (mesure : u(B) passe de
# 106.67 a 173.33 en franchissant `hp = rawMin`). La SEULE fenetre atteignable met les deux cibles
# dans la MEME classe de kill (DefinitelyKill, `hp <= rawMin`) et dans deux classes d'OVERKILL
# differentes :
#   A dans (R/2, rawMin]      -> `pct_max < 100` => verdict = `MightCrit`  (le terme sous test)
#   B dans (rawMin/2, R/2]    -> `pct_max >= 100` => overkill INCONDITIONNEL (+15 toujours)
# et l'ecart de terme degat `80 x (hp_A - hp_B) / H` doit rester < 15.
#
# Remplissage = `tauMarksman` ([3212, 4818] sur `genesPrimus`, soit 0.17-0.26 R) : c'est le PAS DE
# DESCENTE. `astraBullgryn` [12032, 16848] et `orksRuntherd` [12545, 18817] retirent 0.65 R d'un
# coup -- ils SAUTENT les deux bandes (mesure : 18817 -> 6509 -> 0).
RANK_ATTACKER = "orksRuntherd"
RANK_FILLER = "tauMarksman"
RANK_P_UNITS = (RANK_ATTACKER, RANK_FILLER)
RANK_A_UNITS = (UTIL_VICTIM, "necroWarden")


def _port_utility_one(ev, hpmax, wt, *, with_crit: bool) -> float:
    """Utilite PORT d'UN event natif, AVEC ou SANS la cle `mightCrit`. `with_crit=False` reproduit
    EXACTEMENT le port d'AVANT #R34 (cle absente -> `.get("mightCrit")` falsy -> `isCritical = 0`) :
    pas besoin de revenir en arriere dans le code pour montrer la vue ROUGE."""
    f = _fields_from_native_event(ev)
    if not with_crit:
        f.pop("mightCrit", None)
    return damage_composite(f, hpmax, wt)


def attack_action(sid, rid, att_id, tgt_id, ability=NORMAL_ATTACK):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(att_id), "targetId": int(tgt_id),
        "abilityType": int(ability)}}, 120)


def endturn(sid, rid):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)


def has_action(dv, uid) -> bool:
    for u in (dv.get("units") or []):
        if int(u.get("id") or -1) == int(uid):
            return bool(u.get("hasAction"))
    return False


def refresh_activations(sid, rid, uid, tries: int = 6) -> bool:
    """Rend l'activation a `uid` en enchainant des fins de tour. NECESSAIRE : placer les unites
    (`applyAction move`) EPUISE leurs activations, et quand toutes MES unites ont agi le jeu
    auto-termine mon tour -- un `applyAction ability` rend alors `ok=True` SANS RIEN MUTER (le
    no-op silencieux qui a fait passer ce montage pour « pas de bascule » trois fois de suite).
    `--no-ai` garantit que l'adversaire ne joue rien entre-temps."""
    for _ in range(tries):
        if has_action(view(sid, rid), uid):
            return True
        endturn(sid, rid)
    return has_action(view(sid, rid), uid)


def run_rank(seed: int = 34201, state_file=None, keep=False, verbose=True,
             armor_target: int = None) -> dict:
    """MONTAGE C -- deux cibles, une seule dans le regime letal-sous-le-seuil.

    `--hp-target H` met les DEUX ennemis a H = `rawMax(attaquant -> A)` : la cible A est alors
    letale-sous-le-seuil (pct = 0), donc son verdict d'overkill EST `MightCrit`. On fait ensuite
    DESCENDRE les PV de la cible B (coups du remplissage) jusqu'a ce que son utilite se glisse
    ENTRE l'utilite de A sans crit et celle de A avec crit -- a ce point le CLASSEMENT natif dit
    « A d'abord » alors que le port d'AVANT dit « B d'abord ». Le port d'APRES doit rejoindre le
    natif. Geometrie DRIVEE, `--no-ai` (l'IA adverse ne joue pas : la descente de PV est pilotee)."""
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parent.parent / "logs" / "r34rank.json")
    sf.parent.mkdir(parents=True, exist_ok=True)
    wt = load_weights()
    rid = None
    try:
        # Geometrie : l'ATTAQUANT au centre, tout le reste sur son ring 1 -> il atteint LES DEUX
        # cibles en melee (sinon la prediction sur la 2e cible rend un degat NUL et le montage
        # compare deux choses incomparables).
        rid, ids = _setup(sid, sf, seed + 500, RANK_P_UNITS, RANK_A_UNITS, 20000, "0,0",
                          RANK_ATTACKER)
        evs = playbook_events(sid, rid, ids[RANK_ATTACKER], ids[UTIL_VICTIM])
        main = next((e for e in evs if e.get("targetId") == ids[UTIL_VICTIM]), None)
        if main is None:
            return {"error": "passe 1 : aucun event natif"}
        hp = int(main.get("mightKillDmg") or 0)
    finally:
        if rid is not None and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    if hp <= 0:
        return {"error": "passe 1 : borne RAW max nulle"}
    if verbose:
        print("[r34C] tune : PV communs = %d (= rawMax attaquant -> %s)" % (hp, UTIL_VICTIM))
    rid = None
    try:
        rid, ids = _setup(sid, sf, seed, RANK_P_UNITS, RANK_A_UNITS, hp, "100,1", RANK_ATTACKER,
                          no_ai=True, armor_target=armor_target)
        a_id, b_id = ids[UTIL_VICTIM], ids["necroWarden"]
        att, filler = ids[RANK_ATTACKER], ids[RANK_FILLER]
        fpos = move_adjacent_to(sid, rid, filler, b_id)   # le remplissage doit ATTEINDRE B
        if verbose:
            print("[r34C] remplissage place en %s (voisin de B)" % (fpos,))
        # Bandes cibles (cf. en-tete) : A dans (R/2, rawMin], B dans (rawMin/2, R/2].
        e0 = next((e for e in playbook_events(sid, rid, ids[RANK_ATTACKER], ids[UTIL_VICTIM])
                   if e.get("targetId") == ids[UTIL_VICTIM]), None)
        R = int((e0 or {}).get("mightKillDmg") or 0)
        M = int((e0 or {}).get("willKillDmg") or 0)
        band_a, band_b = (R // 2, M), (M // 2, R // 2)
        if verbose:
            print("[r34C] bandes : R=%d rawMin=%d -> A dans (%d, %d] ; B dans (%d, %d]"
                  % (R, M, band_a[0], band_a[1], band_b[0], band_b[1]))
        trace = []
        flip = None
        out_noop = False
        for it in range(16):
            hpmax = _hpmax_by_id(sid, rid)
            dv = view(sid, rid)
            alive = {int(u["id"]): bool(u.get("alive")) for u in (dv.get("units") or [])}
            if not alive.get(b_id) or not alive.get(a_id):
                break
            ea = next((e for e in playbook_events(sid, rid, att, a_id)
                       if e.get("targetId") == a_id), None)
            eb = next((e for e in playbook_events(sid, rid, att, b_id)
                       if e.get("targetId") == b_id), None)
            if ea is None or eb is None:
                break
            ua_bef = _port_utility_one(ea, hpmax.get(a_id), wt, with_crit=False)
            ua_aft = _port_utility_one(ea, hpmax.get(a_id), wt, with_crit=True)
            ub_bef = _port_utility_one(eb, hpmax.get(b_id), wt, with_crit=False)
            ub_aft = _port_utility_one(eb, hpmax.get(b_id), wt, with_crit=True)
            na = native_pair_utility(sid, rid, att, a_id)
            nb = native_pair_utility(sid, rid, att, b_id)
            rec = {"iter": it, "hp_a": ea.get("hpBefore"), "hp_b": eb.get("hpBefore"),
                   "port_before": {"A": ua_bef, "B": ub_bef},
                   "port_after": {"A": ua_aft, "B": ub_aft},
                   "native": {"A": na, "B": nb},
                   "argmax_port_before": "A" if ua_bef > ub_bef else "B",
                   "argmax_port_after": "A" if ua_aft > ub_aft else "B",
                   "argmax_native": (None if na is None or nb is None
                                     else ("A" if na > nb else "B"))}
            trace.append(rec)
            if verbose:
                print("[r34C] it%d PV A=%s B=%s | port AVANT A=%s B=%s -> %s | port APRES A=%s B=%s"
                      " -> %s | natif A=%s B=%s -> %s"
                      % (it, rec["hp_a"], rec["hp_b"], _f(ua_bef), _f(ub_bef),
                         rec["argmax_port_before"], _f(ua_aft), _f(ub_aft),
                         rec["argmax_port_after"], _f(na), _f(nb), rec["argmax_native"]))
            if (rec["argmax_native"] is not None
                    and rec["argmax_port_before"] != rec["argmax_native"]
                    and rec["argmax_port_after"] == rec["argmax_native"]):
                flip = rec
                break
            # descente des PV de B : un coup du remplissage, puis 2 fins de tour pour rafraichir
            # les activations (l'IA adverse est neutralisee par `--no-ai`).
            # ⚠ GARDE-FOU : `applyAction` peut rendre `ok=True` SANS RIEN MUTER -- on RELIT donc
            # les PV et on ARRETE net si le coup n'a rien fait (un no-op silencieux se lirait
            # comme « pas de bascule » alors que le montage n'a jamais demarre).
            # descente : on frappe la cible qui est ENCORE AU-DESSUS de sa bande (A d'abord).
            hp_a_cur, hp_b_cur = int(rec["hp_a"] or 0), int(rec["hp_b"] or 0)
            if hp_a_cur > band_a[1]:
                victim_id = a_id
            elif hp_b_cur > band_b[1] and hp_b_cur >= hp_a_cur:
                victim_id = b_id
            elif hp_b_cur > band_b[1]:
                victim_id = b_id
            else:
                if verbose:
                    print("[r34C]   les deux cibles sont dans leur bande et le classement ne "
                          "bascule pas -- fin de la descente")
                break
            hp_b_before = hp_a_cur if victim_id == a_id else hp_b_cur
            ok_act = refresh_activations(sid, rid, filler)
            move_adjacent_to(sid, rid, filler, victim_id)   # portee GARANTIE (jamais subie)
            # l'id CONCRET d'abord ; repli sur 69 (`Loki_NormalAttack` generique) si l'override
            # per-unit n'est pas jouable par message (`MV71SniperDroneSquadAttackAbility` = 1076
            # est une TRIGGERED : `applyAction` rend `ok=True` sans muter).
            _fid = normal_attack_id(dv, filler)
            resp = attack_action(sid, rid, filler, victim_id, _fid)
            dv2 = view(sid, rid)
            ub = next((u for u in (dv2.get("units") or []) if int(u["id"]) == victim_id), None)
            hp_b_after = None if ub is None else int(ub.get("hp") or 0)
            if _fid != NORMAL_ATTACK and hp_b_after is not None \
                    and hp_b_after >= int(hp_b_before or 0):
                resp = attack_action(sid, rid, filler, victim_id, NORMAL_ATTACK)
                dv2 = view(sid, rid)
                ub = next((u for u in (dv2.get("units") or []) if int(u["id"]) == victim_id), None)
                hp_b_after = None if ub is None else int(ub.get("hp") or 0)
            if verbose:
                print("[r34C]   coup remplissage sur u%s -> PV %s -> %s (activation rendue=%s, "
                      "applyAction ok=%s err=%s)"
                      % (victim_id, hp_b_before, hp_b_after, ok_act, resp.get("ok"),
                         resp.get("error")))
            if hp_b_after is None or hp_b_after >= int(hp_b_before or 0):
                if verbose:
                    why = _r(sid, "abilityReason", {"runnerId": rid, "casterId": filler,
                                                    "abilityType": normal_attack_id(dv, filler),
                                                    "targetId": b_id}, 60)
                    print("[r34C]   ARRET : le coup n'a RIEN mute (no-op silencieux) -- "
                          "montage non demarre, pas de conclusion possible ; abilityReason=%s"
                          % json.dumps(why)[:400])
                    for u in (dv2.get("units") or []):
                        print("[r34C]     u%-4s %-18s pos=%s hp=%s alive=%s hasAction=%s ab=%s"
                              % (u.get("id"), u.get("visualId"), u.get("pos"), u.get("hp"),
                                 u.get("alive"), u.get("hasAction"),
                                 [(a.get("kind"), a.get("id")) for a in (u.get("abilities") or [])]))
                out_noop = True
                break
        out = {"hp_target": hp, "trace": trace, "flip": flip, "noop": out_noop}
        if verbose:
            print("[r34C] BASCULE DE CLASSEMENT : %s" % ("OUI %s" % {
                k: flip[k] for k in ("iter", "hp_a", "hp_b", "argmax_port_before",
                                     "argmax_port_after", "argmax_native")} if flip else "NON"))
        return out
    finally:
        if rid is not None and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="all", choices=("source", "utility", "rank", "all"))
    ap.add_argument("--seed", type=int, default=34011)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    if args.part in ("source", "all"):
        r = run_source(seed=args.seed, state_file=args.state_file, keep=args.keep)
        print("[r34] SOURCE : %s ; PRODUCTEUR : %s"
              % ("OK" if r["agree"] == r["total"] and r["total"] else "ECHEC",
                 "OK" if r["producer_agree"] == r["total"] and r["total"] else "ECHEC"))
    if args.part in ("utility", "all"):
        r = run_utility(seed=args.seed + 90, state_file=args.state_file, keep=args.keep)
        print("[r34] UTILITY : %s" % r.get("error", "mesure rendue"))
    if args.part in ("rank", "all"):
        # Le PAS DE DESCENTE (~4000 PV) est du meme ordre que la LARGEUR de bande (0.167 R = 3137)
        # -> l'atterrissage dans la fenetre depend du tirage. On re-tente sur quelques seeds au lieu
        # de conclure « pas de bascule » sur un seul echantillon.
        r = {}
        for k in (0, 7, 13, 29):
            r = run_rank(seed=args.seed + 190 + k, state_file=args.state_file, keep=args.keep)
            if r.get("flip") or r.get("error"):
                break
        print("[r34] RANK : %s" % (r.get("error")
                                   or ("BASCULE" if r.get("flip") else "pas de bascule")))


if __name__ == "__main__":
    main()
