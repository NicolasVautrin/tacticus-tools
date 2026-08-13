"""#1005 -- GARDE OFFLINE du couple de reliques BLOOD ANGELS : `ChaliceOfBaal` (1550,
`bloodSanguinary`) et `Vitarus` (1470, `bloodMephiston`).

DECLENCHEUR : ce fichier est joue par toute passe qui touche l'un des foyers ci-dessous.
    scripts/python/engine/runner/operations/triggers/loki/chalice_of_baal.py
    scripts/python/engine/runner/operations/triggers/loki/vitarus.py
    scripts/python/engine/entities/effects/loki/extra_damage.py
    scripts/python/engine/entities/effects/base.py
    scripts/python/engine/entities/effects/factory.py
    scripts/python/engine/runner/operations/spawn.py
    scripts/python/engine/runner/damage_model.py
    scripts/python/engine/runner/abilities/behaviours/effects.py
    scripts/python/engine/runner/operations/triggers/dispatch/registry.py

CE QUE CHAQUE ETAGE GARDE (et pourquoi il rougirait) :

  1. INSCRIPTION AUX DEUX REGISTRES. La mesure des relique-triggers dit qu'il en faut DEUX :
     l'ABILITY dans `RELIC_ABILITY_TRIGGERS` **et** l'EFFET dans `EFFECT_CLASSES`. L'effet seul =
     une ability qui ne se declenche jamais ; l'ability seule = un `BaseEffect` nu qui n'agit pas.
  2. `Vitarus_InitAbility` est un OWNER-EFFECT D'INIT, pas un vecteur de combat : il doit vivre
     dans `ABILITY_INIT_OWNER_EFFECTS`, jamais dans `RELIC_ABILITY_TRIGGERS`.
  3. LA VOIE TERTIAIRE DU SEED. Une relique n'est PAS dans le kit gameconfig : sans la lecture de
     `ctx.tertiary_ability`, l'owner-effet de `Vitarus` ne serait JAMAIS pose offline.
  4. LE COUPLE (niveau, multiplicateur) EST CELUI DE LA RELIQUE. MESURE live (`unitAbilityStates`,
     runner 614) : `raw = [1470, .., level = 1, mult = 100, .., hierarchie = 3, ..]` alors que les
     passifs du MEME porteur portent `level = 50, mult = 180`. Lire le couple passif ferait rendre
     `extraDmg[10] = 728` (clamp) au lieu d'`extraDmg[1] = 490` : +238 par coup, en SILENCE.
  5. LES GATES LUS, ET SEULEMENT EUX. `ChaliceOfBaal_ExtraDmg` porte `IsMeleeAttack &
     IsNormalAttack` ; `Vitarus` porte `IsMeleeAttack & (IsNormalAttack | CurrentAbilityIs(1247))`
     **et** « la tuile de la cible est en Feu ». Un gate en trop rend l'effet inerte, un gate en
     moins le rend permissif -- les deux sont muets.
  6. LE FOYER `target_is_on_fire_tile` EST UNIQUE. Il etait ecrit DEUX fois dans
     `extra_damage_aura.py` ; une TROISIEME ecriture pour `Vitarus` aurait fait un fork.
  7. `RemoveEffect` EST TILE-DOMAIN. Le disjoint « on ETEINT » de `VitarusAbility$$CreateBehaviour`
     est `RemoveEffect(Fire, Tiles(Target))` : avant #1005 la feuille ne routait que les UNITES,
     donc ce disjoint etait un NO-OP SILENCIEUX.

ASCII only (cp1252). Aucun runner : tout est offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

#: Le garde `DECLENCHEUR` juge la PRESENCE et la FORME, et il exige un dict de MODULE -- la liste
#: en prose de la docstring ci-dessus ne lui disait rien (ajoute au merge de #1007).
#: Les foyers sont ceux que la tranche edite, repris verbatim de la docstring. `toujours: True`
#: parce que trois d'entre eux sont des foyers PARTAGES (`damage_model`, `spawn`,
#: `effects/base`) : le perimetre etroit n'est pas MESURE ici, et large est sain.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/operations/triggers/loki/chalice_of_baal.py",
        "scripts/python/engine/runner/operations/triggers/loki/vitarus.py",
        "scripts/python/engine/entities/effects/loki/extra_damage.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/spawn.py",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
    ),
    "build": True,
    "toujours": True,
    "raison": "Foyers PARTAGES (damage_model, spawn, effects/base) : perimetre etroit NON MESURE "
              "-- large par honnetete, pas par negligence.",
}

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine.entities.effect_type import EffectType                              # noqa: E402
from engine.entities.effects import base as EBASE                               # noqa: E402
from engine.entities.effects.factory import (ABILITY_INIT_OWNER_EFFECTS,        # noqa: E402
                                             EFFECT_CLASSES)
from engine.entities.effects.loki.extra_damage import (ChaliceOfBaalExtraDmgEffect,  # noqa: E402
                                                       VitarusEffect)
from engine.entities.triggered_ability_type import TriggeredAbilityType         # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                      # noqa: E402
from engine.runner.operations.triggers.dispatch import registry as REG          # noqa: E402
from engine.runner.operations.triggers.loki import chalice_of_baal as CB        # noqa: E402
from engine.runner.operations.triggers.loki import vitarus as VI                # noqa: E402


# --- 1/2 : les DEUX registres, et le bon pour chaque classe native --------------------------------

def test_les_deux_faces_sont_inscrites():
    """L'ABILITY dans `RELIC_ABILITY_TRIGGERS`, l'EFFET dans `EFFECT_CLASSES`. Une seule des deux
    ne suffit pas -- c'est exactement le mode de panne que la mesure des relique-triggers nomme."""
    assert REG.RELIC_ABILITY_TRIGGERS.get("ChaliceOfBaal") == [
        CB.ChaliceOfBaalAbility, CB.ChaliceOfBaalResetAbility]
    assert REG.RELIC_ABILITY_TRIGGERS.get("Vitarus") == [VI.VitarusAbility]
    assert EFFECT_CLASSES.get("ChaliceOfBaal_ExtraDmg") is ChaliceOfBaalExtraDmgEffect
    assert EFFECT_CLASSES.get("Vitarus") is VitarusEffect


