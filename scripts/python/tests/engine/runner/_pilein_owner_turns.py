"""Montage NOMME et REUTILISABLE du scenario `OwnerHasFinishedMinTurns(2)` de PileIn.

Le gate natif se lit dans
`IdunBattleLogic.Entities.DSLTriggers$$OwnerHasFinishedMinTurns` ->
`IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger` :

    amount = <int @+0x18>                                   # 2 pour PileIn
    unit   = <selecteur @+0x10>.Select(entities)            # factory+0x148 = Self/Owner
    return IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(unit) >= amount

`GetTurnsFinished` rend `BaseUnitComponent + 0x5c` -- un compteur PER-UNITE, incremente par
`IdunBattle.Operations.EndTurnOperation$$Execute` sur les ids de
`PlayerComponent.CurrentlyOwnedUnitIds` du joueur qui finit son tour, AVANT que les
trigger-abilities `On(0x17 = TurnEnd)` ne soient executees. Ni `turnsStarted` (`+0x58`, stat 12),
ni le dict PAR JOUEUR `TurnComponent + 0x38` (`State.turn_counts`).

CE QUE LE MONTAGE PRODUIT -- une mesure indexee par l'AGE du grot, ou `age` = nombre de fins de
tour de son proprietaire qu'il a deja traversees (= son `turnsFinished` AVANT le bump du tour
mesure). Le gate natif demande `age + 1 >= 2`, donc :

    age 0 (le tour de sa naissance)  -> gate FERME  -> 0 tirage PRNG impute a PileIn
    age 1 (le tour suivant)          -> gate OUVERT -> >= 1 tirage (`Maybe`, puis `Randomize`
                                                       du placement si le `Maybe` reussit)

C'est le seul couple de points ou les deux hypotheses (per-UNITE vs per-JOUEUR) donnent des
resultats DIFFERENTS : a ce moment-la le JOUEUR a deja fini plusieurs tours, donc un gate lu sur
`turn_counts` serait OUVERT des l'age 0.

SEUL PORTEUR ATTEIGNABLE : `orksNpc1Grot` est `kind=summons`, donc hors `--list-pool`. On l'amene
en bataille par son summoner `orksRuntherd` (hero, passif `SquigHound` : 1 grot par attaque).

DEUX PIEGES QUE CE MONTAGE ENCAPSULE :

  1. **Le co-gate PV PLEINS** (`IsUnitWithStatAmount(Health Cur == Max)`) doit etre SATISFAIT aux
     deux points de mesure, sinon un « 0 tirage » a l'age 0 ne prouve rien (il pourrait venir du
     co-gate). Chaque enregistrement porte `full_hp` -- le test appelant DOIT le verifier.
  2. **Le seed de `turnsFinished`** : le montage le POSE depuis l'age qu'il a lui-meme observe
     (naissance tracee) pour pouvoir forcer un age ARBITRAIRE (le regime `m0_player` a 98 n'est
     atteignable par aucune capture), et pour que les trois regimes compares partent d'un etat
     identique a une seule variable pres. Ce n'est plus un contournement : depuis #234
     `load_state` seede le compteur lui-meme (cf. ci-dessous).

CANAL DU COMPTEUR (#234, resid N11 ferme) : `combatSnapshot.units[].turnsFinished` porte
`BaseUnitComponent + 0x5c`, obtenu en INVOQUANT `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished`
-- ce n'est PAS un `StatType` (l'enum va de 0 a 26 et n'en contient aucun), donc `GetStat` ne peut pas
l'atteindre, d'ou l'accesseur dedie. `snapshot._load_unit_turn_state` le pose sur
`UnitComponent.turns_finished` en tri-etat. Garde : `test_load_state_turns_finished_live.py`.

ASCII only.
"""
from __future__ import annotations

from collections import deque

import gameconfig as GC
from engine.entities.pathfinding.board import Board
from engine.runner.components import UnitComponent
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.snapshot import load_state

CARRIER = "orksRuntherd"        # hero, passif `SquigHound` : 1 grot (`orksNpc1Grot`) par attaque
ESCORT = "orksNob"
ENEMY = "necroWarden"
GROT_VISUAL = "orksNpc1Grot"
BOARD = "MC1_67"


class CountingRng(IntBasedMersenneTwister):
    """Compte les `genrand_int32` reellement consommes (l'oracle du flux natif)."""

    def __init__(self, seed=None):
        super().__init__(seed)
        self.rolls = 0

    def genrand_int32(self) -> int:
        self.rolls += 1
        return super().genrand_int32()


def count_genrand(before, after, cap=4000):
    """Nombre de `genrand_int32` entre deux etats (mt, mti) du MT natif, par re-simulation.
    None si l'etat d'arrivee n'est pas atteint en `cap` tirages (flux non attribuable)."""
    r = IntBasedMersenneTwister()
    r.mt = list(before["mt"])
    r.mti = int(before["mti"])
    tgt = (list(after["mt"]), int(after["mti"]))
    for n in range(cap + 1):
        if (r.mt, r.mti) == tgt:
            return n
        r.genrand_int32()
    return None


