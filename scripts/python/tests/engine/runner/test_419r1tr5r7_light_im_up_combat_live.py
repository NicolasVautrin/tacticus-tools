"""#419-r1-tr5-r7 -- face **COMBAT** de `LightImUp` (1103, passif de kit d'`orksWarboss`).

RE + residus : `engine/runner/operations/triggers/loki/light_im_up.py`.
Mesures et contre-epreuves : `probe_419r1tr5r7_light_im_up_combat.py`,
`docs/rl/case-419-r1-tr5-r7-light-im-up-combat.md`.

⚠ La face DECISION (playbook, #419-r1-tr5) est portee DEPUIS LONGTEMPS et ne dit RIEN de la face
COMBAT, qui etait un NO-OP SILENCIEUX (absente d'`ABILITY_TRIGGERS`). Les deux faces ne portent
d'ailleurs PAS la meme gate : le playbook gate `IsMeleeAttack(case)`, l'execution ne gate QUE
`IsInAttackRange`. C'est le scenario A DISTANCE qui le prouve.

TROIS scenarios CRAFTES (positions PILOTEES -- le runner est un bac a sable), chacun confronte au
LIVE par replay-diff RNG-seede sur le MEME etat :

 1. MELEE (d = 1)     -- le passif frappe la cible de l'attaque normale, `nrOfHits` coups
                         Projectile. PV offline == PV live.
 2. A DISTANCE (d = 3) -- `orksWarboss` porte DEUX armes (melee Eviscerate 2 coups + Projectile
                         Range 3, 1 coup) : a d = 3 il TIRE, et le passif part QUAND MEME. C'est
                         le discriminant de l'absence de gate de melee -- une gate d'adjacence
                         recopiee du playbook annulerait 100 % du passif ici (mesure : 12 933 de
                         degat qui disparaissent).
 3. REPORT (volet 2)  -- T1 meurt de l'attaque NORMALE, donc le volet 1 tombe entierement sur un
                         cadavre -> `NumLeftOverHits` = `nrOfHits`, reportes sur T2 qui SURVIT.
                         Regime NON SATURE des deux cotes (T2 vivante, montant non nul).

Lit l'etat LIVE (rien de hardcode). ASCII only.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.entities.pathfinding.board import Board
from engine.runner.components import HealthComponent
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

WARBOSS = "orksWarboss"
T1_VIS = "astraBullgryn"          # la plus proche apres le pilotage -> cible de l'attaque normale
T2_VIS = "necroWarden"            # dans le disque `range = 3` du passif -> cible du report
SEED = "419503"
BOARD = "MC1_67"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _dist(board, a, b):
    src, dst = board.id_at(a[0], a[1]), board.id_at(b[0], b[1])
    if src is None or dst is None:
        return None
    seen, q = {src: 0}, deque([src])
    while q:
        x = q.popleft()
        if x == dst:
            return seen[x]
        for n in board.neighbours(x):
            if n not in seen:
                seen[n] = seen[x] + 1
                q.append(n)
    return None


def _alive(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _normal_attack_id(dv, uid):
    for u in (dv.get("units") or []):
        if int(u["id"]) == int(uid):
            for ab in (u.get("abilities") or []):
                if ab.get("kind") == "normal":
                    return int(ab["id"])
    return None


def _live_hp_from_events(res):
    """PV LIVE = le dernier `UnitStats_RemainingHealth` que le NATIF a ecrit sur chaque cible.

    ⚠ Ce n'est pas une commodite : `decisionView` relu APRES l'action et `applyAction().units`
    rendent tous deux `hp` INCHANGE pour une unite qui n'est pas la cible de l'action -- mesure du
    2026-08-11 sur le report du volet 2 (T2 frappee de 908, les deux capteurs rendent 900000, les
    events du natif rendent 899092). Un capteur qui ne voit pas la mutation qu'il doit juger
    fabrique une fausse divergence. Residu `#419-r1-tr5-r8`."""
    out = {}
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "UnitStats_RemainingHealth" in td and td.get("Target_Id") is not None:
                out[int(td["Target_Id"])] = td["UnitStats_RemainingHealth"]
    return out


def _passive_hits(res, ability_id):
    """[(target, amount)] des coups du PASSIF. Les tags du natif les marquent
    `Passive_Ability_Type` (l'`AbilityOrEffect` d'un TRIGGERED n'est pas un `ActiveAbilityType`,
    donc `Active_Ability_Type` est ABSENT sur ces events -- lu, pas suppose)."""
    out = []
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Passive_Ability_Type") == int(ability_id):
                out.append((int(td["Target_Id"]), td["Amount"]))
    return out


def _drive(rpc, rid, board, want_dist, turns=30):
    """DEPLACE le warboss a la distance EXACTE `want_dist` de l'ennemi le plus proche (doctrine :
    on DRIVE la position, on ne subit pas la geometrie de spawn). La cible est EXACTE, pas un
    plafond -- un `d <= want_dist` rendrait toujours 1 et le regime A DISTANCE ne serait jamais
    atteint."""
    for _ in range(turns):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        cu = _alive(dv, WARBOSS)
        if cu is None:
            return None
        foes = [u for u in (dv.get("units") or [])
                if u.get("alive") and u.get("owner") != cu.get("owner")]
        if not foes:
            return None
        best = min(foes, key=lambda u: (_dist(board, _pos(cu), _pos(u)) or 99))
        d = _dist(board, _pos(cu), _pos(best))
        if d == want_dist:
            return dv
        if dv.get("currentPlayer") != cu.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        row = next((x for x in (mt.get("units") or [])
                    if int(x.get("unitId") or -1) == int(cu["id"])), None)
        tiles = list((row or {}).get("tiles") or [])
        if not tiles:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        tgt = _pos(best)
        tiles.sort(key=lambda t: abs((_dist(board, (t["col"], t["row"]), tgt) or 99) - want_dist))
        t0 = tiles[0]
        if (_dist(board, (t0["col"], t0["row"]), tgt) or 99) == d:
            return dv                                     # plus rien a gagner
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": int(cu["id"]),
            "to": {"col": t0["col"], "row": t0["row"]}}}, 40)
    return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)


def _scenario(rpc, build_runner, want_dist, extra):
    b = build_runner(SEED, extra=["--board", BOARD, "--rank", "17", "--no-ai",
                                  "--p-units", WARBOSS,
                                  "--a-units", f"{T2_VIS},{T1_VIS}",
                                  "--hp-player", "900000"] + list(extra))
    rid = b["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        return {"ok": False, "reason": "boardGraph indispo"}
    board = Board(bg["tiles"], adjacency="evenq")
    dv = _drive(rpc, rid, board, want_dist)
    if dv is None:
        return {"ok": False, "reason": "pilotage KO"}
    cu = _alive(dv, WARBOSS)
    foes = [u for u in (dv.get("units") or [])
            if u.get("alive") and u.get("owner") != cu.get("owner")]
    if cu is None or len(foes) < 2:
        return {"ok": False, "reason": "roster incomplet apres pilotage"}
    d_by = {int(u["id"]): _dist(board, _pos(cu), _pos(u)) for u in foes}
    t1 = min(d_by, key=lambda k: d_by[k])
    t2 = sorted([k for k in d_by if k != t1], key=lambda k: d_by[k])[0]
    if d_by[t1] != want_dist:
        return {"ok": False, "reason": f"distance {d_by[t1]} != {want_dist} apres pilotage"}
    nat = _normal_attack_id(dv, int(cu["id"]))
    if nat is None:
        return {"ok": False, "reason": "pas d'attaque normale sur le caster"}
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    state = load_state(dv, ob, snap, board=board)
    hp0 = {}
    for uid in [int(cu["id"]), t1, t2]:
        e = state.get_entity(uid)
        hc = e.get_component(HealthComponent) if e is not None else None
        if hc is None or hc.hp is None:
            return {"ok": False, "reason": "unite sans PV offline"}
        hp0[uid] = hc.hp
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        return {"ok": False, "reason": "dumpRng KO"}
    rng = IntBasedMersenneTwister()
    rng.mt = list(s0["mt"]); rng.mti = s0["mti"]
    state.rng = rng
    runner = Runner(state).install_default_handlers(20)
    res = rpc("applyAction", {"runnerId": rid, "captureEvents": True, "action": {
        "kind": "ability", "casterId": int(cu["id"]), "targetId": t1,
        "abilityType": nat}}, 120)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        return {"ok": False, "reason": f"attaque live KO: {str(res)[:200]}"}
    live_hp = _live_hp_from_events(res)
    runner.apply(AttackUnitMessage(int(cu["id"]), t1))
    off_hp = {}
    for uid in hp0:
        e = state.get_entity(uid)
        hc = e.get_component(HealthComponent) if e is not None else None
        off_hp[uid] = hc.hp if hc is not None else None
    return {"ok": True, "reason": None, "caster": int(cu["id"]), "t1": t1, "t2": t2,
            "dist": d_by[t1], "d_t2": d_by[t2], "hp0": hp0, "live_hp": live_hp,
            "off_hp": off_hp, "passive": _passive_hits(res, 1103)}


@pytest.fixture(scope="function")
def liu_melee(live_session, rpc, build_runner):
    return _scenario(rpc, build_runner, 1, ["--hp-target", "900000"])


@pytest.fixture(scope="function")
def liu_ranged(live_session, rpc, build_runner):
    return _scenario(rpc, build_runner, 3, ["--hp-target", "900000"])


@pytest.fixture(scope="function")
def liu_report(live_session, rpc, build_runner):
    # PV DISSOCIES par `--unit-stat` : `--hp-target` force une valeur unique sur tout le camp, donc
    # T1 et T2 mourraient ENSEMBLE et le report serait mesure sur une cible SATUREE (PV clampes a
    # 0 des deux cotes = zero information). `RemainingHealth` EN PLUS de `Health` : le natif lit le
    # premier, et `buildNormalizedBC` recalcule le second.
    return _scenario(rpc, build_runner, 1, [
        "--unit-stat", f"{T1_VIS}:Health=2000,RemainingHealth=2000",
        "--unit-stat", f"{T2_VIS}:Health=900000,RemainingHealth=900000"])


def test_light_im_up_combat_melee(liu_melee):
    """MELEE (d = 1) : apres l'attaque normale, le passif porte `nrOfHits` coups Projectile sur la
    MEME cible. Le port reproduit les PV AU PV PRES -- ce qui prouve aussi que les coups du passif
    sont joues au MEME RANG dans le flux RNG que le natif (un decalage l'aurait desynchronise)."""
    c = liu_melee
    if not c["ok"]:
        pytest.skip(c["reason"])
    t1 = c["t1"]
    on_t1 = [a for tgt, a in c["passive"] if tgt == t1]
    assert on_t1, ("AUCUN coup de passif live sur T1 -- le scenario n'exerce rien "
                   f"(passive={c['passive']})")
    assert c["live_hp"].get(t1) is not None and c["live_hp"][t1] < c["hp0"][t1], (
        f"T1 n'a rien encaisse live ({c['live_hp'].get(t1)} vs {c['hp0'][t1]}) -- regime sature")
    assert c["off_hp"][t1] == c["live_hp"][t1], (
        f"PV T1 offline {c['off_hp'][t1]} != live {c['live_hp'][t1]} "
        f"(coups de passif live = {on_t1})")


def test_light_im_up_combat_fires_at_range(liu_ranged):
    """A DISTANCE (d = 3) -- LE discriminant de la tranche. `orksWarboss` porte une arme Projectile
    de portee 3 : a d = 3 son attaque normale est un TIR, et le passif part QUAND MEME. La face
    DECISION, elle, gate `IsMeleeAttack(case)` ; recopier cette gate ici (le voisin de forme)
    annulerait 100 % du passif dans ce regime -- contre-epreuve mesuree
    (`probe_419r1tr5r7_light_im_up_combat.py --dist 3 --mutant melee-gate`) : 12 933 de degat qui
    disparaissent, `rc = 1`."""
    c = liu_ranged
    if not c["ok"]:
        pytest.skip(c["reason"])
    t1 = c["t1"]
    assert c["dist"] >= 2, f"scenario NON discriminant : le caster est a d={c['dist']}"
    on_t1 = [a for tgt, a in c["passive"] if tgt == t1]
    assert on_t1, ("le passif n'a PAS fire A DISTANCE live -- si c'etait le natif, une gate de "
                   f"melee existerait et le decompile la porterait (passive={c['passive']})")
    assert c["off_hp"][t1] == c["live_hp"][t1], (
        f"PV T1 offline {c['off_hp'][t1]} != live {c['live_hp'][t1]} a d={c['dist']} "
        f"(coups de passif live = {on_t1})")


def test_light_im_up_combat_leftover_report(liu_report):
    """REPORT (volet 2) : T1 (2 000 PV) meurt de l'attaque NORMALE, donc les `nrOfHits` coups du
    volet 1 tombent tous sur un cadavre -> `NumLeftOverHits` rend `nrOfHits` et le volet 2 les
    porte sur T2, tiree dans le disque `range = 3`.

    REGIME NON SATURE DES DEUX COTES : T2 SURVIT (900 000 PV) et son montant est non nul -- c'est
    ce qui donne au verdict un contenu. C'est aussi la premiere confrontation live de la branche
    « cible DEJA MORTE a l'entree » de `ChainLeftOverHitsAttackDamage._left_over_hits`, jusqu'ici
    « modelisee, non confrontee »."""
    c = liu_report
    if not c["ok"]:
        pytest.skip(c["reason"])
    t1, t2 = c["t1"], c["t2"]
    assert c["live_hp"].get(t1) == 0, (
        f"T1 n'est pas morte live ({c['live_hp'].get(t1)}) -- le volet 2 n'est pas arme")
    on_t2 = [a for tgt, a in c["passive"] if tgt == t2]
    assert on_t2, (f"AUCUN report live sur T2 (d={c['d_t2']}) -- passive={c['passive']}")
    assert c["live_hp"].get(t2) is not None and 0 < c["live_hp"][t2] < c["hp0"][t2], (
        f"T2 doit SURVIVRE en ayant encaisse : hp0={c['hp0'][t2]} live={c['live_hp'].get(t2)} "
        "(morte ou intacte = regime sature, verdict vide)")
    assert c["off_hp"][t2] == c["live_hp"][t2], (
        f"PV T2 offline {c['off_hp'][t2]} != live {c['live_hp'][t2]} "
        f"(report live = {on_t2})")
    assert c["off_hp"][t1] == c["live_hp"][t1], (
        f"PV T1 offline {c['off_hp'][t1]} != live {c['live_hp'][t1]}")