def test_vitarus_init_est_un_owner_effect_pas_un_trigger():
    """`Vitarus_InitAbility` (parent `AOwnerEffectTriggeredAbility`, `$$GetEffectType` = `return
    0x5ba`) pose son effet a l'INIT. L'inscrire comme vecteur de combat donnerait un passif qui ne
    se pose JAMAIS ; l'oublier donnerait un effet qui n'existe jamais."""
    assert ABILITY_INIT_OWNER_EFFECTS.get("Vitarus") == ["Vitarus"]
    assert int(EffectType.Vitarus) == 0x5ba == 1466


def test_les_vecteurs_natifs_sont_ceux_du_decompile():
    """`On(0 = UnitDeath)` / `On(0x17 = TurnEnd)` / `On(9 = Attack)` -- lus, pas devines."""
    assert CB.ChaliceOfBaalAbility.event_id == int(EventTriggerType.UnitDeath) == 0
    assert CB.ChaliceOfBaalResetAbility.event_id == int(EventTriggerType.TurnEnd) == 0x17
    assert VI.VitarusAbility.event_id == int(EventTriggerType.Attack) == 9
    assert CB.CHALICE == int(TriggeredAbilityType.ChaliceOfBaal) == 0x60e
    assert VI.VITARUS == int(TriggeredAbilityType.Vitarus) == 0x5be
    assert VI.FURY_OF_THE_ANCIENTS == int(TriggeredAbilityType.FuryOfTheAncients) == 0x4df


# --- 4 : le couple (niveau, multiplicateur) de la RELIQUE, pas celui des passifs ------------------

_TERTIAIRE = {"att_tertiary_ability": "Vitarus", "att_tertiary_level": 1, "att_tertiary_mult": 100}


def test_relic_ability_state_ne_repond_que_pour_SA_relique():
    """Foyer de lecture du couple tertiaire. Une relique DIFFERENTE (ou aucune) -> `(None, None)`,
    jamais un couple devine."""
    assert EBASE.relic_ability_state(_TERTIAIRE, "Vitarus") == (1, 100)
    assert EBASE.relic_ability_state(_TERTIAIRE, "ChaliceOfBaal") == (None, None)
    assert EBASE.relic_ability_state({}, "Vitarus") == (None, None)
    assert EBASE.relic_ability_state(None, "Vitarus") == (None, None)


def test_vitarus_lit_le_niveau_TERTIAIRE_et_pas_le_passif():
    """MESURE live : le porteur monte `Vitarus` a `level = 1, mult = 100` alors que ses passifs
    sont a `50 / 180`. `extraDmg[1] = 490`, `extraDmg[10] = 728` (le clamp du niveau 50). Le test
    FIGE l'ecart : sans la lecture tertiaire, le port sur-applique +238 par coup."""
    ctx = dict(_TERTIAIRE)
    ctx.update({"t_pos": (3, 3), "tile_effects_by_pos": {(3, 3): ["Fire"]}})
    eff = VitarusEffect(name="Vitarus", effect_type=int(EffectType.Vitarus),
                        ability_level=50, ability_variables_multiplier=180)
    b = eff.create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx=ctx)
    assert b is not None and int(b.value) == 490, b
    # contre-epreuve : SANS le canal tertiaire, le port retombe sur le couple passif -> 728.
    sans = {"t_pos": (3, 3), "tile_effects_by_pos": {(3, 3): ["Fire"]}}
    b2 = eff.create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx=sans)
    assert b2 is not None and int(b2.value) == 728, b2


