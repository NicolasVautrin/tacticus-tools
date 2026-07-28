#!/usr/bin/env python
"""Probe #178 -- les GATES D'UNITE de la surcharge d'INSTANCE de
`IdunBattle.Core.Services.DamagePrediction$$IsOverkill`.

QUESTION BINAIRE MESUREE : un coup a `dmg >= 2 x PV` marque-t-il TOUJOURS la cible << overkill >> ?
Le decompile dit NON. La surcharge d'instance (celle dont le corps est INLINE dans
`IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation`, et dont le resultat est le
`didOverkill` du `DamageAppliedResult` que
`IdunBattle.Operations.ApplyDamageOperation$$Execute+0x17d5` transforme en
`UnitFlagsComponent.Add(target, 8)` = `UnitFlag.Overkilled`) applique DEUX gates d'unite AVANT la
formule :

    if (!UnitExtensions.CanBeOverkilled(target)) return false;   // !HasTrait(u, 0x1b Steppable)
    ...
    suppress = UnitExtensions.HasFlag(target, 0x13);             // UnitFlag.PreventOverkill

Le doublon 2-args que le port consommait cote COMBAT (supprime par #178) n'avait NI l'un NI l'autre.

OBSERVABLE (aucun RPC ne lit les flags d'unite -> on passe par un CONSOMMATEUR du flag) --
`TerrifyingCrescendo` (triggered 1435, passif d'`emperNoiseMarine` << Shiron >>), branche 1 =
`On(UnitDeath=0) & OwnerIsActor & TargetIsOverkilled`, et
`IdunBattleLogic.Entities.DSLFactory$$TargetIsOverkilled` = `HasFlagAbilityTrigger(target, 8)`.
Chaque declenchement incremente l'effet `TerrifyingCrescendo_ExtraDmg` (1424) sur Shiron, dont le
`level` est expose tel quel par `decisionView.units[].effects[]` : un compteur d'overkills LISIBLE.

REGIMES (memes rosters, meme geometrie, meme degat -- SEULE la victime change) :
  * `--case control` : victime `genesPrimus` (Isaak), 400 PV, AUCUN gate -> crescendo DOIT monter.
  * `--case titus`   : victime `ultraTitus`, 400 PV, porte `FuelledByFury_BlockOverkill` (1354) des le
        deploiement -- i2 << The first time each turn that Titus is defeated he cannot be Overkilled >>.
        L'effet pose `UnitFlag.PreventOverkill` (`...$$ApplyInternal` -> `Add(u, 0x13)`) -> crescendo
        NE DOIT PAS monter.
Les deux regimes tuent avec la MEME attaque (Shiron, melee, 1452-2178 sur 400 PV) : c'est la paire qui
fait la mesure, un seul cote ne conclurait rien.

MELEE OBLIGATOIRE : le trait `SuppressiveFire` de Shiron pose `Pinned` (1065) sur les attaques RANGED,
ce qui alimente la BRANCHE 2 du MEME crescendo. Au contact hex l'attaque normale part en melee, et la
paire est auto-certifiante : `titus` a +0 => la branche 2 est muette dans ce montage => le +1 de
`control` ne peut venir que de la branche overkill.

GEOMETRIE DRIVEE (jamais subie) : `applyAction move` ne verifie PAS la propriete -> on TELEPORTE la
victime au centre et les deux attaquants sur son ring 1 (le pathfinding naturel echouait : Shiron porte
`HeavyWeapon` = mobilite reduite, et les voisins de la victime au spawn etaient occupes).

Le probe confronte, sur CHAQUE regime : le LIVE, le corps SUPPRIME (recopie verbatim ci-dessous), et
le corps LIVRE evalue sur l'ETAT OFFLINE reellement charge (`load_state`) -- pas sur des booleens
saisis a la main.

ASCII only (cp1252). Usage :
  python probe_178_overkill_gate.py --case both
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                        # noqa: E402
from engine.services.trait_damage_limits import (unit_is_overkill,         # noqa: E402
                                                 _overkill_threshold_pct)
from engine.runner.components import (can_be_overkilled,                   # noqa: E402
                                      unit_prevents_overkill)
from engine.runner.snapshot import load_state                              # noqa: E402

SHIRON = "emperNoiseMarine"       # passif TerrifyingCrescendo (compteur d'overkills lisible)
KILLER = "ultraInceptorSgt"       # 2e unite de mon camp : sans elle l'attaque de Shiron finit mon tour
# 2e ennemi OBLIGATOIRE : sans lui, tuer la victime TERMINE la bataille et `decisionView` ne rend plus
# d'unites -> le crescendo devient illisible (faux negatif mesure a la 1re passe). Tenu a l'ecart.
FILLER = "astraBullgryn"
VICTIMS = {"control": "genesPrimus", "titus": "ultraTitus"}
CRESCENDO = "TerrifyingCrescendo_ExtraDmg"
NORMAL_ATTACK = 69                # `Loki_NormalAttack` (id CONCRET, cf. NormalAttackType@0x28)


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def build(state_file: Path, seed: int, victim: str, hp_target: int) -> int:
    state_file.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state_file), "--board", "MC1_67", "--rank", "17",
         "--p-units", "%s,%s" % (SHIRON, KILLER),
         "--a-units", "%s,%s" % (victim, FILLER),
         "--hp-target", str(hp_target), "--crit", "0,0", "--block-target", "0,0"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[178] build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
        sys.exit(2)
    return int(json.loads(state_file.read_text())["runnerId"])


def view(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)


def by_visual(dv, vis, alive=True):
    for u in (dv.get("units") or []):
        if u.get("visualId") == vis and (bool(u.get("alive")) or not alive):
            return u
    return None


def crescendo_level(dv, unit_id) -> int:
    """Niveau de `TerrifyingCrescendo_ExtraDmg` sur `unit_id` (0 = effet absent)."""
    for u in (dv.get("units") or []):
        if int(u.get("id") or -1) != int(unit_id):
            continue
        for e in (u.get("effects") or []):
            if e.get("name") == CRESCENDO and not e.get("removed"):
                return int(e.get("level") or 0)
    return 0


def move(sid, rid, uid, col, row):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def attack(sid, rid, attacker_id, target_id):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(attacker_id), "targetId": int(target_id),
        "abilityType": NORMAL_ATTACK}}, 120)


def predicted_damage(sid, rid, attacker_id, target_id):
    """Plage de degat BRUT du prochain coup (`aiPredict` = `GetAllPredictions`). `totalDmg*` = brut
    sante+armure+bouclier -> EGALE le degat sante brut quand la cible n'a ni armure ni bouclier
    (le cas ici : `--hp-target` remet `Armor`/`FixedArmor` a 0, et personne n'a de bouclier)."""
    p = (_r(sid, "aiPredict", {"runnerId": rid, "unitId": int(attacker_id),
                               "targetId": int(target_id), "abilityType": NORMAL_ATTACK}, 90)
         or {}).get("pred") or {}
    if p.get("totalDmgMin") is None:
        return None, None
    return int(p["totalDmgMin"]), int(p["totalDmgMax"])


def killed_by(dv, uid, killer_id) -> bool:
    u = next((x for x in (dv.get("units") or []) if int(x["id"]) == int(uid)), None)
    return u is not None and u.get("killerId") is not None and int(u["killerId"]) == int(killer_id)


def _legacy_is_overkill(hp_before, damage) -> bool:
    """LE CORPS SUPPRIME (doublon 2-args de `services/damage_prediction.py`, pre-#178), conserve ici
    VERBATIM pour que le probe puisse dire LEQUEL des deux corps le live refute."""
    import gameconfig as GC
    if damage is None or hp_before is None or hp_before <= 0:
        return False
    pct = int(GC.global_value("overkillDmgPctOfHealth") or 100)
    return (int(damage) - int(hp_before)) * 100 >= pct * int(hp_before)


def offline_verdict(cap, victim_id, hp, dmg):
    """Le corps LIVRE, evalue sur l'ETAT OFFLINE reellement charge depuis la capture live."""
    from engine.entities.pathfinding.board import Board
    st = load_state(cap["dec"], cap["ob"], cap["snap"],
                    board=Board(cap["bg"]["tiles"], adjacency="evenq"))
    tgt = st.get_entity(int(victim_id))
    cbo = can_be_overkilled(tgt)
    prv = unit_prevents_overkill(st, int(victim_id))
    return unit_is_overkill(hp, dmg, can_be_overkilled=cbo, prevent_overkill=prv), cbo, prv


def setup(sid, state_file, seed, victim, center, verbose=True):
    """Build + GEOMETRIE DRIVEE : victime au centre, Shiron et la 2e unite sur son ring 1."""
    rid = build(state_file, seed, victim, hp_target=400)
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    ccol, crow = center
    ring = [board.coord(t) for t in board.neighbours(board.id_at(ccol, crow))]
    if len(ring) < 3:
        raise RuntimeError("centre (%d,%d) trop pauvre en voisins (%d)" % (ccol, crow, len(ring)))
    dv = view(sid, rid)
    ids = {v: by_visual(dv, v)["id"] for v in (SHIRON, KILLER, victim, FILLER)}
    move(sid, rid, ids[FILLER], 6, 7)                      # hors de portee de tout
    move(sid, rid, ids[victim], ccol, crow)
    move(sid, rid, ids[KILLER], *ring[0])
    move(sid, rid, ids[SHIRON], *ring[1])
    dv = view(sid, rid)
    for v, uid in ids.items():
        u = next(x for x in dv["units"] if int(x["id"]) == int(uid))
        if verbose:
            print("[178]   u%-3d %-18s pos=%s hp=%s eff=%s"
                  % (uid, v, u.get("pos"), u.get("hp"),
                     [e.get("name") for e in (u.get("effects") or [])]))
        if v == victim and int(u.get("hp") or 0) != 400:
            # GARDE anti-pollution : un tir d'overwatch pendant le placement fausserait la mesure.
            raise RuntimeError("SETUP POLLUE : la victime a deja perdu des PV")
    return rid, ids


def run(case: str, seed: int = 17811, center=(3, 4), state_file=None,
        keep: bool = False, verbose: bool = True) -> dict:
    """MONTAGE COMPLET d'un regime, reutilisable (le probe EST la fixture -- cf. `probe_psychic_aoe`).

    Rend `{"case", "victim", "rid", "hp", "dmg_min", "dmg_max", "live_level_before",
    "live_level_after", "live_overkill", "port_overkill", "legacy_overkill",
    "can_be_overkilled", "prevent_overkill"}` -- ou `{"error": ...}` si le regime n'est pas atteint."""
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parent.parent / "logs" / "ovk178.json")
    sf.parent.mkdir(parents=True, exist_ok=True)
    victim = VICTIMS[case]
    rid = None
    try:
        rid, ids = setup(sid, sf, seed, victim, center, verbose=verbose)
        dv = view(sid, rid)
        vic = by_visual(dv, victim)
        hp, lvl0 = int(vic["hp"]), crescendo_level(dv, ids[SHIRON])
        dmin, dmax = predicted_damage(sid, rid, ids[SHIRON], vic["id"])
        if dmin is None:
            return {"error": "aiPredict illisible (%s)" % case}
        cap = {"dec": dv,
               "ob": _r(sid, "observeBattle", {"runnerId": rid}, 60),
               "snap": _r(sid, "combatSnapshot", {"runnerId": rid}, 120),
               "bg": _r(sid, "boardGraph", {"runnerId": rid}, 60)}
        attack(sid, rid, ids[SHIRON], vic["id"])
        dv2 = view(sid, rid)
        lvl1 = crescendo_level(dv2, ids[SHIRON])
        if not killed_by(dv2, vic["id"], ids[SHIRON]):
            return {"error": "%s : la victime n'a pas ete tuee par Shiron" % case}
        live = (lvl1 - lvl0) > 0
        old = _legacy_is_overkill(hp, dmin)
        new, cbo, prv = offline_verdict(cap, vic["id"], hp, dmin)
        out = {"case": case, "victim": victim, "rid": rid, "hp": hp,
               "dmg_min": dmin, "dmg_max": dmax,
               "live_level_before": lvl0, "live_level_after": lvl1, "live_overkill": live,
               "port_overkill": bool(new), "legacy_overkill": bool(old),
               "can_be_overkilled": bool(cbo), "prevent_overkill": bool(prv)}
        if verbose:
            print("[178] %s : PV=%d degat=[%s,%s] seuil=%d%%"
                  % (case, hp, dmin, dmax, _overkill_threshold_pct()))
            print("[178]   gates offline : can_be_overkilled=%s prevent_overkill=%s" % (cbo, prv))
            print("[178]   corps SUPPRIME (2 args)      -> overkill=%s" % old)
            print("[178]   corps LIVRE  (instance #178) -> overkill=%s" % new)
            print("[178]   LIVE crescendo %d -> %d       -> overkill=%s" % (lvl0, lvl1, live))
            print("[178]   ACCORD : livre=%s  supprime=%s" % (new == live, old == live))
        return out
    finally:
        if rid is not None and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=("control", "titus", "both"), default="both")
    ap.add_argument("--seed", type=int, default=17811)
    ap.add_argument("--center", default="3,4")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    center = tuple(int(x) for x in args.center.split(","))
    cases = ("control", "titus") if args.case == "both" else (args.case,)
    oks = []
    for i, case in enumerate(cases):
        r = run(case, seed=args.seed + i, center=center, state_file=args.state_file, keep=args.keep)
        if "error" in r:
            print("[178] %s : %s" % (case, r["error"]))
            oks.append(False)
        else:
            oks.append(r["port_overkill"] == r["live_overkill"])
    print("[178] BILAN : %s" % ("OK" if oks and all(oks) else "ECHEC/INDETERMINE %s" % (oks,)))
    sys.exit(0 if (oks and all(oks)) else 1)


if __name__ == "__main__":
    main()
