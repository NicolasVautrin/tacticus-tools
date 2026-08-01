#!/usr/bin/env python
"""Probe #389-r2 -- `IdunBattle.Operations.KillUnitOperation$$RemoveEffects` : PORT contre NATIF.

CE QU'IL MESURE
---------------
QUAND UNE UNITE MEURT, QUELS EFFETS RESTENT ATTACHES A ELLE ?

Le natif vide TOUS les effets du mort. `IdunBattle.Operations.KillUnitOperation$$Execute` appelle
TROIS fois `IdunBattle.Operations.KillUnitOperation$$RemoveEffects(killed, step)` -- un par valeur
de `IdunBattle.Operations.KillUnitStep` (`0=PreUnitRemove, 1=AfterUnitRemove, 2=AfterDeathTrigger`)
-- et chacun delegue au slot 0x5a de `Core.Services.OperationProcessor`
(`IdunBattle.Operations.RemoveEffectsOperation$$Execute`), qui retire chaque entite-effet par
`IdunBattle.Operations.RemoveEffectOperation$$Execute`.

AVANT #389-r2 le port n'en portait qu'un VOLET ETROIT (les effets a
`applied_ability_modifications`) : sur un bras lethal, natif `[]` contre port
`[1026, 1098, 1361, 1362]` -- trois des quatre effets n'ayant AUCUN rapport avec l'ability qui
avait servi a le decouvrir. C'est cet ecart que ce probe chiffre et referme.

BRAS -- deux NATURES de mort, deux chemins d'appel distincts vers la meme operation :
  * `--kill-by attack` (ici) : la CIBLE meurt d'une ATTAQUE NORMALE
    (`AttackUnitMessage` -> `DamageHandler` -> `_apply_damage_pipeline`) ;
  * la mort par ABILITY + NOVA est mesuree par `probe_389_ramming_speed_combat_port.py
    --hp-player 5000` (le caster meurt de son propre contrecoup `AttackWithAttackDamage`, sa nova
    `Explodes` part pendant le cast), dont le cliquet de retrait est RE-ARME par #389-r2.

CANAL -- `decisionView` **`includeInactive`** (`snapshot.decision_view_seed_body`), le SEUL
comparable a `State.effects.by_unit` : le canal par DEFAUT laisse tomber les effets INERTES et
ferait confondre << retire >> avec << desactive >> (piege mesure en #389-r1).

Le probe REFUSE de conclure (`BRAS NON DISCRIMINANT`) plutot que de mesurer degrade : il exige que
la cible PORTE au moins un effet avant le coup, et qu'elle MEURE des deux cotes.

ASCII only (cp1252). Usage (depuis scripts/python, host up, session deja warmee) :
    python probe_389r2_kill_unit_remove_effects.py
    python probe_389r2_kill_unit_remove_effects.py --board C1_20 --seed 39100
    python probe_389r2_kill_unit_remove_effects.py --mutate no-kill-remove   # DOIT rougir
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import hexgeo

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]

from rl_collect_batch import _resolve_session, _rpc                          # noqa: E402
from probe_353r1_ramming_speed_charge_tile import (                          # noqa: E402
    _pos, _view, controlled_by_current_player, drive_to, ensure_turn)

BOARD = "MC1_67"
P_UNITS = "orksKillaKan,astraBullgryn"
# ⚠ CHOIX DE ROSTER, pas un defaut arbitraire : `ultraTitus` est ECARTE du camp adverse. Il porte
# `FuelledByFury_CanRevive` (1324) / `FuelledByFury_BlockOverkill` (1354) et la riposte
# `FinalJustice`, et sur ce montage le natif inflige 45000 PV de plus a l'attaquant que le port --
# un ecart MESURE, INDEPENDANT de #389-r2 (identique avec ET sans le fix), donc du BRUIT pour ce
# probe. Il est consigne comme residu dans `docs/rl/case-389-ramming-speed-combat.md`.
A_UNITS = "necroWarden,necroDestroyer"
TARGET_VISUAL = "necroDestroyer"   # porte 1009 (Overwatch) + 1018 -- deux effets a retirer
HP_TARGET = 1                  # la cible DOIT mourir du premier coup
MUTATIONS = ("none", "no-kill-remove")


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed: int, board: str,
           p_units: str = P_UNITS, a_units: str = A_UNITS) -> int:
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board, "--rank", "17",
           "--p-units", p_units, "--a-units", a_units,
           "--hp-player", "900000", "--hp-target", str(HP_TARGET), "--no-ai"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-1200:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _dv_inactive(sid, rid):
    """`decisionView` sur le canal `includeInactive` -- le seul comparable a `State.effects.by_unit`."""
    from engine.runner.snapshot import decision_view_seed_body
    return _r(sid, "decisionView", decision_view_seed_body(rid, allAbilities=True, maxRank=32), 180)


def _effects_of(dv, uid) -> list:
    for u in (dv.get("units") or []):
        if int(u.get("id")) == int(uid):
            return sorted(int(e.get("effectType") or -1) for e in (u.get("effects") or []))
    return []


def _state_builder(sid, rid, board):
    """Etat + rng CAPTURES avant le coup -> fabrique d'etats rejouables (recette `probe_226r`)."""
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state, decision_view_seed_body
    dv = _r(sid, "decisionView", decision_view_seed_body(rid, allAbilities=True, maxRank=32), 180)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    rng0 = _r(sid, "dumpRng", {"runnerId": rid}, 40)

    def build():
        st = load_state(dv, ob, snap, board=board)
        if isinstance(rng0, dict) and rng0.get("mt"):
            r = IntBasedMersenneTwister()
            r.mt = list(rng0["mt"])
            r.mti = rng0["mti"]
            st.rng = r
        return st
    return build, dv, bool(isinstance(rng0, dict) and rng0.get("mt"))


