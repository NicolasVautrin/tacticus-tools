"""#366-r1b -- QUI a le droit d'ECRIRE `EffectComponent.IsActive @+0x5c` au refresh.

`IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` (branche `refreshType == Normal`) a
DEUX regimes, lus verbatim :

    if (effectComponent.<+0x5e>)                    return false;
    if (!effect.ShouldRefreshForTrigger(trigger))   return effectComponent.<+0x5c>;   # CONSERVER
    return effect.ShouldBeActive(entities);                                            # RE-EVALUER

Le port n'a NI `RefreshEffectTrigger` NI `ShouldRefreshForTrigger` : il ne peut pas mirrorer le CHOIX
natif du regime. `refresh_stat_modifier_effects` decide donc sur ce qu'il PEUT lire -- la classe
porte-t-elle vraiment sa `CreateActiveCondition` (= surcharge-t-elle `is_active`) ?

CE FICHIER RETIENT LA LECON, parce qu'AUCUN test ne retenait le regime « effet seede INACTIF dont la
condition PORTEE devient vraie en cours de sim » : c'est par HASARD que
`test_contagions_lifecycle_live` l'a attrape. Les quatre regimes sont ici, OFFLINE et deterministes.

Historique, a garder : le discriminant avait d'abord ete pris sur `BaseEffect.active_condition_ported`.
Ce drapeau repond a une AUTRE question (« le flag CAPTE au seed est-il PERIME parce que la condition
porte sur l'etat SIMULE ? », case-322) et n'est pose que par UNE classe. Resultat : les 12 autres
classes a condition portee etaient VERROUILLEES -- une instance seedee `active=False` (le canal
`includeInactive` de `snapshot.decision_view_seed_body` publie bien `active: false`) ne pouvait plus
JAMAIS se rallumer. Mesure : `test_contagions_lifecycle_live`, aura qui grandit, live
`actif=[1072] armure=1387` contre port `actif=[] armure=2312`.

ASCII only.
"""
from __future__ import annotations

from engine.entities import EffectsState
from engine.entities.effects.base import BaseEffect
from engine.entities.effects.factory import EFFECT_CLASSES, EffectFactory
from engine.entities.effect_type import EffectType
from engine.entities.unit_context import UnitContext
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent)
from engine.runner.operations.refresh_effects import (_active_condition_is_ported,
                                                      refresh_stat_modifier_effects)
from engine.runner.state import State

# Deux temoins REELS du registre, un par regime -- pas des doubles de test : c'est la production
# qu'on garde.
PORTED = "PowerTrip_FullHealth"            # surcharge `is_active` (condition = PV pleins)
UNPORTED = "WireweaveNet_CounterAttack"    # ne la surcharge PAS ; son flag n'est ecrit que par les
#                                            feuilles `ActivateEffect`/`DeactivateEffect` (la riposte
#                                            1111 se DESARME apres son coup -- si le refresh la
#                                            rallumait, elle repartirait le meme tour)


def _state_with(effect_name: str, active: bool, hp: int, hp_max: int = 1000):
    """`State` minimal : UNE unite portant UNE instance d'effet, dans l'etat `active` demande."""
    st = State()
    st.effects = EffectsState.seed({})
    e = st.add_entity()
    e.add_component(UnitComponent(visual_id="eldarRanger", alive=True))
    e.add_component(OwnerComponent(team=1, player=1))
    ctx = UnitContext(entity_id=e.id, visual_id="eldarRanger", active_ability_level=50,
                      passive_ability_level=50, ability_variables_multiplier=100)
    e.add_component(StatsComponent(ctx=ctx))
    e.add_component(HealthComponent(hp=hp, hp_max=hp_max))
    e.add_component(PositionComponent(col=2, row=2))
    etype = EffectType.__members__.get(effect_name)
    inst = EffectFactory.create({"name": effect_name,
                                 "effectType": (int(etype) if etype is not None else None),
                                 "remaining": 0, "active": active})
    inst.target = e.id
    st.effects.add_effect(e.id, inst)
    return st, e.id, inst


