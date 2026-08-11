"""#947 / #948 -- GARDE OFFLINE des DEUX passifs `_ExtraDamageEffect` portes ensemble :
`HeadClaimer` (`blackHaarken`) et `EnmityForTheUnworthy` (`darkaCompanion`).

Ce fichier ne monte AUCUN runner. Il fige ce que le decompile a LU et qu'aucun live ne re-etablit
seul (un live confronte des NOMBRES ; ici on garde des LITTERAUX, une STRUCTURE et des GATES) :

  [1] REGISTRES -- les 4 classes d'effet dans `EFFECT_CLASSES`, le trigger de `HeadClaimer` dans
      `ABILITY_TRIGGERS` (DEUX classes : la disjonction native), et `EnmityForTheUnworthy` dans
      `ABILITY_INIT_OWNER_EFFECTS` (sa classe d'ability n'a PAS de `CreateTrigger`).
  [2] LITTERAUX -- tous les membres d'enum que le decompile nomme. Un renumerotage de build les
      ferait bouger EN SILENCE (`probe_313` garde les mirrors contre le build ; ici on garde
      l'ordinal ECRIT AU SITE, cf. la doctrine du CLAUDE.md).
  [3] LES GATES QUE LE NATIF N'A PAS -- le point le plus fragile de cette famille : les deux
      `HeadClaimer` n'ont QUE `get_OwnerIsCaster`, alors que leur jumeau de MAGNITUDE
      (`TerrifyingCrescendo_ExtraDmg`, corps de `GetCurrentBonus` DEDUPLIQUE avec le leur) porte en
      plus un `IsRangedAttack`. Recopier le jumeau aurait tue le bonus sur toute attaque MELEE.
  [4] LES QUATRE ECARTS entre les DEUX effets d'`EnmityForTheUnworthy` -- population comptee,
      variable lue, canal `EffectBonus`, scaling de rarete. Une recopie de l'un sur l'autre les
      effacerait.
  [5] STRUCTURE DES SELECTEURS -- l'etage `NonSteppableOrObjectUnits` est PRESENT chez Enmity et
      ABSENT chez son voisin `Deathwing` (#932) : les deux arbres ne sont pas interchangeables.
  [6] CONTRE-EPREUVE PAR MUTATION -- chaque garde de magnitude est REJOUE contre une variante
      MUTEE du code porte, et doit ROUGIR. Un garde qui reste vert sous mutation est inerte.

ASCII only."""
from __future__ import annotations

import pytest

#: #486-r15 -- perimetre = exactement les foyers que ce fichier lit (aucun runner, aucun artefact
#: de build hors les enums, que `probe_313` garde par ailleurs contre le build).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/engine/entities/effects/loki/head_claimer.py",
        "scripts/python/engine/entities/effects/loki/enmity_for_the_unworthy.py",
        "scripts/python/engine/entities/effects/loki/deathwing.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/unit_faction.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        "scripts/python/engine/runner/operations/triggers/loki/head_claimer.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/services/effect_bonus.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Offline : fige les LITTERAUX lus au decompile (les membres d'enum des deux familles), "
              "les GATES ABSENTS (aucun IsRangedAttack/IsNormalAttack), les QUATRE ecarts entre les "
              "deux effets d'Enmity et la STRUCTURE des selecteurs. Lit le gameconfig du build pour "
              "les magnitudes (`extraDmg`, `extraDmgPct`, `extraHit`) -- d'ou `build: True`.",
}

from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.ability_variable_type import AbilityVariableType
from engine.entities.effect_type import EffectType
from engine.entities.effects.factory import (ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES)
from engine.entities.effects.loki import deathwing as DW
from engine.entities.effects.loki import enmity_for_the_unworthy as EN
from engine.entities.effects.loki import head_claimer as HC
from engine.entities.selectors.units import (AdjacentFriends, AdjacentUnits, And, UnitsFromFaction,
                                             UnitsWithoutTrait)
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.entities.unit_faction import UnitFaction
from engine.entities.unit_selection_type import UnitSelectionType
from engine.dsl.event_trigger_type import EventTriggerType
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
from engine.runner.operations.triggers.loki import head_claimer as HCT

import gameconfig as GC


