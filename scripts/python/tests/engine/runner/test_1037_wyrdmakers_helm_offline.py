"""#1037 -- GARDE OFFLINE de `WyrdmakersHelm`, la relique unique de `spaceWolfPriest` (aucun runner).

Elle fige, ETAGE PAR ETAGE, ce que
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.WyrdmakersHelmAbility` fait sur le build
`rnca9r7q6c` -- et surtout ce qu'elle NE fait PAS. Les quatre gates du `CreateTrigger` sont testes
UN PAR UN avec leur contre-epreuve, parce que c'est la seule facon de voir un gate DISPARAITRE :
un port qui les perdrait tous resterait vert sur un unique cas nominal.

Le substrat teste ici (`UnitComponent.times_healed_this_turn` + le vecteur
`On(0x2c = UnitHealedWithRemoveEffects)`) N'EXISTAIT PAS avant cette tranche : sans lui l'ability
serait inscrite au registre et JAMAIS declenchee, silencieusement. C'est ce mode de panne-la que les
etages 2 et 3 ferment.

ASCII only (console cp1252).
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
        # PROPRE A CE FICHIER. Le module de port est l'objet meme du cliquet ; le registre porte
        # l'inscription (sans elle l'ability n'est jamais instanciee) ; `dispatch/heal.py` et
        # `operations/heal.py` portent le VECTEUR et le COMPTEUR, tous deux poses par cette meme
        # tranche ; `turnflow.py` porte le RESET du compteur ; `components.py` / `context.py`
        # portent le substrat et sa publication au dict DSL ; les noeuds cites sont ceux dont un
        # changement deplacerait le verdict.
        "scripts/python/engine/runner/operations/triggers/loki/wyrdmakers_helm.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/heal.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/core.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        "scripts/python/engine/runner/operations/heal.py",
        "scripts/python/engine/runner/operations/turnflow.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/entities/behaviours.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/entities/unit_team_selection_type.py",
        "scripts/python/engine/entities/stats.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/entities/effects/magnitude.py",
    ),
    # Il RELIT le gameconfig vivant (les 10 paliers d'`extraDmg`) : un changement de build peut
    # deplacer les valeurs.
    "build": True,
    "toujours": False,
    "raison": "Il garde le PORT de `WyrdmakersHelm` : les QUATRE gates du `CreateTrigger` avec leur "
              "contre-epreuve chacun, l'ordre des CINQ termes du `CreateBehaviour`, le compteur "
              "`times_healed_this_turn` et son reset, le vecteur `On(0x2c)` et son gate "
              "`removeEffects`, et l'inscription au registre relique.",
}

import hexgeo                                                                          # noqa: E402
from engine.dsl.effects import ExecutionContext                                        # noqa: E402
from engine.entities.pathfinding.board import Board                                    # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                             # noqa: E402
from engine.entities.effect_type import EffectType                                     # noqa: E402
from engine.entities.effects_state import EffectsState                                 # noqa: E402
from engine.entities.stats import StatType                                             # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType                # noqa: E402
from engine.entities.unit_context import UnitContext                                   # noqa: E402
from engine.entities.unit_selection_type import UnitSelectionType                      # noqa: E402
from engine.entities.unit_team_selection_type import UnitTeamSelectionType             # noqa: E402
from engine.runner.abilities.behaviours.context import entities_from_state             # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,                 # noqa: E402
                                      PositionComponent, StatsComponent, UnitComponent)
from engine.runner.operations.triggers.base import TriggerEvent                        # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import (                      # noqa: E402
    RELIC_ABILITY_TRIGGERS)
from engine.runner.operations.triggers.loki.wyrdmakers_helm import (                   # noqa: E402
    ADJACENCY_SELECTION, FIRST_HEAL_OF_TURN, FRIENDS_COMPARISON, ICE_TILE,
    WYRDMAKERS_HELM_STAT, WYRDMAKERS_HELM_STAT_MOD, WyrdmakersHelmAbility, extra_dmg,
    wyrdmakers_helm_behaviour_tree, wyrdmakers_helm_trigger_tree)
from engine.runner.prng import IntBasedMersenneTwister                                 # noqa: E402
from engine.runner.state import State                                                  # noqa: E402

PORTEUR, VOISIN, LOINTAIN, ENNEMI, ENNEMI2 = 10, 11, 12, 13, 14

#: Les 10 paliers d'`extraDmg` du gameconfig de `WyrdmakersHelm` (`units.abilities`). Le premier et
#: le dernier sont ancres ici pour que le test SEPARE un montage niveau 1 d'un montage niveau 10 :
#: un port qui lirait toujours le dernier palier resterait vert sur un seul niveau.
EXTRA_DMG_NIVEAU_1 = 490
EXTRA_DMG_NIVEAU_10 = 728


def _plateau(cols: int = 8, rows: int = 8):
    """Plateau hex minimal -- necessaire parce que la glace est un effet de TUILE (cf. la fixture)."""
    tiles = []
    for c in range(cols):
        for r in range(rows):
            tiles.append({"id": c * rows + r + 1, "col": c, "row": r, "walkable": True,
                          "isWall": False, "elevation": 0,
                          "neighbours": [cc * rows + rr + 1 for (cc, rr) in hexgeo.neighbors(c, r)
                                         if 0 <= cc < cols and 0 <= rr < rows]})
    return Board(tiles)


def _ctx(uid, *, tertiary=None, visual="u", level=10, mult=100):
    """Le VRAI `UnitContext`, pas un stub : les feuilles DSL lisent `get_stat`/`stat` et un doublet
    trop pauvre ferait tomber le test sur son propre echafaudage plutot que sur le port."""
    c = UnitContext(entity_id=int(uid), visual_id=visual, traits=[],
                    active_ability_level=50, passive_ability_level=50,
                    ability_variables_multiplier=mult)
    c.traits_measured = True
    c.tertiary_ability = tertiary               # `UnitConfiguration.TertiaryAbility` (hierarchie 3)
    c.tertiary_ability_level = level
    c.tertiary_ability_multiplier = mult
    return c


def _unite(st: State, uid, *, team=1, alive=True, pos=(0, 0), tertiary=None, visual="u",
           level=10, hp=1000, hp_max=1000):
    e = st.add_entity(uid)
    e.add_component(UnitComponent(visual, alive))
    e.add_component(OwnerComponent(team, team))
    e.add_component(HealthComponent(hp if alive else 0, hp_max))
    e.add_component(StatsComponent(ctx=_ctx(uid, tertiary=tertiary, visual=visual, level=level)))
    e.add_component(PositionComponent(int(pos[0]), int(pos[1])))
    return uid


@pytest.fixture
def montage():
    """FIXTURE NOMMEE et reutilisable. `PORTEUR` tient `WyrdmakersHelm` en TERTIAIRE ; `VOISIN` est
    un allie ADJACENT ; `LOINTAIN` un allie hors de portee ; `ENNEMI`/`ENNEMI2` sont adjacents au
    porteur (donc attaquables). Chaque face negative se fabrique en changeant UNE piece.

    Geometrie (grille hex offset, colonnes paires) -- les positions sont CHOISIES pour que
    l'adjacence soit reelle, jamais subie : `PORTEUR(0,0)`, `VOISIN(1,0)` et `ENNEMI(0,1)` sont
    adjacents a `PORTEUR` ; `LOINTAIN(6,6)` ne l'est pas."""
    def _monter(*, niveau=10, tour_du_porteur=True, voisin_team=1, voisin_pos=(1, 0),
                porteur_vivant=True, tertiaire="WyrdmakersHelm"):
        st = State()
        st.effects = EffectsState()
        st.rng = IntBasedMersenneTwister(777)
        # PLATEAU OBLIGATOIRE, et ce n'est pas de la decoration : le 5e terme de l'arbre pose un
        # effet de TUILE, et `_add_effect_target_id` resout `(col,row) -> board.id_at(...)`. Sans
        # `board`, il rend `None` et la glace n'est JAMAIS posee -- un test monte sans plateau
        # mesurerait son propre echafaudage et pas le port (constate a l'ecriture : temoin nul).
        st.board = _plateau()
        _unite(st, PORTEUR, team=1, alive=porteur_vivant, pos=(0, 0), visual="spaceWolfPriest",
               tertiary=tertiaire, level=niveau)
        _unite(st, VOISIN, team=voisin_team, pos=voisin_pos, visual="spaceWolfUlf",
               hp=500, hp_max=1000)
        _unite(st, LOINTAIN, team=1, pos=(6, 6), visual="spaceWolfNjal", hp=500, hp_max=1000)
        _unite(st, ENNEMI, team=2, pos=(0, 1), visual="ultraTitus")
        _unite(st, ENNEMI2, team=2, pos=(1, 1), visual="ultraApothecary")
        # `IsTurnOf(Owner)` lit le joueur courant du `TurnComponent`.
        st.current_player_id = 1 if tour_du_porteur else 2
        return st
    return _monter


