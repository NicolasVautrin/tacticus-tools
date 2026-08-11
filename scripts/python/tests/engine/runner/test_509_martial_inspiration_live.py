"""GARDE de `1191 MartialInspiration` (#509) -- la face COMBAT, et le compteur qui l'indexe.

Avant #509 l'ability etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, donc la face
DECISION la choisissait (playbook porte depuis #106) et l'execution l'ignorait -- 0 degat, 0 effet,
AUCUNE erreur.

CE QUE LE PORT DOIT PRODUIRE, et ce que ce fichier garde :

    Execute( AddEffect(1408 MartialInspiration_ExtraDamage, source = Caster, targets = Caster,
                       turns = Direct(1))
             op_BitwiseAnd
             AttackWithAttackDamage(Caster, Target, MinMaxDamage, Eviscerate, nrOfHits = 3) )

    effet 1408 : ForPercentIncrease( OwnerIsCaster
                                     & (CurrentAbilityIs(ActiveAbilityType 1191)
                                        | CurrentAbilityIs(TriggeredAbilityType 1319)),
                                     ConfigVar(extraDmgPct) x TotalTurnsWithAttacksMade(Owner) )

DEUX REGIMES DE COMPTEUR, et le second est OBLIGATOIRE. A `TotalTurnsWithAttacksMade == 0` le
produit est NUL : un port qui IGNORERAIT l'effet serait bit-exact. Le montage DRIVE donc Kariyan
jusqu'a ce que le compteur ait avance, et exige au moins DEUX regimes distincts -- sinon il
ECHOUE, il ne rend pas un vert de regime degenere.

DEUX REGIMES D'ARMURE, et le second n'est pas decoratif : `EffectBonus.ForPercentIncrease` ecrit
la %-list du `DamageModifiers` ATTAQUANT, appliquee APRES percage/armure. A armure 0 un port qui
scalerait les BORNES D'ARME donnerait le meme resultat.

CE QUI EST ASSERTIONNE, et pourquoi ce n'est pas un total :
  * la SEQUENCE coup par coup (`UnitDamaged` natifs filtres sur `Active_Ability_Type = 1191` vs
    les `per_hit_health` du port) ;
  * l'ATTRIBUTION EXACTE DES TIRAGES `genrand_int32` : le natif en consomme `2 x <TOUS ses coups>`,
    et le PORT AUTANT depuis #928 -- l'ecart d'avant etait, exactement, les coups de la triggered
    `1319 LegacyOfCombat` (passif de Kariyan), alors NON PORTEE. Mesure (`MC1_67`/50901, regime
    nominal) : AVANT port 6 / natif 18, APRES port 18 / natif 18, sur les DEUX regimes de compteur.
    Le critere est donc l'EGALITE port/natif, plus `2 x coups`. L'identite est VERIFIEE, pas
    supposee ;
  * les TROIS contre-epreuves, chacune ne retirant QU'UNE lecture du mirror. `sans_ability_type`
    est celle qui a MORDU pendant #509 : le port omettait le 7e argument natif
    (`abilityOrEffect = AbilityOrEffect(this)`), donc le gate `CurrentAbilityIs(1191)` restait
    ferme -- bit-exact a compteur 0, faux d'un facteur `1 + n x 33 %` partout ailleurs.

MESURE = `probe_509_martial_inspiration.py` (ce fichier ne duplique NI le montage NI les criteres :
il appelle le probe, foyer unique -- meme discipline que `test_504_kill_maim_burn_live.py`).

Le montage EXIGE ses regimes ; s'il ne les obtient pas, il ECHOUE, il ne skippe pas (#268) --
sauf indisponibilite du host, qui n'est pas un verdict sur le port. ASCII only.
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
        "scripts/python/probe_509_martial_inspiration.py",
        # LE MOTEUR ENTIER, deliberement : le rejeu passe par `Runner.apply(ActiveAbilityMessage)`,
        # donc sa fermeture d'imports MESUREE traverse le pipeline de degat, le PRNG, la couche
        # d'effets, le seed `actorStats` de `snapshot.load_state` et le chokepoint post-resolution
        # `_apply_damage_pipeline` (ou vit desormais `register_attack_made`) -- tous capables de
        # deplacer une valeur bit-exacte. Enumerer les seuls fichiers de #509 serait DECLARER TROP
        # ETROIT, et un declencheur trop etroit est un FAUX VERT ; large est sain.
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment, donc
        # `engine/*.py` (racine du paquet) n'est PAS couvert par `engine/**/*.py` seul -- et
        # `scripts/python/**/*.py` seul raterait `scripts/python/board.py`.
        "scripts/python/*.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        "scripts/python/tests/**/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le port de 1191 (arbre DSL `runner/abilities/custodes.py` : "
              "`AddEffect(1408) op_BitwiseAnd AttackWithAttackDamage(Target)`), l'effet "
              "`entities/effects/loki/martial_inspiration.py` et son gate `CurrentAbilityIs`, le "
              "compteur `ActorStatisticsComponent+0x30` (`components.register_attack_made` / "
              "`unit_turns_with_attacks_made` / `reset_units_attacked_this_turn`), son seed "
              "`snapshot._load_actor_statistics`, le canal `att_ctx['ability_type']` de "
              "`damage_model.attacker_modifiers`, le cablage (registre `ABILITY_CLASSES`, "
              "`ABILITY_ATTACK_TYPE`, masque migre depuis `targeting.py`) -- et tout le moteur que "
              "le rejeu hors-ligne traverse. `build: True` parce que la sequence confronte le "
              "NATIF au tirage pres.",
}

import os
import sys

import pytest

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import probe_509_martial_inspiration as P                     # noqa: E402


def _mesure(regime):
    try:
        sid = P._sid()
    except Exception as e:                                    # host injoignable != verdict du port
        pytest.skip("host indisponible (%s)" % (e,))
    sf = os.path.join(os.environ.get("TEMP", "."), "t509_%s_%s.json" % (regime, os.getpid()))
    m = P.mesure(sid, sf, 50901, P.BOARD, regime, tours=6)
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
def nominal():
    """Armure 0 : le ratio du bonus se lit en clair."""
    yield from _mesure("nominal")


@pytest.fixture(scope="module")
def armure():
    """Armure NON nulle : l'etage `%-list APRES percage/armure` est exerce."""
    yield from _mesure("armure")


