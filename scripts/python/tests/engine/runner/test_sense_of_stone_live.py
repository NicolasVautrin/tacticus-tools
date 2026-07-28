"""#192 `SereneUnifierSenseOfStone` (EffectType 0x491 = 1169) — GARDE d'agrement live.

CE QUE CES TESTS VERROUILLENT, et pourquoi ce decoupage :

`IdunBattle.Entities.Effects.Loki.SereneUnifierSenseOfStoneEffect$$CreateEffectDamageMalusForDefense`
= `EffectBonus.ForPercentDecrease(get_OwnerIsTarget, ConfigVar(0x46 = dmgReductionPct))` — trigger
`get_OwnerIsTarget` **SEUL**, donc **AUCUN gate** : ni melee/ranged, ni profil de degat, ni
normal-vs-ability. Un port qui ajouterait un gate (ou qui manquerait la classe : c'etait l'etat
d'avant, `BaseEffect` nu) rend un degat FAUX **sans jamais lever d'erreur**. Les deux vecteurs sont
donc testes separement — MELEE et RANGED — parce que c'est exactement l'axe sur lequel un gate
introduit par erreur (calque de `Terrifying_ExtraDefense` / `OverwhelmingWrath_RangeDmgReduction`,
tous deux gates dans le meme fichier) se verrait.

MONTAGE (positions DRIVEES, `applyAction` ignore la propriete) : le porteur `tauAunShi` est place
ADJACENT a la cible AVANT le `endturn` qui demarre le tour de son equipe -- c'est ce turn-start qui
declenche `On(0x13) & get_OwnerIsCaster` (`SereneUnifierAbility$$CreateTrigger`) et materialise 1169
sur `AdjacentFriends(owner,1) + owner + UnitsFromFaction(SurroundingFriends(owner,2), Tau)`. Sans ce
tour, l'effet N'EXISTE PAS et le test ne prouverait rien : il SKIPPE explicitement dans ce cas plutot
que de passer au vert a vide.

Cible `necroWarden` (VANILLE, `python unit_map.py vanilla-target`) : rien qui modifie le degat RECU,
donc 1169 est le SEUL modificateur defenseur en jeu.

Mesure de reference (#192, `probe_192_sense_of_stone.py`) : avant le port, le degat OFFLINE valait
EXACTEMENT le DOUBLE du live (dmgReductionPct[L50] = 50) sur deux cibles a la fois.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _combat_replay import _do_replay, _skip        # noqa: E402

import hexgeo                                       # noqa: E402
from engine.entities.pathfinding.board import Board  # noqa: E402

CARRIER = "tauAunShi"          # porteur du passif SereneUnifier (TriggeredAbilityType 0x479 = 1145)
ATTACKER = "necroDestroyer"    # Gauss : attaque normale utilisable en melee ET a distance
TARGET = "necroOverlord"       # cible VANILLE tanky (armure > 0, `effects` vide : 1169 sera le SEUL
                               # modificateur defenseur en jeu -- `necroWarden` porte, lui, un
                               # `RelentlessMarch_DangerZone` qui brouillerait l'attribution)
SENSE_OF_STONE = 1169


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _pair(board, dist):
    """(T cible, C porteur adjacent a T, A tuile d'attaquant a hex-distance `dist` de T) — tuiles
    walkable distinctes. Deterministe (parcours trie par id) ; None si le board ne peut pas la porter.
    `A` n'est qu'un PLACEMENT INITIAL : pour un tir a distance c'est `aiAttackRank` qui tranche la
    tuile effectivement legale (portee ET ligne de vue) -- une tuile a la bonne distance hex peut
    parfaitement etre sans LOS, auquel cas le tir live rend ZERO evenement (mesure : live=[]) et
    l'assert porterait sur un scenario NON JOUE."""
    tiles = [t for t in board.by_id.values() if t.get("walkable") and not t.get("isWall")]
    tiles.sort(key=lambda t: t["id"])
    for tt in tiles:
        tp = (tt["col"], tt["row"])
        carriers = [t for t in tiles if t["id"] != tt["id"]
                    and hexgeo.distance((t["col"], t["row"]), tp) == 1]
        if not carriers:
            continue
        cp = (carriers[0]["col"], carriers[0]["row"])
        for at in tiles:
            ap = (at["col"], at["row"])
            if ap in (tp, cp) or hexgeo.distance(ap, tp) != dist:
                continue
            return tp, cp, ap
    return None


def _normal_id(unit):
    ab = next((a for a in (unit.get("abilities") or []) if a.get("kind") == "normal"), None)
    return (ab or {}).get("id")


def _ranked_tile_at(rpc, rid, board, att_id, tgt_id, norm_id, tgt_pos, dist):
    """Tuile d'attaque LEGALE (`aiAttackRank` = `GetBestTileToAttackFrom`) a hex-distance `dist` de
    la cible — la seule facon fiable d'armer un tir RANGED (portee + LOS tranchees par le natif)."""
    ar = rpc("aiAttackRank", {"runnerId": rid, "unitId": att_id, "targetId": tgt_id,
                              "abilityType": norm_id, "maxRank": 8}, 90)
    ev = next((e for e in (((ar.get("units") or [{}])[0]).get("evals") or [])
               if e.get("targetId") == tgt_id), None)
    for t in ((ev or {}).get("ranked") or []):
        col, row = t.get("col"), t.get("row")
        if col is None or row is None:
            continue
        if hexgeo.distance((col, row), tgt_pos) == dist:
            return (col, row)
    return None


def _run(rpc, build_runner, dist, seed="777"):
    """Monte le scenario et rejoue l'attaque normale live vs offline. Renvoie la classification de
    `_do_replay` enrichie de `carries_1169`, ou {ok:False,reason}."""
    b = build_runner(seed, extra=["--roster", "1", "--p-units", ATTACKER,
                                  "--a-units", "%s,%s" % (CARRIER, TARGET)])
    rid = b["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        return _skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    tri = _pair(board, dist)
    if tri is None:
        return _skip("aucun triplet (cible, porteur adjacent, attaquant a dist=%d) sur ce board" % dist)
    tp, cp, ap = tri
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if not _ok(dv):
        return _skip("decisionView KO")

    def find(vid):
        return next((u for u in (dv.get("units") or [])
                     if u.get("visualId") == vid and u.get("alive")), None)
    champ, tgt, carrier = find(ATTACKER), find(TARGET), find(CARRIER)
    if champ is None or tgt is None or carrier is None:
        return _skip("unite manquante (att=%s tgt=%s carrier=%s)"
                     % (bool(champ), bool(tgt), bool(carrier)))
    for uid, to in ((tgt["id"], tp), (carrier["id"], cp), (champ["id"], ap)):
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": to[0], "row": to[1]}}}, 40)
    # DEUX `endturn` INCONDITIONNELS : le 1er cede la main a l'equipe du porteur (son turn-start pose
    # 1169 sur la cible adjacente), le 2e me la rend pour attaquer. C'est la SEULE facon d'exister
    # pour l'effet -- une boucle « tant que ce n'est pas mon tour » ne jouerait AUCUN endturn (c'est
    # deja mon tour au build) et le test passerait au vert sans avoir rien exerce.
    my_player = champ.get("owner")
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    for _ in range(6):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if dv.get("currentPlayer") == my_player:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    champ = next((u for u in (dv.get("units") or []) if u.get("id") == champ["id"] and u.get("alive")), None)
    tgt = next((u for u in (dv.get("units") or []) if u.get("id") == tgt["id"] and u.get("alive")), None)
    if champ is None or tgt is None:
        return _skip("unite manquante post-tours")
    carries = any(e.get("effectType") == SENSE_OF_STONE for e in (tgt.get("effects") or []))
    move_to = None
    if dist > 1:
        norm_id = _normal_id(champ)
        if norm_id is None:
            return _skip("pas d'attaque normale sur l'attaquant")
        move_to = _ranked_tile_at(rpc, rid, board, champ["id"], tgt["id"], norm_id, tp, dist)
        if move_to is None:
            return _skip("aucune tuile d'attaque LEGALE a dist=%d (portee/LOS)" % dist)
    r = _do_replay(rpc, rid, board, champ, tgt, move_to)
    if r.get("ok"):
        r["carries_1169"] = carries
        r["tgt_effects"] = [e.get("name") for e in (tgt.get("effects") or [])]
    return r


# dist RANGED = 2 : c'est la PORTEE de l'arme a distance de `necroDestroyer` (Gauss, `6hR2p60`).
# A dist 3 l'attaque normale n'est pas legale -> `live_ph` vide, et l'assert echouerait sur un
# scenario NON JOUE au lieu d'un desaccord de degat (mesure : live=[] off=[479,...]).
@pytest.mark.parametrize("dist,label", [(1, "melee"), (2, "ranged")])
def test_sense_of_stone_no_gate_bitexact(live_session, rpc, build_runner, dist, label):
    """Degat recu par une cible portant 1169 : offline == live BIT-EXACT, en MELEE comme en RANGED.

    Discriminant : sans la classe d'effet, l'offline valait le DOUBLE (#192). Un gate melee/ranged
    ajoute par erreur casserait exactement l'une des deux parametrisations."""
    r = _run(rpc, build_runner, dist)
    if not r["ok"]:
        pytest.skip("%s: %s" % (label, r["reason"]))
    if not r.get("carries_1169"):
        pytest.skip("la cible ne porte PAS 1169 (turn-start du porteur non joue ?) effets=%s"
                    % r.get("tgt_effects"))
    if r["did_crit"] or r["did_block"] or r["did_evade"]:
        pytest.skip("coup non propre (crit/block/evade live)")
    print("\n[1169 %s] live=%s off=%s armor=%s pierce=%s effets_cible=%s"
          % (label, r["live_ph"], r["off_ph"], r["armor"], r["pierce"], r.get("tgt_effects")))
    assert r["off_ph"] == r["live_ph"], (
        "1169 SenseOfStone NON bit-exact (%s) : off=%s live=%s — la reduction "
        "-dmgReductionPct%% est-elle appliquee sans gate (get_OwnerIsTarget SEUL) ?"
        % (label, r["off_ph"], r["live_ph"]))
