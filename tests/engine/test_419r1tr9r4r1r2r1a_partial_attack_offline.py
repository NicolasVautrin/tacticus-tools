"""#419-r1-tr9-r4-r1-r2-r1a -- le SECOND conjoint d'`IsValidAttack` de LegendaryCommander.

CE QUE CES ETAGES GARDENT
-------------------------
1. Les DEUX sets statiques sont FIGES par leur ordinal MESURE (pas seulement << conformes au
   mirror >>) : `probe_313` compare le mirror au build, il redeviendrait VERT apres un
   renumerotage alors que la valeur ECRITE au site, elle, aurait change (cf. CLAUDE.md).
2. Le mirror du trigger `AbilityIsPartialAttackAbilityTrigger$$IsPartialAttack` rend le bon
   verdict sur ses trois membres, sur `None`, et sur un voisin d'ordinal.
3. La CONJONCTION MORD : le regime `TriggeringAbilityIsNormalAttack & IsPartialAttackAbility`
   ferme le gate, et le MEME regime avec une `CurrentAbility` HORS des sets le laisse passer.
   C'est exactement ce que l'ancien port -- qui gardait le premier conjoint SEUL -- fermait a
   tort. Le temoin est NON DEGENERE : les deux branches sont jouees sur le meme ctx, une seule
   cle change.
4. Le canal `ability_type` existe bien dans le board de coups (sans lui l'etage 3 serait vert
   pour la mauvaise raison : `None` ne peut pas etre dans un set).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "scripts" / "python"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.services import static_battle_rules as sbr            # noqa: E402
from engine.entities.effects.loki.hits import (                    # noqa: E402
    LegendaryCommanderExtraHitsEffect, LEGENDARY_COMMANDER_EXTRA_HITS)
from engine.entities.effect_type import EffectType                 # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.runner.abilities.attack_type import REGULAR_ATTACK_ABILITY_TYPES   # noqa: E402


# --- etage 1 : les ORDINAUX MESURES, figes ici ---------------------------------------------------
# Mesure du 2026-08-15 sur le build `t6dpr4k06g`, par les OCTETS du PE
# (`probe_419r1tr9r4r1r2r1a_partial_attack_sets.py`). Le probe re-derive ; CE test fige.
_MESURE_TRIGGERED = {1032, 1076}
_MESURE_EFFECT = {1077}


def test_etage1_ordinaux_mesures_figes():
    assert {int(x) for x in sbr.PARTIAL_ATTACK_TRIGGERED_ABILITY_TYPES} == _MESURE_TRIGGERED
    assert {int(x) for x in sbr.PARTIAL_ATTACK_EFFECT_TYPES} == _MESURE_EFFECT
    # ... et les NOMS, qui sont le seul canal ou une confusion d'enum est visible.
    assert int(TriggeredAbilityType.DeathToTheFalseEmperor) == 1032
    assert int(TriggeredAbilityType.HazeOfCorruption) == 1076
    assert int(EffectType.HazeOfCorruption_DamageTransfer) == 1077


def test_etage1b_les_trois_ordinaux_nomment_autre_chose_ailleurs():
    """La confusion d'enum serait SILENCIEUSE en ordinal -- ce test asserte son propre non-vide."""
    croises = {
        1032: (int(EffectType.UnstoppableFerocity_OwnerEffect),),
        1076: (int(EffectType.CondemnorStake_ExtraDmg),),
        1077: (int(TriggeredAbilityType.Volatile),),
    }
    assert croises, "temoin vide : le test ne prouverait rien"
    for ordinal, autres in croises.items():
        assert all(a == ordinal for a in autres), (
            "l'ordinal %d doit exister dans l'autre enum sous un AUTRE nom" % ordinal)


# --- etage 2 : le mirror du trigger ---------------------------------------------------------------
@pytest.mark.parametrize("valeur,attendu", [
    (None, False),                                             # `Nullable.HasValue == false`
    (int(TriggeredAbilityType.DeathToTheFalseEmperor), True),   # 1032
    (int(TriggeredAbilityType.HazeOfCorruption), True),         # 1076
    (int(EffectType.HazeOfCorruption_DamageTransfer), True),    # 1077
    (1078, False),                                              # voisin d'ordinal, hors des deux sets
    (1031, False),
])
def test_etage2_ability_is_partial_attack(valeur, attendu):
    assert sbr.ability_is_partial_attack(valeur) is attendu


def test_etage2b_predicats_types_separes():
    """Les deux predicats natifs restent DISTINCTS : chacun ne connait QUE son enum."""
    assert sbr.is_partial_attack_ability(1032) is True
    assert sbr.is_partial_attack_ability(1077) is False        # 1077 est un EffectType, pas ici
    assert sbr.is_partial_attack(1077) is True
    assert sbr.is_partial_attack(1032) is False               # 1032 est un TriggeredAbilityType


