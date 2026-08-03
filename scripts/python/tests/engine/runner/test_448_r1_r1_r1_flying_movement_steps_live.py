"""GARDE LIVE #448-r1-r1-r1 -- la branche VOLANTE de `_movement_steps`, sur un etat REEL.

Le test offline garde la LOI sur un board synthetique. Il ne garde PAS que la chaine tienne
sur une vraie bataille : que le trait `Flying` remonte bien jusqu'a `UnitContext.traits` (donc
que la branche soit REELLEMENT prise), que les destinations exercees soient celles que le natif
accepte (`aiMovableTiles`), et que la greffe soit vue par le collecteur.

Les assertions sont DETERMINISTES : on n'exerce pas le tirage `Maybe(chance = 30)` -- c'est le
probe qui en mesure la frequence (`probe_448_r1_r1_r1_flying_movement_steps.py`). On exerce la
VALEUR de `movementSteps` et la bascule du gate.

MESURE qui justifie la garde (natif, greffe sur 5 volants du pool, board MC1_67, seed 777) :

    M2  MARCHEUR d=2 -> 3 / 8  morts (37.5 %)      V2  VOLANT d=2 -> 0 / 20 morts (0.0 %)
    V3  VOLANT   d=3 -> 4 / 13 morts (30.8 %)      VD  VOLANT d=2 detourne -> 0 / 14 (0.0 %)

Le port SANS la branche volante rend 33.5 % sur V2 -- il tuerait la ou le natif ne tue pas.
Detail : `docs/rl/case-448-r1-r1-r1-flying-movement-steps.md`. ASCII only.
"""
from __future__ import annotations

import pytest

import hexgeo
import probe_448_r1_r1_r1_flying_movement_steps as P
from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.pathfinding.board import Board
from engine.entities.pathfinding.fly_pathfinder import is_like_flying
from engine.runner.components import PositionComponent, StatsComponent
from engine.runner.operations.movement import _movement_steps, _num_tiles_moved
from engine.runner.operations.triggers.base import TriggerEvent
from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
from engine.runner.operations.triggers.loki.full_throttle import FullThrottlePassiveAbility

BOARD, SEED = "MC1_67", 777
FOES = ["tauCrisis"]


