"""GARDE #BL-1029r (OFFLINE PURE) -- `Drachnyen_ExtraAttackAbility` (triggered 1485) et l'ETAGE
qu'il a fallu ajouter pour qu'elle puisse firer.

CE QU'ELLE PROTEGE. Cinq choses peuvent regresser ici sans qu'aucun autre test ne rougisse, et
QUATRE d'entre elles etaient ECRITES DE TRAVERS dans la fiche de RE avant que le decompile ne les
corrige (`docs/rl/case-bl-1029-1020.md` Sec.7.1) :

  1. **LE CHEMIN DE REGISTRATION** -- `ACTIVE_ABILITY_TRIGGERS["Drachnyen"]`, la voie
     `activeAbilities` -> triggered DERIVEE. `StaticBattleRules.ActiveAbility$$.cctor` range en
     `<statics>+0x30` l'entree `GetDerivedTriggeredAbilities[0x405] = [0x5cd]`. La fiche annoncait
     `EFFECT_TRIGGERS[1471]` : par cette voie l'owner aurait COINCIDE (l'effet 1471 est pose sur
     Abaddon lui-meme), donc l'erreur aurait ete INVISIBLE au test de comportement.
  2. **LA CONFIG LUE EST CELLE DE L'ACTIVE 1029** -- `StaticBattleRules.**TriggeredAbility**$$.cctor`
     range en `<statics>+0x48` l'entree `GetActiveAbilityUsedForConfig[0x5cd] = 0x405`, PREMIERE
     branche d'`AbilitiesDatabase$$GetConfig`. Le gameconfig n'a **aucune** entree
     `Drachnyen_ExtraAttack` : sans cette lecture, la magnitude serait inventee.
  3. **LE SELECTEUR EST `NonSteppableUnits`, PAS `NonSteppableOrObjectUnits`** -- Steppable SEUL.
     Un `Object` adjacent est une cible VALIDE. Les deux factories existent cote natif et se
     ressemblent ; recopier la mauvaise rendrait le pool trop ETROIT, donc le port trop faible.
  4. **LES CINQ CONJOINTS DU TRIGGER**, chacun exerce SEUL : `On(0x26 = NormalAttack)`,
     `get_OwnerIsCaster`, `IsMeleeAttack`, `<DSLTriggers+0x20> = OwnerIsAlive`,
     `HasEffect(Owner, 0x5bf = 1471)`, plus `AmountIsGreaterThanZero(pool)`. Chaque conjoint
     manquant rend le port PERMISSIF -- et un port permissif est vert partout ou on ne le cherche pas.
  5. **L'ETAGE `On(0x26)` A LA PORTE `UseActiveAbility`** -- c'est LUI qui se re-cassera, pas le
     trigger. Le natif n'a qu'UN site d'emission (`ALoki_NormalAttackAbility$$
     ExecuteTriggerAbilities`, a la CLOTURE de l'attaque normale, quelle que soit la PORTE) ; le
     port ne l'emettait que depuis la voie MESSAGE, si bien qu'une attaque normale dispatchee par
     une ability ne reveillait AUCUN trigger `On(0x26)`. Mesure : **6 coups offline contre 10 live**
     avant, **9** apres, les 3 neufs bit-exacts.

Confront LIVE de bout en bout (compte de coups et per-coup) :
`python scripts/python/probe_bl_1029_1020_baseline.py --only drachnyen`.
RE : `docs/rl/case-bl-1029-1020.md` Sec.7.1. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER, perimetre pris LARGE : `dispatch/registry.py` importe la TOTALITE
        # des modules `loki/**`, et l'etage `On(0x26)` vit dans la couche behaviours. Foyers
        # load-bearing pour la relecture : `operations/triggers/loki/drachnyen.py` (le port),
        # `operations/triggers/dispatch/registry.py` (le cablage),
        # `runner/abilities/behaviours/combat.py` (l'ETAGE), `entities/selectors/units.py`
        # (`non_steppable_units`), `operations/damage_utility.py` (le tri).
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment.
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        # `nrOfHits`/`damageProfile`/`minDmg`/`maxDmg` viennent de la config `Drachnyen` du BUILD,
        # et les mirrors d'enum (`TriggeredAbilityType`, `EffectType`) du dump.
        "data/symbols/**",
        # ⚠ MESURE, pas supposition (`probe_486r15` l'a rougi) : le pool passe par
        # `operations/damage_utility.py`, dont les POIDS d'utilite viennent du bloc `Utilities` du
        # seed BC (`engine/weights.py::load`). Le fichier est donc dans la fermeture REELLE meme si
        # aucun test n'en parle.
        "data/seed-bc.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : la voie de registration `ACTIVE_ABILITY_TRIGGERS` (et l'ABSENCE "
              "d'`EFFECT_TRIGGERS[1471]`), la config lue = celle de l'ACTIVE 1029, le selecteur "
              "`NonSteppableUnits` (un Object RESTE cible), les six conjoints du `CreateTrigger` "
              "exerces UN A UN, et l'emission d'`On(0x26)` par la feuille `UseActiveAbility`. "
              "Aucun runner, aucune session Frida : le seul acces disque est le depot.",
}

import pytest

from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.effect_type import EffectType
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType

DRACHNYEN_ABILITY = "Drachnyen"
EXTRA_ATTACK_EFFECT = int(EffectType.Drachnyen_ExtraAttack)               # 0x5bf = 1471
EXTRA_ATTACK_TRIGGERED = int(TriggeredAbilityType.Drachnyen_ExtraAttack)  # 0x5cd = 1485
ABADDON, ENNEMI_A, ENNEMI_B, ALLIE = 83, 77, 79, 85


# --------------------------------------------------------------------------------------------
# 1. LE CHEMIN DE REGISTRATION
# --------------------------------------------------------------------------------------------

def test_la_voie_est_ACTIVE_ABILITY_TRIGGERS_et_PAS_EFFECT_TRIGGERS():
    """`GetDerivedTriggeredAbilities[0x405] = [0x5cd]` -- montee par
    `UnitFactory$$AddDerivedAbilities` des l'init de toute unite qui POSSEDE l'active 1029.
    L'inscrire dans `EFFECT_TRIGGERS[1471]` aurait coincide par accident (l'effet est pose sur
    Abaddon lui-meme) : c'est exactement le genre d'erreur qu'un test de comportement ne voit pas."""
    from engine.runner.operations.triggers.dispatch.registry import (ACTIVE_ABILITY_TRIGGERS,
                                                                     EFFECT_TRIGGERS)
    from engine.runner.operations.triggers.loki.drachnyen import DrachnyenExtraAttackAbility
    assert DrachnyenExtraAttackAbility in (ACTIVE_ABILITY_TRIGGERS.get(DRACHNYEN_ABILITY) or [])
    assert DrachnyenExtraAttackAbility not in (EFFECT_TRIGGERS.get(EXTRA_ATTACK_EFFECT) or [])