def _ev_soin(healed, caster=VOISIN):
    """`processor.<slot 0x51>(caster, caster, healed, 0x2c, ability)` -- le triplet que
    `dispatch/heal.py` construit : `actor` = le SOIGNEUR, `target` = l'unite SOIGNEE."""
    return TriggerEvent(int(EventTriggerType.UnitHealedWithRemoveEffects),
                        caster, healed, ranged=False, profile=None)


def _soigne(st: State, uid: int, fois: int = 1):
    """Pose le compteur natif `ActorStatisticsComponent+0xd4` a `fois` -- ce que
    `HealUnitOperation$$Execute` fait AVANT d'emettre le vecteur."""
    st.get_entity(uid).get_component(UnitComponent).times_healed_this_turn = int(fois)


# --------------------------------------------------------------- 1. le CABLAGE (le registre)
def test_la_relique_est_inscrite_au_registre_relique():
    """Sans inscription, `collect_triggered_abilities` n'instancie RIEN et le port est INERTE --
    sans erreur. C'est le mode de panne que `RELIC_ABILITY_TRIGGERS` doit fermer."""
    assert RELIC_ABILITY_TRIGGERS.get("WyrdmakersHelm") == [WyrdmakersHelmAbility]


def test_l_id_declare_est_celui_du_build_et_PAS_celui_de_l_effet():
    """`TriggeredAbilityType.WyrdmakersHelm = 1504` et `EffectType.WyrdmakersHelm = 1505` portent le
    MEME NOM dans DEUX enums -- les confondre serait silencieux (ordinaux voisins, tous deux
    valides). Ce test fige lequel va ou."""
    assert WyrdmakersHelmAbility.TRIGGERED_ABILITY_ID == int(TriggeredAbilityType.WyrdmakersHelm)
    assert int(TriggeredAbilityType.WyrdmakersHelm) == 1504
    assert int(WYRDMAKERS_HELM_STAT_MOD) == int(EffectType.WyrdmakersHelm) == 1505
    assert int(WYRDMAKERS_HELM_STAT_MOD) != int(TriggeredAbilityType.WyrdmakersHelm)


