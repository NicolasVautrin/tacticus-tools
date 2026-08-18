"""GARDE de trois lectures de decompile qui, chacune, se recopiaient PAR ANALOGIE.

Un seul fichier parce que les trois partagent la MEME forme de faute : une propriete vraie d'un
membre d'une famille, transposee a un autre membre sans etre relue au natif. Elle est silencieuse
dans les trois cas -- ni erreur, ni crash, juste la mauvaise condition ou le mauvais etage.

  * **#1008-r5** -- la gate de `KanOpenerEffect` est `IsMeleeAttack`, PAS `IsNormalAttack`. Les deux
    abilities portent la MEME paire de variables gameconfig (`armorIgnored` + `armorReduction`,
    toutes deux dans `variablesAffectedByRarityBonus`) et le meme kit orky : rien hors du decompile
    ne les distingue. Le canal `get_armor_penetration` ne recevait meme pas de quoi EXPRIMER une
    gate de vecteur.
  * **#946-r3** -- les litteraux du `.ctor` des deux dernieres soeurs `_CounterAttackEffect`, et
    surtout l'ENUM de leur ability source : `WarConstruct` passe par la surcharge d'`op_Implicit`
    qui ecrit `set_ActiveAbility`, seul de sa famille. Confondre l'enum ne leverait AUCUNE erreur.
  * **#1005-r1** -- il n'existe qu'UN placement pour l'additif de l'ATTAQUANT, et il est
    PRE-percage. Le residu en supposait deux.

ASCII only (console cp1252).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.entities.active_ability_type import ActiveAbilityType            # noqa: E402
from engine.entities.effect_type import EffectType                           # noqa: E402
from engine.entities.effects.factory import EFFECT_CLASSES, EffectFactory    # noqa: E402
from engine.entities.effects.loki.counter_attack import (                    # noqa: E402
    GrimRetributionCounterAttackEffect, SmashaSquigJawsCounterAttackEffect,
    UnwaveringSentinelCounterAttackEffect, WarConstructCounterAttackEffect,
    WireweaveNetCounterAttackEffect)
from engine.entities.effects.loki.hits import (                              # noqa: E402
    KanOpenerEffect, PowerTripIgnoreArmorEffect)
from engine.entities.triggered_ability_type import TriggeredAbilityType      # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # #1008-r5 : les deux porteurs de la face ATTAQUANT, le canal qui thread la gate, et la
        # signature qui la rend exprimable.
        "scripts/python/engine/entities/effects/loki/hits.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effects/base.py",
        # #946-r3 : le foyer de litteraux de la famille et le registre qui les monte.
        "scripts/python/engine/entities/effects/loki/counter_attack.py",
        "scripts/python/engine/entities/effects/factory.py",
        # Les mirrors d'enum dont ce fichier fait DEPENDRE la qualification.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        # #1005-r1 : le foyer du placement, et le calculateur qui le fixe.
        "scripts/python/engine/services/effect_bonus.py",
        "scripts/python/engine/services/damage_prediction.py",
        # Le PERIMETRE BALAYE par l'etage 3c (tout appelant du calculateur peut le rouvrir).
        "scripts/python/engine/**/*.py",
    ),
    # Les magnitudes sont LUES dans le gameconfig (`KanOpener.armorIgnored`, `PowerTrip.*`).
    "build": True,
    "toujours": False,
    "raison": ("les gates de vecteur des deux penetrations d'armure ATTAQUANT, les litteraux et "
               "l'enum d'ability source des cinq `_CounterAttackEffect`, et l'unicite du placement "
               "PRE-percage du canal additif attaquant"),
}

NIVEAU = 10        # palier d'ability quelconque, non degenere (les deux tableaux ont 65 entrees)


def _pen(cls, effect_type):
    e = cls(name=cls.__name__, effect_type=effect_type, target=7, level=1)
    e.ability_level = NIVEAU
    return e


# ==================================================================================================
# ETAGE 1 -- #1008-r5 : la gate de KanOpener est `IsMeleeAttack`, celle de PowerTrip `IsNormalAttack`
# ==================================================================================================

def test_1008r5_les_deux_gates_sont_DIFFERENTES_et_orthogonales():
    """LA LECTURE QUI FAIT TOUTE LA TRANCHE, sous forme de table de verite.

    `KanOpenerEffect$$CreateEffectDamageBonusForAttack` = `IsMeleeAttack & get_OwnerIsCaster &
    !get_OwnerIsTarget` ; `PowerTrip_IgnoreArmorEffect$$...` = `IsNormalAttack & ...`. Les deux
    gates portent sur des AXES ORTHOGONAUX (vecteur vs nature du coup), donc il existe des regimes
    ou l'une ouvre et l'autre ferme -- c'est precisement ce qu'une recopie par analogie effacerait.
    """
    kan, pwr = _pen(KanOpenerEffect, 1102), _pen(PowerTripIgnoreArmorEffect, 1119)

    # TEMOINS NON DEGENERES d'abord : chaque classe DOIT pouvoir rendre une valeur non nulle dans
    # SON regime, sinon toute la table ci-dessous serait un `None == None` sans contenu.
    assert kan.get_armor_penetration(is_normal_attack=True, is_ranged=False), \
        "temoin DEGENERE : KanOpener ne rend rien dans son propre regime (melee)"
    assert pwr.get_armor_penetration(is_normal_attack=True, is_ranged=None), \
        "temoin DEGENERE : PowerTrip ne rend rien dans son propre regime (attaque normale)"

    # REGIME DISCRIMINANT 1 -- attaque normale a DISTANCE : PowerTrip ouvre, KanOpener FERME.
    assert kan.get_armor_penetration(is_normal_attack=True, is_ranged=True) is None
    assert pwr.get_armor_penetration(is_normal_attack=True, is_ranged=True) is not None

    # REGIME DISCRIMINANT 2 -- ability SPECIALE en melee : KanOpener ouvre, PowerTrip FERME.
    assert kan.get_armor_penetration(is_normal_attack=False, is_ranged=False) is not None
    assert pwr.get_armor_penetration(is_normal_attack=False, is_ranged=False) is None


def test_1008r5_le_vecteur_NON_MESURE_ferme_la_gate_de_kanopener():
    """POLARITE DU TRI-ETAT, qui ne se devine pas et que le dépôt fixe : `None` = NON MESURE FERME.

    Le port ne devine pas la nature du coup -- meme convention que le nœud symetrique
    `IsRangedAttack` de `WayOfTheShortBladeEffect._is_valid_attack_for_bonus`. Un port permissif
    (`None` ouvre) accorderait la penetration a des attaques a distance, en silence."""
    kan = _pen(KanOpenerEffect, 1102)
    assert kan.get_armor_penetration(is_normal_attack=True, is_ranged=None) is None
    # ... et PowerTrip, lui, n'a AUCUN nœud de vecteur : `is_ranged` ne doit RIEN y changer.
    pwr = _pen(PowerTripIgnoreArmorEffect, 1119)
    valeurs = {pwr.get_armor_penetration(is_normal_attack=True, is_ranged=v)
               for v in (None, True, False)}
    assert len(valeurs) == 1, valeurs


def test_1008r5_la_magnitude_de_kanopener_est_LUE_au_gameconfig():
    """La cle `0x40` que la docstring declarait << non resolue >> est `AbilityVariableType.armorIgnored`
    (#1008-r2) et le gameconfig la porte pour `KanOpener`. Garde la CHAINE, pas la valeur : c'est
    `ability_var` qui doit rendre le meme nombre, indexe sur le niveau d'ability."""
    from engine.entities.effects.magnitude import ability_var
    attendu = ability_var("KanOpener", "armorIgnored", NIVEAU)
    assert attendu, "temoin DEGENERE : `KanOpener.armorIgnored` absent du gameconfig"
    kan = _pen(KanOpenerEffect, 1102)
    assert kan.get_armor_penetration(is_normal_attack=True, is_ranged=False) == attendu

    # ... et la magnitude de PowerTrip DIFFERE, sinon ce test passerait sur une confusion des deux
    # entrees de gameconfig (les deux abilities portent une variable du MEME nom).
    autre = ability_var("PowerTrip", "armorIgnored", NIVEAU)
    assert autre and autre != attendu, (attendu, autre)


def test_1008r5_le_canal_attaquant_THREAD_le_vecteur():
    """LE CABLAGE, sans lequel la gate serait INEXPRIMABLE (et le test ci-dessus verifierait une
    methode que personne n'appelle avec `is_ranged`).

    `_attacker_effect_bonuses` detient deja `is_ranged` ; c'est lui qui doit le passer."""
    from engine.entities.effects import build_attacker_modifiers_from_effects
    kan = _pen(KanOpenerEffect, 1102)
    attendu = kan.get_armor_penetration(is_normal_attack=True, is_ranged=False)

    melee = build_attacker_modifiers_from_effects([kan], is_ranged=False, is_normal_attack=True)
    dist = build_attacker_modifiers_from_effects([kan], is_ranged=True, is_normal_attack=True)
    inconnu = build_attacker_modifiers_from_effects([kan], is_ranged=None, is_normal_attack=True)

    assert melee.armor_penetration == attendu, (melee.armor_penetration, attendu)
    assert dist.armor_penetration == 0, dist.armor_penetration
    assert inconnu.armor_penetration == 0, inconnu.armor_penetration


# ==================================================================================================
# ETAGE 2 -- #946-r3 : les litteraux des cinq soeurs, et l'ENUM de l'ability source
# ==================================================================================================

#: Les cinq membres, avec les litteraux du `.ctor` LUS a l'assembleur. C'est un CLIQUET sur les
#: valeurs MESUREES : `probe_313` compare le mirror au build et redevient vert apres un
#: renumerotage, mais il ne voit pas ce qui est ECRIT au site.
_CTOR = {
    WireweaveNetCounterAttackEffect: (1, 2, False),
    GrimRetributionCounterAttackEffect: (1, 1, False),
    UnwaveringSentinelCounterAttackEffect: (1, 1, False),
    SmashaSquigJawsCounterAttackEffect: (1, 1, False),
    WarConstructCounterAttackEffect: (2, 0, True),
}


def test_946r3_les_litteraux_du_ctor_de_chaque_soeur():
    for cls, (turns, freq, auto) in _CTOR.items():
        assert cls.TURNS_ENABLED == turns, (cls.__name__, cls.TURNS_ENABLED)
        assert cls.ACTIVATION_FREQUENCY == freq, (cls.__name__, cls.ACTIVATION_FREQUENCY)
        assert cls.HAS_AUTOMATIC_ACTIVATION is auto, (cls.__name__, cls.HAS_AUTOMATIC_ACTIVATION)
        # L'INVARIANT NATIF qui relie les deux derniers, et que le port ne doit jamais desaccorder :
        # `PlayerTurnEffect$$.ctor` passe `hasAutomaticActivation = (activationFrequency == 0)`.
        assert auto == (freq == 0), cls.__name__


def test_946r3_warconstruct_est_le_SEUL_a_sortir_du_patron():
    """NON-DEGENERESCENCE de la table ci-dessus : si les cinq lignes etaient identiques, le test
    passerait aussi sur une recopie. Trois axes doivent SEPARER `WarConstruct` des quatre autres."""
    autres = [c for c in _CTOR if c is not WarConstructCounterAttackEffect]
    assert len(autres) == 4
    assert {c.TURNS_ENABLED for c in autres} == {1}
    assert WarConstructCounterAttackEffect.TURNS_ENABLED == 2
    assert all(c.HAS_AUTOMATIC_ACTIVATION is False for c in autres)
    assert WarConstructCounterAttackEffect.HAS_AUTOMATIC_ACTIVATION is True
    assert 0 not in {c.ACTIVATION_FREQUENCY for c in autres}
    assert WarConstructCounterAttackEffect.ACTIVATION_FREQUENCY == 0


def test_946r3_l_enum_de_l_ability_source_suit_la_surcharge_d_op_implicit():
    """LE POINT OU UNE CONFUSION SERAIT SILENCIEUSE EN ORDINAL.

    Quatre membres passent leur id par la surcharge d'`op_Implicit` dont le corps appelle
    `IdunBattle.Core.AbilityOrEffect$$set_TriggeredAbility` ; `WarConstruct` passe par celle qui
    appelle `$$set_ActiveAbility`. Le port porte donc DEUX attributs distincts -- et ce test verifie
    qu'aucun membre ne porte les deux, ce qui signalerait une recopie."""
    for cls in _CTOR:
        a = getattr(cls, "SOURCE_ACTIVE_ABILITY", None)
        t = getattr(cls, "SOURCE_TRIGGERED_ABILITY", None)
        assert (a is None) != (t is None), (cls.__name__, a, t)
        assert isinstance(a or t, (ActiveAbilityType, TriggeredAbilityType))

    assert WarConstructCounterAttackEffect.SOURCE_ACTIVE_ABILITY is ActiveAbilityType.WarConstruct
    assert (SmashaSquigJawsCounterAttackEffect.SOURCE_TRIGGERED_ABILITY
            is TriggeredAbilityType.SmashaSquigJaws)


def test_946r3_les_ordinaux_communs_NOMMENT_AUTRE_CHOSE():
    """CE QUI REND LE NOM OBLIGATOIRE, et qui doit s'asserter NON VIDE (un ensemble vide passerait
    pour vert). Les deux ids de cette tranche existent dans les TROIS enums, et n'y designent pas
    la meme chose -- une confusion ne leverait donc aucune erreur."""
    temoins = 0
    for ordinal, attendu_actif, attendu_trig in ((1133, "WarConstruct", None),
                                                 (1105, None, "SmashaSquigJaws")):
        noms = {}
        for enum in (ActiveAbilityType, TriggeredAbilityType, EffectType):
            try:
                noms[enum.__name__] = enum(ordinal).name
            except ValueError:
                pass
        assert len(noms) >= 2, (ordinal, noms)
        if attendu_actif:
            assert noms["ActiveAbilityType"] == attendu_actif, noms
            assert noms["TriggeredAbilityType"] != attendu_actif, noms
        if attendu_trig:
            assert noms["TriggeredAbilityType"] == attendu_trig, noms
            assert noms["ActiveAbilityType"] != attendu_trig, noms
        temoins += 1
    assert temoins == 2, temoins


def test_946r3_les_deux_classes_neuves_sont_AU_REGISTRE_et_MONTEES_par_la_factory():
    """Une classe hors registre est routee sur `BaseEffect` : le port perdrait ses litteraux sans
    la moindre erreur. Le nom de registre est celui du mirror `EffectType`, jamais un ordinal."""
    for nom, cls, ordinal in (("SmashaSquigJaws_CounterAttack",
                               SmashaSquigJawsCounterAttackEffect, 1104),
                              ("WarConstruct_CounterAttack",
                               WarConstructCounterAttackEffect, 1286)):
        assert EffectType(ordinal).name == nom, (ordinal, EffectType(ordinal).name)
        assert EFFECT_CLASSES.get(nom) is cls, nom
        assert isinstance(EffectFactory.create({"name": nom}), cls), nom


# ==================================================================================================
# ETAGE 3 -- #1005-r1 : UN SEUL placement pour l'additif ATTAQUANT, et il est PRE-percage
# ==================================================================================================

def test_1005r1_for_addition_ne_PORTE_pas_de_placement():
    """LA PREMISSE REFUTEE, en une propriete executable.

    Le residu supposait que `for_addition` choisissait un placement (POST) et
    `attacker_additive_pre` un autre (PRE). `EffectBonus` n'a AUCUN champ de placement : deux appels
    identiques rendent des objets EGAUX, quelle que soit la classe d'effet qui les fabrique. Le
    placement est fixe par le CALCULATEUR, pas par le bonus."""
    from engine.services.effect_bonus import for_addition
    a, b = for_addition(True, 490), for_addition(True, 490)
    assert a == b, (a, b)
    champs = {f for f in vars(a)} if hasattr(a, "__dict__") else set(getattr(a, "_fields", ()))
    assert not any("pre" in f.lower() or "percage" in f.lower() or "pierce" in f.lower()
                   for f in champs), champs


def test_1005r1_le_placement_PRE_percage_est_ARITHMETIQUEMENT_discriminant():
    """LES DEUX HYPOTHESES, SEPAREES PAR UN NOMBRE -- et c'est la contre-epreuve du test suivant.

    Pre-percage : l'additif entre dans la base, donc il traverse la %-list et ressort SCALE.
    Post-percage : il s'ajoute apres, donc il ressort NU. Avec un %-mod non neutre, les deux ne
    peuvent PAS coincider -- c'est ce qui a permis de trancher live (delta mesure 2205, l'hypothese
    post-percage predisant 1470)."""
    from engine.services.damage_modifiers import DamageModifiers
    from engine.services.damage_prediction import apply_pierce_and_modifiers

    mods = DamageModifiers()
    mods.additive = 490
    # Un %-mod NON NEUTRE : sans lui, les deux placements coincident et le test serait DEGENERE.
    # `pct_list` est une liste de couples `(multiplicateur, cap)` -- l'accumulateur `@0x18` que
    # `ApplyCappedModifiers` (slot 0x11) consomme, LU et non devine.
    mods.pct_list = [(1.5, None)]

    base = 802
    pre = apply_pierce_and_modifiers(base, 100, 0, mods, attacker_additive_pre=True)
    post = apply_pierce_and_modifiers(base, 100, 0, mods, attacker_additive_pre=False)
    assert pre != post, (pre, post)            # NON DEGENERE : le regime discrimine vraiment
    # La reconstruction bit-exacte de la mesure live (#1005-r1) : `(802 + 490) x 1.5 = 1938`.
    assert pre == 1938, pre


def test_1005r1_aucun_appelant_du_moteur_ne_choisit_le_placement_POST():
    """LE CLIQUET, et il porte sur le PERIMETRE, pas sur un fichier : n'importe quel appelant neuf
    d'`apply_pierce_and_modifiers` peut rouvrir le gisement en omettant le parametre.

    Le balayage est STATIQUE (il voit les sites qu'aucune passe ne joue) et il assertionne son
    propre NON-VIDE : un recenseur qui ne visite rien rendrait `0 offense` et passerait pour vert.
    """
    racine = PYDIR / "engine"
    vus, sans_mods, offenses = 0, 0, []
    for chemin in racine.rglob("*.py"):
        arbre = ast.parse(chemin.read_text(encoding="utf-8", errors="replace"), str(chemin))
        for nd in ast.walk(arbre):
            if not isinstance(nd, ast.Call):
                continue
            cible = nd.func.attr if isinstance(nd.func, ast.Attribute) else \
                (nd.func.id if isinstance(nd.func, ast.Name) else None)
            if cible != "apply_pierce_and_modifiers":
                continue
            vus += 1
            kw = {k.arg: k.value for k in nd.keywords if k.arg}
            # EXEMPTION **DERIVEE**, jamais une allowlist de chemins : quand l'appelant passe
            # litteralement `mods=None`, il n'y a AUCUN `DamageModifiers`, donc aucun additif a
            # placer -- le corps lui-meme court-circuite (`if mods is not None and ...`). C'est le
            # cas du DoT de tuile `EnvFireTile`, qui n'a ni attaquant ni bonus d'effet. Un critere
            # par chemin se serait perime au premier deplacement de fichier.
            m = kw.get("mods")
            if isinstance(m, ast.Constant) and m.value is None:
                sans_mods += 1
                continue
            pre = kw.get("attacker_additive_pre")
            ok = isinstance(pre, ast.Constant) and pre.value is True
            if not ok:
                offenses.append("%s:%d" % (chemin.relative_to(PYDIR), nd.lineno))
    # NON-DEGENERESCENCE : le recenseur doit avoir VU des appels, sinon son zero ne prouve rien --
    # et l'exemption ne doit pas avoir tout avale.
    assert vus >= 10, "recensement DEGENERE : %d appel(s) visite(s)" % vus
    assert vus - sans_mods >= 8, (
        "exemption TROP LARGE : %d appels visites, %d exemptes" % (vus, sans_mods))
    assert not offenses, (
        "placement du canal additif ATTAQUANT non declare PRE-percage. Le natif ne consomme PAS "
        "`DamageModifiers.Addition@+0x10` dans `DamagePrediction$$CalculateBaseDamageWithAllModifiers` "
        "(#1005-r1) : un appel sans `attacker_additive_pre=True` calcule un etage qui n'existe pas. "
        "Sites : %s" % offenses)
