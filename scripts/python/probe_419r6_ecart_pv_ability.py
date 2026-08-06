#!/usr/bin/env python
"""#419-r6 -- l'ecart natif-port de 904 PV que l'ouverture du canal crit/block fait apparaitre.

LE FAIT, TEL QUE #419-r5 L'A LAISSE
------------------------------------
`tests/engine/runner/test_damage_ability_live.py` passe SANS items et ECHOUE AVEC :

    live_ph == off_ph == [5543]      -- le degat PAR COUP est identique des deux cotes
    off_after 2086  !=  live_after 1182

Le calcul du coup est donc HORS DE CAUSE : l'ecart (904) porte sur autre chose que le montant
du coup. Deux familles d'explication, et elles ont des consequences DISJOINTES :

  (A) L'ETAT DE DEPART differe -- ce que `load_state(dv, ob, snap)` lit comme PV de la cible
      n'est pas ce que le natif porte. Alors c'est un defaut de PUBLICATION ou de LECTURE, et
      il vaut pour tout test qui capture un etat.
  (B) Le LIVE applique un degat de PLUS que le port ne modelise pas (ou l'inverse). Alors le
      port a un trou, et l'ouverture du canal l'a seulement REVELE.

CE QUE CE PROBE MESURE, ET DANS QUEL ORDRE
------------------------------------------
  etape 1  ETAT DE DEPART -- les PV de la cible lus par TROIS canaux independants
           (`observeBattle`, `combatSnapshot`, `decisionView`) et par le port
           (`load_state` -> `HealthComponent.hp`). Si les quatre concordent, (A) tombe.
  etape 2  EVENTS DU CAST -- TOUS les events, pas seulement ceux que le test retient
           (`Active_Ability_Type == ABILITY`). C'est ce filtre qui peut cacher un degat.
  etape 3  BILAN PAR SOUSTRACTION -- `hp_avant - hp_apres` cote natif, confronte a la somme
           des `Amount` retenus. Le reste, s'il existe, est ce que le filtre ecarte.
  etape 4  LE PORT -- ce que le moteur porte applique, et d'ou.

Le TEMOIN est gratuit : `--sans-items` rejoue le meme montage dans le regime d'avant #419-r5.
C'est ce qui etablit que l'ecart est CAUSE par l'ouverture, et non preexistant.

Aucune assertion : c'est un probe, il MESURE.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import deque
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import rl_collect_batch as R     # noqa: E402

CASTER_VIS = "templSwordBrother"
TARGET_VIS = "necroOverlord"
ABILITY = 1043                   # ThunderousAssault


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _bfs(board, src):
    dist = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def _hp_observe(ob: dict, uid) -> dict:
    for u in (ob.get("units") or []):
        if u.get("id") == uid or u.get("squadId") == uid or u.get("entityId") == uid:
            return {k: u.get(k) for k in ("hp", "maxHp", "health", "remainingHealth",
                                          "shield", "isDead") if k in u}
    return {}


def _hp_snapshot(snap: dict, uid) -> dict:
    for u in (snap.get("units") or []):
        if u.get("entityId") == uid or u.get("squadId") == uid:
            st = u.get("stats") or {}
            out = {k: u.get(k) for k in ("hp", "maxHp", "shield") if k in u}
            out.update({("stat." + k): st.get(k) for k in
                        ("health", "maxHealth", "armor", "fixedArmor",
                         "critChance", "critDamage", "blockChance", "blockDamage")
                        if k in st})
            return out
    return {}


# Les DEUX mecanismes HORS AXE que la mesure a nommes, et le montage qui les eteint.
#
#   * `ChampionOfTheFeast` (TriggeredAbilityType 1086, passif du CASTER) -- i2 :
#     « After moving, deals {nrOfHits}x {minDmg}-{maxDmg} Power Damage to an adjacent enemy ».
#     `ThunderousAssault` POUSSE la cible puis DEPLACE le caster dans la case liberee, donc le
#     passif frappe une SECONDE fois dans le meme `applyAction`. Il n'est porte par AUCUN des
#     quatre registres de trigger du moteur.
#   * `LivingMetal` (trait de la CIBLE) -- i2 : « Regenerates {hpPct}% of its max Health at the
#     start of the players' turn », `livingMetalHp = 10`. Le cast TERMINE le tour (roster 1v1),
#     donc le natif bascule sur le tour adverse et rend 10 % des PV max AVANT que le test ne lise
#     `live_after`.
#
# Le premier vit DANS le cast : on l'ETEINT. Le second vit APRES lui : on empeche le tour de
# BASCULER, en donnant au joueur une seconde unite qui n'a pas encore agi -- ce qui borne la
# mesure au cast, quel que soit le trait de turn-start que porte la cible.
ESCORTE = "eldarFarseer"        # 2e p-unit : sa seule fonction est de retenir le tour

_NEUTRALISER = ["--unit-stat", "%s:PassiveAbilities=[]" % CASTER_VIS]


def monter(sid: int, state_file: str, board: str, seed: str, rank: int,
           sans_items: bool, neutraliser: bool = False) -> int:
    p_units = ("%s,%s" % (CASTER_VIS, ESCORTE)) if neutraliser else CASTER_VIS
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed,
            "--state-file", state_file, "--rank", str(rank), "--board", board,
            "--roster", "1", "--p-units", p_units, "--a-units", TARGET_VIS]
    if neutraliser:
        argv += _NEUTRALISER
    if sans_items:
        argv.append("--no-bis-items")
    p = subprocess.run(argv, cwd=str(_HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError("rl_duel build a echoue (rc=%d) : %s"
                           % (p.returncode, (p.stderr or p.stdout or "")[-900:]))
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def approcher(sid: int, rid: int):
    """Amene le caster au contact de la cible -- meme drive que le test."""
    from engine.entities.pathfinding.board import Board

    bg = R._rpc(sid, "boardGraph", [{"runnerId": rid}], timeout=60).get("result") or {}
    if not bg.get("tiles"):
        raise RuntimeError("boardGraph indisponible")
    board = Board(bg["tiles"], adjacency="native_sym")

    def tile_of(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None

    my_player = None
    for _t in range(25):
        dec = R._rpc(sid, "decisionView",
                     [{"runnerId": rid, "maxRank": 1, "allAbilities": True}],
                     timeout=90).get("result") or {}
        if not _ok(dec):
            raise RuntimeError("decisionView KO")
        units = dec.get("units") or []
        caster = next((u for u in units
                       if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
        tgt = next((u for u in units
                    if u.get("visualId") == TARGET_VIS and u.get("alive")), None)
        if caster is None or tgt is None:
            raise RuntimeError("unite manquante (caster=%s tgt=%s)"
                               % (bool(caster), bool(tgt)))
        if my_player is None:
            my_player = caster.get("owner")
        if dec.get("currentPlayer") != my_player:
            R._rpc(sid, "applyAction",
                   [{"runnerId": rid, "action": {"kind": "endturn"}}], timeout=40)
            continue
        if tile_of(caster) in board.neighbours(tile_of(tgt)):
            return board, caster, tgt
        dist = _bfs(board, tile_of(tgt))
        mt = R._rpc(sid, "aiMovableTiles",
                    [{"runnerId": rid, "side": "friendly"}], timeout=60).get("result") or {}
        cmt = next((x for x in (mt.get("units") or [])
                    if x.get("unitId") == caster["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist]
        if not pool:
            R._rpc(sid, "applyAction",
                   [{"runnerId": rid, "action": {"kind": "endturn"}}], timeout=40)
            continue
        best = min(pool, key=lambda t: dist[t])
        col, row = reach[best]
        R._rpc(sid, "applyAction",
               [{"runnerId": rid, "action": {"kind": "move", "unitId": caster["id"],
                                             "to": {"col": col, "row": row}}}], timeout=40)
    raise RuntimeError("caster n'a pas atteint la cible en 25 tours")


def run(sid: int, state_file: str, board_id: str, seed: str, rank: int,
        sans_items: bool, neutraliser: bool = False, avec_board: bool = True) -> dict:
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent

    rid = monter(sid, state_file, board_id, seed, rank, sans_items, neutraliser)
    print("  runner %d monte (%s%s, board cote port : %s)"
          % (rid, "SANS items" if sans_items else "AVEC items",
             ", NEUTRALISE" if neutraliser else "", "OUI" if avec_board else "NON"))
    try:
        board, caster, tgt = approcher(sid, rid)
        att, tid = caster["id"], tgt["id"]

        # --- etape 1 : ETAT DE DEPART, par QUATRE canaux -------------------------------
        dv = R._rpc(sid, "decisionView",
                    [{"runnerId": rid, "maxRank": 1, "allAbilities": True}],
                    timeout=90).get("result") or {}
        ob = R._rpc(sid, "observeBattle", [{"runnerId": rid}], timeout=40).get("result") or {}
        snap = R._rpc(sid, "combatSnapshot", [{"runnerId": rid}], timeout=40).get("result") or {}
        # `board=` est LOAD-BEARING, et son absence est SILENCIEUSE : sans lui les feuilles
        # geometriques de l'arbre DSL (`PushUnit`, la charge `MoveUnit`) sont des no-op, donc le
        # port ne pousse pas, donc il ne peut pas non plus appliquer le KNOCKBACK du push bloque.
        # Meme vice que #63 sur le bonus d'ELEVATION, et meme parade que `_combat_replay._do_replay`.
        state = load_state(dv, ob, snap, board=(board if avec_board else None))
        te = state.get_entity(tid)
        hp_port = te.get_component(HealthComponent).hp if te is not None else None
        dv_hp = next((u.get("hp") for u in (dv.get("units") or []) if u.get("id") == tid), None)

        print("=== etape 1 -- ETAT DE DEPART de la cible (entite %s) ===" % tid)
        print("  observeBattle  : %s" % (_hp_observe(ob, tid),))
        print("  combatSnapshot : %s" % (_hp_snapshot(snap, tid),))
        print("  decisionView   : hp=%s" % (dv_hp,))
        print("  port (load_state -> HealthComponent.hp) : %s" % (hp_port,))

        s0 = R._rpc(sid, "dumpRng", [{"runnerId": rid}], timeout=30).get("result") or {}
        if not _ok(s0):
            raise RuntimeError("dumpRng KO")
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        state.rng = rng

        # --- etape 2 : le CAST, tous events -------------------------------------------
        res = R._rpc(sid, "applyAction",
                     [{"runnerId": rid, "action": {"kind": "ability", "casterId": att,
                                                   "targetId": tid,
                                                   "abilityType": ABILITY}}],
                     timeout=60).get("result") or {}
        a0 = (res.get("actions") or [{}])[0]
        if not (_ok(res) and a0.get("ok")):
            raise RuntimeError("cast KO : %s" % (str(res)[:240],))

        retenus, ecartes = [], []
        print("=== etape 2 -- EVENTS DU CAST (tous, pas seulement ceux du filtre) ===")
        print("  -- qui est qui : %s"
              % ({u.get("id"): u.get("visualId") for u in (dv.get("units") or [])},))
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" not in td:
                # Les events SANS `Amount` disent QUI fait quoi (Effect applique, ability
                # declenchee) -- c'est la que se lit l'origine d'un degat non attribue.
                print("    (hors-Amount) %s=%s" % (e.get("name") or e.get("type"), td))
                continue
            # TAGS BRUTS, jamais une liste blanche : un `Amount` non attribue par les clefs
            # connues est exactement ce qu'on cherche ici -- filtrer le ferait disparaitre.
            garde = (td.get("Target_Id") == tid
                     and td.get("Active_Ability_Type") == ABILITY)
            (retenus if garde else ecartes).append(td)
            print("    %-8s %s | %s" % ("RETENU" if garde else "ECARTE",
                                        e.get("name") or e.get("type"), td))
        if not retenus and not ecartes:
            print("    (aucun event porteur d'Amount)")

        live_after = next((u.get("hp") for u in (res.get("units") or [])
                           if u.get("squadId") == tid), None)
        ob2 = R._rpc(sid, "observeBattle", [{"runnerId": rid}], timeout=40).get("result") or {}

        # --- etape 3 : bilan par SOUSTRACTION ------------------------------------------
        hp_av = (_hp_observe(ob, tid) or {}).get("hp")
        hp_ap = (_hp_observe(ob2, tid) or {}).get("hp")
        somme_ret = sum(x.get("Amount") or 0 for x in retenus)
        somme_ecart = sum(x.get("Amount") or 0 for x in ecartes
                          if x.get("Target_Id") == tid)
        print("=== etape 3 -- BILAN NATIF PAR SOUSTRACTION ===")
        print("  hp avant (observeBattle) : %s" % (hp_av,))
        print("  hp apres (observeBattle) : %s   | applyAction.units.hp : %s"
              % (hp_ap, live_after))
        perdu = (hp_av - hp_ap) if (hp_av is not None and hp_ap is not None) else None
        print("  PV perdus                : %s" % (perdu,))
        print("  somme des Amount RETENUS : %s" % (somme_ret,))
        print("  somme des Amount ECARTES sur la cible : %s" % (somme_ecart,))
        reste = None if perdu is None else perdu - somme_ret - somme_ecart
        print("  RESTE INEXPLIQUE         : %s" % (reste,))

        # --- etape 3bis : LA GEOMETRIE DU PUSH ------------------------------------------
        # `ThunderousAssault` POUSSE la cible d'un hex. Push REUSSI -> la cible bouge, aucun
        # knockback ; push BLOQUE (bord / mur / occupant) -> la cible NE bouge PAS et prend
        # `ceil(maxHealth x BC.Damage.KnockbackPercentage/100)`. Les deux cotes doivent donc
        # d'abord s'accorder sur le DEPLACEMENT avant qu'un montant ait un sens.
        from engine.runner.components import PositionComponent as _PC

        def _pos_natif(d, uid):
            # Les positions vivent dans `decisionView`, PAS dans `observeBattle` (qui ne publie
            # ni `col` ni `row`) -- s'y tromper rend deux `None` qu'on lirait comme « immobile ».
            for u in (d.get("units") or []):
                if u.get("id") == uid:
                    p = u.get("pos") or {}
                    return (p.get("col"), p.get("row"))
            return None

        def _pos_port(st, uid):
            e = st.get_entity(uid)
            pc = e.get_component(_PC) if e is not None else None
            return None if pc is None else (getattr(pc, "col", None), getattr(pc, "row", None))

        dv2 = R._rpc(sid, "decisionView",
                     [{"runnerId": rid, "maxRank": 1, "allAbilities": True}],
                     timeout=90).get("result") or {}
        pos_av = {"caster": _pos_natif(dv, att), "cible": _pos_natif(dv, tid)}
        pos_ap = {"caster": _pos_natif(dv2, att), "cible": _pos_natif(dv2, tid)}
        pos_port_av = {"caster": _pos_port(state, att), "cible": _pos_port(state, tid)}

        # --- etape 4 : le PORT -----------------------------------------------------------
        runner = Runner(state).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=att, target_id=tid,
                                          ability_type=ABILITY))
        atk = (runner.ability_handler.last or {}).get("attack") or {}
        off_after = state.get_entity(tid).get_component(HealthComponent).hp
        pos_port_ap = {"caster": _pos_port(state, att), "cible": _pos_port(state, tid)}
        print("=== etape 3bis -- GEOMETRIE DU PUSH ===")
        print("  natif : caster %s -> %s | cible %s -> %s"
              % (pos_av["caster"], pos_ap["caster"], pos_av["cible"], pos_ap["cible"]))
        print("  port  : caster %s -> %s | cible %s -> %s"
              % (pos_port_av["caster"], pos_port_ap["caster"],
                 pos_port_av["cible"], pos_port_ap["cible"]))
        print("  board charge cote port : %s" % (getattr(state, "board", None) is not None,))
        print("=== etape 4 -- LE PORT ===")
        print("  hits=%s base=[%s,%s] pierce=%s armor=%s per_hit=%s"
              % (atk.get("hits"), atk.get("base_min"), atk.get("base_max"),
                 atk.get("pierce"), atk.get("armor"), atk.get("per_hit")))
        print("  hp apres (port) : %s   | live : %s   | ECART : %s"
              % (off_after, live_after,
                 None if (off_after is None or live_after is None)
                 else off_after - live_after))
        return {"rid": rid, "tid": tid, "att": att, "hp_avant": hp_av,
                "hp_apres_live": hp_ap, "hp_apres_port": off_after,
                "retenus": retenus, "ecartes": ecartes,
                "per_hit": atk.get("per_hit"), "reste": reste}
    finally:
        try:
            R._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            print("  runner %d dispose" % rid)
        except Exception as e:                                    # noqa: BLE001
            print("  [avertissement] dispose a echoue : %s" % e)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rank", type=int, default=17)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU et propre (hors data/)")
    ap.add_argument("--sans-items", action="store_true",
                    help="TEMOIN : rejoue le montage dans le regime d'avant #419-r5")
    ap.add_argument("--sans-board", action="store_true",
                    help="CONTRE-EPREUVE : ne passe PAS le board a `load_state` -- restitue le "
                         "montage d'origine, ou les feuilles geometriques sont des no-op")
    ap.add_argument("--neutraliser", action="store_true",
                    help="empeche la BASCULE DE TOUR (2e p-unit qui n'a pas agi), donc les "
                         "effets de turn-start adverse -- c'est le montage que le test adopte")
    a = ap.parse_args(argv)

    sid = R._resolve_session()
    print("[419-r6] session %d | ecart PV sur %s -> %s (ability %d)"
          % (sid, CASTER_VIS, TARGET_VIS, ABILITY))
    run(sid, a.state_file, a.board, a.seed, a.rank, a.sans_items, a.neutraliser,
        avec_board=not a.sans_board)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
