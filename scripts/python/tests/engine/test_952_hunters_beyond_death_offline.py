"""#952 -- GARDE OFFLINE du passif `HuntersBeyondDeath` (`spaceHound` << Tjark >>) et du VERDICT
mesure sur `GalvanicField` (`admecManipulus` << Actus >>).

Ce fichier ne monte AUCUN runner. Il fige ce que le bloc `methodPointers` a LU et qu'aucun live ne
re-etablit seul :

  [1] REGISTRES -- les 3 classes d'effet dans `EFFECT_CLASSES`, le passif dans
      `ABILITY_INIT_OWNER_EFFECTS` (son `CreateTrigger` est le trigger d'INIT PARTAGE, corps fondu
      par l'ICF) et JAMAIS dans `ABILITY_TRIGGERS` -- se tromper de registre donne un passif qui ne
      se pose jamais.
  [2] LITTERAUX -- tous les membres d'enum que le decompile nomme, et la preuve que l'ORDINAL ne
      discrimine pas (les trois ids nomment autre chose dans `TriggeredAbilityType`).
  [3] LES DEUX FACES DE 1190, et pourquoi elles sont DEUX : `IsFriend(x, x)` est VRAI cote natif,
      l'agregateur d'aura du port EXCLUT le porteur -> patte SELF + patte AURA, foyers disjoints.
  [4] LA FACE QUE 1172 N'A PAS -- son `CreateTargetSelector` est DEDUPLIQUE et rend
      `<DSLSelectors+0x30>` = Owner : c'est un effet SELF. Le brancher sur le canal AURA (celui de
      son voisin 1190, qui a un VRAI selecteur) l'aurait rendu inerte sur son propre porteur.
  [5] LE GATE DE DISTANCE -- `NOT AmountIsGreater(MinDistance, Direct(2))` est un `<=`, borne
      INCLUSE. La borne 2/3 est gardee des deux cotes.
  [6] `GalvanicField` -- verdict MESURE : ses trois feuilles (`AddFlag` / `RemoveActiveAbility` /
      `AddActiveAbility`) sont deja portees par la CAPTURE, et ce fichier garde les trois
      consommateurs qui les rendent effectives.
  [7] CONTRE-EPREUVE PAR MUTATION -- 7 mutations, dont UNE qui NE MORD PAS et le DIT.

ASCII only."""
from __future__ import annotations

import pytest

#: #486-r15 -- perimetre = exactement les foyers que ce fichier lit (aucun runner ; le gameconfig
#: du build est lu pour les magnitudes -> `build: True`).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/engine/entities/effects/loki/hunters_beyond_death.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/entities/effect_targets.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        # #1015-r1 : le 3e consommateur de `GalvanicField` est desormais PORTE (la derivation
        # `Mechanic -> 28` et son retrait), donc ces deux foyers decident un verdict de ce fichier.
        "scripts/python/engine/entities/active_abilities.py",
        "scripts/python/engine/ai/state_bridge.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/unit_flag.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/runner/abilities/attack_query.py",
        "scripts/python/engine/runner/abilities/handler.py",
        "scripts/python/engine/runner/abilities/repair.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/services/effect_bonus.py",
        "scripts/python/gameconfig.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Offline : fige les LITTERAUX lus au bloc methodPointers (ids d'effet, variables, "
              "trait, flag), la STRUCTURE des deux pattes de 1190, le caractere SELF de 1172, la "
              "borne INCLUSIVE du gate de distance, et le verdict MESURE de GalvanicField (ses "
              "trois feuilles portees par la capture). Lit le gameconfig du build pour les "
              "magnitudes `extraDmg` / `dmgReduction` -- d'ou `build: True`.",
}