def test_discriminant_is_the_is_active_override_not_the_case322_flag():
    """CLIQUET du DISCRIMINANT. `_active_condition_is_ported` doit repondre a « la classe
    surcharge-t-elle `is_active` ? », et surtout PAS a `active_condition_ported`. Les deux ensembles
    sont mesures ici : les confondre re-verrouille les classes a condition portee."""
    overrides = {n for n, k in EFFECT_CLASSES.items() if k.is_active is not BaseEffect.is_active}
    helper = {n for n, k in EFFECT_CLASSES.items() if _active_condition_is_ported(k(n))}
    flagged = {n for n, k in EFFECT_CLASSES.items()
               if getattr(k, "active_condition_ported", False)}
    assert helper == overrides, (
        f"le helper ne mirrore plus la surcharge de `is_active` : {helper ^ overrides}")
    # Le cliquet monte DELIBEREMENT avec chaque `CreateActiveCondition` portee : 13 ecrites au
    # #366-r1b, 14 MESUREES a la reprise (`CamoCloak_DmgReduction` etait entree entre-temps sans que
    # le plancher bouge -- preuve qu'un plancher qu'on ne remonte pas cesse d'etre un cliquet), 15
    # depuis `MartialSuperiority_Visual` (1255, case-366-r1).
    assert len(overrides) >= 15, (
        f"seulement {len(overrides)} classes a condition PORTEE -- une surcharge a disparu ?")
    assert flagged < overrides, (
        "`active_condition_ported` n'est PAS un sur-ensemble des conditions portees : "
        f"flagged={sorted(flagged)} overrides={len(overrides)}")
    assert len(flagged) < len(overrides), (
        f"les DEUX ensembles coincident ({len(flagged)}) -- le discriminant a ete reconfondu avec "
        "le drapeau case-322, ce qui VERROUILLE les classes a condition portee (cf. en-tete)")
    # les deux temoins de ce fichier doivent rester de part et d'autre de la frontiere
    assert PORTED in overrides and UNPORTED not in overrides


def test_ported_condition_relights_a_seeded_inactive_instance():
    """REGIME QUI N'ETAIT RETENU PAR RIEN (celui de Contagions) : une instance arrivee INACTIVE du
    seed (`includeInactive` publie `active: false`), dont la condition PORTEE devient vraie, doit se
    RALLUMER au refresh. Le verrou `active = e.active and cond` sans reecriture l'en empechait."""
    st, uid, inst = _state_with(PORTED, active=False, hp=1000, hp_max=1000)   # PV pleins -> vraie
    assert inst.active is False
    refresh_stat_modifier_effects(st, uid)
    assert inst.active is True, (
        "une instance seedee INACTIVE dont la condition PORTEE est vraie n'a pas ete rallumee -- "
        "c'est le verrou qui a fait rougir test_contagions_lifecycle_live")


def test_ported_condition_extinguishes_when_it_becomes_false():
    """Symetrique : la meme classe, condition PORTEE fausse -> le refresh ETEINT l'instance."""
    st, uid, inst = _state_with(PORTED, active=True, hp=400, hp_max=1000)     # PV entames -> fausse
    refresh_stat_modifier_effects(st, uid)
    assert inst.active is False, (
        "la condition portee est fausse et l'instance reste allumee -- le refresh n'ecrit plus rien")


def test_unported_condition_is_never_relit_by_the_refresh():
    """REGIME INVERSE (celui de la riposte 1111) : sans condition portee, `is_active()` rend le
    DEFAUT `True` -- une valeur inventee, pas une lecture. Le refresh doit CONSERVER le flag, sinon
    il ecrase le `DeactivateEffect` que la feuille vient de poser et la riposte repart le meme tour
    (mesure : riposte fantome de 2849 PV, `test_wireweave_net_counter_is_once_per_enemy_turn`)."""
    st, uid, inst = _state_with(UNPORTED, active=False, hp=1000, hp_max=1000)
    refresh_stat_modifier_effects(st, uid)
    assert inst.active is False, (
        "le refresh a RALLUME un effet sans condition portee -- il ecrit un DEFAUT par-dessus le "
        "flag pose par ActivateEffect/DeactivateEffect")


def test_unported_condition_active_instance_is_left_alone():
    """Et il ne l'ETEINT pas non plus : sans lecture, on ne touche a rien."""
    st, uid, inst = _state_with(UNPORTED, active=True, hp=400, hp_max=1000)
    refresh_stat_modifier_effects(st, uid)
    assert inst.active is True, "le refresh a ETEINT un effet sans condition portee"
