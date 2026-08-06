"""#419-r1-tr14-r4-r2-r1-r1 / -r2 -- GARDE des DEUX branches SPECIALES de l'attaque normale.

CE QUE CE FICHIER VERROUILLE

Le parent (#419-r1-tr14-r4-r2-r1) a porte le TAG `Use_Special` et s'est arrete devant deux
choses, chacune pour une raison differente :

  * `-r1` : la branche de `FeederTendrils` executait AUSSI `Heal(ConfigVar hpToHeal)` et
    `AddEffect(Pinned)`, que le port ne jouait pas -- une divergence de COMBAT, pas de flux ;
  * `-r2` : l'ANCRE du gate d'`OptimizedGait_NormalAttack` n'etait pas tranchee (caster ou cible ?).

Les deux sont resolus. Ce fichier garde les faits de RE qui les rendent actionnables, parce
qu'ils se periment EN SILENCE.

CE QUE CE FICHIER NE COUVRE PAS -- la confrontation live :
`probe_419r1tr14r4r2r1r1_normal_attack_special_branches.py` (mesure du 2026-08-06, MC1_67).

ASCII only.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_PYDIR = Path(__file__).resolve().parents[3]
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

from engine.entities.behaviours import AtomicGroup, Seq  # noqa: E402
from engine.entities.effect_type import EffectType  # noqa: E402
from engine.entities.selectors.accessors import Target
from engine.entities.selectors.tiles import Caster  # noqa: E402
from engine.runner.abilities.behaviours.effects import AddEffect
from engine.runner.abilities.behaviours.stats import Heal  # noqa: E402
from engine.runner.abilities.behaviours.stats import healable_heal_type_0  # noqa: E402
from engine.runner.abilities.loki.feeder_tendrils import (  # noqa: E402
    ATOMIC_GROUP, CONFIG_ID, PINNED, feeder_tendrils_special_tree)
from engine.services import custom_normal_attack as CNA  # noqa: E402
from engine.streams.group_type import GroupType  # noqa: E402


# =============================================================================================
# ETAGE 1 -- le GATE de `FeederTendrils` est une CONJONCTION, sur QUATRE combinaisons
# =============================================================================================

def test_gate_feeder_tendrils_est_une_conjonction():
    """`if ((charging & isMelee) == 0) return base.ExecuteBehaviour(...)` -- LU verbatim dans
    `IdunBattleLogic.Entities.Abilities.Active.Loki.FeederTendrils_NormalAttackAbility$$ExecuteBehaviour`.

    Le second terme est `WeaponProfile.get_IsMelee(weapon)`, PAS un second predicat de charge : le
    lire ainsi declencherait la branche sur un TIR de charge, que le natif ne joue pas. Les QUATRE
    combinaisons sont exercees -- une seule doit passer."""
    na = "FeederTendrils_NormalAttack"
    table = {(c, m): CNA.feeder_tendrils_special_applies(na, is_charging=c, weapon_melee=m)
             for c in (True, False) for m in (True, False)}
    assert table[(True, True)] is True, "charge AU CONTACT : la branche speciale DOIT jouer"
    assert table[(True, False)] is False, (
        "TIR de charge : le second terme est get_IsMelee, pas un IsCharging -- la branche ne "
        "doit PAS jouer")
    assert table[(False, True)] is False, "melee sans charge : pas de branche"
    assert table[(False, False)] is False
    assert sum(1 for v in table.values() if v) == 1, (
        "le gate doit etre une CONJONCTION : exactement 1 des 4 combinaisons")


def test_gate_ne_repond_que_pour_le_porteur():
    """Une autre attaque normale ne traverse JAMAIS ce gate, meme en charge melee."""
    for autre in (None, "Loki_NormalAttack", "OptimizedGait_NormalAttack", "Boltstorm_NormalAttack"):
        assert CNA.feeder_tendrils_special_applies(autre, True, True) is False, autre


# =============================================================================================
# ETAGE 2 -- l'ANCRE d'`OptimizedGait_NormalAttack` : le CASTER, et le foyer la porte
# =============================================================================================

def test_ancre_optimized_gait_est_le_caster():
    """`EntityExtensions$$HasEffect(entities@+8, state, 0x4e2, null)` et `AbilityEntities$$.ctor`
    ecrit `+0x08 = caster`.

    MESURE du 2026-08-06 (probe, `admecRuststalker` des deux cotes, 3 bras SEPARANTS) :
      * effet sur le CASTER seul -> `Tag=Attack_Weapon_Use_Special:1` ;
      * effet sur la CIBLE seule -> tag ABSENT ;
      * effet nulle part          -> tag ABSENT.
    Le bras `cible` est le discriminant : une ancre-cible aurait ecrit le tag."""
    na = "OptimizedGait_NormalAttack"
    assert CNA.inform_weapon_use_special(na, False, True, caster_has_gate_effect=True) is True
    assert CNA.inform_weapon_use_special(na, True, True, caster_has_gate_effect=False) is False
    # canal MUET -> False (comportement d'avant), jamais une devinette
    assert CNA.inform_weapon_use_special(na, True, True) is False


def test_les_deux_poseurs_ne_se_contaminent_pas():
    """Les deux abilities posent `useSpecial = 1` sous des gates DIFFERENTS. Croiser les gates est
    la faute que ce test interdit : `FeederTendrils` ne repond pas a l'effet, `OptimizedGait` ne
    repond pas a la charge."""
    assert CNA.inform_weapon_use_special(
        "FeederTendrils_NormalAttack", False, True, caster_has_gate_effect=True) is False, (
        "FeederTendrils ne doit PAS repondre au gate d'EFFET d'OptimizedGait")
    assert CNA.inform_weapon_use_special(
        "OptimizedGait_NormalAttack", True, True, caster_has_gate_effect=False) is False, (
        "OptimizedGait ne doit PAS repondre au gate de CHARGE de FeederTendrils")


# =============================================================================================
# ETAGE 3 -- la FORME de l'arbre, et les DEUX ancres qui DIFFERENT
# =============================================================================================

def test_arbre_feeder_tendrils_mirror_du_decompile():
    """`ExecuteAtomic( Heal(sel@+0x30, sel@+0x30, ConfigVar, ForHeal)
                     + AddEffect(0x429, AbilityStateReference, sel@+0x60, null), 0x2a )`.

    `+0x30` = CASTER et `+0x60` = TARGET -- etabli par `DSLTriggers$$IsCharging(this, caster,
    target)`, appele deux lignes plus haut dans le MEME `ExecuteBehaviour` avec exactement ces deux
    selecteurs. Les DEUX ancres DIFFERENT donc, et c'est le point le plus facile a rater : le soin
    va au caster, le `Pinned` a la cible."""
    tree = feeder_tendrils_special_tree(1234)
    assert isinstance(tree, AtomicGroup), "le natif enveloppe dans un ExecuteAtomic"
    assert isinstance(tree.child, Seq), "op_Addition -> Seq (Heal PUIS AddEffect)"
    heal, pin = tree.child.left, tree.child.right
    assert isinstance(heal, Heal), "volet GAUCHE = Heal"
    assert isinstance(pin, AddEffect), "volet DROIT = AddEffect"
    assert isinstance(heal.targets_sel, Caster), (
        "le Heal vise le CASTER (selecteur +0x30, passe DEUX FOIS au natif)")
    assert isinstance(pin.target_sel, Target), (
        "l'AddEffect vise la CIBLE (selecteur +0x60) -- PAS le caster")
    assert heal.amount_fn == 1234, "le montant est un scalaire deja resolu (fold du ConfigVar)"
    assert heal.guard is healable_heal_type_0, (
        "la garde `Healable` du `HealableUnitsSelector` est portee cote mutation")
    assert pin.effect_type == PINNED
    assert pin.duration_rounds is None, (
        "`turns: null` au natif (aucun `TurnsFromRounds`) -> duree DEFAUT ; "
        "contraste LU : CordClaw passe TurnsFromRounds(2) a la MEME position")


# =============================================================================================
# ETAGE 4 -- les LITTERAUX, qualifies par leur ENUM (jamais infores d'un nom)
# =============================================================================================

def test_litteraux_qualifies_par_leur_enum():
    """Chaque entier qui DESIGNE passe par son membre. Deux d'entre eux sont des homonymes
    d'ordinal, et c'est pour cela que le nom est obligatoire :
      * `0x2a` = 42 = `GroupType.Ability_AtomicGroup`, mais AUSSI `StepType.RotateUnit` ;
      * `0x20` = 32 = `AbilityVariableType.hpToHeal`, mais AUSSI `AbilityConstantType.hpForArmor`
        (tranche par la SURCHARGE `ConfigVar(this, variableType, abilityState, config)`)."""
    assert PINNED == int(EffectType.Pinned) == 0x429
    assert ATOMIC_GROUP == int(GroupType.Ability_AtomicGroup) == 0x2a
    assert CNA.USE_SPECIAL_GATE_EFFECT == int(EffectType.CordClaw_AdditionHits) == 0x4e2
    from engine.entities.ability_variable_type import AbilityVariableType
    assert int(AbilityVariableType.hpToHeal) == 0x20


def test_hp_to_heal_vit_sous_le_PASSIF_pas_sous_l_attaque_substituee():
    """`FeederTendrils_NormalAttack` n'a AUCUNE entree gameconfig : la variable `hpToHeal` est
    portee par le PASSIF `FeederTendrils`, ce qui est coherent avec la fabrique
    (`AddNormalAttackAbility` monte l'attaque substituee avec le `triggeredAbilityState`).

    Un port qui chercherait la config sous le nom de l'ATTAQUE lirait `None` et ne soignerait
    RIEN -- sans erreur."""
    import gameconfig as GC
    assert GC.ability("FeederTendrils_NormalAttack") is None, (
        "si cette entree apparait un jour, le choix de config est a re-trancher")
    kit = GC.ability(CONFIG_ID) or {}
    assert "hpToHeal" in (kit.get("variables") or {}), (
        "la variable du Heal doit vivre sous le PASSIF")


# =============================================================================================
# ETAGE 5 -- le CALL-SITE, cette garde que la contre-epreuve du foyer ne PEUT PAS donner
# =============================================================================================

def _source_normal_py() -> str:
    p = _PYDIR / "engine" / "runner" / "operations" / "damage_ops" / "normal.py"
    return p.read_text(encoding="utf-8")


def test_call_site_lit_la_constante_d_effet_et_la_passe_au_foyer():
    """CE QUE LA MUTATION `M4` DU PROBE NE PEUT PAS ATTRAPER, et pourquoi cet etage existe.

    Muter `USE_SPECIAL_GATE_EFFECT` laisse le FOYER inerte -- il recoit un BOOLEEN deja resolu,
    donc la constante ne peut pas l'atteindre. Son gardien est le CALL-SITE : c'est lui qui lit
    l'effet sur le caster et passe le resultat. Sans cet etage, la constante pourrait devenir
    n'importe quoi sans qu'aucun test ne rougisse.

    L'assertion porte sur les DEUX SENS : la constante est lue, ET c'est bien l'ATTAQUANT qui est
    interroge (pas la cible)."""
    src = _source_normal_py()
    assert "USE_SPECIAL_GATE_EFFECT" in src, (
        "le call-site doit LIRE la constante d'effet du foyer")
    assert "has_effect_of_type(state, attacker_id" in src, (
        "le gate doit interroger l'ATTAQUANT (ancre = caster) -- interroger `target_id` serait "
        "l'ancre REFUTEE par la mesure")
    assert "caster_has_gate_effect=has_effect_of_type" in src


def test_call_site_joue_la_branche_speciale_avant_l_attaque():
    """POSITION du bloc, mirror du natif : `ExecuteInformWeapon` -> bloc special ->
    `ExecuteNormalAttack`. On verifie que l'appel a la branche est bien SOUS le gate et AVANT le
    calcul des modificateurs d'attaque (le 1er etage de l'attaque qui suit)."""
    src = _source_normal_py()
    i_inform = src.find("_iw_tags = InformWeapon.from_weapon")
    i_special = src.find("execute_feeder_tendrils_special(state, attacker_id, target_id)")
    i_mods = src.find("mods, active = attacker_modifiers(")
    assert i_inform != -1 and i_special != -1 and i_mods != -1
    assert i_inform < i_special < i_mods, (
        "la branche speciale se joue APRES ExecuteInformWeapon et AVANT l'attaque -- "
        "c'est la position du natif")
    assert "feeder_tendrils_special_applies(" in src, (
        "le bloc doit etre garde par le predicat PARTAGE avec le tag, pas par un second predicat")


def test_le_gate_du_tag_et_celui_du_bloc_sont_le_MEME():
    """Le natif ne teste le gate qu'UNE FOIS. Deux predicats separes pourraient diverger ; on
    verifie donc qu'ils rendent la meme reponse sur les quatre combinaisons."""
    na = "FeederTendrils_NormalAttack"
    for c in (True, False):
        for m in (True, False):
            assert (CNA.inform_weapon_use_special(na, c, m)
                    == CNA.feeder_tendrils_special_applies(na, c, m)), (c, m)


# =============================================================================================
# ETAGE 6 -- le call-site n'a pas re-derive une SECONDE table
# =============================================================================================

def test_pas_de_second_foyer_de_decision():
    """Le nom de l'attaque normale qui declenche la branche ne doit apparaitre QU'AU foyer.
    Un littéral `"FeederTendrils_NormalAttack"` recopie dans `normal.py` serait un fork."""
    src = _source_normal_py()
    assert '"FeederTendrils_NormalAttack"' not in src, (
        "la decision appartient au foyer `custom_normal_attack`, pas au call-site")
    arbre = ast.parse(src)
    assert isinstance(arbre, ast.Module)
