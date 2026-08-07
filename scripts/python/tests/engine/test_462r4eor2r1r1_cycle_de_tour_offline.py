"""#462-r4e-o-r2-r1-r1 -- GARDE du REJEU MULTI-TOURS : la rotation `SereneUnifier`, le compteur PAR
JOUEUR, et l'appel entier de `FinishUnitTurnOperation` depuis la fin de tour.

CE QUE LA MESURE A ETABLI (`probe_462r4eor2r1_retour_a_la_vie_over_reduce.py`, MC1_67 / 777, volet
resurrect). Le rejeu OFFLINE de bout en bout rendait `[214, 281, 255, 227, 286]` la ou le natif rend
`[1044, 886, 70, 0, 0]`, et les flags de l'unite ressuscitee `[14]` contre `[1, 3, 4, 14]`. Aucun
test d'ETAT ne le voyait : le verdict de la purge etait calcule A ETAT EGAL, ou le port etait deja
bit-exact.

⚠ LA CAUSE N'ETAIT PAS « UN COMPTEUR DE ROUND QUE LE PORT N'AVANCE PAS ». Le compteur natif existe,
et le port l'a : `TurnComponent+0x38` (`State.turn_counts`), incremente par
`IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer` (son ecrivain UNIQUE -- le port
l'ecrivait dans `StartTurnOperation` jusqu'a #287-r11-r1-r1-r1-r1). Il manquait TROIS crans, chacun
mesure separement par sa propre mutation du probe :

  1. son CONSOMMATEUR -- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SereneUnifierAbility`
     (`On(0x13 = TurnStart_Other) & IsTurnOf(Owner) & OwnerIsCaster` -> six
     `If(Modulo(PlayerTurnsStarted(Self), 3, k))`) n'etait pas portee : les EFFETS l'etaient depuis
     longtemps, la ROTATION qui les pose ne l'etait pas ;
  2. son SEED -- `State.turn_counts` restait VIDE sur tout etat recharge, donc
     `PlayerTurnsStarted` rendait 0 et la phase valait `0 % 3 == 0` a chaque rejeu ;
  3. l'APPEL de `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` depuis
     `IdunBattle.Operations.EndTurnOperation$$Execute` -- le port n'en emettait qu'UNE jambe
     (`On(0x28)`), sautant la POSE des flags 1 / 3 / 4.

CE FICHIER EST OFFLINE, ET C'EST DELIBERE : le montage live (sur-tuerie, retour a la vie natif,
trois changements de tour) vit dans le probe. Ici on fige les invariants de STRUCTURE, ceux qu'une
regression silencieuse rouvrirait.

ASCII only.
"""
from __future__ import annotations

import inspect

import pytest

from engine.runner.state import State
from engine.runner.components import (HealthComponent, UnitComponent, UnitFlagsComponent,
                                      OwnerComponent, StatsComponent)
from engine.runner.operations.turnflow import EndTurnOperation, FinishUnitTurnOperation
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
from engine.runner.operations.triggers.loki.serene_unifier import (
    SereneUnifierRotationAbility, PHASE_STORM_OF_FIRE, PHASE_SENSE_OF_STONE,
    PHASE_ZEPHYRS_GRACE, VISUAL_CYCLE, serene_unifier_tree)
from engine.entities.formulas import PlayerTurnsStarted, UnitTurnsStarted
from engine.entities.selectors.tiles import Caster
from engine.entities.effect_type import EffectType
from engine.entities.stats import StatType
from engine.dsl.base import DslContext
from engine.dsl.event_trigger_type import EventTriggerType


# ================================================================================================
# 1. LE COMPTEUR -- `PlayerTurnsStarted` != `UnitTurnsStarted`, et les confondre decale la phase
# ================================================================================================

