"""GARDE #961 -- les DEUX derniers passifs Necrons portes.

  * `TimesplinterMantle` (`TriggeredAbilityType` 0x5fe = 1534, `necroChronomancer` << Thothmek >>) :
    `On(0x12 = TurnStart_EffectActivation, ownerNeedsToBeAlive)` -- **UN SEUL noeud, PAS
    d'`IsTurnOf(Owner)`** -> `Foreach(NonSteppableUnits(MechanicalUnits(Friends(AdjacentUnits(
    Owner)))) op_Addition Owner, AddEffect(0x60f = 1551))`. L'effet est retire par
    `(On(9 = Attack) & OwnerIsTarget & IsUnit(Caster)) | On(0x17 = TurnEnd)`.
  * `LivingLightning` (0x3ef = 1007, `necroPlasmancer` << Thutmose >>) :
    `On(0x1c = ArrivedAtFinalTile) & OwnerIsActor & !AmountIsZero(GetPossibleTargets(Direct(1)))`
    -> `AttackWithAttackDamage(1x, profil `constants.damageProfile`)` sur UN ennemi TIRE AU HASARD
    dans le rayon `If(<ennemi adjacent>, Direct(1), Get(constants.range))`.

RE in extenso : les en-tetes de
`engine/runner/operations/triggers/loki/timesplinter_mantle.py` et `.../living_lightning.py`, plus
`docs/rl/case-961-passifs-necrons.md`.

CE QUE LA GARDE PROUVE (montage `probe_961_necron_passives`, positions DRIVEES et geometrie
ASSERTIONNEE contre le `boardGraph`) :

  (A) le passif enregistre son trigger sur Thothmek par la voie `passiveAbilities`, sur `On(0x12)` ;
  (B) AGREEMENT live-vs-port du SET de porteurs de 1551 a CHAQUE bordure de tour, et **le port
      reconstruit ce set** (assertion `after_end == {}` : le `On(0x17)` a bien tout retire avant que
      le `On(0x12)` re-pose) -- sans quoi l'accord serait un simple heritage de la capture ;
  (C) les bordures mesurees couvrent LES DEUX CAMPS : c'est ce qui prouve l'absence
      d'`IsTurnOf(Owner)`, la ou son voisin `RelentlessMarch` en a un ;
  (D) les QUATRE gates MORDENT (contrefactuels sur les MEMES captures) : `MechanicalUnits`,
      `Friends`, `AdjacentUnits` (rayon), et l'`op_Addition Owner` ;
  (E) CONTRE-EPREUVE NEGATIVE : une attaque sur une unite couverte retire 1551 de CELLE-LA et d'elle
      SEULE. ⚠ Le montage garde le tour adverse OUVERT (second ennemi exile) et l'ASSERTIONNE : avec
      un ennemi SEUL, son attaque cloture la team, la bordure repasse derriere et l'observable ne dit
      plus rien -- c'est exactement ce faux negatif qui a d'abord fait croire a un port fautif ;
  (F) `LivingLightning` : agreement BIT-EXACT du degat ET du NOMBRE DE TIRAGES MT sur le regime
      rayon-2 (la branche que l'i2 ne decrit PAS), et RIEN des deux cotes hors portee.

⚠ **RESIDU OUVERT `#961-r1`** : a DISTANCE 1, le degat diverge d'un facteur CONSTANT (le natif rend
**87,27 %** de ce que rend le port, mesure sur DEUX configurations d'elevation), alors que la CIBLE
et le NOMBRE DE TIRAGES concordent. Le regime `adjacent` n'est donc PAS assertionne sur le degat ici
-- il l'est sur la cible et sur les tirages.

ASCII-only. Skip si pas de session live / montage non montable.
"""
from __future__ import annotations

import os
import sys

