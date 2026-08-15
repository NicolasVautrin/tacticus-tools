"""#419-r1-tr9-r4-r1-r2-r1c-r1 -- `LegendaryCommander_ExtraDamage` (1394) : le port, et surtout ce
qui le SEPARE de son JUMEAU `LegendaryCommander_ExtraHits` (1395), deja porte.

Les deux effets sont poses PAR LE MEME `AddEffect(0x572, ..) & AddEffect(0x573, ..)`
(`...Triggered.Loki.LegendaryCommanderAbility$$CreateBehaviour`), partagent la MEME ability source
et le MEME tronc de selecteur -- et divergent sur QUATRE axes que seule la lecture du decompile
donne. Ce fichier plombe les quatre, plus le tri-etat.

  * 1394 prend le selecteur de la BASE (`ALegendaryCommander_BaseEffect$$CreateTargetSelector`,
    TROIS noeuds) ; 1395 SURCHARGE et ajoute `Filter(., IsAdjacent(Owner@+0x30, Subject@+0x68, 3))`.
    Recopier ce 4e noeud ici fermerait le bonus des que Trajann n'est pas colle a la cible -- c'est
    le << If the affected enemies are ALSO adjacent to Trajann >> de l'i2, propre a la face COUPS.
  * 1394 n'a AUCUN gate de nature d'attaque ; 1395 porte `!IsNormalAttack`.
  * 1394 verse un ADDITIF de degat (`ForAddition(ConfigVar(8 = extraDmg))`) ; 1395 des COUPS
    (`ConfigVar(0x2f = nrOfHits)`).
  * 1394 n'a NI etat persistant NI `IsFirstHitGroupInAttack` ; 1395 a les deux.

Et un cinquieme, contre l'i2 : `<< +[extraDmg] damage from friendly **Characters** >>` -- le natif
ne teste AUCUN `HasTrait(Caster, Hero)`. L'i2 SUR-SPECIFIE.
"""
from __future__ import annotations

import pytest

from engine.entities.effects.factory import EFFECT_CLASSES
from engine.entities.effect_type import EffectType
from engine.entities.effects.loki.legendary_commander import (
    ABILITY_ID, CTX_USED_ACTIVE_BY_ID, LegendaryCommanderExtraDamageEffect)
from engine.entities.effects.loki.extra_damage_aura import CTX_TGT_ADJACENT_UNIT_PROFILES

#: Ce que ce fichier LIT, donc ce qui doit changer pour qu'il puisse changer de verdict.
#: PRIS LARGE a dessein (trop etroit est un faux vert) : `hits.py` y entre parce que l'etage 11
#: confronte le port au JUMEAU 1395 par son source ; les DEUX foyers de prediction/combat parce
#: que l'etage 13 exige que la cle de contexte soit posee des DEUX cotes ; `extra_damage_aura`
#: parce que la constante `CTX_TGT_ADJACENT_UNIT_PROFILES` y vit (foyer de nommage #1025-r1).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/legendary_commander.py",
        "scripts/python/engine/entities/effects/loki/hits.py",
        "scripts/python/engine/entities/effects/loki/extra_damage_aura.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/playbook/prediction/_shared.py",
        "scripts/python/engine/services/effect_bonus.py",
        "data/gameconfig.json",
    ),
    "build": False,          # ne lit ni le binaire ni `data/symbols/**`
    "toujours": False,
    "raison": "le port de 1394 (classe, registre, canal aura-defense) et les DEUX substrats de "
              "contexte qui l'alimentent ; plus le gameconfig, dont `LegendaryCommander.extraDmg` "
              "et `variablesAffectedByRarityBonus` sont lus par les etages 3 et 4.",
}

_NOM = "LegendaryCommander_ExtraDamage"
_NOM_JUMEAU = "LegendaryCommander_ExtraHits"
#: equipes arbitraires mais DISTINCTES -- le port ne lit que l'egalite, jamais la valeur.
_TEAM_PORTEUR, _TEAM_ENNEMI = 0, 1
#: ids arbitraires : porteur (Trajann), un allie, la cible ennemie, un attaquant allie.
_OWNER, _ALLIE, _CIBLE, _ATT = 81, 82, 91, 83


def _effet(level: int = 50, mult: int | None = None, source: int | None = _OWNER):
    e = LegendaryCommanderExtraDamageEffect(_NOM, ability_level=level)
    e.ability_variables_multiplier = mult
    e.source = source
    return e