def minimal_pilein_state(n_grots=1, player=0, turn_counts=None, turns_finished=0, rng=None):
    """`State` minimal : `n_grots` porteurs de `PileIn` vivants a PV PLEINS + un non-grot du meme
    joueur + un ennemi. Pas de board -> `execute_pilein_replica` no-ope, ce qui ISOLE le cout PRNG
    du seul GATE (meme montage que `test_maybe_trigger_rng_live`).

    Partage entre `test_pilein_owner_turns_live` (le gate `OwnerHasFinishedMinTurns`) et
    `test_endturn_order_live` (l'ORDRE `On(0x17)` vs `RefreshEffects`) : les deux ont besoin du
    MEME plateau minimal, et le dupliquer ferait diverger deux montages qui doivent rester egaux."""
    from engine.runner.components import OwnerComponent, HealthComponent
    from engine.runner.state import State
    st = State()
    st.rng = rng
    st.current_player_id = player
    if turn_counts is not None:
        st.turn_counts.update(turn_counts)
    for i in range(n_grots):
        e = st.add_entity(100 + i)
        uc = UnitComponent(visual_id=GROT_VISUAL, alive=True)
        uc.turns_finished = int(turns_finished)
        e.add_component(uc)
        e.add_component(OwnerComponent(team=player, player=player))
        e.add_component(HealthComponent(hp=1000, hp_max=1000))
    ally = st.add_entity(200)
    ally.add_component(UnitComponent(visual_id=CARRIER, alive=True))
    ally.add_component(OwnerComponent(team=player, player=player))
    ally.add_component(HealthComponent(hp=1000, hp_max=1000))
    foe = st.add_entity(300)
    foe.add_component(UnitComponent(visual_id=ENEMY, alive=True))
    foe.add_component(OwnerComponent(team=player + 1, player=player + 1))
    foe.add_component(HealthComponent(hp=1000, hp_max=1000))
    return st


def pilein_units(dv, player):
    """Ids des unites VIVANTES de `player` portant le passif `PileIn` (les grots)."""
    return {u["id"] for u in (dv.get("units") or [])
            if u.get("owner") == player and u.get("alive")
            and "PileIn" in ((GC.unit(u.get("visualId")) or {}).get("passiveAbilities") or [])}


def _bfs(board, src):
    dist, q = {src: 0}, deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def drive_and_attack(rpc, rid, board, mine):
    """Amene le `orksRuntherd` au contact et le fait attaquer -> `SquigHound` spawne 1 grot
    (`orksNpc1Grot`), seule voie d'entree en bataille d'un porteur de `PileIn`. Rend True si
    l'attaque est PASSEE (donc si un grot a du naitre)."""
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    units = dv.get("units") or []
    me = next((u for u in units if u.get("visualId") == CARRIER and u.get("alive")), None)
    if me is None:
        return False
    norm = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
    plan = next((ap for ap in (dv.get("attackPlans") or []) if ap.get("unitId") == me["id"]), None)
    ev = next((e for e in ((plan or {}).get("evals") or [])
               if e.get("targetId") is not None and (e.get("ranked") or [])), None)
    if norm is not None and ev is not None:
        rk = ev["ranked"][0]
        if rk.get("col") is not None:
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": rk["col"], "row": rk["row"]}}}, 60)
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": me["id"], "targetId": ev["targetId"],
            "abilityType": norm.get("id")}}, 90)
        return isinstance(r, dict) and r.get("ok")
    pos = me.get("pos") or {}
    enemies = [u for u in units if u.get("owner") != mine and u.get("alive") and (u.get("pos") or {})]
    if pos.get("col") is None or not enemies:
        return False
    tgt = min(((u["pos"]["col"], u["pos"]["row"]) for u in enemies),
              key=lambda p: abs(p[0] - pos["col"]) + abs(p[1] - pos["row"]))
    dist = _bfs(board, board.id_at(*tgt))
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


def _hp_full(observe, uid):
    for u in (observe.get("units") or []):
        if u.get("squadId") == uid:
            hp, mx = u.get("hp"), u.get("hpMax")
            return hp is not None and mx is not None and int(hp) >= int(mx)
    return False


