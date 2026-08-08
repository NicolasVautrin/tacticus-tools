"""#572 -- `UnbreakableDuty` (1061, `templAncient`) : les gardes OFFLINE du port.

CE QUE CE FICHIER GARDE, ET POURQUOI CHAQUE ETAGE EXISTE
--------------------------------------------------------
La confrontation LIVE (`tests/engine/runner/test_572_unbreakable_duty_live.py`) mesure le
RESULTAT ; elle ne peut pas voir ce qui, dans la STRUCTURE, ne change pas le resultat sur le banc
mesure. Les etages ci-dessous couvrent exactement cela :

  1. **L'ORDRE des feuilles.** Les cinq mecaniques du natif sont chainees par `op_Addition`, et
     l'ordre est LOAD-BEARING sur un seul couple : `AddStaticStatModifierEffect(1256 = +Attack)`
     precede l'attaque libre, donc l'attaque porte DEJA le `+extraDmg`. Les quatre autres
     permutations ne changent ni le degat, ni le flux RNG (les feuilles sont deterministes entre
     elles) -- **seule** une garde d'ORDRE les voit. Le banc live, lui, resterait VERT.
  2. **Les REGISTRES.** `TARGETING_OPTIONS` (le masque `0x8400`) et `ABILITY_ATTACK_TYPE`
     (le litteral `2 = Others`) sont deux donnees TRANSCRITES du ctor : un masque faux ne rougit
     nulle part, il accepte simplement des casts que le natif refuse. Plus le CONTRAT DE
     DISJONCTION (une ability portee ne garde pas de ligne dans `TARGETING_OPTIONS_UNPORTED`).
  3. **Les GATES de l'effet 1097.** Les deux pattes (SELF et AURA PROJETEE) doivent etre
     DISJOINTES : le banc live ne montre que la patte qui a mordu.
  4. **`units_with_traits` est une CONJONCTION.** Une union rendrait le gate des deux morts
     BEAUCOUP plus facile a passer, et le bras `ouvert` du live resterait vert.
  5. **La branche HEALTH du `ChangeStat`.** Le soin passe par `HealthComponent.hp` et NON par
     `ctx.stats[5]` -- l'ecrire dans `ctx.stats` perdrait le soin SILENCIEUSEMENT (rien ne relit
     cette entree pour les PV).
  6. **Les ORDINAUX ecrits au site.** `probe_313` compare le MIRROR au BUILD : il redevient vert
     des qu'on regenere le mirror. Ce qui manque est de figer la valeur MESUREE a la conversion.

ASCII only. Aucun runner, aucun RPC.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        # PROPRE A CE FICHIER, pris LARGE : il construit l'arbre DSL complet de 1061, donc il
        # traverse le registre d'abilities, le vocabulaire de selecteurs/formules/triggers, les
        # feuilles d'effet et de stat, et les trois mirrors d'enum. Une liste feuille a feuille
        # serait un faux vert -- elle ne pourrait pas montrer le module qu'elle a oublie.
        "scripts/python/engine/**/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Les ordinaux figes (EffectType 1097/1251/1256, UnitTrait Imperial/Hero, "
              "AbilityVariableType extraHp/extraDmg/dmgReductionPct, AbilityConstantType range, "
              "ActiveAbilityType Loki_NormalAttack) et le masque `0x8400` sont LUS du build : un "
              "changement de build peut les faire bouger sans qu'une ligne du port change.",
}

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PYDIR))

from engine.dsl.base import Const                                             # noqa: E402
from engine.entities.ability_constant_type import AbilityConstantType         # noqa: E402
from engine.entities.ability_variable_type import AbilityVariableType         # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType             # noqa: E402
from engine.entities.behaviours import If as IfBehaviour, Seq                 # noqa: E402
from engine.entities.effect_type import EffectType                            # noqa: E402
from engine.entities.effects.factory import EffectFactory                     # noqa: E402
from engine.entities.effects.loki.unbreakable_duty import (                   # noqa: E402
    UnbreakableDutyDamageReductionEffect)
from engine.entities.selectors.units import And, UnitsWithTrait, units_with_traits  # noqa: E402
from engine.entities.stats import StatType                                    # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                       # noqa: E402
from engine.entities.triggers import AmountIsEqualOrGreater, AmountIsGreaterThanZero  # noqa: E402
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType  # noqa: E402
from engine.runner.abilities.behaviours.combat import UseActiveAbility        # noqa: E402
from engine.runner.abilities.behaviours.effects import (                      # noqa: E402
    AddEffect, AddStaticStatModifierEffect)
from engine.runner.abilities.behaviours.stats import ChangeStat               # noqa: E402
from engine.runner.abilities.blacktemplars import (                           # noqa: E402
    UNBREAKABLE_DUTY_MIN_DEAD_IMPERIAL_HEROES, UnbreakableDutyAbility,
    unbreakable_duty_dead_imperial_heroes, unbreakable_duty_tree)
from engine.runner.abilities.handler import ABILITY_CLASSES                   # noqa: E402
from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED      # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR        # noqa: E402
from engine.runner.components import HealthComponent, StatsComponent          # noqa: E402

UNBREAKABLE_DUTY = int(ActiveAbilityType.UnbreakableDuty)          # 1061
EXTRA_HP, EXTRA_DMG = 7275, 1455


def _flatten(node, out=None):
    """Sequence des feuilles d'un arbre `Seq`/`If`, GAUCHE d'abord -- l'ordre d'execution natif."""
    out = [] if out is None else out
    if isinstance(node, Seq):
        _flatten(node.left, out)
        _flatten(node.right, out)
    elif isinstance(node, IfBehaviour):
        out.append(node)
        _flatten(node.then, out)
        if node.otherwise is not None:
            _flatten(node.otherwise, out)
    else:
        out.append(node)
    return out


# ================================================================================================
# 1. L'ORDRE des feuilles -- le seul etage que le banc live ne peut PAS voir
# ================================================================================================
def test_l_ordre_des_feuilles_est_celui_du_decompile():
    """`aura op_Addition If(gate, ((A + B) + C) + free)` -- cf. le bloc de commentaire de
    `blacktemplars.py`. La sequence GAUCHE-d'abord est fixee ici, feuille par feuille."""
    seq = _flatten(unbreakable_duty_tree(EXTRA_HP, EXTRA_DMG))
    kinds = [type(n).__name__ for n in seq]
    assert kinds == ["AddEffect",            # [F] l'aura, HORS du gate
                     "If",                   # [E] le gate des deux morts
                     "AddStaticStatModifierEffect",   # [A] +extraHp de PV MAX
                     "ChangeStat",                    # [B] +extraHp de PV COURANTS
                     "AddStaticStatModifierEffect",   # [C] +extraDmg d'ATTACK
                     "If",                            # [D] l'attaque libre, gatee sur le compte
                     "UseActiveAbility"], kinds


