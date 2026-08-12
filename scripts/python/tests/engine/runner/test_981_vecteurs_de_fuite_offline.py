"""#981 (#947-r1) -- cliquet OFFLINE des DEUX events que `FleeOperation` n'emettait pas.

`IdunBattle.Operations.FleeOperation$$Execute` publie, APRES le `UnitFlag 9` et son
`RemoveEffects(step 1)`, DEUX events consecutifs batis sur la MEME struct ::

    <slot 81 = EvaluateAbilities>( triggeringUnit, triggeringUnit, unit, 0x34 = UnitFled,     ... )
    <slot 81 = EvaluateAbilities>( triggeringUnit, triggeringUnit, unit, 0x36 = UnitDefeated, ... )

Le port n'emettait NI l'un NI l'autre. `HeadClaimerOnFledAbility` etait au registre et
structurellement INCAPABLE de fire -- exactement la forme de dette que ce lot traque : du code
enregistre, teste, et que rien n'atteint.

Ce fichier ne se contente PAS d'inspecter la source : il MONTE un etat et EXECUTE la chaine, avec
un temoin NEGATIF a chaque etage (sans quoi un gate toujours faux passerait pour un succes).
Detail : `docs/rl/case-947-948-passifs-extra-damage.md`.
"""
from __future__ import annotations

import hexgeo
import pytest

from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.effects_state import EffectsState
from engine.entities.pathfinding.board import Board
from engine.entities.unit_context import UnitContext
from engine.runner.components import StatsComponent
from engine.runner.operations.behaviour import FleeOperation
from engine.runner.operations.triggers.dispatch import move_death
from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
from engine.runner.snapshot import load_state

#: #486-r15 -- perimetre = exactement les foyers que ce fichier lit et execute.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/coverage_attestations.py",
        # les DEUX foyers de la tranche
        "scripts/python/engine/runner/operations/behaviour.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/move_death.py",
        # les consommateurs exerces
        "scripts/python/engine/runner/operations/triggers/loki/head_claimer.py",
        "scripts/python/engine/runner/operations/triggers/genestealer.py",
        "scripts/python/engine/runner/operations/triggers/loki/savage_killer.py",
        "scripts/python/engine/runner/operations/triggers/loki/fuelled_by_fury.py",
        "scripts/python/engine/runner/operations/remove_effects.py",
        # le rail de collecte + le montage d'etat
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/core.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/entities/unit_context.py",
        "scripts/python/engine/entities/effects_state.py",
        "scripts/python/engine/entities/pathfinding/board.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/gameconfig.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Offline : EXECUTE la chaine `FleeOperation` -> `On(0x34)` / `On(0x36)` sur un etat "
              "monte a la main (aucun runner). Fige l'ASYMETRIE des slots lue au decompile "
              "(`actor = caster = triggeringUnit`, `target = la fuyarde`), qui est ce qui rend "
              "`get_OwnerIsActor` de HeadClaimer satisfiable sur une fuite. Le kit gameconfig est "
              "lu pour les passifs/traits des deux porteurs -> `build: True`.",
}

HAARKEN, FUYARD = 101, 202
COLS = ROWS = 6


def _tid(c: int, r: int) -> int:
    return c * 100 + r


def _tiles() -> list:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


def _state(fuyard_visual: str = "necroWarden"):
    """Etat minimal : `blackHaarken` (passif `HeadClaimer`) en equipe 1, un ennemi en equipe 2.

    `load_state` ne pose de `StatsComponent` que depuis un `combatSnapshot` ; on le fabrique, car
    c'est LUI que `collect_triggered_abilities` lit (`ctx.visual_id` -> kit gameconfig, hierarchie
    de repli quand `passive_abilities` n'a pas ete mesuree)."""
    board = Board(_tiles(), adjacency="evenq")
    units = [
        {"id": HAARKEN, "visualId": "blackHaarken", "alive": True, "team": 1,
         "owner": 1, "pos": {"col": 1, "row": 1}, "effects": []},
        {"id": FUYARD, "visualId": fuyard_visual, "alive": True, "team": 2,
         "owner": 2, "pos": {"col": 3, "row": 3}, "effects": []},
    ]
    decision = {"currentPlayer": 1, "units": units}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000} for u in units]}
    import gameconfig as GC
    st = load_state(decision, observe, board=board)
    if st.effects is None:
        st.effects = EffectsState()
    for u in units:
        # `traits` = la liste gameconfig du `visualId` (canal offline, `traits_measured` faux) :
        # c'est ce que lit `AmbushSummonAbility.matches` via `sc.ctx.traits`.
        traits = list((GC.unit(u["visualId"]) or {}).get("traits") or [])
        st.get_entity(u["id"]).add_component(StatsComponent(ctx=UnitContext(
            entity_id=u["id"], visual_id=u["visualId"], traits=traits,
            passive_ability_level=50, ability_variables_multiplier=100)))
    return st


