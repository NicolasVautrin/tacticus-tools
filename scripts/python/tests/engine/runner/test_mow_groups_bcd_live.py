"""CONFRONT LIVE du reste de la tache #90 : les 5 abilities de MACHINE OF WAR des groupes B/C/D
(cf. `docs/rl/case-90-mow-effect-posers.md` -- le groupe A, « pose d'effet(s) seule », est deja livre).

    B  1161 TwinSmartMissileSystem  (tauBroadside)          unit-target  attaque filtree par ETAT + refresh
    B  1169 PlagueburstMortar       (deathCrawler)          unit-target  attaque filtree par PREDICAT + zone
    C  1143 ForwardSpotter          (astraOrdnanceBattery)  unit-target  template SPAWN + on-appearance
    D  1148 DaemonicOrdnance        (blackForgefiend)       unit-target  buff/attaque/debuff + feu de zone
    D  1187 ThriceBlessedConflagration (adeptExorcist)      unit-target  buff allie + ligne d'ennemis

PROTOCOLE (aucune constante attendue en dur -- l'oracle est le cast NATIF) : pour chaque ability on monte
un runner isole avec sa MoW, on choisit une cible LEGALE (`abilityTargets`), on execute le port OFFLINE sur
l'etat charge (`load_state` -> `_apply_active_ability`), puis on rejoue le MEME cast LIVE et on compare
(a) l'EMPREINTE D'EFFETS `{entite|TUILE -> {effectType: remaining}}` et (b) l'ENSEMBLE DES UNITES BLESSEES.

Pourquoi l'ENSEMBLE des blesses et pas le montant : le tirage de degat n'est pas cale entre `state.rng`
offline et le PRNG natif (gap connu, hors perimetre de cette tranche) -- ce qui est confronte ici est le
CIBLAGE (qui prend des coups), c'est-a-dire exactement ce que ces 5 arbres decident.

Drive les positions ; lit l'etat LIVE ; state-files UNIQUES (chemin absolu + agent id) ; ASCII-only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine.runner.operations.summon_ai import _apply_active_ability

AGENT_ID = "a143b810b752ef04b"
PYDIR = Path(__file__).resolve().parents[3]                        # scripts/python
ROOT = Path(__file__).resolve().parents[5]                         # racine repo
STATE = ROOT / "data" / f"_pytest_mowbcd_{AGENT_ID}.json"
STATE_GEN = ROOT / "data" / f"_pytest_mowbcd_gen_{AGENT_ID}.json"

BOARD = "C1_02"          # board MoW-capable (slot MachineOfWarPosition des deux cotes)
GEN_BOARD = "C2_02"
SEED = "4242"

MARKERLIGHT = 1122       # EffectType.Markerlight            (etat filtrant de 1161)
PINNED = 1065            # EffectType.Pinned                 (pose par 1169 sur les cibles valides)
CONTAMINATED = 1244      # EffectType.Contaminated           (zone de 1169)
FIRE = 5                 # EffectType.Fire                   (zone de 1148)
TBC_MELEE = 1401         # ThriceBlessedConflagration_ExtraPctDamage        (cible Sisterhood)
TBC_RANGED = 1436        # ThriceBlessedConflagration_RangedExtraPctDamage  (cible non-Sisterhood)


# ------------------------------------------------------------------ harnais (jumeau de test_mow_effect_posers_live)

def _build(state_path: Path, extra: list[str], board: str = BOARD, seed: str = SEED,
           p_units: str = "necroDestroyer,necroWarden", a_units: str = "necroDestroyer,necroWarden"):
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
         "--p-units", p_units, "--a-units", a_units,
         "--state-file", str(state_path), *extra],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_path.exists():
        return None, (proc.stderr or proc.stdout or "")[-500:]
    return json.loads(state_path.read_text())["runnerId"], None


@pytest.fixture(scope="module")
def rpc_(host, live_session):
    def _rpc(m, b, t=90):
        r = host._rpc(live_session, m, [b], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r
    return _rpc


def _seed_rng(s):
    """Cale `state.rng` sur l'etat COURANT du PRNG natif (`dumpRng`) : requis des qu'un port tire
    (`PickRandomly` de 1169, attaque on-appearance de 1143)."""
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _load(rpc, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
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
    return state, board, dec, ob


def _live_footprint(rpc, rid, board) -> dict:
    """`{id d'unite|MoW|TUILE -> {effectType: remaining}}` LIVE. Les effets de TUILE ne sont exposes que
    par `tileMeta` ; ceux d'unite/MoW par `decisionView` (cle MoW = `casterId`, PAS le `id` de la ligne)."""
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    tm = rpc("tileMeta", {"runnerId": rid}, 60) or {}
    out: dict = {}
    rows = [(u.get("id"), u) for u in (dec.get("units") or [])]
    rows += [(m.get("casterId"), m) for m in (dec.get("mows") or [])]
    for key, u in rows:
        if key is None:
            continue
        effs = {int(e["effectType"]): e.get("remaining") for e in (u.get("effects") or [])
                if e.get("effectType") is not None}
        if effs:
            out[int(key)] = effs
    for t in (tm.get("tiles") or []):
        effs = {int(e["effectType"]): e.get("remaining") for e in (t.get("effects") or [])
                if e.get("effectType") is not None}
        if effs:
            tid = board.id_at(t["col"], t["row"])
            if tid is not None:
                out[int(tid)] = effs
    return out


