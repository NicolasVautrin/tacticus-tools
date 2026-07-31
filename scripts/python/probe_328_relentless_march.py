#!/usr/bin/env python
"""Probe #328 -- `RelentlessMarchAbility` (passif `RelentlessMarch`, `TriggeredAbilityType` 0x3ec =
1004, de `necroWarden` << Makhotep >>). Confrontation LIVE-vs-PORT des DEUX feuilles du behaviour au
debut du tour du porteur.

MECANIQUE PORTEE (RE : `docs/rl/case-328-relentless-march.md` et l'en-tete de
`engine/runner/operations/triggers/loki/relentless_march.py`) :

    On(TurnStart_Other = 0x13) & <DSLTriggers+0x28 = IsTurnOf(Owner)>
      -> AddEffect(0x3f3 RelentlessMarch_Effect, turns = Nullable<int>(1))
             sur UnitsWithoutTrait( Friends(AdjacentUnits(Owner)), 0x418 Stationary )
       + Repair(Owner, Friends(AdjacentUnits(Owner)), Direct(hpToRepair[lvl]), ForRepair)

⚠ LE POINT DU CAS : le filtre `UnitsWithoutTrait(Stationary)` porte sur la cible de l'`AddEffect`
SEULE -- le `Repair` recoit l'arbre NON filtre (la fiche #317 disait l'inverse).

MONTAGE (positions DRIVEES ; aucune dependance aux spawns) -- SIX cas discriminants sur un plateau :
  * `admecRuststalker` (allie MECHANICAL non-LivingMetal, ENDOMMAGE)  dist 1 -> effet 1011 + REPAIR
  * `astraBullgryn`    (allie ORGANIQUE, ENDOMMAGE)                   dist 1 -> effet 1011, RIEN en PV
                                        (gate `UnitExtensions$$IsAffectedByHealType(target, 1)`)
  * `admecDominus`     (allie MECHANICAL a PV PLEINS)                 dist 1 -> effet 1011, RIEN en PV
                                        (gate `IsDamagedUnit` d'`AttackQuery$$EntityCanBeRepaired`)
  * `admecManipulus`   (allie MECHANICAL, ENDOMMAGE)                  dist 2 -> RIEN (gate d'adjacence)
  * `blackTerminator`  (ENNEMI)                                       dist 1 -> RIEN (gate `Friends`)
  * `necroWarden`      (le PORTEUR lui-meme)                          dist 0 -> RIEN de CE passif
                                        (`AdjacentUnits` = `Units(AdjacentTiles(o)) - o`)

Les cibles MECHANICAL sont choisies **non-`LivingMetal`** (Adeptus Mechanicus) EXPRES : le porteur et
tout Necron portent `LivingMetal`, dont le trigger part sur le MEME `On(TurnStart_Other)` -- le delta
de PV mesure ainsi le seul `RelentlessMarch`.

⚠ Le volet `UnitsWithoutTrait(0x418 = Stationary)` n'est PAS exerce par CE montage : aucune unite du
gameconfig ne porte `Stationary` en statique (mesure : `unit_map.py find --trait Stationary` = 0), le
trait n'est pose EN BATAILLE que par `AddTrait(ActiveTarget, 0x418)` des abilities de transformation
de Machine of War (`DutyEternalAbility`, `AetherStrideAbility`). Volet SEPARE : `--stationary` monte
le montage MoW (`ultraDreadnought` + cast `DutyEternal` -> `ultraSmnDreadnought`, `Stationary` +
`Mechanical`) et verifie que le summon ne recoit PAS 1011 la ou son voisin non-Stationary le recoit.

PROTOCOLE par tour de P (identique a `probe_224_cursed_plague_bell`) :
  1. au tour ADVERSE : capture S (`decisionView allAbilities` + `observeBattle` + `combatSnapshot`) ;
  2. LIVE : `endturn` (A -> P) => `StartTurnOperation` natif => `On(0x13)` => pose + reparation ;
     relecture `decisionView` -> porteurs de 1011 (+ `remaining`) et PV par unite ;
  3. PORT : `load_state(S)` + `_bump_turns_started(P)` (mirror de l'incrementation que
     `StartTurnOperation` fait AVANT d'emettre les 5 events) + `turn_start_other_triggers(P)` ;
  4. comparaison d'ENSEMBLES, de `remaining` et de PV.

`applyAction` ne fait PAS jouer l'IA : entre la capture et la relecture, SEULS les triggers turn-start
de P agissent -- aucun bruit adverse.

CONTREFACTUELS (`--mutate`), rejoues sur les MEMES captures :
  `friends`      : gate de camp retire (`AdjacentUnits` nu au lieu de `Friends(...)`) ;
  `adjacent`     : rayon 2 au lieu de 1 ;
  `repairfilter` : LA FAUTE DE LA FICHE #317 -- le `Repair` recoit la cible FILTREE par
                   `UnitsWithoutTrait(Stationary)` ;
  `stationary`   : filtre de trait retire de l'`AddEffect` ;
  `nostationary` : filtre applique a l'`AddEffect` ET au `Repair` (l'autre demi-faute).
Un gate qui reste inerte signale un montage AVEUGLE, pas un port juste.

ASCII only (cp1252). Usage :
    python probe_328_relentless_march.py [--seed 777] [--board C1_75] [--turns 3] [--mutate]
    python probe_328_relentless_march.py --stationary [--board <board a slot MoW>]
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
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402
from engine.runner.components import HealthComponent                       # noqa: E402
from engine.runner.operations.triggers import turn_start_other_triggers    # noqa: E402
from engine.runner.operations.turnflow import _bump_turns_started          # noqa: E402

ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_328_relentless_march.json"
STATE_ST = ROOT / "logs" / "runners" / "_328_relentless_march_stationary.json"

CARRIER = "necroWarden"             # Makhotep : passif RelentlessMarch (+ trait LivingMetal)
FRIEND_MECH = "admecRuststalker"    # allie Mechanical NON-LivingMetal, ENDOMMAGE, dist 1
FRIEND_ORGANIC = "astraBullgryn"    # allie NON-mechanical, ENDOMMAGE, dist 1 (gate heal-type)
FRIEND_FULLHP = "admecDominus"      # allie Mechanical a PV PLEINS, dist 1 (gate IsDamagedUnit)
FRIEND_FAR = "admecManipulus"       # allie Mechanical ENDOMMAGE, dist 2 (gate d'adjacence)
ENEMY = "blackTerminator"           # ENNEMI, dist 1 (gate Friends)

MARCH_EFFECT = int(EffectType.RelentlessMarch_Effect)       # 0x3f3 = 1011
MARCH_EFFECT_NAME = "RelentlessMarch_Effect"

P_UNITS = [CARRIER, FRIEND_MECH, FRIEND_ORGANIC, FRIEND_FULLHP, FRIEND_FAR]
A_UNITS = [ENEMY]
NEAR = [FRIEND_MECH, FRIEND_ORGANIC, FRIEND_FULLHP, ENEMY]      # ring-1 du porteur
FAR_PLACEMENT = {FRIEND_FAR: 2}
DAMAGED = [FRIEND_MECH, FRIEND_ORGANIC, FRIEND_FAR]             # PAS `FRIEND_FULLHP` : c'est le gate
DAMAGED_HP = 500

# --- volet STATIONARY (montage separe) ----------------------------------------------------------
# `tauShadowsun` (HERO, DANS LE POOL) : son active `ExemplarOfTheKauyon` (1130) se termine par
#     Spawn( <tuile quittee par Shadowsun>, "tauSmnDroneCommandLink",
#            options.onAppear = AddTrait(<selectors+0x68>, 0x418 = UnitTrait.Stationary) )
# (`...ExemplarOfTheKauyonAbility$$ExecuteBehaviour`, l'`AddTrait` etant range dans
# `SpawnUnitOptions+0x18` = le behaviour ON-APPEARANCE du spawn). Le drone porte
# `Summon`/`Flying`/**`Mechanical`** au gameconfig -> il est REPARABLE, et `Stationary` l'exclut de
# l'`AddEffect` : c'est le discriminant COMPLET du cas.
# Shadowsun se TELEPORTE sur la tuile ciblee et le drone prend SA place -> il suffit de la placer
# adjacente au porteur et de caster LOIN pour que le drone naisse adjacent au porteur.
SHADOWSUN = "tauShadowsun"
SUMMON = "tauSmnDroneCommandLink"
EXEMPLAR_OF_THE_KAUYON = 1087       # `ActiveAbilityType.ExemplarOfTheKauyon` (enum_maps.py)
ST_P_UNITS = [CARRIER, SHADOWSUN, FRIEND_MECH]
ST_A_UNITS = [ENEMY]


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def build(seed, board, p_units, a_units, state_file, p_mow=None):
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board,
           "--p-units", ",".join(p_units), "--a-units", ",".join(a_units)]
    for vis in DAMAGED:
        if vis in p_units:
            # PV BAS sans toucher `Health` -> l'unite est ENDOMMAGEE au deploiement, donc le gate
            # `IsDamagedUnit` d'`EntityCanBeRepaired` passe. (`--hp-player` forcerait `Health` ET
            # `RemainingHealth` : l'unite serait a PV PLEINS, et le Repair un no-op.)
            cmd += ["--unit-stat", "%s:RemainingHealth=%d" % (vis, DAMAGED_HP)]
    if p_mow:
        cmd += ["--p-mow", p_mow]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[328] build KO:", (proc.stderr or proc.stdout or "")[-800:], file=sys.stderr)
        return None
    return json.loads(state_file.read_text())["runnerId"]


def dispose(sid, rid):
    try:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    except Exception as exc:                                   # pragma: no cover (nettoyage)
        print("[328] dispose KO:", exc, file=sys.stderr)


def dv(sid, rid, all_ab=False, mr=1):
    b = {"runnerId": rid, "maxRank": mr}
    if all_ab:
        b["allAbilities"] = True
    return _r(sid, "decisionView", b, 150 if all_ab else 60)


def carriers_live(view) -> dict:
    """{id d'unite: `remaining`} des porteurs ACTIFS de 1011 dans `decisionView`. Le `remaining` est
    le DISCRIMINANT du `turns = Nullable<int>(1)` natif (un `TurnsFromRounds` rendrait autre chose)."""
    out = {}
    for u in (view.get("units") or []):
        for e in (u.get("effects") or []):
            if e.get("active") is False:
                continue
            if int(e.get("effectType") or -1) == MARCH_EFFECT or e.get("name") == MARCH_EFFECT_NAME:
                out[int(u["id"])] = e.get("remaining")
    return out


def carriers_offline(state) -> dict:
    """{id: `remaining`} des instances ACTIVES de 1011 dans `State.effects` (cote PORT)."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return {}
    return {int(uid): e.remaining_turns
            for uid, lst in eff.by_unit.items()
            for e in lst if (not e.consumed) and int(e.effect_type) == MARCH_EFFECT}


def hp_live(view) -> dict:
    """{id d'unite: PV courants} depuis `decisionView` (unites VIVANTES)."""
    return {int(u["id"]): int(u.get("hp") or 0) for u in (view.get("units") or []) if u.get("alive")}


def hp_offline(state) -> dict:
    """{id: PV courants} cote PORT."""
    out = {}
    for eid, e in state.entities.items():
        hc = e.get_component(HealthComponent)
        if hc is not None and hc.hp is not None:
            out[int(eid)] = int(hc.hp)
    return out


def move(sid, rid, uid, col, row):
    _r(sid, "applyAction",
       {"runnerId": rid, "actions": [{"kind": "move", "unitId": uid, "to": {"col": col, "row": row}}]}, 60)


def endturn(sid, rid):
    _r(sid, "applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 90)


def _hub_tile(bg):
    """Une tuile jouable a SIX voisins jouables : un spawn en coin SOUS-EXERCERAIT le voisinage
    (runner.md : « si ta mecanique compte des voisins, exige explicitement une tuile a 6 voisins »)."""
    by_id = {t["id"]: t for t in bg["tiles"]}
    cands = []
    for t in bg["tiles"]:
        if not t.get("walkable") or t.get("isWall"):
            continue
        good = [n for n in (t.get("neighbours") or [])
                if n in by_id and by_id[n].get("walkable") and not by_id[n].get("isWall")]
        if len(good) >= 6:
            cands.append(t)
    return cands[len(cands) // 2] if cands else None


def setup_positions(sid, rid, ids, near=NEAR, far=FAR_PLACEMENT):
    """DRIVE les positions : le porteur sur une tuile a 6 voisins, `near` sur son ring-1, `far` aux
    distances hex voulues. `applyAction move` teleporte -> la geometrie est CHOISIE, pas subie."""
    import hexgeo
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    hub = _hub_tile(bg)
    if hub is None:
        return None
    move(sid, rid, ids[CARRIER], hub["col"], hub["row"])
    for vis in near:
        if vis not in ids:
            continue
        # relecture ENTRE CHAQUE move : `applyAction move` refuse une tuile OCCUPEE, et l'echec est
        # SILENCIEUX -> on choisit la 1re tuile REELLEMENT libre a chaque fois, et le controle de
        # distance en sortie refuse un montage degrade.
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        by_id = {t["id"]: t for t in bg["tiles"]}
        ctile = next((t for t in bg["tiles"] if t.get("occupantUnitId") == ids[CARRIER]), None)
        if ctile is None:
            return None
        free = [by_id[n] for n in (ctile.get("neighbours") or [])
                if n in by_id and by_id[n].get("walkable") and not by_id[n].get("isWall")
                and by_id[n].get("occupantUnitId") in (None, ids[vis])]
        if not free:
            return None
        move(sid, rid, ids[vis], free[0]["col"], free[0]["row"])
    for vis, want in far.items():
        if vis not in ids:
            continue
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        ctile = next((t for t in bg["tiles"] if t.get("occupantUnitId") == ids[CARRIER]), None)
        occupied = {t["id"] for t in bg["tiles"] if t.get("occupantUnitId") is not None}
        cpos = (ctile["col"], ctile["row"])
        tgt = next((t for t in bg["tiles"]
                    if t.get("walkable") and not t.get("isWall") and t["id"] not in occupied
                    and hexgeo.distance((t["col"], t["row"]), cpos) == want), None)
        if tgt is None:
            return None
        move(sid, rid, ids[vis], tgt["col"], tgt["row"])
    return _r(sid, "boardGraph", {"runnerId": rid}, 90)


# --- CONTREFACTUELS -----------------------------------------------------------------------------
def _patched_tree(mutate):
    """Rend un remplacant de `relentless_march_behaviour_tree` avec UN gate neutralise/deplace.

    `repairfilter` = LA FAUTE DE LA FICHE #317 : le `Repair` recoit la cible FILTREE par
    `UnitsWithoutTrait(Stationary)` au lieu de l'arbre nu."""
    import engine.runner.operations.triggers.loki.relentless_march as M
    from engine.dsl.base import Const
    from engine.entities.behaviours import Seq
    from engine.entities.selectors import (AdjacentUnits, Caster, Friends, UnitsWithoutTrait)
    from engine.runner.abilities.behaviours import AddEffect, Repair

    def patched(amount, trigger_type=None):
        owner = Caster()
        radius = Const(2) if mutate == "adjacent" else Const(1)
        adj = AdjacentUnits(owner, radius)
        base = adj if mutate == "friends" else Friends(adj, owner)
        filtered = base if mutate == "stationary" else UnitsWithoutTrait(base, M.STATIONARY)
        rep_sel = filtered if mutate in ("repairfilter", "nostationary") else base
        return Seq(AddEffect(M.MARCH_EFFECT, M.MARCH_EFFECT_NAME, filtered,
                             duration_rounds=None, duration_turns=M.MARCH_EFFECT_TURNS),
                   Repair(rep_sel, amount, scope=M.REPAIR_SCOPE,
                          remove_effects=M.REPAIR_REMOVE_EFFECTS))
    return patched


def offline_fire(cap, player, mutate=None):
    """Rejoue le turn-start de `player` cote PORT depuis la capture `cap`.

    `_bump_turns_started` AVANT le vecteur = mirror de l'ORDRE natif (`StartTurnOperation$$Execute`
    incremente `turnsStarted` puis emet la sequence 0x12..0x16)."""
    state = load_state(cap["dec"], cap["ob"], cap["snap"], board=cap["board"])
    _bump_turns_started(state, player)
    import engine.runner.operations.triggers.loki.relentless_march as M
    saved = M.relentless_march_behaviour_tree
    if mutate is not None:
        M.relentless_march_behaviour_tree = _patched_tree(mutate)
    try:
        turn_start_other_triggers(state, player)
    finally:
        M.relentless_march_behaviour_tree = saved
    return state


def measure(sid, seed, board_id, turns, verbose=True, keep=False):
    """Monte le montage, joue `turns` tours de P et rend la mesure BRUTE (aucune assertion).

    `None` si le montage n'a pas pu etre etabli -- JAMAIS un resultat degrade : un move refuse ferait
    disparaitre le cas discriminant que l'unite portait, et le vert ne prouverait plus rien."""
    import hexgeo
    rid = build(seed, board_id, P_UNITS, A_UNITS, STATE)
    if rid is None:
        return None
    if verbose:
        print("[328] runner=%s seed=%s board=%s" % (rid, seed, board_id))
    try:
        view = dv(sid, rid)
        ids, teams = {}, {}
        for u in (view.get("units") or []):
            if u.get("alive"):
                ids[u.get("visualId")] = int(u["id"])
                teams[int(u["id"])] = u.get("team")
        missing = [v for v in (P_UNITS + A_UNITS) if v not in ids]
        if missing:
            print("[328] ABORT unites absentes du build: %s" % missing)
            return None
        vis_by_id = {v: k for k, v in ids.items()}
        p_team = view.get("currentPlayer")
        if setup_positions(sid, rid, ids) is None:
            print("[328] ABORT placement impossible (pas assez de tuiles libres)")
            return None
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="evenq")
        pos = {t.get("occupantUnitId"): (t["col"], t["row"])
               for t in bg["tiles"] if t.get("occupantUnitId") is not None}
        cpos = pos[ids[CARRIER]]
        want = {v: 1 for v in NEAR}
        want.update(FAR_PLACEMENT)
        degraded = []
        for vis in P_UNITS + A_UNITS:
            if vis == CARRIER:
                continue
            d = hexgeo.distance(pos[ids[vis]], cpos)
            if verbose:
                print("  place %-20s pos=%s dist=%d (voulu %d) team=%s"
                      % (vis, pos[ids[vis]], d, want[vis], teams[ids[vis]]))
            if d != want[vis]:
                degraded.append((vis, d, want[vis]))
        if degraded:
            print("[328] ABORT montage degrade (distances non atteintes): %s" % degraded)
            return None

        rows = []
        for k in range(turns):
            if dv(sid, rid).get("currentPlayer") == p_team:      # se placer au tour ADVERSE
                endturn(sid, rid)
            cap = {"dec": dv(sid, rid, all_ab=True),
                   "ob": _r(sid, "observeBattle", {"runnerId": rid}, 60),
                   "snap": _r(sid, "combatSnapshot", {"runnerId": rid}, 120), "board": board}
            hp_before = hp_live(cap["dec"])
            endturn(sid, rid)                                    # A -> P : turn-start natif
            after_view = dv(sid, rid, all_ab=True)
            live, hp_after = carriers_live(after_view), hp_live(after_view)
            st = offline_fire(cap, p_team)
            off, hp_off = carriers_offline(st), hp_offline(st)
            d_live = {i: hp_after.get(i, 0) - hp_before.get(i, 0) for i in hp_before}
            d_port = {i: hp_off.get(i, 0) - hp_before.get(i, 0) for i in hp_before}
            ok_eff = set(live) == set(off) and all(live.get(i) == off.get(i) for i in live)
            ok_hp = all(d_live.get(i) == d_port.get(i) for i in hp_before)
            if verbose:
                print("[328] tour P #%d  1011 live=%s port=%s  duree live=%s port=%s  %s"
                      % (k + 1, sorted(vis_by_id[i] for i in live),
                         sorted(vis_by_id[i] for i in off),
                         sorted(set(live.values())), sorted(set(off.values())),
                         "OK" if ok_eff else "DESACCORD-EFFET"))
                for i in sorted(d_live):
                    if d_live[i] or d_port[i]:
                        print("        dPV %-20s live=%+d port=%+d %s"
                              % (vis_by_id.get(i, i), d_live[i], d_port[i],
                                 "" if d_live[i] == d_port[i] else "<-- DESACCORD"))
                if not ok_hp:
                    print("        DESACCORD-PV")
            rows.append({"k": k + 1, "live": live, "port": off, "d_live": d_live,
                         "d_port": d_port, "hp_before": hp_before, "cap": cap,
                         "ok": bool(ok_eff and ok_hp), "ok_eff": ok_eff, "ok_hp": ok_hp})
        return {"rows": rows, "p_team": p_team, "ids": ids, "vis_by_id": vis_by_id, "rid": rid}
    finally:
        if not keep:
            dispose(sid, rid)


# ================================================================================================
# VOLET STATIONARY -- le seul chemin du build vers un allie porteur de `UnitTrait.Stationary`
# ================================================================================================
def measure_stationary(sid, seed, board_id, turns=2, verbose=True, keep=False):
    """Monte `necroWarden` + `tauShadowsun` + `admecRuststalker`, place Shadowsun ADJACENTE au
    porteur, caste `ExemplarOfTheKauyon` (1087) sur une tuile LOINTAINE : Shadowsun se teleporte et
    le drone `tauSmnDroneCommandLink` naît SUR SA TUILE -- donc adjacent au porteur -- avec
    `AddTrait(0x418 = UnitTrait.Stationary)` pose ON-APPEARANCE
    (`...ExemplarOfTheKauyonAbility$$ExecuteBehaviour`, `SpawnUnitOptions+0x18`).

    C'est le SEUL chemin BON MARCHE du build vers un allie porteur de `Stationary` : aucune unite du
    gameconfig ne le porte en statique (`unit_map.py find --trait Stationary` = 0 unite), le trait
    n'est pose qu'on-appearance par les abilities de spawn `ExemplarOfTheKauyon` / `DutyEternal` /
    `AetherStride` (les deux dernieres exigent une Machine of War et de la MUNITION).

    Le drone est `Mechanical` (donc REPARABLE) et `Stationary` (donc exclu de l'`AddEffect`) : c'est
    le discriminant COMPLET du cas -- reparation SANS effet 1011.

    Rend `None` si le montage n'est pas montable (cast refuse, drone absent, trait absent, adjacence
    non atteinte) -- jamais un resultat degrade."""
    import hexgeo
    rid = build(seed, board_id, ST_P_UNITS, ST_A_UNITS, STATE_ST)
    if rid is None:
        return None
    if verbose:
        print("[328-ST] runner=%s seed=%s board=%s" % (rid, seed, board_id))
    try:
        view = dv(sid, rid)
        ids = {u.get("visualId"): int(u["id"]) for u in (view.get("units") or []) if u.get("alive")}
        missing = [v for v in (ST_P_UNITS + ST_A_UNITS) if v not in ids]
        if missing:
            print("[328-ST] ABORT unites absentes du build: %s" % missing)
            return None
        p_team = view.get("currentPlayer")
        # 1) Shadowsun + l'allie non-Stationary sur le ring-1 du porteur, l'ennemi a distance 2
        #    (hors de l'anneau : il ne doit pas consommer une tuile du ring-1).
        if setup_positions(sid, rid, ids, near=[SHADOWSUN, FRIEND_MECH],
                           far={ENEMY: 2}) is None:
            print("[328-ST] ABORT placement impossible")
            return None
        # 2) cast : cible = une TUILE adjacente a un allie, la PLUS LOIN possible du porteur (le
        #    drone prend la tuile QUITTEE par Shadowsun, donc il naît adjacent au porteur).
        tgts = _r(sid, "abilityTargets",
                  {"runnerId": rid, "unitId": ids[SHADOWSUN],
                   "abilityType": EXEMPLAR_OF_THE_KAUYON}, 120)
        cands = []
        for u in (tgts.get("units") or []):
            for ab in (u.get("abilities") or []):
                if int(ab.get("abilityType") or ab.get("id") or -1) == EXEMPLAR_OF_THE_KAUYON:
                    cands += (ab.get("fromHere") or [])
        if not cands:
            print("[328-ST] ABORT aucune cible legale pour ExemplarOfTheKauyon(1087)")
            return None
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        cpos = next(((t["col"], t["row"]) for t in bg["tiles"]
                     if t.get("occupantUnitId") == ids[CARRIER]), None)
        by_pos = {(t["col"], t["row"]): t for t in bg["tiles"]}

        def _tid(c):
            if isinstance(c, dict):
                if "tileId" in c:
                    return int(c["tileId"]), None
                p = (int(c.get("col")), int(c.get("row")))
                t = by_pos.get(p)
                return (int(t["id"]) if t else None), p
            return int(c), None
        scored = []
        for c in cands:
            tid, p = _tid(c)
            if tid is None:
                continue
            if p is None:
                t = next((x for x in bg["tiles"] if int(x["id"]) == tid), None)
                p = (t["col"], t["row"]) if t else None
            scored.append((hexgeo.distance(p, cpos) if p else 0, tid))
        if not scored:
            print("[328-ST] ABORT cibles ExemplarOfTheKauyon non resolubles en tuiles")
            return None
        scored.sort(reverse=True)
        _r(sid, "applyAction", {"runnerId": rid, "actions": [
            {"kind": "ability", "casterId": ids[SHADOWSUN], "targetId": scored[0][1],
             "abilityType": EXEMPLAR_OF_THE_KAUYON}]}, 150)
        view = dv(sid, rid)
        ids = {u.get("visualId"): int(u["id"]) for u in (view.get("units") or []) if u.get("alive")}
        if SUMMON not in ids:
            print("[328-ST] ABORT le drone %s n'est pas apparu apres le cast" % SUMMON)
            return None
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 120)
        traits = {int(u["entityId"]): set(u.get("traits") or ())
                  for u in (snap.get("units") or []) if u.get("entityId") is not None}
        from engine.entities.traits.unit_trait import UnitTrait
        if int(UnitTrait.Stationary) not in traits.get(ids[SUMMON], set()):
            print("[328-ST] ABORT le drone ne porte PAS 0x418 Stationary (traits=%s)"
                  % sorted(traits.get(ids[SUMMON], ())))
            return None
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="evenq")
        pos = {t.get("occupantUnitId"): (t["col"], t["row"])
               for t in bg["tiles"] if t.get("occupantUnitId") is not None}
        cpos = pos[ids[CARRIER]]
        dsum = hexgeo.distance(pos[ids[SUMMON]], cpos)
        dmech = hexgeo.distance(pos[ids[FRIEND_MECH]], cpos)
        if verbose:
            print("  drone  %-22s dist=%d Stationary=OUI | %-20s dist=%d Stationary=NON"
                  % (SUMMON, dsum, FRIEND_MECH, dmech))
        if dsum != 1 or dmech != 1:
            print("[328-ST] ABORT adjacence non atteinte (drone=%d mech=%d)" % (dsum, dmech))
            return None
        rows = []
        for k in range(turns):
            if dv(sid, rid).get("currentPlayer") == p_team:
                endturn(sid, rid)
            cap = {"dec": dv(sid, rid, all_ab=True),
                   "ob": _r(sid, "observeBattle", {"runnerId": rid}, 60),
                   "snap": _r(sid, "combatSnapshot", {"runnerId": rid}, 120), "board": board}
            hp_before = hp_live(cap["dec"])
            endturn(sid, rid)
            after_view = dv(sid, rid, all_ab=True)
            live, hp_after = carriers_live(after_view), hp_live(after_view)
            st = offline_fire(cap, p_team)
            off, hp_off = carriers_offline(st), hp_offline(st)
            d_live = {i: hp_after.get(i, 0) - hp_before.get(i, 0) for i in hp_before}
            d_port = {i: hp_off.get(i, 0) - hp_before.get(i, 0) for i in hp_before}
            mut = {g: carriers_offline(offline_fire(cap, p_team, mutate=g))
                   for g in ("stationary", "nostationary")}
            ok = (set(live) == set(off)
                  and all(d_live.get(i) == d_port.get(i) for i in hp_before))
            if verbose:
                print("[328-ST] tour #%d 1011 live=%s port=%s | drone(%s) dans 1011 ? live=%s ; "
                      "mutation 'stationary' -> %s  %s"
                      % (k + 1, sorted(live), sorted(off), ids[SUMMON],
                         ids[SUMMON] in live, sorted(mut["stationary"]),
                         "OK" if ok else "DESACCORD"))
                for i in sorted(d_live):
                    if d_live[i] or d_port[i]:
                        print("        dPV u%-5s live=%+d port=%+d %s"
                              % (i, d_live[i], d_port[i],
                                 "" if d_live[i] == d_port[i] else "<-- DESACCORD"))
            rows.append({"k": k + 1, "live": live, "port": off, "mut": mut,
                         "d_live": d_live, "d_port": d_port, "hp_before": hp_before,
                         "cap": cap, "ok": ok})
        return {"rows": rows, "p_team": p_team, "ids": ids, "rid": rid,
                "drone": ids[SUMMON], "mech": ids[FRIEND_MECH], "carrier": ids[CARRIER]}
    finally:
        if not keep:
            dispose(sid, rid)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="C1_75", help="board a >= 5 spawns joueur")
    ap.add_argument("--turns", type=int, default=3, help="nb de tours de P mesures")
    ap.add_argument("--mutate", action="store_true", help="rejoue les contrefactuels par gate")
    ap.add_argument("--stationary", action="store_true",
                    help="monte le volet MoW/DutyEternal qui exerce UnitsWithoutTrait(0x418)")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner en sortie")
    args = ap.parse_args(argv)

    sid = _resolve_session()
    if args.stationary:
        out = measure_stationary(sid, args.seed, args.board, keep=args.keep)
        if out is None:
            return 2
        bad = sum(0 if r["ok"] else 1 for r in out["rows"])
        bites = sum(1 for r in out["rows"] if set(r["mut_stationary"]) != set(r["live"]))
        print("\n[328-ST] %d tours confrontes, %d desaccords ; la mutation 'stationary' MORD sur "
              "%d/%d tours" % (len(out["rows"]), bad, bites, len(out["rows"])))
        return 0 if (bad == 0 and bites == len(out["rows"])) else 1

    out = measure(sid, args.seed, args.board, args.turns, keep=args.keep)
    if out is None:
        return 2
    rows, p_team, vis_by_id = out["rows"], out["p_team"], out["vis_by_id"]
    bad = sum(0 if r["ok"] else 1 for r in rows)
    if args.mutate and rows:
        print("\n[328] contrefactuels (memes captures, un gate deplace/neutralise a la fois)")
        for gate in ("friends", "adjacent", "repairfilter", "stationary", "nostationary"):
            bites = 0
            for row in rows:
                st = offline_fire(row["cap"], p_team, mutate=gate)
                mo, mhp = carriers_offline(st), hp_offline(st)
                md = {i: mhp.get(i, 0) - row["hp_before"].get(i, 0) for i in row["hp_before"]}
                diff = (set(mo) != set(row["live"])
                        or any(md.get(i) != row["d_live"].get(i) for i in row["hp_before"]))
                bites += 1 if diff else 0
                print("   %-13s tour #%d -> 1011=%s  %s"
                      % (gate, row["k"], sorted(vis_by_id[i] for i in mo),
                         "MORD" if diff else "inerte sur ce montage"))
            print("   => %-13s mord sur %d/%d tours" % (gate, bites, len(rows)))
    print("\n[328] %d tours confrontes, %d desaccords" % (len(rows), bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