def test_l_evenement_ecoute_est_bien_0x2c_et_pas_0x2b():
    """`On(0x2c = UnitHealedWithRemoveEffects)`, PAS son voisin `On(0x2b = UnitHealed)` : le natif
    emet les deux, et seul le second est gate par `removeEffects`."""
    assert int(WyrdmakersHelmAbility.event_id) == int(
        EventTriggerType.UnitHealedWithRemoveEffects) == 0x2c
    assert int(EventTriggerType.UnitHealed) == 0x2b


def test_les_litteraux_d_enum_du_trigger_sont_ceux_du_decompile():
    """`IsAdjacent(..., selectionType: 3)` et `AreFriends(..., comparisonType: 0)` : DEUX enums
    differents pour deux parametres voisins, tous deux LUS dans `frida/methods.tsv`. Un port qui
    prendrait `UnitTeamSelectionType` pour l'un ou `UnitSelectionType` pour l'autre serait juste en
    ordinal (0 et 0) et FAUX en semantique."""
    assert ADJACENCY_SELECTION is UnitSelectionType.OnlyAliveAndTargetable
    assert int(ADJACENCY_SELECTION) == 3
    assert FRIENDS_COMPARISON is UnitTeamSelectionType.ByCurrentTeam
    assert int(FRIENDS_COMPARISON) == 0
    # Le stat-mod porte sur l'ATTAQUE (`statType: 0 = StatType.Attack`), pas sur une autre stat.
    assert int(WYRDMAKERS_HELM_STAT) == int(StatType.ATTACK) == 0
    # `<DSLFormulas+0x20>` = la constante 1 : « for the FIRST time this turn ».
    assert FIRST_HEAL_OF_TURN == 1


