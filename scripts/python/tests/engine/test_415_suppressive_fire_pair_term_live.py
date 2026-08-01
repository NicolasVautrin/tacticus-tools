"""#415 — le terme `SUPPRESSIVEFIRE_TargetWithOverwatch` (+35) du `pairUtility`, confronte au NATIF.

`IdunBattle.AI.Playbook.Loki.SuppressiveFirePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
verse le poids `Utilities.Default.TriggeredAbilities.SUPPRESSIVEFIRE_TargetWithOverwatch` quand la
CIBLE porte l'effet `0x3f1` (= `EffectType.Overwatch_AutoAttack`, 1009) ET que la tuile d'attaque
n'est PAS adjacente a la cible (`!IBattleQuery.AreEntitiesAdjacent`, slot 0x60) — c'est le bonus du
TIR. Il entre dans la face ATTACK du dispatcher `TriggeredAbilitiesUtility(2)`, donc DANS le terme de
paire, ce qui le rend directement confrontable a l'oracle natif.

CE QUE CE TEST GARDE, sur les DEUX regimes que le corps natif separe :

  1. **CONFORMITE** — pour CHAQUE tuile testee, l'utilite de paire du port
     (`ComparablePlaybook.calculate_action_utility(...)["u"]`) egale celle du NATIF
     (RPC `pairUtility` = `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`,
     invoque DEPUIS LA MEME tuile via `col`/`row`). Aucune unite n'est deplacee : c'est le RPC qui
     porte la position, donc les deux cotes lisent le MEME etat.
  2. **DISCRIMINANCE** — le meme moteur, playbook 1044 RETIRE du registre
     (`engine.playbook.psyker.TRIGGERED_ATTACK_PLAYBOOKS`), DOIT diverger du natif d'EXACTEMENT le
     poids BC sur les tuiles NON adjacentes, et rester d'accord sur les tuiles adjacentes. Sans cette
     seconde assertion le test serait incapable d'echouer sur un port qui ignore le terme — et c'est
     exactement l'etat dans lequel il etait avant #415.

Le montage EXIGE les deux regimes (au moins une tuile adjacente et une non adjacente a la cible) :
s'il ne les obtient pas, il ECHOUE, il ne skippe pas (#268 — un skip sur un regime non atteint est un
vert qui ment).

Porteur du trait `SuppressiveFire` (UnitTrait 1010 -> triggered 1044) : `emperNoiseMarine`, HERO au
pool, voie directe. Cible portant l'overwatch : `eldarRanger` (trait `Overwatch`).
ASCII only. Probe jumeau : `scripts/python/probe_415_normal_attack_tie_order.py`.
"""
from __future__ import annotations

import pytest

import hexgeo
from engine import weights as W
from engine.entities.effect_type import EffectType
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.playbook import scene as _scene
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK
from engine.ai import context as _ai_ctx

BOARD = "MC1_67"
SEED = "41504"
CASTER = "emperNoiseMarine"        # trait SuppressiveFire (1010) -> triggered 1044
TARGET = "eldarRanger"             # trait Overwatch -> effet 1009 sur elle-meme
OVERWATCH = int(EffectType.Overwatch_AutoAttack)      # 1009 = le `0x3f1` du corps natif
EPS = 1e-4                         # Fix64 natif vs float du port


def _pair_native(rpc, rid, cid, tgt, ab, tile) -> float:
    r = rpc("pairUtility", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                            "abilityType": ab, "col": tile[0], "row": tile[1]}, 90)
    v = (r or {}).get("utility")
    assert isinstance(v, (int, float)), f"pairUtility natif indisponible pour {tile}: {r}"
    return float(v)


def _pair_port(ctx, ab, tgt, tile) -> float:
    cand = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, tgt, ab)
    assert cand is not None, f"le port ne produit AUCUNE action depuis {tile} sur {tgt}"
    return float(cand["u"])


