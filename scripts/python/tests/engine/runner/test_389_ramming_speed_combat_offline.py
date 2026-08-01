"""#389 (residu `#383-r1`) -- la face COMBAT de `RammingSpeed` (1059), 100 % OFFLINE.

Ce que ces cliquets verrouillent, et POURQUOI :

  * **le noeud `<DSLTriggers+0x20>` est `OwnerIsAlive`, SANS operande.** C'est le verrou qui avait
    fait refuser le port (#383 sec.6) : un noeud non nomme. La garde structurelle interdit de le
    re-remplacer par un conjoint invente -- `SkyStrikeAbility$$ExecuteBehaviour` porte le MEME noeud
    et le port y ecrivait `IsAlive(caster) & IsAlive(target)`, ce qui est un mirror FAUX.
  * **la gate FERME reellement** quand l'owner est mort : c'est la seule face du noeud que le live
    n'atteint pas (il faudrait un tir REACTIF qui tue le charger pendant son deplacement), donc
    c'est ICI qu'elle se mesure.
  * **le contrecoup vise l'OWNER** (`Owner@0x30` en 2e argument comme en 3e) et lit `nrOfHits_2`,
    pas `nrOfHits`.
  * **les deux donnees de registre** (`TARGETING_OPTIONS` = litteral `0x4002` + `RANGE_FROM_CONFIG`
    + `forceMeleeTarget = RangedBool.False`, `ABILITY_ATTACK_TYPE` = 0 `DirectTargetAttack`) sont
    celles LUES au `RammingSpeedAbility$$.ctor`.
  * **`GetDynamicInvalidTargetReason`** rend bien `0` quand le caster est DEJA au contact (aucun
    move, donc aucune contrainte de tuile) et `0x8000000 = TargetIsInRange` quand aucune tuile de
    charge n'est atteignable.

Board 7x7 PLAT et deterministe (meme construction que `test_383_ramming_speed_explosion_offline`).
ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                              # noqa: E402
from engine.dsl.effects import ExecutionContext                            # noqa: E402
from engine.entities.triggers import OwnerIsAlive                          # noqa: E402
from engine.runner.abilities import ABILITY_CLASSES                        # noqa: E402
from engine.runner.abilities.attack_type import (AbilityAttackType,        # noqa: E402
                                                 ABILITY_ATTACK_TYPE)
from engine.runner.abilities.behaviours import entities_from_state         # noqa: E402
from engine.runner.abilities.orks import (RammingSpeedAbility,             # noqa: E402
                                          ramming_speed_tree)
from engine.runner.abilities.targeting import (RANGE_FROM_CONFIG,          # noqa: E402
                                               RANGED_BOOL_FALSE)
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.components import HealthComponent, UnitComponent        # noqa: E402

ABILITY = 1059
COLS, ROWS = 7, 7
CASTER_ID, TARGET_ID, ALLY_ID = 10, 20, 40
HP = 100000


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


def _state(caster=(0, 3), target=(3, 3), ally=(6, 6), block_ring: bool = False):
    """`State` runner minimal. `block_ring` SATURE l'anneau de la cible avec des blocs, ce qui rend
    `CanAddUnit(AdjacentTiles(Target))` VIDE -- le seul regime ou `GetTileToMoveTo` ne designe rien."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    tiles = _tiles()
    if block_ring:
        ring = {(c, r) for (c, r) in hexgeo.neighbors(target[0], target[1])}
        for t in tiles:
            if (t["col"], t["row"]) in ring:
                t["walkable"] = False
    board = Board(tiles, adjacency="evenq")
    decision = {"currentPlayer": 1, "units": [
        {"id": CASTER_ID, "visualId": "orksKillaKan", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": caster[0], "row": caster[1]}, "effects": []},
        {"id": ALLY_ID, "visualId": "astraBullgryn", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": ally[0], "row": ally[1]}, "effects": []},
        {"id": TARGET_ID, "visualId": "necroWarden", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": target[0], "row": target[1]}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": HP, "hpMax": HP} for u in decision["units"]]}
    return load_state(decision, observe, board=board)


def _run_tree(state, dest=(2, 3)):
    """Execute l'arbre COMBAT et rend la liste des operations emises (nom, payload)."""
    ectx = ExecutionContext(state=state, rng=state.rng)
    ramming_speed_tree(dest, "Physical").execute(
        entities_from_state(state, CASTER_ID, TARGET_ID), ectx)
    return list(ectx.emitted)


def _kill(state, uid):
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent)
    hc.hp = 0
    uc = e.get_component(UnitComponent)
    if uc is not None:
        uc.alive = False


# --------------------------------------------------------------------- le noeud `<DSLTriggers+0x20>`

def test_the_gate_node_is_OwnerIsAlive_and_carries_no_operand():
    """`If(<DSLTriggers+0x20>, atk1 + atk2)` : le noeud natif est le SINGLETON PARTAGE
    `OwnerIsAliveAbilityTrigger`, alloue SANS selecteur (`new C(dsl.state@+0x10)`). Un port qui y
    conjoindrait un `IsAlive(Target())` -- l'ecriture qu'avait `sky_strike_tree` -- serait un mirror
    FAUX : ce cliquet interdit la regression."""
    tree = ramming_speed_tree((2, 3), "Physical")
    gate = tree.right                                     # (ifMove + addEff) + If(gate, atks)
    assert isinstance(gate.cond, OwnerIsAlive)
    # SANS operande : le noeud n'a aucun attribut de sous-noeud (contraste `IsAlive(unit)`).
    assert not [a for a in vars(gate.cond)] if hasattr(gate.cond, "__dict__") else True


def test_the_same_node_gates_sky_strike():
    """`SkyStrikeAbility$$ExecuteBehaviour` lit le MEME `<dsl+0x88>+0x20` (xrefs du motif). Les deux
    ports doivent donc porter la MEME classe de noeud -- pas deux lectures divergentes."""
    from engine.runner.abilities.sisterhood import sky_strike_tree
    tree = sky_strike_tree((1, 1), 5, "Power", 3)
    assert isinstance(tree.right.cond, OwnerIsAlive)


def test_a_dead_owner_closes_the_gate():
    """FACE QUE LE LIVE N'ATTEINT PAS : le caster ne meurt pendant son deplacement que sous un tir
    REACTIF. Gate FERMEE => AUCUNE des deux attaques, mais le `MoveUnit` et l'`AddEffect` (qui sont
    HORS du `If`, en `op_Addition` a gauche) restent."""
    st = _state()
    _kill(st, CASTER_ID)
    names = [n for n, _ in _run_tree(st)]
    assert "AttackWithAttackDamage" not in names
    assert "AddEffect" in names


def test_an_alive_owner_opens_the_gate_on_both_attacks():
    st = _state()
    emitted = _run_tree(st)
    atks = [p for n, p in emitted if n == "AttackWithAttackDamage"]
    assert len(atks) == 2
    # ORDRE natif : la CIBLE d'abord (atk1), le CASTER ensuite (atk2 = le contrecoup).
    assert atks[0]["target"] == TARGET_ID
    assert atks[1]["target"] == CASTER_ID and atks[1]["caster"] == CASTER_ID


# ------------------------------------------------------------------------------- structure de l'arbre

def test_the_recoil_reads_nrOfHits_2_and_the_main_attack_nrOfHits():
    """`hits = GetNumberConstant(0x2f = nrOfHits)` pour la cible, `GetNumberConstant(0x32 =
    nrOfHits_2)` pour le contrecoup -- deux constantes DISTINCTES du meme config."""
    tree = ramming_speed_tree((2, 3), "Physical")
    atk_target, atk_self = tree.right.then.left, tree.right.then.right
    assert atk_target.hits_key == "nrOfHits"
    assert atk_self.hits_key == "nrOfHits_2"
    # MEME noeud `amount` natif (`local_228`) -> MEMES bornes de config des deux cotes.
    assert (atk_target.min_key, atk_target.max_key) == (atk_self.min_key, atk_self.max_key)
    # Famille ATTACK (surcharge `AttackWithAttackDamage` a `hits` INT -> AttackDamageBehaviour).
    assert atk_target.native_factory == "attack" and atk_self.native_factory == "attack"


def test_the_effect_1098_is_posed_on_the_owner_with_the_default_duration():
    """`AddEffect(0x44a, AbilityStateReference, source = Owner@0x30, targets = Owner@0x30,
    <options ZERO>)` : la surcharge 6-args a struct d'options ZERO ne porte AUCUN override de duree
    -> duree DEFAUT (`duration_rounds=None`)."""
    st = _state()
    eff = [p for n, p in _run_tree(st) if n == "AddEffect"]
    assert len(eff) == 1
    assert eff[0]["effect_type"] == 1098
    assert eff[0]["target"] == CASTER_ID and eff[0]["source"] == CASTER_ID
    tree = ramming_speed_tree((2, 3), "Physical")
    assert tree.left.right.duration_rounds is None and tree.left.right.duration_turns is None


def test_an_adjacent_caster_skips_the_move():
    """`If(NOT IsAdjacent(Caster, Target), MoveUnit(...))` : deja au contact -> aucun `MoveUnit`."""
    st = _state(caster=(3, 2), target=(3, 3))
    names = [n for n, _ in _run_tree(st, dest=(2, 3))]
    assert "MoveUnit" not in names
    st2 = _state(caster=(0, 3), target=(3, 3))
    assert "MoveUnit" in [n for n, _ in _run_tree(st2, dest=(2, 3))]


# ------------------------------------------------------------------------------------- le registre

def test_the_registry_carries_the_ctor_literals():
    """`RammingSpeedAbility$$.ctor` (forme FLAGS DIRECTS) :
    `TargetingOptions..ctor(&opts, 0, &<TargetingRange statics>+0x18, 1, 0x4002, 0, 0)` puis
    `AActiveAbility..ctor(this, &opts, 0)`."""
    assert ABILITY_CLASSES.get(ABILITY) is RammingSpeedAbility
    opts = RammingSpeedAbility.TARGETING_OPTIONS
    assert int(opts.rules) == 0x4002 == int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy)
    assert opts.range == RANGE_FROM_CONFIG
    assert opts.force_melee_target == RANGED_BOOL_FALSE
    assert opts.self_cast is False
    assert ABILITY_ATTACK_TYPE.get(ABILITY) == AbilityAttackType.DirectTargetAttack