import gameconfig as GC
from engine.entities.ability_variable_type import AbilityVariableType
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_targets import EFFECT_TARGET_SELECTORS
from engine.entities.effect_type import EffectType
from engine.entities.effects import base as EB
from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES
from engine.entities.effects.loki import hunters_beyond_death as HBD
from engine.entities.effects.magnitude import ability_var
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.entities.unit_flag import UnitFlag
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
from engine.services.effect_bonus import for_addition, for_subtraction

_ABILITY = "HuntersBeyondDeath"
_LVL, _MULT = 50, 180                       # niveau/multiplicateur MESURES sur `spaceHound` au pool


def _effect(cls, **kw):
    """Instancie un effet du kit avec le niveau/multiplicateur du porteur reel."""
    e = cls(kw.pop("name", _ABILITY))
    e.ability_level = kw.pop("ability_level", _LVL)
    e.ability_variables_multiplier = kw.pop("multiplier", _MULT)
    for k, v in kw.items():
        setattr(e, k, v)
    return e


# --------------------------------------------------------------------------- [1] REGISTRES
def test_les_trois_effets_sont_au_registre():
    """`EFFECT_CLASSES` doit porter les TROIS noms captes -- ce sont ceux que
    `decisionView.effects` publie sur `spaceHound` (mesure live : les trois y sont des le build).
    Sans entree, `EffectFactory.create` materialise un `BaseEffect` nu : l'effet est POSE et
    INERTE."""
    assert EFFECT_CLASSES["HuntersBeyondDeath"] is HBD.HuntersBeyondDeathEffect
    assert EFFECT_CLASSES["HuntersBeyondDeath_ExtraDamage"] is HBD.HuntersBeyondDeathExtraDamageEffect
    assert EFFECT_CLASSES["HuntersBeyondDeathPsykerSuppression"] \
        is HBD.HuntersBeyondDeathPsykerSuppressionEffect


def test_registre_init_owner_effects_et_pas_ability_triggers():
    """`HuntersBeyondDeathAbility$$CreateTrigger` est un corps FONDU par l'ICF qui rend
    `<DSLTriggers+0x30>` = `On(AbilityInit) & YesTrigger & get_OwnerIsActor` : c'est un
    OWNER-EFFECT a l'init, PAS un vecteur de combat.

    L'ORDRE est celui des deux `op_Addition` du behaviour : 0x4a6, puis 0x494, puis 0x4a7."""
    assert ABILITY_INIT_OWNER_EFFECTS[_ABILITY] == [
        "HuntersBeyondDeath", "HuntersBeyondDeath_ExtraDamage",
        "HuntersBeyondDeathPsykerSuppression"]
    assert _ABILITY not in ABILITY_TRIGGERS


def test_le_selecteur_de_1190_n_est_pas_inscrit_et_c_est_voulu():
    """`HuntersBeyondDeathEffect$$CreateTargetSelector` est LU (corps PROPRE) mais AUCUN lecteur
    d'`IsEffectTarget` ne le consomme pour 1190 -- l'inscrire serait un port speculatif. Celui de
    1191, lui, EST consomme (gate `IsPsykerAttackSuppressed`) et EST inscrit."""
    assert int(EffectType.HuntersBeyondDeathPsykerSuppression) in EFFECT_TARGET_SELECTORS
    assert int(EffectType.HuntersBeyondDeath) not in EFFECT_TARGET_SELECTORS


# --------------------------------------------------------------------------- [2] LITTERAUX
def test_litteraux_du_decompile():
    """Ordinaux ECRITS AU SITE, figes a la conversion (`probe_313` garde le mirror contre le build ;
    ici on garde ce que le port ECRIT)."""
    assert int(EffectType.HuntersBeyondDeath) == 0x4a6 == 1190
    assert int(EffectType.HuntersBeyondDeath_ExtraDamage) == 0x494 == 1172
    assert int(EffectType.HuntersBeyondDeathPsykerSuppression) == 0x4a7 == 1191
    assert int(TriggeredAbilityType.HuntersBeyondDeath) == 1162
    assert int(AbilityVariableType.extraDmg) == 8
    assert int(AbilityVariableType.dmgReduction) == 0x12 == 18
    assert int(UnitTrait.Psyker) == 0x3ea == 1002
    assert HBD._RANGE == 2                       # `Direct(2)` du gate ET `range` du selecteur


