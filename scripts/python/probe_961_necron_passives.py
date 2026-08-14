#!/usr/bin/env python
"""Probe #961 -- confrontation LIVE-vs-PORT des DEUX derniers passifs Necrons portes :

  * volet `--tm` : `TimesplinterMantle` (`TriggeredAbilityType` 0x5fe = 1534, `necroChronomancer`
    << Thothmek >>) -- `On(0x12 = TurnStart_EffectActivation)` (SANS `IsTurnOf`) ->
    `Foreach(NonSteppableUnits(MechanicalUnits(Friends(AdjacentUnits(Owner)))) + Owner,
             AddEffect(0x60f = 1551))`, effet retire par `On(9) & OwnerIsTarget & IsUnit(Caster)`
    OU par `On(0x17 = TurnEnd)`.
  * volet `--ll` : `LivingLightning` (0x3ef = 1007, `necroPlasmancer` << Thutmose >>) --
    `On(0x1c = ArrivedAtFinalTile) & OwnerIsActor & <il existe une cible>` ->
    `AttackWithAttackDamage(1x DirectDamage)` sur UN ennemi tire au hasard dans le rayon
    `If(<ennemi adjacent>, 1, constants.range = 2)`.

RE in extenso : les en-tetes de `engine/runner/operations/triggers/loki/timesplinter_mantle.py` et
`.../living_lightning.py`.

## Ce que le montage EXERCE (volet TM) -- QUATRE discriminants, positions DRIVEES

  * `admecRuststalker` (allie MECHANICAL non-LivingMetal)  dist 1 -> 1551
  * `astraBullgryn`    (allie ORGANIQUE)                   dist 1 -> RIEN (`MechanicalUnits`)
  * `admecManipulus`   (allie MECHANICAL)                  dist 2 -> RIEN (`AdjacentUnits`)
  * `blackTerminator`  (ENNEMI)                            dist 1 -> RIEN (`Friends`)
  * `necroChronomancer` (le PORTEUR)                       dist 0 -> 1551 (l'`op_Addition Owner`,
                                        que `AdjacentUnits` avait EXCLU -- sans lui, le porteur
                                        ne serait PAS couvert)

Les allies MECHANICAL sont pris NON-`LivingMetal` (Adeptus Mechanicus) : Thothmek et tout Necron
portent `LivingMetal`, dont le regen part au MEME turn-start -- on ne veut pas d'un delta de PV
parasite.

## Le protocole EVITE le regime DEGENERE

1551 est deja pose quand on capture (le natif l'a mis au turn-start precedent), donc rejouer le
seul `On(0x12)` cote port ferait un no-op (`AddEffectOperation` a un gate << deja present >>) et
l'accord ne prouverait RIEN. Le port rejoue donc le BOUNDARY COMPLET :

    On(0x17 = TurnEnd)  -> les DEUX effect-triggers retirent 1551 partout   (l'ensemble doit etre VIDE)
    On(0x12)            -> l'ability le re-pose                            (comparaison REELLE)

L'etage intermediaire est ASSERTIONNE (`empty_after_turnend`) : sans lui, un port qui ne saurait
PAS retirer l'effet passerait le test par heritage de la capture.

## Contre-epreuve NEGATIVE (volet TM)

`--consume` : au tour ADVERSE, l'ennemi FRAPPE une seule des deux unites couvertes. Le natif doit
alors retirer 1551 de CELLE-LA et d'elle seule (`On(9) & OwnerIsTarget`) -- le regime ou l'effet ne
doit PAS se produire, et le seul qui distingue une charge a usage unique d'un buff permanent.

## CONTREFACTUELS (`--mutate`, volet TM), rejoues sur les MEMES captures

  `mechanical` : filtre `MechanicalUnits` retire      -> Bullgryn entre a tort
  `friends`    : gate de camp retire                  -> l'ennemi entre a tort
  `adjacent`   : rayon 2 au lieu de 1                 -> Manipulus entre a tort
  `owner`      : `op_Addition Owner` retire           -> le porteur sort a tort
  `steppable`  : `NonSteppableUnits` retire           -> inerte sur ce montage (aucun Steppable), et
                 c'est DIT plutot que compte pour un succes.

## Volet LL

`necroPlasmancer` est l'UNIQUE entree d'`rl_collect_batch.UNSPAWNABLE_FALLBACK`. RE-MESURE
(`probe_961_plasmancer_spawn.py`) : il SPAWNE sur ce build -- la liste est PERIMEE. Ce probe leve
donc la liste EN MEMOIRE dans le sous-processus de build (le fichier versionne n'est pas touche).

Protocole : positions DRIVEES (un ennemi a distance 2 de la DESTINATION, un autre plus loin), puis

  LIVE : `applyAction move` -> le natif emet `On(0x1c)` -> l'eclair part ; on lit le delta de PV.
  PORT : `load_state(<capture AVANT le move>)`, on TELEPORTE l'unite portee a la meme destination,
         puis `arrived_at_final_tile_triggers(state, uid)` -- le vecteur EXACT que
         `MoveUnitOperation$$Execute` appelle. On compare CIBLE et DEGAT.

ASCII only (cp1252). Usage :
    python probe_961_necron_passives.py --tm [--turns 3] [--mutate] [--consume]
    python probe_961_necron_passives.py --ll
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                                             # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                       # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                # noqa: E402
from engine.entities.effect_type import EffectType                        # noqa: E402
from engine.entities.pathfinding.board import Board                       # noqa: E402
from engine.runner.components import HealthComponent, PositionComponent   # noqa: E402
from engine.runner.snapshot import load_state                             # noqa: E402
from engine.runner.operations.triggers.base import TriggerEvent           # noqa: E402
from engine.runner.operations.triggers.dispatch.core import evaluate_trigger_operation  # noqa: E402
from engine.runner.operations.triggers.dispatch.move_death import (       # noqa: E402
    arrived_at_final_tile_triggers)
from engine.runner.operations.triggers.dispatch.turn import tile_tick_triggers  # noqa: E402

ROOT = PYDIR.parents[1]
STATE_TM = ROOT / "logs" / "runners" / "_961_timesplinter.json"
STATE_LL = ROOT / "logs" / "runners" / "_961_livinglightning.json"

# ---- volet TimesplinterMantle -------------------------------------------------------------------
TM_CARRIER = "necroChronomancer"      # Thothmek : passif TimesplinterMantle (1534)
TM_MECH = "admecRuststalker"          # allie MECHANICAL non-LivingMetal, dist 1 -> COUVERT
TM_ORGANIC = "astraBullgryn"          # allie ORGANIQUE, dist 1 -> NON couvert (MechanicalUnits)
TM_FAR = "admecManipulus"             # allie MECHANICAL, dist 2 -> NON couvert (AdjacentUnits)
# ENNEMI **MECHANICAL** et de MELEE (`orksKillaKan` : traits `Mechanical`, 3 coups au contact), et
# c'est LOAD-BEARING : avec un ennemi organique le gate `Friends` reste INERTE (`MechanicalUnits`
# l'ecarte deja), donc le contrefactuel `friends` ne mordrait pas et le montage serait AVEUGLE a ce
# gate. Mesure : `blackTerminator` -> `friends` mord 0/3 ; `orksKillaKan` -> il mord.
TM_ENEMY = "orksKillaKan"             # ENNEMI Mechanical, dist 1 -> NON couvert (Friends SEUL)
# SECOND ennemi, EXILE a distance >= 5, et il est LOAD-BEARING pour la contre-epreuve NEGATIVE :
# avec un ennemi SEUL, son attaque TERMINE la team adverse -> `EndTurn` + `StartTurn` s'enchainent
# dans le meme `applyAction`, `On(0x17)` retire les 1551 et `On(0x12)` les re-pose TOUS. On lisait
# alors << l'effet n'a pas ete consomme >> (mesure du 2026-08-12 : les DEUX instances remplacees,
# 111->114 et 112->115) alors que c'etait la BORDURE qui repassait derriere. Le second ennemi garde
# le tour adverse OUVERT : `currentPlayer` est alors INCHANGE (assertionne), et le retrait `On(9) &
# OwnerIsTarget` devient VISIBLE -- l'instance de la CIBLE part, celle du porteur ne bouge pas.
TM_ENEMY_SPARE = "orksNob"
TM_P_UNITS = [TM_CARRIER, TM_MECH, TM_ORGANIC, TM_FAR]
TM_A_UNITS = [TM_ENEMY, TM_ENEMY_SPARE]
TM_NEAR = [TM_MECH, TM_ORGANIC, TM_ENEMY]
TM_FAR_PLACEMENT = {TM_FAR: 2, TM_ENEMY_SPARE: 5}

MANTLE = int(EffectType.TimesplinterMantle_DamageReduction)               # 0x60f = 1551
MANTLE_NAME = "TimesplinterMantle_DamageReduction"

# ---- volet LivingLightning ----------------------------------------------------------------------
LL_CARRIER = "necroPlasmancer"        # Thutmose : passif LivingLightning (1007)
LL_ENEMY_NEAR = "orksRuntherd"        # a placer au ring-1 de la DESTINATION
LL_ENEMY_FAR = "orksNob"              # hors du rayon (temoin negatif)
LL_P_UNITS = [LL_CARRIER]
LL_A_UNITS = [LL_ENEMY_NEAR, LL_ENEMY_FAR]


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def augmented_seed_bc() -> Path:
    """`necroChronomancer` est l'une des 21 unites `lineup` ABSENTES du catalogue `BC.Units` du seed
    BC (capture d'UNE bataille). On l'injecte -- `catalog_inject` pose l'unite ET ses configs
    d'ability, faute de quoi le cast/le trigger faute au deploiement (« system error », #226).
    Sortie dans `logs/` (jamais sous `data/`, qui ne porte que des ENTREES versionnees)."""
    import catalog_inject
    out = ROOT / "logs" / "runners" / "_961_seed_bc_necrons.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        catalog_inject.write_augmented_seed_bc(str(out), [TM_CARRIER])
    return out


def build(seed, board, p_units, a_units, state_file, extra=(), lift_unspawnable=False,
          seed_bc=None):
    """`rl_duel build` en SOUS-PROCESSUS. `lift_unspawnable` vide `UNSPAWNABLE_FALLBACK` EN MEMOIRE
    dans ce sous-processus (le fichier versionne `rl_collect_batch.py` n'est pas touche) : c'est le
    seul moyen d'amener `necroPlasmancer` en bataille tant que la liste heritee n'est pas re-mesuree
    pour tout le monde (cf. le residu ouvert)."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    argv = ["build", "--seed", str(seed), "--state-file", str(state_file), "--board", board,
            "--p-units", ",".join(p_units), "--a-units", ",".join(a_units)]
    if seed_bc is not None:
        argv += ["--seed-bc", str(seed_bc)]
    for spec in extra:
        argv += ["--unit-stat", spec]
    if lift_unspawnable:
        code = ("import sys; sys.path.insert(0, %r);"
                "import rl_collect_batch as R; R.UNSPAWNABLE_FALLBACK = set();"
                "import rl_duel; sys.exit(rl_duel.main(%r))" % (str(PYDIR), argv))
        cmd = [sys.executable, "-c", code]
    else:
        cmd = [sys.executable, "rl_duel.py"] + argv
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[961] build KO:", ((proc.stderr or "") + (proc.stdout or ""))[-900:], file=sys.stderr)
        return None
    return json.loads(state_file.read_text())["runnerId"]


def dispose(sid, rid):
    try:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    except Exception as exc:                                   # pragma: no cover (nettoyage)
        print("[961] dispose KO:", exc, file=sys.stderr)


def dv(sid, rid, all_ab=False, mr=1, inactifs=False):
    """`decisionView`. `inactifs` = drapeau `includeInactive` du canal.

    ⚠ DEFAUT INCHANGE (`False`), et c'est deliberе : le canal FILTRE les effets inactifs quand on
    ne le passe pas, donc tout appelant historique garde exactement la vue qu'il mesurait. Le
    parametre existe parce que l'absence d'un effet dans la vue par defaut ne distingue PAS
    << pose mais inactif a cet instant >> de << pas pose du tout >> -- c'est la cause (a) vs (b)
    de `#961-r3`, et elle se tranche en redemandant la MEME vue avec `includeInactive: true`."""
    b = {"runnerId": rid, "maxRank": mr}
    if all_ab:
        b["allAbilities"] = True
    if inactifs:
        b["includeInactive"] = True
    return _r(sid, "decisionView", b, 150 if all_ab else 60)


def move(sid, rid, uid, col, row):
    return _r(sid, "applyAction", {"runnerId": rid, "actions": [
        {"kind": "move", "unitId": uid, "to": {"col": col, "row": row}}]}, 60)


def endturn(sid, rid):
    return _r(sid, "applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 90)


def carriers_live(view, effect_type=MANTLE, name=MANTLE_NAME) -> dict:
    out = {}
    for u in (view.get("units") or []):
        for e in (u.get("effects") or []):
            if e.get("active") is False:
                continue
            if int(e.get("effectType") or -1) == effect_type or e.get("name") == name:
                out[int(u["id"])] = e.get("remaining")
    return out


def carriers_offline(state, effect_type=MANTLE) -> dict:
    eff = getattr(state, "effects", None)
    if eff is None:
        return {}
    return {int(uid): e.remaining_turns
            for uid, lst in eff.by_unit.items()
            for e in lst if (not e.consumed) and int(e.effect_type) == effect_type}


def hp_live(view) -> dict:
    return {int(u["id"]): int(u.get("hp") or 0) for u in (view.get("units") or []) if u.get("alive")}


def hp_offline(state) -> dict:
    out = {}
    for eid, e in state.entities.items():
        hc = e.get_component(HealthComponent)
        if hc is not None and hc.hp is not None:
            out[int(eid)] = int(hc.hp)
    return out


def _mt_draws(before, after):
    """Nombre de `genrand` consommes entre deux etats MT19937 (`mti` = index dans le bloc de 624 ;
    un `mti` qui RECULE signale un RELOAD du bloc). `None` si un des deux etats manque."""
    if not (isinstance(before, dict) and isinstance(after, dict)):
        return None
    b, a = before.get("mti"), after.get("mti")
    if b is None or a is None:
        return None
    d = int(a) - int(b)
    return d if d >= 0 else d + 624


def _hub_tile(bg):
    """Une tuile jouable a SIX voisins jouables (runner.md : une mecanique qui compte des voisins
    exige explicitement une tuile a 6 voisins -- un coin de spawn la SOUS-EXERCERAIT)."""
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


def setup_positions(sid, rid, ids, carrier, near, far):
    """DRIVE les positions : le porteur sur une tuile a 6 voisins, `near` sur son ring-1, `far` aux
    distances hex voulues. `applyAction move` TELEPORTE -> la geometrie est CHOISIE, pas subie."""
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    hub = _hub_tile(bg)
    if hub is None:
        return None
    move(sid, rid, ids[carrier], hub["col"], hub["row"])
    for vis in near:
        if vis not in ids:
            continue
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        by_id = {t["id"]: t for t in bg["tiles"]}
        ctile = next((t for t in bg["tiles"] if t.get("occupantUnitId") == ids[carrier]), None)
        if ctile is None:
            return None
        free = [by_id[n] for n in (ctile.get("neighbours") or [])
                if n in by_id and by_id[n].get("walkable") and not by_id[n].get("isWall")
                and by_id[n].get("occupantUnitId") in (None, ids[vis])]
        if not free:
            return None
        move(sid, rid, ids[vis], free[0]["col"], free[0]["row"])
    for vis, want in (far or {}).items():
        if vis not in ids:
            continue
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        ctile = next((t for t in bg["tiles"] if t.get("occupantUnitId") == ids[carrier]), None)
        occupied = {t["id"] for t in bg["tiles"] if t.get("occupantUnitId") is not None}
        cpos = (ctile["col"], ctile["row"])
        tgt = next((t for t in bg["tiles"]
                    if t.get("walkable") and not t.get("isWall") and t["id"] not in occupied
                    and hexgeo.distance((t["col"], t["row"]), cpos) == want), None)
        if tgt is None:
            return None
        move(sid, rid, ids[vis], tgt["col"], tgt["row"])
    return _r(sid, "boardGraph", {"runnerId": rid}, 90)


# ================================================================================================
# VOLET TimesplinterMantle
# ================================================================================================
def _patched_targets(mutate):
    """Remplacant de `timesplinter_mantle_targets` avec UN gate neutralise a la fois."""
    from engine.dsl.base import Const
    from engine.entities.selectors.tiles import Caster
    from engine.entities.selectors.units import (
        AdjacentUnits, Friends, MechanicalUnits, Union, non_steppable_units)
    import engine.runner.operations.triggers.loki.timesplinter_mantle as M

    def patched():
        owner = Caster()
        sel = M._SEL_ALIVE_TARGETABLE
        chain = AdjacentUnits(owner, Const(2) if mutate == "adjacent" else Const(1),
                              selection_type=sel)
        if mutate != "friends":
            chain = Friends(chain, owner, selection_type=sel)
        if mutate != "mechanical":
            chain = MechanicalUnits(chain, selection_type=sel)
        if mutate != "steppable":
            chain = non_steppable_units(chain, sel)
        return chain if mutate == "owner" else Union(chain, owner)
    return patched


def tm_offline_boundary(cap, player, mutate=None):
    """Rejoue le BOUNDARY de tour cote PORT depuis la capture : `On(0x17 = TurnEnd)` (retrait par
    les deux effect-triggers) PUIS `On(0x12 = TurnStart_EffectActivation)` (re-pose par l'ability).

    Rend `(state, set_apres_turnend)` -- le second est ce qui interdit le regime DEGENERE : si le
    retrait ne marchait pas, l'ensemble final serait celui de la capture, pas celui que l'ability
    reconstruit.

    Le `On(0x17)` est emis en BRUT (`evaluate_trigger_operation`) et non par
    `end_turn_summon_triggers`, qui embarque en plus le volet BESPOKE `PileIn` (spawn) : on veut le
    vecteur, pas son voisinage."""
    import engine.runner.operations.triggers.loki.timesplinter_mantle as M
    state = load_state(cap["dec"], cap["ob"], cap["snap"], board=cap["board"])
    ev = TriggerEvent(EventTriggerType.TurnEnd, -1, -1, ranged=False, profile=None,
                      player_id=player)
    evaluate_trigger_operation(state, ev)
    after_end = carriers_offline(state)
    saved = M.timesplinter_mantle_targets
    if mutate is not None:
        M.timesplinter_mantle_targets = _patched_targets(mutate)
    try:
        tile_tick_triggers(state)
    finally:
        M.timesplinter_mantle_targets = saved
    return state, after_end


def measure_tm(sid, seed, board_id, turns, verbose=True, keep=False, consume=False):
    rid = build(seed, board_id, TM_P_UNITS, TM_A_UNITS, STATE_TM, seed_bc=augmented_seed_bc())
    if rid is None:
        return None
    if verbose:
        print("[961-TM] runner=%s seed=%s board=%s" % (rid, seed, board_id))
    try:
        view = dv(sid, rid)
        ids, teams = {}, {}
        for u in (view.get("units") or []):
            if u.get("alive"):
                ids[u.get("visualId")] = int(u["id"])
                teams[int(u["id"])] = u.get("team")
        missing = [v for v in (TM_P_UNITS + TM_A_UNITS) if v not in ids]
        if missing:
            print("[961-TM] ABORT unites absentes du build: %s" % missing)
            return None
        vis_by_id = {v: k for k, v in ids.items()}
        p_team = view.get("currentPlayer")
        if setup_positions(sid, rid, ids, TM_CARRIER, TM_NEAR, TM_FAR_PLACEMENT) is None:
            print("[961-TM] ABORT placement impossible")
            return None
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="evenq")
        pos = {t.get("occupantUnitId"): (t["col"], t["row"])
               for t in bg["tiles"] if t.get("occupantUnitId") is not None}
        cpos = pos[ids[TM_CARRIER]]
        want = {v: 1 for v in TM_NEAR}
        want.update(TM_FAR_PLACEMENT)
        degraded = []
        for vis in TM_P_UNITS + TM_A_UNITS:
            if vis == TM_CARRIER:
                continue
            d = hexgeo.distance(pos[ids[vis]], cpos)
            if verbose:
                print("  place %-20s pos=%s dist=%d (voulu %d) team=%s"
                      % (vis, pos[ids[vis]], d, want[vis], teams[ids[vis]]))
            if d != want[vis]:
                degraded.append((vis, d, want[vis]))
        # GEOMETRIE ASSERTIONNEE CONTRE LE `boardGraph` : la distance est CALCULEE (hexgeo) puis
        # confrontee a l'adjacence STOCKEE du plateau -- un montage ou le voisinage differerait de
        # `distance == 1` invaliderait le discriminant `AdjacentUnits`.
        ctile = next(t for t in bg["tiles"] if t.get("occupantUnitId") == ids[TM_CARRIER])
        ring = set(ctile.get("neighbours") or [])
        tile_of = {t.get("occupantUnitId"): t["id"] for t in bg["tiles"]
                   if t.get("occupantUnitId") is not None}
        for vis in TM_NEAR:
            if tile_of[ids[vis]] not in ring:
                degraded.append((vis, "hors boardGraph.neighbours", 1))
        if tile_of[ids[TM_FAR]] in ring:
            degraded.append((TM_FAR, "DANS boardGraph.neighbours", 2))
        if degraded:
            print("[961-TM] ABORT montage degrade: %s" % degraded)
            return None

        rows = []
        for k in range(turns):
            cap = {"dec": dv(sid, rid, all_ab=True),
                   "ob": _r(sid, "observeBattle", {"runnerId": rid}, 60),
                   "snap": _r(sid, "combatSnapshot", {"runnerId": rid}, 120), "board": board}
            cur = cap["dec"].get("currentPlayer")
            endturn(sid, rid)                                  # boundary : TurnEnd puis TurnStart
            after_view = dv(sid, rid, all_ab=True)
            live = carriers_live(after_view)
            st, after_end = tm_offline_boundary(cap, cur)
            off = carriers_offline(st)
            ok = set(live) == set(off) and not after_end
            if verbose:
                print("[961-TM] boundary #%d (joueur %s -> %s) : 1551 live=%s port=%s "
                      "| apres On(TurnEnd) port=%s  %s"
                      % (k + 1, cur, after_view.get("currentPlayer"),
                         sorted(vis_by_id[i] for i in live),
                         sorted(vis_by_id[i] for i in off),
                         sorted(vis_by_id.get(i, i) for i in after_end),
                         "OK" if ok else "DESACCORD"))
            rows.append({"k": k + 1, "player": cur, "live": live, "port": off,
                         "after_end": after_end, "cap": cap, "ok": ok})

        consumed = None
        if consume:
            consumed = _tm_consume(sid, rid, ids, vis_by_id, p_team, verbose)
        return {"rows": rows, "ids": ids, "vis_by_id": vis_by_id, "rid": rid,
                "p_team": p_team, "consumed": consumed}
    finally:
        if not keep:
            dispose(sid, rid)


def _tm_consume(sid, rid, ids, vis_by_id, p_team, verbose=True):
    """CONTRE-EPREUVE NEGATIVE : l'ennemi frappe UNE des deux unites couvertes ; 1551 doit
    disparaitre de CELLE-LA et d'elle seule (`On(9 = Attack) & get_OwnerIsTarget`)."""
    while dv(sid, rid).get("currentPlayer") == p_team:
        endturn(sid, rid)                                      # se placer au tour de l'ENNEMI
    view = dv(sid, rid, all_ab=True)
    before = carriers_live(view)
    victim = ids[TM_MECH] if ids[TM_MECH] in before else (
        ids[TM_CARRIER] if ids[TM_CARRIER] in before else None)
    if victim is None:
        print("[961-TM] consume : aucune unite couverte a frapper")
        return None
    normal = None
    for u in (view.get("units") or []):
        if int(u["id"]) == ids[TM_ENEMY]:
            normal = next((int(a["id"]) for a in (u.get("abilities") or [])
                           if a.get("kind") == "normal"), None)
    if normal is None:
        print("[961-TM] consume : pas d'attaque normale sur l'ennemi")
        return None
    hp0 = hp_live(view)
    cur0 = view.get("currentPlayer")
    res = _r(sid, "applyAction", {"runnerId": rid, "actions": [
        {"kind": "ability", "casterId": ids[TM_ENEMY], "targetId": victim,
         "abilityType": normal}]}, 150)
    after_view = dv(sid, rid, all_ab=True)
    after, hp1 = carriers_live(after_view), hp_live(after_view)
    dmg = hp0.get(victim, 0) - hp1.get(victim, 0)
    # GARDE DE MONTAGE : si le coup a CLOS le tour adverse, la bordure `On(0x17)` + `On(0x12)` est
    # repassee derriere et l'observable ne dit plus rien du retrait. Le second ennemi EXILE est la
    # pour empecher ca ; on le VERIFIE plutot que de l'esperer.
    turn_kept = (cur0 == after_view.get("currentPlayer"))
    if verbose:
        print("[961-TM] CONSUME : l'ennemi frappe %s (dPV=%+d, tour %s) -> 1551 avant=%s apres=%s"
              % (vis_by_id[victim], -dmg, "OUVERT" if turn_kept else "CLOS <-- MONTAGE AVEUGLE",
                 sorted(vis_by_id[i] for i in before),
                 sorted(vis_by_id[i] for i in after)))
        if not dmg:
            print("        applyAction (brut) = %s" % json.dumps(res)[:600])
    # PORT : le MEME retrait, rejoue depuis la capture d'AVANT le coup.
    st = load_state(view, _r(sid, "observeBattle", {"runnerId": rid}, 60),
                    _r(sid, "combatSnapshot", {"runnerId": rid}, 120))
    ev = TriggerEvent(EventTriggerType.Attack, ids[TM_ENEMY], victim, ranged=False, profile=None)
    evaluate_trigger_operation(st, ev)
    port_after = carriers_offline(st)
    if verbose:
        print("        PORT On(9 Attack, target=%s) -> 1551 = %s"
              % (vis_by_id[victim], sorted(vis_by_id.get(i, i) for i in port_after)))
    return {"victim": victim, "before": before, "after": after, "dmg": dmg,
            "port_after": port_after, "turn_kept": turn_kept,
            "agree": (set(after) == set(port_after))}


# ================================================================================================
# VOLET LivingLightning
# ================================================================================================
def measure_ll(sid, seed, board_id, verbose=True, keep=False, regime="adjacent"):
    """`regime` = la DISTANCE de l'ennemi le plus proche a la DESTINATION du pas, donc la BRANCHE
    du `If(AmountIsGreaterThanZero(AdjacentEnemies(Caster)), Direct(1), Get(constants.range))` :

      * `adjacent` (1) -- branche THEN, rayon 1. C'est le seul regime que l'i2 decrit.
      * `range2`   (2) -- branche ELSE, rayon `constants.range` = 2. L'i2 dit << adjacent enemy >>
                          et le natif frappe QUAND MEME : c'est la branche que le tooltip ne dit
                          pas, et la recopier aurait rendu l'ability muette ici.
      * `none`     (>=3) -- CONTRE-EPREUVE NEGATIVE : hors des deux rayons, le gate
                          `!AmountIsZero(...)` est faux et RIEN ne doit se produire."""
    # `adjacent_low` = MEME distance 1 que `adjacent`, mais sur une tuile d'elevation STRICTEMENT
    # INFERIEURE a la destination : c'est le SEPARATEUR qui distingue << la distance 1 >> de
    # << l'egalite d'elevation >> quand un ecart apparait (cf. le residu nomme dans le rapport).
    #
    # #961-r1 -- LA DISTANCE ET L'ELEVATION ETAIENT CONFONDUES DANS LE MONTAGE D'ORIGINE : la tuile
    # `near` etant prise comme la PREMIERE libre a la distance voulue, `adjacent` tombait sur une
    # tuile d'elevation EGALE (aucun bonus) et `range2` sur une tuile PLUS BASSE (bonus x1.5). Les
    # deux regimes differaient donc par DEUX variables. `range2_flat` (distance 2, elevation EGALE)
    # et `adjacent_low` (distance 1, elevation INFERIEURE) completent le carre 2x2 et rendent chaque
    # axe separable.
    want = {"adjacent": 1, "adjacent_low": 1,
            "range2": 2, "range2_flat": 2, "none": 3}[regime]
    want_lower = (regime == "adjacent_low")
    want_equal = (regime == "range2_flat")
    rid = build(seed, board_id, LL_P_UNITS, LL_A_UNITS, STATE_LL, lift_unspawnable=True)
    if rid is None:
        return None
    if verbose:
        print("[961-LL] runner=%s seed=%s board=%s" % (rid, seed, board_id))
    try:
        view = dv(sid, rid)
        ids = {u.get("visualId"): int(u["id"]) for u in (view.get("units") or []) if u.get("alive")}
        missing = [v for v in (LL_P_UNITS + LL_A_UNITS) if v not in ids]
        if missing:
            print("[961-LL] ABORT unites absentes du build: %s" % missing)
            return None
        vis_by_id = {v: k for k, v in ids.items()}
        p_team = view.get("currentPlayer")
        # 1) On choisit la DESTINATION du porteur : une tuile a 6 voisins.
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        hub = _hub_tile(bg)
        if hub is None:
            print("[961-LL] ABORT pas de tuile hub")
            return None
        by_id = {t["id"]: t for t in bg["tiles"]}
        # 2) l'ennemi PROCHE sur le ring-1 de la destination, l'ennemi LOIN a distance >= 4.
        dest = (hub["col"], hub["row"])
        # L'ennemi PROCHE est place a la distance EXACTE voulue par le regime -- c'est ce qui
        # selectionne la branche du `If` (rayon 1 / rayon `range` / hors portee).
        dest_elev = hub.get("elevation")
        near_t = next((t for t in bg["tiles"]
                       if t.get("walkable") and not t.get("isWall")
                       and t.get("occupantUnitId") is None
                       and hexgeo.distance((t["col"], t["row"]), dest) == want
                       and (not want_lower or (t.get("elevation") is not None
                                               and dest_elev is not None
                                               and t["elevation"] < dest_elev))
                       and (not want_equal or (t.get("elevation") is not None
                                               and dest_elev is not None
                                               and t["elevation"] == dest_elev))), None)
        if near_t is None:
            print("[961-LL] ABORT pas de tuile libre a distance %d de la destination" % want)
            return None
        move(sid, rid, ids[LL_ENEMY_NEAR], near_t["col"], near_t["row"])
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        far_t = next((t for t in bg["tiles"]
                      if t.get("walkable") and not t.get("isWall")
                      and t.get("occupantUnitId") is None
                      and hexgeo.distance((t["col"], t["row"]), dest) >= 4), None)
        if far_t is None:
            print("[961-LL] ABORT pas de tuile lointaine libre")
            return None
        move(sid, rid, ids[LL_ENEMY_FAR], far_t["col"], far_t["row"])
        # 3) le porteur ADJACENT a la destination (pour que le pas soit legal et court).
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        by_id = {t["id"]: t for t in bg["tiles"]}
        start = next((by_id[n] for n in (hub.get("neighbours") or [])
                      if n in by_id and by_id[n].get("walkable") and not by_id[n].get("isWall")
                      and by_id[n].get("occupantUnitId") is None), None)
        if start is None:
            print("[961-LL] ABORT pas de tuile de depart libre")
            return None
        move(sid, rid, ids[LL_CARRIER], start["col"], start["row"])
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="evenq")
        pos = {t.get("occupantUnitId"): (t["col"], t["row"])
               for t in bg["tiles"] if t.get("occupantUnitId") is not None}
        d_near = hexgeo.distance(pos[ids[LL_ENEMY_NEAR]], dest)
        d_far = hexgeo.distance(pos[ids[LL_ENEMY_FAR]], dest)
        elev = {(t["col"], t["row"]): t.get("elevation") for t in bg["tiles"]}
        if verbose:
            for lbl, p in (("dest", dest), ("near", pos[ids[LL_ENEMY_NEAR]]),
                           ("start", pos[ids[LL_CARRIER]])):
                rec = next((t for t in bg["tiles"] if (t["col"], t["row"]) == p), {})
                print("    tuile %-5s %s -> %s" % (lbl, p, {k: v for k, v in rec.items()
                                                           if k not in ("neighbours",)}))
        if verbose:
            print("  regime=%s destination=%s (elev %s) | %s dist=%d (voulu %d, elev %s) | "
                  "%s dist=%d | depart=%s (elev %s)"
                  % (regime, dest, elev.get(dest), LL_ENEMY_NEAR, d_near, want,
                     elev.get(pos[ids[LL_ENEMY_NEAR]]), LL_ENEMY_FAR, d_far,
                     pos[ids[LL_CARRIER]], elev.get(pos[ids[LL_CARRIER]])))
        # GEOMETRIE ASSERTIONNEE CONTRE LE `boardGraph` : la distance hexgeo est CONFRONTEE a
        # l'adjacence STOCKEE du plateau (le rayon 1 du `If` est celui du voisinage, pas d'une
        # metrique calculee a cote).
        dest_id = next((t["id"] for t in bg["tiles"] if (t["col"], t["row"]) == dest), None)
        ring = set(next(t.get("neighbours") or [] for t in bg["tiles"] if t["id"] == dest_id))
        near_tid = next(t["id"] for t in bg["tiles"]
                        if t.get("occupantUnitId") == ids[LL_ENEMY_NEAR])
        in_ring = near_tid in ring
        if d_near != want or d_far < 4 or in_ring != (want == 1):
            print("[961-LL] ABORT geometrie non atteinte (near=%d voulu=%d far=%d ring=%s)"
                  % (d_near, want, d_far, in_ring))
            return None
        # 3bis) UN ROUND COMPLET avant de mesurer. Les `move` de placement sont de VRAIS
        # deplacements du point de vue du natif : ils posent `UnitFlag.ArrivedAtFinalTile` (et
        # consomment l'activation). Or `MoveUnitOperation$$Execute` ne publie `On(0x1c)` que si le
        # flag vient d'etre AJOUTE -- un second move dans le MEME tour n'emet donc RIEN, et le
        # << port et live tous deux a zero >> qu'on lisait etait un accord DEGENERE, pas une mesure.
        # `StartTurnOperation` remet les `UnitFlags` a plat : on rend la main jusqu'a revenir au
        # tour du porteur, et on VERIFIE qu'il est bien activable avant de bouger.
        for _ in range(6):
            endturn(sid, rid)
            if dv(sid, rid).get("currentPlayer") == p_team:
                break
        pre = dv(sid, rid, all_ab=True)
        to_act = [int(x) for x in (pre.get("toActivate") or [])]
        if verbose:
            print("  tour du porteur : currentPlayer=%s toActivate=%s"
                  % (pre.get("currentPlayer"), [vis_by_id.get(i, i) for i in to_act]))
        if ids[LL_CARRIER] not in to_act:
            print("[961-LL] ABORT le porteur n'est pas activable -- le move n'emettrait pas On(0x1c)")
            return None
        # 4) capture AVANT le move, puis LIVE move.
        cap = {"dec": dv(sid, rid, all_ab=True),
               "ob": _r(sid, "observeBattle", {"runnerId": rid}, 60),
               "snap": _r(sid, "combatSnapshot", {"runnerId": rid}, 120), "board": board}
        # ETAT MT LIVE : sans lui, `AttackDamageOperation.execute_ability_attack` SKIPPE le degat
        # (`return None`, garde documentee << rng non cale >>) et le port rendait `attack: null`
        # avec un delta de PV NUL -- un accord DEGENERE avec un live a zero, puis un desaccord
        # muet. C'est le meme calage que `probe_116_necrons`.
        rng0 = _r(sid, "dumpRng", {"runnerId": rid}, 30)
        hp_before = hp_live(cap["dec"])
        move(sid, rid, ids[LL_CARRIER], dest[0], dest[1])
        bg2 = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        landed = next(((t["col"], t["row"]) for t in bg2["tiles"]
                       if t.get("occupantUnitId") == ids[LL_CARRIER]), None)
        if verbose:
            print("  move %s -> %s (arrive en %s)" % (pos[ids[LL_CARRIER]], dest, landed))
        if landed != dest:
            print("[961-LL] ABORT le move n'a pas abouti (%s != %s)" % (landed, dest))
            return None
        after_view = dv(sid, rid, all_ab=True)
        rng1 = _r(sid, "dumpRng", {"runnerId": rid}, 30)
        hp_after = hp_live(after_view)
        d_live = {i: hp_after.get(i, 0) - hp_before.get(i, 0) for i in hp_before}
        # 5) PORT : meme capture, on TELEPORTE puis on emet le vecteur `On(0x1c)`.
        st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board)
        if isinstance(rng0, dict) and rng0.get("mt"):
            from engine.runner.prng import IntBasedMersenneTwister
            rng = IntBasedMersenneTwister()
            rng.mt, rng.mti = list(rng0["mt"]), rng0["mti"]
            st.rng = rng
        ent = st.get_entity(ids[LL_CARRIER])
        pc = ent.get_component(PositionComponent) if ent is not None else None
        if pc is None:
            print("[961-LL] ABORT porteur sans PositionComponent cote port")
            return None
        pc.col, pc.row = int(dest[0]), int(dest[1])
        fired = arrived_at_final_tile_triggers(st, ids[LL_CARRIER])
        hp_off = hp_offline(st)
        d_port = {i: hp_off.get(i, 0) - hp_before.get(i, 0) for i in hp_before}
        # DECOMPOSITION PAR ETAGE plutot que fit d'un scalaire : le compteur MT dit combien de
        # tirages chaque cote a consommes. Un ecart de degat A CIBLE IDENTIQUE avec un ecart de
        # tirages est un DECALAGE DE FLUX (le natif evalue `PickRandomly` DEUX fois -- une dans le
        # gate `AmountIsZero` du trigger, une dans le behaviour -- la ou le port ne l'evalue qu'une),
        # pas une erreur de magnitude.
        # TEMOIN DE MONTAGE : le MEME rejeu SANS la teleportation. Si les deux rendent le meme
        # degat, la teleportation est INERTE cote port et la comparaison ne mesure pas ce qu'elle
        # pretend (elle jugerait un tir depuis la tuile de DEPART).
        st_nt = load_state(cap["dec"], cap["ob"], cap["snap"], board=board)
        if isinstance(rng0, dict) and rng0.get("mt"):
            from engine.runner.prng import IntBasedMersenneTwister
            r2 = IntBasedMersenneTwister()
            r2.mt, r2.mti = list(rng0["mt"]), rng0["mti"]
            st_nt.rng = r2
        arrived_at_final_tile_triggers(st_nt, ids[LL_CARRIER])
        hp_nt = hp_offline(st_nt)
        d_nt = {i: hp_nt.get(i, 0) - hp_before.get(i, 0) for i in hp_before}
        if verbose:
            ent2 = st.get_entity(ids[LL_CARRIER])
            pc2 = ent2.get_component(PositionComponent) if ent2 is not None else None
            print("[961-LL] port : caster @%s (teleporte) | temoin SANS teleport dPV=%s"
                  % ((pc2.col, pc2.row) if pc2 else None,
                     {vis_by_id.get(i, i): d_nt[i] for i in sorted(d_nt) if d_nt[i]}))
        draws_live = _mt_draws(rng0, rng1)
        draws_port = _mt_draws(rng0, {"mt": list(st.rng.mt), "mti": st.rng.mti}) \
            if getattr(st, "rng", None) is not None else None
        if verbose:
            print("[961-LL] tirages MT : live=%s port=%s (mti %s -> live %s / port %s)"
                  % (draws_live, draws_port, (rng0 or {}).get("mti"), (rng1 or {}).get("mti"),
                     getattr(getattr(st, "rng", None), "mti", None)))
        if verbose:
            print("[961-LL] dPV live=%s" % {vis_by_id.get(i, i): d_live[i]
                                            for i in sorted(d_live) if d_live[i]})
            print("[961-LL] dPV port=%s" % {vis_by_id.get(i, i): d_port[i]
                                            for i in sorted(d_port) if d_port[i]})
            print("[961-LL] triggers portes : %s" % [f.get("passive") or f.get("effect")
                                                     for f in fired])
        return {"ids": ids, "vis_by_id": vis_by_id, "d_live": d_live, "d_port": d_port,
                "fired": fired, "hp_before": hp_before, "cap": cap, "dest": dest,
                "rid": rid, "p_team": p_team, "regime": regime,
                "draws_live": draws_live, "draws_port": draws_port,
                "hit_live": {i: d_live[i] for i in d_live if d_live[i]},
                "hit_port": {i: d_port[i] for i in d_port if d_port[i]}}
    finally:
        if not keep:
            dispose(sid, rid)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tm", action="store_true", help="volet TimesplinterMantle")
    ap.add_argument("--ll", action="store_true", help="volet LivingLightning")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="C1_75")
    ap.add_argument("--turns", type=int, default=3)
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--consume", action="store_true")
    ap.add_argument("--regimes", default=None,
                    help="volet LL : liste de regimes (adjacent,range2,none)")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)
    if not (args.tm or args.ll):
        args.tm = args.ll = True

    sid = _resolve_session()
    rc = 0
    if args.tm:
        out = measure_tm(sid, args.seed, args.board, args.turns, keep=args.keep,
                         consume=args.consume)
        if out is None:
            return 2
        rows, vis = out["rows"], out["vis_by_id"]
        bad = sum(0 if r["ok"] else 1 for r in rows)
        if args.mutate and rows:
            print("\n[961-TM] contrefactuels (memes captures, un gate a la fois)")
            for gate in ("mechanical", "friends", "adjacent", "owner", "steppable"):
                bites = 0
                for row in rows:
                    st, _ = tm_offline_boundary(row["cap"], row["player"], mutate=gate)
                    mo = carriers_offline(st)
                    diff = set(mo) != set(row["live"])
                    bites += 1 if diff else 0
                print("   %-11s mord sur %d/%d boundaries" % (gate, bites, len(rows)))
        print("\n[961-TM] %d boundaries confrontes, %d desaccords" % (len(rows), bad))
        rc |= (0 if bad == 0 else 1)
    if args.ll:
        # LES TROIS REGIMES : rayon 1 (branche THEN), rayon `range` (branche ELSE, celle que l'i2
        # ne decrit PAS) et hors portee (contre-epreuve NEGATIVE). Un seul regime rendrait un vert
        # qui ne distingue pas un port fidele d'un port qui ne fait jamais rien.
        regimes = args.regimes.split(",") if args.regimes else ["adjacent", "range2", "none"]
        summary = []
        for reg in regimes:
            out = measure_ll(sid, args.seed, args.board, keep=args.keep, regime=reg)
            if out is None:
                return 2
            agree = (all(out["d_live"].get(i) == out["d_port"].get(i) for i in out["hp_before"])
                     and out["draws_live"] == out["draws_port"])
            fired = bool(out["hit_live"])
            expect_fire = (reg != "none")
            print("[961-LL] regime %-8s : tire=%s (attendu %s) | dPV live=%s port=%s | "
                  "tirages %s/%s -> %s"
                  % (reg, fired, expect_fire, out["hit_live"], out["hit_port"],
                     out["draws_live"], out["draws_port"],
                     "OK" if (agree and fired == expect_fire) else "DESACCORD"))
            summary.append(agree and fired == expect_fire)
        print("\n[961-LL] %d regimes, %d desaccords" % (len(summary), sum(1 for s in summary if not s)))
        rc |= (0 if all(summary) else 1)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