# ----------------------------------------------------------- `GetDynamicInvalidTargetReason`

def test_dynamic_reason_accepts_a_caster_already_in_contact():
    """`if (!movedOrOffTile || isAdjacent) ... ; if (isAdjacent) return 0` -- au contact l'ability est
    TOUJOURS valide, sans aucune contrainte de tuile."""
    st = _state(caster=(3, 2), target=(3, 3))
    assert RammingSpeedAbility().get_dynamic_invalid_target_reason(st, CASTER_ID, TARGET_ID) == 0


def test_dynamic_reason_refuses_a_target_whose_ring_is_unwalkable():
    """`GetFreeAdjacentTiles(target).Count < 1 -> 0x20 = TargetHasFreeAdjacentTile`."""
    st = _state(caster=(0, 3), target=(3, 3), block_ring=True)
    assert (RammingSpeedAbility().get_dynamic_invalid_target_reason(st, CASTER_ID, TARGET_ID)
            == int(TR.TargetHasFreeAdjacentTile))


def test_dynamic_reason_refuses_a_target_out_of_charge_range():
    """Ring LIBRE mais aucune tuile de charge ATTEIGNABLE (`range` = 5) -> `0x8000000 =
    TargetIsInRange`, le litteral que rend le natif quand `SelectTile` ne donne rien.

    La geometrie est CHOISIE par mesure (le coin oppose du 7x7), et la PRECONDITION est verifiee :
    si `GetTileToMoveTo` designait une tuile, le cliquet serait vacant."""
    from engine.runner.abilities.orks import ramming_speed_tile_to_move_to
    st = _state(caster=(0, 0), target=(6, 6))
    assert ramming_speed_tile_to_move_to(st, CASTER_ID, TARGET_ID) is None
    assert (RammingSpeedAbility().get_dynamic_invalid_target_reason(st, CASTER_ID, TARGET_ID)
            == int(TR.TargetIsInRange))


