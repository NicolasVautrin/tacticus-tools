"""#1079 -- les trois fils de seeding CONFRONTES sur un `State` REEL, pas sur des doublures.

`tests/engine/test_1079_nccontext_seeding_offline.py` prouve que chaque etage se comporte comme le
decompile ; il ne prouve PAS que la CHAINE reelle transporte quoi que ce soit. Un champ pose sur
une doublure et jamais alimente sur du vrai passe le test offline en VERT -- c'est exactement le
vice #943-r8, et le tri-etat le rend d'autant plus invisible (`None`/`{}` sont des reponses
LEGITIMES, donc un transport mort ressemble a une mesure honnete).

Ce fichier monte une bataille et mesure la chaine complete :

    runner -> snapshot.load_state -> Scene.from_state -> state_bridge.build_from_state
           -> AiDecisionContext -> NCContext -> le gate

Le scenario de GENERALISATION est l'etage 3 : un plafond de rounds INJECTE dans le `State`. Aucun
runner `rl_duel build` n'en porte (la seed ne declare pas `MainPlayerRoundLimitation`), donc c'est
le SEUL regime ou le bras 2 de `BattleQuery$$HasMinimumRemainingTurns` est atteint -- et le seul ou
le fix CHANGE une decision observable.

ASCII only (console cp1252).
"""
from __future__ import annotations

import pytest

from engine.ai import state_bridge as SB
from engine.entities.victory_condition_type import VictoryConditionType
from engine.playbook.noncomparable import _base as NCB
from engine.playbook.noncomparable.duty_eternal import DutyEternalPlaybook
from engine.playbook.scene import Scene
from engine.runner import snapshot as SNAP
from engine.entities.pathfinding.board import Board
from engine.services import battle_query as SBQ

#: Cf. le fichier offline : ce que ce FICHIER garde peut changer si l'un de ces chemins bouge.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/ai/context.py",
        "scripts/python/engine/ai/state_bridge.py",
        "scripts/python/engine/playbook/noncomparable/_base.py",
        "scripts/python/engine/playbook/noncomparable/duty_eternal.py",
        "scripts/python/engine/playbook/scene.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/services/battle_query.py",
        "scripts/python/engine/services/victory_config.py",
        "data/seed-bc.json",
    ),
    "build": False,
    "toujours": False,
    "raison": (
        "Ce fichier ne garde qu'une chose : que la CHAINE reelle transporte les trois canaux "
        "seedes par #1079. Les chemins cites sont les maillons de cette chaine, du snapshot au "
        "gate. `data/seed-bc.json` y est parce que le defaut du plafond de rounds en est DERIVE "
        "et qu'aucun import ne le revele. Pas de `build` : rien ici ne lit le binaire -- les "
        "valeurs du decompile sont figees dans le fichier offline jumeau."
    ),
}

TURNS = 2   # le litteral `2` du call-site `<IBattleQuery slot 0x1b>(unit, 2)` -- un nb de TOURS