def _offline_footprint(state) -> dict:
    out: dict = {}
    for key, effs in (state.effects.by_unit if state.effects is not None else {}).items():
        cur = {int(e.effect_type): (0 if e.remaining_turns is None else int(e.remaining_turns))
               for e in effs if not e.consumed}
        if cur:
            out[int(key)] = cur
    return out


def _delta(before: dict, after: dict) -> dict:
    out: dict = {}
    for key, effs in after.items():
        new = {et: rem for et, rem in effs.items() if et not in (before.get(key) or {})}
        if new:
            out[int(key)] = new
    return out


def _hp_offline(state) -> dict:
    from engine.runner.components import HealthComponent
    return {eid: hc.hp for eid, hc in
            ((e.id, e.get_component(HealthComponent)) for e in state.entities.values())
            if hc is not None}


def _hp_live(rpc, rid) -> dict:
    ob = rpc("observeBattle", {"runnerId": rid}, 40) or {}
    return {u.get("squadId"): u.get("hp") for u in (ob.get("units") or [])}


def _hurt(before: dict, after: dict) -> set:
    """Ids des unites dont les PV ONT BAISSE (l'ENSEMBLE, pas le montant : cf. docstring du module)."""
    return {k for k, v in after.items()
            if before.get(k) is not None and v is not None and v < before[k]}


def _units_live(rpc, rid) -> set:
    ob = rpc("observeBattle", {"runnerId": rid}, 40) or {}
    return {u.get("squadId") for u in (ob.get("units") or []) if u.get("squadId") is not None}


def _pick_unit_target(rpc, rid, caster, ability, prefer_center=False, board=None):
    """1re cible LEGALE (`abilityTargets`), UNITE si l'ability en propose, sinon TUILE. `prefer_center`
    privilegie la tuile la plus CENTRALE (max de voisins) -- une zone castee dans un COIN est tronquee
    par les bords et n'exerce pas la forme complete."""
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": ability}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster), None)
    tgts = ((row.get("abilities") or [{}])[0].get("targets") or []) if row else []
    units = [t for t in tgts if t.get("kind") == "unit"]
    if units:
        return {"kind": "unit", "id": units[0]["targetId"]}, len(tgts)
    tiles = [t for t in tgts if t.get("kind") == "tile"]
    if tiles:
        if prefer_center and board is not None:
            tiles = sorted(tiles, key=lambda t: -len(board.neighbours(
                board.id_at(t["tile"]["col"], t["tile"]["row"]) or -1)))
        tl = tiles[0]["tile"]
        return {"kind": "tile", "col": tl["col"], "row": tl["row"]}, len(tgts)
    return None, 0


