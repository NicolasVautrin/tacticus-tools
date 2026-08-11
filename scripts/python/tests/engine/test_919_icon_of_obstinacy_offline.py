"""#919 -- CLIQUETS OFFLINE du passif `IconOfObstinacy` (1552, `astarLysander`).

RE : en tete d'`engine/entities/effects/loki/icon_of_obstinacy.py` et
d'`engine/runner/operations/triggers/loki/icon_of_obstinacy.py`.
Confrontation LIVE : `probe_919_icon_of_obstinacy.py` (montants EXACTS, trois gates discrimines) et
`tests/engine/runner/test_919_icon_of_obstinacy_live.py`.

Ce fichier garde ce qui se casse en SILENCE : les ordinaux ECRITS aux sites, les trois registres,
la formule au chiffre, et le fait que les DEUX pattes du bonus de degat sont DISJOINTES.
"""
from __future__ import annotations

import pytest

#: #486-r15 -- les chemins dont une modification DOIT rejouer ce fichier. Perimetre : le port des
#: deux effets, le trigger, les trois registres, les deux faces DECISION et les mirrors d'enum
#: dont ce fichier FIGE les ordinaux ecrits.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/engine/entities/effects/loki/icon_of_obstinacy.py",
        "scripts/python/engine/runner/operations/triggers/loki/icon_of_obstinacy.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/playbook/adjacent_unit_preference.py",
        "scripts/python/engine/playbook/non_owner.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/entities/stats.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Offline : fige les ordinaux ECRITS aux sites (un mirror regenere apres un "
              "renumerotage rendrait `probe_313` vert alors que la valeur au site a change), les "
              "TROIS registres -- et surtout le fait que les DEUX abilities natives en empruntent "
              "DEUX DIFFERENTS --, la magnitude au chiffre, et la disjonction des deux pattes du "
              "bonus de degat. Aucun runner : tout se lit du gameconfig et des registres.",
}

from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.effect_type import EffectType
from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES
from engine.entities.effects.loki.icon_of_obstinacy import (
    CHANCE_VAR, EXTRA_ARMOR_VAR, EXTRA_DMG_VAR, ICON_OF_OBSTINACY,
    IconOfObstinacyExtraArmorEffect, IconOfObstinacyExtraDmgEffect, _percentage_of)
from engine.entities.effects.magnitude import ability_var
from engine.entities.stats import StatPart, StatType
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.playbook.adjacent_unit_preference import load_playbook
from engine.playbook.non_owner import load_playbook_non_owner
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS

ABILITY = "IconOfObstinacy"
EXTRA_ARMOR_NAME = "IconOfObstinacy_ExtraArmor"
EXTRA_DMG_NAME = "IconOfObstinacy_ExtraDmg"


class _StatsCtx:
    """Le `StatsComponent.ctx` du porteur, reduit a ce que lit `applied_stat_mods`."""

    def __init__(self, block_damage: int):
        self.block_damage = int(block_damage)

    def get_stat(self, stat_type, stat_part=0, source=None) -> int:
        assert int(stat_part) == int(StatPart.CURRENT), \
            "le natif lit `GetStat(target, BlockDamage, 0x0 = Current)` -- pas une autre part"
        return self.block_damage if int(stat_type) == int(StatType.BLOCK_DAMAGE) else 0


def _armour(block_damage, level=50, mult=180):
    e = IconOfObstinacyExtraArmorEffect(EXTRA_ARMOR_NAME)
    e.ability_level, e.ability_variables_multiplier = level, mult
    return e.applied_stat_mods(_StatsCtx(block_damage))


def _dmg_effect(level=50, mult=180):
    d = IconOfObstinacyExtraDmgEffect(EXTRA_DMG_NAME)
    d.ability_level, d.ability_variables_multiplier = level, mult
    return d


# ------------------------------------------------------------------ etage 1 : ordinaux ECRITS
def test_les_ordinaux_ecrits_aux_sites_sont_figes():
    """Les litteraux du decompile, FIGES a la valeur MESUREE a la conversion.

    `probe_313` compare le MIRROR au BUILD : il redevient vert des qu'on regenere le mirror apres
    un renumerotage, alors que la valeur ECRITE au site, elle, a change. C'est ce cran-la que ce
    test tient (cf. la doctrine `#270-r1-r1-r3` du `CLAUDE.md`)."""
    assert int(TriggeredAbilityType.IconOfObstinacy) == 0x610          # 1552
    assert int(EffectType.IconOfObstinacy_ExtraDmg) == 0x627           # 1575
    assert int(EffectType.IconOfObstinacy_ExtraArmor) == 0x628         # 1576
    assert int(UnitTrait.TerminatorArmour) == 0x40f                    # 1039
    assert int(EventTriggerType.UnitFinishedTurn) == 0x28              # 40
    assert int(EventTriggerType.SpecificAbilityInit) == 0x31           # 49
    assert int(StatType.FIXED_ARMOR) == 0x10                           # statType de la pose
    assert int(StatType.BLOCK_DAMAGE) == 0x8                           # stat lue par la magnitude


