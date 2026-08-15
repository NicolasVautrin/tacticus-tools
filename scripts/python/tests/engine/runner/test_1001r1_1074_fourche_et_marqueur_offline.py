"""GARDE #1001-r1 + #1074 (OFFLINE PURE) -- la FOURCHE `Custom` d'`ActOfFaith` et le RETRAIT du
marqueur `1061 GeminaeSuperia_JustSummonedEffect`.

CE QU'ELLE PROTEGE, et pourquoi chaque bloc peut regresser SILENCIEUSEMENT :

  1. **La fourche du reset d'`ActOfFaith`.** Le port collapsait
     `IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaith_RemoveEffectAbility$$CreateBehaviour`
     sur son seul bras `RemoveEffect`, en disant la branche `!= 0x20 = Custom` inatteignable
     (<< cross-instantiation gshared >>). Elle ne l'est pas : le corps est NOMME, propre a cette
     classe, et son jumeau de forme `...BladeOfTheAncestors_RemoveEffectAbility$$CreateBehaviour`
     -- decompile IDENTIQUE au token pres -- a ete confronte LIVE par #1001. Regression possible :
     re-collapser sur `RemoveEffect` retire les stacks AU MILIEU de la salve au lieu d'apres sa
     cloture, sans erreur ni crash, et aucun compte d'effets ne bouge a la fin du tour.
  2. **L'appariement des DEUX bras.** Le bras `!= Custom` doit ENFILER `1018` et le bras `Custom`
     doit etre joignable par `CUSTOM_TRIGGERED_ABILITIES[1018]`. Perdre l'inscription fait
     retomber `TriggerAbilityDelayed` sur son collapse INLINE herite -- donc, a nouveau, un retrait
     trop tot, et `queued` redevient faux sans que rien ne le dise.
  3. **Le conjoint `AreEnemies(Targets@+0x60, Owner@+0x30)`** du 2e stack PROBA d'
     `...ActOfFaithAbility$$CreateBehaviour`. Il etait ABSENT du port : sans lui, la branche 1 du
     `CreateTrigger` (<< un allie Imperial MEURT >>) peut accorder le stack conditionnel la ou le
     natif le reserve au cas ou la VICTIME est un ennemi. Degradation PERMISSIVE.
  4. **Les TROIS vecteurs de retrait de `1061`**, avec leurs `event_id` et leur conjoint. Le natif
     est `( On(0x3a = PhaseEnd, alive 0) | (On(0x1f = PreUnitMove, alive 1) & get_OwnerIsActor) )
     | (On(0x2a = PreUnitAbility, alive 1) & get_OwnerIsActor)`. En perdre un laisse le marqueur --
     donc, depuis #1074, laisse CELESTINE NON CIBLABLE plus longtemps que le natif.
  5. **Le conjoint `get_OwnerIsActor` des deux derniers**, exerce sur ses DEUX bras. Le poser sur
     `PhaseEnd` (qui n'a NI acteur NI cible cote port : `actor_id = -1`) eteindrait le vecteur
     DOMINANT ; l'omettre sur les deux autres ferait partir le marqueur au premier deplacement de
     n'importe qui.
  6. **L'appariement POSE <-> DOMAINE.** `1061` est dans `UNTARGETABLE_EFFECT_TYPES` PARCE QUE son
     retrait est porte. Le cran bidirectionnel de
     `test_448_r2b_stormboyz_teleporting_in_offline.py` garde la regle ; celui-ci garde qu'elle
     MORD reellement sur l'etat (l'unite redevient ciblable).

RE : `docs/rl/case-1001r1-1074-894r7-fourches-marqueurs-et-kit-derive.md`. ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import hexgeo                                                            # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType               # noqa: E402
from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.effects.aura_selectors import (                     # noqa: E402
    UNTARGETABLE_EFFECT_TYPES, is_targetable)
from engine.entities.effects_state import EffectsState                   # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.runner.operations.effects import AddEffectOperation          # noqa: E402
from engine.runner.operations.triggers.base import TriggerEvent          # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import (        # noqa: E402
    CUSTOM_TRIGGERED_ABILITIES, EFFECT_TRIGGERS, TRAIT_TRIGGERS)
from engine.runner.operations.triggers.loki.act_of_faith import (        # noqa: E402
    ACT_OF_FAITH_ABILITY, ACTOFFAITH_EFFECT, ActOfFaithCustomRemoveEffectAbility,
    ActOfFaithResetAbility)
from engine.runner.operations.triggers.loki.geminae_superia import (     # noqa: E402
    JUST_SUMMONED_EFFECT, JustSummonedRemoveOnOwnerAbility,
    JustSummonedRemoveOnOwnerMove, JustSummonedRemoveOnPhaseEnd)
from engine.runner.snapshot import load_state                            # noqa: E402

#: `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
#: Volontairement LARGE : trop etroit est un FAUX VERT (le fichier ne se rejoue pas sous `--since`
#: quand ce qu'il garde a bouge). Les quatre foyers cites sont ceux que les six blocs LISENT.
DECLENCHEUR = {
    "chemins": (
        # les DEUX arbres gardes, et leurs registres
        "scripts/python/engine/runner/operations/triggers/loki/act_of_faith.py",
        "scripts/python/engine/runner/operations/triggers/loki/geminae_superia.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        # le DOMAINE de non-ciblabilite (bloc 6) et son lecteur
        "scripts/python/engine/entities/effects/aura_selectors.py",
        # la file des differees : c'est elle qui rend `queued` vrai (blocs 1 et 2)
        "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/pending.py",
        # le noeud du conjoint verifie sur l'ARBRE (bloc 3)
        "scripts/python/engine/entities/triggers.py",
    ),
    # OFFLINE PURE : aucun RPC, aucun runner, aucune lecture de symbole du build. Les deux arbres
    # sont exerces sur un `State` monte a la main, donc un changement de build ne peut pas changer
    # ce verdict -- ce qui le changerait, ce sont les MIRRORS d'enum, et ils sont dans `chemins`
    # par leurs consommateurs.
    "build": False,
    "toujours": False,
    "raison": ("les six blocs ne lisent que ces foyers ; un changement ailleurs ne peut pas "
               "changer leur verdict sans passer par l'un d'eux (registres, arbres, domaine, file)"),
}

COLS, ROWS = 7, 7
CARRIER, ALLY, FOE = 10, 40, 20

#: Les trois vecteurs du natif, dans l'ordre des `op_BitwiseOr` du corps relu.
VECTEURS_1061 = [
    (JustSummonedRemoveOnPhaseEnd, EventTriggerType.PhaseEnd),        # 0x3a, SANS conjoint
    (JustSummonedRemoveOnOwnerMove, EventTriggerType.PreUnitMove),    # 0x1f & get_OwnerIsActor
    (JustSummonedRemoveOnOwnerAbility, EventTriggerType.PreUnitAbility),  # 0x2a & get_OwnerIsActor
]


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


@pytest.fixture
def state():
    board = Board(_tiles(), adjacency="evenq")
    decision = {"currentPlayer": 1, "units": [
        {"id": CARRIER, "visualId": "adeptCelestine", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 0, "row": 3}, "effects": []},
        {"id": ALLY, "visualId": "adeptMorvenn", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 3}, "effects": []},
        {"id": FOE, "visualId": "ultraTitus", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 6, "row": 6}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    snapshot = {"units": [{"entityId": u["id"], "entityType": 1,
                           "stats": {"health": 1000, "movement": 3, "turnsStarted": 0,
                                     "critChance": 10, "critDamage": 150},
                           "healthMax": 1000, "traits": [], "unitFlags": [],
                           "unitConfig": {"visualId": u["visualId"], "level": 50,
                                          "passiveAbilityLevel": 50, "activeAbilityLevel": 50,
                                          "abilityVariablesMultiplier": 100}}
                          for u in decision["units"]]}
    st = load_state(decision, observe, snapshot, board=board, ability_states=False)
    if st.effects is None:
        st.effects = EffectsState()
    return st


def _put(st, uid, effect_type, name):
    AddEffectOperation.execute(st, source=uid, target=uid, effect_type=int(effect_type),
                               name=name, duration_override=None)


def _live(st, uid, effect_type) -> list:
    return [e for e in (st.effects.by_unit.get(int(uid)) or [])
            if int(getattr(e, "effect_type", -1)) == int(effect_type) and not e.consumed]


def _ev(event_id, actor=CARRIER):
    return TriggerEvent(int(event_id), actor, actor, ranged=False, profile=None)


# ------------------------------------------------------------------ 1. #1074, les trois vecteurs

def test_les_trois_vecteurs_du_retrait_sont_inscrits_avec_leurs_event_id():
    """BLOC 4. `EFFECT_TRIGGERS[1061]` porte EXACTEMENT les trois classes, et leurs `event_id`
    sont ceux du corps relu -- pas l'un des trois de moins."""
    inscrites = list(EFFECT_TRIGGERS.get(int(JUST_SUMMONED_EFFECT), ()))
    assert inscrites, "aucune entree EFFECT_TRIGGERS[1061] : le retrait n'est plus porte"
    for cls, event in VECTEURS_1061:
        assert cls in inscrites, "%s absente d'EFFECT_TRIGGERS[1061]" % cls.__name__
        assert int(cls.event_id) == int(event), (
            "%s ecoute %s, le natif dit %s" % (cls.__name__, cls.event_id, int(event)))
        assert int(cls.effect_type) == int(JUST_SUMMONED_EFFECT)
    assert len(inscrites) == len(VECTEURS_1061), (
        "EFFECT_TRIGGERS[1061] porte %d classes, le corps natif en a TROIS" % len(inscrites))


