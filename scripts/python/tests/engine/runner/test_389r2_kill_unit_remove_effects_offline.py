"""#389-r2 -- `IdunBattle.Operations.KillUnitOperation$$RemoveEffects`, 100 % OFFLINE.

Ce que ces cliquets verrouillent, et POURQUOI :

  * **un mort perd TOUS ses effets**, pas seulement ceux qui portent des `ability_modifications`.
    C'est l'ecart chiffre de #389-r1 (natif `[]`, port `[1026, 1098, 1361, 1362]`) : trois des
    quatre effets n'avaient AUCUN rapport avec l'ability qui l'avait revele.
  * **une unite VIVANTE ne perd rien** -- controle negatif, sans quoi le cliquet precedent serait
    satisfait par un port qui viderait les effets de tout le monde.
  * **un REVIVE court-circuite le retrait** : la garde `!PendingRevive.HasValue` de
    `IdunBattle.Operations.KillUnitOperation$$Execute` est AVANT les trois `RemoveEffects`, donc un
    mort qui revient garde ses effets. C'est la face qui separe les deux mecanismes de desarmement
    du marqueur `FuelledByFury_CanRevive` (1324) -- cf. `test_fuelled_by_fury_revive_live.py`.
  * **la GARDE HEAL** (`if (health.hp > 0) return` juste avant le 3e appel) : un consommateur de
    `On(UnitDeath)` / `On(UnitDefeated)` qui remonte les PV du mourant ANNULE le step
    `AfterDeathTrigger`. Face que le live n'atteint pas (aucun consommateur porte ne soigne un
    mourant sur ces deux vecteurs) -- elle se mesure donc ICI.
  * **la ventilation par `KillUnitStep`** : un effet marque `AfterDeathTrigger` survit a
    `On(UnitDeath)` et `On(UnitDefeated)`, un effet marque `PreUnitRemove` non. Le defaut
    (`PreUnitRemove`) est une HYPOTHESE NOMMEE (getteur constant DEDUPLIQUE, illisible offline) --
    ces cliquets gardent la MECANIQUE, pas la valeur par defaut.
  * **le foyer est PARTAGE avec la feuille DSL `RemoveEffect`** : les deux passent par
    `remove_effect_instance`, donc les deux revoquent et emettent `On(0x3f = PreEffectRemoved)` / `On(0x40 = EffectRemoved)`.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                              # noqa: E402
from engine.entities.effects.base import BaseEffect  # noqa: E402
from engine.entities.effects_state import EffectsState                     # noqa: E402
from engine.runner.components import HealthComponent, UnitComponent        # noqa: E402
from engine.runner.operations.damage import AttackDamageOperation          # noqa: E402
from engine.entities.kill_unit_step import KillUnitStep                    # noqa: E402
from engine.runner.operations.remove_effects import (                      # noqa: E402
    remove_effect_instance, remove_effects_operation)

COLS, ROWS = 5, 5
KILLER_ID, VICTIM_ID = 10, 20
HP = 1000


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _state():
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    board = Board(tiles, adjacency="evenq")
    decision = {"currentPlayer": 1, "units": [
        {"id": KILLER_ID, "visualId": "orksKillaKan", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 0, "row": 0}, "effects": []},
        {"id": VICTIM_ID, "visualId": "necroWarden", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 2, "row": 2}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": HP, "hpMax": HP} for u in decision["units"]]}
    st = load_state(decision, observe, board=board)
    if st.effects is None:
        st.effects = EffectsState()
    return st


def _put(st, uid, effect_type, name, **kw):
    e = BaseEffect(name=name, effect_type=int(effect_type), target=int(uid), **kw)
    st.effects.add_effect(int(uid), e)
    return e


def _alive_effects(st, uid):
    return sorted(int(e.effect_type) for e in (st.effects.by_unit.get(int(uid)) or [])
                  if not e.consumed)


def _kill(st, uid, killer=KILLER_ID):
    """Fait passer l'unite par le VRAI chokepoint de mort (le meme que le pipeline de degat)."""
    e = st.get_entity(uid)
    hc = e.get_component(HealthComponent)
    before = int(hc.hp)
    hc.hp = 0
    return AttackDamageOperation._fire_death_if_killed(st, uid, killer, before, 0, e,
                                                       damage=before) or []


# ------------------------------------------------------------------ l'enum, VERBATIM du dump

