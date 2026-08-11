"""#419-r1-tr5-r7 -- face **COMBAT** de `LightImUp` (1103, passif de kit d'`orksWarboss`).

RE + residus : `engine/runner/operations/triggers/loki/light_im_up.py`.
La face DECISION (playbook) est portee et confrontee ailleurs (#419-r1-tr5) ; elle ne dit RIEN de
celle-ci, qui etait un NO-OP SILENCIEUX (absente d'`ABILITY_TRIGGERS`).

MONTAGE : `orksWarboss` cote JOUEUR, deux ennemis. On DRIVE la position (doctrine : on deplace les
unites pour realiser la configuration, on ne subit pas la geometrie de spawn) pour amener le
warboss au contact d'une cible T1, avec T2 dans le disque `range = 3` du passif. Puis on joue
l'ATTAQUE NORMALE, live et offline, sur le MEME etat et le MEME flux RNG (`dumpRng`).

ETAGES CONFRONTES (jamais un scalaire agrege) :
  0. l'ability est-elle CABLEE (`ABILITY_TRIGGERS`) -- sans quoi tout le reste est vide ;
  1. le passif FIRE-t-il live -- nombre d'events de degat imputes a 1103 sur T1 ;
  2. les PV de T1 -- offline vs live (l'attaque normale + les `nrOfHits` coups du passif) ;
  3. les PV de T2 -- le report du volet 2 quand T1 MEURT (`IsDead` -> `NumLeftOverHits`) ;
  4. les PV de TOUTES les unites -- aucun degat fantome ailleurs.

`--kill` monte le regime ou T1 meurt (PV bas) : c'est le SEUL regime qui exerce le volet 2.

ASCII only (cp1252). Usage :
    python probe_419r1tr5r7_light_im_up_combat.py [--seed 419503] [--board MC1_67]
        [--hp-target 900000] [--kill] [--state-file <ABS>] [--mutant none|no-registry|melee-gate]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from probe_116_necrons import (_alive_units, _build, _capture, _dispose, _r,          # noqa: E402
                               _unit_of)
from rl_collect_batch import _resolve_session                                         # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType               # noqa: E402
from engine.runner.components import HealthComponent                                  # noqa: E402
from engine.runner.messages import AttackUnitMessage                                  # noqa: E402
from engine.runner.runner import Runner                                               # noqa: E402

ROOT = PYDIR.parents[1]
WARBOSS = "orksWarboss"
LIGHT_IM_UP_ID = int(TriggeredAbilityType.LightImUp)          # 1103


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _normal_attack_id(dec, uid):
    """L'attaque normale EST une ability, de type PER-UNIT (`NormalAttackType@0x28`) : on la LIT
    dans `decisionView`, on ne la devine pas."""
    for u in _alive_units(dec):
        if int(u["id"]) == int(uid):
            for ab in (u.get("abilities") or []):
                if ab.get("kind") == "normal":
                    return int(ab["id"])
    return None


def _hp_by_id(dec):
    return {int(u["id"]): u.get("hp") for u in (dec.get("units") or [])}


def _dist(board, a, b):
    from collections import deque
    src = board.id_at(a[0], a[1])
    dst = board.id_at(b[0], b[1])
    if src is None or dst is None:
        return None
    seen = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        if x == dst:
            return seen[x]
        for n in board.neighbours(x):
            if n not in seen:
                seen[n] = seen[x] + 1
                q.append(n)
    return None


def _drive_adjacent(sid, rid, board, caster_vid, want_dist=1, turns=30):
    """DEPLACE le caster jusqu'a la distance EXACTE `want_dist` de l'ennemi le plus proche.

    ⚠ La cible de distance est EXACTE, pas un plafond : le premier jet s'arretait a `d <=
    want_dist` et rendait donc TOUJOURS d = 1 -- le regime A DISTANCE, celui qui rend la gate de
    melee discriminante, n'etait jamais atteint et le mutant serait passe pour vert."""
    for _ in range(turns):
        dec = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        cu = _unit_of(dec, caster_vid)
        if cu is None:
            return dec, None, None
        foes = [u for u in _alive_units(dec) if u.get("owner") != cu.get("owner")]
        if not foes:
            return dec, int(cu["id"]), None
        best = min(foes, key=lambda u: (_dist(board, _pos(cu), _pos(u)) or 99))
        d = _dist(board, _pos(cu), _pos(best))
        if d == want_dist:
            return dec, int(cu["id"]), int(best["id"])
        if dec.get("currentPlayer") != cu.get("owner"):
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        mt = _r(sid, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        row = next((x for x in (mt.get("units") or []) if int(x.get("unitId") or -1) == int(cu["id"])),
                   None)
        tiles = list((row or {}).get("tiles") or [])
        if not tiles:
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        tgt = _pos(best)
        # tuile dont la distance a T1 est la plus PROCHE de `want_dist` (en valeur absolue) : on
        # peut donc aussi s'ELOIGNER, ce qu'un tri par distance croissante ne permet pas.
        tiles.sort(key=lambda t: abs((_dist(board, (t["col"], t["row"]), tgt) or 99) - want_dist))
        t0 = tiles[0]
        if (_dist(board, (t0["col"], t0["row"]), tgt) or 99) == d:
            return dec, int(cu["id"]), int(best["id"])       # plus rien a gagner : on rend l'etat
        _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": int(cu["id"]), "to": {"col": t0["col"], "row": t0["row"]}}}, 40)
    dec = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    cu = _unit_of(dec, caster_vid)
    return dec, (int(cu["id"]) if cu else None), None


def _events_by_ability(res):
    """{abilityType -> [(target_id, amount)]} depuis les events d'`applyAction(captureEvents)`."""
    out: dict = {}
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" not in td:
                continue
            key = td.get("Active_Ability_Type")
            out.setdefault(key, []).append((td.get("Target_Id"), td.get("Amount")))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="419503")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--rank", default="17")
    ap.add_argument("--hp-target", default="900000")
    ap.add_argument("--hp-player", default="900000")
    ap.add_argument("--a-units", default="necroWarden,astraBullgryn")
    ap.add_argument("--kill", action="store_true",
                    help="PV de T1 tres bas -> le volet 2 (report) s'exerce")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--unit-stat", action="append", default=[],
                    help="patch PER-UNIT du BC NORMALISE, pass-through vers `rl_duel build`. "
                         "C'est le SEUL moyen de dissocier les PV de T1 et de T2 : `--hp-target` "
                         "force une valeur unique sur tout le camp (et met l'armure a 0). Poser "
                         "`RemainingHealth` EN PLUS de `Health` -- le natif lit le premier.")
    ap.add_argument("--dump-tags", action="store_true", help="imprime les TAGS BRUTS des events de degat")
    ap.add_argument("--dist", type=int, default=1,
                    help="distance VOULUE entre le caster et T1. `orksWarboss` porte DEUX armes "
                         "(melee Eviscerate 2 coups + Projectile Range 3, 1 coup) : a d >= 2 il "
                         "attaque A DISTANCE, ce qui rend la gate de melee DISCRIMINANTE.")
    ap.add_argument("--no-hp-target", action="store_true",
                    help="n'envoie PAS `--hp-target` (qui met Armor/FixedArmor a 0)")
    ap.add_argument("--mutant", default="none",
                    choices=["none", "no-registry", "melee-gate"],
                    help="contre-epreuves : retirer le port du registre ; ajouter une gate de melee")
    args = ap.parse_args()

    # --- etage 0 : CABLAGE (sans lui, tous les autres etages sont vides par construction) --------
    import engine.runner.operations.triggers.dispatch.registry as REG
    cabled = list(REG.ABILITY_TRIGGERS.get("LightImUp") or [])
    print(f"[tr5r7] etage 0 CABLAGE : ABILITY_TRIGGERS['LightImUp'] = "
          f"{[c.__name__ for c in cabled]}")
    if args.mutant == "no-registry":
        REG.ABILITY_TRIGGERS.pop("LightImUp", None)
        print("[tr5r7] MUTANT no-registry : entree RETIREE du registre")
    if args.mutant == "melee-gate":
        import engine.runner.operations.triggers.loki.light_im_up as M
        from engine.runner.operations.triggers.base import _is_adjacent_units
        _orig = M.LightImUpAbility.matches

        def _melee(self, state, ev):
            if not _orig(self, state, ev):
                return False
            return _is_adjacent_units(state, ev.actor_id, ev.target_id)
        M.LightImUpAbility.matches = _melee
        print("[tr5r7] MUTANT melee-gate : gate d'adjacence AJOUTEE (le voisin de forme)")

    st_file = Path(args.state_file or (ROOT / "logs" / "runners" / "_419r1tr5r7_state.json"))
    st_file.parent.mkdir(parents=True, exist_ok=True)
    sid = _resolve_session()
    hp_t = "2600" if args.kill else args.hp_target
    build_args = ["--seed", str(args.seed), "--board", args.board, "--rank", args.rank,
                  "--p-units", WARBOSS, "--a-units", args.a_units, "--no-ai",
                  "--hp-player", args.hp_player]
    if not args.no_hp_target:
        build_args += ["--hp-target", hp_t]
    for us in args.unit_stat:
        build_args += ["--unit-stat", us]
    rid = _build(st_file, build_args)
    print(f"[tr5r7] runner={rid} session={sid} board={args.board} seed={args.seed} "
          f"hp-target={hp_t} mutant={args.mutant}")
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
        from engine.entities.pathfinding.board import Board
        board = Board(bg["tiles"], adjacency="evenq")
        dec, cid, t1 = _drive_adjacent(sid, rid, board, WARBOSS, want_dist=int(args.dist))
        if cid is None or t1 is None:
            print("[tr5r7] ECHEC MONTAGE : caster ou cible introuvable")
            return 2
        mkstate, dec, board = _capture(sid, rid)
        cu = _unit_of(dec, WARBOSS)
        foes = [u for u in _alive_units(dec) if u.get("owner") != cu.get("owner")]
        d_by = {int(u["id"]): _dist(board, _pos(cu), _pos(u)) for u in foes}
        t1 = min(d_by, key=lambda k: d_by[k])
        others = sorted([k for k in d_by if k != t1], key=lambda k: d_by[k])
        print(f"[tr5r7] caster={cid} T1={t1} (d={d_by[t1]}) autres={[(k, d_by[k]) for k in others]}")
        nat = _normal_attack_id(dec, cid)
        if nat is None:
            print("[tr5r7] ECHEC MONTAGE : pas d'attaque normale sur le caster")
            return 2
        hp0 = _hp_by_id(dec)
        state = mkstate()
        if state.rng is None:
            print("[tr5r7] ECHEC MONTAGE : rng non cale (dumpRng)")
            return 2
        # --- LIVE ---------------------------------------------------------------------------
        res = _r(sid, "applyAction", {"runnerId": rid, "captureEvents": True, "action": {
            "kind": "ability", "casterId": int(cid), "targetId": int(t1),
            "abilityType": int(nat)}}, 120)
        a0 = (res.get("actions") or [{}])[0]
        if not (res.get("ok") and a0.get("ok")):
            print(f"[tr5r7] ECHEC : attaque live KO {str(res)[:300]}")
            return 2
        # PV LIVE : relus dans un `decisionView` POSTERIEUR a l'action, jamais dans
        # `applyAction().units` -- mesure du 2026-08-11 : ce dernier a rendu `hp` INCHANGE pour une
        # unite que ses propres events montraient frappee deux fois (u77 : events 309 + 279, `units`
        # = 900000). Un capteur qui ne voit pas la mutation qu'il doit juger fabrique une fausse
        # divergence ; on lit donc l'ETAT, pas le compte rendu de l'action.
        dec2 = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob2 = _r(sid, "observeBattle", {"runnerId": rid}, 40)
        live_hp_dec = _hp_by_id(dec2)
        live_hp_action = {int(u["squadId"]): u.get("hp") for u in (res.get("units") or [])
                          if u.get("squadId") is not None}
        live_hp_ob = {}
        for u in (ob2.get("units") or []):
            uid = u.get("id") if u.get("id") is not None else u.get("unitId")
            if uid is not None:
                live_hp_ob[int(uid)] = u.get("hp") if u.get("hp") is not None else u.get("health")
        # 3e source, la SEULE qui soit dans le flux de l'action : le dernier `UnitStats_
        # RemainingHealth` que le natif a lui-meme ecrit sur la cible.
        live_hp_evt = {}
        for act in (res.get("actions") or []):
            for e in (act.get("events") or []):
                td = e.get("tags")
                if not td:
                    continue
                td = json.loads(td) if isinstance(td, str) else td
                if "UnitStats_RemainingHealth" in td and td.get("Target_Id") is not None:
                    live_hp_evt[int(td["Target_Id"])] = td["UnitStats_RemainingHealth"]
        live_hp = dict(live_hp_dec)
        for k, v in live_hp_evt.items():                # l'event PRIME (cf. commentaire ci-dessus)
            live_hp[k] = v
        by_ab = _events_by_ability(res)
        n_passif = len(by_ab.get(LIGHT_IM_UP_ID) or [])
        print(f"[tr5r7] etage 1 events par abilityType : "
              f"{ {k: len(v) for k, v in by_ab.items()} }")
        for k, v in by_ab.items():
            tot = sum(int(a or 0) for _t, a in v)
            print(f"[tr5r7]         abilityType={k!s:<6} n={len(v)} total={tot} detail={v}")
        if args.dump_tags:
            print("[tr5r7] TAGS BRUTS des events porteurs d'un `Amount` :")
            for act in (res.get("actions") or []):
                for e in (act.get("events") or []):
                    td = e.get("tags")
                    if not td:
                        continue
                    td = json.loads(td) if isinstance(td, str) else td
                    if "Amount" in td:
                        print("   " + json.dumps(td, sort_keys=True))
        # `AbilityOrEffect(this.Id)` d'un TRIGGERED n'est pas un `ActiveAbilityType` : le tag
        # `Active_Ability_Type` du natif rend donc `None` pour les coups du passif (les coups de
        # l'attaque normale portent, eux, l'id PER-UNIT lu dans `decisionView`).
        n_passif = len(by_ab.get(None) or []) if not (by_ab.get(LIGHT_IM_UP_ID)) else n_passif
        print(f"[tr5r7]         coups imputes au PASSIF (tag Active_Ability_Type absent) : "
              f"{n_passif}")
        # --- OFFLINE ------------------------------------------------------------------------
        runner = Runner(state).install_default_handlers(20)
        runner.apply(AttackUnitMessage(int(cid), int(t1)))
        off_hp = {}
        for uid in set(list(hp0.keys())):
            e = state.get_entity(uid)
            hc = e.get_component(HealthComponent) if e is not None else None
            if hc is not None:
                off_hp[uid] = hc.hp
        # --- verdicts -------------------------------------------------------------------------
        rc = 0
        print("[tr5r7] etages 2-4 -- PV par unite (hp0 / live / offline) :")
        for uid in sorted(hp0):
            lv = live_hp.get(uid)
            of = off_hp.get(uid)
            tag = "T1" if uid == t1 else ("CASTER" if uid == cid else "")
            mark = "OK " if lv == of else "DIFF"
            if lv != of:
                rc = 1
            print(f"   {mark} u{uid:<4} {tag:<7} hp0={hp0.get(uid)!s:<9} "
                  f"live={lv!s:<9} off={of!s:<9} "
                  f"[dec={live_hp_dec.get(uid)!s} ob={live_hp_ob.get(uid)!s} "
                  f"evt={live_hp_evt.get(uid)!s} act={live_hp_action.get(uid)!s}]")
        if live_hp.get(t1) == hp0.get(t1):
            print("[tr5r7] !! REGIME SATURE : T1 n'a RIEN encaisse live -- le montage n'exerce rien")
            rc = max(rc, 3)
        print(f"[tr5r7] VERDICT rc={rc}")
        return rc
    finally:
        _dispose(st_file)


if __name__ == "__main__":
    sys.exit(main())