def test_les_deux_compteurs_de_tour_sont_DISTINCTS():
    """`IdunBattle.Entities.Formulas.UnitsPlayerTurnsStartedFormula$$Calculate` lit
    `TurnComponent.GetAmountOfTurnsStartedByPlayer` (le dict PAR JOUEUR `+0x38`) ;
    `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate` lit `GetStat(unit, 0xc)`
    (`UnitComponent+0x58`). Les deux existent dans le binaire, le port en a deux noeuds, et le
    cycle de `SereneUnifier` indexe le PREMIER quand celui de `FleshmetalGuns` indexe le SECOND.

    Le test les met en REGIME SEPARANT (valeurs differentes) : sans cela il serait vacu."""
    u = {"id": 7}
    ctx = DslContext(units=[u], caster=u,
                     player_turns_started=lambda _u: 3,
                     get_stat=lambda _u, st, va=0, lv=None: 11)
    assert PlayerTurnsStarted(Caster()).calculate(ctx) == 3
    assert UnitTurnsStarted(Caster()).calculate(ctx) == 11
    assert 3 % 3 != 11 % 3, "regime NON separant : les deux compteurs rendraient la meme phase"


def test_PlayerTurnsStarted_degrade_a_zero_quand_le_canal_est_ABSENT():
    """Mirror du `if (unit == null) return 0` natif : un arbre purement numerique (aucun canal
    `player_turns_started` cable) ne LEVE pas, il rend 0."""
    u = {"id": 7}
    assert PlayerTurnsStarted(Caster()).calculate(DslContext(units=[u], caster=u)) == 0


def test_le_canal_player_turns_started_lit_bien_turn_counts_du_PROPRIETAIRE():
    """Le canal cable par `entities_from_state` : `State.turn_counts[OwnerComponent.player]`.
    Deux joueurs a des compteurs DIFFERENTS -> regime separant."""
    from engine.runner.abilities.behaviours.context import entities_from_state
    st = State()
    ids = []
    for player in (3, 4):
        e = st.add_entity()
        e.add_component(UnitComponent("u%d" % player, True))
        e.add_component(OwnerComponent(team=player, player=player))
        e.add_component(HealthComponent(100, 100))
        ids.append(e.id)
    st.turn_counts = {3: 5, 4: 2}
    ctx = entities_from_state(st, ids[0], None)
    assert ctx.player_turns_started({"id": ids[0]}) == 5
    assert ctx.player_turns_started({"id": ids[1]}) == 2


# ================================================================================================
# 2. LE SEED -- `snapshot._load_turn_counts`, derive de la stat 12 deja captee
# ================================================================================================

def _unite(st, player, alive, turns_started):
    e = st.add_entity()
    e.add_component(UnitComponent("u", alive))
    e.add_component(OwnerComponent(team=player, player=player))
    e.add_component(HealthComponent(100 if alive else 0, 100))

    class _Stats:
        def get_stat(self, stat_type, variant=0, level=None):
            return turns_started if int(stat_type) == int(StatType.TURNS_STARTED) else 0

    class _Ctx:
        stats = _Stats()
    e.add_component(StatsComponent(ctx=_Ctx()))
    return e.id


def test_le_seed_prend_le_MAX_et_ne_SUR_ESTIME_jamais():
    """`StartTurnOperation$$Execute` bumpe `turnsStarted@+0x58` de CHAQUE unite vivante du joueur au
    MEME instant qu'il bumpe `TurnComponent+0x38[player]` : aucune unite ne peut porter plus de
    bumps que de tours demarres, et une unite presente depuis le 1er tour en porte exactement
    autant. Le `max` est donc EXACT des qu'une telle unite existe -- ici l'unite a 4."""
    from engine.runner.snapshot import _load_turn_counts
    st = State()
    _unite(st, 3, True, 1)          # arrivee tard (summon) -> sous-compte
    _unite(st, 3, True, 4)          # presente depuis le debut -> la valeur EXACTE
    _load_turn_counts(st)
    assert st.turn_counts[3] == 4


