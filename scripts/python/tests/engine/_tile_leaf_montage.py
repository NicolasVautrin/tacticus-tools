"""Montage REUTILISABLE des feuilles Tile(7) a gate de TRAIT (`ctx["unit_traits"]`, #175).

Pourquoi un module de montage et pas un `@fixture` inline : les 7 feuilles concernees
(`CapturePointTileUtility`, `PowerUpTileUtility`, `DespoiledGroundUtility`,
`SummonDislikeDoorOpeningUtility`, `HeroDoorOpeningUtility`, `AttractMechanicalsUtility`,
`MoveTowardsUnitUtility`) exigent TOUTES le meme etat de depart -- une bataille ou l'unite qui
evalue porte un trait discriminant ET ou la tuile candidate porte l'attribut co-gate. Chaque
nouvelle feuille ranimee reutilise donc ce montage au lieu d'en recopier un.

Ce que le montage produit (`DespoiledMontage`) :
  * un runner 1v1 **porteur `LetTheGalaxyBurn` (Chaos) vs cible Imperial** ;
  * une tuile qui porte REELLEMENT l'effet de tuile `DespoiledGround` (EffectType `0x5c4` = 1476),
    POSE PAR LE NATIF (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour`
    -> `AddEffect(0x5c4)`) -- ce volet du kit n'est pas porte offline, donc c'est bien le moteur natif
    qui fabrique l'etat, pas nous ;
  * une tuile TEMOIN sans cet effet ;
  * les deux `AiDecisionContext` (porteur Chaos / cible Imperial) qui evaluent ces tuiles.

C'est le seul co-gate des 7 dont la donnee par-tuile soit a la fois REMONTEE par le RPC `tileMeta`
et FABRICABLE live (cf. `docs/rl/case-175-tile-unit-traits.md` pour les 5 autres).

ASCII only.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

import hexgeo
from engine import weights as W
from engine.ai import context as _ai_ctx
from engine.playbook import scene as _scene

CARRIER = "blackTerminator"      # Chaos (GrandAllianceId) + trait LetTheGalaxyBurn (1058)
TARGET = "bloodSanguinary"       # Imperial (GrandAllianceId)
HP = "900000"                    # la cible survit aux attaques repetees
DESPOIL_TRIES = 12               # pose = Maybe(33 %) par attaque -> 12 essais suffisent tres largement


@dataclass
class DespoiledMontage:
    """Etat livre par le montage. `pos_despoiled` porte l'EffectType 1476, `pos_clean` non."""
    rid: int
    wt: object
    carrier_id: int
    target_id: int
    pos_despoiled: tuple
    pos_clean: tuple
    ctx_carrier: object          # AiDecisionContext du porteur (Chaos)
    ctx_target: object           # AiDecisionContext de la cible (Imperial)
    tile_effect_types: dict = field(default_factory=dict)


def _dv(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def _tile_types(rpc, rid) -> dict:
    """{(col,row): [EffectType]} tel que remonte par `tileMeta` (`EffectComponent+0x58`)."""
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    out = {}
    for t in (tm.get("tiles") or []):
        ids = [int(e["effectType"]) for e in (t.get("effects") or [])
               if e.get("effectType") is not None]
        if ids:
            out[(t.get("col"), t.get("row"))] = ids
    return out


def build_despoiled_montage(rpc, build_runner, seed: str = "175001",
                            board: str = "MC1_67") -> DespoiledMontage:
    """Monte la bataille et fabrique l'etat despoiled. `pytest.skip` si l'etat n'est pas obtenu
    (le harnais reste honnete : on ne valide pas un gate dont l'etat n'a pas ete atteint)."""
    rid = build_runner(seed, extra=["--p-units", CARRIER, "--a-units", TARGET,
                                    "--hp-target", HP, "--hp-player", HP],
                       board=board)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    walk = [(t["col"], t["row"]) for t in (bg.get("tiles") or []) if t.get("walkable")]
    if not walk:
        pytest.skip("boardGraph indispo")

    dv = _dv(rpc, rid)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    me = next((u for u in units if u.get("visualId") == CARRIER), None)
    en = next((u for u in units if u.get("visualId") == TARGET), None)
    if me is None or en is None:
        pytest.skip("1v1 %s vs %s attendu" % (CARRIER, TARGET))
    myp, aid, tid = me.get("owner"), me["id"], en["id"]
    norm = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
    if norm is None:
        pytest.skip("pas d'attaque normale sur %s" % CARRIER)

    despoiled = None
    for _ in range(DESPOIL_TRIES):
        for _ in range(4):
            dv = _dv(rpc, rid)
            if dv.get("currentPlayer") == myp:
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        us = {u["id"]: u for u in (dv.get("units") or []) if u.get("alive")}
        a, t_ = us.get(aid), us.get(tid)
        if a is None or t_ is None:
            break
        T = (t_["pos"]["col"], t_["pos"]["row"])
        A = (a["pos"]["col"], a["pos"]["row"])
        if hexgeo.distance(A, T) != 1:                 # DRIVE : on colle l'attaquant (melee)
            nb = [c for c in walk if hexgeo.distance(c, T) == 1]
            if nb:
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": aid,
                    "to": {"col": nb[0][0], "row": nb[0][1]}}}, 60)
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": aid, "targetId": tid,
            "abilityType": norm["id"]}}, 90)
        types = _tile_types(rpc, rid)
        hit = [p for p, ids in types.items() if 1476 in ids]
        if hit:
            despoiled = hit[0]
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

    if despoiled is None:
        pytest.skip("DespoiledGround (1476) non pose en %d attaques" % DESPOIL_TRIES)

    # Re-arme l'ACTIVATION du porteur : la derniere attaque a consomme son tour, donc
    # `ctx.move_tiles` serait VIDE et le sweep MOVE (`MovementActionGenerator`) sortirait
    # immediatement -- un chemin non exerce ne prouve rien. Deux `endturn` rendent la main.
    for _ in range(4):
        dv = _dv(rpc, rid)
        if dv.get("currentPlayer") == myp and (dv.get("units") or []):
            mv = rpc("aiMovableTiles", {"runnerId": rid}, 150)
            if any((u.get("tiles") or []) for u in (mv.get("units") or [])
                   if u.get("unitId") == aid):
                break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

    types = _tile_types(rpc, rid)
    hit = [p for p, ids in types.items() if 1476 in ids]
    if not hit:
        pytest.skip("DespoiledGround expire avant la mesure (remaining trop court)")
    despoiled = hit[0]
    clean = next((p for p in walk if 1476 not in (types.get(p) or [])), None)
    if clean is None:
        pytest.skip("aucune tuile temoin sans 1476")

    wt = W.load()
    predictor = _scene.build_predictor(lambda m, b, t: rpc(m, b, t), rid)
    dv = _dv(rpc, rid)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 150)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    rpc_l = lambda m, b, t: rpc(m, b, t)                                   # noqa: E731
    ctx_c = _ai_ctx.build(rpc_l, rid, dv, mov_by_unit, aid, wt, predictor)
    ctx_t = _ai_ctx.build(rpc_l, rid, dv, mov_by_unit, tid, wt, predictor)
    return DespoiledMontage(rid=rid, wt=wt, carrier_id=aid, target_id=tid,
                            pos_despoiled=despoiled, pos_clean=clean,
                            ctx_carrier=ctx_c, ctx_target=ctx_t,
                            tile_effect_types=types)
