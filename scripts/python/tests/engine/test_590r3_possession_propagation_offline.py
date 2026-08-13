"""#590-r3 -- la PROPAGATION de `1209 AttemptedPossession_Possessed` aux summons qui apparaissent.

`IdunBattle.Entities.Effects.Loki.AttemptedPossession_PossessedEffect$$CreateHandleTriggerAbilitiesInternal`
greffe sur l'effet un `Triggered(On(0x32 UnitAdded) & AmountIsZero(Count(Parent(Owner))) &
AreEqual(Parent(Actor), Owner), AddBondEffect(0x4b9, targets = Actor,
bondedEntity = BondedEntityFromEffect(Effect), turns = 1))` -- rien de tout cela n'etait porte : ni
la propagation, ni les retraits HERITES d'`ABondEffect` (`1209` etait absent de `EFFECT_TRIGGERS`
**et** de `BOND_REMOVAL_GATES`).

Les gates HERITES sont desormais MESURES et non supposes
(`probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step declared`, 2026-08-13) :
`get_Range = OWN none`, `get_Adjacent = OWN false`, `get_RemoveOnBondedEntityDeath = OWN true`.
Un seul des trois retraits s'arme donc, et ce fichier le garde des DEUX cotes : le (a) mord, les
(b)/(c) ne doivent PAS etre inscrits.

OFFLINE INTEGRAL : `State` synthetique, aucun runner, aucun RPC. La face LIVE de `1101` est deja
gardee par `probe_590` / `test_590_attempted_possession_offline.py` ; ce qui manquait ici est un
vecteur `On(UnitAdded)` PENDANT une possession, que le harnais ne produit pas spontanement (il
faudrait que la proie possedee invoque, et Thaumachus lui commande une ATTAQUE).

ASCII only (console cp1252).
"""
from __future__ import annotations

import pytest

from engine.entities.effect_type import EffectType
from engine.entities.effects.base import BaseEffect
from engine.entities.effects_state import EffectsState
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent)
from engine.runner.operations.spawn import on_unit_added
from engine.runner.operations.triggers.bond_removal import (BOND_REMOVAL_GATES,
                                                            BondRemoveOnAdjacencyLost,
                                                            BondRemoveOnBondedEntityDeath,
                                                            BondRemoveOnRangeExceeded,
                                                            bond_removal_registry_entries)
from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
from engine.runner.operations.triggers.loki.attempted_possession import (
    POSSESSED, PROPAGATION_TURNS, AttemptedPossessionPropagate)
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.state import State


#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # VIDE : le trigger, le registre, la table de retrait et le vecteur `on_unit_added` sont tous
    # dans la fermeture d'imports de ce fichier, donc dans la cascade DERIVEE par le foyer.
    "chemins": (),
    # FAUX : aucune magnitude ne vient du gameconfig -- le `turns` est le litteral
    # `<DSLFormulas+0x20>` et les trois gates sont des constantes MESUREES, figees ici.
    "build": False,
    "toujours": False,
    "raison": (
        "Ce fichier garde UN trigger et son cablage : que `On(UnitAdded)` propage `1209` au summon "
        "de l'unite possedee, que les deux gates du `Triggered()` discriminent, et que le SEUL "
        "retrait herite arme soit le (a). Rien n'y depend du gameconfig ni d'un runner."
    ),
}

CASTER, ROOT, SUMMON, ETRANGER = 10, 11, 12, 13


class _Ctx:
    def __init__(self):
        self.traits = []
        self.active_ability_level = 50
        self.passive_ability_level = 50
        self.ability_variables_multiplier = 100


def _unite(st: State, uid: int, *, team: int = 1, parent=None, pos=(0, 0)) -> int:
    e = st.add_entity(uid)
    e.add_component(UnitComponent("u%d" % uid, True, parent_id=parent))
    e.add_component(OwnerComponent(team, team))
    e.add_component(HealthComponent(1000, 1000))
    e.add_component(StatsComponent(ctx=_Ctx()))
    e.add_component(PositionComponent(int(pos[0]), int(pos[1])))
    return uid


@pytest.fixture
def montage():
    """FIXTURE NOMMEE : Thaumachus (`CASTER`) possede `ROOT` ; `SUMMON` est un enfant de `ROOT`,
    `ETRANGER` un enfant de personne. Chaque face negative se fabrique en changeant UNE piece."""
    def _monter(root_a_un_parent: bool = False, bonde: bool = True):
        st = State()
        st.effects = EffectsState()
        st.rng = IntBasedMersenneTwister(777)
        _unite(st, CASTER, team=1, pos=(0, 0))
        _unite(st, ROOT, team=2, parent=(CASTER if root_a_un_parent else None), pos=(1, 0))
        _unite(st, SUMMON, team=2, parent=ROOT, pos=(2, 0))
        _unite(st, ETRANGER, team=2, parent=None, pos=(3, 0))
        eff = BaseEffect(name=EffectType.AttemptedPossession_Possessed.name,
                         effect_type=POSSESSED, source=CASTER, target=ROOT)
        if bonde:
            eff.bonded = CASTER
        st.effects.by_unit.setdefault(ROOT, []).append(eff)
        return st
    return _monter


def _bonds(st: State, uid: int):
    return [(int(e.effect_type), getattr(e, "bonded", None))
            for e in (st.effects.by_unit.get(int(uid)) or []) if not e.consumed]


