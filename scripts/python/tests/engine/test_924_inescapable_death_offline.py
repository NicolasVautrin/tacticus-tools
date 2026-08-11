"""#924 -- `InescapableDeath` (passif de `necroDestroyer`), les gardes OFFLINE.

Ce fichier fige ce que le DECOMPILE dit et que rien d'autre ne garde :

  1. les TROIS faces sont cablees (init owner / 2 `Triggered()` heritees / face DEGAT) ;
  2. le gate de la face DEGAT est `TriggeringAbilityIs(EffectType 1009)` et RIEN d'autre --
     en particulier PAS de gate `IsRangedAttack`, que l'i2 anglais suggere pourtant ;
  3. les points ou `InescapableDeathEffect` (1018) DIVERGE de sa soeur de forme
     `EarlyWarningOverride_ReactivateOverwatchEffect` (1145). C'est le coeur : les deux classes
     derivent de la MEME base native, et recopier l'une pour l'autre donne un port FAUX ;
  4. les ordinaux MESURES au portage (un mirror regenere apres renumerotage rendrait `probe_313`
     vert alors que la valeur ECRITE au site aurait change).

Tout est offline : aucun runner, aucun RPC.
"""
from __future__ import annotations

import pytest

from engine.entities.ability_variable_type import AbilityVariableType
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES
from engine.entities.effects.loki.inescapable_death import InescapableDeathEffect
from engine.entities.effects.magnitude import ability_var
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
from engine.runner.operations.triggers.loki.reactivate_overwatch import (
    AReactivateOverwatch, EarlyWarningOverrideReactivateOverwatch,
    EarlyWarningOverrideHitReductionPurge, InescapableDeathHitReductionPurge,
    InescapableDeathReactivateOverwatch, _hit_reduction_value,
)

ABILITY = "InescapableDeath"

