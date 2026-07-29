"""PROBE O4a -- un gate `Maybe(chance)` consomme-t-il UN tirage, AU BON MOMENT, comme le natif ?

CRITERE (binaire) : « un trigger gate par `Maybe(chance)` consomme-t-il exactement UN tirage RNG,
au bon moment dans le flux, comme le natif ? ». La mesure est le COMPTE de `genrand_int32`, jamais
un scalaire ajuste.

VERITE NATIVE (decompile gqfc5mff6c) :

  `IdunBattle.Entities.Triggers.MaybeTrigger$$ShouldTrigger`
      chance = <formule V @+0x20>.Calculate(entities)
      if (!IdunBattle.DSL.ANonDeterministicAbilityTrigger$$CanUseRandom(this)) return 99 < chance;
      return IdunBattle.Utils.PRNG.DisallowablePseudoRNG$$NextBool(this@+0x18, chance);

  `IdunBattle.DSL.ANonDeterministicAbilityTrigger$$CanUseRandom`
      return state@+0x10.IsRandomAllowed && rng@+0x18.IsAllowed@+0x20;
  ou `IsAllowed@+0x20` vaut 1 des `IdunBattle.Utils.PRNG.DisallowablePseudoRNG$$.ctor` et n'est mis a
  0 que par `IdunBattleLogic.Entities.DSLFactory$$SetDisallowRandom`, dont l'UNIQUE call-site est
  `IdunBattle.AI.Playbook.BasePlaybook$$Evaluate` (l'IA qui EVALUE). Donc `!CanUseRandom` == cote
  DECISION/PREDICTION -> aucun tirage, verdict deterministe `99 < chance`.

Trois mesures :

 (U) NOEUD SEUL, in-vitro -- `MaybeTrigger` consomme-t-il 1 `genrand_int32` et rend-il le meme
     verdict que `NextBool` ? Et 0 tirage + `99 < chance` sur la branche `!CanUseRandom` ?

 (P) PILEIN, LIVE bit-exact -- `IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateBehaviour`
     se termine par `If( Maybe(Difference(Direct(chance), Multiply(Count(...), Direct(chance_2)))),
     Spawn(Self, First(SortByFormula(Randomize(CanAddUnit(AdjacentTiles(Self))), ...), 1), ...),
     Nothing() )`. Le selecteur de tuile est un ARGUMENT du `Spawn`, donc de la branche THEN :
     `IdunBattle.Entities.Behaviours.IfBehaviour$$Execute` ne l'evalue QUE si le `Maybe` a reussi.
     Compte natif par grot candidat = 1 `next_bool` PUIS `len(pool)` (Randomize) SI succes.
     On compte les `genrand_int32` LIVE d'un `endturn` (dumpRng avant/apres + re-simulation MT) et on
     les compare au port rejouant le MEME endturn sur le MEME etat MT, sous deux modeles :
        M0 = le port d'AVANT (gate `Maybe` NON modelise -> DETERMINISTE : 0 tirage de gate, et le
             `Randomize` paye a TOUS les coups) ;
        M1 = le port d'APRES (mirror : 1 tirage de gate, `Randomize` seulement sur succes).
     Discriminants : le COMPTE de genrand ET le nombre de grots reellement dedoubles.

 (L) LETTHEGALAXYBURN (residu O6), in-vitro -- ORDRE de la conjonction native
     `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger` =
     `((On(5) & OwnerIsCaster) & Maybe(ConfigConst 0x2a)) & !HasTileStatusEffect(Targets@0x190)`.
     `IdunBattle.DSL.MultipleAbilityTrigger$$ShouldTrigger` evalue GAUCHE puis DROITE : le tirage est
     consomme MEME quand la cible est deja sur une tuile a status-effect. On mesure le nombre de
     `genrand_int32` du trigger sur les DEUX branches (tuile nue / tuile a effet).

Usage : python probe_o4a_maybe_trigger_rng.py [--case unit|pilein|ltgb|all] [--seed 777]
                                              [--board MC1_67] [--turns 14]
Depuis scripts/python. ASCII only. Dispose SES runners (jamais ceux des autres).
Pre-requis : session Frida vivante et WARMEE (ce probe ne (re)injecte JAMAIS).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

BOARD = "MC1_67"
CARRIER = "orksRuntherd"          # active GetEmRuntz (spawn de grots) + passif SquigHound
ESCORT = "orksNob"
ENEMY = "necroWarden"
GROT = "orksGrot"                 # le porteur du passif PileIn (kind = summons)
GROTS_WANTED = 1                  # 1 seul porteur : port et natif s'accordent alors sur la population
MIN_AGE = 1                       # tours (de MES tours) a laisser vieillir un porteur avant mesure.
                                  # 1 = le SEUIL NATIF (`GetTurnsFinished >= 2`, et le bump
                                  # d'EndTurn precede `On(0x17)` -> age 1 suffit). La marge de 3
                                  # d'avant compensait le gate per-JOUEUR du port ; elle rendait la
                                  # mesure rare (PileIn se dedouble, la population depasse 1 vite).
VERBOSE = False                   # --verbose : dump des unites/candidats a chaque tour


# ---------------------------------------------------------------- plomberie RPC / comptage

class Rpc:
    """Meme voie que la conftest : `rl_collect_batch._rpc(sid, method, [body], timeout_s)`."""

    def __init__(self):
        import rl_collect_batch as R
        self.R = R
        self.sid = R._resolve_session()

    def __call__(self, method, args=None, timeout=60):
        out = self.R._rpc(self.sid, method, [args] if args is not None else [], timeout=timeout)
        return out.get("result") if isinstance(out, dict) and "result" in out else out


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def count_genrand(before, after, cap=4000):
    """Nombre de `genrand_int32` entre deux etats (mt, mti) du MT natif -- par re-simulation.
    C'est une MESURE (le nombre de pas EST le nombre de tirages), pas une estimation."""
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt = list(before["mt"])
    r.mti = int(before["mti"])
    tgt_mt, tgt_mti = list(after["mt"]), int(after["mti"])
    for n in range(cap + 1):
        if r.mti == tgt_mti and r.mt == tgt_mt:
            return n
        r.genrand_int32()
    return None


