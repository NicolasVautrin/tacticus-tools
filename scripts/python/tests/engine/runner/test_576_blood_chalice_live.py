"""GARDE de `1175 BloodChalice` (#576) -- les TROIS mecaniques, et les DEUX effets qu'elle pose.

Avant #576 l'ability etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, donc la face
DECISION la choisissait (`playbook/bespoke.py::BloodChalicePlaybook`, portee depuis #82) et
l'execution l'ignorait -- 0 PV touche, 0 effet, AUCUNE erreur.

⚠ CE FICHIER GARDE D'ABORD UNE CATEGORIE, PAS UNE VALEUR. L'audit `combat-ability-coverage.md`
classe 1175 en `HEAL` (colonne derivee du `damageProfile` de l'ARME du porteur). Le volet 1 n'est
PAS un soin : c'est `ChangeStat(..., mode 0 = SetAbsolute, ...)`, et il fait **DESCENDRE** un allie
au-dessus du seuil. E2 est l'etage qui refute la lecture « HEAL » -- il exige une cible PLEINE, et
c'est le seul regime ou les deux lectures divergent.

Les six criteres vivent dans `probe_576_blood_chalice_live.py` (foyer unique -- ce fichier ne
duplique NI le montage NI les criteres, meme discipline que `test_510_light_of_sanguinius_live.py`).

Le montage EXIGE ses regimes ; s'il ne les obtient pas il ECHOUE, il ne skippe pas (#268) -- sauf
indisponibilite du host, qui n'est pas un verdict sur le port. ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des `conftest.py` et sa fermeture.
        # Elles portent des fixtures `autouse` dont le verdict de CHAQUE test depend, et aucun
        # test ne les IMPORTE (semantique pytest) -- donc aucun graphe d'imports ne les verrait.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER -- le probe qui porte le montage ET les criteres, et les deux probes
        # dont il tire ses helpers de runner :
        "scripts/python/probe_576_blood_chalice_live.py",
        "scripts/python/probe_112_darkangels.py",
        "scripts/python/probe_27_custom_utility_inventory.py",
        "scripts/python/rl_duel.py",
        # LE MOTEUR ENTIER, deliberement : le cast passe par `Runner.apply(ActiveAbilityMessage)`,
        # donc la fermeture MESUREE traverse la cascade de ciblage, la couche d'effets, le pipeline
        # de stat-mod et le PRNG -- tous capables de deplacer une valeur. Enumerer les seuls
        # fichiers de #576 serait DECLARER TROP ETROIT, et un declencheur trop etroit est un FAUX
        # VERT. ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un
        # segment, donc `engine/*.py` (racine du paquet) n'est PAS couvert par `engine/**/*.py`.
        "scripts/python/*.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        "scripts/python/tests/**/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le port de 1175 (arbre DSL `runner/abilities/bloodangels.py` : `SetHealth` sur le "
              "`ChangeStat` mode 0 SetAbsolute, `AddEffect` 1368, `AddStaticStatModifierEffect` "
              "1369 sur `StatType.ExtraPierceMelee`), les deux parametres `pct_rounding` / "
              "`pct_is_constant` de `SetHealth` (`runner/abilities/behaviours/stats.py`), les deux "
              "classes d'effet (`entities/effects/loki/blood_chalice.py`), le trigger de soin "
              "(`runner/operations/triggers/effect_triggers.py` + son registre) et le cablage "
              "(registre `ABILITY_CLASSES`, `ABILITY_ATTACK_TYPE`, masque et regle dynamique "
              "migres depuis `targeting.py`) -- plus tout le moteur que le cast traverse. "
              "`build: True` parce que E1 et E5 confrontent le NATIF au PV pres.",
}

import os
import sys

import pytest

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import probe_576_blood_chalice_live as P                          # noqa: E402


@pytest.fixture(scope="module")
def mesure():
    """UN seul montage par etage, joue une fois : le runner est cher. E1/E5 montent trois runners
    LEGERS (le `hp_max` doit VARIER pour isoler le SET du soin passif voisin), E2/E3/E4 un runner
    complet."""
    a = P._parser().parse_args([
        "--state-file", "t576_%d.json" % os.getpid(),             # isole par PID (probes en //)
    ])
    try:
        verdicts = P.mesure(a)
    except Exception as e:                                        # host injoignable != verdict
        pytest.skip("host/session indisponible (%s)" % (e,))
    if verdicts is None:
        pytest.skip("montage KO (build/session) -- pas un verdict sur le port")
    return verdicts


# ---------------------------------------------------------------- 0. le cablage, hors live

def test_le_cablage_du_registre_est_complet():
    """Une ability qui entre dans `ABILITY_CLASSES` pose son masque ET son `AbilityAttackType`
    DANS LE MEME COMMIT, et SORT des deux tables `_UNPORTED` (contrat de DISJONCTION : une ability
    a UNE source de masque, jamais deux). Sans masque, `get_invalid_target_reason` rend 0 et le
    moteur accepte des casts que `ActiveAbilityOperation$$IsInvalidTarget` REFUSE."""
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,
                                                   TARGETING_OPTIONS_UNPORTED,
                                                   RANGE_ADJACENT, RANGED_BOOL_FALSE)
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    bc = int(ActiveAbilityType.BloodChalice)                      # 1175
    cls = ABILITY_CLASSES.get(bc)
    assert cls is not None, "1175 absente d'ABILITY_CLASSES : c'est le NO-OP d'avant #576"
    assert bc not in TARGETING_OPTIONS_UNPORTED, (
        "1175 est portee ET encore dans TARGETING_OPTIONS_UNPORTED (disjonction rompue)")
    assert bc not in DYNAMIC_TARGET_RULE_UNPORTED, (
        "1175 est portee ET sa regle dynamique vit encore dans DYNAMIC_TARGET_RULE_UNPORTED : "
        "la classe la SURCHARGE desormais, les deux sources se contrediraient")
    opts = getattr(cls, "TARGETING_OPTIONS", None)
    assert opts is not None, "1175 au registre SANS masque = gate de ciblage DESARME"
    # `...BloodChaliceAbility$$.ctor` = `.ctor(&opts, 1, &<TargetingRange statics+0x30>, 1, 0xc02,
    # 0, 0)` -- forme FLAGS DIRECTS, le litteral EST le masque. La somme est EXHAUSTIVE.
    assert int(opts.rules) == int(TR.TargetMatchesDynamicRule | TR.TargetIsFriendly
                                  | TR.AddCasterIfAtLeastOneTarget)
    assert int(opts.rules) == 0xc02
    assert opts.self_cast is True
    assert opts.range == RANGE_ADJACENT
    assert opts.force_melee_target == RANGED_BOOL_FALSE
    # ⚠ PAS de `TargetIsHealable` : contraste avec 1002/1039, qui sont de VRAIS soins. Ici le gate
    # non-mecanique passe par la REGLE DYNAMIQUE seule, et c'est ce bit-la qui l'atteste.
    assert not (int(opts.rules) & int(TR.TargetIsHealable))
    # 3e argument d'`AActiveAbility$$.ctor`, TRANSCRIT (jamais deduit du profil de degat).
    assert ABILITY_ATTACK_TYPE.get(bc) == AbilityAttackType.Others
    # ... et le retrait des deux tables est CIBLE, pas un effacement.
    assert len(TARGETING_OPTIONS_UNPORTED) > 10
    assert len(DYNAMIC_TARGET_RULE_UNPORTED) >= 1

    # La surcharge de regle dynamique DOIT deleguer au mirror unique -- sur une cible NON adjacente
    # elle refuse (`TargetMatchesDynamicRule`), sur le caster lui-meme elle laisse passer.
    assert hasattr(cls, "get_dynamic_invalid_target_reason")


def test_les_deux_effets_sont_enregistres_et_portent_la_bonne_face():
    """1368 et 1369 doivent resoudre sur LEURS classes (un `BaseEffect` nu ne contribuerait RIEN),
    et le +percage de 1368 doit porter la face `OwnerIsCaster` -- l'INVERSE de son jumeau
    structurel `Supercharge_ExtraPiercing` (1208), qui gate sur `OwnerIsTarget`. Recopier le voisin
    aurait inverse la face sans rien casser d'autre."""
    from engine.entities.effect_type import EffectType
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki.blood_chalice import (BloodChaliceExtraPiercingEffect,
                                                            BloodChaliceHealOnAttackEffect)
    import gameconfig as GC

    assert EFFECT_CLASSES.get(EffectType.BloodChalice_HealOnAttack.name) is (
        BloodChaliceHealOnAttackEffect)
    assert EFFECT_CLASSES.get(EffectType.BloodChalice_ExtraPiercing.name) is (
        BloodChaliceExtraPiercingEffect)

    # Magnitude DERIVEE du gameconfig, jamais ecrite en dur ici.
    ratio = ((GC.ability("BloodChalice") or {}).get("variables") or {}).get("extraPierceRatio")
    assert ratio, "gameconfig sans `extraPierceRatio` : le port n'a plus de source"
    eff = BloodChaliceHealOnAttackEffect(name=EffectType.BloodChalice_HealOnAttack.name)
    eff.active_ability_level = 50            # `AbilityState` du POSEUR (`scale_from_source`)
    bonus = eff.create_piercing_bonus_for_attack(damage_profile=None, is_melee=True)
    assert bonus is not None, "1368 ne rend AUCUN bonus de percage en MELEE"
    assert bonus.kind == "Piercing"
    assert bonus.owner_is_caster is True, (
        "face INVERSEE : 1368 est sur l'unite QUI FRAPPE (get_OwnerIsCaster), pas sur la victime")
    assert int(bonus.value) == int(ratio[49])
    # Le SEUL gate natif est MELEE -- aucun `damageProfile` (contraste Supercharge).
    assert eff.create_piercing_bonus_for_attack(damage_profile=None, is_melee=False) is None
    assert eff.create_piercing_bonus_for_attack(damage_profile=None, is_melee=None) is None
    # 1369 n'expose PAS sa `CreateActiveCondition` (residu #576-r1 assume, cf. sa docstring) :
    # `active_condition_ported` DOIT rester False, sinon le defaut `is_active -> True`
    # transformerait un inerte capte en contributeur.
    assert BloodChaliceExtraPiercingEffect.active_condition_ported is False