def _profil(uid: int, team: int):
    """Un element de `tgt_adjacent_unit_profiles` : `(uid, team, visual_id, rarity, is_hero)`."""
    return (uid, team, None, None, False)


def _ctx(**kw):
    """Contexte NOMINAL : l'allie `_ALLIE` a caste une active et est adjacent a la cible ennemie."""
    base = {
        "owner_id": _OWNER, "owner_team": _TEAM_PORTEUR,
        "tgt_id": _CIBLE, "tgt_team": _TEAM_ENNEMI,
        "att_id": _ATT, "att_team": _TEAM_PORTEUR,
        CTX_TGT_ADJACENT_UNIT_PROFILES: (_profil(_ALLIE, _TEAM_PORTEUR),),
        CTX_USED_ACTIVE_BY_ID: {_ALLIE: True},
    }
    base.update(kw)
    return base


# ------------------------------------------------------------------ [1] registre et identite ----
def test_1_effet_au_registre_par_son_nom_plein():
    """`EFFECT_CLASSES` est cle par le NOM, jamais par l'ordinal -- l'interroger par `1394` rend un
    faux negatif (piege mesure sur `1400`, #1078-r3)."""
    assert _NOM in EFFECT_CLASSES, "1394 doit etre au registre, sinon EffectFactory en fait un " \
                                   "BaseEffect NU : visible dans la liste, INERTE sur le degat"
    assert EFFECT_CLASSES[_NOM] is LegendaryCommanderExtraDamageEffect
    assert _NOM_JUMEAU in EFFECT_CLASSES, "le temoin (axe COUPS) doit rester porte"
    assert EFFECT_CLASSES[_NOM] is not EFFECT_CLASSES[_NOM_JUMEAU], \
        "deux EffectType distincts, deux classes distinctes"
    # L'ordinal est LU du mirror, pas ecrit ici : c'est ce couple qui se perime au renumerotage.
    assert int(EffectType.LegendaryCommander_ExtraDamage) == 1394
    assert int(EffectType.LegendaryCommander_ExtraHits) == 1395


def test_2_face_native_est_attaquant():
    """Le slot natif est `$$CreateEffectDamageBonusForAttack` -- le natif verse dans
    `attackModifiers` -- alors que le port l'evalue par le canal AURA-DEFENSE. La face vient donc de
    la CLASSE (#437-r1-r1-r1), et c'est une consequence ARITHMETIQUE, pas une etiquette."""
    assert LegendaryCommanderExtraDamageEffect.AURA_DEFENSE_MALUS_NATIVE_FACE == "attacker"


# ------------------------------------------------------------------ [3] le cas NOMINAL ----------
def test_3_cas_nominal_verse_extra_dmg():
    from engine.entities.effects.magnitude import ability_var
    attendu = ability_var(ABILITY_ID, "extraDmg", 50, multiplier_pct=None)
    assert attendu, "le gameconfig doit porter `LegendaryCommander.extraDmg` (sinon test vacant)"
    eb = _effet().create_aura_defense_damage_malus_for_ally(_ctx())
    assert eb is not None, "cas nominal : un allie ayant caste est adjacent a la cible ennemie"
    assert eb.value == int(attendu), "canal EffectBonus +0x10 = ForAddition, additif PLAT"
    assert eb.kind == "Addition", \
        "`ForAddition`, PAS `ForPercentIncrease` (contraste MoreGitzOverEre, meme forme d'aura)"
    assert eb.native_face == "attacker", "pose par l'agregateur depuis la CLASSE (#437-r1-r1-r1)"


def test_4_extra_dmg_scale_par_la_rarete():
    """`extraDmg` EST dans `variablesAffectedByRarityBonus` (lu au gameconfig) -> le multiplier
    du porteur s'applique. Sans cet axe, un port a plat sous-estimerait tout porteur rare."""
    import gameconfig as GC
    assert "extraDmg" in (GC.ability(ABILITY_ID) or {}).get("variablesAffectedByRarityBonus", []), \
        "premisse du test : si le gameconfig change, c'est CE test qui doit bouger"
    nu = _effet(mult=None).create_aura_defense_damage_malus_for_ally(_ctx())
    x2 = _effet(mult=200).create_aura_defense_damage_malus_for_ally(_ctx())
    assert nu is not None and x2 is not None
    assert x2.value == 2 * nu.value, "multiplier de rarete non applique (attendu x2 a mult=200)"