def measure_grot_age_sweep(rpc, rid, ages=(0, 1), max_turns=16):
    """Fait naitre UN grot puis mesure, aux fins de tour de son proprietaire d'age `ages`,
    le nombre de `genrand_int32` consommes LIVE et le nombre consomme par le PORT sur le meme
    etat MT de depart.

    Rend `(records, why)` -- `records` = liste de
        {age, grot, full_hp, live_rolls, port_rolls, live_spawn, port_spawn, n_grots,
         m0_player_rolls, m0_snapshot_rolls}
    et `why` = raison textuelle si la campagne n'a pas pu produire tous les ages demandes.

    Le PORT est evalue par `EndTurnOperation.execute(state, advance=False)` -- l'operation
    COMPLETE, pas seulement le vecteur de triggers : c'est elle qui porte le bump
    `turnsFinished += 1` (mirror natif) juste avant `On(0x17)`.

    Les deux colonnes `m0_*` reproduisent les DEUX regimes du port d'AVANT, qui lisait le compteur
    PAR JOUEUR `state.turn_counts[player]` :
      * `m0_player`   = le joueur a deja fini >= 2 tours -> gate VACUANT (on force `turnsFinished`
        a 99, ce qui rend le gate d'age toujours vrai : exactement l'ancien comportement) ;
      * `m0_snapshot` = etat monte par `load_state`, `turn_counts == {}` -> gate TOUJOURS FAUX (on
        laisse `turnsFinished` a 0, sa valeur par defaut apres chargement).
    """
    from engine.runner.operations.turnflow import EndTurnOperation

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")

    def dview():
        return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)

    dv = dview()
    me = next((u for u in (dv.get("units") or []) if u.get("visualId") == CARRIER), None)
    if me is None:
        return [], "%s absent du runner" % CARRIER
    mine = me["owner"]

    records = []
    want = sorted(set(int(a) for a in ages))
    birth = {}
    my_endturns = 0
    attacked = False
    for _ in range(max_turns):
        dv = dview()
        if dv.get("currentPlayer") != mine:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        grots = pilein_units(dv, mine)
        if not grots and not attacked:
            attacked = drive_and_attack(rpc, rid, board, mine)
            dv = dview()
            grots = pilein_units(dv, mine)
        for uid in grots:
            birth.setdefault(uid, my_endturns)
        if not grots:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            my_endturns += 1
            continue
        first = min(grots, key=lambda u: (birth[u], u))
        age = my_endturns - birth[first]
        if age not in want:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            my_endturns += 1
            continue

        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        full_hp = all(_hp_full(ob, g) for g in grots)

        # --- PORT : meme etat, meme MT, meme operation ---------------------------------------
        def _replay(seed_turns_finished):
            """Un `EndTurn` du port sur un etat FRAIS et le MEME etat MT. `seed_turns_finished`
            = fonction grot -> valeur posee sur `UnitComponent.turns_finished` avant l'operation."""
            st = load_state(dv, ob, snap, board=board)
            for g in grots:
                e = st.get_entity(g)
                uc = e.get_component(UnitComponent) if e is not None else None
                if uc is not None:
                    uc.turns_finished = int(seed_turns_finished(g))
            rr = CountingRng()
            rr.mt = list(rng0["mt"])
            rr.mti = int(rng0["mti"])
            st.rng = rr
            res = EndTurnOperation.execute(st, advance=False)
            spawned = sum(len(o.get("spawned") or ()) for o in (res.get("pilein") or [])
                          if isinstance(o, dict) and "grot" in o)
            return rr.rolls, spawned

        # SEED MANUEL -- il ECRASE celui que `load_state` pose depuis `combatSnapshot.turnsFinished`
        # (#234), pour que les trois regimes ci-dessous ne different QUE par cette valeur. Elle vient
        # de l'age OBSERVE (naissance tracee), pas d'une derivation.
        port_rolls, port_spawn = _replay(lambda g: my_endturns - birth[g])
        # `- 1` : `EndTurnOperation` bumpe, donc pour que le gate voie 99 il faut partir de 98 ;
        # ce qui compte est qu'il soit VACUANT, comme l'etait le test `turn_counts >= 2`.
        m0_player_rolls, _ = _replay(lambda g: 98)
        m0_snapshot_rolls, _ = _replay(lambda g: 0)    # la valeur EXACTE que `load_state` laisse

        # --- LIVE ---------------------------------------------------------------------------
        act = rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
        my_endturns += 1
        if not (isinstance(act, dict) and act.get("ok")):
            return records, "endturn refuse: %s" % str(act)[:160]
        rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
        live_rolls = count_genrand(rng0, rng1)
        live_spawn = len(pilein_units(dview(), mine) - grots)

        records.append({"age": age, "grot": first, "full_hp": full_hp,
                        "live_rolls": live_rolls, "port_rolls": port_rolls,
                        "live_spawn": live_spawn, "port_spawn": port_spawn,
                        "n_grots": len(grots),
                        "m0_player_rolls": m0_player_rolls,
                        "m0_snapshot_rolls": m0_snapshot_rolls})
        want.remove(age)
        if not want:
            return records, ""
    return records, "ages non atteints en %d tours: %s" % (max_turns, want)