def test_dynamic_reason_accepts_a_reachable_target():
    st = _state(caster=(0, 3), target=(3, 3))
    assert RammingSpeedAbility().get_dynamic_invalid_target_reason(st, CASTER_ID, TARGET_ID) == 0


def test_dynamic_reason_refuses_a_caster_that_already_moved():
    """`DidMove(caster) && !isAdjacent -> 0x10 = CasterHasNotMoved`."""
    from engine.runner.components import set_moved_flag
    st = _state(caster=(0, 3), target=(3, 3))
    set_moved_flag(st, CASTER_ID)
    assert (RammingSpeedAbility().get_dynamic_invalid_target_reason(st, CASTER_ID, TARGET_ID)
            == int(TR.CasterHasNotMoved))


# ------------------------------------------- `#389-r1` : le RETRAIT de 1098 a la cloture de phase
#
# MECANISME NATIF, nomme. La classe d'effet n'a AUCUNE methode a son nom dans les tables (4 corps
# DEDUPLIQUES, donc attribues a d'autres classes) ; son bloc de 5 entrees consecutives dans la table
# de pointeurs IL2CPP les rend tous, et l'appariement position <-> slot est CALIBRE sur
# `IdunBattle.Entities.Effects.Loki.PowerTrip_FullHealthEffect` (4 overrides NOMMES) :
#
#     CreateTargetTrigger          = DSLTriggers$$On(0x3a = PhaseEnd, ownerNeedsToBeAlive: false)
#     CreateTargetTriggerBehaviour = BaseEffect$$GetRemoveEffectBehaviour
#                                  = DSLBehaviors$$RemoveEffect(Effect@0x38)
#
# `PhaseEnd` est publie par `IdunBattle.Operations.EndPhaseOperation$$Execute`, atteint depuis la
# branche `isInternalPhase == false` d'`IdunBattle.Messages.InputMessageProcessor$$RunPhase` -- le
# corps meme d'un `applyAction`. Cf. `runner/operations/triggers/loki/ramming_speed.py` et
# `dispatch/phase.py`. Detail : `docs/rl/case-389-ramming-speed-combat.md` sec.5.