class CountingRng:
    """Compteur de `genrand_int32` cote PORT (meme helper que `probe_130_placement_sort_rng.py`)."""

    def __init__(self, mt, mti):
        from engine.runner.prng import IntBasedMersenneTwister
        self.r = IntBasedMersenneTwister()
        self.r.mt = list(mt)
        self.r.mti = int(mti)
        self.n = 0

    def genrand_int32(self):
        self.n += 1
        return self.r.genrand_int32()

    def genrand_real2(self):
        self.n += 1
        return self.r.genrand_real2()

    def __getattr__(self, k):
        return getattr(self.r, k)

    def next_internal(self, lo, hi):
        from engine.runner.prng import _i32
        rng = hi - lo
        if (-rng & rng) == rng:
            return ((rng * (self.genrand_int32() >> 1)) >> 31) + lo
        while True:
            v0 = self.genrand_int32() >> 1
            v = v0 % rng
            if _i32((rng - 1) + (v0 - v)) >= 0:
                return v + lo

    def next(self, bound):
        return self.next_internal(0, bound)

    def next_bool(self, chance):
        return self.next_internal(1, 100) <= chance


# ---------------------------------------------------------------- (U) le noeud seul

def case_unit():
    """Le noeud `MaybeTrigger` : 1 tirage + meme verdict que `NextBool` ; 0 tirage et `99 < chance`
    sur la branche `!CanUseRandom` (rng absent = cote DECISION/PREDICTION)."""
    from engine.entities.triggers import MaybeTrigger
    from engine.dsl.base import Const

    print("=== (U) MaybeTrigger, in-vitro ===")
    ok = True
    for chance in (25, 33, 75, 100):
        rng = CountingRng([0] * 624, 625)          # non seede -> seed natif 5489 (mirror prng.py)
        rng.r.init_genrand(20260727)
        verdict = MaybeTrigger(rng, Const(chance)).should_trigger(None)
        ref = CountingRng([0] * 624, 625)
        ref.r.init_genrand(20260727)
        expect = ref.next_bool(chance)
        same = (verdict == expect) and (rng.n == ref.n) and rng.n >= 1
        ok = ok and same
        print("  chance=%-4d tirages=%d verdict=%-5s == NextBool ? %s"
              % (chance, rng.n, verdict, same))
    print("  -- branche !CanUseRandom (rng absent) : `return 99 < chance`, 0 tirage")
    for chance, expect in ((0, False), (33, False), (99, False), (100, True), (150, True)):
        got = MaybeTrigger(None, Const(chance)).should_trigger(None)
        ok = ok and (got == expect)
        print("     chance=%-4d -> %-5s (attendu %s)" % (chance, got, expect))
    print("  VERDICT (U) : %s" % ("OK" if ok else "KO"))
    return ok