# ==================================================================================================
# [1] REGISTRES
# ==================================================================================================

def test_registres_des_quatre_effets():
    """Les 4 classes d'effet sont inscrites, chacune sous le NOM d'`EffectType` capte live."""
    assert EFFECT_CLASSES["HeadClaimer_ExtraDmg"] is HC.HeadClaimerExtraDmgEffect
    assert EFFECT_CLASSES["HeadClaimer_ExtraHit"] is HC.HeadClaimerExtraHitEffect
    assert EFFECT_CLASSES["EnmityForTheUnworthy_ExtraDamage"] is \
        EN.EnmityForTheUnworthyExtraDamageEffect
    assert EFFECT_CLASSES["EnmityForTheUnworthy_ExtraDamagePct"] is \
        EN.EnmityForTheUnworthyExtraDamagePctEffect


def test_head_claimer_est_un_trigger_a_deux_branches():
    """`...HeadClaimerAbility$$CreateTrigger` est une DISJONCTION `op_BitwiseOr` : le port l'ecrit
    en DEUX entrees de registre (patron TerrifyingCrescendo). Les events sont `PreUnitDeath_2`
    (via `OnPreDeath2` -> `OnDeathEvent(2, ...)`) et `UnitFled`."""
    classes = ABILITY_TRIGGERS["HeadClaimer"]
    assert classes == [HCT.HeadClaimerOnDeathAbility, HCT.HeadClaimerOnFledAbility]
    assert int(HCT.HeadClaimerOnDeathAbility.event_id) == int(EventTriggerType.PreUnitDeath_2) == 2
    assert int(HCT.HeadClaimerOnFledAbility.event_id) == int(EventTriggerType.UnitFled) == 52


def test_enmity_est_un_owner_effect_dinit_pas_un_trigger():
    """`EnmityForTheUnworthyAbility` ne DECLARE que `CreateBehaviour` (bloc `methodPointers`) :
    aucune `CreateTrigger` propre -> pose a l'INIT, pas sur un evenement. Le port doit donc
    l'inscrire en `ABILITY_INIT_OWNER_EFFECTS` et NULLE PART dans `ABILITY_TRIGGERS`."""
    assert ABILITY_INIT_OWNER_EFFECTS["EnmityForTheUnworthy"] == [
        "EnmityForTheUnworthy_ExtraDamage", "EnmityForTheUnworthy_ExtraDamagePct"]
    assert "EnmityForTheUnworthy" not in ABILITY_TRIGGERS


# ==================================================================================================
# [2] LITTERAUX -- ce que le decompile NOMME
# ==================================================================================================

def test_litteraux_denum():
    """Les ordinaux ECRITS AUX SITES, figes a la conversion. `probe_313` garde le mirror contre le
    build ; ce test garde le fait que le SITE designe bien CE membre-la."""
    assert int(EffectType.HeadClaimer_ExtraDmg) == 0x404 == 1028
    assert int(EffectType.HeadClaimer_ExtraHit) == 0x405 == 1029
    assert int(EffectType.EnmityForTheUnworthy_ExtraDamage) == 0x578 == 1400
    assert int(EffectType.EnmityForTheUnworthy_ExtraDamagePct) == 0x577 == 1399
    # les `AbilityOrEffect` que les `.ctor` (DEDUPLIQUES) passent a `BaseEffect` -- lus AUX OCTETS
    # (`mov edx, 0x407` / `mov edx, 0x522`), et qualifies par l'overload `op_Implicit` qui pose
    # `set_TriggeredAbility` (adresse REELLE du `call`, jamais le pseudo-C).
    assert int(TriggeredAbilityType.HeadClaimer) == 0x407 == 1031
    assert int(TriggeredAbilityType.EnmityForTheUnworthy) == 0x522 == 1314
    # l'argument du `NOT TriggeringAbilityIs` de `HeadClaimerAbility$$CreateTrigger` : MEME id et
    # MEME qualification que celui de `BarbedOvipositorAbility$$CreateTrigger`.
    assert int(TriggeredAbilityType.ItsGonnaBlow) == 0x438 == 1080
    # variables/constantes lues par `ConfigVar` / `GetNumberConstant`
    assert int(AbilityVariableType.extraDmg) == 8
    assert int(AbilityVariableType.extraDmgPct) == 0xa == 10
    assert int(AbilityConstantType.extraHit) == 0x2b == 43
    # traits et faction des selecteurs
    assert int(UnitTrait.Hero) == 0x10 == 16              # `DSLTriggers$$IsHero` = HasTrait(_, 0x10)
    assert int(UnitTrait.Steppable) == 0x1b == 27         # `NonSteppableOrObjectUnits`
    assert int(UnitTrait.Object) == 0xd == 13             # idem
    assert int(UnitFaction.DarkAngels) == 0xa == 10
    assert int(UnitSelectionType.OnlyAliveAndTargetable) == 3


