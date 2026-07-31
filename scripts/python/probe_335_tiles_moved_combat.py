"""probe #335 (residu #322-r1) -- FACE COMBAT de `ModifiedExoarmour_ExtraDmg` : le compteur de
TUILES PARCOURUES arrive-t-il jusqu'au degat REELLEMENT inflige ?

LE CRITERE, pose AVANT toute methode
------------------------------------
Question binaire : **le degat de COMBAT d'une attaque de melee de Kimm apres un deplacement de `n`
tuiles vaut-il `base + V x n` par coup, avec le MEME `n` que celui du deplacement joue ?**

Deux valeurs de `n` au MINIMUM, sinon on ne distingue pas « le compte est threade » de « une
constante heureuse » : un port qui facturerait `V x 1` quel que soit le pas passerait un scenario a
une seule valeur de `n`.

CE QUE LE DECOMPILE DIT (relu sur `rnca9r7q6c`, cf. `docs/rl/case-322-modified-exoarmour-extradmg.md`)
------------------------------------------------------------------------------------------------
    IdunBattle.Entities.UnitExtensions$$RecordTilesMoved(unit, tiles, state):
        if ((int)tiles < 1) return;
        comp[0xec] += tiles;      // ActorStatisticsComponent, cumul BATAILLE
        comp[0xf0] += tiles;      // cumul CE TOUR  <- ce que lit TilesMovedThisTurnFormula

    IdunBattle.Operations.MoveUnitOperation$$Execute, branche REELLE :
        ... SetMovedFlag -> Add(ArrivedAtFinalTile) -> RemoveReservation
        if (options.<+0x16> == 0) {
            n = BattleQuery.GetNumTilesMoved(connectedPath);   // = path.Count - 1
            RecordTilesMoved(unit, n, state);
        }
        ... RefreshEffects(RefreshTrigger.UnitPositionChanged = 7) -> EvaluateAfterMoveTriggers

    IdunBattle.Operations.EndTurnOperation$$Execute, sur GetAllUnits :
        ActorStatisticsComponent$$ResetThisTurn(comp, wasOwnTurn):
            if (wasOwnTurn) comp[0xf4] = comp[0xf0];
            comp[0xf0] = 0;                                    // reset INCONDITIONNEL

⚠ La branche REELLE n'a PAS le gate `HasTriggeredAbility(0x5f9) || (0x4de)` de
`MoveUnitOperation$$GetNumTilesMovedForSimulation` : ce gate n'existe QUE cote SIMULATION.

MONTAGE (et pourquoi chaque marche existe)
------------------------------------------
  * `votanChampion` (Kimm) est HORS du seed BC (les 4 Votann n'y sont pas) -> injection catalogue
    (`catalog_inject.write_augmented_seed_bc`), jamais un clone a la main de `BC.Units`.
  * On DEPLACE les unites pour obtenir la geometrie voulue -- jamais « bloque par la geometrie de
    spawn ». La cible est ancree sur une tuile a >= 3 voisins libres ; Kimm part d'une tuile a
    distance hex `n` d'une tuile ADJACENTE a la cible.
  * **`reach_my_turn(force_cycle=True)` est OBLIGATOIRE apres le placement** : chaque `applyAction
    move` du montage est un vrai `MoveUnitOperation`, donc il ENREGISTRE des tuiles. Sans un
    `endturn` complet (= `EndTurnOperation` = `ResetThisTurn`), le compteur du montage survivrait
    dans le snapshot cote LIVE et serait INVISIBLE cote offline (aucun capteur ne publie `+0xf0`,
    residu #322-r2) : l'ecart se lirait comme un bug de port alors que c'est le MONTAGE qui triche.
    C'est le meme piege, a l'identique, que celui documente dans `_charge_regime.arrange`.
  * SNAPSHOT **avant** le pas : c'est le pas lui-meme qui remplit le compteur, donc l'offline doit
    le REJOUER (`MoveUnitMessage`), jamais le declarer -- declarer court-circuiterait justement le
    morceau de port qu'on confronte.
  * RE-SEED du MT **apres** le pas live : les deux cotes doivent partir du meme etat de PRNG pour
    que seule l'ATTAQUE soit comparee.

VERDICTS RENDUS (par valeur de `n`)
-----------------------------------
  `live_per_hit` / `off_per_hit`  : les coups, live et rejeu offline (doivent etre EGAUX) ;
  `n`                             : le compteur du port apres le pas rejoue ;
  `off_per_hit_zero`              : le MEME rejeu avec le compteur FORCE a 0 (contrefactuel : si
                                    c'est identique, le montage ne mesure RIEN) ;
  `off_per_hit_n1`                : le MEME rejeu avec le compteur FORCE a 1 -- c'est CE bras qui
                                    separe « threade » de « constante heureuse ».

Usage :
    python probe_335_tiles_moved_combat.py                     # MC1_67 / 909, n = 1 et 2
    python probe_335_tiles_moved_combat.py --board C1_25 --seed 31337
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
from engine.runner.components import UnitComponent, unit_tiles_moved_this_turn
from engine.runner.messages import AttackUnitMessage, MoveUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOGS = ROOT / "logs"
SEED_BC = LOGS / "bc_335_kimm.json"
STATE = LOGS / "rs_335_tiles_moved.json"

BOARD = "MC1_67"
SEED = 909
CASTER_VID = "votanChampion"                 # << Kimm >> -- porteuse de ModifiedExoarmour (0x5f9)
ENEMY_VIDS = "necroOverlord,necroWarden"
EXOARMOUR_EFFECT_TYPE = 1544                 # 0x608 "ModifiedExoarmour_ExtraDmg"
WITNESS_EFFECT_TYPE = 1543                   # 0x607 "ModifiedExoarmour_PierceReduction" (temoin)

# Indisponibilite TEMPORAIRE du harnais -- memes marqueurs que `tests/conftest.py` (cap de runners
# sature cote hooks, mode DRAIN cote host). On ATTEND, on ne conclut RIEN.
_WAIT_MARKERS = ("runner cap reached", "runner creation paused")
_WAIT_MAX_S = 300.0
_WAIT_POLL_S = 15.0


def _rpc(method, body=None, timeout_ms=90000):
    return INV.rpc(INV._session_id(), method, [body] if body is not None else [], timeout_ms)


def _upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _seed_rng(dump):
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"])
    rng.mti = dump["mti"]
    return rng


def ensure_seed_bc() -> Path:
    """Seed BC augmentee de `votanChampion` (hors pool du seed partage).

    `write_augmented_seed_bc` pose `BC.Units` **ET** `BC.Abilities` : un clone a la main de
    `BC.Units` produirait un porteur qui se deploie puis faute au premier cast
    (`AbilityConfiguration$$GetVariableForLevel` leve sur une config d'ability vide) -- cf.
    `docs/rl/case-92-catalog-injection.md`."""
    if not SEED_BC.exists():
        LOGS.mkdir(parents=True, exist_ok=True)
        import catalog_inject
        catalog_inject.write_augmented_seed_bc(str(SEED_BC), [CASTER_VID])
    return SEED_BC


class TilesMovedHarness:
    """Une bataille isolee ou l'on impose la LONGUEUR du pas de Kimm avant son attaque."""

    def __init__(self, rid: int, board: Board):
        self.rid, self.board = rid, board
        self.my_player = None
        self.endturns = 0

    # ------------------------------------------------------------------ lecture d'etat live
    def dview(self):
        return _rpc("decisionView", {"runnerId": self.rid, "maxRank": 1, "allAbilities": True})

    def alive(self, dv=None):
        dv = dv if dv is not None else self.dview()
        return [u for u in (dv.get("units") or []) if u.get("alive")]

    def by_visual(self, vid, dv=None):
        return next((u for u in self.alive(dv) if u.get("visualId") == vid), None)

    def enemies_of(self, player, dv=None):
        return [u for u in self.alive(dv) if u.get("owner") != player]

    def normal_attack_type(self, unit_id, dv=None):
        """L'attaque normale est un `ActiveAbilityType` PAR UNITE (`kind == 'normal'`), jamais
        l'id generique 17 (cf. `NormalAttackType@0x28`)."""
        dv = dv if dv is not None else self.dview()
        for u in (dv.get("units") or []):
            if u.get("id") == unit_id:
                for a in (u.get("abilities") or []):
                    if a.get("kind") == "normal":
                        return a.get("id")
        return None

    # ------------------------------------------------------------------ pilotage
    def reach_my_turn(self, max_end_turns=12, force_cycle=False):
        """Enchaine des `endturn` jusqu'a mon tour.

        `force_cycle=True` : passer par UN CYCLE COMPLET meme si c'est DEJA mon tour. C'est ce
        `endturn`-la qui execute `EndTurnOperation$$Execute` -> `ActorStatisticsComponent$$
        ResetThisTurn` -> `+0xf0 = 0`, donc qui EFFACE les tuiles enregistrees par les `place()` du
        montage. Sans lui, le compteur du montage entre dans le snapshot LIVE et reste invisible
        offline (aucun capteur ne publie `+0xf0`)."""
        dv = self.dview()
        if self.my_player is None:
            mine = self.alive(dv)
            self.my_player = mine[0].get("owner") if mine else None
        if force_cycle and dv.get("currentPlayer") == self.my_player:
            _rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 40000)
            self.endturns += 1
            dv = self.dview()
        for _ in range(max_end_turns):
            if dv.get("currentPlayer") == self.my_player:
                return dv
            _rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 40000)
            self.endturns += 1
            dv = self.dview()
        return dv if dv.get("currentPlayer") == self.my_player else None

    def place(self, unit_id, coord) -> bool:
        """Pose `unit_id` sur `coord` et RELIT la position -> True SSI le pas a eu lieu.
        (`applyAction {kind:'move'}` rend `ok=True` MEME quand le pas est refuse.)"""
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

    def snapshot(self):
        return {"dv": self.dview(),
                "ob": _rpc("observeBattle", {"runnerId": self.rid}, 40000),
                "snap": _rpc("combatSnapshot", {"runnerId": self.rid}, 60000),
                "rng": _rpc("dumpRng", {"runnerId": self.rid}, 30000)}

    # ------------------------------------------------------------------ montage du regime
    def arrange(self, steps: int):
        """Impose la geometrie : cible ancree, Kimm a distance hex `steps` d'une tuile ADJACENTE a
        la cible. Rend `{caster, target, start, step_to, anchor, steps}` ou None.

        ORDRE DES POSES : (1) garer la cible LOIN, (2) ecarter les autres ennemis, (3) poser Kimm,
        (4) AMENER la cible sur l'ancre. Le meme ordre que `_charge_regime.arrange`, pour la meme
        raison : un `place()` est un `MoveUnitOperation` complet."""
        dv = self.dview()
        me = self.by_visual(CASTER_VID, dv)
        if me is None:
            return None
        self.my_player = me.get("owner")
        ens = self.enemies_of(self.my_player, dv)
        if not ens:
            return None
        tgt = ens[0]
        anchors = [self.board.coord(t) for t in sorted(self.board.by_id)
                   if self.board.walkable(t)
                   and len(self.free_tiles(self.board.coord(t), 1,
                                           exclude=(tgt["id"], me["id"]))) >= 3]
        for anchor in anchors:
            park = self.free_tiles(anchor, 4 + steps, exclude=(tgt["id"],))
            if not park or not self.place(tgt["id"], park[0]):
                continue
            for other in ens[1:]:
                far = self.free_tiles(anchor, 4 + steps, exclude=(other["id"],))
                if far:
                    self.place(other["id"], far[0])
            ring1 = self.free_tiles(anchor, 1, exclude=(me["id"], tgt["id"]))
            for step_to in ring1:
                for start in self.free_tiles(step_to, steps, exclude=(me["id"], tgt["id"])):
                    if hexgeo.distance(start, anchor) <= 1:
                        continue          # depart DEJA au contact -> le pas ne serait pas une charge
                    if not self.place(me["id"], start):
                        continue
                    if not self.place(tgt["id"], anchor):
                        continue
                    return {"caster": me["id"], "target": tgt["id"], "start": start,
                            "step_to": step_to, "anchor": anchor, "steps": int(steps)}
        return None

    def run(self, steps: int):
        """Monte le regime, atteint mon tour, SNAPSHOTe, joue le pas puis l'ATTAQUE NORMALE en LIVE.
        Rend le dict de mesure, ou None si la geometrie/le tour n'ont pas pu etre obtenus."""
        self.endturns = 0
        plan = self.arrange(steps)
        if plan is None:
            return None
        if self.reach_my_turn(force_cycle=True) is None:
            return None
        dv = self.dview()
        pos = {u["id"]: _upos(u) for u in self.alive(dv)}
        if pos.get(plan["caster"]) != plan["start"] or pos.get(plan["target"]) != plan["anchor"]:
            return None
        # GARDE DE REGIME : depart NON adjacent, arrivee adjacente, pas de longueur hex `steps`.
        if hexgeo.distance(plan["start"], plan["anchor"]) <= 1:
            return None
        if hexgeo.distance(plan["step_to"], plan["anchor"]) != 1:
            return None
        if hexgeo.distance(plan["start"], plan["step_to"]) != steps:
            return None
        plan["ability_type"] = self.normal_attack_type(plan["caster"], dv)
        if plan["ability_type"] is None:
            return None
        plan["snapshot"] = self.snapshot()
        if not self.place(plan["caster"], plan["step_to"]):
            return None
        plan["rng_after_step"] = _rpc("dumpRng", {"runnerId": self.rid}, 30000)
        res = _rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "ability", "casterId": plan["caster"], "targetId": plan["target"],
            "abilityType": int(plan["ability_type"])}}, 60000)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        hits = []
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if ("Amount" in td and td.get("Attacker_Id") == plan["caster"]
                    and td.get("Target_Id") == plan["target"]):
                hits.append(int(td["Amount"]))
        plan["live_ok"] = bool(isinstance(res, dict) and res.get("ok") and a0.get("ok"))
        plan["live_per_hit"] = hits
        plan["live_raw"] = res
        plan["endturns"] = self.endturns
        return plan

    def run_second_attack(self, rec):
        """SECONDE attaque, un TOUR PLUS TARD et SANS BOUGER -- confronte le RESET de fin de tour.

        `IdunBattle.Operations.EndTurnOperation$$Execute` appelle
        `ActorStatisticsComponent$$ResetThisTurn` sur `GetAllUnits`, qui fait `+0xf0 = 0`
        INCONDITIONNELLEMENT. Le compteur de Kimm doit donc etre RETOMBE a zero : la meme attaque,
        depuis la MEME tuile, ne doit plus porter aucun `V x n`.

        C'est la seule facon d'OBSERVER ce reset sans capteur sur `+0xf0` : on ne le lit pas, on
        lit sa CONSEQUENCE sur le degat. Rend `{snapshot, live_per_hit, live_ok}` ou None."""
        if self.reach_my_turn(force_cycle=True) is None:
            return None
        dv = self.dview()
        pos = {u["id"]: _upos(u) for u in self.alive(dv)}
        if pos.get(rec["caster"]) != tuple(rec["step_to"]) or pos.get(rec["target"]) != tuple(rec["anchor"]):
            return None                    # la geometrie a bouge -> on ne mesure pas autre chose
        snap = self.snapshot()
        res = _rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "ability", "casterId": rec["caster"], "targetId": rec["target"],
            "abilityType": int(rec["ability_type"])}}, 60000)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        hits = []
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if ("Amount" in td and td.get("Attacker_Id") == rec["caster"]
                    and td.get("Target_Id") == rec["target"]):
                hits.append(int(td["Amount"]))
        return {"snapshot": snap, "live_per_hit": hits,
                "live_ok": bool(isinstance(res, dict) and res.get("ok") and a0.get("ok"))}

    def replay_static(self, rec, snap, force_tiles=None):
        """Rejeu d'une attaque SANS pas prealable, depuis la capture `snap`. `force_tiles` ecrase
        `tiles_moved_this_turn` du caster juste avant l'attaque."""
        st = load_state(snap["dv"], snap["ob"], snap["snap"], board=self.board)
        if force_tiles is not None:
            e = st.get_entity(rec["caster"])
            uc = e.get_component(UnitComponent) if e is not None else None
            if uc is not None:
                uc.tiles_moved_this_turn = int(force_tiles)
        dump = snap.get("rng")
        if isinstance(dump, dict) and dump.get("mt"):
            st.rng = _seed_rng(dump)
        runner = Runner(st).install_default_handlers(20)
        runner.apply(AttackUnitMessage(attacker_id=rec["caster"], target_id=rec["target"]))
        return {"per_hit": list((runner.damage_handler.last or {}).get("per_hit") or []),
                "state": st, "n": unit_tiles_moved_this_turn(st, rec["caster"])}

    # ------------------------------------------------------------------ rejeu offline
    def offline_state(self, rec, force_tiles=None):
        """`State` OFFLINE depuis le snapshot PRE-pas, pas REJOUE (`MoveUnitMessage`) -> le compteur
        de tuiles est pose PAR LE MOTEUR, jamais declare. MT cale sur le dump pris APRES le pas live.

        `force_tiles` (contrefactuel) : ecrase `tiles_moved_this_turn` du caster APRES le rejeu du
        pas. `0` = « le port n'a pas compte » (l'etat d'AVANT #322-r1) ; `1` = « le port compte une
        constante » -- c'est ce bras qui separe threade de constante heureuse."""
        s = rec["snapshot"]
        st = load_state(s["dv"], s["ob"], s["snap"], board=self.board)
        Runner(st).install_default_handlers().apply(
            MoveUnitMessage(rec["caster"], tuple(rec["step_to"])))
        if force_tiles is not None:
            e = st.get_entity(rec["caster"])
            uc = e.get_component(UnitComponent) if e is not None else None
            if uc is not None:
                uc.tiles_moved_this_turn = int(force_tiles)
        dump = rec.get("rng_after_step") or s["rng"]
        if isinstance(dump, dict) and dump.get("mt"):
            st.rng = _seed_rng(dump)
        return st

    def replay_offline(self, rec, force_tiles=None):
        st = self.offline_state(rec, force_tiles=force_tiles)
        n = unit_tiles_moved_this_turn(st, rec["caster"])
        runner = Runner(st).install_default_handlers(20)
        runner.apply(AttackUnitMessage(attacker_id=rec["caster"], target_id=rec["target"]))
        per_hit = list((runner.damage_handler.last or {}).get("per_hit") or [])
        return {"per_hit": per_hit, "state": st, "n": n}

    def dispose(self):
        _rpc("disposeRunner", {"runnerId": self.rid}, 20000)


