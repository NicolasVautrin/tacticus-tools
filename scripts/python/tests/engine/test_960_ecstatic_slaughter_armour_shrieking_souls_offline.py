"""#960 -- GARDE OFFLINE des deux passifs Emperor's Children portes par la tranche :
`EcstaticSlaughter` (`emperFlawlessBlade`) et `ArmourOfShriekingSouls` (`emperLucius`).

Ce fichier ne monte AUCUN runner. Il fige ce que le bloc `methodPointers` et le desassemblage ont
LU, et qu'aucun live ne re-etablit seul :

  [1] REGISTRES -- les DEUX branches de l'`op_BitwiseOr` d'`EcstaticSlaughter` dans
      `ABILITY_TRIGGERS` (une classe par event, le dispatch etant indexe par `event_id`),
      l'ability d'`ArmourOfShriekingSouls` dans `ABILITY_TRIGGERS` et ses TROIS autres faces dans
      `EFFECT_TRIGGERS[1423]`. Se tromper de registre donne un passif qui ne se pose jamais.
  [2] LE VECTEUR `On(0x3e = EffectAdded)` -- il N'EXISTAIT PAS avant cette tranche. La branche 1
      d'`EcstaticSlaughter` est branchee dessus : sans emetteur elle serait REGISTERED-BUT-DEAD, et
      rien ne rougirait. On garde donc les DEUX bouts (le vecteur existe ; `AddEffectOperation`
      l'emet) -- c'est le seul cran qui distingue << porte >> de << inscrit >>.
  [3] LITTERAUX -- tous les membres d'enum que le decompile nomme, ET la preuve que l'ORDINAL ne
      discrimine pas : `ThrillSeekers` vaut 1434 en `EffectType` et 1444 en `TriggeredAbilityType`,
      et c'est la SIGNATURE de la surcharge d'`AbilityOrEffect$$op_Implicit` qui tranche.
  [4] LES EVENTS -- un `event_id` faux est silencieux (le trigger n'est jamais collecte).
  [5] L'INVERSION des deux `Resurrect` d'`ArmourOfShriekingSouls` : le `CreateBehaviour` de
      l'ability ressuscite l'OWNER sur les tuiles de l'ACTOR, le `Triggered()` de l'effet
      ressuscite la SOURCE sur les tuiles de l'OWNER. Recopier l'un sur l'autre ferait revenir la
      mauvaise unite au mauvais endroit.
  [6] LE NOEUD `DirectDamage` -- il route `AttackDamageOperation.execute_direct`
      (`IdunBattle.Operations.DirectDamageOperation`), PAS `execute_ability_attack` : les deux
      pipelines different (block / bouclier / cap Resilient).
  [7] CONTRE-EPREUVE PAR MUTATION -- chaque mutant mord sur SON bras, et le temoin est
      assertionne NON DEGENERE avant de conclure.

ASCII only."""
from __future__ import annotations

import pytest

#: #486-r15 -- perimetre = exactement les foyers que ce fichier lit (aucun runner ; le gameconfig
#: du build est lu pour les constantes/variables -> `build: True`).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/engine/runner/operations/triggers/loki/ecstatic_slaughter.py",
        "scripts/python/engine/runner/operations/triggers/loki/armour_of_shrieking_souls.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/move_death.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/turn.py",
        "scripts/python/engine/runner/operations/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/__init__.py",
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        "scripts/python/gameconfig.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Offline : fige les registres des deux passifs, l'EXISTENCE de l'emetteur "
              "On(EffectAdded=0x3e) sans lequel une branche entiere serait registered-but-dead, "
              "les litteraux d'enum lus au desassemblage (dont la confusion 1434/1444 que "
              "l'ordinal ne signale pas), et l'INVERSION des deux Resurrect. Lit le gameconfig du "
              "build pour nrOfHits / nrOfRounds / damageProfile / minHp / maxHp / hp.",
}

import inspect                                                             # noqa: E402

import gameconfig as GC                                                    # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                 # noqa: E402
from engine.entities.ability_constant_type import AbilityConstantType      # noqa: E402
from engine.entities.ability_variable_type import AbilityVariableType      # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.effects.magnitude import ability_var                  # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                    # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType    # noqa: E402
from engine.runner.abilities.behaviours import combat as CB                # noqa: E402
from engine.runner.operations import effects as EFFECT_OPS                 # noqa: E402
from engine.runner.operations.triggers.dispatch import move_death as MD    # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import (          # noqa: E402
    ABILITY_TRIGGERS, EFFECT_TRIGGERS)
