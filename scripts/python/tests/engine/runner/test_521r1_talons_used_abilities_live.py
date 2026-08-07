"""GARDE de la face TRIGGERED de `1195 TalonsOfTheEmperor` (#521-r1) --
`1330 TalonsOfTheEmperor_UsedAbilities`, l'ability qui FAIT AVANCER le compteur `1420`.

#521 avait porte la face COMBAT et LU le compteur depuis la capture ; il ne le faisait pas AVANCER.
En simulation pure il restait donc fige a sa valeur de depart, et l'extra damage devenait faux des
le 2e cast d'ability allie -- **sans erreur, sans crash**, exactement la degradation silencieuse que
le no-op d'avant #521 produisait un etage plus haut.

CE QUE LE PORT DOIT PRODUIRE, et ce que ce fichier garde :

    On( 0xe = UnitPostAbility, ownerNeedsToBeAlive = 1 )
    & AreFriends( Owner@+0x30, actor@+0x48 )
    & ( HasTrait(actor, Hero) & !HasTrait(actor, MachineOfWar) )
    & IsActiveAbilityCountedAsUsed( isPreAbilityTrigger = 0 )
        -> AddEffectOrIncreaseLevel( 0x58c, source = targets = Owner@+0x30,
                                     level = Formulas@+0x20 = Direct(1), maxLevel = NULL )

DEUX REGIMES, ET AUCUN N'EST DECORATIF.

  * `chaine` -- UN build, DEUX captures, les DEUX branches du `If` interne :
        cap0 (compteur 0) -> un ALLIE `Hero` caste `1184 MomentShackle` -> compteur 1
        cap1 (compteur 1) -> le PORTEUR caste `1195`                    -> degat, puis compteur 2
    La 1re transition exerce la branche **AddEffect** (pose a 1), la 2e la branche
    **IncreaseEffectLevel** (1 -> 2, et c'est le PORTEUR lui-meme qui compte : il est `Hero` et son
    propre allie -- aucun `!AreEqual` dans la conjonction native). Le degat du cast de 1195 est
    confronte coup par coup : il lit le compteur d'AVANT (1), pas celui d'apres.
  * `attaque_normale` -- LE TEMOIN NEGATIF. L'attaque normale EST une active ability cote natif et
    emet donc `On(0xe)` : seul `IsActiveAbilityCountedAsUsed` l'ecarte. Un port qui aurait oublie ce
    gate passerait `chaine` et echouerait ICI.

ET LES CINQ CONTRE-EPREUVES, chacune ne mutant QU'UNE lecture -- le probe EXIGE que celles qui
doivent discriminer discriminent, sans quoi l'accord du port serait un accord de hasard :
`sans_registre` (l'inscription par `GetPassiveHelperAbility`), `increment_2` (le `Direct(1)`),
`avec_cap` (le `maxLevel = NULL`), `sans_gate_compte` (`IsActiveAbilityCountedAsUsed`), et les trois
gates FORGES hors-ligne (`AreFriends` / `Hero` / `MachineOfWar`) que le live ne separe pas.

MESURE = `probe_521r1_talons_used_abilities.py` (ce fichier ne duplique NI le montage NI les
criteres : il appelle le probe, foyer unique -- meme discipline que
`test_521_talons_of_the_emperor_live.py`).

Le montage EXIGE ses regimes ; s'il ne les obtient pas, il ECHOUE, il ne skippe pas (#268) -- sauf
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
        # PROPRE A CE FICHIER -- le probe qui porte le montage ET les criteres :
        "scripts/python/probe_521r1_talons_used_abilities.py",
        # LE MOTEUR ENTIER, deliberement : le rejeu passe par `Runner.apply(ActiveAbilityMessage)`,
        # donc sa fermeture d'imports MESUREE traverse le dispatch de triggers et ses SIX registres,
        # le pipeline de degat, le PRNG, la couche d'effets (pose et increment de 1420), et le seed
        # `EffectsState` de `snapshot.load_state`. Enumerer les seuls fichiers de #521-r1 serait
        # DECLARER TROP ETROIT, et un declencheur trop etroit est un FAUX VERT ; large est sain.
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment, donc
        # `engine/*.py` (racine du paquet) n'est PAS couvert par `engine/**/*.py` seul.
        "scripts/python/*.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        "scripts/python/tests/**/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le port de 1330 (`runner/operations/triggers/loki/talons_of_the_emperor.py`), son "
              "inscription par le registre `PASSIVE_HELPER_ABILITY_TRIGGERS` "
              "(`triggers/dispatch/registry.py`) et sa collecte "
              "(`triggers/dispatch/core.py::collect_triggered_abilities`), le gate partage "
              "`fuelled_by_fury.py::is_active_ability_counted_as_used`, le helper d'arbre "
              "`abilities/behaviours/effects.py::add_effect_or_increase_level`, la LECTURE du "
              "compteur par 1195 (`runner/abilities/custodes.py`), et tout le moteur que le rejeu "
              "hors-ligne traverse. `build: True` parce que la confrontation du degat est au tirage "
              "pres.",
}

import os
import sys

import pytest

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import probe_521r1_talons_used_abilities as P                 # noqa: E402

_SEED = 52111


def _mesure(regime):
    try:
        sid = P._sid()
    except Exception as e:                                    # host injoignable != verdict du port
        pytest.skip("host indisponible (%s)" % (e,))
    sf = os.path.join(os.environ.get("TEMP", "."), "t521r1_%s_%s.json" % (regime, os.getpid()))
    m = (P.mesure_chaine(sid, sf, _SEED) if regime == "chaine"
         else P.mesure_normale(sid, sf, _SEED))
    if m is None:
        pytest.skip("build KO -- session/host indisponible")
    try:
        yield m
    finally:
        try:
            os.remove(sf)
        except OSError:
            pass


@pytest.fixture(scope="module")
def chaine():
    """Cast ALLIE puis cast du PORTEUR : les deux branches du `If` + le degat."""
    yield from _mesure("chaine")


@pytest.fixture(scope="module")
def attaque_normale():
    """Le TEMOIN NEGATIF : `IsActiveAbilityCountedAsUsed` ecarte l'attaque normale."""
    yield from _mesure("attaque_normale")