def test_le_buff_d_attaque_precede_l_attaque_libre():
    """LE couple LOAD-BEARING : l'attaque gratuite porte DEJA le `+extraDmg`. Permuter [C] et [D]
    ne changerait ni le flux RNG ni la structure des effets -- seul cet ordre-la le dit."""
    seq = _flatten(unbreakable_duty_tree(EXTRA_HP, EXTRA_DMG))
    i_dmg = next(i for i, n in enumerate(seq)
                 if isinstance(n, AddStaticStatModifierEffect)
                 and n.effect_type == int(EffectType.UnbreakableDuty_Damage))
    i_atk = next(i for i, n in enumerate(seq) if isinstance(n, UseActiveAbility))
    assert i_dmg < i_atk, "le +extraDmg doit etre pose AVANT l'attaque libre (%d vs %d)" % (i_dmg, i_atk)


def test_l_aura_est_HORS_du_gate_des_deux_morts():
    """i2 : l'aura est INCONDITIONNELLE (<< Ancient Thoread and all friendly units ... receive
    -33% Damage >>), seul le reste est sous le << If 2 or more ... >>."""
    tree = unbreakable_duty_tree(EXTRA_HP, EXTRA_DMG)
    assert isinstance(tree, Seq)
    assert isinstance(tree.left, AddEffect)
    assert tree.left.effect_type == int(EffectType.UnbreakableDuty_DamageReduction)
    assert isinstance(tree.right, IfBehaviour)
    # ... et rien d'AUTRE ne sort du gate.
    assert isinstance(tree.right.cond, AmountIsEqualOrGreater)
    assert tree.right.otherwise is None, "la branche `else` native est NULLE"


