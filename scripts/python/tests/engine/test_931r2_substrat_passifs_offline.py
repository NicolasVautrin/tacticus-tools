"""#931-r2 -- les abilities ACCORDEES par un passif viennent de l'ENTITE, pas du KIT gameconfig.

GARDE (le probe qui MESURE est `probe_931r2_substrat_passifs.py`). 100 % OFFLINE.

NATIF. `...TwistedScienceAbility$$CreateBehaviour` (`On(AbilityInit) & OwnerIsActor`) monte
l'ability accordee depuis `UnitConfiguration.PassiveAbilities`, c.-a-d. `BC.Units[].PassiveAbilities`
-- un fait d'ENTITE. Le KIT gameconfig (`GC.unit(vid).passiveAbilities`) n'est qu'une DERIVATION,
exacte tant que personne ne touche a la liste. Tout bras
`catalog_inject.write_grafted_seed_bc(..., replace=True)` la REMPLACE, et la divergence devient
SILENCIEUSE dans les deux sens. Meme vice que #264 (traits) / #366-r1 (passifs, face COMBAT) /
#419-r1-tr14-r5 (attaque normale) ; meme parade (tri-etat), transposee.

CE QUI EST GARDE
  1. la MESURE prime -- greffe : une entite qui porte le passif recoit l'ability, meme si son kit
     ne le porte pas ;
  2. la MESURE prime AUSSI dans l'autre sens -- retrait : une entite qui ne porte PAS le passif ne
     recoit pas l'ability, meme si son kit le porte. C'est la moitie qu'un test « la greffe marche »
     laisserait passer, et c'est la degradation PERMISSIVE (une ability fantome) ;
  3. le TRI-ETAT est reel : `None` (canal muet) rend EXACTEMENT le comportement kit, et un tuple
     VIDE en differe -- sinon `()` se lirait « pas de mesure » ;
  4. le fix est BRANCHE : `build_from_state` propage la mesure jusqu'aux `abilities` publiees. Sans
     cet etage, les trois precedents pourraient etre verts sur un foyer que personne n'appelle.
"""
from __future__ import annotations

import pytest

from engine.ai import state_bridge as SB
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.pathfinding.board import Board
from engine.entities.unit_context import UnitContext
from engine.runner.components import (OwnerComponent, PositionComponent, StatsComponent,
                                      UnitComponent)
from engine.runner.state import State

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15). Il garde le
#: substrat des abilities ACCORDEES : le foyer, le mirror d'enum qui nomme `Heal_<passif>`,
#: et le `UnitContext` qui porte la mesure d'entite.
DECLENCHEUR = {
    "chemins": (),   # tout est dans la cascade derivee par le foyer (#531)
    "build": False,
    "toujours": True,
    "raison": "les porteurs du grant (`passiveAbilities` du kit) et les membres `Heal_*` de "
              "`ActiveAbilityType` viennent du gameconfig et du dump : hors depot. Un membre "
              "de plus elargirait la population sans qu'un chemin change.",
}

PASSIF = "TwistedScience"
ACCORDEE = int(ActiveAbilityType.Heal_TwistedScience)      # 1167
KIT_PORTEUR = "genesBiophagus"        # son KIT porte `TwistedScience`
KIT_SANS = "admecRuststalker"         # son KIT ne le porte pas (temoin)


@pytest.fixture(scope="module")
def porteurs_kit():
    """Les unites a qui le KIT accorde une active via un passif -- la population de reference.
    Assertionne son propre non-vide au premier test qui la consomme."""
    import unit_map as UM

    ids = sorted(k["id"] for k in UM.all_kits() if k.get("id"))
    return [v for v in ids if SB._granted_abilities(v)]


def _state_avec_passifs_mesures(vid: str, passifs):
    """`State` OFFLINE minimal dont l'unite porte un `UnitContext` avec `passive_abilities`
    SEEDE -- exactement ce que `runner.snapshot._load_passive_abilities` pose depuis le canal
    `unitAbilityStates`. `passifs=None` = canal MUET (le `UnitContext` existe, l'attribut est
    `None`), et c'est le cas qui doit retomber sur le kit."""
    tiles = [{"id": c * 3 + r + 1, "col": c, "row": r, "walkable": True, "elevation": 0}
             for c in range(3) for r in range(3)]
    st = State()
    st.board = Board(tiles, adjacency="evenq")
    e = st.add_entity(101)
    e.add_component(UnitComponent(visual_id=vid, alive=True))
    e.add_component(OwnerComponent(team=1, player=1))
    e.add_component(PositionComponent(col=1, row=1))
    e.add_component(StatsComponent(UnitContext(entity_id=101, visual_id=vid,
                                               passive_abilities=passifs)))
    return st


def test_la_population_de_reference_n_est_pas_vide(porteurs_kit):
    assert porteurs_kit, "aucune unite ne recoit d'ability accordee : ce fichier ne garde rien"
    assert KIT_PORTEUR in porteurs_kit


def test_greffe_la_mesure_d_entite_ACCORDE_ce_que_le_kit_ignore():
    """Sens 1 : le natif monte l'ability, le port (kit) la manquait."""
    assert SB._granted_abilities(KIT_SANS) == ()
    got = SB._granted_abilities(KIT_SANS, (PASSIF,))
    assert ACCORDEE in [a for a, _n in got], got


def test_retrait_la_mesure_d_entite_ECARTE_ce_que_le_kit_donne():
    """Sens 2 -- la moitie qu'un test de greffe seul laisserait passer : une ability FANTOME."""
    assert ACCORDEE in [a for a, _n in SB._granted_abilities(KIT_PORTEUR)]
    assert SB._granted_abilities(KIT_PORTEUR, ()) == ()


def test_le_tri_etat_distingue_muet_et_mesure_vide():
    muet = SB._granted_abilities(KIT_PORTEUR, None)
    vide = SB._granted_abilities(KIT_PORTEUR, ())
    assert muet == SB._granted_abilities(KIT_PORTEUR), "le muet doit EGALER le repli kit"
    assert muet != vide, "`()` se lirait comme `None` : le tri-etat serait un bi-etat"


@pytest.mark.parametrize("vid,passifs,attendu", [
    (KIT_SANS, (PASSIF,), True),      # greffe   : mesure -> accordee
    (KIT_SANS, None, False),          # muet     : repli kit -> rien
    (KIT_PORTEUR, (), False),         # retrait  : mesure vide -> ecartee
    (KIT_PORTEUR, None, True),        # muet     : repli kit -> accordee
])
def test_build_from_state_propage_la_mesure_jusqu_aux_abilities_publiees(vid, passifs, attendu):
    """Etage 4 -- le fix est BRANCHE. Sans lui, les trois etages precedents gardent un foyer
    que le contexte de decision n'appellerait pas avec la mesure."""
    st = _state_avec_passifs_mesures(vid, passifs)
    ctx = SB.build_from_state(st, 101)
    ids = [a["id"] for a in (ctx.me or {}).get("abilities", [])]
    assert (ACCORDEE in ids) is attendu, (vid, passifs, ids)