def test_l_arbre_porte_les_trois_mecaniques_dans_l_ordre_natif():
    """`op_Addition(op_Addition(ChangeStat, AddEffect), AddStaticStatModifierEffect)` : TROIS
    feuilles, dans CET ordre. Un arbre a deux feuilles serait le port « HEAL » que l'audit
    annoncait."""
    from engine.entities.effect_type import EffectType
    from engine.entities.stats import StatType
    from engine.runner.abilities.behaviours.effects import AddEffect, AddStaticStatModifierEffect
    from engine.runner.abilities.behaviours.stats import SetHealth
    from engine.runner.abilities.bloodangels import blood_chalice_tree

    t = blood_chalice_tree(12)
    # `Seq(Seq(a, b), c)` -- l'associativite du natif est a GAUCHE (deux `op_Addition` chaines).
    assert type(t).__name__ == "Seq"
    assert type(t.left).__name__ == "Seq"
    a, b, c = t.left.left, t.left.right, t.right
    assert isinstance(a, SetHealth)
    assert isinstance(b, AddEffect) and b.effect_type == int(EffectType.BloodChalice_HealOnAttack)
    assert isinstance(c, AddStaticStatModifierEffect)
    assert c.effect_type == int(EffectType.BloodChalice_ExtraPiercing)
    assert c.stat_type == int(StatType.EXTRA_PIERCE_MELEE)
    # Les DEUX litteraux du `PercentageOf` natif, LUS au call-site (`roundingRule = 2` = Floor ;
    # `ConfigConst` = `GetNumberConstant`). BlackRage porte les valeurs INVERSES sur les deux axes.
    assert a.pct_rounding == 2
    assert a.pct_is_constant is True
    assert a.pct_var == "healthPct"
    # `scale_from_source` : la magnitude du soin de 1368 est indexee par l'`AbilityState` du POSEUR,
    # et `hpToHeal` EST dans `variablesAffectedByRarityBonus`.
    assert b.scale_from_source is True
    assert b.duration_rounds == 1 and c.duration_rounds == 1      # TurnsFromRounds(1) x2