def test_le_seed_EXCLUT_les_unites_MORTES():
    """`PlayerComponent$$get_CurrentlyOwnedUnitIds` finit par un `RemoveAll` des defaits -> leur
    compteur est GELE. Une morte a 9 ne doit pas faire croire a 9 tours demarres."""
    from engine.runner.snapshot import _load_turn_counts
    st = State()
    _unite(st, 3, False, 9)         # MORTE, compteur gele et plus haut
    _unite(st, 3, True, 2)
    _load_turn_counts(st)
    assert st.turn_counts[3] == 2


def test_le_seed_n_INVENTE_pas_de_zero():
    """Tri-etat : un joueur dont aucune unite vivante ne porte la stat n'entre PAS au dict -- un
    `0` ECRIT se lirait comme une mesure."""
    from engine.runner.snapshot import _load_turn_counts
    st = State()
    e = st.add_entity()
    e.add_component(UnitComponent("u", True))
    e.add_component(OwnerComponent(team=3, player=3))
    _load_turn_counts(st)
    assert 3 not in st.turn_counts


# ================================================================================================
# 3. LA ROTATION -- registre, vecteur, et la table des phases
# ================================================================================================

def test_la_rotation_est_au_registre_sur_le_vecteur_TurnStart_Other():
    """`...SereneUnifierAbility$$CreateTrigger` = `On(0x13 = TurnStart_Other, 1) &
    <DSLTriggers+0x28 = IsTurnOf(Owner)> & get_OwnerIsCaster`.

    ⚠ PAS `On(0x16 = TurnStart_Actions)`, celui du cycle jumeau de `FleshmetalGuns` : les deux
    events sortent du MEME `StartTurnOperation$$Execute` mais dans la sequence 0x12..0x16, donc
    l'ordre relatif compte."""
    assert SereneUnifierRotationAbility in (ABILITY_TRIGGERS.get("SereneUnifier") or [])
    assert SereneUnifierRotationAbility.event_id == int(EventTriggerType.TurnStart_Other)


def test_les_trois_phases_du_cycle_sont_celles_du_decompile():
    """`Modulo(PlayerTurnsStarted(Self), Direct(3), Direct(k))`, k dans l'ordre du decompile :
    0 -> 0x493 StormOfFire (ATTAQUE), 1 -> 0x491 SenseOfStone (DEFENSE), 2 -> 0x492 ZephyrsGrace
    (MOUVEMENT). Les trois `*_Visual` sont apparies a la MEME phase que leur effet reel."""
    assert (PHASE_STORM_OF_FIRE, PHASE_SENSE_OF_STONE, PHASE_ZEPHYRS_GRACE) == (0, 1, 2)
    assert VISUAL_CYCLE == (
        (PHASE_STORM_OF_FIRE, int(EffectType.SereneUnifierStormOfFire_Visual)),
        (PHASE_SENSE_OF_STONE, int(EffectType.SereneUnifierSenseOfStone_Visual)),
        (PHASE_ZEPHYRS_GRACE, int(EffectType.SereneUnifierZephyrsGrace_Visual)))


def _marcher(noeud, vus=None):
    """Parcours de l'ARBRE CONSTRUIT (pas de son source : une docstring qui CITE un nom n'est pas
    un noeud, et l'y chercher rendrait le controle faux dans les deux sens)."""
    vus = [] if vus is None else vus
    vus.append(noeud)
    for nom in ("a", "b", "cond", "then", "otherwise", "left", "right", "nodes", "children"):
        v = getattr(noeud, nom, None)
        if v is None:
            continue
        for x in (v if isinstance(v, (list, tuple)) else [v]):
            if hasattr(x, "__dict__") or hasattr(x, "__slots__"):
                _marcher(x, vus)
    return vus


