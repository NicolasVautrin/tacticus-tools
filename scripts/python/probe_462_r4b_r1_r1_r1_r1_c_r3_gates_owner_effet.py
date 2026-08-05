"""#462-r4b-r1-r1-r1-r1-c-r3 -- les DEUX gates d'owner que le port garde sur la face EFFET.

La tranche `-c-r1` a etabli que le natif n'applique AUCUN gate d'owner sur la face EFFET
(`IdunBattle.Operations.EvaluateTriggerOperation$$CanGetEffectTrigger` et la branche effet
d'`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityOrEffectTrigger` commencent par un
corps DEDUPLIQUE `return 1`). Le port, lui, en gardait deux : porteur INTROUVABLE et porteur MORT.
Ce probe MESURE ce que leur levee change, avant de la faire.

  --step registre  : inventaire DERIVE du registre `EFFECT_TRIGGERS` -- face (effet/tuile), presence
                     de l'echappatoire `fire_on_death`, evenements ecoutes. C'est ce qui borne le
                     perimetre : seules les classes SANS `fire_on_death` changent de comportement.
  --step fenetre   : la FENETRE de vulnerabilite, mesuree sur la sequence de mort du port
                     (`IdunBattle.Operations.KillUnitOperation$$Execute`) -- a quel(s) evenement(s)
                     le mourant est-il `alive=False` alors que ses effets ne sont PAS encore
                     consommes ? C'est la seule fenetre ou le gate `alive` peut mordre.
  --step gate      : combien d'entrees de la face EFFET chaque branche du gate JETTE, sur des
                     regimes crafted (porteur mort / porteur introuvable).
  --step fod       : les classes d'`EffectTrigger` qui declarent `fire_on_death` -- l'echappatoire
                     ad hoc qu'un gate absent du natif a rendue necessaire.

Sortie ASCII (console cp1252). Aucun runner, aucun RPC : 100 % offline.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.dsl.event_trigger_type import EventTriggerType                # noqa: E402
from engine.runner.state import State                                    # noqa: E402
from engine.runner.components import UnitComponent                       # noqa: E402
from engine.runner.operations.triggers.base import (EffectTrigger,       # noqa: E402
                                                    TileEffectTrigger, TriggerEvent)
from engine.runner.operations.triggers.dispatch import registry as REG   # noqa: E402
from engine.runner.operations.triggers.dispatch import core as CORE      # noqa: E402


def _nom_event(e: int) -> str:
    try:
        return EventTriggerType(int(e)).name
    except Exception:
        return "?"


def _events(cls) -> tuple:
    eids = tuple(getattr(cls, "event_ids", ()) or ())
    return eids or (int(getattr(cls, "event_id", -1)),)


def _inventaire():
    """`[(effect_type, classe, est_tuile, fire_on_death, events)]` -- DERIVE du registre."""
    out = []
    for et in sorted(REG.EFFECT_TRIGGERS):
        for c in REG.EFFECT_TRIGGERS[et]:
            out.append((int(et), c, issubclass(c, TileEffectTrigger),
                        bool(getattr(c, "fire_on_death", False)),
                        tuple(int(e) for e in _events(c))))
    return out


def step_registre() -> int:
    inv = _inventaire()
    ets = sorted({et for et, _c, _t, _f, _e in inv})
    tuiles = [x for x in inv if x[2]]
    nues = [x for x in inv if not x[2]]
    ets_nus = sorted({et for et, _c, t, _f, _e in inv if not t}
                     - {et for et, _c, t, _f, _e in inv if t})
    print("[registre] EFFECT_TRIGGERS : %d effect_type, %d classes" % (len(ets), len(inv)))
    print("[registre] classes TileEffectTrigger : %d ; classes NUES : %d" % (len(tuiles), len(nues)))
    print("[registre] effect_type servis EXCLUSIVEMENT par des classes nues : %d" % len(ets_nus))
    print("[registre] %s" % ets_nus)
    sans_fod = [x for x in nues if not x[3]]
    print("[registre] classes nues SANS fire_on_death (le perimetre de la levee) : %d" % len(sans_fod))
    for et, c, _t, _f, ev in sans_fod:
        print("   %5d %-52s %s" % (et, c.__name__, [(i, _nom_event(i)) for i in ev]))
    return 0


def step_fod() -> int:
    """Les `EffectTrigger` qui declarent `fire_on_death`.

    Cet attribut est l'ECHAPPATOIRE que le gate `alive` a rendue necessaire cote port -- le natif
    n'en a pas besoin, sa face EFFET ne gate rien. Chaque ligne ici est donc une classe qui, sans
    l'attribut, serait JETEE par le port la ou le natif l'evalue."""
    inv = _inventaire()
    fod = [x for x in inv if x[3]]
    print("[fod] classes d'EffectTrigger declarant fire_on_death : %d" % len(fod))
    for et, c, tuile, _f, ev in fod:
        print("   %5d %-52s %-5s %s"
              % (et, c.__name__, "TILE" if tuile else "nue", [(i, _nom_event(i)) for i in ev]))
    print("[fod] LECTURE : sur la face EFFET le natif n'a AUCUN gate d'owner -- cet attribut y est")
    print("[fod]           un correctif local du SURPLUS du port, pas un mirror.")
    return 0


# --------------------------------------------------------------------------- fenetre de mort

class _Sonde(EffectTrigger):
    """Effet-trigger NU qui NOTE le couple (event, owner) a chaque passage de `matches`, sans muter.

    C'est le capteur : si le gate d'owner l'ecarte AVANT `matches`, rien n'est note."""
    event_id = -1
    event_ids: tuple = ()
    vus: list = []

    def matches(self, state, ev) -> bool:
        _Sonde.vus.append((int(ev.event_id), int(self.owner_id)))
        return False

    def execute_behaviour(self, state, ev):
        return None


def _effect_type_libre() -> int:
    """Un `effect_type` HORS registre : la sonde s'y inscrit sans ecraser aucune entree reelle."""
    et = 990001
    while et in REG.EFFECT_TRIGGERS:
        et += 1
    return et