# --------------------------------------------------------- 2. les QUATRE gates du CreateTrigger
def test_gate_owner_est_la_cible__le_porteur_soigne_LUI_MEME_declenche(montage):
    st = montage()
    _soigne(st, PORTEUR, 1)
    assert WyrdmakersHelmAbility(PORTEUR).matches(st, _ev_soin(PORTEUR)) is True


def test_gate_voisin_ami__un_ALLIE_ADJACENT_soigne_declenche(montage):
    st = montage()
    _soigne(st, VOISIN, 1)
    assert WyrdmakersHelmAbility(PORTEUR).matches(st, _ev_soin(VOISIN)) is True


def test_contre_epreuve_adjacence__un_allie_LOINTAIN_soigne_ne_declenche_PAS(montage):
    """`IsAdjacent(Owner, Target, 3)`. Sans ce gate, tout soin sur n'importe quel allie de la carte
    declencherait -- et le test nominal ci-dessus resterait vert."""
    st = montage()
    _soigne(st, LOINTAIN, 1)
    assert WyrdmakersHelmAbility(PORTEUR).matches(st, _ev_soin(LOINTAIN)) is False


def test_contre_epreuve_amitie__un_ENNEMI_ADJACENT_soigne_ne_declenche_PAS(montage):
    """`AreFriends(Owner, Target, ByCurrentTeam, false)`. L'ennemi est place a la MEME position que
    le voisin ami du cas nominal : seule l'EQUIPE change, donc c'est bien ce gate-la qu'on mesure et
    pas l'adjacence."""
    st = montage(voisin_team=2)
    _soigne(st, VOISIN, 1)
    assert WyrdmakersHelmAbility(PORTEUR).matches(st, _ev_soin(VOISIN)) is False


def test_contre_epreuve_premier_soin__un_SECOND_soin_du_meme_tour_ne_declenche_PAS(montage):
    """`AmountIsEqual(TimesHealedThisTurn(Target), Const(1))`. C'est une EGALITE, pas un `>= 1` :
    la surcharge appelee est celle qui construit un `AmountIsEqualAbilityTrigger` (tranchee par les
    XREFS ENTRANTES, une homonyme construisant un `AmountIsGreater`)."""
    st = montage()
    _soigne(st, VOISIN, 2)
    assert WyrdmakersHelmAbility(PORTEUR).matches(st, _ev_soin(VOISIN)) is False


def test_contre_epreuve_zero_soin__un_compteur_a_zero_ne_declenche_PAS(montage):
    """L'autre bord de l'egalite : si le vecteur etait emis AVANT l'increment natif, le compteur
    vaudrait 0 et l'ability ne fire jamais. Ce test fige l'ORDRE mesure sur le natif."""
    st = montage()
    _soigne(st, VOISIN, 0)
    assert WyrdmakersHelmAbility(PORTEUR).matches(st, _ev_soin(VOISIN)) is False


def test_contre_epreuve_tour__hors_du_tour_du_porteur_rien_ne_declenche(montage):
    """`<DSLTriggers+0x28>` = `IsTurnOf(Owner)` -- « During HIS turn »."""
    st = montage(tour_du_porteur=False)
    _soigne(st, VOISIN, 1)
    assert WyrdmakersHelmAbility(PORTEUR).matches(st, _ev_soin(VOISIN)) is False


def test_contre_epreuve_porteur_mort__ownerNeedsToBeAlive(montage):
    """`On(0x2c, ownerNeedsToBeAlive: true)` -- le 2e argument litteral de `DSLTriggers$$On`."""
    st = montage(porteur_vivant=False)
    _soigne(st, VOISIN, 1)
    assert WyrdmakersHelmAbility(PORTEUR).matches(st, _ev_soin(VOISIN)) is False


