"""#227 -- GARDE de l'EMETTEUR d'`On(UnitRemoved = 0x25 = 37)`.

CE QUE CE FICHIER VERROUILLE, et pourquoi c'est un cliquet et pas un test de plus :

Le vecteur `unit_removed_triggers` existait, etait exporte et etait ENREGISTRE cote port -- mais
**aucun site de production ne l'appelait** (`RemoveUnitOperation` n'etait pas portee ; les deux
sites de despawn du port -- la feuille DSL `RemoveUnit` et l'eviction MV71 -- se contentaient d'un
`alive = False` + consommation des effets PORTES par l'unite). Un consommateur ecoutait donc un
evenement que rien ne declenchait : degradation **RESTRICTIVE et silencieuse** (ni erreur, ni
crash, le trigger ne fire jamais). C'est exactement la classe de trou qu'aucun test ne voit.

CHAINE NATIVE (decompile = verite) :
    `IdunBattleLogic.Entities.DSLBehaviors$$RemoveUnit`
      -> `IdunBattle.Entities.Behaviours.RemoveUnitBehaviour$$Execute`  (slot +6, args `(uid, 1, 0)`)
      -> `Core.Services.OperationProcessor$$RemoveUnit`
      -> `IdunBattle.Operations.RemoveUnitOperation$$Execute`
           ... `UnitFlagsComponent$$Add(entity, 0x1a = Removed)`
           ... **publie `On(0x25)`** `(a = b = c = l'unite retiree)`
           ... PUIS, si `removeEffects`, `RemoveUnitOperation$$RemoveEffects`.

CONSOMMATEUR UNIQUE porte : `GhostRemoveOnSourceRemoved` -- 5e retrait de
`IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateHandleTriggerAbilitiesInternal`
(`On(0x25) & AreEqual(EffectSource, target@0x178)`, effet 1186 `TimeFlux_Revive` de
`thousTerminator`). Le ghost est porte par la TUILE avec Toth pour SOURCE : c'est ce qui rend la
contre-epreuve nette -- consommer les effets de Toth ne le retire PAS, seul l'evenement le fait.

Aucune fixture gelee : l'etat vient d'un runner LIVE (`load_state` de `decisionView` /
`observeBattle` / `combatSnapshot` / `boardGraph` / `tileMeta`), le kit vient de gameconfig.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]          # scripts/python
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

GHOST_HERO = "thousTerminator"      # Toth
GHOST_FOE = "orksNob"               # ennemi jamais pilote
MV71_HERO = "tauMarksman"           # Sho'syl -- attaque normale 1076
MV71_FOE = "astraBullgryn"
DRONE = "tauSmnDroneSniper"
BOARD = "MC1_67"
SEED = "31337"


# --------------------------------------------------------------------- cliquet structurel
def test_unit_removed_vector_has_a_production_emitter():
    """CLIQUET : `On(0x25)` doit avoir au moins un emetteur de production, et son ecouteur
    doit rester enregistre. Si l'un des deux disparait, le couple redevient MORT en silence."""
    from probe_227_unit_removed_blast_radius import emitters, listeners

    lis, emi = listeners(), emitters()
    assert lis, ("plus aucun trigger n'ecoute On(UnitRemoved) : le vecteur n'a plus d'objet "
                 "(si c'est voulu, retirer aussi l'emetteur et cette garde)")
    assert emi, ("On(UnitRemoved = 0x25) n'a AUCUN emetteur de production : les %d ecouteur(s) "
                 "sont MORTS (degradation restrictive silencieuse, cf. #227). Emetteur attendu : "
                 "engine/runner/operations/remove_unit.py" % len(lis))


