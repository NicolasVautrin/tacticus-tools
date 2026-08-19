#!/usr/bin/env python
"""probe_287r11r1r1 -- ARMEMENT du bit `CasterHas2TurnsLeft` (52) et confrontation du slot 0x1b.

CE QUE CE PROBE ETABLIT
-----------------------
Quatre sites du port declaraient « le slot 0x1a d'`IBattleQuery` n'est pas resolu, donc la regle
`CasterHas2TurnsLeft` n'est pas portee ». C'etait un DECALAGE DE UN : `0x1a` = 26 est
`ShouldPlayerSkipTurn` (arite **1**), alors que le call-site de
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` passe DEUX arguments. Le vrai slot
est `0x1b` = 27 = `IdunBattle.Core.Services.BattleQuery$$HasMinimumRemainingTurns` (arite 2), dont le
corps est :

    limit = <victoryConfig @+0xb0>.<Dictionary @+0x18>[VictoryConditionType.MainPlayerRoundLimitation]
    if (!limit.HasValue)  return true;
    return turns <= limit.Value - matchTurn.GetAmountOfTurnsEndedByPlayer(GetPlayerTurnOrder()[0]);

Le dictionnaire est **`BC.Victory.VictoryConditions`**. Ce probe le PATCHE et mesure le verdict
NATIF (`abilityReason.casterReason`) sur TROIS bras :

  * `temoin`     -- pas de `MainPlayerRoundLimitation` -> `limit` VIDE -> `true` -> AUCUN refus ;
  * `plafond1`   -- `MainPlayerRoundLimitation = 1` -> `2 <= 1 - ended` est FAUX pour TOUT
                    `ended >= 0` -> refus `CasterHas2TurnsLeft` (0x10000000000000) ;
  * `plafond20`  -- `= 20` -> `2 <= 20 - ended` est VRAI pour tout `ended <= 18` -> AUCUN refus.

⚠ **LES DEUX BRAS A PLAFOND SONT CHOISIS POUR NE PAS DEPENDRE DE `ended`.** Le port est confronte
par ENCADREMENT : son verdict est evalue pour TOUTE valeur de `ended` dans `[0, nb d'endturns
emis]`, et l'accord n'est retenu que si ce verdict est CONSTANT sur l'intervalle ET egal au natif.
Fitter un `ended` sur la reponse native serait exactement l'anti-pattern « ajuster un scalaire ».

⚠ **L'ENCADREMENT NE SUFFIT PLUS, ET C'EST VOULU (#287-r11-r1-r1-r1).** Le port MESURE desormais
`ended` (`State.turns_ended`, mirror de `TurnComponent+0x40` pose par son ecrivain natif UNIQUE
`TurnComponent$$SetCurrentPlayer`) : un encadrement qui accepte toute valeur du compteur ne peut
PAS voir un compteur FAUX. Le probe demande donc AUSSI, a chaque bras ET a chaque pas du bras
`bascule`, le verdict DIRECT du port -- sans lui souffler `ended` -- et exige l'ACCORD PAS A PAS
plus l'EGALITE DES RANGS DE BASCULE (natif vs port). Les deux criteres coexistent : l'encadrement
garde la FORMULE, l'accord pas a pas garde le COMPTEUR.

⚠ **LE COURT-CIRCUIT MUNITIONS EST LE PIEGE DU MONTAGE** : `AttackQuery$$GetInvalidCasterReason`
rend `broken(ValidRequest=1)` AVANT la cascade quand `ActiveAbility.CanCurrentlyBeUsed` est faux, et
1142 porte `munitionsCost = 1` alors que le seed BC capture `MachineOfWarAmmo = 0`. Le probe patche
donc AUSSI les munitions (meme levier que `probe_253`), et REFUSE de conclure si `casterReason`
reste a `0x1` -- un court-circuit n'est pas un accord.

PORTEUR : `astraOrdnanceBattery` (**MACHINE OF WAR**, presente dans le pool MoW du seed) et son
ability 1142 `MalleusRocketLauncher`. Les deux autres porteurs du bit sont aussi des MoW
(1160 `tauBroadside`, 1188 `adeptExorcist`) -- aucun HERO, aucun SUMMON, aucun NPC.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_287r11r1r1_caster_has_2_turns_left.py
    python probe_287r11r1r1_caster_has_2_turns_left.py --seed 31337 --board C1_02

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.entities.victory_condition_type import VictoryConditionType   # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import get_invalid_caster_reason   # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR    # noqa: E402
from engine.runner.operations import turnflow as TF                  # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402
from engine.services import battle_query as _bq                      # noqa: E402
from engine.services.victory_config import CONDITIONS_KEY, VICTORY_SECTION   # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

MALLEUS_ROCKET_LAUNCHER = 1142
BATTERY = "astraOrdnanceBattery"        # porteur 1142 (MACHINE OF WAR, pool MoW)
P_UNITS = "astraYarrick,astraCreed"
A_UNITS = "necroWarden,necroWarden"
BOARD = "C1_02"                         # board MoW-capable (slot MachineOfWarPosition des 2 cotes)
SEED = "777"
MOW_AMMO = 9                            # desarme le court-circuit `CanCurrentlyBeUsed` (munitions)
TOURS_DE_CHAUFFE = 6                     # purge `initialCooldownTurns` de 1142 (= 1)
#: Le 2e argument du call-site (`<slot 0x1b>(caster, 2)`) -- c'est lui qui NOMME le bit.
TURNS_ARG = 2

#: Les trois bras STATIQUES. `None` = la cle est ABSENTE du dictionnaire (`Nullable` vide natif).
BRAS = (("temoin", None), ("plafond1", 1), ("plafond20", 20))

#: 4e bras, DYNAMIQUE -- il separe la formule native d'un modele plausible mais FAUX.
#: Les trois bras ci-dessus sont TOUS compatibles avec `turns <= limit` (sans le terme `- ended`) :
#: `2 <= 1` faux, `2 <= 20` vrai, plafond absent -> vrai. Un port qui aurait oublie
#: `GetAmountOfTurnsEndedByPlayer` y serait passe. Le bras `bascule` pose `limit = 3` et mesure
#: `casterReason` APRES CHAQUE `endturn` : le refus doit APPARAITRE quand `ended >= limit - 2 = 1`,
#: et le RANG de la bascule est alors une MESURE indirecte du compteur `TurnComponent+0x40`.
BASCULE_ROUNDS = 3
BASCULE_ENDTURNS = 8

_seq = itertools.count()


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _victory_section(rounds):
    """La section `BC.Victory` du bras : celle de la seed, plus (ou non) le plafond de rounds."""
    src = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    bc = src.get("bc") if isinstance(src, dict) and "bc" in src else src
    vic = json.loads(json.dumps(bc.get(VICTORY_SECTION) or {}))
    conds = dict(vic.get(CONDITIONS_KEY) or {})
    key = VictoryConditionType.MainPlayerRoundLimitation.name
    conds.pop(key, None)
    if rounds is not None:
        conds[key] = int(rounds)
    vic[CONDITIONS_KEY] = conds
    return vic


def _seed_bc(rounds) -> Path:
    """Seed BC patche HORS `data/` (versionne, ENTREES seulement) : munitions de MoW + plafond de
    rounds. Le patch est fait EN MEMOIRE puis ecrit, et `BC.Victory` n'est touche par AUCUN
    rattrapage (`_load_seed_bc` ne re-synthetise que `BC.Abilities`, `buildNormalizedBC` ne lit pas
    `Victory` -- verifie par grep sur `frida/hooks/features/normalize-bc/`)."""
    src = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    bc = src.get("bc") if isinstance(src, dict) and "bc" in src else src
    for _pid, p in ((bc.get("Player") or {}).get("Players") or {}).items():
        if p.get("PlayerType") != 2:                  # 2 = Environment
            p["MachineOfWarAmmo"] = MOW_AMMO
    bc[VICTORY_SECTION] = _victory_section(rounds)
    out = ROOT / "logs" / ("_probe287r11r1r1-seedbc-%d-%s.json"
                           % (os.getpid(), "none" if rounds is None else str(rounds)))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(src), encoding="utf-8")
    return out


def _build(sid, seed: str, board: str, seed_bc: Path):
    state = ROOT / "logs" / ("_probe287r11r1r1-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", P_UNITS, "--a-units", A_UNITS, "--p-mow", BATTERY,
            "--seed-bc", str(seed_bc)]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"]), state
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-600:])
        time.sleep(10)


def _dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _act(sid, rid, action, timeout=90):
    return _r(sid, "applyAction", {"runnerId": rid, "action": action}, timeout)


def _mow_by_vis(dec, vis):
    for m in (dec.get("mows") or []):
        if m.get("visualId") == vis:
            return m
    return None


def _native_caster(sid, rid, caster_id, aid):
    """`abilityReason(...).casterReason` -- l'oracle. Rend `(code, reasons, abilityState, err)`."""
    nat = _r(sid, "abilityReason",
             {"runnerId": rid, "casterId": int(caster_id), "abilityType": int(aid)}, 60) or {}
    cr = nat.get("casterReason") or {}
    h = cr.get("hex")
    code = int(h, 16) if isinstance(h, str) else (
        0 if cr.get("ruleClass") == "NoBrokenTargetingRule" else None)
    return code, (cr.get("reasons") or []), nat.get("abilityState"), nat.get("error")


