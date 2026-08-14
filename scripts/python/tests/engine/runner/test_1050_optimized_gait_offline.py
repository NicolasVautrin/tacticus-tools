"""#1050 -- les crans OFFLINE de la tranche ZONE-GRISE `OptimizedGait` / `AncientFury`.

Ce fichier garde ce qui se PERIME EN SILENCE : les littéraux lus au décompilé (event ids, id
d'ability, `EffectType` du gate `useSpecial`), la forme des DEUX arbres, le quirk `set_moved`, et
la FRONTIERE entre les deux familles de cleave d'attaque normale -- celle-là même dont la confusion
produirait un port faux SANS erreur.

Aucun runner : tout est structurel ou joué sur un `State` synthétique.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))))

from engine.dsl.event_trigger_type import EventTriggerType            # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType     # noqa: E402
from engine.entities.effect_type import EffectType                    # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.runner.abilities.behaviours.movement import MoveUnit      # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS  # noqa: E402
from engine.runner.operations.triggers.loki import optimized_gait as OG  # noqa: E402
from engine.services.custom_normal_attack import CUSTOM_NORMAL_ATTACK_BY_PASSIVE  # noqa: E402


# ================================================================== ETAGE 1 -- le CABLAGE
def test_etage1_les_deux_classes_sont_au_registre_sous_la_meme_cle():
    """`ABILITY_TRIGGERS["OptimizedGait"]` porte les DEUX `BaseTriggeredAbility`.

    C'est LE cran de la tranche : avant #1050 la clé n'existait pas, et le seul endroit du port qui
    nommait `OptimizedGait` était `CUSTOM_NORMAL_ATTACK_BY_PASSIVE` -- une table de DISPATCH
    d'attaque normale, pas un câblage de mécanique (c'est cette confusion qui a fait classer le
    passif « zone grise » au lieu de « absent »)."""
    entries = ABILITY_TRIGGERS.get(OG.OPTIMIZED_GAIT)
    assert entries, "OptimizedGait doit etre inscrit dans ABILITY_TRIGGERS"
    assert set(entries) == {OG.OptimizedGaitTriggerAttackAbility, OG.OptimizedGaitMoveAbility}, (
        f"les DEUX classes triggered doivent y etre, vu {entries}")


def test_etage1b_les_deux_classes_partagent_le_meme_triggered_ability_id():
    """`TriggeredAbilityType` n'a qu'UN `OptimizedGait` (0x4b5 = 1205) -- il n'existe aucun
    `OptimizedGait_TriggerAttack` dans l'enum. Les deux classes natives sont donc montées sous le
    MEME id (même forme que les trois classes de `StormboyzStrike` sous 1141), et c'est ce partage
    qui arme la branche `TriggeringAbilityIs(0x4b5)` du déplacement : l'attaque réactive s'exécute
    avec `CurrentAbility = 1205`, donc le kill qu'elle cause porte `killTrigger = 1205`."""
    assert int(TriggeredAbilityType.OptimizedGait) == 0x4b5
    assert not [n for n in TriggeredAbilityType.__members__
                if n.startswith("OptimizedGait") and n != "OptimizedGait"], (
        "l'enum ne doit porter qu'UN OptimizedGait -- si un OptimizedGait_TriggerAttack apparait, "
        "la lecture << les deux classes partagent l'id >> est a re-mesurer")
    assert OG.OptimizedGaitTriggerAttackAbility.TRIGGERED_ABILITY_ID == 0x4b5
    assert OG.OptimizedGaitMoveAbility.TRIGGERED_ABILITY_ID == 0x4b5


