"""#1077 -- GARDE offline des deux passifs portes : `FiringPosition` (1150) et `MischiefMakers`
(1471 -> effet 1469).

Le PROBE (`probe_1077_firing_position_mischief_makers.py`) MESURE contre le natif ; ce fichier
GARDE ce que la mesure a etabli, y compris les points qu'aucun test existant ne voit :

  1. les ORDINAUX ECRITS AU SITE (un mirror regenere apres renumerotage redeviendrait vert alors
     que la valeur ecrite, elle, aurait change -- cf. la note `probe_313` du CLAUDE.md) ;
  2. les QUATRE inscriptions de registre, par EXECUTION et jamais par grep du nom ;
  3. le fait que `FiringPosition_ReactivateOverwatchEffect` **n'override PAS** `LegitDeathReasons`
     (bloc `methodPointers` = 2 entrees) -- c'est le point ou recopier le voisin de forme 1145
     aurait re-arme l'overwatch sur des morts que le natif refuse ;
  4. `hitsReduction = 2`, LU au gameconfig, et DISTINCT du `1` de ses deux classes soeurs ;
  5. le canal `is_normal_attack` du vecteur `On(9)`, sans lequel le passif est MUET offline --
     c'est une regression SILENCIEUSE (aucune erreur, aucun test rouge) et c'est exactement l'etat
     dans lequel la tranche l'a trouve.
"""
from __future__ import annotations

import inspect

import pytest

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
#: Volontairement LARGE : ce test garde des appariements repartis sur SIX foyers, dont deux
#: (`damage_ops/normal.py`, `dispatch/attack.py`) sont des foyers PARTAGES que la tranche a du
#: reparer. Trop large est sain ; trop etroit serait un faux vert -- le fichier ne se rejouerait
#: pas sous `--since` quand ce qu'il garde a bouge.
DECLENCHEUR = {
    "chemins": (
        # Les deux mirrors d'enum dont ce fichier FIGE les ordinaux ECRITS au site.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        # Les quatre registres dont il verifie les inscriptions PAR EXECUTION.
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/entities/effects/factory.py",
        # Les deux modules portes par la tranche.
        "scripts/python/engine/runner/operations/triggers/loki/reactivate_overwatch.py",
        "scripts/python/engine/runner/operations/triggers/loki/mischief_makers.py",
        "scripts/python/engine/entities/effects/loki/heal_blocking.py",
        # Le canal `is_normal_attack` du vecteur On(9) : son SITE D'APPEL (lu par AST) et le
        # dispatcher qui le porte. Sans eux, la regression est SILENCIEUSE.
        "scripts/python/engine/runner/operations/damage_ops/normal.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        # `_config_const` / `_hit_reduction_value` lisent le gameconfig : une valeur qui bouge
        # cote donnees (chance 25, nrOfRounds 1, hitsReduction 2) doit rejouer ce fichier.
        "scripts/python/gameconfig.py",
    ),
    # Les ordinaux figes ici sont ceux du BUILD (`frida/enums.tsv`) : un changement de build peut
    # les renumeroter, et c'est PRECISEMENT ce que ce fichier doit alors faire rougir.
    "build": True,
    "toujours": False,
    "raison": (
        "Appariements ability <-> effet (1144/1150/1151, 1471/1469), constantes LUES au "
        "gameconfig, inscriptions aux quatre registres, non-override de `LegitDeathReasons` "
        "par la sous-classe 1150, et le canal `is_normal_attack` du vecteur On(9)."
    ),
}


# --------------------------------------------------------------------- etage 1 : ordinaux au SITE

def test_1077_ordinaux_ecrits_au_site():
    """Les ordinaux que le PORT ecrit, figes a la valeur MESUREE a la confrontation.

    ⚠ Ce n'est PAS un doublon de `probe_313` : celui-la compare le MIRROR au BUILD et redevient
    vert des qu'on regenere le mirror ; celui-ci garde la valeur ECRITE."""
    from engine.entities.effect_type import EffectType
    from engine.entities.triggered_ability_type import TriggeredAbilityType

    # FiringPosition : ability 0x478, owner-effect 0x47e, effet de reduction 0x47f.
    assert int(TriggeredAbilityType.FiringPosition) == 0x478 == 1144
    assert int(EffectType.FiringPosition_ReactivateOverwatch) == 0x47e == 1150
    assert int(EffectType.FiringPosition_HitReduction) == 0x47f == 1151
    # MischiefMakers : ability 0x5bf, effet pose 0x5bd, plus le `Pinned` du `Maybe`.
    assert int(TriggeredAbilityType.MischiefMakers) == 0x5bf == 1471
    assert int(EffectType.MischiefMakers) == 0x5bd == 1469
    assert int(EffectType.Pinned) == 0x429 == 1065