def test_kill_unit_step_is_the_native_enum():
    """`IdunBattle.Operations.KillUnitStep` = `0=PreUnitRemove,1=AfterUnitRemove,2=AfterDeathTrigger`
    (`data/symbols/<build>/frida/enums.tsv`). Les trois valeurs sont les trois literaux passes par
    `IdunBattle.Operations.KillUnitOperation$$Execute` a `$$RemoveEffects`."""
    assert (int(KillUnitStep.PreUnitRemove), int(KillUnitStep.AfterUnitRemove),
            int(KillUnitStep.AfterDeathTrigger)) == (0, 1, 2)
    # #427 : les NOMS aussi sont ceux du jeu -- c'est ce qui autorise `strict=True` au registre de
    # `probe_313`, donc la garde du sens RENUMEROTE sur ce mirror.
    assert [m.name for m in KillUnitStep] == ["PreUnitRemove", "AfterUnitRemove",
                                              "AfterDeathTrigger"]


# ------------------------------------------------------------------ le coeur : un mort perd TOUT

def test_a_dead_unit_loses_every_effect():
    """L'ECART DE #389-r1, chiffre : le natif rend `[]`, le port rendait la liste entiere. Aucun des
    effets poses ici ne porte d'`ability_modifications` -- le volet ETROIT d'avant n'en aurait
    consomme AUCUN."""
    st = _state()
    for et, nm in ((1026, "A"), (1098, "B"), (1361, "C"), (1362, "D")):
        _put(st, VICTIM_ID, et, nm)
    assert _alive_effects(st, VICTIM_ID) == [1026, 1098, 1361, 1362]
    _kill(st, VICTIM_ID)
    assert not st.get_entity(VICTIM_ID).get_component(UnitComponent).alive
    assert _alive_effects(st, VICTIM_ID) == []


def test_a_living_unit_keeps_its_effects():
    """CONTROLE NEGATIF : le retrait vise le MORT, pas le plateau. Sans lui, un port qui viderait
    tout le monde satisferait le cliquet precedent."""
    st = _state()
    _put(st, KILLER_ID, 1026, "A")
    _put(st, VICTIM_ID, 1098, "B")
    _kill(st, VICTIM_ID)
    assert _alive_effects(st, KILLER_ID) == [1026]
    assert _alive_effects(st, VICTIM_ID) == []


def test_a_pending_revive_short_circuits_the_removal():
    """GARDE REVIVE `if (!unitComponent.PendingRevive@+0xa8 .HasValue)` -- elle est AVANT les trois
    `RemoveEffects`, donc un mort qui revient garde ses effets."""
    st = _state()
    _put(st, VICTIM_ID, 1324, "CanRevive")
    _put(st, VICTIM_ID, 1354, "BlockOverkill")
    uc = st.get_entity(VICTIM_ID).get_component(UnitComponent)
    uc.pending_revive = {"amount": HP, "heal_type": 0, "source": 1251, "priority": 0}
    out = _kill(st, VICTIM_ID)
    assert any("kill_cancelled_by_revive" in r for r in out), out
    assert _alive_effects(st, VICTIM_ID) == [1324, 1354]


def test_the_heal_gate_cancels_the_third_step():
    """GARDE HEAL `if (health.hp > 0) return`, juste avant `RemoveEffects(AfterDeathTrigger)` : les
    steps 0 et 1 ont deja tourne, le 3e est ANNULE. Face que le live n'atteint pas."""
    st = _state()
    e_late = _put(st, VICTIM_ID, 7001, "Late")
    e_late.remove_on_kill_step = int(KillUnitStep.AfterDeathTrigger)
    _put(st, VICTIM_ID, 7000, "Early")            # defaut = PreUnitRemove
    # un consommateur d'`On(UnitDefeated)` remonte les PV : on le simule en soignant AVANT le drain
    # de la file (le port relit le `HealthComponent` juste avant le step 2, comme le natif).
    hc = st.get_entity(VICTIM_ID).get_component(HealthComponent)
    before = int(hc.hp)
    hc.hp = 0
    AttackDamageOperation._record_death_reason(st, VICTIM_ID, KILLER_ID, None)
    AttackDamageOperation._add_death(st, VICTIM_ID, KILLER_ID, False)
    hc.hp = 500                                   # le << heal >> pendant la sequence de mort
    AttackDamageOperation._verify_deaths(st)
    assert _alive_effects(st, VICTIM_ID) == [7001], \
        "le step 2 a tourne malgre des PV > 0 (ou le step 0 n'a pas tourne)"
    assert before == HP


