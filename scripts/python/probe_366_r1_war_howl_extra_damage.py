#!/usr/bin/env python
"""probe #366-r1 -- MESURE de `WarHowl_ExtraDamage_Unstoppable` (1222) sur un ALLIE buffe.

CRITERION BINAIRE : « le port applique-t-il -- ET retire-t-il -- la contribution de 1222 comme le
natif ? », mesure dans un regime ou l'effet MORD (son absence CHANGE le degat per-coup observe).

L'effet est pose par l'ACTIVE `WarHowl` (`ActiveAbilityType` 0x452 = 1106) de `spaceBlackmane`
<<Ragnar>>, sur LUI-MEME et sur tout AMI melee non-Summon
(`IdunBattleLogic.Entities.Abilities.Active.Loki.WarHowlAbility$$ExecuteBehaviour` :
`AddEffect(0x4c6, CreateSnapshot(abilityState), source = Caster,
 targets = Caster + UnitsWithoutTrait(UnitsWithoutRangedWeapons(Friends(Caster, <pool> - Caster,
 OnlyAliveAndTargetable)), 0x2 = Summon, OnlyAliveAndTargetable), turns = Get(1))`).
Aucune faction, aucun rayon. `turns = Get(1)` => l'effet ne vaut QUE le tour du cast (MESURE :
absent des trois porteurs apres un seul `endturn`).

⚠ Le CASTER ne peut pas mesurer sa propre face : le cast consomme son activation. Le porteur
mesure est donc TOUJOURS un ALLIE -- ce qui expose le residu PARTAGE #382 (le port seede
niveau/multiplicateur depuis le PORTEUR, le natif les lit sur l'`AbilityState` de la SOURCE).
D'ou les deux regimes de multiplicateur ci-dessous.

DEUX BRAS x DEUX REGIMES DE CRIT x DEUX REGIMES DE MULTIPLICATEUR :

  bras    WARHOWL  -- Ragnar caste 1106 ; l'allie attaque DANS LE MEME TOUR (l'effet est la).
          WITNESS  -- aucun cast ; TEMOIN : les deux modeles doivent coincider sur le degat NU.

  crit    NOCRIT   -- `--crit 0,700` : `GetStat(9) == 0`. Le gate natif
                      `AmountIsGreaterThanZero(StatAmount(Caster, CriticalChance, Current))` est
                      FERME -> aucun bonus de chance de crit, donc `CouldCrit` reste FAUX et le
                      natif ne TIRE MEME PAS. Un port sans ce gate rendrait cc = 0 + 36 = 36 ->
                      `roll_critical` consommerait un tirage par coup -> le flux PRNG DECALE et
                      TOUS les coups divergent. Bras le plus discriminant des deux faces a la fois.
          CRIT     -- `--crit 40,700` : gate OUVERT, cc natif = 40 + extraCritChance[50] = 76. Un
                      port sans la face CRIT roulerait a 40 -> memes tirages, crits DIFFERENTS.

  mult    ALIGNED  -- `--unit-stat spaceBlackmane:AbilityVariablesMultiplierPercentage=180` : la
                      SOURCE et le PORTEUR ont le meme multiplicateur, donc #382 est NEUTRALISE et
                      l'accord mesure CE port, et rien d'autre. C'est le regime de reference.
          SRCMULT  -- sans patch (Ragnar 200, allie 180, MESURE) : le natif applique
                      `extraDmg[50] x 200% = 1772`, le port `round(886 x 1.80) = 1595`. L'ecart
                      attendu est donc de 177 par coup, ET C'EST LE RESIDU #382, pas ce port.
                      `--expect-diverge` fait de cette divergence le SUCCES du bras.

Le probe REFUSE de mesurer si le regime n'est pas atteint (cast refuse, 1222 absent/present a
contretemps, crit du caster hors regime, cible morte en cours de salve) : un « vert » degrade
vaudrait moins que rien.

Usage (depuis scripts/python, session warmee) :
    python probe_366_r1_war_howl_extra_damage.py [--seed 777] [--board MC1_67]
    python probe_366_r1_war_howl_extra_damage.py --mult SRCMULT --expect-diverge

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

#: Le POSEUR -- seul porteur de l'active `WarHowl` (`unit_map find --ability WarHowl` : 1 unite).
RAGNAR = "spaceBlackmane"
#: Le PORTEUR MESURE par DEFAUT -- ami MELEE non-Summon, donc dans le selecteur de
#: `ExecuteBehaviour`. (MESURE live : `spaceWulfen` et `spaceHound` recoivent 1222 ;
#: `spaceRockfist` et `spaceStormcaller` NON -- ils portent une arme a distance.)
ALLY = "spaceWulfen"
EFFECT_NAME = "WarHowl_ExtraDamage_Unstoppable"
WAR_HOWL = 1106                      # ActiveAbilityType 0x452
#: Multiplicateur COMMUN impose aux deux camps du bras ALIGNED (valeur mesuree de `spaceWulfen` /
#: `spaceHound` sur le BC normalise ; `spaceBlackmane` y vaut 200, d'ou le besoin d'aligner).
ALIGNED_MULT = 180


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _effect_names(u):
    return [e.get("name") for e in (u.get("effects") or []) if isinstance(e, dict)]


def _hits_of(res, caster, target):
    """Degats per-coup lus dans les events du cast live (tag `Amount`, paire attaquant/cible)."""
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    out = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if ("Amount" in td and td.get("Attacker_Id") == caster
                and td.get("Target_Id") == target):
            out.append(int(td["Amount"]))
    return bool(a0.get("ok")), out


def build(a, arm, crit, mult):
    """Un runner par (bras, crit, mult). Rend `(runnerId, state_file)` ou `(None, state_file)`."""
    fd, sf = tempfile.mkstemp(prefix="wh1222_%s_%s_%s_" % (arm.lower(), crit.lower(), mult.lower()),
                              suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(a.seed),
            "--state-file", sf, "--board", a.board,
            "--p-units", "%s,%s" % (RAGNAR, a.ally),
            "--a-units", "%s,%s" % (a.target_unit, a.other_unit),
            "--hp-target", "400000", "--hp-player", "400000", "--no-ai",
            "--crit", ("0,700" if crit == "NOCRIT" else "40,700")]
    if mult == "ALIGNED":
        # NEUTRALISE #382 : SOURCE et PORTEUR prennent le MEME multiplicateur, donc les deux
        # lectures coincident et l'accord mesure CE port seul. On force les DEUX (et pas seulement
        # la source) pour que le bras reste valable quel que soit l'allie choisi ; la garde
        # d'execution `mult_src != mult_carrier` REFUSE si le patch n'a pas pris.
        for vis in (RAGNAR, a.ally):
            argv += ["--unit-stat",
                     "%s:AbilityVariablesMultiplierPercentage=%d" % (vis, ALIGNED_MULT)]
    argv += list(a.extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("[%s/%s/%s] build KO : %s" % (arm, crit, mult, (p.stderr or p.stdout or "")[-500:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


def stage(h, ally_visual, do_cast, ragnar_visual=RAGNAR):
    """FOYER UNIQUE du montage (importe par le cliquet, jamais re-transcrit).

    Pose la geometrie NO_STEP, prend un tour NEUF, (option) fait CASTER `WarHowl` a Ragnar, puis
    SNAPSHOTe l'etat EXACT que l'offline devra rejouer. Rend `(rec, reason)` : `reason is None`
    = regime atteint, sinon la raison EXACTE du refus (l'appelant decide s'il imprime ou echoue).

    NO_STEP : l'allie est pose AU CONTACT et ne bougera pas. Le rejeu offline est donc une ATTAQUE
    PURE (aucun `MoveUnitMessage` a rejouer) et `IsCharging` reste FAUX -- ce qui TAIT les effets de
    charge du roster (`SagaOfTheWarriorBorn_Owner` sur Ragnar) et laisse 1222 seul en scene.

    ORDRE NON NEGOCIABLE : le cast vient APRES `reach_my_turn(force_cycle=True)` et AVANT le
    snapshot. Avant le cycle, l'effet serait purge par le `endturn` (`turns = Get(1)`, MESURE :
    absent apres un seul `endturn`) ; apres le snapshot, l'offline partirait d'un etat sans lui."""
    plan = h.arrange(caster_visual=ally_visual, regime="NO_STEP")
    if plan is None:
        return None, "geometrie NO_STEP non realisable"
    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint"
    dv = h.dview()
    ragnar = h.by_visual(ragnar_visual, dv)
    ally = h.by_visual(ally_visual, dv)
    if ragnar is None or ally is None:
        return None, ("roster incomplet (ragnar=%s ally=%s)"
                      % (ragnar is not None, ally is not None))
    if do_cast:
        res = h.rpc("applyAction", {"runnerId": h.rid, "action": {
            "kind": "ability", "casterId": ragnar["id"], "targetId": ragnar["id"],
            "abilityType": WAR_HOWL}}, 60)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        if not (res.get("ok") and a0.get("ok")):
            return None, "cast WarHowl refuse (%s)" % str(res)[:200]
    names = _effect_names(h.by_visual(ally_visual))
    here = EFFECT_NAME in names
    if here != bool(do_cast):
        return None, ("%s present=%s, attendu %s -- regime NON ATTEINT (effets=%s)"
                      % (EFFECT_NAME, here, bool(do_cast), names))
    snap = h.snapshot()
    rec = {"caster": plan["caster"], "target": plan["target"], "step_to": None,
           "snapshot": snap, "rng_after_step": snap["rng"], "source": ragnar["id"],
           "carries": here}
    # Etat OFFLINE de reference : sert aux GARDES DE REGIME (crit du caster, alignement des
    # multiplicateurs) AVANT toute mesure -- un bras ne prouve ce qu'il promet que si l'etat est
    # bien celui que son nom decrit.
    from engine.entities.stats import StatType
    from engine.runner.components import StatsComponent
    st0 = h.offline_state(rec)
    sc = st0.get_entity(rec["caster"]).get_component(StatsComponent)
    src = st0.get_entity(rec["source"]).get_component(StatsComponent)
    rec["crit_chance"] = int(sc.ctx.stat(StatType.CRIT_CHANCE) or 0)
    rec["mult_carrier"] = int(getattr(sc.ctx, "ability_variables_multiplier", 100) or 100)
    rec["mult_source"] = int(getattr(src.ctx, "ability_variables_multiplier", 100) or 100)
    return rec, None


def strike(h, rec):
    """Joue l'ATTAQUE NORMALE live et rend `(live_hits, reason)`."""
    atk = h.normal_attack_type(rec["caster"])
    if atk is None:
        return None, "pas d'attaque normale sur u%s" % rec["caster"]
    live = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": rec["caster"], "targetId": rec["target"],
        "abilityType": int(atk)}}, 60)
    ok, hits = _hits_of(live, rec["caster"], rec["target"])
    if not ok or not hits:
        return None, "attaque live refusee/vide"
    # Une cible MORTE tronque le flux d'evenements (l'overkill est cape aux PV restants) : les
    # valeurs mesureraient la mort, pas les coups.
    if not any(u.get("id") == rec["target"] for u in h.alive()):
        return None, "la cible u%s est MORTE pendant la salve -- flux live tronque" % rec["target"]
    return hits, None