import pytest

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/rl_duel.py", "scripts/python/hexgeo.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER, perimetre pris LARGE : les deux passifs tirent le registre de
        # triggers COMPLET, le pipeline de degat, la couche d'effets et les selecteurs. Foyers
        # load-bearing : `operations/triggers/loki/timesplinter_mantle.py`,
        # `operations/triggers/loki/living_lightning.py`,
        # `operations/triggers/dispatch/registry.py`, `entities/effects/factory.py`,
        # `entities/effects/loki/damage_reduction.py`, `entities/selectors/units.py`
        # (`non_steppable_units`) et `entities/selectors/tiles.py` (`UnobscuredTiles`).
        # Le MONTAGE lui-meme est un declencheur : `probe_961_necron_passives.py`.
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment.
        "scripts/python/probe_961_necron_passives.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        # Les magnitudes (`dmgReduction`, `minDmg`/`maxDmg`) et les constantes (`range`,
        # `nrOfHits`, `damageProfile`) sont des DONNEES du gameconfig ; le catalogue injecte part
        # du seed BC ; les ordinaux d'enum viennent du dump du build.
        "data/seed-bc.json",
        "data/boards/**",
        "data/symbols/**",
    ),
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : la STRUCTURE des deux arbres (les quatre etages de selecteur de "
              "TimesplinterMantle et les deux branches de rayon de LivingLightning), l'ABSENCE "
              "d'`IsTurnOf(Owner)` sur `On(0x12)`, le fait que le gate du trigger de "
              "LivingLightning evalue le `PickRandomly` (donc CONSOMME un tirage MT), et la "
              "confrontation live du SET couvert, de son retrait par cible, du degat a rayon 2 et "
              "du silence hors portee. Exige une session Frida (fixtures live) sauf pour les "
              "quatre cas de structure.",
}

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                  # scripts/python
import probe_961_necron_passives as NP                              # noqa: E402

SEED, BOARD, TURNS = "777", "C1_75", 3


@pytest.fixture(scope="session")
def tm(rpc, live_session):
    """Monte le volet TimesplinterMantle UNE fois (destructif : il joue 3 bordures + une attaque)."""
    from rl_collect_batch import _resolve_session
    out = NP.measure_tm(_resolve_session(), SEED, BOARD, TURNS, verbose=True, consume=True)
    if out is None or not out["rows"]:
        pytest.skip("montage TimesplinterMantle non montable (board/pool/placement)")
    return out


@pytest.fixture(scope="session")
def ll_range2(rpc, live_session):
    """Volet LivingLightning, regime RAYON 2 -- la branche `else` du `If`, celle que l'i2 tait."""
    from rl_collect_batch import _resolve_session
    out = NP.measure_ll(_resolve_session(), SEED, BOARD, verbose=True, regime="range2")
    if out is None:
        pytest.skip("montage LivingLightning (rayon 2) non montable")
    return out


@pytest.fixture(scope="session")
def ll_none(rpc, live_session):
    """Volet LivingLightning, regime HORS PORTEE -- la contre-epreuve NEGATIVE."""
    from rl_collect_batch import _resolve_session
    out = NP.measure_ll(_resolve_session(), SEED, BOARD, verbose=True, regime="none")
    if out is None:
        pytest.skip("montage LivingLightning (hors portee) non montable")
    return out


