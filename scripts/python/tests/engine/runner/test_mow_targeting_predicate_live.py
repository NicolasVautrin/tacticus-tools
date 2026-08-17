"""Les 3 abilities MACHINE OF WAR a PREDICAT DE CIBLAGE conditionnel (tache #90 lot A).

Ces 3 abilities rendent **0 cible au spawn** : leur legalite de cible depend de la CONFIGURATION DU
PLATEAU (predicat natif), pas d'un defaut de harnais. Chaque test MONTE le predicat (drive-positions /
fait invoquer l'adversaire), puis confronte le PORT au natif sur la MEME scene, RNG cale (`dumpRng`).

  * `SquigLaunchas` (1200, orksRukkatrukk) — `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$GetDynamicInvalidTargetReason` :
        >= GetNumberConstant(0x78)=nrOfUnits=1  Ork allie-du-caster adjacent a la cible
     OU >= GetNumberConstant(0x79)=nrOfUnits_2=2 allies (non Steppable/Object) adjacents.
    Le SUMMON a des seuils PLUS HAUTS (`IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$FulfillsSummonCriteria` : 0x81=nrOfUnits_3=2 Orks /
    0x82=nrOfUnits_4=4 allies) -> scenario DISCRIMINANT en deux temps (1 Ork = cible legale SANS summon,
    2 Orks = cible legale AVEC summon). C'est le seul moyen de prouver que les DEUX seuils sont portes.
  * `HadesAutocannons` (1147, blackForgefiend) — la cible doit etre un **SUMMON ennemi** (TargetingOptions
    du IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$.ctor ; redit par `IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets` `UnitsWithTrait(2=Summon)`), et l'attaque
    porte sur la cible **ET** tous les summons de SON camp a <= `range`=2 hex (`SurroundingUnits(...,
    includeCenter=1)`). On fait invoquer 2 summoners adverses pour obtenir un SET multi-cibles.
  * `EntropyCannons` (1168, deathCrawler) — `IdunBattleLogic.Entities.Abilities.Active.EntropyCannonsAbility$$GetDynamicInvalidTargetReason` : cible dans une
    aura `ContagionsOfNurgle` (effet 0x42f=1071) d'un allie DU CASTER, OU FixedArmor negativement
    modifiee. On amene un porteur d'aura (deathTyphus) au contact de l'ennemi.

Aucune constante de degat attendue en dur : l'oracle est le natif (delta PV live vs delta PV du port
sur le MEME etat + le MEME RNG). Drive les positions ; state-file UNIQUE absolu ; ASCII-only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent)
from engine.runner.snapshot import load_state

AGENT_ID = "a24478d7487d3"
PYDIR = Path(__file__).resolve().parents[3]                        # scripts/python
ROOT = Path(__file__).resolve().parents[5]                         # racine repo
# SOUS `logs/`, PAS `data/` (VERSIONNE) : meme migration que les autres suites MoW (#162/#174).
STATE = ROOT / "logs" / f"_pytest_mowpredicate_{AGENT_ID}.json"     # state-file UNIQUE

BOARD = "C1_02"                 # board MoW-capable (slot MachineOfWarPosition des 2 cotes)
SEED = "4242"
SQUIG = 1200
HADES = 1147
ENTROPY = 1168


# ------------------------------------------------------------------ harnais

def _rpc_factory(host, live_session):
    def _rpc(m, b, t=90):
        r = host._rpc(live_session, m, [b], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r
    return _rpc


def _build(p_units: str, a_units: str, p_mow: str, seed: str = SEED) -> int:
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", BOARD,
         "--p-units", p_units, "--a-units", a_units, "--p-mow", p_mow,
         "--state-file", str(STATE)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        pytest.skip(f"build MoW {p_mow} KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    return json.loads(STATE.read_text())["runnerId"]


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _load(rpc, rid):
    """Etat offline + RNG cale sur le LIVE (rejeu bit-exact de la cascade a venir)."""
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    state = load_state(dec, ob, snap, board=board)
    if isinstance(s0, dict) and s0.get("mt"):
        state.rng = _seed_rng(s0)
    return state, board, dec, ob, bg


def _mow(dec, vid):
    m = next((x for x in (dec.get("mows") or []) if x.get("visualId") == vid), None)
    if m is None:
        pytest.skip(f"MoW {vid} absente de decisionView.mows (non deployee)")
    return m


def _targets(rpc, rid, caster, ability):
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": ability}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster), None)
    if row is None:
        return []
    for a in (row.get("abilities") or []):
        return a.get("targets") or []
    return []


def _move(rpc, rid, uid, col, row):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": col, "row": row}}}, 90)


def _cast(rpc, rid, caster, ability, target_id):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster, "abilityType": ability,
        "targetId": target_id}}, 90)


def _live_hp(ob):
    return {u["squadId"]: (u.get("hp"), bool(u.get("isDead"))) for u in (ob.get("units") or [])}


def _off_hp(state):
    out = {}
    for eid, e in state.entities.items():
        hc = e.get_component(HealthComponent)
        uc = e.get_component(UnitComponent)
        if hc is None:
            continue                       # MoW : ni Health ni Position (hors-plateau)
        out[eid] = (hc.hp, not bool(uc.alive) if uc is not None else False)
    return out


def _free_neighbours(bg, ob, pos):
    tiles = {t["id"]: t for t in bg["tiles"]}
    byrc = {(t["col"], t["row"]): t for t in bg["tiles"]}
    occ = {(u["col"], u["row"]) for u in (ob.get("units") or []) if not u.get("isDead")}
    t0 = byrc.get(pos)
    if t0 is None:
        return []
    return [tiles[n] for n in t0["neighbours"]
            if n in tiles and (tiles[n]["col"], tiles[n]["row"]) not in occ
            and tiles[n].get("walkable", True)]


def _dispose(host, live_session, rid):
    try:
        host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)
    except Exception:                                     # noqa: BLE001
        pass


# ============================================================== SquigLaunchas (1200)

def _squig_scene(rpc, rid, n_orks: int):
    """Monte la scene : ennemi sur une tuile a MAX de voisins libres (sans quoi le
    `CanAddUnit(AdjacentTiles(target))` du spawn est vide des que les Orks occupent les voisins),
    puis `n_orks` Orks amis AU CONTACT. Renvoie (mow, enemy_id)."""
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    m = _mow(dec, "orksRukkatrukk")
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    tiles = {t["id"]: t for t in bg["tiles"]}
    enemy = next(u for u in ob["units"] if u["teamId"] != m["team"] and not u.get("isDead"))
    occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
    best = max((t for t in bg["tiles"]
                if t.get("walkable", True) and (t["col"], t["row"]) not in occ),
               key=lambda t: sum(1 for n in t["neighbours"]
                                 if n in tiles and tiles[n].get("walkable", True)
                                 and (tiles[n]["col"], tiles[n]["row"]) not in occ))
    _move(rpc, rid, enemy["squadId"], best["col"], best["row"])
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    enemy = next(u for u in ob["units"] if u["squadId"] == enemy["squadId"])
    free = _free_neighbours(bg, ob, (enemy["col"], enemy["row"]))
    orks = [u for u in ob["units"] if u["visualId"] in ("orksNob", "orksBigMek")]
    if len(free) < n_orks + 1 or len(orks) < n_orks:
        pytest.skip("geometrie insuffisante (il faut n_orks voisins libres + 1 pour le spawn)")
    for u, t in zip(orks[:n_orks], free[:n_orks]):
        _move(rpc, rid, u["squadId"], t["col"], t["row"])
    return m, enemy["squadId"]


def _squig_case(host, live_session, n_orks: int):
    """Monte la scene a `n_orks` Orks au contact, joue le cast OFFLINE (RNG live) PUIS LIVE, et rend
    (diag_offline, off_hp_avant, off_hp_apres, live_hp_avant, live_hp_apres, spawned_live)."""
    from engine.runner.operations.summon_ai import _apply_active_ability
    rpc = _rpc_factory(host, live_session)
    rid = _build("orksNob,orksBigMek,necroDestroyer", "ultraTitus", "orksRukkatrukk")
    try:
        m, enemy_id = _squig_scene(rpc, rid, n_orks)
        cid = m["casterId"]
        tg = _targets(rpc, rid, cid, SQUIG)
        assert any(t.get("targetId") == enemy_id for t in tg), (
            f"predicat de ciblage NON monte a {n_orks} Ork(s) adjacents : targets={tg} "
            f"(IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$GetDynamicInvalidTargetReason exige >=1 Ork ou >=2 allies adjacents)")

        state, _board, _dec, ob0, _bg = _load(rpc, rid)
        off_before = _off_hp(state)
        live_before = _live_hp(ob0)
        ids_before = set(live_before)
        res = _apply_active_ability(state, cid, enemy_id, SQUIG)
        diag = (res or {}).get("diag") or {}
        assert res.get("routed") == "handler" and diag.get("ported") is True, \
            f"1200 non porte (no-op silencieux) : {res}"
        off_after = _off_hp(state)

        r = _cast(rpc, rid, cid, SQUIG, enemy_id)
        act = (r.get("actions") or [{}])[0]
        if act.get("error"):
            pytest.skip(f"cast natif 1200 refuse: {act.get('error')}")
        ob1 = rpc("observeBattle", {"runnerId": rid}, 40)
        live_after = _live_hp(ob1)
        spawned_live = [u for u in ob1["units"] if u["squadId"] not in ids_before]
        return diag, off_before, off_after, live_before, live_after, spawned_live, state, enemy_id, m
    finally:
        _dispose(host, live_session, rid)


def test_squig_launchas_one_ork_damage_no_summon(host, live_session):
    """UN Ork allie adjacent : la cible est LEGALE (nrOfUnits=1) mais le critere de SUMMON
    (`FulfillsSummonCriteria` : 2 Orks / 4 allies) n'est PAS rempli -> degat SEUL, aucun Squig.
    Confront : delta PV offline == delta PV live (RNG cale) ET zero spawn des deux cotes."""
    (diag, off0, off1, live0, live1, spawned_live,
     _state, enemy_id, _m) = _squig_case(host, live_session, n_orks=1)
    off_delta = off0[enemy_id][0] - off1[enemy_id][0]
    live_delta = live0[enemy_id][0] - live1[enemy_id][0]
    print(f"\n[SQUIG/1ork] criteria={diag.get('summon_criteria')} off_delta={off_delta} "
          f"live_delta={live_delta} spawned_off={diag.get('spawned')} "
          f"spawned_live={[(u['squadId'], u['visualId']) for u in spawned_live]}")
    assert diag.get("summon_criteria") is False, \
        "le port croit le critere de summon rempli avec 1 seul Ork adjacent (seuils 0x81/0x82)"
    assert diag.get("spawned") == [], f"le port a spawne un Squig a tort: {diag.get('spawned')}"
    assert spawned_live == [], \
        f"le natif a spawne alors que le critere est cense etre faux: {spawned_live}"
    assert off_delta > 0, "aucun degat offline (attaque 3x Physical attendue)"
    assert off_delta == live_delta, f"degat offline {off_delta} != live {live_delta}"


def test_squig_launchas_two_orks_summons_squig(host, live_session):
    """DEUX Orks allies adjacents : `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$FulfillsSummonCriteria` (>= nrOfUnits_3=2 Orks) est
    rempli -> degat ET invocation d'un Squig sur un hex LIBRE adjacent a la cible. Confront : meme
    delta PV, et le summon offline == le summon live (equipe / tuile adjacente / PV)."""
    (diag, off0, off1, live0, live1, spawned_live,
     state, enemy_id, m) = _squig_case(host, live_session, n_orks=2)
    off_delta = off0[enemy_id][0] - off1[enemy_id][0]
    live_delta = live0[enemy_id][0] - live1[enemy_id][0]
    off_spawned = diag.get("spawned") or []
    print(f"\n[SQUIG/2orks] criteria={diag.get('summon_criteria')} off_delta={off_delta} "
          f"live_delta={live_delta} spawned_off={off_spawned} "
          f"spawned_live={[(u['squadId'], u['visualId'], (u['col'], u['row']), u['hp']) for u in spawned_live]}")
    assert diag.get("summon_criteria") is True, \
        "critere de summon NON rempli avec 2 Orks adjacents (mirror FulfillsSummonCriteria)"
    assert off_delta == live_delta, f"degat offline {off_delta} != live {live_delta}"
    assert len(off_spawned) == 1, f"le port a spawne {len(off_spawned)} Squig(s) != 1"
    assert len(spawned_live) == 1, f"le natif a spawne {len(spawned_live)} unite(s) != 1"
    off_e = state.get_entity(off_spawned[0])
    off_oc = off_e.get_component(OwnerComponent)
    off_pc = off_e.get_component(PositionComponent)
    off_hc = off_e.get_component(HealthComponent)
    lv = spawned_live[0]
    assert (off_oc.team, off_oc.player) == (m["team"], m["owner"]), \
        f"summon offline owner ({off_oc.team},{off_oc.player}) != MoW ({m['team']},{m['owner']})"
    assert (lv["teamId"], lv["playerId"]) == (off_oc.team, off_oc.player), \
        "owner live != owner offline"
    assert lv["hp"] == off_hc.hp, f"hp live {lv['hp']} != offline {off_hc.hp}"
    # Le port pose l'id de CONFIG (`unitId`), le live rend l'id VISUEL (reduction documentee du
    # noeud `IdunBattleLogic.Entities.DSLFormulas$$VisualUnitIdFromUnitId`) -> on accepte les DEUX formes.
    import gameconfig as GC
    uid = ((GC.ability("SquigLaunchas") or {}).get("constants") or {}).get("unitId")
    forms = {uid, (GC.unit(uid) or {}).get("visualId")}
    assert off_e.get_component(UnitComponent).visual_id in forms
    assert lv["visualId"] in forms, f"summon live {lv['visualId']} hors {forms}"
    # tuile : LIBRE et ADJACENTE a la cible (PickRandomly d'un ensemble -> la tuile exacte peut
    # differer du tirage natif ; la CONTRAINTE, elle, est verifiee des deux cotes).
    te = state.get_entity(enemy_id).get_component(PositionComponent)
    import hexgeo
    assert hexgeo.distance((off_pc.col, off_pc.row), (te.col, te.row)) == 1, \
        "summon offline non adjacent a la cible"
    assert hexgeo.distance((lv["col"], lv["row"]), (te.col, te.row)) == 1, \
        "summon live non adjacent a la cible"


# --------------------------------------------------------- GENERALISATION : la 2e branche du predicat

def test_squig_launchas_non_ork_allies_branch(host, live_session):
    """GENERALISATION (branche NON exercee par les tests ci-dessus, ni utilisee pour construire le port)
    : le predicat a DEUX branches. Avec des allies NON-Orks, le ciblage passe des >= nrOfUnits_2=2
    (`HasMinimumAdjacentFriendlyUnits`), mais le SUMMON exige >= nrOfUnits_4=4. On monte 3 allies
    non-Orks adjacents : cible LEGALE, critere de summon FAUX (3 < 4, et 0 Ork < 2) -> degat seul.
    Autre roster, autre seed, autre porteur d'ennemi que les tests principaux."""
    from engine.runner.operations.summon_ai import _apply_active_ability
    rpc = _rpc_factory(host, live_session)
    rid = _build("necroDestroyer,necroWarden,ultraTitus", "astraBullgryn", "orksRukkatrukk",
                 seed="31337")
    try:
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        m = _mow(dec, "orksRukkatrukk")
        cid = m["casterId"]
        assert _targets(rpc, rid, cid, SQUIG) == [], "0 cible attendue au spawn (aucun allie au contact)"
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        tiles = {t["id"]: t for t in bg["tiles"]}
        enemy = next(u for u in ob["units"] if u["teamId"] != m["team"] and not u.get("isDead"))
        occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
        best = max((t for t in bg["tiles"]
                    if t.get("walkable", True) and (t["col"], t["row"]) not in occ),
                   key=lambda t: sum(1 for n in t["neighbours"]
                                     if n in tiles and tiles[n].get("walkable", True)
                                     and (tiles[n]["col"], tiles[n]["row"]) not in occ))
        _move(rpc, rid, enemy["squadId"], best["col"], best["row"])
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        enemy = next(u for u in ob["units"] if u["squadId"] == enemy["squadId"])
        free = _free_neighbours(bg, ob, (enemy["col"], enemy["row"]))
        allies = [u for u in ob["units"] if u["teamId"] == m["team"] and not u.get("isDead")]
        if len(free) < len(allies) + 1 or len(allies) < 3:
            pytest.skip("geometrie insuffisante pour 3 allies + 1 tuile de spawn")
        for u, t in zip(allies, free):
            _move(rpc, rid, u["squadId"], t["col"], t["row"])
        tg = _targets(rpc, rid, cid, SQUIG)
        print(f"\n[SQUIG/gen-nonork] allies={len(allies)} cibles={[t.get('targetId') for t in tg]}")
        assert any(t.get("targetId") == enemy["squadId"] for t in tg), \
            "2e branche du ciblage (>=2 allies NON-Orks) non montee"

        state, _b, _d, ob0, _bg = _load(rpc, rid)
        off0, live0 = _off_hp(state), _live_hp(ob0)
        ids_before = set(live0)
        res = _apply_active_ability(state, cid, enemy["squadId"], SQUIG)
        diag = (res or {}).get("diag") or {}
        assert diag.get("ported") is True, f"1200 non porte: {res}"
        off1 = _off_hp(state)
        r = _cast(rpc, rid, cid, SQUIG, enemy["squadId"])
        if (r.get("actions") or [{}])[0].get("error"):
            pytest.skip(f"cast refuse: {(r.get('actions') or [{}])[0].get('error')}")
        ob1 = rpc("observeBattle", {"runnerId": rid}, 40)
        live1 = _live_hp(ob1)
        spawned_live = [u for u in ob1["units"] if u["squadId"] not in ids_before]
        eid = enemy["squadId"]
        print(f"[SQUIG/gen-nonork] criteria={diag.get('summon_criteria')} "
              f"off_delta={off0[eid][0] - off1[eid][0]} live_delta={live0[eid][0] - live1[eid][0]} "
              f"spawned_live={[(u['squadId'], u['visualId']) for u in spawned_live]}")
        assert diag.get("summon_criteria") is False, \
            "3 allies NON-Orks ne doivent PAS remplir le critere de summon (seuils 2 Orks / 4 allies)"
        assert spawned_live == [] and (diag.get("spawned") or []) == [], \
            f"summon a tort : live={spawned_live} off={diag.get('spawned')}"
        assert off0[eid][0] - off1[eid][0] == live0[eid][0] - live1[eid][0] > 0, \
            "degat offline != live"
    finally:
        _dispose(host, live_session, rid)


