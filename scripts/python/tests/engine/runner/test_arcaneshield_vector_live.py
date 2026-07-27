"""ArcaneShield (thousSorcerer/Thaumachus) — VECTEUR d'activation et FORMULE DE TRI de la cible.

Ce fichier garde les deux faces que le residu N1 avait laissees fausses, et il les garde SEPAREMENT :

1. VECTEUR. `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$CreateTrigger` =
   `On(0x1c, ownerNeedsToBeAlive=1) & get_OwnerIsActor & get_OwnerIsCaster` — `0x1c = 28 =
   EventTriggerType.ArrivedAtFinalTile`, PAS `On(4 = UnitAfterMove)`. Les deux emetteurs natifs de cet
   event sont gardes par le MEME flag `UnitFlag.ArrivedAtFinalTile` :
     * `IdunBattle.Operations.MoveUnitOperation$$Execute` (apres `EvaluateAfterMoveTriggers`),
     * `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` (gate `newly_arrived and not forced`).
   => AU PLUS UN fire par activation. Les deux cas testes ici sont donc SYMETRIQUES :
     (a) l'owner bouge PUIS finit son tour  -> le bouclier est accorde UNE fois, pas deux ;
     (b) l'owner finit son tour SANS bouger -> le bouclier est accorde.
   Le cas (b) etait ROUGE avant le recablage (le port ecoutait `On(4)`, qu'un tour sans deplacement
   n'emet jamais).

2. FORMULE DE TRI. `...ArcaneShieldAbility$$CreateBehaviour` classe les candidats par
   `Sum($$Distance, $$Faction, $$Chaos, $$Owner)` trie ASCENDANT — un SCORE ADDITIF ou la distance pese
   3 par hex et ou faction / trait Chaos ne pesent que 1 chacun. Ce n'est PAS un ordre lexicographique
   << faction d'abord >>. Le montage `arcaneshield_stage` existe pour rendre cette difference
   OBSERVABLE : un ami NON-Chaos a distance 1 (score 5) doit battre un ami de la MEME faction a
   distance 2 (score 6).

ORACLES. Le MONTANT et la DUREE se confrontent au live (`ability_var` sur le gameconfig live,
`convert_rounds_to_turns` sur le nombre de joueurs de la bataille montee) — jamais une constante gravee.
Le CLASSEMENT, lui, a pour oracle le DECOMPILE : le natif n'expose nulle part le score qu'il a calcule,
donc chaque attente est ecrite en RE-DERIVANT la formule (`_score`), pas en recopiant un resultat.

Montage : fixture `arcaneshield_stage` (`tests/conftest.py` -> `_arcane_shield_stage.py`). ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _arcane_shield_stage import FRIEND_ROLES, ROLE_VIS      # noqa: E402

from engine.runner.abilities.base import convert_rounds_to_turns
from engine.runner.components import ShieldComponent, StatsComponent
from engine.runner.operations import triggers as T
from engine.runner.operations.turnflow import FinishUnitTurnOperation
from engine.runner.operations.triggers.loki.arcane_shield import (
    ARCANESHIELD_DISTANCE_WEIGHT, ARCANESHIELD_OWNER_PENALTY_OFFSET, _arcaneshield_range)


def _shield_total(state, uid):
    e = state.get_entity(uid)
    shc = e.get_component(ShieldComponent) if e is not None else None
    return shc.get_total_shield() if shc is not None else 0


def _expected_amount(state, owner_id):
    """Oracle du MONTANT = `ConfigVar(0x27 = shieldHp)` sur le gameconfig LIVE, au niveau de PASSIVE
    reellement porte par l'unite montee (et non une valeur gravee dans le test)."""
    from engine.entities.effects.magnitude import ability_var
    sc = state.get_entity(owner_id).get_component(StatsComponent)
    if sc is None:
        return 0
    ctx = sc.ctx
    return int(ability_var("ArcaneShield", "shieldHp",
                           int(getattr(ctx, "passive_ability_level", 0) or 0),
                           multiplier_pct=int(getattr(ctx, "ability_variables_multiplier", 100) or 100)) or 0)


