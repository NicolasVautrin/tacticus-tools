"""#937-r1 -- la branche `owner MORT + FinalJustice` de `SynapticLinchpin` est-elle ATTEIGNABLE ?

CE QUE CE FICHIER GARDE, ET POURQUOI IL EXISTE
----------------------------------------------
Le passif `SynapticLinchpin` (1192, `tyranWingedPrime`) a un gate effectif
`OwnerIsAlive | (OwnerIsActor & TriggeringAbilityIs(FinalJustice))` -- il survit donc a la mort de
son porteur QUAND c'est LUI qui frappe, via l'attaque post-mortem du trait `FinalJustice`. Ce
disjunct etait porte dans `_owner_alive_or_final_justice` et **INERTE** : `dispatch/core.py` ecarte
tout porteur non vivant AVANT `matches`, et l'attribut qui leve ce gate (`fire_on_death`) valait
FAUX pour cette ability.

La valeur a ete LUE (#10015) : `SynapticLinchpinAbility$$get_AllowForDeadOwner`
(`IdunBattle.Entities.Abilities.ITriggeredAbility` slot 8, surcharge au slot 22 de la vtable) rend
**VRAI** -- corps `b0 01 c3`, PARTAGE avec `FinalJusticeAbility$$get_AllowForDeadOwner`. Le natif
laisse donc bien passer le porteur mort jusqu'a `ShouldTrigger`.

⚠ **CE QUI REND CETTE GARDE NECESSAIRE PLUTOT QUE SUPERFLUE** : le fix tient en UN attribut de
classe, et rien d'autre dans le depot ne le lit -- `dispatch/core.py::evaluate_trigger_operation`
est son unique lecteur. Un futur nettoyage qui le retirerait ne casserait AUCUN test existant : la
branche redeviendrait inatteignable EN SILENCE, exactement l'etat dont ce residu sort. Les deux
bras ci-dessous font donc porter l'assertion sur le COMPORTEMENT (le trigger est-il EVALUE ?),
jamais sur la valeur de l'attribut.

⚠ **ET LE REGIME EST ETROIT** : un porteur mort ne passe que s'il est LUI-MEME l'acteur ET que le
coup vient de `FinalJustice`. Les trois bras negatifs le verifient un par un -- sans eux, un
`fire_on_death` pose sans le disjunct passerait pour un fix.

100 % OFFLINE. ASCII only (cp1252).
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
#: `chemins` VIDE, et c'est un RESULTAT, pas un aveu : la fermeture d'imports de ce fichier
#: (749 modules, derivee par le foyer depuis #531) tient ENTIEREMENT dans la cascade -- il
#: n'atteint aucun module par `sys.path` que le paquet n'importerait pas.
#: `build: True` (== `data/symbols/**`) est le seul ajout, et il ne vient PAS des imports :
#: l'etage `test_l_attribut_vaut_ce_que_le_build_dit` LIT
#: `data/symbols/*/metadata/allow_for_dead_owner.tsv` par `read_text`, exactement la lecture
#: qu'une derivation par imports ne peut pas voir -- et c'est elle qui fige le fait du residu
#: (`SynapticLinchpinAbility$$get_AllowForDeadOwner` rend VRAI, corps `b0 01 c3` PARTAGE avec
#: `FinalJusticeAbility$$get_AllowForDeadOwner`). Une MAJ du jeu la deplace.
DECLENCHEUR = {
    "chemins": (),
    "build": True,
    "toujours": False,
    "raison": "branche `owner MORT + FinalJustice` de `SynapticLinchpin` (1192) : les quatre "
              "bras de comportement passent par la cascade du paquet `engine`, et le cinquieme "
              "confronte l'attribut `fire_on_death` a `data/symbols/*/metadata/"
              "allow_for_dead_owner.tsv`, LU au build -- seule entree hors imports.",
}

import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[3]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from engine.runner.state import State                                       # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,      # noqa: E402
                                      PositionComponent, StatsComponent, UnitComponent)
from engine.runner.operations.triggers.base import TriggerEvent             # noqa: E402
from engine.runner.operations.triggers.dispatch import core as CORE         # noqa: E402
from engine.runner.operations.triggers.loki.synaptic_linchpin import (      # noqa: E402
    SynapticLinchpinAbility)
from engine.entities.triggered_ability_type import TriggeredAbilityType     # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                     # noqa: E402

PRIME = "tyranWingedPrime"
NIVEAU = 50
FINAL_JUSTICE = int(TriggeredAbilityType.FinalJustice)                       # 1024


class _Ctx:
    """`UnitContext` minimal : ce que `collect_triggered_abilities` et les noeuds DSL lisent."""

    def __init__(self, visual_id: str, traits=()):
        self.visual_id = visual_id
        self.traits = list(traits)
        self.passive_abilities = None
        self.config_active_abilities = None
        self.tertiary_ability = None
        self.active_ability_level = NIVEAU
        self.passive_ability_level = NIVEAU
        self.ability_variables_multiplier = 100


def _unite(st: State, uid: int, visual_id: str, *, team: int, vivant: bool,
           traits=(), pos=(0, 0)) -> int:
    e = st.add_entity(uid)
    e.add_component(UnitComponent(visual_id, vivant))
    e.add_component(OwnerComponent(team, team))
    e.add_component(HealthComponent(1000 if vivant else 0, 1000))
    e.add_component(StatsComponent(ctx=_Ctx(visual_id, traits)))
    e.add_component(PositionComponent(int(pos[0]), int(pos[1])))
    return uid


@pytest.fixture
def plateau():
    """Le Prime MORT (porteur du passif, `Synapse`), un allie Synapse VIVANT, une cible ennemie.

    Le Prime est mort : c'est l'etat dans lequel `FinalJusticeAbility` porte son attaque
    post-mortem (`On(PreUnitDeath) & OwnerIsTarget` -- l'owner EST le mourant, deja `alive=False`)."""
    st = State()
    st.current_player_id = 1
    _unite(st, 1, PRIME, team=1, vivant=False, traits=[int(UnitTrait.Synapse)], pos=(2, 2))
    _unite(st, 2, "tyranTyrantGuard", team=1, vivant=True,
           traits=[int(UnitTrait.Synapse)], pos=(3, 2))
    _unite(st, 3, "necroWarrior", team=2, vivant=True, pos=(4, 2))
    #: ⚠ LE TEMOIN DOIT PORTER LE MEME PASSIF, pas seulement etre VIVANT. Premiere ecriture de ce
    #: fichier : le temoin etait le `tyranTyrantGuard`, qui ne porte PAS `SynapticLinchpin` -- il
    #: n'entre donc a aucun titre au registre, et le controle rougissait pour une raison qui n'a
    #: rien a voir avec la vivacite. Un second Prime, VIVANT, est le seul temoin qui isole l'axe.
    _unite(st, 4, PRIME, team=1, vivant=True, traits=[int(UnitTrait.Synapse)], pos=(1, 2))
    return st


def _evalue(st: State, *, actor: int, cible: int, declencheur) -> list:
    """Le trigger est-il EVALUE ? On instrumente `matches` -- le seul point qui distingue
    << ecarte au dispatch >> de << evalue puis refuse >>, que le resultat du behaviour confond."""
    vus: list[tuple] = []
    vrai_matches = SynapticLinchpinAbility.matches

    def espion(self, state, ev):
        vus.append((self.owner_id, ev.actor_id, ev.triggering_ability))
        return False                       # on ne veut QUE le fait d'avoir ete appele
    SynapticLinchpinAbility.matches = espion
    try:
        CORE.evaluate_trigger_operation(st, TriggerEvent(
            SynapticLinchpinAbility.event_id, actor, cible, ranged=False, profile=None,
            triggering_ability=declencheur))
    finally:
        SynapticLinchpinAbility.matches = vrai_matches
    return vus


# ================================================================================================
# ETAGE 1 -- le DISPATCH : un porteur MORT atteint-il `matches` ?
# ================================================================================================
def test_le_porteur_mort_atteint_matches(plateau):
    """LE BRAS QUI TOMBE SANS LE FIX. Avant #937-r1, `evaluate_trigger_operation` faisait
    `continue` sur `not uc.alive and not fire_on_death` : `matches` n'etait JAMAIS appele pour le
    Prime mort, donc `_owner_alive_or_final_justice` -- et tout son disjunct -- etait du code
    inatteignable."""
    vus = _evalue(plateau, actor=1, cible=3, declencheur=FINAL_JUSTICE)
    assert (1, 1, FINAL_JUSTICE) in vus, (
        "le porteur MORT n'atteint pas `matches` : `fire_on_death` ne mirrore plus le "
        "`get_AllowForDeadOwner` VRAI de `SynapticLinchpinAbility` (corps `b0 01 c3`, partage avec "
        "`FinalJusticeAbility`). Vu : %r" % (vus,))


def test_le_controle_un_porteur_vivant_atteint_matches_aussi(plateau):
    """CONTROLE : le bras ci-dessus ne prouve rien si le trigger n'est de toute facon jamais
    evalue. On exige que le porteur VIVANT (l'allie Synapse) y arrive aussi -- sinon le montage
    est mort et le vert de l'etage 1 serait vide."""
    vus = _evalue(plateau, actor=2, cible=3, declencheur=None)
    assert any(o == 4 for o, _a, _t in vus), (
        "aucun porteur VIVANT n'atteint `matches` : le montage ne mesure rien. Vu : %r" % (vus,))


# ================================================================================================
# ETAGE 2 -- le DISJUNCT : `OwnerIsAlive | (OwnerIsActor & TriggeringAbilityIs(FinalJustice))`
# ================================================================================================
@pytest.mark.parametrize("actor,declencheur,attendu,motif", [
    (1, FINAL_JUSTICE, True, "le porteur MORT est l'acteur, et le coup vient de FinalJustice"),
    (1, None, False, "meme acteur, mais AUCUNE ability declenchante -> `TriggeringAbilityIs` faux"),
    (1, 1192, False, "meme acteur, mais une AUTRE ability declenchante (SynapticLinchpin)"),
    (2, FINAL_JUSTICE, False, "FinalJustice, mais l'acteur n'est PAS le porteur -> `OwnerIsActor` faux"),
])
def test_le_disjunct_discrimine(plateau, actor, declencheur, attendu, motif):
    """Les TROIS bras negatifs existent parce qu'un `fire_on_death = True` pose SANS le disjunct
    ferait firer le passif pour n'importe quel coup allie pendant que le porteur est mort -- une
    degradation PERMISSIVE, donc silencieuse."""
    ab = SynapticLinchpinAbility(1)
    ev = TriggerEvent(SynapticLinchpinAbility.event_id, actor, 3, ranged=False, profile=None,
                      triggering_ability=declencheur)
    assert ab._owner_alive_or_final_justice(plateau, ev) is attendu, motif


def test_un_porteur_vivant_passe_la_branche_gauche(plateau):
    """`OwnerIsAlive` : la branche gauche, sur un porteur VIVANT, rend vrai quel que soit le reste."""
    ab = SynapticLinchpinAbility(2)
    ev = TriggerEvent(SynapticLinchpinAbility.event_id, 3, 1, ranged=False, profile=None,
                      triggering_ability=None)
    assert ab._owner_alive_or_final_justice(plateau, ev) is True


# ================================================================================================
# ETAGE 3 -- la valeur NATIVE, confrontee a l'entree VERSIONNEE
# ================================================================================================
def test_l_attribut_vaut_ce_que_le_build_dit():
    """L'attribut n'est pas un choix de port : il MIRRORE une valeur du build. Cette assertion la
    relit dans l'entree versionnee plutot que de la recopier -- si le build change d'avis, c'est
    ICI que ca doit rougir, pas dans un commentaire."""
    tsv = (RACINE.parent.parent / "data" / "symbols")
    lignes = []
    for d in sorted(tsv.glob("*/metadata/allow_for_dead_owner.tsv")):
        lignes.extend(d.read_text(encoding="utf-8").splitlines())
    if not lignes:
        pytest.skip("PAS MESURE : aucune entree `allow_for_dead_owner.tsv` versionnee")
    vus = [l.split("\t") for l in lignes
           if l.startswith("IdunBattleLogic.Entities.Abilities.Triggered.Loki.SynapticLinchpinAbility\t")
           and "\tget_AllowForDeadOwner\t" in l]
    assert len(vus) == 1, (
        "`SynapticLinchpinAbility::get_AllowForDeadOwner` doit avoir EXACTEMENT une ligne dans "
        "l'entree versionnee ; vu %d. Regenerer : probe_10015_allow_for_dead_owner.py --regenerer"
        % len(vus))
    assert vus[0][3] == "TRUE", (
        "le build dit `%s` : `fire_on_death` doit suivre, pas rester a True par habitude"
        % vus[0][3])
    assert SynapticLinchpinAbility.fire_on_death is True