def test_les_deux_seuils_et_les_deux_durees():
    """`Direct(2)` du gate ; `TurnsFromRounds(1)` de l'aura ; `turns = null` des deux self-buffs."""
    tree = unbreakable_duty_tree(EXTRA_HP, EXTRA_DMG)
    assert UNBREAKABLE_DUTY_MIN_DEAD_IMPERIAL_HEROES == 2
    assert isinstance(tree.right.cond.b, Const) and tree.right.cond.b.evaluate(None) == 2
    assert tree.left.duration_rounds == 1 and tree.left.duration_turns is None
    for n in _flatten(tree):
        if isinstance(n, AddStaticStatModifierEffect):
            assert n.duration_rounds is None and n.duration_turns is None, (
                "les deux self-buffs sont PERMANENTS (`turns = null` natif)")


def test_l_attaque_libre_est_gatee_sur_le_COMPTE_du_selecteur():
    """`If(AmountIsGreaterThanZero(Count(sel)), attack)` -- le natif compte le MEME selecteur que
    celui que `PickRandomly` consomme, AVANT le tirage."""
    seq = _flatten(unbreakable_duty_tree(EXTRA_HP, EXTRA_DMG))
    ifs = [n for n in seq if isinstance(n, IfBehaviour)]
    assert len(ifs) == 2
    assert isinstance(ifs[1].cond, AmountIsGreaterThanZero)
    assert ifs[1].otherwise is None


# ================================================================================================
# 2. Les REGISTRES -- deux donnees TRANSCRITES qui ne rougissent nulle part si elles sont fausses
# ================================================================================================
def test_l_ability_est_au_registre_avec_son_masque_et_son_attack_type():
    assert ABILITY_CLASSES.get(UNBREAKABLE_DUTY) is UnbreakableDutyAbility
    opts = UnbreakableDutyAbility.TARGETING_OPTIONS
    assert opts is not None
    # `.ctor(&opts, 1, &<TargetingRange statics+0x18>, 1, 0x8400, 0, 0)` -- FLAGS DIRECTS.
    assert int(opts.rules) == 0x8400
    assert int(opts.rules) == int(TR.TargetIsFriendly | TR.CasterIsPossibleTarget)
    assert opts.self_cast is True
    assert opts.range.use_range_from_config is True
    assert int(opts.force_melee_target) == 1        # `RangedBool.False` (enum natif INVERSE)
    # `AActiveAbility..ctor(this, &opts, 2)` -> `Others`, PAS `DirectTargetAttack`.
    assert ABILITY_ATTACK_TYPE.get(UNBREAKABLE_DUTY) == AbilityAttackType.Others == 2


def test_contrat_de_disjonction_avec_la_table_des_NON_portees():
    """Une ability PORTEE tient son masque sur SA classe : garder une ligne dans
    `TARGETING_OPTIONS_UNPORTED` ferait DEUX sources pour la meme donnee."""
    assert UNBREAKABLE_DUTY not in TARGETING_OPTIONS_UNPORTED