def test_les_deux_ctor_sont_dedupliques_donc_meme_config():
    """Consequence LUE de la dedup : les DEUX effets d'une meme famille indexent la MEME entree
    gameconfig (celle du PASSIF), jamais une entree par `EffectType`."""
    assert HC.ABILITY_ID == "HeadClaimer"
    assert EN.ABILITY_ID == "EnmityForTheUnworthy"
    assert GC.ability(HC.ABILITY_ID) is not None
    assert GC.ability(EN.ABILITY_ID) is not None


# ==================================================================================================
# [3] HEADCLAIMER -- magnitudes et GATES ABSENTS
# ==================================================================================================

def _hc_dmg(level, ability_level, mult=100):
    e = HC.HeadClaimerExtraDmgEffect(name="HeadClaimer_ExtraDmg",
                                     effect_type=int(EffectType.HeadClaimer_ExtraDmg),
                                     level=level, ability_level=ability_level,
                                     ability_variables_multiplier=mult)
    return e


def _hc_hit(level, ability_level=50, mult=100):
    return HC.HeadClaimerExtraHitEffect(name="HeadClaimer_ExtraHit",
                                        effect_type=int(EffectType.HeadClaimer_ExtraHit),
                                        level=level, ability_level=ability_level,
                                        ability_variables_multiplier=mult)


def _extra_dmg_ref(level_ability, mult):
    """`ConfigVar(extraDmg)` re-derive du gameconfig, JAMAIS un litteral recopie."""
    arr = GC.ability("HeadClaimer")["variables"]["extraDmg"]
    base = int(arr[level_ability - 1])
    return round(base * mult / 100) if mult != 100 else base


def test_head_claimer_degat_est_extradmg_fois_le_niveau_deffet():
    """`ForAddition(get_OwnerIsCaster, Multiply(ConfigVar(extraDmg), EffectLevel))` -- la
    DECOMPOSITION PAR ETAGE : niveau d'ability -> valeur nue -> multiplicateur -> x EffectLevel."""
    per = _extra_dmg_ref(50, 180)
    assert per > 0
    for heads in (1, 2, 5, 17):
        b = _hc_dmg(heads, 50, 180).create_effect_damage_bonus_for_attack()
        assert b is not None, heads
        assert b.kind == "Addition", b.kind          # canal +0x10 (jamais un ForPercentIncrease)
        assert b.value == per * heads, (heads, b.value, per)


def test_head_claimer_degat_na_aucun_gate_de_nature_de_coup():
    """L'ecart MESURE avec `TerrifyingCrescendo_ExtraDmg` (dont le corps de magnitude est le MEME,
    par dedup ICF) : celui-la porte un `IsRangedAttack`, celui-ci **rien**. Le bonus doit donc
    survivre a TOUTES les combinaisons de nature de coup, y compris melee et attaque d'ability."""
    e = _hc_dmg(3, 50, 180)
    attendu = _extra_dmg_ref(50, 180) * 3
    for kwargs in ({}, {"is_ranged": True}, {"is_ranged": False}, {"is_ranged": None},
                   {"is_normal_attack": False}, {"is_normal_attack": None},
                   {"is_prediction": True}, {"has_moved": True},
                   {"is_ranged": False, "is_normal_attack": False, "is_prediction": True}):
        b = e.create_effect_damage_bonus_for_attack(**kwargs)
        assert b is not None and b.value == attendu, kwargs