def _load_board(sid, rid):
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    return Board(bg["tiles"], adjacency="evenq")


def _apply_mutation(mutate: str):
    """CONTRE-EPREUVE `no-kill-remove` : neutralise le `RemoveEffects` de la sequence de mort --
    exactement l'etat d'AVANT #389-r2. Le symbole est resolu au niveau MODULE par
    `AttackDamageOperation._kill_unit_operation`, donc un patch d'attribut suffit."""
    from engine.runner.operations import damage as D
    saved = D._kill_unit_remove_effects

    def _restore():
        D._kill_unit_remove_effects = saved

    if mutate == "no-kill-remove":
        D._kill_unit_remove_effects = lambda *a, **k: []
    return _restore


def _pick_target(dv_inactive, dv, my_team_owner, target_visual: str = None) -> tuple:
    """Choisit (attaquant, cible) : la cible = l'ENNEMI VIVANT qui porte le PLUS d'effets (sans quoi
    le bras ne discrimine rien), ou celui de `target_visual` si impose ; l'attaquant = une unite du
    joueur courant qui expose une attaque normale."""
    eff_count = {}
    for u in (dv_inactive.get("units") or []):
        eff_count[int(u.get("id"))] = len(u.get("effects") or [])
    mine, foes = [], []
    for u in (dv.get("units") or []):
        if not u.get("alive"):
            continue
        (mine if u.get("owner") == my_team_owner else foes).append(u)
    if not mine or not foes:
        return (None, None, {})
    if target_visual:
        foes = [u for u in foes if u.get("visualId") == target_visual]
        if not foes:
            return (None, None, eff_count)
    foes.sort(key=lambda u: (-eff_count.get(int(u["id"]), 0), int(u["id"])))
    tgt = foes[0]
    att = None
    for u in mine:
        if any(ab.get("kind") == "normal" for ab in (u.get("abilities") or [])):
            att = u
            break
    if att is None:
        return (None, None, {})
    return (int(att["id"]), int(tgt["id"]), eff_count)


