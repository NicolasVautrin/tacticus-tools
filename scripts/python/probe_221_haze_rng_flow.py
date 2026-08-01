"""case-221 -- le FLUX RNG du report de degat `HazeOfCorruption` : natif 8 tirages, port 6.

QUESTION (binaire) : le port consomme-t-il le MEME nombre de `genrand_int32`, aux MEMES points de
la cascade, que le natif ? Sinon, QUELLE operation native emet les tirages manquants ?

Le case-209 a livre la CHARGE UTILE (le montant transfere, bit-exact 6/6) et a NOMME l'ecart RNG
comme residu. Ce probe l'instrumente : il rejoue l'attaque OFFLINE sur le MEME flux, en capturant
pour CHAQUE tirage la PILE d'appel cote port (fichier + fonction sous `engine/`), et compare le
compte au `dumpRng` natif d'encadrement.

MONTAGE (identique a case-209, k = 1) : `deathBlightlord` vs `astraBullgryn` (aucun trigger, aucun
summon -> UNE seule emission de `On(0x2a = PreUnitAbility)`), relais `astraDreir` sur un voisin commun, board MC1_67.
`--hp` pilote le REGIME : la cible survit (aucun volet mort) / meurt sous le dernier coup / meurt
avant la fin de la serie. C'est l'ECHELLE qui attribue les tirages a un etage plutot qu'a un autre.

CLI (depuis scripts/python) :
  python probe_221_haze_rng_flow.py --seeds 777,88 --hp 8000,6000,5000
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback

from probe_r6_round_materialize import _mkrpc
from probe_159_ah_bounds import _board, _genrand_steps
from probe_dpw_weapon_cell import _replay_recording, _raw_stream, resolve as _rs
from probe_207_haze_pool_ladder import EXTRAS, _drive_pool
from probe_209_haze_damage_transfer import _build, _hp_map, _events


def _frames():
    """Les frames `engine/` de la pile courante, de la plus PROFONDE a la plus superficielle --
    la provenance du tirage, en ASCII et sans chemin absolu."""
    out = []
    for fr in traceback.extract_stack():
        p = fr.filename.replace("\\", "/")
        i = p.find("/engine/")
        if i < 0:
            continue
        out.append("%s:%s" % (p[i + 1:], fr.name))
    return out


def _origin(frames):
    """Le point d'emission RETENU : la frame `engine/` la plus profonde qui n'appartient PAS a la
    couche PRNG elle-meme (`runner/prng.py`) ni au wrapper d'enregistrement."""
    for f in reversed(frames):
        if "runner/prng.py" in f:
            continue
        return f
    return "?"


CONTAMINATED = 1244        # `EffectType.Contaminated` (0x4dc) -- effet de TUILE pose par 1203


def _contaminated(rpc, rid, board):
    """Les tuiles portant l'effet 1244 (`Contaminated`), lues DIRECTEMENT depuis `tileMeta` --
    le TEMOIN observable du `Maybe(chance)` d'`OnToxicDamageAbility` : si le `Maybe` est evalue et
    REUSSIT, une tuile apparait ici. C'est ce qui separe « le natif tire ici » de « le natif tire
    ailleurs » sans avoir a deviner."""
    from engine.runner.snapshot import tile_effects_footprint_live
    tiles = rpc("tileMeta", {"runnerId": rid}, 90)
    foot = tile_effects_footprint_live(tiles, board) or {}
    return sorted(t for t, effs in foot.items() if CONTAMINATED in effs)


def _next_bool_value(g):
    """`IntBasedMersenneTwister$$NextBool(chance)` = `NextInternal(1, 100) <= chance` : la valeur
    tiree, dans [1, 99]. Sert a PREDIRE, pour un rang donne du flux, si le `Maybe(25)` passerait --
    donc a choisir une seed ou le temoin `Contaminated` est OBSERVABLE."""
    return ((g >> 1) % 99) + 1


def _replay_traced(dv, ob, snap, board, rng0, cid, tid):
    """`_replay_recording` avec capture de la PROVENANCE de chaque `genrand_int32`. Le patch porte
    sur `IntBasedMersenneTwister.genrand_int32` (la classe de BASE), que la sous-classe
    `_Recording` de `probe_dpw_weapon_cell` appelle explicitement -- donc tous les tirages du
    replay passent par le wrapper, y compris ceux emis hors `next_internal`."""
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.operations.effects import AddEffectOperation
    picks = []
    posed = []
    orig = IntBasedMersenneTwister.genrand_int32
    orig_add = AddEffectOperation.execute

    def _traced(self):
        g = orig(self)
        picks.append({"g": g, "stack": _frames()})
        return g

    def _traced_add(state, **kw):
        out = orig_add(state, **kw)
        if int(kw.get("effect_type") or 0) == CONTAMINATED:
            posed.append({"target": kw.get("target"), "source": kw.get("source")})
        return out

    IntBasedMersenneTwister.genrand_int32 = _traced
    AddEffectOperation.execute = staticmethod(_traced_add)
    try:
        off = _replay_recording(dv, ob, snap, board, rng0, cid, tid, 0)
    finally:
        IntBasedMersenneTwister.genrand_int32 = orig
        AddEffectOperation.execute = staticmethod(orig_add)
    off["contaminated"] = posed
    for p in picks:
        p["origin"] = _origin(p["stack"])
    off["picks"] = picks
    return off