def test_head_claimer_coups_est_la_constante_extrahit_fois_le_niveau():
    """`Multiply(Get(GetNumberConstant(0x2b = extraHit)), EffectLevel)` : une CONSTANTE, donc ni
    indexee par niveau ni scalee par le multiplier de rarete."""
    n = int(GC.ability("HeadClaimer")["constants"]["extraHit"])
    assert n == 1
    for heads in (1, 4, 9):
        b = _hc_hit(heads).create_effect_hits_bonus_for_attack()
        assert b is not None and b.kind == "Addition" and b.value == n * heads, heads
    # NON scalee : le multiplier ne change RIEN (contraste `extraDmg`, qui est rarity-affected)
    assert _hc_hit(4, mult=180).create_effect_hits_bonus_for_attack().value == n * 4
    # et aucun gate de nature de coup non plus (contraste `UnstoppableFerocity_Owner` / `IsCharging`)
    assert _hc_hit(4).create_effect_hits_bonus_for_attack(is_normal_attack=False).value == n * 4


def test_head_claimer_inerte_sans_niveau():
    """Degradation FIDELE : `EffectLevel` nul (aucune tete) ou `AbilityState` inconnu -> aucune
    contribution. C'est ce qui rend le compteur observable : 0 tete = 0 bonus."""
    assert _hc_dmg(0, 50).create_effect_damage_bonus_for_attack() is None
    assert _hc_dmg(None, 50).create_effect_damage_bonus_for_attack() is None
    assert _hc_dmg(3, None).create_effect_damage_bonus_for_attack() is None
    assert _hc_hit(0).create_effect_hits_bonus_for_attack() is None
    assert _hc_hit(None).create_effect_hits_bonus_for_attack() is None


def test_head_claimer_pas_de_cap_de_niveau():
    """`max = NULL` passe a `AddEffectOrIncreaseLevel` (contraste TerrifyingCrescendo, qui passe
    `Direct(buffMaxLevel = 6)`) : la magnitude doit rester lineaire tres au-dela de 6."""
    per = _extra_dmg_ref(50, 100)
    assert _hc_dmg(20, 50).create_effect_damage_bonus_for_attack().value == per * 20
    # et le gameconfig de HeadClaimer n'a AUCUNE constante de plafond
    assert "buffMaxLevel" not in (GC.ability("HeadClaimer").get("constants") or {})


# ==================================================================================================
# [4] ENMITY -- les QUATRE ecarts entre les deux effets
# ==================================================================================================

def _en_add(n, ability_level=50, mult=100):
    e = EN.EnmityForTheUnworthyExtraDamageEffect(
        name="EnmityForTheUnworthy_ExtraDamage",
        effect_type=int(EffectType.EnmityForTheUnworthy_ExtraDamage),
        level=1, ability_level=ability_level, ability_variables_multiplier=mult)
    return e, {EN.CTX_ADJACENT_DA: n}


def _en_pct(n, ability_level=50, mult=100):
    e = EN.EnmityForTheUnworthyExtraDamagePctEffect(
        name="EnmityForTheUnworthy_ExtraDamagePct",
        effect_type=int(EffectType.EnmityForTheUnworthy_ExtraDamagePct),
        level=1, ability_level=ability_level, ability_variables_multiplier=mult)
    return e, {EN.CTX_ADJACENT_UNITS: n}


def _en_var_ref(var, level_ability, mult):
    a = GC.ability("EnmityForTheUnworthy")
    base = int(a["variables"][var][level_ability - 1])
    if mult != 100 and var in (a.get("variablesAffectedByRarityBonus") or []):
        return round(base * mult / 100)
    return base


def test_enmity_ecart_1_les_deux_lisent_des_CLES_DE_CONTEXTE_distinctes():
    """Ecart n.1 -- population comptee. La face ADDITIVE lit le compteur des amis DARK ANGELS ; la
    face POURCENTAGE lit celui de TOUTES les unites adjacentes. Les deux cles sont DISTINCTES, et
    remplir l'une ne doit PAS alimenter l'autre."""
    assert EN.CTX_ADJACENT_DA != EN.CTX_ADJACENT_UNITS
    e_add, _ = _en_add(0)
    e_pct, _ = _en_pct(0)
    # la face additive est SOURDE a la cle du pourcentage, et reciproquement
    assert e_add.create_effect_damage_bonus_for_attack(
        att_ctx={EN.CTX_ADJACENT_UNITS: 5}) is None
    assert e_pct.create_effect_damage_bonus_for_attack(
        att_ctx={EN.CTX_ADJACENT_DA: 5}) is None