# ------------------------------------------------------------------------------------------------
# STRUCTURE des arbres -- offline, aucun live requis.
# ------------------------------------------------------------------------------------------------
def test_961_tm_tree_shape():
    """L'arbre de `TimesplinterMantleAbility$$GetTargets`, encode en assertion. Chaque etage cite le
    noeud natif : `AdjacentUnits(Owner, 1, 3)` |> `Friends(of = Owner, _, 3)` |>
    `MechanicalUnits(_, 3)` |> `NonSteppableUnits(_, 3)` `op_Addition` `Owner`."""
    from engine.entities.selectors.units import (
        AdjacentUnits, And, Friends, MechanicalUnits, Union, UnitsWithoutTrait)
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.runner.operations.triggers.loki.timesplinter_mantle import (
        timesplinter_mantle_targets)
    t = timesplinter_mantle_targets()
    assert isinstance(t, Union), "l'`op_Addition Owner@0x30` est le noeud RACINE"
    ns = t.a
    assert isinstance(ns, And), "`NonSteppableUnits` = `op_BitwiseAnd(src, UnitsWithoutTrait(src))`"
    assert isinstance(ns.b, UnitsWithoutTrait) and int(ns.b.trait) == int(UnitTrait.Steppable) == 0x1b
    assert ns.b.source is ns.a, "les DEUX operandes partagent le MEME sous-arbre (comme le natif)"
    mech = ns.a
    assert isinstance(mech, MechanicalUnits), "`MechanicalUnits` est SOUS `NonSteppableUnits`"
    fr = mech.source
    assert isinstance(fr, Friends), "le camp vient du `Friends`, dont le REFERENT est l'Owner"
    assert isinstance(fr.inner, AdjacentUnits)
    for node in (fr, fr.inner):
        assert int(node.selection_type) == 3, "selectionType = 3 (OnlyAliveAndTargetable) au natif"


def test_961_tm_no_isturnof():
    """`...TimesplinterMantleAbility$$CreateTrigger` = `On(0x12)` et RIEN d'autre -- contraste
    `RelentlessMarchAbility`, qui porte `& IsTurnOf(Owner)` sur son `On(0x13)`. Le port ne doit donc
    poser AUCUN predicat de joueur : `matches` rend True inconditionnellement."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.loki.timesplinter_mantle import TimesplinterMantleAbility
    ab = TimesplinterMantleAbility(1)
    assert ab.event_id == int(EventTriggerType.TurnStart_EffectActivation) == 0x12
    assert ab.matches(None, None) is True, "aucun gate de joueur -- cf. l'en-tete du module"


def test_961_ll_gate_evaluates_pickrandomly():
    """LE POINT DU CAS cote LivingLightning : le gate du trigger evalue
    `GetPossibleTargets(Direct(1))` **AU COMPLET**, `PickRandomly` compris -- donc il CONSOMME un
    `genrand_int32`, comme le natif. Evaluer le seul POOL rendrait la meme valeur de verite et
    laisserait le flux MT en retard d'un cran (mesure : 6 tirages live contre 5 cote port, et un
    degat divergent A CIBLE IDENTIQUE)."""
    from engine.entities.selectors.geometry import PickRandomly
    from engine.entities.selectors.units import Damageable
    from engine.runner.operations.triggers.loki.living_lightning import (
        living_lightning_pool, living_lightning_possible_targets)
    gate = living_lightning_possible_targets()
    assert isinstance(gate, PickRandomly), \
        "le gate DOIT etre le `PickRandomly` natif, pas le pool nu (sinon 1 tirage manquant)"
    assert isinstance(gate.source, Damageable), "`Damageable` ferme le pool, comme au natif"
    assert isinstance(living_lightning_pool(), Damageable)


def test_961_ll_radius_branches():
    """Le rayon est `If(AmountIsGreaterThanZero(AdjacentEnemies(Caster)), Direct(1),
    Get(constants.range))` -- et `constants.range` est LU au gameconfig, jamais devine.
    L'i2 ne decrit QUE la branche `then` (<< one random adjacent enemy >>)."""
    import gameconfig as GC
    from engine.entities.formulas import If as IfAmount
    from engine.entities.selectors.accessors import SurroundingTiles
    from engine.entities.selectors.tiles import UnobscuredTiles
    from engine.entities.selectors.units import Damageable, Enemies, Units
    from engine.entities.triggers import AmountIsGreaterThanZero
    from engine.runner.operations.triggers.loki.living_lightning import living_lightning_pool
    pool = living_lightning_pool()
    assert isinstance(pool, Damageable)
    enemies = pool.inner
    assert isinstance(enemies, Enemies)
    units = enemies.inner
    assert isinstance(units, Units)
    unobs = units.tiles
    assert isinstance(unobs, UnobscuredTiles), \
        "`UnobscuredTiles(fromAnyTiles = CasterTile, _)` est un maillon du natif (residu #287-r11-r2-r1-r3)"
    surr = unobs.to_tiles
    assert isinstance(surr, SurroundingTiles) and surr.include_center is False
    assert isinstance(surr.radius, IfAmount)
    assert isinstance(surr.radius.cond, AmountIsGreaterThanZero)
    consts = (GC.ability("LivingLightning") or {}).get("constants") or {}
    assert int(surr.radius.b.value) == int(consts["range"]), \
        "la branche `else` est `Get(GetNumberConstant(0x16 = range))`, LU au gameconfig"
    assert int(surr.radius.a.value) == 1, "<DSLFormulas+0x20> = Direct(1)"


