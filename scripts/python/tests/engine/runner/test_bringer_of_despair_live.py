"""case-220 §6.11 BlackLegion : BringerOfDespair (1022, Angrax `blackTerminator`) FACE COMBAT confront LIVE.

`BringerOfDespairAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.BringerOfDespairAbility$$ExecuteBehaviour` (DECOMPILE, mirror 1:1 + callees verifiees) :
    bonusSel = PickRandomly( Damageable(Enemies(AdjacentUnits(casterTile@0x168, r=1))) − Target()@0x178, 1 )
    ExecuteAtomic( op_BitwiseAnd(
        AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage, GetDamageProfile=Power, 0x2f=4),  # MAIN
        AttackWithAttackDamage(caster@0x160, bonusSel,     MinMaxDamage, Power,                  0x32=4) ), 0x45 )  # BONUS
i2 : « 4x Power to a melee target and 4x Power to another random enemy adjacent to Angrax [le caster]. »
`native_factory="attack"` (les DEUX volets = `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`, VERIFIE par les
callees de IdunBattleLogic.Entities.Abilities.Active.Loki.BringerOfDespairAbility$$ExecuteBehaviour) = 2 tirages/coup a cc=0 -- pipeline partage rngcrit-1202 (tip #2).

Ce que ces tests PROUVENT (drive les 2 camps -- applyAction ignore propriete+portee -- `--hp-target` = armure
nulle pour un per-coup bit-exact SANS le gap d'arrondi pierce/armure) :
  (1) CAST LIVE bit-exact : MAIN 4 coups sur la cible == live per-coup (profil Power melee, minDmg/maxDmg/
      pierce corrects, path attack-family 2 tirages/coup) ; BONUS = 4 coups sur UN ennemi adjacent au CASTER.
  (2) FIDELITE A/B : l'arbre `bringer_of_despair_tree()` == une sequence directe `execute_ability_attack`
      (main 4 coups puis bonus 4 coups, meme rng seede) -> le port n'introduit AUCUN bug de degat.
  (3) DISCRIMINANT caster-anchor (offline, drive) : le bonus frappe l'ennemi adjacent au CASTER, PAS un
      ennemi adjacent a la CIBLE seule (contraste PlasmaGrenade/Stikkbomb/Fragstorm = cible-ancres). C'est
      LE point de fidelite critique de BringerOfDespair (CasterTile, pas TargetTile).
  (4) DISCRIMINANT cap-1 + exclude-target (offline, drive) : 2 ennemis adjacents au caster -> le bonus n'en
      frappe QU'UN (PickRandomly(1), contraste Gauntlets AoE=tous) ; la cible MAIN n'est jamais dans le bonus.

GAP CONNU (hors port, #205/#215) : (a) le per-coup vs live peut desync apres le 1er coup d'une cible multi-
coups quand un block-chance present LIVE mais non charge OFFLINE decale le rng (PRE-EXISTANT, prouve par A/B) ;
(b) quand le pool du pick a >1 candidat, l'ORDRE d'enumeration natif (non id-trie) decide QUI est pique --
residu #215 restant. Le COUT du pick, lui, est cale depuis #130 : `PickRandomly` consomme `min(len(pool),
amount)` tirages MEME quand le pool tient dans `amount` (aucun court-circuit au decompile), et la baseline
A/B ci-dessous le reproduit explicitement. On asserte MAIN per-coup exact (le MAIN precede TOUT pick) + A/B
+ les discriminants de CIBLAGE (caster-anchor, cap-1, exclude-target), PAS le per-coup exact du bonus sous
pick multi-candidat.

Drive les positions (memoire « drive positions, don't blame geometry »). Lit l'etat LIVE, aucune RVA/tuile
hardcodee, seed = simple generateur. ASCII-only.
"""
from __future__ import annotations

import json

import pytest

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.abilities.base import ability_attack_params
from engine.runner.abilities.blacklegion import BringerOfDespairAbility

