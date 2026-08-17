"""case-220 §6.7 Necrons : HarbingerOfDestruction (1008, `necroPlasmancer`) FACE COMBAT.

`HarbingerOfDestructionAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$ExecuteBehaviour` (DECOMPILE, mirror 1:1 + callees
`IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$GetAdditionalTargets` / `IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$GetEnemiesInRange` / `IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$GetTargetAmount`) =
    targets = If( AreEqual(caster@0x160, target@0x178),
                  GetAdditionalTargets,                            # then : caster==target (degenere)
                  op_Addition(target@0x178, GetAdditionalTargets) )  # else : cible + additionnels
    AttackWithAttackDamage(caster, targets, MinMaxDamage, Direct(GetDamageProfile(0)=DirectDamage),
                           Direct(GetNumberConstant(0x2f)=nrOfHits=1))                      # UN SEUL leaf
avec
    GetEnemiesInRange = PickRandomly( Damageable(Unobscured(caster, SurroundingEnemies(casterTile,
                        range=GetNumberConstant(0x16)=2) - target)), count = nrOfUnits(0x9a) - 1 )
i2/config : cible + N-1 ennemis RANDOM dans un DISQUE rayon-2 du CASTER (non obscurcis, damageable), 1 coup
MinMaxDamage profil "DirectDamage" (PiercingRatio 100). `native_factory="attack"` (IdunBattleLogic.Entities.Abilities.Active.Loki.HarbingerOfDestructionAbility$$ExecuteBehaviour appelle
`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`, VERIFIE par les callees ; "DirectDamage" est le NOM DU
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
  (5) PARAMS DEGAT : chaque coup dans la plage config-scalee [minDmg,maxDmg] ; nb de coups et percage lus
      de la CONFIG (cf. ORACLE).

ORACLE (#96) -- AUCUN scalaire de gameplay n'est fige dans ce fichier. Le decompile tranche brut/calcule :
`HarbingerOfDestructionAbility$$ExecuteBehaviour` passe `Direct(GetDamageProfile(config, 0))` et
`Direct(GetNumberConstant(config, 0x2f))` TELS QUELS a `AttackWithAttackDamage`, et
`$$GetAdditionalTargets` passe `GetNumberConstant(config, 0x16)` tel quel a `GetEnemiesInRange` -> ces
trois-la sont BRUTS, leur oracle est la config : `constants.nrOfHits` (0x2f), `constants.range` (0x16),
`damageProfiles[constants.damageProfile].PiercingRatio` (indices resolus sur
`IdunBattle.Configuration.AbilityConstantType`). N (`nrOfUnits`, 0x9a) est deja lu par niveau via le port.
Le degat, lui, est CALCULE : il est confronte a une sequence directe re-jouee sous le MEME rng (volet 4),
jamais a un nombre ecrit a la main.
NB : le port FIGE le nom de profil "DirectDamage" (mirror du decompile) la ou le natif le LIT en config ;
le test lit la cle de config -> si un patch changeait `constants.damageProfile`, le test deviendrait rouge,
et il aurait raison (c'est le port qui aurait diverge du natif).

GAP CONNU (hors port, #215) : l'ordre/cout exact du tirage `PickRandomly` (pool > N-1) n'est pas cale ->
DETERMINISTE seulement quand `len(pool) <= N-1` (le pool tient, pas de tirage). Les tests de ciblage exact
(1)(5) drivent `len(pool) <= N-1` ; le cap (2) assert le COMPTE (N-1) sous pool > N-1, PAS quel ennemi precis.

Drive les positions (memoire « drive positions, don't blame geometry »). Lit l'etat LIVE, aucune RVA/tuile
hardcodee, seed = simple generateur. State-file UNIQUE (chemin absolu + agent id). ASCII-only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _config_oracle import (assert_ability_damage_profile,     # noqa: E402
                            damage_profile_pierce)

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
STATE = ROOT / "logs" / "runners" / f"_pytest_harbinger_{AGENT_ID}.json"   # SORTIE -> logs/ (#349)

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


def _cfg_constants() -> dict:
    """ORACLE des scalaires BRUTS de l'ability = `constants` de gameconfig (cf. en-tete). Le decompile passe
    `GetNumberConstant(0x2f)`/`(0x16)` et `GetDamageProfile(0)` TELS QUELS aux noeuds DSL : aucune formule
    entre la config et le noeud, donc l'attendu du test se LIT dans la config au lieu d'etre ecrit en dur."""
    import gameconfig as GC
    cst = (GC.ability("HarbingerOfDestruction") or {}).get("constants") or {}
    assert cst.get("nrOfHits") is not None and cst.get("range") is not None and cst.get("damageProfile"), \
        f"oracle introuvable : constants nrOfHits/range/damageProfile de HarbingerOfDestruction (lu: {cst})"
    return cst


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
        st = load_state(dv, ob, snap, board=board)
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
    """CIBLAGE rayon-`range` (cible + ennemis dist 1 et dist `range` du CASTER frappes ; dist `range`+1 NON)
    + A/B bit-exact + params. Drive `len(pool) <= N-1` -> pick DETERMINISTE (aucun tirage) -> ciblage EXACT
    + per-coup bit-exact.

    `range` n'est PAS ecrit en dur : il est lu dans `constants.range` (oracle config, cf. en-tete) et pilote
    la GEOMETRIE du scenario -- la frontiere testee est toujours `range` vs `range+1`, ou que la config le
    place. La 1re assertion confronte la valeur que le PORT a lue a cet oracle."""
    state = har_off["build_state"]()
    board, elev = har_off["board"], har_off["elev"]
    cid = _find_by_vis(state, CASTER)
    ens = _enemies_of(state, cid)
    if cid is None or len(ens) < 4:
        pytest.skip("caster + 4 ennemis requis")
    cst = _cfg_constants()
    cfg_range = int(cst["range"])
    n_total, rng_range = _params(state, cid)
    assert rng_range == cfg_range, \
        f"range lu par le port {rng_range} != constants.range={cfg_range} (oracle gameconfig, 0x16)"
    n_pick = max(0, n_total - 1)
    if n_pick < 2:
        pytest.skip(f"N={n_total} -> besoin de n_pick>=2 pour le discriminant d1/d{rng_range}")
    if rng_range < 2:
        pytest.skip(f"range={rng_range} -> le discriminant dist1/dist-range exige range>=2")

    # geometrie FLAT : C avec >=2 tuiles dist1, >=1 a dist `range` (meme elev -> Unobscured passe), >=1 a
    # dist `range`+1. On place 2 additionnels (d1 + d`range`, pool=2 <= n_pick -> DETERMINISTE) + cible (d1)
    # + far (d`range`+1, PREMIERE distance hors du disque).
    C = None
    for t in sorted(board.by_id):
        if not board.walkable(t):
            continue
        c = board.coord(t); ec = elev.get(c)
        if (len(_ring(board, c, 1)) >= 2 and len(_ring(board, c, rng_range, ec, elev)) >= 1
                and len(_ring(board, c, rng_range + 1)) >= 1):
            C = c; break
    if C is None:
        pytest.skip(f"aucune tuile caster flat avec dist 1(x2)&{rng_range}&{rng_range + 1} disponibles")
    ec = elev.get(C)
    t_id, a1_id, a2_id, far_id = ens[0], ens[1], ens[2], ens[3]
    _park_others(state, board, {cid, t_id, a1_id, a2_id, far_id}, C)
    _set_pos(state, cid, *C)
    occ = {C}
    d1 = [p for p in _ring(board, C, 1) if p not in occ]
    _set_pos(state, t_id, *d1[0]); occ.add(d1[0])            # cible a dist 1
    _set_pos(state, a1_id, *d1[1]); occ.add(d1[1])           # additionnel 1 a dist 1
    d2 = [p for p in _ring(board, C, rng_range, ec, elev) if p not in occ]
    _set_pos(state, a2_id, *d2[0]); occ.add(d2[0])           # additionnel 2 au BORD du disque (flat -> Unobscured passe)
    d3 = [p for p in _ring(board, C, rng_range + 1) if p not in occ]
    _set_pos(state, far_id, *d3[0]); occ.add(d3[0])          # far juste HORS du disque rayon-`range`

    dist = {i: hexgeo.distance(C, _pos(state, i)) for i in (t_id, a1_id, a2_id, far_id)}
    assert dist[a1_id] == 1 and dist[a2_id] == rng_range and dist[far_id] == rng_range + 1, \
        f"geometrie inattendue: {dist} (range={rng_range})"
    expect_hit = {t_id, a1_id, a2_id}
    pos_snap = {i: _pos(state, i) for i in (cid, t_id, a1_id, a2_id, far_id)}
    print(f"\n[HAR r{rng_range}] C={C} N={n_total} n_pick={n_pick} cible=e{t_id}(d1) "
          f"add=e{a1_id}(d1),e{a2_id}(d{rng_range}) far=e{far_id}(d{rng_range + 1})")

    rng_snap = {"mt": list(state.rng.mt), "mti": state.rng.mti} if state.rng is not None else None
    hp0 = {i: _hp(state, i) for i in (t_id, a1_id, a2_id, far_id)}
    res = HarbingerOfDestructionAbility().execute_behaviour(state, cid, t_id)
    assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
    main = res.get("main_attack") or {}
    splash = res.get("splash") or []
    hit = {t_id} | {s["target"] for s in splash}
    print(f"[HAR r{rng_range}] hit={sorted(hit)} attendu={sorted(expect_hit)}")

    # (1) CIBLAGE : cible + additionnels dist<=range frappes ; far (dist range+1) NON frappe (frontiere)
    assert hit == expect_hit, f"cibles frappees {sorted(hit)} != attendu {sorted(expect_hit)}"
    assert far_id not in hit, \
        f"ennemi a dist {rng_range + 1} (e{far_id}) frappe a tort -> rayon > constants.range={rng_range}"
    assert _hp(state, far_id) == hp0[far_id], \
        f"far e{far_id} endommage a tort (rayon > constants.range={rng_range})"
    assert _hp(state, t_id) < hp0[t_id], "cible MAIN non endommagee"
    for aid in (a1_id, a2_id):
        assert _hp(state, aid) < hp0[aid], f"additionnel e{aid} (dist {dist[aid]}) non endommage"

    # (4) FIDELITE A/B : rejoue depuis le MEME MT une sequence directe execute_ability_attack sur les cibles
    #     id-triees {cible} U additionnels (1 coup chacun) -> l'arbre == la baseline (bit-exact).
    st2 = har_off["build_state"]()   # #64 : build_state pose deja state.board (via load_state board=)
    if rng_snap is not None:
        r = IntBasedMersenneTwister(); r.mt = list(rng_snap["mt"]); r.mti = rng_snap["mti"]; st2.rng = r
    _park_others(st2, board, {cid, t_id, a1_id, a2_id, far_id}, C)
    for i, p in pos_snap.items():
        _set_pos(st2, i, *p)
    # Le profil de la baseline est LU en config (`GetDamageProfile(config, 0)`), pas ecrit en dur : la
    # sequence de reference emprunte donc exactement le profil que le natif emprunterait.
    cfg_profile = str(cst["damageProfile"])
    bmin, bmax, pierce, hits = ability_attack_params(st2, cid, "HarbingerOfDestruction", cfg_profile,
                                                     ranged=True)
    # Le `PickRandomly(pool, N-1)` natif precede TOUS les coups (il resout le selecteur d'additionnels)
    # et consomme `min(len(pool), N-1)` tirages, bornes decroissantes -- MEME quand le pool tient dans
    # N-1 (#130 : `PickRandomAmountSelector$$Select` n'a aucun court-circuit). Le setup ne laisse dans le
    # rayon que a1/a2 (far est a range+1) -> pool = les ennemis a dist <= range, cible exclue.
    pool_ids = sorted(i for i in (a1_id, a2_id, far_id) if dist[i] <= rng_range)
    n_draw = len(splash)                                     # == min(len(pool), N-1), lu du port
    assert n_draw == min(len(pool_ids), n_draw), f"pick {n_draw} > pool {len(pool_ids)} (setup incoherent)"
    for i in range(n_draw):
        st2.rng.next_internal(0, len(pool_ids) - i)          # NextInternal(0, candidates.Count)
    ref_ph = {}
    for tid in sorted(expect_hit):                          # ordre id (== multi=True du leaf)
        rr = AttackDamageOperation.execute_ability_attack(st2, cid, tid, bmin, bmax, pierce, hits,
                                                          damage_profile=cfg_profile, is_melee=False)
        ref_ph[tid] = (rr or {}).get("per_hit")
    port_ph = {t_id: main.get("per_hit")}
    for s in splash:
        port_ph[s["target"]] = (s["attack"] or {}).get("per_hit")
    print(f"[HAR r{rng_range}] params [bmin,bmax]=[{bmin},{bmax}] pierce={pierce} hits={hits} "
          f"profil={cfg_profile}")
    for tid in sorted(expect_hit):
        print(f"[HAR r{rng_range}]  e{tid} port_ph={port_ph.get(tid)} ref_ph={ref_ph.get(tid)}")
        assert port_ph.get(tid) == ref_ph.get(tid), (
            f"A/B e{tid}: arbre {port_ph.get(tid)} != baseline execute_ability_attack {ref_ph.get(tid)}")
    # (5) params BRUTS -> ORACLE CONFIG (jamais un litteral) : `constants.nrOfHits` (GetNumberConstant 0x2f)
    #     et `PiercingRatio` du profil NOMME par `constants.damageProfile` (GetDamageProfile 0, appele par
    #     `HarbingerOfDestructionAbility$$ExecuteBehaviour`). Le percage lui-meme est BRUT :
    #     `StaticBattleRules.Damage$$GetPiercingRatio` lit `DamageProfile.PiercingDamageRatio` tel quel.
    #     `assert_ability_damage_profile` epingle EN PLUS le nom lu en config a celui du decompile -- sans
    #     lui, un profil renomme en config deplacerait silencieusement l'attendu avec lui.
    #     Le percage EFFECTIF etant `clamp(0,100, ratio + ExtraPierce + ExtraPierceRanged)`, on exige
    #     d'abord des ExtraPierce nuls, sinon l'egalite ne testerait plus le choix du PROFIL mais la somme.
    from engine.runner.components import StatsComponent
    cfg_hits = int(cst["nrOfHits"])
    assert_ability_damage_profile("HarbingerOfDestruction", "DirectDamage")
    cfg_pierce = damage_profile_pierce(cfg_profile)
    ctx = st2.get_entity(cid).get_component(StatsComponent).ctx
    assert (ctx.extra_pierce, ctx.extra_pierce_ranged) == (0, 0), (
        f"caster avec percage supplementaire ({ctx.extra_pierce}/{ctx.extra_pierce_ranged}) : le percage "
        f"effectif n'est plus l'identite du PiercingRatio de profil -- adapter le setup ou l'attendu")
    assert hits == cfg_hits, \
        f"coups {hits} != constants.nrOfHits={cfg_hits} (oracle gameconfig, GetNumberConstant 0x2f)"
    assert pierce == cfg_pierce, (
        f"pierce {pierce} != damageProfiles[{cfg_profile}].PiercingRatio={cfg_pierce} (oracle gameconfig, "
        f"profil lu par GetDamageProfile(config, 0))")
    for tid in sorted(expect_hit):
        assert len(port_ph.get(tid) or []) == cfg_hits, (
            f"le PORT a joue {len(port_ph.get(tid) or [])} coups sur e{tid}, pas constants.nrOfHits="
            f"{cfg_hits}")
        for v in (port_ph.get(tid) or []):
            assert bmin <= v <= bmax, f"coup e{tid} {v} hors plage config [{bmin},{bmax}]"
    print(f"[HAR r{rng_range}] OK : ciblage rayon-{rng_range} (dist1&{rng_range} frappes, "
          f"dist{rng_range + 1} exclu), A/B tree==baseline, params {cfg_profile} (oracle config)")


def test_harbinger_hits_derived_from_config(har_off, monkeypatch):
    """DERIVATION du nb de coups : on DECALE `constants.nrOfHits` et le port doit SUIVRE.

    Sans ce controle, l'egalite du test precedent ne prouverait rien : `nrOfHits` vaut 1, exactement la
    valeur de repli du lecteur (`ability_var(..., is_constant=True) or 1`) -- une cle MAL nommee rendrait
    1 elle aussi et passerait inapercue (piege " cle voisine de meme valeur ", #96). Le decalage teste AUSSI
    que le canal `GetAttackHits` (famille ATTACK) est l'identite sur ce roster : le port doit rendre
    EXACTEMENT l'oracle decale. Geometrie minimale (cible + 1 additionnel a dist 1, jamais obscurci) ; etat
    reconstruit depuis les payloads en cache -- aucun RPC, aucun runner de plus."""
    import gameconfig as GC
    state = har_off["build_state"]()
    board = har_off["board"]
    cid = _find_by_vis(state, CASTER)
    ens = _enemies_of(state, cid)
    if cid is None or len(ens) < 2:
        pytest.skip("caster + 2 ennemis requis")
    C = next((board.coord(t) for t in sorted(board.by_id)
              if board.walkable(t) and len(_ring(board, board.coord(t), 1)) >= 2), None)
    if C is None:
        pytest.skip("aucune tuile a 2 voisins dist1")
    t_id, a_id = ens[0], ens[1]
    _park_others(state, board, {cid, t_id, a_id}, C)
    _set_pos(state, cid, *C)
    d1 = _ring(board, C, 1)
    _set_pos(state, t_id, *d1[0]); _set_pos(state, a_id, *d1[1])

    base = int(_cfg_constants()["nrOfHits"])
    bumped = base + 2
    orig_ability = GC.ability
    patched = dict(orig_ability("HarbingerOfDestruction") or {})
    patched["constants"] = {**(patched.get("constants") or {}), "nrOfHits": str(bumped)}
    monkeypatch.setattr(GC, "ability",
                        lambda aid: patched if aid == "HarbingerOfDestruction" else orig_ability(aid))
    res = HarbingerOfDestructionAbility().execute_behaviour(state, cid, t_id)
    assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
    per_hit = {t_id: ((res.get("main_attack") or {}).get("per_hit") or [])}
    for s in (res.get("splash") or []):
        per_hit[s["target"]] = (s["attack"] or {}).get("per_hit") or []
    print(f"\n[HAR derive] nrOfHits {base}->{bumped} : coups par cible "
          f"{ {k: len(v) for k, v in per_hit.items()} }")
    for tid, ph in per_hit.items():
        assert len(ph) == bumped, (
            f"e{tid} : {len(ph)} coups != oracle decale {bumped} (base {base}) -- le port ne DERIVE pas de "
            f"constants.nrOfHits (cle mal nommee retombant sur le repli 1, valeur figee, ou canal "
            f"GetAttackHits non identite sur ce roster)")


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
    """CAP : pool (ennemis du disque rayon-`range` - cible) > N-1 -> exactement N-1 additionnels
    (PickRandomly(N-1)) ; la cible MAIN n'est JAMAIS un additionnel (op_Subtraction Target()). MC1_67 ne
    spawne que 5 ennemis ; on borne le niveau d'ability au plus bas (N = `nrOfUnits`[niveau], config-driven)
    pour que le pool depasse n_pick et que le cap MORDE. `range` vient de la config (pas d'attendu fige)."""
    state = har_off["build_state"]()
    board, elev = har_off["board"], har_off["elev"]
    cid = _find_by_vis(state, CASTER)
    ens = _enemies_of(state, cid)
    if cid is not None:
        _set_ability_level(state, cid, 1)                   # niveau bas REEL -> N = nrOfUnits[idx 0]
    n_total, rng_range = _params(state, cid)
    n_pick = max(0, n_total - 1)
    need_disk = n_pick + 1                                   # ennemis dans le disque (hors cible) -> pool > n_pick
    if cid is None or n_pick < 1 or len(ens) < need_disk + 1:
        pytest.skip(f"besoin de N>=2 et {need_disk + 1} ennemis (cible + {need_disk} disque) ; N={n_total}, {len(ens)} dispo")
    # C avec assez de voisins dist1 (jamais obscurci) pour cible + need_disk ; complement au BORD du disque
    # (dist `range`, flat -> Unobscured passe) si besoin.
    C = None
    for t in sorted(board.by_id):
        if not board.walkable(t):
            continue
        c = board.coord(t); ec = elev.get(c)
        d1n = len(_ring(board, c, 1)); d2n = len(_ring(board, c, rng_range, ec, elev))
        if d1n + d2n >= need_disk + 1:                       # cible + need_disk cibles placables dans le disque
            C = c; break
    if C is None:
        pytest.skip(f"aucune tuile caster avec assez de tuiles disque (dist1+dist{rng_range} flat)")
    ec = elev.get(C)
    everyone = ens[:need_disk + 1]                           # cible + need_disk = pool > n_pick
    t_id = everyone[0]; pool_ids = everyone[1:]
    _park_others(state, board, set(everyone) | {cid}, C)
    _set_pos(state, cid, *C)
    occ = {C}
    slots = ([p for p in _ring(board, C, 1) if p not in occ]
             + [p for p in _ring(board, C, rng_range, ec, elev) if p not in occ])
    if len(slots) < len(everyone):
        pytest.skip("pas assez de tuiles disque placables (Unobscured)")
    for uid, p in zip(everyone, slots):
        _set_pos(state, uid, *p); occ.add(p)
    dist = {i: hexgeo.distance(C, _pos(state, i)) for i in everyone}
    assert all(dist[i] <= rng_range for i in everyone), \
        f"toutes les cibles doivent etre dans le disque rayon-{rng_range} : {dist}"

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
    D adjacent a la CIBLE mais HORS du disque rayon-`range` du CASTER -> il ne doit PAS etre frappe (refute
    cible-anchor). `range` = `constants.range` lu par le port (oracle config, aucun rayon fige ici)."""
    state = har_off["build_state"]()
    board, elev = har_off["board"], har_off["elev"]
    cid = _find_by_vis(state, CASTER)
    ens = _enemies_of(state, cid)
    if cid is None or len(ens) < 3:
        pytest.skip("caster + 3 ennemis requis")
    _n_total, rng_range = _params(state, cid)
    coords = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]
    # geometrie : C ; T au BORD du disque caster (dist `range`, flat) ; A a dist 1 du caster (additionnel) ;
    # D adjacent a T mais dist > `range` de C (meme elev) -> D est adjacent a la CIBLE (un splash
    # cible-anchor le frapperait) mais HORS du disque caster.
    geom = None
    for t in sorted(board.by_id):
        if not board.walkable(t):
            continue
        C = board.coord(t); ec = elev.get(C)
        d2 = _ring(board, C, rng_range, ec, elev); d1 = _ring(board, C, 1)
        if not d2 or not d1:
            continue
        for T in d2:
            Dc = [p for p in coords if hexgeo.distance(T, p) == 1 and elev.get(p) == ec
                  and hexgeo.distance(C, p) > rng_range and p != C]
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
    assert dC[d_id] > rng_range and dT == 1, (
        f"D doit etre adjacent a la CIBLE (dT={dT}) mais hors du disque caster rayon-{rng_range} "
        f"(dC={dC[d_id]})")

    hp0 = {i: _hp(state, i) for i in (t_id, a_id, d_id)}
    res = HarbingerOfDestructionAbility().execute_behaviour(state, cid, t_id)
    hit = {t_id} | {s["target"] for s in (res.get("splash") or [])}
    print(f"[HAR anchor] hit={sorted(hit)}")
    assert a_id in hit, f"A e{a_id} (dist {dC[a_id]} du caster) devrait etre frappe (additionnel caster-anchor)"
    assert d_id not in hit, f"D e{d_id} (adjacent cible mais dist {dC[d_id]} du caster) frappe a tort -> cible-anchor"
    assert _hp(state, d_id) == hp0[d_id], f"D e{d_id} endommage a tort (ciblage cible-anchor)"
    assert _hp(state, a_id) < hp0[a_id], f"A e{a_id} (disque caster) non endommage"
    print(f"[HAR anchor] OK : additionnels ancres sur le CASTER (disque rayon-{rng_range}), pas sur la cible")