# ============================================================== HadesAutocannons (1147)

def test_hades_autocannons_hits_target_and_nearby_enemy_summons(host, live_session):
    """Le predicat de ciblage exige un **SUMMON ennemi** : on fait invoquer 2 summoners adverses
    (Poxwalkers + Scarab Hive), on verifie 0 cible AVANT / N cibles APRES, puis on confronte le SET
    frappe : `IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets` = summons du camp de la CIBLE a <= range hex d'elle,
    **cible INCLUSE** (`SurroundingUnits(..., includeCenter=1)`)."""
    from engine.runner.operations.summon_ai import _apply_active_ability
    rpc = _rpc_factory(host, live_session)
    rid = _build("necroDestroyer", "deathBlightbringer,necroSpyder", "blackForgefiend")
    try:
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        m = _mow(dec, "blackForgefiend")
        cid = m["casterId"]
        assert _targets(rpc, rid, cid, HADES) == [], \
            "1147 devrait n'avoir AUCUNE cible tant qu'aucun summon ennemi n'existe"

        me = next(u for u in ob["units"] if u["teamId"] == m["team"] and not u.get("isDead"))
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        free = _free_neighbours(bg, ob, (me["col"], me["row"]))
        summoners = [u for u in ob["units"]
                     if u["visualId"] in ("necroSpyder", "deathBlightbringer")]
        for u, t in zip(summoners, free):                     # drive : summoners AU CONTACT
            _move(rpc, rid, u["squadId"], t["col"], t["row"])
        for u, ab in ((next((x for x in summoners if x["visualId"] == "deathBlightbringer"), None), 1040),
                      (next((x for x in summoners if x["visualId"] == "necroSpyder"), None), 1007)):
            if u is not None:
                _cast(rpc, rid, u["squadId"], ab, u["squadId"] if ab == 1040 else me["squadId"])
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        tg = _targets(rpc, rid, cid, HADES)
        print(f"\n[HADES] summons crees -> cibles legales {[t.get('targetId') for t in tg]}")
        if not tg:
            pytest.skip("aucun summon ennemi cree (les summoners adverses n'ont rien invoque)")

        state, _board, _dec, ob0, _bg = _load(rpc, rid)
        tid = tg[0]["targetId"]
        off_before, live_before = _off_hp(state), _live_hp(ob0)
        res = _apply_active_ability(state, cid, tid, HADES)
        diag = (res or {}).get("diag") or {}
        assert res.get("routed") == "handler" and diag.get("ported") is True, \
            f"1147 non porte (no-op silencieux) : {res}"
        off_after = _off_hp(state)
        off_hit = {u for u in off_before if off_before[u][0] != off_after[u][0]}

        r = _cast(rpc, rid, cid, HADES, tid)
        act = (r.get("actions") or [{}])[0]
        if act.get("error"):
            pytest.skip(f"cast natif 1147 refuse: {act.get('error')}")
        ob1 = rpc("observeBattle", {"runnerId": rid}, 40)
        live_after = _live_hp(ob1)
        live_hit = {u for u in live_before if u in live_after and live_before[u][0] != live_after[u][0]}
        print(f"[HADES] cible={tid} off_targets={diag.get('targets')} off_hit={sorted(off_hit)} "
              f"live_hit={sorted(live_hit)} crit_amount={diag.get('crit_amount')}")
        assert tid in off_hit, "le port n'a pas frappe la CIBLE (includeCenter=1 non porte ?)"
        assert off_hit == live_hit, \
            (f"SET de cibles divergent : offline {sorted(off_hit)} vs live {sorted(live_hit)} "
             f"(IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets : summons du camp de la cible <= range hex, cible incluse)")
        for u in sorted(live_hit):                      # meme issue par cible (mort / PV restants)
            assert off_after[u][1] == live_after[u][1], \
                f"unite {u}: mort offline={off_after[u][1]} != live={live_after[u][1]}"
            if not live_after[u][1]:
                assert off_after[u][0] == live_after[u][0], \
                    f"unite {u}: PV offline {off_after[u][0]} != live {live_after[u][0]}"
    finally:
        _dispose(host, live_session, rid)