# --------------------------------------------------------------------------- un bras

def _run_bras(sid, label, rounds, seed, board):
    seed_bc = _seed_bc(rounds)
    rid, state_file = _build(sid, seed, board, seed_bc)
    try:
        # PURGE du `initialCooldownTurns` : sans elle `CanCurrentlyBeUsed` est faux et
        # `AttackQuery$$GetInvalidCasterReason` court-circuite AVANT la cascade.
        n_end = 0
        for _ in range(TOURS_DE_CHAUFFE):
            d = _dv(sid, rid)
            mow = _mow_by_vis(d, BATTERY)
            ab = next((a for a in ((mow or {}).get("abilities") or [])
                       if a.get("id") == MALLEUS_ROCKET_LAUNCHER), None)
            if ab is not None and ab.get("usable") and not (ab.get("cooldown") or 0):
                break
            r = _act(sid, rid, {"kind": "endturn"}, 60)
            if isinstance(r, dict) and r.get("error"):
                break
            n_end += 1

        dv = _dv(sid, rid)
        mow = _mow_by_vis(dv, BATTERY)
        if mow is None:
            return {"label": label, "rounds": rounds, "erreur": "MoW absente"}
        mid = int(mow["casterId"])
        code, reasons, abstate, err = _native_caster(sid, rid, mid, MALLEUS_ROCKET_LAUNCHER)

        ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        brd = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
        st = load_state(dv, ob, snap, board=brd, victory_config=_victory_section(rounds))
        ability = ABILITY_CLASSES[MALLEUS_ROCKET_LAUNCHER]()

        # --- LE PORT, PAR ENCADREMENT ------------------------------------------------------
        # `ended` n'est pas mesurable cote port (residu #287-r11-r1-r1-r1). On evalue donc le
        # verdict pour TOUTE valeur plausible et on n'accepte l'accord que s'il est CONSTANT.
        bornes = list(range(0, n_end + 2))
        verdicts = []
        for ended in bornes:
            ok = _bq.has_minimum_remaining_turns(mid, TURNS_ARG, state=st,
                                                 turns_ended_by_first_player=ended)
            verdicts.append(0 if ok else int(TR.CasterHas2TurnsLeft))
        port_constant = (len(set(verdicts)) == 1)
        port_code = verdicts[0] if port_constant else None

        # --- LE PORT, SANS AUCUNE AIDE (#287-r11-r1-r1-r1) ---------------------------------
        # Le port LEVAIT ici, faute du compteur `TurnComponent+0x40`. Il a desormais son mirror
        # (`State.turns_ended`, seede par `snapshot._load_turns_ended`) : on lui demande donc son
        # verdict DIRECT, sans lui souffler `ended`, et on le confronte au natif. C'est le cran que
        # l'encadrement ci-dessus ne pouvait PAS donner -- il acceptait toute valeur du compteur.
        direct = int(get_invalid_caster_reason(st, mid, ability))
        order = TF.player_turn_order(st)
        first = order[0] if order else None
        ended_port = _bq.get_amount_of_turns_ended_by_player(st, first)

        return {"label": label, "rounds": rounds, "runner": rid, "mow": mid,
                "endturns": n_end, "nat": code, "nat_reasons": reasons,
                "abilityState": abstate, "err": err,
                "port_bornes": bornes, "port_verdicts": verdicts,
                "port_constant": port_constant, "port": port_code,
                "port_direct": direct, "port_ordre": order, "port_first": first,
                "port_ended": ended_port, "port_turn_counts": dict(st.turn_counts),
                "port_turns_ended": dict(st.turns_ended)}
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            state_file.unlink(missing_ok=True)
            seed_bc.unlink(missing_ok=True)
            print("[cleanup] runner %d dispose (bras %s)" % (rid, label))
        except Exception as e:                                       # noqa: BLE001
            print("[cleanup] dispose KO: %s" % e)


