"""#448-r1-r1-r3-r1 -- CONFRONTATION LIVE de `movementStartPosition` sur une unite HORS PLATEAU.

LA QUESTION BINAIRE, et elle porte sur un canal que le jeu PUBLIE : quand une unite qui n'a plus
de tuile se deplace, combien de tuiles le natif lui compte-t-il ?

    IdunBattle.Operations.MoveUnitOperation$$Execute
        movementStartPosition = currentPosition
        if (IsEmpty(currentPosition) && prevThisTurn.HasValue && !IsEmpty(prevThisTurn.Value))
            movementStartPosition = prevThisTurn.Value
        startTile = movementStartPosition.Count > 0 ? movementStartPosition[0] : endTile
        CalculatePaths(unit, movementStartPosition, currentPosition, startTile, endTile, ...)
        ...
        RecordTilesMoved(unit, BattleQuery.GetNumTilesMoved(connectedPath), state)

Le port passait `old_pos` (la position COURANTE, donc `None` hors plateau) la ou le natif passe
`movementStartPosition`. `_num_tiles_moved` court-circuitait alors a `0`, et `RecordTilesMoved`
n'ecrivait RIEN.

MESURE DU 2026-08-18 (`MC1_67` / 777 / greffon `orksNob`, entite 79) :

    natif  `tilesMovedThisBattle` 0 -> 1        <- la branche degeneree `[endTile, endTile]`,
    port   1                                       `GetNumTilesMoved([end,end]) = Count - 1 = 1`
    port d'AVANT                    0           <- CONTRE-EPREUVE, non vide
    TEMOIN (2e pas, unite SUR le plateau)  delta 3 des deux cotes

⚠ **DEUX PIEGES DE CANAL, tous deux rencontres, tous deux capables de faire RETIRER un port juste.**

  1. `tilesMoved*` ne vient PAS de `combatSnapshot` mais d'un RPC DISTINCT, `actorStats`, que
     `load_state` n'ingere que si on le lui passe (`actor_stats=`). La capture de #448-r2b ne le
     demande pas -> les DEUX cotes repartaient a `0` et << s'accordaient >> sur un canal vide.
  2. Le compteur DU TOUR (`@+0xf0`) est ROULE par `ActorStatisticsComponent$$ResetThisTurn` en fin
     de tour, et le pas mesure ici TERMINE le tour du porteur (seul de son equipe). Lu sur `@+0xf0`
     le natif rend `0 -> 0` -- alors que la MEME ligne brute porte `tilesMovedLastTurn 0 -> 1`.
     C'est le cumul BATAILLE (`@+0xec`), que rien ne roule, qui mesure l'increment.

C'est le TEMOIN NON NUL qui a fait tomber le piege 1, et la lecture de la LIGNE ENTIERE (plutot
que du seul champ attendu) qui a fait tomber le piege 2.

MONTAGE : celui de #366-r1 / #448-r2b, DEJA valide -- greffe du passif `StormboyzStrike` (1141)
sur une unite du pool, qui se retrouve HORS PLATEAU sous `1140
StormboyzStrike_TeleportingIn` au premier tour. Le porteur reel `orksNpc6Stormboy` est un npc sans
summoner (`case-92` sec.5bis). Les briques de montage sont IMPORTEES du probe #448-r2b : pas de
fork, et si son montage se perime, celui-ci se perime avec lui -- ce qui est le regime sain.

⚠ CE PROBE NE MESURE RIEN SANS LE TRANSPORT AMBIANT (`snapshot.bind_live_rpc`) : sans lui la
greffe n'est pas montee cote port. `run()` le lie lui-meme.

ASCII only. Aucune VA en dur. Dispose SON runner.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import probe_448_r2b_stormboyz_teleporting_in as P

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "logs" / "probe448r1r1r3r1"


def _tiles_moved(st, uid: int) -> int:
    """Le cumul BATAILLE (`ActorStatisticsComponent @+0xec`), PAS celui du tour (`@+0xf0`).

    ⚠ ET C'EST LE COEUR DE LA MESURE. Les deux prennent le MEME increment sous
    `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved`, mais `@+0xf0` est ROULE en fin de tour
    par `ActorStatisticsComponent$$ResetThisTurn` (`+0xf4 = +0xf0` puis `+0xf0 = 0`). Or le pas
    mesure ici TERMINE le tour du porteur (il est seul de son equipe). Lu sur `@+0xf0`, le natif
    rend donc `0 -> 0` et parait ne rien compter ; la ligne BRUTE montre en meme temps
    `tilesMovedLastTurn 0 -> 1` et `tilesMovedThisBattle 0 -> 1`. Prendre le compteur du TOUR
    aurait fait conclure << le natif compte 0 >> et fait retirer un port JUSTE."""
    from engine.runner.components import UnitComponent
    e = st.get_entity(int(uid))
    uc = e.get_component(UnitComponent) if e is not None else None
    return int(getattr(uc, "tiles_moved_this_battle", 0) or 0) if uc is not None else 0


def _actor_stats(sid, rid) -> dict:
    """Payload BRUT du RPC `actorStats` -- un RPC DISTINCT de `combatSnapshot`.

    ⚠ C'EST CE QUI A FAIT RENDRE UNE PREMIERE MESURE VIDE. La capture de #448-r2b appelle
    `decisionView` / `observeBattle` / `combatSnapshot` / `boardGraph`, et `load_state` ne seede
    `UnitComponent.tiles_moved_this_turn` que si on lui passe `actor_stats=` (cf.
    `snapshot._load_actor_statistics`, #340-r1). Sans lui, les DEUX cotes repartent a `0` : le
    port et le natif << s'accordent >> sur un canal que personne n'a rempli."""
    return P.rpc(sid, "actorStats", {"runnerId": rid}, 60)


def _row(ast: dict, uid: int) -> dict:
    """La LIGNE ENTIERE du payload brut pour `uid` -- les trois compteurs de tuiles ET le canal
    `movement` (les deux `Nullable<UnitPositionId>`). Prendre la ligne entiere plutot qu'un champ
    choisi est ce qui a permis de voir que le `0` n'etait pas la ou on le cherchait."""
    for u in ((ast or {}).get("units") or []):
        if u.get("entityId") is not None and int(u["entityId"]) == int(uid):
            return dict(u)
    return {}


def _turn_counter(ast: dict, uid: int):
    """`tilesMovedThisBattle` de `uid` dans le payload BRUT, ou `None` = NON MESURE (jamais 0 par
    defaut : un echec rendu ne doit pas pouvoir se lire comme une mesure). Cf. `_tiles_moved` pour
    la raison du choix de CE compteur plutot que celui du tour."""
    v = _row(ast, uid).get("tilesMovedThisBattle")
    return None if v is None else int(v)


def _prev_this_turn(st, uid: int):
    from engine.runner.components import UnitComponent
    e = st.get_entity(int(uid))
    uc = e.get_component(UnitComponent) if e is not None else None
    v = getattr(uc, "previous_position_this_turn", None) if uc is not None else None
    return None if v is None else [tuple(x) for x in v]


def run(board_id: str = "MC1_67", seed: int = 777, graft: str = "orksNob",
        foes=("ultraTitus",)) -> dict:
    """Monte le porteur hors plateau, joue LE MEME pas des deux cotes, et rend les deux comptes."""
    import catalog_inject as CI
    from engine.runner.events import EventBus
    from engine.runner.operations.movement import (MoveUnitOperation, _movement_start_position,
                                                   _num_tiles_moved)

    from rl_collect_batch import _resolve_session
    sid = _resolve_session()
    prev_ambient = P.bind_ambient(sid)
    LOGS.mkdir(parents=True, exist_ok=True)
    tag = "%s_%s" % (graft, board_id)
    bc = LOGS / ("seedbc_%s.json" % tag)
    _p, reports = CI.write_grafted_seed_bc(str(bc), ["%s:%s" % (graft, P.ABILITY)])
    out: dict = {"board": board_id, "seed": seed, "graft": graft, "graftReport": reports[0],
                 "fails": []}
    fails = out["fails"]
    ctrl_uid, team, player = P.control_owner(sid, board_id, seed, graft, list(foes), tag)

    sf = LOGS / ("state_%s.json" % tag)
    rid = P.build(seed, board_id, graft, list(foes), str(bc), sf)
    print("[448r1r1r3r1] runner %d monte sur %s (seed %d, greffon %s)" % (rid, board_id, seed, graft))
    try:
        from engine.runner.snapshot import clear_ability_states_cache
        clear_ability_states_cache()
        st, board = P.offline_state(P.capture(sid, rid))
        uid = P.carrier_id(st, list(foes))
        if uid is None:
            raise SystemExit("MONTAGE : greffon introuvable")
        P.repair_owner(st, uid, team, player)

        depart = P.terms(st, uid)
        out["start"] = depart
        out["startPrevThisTurn"] = _prev_this_turn(st, uid)
        out["startTilesMoved"] = _tiles_moved(st, uid)
        out["startMovementStart"] = [list(t) for t in _movement_start_position(st, uid)]
        print("[448r1r1r3r1] depart : pos=%r feet=%r prevThisTurn=%r tilesMoved=%d "
              "movementStartPosition=%r"
              % (depart["pos"], depart["feet"], out["startPrevThisTurn"], out["startTilesMoved"],
                 out["startMovementStart"]))
        if depart["pos"] is not None:
            raise SystemExit("MONTAGE : le porteur n'est PAS hors plateau -- rien a mesurer")

        legal = P.native_movable(sid, rid, uid)
        if not legal:
            raise SystemExit("MONTAGE : `aiMovableTiles` VIDE pour le porteur hors plateau")
        dest = sorted(legal)[len(legal) // 2]
        out["dest"] = list(dest)
        print("[448r1r1r3r1] destination choisie : %r (%d tuiles legales)" % (dest, len(legal)))

        # ---- PORT : le MEME pas, sur l'etat capture AVANT.
        st_port, _b = P.offline_state(P.capture(sid, rid))
        P.repair_owner(st_port, uid, team, player)
        P.align_rng(sid, rid, st_port)
        op = MoveUnitOperation(int(uid), (int(dest[0]), int(dest[1])))
        op.execute(st_port, EventBus())
        out["portTilesMoved"] = _tiles_moved(st_port, uid)
        out["portPath"] = None if op.last_path is None else [list(t) for t in op.last_path]
        out["portMovementSteps"] = op.last_movement_steps
        out["portAbandoned"] = op.last_abandoned
        out["portPos"] = P.terms(st_port, uid)["pos"]
        # LE COMPTE QUE RENDAIT LE PORT D'AVANT, calcule sur le MEME etat : `from_pos = old_pos`,
        # c'est-a-dire `None` hors plateau. C'est la CONTRE-EPREUVE -- sans elle, un accord
        # port/natif ne dirait pas si le fix a mordu ou si le regime est degenere.
        st_av, _b2 = P.offline_state(P.capture(sid, rid))
        P.repair_owner(st_av, uid, team, player)
        out["portAvantTilesMoved"] = _num_tiles_moved(st_av, int(uid), None,
                                                      (int(dest[0]), int(dest[1])))
        print("[448r1r1r3r1] PORT : tilesMoved=%d path=%r steps=%r abandoned=%r pos=%r "
              "(port d'AVANT aurait rendu %d)"
              % (out["portTilesMoved"], out["portPath"], out["portMovementSteps"],
                 out["portAbandoned"], out["portPos"], out["portAvantTilesMoved"]))

        # ---- NATIF : le MEME pas. LE COMPTE SE LIT EN DELTA sur le payload BRUT du RPC
        # `actorStats` -- pas a travers `load_state`, qui ne le seede que si on le lui passe.
        ast_avant = _actor_stats(sid, rid)
        out["nativeAvant"] = _turn_counter(ast_avant, uid)
        out["ligneAvant"] = _row(ast_avant, uid)
        print("[448r1r1r3r1] NATIF ligne AVANT = %s" % json.dumps(out["ligneAvant"], sort_keys=True))
        act = P.rpc(sid, "applyAction", {"runnerId": rid,
                                         "action": {"kind": "move", "unitId": int(uid),
                                                    "to": {"col": int(dest[0]),
                                                           "row": int(dest[1])}}}, 180)
        if not act.get("ok"):
            fails.append("`applyAction move` REFUSE (montage, pas mesure) : %r" % (act,))
        ast_apres = _actor_stats(sid, rid)
        out["nativeApres"] = _turn_counter(ast_apres, uid)
        out["ligneApres"] = _row(ast_apres, uid)
        print("[448r1r1r3r1] NATIF ligne APRES = %s" % json.dumps(out["ligneApres"], sort_keys=True))
        cap_nat = P.capture(sid, rid)
        st_nat, _b3 = P.offline_state(cap_nat)
        P.repair_owner(st_nat, uid, team, player)
        out["nativePos"] = P.terms(st_nat, uid)["pos"]
        if out["nativeAvant"] is None or out["nativeApres"] is None:
            fails.append("CANAL NON MESURE : `actorStats.tilesMovedThisBattle` absent pour l'entite "
                         "%r (avant=%r apres=%r) -- aucune conclusion possible."
                         % (uid, out["nativeAvant"], out["nativeApres"]))
            out["nativeTilesMoved"] = None
        else:
            out["nativeTilesMoved"] = out["nativeApres"] - out["nativeAvant"]
        print("[448r1r1r3r1] NATIF : tilesMovedThisBattle %r -> %r (delta %r) pos=%r"
              % (out["nativeAvant"], out["nativeApres"], out["nativeTilesMoved"], out["nativePos"]))

        # ---- LE TEMOIN NON NUL, INDISPENSABLE : un delta `0` cote natif ne dit RIEN tant qu'on n'a
        # pas montre que ce canal SAIT bouger dans CE runner. On rejoue un SECOND pas, depuis la
        # position que le premier vient de poser -- l'unite est desormais SUR le plateau, donc c'est
        # le regime NOMINAL, celui dont on sait qu'il compte.
        legal2 = P.native_movable(sid, rid, uid)
        out["temoinLegal"] = len(legal2)
        out["temoinDelta"] = None
        if legal2:
            dest2 = sorted(legal2)[len(legal2) // 2]
            act2 = P.rpc(sid, "applyAction",
                         {"runnerId": rid, "action": {"kind": "move", "unitId": int(uid),
                                                      "to": {"col": int(dest2[0]),
                                                             "row": int(dest2[1])}}}, 180)
            av2 = out["nativeApres"]
            ap2 = _turn_counter(_actor_stats(sid, rid), uid)
            out["temoinOk"] = bool(act2.get("ok"))
            out["temoinDest"] = list(dest2)
            out["temoinApres"] = ap2
            out["temoinDelta"] = None if (av2 is None or ap2 is None) else ap2 - av2
            print("[448r1r1r3r1] TEMOIN (2e pas, unite SUR le plateau) : ok=%r dest=%r "
                  "tilesMovedThisBattle %r -> %r (delta %r)"
                  % (out["temoinOk"], out["temoinDest"], av2, ap2, out["temoinDelta"]))

        # ---- LES VERDICTS.
        if not out["temoinDelta"]:
            fails.append("TEMOIN NUL : le canal `tilesMovedThisBattle` ne bouge pas non plus sur un "
                         "pas NOMINAL (delta %r) -- le compte du pas hors plateau ne prouve RIEN, "
                         "ni pour ni contre." % (out["temoinDelta"],))
        if out["portTilesMoved"] != out["nativeTilesMoved"]:
            fails.append("tilesMovedThisBattle : port=%r != natif=%r"
                         % (out["portTilesMoved"], out["nativeTilesMoved"]))
        if out["portAvantTilesMoved"] == out["nativeTilesMoved"]:
            fails.append("CONTRE-EPREUVE VIDE : le port d'AVANT rendait deja %d, le meme compte que "
                         "le natif -- ce montage n'exerce pas #448-r1-r1-r3-r1"
                         % out["portAvantTilesMoved"])
        if out["portPos"] != out["nativePos"]:
            fails.append("position finale : port=%r != natif=%r" % (out["portPos"], out["nativePos"]))
    finally:
        P.rpc(sid, "disposeRunner", {"runnerId": rid}, 45)
        sf.unlink(missing_ok=True)
        if prev_ambient is not None:
            from engine.runner.snapshot import bind_live_rpc
            bind_live_rpc(prev_ambient)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--graft", default="orksNob")
    ap.add_argument("--foes", default="ultraTitus")
    a = ap.parse_args()
    out = run(a.board, a.seed, a.graft, tuple(x for x in a.foes.split(",") if x))
    print(json.dumps({k: v for k, v in out.items() if k != "start"}, indent=1, sort_keys=True))
    for f in out["fails"]:
        print("  [FAIL] %s" % f)
    print("[448r1r1r3r1] %s" % ("OK" if not out["fails"] else "%d FAIL" % len(out["fails"])))
    return 0 if not out["fails"] else 1


if __name__ == "__main__":
    sys.exit(main())
