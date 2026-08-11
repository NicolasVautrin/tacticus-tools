"""#931 -- GARDE OFFLINE du port de `TwistedScience` : ce que la RE a LU, fige ici.

Ce fichier ne monte AUCUN runner. Il garde les faits que le decompile a etablis et qu'aucun test
live ne peut re-etablir seul (un live confronte des NOMBRES ; ici on garde des LITTERAUX et une
STRUCTURE) :

  [1] REGISTRES -- `1167` est dans `ABILITY_CLASSES`, avec son masque de ciblage EXACT, son
      `TargetingRange` et son `AbilityAttackType` ; `1355`/`1356` sont dans `EFFECT_CLASSES`.
      C'est la regle de non-regression : une ability entre au registre AVEC ses deux donnees.
  [2] LITTERAUX -- les quatre enums que le decompile nomme (`Heal` 18, `Heal_TwistedScience` 1167,
      `TwistedScience_ExtraHp` 1355, `TwistedScience_ExtraDmg` 1356) et les deux index de variable
      (`hp` 0x1d, `extraDmg` 8). Un renumerotage de build les ferait bouger EN SILENCE.
  [3] STRUCTURE DE L'ARBRE -- la forme de `$$ExecuteBehaviour`, feuille par feuille et DANS SON
      ORDRE : le bloc de buffs est SOUS un `If`, le `Heal` est HORS de ce `If` (donc
      inconditionnel), le stat-mod PRECEDE le `ChangeStat`, et l'`AddEffect(1356)` est sous un
      SECOND `If` (le gate de faction). Un live ne voit que le resultat ; l'ordre et
      l'imbrication, eux, ne se lisent qu'ici.
  [4] L'EFFET 1356 -- gate `OwnerIsCaster` SEUL : il contribue AUSSI en PREDICTION (contraste avec
      ses voisins de module, dont le `if is_prediction: return None` vient d'un `IsNormalAttack`
      que celui-ci n'a PAS).
  [5] L'EFFET 1355 -- il declare `applied_stat_mods`, et c'est ce qui choisit le CHEMIN
      d'application (`_apply_stat_mods` -> `apply_change_stat` -> `HealthComponent.modify_max`).
      Sans lui l'effet est pose mais le plafond de PV ne bouge pas.

ASCII only."""
from __future__ import annotations

#: #486-r15 -- ce fichier lit les registres, les enums, la classe d'ability et les deux classes
#: d'effet. Perimetre = exactement ces foyers (aucun runner, aucun artefact de build hors les
#: enums, que `probe_313` garde par ailleurs contre le build).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/engine/runner/abilities/genestealer.py",
        "scripts/python/engine/runner/abilities/handler.py",
        "scripts/python/engine/runner/abilities/attack_type.py",
        "scripts/python/engine/runner/abilities/targeting.py",
        "scripts/python/engine/runner/abilities/targeting_rule.py",
        "scripts/python/engine/entities/effects/loki/twisted_science.py",
        "scripts/python/engine/entities/effects/loki/extra_damage.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/unit_faction.py",
        "scripts/python/engine/entities/behaviours.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/entities/effects/magnitude.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Offline : fige les LITTERAUX lus au decompile (les quatre membres d'enum, les deux "
              "index de variable, le masque 0x8402, le `TargetingRange` statics+0x00, "
              "`AbilityAttackType.Others`) et la STRUCTURE de l'arbre DSL -- ordre et imbrication "
              "des feuilles, qu'aucun observable live ne separe. Ne lit ni runner ni gameconfig "
              "de build.",
}

from engine.entities.ability_variable_type import AbilityVariableType
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.behaviours import If, Seq
from engine.entities.effect_type import EffectType
from engine.entities.effects.factory import EFFECT_CLASSES
from engine.entities.effects.loki.extra_damage import TwistedScienceExtraDmgEffect
from engine.entities.effects.loki.twisted_science import TwistedScienceExtraHpEffect
from engine.entities.stats import StatType
from engine.entities.triggers import HasEffect, HasFaction, Not, OwnerIsTarget, TriggerAnd
from engine.entities.unit_faction import UnitFaction
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
from engine.runner.abilities.behaviours.effects import AddDynamicStatModifierEffect, AddEffect
from engine.runner.abilities.behaviours.stats import ChangeStat, Heal
from engine.runner.abilities.genestealer import (TwistedScience_HealAbility,
                                                 twisted_science_heal_tree)
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting import (RANGE_ADJACENT_IF_MELEE_CASTER,
                                               RANGED_BOOL_IF_RANGED_CASTER)