def _cast_live(rpc, rid, caster, ability, tgt):
    action = {"kind": "ability", "casterId": caster, "abilityType": ability}
    if tgt["kind"] == "unit":
        action["targetId"] = tgt["id"]
    else:
        action["to"] = {"col": tgt["col"], "row": tgt["row"]}
    r = rpc("applyAction", {"runnerId": rid, "action": action}, 90) or {}
    return (r.get("actions") or [{}])[0]


def _confront(rpc, ability, carrier, state_path=STATE, board_id=BOARD, extra=None, endturn=0,
              p_units="necroDestroyer,necroWarden", a_units="necroDestroyer,necroWarden",
              prefer_center=False):
    """Monte le runner, choisit la cible, execute OFFLINE puis LIVE ; rend
    (diag, off_delta, live_delta, off_hurt, live_hurt, ctx)."""
    rid, err = _build(state_path, list(extra or []) + ["--p-mow", carrier], board=board_id,
                      p_units=p_units, a_units=a_units)
    if rid is None:
        pytest.skip(f"build MoW {carrier} KO: {err}")
    for _ in range(endturn):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    state, board, dec, _ob = _load(rpc, rid)
    m = next((x for x in (dec.get("mows") or []) if x.get("visualId") == carrier), None)
    if m is None:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        pytest.skip(f"MoW {carrier} non deployee")
    caster = m["casterId"]
    tgt, n_tgts = _pick_unit_target(rpc, rid, caster, ability, prefer_center, board)
    if tgt is None:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        pytest.skip(f"aucune cible legale pour {ability}")

    off_before, hp_off_before = _offline_footprint(state), _hp_offline(state)
    tid = tgt["id"] if tgt["kind"] == "unit" else board.id_at(tgt["col"], tgt["row"])
    res = _apply_active_ability(state, caster, tid, ability)
    diag = (res or {}).get("diag") or {}
    assert res.get("routed") == "handler" and diag.get("ported") is True, \
        f"ability {ability} non portee (routed={res.get('routed')})"
    off_delta = _delta(off_before, _offline_footprint(state))
    off_hurt = _hurt(hp_off_before, _hp_offline(state))

    live_before, hp_live_before = _live_footprint(rpc, rid, board), _hp_live(rpc, rid)
    units_before = _units_live(rpc, rid)
    act = _cast_live(rpc, rid, caster, ability, tgt)
    if act.get("error"):
        rpc("disposeRunner", {"runnerId": rid}, 20)
        pytest.skip(f"cast natif bloque: {act.get('error')}")
    live_delta = _delta(live_before, _live_footprint(rpc, rid, board))
    live_hurt = _hurt(hp_live_before, _hp_live(rpc, rid))
    ctx = {"rid": rid, "caster": caster, "target": tgt, "tileId": tid, "board": board, "mow": m,
           "nTargets": n_tgts, "dec": dec, "state": state, "diag": diag,
           "unitsBefore": units_before, "unitsAfter": _units_live(rpc, rid)}
    return diag, off_delta, live_delta, off_hurt, live_hurt, ctx


def _dispose(rpc, ctx):
    try:
        rpc("disposeRunner", {"runnerId": ctx["rid"]}, 20)
    except Exception:
        pass


def _coords(board, keys):
    return sorted(board.coord(k) for k in keys if k in board.by_id)


# ------------------------------------------------------------------ CONFRONT par ability