def test_hades_autocannons_range_excludes_far_summon(host, live_session):
    """GENERALISATION (scenario NON utilise pour construire le port) : le splash est borne par
    `GetNumberConstant(0x16)=range`=2 autour de la CIBLE. On cree >= 2 summons ennemis, on en ELOIGNE
    un a distance >= 3 de la cible, et on exige qu'il ne soit frappe NI offline NI live — pendant que
    la cible, elle, l'est. Autre board (`C2_02`) et autre seed que le test principal."""
    import hexgeo
    from engine.runner.operations.summon_ai import _apply_active_ability
    rpc = _rpc_factory(host, live_session)
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "909", "--board", "C2_02",
         "--p-units", "necroDestroyer", "--a-units", "deathBlightbringer",
         "--p-mow", "blackForgefiend", "--state-file", str(STATE)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        pytest.skip(f"build KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    rid = json.loads(STATE.read_text())["runnerId"]
    try:
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        m = _mow(dec, "blackForgefiend")
        cid = m["casterId"]
        bb = next((u for u in ob["units"] if u["visualId"] == "deathBlightbringer"), None)
        if bb is None:
            pytest.skip("summoner adverse absent")
        _cast(rpc, rid, bb["squadId"], 1040, bb["squadId"])          # Poxwalkers (self-cast)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        summons = [u for u in ob["units"]
                   if u["teamId"] != m["team"] and not u.get("isDead")
                   and u["visualId"] not in ("deathBlightbringer",)]
        if len(summons) < 2:
            pytest.skip(f"il faut >= 2 summons ennemis, vu {len(summons)}")
        tgt_u, far_u = summons[0], summons[1]
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
        far_tile = next((t for t in bg["tiles"]
                         if t.get("walkable", True) and (t["col"], t["row"]) not in occ
                         and hexgeo.distance((t["col"], t["row"]),
                                             (tgt_u["col"], tgt_u["row"])) >= 3), None)
        if far_tile is None:
            pytest.skip("aucune tuile libre a distance >= 3 de la cible")
        _move(rpc, rid, far_u["squadId"], far_tile["col"], far_tile["row"])

        state, _b, _d, ob0, _bg = _load(rpc, rid)
        off_before, live_before = _off_hp(state), _live_hp(ob0)
        res = _apply_active_ability(state, cid, tgt_u["squadId"], HADES)
        assert ((res or {}).get("diag") or {}).get("ported") is True, f"1147 non porte: {res}"
        off_after = _off_hp(state)
        off_hit = {u for u in off_before if off_before[u][0] != off_after[u][0]}
        r = _cast(rpc, rid, cid, HADES, tgt_u["squadId"])
        if (r.get("actions") or [{}])[0].get("error"):
            pytest.skip(f"cast refuse: {(r.get('actions') or [{}])[0].get('error')}")
        ob1 = rpc("observeBattle", {"runnerId": rid}, 40)
        live_after = _live_hp(ob1)
        live_hit = {u for u in live_before if u in live_after and live_before[u][0] != live_after[u][0]}
        print(f"\n[HADES/range] cible={tgt_u['squadId']} eloigne={far_u['squadId']} "
              f"dist={hexgeo.distance((far_tile['col'], far_tile['row']), (tgt_u['col'], tgt_u['row']))} "
              f"off_hit={sorted(off_hit)} live_hit={sorted(live_hit)}")
        assert tgt_u["squadId"] in off_hit and tgt_u["squadId"] in live_hit, "la cible n'a pas ete frappee"
        assert far_u["squadId"] not in live_hit, \
            "le natif a frappe un summon a distance >= 3 (range=2 attendu)"
        assert far_u["squadId"] not in off_hit, \
            "le port a frappe un summon HORS du rayon (borne `range` non portee)"
        assert off_hit == live_hit, f"SET divergent : offline {sorted(off_hit)} vs live {sorted(live_hit)}"
    finally:
        _dispose(host, live_session, rid)


