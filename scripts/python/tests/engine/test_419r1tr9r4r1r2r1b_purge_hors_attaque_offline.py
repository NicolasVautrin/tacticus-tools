"""#419-r1-tr9-r4-r1-r2-r1b -- la marque de `LegendaryCommander_ExtraHits` (1395) part-elle quand la
cible SORT du selecteur, SANS qu'aucune attaque ne la vise ?

## Ce que le natif fait, et ce que le port faisait
`IdunBattle.Entities.Effects.Loki.LegendaryCommander_ExtraHitsEffect$$RevertInternal` =
`ExecuteBehaviour(ClearPersistentData(<AbilityOrEffect>, EffectSource(Get(effect)),
EntityId(Target@<DSLSelectors+0x60>)))`, joue par le `b__2` (`RevertEffectsForTargets`) d'
`IdunBattle.Operations.RefreshEffectsOperation$$UpdateEffectTargets` pour chaque cible que
`$$GetTargetsToRemove` sort de `EffectComponent.Targets @+0x48`.

Le port faisait cette purge dans le TARGET-TRIGGER, a la CLOTURE D'ATTAQUE -- donc il n'observait
QUE la cible du coup courant. Une cible marquee, sortie du selecteur, puis re-couverte sans avoir
ete attaquee entre-temps gardait sa marque : le port REFUSAIT un bonus que le natif RE-DONNE.

⚠ CE N'EST PAS UN REGIME EXOTIQUE. Le selecteur exige `HasUsedActiveAbilityThisTurn` d'un allie, et
`IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags` le retire a CHAQUE entree de
tour (port : `turnflow`, AVANT le refresh `TurnChanged`). La couverture tombe donc tous les tours.
C'est exactement ce que la mesure live de `case-419-r1-tr9-r4-r1-r2-r1-legendary-commander.md` Sec.4
avait etabli sur le NATIF (<< Trajann RE-caste au tour 2 -> le natif rend de nouveau 5 coups >>).

## Ce que ce fichier plombe
1. la surcharge EXISTE et le defaut de `BaseEffect` rend `()` (le discriminant est le MRO, pas un
   `hasattr` defensif) ;
2. couverte -> la marque RESTE (contre-bras : sans lui, un driver qui purge tout serait vert) ;
3. NON couverte -> la marque PART, sans qu'aucune attaque n'ait eu lieu ;
4. le driver `refresh_stat_modifier_effects` la joue REELLEMENT (le cablage, pas seulement la
   fonction) ;
5. une cible marquee DISPARUE de l'etat sort aussi (elle quitte `Targets` au meme titre) ;
6. aucune autre classe d'effet du registre ne surcharge par accident (le no-op est un FAIT mesure,
   pas une esperance).

ASCII only.
"""
from __future__ import annotations

import pytest

import hexgeo
from engine.entities.effect_type import EffectType
from engine.entities.effects.base import BaseEffect
from engine.entities.effects.factory import EFFECT_CLASSES
from engine.entities.effects.loki.hits import (LegendaryCommanderExtraHitsEffect,
                                               legendary_commander_marked_key)
from engine.entities.pathfinding.board import Board
from engine.runner.components import (OwnerComponent, PersistentDataComponent, PositionComponent,
                                      UnitComponent, UnitFlagsComponent)
from engine.runner.operations import refresh_effects as RE

#: Ce que ce fichier LIT -- pris LARGE (trop etroit est un faux vert, cf. la doctrine des cliquets).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/hits.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/refresh_effects.py",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/runner/components.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "le protocole `targets_to_revert_on_exit` (defaut + surcharge 1395), son driver dans "
              "le refresh, et le foyer `build_hits_board` d'ou sort le contexte du selecteur.",
}

COLS, ROWS = 5, 5
#: Trajann (porteur ET source de 1395), un allie qui a utilise son active, la cible ennemie.
_OWNER, _ALLIE, _CIBLE = 81, 82, 91
_TEAM_AMI, _TEAM_ENNEMI = 1, 2
_EFFET = EffectType.LegendaryCommander_ExtraHits


def _board() -> Board:
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [c * ROWS + r + 1 for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": col * ROWS + row + 1, "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tiles, adjacency="evenq")


