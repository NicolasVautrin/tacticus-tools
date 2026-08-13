"""#1002 -- GARDE OFFLINE des deux reliques ASTRA MILITARUM (aucun runner).

Elle fige ce que la MESURE LIVE du 2026-08-13 a etabli sur le NATIF
(`probe_1002_reliques_astra_live.py`, trois bras VERTS sur `rnca9r7q6c`) :

  * SABRE_CHARGE      -- Dreir se DEPLACE au contact puis attaque : `Pinned` sur la cible ET
                         `SabreOfSacrifice_ExtraArmor` sur le chargeur, `fixedArmor` 0 -> **1018**
                         (= `extraArmor[10]` x 1 allie normal vaincu) ;
  * SABRE_SANS_CHARGE -- meme attaque, cible DEJA adjacente, aucun deplacement
                         (`chargedUnitIds` VIDE) : AUCUN des deux effets. C'est la contre-epreuve
                         du gate `IsCharging` ;
  * CADIA_MORT        -- le porteur est abattu : un `astraNpc1Guardsman` apparait dans SON hex,
                         dans SON camp, avec **5817 / 3492 / 1166** = `summonHp` / `summonDmg` /
                         `summonArmor` au niveau TERTIAIRE 10.

Ces trois chiffres sont l'ancre : ils ne se re-derivent pas d'un port, ils viennent du jeu.
"""
from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PY = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

DECLENCHEUR = {
    "chemins": (
        # SOCLE d'un fichier de test OFFLINE : la cascade des `conftest.py` et les deux gardes de
        # passe. Aucun harnais live n'est traverse -- ce fichier ne monte AUCUN runner.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # PROPRE A CE FICHIER. Les deux modules de port sont l'objet meme du cliquet ; le probe
        # porte le MONTAGE et les attendus mesures ; le registre porte l'inscription (sans elle,
        # aucune des deux abilities n'est jamais instanciee) ; les noeuds DSL cites sont ceux dont
        # un changement deplacerait le verdict.
        "scripts/python/probe_1002_reliques_astra_live.py",
        "scripts/python/engine/runner/operations/triggers/loki/sabre_of_sacrifice.py",
        "scripts/python/engine/runner/operations/triggers/loki/relic_of_lost_cadia.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/core.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/summon.py",
        "scripts/python/engine/runner/operations/spawn.py",
        "scripts/python/engine/runner/operations/effects.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/entities/behaviours.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/selectors/tiles.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/entities/unit_flag.py",
        "scripts/python/engine/entities/effects/magnitude.py",
    ),
    # Il RELIT le gameconfig vivant (`extraArmor`, `summonHp`/`summonDmg`/`summonArmor`,
    # la constante `unitId`) : un changement de build peut deplacer les paliers.
    "build": True,
    "toujours": False,
    "raison": "Il garde le PORT des deux reliques Astra contre les chiffres MESURES sur le natif : "
              "le gate `IsCharging` et sa contre-epreuve, le produit `Count(allies vaincus) x "
              "extraArmor`, les deux effets poses, l'inscription au registre, et le `Spawn` a la "
              "mort avec l'AbilityState TERTIAIRE.",
}

from engine.dsl.effects import ExecutionContext                                        # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                             # noqa: E402
from engine.entities.effect_type import EffectType                                     # noqa: E402
from engine.entities.effects_state import EffectsState                                 # noqa: E402
from engine.entities.stats import StatType                                             # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                                # noqa: E402
from engine.entities.unit_context import UnitContext                                   # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType                # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,                 # noqa: E402
                                      PositionComponent, StatsComponent, UnitComponent)
from engine.runner.operations.triggers.base import TriggerEvent                        # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import (                      # noqa: E402
    RELIC_ABILITY_TRIGGERS)
from engine.runner.operations.triggers.loki.relic_of_lost_cadia import (               # noqa: E402
    RelicOfLostCadiaAbility, RelicOfLostCadiaSummonUnitAbility, is_imperial_and_summon)
from engine.runner.operations.triggers.loki.sabre_of_sacrifice import (                # noqa: E402
    SabreOfSacrificeAbility, relic_extra_armor_per_unit,
    sabre_of_sacrifice_defeated_friends_selector)
from engine.runner.state import State                                                  # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                                 # noqa: E402

PORTEUR, CIBLE, ALLIE, ETRANGER = 10, 11, 12, 13

#: MESURES LIVE du 2026-08-13 (`probe_1002_reliques_astra_live.py`, build `rnca9r7q6c`).
#: Ce ne sont pas des valeurs re-derivees du port : elles viennent du jeu.
ARMURE_MESUREE_NIVEAU_10 = 1018                 # `fixedArmor` 0 -> 1018 sur UN allie vaincu
GUARDSMAN_MESURE = {"health": 5817, "attack": 3492, "fixedArmor": 1166}


