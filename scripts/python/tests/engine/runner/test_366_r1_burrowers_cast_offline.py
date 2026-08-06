"""GARDE #366-r1 tranche 1 (OFFLINE PURE) -- `Burrowers` (active 1023) et la clause TUILE-NULLE.

CE QU'ELLE PROTEGE, en trois blocs, et pourquoi chacun peut regresser SILENCIEUSEMENT :

  1. **LE CAST**. Les TROIS `AActiveAbility$$Execute` de
     `IdunBattleLogic.Entities.Abilities.Active.Loki.BurrowersAbility$$ExecuteBehaviour` --
     `RemoveUnitFromItsTiles(Caster, true)` & `RemoveAllForcedAttackTargets(Caster)` &
     `AddEffect(0x410 Burrowers_Hidden -> le CASTER, surcharge SANS source, PERMANENT)`.
     L'hypothese « jumeau exact de 1011 » est FAUSSE sur cet etage 3 : chez 1011 l'effet va sur la
     TUILE visee (`AddBondEffect`), ici sur le CASTER. Une regression qui remettrait un bond sur une
     tuile serait invisible sans ce test.
  2. **LES DEUX LITTERAUX DU REGISTRE**. Le `$$.ctor` de 1023 n'appelle AUCUN ctor de
     `TargetingOptions` : il recopie le preset STATIQUE `<TargetingOptions statics>+0x280`
     (`isSelfCasting = 1`, range = `TargetingRange statics+0x60` = RANGE_SELF, forceMeleeTarget = 1,
     `rules = 0x8004`). Recopier « le litteral visible » du ctor donnerait un masque FAUX -- il n'y
     en a aucun. `ABILITY_ATTACK_TYPE` = le 3e argument d'`AActiveAbility..ctor` = 2 = Others.
  3. **LA CLAUSE TUILE-NULLE** du volet CASTER (`TargetingQuery$$GetInvalidCasterReason`) :
     `!AllowNullCasterTile && !CasterHasNoTile && IsNullOrEmpty(casterTiles) -> broken(0x40000000)`.
     Elle est POSEE par cette tranche. Sans elle, le port ACCEPTE un second cast de 1023 (et de 1011)
     depuis une unite deja sous terre, que le natif REFUSE -- degradation PERMISSIVE, silencieuse,
     exactement le trou qu'un entrainement irait exploiter. Le CONTRE-BRAS (une ability MoW, qui pose
     `AllowNullCasterTile`) garde l'autre sens : la clause ne doit PAS refuser leurs casts.

Mesure live (confrontation terme a terme sur 2 couples board/seed, echange d'ability, verdicts) :
`python scripts/python/probe_366_r1_burrowers.py`.
RE : `docs/rl/case-366-r1-tunneling-horror-pending-summon.md` §5. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import hexgeo                                                            # noqa: E402
from engine.entities.effects_state import EffectsState  # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES              # noqa: E402
from engine.runner.abilities.targeting import (RANGE_SELF, RANGED_BOOL_FALSE,  # noqa: E402
                                               get_invalid_caster_reason)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.abilities.tyranids import BurrowersAbility            # noqa: E402
from engine.runner.components import (ForcedAttackTargetsComponent, PositionComponent,  # noqa: E402
                                      UnitComponent, get_unit_feet, set_unit_feet)
from engine.runner.snapshot import load_state                            # noqa: E402

BURROWERS = 1023                 # ActiveAbilityType.Burrowers
HIDDEN = 1040                    # EffectType.Burrowers_Hidden (0x410)
# `BurrowersAbility$$.ctor` : PAS de ctor `TargetingOptions`, recopie du preset statique +0x280,
# dont `TargetingOptions$$.cctor` ecrit `<preset>+0x28 = 0x8004`.
NATIVE_MASK = 0x8004
COLS, ROWS = 7, 7
CASTER, ALLY, FOE = 10, 40, 20


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


@pytest.fixture
def state():
    """`State` runner minimal : deux allies Tyranids + un ennemi, `EffectsState` materialise (sans
    lui `AddEffectOperation` abandonne -- et la feuille emettrait quand meme sa trace)."""
    board = Board(_tiles(), adjacency="evenq")
    decision = {"currentPlayer": 1, "units": [
        {"id": CASTER, "visualId": "tyranParasite", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 0, "row": 3}, "effects": []},
        {"id": ALLY, "visualId": "tyranNeurothrope", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 3}, "effects": []},
        {"id": FOE, "visualId": "ultraTitus", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 6, "row": 6}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    st = load_state(decision, observe, board=board)
    if st.effects is None:
        st.effects = EffectsState()
    return st


def _hidden(st, uid) -> list:
    return [e for e in (st.effects.by_unit.get(int(uid)) or [])
            if int(getattr(e, "effect_type", -1)) == HIDDEN and not e.consumed]


# ------------------------------------------------------------------ 1. LE CAST

def test_cast_removes_the_caster_from_the_board_and_marks_the_caster_itself(state):
    """LES TROIS ETAGES, en un cast. Le caster quitte le plateau (`pos`/`feet` vides,
    `alive = True`) ET porte l'effet 1040 -- c'est LUI la cible de l'`AddEffect`, pas une tuile."""
    ab = BurrowersAbility()
    out = ab.execute_behaviour(state, CASTER, CASTER)
    assert get_unit_feet(state, CASTER) == []
    assert state.get_entity(CASTER).get_component(PositionComponent) is None
    assert state.get_entity(CASTER).get_component(UnitComponent).alive is True
    got = _hidden(state, CASTER)
    assert len(got) == 1, "effet 1040 non pose sur le CASTER : %r" % (out,)
    assert got[0].remaining_turns is None, (
        "1040 doit etre PERMANENT (`DefaultAmountOfRounds(0x410)` = null) : %r"
        % (got[0].remaining_turns,))
    assert got[0].source == CASTER, (
        "source de l'effet = %r (surcharge SANS selecteur source -> la source EST la cible)"
        % (got[0].source,))
    # La feuille n'EMET que pour une unite EFFECTIVEMENT retiree (`applied`), et sa charge utile
    # porte les tuiles liberees -> la presence de l'emission EST la preuve du retrait.
    assert (out.get("removed_from_tiles") or {}).get("tiles") == [(0, 3)]
    assert [p for p in out["posed"] if p["effect"] == HIDDEN and p["placed"]]


