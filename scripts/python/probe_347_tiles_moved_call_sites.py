"""probe #347 (residu #335-r1) -- les call-sites de `RecordTilesMoved` que #335/#340 n'avaient pas
portes : `DisplaceUnitOperation$$AddTilesMoved` (switch/teleport) et `ReviveUnitOperation$$
SetRevivePosition`.

LE CRITERE, pose AVANT toute methode
------------------------------------
Question binaire : **apres un SWITCH, le compteur `ActorStatisticsComponent+0xf0` des deux unites
vaut-il la DISTANCE HEXAGONALE entre leurs tuiles, cote NATIF comme cote PORT ?**

CE QUI BLOQUE LA MESURE, ET QUI EST DIT PLUTOT QUE CONTOURNE
-----------------------------------------------------------
Le compteur n'a **aucun lecteur** utilisable sur ce montage :

* le capteur direct `actorStats.tilesMovedThisTurn` a bien ete livre par #340
  (`frida/hooks/features/ai-step/rpc-snapshot.ts`) mais **n'est PAS deploye** -- le hook actif rend
  `actorStats` sans les trois champs `tilesMoved*`. `assert_sensor()` ci-dessous le VERIFIE et
  l'annonce ; il ne rend jamais un zero silencieux ;
* la voie indirecte de #335 (le degat de `ModifiedExoarmour_ExtraDmg`, seul consommateur porte de
  `DSLFormulas$$TilesMovedThisTurn`) exige que l'unite DEPLACEE soit `votanChampion`. Or les trois
  mecanismes ne l'atteignent pas : `SorcerousFacade` (le seul porteur de `SwitchPosition`) exige une
  cible **Psyker**, que Kimm n'est pas (`Hero`, `PrioritisedEfficiency`, `Unstoppable`) ; le
  `Teleport` DSL n'a qu'un porteur (`ExemplarOfTheKauyon`, `tauShadowsun`) et il teleporte le
  CASTER ; le revive A POSITION n'existe que via le `GhostEffect` de `thousTerminator`, qui
  ressuscite son propre porteur. Les trois autres consommateurs du compteur
  (`EmpyricAmbush`/`eldarLhykhis`, `SmashaEad`/`orksNob`, `MastersOfManoeuvre`/`darkaStormSpeeder`)
  ne sont pas Psyker non plus.

Ce que ce probe MESURE donc, sans capteur :
  * que le cast 1100 ECHANGE bien les deux tuiles, et **de combien** (la distance hex, entree de
    `AddTilesMoved`) ;
  * ce que le PORT enregistre pour chacune des deux unites apres le meme cast rejoue hors-ligne.
Le verdict NATIF reste **NON CONFRONTE** tant que le capteur n'est pas injecte ; le montage est
pret et le probe le jouera tel quel.

CE QUE LE DECOMPILE DIT (relu sur `rnca9r7q6c`, cf. `docs/rl/case-347-tiles-moved-call-sites.md`)
------------------------------------------------------------------------------------------------
    DisplaceUnitOperation$$AddTilesMoved(caster, target, prev, dest, options):
        if (options.<+0x10>)                            // = DisplaceUnitBehaviourOptions+0x1c
            if (!IsEnemy(caster, target, state))
                RecordTilesMoved(target, GetDistance(prev, [dest]), state);

    Seules `DSLBehaviors$$SwitchPosition` et `DSLBehaviors$$Teleport` posent `+0x1c = 1` ; les six
    autres feuilles (dont TOUS les push) le laissent a 0 -> un push n'enregistre RIEN.

Usage :
    python probe_347_tiles_moved_call_sites.py                 # bras switch, MC1_67 / 909
    python probe_347_tiles_moved_call_sites.py --gap 2
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import hexgeo
import probe_27_custom_utility_inventory as INV
from engine.entities.pathfinding.board import Board
from engine.runner.components import unit_tiles_moved_this_turn
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOGS = ROOT / "logs"
STATE = LOGS / "rs_347_tiles_moved.json"

BOARD = "MC1_67"
SEED = 909
SWITCH_CASTER = "thousTzaangor"          # Yazaghor -- seul porteur de 1100 SorcerousFacade
SWITCH_ALLY = "thousSorcerer"            # allie PSYKER (la regle dynamique de 1100 l'exige)
ENEMY_VIDS = "necroOverlord,necroWarden"
SORCEROUS_FACADE = 1100

_WAIT_MARKERS = ("runner cap reached", "runner creation paused")
_WAIT_MAX_S = 300.0
_WAIT_POLL_S = 15.0


def _rpc(method, body=None, timeout_ms=90000):
    return INV.rpc(INV._session_id(), method, [body] if body is not None else [], timeout_ms)


def _upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


class Harness:
    def __init__(self, rid: int, board: Board):
        self.rid, self.board = rid, board
        self.my_player = None

    def dview(self):
        return _rpc("decisionView", {"runnerId": self.rid, "maxRank": 1, "allAbilities": True})

    def alive(self, dv=None):
        dv = dv if dv is not None else self.dview()
        return [u for u in (dv.get("units") or []) if u.get("alive")]

    def by_visual(self, vid, dv=None):
        return next((u for u in self.alive(dv) if u.get("visualId") == vid), None)

    def sensor_state(self) -> dict:
        """Tri-etat EXPLICITE du capteur `+0xf0` : `{deployed, sample}`. `deployed=False` veut dire
        « le hook actif ne publie pas `tilesMovedThisTurn` » -- PAS « le compteur vaut zero »."""
        r = _rpc("actorStats", {"runnerId": self.rid}, 40000)
        if not (isinstance(r, dict) and r.get("ok")):
            return {"deployed": None, "error": r}
        units = r.get("units") or []
        deployed = bool(units) and "tilesMovedThisTurn" in units[0]
        return {"deployed": deployed,
                "sample": units[0] if units else None,
                "by_id": ({int(u["entityId"]): int(u["tilesMovedThisTurn"]) for u in units}
                          if deployed else None)}

    def snapshot(self):
        return {"dv": self.dview(),
                "ob": _rpc("observeBattle", {"runnerId": self.rid}, 40000),
                "snap": _rpc("combatSnapshot", {"runnerId": self.rid}, 60000),
                "rng": _rpc("dumpRng", {"runnerId": self.rid}, 30000)}

    def reach_my_turn(self, max_end_turns=12, force_cycle=False):
        dv = self.dview()
        if self.my_player is None:
            mine = self.alive(dv)
            self.my_player = mine[0].get("owner") if mine else None
        if force_cycle and dv.get("currentPlayer") == self.my_player:
            _rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 40000)
            dv = self.dview()
        for _ in range(max_end_turns):
            if dv.get("currentPlayer") == self.my_player:
                return dv
            _rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 40000)
            dv = self.dview()
        return dv if dv.get("currentPlayer") == self.my_player else None

    def place(self, unit_id, coord) -> bool:
        _rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "move", "unitId": unit_id,
            "to": {"col": int(coord[0]), "row": int(coord[1])}}}, 40000)
        u = next((x for x in self.alive() if x.get("id") == unit_id), None)
        return u is not None and _upos(u) == (int(coord[0]), int(coord[1]))

    def free_tiles(self, center, radius, exclude=()):
        occupied = {_upos(u) for u in self.alive() if u.get("id") not in set(exclude)}
        out = []
        for t in sorted(self.board.by_id):
            c = self.board.coord(t)
            if (self.board.walkable(t) and hexgeo.distance(tuple(center), c) == radius
                    and c not in occupied and c != tuple(center)):
                out.append(c)
        return out

    def dispose(self):
        _rpc("disposeRunner", {"runnerId": self.rid}, 20000)


def build(p_units: str, board: str = BOARD, seed: int = SEED) -> Harness:
    """EXIGE un runner NEUF : `rl_duel build` peut REFUSER sans lever, et on relirait l'ANCIEN
    runner du meme `--state-file` (piege documente par #322 SS5)."""
    before = None
    if STATE.exists():
        try:
            before = int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])
        except Exception:                                  # noqa: BLE001
            before = None
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", str(STATE), "--p-units", p_units, "--a-units", ENEMY_VIDS,
            "--hp-target", "300000", "--hp-player", "300000", "--no-ai"]

    def _attempt() -> str:
        STATE.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(HERE), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return (p.stderr or p.stdout or "")

    out = _attempt()
    waited = 0.0
    while (not STATE.exists()) and any(m in out for m in _WAIT_MARKERS) and waited < _WAIT_MAX_S:
        time.sleep(_WAIT_POLL_S)
        waited += _WAIT_POLL_S
        out = _attempt()
    if not STATE.exists():
        raise RuntimeError("build refuse apres %.0fs : %s" % (waited, out[-400:]))
    rid = int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])
    if before is not None and rid == before:
        raise RuntimeError("build REFUSE (runner inchange : %d)" % rid)
    bg = _rpc("boardGraph", {"runnerId": rid}, 60000)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible pour le runner %d" % rid)
    return Harness(rid, Board(bg["tiles"], adjacency="native_sym"))