DECLENCHEUR = {
    "chemins": (
        # Le module porteur de la RE et de la classe d'effet -- c'est LUI que le cliquet inverse
        # de #924-r2 surveille (re-armement de la face DEGAT).
        "scripts/python/engine/entities/effects/loki/inescapable_death.py",
        # Les deux `Triggered()` heritees et leur base factorisee : les etages 4 (divergence
        # d'avec 1145) lisent directement ces classes.
        "scripts/python/engine/runner/operations/triggers/loki/reactivate_overwatch.py",
        # Les TROIS registres ou les faces sont cablees.
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        # L'etape 1 du fix #924-r2 : ce fichier assertionne que `trigger_ability_type` n'est PAS
        # encore threade sur l'axe DEGAT. Le threader DOIT faire rougir ce test.
        "scripts/python/engine/runner/operations/damage_ops/normal.py",
        # Les mirrors d'enum dont les ordinaux sont figes a l'etage 1, et la magnitude lue.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/gameconfig.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Fige les ordinaux MESURES au portage (`probe_313` compare le mirror au build et "
              "redevient vert des qu'on le regenere -- il ne voit pas la valeur ECRITE au site), "
              "la divergence structurelle d'avec la soeur de forme 1145 (`LegitDeathReasons` : un "
              "terme ici, deux la-bas), et le cliquet INVERSE de #924-r2 qui garde la face DEGAT "
              "desarmee tant que son etage d'injection n'est pas traite.",
}


# --------------------------------------------------------------- 1. les ORDINAUX, figes au portage

def test_924_ordinaux_mesures_au_portage():
    """Les valeurs LUES au decompile, figees au site. `probe_313` compare le MIRROR au BUILD et
    redevient vert des qu'on regenere le mirror ; il ne voit pas qu'un ordinal ECRIT ici a change.

    Sources : `InescapableDeathAbility$$GetEffectType` = `return 0x3fa` ;
    `InescapableDeathEffect$$GetHitReductionEffectType` = `return 0x3fb` ;
    `InescapableDeathEffect$$.ctor` = `AReactivateOverwatchEffect..ctor(this, 0x3ed)` ;
    `IsOverwatchAttack()` -> immediat `0x3f1` lu AUX OCTETS (`mov edx,0x3f1`) ;
    `GetOverwatchExtraDamage` = `ConfigVar(..., 8, ...)`."""
    assert int(EffectType.InescapableDeath_Effect) == 0x3fa == 1018
    assert int(EffectType.InescapableDeath_HitsReduction) == 0x3fb == 1019
    assert int(TriggeredAbilityType.InescapableDeath) == 0x3ed == 1005
    assert int(EffectType.Overwatch_AutoAttack) == 0x3f1 == 1009
    assert int(AbilityVariableType.extraDmg) == 8


def test_924_le_1009_du_gate_est_un_EffectType_pas_un_ActiveAbilityType():
    """Qualification d'enum. La surcharge `AbilityOrEffect$$op_Implicit` appelee par
    `IsOverwatchAttack()` est celle dont le corps est `set_Effect` -- donc un
    `AbilityOrEffect{Effect = 1009}`. L'ordinal 1009 est AUSSI un membre d'`ActiveAbilityType`
    (`ResurrectionOrb`) et de `TriggeredAbilityType` (`WhipcoilBody`), qui n'ont rien a voir.

    Ce test assertionne son propre NON-VIDE : si les homonymes disparaissaient du build, un test
    qui se contente de comparer des ordinaux passerait pour vert sans rien mesurer."""
    homonymes = {}
    for enum, nom in ((ActiveAbilityType, "ActiveAbilityType"),
                      (TriggeredAbilityType, "TriggeredAbilityType")):
        m = next((x for x in enum if int(x) == 1009), None)
        if m is not None:
            homonymes[nom] = m.name
    assert homonymes, ("aucun homonyme de 1009 trouve -- ce test ne mesure plus rien "
                       "(le build a change : re-deriver la qualification)")
    for nom, membre in homonymes.items():
        assert membre != EffectType.Overwatch_AutoAttack.name, \
            f"{nom}.{membre} porte 1009 mais nomme autre chose que l'EffectType attendu"


# --------------------------------------------------------------- 2. les TROIS faces sont cablees

def test_924_face_init_owner():
    """`AOwnerEffectTriggeredAbility$$CreateTrigger` = `OnOwnerSpecificAbilityInit(this@0x10)` et
    `$$CreateBehaviour` = `If(cond, AddEffect(GetEffectType(), ..., owner, owner))` -> l'effet 1018
    est pose sur le PORTEUR a l'init de son ability."""
    assert ABILITY_INIT_OWNER_EFFECTS.get(ABILITY) == [EffectType.InescapableDeath_Effect.name]


def test_924_face_degat_est_une_classe_deffet():
    assert EFFECT_CLASSES.get(EffectType.InescapableDeath_Effect.name) is InescapableDeathEffect


def test_924_face_triggers_deux_entrees_sur_leffet_porteur():
    """`CreateHandleTriggerAbilitiesInternal` rend un `ArraySet` de DEUX `Triggered()`, tous deux
    enregistres sur l'effet PORTEUR (1018), pas sur l'effet de reduction (1019)."""
    entrees = EFFECT_TRIGGERS.get(int(EffectType.InescapableDeath_Effect)) or []
    assert [c.__name__ for c in entrees] == ["InescapableDeathReactivateOverwatch",
                                             "InescapableDeathHitReductionPurge"]
    assert int(EffectType.InescapableDeath_HitsReduction) not in EFFECT_TRIGGERS, \
        "1019 est l'effet POSE, pas le porteur du trigger -- l'enregistrer la serait un contresens"


# --------------------------------------------------------------- 3. le gate de la face DEGAT

def _effet(level: int = 50, mult: int = 100) -> InescapableDeathEffect:
    """⚠ `BaseEffect.__init__` prend `name: str` en PREMIER, pas le dict capte (c'est
    `EffectFactory.create` qui traduit le dict). Passer le dict << marche >> silencieusement --
    `ability_variables_multiplier` reste alors a son defaut 100 et le volet SCALING du test
    ci-dessous devient inerte. Construire par mots-cles est ce qui rend le pilotage verifiable."""
    return InescapableDeathEffect(
        name=EffectType.InescapableDeath_Effect.name,
        effect_type=int(EffectType.InescapableDeath_Effect),
        level=level, ability_level=level, ability_variables_multiplier=mult)


def test_924_le_pilotage_du_test_mord_vraiment():
    """Contre-epreuve du helper ci-dessus : sans elle, un `_effet(mult=180)` qui n'aurait pas
    transmis le multiplicateur rendrait la valeur de base et le test de scaling passerait pour
    vert en ne mesurant rien."""
    assert _effet(mult=180).ability_variables_multiplier == 180
    assert _effet().ability_variables_multiplier == 100
    assert _effet(level=7).ability_level == 7


def test_924_r2_la_face_degat_reste_DESARMEE_tant_que_letage_nest_pas_traite():
    """CLIQUET INVERSE (#924-r2). La face DEGAT est RE-solue (gate + magnitude etablis) et le natif
    l'applique bel et bien -- mesure live, meme run, meme cible, armure 0 :

        attaque NORMALE  moyenne  628,7 / coup
        tir  OVERWATCH   moyenne 1246,0 / coup      (1,98x)

    Mais l'ecart que le PORT produirait vaut 898,0/coup EXACTEMENT (mesure par mutant), quand le
    natif en produit 617,3. `617,3/898 = 0,687`, et le rapport `degat normal / stat Attack` vaut
    `628,7/906 = 0,694` -- MESURE INDEPENDAMMENT : le bonus subit la meme transformation que la
    base, donc le natif l'ajoute AVANT la resolution des bornes et le port APRES. Livrer a cet
    etage-la, c'est +45 % de degat sur chaque tir d'overwatch d'Imospekh.

    Ce test rougit si quelqu'un re-arme la face sans traiter l'etage. Le lever demande de MESURER
    a nouveau le couple (normale, overwatch), pas de supprimer ce test."""
    assert "create_effect_damage_bonus_for_attack" not in InescapableDeathEffect.__dict__, \
        ("la face DEGAT a ete re-armee. Si l'etage d'injection a ete corrige (#924-r2), remplace ce "
         "cliquet par la confrontation live du couple (attaque normale, tir d'overwatch) -- ne le "
         "supprime pas sans cette mesure.")
    e = _effet()
    assert e.create_effect_damage_bonus_for_attack(att_ctx={"trigger_ability_type": 1009}) is None


def test_924_r2_la_magnitude_reste_LISIBLE_pour_le_futur_fix():
    """La RE ne se perd pas parce que la face est desarmee : le montant natif reste derivable du
    gameconfig, et c'est lui que le fix devra injecter au bon etage.

    `GetOverwatchExtraDamage` = `ConfigVar(AbilityVariableType.extraDmg)`, et `extraDmg` est dans
    `variablesAffectedByRarityBonus` -> scale par le multiplicateur de rarete de l'unite."""
    base = ability_var(ABILITY, AbilityVariableType.extraDmg.name, 50)
    scale = ability_var(ABILITY, AbilityVariableType.extraDmg.name, 50, multiplier_pct=180)
    assert base == 499 and scale == 898, (base, scale)


def test_924_le_trigger_ability_type_nest_PAS_threade_sur_laxe_DEGAT():
    """Etat MESURE du substrat, et premiere etape du fix #924-r2. Le vecteur ATTAQUE NORMALE ne
    passe pas `trigger_ability_type` a `attacker_modifiers` -- seul l'axe COUPS le recoit
    (`build_hits_board`, consomme par `PurgeResponse`). Un futur fix devra le threader ; ce test
    documente qu'il ne l'est pas encore, pour qu'on ne croie pas le substrat deja pret."""
    import inspect
    from engine.runner.operations.damage_ops import normal as N
    src = inspect.getsource(N)
    i = src.find("mods, active = attacker_modifiers(")
    assert i > 0, "site d'appel introuvable -- ce test ne mesure plus rien"
    appel = src[i:i + 900]
    assert "trigger_ability_type=" not in appel, \
        ("`trigger_ability_type` est desormais threade sur l'axe DEGAT : c'est l'etape 1 de "
         "#924-r2 -- reprends la confrontation live de la face DEGAT et mets ce test a jour")


# ------------------------------------------- 4. la DIVERGENCE d'avec le voisin de forme (1145)

def test_924_legit_death_reasons_un_seul_terme_contre_deux_pour_1145():
    """LE point ou recopier le voisin donne un port FAUX.

    `EarlyWarningOverride_ReactivateOverwatchEffect$$LegitDeathReasons` est un OVERRIDE a DEUX
    termes (`1009 | 1148 CyclicIonBlaster_AdditionalHits`). `InescapableDeathEffect`, lui, ne
    surcharge PAS ce slot -- ses entrees `methodPointers` sont `.ctor`,
    `GetHitReductionEffectType`, `GetOverwatchExtraDamage` et `GetAdditionalExtraDamageTrigger`,
    et aucune n'adresse `LegitDeathReasons`. Il prend donc le corps de la BASE : UN terme.

    On le verifie STRUCTURELLEMENT (qui possede la methode), pas par une mort simulee : c'est la
    propriete que le decompile etablit."""
    assert "_legit_death_reasons" in EarlyWarningOverrideReactivateOverwatch.__dict__, \
        "1145 DOIT surcharger LegitDeathReasons (2 termes)"
    assert "_legit_death_reasons" not in InescapableDeathReactivateOverwatch.__dict__, \
        ("1018 ne surcharge PAS LegitDeathReasons -- lui donner les 2 termes de 1145 re-armerait "
         "l'overwatch sur des morts que le natif refuse ici")
    assert InescapableDeathReactivateOverwatch._legit_death_reasons \
        is AReactivateOverwatch._legit_death_reasons


def test_924_les_deux_sous_classes_ne_partagent_aucune_valeur_specialisee():
    """Les trois points de variation de la base, cote a cote. Un copier-coller qui aurait laisse
    une valeur de 1145 dans 1018 (ou l'inverse) rougit ici."""
    ID_, EWO = InescapableDeathReactivateOverwatch, EarlyWarningOverrideReactivateOverwatch
    assert (ID_.effect_type, ID_.HIT_REDUCTION_EFFECT_TYPE, ID_.SOURCE_ABILITY) == (1018, 1019, ABILITY)
    assert (EWO.effect_type, EWO.HIT_REDUCTION_EFFECT_TYPE, EWO.SOURCE_ABILITY) == \
        (1145, 1146, "EarlyWarningOverride")
    for champ in ("effect_type", "HIT_REDUCTION_EFFECT_TYPE", "SOURCE_ABILITY", "HIT_REDUCTION_NAME"):
        assert getattr(ID_, champ) != getattr(EWO, champ), champ
    # meme separation sur la PURGE (Triggered #2)
    assert InescapableDeathHitReductionPurge.HIT_REDUCTION_EFFECT_TYPE == 1019
    assert EarlyWarningOverrideHitReductionPurge.HIT_REDUCTION_EFFECT_TYPE == 1146


def test_924_hit_reduction_value_lit_la_config_de_SA_propre_ability():
    """`HitReductionValue()` = `Direct(GetNumberConstant(config@0x60, 0x2c))`, ou `config@0x60` est
    la config de l'ability passee au `.ctor` -- `InescapableDeath` ici, `EarlyWarningOverride` la.
    Les deux valent 1 aujourd'hui : le test verifie donc la SOURCE (que la lecture est bien
    parametree), pas la coincidence de valeur."""
    assert _hit_reduction_value(ABILITY) == 1
    assert _hit_reduction_value("EarlyWarningOverride") == 1
    with pytest.raises(Exception):
        _hit_reduction_value()          # plus de defaut : la source est OBLIGATOIRE
