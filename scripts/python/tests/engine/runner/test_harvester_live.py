"""HarvesterOfSouls (1067, eldarMauganRa « Maugan Ra », Aeldari) -- face COMBAT (execute) portee, confrontee au LIVE.

`IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$ExecuteBehaviour` (DECOMPILE, mirror 1:1 -- namespace natif
`Abilities.Active.Loki.HarvesterOfSoulsAbility`) =
    hits = If( HasFlag(caster@0x160, Moved=0), ConfigConst(nrOfHits=0x2f),                       # IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetHits
               Sum(ConfigConst(nrOfHits=0x2f), ConfigConst(extraHit=0x2b)) )                     #   a bouge:2 / sinon:3
    ExecuteAtomic( op_BitwiseAnd(                                                                 # tag 0x2a
        AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage, Nullable(0x13=HeavyRound), hits),   # MAIN
        AttackWithAttackDamage(caster@0x160,
            And( SurroundingUnits(caster@0x160, GetNumberConstant(range=0x16)),                   # A: <= range hex caster
                 Enemies(caster, AdjacentFriends(target@0x178, 1)) ),                             # B: ennemis ring-1 cible
            MinMaxDamage2, Nullable(0x13=HeavyRound), hits) ) )                                   # SPLASH

i2 : « 3x HeavyRound + 1 extra hit if hasn't moved a un ennemi ET aux ennemis adjacents dans un rayon ».
Attaque RANGED HeavyRound. Config 1067 LUE A LA REDACTION (les tests, eux, la relisent : cf. ORACLE en bas
de cet en-tete) : nrOfHits=2, extraHit=1, range=3, PiercingRatio 55 ; minDmg_2/maxDmg_2 ==
minDmg/maxDmg. `native_factory="attack"` (IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage, XREF ExecuteBehaviour ; 2 tirages/coup a cc=0, rngcrit-1202).
Le natif B `Enemies(caster, AdjacentFriends(target,1))` = ennemis-du-caster ring-1 de la cible ; porte via
`AdjacentEnemies(TargetTile(), Const(1))` (le runner `AdjacentFriends` filtre team==CASTER, PAS subject-relatif ->
`Enemies(AdjacentFriends(target))` serait VIDE ; `AdjacentEnemies(TargetTile())` = l'equivalent CORRECT, convention #122).

Ce que ces tests PROUVENT :
  (a) CAST LIVE bit-exact (cas A BOUGE, hits=2) : MAIN + SPLASH per-coup == le port offline (arbre DSL), sous le
      meme rng seede -> les feuilles appellent le pipeline d'attaque fidele.
  (c) FIDELITE A/B : arbre == sequences directes `execute_ability_attack(hits, HeavyRound, "attack")` (main +
      splash minDmg_2/maxDmg_2) -> le port n'introduit AUCUN bug de degat.
  (d) NATIVE_FACTORY : la MAIN live == modele "attack" (2 tirages/coup), != "ability" (1 tirage/coup) -> le choix
      "attack" est le bon (discriminant rngcrit-1202), sur 2 seeds.
  (e) SPLASH GEOMETRIE (offline, drive positions) : splash = ennemis a la FOIS adjacents (ring-1) a la cible ET
      <= range(3) hex du caster. Ennemi adjacent-cible mais HORS rayon-caster -> exclu (pruning A) ; ennemi dans
      le rayon mais NON adjacent-cible -> exclu (pruning B) ; la cible principale hors splash.
  (f) HITS FORMULE (offline, flag MOVED) : A BOUGE -> nrOfHits=2 ; PAS BOUGE -> nrOfHits+extraHit=3.

VALIDATION MOVED-ONLY pour le bit-exact : le passif `InescapableAccuracy` de Maugan Ra (+crit-chance/+crit-dmg/
override-hits, gated « n'a pas bouge ») est un item SEPARE ([opus]+prerequis) NON porte -> il ne s'applique PAS
offline. Le cas A BOUGE gate ce passif OFF cote LIVE (cc=0) -> bit-exact PROPRE. Le cas PAS BOUGE : le live applique
le passif (crits per-coup) tandis que l'offline non (mesure : main live [3748,3104,2616] vs offline [2001,2035,2211],
ratios ~1.87/1.52/1.18 = crits) -> divergence per-coup ATTENDUE cote live (non un bug de ce port ; le hit-count=3 et
la geometrie splash restent EXACTS). D'ou : per-coup live-agreement teste UNIQUEMENT sur le cas A BOUGE (cc=0).

ORACLE (#96) -- AUCUN scalaire de gameplay n'est fige dans ce fichier. Le decompile tranche brut/calcule :
  * `HarvesterOfSoulsAbility$$GetHits` = `If(HasFlag(caster,Moved), ConfigConst(0x2f), Sum(ConfigConst(0x2f),
    ConfigConst(0x2b)))` -> les DEUX operandes sont des `ConfigConst` = BRUTS (`constants.nrOfHits` et
    `constants.extraHit`, indices resolus sur `IdunBattle.Configuration.AbilityConstantType`). Le nb de coups,
    lui, est CALCULE par cette formule : le test le confronte donc a `nrOfHits` / `nrOfHits + extraHit` selon
    la branche (jamais a 2/3 ecrits en dur) cote offline, et au LIVE (`len(live_main)`) cote bataille.
  * `ExecuteBehaviour` passe `GetNumberConstant(config, 0x16)` (= `constants.range`) TEL QUEL a
    `SurroundingUnits` -> BRUT : la portee du splash est lue en config et PILOTE la geometrie du scenario.
  * le profil, lui, n'est PAS lu en config : le decompile construit un `Nullable<DamageProfileType>(0x13)`
    litteral (0x13 = 19 = HeavyRound sur `IdunBattle.Entities.Enum.DamageProfileType`) -> le NOM reste un
    mirror en dur, mais son `PiercingRatio` se lit dans `damageProfiles`.

Drive les positions (memoire « drive positions »). Lit l'etat LIVE, aucune RVA/tuile hardcodee. ASCII only.
State-file UNIQUE par agent (chemin absolu). Skip propre si pas de session / geometrie / legalite infaisable.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _config_oracle import damage_profile_pierce    # noqa: E402

import hexgeo

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                      # racine repo
AGENT = "a0cb06c655a982391"                                  # id agent -> state-file unique (coexistence runners)
CASTER_VIS = "eldarMauganRa"
ABILITY = 1067
ABILITY_ID = "HarvesterOfSouls"                              # cle gameconfig (= ABILITY_ID du port)
A_UNITS = "necroWarden,necroDestroyer,necroOverlord"
# Profil de degat : le decompile d'`ExecuteBehaviour` construit un `Nullable<DamageProfileType>(0x13)`
# LITTERAL (pas de `GetDamageProfile(config)`) -- 0x13 = 19 = HeavyRound. Le nom est donc un mirror en dur ;
# son PiercingRatio, lui, se lit dans `damageProfiles` (cf. `_cfg_pierce`).
PROFILE = "HeavyRound"


# ------------------------------------------------------------------ helpers

def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _cfg_constants() -> dict:
    """ORACLE des scalaires BRUTS de 1067 = `constants` de gameconfig (cf. en-tete : `ConfigConst(0x2f/0x2b)`
    et `GetNumberConstant(0x16)` sont pris TELS QUELS par le natif)."""
    import gameconfig as GC
    cst = (GC.ability(ABILITY_ID) or {}).get("constants") or {}
    assert cst.get("nrOfHits") is not None and cst.get("extraHit") is not None \
        and cst.get("range") is not None, \
        f"oracle introuvable : constants nrOfHits/extraHit/range de {ABILITY_ID} (lu: {cst})"
    return cst


def _cfg_range() -> int:
    """`constants.range` (GetNumberConstant 0x16) -- PILOTE la geometrie des scenarios splash."""
    return int(_cfg_constants()["range"])


def _build(seed: str):
    """Build un runner ISOLE (state-file unique agent+tag, chemin absolu). Renvoie (rid, state_file)."""
    tag = uuid.uuid4().hex[:8]
    state_file = ROOT / "logs" / "runners" / f"harv-{AGENT}-{seed}-{tag}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(state_file),
         "--board", "MC1_67", "--p-units", CASTER_VIS, "--a-units", A_UNITS, "--hp-target", "300000",
         # #933 -- LE REGIME « cc = 0 » SE CONSTRUIT. Le volet bit-exact ci-dessous SKIPPE quand le
         # caster a de la chance de crit ; depuis la bascule #419-r5/-r6 (items BiS par defaut),
         # `eldarMauganRa` en porte (MESURE : `probe_933_premisses_regime.py --unites`), donc le
         # skip etait SYSTEMATIQUE -- 1 passed / 2 skipped, rc 0, coeur du fichier jamais evalue.
         "--crit", "0,0"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        return None, state_file
    return json.loads(state_file.read_text())["runnerId"], state_file


def _cleanup(rpc, rid, state_file):
    if rid:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass
    try:
        if state_file is not None:
            state_file.unlink()
    except Exception:
        pass


def _mk_rng(s):
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _mv(rpc, rid, uid, c):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)


def _legal_fromhere(rpc, rid, cid):
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
    a = next((x for x in ((at.get("units") or [{}])[0].get("abilities") or [])
              if x.get("abilityId") == ABILITY), {})
    return set(x.get("targetId") for x in (a.get("fromHere") or []))


def _drive_moved(rpc, rid, board):
    """Place la cible sur une tuile T a >=3 voisins libres, un ennemi SPLASH sur un voisin de T, parque les
    autres LOIN, DEPLACE le caster (Maugan) sur un autre voisin de T (pose UnitFlag.Moved -> hits=2, gate le
    passif InescapableAccuracy OFF) et verifie la LEGALITE du cast. Renvoie (dv, cid, tid, sid) ou (None,..)."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    me = next((u for u in (dv.get("units") or []) if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
    if me is None:
        return None, None, None, None
    myp = me.get("owner"); cid = me["id"]
    ens = [u for u in (dv.get("units") or []) if u.get("owner") != myp and u.get("alive")]
    if len(ens) < 2:
        return None, None, None, None
    T = next((t for t in sorted(board.by_id)
              if board.walkable(t) and sum(1 for n in board.neighbours(t) if board.walkable(n)) >= 3), None)
    if T is None:
        return None, None, None, None
    tc = board.coord(T)
    nb = [board.coord(n) for n in board.neighbours(T) if board.walkable(n)]
    tgt, e1 = ens[0], ens[1]
    far = [board.coord(t) for t in sorted(board.by_id)
           if board.walkable(t) and hexgeo.distance(board.coord(t), tc) > 6]
    for i, e in enumerate(ens[2:]):
        if i < len(far):
            _mv(rpc, rid, e["id"], far[i])
    _mv(rpc, rid, tgt["id"], tc)
    # caster sur un voisin de T d'ou la cible est LEGALE ; splash e1 sur un AUTRE voisin de T (dist<=range du caster)
    for ci, c in enumerate(nb):
        _mv(rpc, rid, cid, c)                                        # DEPLACE le caster -> UnitFlag.Moved
        if tgt["id"] not in _legal_fromhere(rpc, rid, cid):
            continue
        sc = next((s for j, s in enumerate(nb) if j != ci and hexgeo.distance(s, c) <= _cfg_range()), None)
        if sc is None:
            continue
        _mv(rpc, rid, e1["id"], sc)                                  # splash : adjacent-cible ET <= range du caster
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        return dv, cid, tgt["id"], e1["id"]
    return None, None, None, None