from engine.runner.operations.triggers.loki import (                       # noqa: E402
    armour_of_shrieking_souls as ASS, ecstatic_slaughter as ES)


# --------------------------------------------------------------------- [1] REGISTRES
def test_ecstatic_slaughter_deux_branches_au_registre():
    """`EcstaticSlaughterAbility$$CreateTrigger` est un `op_BitwiseOr` de DEUX branches sur DEUX
    events differents ; le dispatch du port etant indexe par `event_id`, il FAUT deux classes."""
    entrees = ABILITY_TRIGGERS.get("EcstaticSlaughter")
    assert entrees is not None, "EcstaticSlaughter absent d'ABILITY_TRIGGERS -> passif MORT"
    assert set(entrees) == {ES.EcstaticSlaughterOnThrilledAbility,
                            ES.EcstaticSlaughterOnOverkillAbility}
    # Le `CreateBehaviour` natif est UNIQUE : les deux classes partagent le meme corps.
    assert (ES.EcstaticSlaughterOnThrilledAbility.execute_behaviour
            is ES.EcstaticSlaughterOnOverkillAbility.execute_behaviour)


def test_armour_of_shrieking_souls_ability_et_effet_dans_deux_registres():
    """UNE face au registre d'ABILITY (`OnDeathEvent`), TROIS au registre d'EFFET -- ce sont deux
    classes natives distinctes (`...Ability` : `BaseTriggeredAbility` ; `...Effect` : `BaseEffect`),
    donc deux canaux de collecte."""
    assert ABILITY_TRIGGERS.get("ArmourOfShriekingSouls") == [
        ASS.ArmourOfShriekingSoulsOnDeathAbility]
    assert EFFECT_TRIGGERS.get(int(EffectType.ArmourOfShriekingSouls)) == [
        ASS.ArmourOfShriekingSoulsDrainOnTurnStart,
        ASS.ArmourOfShriekingSoulsResurrectOnRemoved,
        ASS.ArmourOfShriekingSoulsRemoveOnSourceResurrected]


# --------------------------------------------------- [2] L'EMETTEUR On(EffectAdded), le cran vital
def test_vecteur_effect_added_existe_et_est_emis_par_add_effect_operation():
    """`On(0x3e = EffectAdded)` n'avait AUCUN emetteur cote port : `TerminatorArmourActivateOnEffect
    Added` y etait inscrit depuis toujours, sans qu'aucun vecteur ne le publie. La branche 1
    d'`EcstaticSlaughter` en depend -- sans lui elle est registered-but-DEAD, ce qu'aucun test
    d'appartenance au registre ne voit.

    On garde les DEUX bouts : (a) le vecteur existe et vise le bon event ; (b) le corps d'
    `AddEffectOperation.execute` l'appelle, APRES `add_effect` (place du natif :
    `AddEffectOperation$$Execute+0xd0b`, apres `AddNewEffect` en +0xc4e)."""
    assert hasattr(MD, "effect_added_triggers"), "vecteur On(0x3e) absent"
    src = inspect.getsource(MD.effect_added_triggers)
    assert "EventTriggerType.EffectAdded" in src
    assert "removing=False" in src, "la POSE ecrit les DEUX canaux d'ability (#306)"
    corps = inspect.getsource(EFFECT_OPS.AddEffectOperation.execute)
    assert "\n        effect_added_triggers(" in corps, "AddEffectOperation n'emet pas On(0x3e)"
    # ORDRE : l'emission suit la materialisation (`state.effects.add_effect`), elle ne la precede
    # pas -- c'est ce qui distingue 0x3e de son jumeau 0x3d (<< would have >>). ⚠ le `pre_`
    # CONTIENT le nom du second : on ancre sur le debut de ligne, sinon le test compare le
    # pre-add a lui-meme et passe pour de mauvaises raisons.
    assert (corps.index("state.effects.add_effect(target, eff)")
            < corps.index("\n        effect_added_triggers("))
    assert (corps.index("\n        pre_effect_added_triggers(")
            < corps.index("state.effects.add_effect(target, eff)"))