@pytest.mark.parametrize("cls,event", VECTEURS_1061)
def test_chaque_vecteur_retire_reellement_le_marqueur(state, cls, event):
    """BLOC 4. Chacun des trois, EXERCE : le marqueur part et l'unite REDEVIENT ciblable.

    C'est le pendant executable du cran bidirectionnel : lui garde la REGLE (pose + retrait),
    celui-ci garde que le retrait MORD sur l'etat."""
    _put(state, CARRIER, JUST_SUMMONED_EFFECT, EffectType.GeminaeSuperia_JustSummonedEffect.name)
    assert _live(state, CARRIER, JUST_SUMMONED_EFFECT), "le marqueur n'a pas ete pose"
    assert is_targetable(state, CARRIER) is False, (
        "1061 est au domaine de non-ciblabilite : le porteur ne doit pas etre ciblable")
    r = cls(CARRIER).execute_behaviour(state, _ev(event))
    assert r is not None and r.get("removed") == 1, "le vecteur %s n'a rien retire" % cls.__name__
    assert not _live(state, CARRIER, JUST_SUMMONED_EFFECT)
    assert is_targetable(state, CARRIER) is True, (
        "le marqueur est parti mais le porteur reste non ciblable")


def test_le_conjoint_OwnerIsActor_mord_sur_les_DEUX_bras(state):
    """BLOC 5. `get_OwnerIsActor` : les deux derniers vecteurs ne firent QUE si le porteur est
    l'acteur. Le premier (`PhaseEnd`) n'a PAS ce conjoint -- et l'event ne porte ni acteur ni
    cible cote port (`actor_id = -1`), donc le lui ajouter l'eteindrait."""
    for cls, event in VECTEURS_1061[1:]:
        assert cls(CARRIER).matches(state, _ev(event, actor=CARRIER)) is True
        assert cls(CARRIER).matches(state, _ev(event, actor=ALLY)) is False, (
            "%s fire alors que l'acteur n'est pas le porteur" % cls.__name__)
    phase = VECTEURS_1061[0][0]
    assert phase(CARRIER).matches(state, TriggerEvent(int(EventTriggerType.PhaseEnd), -1, -1,
                                                     ranged=False, profile=None)) is True, (
        "le vecteur PhaseEnd est gate par un acteur : il ne firerait jamais")


