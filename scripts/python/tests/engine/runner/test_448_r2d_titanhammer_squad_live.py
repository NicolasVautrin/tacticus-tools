"""GARDE LIVE #448-r2d -- `1573 TitanhammerSquad_TeleportingIn` et son vslot 0x748, port contre
NATIF, sur le MEME etat de depart.

LE MONTAGE, et pourquoi il est INDISPENSABLE : `1571 TitanhammerSquad_TargetTile` -- le substrat de
`IdunBattle.Entities.Effects.Loki.TitanhammerSquad_TeleportingInEffect$$GetCustomMovingEffectCondition`
-- n'est pose par PERSONNE cote port (son poseur est l'ACTIVE `1231`, non portee). Sans montage, la
condition serait donc confrontee sur une entree VIDE, rendrait `False` partout, et la garde serait
VERTE SANS RIEN MESURER. On fait donc poser le substrat par le NATIF :

    astarLysander (seul porteur de 1231, HERO HORS POOL) injecte au catalogue
      -> il CASTE 1231 sur une tuile choisie
      -> le natif pose 1571 sur cette tuile et 1573 sur les allies `TerminatorArmour` a portee
      -> l'etat du port est RECHARGE depuis le natif (`tileMeta` INCLUS -- seul canal des effets
         de TUILE, cf. `snapshot._load_tile_effects`)
      -> DEUX pas depuis cet etat : un loin de la marque, un DESSUS.

CE QUI REGRESSERAIT SANS CETTE GARDE : un port qui inscrit 1573 au registre SANS lire le vslot
0x748 (donc en le collapsant a `True`, comme ses trois soeurs) poserait `1574` a CHAQUE pas de son
porteur. Aucune erreur, aucun crash -- juste un marqueur pose ou le natif n'en pose pas. C'est
exactement ce que la contre-epreuve `--mutate` du probe rend rouge.

Mesure complete (2 couples board/seed + contre-epreuve) :
`python scripts/python/probe_448_r2d_titanhammer_squad.py`. ASCII only.
"""
from __future__ import annotations

import uuid

import pytest

import catalog_inject
import probe_448_r2d_titanhammer_squad as P
from engine.entities.pathfinding.board import Board
from engine.runner.components import UnitComponent, get_unit_feet
from engine.runner.events import EventBus
from engine.runner.operations.movement import MoveUnitOperation
from engine.runner.operations.triggers import after_move_triggers
from engine.runner.snapshot import load_state


def _capture(rpc, rid) -> dict:
    return {"dec": rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150),
            "ob": rpc("observeBattle", {"runnerId": rid}, 60),
            "snap": rpc("combatSnapshot", {"runnerId": rid}, 90),
            "tm": rpc("tileMeta", {"runnerId": rid}, 90),
            "bg": rpc("boardGraph", {"runnerId": rid}, 90)}