def test_le_trigger_ecoute_UnitFinishedTurn_et_PAS_sa_variante_normale():
    """`On(0x28 = UnitFinishedTurn)`, pas `On(0x29 = UnitFinishedTurnNormally)`.

    Les deux existent et le natif publie les DEUX au meme site ; seul `0x29` porte le gate
    `!isTerminated`. Confondre les deux ferait rater le buff sur toute terminaison FORCEE --
    une omission SILENCIEUSE, jamais une erreur."""
    from engine.runner.operations.triggers.loki.icon_of_obstinacy import (
        IconOfObstinacyAddArmourBuffAbility)
    assert IconOfObstinacyAddArmourBuffAbility.event_id == int(EventTriggerType.UnitFinishedTurn)
    assert IconOfObstinacyAddArmourBuffAbility.event_id != \
        int(EventTriggerType.UnitFinishedTurnNormally)


# ------------------------------------------------------------------- etage 2 : les 3 registres
def test_les_deux_abilities_natives_empruntent_DEUX_registres_differents():
    """UNE entree de gameconfig, DEUX classes natives -- et elles ne se cablent PAS au meme endroit.

      * `IconOfObstinacy_AddArmourBuffAbility` a un `CreateTrigger` de COMBAT -> `ABILITY_TRIGGERS` ;
      * `IconOfObstinacy_AddDamageBuffAbility` a un `CreateTrigger` d'INIT
        (`OnOwnerSpecificAbilityInit`) -> `ABILITY_INIT_OWNER_EFFECTS`.

    Les inscrire tous deux au meme registre ferait, selon le sens : soit poser l'aura de degat a
    chaque fin de tour, soit ne jamais poser le buff d'armure. Aucune des deux fautes ne leve."""
    trig = [c.__name__ for c in (ABILITY_TRIGGERS.get(ABILITY) or [])]
    assert trig == ["IconOfObstinacyAddArmourBuffAbility"], trig
    assert list(ABILITY_INIT_OWNER_EFFECTS.get(ABILITY) or []) == [EXTRA_DMG_NAME]
    assert EFFECT_CLASSES.get(EXTRA_ARMOR_NAME) is IconOfObstinacyExtraArmorEffect
    assert EFFECT_CLASSES.get(EXTRA_DMG_NAME) is IconOfObstinacyExtraDmgEffect


def test_les_DEUX_faces_decision_sont_au_registre_sous_le_meme_id():
    """OWNER (`IconOfObstinacyPlaybook`, cle `..._LikesAdjacentTerminatorFriends`) et NON-OWNER
    (`IconOfObstinacyNonOwnerPlaybook`, cle `..._TerminatorFriendLikesToBeAdjacent`). Les deux
    poids sont NEUFS a ce build ; ils se cumulent sur une meme decision de mouvement."""
    aid = int(TriggeredAbilityType.IconOfObstinacy)
    assert type(load_playbook(aid)).__name__ == "IconOfObstinacyPlaybook"
    assert type(load_playbook_non_owner(aid)).__name__ == "IconOfObstinacyNonOwnerPlaybook"


def test_le_playbook_owner_ne_declare_NI_cap_NI_filtre():
    """Le `global-metadata.dat` ne declare pour cette classe que `[.ctor, GetAdjacentFriendUtility,
    GetAdjacentEnemyUtility]` -- ni `GetMaxAdjacentFriendsToCount` (le cap qui MORD chez
    `FabricatorClawArray`/`SpiritualLeader`) ni `FilterAdjacentFriends`. Poser un cap ici
    plafonnerait le terme a 1 voisin ; poser un filtre deplacerait un gate qui vit dans
    l'accesseur."""
    pb = load_playbook(int(TriggeredAbilityType.IconOfObstinacy))
    assert pb.MAX_ADJACENT_FRIENDS is None and pb.MAX_ADJACENT_ENEMIES is None
    assert pb.filter_adjacent_friend({}, {}) is True
    assert pb.get_adjacent_enemy_utility({}, None) == 0.0


# --------------------------------------------------------------------- etage 3 : la magnitude
@pytest.mark.parametrize("block_damage,attendu", [(0, 400), (1000, 700), (2349, 1105)])
def test_la_magnitude_est_flat_plus_pourcentage_du_blockdamage(block_damage, attendu):
    """`GetCurrentExtraArmour` = `extraArmor[lvl] + PercentageOf(GetStat(target, BlockDamage),
    chance)`, `roundingRule = 0`.

    `2349 -> 1105` est la MESURE LIVE (`probe_919`, deux beneficiaires) : `400 + 705`, ou
    `705 = round(2349 x 30 %)`. Le point d'ancrage est ce couple-la, pas une valeur inventee."""
    mods = _armour(block_damage)
    assert mods == [(int(StatType.FIXED_ARMOR), attendu)], mods


