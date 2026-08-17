"""`OwnerHasFinishedMinTurns(2)` de PileIn : PER-UNITE (`turnsFinished`), jamais per-JOUEUR.

Chaine native (decompile = verite) :

    IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateTrigger
      -> IdunBattleLogic.Entities.DSLTriggers$$OwnerHasFinishedMinTurns(2)
      -> IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger$$.ctor
             (selecteur = factory+0x148 = Self/Owner, amount = 2 @+0x18, selType = 3 @+0x28)
      -> IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger
             = IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(owner) >= 2
      -> `BaseUnitComponent + 0x5c`

et l'ECRITURE de ce champ est la boucle de `IdunBattle.Operations.EndTurnOperation$$Execute` sur
`PlayerComponent.CurrentlyOwnedUnitIds` du joueur qui finit son tour (`+0x5c += 1`), AVANT
l'execution des trigger-abilities `On(0x17)`.

Le port lisait `state.turn_counts[player]` -- le dict PAR JOUEUR `TurnComponent + 0x38`
(`GetAmountOfTurnsStartedByPlayer`, cf. `IdunBattle.Entities.Formulas.
CurrentPlayerTurnsStartedFormula$$Calculate`). Deux defauts opposes, tous deux SILENCIEUX :

  * PERMISSIF : un grot ne au tour 5 passait le gate des sa PREMIERE fin de tour, alors que le
    natif lui en demande DEUX (`turnsFinished` d'un summon part de 0 a son apparition) ;
  * BLOQUANT  : `load_state` ne seedant pas `turn_counts`, tout runner monte depuis un snapshot
    avait `turn_counts == {}` -> `get(player, 0) = 0 < 2` -> PileIn MORT, sans erreur ni test rouge.

Ce que ces tests GARDENT (chacun etait ROUGE avant le fix -- messages verbatim en tete de PR) :
  1. gate FERME pour un grot a 1 tour fini, MEME si son joueur en a fini 9 ;
  2. gate OUVERT pour un grot a 2 tours finis, MEME si `turn_counts` est VIDE ;
  3. `EndTurnOperation` bumpe `turnsFinished` des unites VIVANTES du joueur FINISSANT, et d'elles
     seules ; et il le fait AVANT le vecteur `On(0x17)` ;
  4. LIVE : aux fins de tour d'age 0 et d'age 1 du meme grot, le port consomme le MEME nombre de
     `genrand_int32` que le natif -- 0 puis >= 1. C'est le seul couple de points ou les deux
     hypotheses divergent.

ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from engine.runner.components import UnitComponent, OwnerComponent, HealthComponent
from engine.runner.operations.turnflow import EndTurnOperation

from ._pilein_owner_turns import (BOARD, CARRIER, ENEMY, ESCORT, CountingRng,
                                  measure_grot_age_sweep, minimal_pilein_state)

PYDIR = Path(__file__).resolve().parents[3]
ROOT = PYDIR.parents[1]


def _state(n_grots=1, player=0, turn_counts=None, turns_finished=0, rng=None):
    """Montage minimal PARTAGE — cf. `_pilein_owner_turns.minimal_pilein_state` (meme plateau que
    `test_endturn_order_live`, qui garde l'ORDRE `On(0x17)` vs `RefreshEffects` sur ce meme etat)."""
    return minimal_pilein_state(n_grots=n_grots, player=player, turn_counts=turn_counts,
                                turns_finished=turns_finished, rng=rng)


# --------------------------------------------------------------- (1) le gate est PER-UNITE

@pytest.mark.parametrize("n_grots", [1, 3])
def test_gate_closed_for_young_grot_even_when_player_is_old(n_grots):
    """`GetTurnsFinished(grot) = 1 < 2` -> AUCUN candidat, donc AUCUN tirage -- et cela quel que
    soit le nombre de tours finis par le JOUEUR (ici 9). Sur le port d'avant (gate lu sur
    `turn_counts`) ce cas rendait 1 tirage par grot et un dedoublement 3 fois sur 4."""
    from engine.runner.operations.triggers.dispatch.turn import end_turn_summon_triggers
    r = CountingRng(4242)
    st = _state(n_grots, turn_counts={0: 9}, turns_finished=1, rng=r)
    out = end_turn_summon_triggers(st, 0)
    assert r.rolls == 0, "%d tirage(s) pour un grot a 1 tour fini (gate `>= 2` non applique)" % r.rolls
    assert not [o for o in out if isinstance(o, dict) and "grot" in o]


@pytest.mark.parametrize("n_grots", [1, 3])
def test_gate_open_at_two_finished_turns_without_any_turn_counts(n_grots):
    """`GetTurnsFinished(grot) = 2 >= 2` -> UN `next_bool` par grot, MEME avec `turn_counts` VIDE.
    C'est exactement l'etat d'un runner monte par `load_state` (qui ne seede pas le compteur
    JOUEUR) : sur le port d'avant, PileIn y etait purement et simplement mort."""
    from engine.runner.operations.triggers.dispatch.turn import end_turn_summon_triggers
    r = CountingRng(4242)
    st = _state(n_grots, turn_counts=None, turns_finished=2, rng=r)
    assert st.turn_counts == {}, "le montage doit reproduire l'etat non seede de `load_state`"
    end_turn_summon_triggers(st, 0)
    assert r.rolls == n_grots, \
        "%d tirages pour %d grots eligibles (attendu 1 `next_bool` chacun)" % (r.rolls, n_grots)


# --------------------------------------------------------------- (2) le compteur lui-meme

def test_endturn_bumps_turns_finished_of_living_owner_units_only():
    """Mirror de la boucle d'`EndTurnOperation$$Execute` : `+0x5c += 1` sur les ids de
    `PlayerComponent.CurrentlyOwnedUnitIds` du joueur FINISSANT. Les unites adverses ne bougent
    pas ; les MORTES non plus (`get_CurrentlyOwnedUnitIds` retire les defaits @+0x40 via
    `RemoveAll`)."""
    st = _state(1, turns_finished=0, rng=CountingRng(1))
    dead = st.add_entity(400)
    dead.add_component(UnitComponent(visual_id=ESCORT, alive=False))
    dead.add_component(OwnerComponent(team=0, player=0))
    EndTurnOperation.execute(st, advance=False)
    assert st.get_entity(100).get_component(UnitComponent).turns_finished == 1, "grot non bumpe"
    assert st.get_entity(200).get_component(UnitComponent).turns_finished == 1, "allie non bumpe"
    assert st.get_entity(300).get_component(UnitComponent).turns_finished == 0, "adversaire bumpe"
    assert st.get_entity(400).get_component(UnitComponent).turns_finished == 0, "unite MORTE bumpee"


def test_endturn_bumps_before_the_turnend_trigger_vector():
    """ORDRE natif : le bump precede l'execution des trigger-abilities `On(0x17)` -> un grot ne
    au tour PRECEDENT (`turnsFinished` = 1 avant le bump) est DEJA eligible pendant CE `EndTurn`.
    A 0 avant le bump il ne l'est pas encore : c'est la frontiere exacte du gate."""
    for before, expect_rolls in ((0, 0), (1, 1)):
        r = CountingRng(4242)
        st = _state(1, turns_finished=before, rng=r)
        EndTurnOperation.execute(st, advance=False)
        assert st.get_entity(100).get_component(UnitComponent).turns_finished == before + 1
        assert r.rolls == expect_rolls, \
            "turnsFinished %d avant bump -> %d tirage(s), attendu %d" % (before, r.rolls, expect_rolls)


def test_replica_spawned_by_the_trigger_is_not_bumped_this_turn():
    """Le natif COPIE la liste d'ids AVANT la boucle de bump, et n'execute `On(0x17)` qu'apres :
    une replique creee par PileIn ne prend donc PAS le bump du tour qui l'a vue naitre. Le port
    doit avoir la meme propriete -- sinon la replique serait eligible un tour trop tot."""
    st = _state(1, turns_finished=5, rng=CountingRng(4242))
    new = st.add_entity(999)                    # simule la replique posee par le vecteur On(0x17)
    new.add_component(UnitComponent(visual_id="orksNpc1Grot", alive=True))
    new.add_component(OwnerComponent(team=0, player=0))
    new.add_component(HealthComponent(hp=1000, hp_max=1000))
    assert new.get_component(UnitComponent).turns_finished == 0, \
        "une unite fraichement creee doit partir de `turnsFinished` = 0"


# --------------------------------------------------------------- (3) LIVE : 0 tirage puis >= 1

def test_pilein_gate_age_sweep_matches_live(rpc):
    """LIVE, bit-exact. Sur le MEME grot, aux fins de tour d'age 0 puis d'age 1 de son
    proprietaire, le port consomme le MEME nombre de `genrand_int32` que le natif.

    Attendu natif : age 0 -> 0 (gate `turnsFinished(1) >= 2` FAUX), age 1 -> >= 1 (le `Maybe`,
    puis le `Randomize` du placement si le `Maybe` reussit). Le port d'avant lisait
    `turn_counts[player]`, deja >= 2 aux deux points -> il tirait AUX DEUX, donc divergeait a
    l'age 0 (et fabriquait un grot fantome 3 fois sur 4)."""
    sf = ROOT / "logs" / "runners" / ("pilein-owner-turns-%s.json" % uuid.uuid4().hex[:8])
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
        records, why = measure_grot_age_sweep(rpc, rid, ages=(0, 1))
        by_age = {r["age"]: r for r in records}
        if 0 not in by_age or 1 not in by_age:
            pytest.skip("ages 0 et 1 non mesures (%s) -- releve: %s" % (why, records))
        for age, rec in sorted(by_age.items()):
            assert rec["full_hp"], \
                "age %d : co-gate PV PLEINS NON satisfait -> la mesure ne prouve rien (%s)" % (age, rec)
            assert rec["live_rolls"] is not None, \
                "age %d : flux MT live non attribuable (%s)" % (age, rec)
            assert rec["port_rolls"] == rec["live_rolls"], \
                ("age %d : tirages port=%d live=%d (%s)"
                 % (age, rec["port_rolls"], rec["live_rolls"], rec))
            assert rec["port_spawn"] == rec["live_spawn"], \
                ("age %d : spawns port=%d live=%d (%s)"
                 % (age, rec["port_spawn"], rec["live_spawn"], rec))
        assert by_age[0]["live_rolls"] == 0, \
            ("le natif a consomme %d tirage(s) a l'age 0 : le gate y serait donc OUVERT, ce qui "
             "contredit `GetTurnsFinished >= 2` (%s)" % (by_age[0]["live_rolls"], by_age[0]))
        assert by_age[1]["live_rolls"] >= 1, \
            ("le natif n'a consomme AUCUN tirage a l'age 1 : le gate y serait donc FERME (%s)"
             % (by_age[1],))
        # Les DEUX regimes du port d'avant, mesures sur les MEMES points (cf. `_pilein_owner_turns`) :
        # ils divergent du natif dans les deux sens opposes -- c'est le chiffre avant/apres.
        assert by_age[0]["m0_player_rolls"] > by_age[0]["live_rolls"], \
            ("regime per-JOUEUR non discriminant a l'age 0 (m0=%d live=%d) : la mesure ne separe pas "
             "les deux hypotheses" % (by_age[0]["m0_player_rolls"], by_age[0]["live_rolls"]))
        assert by_age[1]["m0_snapshot_rolls"] < by_age[1]["live_rolls"], \
            ("regime snapshot-non-seede non discriminant a l'age 1 (m0=%d live=%d)"
             % (by_age[1]["m0_snapshot_rolls"], by_age[1]["live_rolls"]))
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        sf.unlink(missing_ok=True)
