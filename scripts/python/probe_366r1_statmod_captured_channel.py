"""#366-r1-statmod -- le canal `StatModifierComponent` CAPTE, confronte en regime CROSS-UNITE.

CE QUE CE PROBE MESURE. `IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModificationStat`
retourne litteralement `StatModifierComponent+0x10` et
`IdunBattle.Entities.Effects.StaticStatModifierEffect$$GetStatModificationAmount` litteralement
`+0x14` : c'est la MAGNITUDE QUE LE NATIF RELIT, ecrite UNE FOIS a la pose par
`IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$StatModifierBuilder`. Toute
re-derivation gameconfig cote port est donc une APPROXIMATION -- exacte quand elle sait retrouver
l'`AbilityState` du POSEUR, FAUSSE sinon.

LE DISCRIMINANT, LU AU DECOMPILE (build rnca9r7q6c) :

  * les TROIS surcharges `IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect`
    (targets, effectType, statType, amount, turns, isHidden) construisent
    `IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$.ctor` avec **source = NULL**
    (4e argument) ; les deux `...$$AddStaticStatModifierEffectToOwner` y passent `Owner@DSLSelectors+0x30`
    en source ET en cibles ;
  * `IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$Execute` evalue le selecteur de
    SOURCE (champ `+0x58`) et, quand il est NUL, retombe litteralement sur **l'ENTITE-CIBLE** de
    l'iteration (`lVar9 = <target>; if (sourceSelected != 0) lVar9 = sourceSelected;`).

=> pour toute pose `AddStaticStatModifierEffect(<selecteur != Owner>)`, `EffectComponent.SourceUnit`
designe le **PORTEUR**, jamais le poseur -- donc la cle de `effects_state.baked_ability_state` aussi,
et la re-derivation lit l'`AbilityState` de la MAUVAISE unite.

LE CAS MESURE ICI : `SereneUnifierStormOfFire` (0x493 = 1171), phase `k = 0` du cycle
`Modulo(PlayerTurnsStarted, 3)` de
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SereneUnifierAbility$$CreateBehaviour` :

    AddStaticStatModifierEffect( units, 0x493, statType = 0 ATTACK,
                                 ConfigVar(8 = extraDmg, <AbilityState du PASSIF d'Aun'Shi>),
                                 TurnsFromRounds(1), isHidden = 0 )

avec `units = (AdjacentFriends(Caster,1) + Caster) + UnitsFromFaction(SurroundingFriends(Caster,
ConfigConst(0x16)) - AdjacentFriends, T'au)` -- le porteur PEUT donc etre un ALLIE, et c'est le
regime CROSS-UNITE que `probe_371_serene_unifier_live.py` avait explicitement laisse de cote.

LE BRAS DISCRIMINANT. En regime NOMINAL les deux modeles peuvent coincider (`buildNormalizedBC`
ecrit le MEME `targetAbilityLevel` dans `ActiveAbilityLevel`/`PassiveAbilityLevel` de TOUTES les
unites). On DISSOCIE donc par `--unit-stat "<allie>:PassiveAbilityLevel=<n>"`, applique APRES la
normalisation : le natif continue d'ecrire `extraDmg[niveau d'AUN'SHI] x son multiplier`, la
re-derivation lit `extraDmg[n] x multiplier de l'ALLIE`. Les deux modeles deviennent SEPARABLES.

Usage : `python probe_366r1_statmod_captured_channel.py [--seed 3711] [--board MC1_67]
                                                       [--ally-level 20] [--keep]`.
Consommateur pytest : `tests/engine/runner/test_statmod_captured_channel_live.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
_ROOT = _PYDIR.parent.parent

CARRIER = "tauAunShi"          # seul porteur `lineup` du passif SereneUnifier (1145) au pool
ALLY = "tauCrisis"             # 2e T'au : le selecteur `units` l'arrose -> regime CROSS-UNITE
ENEMIES = ("orksNob", "astraBullgryn")
STORM_OF_FIRE = 1171           # 0x493
SENSE_OF_STONE = 1169          # 0x491 -- phase k=1
ZEPHYRS_GRACE = 1170           # 0x492 -- phase k=2
BOARD = "MC1_67"
SEED = "3711"
ALLY_LEVEL = 20                # bras DISSOCIE : le niveau de passif force sur l'allie
MAX_TURNS = 14                 # le cycle fait 6 tours ; 14 laisse deux passages


def build_args(ally_level: "int | None") -> list:
    """Arguments `rl_duel build`. `--no-ai` : on pilote les fins de tour, aucune action adverse ne
    peut tuer un porteur au milieu de la fenetre. `--unit-stat PassiveAbilityLevel` = le bras
    DISSOCIE (None -> bras NOMINAL, aucun patch)."""
    a = ["--roster", "2",
         "--p-units", "%s,%s" % (CARRIER, ALLY),
         "--a-units", ",".join(ENEMIES),
         "--board", BOARD,
         "--hp-target", "60000", "--hp-player", "60000",
         "--no-ai"]
    if ally_level is not None:
        a += ["--unit-stat", "%s:PassiveAbilityLevel=%d" % (ALLY, int(ally_level))]
    return a


def _build_subprocess(seed: str, extra: list) -> int:
    state = _ROOT / "logs" / ("_probe366r1statmod-%d.json" % os.getpid())
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed,
            "--state-file", str(state), *extra]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build runner KO (rl_duel): " + ((p.stderr or p.stdout or "")[-600:]))
    return json.loads(state.read_text())["runnerId"]


def _unit_entry(dec, uid):
    for u in (dec.get("units") or []):
        if u.get("id") == uid:
            return u
    return None


def _effect_entry(dec, uid, effect_type):
    """L'entree brute de `effect_type` sur `uid` dans un `decisionView` (avec `statMod`)."""
    u = _unit_entry(dec, uid)
    for e in ((u or {}).get("effects") or []):
        if e.get("effectType") == effect_type:
            return e
    return None