def _par_ability(res, nom: str) -> list:
    return [d for d in (res or []) if isinstance(d, dict) and d.get("ability") == nom]


# ------------------------------------------------------- [1] les deux vecteurs EXISTENT
def test_les_deux_vecteurs_existent_et_portent_le_bon_ordinal():
    """`On(0x34)` n'avait AUCUNE fonction de dispatch ; `On(0x36)` en avait une, mais aucune
    Operation de FUITE ne l'appelait."""
    assert callable(getattr(move_death, "unit_fled_triggers", None)), \
        "le vecteur `On(UnitFled)` n'existe pas"
    assert callable(getattr(move_death, "unit_defeated_triggers", None))
    assert int(EventTriggerType.UnitFled) == 0x34 == 52
    assert int(EventTriggerType.UnitDefeated) == 0x36 == 54
    assert int(EventTriggerType.PreUnitFled) == 0x33 == 51


# ------------------------------------------------------- [2] l'ASYMETRIE des slots, LUE
def test_l_asymetrie_des_slots_entre_pre_unit_fled_et_les_deux_suivants():
    """`On(PreUnitFled)` passe la fuyarde TROIS FOIS (`actor = caster = target`) ; `On(0x34)` et
    `On(0x36)` passent `actor = caster = triggeringUnit` et `target = la fuyarde`.

    C'est LA lecture qui rend le port correct : inverser les deux slots laisserait la branche
    de `HeadClaimer` inerte d'une AUTRE facon, sans lever la moindre erreur."""
    st = _state()
    vus = []
    reel = move_death.evaluate_trigger_operation

    def _espion(state, ev):
        vus.append((int(ev.event_id), ev.actor_id, ev.target_id))
        return reel(state, ev)

    move_death.evaluate_trigger_operation = _espion
    try:
        FleeOperation.execute(st, FUYARD, triggering_unit=HAARKEN)
    finally:
        move_death.evaluate_trigger_operation = reel

    par_event = {e: (a, t) for (e, a, t) in vus}
    assert int(EventTriggerType.PreUnitFled) in par_event, "`On(0x33)` n'est plus emis"
    assert par_event[int(EventTriggerType.PreUnitFled)] == (FUYARD, FUYARD), \
        "`On(PreUnitFled)` doit passer la FUYARDE en actor ET en target"
    for eid in (int(EventTriggerType.UnitFled), int(EventTriggerType.UnitDefeated)):
        assert eid in par_event, "l'event 0x%x n'est pas emis par FleeOperation" % eid
        assert par_event[eid] == (HAARKEN, FUYARD), (
            "event 0x%x : attendu (actor=triggeringUnit, target=fuyarde), obtenu %r"
            % (eid, par_event[eid]))


def test_l_ordre_natif_des_trois_emissions_est_preserve():
    """`On(0x33)` -> retrait du plateau -> `UnitFlag 9` -> `On(0x34)` -> `On(0x36)`."""
    st = _state()
    vus = []
    reel = move_death.evaluate_trigger_operation

    def _espion(state, ev):
        vus.append(int(ev.event_id))
        return reel(state, ev)

    move_death.evaluate_trigger_operation = _espion
    try:
        FleeOperation.execute(st, FUYARD, triggering_unit=HAARKEN)
    finally:
        move_death.evaluate_trigger_operation = reel

    trois = [e for e in vus if e in (int(EventTriggerType.PreUnitFled),
                                     int(EventTriggerType.UnitFled),
                                     int(EventTriggerType.UnitDefeated))]
    assert trois == [int(EventTriggerType.PreUnitFled),
                     int(EventTriggerType.UnitFled),
                     int(EventTriggerType.UnitDefeated)], \
        "ordre des emissions non conforme au decompile : %r" % (trois,)