def test_etage1c_les_deux_vecteurs_ecoutes():
    """`On(9 = Attack)` pour l'attaque réactive, `On(0 = UnitDeath)` pour le pas.

    ⚠ `UnitDeath = 0`, PAS `PreUnitDeath_2 = 2` : `DSLTriggers$$OnDeath(a, b)` = `OnDeathEvent(0,
    a, b)` -- l'écart avec `HeadClaimer`, qui appelle `OnPreDeath2`. Se tromper de vecteur donne un
    trigger qui ne fire jamais, sans erreur."""
    assert OG.OptimizedGaitTriggerAttackAbility.event_id == int(EventTriggerType.Attack) == 9
    assert OG.OptimizedGaitMoveAbility.event_id == int(EventTriggerType.UnitDeath) == 0


# ================================================================== ETAGE 2 -- les LITTERAUX lus
def test_etage2_le_gate_use_special_est_cord_claw_addition_hits():
    """`0x4e2` = 1250 = `EffectType.CordClaw_AdditionHits` -- le MEME littéral que le gate
    `useSpecial` de l'attaque normale substituée (`services/custom_normal_attack.py`), lu dans
    `EntityExtensions$$HasEffect(entities+0x18, state, 0x4e2, null)`.

    L'ordinal seul ne tranche rien : `TriggeredAbilityType` 1250 et `ActiveAbilityType` 1250
    nomment autre chose. C'est le NOM qui est gardé."""
    assert OG.CORD_CLAW_ADDITION_HITS == 0x4e2 == int(EffectType.CordClaw_AdditionHits)


def test_etage2b_la_config_lue_est_celle_du_passif():
    """Le behaviour lit `GetVariableForLevel(0xc/0xd)` = `minDmg`/`maxDmg`,
    `GetNumberConstant(0x2f)` = `nrOfHits` et `GetDamageProfile()` = `damageProfile`, TOUS sur la
    config de `OptimizedGait` (le passif). Le gameconfig doit donc porter ces trois clés -- sans
    elles le port frapperait à 0 sans erreur, et le texte i2 (« nrOfHits x minDmg-maxDmg Energy »)
    serait démenti."""
    import gameconfig as GC
    cfg = GC.ability(OG.OPTIMIZED_GAIT) or {}
    consts = cfg.get("constants") or {}
    assert "nrOfHits" in consts and "damageProfile" in consts, consts
    assert set(("minDmg", "maxDmg")) <= set((cfg.get("variables") or {})), cfg.get("variables")
    assert OG._damage_profile() == consts["damageProfile"]


# ================================================================== ETAGE 3 -- le QUIRK set_moved
def test_etage3_le_pas_ne_consomme_pas_le_deplacement():
    """`options{+0x10 = <DSLTriggers+0x48> = TOUJOURS-FAUX}` -> `MoveUnitOptions+0x11 = 1` ->
    `MoveUnitOperation$$Execute` NE POSE PAS `UnitFlag.Moved`.

    C'est le seul call-site du port dans ce régime ; tout autre `MoveUnit` garde le défaut natif
    (options nulles -> `+0x11 = 0` -> flag posé)."""
    tree = OG.optimized_gait_move_tree()
    assert isinstance(tree, MoveUnit)
    assert tree.set_moved is False, (
        "le pas d'Exitor-Rho ne pose PAS `Moved` -- cf. la chaine options+0x10 -> +0x11 -> SetMovedFlag")
    # le DEFAUT reste celui des 29 autres call-sites : un no-op strict.
    assert MoveUnit(tree.subject_sel, tree.dest_tile_sel).set_moved is True


def test_etage3b_le_quirk_mord_reellement_dans_l_operation():
    """Contre-épreuve du DESSOUS : `MoveUnitOperation(set_moved=False)` ne doit pas poser le flag,
    et `set_moved=True` doit le poser. Sans ce cran, `MoveUnit(set_moved=False)` pourrait très bien
    ne rien changer (paramètre accepté mais non threadé) -- exactement le genre de vert à vide que
    la tranche doit interdire."""
    from engine.runner.operations.movement import MoveUnitOperation
    op_off = MoveUnitOperation(1, (0, 0), set_moved=False)
    op_on = MoveUnitOperation(1, (0, 0), set_moved=True)
    assert op_off.set_moved is False and op_on.set_moved is True
    # le paramètre est bien celui que la feuille thread (et non un homonyme).
    import inspect
    src = inspect.getsource(MoveUnit.execute)
    assert "set_moved=self.set_moved" in src, (
        "la feuille DSL doit THREADER son set_moved a l'Operation, sinon le quirk est mort-ne")