def test_lability_est_montee_pour_une_unite_qui_possede_lACTIVE_1029():
    """Bout en bout du rail : `collect_triggered_abilities` doit instancier la classe pour une
    unite dont le kit porte `Drachnyen` en `activeAbilities` -- et pour elle seule."""
    from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
    from engine.runner.operations.triggers.loki.drachnyen import DrachnyenExtraAttackAbility
    st = _state()
    portees = [t for t in collect_triggered_abilities(st)
               if isinstance(t, DrachnyenExtraAttackAbility)]
    assert [t.owner_id for t in portees] == [ABADDON]


# --------------------------------------------------------------------------------------------
# 2. LA CONFIG LUE
# --------------------------------------------------------------------------------------------

def test_la_config_lue_est_celle_de_lACTIVE_1029():
    """`GetActiveAbilityUsedForConfig[0x5cd] = 0x405`. Il n'existe AUCUNE entree gameconfig
    `Drachnyen_ExtraAttack` : si le port lisait son propre nom, `nrOfHits` vaudrait 0 et l'attaque
    serait un no-op SILENCIEUX (`execute_behaviour` rend None)."""
    import gameconfig as GC
    from engine.runner.operations.triggers.loki import drachnyen as D
    assert GC.ability("Drachnyen_ExtraAttack") is None, \
        "montage : une entree homonyme existe desormais -- la lecture doit etre re-tranchee"
    assert D.DRACHNYEN_ABILITY == DRACHNYEN_ABILITY
    consts = (GC.ability(DRACHNYEN_ABILITY) or {}).get("constants") or {}
    assert int(consts.get("nrOfHits") or 0) > 0
    assert D._damage_profile_or_default() == consts.get("damageProfile")


# --------------------------------------------------------------------------------------------
# 3. LE SELECTEUR -- Steppable SEUL
# --------------------------------------------------------------------------------------------

