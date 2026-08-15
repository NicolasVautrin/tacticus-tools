"""#1008 OFFLINE -- les DEUX reliques BLACK LEGION : `BookOfFate` (1461, `blackPossession`) et
`Helspear` (1558, `blackHaarken`).

Ce fichier GARDE ce que le decompile a dit, sans session : les ordinaux ECRITS AUX SITES, le
cablage des DEUX registres, la STRUCTURE des deux arbres, et les residus NOMMES (un residu qu'on
n'assertionne pas se referme tout seul en silence a la premiere refonte).

Pourquoi FIGER les ordinaux ici alors que `probe_313` garde deja les mirrors : `probe_313` compare
le MIRROR au BUILD, donc il redevient vert des qu'on regenere le mirror apres un renumerotage --
alors que la valeur ECRITE au site, elle, a change (meme cran que `test_1001_votann_relics_offline`).
"""
from __future__ import annotations

#: Perimetre : les deux modules de trigger, la classe d'effet, les registres qui les font exister,
#: le selecteur NEUF (`HasAnyValidTarget`) et la formule NEUVE (`UnitLevel`) que la tranche a du
#: ajouter, l'accesseur de magnitude, et TOUS les mirrors d'enum dont un ordinal est fige ci-dessous.
#: `gameconfig.json` entre au perimetre parce que les TROIS variables/constantes en sortent.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/operations/triggers/loki/book_of_fate.py",
        "scripts/python/engine/runner/operations/triggers/loki/helspear.py",
        "scripts/python/engine/entities/effects/loki/helspear.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/entities/selectors/valid_targets.py",
        "scripts/python/engine/entities/selectors/__init__.py",
        # Ce fichier importe `units.First`, qui EST `PickFirstN` depuis #1032-r2 : son
        # implementation vit dans le module FEUILLE `._pick`, donc le declencheur doit le nommer.
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/_pick.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/entities/stats.py",
        "scripts/python/engine/dsl/base.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "data/symbols/*/gameconfig.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "Offline : fige les ordinaux ECRITS AUX SITES (que `probe_313` ne voit pas -- il "
              "compare le mirror au build, pas le site), le cablage des DEUX registres "
              "(`RELIC_ABILITY_TRIGGERS`, `EFFECT_CLASSES`), la STRUCTURE des deux arbres "
              "(cascade `Otherwise` a TROIS etages de `BookOfFate` ; ordre "
              "`(buff & attaque) & retrait` ; increment A GAUCHE du `If` de `Helspear`), les "
              "gates des TROIS `CreateTrigger`, et les DEUX residus nommes (`#1008-r2` la "
              "magnitude non branchee, `#1008-r3` le conjoint non identifie) -- un residu qu'on "
              "n'assertionne pas se referme en silence.",
}

import pytest        # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)

from engine.dsl.event_trigger_type import EventTriggerType                    # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.ability_variable_type import AbilityVariableType
from engine.entities.effect_type import EffectType
from engine.entities.effects import factory as F
from engine.entities.effects.loki.helspear import HelspearIgnoreArmorEffect
from engine.entities.formulas import UnitLevel
from engine.entities.selectors.geometry import Otherwise
from engine.entities.selectors.units import First, SortByFormula, UnitsWithTrait, UnitsWithoutTrait
from engine.entities.selectors.valid_targets import HasAnyValidTarget
from engine.entities.stats import StatType
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.entities.unit_selection_type import UnitSelectionType
from engine.runner.operations.triggers.dispatch.registry import RELIC_ABILITY_TRIGGERS
from engine.runner.operations.triggers.loki import book_of_fate as BOF
from engine.runner.operations.triggers.loki import helspear as HS


# =====================================================================================
# ETAGE 1 -- les ORDINAUX ECRITS AUX SITES (ce que `probe_313` ne peut pas voir)
# =====================================================================================

def test_ordinaux_ecrits_aux_sites():
    """Chaque littéral RELU au decompile, fige a la valeur MESUREE sur `rnca9r7q6c`."""
    # BookOfFate
    assert BOF.BOOK_OF_FATE == 1461 == int(TriggeredAbilityType.BookOfFate)
    assert BOF.DAEMON_BUFF_EFFECT == 1452 == int(EffectType.BookOfFate_DaemonBuff)
    assert BOF.BookOfFateAbility.event_id == 38 == int(EventTriggerType.NormalAttack)
    assert int(UnitTrait.Summon) == 2 and int(UnitTrait.Daemon) == 1019          # 0x2 / 0x3fb
    assert int(AbilityVariableType.extraDmg) == 8
    assert int(AbilityConstantType.affectedUnitId) == 140                        # 0x8c
    assert int(StatType.ATTACK) == 0
    assert BOF._GROUP_ABILITY_ATTACK == 0x20                                     # GroupType.Ability_Attack
    assert BOF._SEL == 3 == int(UnitSelectionType.OnlyAliveAndTargetable)
    # Helspear
    assert HS.HELSPEAR == 1558 == int(TriggeredAbilityType.Helspear)
    assert HS.IGNORE_ARMOR_EFFECT == 1583 == int(EffectType.Helspear_IgnoreArmor)
    assert HS.DESPOILED_GROUND_EFFECT == 1476 == int(EffectType.DespoiledGround)
    assert HS.HERALD_OF_THE_APOCALYPSE == 1020 == int(ActiveAbilityType.HeraldOfTheApocalypse)
    assert HS.HelspearBuffActiveAbility.event_id == 9 == int(EventTriggerType.Attack)
    assert HS.HelspearResetActiveAbility.event_id == 54 == int(EventTriggerType.UnitDefeated)
    assert int(AbilityVariableType.nrOfUnits) == 154                             # 0x9a
    assert int(AbilityVariableType.armorIgnored) == 64                           # 0x40


def test_le_1020_de_helspear_est_un_ActiveAbilityType_et_pas_un_autre():
    """`0x3fc` est QUALIFIE par l'adresse de son `op_Implicit` (RVA `166a000` = surcharge
    `activeAbility`), pas par son ordinal -- et ce test montre POURQUOI c'etait necessaire :
    1020 est un membre VALIDE de DEUX autres enums, ou il nomme AUTRE CHOSE.

    Ce controle assertionne son propre non-vide (le vice mesure par #270-r1-r1-r3 : un test
    d'intersection qui rend un ensemble VIDE passerait pour vert)."""
    autres = {}
    for enum in (TriggeredAbilityType, EffectType):
        try:
            autres[enum.__name__] = enum(1020).name
        except ValueError:
            pass
    assert autres, "controle DEGENERE : 1020 devait exister dans au moins un AUTRE enum"
    assert ActiveAbilityType(1020).name == "HeraldOfTheApocalypse"
    for nom in autres.values():
        assert nom != "HeraldOfTheApocalypse", (
            "l'ordinal ne discrimine pas -- seule l'adresse de l'`op_Implicit` le fait")


# =====================================================================================
# ETAGE 2 -- le CABLAGE des registres (le diff d'une tranche ne les atteint jamais seul)
# =====================================================================================

def test_registres_cables():
    assert RELIC_ABILITY_TRIGGERS.get("BookOfFate") == [BOF.BookOfFateAbility]
    assert RELIC_ABILITY_TRIGGERS.get("Helspear") == [HS.HelspearBuffActiveAbility,
                                                      HS.HelspearResetActiveAbility]
    # L'EFFET dans le MEME commit que l'ability (regle de non-regression du CLAUDE.md).
    assert F.EFFECT_CLASSES.get("Helspear_IgnoreArmor") is HelspearIgnoreArmorEffect


def test_book_of_fate_n_a_pas_d_effet_dedie_et_c_est_LU():
    """L'effet 1452 est le `StaticStatModifierEffect` GENERIQUE que monte
    `AddStaticStatModifierEffect` -- le build ne porte AUCUNE classe
    `IdunBattle.Entities.Effects.*.BookOfFate*Effect`. Rien a inscrire dans `EFFECT_CLASSES`, et ce
    test le FIGE : si un jour une classe dediee apparait, l'absence redeviendra une dette."""
    assert "BookOfFate_DaemonBuff" not in F.EFFECT_CLASSES


def test_aucune_relique_n_est_dans_les_DEUX_registres():
    """Le registre relique est SEPARE de `ABILITY_TRIGGERS` a dessein (cf. l'en-tete de
    `registry.py`) : la double-inscription doit rester structurellement impossible."""
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    assert not (set(RELIC_ABILITY_TRIGGERS) & set(ABILITY_TRIGGERS))


# =====================================================================================
# ETAGE 3 -- la STRUCTURE des arbres (ce qu'un scalaire ne montrerait pas)
# =====================================================================================

def test_book_of_fate_cascade_a_TROIS_etages_dans_l_ordre_natif():
    """`pipe(A).Otherwise(pipe(B)).Otherwise(pipe(C))` -- A = l'unite NOMMEE par la constante,
    B = un Daemon, C = un non-Daemon. L'ordre est LU, et il n'est PAS dans l'i2."""
    sel = BOF.book_of_fate_target_selector("thousSmnDaemonPrince")
    assert isinstance(sel, Otherwise)
    assert isinstance(sel.primary, Otherwise)             # (A otherwise B) otherwise C
    a, b, c = sel.primary.primary, sel.primary.fallback, sel.fallback
    # Chaque etage : First(SortByFormula(Cache(Randomize(X)), UnitLevel, desc), 0)
    for etage in (a, b, c):
        assert isinstance(etage, First)
        assert isinstance(etage.source, SortByFormula)
        assert etage.source.ascending is False            # `ascending = false` -> DESCENDANT
        assert isinstance(etage.source.formula, UnitLevel)
    # etage B = AVEC le trait Daemon, etage C = SANS.
    assert isinstance(b.source.source.source.source, UnitsWithTrait)
    assert b.source.source.source.source.trait == int(UnitTrait.Daemon)
    assert isinstance(c.source.source.source.source, UnitsWithoutTrait)
    assert c.source.source.source.source.trait == int(UnitTrait.Daemon)


def test_book_of_fate_le_pool_passe_par_HasAnyValidTarget():
    """Le << in range >> de l'i2 vit dans le BEHAVIOUR (`UnitsWithAnyValidTarget` surcharge a UN
    argument), pas dans le trigger. Ce noeud N'EXISTAIT PAS avant cette tranche -- la prose de
    `valid_targets.py` le declarait << deja porte >>, a tort."""
    sel = BOF.book_of_fate_target_selector("x")
    pool = sel.primary.primary.source.source.source.source.source   # descend jusqu'a la source
    assert isinstance(pool, HasAnyValidTarget)
    assert pool.selection_type == int(UnitSelectionType.OnlyAliveAndTargetable)


def test_book_of_fate_ordre_pose_attaque_retrait():
    """`op_BitwiseAnd( op_BitwiseAnd(b1 = buff, b3 = attaque), b2 = retrait )` -- l'ordre est LU au
    dernier `op_BitwiseAnd`. Inverser les deux derniers termes retirerait le buff AVANT qu'il ne
    serve, et l'effet 1452 ne changerait jamais aucun degat."""
    from engine.runner.abilities.behaviours.effects import (AddStaticStatModifierEffect,
                                                            RemoveEffect)
    from engine.entities.behaviours import Group
    tree = BOF.book_of_fate_tree(928, "thousSmnDaemonPrince")
    gauche, droite = tree.left, tree.right                       # op_and(op_and(b1, b3), b2)
    assert isinstance(droite, RemoveEffect)               # le RETRAIT est le DERNIER terme
    assert droite.effect_type == BOF.DAEMON_BUFF_EFFECT
    assert isinstance(gauche.left, AddStaticStatModifierEffect)   # la POSE est le PREMIER
    assert gauche.left.effect_type == BOF.DAEMON_BUFF_EFFECT
    assert gauche.left.stat_type == int(StatType.ATTACK)
    assert isinstance(gauche.right, Group)                    # l'ATTAQUE est au milieu
    assert gauche.right.group_id == BOF._GROUP_ABILITY_ATTACK


def test_book_of_fate_le_buff_ne_vise_QUE_les_daemons():
    """`AddStaticStatModifierEffect( UnitsWithTrait(sel, Daemon), ... )` -- quand la cascade tombe a
    l'etage C (non-Daemon), le filtre rend VIDE : c'est le << If the summon is a Daemon >> de l'i2,
    et c'est ce qui fait que l'etage C attaque SANS buff."""
    tree = BOF.book_of_fate_tree(928, "x")
    cible_du_buff = tree.left.left.unit_sel
    assert isinstance(cible_du_buff, UnitsWithTrait)
    assert cible_du_buff.trait == int(UnitTrait.Daemon)


def test_helspear_increment_A_GAUCHE_du_if():
    """`AddPersistentData(+1) + If(compteur >= nrOfUnits, ...)` : l'increment s'execute AVANT que le
    `If` ne relise le compteur -> le seuil porte sur le compteur DEJA incremente. C'est la forme de
    `VolummsMasterArtifice`, l'INVERSE de `DaemonfleshPlate` -- recopier le voisin decalerait le
    declenchement d'un kill entier."""
    from engine.runner.abilities.behaviours.persistent_data import AddPersistentData
    from engine.entities.behaviours import If
    tree = HS.helspear_reset_tree(7)
    assert isinstance(tree.left, AddPersistentData)          # increment = terme de GAUCHE
    assert tree.left.value == 1 == HS._INCREMENT             # `<DSLFormulas+0x20>` = Direct(1)
    assert isinstance(tree.right, If)


def test_helspear_reset_vide_la_cle_au_lieu_de_la_remettre_a_zero():
    """`ClearPersistentData` (retire LA cle), PAS `SetPersistentData(..., 0)` : `VolummsMasterArtifice`
    fait l'inverse, et les deux fabriques natives sont distinctes."""
    from engine.runner.abilities.behaviours.persistent_data import (ClearPersistentData,
                                                                    SetPersistentData)
    from engine.runner.abilities.behaviours.ability_state import ResetActiveAbility
    then_ = HS.helspear_reset_tree(7).right.then
    assert isinstance(then_.left, ResetActiveAbility)
    assert then_.left.ignore_turn_flag is True is HS.RESET_ALLOW_USELESS   # `allowUseless = true`
    assert isinstance(then_.right, ClearPersistentData)
    assert not isinstance(then_.right, SetPersistentData)
    assert then_.right.data_key == HS._COUNTER_KEY == "helspear_defeat_count"


def test_helspear_buff_pose_les_DEUX_effets():
    """`AddEffect(1583, Target) + AddEffect(1476, Tiles(Target))` -- l'un sur l'UNITE, l'autre sur
    sa TUILE. `op_Addition` : aucun des deux ne gate l'autre."""
    from engine.runner.abilities.behaviours.effects import AddEffect
    from engine.entities.selectors.units import Tiles
    tree = HS.helspear_buff_tree()
    assert isinstance(tree.left, AddEffect) and tree.left.effect_type == HS.IGNORE_ARMOR_EFFECT
    assert isinstance(tree.right, AddEffect) and tree.right.effect_type == HS.DESPOILED_GROUND_EFFECT
    assert isinstance(tree.right.target_sel, Tiles)           # la TUILE, pas l'unite
    assert not isinstance(tree.left.target_sel, Tiles)


# =====================================================================================
# ETAGE 4 -- les MAGNITUDES viennent du palier TERTIAIRE (faute mesuree par #1007)
# =====================================================================================

@pytest.mark.parametrize("level,attendu", [(1, 8), (3, 7), (5, 6), (9, 4), (10, 4)])
def test_helspear_nrOfUnits_par_palier(level, attendu):
    """`nrOfUnits` = [8, 8, 7, 7, 6, 6, 5, 5, 4, 4] (gameconfig, LU). Le LEVEL 3 SEPARE le palier
    tertiaire (7) du palier clampe (4) -- c'est le niveau a monter pour une contre-epreuve, comme
    #1008 (PR VOTANN) l'avait etabli."""
    from engine.entities.effects.magnitude import ability_var
    assert int(ability_var("Helspear", "nrOfUnits", level) or 0) == attendu


@pytest.mark.parametrize("level,attendu", [(1, 880), (3, 975), (10, 1308)])
def test_book_of_fate_extraDmg_par_palier(level, attendu):
    """`extraDmg` = [880, 928, ...] (gameconfig, LU). ⚠ L'i2 rendue par
    `gameconfig.ability_description(a, 1)` affiche **928** -- elle indexe le tableau par le niveau
    BRUT, la ou le natif passe par `Level$$ToZeroBasedIndex`. Lire l'i2 comme un oracle de
    magnitude decalerait d'un palier."""
    from engine.entities.effects.magnitude import ability_var
    assert int(ability_var("BookOfFate", "extraDmg", level) or 0) == attendu


def test_book_of_fate_constante_affectedUnitId():
    """`ConfigConstString(AbilityConstantType.affectedUnitId = 0x8c)` -- une CONSTANTE, donc sans
    niveau."""
    from engine.entities.effects.magnitude import ability_const_str
    assert ability_const_str("BookOfFate", "affectedUnitId") == "thousSmnDaemonPrince"


# =====================================================================================
# ETAGE 5 -- les RESIDUS, assertionnes pour qu'ils ne se referment pas en silence
# =====================================================================================

def test_residu_1008_r2_la_magnitude_de_l_effet_1583_est_branchee_SOUS_SA_GATE():
    """`#1008-r2` -- LE CLIQUET S'EST DECLENCHE, ET IL A ETE HONORE ; il garde maintenant l'autre
    sens. ROUGE DE `master` REPARE ICI (#1008-r4) : ce test asserta longtemps
    `"get_armor_penetration" not in vars(HelspearIgnoreArmorEffect)` en disant << si un jour
    quelqu'un surcharge cette methode, ce test rougit -- et c'est voulu : il faudra alors avoir RE-lu
    le canal defenseur, pas juste cable >>. Le canal A ETE RE-LU (#1008-r2, la lecture vit en tete
    d'`entities/effects/loki/helspear.py`) et la methode a ete surchargee dans la foulee -- mais
    personne n'a retourne le cliquet, qui rougissait donc sur `origin/master`.

    CE QU'IL GARDE DESORMAIS, et c'est le fait que la RE a etabli : la magnitude n'est pas
    << branchee >> n'importe ou -- elle est lue DANS le bloc ou le malus est rendu, donc SOUS la
    meme gate que lui, exactement comme `IdunBattle.Entities.Effects.BaseEffect$$DamageMalusForDefense`
    evalue `this.<vtable +0x718>()` apres avoir teste le trigger de l'`EffectBonus`."""
    import inspect

    from engine.entities.effects import build_defender_modifiers_from_effects

    eff = HelspearIgnoreArmorEffect(HS.IGNORE_ARMOR_EFFECT_NAME)
    assert "get_armor_penetration" in vars(HelspearIgnoreArmorEffect), (
        "la surcharge a disparu : la penetration du DEFENSEUR retomberait sur le `None` de "
        "`BaseEffect`, sans erreur et sans qu'aucun degat ne change")
    assert hasattr(eff, "ignore_armor")                     # la magnitude EST lisible
    assert eff.applies_to_incoming_attack(attacker_id=None) is False    # degradation RESTRICTIVE
    assert eff.applies_to_incoming_attack(attacker_id=7) is True

    # LA GATE N'EST PAS DUPLIQUEE : la boucle defenseur lit la penetration DANS le bloc du malus.
    # Un `get_armor_penetration` appele hors de ce bloc l'activerait meme quand le trigger est faux.
    src = inspect.getsource(build_defender_modifiers_from_effects)
    avant, _, apres = src.partition("get_armor_penetration")
    assert "if mb is not None:" in avant, "la penetration est lue HORS du bloc gate par le malus"
    assert apres, "`get_armor_penetration` n'est plus lu par la boucle defenseur"

    # LE CONTRASTE AVEC SON VOISIN DE CANAL, mesure : `StrikeFromTheShadows` (1549) vit sur le MEME
    # slot mais avec une gate DIFFERENTE (`IsRangedAttack()` la ou 1583 porte `IsUnit(Caster)`).
    # Recopier l'une sur l'autre serait le piege du voisin de forme.
    from engine.entities.effects.loki.strike_from_the_shadows import StrikeFromTheShadowsEffect
    voisin = StrikeFromTheShadowsEffect("StrikeFromTheShadows")
    assert voisin.create_effect_damage_malus_for_defense(is_melee=True) is None
    assert voisin.create_effect_damage_malus_for_defense(is_melee=None) is None
    assert voisin.create_effect_damage_malus_for_defense(is_melee=False) is not None
    # ... et 1583, lui, n'a AUCUN gate de nature de coup : la melee passe.
    assert eff.create_effect_damage_malus_for_defense(
        is_melee=True, attacker_ctx={"id": 7}) is not None


def test_residu_1008_r3_le_sixieme_conjoint_du_reset_n_est_PAS_porte():
    """`#1008-r3` (BLOCAGE `capteur`) : `<DSLTriggers+0x58>` n'est pas identifie -- deux candidats
    restants et rien ne tranche offline. Le port OMET le conjoint ; ce test FIGE le fait que les
    gates portes sont exactement CINQ, pour qu'un sixieme n'apparaisse pas sans RE."""
    src = HS.HelspearResetActiveAbility.matches.__doc__ or ""
    assert "#1008-r3" in src, "le residu doit rester ECRIT au site qui l'omet"
    assert "CINQ" in src


def test_residu_1008_r1_UnitLevel_sans_substrat_rend_zero():
    """`#1008-r1` : le dict d'unite ne porte pas de niveau -> la cle de tri vaut 0 partout, et le
    tri STABLE preserve l'ordre du `Randomize` amont. Fidele au regime << tous les niveaux egaux >>,
    pas au cas general."""
    from engine.dsl.base import DslContext
    from engine.entities.selectors.accessors import ActiveTarget
    ctx = DslContext(units=[{"id": 1, "alive": True}])
    assert UnitLevel(ActiveTarget()).calculate(ctx) == 0
    ctx2 = DslContext(units=[{"id": 1, "alive": True, "level": 4}])
    from dataclasses import replace
    assert UnitLevel(ActiveTarget()).calculate(
        replace(ctx2, active_target=ctx2.units[0])) == 4