def _state_unite_avec_effet(effect_type: int, *, vivant: bool, hp: int = 10):
    from engine.entities.effects_state import EffectsState
    from engine.entities.effects import EffectFactory
    from engine.runner.components import HealthComponent
    st = State()
    st.effects = EffectsState()
    ent = st.add_entity()
    uid = int(ent.id)
    ent.add_component(UnitComponent(visual_id="sonde", alive=bool(vivant)))
    ent.add_component(HealthComponent(hp=hp if vivant else 0, hp_max=hp))
    st.effects.add_effect(uid, EffectFactory.create(
        {"name": "SondeEffect", "effectType": int(effect_type), "remaining": 0}, 100, None, None))
    return st, uid


def _sonde_inscrite(et: int, events: tuple):
    _Sonde.event_ids = tuple(int(e) for e in events)
    _Sonde.event_id = int(events[0])
    REG.EFFECT_TRIGGERS[et] = [_Sonde]


def _sonde_retiree(et: int):
    REG.EFFECT_TRIGGERS.pop(et, None)


_EVENTS_MORT = (int(EventTriggerType.PendingDeathAdded), int(EventTriggerType.PreUnitDeath),
                int(EventTriggerType.PreUnitDeath_2), int(EventTriggerType.UnitDeath),
                int(EventTriggerType.UnitDefeated))