def test_1061_est_au_domaine_ET_son_retrait_est_porte(state):
    """BLOC 6. L'appariement des deux faces, verifie sur les REGISTRES executables."""
    assert int(JUST_SUMMONED_EFFECT) in [int(x) for x in UNTARGETABLE_EFFECT_TYPES]
    assert EFFECT_TRIGGERS.get(int(JUST_SUMMONED_EFFECT)), (
        "1061 est au domaine SANS retrait porte : le porteur resterait non ciblable a jamais")


# ------------------------------------------------------------ 2. #1001-r1, la fourche `Custom`

def test_le_reset_ENFILE_au_lieu_de_retirer(state):
    """BLOCS 1 et 2. Bras `triggerType != Custom` = `TriggerAbilityDelayed(Owner, 0x3fa, 3)`.

    Le stack doit SURVIVRE au declenchement -- c'est tout l'objet du differe : les coups suivants
    de l'attaque qui a crite gardent le buff."""
    _put(state, CARRIER, ACTOFFAITH_EFFECT, EffectType.ActOfFaith_Effect.name)
    avant = len(_live(state, CARRIER, ACTOFFAITH_EFFECT))
    assert avant == 1
    ev = TriggerEvent(int(EventTriggerType.Attack), CARRIER, FOE, ranged=False, profile=None)
    r = ActOfFaithResetAbility(CARRIER).execute_behaviour(state, ev)
    assert r is not None and r.get("queued") is True, (
        "le reset n'a pas ENFILE : le noeud est retombe sur son collapse INLINE")
    assert len(_live(state, CARRIER, ACTOFFAITH_EFFECT)) == avant, (
        "le stack a ete retire SUR PLACE -- un cran trop tot (#1001-r1)")
    assert state.pending_triggered_abilities, "la file des differees est vide"
    assert any(int(a) == int(ACT_OF_FAITH_ABILITY)
               for (_u, a, _e) in state.pending_triggered_abilities)