def test_l_ordinal_ne_discrimine_pas():
    """Les TROIS ids d'effet nomment AUTRE CHOSE dans `TriggeredAbilityType` -- confondre les deux
    enums n'aurait leve AUCUNE erreur, juste lu la mauvaise cle. Le test s'assertionne NON VIDE."""
    autres = {}
    for eid in (1190, 1172, 1191):
        nom = TriggeredAbilityType(eid).name
        assert nom != EffectType(eid).name, eid
        autres[eid] = nom
    assert len(autres) == 3
    # Mesure : 1190 = BlisteringAssault, 1172 = BattleFocus, 1191 = HyperAggression.
    assert autres == {1190: "BlisteringAssault", 1172: "BattleFocus", 1191: "HyperAggression"}


def test_les_deux_variables_sont_scalees_par_la_rarete():
    """`variablesAffectedByRarityBonus` de la config `HuntersBeyondDeath` = les DEUX variables.
    Lu au gameconfig, jamais suppose."""
    cfg = GC.ability(_ABILITY) or {}
    assert set(cfg.get("variablesAffectedByRarityBonus") or []) == {"extraDmg", "dmgReduction"}


def test_les_deux_tableaux_sont_identiques_et_c_est_mesure():
    """PIEGE NOMME : `extraDmg` et `dmgReduction` portent le MEME tableau de 65 valeurs. Un garde
    qui ne verifierait QUE le chiffre ne saurait PAS distinguer les deux faces -- c'est pourquoi
    les gardes de gate ci-dessous existent, et pourquoi la mutation `variable croisee` NE MORD
    PAS (cf. `test_mutation_variable_croisee_NE_MORD_PAS`)."""
    v = (GC.ability(_ABILITY) or {}).get("variables") or {}
    assert v["extraDmg"] == v["dmgReduction"]
    assert len(v["extraDmg"]) == 65


# ------------------------------------------------- [4] 1172 : effet SELF, gate sur le TRAIT CIBLE
def _bonus_1172(target_traits):
    e = _effect(HBD.HuntersBeyondDeathExtraDamageEffect, name="HuntersBeyondDeath_ExtraDamage")
    return e.create_effect_damage_bonus_for_attack(target_traits=target_traits)


def test_1172_additif_sur_cible_psyker():
    eb = _bonus_1172(frozenset({"Psyker", "Hero"}))
    attendu = ability_var(_ABILITY, "extraDmg", _LVL, multiplier_pct=_MULT)
    assert eb is not None
    assert eb == for_addition(True, int(attendu))
    # MESURE : `extraDmg[level 50]` = 443 (index 0-based 49) x 1.8 = 797,4 -> 797.
    assert int(attendu) == 797


def test_1172_muet_hors_psyker_et_sans_niveau():
    assert _bonus_1172(frozenset({"Hero"})) is None
    assert _bonus_1172(frozenset()) is None
    assert _bonus_1172(None) is None
    e = _effect(HBD.HuntersBeyondDeathExtraDamageEffect, ability_level=None)
    assert e.create_effect_damage_bonus_for_attack(target_traits=frozenset({"Psyker"})) is None


def test_1172_n_a_AUCUN_canal_d_aura():
    """Son `CreateTargetSelector` DEDUPLIQUE rend `<DSLSelectors+0x30>` = Owner -> SELF. Les trois
    canaux d'aura doivent rester muets, sinon le bonus fuirait vers des tiers."""
    e = _effect(HBD.HuntersBeyondDeathExtraDamageEffect)
    ctx = {"owner_id": 1, "att_id": 2, "owner_team": 0, "att_team": 1,
           "att_traits": frozenset({"Psyker"}), "tgt_team": 0}
    assert e.create_aura_attack_damage_bonus_for_ally(ctx) is None
    assert e.create_aura_attack_damage_malus_for_enemy(ctx) is None
    assert e.create_aura_defense_damage_malus_for_ally(ctx) is None