# ================================================================== ETAGE 4 -- la FRONTIERE cleave
def test_etage4_ancient_fury_n_est_pas_de_la_famille_get_additional_targets():
    """`AncientFury` NE DOIT PAS entrer dans `NORMAL_ATTACK_CLEAVES` -- et ce n'est pas un détail de
    rangement : les deux familles de « cleave d'attaque normale » ont des FORMES natives
    différentes, donc des observables différents.

    * `NORMAL_ATTACK_CLEAVES` (#478) = les quatre `<X>_NormalAttackAbility$$
      GetAdditionalTargetsAttackBehavior` (`Fealty`, `TalonOfHorus`, `RighteousRepugnance`,
      `Boltstorm`) : un `DSLBehaviors$$Attack` PAR cible additionnelle, aux BORNES de la config du
      passif (`RandomAmount(var 0xc, var 0xd)`), APRES l'attaque primaire, ordre du SELECTEUR.
    * `AncientFury` = `IdunBattleLogic.Entities.Abilities.Active.Loki.AncientFury_NormalAttackAbility$$
      GetTarget` : il n'ajoute AUCUN behaviour -- il ELARGIT le sélecteur de cibles que
      `ALoki_NormalAttackAbility$$ExecuteNormalAttack` passe à `GetAttackDamageBehaviour`, donc à
      l'`Attack(caster, <sélecteur>, ...)` unique. `AttackBehaviour$$Execute` boucle alors sur les
      cibles TRIEES (`OrderBy(b__5_0)` dès qu'il y en a plus d'une) et rejoue le behaviour ENTIER
      par cible : coups d'ARME complets, `StartAttack`/`FinishAttack` par cible.

    Le ranger dans `NORMAL_ATTACK_CLEAVES` lui donnerait les bornes de config au lieu des coups
    d'arme, et l'ordre « primaire d'abord » au lieu du tri -- deux écarts SILENCIEUX. Résidu #1050.
    """
    from engine.runner.abilities.loki.additional_targets import NORMAL_ATTACK_CLEAVES
    assert set(NORMAL_ATTACK_CLEAVES) == {"Fealty", "TalonOfHorus", "RighteousRepugnance",
                                          "Boltstorm"}, (
        "la liste est CLOSE (les 4 porteurs de `$$GetAdditionalTargetsAttackBehavior` du build) -- "
        "y ajouter AncientFury serait un port FAUX, cf. la docstring")
    assert "AncientFury" not in NORMAL_ATTACK_CLEAVES


def test_etage4b_ancient_fury_reste_une_substitution_d_attaque_normale():
    """Ce que le port EXECUTE réellement pour `AncientFury`, mesuré et non supposé : la SEULE chose
    est la cascade `UnitFactory$$AddNormalAttackAbility` (1256 -> 1162), c'est-à-dire QUELLE attaque
    normale l'entité porte. Son sélecteur élargi (`$$GetTarget`) n'est pas exécuté.

    Ce test garde la moitié VRAIE de l'énoncé (la substitution est bien portée, avec le bon
    appariement d'ordinaux) pour qu'un futur port du sélecteur ne casse pas ce qui existe."""
    assert CUSTOM_NORMAL_ATTACK_BY_PASSIVE["AncientFury"] == "AncientFury_NormalAttack"
    assert int(TriggeredAbilityType.AncientFury) == 1256
    assert int(ActiveAbilityType.AncientFury_NormalAttack) == 1162
    # même appariement pour OptimizedGait : la table de dispatch reste intacte après cette tranche.
    assert CUSTOM_NORMAL_ATTACK_BY_PASSIVE["OptimizedGait"] == "OptimizedGait_NormalAttack"
    assert int(ActiveAbilityType.OptimizedGait_NormalAttack) == 1123