@pytest.fixture(scope="module")
def sf_case(live_session, rpc, build_runner):
    """Monte UN runner, AMENE le caster au contact de la cible, et retient les tuiles des DEUX
    regimes (adjacente a la cible / a distance).

    Le drive est indispensable : l'oracle `pairUtility` REFUSE une tuile qui n'est ni la tuile
    courante ni dans le movable set (« tile (c,r) ni courante ni dans le movable set »), et au spawn
    les deux camps sont trop loin pour qu'une tuile ADJACENTE a la cible entre dans ce set. On
    DEPLACE donc les unites plutot que d'accuser la geometrie -- montage NOMME reutilise :
    `probe_124_line_elevation_decision._drive_to` (waypoints sur le graphe de mouvement natif)."""
    import probe_124_line_elevation_decision as P124
    rid = build_runner(SEED, ["--board", BOARD, "--p-units", CASTER, "--a-units", TARGET,
                              "--hp-target", "90000", "--hp-player", "90000"])["rid"]
    elev, walk, _tid = P124._board(live_session, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mine = [u for u in (dv.get("units") or []) if u.get("ctrl") and u.get("alive")]
    cid = next((u["id"] for u in mine if u.get("visualId") == CASTER), None)
    if cid is None:
        pytest.fail(f"montage NON INSTALLE : {CASTER} absent du roster", pytrace=False)
    myplayer = next((u.get("owner") for u in mine), None)
    tgt_u = next((u for u in (dv.get("units") or [])
                  if u.get("owner") != myplayer and u.get("alive")
                  and u.get("visualId") == TARGET), None)
    if tgt_u is None:
        pytest.fail(f"montage NON INSTALLE : {TARGET} absent du roster adverse", pytrace=False)
    tgt = tgt_u["id"]
    eff = [e.get("effectType") for e in (tgt_u.get("effects") or [])]
    if OVERWATCH not in eff:
        pytest.fail(f"montage NON INSTALLE : la cible {TARGET} ne porte pas l'overwatch "
                    f"({OVERWATCH}) -- effets publies {eff}", pytrace=False)

    # Couple de tuiles ADJACENTES walkables, le plus au centre possible : la cible sur l'une, le
    # caster sur l'autre. Le regime CONTACT devient alors la tuile COURANTE du caster, et les tuiles
    # DISTANTES sortent de son movable set -- les deux sont acceptees par `pairUtility`.
    cells = sorted(p for p, w in walk.items() if w and elev.get(p) is not None)
    if not cells:
        pytest.fail("montage NON INSTALLE : boardGraph sans tuile walkable", pytrace=False)
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    pair = None
    for p in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        nb = [q for q in hexgeo.neighbors(p[0], p[1])
              if walk.get(q) and elev.get(q) is not None and abs(elev[q] - elev[p]) < 2]
        if nb:
            pair = (p, nb[0])          # (tuile CIBLE, tuile CASTER adjacente)
            break
    if pair is None:
        pytest.fail("montage NON INSTALLE : aucune paire de tuiles adjacentes walkables",
                    pytrace=False)
    tpos, cpos = pair
    if not P124._drive_to(live_session, rid, walk, elev, {tgt: tpos, cid: cpos}):
        _dv, pos = P124._positions(live_session, rid)
        pytest.fail(f"montage NON INSTALLE : placement incomplet -- voulu {{{tgt}: {tpos}, "
                    f"{cid}: {cpos}}}, obtenu {{{tgt}: {pos.get(tgt)}, {cid}: {pos.get(cid)}}}",
                    pytrace=False)
    P124._give_turn_back(live_session, rid, myplayer)

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(rpc, rid)
    ctx = _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), predictor)
    ab = next((a for a in (ctx.normal_ids or ())), None)
    if ab is None:
        pytest.fail("montage NON INSTALLE : aucune attaque normale sur le caster", pytrace=False)

    # Tuiles ACCEPTEES par l'oracle = tuile courante + movable set = exactement `ctx.action_tiles`.
    tiles = [t for t in (ctx.action_tiles or []) if t and t[0] is not None]
    adj = sorted(t for t in tiles if hexgeo.distance(t, tpos) == 1)
    far = sorted(t for t in tiles if 2 <= hexgeo.distance(t, tpos) <= 3)
    if not adj or not far:
        pytest.fail(f"montage NON INSTALLE : les deux regimes ne sont pas atteints "
                    f"(adjacentes={adj} distantes={far[:5]}) -- le test ne discriminerait rien",
                    pytrace=False)
    return {"rid": rid, "cid": cid, "tgt": tgt, "tpos": tpos, "ab": ab, "ctx": ctx,
            "adj": adj[:2], "far": far[:3], "wt": ctx.wt}


def test_suppressive_fire_pair_term_matches_native(sf_case, rpc):
    """(1) CONFORMITE : port == natif sur les deux regimes, tuile par tuile."""
    c = sf_case
    for tile in c["adj"] + c["far"]:
        nat = _pair_native(rpc, c["rid"], c["cid"], c["tgt"], c["ab"], tile)
        port = _pair_port(c["ctx"], c["ab"], c["tgt"], tile)
        d = hexgeo.distance(tile, c["tpos"])
        assert abs(nat - port) < EPS, (
            f"pairUtility != natif depuis {tile} (dist {d} de la cible) : "
            f"natif={nat} port={port} ecart={port - nat}")


def test_suppressive_fire_term_is_load_bearing(sf_case, rpc):
    """(2) DISCRIMINANCE : playbook 1044 RETIRE du registre -> le port doit perdre EXACTEMENT le
    poids BC sur les tuiles NON adjacentes, et rester exact sur les adjacentes (le predicat natif
    est NIE : au contact, le terme ne tombe pas)."""
    import engine.playbook.psyker as PSY
    c = sf_case
    weight = float(c["wt"].triggered("SUPPRESSIVEFIRE_TargetWithOverwatch"))
    assert weight != 0, ("le BC courant ne porte pas SUPPRESSIVEFIRE_TargetWithOverwatch : "
                         "le regime ne discrimine rien")
    key = int(TriggeredAbilityType.SuppressiveFire)
    saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS.pop(key, None)
    assert saved is not None, "le playbook 1044 n'est PAS au registre -- rien a muter"
    try:
        for tile in c["far"]:
            nat = _pair_native(rpc, c["rid"], c["cid"], c["tgt"], c["ab"], tile)
            muted = _pair_port(c["ctx"], c["ab"], c["tgt"], tile)
            assert abs((muted + weight) - nat) < EPS, (
                f"[TIR] sans le playbook 1044, l'ecart au natif depuis {tile} devrait valoir "
                f"exactement le poids {weight} : natif={nat} port_mute={muted}")
        for tile in c["adj"]:
            nat = _pair_native(rpc, c["rid"], c["cid"], c["tgt"], c["ab"], tile)
            muted = _pair_port(c["ctx"], c["ab"], c["tgt"], tile)
            assert abs(muted - nat) < EPS, (
                f"[CONTACT] le terme ne doit PAS entrer au contact (predicat NIE) : depuis {tile} "
                f"le port mute devrait deja egaler le natif -- natif={nat} port_mute={muted}")
    finally:
        PSY.TRIGGERED_ATTACK_PLAYBOOKS[key] = saved