def _ctx(uid, *, traits=(), tertiary=None, visual="u", level=10, mult=100):
    """Le VRAI `UnitContext`, pas un stub : les feuilles DSL lisent `get_stat` / `stat` et un
    doublet trop pauvre fait tomber le test sur son propre echafaudage plutot que sur le port."""
    c = UnitContext(entity_id=int(uid), visual_id=visual, traits=list(traits),
                    active_ability_level=50, passive_ability_level=50,
                    ability_variables_multiplier=mult)
    c.traits_measured = True                    # traits FOURNIS, pas re-derives de la grande alliance
    c.tertiary_ability = tertiary               # `UnitConfiguration.TertiaryAbility` (hierarchie 3)
    c.tertiary_ability_level = level
    c.tertiary_ability_multiplier = mult
    return c


def _unite(st: State, uid, *, team=1, alive=True, pos=(0, 0), traits=(), tertiary=None,
           visual="u", parent=None):
    e = st.add_entity(uid)
    e.add_component(UnitComponent(visual, alive, parent_id=parent))
    e.add_component(OwnerComponent(team, team))
    e.add_component(HealthComponent(1000 if alive else 0, 1000))
    e.add_component(StatsComponent(ctx=_ctx(uid, traits=traits, tertiary=tertiary, visual=visual)))
    e.add_component(PositionComponent(int(pos[0]), int(pos[1])))
    return uid


@pytest.fixture
def montage():
    """FIXTURE NOMMEE. Le PORTEUR tient `SabreOfSacrifice` en tertiaire ; `CIBLE` est l'ennemi
    attaque ; `ALLIE` est un ami NORMAL dont on choisit s'il est vaincu ; `ETRANGER` est un ennemi
    mort (il ne doit PAS compter). Chaque face negative se fabrique en changeant UNE piece."""
    def _monter(*, allie_vaincu=True, charge=True, allie_steppable=False):
        st = State()
        st.effects = EffectsState()
        st.rng = IntBasedMersenneTwister(777)
        _unite(st, PORTEUR, team=1, pos=(0, 0), visual="astraDreir",
               tertiary="SabreOfSacrifice")
        _unite(st, CIBLE, team=2, pos=(1, 0), visual="ultraTitus")
        _unite(st, ALLIE, team=1, alive=not allie_vaincu, pos=(5, 5), visual="astraOrdnance",
               traits=([UnitTrait.Steppable.name] if allie_steppable else []))
        _unite(st, ETRANGER, team=2, alive=False, pos=(6, 6), visual="ultraApothecary")
        if charge:
            # `MoveUnitOperation$$UpdateCharging` : la cible est NOUVELLEMENT adjacente.
            st.get_entity(PORTEUR).get_component(UnitComponent).charged_unit_ids = {CIBLE}
        return st
    return _monter


def _ev_attaque(actor=PORTEUR, target=CIBLE):
    """`On(9 = Attack)` -- l'evenement que `dispatch/attack.py` construit : `actor` = le CASTER du
    coup (`Caster@+0x48`), `target` = la victime (`Target@+0x60`)."""
    return TriggerEvent(int(EventTriggerType.Attack), actor, target,
                        ranged=False, profile=None, is_normal_attack=True)


def _ev_mort(killer, dying):
    """`On(0 = UnitDeath)` -- `unit_death_triggers` pose `actor = killer`, `target = dying`."""
    return TriggerEvent(int(EventTriggerType.UnitDeath), killer, dying,
                        ranged=False, profile=None, killer_id=killer, dying_id=dying)


def _effets(st: State, uid: int):
    return sorted(int(e.effect_type) for e in (st.effects.by_unit.get(int(uid)) or [])
                  if not e.consumed)


# ------------------------------------------------------------------ 1. le CABLAGE (le registre)
def test_les_deux_reliques_sont_inscrites_au_registre_relique():
    """Sans inscription, `collect_triggered_abilities` n'instancie RIEN et les deux ports sont
    INERTES -- sans erreur. C'est le mode de panne que `RELIC_ABILITY_TRIGGERS` doit fermer."""
    assert RELIC_ABILITY_TRIGGERS.get("SabreOfSacrifice") == [SabreOfSacrificeAbility]
    assert RELIC_ABILITY_TRIGGERS.get("RelicOfLostCadia") == [RelicOfLostCadiaAbility,
                                                              RelicOfLostCadiaSummonUnitAbility]


def test_les_ids_declares_sont_ceux_du_build():
    assert SabreOfSacrificeAbility.TRIGGERED_ABILITY_ID == int(TriggeredAbilityType.SabreOfSacrifice)
    assert RelicOfLostCadiaAbility.TRIGGERED_ABILITY_ID == int(TriggeredAbilityType.RelicOfLostCadia)
    assert (RelicOfLostCadiaSummonUnitAbility.TRIGGERED_ABILITY_ID
            == int(TriggeredAbilityType.RelicOfLostCadia))