def test_le_selecteur_de_cibles_porte_ses_TROIS_etages():
    """`GetTargets` = `UnitsWithoutTrait(AdjacentFriends(Caster) op_Subtraction
    MechanicalUnits(AdjacentFriends(Caster)), 0x19 Immune)` -- TROIS etages, et deux d'entre eux
    sont MUETS dans le tooltip.

    ⚠ POURQUOI UNE GARDE STRUCTURELLE PLUTOT QUE LE SEUL LIVE. L'etage E3 du probe mesure que le
    NATIF laisse le mecanique intact -- ce qu'il fait quoi qu'on ecrive cote port. Retirer le
    `MechanicalUnits` du selecteur laisserait donc E3 VERT tout en faisant soigner (et effecter) une
    unite que le natif refuse : exactement la panne #520/#564, invisible de tout compteur. C'est
    cette assertion-ci qui la voit.

    ⚠ Et le filtre `Immune` n'est confronte NULLE PART en live : aucune des unites du pool ne porte
    ce trait. La structure est le SEUL canal qui le garde."""
    from engine.entities.selectors.units import (AdjacentFriends, MechanicalUnits, Sub,
                                                 UnitsWithoutTrait)
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.runner.abilities.bloodangels import blood_chalice_targets

    sel = blood_chalice_targets()
    assert isinstance(sel, UnitsWithoutTrait)
    assert int(sel.trait) == int(UnitTrait.Immune), (
        "`0x19` est un UnitTrait.Immune -- l'ordinal est AUSSI valide dans EffectType et "
        "ActiveAbilityType, seul le nom discrimine")
    assert isinstance(sel.source, Sub), (
        "l'exclusion des MECANIQUES a disparu : le port affecterait des unites que le natif REFUSE, "
        "sans erreur et sans qu'aucun etage live ne le voie")
    assert isinstance(sel.source.a, AdjacentFriends)
    assert isinstance(sel.source.b, MechanicalUnits)
    # Le natif appelle la surcharge UNIT-ancree (tranchee par ses XREFS entrantes) : centre = Caster,
    # reference d'equipe = le MEME selecteur -> collapse `reference=None` exact ici.
    assert sel.source.a.reference is None