def _state(effet_1471=True, abaddon_vivant=True, traits_ennemi_a=()):
    """`State` minimal : Abaddon (active `Drachnyen`), deux ennemis ADJACENTS, un allie adjacent."""
    from engine.entities.effects_state import EffectsState
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import (OwnerComponent, PositionComponent, StatsComponent,
                                          UnitComponent)
    from engine.runner.operations.effects import AddEffectOperation
    from engine.runner.state import State
    # Board 6x6 plein. ⚠ Le champ `neighbours` est OBLIGATOIRE : `Board` lit la liste d'adjacence
    # STOCKEE (c'est ce que rend `boardGraph` en live), il ne la derive pas de la geometrie -- sans
    # lui `neighbours()` rend `[]` et TOUT le pool est vide, ce qui se lirait comme un rouge de
    # fond alors que c'est le montage.
    import hexgeo
    tiles = []
    for c in range(6):
        for r in range(6):
            tiles.append({"id": c * 6 + r + 1, "col": c, "row": r, "walkable": True,
                          "isWall": False, "elevation": 0,
                          "neighbours": [cc * 6 + rr + 1 for (cc, rr) in hexgeo.neighbors(c, r)
                                         if 0 <= cc < 6 and 0 <= rr < 6]})
    st = State()
    st.effects = EffectsState()
    st.board = Board(tiles)
    for uid, vis, team, pos in ((ABADDON, "blackAbaddon", 1, (2, 2)),
                                (ENNEMI_A, "necroWarden", 2, (2, 3)),
                                (ENNEMI_B, "necroDestroyer", 2, (3, 2)),
                                (ALLIE, "blackHaarken", 1, (1, 2))):
        e = st.add_entity(uid)
        uc = UnitComponent(vis, uid != ABADDON or abaddon_vivant)
        e.add_component(uc)
        e.add_component(OwnerComponent(team, team + 2))
        e.add_component(PositionComponent(pos[0], pos[1]))
        ctx = _UnitCtx(vis, list(traits_ennemi_a) if uid == ENNEMI_A else [])
        e.add_component(StatsComponent(ctx))
    if effet_1471:
        AddEffectOperation.execute(st, source=ABADDON, target=ABADDON,
                                   effect_type=EXTRA_ATTACK_EFFECT,
                                   name=EffectType.Drachnyen_ExtraAttack.name)
    return st


class _UnitCtx:
    """Substitut minimal d'`UnitContext` : ce que le pool et le registre LISENT, rien de plus."""

    def __init__(self, visual_id, traits):
        self.visual_id = visual_id
        self.traits = list(traits)
        self.active_ability_level = 50
        self.ability_variables_multiplier = 180
        self.passive_abilities = None
        self.config_active_abilities = None
        self.tertiary_ability = None
        self.triggered_abilities = None

    def stat(self, _s):
        return 0


def test_le_pool_est_NonSteppableUnits_donc_un_Object_RESTE_cible():
    """`NonSteppableUnits` retire `UnitTrait.Steppable` (0x1b) et RIEN d'autre. Son homonyme
    `NonSteppableOrObjectUnits` retirerait aussi `UnitTrait.Object` (0xd) -- le port serait alors
    trop ETROIT, ce qu'aucun test de degat ne montre (une cible en moins n'est pas une erreur)."""
    from engine.runner.operations.triggers.loki.drachnyen import DrachnyenExtraAttackAbility
    trig = DrachnyenExtraAttackAbility(ABADDON)
    st = _state(traits_ennemi_a=[UnitTrait.Object.name])
    ids = {u.get("id") for u in trig._pool(st)}
    assert ENNEMI_A in ids, "un Object adjacent doit RESTER dans le pool"
    st2 = _state(traits_ennemi_a=[UnitTrait.Steppable.name])
    ids2 = {u.get("id") for u in DrachnyenExtraAttackAbility(ABADDON)._pool(st2)}
    assert ENNEMI_A not in ids2, "un Steppable doit SORTIR du pool"
    assert ENNEMI_B in ids2, "temoin non nul : le pool n'est pas vide par accident"


def test_le_pool_ne_retient_que_les_ENNEMIS_adjacents():
    from engine.runner.operations.triggers.loki.drachnyen import DrachnyenExtraAttackAbility
    ids = {u.get("id") for u in DrachnyenExtraAttackAbility(ABADDON)._pool(_state())}
    assert ids == {ENNEMI_A, ENNEMI_B}, "l'allie adjacent ne doit pas y etre"


# --------------------------------------------------------------------------------------------
# 4. LES CONJOINTS DU TRIGGER, UN A UN
# --------------------------------------------------------------------------------------------

def _ev(actor=ABADDON, target=ENNEMI_A, ranged=False):
    from engine.runner.operations.triggers.base import TriggerEvent
    return TriggerEvent(EventTriggerType.NormalAttack, actor, target,
                        ranged=ranged, profile="Power")