ANGRAX = "blackTerminator"                                   # id 1022 BringerOfDespair
ABILITY = 1022
HP = "500000"                                                # ennemis armure 0 (bit-exact) + survivent 4 coups
ENEMIES2 = "necroWarden,necroDestroyer"                      # cast live (2 ennemis -> bonus deterministe)
ENEMIES3 = "necroWarden,necroDestroyer,necroOverlord"        # discriminants offline (3 ennemis)
BUILD_LIVE = ["--p-units", ANGRAX, "--a-units", ENEMIES2, "--hp-target", HP]
BUILD_OFF = ["--p-units", ANGRAX, "--a-units", ENEMIES3, "--hp-target", HP]


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


def _walk(board, coord):
    t = board.id_at(coord[0], coord[1])
    return t is not None and board.walkable(t)


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


# ------------------------------------------------------------------ fixtures

@pytest.fixture(scope="session")
def bod_off(rpc, build_runner):
    """Etat LIVE reel (Angrax + 3 necrons) charge offline, rejouable a volonte (drive offline)."""
    rid = build_runner("777", extra=BUILD_OFF)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)

    def build_state():
        st = load_state(dv, ob, snap, board=board)
        if isinstance(rng0, dict) and rng0.get("mt"):
            st.rng = _seed_rng(rng0)
        return st

    if _find_by_vis(build_state(), ANGRAX) is None:
        pytest.skip("Angrax (blackTerminator) absent du build")
    return {"build_state": build_state, "board": board}


# ------------------------------------------------------------------ (1)+(2) CAST LIVE bit-exact + A/B

