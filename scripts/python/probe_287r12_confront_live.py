"""probe #287-r12 (volet LIVE) -- confrontation des DEUX abilities du rayon effectif : `1017 FragBomb`
et `1018 ValkyrieStrike`, castees sur une **TUILE** (le regime que le port rendait MUET).

POURQUOI CES DEUX-LA, ET PAS LES CINQ DU BACKLOG
------------------------------------------------
Le backlog annoncait cinq abilities TILE-TARGET « lisant un `Target()` nul ». La mesure offline
(`probe_287r12_role_target_tuile.py --rayon`) ramene le rayon EFFECTIF a **deux** : seules `1017` et
`1018` EVALUENT le noeud `Target()` quand `target_id` designe une tuile. `1026 BasiliskBarrage`
collapse ses tirages en Python AVANT l'arbre (son trou etait ailleurs, dans la normalisation de la
tuile) ; `1148 DaemonicOrdnance` et `1169 PlagueburstMortar` portent leur propre normalisation
(`FixedTileIds`). C'est CE probe qui confronte les deux, et le natif est l'ORACLE.

CE QUE LE NATIF FAIT DE SA CIBLE (lu, puis confronte ici)
---------------------------------------------------------
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` resout
`finalTarget = IActiveAbility.GetActualTarget(ability, caster, target)` (slot 16 ->
`IdunBattle.Entities.Abilities.AActiveAbility$$GetActualTarget` -> slot `ITargetingQuery` 6 =
`IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`), dont la branche
`rules & TargetIsTile` rend `IdunBattle.Entities.EntityExtensions$$GetMainTile(target, state)`. Ce
`finalTarget` devient `AbilityEntities+0x10` (= le role `target`, lu par `Target()`). Pour ces deux
abilities, le natif y met donc l'ENTITE-TUILE -- jamais nul, jamais l'unite occupante.

VOLET 1017 (`astraBullgryn`, HERO du pool) -- l'ARBRE
  `Units(Target@0x178, 1, 1)` (volet principal) et `AdjacentUnits(Target@0x178, 0, 3) - Caster@0x160`
  (splash) sont ANCRES sur ce role. Cast avec `targetId` = l'id d'ENTITE-TUILE, et on confronte les
  coups LIVE aux coups OFFLINE rejoues depuis le MEME MT. Le TEMOIN est le port d'AVANT (role
  `target` non materialise) : il doit rendre **zero coup**, sans erreur -- c'est la signature exacte
  du no-op silencieux qu'on repare.

VOLET 1018 (`astraSmnVoxcaster`, SUMMON injecte au catalogue -- meme montage que
`probe_245_valkyrie_targeting.py`, dont l'en-tete justifie les deux amenagements d'entree) -- LE
POINT DUR. L'arbre est le noeud unique
`AddBondEffect(0x3fe = 1022, AbilityStateReference, caster@0x160, target@0x178, caster@0x160, ZERO)`.
Le porteur de l'effet 1022 est donc `finalTarget` = l'ENTITE-TUILE. La question binaire est :
**le natif inscrit-il 1022 sur la TUILE (`tileMeta.tiles[].effects`) ou sur l'UNITE qui l'occupe
(`decisionView.units[].effects`) ?** Les deux canaux sont lus, et le probe imprime les DEUX.

Discipline runner : state-file ABSOLU sous `logs/`, `--dispose` en fin de passe, un SEUL runner.
Usage (depuis scripts/python, session Frida chaude) :
    python probe_287r12_confront_live.py --volet 1018
    python probe_287r12_confront_live.py --volet 1017
    python probe_287r12_confront_live.py --dispose
ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import catalog_inject as CI                                          # noqa: E402
import rl_duel as RD                                                 # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType    # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister               # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

FRAG_BOMB = int(ActiveAbilityType.FragBomb)                 # 1017
VALKYRIE = int(ActiveAbilityType.ValkyrieStrike)            # 1018
VALK_EFFECT = 1022                                          # EffectType.ValkyrieStrike_Effect (0x3fe)

BULLGRYN = "astraBullgryn"          # HERO, pool -- porteur de 1017
VOXCASTER = "astraSmnVoxcaster"     # SUMMON injecte au catalogue -- porteur de 1018
ENEMY = "necroWarden"
BOARD = "MC1_67"
SEED = 777
RANK = 17
# Les DEUX seuls amenagements de l'entree de catalogue du Voxcaster, justifies dans l'en-tete de
# `probe_245_valkyrie_targeting.py` : PV a 0 au seed (ils viennent du summoner), et le trait `Summon`
# qui rendrait l'unite AUTOMATIQUE (`UnitExtensions$$IsAutomatic`) donc non commandable.
VOX_HEALTH = 5000
VOX_TRAITS = ["Imperial", "BattleFatigue"]

STATE = ROOT / "logs" / ("_probe287r12-%d.json" % os.getpid())


def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _build(sid, seed: int, board: str):
    """Un SEUL runner portant les DEUX casters (le Bullgryn du pool + le Voxcaster injecte)."""
    STATE.parent.mkdir(parents=True, exist_ok=True)
    bc0, _added, _ab, _m = CI.augment(RD._load_seed_bc(None), [VOXCASTER, BULLGRYN, ENEMY],
                                      rank=RANK)
    dump = RD._load_board_dump(board)
    template, _pool, _pool_mow = RD._normalize_and_extract_pool(sid, bc0, RANK, board_dump=dump)
    bc = copy.deepcopy(template)
    vox = next((u for u in bc["Units"] if u.get("Id") == VOXCASTER), None)
    if vox is None:
        raise RuntimeError("%s absent du catalogue BC.Units" % VOXCASTER)
    vox["Health"] = VOX_HEALTH
    vox["Traits"] = list(VOX_TRAITS)
    RD._patch_predefined_units(bc, [ENEMY, ENEMY, ENEMY])
    pts = (RD._spawn_points_by_twpi(bc).get(0) or [])
    if len(pts) < 2:
        raise RuntimeError("moins de 2 spawn points joueur sur %s" % board)
    pu = [{"unitId": VOXCASTER, "playerId": RD.PLAYER_ID_HUMAN,
           "col": int(pts[0][0]), "row": int(pts[0][1])},
          {"unitId": BULLGRYN, "playerId": RD.PLAYER_ID_HUMAN,
           "col": int(pts[1][0]), "row": int(pts[1][1])}]
    resp = _rpc(sid, "initAndStart",
                [{"configJson": json.dumps(bc), "seed": seed, "playerUnits": pu,
                  "owner": str(STATE.resolve())}], timeout=120)
    rid = ((resp or {}).get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError("initAndStart KO: %s" % json.dumps(resp)[:400])
    STATE.write_text(json.dumps({"runnerId": int(rid)}), encoding="utf-8")
    return int(rid)


def _rid(sid, seed, board, rebuild: bool):
    if not rebuild and STATE.exists():
        return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])
    return _build(sid, seed, board)


def _capture(sid, rid):
    """Etat LIVE fige : les CINQ canaux que `load_state` consomme, plus le MT."""
    dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    tiles = _r(sid, "tileMeta", {"runnerId": rid}, 60)
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    rng = _r(sid, "dumpRng", {"runnerId": rid}, 40)
    return dv, ob, snap, tiles, bg, rng


def _seed_rng(dump):
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"])
    rng.mti = dump["mti"]
    return rng


def _unit(dv, vid):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vid), None)


def _alive_enemies(dv, owner):
    return [u for u in (dv.get("units") or [])
            if u.get("alive") and u.get("owner") != owner]


def _to_my_turn(sid, rid, vid, maxit=4):
    for _ in range(maxit):
        dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
        u = _unit(dv, vid)
        if u is None or u.get("ctrl"):
            return dv, u
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
    return dv, _unit(dv, vid)


def _effets_unites(dv) -> dict:
    """{unitId: sorted[effectType]} lu de `decisionView.units[].effects` (= `readEffectsByUnit`)."""
    out = {}
    for u in (dv.get("units") or []):
        types = sorted(int(e.get("type")) for e in (u.get("effects") or [])
                       if e.get("type") is not None)
        if types:
            out[int(u["id"])] = types
    return out


def _effets_tuiles(tiles) -> dict:
    """{tileId: sorted[effectType]} lu de `tileMeta.tiles[].effects` (= `readEffectsByTile`, #102)."""
    out = {}
    for t in ((tiles or {}).get("tiles") or []):
        types = sorted(int(e.get("type")) for e in (t.get("effects") or [])
                       if e.get("type") is not None)
        if types:
            out[int(t["id"])] = types
    return out


def _coups(res, ability: int) -> list:
    """[(targetId, amount)] des coups publies par le cast LIVE, dans l'ordre des evenements."""
    out = []
    for a in (res.get("actions") or []):
        for e in (a.get("events") or []):
            td = e.get("tags")
            if isinstance(td, str):
                td = json.loads(td)
            if not td:
                continue
            if td.get("Active_Ability_Type") == ability and "Amount" in td:
                out.append((td["Target_Id"], td["Amount"]))
    return out


def _sans_role_target(klass):
    """Le port d'AVANT #287-r12 : la MEME classe, mais le role `target` de l'`AbilityEntities` n'est
    PAS materialise pour une entite-tuile. C'est le TEMOIN -- sans lui, un accord natif/port ne
    distingue pas « l'elargissement porte le resultat » de « il vient d'ailleurs »."""
    import engine.runner.abilities.behaviours.context as CTX

    class _Avant(klass):
        __slots__ = ()

        def execute_behaviour(self, state, caster_id, target_id):
            vrai = CTX._tile_entity

            def _mort(_state, _eid):
                return None                      # l'etat d'avant : aucune entite-tuile materialisee

            CTX._tile_entity = _mort
            try:
                return klass.execute_behaviour(self, state, caster_id, target_id)
            finally:
                CTX._tile_entity = vrai

    return _Avant


# ------------------------------------------------------------------------------- volet 1018

def volet_1018(sid, rid) -> int:
    dv, vox = _to_my_turn(sid, rid, VOXCASTER)
    if vox is None:
        print("[1018] Voxcaster absent du build -- NON CONFRONTE")
        return 1
    ens = _alive_enemies(dv, vox.get("owner"))
    if not ens:
        print("[1018] aucun ennemi vivant -- NON CONFRONTE")
        return 1
    dv, ob, snap, tiles, bg, rng = _capture(sid, rid)
    board = Board(bg["tiles"], adjacency="native_sym")
    cible = ens[0]
    tuile = board.id_at(cible["pos"]["col"], cible["pos"]["row"])
    print(f"[1018] caster={vox['id']} cible-unite={cible['id']} tuile-cible={tuile}")
    av_u, av_t = _effets_unites(dv), _effets_tuiles(tiles)

    res = _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": vox["id"], "targetId": int(tuile),
        "abilityType": VALKYRIE}}, 120)
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    print(f"[1018] cast ok={bool(isinstance(res, dict) and res.get('ok'))} "
          f"action0.ok={a0.get('ok')} reason={a0.get('reason')}")
    dv2 = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
    tiles2 = _r(sid, "tileMeta", {"runnerId": rid}, 60)
    ap_u, ap_t = _effets_unites(dv2), _effets_tuiles(tiles2)

    neuf_u = {k: sorted(set(v) - set(av_u.get(k, []))) for k, v in ap_u.items()
              if sorted(set(v) - set(av_u.get(k, [])))}
    neuf_t = {k: sorted(set(v) - set(av_t.get(k, []))) for k, v in ap_t.items()
              if sorted(set(v) - set(av_t.get(k, [])))}
    print(f"[1018] NATIF effets NEUFS sur UNITES : {neuf_u}")
    print(f"[1018] NATIF effets NEUFS sur TUILES : {neuf_t}")
    porteur_natif = ("TUILE" if any(VALK_EFFECT in v for v in neuf_t.values())
                     else "UNITE" if any(VALK_EFFECT in v for v in neuf_u.values())
                     else "AUCUN")
    print(f"[1018] >>> le natif inscrit {VALK_EFFECT} sur : {porteur_natif}")

    klass = ABILITY_CLASSES[VALKYRIE]
    for nom, cls in (("APRES", klass), ("AVANT(temoin)", _sans_role_target(klass))):
        st = load_state(dv, ob, snap, board=board, tiles=tiles)
        if rng and rng.get("ok"):
            st.rng = _seed_rng(rng)
        cls().execute_behaviour(st, int(vox["id"]), int(tuile))
        pose = sorted((int(k), sorted(int(e.effect_type) for e in v))
                      for k, v in (st.effects.by_unit if st.effects else {}).items()
                      if any(int(e.effect_type) == VALK_EFFECT for e in v))
        print(f"[1018] PORT {nom} : porteurs de {VALK_EFFECT} = {pose}")
    return 0