# --- 5/6 : les gates LUS, et le foyer du « la tuile de la cible est en feu » ----------------------

def test_vitarus_les_quatre_gates_mordent():
    """`IsMeleeAttack & (IsNormalAttack | CurrentAbilityIs(1247)) & <tuile de la cible en Feu>`."""
    base = dict(_TERTIAIRE, t_pos=(3, 3), tile_effects_by_pos={(3, 3): ["Fire"]})
    eff = VitarusEffect(name="Vitarus", effect_type=int(EffectType.Vitarus), ability_level=1,
                        ability_variables_multiplier=100)
    assert eff.create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx=base) is not None
    # nature non PROUVEE melee -> gate FERME (tri-etat #106), et distance -> ferme aussi
    assert eff.create_effect_damage_bonus_for_attack(is_ranged=None, att_ctx=base) is None
    assert eff.create_effect_damage_bonus_for_attack(is_ranged=True, att_ctx=base) is None
    # tuile de la cible SANS feu -> pas de bonus
    froid = dict(base, tile_effects_by_pos={(3, 3): []})
    assert eff.create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx=froid) is None
    # une AUTRE ability courante -> hors des deux disjoints
    autre = dict(base, ability_type=1151)          # TheQuickening
    assert eff.create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx=autre) is None
    # `FuryOfTheAncients` -> 2e disjoint, le bonus revient
    fury = dict(base, ability_type=int(TriggeredAbilityType.FuryOfTheAncients))
    assert eff.create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx=fury) is not None


def test_le_gate_tuile_en_feu_a_UN_SEUL_foyer():
    """`APsychicStalkEffect$$GetTargetIsOnFireTileCondition` et le jumeau `1216` DELEGUENT au meme
    foyer que `Vitarus`. Une reecriture locale (le fork qu'on vient de fermer) rougirait ici."""
    from engine.entities.effects.loki import extra_damage_aura as AURA
    src = Path(AURA.__file__).read_text(encoding="utf-8")
    assert src.count("_target_is_on_fire_tile(ctx)") == 2, (
        "les deux lecteurs d'aura doivent DELEGUER au foyer, pas re-deriver la condition")
    assert EBASE.target_is_on_fire_tile({"t_pos": (1, 1),
                                         "tile_effects_by_pos": {(1, 1): ["Fire"]}}) is True
    assert EBASE.target_is_on_fire_tile({"t_pos": (1, 1), "tile_effects_by_pos": {}}) is False
    assert EBASE.target_is_on_fire_tile({}) is False          # canal muet -> RESTRICTIF


def test_chalice_les_trois_gates_mordent():
    """`get_OwnerIsActor & IsMeleeAttack & IsNormalAttack` -- et le `is_prediction` du jumeau
    `SmashaEad`, dont le noeud `IsNormalAttack` evalue FAUX en prediction d'affichage."""
    eff = ChaliceOfBaalExtraDmgEffect(name="ChaliceOfBaal_ExtraDmg",
                                      effect_type=int(EffectType.ChaliceOfBaal_ExtraDmg),
                                      ability_level=1, ability_variables_multiplier=100)
    ctx = {"att_tertiary_ability": "ChaliceOfBaal", "att_tertiary_level": 1,
           "att_tertiary_mult": 100}
    b = eff.create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx=ctx)
    assert b is not None and int(b.value) == 490, b
    assert eff.create_effect_damage_bonus_for_attack(is_ranged=True, att_ctx=ctx) is None
    assert eff.create_effect_damage_bonus_for_attack(is_ranged=None, att_ctx=ctx) is None
    assert eff.create_effect_damage_bonus_for_attack(is_ranged=False, is_normal_attack=False,
                                                     att_ctx=ctx) is None
    assert eff.create_effect_damage_bonus_for_attack(is_ranged=False, is_prediction=True,
                                                     att_ctx=ctx) is None


# --- 7 : `RemoveEffect` tile-domain, et la forme des deux arbres ----------------------------------