def test_la_variable_chance_n_est_PAS_scalee_par_la_rarete():
    """`variablesAffectedByRarityBonus` du gameconfig `IconOfObstinacy` = `["extraDmg",
    "extraArmor"]`. `chance` en est EXCLUE -- la scaler ferait grossir le terme `%` d'un facteur
    1,8 sur un Legendaire, silencieusement."""
    assert ability_var(ICON_OF_OBSTINACY, CHANCE_VAR, 50, multiplier_pct=100) == \
        ability_var(ICON_OF_OBSTINACY, CHANCE_VAR, 50, multiplier_pct=180)
    for var in (EXTRA_ARMOR_VAR, EXTRA_DMG_VAR):
        assert ability_var(ICON_OF_OBSTINACY, var, 50, multiplier_pct=180) > \
            ability_var(ICON_OF_OBSTINACY, var, 50, multiplier_pct=100), var


def test_sans_niveau_d_ability_la_magnitude_n_est_PAS_devinee():
    """`ConfigVar` sans `AbilityState` -> aucune magnitude. Rendre le flat << par defaut >>
    inventerait une valeur ; rendre 0 ferait croire a un effet inerte."""
    e = IconOfObstinacyExtraArmorEffect(EXTRA_ARMOR_NAME)
    e.ability_level = None
    assert e.applied_stat_mods(_StatsCtx(2349)) == []
    d = IconOfObstinacyExtraDmgEffect(EXTRA_DMG_NAME)
    d.ability_level = None
    assert d.create_effect_damage_bonus_for_attack(att_ctx={"owner_block_damage": 2349}) is None


def test_sans_blockdamage_publie_le_terme_pourcentage_est_OMIS_pas_devine():
    """Tri-etat : cle absente = `None` = NON MESURE -> seul `extraDmg`/`extraArmor` est rendu.
    Un 0 rabattu donnerait EXACTEMENT le meme nombre, mais en pretendant l'avoir mesure."""
    d = _dmg_effect()
    sans = d.create_effect_damage_bonus_for_attack()
    avec = d.create_effect_damage_bonus_for_attack(att_ctx={"owner_block_damage": 2349})
    assert int(sans.value) == int(ability_var(ICON_OF_OBSTINACY, EXTRA_DMG_VAR, 50,
                                              multiplier_pct=180))
    assert int(avec.value) > int(sans.value)


# ------------------------------------------------- etage 4 : les DEUX pattes du bonus de degat
def test_les_deux_pattes_du_bonus_de_degat_sont_DISJOINTES():
    """Le selecteur natif ADDITIONNE `Owner` au set filtre par trait (`op_Addition`), alors que les
    agregateurs d'aura EXCLUENT le beneficiaire (`uid == att_id`). La patte SELF
    (`create_effect_damage_bonus_for_attack`) et la patte ALLIES
    (`create_aura_attack_damage_bonus_for_ally`) couvrent donc des unites disjointes.

    Le mutant qu'il faut craindre est le DOUBLE-COMPTE : si la patte aura acceptait aussi le
    porteur (distance 0), il toucherait son bonus DEUX FOIS. On l'exerce ici."""
    d = _dmg_effect()
    ctx = {"owner_id": 7, "owner_pos": (3, 3), "owner_team": 0,
           "att_id": 7, "att_pos": (3, 3), "att_team": 0,
           "att_traits": (UnitTrait.TerminatorArmour.name,),
           "owner_stat_block_damage": {7: 2349}}
    assert d.create_aura_attack_damage_bonus_for_ally(ctx) is None, \
        "distance 0 = le porteur lui-meme : `AdjacentFriends` le retire (`- unit`)"
    ctx_adj = dict(ctx, att_id=9, att_pos=(3, 4))
    assert d.create_aura_attack_damage_bonus_for_ally(ctx_adj) is not None


@pytest.mark.parametrize("ctx_patch,motif", [
    ({"att_traits": ("Hero",)}, "gate TRAIT : un ami adjacent SANS TerminatorArmour"),
    ({"att_pos": (0, 0)}, "gate DISTANCE : un porteur du trait hors du ring-1"),
    ({"att_team": 1}, "gate EQUIPE : `Friends` = meme equipe que le porteur"),
])
def test_les_trois_gates_de_l_aura_de_degat_mordent(ctx_patch, motif):
    d = _dmg_effect()
    base = {"owner_id": 7, "owner_pos": (3, 3), "owner_team": 0,
            "att_id": 9, "att_pos": (3, 4), "att_team": 0,
            "att_traits": (UnitTrait.TerminatorArmour.name,),
            "owner_stat_block_damage": {7: 2349}}
    assert d.create_aura_attack_damage_bonus_for_ally(base) is not None, "temoin NUL : " + motif
    assert d.create_aura_attack_damage_bonus_for_ally(dict(base, **ctx_patch)) is None, motif


def test_pourcentage_of_est_l_arrondi_Fix64_demi_vers_le_pair():
    """`PercentageOf(..., roundingRule = 0)` = `Fix64.Round`. `2349 x 30 % = 704,7 -> 705` est la
    valeur qui, ajoutee a 400, rend le `1105` MESURE live."""
    assert _percentage_of(2349, 30) == 705
    assert _percentage_of(0, 30) == 0 and _percentage_of(2349, 0) == 0