def run_case(a, rpc, Board, ChargeRegimeHarness, arm, crit, mult) -> int:
    rid, sf = build(a, arm, crit, mult)
    if rid is None:
        Path(sf).unlink(missing_ok=True)
        return 2
    tag = "%s/%s/%s" % (arm, crit, mult)
    print("\n===== %s -- runner %s (board %s seed %s) =====" % (tag, rid, a.board, a.seed))
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        rec, why = stage(h, a.ally, arm == "WARHOWL")
        if rec is None:
            print("[%s] REFUS : %s" % (tag, why))
            return 2
        print("[%s] attaquant u%s cc=%d mult_porteur=%d | source u%s mult_source=%d"
              % (tag, rec["caster"], rec["crit_chance"], rec["mult_carrier"],
                 rec["source"], rec["mult_source"]))
        if (rec["crit_chance"] > 0) != (crit == "CRIT"):
            print("[%s] REFUS : CritChance=%d hors regime %s -- rien n'est mesure"
                  % (tag, rec["crit_chance"], crit))
            return 2
        if mult == "ALIGNED" and rec["mult_source"] != rec["mult_carrier"]:
            print("[%s] REFUS : multiplicateurs NON alignes (%d vs %d) -- le bras de reference "
                  "mesurerait #382 au lieu de ce port"
                  % (tag, rec["mult_source"], rec["mult_carrier"]))
            return 2
        live_hits, why = strike(h, rec)
        if live_hits is None:
            print("[%s] REFUS : %s" % (tag, why))
            return 2

        off = h.replay_offline(rec)
        same = off["per_hit"] == live_hits
        print("[%s] LIVE    n=%d %s" % (tag, len(live_hits), live_hits))
        print("[%s] OFFLINE n=%d %s" % (tag, len(off["per_hit"]), off["per_hit"]))
        if len(off["per_hit"]) == len(live_hits):
            print("[%s] DELTA   %s" % (tag, [l - o for l, o in zip(live_hits, off["per_hit"])]))
        expect_div = bool(a.expect_diverge) and arm == "WARHOWL"
        verdict = "OK" if same else "DIVERGE"
        print("[%s] VERDICT per_hit %s (attendu : %s)"
              % (tag, verdict, "DIVERGE" if expect_div else "OK"))
        return 0 if (same != expect_div) else 1
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--ally", default=ALLY,
                    help="le PORTEUR mesure (ami MELEE non-Summon : spaceWulfen, spaceHound, ...)")
    ap.add_argument("--target-unit", default="necroWarden", help="cible robuste de l'allie buffe")
    ap.add_argument("--other-unit", default="necroOverlord", help="2e ennemi, ecarte par le montage")
    ap.add_argument("--arms", default="WARHOWL,WITNESS")
    ap.add_argument("--crits", default="NOCRIT,CRIT")
    ap.add_argument("--mult", default="ALIGNED", choices=("ALIGNED", "SRCMULT"))
    ap.add_argument("--expect-diverge", action="store_true",
                    help="le bras WARHOWL doit DIVERGER (regime SRCMULT : mesure du residu #382)")
    ap.add_argument("--extra", action="append", default=[],
                    help="arg supplementaire passe a `rl_duel build` (repetable)")
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
    for crit in [x.strip() for x in a.crits.split(",") if x.strip()]:
        for arm in [x.strip() for x in a.arms.split(",") if x.strip()]:
            rc |= run_case(a, rpc, Board, ChargeRegimeHarness, arm, crit, a.mult)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