# ================================================================================================
# 3. Les deux pattes de l'effet 1097, DISJOINTES
# ================================================================================================
def _eff(level=65, mult=100):
    return EffectFactory.create({"name": "UnbreakableDuty_DamageReduction", "type": 1097,
                                 "remaining": 2}, mult, None, level)


def test_l_effet_1097_est_au_registre_de_la_factory():
    e = _eff()
    assert isinstance(e, UnbreakableDutyDamageReductionEffect), (
        "1097 se materialiserait en `BaseEffect` NU : present dans decisionView, contribuant ZERO")


def test_patte_SELF_aucun_gate():
    """`get_OwnerIsTarget` SEUL : ni melee/ranged, ni profil, ni normal-only."""
    e = _eff()
    for is_melee in (True, False, None):
        for profile in ("Power", "Psychic", "Blast", None):
            b = e.create_effect_damage_malus_for_defense(is_melee, profile, None)
            assert b is not None and b.kind == "PercentDecrease" and int(b.value) == 33, (
                "melee=%s profil=%s -> %s" % (is_melee, profile, b))


def test_patte_AURA_les_trois_gates_du_selecteur():
    """`SurroundingFriends(Owner, ConfigConst(range) = 2, unique, OnlyAliveAndTargetable)` : meme
    equipe, distance <= 2, et le PORTEUR exclu (sa patte vit dans l'autre foyer)."""
    e = _eff()
    base = {"owner_id": 1, "owner_team": 0, "owner_pos": (3, 3)}
    ok = e.create_aura_defense_damage_malus_for_ally(
        dict(base, tgt_id=2, tgt_team=0, t_pos=(3, 5)))
    assert ok is not None and int(ok.value) == 33
    assert e.create_aura_defense_damage_malus_for_ally(
        dict(base, tgt_id=2, tgt_team=1, t_pos=(3, 5))) is None, "ennemi : pas d'aura"
    assert e.create_aura_defense_damage_malus_for_ally(
        dict(base, tgt_id=1, tgt_team=0, t_pos=(3, 3))) is None, (
        "le PORTEUR est servi par la patte SELF -- le compter ici serait un DOUBLE-COMPTE")
    loin = e.create_aura_defense_damage_malus_for_ally(
        dict(base, tgt_id=2, tgt_team=0, t_pos=(3, 9)))
    assert loin is None, "hors de `range` : pas d'aura"


def test_les_deux_pattes_sont_sur_la_face_DEFENSEUR():
    """La classe native derive de `BaseEffect` et surcharge `CreateEffectDamageMalusForDefense`
    (slot 0x1a) -- sa contribution va dans l'accumulateur DEFENSEUR, pas ATTAQUANT (contraste
    `PsychicFortress_DmgReduction`, dont la base est `DamageModifierAbilityEffect`)."""
    e = _eff()
    assert e.DEFENSE_MALUS_NATIVE_FACE == "defender"
    assert e.AURA_DEFENSE_MALUS_NATIVE_FACE == "defender"


def test_la_magnitude_n_est_PAS_scalee_par_la_rarete():
    """`dmgReductionPct` est HORS de `variablesAffectedByRarityBonus` (= ['extraDmg', 'extraHp'])
    -> le multiplier est INERTE. Le passer quand meme mirrorе le natif (qui le passe aussi)."""
    assert int(_eff(65, 100).create_effect_damage_malus_for_defense().value) == 33
    assert int(_eff(65, 180).create_effect_damage_malus_for_defense().value) == 33


# ================================================================================================
# 4. `UnitsWithTraits` est une CONJONCTION
# ================================================================================================
class _FakeCtx:
    """Le minimum que lisent `UnitsWithTrait` (`ctx.has_trait`) et la source ci-dessous."""
    def __init__(self, units):
        self.units, self.caster, self.owner, self.target = units, units[0], units[0], None
        self.has_trait = lambda u, t: UnitTrait(int(t)).name in (u.get("_traits") or set())