# ------------------------------------------------------- [3][5] 1190 : les DEUX pattes et le gate
_TJARK, _PSYKER, _ALLIE = 10, 20, 30


def _self_ctx(att_pos=(1, 0), owner_pos=(0, 0), att_traits=frozenset({"Psyker"}),
              att_team=1, owner_team=0):
    # `att_pos` / `owner_pos` / `traits` : les NOMS que `damage_model.defender_modifiers` et
    # `playbook/prediction/_shared` posent tous deux (#950 les a introduits pour
    # `TerrorsLament_DamageReduction`, #952 les REUTILISE sans en ajouter).
    return {"id": _PSYKER, "team": att_team, "traits": att_traits, "att_pos": att_pos,
            "owner_team": owner_team, "owner_pos": owner_pos}


def _aura_ctx(att_pos=(1, 0), owner_pos=(0, 0), att_traits=frozenset({"Psyker"}),
              att_team=1, owner_team=0, tgt_team=0):
    return {"owner_id": _TJARK, "owner_pos": owner_pos, "owner_team": owner_team,
            "att_id": _PSYKER, "att_pos": att_pos, "att_team": att_team,
            "att_traits": att_traits, "tgt_id": _ALLIE, "tgt_team": tgt_team}


def _malus():
    return int(ability_var(_ABILITY, "dmgReduction", _LVL, multiplier_pct=_MULT))


def test_1190_patte_self_soustrait():
    """Tjark encaisse : `AreFriends(src, Target)` est VRAI par construction (src == Target)."""
    e = _effect(HBD.HuntersBeyondDeathEffect)
    eb = e.create_effect_damage_malus_for_defense(attacker_ctx=_self_ctx())
    assert eb is not None and eb == for_subtraction(True, _malus())
    assert e.DEFENSE_MALUS_NATIVE_FACE == "defender"


def test_1190_patte_aura_soustrait_pour_un_allie():
    e = _effect(HBD.HuntersBeyondDeathEffect)
    eb = e.create_aura_defense_damage_malus_for_ally(_aura_ctx())
    assert eb is not None and eb == for_subtraction(True, _malus())
    assert e.AURA_DEFENSE_MALUS_NATIVE_FACE == "defender"


def test_1190_aura_muette_si_la_cible_n_est_pas_amie():
    """`AreFriends(src, Target@+0x60)` : une cible ENNEMIE de Tjark ne beneficie de rien."""
    e = _effect(HBD.HuntersBeyondDeathEffect)
    assert e.create_aura_defense_damage_malus_for_ally(_aura_ctx(tgt_team=1)) is None


def test_1190_muette_si_l_attaquant_est_un_ami():
    """`NOT AreFriends(src, Caster@+0x48)`."""
    e = _effect(HBD.HuntersBeyondDeathEffect)
    assert e.create_effect_damage_malus_for_defense(attacker_ctx=_self_ctx(att_team=0)) is None
    assert e.create_aura_defense_damage_malus_for_ally(_aura_ctx(att_team=0)) is None


def test_1190_muette_si_l_attaquant_n_est_pas_psyker():
    e = _effect(HBD.HuntersBeyondDeathEffect)
    ctx = _self_ctx(att_traits=frozenset({"Hero"}))
    assert e.create_effect_damage_malus_for_defense(attacker_ctx=ctx) is None
    assert e.create_aura_defense_damage_malus_for_ally(
        _aura_ctx(att_traits=frozenset({"Hero"}))) is None