@pytest.fixture(scope="module")
def live(rpc, build_runner):
    """Un runner dont les 5 unites joueur sont VOLANTES et portent la greffe `FullThrottle`.

    Fixtures du harnais (`rpc` / `build_runner`) : elles isolent le state-file par PID et
    LIBERENT le runner au teardown. Montage KO => ECHEC, jamais skip (#455)."""
    import json
    import uuid
    import catalog_inject as CI
    P.LOGSDIR.mkdir(parents=True, exist_ok=True)
    bcp = P.LOGSDIR / ("seedbc-test-r1r1r1-%s.json" % uuid.uuid4().hex[:8])
    bc = json.loads((P.ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    for uid in P.FLY_GRAFTS:
        CI.graft_passive_ability(bc, uid, P.ABILITY)
    bcp.write_text(json.dumps(bc), encoding="utf-8")

    built = build_runner(seed=str(SEED), board=BOARD,
                         extra=["--rank", "17", "--no-ai", "--seed-bc", str(bcp),
                                "--p-units", ",".join(P.FLY_GRAFTS),
                                "--a-units", ",".join(FOES)])
    rid = int(built["rid"])

    def _rpc(sid, method, args, timeout=120):
        return rpc(method, args, timeout)

    bg = rpc("boardGraph", {"runnerId": rid}, 90)
    brd = Board(bg["tiles"], adjacency="native_sym")
    state, dv, _ob = P._port_state(None, _rpc, rid, brd)
    yield {"rid": rid, "sid": None, "rpc": _rpc, "board": brd, "state": state, "dv": dv}


def _carriers(live):
    return sorted(P._carriers(live["dv"], P.FLY_GRAFTS))


def test_les_porteurs_sont_bien_volants(live):
    """MONTAGE, et c'est la premiere chose qui peut casser en silence : si `Flying` n'arrivait
    pas jusqu'a `UnitContext.traits`, tout le fichier exercerait la branche MARCHEUSE en
    croyant mesurer la volante -- et passerait au vert."""
    st = live["state"]
    carriers = _carriers(live)
    assert carriers, "aucun porteur greffe dans decisionView -- montage KO"
    for uid in carriers:
        sc = st.get_entity(uid).get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        assert is_like_flying(traits or []), "u%s n'est pas IsLikeFlying (traits=%s)" % (uid,
                                                                                        traits)


def test_la_greffe_est_vue_par_le_collecteur(live):
    """Meme etage que #448-r1-r1 : `collect_triggered_abilities` doit instancier le passif
    GREFFE, sinon la mecanique est INERTE sans la moindre erreur."""
    trigs = collect_triggered_abilities(live["state"])
    ft = [t for t in trigs if isinstance(t, FullThrottlePassiveAbility)]
    carriers = _carriers(live)
    assert len(ft) == len(carriers), (
        "collect_triggered_abilities a instancie %d FullThrottlePassiveAbility pour %d "
        "porteur(s) greffe(s)" % (len(ft), len(carriers)))


@pytest.mark.parametrize("d,attendu_match", [(2, False), (3, True)])
def test_gate_volant_bascule_a_3_hexes(live, d, attendu_match):
    """Sur une destination REELLEMENT legale au natif, `movementSteps` d'un VOLANT vaut la
    DISTANCE -- donc le gate `>= 3` bascule entre 2 et 3 hexes, un cran PLUS LOIN que pour un
    marcheur (qui bascule des 2 pas, cf. #448-r1-r1)."""
    st, rpc_, rid, brd = live["state"], live["rpc"], live["rid"], live["board"]
    tested = 0
    for uid in _carriers(live):
        legal = P._legal_moves(live["sid"], rpc_, rid, uid)
        got = P._pick(st, brd, uid, legal, "fly", d)
        if got is None:
            continue
        dest, _info = got
        pc = st.get_entity(uid).get_component(PositionComponent)
        src = (pc.col, pc.row)
        steps = _movement_steps(st, uid, src, dest)
        assert steps == d == hexgeo.distance(src, dest), (
            "u%s %s->%s : movement_steps=%d (attendu la DISTANCE %d)" % (uid, src, dest, steps, d))
        ev = TriggerEvent(int(EventTriggerType.UnitPositionChanged_1), uid, uid,
                          ranged=False, profile=None, movement_steps=steps)
        assert bool(FullThrottlePassiveAbility(owner_id=uid).matches(st, ev)) is attendu_match
        tested += 1
    assert tested > 0, ("aucun porteur n'avait de destination legale a d=%d -- montage a revoir, "
                        "surtout PAS un skip vert" % d)


def test_asymetrie_volant_marcheur_sur_le_meme_trajet(live):
    """LE COUPLE, sur l'etat live : MEME unite, MEME depart, MEME arrivee -- on ne change QUE
    le regime (on retire `Flying` de ses traits). Les deux branches doivent rendre des choses
    DIFFERENTES, chacune selon SA loi :

        volant   = `GetDistance(first, last)`  = la distance hex
        marcheur = `path.Count`                = pas de MARCHE + 1

    ⚠ L'ecart n'est PAS constant, et c'est le fond de l'asymetrie : il vaut
    `pas_de_marche + 1 - distance`, donc **1 seulement si le chemin de marche est direct**.
    MESURE sur ce montage : `u83 (1,1)->(1,3)` est a `d = 2` mais coute **3 pas de marche**
    (relief de MC1_67) -> volant 2, marcheur 4, ecart **2**. Un test qui exigerait « exactement
    1 » confondrait l'asymetrie avec une constante -- il est tombe la-dessus au premier jet.

    C'est la contre-epreuve du port : si la branche volante disparaissait, les deux lectures
    seraient EGALES et l'assertion de stricte inegalite tomberait."""
    st, rpc_, rid, brd = live["state"], live["rpc"], live["rid"], live["board"]
    tested = 0
    for uid in _carriers(live):
        legal = P._legal_moves(live["sid"], rpc_, rid, uid)
        got = P._pick(st, brd, uid, legal, "fly", 2)
        if got is None:
            continue
        dest, _info = got
        pc = st.get_entity(uid).get_component(PositionComponent)
        src = (pc.col, pc.row)
        sc = st.get_entity(uid).get_component(StatsComponent)
        avant = list(getattr(sc.ctx, "traits", None) or [])
        fly = _movement_steps(st, uid, src, dest)
        try:
            sc.ctx.traits = [t for t in avant if t not in ("Flying", "Burrow")]
            walk = _movement_steps(st, uid, src, dest)
            pas = _num_tiles_moved(st, uid, src, dest)
        finally:
            sc.ctx.traits = avant
        assert fly == hexgeo.distance(src, dest) == 2, (
            "u%s %s->%s : volant=%d -- la branche volante ne rend pas la distance"
            % (uid, src, dest, fly))
        assert walk == pas + 1, (
            "u%s %s->%s : marcheur=%d pour %d pas -- `path.Count` n'est plus `pas + 1`"
            % (uid, src, dest, walk, pas))
        assert walk > fly, (
            "u%s %s->%s : volant=%d marcheur=%d -- l'asymetrie du ternaire natif a disparu"
            % (uid, src, dest, fly, walk))
        tested += 1
    assert tested > 0, "aucun porteur n'avait de destination legale a d=2 -- montage a revoir"