class _Src:
    """Source de test : rend `ctx.units` verbatim (stand-in du `AllAliveUnits` natif)."""
    def evaluate(self, ctx):
        return list(ctx.units)


def test_units_with_traits_exige_TOUS_les_traits():
    """`UnitsWithTraits` FOLDE `op_BitwiseAnd(left, UnitsWithTrait(entities, t))` -- une UNION
    rendrait le gate des deux morts beaucoup plus facile a passer, et le bras `ouvert` du banc
    live resterait VERT."""
    units = [{"id": 1, "_traits": {"Imperial", "Hero"}},
             {"id": 2, "_traits": {"Imperial"}},
             {"id": 3, "_traits": {"Hero"}},
             {"id": 4, "_traits": set()}]
    sel = units_with_traits(_Src(), (UnitTrait.Imperial, UnitTrait.Hero))
    got = [u["id"] for u in sel.evaluate(_FakeCtx(units))]
    assert got == [1], got
    # ... et la composition est bien celle du natif : DEUX `And` empiles sur la MEME source.
    assert isinstance(sel, And) and isinstance(sel.b, UnitsWithTrait)
    assert isinstance(sel.a, And) and isinstance(sel.a.b, UnitsWithTrait)


def test_le_gate_compte_les_morts_ALLIES_avec_les_DEUX_traits():
    """`Friends(of = Owner, entities = AllDeadOrResurrectedUnits())` puis les deux traits."""
    from engine.entities.selectors.units import Friends, AllDeadOrResurrectedUnits
    sel = unbreakable_duty_dead_imperial_heroes()
    assert isinstance(sel, And)
    src = sel.a.a if isinstance(sel.a, And) else sel.a
    assert isinstance(src, Friends) and isinstance(src.inner, AllDeadOrResurrectedUnits)


# ================================================================================================
# 5. La branche HEALTH du `ChangeStat` -- la stat FILL-UP ne vit PAS dans `ctx.stats`
# ================================================================================================
def _state_with_unit(uid=1, hp=1000, hp_max=1000):
    from engine.runner.state import State
    from engine.runner.components import OwnerComponent, UnitComponent
    from engine.entities.unit_context import UnitContext
    st = State()
    e = st.add_entity(uid)
    e.add_component(OwnerComponent(team=1, player=3))
    e.add_component(UnitComponent(visual_id="templAncient", alive=True))
    e.add_component(HealthComponent(hp=hp, hp_max=hp_max))
    e.add_component(StatsComponent(UnitContext(entity_id=uid, visual_id="templAncient")))
    return st


class _Entities:
    """Le minimum que lit la feuille : `_units_of(target_sel)` puis `caster`."""
    def __init__(self, unit):
        self.units, self.caster, self.owner = [unit], unit, unit
        self.target = None


def test_le_changestat_HEALTH_monte_les_PV_COURANTS_et_PAS_ctx_stats():
    """Le natif ecrit `StatModifier(Position(Health, Current), GetStat + delta)` -> `hc.hp`.
    Ecrire dans `ctx.stats[5]` perdrait le soin SILENCIEUSEMENT (rien ne relit cette entree)."""
    from engine.dsl.effects import ExecutionContext
    from engine.entities.selectors.accessors import Owner
    st = _state_with_unit(hp=1000, hp_max=1000)
    unit = {"id": 1}
    ChangeStat(Owner(), int(StatType.HEALTH), "add", "t", 500).execute(
        _Entities(unit), ExecutionContext(state=st, rng=None))
    hc = st.get_entity(1).get_component(HealthComponent)
    assert hc.hp == 1500, hc.hp
    sc = st.get_entity(1).get_component(StatsComponent)
    assert sc.ctx.stats.get_stat(int(StatType.HEALTH), 0) in (0, None), (
        "la modification ne doit PAS atterrir dans `ctx.stats[HEALTH]`")


