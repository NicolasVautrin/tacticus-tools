"""#1011-r1 -- CONTRE-EPREUVE 100 % OFFLINE de la relique `PhasalSubjugator` (1557,
`necroOverlord`) : ses DEUX classes natives, leurs DEUX vecteurs, et le re-declenchement de
`MyWillBeDoneOverlord` (1556) par la branche `Custom`.

Chaque etage est un COUPLE (un bras qui DOIT rendre le comportement, un bras qui DOIT le refuser) --
un test a un seul bras peut passer pour une raison etrangere a ce qu'il croit mesurer.

  0. les ids, les DEUX entrees de registre et les constantes gameconfig sont LUS, pas devines ;
  1. classe 1 (`On(0x1c = ArrivedAtFinalTile)`) : le gate `NOT AmountIsGreaterThanZero(Friends(
     Owner, UnitsWithVisualId(...), OnlyAlive))`. Bras negatifs : un Guerrier ami VIVANT ferme ;
     un Guerrier ami MORT n'ferme PAS (`selectionType = 1 = OnlyAlive` -- le discriminant que
     `UnitSelectionType.Any` aurait perdu) ; un Guerrier ENNEMI ne ferme pas (`Friends`) ;
     l'acteur qui n'est pas le porteur ne declenche pas (`get_OwnerIsActor`) ;
  2. classe 2 (`On(0x29 = UnitFinishedTurnNormally)`) : le gate `HasFriendlyWarrior` vit dans le
     BEHAVIOUR (un `If`), PAS dans le trigger -- donc le re-declenchement de 1556 a lieu MEME quand
     un Guerrier est vivant. Bras : avec Guerrier -> 0 spawn + retrigger ; sans -> spawn + retrigger ;
  3. le re-declenchement est DISPATCHE (branche `Custom` de 1556) et il n'est pas la PURGE ;
  4. le niveau lu est celui de l'`AbilityState` **TERTIAIRE** : contre-epreuve par MUTATION du ctx
     (niveau passif != niveau tertiaire -> les PV du Guerrier spawne changent).

TEMOIN NON DEGENERE : l'etage 4 assertionne que les deux paliers de `summonHp` DIFFERENT avant de
comparer (sinon l'egalite ne prouverait rien), et l'etage 1 assertionne que le gate rend VRAI dans
au moins un montage (sinon tous les bras negatifs passeraient sur un arbre mort). ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import pytest                                                               # noqa: E402,F401

import hexgeo                                                               # noqa: E402
from engine.dsl.effects import ExecutionContext                             # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                  # noqa: E402
from engine.entities.ability_constant_type import AbilityConstantType       # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType     # noqa: E402
from engine.entities.effects_state import EffectsState                      # noqa: E402
from engine.entities.unit_context import UnitContext                        # noqa: E402
from engine.entities.unit_selection_type import UnitSelectionType           # noqa: E402
from engine.runner.abilities.behaviours.context import entities_from_state  # noqa: E402
from engine.runner.abilities.behaviours.lifecycle import TRIGGERED_ABILITY_BEHAVIOURS  # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,      # noqa: E402
                                      PositionComponent, StatsComponent, UnitComponent)
from engine.runner.prng import IntBasedMersenneTwister                      # noqa: E402
from engine.runner.state import State                                       # noqa: E402
from engine.runner.operations.triggers.base import TriggerEvent             # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import RELIC_ABILITY_TRIGGERS  # noqa: E402
from engine.runner.operations.triggers.loki.phasal_subjugator import (      # noqa: E402
    ABILITY_ID, MY_WILL_BE_DONE_OVERLORD, PHASAL_SUBJUGATOR, PhasalSubjugatorSummonAbility,
    PhasalSubjugatorTriggerPassiveAbility, WARRIOR_SELECTION, _summon_unit_id,
    phasal_has_friendly_warrior, phasal_spawn_tree, phasal_trigger_passive_tree)
from engine.utilities.utility_type import UtilityType                       # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/operations/triggers/loki/phasal_subjugator.py",
        "scripts/python/engine/runner/operations/triggers/loki/my_will_be_done_overlord.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        # Les primitives MIRRORS que les etages traversent.
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/tiles.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/entities/behaviours.py",
        "scripts/python/engine/runner/abilities/behaviours/summon.py",
        "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
        "scripts/python/engine/runner/operations/spawn.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        # Les mirrors d'enum dont les ordinaux sont FIGES au site par l'etage 0.
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/utilities/utility_type.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Deux etages lisent le GAMECONFIG (`PhasalSubjugator.constants.unitId` et "
              "`variables.summonHp`), qui se perime SEPAREMENT du build ; l'etage 0 fige des "
              "ORDINAUX au site (1557 / 1556 / 0x1c / 0x29 / 7 / 1), qu'un renumerotage rendrait "
              "faux sans toucher aucun des chemins ci-dessus.",
}

COLS, ROWS = 7, 7
OWNER_ID, W_ALIVE, W_DEAD, W_ENEMY, ALLY_ID, ENEMY_ID = 10, 20, 30, 40, 50, 60
HP = 40000
PLAYER_COUNT = 2
WARRIOR = "necroSmnWarrior"
#: Deux paliers de `PhasalSubjugator.variables.summonHp` que l'etage 4 oppose.
LVL_TERTIAIRE, LVL_PASSIF = 1, 10


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _board():
    from engine.entities.pathfinding.board import Board
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tiles, adjacency="evenq")


def _ctx(uid, visual, *, traits=(), tertiary=None, level=LVL_TERTIAIRE,
         passive_level=LVL_PASSIF):
    """Le VRAI `UnitContext`, pas un stub. `tertiary_ability*` est le montage de la voie TERTIAIRE,
    c.-a-d. ce que le canal live `unitAbilityStates` (#357) pose. On separe DELIBEREMENT le niveau
    tertiaire du niveau passif -- l'etage 4 en depend."""
    c = UnitContext(entity_id=int(uid), visual_id=visual, traits=list(traits),
                    active_ability_level=passive_level, passive_ability_level=passive_level,
                    ability_variables_multiplier=100)
    c.traits_measured = True                 # traits FOURNIS, pas re-derives
    c.tertiary_ability = tertiary
    c.tertiary_ability_level = int(level)
    c.tertiary_ability_variables_multiplier = 100
    return c


def _unite(st, uid, visual, *, team=1, alive=True, pos=(0, 0), traits=(), tertiary=None,
           level=LVL_TERTIAIRE, passive_level=LVL_PASSIF):
    import gameconfig as GC
    e = st.add_entity(uid)
    tr = list(traits) or list((GC.unit(visual) or {}).get("traits") or [])
    e.add_component(UnitComponent(visual, alive))
    e.add_component(OwnerComponent(team, team))
    e.add_component(HealthComponent(HP if alive else 0, HP))
    e.add_component(StatsComponent(ctx=_ctx(uid, visual, traits=tr, tertiary=tertiary,
                                            level=level, passive_level=passive_level)))
    e.add_component(PositionComponent(int(pos[0]), int(pos[1])))
    return uid


def _state(*, warrior_alive=False, warrior_dead=False, warrior_enemy=False,
           level=LVL_TERTIAIRE):
    """Etat synthetique. Le PORTEUR (`necroOverlord`, team 1) en (1,1) ; un allie MECANIQUE adjacent
    et un ennemi adjacent a lui (pour que `MyWillBeDoneOverlord` ait une cible eligible au
    re-declenchement) ; et, a la demande, un Guerrier ami VIVANT / ami MORT / ENNEMI vivant.

    Chaque Guerrier est place LOIN du porteur : le gate `UnitsWithVisualId` est BOARD-WIDE (source =
    le slot partage `factory+0x80`), donc la distance ne doit RIEN changer -- c'est aussi ce que
    l'etage 1 verifie implicitement."""
    st = State()
    st.board = _board()
    st.effects = EffectsState.seed({})
    st.rng = IntBasedMersenneTwister(7)
    _unite(st, OWNER_ID, "necroOverlord", team=1, pos=(1, 1), tertiary=ABILITY_ID, level=level)
    # `necroWarden` : `Mechanical` (exige par `GetTargetFriend`), adjacent au porteur.
    _unite(st, ALLY_ID, "necroWarden", team=1, pos=(1, 2))
    # ennemi ADJACENT a l'allie -> `ValidNormalAttackTargets(it, Tiles(it))` non vide.
    _unite(st, ENEMY_ID, "orksRuntherd", team=2, pos=(1, 3))
    if warrior_alive:
        _unite(st, W_ALIVE, WARRIOR, team=1, pos=(6, 6))
    if warrior_dead:
        _unite(st, W_DEAD, WARRIOR, team=1, alive=False, pos=(6, 5))
    if warrior_enemy:
        _unite(st, W_ENEMY, WARRIOR, team=2, pos=(6, 0))
    return st


def _ev_arrived(actor_id=OWNER_ID):
    """`On(0x1c = ArrivedAtFinalTile)` -- `dispatch/move_death.arrived_at_final_tile_triggers`
    publie `actor == target == l'unite qui vient de clore son deplacement`."""
    return TriggerEvent(int(EventTriggerType.ArrivedAtFinalTile), actor_id, actor_id,
                        ranged=False, profile=None)


def _ev_finished(actor_id=OWNER_ID):
    """`On(0x29 = UnitFinishedTurnNormally)`."""
    return TriggerEvent(int(EventTriggerType.UnitFinishedTurnNormally), actor_id, actor_id,
                        ranged=False, profile=None)


def _warriors(state):
    """Les unites du plateau dont le `visualId` matche la constante -- lecture INDEPENDANTE du
    noeud teste (l'oracle ne doit pas etre l'implementation)."""
    import gameconfig as GC
    vid = _summon_unit_id()
    formes = {vid, (GC.unit(vid) or {}).get("visualId")}
    from engine.runner.components import UnitComponent
    out = []
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.visual_id in formes:
            out.append(int(uid))
    return sorted(out)


# --------------------------------------------------------------------------------------------
# Etage 0 -- ids, registres et constantes gameconfig, LUS
# --------------------------------------------------------------------------------------------

def test_ids_registre_et_constantes_sont_lus_au_decompile():
    """Ces ordinaux sont ECRITS ICI pour qu'un renumerotage du build les fasse ROUGIR au SITE (le
    mirror d'enum, lui, redeviendrait vert apres regeneration -- c'est le cran du dessous de
    `probe_313`)."""
    assert int(PHASAL_SUBJUGATOR) == 0x615 == 1557
    assert int(TriggeredAbilityType.PhasalSubjugator) == PHASAL_SUBJUGATOR
    assert MY_WILL_BE_DONE_OVERLORD == 0x614 == 1556
    assert int(AbilityConstantType.unitId) == 0x0
    assert int(WARRIOR_SELECTION) == 1 == int(UnitSelectionType.OnlyAlive)
    assert int(UtilityType.Tile) == 7
    assert PhasalSubjugatorSummonAbility.event_id == 0x1c == 28 == int(
        EventTriggerType.ArrivedAtFinalTile)
    assert PhasalSubjugatorTriggerPassiveAbility.event_id == 0x29 == 41 == int(
        EventTriggerType.UnitFinishedTurnNormally)
    # LA cle 0x615 enregistre DEUX classes (lambda `b__28_433` : une `List` + DEUX `Add`).
    assert RELIC_ABILITY_TRIGGERS.get(ABILITY_ID) == [PhasalSubjugatorSummonAbility,
                                                      PhasalSubjugatorTriggerPassiveAbility]


def test_la_constante_unitId_est_lue_au_gameconfig_pas_codee():
    assert _summon_unit_id() == WARRIOR, (
        "gameconfig PhasalSubjugator.constants.unitId = %r" % (_summon_unit_id(),))


# --------------------------------------------------------------------------------------------
# Etage 1 -- classe 1 : le gate `HasFriendlyWarrior`, un bras negatif par conjoint
# --------------------------------------------------------------------------------------------

def test_sans_guerrier_ami_le_trigger_MORD_et_pose_un_guerrier():
    """Le bras POSITIF -- sans lui, tous les bras negatifs ci-dessous passeraient sur un arbre mort."""
    st = _state()
    assert _warriors(st) == [], "montage : le plateau porte deja un Guerrier"
    ab = PhasalSubjugatorSummonAbility(OWNER_ID)
    assert ab.matches(st, _ev_arrived()) is True
    r = ab.execute_behaviour(st, _ev_arrived())
    assert r is not None and len(r["spawned"]) == 1, (
        "aucun Guerrier pose : `Spawn(First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles("
        "Owner)))))` a rendu un ensemble vide")
    assert _warriors(st) == sorted(r["spawned"])


def test_un_guerrier_ami_VIVANT_ferme_le_gate():
    st = _state(warrior_alive=True)
    assert _warriors(st) == [W_ALIVE], "montage : le Guerrier vivant n'est pas dans l'etat"
    assert PhasalSubjugatorSummonAbility(OWNER_ID).matches(st, _ev_arrived()) is False


def test_un_guerrier_ami_MORT_ne_ferme_PAS_le_gate():
    """LE cran de l'etage. `selectionType = 1 = OnlyAlive` est le TYPE DECLARE des deux arguments
    (`frida/methods.tsv`) : un Guerrier MORT ne compte pas, donc l'Overlord en re-pose un. Ecrire
    `UnitSelectionType.Any` ici (ou omettre le filtre) rendrait la relique MUETTE des la premiere
    mort de son summon -- une degradation RESTRICTIVE et totalement silencieuse."""
    st = _state(warrior_dead=True)
    assert _warriors(st) == [W_DEAD], "montage : le Guerrier mort n'est pas dans l'etat"
    assert PhasalSubjugatorSummonAbility(OWNER_ID).matches(st, _ev_arrived()) is True


def test_un_guerrier_ENNEMI_vivant_ne_ferme_PAS_le_gate():
    """`Friends(of = Owner, ...)` : le referent d'equipe est le PORTEUR."""
    st = _state(warrior_enemy=True)
    assert _warriors(st) == [W_ENEMY]
    assert PhasalSubjugatorSummonAbility(OWNER_ID).matches(st, _ev_arrived()) is True


def test_un_ACTEUR_qui_n_est_pas_le_porteur_ne_declenche_pas():
    """`get_OwnerIsActor` = `AreEqual(Owner@+0x30, Actor@+0x40)`."""
    st = _state()
    assert PhasalSubjugatorSummonAbility(OWNER_ID).matches(st, _ev_arrived(ALLY_ID)) is False


# --------------------------------------------------------------------------------------------
# Etage 2 -- classe 2 : le gate est dans le BEHAVIOUR, pas dans le TRIGGER
# --------------------------------------------------------------------------------------------

def test_classe2_le_trigger_ne_porte_PAS_le_gate_guerrier():
    """Le `CreateTrigger` partage (`On(0x29, alive) & get_OwnerIsActor`) n'a AUCUN conjoint sur les
    Guerriers -- c'est ce qui fait que le re-declenchement de 1556 a lieu meme quand un Guerrier vit.
    Le confondre avec la forme de la classe 1 supprimerait la moitie du contenu de la relique."""
    ab = PhasalSubjugatorTriggerPassiveAbility(OWNER_ID)
    assert ab.matches(_state(warrior_alive=True), _ev_finished()) is True
    assert ab.matches(_state(), _ev_finished()) is True
    assert ab.matches(_state(), _ev_finished(ALLY_ID)) is False


def test_classe2_avec_guerrier_vivant_zero_spawn_mais_retrigger():
    st = _state(warrior_alive=True)
    r = PhasalSubjugatorTriggerPassiveAbility(OWNER_ID).execute_behaviour(st, _ev_finished())
    assert r is not None
    assert r["spawned"] == [], "le `If(NOT HasFriendlyWarrior(), Spawn)` a spawne malgre le Guerrier"
    assert r["retrigger_targets"] == [OWNER_ID], (
        "`IfAlive(Owner, TriggerAbility(Owner, 1556))` n'a pas vise le porteur")


def test_classe2_sans_guerrier_spawn_ET_retrigger():
    st = _state()
    r = PhasalSubjugatorTriggerPassiveAbility(OWNER_ID).execute_behaviour(st, _ev_finished())
    assert r is not None and len(r["spawned"]) == 1
    assert r["retrigger_targets"] == [OWNER_ID]


def test_un_porteur_MORT_ferme_le_IfAlive_mais_pas_le_spawn():
    """`If(cond, spawn) op_BitwiseAnd IfAlive(Owner, trigger)` : les DEUX gardes sont INDEPENDANTES.
    Le `IfAlive` est le SEUL a lire la vie du porteur -- l'ecrire au-dessus des deux termes
    supprimerait un spawn que le natif fait."""
    st = _state()
    from engine.runner.components import UnitComponent
    st.get_entity(OWNER_ID).get_component(UnitComponent).alive = False
    entities = entities_from_state(st, OWNER_ID, OWNER_ID, actor_id=OWNER_ID)
    ectx = ExecutionContext(state=st, rng=st.rng)
    phasal_trigger_passive_tree((LVL_TERTIAIRE, 100)).execute(entities, ectx)
    noms = [n for (n, _) in ectx.emitted]
    assert "SpawnUnit" in noms, "le spawn a ete ferme par la vie du porteur"
    assert "TriggerAbility" not in noms, "`IfAlive(Owner, ...)` n'a pas ferme sur un porteur mort"


# --------------------------------------------------------------------------------------------
# Etage 3 -- le re-declenchement de 1556 est DISPATCHE, et c'est la branche `Custom`
# --------------------------------------------------------------------------------------------

def test_le_retrigger_de_1556_est_DISPATCHE():
    """Sans l'entree `TRIGGERED_ABILITY_BEHAVIOURS[1556]`, la feuille rendrait `dispatched: False` :
    un gap VISIBLE, mais un gap -- la moitie du contenu de la relique ne s'executerait pas."""
    assert MY_WILL_BE_DONE_OVERLORD in TRIGGERED_ABILITY_BEHAVIOURS
    st = _state(warrior_alive=True)
    r = PhasalSubjugatorTriggerPassiveAbility(OWNER_ID).execute_behaviour(st, _ev_finished())
    assert r["retrigger_dispatched"] is True
    res = [x for x in (r["retrigger_results"] or []) if x is not None]
    assert res and res[0]["passive"] == "MyWillBeDoneOverlord"
    assert res[0]["trigger_type"] == int(EventTriggerType.Custom), (
        "`TriggerTriggeredAbilityOperation$$TriggerAbility` appelle `ExecuteBy(..., 0x20 = Custom)` "
        "-- le `0x20` est EN DUR dans l'Operation")
    assert int(EventTriggerType.Custom) != int(EventTriggerType.TurnStart_EffectActivation), (
        "temoin : si `Custom` valait 0x12, la branche prise serait la PURGE, pas l'attaque")


def test_le_retrigger_fait_AGIR_un_allie():
    """Le bout de chaine COMPLET : le `Custom` de 1556 doit produire une action observable
    (l'override d'Attaque + l'attaque libre de l'allie), sinon le dispatch serait decoratif."""
    st = _state(warrior_alive=True)
    ectx = ExecutionContext(state=st, rng=st.rng)
    entities = entities_from_state(st, OWNER_ID, OWNER_ID, actor_id=OWNER_ID)
    TRIGGERED_ABILITY_BEHAVIOURS[MY_WILL_BE_DONE_OVERLORD](st, OWNER_ID, entities, ectx)
    noms = [n for (n, _) in ectx.emitted]
    assert "PerformAIAttack" in noms or "AddDynamicStatModifierEffect" in noms, (
        "la branche `Custom` de 1556 n'a produit NI attaque libre NI auto-buff : "
        "emis = %r" % (noms,))


# --------------------------------------------------------------------------------------------
# Etage 4 -- le niveau lu est le TERTIAIRE (contre-epreuve par MUTATION du ctx)
# --------------------------------------------------------------------------------------------

def _hp_du_guerrier_spawne(state):
    """⚠ PASSE PAR `execute_behaviour`, PAS par l'arbre nu : c'est LA que la resolution du couple
    `(niveau, multiplicateur)` a lieu (`triggered_ability_state(state, owner, ABILITY_ID)`). Un
    montage qui appellerait `phasal_spawn_tree` en lui donnant le couple a la main testerait son
    propre echafaudage -- mesure : la mutation << lire le niveau PASSIF >> restait VERTE."""
    r = PhasalSubjugatorSummonAbility(OWNER_ID).execute_behaviour(state, _ev_arrived())
    assert r is not None and len(r["spawned"]) == 1, "montage : aucun Guerrier pose"
    return int(state.get_entity(r["spawned"][0]).get_component(HealthComponent).hp_max)


def test_le_niveau_du_summon_vient_de_l_ability_state_TERTIAIRE():
    """`WithStatsFromConfig(config, abilityState, 0, 0)` : l'`AbilityState` d'une RELIQUE est le
    TERTIAIRE. Lire celui des passifs (50 dans tout runner normalise) clamperait `summonHp` au
    dernier palier -- l'ecart #174, silencieux."""
    import gameconfig as GC
    paliers = ((GC.ability(ABILITY_ID) or {}).get("variables") or {}).get("summonHp")
    assert paliers and paliers[LVL_TERTIAIRE - 1] != paliers[LVL_PASSIF - 1], (
        "TEMOIN DEGENERE : les deux paliers de summonHp sont egaux, la mutation ne separerait rien")
    bas = _hp_du_guerrier_spawne(_state(level=LVL_TERTIAIRE))
    haut = _hp_du_guerrier_spawne(_state(level=LVL_PASSIF))
    assert bas != haut, ("le niveau du summon ne suit pas l'`AbilityState` tertiaire "
                         "(bas=%d haut=%d)" % (bas, haut))
    assert bas == paliers[LVL_TERTIAIRE - 1], (
        "PV du Guerrier = %d, palier tertiaire attendu = %d" % (bas, paliers[LVL_TERTIAIRE - 1]))


# --------------------------------------------------------------------------------------------
# Etage 5 -- le sous-arbre PARTAGE est bien PARTAGE (une instance FRAICHE par site)
# --------------------------------------------------------------------------------------------

def test_le_gate_guerrier_est_une_instance_FRAICHE_par_appel():
    """Le natif rebatit le sous-arbre a chaque site, sans aucun `Cache` : deux appels ne doivent pas
    rendre le MEME objet, sinon un memo (present ou futur) figerait le verdict entre les deux
    classes -- qui, elles, sont evaluees a des instants differents du tour."""
    a, b = phasal_has_friendly_warrior(), phasal_has_friendly_warrior()
    assert a is not b