def test_remove_unit_operation_is_the_single_despawn_path():
    """Les DEUX sites de despawn du port passent par l'Operation -- personne ne remet un
    `alive = False` inline (c'est ainsi que le vecteur avait perdu son emetteur)."""
    root = PYDIR / "engine" / "runner"
    for rel in ("abilities/behaviours/lifecycle.py", "abilities/loki/mv71.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert "RemoveUnitOperation" in src, \
            f"{rel} ne delegue plus a RemoveUnitOperation (despawn sans On(0x25) ?)"


# ------------------------------------------------------------------------------ face LIVE A
@pytest.fixture(scope="module")
def ghost_stage(live_session, build_runner, rpc):
    """Runner LIVE avec Toth : etat capte JUSTE AVANT son deplacement (donc avant la pose du
    ghost), plus la tuile de destination choisie."""
    import hexgeo
    from probe_227_remove_unit_operation import view, wait_for_action, movable

    info = build_runner(SEED, extra=["--board", BOARD, "--p-units", GHOST_HERO,
                                     "--a-units", GHOST_FOE, "--no-ai"])
    rid = info["rid"]
    sid = live_session
    dv, uu = wait_for_action(sid, rid, GHOST_HERO)
    if GHOST_HERO not in uu:
        pytest.fail(f"{GHOST_HERO} absent du runner {rid} -- montage KO")
    hid = uu[GHOST_HERO][0]["id"]
    start = (uu[GHOST_HERO][0]["col"], uu[GHOST_HERO][0]["row"])
    cand = [t for t in movable(sid, rid, hid) if t != start]
    if not cand:
        pytest.fail("aucune tuile de destination -- Toth ne peut pas bouger, pas de ghost")
    cand.sort(key=lambda t: -hexgeo.distance(t, start))
    return {"sid": sid, "rid": rid, "dv": dv, "hid": hid, "start": start, "dest": cand[0]}


def _moved_state_with_ghost(stage):
    """Etat PORT reconstruit du live, `StartTurnOperation` rejoue (seul ecrivain de
    `UnitComponent + 0x18c`) puis MOVE -> `On(PreUnitMove)` -> le ghost est pose."""
    from probe_227_remove_unit_operation import load_port_state, port_ghost_tiles
    from engine.runner.components import OwnerComponent
    from engine.runner.events import EventBus
    from engine.runner.operations.movement import MoveUnitOperation
    from engine.runner.operations.turnflow import StartTurnOperation

    st, board = load_port_state(stage["sid"], stage["rid"], stage["dv"])
    pl = st.get_entity(stage["hid"]).get_component(OwnerComponent).player
    StartTurnOperation.execute(st, pl)
    MoveUnitOperation(stage["hid"], stage["dest"]).execute(st, EventBus())
    return st, board, port_ghost_tiles(st)


def test_ghost_is_posted_on_the_turn_start_tile(ghost_stage):
    """COUVERTURE (anti-faux-vert) : sans ghost pose, les deux tests suivants ne testent rien."""
    st, board, ghosts = _moved_state_with_ghost(ghost_stage)
    tile_a = board.id_at(*ghost_stage["start"])
    assert ghosts == [tile_a], (
        f"le GhostEffect 1186 devrait etre porte par la seule tuile de debut de tour "
        f"{tile_a}, obtenu {ghosts}")


def test_removing_the_ghost_source_dissipates_the_ghost(ghost_stage):
    """`On(0x25)` -> `GhostRemoveOnSourceRemoved` : retirer le POSEUR fait partir le ghost."""
    from probe_227_remove_unit_operation import port_ghost_tiles
    from engine.runner.components import UnitFlagsComponent
    from engine.runner.operations.remove_unit import RemoveUnitOperation

    st, _, ghosts_before = _moved_state_with_ghost(ghost_stage)
    assert ghosts_before, "montage KO : aucun ghost a dissiper"
    out = RemoveUnitOperation.execute(st, ghost_stage["hid"], remove_effects=True)
    assert out is not None, "l'Operation a refuse un retrait legitime"
    assert port_ghost_tiles(st) == [], (
        "le time-ghost SURVIT au retrait de son poseur : On(UnitRemoved) n'est pas emis "
        "(ou le trigger 1186 ne l'ecoute plus)")
    fl = st.get_entity(ghost_stage["hid"]).get_component(UnitFlagsComponent)
    assert fl.has(UnitFlagsComponent.REMOVED), \
        "le flag `Removed (0x1a)` n'est pas pose -- gate anti-double-retrait inoperant"
    assert RemoveUnitOperation.execute(st, ghost_stage["hid"]) is None, \
        "second retrait accepte : le gate `HasFlag(entity, 0x1a)` ne mord pas"


def test_legacy_despawn_would_leave_the_ghost_behind(ghost_stage):
    """CONTRE-EPREUVE (mordant) : la mutation d'AVANT #227 -- `alive = False` + consommation des
    effets PORTES par l'unite, sans evenement -- laisse le ghost EN PLACE. C'est la preuve que le
    test precedent ne peut pas passer par accident : le ghost est porte par la TUILE."""
    from probe_227_remove_unit_operation import port_ghost_tiles
    from engine.runner.components import UnitComponent

    st, _, ghosts_before = _moved_state_with_ghost(ghost_stage)
    e = st.get_entity(ghost_stage["hid"])
    e.get_component(UnitComponent).alive = False
    for eff in (st.effects.by_unit.get(int(ghost_stage["hid"]), []) or []):
        eff.consumed = True
    assert port_ghost_tiles(st) == ghosts_before, (
        "la contre-epreuve ne mord plus : le despawn sans evenement retire deja le ghost, "
        "donc le test principal ne prouve rien")


# ------------------------------------------------------------------------------ face LIVE B
def test_mv71_eviction_goes_through_the_operation(live_session, build_runner, rpc):
    """NON-REGRESSION du SEUL call-site de production : `MV71SniperDroneSquadAttackAbility`
    (Sho'syl). Quatre casts -> le natif borne a `maxSummons` via `HasToManySummons` ; l'evince
    doit porter `Removed` et le compte de drones vivants respecter le cap du gameconfig."""
    import gameconfig as GC
    from probe_227_remove_unit_operation import load_port_state, view
    from engine.runner.abilities.loki.mv71 import MV71SniperDroneSquadAttackAbility
    from engine.runner.components import UnitComponent, OwnerComponent, UnitFlagsComponent

    max_summons = int(((GC.ability("MV71SniperDroneSquad") or {}).get("constants")
                       or {}).get("maxSummons") or 3)
    info = build_runner(SEED, extra=["--board", BOARD, "--p-units", MV71_HERO,
                                     "--a-units", MV71_FOE, "--hp-target", "999999", "--no-ai"])
    rid = info["rid"]
    dv, uu = view(live_session, rid)
    if MV71_HERO not in uu or MV71_FOE not in uu:
        pytest.fail(f"roster incomplet sur le runner {rid} -- montage KO")
    cid, tid = uu[MV71_HERO][0]["id"], uu[MV71_FOE][0]["id"]
    st, _ = load_port_state(live_session, rid, dv)
    team = st.get_entity(cid).get_component(OwnerComponent).team
    ability = MV71SniperDroneSquadAttackAbility()
    evicted = []
    for _ in range(max_summons + 1):                 # un cast de plus que le cap -> eviction
        out = ability.execute_behaviour(st, cid, tid)
        if out:
            evicted += list(out.get("evicted") or [])
    assert evicted, (
        f"aucune eviction apres {max_summons + 1} casts : le call-site de RemoveUnit n'est pas "
        f"exerce, la garde ne teste rien")
    for uid in evicted:
        fl = st.get_entity(int(uid)).get_component(UnitFlagsComponent)
        assert fl is not None and fl.has(UnitFlagsComponent.REMOVED), (
            f"le drone evince {uid} ne porte pas `Removed (0x1a)` : l'eviction MV71 ne passe "
            f"plus par RemoveUnitOperation")
    alive = [uid for uid, e in st.entities.items()
             if (e.get_component(UnitComponent) is not None
                 and e.get_component(UnitComponent).visual_id == DRONE
                 and e.get_component(UnitComponent).alive
                 and e.get_component(OwnerComponent) is not None
                 and e.get_component(OwnerComponent).team == team)]
    assert len(alive) <= max_summons, (
        f"{len(alive)} drones vivants pour un cap natif de {max_summons} -- l'eviction "
        f"n'a pas libere la place")