from engine.runner.abilities.targeting_rule import TargetingRule as TR

HEAL_TS = int(ActiveAbilityType.Heal_TwistedScience)


# ---------------------------------------------------------------- [2] les litteraux du decompile

def test_les_quatre_membres_d_enum_du_decompile():
    """Les quatre entiers que `...TwistedScienceAbility$$CreateBehaviour` et
    `...TwistedScience_HealAbility$$ExecuteBehaviour` portent en dur. `probe_313` garde le mirror
    contre le BUILD ; ce test-ci fige l'ordinal ECRIT AU SITE -- le cran du dessous, sans lequel
    un renumerotage regenere rendrait `probe_313` vert alors que le port lit la mauvaise cle."""
    assert int(ActiveAbilityType.Heal) == 0x12                     # `RemoveActiveAbility(Owner, 18)`
    assert int(ActiveAbilityType.Heal_TwistedScience) == 0x48f     # `AddActiveAbility(Owner, 1167)`
    assert int(EffectType.TwistedScience_ExtraHp) == 0x54b         # stat-mod HEALTH
    assert int(EffectType.TwistedScience_ExtraDmg) == 0x54c        # +extraDmg additif
    assert int(AbilityVariableType.hp) == 0x1d                     # `ConfigVar(..., 0x1d)`
    assert int(AbilityVariableType.extraDmg) == 8                  # `ConfigVar(8, ...)`
    assert int(UnitFaction.Genestealers) == 0xf                    # `HasFaction(Target, 15, 3)`


def test_le_nom_de_l_enum_et_celui_de_la_classe_sont_inverses():
    """Piege du build, verifie plutot que commente : la classe native s'appelle
    `TwistedScience_HealAbility`, le membre d'enum `Heal_TwistedScience`. Chercher l'un sous le
    nom de l'autre ne rend RIEN, et c'est ainsi qu'un port se retrouve a enregistrer un id faux."""
    noms = {m.name for m in ActiveAbilityType}
    assert "Heal_TwistedScience" in noms
    assert "TwistedScience_Heal" not in noms


# ---------------------------------------------------------------- [1] les registres

def test_1167_au_registre_avec_son_masque_et_son_attack_type():
    """La regle de non-regression : `TARGETING_OPTIONS` **et** `ABILITY_ATTACK_TYPE` dans le meme
    commit. Les valeurs sont celles du ctor, relues :
    `TargetingOptions..ctor(&opts, 0, &<TargetingRange statics>+0x00, 2, 0x8402, 0, 0)` puis
    `AActiveAbility..ctor(this, &opts, 2)`."""
    assert ABILITY_CLASSES.get(HEAL_TS) is TwistedScience_HealAbility
    opts = TwistedScience_HealAbility.TARGETING_OPTIONS
    assert opts is not None
    assert int(opts.rules) == 0x8402
    assert int(opts.rules) == int(TR.TargetMatchesDynamicRule | TR.TargetIsFriendly
                                  | TR.CasterIsPossibleTarget)
    assert opts.self_cast is False
    # statics+0x00, PAS statics+0x30 (`RANGE_ADJACENT`, celui de `RepairAbility`) : les deux
    # coincident sur un caster de melee, ce sont deux constantes DIFFERENTES.
    assert opts.range == RANGE_ADJACENT_IF_MELEE_CASTER
    assert opts.force_melee_target == RANGED_BOOL_IF_RANGED_CASTER
    assert ABILITY_ATTACK_TYPE.get(ActiveAbilityType.Heal_TwistedScience) is AbilityAttackType.Others


def test_1167_n_a_aucune_entree_gameconfig():
    """`ABILITY_ID = None` -- comme `RepairAbility` (28) et pour la meme raison : l'ability est
    ACCORDEE (ici par un passif, la par un trait), donc elle n'a pas d'entree `units.abilities`.
    Ses deux variables vivent dans la config du PASSIF `TwistedScience`."""
    import gameconfig as GC
    assert TwistedScience_HealAbility.ABILITY_ID is None
    assert (GC.ability("Heal_TwistedScience") or None) is None
    cfg = GC.ability("TwistedScience") or {}
    assert set((cfg.get("variables") or {})) == {"hp", "extraDmg"}