# ---------------------------------------------------------------- (P) PileIn, live

def build(seed, state_file, p_units, a_units, extra=()):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(state_file),
           "--board", BOARD, "--roster", "1", "--p-units", p_units, "--a-units", a_units,
           "--hp-target", "90000", "--hp-player", "90000", "--no-ai"] + list(extra)
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-700:])
        return None
    return json.loads(state_file.read_text())["runnerId"]


class _DeterministicPileIn:
    """Restaure le gate d'AVANT (`Maybe(chance)` NON modelise -> DETERMINISTE : fire si chance > 0).
    Reproduit ICI par neutralisation du seul noeud `MaybeTrigger` vu par `dispatch`, jamais importe :
    le fichier de production n'en garde aucune trace."""

    def __init__(self):
        self.saved = None

    def __enter__(self):
        import engine.entities.triggers as T
        self.T = T
        self.saved = T.MaybeTrigger.should_trigger

        def _deterministic(node, ctx):
            ch = node.chance.evaluate(ctx) if hasattr(node.chance, "evaluate") else int(node.chance)
            return int(ch) > 0                      # 0 tirage : exactement le port d'AVANT

        T.MaybeTrigger.should_trigger = _deterministic
        return self

    def __exit__(self, *a):
        self.T.MaybeTrigger.should_trigger = self.saved
        return False


def _pilein_candidates(st, player):
    """Les grots que le gate DETERMINISTE de PileIn retiendrait (mirror des gates NON-Maybe :
    passif PileIn, vivant, meme joueur, PV pleins). DIAGNOSTIC : le gate d'AGE
    (`OwnerHasFinishedMinTurns(2)`) est volontairement EXCLU ici -- ce comptage sert de BORNE
    SUPERIEURE des candidats, et l'appelant pose lui-meme `turns_finished` depuis l'age observe
    (il ecrase alors celui que `load_state` seede depuis `combatSnapshot.turnsFinished`, #234)."""
    import gameconfig as GC
    from engine.runner.components import UnitComponent, OwnerComponent, HealthComponent
    out = []
    for eid, e in st.entities.items():
        uc, oc, hc = (e.get_component(UnitComponent), e.get_component(OwnerComponent),
                      e.get_component(HealthComponent))
        if uc is None or oc is None or hc is None or not uc.alive or oc.player != int(player):
            continue
        if "PileIn" not in ((GC.unit(uc.visual_id) or {}).get("passiveAbilities") or []):
            continue
        if hc.hp < hc.hp_max:
            continue
        out.append(eid)
    return out


def _pilein_units_live(dv, player):
    """{unitId} des unites VIVANTES de `player` portant le passif `PileIn` -- le summon de
    `SquigHound` est `orksNpc1Grot` (et non `orksGrot`, le `summonId` de PileIn lui-meme) : on
    filtre donc sur le PASSIF, jamais sur un visualId en dur."""
    import gameconfig as GC
    out = set()
    for u in (dv.get("units") or []):
        if u.get("owner") != player or not u.get("alive"):
            continue
        if "PileIn" in ((GC.unit(u.get("visualId")) or {}).get("passiveAbilities") or []):
            out.add(u["id"])
    return out