# ---------------------------------------------------------------- 0. le cablage, hors live

def test_le_cablage_du_registre_est_complet():
    """Une ability qui entre dans `ABILITY_CLASSES` pose son masque ET son `AbilityAttackType`
    DANS LE MEME COMMIT, et SORT de `TARGETING_OPTIONS_UNPORTED` (contrat de disjonction : une
    ability a UNE source de masque, jamais deux). Sans masque, `get_invalid_target_reason` rend 0
    et le moteur accepte des casts que `ActiveAbilityOperation$$IsInvalidTarget` REFUSE."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    cls = ABILITY_CLASSES.get(P.MARTIAL_INSPIRATION)
    assert cls is not None, "1191 absente d'ABILITY_CLASSES : c'est le NO-OP d'avant #509"
    assert P.MARTIAL_INSPIRATION not in TARGETING_OPTIONS_UNPORTED, (
        "1191 est portee ET encore dans TARGETING_OPTIONS_UNPORTED (disjonction rompue)")
    opts = getattr(cls, "TARGETING_OPTIONS", None)
    assert opts is not None, "1191 au registre SANS masque = gate de ciblage DESARME"
    # `<TargetingOptions statics>+0x68` = `<preset +0x40>+0x28` = 0x4000, LU dans le `.cctor`.
    assert int(opts.rules) == int(TR.TargetIsEnemy), (
        "masque 1191 attendu = TargetIsEnemy SEUL (preset statics+0x40), lu %s" % (opts.rules,))
    assert opts.self_cast is False
    # 3e argument LITTERAL d'`AActiveAbility..ctor(this, &opts, 0)`.
    assert ABILITY_ATTACK_TYPE.get(P.MARTIAL_INSPIRATION) == AbilityAttackType.DirectTargetAttack


def test_le_perimetre_hors_registre_a_perdu_son_entree():
    """Le CINQUIEME endroit du contrat de disjonction (#433) : la liste FIGEE des abilities du
    pool spawnable hors `ABILITY_CLASSES`. Une ability qui entre au registre en SORT dans le meme
    commit, sinon son masque aurait DEUX sources."""
    import importlib
    mod = importlib.import_module("tests.engine.test_433_r4_r2_r1_r2_ability_range_offline")
    assert P.MARTIAL_INSPIRATION not in mod.POOL_ABILITIES_WITHOUT_COMBAT_CLASS


def test_l_effet_1408_est_au_registre_des_effets():
    """Sans cette entree, `EffectFactory.create` rendrait un `BaseEffect` NU : l'effet serait pose,
    `active`, et ne contribuerait RIEN -- exactement le no-op silencieux d'avant, deplace d'un
    cran. La cle est le NOM gameconfig, apparie au membre d'enum (jamais un ordinal nu)."""
    from engine.entities.effect_type import EffectType
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki.martial_inspiration import MartialInspirationExtraDamageEffect
    assert EFFECT_CLASSES.get(EffectType.MartialInspiration_ExtraDamage.name) is \
        MartialInspirationExtraDamageEffect


def test_les_deux_ids_du_gate_sont_dans_des_enums_DIFFERENTS():
    """Les trois `mov edx, imm32` du corps natif passent par TROIS surcharges d'`op_Implicit`
    (`set_ActiveAbility` / `set_TriggeredAbility` / `set_Effect`). Confondre les enums aurait ete
    SILENCIEUX : `1191` est aussi un `TriggeredAbilityType` et un `EffectType`, `1319` est aussi un
    `EffectType`. Ce test fige l'appariement NOM <-> ordinal mesure a la conversion."""
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.entities.effect_type import EffectType
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.entities.effects.loki import martial_inspiration as MI
    assert MI.CURRENT_ACTIVE_ABILITY == int(ActiveAbilityType.MartialInspiration) == 0x4A7
    assert MI.CURRENT_TRIGGERED_ABILITY == int(TriggeredAbilityType.LegacyOfCombat) == 0x527
    assert int(EffectType.MartialInspiration_ExtraDamage) == 0x580
    # Les MEMES ordinaux NOMMENT AUTRE CHOSE ailleurs -- c'est ce qui rend le NOM obligatoire.
    assert TriggeredAbilityType(0x4A7).name != ActiveAbilityType(0x4A7).name
    assert EffectType(0x527).name != TriggeredAbilityType(0x527).name


# ---------------------------------------------------------------- 1. l'effet, hors live

def test_le_gate_CurrentAbilityIs_ferme_sans_canal():
    """`att_ctx["ability_type"]` ABSENT (attaque normale, appelant historique) => gate FERME,
    jamais « inconnu = vrai ». Et un id qui n'est NI 1191 NI 1319 le ferme aussi."""
    from engine.entities.effects.loki.martial_inspiration import MartialInspirationExtraDamageEffect
    e = MartialInspirationExtraDamageEffect(name="MartialInspiration_ExtraDamage",
                                            effect_type=0x580, active_ability_level=50)
    assert e.create_effect_damage_bonus_for_attack(att_ctx=None) is None
    assert e.create_effect_damage_bonus_for_attack(
        att_ctx={"turns_with_attacks_made": 3}) is None
    assert e.create_effect_damage_bonus_for_attack(
        att_ctx={"ability_type": 1043, "turns_with_attacks_made": 3}) is None


def test_la_magnitude_est_le_PRODUIT_pct_x_compteur():
    """`Multiply(ConfigVar(extraDmgPct), TotalTurnsWithAttacksMade(Owner))`. Compteur nul =>
    produit nul => AUCUNE contribution (et non un `EffectBonus` de valeur 0)."""
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.effects.loki.martial_inspiration import MartialInspirationExtraDamageEffect
    pct = int(ability_var("MartialInspiration", "extraDmgPct", 50) or 0)
    assert pct > 0, "extraDmgPct introuvable dans le gameconfig -- mesure impossible"
    e = MartialInspirationExtraDamageEffect(name="MartialInspiration_ExtraDamage",
                                            effect_type=0x580, active_ability_level=50)
    assert e.create_effect_damage_bonus_for_attack(
        att_ctx={"ability_type": 1191, "turns_with_attacks_made": 0}) is None
    for n in (1, 2, 3):
        b = e.create_effect_damage_bonus_for_attack(
            att_ctx={"ability_type": 1191, "turns_with_attacks_made": n})
        assert b is not None and b.kind == "PercentIncrease" and b.value == pct * n
    # La branche TRIGGERED existe dans le mirror, meme si le port ne l'alimente pas encore.
    b = e.create_effect_damage_bonus_for_attack(
        att_ctx={"ability_type": 1319, "turns_with_attacks_made": 2})
    assert b is not None and b.value == pct * 2


def test_le_compteur_n_avance_qu_une_fois_par_tour():
    """`RegisterAttackMade` : `if (Count(+0x40) == 0) +0x30 += 1`. Deux attaques dans le MEME tour
    n'avancent le compteur qu'une fois ; c'est `ResetUnitsAttackedThisTurn` (entree de tour) qui
    rouvre la fenetre. Un port qui incrementerait a CHAQUE attaque rendrait, sur ce montage,
    `3` la ou le natif rend `2`."""
    from engine.runner.components import (UnitComponent, register_attack_made,
                                          reset_units_attacked_this_turn,
                                          unit_turns_with_attacks_made)
    from engine.runner.state import State
    st = State()
    att = st.add_entity()
    att.add_component(UnitComponent(visual_id="custoBladeChampion", alive=True))
    a, b = st.add_entity(), st.add_entity()
    assert unit_turns_with_attacks_made(st, att.id) == 0
    register_attack_made(st, att.id, a.id)
    register_attack_made(st, att.id, b.id)                 # MEME tour, cible differente
    register_attack_made(st, att.id, a.id)                 # MEME tour, MEME cible
    assert unit_turns_with_attacks_made(st, att.id) == 1
    reset_units_attacked_this_turn(st, att.id)             # StartTurnOperation
    register_attack_made(st, att.id, a.id)
    assert unit_turns_with_attacks_made(st, att.id) == 2


# ---------------------------------------------------------------- 2. la confrontation LIVE

def _assert_regimes(m):
    regimes = sorted({c["compteur_live"] for c in m["casts"]})
    assert len(m["casts"]) >= 2, "montage sterile : %d cast(s) mesure(s)" % len(m["casts"])
    assert len(regimes) >= 2, (
        "REGIME DEGENERE : un seul compteur (%r) -- l'accord ne prouverait PAS l'effet" % regimes)
    assert max(regimes) >= 1, "le compteur n'a jamais avance : le bonus reste nul partout"


def _assert_cast(c):
    sp, sn = c["port"]["seq"], c["natif"]["seq"]
    assert c["port"]["ported"] is True, "1191 non routee par le registre"
    assert sn, "aucun `UnitDamaged` natif attribue a 1191"
    assert sp == sn, ("SEQUENCE divergente au compteur %s : port=%r natif=%r"
                      % (c["compteur_live"], sp, sn))
    assert c["port"]["compteur_avant"] == c["compteur_live"], (
        "le compteur seede hors-ligne (%s) differe du LIVE (%s)"
        % (c["port"]["compteur_avant"], c["compteur_live"]))
    # ATTRIBUTION EXACTE DES TIRAGES (2 par coup a cc = 0, famille ATTACK).
    assert c["tirages_port"] == P.TIRAGES_PAR_COUP * len(sp)
    assert c["tirages_natif"] == P.TIRAGES_PAR_COUP * c["natif"]["coups_tous"], (
        "les tirages natifs ne bouclent pas : %s pour %d coups"
        % (c["tirages_natif"], c["natif"]["coups_tous"]))


def _assert_contre_epreuves(c):
    """A compteur > 0, CHAQUE contre-epreuve doit diverger : sinon la lecture qu'elle retire n'est
    pas mesuree par ce montage, et l'accord serait un accord de hasard."""
    if not c["compteur_live"]:
        return
    ab, sn = c["ab"], c["natif"]["seq"]
    assert ab["ref"]["seq"] == sn, "l'arbre du module ne rend pas la sequence native"
    for nom in ("sans_effet", "ordre_inverse", "sans_ability_type"):
        assert ab[nom]["seq"] != sn, "contre-epreuve %s NON discriminante" % nom


@pytest.mark.parametrize("nom", ["nominal"])
def test_nominal_sequence_et_tirages(nominal, nom):
    _assert_regimes(nominal)
    for c in nominal["casts"]:
        _assert_cast(c)
        _assert_contre_epreuves(c)


def test_nominal_le_bonus_vaut_exactement_pct_x_compteur(nominal):
    """L'etage MAGNITUDE, isole par la contre-epreuve `sans_effet` (une seule variable change).
    A armure 0 le rapport est exactement `1 + n x extraDmgPct/100`."""
    from engine.entities.effects.magnitude import ability_var
    pct = int(ability_var("MartialInspiration", "extraDmgPct", 50) or 0)
    vus = 0
    for c in nominal["casts"]:
        n = c["compteur_live"]
        if not n:
            continue
        ref, sans = c["ab"]["ref"]["total"], c["ab"]["sans_effet"]["total"]
        assert sans > 0
        attendu = 1.0 + (n * pct) / 100.0
        assert abs(ref / float(sans) - attendu) < 1e-3, (
            "compteur %s : ratio %.4f, attendu %.4f" % (n, ref / float(sans), attendu))
        vus += 1
    assert vus >= 1, "aucun cast a compteur > 0 : l'etage magnitude n'est PAS mesure"


def test_armure_sequence_et_tirages(armure):
    """L'ETAGE : `ForPercentIncrease` ecrit la %-list ATTAQUANT, appliquee APRES percage/armure.
    Un port qui scalerait les bornes d'arme serait bit-exact a armure 0 et FAUX ici."""
    _assert_regimes(armure)
    for c in armure["casts"]:
        _assert_cast(c)
        _assert_contre_epreuves(c)
    # Le regime doit etre NON DEGENERE : l'armure doit MORDRE (degats < ceux du nominal).
    assert all(a < 5000 for c in armure["casts"] for _t, a in c["natif"]["seq"]), (
        "l'armure ne mord pas -- le regime ne mesure pas l'etage qu'il vise")
