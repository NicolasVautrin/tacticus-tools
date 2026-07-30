#!/usr/bin/env python
"""Probe #175 -- le dict `ctx` des feuilles Tile(7) porte-t-il la cle `unit_traits` ?

CRITERE BINAIRE (mesure, pas lecture) : sur les DEUX chemins natifs qui emettent la MEME
`ComposedUtility` Tile(7) -- le sweep MOVE (`MovementActionGenerator.generate` ->
`engine.move.best_move_faithful`) et le terme Tile(7) de l'ATTAQUE
(`engine.playbook.base.tile_utility`) -- le dict qui atteint REELLEMENT
`BaseUtility.evaluate(self, tile, meta, ctx, wt)` contient-il `unit_traits` ?

Si NON : les 12 lectures `ctx["unit_traits"]` de `engine/utilities/tile.py` rendent 0.0 en
silence (`_has` est strict : cle absente -> False), donc 7 feuilles sont MORTES
(CapturePoint 24 +/-300, PowerUp 26, DespoiledGround 28, SummonDislikeDoorOpening 29,
HeroLikeDoorOpening 30, DoctrinaImperatives_AttractMechanicals 57,
MasterOfTheTutelaries_MoveTowardsTarget 62).

Le probe instrumente les INSTANCES de feuilles (`TILE_LEAVES`) : chaque `evaluate` enregistre
les cles du ctx recu, sans changer la valeur rendue. Il imprime aussi, pour chaque gate,
l'etat de son CO-GATE metadata par-tuile (`meta.is_territory`, `meta.tile_effect_type_ids`,
`meta.door`, ...) : une cle ctx presente ne ranime la feuille que si sa metadata l'est aussi.

Section C = disponibilite des donnees LIVE que le RPC `tileMeta` remonte deja
(`isTerritory`, `effects[].effectType`) et que le port jetait.

Runner dedie, dispose en fin. ASCII only (cp1252).

Usage :
  python probe_175_tile_leaf_unit_traits.py [--board MC1_67]
         [--p-units ...] [--a-units ...]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine import weights as W  # noqa: E402
from engine.playbook import scene as _scene  # noqa: E402
from engine.ai import context as _ai_ctx  # noqa: E402
from engine.utilities.tile import TILE_LEAF_IDS, TILE_LEAVES  # noqa: E402
from engine.utilities.utility_type import UtilityType  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

# (ligne source dans utilities/tile.py, feuille, cle meta CO-GATE) -- la table du mandat.
# #272 : l'ordinal est DERIVE du membre, jamais ecrit en dur. Les litteraux d'origine (24, 26, 28,
# 29, 30, 57, 62) dataient d'avant `fe5b9245` (#252 : `AttackTile` insere en 8, 59 membres decales
# de +1) et faisaient donc afficher a ce rapport `CapturePoint(24)` -- l'etiquette de la feuille
# VOISINE (`MoltenForm`). Meme ordinal perime, meme famille de degradation silencieuse que le rouge
# de #272 ; ici purement cosmetique (l'indexation, elle, passe par `TILE_LEAF_IDS`, des MEMBRES).
UNIT_TRAIT_GATES = [
    (233, "CapturePoint", int(UtilityType.CapturePoint), "is_territory", "traits 2/13 -> +/-300"),
    (246, "PowerUp", int(UtilityType.PowerUp), "occupant_is_powerup", "traits 2/13 -> -300"),
    (320, "DespoiledGround", int(UtilityType.DespoiledGround), "tile_effect_type_ids",
     "trait 2026 -> -5"),
    (322, "DespoiledGround", int(UtilityType.DespoiledGround), "tile_effect_type_ids",
     "traits 26/1006 -> -25"),
    (337, "SummonDislikeDoorOpening", int(UtilityType.SummonDislikeDoorOpening), "door",
     "trait 2 -> -50"),
    (351, "HeroLikeDoorOpening", int(UtilityType.HeroLikeDoorOpening), "door",
     "trait 16 -> -50 / (10-cost)*10"),
    (392, "DoctrinaImperatives_AttractMechanicals",
     int(UtilityType.DoctrinaImperatives_AttractMechanicals), "attract_mechanicals_neighbor",
     "trait 5 -> +10"),
    (459, "MasterOfTheTutelaries_MoveTowardsTarget",
     int(UtilityType.MasterOfTheTutelaries_MoveTowardsTarget), "movetowards_hexdist",
     "traits 2026/1019 -> -20 x d"),
]


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state, board, p_units, a_units, seed="41171", cap_wait_s=600, poll_s=20):
    args = [sys.executable, "rl_duel.py", "build", "--seed", seed,
            "--state-file", str(state), "--board", board,
            "--p-units", p_units, "--a-units", a_units,
            "--hp-target", "90000", "--hp-player", "90000"]
    waited = 0.0
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(args, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return json.loads(state.read_text())["runnerId"]
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or waited >= cap_wait_s:
            print("BUILD KO:", out[-600:])
            return None
        print("  cap sature, attente %ds (%.0f/%d)" % (poll_s, waited, cap_wait_s))
        time.sleep(poll_s)
        waited += poll_s


class _Spy:
    """Instrumente les INSTANCES de `TILE_LEAVES` : capture les cles du ctx qui atteint
    REELLEMENT `evaluate(tile, meta, ctx, wt)`. Ne change aucune valeur rendue."""

    def __init__(self):
        self.saved = []
        self.ctx_keys = {}      # {label: set(cles)}
        self.meta_keys = {}     # {label: set(cles)}
        self.calls = {}         # {label: {leafName: n}}
        self.label = "?"

    def arm(self):
        for i in TILE_LEAF_IDS:
            name, leaf = TILE_LEAVES.get(i, (None, None))
            if leaf is None:
                continue
            orig = leaf.evaluate
            spy = self

            def ev(tile, meta, ctx, wt, _orig=orig, _n=name):
                spy.ctx_keys.setdefault(spy.label, set()).update((ctx or {}).keys())
                spy.meta_keys.setdefault(spy.label, set()).update((meta or {}).keys())
                spy.calls.setdefault(spy.label, {})
                spy.calls[spy.label][_n] = spy.calls[spy.label].get(_n, 0) + 1
                return _orig(tile, meta, ctx, wt)

            self.saved.append((leaf, orig))
            leaf.evaluate = ev

    def disarm(self):
        for leaf, orig in self.saved:
            leaf.evaluate = orig
        self.saved = []


def _measure(sid, rid, wt, predictor, spy):
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 150)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    mine = [u for u in (dv.get("units") or []) if u.get("ctrl") and u.get("alive")]
    if not mine:
        print("aucune unite controlee vivante")
        return None
    rows = []
    for u in mine:
        uid = u["id"]
        ctx = _ai_ctx.build(lambda m, b, t: _r(sid, m, b, t), rid, dv, mov_by_unit, uid,
                            wt, predictor)
        # --- chemin 1 : sweep MOVE (MovementActionGenerator -> best_move_faithful) ---
        from engine.ai.action_generators import MovementActionGenerator
        spy.label = "MOVE"
        MovementActionGenerator().generate(ctx)
        # --- chemin 2 : terme Tile(7) de l'ATTAQUE (playbook.base.tile_utility) ---
        from engine.playbook.base import tile_utility
        spy.label = "ATTACK"
        pos = ctx.origin
        if pos is not None:
            tile_utility(ctx, pos)
        rows.append((uid, u.get("visualId")))
    return rows


def _tile_data_report(sid, rid):
    tm = _r(sid, "tileMeta", {"runnerId": rid}, 60)
    tiles = tm.get("tiles") or []
    n_terr = sum(1 for t in tiles if t.get("isTerritory"))
    n_eff = sum(1 for t in tiles if (t.get("effects") or []))
    types = sorted({int(e.get("effectType"))
                    for t in tiles for e in (t.get("effects") or [])
                    if e.get("effectType") is not None})
    names = sorted({e.get("name")
                    for t in tiles for e in (t.get("effects") or []) if e.get("name")})
    print("\n== C. donnees LIVE remontees par le RPC tileMeta (source des co-gates) ==")
    print("  tiles=%d  isTerritory=%d  tiles-avec-effet=%d" % (len(tiles), n_terr, n_eff))
    print("  effectType distincts sur tuiles : %s" % (types or "(aucun)"))
    print("  noms d'effets de tuile          : %s" % (names or "(aucun)"))
    return {"tiles": len(tiles), "territory": n_terr, "effect_types": types}


def run(sid, board, p_units, a_units, seed):
    state = ROOT / "logs" / "runners" / ("probe175-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    rid = _build(state, board, p_units, a_units, seed)
    if rid is None:
        return 1
    print("runner", rid, "board", board, "seed", seed)
    spy = _Spy()
    try:
        wt = W.load()
        predictor = _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t), rid)
        spy.arm()
        rows = _measure(sid, rid, wt, predictor, spy)
        spy.disarm()
        if rows is None:
            return 1
        print("unites balayees :", rows)

        print("\n== A. CRITERE -- cles du ctx qui atteint REELLEMENT BaseUtility.evaluate ==")
        verdict = {}
        for label in ("MOVE", "ATTACK"):
            keys = sorted(spy.ctx_keys.get(label) or ())
            has = "unit_traits" in keys
            verdict[label] = has
            print("  [%s] appels=%d" % (label, sum((spy.calls.get(label) or {}).values())))
            print("       ctx keys  = %s" % keys)
            print("       meta keys = %s" % sorted(spy.meta_keys.get(label) or ()))
            print("       unit_traits PRESENT ? %s" % ("OUI" if has else "NON"))
        print("  VERDICT : MOVE=%s ATTACK=%s" %
              ("OUI" if verdict.get("MOVE") else "NON",
               "OUI" if verdict.get("ATTACK") else "NON"))

        live = _tile_data_report(sid, rid)

        print("\n== B. les 8 sites de lecture `unit_traits` et leur CO-GATE metadata ==")
        print("  CABLE = ctx + meta arrivent ; EXERCE = la donnee live prend une valeur qui MORD.")
        meta_seen = set()
        for label in ("MOVE", "ATTACK"):
            meta_seen |= (spy.meta_keys.get(label) or set())
        for line, leaf, uid_, meta_key, effet in UNIT_TRAIT_GATES:
            ctx_ok = verdict.get("MOVE") and verdict.get("ATTACK")
            meta_ok = meta_key in meta_seen
            if not ctx_ok:
                state_s = "MORT (ctx)" if meta_ok else "MORT (ctx+meta)"
            elif not meta_ok:
                state_s = "MORT (meta)"
            elif meta_key == "is_territory" and not live["territory"]:
                state_s = "CABLE, 0 tuile"      # ruleset Territories absent de la seed BC
            else:
                state_s = "CABLE+EXERCABLE"
            print("  tile.py:%-4d %-40s meta.%-28s %-16s %s"
                  % (line, "%s(%d)" % (leaf, uid_), meta_key, state_s, effet))
        return 0
    finally:
        spy.disarm()
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        try:
            state.unlink()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="41171")
    ap.add_argument("--p-units", default="ultraEudorai,eldarRanger,adeptHospitaller")
    ap.add_argument("--a-units", default="deathBlightbringer,orksRuntherd,tyranWarrior")
    a = ap.parse_args()
    sid = _resolve_session()
    return run(sid, a.board, a.p_units, a.a_units, a.seed)


if __name__ == "__main__":
    raise SystemExit(main())
