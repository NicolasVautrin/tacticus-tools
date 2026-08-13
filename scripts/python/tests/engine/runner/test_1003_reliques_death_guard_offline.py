"""#1003 -- CLIQUET OFFLINE du couple de reliques DEATH GUARD : `OrbsOfDecay` (1465) et
`Lakrimae` (1541, volet `AddContamination`).

CE QUE CE FICHIER GARDE, ETAGE PAR ETAGE -- et pourquoi chaque bras est DISCRIMINANT :

 1. ORDINAUX FIGES A LA CONVERSION. `probe_313` compare le MIRROR au BUILD ; il redevient vert des
    qu'on regenere un mirror apres un renumerotage, alors que la valeur ECRITE au site, elle, a
    change. Ce fichier fige les ordinaux MESURES le 2026-08-13 sur `rnca9r7q6c`.
 2. LES DEUX CONSTANTES DE CONFIG relues du gameconfig VIVANT (`armorReductionPct`, `nrOfHits`,
    `damageProfile`, `attackRangeType`, `unitId`, `nrOfUnits`). `build: True` : c'est justement ce
    que ce fichier doit rougir a un changement de build.
 3. LE PREDICAT `OrbsOfDecayAbility$$GetTriggerForAttack`, avec SON cas discriminant :
    `AmountIsGreater` est **STRICT**. Une armure reduite d'EXACTEMENT `armorReductionPct` % n'est
    PAS retenue -- et ce n'est pas academique, `ContaminatedStatModifierEffect` pose exactement
    `-30 %`. Un mirror qui aurait ecrit `AmountIsEqualOrGreater` (l'autre classe native, meme
    ctor mislabel) passerait tous les autres bras.
 4. `StatNegativeModification` != `StatAmount(part 5 = MODIFICATION)`. Le bras `-40 / +40` separe
    les deux : la formule native n'accumule QUE les contributions negatives, en valeur absolue,
    donc `40` -- la ou le total signe rend `0`. C'est la seule chose qui distingue la formule
    NEUVE de celle qui existait deja.
 5. LA CIBLE N'EST PAS FRAPPEE par le volet ABILITY. `AdjacentTilesSelector$$Select` exclut ses
    tuiles d'origine, donc `AdjacentEnemies(Owner, TargetTiles, unique)` ne contient PAS l'unite
    de la tuile-cible. L'i2 (« on **or** adjacent to the target's hex ») decrit les DEUX classes
    natives de 1465 ; le « on » vit dans l'effet 1463, NON porte (residu `#1003-r1`). Ce bras
    empeche qu'on « corrige » le port vers l'i2.
 6. LES DEUX `AddEffect(Contaminated)` DIFFERENT PAR LEUR SOURCE, et c'est une surcharge native
    differente : `OrbsOfDecay` appelle la 5-args (source litteralement `0` -> chaque TUILE est sa
    propre source), `Lakrimae_AddContamination` la 6-args avec `source = Owner@+0x30`. Deux
    abilities Death Guard, meme effet, meme geometrie, attribution OPPOSEE.
 7. `level_slot="tertiary"` LIT LE COUPLE TERTIAIRE. Le bras compare le meme etat avec et sans
    `tertiary_ability` : la relique de niveau 3 doit rendre `minDmg[3]`, pas `minDmg[dernier]`.
 8. LES GATES DE `matches`. `OrbsOfDecay` n'a **AUCUN** `IsNormalAttack` (contraste LU avec 1316
    sur le MEME evenement) ; `Lakrimae_AddContamination` en a un, et refuse le RANGED.
 9. NI 1465 NI 1541 N'ENTRENT DANS `ABILITY_CLASSES`. Mesure du gisement : les 21 abilities de
    relique voie `item` non portees sont **21/21** des `TriggeredAbilityType`, ZERO active -- donc
    ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` ne les concernent. Deux tranches ont ete
    briefees a tort la-dessus ; ce bras rend le fait executable.

OFFLINE : ce fichier ne monte AUCUN runner. La confrontation LIVE (montage `--equip-relic`,
contamination observee, splash sur voisin a l'armure reduite) vit dans
`test_1003_reliques_death_guard_live.py`.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

_PYDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PYDIR not in sys.path:
    sys.path.insert(0, _PYDIR)

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test : la cascade des `conftest.py` et ses gardes.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LES DEUX MIRRORS et leur inscription au registre : l'objet meme du cliquet.
        "scripts/python/engine/runner/operations/triggers/loki/orbs_of_decay.py",
        "scripts/python/engine/runner/operations/triggers/loki/lakrimae.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/core.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        # LA FORMULE NEUVE et son substrat -- les deux points ou l'etage 4 peut redevenir muet.
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/entities/stats.py",
        "scripts/python/engine/dsl/base.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        # LES FEUILLES DSL dont ce fichier fige les parametres (source de l'effet, level_slot).
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        "scripts/python/engine/runner/abilities/base.py",
        # LES SELECTEURS de l'etage 5 (l'exclusion de la tuile d'origine).
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        # LES ENUMS dont ce fichier fige les ordinaux.
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        # LE REGISTRE DES ACTIVES, dont l'etage 9 mesure l'ABSENCE des deux ids.
        "scripts/python/engine/runner/abilities/handler.py",
        # LA LECTURE DU GAMECONFIG (etage 2).
        "scripts/python/gameconfig.py",
        "scripts/python/engine/entities/effects/magnitude.py",
    ),
    # `build: True` -- les constantes de 1465/1541 et les ordinaux des cinq enums sont relus du
    # build vivant : un changement de build peut les deplacer, et c'est ce qu'on veut voir rougir.
    "build": True,
    "toujours": False,
    "raison": (
        "Ce fichier garde le port des deux reliques Death Guard `OrbsOfDecay` (TriggeredAbilityType "
        "1465) et `Lakrimae` (1541, volet AddContamination) : leur inscription dans "
        "`RELIC_ABILITY_TRIGGERS`, les ordinaux figes a la conversion, le predicat STRICT d'armure "
        "reduite, la formule neuve `StatNegativeModification`, l'exclusion de la tuile-cible du "
        "volet splash, et l'attribution OPPOSEE des deux `AddEffect(Contaminated)`."),
}

import gameconfig as GC                                                    # noqa: E402
from engine.dsl.base import Const, DslContext                              # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                 # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.formulas import StatAmount, StatNegativeModification  # noqa: E402
from engine.entities.selectors.accessors import Owner, TargetTile          # noqa: E402
from engine.entities.selectors.units import AdjacentEnemies, Filter        # noqa: E402
from engine.entities.stats import (StatComponent, StatPart, StatType,      # noqa: E402
                                   UnitStats)
from engine.entities.triggered_ability_type import TriggeredAbilityType    # noqa: E402
from engine.entities.unit_selection_type import UnitSelectionType          # noqa: E402
from engine.runner.abilities.base import ability_attack_params             # noqa: E402
from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage  # noqa: E402
from engine.runner.abilities.behaviours.effects import AddEffect           # noqa: E402
from engine.runner.operations.triggers.base import TriggerEvent            # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import (          # noqa: E402
    RELIC_ABILITY_TRIGGERS)
from engine.runner.operations.triggers.loki import lakrimae as LK          # noqa: E402
from engine.runner.operations.triggers.loki import orbs_of_decay as OD     # noqa: E402


# ----------------------------------------------------------------- 1. ordinaux figes a la conversion
def test_1003_ordinaux_figes():
    """Les ordinaux ECRITS aux deux sites, tels que MESURES sur `rnca9r7q6c` le 2026-08-13.

    `probe_313` garde la bijection mirror<->build ; il ne garde PAS ce que le SITE a ecrit. Un
    renumerotage suivi d'une regeneration du mirror le laisse VERT et deplace la valeur du site en
    silence -- le cran manquant, et c'est ce bras."""
    assert int(TriggeredAbilityType.OrbsOfDecay) == 1465    # 0x5b9
    assert int(TriggeredAbilityType.Lakrimae) == 1541       # 0x605
    assert int(EffectType.Contaminated) == 1244             # 0x4dc
    assert int(EventTriggerType.AttackInAtomicGroup) == 74  # 0x4a
    assert int(EventTriggerType.NormalAttack) == 38         # 0x26
    assert int(StatType.FIXED_ARMOR) == 16                  # 0x10
    assert int(StatPart.INITIAL) == 3
    assert int(UnitSelectionType.OnlyAliveAndTargetable) == 3
    # Les DEUX classes portees citent bien l'id qu'elles pretendent.
    assert OD.OrbsOfDecayAbility.TRIGGERED_ABILITY_ID == int(TriggeredAbilityType.OrbsOfDecay)
    assert LK.LakrimaeAddContaminationAbility.TRIGGERED_ABILITY_ID == int(
        TriggeredAbilityType.Lakrimae)


