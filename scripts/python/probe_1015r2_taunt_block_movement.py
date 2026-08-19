#!/usr/bin/env python
"""probe_1015r2_taunt_block_movement -- `Taunted_BlockMovement` (25) IMMOBILISE, confronte au natif.

CE QUE CE PROBE MESURE
----------------------
#1015-r1 a porte le 4e etage d'`IdunBattle.Entities.UnitExtensions$$CanMove` --
`IdunBattle.Entities.Components.MovementComponent$$IsAllowedToMove` = `<+0x50>.Count == 0` -- en
n'inscrivant au registre `BLOCK_UNIT_MOVEMENT_EFFECT_TYPES` que `1235
InstinctiveBehaviour_BlockMovement`, seul `EffectType` dont l'appariement vers une classe qui ECRIT
ce dictionnaire fut alors etabli. #1015-r2 en inscrit TROIS de plus, et ce probe les CONFRONTE sur
le seul des trois qui se monte en un cast : `25 Taunted_BlockMovement`.

LA CHAINE, LUE
--------------
`IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal` (composite `27
Taunted_OnlySpecificTargets`, base `ABondEffect`) spawne ses sous-effets par
`IdunBattle.Entities.Effects.BaseEffect$$AddSubEffectWithSameTurns`, dont `25`. La classe qui sert
`25` ecrit `MovementComponent+0x50` (`BlockUnitMovement*Effect$$ApplyInternal`), donc
`IsAllowedToMove` devient FAUX et `IdunBattle.Core.Services.MovementQuery$$GetMovableTilesFor` sort
a VIDE. L'oracle natif est donc `aiMovableTiles`, exactement comme pour `1235`.

L'APPARIEMENT `25 -> classe` est etabli OFFLINE par `probe_1015r2_effectsdb_slot_de_classe.py`
(slot `Il2CppClass*` partage par `25`/`91`/`1016`, groupe de taille exactement 3). Ce probe-ci
mesure l'OBSERVABLE : le taunte peut-il encore marcher ?

LES QUATRE ETAGES
-----------------
0. MONTAGE  -- le taunte porte `27` ET `25` dans `decisionView.units[].effects`.
1. NATIF    -- `aiMovableTiles(taunte)` : NON VIDE avant le cast, VIDE apres.
2. PORT     -- `engine.runner.components.unit_extensions_can_move` : `True` avant, `False` apres.
3. TEMOIN   -- un AUTRE ennemi, non taunte, sur le MEME plateau et au MEME instant, reste mobile
               des DEUX cotes. Sans lui, un accord obtenu en regime degenere (plus personne ne
               bouge parce que le tour a tourne) ne prouverait rien.
4. MUTATION ADVERSARIALE -- la table est AMPUTEE de `25` en memoire, et le port est re-interroge
               sur le MEME etat : il doit alors rendre `True` la ou le natif rend VIDE. C'est le
               ROUGE d'avant le fix, joue DANS le probe -- pas un souvenir.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_1015r2_taunt_block_movement.py
    python probe_1015r2_taunt_block_movement.py --seed 31337 --board C4_09

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session                        # noqa: E402

import probe_247_splash_targeting as P247                            # noqa: E402
import probe_436_taunt_targeting as P436                             # noqa: E402

from engine.entities.effect_type import EffectType                   # noqa: E402
from engine.entities.effects.loki import instinctive_behaviour as _instinctive   # noqa: E402
from engine.runner import components as _components                  # noqa: E402

CRUSHING = 1105                                     # `CrushingClaws` (porteur `tyranTyrantGuard`)
TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)          # 27, le COMPOSITE
BLOCK_MOVEMENT = int(EffectType.Taunted_BlockMovement)         # 25, le SOUS-EFFET mesure ici
P_UNITS = ["tyranTyrantGuard", "ultraCalgar"]
A_UNITS = "necroWarden,necroWarden,necroWarden,necroWarden"


def _mesure(sid, rid, uid):
    """(tuiles natives, verdict du port) pour `uid`, sur un etat capture A CET INSTANT."""
    nat = P247._movable(sid, rid, uid)
    dv, payloads = P436._capture(sid, rid)
    st = P436._mk_state(payloads)
    port = _components.unit_extensions_can_move(st, int(uid))
    effets = [int(e[1] or -1) for e in P436._effects_of(dv, uid)]
    return {"nat": len(nat), "port": port, "effets": effets, "_st": st}


def _tour_de(sid, rid, uid, maxit=8):
    """Rend la main au camp de l'entite `uid` (chaine d'`endturn`, runner `--no-ai`)."""
    for _ in range(maxit):
        d = P247._dv(sid, rid)
        u = next((x for x in (d.get("units") or []) if int(x["id"]) == int(uid)), None)
        if u is not None and u.get("ctrl"):
            return True
        P247._act(sid, rid, {"kind": "endturn"}, 60)
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--a-units", default=A_UNITS)
    a = ap.parse_args(argv)

    sid = _resolve_session()
    rid, state_file = P436._build(sid, a.seed, a.board, P_UNITS, a.a_units)
    print("[build] runner=%d board=%s seed=%s" % (rid, a.board, a.seed))
    verdicts = {}
    try:
        for _ in range(P247.TOURS_DE_CHAUFFE):
            P247._act(sid, rid, {"kind": "endturn"}, 60)

        # --- GEOMETRIE : le tauntant AU CONTACT d'un ennemi (CrushingClaws = RANGE_ADJACENT) ----
        tauntee = P436._make_adjacent(sid, rid, "tyranTyrantGuard")
        if tauntee is None:
            print("[FAIL] impossible d'amener tyranTyrantGuard au contact d'un ennemi")
            return 2
        # LE TEMOIN : un AUTRE ennemi, celui qui ne sera pas taunte. Choisi AVANT le cast pour que
        # le choix ne puisse pas dependre du resultat.
        d0 = P247._dv(sid, rid)
        tu = next(x for x in d0["units"] if int(x["id"]) == tauntee)
        temoin = next((int(x["id"]) for x in d0["units"]
                       if x.get("alive") and x.get("owner") == tu.get("owner")
                       and int(x["id"]) != tauntee), None)
        print("[geometrie] taunte=u%s temoin=u%s" % (tauntee, temoin))
        if temoin is None:
            print("[FAIL] aucun temoin (il faut >= 2 ennemis vivants)")
            return 2

        # --- BASELINE : AVANT le cast, dans le tour du camp du taunte -------------------------
        if not _tour_de(sid, rid, tauntee):
            print("[FAIL] impossible de rendre la main au camp du taunte")
            return 2
        avant = _mesure(sid, rid, tauntee)
        avant_temoin = _mesure(sid, rid, temoin)
        print("[AVANT] taunte : natif=%d tuiles ; port can_move=%s ; effets=%s"
              % (avant["nat"], avant["port"], avant["effets"]))
        print("[AVANT] temoin : natif=%d tuiles ; port can_move=%s"
              % (avant_temoin["nat"], avant_temoin["port"]))

        # --- LE CAST -------------------------------------------------------------------------
        P247._give_turn_to(sid, rid, "tyranTyrantGuard")
        dvc = P247._dv(sid, rid)
        guard = P247._by_vis(dvc, "tyranTyrantGuard")
        if guard is None:
            print("[FAIL] tyranTyrantGuard absent au moment du cast")
            return 2
        cid = int(guard["id"])
        r = P247._act(sid, rid, {"kind": "ability", "casterId": cid,
                                 "abilityType": CRUSHING, "targetId": tauntee}, 120)
        mut = ((r or {}).get("actions") or [{}])[0].get("mutated")
        print("[cast] CrushingClaws u%d -> u%d : mutated=%s" % (cid, tauntee, mut))
        if not mut:
            print("[FAIL] le cast n'a pas mute l'etat -- rien a mesurer")
            return 2

        # --- APRES : meme mesure, dans le tour du camp du taunte ------------------------------
        if not _tour_de(sid, rid, tauntee):
            print("[FAIL] impossible de rendre la main au camp du taunte apres le cast")
            return 2
        apres = _mesure(sid, rid, tauntee)
        apres_temoin = _mesure(sid, rid, temoin)
        print("[APRES] taunte : natif=%d tuiles ; port can_move=%s ; effets=%s"
              % (apres["nat"], apres["port"], apres["effets"]))
        print("[APRES] temoin : natif=%d tuiles ; port can_move=%s ; effets=%s"
              % (apres_temoin["nat"], apres_temoin["port"], apres_temoin["effets"]))

        # ---------------------------------------------------------------- ETAGE 0 -- MONTAGE
        verdicts["0_montage_27"] = TAUNTED in apres["effets"]
        verdicts["0_montage_25"] = BLOCK_MOVEMENT in apres["effets"]

        # ---------------------------------------------------------------- ETAGE 1 -- NATIF
        verdicts["1_natif_avant_non_vide"] = avant["nat"] > 0
        verdicts["1_natif_apres_vide"] = apres["nat"] == 0

        # ---------------------------------------------------------------- ETAGE 2 -- PORT
        verdicts["2_port_avant_true"] = avant["port"] is True
        verdicts["2_port_apres_false"] = apres["port"] is False

        # ---------------------------------------------------------------- ETAGE 3 -- TEMOIN
        verdicts["3_temoin_natif_mobile"] = apres_temoin["nat"] > 0
        verdicts["3_temoin_port_mobile"] = apres_temoin["port"] is True
        verdicts["3_temoin_sans_25"] = BLOCK_MOVEMENT not in apres_temoin["effets"]

        # ------------------------------------------------- ETAGE 4 -- MUTATION ADVERSARIALE
        # La table AMPUTEE de `25` : c'est exactement l'etat du port AVANT #1015-r2. Sur le MEME
        # etat capture, il doit alors rendre `True` la ou le natif rend VIDE -- c'est le ROUGE,
        # joue ici, pas raconte.
        table = _instinctive.BLOCK_UNIT_MOVEMENT_EFFECT_TYPES
        try:
            _instinctive.BLOCK_UNIT_MOVEMENT_EFFECT_TYPES = tuple(
                t for t in table if int(t) != BLOCK_MOVEMENT)
            ampute = _components.unit_extensions_can_move(apres["_st"], int(tauntee))
        finally:
            _instinctive.BLOCK_UNIT_MOVEMENT_EFFECT_TYPES = table
        print("[MUTATION] table amputee de %d -> port can_move=%s (natif=%d tuiles)"
              % (BLOCK_MOVEMENT, ampute, apres["nat"]))
        verdicts["4_mutation_desaccorde"] = (ampute is True and apres["nat"] == 0)

        print("")
        for k in sorted(verdicts):
            print("  [%s] %s" % ("PASS" if verdicts[k] else "FAIL", k))
        print("[RAW] %s" % json.dumps({
            "runner": rid, "board": a.board, "seed": a.seed,
            "tauntee": tauntee, "temoin": temoin,
            "avant": {k: v for k, v in avant.items() if k != "_st"},
            "apres": {k: v for k, v in apres.items() if k != "_st"},
            "avant_temoin": {k: v for k, v in avant_temoin.items() if k != "_st"},
            "apres_temoin": {k: v for k, v in apres_temoin.items() if k != "_st"},
            "mutation_can_move": ampute,
            "verdicts": verdicts}, ensure_ascii=True))
        return 0 if all(verdicts.values()) else 1
    finally:
        try:
            P247._r(sid, "disposeRunner", {"runnerId": rid}, 60)
            print("[dispose] runner=%d" % rid)
        except Exception as exc:                                    # pragma: no cover
            print("[dispose] echec : %s" % exc)
        Path(state_file).unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