def test_les_deux_effets_au_registre():
    assert EFFECT_CLASSES.get("TwistedScience_ExtraHp") is TwistedScienceExtraHpEffect
    assert EFFECT_CLASSES.get("TwistedScience_ExtraDmg") is TwistedScienceExtraDmgEffect


# ---------------------------------------------------------------- [3] la structure de l'arbre

def _tree():
    """L'arbre construit HORS state : `twisted_science_heal_tree(None, None)` -- les deux
    magnitudes retombent alors a 0 (aucun `ctx` a lire), ce qui n'affecte NI la forme NI l'ordre,
    les seuls objets de cet etage."""
    return twisted_science_heal_tree(None, None)


def test_le_soin_est_HORS_du_if_donc_inconditionnel():
    """`Execute( If(cond, buffs) op_Addition heal )` : le second terme du `op_Addition` FINAL est le
    `Heal`, jamais un `If`. Une cible deja marquee -- ou le caster lui-meme -- est donc soignee
    sans recevoir aucun buff. C'est ce que la phase `self` du probe mesure, et c'est ici que la
    STRUCTURE qui le produit est figee."""
    tree = _tree()
    assert isinstance(tree, Seq), "l'arbre racine est un op_Addition (`Seq`)"
    assert isinstance(tree.left, If), "le PREMIER terme est le bloc de buffs, sous un If"
    assert isinstance(tree.right, Heal), "le SECOND terme est le Heal, HORS du If"


def test_le_gate_de_buff_a_DEUX_termes_tous_deux_nies():
    """`cond = NOT HasEffect(Target, 1355, onlyActive = false) AND NOT get_OwnerIsTarget`.

    Les deux sont exiges : le premier porte "Affected units cannot gain the effects of Twisted
    Science again", le second "Units healed by Hollan, **other than himself**". `active_only` est
    FAUX -- le natif passe `onlyActive = false`, donc le gate voit aussi une instance INACTIVE."""
    cond = _tree().left.cond
    assert isinstance(cond, TriggerAnd)
    termes = [cond.a, cond.b]
    assert all(isinstance(t, Not) for t in termes), "les DEUX termes sont NIES"
    inner = [t.a for t in termes]
    has_eff = next((x for x in inner if isinstance(x, HasEffect)), None)
    assert has_eff is not None and int(has_eff.effect_type) == int(EffectType.TwistedScience_ExtraHp)
    assert has_eff.active_only is False
    assert any(isinstance(x, OwnerIsTarget) for x in inner)


def test_l_ordre_des_trois_volets_du_bloc_de_buffs():
    """`(statMod op_Addition changeStat) op_Addition If(hasFaction, addEffect)`.

    L'ordre statMod -> ChangeStat est celui du natif ; il n'a PAS d'observable propre (demonstration
    algebrique : `probe_931_mutants.py::_demo_m4`), donc c'est ici -- et seulement ici -- qu'il est
    garde. Le TROISIEME volet est sous un SECOND `If` : seul l'`AddEffect(1356)` est conditionne par
    la faction, jamais le +hp."""
    buffs = _tree().left.then
    a, b = buffs.left, buffs.right
    assert isinstance(b, If), "le 3e volet (l'effet de degat) est sous le gate de FACTION"
    assert isinstance(b.cond, HasFaction) and int(b.cond.faction) == int(UnitFaction.Genestealers)
    assert isinstance(b.then, AddEffect)
    assert int(b.then.effect_type) == int(EffectType.TwistedScience_ExtraDmg)
    assert b.then.duration_rounds is None, "`options = default(0)` -> PERMANENT"
    assert b.then.scale_from_source is True, "`AbilityStateReference` -> magnitude du POSEUR"
    stat_mod, change = a.left, a.right
    assert isinstance(stat_mod, AddDynamicStatModifierEffect)
    assert int(stat_mod.effect_type) == int(EffectType.TwistedScience_ExtraHp)
    assert int(stat_mod.stat_type) == int(StatType.HEALTH)
    assert stat_mod.duration_rounds is None, "`turns = null` -> PERMANENT"
    assert isinstance(change, ChangeStat)
    assert int(change.stat_type) == int(StatType.HEALTH) and change.mode == "add"