# --------------------------------------------------------------- 2. constantes du gameconfig VIVANT
def test_1003_constantes_gameconfig():
    """`GetNumberConstant`/`GetStringConstant` des deux abilities, RELUS. Les valeurs attendues sont
    celles du build `rnca9r7q6c` ; elles sont ce que le port ECRIT dans ses arbres."""
    od = GC.ability("OrbsOfDecay") or {}
    cst = od.get("constants") or {}
    assert cst.get("armorReductionPct") == "30", cst        # `ConfigConst(0x83)`
    assert cst.get("nrOfHits") == "2", cst                  # `ConfigConst(0x2f)`
    assert cst.get("damageProfile") == "Toxic", cst         # `GetDamageProfile()`
    # `attackRangeType` de 1465 = **Ranged** : c'est ce que le port ecrit en `is_melee=False`, alors
    # meme que le trigger exige `IsMeleeAttack` sur l'attaque DECLENCHANTE. Deux litteraux LUS, et
    # ce n'est pas le meme.
    assert od.get("attackRangeType") == "Ranged", od
    assert OD.DAMAGE_PROFILE == "Toxic" and OD.armor_reduction_pct() == 30
    # Les paliers de degat existent bien a 10 crans (niveaux de RELIQUE 1..10) -- ce qui rend le
    # `level_slot="tertiary"` de l'etage 7 OBSERVABLE.
    assert len((od.get("variables") or {}).get("minDmg") or []) == 10, od

    lk = GC.ability("Lakrimae") or {}
    lcst = lk.get("constants") or {}
    assert lcst.get("unitId") == "deathPoxwalker", lcst     # `GetStringConstant(0x0)`
    assert lcst.get("nrOfUnits") == "3", lcst               # `GetNumberConstant(0x78)`