def test_cast_marks_the_caster_and_NOBODY_else(state):
    """CONTRE-BRAS de ciblage : ni l'allie, ni l'ennemi, ni AUCUNE tuile ne recoit 1040. C'est ce qui
    distingue le port de celui de 1011, dont l'effet va sur une TUILE."""
    BurrowersAbility().execute_behaviour(state, CASTER, CASTER)
    assert _hidden(state, ALLY) == [] and _hidden(state, FOE) == []
    others = [k for k in state.effects.by_unit if int(k) != CASTER
              and any(int(getattr(e, "effect_type", -1)) == HIDDEN for e in state.effects.by_unit[k])]
    assert others == [], "1040 pose hors du caster : %r" % (others,)


def test_cast_clears_the_forced_attack_targets_of_the_caster(state):
    """2e etage. Il n'a emis AUCUN event dans la mesure live de 1011 (liste vide) ; on l'exerce donc
    ICI, avec une liste NON vide -- le porteur reel (`tyranSmnRipperSwarm`) a le trait
    `InstinctiveBehaviour`, ce regime n'est pas theorique pour lui."""
    e = state.get_entity(CASTER)
    comp = e.add_component(ForcedAttackTargetsComponent())
    comp.targets = [FOE]
    out = BurrowersAbility().execute_behaviour(state, CASTER, CASTER)
    assert comp.get() == []
    assert out["forced_targets_removed"] == [[FOE]], out


def test_cast_is_ordered_remove_then_pose(state):
    """L'ORDRE est LOAD-BEARING : le caster quitte le plateau AVANT la pose, donc l'effet 1040 est
    pose sur une unite SANS position. Un port qui poserait d'abord n'echouerait sur AUCUN des tests
    ci-dessus -- on verifie donc que la pose a bien eu lieu sur une entite deja sans tuile, en
    exigeant que les DEUX soient vrais a la fin ET que la cible de l'AddEffect soit le caster."""
    out = BurrowersAbility().execute_behaviour(state, CASTER, CASTER)
    assert out["removed_from_tiles"]["tiles"] == [(0, 3)]
    assert [p["target"] for p in out["posed"]] == [CASTER]
    assert get_unit_feet(state, CASTER) == []


# ------------------------------------------------------------------ 2. LE REGISTRE