def test_la_branche_Custom_est_inscrite_et_retire(state):
    """BLOCS 1 et 2. Bras `triggerType == Custom` = `RemoveEffect(Owner, Nullable(0x3f9))`,
    joignable UNIQUEMENT par le drain."""
    assert ActOfFaithCustomRemoveEffectAbility in list(
        CUSTOM_TRIGGERED_ABILITIES.get(int(ACT_OF_FAITH_ABILITY), ())), (
        "CUSTOM_TRIGGERED_ABILITIES[1018] ne porte pas la branche Custom : `TriggerAbilityDelayed` "
        "retomberait sur le collapse INLINE")
    _put(state, CARRIER, ACTOFFAITH_EFFECT, EffectType.ActOfFaith_Effect.name)
    ev = TriggerEvent(int(EventTriggerType.Custom), CARRIER, None, ranged=False, profile=None)
    r = ActOfFaithCustomRemoveEffectAbility(CARRIER).execute_behaviour(state, ev)
    assert r is not None and r.get("removed") == 1
    assert not _live(state, CARRIER, ACTOFFAITH_EFFECT)


def test_l_autre_classe_de_1018_n_est_PAS_inscrite_au_registre_Custom():
    """BLOC 2, cote NEGATIF. `ActOfFaithAbility` a elle aussi une branche `Custom`, et elle vaut
    `DSLBehaviors$$Nothing()` : le natif l'appelle au drain et elle ne fait RIEN. L'inscrire serait
    un mensonge de couverture -- meme arbitrage que `BladeOfTheAncestors` (1491)."""
    inscrites = [c.__name__ for c in CUSTOM_TRIGGERED_ABILITIES.get(int(ACT_OF_FAITH_ABILITY), ())]
    assert inscrites == ["ActOfFaithCustomRemoveEffectAbility"], (
        "CUSTOM_TRIGGERED_ABILITIES[1018] porte %s -- la classe d'accumulation ne doit PAS y etre "
        "(sa branche Custom est un no-op natif)" % inscrites)
    assert int(ACT_OF_FAITH_ABILITY) == int(TriggeredAbilityType.ActOfFaithAbility) == 0x3FA


def test_le_conjoint_AreEnemies_est_dans_l_arbre_d_accumulation():
    """BLOC 3. `AreEnemies(Targets@+0x60, Owner@+0x30, 0)` -- le conjoint que le port n'avait pas.

    Verifie sur l'ARBRE construit, pas sur le texte du module : c'est la structure qui compte."""
    from engine.entities.triggers import AreEnemies
    from engine.runner.operations.triggers.loki.act_of_faith import act_of_faith_accumulate_tree

    vus, pile = [], [act_of_faith_accumulate_tree(ACTOFFAITH_EFFECT)]
    while pile:
        n = pile.pop()
        vus.append(type(n).__name__)
        for attr in ("a", "b", "left", "right", "cond", "body", "inner", "trigger", "behaviour"):
            enfant = getattr(n, attr, None)
            if enfant is not None and hasattr(enfant, "__class__"):
                pile.append(enfant)
    assert AreEnemies.__name__ in vus, (
        "le conjoint `AreEnemies(Target, Owner)` du 2e stack PROBA est absent de l'arbre : le "
        "stack conditionnel tomberait aussi quand un ALLIE meurt (#1001-r1)")


def test_ActOfFaith_reste_accroche_a_son_trait():
    """Non-regression de cablage : les deux classes du bus restent sur le trait `ActOfFaith`.
    La branche `Custom`, elle, n'y est PAS -- elle n'est joignable que par le drain."""
    classes = [c.__name__ for c in TRAIT_TRIGGERS.get("ActOfFaith", ())]
    assert "ActOfFaithAccumulateAbility" in classes and "ActOfFaithResetAbility" in classes
    assert "ActOfFaithCustomRemoveEffectAbility" not in classes
