#!/usr/bin/env python
"""Probe #235 -- le flag `UnitFlag.Moved` d'un etat RECHARGE vient du canal live, pas d'une pose
manuelle de fixture.

LE FAIT A MESURER. `test_sentinel_directives_live` re-posait `UnitFlag.Moved` a la main
(`components.set_moved_flag`) parce que son commentaire affirmait « aucun RPC n'expose les
UnitFlags ». Le capteur O5 rend cette affirmation fausse : `combatSnapshot.units[].unitFlags`
publie les ids `UnitFlag` POSES, obtenus en invoquant la fonction NOMMEE
`IdunBattle.Entities.UnitExtensions$$HasFlag(unit, flag)` une fois par valeur d'enum (le
`OrderedSet<UnitFlag>` @+0x10 d'`IdunBattle.Entities.Components.UnitFlagsComponent` n'est PAS lu en
memoire), et `snapshot._load_unit_flags` le seede sur tout etat charge.

TRI-ETAT DU CANAL, et il porte : `null` = NON MESURE (methode irresolue / enum vide) -> `load_state`
laisse le defaut du port intact ; `[]` = mesure, aucun flag pose ; liste = mesure. Rabattre `null`
sur `[]` ferait passer un capteur MORT pour un caster immobile.

DECOMPOSITION PAR ETAGE (aucun scalaire fitte) -- montage SentinelDirectives (actif 1139,
`admecDestroyer` vs `necroOverlord`, board MC1_67, seed 777), caster RAPPROCHE de la cible (donc
`MoveUnitOperation` a pose `Moved` cote natif) :

  etage 1  canal      : `combatSnapshot.units[caster].unitFlags` + `unitFlagTypes` (ids et table lus
                        au RUNTIME) ;
  etage 2  seed       : `unit_has_moved` sur l'etat rendu par `load_state` -- doit valoir VRAI sans
                        aucune pose manuelle, et coincider avec le nb de `move` que le probe a emis
                        depuis le debut du tour (oracle INDEPENDANT du canal) ;
  etage 3  degat      : le meme cast rejoue offline sous TROIS hypotheses, meme RNG seede --
                        (A) canal seul, (B) canal + `set_moved_flag` (l'ancien contournement),
                        (C) canal AVEUGLE (`unitFlags` force a `null`, monde d'avant O5).
                        A == B == LIVE prouve que le contournement etait redondant ; C != LIVE
                        (facteur 1.25 = `traitVariables.heavyWeaponExtraDmg`) prouve que le canal
                        est ce qui PORTE le gate, et non un decor.

Gate concerne : `IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier`
= `... & (!HasFlag(Self, 0 = Moved) | HasFlag(Self, 0xc = Teleported))`.

ASCII only (cp1252). Usage : python probe_235_moved_channel_sentdir.py [--seed 777]
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))

from rl_collect_batch import _resolve_session, _rpc                            # noqa: E402
from engine.entities.pathfinding.board import Board                            # noqa: E402
from engine.runner.snapshot import load_state                                  # noqa: E402
from engine.runner.runner import Runner                                        # noqa: E402
from engine.runner.messages import ActiveAbilityMessage                        # noqa: E402
from engine.runner.components import set_moved_flag, unit_has_moved            # noqa: E402

import test_sentinel_directives_live as T                                      # noqa: E402

FLAG_MOVED = 0          # `enums.tsv` : confronte a la table que le hook lit au RUNTIME


def _mk_rpc(sid):
    def rpc(method, body, timeout=90):
        return (_rpc(sid, method, [body], timeout=timeout).get("result") or {})
    return rpc


def _cast_offline(state, s0, cid, tid):
    """Rejoue le cast 1139 sur `state`, RNG re-seede a l'etat dumpe avant le cast live."""
    state.rng = T._seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=tid, ability_type=T.ABILITY))
    last = runner.ability_handler.last or {}
    return (last.get("attack") or {}).get("per_hit") or []