def test_le_trigger_de_soin_passe_par_l_operation_qui_porte_le_gate():
    """Le soin sur attaque melee DOIT passer par `HealUnitOperation.execute` -- qui porte le gate
    `AttackQuery$$EntityCanBeHealed` ET `PredictHeal`. C'est exactement la panne trouvee DEUX fois
    (#520 sur `HealUnitOperation`, #564 sur `ResurrectUnitOperation`) : une mutation directe des PV
    soigne des cibles que le natif REFUSE, en rendant `ported: True`. Aucun compteur d'audit ne le
    voit."""
    import inspect
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.entities.effect_type import EffectType
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    from engine.runner.operations.triggers.effect_triggers import BloodChaliceHealOnMeleeAttack

    ef = int(EffectType.BloodChalice_HealOnAttack)
    assert BloodChaliceHealOnMeleeAttack in (EFFECT_TRIGGERS.get(ef) or []), (
        "le trigger de soin de 1368 n'est pas au registre : l'effet serait pose et INERTE")
    assert BloodChaliceHealOnMeleeAttack.event_id == EventTriggerType.Attack   # `On(0x9, 1)`
    src = inspect.getsource(BloodChaliceHealOnMeleeAttack.execute_behaviour)
    assert "HealUnitOperation.execute" in src, (
        "le soin ne passe PAS par l'Operation qui porte le gate `EntityCanBeHealed` et `PredictHeal`")
    # `HealBehaviourOptions$$ForHeal` = `(scope 0, removeEffects 1)`, LU au call-site -- ce n'est
    # PAS `ForRegenerate` `(1, 0)`, et le passif du MEME porteur, lui, utilise bien `ForRegenerate`.
    assert "scope=0" in src and "remove_effects=True" in src

    # `IsMeleeAttack` : le trigger doit se TAIRE sur une attaque a distance et sur un `ranged` non
    # threade (tri-etat), et ne mordre que si l'ACTEUR est le porteur.
    class _Ev:
        def __init__(self, actor, ranged):
            self.actor_id, self.ranged = actor, ranged
    t = BloodChaliceHealOnMeleeAttack(owner_id=7)
    assert t.matches(None, _Ev(7, False)) is True
    assert t.matches(None, _Ev(7, True)) is False
    assert t.matches(None, _Ev(7, None)) is False
    assert t.matches(None, _Ev(9, False)) is False