def test_enmity_ecart_2_et_3_variable_et_canal():
    """Ecarts n.2 (`extraDmg` vs `extraDmgPct`) et n.3 (`ForAddition` +0x10 vs
    `ForPercentIncrease` +0x08)."""
    e, ctx = _en_add(3, 50, 180)
    b = e.create_effect_damage_bonus_for_attack(att_ctx=ctx)
    assert b.kind == "Addition"
    assert b.value == _en_var_ref("extraDmg", 50, 180) * 3

    e, ctx = _en_pct(4, 50, 180)
    b = e.create_effect_damage_bonus_for_attack(att_ctx=ctx)
    assert b.kind == "PercentIncrease"
    assert b.value == _en_var_ref("extraDmgPct", 50, 180) * 4


def test_enmity_ecart_4_seul_extradmg_est_rarity_scale():
    """Ecart n.4 -- `variablesAffectedByRarityBonus == ["extraDmg"]` : le multiplier de rarete
    scale la face ADDITIVE et laisse la face POURCENTAGE inchangee. Ce fait ne se lit QUE dans le
    gameconfig (aucun decompile ne le porte)."""
    rar = GC.ability("EnmityForTheUnworthy").get("variablesAffectedByRarityBonus") or []
    assert list(rar) == ["extraDmg"]
    e100, c = _en_add(2, 50, 100)
    v100 = e100.create_effect_damage_bonus_for_attack(att_ctx=c).value
    e180, c = _en_add(2, 50, 180)
    v180 = e180.create_effect_damage_bonus_for_attack(att_ctx=c).value
    assert v180 > v100                                    # extraDmg SCALE
    p100 = _en_pct(2, 50, 100)
    p180 = _en_pct(2, 50, 180)
    assert p100[0].create_effect_damage_bonus_for_attack(att_ctx=p100[1]).value == \
        p180[0].create_effect_damage_bonus_for_attack(att_ctx=p180[1]).value   # extraDmgPct NON


def test_enmity_tri_etat_du_compteur():
    """`AmountIsGreaterThanZero` + tri-etat : cle ABSENTE ou `None` => aucune contribution, JAMAIS
    un 0 rabattu en contribution. Et `0` voisin => inerte, ce qui EST la condition native."""
    e, _ = _en_add(0)
    assert e.create_effect_damage_bonus_for_attack(att_ctx=None) is None
    assert e.create_effect_damage_bonus_for_attack(att_ctx={}) is None
    assert e.create_effect_damage_bonus_for_attack(att_ctx={EN.CTX_ADJACENT_DA: None}) is None
    assert e.create_effect_damage_bonus_for_attack(att_ctx={EN.CTX_ADJACENT_DA: 0}) is None


def test_enmity_aucun_gate_de_nature_de_coup():
    """`get_OwnerIsCaster` est le SEUL noeud des deux conjonctions : le bonus vaut pour TOUTE
    attaque du porteur (i2 << deals ... Damage >>, sans restriction)."""
    e, ctx = _en_add(2, 50, 180)
    attendu = _en_var_ref("extraDmg", 50, 180) * 2
    for kwargs in ({}, {"is_ranged": True}, {"is_ranged": False},
                   {"is_normal_attack": False}, {"is_prediction": True}, {"has_moved": True}):
        b = e.create_effect_damage_bonus_for_attack(att_ctx=ctx, **kwargs)
        assert b is not None and b.value == attendu, kwargs


