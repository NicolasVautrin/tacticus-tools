"""#915 -- gardes OFFLINE du passif de kit `PropheticSentinel` (`thousSekhetar`).

Ce que ces tests FIGENT, et pourquoi chacun existe :

1. **Les TROIS appariements (effectType -> stat, variable, trait de selecteur)**, mesures live en
   regime discriminant (`probe_915_prophetic_sentinel.py`, quatre voisins couvrant les quatre
   combinaisons du couple Psyker/Chaos). Le premier port de cette tranche les avait TOUS les trois
   faux d'une facon SILENCIEUSE -- il declarait un self-buff (`get_stat_modification_*`) la ou le
   natif projette une aura. Un test d'existence n'aurait rien vu : les classes existaient.
2. **L'ABSENCE de l'interface self-buff** sur ces trois classes. C'est le cran du dessous : la
   remettre redonnerait au porteur un bonus que la mesure lui refuse, sans qu'aucun autre garde ne
   bouge.
3. **Les DEUX predicats de trait ne sont pas le meme**, et aucun des deux n'est celui de la face
   DECISION. Ce kit porte TROIS predicats deux a deux differents ; les confondre est l'erreur
   naturelle.
4. **Le trigger d'overwatch** : `On(TurnEnd) & IsTurnOf(Owner) & count(amis Psyker adjacents) >= 1`.

Tests OFFLINE (aucun runner) -- ils tournent en quelques dixiemes de seconde.
"""
from __future__ import annotations

import pytest

from engine.entities.effect_type import EffectType
from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES
from engine.entities.effects.loki import prophetic_sentinel as PS
from engine.entities.stats import StatType
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.dsl.event_trigger_type import EventTriggerType

#: (nom d'EffectType, id, classe portee, stat, variable gameconfig, trait du selecteur).
#: Les quatre dernieres colonnes sont MESUREES live, pas deduites du nom de l'effet.
ATTENDU = [
    ("PropheticSentinel_ExtraArmor", 1558, PS.PropheticSentinelExtraArmorEffect,
     StatType.FIXED_ARMOR, "extraArmor", UnitTrait.Chaos),
    ("PropheticSentinel_ExtraBlockChance", 1559, PS.PropheticSentinelExtraBlockChanceEffect,
     StatType.BLOCK_CHANCE, "blockChance", UnitTrait.Psyker),
    ("PropheticSentinel_ExtraBlockDamage", 1560, PS.PropheticSentinelExtraBlockDamageEffect,
     StatType.BLOCK_DAMAGE, "blockDmg", UnitTrait.Psyker),
]


@pytest.mark.parametrize("nom,eid,cls,stat,var,trait", ATTENDU)
def test_ids_et_appariements(nom, eid, cls, stat, var, trait):
    """Le mirror d'enum, le registre et les trois colonnes mesurees."""
    assert int(getattr(EffectType, nom)) == eid
    assert EFFECT_CLASSES.get(nom) is cls
    assert int(cls._STAT) == int(stat)
    assert cls._VAR == var
    assert int(cls._TRAIT) == int(trait)


def test_les_deux_predicats_de_trait_different():
    """Le kit porte DEUX selecteurs distincts : sans cette assertion, une uniformisation << tous
    Psyker >> ou << tous Chaos >> passerait, et c'est EXACTEMENT ce que le decompile interdit
    (`PropheticSentinel_PsykerEffect` vs `_ChaosEffect`, deux corps de `CreateTargetSelector`)."""
    traits = {int(c._TRAIT) for _n, _i, c, _s, _v, _t in ATTENDU}
    assert traits == {int(UnitTrait.Psyker), int(UnitTrait.Chaos)}, traits
    assert int(UnitTrait.Psyker) != int(UnitTrait.Chaos)          # non-vide du discriminant


@pytest.mark.parametrize("_n,_i,cls,_s,_v,_t", ATTENDU)
def test_aucune_interface_self_buff(_n, _i, cls, _s, _v, _t):
    """Ces trois effets ne modifient PAS le porteur -- mesure live : le Sekhetar reste a 0/0/0 sur
    les trois stats alors que ses voisins qualifiants sont buffes. Declarer le couple
    `get_stat_modification_stat/amount` (l'interface SELF de `BaseEffect`) lui rendrait le bonus."""
    inst = cls(effect_type=_i, name=_n)
    assert inst.get_stat_modification_stat() is None
    assert inst.get_stat_modification_amount() in (None, 0)
    # ... et l'interface AURA, elle, DOIT etre la (sinon `aura_stat_mods` ne voit aucun carrier).
    assert callable(getattr(inst, "aura_stat_modification_stat", None))
    assert callable(getattr(inst, "aura_stat_modification_targets", None))