def _roster(dv, dvi) -> list:
    """Diagnostic : `[{id, visualId, owner, hp, effects}]` -- ce que le montage a REELLEMENT pose."""
    eff = {int(u.get("id")): sorted(int(e.get("effectType") or -1) for e in (u.get("effects") or []))
           for u in (dvi.get("units") or [])}
    return [{"id": int(u.get("id")), "visualId": u.get("visualId"), "owner": u.get("owner"),
             "hp": u.get("hp"), "effects": eff.get(int(u.get("id")), [])}
            for u in (dv.get("units") or [])]


def _normal_ability_id(dv, uid):
    for u in (dv.get("units") or []):
        if int(u.get("id")) == int(uid):
            return next((int(ab["id"]) for ab in (u.get("abilities") or [])
                         if ab.get("kind") == "normal"), None)
    return None


def _adjacent_free(board, dv, tgt_pos, busy) -> tuple:
    """Une tuile marchable ADJACENTE a la cible et libre -- l'attaquant doit y aller (melee)."""
    for t in board.by_id:
        if not board.walkable(t):
            continue
        p = board.coord(t)
        if hexgeo.distance(p, tgt_pos) == 1 and tuple(p) not in busy:
            return tuple(p)
    return None


def _hp_offline(st) -> dict:
    from engine.runner.components import HealthComponent
    out = {}
    for eid, e in st.entities.items():
        hc = e.get_component(HealthComponent)
        if hc is not None and hc.hp is not None:
            out[int(eid)] = int(max(0, hc.hp))
    return out


