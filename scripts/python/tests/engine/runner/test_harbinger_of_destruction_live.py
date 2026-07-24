"""case-220 §6.7 Necrons : HarbingerOfDestruction (1008, `necroPlasmancer`) FACE COMBAT.

`HarbingerOfDestructionAbility$$ExecuteBehaviour @1811e6750` (DECOMPILE, mirror 1:1 + callees
`GetAdditionalTargets @1811e6a40` / `GetEnemiesInRange @1811e6e50` / `GetTargetAmount @1811e6fa0`) =
    targets = If( AreEqual(caster@0x160, target@0x178),
                  GetAdditionalTargets,                            # then : caster==target (degenere)
                  op_Addition(target@0x178, GetAdditionalTargets) )  # else : cible + additionnels
    AttackWithAttackDamage(caster, targets, MinMaxDamage, Direct(GetDamageProfile(0)=DirectDamage),
                           Direct(GetNumberConstant(0x2f)=nrOfHits=1))                      # UN SEUL leaf
avec
    GetEnemiesInRange = PickRandomly( Damageable(Unobscured(caster, SurroundingEnemies(casterTile,
                        range=GetNumberConstant(0x16)=2) - target)), count = nrOfUnits(0x9a) - 1 )
i2/config : cible + N-1 ennemis RANDOM dans un DISQUE rayon-2 du CASTER (non obscurcis, damageable), 1 coup
MinMaxDamage profil "DirectDamage" (PiercingRatio 100). `native_factory="attack"` (@1811e6750 appelle
`DSLFactory.AttackWithAttackDamage @180de9fb0`, VERIFIE par les callees ; "DirectDamage" est le NOM DU
PROFIL, PAS l'effet direct-damage).

*** PORTEUR UNSPAWNABLE -> validation CASTER-AGNOSTIQUE (precedent PlasmaGrenade eldarSmnGuardian) ***
`necroPlasmancer` = `UNSPAWNABLE_FALLBACK` (rl_collect_batch.py : "only necroPlasmancer fails") ; les autres
porteurs (necroNpcPlasmancer / necroBoss*Plasmancer) sont hors pool arene ; un force-cast de 1008 sur un
caster non-porteur est un NO-OP (le natif ne resout pas une ability absente -- VERIFIE probe). AUCUN cast LIVE
reel de 1008 n'est donc possible. La config 1008 etant GLOBALE (lue par id d'ability, PAS par le slot du
caster), on valide CASTER-AGNOSTIQUE (== PlasmaGrenade summon-only) : l'execute_behaviour porte tourne avec un
caster SPAWNABLE (necroWarden), lisant le config global. Les PRIMITIVES du selecteur sont LIVE-VALIDEES par
des soeurs : le disque rayon-2 `SurroundingEnemies`+`Unobscured` par Gauntlets (test_gauntlets_combat_live,
case-220 P0), le caster-anchor + `Sub(Target)` + `PickRandomly` par BringerOfDespair (test_bringer_of_despair
_live). Ce que ces tests PROUVENT (drive les positions en zone FLAT ou Unobscured est passe-tout) :
  (1) CIBLAGE rayon-2 : cible + ennemis du CASTER a dist 1 ET 2 frappes ; ennemi a dist 3 NON frappe
      (frontiere rayon-2, PAS ring-1 comme les splash portes ; PAS un rayon-3).
  (2) CAP N-1 + exclude-target : pool > N-1 -> exactement N-1 additionnels (PickRandomly(N-1)) ; la cible
      MAIN n'est JAMAIS un additionnel (op_Subtraction Target()).
  (3) CASTER-ANCHOR : les additionnels sont dans le disque du CASTER, PAS de la cible (contraste
      PlasmaGrenade/Stikkbomb/Fragstorm cible-ancres).
  (4) FIDELITE A/B (bit-exact) : l'arbre == une sequence directe `execute_ability_attack` (cibles id-triees
      {cible} U additionnels, 1 coup chacun, meme rng seede) -> le port n'introduit AUCUN bug de degat.
  (5) PARAMS DEGAT : chaque coup dans la plage config-scalee [minDmg,maxDmg], profil DirectDamage pierce 100.

GAP CONNU (hors port, #215) : l'ordre/cout exact du tirage `PickRandomly` (pool > N-1) n'est pas cale ->
DETERMINISTE seulement quand `len(pool) <= N-1` (le pool tient, pas de tirage). Les tests de ciblage exact
(1)(5) drivent `len(pool) <= N-1` ; le cap (2) assert le COMPTE (N-1) sous pool > N-1, PAS quel ennemi precis.

Drive les positions (memoire « drive positions, don't blame geometry »). Lit l'etat LIVE, aucune RVA/tuile
hardcodee, seed = simple generateur. State-file UNIQUE (chemin absolu + agent id). ASCII-only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.abilities.base import ability_attack_params
from engine.runner.abilities.necrons import HarbingerOfDestructionAbility

AGENT_ID = "a53103b4b5d220e79"
PYDIR = Path(__file__).resolve().parents[3]                     # scripts/python
ROOT = Path(__file__).resolve().parents[5]                      # racine repo
STATE = ROOT / "data" / f"_pytest_harbinger_{AGENT_ID}.json"    # state-file UNIQUE (discipline runner)

CASTER = "necroWarden"                                          # caster SPAWNABLE (config 1008 caster-agnostique)
ENEMIES = "necroDestroyer,necroSpyder,necroOverlord,eldarRanger,eldarAutarch,orksNob"   # 6 cibles
HP = "500000"                                                  # ennemis armure 0 (per-coup bit-exact) + survivent


# ------------------------------------------------------------------ helpers etat offline

def _find_by_vis(state, vis):
    from engine.runner.components import UnitComponent
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.alive and uc.visual_id == vis:
            return uid
    return None


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
    """Deplace toute unite VIVANTE hors `keep_ids` sur une tuile marchable LOIN (dist hex > 4) du centre."""
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


def _ring(board, center, dx, same_elev=None, elev=None):
    """Tuiles marchables a dist hex EXACTEMENT `dx` de `center`. `same_elev` fixe -> filtre a cette
    elevation (Unobscured passe-tout : aucune crete entre le caster dist-2 et la cible). dist 1 : jamais
    obscurci (Unobscured passe quel que soit l'elevation) ; dist 3+ : hors disque (non concerne)."""
    out = []
    for t in board.by_id:
        c = board.coord(t)
        if not (board.walkable(t) and hexgeo.distance(center, c) == dx):
            continue
        if same_elev is not None and elev is not None and elev.get(c) != same_elev:
            continue
        out.append(c)
    return out


def _params(state, caster_id):
    """(N, range) via le port (mirror GetVariableForLevel(0x9a)=nrOfUnits / GetNumberConstant(0x16)=range)."""
    return HarbingerOfDestructionAbility()._params(state, caster_id)


# ------------------------------------------------------------------ fixture : etat LIVE rejouable

@pytest.fixture(scope="module")
def har_off(host, live_session, request):
    """Etat LIVE reel (necroWarden + 6 ennemis) charge offline, rejouable a volonte (drive offline).
    Build via state-file UNIQUE (discipline runner) ; runner dispose au teardown."""
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777", "--state-file", str(STATE),
         "--board", "MC1_67", "--p-units", CASTER, "--a-units", ENEMIES, "--hp-target", HP],
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
    board = Board(bg["tiles"], adjacency="native_sym")
    elev = {(t["col"], t["row"]): t.get("elevation") for t in bg["tiles"]}
    dv = _rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = _rpc("observeBattle", {"runnerId": rid}, 40)
    snap = _rpc("combatSnapshot", {"runnerId": rid}, 60)
    rng0 = _rpc("dumpRng", {"runnerId": rid}, 30)

    def build_state():
        st = load_state(dv, ob, snap)
        st.board = board
        if isinstance(rng0, dict) and rng0.get("mt"):
            st.rng = _seed_rng(rng0)
        return st

    if _find_by_vis(build_state(), CASTER) is None:
        pytest.skip("caster (necroWarden) absent du build")
    return {"build_state": build_state, "board": board, "elev": elev}