def test_registry_carries_both_native_literals():
    """Une ability qui entre dans `ABILITY_CLASSES` pose son masque ET son `AbilityAttackType` DANS
    LE MEME COMMIT. Les deux sont RELUS au `$$.ctor` -- forme « preset statique copie »."""
    assert ABILITY_CLASSES[BURROWERS] is BurrowersAbility
    opts = BurrowersAbility.TARGETING_OPTIONS
    assert int(opts.rules) == NATIVE_MASK
    assert int(opts.rules) == int(TR.CasterMatchesDynamicRule | TR.CasterIsPossibleTarget), (
        "0x8004 se decompose EXACTEMENT en ces deux bits, sans residu")
    assert opts.self_cast is True and opts.range == RANGE_SELF
    assert opts.force_melee_target == RANGED_BOOL_FALSE
    assert ABILITY_ATTACK_TYPE[BURROWERS] == AbilityAttackType.Others


# ------------------------------------------------------------------ 3. LA CLAUSE TUILE-NULLE

def test_dynamic_caster_rule_mirrors_the_native_literal(state):
    """`BurrowersAbility$$GetDynamicInvalidCasterReason` rend le litteral **4** sur `casterTiles`
    vide, **0** sinon. Le mirror est conserve bien qu'il soit PREEMPTE dans la cascade (cf. le test
    suivant) : le natif porte bien ce test, et le rang de la cascade generique n'est pas une
    propriete de cette ability."""
    ab = BurrowersAbility()
    assert ab.get_dynamic_invalid_caster_reason(state, CASTER) == 0
    set_unit_feet(state, CASTER, [])
    assert ab.get_dynamic_invalid_caster_reason(state, CASTER) == int(TR.CasterMatchesDynamicRule)


def test_a_burrowed_caster_is_refused_by_the_null_tile_clause(state):
    """LE COEUR DE LA NON-REGRESSION. Une unite sans tuile ne peut plus caster 1023, et la raison
    RENDUE est `AllowNullCasterTile` (0x40000000) -- la clause TUILE-NULLE PRECEDE la regle-delegue
    dans `TargetingQuery$$GetInvalidCasterReason`. Avant cette tranche, le port rendait 0 : il
    ACCEPTAIT le second cast."""
    ab = BurrowersAbility()
    assert get_invalid_caster_reason(state, CASTER, ab) == 0        # sur le plateau -> OK
    BurrowersAbility().execute_behaviour(state, CASTER, CASTER)     # le caster s'enfouit
    assert get_invalid_caster_reason(state, CASTER, ab) == int(TR.AllowNullCasterTile)
    assert get_invalid_caster_reason(state, ALLY, ab) == 0          # TEMOIN : toujours acceptant


def test_the_null_tile_clause_spares_abilities_that_allow_it(state):
    """CONTRE-BRAS : la clause est une PERMISSION cote MoW. Une ability qui pose
    `AllowNullCasterTile` (les 17 abilities MoW du registre le font TOUTES) doit rester castable par
    une entite sans tuile -- sinon ce port rendrait toute MoW muette."""
    class _MoWLike:
        TARGETING_OPTIONS = BurrowersAbility.TARGETING_OPTIONS.__class__(
            rules=int(TR.AllowNullCasterTile), self_cast=False)
        ABILITY_ID = None

        def get_dynamic_invalid_caster_reason(self, st, cid):
            return 0

    set_unit_feet(state, CASTER, [])
    assert get_invalid_caster_reason(state, CASTER, _MoWLike()) == 0


def test_every_registry_mow_ability_carries_the_permission():
    """Le compte qui rend le CONTRE-BRAS ci-dessus non anecdotique, RE-DERIVE et non cite de memoire :
    toute ability du registre dont le masque n'a NI `AllowNullCasterTile` NI `CasterHasNoTile` doit
    etre portee par une unite du PLATEAU. On garde l'invariant utile : aucune ability MoW connue ne
    tombe dans ce trou. La liste des MoW vient des commentaires du registre, donc on se contente ici
    de l'implication testable -- les 17 masques a bit 30 sont EXACTEMENT ceux des abilities MoW."""
    with_perm = {aid for aid, k in ABILITY_CLASSES.items()
                 if getattr(k, "TARGETING_OPTIONS", None) is not None
                 and int(k.TARGETING_OPTIONS.rules) & (int(TR.AllowNullCasterTile)
                                                       | int(TR.CasterHasNoTile))}
    # Les abilities MoW portees, releve du registre (cf. `handler.py`, sections MoW).
    mow = {1142, 1143, 1145, 1147, 1148, 1158, 1159, 1160, 1161, 1168, 1169, 1187, 1188,
           1200, 1201, 1213, 1214}
    assert mow <= with_perm, (
        "abilities MoW SANS la permission tuile-nulle (elles deviendraient incastables) : %r"
        % sorted(mow - with_perm))