def test_l_arbre_porte_les_SIX_branches_et_le_compteur_PAR_JOUEUR():
    """L'arbre est un mirror de STRUCTURE : six `If(Modulo(...))`, et le noeud de phase est bien
    `PlayerTurnsStarted` -- si un jour quelqu'un le remplace par `UnitTurnsStarted` (le compteur du
    cycle voisin `FleshmetalGuns`), la phase glisse sans qu'aucune erreur ne soit levee."""
    from engine.entities.behaviours import If as IfBehaviour
    from engine.entities.triggers import Modulo
    noeuds = _marcher(serene_unifier_tree())
    ifs = [n for n in noeuds if isinstance(n, IfBehaviour)]
    assert len(ifs) == 6, "3 phases + 3 visuels = 6 branches, vu %d" % len(ifs)
    modulos = [n for n in noeuds if isinstance(n, Modulo)]
    assert len(modulos) == 6
    for m in modulos:
        assert isinstance(m.a, PlayerTurnsStarted), \
            "le compteur du cycle est le dict PAR JOUEUR, pas %s" % type(m.a).__name__
        assert not isinstance(m.a, UnitTurnsStarted)


# ================================================================================================
# 4. LA FIN DE TOUR -- `EndTurnOperation` appelle l'OPERATION ENTIERE
# ================================================================================================

def _joueur_avec_unite(st, player, alive=True):
    e = st.add_entity()
    e.add_component(UnitComponent("u", alive))
    e.add_component(OwnerComponent(team=player, player=player))
    e.add_component(HealthComponent(100 if alive else 0, 100))
    e.add_component(UnitFlagsComponent())
    return e.id


def test_la_fin_de_tour_POSE_les_flags_1_3_et_4():
    """`EndTurnOperation$$Execute` appelle le slot 0x23 `(unit, false)` par unite possedee, donc
    `FinishUnitTurnOperation$$Execute` : `Add(0x01 = ArrivedAtFinalTile)`, `Add(0x03 =
    TurnFinished)` et, en derniere instruction, le slot 0x76 -> `NoActionAvailable` (4).

    MESURE qui l'a impose : l'unite RESSUSCITEE portait `[14]` cote port contre `[1, 3, 4, 14]`
    cote natif -- exactement ces trois flags."""
    st = State()
    uid = _joueur_avec_unite(st, 3)
    st.current_player_id = 3
    EndTurnOperation.execute(st, advance=False)
    fl = st.get_entity(uid).get_component(UnitFlagsComponent)
    assert fl.has(UnitFlagsComponent.ARRIVED_AT_FINAL_TILE)
    assert fl.has(UnitFlagsComponent.TURN_FINISHED)
    assert fl.has(UnitFlagsComponent.NO_ACTION_AVAILABLE)


def test_la_fin_de_tour_NE_TOUCHE_PAS_a_l_autre_joueur():
    """La boucle native itere `PlayerComponent.CurrentlyOwnedUnitIds` du joueur qui FINIT, et lui
    seul. Sans ce controle le test precedent passerait meme sur un port qui marque tout le monde."""
    st = State()
    _mien = _joueur_avec_unite(st, 3)
    autre = _joueur_avec_unite(st, 4)
    st.current_player_id = 3
    EndTurnOperation.execute(st, advance=False)
    fl = st.get_entity(autre).get_component(UnitFlagsComponent)
    assert not fl.flags, "l'unite du joueur 4 ne finit pas le tour du joueur 3 : %r" % fl.flags


def test_la_fin_de_tour_EXCLUT_les_unites_MORTES():
    """MEME filtre que `_bump_turns_started` / `_bump_turns_finished` : le `RemoveAll` des defaits
    de `PlayerComponent$$get_CurrentlyOwnedUnitIds`."""
    st = State()
    mort = _joueur_avec_unite(st, 3, alive=False)
    st.current_player_id = 3
    EndTurnOperation.execute(st, advance=False)
    fl = st.get_entity(mort).get_component(UnitFlagsComponent)
    assert not fl.flags, "une unite MORTE n'est plus dans CurrentlyOwnedUnitIds : %r" % fl.flags