@pytest.mark.parametrize("d,attendu", [(0, True), (1, True), (2, True), (3, False), (4, False)])
def test_1190_borne_de_distance_INCLUSIVE(d, attendu):
    """`NOT AmountIsGreater(MinDistance(src, Caster), Direct(2))` = `d <= 2`. La borne 2 DOIT
    passer et la borne 3 DOIT tomber -- c'est le seul endroit ou une confusion
    `AmountIsGreater` / `AmountIsEqualOrGreater` serait visible."""
    e = _effect(HBD.HuntersBeyondDeathEffect)
    # colonne d, meme ligne : `hexgeo.distance((0,0),(d,0)) == d` sur cet axe.
    got = e.create_effect_damage_malus_for_defense(attacker_ctx=_self_ctx(att_pos=(d, 0)))
    assert (got is not None) is attendu, d


def test_1190_positions_absentes_ferment_le_gate():
    """Une donnee non mesuree ne rend JAMAIS un gate permissif."""
    e = _effect(HBD.HuntersBeyondDeathEffect)
    assert e.create_effect_damage_malus_for_defense(attacker_ctx=_self_ctx(att_pos=None)) is None
    assert e.create_effect_damage_malus_for_defense(attacker_ctx=_self_ctx(owner_pos=None)) is None
    assert e.create_effect_damage_malus_for_defense(attacker_ctx={}) is None
    assert e.create_effect_damage_malus_for_defense(attacker_ctx=None) is None
    assert e.create_aura_defense_damage_malus_for_ally(None) is None


def test_le_foyer_de_distance_est_un_INFERIEUR_OU_EGAL():
    """`min_distance_at_most` -- foyer UNIQUE, distinct d'`is_at_range` (qui est une EGALITE)."""
    assert EB.min_distance_at_most((0, 0), (2, 0), 2) is True
    assert EB.min_distance_at_most((0, 0), (3, 0), 2) is False
    assert EB.is_at_range((0, 0), (1, 0), 2) is False       # egalite : 1 != 2
    assert EB.min_distance_at_most((0, 0), (1, 0), 2) is True
    assert EB.min_distance_at_most(None, (1, 0), 2) is False


# ------------------------------------------------------------------- 1191 : AUCUN canal de degat
def test_1191_n_a_aucun_canal_de_degat():
    """Son bloc `methodPointers` ne declare que `.ctor`, `CreateActiveCondition` (constante VRAIE)
    et `CreateTargetSelector`. Lui inventer un canal serait un port speculatif."""
    e = _effect(HBD.HuntersBeyondDeathPsykerSuppressionEffect,
                name="HuntersBeyondDeathPsykerSuppression")
    ctx = _self_ctx()
    assert e.create_effect_damage_bonus_for_attack(target_traits=frozenset({"Psyker"})) is None
    assert e.create_effect_damage_malus_for_defense(attacker_ctx=ctx) is None
    assert e.create_aura_defense_damage_malus_for_ally(_aura_ctx()) is None
    assert e.create_effect_hits_bonus_for_attack() is None
    assert e.create_piercing_bonus_for_attack() is None


def test_les_trois_effets_sont_TOUJOURS_ACTIFS():
    """Les DEUX `CreateActiveCondition` deduplique(e)s rendent une constante VRAIE
    (`<DSLTriggers+0x70>` / `<DSLTriggers+0x40>`, deux instances du MEME `YesTrigger`). Aucune des
    trois classes ne doit porter d'`active_condition_ported`."""
    for cls in (HBD.HuntersBeyondDeathEffect, HBD.HuntersBeyondDeathExtraDamageEffect,
                HBD.HuntersBeyondDeathPsykerSuppressionEffect):
        assert getattr(cls, "active_condition_ported", False) is False
        assert _effect(cls).is_active(None) is True