# --------------------------------------------------------------------------- bras DYNAMIQUE

def _run_bascule(sid, seed, board):
    """`MainPlayerRoundLimitation = 3` + un `casterReason` APRES CHAQUE `endturn`.

    Le refus doit apparaitre quand `ended >= limit - TURNS_ARG = 1`, et JAMAIS revenir a `0`
    ensuite (`ended` est monotone croissant). C'est ce qui etablit que la formule porte bien le
    terme `- GetAmountOfTurnsEndedByPlayer(...)` : sans lui, `2 <= 3` serait vrai a jamais.

    ⚠ DEPUIS #287-r11-r1-r1-r1 CE BRAS PORTE LE VRAI CRAN. Il ne se contente plus de lire le
    natif : a CHAQUE pas il recharge l'etat du port et lui demande son verdict DIRECT
    (`get_invalid_caster_reason`, sans lui souffler `ended`) plus la valeur de son mirror
    `State.turns_ended[GetPlayerTurnOrder()[0]]`. Le critere devient un ACCORD PAS A PAS, pas un
    encadrement -- l'encadrement acceptait toute valeur du compteur, donc il ne pouvait pas voir
    un compteur FAUX."""
    seed_bc = _seed_bc(BASCULE_ROUNDS)
    rid, state_file = _build(sid, seed, board, seed_bc)
    suite = []
    ability = ABILITY_CLASSES[MALLEUS_ROCKET_LAUNCHER]()
    vic = _victory_section(BASCULE_ROUNDS)
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        brd = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
        for step in range(BASCULE_ENDTURNS + 1):
            d = _dv(sid, rid)
            mow = _mow_by_vis(d, BATTERY)
            if mow is None:
                break
            mid = int(mow["casterId"])
            ab = next((a for a in (mow.get("abilities") or [])
                       if a.get("id") == MALLEUS_ROCKET_LAUNCHER), None)
            usable = bool((ab or {}).get("usable")) and not ((ab or {}).get("cooldown") or 0)
            code, reasons, _st, err = _native_caster(sid, rid, mid, MALLEUS_ROCKET_LAUNCHER)
            # --- LE PORT, AU MEME PAS, SANS AIDE ------------------------------------------
            ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
            snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
            st = load_state(d, ob, snap, board=brd, victory_config=vic)
            order = TF.player_turn_order(st)
            first = order[0] if order else None
            suite.append({"step": step, "usable": usable, "nat": code,
                          "reasons": reasons, "err": err,
                          "port": int(get_invalid_caster_reason(st, mid, ability)),
                          "port_first": first,
                          "port_ended": _bq.get_amount_of_turns_ended_by_player(st, first),
                          "port_turns_ended": dict(st.turns_ended),
                          "port_turn_counts": dict(st.turn_counts),
                          "port_current": st.current_player_id})
            print("    [bascule step=%d] usable=%s casterReason=%s %s | PORT=%s ended[%s]=%s "
                  "turns_ended=%s"
                  % (step, usable, "-" if code is None else hex(code),
                     ",".join(reasons) or "(valide)", hex(suite[-1]["port"]),
                     first, suite[-1]["port_ended"], suite[-1]["port_turns_ended"]))
            if step == BASCULE_ENDTURNS:
                break
            r = _act(sid, rid, {"kind": "endturn"}, 60)
            if isinstance(r, dict) and r.get("error"):
                print("    [bascule] endturn refuse (%s) -- arret" % r.get("error"))
                break
        return suite
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            state_file.unlink(missing_ok=True)
            seed_bc.unlink(missing_ok=True)
            print("[cleanup] runner %d dispose (bras bascule)" % rid)
        except Exception as e:                                       # noqa: BLE001
            print("[cleanup] dispose KO: %s" % e)