def test_le_depart_de_tour_RETIRE_ce_que_la_fin_de_tour_a_pose():
    """`StartTurnOperation` appelle `RemoveTurnFlags(includeNoAction = 0, newActivation = 1)` :
    1 et 3 repartent, 4 est CONSERVE (c'est `VerifyUnitsTurnFinished`, slot 0x77, qui le leve
    quand l'unite regagne des options). Sans ce cran, poser les flags en fin de tour les rendrait
    COLLANTS et fermerait l'unite pour toujours."""
    from engine.runner.operations.turnflow import StartTurnOperation
    st = State()
    uid = _joueur_avec_unite(st, 3)
    st.current_player_id = 3
    EndTurnOperation.execute(st, advance=False)
    StartTurnOperation.execute(st, 3)
    fl = st.get_entity(uid).get_component(UnitFlagsComponent)
    assert not fl.has(UnitFlagsComponent.ARRIVED_AT_FINAL_TILE)
    assert not fl.has(UnitFlagsComponent.TURN_FINISHED)
    assert fl.has(UnitFlagsComponent.NO_ACTION_AVAILABLE), \
        "`includeNoAction = 0` CONSERVE le flag 4 au changement de tour"


def test_le_CHANGEMENT_de_tour_AVANCE_le_compteur_PAR_JOUEUR():
    """Le maillon que `PlayerTurnsStarted` relit. C'est ce qui fait tourner la phase du cycle.

    ⚠ L'ECRIVAIN A CHANGE DE PLACE (#287-r11-r1-r1-r1-r1), et le TITRE avec lui : ce n'est PAS le
    depart de tour qui avance `TurnComponent+0x38`, c'est le CHANGEMENT
    (`TurnComponent$$SetCurrentPlayer`, ecrivain unique -- `StartTurnOperation$$Execute` ne fait
    que LIRE `GetAmountOfTurnsStartedByCurrentPlayer`). Le montage a DEUX joueurs : avec un seul,
    `FindNextPlayer` rendrait le courant et le NO-OP natif ne compterait rien.

    Les deux jambes sont assertionnees SEPAREMENT, sinon le test ne dirait pas OU vit l'ecrivain."""
    from engine.runner.operations.turnflow import ChangeTurnOperation, StartTurnOperation
    st = State()
    _joueur_avec_unite(st, 3)
    _joueur_avec_unite(st, 4)
    st.current_player_id = 4
    st.turn_counts = {3: 2}
    assert ChangeTurnOperation.execute(st) == 3, "l'ordre de tour doit ramener au joueur 3"
    assert st.turn_counts[3] == 3, "`SetCurrentPlayer` bumpe l'ENTRANT (`started[current] += 1`)"
    StartTurnOperation.execute(st, 3)
    assert st.turn_counts[3] == 3, (
        "`StartTurnOperation$$Execute` n'ECRIT pas `+0x38` -- un second bump ici double le compteur")


# ================================================================================================
# 5. CONTRE-EPREUVE -- chaque foyer mute doit faire ROUGIR le test qui le garde
# ================================================================================================

def test_contre_epreuve_le_foyer_de_fin_de_tour_est_LOAD_BEARING(monkeypatch):
    """Si `EndTurnOperation` cesse d'appeler l'operation entiere, les flags ne sont plus poses.
    `a_mordu` est evalue SEPAREMENT du verdict : on assertionne d'abord que la mutation a bien
    remplace le foyer, puis que l'observable change."""
    appels = []

    def _faux(state, unit_id, forced=False):
        appels.append(int(unit_id))
        return {"unit": int(unit_id), "found": True, "mute": True}

    monkeypatch.setattr(FinishUnitTurnOperation, "execute", staticmethod(_faux))
    st = State()
    uid = _joueur_avec_unite(st, 3)
    st.current_player_id = 3
    EndTurnOperation.execute(st, advance=False)
    assert appels == [uid], "la mutation n'a PAS mordu : le foyer n'est pas celui qu'on croit"
    fl = st.get_entity(uid).get_component(UnitFlagsComponent)
    assert not fl.flags, "le foyer mute doit faire disparaitre l'observable"