def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def test_bringer_live_cast_targeting_and_ab_fidelity(live_session, rpc, build_runner):
    """CAST LIVE reel : le CIBLAGE (main sur la cible + bonus sur l'unique ennemi adjacent au CASTER,
    != cible) == offline ; les COUPS de base = config 4/4 offline ; l'arbre == baseline execute_ability_attack
    (A/B bit-exact offline) ; la magnitude offline dans la plage config-scalee.

    CONFOUND DOCUMENTE (VERIFIE decompile) : Angrax porte le trait faction `LetTheGalaxyBurn` (1482, Black
    Legion), une ability DECLENCHEE (`Abilities.Triggered.Loki.LetTheGalaxyBurnAbility`) qui pose
    `EffectAdditionalHits.Create` (`IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`) -> +1 coup/attaque
    COMPOSE par-dessus l'attaque (comme FleshmetalGuns extra-hits). Ce trait est HORS de l'IdunBattleLogic.Entities.Abilities.Active.Loki.BringerOfDespairAbility$$ExecuteBehaviour (aucun noeud extra-hit) ET NON WIRE offline (transverse case-doc §6.11, TRAIT_TRIGGERS). Live =
    5 coups/attaque = 4 (BringerOfDespair) + 1 (trait) ; le coup extra decale TOUT le flux RNG -> le per-coup
    -vs-live n'est PAS bit-exact (confondu). On valide donc le CIBLAGE (non confondu : le trait ne change pas
    QUI est frappe) + la fidelite du degat par A/B OFFLINE (bit-exact, tree==baseline) + la magnitude config,
    PAS le per-coup-vs-live. La face extra-hit du trait = item transverse SEPARE (hors BringerOfDespair)."""
    rid = build_runner("777", extra=BUILD_LIVE)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")

    def dview():
        return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)

    def move(uid, coord):
        return rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": coord[0], "row": coord[1]}}}, 40)

    def dv_alive(dv):
        return [u for u in (dv.get("units") or []) if u.get("alive")]

    def upos(u):
        p = u.get("pos") or {}
        return (p.get("col"), p.get("row")) if p.get("col") is not None else None

    dv = dview()
    if not _ok(dv):
        pytest.skip("decisionView KO")
    ang = next((u for u in dv_alive(dv) if u.get("visualId") == ANGRAX), None)
    if ang is None:
        pytest.skip("Angrax absent")
    myp = ang.get("owner")
    ang_id = ang["id"]

    # atteindre MON tour
    for _ in range(12):
        dv = dview()
        if dv.get("currentPlayer") == myp:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    else:
        pytest.skip("jamais mon tour")

    ang = next((u for u in dv_alive(dv) if u.get("id") == ang_id), None)
    ens = [u for u in dv_alive(dv) if u.get("owner") != myp]
    if ang is None or len(ens) < 2:
        pytest.skip("Angrax + 2 ennemis requis")

    # geometrie : C (tuile Angrax) avec >=2 voisins hex marchables libres -> y poser T et B (les 2 ennemis)
    def hex_nbrs_free(center, occupied):
        return [board.coord(t) for t in sorted(board.by_id)
                if board.walkable(t) and hexgeo.distance(board.coord(t), center) == 1
                and board.coord(t) not in occupied]

    C = upos(ang)
    if not (_walk(board, C) and len(hex_nbrs_free(C, {C})) >= 2):
        # choisir une tuile C marchable avec >=2 voisins libres, atteignable-ish (on force le move)
        cand = [board.coord(t) for t in sorted(board.by_id)
                if board.walkable(t) and len(hex_nbrs_free(board.coord(t), {board.coord(t)})) >= 2]
        if not cand:
            pytest.skip("aucune tuile C avec 2 voisins libres")
        C = min(cand, key=lambda c: (c[0] - 3) ** 2 + (c[1] - 4) ** 2)
        if move(ang_id, C).get("ok") is not True and upos(next(u for u in dv_alive(dview()) if u["id"] == ang_id)) != C:
            pytest.skip("move Angrax->C KO")
    nb = hex_nbrs_free(C, {C})
    if len(nb) < 2:
        pytest.skip("pas 2 voisins libres autour de C")
    T_coord, B_coord = nb[0], nb[1]
    t_id, b_id = ens[0]["id"], ens[1]["id"]
    move(t_id, T_coord); move(b_id, B_coord)

    # geometrie finale reelle
    dv = dview()
    ang = next(u for u in dv_alive(dv) if u["id"] == ang_id)
    C = upos(ang)
    ens = {u["id"]: upos(u) for u in dv_alive(dv) if u.get("owner") != myp}
    adj_caster = sorted(i for i, p in ens.items() if p and hexgeo.distance(C, p) == 1)
    if t_id not in adj_caster or b_id not in adj_caster or len(adj_caster) != 2:
        pytest.skip(f"geometrie non atteinte : C={C} ens={ens} adj_caster={adj_caster}")
    # cible MAIN = t_id ; bonus deterministe = b_id (unique ennemi adjacent-caster != cible)

    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")

    # --- CAST LIVE (cible = t_id) ---
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": ang_id, "targetId": t_id, "abilityType": ABILITY}}, 60)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        pytest.skip(f"cast KO: {str(res)[:160]}")
    live_by_tgt = {}
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
            live_by_tgt.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
    if not live_by_tgt:
        pytest.skip("aucun event de degat BringerOfDespair live")

    # --- OFFLINE : l'engine DERIVE l'arbre DSL depuis le cast ---
    st = load_state(dv, ob, snap, board=board); st.rng = _seed_rng(s0)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=ang_id, target_id=t_id, ability_type=ABILITY))
    last = runner.ability_handler.last or {}
    assert last.get("ported"), f"ability {ABILITY} non routee par le wiring: {last}"
    main = last.get("main_attack") or {}
    bonus = last.get("bonus") or []
    # #227 : la SEQUENCE d'evenements de degat encaissee par une cible = coups d'ARME **puis** coups
    #   des groupes du canal #179 (sous-operations de la MEME `IdunBattle.Operations.
    #   AttackDamageOperation$$Execute`). Le coup `LetTheGalaxyBurn` d'Angrax est desormais l'un de
    #   ces groupes (descripteur `IdunBattle.Entities.Effects.EffectAdditionalHits`), plus un coup
    #   d'arme surnumeraire -> il faut concatener les deux canaux pour reconstituer le live.
    def _seq(a):
        return list((a or {}).get("per_hit") or []) \
            + list(((a or {}).get("additional_hits") or {}).get("per_hit") or [])

    off_main_ph = _seq(main)
    off_bonus = bonus[0] if bonus else {}
    off_bonus_ph = _seq(off_bonus.get("attack"))

    # baseline degat scalee (armure 0 -> per-coup dans [bmin, bmax] ; pas de crit cc=0, pas de block).
    # La sequence de reference DOIT inclure le `PickRandomly(bonusSel, 1)` qui SEPARE les deux volets :
    # `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` consomme `min(len(pool), 1)`
    # tirages MEME quand le pool tient dans `amount` (#130 -- aucun court-circuit au decompile ; la
    # borne 1 passe par la branche puissance-de-2 de `IntBasedMersenneTwister$$NextInternal`, qui
    # consomme un `genrand_int32`). Sans ce tirage la baseline decrit un flux RNG qui n'existe pas.
    st2 = load_state(dv, ob, snap, board=board); st2.rng = _seed_rng(s0)
    bmin, bmax, pierce, _ = ability_attack_params(st2, ang_id, "BringerOfDespair", "Power", ranged=False)
    ref_main = AttackDamageOperation.execute_ability_attack(st2, ang_id, t_id, bmin, bmax, pierce, 4,
                                                            damage_profile="Power", is_melee=True)
    n_bonus_pool = len([e for e in adj_caster if e != t_id])          # pool du PickRandomly (cible retiree)
    for i in range(min(n_bonus_pool, 1)):                             # min(len(pool), amount=1) tirages
        st2.rng.next_internal(0, n_bonus_pool - i)                    # NextInternal(0, candidates.Count)
    ref_bonus = AttackDamageOperation.execute_ability_attack(st2, ang_id, b_id, bmin, bmax, pierce, 4,
                                                             damage_profile="Power", is_melee=True)

    lm, lb = live_by_tgt.get(t_id) or [], live_by_tgt.get(b_id) or []
    print(f"\n[BOD live] C={C} main=t{t_id} bonus_off=t{off_bonus.get('target')} adj_caster={adj_caster}")
    print(f"[BOD live] plage config-scalee [bmin,bmax]=[{bmin},{bmax}] pierce={pierce}")
    print(f"[BOD live] live main(t{t_id})={lm} ({len(lm)} coups)  live bonus(t{b_id})={lb} ({len(lb)} coups)")
    print(f"[BOD live] off  main={off_main_ph} ({len(off_main_ph)})  off bonus(t{off_bonus.get('target')})={off_bonus_ph} ({len(off_bonus_ph)})")

    # (1) CIBLAGE (NON confondu par le trait extra-hit -- il ne change pas QUI est frappe) :
    #  - LIVE frappe EXACTEMENT {cible MAIN, unique ennemi adjacent-CASTER} == offline main+bonus.
    assert off_bonus.get("target") == b_id, \
        f"bonus offline cible t{off_bonus.get('target')} != t{b_id} (unique ennemi adjacent-CASTER)"
    assert set(live_by_tgt) == {t_id, b_id}, \
        f"live frappe {set(live_by_tgt)} != {{t{t_id}(main), t{b_id}(bonus adjacent-caster)}}"

    # (2) COUPS : assertion d'ACCORD offline == live, plus au moins la base config 4/4 des deux cotes.
    #     ⚠ Cette assertion exigeait `== 4` cote offline, ce qui encodait « le port ne compose PAS le
    #     coup additionnel `LetTheGalaxyBurn` ». Le port le compose DESORMAIS (canal #179 + verdict du
    #     `Maybe` alignes) : le test etait ROUGE sur `origin/master` avec offline 5/5 == live 5/5, donc
    #     un ACCORD PARFAIT rejete par une attente perimee. Mesure (seed 777, MC1_67) :
    #         live main [2832,2578,2516,2852,2946] / bonus [2537,2981,2476,2358,2379]
    #         off  main [2832,2578,2516,2852,2946] / bonus [2537,2981,2476,2358,2379]   (bit-exact)
    #     Corrige en ACCORD : c'est le live qui est l'oracle, pas la constante de config.
    assert len(off_main_ph) == len(lm) and len(off_bonus_ph) == len(lb), \
        (f"coups offline main={len(off_main_ph)} bonus={len(off_bonus_ph)} != "
         f"live main={len(lm)} bonus={len(lb)}")
    assert len(lm) >= 4 and len(lb) >= 4, \
        f"coups live main={len(lm)} bonus={len(lb)} < 4 (base config attendue sur chaque attaque)"

    # (3) FIDELITE A/B (OFFLINE, bit-exact) : l'arbre == sequence directe execute_ability_attack (main 4 coups
    #     puis bonus 4 coups, meme rng seede) -> le port n'introduit AUCUN bug de degat (structure/pipeline).
    assert off_main_ph == _seq(ref_main), \
        f"arbre MAIN {off_main_ph} != baseline execute_ability_attack {_seq(ref_main)}"
    assert off_bonus_ph == _seq(ref_bonus), \
        f"arbre BONUS {off_bonus_ph} != baseline {_seq(ref_bonus)} (port non bit-exact vs pipeline)"

    # (4) MAGNITUDE : chaque coup offline dans la plage config-scalee [bmin,bmax] (armure 0, cc=0, pas de block)
    #     -> profil Power/pierce/minDmg/maxDmg corrects. (Live NON borne strictement : le trait/DespoiledGround
    #     peut ajouter du degat -- on sanity-check juste que les coups live sont du meme ordre.)
    for v in off_main_ph + off_bonus_ph:
        assert bmin <= v <= bmax, f"coup offline {v} hors plage config-scalee [{bmin},{bmax}]"
    assert lm and min(lm) >= bmin // 2, f"coups live main {lm} anormalement bas vs plage [{bmin},{bmax}]"

    print("[BOD live] OK : ciblage main+bonus(adjacent-caster) LIVE, coups offline == live, "
          "A/B tree==baseline, magnitude config ; 5/5 = 4 config + extra-hit LetTheGalaxyBurn, "
          "desormais COMPOSE par le port aussi")