def run(seed: int = 39100, board: str = BOARD, mutate: str = "none", verbose: bool = True,
        p_units: str = P_UNITS, a_units: str = A_UNITS, target_visual: str = TARGET_VISUAL,
        scan: bool = False) -> dict:
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage

    sid = _resolve_session()
    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    sf = logs / ("p389r2-%s.json" % uuid.uuid4().hex[:8])
    out: dict = {"seed": seed, "board": board, "mutation": mutate,
                 "p_units": p_units, "a_units": a_units}
    rid = None
    try:
        rid = _build(sf, seed, board, p_units, a_units)
        out["runner"] = rid
        board_obj = _load_board(sid, rid)
        dv0 = _view(sid, rid)
        dvi0 = _dv_inactive(sid, rid)
        out["roster"] = _roster(dv0, dvi0)
        if scan:
            out["ok"] = True
            out["verdict"] = "SCAN : roster + effets lus, rien n'est joue"
            if verbose:
                print("[389r2] runner=%s board=%s seed=%s SCAN" % (rid, board, seed))
                for u in out["roster"]:
                    print("  roster  u%-4s %-22s owner=%-4s hp=%-8s effets=%s"
                          % (u["id"], u["visualId"], u["owner"], u["hp"], u["effects"]))
            return out
        cur = dv0.get("currentPlayer")
        att, tgt, eff_count = _pick_target(dvi0, dv0, cur, target_visual)
        if att is None or tgt is None:
            out["error"] = "aucun couple (attaquant avec attaque normale / ennemi vivant) lisible"
            return out
        out["attacker_id"], out["target_id"] = att, tgt
        out["effects_before_target"] = _effects_of(dvi0, tgt)
        if not out["effects_before_target"]:
            out["error"] = ("la cible %d ne porte AUCUN effet avant le coup -- le bras ne peut "
                            "rien discriminer" % tgt)
            return out

        # --- geometrie : l'attaquant au CONTACT de la cible (melee), personne d'autre ne bouge.
        tp = _pos(dv0, tgt)
        busy = {tuple(_pos(dv0, int(u["id"]))) for u in (dv0.get("units") or [])
                if u.get("alive") and int(u["id"]) not in (att,)}
        dest = _adjacent_free(board_obj, dv0, tp, busy)
        if dest is None:
            out["error"] = "aucune tuile libre adjacente a la cible sur %s" % board
            return out
        out["geometry"] = {"target": list(tp), "attacker": list(dest)}
        if not drive_to(sid, rid, {att: dest}):
            out["error"] = "drive KO : voulu %s obtenu %s" % (list(dest),
                                                              _pos(_view(sid, rid), att))
            return out
        out["turn_given"] = ensure_turn(sid, rid, att)
        ctrl = controlled_by_current_player(sid, rid)
        out["attacker_has_turn"] = (int(att) in ctrl) if ctrl else None

        # --- etat + rng CAPTURES juste avant le coup
        build, dv, has_rng = _state_builder(sid, rid, board_obj)
        out["rng_captured"] = has_rng
        norm = _normal_ability_id(dv, att)
        out["normal_ability"] = norm
        if norm is None:
            out["error"] = "l'attaquant %d n'expose pas d'attaque normale" % att
            return out

        # --- PORT
        restore = _apply_mutation(mutate)
        try:
            st = build()
            Runner(st).install_default_handlers(20).apply(AttackUnitMessage(att, tgt))
            port_eff = sorted(int(e.effect_type) for e in (st.effects.by_unit.get(int(tgt)) or [])
                              if not e.consumed)
            port_hp = _hp_offline(st)
        finally:
            restore()
        out["port_effects_target"] = port_eff
        out["port_target_dead"] = (port_hp.get(int(tgt), 1) <= 0)

        # --- NATIF
        res = _r(sid, "applyAction", {"runnerId": rid, "captureEvents": False, "action": {
            "kind": "ability", "casterId": int(att), "targetId": int(tgt),
            "abilityType": int(norm)}}, 150) or {}
        act0 = (res.get("actions") or [{}])[0]
        out["live_error"], out["live_mutated"] = act0.get("error"), bool(act0.get("mutated"))
        dvi1 = _dv_inactive(sid, rid)
        out["live_effects_target"] = _effects_of(dvi1, tgt)
        live_hp = {int(u["id"]): int(u.get("hp") or 0) for u in (dvi1.get("units") or [])}
        out["live_target_dead"] = (live_hp.get(int(tgt), 1) <= 0)
        ids_common = sorted(set(port_hp) & set(live_hp))
        out["hp_port"] = {str(u): port_hp[u] for u in ids_common}
        out["hp_live"] = {str(u): live_hp[u] for u in ids_common}
        out["hp_match"] = all(port_hp[u] == live_hp[u] for u in ids_common)
        # Ventilation de l'ecart de PV : sur le MORT (l'observable de ce probe) vs sur une AUTRE
        # unite (bruit du montage -- riposte, nova, DoT -- ETRANGER a `KillUnitOperation$$
        # RemoveEffects`). Les deux sont publies, aucun n'est masque.
        out["hp_mismatch_units"] = [str(u) for u in ids_common if port_hp[u] != live_hp[u]]
        out["hp_match_dead"] = (port_hp.get(int(tgt)) == live_hp.get(int(tgt)))

        out["effects_match"] = (out["port_effects_target"] == out["live_effects_target"])
        out["dead_keeps_effects_port_only"] = bool(
            out["port_target_dead"] and out["port_effects_target"]
            and not out["live_effects_target"])
        out["both_died"] = bool(out["port_target_dead"] and out["live_target_dead"])
        out["match"] = bool(out["effects_match"] and out["hp_match"] and out["both_died"])
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        sf.unlink(missing_ok=True)

    if scan:
        pass
    elif out.get("error"):
        out["ok"] = False
        out["verdict"] = "MONTAGE KO : %s" % out["error"]
    elif out.get("attacker_has_turn") is not True:
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT : l'attaquant n'a pas la main "
                          "(attacker_has_turn=%s)." % out.get("attacker_has_turn"))
    elif not out.get("live_mutated"):
        out["ok"] = False
        out["verdict"] = "ATTAQUE NATIVE REFUSEE (%s) -- rien n'est mesure" % out.get("live_error")
    elif not out.get("both_died"):
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT : la cible n'est pas morte des DEUX cotes "
                          "(port=%s natif=%s) -- l'observable ne porte pas sur KillUnitOperation."
                          % (out.get("port_target_dead"), out.get("live_target_dead")))
    elif mutate != "none":
        out["ok"] = not out["match"]
        out["verdict"] = (
            "MUTATION %r : le port MUTE %s le natif -- le bras %s ce terme. "
            "(effets du mort port=%s natif=%s / PV %s)"
            % (mutate, "DIVERGE de" if not out["match"] else "s'accorde AVEC",
               "DISCRIMINE" if not out["match"] else "NE DISCRIMINE PAS",
               out["port_effects_target"], out["live_effects_target"], out["hp_match"]))
    elif out["match"]:
        out["ok"] = True
        out["verdict"] = ("PORT == NATIF : la cible %d meurt en portant %s, et les DEUX cotes la "
                          "laissent avec %s ; PV identiques sur %d unites."
                          % (out["target_id"], out["effects_before_target"],
                             out["live_effects_target"], len(out.get("hp_live") or {})))
    else:
        out["ok"] = False
        out["verdict"] = ("PORT != NATIF : effets du mort port=%s natif=%s (%s, le mort GARDE ses "
                          "effets cote PORT SEUL=%s) | PV du MORT identiques=%s | PV divergents "
                          "sur %s (port=%s natif=%s)"
                          % (out["port_effects_target"], out["live_effects_target"],
                             out["effects_match"], out["dead_keeps_effects_port_only"],
                             out.get("hp_match_dead"), out.get("hp_mismatch_units"),
                             out.get("hp_port"), out.get("hp_live")))

    if verbose:
        print("[389r2] runner=%s board=%s seed=%s mutation=%s"
              % (out.get("runner"), board, seed, mutate))
        for u in (out.get("roster") or []):
            print("  roster  u%-4s %-22s owner=%-4s hp=%-8s effets=%s"
                  % (u["id"], u["visualId"], u["owner"], u["hp"], u["effects"]))
        if scan:
            print("[389r2] %s" % out.get("verdict"))
            return out
        print("[389r2] attaquant=%s cible=%s main=%s rng=%s normale=%s"
              % (out.get("attacker_id"), out.get("target_id"), out.get("attacker_has_turn"),
                 out.get("rng_captured"), out.get("normal_ability")))
        print("  effets de la cible AVANT   %s" % out.get("effects_before_target"))
        print("  effets du MORT   port=%s   natif=%s   (mort port=%s natif=%s)"
              % (out.get("port_effects_target"), out.get("live_effects_target"),
                 out.get("port_target_dead"), out.get("live_target_dead")))
        print("  PV               port=%s" % json.dumps(out.get("hp_port")))
        print("                   natif=%s" % json.dumps(out.get("hp_live")))
        print("  PV du MORT identiques=%s   unites divergentes=%s"
              % (out.get("hp_match_dead"), out.get("hp_mismatch_units")))
        print("[389r2] %s" % out.get("verdict"))
        print("[389r2] -> %s" % ("OK" if out.get("ok") else "ECHEC"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=39100)
    ap.add_argument("--board", default=BOARD, help="board CHOISI (runner.md sec.2), jamais subi")
    ap.add_argument("--mutate", choices=MUTATIONS, default="none",
                    help="GARDE ADVERSARIALE : le port est volontairement FAUX, le probe DOIT rougir")
    ap.add_argument("--p-units", default=P_UNITS)
    ap.add_argument("--a-units", default=A_UNITS)
    ap.add_argument("--target-visual", default=TARGET_VISUAL,
                    help="impose la CIBLE par visualId ; '' = l'ennemi qui porte le plus d'effets")
    ap.add_argument("--scan", action="store_true",
                    help="monte le runner, LIT le roster + les effets, ne joue rien")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(seed=a.seed, board=a.board, mutate=a.mutate, verbose=not a.json,
              p_units=a.p_units, a_units=a.a_units, target_visual=a.target_visual, scan=a.scan)
    if a.json:
        print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