def _state(cap):
    board = Board(cap["bg"]["tiles"], adjacency="evenq")
    return load_state(cap["dec"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"]), board


def _find(st, vis):
    for uid, e in st.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and str(uc.visual_id) == vis:
            return int(uid)
    return None


def _types(st, uid) -> list:
    return sorted(int(getattr(x, "effect_type", -1))
                  for x in (st.effects.by_unit.get(int(uid)) or []) if not x.consumed)


@pytest.fixture(scope="module")
def stage(rpc, build_runner):
    """UN runner, l'injection catalogue et le CAST -- puis l'etat est fige pour les deux bras.
    ⚠ Montage non installe => ECHEC, jamais skip (#268) : un skip vert dirait « rien a valider »."""
    # Le repertoire de SORTIE est celui du probe (`P.LOGS`, sous `logs/` = gitignore, #349) : un
    # seul calcul de racine, pas deux -- une racine recalculee ici a DEJA pointe une marche trop
    # bas (`scripts/logs/`), ce que `probe_273 --only-scan` a attrape.
    P.LOGS.mkdir(parents=True, exist_ok=True)
    bc = P.LOGS / ("seedbc-test-%s.json" % uuid.uuid4().hex[:8])
    catalog_inject.write_augmented_seed_bc(str(bc), [P.CASTER])
    try:
        rid = build_runner(seed="777", board="MC1_67",
                           extra=["--rank", "17", "--no-ai", "--seed-bc", str(bc),
                                  "--p-units", P.P_UNITS, "--a-units", P.A_UNITS])["rid"]
    finally:
        bc.unlink(missing_ok=True)

    st, board = _state(_capture(rpc, rid))
    caster, on_mover, far_mover = (_find(st, P.CASTER), _find(st, P.ON_MOVER),
                                   _find(st, P.FAR_MOVER))
    if caster is None or on_mover is None or far_mover is None:
        pytest.fail("MONTAGE : %s/%s/%s non deployes (%r/%r/%r) -- l'injection catalogue de "
                    "#270-d a-t-elle change ?" % (P.CASTER, P.ON_MOVER, P.FAR_MOVER,
                                                  caster, on_mover, far_mover))

    # La CIBLE : une tuile LEGALE (`fromHere` -- un cast hors domaine est un NO-OP SILENCIEUX),
    # la PLUS LOIN possible du mover « far », pour qu'un pas de MARCHE existe qui n'approche ni la
    # marque ni ses voisines.
    ab = rpc("abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": P.ABILITY}, 150)
    tiles = [(t["tile"]["col"], t["tile"]["row"]) for u in (ab.get("units") or [])
             for a in (u.get("abilities") or []) for t in (a.get("fromHere") or [])
             if t.get("kind") == "tile"]
    if not tiles:
        pytest.fail("MONTAGE : %d n'a aucune tuile-cible `fromHere`" % P.ABILITY)
    fpos = next(iter(get_unit_feet(st, far_mover)), None)
    target = max(tiles, key=lambda t: P._hex_dist(board, t, fpos))
    r = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster, "to": {"col": target[0], "row": target[1]},
        "abilityType": P.ABILITY}}, 150) or {}
    if not ((r.get("actions") or [{}])[0].get("ok")):
        pytest.fail("MONTAGE : le cast de %d a ECHOUE : %r" % (P.ABILITY, r))
    return {"rid": rid, "caster": caster, "on_mover": on_mover, "far_mover": far_mover,
            "board": board, "target": tuple(target)}


def test_the_cast_installs_the_substrate_of_the_0x748_vslot(rpc, stage):
    """PRE-CONDITION, et c'est une MESURE : sans elle les deux bras ne discrimineraient RIEN (une
    condition sur une entree vide est fausse partout, et le port aurait l'air juste)."""
    st, board = _state(_capture(rpc, stage["rid"]))
    marks = P.marked_tiles(st, board, stage["caster"])
    assert marks == [stage["target"]], (
        "tuiles marquees %r != [%r] -- le substrat de la condition n'est pas celui qu'on croit"
        % (marks, stage["target"]))
    for uid in (stage["caster"], stage["on_mover"], stage["far_mover"]):
        assert P.TELEPORTING_IN in _types(st, uid), (
            "u%d ne porte pas 1573 apres le cast : %r" % (uid, _types(st, uid)))
        src = next(int(e.source) for e in st.effects.by_unit[uid]
                   if not e.consumed and int(e.effect_type) == P.TELEPORTING_IN
                   and e.source is not None)
        assert src == stage["caster"], "source de 1573 sur u%d = %r" % (uid, src)