# ---------------------------------------------------------------- 0. le cablage, hors live

def test_le_registre_est_celui_du_bon_dict_natif():
    """1330 est montee par `...StaticBattleRules.ActiveAbility$$GetPassiveHelperAbility`
    (`<statics>+0x78`), PAS par `...$$GetDerivedTriggeredAbilities` (`<statics>+0x30`). Deux dicts
    natifs distincts, deux chemins de montage distincts -- et se tromper serait SILENCIEUX : le
    trigger ne serait inscrit sur personne et le compteur resterait fige.

    Le porteur ne porte 1330 par AUCUNE autre voie : son kit rend `passiveAbilities =
    ['DaughterOfTheAbyss']`, donc `ABILITY_TRIGGERS` ne peut pas la monter."""
    import gameconfig as GC
    from engine.runner.operations.triggers.dispatch.registry import (
        ABILITY_TRIGGERS, ACTIVE_ABILITY_TRIGGERS, PASSIVE_HELPER_ABILITY_TRIGGERS,
        RELIC_ABILITY_TRIGGERS)
    from engine.runner.operations.triggers.loki.talons_of_the_emperor import (
        TalonsOfTheEmperorUsedAbilitiesAbility as A, TALONS_OF_THE_EMPEROR_ID)

    assert PASSIVE_HELPER_ABILITY_TRIGGERS.get(TALONS_OF_THE_EMPEROR_ID) == [A], (
        "1330 doit etre inscrite sous la cle de l'ACTIVE 1195 dans le registre du dict "
        "`GetPassiveHelperAbility` -- c'est le seul chemin par lequel le natif la monte")
    # Les trois AUTRES registres ne doivent PAS la porter : une double inscription la ferait firer
    # deux fois par `On(0xe)`, donc incrementer de 2.
    for nom, reg in (("ABILITY_TRIGGERS", ABILITY_TRIGGERS),
                     ("ACTIVE_ABILITY_TRIGGERS", ACTIVE_ABILITY_TRIGGERS),
                     ("RELIC_ABILITY_TRIGGERS", RELIC_ABILITY_TRIGGERS)):
        double = [k for k, v in reg.items() if A in v]
        assert not double, "1330 inscrite AUSSI dans %s sous %r -- double fire" % (nom, double)
    # Le porteur n'a PAS 1330 en passiveAbilities : sans le nouveau registre, elle est orpheline.
    kit = GC.unit(P.CASTER) or {}
    assert TALONS_OF_THE_EMPEROR_ID in (kit.get("activeAbilities") or []), (
        "le kit de %s ne porte plus 1195 en active -- le chemin de montage a change" % P.CASTER)
    assert "TalonsOfTheEmperor_UsedAbilities" not in (kit.get("passiveAbilities") or [])