def test_le_vecteur_est_On_NormalAttack():
    from engine.runner.operations.triggers.loki.drachnyen import DrachnyenExtraAttackAbility
    assert DrachnyenExtraAttackAbility.event_id == EventTriggerType.NormalAttack   # 0x26
    assert DrachnyenExtraAttackAbility.TRIGGERED_ABILITY_ID == \
        TriggeredAbilityType.Drachnyen_ExtraAttack


def test_le_cas_NOMINAL_matche_temoin_non_nul():
    """Sans ce temoin, les cinq refus ci-dessous ne prouveraient rien (un `matches` toujours faux
    les passerait tous)."""
    from engine.runner.operations.triggers.loki.drachnyen import DrachnyenExtraAttackAbility
    assert DrachnyenExtraAttackAbility(ABADDON).matches(_state(), _ev()) is True


@pytest.mark.parametrize("conjoint,st_kw,ev_kw", [
    ("get_OwnerIsCaster", {}, {"actor": ENNEMI_B}),
    ("IsMeleeAttack", {}, {"ranged": True}),
    ("OwnerIsAlive", {"abaddon_vivant": False}, {}),
    ("HasEffect(Owner, 1471)", {"effet_1471": False}, {}),
])
def test_chaque_conjoint_du_trigger_REFUSE_seul(conjoint, st_kw, ev_kw):
    from engine.runner.operations.triggers.loki.drachnyen import DrachnyenExtraAttackAbility
    trig = DrachnyenExtraAttackAbility(ABADDON)
    assert trig.matches(_state(**st_kw), _ev(**ev_kw)) is False, conjoint


def test_AmountIsGreaterThanZero_refuse_quand_le_pool_est_VIDE():
    """Dernier conjoint : `AmountIsGreaterThanZero(NonSteppableUnits(AdjacentEnemies(Owner)))`.
    On ECARTE les deux ennemis au lieu de les supprimer -- le montage reste une bataille."""
    from engine.runner.components import PositionComponent
    from engine.runner.operations.triggers.loki.drachnyen import DrachnyenExtraAttackAbility
    st = _state()
    for uid, pos in ((ENNEMI_A, (5, 5)), (ENNEMI_B, (5, 4))):
        pc = st.get_entity(uid).get_component(PositionComponent)
        pc.col, pc.row = pos
    trig = DrachnyenExtraAttackAbility(ABADDON)
    assert trig._pool(st) == []
    assert trig.matches(st, _ev()) is False


# --------------------------------------------------------------------------------------------
# 5. L'ETAGE -- `On(0x26)` a la porte `UseActiveAbility`
# --------------------------------------------------------------------------------------------

def test_UseActiveAbility_EMET_le_vecteur_On_NormalAttack():
    """C'est l'etage qui se re-cassera. Le natif n'a qu'UN site d'emission, a la CLOTURE de
    l'attaque normale, quelle que soit la PORTE ; le port en avait DEUX dont un muet. On SUBSTITUE
    `after_hit_normal_attack` au module qui le consomme (forme B, la seule qui morde) et on
    verifie qu'il est appele avec l'attaquant et la cible de l'attaque dispatchee."""
    import engine.runner.operations.triggers.dispatch.attack as A
    from engine.dsl.effects import ExecutionContext
    from engine.runner.abilities.behaviours.combat import UseActiveAbility
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.entities.selectors.accessors import Target
    from engine.entities.selectors.tiles import Caster
    import engine.runner.operations.damage as DMG

    vus = []
    orig_after = A.after_hit_normal_attack
    orig_exec = DMG.AttackDamageOperation.execute
    A.after_hit_normal_attack = lambda st, a, t, *ar, **kw: (vus.append((a, t)) or [])
    DMG.AttackDamageOperation.execute = staticmethod(
        lambda st, a, t, *ar, **kw: {"target": t, "ranged": False, "profile": "Power",
                                     "did_crit": False, "did_block": False, "finish_attack": []})
    try:
        st = _state()
        st.rng = object()                      # non nul : la feuille refuse de dispatcher sans rng
        ectx = ExecutionContext(state=st, rng=st.rng)
        UseActiveAbility(Caster(), Target()).execute(
            entities_from_state(st, ABADDON, ENNEMI_A), ectx)
    finally:
        A.after_hit_normal_attack = orig_after
        DMG.AttackDamageOperation.execute = orig_exec
    assert vus == [(ABADDON, ENNEMI_A)], \
        "la porte `UseActiveAbility` doit emettre `On(0x26)` avec l'attaquant et la cible reels"