# ------------------------------------------ [5] LE DISCRIMINANT : le 4e noeud N'EST PAS ICI -----
def test_5_aucun_gate_d_adjacence_au_porteur():
    """`ALegendaryCommander_BaseEffect$$CreateTargetSelector` a TROIS noeuds. Le QUATRIEME,
    `Filter(., IsAdjacent(Owner@+0x30, Subject@+0x68, 3))`, n'existe QUE sur la surcharge de 1395.

    CONTRE-EPREUVE EXECUTABLE : on prive le ctx de TOUTE information sur la position du PORTEUR
    (`owner_pos` absent, et le porteur ne figure pas parmi les voisins de la cible). Si un 4e noeud
    avait ete recopie, il ne pourrait pas etre satisfait et le bonus tomberait. Il doit MORDRE."""
    ctx = _ctx()
    assert "owner_pos" not in ctx, "le montage doit rester muet sur la position du porteur"
    assert _OWNER not in [p[0] for p in ctx[CTX_TGT_ADJACENT_UNIT_PROFILES]], \
        "Trajann NE DOIT PAS etre voisin de la cible dans ce montage"
    assert _effet().create_aura_defense_damage_malus_for_ally(ctx) is not None, \
        "1394 mord meme quand le porteur est LOIN de la cible -- c'est ce qui le separe de 1395"


def test_6_aucun_gate_de_nature_d_attaque():
    """Ni `IsNormalAttack` (contraste 1395, qui le porte EN NEGATION), ni `IsMeleeAttack`
    (contraste `MoreGitzOverEre`). Le bonus vaut pour TOUT vecteur."""
    for cle, valeurs in (("is_normal_attack", (True, False, None)),
                         ("is_melee", (True, False, None))):
        for v in valeurs:
            eb = _effet().create_aura_defense_damage_malus_for_ally(_ctx(**{cle: v}))
            assert eb is not None, "aucun gate natif sur %s=%r" % (cle, v)


def test_7_aucun_gate_de_trait_hero_malgre_l_i2():
    """L'i2 dit << from friendly **Characters** >>, le natif ne teste AUCUN `HasTrait(Caster,
    0x10 = Hero)`. Un attaquant SANS trait Hero doit toucher le bonus."""
    eb = _effet().create_aura_defense_damage_malus_for_ally(_ctx(att_traits=frozenset()))
    assert eb is not None, "gate Hero recopie de l'i2 -- le decompile n'en porte aucun"


def test_8_le_porteur_qui_attaque_lui_meme_touche_le_bonus():
    """`AreFriends(Caster, EffectSource)` est VRAI quand `Caster == EffectSource`
    (`UnitExtensions$$IsFriend` n'ecarte pas l'egalite), et l'agregateur DEFENSE n'exclut pas
    `att_id == owner_id`. Ajouter une exclusion serait un ECART au natif."""
    eb = _effet().create_aura_defense_damage_malus_for_ally(_ctx(att_id=_OWNER))
    assert eb is not None


def test_9_trajann_arme_sa_propre_aura():
    """`Friends(Owner@+0x30, AllUnits@+0x20, 3)` ne SOUSTRAIT PAS le porteur : le cast d'active de
    Trajann lui-meme suffit a marquer les ennemis qui lui sont adjacents."""
    ctx = _ctx(**{CTX_TGT_ADJACENT_UNIT_PROFILES: (_profil(_OWNER, _TEAM_PORTEUR),),
                  CTX_USED_ACTIVE_BY_ID: {_OWNER: True}})
    assert _effet().create_aura_defense_damage_malus_for_ally(ctx) is not None