def _run(rpc, seed, hp, args):
    rid, sf = _build(seed, hp, args.armor)
    if rid is None:
        return None
    try:
        board = _board(rpc, rid)
        cid, tid, aid, err = _drive_pool(rpc, rid, board, args.k)
        if cid is None:
            print("[221] seed %s hp=%s : drive KO -- %s" % (seed, hp, err))
            return None
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        before = _hp_map(dv, snap)
        tiles0 = _contaminated(rpc, rid, board)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": aid},
            "captureEvents": True}, 120)
        rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
        tiles1 = _contaminated(rpc, rid, board)
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        after = _hp_map(dv2, snap2)
        relay = None
        for uid, u in before.items():
            if u["vis"] in EXTRAS and u["pos"] is not None:
                if relay is None or (before[relay]["pos"] == [None, None]):
                    relay = uid
        off = _replay_traced(dv, ob, snap, board, rng0, cid, tid)
        rpos = (before.get(relay) or {}).get("pos") if relay is not None else None
        return {"seed": seed, "hp": hp, "cid": cid, "tid": tid, "relay": relay,
                "relay_tile": board.id_at(*rpos) if (rpos and rpos[0] is not None) else None,
                "off_tiles": list(off.get("contaminated") or []),
                "n_native": _genrand_steps(rng0, rng1), "n_off": off["n_genrand"],
                "per_hit": list(off["per_hit"]), "cell": off["cell"],
                "rolls": list(off.get("rolls") or []), "picks": list(off.get("picks") or []),
                "raw": _raw_stream(rng0, 14), "before": before, "after": after,
                "tiles0": tiles0, "tiles1": tiles1,
                "tgt_tile": board.id_at(*((before.get(tid) or {}).get("pos") or (None, None)))
                if ((before.get(tid) or {}).get("pos") or [None])[0] is not None else None,
                "events": _events(res)}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="777")
    ap.add_argument("--hp", default="6000")
    ap.add_argument("--armor", type=int, default=0)
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--stacks", type=int, default=0,
                    help="nb de frames `engine/` a imprimer par tirage (0 = juste l'origine)")
    args = ap.parse_args()
    rpc = _mkrpc()
    rows = []
    for seed in [s for s in args.seeds.split(",") if s.strip()]:
        for hp in [int(h) for h in str(args.hp).split(",") if h.strip()]:
            r = _run(rpc, seed, hp, args)
            if r is None:
                continue
            rows.append(r)
            print("[221] seed %s hp=%d : NATIF %s tirages | PORT %s tirages  (ecart %+d)"
                  % (seed, hp, r["n_native"], r["n_off"], r["n_off"] - r["n_native"]))
            lo, hi = r["cell"]
            print("      cellule arme = %s ; raw resolus = %s"
                  % (r["cell"], [(i, _rs(lo, hi, g)) for i, g in enumerate(r["raw"])]))
            print("      raw en NextBool[1,99] = %s   (Maybe(25) passe si <= 25)"
                  % [(i, _next_bool_value(g)) for i, g in enumerate(r["raw"][:8])])
            print("      Contaminated LIVE : avant=%s apres=%s | PORT pose=%s"
                  " | tuile cible=%s tuile relais=%s"
                  % (r["tiles0"], r["tiles1"], json.dumps(r["off_tiles"]),
                     r["tgt_tile"], r["relay_tile"]))
            print("      PORT per_hit = %s" % r["per_hit"])
            for i, p in enumerate(r["picks"]):
                print("      port pick #%d  g=%-12s  <- %s" % (i, p["g"], p["origin"]))
                if args.stacks:
                    for f in p["stack"][-args.stacks:]:
                        print("            %s" % f)
            for i, rl in enumerate(r["rolls"]):
                print("      port roll #%d  [%s, %s] -> %s  (%s genrand)"
                      % (i, rl["lo"], rl["hi"], rl["out"], rl["n"]))
            dmg = [(td["tags"].get("Damage_Target_Id") or td["tags"].get("Unit_Id")
                    or td["tags"].get("Target_Id"), int(td["tags"]["Amount"]),
                    td["tags"].get("Effect_Type"))
                   for td in r["events"] if "Amount" in td["tags"]]
            print("      degats LIVE (cible, montant, effectType) = %s" % json.dumps(dmg))
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
