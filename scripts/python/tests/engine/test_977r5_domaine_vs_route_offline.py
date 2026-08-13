"""#977-r5 -- le DOMAINE de cible offline ne doit JAMAIS etre derive de la ROUTE de decision.

GARDE (le probe qui MESURE est `probe_977r5_domaine_vs_route.py`). 100 % OFFLINE : aucun runner,
aucun RPC -- tout se joue sur `engine.ai.state_bridge` et un `State` synthetique.

CE QUI EST GARDE, et pourquoi chaque etage existe
--------------------------------------------------
1. `_ability_kind` ne rabat plus AUCUNE NonComparable a `damageProfile` sans veto de camp sur le
   domaine residuel `self`. C'etait le gisement : mesure a l'ouverture du residu, **29** abilities
   (`1122 CordClaw`, `1132 KillMaimBurn`, `1202 VigilanceEternal`, ...). L'etage ASSERTIONNE SON
   PROPRE NON-VIDE : un ensemble vide passerait pour vert.
2. L'effet OBSERVABLE sur le substrat : `ability_targets_offline` emet bien l'ennemi adjacent, et
   pas le caster SEUL. Un test sur le seul `kind` serait satisfait par un renommage.
3. L'effet OBSERVABLE sur la face DECISION : `CordClawPlaybook._eligible_ids` retrouve l'ennemi.
   Sans lui, le playbook filtrait TOUTES ses cibles (`tid not in eligible`) et l'ability ne
   produisait AUCUNE action offline -- une degradation RESTRICTIVE et silencieuse.
4. La ROUTE est INCHANGEE : `_is_attack_ability` rend toujours `False` pour une NonComparable (elle
   ne doit pas entrer dans `attackPlans` / `_best_attack`), et le VETO #217 tient toujours
   (`1100 SorcerousFacade` reste `ally`). C'est la contre-partie du fix : elargir le domaine ne doit
   pas elargir la route.
5. Le domaine emis est un SUR-ENSEMBLE de l'ancien : le caster reste emis. C'est ce qui rend le fix
   non-regressif PAR CONSTRUCTION pour les lecteurs qui n'attendaient que lui (`1192 NovaBoost`).

FONDEMENT NATIF (LU sur `rnca9r7q6c`, cf. la docstring d'`_enumerates_both_camps`) :
`IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` n'applique AUCUN filtre de
camp -- ses trois `RemoveWhere` retirent les entites mortes/steppables, les NON-amis obscurcis par
du terrain, et la regle dynamique. Le camp n'est tranche qu'ensuite par
`...$$GetInvalidTargetReason`, dont les deux seules regles de camp sont celles que
`refuses_all_enemy_targets` reconnait.
"""
from __future__ import annotations

import pytest

from engine.ai import state_bridge as SB
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.pathfinding.board import Board
from engine.playbook.noncomparable import PLAYBOOKS
from engine.runner.abilities.targeting import targeting_options_for
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent
from engine.runner.state import State

#: Porteurs `lineup` LUS par `unit_map.py find --ability` (voie `active`).
CASTER_VID = "admecRuststalker"      # porte `1122 CordClaw`
FOE_VID = "templSwordBrother"
CORD_CLAW = int(ActiveAbilityType.CordClaw)              # 1122
SORCEROUS_FACADE = int(ActiveAbilityType.SorcerousFacade)  # 1100 -- le VETO #217


def _sans_veto_de_camp(aid: int) -> bool:
    """Le masque est-il LU et sans regle de camp ni `TargetIsTile` ? (= le domaine `any`)"""
    o = targeting_options_for(aid)
    return o is not None and not (o.has(TR.TargetIsFriendly) or o.has(TR.TargetIsCaster)
                                  or o.has(TR.TargetIsTile))


@pytest.fixture(scope="module")
def nc_sans_veto():
    """Les playbooks NonComparable a `constants.damageProfile` dont le masque n'oppose AUCUN veto de
    camp -- la population EXACTE que la clause de route rabattait sur `self`."""
    out = []
    for aid in sorted(PLAYBOOKS):
        name, cfg = SB._resolve_ability(aid)
        if not (cfg.get("constants") or {}).get("damageProfile"):
            continue
        if not _sans_veto_de_camp(aid):
            continue
        out.append((aid, name, cfg))
    return out