def arm_switch(gap: int = 3, board: str = BOARD, seed: int = SEED) -> dict:
    """`thousTzaangor` cast 1100 sur `thousSorcerer` place a distance hex `gap` -> la triggered 1180
    echange les deux tuiles. Rend le releve LIVE (positions, distance) + le rejeu OFFLINE du meme
    cast (compteurs du PORT) + l'etat du capteur natif."""
    h = build("%s,%s" % (SWITCH_CASTER, SWITCH_ALLY), board=board, seed=seed)
    try:
        dv = h.dview()
        me = h.by_visual(SWITCH_CASTER, dv)
        ally = h.by_visual(SWITCH_ALLY, dv)
        if me is None or ally is None:
            raise RuntimeError("montage NON INSTALLE : caster=%s ally=%s" % (me, ally))
        h.my_player = me.get("owner")
        enemies = [u for u in h.alive(dv) if u.get("owner") != h.my_player]
        # Un `applyAction move` reste borne par la portee : l'ancre du caster est sa position
        # COURANTE, et on ITERE sur les tuiles candidates de l'allie jusqu'a un pas reellement joue.
        anchor = _upos(me)
        # Le terme [2] du cast est une ATTAQUE NORMALE sur l'ennemi le plus proche : il faut donc
        # un ennemi ATTEIGNABLE, sinon la regle dynamique de 1100 refuse le cast (#287).
        foe = None
        for c in h.free_tiles(anchor, 1, exclude=(enemies[0]["id"],)):
            if h.place(enemies[0]["id"], c):
                foe = enemies[0]
                break
        for other in enemies[1:]:
            far = h.free_tiles(anchor, 6, exclude=(other["id"],))
            if far:
                h.place(other["id"], far[0])
        dest = None
        for c in h.free_tiles(anchor, gap, exclude=(ally["id"],)):
            if h.place(ally["id"], c):
                dest = c
                break
        if dest is None:
            raise RuntimeError("allie non pose a distance %d de %s (aucune tuile atteignable)"
                               % (gap, anchor))
        if h.reach_my_turn(force_cycle=True) is None:
            raise RuntimeError("mon tour inatteignable")
        dv = h.dview()
        pos = {u["id"]: _upos(u) for u in h.alive(dv)}
        if pos.get(me["id"]) != anchor or pos.get(ally["id"]) != dest:
            raise RuntimeError("geometrie perdue apres le cycle de tour : %s" % pos)
        sensor_before = h.sensor_state()
        snap = h.snapshot()
        res = _rpc("applyAction", {"runnerId": h.rid, "action": {
            "kind": "ability", "casterId": me["id"], "targetId": ally["id"],
            "abilityType": SORCEROUS_FACADE}}, 90000)
        sensor_after = h.sensor_state()
        dv2 = h.dview()
        pos2 = {u["id"]: _upos(u) for u in h.alive(dv2)}
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        switched = pos2.get(me["id"]) == dest and pos2.get(ally["id"]) == anchor
        # --- rejeu OFFLINE du MEME cast : ce que le PORT enregistre -------------------------------
        st = load_state(snap["dv"], snap["ob"], snap["snap"], board=h.board)
        runner = Runner(st).install_default_handlers(20)
        from engine.runner.messages import ActiveAbilityMessage
        runner.apply(ActiveAbilityMessage(caster_id=me["id"], target_id=ally["id"],
                                          ability_type=SORCEROUS_FACADE))
        from engine.runner.components import PositionComponent
        off_pos = {}
        for uid in (me["id"], ally["id"]):
            e = st.get_entity(uid)
            pc = e.get_component(PositionComponent) if e is not None else None
            off_pos[uid] = (pc.col, pc.row) if pc is not None else None
        port_counter = {uid: unit_tiles_moved_this_turn(st, uid) for uid in (me["id"], ally["id"])}
        return {"harness": h, "kind": "switch", "gap": int(gap),
                "caster": me["id"], "ally": ally["id"], "foe": (foe or {}).get("id"),
                "caster_from": anchor, "ally_from": dest,
                "caster_to": pos2.get(me["id"]), "ally_to": pos2.get(ally["id"]),
                "hex_distance": hexgeo.distance(anchor, dest),
                "cast_ok": bool(isinstance(res, dict) and res.get("ok") and a0.get("ok")),
                "mutated": bool(a0.get("mutated")), "switched": switched,
                "sensor_before": sensor_before, "sensor_after": sensor_after,
                "off_pos": off_pos, "port_counter": port_counter, "cast_raw": res}
    except Exception:
        h.dispose()
        raise


