"""#10019-r2 -- la face PREDICTION des DEUX jumeaux de `MasterAnnihilator` sur le canal #179.

CE QUE LA TRANCHE ETABLIT, ET D'OU CA VIENT. La fiche demandait de ne PAS generaliser la mesure
#10019 (`MasterAnnihilator` predit un coup de plus) aux deux autres porteurs de
`FirstHitInCurrentAttackDamageRange`. Ce fichier ne generalise pas : il fige une lecture du corps
PARTAGE, `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits(entities, isPrediction)`, qui

    * evalue `trigger.ShouldTrigger(entities)`      -- IDENTIQUE sur les deux faces ;
    * evalue `hitsFormula.Calculate(entities) ?? 1` -- IDENTIQUE sur les deux faces ;
    * ne consulte `isPrediction` QUE pour choisir la formule de DEGAT, entre
      `predictionDamageFormula` (le 7e parametre, NOMME dans la metadata de
      `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create`) et `damageFormula`.

Donc le COMPTE de coups d'un descripteur `EffectAdditionalHits` est face-INDEPENDANT, et
`IdunBattle.Entities.Abilities.AActiveAbility$$AddAdditionalHitsToPrediction` `Add`e une prediction
par entree, avec le `hits` de l'entree. Ce que la face PREDICTION change, c'est la VALEUR du coup,
jamais son EXISTENCE.

⚠ CE QUI RESTE OUVERT, et ce fichier ne le tranche PAS : par quel chemin le coup PREDIT recupere le
degat d'un coup d'ARME, alors que
`IdunBattle.Entities.Formulas.FirstHitInCurrentAttackDamageRange$$Calculate` rend `0` hors
`OngoingAttack` (LU : liste nulle ou `Count <= 0` -> `return 0`). C'est le residu `#10019-r1`,
`BLOCAGE: capteur`. Il porte sur la VALEUR ; ce fichier-ci porte sur le COMPTE.

Etages :
  1. PEREMPTION -- la signature native de `EffectAdditionalHits$$Create` porte bien un parametre
     nomme `predictionDamageFormula` en 7e position, LU dans `frida/methods.tsv` du build qui fait
     foi. Si un build renomme ou reordonne, cet etage rougit AVANT que la prose ne mente.
  2. Les DEUX faces sont SEPAREES chez les deux porteurs (combat inchange, prediction +N).
  3. Le GATE est ECRIT UNE FOIS : casser le gate eteint les DEUX faces ensemble.
  4. La FORMULE propage `is_prediction` au canal ATTAQUANT -- c'est le maillon qui manquait
     (`att_hits_ctx` etait bati AVANT le `board` qui porte la cle).
  5. NON-REGRESSION #204 : la face COMBAT d'`AstartesBanner` reste le groupe #179, au bit pres.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.entities.effects import aura_hits_bonus_for_attack, hits_bonus_from_effects  # noqa: E402
from engine.entities.effects.loki.hits import (AstartesBannerExtraHitEffect,  # noqa: E402
                                               LetTheGalaxyBurnEffect)
from engine.services.attack_hits_formula import attack_hits_with_modifiers  # noqa: E402
from symbols_layout import build_dir  # noqa: E402

#: `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create` -- l'ORDRE des parametres, LU.
CREATE_PARAMS = ("trigger", "damageFormula", "additionalHitsType", "damageProfileType",
                 "hitsFormula", "forceOverkill", "predictionDamageFormula", "maxDamage")

TUILE = (3, 4)


@pytest.fixture()
def ltgb():
    return LetTheGalaxyBurnEffect(name="LetTheGalaxyBurn")


@pytest.fixture()
def banner():
    return AstartesBannerExtraHitEffect(name="AstartesBanner_ExtraHit")


def _ctx_ltgb(*, tuile_armee: bool, prediction: bool) -> dict:
    return {"t_pos": TUILE,
            "tile_effects_by_pos": {TUILE: (["DespoiledGround"] if tuile_armee else [])},
            "is_prediction": prediction}


def _ctx_banner(*, dans_rayon: bool, melee: bool, prediction: bool) -> dict:
    return {"is_melee": melee, "att_id": 2, "owner_id": 1, "owner_team": 0, "att_team": 0,
            "owner_pos": (0, 0), "att_pos": ((1, 0) if dans_rayon else (9, 9)),
            "is_prediction": prediction}


# ---------------------------------------------------------------------------------------------
# ETAGE 1 -- PEREMPTION : le 7e parametre s'appelle bien `predictionDamageFormula`
# ---------------------------------------------------------------------------------------------

def test_le_septieme_parametre_de_create_se_nomme_prediction_damage_formula():
    """Toute la tranche repose sur ce NOM : le port l'appelait << display >>, ce qui masquait
    qu'il gouverne la face PREDICTION. Si un build le renomme ou le deplace, on veut le savoir
    ici, pas en lisant du decompile qui ne correspond plus a la prose."""
    tsv = build_dir() / "frida" / "methods.tsv"
    ligne = None
    for l in tsv.read_text(encoding="utf-8", errors="replace").splitlines():
        col = l.split("\t")
        if len(col) > 2 and col[1] == "IdunBattle.Entities.Effects.EffectAdditionalHits.Create":
            ligne = col
            break
    assert ligne is not None, "`EffectAdditionalHits.Create` absente de methods.tsv"
    noms = tuple(p.split(":", 1)[0] for p in ligne[5].split(","))
    assert noms == CREATE_PARAMS, (
        "la signature native a bouge : %r != %r -- relire le decompile AVANT de croire la prose"
        % (noms, CREATE_PARAMS))
    # Le temoin de non-degenerescence de cet etage : l'assertion ci-dessus serait vraie sur un
    # tuple vide si `noms` etait vide.
    assert len(noms) == 8 and noms[6] == "predictionDamageFormula"


# ---------------------------------------------------------------------------------------------
# ETAGE 2 -- les DEUX faces sont SEPAREES
# ---------------------------------------------------------------------------------------------

def test_ltgb_la_face_combat_ne_gagne_rien_sur_le_canal_des_coups(ltgb):
    """Le COMBAT garde INTEGRALEMENT le groupe #179 (#227/#204) : ce canal-ci doit y etre muet,
    sinon le coup serait compte DEUX fois."""
    assert ltgb.create_effect_hits_bonus_for_attack(
        True, _ctx_ltgb(tuile_armee=True, prediction=False)) is None
    assert hits_bonus_from_effects([ltgb], True,
                                   att_ctx=_ctx_ltgb(tuile_armee=True, prediction=False)) == 0


def test_ltgb_la_face_prediction_gagne_un_coup_quand_la_tuile_est_armee(ltgb):
    eb = ltgb.create_effect_hits_bonus_for_attack(True, _ctx_ltgb(tuile_armee=True, prediction=True))
    assert eb is not None and eb.kind == "Addition" and eb.value == 1
    assert hits_bonus_from_effects([ltgb], True,
                                   att_ctx=_ctx_ltgb(tuile_armee=True, prediction=True)) == 1


def test_ltgb_la_face_prediction_est_muette_quand_la_tuile_ne_l_est_pas(ltgb):
    """Le TEMOIN NEGATIF de l'etage : sans lui, un port qui rendrait +1 INCONDITIONNELLEMENT
    passerait le test precedent."""
    assert ltgb.create_effect_hits_bonus_for_attack(
        True, _ctx_ltgb(tuile_armee=False, prediction=True)) is None


def test_banner_les_deux_faces_du_canal_aura(banner):
    assert banner.create_aura_hits_bonus_for_attack(
        _ctx_banner(dans_rayon=True, melee=True, prediction=False)) is None
    eb = banner.create_aura_hits_bonus_for_attack(
        _ctx_banner(dans_rayon=True, melee=True, prediction=True))
    assert eb is not None and eb.kind == "Addition" and eb.value >= 1
    porteurs = [(1, (0, 0), 0, [banner])]
    assert aura_hits_bonus_for_attack(
        porteurs, _ctx_banner(dans_rayon=True, melee=True, prediction=True)) >= 1
    assert aura_hits_bonus_for_attack(
        porteurs, _ctx_banner(dans_rayon=True, melee=True, prediction=False)) == 0


@pytest.mark.parametrize("dans_rayon,melee", [(False, True), (True, False)])
def test_banner_le_selecteur_et_le_trigger_ferment_en_prediction(banner, dans_rayon, melee):
    """`SurroundingFriends(range = 2)` et `IsMeleeAttack` -- les deux noeuds du natif, evaluables
    en prediction, doivent y mordre exactement comme en combat."""
    assert banner.create_aura_hits_bonus_for_attack(
        _ctx_banner(dans_rayon=dans_rayon, melee=melee, prediction=True)) is None


# ---------------------------------------------------------------------------------------------
# ETAGE 3 -- le GATE est ECRIT UNE FOIS (le natif n'a qu'UN trigger)
# ---------------------------------------------------------------------------------------------

def test_ltgb_les_deux_faces_partagent_le_meme_gate(monkeypatch, ltgb):
    combat = _ctx_ltgb(tuile_armee=True, prediction=False)
    combat["attack_hit_damage"] = (100, 100)
    assert ltgb.additional_hit_groups(combat), "temoin : la face COMBAT mord avant la mutation"
    assert ltgb.create_effect_hits_bonus_for_attack(
        True, _ctx_ltgb(tuile_armee=True, prediction=True)) is not None

    monkeypatch.setattr(LetTheGalaxyBurnEffect, "_trigger_fires", lambda self, ctx=None: False)
    assert ltgb.additional_hit_groups(combat) is None
    assert ltgb.create_effect_hits_bonus_for_attack(
        True, _ctx_ltgb(tuile_armee=True, prediction=True)) is None


def test_banner_les_deux_faces_partagent_le_meme_compte(monkeypatch, banner):
    combat = _ctx_banner(dans_rayon=True, melee=True, prediction=False)
    combat["attack_hit_damage"] = (100, 100)
    groupe = banner.create_aura_additional_hits_for_ally(combat)
    assert groupe is not None, "temoin : la face COMBAT mord avant la mutation"
    eb = banner.create_aura_hits_bonus_for_attack(
        _ctx_banner(dans_rayon=True, melee=True, prediction=True))
    # LE MEME `hitsFormula` des deux cotes -- c'est le fait natif que le port doit rendre.
    assert groupe["count"] == eb.value

    monkeypatch.setattr(AstartesBannerExtraHitEffect, "_hits_if_trigger_and_selector",
                        lambda self, ctx=None: None)
    assert banner.create_aura_additional_hits_for_ally(combat) is None
    assert banner.create_aura_hits_bonus_for_attack(
        _ctx_banner(dans_rayon=True, melee=True, prediction=True)) is None


# ---------------------------------------------------------------------------------------------
# ETAGE 4 -- la FORMULE propage `is_prediction` au canal ATTAQUANT
# ---------------------------------------------------------------------------------------------

def _formule(effets_attaquant, aura, *, is_prediction: bool) -> int:
    board = {"att_id": 2, "tgt_id": 9, "attack_pos": (1, 0), "t_pos": TUILE,
             "pos_by_id": {2: (1, 0), 9: TUILE, 1: (0, 0)},
             "team_by_id": {2: 0, 9: 1, 1: 0},
             "tile_effects_by_pos": {TUILE: ["DespoiledGround"]}}
    return attack_hits_with_modifiers(
        weapon_hits=4, extra_hits=0, extra_hits_melee=0,
        attacker_effects=effets_attaquant, trait_objects=[], target_effects=[],
        aura_sources=aura, board=board, is_melee=True, damage_profile=None,
        is_prediction=is_prediction)


def test_la_formule_thread_is_prediction_jusqu_au_canal_attaquant(ltgb):
    """LE MAILLON QUI MANQUAIT. `att_hits_ctx` etait bati AVANT le `board` qui porte la cle, donc
    un porteur ATTAQUANT ne pouvait PAS voir la face -- le port aurait ete inerte en silence."""
    assert _formule([], [], is_prediction=True) == 4, "temoin sans porteur"
    assert _formule([ltgb], [], is_prediction=False) == 4, "la face COMBAT reste a 4"
    assert _formule([ltgb], [], is_prediction=True) == 5, "la face PREDICTION gagne le coup"


def test_la_formule_thread_is_prediction_jusqu_au_canal_aura(banner):
    porteurs = [(1, (0, 0), 0, [banner])]
    assert _formule([], porteurs, is_prediction=False) == 4
    assert _formule([], porteurs, is_prediction=True) == 5


def test_le_defaut_de_la_formule_est_le_combat(ltgb, banner):
    """`is_prediction` par defaut = `False` : tout appelant anterieur a la tranche garde
    EXACTEMENT son comportement, y compris les quatre facades de combat et les probes."""
    board = {"att_id": 2, "tgt_id": 9, "attack_pos": (1, 0), "t_pos": TUILE,
             "pos_by_id": {2: (1, 0), 9: TUILE, 1: (0, 0)}, "team_by_id": {2: 0, 9: 1, 1: 0},
             "tile_effects_by_pos": {TUILE: ["DespoiledGround"]}}
    n = attack_hits_with_modifiers(
        weapon_hits=4, extra_hits=0, extra_hits_melee=0,
        attacker_effects=[ltgb], trait_objects=[], target_effects=[],
        aura_sources=[(1, (0, 0), 0, [banner])], board=board, is_melee=True, damage_profile=None)
    assert n == 4


# ---------------------------------------------------------------------------------------------
# ETAGE 5 -- NON-REGRESSION #204 : la face COMBAT d'`AstartesBanner` reste le groupe #179
# ---------------------------------------------------------------------------------------------

def test_le_groupe_179_de_combat_est_inchange(banner):
    """#204 a MESURE que l'evenement supplementaire de COMBAT vaut une CONSTANTE (le `HitDamage`
    brut de l'attaque), pas un coup d'arme. Ce verdict-la ne bouge pas."""
    ctx = _ctx_banner(dans_rayon=True, melee=True, prediction=False)
    ctx["attack_hit_damage"] = (4617, 4617)
    assert banner.create_aura_additional_hits_for_ally(ctx) == {
        "count": 1, "min": 4617, "max": 4617, "profile": None}
    # Et il ne depend PAS de la face : le groupe #179 se materialise a l'EXECUTION.
    ctx["is_prediction"] = True
    assert banner.create_aura_additional_hits_for_ally(ctx) == {
        "count": 1, "min": 4617, "max": 4617, "profile": None}