def test_1077_les_homonymes_nomment_AUTRE_CHOSE():
    """Les quatre ordinaux de la tranche sont AUSSI des membres valides de l'autre enum, et ils y
    nomment autre chose. C'est ce qui rend la QUALIFICATION obligatoire : une confusion serait
    SILENCIEUSE (aucune exception, juste la mauvaise cle).

    `1144` en `ActiveAbilityType` est `BioMinefield` -- **deja au registre `ABILITY_CLASSES`**,
    donc un `ABILITY_CLASSES[1144]` existant ne prouve RIEN sur `FiringPosition`."""
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.entities.effect_type import EffectType
    from engine.entities.triggered_ability_type import TriggeredAbilityType

    assert ActiveAbilityType(1144).name == "BioMinefield"
    assert TriggeredAbilityType(1151).name == "NeedsMoreDakka_Attack"
    assert TriggeredAbilityType(1469).name == "MawClawsOfThyrax"
    assert EffectType(1471).name == "Drachnyen_ExtraAttack"
    # ... et le test ci-dessus ne doit pas etre vide de sens : les quatre couples DIFFERENT.
    assert ActiveAbilityType(1144).name != TriggeredAbilityType(1144).name
    assert EffectType(1471).name != TriggeredAbilityType(1471).name


# ------------------------------------------------------- etage 2 : les registres, PAR EXECUTION

def _registres():
    """Peuple les registres comme le fait le moteur, puis les rend. JAMAIS un grep du nom :
    `GAP-MENTION` veut precisement dire « le nom est ecrit quelque part sans que ce soit cable »."""
    import importlib
    import pkgutil

    import engine.runner.operations.triggers as trg
    for m in pkgutil.walk_packages(trg.__path__, trg.__name__ + "."):
        importlib.import_module(m.name)
    import engine.entities.effects.factory as fx
    import engine.runner.operations.triggers.dispatch.registry as reg
    return reg, fx


def test_1077_firing_position_inscrit_aux_deux_registres():
    """`ABILITY_INIT_OWNER_EFFECTS` (la POSE a l'init, via `AOwnerEffectTriggeredAbility`) ET
    `EFFECT_TRIGGERS[1150]` (les DEUX `Triggered()` heritees de la base)."""
    from engine.entities.effect_type import EffectType
    reg, fx = _registres()

    assert fx.ABILITY_INIT_OWNER_EFFECTS.get("FiringPosition") == [
        EffectType.FiringPosition_ReactivateOverwatch.name]
    trigs = reg.EFFECT_TRIGGERS.get(int(EffectType.FiringPosition_ReactivateOverwatch))
    assert trigs is not None, "EFFECT_TRIGGERS[1150] absent"
    noms = {c.__name__ for c in trigs}
    assert noms == {"FiringPositionReactivateOverwatch", "FiringPositionHitReductionPurge"}


def test_1077_mischief_makers_inscrit_aux_deux_registres():
    """`ABILITY_TRIGGERS` (l'ability) ET `EFFECT_CLASSES` (la CLASSE de l'effet pose).

    Les deux sont necessaires et AUCUNE ne subsume l'autre : sans la seconde, l'effet est pose mais
    materialise en `BaseEffect` nu, donc `has_heal_blockers` reste FAUX et la cible demeure
    soignable -- degradation PERMISSIVE, exactement le residu que #927 avait nomme."""
    from engine.entities.effects.loki.heal_blocking import HealBlockingEffect, MischiefMakersEffect
    reg, fx = _registres()

    trigs = reg.ABILITY_TRIGGERS.get("MischiefMakers")
    assert trigs is not None, "ABILITY_TRIGGERS['MischiefMakers'] absent"
    assert {c.__name__ for c in trigs} == {"MischiefMakersAbility"}
    assert fx.EFFECT_CLASSES.get("MischiefMakers") is MischiefMakersEffect
    # C'est un BLOQUEUR DE SOIN, pas un effet de degat : la hierarchie vient de `classes.tsv`, le
    # pseudo-C de son `.ctor` designe `DeathwingEffect` (corps fondu par l'ICF).
    assert issubclass(MischiefMakersEffect, HealBlockingEffect)


# ------------------------------------------- etage 3 : FiringPosition n'override PAS la base