# ------------------------------------------------------------------ [10] les GATES qui FERMENT --
@pytest.mark.parametrize("kw, pourquoi", [
    ({"att_team": _TEAM_ENNEMI}, "AreFriends(Caster, EffectSource) -- attaquant ennemi du porteur"),
    ({"att_team": None}, "att_team NON MESURE -> gate FERME, jamais suppose vrai"),
    ({"owner_team": None}, "owner_team NON MESURE -> gate FERME"),
    ({"tgt_team": _TEAM_PORTEUR}, "AdjacentEnemies -- la cible doit etre ENNEMIE du porteur"),
    ({"tgt_team": None}, "tgt_team NON MESURE -> gate FERME"),
    ({CTX_TGT_ADJACENT_UNIT_PROFILES: None}, "voisinage NON MESURE -> gate FERME, pas un vide"),
    ({CTX_USED_ACTIVE_BY_ID: None}, "flags NON MESURES -> gate FERME"),
    ({CTX_TGT_ADJACENT_UNIT_PROFILES: ()}, "MESURE et vide : aucun voisin -> aucun bonus"),
    ({CTX_USED_ACTIVE_BY_ID: {_ALLIE: False}}, "le voisin n'a PAS caste d'active ce tour"),
    ({CTX_USED_ACTIVE_BY_ID: {_ALLIE: None}}, "capteur unitFlags muet -> restrictif, pas permissif"),
    ({CTX_TGT_ADJACENT_UNIT_PROFILES: ((_ALLIE, _TEAM_ENNEMI, None, None, False),)},
     "Friends(Owner, ...) -- un voisin ENNEMI du porteur ne compte pas, meme s'il a caste"),
    ({CTX_TGT_ADJACENT_UNIT_PROFILES: ((_ALLIE, None, None, None, False),)},
     "voisin sans equipe mesuree -> ecarte"),
])
def test_10_gates_fermants(kw, pourquoi):
    assert _effet().create_aura_defense_damage_malus_for_ally(_ctx(**kw)) is None, pourquoi


def test_11_meme_lecture_d_ability_state_que_le_jumeau():
    """`GetAbilityState(this)` designe le MEME etat pour 1394 et 1395 (meme `AbilityOrEffect`, pose
    par le MEME `CreateBehaviour`). Les deux faces doivent donc lire `self.ability_level` de la MEME
    facon -- et notamment PARTAGER le repli d'`ability_var` sur un niveau non renseigne.

    Ce test FIGE ce repli (`level None` -> 1er echelon) plutot que de le supposer : ecrire un garde
    `if ability_level is None: return None` ICI et pas chez le jumeau serait un FORK sur un seul des
    deux axes du meme `AddEffect`, invisible tant qu'aucun scenario ne pose l'effet sans niveau."""
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.effects.loki.hits import LegendaryCommanderExtraHitsEffect

    e = LegendaryCommanderExtraDamageEffect(_NOM, ability_level=None)
    e.source = _OWNER
    eb = e.create_aura_defense_damage_malus_for_ally(_ctx())
    attendu = ability_var(ABILITY_ID, "extraDmg", None)
    assert attendu, "premisse : `ability_var` a un repli non nul sur un niveau absent"
    assert eb is not None and eb.value == int(attendu), \
        "1394 doit suivre le repli d'`ability_var`, comme 1395 (aucun des deux ne garde)"
    # Le jumeau lit la MEME ability et ne pose aucun garde de niveau : on le CONSTATE au source.
    import inspect
    src = inspect.getsource(LegendaryCommanderExtraHitsEffect.create_aura_hits_bonus_for_attack)
    assert "ability_var(\"LegendaryCommander\"" in src
    assert "ability_level is None" not in src, \
        "si le jumeau se met a garder, 1394 doit garder aussi -- ce test est le cliquet"


def test_12_le_ctx_vide_ne_leve_pas():
    """Robustesse du canal : aucun appelant ne doit pouvoir faire lever cet effet."""
    assert _effet().create_aura_defense_damage_malus_for_ally(None) is None
    assert _effet().create_aura_defense_damage_malus_for_ally({}) is None


# --------------------------------------------- [13] le substrat est CABLE sur les DEUX faces ----
def test_13_les_deux_faces_publient_la_cle_du_selecteur():
    """La cle `used_active_by_id` doit etre posee par la face COMBAT **et** par la face PREDICTION
    du canal AURA-DEFENSE : la poser d'un seul cote creerait un fork silencieux (le vice repare par
    #1025-r1 pour `tgt_rarity`/`team_by_id`). On lit le SOURCE des deux foyers -- un import ne
    prouverait pas que la cle entre reellement dans le ctx."""
    from pathlib import Path

    from engine.playbook.prediction import _shared
    from engine.runner import damage_model

    for mod in (damage_model, _shared):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "_LC_CTX_USED_ACTIVE:" in src, \
            "%s ne pose pas la cle dans son ctx d'aura-defense" % mod.__name__
        assert "CTX_USED_ACTIVE_BY_ID as _LC_CTX_USED_ACTIVE" in src, \
            "%s doit importer la CONSTANTE, pas re-declarer la chaine (fork de nommage)" \
            % mod.__name__
