"""GARDE LIVE #448-r1-r1 -- la CHAINE de `1134 FullThrottle`, du mouvement natif au gate porte.

Le test offline garde la LOI (`movementSteps = path.Count`) et le seuil. Il ne garde PAS le
CABLAGE : que la greffe soit vue par le collecteur, et que `movementSteps` remonte reellement de
`MoveUnitOperation` jusqu'au trigger a travers `after_move_triggers`. C'est ce que ce fichier
garde, sur un etat LIVE.

POURQUOI C'EST NECESSAIRE, et c'est mesure : au premier jet, le volet PORT du probe rendait
**0 mort sur 200 essais** la ou le natif en tue 30 %. Le gate etait bon, la loi etait bonne -- le
canal `unitAbilityStates` n'etait simplement pas fourni a `load_state`, donc
`UnitContext.passive_abilities` restait `None`, `collect_triggered_abilities` retombait sur la
derivation gameconfig par `visualId` (ou `orksNob` porte `SmashaEad`, jamais `FullThrottle`), et
le passif greffe etait INERTE **sans la moindre erreur**. Une garde qui n'exerce que le gate
n'aurait rien vu.

Le montage est une GREFFE (`catalog_inject.graft_passive_ability`) : `orksNpc6Stormboy` est le SEUL
porteur de `FullThrottle` et il est npc. Condition de greffe verifiee : ni le `CreateTrigger` ni le
`CreateBehaviour` ne lisent stat, trait ou arme du caster.

Les assertions sont DETERMINISTES : on n'exerce pas le tirage `Maybe(chance=30)` (c'est le probe
qui en mesure la frequence), on exerce le GATE sur un mouvement de longueur choisie.

Mesure complete : `python scripts/python/probe_448_r1_r1_full_throttle.py --port`. ASCII only.
"""
from __future__ import annotations

import pytest

import probe_448_r1_r1_full_throttle as P
from engine.entities.pathfinding.board import Board
from engine.runner.components import PositionComponent
from engine.runner.operations.movement import _movement_steps
from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
from engine.runner.operations.triggers.loki.full_throttle import FullThrottlePassiveAbility
from engine.runner.operations.triggers.base import TriggerEvent
from engine.dsl.event_trigger_type import EventTriggerType

BOARD, SEED = "MC1_67", 777
FOES = ["tauCrisis"]


@pytest.fixture(scope="module")
def live(rpc, build_runner):
    """Un runner GREFFE, partage par le module (un seul build).

    On passe par les fixtures `rpc` / `build_runner` du harnais plutot que par un montage maison :
    elles isolent le state-file par PID et LIBERENT le runner au teardown. Un montage maison avait
    ici casse la collecte pytest (`assert not self._finalizers`) -- et un runner non libere fait
    trainer le cap `MAX_RUNNERS` pour tous les autres agents.

    ⚠ Montage KO => ECHEC, jamais skip : un skip vert dirait « rien a valider »."""
    import json
    import uuid
    import catalog_inject as CI
    P.LOGSDIR.mkdir(parents=True, exist_ok=True)
    bcp = P.LOGSDIR / ("seedbc-test-r1r1-%s.json" % uuid.uuid4().hex[:8])
    bc = json.loads((P.ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    for uid in P.GRAFTS:
        CI.graft_passive_ability(bc, uid, P.ABILITY)
    bcp.write_text(json.dumps(bc), encoding="utf-8")

    built = build_runner(seed=str(SEED), board=BOARD,
                         extra=["--rank", "17", "--no-ai", "--seed-bc", str(bcp),
                                "--p-units", ",".join(P.GRAFTS),
                                "--a-units", ",".join(FOES)])
    rid = int(built["rid"])

    def _rpc(sid, method, args, timeout=120):
        return rpc(method, args, timeout)

    sid = None
    bg = rpc("boardGraph", {"runnerId": rid}, 90)
    brd = Board(bg["tiles"], adjacency="native_sym")
    state, dv, _ob = P._port_state(sid, _rpc, rid, brd)
    yield {"rid": rid, "sid": sid, "rpc": _rpc, "board": brd, "state": state, "dv": dv}


def test_la_greffe_est_vue_par_le_collecteur(live):
    """ETAGE 3 -- `collect_triggered_abilities` doit instancier le passif GREFFE. C'est l'etage
    exact ou le premier jet echouait (0 instance), et l'echec y est SILENCIEUX."""
    trigs = collect_triggered_abilities(live["state"])
    ft = [t for t in trigs if isinstance(t, FullThrottlePassiveAbility)]
    carriers = P._carriers(live["dv"])
    assert carriers, "aucun porteur greffe dans decisionView -- montage KO"
    assert len(ft) == len(carriers), (
        "collect_triggered_abilities a instancie %d FullThrottlePassiveAbility pour %d porteur(s) "
        "greffe(s) -- le canal `unitAbilityStates` ne remonte pas jusqu'a "
        "`UnitContext.passive_abilities`" % (len(ft), len(carriers)))


@pytest.mark.parametrize("pas,attendu_steps,attendu_match", [(1, 2, False), (2, 3, True)])
def test_gate_sur_un_mouvement_reel(live, pas, attendu_steps, attendu_match):
    """ETAGES 1 + 4 -- sur une destination REELLEMENT legale au natif (`aiMovableTiles`), la loi
    `movementSteps = pas + 1` tient, et le gate bascule entre 1 et 2 pas.

    C'est la borne exacte que la mesure live a tranchee : le natif ne tue JAMAIS a 1 pas
    (0 / 15) et tue 30 % a 2 pas."""
    st, sid, rpc, rid = live["state"], live["sid"], live["rpc"], live["rid"]
    carriers = sorted(P._carriers(live["dv"]))
    tested = 0
    for uid in carriers:
        legal = P._legal_moves(sid, rpc, rid, uid)
        dest = P._pick_dest(st, uid, legal, pas)
        if dest is None:
            continue
        pc = st.get_entity(uid).get_component(PositionComponent)
        steps = _movement_steps(st, uid, (pc.col, pc.row), dest)
        assert steps == attendu_steps, (
            "u%s %s->%s : movement_steps=%d (attendu %d = path.Count)"
            % (uid, (pc.col, pc.row), dest, steps, attendu_steps))
        ev = TriggerEvent(int(EventTriggerType.UnitPositionChanged_1), uid, uid,
                          ranged=False, profile=None, movement_steps=steps)
        got = bool(FullThrottlePassiveAbility(owner_id=uid).matches(st, ev))
        assert got is attendu_match, (
            "u%s a %d pas : gate=%s (attendu %s)" % (uid, pas, got, attendu_match))
        tested += 1
    assert tested > 0, ("aucun porteur n'avait de destination legale a %d pas -- montage a revoir, "
                        "surtout PAS un skip vert" % pas)