# ------------------------------------------------------- [3] HeadClaimer COMPTE une fuite
def test_head_claimer_est_au_registre_avec_SES_DEUX_branches():
    st = _state()
    noms = sorted({type(t).__name__ for t in collect_triggered_abilities(st)})
    assert "HeadClaimerOnDeathAbility" in noms
    assert "HeadClaimerOnFledAbility" in noms, \
        "la branche `On(0x34)` de la disjonction n'est plus inscrite"


def test_une_fuite_credite_une_tete_a_haarken():
    """LE point du residu : `(OnPreDeath2 | On(0x34)) & get_OwnerIsActor & NOT AreFriends`.
    Haarken fait fuir un ennemi -> l'effet `1028 HeadClaimer_ExtraDmg` monte d'un niveau.

    `necroWarden` PORTE le trait `Hero` (`traits = ['Hero', 'LivingMetal', 'Mechanical']`, lu au
    gameconfig), donc le `If(IsHero(Target@+0x60))` du `CreateBehaviour` est VRAI et la face COUPS
    (`1029`) monte AUSSI -- c'est le << For each enemy Character >> de l'i2."""
    from engine.entities.effect_type import EffectType
    st = _state()
    res = FleeOperation.execute(st, FUYARD, triggering_unit=HAARKEN)
    tetes = _par_ability(res.get("unit_fled"), "HeadClaimer")
    assert len(tetes) == 1, "HeadClaimer n'a PAS compte la fuite : %r" % (res.get("unit_fled"),)
    t = tetes[0]
    assert t["unit"] == HAARKEN and t["victim"] == FUYARD
    assert t["on_event"] == int(EventTriggerType.UnitFled)
    assert t["victim_is_hero"] is True
    assert t["levels"].get(int(EffectType.HeadClaimer_ExtraDmg)) == 1
    assert t["levels"].get(int(EffectType.HeadClaimer_ExtraHit)) == 1


def test_une_fuite_de_NON_hero_ne_monte_que_la_face_degat():
    """Contre-epreuve du `If(IsHero(Target@+0x60), AddEffectOrIncreaseLevel(1029))` : un fuyard
    SANS le trait `Hero` (`genesSmnGenestealer`, un summon) ne credite QUE la face DEGAT. Sans ce
    cas, le test precedent ne distinguerait pas le `If` d'un `AND` inconditionnel."""
    from engine.entities.effect_type import EffectType
    st = _state(fuyard_visual="genesSmnGenestealer")
    res = FleeOperation.execute(st, FUYARD, triggering_unit=HAARKEN)
    tetes = _par_ability(res.get("unit_fled"), "HeadClaimer")
    assert len(tetes) == 1
    t = tetes[0]
    assert t["victim_is_hero"] is False
    assert t["levels"].get(int(EffectType.HeadClaimer_ExtraDmg)) == 1
    assert int(EffectType.HeadClaimer_ExtraHit) not in t["levels"], \
        "la face COUPS ne doit monter que contre un `Hero`"


def test_temoin_NEGATIF_sans_triggering_unit_aucune_tete():
    """Degradation RESTRICTIVE assumee : canal `triggeringUnit` non seede -> le vecteur est emis
    avec `actor = target = la fuyarde`, donc `get_OwnerIsActor` FERME pour tout tiers. Sans ce
    temoin, l'etage precedent pourrait etre vert avec un gate qui laisse tout passer."""
    st = _state()
    res = FleeOperation.execute(st, FUYARD)
    assert _par_ability(res.get("unit_fled"), "HeadClaimer") == []