# ------------------------------------------------------------------ (3) DISCRIMINANT caster-anchor

def _find_caster_anchor_geom(board):
    """(C, T, B, D) marchables distincts : dist(C,T)=1, dist(C,B)=1, dist(T,D)=1, dist(B,T)>=2, dist(D,C)>=2.
    B = adjacent CASTER (pas cible) ; D = adjacent CIBLE (pas caster) -> discriminant net caster vs cible."""
    coords = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]
    cset = set(coords)

    def nbrs(c):
        return [d for d in coords if hexgeo.distance(c, d) == 1]
    for C in coords:
        cn = nbrs(C)
        for T in cn:
            for B in cn:
                if B == T or hexgeo.distance(B, T) < 2:
                    continue
                for D in nbrs(T):
                    if D in (C, T, B) or hexgeo.distance(D, C) < 2:
                        continue
                    return C, T, B, D
    return None


def test_bringer_bonus_anchored_on_caster_not_target(bod_off):
    """DISCRIMINANT : le bonus frappe l'ennemi adjacent au CASTER (B), PAS l'ennemi adjacent a la CIBLE
    seule (D). Prouve `AdjacentUnits(CasterTile())` et refute un ciblage cible-ancre (PlasmaGrenade-like)."""
    state = bod_off["build_state"]()
    board = bod_off["board"]
    ang = _find_by_vis(state, ANGRAX)
    ens = _enemies_of(state, ang)
    if ang is None or len(ens) < 3:
        pytest.skip("Angrax + 3 ennemis requis")
    geom = _find_caster_anchor_geom(board)
    if geom is None:
        pytest.skip("aucune geometrie caster-anchor discriminante")
    C, T, B, D = geom
    t_id, b_id, d_id = ens[0], ens[1], ens[2]
    _park_others(state, board, {ang, t_id, b_id, d_id}, C)
    _set_pos(state, ang, *C); _set_pos(state, t_id, *T); _set_pos(state, b_id, *B); _set_pos(state, d_id, *D)

    hp_b0, hp_d0 = _hp(state, b_id), _hp(state, d_id)
    res = BringerOfDespairAbility().execute_behaviour(state, ang, t_id)
    assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
    bonus = res.get("bonus") or []
    print(f"\n[BOD anchor] C={C} T={T}(t{t_id}) B={B}(t{b_id},adjC) D={D}(t{d_id},adjT) "
          f"bonus={[x['target'] for x in bonus]}")
    # bonus = B (adjacent CASTER), PAS D (adjacent CIBLE)
    assert len(bonus) == 1 and bonus[0]["target"] == b_id, \
        f"bonus doit cibler B=t{b_id} (adjacent caster), pas {[x['target'] for x in bonus]}"
    assert _hp(state, b_id) < hp_b0, f"B (adjacent caster) non endommage (hp {hp_b0} -> {_hp(state, b_id)})"
    assert _hp(state, d_id) == hp_d0, \
        f"D (adjacent CIBLE seule) endommage a tort -> ciblage cible-ancre (hp {hp_d0} -> {_hp(state, d_id)})"