def test_enmity_active_condition_portee_et_permissive_sans_substrat():
    """`CreateActiveCondition = AmountIsGreaterThanZero(<compteur>)`, PORTEE -> le flag capte est
    perime (`active_condition_ported`). Sans substrat (`unit_state` ne porte pas ces compteurs), la
    condition rend VRAI : c'est la magnitude qui referme, jamais `is_active` -- rendre `False` par
    defaut ferait DISPARAITRE l'instance d'`active_effects`."""
    for cls in (EN.EnmityForTheUnworthyExtraDamageEffect,
                EN.EnmityForTheUnworthyExtraDamagePctEffect):
        assert cls.active_condition_ported is True
    e, _ = _en_add(0)
    assert e.is_active(None) is True
    assert e.is_active({}) is True
    assert e.is_active({EN.CTX_ADJACENT_DA: 0}) is False
    assert e.is_active({EN.CTX_ADJACENT_DA: 2}) is True
    # contraste : HeadClaimer n'a AUCUNE `CreateActiveCondition` -> flag capte souverain
    assert HC.HeadClaimerExtraDmgEffect.active_condition_ported is False
    assert HC.HeadClaimerExtraHitEffect.active_condition_ported is False


# ==================================================================================================
# [5] STRUCTURE DES SELECTEURS
# ==================================================================================================

def _flatten(node, out=None):
    """Aplatit un arbre de selecteurs par ses attributs porteurs (le port ne publie pas de
    `children` generique) -- `Count.selector` inclus, puisque les deux fabriques rendent un `Count`."""
    out = [] if out is None else out
    if node is None or not (hasattr(node, "select") or hasattr(node, "calculate")):
        return out
    out.append(node)
    for attr in ("selector", "source", "center", "entities", "units", "left", "right", "a", "b"):
        _flatten(getattr(node, attr, None), out)
    return out


def test_selecteurs_enmity_portent_letage_non_steppable_or_object():
    """`NonSteppableOrObjectUnits(entities, 3)` = `entities & UnitsWithoutTrait(Steppable) &
    UnitsWithoutTrait(Object)` -- present sur LES DEUX arbres d'Enmity."""
    for factory in (EN.adjacent_units_selector, EN.adjacent_dark_angels_friends_selector):
        noeuds = _flatten(factory())
        traits = sorted({n.trait for n in noeuds if isinstance(n, UnitsWithoutTrait)})
        assert traits == sorted([int(UnitTrait.Object), int(UnitTrait.Steppable)]), \
            (factory.__name__, traits)
        assert any(isinstance(n, And) for n in noeuds), factory.__name__


def test_selecteur_pct_ne_filtre_ni_equipe_ni_faction():
    """`AdjacentUnits(Owner, 1, 3)` NU : ni `AdjacentFriends`, ni `UnitsFromFaction`."""
    noeuds = _flatten(EN.adjacent_units_selector())
    assert any(isinstance(n, AdjacentUnits) for n in noeuds)
    assert not any(isinstance(n, AdjacentFriends) for n in noeuds)
    assert not any(isinstance(n, UnitsFromFaction) for n in noeuds)


def test_selecteur_additif_filtre_equipe_ET_faction():
    """`UnitsFromFaction(AdjacentFriends(Owner, 1, 3), DarkAngels, 3)`."""
    noeuds = _flatten(EN.adjacent_dark_angels_friends_selector())
    assert any(isinstance(n, AdjacentFriends) for n in noeuds)
    froms = {id(n): n for n in noeuds if isinstance(n, UnitsFromFaction)}
    assert len(froms) == 1
    assert next(iter(froms.values())).faction == UnitFaction.DarkAngels.name


def test_enmity_nest_pas_le_selecteur_de_deathwing():
    """L'arbre de `DeathwingEffect$$GetDoubleEffectCondition` (#932) s'arrete a `UnitsFromFaction` :
    il n'a PAS l'etage `NonSteppableOrObjectUnits`. Confondre les deux porterait un ordinal juste
    sur un arbre faux -- et les DEUX cles de contexte doivent rester distinctes."""
    dw = _flatten(DW.adjacent_dark_angels_friends_selector())
    assert not any(isinstance(n, UnitsWithoutTrait) for n in dw)
    assert EN.CTX_ADJACENT_DA != DW.CTX_ADJACENT_DA


# ==================================================================================================
# [6] CONTRE-EPREUVE PAR MUTATION -- chaque mutation doit faire ROUGIR un garde ci-dessus
# ==================================================================================================