def test_hades_autocannons_spares_friendly_summons(host, live_session):
    """GENERALISATION la plus DISCRIMINANTE du port : `IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets` filtre par
    `Friends(target@0x178, ...)` = les allies **DE LA CIBLE**, PAS du caster. On place des summons
    A MOI (Scarab Hive) a portee de la cible ennemie : ils doivent etre EPARGNES des deux cotes.
    Un port qui aurait pris le caster pour referent (le defaut historique du noeud `Friends`) les
    frapperait -> ce test le detecterait."""
    import hexgeo
    from engine.runner.operations.summon_ai import _apply_active_ability
    rpc = _rpc_factory(host, live_session)
    rid = _build("necroSpyder", "necroSpyder", "blackForgefiend", seed="2468")
    try:
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        m = _mow(dec, "blackForgefiend")
        cid = m["casterId"]
        spy = next((u for u in ob["units"] if u["teamId"] == m["team"]
                    and u["visualId"] == "necroSpyder"), None)
        foe = next((u for u in ob["units"] if u["teamId"] != m["team"]
                    and u["visualId"] == "necroSpyder"), None)
        if spy is None or foe is None:
            pytest.skip("roster incomplet (un necroSpyder par camp attendu)")
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        # ORDRE (drive-positions) : les DEUX camps ont un summoner. (1) mon Spyder au contact du Spyder
        # adverse ; (2) MON ScarabHive sur LUI -> MES swarms autour de lui (9k PV : il survit a
        # l'on-appearance) ; (3) SON ScarabHive sur MON Spyder -> SES swarms autour de moi, donc a <= 2 hex
        # des miens = discriminant arme (summons des DEUX camps entremeles autour de la zone de contact).
        free = _free_neighbours(bg, ob, (foe["col"], foe["row"]))
        if free:
            _move(rpc, rid, spy["squadId"], free[0]["col"], free[0]["row"])
        _cast(rpc, rid, spy["squadId"], 1007, foe["squadId"])   # MES swarms autour du Spyder adverse
        _cast(rpc, rid, foe["squadId"], 1007, spy["squadId"])   # SES swarms autour du mien
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        mine = [u for u in ob["units"]
                if u["teamId"] == m["team"] and u["visualId"] not in ("necroSpyder",)
                and not u.get("isDead")]
        tg = _targets(rpc, rid, cid, HADES)
        if not tg or not mine:
            pytest.skip(f"montage incomplet (cibles={len(tg)}, summons allies={len(mine)})")
        tid = tg[0]["targetId"]
        tpos = next((u["col"], u["row"]) for u in ob["units"] if u["squadId"] == tid)
        near_mine = [u for u in mine if hexgeo.distance((u["col"], u["row"]), tpos) <= 2]
        if not near_mine:
            pytest.skip("aucun summon ALLIE a <= 2 hex de la cible (le discriminant n'est pas arme)")

        state, _b, _d, ob0, _bg = _load(rpc, rid)
        off_before, live_before = _off_hp(state), _live_hp(ob0)
        res = _apply_active_ability(state, cid, tid, HADES)
        assert ((res or {}).get("diag") or {}).get("ported") is True, f"1147 non porte: {res}"
        off_after = _off_hp(state)
        off_hit = {u for u in off_before if off_before[u][0] != off_after[u][0]}
        r = _cast(rpc, rid, cid, HADES, tid)
        if (r.get("actions") or [{}])[0].get("error"):
            pytest.skip(f"cast refuse: {(r.get('actions') or [{}])[0].get('error')}")
        ob1 = rpc("observeBattle", {"runnerId": rid}, 40)
        live_after = _live_hp(ob1)
        live_hit = {u for u in live_before if u in live_after and live_before[u][0] != live_after[u][0]}
        ids_mine = {u["squadId"] for u in near_mine}
        print(f"\n[HADES/friendly] cible={tid} allies_proches={sorted(ids_mine)} "
              f"off_hit={sorted(off_hit)} live_hit={sorted(live_hit)}")
        assert not (ids_mine & live_hit), "le natif a frappe un summon ALLIE (contredit le RE)"
        assert not (ids_mine & off_hit), \
            "le port frappe les summons ALLIES -> le referent de `Friends` est le caster au lieu de la CIBLE"
        assert off_hit == live_hit, f"SET divergent : offline {sorted(off_hit)} vs live {sorted(live_hit)}"
    finally:
        _dispose(host, live_session, rid)


