"""MONTAGE REUTILISABLE des scenarios SUMMON live-vs-port (helpers + fabriques de scenario).

Extrait de `test_summon_consumers_live.py` (deplacement VERBATIM des helpers `_board`,
`_legal_targets`, `_drive_until_castable`, `_cast_and_replay`) pour que le montage --
roster, board, seed, positions DRIVEES -- soit REUTILISABLE par un autre test ou un probe,
au lieu d'etre re-craft inline a chaque fois.

Deux fabriques de scenario y sont exposees, qui rendent le MEME dict (celui de
`cast_and_replay`, augmente de `rid`, `caster_id`, `caster_pos`, `enemy_id`) -- un test passe
donc de l'une a l'autre sans re-ecrire ses assertions :

  * `waaagh_scenario(rpc, build_runner)` -- board `MC1_67`, seed 31337, Warboss SEUL vs
    necroWarden+necroDestroyer. Le Warboss est rapproche tour par tour jusqu'a ce que le NATIF
    publie une cible legale pour Waaagh (1058).

  * `waaagh_ally_scenario(rpc, build_runner)` -- board `C3_01`, seed 777, roster a DEUX heros
    (Warboss + `orksNob`). Les TROIS parametres different du precedent : c'est le montage de
    GENERALISATION. Expose en plus l'allie Ork avant/apres le cast.

`cast_and_replay` capture aussi `live_new_stats` = les stats RESOLUES (`combatSnapshot`
POST-cast) des unites APPARUES pendant le cast : la seule source qui publie le `movement` d'un
summon frais, donc la seule facon de confronter une GRANDEUR plutot qu'une geometrie.
`port_spawn_positions(d)` rend les tuiles d'APPARITION cote port (le dict de resultat ne porte
que les positions finales), ce qui permet de mesurer la DISTANCE PARCOURUE. ASCII-only.
"""
from __future__ import annotations

import pytest

import hexgeo

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, PositionComponent


# --- roster / board / seed du montage Waaagh (source unique) ---------------------------------- #
WAAAGH_CASTER = "orksWarboss"
WAAAGH_ENEMY = "necroWarden"
WAAAGH_FOIL = "necroDestroyer"
WAAAGH_SEED = "31337"
BOY_VIS = {"orksOrkBoys", "orksNpc2OrkBoy"}      # config id / visualId (cf. VisualUnitIdFromUnitId)
WAAAGH_ABILITY = 1058


def upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def board_of(rpc, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    return Board(bg["tiles"], adjacency="evenq")


def legal_targets(rpc, rid, uid, ability):
    """Cibles LEGALES de `ability` pour l'unite `uid`, telles que le NATIF les publie (`abilityTargets`
    -> `GetDynamicInvalidTargetReason` de la classe d'ability). C'est la SEULE porte fiable : p.ex.
    `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetDynamicInvalidTargetReason` n'accepte une cible que s'il existe au moins
    une tuile de CHARGE (`GetPossibleMovementTiles` non vide) -> un simple critere de distance ne suffit
    pas (verifie live : cible a dist 2 REFUSEE, cible a dist 5 ACCEPTEE)."""
    at = rpc("abilityTargets", {"runnerId": rid}, 90)
    out = []
    for u in (at.get("units") or []):
        if u.get("unitId") != uid:
            continue
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != int(ability):
                continue
            for t in (a.get("targets") or []):
                if t.get("targetId") is not None:
                    out.append(t["targetId"])
    return out


def drive_until_castable(rpc, rid, caster_vis, enemy_vis, ability, tries=16, max_dist=None):
    """Rapproche le caster de l'ennemi, tour par tour, JUSQU'A ce que le natif publie une cible legale
    pour `ability` (et, si `max_dist` est donne, que la distance soit <= max_dist).
    Renvoie (caster_live, target_id). Skip si jamais castable.

    `max_dist` sert aux abilities dont la porte de TARGETING est PLUS LARGE que la garde d'EXECUTION :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$GetNextSpawnTile` exige `IsInRange(caster, target, range=2)` alors que
    `abilityTargets` accepte la cible bien au-dela (verifie live : cible legale a dist 5, 0 summon)."""
    for _ in range(tries):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        c = next((u for u in (dv.get("units") or []) if u.get("visualId") == caster_vis), None)
        e = next((u for u in (dv.get("units") or []) if u.get("visualId") == enemy_vis), None)
        if c is None or e is None:
            pytest.skip(f"{caster_vis}/{enemy_vis} absent")
        cp, ep = upos(c), upos(e)
        if cp[0] is None or ep[0] is None:
            pytest.skip("positions absentes")
        if dv.get("currentPlayer") != c.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        d = hexgeo.distance(cp, ep)
        tgts = legal_targets(rpc, rid, c["id"], ability)
        if tgts and (max_dist is None or d <= max_dist):
            return c, (e["id"] if e["id"] in tgts else tgts[0])
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == c["id"]), None)
        best = None
        for t in (mu or {}).get("tiles") or []:
            if t.get("col") is None:
                continue
            dd = hexgeo.distance((t["col"], t["row"]), ep)
            if best is None or dd < best[0]:
                best = (dd, (t["col"], t["row"]))
        if best is None or best[0] >= d:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": c["id"], "to": {"col": best[1][0], "row": best[1][1]}}}, 60)
        if legal_targets(rpc, rid, c["id"], ability) and (max_dist is None or best[0] <= max_dist):
            dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            c = next(u for u in dv["units"] if u.get("visualId") == caster_vis)
            tg = legal_targets(rpc, rid, c["id"], ability)
            return c, (e["id"] if e["id"] in tg else tg[0])
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    pytest.skip(f"{caster_vis} : aucune cible legale pour {ability} (geometrie)")