# ------------------------------------------------------------------ (0) ROUTAGE handler (entry point)

def test_harbinger_handler_routes_1008(har_off):
    """Le handler `AbilityHandler` (registry handler.py, seul fichier partage modifie) ROUTE 1008 vers
    `HarbingerOfDestructionAbility` (ported=True) via `Runner.apply(ActiveAbilityMessage)` = le vrai point
    d'entree (mirror natif). Place cible + 1 additionnel adjacent -> le cast frappe les deux."""
    state = har_off["build_state"]()
    board = har_off["board"]
    cid = _find_by_vis(state, CASTER)
    ens = _enemies_of(state, cid)
    if cid is None or len(ens) < 2:
        pytest.skip("caster + 2 ennemis requis")
    # C avec >=2 voisins dist1 (jamais obscurci) : cible + 1 additionnel
    C = next((board.coord(t) for t in sorted(board.by_id)
              if board.walkable(t) and len(_ring(board, board.coord(t), 1)) >= 2), None)
    if C is None:
        pytest.skip("aucune tuile a 2 voisins dist1")
    t_id, a_id = ens[0], ens[1]
    _park_others(state, board, {cid, t_id, a_id}, C)
    _set_pos(state, cid, *C)
    d1 = _ring(board, C, 1)
    _set_pos(state, t_id, *d1[0]); _set_pos(state, a_id, *d1[1])
    hp0 = {t_id: _hp(state, t_id), a_id: _hp(state, a_id)}
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=t_id, ability_type=1008))
    last = runner.ability_handler.last or {}
    print(f"\n[HAR route] last.ported={last.get('ported')} ability={last.get('ability')} "
          f"main={bool(last.get('main_attack'))} splash={[s['target'] for s in (last.get('splash') or [])]}")
    assert last.get("ported") is True, f"1008 non route par le handler (registry manquant?): {last}"
    assert last.get("ability") == "HarbingerOfDestruction"
    assert last.get("main_attack") is not None, "cible MAIN non attaquee via le handler"
    assert _hp(state, t_id) < hp0[t_id], "cible MAIN non endommagee via Runner.apply"
    assert _hp(state, a_id) < hp0[a_id], "additionnel adjacent non endommage via Runner.apply"
    print("[HAR route] OK : handler route 1008 -> HarbingerOfDestruction (ported), cast end-to-end")