# --------------------------------------------------- 1. le CABLAGE (le residu, litteralement)
def test_1209_est_inscrit_au_registre_des_triggers_d_effet():
    """`1209` etait absent d'`EFFECT_TRIGGERS` : le `Triggered()` greffe par
    `CreateHandleTriggerAbilitiesInternal` n'avait AUCUN porteur cote port."""
    classes = EFFECT_TRIGGERS.get(POSSESSED) or []
    assert AttemptedPossessionPropagate in classes, "la propagation n'est pas inscrite"


def test_les_trois_retraits_herites_sont_MESURES_et_un_SEUL_est_arme():
    """`--step declared` sur `AttemptedPossession_PossessedEffect` : `get_Range` = none,
    `get_Adjacent` = false, `get_RemoveOnBondedEntityDeath` = true. L'inscription est DERIVEE de la
    table, donc ces trois valeurs sont exactement ce qui decide des triggers -- les figer ici est ce
    qui empeche qu'une des deux faces derive sans l'autre."""
    g = BOND_REMOVAL_GATES.get(POSSESSED)
    assert g is not None, "1209 etait absent de BOND_REMOVAL_GATES -- les 3 retraits herites aussi"
    assert g.native == "IdunBattle.Entities.Effects.Loki.AttemptedPossession_PossessedEffect"
    assert g.remove_on_bonded_entity_death is True, "get_RemoveOnBondedEntityDeath = OWN true"
    assert g.range is None, "get_Range = OWN none -> PAS de retrait (b) IsInRange"
    assert g.adjacent is False, "get_Adjacent = OWN false -> PAS de retrait (c) IsAdjacent"

    derives = [c for et, c in bond_removal_registry_entries() if et == POSSESSED]
    assert derives == [BondRemoveOnBondedEntityDeath], (
        "un SEUL retrait doit etre derive ; (b)/(c) inscrits ici retireraient la possession a la "
        "distance ou a la rupture d'adjacence -- or le cast ENVOIE la proie attaquer, donc "
        "s'eloigner de Thaumachus")
    assert BondRemoveOnRangeExceeded not in derives
    assert BondRemoveOnAdjacencyLost not in derives


# ------------------------------------------------ 2. le COMPORTEMENT : la propagation MORD
def test_le_summon_qui_apparait_est_POSSEDE_a_son_tour(montage):
    """Le coeur du residu : `On(UnitAdded)` sur un enfant de l'unite possedee pose `1209` sur lui,
    bonde au MEME caster."""
    st = montage()
    assert _bonds(st, SUMMON) == [], "montage : le summon ne doit rien porter avant l'event"
    out = on_unit_added(st, SUMMON)
    assert _bonds(st, SUMMON) == [(POSSESSED, CASTER)], (
        "le summon n'est PAS possede -- la propagation ne mord pas (%s)" % (out,))


def test_le_bond_du_summon_dure_UN_tour(montage):
    """`turns = <DSLFormulas+0x20> = Direct(1)`, et c'est un `turns`, pas un `rounds` : le passer en
    rounds DOUBLERAIT la duree (`TurnsFromRounds`)."""
    st = montage()
    on_unit_added(st, SUMMON)
    e = [x for x in st.effects.by_unit[SUMMON] if int(x.effect_type) == POSSESSED][0]
    assert PROPAGATION_TURNS == 1
    assert int(e.remaining_turns) == 1, \
        "duree != 1 tour -- le passer en `rounds` la DOUBLERAIT (`TurnsFromRounds`)"


# ------------------------- 3. les DEUX gates DISCRIMINENT (sinon le test 2 ne garde rien)
def test_une_unite_qui_n_est_PAS_enfant_du_porteur_n_est_pas_possedee(montage):
    """`AreEqual(Parent(Actor), Owner)` : une unite qui apparait sans lien de summon avec le porteur
    ne recoit rien."""
    st = montage()
    on_unit_added(st, ETRANGER)
    assert _bonds(st, ETRANGER) == [], "propagation a une unite qui n'est pas un enfant du porteur"


def test_un_porteur_qui_a_LUI_MEME_un_parent_ne_propage_PAS(montage):
    """`AmountIsZero(Count(Parent(Owner)))` : seule la cible RACINE propage. Sans ce gate, un summon
    deja possede possederait ses propres summons -- une CHAINE que le natif n'a pas.

    ⚠ C'est le gate dont la lecture LITTERALE d'`AmountIsZero` (`x <= 1`) ferait un no-op toujours
    vrai ; le port suit la semantique MESUREE (`x == 0`), et cette garde est ce qui rend les deux
    lectures DISCERNABLES."""
    st = montage(root_a_un_parent=True)
    on_unit_added(st, SUMMON)
    assert _bonds(st, SUMMON) == [], "propagation en CHAINE depuis un porteur qui a un parent"


def test_sans_bondedEntity_resoluble_rien_n_est_pose(montage):
    """Le behaviour LIT `BondedEntityFromEffect(Effect)` DEUX fois (source ET bondedEntity). Sans
    bonde, le natif passe un selecteur VIDE : on ne fabrique pas un bond sans son ancre."""
    st = montage(bonde=False)
    on_unit_added(st, SUMMON)
    assert _bonds(st, SUMMON) == [], "bond pose alors que l'effet source n'a AUCUN bondedEntity"