def test_les_vecteurs_d_evenement_sont_ceux_des_CreateTrigger():
    """`SabreOfSacrifice` : UN `On(9)`. `RelicOfLostCadia` : QUATRE `On()` ventiles en `event_ids`,
    et son volet SummonUnit ecoute `On(0 = UnitDeath)` en `fire_on_death` (`alive: 0`)."""
    assert SabreOfSacrificeAbility.event_id == int(EventTriggerType.Attack)
    assert set(RelicOfLostCadiaAbility.event_ids) == {
        int(EventTriggerType.UnitAfterMove), int(EventTriggerType.UnitAdded),
        int(EventTriggerType.UnitBecameTargetable), int(EventTriggerType.UnitRevived)}
    assert RelicOfLostCadiaSummonUnitAbility.event_id == int(EventTriggerType.UnitDeath)
    assert RelicOfLostCadiaSummonUnitAbility.fire_on_death is True, (
        "`ownerNeedsToBeAlive: 0` : l'owner est deja mort au dispatch, le gate vivant de "
        "`CanGetAbilityTrigger` doit etre court-circuite")
    assert SabreOfSacrificeAbility.fire_on_death is False, (
        "`On(9, ownerNeedsToBeAlive: 1)` -- le porteur doit etre VIVANT")


# ------------------------------------------------- 2. le GATE `IsCharging` et sa contre-epreuve
def test_le_gate_IsCharging_ouvre_quand_le_porteur_a_charge(montage):
    st = montage(charge=True)
    assert SabreOfSacrificeAbility(PORTEUR).matches(st, _ev_attaque()) is True


def test_le_gate_IsCharging_FERME_sans_charge(montage):
    """CONTRE-EPREUVE, et c'est le bras qui a le plus de valeur : le porteur est ADJACENT a sa
    cible, il attaque, mais `ChargedUnitIds` est VIDE -- exactement ce que le natif rend
    (`SABRE_SANS_CHARGE` : aucun effet, `fixedArmor` inchange). Un port qui aurait oublie
    `IsCharging` serait vert sur le bras nominal et FAUX ici."""
    st = montage(charge=False)
    assert SabreOfSacrificeAbility(PORTEUR).matches(st, _ev_attaque()) is False


# --------------------------------------------- 3. le PRODUIT `Count(vaincus) x extraArmor`
def test_le_compte_des_allies_vaincus_ne_retient_que_les_AMIS_NORMAUX_MORTS(montage):
    """`AreFriends(Owner, It) & HasBeenDefeated(It) & IsNormalUnit(It)` sur `AllUnits()` (pool 8,
    MORTS INCLUS). L'ennemi mort ne compte pas (AreFriends), l'ami vivant non plus
    (HasBeenDefeated), et un ami `Steppable` non plus (IsNormalUnit)."""
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.entities.formulas import Count

    def _n(st):
        return int(Count(sabre_of_sacrifice_defeated_friends_selector()).evaluate(
            entities_from_state(st, PORTEUR, CIBLE, owner_id=PORTEUR)))

    assert _n(montage(allie_vaincu=True)) == 1
    assert _n(montage(allie_vaincu=False)) == 0, "un ami VIVANT ne doit pas compter"
    assert _n(montage(allie_vaincu=True, allie_steppable=True)) == 0, (
        "un ami `Steppable` echoue `IsNormalUnit` -- il ne compte pas")


def test_la_magnitude_par_unite_est_celle_du_niveau_TERTIAIRE(montage):
    """`GetVariableForLevel(0x1b = extraArmor, abilityState)` sous l'`AbilityState` TERTIAIRE.
    Le niveau 10 est celui de la mesure live : la valeur DOIT etre celle qu'on a lue sur le jeu."""
    st = montage()
    assert relic_extra_armor_per_unit(st, PORTEUR) == ARMURE_MESUREE_NIVEAU_10


def test_la_charge_pose_Pinned_sur_la_cible_et_l_armure_MESUREE_sur_le_chargeur(montage):
    """L'ancre de toute la tranche : le port doit reproduire les DEUX effets et le chiffre 1018
    (`fixedArmor` 0 -> 1018) que le natif a rendus."""
    st = montage(charge=True, allie_vaincu=True)
    a = SabreOfSacrificeAbility(PORTEUR)
    assert a.matches(st, _ev_attaque()) is True
    out = a.execute_behaviour(st, _ev_attaque())
    assert out is not None
    assert int(EffectType.Pinned) in _effets(st, CIBLE), "`Pinned` absent de la CIBLE"
    assert int(EffectType.SabreOfSacrifice_ExtraArmor) in _effets(st, PORTEUR), (
        "`SabreOfSacrifice_ExtraArmor` absent du CHARGEUR")
    assert out["extra_armor"] == ARMURE_MESUREE_NIVEAU_10, (
        "montant %r != la mesure live %d" % (out["extra_armor"], ARMURE_MESUREE_NIVEAU_10))