def test_twin_smart_missile_system_confront_live(rpc_):
    """1161 `IdunBattleLogic.Entities.Abilities.Active.Loki.TwinSmartMissileSystemAbility$$ExecuteBehaviour`.

    Runner FRAIS : personne ne porte `Markerlight` -> `EntitiesWithAnyEffect(Enemies, 1122)` est VIDE ->
    AUCUN degat, et la branche `AddEffect` du `If` marque la cible. C'est la structure native, pas une
    degradation : on verifie que le natif ne blesse PERSONNE non plus."""
    diag, off, live, off_hurt, live_hurt, ctx = _confront(rpc_, 1161, "tauBroadside")
    tgt_id = ctx["target"]["id"]
    print(f"\n[1161] caster={ctx['caster']} target={tgt_id} attacks={diag.get('attacks')} "
          f"marked={diag.get('marked')}\n       off={off}\n       live={live}")
    _dispose(rpc_, ctx)
    assert off == live, f"empreinte d'effets offline {off} != live {live}"
    assert off_hurt == live_hurt == set(), \
        f"degat au 1er cast (aucun ennemi marque) off={off_hurt} live={live_hurt}"
    assert MARKERLIGHT in (off.get(tgt_id) or {}), f"Markerlight non pose sur la cible: {off}"