def _score(role: str, dist: int, rng: int) -> int:
    """RE-DERIVATION de `Sum($$Distance, $$Faction, $$Chaos, $$Owner)` a partir du DECOMPILE, ecrite
    ici independamment du port (l'attente ne doit pas etre le code teste) :
        $$Distance = 3 * distance   |  $$Faction = 0 si meme faction que l'owner, 1 sinon
        $$Chaos    = 0 si le candidat a UnitTrait.Chaos (grande alliance Chaos), 1 sinon
        $$Owner    = 0 si le candidat n'est pas l'owner, range*3 + 4 sinon"""
    if role == "owner":
        return ARCANESHIELD_DISTANCE_WEIGHT * rng + ARCANESHIELD_OWNER_PENALTY_OFFSET
    faction = 0 if role == "same_faction" else 1
    chaos = 0 if role in ("same_faction", "other_chaos") else 1
    return ARCANESHIELD_DISTANCE_WEIGHT * int(dist) + faction + chaos


# ------------------------------------------------------------------ 1. VECTEUR `On(0x1c)`

def test_arcaneshield_granted_on_turn_end_without_moving(arcaneshield_stage):
    """(b) L'owner CLOT SON TOUR SANS AVOIR BOUGE -> le bouclier EST accorde.

    Mirror de `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` : `Add(ArrivedAtFinalTile=1)`
    puis publication d'`On(0x1c)` SSI le flag venait d'etre pose ET `!forced`. C'est LE cas que le
    vecteur `On(4=UnitAfterMove)` du port historique ne pouvait pas voir."""
    stage = arcaneshield_stage
    state = stage.load()
    amount = _expected_amount(state, stage.owner_id)
    if amount <= 0:
        pytest.skip("shieldHp indispo (config/level) -> montant non calculable")
    stage.place(state, {"same_faction": 1})          # un ami a portee : la cible sera lui

    before = _shield_total(state, stage.ids["same_faction"])
    res = FinishUnitTurnOperation.execute(state, stage.owner_id, forced=False)

    assert res.get("newly_arrived") is True, \
        "l'owner devait arriver au flag ArrivedAtFinalTile pour la 1re fois (etat de depart pollue ?)"
    grants = [g for g in (res.get("arrived_triggers") or []) if g.get("ability") == "ArcaneShield"]
    after = _shield_total(state, stage.ids["same_faction"])
    assert len(grants) == 1, (
        f"fin de tour SANS deplacement : ArcaneShield n'a PAS ete accorde "
        f"(grants={grants}, shield allie {before}->{after}). Le trigger natif est "
        f"On(0x1c=ArrivedAtFinalTile), emis par FinishUnitTurnOperation$$Execute quand l'unite n'a "
        f"pas bouge -- un port route sur On(4=UnitAfterMove) rate ce cas.")
    assert grants[0]["target"] == stage.ids["same_faction"], \
        f"cible {grants[0]['target']} != ami a portee {stage.ids['same_faction']}"
    assert grants[0]["amount"] == amount, f"montant {grants[0]['amount']} != shieldHp live {amount}"
    exp_dur = convert_rounds_to_turns(state, 1)
    assert grants[0]["remaining"] == exp_dur, \
        f"duree {grants[0]['remaining']} != ConvertRoundsToTurns(TurnsFromRounds(1))={exp_dur}"
    assert after == before + amount, f"shield_total allie {before}->{after} != +{amount}"
    print(f"[VECTEUR fin-de-tour] OK : bouclier {amount} ({exp_dur} tours) sur "
          f"{ROLE_VIS['same_faction']}, total {before}->{after}")