def test_l_arbre_vitarus_est_bien_un_If_a_deux_branches():
    """`If(cond, Inform + RemoveEffect(Fire, tiles), AddEffect(Fire, tiles))`, et les selecteurs de
    tuile rendent des IDs (sans quoi `HasEffect` ne route rien et le gate est FAUX en silence)."""
    from engine.entities.behaviours import If, Seq
    tree = VI.vitarus_behaviour_tree()
    assert isinstance(tree, If)
    assert isinstance(tree.then, Seq)              # Inform + RemoveEffect
    assert tree.otherwise is not None              # la branche `else` EXISTE (AddEffect)
    assert tree.otherwise.effect_type == int(EffectType.Fire)
    assert tree.otherwise.duration_rounds is None  # `turns = null` -> duree DEFAUT de l'effet
    assert tree.otherwise.source_from_target is True
    assert VI.target_tile_is_on_fire().unit.as_ids is True
    assert VI.target_tile_is_on_fire().active_only is False


def test_remove_effect_route_le_domaine_TUILE():
    """Avant #1005 la feuille ne resolvait que les UNITES (`isinstance(tu, dict)`) : le disjoint
    « on ETEINT » de `VitarusAbility` etait un no-op muet. Le test lit la resolution d'id."""
    import engine.runner.abilities.behaviours.effects as FX
    assert FX._add_effect_target_id(7, None) == 7            # id de tuile deja resolu
    assert FX._add_effect_target_id({"id": 42}, None) == 42   # unite
    src = Path(FX.__file__).read_text(encoding="utf-8")
    bloc = src.split("class RemoveEffect")[1].split("class ")[0]
    assert "_add_effect_targets(" in bloc and "_add_effect_target_id(" in bloc, (
        "RemoveEffect doit passer par le MEME resolveur qu'AddEffect (cle de pose == cle de retrait)")


def test_l_arbre_chalice_pose_l_effet_UN_TOUR_sur_les_non_mecaniques():
    """`Heal & AddEffect(1569, turns = Direct(1)) & SetPersistentData(<cle>)`, cible =
    `UnitsAffectedByHealType(Owner + AdjacentFriends(Owner, unique, OnlyAliveAndTargetable),
    NonMechanical)`."""
    from engine.entities.selectors.units import UnitsAffectedByHealType, Union, AdjacentFriends
    tree = CB.chalice_behaviour_tree(1765)
    # Seq(Seq(Heal, AddEffect), SetPersistentData)
    heal, add = tree.left.left, tree.left.right
    assert int(heal.amount_fn) == 1765 and heal.scope == 0 and heal.remove_effects is True
    assert add.effect_type == int(EffectType.ChaliceOfBaal_ExtraDmg) == 0x621
    assert add.duration_turns == 1 and add.duration_rounds is None
    assert add.scale_from_source is True
    assert tree.right.ability_or_effect == CB.CHALICE
    assert tree.right.data_key == "ChaliceOfBaalTriggered" and tree.right.value == 1
    sel = CB.chalice_targets()
    assert isinstance(sel, UnitsAffectedByHealType) and sel.heal_type == 0   # NonMechanical
    assert isinstance(sel.source, Union) and isinstance(sel.source.b, AdjacentFriends)
    assert sel.source.b.selection_type == 3                                  # OnlyAliveAndTargetable


def test_le_reset_efface_TOUTES_les_cles_de_la_relique():
    """`ClearAllPersistentData(AbilityOrEffect(ChaliceOfBaal), Owner)` -- corps ICF-partage avec
    `NoHidingFromTheWatchers_EndPhaseAbility$$CreateBehaviour`, donc SANS symbole propre."""
    t = CB.chalice_reset_tree()
    assert t.ability_or_effect == CB.CHALICE


# --- 3 : la voie TERTIAIRE du seed d'owner-effects ------------------------------------------------

def test_le_seed_lit_la_voie_TERTIAIRE_et_son_couple():
    """Une relique n'est PAS dans le kit gameconfig : `_seed_ability_owner_effects` doit lire
    `ctx.tertiary_ability` -- et la materialiser avec le couple TERTIAIRE, pas le passif."""
    import engine.runner.operations.spawn as SP
    src = Path(SP.__file__).read_text(encoding="utf-8")
    bloc = src.split("def _seed_ability_owner_effects")[1].split("\ndef ")[0]
    assert "tertiary_ability" in bloc, "la voie relique n'est pas lue"
    assert "tertiary_ability_level" in bloc and "tertiary_ability_variables_multiplier" in bloc, (
        "le couple (niveau, multiplicateur) de la relique n'est pas celui des passifs -- MESURE")


def test_damage_model_publie_le_couple_tertiaire():
    """Le canal que lit `relic_ability_state`. S'il disparait, les deux effets de relique
    retombent SILENCIEUSEMENT sur le couple passif (+238/coup pour `Vitarus`)."""
    import engine.runner.damage_model as DM
    src = Path(DM.__file__).read_text(encoding="utf-8")
    for cle in ("att_tertiary_ability", "att_tertiary_level", "att_tertiary_mult"):
        assert cle in src, f"cle {cle} absente d'attacker_modifiers"


if __name__ == "__main__":                       # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