def test_sans_allie_vaincu_l_armure_vaut_ZERO_et_le_regime_est_DEGENERE(montage):
    """Ce n'est PAS un bug : `Multiply(0, extraArmor)` = 0, l'effet est pose mais ne contribue a
    rien. Le figer ici est ce qui empeche qu'un bras joue dans ce regime passe pour une mesure --
    c'est exactement l'erreur que le probe a commise a son premier jet."""
    st = montage(charge=True, allie_vaincu=False)
    out = SabreOfSacrificeAbility(PORTEUR).execute_behaviour(st, _ev_attaque())
    assert out is not None and out["extra_armor"] == 0


# --------------------------------------------------------- 4. `RelicOfLostCadia`, volet SUMMON
def test_le_summon_ne_part_QUE_sur_la_mort_du_PORTEUR(montage):
    """`get_OwnerIsTarget` sur `On(UnitDeath)` : l'evenement porte `actor = killer`,
    `target = dying`. Une autre unite qui meurt ne doit RIEN declencher."""
    st = montage()
    a = RelicOfLostCadiaSummonUnitAbility(PORTEUR)
    assert a.matches(st, _ev_mort(CIBLE, PORTEUR)) is True
    assert a.matches(st, _ev_mort(PORTEUR, CIBLE)) is False


# ------------------------------------------------- 5. `RelicOfLostCadia`, volet FINAL VENGEANCE
def test_le_selecteur_de_zone_exige_les_DEUX_traits(montage):
    """`IsImperialAndSummon` = `UnitsWithTraits(targets, [Imperial, Summon], 3)`, et
    `DSLSelectors$$UnitsWithTraits` est une INTERSECTION (decompile : `result op_BitwiseAnd
    UnitsWithTrait(...)` par trait). Un `Imperial` qui n'est pas `Summon` ne doit PAS entrer."""
    from engine.runner.abilities.behaviours.context import entities_from_state
    # ⚠ `AllAliveUnits` (pool 0), PAS `AllUnits` (pool 8) : le natif ne passe JAMAIS un pool a
    # `IsImperialAndSummon` -- il lui donne `SurroundingFriends(...)` ou `Caster@+0x48`. La source
    # n'est ici qu'une COMMODITE de garde, et prendre le pool-8 ferait ecrire a ce test un site
    # `AllUnits(` non attribuable a un call-site natif (le cliquet `probe_514` etape 3 le refuse,
    # a juste titre).
    from engine.entities.selectors.tiles import AllAliveUnits
    # ⚠ ALLIE VIVANT : le `selectionType: 3` du site est `OnlyAliveAndTargetable` -- une unite morte
    # est ecartee AVANT meme le test de traits, et le bras ne mesurerait plus l'intersection.
    st = montage(allie_vaincu=False)
    st.get_entity(ALLIE).get_component(StatsComponent).ctx.traits = [UnitTrait.Imperial.name]
    ctx = entities_from_state(st, PORTEUR, CIBLE, owner_id=PORTEUR)
    assert [u["id"] for u in is_imperial_and_summon(AllAliveUnits()).evaluate(ctx)] == []
    st.get_entity(ALLIE).get_component(StatsComponent).ctx.traits = [
        UnitTrait.Imperial.name, UnitTrait.Summon.name]
    ctx = entities_from_state(st, PORTEUR, CIBLE, owner_id=PORTEUR)
    assert [u["id"] for u in is_imperial_and_summon(AllAliveUnits()).evaluate(ctx)] == [ALLIE]


# ------------------------------------------------------------- 6. le slot OWNER, threade a part
def test_le_slot_OWNER_est_DISTINCT_du_caster(montage):
    """La branche Death Rider du `CreateTrigger` a `Owner != Caster`. `entities_from_state` doit
    donc pouvoir les separer -- sinon `Owner()` retombe sur le caster (`ctx.owner or ctx.caster`)
    et `AreFriends(Owner, ...)` change de referent, SILENCIEUSEMENT."""
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.entities.selectors.accessors import Owner
    from engine.entities.selectors.tiles import Caster
    st = montage()
    ctx = entities_from_state(st, CIBLE, CIBLE, owner_id=PORTEUR)
    assert Owner().evaluate(ctx)["id"] == PORTEUR
    assert Caster().evaluate(ctx)["id"] == CIBLE
    ctx_sans = entities_from_state(st, CIBLE, CIBLE)
    assert Owner().evaluate(ctx_sans)["id"] == CIBLE, (
        "sans `owner_id`, le repli documente doit rester le CASTER -- comportement d'avant")