# ------------------------------------------------------------------ (1) CIBLAGE rayon-2 + (4)(5) A/B/params

def test_harbinger_radius2_targeting_and_ab(har_off):
    """CIBLAGE rayon-2 (cible + ennemis dist 1&2 du CASTER frappes ; dist 3 NON) + A/B bit-exact + params.
    Drive `len(pool) <= N-1` -> pick DETERMINISTE (aucun tirage) -> ciblage EXACT + per-coup bit-exact."""
    state = har_off["build_state"]()
    board, elev = har_off["board"], har_off["elev"]
    cid = _find_by_vis(state, CASTER)
    ens = _enemies_of(state, cid)
    if cid is None or len(ens) < 4:
        pytest.skip("caster + 4 ennemis requis")
    n_total, rng_range = _params(state, cid)
    assert rng_range == 2, f"range config attendu 2 (rayon-2), lu {rng_range}"
    n_pick = max(0, n_total - 1)
    if n_pick < 2:
        pytest.skip(f"N={n_total} -> besoin de n_pick>=2 pour le discriminant d1/d2")

    # geometrie FLAT : C avec >=2 tuiles dist1, >=1 dist2 (meme elev -> Unobscured passe), >=1 dist3.
    # On place 2 additionnels (d1+d2, pool=2 <= n_pick -> DETERMINISTE) + cible (d1) + far (d3).
    C = None
    for t in sorted(board.by_id):
        if not board.walkable(t):
            continue
        c = board.coord(t); ec = elev.get(c)
        if (len(_ring(board, c, 1)) >= 2 and len(_ring(board, c, 2, ec, elev)) >= 1
                and len(_ring(board, c, 3)) >= 1):
            C = c; break
    if C is None:
        pytest.skip("aucune tuile caster flat avec dist 1(x2)&2&3 disponibles")
    ec = elev.get(C)
    t_id, a1_id, a2_id, far_id = ens[0], ens[1], ens[2], ens[3]
    _park_others(state, board, {cid, t_id, a1_id, a2_id, far_id}, C)
    _set_pos(state, cid, *C)
    occ = {C}
    d1 = [p for p in _ring(board, C, 1) if p not in occ]
    _set_pos(state, t_id, *d1[0]); occ.add(d1[0])            # cible a dist 1
    _set_pos(state, a1_id, *d1[1]); occ.add(d1[1])           # additionnel 1 a dist 1
    d2 = [p for p in _ring(board, C, 2, ec, elev) if p not in occ]
    _set_pos(state, a2_id, *d2[0]); occ.add(d2[0])           # additionnel 2 a dist 2 (flat -> Unobscured passe)
    d3 = [p for p in _ring(board, C, 3) if p not in occ]
    _set_pos(state, far_id, *d3[0]); occ.add(d3[0])          # far a dist 3 (hors disque rayon-2)

    dist = {i: hexgeo.distance(C, _pos(state, i)) for i in (t_id, a1_id, a2_id, far_id)}
    assert dist[a1_id] == 1 and dist[a2_id] == 2 and dist[far_id] == 3, f"geometrie inattendue: {dist}"
    expect_hit = {t_id, a1_id, a2_id}
    pos_snap = {i: _pos(state, i) for i in (cid, t_id, a1_id, a2_id, far_id)}
    print(f"\n[HAR r2] C={C} N={n_total} n_pick={n_pick} cible=e{t_id}(d1) add=e{a1_id}(d1),e{a2_id}(d2) "
          f"far=e{far_id}(d3)")

    rng_snap = {"mt": list(state.rng.mt), "mti": state.rng.mti} if state.rng is not None else None
    hp0 = {i: _hp(state, i) for i in (t_id, a1_id, a2_id, far_id)}
    res = HarbingerOfDestructionAbility().execute_behaviour(state, cid, t_id)
    assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
    main = res.get("main_attack") or {}
    splash = res.get("splash") or []
    hit = {t_id} | {s["target"] for s in splash}
    print(f"[HAR r2] hit={sorted(hit)} attendu={sorted(expect_hit)}")

    # (1) CIBLAGE : cible + additionnels dist<=2 frappes ; far (dist3) NON frappe (frontiere rayon-2)
    assert hit == expect_hit, f"cibles frappees {sorted(hit)} != attendu {sorted(expect_hit)}"
    assert far_id not in hit, f"ennemi a dist 3 (e{far_id}) frappe a tort -> rayon > 2"
    assert _hp(state, far_id) == hp0[far_id], f"far e{far_id} endommage a tort (rayon > 2)"
    assert _hp(state, t_id) < hp0[t_id], "cible MAIN non endommagee"
    for aid in (a1_id, a2_id):
        assert _hp(state, aid) < hp0[aid], f"additionnel e{aid} (dist {dist[aid]}) non endommage"

    # (4) FIDELITE A/B : rejoue depuis le MEME MT une sequence directe execute_ability_attack sur les cibles
    #     id-triees {cible} U additionnels (1 coup chacun) -> l'arbre == la baseline (bit-exact).
    st2 = har_off["build_state"]()
    st2.board = board
    if rng_snap is not None:
        r = IntBasedMersenneTwister(); r.mt = list(rng_snap["mt"]); r.mti = rng_snap["mti"]; st2.rng = r
    _park_others(st2, board, {cid, t_id, a1_id, a2_id, far_id}, C)
    for i, p in pos_snap.items():
        _set_pos(st2, i, *p)
    bmin, bmax, pierce, hits = ability_attack_params(st2, cid, "HarbingerOfDestruction", "DirectDamage",
                                                     ranged=True)
    ref_ph = {}
    for tid in sorted(expect_hit):                          # ordre id (== multi=True du leaf)
        rr = AttackDamageOperation.execute_ability_attack(st2, cid, tid, bmin, bmax, pierce, hits,
                                                          damage_profile="DirectDamage", is_melee=False)
        ref_ph[tid] = (rr or {}).get("per_hit")
    port_ph = {t_id: main.get("per_hit")}
    for s in splash:
        port_ph[s["target"]] = (s["attack"] or {}).get("per_hit")
    print(f"[HAR r2] params [bmin,bmax]=[{bmin},{bmax}] pierce={pierce} hits={hits}")
    for tid in sorted(expect_hit):
        print(f"[HAR r2]  e{tid} port_ph={port_ph.get(tid)} ref_ph={ref_ph.get(tid)}")
        assert port_ph.get(tid) == ref_ph.get(tid), (
            f"A/B e{tid}: arbre {port_ph.get(tid)} != baseline execute_ability_attack {ref_ph.get(tid)}")
    # (5) params : nrOfHits=1, pierce=100 (profil DirectDamage), chaque coup dans [bmin,bmax]
    assert hits == 1, f"nrOfHits attendu 1, lu {hits}"
    assert pierce == 100, f"pierce attendu 100 (profil DirectDamage), lu {pierce}"
    for tid in sorted(expect_hit):
        for v in (port_ph.get(tid) or []):
            assert bmin <= v <= bmax, f"coup e{tid} {v} hors plage config [{bmin},{bmax}]"
    print("[HAR r2] OK : ciblage rayon-2 (dist1&2 frappes, dist3 exclu), A/B tree==baseline, params DirectDamage")