def _live_dmg_by_target(cast):
    live = {}
    for a in (cast.get("actions") or []):
        for e in (a.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                live.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
    return live


# ------------------------------------------------------------------ (a)+(c)+(d) LIVE cast MOVED + A/B + native_factory

@pytest.mark.parametrize("seed", ["777", "31337"])
def test_harvester_live_moved_bitexact_and_native_factory(live_session, rpc, seed):
    """(a) MAIN + SPLASH live per-coup == arbre DSL offline (bit-exact, cas A BOUGE hits=2, cc=0) ; (c) arbre ==
    sequences directes `execute_ability_attack` (main + splash minDmg_2/maxDmg_2, "attack") ; (d) native_factory :
    live == "attack" (2 tirages/coup) != "ability" (1/coup). Le caster est DEPLACE -> hits=2 + passif
    InescapableAccuracy gate OFF (cc=0 requis pour le bit-exact)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.components import StatsComponent, UnitFlagsComponent
    from engine.runner.abilities.aeldari import HarvesterOfSoulsAbility, _harvester_hits
    from engine.runner.abilities.base import ability_attack_params
    from engine.runner.operations.damage import AttackDamageOperation

    rid, state_file = _build(seed)
    if rid is None:
        pytest.skip("build runner KO (rl_duel)")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        dv, cid, tid, sid_splash = _drive_moved(rpc, rid, board)
        if cid is None:
            pytest.skip("drive/position/legalite infaisable")

        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if snap is None or not _ok(s0):
            pytest.skip("combatSnapshot/dumpRng indispo")

        def mkstate():
            st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
            ce = st.get_entity(cid)
            fc = ce.get_component(UnitFlagsComponent)
            if fc is None:
                fc = UnitFlagsComponent(); ce.add_component(fc)
            fc.add(UnitFlagsComponent.MOVED)                # le caster LIVE a bouge -> seed le flag (load_state ne le capte pas)
            return st

        st0 = mkstate()
        cc = int(getattr(st0.get_entity(cid).get_component(StatsComponent).ctx, "crit_chance", 0) or 0)
        # #933 -- PREMISSE DE MONTAGE, plus un skip (cf. `_build` : `--crit 0,0`).
        assert cc == 0, (
            f"crit_chance={cc} != 0 : le bit-exact requiert cc=0, et le levier `--crit 0,0` du "
            f"build ne mord plus (regime BiS, cf. #933)")
        # branche A BOUGE de `GetHits` = `ConfigConst(0x2f)` SEUL -> l'attendu est `constants.nrOfHits`
        # (oracle gameconfig), pas un 2 ecrit en dur.
        cfg_hits = int(_cfg_constants()["nrOfHits"])
        off_hits = _harvester_hits(st0, cid)
        assert off_hits == cfg_hits, (
            f"cas A BOUGE : hits {off_hits} != constants.nrOfHits={cfg_hits} (oracle gameconfig, flag Moved "
            f"seede -> branche then de If(HasFlag(Moved)))")

        # --- LIVE cast ---
        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ABILITY},
            "captureEvents": True}, 120)
        assert _ok(cast), f"cast HarvesterOfSouls non applique: {str(cast)[:200]}"
        live = _live_dmg_by_target(cast)
        live_main = live.get(tid) or []
        live_splash = live.get(sid_splash) or []
        if not live_main:
            pytest.skip(f"aucun degat live Harvester (cast no-op ; targets live={sorted(live)})")
        assert len(live_main) == off_hits, f"coups main live {len(live_main)} != hits(moved) {off_hits}"

        # --- port offline (arbre DSL) meme rng ---
        st_tree = mkstate(); st_tree.rng = _mk_rng(s0)
        res = HarvesterOfSoulsAbility().execute_behaviour(st_tree, cid, tid)
        assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
        assert res.get("hits") == off_hits, f"port hits {res.get('hits')} != {off_hits} (moved)"
        tree_main = (res.get("main_attack") or {}).get("per_hit") or []
        splash_list = res.get("splash") or []
        tree_splash_ids = [x["target"] for x in splash_list]
        tree_splash = (splash_list[0]["attack"].get("per_hit") if splash_list else []) or []

        # (a) bit-exact vs LIVE (main + splash)
        assert tree_main == live_main, \
            f"arbre MAIN {tree_main} != LIVE {live_main} (bit-exact cc=0, native_factory attack)"
        assert tree_splash_ids == [sid_splash], \
            f"splash targets {tree_splash_ids} != [{sid_splash}] (ennemi adjacent-cible dans rayon caster)"
        assert tree_splash == live_splash, \
            f"arbre SPLASH {tree_splash} != LIVE {live_splash} (bit-exact splash MinMaxDamage2 HeavyRound)"

        # (c) A/B : arbre == sequences directes execute_ability_attack (main puis splash, meme rng)
        st_dir = mkstate(); st_dir.rng = _mk_rng(s0)
        bmin, bmax, pierce, _h = ability_attack_params(st_dir, cid, ABILITY_ID, PROFILE, ranged=True)
        d_main = (AttackDamageOperation.execute_ability_attack(
            st_dir, cid, tid, bmin, bmax, pierce, off_hits,
            damage_profile=PROFILE, is_melee=False, is_attack_damage_op=True) or {}).get("per_hit")
        bmin2, bmax2, pierce2, _h2 = ability_attack_params(
            st_dir, cid, ABILITY_ID, PROFILE, ranged=True, min_key="minDmg_2", max_key="maxDmg_2")
        d_splash = (AttackDamageOperation.execute_ability_attack(
            st_dir, cid, sid_splash, bmin2, bmax2, pierce2, off_hits,
            damage_profile=PROFILE, is_melee=False, is_attack_damage_op=True) or {}).get("per_hit")
        assert tree_main == d_main, f"arbre MAIN {tree_main} != sequence directe {d_main} (feuille/pipeline)"
        assert tree_splash == d_splash, f"arbre SPLASH {tree_splash} != sequence directe {d_splash}"
        # PERCAGE = valeur BRUTE (`StaticBattleRules.Damage$$GetPiercingRatio` lit
        # `DamageProfile.PiercingDamageRatio` tel quel) -> oracle = CONFIG, via `damage_profile_pierce`
        # qui ECHOUE sur cle absente. Le NOM du profil, lui, est un fait de STRUCTURE :
        # `HarvesterOfSoulsAbility$$ExecuteBehaviour` passe un litteral `Nullable<DamageProfileType>(0x13
        # = HeavyRound)` a `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` -- il n'appelle PAS
        # `AbilityConfiguration$$GetDamageProfile`, donc aucune constante damageProfile a lire ici.
        # Le percage EFFECTIF etant `clamp(0,100, ratio + ExtraPierce + ExtraPierceRanged)` -- et
        # HeavyRound ne saturant PAS a 100 --, on exige d'abord des ExtraPierce nuls : sinon l'egalite
        # testerait la SOMME et non le PROFIL (ces deux assertions verifient que les DEUX volets portent
        # bien HeavyRound).
        pierce_cfg = damage_profile_pierce(PROFILE)
        _ctx = st_dir.get_entity(cid).get_component(StatsComponent).ctx
        assert (_ctx.extra_pierce, _ctx.extra_pierce_ranged) == (0, 0), (
            f"caster avec percage supplementaire ({_ctx.extra_pierce}/{_ctx.extra_pierce_ranged}) : le "
            f"percage effectif n'est plus l'identite du PiercingRatio -- adapter le setup ou l'attendu")
        assert pierce == pierce_cfg and pierce2 == pierce_cfg, (
            f"pierce {pierce}/{pierce2} != damageProfiles.{PROFILE}.PiercingRatio={pierce_cfg} "
            f"(oracle gameconfig ; profil = Nullable(0x13) litteral du decompile)")

        # (d) native_factory discriminant : "ability" (1 tirage/coup) DIVERGE du live des le coup >=2
        st_ab = mkstate(); st_ab.rng = _mk_rng(s0)
        off_ability = (AttackDamageOperation.execute_ability_attack(
            st_ab, cid, tid, bmin, bmax, pierce, off_hits,
            damage_profile=PROFILE, is_melee=False, is_attack_damage_op=False) or {}).get("per_hit")
        assert off_ability != live_main, \
            (f"modele 'ability' {off_ability} == LIVE {live_main} : le discriminant native_factory ne separe "
             f"pas les familles (attendu: 'ability' desync des le coup 2)")
        print(f"[harv live seed={seed}] MOVED hits={off_hits} cc=0 | MAIN live={live_main}==tree "
              f"| SPLASH live={live_splash}==tree")
        print(f"[harv live seed={seed}] A/B arbre==directes ; native_factory attack DISCRIMINE (ability={off_ability})")
    finally:
        _cleanup(rpc, rid, state_file)


# ------------------------------------------------------------------ (e)+(f) HITS + SPLASH geometrie (offline, drive)

def _find_vis(state, vis):
    from engine.runner.components import UnitComponent
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.alive and uc.visual_id == vis:
            return uid
    return None


def _enemies_of(state, uid):
    from engine.runner.components import UnitComponent, OwnerComponent
    oc = state.get_entity(uid).get_component(OwnerComponent)
    out = []
    for oid, e in state.entities.items():
        u = e.get_component(UnitComponent); o = e.get_component(OwnerComponent)
        if u and o and u.alive and o.team != oc.team:
            out.append(oid)
    return sorted(out)


def _setpos(state, uid, c):
    from engine.runner.components import PositionComponent
    pc = state.get_entity(uid).get_component(PositionComponent)
    pc.col, pc.row = int(c[0]), int(c[1])


def _set_moved(state, uid, moved: bool):
    from engine.runner.components import UnitFlagsComponent
    e = state.get_entity(uid)
    fc = e.get_component(UnitFlagsComponent)
    if fc is None:
        fc = UnitFlagsComponent(); e.add_component(fc)
    (fc.add if moved else fc.remove)(UnitFlagsComponent.MOVED)


def _find_splash_geom(board, r):
    """(C, T, E1, E2, E3) marchables distincts : dist(C,T)=r ; E1 voisin de T avec dist(E1,C)<=r (splash) ;
    E2 voisin de T avec dist(E2,C)>r (adjacent-cible HORS rayon caster -> pruning A) ; E3 avec dist(E3,C)<=r
    et dist(E3,T)>=2 (dans rayon caster, NON adjacent-cible -> pruning B)."""
    coords = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]

    def nbrs(c):
        return [d for d in coords if hexgeo.distance(c, d) == 1]
    for C in coords:
        for T in coords:
            if hexgeo.distance(C, T) != r:
                continue
            tn = nbrs(T)
            E1 = next((e for e in tn if e != C and 1 <= hexgeo.distance(e, C) <= r), None)
            E2 = next((e for e in tn if e != C and hexgeo.distance(e, C) > r), None)
            E3 = next((e for e in coords if e not in (C, T, E1, E2)
                       and hexgeo.distance(e, C) <= r and hexgeo.distance(e, T) >= 2), None)
            if E1 and E2 and E3:
                return C, T, E1, E2, E3
    return None


def test_harvester_offline_hits_and_splash_geometry(live_session, rpc, monkeypatch):
    """(f) HITS, formule `If(HasFlag(Moved), ConfigConst(nrOfHits), Sum(nrOfHits, extraHit))` : A BOUGE ->
    `nrOfHits` ; PAS BOUGE -> `nrOfHits + extraHit`. (e) SPLASH geometrie (rayon = `constants.range`), drivee
    OFFLINE depuis un etat LIVE reel (deterministe) :
      [HIT]     ennemi adjacent-cible ET <= `range` hex du caster -> touche.
      [PRUNE-A] ennemi adjacent-cible mais HORS rayon-caster (dist > `range`) -> NON touche.
      [PRUNE-B] ennemi dans le rayon-caster mais NON adjacent-cible (dist>=2) -> NON touche.
      [EXCL]    la cible principale n'est jamais dans le splash.

    ORACLE (cf. en-tete) : les DEUX branches de la formule sont derivees de la config, jamais ecrites en
    dur -- et on exige d'abord `extraHit > 0`, sans quoi les deux branches rendraient le MEME nombre et le
    test serait INCAPABLE d'echouer sur un port qui ignorerait le flag Moved."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.abilities.aeldari import HarvesterOfSoulsAbility, _harvester_hits

    rid, state_file = _build("777")
    if rid is None:
        pytest.skip("build runner KO (rl_duel)")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if snap is None or not _ok(s0):
            pytest.skip("combatSnapshot/dumpRng indispo")

        def mkstate():
            st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
            st.rng = _mk_rng(s0)                            # rng cale -> les feuilles emettent un per_hit
            return st

        cid = _find_vis(mkstate(), CASTER_VIS)
        ens = _enemies_of(mkstate(), cid)
        if cid is None or len(ens) < 3:
            pytest.skip("caster + 3 ennemis requis")
        tid, a, b = ens[0], ens[1], ens[2]

        range_r = _cfg_range()                              # constants.range (0x16) -- pilote la geometrie
        geom = _find_splash_geom(board, range_r)
        if geom is None:
            pytest.skip(f"geometrie splash discriminante (rayon {range_r}) indispo sur ce board")
        C, T, E1, E2, E3 = geom

        # (f) HITS : les DEUX attendus viennent de la config (oracle), pas de 2/3 en dur.
        cst = _cfg_constants()
        n_hits, extra_hit = int(cst["nrOfHits"]), int(cst["extraHit"])
        assert extra_hit > 0, (
            f"constants.extraHit={extra_hit} : les deux branches de If(HasFlag(Moved)) rendraient le MEME "
            f"nombre -- ce test ne pourrait plus distinguer un port qui IGNORE le flag Moved")
        st = mkstate(); _set_moved(st, cid, False)
        assert _harvester_hits(st, cid) == n_hits + extra_hit, (
            f"PAS BOUGE : hits != constants.nrOfHits + constants.extraHit ({n_hits}+{extra_hit}) "
            f"(oracle gameconfig, branche else de If(HasFlag(Moved)))")
        _set_moved(st, cid, True)
        assert _harvester_hits(st, cid) == n_hits, (
            f"A BOUGE : hits != constants.nrOfHits={n_hits} (oracle gameconfig, branche then)")

        # [HIT] + [PRUNE-A] : E1 adjacent-cible dans rayon -> touche ; E2 adjacent-cible hors rayon -> exclu
        st = mkstate(); _set_moved(st, cid, True)
        _setpos(st, cid, C); _setpos(st, tid, T); _setpos(st, a, E1); _setpos(st, b, E2)
        res = HarvesterOfSoulsAbility().execute_behaviour(st, cid, tid)
        sp = sorted(x["target"] for x in (res.get("splash") or []))
        assert sp == [a], f"[HIT/PRUNE-A] splash {sp} != [{a}] (E1 dans rayon touche ; E2 hors rayon exclu)"
        assert tid not in sp, "[EXCL] la cible principale est dans le splash a tort"

        # [PRUNE-B] : E3 dans le rayon mais NON adjacent-cible -> exclu (seul E1 reste)
        st = mkstate(); _set_moved(st, cid, True)
        _setpos(st, cid, C); _setpos(st, tid, T); _setpos(st, a, E1); _setpos(st, b, E3)
        res = HarvesterOfSoulsAbility().execute_behaviour(st, cid, tid)
        sp = sorted(x["target"] for x in (res.get("splash") or []))
        assert sp == [a], f"[PRUNE-B] splash {sp} != [{a}] (E3 dans rayon mais non adjacent-cible exclu)"

        # splash utilise les MEMES coups que le main (hits = nrOfHits, caster moved) et un per-hit non vide
        assert (res.get("splash") or [])[0]["attack"].get("per_hit"), "[SPLASH] aucun coup emis"

        # [DERIVE-RANGE] la portee du splash doit DERIVER de `constants.range`, pas de la valeur de repli du
        # lecteur -- qui vaut justement 3 dans le port (`ability_var(...) or 3`) : une cle mal nommee rendrait
        # 3 elle aussi et passerait inapercue (piege " repli de meme valeur ", #96). On DECALE l'oracle a
        # range+1 et on exige que la FRONTIERE bouge : E2 (adjacent-cible, a exactement range+1 du caster,
        # exclu ci-dessus par le pruning A) doit desormais ETRE touche.
        import gameconfig as GC
        orig_ability = GC.ability
        patched = dict(orig_ability(ABILITY_ID) or {})
        patched["constants"] = {**cst, "range": str(range_r + 1)}
        monkeypatch.setattr(GC, "ability",
                            lambda aid: patched if aid == ABILITY_ID else orig_ability(aid))
        st = mkstate(); _set_moved(st, cid, True)
        _setpos(st, cid, C); _setpos(st, tid, T); _setpos(st, a, E1); _setpos(st, b, E2)
        res = HarvesterOfSoulsAbility().execute_behaviour(st, cid, tid)
        sp = sorted(x["target"] for x in (res.get("splash") or []))
        assert sp == sorted([a, b]), (
            f"[DERIVE-RANGE] splash {sp} != {sorted([a, b])} avec range={range_r + 1} : la portee du splash "
            f"ne DERIVE pas de constants.range (cle mal nommee retombant sur le repli, ou rayon fige)")
        print(f"[harv offline] HITS moved={n_hits}/notmoved={n_hits + extra_hit} (oracle config) OK ; "
              f"SPLASH rayon={range_r} HIT/PRUNE-A(rayon)/PRUNE-B(adjacence)/EXCL(cible) OK ; "
              f"DERIVE-RANGE {range_r}->{range_r + 1} OK")
    finally:
        _cleanup(rpc, rid, state_file)
