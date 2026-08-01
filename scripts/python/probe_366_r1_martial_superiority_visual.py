"""Probe LIVE #366-r1 -- `1255 MartialSuperiority_Visual`, le MARQUEUR « riposte armee » de
`templChampion` (<< Brother Jaeger >>).

CE QU'IL MESURE, et pourquoi une absence ne suffirait pas. Le decompile dit que la SEULE semantique
de cet effet est sa `CreateActiveCondition` :

    IdunBattle.Entities.Effects.Loki.MartialSuperiority_VisualEffect$$CreateActiveCondition
        = op_LogicalNot( <DSLTriggers+0x28> )        # = NOT IsTurnOf(Owner)

Un marqueur sans contribution n'EMET rien : ni degat, ni stat, ni evenement. Chercher un observable
de comportement rendrait donc VERT pour « effet absent » comme pour « effet present et inerte ». Ce
probe lit donc la VALEUR DE RETOUR de la condition la ou le natif la publie -- le flag
`EffectComponent.IsActive @+0x5c`, expose entree par entree par `readEffectsByUnit` et rendu par
`decisionView` (les entrees a `false` n'etant publiees que sous `includeInactive`).

QUATRE etapes, chacune rend une observation :

  [0] POSE       -- Jaeger porte-t-il une instance 1255 ? (canal `includeInactive`) C'est la
                    reachability du poseur `MartialSuperiorityAddEffectAbility`, qui n'a AUCUNE ligne
                    dans les tables de symboles.
  [1] TOUR DU PORTEUR   -- `active` doit etre FAUX, et l'entree ABSENTE du canal par DEFAUT.
  [2] TOUR ADVERSE      -- `active` doit etre VRAI, et l'entree PRESENTE sur les DEUX canaux.
  [3] HYSTERESIS + PORT -- retour au tour du porteur (l'effet se re-eteint : c'est une CONDITION, pas
                    un one-shot), puis confrontation du PORT sur la MEME capture :
                    `EffectsState.active_effects` doit contenir 1255 ssi ce n'est pas le tour de
                    Jaeger, et le CONTREFACTUEL (bascule de `state.current_player_id` sur l'etat DEJA
                    charge) doit renverser le verdict.

Usage (depuis scripts/python) :
    python probe_366_r1_martial_superiority_visual.py --state-file <ABSOLU hors data/>
                                     [--board MC1_67] [--seed 777] [--keep]

ASCII only (console cp1252). Ne (re)injecte JAMAIS -- il consomme la session existante.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
CARRIER = "templChampion"           # Brother Jaeger -- HERO, dans `rl_duel build --list-pool`
FOE = "orksNob"
VISUAL = 1255                       # 0x4e7 EffectType.MartialSuperiority_Visual


def sid() -> int:
    return int(requests.get(HOST + "/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 90):
    r = requests.post("%s/api/scripts/%d/rpc" % (HOST, s),
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def dview(s: int, rid: int, inactive: bool):
    return rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                                   "includeInactive": bool(inactive)}, 120) or {}


def row(dv: dict, uid):
    return next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)


def alive(dv: dict, vis: str):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def eff(u, etype: int):
    return next((e for e in ((u or {}).get("effects") or [])
                 if e.get("effectType") == etype), None)


def build(state_file: str, board: str, seed: str) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
            "--state-file", state_file, "--p-units", CARRIER, "--a-units", FOE,
            "--hp-player", "999999", "--hp-target", "999999"]
    out = subprocess.run(argv, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("[1255] build KO rc=%d\n%s\n%s"
                         % (out.returncode, out.stdout[-2000:], out.stderr[-2000:]))
    return int(json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"])


def endturn(s: int, rid: int):
    return rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)


def to_turn_of(s: int, rid: int, owner, want: bool, max_steps: int = 8):
    """Fait avancer les tours jusqu'a ce que `currentPlayer == owner` soit `want`. Rend la vue."""
    for _ in range(max_steps):
        dv = dview(s, rid, True)
        if (dv.get("currentPlayer") == owner) is bool(want):
            return dv
        endturn(s, rid)
    return dview(s, rid, True)