def _report(rec):
    print("== bras %s (gap demande=%d) ==" % (rec["kind"], rec["gap"]))
    print("   cast_ok=%s mutated=%s switched=%s" % (rec["cast_ok"], rec["mutated"],
                                                    rec["switched"]))
    print("   distance hex entre les deux tuiles : %d" % rec["hex_distance"])
    print("   LIVE    caster %s -> %s | allie %s -> %s"
          % (rec["caster_from"], rec["caster_to"], rec["ally_from"], rec["ally_to"]))
    print("   OFFLINE caster %s        | allie %s"
          % (rec["off_pos"].get(rec["caster"]), rec["off_pos"].get(rec["ally"])))
    print("   compteur PORT apres le cast : caster=%d allie=%d"
          % (rec["port_counter"][rec["caster"]], rec["port_counter"][rec["ally"]]))
    sb, sa = rec["sensor_before"], rec["sensor_after"]
    if sb.get("deployed"):
        print("   compteur NATIF : avant=%s apres=%s" % (sb.get("by_id"), sa.get("by_id")))
    else:
        print("   compteur NATIF : NON MESURE -- le capteur `actorStats.tilesMovedThisTurn` "
              "(#340) n'est pas deploye (champs publies : %s)"
              % sorted((sb.get("sample") or {}).keys()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--gap", type=int, default=3)
    a = ap.parse_args()
    rec = None
    try:
        rec = arm_switch(gap=a.gap, board=a.board, seed=a.seed)
        _report(rec)
    finally:
        if rec is not None:
            try:
                rec["harness"].dispose()
            except Exception:                              # noqa: BLE001
                pass


if __name__ == "__main__":
    main()