def test_the_step_ventilation_orders_the_removals():
    """Un effet marque `AfterDeathTrigger` survit a `On(UnitDeath)` et `On(UnitDefeated)` ; un effet
    au defaut (`PreUnitRemove`) part avant eux. Le cliquet garde la MECANIQUE de ventilation -- la
    valeur par defaut, elle, est une hypothese nommee (getteur constant DEDUPLIQUE)."""
    st = _state()
    seen = {}
    late = _put(st, VICTIM_ID, 7001, "Late")
    late.remove_on_kill_step = int(KillUnitStep.AfterDeathTrigger)
    _put(st, VICTIM_ID, 7000, "Early")
    from engine.runner.operations.triggers.dispatch import move_death as MD
    orig = MD.unit_death_triggers

    def _spy(state, dying_id, killer_id=None, **kw):
        seen["at_unit_death"] = _alive_effects(state, dying_id)
        return orig(state, dying_id, killer_id, **kw)
    MD.unit_death_triggers = _spy
    try:
        import engine.runner.operations.triggers as T
        T.unit_death_triggers = _spy
        _kill(st, VICTIM_ID)
    finally:
        MD.unit_death_triggers = orig
        import engine.runner.operations.triggers as T
        T.unit_death_triggers = orig
    assert seen.get("at_unit_death") == [7001], \
        "au moment d'On(UnitDeath), seul l'effet AfterDeathTrigger doit rester (%s)" % seen
    assert _alive_effects(st, VICTIM_ID) == []


# ------------------------------------------------------------------ l'Operation elle-meme

def test_remove_effects_operation_without_step_takes_everything():
    """`options.step` SANS valeur -> aucun filtre (le `Nullable.HasValue` natif). C'est la forme que
    prendrait un appelant hors sequence de mort."""
    st = _state()
    a = _put(st, VICTIM_ID, 7000, "Early")
    b = _put(st, VICTIM_ID, 7001, "Late")
    b.remove_on_kill_step = int(KillUnitStep.AfterDeathTrigger)
    removed = remove_effects_operation(st, VICTIM_ID)
    assert sorted(removed) == [7000, 7001]
    assert a.consumed and b.consumed


def test_remove_effect_instance_is_idempotent():
    """Gates `EffectComponent.IsRemoved@+0x5f` / `IsRemoving@+0x5e` : une instance deja retiree ne
    repasse pas -- le natif RETOURNE sans rien faire."""
    st = _state()
    e = _put(st, VICTIM_ID, 7000, "Early")
    assert remove_effect_instance(st, VICTIM_ID, e) is True
    assert remove_effect_instance(st, VICTIM_ID, e) is False
    assert remove_effects_operation(st, VICTIM_ID) == []


def test_removal_publishes_both_effect_vectors():
    """`On(PreEffectRemoved = 0x3f)` AVANT la revocation, `On(EffectRemoved = 0x40)` APRES -- les
    deux publications de `IdunBattle.Operations.RemoveEffectOperation$$Execute`. Le foyer partage
    doit les emettre AUSSI quand le retrait vient de la sequence de mort."""
    from engine.runner.operations.triggers.dispatch import move_death as MD
    st = _state()
    _put(st, VICTIM_ID, 7000, "Early")
    calls = []
    orig = MD._effect_vector_triggers

    def _spy(state, event_id, actor_id, target_id, effect_type, *, removing):
        calls.append((int(event_id), int(target_id), int(effect_type), bool(removing)))
        return orig(state, event_id, actor_id, target_id, effect_type, removing=removing)
    MD._effect_vector_triggers = _spy
    try:
        _kill(st, VICTIM_ID)
    finally:
        MD._effect_vector_triggers = orig
    assert (0x3f, VICTIM_ID, 7000, True) in calls, calls
    assert (0x40, VICTIM_ID, 7000, True) in calls, calls
    assert calls.index((0x3f, VICTIM_ID, 7000, True)) < calls.index((0x40, VICTIM_ID, 7000, True))


def test_the_dsl_leaf_uses_the_same_focus():
    """Frontiere #149 : la feuille DSL `RemoveEffect` (declarative) APPELLE `remove_effect_instance`
    (imperative). Un seul foyer -> une seule semantique de retrait."""
    import inspect
    from engine.runner.abilities.behaviours.effects import RemoveEffect
    src = inspect.getsource(RemoveEffect.execute)
    assert "remove_effect_instance" in src