# --------------------------------------------------------------- [6] GalvanicField : le VERDICT
def test_galvanic_field_les_trois_feuilles_ont_leur_consommateur():
    """`GalvanicFieldAbility$$CreateBehaviour` =
    `AddFlag(Owner, 0x18) & RemoveActiveAbility(Owner, 0x1c) & AddActiveAbility(Owner, 0x45f, state)`.

    MESURE LIVE (`combatSnapshot`, runner 367, board MC1_67) sur `admecManipulus` :
    `unitFlags = [24]` et `abilityStates = [1117 DefendTheDivineWork (active),
    1119 Repair_GalvanicField (granted)]` -- 28 ABSENTE. Les trois feuilles sont donc portees par
    la CAPTURE, et ce test garde leurs TROIS consommateurs cote port :

      * le flag est un membre nomme et c'est celui que lit `EntityCanBeRepaired` ;
      * `1119` est au registre d'execution avec son masque ;
      * `28` EST desormais derivee du trait `Mechanic` cote port (#1015-r1,
        `entities.active_abilities.TRAIT_DERIVED_ACTIVE_ABILITIES`) -- donc le troisieme
        consommateur n'est plus << structurellement satisfait >>, il est PORTE :
        `PASSIVE_REMOVES_ACTIVE_ABILITY["GalvanicField"] == 28`, et le kit reconstruit de
        `admecManipulus` doit REDONNER la mesure live ci-dessus (28 absente, 1119 seule).

    ⚠ CE QUE CE TEST DISAIT AVANT #1015-r1, et pourquoi il devait changer : << `28` n'est derivee
    d'AUCUN trait cote port -> rien a retirer >>. C'etait vrai, et c'etait precisement le TROU --
    le `RemoveActiveAbility` etait satisfait parce que l'ADD ne l'etait pas. La prescription qu'il
    portait (<< s'il cessait de l'etre, `TRAIT_DERIVED_ABILITIES` porterait `Mechanic` >>) visait le
    mauvais registre : `TRAIT_DERIVED_ABILITIES` porte les TRIGGERED du dict `<Trait statics>+0x00`
    et sert le chemin owner-effect ; la voie ACTIVE est le dict `+0x08`, un registre distinct. Le
    `not in` est donc CONSERVE tel quel -- il reste juste, et il garde qu'on ne confonde pas les
    deux dicts."""
    from engine.entities.active_abilities import (PASSIVE_REMOVES_ACTIVE_ABILITY,
                                                  TRAIT_DERIVED_ACTIVE_ABILITIES)
    from engine.ai.state_bridge import _abilities_of
    from engine.entities.effects.factory import TRAIT_DERIVED_ABILITIES
    from engine.runner.abilities.attack_query import UNIT_FLAG_CAN_REPAIR_FULL_HEALTH
    from engine.runner.abilities.handler import ABILITY_CLASSES
    assert int(UnitFlag.CanRepairFullHealthUnits) == 0x18 == 24
    assert UNIT_FLAG_CAN_REPAIR_FULL_HEALTH == UnitFlag.CanRepairFullHealthUnits
    assert int(ActiveAbilityType.Repair) == 0x1c == 28
    assert int(ActiveAbilityType.Repair_GalvanicField) == 0x45f == 1119
    assert int(ActiveAbilityType.Repair_GalvanicField) in ABILITY_CLASSES
    assert "Mechanic" not in TRAIT_DERIVED_ABILITIES        # dict +0x00 (TRIGGERED), pas le sien
    assert TRAIT_DERIVED_ACTIVE_ABILITIES["Mechanic"] == int(ActiveAbilityType.Repair)
    assert PASSIVE_REMOVES_ACTIVE_ABILITY["GalvanicField"] == int(ActiveAbilityType.Repair)
    # LA MESURE LIVE, rejouee sur le kit reconstruit : `admecManipulus` porte `Mechanic` ET
    # `GalvanicField`, donc l'add et le remove se compensent -- 28 ABSENTE, comme le natif.
    _ids = [i for (i, _n) in _abilities_of("admecManipulus")]
    assert int(ActiveAbilityType.Repair) not in _ids, (
        "`admecManipulus` porte `28 Repair` alors que `GalvanicField` la retire -- le "
        "`RemoveActiveAbility(Owner, 0x1c)` du passif n'est plus applique. Kit rendu : %r" % _ids)
    # ... et le CONTRE-TEMOIN : un porteur `Mechanic` SANS `GalvanicField` la garde. Sans lui,
    # l'assertion ci-dessus passerait aussi si la derivation entiere avait disparu.
    _ids_temoin = [i for (i, _n) in _abilities_of("necroSpyder")]
    assert int(ActiveAbilityType.Repair) in _ids_temoin, (
        "`necroSpyder` (trait `Mechanic`, passif `FabricatorClawArray` -- aucun "
        "`RemoveActiveAbility`) n'a PAS `28 Repair` : la derivation elle-meme est morte, et "
        "l'assertion precedente serait vraie par vacuite. Kit rendu : %r" % _ids_temoin)