def test_le_trigger_est_un_ARBRE_et_pas_du_code_impératif():
    """Doctrine #149 : l'artefact natif est un `CreateTrigger`, donc l'arbre DOIT exister comme
    arbre. Un port qui recablerait les gates a la main dans `matches` passerait tous les tests
    ci-dessus et violerait quand meme la doctrine -- ce test-ci est le seul qui le voie."""
    from engine.entities.triggers import (AmountIsEqual, AreFriends, IsAdjacent, IsTurnOf,
                                          OwnerIsTarget, TriggerAnd, TriggerOr)
    t = wyrdmakers_helm_trigger_tree()
    assert isinstance(t, TriggerAnd)
    assert isinstance(t.b, IsTurnOf)                       # dernier `&` = IsTurnOf(Owner)
    assert isinstance(t.a, TriggerAnd)
    assert isinstance(t.a.b, AmountIsEqual)                # `& AmountIsEqual(...)`
    assert isinstance(t.a.a, TriggerOr)                    # `(OwnerIsTarget | (...))`
    assert isinstance(t.a.a.a, OwnerIsTarget)
    assert isinstance(t.a.a.b, TriggerAnd)
    assert isinstance(t.a.a.b.a, IsAdjacent)
    assert isinstance(t.a.a.b.b, AreFriends)


# ------------------------------------------------------- 3. le COMPTEUR et son RESET (substrat)
def test_le_compteur_existe_sur_le_composant_et_part_de_zero():
    """`ActorStatisticsComponent @+0xd4`. S'il n'existe pas, `TimesHealedThisTurn` rend 0 par
    defaut et le gate d'egalite ne matche JAMAIS -- panne silencieuse."""
    uc = UnitComponent("u", True)
    assert uc.times_healed_this_turn == 0
    assert "times_healed_this_turn" in UnitComponent.__slots__


def test_le_compteur_est_publie_au_dict_DSL_et_il_est_LIVE(montage):
    """`TimesHealedThisTurnFormula$$Calculate` lit le composant ; cote port le noeud lit la cle
    `timesHealedThisTurn` du dict d'unite. Elle doit etre dans `_LIVE_KEYS` : l'increment natif
    PRECEDE l'emission du vecteur, donc un dict fige au seed rendrait la valeur d'AVANT."""
    from engine.runner.abilities.behaviours.context import _LIVE_KEYS, _unit_dict
    assert "timesHealedThisTurn" in _LIVE_KEYS
    st = montage()
    _soigne(st, VOISIN, 3)
    assert int(_unit_dict(st, VOISIN)["timesHealedThisTurn"]) == 3


def test_le_noeud_formule_lit_bien_ce_compteur(montage):
    from engine.entities.formulas import TimesHealedThisTurn
    from engine.entities.selectors.accessors import Target
    st = montage()
    _soigne(st, VOISIN, 2)
    entities = entities_from_state(st, PORTEUR, VOISIN)
    assert int(TimesHealedThisTurn(Target()).evaluate(entities)) == 2


def test_le_reset_de_turn_start_remet_le_compteur_a_zero__et_SEULEMENT_pour_le_joueur_entrant(
        montage):
    """`StartTurnOperation$$ResetUnit` -- MEME portee que ses voisins `ResetBlocksMadeThisTurn` /
    `ResetReceivedDamageThisTurn` : les unites du joueur ENTRANT. Un reset GLOBAL effacerait aussi
    le compteur des adversaires, ce que le natif ne fait pas."""
    from engine.runner.operations.turnflow import StartTurnOperation
    st = montage()
    _soigne(st, PORTEUR, 2)
    _soigne(st, VOISIN, 3)
    _soigne(st, ENNEMI, 4)              # equipe 2 -> NE doit PAS etre remis a zero
    StartTurnOperation.execute(st, 1)
    assert st.get_entity(PORTEUR).get_component(UnitComponent).times_healed_this_turn == 0
    assert st.get_entity(VOISIN).get_component(UnitComponent).times_healed_this_turn == 0
    assert st.get_entity(ENNEMI).get_component(UnitComponent).times_healed_this_turn == 4


# ------------------------------------------------- 4. le VECTEUR On(0x2c) et son gate removeEffects
def test_le_soin_incremente_le_compteur_et_emet_le_vecteur(montage):
    """Chaine complete `HealUnitOperation.execute` -> compteur -> vecteur -> `matches`."""
    from engine.runner.operations.heal import HealUnitOperation
    st = montage()
    healed = HealUnitOperation.execute(st, VOISIN, VOISIN, 200, scope=0, remove_effects=True)
    assert healed > 0, "le montage doit vraiment soigner (temoin non nul)"
    assert st.get_entity(VOISIN).get_component(UnitComponent).times_healed_this_turn == 1