def test_1077_firing_position_herite_legit_death_reasons_de_la_base():
    """Le bloc `methodPointers` de `FiringPosition_ReactivateOverwatchEffect` fait DEUX entrees
    (`.ctor` + `GetHitReductionEffectType`), donc la classe prend `LegitDeathReasons` de la BASE --
    **un seul terme**, `HasDeathReason(dying, Ability, 1009)`.

    `EarlyWarningOverride` (1145), lui, l'OVERRIDE (deux termes, dont l'effet 1148 de Re'vas).
    Recopier ce voisin-la aurait re-arme l'overwatch sur des morts que le natif refuse."""
    from engine.runner.operations.triggers.loki.reactivate_overwatch import (
        AReactivateOverwatch, EarlyWarningOverrideReactivateOverwatch,
        FiringPositionReactivateOverwatch, InescapableDeathReactivateOverwatch)

    # HERITE : l'attribut resolu est LITTERALEMENT celui de la base.
    assert (FiringPositionReactivateOverwatch._legit_death_reasons
            is AReactivateOverwatch._legit_death_reasons)
    assert (InescapableDeathReactivateOverwatch._legit_death_reasons
            is AReactivateOverwatch._legit_death_reasons)
    # ... et le controle NON VIDE : la soeur 1145, elle, override bien -> sinon ce test ne
    # distinguerait rien et passerait pour vert sur une hierarchie plate.
    assert (EarlyWarningOverrideReactivateOverwatch._legit_death_reasons
            is not AReactivateOverwatch._legit_death_reasons)


def test_1077_hits_reduction_vaut_2_et_pas_1():
    """`AReactivateOverwatchEffect$$HitReductionValue` = `GetNumberConstant(config, 0x2c)` sur la
    config de l'ability passee au `.ctor`. Pour `FiringPosition` c'est **2** (i2 : « retaining 2
    fewer hits »), la ou ses deux soeurs valent 1. LU au gameconfig, jamais code en dur."""
    from engine.runner.operations.triggers.loki import reactivate_overwatch as RO

    assert RO._hit_reduction_value("FiringPosition") == 2
    # Le controle qui rend ce test discriminant : les soeurs ne valent PAS 2.
    assert RO._hit_reduction_value("EarlyWarningOverride") == 1
    assert RO._hit_reduction_value("InescapableDeath") == 1
    # ⚠ ET LA CLASSE DOIT VISER LA BONNE CONFIG. Tester la seule FONCTION laissait le test VERT
    # quand `SOURCE_ABILITY` basculait sur celle d'une soeur -- la valeur lue devenait 1 sans que
    # rien ne rougisse. Trouve par contre-epreuve.
    assert RO.FiringPositionReactivateOverwatch.SOURCE_ABILITY == "FiringPosition"
    assert RO.EarlyWarningOverrideReactivateOverwatch.SOURCE_ABILITY == "EarlyWarningOverride"
    assert RO.InescapableDeathReactivateOverwatch.SOURCE_ABILITY == "InescapableDeath"
    assert RO._hit_reduction_value(RO.FiringPositionReactivateOverwatch.SOURCE_ABILITY) == 2


def test_1077_appariement_effet_de_reduction():
    """Chaque sous-classe vise SON effet de reduction. Les intervertir ne leverait aucune erreur."""
    from engine.entities.effect_type import EffectType
    from engine.runner.operations.triggers.loki.reactivate_overwatch import (
        EarlyWarningOverrideReactivateOverwatch, FiringPositionReactivateOverwatch,
        InescapableDeathReactivateOverwatch)

    paires = {
        FiringPositionReactivateOverwatch: (int(EffectType.FiringPosition_ReactivateOverwatch),
                                            int(EffectType.FiringPosition_HitReduction)),
        EarlyWarningOverrideReactivateOverwatch: (
            int(EffectType.EarlyWarningOverride_ReactivateOverwatch),
            int(EffectType.EarlyWarningOverride_HitReduction)),
        InescapableDeathReactivateOverwatch: (int(EffectType.InescapableDeath_Effect),
                                              int(EffectType.InescapableDeath_HitsReduction)),
    }
    for cls, (porteur, reduction) in paires.items():
        assert cls.effect_type == porteur, cls.__name__
        assert cls.HIT_REDUCTION_EFFECT_TYPE == reduction, cls.__name__
    # Les trois reductions sont DEUX A DEUX distinctes (sinon l'appariement ne prouverait rien).
    assert len({r for _, r in paires.values()}) == 3


# ---------------------------------------- etage 4 : le canal `is_normal_attack` du vecteur On(9)