# --------------------------------------------------------------------- [3] LITTERAUX
def test_litteraux_ecstatic_slaughter():
    assert ES.ECSTATIC_SLAUGHTER == int(TriggeredAbilityType.EcstaticSlaughter) == 1472
    assert ES.THRILLED == int(EffectType.ThrillSeekers) == 1434
    assert ES.TAUNT_EFFECT == int(EffectType.Taunted_OnlySpecificTargets) == 27
    consts = (GC.ability("EcstaticSlaughter") or {}).get("constants") or {}
    assert consts.get("damageProfile") == "Eviscerate"
    assert int(consts.get(AbilityConstantType.nrOfHits.name)) == 3
    assert int(consts.get(AbilityConstantType.nrOfRounds.name)) == 1


def test_ordinal_ne_discrimine_pas_thrillseekers():
    """`CurrentAbilityIs(AbilityOrEffect(0x59a))` -- la surcharge appelee est celle qui prend un
    `EffectType`. `ThrillSeekers` existe dans les DEUX enums a des ordinaux DIFFERENTS : lire 1444
    (le `TriggeredAbilityType`) aurait cable le gate sur un id que le vecteur ne publie JAMAIS, sans
    la moindre erreur. Le NOM est le seul canal ou la faute est visible."""
    assert int(EffectType.ThrillSeekers) != int(TriggeredAbilityType.ThrillSeekers)
    assert int(TriggeredAbilityType.ThrillSeekers) == 1444
    assert ES.THRILLED == int(EffectType.ThrillSeekers)


def test_litteraux_armour_of_shrieking_souls():
    assert ASS.ARMOUR_ABILITY == int(TriggeredAbilityType.ArmourOfShriekingSouls) == 1432
    assert ASS.ELATED_EFFECT == int(EffectType.ArmourOfShriekingSouls) == 1423
    assert ASS.RESURRECT_HEAL_TYPE == 2            # 4e argument LU du `Resurrect` natif
    # `ConfigVar(0x25)` / `ConfigVar(0x95)` / `ConfigVar(0x1d)` -- ordinaux LUS au desassemblage.
    assert int(AbilityVariableType.minHp) == 0x25
    assert int(AbilityVariableType.maxHp) == 0x95
    assert int(AbilityVariableType.hp) == 0x1d
    for cle in (AbilityVariableType.minHp.name, AbilityVariableType.maxHp.name,
                AbilityVariableType.hp.name):
        assert (GC.ability("ArmourOfShriekingSouls") or {}).get("variables", {}).get(cle)
        assert ability_var("ArmourOfShriekingSouls", cle, 50)


# --------------------------------------------------------------------- [4] LES EVENTS
def test_events_des_cinq_faces():
    """Un `event_id` faux est SILENCIEUX : le trigger n'est jamais collecte, aucune erreur."""
    assert ES.EcstaticSlaughterOnThrilledAbility.event_id == int(EventTriggerType.EffectAdded) == 62
    assert ES.EcstaticSlaughterOnOverkillAbility.event_id == int(EventTriggerType.UnitDeath) == 0
    assert ASS.ArmourOfShriekingSoulsOnDeathAbility.event_id == int(EventTriggerType.UnitDeath)
    assert (ASS.ArmourOfShriekingSoulsDrainOnTurnStart.event_id
            == int(EventTriggerType.TurnStart_Actions) == 22)
    assert (ASS.ArmourOfShriekingSoulsResurrectOnRemoved.event_id
            == int(EventTriggerType.UnitRemoved) == 37)
    assert (ASS.ArmourOfShriekingSoulsRemoveOnSourceResurrected.event_id
            == int(EventTriggerType.UnitResurrected) == 46)


def test_fire_on_death_sur_les_deux_faces_dont_l_owner_est_mort():
    """`get_OwnerIsTarget` sur `On(UnitDeath)` / `IsDead(Owner)` sur `On(UnitRemoved)` : le porteur
    est MORT au dispatch. Sans `fire_on_death`, `CanGetAbilityTrigger` ecarte le trigger et le
    passif ne fire JAMAIS."""
    assert ASS.ArmourOfShriekingSoulsOnDeathAbility.fire_on_death is True
    assert ASS.ArmourOfShriekingSoulsResurrectOnRemoved.fire_on_death is True
    # Les faces dont le porteur est VIVANT ne le posent PAS (le gate de vivacite est le mirror
    # d'`ownerNeedsToBeAlive: true`).
    assert getattr(ASS.ArmourOfShriekingSoulsDrainOnTurnStart, "fire_on_death", False) is False
    assert getattr(ES.EcstaticSlaughterOnThrilledAbility, "fire_on_death", False) is False