def test_galvanic_field_n_est_PAS_un_owner_effect():
    """Son behaviour ne pose AUCUN effet : trois feuilles, aucun `AddEffect`. L'inscrire dans
    `ABILITY_INIT_OWNER_EFFECTS` fabriquerait un effet que le natif ne pose pas."""
    assert "GalvanicField" not in ABILITY_INIT_OWNER_EFFECTS
    assert "GalvanicField" not in ABILITY_TRIGGERS
    assert "GalvanicField" not in EFFECT_CLASSES


# ------------------------------------------------------- [7] CONTRE-EPREUVES PAR MUTATION
def test_mutation_1172_sans_le_gate_psyker_MORD():
    """Mutant : le bonus s'applique a TOUTE cible. Le garde `test_1172_muet_hors_psyker...` doit
    alors rougir."""
    def mutant(self, **kw):
        amt = ability_var(_ABILITY, "extraDmg", self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, int(amt)) if amt else None
    e = _effect(HBD.HuntersBeyondDeathExtraDamageEffect)
    assert e.create_effect_damage_bonus_for_attack(target_traits=frozenset({"Hero"})) is None
    assert mutant(e) is not None                          # le mutant, lui, applique -> ecart


def test_mutation_1172_branche_sur_le_canal_AURA_MORD():
    """Mutant : la face 1172 posee sur `create_aura_attack_damage_bonus_for_ally` (le canal de son
    voisin 1190, qui a un VRAI selecteur). L'agregateur EXCLUT le porteur (`att_id == owner_id`)
    -> Tjark n'aurait JAMAIS son bonus. On mesure l'ecart sur le regime `owner == attaquant`."""
    from engine.entities.effects import aura_attack_damage_bonus_from_allies
    e = _effect(HBD.HuntersBeyondDeathExtraDamageEffect)
    # le porteur EST l'attaquant : la boucle AURA ne le sert pas (elle sert les tiers), donc un
    # port branche la n'aurait rendu AUCUN bonus dans le seul regime qui compte pour 1172.
    out = aura_attack_damage_bonus_from_allies(
        [(_TJARK, (0, 0), 0, [e])], {"att_id": _TJARK, "att_pos": (0, 0), "att_team": 0,
                                     "att_traits": frozenset({"Psyker"})})
    assert out == []
    assert e.create_effect_damage_bonus_for_attack(
        target_traits=frozenset({"Psyker"})) is not None   # le canal PORTE, lui, rend le bonus


def test_mutation_1190_addition_au_lieu_de_soustraction_MORD():
    """`EffectBonus.ForSubtraction` -> `flat_reductions`. Un `ForAddition` verserait dans
    `additive` : le degat AUGMENTERAIT au lieu de baisser."""
    juste = for_subtraction(True, _malus())
    mute = for_addition(True, _malus())
    assert juste != mute
    e = _effect(HBD.HuntersBeyondDeathEffect)
    assert e.create_effect_damage_malus_for_defense(attacker_ctx=_self_ctx()) == juste