def cast_and_replay(rpc, rid, board, caster_id, target_id, ability, ability_cls, new_vis):
    """Capture l'etat-avant, caste LIVE, rejoue le PORT sur le MEME etat-avant (rng cale)."""
    dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    ids_before = {u["id"] for u in dv0["units"]}
    tgt0 = next((u for u in dv0["units"] if u["id"] == target_id), None)
    tgt_hp0 = (tgt0 or {}).get("hp")

    act = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "targetId": target_id,
        "abilityType": ability}}, 120)
    a0 = ((act or {}).get("actions") or [{}])[0]
    if not a0.get("mutated"):
        pytest.skip(f"cast live non mute (ability {ability} refusee : {a0.get('error')})")
    dv1 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    dv1_units = dv1.get("units") or []
    # Filet : si la bataille s'est TERMINEE au cast (cible tuee), `decisionView` ne publie plus d'unites
    # -> on lit les apparitions dans les `changes` de l'action (source PRIMAIRE, publiee par le runner).
    live_new = [u for u in dv1_units if u["id"] not in ids_before]
    live_summons = [u for u in live_new if u.get("visualId") in new_vis]
    appeared = [ch for ch in (a0.get("changes") or []) if ch.get("appeared")]
    tgt1 = next((u for u in dv1_units if u["id"] == target_id), None)
    live_tgt_delta = (tgt_hp0 or 0) - ((tgt1 or {}).get("hp") or 0)
    if tgt1 is None:                                  # bataille finie -> delta lu dans les changes
        ch = next((c for c in (a0.get("changes") or []) if c.get("squadId") == target_id), None)
        if ch is not None:
            live_tgt_delta = -(ch.get("hpDelta") or 0)
    live_effects = {ef.get("name") for u in dv1_units if u["id"] == caster_id
                    for ef in (u.get("effects") or [])}
    # STATS NATIVES des unites APPARUES pendant le cast (`combatSnapshot` POST-cast) : c'est la seule
    # source qui publie les stats RESOLUES d'un summon frais (`movement`, `attack`, ...) -- ni
    # `decisionView` ni les `changes` ne les portent. Sert a confronter une GRANDEUR (et pas une
    # geometrie) entre le summon natif et le summon porte.
    snap1 = rpc("combatSnapshot", {"runnerId": rid}, 60)
    live_new_stats = {su.get("entityId"): (su.get("stats") or {})
                      for su in (snap1.get("units") or [])
                      if su.get("entityId") not in ids_before}

    def _fresh():
        st = load_state(dv0, ob0, snap, board=board)
        if isinstance(s0, dict) and s0.get("mt"):
            rng = IntBasedMersenneTwister()
            rng.mt = list(s0["mt"])
            rng.mti = s0["mti"]
            st.rng = rng
        return st

    state = _fresh()
    port_hp0 = state.get_entity(target_id).get_component(HealthComponent).hp
    res = ability_cls().execute_behaviour(state, caster_id, target_id)
    port_tgt_delta = port_hp0 - state.get_entity(target_id).get_component(HealthComponent).hp
    return {"res": res, "state": state, "fresh": _fresh, "dv0": dv0, "act": a0,
            # `dv1` = la vue de DECISION POST-cast entiere. Expose (#291) parce que `toActivate`
            # (= `IsControlledByCurrentPlayer && IsAlive && HasActionLeft`, cf.
            # `ai-step/internals.ts::toActivateSquads`) est la seule facon de LIRE, cote natif, le
            # `MarkUnitAsNoActionAvailable` que `FinishUnitTurnOperation` pose sur un summon frais.
            "dv1": dv1, "live_new": live_new,
            "live_summons": live_summons, "live_appeared": appeared,
            "live_tgt_delta": live_tgt_delta, "live_new_stats": live_new_stats,
            "port_tgt_delta": port_tgt_delta, "live_effects": live_effects}


# ============================================================================================== #
# Fabriques de SCENARIO -- le montage lui-meme (roster + board + seed + positions drivees).
# ============================================================================================== #

