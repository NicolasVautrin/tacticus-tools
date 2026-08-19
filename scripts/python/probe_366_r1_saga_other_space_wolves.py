#!/usr/bin/env python
"""probe #366-r1 -- MESURE de `SagaOfTheWarriorBorn_OtherSpaceWolves` (1224) sur un ALLIE Space Wolf.

CRITERION BINAIRE : « le port compte-t-il la contribution de 1224 comme le natif ? », mesure dans
un regime ou l'effet MORD -- c.-a-d. ou son absence CHANGE le nombre de coups observe.

L'effet 1224 est une instance de la MEME classe native que 1223
(`IdunBattle.Entities.Effects.Loki.SagaOfTheWarriorBorn_OwnerEffect` : les deux fabriques
`<>c$$<InitializeEffects>b__14_{241,242}` sont bit-identiques, meme slot `Il2CppClass*`). Il se
POSE sur les Space Wolves AMIS (hors Ragnar) quand Ragnar TUE un ennemi ayant le trait `Hero` :

    SagaOfTheWarriorBorn_KillAbility$$CreateTrigger =
        OnDeath(triggerOnOverkill: 1, triggerOnSteppable: 0) & get_OwnerIsActor
        & HasTrait(Target, 0x10 = UnitTrait.Hero)
    SagaOfTheWarriorBorn_KillAbility$$CreateBehaviour =
        AddEffect(0x4c8, AbilityStateReference, source = Owner,
                  targets = UnitsFromFaction(Friends(Owner, <pool>, OnlyAlive) - Owner,
                                             0xd = UnitFaction.SpaceWolves, OnlyAlive))

DEUX BRAS, et c'est leur ECART qui fait la preuve :

  * `KILL`   -- Ragnar execute d'abord un Hero ennemi -> 1224 est pose sur l'allie Space Wolf ;
               l'allie charge ensuite -> `EffectBonus.ForAddition(OwnerIsCaster & IsCharging,
               ConfigVar(0x13 = extraHits))` s'applique.
  * `NOKILL` -- personne ne meurt, 1224 n'existe pas -> TEMOIN : les deux modeles doivent
               coincider sur le nombre de coups NU de l'allie.

L'observable est le NOMBRE DE COUPS (`len(per_hit)`), discret : un ecart ne peut pas etre absorbe
par du bruit d'armure ou de percage.

Le probe REFUSE de mesurer si le regime n'est pas atteint (kill non obtenu, 1224 absent de l'allie,
geometrie de charge non realisable) : un « vert » degrade vaudrait moins que rien.

Usage (depuis scripts/python, session warmee) :
    python probe_366_r1_saga_other_space_wolves.py [--seed 777] [--board MC1_67]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))

#: L'ALLIE qui RECOIT 1224 -- Space Wolf du pool, 3 coups d'arme (base discrete, `extraHits[50]`=3
#: la DOUBLE : 3 -> 6, le rapport le plus large des quatre receveurs possibles).
ALLY = "spaceWulfen"
#: Le POSEUR -- seul porteur de l'ability `SagaOfTheWarriorBorn` (`unit_map find --ability`, 1 unite).
RAGNAR = "spaceBlackmane"
EFFECT_NAME = "SagaOfTheWarriorBorn_OtherSpaceWolves"


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _effect_names(u):
    return [e.get("name") for e in (u.get("effects") or []) if isinstance(e, dict)]


def execute_hero(h, killer_visual, victim_id, max_swings=4):
    """Fait EXECUTER `victim_id` par `killer_visual` (attaque normale, au contact).

    Rend `True` SSI la victime est morte de la main du tueur -- c'est la condition exacte du
    trigger natif (`OnDeath & get_OwnerIsActor`). Aucun repli : un kill non obtenu fait REFUSER
    la mesure en amont, il n'est jamais compense."""
    import hexgeo

    for _ in range(max_swings):
        dv = h.dview()
        killer = h.by_visual(killer_visual, dv)
        victim = next((u for u in h.alive(dv) if u.get("id") == victim_id), None)
        if victim is None:
            return True                       # deja mort
        if killer is None:
            return False
        # ⚠ FIXER `my_player` DEPUIS LE TUEUR, jamais laisser `reach_my_turn` le deviner : son
        # repli est `alive()[0].owner`, c.-a-d. la PREMIERE unite du `decisionView` -- qui est
        # l'ENNEMI sur ce montage (u77 owner=4 avant u81 owner=3). Le harnais bouclait alors sur
        # les tours adverses et le kill n'avait jamais lieu, sans erreur (mesure du 2026-07-31).
        h.my_player = killer.get("owner")
        kp = (killer.get("pos") or {}).get("col"), (killer.get("pos") or {}).get("row")
        vp = (victim.get("pos") or {}).get("col"), (victim.get("pos") or {}).get("row")
        if hexgeo.distance(kp, vp) != 1:
            spots = h.free_tiles(vp, 1, exclude=(killer["id"],))
            if not spots or not h.place(killer["id"], spots[0]):
                return False
        # `force_cycle=True` : le `place` ci-dessus est un `MoveUnitOperation` COMPLET (il consomme
        # l'activation du tueur). Sans cycle force, l'attaque suivante serait refusee EN SILENCE.
        if h.reach_my_turn(force_cycle=True) is None:
            return False
        atk = h.normal_attack_type(killer["id"])
        if atk is None:
            return False
        h.rpc("applyAction", {"runnerId": h.rid, "action": {
            "kind": "ability", "casterId": killer["id"], "targetId": victim_id,
            "abilityType": int(atk)}}, 60)
    return not any(u.get("id") == victim_id for u in h.alive())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--victim", default="necroOverlord", help="Hero ennemi execute par Ragnar")
    ap.add_argument("--survivor", default="necroWarden", help="cible robuste de la charge de l'allie")
    ap.add_argument("--regimes", default="CHARGE,STEP_ADJACENT")
    ap.add_argument("--arms", default="KILL,NOKILL")
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--extra", action="append", default=[],
                    help="arg supplementaire passe a `rl_duel build` (repetable). Sert a mesurer le "
                         "regime DISSOCIE (#382) : le natif indexe `extraHits` sur l'AbilityState "
                         "BAKEE dans l'effet, donc celle de la SOURCE (Ragnar). Les deux niveaux "
                         "coincident sous `buildNormalizedBC` (50 partout) ; les DISSOCIER "
                         "(`--extra --unit-stat --extra spaceBlackmane:PassiveAbilityLevel=1`) est "
                         "le SEUL montage qui les separe. Montage dedie : "
                         "`probe_382_effect_source_ability_state.py`.")
    a = ap.parse_args()

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness

    sid = R._resolve_session()
    w = _unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=180))
    if not (isinstance(w, dict) and w.get("ok")):
        print("[probe] amorce KO : %s" % str(w)[:200])
        return 2

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    rc = 0
    for arm in [x.strip() for x in a.arms.split(",") if x.strip()]:
        rc |= run_arm(a, rpc, arm, Board, ChargeRegimeHarness)
    return rc