@pytest.fixture(scope="module")
def duel_synthetique():
    """`State` OFFLINE minimal : grille 5x5 evenq toute marchable, un caster (team 1) porteur de
    `1122 CordClaw` et UN ennemi (team 2) sur une tuile ADJACENTE.

    L'adjacence n'est pas cosmetique : `CordClaw` est une melee, donc hors adjacence la PORTEE
    refuserait EN AMONT et masquerait ce que le domaine, lui, rend. Rend
    `(state, caster_id, foe_id)`."""
    tiles = [{"id": c * 5 + r + 1, "col": c, "row": r, "walkable": True, "elevation": 0}
             for c in range(5) for r in range(5)]
    board = Board(tiles, adjacency="evenq")   # les tuiles n'ont pas de champ `neighbours`
    st = State()
    st.board = board
    caster_t = next(t for t in sorted(board.by_id)
                    if sum(1 for x in board.neighbours(t) if board.walkable(x)) >= 3)
    ftile = next(x for x in board.neighbours(caster_t) if board.walkable(x))

    def mk(eid, vis, team, tile):
        col, row = board.coord(tile)
        e = st.add_entity(eid)
        e.add_component(UnitComponent(visual_id=vis, alive=True))
        e.add_component(OwnerComponent(team=team, player=team))
        e.add_component(PositionComponent(col=col, row=row))
        return eid

    return st, mk(101, CASTER_VID, 1, caster_t), mk(102, FOE_VID, 2, ftile)


def _cibles(state, uid: int, aid: int) -> list:
    at = SB.ability_targets_offline(state, uid, aid)
    return [t.get("targetId") for u in (at.get("units") or [])
            for a in (u.get("abilities") or []) for t in (a.get("targets") or [])]


def test_aucune_noncomparable_sans_veto_n_est_rabattue_sur_self(nc_sans_veto):
    """Etage 1 -- et il ASSERTIONNE SON PROPRE NON-VIDE : le gisement en comptait 29."""
    assert len(nc_sans_veto) >= 20, (
        "la population mesuree a fondu (%d) : ce test ne garde plus rien" % len(nc_sans_veto))
    rabattues = [(aid, name) for (aid, name, cfg) in nc_sans_veto
                 if SB._ability_kind(aid, name, cfg) == "self"]
    assert rabattues == [], (
        "domaine 'self' pour des abilities dont le masque n'oppose AUCUN veto de camp : %r"
        % (rabattues,))


def test_le_substrat_emet_l_ennemi_et_pas_le_caster_seul(duel_synthetique):
    """Etage 2 -- l'effet OBSERVABLE. Avant le fix : `[101]`."""
    st, caster, foe = duel_synthetique
    ids = _cibles(st, caster, CORD_CLAW)
    assert foe in ids, "ability_targets_offline(1122) n'emet pas l'ennemi adjacent : %r" % (ids,)


def test_le_caster_reste_emis_le_domaine_est_un_sur_ensemble(duel_synthetique):
    """Etage 5 -- non-regression PAR CONSTRUCTION : ce que l'ancien domaine emettait (le caster)
    est toujours la, donc un lecteur qui ne cherchait que lui (`1192 NovaBoost`) n'est pas casse."""
    st, caster, _foe = duel_synthetique
    assert caster in _cibles(st, caster, CORD_CLAW)


def test_la_face_decision_de_cord_claw_retrouve_sa_cible(duel_synthetique):
    """Etage 3 -- `_eligible_ids` filtrait TOUS les ennemis quand l'ensemble valait `{caster}`."""
    from engine.playbook.noncomparable.cord_claw import CordClawPlaybook

    st, caster, foe = duel_synthetique
    ctx = SB.build_from_state(st, caster)

    class _NC:
        uid = ctx.uid
        ability_targets = staticmethod(ctx.ability_targets)

    elig = CordClawPlaybook()._eligible_ids(_NC())
    assert elig is not None and foe in elig, "cibles eligibles de 1122 : %r" % (elig,)


def test_la_route_reste_fermee_aux_noncomparable(nc_sans_veto):
    """Etage 4a -- elargir le DOMAINE ne doit pas elargir la ROUTE : une NonComparable n'entre
    jamais dans `attackPlans` (`ABaseAiActorTactic$$InitAbilityTypeLists` la range ailleurs)."""
    fuites = [(aid, name) for (aid, name, cfg) in nc_sans_veto
              if SB._is_attack_ability(aid, cfg)]
    assert fuites == [], "NonComparable entrees dans la route d'attaque : %r" % (fuites,)


def test_le_veto_217_tient_toujours():
    """Etage 4b -- `1100 SorcerousFacade` porte un `damageProfile` ET `TargetIsFriendly` : son
    domaine reste `ally`, et elle reste hors de la route ennemie."""
    name, cfg = SB._resolve_ability(SORCEROUS_FACADE)
    assert SB._ability_kind(SORCEROUS_FACADE, name, cfg) == "ally"
    assert SB._is_attack_ability(SORCEROUS_FACADE, cfg) is False