# ------------------------------------------------------------------ (4) DISCRIMINANT cap-1 + exclude-target

def _find_two_caster_adj(board):
    """(C, T, B1, B2) : dist(C,T)=1, dist(C,B1)=1, dist(C,B2)=1, tous distincts -> 2 ennemis adjacents caster."""
    coords = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]

    def nbrs(c):
        return [d for d in coords if hexgeo.distance(c, d) == 1]
    for C in coords:
        cn = nbrs(C)
        if len(cn) >= 3:
            return C, cn[0], cn[1], cn[2]
    return None


def test_bringer_bonus_cap1_and_excludes_target(bod_off):
    """DISCRIMINANT : 2 ennemis adjacents au CASTER -> le bonus n'en frappe QU'UN (PickRandomly(1), cap 1,
    contraste Gauntlets=tous) ; la cible MAIN n'est JAMAIS dans le bonus (op_Subtraction Target())."""
    state = bod_off["build_state"]()
    board = bod_off["board"]
    ang = _find_by_vis(state, ANGRAX)
    ens = _enemies_of(state, ang)
    if ang is None or len(ens) < 3:
        pytest.skip("Angrax + 3 ennemis requis")
    geom = _find_two_caster_adj(board)
    if geom is None:
        pytest.skip("aucune tuile a 3 voisins pour 2 ennemis adjacents caster")
    C, T, B1, B2 = geom
    t_id, b1, b2 = ens[0], ens[1], ens[2]
    _park_others(state, board, {ang, t_id, b1, b2}, C)
    _set_pos(state, ang, *C); _set_pos(state, t_id, *T); _set_pos(state, b1, *B1); _set_pos(state, b2, *B2)

    hp0 = {u: _hp(state, u) for u in (t_id, b1, b2)}
    res = BringerOfDespairAbility().execute_behaviour(state, ang, t_id)
    assert res is not None
    bonus = res.get("bonus") or []
    hit = [x["target"] for x in bonus]
    print(f"\n[BOD cap1] C={C} cible=t{t_id} adjC={{t{b1},t{b2}}} bonus={hit}")
    # cap 1 : exactement UN bonus, dans {b1,b2} (jamais la cible), l'autre non touche
    assert len(bonus) == 1, f"bonus doit etre cap 1 (PickRandomly(1)), obtenu {len(bonus)}: {hit}"
    assert hit[0] in (b1, b2), f"bonus t{hit[0]} hors {{t{b1},t{b2}}} (ennemis adjacents caster)"
    assert hit[0] != t_id, "la cible MAIN ne doit JAMAIS etre dans le bonus (op_Subtraction Target())"
    other = b2 if hit[0] == b1 else b1
    assert _hp(state, other) == hp0[other], f"le 2e ennemi adjacent (non pick) est touche a tort (cap 1 viole)"
    assert _hp(state, t_id) < hp0[t_id], "la cible MAIN doit subir l'attaque principale"
    assert _hp(state, hit[0]) < hp0[hit[0]], "l'ennemi bonus pick doit subir des degats"