def run_arm(a, rpc, arm, Board, ChargeRegimeHarness) -> int:
    fd, state_file = tempfile.mkstemp(prefix="saga1224_%s_" % arm.lower(), suffix=".json")
    os.close(fd)
    Path(state_file).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(a.seed),
            "--state-file", state_file, "--board", a.board,
            "--p-units", "%s,%s" % (RAGNAR, ALLY),
            "--a-units", "%s,%s" % (a.victim, a.survivor),
            "--hp-target", "120000", "--hp-player", "120000", "--no-ai"]
    if arm == "KILL":
        # La VICTIME seule est rendue executable en un echange : `--hp-target` vaut pour tout le
        # camp, donc le per-unit est le SEUL moyen de garder le survivant encaisseur.
        # ⚠ RESERVE AU BRAS KILL. Applique au TEMOIN, ce patch laisse un ennemi a 400 PV que la
        # charge de l'allie TUE au premier coup : le live rend alors n=1 (un seul event, l'overkill
        # cape aux PV restants) et l'ecart se lit a tort comme une divergence de port. Mesure du
        # 2026-07-31 : `NOKILL/CHARGE live n=1 [400]` contre `offline n=3` -- defaut de MONTAGE,
        # pas de moteur.
        argv += ["--unit-stat", "%s:Health=400,RemainingHealth=400" % a.victim]
    argv += list(a.extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(state_file).exists():
        print("[%s] build KO : %s" % (arm, (p.stderr or p.stdout or "")[-500:]))
        Path(state_file).unlink(missing_ok=True)
        return 2
    rid = json.loads(Path(state_file).read_text())["runnerId"]
    print("\n===== BRAS %s -- runner %s (board %s seed %s) =====" % (arm, rid, a.board, a.seed))

    rc = 0
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        dv = h.dview()
        ally = h.by_visual(ALLY, dv)
        ragnar = h.by_visual(RAGNAR, dv)
        victim = h.by_visual(a.victim, dv)
        if ally is None or ragnar is None or victim is None:
            print("[%s] REFUS : roster incomplet (ally=%s ragnar=%s victim=%s)"
                  % (arm, ally is not None, ragnar is not None, victim is not None))
            return 2
        print("[%s] allie u%s effets AVANT = %s" % (arm, ally["id"], _effect_names(ally)))

        if arm == "KILL":
            if not execute_hero(h, RAGNAR, victim["id"]):
                print("[%s] REFUS : Ragnar n'a pas execute %s -- regime NON ATTEINT, "
                      "rien n'est mesure." % (arm, a.victim))
                return 2
            dv = h.dview()
            ally = h.by_visual(ALLY, dv)
            names = _effect_names(ally)
            print("[%s] allie u%s effets APRES kill = %s" % (arm, ally["id"], names))
            if EFFECT_NAME not in names:
                print("[%s] REFUS : %s absent de l'allie apres le kill -- le regime n'est pas "
                      "atteint, on ne mesure PAS en degrade." % (arm, EFFECT_NAME))
                return 2
        else:
            names = _effect_names(ally)
            if EFFECT_NAME in names:
                print("[%s] REFUS : %s deja present SANS kill -- le temoin serait vacu."
                      % (arm, EFFECT_NAME))
                return 2

        for regime in [x.strip() for x in a.regimes.split(",") if x.strip()]:
            # GARDE DE REGIME, re-evaluee AVANT chaque mesure : le bras n'a de valeur que si le
            # PORTEUR est dans l'etat que son nom promet. Un scenario precedent (ou une cascade)
            # a pu poser/retirer 1224 entre-temps.
            here = EFFECT_NAME in _effect_names(h.by_visual(ALLY))
            if here != (arm == "KILL"):
                print("[%s/%s] REFUS : %s present=%s, attendu %s -- regime NON ATTEINT."
                      % (arm, regime, EFFECT_NAME, here, arm == "KILL"))
                rc |= 2
                continue
            rec = h.run(caster_visual=ALLY, regime=regime)
            if rec is None:
                print("[%s/%s] REFUS : geometrie non realisable" % (arm, regime))
                rc |= 2
                continue
            if not rec["live_ok"] or not rec["live_per_hit"]:
                print("[%s/%s] REFUS : attaque live refusee/vide" % (arm, regime))
                rc |= 2
                continue
            # La cible doit SURVIVRE a la salve : un mort tronque le flux d'evenements live
            # (l'overkill est cape aux PV restants) et le `n` mesure alors la mort, pas les coups.
            if not any(u.get("id") == rec["target"] for u in h.alive()):
                print("[%s/%s] REFUS : la cible u%s est MORTE pendant la salve -- `n` live tronque, "
                      "on ne mesure PAS en degrade." % (arm, regime, rec["target"]))
                rc |= 2
                continue
            off = h.replay_offline(rec)
            same_n = len(off["per_hit"]) == len(rec["live_per_hit"])
            same_v = off["per_hit"] == rec["live_per_hit"]
            print("[%s/%s] charged=%s target=%s" % (arm, regime, off["charged"], rec["target"]))
            print("[%s/%s] LIVE    n=%d %s" % (arm, regime, len(rec["live_per_hit"]),
                                               rec["live_per_hit"]))
            print("[%s/%s] OFFLINE n=%d %s" % (arm, regime, len(off["per_hit"]), off["per_hit"]))
            print("[%s/%s] VERDICT hits %s | per_hit %s"
                  % (arm, regime, "OK" if same_n else "DIVERGE",
                     "OK" if same_v else "DIVERGE"))
            if not same_v:
                rc |= 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(state_file).unlink(missing_ok=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