def _port_replay_endturn(dv, ob, snap, board, player, rng_before, ages, deterministic: bool):
    """Rejoue le VOLET PileIn du `endturn` par le port reel, sur le MEME etat MT que le live.
    Rend (nb genrand, nb grots dedoubles).

    `ages` = {unitId du porteur -> nb de MES fins de tour deja traversees} = son `turnsFinished`
    AVANT le bump du tour mesure. On pose `turnsFinished = age + 1` parce que le natif bumpe
    `BaseUnitComponent + 0x5c` (boucle d'`IdunBattle.Operations.EndTurnOperation$$Execute` sur
    `PlayerComponent.CurrentlyOwnedUnitIds`) AVANT d'executer les trigger-abilities `On(0x17)`,
    alors que ce replay appelle le VECTEUR seul.

    GAP MESURE ici -- `load_state` (`engine/runner/snapshot.py`) ne seede PAS `turnsFinished`, et
    AUCUN RPC ne l'expose : ce n'est pas un `StatType` (l'enum s'arrete a 26 sans lui), donc
    `combatSnapshot` ne peut pas l'atteindre via `GetStat`. Tout etat charge depuis un snapshot part
    donc a 0 pour toutes les unites -> sans ce seeding, le volet PileIn du port est un NO-OP
    silencieux et il n'y a rien a confronter. Le compteur JOUEUR `state.turn_counts`
    (`TurnComponent + 0x38`) n'est PAS non plus seede, mais il n'entre plus dans ce gate."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import UnitComponent
    from engine.runner.operations.triggers.dispatch import end_turn_summon_triggers

    st = load_state(dv, ob, snap, board=board)
    for uid, age in (ages or {}).items():                  # cf. docstring : gap de `load_state`
        e = st.get_entity(uid)
        uc = e.get_component(UnitComponent) if e is not None else None
        if uc is not None:
            uc.turns_finished = int(age) + 1
    st.rng = CountingRng(rng_before["mt"], rng_before["mti"])
    if deterministic:
        with _DeterministicPileIn():
            out = end_turn_summon_triggers(st, int(player))
    else:
        out = end_turn_summon_triggers(st, int(player))
    spawned = sum(len(r.get("spawned") or ()) for r in out if isinstance(r, dict) and "grot" in r)
    return st.rng.n, spawned


def _drive_and_attack(rpc, rid, board, carrier_vis, mine):
    """Amene le porteur au contact d'un ennemi et attaque (le passif `SquigHound` spawne alors 1
    grot). Rend True si l'attaque a eu lieu. Meme patron que `probe_1203_toxic_contamination`."""
    from collections import deque

    def bfs(src):
        dist, q = {src: 0}, deque([src])
        while q:
            x = q.popleft()
            for n in board.neighbours(x):
                if n not in dist and (n == src or board.walkable(n)):
                    dist[n] = dist[x] + 1
                    q.append(n)
        return dist

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    units = dv.get("units") or []
    me = next((u for u in units if u.get("visualId") == carrier_vis and u.get("alive")), None)
    if me is None or dv.get("currentPlayer") != mine:
        return False
    norm = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
    if norm is None:
        return False
    plan = next((ap for ap in (dv.get("attackPlans") or []) if ap.get("unitId") == me["id"]), None)
    ev = next((e for e in ((plan or {}).get("evals") or [])
               if e.get("targetId") is not None and (e.get("ranked") or [])), None)
    if ev is not None:
        rk = ev["ranked"][0]
        if rk.get("col") is not None:
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": rk["col"], "row": rk["row"]}}}, 60)
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": me["id"], "targetId": ev["targetId"],
            "abilityType": norm.get("id")}}, 90)
        return _ok(r)
    # pas encore a portee : on se rapproche de l'ennemi le plus proche
    pos = me.get("pos") or {}
    enemies = [u for u in units if u.get("owner") != mine and u.get("alive") and (u.get("pos") or {})]
    if pos.get("col") is None or not enemies:
        return False
    tgt_pos = min(((u["pos"]["col"], u["pos"]["row"]) for u in enemies),
                  key=lambda p: abs(p[0] - pos["col"]) + abs(p[1] - pos["row"]))
    dist = bfs(board.id_at(*tgt_pos))
    mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60) or {}
    cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == me["id"]), None)
    reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
             for t in ((cmt or {}).get("tiles") or [])}
    pool = [t for t in reach if t in dist]
    if pool:
        col, row = reach[min(pool, key=lambda t: dist[t])]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": me["id"], "to": {"col": col, "row": row}}}, 60)
    return False