def test_twin_smart_missile_system_marked_target_is_attacked_live(rpc_):
    """GENERALISATION 1161 (le coeur du patron « attaque filtree par un ETAT ») : APRES un 1er cast, la
    cible PORTE `Markerlight` -> un 2e cast doit la FRAPPER et RAFRAICHIR la duree (`ChangeEffectTurns`,
    `ChangeType.Add` = la duree restante AUGMENTE, elle n'est pas remise a plat).

    Non-circulaire : le 1er cast est joue LIVE (c'est le natif qui pose le marquage), l'etat est RECHARGE
    depuis le live, puis le 2e cast est confronte offline/live."""
    rid, err = _build(STATE_GEN, ["--p-mow", "tauBroadside"], board=GEN_BOARD)
    if rid is None:
        pytest.skip(f"build KO: {err}")
    dec = rpc_("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    m = next((x for x in (dec.get("mows") or []) if x.get("visualId") == "tauBroadside"), None)
    if m is None:
        rpc_("disposeRunner", {"runnerId": rid}, 20)
        pytest.skip("MoW tauBroadside non deployee")
    caster = m["casterId"]
    tgt, _n = _pick_unit_target(rpc_, rid, caster, 1161)
    if tgt is None or tgt["kind"] != "unit":
        rpc_("disposeRunner", {"runnerId": rid}, 20)
        pytest.skip("aucune cible unite legale pour 1161")
    act = _cast_live(rpc_, rid, caster, 1161, tgt)                 # 1er cast LIVE = pose du marquage
    if act.get("error"):
        rpc_("disposeRunner", {"runnerId": rid}, 20)
        pytest.skip(f"1er cast bloque: {act.get('error')}")
    # tours pour rendre l'ability re-castable (cooldown) : on s'arrete au 1er tour ou l'ability EST
    # re-castable ET le marquage TIENT ENCORE (au-dela, la duree de `Markerlight` expire et le scenario
    # discriminant disparait). Trace du deroule pour que le skip soit lisible.
    tgt2, trace = None, []
    for k in range(6):
        rpc_("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        cand, _n2 = _pick_unit_target(rpc_, rid, caster, 1161)
        dv = rpc_("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90) or {}
        still = [u.get("id") for u in (dv.get("units") or [])
                 if any(int(e.get("effectType") or -1) == MARKERLIGHT for e in (u.get("effects") or []))]
        trace.append((k, cand is not None, still))
        if cand is not None:
            tgt2 = cand
            break
    print(f"\n[1161 gen] deroule endturn -> (tour, castable, marques) = {trace}")
    if tgt2 is None:
        rpc_("disposeRunner", {"runnerId": rid}, 20)
        pytest.skip(f"1161 non re-castable en 6 tours -- 2e cast non couvert (trace={trace})")

    state, board, dec2, _ob = _load(rpc_, rid)
    marked = [uid for uid, effs in _offline_footprint(state).items()
              if MARKERLIGHT in effs and uid in {u.get("id") for u in (dec2.get("units") or [])}]
    if not marked:
        rpc_("disposeRunner", {"runnerId": rid}, 20)
        pytest.skip(f"le marquage n'a pas survecu jusqu'au 2e cast (trace={trace})")
    tid2 = tgt2["id"] if tgt2["kind"] == "unit" else board.id_at(tgt2["col"], tgt2["row"])
    hp_off_before = _hp_offline(state)
    rem_before = dict(_offline_footprint(state).get(marked[0]) or {})
    res = _apply_active_ability(state, caster, tid2, 1161)
    diag = (res or {}).get("diag") or {}
    off_hurt = _hurt(hp_off_before, _hp_offline(state))
    rem_after = dict(_offline_footprint(state).get(marked[0]) or {})

    hp_live_before = _hp_live(rpc_, rid)
    act2 = _cast_live(rpc_, rid, caster, 1161, tgt2)
    if act2.get("error"):
        rpc_("disposeRunner", {"runnerId": rid}, 20)
        pytest.skip(f"2e cast bloque: {act2.get('error')}")
    live_hurt = _hurt(hp_live_before, _hp_live(rpc_, rid))
    print(f"\n[1161 gen] marked={marked} attacks={diag.get('attacks')} refreshed={diag.get('refreshed')}\n"
          f"           off_hurt={off_hurt} live_hurt={live_hurt} rem {rem_before} -> {rem_after}")
    rpc_("disposeRunner", {"runnerId": rid}, 20)
    assert off_hurt == live_hurt, f"cibles frappees offline {off_hurt} != live {live_hurt}"
    assert set(marked) & off_hurt, "l'unite MARQUEE n'a pas ete frappee par le port"
    if tid2 == marked[0]:                       # la cible re-marquee = ChangeEffectTurns (Add)
        assert rem_after.get(MARKERLIGHT, 0) >= rem_before.get(MARKERLIGHT, 0), \
            f"ChangeEffectTurns(Add) n'a pas augmente la duree: {rem_before} -> {rem_after}"


def test_plagueburst_mortar_confront_live(rpc_):
    """1169 `IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$ExecuteBehaviour`.

    Le volet DEGAT/`Pinned` est filtre par le predicat armure-reduite/aura-Contagion (souvent VIDE sur un
    runner frais, comme le « 0 cible au spawn » d'EntropyCannons) ; le volet ZONE (`Contaminated` sur la
    cible + `nrOfTiles-1` tuiles adjacentes) est INCONDITIONNEL. On confronte les deux."""
    diag, off, live, off_hurt, live_hurt, ctx = _confront(rpc_, 1169, "deathCrawler")
    board, tile_id = ctx["board"], int(diag.get("tile"))
    contam_off = sorted(k for k, e in off.items() if CONTAMINATED in e)
    contam_live = sorted(k for k, e in live.items() if CONTAMINATED in e)
    print(f"\n[1169] caster={ctx['caster']} target={ctx['target']} tile={tile_id} "
          f"nrOfTiles={diag.get('nr_of_tiles')} attacks={diag.get('attacks')} pinned={diag.get('pinned')}\n"
          f"       contam off={contam_off} ({_coords(board, contam_off)})\n"
          f"       contam live={contam_live} ({_coords(board, contam_live)})")
    _dispose(rpc_, ctx)
    n = int(diag.get("nr_of_tiles") or 0)
    assert n > 0, "nrOfTiles non lu de la config"
    # CARDINAL : `1 + min(nrOfTiles - 1, |voisines|)` -- le natif tire `nrOfTiles-1` tuiles dans un pool
    # d'AU PLUS 6 voisines (moins au bord du plateau), le tirage ne peut pas depasser le pool.
    n_expected = 1 + min(n - 1, len(board.neighbours(tile_id)))
    assert len(contam_off) == len(contam_live) == n_expected, \
        f"cardinal Contaminated off={len(contam_off)} live={len(contam_live)} attendu {n_expected}"
    assert tile_id in contam_off and tile_id in contam_live, \
        "la TUILE ciblee n'est pas contaminee (1er terme de l'union native)"
    # les tuiles tirees sont TOUJOURS adjacentes a la tuile ciblee, des deux cotes
    adj = set(board.neighbours(tile_id))
    for k in contam_off + contam_live:
        assert k == tile_id or k in adj, f"tuile contaminee {k} hors du voisinage de la tuile ciblee"
    assert off_hurt == live_hurt, f"cibles frappees offline {off_hurt} != live {live_hurt}"
    # le PREDICAT filtre : degat <=> Pinned pose (les DEUX volets partagent le meme selecteur)
    pinned_off = {k for k, e in off.items() if PINNED in e}
    assert bool(pinned_off) == bool(off_hurt), \
        f"incoherence predicat : pinned={pinned_off} hurt={off_hurt} (meme selecteur natif)"


def test_plagueburst_mortar_center_zone_live(rpc_):
    """GENERALISATION 1169 : la meme zone castee sur une tuile CENTRALE (6 voisines) -- le cas COIN du
    test precedent n'exerce que 4 tuiles. Ici le pool couvre `nrOfTiles-1` exactement, donc l'ENSEMBLE
    contamine doit coincider offline/live SANS marge (le `PickRandomly` ne peut pas choisir)."""
    diag, off, live, off_hurt, live_hurt, ctx = _confront(rpc_, 1169, "deathCrawler",
                                                         state_path=STATE_GEN, board_id=GEN_BOARD,
                                                         prefer_center=True)
    board, tile_id = ctx["board"], int(diag.get("tile"))
    contam_off = sorted(k for k, e in off.items() if CONTAMINATED in e)
    contam_live = sorted(k for k, e in live.items() if CONTAMINATED in e)
    n = int(diag.get("nr_of_tiles") or 0)
    n_expected = 1 + min(n - 1, len(board.neighbours(tile_id)))
    print(f"\n[1169 centre] tile={tile_id} ({board.coord(tile_id)}) voisines={len(board.neighbours(tile_id))} "
          f"nrOfTiles={n} attendu={n_expected}\n"
          f"       contam off={contam_off} ({_coords(board, contam_off)})\n"
          f"       contam live={contam_live} ({_coords(board, contam_live)})")
    _dispose(rpc_, ctx)
    assert len(contam_off) == len(contam_live) == n_expected, \
        f"cardinal off={len(contam_off)} live={len(contam_live)} attendu {n_expected}"
    # pool NON sature (`nrOfTiles-1 >= |voisines|`) -> le tirage prend TOUT -> ensembles IDENTIQUES.
    if n - 1 >= len(board.neighbours(tile_id)):
        assert contam_off == contam_live, f"zone offline {contam_off} != live {contam_live}"


def test_forward_spotter_confront_live(rpc_):
    """1143 `IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardSpotterAbility$$ExecuteBehaviour` :
    template SPAWN. On confronte le NOMBRE de summons et leur VOISINAGE (adjacents a la cible) --
    la TUILE exacte reste un residu (`SortTilesByUtilityForSummon` = moteur d'utilite IA non porte)."""
    diag, off, live, off_hurt, live_hurt, ctx = _confront(rpc_, 1143, "astraOrdnanceBattery")
    board, tgt_id = ctx["board"], ctx["target"]["id"]
    spawned_off = list(diag.get("spawned") or [])
    new_live = ctx["unitsAfter"] - ctx["unitsBefore"]
    print(f"\n[1143] caster={ctx['caster']} target={tgt_id} tiles={diag.get('tiles')} "
          f"({_coords(board, diag.get('tiles') or [])})\n"
          f"       spawned_off={spawned_off} new_live={sorted(new_live)} count={diag.get('count')}")
    _dispose(rpc_, ctx)
    assert int(diag.get("count") or 0) > 0, "nrOfSummons non lu de la config"
    assert len(spawned_off) == len(new_live), \
        f"nb de summons offline {len(spawned_off)} != live {len(new_live)}"
    tpos = next((u.get("pos") for u in (ctx["dec"].get("units") or []) if u.get("id") == tgt_id), None)
    if tpos and spawned_off:
        adj = set(board.neighbours(board.id_at(tpos["col"], tpos["row"])))
        for t in (diag.get("tiles") or []):
            assert t in adj, f"tuile de spawn {t} non adjacente a la cible"


def test_daemonic_ordnance_confront_live(rpc_):
    """1148 `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$ExecuteBehaviour`.

    2-PHASES PAR CONSTRUCTION : l'attaque ne frappe que les ennemis DEJA sur une tuile en feu, et le feu
    est pose EN FIN du meme cast -> le 1er cast n'inflige rien et allume le triangle. On confronte le
    triangle enflamme (tuiles EXACTES) et l'absence de degat des deux cotes."""
    diag, off, live, off_hurt, live_hurt, ctx = _confront(rpc_, 1148, "blackForgefiend")
    board = ctx["board"]
    fire_off = sorted(k for k, e in off.items() if FIRE in e)
    fire_live = sorted(k for k, e in live.items() if FIRE in e)
    print(f"\n[1148] caster={ctx['caster']} target={ctx['target']} crit_dmg={diag.get('extra_crit_dmg')} "
          f"crit_chance={diag.get('extra_crit_chance')} attacks={diag.get('attacks')}\n"
          f"       fire off={fire_off} ({_coords(board, fire_off)})\n"
          f"       fire live={fire_live} ({_coords(board, fire_live)})")
    _dispose(rpc_, ctx)
    assert fire_off == fire_live, f"zone de feu offline {fire_off} != live {fire_live}"
    assert fire_off, "aucune tuile enflammee (GetTargetAreaTiles vide)"
    assert off_hurt == live_hurt == set(), \
        f"degat au 1er cast (aucune tuile encore en feu) off={off_hurt} live={live_hurt}"
    # le buff/debuff de CRIT_DAMAGE encadre l'attaque -> NET NUL apres le cast
    from engine.entities.stats import StatType
    from engine.runner.components import StatsComponent
    e = ctx["state"].get_entity(ctx["caster"])
    sc = e.get_component(StatsComponent) if e is not None else None
    us = getattr(sc.ctx, "stats", None) if sc is not None else None
    if us is not None:
        comp = us.components.get(int(StatType.CRIT_DAMAGE))
        if comp is not None:
            assert comp.modification.total == 0, \
                f"le buff extraCritDmg n'a pas ete reverte (net {comp.modification.total})"


def test_thrice_blessed_conflagration_confront_live(rpc_):
    """1187 `IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$ExecuteBehaviour`.

    La cible est un ALLIE (buff 1401 si Sisterhood, sinon 1436) ; le degat part sur la LIGNE CONTIGUE
    d'ennemis choisie par `SortByFormula(Count(GetTilesInLine))`. On confronte le buff (effectType + porteur)
    ET l'ensemble des unites frappees."""
    diag, off, live, off_hurt, live_hurt, ctx = _confront(rpc_, 1187, "adeptExorcist")
    tgt_id = ctx["target"]["id"] if ctx["target"]["kind"] == "unit" else None
    print(f"\n[1187] caster={ctx['caster']} target={ctx['target']} sisterhood={diag.get('sisterhood_target')} "
          f"rounds={diag.get('rounds')} turns={diag.get('duration_turns')} attacks={diag.get('attacks')}\n"
          f"       off={off}\n       live={live}\n       off_hurt={off_hurt} live_hurt={live_hurt}")
    _dispose(rpc_, ctx)
    assert off == live, f"empreinte d'effets offline {off} != live {live}"
    assert off_hurt == live_hurt, f"cibles frappees offline {off_hurt} != live {live_hurt}"
    if tgt_id is not None:
        posed = set((off.get(tgt_id) or {}))
        assert posed & {TBC_MELEE, TBC_RANGED}, f"aucun buff pose sur la cible: {off}"
        # la BRANCHE prise doit correspondre au verdict `HasFaction(target, Sisterhood)`
        expected = TBC_MELEE if diag.get("sisterhood_target") else TBC_RANGED
        assert expected in posed, f"branche HasFaction incoherente: attendu {expected}, pose {posed}"
