"""CLIQUET #230 -- `load_state` CONSOMME les deux champs d'ETAT DE TOUR du `UnitComponent`.

Le capteur `readUnitTurnState` (`frida/hooks/features/ai-step/rpc-snapshot.ts`, `f790ff4`) expose par
unite `currentTurnStartTile` (@+0x18c) et `chargedUnitIds` (@+0x190) ; `snapshot._load_unit_turn_state`
les pose sur l'ECS au chargement. Ce fichier garde les DEUX faces, chacune par son cas discriminant.

CHARGE -- `IdunBattle.Core.Services.BattleQuery$$IsCharging(caster, target)` =
`AreEntitiesAdjacent(caster, target) && ChargedUnitIds@+0x190.Contains(target.Id)`. La liste n'est
NON VIDE que **pendant une activation** (`IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` la
remplit, `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` la vide) : la capture doit donc etre
prise MI-ACTIVATION, apres le pas et avant l'attaque. C'est ce que `capture_mid=True` ajoute a
`_charge_regime`. Une capture prise ENTRE deux tours la voit toujours vide -- et c'est CORRECT, pas un
defaut de lecture.

  * `CHARGE`        : la cible entre dans la liste -> le seed doit RENDRE le +extraDmg que l'etat
                      d'avant #230 OMETTAIT (degradation RESTRICTIVE, `case-r32` SS 7).
  * `STEP_ADJACENT` : la cible etait DEJA adjacente -> la liste reste vide, le seed ne doit RIEN
                      accorder. C'est la polarite qui interdit un seed « tout adjacent = charge ».

TUILE DE DEBUT DE TOUR -- ECRITE par `IdunBattle.Operations.StartTurnOperation$$Execute`, RELUE par
`IdunBattle.Entities.Selectors.CurrentTurnStartTileSelector$$Select`. Sans le seed, un etat recharge
partait a `None` et le time-ghost de `thousTerminator` (`TimeFluxReviveAbility`, effet 1186) ne se
posait qu'apres un `StartTurnOperation` REJOUE offline -- le contournement `_start_turn` de
`test_ghost_revive_live.py`. Le test ci-dessous joue le PREMIER move sans ce contournement.

ASCII only (console cp1252).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))          # helpers siblings
from _charge_regime import (CHARGE, STEP_ADJACENT,          # noqa: E402,F401  (fixture)
                            charge_regime)

from engine.entities.pathfinding.board import Board                    # noqa: E402
from engine.runner.components import (PositionComponent,               # noqa: E402
                                      UnitComponent)
from engine.runner.events import EventBus                              # noqa: E402
from engine.runner.operations.movement import MoveUnitOperation        # noqa: E402
from engine.runner.operations.triggers import after_move_triggers      # noqa: E402
from engine.runner.operations.triggers.loki.ghost_revive import GHOST_EFFECT   # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                 # noqa: E402
from engine.runner.snapshot import load_state                          # noqa: E402

TOTH = "thousTerminator"


@pytest.fixture(scope="module")
def bullgryn_mid(charge_regime):
    """`astraBullgryn` porte le passif `AvalancheOfMuscle` -> l'effet 1025, gate par `IsCharging`.
    C'est le canal qui rend le seed OBSERVABLE en degat. Cibles a PV gonfles (aucune ne meurt)."""
    return charge_regime(p_units="astraBullgryn", a_units="necroOverlord,necroWarden")


def _run_mid(h, regime):
    rec = h.run(caster_visual="astraBullgryn", regime=regime, capture_mid=True)
    if rec is None:
        pytest.skip("geometrie %s non realisable sur ce board" % regime)
    if not rec["live_ok"] or not rec["live_per_hit"]:
        pytest.skip("attaque normale live refusee/vide (%s)" % regime)
    return rec


@pytest.fixture(scope="module")
def charge_mid(bullgryn_mid):
    """Le regime CHARGE monte UNE SEULE fois (il joue une bataille live) et sert les deux tests."""
    return _run_mid(bullgryn_mid, CHARGE)


