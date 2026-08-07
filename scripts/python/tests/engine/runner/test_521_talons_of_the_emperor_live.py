"""GARDE de `1195 TalonsOfTheEmperor` (#521) -- la face COMBAT, ses DEUX branches, et la semantique
du selecteur qui les choisit.

Avant #521 l'ability etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, donc la decision
pouvait la choisir et l'execution l'ignorait -- 0 degat, 0 effet, AUCUNE erreur.

CE QUE LE PORT DOIT PRODUIRE, et ce que ce fichier garde :

    Execute( If( HasTrait(Target, Psyker)
                 | HasFaction(NonSteppableOrObjectUnits(AdjacentFriends(Caster, CasterTile, 1), 3),
                              Custodes),
                 AttackWithAttackDamage(..., GetDamageProfile2() = DirectDamage),
                 AttackWithAttackDamage(..., GetDamageProfile()  = Power) ) )

    degat des DEUX branches = Sum( MinMaxDamage(minDmg, maxDmg),
                                   Multiply( ConfigVar(extraDmg),
                                             If(HasEffect(Caster, 1420), EffectLevel, 0) ) )

QUATRE REGIMES, ET AUCUN N'EST DECORATIF.
  * ARMURE NON NULLE PARTOUT : `Power` perce 40 %, `DirectDamage` 100 %. A armure 0 les deux
    branches rendraient le MEME degat et l'etage `If` ne serait pas mesure du tout.
  * DEUX REGIMES DE COMPTEUR (0 et 1) : a compteur 0 le produit `extraDmg x EffectLevel` est NUL,
    donc un port qui IGNORERAIT `GetExtraDamage` serait bit-exact. 1195 etant **une fois par
    bataille** (aucun `cooldownTurns` au kit -- MESURE : `usable` reste `false` sur 10 cycles de
    tour apres le premier cast), le second regime s'obtient en faisant caster un ALLIE avant
    Atlacoya, pas en rejouant l'ability.
  * LES DEUX BRANCHES DU `If`, chacune par SA voie : `psyker` ferme le volet FACTION, `custodes`
    ferme le volet TRAIT. Une seule des deux laisserait l'autre non exercee.

ET LE COUPLE `mixte` / `mixte_inv`, qui garde ce que ce cas a MESURE (#521-r2) :
`HasFactionTrigger$$ShouldTrigger` resout son selecteur en UNE entite -- LA PREMIERE. Avec deux amis
adjacents de factions differentes, le natif rend `Power` quand le NON-Custodes est en tete de l'ordre
d'adjacence et `DirectDamage` quand c'est le Custodes. Le noeud porte faisait `any(...)` : il rendait
`DirectDamage` DANS LES DEUX, et c'est CE montage qui l'a montre. Si `entities/triggers.py::HasFaction`
repassait a `any`, `mixte` rougirait ; s'il passait a un `SingleOrDefault`, `mixte_inv` rougirait.

MESURE = `probe_521_talons_of_the_emperor.py` (ce fichier ne duplique NI le montage NI les criteres :
il appelle le probe, foyer unique -- meme discipline que `test_509_martial_inspiration_live.py`).

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
        "scripts/python/probe_521_talons_of_the_emperor.py",
        # LE MOTEUR ENTIER, deliberement : le rejeu passe par `Runner.apply(ActiveAbilityMessage)`,
        # donc sa fermeture d'imports MESUREE traverse le pipeline de degat, le PRNG, la couche
        # d'effets (l'aura `DaughterOfTheAbyss` du caster entre dans le regime `psyker`), le seed
        # `EffectsState` de `snapshot.load_state` et tout le domaine SELECTEUR (c'est un ordre
        # d'adjacence qui decide la branche). Enumerer les seuls fichiers de #521 serait DECLARER
        # TROP ETROIT, et un declencheur trop etroit est un FAUX VERT ; large est sain.
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment, donc
        # `engine/*.py` (racine du paquet) n'est PAS couvert par `engine/**/*.py` seul.
        "scripts/python/*.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        "scripts/python/tests/**/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le port de 1195 (arbre DSL `runner/abilities/custodes.py` : `If("
              "MeetSecondDamageProfileRequirement(), Attack(damageProfile_2), Attack(damageProfile))`"
              " + `damage_override` = `Sum(MinMaxDamage, GetExtraDamage)`), le noeud partage "
              "`entities/triggers.py::HasFaction` (repare en `SelectSingle` par ce cas), le cablage "
              "(registre `ABILITY_CLASSES`, `ABILITY_ATTACK_TYPE`, masque migre depuis "
              "`targeting.py`), le seed du compteur 1420 par `EffectsState`, et tout le moteur que "
              "le rejeu hors-ligne traverse. `build: True` parce que la confrontation est au tirage "
              "pres.",
}

import os
import sys

import pytest

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import probe_521_talons_of_the_emperor as P                   # noqa: E402


def _mesure(regime):
    try:
        sid = P._sid()
    except Exception as e:                                    # host injoignable != verdict du port
        pytest.skip("host indisponible (%s)" % (e,))
    sf = os.path.join(os.environ.get("TEMP", "."), "t521_%s_%s.json" % (regime, os.getpid()))
    m = P.mesure(sid, sf, 52101, P.BOARD, regime)
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
def power():
    """Branche `else` (Power), compteur 1420 = 0."""
    yield from _mesure("power")


@pytest.fixture(scope="module")
def power_n1():
    """MEME branche, compteur 1420 = 1 (un allie a caste avant) : l'etage `GetExtraDamage`."""
    yield from _mesure("power_n1")