# ============================================================== EntropyCannons (1168)

def test_entropy_cannons_requires_contagion_aura_then_damages(host, live_session):
    """`IdunBattleLogic.Entities.Abilities.Active.EntropyCannonsAbility$$GetDynamicInvalidTargetReason` : 0 cible tant qu'aucun ennemi n'est dans une aura
    `ContagionsOfNurgle` ALLIEE (ni n'a de FixedArmor negativement modifiee) ; amener deathTyphus
    (porteur du trait `ContagionsOfNurgle`) au contact ouvre le ciblage. Puis confront du degat
    (2x Energy, famille ABILITY) : delta PV offline == delta PV live, RNG cale."""
    from engine.runner.operations.summon_ai import _apply_active_ability
    rpc = _rpc_factory(host, live_session)
    rid = _build("deathTyphus,deathPutrifier", "ultraTitus", "deathCrawler")
    try:
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        m = _mow(dec, "deathCrawler")
        cid = m["casterId"]
        assert _targets(rpc, rid, cid, ENTROPY) == [], \
            "1168 devrait n'avoir AUCUNE cible tant qu'aucun ennemi n'est sous aura Contagion"

        enemy = next(u for u in ob["units"] if u["teamId"] != m["team"] and not u.get("isDead"))
        typhus = next(u for u in ob["units"] if u["visualId"] == "deathTyphus")
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        free = _free_neighbours(bg, ob, (enemy["col"], enemy["row"]))
        if not free:
            pytest.skip("aucune tuile libre adjacente a l'ennemi")
        _move(rpc, rid, typhus["squadId"], free[0]["col"], free[0]["row"])
        tg = _targets(rpc, rid, cid, ENTROPY)
        print(f"\n[ENTROPY] apres Typhus adjacent -> cibles {[t.get('targetId') for t in tg]}")
        assert any(t.get("targetId") == enemy["squadId"] for t in tg), \
            ("predicat de ciblage NON monte : l'ennemi adjacent a un porteur d'aura Contagion "
             "alliee devrait etre legal (IdunBattleLogic.Entities.DSLTriggers$$IsInTeamContagionsOfNurgleAura)")

        state, _board, _dec, ob0, _bg = _load(rpc, rid)
        off_before, live_before = _off_hp(state), _live_hp(ob0)
        res = _apply_active_ability(state, cid, enemy["squadId"], ENTROPY)
        diag = (res or {}).get("diag") or {}
        assert res.get("routed") == "handler" and diag.get("ported") is True, \
            f"1168 non porte (no-op silencieux) : {res}"
        off_after = _off_hp(state)

        r = _cast(rpc, rid, cid, ENTROPY, enemy["squadId"])
        act = (r.get("actions") or [{}])[0]
        if act.get("error"):
            pytest.skip(f"cast natif 1168 refuse: {act.get('error')}")
        ob1 = rpc("observeBattle", {"runnerId": rid}, 40)
        live_after = _live_hp(ob1)
        eid = enemy["squadId"]
        off_delta = off_before[eid][0] - off_after[eid][0]
        live_delta = live_before[eid][0] - live_after[eid][0]
        print(f"[ENTROPY] off_delta={off_delta} live_delta={live_delta} attacks={diag.get('attacks')}")
        assert off_delta > 0, "aucun degat offline (2x Energy attendus)"
        assert off_delta == live_delta, f"degat offline {off_delta} != live {live_delta}"
        # AUCUNE autre unite touchee (mono-cible : pas de splash dans IdunBattleLogic.Entities.Abilities.Active.EntropyCannonsAbility$$ExecuteBehaviour)
        others_off = {u for u in off_before if u != eid and off_before[u][0] != off_after[u][0]}
        others_live = {u for u in live_before
                       if u != eid and u in live_after and live_before[u][0] != live_after[u][0]}
        assert others_off == set() == others_live, \
            f"degat hors-cible : offline {others_off} live {others_live}"
    finally:
        _dispose(host, live_session, rid)