# --- etage 3 : LA CONJONCTION MORD ---------------------------------------------------------------
def _ctx_couvert(ability_type, trigger_ability_type):
    """Un ctx MINIMAL ou l'aura COUVRE deja la cible -- seules les deux cles du conjoint varient.

    Geometrie : owner (Trajann) en (0,0), cible ennemie en (1,0) -- adjacente (4e noeud du
    selecteur) ; l'attaquant, allie de l'owner, est en (0,0) lui aussi et a utilise une active ce
    tour (`HasUsedActiveAbilityThisTurn`), donc le 3e noeud tient."""
    return {
        "owner_id": 1, "owner_pos": (0, 0), "owner_team": 0,
        "att_id": 1, "tgt_id": 2,
        "t_pos": (1, 0),
        "pos_by_id": {1: (0, 0), 2: (1, 0)},
        "team_by_id": {1: 0, 2: 1},
        "used_active_by_id": {1: True, 2: False},
        "is_normal_attack": False,          # `!IsNormalAttack(CurrentAbility)` -- vecteur ABILITY
        "trigger_ability_type": trigger_ability_type,
        "ability_type": ability_type,
    }


def _effet():
    e = LegendaryCommanderExtraHitsEffect(LEGENDARY_COMMANDER_EXTRA_HITS)
    e.source = 1
    return e


#: une attaque normale PER-UNIT, donc `IsNormalAttack(TriggeringAbility)` VRAI -- premier conjoint.
_TRIGGER_NORMAL = sorted(int(x) for x in REGULAR_ATTACK_ABILITY_TYPES)[0]


def test_etage3_temoin_non_degenere_le_selecteur_couvre():
    """Sans ce controle, les deux branches de l'etage 3 seraient FAUSSES pour la meme raison
    (l'aura ne couvre pas) et l'accord ne prouverait rien."""
    assert _effet().aura_selector_covers(_ctx_couvert(None, None)) is True


def test_etage3_conjonction_ferme_quand_les_deux_conjoints_tiennent():
    ctx = _ctx_couvert(int(TriggeredAbilityType.HazeOfCorruption), _TRIGGER_NORMAL)
    assert _effet().is_valid_attack(ctx) is False


def test_etage3_conjonction_laisse_passer_quand_current_ability_hors_des_sets():
    """LE REGIME QUE L'ANCIEN PORT FERMAIT A TORT : premier conjoint VRAI, second FAUX."""
    ctx = _ctx_couvert(1078, _TRIGGER_NORMAL)      # 1078 : hors des deux sets
    assert _effet().is_valid_attack(ctx) is True


def test_etage3_second_conjoint_seul_ne_ferme_pas():
    """Symetrique : `IsPartialAttackAbility` vrai mais l'ability declenchante n'est pas normale."""
    ctx = _ctx_couvert(int(TriggeredAbilityType.HazeOfCorruption), None)
    assert _effet().is_valid_attack(ctx) is True


def test_etage3b_contre_epreuve_lancien_port_fermait_ce_regime(monkeypatch):
    """CONTRE-EPREUVE. L'ancien port gardait le PREMIER conjoint SEUL, ce qui equivaut a
    `IsPartialAttackAbility ==> VRAI`. On restaure exactement ce regime et on verifie que le cas
    << laisse passer >> ci-dessus se REFERME : sans cela, l'etage 3 serait vert sans rien mordre.

    Ce patch MORD parce que `hits.py` consomme le predicat en FORME B (liaison de MODULE). En
    forme A (`from ... import ability_is_partial_attack` en tete) il ne mordrait PAS, et cette
    assertion deviendrait un faux vert -- c'est le cran qui garde la forme."""
    monkeypatch.setattr("engine.services.static_battle_rules.ability_is_partial_attack",
                        lambda _x: True)
    ctx = _ctx_couvert(1078, _TRIGGER_NORMAL)
    assert _effet().is_valid_attack(ctx) is False, (
        "le patch n'a pas mordu : le site consomme-t-il encore le predicat en forme A ?")


# --- etage 4 : le canal existe dans le board de coups --------------------------------------------
def test_etage4_le_board_de_coups_porte_la_cle_ability_type():
    """Sans cette cle, l'etage 3 serait vert pour la MAUVAISE raison : `None` n'est dans aucun set,
    donc la conjonction ne fermerait jamais et le port resterait aussi faux qu'avant -- dans
    l'autre sens."""
    import inspect

    from engine.runner import damage_model
    sig = inspect.signature(damage_model.build_hits_board)
    assert "ability_type" in sig.parameters, "build_hits_board ne thread pas `CurrentAbility`"
    src = inspect.getsource(damage_model.build_hits_board)
    assert '"ability_type"' in src, "la cle n'est pas posee dans le board"
    # et le call-site du SEUL vecteur ou l'effet reste ouvert (famille ATTACK d'une ability)
    from engine.runner.operations.damage_ops import ability as _ability_ops
    assert "ability_type=ability_type" in inspect.getsource(_ability_ops), (
        "damage_ops/ability.py ne passe pas `CurrentAbility` au board de coups")