# --------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    a = ap.parse_args()

    sid = _resolve_session()
    if not sid:
        print("[FAIL] pas de session Frida")
        return 2

    print("[287-r11-r1-r1] bit CasterHas2TurnsLeft = <IBattleQuery slot 0x1b>(caster, %d)"
          % TURNS_ARG)
    print("  porteur %s (MACHINE OF WAR) ability %d ; board %s ; MachineOfWarAmmo=%d"
          % (BATTERY, MALLEUS_ROCKET_LAUNCHER, a.board, MOW_AMMO))

    res = []
    for label, rounds in BRAS:
        print("\n--- BRAS %s (MainPlayerRoundLimitation = %s) ---"
              % (label, "ABSENT" if rounds is None else rounds))
        r = _run_bras(sid, label, rounds, a.seed, a.board)
        res.append(r)
        if r.get("erreur"):
            print("  [KO] %s" % r["erreur"])
            continue
        print("  endturns=%d  abilityState=%s" % (r["endturns"], r["abilityState"]))
        print("  NATIF casterReason = %s %s%s"
              % ("-" if r["nat"] is None else hex(r["nat"]),
                 ",".join(r["nat_reasons"]) or "(valide)",
                 "  err=%s" % r["err"] if r["err"] else ""))
        print("  PORT  verdicts sur ended in %s : %s -> %s"
              % (r["port_bornes"], [hex(v) for v in r["port_verdicts"]],
                 "CONSTANT %s" % hex(r["port"]) if r["port_constant"] else "NON CONSTANT"))
        print("  PORT  get_invalid_caster_reason (SANS aide) : %s ; ordre=%s first=%s ended=%s"
              % (hex(r["port_direct"]), r["port_ordre"], r["port_first"], r["port_ended"]))
        print("  PORT  turn_counts=%s turns_ended=%s"
              % (r["port_turn_counts"], r["port_turns_ended"]))

    # ---------------------------------------------------------------- verdict
    attendu = {"temoin": 0, "plafond1": int(TR.CasterHas2TurnsLeft), "plafond20": 0}
    court_circuit = [r["label"] for r in res
                     if r.get("nat") == int(TR.ValidRequest)]
    ventilation = {}
    for r in res:
        if r.get("nat") is not None:
            ventilation[hex(r["nat"])] = ventilation.get(hex(r["nat"]), 0) + 1

    print("\n[VENTILATION PAR VERDICT NATIF] %s  (bras=%d)"
          % (ventilation, len(res)))
    if court_circuit:
        print("[FAIL] court-circuit `broken(ValidRequest)` sur %s -- la cascade CASTER n'est PAS "
              "atteinte (munitions / cooldown). Aucun accord ne peut etre conclu." % court_circuit)
        return 1
    if len(ventilation) < 2:
        print("[FAIL] regime DEGENERE : les %d bras rendent le MEME verdict natif -- le montage ne "
              "discrimine rien." % len(res))
        return 1

    # ---------------------------------------------------------------- 4e bras, DYNAMIQUE
    print("\n--- BRAS bascule (MainPlayerRoundLimitation = %d, un casterReason par endturn) ---"
          % BASCULE_ROUNDS)
    suite = _run_bascule(sid, a.seed, a.board)
    refus = int(TR.CasterHas2TurnsLeft)
    # ⚠ Les pas COURT-CIRCUITES sont ECARTES, et pour une raison NOMMEE, pas pour faire passer le
    # critere : tant que `CanCurrentlyBeUsed` est faux (`initialCooldownTurns` de 1142 = 1),
    # `AttackQuery$$GetInvalidCasterReason` rend `broken(ValidRequest)` AVANT la cascade -- la regle
    # n'a PAS ete evaluee, donc ce pas ne dit rien d'elle. Ils sont COMPTES et affiches.
    ecartes = [s["step"] for s in suite if s["nat"] == int(TR.ValidRequest)]
    evalues = [s for s in suite if s["nat"] is not None and s["nat"] != int(TR.ValidRequest)]
    codes = [s["nat"] for s in evalues]
    # Le refus doit APPARAITRE (il n'etait pas la au 1er pas EVALUE) et ne plus DISPARAITRE.
    a_bascule = bool(codes) and codes[0] == 0 and refus in codes
    monotone = True
    vu_refus = False
    for c in codes:
        if c == refus:
            vu_refus = True
        elif vu_refus:
            monotone = False
    rang = next((s["step"] for s in evalues if s["nat"] == refus), None)
    print("  pas ECARTES (court-circuit `broken(ValidRequest)`, regle NON evaluee) : %s" % ecartes)
    print("  suite des casterReason EVALUES : %s" % [hex(c) for c in codes])
    print("  bascule 0x0 -> CasterHas2TurnsLeft au pas %s ; monotone : %s"
          % (rang, monotone))
    if rang is not None:
        # `refus <=> turns > limit - ended <=> ended > limit - turns <=> ended >= limit-turns+1`.
        # Le rang donne donc une MESURE indirecte du compteur natif `TurnComponent+0x40` : au PAS
        # DE BASCULE (le premier refus), `ended` vaut exactement `limit - turns + 1`, soit le
        # nombre de tours que `GetPlayerTurnOrder()[0]` a termines. C'est le seul canal par lequel
        # ce compteur soit observable a ce jour (`decisionView.turnsEnded` en publie la SOMME).
        print("  => au pas %d, `GetAmountOfTurnsEndedByPlayer(turnOrder[0])` vaut %d "
              "(deduit de `ended >= limit - turns + 1`), pour %d `endturn` emis -- coherent avec "
              "l'ALTERNANCE stricte des tours mesuree par #462-r4e-o-r2-r1-r1-r1."
              % (rang, BASCULE_ROUNDS - TURNS_ARG + 1, rang))
    print("  => le terme `- GetAmountOfTurnsEndedByPlayer(...)` est %s : sans lui, `2 <= %d` "
          "resterait VRAI a tous les pas." % ("MESURE" if a_bascule else "NON MESURE",
                                              BASCULE_ROUNDS))

    # ---------------------------------------------------------------- ACCORD PAS A PAS (#...-r1)
    # LE CRAN QUE L'ENCADREMENT NE POUVAIT PAS DONNER. Le port rend maintenant un verdict SANS
    # qu'on lui souffle `ended` -- on le confronte donc pas a pas au natif, sur les seuls pas
    # EVALUES (les court-circuites ne disent rien de la regle).
    pas_a_pas = [(s["step"], s["nat"], s["port"], s["port_ended"]) for s in evalues]
    desaccords = [t for t in pas_a_pas if t[1] != t[2]]
    print("  ACCORD PAS A PAS (step, natif, port, ended_port) : %s"
          % [(a, hex(b), hex(c), d) for a, b, c, d in pas_a_pas])
    print("  desaccords : %s" % (desaccords or "aucun"))
    # Le rang de bascule du PORT doit etre le MEME que celui du natif -- c'est ce qui confronte le
    # compteur lui-meme, et pas seulement la formule.
    rang_port = next((s["step"] for s in evalues if s["port"] == refus), None)
    print("  rang de bascule : natif=%s port=%s" % (rang, rang_port))
    # ANTI-REGIME DEGENERE : un accord ou le port refuse (ou accepte) PARTOUT ne prouve rien.
    ventil_port = {}
    for s in evalues:
        ventil_port[hex(s["port"])] = ventil_port.get(hex(s["port"]), 0) + 1
    print("  ventilation des verdicts PORT : %s" % ventil_port)
    accord_pas_a_pas = (not desaccords) and rang_port == rang and len(ventil_port) >= 2

    ok = a_bascule and monotone and accord_pas_a_pas
    for r in res:
        att = attendu[r["label"]]
        nat_ok = (r.get("nat") == att)
        port_ok = bool(r.get("port_constant")) and r.get("port") == att
        direct_ok = (r.get("port_direct") == att)
        ok = ok and nat_ok and port_ok and direct_ok
        print("[%s] natif=%s attendu=%s -> %s ; port(encadre)=%s -> %s ; port(direct)=%s -> %s"
              % (r["label"], "-" if r.get("nat") is None else hex(r["nat"]), hex(att),
                 "OK" if nat_ok else "MISMATCH",
                 "-" if r.get("port") is None else hex(r["port"]),
                 "OK" if port_ok else "MISMATCH",
                 hex(r.get("port_direct") or 0), "OK" if direct_ok else "MISMATCH"))
    print("[VERDICT] %s" % ("PASS" if ok else "FAIL"))
    print("[RAW] " + json.dumps({"statiques": res, "bascule": suite}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