def run(seed: str = "777") -> dict:
    sid = _resolve_session()
    rpc = _mk_rpc(sid)
    out: dict = {"seed": seed}
    rid, sf, err = T._build(seed, f"{T.TARGET_VIS},necroWarden")
    if rid is None:
        return {"error": "build KO: %s" % err}
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            return {"error": "boardGraph indispo"}
        board = Board(bg["tiles"], adjacency="native_sym")
        placed = T._approach(rpc, rid, board, T.TARGET_VIS)
        if placed is None:
            return {"error": "caster hors portee apres approche"}
        cid, tid, my, moves = placed
        out["moves_emitted_this_turn"] = moves

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)

        # --- etage 1 : le CANAL ---------------------------------------------------------------
        types = snap.get("unitFlagTypes")
        su = next((u for u in (snap.get("units") or []) if u.get("entityId") == cid), {})
        flags = su.get("unitFlags")
        out["flag_types_count"] = len(types or {})
        out["enum_moved_id"] = (types or {}).get("Moved")
        out["enum_agrees"] = (types or {}).get("Moved") == FLAG_MOVED
        out["caster_flags_measured"] = flags is not None
        out["caster_flags"] = flags
        out["caster_moved_live"] = (None if flags is None else bool(FLAG_MOVED in flags))

        # --- etage 2 : le SEED de l'etat recharge ----------------------------------------------
        st_chan = load_state(dv, ob, snap, board=board)
        out["seeded_moved_channel"] = unit_has_moved(st_chan, cid)

        snap_blind = copy.deepcopy(snap)                 # monde d'AVANT O5 : canal non mesure
        for u in (snap_blind.get("units") or []):
            u["unitFlags"] = None
        st_blind = load_state(dv, ob, snap_blind, board=board)
        out["seeded_moved_blind"] = unit_has_moved(st_blind, cid)

        # --- etage 3 : le DEGAT sous les trois hypotheses --------------------------------------
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not (isinstance(s0, dict) and s0.get("ok")):
            return {"error": "dumpRng KO"}
        live_ph, crit, block, evade, res = T._cast_live(rpc, rid, cid, tid)
        out["live_per_hit"] = live_ph
        out["live_clean"] = not (crit or block or evade)
        if not live_ph:
            out["error"] = "aucun degat live : %s" % str(res)[:160]
            return out

        out["off_A_channel"] = _cast_offline(load_state(dv, ob, snap, board=board), s0, cid, tid)
        st_b = load_state(dv, ob, snap, board=board)
        set_moved_flag(st_b, cid)                        # ANCIEN contournement, par-dessus le canal
        out["off_B_channel_plus_manual"] = _cast_offline(st_b, s0, cid, tid)
        out["off_C_blind"] = _cast_offline(
            load_state(dv, ob, snap_blind, board=board), s0, cid, tid)
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            if sf is not None:
                sf.unlink()
        except Exception:
            pass
    return out


def _verdict(m: dict) -> tuple:
    if m.get("error"):
        return False, m["error"]
    if not m.get("enum_agrees"):
        return False, "UnitFlag renumerote : Moved=%s cote runtime" % m.get("enum_moved_id")
    if not m.get("caster_flags_measured"):
        return False, "unitFlags NON MESURE sur le caster (capteur mort)"
    if m.get("seeded_moved_channel") is not m.get("caster_moved_live"):
        return False, "load_state n'a pas seede ce que le canal rend"
    if m.get("seeded_moved_channel") is not (m.get("moves_emitted_this_turn", 0) > 0):
        return False, "desaccord canal / deplacements emis par la fixture"
    a, b, c, live = (m.get("off_A_channel"), m.get("off_B_channel_plus_manual"),
                     m.get("off_C_blind"), m.get("live_per_hit"))
    if not (a == live):
        return False, "canal seul != live (%s vs %s)" % (a, live)
    if not (a == b):
        return False, "la pose manuelle CHANGE le resultat (%s vs %s) -- elle n'est pas redondante" % (a, b)
    if m.get("moves_emitted_this_turn", 0) > 0 and c == live:
        return False, ("l'hypothese AVEUGLE rend le meme degat que le live : le montage ne "
                       "discrimine pas (le caster a-t-il vraiment bouge ?)")
    return True, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    a = ap.parse_args()
    m = run(a.seed)
    print(json.dumps(m, indent=2, sort_keys=True))
    ok, why = _verdict(m)
    print("VERDICT : %s %s" % ("OK" if ok else "ECHEC", why))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