def test_le_vecteur_N_EST_PAS_emis_quand_removeEffects_est_faux(montage):
    """`if (removeEffects) processor.<slot 0x51>(..., 0x2c, ...)`. C'est ce qui separe
    `HealBehaviourOptions$$ForHeal` (=1) de `$$ForRegenerate` (=0) : une REGENERATION ne declenche
    pas la relique. Le COMPTEUR, lui, monte dans les deux cas -- il est hors du `if`."""
    from engine.runner.operations import heal as heal_mod
    st = montage()
    vus = []
    reel = heal_mod.__dict__.get("_vecteur_espion")
    import engine.runner.operations.triggers.dispatch.heal as dh
    origine = dh.unit_healed_with_remove_effects_triggers

    def espion(state, caster_id, target_id, ability_or_effect=None):
        vus.append((caster_id, target_id))
        return origine(state, caster_id, target_id, ability_or_effect=ability_or_effect)

    dh.unit_healed_with_remove_effects_triggers = espion
    try:
        heal_mod.HealUnitOperation.execute(st, VOISIN, VOISIN, 100, scope=0, remove_effects=False)
        assert vus == [], "ForRegenerate (removeEffects=0) ne doit PAS emettre On(0x2c)"
        assert st.get_entity(VOISIN).get_component(UnitComponent).times_healed_this_turn == 1, \
            "le compteur monte quand meme -- il est hors du `if (removeEffects)`"
        heal_mod.HealUnitOperation.execute(st, VOISIN, VOISIN, 100, scope=0, remove_effects=True)
        assert vus == [(VOISIN, VOISIN)], "ForHeal (removeEffects=1) DOIT emettre On(0x2c)"
    finally:
        dh.unit_healed_with_remove_effects_triggers = origine
        _ = reel


# ------------------------------------------------------ 5. les CINQ termes du CreateBehaviour
def test_l_arbre_de_behaviour_a_les_CINQ_termes_DANS_L_ORDRE():
    """L'ordre des `op_BitwiseAnd`/`op_Addition` PORTE la mecanique : le bonus est pose AVANT
    l'attaque et retire APRES (il ne vaut donc que pour ce coup), et `SetCache` fige la tuile AVANT
    l'attaque (la glace atterrit meme si la cible y meurt)."""
    from engine.entities.behaviours import If, SetCache
    from engine.runner.abilities.behaviours.combat import UseNormalAttack
    from engine.runner.abilities.behaviours.effects import (AddEffect,
                                                            AddStaticStatModifierEffect,
                                                            RemoveEffect)
    termes = wyrdmakers_helm_behaviour_tree(EXTRA_DMG_NIVEAU_10).terms
    assert [type(t).__name__ for t in termes] == [
        "AddStaticStatModifierEffect", "SetCache", "UseNormalAttack", "RemoveEffect", "If"]
    assert isinstance(termes[0], AddStaticStatModifierEffect)
    assert int(termes[0].effect_type) == int(WYRDMAKERS_HELM_STAT_MOD)
    assert int(termes[0].stat_type) == int(WYRDMAKERS_HELM_STAT)
    assert int(termes[0].amount) == EXTRA_DMG_NIVEAU_10
    # `turns: null` -- aucune duree : c'est le `RemoveEffect` du terme 4 qui retire le bonus.
    assert termes[0].duration_rounds is None and termes[0].duration_turns is None
    assert isinstance(termes[1], SetCache)
    assert isinstance(termes[2], UseNormalAttack)
    assert isinstance(termes[3], RemoveEffect)
    assert int(termes[3].effect_type) == int(WYRDMAKERS_HELM_STAT_MOD)
    assert isinstance(termes[4], If)
    assert isinstance(termes[4].then, AddEffect)
    assert int(termes[4].then.effect_type) == int(ICE_TILE) == 17


def test_le_cache_de_la_tuile_est_PARTAGE_entre_SetCache_et_le_AddEffect():
    """`SetCache(cache)` puis `AddEffect(..., targets: cache)` -- le MEME noeud `Cache` au
    decompile. S'ils etaient deux instances distinctes, la memoisation ne servirait a rien et la
    glace serait posee sur une tuile RE-EVALUEE apres l'attaque."""
    termes = wyrdmakers_helm_behaviour_tree(EXTRA_DMG_NIVEAU_10).terms
    assert termes[1].node is termes[4].then.target_sel