# --------------------------------------------------------------------------- 3+9. le registre
def test_1003_registre_relique():
    """`RELIC_ABILITY_TRIGGERS` est indexe par le NOM gameconfig (le natif monte la relique par
    `BC.Units[].TertiaryAbility`, une CHAINE). Les deux cles doivent y etre, avec EXACTEMENT les
    classes portees -- ni plus (une entree vide serait un mensonge de couverture), ni moins."""
    assert RELIC_ABILITY_TRIGGERS.get("OrbsOfDecay") == [OD.OrbsOfDecayAbility]
    assert RELIC_ABILITY_TRIGGERS.get("Lakrimae") == [LK.LakrimaeAddContaminationAbility]
    # Temoin NON NUL : le registre porte aussi les entrees preexistantes (un dict vide passerait).
    assert "DawnBlade" in RELIC_ABILITY_TRIGGERS and len(RELIC_ABILITY_TRIGGERS) >= 4


def test_1003_ni_active_ni_masque_de_ciblage():
    """MESURE du gisement (2026-08-13) : les abilities de relique de la voie `item` sont des
    `TriggeredAbilityType`, PAS des actives. Ni 1465 ni 1541 n'entrent donc dans `ABILITY_CLASSES`,
    et ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` ne les concernent.

    Ce bras existe parce que l'erreur inverse a ete commise : deux tranches ont ete briefees pour
    poser un masque de ciblage sur une relique. Il rend le fait EXECUTABLE au lieu d'ecrit."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    assert len(ABILITY_CLASSES) > 50, "registre des ACTIVES vide/ampute -- il ne peut rien garder"
    assert int(TriggeredAbilityType.OrbsOfDecay) not in ABILITY_CLASSES
    assert int(TriggeredAbilityType.Lakrimae) not in ABILITY_CLASSES
    # Et les deux noms ne sont PAS des actives du build (la voie ne dit pas l'enum, le NOM si).
    assert not hasattr(ActiveAbilityType, "OrbsOfDecay")
    assert not hasattr(ActiveAbilityType, "Lakrimae")


# ------------------------------------------ 4. le predicat d'armure reduite, et sa STRICTESSE
def _ctx_avec_armure(initial: int, mods: "dict"):
    """`DslContext` minimal ou le SUJET porte `initial` de `FIXED_ARMOR` et les modifications
    per-source `mods` (`{source: montant}`). Les deux accesseurs sont ceux que le runner pose."""
    comp = StatComponent(initial=int(initial), min_value=0)
    for src, amount in mods.items():
        comp.modification.modify(src, int(amount))
    us = UnitStats({int(StatType.FIXED_ARMOR): comp})
    sujet = {"id": 7, "pos": {"col": 1, "row": 1}, "team": 1, "alive": True, "hp": 10}

    def _get_stat(u, stat_type, part=0, level=None):
        return us.get_stat(stat_type, part) if (u or {}).get("id") == 7 else 0

    def _neg(u, stat_type):
        return us.negative_stat_modification(stat_type) if (u or {}).get("id") == 7 else 0

    return DslContext(units=[sujet], caster=None, target=None, subject=sujet,
                      get_stat=_get_stat, negative_stat_modification=_neg), us


@pytest.mark.parametrize("initial,mods,attendu", [
    # ratio = 0 -> refuse (aucune reduction).
    (1000, {}, False),
    # ratio = EXACTEMENT 30 -> **REFUSE**. `AmountIsGreater` est STRICT ; c'est precisement ce que
    # pose `ContaminatedStatModifierEffect` (-`ContaminatedArmorReductionPct` = -30 %).
    (1000, {"contaminated": -300}, False),
    # ratio = 30.1 -> arrondi Fix64 half-to-even du `Divide` -> 30 -> encore REFUSE. Le seuil mord
    # sur la valeur ARRONDIE, pas sur le rationnel.
    (1000, {"contaminated": -301}, False),
    # ratio = 30.5 -> half-to-even -> 30 -> refuse (le bras qui EXERCE l'arrondi pair).
    (1000, {"contaminated": -305}, False),
    # ratio = 31 -> retenu.
    (1000, {"contaminated": -310}, True),
    # DEUX sources qui s'ADDITIONNENT (Contaminated + une aura ContagionsOfNurgle) -> 45 % -> retenu.
    (1000, {"contaminated": -300, "aura": -150}, True),
    # armure de BASE nulle -> `AmountIsGreaterThanZero` faux -> refuse SANS evaluer le `Divide`
    # (court-circuit du `op_BitwiseAnd`, la seule raison pour laquelle le natif divise sans garde).
    (0, {"contaminated": -300}, False),
])
def test_1003_predicat_armure_reduite(initial, mods, attendu):
    """`...OrbsOfDecayAbility$$GetTriggerForAttack` -- le denominateur est `StatPart.INITIAL`
    (l'armure de BASE), le numerateur la SOMME des reductions, et la comparaison est STRICTE."""
    ctx, _us = _ctx_avec_armure(initial, mods)
    assert bool(OD.orbs_of_decay_trigger_for_attack().evaluate(ctx)) is attendu


def test_1003_stat_negative_modification_nest_pas_le_total_signe():
    """LE BRAS DISCRIMINANT DE LA FORMULE NEUVE. `-40` compense par `+40` :
      * `StatNegativeModification` (natif `NegativeStatModificationFormula`) rend **40** ;
      * `StatAmount(part 5 = MODIFICATION)` rend **0**.
    Ecrire la seconde a la place de la premiere aurait ete invisible sur tout cas a une seule
    source -- et rend le predicat d'armure MUET des qu'un buff d'armure coexiste."""
    ctx, us = _ctx_avec_armure(1000, {"debuff": -40, "buff": +40})
    assert us.negative_stat_modification(int(StatType.FIXED_ARMOR)) == 40
    assert us.get_stat(int(StatType.FIXED_ARMOR), int(StatPart.MODIFICATION)) == 0
    assert StatNegativeModification(OD.Subject(), int(StatType.FIXED_ARMOR)).evaluate(ctx) == 40
    assert StatAmount(OD.Subject(), int(StatType.FIXED_ARMOR),
                      int(StatPart.MODIFICATION)).evaluate(ctx) == 0
    # ... et l'accesseur ABSENT degrade a 0 (donc gate FAUX = RESTRICTIF, jamais permissif).
    nu = DslContext(units=[], caster=None, target=None, subject={"id": 7})
    assert StatNegativeModification(OD.Subject(), int(StatType.FIXED_ARMOR)).evaluate(nu) == 0


# ------------------------------------- 5. la CIBLE n'est PAS dans le selecteur du volet ABILITY
def test_1003_la_cible_nest_pas_frappee_par_le_volet_ability():
    """`AdjacentEnemies(Owner@+0x30, TargetTiles@+0x78, unique)` = variante B =
    `Enemies(unit, Units(AdjacentTiles(unitTile), unique, 3) - unitTile, 3)`, et
    `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` EXCLUT ses tuiles d'origine.
    Donc l'unite qui OCCUPE la tuile ciblee n'est pas dans l'ensemble.

    ⚠ CE BRAS EXISTE CONTRE L'i2, qui dit « on **or** adjacent to the target's hex ». Le « on » est
    l'autre classe native de 1465 (`OrbsOfDecay_AdditionalHitsEffect`, effet 1463, canal
    `additional_hit_groups`), NON portee -- residu `#1003-r1`. Aligner le selecteur sur l'i2 serait
    une faute de lecture, et c'est ici que ca doit rougir."""
    def U(i, c, r, t):
        return {"id": i, "pos": {"col": c, "row": r}, "team": t, "alive": True, "hp": 10}
    porteur, cible, voisin, loin, allie = U(1, 3, 3, 0), U(2, 4, 3, 1), U(3, 4, 4, 1), U(4, 9, 9, 1), U(5, 3, 4, 0)
    ctx = DslContext(units=[porteur, cible, voisin, loin, allie], caster=porteur, target=cible)
    sel = AdjacentEnemies(TargetTile(), Const(1),
                          selection_type=int(UnitSelectionType.OnlyAliveAndTargetable))
    ids = sorted(u["id"] for u in sel.evaluate(ctx))
    assert ids == [3], ("le selecteur doit rendre le SEUL voisin ennemi de la tuile ciblee : "
                        "ni la cible (2), ni l'unite lointaine (4), ni l'allie adjacent (5)")


def test_1003_larbre_est_un_filter_sur_ce_selecteur():
    """L'arbre PORTE est bien `Filter(<ce selecteur>, <le predicat>)` -- pas du ciblage recable a la
    main dans l'`execute_behaviour` (doctrine #149 : le natif est un `DSLSelectors$$Filter`)."""
    cibles = OD.orbs_of_decay_targets()
    assert isinstance(cibles, Filter)
    assert isinstance(cibles.source, AdjacentEnemies)
    assert isinstance(cibles.source.center, TargetTile)
    assert cibles.source.selection_type == int(UnitSelectionType.OnlyAliveAndTargetable)


# ------------------------------------- 6. les DEUX AddEffect(Contaminated) et leur SOURCE opposee
def _feuilles(tree):
    """Aplatit un arbre `Seq` (`op_and`, slots `left`/`right`) en la liste ORDONNEE de ses feuilles."""
    left, right = getattr(tree, "left", None), getattr(tree, "right", None)
    if left is None and right is None:
        return [tree]
    return _feuilles(left) + _feuilles(right)


def test_1003_les_deux_contaminations_nont_pas_la_meme_source():
    """LA SURCHARGE NATIVE DIFFERE, ET C'EST OBSERVABLE :
      * `OrbsOfDecay` appelle la 5-args `DSLBehaviors$$AddEffect(effectType, abilityState, targets,
        turns)`, dont le corps passe litteralement `0` en SOURCE -> `AddEffectBehaviour$$Execute`
        rabat sur « la source EST la cible » -> `source_from_target=True` ;
      * `Lakrimae_AddContamination` appelle la 6-args avec `source = Owner@DSLSelectors+0x30`
        -> `source_ref=Owner()`.
    Confondre les deux poserait le MEME effet avec une ATTRIBUTION differente, en silence."""
    od_eff = [f for f in _feuilles(OD.orbs_of_decay_tree()) if isinstance(f, AddEffect)]
    assert len(od_eff) == 1
    assert od_eff[0].effect_type == int(EffectType.Contaminated)
    assert od_eff[0].source_from_target is True and od_eff[0].source_ref is None
    assert isinstance(od_eff[0].target_sel, TargetTile)     # `targets = TargetTiles@+0x78`
    assert od_eff[0].duration_rounds is None                # `turns = null` -> DefaultAmountOfRounds

    lk_eff = LK.lakrimae_add_contamination_tree()
    assert isinstance(lk_eff, AddEffect)
    assert lk_eff.effect_type == int(EffectType.Contaminated)
    assert isinstance(lk_eff.source_ref, Owner) and lk_eff.source_from_target is False
    assert isinstance(lk_eff.target_sel, TargetTile)
    assert lk_eff.duration_rounds is None


def test_1003_la_feuille_dattaque_porte_les_litteraux_lus():
    """`AttackWithAttackDamage(..., MinMaxDamage, GetDamageProfile, GetHits, ..., selectionType 2)`."""
    att = [f for f in _feuilles(OD.orbs_of_decay_tree())
           if isinstance(f, AttackWithAttackDamage)]
    assert len(att) == 1
    a = att[0]
    assert a.ability_id == "OrbsOfDecay" and a.profile == "Toxic"
    assert a.is_melee is False        # `attackRangeType` = Ranged (etage 2)
    assert a.multi is True            # le natif passe un SELECTEUR multi-cible
    assert a.level_slot == "tertiary"  # relique EQUIPEE -> `TertiaryAbilityLevel`
    assert a.native_factory == "attack"  # `DSLBehaviors$$AttackWithAttackDamage`, pas `AbilityDamage`
    assert a.hits_key == "nrOfHits"   # `GetHits()` = `ConfigConst(0x2f)`
    assert a.ability_type == int(TriggeredAbilityType.OrbsOfDecay)  # `AbilityOrEffect(this)`
    # ORDRE de l'`op_BitwiseAnd` natif : l'attaque D'ABORD, la contamination ENSUITE.
    feuilles = _feuilles(OD.orbs_of_decay_tree())
    assert isinstance(feuilles[0], AttackWithAttackDamage)
    assert isinstance(feuilles[-1], AddEffect)


# ---------------------------------------------------- 7. `level_slot="tertiary"` lit le bon couple
class _Ctx:
    def __init__(self, **kw):
        self.passive_ability_level = kw.get("passive_ability_level")
        self.active_ability_level = kw.get("active_ability_level")
        self.ability_variables_multiplier = kw.get("ability_variables_multiplier", 100)
        self.tertiary_ability = kw.get("tertiary_ability")
        self.tertiary_ability_level = kw.get("tertiary_ability_level", 0)
        self.tertiary_ability_variables_multiplier = kw.get(
            "tertiary_ability_variables_multiplier", 100)
        self.extra_pierce = 0
        self.extra_pierce_melee = 0
        self.extra_pierce_ranged = 0


class _Sc:
    def __init__(self, ctx):
        self.ctx = ctx


class _Ent:
    def __init__(self, sc):
        self._sc = sc

    def get_component(self, _cls):
        return self._sc


class _State:
    def __init__(self, ent):
        self._ent = ent

    def get_entity(self, _uid):
        return self._ent


def _params(ctx, slot):
    return ability_attack_params(_State(_Ent(_Sc(ctx))), 1, "OrbsOfDecay", "Toxic",
                                 level_slot=slot)


def test_1003_level_slot_tertiary_lit_le_niveau_de_la_relique():
    """`MinMaxDamage` se resout contre l'`abilityState` sous lequel l'ability est MONTEE. Une
    relique EQUIPEE arrive par la branche TERTIAIRE d'`UnitFactory$$AddConfiguredAbilities`.

    Le bras est DISCRIMINANT : le meme etat, lu au slot PASSIF (50 dans tout runner normalise),
    rend le DERNIER palier de `minDmg` ; lu au slot TERTIAIRE (niveau 3) il rend `minDmg[3]`. Sans
    ce slot, une relique de niveau 3 tapait au niveau 10 -- l'ecart silencieux que #357 a ferme
    pour `DawnBlade`, et qui se rouvrait ici sur le canal DEGAT."""
    paliers = ((GC.ability("OrbsOfDecay") or {}).get("variables") or {}).get("minDmg") or []
    assert len(paliers) == 10, "premisse : `minDmg` a 10 paliers"

    ctx = _Ctx(passive_ability_level=50, active_ability_level=50,
               tertiary_ability="OrbsOfDecay", tertiary_ability_level=3)
    bmin_t, bmax_t, _p, hits = _params(ctx, "tertiary")
    bmin_p, _bmaxp, _p2, _h2 = _params(ctx, "passive")
    assert bmin_t == paliers[2], (bmin_t, paliers[:4])      # `ToZeroBasedIndex(3)` = 2
    assert bmin_p == paliers[-1], (bmin_p, paliers[-1])     # niveau 50 -> clamp dernier palier
    assert bmin_t != bmin_p, "le bras ne discrimine RIEN si les deux paliers coincident"
    assert bmax_t > bmin_t and hits == 2                    # `GetHits()` = nrOfHits = 2

    # REPLI FIDELE : la MEME ability montee AILLEURS que sur le slot tertiaire (relique cablee au
    # kit d'un npc, ou canal tertiaire non fourni) retombe sur l'etat PASSIF -- mirror du choix de
    # `UnitFactory$$Build`, porte par `triggered_ability_state`.
    ctx_sans = _Ctx(passive_ability_level=50, active_ability_level=50, tertiary_ability=None)
    assert _params(ctx_sans, "tertiary")[0] == paliers[-1]


# ----------------------------------------------------------------------------- 8. les gates
def _ev(event, actor, target, ranged, **kw):
    return TriggerEvent(int(event), actor, target, ranged=ranged, profile="Toxic", **kw)


def test_1003_gates_orbs_of_decay():
    """`On(0x4a) & get_OwnerIsCaster & IsMeleeAttack` -- et **AUCUN** `IsNormalAttack`."""
    ab = OD.OrbsOfDecayAbility(owner_id=11)
    ev_ok = _ev(EventTriggerType.AttackInAtomicGroup, 11, 22, False)
    assert ab.matches(None, ev_ok) is True
    # `get_OwnerIsCaster` : un autre acteur ne declenche rien.
    assert ab.matches(None, _ev(EventTriggerType.AttackInAtomicGroup, 33, 22, False)) is False
    # `IsMeleeAttack` : le coup RANGED est refuse.
    assert ab.matches(None, _ev(EventTriggerType.AttackInAtomicGroup, 11, 22, True)) is False
    # PAS de gate `IsNormalAttack` : un coup d'ABILITY (kind explicitement non-normal) declenche
    # QUAND MEME -- contraste LU avec 1316, qui sur le MEME evenement en porte un.
    assert ab.matches(None, _ev(EventTriggerType.AttackInAtomicGroup, 11, 22, False,
                                is_normal_attack=False)) is True
    # cible absente -> rien (le behaviour n'a pas d'ancre geometrique).
    assert ab.matches(None, _ev(EventTriggerType.AttackInAtomicGroup, 11, None, False)) is False
    assert ab.event_id == int(EventTriggerType.AttackInAtomicGroup)


def test_1003_gates_lakrimae_add_contamination():
    """`On(0x26) & get_OwnerIsActor & IsMeleeAttack & IsNormalAttack`."""
    ab = LK.LakrimaeAddContaminationAbility(owner_id=11)
    assert ab.matches(None, _ev(EventTriggerType.NormalAttack, 11, 22, False)) is True
    assert ab.matches(None, _ev(EventTriggerType.NormalAttack, 33, 22, False)) is False
    assert ab.matches(None, _ev(EventTriggerType.NormalAttack, 11, 22, True)) is False
    # `IsNormalAttack` : un `False` EXPLICITE refuse ; `None` (non mesure sur ce vecteur, qui EST
    # celui de l'attaque normale) accepte.
    assert ab.matches(None, _ev(EventTriggerType.NormalAttack, 11, 22, False,
                                is_normal_attack=False)) is False
    assert ab.matches(None, _ev(EventTriggerType.NormalAttack, 11, 22, False,
                                is_normal_attack=True)) is True
    assert ab.event_id == int(EventTriggerType.NormalAttack)