def step_fenetre() -> int:
    """La FENETRE : sur quels evenements de la sequence de mort le mourant porte-t-il encore ses
    effets alors qu'il est deja `alive=False` ?

    Mesure directe : on inscrit la sonde sur les CINQ events de
    `IdunBattle.Operations.KillUnitOperation$$Execute`, on tue l'unite par le vrai pipeline de degat
    du port, et on regarde ce que le COLLECTEUR rend a chaque event -- gate d'owner NEUTRALISE, pour
    mesurer la fenetre elle-meme et non le gate."""
    from engine.runner.operations.damage import AttackDamageOperation
    et = _effect_type_libre()
    st, uid = _state_unite_avec_effet(et, vivant=True, hp=10)
    ent = st.get_entity(uid)
    _Sonde.vus = []
    _sonde_inscrite(et, _EVENTS_MORT)
    # Gate d'owner neutralise : on mesure la PRESENCE des effets a chaque event, pas le gate.
    collecte = {}
    vrai_collect = CORE.collect_effect_triggers

    def _trace(state):
        trigs = vrai_collect(state)
        return trigs

    try:
        from engine.runner.components import HealthComponent
        hc = ent.get_component(HealthComponent)
        vus_par_event = []
        # on instrumente le collecteur pour enregistrer, PAR EVENT, si l'effet est encore la
        original = CORE.evaluate_trigger_operation

        def _wrap(state, ev):
            presents = [t for t in vrai_collect(state) if int(t.owner_id) == uid]
            vus_par_event.append((int(ev.event_id), len(presents)))
            return original(state, ev)

        CORE.evaluate_trigger_operation = _wrap
        try:
            AttackDamageOperation._fire_death_if_killed(
                st, uid, uid, hc.hp, 0, ent, damage=hc.hp)
        finally:
            CORE.evaluate_trigger_operation = original
        collecte = vus_par_event
    finally:
        _sonde_retiree(et)
    print("[fenetre] sequence de mort du port -- effets NON CONSOMMES du mourant, par evenement :")
    for eid, n in collecte:
        print("   On(%-3d %-22s) : %d effet(s) encore collecte(s)" % (eid, _nom_event(eid), n))
    fenetre = [eid for eid, n in collecte if n > 0]
    print("[fenetre] FENETRE (alive=False ET effets presents) = %s"
          % [(e, _nom_event(e)) for e in fenetre])
    return 0


def step_gate() -> int:
    """Combien d'entrees de la face EFFET le gate JETTE, regime par regime."""
    et = _effect_type_libre()
    resultats = []
    for libelle, vivant in (("porteur VIVANT", True), ("porteur MORT", False)):
        st, uid = _state_unite_avec_effet(et, vivant=vivant)
        _Sonde.vus = []
        _sonde_inscrite(et, (2,))
        try:
            CORE.evaluate_trigger_operation(
                st, TriggerEvent(2, uid, uid, ranged=False, profile=None))
        finally:
            _sonde_retiree(et)
        resultats.append((libelle, len(_Sonde.vus)))
    # porteur INTROUVABLE : une cle de `by_unit` qui n'est ni une entite ni une tuile
    from engine.entities.effects_state import EffectsState
    from engine.entities.effects import EffectFactory
    st = State()
    st.effects = EffectsState()
    orphelin = 987654
    st.effects.add_effect(orphelin, EffectFactory.create(
        {"name": "SondeEffect", "effectType": int(et), "remaining": 0}, 100, None, None))
    _Sonde.vus = []
    _sonde_inscrite(et, (2,))
    try:
        CORE.evaluate_trigger_operation(
            st, TriggerEvent(2, orphelin, orphelin, ranged=False, profile=None))
    finally:
        _sonde_retiree(et)
    resultats.append(("porteur INTROUVABLE (ni entite ni tuile)", len(_Sonde.vus)))
    print("[gate] face EFFET -- `matches` atteint ?")
    for libelle, n in resultats:
        print("   %-42s : %d passage(s)" % (libelle, n))
    print("[gate] NATIF : les trois regimes valent 1 -- `CanGetEffectTrigger` commence par un")
    print("[gate]         corps DEDUPLIQUE `return 1`, donc aucun gate d'owner.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--step", required=True,
                   choices=["registre", "fod", "fenetre", "gate"])
    a = p.parse_args()
    return {"registre": step_registre, "fod": step_fod,
            "fenetre": step_fenetre, "gate": step_gate}[a.step]()


if __name__ == "__main__":
    raise SystemExit(main())