@pytest.fixture(scope="module")
def etat(rpc, build_runner):
    """Une bataille montee, plus le `State` du port charge depuis SES canaux."""
    rid = build_runner("777", extra=["--p-units", "ultraTitus,ultraCalgar",
                                     "--a-units", "necroWarden,necroSpyder", "--no-ai"])["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    obs = rpc("observeBattle", {"runnerId": rid})
    snap = rpc("combatSnapshot", {"runnerId": rid})
    ab = rpc("unitAbilityStates", {"runnerId": rid})
    # `load_state` attend un `Board` OBJET, pas la reponse RPC brute (`board.id_at` sinon).
    board = Board(rpc("boardGraph", {"runnerId": rid})["tiles"])
    st = SNAP.load_state(dv, obs, snapshot=snap, board=board, ability_states=ab)
    uid = next((u["id"] for u in (dv.get("units") or []) if u.get("ctrl") and u.get("alive")), None)
    if uid is None:
        pytest.fail("aucune unite controlee -- rien a decider", pytrace=False)
    return {"rid": rid, "dv": dv, "state": st, "uid": uid}


def _nc(ctx):
    """Le `NCContext` du VRAI call-site (`ai/action_generators`), champ par champ."""
    return NCB.NCContext(
        uid=ctx.uid, origin=ctx.origin, reach_nc=ctx.reach_nc, epos=ctx.epos, fpos=ctx.fpos,
        enemies=ctx.enemies, neigh_by_pos=ctx.neigh_by_pos, walkable_by_pos=ctx.walkable_by_pos,
        plan=ctx.plans.get(ctx.uid) or {}, plans=ctx.plans, hp_cur_by_id=ctx.hp_cur_by_id,
        elev_by_pos=ctx.elev_by_pos, ability_targets=ctx.ability_targets,
        is_wall_by_pos=ctx.is_wall_by_pos, is_in_fog_by_pos=ctx.is_in_fog_by_pos,
        wt=ctx.wt, is_temporary_by_pos=ctx.is_temporary_by_pos,
        effects_by_pos=ctx.effects_by_pos, obs_units=ctx.obs_units, current_player=ctx.cur,
        tile_id_by_pos=ctx.tile_id_by_pos, units=ctx.units, scene=ctx.scene,
        triggered_kits=ctx.live_triggered_kits,
        victory_conditions=ctx.victory_conditions,
        turns_ended_by_first_player=ctx.turns_ended_by_first_player)


# --------------------------------------------------------------------------- #983-r1

def test_le_pont_du_kit_declenche_transporte_une_mesure_NON_VIDE(etat):
    """Un `{}` passerait le test offline (le tri-etat l'autorise) et signifierait pourtant que la
    chaine ne transporte RIEN. C'est ce que seul un etat REEL peut distinguer."""
    table = SB._triggered_kits_from_state(Scene.from_state(etat["state"]))
    assert table, "la chaine ne transporte AUCUNE mesure de kit declenche"
    assert sum(len(v) for v in table.values()) > 0, "des unites mesurees, mais zero id"

    ctx = SB.build_from_state(etat["state"], etat["uid"])
    assert ctx.rid == 0, "le bridge offline doit rester a rid=0 (aucun RPC)"
    assert ctx.live_triggered_kits() == table
    # La voie PAR-UNITE lit la MEME table (les deux se servent mutuellement, cf. la docstring).
    cible = next(iter(table))
    assert ctx.live_triggered_ability_ids(cible) == table[cible]


# --------------------------------------------------------------------------- #1027-r5

def test_le_gate_transporte_repond_comme_le_foyer_interroge_avec_le_State(etat):
    """Le TRANSPORT ne doit rien changer : meme question, meme reponse. C'est le cran qui separe
    « le champ existe » de « le champ porte la bonne valeur »."""
    st, uid = etat["state"], etat["uid"]
    ctx = SB.build_from_state(st, uid)
    assert ctx.turns_ended_by_first_player is not None, "compteur NON transporte"
    assert NCB.has_minimum_remaining_turns(_nc(ctx), TURNS) is bool(
        SBQ.has_minimum_remaining_turns(uid, TURNS, state=st))


def test_un_plafond_de_rounds_INJECTE_fait_BASCULER_le_gate(etat):
    """LE scenario de generalisation. Sans plafond, les deux regimes (avant/apres #1079) rendent
    `True` -- indiscernables. Avec un plafond, l'ancien code repond encore `True` (il jugeait sur
    la SEED, ou la cle est absente) et le nouveau REFUSE. C'est la degradation permissive qui se
    ferme, et elle n'est visible que par ce montage."""
    st, uid = etat["state"], etat["uid"]
    cle = VictoryConditionType.MainPlayerRoundLimitation.name
    avant = st.victory_conditions
    try:
        ended = SB._turns_ended_by_first_player(st) or 0
        # `turns <= limit - ended` : avec `limit = ended + 1`, c'est `2 <= 1` -> FAUX.
        st.victory_conditions = {cle: ended + 1}
        ctx = SB.build_from_state(st, uid)
        assert ctx.victory_conditions == {cle: ended + 1}, "la BC du `State` n'est pas transportee"
        assert NCB.has_minimum_remaining_turns(_nc(ctx), TURNS) is False, (
            "le plafond ne MORD pas -- le transport est inerte")
        # Le meme plafond, largement au-dessus : le gate se rouvre (ce n'est pas un refus constant).
        st.victory_conditions = {cle: ended + 99}
        ctx = SB.build_from_state(st, uid)
        assert NCB.has_minimum_remaining_turns(_nc(ctx), TURNS) is True
    finally:
        st.victory_conditions = avant


def test_les_deux_playbooks_consommateurs_referment_leur_sweep_sous_plafond(etat):
    """`SolarAtomizer` (1174) et `TheLantern` (1094) partagent ce gate en AMONT du sweep : sous un
    plafond qui mord, aucun des deux ne doit produire de candidate."""
    import engine.playbook.noncomparable.solar_atomizer as SA
    import engine.playbook.noncomparable.the_lantern as TL

    st, uid = etat["state"], etat["uid"]
    cle = VictoryConditionType.MainPlayerRoundLimitation.name
    avant = st.victory_conditions
    try:
        ended = SB._turns_ended_by_first_player(st) or 0
        st.victory_conditions = {cle: ended + 1}
        nc = _nc(SB.build_from_state(st, uid))
        assert SA.SolarAtomizerPlaybook().should_evaluate(nc) is False
        assert TL.TheLanternPlaybook().should_evaluate(nc) is False
        assert SA.SolarAtomizerPlaybook().generate_candidates(nc) == []
        assert TL.TheLanternPlaybook().generate_candidates(nc) == []
    finally:
        st.victory_conditions = avant


# --------------------------------------------------------------------------- #979-r1

def test_la_rampe_de_duty_eternal_bascule_sur_le_compteur_REEL_de_la_Scene(etat):
    """`Scene.turns_finished` est le canal que la fiche #979-r1 declarait ABSENT. Ici il est LU sur
    une `Scene` construite depuis le `State` du runner, et la rampe bascule exactement aux bornes
    du decompile -- `c = initialCooldownTurns = 2` pour `DutyEternal`.

    Le porteur (`ultraDreadnought`, MoW) n'est pas dans cette bataille : c'est SANS IMPORTANCE,
    `GetUseProbability` ne lit du caster que `GetTurnsFinished(unit)`, et `GetNumberConstant` sort
    de la CONFIG de l'ability. Le gate se greffe donc sur n'importe quelle unite -- meme forme que
    la greffe `1194 NovaShield` sur `tauCrisis` (case-92 SS5bis)."""
    import engine.services.ability_caster_gates as ACG

    st, uid = etat["state"], etat["uid"]
    ctx = SB.build_from_state(st, uid)
    nc = _nc(ctx)
    p = DutyEternalPlaybook()
    c = ACG.try_get_number_constant(p.ABILITY_ID, ACG.CONST_INITIAL_COOLDOWN)
    assert c is not None, "initialCooldownTurns absente : le natif LEVERAIT ici"

    sc = ctx.scene
    avant = sc.turns_finished_by_id.get(uid)
    try:
        verdicts = {}
        for t in range(0, c + 5):
            sc.turns_finished_by_id[uid] = t
            verdicts[t] = (p._use_probability(nc), p.should_evaluate(nc))
        # Extremite BASSE : refus deterministe tant que `t <= c - 1`.
        for t in range(0, c):
            assert verdicts[t][1] is False, (t, verdicts[t])
        # Bande OUVERTE : trois valeurs, permissif assume.
        for t in (c, c + 1, c + 2):
            assert 0.0 < verdicts[t][0] < 1.0 and verdicts[t][1] is True, (t, verdicts[t])
        # Extremite HAUTE : `t >= c + 3`.
        assert verdicts[c + 3][0] >= 1.0 and verdicts[c + 3][1] is True
    finally:
        if avant is None:
            sc.turns_finished_by_id.pop(uid, None)
        else:
            sc.turns_finished_by_id[uid] = avant