# --------------------------------------------------------------------- [5] L'INVERSION
def test_les_deux_resurrect_sont_inverses():
    """`Ability$$CreateBehaviour` : `Resurrect(resurrectTarget = Owner, targetTiles = Tiles(Actor))`
    -- Lucius revient sur l'hex du TUEUR (mort simultanee).
    `Effect$$CreateHandleTriggerAbilitiesInternal` (1) : `Resurrect(resurrectTarget =
    EffectSource(Effect), targetTiles = Tiles(Owner))` -- Lucius revient sur l'hex de SA VICTIME.

    Les deux appellent la MEME fonction statique `$$Resurrect` avec les arguments ECHANGES. Le port
    passe donc `(qui, ou)` explicitement a chaque call-site, et ce test fige l'ordre lu."""
    sig = inspect.signature(ASS.armour_resurrect_tree)
    assert list(sig.parameters)[:2] == ["resurrect_target_id", "tiles_of_id"]
    face_ability = inspect.getsource(ASS.ArmourOfShriekingSoulsOnDeathAbility.execute_behaviour)
    assert "armour_resurrect_tree(int(self.owner_id), killer," in face_ability
    face_effet = inspect.getsource(ASS.ArmourOfShriekingSoulsResurrectOnRemoved.execute_behaviour)
    assert "armour_resurrect_tree(src, int(self.owner_id)," in face_effet


# --------------------------------------------------------------------- [6] LE NOEUD DirectDamage
def test_direct_damage_route_l_operation_directe():
    """`IdunBattleLogic.Entities.DSLBehaviors$$DirectDamage` construit un
    `IdunBattle.Operations.DirectDamageOperation` (slot 0x40 de l'`IOperationProcessor`), PAS un
    `AbilityDamageOperation` : les pipelines different (block / bouclier / cap Resilient). La
    feuille doit donc router `execute_direct`, et son profil est ABSENT de la signature native."""
    src = inspect.getsource(CB.DirectDamage)
    assert "execute_direct(" in src
    assert "execute_ability_attack(" not in src
    params = inspect.signature(CB.DirectDamage.__init__).parameters
    assert params["profile"].default is None, "la factory native ne prend AUCUN damageProfile"
    # Le call-site du DoT ne passe donc pas de profil.
    dot = inspect.getsource(ASS.ArmourOfShriekingSoulsDrainOnTurnStart.execute_behaviour)
    assert "profile=" not in dot


def test_sort_units_by_damage_utility_accepte_la_plage():
    """`BaseTriggeredAbility$$MinMaxDamage` est une PLAGE, la ou `NormalAttackDamage(Owner)` est un
    scalaire. Le noeud du port devait apprendre le couple ; le dedoublement scalaire reste le
    comportement des call-sites anterieurs (aucun ne rend de tuple)."""
    from engine.entities.selectors.units import SortUnitsByDamageUtility
    src = inspect.getsource(SortUnitsByDamageUtility.select)
    assert "isinstance(dmg, tuple)" in src
    # Le noeud `_MinMaxDamage` de la tranche rend bien un COUPLE, et (0, 0) sans ECS -- il ne
    # fabrique aucune borne.
    assert ES._MinMaxDamage(None, 1, "Eviscerate").evaluate(None) == (0, 0)


# --------------------------------------------------------------------- [7] CONTRE-EPREUVE
_MUTANTS = (
    # (nom, ce qu'on casse, ce qui doit rougir)
    ("id de ThrillSeekers pris dans le mauvais enum", 1444, "THRILLED"),
    ("id de l'effet Elated", 1424, "ELATED_EFFECT"),
)


@pytest.mark.parametrize("libelle,valeur,attribut", _MUTANTS)
def test_mutation_mord(libelle, valeur, attribut):
    """Chaque mutation mord sur SON bras. Le TEMOIN est assertionne NON DEGENERE d'abord : un
    littéral qui vaudrait deja la valeur mutee rendrait le mutant MUET, et un mutant muet se lit
    comme un vert (#957)."""
    mod = ES if attribut == "THRILLED" else ASS
    avant = getattr(mod, attribut)
    assert avant != valeur, f"temoin DEGENERE : {attribut} vaut deja {valeur}"
    setattr(mod, attribut, valeur)
    try:
        with pytest.raises(AssertionError):
            if attribut == "THRILLED":
                test_ordinal_ne_discrimine_pas_thrillseekers()
            else:
                test_litteraux_armour_of_shrieking_souls()
    finally:
        setattr(mod, attribut, avant)