class _EtatMinimal:
    """Le sous-ensemble de `State` que le driver et `build_hits_board` LISENT.

    Monte a la main plutot que par `load_state` : le regime teste est un REFRESH sans attaque, donc
    aucune couche de snapshot n'y participe. Ce qui compte est que les positions, equipes, flags et
    effets soient ceux que le selecteur lit."""

    def __init__(self, allie_a_utilise_son_active: bool, cible_presente: bool = True):
        from engine.runner.state import State
        self.state = State()
        self.state.board = _board()
        # Trajann et son allie sont ADJACENTS a la cible (le 4e noeud de 1395 exige
        # `IsAdjacent(Owner, Subject)`, le 3e `AdjacentEnemies` depuis l'allie).
        places = [(_OWNER, _TEAM_AMI, (2, 1)), (_ALLIE, _TEAM_AMI, (2, 3))]
        if cible_presente:
            places.append((_CIBLE, _TEAM_ENNEMI, (2, 2)))
        for uid, team, pos in places:
            e = self.state.add_entity(uid)
            e.add_component(UnitComponent(visual_id="x", alive=True))
            e.add_component(OwnerComponent(team=team, player=team))
            e.add_component(PositionComponent(col=pos[0], row=pos[1]))
            fl = UnitFlagsComponent()
            if uid == _ALLIE and allie_a_utilise_son_active:
                fl.add(int(UnitFlagsComponent.ACTIVE_ABILITY_USED))
            e.add_component(fl)
        # L'effet 1395 vit sur Trajann ; sa SOURCE est Trajann (le `AddEffect` le pose sur Owner).
        eff = LegendaryCommanderExtraHitsEffect(_EFFET.name, ability_level=50)
        eff.source = _OWNER
        eff.effect_type = _EFFET
        self.effet = eff
        from engine.entities.effects_state import EffectsState
        self.state.effects = EffectsState()
        self.state.effects.by_unit[_OWNER] = [eff]
        # Le sac persistant de Trajann porte DEJA la marque de la cible (attaque d'un tour anterieur).
        sac = PersistentDataComponent()
        sac.persist_data(legendary_commander_marked_key(_CIBLE), [999])
        self.state.get_entity(_OWNER).add_component(sac)

    @property
    def marques(self):
        sac = self.state.get_entity(_OWNER).get_component(PersistentDataComponent)
        return dict(sac.data)


def test_le_defaut_de_BaseEffect_est_VIDE_et_la_surcharge_EXISTE():
    """Le discriminant du driver est le MRO -- `hasattr` confondrait << pas porte >> et << rien a
    purger >>, ce que la doctrine proscrit."""
    assert BaseEffect.targets_to_revert_on_exit(BaseEffect("x"), None, 0) == ()
    assert (LegendaryCommanderExtraHitsEffect.targets_to_revert_on_exit
            is not BaseEffect.targets_to_revert_on_exit)


def test_cible_COUVERTE_la_marque_RESTE():
    """CONTRE-BRAS. Sans lui, un driver qui purgerait TOUT passerait le test suivant."""
    m = _EtatMinimal(allie_a_utilise_son_active=True)
    assert m.effet.targets_to_revert_on_exit(m.state, _OWNER) == (), (
        "la cible est couverte (un allie adjacent a utilise son active) : rien ne doit sortir")
    RE.revert_effects_for_exited_targets(m.state)
    assert legendary_commander_marked_key(_CIBLE) in m.marques


def test_cible_SORTIE_la_marque_PART_sans_aucune_attaque():
    """LE REGIME DU RESIDU : la couverture tombe (aucun allie n'a plus d'active consommee ce tour),
    et personne n'attaque. Le natif a purge au refresh ; le port doit en faire autant."""
    m = _EtatMinimal(allie_a_utilise_son_active=False)
    sorties = m.effet.targets_to_revert_on_exit(m.state, _OWNER)
    assert sorties == ((_OWNER, legendary_commander_marked_key(_CIBLE)),), sorties
    RE.revert_effects_for_exited_targets(m.state)
    assert legendary_commander_marked_key(_CIBLE) not in m.marques


def test_le_DRIVER_du_refresh_joue_reellement_la_purge():
    """LE CABLAGE, pas la fonction : `refresh_stat_modifier_effects` est le point que `turnflow`
    (`TurnChanged`, APRES `remove_turn_flags`), `movement` et `damage` appellent deja."""
    m = _EtatMinimal(allie_a_utilise_son_active=False)
    RE.refresh_stat_modifier_effects(m.state, refresh_trigger=RE.RefreshEffectTrigger.TurnChanged)
    assert legendary_commander_marked_key(_CIBLE) not in m.marques


def test_cible_DISPARUE_de_l_etat_sort_aussi():
    """Une cible sans tuile a quitte `Targets` au meme titre -- le natif ne la garde pas non plus."""
    m = _EtatMinimal(allie_a_utilise_son_active=True, cible_presente=False)
    sorties = m.effet.targets_to_revert_on_exit(m.state, _OWNER)
    assert sorties == ((_OWNER, legendary_commander_marked_key(_CIBLE)),), sorties


def test_aucune_AUTRE_classe_du_registre_ne_surcharge_par_accident():
    """Le no-op sur tout le reste du registre est une MESURE, pas une esperance : si une classe
    surchargeait sans le vouloir, le driver la balaierait a chaque refresh."""
    surchargeantes = {n for n, c in EFFECT_CLASSES.items()
                      if getattr(c, "targets_to_revert_on_exit", None)
                      is not BaseEffect.targets_to_revert_on_exit}
    assert surchargeantes == {_EFFET.name}, surchargeantes


def test_le_driver_est_un_NO_OP_sans_instance_surchargeante():
    """Cout nul hors regime : un etat sans instance 1395 ne doit produire AUCUNE purge."""
    m = _EtatMinimal(allie_a_utilise_son_active=True)
    m.state.effects.by_unit[_OWNER] = []
    assert RE.revert_effects_for_exited_targets(m.state) == []
    assert legendary_commander_marked_key(_CIBLE) in m.marques