def test_a_walk_far_from_the_mark_poses_no_moving_marker(rpc, stage):
    """LE BRAS NEGATIF. Il PASSE d'abord : il laisse la marque LIBRE pour le bras suivant."""
    rid, mover, board = stage["rid"], stage["far_mover"], stage["board"]
    tgt_id = board.id_at(stage["target"][0], stage["target"][1])
    near = {board.coord(t) for t in board.neighbours_native(tgt_id)} | {stage["target"]}
    mv = rpc("aiMovableTiles", {"runnerId": rid}, 120) or {}
    pool = sorted({(t.get("col"), t.get("row")) for u in (mv.get("units") or [])
                   if int(u.get("unitId")) == mover for t in (u.get("tiles") or [])})
    dest = next((t for t in pool if t not in near), None)
    if dest is None:
        pytest.fail("MONTAGE : aucune tuile du pool natif hors de la zone marquee (pool=%r)" % pool)

    st, _b = _state(_capture(rpc, rid))
    MoveUnitOperation(mover, tuple(dest)).execute(st, EventBus())
    mid = _types(st, mover)
    after_move_triggers(st, mover)
    assert P.MOVING not in mid, (
        "le port pose 1574 sur un pas LOIN de la marque : le vslot 0x748 est collapse a True (%r)"
        % (mid,))

    r = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": mover, "to": {"col": int(dest[0]), "row": int(dest[1])}}}, 120) or {}
    assert (r.get("actions") or [{}])[0].get("mutated") is True, \
        "le move live n'a RIEN mute (montage, H55) : %r" % (r,)
    live = P.moving_marker_live(P.cascade(r), mover)
    assert not live["received"], "le natif POSE 1574 loin de la marque : %r" % (live,)
    st2, _b2 = _state(_capture(rpc, rid))
    assert P.TELEPORTING_IN not in _types(st2, mover), "le natif GARDE 1573 apres le pas (T1)"
    assert P.TELEPORTING_IN not in _types(st, mover), "le port GARDE 1573 apres le pas (T1)"


def test_a_teleport_onto_the_mark_poses_the_moving_marker(rpc, stage):
    """LE BRAS POSITIF (`Contains`). Le pas est DECOUPE cote port pour observer le marqueur
    TRANSITOIRE que la cascade native montre elle aussi (`ActivateEffect`/`ReceiveEffect
    TitanhammerSquad_Moving` AVANT `ChangePosition`, puis `LoseEffect` apres)."""
    rid, mover = stage["rid"], stage["on_mover"]
    dest = stage["target"]
    mv = rpc("aiMovableTiles", {"runnerId": rid}, 120) or {}
    pool = {(t.get("col"), t.get("row")) for u in (mv.get("units") or [])
            if int(u.get("unitId")) == mover for t in (u.get("tiles") or [])}
    if dest not in pool:
        pytest.fail("MONTAGE : la tuile marquee %r n'est pas dans le pool de u%d (%r) -- "
                    "le decorateur ATeleportPathfinder devrait l'y mettre"
                    % (dest, mover, sorted(pool)))

    st, _b = _state(_capture(rpc, rid))
    MoveUnitOperation(mover, tuple(dest)).execute(st, EventBus())
    mid = _types(st, mover)
    assert P.MOVING in mid, "T4 n'a pas pose 1574 pendant le pas : %r" % (mid,)
    assert P.TELEPORTING_IN in mid, "1573 deja retire pendant le pas : T1 fire trop tot"
    after_move_triggers(st, mover)
    end = _types(st, mover)
    assert P.MOVING not in end, "1574 SURVIT au pas cote port (TeleportMovingEffect non retire)"
    assert P.TELEPORTING_IN not in end, "1573 SURVIT au pas cote port (T1 n'a pas retire)"

    r = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": mover, "to": {"col": int(dest[0]), "row": int(dest[1])}}}, 120) or {}
    assert (r.get("actions") or [{}])[0].get("mutated") is True, \
        "le move live n'a RIEN mute (montage, H55) : %r" % (r,)
    live = P.moving_marker_live(P.cascade(r), mover)
    assert live["received"], "le natif ne pose PAS 1574 SUR la marque -- mesure vide : %r" % (live,)
    # `turns: Nullable<int>(1)` -- deja en TOURS. Un `TurnsFromRounds(1)` vaudrait 2 a deux joueurs.
    assert [int(t.get("Effect_RemainingTurns")) for t in live["received"]] == [1], live
    assert [int(t.get("Effect_SourceActiveAbility")) for t in live["received"]] == [P.ABILITY], live
    assert live["lost"], "le natif garde 1574 apres le pas (TeleportMovingEffect n'a pas retire)"
    st2, _b2 = _state(_capture(rpc, rid))
    assert P.MOVING not in _types(st2, mover)
    assert P.TELEPORTING_IN not in _types(st2, mover)
    assert get_unit_feet(st, mover) == get_unit_feet(st2, mover) == [tuple(dest)]