def test_temoin_NEGATIF_un_ami_qui_fuit_ne_compte_pas():
    """`NOT AreFriends(Owner@+0x30, Target@+0x60)` -- une fuite AMIE ne credite rien."""
    st = _state()
    from engine.runner.components import OwnerComponent
    st.get_entity(FUYARD).get_component(OwnerComponent).team = 1     # meme equipe que Haarken
    res = FleeOperation.execute(st, FUYARD, triggering_unit=HAARKEN)
    assert _par_ability(res.get("unit_fled"), "HeadClaimer") == []


# ------------------------------------------------------- [4] le SECOND vecteur est vivant
def test_le_vecteur_unit_defeated_de_la_fuite_atteint_ambush():
    """`Ambush_SummonAbility` = `On(0x36) & OwnerIsTarget & HasTrait(Ambush) & NOT HasFlag(0xe)`.

    Le natif publie `On(0x36)` dans `FleeOperation` comme dans `KillUnitOperation` : un porteur
    `Ambush` qui FUIT pose donc son decoy. C'est ce que dit l'i2 de `HeadClaimer` en ecrivant
    << defeated >> et non << killed >>, et c'est le regime que le port ratait entierement."""
    st = _state(fuyard_visual="genesKelermorph")
    res = FleeOperation.execute(st, FUYARD, triggering_unit=HAARKEN)
    ambush = [d for d in (res.get("unit_defeated") or [])
              if isinstance(d, dict) and d.get("ability") == "Ambush_Summon"]
    assert len(ambush) == 1, \
        "le vecteur `On(UnitDefeated)` de la FUITE n'atteint pas Ambush : %r" % (
            res.get("unit_defeated"),)
    assert ambush[0]["owner"] == FUYARD


def test_by_flight_ne_renseigne_NI_killer_id_NI_dying_id():
    """La fuyarde n'est pas morte : renseigner les deux canaux de `KillUnitOptions` mentirait sur
    un mort qui n'existe pas. `by_flight=False` (la MORT) doit, lui, les renseigner."""
    st = _state()
    vus = []
    reel = move_death.evaluate_trigger_operation

    def _espion(state, ev):
        vus.append(ev)
        return []

    move_death.evaluate_trigger_operation = _espion
    try:
        move_death.unit_defeated_triggers(st, FUYARD, HAARKEN, by_flight=True)
        move_death.unit_defeated_triggers(st, FUYARD, HAARKEN)
    finally:
        move_death.evaluate_trigger_operation = reel

    fuite, mort = vus
    assert (fuite.killer_id, fuite.dying_id) == (None, None)
    assert (fuite.actor_id, fuite.target_id) == (HAARKEN, FUYARD)
    assert (mort.killer_id, mort.dying_id) == (HAARKEN, FUYARD), \
        "le chemin MORT ne doit PAS avoir change"


# ------------------------------------------------------- [5] l'appelant seede le bon slot
def test_battle_fatigue_passe_le_caster_du_decompile():
    """`BattleFatigueAbility$$CreateBehaviour` passe `Caster@<DSLSelectors+0x48>` en 2e argument de
    `IdunBattleLogic.Entities.DSLBehaviors$$Flee` -- le port doit donc transmettre `ev.actor_id`,
    et non l'owner du passif (qui est la FUYARDE, ce qui fermerait `get_OwnerIsActor`)."""
    import inspect
    from engine.runner.operations import behaviour as BEH
    src = inspect.getsource(BEH.BattleFatigueAbility.execute_behaviour)
    assert "triggering_unit=ev.actor_id" in src, \
        "BattleFatigue ne seede pas le `triggeringUnit` du call-site natif"
    assert "triggering_unit" in inspect.signature(BEH.FleeOperation.execute).parameters