def test_arcaneshield_fires_once_when_owner_moves_then_ends_turn(arcaneshield_stage):
    """(a) L'owner BOUGE puis clot son tour -> le bouclier est accorde UNE SEULE FOIS.

    Le gate est le flag `UnitFlag.ArrivedAtFinalTile`, pose par le PREMIER des deux emetteurs et lu par
    le second (`UnitFlagsComponent.Add` rend false -> pas de second `On(0x1c)`). Une double pose se
    verrait au doublement du `shield_total` (`add_or_update_shield` cumule a source egale)."""
    stage = arcaneshield_stage
    state = stage.load()
    amount = _expected_amount(state, stage.owner_id)
    if amount <= 0:
        pytest.skip("shieldHp indispo (config/level) -> montant non calculable")
    stage.place(state, {"same_faction": 1})
    ally = stage.ids["same_faction"]

    before = _shield_total(state, ally)
    # Vecteur MOVE : exactement ce que `MovementHandler.visit_MoveUnitMessage` appelle apres
    # `MoveUnitOperation` -- `after_move_triggers` emet `On(0x1c)` EN QUEUE et pose le flag.
    moved = [g for g in T.after_move_triggers(state, stage.owner_id)
             if g.get("ability") == "ArcaneShield"]
    after_move = _shield_total(state, ally)
    assert len(moved) == 1, f"apres le move, ArcaneShield devait fire une fois (grants={moved})"
    assert after_move == before + amount, f"shield_total {before}->{after_move} != +{amount}"

    # Puis la CLOTURE du tour de la meme activation : le flag est deja pose -> AUCUN second event.
    res = FinishUnitTurnOperation.execute(state, stage.owner_id, forced=False)
    assert res.get("newly_arrived") is False, \
        "le move aurait du poser ArrivedAtFinalTile -> la cloture ne doit PAS le poser a nouveau"
    again = [g for g in (res.get("arrived_triggers") or []) if g.get("ability") == "ArcaneShield"]
    final = _shield_total(state, ally)
    assert not again, f"DOUBLE POSE : ArcaneShield a re-fire a la cloture du tour (grants={again})"
    assert final == after_move, (
        f"DOUBLE POSE : shield_total {after_move}->{final} apres la cloture "
        f"(attendu inchange -- On(0x1c) fire AU PLUS UNE FOIS par activation)")
    print(f"[VECTEUR move+cloture] OK : une seule pose de {amount}, total {before}->{final}")


def test_arcaneshield_not_granted_on_forced_turn_end(arcaneshield_stage):
    """`FinishUnitTurnOperation$$Execute` publie `On(0x1c)` sous `newly_arrived` **ET `!forced`**.

    La cloture FORCEE (l'unite n'a pas choisi de finir : `TURN_FINISHED_FORCED`) pose bien le flag
    mais N'EMET PAS l'event. Sans cette garde, un port qui ignorerait le `!forced` accorderait un
    bouclier a chaque fin de tour subie — et rien d'autre ne le verrait."""
    stage = arcaneshield_stage
    state = stage.load()
    stage.place(state, {"same_faction": 1})
    ally = stage.ids["same_faction"]
    before = _shield_total(state, ally)

    res = FinishUnitTurnOperation.execute(state, stage.owner_id, forced=True)

    assert res.get("newly_arrived") is True, "le flag ArrivedAtFinalTile devait etre pose meme forced"
    assert "arrived_triggers" not in res, \
        f"cloture FORCEE : aucun On(0x1c) ne doit etre publie (res={res})"
    after = _shield_total(state, ally)
    assert after == before, f"cloture FORCEE : shield_total {before}->{after} (attendu inchange)"
    print(f"[VECTEUR cloture forcee] OK : flag pose, aucun event, shield inchange ({before})")


# ------------------------------------------------- 2. FORMULE DE TRI : Sum(3*dist, faction, chaos)