def case_pilein(rpc, seed, max_turns):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state

    print("=== (P) PileIn -- comptage RNG LIVE vs PORT ===")
    sf = ROOT / "logs" / "runners" / ("o4a-pilein-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    rid = build(seed, sf, "%s,%s" % (CARRIER, ESCORT), "%s,%s" % (ENEMY, ENEMY))
    if rid is None:
        return None
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print("  boardGraph indispo")
            return None
        board = Board(bg["tiles"], adjacency="native_sym")

        def dview():
            return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)

        dv = dview()
        me = next((u for u in (dv.get("units") or []) if u.get("visualId") == CARRIER), None)
        if me is None:
            print("  porteur absent")
            return None
        mine = me.get("owner")
        rows = []
        my_turns = 0          # nb de MES fins de tour (horloge du probe)
        birth = {}            # unitId (porteur PileIn) -> `my_turns` a son apparition
        for turn in range(max_turns):
            dv = dview()
            if dv.get("currentPlayer") != mine:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            live_grots = _pilein_units_live(dv, mine)
            for uid in live_grots:
                birth.setdefault(uid, my_turns)
            # 1) peupler l'equipe : le passif `SquigHound` du runtherd spawne 1 grot par attaque
            #    (`orksNpc1Grot`, porteur de `PileIn` -- kind=summons, hors `--list-pool` : c'est le
            #    gate SUMMON du CLAUDE.md, on l'amene par son summoner).
            if len(live_grots) < GROTS_WANTED:
                if _drive_and_attack(rpc, rid, board, CARRIER, mine):
                    dv = dview()
                    live_grots = _pilein_units_live(dv, mine)
                    for uid in live_grots:
                        birth.setdefault(uid, my_turns)

            ob = rpc("observeBattle", {"runnerId": rid}, 60)
            snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
            st = load_state(dv, ob, snap, board=board)
            cands = _pilein_candidates(st, mine)
            # `OwnerHasFinishedMinTurns(2)` est PER-UNITE cote natif (RE :
            # `IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger` ->
            # `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(unit)`) -- et le port le lit
            # desormais pareil (`UnitComponent.turns_finished`, `BaseUnitComponent + 0x5c`).
            # L'AGE de chaque porteur (nb de MES fins de tour deja traversees) est l'observable qui
            # seede ce compteur cote port (cf. `_port_replay_endturn`) : `load_state` ne peut pas.
            ages = {uid: my_turns - birth.get(uid, my_turns) for uid in live_grots}
            # UN SEUL porteur, assez vieux : garde la mesure LISIBLE (le natif dedouble tout seul
            # des le tour suivant, et un nouveau-ne ferait varier le nombre de candidats en cours
            # de mesure). MIN_AGE >= 1 suffirait maintenant que le gate est per-unite des deux
            # cotes ; on garde la marge.
            ready = len(live_grots) == 1 and all(a >= MIN_AGE for a in ages.values())
            if VERBOSE:
                mineu = [(u.get("id"), u.get("visualId")) for u in (dv.get("units") or [])
                         if u.get("owner") == mine and u.get("alive")]
                print("     [dbg] mes unites: %s | ages=%s | cands_port=%s"
                      % (mineu, ages, cands))
            if not cands or not ready:
                print("  tour %-2d : porteurs=%d ages=%s cands_port=%d -> endturn (pas de mesure)"
                      % (turn, len(live_grots), sorted(ages.values()), len(cands)))
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                my_turns += 1
                continue

            rng_before = rpc("dumpRng", {"runnerId": rid}, 30)
            if not _ok(rng_before):
                print("  dumpRng KO")
                return None
            act = rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            if not _ok(act):
                print("  endturn KO", str(act)[:200])
                return None
            my_turns += 1
            rng_after = rpc("dumpRng", {"runnerId": rid}, 30)
            dv2 = dview()
            after_grots = _pilein_units_live(dv2, mine)
            live_n = count_genrand(rng_before, rng_after)
            n1, sp1 = _port_replay_endturn(dv, ob, snap, board, mine, rng_before, ages,
                                           deterministic=False)
            n0, sp0 = _port_replay_endturn(dv, ob, snap, board, mine, rng_before, ages,
                                           deterministic=True)
            live_spawn = len(after_grots - live_grots)
            row = {"turn": turn, "cands": len(cands), "grots_before": len(live_grots),
                   "live_n": live_n, "live_spawn": live_spawn,
                   "m1_n": n1, "m1_spawn": sp1, "m0_n": n0, "m0_spawn": sp0}
            rows.append(row)
            print("  tour %-2d : porteurs=%-2d | LIVE genrand=%-4s spawn=%-2d "
                  "| M1 genrand=%-4s spawn=%-2d | M0 genrand=%-4s spawn=%-2d"
                  % (turn, len(live_grots), live_n, live_spawn, n1, sp1, n0, sp0))
            break                       # 1 mesure PROPRE par runner (apres, les ages divergent)
        return rows
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        try:
            sf.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------- (L) LetTheGalaxyBurn (O6)