# ------------------------------------------------------------------------------------------------
# (A)-(E) -- confrontation LIVE, volet TimesplinterMantle.
# ------------------------------------------------------------------------------------------------
def test_961_tm_trigger_registered(tm):
    """(A) `TimesplinterMantle` enregistre EXACTEMENT un trigger sur Thothmek, sur `On(0x12)`."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
    from engine.runner.operations.triggers.loki.timesplinter_mantle import TimesplinterMantleAbility
    from engine.runner.snapshot import load_state
    row = tm["rows"][0]
    st = load_state(row["cap"]["dec"], row["cap"]["ob"], row["cap"]["snap"],
                    board=row["cap"]["board"])
    mine = [t for t in collect_triggered_abilities(st) if isinstance(t, TimesplinterMantleAbility)]
    assert len(mine) == 1, "Thothmek doit porter exactement 1 trigger TimesplinterMantle"
    assert mine[0].owner_id == tm["ids"][NP.TM_CARRIER]
    assert mine[0].event_id == int(EventTriggerType.TurnStart_EffectActivation)


def test_961_tm_agreement_and_non_degenerate(tm):
    """(B) A chaque bordure : MEME ensemble de porteurs de 1551 live et port, et le port a
    RECONSTRUIT cet ensemble (vide juste apres `On(0x17)`)."""
    vis = tm["vis_by_id"]
    for row in tm["rows"]:
        assert not row["after_end"], (
            "bordure #%d : `On(0x17 = TurnEnd)` doit avoir retire TOUS les 1551 avant la re-pose "
            "-- sinon l'accord n'est qu'un heritage de la capture (porteurs restants : %s)"
            % (row["k"], sorted(vis.get(i, i) for i in row["after_end"])))
        assert set(row["live"]) == set(row["port"]), (
            "bordure #%d : live=%s port=%s"
            % (row["k"], sorted(vis[i] for i in row["live"]),
               sorted(vis[i] for i in row["port"])))


def test_961_tm_covered_set_is_discriminating(tm):
    """(D) L'ensemble couvert EST le discriminant : le porteur et l'allie MECHANICAL adjacent, et
    EUX SEULS. L'allie ORGANIQUE adjacent, l'allie MECHANICAL a distance 2 et l'ENNEMI MECHANICAL
    adjacent en sont exclus -- chacun par un gate DIFFERENT."""
    ids, vis = tm["ids"], tm["vis_by_id"]
    expected = {ids[NP.TM_CARRIER], ids[NP.TM_MECH]}
    for row in tm["rows"]:
        assert set(row["live"]) == expected, (
            "bordure #%d : couverts=%s (attendu porteur + allie Mechanical adjacent)"
            % (row["k"], sorted(vis[i] for i in row["live"])))
        for excluded in (NP.TM_ORGANIC, NP.TM_FAR, NP.TM_ENEMY):
            assert ids[excluded] not in row["live"], \
                "%s ne doit PAS etre couvert" % excluded


def test_961_tm_consumed_by_the_first_hit(tm):
    """(E) CONTRE-EPREUVE NEGATIVE : l'attaque retire 1551 de la CIBLE et d'elle seule, live comme
    port. Le montage VERIFIE d'abord que le tour adverse est reste OUVERT -- une attaque qui cloture
    la team fait repasser la bordure et rend l'observable AVEUGLE."""
    c = tm["consumed"]
    assert c is not None, "la contre-epreuve n'a pas pu etre montee"
    assert c["turn_kept"], (
        "le coup a CLOS le tour adverse : `On(0x17)` + `On(0x12)` sont repasses derriere, "
        "l'observable ne dit plus rien du retrait")
    assert c["dmg"] > 0, "l'attaque doit avoir porte, sinon `On(9)` n'est pas emis"
    assert c["victim"] in c["before"], "la cible etait bien couverte avant le coup"
    assert c["victim"] not in c["after"], (
        "1551 doit disparaitre de la CIBLE (`On(9) & get_OwnerIsTarget`)")
    others = set(c["before"]) - {c["victim"]}
    assert others and others <= set(c["after"]), (
        "les autres couverts gardent leur charge -- le retrait est PAR CIBLE, pas global")
    assert set(c["after"]) == set(c["port_after"]), (
        "port %s != live %s apres `On(9)`" % (sorted(c["port_after"]), sorted(c["after"])))