def build(board: str = BOARD, seed: int = SEED, extra=None) -> TilesMovedHarness:
    """Monte le runner isole. EXIGE un runner NEUF : `rl_duel build` peut REFUSER sans lever, et
    `_runner_id()` relirait paisiblement l'ANCIEN runner du meme `--state-file` -- le probe
    mesurerait alors un bras qu'il croit neuf (piege documente par #322 SS5)."""
    before = None
    if STATE.exists():
        try:
            before = int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])
        except Exception:                                 # noqa: BLE001
            before = None
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--seed-bc", str(ensure_seed_bc()), "--board", board,
            "--state-file", str(STATE),
            "--p-units", CASTER_VID, "--a-units", ENEMY_VIDS,
            "--hp-target", "300000", "--hp-player", "300000", "--no-ai", *(extra or [])]

    def _attempt() -> str:
        STATE.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(HERE), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return (p.stderr or p.stdout or "")

    # Indisponibilite TEMPORAIRE du harnais (cap de runners sature, ou host en mode DRAIN) : on
    # ATTEND puis on reessaie. Memes marqueurs que `tests/conftest.py` -- un refus temporaire n'est
    # ni une panne ni un verdict, et surtout pas une mesure.
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
        raise RuntimeError("build REFUSE (runner inchange : %d) -- le bras mesurerait le runner "
                           "PRECEDENT. Sortie: %s" % (rid, (p.stderr or p.stdout or "")[-400:]))
    bg = _rpc("boardGraph", {"runnerId": rid}, 60000)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible pour le runner %d" % rid)
    return TilesMovedHarness(rid, Board(bg["tiles"], adjacency="native_sym"))