def test_pose_a_l_init_et_pas_dans_ability_triggers():
    """Les trois effets sont poses par le trigger HERITE `<DSLTriggers+0x30>` =
    `On(AbilityInit) & OwnerIsActor` -> canal `ABILITY_INIT_OWNER_EFFECTS`. L'entree
    `ABILITY_TRIGGERS['PropheticSentinel']`, elle, ne porte QUE l'ability d'overwatch."""
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    from engine.runner.operations.triggers.loki.prophetic_sentinel import (
        PropheticSentinelOverwatchAbility)
    poses = ABILITY_INIT_OWNER_EFFECTS.get("PropheticSentinel")
    assert poses == ["PropheticSentinel_ExtraArmor", "PropheticSentinel_ExtraBlockChance",
                     "PropheticSentinel_ExtraBlockDamage"]
    assert ABILITY_TRIGGERS.get("PropheticSentinel") == [PropheticSentinelOverwatchAbility]


def test_trigger_overwatch_litteraux():
    """`On(0x17 = TurnEnd)`, seuil `Direct(1)`, effet `0x3f1 = Overwatch_AutoAttack`, ability
    `0x607 = 1543`. Quatre litteraux LUS au decompile ; l'ordinal ne discrimine aucun des quatre
    (1009 nomme `ResurrectionOrb` en actif et `Resilient` en trait ; 1543 nomme
    `ModifiedExoarmour_PierceReduction` en EffectType)."""
    from engine.runner.operations.triggers.loki import prophetic_sentinel as T
    assert T.PropheticSentinelOverwatchAbility.event_id == int(EventTriggerType.TurnEnd) == 23
    assert T.OVERWATCH_AUTO_ATTACK == int(EffectType.Overwatch_AutoAttack) == 1009
    assert T.MIN_ADJACENT_PSYKER_FRIENDS == 1
    assert (T.PropheticSentinelOverwatchAbility.TRIGGERED_ABILITY_ID
            == int(TriggeredAbilityType.PropheticSentinel) == 1543)
    assert T.SELECTION == 3                       # UnitSelectionType.OnlyAliveAndTargetable


def test_face_decision_owner_ne_connait_que_psyker():
    """`PropheticSentinelPlaybook` (face OWNER) compte les amis adjacents `Psyker` -- PAS Chaos. Le
    piege est la face NON-OWNER, qui CUMULE les deux : recopier son predicat ici doublerait
    l'utilite sur toute unite Psyker+Chaos et en fabriquerait une sur les Chaos purs."""
    from engine.playbook.prophetic_sentinel import PropheticSentinelPlaybook as P
    from engine.playbook.non_owner import PropheticSentinelNonOwnerPlaybook as N
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
    assert int(P.PSYKER_TRAIT) == int(UnitTrait.Psyker)
    assert P.WEIGHT_KEY == "PropheticSentinel_LikesAdjacentPsykerFriends"
    assert int(P.ABILITY_ID) == 1543
    assert isinstance(TRIGGERED_MOVE_PLAYBOOKS.get(1543), P)
    # la face NON-OWNER, elle, porte DEUX cles -- et ce sont d'AUTRES cles.
    assert {N.KEY_PSYKER, N.KEY_CHAOS} == {"PropheticSentinel_PsykerLikesToBeAdjacent",
                                           "PropheticSentinel_ChaosLikesToBeAdjacent"}
    assert P.WEIGHT_KEY not in {N.KEY_PSYKER, N.KEY_CHAOS}


def test_face_decision_owner_compte_les_psyker_adjacents():
    """Le comptage lui-meme, sur un `tile_leaf_ctx` synthetique : deux amis adjacents dont UN seul
    Psyker -> `20 x 1`. Le SELF compte aussi (le corps natif n'ecrit aucun `RemoveAll(case.Unit)`),
    mais seulement s'il est Psyker -- `thousSekhetar` ne l'est pas, d'ou un volet INERTE pour son
    seul porteur, ecrit parce que le natif le fait."""
    from engine.playbook.prophetic_sentinel import PropheticSentinelPlaybook

    class _W:
        def sub(self, groupe, cle):
            assert groupe == "TriggeredAbilities"
            return 20 if cle == "PropheticSentinel_LikesAdjacentPsykerFriends" else 0

    p = PropheticSentinelPlaybook()
    tuile = (2, 2)
    ctx = {"friend_units": [{"pos": (2, 1), "traits": ["Psyker", "Hero"]},
                            {"pos": (1, 2), "traits": ["Hero"]},
                            {"pos": (5, 5), "traits": ["Psyker"]}],   # loin -> ne compte pas
           "self_pos": None, "unit_traits": []}
    assert p.calculate_movement_utility_in_steps(tuile, ctx, _W()) == 20.0
    # SELF Psyker pose sur un hex adjacent -> +1 cran (le natif ne s'exclut pas).
    ctx2 = dict(ctx, self_pos=(3, 2), unit_traits=[int(UnitTrait.Psyker)])
    assert p.calculate_movement_utility_in_steps(tuile, ctx2, _W()) == 40.0
    # poids a 0 -> terme INERTE (garde du `if not w`), jamais une exception.
    class _Z:
        def sub(self, *_a):
            return 0
    assert p.calculate_movement_utility_in_steps(tuile, ctx, _Z()) == 0.0