def test_le_changestat_d_une_AUTRE_stat_reste_dans_ctx_stats():
    """ANTI-SUR-CORRECTION : la branche est bornee a HEALTH ; CRIT_DAMAGE (le seul autre
    consommateur porte de cette feuille) doit continuer de passer par `apply_change_stat`."""
    from engine.dsl.effects import ExecutionContext
    from engine.entities.selectors.accessors import Owner
    st = _state_with_unit(hp=1000, hp_max=1000)
    unit = {"id": 1}
    ChangeStat(Owner(), int(StatType.CRIT_DAMAGE), "add", "t", 40).execute(
        _Entities(unit), ExecutionContext(state=st, rng=None))
    sc = st.get_entity(1).get_component(StatsComponent)
    assert sc.ctx.stats.get_stat(int(StatType.CRIT_DAMAGE), 0) == 40
    assert st.get_entity(1).get_component(HealthComponent).hp == 1000


# ================================================================================================
# 6. Les ORDINAUX ECRITS AU SITE, figes a la valeur MESUREE le 2026-08-08 sur `rnca9r7q6c`
# ================================================================================================
def test_les_ordinaux_lus_au_decompile_sont_figes():
    """`probe_313` compare le MIRROR au BUILD : il redevient VERT des qu'on regenere le mirror
    apres un renumerotage. Ce qui manque est de figer la valeur ECRITE AU SITE."""
    assert int(EffectType.UnbreakableDuty_DamageReduction) == 0x449     # 1097
    assert int(EffectType.UnbreakableDuty_Health) == 0x4E3              # 1251
    assert int(EffectType.UnbreakableDuty_Damage) == 0x4E8              # 1256
    assert int(ActiveAbilityType.UnbreakableDuty) == 1061
    assert int(ActiveAbilityType.Loki_NormalAttack) == 0x45             # le 4e arg d'UseActiveAbility
    assert int(UnitTrait.Imperial) == 0x1A and int(UnitTrait.Hero) == 0x10
    assert int(AbilityVariableType.extraHp) == 0x1E
    assert int(AbilityVariableType.extraDmg) == 0x08
    assert int(AbilityVariableType.dmgReductionPct) == 0x46
    assert int(AbilityConstantType.range) == 0x16
    assert int(StatType.HEALTH) == 5 and int(StatType.ATTACK) == 0


def test_les_ordinaux_communs_nomment_AUTRE_CHOSE_dans_l_enum_voisin():
    """CE QUI REND LE NOM OBLIGATOIRE : les quatre cles de config de 1061 ont un homonyme
    d'ordinal dans l'AUTRE enum, et il nomme une cle SANS RAPPORT -- confondre `ConfigVar` et
    `ConfigConst` ne leverait AUCUNE erreur, ca lirait juste la mauvaise cle du gameconfig."""
    paires = []
    for v in (AbilityVariableType.extraHp, AbilityVariableType.extraDmg,
              AbilityVariableType.dmgReductionPct):
        try:
            autre = AbilityConstantType(int(v))
        except ValueError:
            continue
        paires.append((v.name, autre.name))
    assert paires, "aucun ordinal commun -- ce test serait VIDE, donc faussement vert"
    for var_name, const_name in paires:
        assert var_name != const_name, (var_name, const_name)


def test_les_magnitudes_du_gameconfig_sont_celles_de_l_i2():
    """i2 (L65) : << gains 7275 extra Health and +1455 Damage >>, << -33% Damage >>, << 2 hexes >>."""
    from engine.entities.effects.magnitude import ability_var
    assert int(ability_var("UnbreakableDuty", "extraHp", 65)) == 7275
    assert int(ability_var("UnbreakableDuty", "extraDmg", 65)) == 1455
    assert int(ability_var("UnbreakableDuty", "dmgReductionPct", 65)) == 33
    assert int(ability_var("UnbreakableDuty", "range", is_constant=True)) == 2


if __name__ == "__main__":                                     # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