def scenario(steps=(1, 2), board: str = BOARD, seed: int = SEED, verbose: bool = False,
             second_attack_on=None) -> dict:
    """Monte UN runner et y joue un bras par valeur de `steps`. Rend
    `{board, seed, rid, arms: {n_demande: {...}}}`. Leve si un bras ne s'installe pas -- un montage
    non installe n'est pas une mesure.

    `second_attack_on` = la valeur de `steps` sur laquelle on joue AUSSI la seconde attaque (un tour
    plus tard, sans bouger) qui confronte le RESET de fin de tour. Defaut : le dernier bras."""
    h = build(board=board, seed=seed)
    out = {"board": board, "seed": seed, "rid": h.rid, "arms": {}, "harness": h}
    last = list(steps)[-1] if steps else None
    want_second = last if second_attack_on is None else second_attack_on
    for s in steps:
        rec = h.run(int(s))
        if rec is None:
            raise RuntimeError("montage NON INSTALLE pour un pas de %d tuile(s) sur %s/%d"
                               % (s, board, seed))
        if not rec["live_ok"] or not rec["live_per_hit"]:
            raise RuntimeError("attaque normale live refusee/vide pour un pas de %d tuile(s) "
                               "(live_ok=%s hits=%s)" % (s, rec["live_ok"], rec["live_per_hit"]))
        off = h.replay_offline(rec)
        arm = {"rec": rec, "steps": int(s), "n": off["n"],
               "live_per_hit": rec["live_per_hit"], "off_per_hit": off["per_hit"],
               "off_per_hit_zero": h.replay_offline(rec, force_tiles=0)["per_hit"],
               "off_per_hit_n1": h.replay_offline(rec, force_tiles=1)["per_hit"],
               "state": off["state"]}
        if int(s) == want_second:
            sec = h.run_second_attack(rec)
            if sec is None or not sec["live_ok"] or not sec["live_per_hit"]:
                raise RuntimeError("seconde attaque (apres cycle de tour) NON INSTALLEE pour un pas "
                                   "de %d tuile(s) : %s" % (s, sec))
            st0 = h.replay_static(rec, sec["snapshot"])
            arm["second"] = {"live_per_hit": sec["live_per_hit"],
                             "off_per_hit": st0["per_hit"], "n": st0["n"],
                             "off_per_hit_kept": h.replay_static(
                                 rec, sec["snapshot"], force_tiles=off["n"])["per_hit"]}
        out["arms"][int(s)] = arm
        if verbose:
            print("[pas=%d] n=%s live=%s off=%s | n=0 -> %s | n=1 -> %s"
                  % (s, arm["n"], arm["live_per_hit"], arm["off_per_hit"],
                     arm["off_per_hit_zero"], arm["off_per_hit_n1"]))
            if "second" in arm:
                print("        2e attaque (tour suivant, sans bouger) : live=%s off=%s | "
                      "compteur CONSERVE -> %s" % (arm["second"]["live_per_hit"],
                                                   arm["second"]["off_per_hit"],
                                                   arm["second"]["off_per_hit_kept"]))
    return out


def dispose(res) -> None:
    h = (res or {}).get("harness")
    if h is not None:
        try:
            h.dispose()
        except Exception:                                 # noqa: BLE001
            pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--steps", default="1,2")
    a = ap.parse_args()
    steps = tuple(int(x) for x in a.steps.split(","))
    res = None
    try:
        res = scenario(steps=steps, board=a.board, seed=a.seed, verbose=True)
        print("\n== probe #335 -- face COMBAT de ModifiedExoarmour_ExtraDmg ==")
        print("board=%s seed=%d runner=%d" % (res["board"], res["seed"], res["rid"]))
        for s in sorted(res["arms"]):
            arm = res["arms"][s]
            ok = "OK " if arm["live_per_hit"] == arm["off_per_hit"] else "ECART"
            print("  pas=%d n=%s %s live=%s off=%s" % (s, arm["n"], ok, arm["live_per_hit"],
                                                       arm["off_per_hit"]))
            print("        contrefactuels : n=0 -> %s | n=1 -> %s"
                  % (arm["off_per_hit_zero"], arm["off_per_hit_n1"]))
    finally:
        dispose(res)


if __name__ == "__main__":
    main()