# ================================================================== ETAGE 5 -- les GATES, joués
_COLS, _ROWS = 7, 7


def _board():
    """Un board PLAT 7x7 en `evenq` -- l'adjacence hex du runner, celle que lisent `IsAdjacent`
    (via `services.battle_query.are_tiles_adjacent`) et `IsWalkable` (via `board.walkable`)."""
    from engine.entities.pathfinding.board import Board
    import hexgeo
    tiles = []
    for col in range(_COLS):
        for row in range(_ROWS):
            nb = [c * _ROWS + r + 1 for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < _COLS and 0 <= r < _ROWS]
            tiles.append({"id": col * _ROWS + row + 1, "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tiles, adjacency="evenq")


def _mini_state(positions, teams, traits=None, alive=None):
    """Un `State` synthétique minimal : N unités posées sur un board plat, avec équipe et traits.

    Pas de runner : les nœuds DSL de ce module ne lisent que la position, l'équipe, les traits et
    le board. `traits_measured = True` -- les traits sont FOURNIS, jamais re-dérivés d'un
    gameconfig (le repli #226 masquerait le bras qui les retire)."""
    from engine.runner.state import State
    from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                          StatsComponent, UnitComponent)
    from engine.entities.unit_context import UnitContext
    st = State()
    st.board = _board()
    for uid, pos in positions.items():
        vivant = (alive or {}).get(uid, True)
        e = st.add_entity(uid)
        e.add_component(UnitComponent(f"u{uid}", vivant))
        e.add_component(OwnerComponent(teams[uid], teams[uid]))
        e.add_component(HealthComponent(100 if vivant else 0, 100))
        ctx = UnitContext(entity_id=int(uid), visual_id=f"u{uid}",
                          traits=list((traits or {}).get(uid, [])),
                          active_ability_level=10, passive_ability_level=10,
                          ability_variables_multiplier=100)
        ctx.traits_measured = True
        e.add_component(StatsComponent(ctx=ctx))
        e.add_component(PositionComponent(int(pos[0]), int(pos[1])))
    return st


@pytest.mark.parametrize("acteur_mechanical,acteur_allie,cible_adjacente,attendu", [
    (True, True, True, True),        # le régime nominal
    (False, True, True, False),      # `IsMechanical(Actor)` tombe
    (True, False, True, False),      # `AreFriends(Owner, Actor)` tombe
    (True, True, False, False),      # `IsAdjacent(Owner, Target)` tombe
])
def test_etage5_gates_de_l_attaque_reactive(acteur_mechanical, acteur_allie, cible_adjacente,
                                            attendu):
    """Les quatre conjoints d'`OptimizedGait_TriggerAttackAbility$$CreateTrigger`, un par bras.

    Sans ces bras, `matches` pourrait rendre `True` inconditionnellement et le test resterait vert :
    chaque bras EST le discriminant d'un conjoint."""
    from engine.runner.operations.triggers.base import TriggerEvent
    OWNER, ACTOR, TARGET = 1, 2, 3
    pos = {OWNER: (2, 2), ACTOR: (5, 5), TARGET: ((2, 3) if cible_adjacente else (6, 6))}
    teams = {OWNER: 1, ACTOR: (1 if acteur_allie else 2), TARGET: 2}
    traits = {ACTOR: (["Mechanical"] if acteur_mechanical else [])}
    st = _mini_state(pos, teams, traits)
    ev = TriggerEvent(int(EventTriggerType.Attack), ACTOR, TARGET, ranged=False, profile=None)
    got = OG.OptimizedGaitTriggerAttackAbility(OWNER).matches(st, ev)
    assert bool(got) is attendu, (
        f"mechanical={acteur_mechanical} allie={acteur_allie} adjacent={cible_adjacente} "
        f"-> attendu {attendu}, vu {got}")


def test_etage5b_le_porteur_ne_se_declenche_pas_sur_sa_propre_attaque():
    """`op_LogicalNot(get_OwnerIsCaster)` : quand c'est Exitor-Rho lui-même qui attaque, le trigger
    NE part PAS. Sans ce conjoint, chaque attaque normale du porteur s'auto-doublerait."""
    from engine.runner.operations.triggers.base import TriggerEvent
    OWNER, TARGET = 1, 3
    st = _mini_state({OWNER: (2, 2), TARGET: (2, 3)}, {OWNER: 1, TARGET: 2},
                     {OWNER: ["Mechanical"]})
    ev = TriggerEvent(int(EventTriggerType.Attack), OWNER, TARGET, ranged=False, profile=None)
    assert OG.OptimizedGaitTriggerAttackAbility(OWNER).matches(st, ev) is False


@pytest.mark.parametrize("owner_is_actor,kill_trigger,attendu", [
    (False, None, True),                                   # branche A : un allié Mechanical a tué
    (True, int(TriggeredAbilityType.OptimizedGait), True),  # branche B : l'attaque réactive a tué
    (True, None, False),                                   # branche B sans killTrigger -> rien
    (True, int(TriggeredAbilityType.Skullsmasher), False),  # killTrigger d'une AUTRE ability
])
def test_etage6_les_deux_branches_du_pas(owner_is_actor, kill_trigger, attendu):
    """`C & (A | B)` -- les deux branches du `CreateTrigger` du déplacement.

    La branche B lit le canal `AbilityEntities+0x98` (`state.trigger_ability_type`, le `killTrigger`
    que `_verify_deaths` repose le temps du drain), JAMAIS `+0x60` que `KillUnitOperation` publie
    VIDE sur tout le vecteur mort (#301). Le 4e bras (`killTrigger` d'une autre ability) est le
    discriminant qui interdit de rabattre le gate sur « il y a un killTrigger »."""
    from engine.runner.operations.triggers.base import TriggerEvent
    OWNER, ACTOR, VICTIM = 1, 2, 3
    actor = OWNER if owner_is_actor else ACTOR
    st = _mini_state({OWNER: (2, 2), ACTOR: (5, 5), VICTIM: (2, 3)},
                     {OWNER: 1, ACTOR: 1, VICTIM: 2},
                     {ACTOR: ["Mechanical"], OWNER: ["Mechanical"]},
                     alive={VICTIM: False})
    st.trigger_ability_type = kill_trigger
    ev = TriggerEvent(int(EventTriggerType.UnitDeath), actor, VICTIM, ranged=False, profile=None,
                      killer_id=actor, dying_id=VICTIM)
    got = OG.OptimizedGaitMoveAbility(OWNER).matches(st, ev)
    assert bool(got) is attendu, (
        f"owner_is_actor={owner_is_actor} killTrigger={kill_trigger} -> attendu {attendu}, vu {got}")


def test_etage6b_le_pas_refuse_une_victime_steppable():
    """`steppableGate` d'`OnDeathEvent(0, a, b = false)` = `NOT HasTrait(Target, 0x1b)`. Le pas a
    lieu même en overkill (`a = true` désarme `TargetIsOverkilled`), mais jamais sur un
    `Steppable`."""
    from engine.runner.operations.triggers.base import TriggerEvent
    OWNER, ACTOR, VICTIM = 1, 2, 3
    st = _mini_state({OWNER: (2, 2), ACTOR: (5, 5), VICTIM: (2, 3)},
                     {OWNER: 1, ACTOR: 1, VICTIM: 2},
                     {ACTOR: ["Mechanical"], VICTIM: ["Steppable"]}, alive={VICTIM: False})
    ev = TriggerEvent(int(EventTriggerType.UnitDeath), ACTOR, VICTIM, ranged=False, profile=None,
                      killer_id=ACTOR, dying_id=VICTIM)
    assert OG.OptimizedGaitMoveAbility(OWNER).matches(st, ev) is False