@pytest.mark.parametrize("layout,winner,why", [
    # LE DISCRIMINANT DU LOT : la distance (poids 3) domine la faction (poids 1).
    ({"non_chaos": 1, "same_faction": 2, "other_chaos": 2}, "non_chaos",
     "non-Chaos a d=1 (5) bat meme-faction a d=2 (6) : un tri lexicographique choisirait l'inverse"),
    # A DISTANCE EGALE, la faction reprend la main -> le terme $$Faction n'est pas inerte.
    ({"non_chaos": 2, "same_faction": 2, "other_chaos": 2}, "same_faction",
     "a distance egale : meme faction (6) < autre Chaos (7) < non-Chaos (8)"),
    # A DISTANCE EGALE ENTRE DEUX NON-MEME-FACTION, c'est le trait Chaos qui departage.
    ({"other_chaos": 1, "non_chaos": 1, "same_faction": 2}, "other_chaos",
     "a d=1 : autre Chaos (4) bat non-Chaos (5) ; meme-faction a d=2 (6) est distance"),
])
def test_arcaneshield_target_is_additive_score(arcaneshield_stage, layout, winner, why):
    """`First(SortByFormula(pool, Sum($$Distance, $$Faction, $$Chaos, $$Owner), ascending=true), 1)`.

    Chaque cas isole UN terme de la somme. Les scores attendus sont RE-DERIVES du decompile par
    `_score` (le test ne recopie pas le code sous test) et affiches, pour que l'echec dise POURQUOI et
    pas seulement QUI."""
    stage = arcaneshield_stage
    state = stage.load()
    stage.place(state, layout)
    rng = _arcaneshield_range()

    scores = {r: _score(r, layout[r], rng) for r in layout}
    scores["owner"] = _score("owner", 0, rng)
    expected = min(scores, key=lambda r: (scores[r], r))
    assert expected == winner, (
        f"le cas de test est incoherent avec la formule re-derivee : "
        f"min={expected} mais le cas attend {winner} (scores={scores})")

    tgt = T._arcaneshield_target(state, stage.owner_id)
    got = next((r for r, uid in stage.ids.items() if uid == tgt), f"id={tgt}")
    assert tgt == stage.ids[winner], (
        f"cible {got} != {winner} ({ROLE_VIS[winner]}). {why}. "
        f"layout={layout} scores={scores}")
    print(f"[TRI {layout}] OK : cible = {winner} ({ROLE_VIS[winner]}), scores={scores}")


def test_arcaneshield_owner_is_always_last_resort(arcaneshield_stage):
    """`$$Owner = ConditionalAmount(NOT AreEqual(Caster, It), Zero, Get(range*3 + 4))`.

    La penalite du caster (`range*3 + 4`) est calibree pour depasser STRICTEMENT le pire score
    atteignable par un autre candidat (`3*range + 1 + 1`) : le caster est donc dernier des qu'un seul
    ami est a portee, et retenu des qu'aucun ne l'est. On verifie les DEUX moities, plus l'inegalite
    elle-meme -- c'est elle qui realise le << lastly casting it on himself >> sans aucun palier."""
    stage = arcaneshield_stage
    rng = _arcaneshield_range()
    worst_other = ARCANESHIELD_DISTANCE_WEIGHT * rng + 1 + 1
    owner_score = ARCANESHIELD_DISTANCE_WEIGHT * rng + ARCANESHIELD_OWNER_PENALTY_OFFSET
    assert owner_score > worst_other, (
        f"penalite owner {owner_score} <= pire score d'un autre candidat {worst_other} : "
        f"le caster ne serait plus le dernier recours")

    # (i) le PIRE ami possible (non-Chaos, a la distance maximale) passe quand meme devant le caster.
    state = stage.load()
    stage.place(state, {"non_chaos": rng})
    tgt = T._arcaneshield_target(state, stage.owner_id)
    assert tgt == stage.ids["non_chaos"], (
        f"cible {tgt} != non_chaos a d={rng} (score {_score('non_chaos', rng, rng)}) "
        f"alors que le caster vaut {owner_score}")

    # (ii) tous les amis HORS rayon -> le pool se reduit a `op_Addition Caster` -> le caster.
    state2 = stage.load()
    stage2_layout = {r: rng + 2 for r in FRIEND_ROLES}
    stage.place(state2, stage2_layout)
    tgt2 = T._arcaneshield_target(state2, stage.owner_id)
    assert tgt2 == stage.owner_id, \
        f"cible {tgt2} != owner {stage.owner_id} alors qu'aucun ami n'est dans le rayon {rng}"
    print(f"[OWNER dernier recours] OK : penalite {owner_score} > pire autre {worst_other} ; "
          f"fallback sur soi quand le rayon est vide")