def test_le_heal_prend_les_options_ForHeal():
    """`HealBehaviourOptions$$ForHeal()` -> `(scope 0, removeEffects true)`. Ce n'est PAS un defaut
    recopie : les six call-sites du build qui prennent `ForRegenerate` sont nommes ailleurs, et
    celui-ci a ete LU."""
    heal = _tree().right
    assert heal.scope == 0 and heal.remove_effects is True


# ---------------------------------------------------------------- [4]/[5] les deux classes d'effet

def test_1356_contribue_AUSSI_en_prediction():
    """Gate `get_OwnerIsCaster` SEUL -- ni `IsNormalAttack`, ni melee/ranged, ni selecteur de
    cible. Le `if is_prediction: return None` de ses voisins de module vient d'un `IsNormalAttack`
    que cette classe n'a PAS : le recopier serait la faute inverse."""
    eff = TwistedScienceExtraDmgEffect(
        EffectType.TwistedScience_ExtraDmg.name,
        effect_type=int(EffectType.TwistedScience_ExtraDmg),
        ability_level=50, ability_variables_multiplier=180)
    en_combat = eff.create_effect_damage_bonus_for_attack(is_prediction=False)
    en_predic = eff.create_effect_damage_bonus_for_attack(is_prediction=True)
    assert en_combat is not None and en_predic is not None
    assert en_combat.value == en_predic.value and en_combat.value > 0
    assert en_combat.kind == "Addition", "`ForAddition` -> canal additif, POST-percage"
    # et il ne depend NI de la nature du coup NI des traits de la cible
    autre = eff.create_effect_damage_bonus_for_attack(is_ranged=True, is_normal_attack=False,
                                                      target_traits=frozenset({"Vehicle"}))
    assert autre is not None and autre.value == en_combat.value


def test_1355_declare_le_chemin_qui_atteint_le_plafond_de_PV():
    """`applied_stat_mods` n'est pas redondant avec le couple `get_stat_modification_*` : c'est lui
    que lit `AddEffectOperation._apply_stat_mods`, et c'est le SEUL chemin qui route `HEALTH` vers
    `HealthComponent.modify_max`. Sans lui, le `Heal` de l'arbre se clampe sur l'ANCIEN plafond
    (mesure : 6023 au lieu de 7606)."""
    eff = TwistedScienceExtraHpEffect(
        EffectType.TwistedScience_ExtraHp.name,
        effect_type=int(EffectType.TwistedScience_ExtraHp),
        ability_level=50, ability_variables_multiplier=180)
    assert int(eff.get_stat_modification_stat()) == int(StatType.HEALTH)
    amt = eff.get_stat_modification_amount()
    assert amt and int(amt) > 0
    mods = eff.applied_stat_mods(None)
    assert mods == [(int(StatType.HEALTH), int(amt))]
    assert eff.reverted_stats() == [int(StatType.HEALTH)]


def test_les_deux_magnitudes_viennent_de_la_config_du_PASSIF():
    """`hp` et `extraDmg` sont lues dans `TwistedScience` (le passif 1278), la seule entree
    gameconfig de la mecanique, et TOUTES DEUX sont `variablesAffectedByRarityBonus` -> le
    multiplicateur de rarete s'applique aux deux."""
    import gameconfig as GC
    from engine.entities.effects.magnitude import ability_var
    cfg = GC.ability("TwistedScience") or {}
    assert set(cfg.get("variablesAffectedByRarityBonus") or ()) == {"hp", "extraDmg"}
    brut_hp = ability_var("TwistedScience", "hp", 50, multiplier_pct=100)
    scale_hp = ability_var("TwistedScience", "hp", 50, multiplier_pct=180)
    assert brut_hp and scale_hp and scale_hp > brut_hp
    brut_dmg = ability_var("TwistedScience", "extraDmg", 50, multiplier_pct=100)
    scale_dmg = ability_var("TwistedScience", "extraDmg", 50, multiplier_pct=180)
    assert brut_dmg and scale_dmg and scale_dmg > brut_dmg
