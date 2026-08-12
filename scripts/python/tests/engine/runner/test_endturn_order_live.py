"""ORDRE dans `IdunBattle.Operations.EndTurnOperation$$Execute` : le vecteur de triggers
`On(0x17 = TurnEnd)` s'execute AVANT `IdunBattle.Operations.EndTurnOperation$$RefreshEffects`.

Lu dans le corps d'`Execute` (decompile = verite, pas l'experience) -- les cinq etapes, dans l'ordre :

  1. boucle sur `PlayerComponent.CurrentlyOwnedUnitIds` du joueur FINISSANT : `turnsFinished@+0x5c += 1`
     (+ `IdunBattle.Operations.EndTurnOperation$$ResetAbilitiesThatResetOnTurnEnd` et
     `IdunBattle.Operations.EndTurnOperation$$DecreaseAbilityCooldowns`) ;
  2. boucle `GetAllUnits` : `IdunBattle.Operations.EndTurnOperation$$RemoveOneTurnOnShields`
     + `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetThisTurn` ;
  3. meme `+0x5c += 1` sur la Machine of War du joueur (`PlayerComponent+0x78`) ;
  4. **si `IdunBattle.Entities.Components.TurnComponent$$HasActivePlayer`** : appel du slot 0x51 avec
     le litteral `0x17` = `Core.Services.OperationProcessor$$EvaluateAbilities` -> le vecteur ;
  5. **`IdunBattle.Operations.EndTurnOperation$$RefreshEffects`** -- le bloc de l'appel `0x17` tombe en
     FALL-THROUGH sur celui-ci, et la branche `HasActivePlayer == 0` saute DIRECTEMENT ici en enjambant
     le vecteur. Les deux lectures donnent le meme ordre : vecteur PUIS tick.

Le port faisait l'inverse (tick d'abord). CONSEQUENCE EXACTE, et c'est ce que ces tests gardent :
**les gates des triggers `On(0x17)` doivent voir l'etat PRE-tick** -- un effet a duree qui s'eteint a
cette fin de tour est encore ACTIF quand ils s'evaluent, et un effet POSE par un de ces triggers est
soumis au tick du meme tour.

Ce que `RefreshEffects` fait -- et ce qu'il ne fait PAS : le natif y boucle sur les entites-effet,
gate `!Removed@+0x5f && HasTurns@+0x5d`, appelle
`IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn`, emet deux events (0x16/0x15), puis
appelle `Core.Services.OperationProcessor$$RefreshEffects` ->
`IdunBattle.Operations.RefreshEffectsOperation$$Execute` (branche de retrait). **Aucun degat n'y est
inflige** : l'idee d'un « DoT qui entame les PV du porteur au tick de fin de tour » ne correspond a
rien dans ce corps -- les DoT de tuile passent par les events 0x12/0x14 de `StartTurnOperation`.

DEUX SONDES SYMETRIQUES, aucune ne touche au code de production (meme patron que `CountingRng`) :

  * `ProbeRng` : au PREMIER tirage PRNG (= le `Maybe` du vecteur `On(0x17)` de PileIn), capture l'etat
    de l'effet-temoin. Ordre natif -> le temoin a duree 1 est ENCORE ACTIF. Ordre d'avant -> il est
    deja `consumed`, `remaining_turns == 0`.
  * `ProbeEffects` : au PREMIER `on_turn_end` (= le tick), capture le nombre de tirages deja consommes
    et le cardinal d'entites du `State`. Ordre natif -> `rolls >= 1` (le vecteur a tire). Ordre
    d'avant -> `rolls == 0`.

INVENTAIRE des consommateurs de ce vecteur (re-derive des registres par
`probe_n8b_turnend_consumers.py`, pas cite d'un commentaire) : `RadSaturationAbility` (dispatch
generique `ABILITY_TRIGGERS`, gate `NOT HasFlag(owner, Moved)`) et le bespoke `PileIn`
(`OwnerHasFinishedMinTurns(2) & IsUnitWithStatAmount(Health Cur == Max)`). AUCUN des deux ne lit un
effet dans son gate -> le deplacement ne change le VERDICT d'aucun d'eux aujourd'hui, et c'est
precisement ce que le volet non-regression ci-dessous verifie (tirages et repliques INCHANGES).

ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from engine.entities.effects.base import BaseEffect
from engine.entities.effects_state import EffectsState
from engine.runner.components import UnitComponent
from engine.runner.operations.turnflow import EndTurnOperation

from ._pilein_owner_turns import (BOARD, CARRIER, ENEMY, ESCORT, CountingRng, GROT_VISUAL,
                                  minimal_pilein_state, pilein_units, drive_and_attack)

PYDIR = Path(__file__).resolve().parents[3]
ROOT = PYDIR.parents[1]

WITNESS_TYPE = 999_001      # type d'effet-TEMOIN, hors de tout registre porte (aucun trigger, aucun
                            # stat-mod) : il ne sert qu'a dater le tick. Ce n'est PAS un effet du jeu.


class ProbeRng(CountingRng):
    """`CountingRng` + capture de l'etat de l'effet-temoin au PREMIER tirage. Le premier `genrand_int32`
    d'un `EndTurn` est celui du `Maybe` du vecteur `On(0x17)` (le tick d'effets, lui, ne tire jamais)."""

    def __init__(self, seed=None):
        super().__init__(seed)
        self.witness_at_first_roll = None       # {"consumed": bool, "remaining": int|None} ou None

    def observe(self, effects_state, unit_id):
        self._src = (effects_state, int(unit_id))

    def genrand_int32(self) -> int:
        if self.witness_at_first_roll is None and getattr(self, "_src", None) is not None:
            es, uid = self._src
            for e in es.by_unit.get(uid, []):
                if e.effect_type == WITNESS_TYPE:
                    self.witness_at_first_roll = {"consumed": bool(e.consumed),
                                                  "remaining": e.remaining_turns}
                    break
        return super().genrand_int32()


class ProbeEffects(EffectsState):
    """`EffectsState` + capture, au PREMIER `on_turn_end` (le tick de duree), de l'etat d'avancement
    du reste de l'operation : tirages PRNG deja consommes et cardinal d'entites du `State`."""

    def bind(self, rng, state):
        self._rng = rng
        self._state = state
        self.at_first_tick = None
        return self

    def on_turn_end(self, unit_id: int, attacked: bool, state=None) -> list:
        if getattr(self, "at_first_tick", None) is None:
            self.at_first_tick = {"rolls": int(getattr(self._rng, "rolls", 0)),
                                  "entities": len(self._state.entities)}
        # `state` RELAYE (#936-r1) : sans lui la sonde re-fabriquerait le repli `consumed = True` et
        # l'echeance redeviendrait muette SOUS la sonde seulement -- un faux vert par instrumentation.
        return super().on_turn_end(unit_id, attacked, state)


def _witness_state(rng, turns_finished=5, remaining=1, n_grots=1):
    """Plateau minimal PileIn (gate d'age OUVERT) + un effet-TEMOIN a duree `remaining` sur le grot.
    Sonde d'effets branchee, RNG branche sur le temoin."""
    st = minimal_pilein_state(n_grots=n_grots, turns_finished=turns_finished, rng=rng)
    st.effects = ProbeEffects().bind(rng, st)
    for i in range(n_grots):
        st.effects.by_unit[100 + i] = [BaseEffect(name="OrderWitness", effect_type=WITNESS_TYPE,
                                                  remaining_turns=int(remaining), target=100 + i)]
    if hasattr(rng, "observe"):
        rng.observe(st.effects, 100)
    return st


# ------------------------------------------------------- (1) le vecteur voit l'etat PRE-tick

def test_turnend_vector_sees_effects_before_the_duration_tick():
    """SONDE `ProbeRng` : au moment ou le `Maybe` du vecteur `On(0x17)` tire, l'effet-temoin a duree 1
    est ENCORE ACTIF. C'est l'enonce direct du natif (`RefreshEffects` vient APRES l'appel `0x17`).
    Avec l'ordre d'avant, le tick l'aurait deja marque `consumed` avec `remaining == 0`."""
    r = ProbeRng(4242)
    st = _witness_state(r, remaining=1)
    EndTurnOperation.execute(st, advance=False)
    assert r.rolls >= 1, "le vecteur `On(0x17)` n'a tire aucun `Maybe` : le montage ne mesure rien"
    seen = r.witness_at_first_roll
    assert seen is not None, "l'effet-temoin n'a pas ete observe au 1er tirage"
    assert seen["consumed"] is False, (
        "le vecteur `On(0x17)` a vu l'effet-temoin DEJA consomme -> `RefreshEffects` s'est execute "
        "AVANT le vecteur (%s)" % (seen,))
    assert seen["remaining"] == 1, (
        "le vecteur `On(0x17)` a vu l'effet-temoin a remaining=%s au lieu de 1 -> le tick de duree "
        "l'a precede (%s)" % (seen["remaining"], seen))


def test_witness_effect_is_still_ticked_by_the_same_endturn():
    """Le deplacement ne SUPPRIME pas le tick, il le DECALE : au retour d'`EndTurnOperation.execute`
    le temoin a bien perdu son tour et a ete retire (`ShouldBeRemoved` = `HasTurns && Duration == 0`)."""
    r = ProbeRng(4242)
    st = _witness_state(r, remaining=1)
    res = EndTurnOperation.execute(st, advance=False)
    w = st.effects.by_unit[100][0]
    assert 100 in (res.get("ticked") or []), "le porteur du temoin n'a pas ete ticke"
    assert w.remaining_turns == 0 and w.consumed, \
        "le temoin n'a pas ete ticke par ce meme EndTurn (remaining=%s consumed=%s)" % (
            w.remaining_turns, w.consumed)


# ------------------------------------------------------- (2) le tick voit le vecteur deja passe

@pytest.mark.parametrize("n_grots", [1, 3])
def test_duration_tick_runs_after_the_turnend_vector(n_grots):
    """SONDE `ProbeEffects` : au 1er `on_turn_end`, le `Maybe` du vecteur a DEJA consomme ses tirages
    (1 par grot eligible). Observable RECIPROQUE du test precedent, et le plus direct : avec l'ordre
    d'avant, le tick voyait `rolls == 0`."""
    r = ProbeRng(4242)
    st = _witness_state(r, n_grots=n_grots)
    EndTurnOperation.execute(st, advance=False)
    at = st.effects.at_first_tick
    assert at is not None, "aucun tick de duree n'a eu lieu : le montage ne mesure rien"
    assert at["rolls"] == n_grots, (
        "le tick de duree a vu %d tirage(s) alors que le vecteur `On(0x17)` en consomme %d "
        "(1 `Maybe` par grot eligible) -> le tick a precede le vecteur" % (at["rolls"], n_grots))


def test_gate_closed_still_leaves_the_tick_last():
    """Contre-epreuve : gate d'age FERME (`turnsFinished` 0 -> 1 apres bump, < 2) -> aucun tirage.
    L'ordre n'est alors plus observable par le PRNG, mais le tick doit rester le DERNIER acte
    (le temoin est encore intact quand le vecteur passe -- il n'y a juste rien a mesurer)."""
    r = ProbeRng(4242)
    st = _witness_state(r, turns_finished=0)
    EndTurnOperation.execute(st, advance=False)
    assert r.rolls == 0, "%d tirage(s) alors que le gate d'age est ferme" % r.rolls
    assert st.effects.at_first_tick == {"rolls": 0, "entities": 3}, \
        "cardinal/tirages inattendus au tick (%s)" % (st.effects.at_first_tick,)


# ------------------------------------------------------- (3) NON-REGRESSION : verdicts inchanges

@pytest.mark.parametrize("turns_finished,expected", [(0, 0), (1, 1), (5, 1)])
def test_pilein_gate_verdict_unchanged_by_the_reordering(turns_finished, expected):
    """Le deplacement ne doit RIEN changer au verdict de PileIn : ni son gate d'age, ni sa
    consommation PRNG. Les deux consommateurs portes du vecteur (`PileIn`, `RadSaturationAbility`)
    ont des gates qui ne lisent AUCUN effet -- l'inventaire est re-derive par
    `probe_n8b_turnend_consumers.py`. Ce test est le garde-fou de cette affirmation."""
    r = ProbeRng(4242)
    st = _witness_state(r, turns_finished=turns_finished)
    EndTurnOperation.execute(st, advance=False)
    assert r.rolls == expected, \
        "turnsFinished %d -> %d tirage(s), attendu %d" % (turns_finished, r.rolls, expected)


def test_deep_strike_landing_is_not_cancelled_by_the_tick():
    """L'ORDRE que ce test protege est INCHANGE : l'atterrissage deep-strike doit passer AVANT le
    tick de duree. Sinon le tick consommerait l'instance de `TeleportStrike_TeleportingIn` et
    l'atterrissage serait un no-op silencieux (passives deferrees jamais initialisees).

    ⚠ #448-r2 en a change le VEHICULE, pas l'ordre : `EndTurnOperation` n'appelle plus une boucle
    bespoke `land_deep_strike` mais emet la jambe `On(0x28 = UnitFinishedTurn)` du
    `FinishUnitTurn(unit, false)` que le natif fait ICI, par unite possedee -- et c'est le 3e
    trigger d'`ATeleportingEffect` (`On(0x28 = UnitFinishedTurn) & OwnerIsActor & HasTile(Owner)`) qui retire l'effet.
    Deux consequences sur le MONTAGE, toutes deux natives :
      * le porteur doit AVOIR UNE TUILE (`HasTile(Owner)`) -> on lui pose une `PositionComponent` ;
      * le payload de `res["landed"]` est desormais celui du trigger, pas celui de
        `land_deep_strike`."""
    from engine.runner.components import PositionComponent
    from engine.runner.operations.spawn import TELEPORT_STRIKE_TELEPORTING_IN
    r = ProbeRng(4242)
    st = _witness_state(r, turns_finished=0)
    st.get_entity(200).add_component(PositionComponent(0, 0))   # `HasTile(Owner)` du gate natif
    st.effects.by_unit[200] = [BaseEffect(name="TeleportStrike_TeleportingIn",
                                          effect_type=TELEPORT_STRIKE_TELEPORTING_IN,
                                          remaining_turns=1, target=200)]
    res = EndTurnOperation.execute(st, advance=False)
    assert [x for x in (res.get("landed") or [])
            if x.get("owner") == 200 and x.get("effect") == TELEPORT_STRIKE_TELEPORTING_IN], \
        "l'atterrissage deep-strike n'a pas eu lieu : le tick l'a precede (%s)" % (res.get("landed"),)
    assert not [e for e in st.effects.by_unit.get(200, [])
                if not e.consumed and e.effect_type == TELEPORT_STRIKE_TELEPORTING_IN]


# ------------------------------------------------------- (4) LIVE : la replique existe avant le tick

def test_replica_exists_before_the_tick_live(rpc):
    """LIVE. Sur un vrai runner (donc avec un BOARD, seul cas ou `execute_pilein_replica` spawne
    reellement), on verifie le TROISIEME observable : au moment du tick de duree, la replique PileIn
    est DEJA dans le `State`. Deux observables couplees en un point (`rolls` et `entities`).

    Le grot est amene par `orksRuntherd` (passif `SquigHound`), seule voie d'entree d'un porteur de
    `PileIn` (`orksNpc1Grot` est `kind=summons`, hors `--list-pool`)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state

    sf = ROOT / "logs" / "runners" / ("endturn-order-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777", "--state-file", str(sf),
         "--board", BOARD, "--roster", "1", "--p-units", "%s,%s" % (CARRIER, ESCORT),
         "--a-units", "%s,%s" % (ENEMY, ENEMY), "--hp-target", "90000", "--hp-player", "90000",
         "--no-ai"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        pytest.skip("build KO: " + (proc.stderr or proc.stdout or "")[-300:])
    rid = json.loads(sf.read_text())["runnerId"]
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        me = next((u for u in (dv.get("units") or []) if u.get("visualId") == CARRIER), None)
        if me is None:
            pytest.skip("%s absent du runner" % CARRIER)
        mine = me["owner"]
        for _ in range(8):
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
            if dv.get("currentPlayer") != mine:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            if pilein_units(dv, mine):
                break
            if not drive_and_attack(rpc, rid, board, mine):
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        grots = pilein_units(dv, mine)
        if not grots:
            pytest.skip("aucun grot PileIn amene en bataille")
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)

        # Cherche un seed PRNG ou le `Maybe` REUSSIT (donc ou une replique est reellement spawnee) :
        # c'est la seule configuration ou le cardinal d'entites separe les deux ordres.
        for seed in range(64):
            r = ProbeRng(seed)
            st = load_state(dv, ob, snap, board=board)
            st.rng = r
            probe = ProbeEffects().bind(r, st)
            probe.by_unit = dict(st.effects.by_unit) if st.effects is not None else {}
            st.effects = probe
            st.current_player_id = mine
            for g in grots:
                e = st.get_entity(g)
                uc = e.get_component(UnitComponent) if e is not None else None
                if uc is not None:
                    uc.turns_finished = 5           # gate d'age OUVERT quel que soit l'age reel du
                                                    # grot (ecrase le seed `load_state` de #234)
            before = len(st.entities)
            res = EndTurnOperation.execute(st, advance=False)
            spawned = sum(len(o.get("spawned") or ()) for o in (res.get("pilein") or [])
                          if isinstance(o, dict) and "grot" in o)
            if spawned:
                at = probe.at_first_tick
                assert at is not None, "aucun tick de duree (seed %d)" % seed
                assert at["rolls"] >= 1, (
                    "seed %d : le tick de duree a vu %d tirage -> il a precede le vecteur `On(0x17)`"
                    % (seed, at["rolls"]))
                assert at["entities"] == before + spawned, (
                    "seed %d : au tick de duree le `State` porte %d entites, attendu %d "
                    "(%d avant + %d replique(s)) -> la replique n'existait pas encore, donc le tick "
                    "a precede le vecteur" % (seed, at["entities"], before + spawned, before, spawned))
                return
        pytest.skip("aucun seed sur 64 n'a produit de replique PileIn (le `Maybe` a toujours echoue)")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        sf.unlink(missing_ok=True)
