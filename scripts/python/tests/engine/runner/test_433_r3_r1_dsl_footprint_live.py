"""#433-r3-r1 -- CONFRONTATION du noeud DSL `IsAdjacent` sur une EMPREINTE multi-hex.

CRITERE : « quand deux entites sont adjacentes par un pied AUTRE que la main tile, le noeud DSL
`IsAdjacent` du port dit-il ce que dit le natif ? »

LE MONTAGE DEGENERE, ET POURQUOI CELUI-CI NE L'EST PAS. A UN pied, `GetTiles(u) == [GetMainTile(u)]`
et les deux modeles (empreinte / main tile) coincident EXACTEMENT : toute mesure sur une unite
mono-tuile est donc INCAPABLE de les separer. Il faut une unite MULTI-HEX **et** une geometrie ou
l'adjacence passe par un pied non-ancre. Ce fichier monte les deux :

  * PORTEUR MULTI-HEX -- `ultraDreadnought` (MoW du pool) caste `DutyEternal` (1158) et fait
    apparaitre `ultraSmnDreadnought` (Galatian) sur **3 tuiles** (#R30/#91). C'est le seul porteur
    multi-hex confrontable du build, et le montage est celui de `test_multihex_dutyeternal_live.py`
    -- dont ce fichier IMPORTE les helpers plutot que de les recopier (`_pick_anchor` porte le
    CRITERE de discriminance ; le forker, c'est forker le critere).
  * GEOMETRIE STRICTE -- `_pick_anchor` place l'attaquant a distance **1 d'un pied** et **>= 2 de
    `feet[0]` (la main tile reelle) ET de `feet[-1]` (ce que rend `decisionView.units[].pos`).
    Quel que soit le pied qu'un port mono-tuile retienne, il conclut « pas adjacent » la ou le natif
    conclut « adjacent ».
  * CONSOMMATEUR OBSERVABLE -- `custoKyrus` (pool) porte `VigilanceEternal` (1202), dont l'etage
    MOVE est `If(Not(IsAdjacent(Caster, Target)), MoveUnit(Caster, dest))`
    (`IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$ExecuteBehaviour`).
    Le verdict du noeud est donc DIRECTEMENT observable : le caster BOUGE (« pas adjacent ») ou
    NE BOUGE PAS (« adjacent »). `initialCooldownTurns = 0` -> castable sans faire tourner de tour
    de plus que ce que la MoW impose deja.

ORACLE : la POSITION du caster apres le cast NATIF. Le port corrige doit dire `IsAdjacent = True`
(pas de move) ; le port d'AVANT (collapse main tile) disait `False` (move). La contre-epreuve
`test_main_tile_collapse_flips_the_verdict` REJOUE le collapse d'avant sur le MEME etat et verifie
que le verdict BASCULE -- une correction qui ne mordrait pas se dirait.

Aucun hook neuf : `decisionView`, `observeBattle`, `boardGraph`, `applyAction`, `aiMovableTiles`.
ASCII only.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import hexgeo
import pytest

from engine.dsl import nodes as dsl
from engine.dsl.base import _pos
from engine.entities.triggers import IsAdjacent
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.runner.components import get_unit_feet
from engine.runner.snapshot import load_state
from engine.services import spawn_tile_shape as STS

MOW = "ultraDreadnought"
SUMMON = "ultraSmnDreadnought"
ATTACKER = "custoKyrus"
DUTY_ETERNAL = 1158
VIGILANCE_ETERNAL = 1202
MAX_ROUNDS = 8
BOARD = "MC1_67"


def _harness():
    """Helpers du montage multi-hex, IMPORTES depuis `test_multihex_dutyeternal_live.py`.

    Les repertoires de tests n'ont pas d'`__init__.py` (aucun test n'en importe un autre), d'ou le
    chargement par chemin explicite. Ce qu'on prend : `_ammo_seed_bc` (munitions de MoW),
    `_board`/`_occupants` (canaux), et surtout `_pick_anchor` -- le CRITERE de discriminance."""
    src = Path(__file__).with_name("test_multihex_dutyeternal_live.py")
    spec = importlib.util.spec_from_file_location("_multihex_harness", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def footprint_case(rpc, build_runner):
    """Monte le regime discriminant et joue le cast NATIF de `VigilanceEternal` dessus."""
    H = _harness()
    bc = H._ammo_seed_bc()
    # MoW cote ADVERSE -> le Galatian nait dans l'equipe adverse, donc `custoKyrus` (a moi) peut le
    # CIBLER et je garde la main totale sur ses deplacements.
    rid = build_runner("777", board=BOARD,
                       extra=["--seed-bc", str(bc), "--a-mow", MOW, "--no-ai",
                              "--p-units", f"{ATTACKER},ultraTitus",
                              "--a-units", "necroWarden,necroSpyder"])["rid"]

    view = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    mows = [m for m in (view.get("mows") or []) if m.get("visualId") == MOW]
    if not mows:
        pytest.fail(f"{MOW} absent de decisionView.mows -- la MoW n'est pas deployee", pytrace=False)
    caster_mow = mows[0]["casterId"]

    board = H._board(rpc, rid)
    occupied = set(H._occupants(rpc, rid))
    attacker = next((u for u in (view.get("units") or [])
                     if u.get("visualId") == ATTACKER and u.get("ctrl") and u.get("alive")), None)
    if attacker is None:
        pytest.fail(f"{ATTACKER} absent du roster controle", pytrace=False)
    here = (attacker["pos"]["col"], attacker["pos"]["row"])
    mv = rpc("aiMovableTiles", {"runnerId": rid}) or {}
    reach = [here] + [(t["col"], t["row"]) for e in (mv.get("units") or [])
                      if e.get("unitId") == attacker["id"] for t in (e.get("tiles") or [])]
    anchor, predicted, post, strict = H._pick_anchor(board, occupied, reach)
    if anchor is None:
        pytest.fail("aucune ancre ne porte d'aire 3-tuiles valide sur ce board", pytrace=False)
    if post is not None and post != here:
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": attacker["id"], "to": {"col": post[0], "row": post[1]}}})
        acts = r.get("actions") or []
        if not (acts and acts[0].get("ok") and acts[0].get("mutated")):
            pytest.fail(f"deplacement de l'attaquant vers {post} refuse : {json.dumps(r)[:300]}",
                        pytrace=False)

    # DutyEternal : `initialCooldownTurns = 2` + il faut le TOUR du proprietaire de la MoW, sinon
    # `applyAction` rend un REFUS SILENCIEUX (`mutated: false, spawned: 0`).
    owner = mows[0].get("owner")
    for _ in range(2 * MAX_ROUNDS):
        v = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
        ab = next((a for a in (v["mows"][0].get("abilities") or [])
                   if a.get("id") == DUTY_ETERNAL), None)
        if ab is None:
            pytest.fail("DutyEternal (1158) absente des abilities de la MoW", pytrace=False)
        if ab.get("usable") and ab.get("hasAmmo", True) and not (ab.get("cooldown") or 0) \
                and (owner is None or v.get("currentPlayer") == owner):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}})
    else:
        pytest.fail(f"1158 jamais castable apres {2 * MAX_ROUNDS} fins de tour", pytrace=False)

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_mow, "abilityType": DUTY_ETERNAL,
        "to": {"col": anchor[0], "row": anchor[1]}}})
    a0 = (res.get("actions") or [{}])[0]
    if not (res.get("ok") and a0.get("ok") and a0.get("mutated") and a0.get("spawned")):
        pytest.fail(f"cast 1158 sans effet en {anchor} : {json.dumps(res)[:400]}", pytrace=False)

    after = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    summon = next((u for u in (after.get("units") or []) if u.get("visualId") == SUMMON), None)
    if summon is None:
        pytest.fail(f"{SUMMON} absent apres le cast de 1158", pytrace=False)

    # GATE `toActivate` -- et ce n'est PAS `currentPlayer`. L'attaquant a deja depense son
    # activation pour rejoindre le poste d'observation ; un cast hors activation est refuse EN
    # SILENCE (`ok: true, mutated: false, actionConsumed: false`), signature IDENTIQUE au « le natif
    # a juge adjacent et n'a donc rien deplace » qu'on veut mesurer. MESURE : sans cette gate le
    # cast 1202 rendait exactement cela, avec pourtant `casterReason = NoBrokenTargetingRule`
    # (le filtre STATIQUE de ciblage ne voit pas l'activation). On fait donc tourner les tours
    # jusqu'a ce que l'attaquant soit RE-ACTIVABLE.
    my_player = attacker.get("player")
    for _ in range(4 * MAX_ROUNDS):
        v = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
        if attacker["id"] in (v.get("toActivate") or []):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}})
    else:
        pytest.fail(f"{ATTACKER} jamais re-activable apres {4 * MAX_ROUNDS} fins de tour",
                    pytrace=False)

    # ETAT PRE-CAST : c'est LUI que le port rejoue (les deux faces lisent le meme etat).
    pre_dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    pre_ob = rpc("observeBattle", {"runnerId": rid})
    pre_state = load_state(pre_dv, pre_ob, board=board)
    att_before = next((u for u in (pre_dv.get("units") or []) if u.get("id") == attacker["id"]), None)
    pos_before = (att_before["pos"]["col"], att_before["pos"]["row"]) if att_before else None

    # DIAGNOSTIC du refus silencieux (`ok: true, mutated: false`) : le verdict natif de ciblage et
    # l'etat de l'ability, capturees AVANT le cast -- sans elles un refus ne se distingue pas d'un
    # « le natif a juge adjacent et n'a rien fait ».
    reason = rpc("abilityReason", {"runnerId": rid, "casterId": attacker["id"],
                                   "abilityType": VIGILANCE_ETERNAL, "targetId": summon["id"]})
    ab_state = next((a for a in ((att_before or {}).get("abilities") or [])
                     if a.get("id") == VIGILANCE_ETERNAL), None)

    cast = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": attacker["id"], "abilityType": VIGILANCE_ETERNAL,
        "targetId": summon["id"]}})
    c0 = (cast.get("actions") or [{}])[0]
    post_dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    att_after = next((u for u in (post_dv.get("units") or []) if u.get("id") == attacker["id"]), None)
    pos_after = (att_after["pos"]["col"], att_after["pos"]["row"]) if att_after else None

    return {"rid": rid, "board": board, "anchor": anchor, "predicted": predicted,
            "attacker_id": attacker["id"], "attacker_pos": pos_before, "strict": strict,
            "summon_id": summon["id"], "pre_state": pre_state,
            "cast": cast, "cast_ok": bool(cast.get("ok") and c0.get("ok") and c0.get("mutated")),
            "reason": reason, "ab_state": ab_state,
            "current_player": pre_dv.get("currentPlayer"), "my_player": my_player,
            "pos_before": pos_before, "pos_after": pos_after}


def _ctx(case):
    """`AbilityEntities` du cast : caster = l'attaquant, target = le Galatian (mirror natif)."""
    return entities_from_state(case["pre_state"], case["attacker_id"], case["summon_id"])


def test_regime_is_strictly_discriminant(footprint_case):
    """Le montage SEPARE les deux modeles -- sinon toute la suite ne prouve rien.

    Exigences, verifiees et non supposees : la cible a **3 pieds**, l'attaquant est a distance **1**
    d'au moins un pied, et a distance **>= 2** de `feet[0]` (`EntityExtensions$$GetMainTileId`)."""
    case = footprint_case
    feet = get_unit_feet(case["pre_state"], case["summon_id"])
    assert len(feet) == 3, f"cible non multi-hex : feet={feet} -- montage DEGENERE"
    att = case["attacker_pos"]
    dists = [hexgeo.distance(f, att) for f in feet]
    assert min(dists) == 1, f"attaquant non adjacent a un pied : {dists} depuis {att}, feet={feet}"
    assert dists[0] >= 2, (f"attaquant adjacent a la MAIN TILE {feet[0]} (d={dists[0]}) -- "
                           f"montage DEGENERE, les deux modeles coincident")


def test_port_node_is_adjacent_on_the_footprint(footprint_case):
    """Le noeud DSL du port dit ADJACENT -- mirror de
    `AreTilesAdjacent(GetTiles(caster), GetTiles(target))`, la surcharge ENTITE/ENTITE de
    `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent`."""
    assert IsAdjacent(dsl.Caster(), dsl.Target()).should_trigger(_ctx(footprint_case)) is True


def test_main_tile_collapse_flips_the_verdict(footprint_case, monkeypatch):
    """CONTRE-EPREUVE : le collapse main tile d'AVANT (#433-r3-r1) rend FAUX sur ce meme etat.

    On remplace `_feet` par le collapse `[_pos(u)]` -- exactement ce que faisait le port -- et le
    verdict BASCULE. Une correction qui ne mordrait pas se dirait ici."""
    import engine.entities.triggers as T

    def _main_tile_only(u):
        p = _pos(u)
        return [] if p is None else [p]

    monkeypatch.setattr(T, "_feet", _main_tile_only)
    assert IsAdjacent(dsl.Caster(), dsl.Target()).should_trigger(_ctx(footprint_case)) is False


def test_native_does_not_move_the_caster(footprint_case):
    """ORACLE NATIF : `VigilanceEternal` = `If(Not(IsAdjacent(Caster, Target)), MoveUnit(...))`.

    Le natif ne DEPLACE PAS le caster -> il a juge les deux entites ADJACENTES, par un pied qui
    n'est pas la main tile. C'est l'accord avec le port corrige, et le desaccord avec le port
    d'avant (qui aurait deplace)."""
    case = footprint_case
    if not case["cast_ok"]:
        pytest.fail("cast 1202 sans effet (refus SILENCIEUX). "
                    f"abilityReason={json.dumps(case['reason'])[:200]} "
                    f"ability={json.dumps(case['ab_state'])[:300]} "
                    f"currentPlayer={case['current_player']} myPlayer={case['my_player']} "
                    f"reponse={json.dumps(case['cast'])[:900]}", pytrace=False)
    assert case["pos_after"] == case["pos_before"], (
        f"le natif a DEPLACE le caster {case['pos_before']} -> {case['pos_after']} : il a donc juge "
        f"NON adjacent, ce qui contredit le modele d'empreinte")