def test_1077_le_vecteur_on9_thread_is_normal_attack():
    """SANS ce canal, `MischiefMakersAbility.matches` ne peut JAMAIS etre vrai et le passif est
    MUET offline -- sans erreur, sans test rouge. C'etait l'etat trouve par la tranche.

    Le garde porte sur le SITE D'APPEL (le seul), pas sur la signature : un parametre qui existe
    mais que personne ne passe laisse la regression intacte."""
    from engine.runner.operations.damage_ops import normal as N

    # ⚠ **PAR AST, JAMAIS PAR GREP DE SOURCE**, et c'est la contre-epreuve qui l'a impose : la
    # premiere version cherchait la chaine `is_normal_attack=True` dans la fenetre du site d'appel
    # -- or le COMMENTAIRE qui documente ce site cite ce meme litteral. Le test restait donc VERT
    # apres avoir mis le vrai kwarg a `None`. C'est exactement le vice que l'audit passif nomme
    # (« un catalogue n'est pas un cablage »), applique a un test.
    import ast

    arbre = ast.parse(inspect.getsource(N))
    sites = [n for n in ast.walk(arbre)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)
             and n.func.attr == "finish_attack_triggers"]
    assert len(sites) == 1, "attendu UN site d'appel de finish_attack_triggers, vu %d" % len(sites)
    kw = {k.arg: k.value for k in sites[0].keywords}
    assert "is_normal_attack" in kw, (
        "le vecteur On(9) de la voie NORMALE ne thread plus `is_normal_attack` -> "
        "MischiefMakers redevient muet en silence, sans erreur ni test rouge")
    val = kw["is_normal_attack"]
    assert isinstance(val, ast.Constant) and val.value is True, (
        "`is_normal_attack` doit valoir le litteral True sur la voie NORMALE, vu %r"
        % (ast.dump(val)[:120],))


def test_1077_le_gate_est_restrictif_sur_un_canal_non_mesure():
    """TRI-ETAT : `None` = canal non threade -> le trigger se TAIT. Il ne suppose pas une attaque
    normale. C'est ce qui le rend inerte sur la voie ability/splash (`after_hit_ability_attack`),
    qui n'annonce pas ce canal."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.runner.operations.triggers.loki.mischief_makers import MischiefMakersAbility

    ab = MischiefMakersAbility(1)
    for valeur in (None, False):
        ev = TriggerEvent(EventTriggerType.Attack, 1, 2, ranged=False, profile=None,
                          is_normal_attack=valeur)
        assert ab.matches(None, ev) is False, "canal=%r devrait FAIRE TAIRE le trigger" % (valeur,)


def test_1077_mischief_makers_lit_les_constantes_du_gameconfig():
    """`GetNumberConstant` (`AbilityConstantType`), PAS `GetVariableForLevel` : ni le niveau ni la
    rarete ne mordent. Les deux valeurs sont LUES, jamais codees en dur."""
    from engine.runner.operations.triggers.loki import mischief_makers as MM

    assert MM._config_const(MM.CONST_CHANCE) == 25
    assert MM._config_const(MM.CONST_NR_OF_ROUNDS) == 1


def test_1077_ordre_du_behaviour_et_tirage_unique():
    """L'`op_BitwiseAnd` final est `(AddEffect(1469), Maybe(AddEffect(Pinned)))` -- l'INVERSE de
    l'ordre de CONSTRUCTION du pseudo-C. Ici ce n'est pas inerte : le `Maybe` consomme un
    `next_bool`, donc inverser decalerait le PRNG de toute la bataille.

    Mesure du probe : `mti` 7 avec l'ability contre 6 sans -> EXACTEMENT un tirage."""
    from engine.entities.behaviours import Maybe, Seq
    from engine.runner.abilities.behaviours.effects import AddEffect
    from engine.entities.effect_type import EffectType
    from engine.runner.operations.triggers.loki.mischief_makers import (
        mischief_makers_behaviour_tree)

    arbre = mischief_makers_behaviour_tree(chance=25, rounds=1)
    assert isinstance(arbre, Seq)
    # GAUCHE = le bloqueur de soin, INCONDITIONNEL (il n'est PAS sous le `Maybe`).
    assert isinstance(arbre.left, AddEffect)
    assert arbre.left.effect_type == int(EffectType.MischiefMakers)
    assert arbre.left.duration_rounds == 1
    # DROITE = le tirage, et il ne porte QUE le `Pinned`.
    assert isinstance(arbre.right, Maybe)
    assert isinstance(arbre.right.child, AddEffect)
    assert arbre.right.child.effect_type == int(EffectType.Pinned)
    # `options` ZEROEES cote natif -> duree PAR DEFAUT de l'effet, pas une duree nulle.
    assert arbre.right.child.duration_rounds is None


if __name__ == "__main__":                                   # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