def case_ltgb():
    """ORDRE de la conjonction native : `Maybe` AVANT `!HasTileStatusEffect`. On mesure le nombre de
    `genrand_int32` consommes par le trigger sur les DEUX branches, sur un `State` synthetique dont
    la seule variable est la presence d'un status-effect sur la tuile de la cible."""
    from engine.runner.operations.triggers.loki.let_the_galaxy_burn import LetTheGalaxyBurnArmAbility
    import engine.runner.operations.triggers.loki.let_the_galaxy_burn as LTGB
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.dsl.event_trigger_type import EventTriggerType

    from engine.runner.state import State
    from engine.runner.components import UnitComponent, OwnerComponent, HealthComponent

    print("=== (L) LetTheGalaxyBurn (O6) -- ordre du roll dans la conjonction ===")

    def _state(rng):
        st = State()
        st.rng = rng
        st.current_player_id = 0
        for eid, (team, player) in ((1, (0, 0)), (2, (1, 1))):
            e = st.add_entity(eid)
            e.add_component(UnitComponent(visual_id="blackTerminator" if eid == 1 else "necroWarden",
                                          alive=True))
            e.add_component(OwnerComponent(team=team, player=player))
            e.add_component(HealthComponent(hp=1000, hp_max=1000))
        return st

    def _legacy_matches(ab, state, ev):
        """Le `matches` d'AVANT (ordre INVERSE + primitive `next_internal(0,100) <`), recopie ICI
        pour que la garde soit vue ROUGE. Le fichier de production n'en garde aucune trace."""
        from engine.entities.effects.magnitude import trait_var
        if ev.actor_id != ab.owner_id:
            return False
        if ev.target_id is None or state.get_entity(ev.target_id) is None:
            return False
        if LTGB._target_tile_effects(state, ev.target_id):        # gate DETERMINISTE d'abord
            return False
        pct = trait_var("LetTheGalaxyBurn", "LetTheGalaxyBurnChancePct")
        if not pct or state.rng is None:
            return False
        return state.rng.next_internal(0, 100) < int(pct)

    saved = LTGB._target_tile_effects
    rows = []
    try:
        for model, fn in (("M0 (port d'AVANT)", _legacy_matches),
                          ("M1 (mirror natif)", LetTheGalaxyBurnArmAbility.matches)):
            for label, tile_fx in (("tuile NUE (pose possible)      ", []),
                                   ("tuile a STATUS-EFFECT (bloquee)", ["Fire"])):
                LTGB._target_tile_effects = lambda st, tid, _fx=tile_fx: list(_fx)
                rng = CountingRng([0] * 624, 625)
                rng.r.init_genrand(20260727)
                st = _state(rng)
                ab = LetTheGalaxyBurnArmAbility.__new__(LetTheGalaxyBurnArmAbility)
                ab.owner_id = 1
                ev = TriggerEvent(EventTriggerType.PreAttack, 1, 2, ranged=False, profile=None)
                got = fn(ab, st, ev)
                rows.append((model, label, rng.n, got))
                print("  %-18s %-32s tirages=%d matches=%s" % (model, label, rng.n, got))
    finally:
        LTGB._target_tile_effects = saved
    ok = all(n == 1 for m, _l, n, _g in rows if m.startswith("M1"))
    red = any(n == 0 for m, _l, n, _g in rows if m.startswith("M0"))
    print("  attendu NATIF : 1 tirage sur LES DEUX branches (le `Maybe` precede le gate de tuile)")
    print("  garde vue ROUGE sur M0 (0 tirage sur la branche bloquee) : %s" % red)
    print("  VERDICT (L) : %s" % ("OK" if (ok and red) else "KO"))
    return ok and red