# ------------------------------------------------------------------------------- volet 1017

def volet_1017(sid, rid) -> int:
    dv, bull = _to_my_turn(sid, rid, BULLGRYN)
    if bull is None:
        print("[1017] Bullgryn absent du build -- NON CONFRONTE")
        return 1
    ens = _alive_enemies(dv, bull.get("owner"))
    if not ens:
        print("[1017] aucun ennemi vivant -- NON CONFRONTE")
        return 1
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    board = Board(bg["tiles"], adjacency="native_sym")
    cible = ens[0]
    tp = (cible["pos"]["col"], cible["pos"]["row"])
    tuile = board.id_at(*tp)
    # 1017 est RANGE_ADJACENT : on AMENE le caster au contact (on ne se plaint pas de la geometrie).
    voisins = [t for t in board.neighbours_native(tuile)
               if board.by_id.get(t, {}).get("walkable")]
    occupes = {(u["pos"]["col"], u["pos"]["row"]) for u in (dv.get("units") or []) if u.get("alive")}
    libre = next((t for t in voisins if board.coord(t) not in occupes), None)
    if libre is None:
        print("[1017] aucune tuile adjacente libre autour de la cible -- NON CONFRONTE")
        return 1
    c = board.coord(libre)
    _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": bull["id"], "to": {"col": int(c[0]), "row": int(c[1])}}}, 90)

    dv, ob, snap, tiles, bg, rng = _capture(sid, rid)
    print(f"[1017] caster={bull['id']} cible-unite={cible['id']} tuile-cible={tuile}")
    res = _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": bull["id"], "targetId": int(tuile),
        "abilityType": FRAG_BOMB}}, 120)
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    print(f"[1017] cast ok={bool(isinstance(res, dict) and res.get('ok'))} "
          f"action0.ok={a0.get('ok')} reason={a0.get('reason')}")
    live = _coups(res, FRAG_BOMB)
    print(f"[1017] NATIF coups = {live}")

    klass = ABILITY_CLASSES[FRAG_BOMB]
    for nom, cls in (("APRES", klass), ("AVANT(temoin)", _sans_role_target(klass))):
        st = load_state(dv, ob, snap, board=board, tiles=tiles)
        if rng and rng.get("ok"):
            st.rng = _seed_rng(rng)
        out = cls().execute_behaviour(st, int(bull["id"]), int(tuile)) or {}
        seq = [(out.get("main_attack") or {}).get("per_hit") or []]
        coups = [(cible["id"], a) for a in seq[0]]
        for s in (out.get("splash") or []):
            coups += [(s["target"], a) for a in ((s.get("attack") or {}).get("per_hit") or [])]
        print(f"[1017] PORT {nom} : coups = {coups}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--volet", choices=["1017", "1018"], default=None)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--dispose", action="store_true")
    ns = ap.parse_args(argv)
    sid = _resolve_session(None)
    if ns.dispose:
        if STATE.exists():
            rid = int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])
            print(_r(sid, "disposeRunner", {"runnerId": rid}, 60))
            STATE.unlink()
        return 0
    rid = _rid(sid, ns.seed, ns.board, ns.rebuild)
    print(f"[287-r12] runner={rid} board={ns.board} seed={ns.seed}")
    if ns.volet == "1017":
        return volet_1017(sid, rid)
    if ns.volet == "1018":
        return volet_1018(sid, rid)
    rc = volet_1018(sid, rid)
    return rc or volet_1017(sid, rid)


if __name__ == "__main__":
    raise SystemExit(main())
