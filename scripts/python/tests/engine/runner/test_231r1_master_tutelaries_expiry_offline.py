"""#231-r1 -- le CYCLE DE VIE de `1197 MasterOfTheTutelaries`, donc celui de la triggered `1173`.

CE QUE CE FICHIER GARDE, et pourquoi il existe. Le residu `#231-r1` affirmait que << le port
PERSISTE la triggered 1173, le natif la RETIRE des la fin du cast >>, sur la base du releve live
de `case-546` Sec.6.2 :

    id=98 owner=81 ownerType=1 inOwnerList=False active=False removed=True beingRemoved=True
         hasTurns=True initial=1 remaining=0 timesApplied=1 parent=None subs=[] src=81

Ce releve est annonce POST-CAST. Or il porte `remaining = 0` avec `initial = 1`, et le decompile
etablit que **seul un tick de duree peut produire ce couple** :

  * `IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn` = `if (0 < Duration@+0x64)
    Duration -= 1` -- l'UNIQUE ecrivain decroissant, enfile par
    `IdunBattle.Operations.EndTurnOperation$$RefreshEffects` ;
  * `IdunBattle.Operations.RemoveEffectOperation$$Execute` (le retrait) ecrit `+0x5e = 1`
    (beingRemoved), retire l'id des listes, puis `+0x5c = 0` (IsActive) et `+0x5f = 1` (Removed) --
    il **n'ecrit JAMAIS `Duration`**. Un retrait sans tick aurait donc laisse `remaining = 1`.

=> le releve est POST-TICK, c'est-a-dire apres un `EndTurn`. La comparaison qui fondait le residu
opposait un etat natif POST-end-turn a un etat port PRE-end-turn : les deux moteurs ne divergent
pas sur ce cycle. Ce fichier FIGE la coincidence, pour qu'une regression du tick (ou du gate) la
fasse rougir.

CE QU'IL NE COUVRE PAS, et c'est nomme : la fenetre INTRA-TOUR (entre la pose et le premier
`EndTurn`). `case-546` Sec.8 dit lui-meme que << la fenetre temporelle pendant le cast de 1197
n'est pas observee >>. Si le natif retirait l'effet plus tot, le port sur-accorderait sur cette
seule fenetre -- il faudrait un releve `effectsAll --effectType 1197` pris AVANT tout end-turn
pour trancher, et c'est un montage live, pas un test offline.
"""
from __future__ import annotations

from engine.entities.effect_type import EffectType
from engine.entities.effects.factory import EffectFactory
from engine.entities.effects_state import EffectsState
from engine.runner.operations.triggers.loki import master_of_the_tutelaries as MOT

OWNER = 81
MASTER = int(EffectType.MasterOfTheTutelaries)          # 1197 (0x4ad)


def _state_with_master_effect(remaining: int):
    """L'etat minimal que le gate lit : une `EffectsState` portant UNE instance de `1197`.

    `remaining = 1` est la duree que pose l'arbre natif -- le noeud `<dsl+0xc0>` = `Direct(1)`,
    passe tel quel a `IdunBattle.Operations.AddEffectOperation$$Execute` (pas de
    `TurnsFromRounds`), soit **1 TOUR** (cf. `runner/abilities/loki/summon.py::
    master_of_the_tutelaries_tree`)."""
    class _S:
        pass
    st = _S()
    st.effects = EffectsState()
    eff = EffectFactory.create({"name": "MasterOfTheTutelaries", "effectType": MASTER,
                                "level": 1, "remaining": remaining, "source": OWNER,
                                "active": True})
    eff.target = OWNER
    st.effects.add_effect(OWNER, eff)
    return st, eff


def test_le_gate_de_1173_est_OUVERT_tant_que_1197_n_a_pas_tique():
    """Etage 1 -- temoin NON NUL. Sans lui, l'etage 2 pourrait etre vert par vacuite (un gate
    toujours faux passerait le test de fermeture sans rien prouver)."""
    st, eff = _state_with_master_effect(remaining=1)
    assert MOT._master_effect_is_carried_and_active(st, OWNER) is True, (
        "temoin NON NUL absent : le gate doit etre OUVERT juste apres la pose "
        "(remaining=%r consumed=%r active=%r)" % (eff.remaining_turns, eff.consumed, eff.active))


def test_le_tick_de_fin_de_tour_FERME_le_gate_de_1173():
    """Etage 2 -- LA coincidence. `EndTurnOperation$$RefreshEffects` -> `RemoveOneTurn` amene
    `Duration` a 0, `EffectComponent$$ShouldBeRemoved` (`HasTurns && Duration == 0`) devient vrai,
    l'entite-effet est retiree -> `RevertInternal` -> `RemoveTriggeredAbility(0x495 = 1173)`.
    Cote port : `EffectsState.on_turn_end` pose `consumed`, que `_master_of_tutelaries_instances`
    filtre."""
    st, eff = _state_with_master_effect(remaining=1)
    st.effects.on_turn_end(OWNER, attacked=False)
    assert eff.remaining_turns == 0, "RemoveOneTurn : 1 -> 0 (decrement CLAMPE)"
    assert eff.consumed is True, "ShouldBeRemoved -> retrait de l'entite-effet"
    assert MOT._master_effect_is_carried_and_active(st, OWNER) is False, (
        "le gate de 1173 doit etre FERME apres le tick : le natif a joue "
        "RemoveTriggeredAbility(0x495), le port doit cesser de collecter le trigger")


def test_le_gate_reste_ferme_aux_tours_suivants():
    """Etage 3 -- << tour apres tour >>, la formulation exacte du residu. Un second tick ne doit
    pas rouvrir le gate (ni le decrement clampe ni la cascade ne ressuscitent l'instance)."""
    st, _ = _state_with_master_effect(remaining=1)
    st.effects.on_turn_end(OWNER, attacked=False)
    st.effects.on_turn_end(OWNER, attacked=False)
    assert MOT._master_effect_is_carried_and_active(st, OWNER) is False


def test_une_instance_PERMANENTE_ne_tique_pas():
    """Etage 4 -- le contre-bras du gate natif `!Removed@+0x5f && HasTurns@+0x5d`. Une instance
    SANS timer (`remaining_turns is None`, `HasTurns` faux) n'est jamais retiree par le tick.
    Ce n'est pas le regime de `1197` (qui a `hasTurns=True`, mesure `case-546` Sec.6.2) : c'est ce
    qui etablit que l'etage 2 mesure bien le TIMER et pas un retrait inconditionnel."""
    st, eff = _state_with_master_effect(remaining=None)
    assert eff.remaining_turns is None
    st.effects.on_turn_end(OWNER, attacked=False)
    assert MOT._master_effect_is_carried_and_active(st, OWNER) is True