# ---------------------------------------------------------------- main

def main():
    global BOARD, VERBOSE
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="all", choices=["unit", "pilein", "ltgb", "all"])
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--turns", type=int, default=14)
    ap.add_argument("--min-age", type=int, default=MIN_AGE,
                    help="tours a laisser vieillir le porteur avant de mesurer (gate natif "
                         "`OwnerHasFinishedMinTurns(2)`, PER-UNITE)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    BOARD = args.board
    VERBOSE = args.verbose
    globals()["MIN_AGE"] = args.min_age

    if args.case in ("unit", "all"):
        case_unit()
        print()
    if args.case in ("ltgb", "all"):
        case_ltgb()
        print()
    if args.case in ("pilein", "all"):
        rpc = Rpc()
        seeds = [s.strip() for s in str(args.seed).split(",") if s.strip()]
        print("session=%s seeds=%s board=%s" % (rpc.sid, seeds, BOARD))
        allrows = []
        for sd in seeds:
            rows = case_pilein(rpc, sd, args.turns) or []
            for r in rows:
                r["seed"] = sd
            allrows += rows
        print("\n=== VERDICT (P) ===")
        if not allrows:
            print("  aucune mesure (pas de porteur PileIn eligible rencontre)")
        m1_ok = m0_ok = 0
        for r in allrows:
            d1 = None if r["live_n"] is None else r["m1_n"] - r["live_n"]
            d0 = None if r["live_n"] is None else r["m0_n"] - r["live_n"]
            m1_ok += int(d1 == 0)
            m0_ok += int(d0 == 0)
            print("  seed %-6s tour %-2d porteurs=%-2d | live genrand=%-4s spawn=%-2d "
                  "| M1 delta=%-5s spawn=%-2d | M0 delta=%-5s spawn=%-2d"
                  % (r["seed"], r["turn"], r["grots_before"], r["live_n"], r["live_spawn"],
                     d1, r["m1_spawn"], d0, r["m0_spawn"]))
        if allrows:
            print("  accord du COMPTE de tirages : M1 %d/%d | M0 %d/%d"
                  % (m1_ok, len(allrows), m0_ok, len(allrows)))
        print("  attendu : M1 reproduit le compte LIVE (1 `next_bool` + `Randomize` seulement sur")
        print("            succes) ; M0 diverge (aucun tirage de gate, `Randomize` paye toujours).")


if __name__ == "__main__":
    main()