# ------------------------------------------------------------------ (2) CAP N-1 + exclude-target

def _set_ability_level(state, caster_id, level):
    """Override offline du `active_ability_level` du caster (mirror d'un Plasmancer a un autre niveau : N =
    nrOfUnits[level] est config-driven, 3 aux niveaux bas / 5 au niveau 50). Legitime (config REELLE) : borne
    le nombre d'additionnels pour rendre le CAP demontrable avec le nb d'ennemis spawnables (5 sur MC1_67)."""
    from engine.runner.components import StatsComponent
    e = state.get_entity(caster_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is not None and sc.ctx is not None:
        sc.ctx.active_ability_level = int(level)


def test_harbinger_cap_and_excludes_target(har_off):
    """CAP : pool (ennemis disque rayon-2 - cible) > N-1 -> exactement N-1 additionnels (PickRandomly(N-1)) ;
    la cible MAIN n'est JAMAIS un additionnel (op_Subtraction Target()). MC1_67 ne spawne que 5 ennemis ; on
    borne N=3 (niveau bas REEL : nrOfUnits[idx<=16]=3 -> n_pick=2) pour que pool=3 > n_pick=2 -> le cap mord."""
    state = har_off["build_state"]()
    board, elev = har_off["board"], har_off["elev"]
    cid = _find_by_vis(state, CASTER)
    ens = _enemies_of(state, cid)
    if cid is not None:
        _set_ability_level(state, cid, 1)                   # niveau bas REEL -> N=3 (nrOfUnits[idx 0])
    n_total, _ = _params(state, cid)
    n_pick = max(0, n_total - 1)
    need_disk = n_pick + 1                                   # ennemis dans le disque (hors cible) -> pool > n_pick
    if cid is None or n_pick < 1 or len(ens) < need_disk + 1:
        pytest.skip(f"besoin de N>=2 et {need_disk + 1} ennemis (cible + {need_disk} disque) ; N={n_total}, {len(ens)} dispo")
    # C avec assez de voisins dist1 (jamais obscurci) pour cible + need_disk ; complement dist2 flat si besoin.
    C = None
    for t in sorted(board.by_id):
        if not board.walkable(t):
            continue
        c = board.coord(t); ec = elev.get(c)
        d1n = len(_ring(board, c, 1)); d2n = len(_ring(board, c, 2, ec, elev))
        if d1n + d2n >= need_disk + 1:                       # cible + need_disk cibles placables dans le disque
            C = c; break
    if C is None:
        pytest.skip("aucune tuile caster avec assez de tuiles disque (dist1+dist2 flat)")
    ec = elev.get(C)
    everyone = ens[:need_disk + 1]                           # cible + need_disk = pool > n_pick
    t_id = everyone[0]; pool_ids = everyone[1:]
    _park_others(state, board, set(everyone) | {cid}, C)
    _set_pos(state, cid, *C)
    occ = {C}
    slots = [p for p in _ring(board, C, 1) if p not in occ] + [p for p in _ring(board, C, 2, ec, elev) if p not in occ]
    if len(slots) < len(everyone):
        pytest.skip("pas assez de tuiles disque placables (Unobscured)")
    for uid, p in zip(everyone, slots):
        _set_pos(state, uid, *p); occ.add(p)
    dist = {i: hexgeo.distance(C, _pos(state, i)) for i in everyone}
    assert all(dist[i] <= 2 for i in everyone), f"toutes les cibles doivent etre dans le disque : {dist}"

    hp0 = {i: _hp(state, i) for i in everyone}
    res = HarbingerOfDestructionAbility().execute_behaviour(state, cid, t_id)
    splash = res.get("splash") or []
    add_hit = [s["target"] for s in splash]
    print(f"\n[HAR cap] C={C} N={n_total} n_pick={n_pick} pool={pool_ids}(size {len(pool_ids)}) add_hit={sorted(add_hit)}")
    # cap : exactement n_pick additionnels, tous dans le pool (jamais la cible)
    assert len(add_hit) == n_pick, f"cap viole : {len(add_hit)} additionnels != n_pick={n_pick}"
    assert t_id not in add_hit, "la cible MAIN ne doit JAMAIS etre un additionnel (op_Subtraction Target())"
    for aid in add_hit:
        assert aid in pool_ids, f"additionnel e{aid} hors pool {pool_ids}"
    not_picked = [i for i in pool_ids if i not in add_hit]
    for i in not_picked:
        assert _hp(state, i) == hp0[i], f"ennemi non-picke e{i} touche a tort (cap viole)"
    assert _hp(state, t_id) < hp0[t_id], "cible MAIN non endommagee"
    print(f"[HAR cap] OK : {len(add_hit)}/{len(pool_ids)} pickes (cap N-1={n_pick}), cible exclue du pool")


# ------------------------------------------------------------------ (3) CASTER-ANCHOR (pas cible-anchor)

def test_harbinger_additional_anchored_on_caster(har_off):
    """DISCRIMINANT : les additionnels sont dans le disque du CASTER, PAS de la cible seule. Place un ennemi
    D adjacent a la CIBLE mais a dist > 2 du CASTER -> il ne doit PAS etre frappe (refute cible-anchor)."""
    state = har_off["build_state"]()
    board, elev = har_off["board"], har_off["elev"]
    cid = _find_by_vis(state, CASTER)
    ens = _enemies_of(state, cid)
    if cid is None or len(ens) < 3:
        pytest.skip("caster + 3 ennemis requis")
    coords = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]
    # geometrie : C ; T a dist 2 du caster (flat) ; A a dist 1 du caster (additionnel) ; D adjacent a T mais
    # dist>2 de C (meme elev) -> D est adjacent a la CIBLE (splash cible-anchor le frapperait) mais HORS disque.
    geom = None
    for t in sorted(board.by_id):
        if not board.walkable(t):
            continue
        C = board.coord(t); ec = elev.get(C)
        d2 = _ring(board, C, 2, ec, elev); d1 = _ring(board, C, 1)
        if not d2 or not d1:
            continue
        for T in d2:
            Dc = [p for p in coords if hexgeo.distance(T, p) == 1 and elev.get(p) == ec
                  and hexgeo.distance(C, p) > 2 and p != C]
            Ac = [p for p in d1 if p != T and hexgeo.distance(T, p) != 1]   # A pas adjacent a T (isole)
            if Dc and Ac:
                geom = (C, T, Ac[0], Dc[0]); break
        if geom:
            break
    if geom is None:
        pytest.skip("aucune geometrie caster-anchor discriminante (flat)")
    C, T, A, D = geom
    t_id, a_id, d_id = ens[0], ens[1], ens[2]
    _park_others(state, board, {cid, t_id, a_id, d_id}, C)
    _set_pos(state, cid, *C); _set_pos(state, t_id, *T); _set_pos(state, a_id, *A); _set_pos(state, d_id, *D)
    dC = {i: hexgeo.distance(C, _pos(state, i)) for i in (t_id, a_id, d_id)}
    dT = hexgeo.distance(T, D)
    print(f"\n[HAR anchor] C={C} T={T}(e{t_id},dC={dC[t_id]}) A={A}(e{a_id},dC={dC[a_id]}) "
          f"D={D}(e{d_id},dC={dC[d_id]},dT={dT})")
    assert dC[d_id] > 2 and dT == 1, f"D doit etre adjacent a la CIBLE (dT={dT}) mais hors disque caster (dC={dC[d_id]})"

    hp0 = {i: _hp(state, i) for i in (t_id, a_id, d_id)}
    res = HarbingerOfDestructionAbility().execute_behaviour(state, cid, t_id)
    hit = {t_id} | {s["target"] for s in (res.get("splash") or [])}
    print(f"[HAR anchor] hit={sorted(hit)}")
    assert a_id in hit, f"A e{a_id} (dist {dC[a_id]} du caster) devrait etre frappe (additionnel caster-anchor)"
    assert d_id not in hit, f"D e{d_id} (adjacent cible mais dist {dC[d_id]} du caster) frappe a tort -> cible-anchor"
    assert _hp(state, d_id) == hp0[d_id], f"D e{d_id} endommage a tort (ciblage cible-anchor)"
    assert _hp(state, a_id) < hp0[a_id], f"A e{a_id} (disque caster) non endommage"
    print("[HAR anchor] OK : additionnels ancres sur le CASTER (disque rayon-2), pas sur la cible")