def test_charged_unit_ids_are_seeded_from_mid_activation_capture(bullgryn_mid, charge_mid):
    """FACE POSITIVE -- capture MI-ACTIVATION d'un caster qui vient de CHARGER : le seed doit poser
    la cible dans `charged_unit_ids`, et le rejeu offline (SANS rejouer le pas) etre bit-exact."""
    rec = charge_mid
    raw = next((u for u in (rec["snapshot_mid"]["snap"].get("units") or [])
                if u.get("entityId") == rec["caster"]), {})
    assert isinstance(raw.get("chargedUnitIds"), list) and rec["target"] in raw["chargedUnitIds"], (
        "le capteur doit voir la cible dans ChargedUnitIds MI-ACTIVATION ; chargedUnitIds=%s "
        "target=%s (capture prise entre deux tours ? la liste serait vide, et ce serait CORRECT)"
        % (raw.get("chargedUnitIds"), rec["target"]))
    off = bullgryn_mid.replay_offline_mid(rec, seeded=True)
    assert rec["target"] in off["charged"], (
        "`load_state` n'a pas seede ChargedUnitIds : charged=%s target=%s" % (off["charged"],
                                                                              rec["target"]))
    assert off["per_hit"] == rec["live_per_hit"], (
        "CHARGE depuis capture mi-activation : live=%s offline=%s (delta/coup=%s)"
        % (rec["live_per_hit"], off["per_hit"],
           [o - l for l, o in zip(rec["live_per_hit"], off["per_hit"])]))


def test_seed_is_not_vacuous_without_it_the_charge_bonus_is_lost(bullgryn_mid, charge_mid):
    """GARDE DE NON-VACUITE -- le MEME enregistrement rejoue avec les deux champs EFFACES (l'etat
    d'AVANT #230) doit DIVERGER du live, et diverger vers le BAS.

    Sans ce controle, le test positif ci-dessus passerait a vide le jour ou le canal `IsCharging`
    cesserait de porter quoi que ce soit : les deux cotes seraient egaux et personne ne le verrait.
    Le sens de la divergence est le point : la degradation d'avant etait RESTRICTIVE (le port OMET
    le bonus), a l'inverse de l'ancien proxy `has_moved` qui, lui, SUR-accordait (`case-r32`)."""
    rec = charge_mid
    off = bullgryn_mid.replay_offline_mid(rec, seeded=True)
    old = bullgryn_mid.replay_offline_mid(rec, seeded=False)
    assert old["charged"] == [], (
        "contre-epreuve mal montee : les champs devaient etre effaces, charged=%s" % (old["charged"],))
    assert len(old["per_hit"]) == len(off["per_hit"]), (
        "le gate ne doit pas changer la CARDINALITE des coups -- avec=%s sans=%s"
        % (off["per_hit"], old["per_hit"]))
    assert old["per_hit"] != rec["live_per_hit"] and sum(old["per_hit"]) < sum(rec["live_per_hit"]), (
        "scenario NON DISCRIMINANT : effacer le seed ne change rien (live=%s sans-seed=%s) -- le "
        "test positif comparerait live et offline a vide"
        % (rec["live_per_hit"], old["per_hit"]))