# ------------------------------------------------------- [6] #929-r1 : la 4e disjonction VIT
def _state_wulfen():
    """Ulf (`spaceWulfen`, passif `SavageKiller`) et un SUMMON ennemi ADJACENT."""
    board = Board(_tiles(), adjacency="evenq")
    units = [
        {"id": HAARKEN, "visualId": "spaceWulfen", "alive": True, "team": 1,
         "owner": 1, "pos": {"col": 2, "row": 2}, "effects": []},
        {"id": FUYARD, "visualId": "genesSmnGenestealer", "alive": True, "team": 2,
         "owner": 2, "pos": {"col": 2, "row": 3}, "effects": []},
    ]
    decision = {"currentPlayer": 1, "units": units}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000} for u in units]}
    import gameconfig as GC
    st = load_state(decision, observe, board=board)
    if st.effects is None:
        st.effects = EffectsState()
    for u in units:
        traits = list((GC.unit(u["visualId"]) or {}).get("traits") or [])
        st.get_entity(u["id"]).add_component(StatsComponent(ctx=UnitContext(
            entity_id=u["id"], visual_id=u["visualId"], traits=traits,
            passive_ability_level=50, ability_variables_multiplier=100)))
    return st


def test_929r1_un_summon_qui_devient_ciblable_SANS_avoir_bouge_declenche_savage_killer():
    """#929-r1 : `On(0x3b) & hasSummon & adjacent & enemies & NOT moved`. Le vecteur existe depuis
    #936 et la branche est abonnee depuis #981 -- ce test verifie qu'elle est ATTEIGNABLE, pas
    seulement inscrite (etre au registre ne prouve rien : c'est tout l'objet de ce lot)."""
    from engine.entities.effect_type import EffectType
    st = _state_wulfen()
    out = move_death.unit_became_targetable_triggers(st, FUYARD,
                                                     int(EffectType.TeleportStrike_TeleportingIn))
    sk = [d for d in (out or []) if isinstance(d, dict) and d.get("ability") == "SavageKiller"]
    assert len(sk) == 1, "la 4e disjonction ne fire PAS : %r" % (out,)


def test_929r1_temoin_NEGATIF_un_summon_qui_A_bouge_ne_declenche_pas():
    """Le conjoint `NOT moved` : un summon porteur d'une `PreviousTile` a BOUGE -- son arrivee est
    deja couverte par `On(UnitAfterMove)`, donc la 4e branche doit se taire (sans quoi un meme
    deplacement declencherait DEUX fois)."""
    from engine.entities.effect_type import EffectType
    from engine.runner.components import save_previous_position
    st = _state_wulfen()
    save_previous_position(st, FUYARD, [(2, 4)])          # `PositionComponent+0x88` non vide
    out = move_death.unit_became_targetable_triggers(st, FUYARD,
                                                     int(EffectType.TeleportStrike_TeleportingIn))
    sk = [d for d in (out or []) if isinstance(d, dict) and d.get("ability") == "SavageKiller"]
    assert sk == [], "`NOT moved` ne mord pas : la branche a fire sur un summon qui a bouge"


def test_929r1_temoin_NEGATIF_le_second_substrat_mord_aussi():
    """L'autre terme de la disjonction `moved` : `TurnStartTile` (`UnitComponent+0x18c`). Sans ce
    cas, le port pourrait ne lire que `PreviousTile` et rester vert."""
    from engine.entities.effect_type import EffectType
    from engine.runner.components import UnitComponent
    st = _state_wulfen()
    st.get_entity(FUYARD).get_component(UnitComponent).current_turn_start_tile = 204
    out = move_death.unit_became_targetable_triggers(st, FUYARD,
                                                     int(EffectType.TeleportStrike_TeleportingIn))
    sk = [d for d in (out or []) if isinstance(d, dict) and d.get("ability") == "SavageKiller"]
    assert sk == [], "le terme `TurnStartTile` de `moved` n'est pas lu"


@pytest.mark.parametrize("mod", [
    "engine.runner.operations.behaviour",
    "engine.runner.operations.triggers.dispatch.move_death",
    "engine.runner.operations.triggers.loki.savage_killer",
])
def test_les_modules_touches_s_importent_SEULS(mod):
    """L'invariant d'import isole : chaque module de `engine/**` s'importe seul en process FRAIS."""
    import subprocess
    import sys
    from pathlib import Path
    r = subprocess.run([sys.executable, "-c", "import %s" % mod],
                       cwd=str(Path(__file__).resolve().parents[3]),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, "import isole KO : %s" % (r.stderr or "")[-600:]