def measure(s: int, rid: int, jid, label: str) -> dict:
    """Les DEUX canaux sur la MEME date. Rend {turn_of_owner, present_inactive, active, present_default}."""
    dvi = dview(s, rid, True)
    dvd = dview(s, rid, False)
    ui, ud = row(dvi, jid), row(dvd, jid)
    ei, ed = eff(ui, VISUAL), eff(ud, VISUAL)
    out = {
        "label": label,
        "currentPlayer": dvi.get("currentPlayer"),
        "owner": (ui or {}).get("owner"),
        "turn_of_owner": (dvi.get("currentPlayer") == (ui or {}).get("owner")),
        "present_inactive": ei is not None,
        "active": (None if ei is None else bool(ei.get("active"))),
        "present_default": ed is not None,
        "all_effects_inactive_channel": [(e.get("effectType"), e.get("name"), e.get("active"))
                                         for e in ((ui or {}).get("effects") or [])],
    }
    print("  [%s] tourDuPorteur=%s | includeInactive: present=%s active=%s | defaut: present=%s"
          % (label, out["turn_of_owner"], out["present_inactive"], out["active"],
             out["present_default"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    s = sid()
    rid = build(a.state_file, a.board, a.seed)
    print("[1255] runner %d  board=%s  seed=%s  porteur=%s" % (rid, a.board, a.seed, CARRIER))
    rc = 1
    try:
        dv = dview(s, rid, True)
        j = alive(dv, CARRIER)
        if j is None:
            print("[1255] %s ABSENT du runner -- montage KO" % CARRIER)
            return 3
        jid, owner = j["id"], j.get("owner")
        print("[1255] Jaeger uid=%s owner=%s  currentPlayer=%s"
              % (jid, owner, dv.get("currentPlayer")))

        # [0] POSE -- l'instance existe-t-elle du tout ?
        e0 = eff(row(dv, jid), VISUAL)
        print("[0] POSE : instance 1255 sur Jaeger = %s" % (json.dumps(e0) if e0 else "ABSENTE"))
        if e0 is None:
            print("[0] ECHEC : le poseur `MartialSuperiorityAddEffectAbility` n'a rien pose"
                  " (ou le canal ne le publie pas) -- rien a confronter.")
            return 4

        # [1] tour du PORTEUR  -> attendu : active == False, absent du canal par defaut
        to_turn_of(s, rid, owner, True)
        m_own = measure(s, rid, jid, "tour du PORTEUR")
        # [2] tour ADVERSE     -> attendu : active == True, present sur les deux canaux
        to_turn_of(s, rid, owner, False)
        m_foe = measure(s, rid, jid, "tour ADVERSE")
        # [3] HYSTERESIS : retour au tour du porteur
        to_turn_of(s, rid, owner, True)
        m_back = measure(s, rid, jid, "retour au PORTEUR")

        ok_native = (m_own["active"] is False and m_foe["active"] is True
                     and m_back["active"] is False
                     and m_own["present_default"] is False
                     and m_foe["present_default"] is True)
        print("[1-3] NATIF : condition `NOT IsTurnOf(Owner)` %s"
              % ("CONFIRMEE" if ok_native else "NON CONFIRMEE"))

        # [4] PORT sur la MEME capture (etat au tour du PORTEUR : 1255 doit etre INACTIF)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from engine.runner.snapshot import load_state, decision_view_seed_body
        from engine.entities.effects.loki.martial_superiority import MartialSuperiorityVisualEffect
        from engine.runner.components import unit_state_for_effects

        dvs = rpc(s, "decisionView", decision_view_seed_body(rid, maxRank=1, allAbilities=True), 120)
        ob = rpc(s, "observeBattle", {"runnerId": rid}, 60)
        snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 60)
        st = load_state(dvs, ob, snap)
        insts = [e for e in (st.effects.by_unit.get(jid) or []) if int(e.effect_type or 0) == VISUAL]
        klass = type(insts[0]).__name__ if insts else None
        print("[4] PORT : instances 1255 chargees = %d  classe = %s" % (len(insts), klass))
        if not insts:
            print("[4] ECHEC : le port n'a chargE aucune instance 1255 depuis la capture.")
            return 5
        if not isinstance(insts[0], MartialSuperiorityVisualEffect):
            print("[4] ECHEC : classe %s -- le registre ne route pas 1255 sur la classe portee."
                  % klass)
            return 6
        others = sorted(o for o in {u.get("owner") for u in (dvs.get("units") or [])}
                        if o is not None and o != owner)
        if not others:
            print("[4] ECHEC : aucun autre joueur dans la capture.")
            return 8
        foe_player = others[0]
        from engine.runner.operations.refresh_effects import refresh_stat_modifier_effects

        def port_at(player) -> dict:
            """Le port a la date « c'est le tour de `player` ». `refresh_stat_modifier_effects` est
            LITTERALEMENT la ligne que `turnflow` joue au StartTurn pour
            `RefreshEffectTrigger.TurnChanged` -> `RefreshEffectsOperation$$Execute(effectEntity =
            NUL)` : c'est ce qui ECRIT le flag `EffectComponent.IsActive @+0x5c` offline."""
            st.current_player_id = player
            us = unit_state_for_effects(st, jid)
            cond = bool(insts[0].is_active(us))
            refresh_stat_modifier_effects(st)                    # mirror StartTurn / TurnChanged
            flag = bool(insts[0].active)
            us2 = unit_state_for_effects(st, jid)
            pub = VISUAL in [int(e.effect_type or 0) for e in st.effects.active_effects(jid, us2)]
            return {"cond": cond, "flag": flag, "published": pub}

        p_own = port_at(owner)
        p_foe = port_at(foe_player)
        p_back = port_at(owner)
        for lbl, p in (("tour du PORTEUR", p_own), ("tour ADVERSE", p_foe),
                       ("retour au PORTEUR", p_back)):
            print("[4] PORT [%s] is_active=%s flag=%s publie(active_effects)=%s"
                  % (lbl, p["cond"], p["flag"], p["published"]))
        ok_port = (p_own == {"cond": False, "flag": False, "published": False}
                   and p_foe == {"cond": True, "flag": True, "published": True}
                   and p_back == {"cond": False, "flag": False, "published": False})
        # CONTRE-EPREUVE : le MEME effet capte, route sur `BaseEffect` (= le port AVANT ce cas).
        # `BaseEffect.is_active` rend `True` INCONDITIONNELLEMENT -> le halo « riposte armee »
        # serait publie pendant le tour de Jaeger, ou le natif l'eteint.
        from engine.entities.effects.base import BaseEffect
        naked = BaseEffect(name="MartialSuperiority_Visual", effect_type=VISUAL, active=True)
        st.current_player_id = owner
        us_own = unit_state_for_effects(st, jid)
        print("[4] CONTRE-EPREUVE (classe NON portee, BaseEffect) : is_active(tour du porteur)=%s"
              " -- attendu True (le defaut), donc le regime MORD" % bool(naked.is_active(us_own)))
        bites = bool(naked.is_active(us_own)) is True
        print("[4] PORT %s le natif" % ("REPRODUIT" if ok_port else "DIVERGE de"))
        rc = 0 if (ok_native and ok_port and bites) else 7
    finally:
        if not a.keep:
            try:
                rpc(s, "disposeRunner", {"runnerId": rid}, 30)
                print("[1255] runner %d dispose" % rid)
            except Exception as e:
                print("[1255] dispose KO: %s" % str(e)[:200])
    return rc


if __name__ == "__main__":
    sys.exit(main())
