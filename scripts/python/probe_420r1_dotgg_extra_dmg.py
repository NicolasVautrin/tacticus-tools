#!/usr/bin/env python
"""#420-r1 -- MESURE de l'axe DEGAT de `DefenderOfTheGreaterGood` (`1182 ..._ExtraDmg`, jumeau drone
`1306`), et en particulier de la BASCULE PSYCHIC que le natif porte dans

    IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraDmgEffect$$CreateDamageModifier
      = EffectBonus.ForAddition(
            get_OwnerIsCaster & IsRangedAttack() & !DamageProfileIs(0xd = Psychic),
            ConfigVar(8 = extraDmg, GetAbilityState(effet), config = effet+0x60) )

Le `ForAddition` n'apparait pas comme un appel dans le decompile de `CreateDamageModifier` : il y est
INLINE. On le lit a la DISPOSITION des champs -- `IdunBattle.Entities.Effects.EffectBonus$$ForAddition`
ecrit le montant a `+0x10`, `...$$ForPercentIncrease` a `+0x08` ; le corps de `CreateDamageModifier`
ecrit `trigger` a `+0x00`, `0` a `+0x08` et `amount` a `+0x10` -> c'est bien le canal ADDITIF.

Le probe MESURE (il n'assert pas ; c'est `tests/engine/runner/test_dotgg_extra_dmg_live.py` qui
GARDE). Pour chaque bras il rend, sur le MEME etat :

  * `live`     -- les `Amount` par coup de l'attaque normale du beneficiaire (evenements natifs) ;
  * `offline`  -- le rejeu du port depuis le snapshot pris JUSTE AVANT l'attaque ;
  * `no_aura`  -- le MEME rejeu, l'effet `DefenderOfTheGreaterGood_ExtraDmg` RETIRE du porteur.

`no_aura` est la CONTRE-EPREUVE DE SENSIBILITE : sans elle, un accord `live == offline` ne dit pas si
le montage exerce quoi que ce soit. Sur le bras NON-PSYCHIC le retrait DOIT changer les valeurs ; sur
le bras PSYCHIC il ne doit RIEN changer (le gate a deja tout ferme).

Usage (depuis scripts/python, session Frida deja warmee) :

    python probe_420r1_dotgg_extra_dmg.py --state-file <ABSOLU hors data/> \
        [--benef darkaHellblaster] [--tgt-dist 2,3] [--passive-level 30] [--keep]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

import requests

HOST = os.environ.get("TACTICUS_HOST", "http://127.0.0.1:8765")
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "tests", "engine", "runner"))

from _dotgg_aura_regime import (ADJACENT, CARRIER, DotggAuraHarness,  # noqa: E402
                                RING2_NON_TAU, RING2_TAU, FAR)

from engine.entities.effects.magnitude import ability_var              # noqa: E402
from engine.entities.pathfinding.board import Board                    # noqa: E402

EFFECT_DMG = "DefenderOfTheGreaterGood_ExtraDmg"


def session_id() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"])


def make_rpc(sid: int):
    def rpc(method: str, args=None, timeout: int = 90):
        r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                          json={"method": method, "args": [args or {}],
                                "timeout": int(timeout) * 1000},
                          timeout=timeout + 30)
        if r.status_code >= 400:
            raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
        body = r.json()
        if body.get("error"):
            raise RuntimeError(str(body["error"])[:400])
        return body.get("result")
    return rpc


def build(seed: str, board: str, benef: str, state_file: str, passive_level=None) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", state_file, "--board", board,
            "--p-units", "%s,%s" % (CARRIER, benef), "--a-units", "orksNob",
            "--hp-target", "300000", "--hp-player", "300000", "--no-ai"]
    if passive_level is not None:
        # DISSOCIE le niveau du PASSIF (que lit `GetAbilityState` sur la config du passif) de celui
        # de l'ACTIF -- le regime nominal les met TOUS DEUX a 50 (#408), donc un port qui lirait le
        # mauvais y rendrait le meme chiffre.
        argv += ["--unit-stat", "%s:PassiveAbilityLevel=%d" % (CARRIER, int(passive_level))]
    if os.path.exists(state_file):
        os.unlink(state_file)                       # un state-file perime relirait un rid mort
    out = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if not os.path.exists(state_file):
        raise RuntimeError("rl_duel build KO rc=%d: %s"
                           % (out.returncode, (out.stderr or out.stdout or "")[-600:]))
    with open(state_file, encoding="utf-8") as fh:
        return int(json.load(fh)["runnerId"])


def measure(harness, benef, regime, tgt_dist):
    rec = harness.run(benef, regime, tgt_dist=tgt_dist)
    if rec is None:
        return {"regime": regime, "error": "montage NON INSTALLE"}
    off = harness.replay_offline(rec)
    no_aura = harness.replay_offline(rec, drop_carrier_effects=(EFFECT_DMG,))
    lvl, mult = None, None
    for e in (off["state"].effects.by_unit.get(rec["carrier"]) or []):
        if getattr(e, "name", None) == EFFECT_DMG:
            lvl, mult = e.ability_level, e.ability_variables_multiplier
    delta = [a - b for a, b in zip(off["per_hit"], no_aura["per_hit"])] \
        if len(off["per_hit"]) == len(no_aura["per_hit"]) else None
    return {"regime": regime, "benef": benef,
            "turns_started": rec.get("turns_started"),
            "live": rec["live_per_hit"], "profiles": rec.get("live_profiles"),
            "offline": off["per_hit"], "no_aura": no_aura["per_hit"],
            "delta_per_hit": delta,
            "tag_keys": sorted((rec.get("live_first_damage_tags") or {}).keys()),
            "carrier_effects": off["carrier_effects"],
            "ability_level": lvl, "multiplier": mult,
            "expected_extra_dmg": ability_var("DefenderOfTheGreaterGood", "extraDmg", lvl,
                                              multiplier_pct=mult) if lvl else None}


def show(m):
    if m.get("error"):
        print("  %-14s ERROR %s" % (m["regime"], m["error"]))
        return
    print("  %-14s benef=%-20s turns=%s" % (m["regime"], m["benef"], m["turns_started"]))
    print("      profiles       : %s" % (sorted(set(map(str, m["profiles"] or []))),))
    print("      tag keys       : %s" % (m.get("tag_keys"),))
    print("      live           : %s" % (m["live"],))
    print("      offline        : %s" % (m["offline"],))
    print("      offline no-aura: %s" % (m["no_aura"],))
    print("      delta/coup     : %s" % (m["delta_per_hit"],))
    print("      ablvl=%s mult=%s extraDmg attendu=%s | agree=%s"
          % (m["ability_level"], m["multiplier"], m["expected_extra_dmg"],
             m["live"] == m["offline"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--benef", default="darkaHellblaster")
    ap.add_argument("--tgt-dist", default="2,3")
    ap.add_argument("--regimes", default=ADJACENT)
    ap.add_argument("--passive-level", type=int, default=None)
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    td = tuple(int(x) for x in a.tgt_dist.split(","))
    sid = session_id()
    rpc = make_rpc(sid)
    rid = build(a.seed, a.board, a.benef, a.state_file, a.passive_level)
    print("[probe] runner=%s benef=%s board=%s seed=%s passive_level=%s"
          % (rid, a.benef, a.board, a.seed, a.passive_level))
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    h = DotggAuraHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
    try:
        for reg in a.regimes.split(","):
            reg = reg.strip()
            if reg not in (ADJACENT, RING2_NON_TAU, RING2_TAU, FAR):
                print("  regime inconnu: %s" % reg)
                continue
            show(measure(h, a.benef, reg, td))
    finally:
        if not a.keep:
            h.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