class _MuteHeadClaimerAvecGateRanged(HC.HeadClaimerExtraDmgEffect):
    """MUTATION : on recopie le gate `IsRangedAttack` du jumeau `TerrifyingCrescendo` -- exactement
    la faute que `test_head_claimer_degat_na_aucun_gate_de_nature_de_coup` doit voir."""

    def create_effect_damage_bonus_for_attack(self, **kw):
        if kw.get("is_ranged") is not True:
            return None
        return super().create_effect_damage_bonus_for_attack(**kw)


class _MuteEnmityPctEnAdditif(EN.EnmityForTheUnworthyExtraDamagePctEffect):
    """MUTATION : on recopie le canal de la face additive sur la face pourcentage (ecart n.3)."""

    def create_effect_damage_bonus_for_attack(self, **kw):
        from engine.services.effect_bonus import for_addition
        amt = self._amount(kw.get("att_ctx"))
        return for_addition(True, amt) if amt else None


class _MuteEnmityAddSurLaCleDesUnites(EN.EnmityForTheUnworthyExtraDamageEffect):
    """MUTATION : on branche la face additive sur le compteur de TOUTES les unites (ecart n.1)."""
    _CTX_KEY = EN.CTX_ADJACENT_UNITS


class _MuteEnmityPctRarityScale(EN.EnmityForTheUnworthyExtraDamagePctEffect):
    """MUTATION : on fait croire que `extraDmgPct` est rarity-affected (ecart n.4)."""

    def _amount(self, ctx):
        n = self._count(ctx)
        if not n or self.ability_level is None:
            return None
        base = int(GC.ability("EnmityForTheUnworthy")["variables"]["extraDmgPct"]
                   [self.ability_level - 1])
        return round(base * self.ability_variables_multiplier / 100) * n


class _MuteHeadClaimerHitScaleParLeMultiplier(HC.HeadClaimerExtraHitEffect):
    """MUTATION : on traite `extraHit` comme une VARIABLE rarity-affected au lieu d'une CONSTANTE."""

    def get_hits(self):
        h = super().get_hits()
        return None if h is None else round(h * self.ability_variables_multiplier / 100)


def _rougit(fn):
    """Le garde `fn` doit LEVER. Un garde qui reste vert sous mutation est inerte."""
    with pytest.raises(AssertionError):
        fn()


def test_contre_epreuve_gate_ranged_recopie_du_jumeau(monkeypatch):
    monkeypatch.setattr(HC, "HeadClaimerExtraDmgEffect", _MuteHeadClaimerAvecGateRanged)
    _rougit(test_head_claimer_degat_na_aucun_gate_de_nature_de_coup)


def test_contre_epreuve_canal_pct_devenu_additif(monkeypatch):
    monkeypatch.setattr(EN, "EnmityForTheUnworthyExtraDamagePctEffect", _MuteEnmityPctEnAdditif)
    _rougit(test_enmity_ecart_2_et_3_variable_et_canal)


def test_contre_epreuve_face_additive_branchee_sur_la_mauvaise_cle(monkeypatch):
    monkeypatch.setattr(EN, "EnmityForTheUnworthyExtraDamageEffect",
                        _MuteEnmityAddSurLaCleDesUnites)
    _rougit(test_enmity_ecart_1_les_deux_lisent_des_CLES_DE_CONTEXTE_distinctes)


def test_contre_epreuve_pct_scale_a_tort_par_la_rarete(monkeypatch):
    monkeypatch.setattr(EN, "EnmityForTheUnworthyExtraDamagePctEffect", _MuteEnmityPctRarityScale)
    _rougit(test_enmity_ecart_4_seul_extradmg_est_rarity_scale)


def test_contre_epreuve_extrahit_traite_comme_une_variable(monkeypatch):
    monkeypatch.setattr(HC, "HeadClaimerExtraHitEffect", _MuteHeadClaimerHitScaleParLeMultiplier)
    _rougit(test_head_claimer_coups_est_la_constante_extrahit_fois_le_niveau)


def test_contre_epreuve_selecteur_enmity_sans_letage_non_steppable(monkeypatch):
    """MUTATION : on recopie le selecteur de `Deathwing` (sans `NonSteppableOrObjectUnits`)."""
    monkeypatch.setattr(EN, "adjacent_dark_angels_friends_selector",
                        DW.adjacent_dark_angels_friends_selector)
    _rougit(test_selecteurs_enmity_portent_letage_non_steppable_or_object)