def waaagh_scenario(rpc, build_runner):
    """Montage HISTORIQUE : Warboss seul (seed 31337, board par defaut MC1_67) vs
    necroWarden+necroDestroyer, approche jusqu'a la premiere cible legale pour Waaagh (1058)."""
    from engine.runner.abilities.orks import WaaaghAbility
    rid = build_runner(WAAAGH_SEED, extra=["--p-units", WAAAGH_CASTER,
                                           "--a-units", f"{WAAAGH_ENEMY},{WAAAGH_FOIL}"])["rid"]
    board = board_of(rpc, rid)
    c, tid = drive_until_castable(rpc, rid, WAAAGH_CASTER, WAAAGH_ENEMY, WAAAGH_ABILITY)
    d = cast_and_replay(rpc, rid, board, c["id"], tid, WAAAGH_ABILITY, WaaaghAbility, BOY_VIS)
    d.update({"rid": rid, "caster_id": c["id"], "caster_pos": upos(c), "enemy_id": tid})
    return d


# --- montage ALTERNATIF (generalisation) : board, seed et roster DIFFERENTS -------------------- #
WAAAGH_ALLY = "orksNob"        # Hero Orks : MEME faction (donc BUFFE) mais visualId != orksOrkBoys
WAAAGH_ALT_BOARD = "C3_01"
WAAAGH_ALT_SEED = "777"


def waaagh_ally_scenario(rpc, build_runner):
    """Montage ALTERNATIF : board `C3_01`, seed 777, roster a DEUX heros (Warboss + `orksNob`).
    Aucun de ces trois parametres n'a servi a construire le port -- c'est le montage de
    GENERALISATION. En plus du dict de `cast_and_replay`, il expose l'allie Ork (buffe mais pas
    pousse a agir : `UnitsWithVisualId` ne retient que les `orksOrkBoys`) AVANT et APRES le cast."""
    from engine.runner.abilities.orks import WaaaghAbility
    rid = build_runner(WAAAGH_ALT_SEED,
                       extra=["--p-units", f"{WAAAGH_CASTER},{WAAAGH_ALLY}",
                              "--a-units", f"{WAAAGH_ENEMY},{WAAAGH_FOIL}",
                              "--board", WAAAGH_ALT_BOARD])["rid"]
    board = board_of(rpc, rid)
    c, tid = drive_until_castable(rpc, rid, WAAAGH_CASTER, WAAAGH_ENEMY, WAAAGH_ABILITY)
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ally = next((u for u in dv["units"] if u.get("visualId") == WAAAGH_ALLY), None)
    if ally is None:
        pytest.skip("allie ork absent")
    ally_pos_before = upos(ally)
    d = cast_and_replay(rpc, rid, board, c["id"], tid, WAAAGH_ABILITY, WaaaghAbility, BOY_VIS)
    dv1 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ally1 = next((u for u in (dv1.get("units") or []) if u["id"] == ally["id"]), None)
    d.update({"rid": rid, "caster_id": c["id"], "caster_pos": upos(c), "enemy_id": tid,
              "ally_id": ally["id"], "ally_pos_before": ally_pos_before,
              "ally_pos_after": upos(ally1) if ally1 else None,
              "ally_effects": {ef.get("name") for ef in (ally1 or {}).get("effects") or []}})
    return d


def port_spawn_positions(d) -> dict:
    """`{entityId -> (col, row)}` des Ork Boyz A LEUR APPARITION, cote PORT.

    Rejoue le SEUL etage `Spawn` de `WaaaghAbility$$ExecuteBehaviour` sur un etat-avant FRAIS (RNG
    recale par `cast_and_replay._fresh`) -> `PickRandomly` retire les MEMES tuiles que la passe
    complete. Necessaire parce que le dict de resultat ne porte que les positions FINALES : sans la
    tuile de depart on ne peut pas mesurer la DISTANCE PARCOURUE, seulement la distance au caster.
    (Le natif ne publie pas la tuile de spawn : `changes.appeared.to` est deja la position FINALE --
    mesure : dist 3 du caster alors que le spawn est un hex ADJACENT.)"""
    import gameconfig as GC
    from engine.dsl.effects import ExecutionContext
    from engine.runner.abilities.behaviours import entities_from_state
    from engine.runner.abilities.orks import waaagh_spawn_tree
    st = d["fresh"]()
    n = int(((GC.ability("Waaagh") or {}).get("constants") or {}).get("nrOfSummons") or 0)
    ectx = ExecutionContext(state=st, rng=st.rng)
    waaagh_spawn_tree(n).execute(entities_from_state(st, d["caster_id"], d["enemy_id"]), ectx)
    out = {}
    for nm, p in ectx.emitted:
        if nm != "SpawnUnit":
            continue
        pc = st.get_entity(p["unit"]).get_component(PositionComponent)
        if pc is not None:
            out[p["unit"]] = (pc.col, pc.row)
    return out