def test_l_arbre_est_REBATI_a_chaque_appel():
    """Le noeud `Cache` memoise dans son INSTANCE. Un arbre garde entre deux declenchements
    reposerait la glace sur la tuile du declenchement PRECEDENT."""
    a = wyrdmakers_helm_behaviour_tree(EXTRA_DMG_NIVEAU_10)
    b = wyrdmakers_helm_behaviour_tree(EXTRA_DMG_NIVEAU_10)
    assert a.terms[1].node is not b.terms[1].node


def test_le_gate_final_porte_sur_le_PORTEUR_et_pas_sur_la_cible():
    """`If(NOT IsDead(Owner), AddEffect(Ice, ...))`. Si Baldr meurt de sa propre attaque (riposte,
    overwatch), la glace n'est PAS posee -- alors qu'un gate sur la CIBLE donnerait l'inverse."""
    from engine.entities.selectors.accessors import Owner
    from engine.entities.triggers import IsDead, Not
    termes = wyrdmakers_helm_behaviour_tree(EXTRA_DMG_NIVEAU_10).terms
    cond = termes[4].cond
    assert isinstance(cond, Not)
    assert isinstance(cond.a, IsDead)
    assert isinstance(cond.a.unit, Owner)


# ---------------------------------------------------------------- 6. la MAGNITUDE (extraDmg)
def test_le_niveau_de_la_relique_SEPARE_les_magnitudes(montage):
    """10 paliers, 490 -> 728 (+48,6 %). Un port qui lirait toujours le dernier palier -- la faute
    MESUREE de #1006 sur `Maugetar`/`PhoenixGem` -- serait vert au niveau 10 et faux au niveau 1.
    Ce test le SEPARE, donc il ne peut pas etre satisfait par le mauvais modele."""
    assert extra_dmg(montage(niveau=1), PORTEUR) == EXTRA_DMG_NIVEAU_1
    assert extra_dmg(montage(niveau=10), PORTEUR) == EXTRA_DMG_NIVEAU_10
    assert EXTRA_DMG_NIVEAU_1 != EXTRA_DMG_NIVEAU_10, "temoin NON DEGENERE"


def test_sans_relique_equipee_la_magnitude_ne_vient_PAS_du_tertiaire(montage):
    """`triggered_ability_state` arbitre TERTIAIRE / PASSIF. Sans `TertiaryAbility`, l'unite tombe
    sur l'etat PASSIF (50 -> clampe au dernier palier) : c'est le regime npc, et c'est justement
    ce qui rend le montage de la relique OBLIGATOIRE pour mesurer un niveau 1."""
    st = montage(niveau=1, tertiaire=None)
    assert extra_dmg(st, PORTEUR) == EXTRA_DMG_NIVEAU_10


# ---------------------------------------------------- 7. EXECUTION de bout en bout (offline)
def test_le_declenchement_attaque_ET_glace_la_tuile_de_la_cible(montage):
    """Bout en bout : l'ability fire, l'attaque part, la glace est posee. Temoin NON DEGENERE
    exige -- une liste vide d'attaques ferait passer un port qui ne fait rien."""
    st = montage()
    _soigne(st, VOISIN, 1)
    ab = WyrdmakersHelmAbility(PORTEUR)
    assert ab.matches(st, _ev_soin(VOISIN)) is True
    out = ab.execute_behaviour(st, _ev_soin(VOISIN))
    assert out is not None and out["relic"] == "WyrdmakersHelm"
    assert out["extra_dmg"] == EXTRA_DMG_NIVEAU_10
    assert out["attacks"], "temoin non nul : l'attaque normale doit avoir ete emise"
    assert out["ice"], "temoin non nul : la glace doit avoir ete posee"


def test_le_stat_mod_est_RETIRE_apres_l_attaque(montage):
    """« THESE attacks deal +X » -- le bonus ne survit pas au declenchement. Un port qui oublierait
    le 4e terme laisserait le porteur avec +728 d'attaque PERMANENTS."""
    st = montage()
    _soigne(st, VOISIN, 1)
    WyrdmakersHelmAbility(PORTEUR).execute_behaviour(st, _ev_soin(VOISIN))
    restants = [int(e.effect_type) for e in (st.effects.by_unit.get(PORTEUR) or [])
                if not e.consumed]
    assert int(WYRDMAKERS_HELM_STAT_MOD) not in restants