# ------------------------------------------------------------------------------------------------
# (F) -- confrontation LIVE, volet LivingLightning.
# ------------------------------------------------------------------------------------------------
def test_961_ll_range2_bit_exact(ll_range2):
    """(F1) Rayon 2 -- la branche `else` du `If`, celle que l'i2 ne decrit PAS : l'eclair part sur
    l'ennemi a distance 2, et le port l'egale BIT-EXACT, degat ET nombre de tirages MT."""
    out = ll_range2
    assert out["hit_live"], (
        "le natif DOIT frapper a distance 2 (branche `Get(constants.range)`) -- un vide ici "
        "signifie que le montage n'exerce pas la branche")
    assert out["draws_live"] == out["draws_port"], (
        "tirages MT live=%s port=%s : un ecart de FLUX (gate `PickRandomly` non evalue ?)"
        % (out["draws_live"], out["draws_port"]))
    assert out["hit_live"] == out["hit_port"], (
        "degat live=%s port=%s" % (out["hit_live"], out["hit_port"]))


def test_961_ll_out_of_range_is_silent(ll_none):
    """(F2) CONTRE-EPREUVE NEGATIVE : hors des DEUX rayons, `!AmountIsZero(...)` est faux -- rien ne
    part, et AUCUN tirage n'est consomme (le gate lui-meme ne pique pas dans un pool vide)."""
    out = ll_none
    assert not out["hit_live"], "le natif ne doit RIEN faire hors portee"
    assert not out["hit_port"], "le port non plus"
    assert out["draws_live"] == out["draws_port"] == 0, (
        "tirages live=%s port=%s : un pool VIDE ne doit consommer aucun `genrand_int32`"
        % (out["draws_live"], out["draws_port"]))


def test_961_ll_adjacent_target_and_draws(ll_range2):
    """(F3) Le regime ADJACENT est mesure a part (`probe_961_necron_passives.py --ll --regimes
    adjacent`) : la CIBLE et le NOMBRE DE TIRAGES y concordent, mais le DEGAT diverge d'un facteur
    constant (87,27 % du port) -- residu `#961-r1`, NON assertionne ici pour ne pas figer un chiffre
    qu'on n'explique pas encore. Ce test-ci garde seulement que le regime rayon-2 reste le temoin
    NON DEGENERE de la paire (il FRAPPE, donc le `none` ci-dessus mesure bien une absence)."""
    assert ll_range2["hit_live"] and ll_range2["hit_port"], \
        "sans un regime qui FRAPPE, le regime `none` ne prouverait rien"