def _state_with_effects(**kw):
    """`_state()` + un `EffectsState` VIDE : sans lui, `AddEffect` emet mais ne materialise rien, et
    tout cliquet sur la duree de vie de l'instance serait vacant."""
    from engine.entities import EffectsState
    st = _state(**kw)
    st.effects = EffectsState()
    return st


def _cast_via_runner(st):
    """Cast par le CHEMIN DE PRODUCTION offline (`Runner.apply`), le seul qui porte la borne de
    phase -- `AbilityHandler.visit_ActiveAbilityMessage` appele nu ne la traverse pas."""
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner
    Runner(st).install_default_handlers(20).apply(
        ActiveAbilityMessage(caster_id=CASTER_ID, target_id=TARGET_ID, ability_type=ABILITY))
    return st


def _instances_1098(st):
    return [e for e in (st.effects.by_unit.get(CASTER_ID) or []) if e.effect_type == 1098]


def test_the_removal_trigger_is_registered_on_phase_end():
    """Garde STRUCTURELLE : l'entree existe, elle ecoute `On(0x3a = PhaseEnd = 58)` et porte 1098.
    Un port qui la retirerait -- ou la re-brancherait sur `TurnEnd` (0x17), l'autre valeur du meme
    couple de classes soeurs `UntilOfEndTurnEffect`/`UntilOfEndPhaseEffect` -- rougit ici."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers import EFFECT_TRIGGERS
    from engine.runner.operations.triggers.loki.ramming_speed import RammingSpeedExtraExplodeRemove
    entries = EFFECT_TRIGGERS.get(1098) or []
    assert RammingSpeedExtraExplodeRemove in entries
    assert RammingSpeedExtraExplodeRemove.effect_type == 1098
    assert RammingSpeedExtraExplodeRemove.event_id == int(EventTriggerType.PhaseEnd) == 58


def test_runner_apply_closes_the_phase(monkeypatch):
    """Garde de CABLAGE : `Runner.apply` emet `PhaseEnd` EN SORTIE (mirror de la publication `0x3a`
    d'`EndPhaseOperation$$Execute`, appelee par `RunPhase(..., isInternalPhase: false)`).

    L'import du vecteur est LAZY dans `apply` -> patcher l'attribut du module suffit, et le compteur
    prouve l'emission SANS dependre d'un consommateur."""
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.operations.triggers.dispatch import phase as phase_mod
    from engine.runner.runner import Runner
    seen = []
    monkeypatch.setattr(phase_mod, "phase_end_triggers", lambda st: seen.append(st) or [])
    st = _state_with_effects()
    Runner(st).install_default_handlers(20).apply(
        ActiveAbilityMessage(caster_id=CASTER_ID, target_id=TARGET_ID, ability_type=ABILITY))
    assert len(seen) == 1 and seen[0] is st


def test_the_cast_poses_1098_and_the_phase_boundary_removes_it():
    """LES DEUX FAITS, dans le meme test, pour qu'aucun ne puisse etre satisfait par l'autre :
    l'arbre POSE bien l'effet (ce n'est pas un refus de pose -- l'evenement de creation existe cote
    natif aussi), et la CLOTURE DE PHASE le retire."""
    from engine.runner.components import has_effect_of_type
    # (a) l'arbre seul, hors borne de phase : l'instance est posee et VIVANTE.
    st_tree = _state_with_effects()
    _run_tree(st_tree)
    posed = _instances_1098(st_tree)
    assert len(posed) == 1 and not posed[0].consumed
    assert has_effect_of_type(st_tree, CASTER_ID, 1098) is True
    # (b) le meme cast par `Runner.apply` : l'instance existe TOUJOURS mais n'est plus lue.
    st = _cast_via_runner(_state_with_effects())
    kept = _instances_1098(st)
    assert len(kept) == 1 and kept[0].consumed, "1098 doit etre RETIRE a la cloture de phase"
    assert has_effect_of_type(st, CASTER_ID, 1098) is False


def test_stripping_the_registry_entry_keeps_1098_alive(monkeypatch):
    """CONTRE-EPREUVE : sans l'entree de registre, l'effet SURVIT au meme cast. C'est l'etat
    d'AVANT `#389-r1` -- `AddEffect` options ZERO -> `remaining = 0` = PERMANENT. Ce cliquet garantit
    que le test ci-dessus mesure bien le RETRAIT, et pas une non-pose."""
    from engine.runner.components import has_effect_of_type
    from engine.runner.operations.triggers import EFFECT_TRIGGERS
    monkeypatch.setitem(EFFECT_TRIGGERS, 1098, [])
    st = _cast_via_runner(_state_with_effects())
    left = _instances_1098(st)
    assert len(left) == 1 and not left[0].consumed
    assert has_effect_of_type(st, CASTER_ID, 1098) is True


def test_a_nova_after_the_cast_reads_the_BASE_percentage_only(monkeypatch):
    """LE REGIME QUI MORD, bout en bout. `ExplodesAbility$$GetDamage` =
    `PercentageOf(Sum(ConfigConst(1021 Explodes, explodesDmg),
                      ConditionalAmount(HasEffect(Owner, 1098), ConfigConst(1059, extraDmgPct), 0)),
                 StatAmount(Owner, HEALTH, MAXIMUM))`.

    Une mort survenant APRES le cast (tour suivant, ou coup adverse) lit 1098 APRES `PhaseEnd`. Avec
    le retrait porte : `explodesDmg` SEUL. Sans lui : `explodesDmg + extraDmgPct` -- le porteur
    garderait A VIE le bonus d'une charge deja consommee.

    Bras DISCRIMINANT par construction : l'assertion finale exige que les deux montants DIFFERENT."""
    import gameconfig as GC
    from engine.dsl.effects import ExecutionContext
    from engine.runner.operations.triggers import EFFECT_TRIGGERS
    from engine.runner.operations.triggers.loki.death_nova import explodes_tree
    base = int(((GC.trait("Explodes") or {}).get("variables") or {}).get("explodesDmg"))
    extra = int(((GC.ability("RammingSpeed") or {}).get("constants") or {}).get("extraDmgPct"))

    def _nova(st):
        ectx = ExecutionContext(state=st, rng=st.rng)
        explodes_tree(base, extra).execute(
            entities_from_state(st, CASTER_ID, CASTER_ID), ectx)
        return [p["attack"]["base_min"] for n, p in ectx.emitted
                if n == "AttackWithAbilityDamage"]

    with_removal = _nova(_cast_via_runner(_state_with_effects()))
    assert with_removal == [round(HP * base / 100)]
    monkeypatch.setitem(EFFECT_TRIGGERS, 1098, [])              # port AMPUTE du retrait
    without_removal = _nova(_cast_via_runner(_state_with_effects()))
    assert without_removal == [round(HP * (base + extra) / 100)]
    assert with_removal != without_removal, "bras non discriminant : extraDmgPct vaut 0 en config"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