def _snap_unit(snap, uid):
    for u in (snap.get("units") or []):
        if u.get("entityId") == uid:
            return u
    return None


def _attack(snap, uid):
    u = _snap_unit(snap, uid)
    return (u.get("stats") or {}).get("attack") if u else None


def _unit_cfg(snap, uid):
    u = _snap_unit(snap, uid)
    return (u.get("unitConfig") or {}) if u else {}


def run(rpc, seed: str = SEED, board: str = BOARD, ally_level: "int | None" = ALLY_LEVEL,
        build_runner=None, keep: bool = False) -> dict:
    """Monte le montage, mesure LIVE + MOTEUR, rend le dict. Libere le runner sauf `keep`."""
    r = _run(rpc, seed, board, ally_level, build_runner)
    if not keep and r.get("rid") is not None:
        try:
            rpc("disposeRunner", {"runnerId": r["rid"]}, 40)
        except Exception:                                # pragma: no cover (nettoyage best-effort)
            pass
    return r


def _run(rpc, seed: str, board: str, ally_level, build_runner) -> dict:
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.pathfinding.board import Board
    from engine.entities.stats import StatType, CAPTURED_SOURCE
    from engine.runner.components import StatsComponent
    from engine.runner.operations.turnflow import EndTurnOperation
    from engine.runner.snapshot import load_state

    extra = list(build_args(ally_level))
    if board != BOARD:
        extra[extra.index("--board") + 1] = board
    if build_runner is not None:
        rid = build_runner(seed, extra=extra)["rid"]
    else:
        rid = _build_subprocess(seed, extra)
    out = {"rid": rid, "seed": seed, "board": board, "ally_level": ally_level,
           "ok": False, "why": None}

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        out["why"] = "boardGraph indispo"
        return out
    brd = Board(bg["tiles"], adjacency="evenq")

    def dec():
        return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)

    def snap():
        return rpc("combatSnapshot", {"runnerId": rid}, 60)

    def endturn():
        return rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    d0 = dec()
    ids = {}
    for u in (d0.get("units") or []):
        if u.get("visualId") in (CARRIER, ALLY):
            ids[u["visualId"]] = u.get("id")
    if CARRIER not in ids or ALLY not in ids:
        out["why"] = "porteur/allie absent du live : %s" % (sorted(ids),)
        return out
    src_uid, ally_uid = ids[CARRIER], ids[ALLY]
    out["src_uid"], out["ally_uid"] = src_uid, ally_uid

    # --- 1. attendre la phase k = 0 du cycle, avec 1171 sur les DEUX unites ----------------------
    phases = []
    d = d0
    for _ in range(MAX_TURNS):
        seen = []
        for et, nm in ((STORM_OF_FIRE, "StormOfFire"), (SENSE_OF_STONE, "SenseOfStone"),
                       (ZEPHYRS_GRACE, "ZephyrsGrace")):
            if _effect_entry(d, src_uid, et) is not None:
                seen.append(nm)
        phases.append("+".join(seen) or "-")
        e_src = _effect_entry(d, src_uid, STORM_OF_FIRE)
        e_ally = _effect_entry(d, ally_uid, STORM_OF_FIRE)
        if e_src is not None and e_ally is not None:
            break
        endturn()
        d = dec()
    out["phases"] = phases
    e_src = _effect_entry(d, src_uid, STORM_OF_FIRE)
    e_ally = _effect_entry(d, ally_uid, STORM_OF_FIRE)
    if e_src is None or e_ally is None:
        out["why"] = ("%d absent (porteur=%s allie=%s) en %d tours -- phases : %s"
                      % (STORM_OF_FIRE, e_src is not None, e_ally is not None, MAX_TURNS, phases))
        return out

    # --- 2. CE QUE LE NATIF A ECRIT -- le composant, champ par champ ------------------------------
    out["statmod_src"] = e_src.get("statMod")
    out["statmod_ally"] = e_ally.get("statMod")
    out["effsource_src"] = e_src.get("source")     # EffectComponent.SourceUnit @+0x10
    out["effsource_ally"] = e_ally.get("source")
    out["remaining_ally"] = e_ally.get("remaining")

    cap_dec, cap_ob, cap_snap = d, rpc("observeBattle", {"runnerId": rid}, 40), snap()
    out["attack_live_on"] = _attack(cap_snap, ally_uid)
    cfg_src, cfg_ally = _unit_cfg(cap_snap, src_uid), _unit_cfg(cap_snap, ally_uid)
    out["cfg_src"] = {k: cfg_src.get(k) for k in
                      ("passiveAbilityLevel", "activeAbilityLevel", "abilityVariablesMultiplier")}
    out["cfg_ally"] = {k: cfg_ally.get(k) for k in
                       ("passiveAbilityLevel", "activeAbilityLevel", "abilityVariablesMultiplier")}

    # La RE-DERIVATION gameconfig, calculee des DEUX cotes -- c'est le modele que le canal remplace.
    def _derived(cfg):
        return ability_var("SereneUnifier", "extraDmg",
                           cfg.get("passiveAbilityLevel") or cfg.get("activeAbilityLevel"),
                           multiplier_pct=int(cfg.get("abilityVariablesMultiplier") or 100))
    out["derived_from_src"] = _derived(cfg_src)
    out["derived_from_ally"] = _derived(cfg_ally)

    # --- 3. LE MOTEUR sur la MEME capture ---------------------------------------------------------
    s = load_state(cap_dec, cap_ob, cap_snap, board=brd)
    eff = next((x for x in s.effects.by_unit.get(ally_uid, [])
                if x.effect_type == STORM_OF_FIRE), None)
    if eff is None:
        out["why"] = "1171 absent du State charge pour l'allie"
        return out
    out["engine_stat"] = eff.get_stat_modification_stat()
    out["engine_amount"] = eff.get_stat_modification_amount()
    out["engine_captured_amount"] = eff.captured_stat_mod_amount()
    ent = s.get_entity(ally_uid)
    c = ent.get_component(StatsComponent) if ent is not None else None
    if c is None or c.ctx is None:
        out["why"] = "StatsComponent absent du State charge (allie)"
        return out
    cx = c.ctx
    ps = dict(cx.stats.components[int(StatType.ATTACK)].modification.per_source)
    out["attributed"] = sum(ps[k] for k in ps
                            if isinstance(k, tuple) and k[:2] == ("statmod", STORM_OF_FIRE))
    out["opaque_residual"] = int(ps.get(CAPTURED_SOURCE, 0))
    out["attack_off_on"] = int(cx.stat(StatType.ATTACK))
    for _ in range(int(out["remaining_ally"] or 1)):
        EndTurnOperation.execute(s, advance=True)
    out["off_still_here"] = any(x.effect_type == STORM_OF_FIRE and not x.consumed
                                for x in s.effects.by_unit.get(ally_uid, []))
    out["attack_off_off"] = int(cx.stat(StatType.ATTACK))

    # --- 4. LE LIVE apres expiration --------------------------------------------------------------
    for _ in range(int(out["remaining_ally"] or 1) + 2):
        endturn()
        if _effect_entry(dec(), ally_uid, STORM_OF_FIRE) is None:
            break
    out["live_still_here"] = _effect_entry(dec(), ally_uid, STORM_OF_FIRE) is not None
    out["attack_live_off"] = _attack(snap(), ally_uid)

    out["ok"] = True
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--ally-level", type=int, default=ALLY_LEVEL,
                    help="niveau de passif force sur l'allie (bras DISSOCIE) ; 0 = bras NOMINAL")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    import rl_collect_batch as R
    sid = R._resolve_session()

    def _unwrap(x):
        return x.get("result") if isinstance(x, dict) and "result" in x else x

    def rpc(method, body=None, timeout=90):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    r = run(rpc, seed=a.seed, board=a.board,
            ally_level=(a.ally_level or None), keep=a.keep)
    print("runner=%s ok=%s why=%s" % (r.get("rid"), r.get("ok"), r.get("why")))
    print("cycle observe : %s" % (" -> ".join(r.get("phases") or []),))
    if not r.get("ok"):
        return 1
    print("PORTEURS  source(Aun'Shi)=u%s  allie(%s)=u%s" % (r["src_uid"], ALLY, r["ally_uid"]))
    print("  EffectComponent.SourceUnit : sur Aun'Shi=%s  sur l'allie=%s"
          % (r["effsource_src"], r["effsource_ally"]))
    print("  StatModifierComponent NATIF : Aun'Shi=%s" % (r["statmod_src"],))
    print("                                allie  =%s" % (r["statmod_ally"],))
    print("  unitConfig  Aun'Shi=%s" % (r["cfg_src"],))
    print("              allie  =%s" % (r["cfg_ally"],))
    print("  re-derivation gameconfig : depuis Aun'Shi=%s  depuis l'ALLIE=%s"
          % (r["derived_from_src"], r["derived_from_ally"]))
    print("  MOTEUR sur l'allie : stat=%s montant=%s (canal capte=%s)"
          % (r["engine_stat"], r["engine_amount"], r["engine_captured_amount"]))
    print("  attribution du seed : montant=%s residu_opaque=%s"
          % (r["attributed"], r["opaque_residual"]))
    print("  ATTACK allie avec l'effet    : live=%s  moteur=%s"
          % (r["attack_live_on"], r["attack_off_on"]))
    print("  ATTACK allie apres expiration: live=%s  moteur=%s (present live=%s moteur=%s)"
          % (r["attack_live_off"], r["attack_off_off"],
             r["live_still_here"], r["off_still_here"]))
    print("  ECART a l'expiration : %s"
          % ((r["attack_off_off"] or 0) - (r["attack_live_off"] or 0),))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
