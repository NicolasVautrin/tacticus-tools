"""case-220 Necrons : MartialApotheosis (TriggeredAbilityType 1045, passif `necroOverlord`) FACE COMBAT.

RE (decompile gqfc5mff6c, cf. en-tete de `triggers/loki/martial_apotheosis.py`) : la classe native
`MartialApotheosisAbility` ETEND `DestroyerHiveAbility` -> CreateTrigger/GetValidTargets HERITES :
  IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$CreateTrigger = On(TurnStart_Actions=0x16) & OwnerIsActor(@0xa0) & AmountIsGreaterThanZero(
                             GetValidTargets)
  IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$GetValidTargets = Damageable(Enemies(AdjacentUnits(casterTile@0x148, radius=1)))   # anneau-1
  IdunBattleLogic.Entities.Abilities.Active.Loki.MartialApotheosisAbility$$CreateBehaviour = AttackWithAttackDamage(caster, PickRandomly(GetValidTargets, count=1),
                               MinMaxDamage(minDmg/maxDmg[level]), GetDamageProfile(0)="Energy"(pierce 30),
                               GetNumberConstant(0x2f)=nrOfHits=2)   # famille "attack", melee, level passif
= au debut de son tour, si >=1 ennemi adjacent damageable, en attaque UN au hasard, 2 coups Energy.

CE QUI EST VALIDE (le porteur necroOverlord EST SPAWNABLE, cf. test_thebetrayer) :
  (A) VECTEUR turn-start + OwnerIsActor : `start_turn_triggers(overlord_player)` dispatche MartialApotheosis
      (mirror StartTurnOperation `On(0x16)`) ; `start_turn_triggers(enemy_player)` ne le fire PAS.
  (B) AmountIsGreaterThanZero : 0 ennemi adjacent -> ne fire pas.
  (C) CIBLAGE ANNEAU-1 : un ennemi adjacent (dist 1) est cible ; un ennemi a dist 2 NE l'est PAS (anneau-1,
      PAS le disque rayon-2 de HarbingerOfDestruction).
  (D) A/B bit-exact + params : pool==1 (deterministe) -> l'arbre == une sequence directe
      `execute_ability_attack` depuis le MEME MT ; params confrontes a l'ORACLE CONFIG (cf. ci-dessous), melee.
  (E) LIVE replay-diff : on drive un ennemi adjacent a necroOverlord, `endturn` (flip -> son turn-start ->
      MartialApotheosis), et la cible frappee live == la cible offline (pool==1) + une attaque a lieu.
Le DEGAT exact live (calage RNG de la cascade turn-start `On(0x12..0x16)`) n'est PAS exige (== TheBetrayer) ;
la bit-exactness du DEGAT est prouvee PAR CONSTRUCTION en (D).

ORACLE DES PARAMS (#96 -- aucun scalaire de gameplay fige ici). Le decompile TRANCHE : le nb de coups et le
profil sont lus TELS QUELS dans la config d'ability par
`IdunBattleLogic.Entities.Abilities.Active.Loki.MartialApotheosisAbility$$CreateBehaviour`
(`GetNumberConstant(cfg, 0x2f)` et `GetDamageProfile(cfg, 0)` passes directement en arguments de
`IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` -- aucune formule),
et `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant` n'est qu'un
`GetStringConstant` + `System.Int32.Parse`. Ce sont donc des valeurs BRUTES -> l'oracle est la CONFIG :
`gameconfig.ability("MartialApotheosis").constants` (`nrOfHits`, `damageProfile`) et
`gameconfig.damage_profile(<profil>).PiercingRatio`. Cle non ambigue : enum `AbilityConstantType`
0x2f=nrOfHits(47) (cf. `engine/entities/formulas.py::ConfigConst`), distinct de 0x16=range(22).
RESIDU DE CONFRONTATION (mesure) : sur CE vecteur (turn-start), `applyAction endturn` + `captureEvents`
rend 1 action / 0 event -- aucun evenement per-coup n'est expose, le nb de coups LIVE n'est donc pas
observable ici (contrairement aux abilities castees : PlasmaCannon/SanctorumMissile/SentinelDirectives le
confrontent, eux). L'oracle config est confronte au PORT (nb de coups emis par l'arbre) ; le confronter au
NATIF demanderait un hook sur `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`.

Drive les positions (memoire « drive positions, don't blame geometry »). Etat LIVE, aucune RVA/tuile
hardcodee. State-file UNIQUE (chemin absolu + agent id). ASCII-only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import gameconfig as GC

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.abilities.base import ability_attack_params
from engine.runner.operations.triggers import start_turn_triggers
from engine.runner.operations.triggers.base import TriggerEvent
from engine.runner.operations.triggers.loki.martial_apotheosis import MartialApotheosisAttackAbility
from engine.dsl.event_trigger_type import EventTriggerType

AGENT_ID = "a2a29ebf31c1e4476"
PYDIR = Path(__file__).resolve().parents[3]                          # scripts/python
ROOT = Path(__file__).resolve().parents[5]                          # racine repo
STATE = ROOT / "data" / f"_pytest_martial_apotheosis_{AGENT_ID}.json"

CARRIER = "necroOverlord"                                           # porteur du passif MartialApotheosis
ENEMIES = "necroWarden,eldarRanger,eldarAutarch"                    # ennemis (team joueur), tanky + armure 0
HP = "500000"                                                       # --hp-player : survivent + armure 0 (per-coup net)


# ------------------------------------------------------------------ oracle CONFIG (cf. en-tete)

def _const(key):
    """Constante de config d'ability = `AbilityConfiguration.GetNumberConstant/GetStringConstant`
    (lecture BRUTE, aucune formule) -> ORACLE des params. None si la cle a disparu de la config."""
    return ((GC.ability("MartialApotheosis") or {}).get("constants") or {}).get(key)


# ------------------------------------------------------------------ helpers etat offline

def _find_by_vis(state, vis):
    from engine.runner.components import UnitComponent
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.alive and uc.visual_id == vis:
            return uid
    return None


def _owner(state, uid):
    from engine.runner.components import OwnerComponent
    e = state.get_entity(uid)
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.player if oc is not None else None


def _team(state, uid):
    from engine.runner.components import OwnerComponent
    e = state.get_entity(uid)
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _enemies_of(state, uid):
    from engine.runner.components import UnitComponent, OwnerComponent
    mine = _team(state, uid)
    out = []
    for oid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or oc is None or not uc.alive or oc.team == mine:
            continue
        out.append(oid)
    return sorted(out)


def _pos(state, uid):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _set_pos(state, uid, col, row):
    from engine.runner.components import PositionComponent
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is not None:
        pc.col, pc.row = int(col), int(row)


def _hp(state, uid):
    from engine.runner.components import HealthComponent
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _park_others(state, board, keep_ids, center):
    """Deplace toute unite VIVANTE hors `keep_ids` loin (dist hex > 4) du centre."""
    from engine.runner.components import UnitComponent
    used = set()
    far = sorted(t for t in board.by_id
                 if board.walkable(t) and hexgeo.distance(board.coord(t), center) > 4)
    it = iter(far)
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uid in keep_ids or uc is None or not uc.alive:
            continue
        for t in it:
            if t not in used:
                used.add(t); _set_pos(state, uid, *board.coord(t)); break


def _ring(board, center, dx):
    """Tuiles marchables a dist hex EXACTEMENT `dx` de `center`."""
    return [board.coord(t) for t in board.by_id
            if board.walkable(t) and hexgeo.distance(center, board.coord(t)) == dx]


# ------------------------------------------------------------------ fixture : etat LIVE rejouable

@pytest.fixture(scope="module")
def ma_env(host, live_session, request):
    """Runner LIVE (necroOverlord porteur + 3 ennemis) : rid pour le replay live + `build_state()`
    rejouable pour les drives offline. State-file UNIQUE (discipline runner) ; runner dispose au teardown."""
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "4321", "--state-file", str(STATE),
         "--board", "MC1_67", "--p-units", ENEMIES, "--a-units", CARRIER, "--hp-player", HP],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        pytest.skip(f"build runner KO (rl_duel): {(proc.stderr or proc.stdout or '')[-300:]}")
    rid = json.loads(STATE.read_text())["runnerId"]

    def _rpc(m, b, t=60):
        r = host._rpc(live_session, m, [b], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    request.addfinalizer(lambda: host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20))

    bg = _rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = _rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 90)
    ob = _rpc("observeBattle", {"runnerId": rid}, 40)
    snap = _rpc("combatSnapshot", {"runnerId": rid}, 60)
    rng0 = _rpc("dumpRng", {"runnerId": rid}, 30)

    def build_state():
        st = load_state(dv, ob, snap, board=board)
        if isinstance(rng0, dict) and rng0.get("mt"):
            st.rng = _seed_rng(rng0)
        return st

    if _find_by_vis(build_state(), CARRIER) is None:
        pytest.skip("porteur necroOverlord absent du build")
    return {"build_state": build_state, "board": board, "rid": rid, "rpc": _rpc}


# ------------------------------------------------------------------ (A) vecteur turn-start + OwnerIsActor

def test_ma_turnstart_dispatch_and_owner_gate(ma_env):
    """`start_turn_triggers(overlord_player)` dispatche MartialApotheosis (1 ennemi adjacent -> le frappe) ;
    `start_turn_triggers(enemy_player)` ne le fire PAS (OwnerIsActor @0xa0)."""
    state = ma_env["build_state"]()
    board = ma_env["board"]
    cid = _find_by_vis(state, CARRIER)
    ens = _enemies_of(state, cid)
    if cid is None or not ens:
        pytest.skip("porteur + 1 ennemi requis")
    C = next((board.coord(t) for t in sorted(board.by_id)
              if board.walkable(t) and len(_ring(board, board.coord(t), 1)) >= 1), None)
    if C is None:
        pytest.skip("aucune tuile a >=1 voisin")
    t_id = ens[0]
    _park_others(state, board, {cid, t_id}, C)
    _set_pos(state, cid, *C)
    _set_pos(state, t_id, *_ring(board, C, 1)[0])
    op = _owner(state, cid)
    ep = _owner(state, t_id)
    hp0 = _hp(state, t_id)

    # OwnerIsActor : au tour de l'ENNEMI (ep), MartialApotheosis ne fire pas.
    res_e = start_turn_triggers(state, ep)
    assert not any(r.get("ability") == "MartialApotheosis" for r in res_e), \
        f"MartialApotheosis a fire au tour ADVERSE (OwnerIsActor viole): {res_e}"
    assert _hp(state, t_id) == hp0, "cible endommagee au tour adverse (OwnerIsActor viole)"

    # au tour du PROPRIETAIRE (op) : fire + frappe la cible adjacente.
    res_o = start_turn_triggers(state, op)
    ma = next((r for r in res_o if r.get("ability") == "MartialApotheosis"), None)
    print(f"\n[MA A] owner_player={op} enemy_player={ep} target={ma.get('target') if ma else None} "
          f"total={(ma.get('attack') or {}).get('total') if ma else None}")
    assert ma is not None, f"MartialApotheosis non dispatche au turn-start du proprietaire: {res_o}"
    assert ma.get("target") == t_id, f"cible {ma.get('target')} != ennemi adjacent {t_id}"
    assert (ma.get("attack") or {}).get("total", 0) > 0, "aucune attaque"
    assert _hp(state, t_id) < hp0, "ennemi adjacent non endommage"
    print("[MA A] OK : On(TurnStart_Actions) & OwnerIsActor -> frappe l'ennemi adjacent ; muet au tour adverse")


# ------------------------------------------------------------------ (B) AmountIsGreaterThanZero (0 cible)

def test_ma_no_adjacent_no_fire(ma_env):
    """AmountIsGreaterThanZero(GetValidTargets) : aucun ennemi adjacent -> MartialApotheosis ne fire pas."""
    state = ma_env["build_state"]()
    board = ma_env["board"]
    cid = _find_by_vis(state, CARRIER)
    ens = _enemies_of(state, cid)
    if cid is None or not ens:
        pytest.skip("porteur + ennemis requis")
    # tuile isolee : porteur au centre, TOUS les ennemis parkes loin (dist > 4).
    C = next((board.coord(t) for t in sorted(board.by_id) if board.walkable(t)), None)
    _park_others(state, board, {cid}, C)
    _set_pos(state, cid, *C)
    op = _owner(state, cid)
    hp0 = {e: _hp(state, e) for e in ens}
    ab = MartialApotheosisAttackAbility(cid)
    ev = TriggerEvent(EventTriggerType.TurnStart_Actions, -1, -1, ranged=False, profile=None, player_id=op)
    assert ab.matches(state, ev) is False, "matches True sans ennemi adjacent (AmountIsGreaterThanZero viole)"
    res = start_turn_triggers(state, op)
    assert not any(r.get("ability") == "MartialApotheosis" for r in res), \
        f"MartialApotheosis a fire sans cible adjacente: {res}"
    for e in ens:
        assert _hp(state, e) == hp0[e], f"ennemi e{e} endommage sans adjacence"
    print("\n[MA B] OK : 0 ennemi adjacent -> pas de fire (AmountIsGreaterThanZero)")


# ------------------------------------------------------------------ (C) ciblage ANNEAU-1 (pas rayon-2)

def test_ma_ring1_not_radius2(ma_env):
    """CIBLAGE ANNEAU-1 : un ennemi a dist 1 est ciblable ; un ennemi a dist 2 ne l'est PAS (contraste
    HarbingerOfDestruction disque rayon-2). Pool == {dist1} -> pick deterministe -> dist2 jamais frappe."""
    state = ma_env["build_state"]()
    board = ma_env["board"]
    cid = _find_by_vis(state, CARRIER)
    ens = _enemies_of(state, cid)
    if cid is None or len(ens) < 2:
        pytest.skip("porteur + 2 ennemis requis")
    # C avec >=1 voisin dist1 ET >=1 tuile dist2.
    C = None
    for t in sorted(board.by_id):
        if not board.walkable(t):
            continue
        c = board.coord(t)
        if len(_ring(board, c, 1)) >= 1 and len(_ring(board, c, 2)) >= 1:
            C = c; break
    if C is None:
        pytest.skip("aucune tuile avec dist1 & dist2")
    near, far = ens[0], ens[1]
    _park_others(state, board, {cid, near, far}, C)
    _set_pos(state, cid, *C)
    occ = {C}
    d1 = [p for p in _ring(board, C, 1) if p not in occ]
    _set_pos(state, near, *d1[0]); occ.add(d1[0])
    d2 = [p for p in _ring(board, C, 2) if p not in occ]
    _set_pos(state, far, *d2[0]); occ.add(d2[0])
    assert hexgeo.distance(C, _pos(state, near)) == 1 and hexgeo.distance(C, _pos(state, far)) == 2
    op = _owner(state, cid)
    hp0 = {near: _hp(state, near), far: _hp(state, far)}
    res = start_turn_triggers(state, op)
    ma = next((r for r in res if r.get("ability") == "MartialApotheosis"), None)
    print(f"\n[MA C] near(d1)=e{near} far(d2)=e{far} target={ma.get('target') if ma else None}")
    assert ma is not None and ma.get("target") == near, \
        f"cible {ma.get('target') if ma else None} != ennemi ANNEAU-1 {near} (dist2 cible a tort ?)"
    assert _hp(state, near) < hp0[near], "ennemi anneau-1 non endommage"
    assert _hp(state, far) == hp0[far], f"ennemi a dist 2 (e{far}) endommage a tort -> rayon > 1 (pas anneau-1)"
    print("[MA C] OK : ciblage anneau-1 (dist1 frappe, dist2 exclu)")


# ------------------------------------------------------------------ (D) A/B bit-exact + params

def test_ma_ab_and_params(ma_env):
    """A/B : pool==1 (deterministe) -> l'arbre == une sequence directe `execute_ability_attack` depuis le
    MEME MT (bit-exact). Params confrontes a l'ORACLE CONFIG (cf. en-tete, aucun scalaire fige) : nb de
    coups == `constants.nrOfHits`, percage == `PiercingRatio` du profil `constants.damageProfile`, melee,
    chaque coup dans [bmin,bmax]."""
    from engine.runner.components import StatsComponent
    state = ma_env["build_state"]()
    board = ma_env["board"]
    cid = _find_by_vis(state, CARRIER)
    ens = _enemies_of(state, cid)
    if cid is None or not ens:
        pytest.skip("porteur + 1 ennemi requis")
    C = next((board.coord(t) for t in sorted(board.by_id)
              if board.walkable(t) and len(_ring(board, board.coord(t), 1)) >= 1), None)
    if C is None:
        pytest.skip("aucune tuile a >=1 voisin")
    t_id = ens[0]
    _park_others(state, board, {cid, t_id}, C)
    _set_pos(state, cid, *C)
    _set_pos(state, t_id, *_ring(board, C, 1)[0])
    op = _owner(state, cid)

    # ORACLE CONFIG : nb de coups + profil lus TELS QUELS dans la config (cf. en-tete).
    want_hits = _const("nrOfHits")
    prof = _const("damageProfile")
    assert want_hits is not None and prof is not None, (
        "oracle introuvable : gameconfig.ability('MartialApotheosis').constants sans nrOfHits/damageProfile "
        "-- le natif les lit par GetNumberConstant(0x2f)/GetDamageProfile(0), elles DOIVENT exister")
    want_hits = int(want_hits)
    dp = GC.damage_profile(prof) or {}
    assert dp.get("PiercingRatio") is not None, f"oracle introuvable : damageProfiles.{prof}.PiercingRatio"
    want_pierce = int(dp["PiercingRatio"])

    # params via le port (level_slot="passive"), profil pris de la config (== GetDamageProfile(0)).
    bmin, bmax, pierce, hits = ability_attack_params(state, cid, "MartialApotheosis", prof,
                                                     ranged=False, level_slot="passive")
    assert hits == want_hits, (
        f"nrOfHits lu {hits} != oracle config {want_hits} (constants.nrOfHits) -- le port ne lit pas la "
        f"CONSTANTE d'ability (0x2f) mais autre chose (variable per-niveau scalee ? mauvaise cle ?)")
    # le percage de l'attaque = PiercingRatio du PROFIL + ExtraPierce du caster ; ici le porteur n'en a
    # aucun -> l'identite isole l'oracle de profil. Si un patch lui en donnait, ce garde-fou le DIRAIT
    # au lieu de laisser l'assertion suivante rougir sans explication.
    _sc = state.get_entity(cid).get_component(StatsComponent)
    _xp = int(_sc.ctx.extra_pierce or 0) + int(_sc.ctx.extra_pierce_melee or 0)
    assert _xp == 0, (f"setup n'isole plus le PiercingRatio du profil : le porteur a ExtraPierce={_xp} "
                      f"-> l'oracle attendu devient PiercingRatio + {_xp}")
    assert pierce == want_pierce, (
        f"pierce {pierce} != oracle config {want_pierce} (damageProfiles.{prof}.PiercingRatio)")

    # snapshot MT AVANT le fire.
    rng_snap = {"mt": list(state.rng.mt), "mti": state.rng.mti} if state.rng is not None else None
    hp0 = _hp(state, t_id)
    ab = MartialApotheosisAttackAbility(cid)
    ev = TriggerEvent(EventTriggerType.TurnStart_Actions, -1, -1, ranged=False, profile=None, player_id=op)
    res = ab.execute_behaviour(state, ev)
    assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
    assert res.get("target") == t_id, f"cible {res.get('target')} != ennemi adjacent {t_id}"
    port_ph = (res.get("attack") or {}).get("per_hit")
    print(f"\n[MA D] [bmin,bmax]=[{bmin},{bmax}] pierce={pierce} hits={hits} port_per_hit={port_ph}")
    assert _hp(state, t_id) < hp0, "ennemi non endommage"

    # baseline : rejoue depuis le MEME MT une sequence directe execute_ability_attack (2 coups Energy).
    st2 = ma_env["build_state"]()   # #64 : build_state pose deja state.board (via load_state board=)
    if rng_snap is not None:
        r = IntBasedMersenneTwister(); r.mt = list(rng_snap["mt"]); r.mti = rng_snap["mti"]; st2.rng = r
    _park_others(st2, board, {cid, t_id}, C)
    _set_pos(st2, cid, *C)
    _set_pos(st2, t_id, *_pos(state, t_id))
    rr = AttackDamageOperation.execute_ability_attack(st2, cid, t_id, bmin, bmax, pierce, hits,
                                                      damage_profile=prof, is_melee=True)
    ref_ph = (rr or {}).get("per_hit")
    print(f"[MA D] ref_per_hit={ref_ph}")
    assert port_ph == ref_ph, f"A/B : arbre {port_ph} != baseline execute_ability_attack {ref_ph}"
    assert port_ph is not None and len(port_ph) == want_hits, \
        f"{len(port_ph or [])} coups emis par l'arbre != oracle config nrOfHits={want_hits}, per_hit={port_ph}"
    for v in port_ph:
        assert bmin <= v <= bmax, f"coup {v} hors plage config [{bmin},{bmax}]"
    print(f"[MA D] OK : A/B tree==baseline ({want_hits} coups {prof} pierce {want_pierce}, bit-exact), "
          f"params == oracle config")


# ------------------------------------------------------------------ (E) LIVE replay-diff turn-start

def test_ma_live_replay(ma_env):
    """LIVE : drive un ennemi adjacent a necroOverlord, `endturn` (flip -> son turn-start -> MartialApotheosis),
    la cible frappee live == la cible offline (pool==1) + une attaque a lieu. Degat exact hors scope (calage
    RNG turn-start, == TheBetrayer). Utilise le runner LIVE partage (pas de rebuild)."""
    rpc = ma_env["rpc"]
    board = ma_env["board"]
    rid = ma_env["rid"]

    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ov = next((u for u in (dec.get("units") or []) if u.get("visualId") == CARRIER), None)
    if ov is None:
        pytest.skip("necroOverlord absent")
    ov_player = ov.get("owner")
    p_player = dec.get("currentPlayer")
    if p_player == ov_player:
        pytest.skip("build demarre au tour du porteur (impossible d'endturn INTO son turn-start)")
    oid = ov["id"]
    ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
    om = {u.get("squadId"): u for u in (ob0.get("units") or [])}
    ovp = om.get(oid)
    # un ennemi du porteur (team courante) a driver adjacent.
    foe = next((u for u in (ob0.get("units") or [])
                if u.get("teamId") != ovp.get("teamId") and not u.get("isDead")), None)
    if ovp is None or foe is None:
        pytest.skip("porteur/ennemi absent live")
    otile = board.id_at(ovp.get("col"), ovp.get("row"))
    occupied = {board.id_at(u.get("col"), u.get("row")) for u in om.values()
                if u.get("col") is not None and not u.get("isDead")}
    free = [n for n in board.neighbours(otile) if n not in occupied]
    if not free:
        pytest.skip("aucun voisin libre du porteur")
    dcol, drow = board.coord(free[0])
    fid = foe.get("squadId")
    rpc("applyAction", {"runnerId": rid,
                        "action": {"kind": "move", "unitId": fid, "to": {"col": dcol, "row": drow}}}, 90)
    ob1 = rpc("observeBattle", {"runnerId": rid}, 60)
    fu = next((u for u in (ob1.get("units") or []) if u.get("squadId") == fid), None)
    if fu is None or board.id_at(fu.get("col"), fu.get("row")) not in set(board.neighbours(otile)):
        pytest.skip("ennemi pas adjacent apres move (dest occupee ?)")

    # capture S (tour joueur), rng.
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    hp_before = next((u.get("hp") for u in (ob.get("units") or []) if u.get("squadId") == fid), None)

    # LIVE : endturn -> porteur turn-start -> MartialApotheosis.
    # NB (mesure) : `applyAction endturn` + `captureEvents` rend 1 action / 0 event -- la cascade
    # turn-start n'expose AUCUN evenement per-coup. Le nb de coups de ce vecteur n'est donc PAS
    # confrontable live (cf. en-tete, residu) ; seul le HP delta l'est.
    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}, "captureEvents": True}, 90)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    hp_after = next((u.get("hp") for u in (ob2.get("units") or []) if u.get("squadId") == fid), None)
    live_dmg = (hp_before - hp_after) if (hp_before is not None and hp_after is not None) else None

    # OFFLINE : load_state(S) + seed rng + start_turn_triggers(porteur).
    state = load_state(dec, ob, snap, board=board)
    if isinstance(rng0, dict) and rng0.get("mt"):
        state.rng = _seed_rng(rng0)
    if state.get_entity(oid) is None or state.get_entity(fid) is None:
        pytest.skip("porteur/ennemi absent offline (snapshot incomplet)")
    res = start_turn_triggers(state, ov_player)
    ma = next((r for r in res if r.get("ability") == "MartialApotheosis"), None)
    off_target = ma.get("target") if ma else None
    off_total = (ma.get("attack") or {}).get("total") if ma else None
    print(f"\n[MA E] off target={off_target} total={off_total} | live target=e{fid} live_dmg={live_dmg} "
          f"{'BIT-EXACT' if off_total == live_dmg else '(degat diverge = calage RNG turn-start, hors scope)'}")

    assert ma is not None and off_target is not None, f"MartialApotheosis non tire offline: {res}"
    assert off_target == fid, f"cible offline {off_target} != ennemi drive adjacent {fid}"
    assert off_total is not None and off_total > 0, f"pas d'attaque offline (total={off_total})"
    assert live_dmg is not None and live_dmg > 0, f"live : ennemi pas touche au turn-start (live_dmg={live_dmg})"
    print("[MA E] OK : live turn-start -> MartialApotheosis frappe l'ennemi adjacent (cible offline==live)")