@pytest.fixture(scope="module")
def psyker():
    """Branche `then` par `HasTrait(Target, Psyker)`."""
    yield from _mesure("psyker")


@pytest.fixture(scope="module")
def custodes():
    """Branche `then` par `HasFaction(<amis adjacents>, Custodes)`."""
    yield from _mesure("custodes")


@pytest.fixture(scope="module")
def mixte():
    """DEUX amis adjacents, le NON-Custodes en tete de l'ordre d'adjacence."""
    yield from _mesure("mixte")


@pytest.fixture(scope="module")
def mixte_inv():
    """Les MEMES deux amis, positions echangees."""
    yield from _mesure("mixte_inv")


# ---------------------------------------------------------------- 0. le cablage, hors live

def test_le_cablage_du_registre_est_complet():
    """Une ability qui entre dans `ABILITY_CLASSES` pose son masque ET son `AbilityAttackType`
    DANS LE MEME COMMIT, et SORT de `TARGETING_OPTIONS_UNPORTED` (contrat de disjonction : une
    ability a UNE source de masque, jamais deux). Sans masque, `get_invalid_target_reason` rend 0
    et le moteur accepte des casts que `ActiveAbilityOperation$$IsInvalidTarget` REFUSE."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (RANGED_BOOL_FALSE, RANGE_ADJACENT,
                                                   TARGETING_OPTIONS_UNPORTED)
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    cls = ABILITY_CLASSES.get(P.TALONS)
    assert cls is not None, "1195 absente d'ABILITY_CLASSES : c'est le NO-OP d'avant #521"
    assert P.TALONS not in TARGETING_OPTIONS_UNPORTED, (
        "1195 est portee ET encore dans TARGETING_OPTIONS_UNPORTED (disjonction rompue)")
    opts = getattr(cls, "TARGETING_OPTIONS", None)
    assert opts is not None, "1195 au registre SANS masque = gate de ciblage DESARME"
    # `<TargetingOptions statics>+0x68` = `<preset +0x40>+0x28` = 0x4000, LU dans le `.cctor`.
    assert int(opts.rules) == int(TR.TargetIsEnemy), (
        "masque 1195 attendu = TargetIsEnemy SEUL (preset statics+0x40), lu %s" % (opts.rules,))
    assert opts.self_cast is False
    assert opts.range == RANGE_ADJACENT
    assert opts.force_melee_target == RANGED_BOOL_FALSE
    # 3e argument LITTERAL d'`AActiveAbility..ctor(this, &opts, 2)` -- **2 = Others**, transcrit et
    # surtout pas deduit (1195 EST une attaque directe mono-cible).
    assert ABILITY_ATTACK_TYPE.get(P.TALONS) == AbilityAttackType.Others


def test_le_perimetre_hors_registre_a_perdu_son_entree():
    """Le CINQUIEME endroit du contrat de disjonction (#433) : la liste FIGEE des abilities du
    pool spawnable hors `ABILITY_CLASSES`. Une ability qui entre au registre en SORT dans le meme
    commit, sinon son masque aurait DEUX sources."""
    import importlib
    mod = importlib.import_module("tests.engine.test_433_r4_r2_r1_r2_ability_range_offline")
    assert P.TALONS not in mod.POOL_ABILITIES_WITHOUT_COMBAT_CLASS


def test_les_quatre_ids_du_gate_sont_dans_des_enums_DIFFERENTS():
    """Les quatre `mov edx, imm32` du corps natif designent QUATRE enums distincts. Les confondre
    aurait ete SILENCIEUX : `1195` est aussi un `EffectType`, `1002` aussi un `ActiveAbilityType`,
    `1420` aussi un `TriggeredAbilityType`. Ce test fige l'appariement NOM <-> ordinal MESURE a la
    conversion, ce que `probe_313` (mirror contre build) ne peut pas voir."""
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.entities.effect_type import EffectType
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.entities.unit_faction import UnitFaction
    import engine.runner.abilities.custodes as CU

    assert int(ActiveAbilityType.TalonsOfTheEmperor) == 0x4AB == P.TALONS
    assert CU.TOTE_USED_ABILITIES == int(EffectType.TalonsOfTheEmperor_UsedAbilities) == 0x58C
    assert CU.TOTE_PSYKER_TRAIT == int(UnitTrait.Psyker) == 0x3EA
    assert CU.TOTE_CUSTODES_FACTION == int(UnitFaction.Custodes) == 0x12
    # Les MEMES ordinaux NOMMENT AUTRE CHOSE ailleurs -- c'est ce qui rend le NOM obligatoire.
    assert EffectType(0x4AB).name != ActiveAbilityType(0x4AB).name
    assert ActiveAbilityType(0x3EA).name != UnitTrait(0x3EA).name


def test_les_deux_profils_viennent_de_la_CONFIG_et_sont_DIFFERENTS():
    """`GetDamageProfile` / `GetDamageProfile2` = `constants.damageProfile` / `damageProfile_2`.
    S'ils etaient egaux, l'etage `If` n'aurait aucun observable et TOUT ce fichier serait un vert
    de regime degenere -- d'ou l'assertion sur leur DIFFERENCE, pas seulement leur presence.
    Le PIERCING est ce qui les separe, et c'est lui que l'armure du montage exerce."""
    import gameconfig as GC
    from engine.runner.abilities.base import profile_pierce
    consts = (GC.ability("TalonsOfTheEmperor") or {}).get("constants") or {}
    p1, p2 = consts.get("damageProfile"), consts.get("damageProfile_2")
    assert p1 and p2 and p1 != p2, "les deux profils du kit 1195 : %r / %r" % (p1, p2)
    assert profile_pierce(None, p1) != profile_pierce(None, p2)
    # Les DEUX cles de bornes et de coups sont PARTAGEES par les deux branches (le decompile
    # rappelle `MinMaxDamage` et `GetHits`, jamais `MinMaxDamage2` / `GetHits2`) -- et le kit ne
    # porte AUCUNE cle `_2` de degat, donc un port qui aurait bascule dessus aurait lu du vide.
    v = (GC.ability("TalonsOfTheEmperor") or {}).get("variables") or {}
    assert "minDmg" in v and "maxDmg" in v and "extraDmg" in v
    assert "minDmg_2" not in v and "nrOfHits_2" not in consts


def test_1195_n_a_AUCUN_cooldown_au_kit():
    """La raison pour laquelle chaque regime est un BUILD : le kit 1195 ne porte pas de
    `cooldownTurns` (contraste `MartialInspiration`, qui en porte un), et le natif garde
    `CanUse = false` apres le premier cast. Si un build futur en ajoutait un, ce test rougirait et
    le montage « un cast par runner » redeviendrait discutable."""
    import gameconfig as GC
    consts = (GC.ability("TalonsOfTheEmperor") or {}).get("constants") or {}
    assert "cooldownTurns" not in consts
    ref = (GC.ability("MartialInspiration") or {}).get("constants") or {}
    assert "cooldownTurns" in ref, "temoin perime : le kit de reference n'a plus de cooldownTurns"


# ---------------------------------------------------------------- 1. le noeud partage, hors live

def _ctx(units, caster, faction_by_id):
    from engine.dsl.base import DslContext
    return DslContext(units=list(units), caster=caster,
                      faction_of=lambda u: faction_by_id.get((u or {}).get("id")))


def test_HasFaction_resout_UNE_entite_LA_PREMIERE():
    """`IdunBattle.Entities.Triggers.HasFactionTrigger$$ShouldTrigger` resout son selecteur en UNE
    entite puis teste `UnitExtensions.HasFaction` dessus -- il n'ITERE rien. Ce test fige la
    reparation de #521 sur le noeud NU : le `any(...)` d'avant rendait VRAI dans les deux ordres.

    C'est le pendant OFFLINE du couple live `mixte` / `mixte_inv` : si le noeud repassait a `any`,
    l'assertion `is False` tomberait ICI, sans runner."""
    from engine.entities.selectors.units import UnitSet
    from engine.entities.triggers import HasFaction
    from engine.entities.unit_faction import UnitFaction

    a = {"id": 1, "team": 1}          # NON-Custodes
    b = {"id": 2, "team": 1}          # Custodes
    fac = {1: "DarkAngels", 2: "Custodes"}
    ctx = _ctx([a, b], a, fac)
    cust = int(UnitFaction.Custodes)
    assert HasFaction(UnitSet([b, a]), cust).should_trigger(ctx) is True
    assert HasFaction(UnitSet([a, b]), cust).should_trigger(ctx) is False   # `any` aurait dit True
    assert HasFaction(UnitSet([]), cust).should_trigger(ctx) is False       # `unit == 0 -> 0`
    # Selecteur MONO-entite : le comportement est celui d'avant #521 (l'unique consommateur
    # historique, `HasFaction(Target(), Sisterhood)` de ThriceBlessedConflagration, est ici).
    assert HasFaction(UnitSet([b]), cust).should_trigger(ctx) is True
    assert HasFaction(UnitSet([a]), cust).should_trigger(ctx) is False


def test_le_gate_est_une_DISJONCTION_et_ses_deux_volets_sont_lus():
    """`op_BitwiseOr(HasTrait(Target, Psyker), HasFaction(<amis>, Custodes))` : chacun des deux
    volets suffit SEUL. Monte hors live sur un contexte minimal -- si l'un des deux disparaissait
    de l'arbre, une des quatre lignes ci-dessous tomberait sans qu'aucun runner soit necessaire."""
    from engine.dsl.base import DslContext
    from engine.entities.traits.unit_trait import UnitTrait
    import engine.runner.abilities.custodes as CU

    caster = {"id": 1, "team": 1}
    cible = {"id": 2, "team": 2}

    def ctx(psyker_cible, ami_custodes):
        amis = [{"id": 3, "team": 1}] if ami_custodes is not None else []
        return DslContext(
            units=[caster, cible] + amis, caster=caster, target=cible,
            faction_of=lambda u: (ami_custodes if (u or {}).get("id") == 3 else "Necrons"),
            has_trait=lambda u, t: (psyker_cible and (u or {}).get("id") == 2
                                    and int(t) == int(UnitTrait.Psyker)))

    # Les deux volets sont montes SEPAREMENT : le volet FACTION passe par un selecteur GEOMETRIQUE
    # (AdjacentFriends), non montable sans board -- on l'exerce ici sur son noeud nu, et le volet
    # complet est confronte LIVE par les regimes `custodes` / `mixte`.
    from engine.entities.selectors.units import UnitSet
    from engine.entities.triggers import HasFaction, HasTrait, TriggerOr
    from engine.entities.selectors.accessors import Target

    def gate(sel):
        return TriggerOr(HasTrait(Target(), CU.TOTE_PSYKER_TRAIT),
                         HasFaction(sel, CU.TOTE_CUSTODES_FACTION))

    ami = [{"id": 3, "team": 1}]
    assert gate(UnitSet([])).should_trigger(ctx(True, None)) is True        # TRAIT seul
    assert gate(UnitSet(ami)).should_trigger(ctx(False, "Custodes")) is True   # FACTION seule
    assert gate(UnitSet(ami)).should_trigger(ctx(True, "Custodes")) is True    # les deux
    assert gate(UnitSet(ami)).should_trigger(ctx(False, "DarkAngels")) is False   # aucun


# ---------------------------------------------------------------- 2. la confrontation LIVE

def _cast_unique(m):
    assert len(m["casts"]) == 1, "1195 est once-per-battle : un cast par runner, %d mesure(s)" % (
        len(m["casts"]),)
    return m["casts"][0]


def _assert_cast(c, profil_attendu=None):
    sp, sn = c["port"]["seq"], c["natif"]["seq"]
    assert c["port"]["ported"] is True, "1195 non routee par le registre (NO-OP)"
    assert sn, "aucun `UnitDamaged` natif attribue a 1195"
    assert sp == sn, "SEQUENCE divergente : port=%r natif=%r" % (sp, sn)
    assert len(c["natif"]["profils"]) == 1, "profils natifs multiples : %r" % (c["natif"]["profils"],)
    pn = c["natif"]["profils"][0]
    assert c["port"]["profil"] == pn, "PROFIL divergent : port=%s natif=%s" % (c["port"]["profil"], pn)
    if profil_attendu is not None:
        assert pn == profil_attendu, (
            "le natif rend le profil %s, la LECTURE du decompile en attendait %s" % (pn, profil_attendu))
    assert c["port"]["compteur"] == c["compteur_live"], (
        "le compteur 1420 seede hors-ligne (%s) differe du LIVE (%s)"
        % (c["port"]["compteur"], c["compteur_live"]))
    # ATTRIBUTION EXACTE DES TIRAGES (2 par coup a cc = 0, famille ATTACK).
    assert c["tirages_port"] == P.TIRAGES_PAR_COUP * len(sp)
    assert c["tirages_natif"] == P.TIRAGES_PAR_COUP * c["natif"]["coups_tous"], (
        "les tirages natifs ne bouclent pas : %s pour %d coups"
        % (c["tirages_natif"], c["natif"]["coups_tous"]))
    ref = (c.get("ab") or {}).get("ref")
    assert ref and ref["seq"] == sn, "l'arbre du module ne rend pas la sequence native"


def _assert_contre_epreuves(c):
    """CHAQUE contre-epreuve attendue doit diverger : sinon la lecture qu'elle retire n'est pas
    mesuree par ce regime, et l'accord serait un accord de hasard."""
    sn = c["natif"]["seq"]
    attendues = P._attendues_divergentes(c["natif"]["profils"][0], c["compteur_live"])
    assert attendues, "aucune contre-epreuve discriminante dans ce regime -- il ne mesure rien"
    for nom in attendues:
        assert c["ab"][nom]["seq"] != sn, "contre-epreuve %s NON discriminante" % nom


def test_power_branche_else(power):
    """Profil `Power`, compteur 0 : le TEMOIN. `profil_fixe_direct` doit diverger, sinon l'armure
    du montage ne mord pas et l'etage `If` n'est pas mesure."""
    c = _cast_unique(power)
    _assert_cast(c, P.DP_POWER)
    _assert_contre_epreuves(c)
    assert c["compteur_live"] == 0
    assert c["port"]["extra"] == 0, "compteur 0 -> le produit extraDmg x EffectLevel doit etre NUL"


def test_power_n1_l_etage_GetExtraDamage(power_n1, power):
    """Le SECOND regime de compteur. `sans_extra` doit diverger ICI et PAS dans `power` : c'est
    exactement ce qui distingue « le port lit le compteur » de « le port l'ignore »."""
    c = _cast_unique(power_n1)
    _assert_cast(c, P.DP_POWER)
    _assert_contre_epreuves(c)
    assert c["compteur_live"] == 1, "le pre-cast d'allie n'a pas fait avancer le compteur 1420"
    assert c["port"]["extra"] > 0
    # NON DEGENERE : les deux regimes de compteur sont DISTINCTS et le degat en depend.
    c0 = _cast_unique(power)
    assert c0["compteur_live"] != c["compteur_live"]
    assert c["natif"]["total"] > c0["natif"]["total"], (
        "compteur 1 ne fait pas plus de degat que compteur 0 : le bonus n'est pas exerce")
    # Le TERME est celui du gameconfig, pas un scalaire fitte : `extraDmg[level] x multiplier`.
    assert c["ab"]["ref"]["total"] - c["ab"]["sans_extra"]["total"] == c["port"]["extra"]


def test_psyker_branche_then_par_le_TRAIT(psyker):
    """`HasTrait(Target, Psyker)` SEUL ouvre la branche : `faction_seule` (qui ampute ce volet) doit
    diverger, sinon le volet TRAIT n'est pas ce qui decide ici."""
    c = _cast_unique(psyker)
    _assert_cast(c, P.DP_DIRECT_DAMAGE)
    _assert_contre_epreuves(c)
    assert c["ab"]["faction_seule"]["seq"] != c["natif"]["seq"], (
        "sans le volet TRAIT le resultat ne change pas : ce regime ne mesure pas HasTrait")
    assert c["ab"]["psyker_seul"]["seq"] == c["natif"]["seq"]


def test_custodes_branche_then_par_la_FACTION(custodes):
    """`HasFaction(<amis adjacents>, Custodes)` SEUL ouvre la branche : `psyker_seul` (qui ampute ce
    volet) doit diverger."""
    c = _cast_unique(custodes)
    _assert_cast(c, P.DP_DIRECT_DAMAGE)
    _assert_contre_epreuves(c)
    assert c["ab"]["psyker_seul"]["seq"] != c["natif"]["seq"], (
        "sans le volet FACTION le resultat ne change pas : ce regime ne mesure pas HasFaction")
    assert c["ab"]["faction_seule"]["seq"] == c["natif"]["seq"]


def test_mixte_et_mixte_inv_figent_la_semantique_du_selecteur(mixte, mixte_inv):
    """#521-r2, MESURE : le natif prend LE PREMIER ami adjacent, pas « un quelconque ».

    Les deux arrangements ne different QUE par l'echange de deux tuiles ; le natif change de branche.
    C'est cela qui separe les trois hypotheses -- `any` aurait rendu `DirectDamage` dans les deux,
    un `SingleOrDefault` `Power` dans les deux."""
    cm, ci = _cast_unique(mixte), _cast_unique(mixte_inv)
    _assert_cast(cm)
    _assert_cast(ci)
    v, (a, b) = P.semantique_hasfaction(mixte, mixte_inv)
    assert v == "premier", (
        "semantique native de HasFaction : %r (mixte=%s, mixte_inv=%s) -- le port doit la suivre"
        % (v, a, b))
    assert a == P.DP_POWER and b == P.DP_DIRECT_DAMAGE