def test_step_adjacent_seed_stays_empty(bullgryn_mid):
    """CAS DISCRIMINANT du SEED -- le caster a BOUGE, mais vers une cible DEJA adjacente.

    `UpdateCharging` n'ajoute que les unites NOUVELLEMENT adjacentes : la liste native est VIDE, le
    seed doit donc rester vide et le port ne rien accorder. Un seed qui deviendrait « tous les
    adjacents » (ou qui retomberait sur le proxy `Moved`, VRAI ici) sur-appliquerait +599/coup."""
    rec = _run_mid(bullgryn_mid, STEP_ADJACENT)
    raw = next((u for u in (rec["snapshot_mid"]["snap"].get("units") or [])
                if u.get("entityId") == rec["caster"]), {})
    assert raw.get("chargedUnitIds") == [], (
        "le natif ne doit charger PERSONNE dans ce regime, obtenu %s" % (raw.get("chargedUnitIds"),))
    off = bullgryn_mid.replay_offline_mid(rec, seeded=True)
    assert rec["target"] not in off["charged"], (
        "la cible ne doit PAS entrer dans ChargedUnitIds (deja adjacente avant le pas) ; charged=%s"
        % (off["charged"],))
    assert off["per_hit"] == rec["live_per_hit"], (
        "STEP_ADJACENT depuis capture mi-activation : le port sur-applique -- live=%s offline=%s"
        % (rec["live_per_hit"], off["per_hit"]))


# --------------------------------------------------------------------------------------------
# `currentTurnStartTile` -- le PREMIER move apres chargement, sans rejouer de `StartTurnOperation`.
# --------------------------------------------------------------------------------------------

def test_current_turn_start_tile_drives_first_move_ghost_live(live_session, rpc, build_runner):
    """Toth charge depuis un `combatSnapshot` FRAIS pose son time-ghost sur la BONNE tuile des le
    PREMIER move -- sans le contournement `StartTurnOperation` rejoue offline.

    Deux assertions, dans cet ordre : (1) le champ est seede et vaut la tuile ou Toth se tient a la
    capture ; (2) le `On(PreUnitMove)` du premier move pose l'effet 1186 sur CETTE tuile, et sur
    elle seule."""
    rid = build_runner("31337", extra=["--p-units", TOTH,
                                       "--a-units", "astraBullgryn,orksNob",
                                       "--hp-player", "12000"])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    tm = rpc("tileMeta", {"runnerId": rid}, 90)
    td = next((u for u in (dec.get("units") or []) if u.get("visualId") == TOTH), None)
    if td is None:
        pytest.skip("Toth absent du build")
    tid = int(td["id"])
    raw = next((u for u in (snap.get("units") or []) if u.get("entityId") == tid), {})
    if raw.get("currentTurnStartTile") is None:
        pytest.skip("Toth n'appartient pas au joueur ENTRANT a la capture (champ natif a 0)")

    st = load_state(dec, ob, snap, board=board, tiles=tm)
    st.rng = IntBasedMersenneTwister(12345)
    ent = st.get_entity(tid)
    uc, pc = ent.get_component(UnitComponent), ent.get_component(PositionComponent)
    start = (int(pc.col), int(pc.row))
    here = board.id_at(*start)
    assert uc.current_turn_start_tile == here == raw["currentTurnStartTile"], (
        "current_turn_start_tile non seede : port=%s tuile-courante=%s capteur=%s"
        % (uc.current_turn_start_tile, here, raw.get("currentTurnStartTile")))

    occupied = {(e.get_component(PositionComponent).col, e.get_component(PositionComponent).row)
                for k, e in st.entities.items()
                if e.get_component(PositionComponent) is not None and k != tid}
    dest = next(((int(board.coord(n)[0]), int(board.coord(n)[1]))
                 for n in board.neighbours(here)
                 if board.walkable(n)
                 and (int(board.coord(n)[0]), int(board.coord(n)[1])) not in occupied), None)
    if dest is None:
        pytest.skip("aucune tuile voisine libre pour deplacer Toth")
    MoveUnitOperation(tid, dest).execute(st, EventBus())
    after_move_triggers(st, tid)
    ghosts = sorted(int(t) for t, effs in st.effects.by_unit.items()
                    if int(t) in board.by_id
                    and any((not e.consumed) and e.effect_type == GHOST_EFFECT for e in effs))
    assert ghosts == [here], (
        "le time-ghost 1186 doit se poser sur la tuile de DEBUT DE TOUR %s (tile %s) des le premier "
        "move apres chargement ; obtenu %s (destination %s)" % (start, here, ghosts, dest))