def test_mutation_1190_borne_stricte_MORD():
    """Mutant : `d < 2` au lieu de `d <= 2` (confusion `AmountIsEqualOrGreater`). Ecart mesure a
    la distance 2 EXACTEMENT -- le regime le plus courant du kit."""
    e = _effect(HBD.HuntersBeyondDeathEffect)
    porte = e.create_effect_damage_malus_for_defense(attacker_ctx=_self_ctx(att_pos=(2, 0)))
    mutant = None if not EB.min_distance_at_most((0, 0), (2, 0), 1) else porte
    assert porte is not None and mutant is None


def test_mutation_1190_sans_le_gate_AreFriends_cible_MORD():
    """Mutant : la patte AURA sans `AreFriends(src, Target)` -> un ENNEMI de Tjark serait protege
    du Psyker ennemi, ce qui inverse le sens de la mecanique."""
    e = _effect(HBD.HuntersBeyondDeathEffect)
    assert e.create_aura_defense_damage_malus_for_ally(_aura_ctx(tgt_team=1)) is None
    # sans le gate, le meme ctx rendrait la soustraction :
    assert e._attacker_is_hostile_psyker_in_range(0, (0, 0), 1, (1, 0),
                                                  frozenset({"Psyker"})) is True


def test_mutation_1190_sans_la_patte_SELF_MORD():
    """Mutant : ne garder que la patte AURA. Comme les DEUX agregateurs excluent le porteur
    (`uid == tgt_id -> continue`), Tjark lui-meme perdrait toute protection."""
    from engine.entities.effects import aura_defense_damage_malus_from_units
    e = _effect(HBD.HuntersBeyondDeathEffect)
    # regime : Tjark EST le defenseur -> l'agregateur ne lui presente aucun carrier.
    assert aura_defense_damage_malus_from_units([], _aura_ctx(tgt_team=0)) == []
    # la patte SELF, elle, repond.
    assert e.create_effect_damage_malus_for_defense(attacker_ctx=_self_ctx()) is not None


def test_mutation_rarete_ignoree_MORD():
    """Mutant : multiplicateur 100 au lieu de 180. Les DEUX variables etant dans
    `variablesAffectedByRarityBonus`, l'ecart est reel des deux cotes."""
    base = ability_var(_ABILITY, "dmgReduction", _LVL, multiplier_pct=100)
    scale = ability_var(_ABILITY, "dmgReduction", _LVL, multiplier_pct=_MULT)
    assert base != scale and int(scale) == _malus()


def test_mutation_variable_croisee_NE_MORD_PAS():
    """AVEU MESURE, ecrit comme un resultat : echanger `extraDmg` et `dmgReduction` ne change
    AUCUN chiffre -- les deux tableaux du gameconfig sont IDENTIQUES (65 valeurs, 8..582). Aucun
    levier numerique ne separe les deux faces ; ce qui les separe est leur GATE et leur CANAL,
    gardes ci-dessus. Ecrire cette non-morsure evite un faux vert : un test de magnitude seul
    aurait ete inerte sur cette confusion."""
    a = ability_var(_ABILITY, "extraDmg", _LVL, multiplier_pct=_MULT)
    b = ability_var(_ABILITY, "dmgReduction", _LVL, multiplier_pct=_MULT)
    assert a == b                       # la mutation est INVISIBLE en valeur -- c'est le resultat
    # ... et ce qui la rend visible est la STRUCTURE : canaux et gates DIFFERENTS.
    e_atk = _effect(HBD.HuntersBeyondDeathExtraDamageEffect)
    e_def = _effect(HBD.HuntersBeyondDeathEffect)
    assert e_atk.create_effect_damage_bonus_for_attack(
        target_traits=frozenset({"Psyker"})).kind != \
        e_def.create_effect_damage_malus_for_defense(attacker_ctx=_self_ctx()).kind