# ---------------------------------------------------------------- 1..6. le live

def test_e1_le_set_est_isole_et_bit_exact(mesure):
    """L'ecart entre le PV live et le SET que le PORT calcule est CONSTANT quand `hp_max` VARIE --
    c'est ce qui etablit la base (`MAXIMUM`, pas le courant), le pct et l'arrondi SANS fitter le
    soin passif voisin (`SanguinaryPriest`, non porte), qui vaut ~2049 PV."""
    k = next(x for x in mesure if x.startswith("E1 "))
    assert mesure[k], k


def test_e2_une_cible_pleine_descend_ce_n_est_pas_un_heal(mesure):
    """LE DISCRIMINANT de la categorie. Un `Heal` laisserait une cible PLEINE intacte ; le
    `ChangeStat` mode 0 = SetAbsolute la fait DESCENDRE au point de consigne."""
    k = next(x for x in mesure if x.startswith("E2 "))
    assert mesure[k], k


def test_e3_le_natif_refuse_mecanique_et_hors_portee(mesure):
    """Le regime ou le natif REFUSE, monte a cote d'un regime ou il accepte -- sans lui, l'accord
    d'E1/E2 serait un accord en regime degenere."""
    k = next(x for x in mesure if x.startswith("E3 "))
    assert mesure[k], k


def test_e4_les_effets_sont_poses_sur_le_bon_ensemble(mesure):
    """1368 sur la cible eligible et sur elle SEULE."""
    k = next(x for x in mesure if x.startswith("E4 effets"))
    assert mesure[k], k


def test_e4bis_1369_est_inactif_hors_charge(mesure):
    """`CreateActiveCondition = IsCharging(Owner, Target)` : hors charge, l'entite-effet existe mais
    `IsActive == 0`, et `readEffectsByUnit` la DROPPE. C'est la mesure qui FONDE le residu #576-r1
    (le port applique le stat-mod pour toute la duree -> il SUR-ACCORDE)."""
    k = next(x for x in mesure if x.startswith("E4bis"))
    assert mesure[k], k


def test_e5_l_arrondi_est_floor_pas_le_half_to_even(mesure):
    """`roundingRule = 2`. Le departage exige `hp_max = 3 (mod 4)` ; l'etage le monte expres et DIT
    quand il n'est pas discriminant plutot que de rendre un faux vert."""
    k = next(x for x in mesure if x.startswith("E5 "))
    assert mesure[k], k