def test_les_litteraux_du_trigger_et_du_behaviour():
    """Les cinq litteraux du couple `CreateTrigger`/`CreateBehaviour`, transcrits et non deduits :
    l'evenement (`0xe`), les deux traits (`0x10` / `0x419`), le type d'effet (`0x58c`) et l'id de
    l'ability (`0x532`). Le `ownerNeedsToBeAlive = 1` du 3e argument d'`On` = `fire_on_death` FAUX."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.entities.effect_type import EffectType
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    import engine.runner.operations.triggers.loki.talons_of_the_emperor as T

    assert T.TalonsOfTheEmperorUsedAbilitiesAbility.event_id == int(
        EventTriggerType.UnitPostAbility) == 0xE
    assert T.TalonsOfTheEmperorUsedAbilitiesAbility.fire_on_death is False, (
        "`On(0xe, ownerNeedsToBeAlive = 1)` : le porteur DOIT etre vivant")
    assert int(T.TalonsOfTheEmperorUsedAbilitiesAbility.TRIGGERED_ABILITY_ID) == int(
        TriggeredAbilityType.TalonsOfTheEmperor_UsedAbilities) == 0x532
    assert T.TOTE_USED_ABILITIES == int(EffectType.TalonsOfTheEmperor_UsedAbilities) == 0x58C
    assert T._HERO == UnitTrait(0x10).name == "Hero"
    assert T._MACHINE_OF_WAR == UnitTrait(0x419).name == "MachineOfWar"
    # Le MEME ordinal nomme AUTRE CHOSE dans l'enum voisin -- c'est ce qui rend le NOM obligatoire
    # (une confusion d'enums a ordinal egal est SILENCIEUSE).
    assert EffectType(0x532).name != TriggeredAbilityType(0x532).name


def test_le_compteur_lu_et_le_compteur_ecrit_sont_LE_MEME():
    """Le port ECRIT 1420 dans `talons_of_the_emperor.py` et le LIT dans `custodes.py`. Si les deux
    constantes divergeaient, la triggered incrementerait un effet que 1195 ne regarde pas -- et le
    port resterait VERT sur le seul degat a compteur 0."""
    import engine.runner.abilities.custodes as CU
    import engine.runner.operations.triggers.loki.talons_of_the_emperor as T

    assert T.TOTE_USED_ABILITIES == CU.TOTE_USED_ABILITIES


def test_l_arbre_est_le_helper_de_factory_pas_un_collapse():
    """Artefact natif = `DSLBehaviors$$AddEffectOrIncreaseLevel` (factory COMPOSITE : un
    `ForeachBehaviour` dont le lambda construit `If(HasEffect, IncreaseEffectLevel, AddEffect)`).
    L'arbre porte doit donc etre un `Foreach` d'un `If`, pas une logique impurative recablee (#149)."""
    from engine.runner.abilities.behaviours.effects import IfBehaviour
    from engine.runner.operations.triggers.loki.talons_of_the_emperor import (
        talons_used_abilities_tree)

    arbre = talons_used_abilities_tree()
    assert type(arbre).__name__ == "Foreach", (
        "attendu un `ForeachBehaviour` (mirror de la factory), lu %r" % type(arbre).__name__)
    corps = arbre.body(None) if callable(getattr(arbre, "body", None)) else None
    assert isinstance(corps, IfBehaviour), (
        "le corps du Foreach doit etre le `If(HasEffect, IncreaseEffectLevel, AddEffect)` natif")


# ---------------------------------------------------------------- 1. le regime CHAINE

def test_chaine_le_verdict_du_probe(chaine):
    """Le verdict AGREGE : compteur aux deux etages, degat coup par coup, et les contre-epreuves
    qui doivent discriminer. Le detail est imprime par le probe (foyer unique des criteres)."""
    assert P.rapport_chaine(chaine)


def test_chaine_le_cast_ALLIE_fait_monter_le_compteur(chaine):
    """Etage [A] : `AreFriends(Owner, actor) & HasTrait(actor, Hero)` sur un allie DISTINCT du
    porteur, et branche **AddEffect** du `If` (le compteur part de 0)."""
    cl = chaine["compteurs_live"]
    a = chaine["portA"]["ref"]
    assert cl["c0"] == 0, "compteur de depart non nul (%s) : le regime ne mesure pas la POSE" % cl["c0"]
    assert cl["apres_allie"] == 1, (
        "le NATIF n'a pas incremente sur le cast allie (%s) -- regime degenere" % cl["apres_allie"])
    assert a["compteur_avant"] == 0
    assert a["compteur_apres"] == cl["apres_allie"]


def test_chaine_le_cast_DU_PORTEUR_compte_aussi(chaine):
    """Etage [B] : aucun `!AreEqual(Owner, actor)` dans la conjonction native -- Atlacoya castant sa
    PROPRE active compte pour elle-meme. Et c'est la branche **IncreaseEffectLevel** (1 -> 2)."""
    cl = chaine["compteurs_live"]
    b = chaine["portB"]["ref"]
    assert cl["apres_talons"] == 2, (
        "le NATIF n'a pas incremente sur le self-cast (%s)" % cl["apres_talons"])
    assert b["compteur_avant"] == 1
    assert b["compteur_apres"] == cl["apres_talons"]


def test_chaine_le_degat_lit_le_compteur_D_AVANT(chaine):
    """`On(0xe = UnitPostAbility)` est le DERNIER evenement d'`ActiveAbilityOperation$$
    ExecuteInternal` : l'increment arrive APRES le degat. Le cast de 1195 doit donc lire 1, pas 2 --
    et le degat doit etre bit-exact coup par coup."""
    cl = chaine["compteurs_live"]
    b, n = chaine["portB"]["ref"], chaine["natif_talons"]
    assert n["seq"], "aucun coup natif capte -- rien n'est confronte"
    assert b["used_abilities_level"] == cl["apres_allie"] == 1
    assert b["seq"] == n["seq"], "degat coup par coup : natif=%r port=%r" % (n["seq"], b["seq"])
    assert b["total"] == n["total"]
    assert n["profils"] == [P.DP_POWER], (
        "le regime vise la branche `else` (Power) : profils natifs lus %r" % (n["profils"],))


def test_chaine_les_contre_epreuves_discriminent(chaine):
    """Trois lectures du mirror, chacune mutee SEULE. Si l'une rendait le meme compteur que la
    reference, ce regime ne la mesurerait pas -- et l'accord serait fortuit."""
    b = chaine["portB"]
    ref = b["ref"]["compteur_apres"]
    assert b["sans_registre"]["compteur_apres"] != ref, (
        "registre vide -> meme compteur : l'INSCRIPTION n'est pas mesuree")
    assert b["increment_2"]["compteur_apres"] != ref, (
        "increment 2 -> meme compteur : le `Direct(1)` n'est pas mesure")
    assert b["avec_cap"]["compteur_apres"] != ref, (
        "cap a 1 -> meme compteur : le `maxLevel = NULL` n'est pas mesure")


def test_chaine_les_trois_gates_forges(chaine):
    """`AreFriends`, `HasTrait(Hero)` et `!HasTrait(MachineOfWar)` : le live ne les separe pas (un
    seul acteur y passe les trois). Ils sont donc evalues hors-ligne sur l'etat capture, avec le cas
    NOMINAL comme temoin -- sans lui, trois refus ne prouveraient rien."""
    f = chaine["forges"]
    assert f["allie_hero"] is True, "le cas NOMINAL ne matche pas : les refus ne prouvent rien"
    assert f["ennemi"] is False, "`AreFriends` : un acteur ENNEMI ne doit pas compter"
    assert f["sans_hero"] is False, "`HasTrait(actor, Hero)` : un non-Character ne compte pas"
    assert f["machine_of_war"] is False, "`!HasTrait(actor, MachineOfWar)` : une MoW ne compte pas"


# ---------------------------------------------------------------- 2. le TEMOIN NEGATIF

def test_normale_le_verdict_du_probe(attaque_normale):
    assert P.rapport_normale(attaque_normale)


def test_normale_le_compteur_NE_MONTE_PAS(attaque_normale):
    """L'attaque normale EST une active ability cote natif et emet `On(0xe)` : seul
    `IsActiveAbilityCountedAsUsed` l'ecarte. Des DEUX cotes le compteur doit rester a 0."""
    cl = attaque_normale["compteurs_live"]
    p = attaque_normale["port"]["ref"]
    assert attaque_normale["natif"]["coups"] > 0, (
        "aucun coup natif : l'attaque n'a pas eu lieu, le temoin ne temoigne de rien")
    assert cl["c0"] == 0
    assert cl["apres_attaque"] == 0, "le NATIF a compte une attaque NORMALE (%s)" % cl["apres_attaque"]
    assert p["compteur_apres"] == 0, "le PORT a compte une attaque normale que le natif ignore"


def test_normale_le_gate_est_bien_CE_QUI_DECIDE(attaque_normale):
    """La contre-epreuve qui rend ce temoin NON TRIVIAL : gate force a VRAI -> le compteur DOIT
    monter. Sans elle, un port qui n'aurait rien inscrit du tout passerait aussi."""
    p = attaque_normale["port"]
    assert p["sans_gate_compte"]["compteur_apres"] > p["ref"]["compteur_apres"], (
        "gate force a VRAI et le compteur ne bouge toujours pas : ce regime ne mesure PAS "
        "`IsActiveAbilityCountedAsUsed`, seulement l'absence d'inscription")
