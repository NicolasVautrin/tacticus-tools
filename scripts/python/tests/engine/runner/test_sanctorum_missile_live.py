"""SanctorumMissile (actif 1062, adeptMorvenn = Morvenn Vahl, Sisterhood) PORT -> arbre DSL 2-bandes,
confronte au LIVE.

`SanctorumMissileAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour` (DECOMPILE, mirror 1:1 -- cf. `abilities/sisterhood.py`) =
    ExecuteAtomic( op_BitwiseAnd(
        AttackWithAttackDamage(caster, target, MinMaxDamage, Blast, nrOfHits=GetNumberConstant(0x2f)=2),    # MAIN
        AttackWithAttackDamage(caster, GetAdjacentDamageTargetsAll(), MEME MinMaxDamage, Blast,
                               nrOfHits_2=GetNumberConstant(0x32)=1) ), 0x56 )                                # SPLASH
avec `IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$GetAdjacentDamageTargetsAll` =
    Unobscured( self, ( Units(AdjacentTiles(target)) - caster ) + EmptyOrHasSteppableUnit(AdjacentTiles(target)) )

FINDINGS DECOMPILE (VA citees dans sisterhood.py) :
  - factory native = `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` -> native_factory="attack" (2 tirages/coup a cc=0),
    CLASSIFIE PAR XREFS (call-sites IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour+0x15f/IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour+0x1ff -> IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage ; SanctorumMissile ABSENT des xrefs de
    la famille ability -- ses enveloppes comme son COEUR
    `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage(abilityOrEffect, options:IdunBattle.Entities.Behaviours.AbilityDamageBehaviourOptions)`
    ; #1032-r5, cette ligne disait `X/X`). Piege rngcrit-1202 / tip #2.
  - splash = unites ADJACENTES a la cible (AUCUN filtre d'equipe = FRIENDLY-FIRE, band UNIT `Units(AdjacentTiles(
    target))`) MOINS le CASTER (hex de Morvenn EXCLU), Unobscured depuis le caster. Band TILE EmptyOrHasSteppable
    (tuiles vides/steppables) NON porte -- inerte pour le degat-unite (le frere natif GetAdjacentDamageTargetsUnits
    = Units(All) re-resout aux occupants). Config : nrOfHits=2 (cible), nrOfHits_2=1 (splash), profil Blast, range 3.

CONFRONTATION LIVE (state-file UNIQUE ; doctrine drive-positions : `applyAction move` ignore portee/propriete,
`applyAction ability` EXIGE un cast legal -> on drive la geometrie puis on verifie `fromHere`). Board plat
(--board MC1_67), armure de la cible a 0 (--hp-target) pour isoler le degat de la MAIN.

CE QUE LE TEST VALIDE (perimetre du PORT) :
  (A) A/B BIT-EXACT (deterministe) : l'arbre `sanctorum_missile_tree` (main ET splash) == des sequences DIRECTES
      `execute_ability_attack(Blast, nrOfHits/nrOfHits_2, [minDmg,maxDmg], native_factory=attack)` sous le MEME
      rng seede -> prouve que les feuilles lisent la bonne config/profil/factory/cle-de-coups (structure fidele).
  (B) TARGETING LIVE : la MAIN frappe la cible 2x (nrOfHits) ; le SPLASH frappe EXACTEMENT les unites adjacentes
      a la cible MOINS Morvenn (== `Sub(AdjacentUnits(TargetTile()), Caster())` offline), 1x (nrOfHits_2) chacune.
      Inclut l'ALLIE adjacent (friendly-fire, band UNIT no-team-filter) et EXCLUT Morvenn meme adjacente (hex du
      caster). Tout autre unite parquee LOIN.
  (C) native_factory="attack" LIVE : sur la cible MAIN (rng SYNCHRONISE), le ratio live/offline est CONSTANT
      per-coup en famille "attack" (2 tirages/coup) et NON-CONSTANT en famille "ability" (1 tirage/coup, desync
      des le coup 2). Discriminant rngcrit-1202/tip #2, confronte live sur 2 seeds (tip #7).

CONFOND DOCUMENTE (pipeline PARTAGE, HORS perimetre de ce port) : la MAGNITUDE offline peut != live par un
facteur SCALAIRE constant (buff ranged du caster non applique aux attaques d'ability, cf. PlasmaCannon). Le ratio
CONSTANT per-coup prouve que ce n'est PAS un desync rng (native_factory OK). On valide STRUCTURE (A/B),
TARGETING, nb de coups, native_factory (ratio-constant), PAS l'egalite de degat brute.

ORACLE DU NOMBRE DE COUPS (#96 -- aucun scalaire de gameplay fige). Le decompile TRANCHE : dans
`IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour`, les deux
`GetNumberConstant(cfg, 0x2f)` / `GetNumberConstant(cfg, 0x32)` partent DIRECTEMENT en argument des deux
`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (main / splash) -- aucune formule, et
`IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant` n'est qu'un `GetStringConstant` +
`System.Int32.Parse`. Valeurs BRUTES -> l'oracle est la CONFIG :
`gameconfig.ability("SanctorumMissile").constants.nrOfHits` / `.nrOfHits_2`. C'est CETTE ability qui LEVE
l'ambiguite de cle a elle seule : nrOfHits(0x2f)=2 et nrOfHits_2(0x32)=1 ont des valeurs DIFFERENTES et le
LIVE les separe (2 coups sur la main, 1 sur chaque splash) -- un port qui lirait la mauvaise cle rougirait.
Le nb de coups REELLEMENT applique, lui, est CALCULE (`attack_hits_with_modifiers` : base + ExtraHits -
reductions, plancher 1) : c'est le LIVE qui l'arbitre, et on le confronte a l'oracle config (aucune
reduction de coups dans ce setup).

Lit l'etat LIVE, aucune tuile/RVA hardcodee. ASCII only. Skip si build/geometrie/adeptMorvenn indispo.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import gameconfig as GC
import hexgeo
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.abilities.sisterhood import SanctorumMissileAbility
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.runner.abilities.base import ability_attack_params
from engine.runner.operations.damage import AttackDamageOperation
from engine.entities.selectors.accessors import TargetTile
from engine.entities.selectors.tiles import Caster
from engine.entities.selectors.units import AdjacentUnits, Sub, Unobscured

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                     # racine repo
CASTER_VIS = "adeptMorvenn"
ALLY_VIS = "adeptCanoness"
ABILITY = 1062
P_UNITS = "adeptMorvenn,adeptCanoness"
A_UNITS = "necroWarden,necroWarden,necroWarden,necroOverlord"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _byvis(dv, vis, alive=True):
    return [u for u in (dv.get("units") or []) if u.get("visualId") == vis and (u.get("alive") or not alive)]


def _spread(ratios):
    return (max(ratios) - min(ratios)) if ratios else 0.0


def _const(key):
    """ORACLE : constante de config d'ability SanctorumMissile (`GetNumberConstant`, lecture BRUTE cote
    natif -- cf. en-tete). Fail explicite si la cle a disparu de la config."""
    v = ((GC.ability("SanctorumMissile") or {}).get("constants") or {}).get(key)
    assert v is not None, (f"oracle introuvable : gameconfig.ability('SanctorumMissile').constants.{key} "
                           f"absent -- le natif le lit par GetNumberConstant, il DOIT exister")
    return int(v)


def _fromhere(at, cid):
    """Ids cibles legaux de l'ability ABILITY depuis la position courante du caster cid."""
    us = at.get("units") or []
    u = next((x for x in us if x.get("unitId") == cid), (us[0] if us else {}))
    ab = next((a for a in (u.get("abilities") or []) if a.get("abilityId") == ABILITY), {})
    return [x.get("targetId") for x in (ab.get("fromHere") or [])]


def _build(seed, state_file):
    return subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(state_file),
         "--board", "MC1_67", "--roster", "1", "--p-units", P_UNITS, "--a-units", A_UNITS,
         "--hp-target", "90000"],                           # armure cible a 0 + PV hauts -> isole le degat MAIN
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")


def _drive_scene(rpc, rid, board):
    """Drive une geometrie SanctorumMissile : cible T (ennemi) ; splash = 2 ennemis + 1 allie (Canoness)
    adjacents a T ; Morvenn adjacente a T si le cast reste LEGAL (sinon a dist 2). Tout le reste parque LOIN.
    Rend (cid, target_id, expect_splash:set, morvenn_adjacent:bool) ou None si geometrie impossible."""
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    if not _ok(dv):
        return None
    mv_l = _byvis(dv, CASTER_VIS)
    ally_l = _byvis(dv, ALLY_VIS)
    if not mv_l or not ally_l:
        return None
    morvenn = mv_l[0]; ally = ally_l[0]
    myplayer = morvenn.get("owner")
    enemies = [u for u in (dv.get("units") or []) if u.get("owner") != myplayer and u.get("alive")]
    if len(enemies) < 3:
        return None

    def mv(uid, tid):
        c = board.coord(tid)
        return rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)

    walk = [t for t in sorted(board.by_id) if board.walkable(t)]
    # Cherche une tuile cible T (walkable) avec >=4 voisins walkable distincts (n1..n4) pour E2,E3,A1,Morvenn.
    for T in walk:
        nbrs = [n for n in board.neighbours(T) if board.walkable(n)]
        if len(nbrs) < 4:
            continue
        tc = board.coord(T)
        # tuiles LOIN pour parquer tout le monde (hors de la zone T + voisins)
        far = [t for t in walk if hexgeo.distance(board.coord(t), tc) > 6]
        allunits = (dv.get("units") or [])
        if len(far) < len(allunits):
            continue
        # 1) parque TOUT loin (evite toute contamination du splash)
        for u, ft in zip(allunits, far):
            mv(u["id"], ft)
        # 2) place cible + splash sur T et ses voisins
        target, e2, e3 = enemies[0], enemies[1], enemies[2]
        n1, n2, n3, n4 = nbrs[0], nbrs[1], nbrs[2], nbrs[3]
        mv(target["id"], T)
        mv(e2["id"], n1)
        mv(e3["id"], n2)
        mv(ally["id"], n3)
        # 3) Morvenn adjacente (n4) si cast legal ; sinon a dist 2 (cast garanti par range 3).
        mv(morvenn["id"], n4)
        cid = morvenn["id"]
        fh = _fromhere(rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90), cid)
        morvenn_adj = target["id"] in fh
        if not morvenn_adj:
            # recule Morvenn a dist 2 d'une tuile walkable non-voisine de T
            d2 = [t for t in walk if hexgeo.distance(board.coord(t), tc) == 2
                  and t not in nbrs and t != T]
            placed = False
            for t2 in d2:
                mv(cid, t2)
                fh = _fromhere(rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90), cid)
                if target["id"] in fh:
                    placed = True
                    break
            if not placed:
                continue
        # splash attendu = ennemis + allie adjacents a T, Morvenn EXCLUE (caster). Si Morvenn adjacente (n4),
        # elle est dans AdjacentUnits(T) brut mais retiree par Sub(caster) -> pas dans expect.
        expect = {e2["id"], e3["id"], ally["id"]}
        return cid, target["id"], expect, morvenn_adj
    return None


def _run_cast(rpc, rid, board, cid, target_id):
    """Capture etat + rng, cast LIVE, rend (live_by_target:dict[id]->[amounts], st_capture_args, s0)."""
    dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        return None
    cast = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": target_id, "abilityType": ABILITY},
        "captureEvents": True}, 120)
    if not _ok(cast):
        return None
    live = {}
    for act in (cast.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                live.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
    return live, (dv2, ob2, snap2), s0


def test_sanctorum_missile_targeting_and_ab(live_session, rpc):
    """(A) A/B bit-exact main+splash ; (B) targeting live = 2x cible + 1x chaque adjacent-cible (allie inclus,
    Morvenn exclue) == offline `Sub(AdjacentUnits(TargetTile()), Caster())`."""
    state_file = ROOT / "logs" / "runners" / f"sanctorum-tgt-{uuid.uuid4().hex[:8]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    proc = _build("777", state_file)
    if not state_file.exists():
        pytest.skip(f"build runner KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    rid = json.loads(state_file.read_text())["runnerId"]
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        scene = _drive_scene(rpc, rid, board)
        if scene is None:
            pytest.skip("geometrie SanctorumMissile impossible (unites/board)")
        cid, target_id, expect_splash, morvenn_adj = scene

        # capture post-drive AVANT cast (offline) : selecteur porte == splash attendu
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        st = load_state(dv2, ob2, snap2, board=board)
        ent = entities_from_state(st, cid, target_id)
        raw_adj = sorted(u.get("id") for u in AdjacentUnits(TargetTile()).select(ent))
        sub_sel = sorted(u.get("id") for u in Sub(AdjacentUnits(TargetTile()), Caster()).select(ent))
        unobsc = sorted(u.get("id") for u in
                        Unobscured(Sub(AdjacentUnits(TargetTile()), Caster()), Caster()).select(ent))
        assert set(sub_sel) == expect_splash, \
            f"selecteur porte Sub(AdjacentUnits,Caster) {sub_sel} != attendu {sorted(expect_splash)}"
        # board plat MC1_67 -> Unobscured passe-tout : le set porte == Sub
        assert set(unobsc) == set(sub_sel), \
            f"Unobscured a filtre sur board plat {unobsc} != {sub_sel} (inattendu)"
        if morvenn_adj:
            # caster-exclusion PROUVE : Morvenn est dans AdjacentUnits BRUT mais retiree par Sub(Caster)
            assert cid in raw_adj, f"Morvenn (caster) drivee adjacente mais absente d'AdjacentUnits brut {raw_adj}"
            assert cid not in sub_sel, f"Morvenn (caster) NON exclue par Sub(Caster) : {sub_sel}"

        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not _ok(s0):
            pytest.skip("dumpRng KO")

        # ============ LIVE cast ============
        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": target_id, "abilityType": ABILITY},
            "captureEvents": True}, 120)
        assert _ok(cast), f"cast SanctorumMissile non applique: {str(cast)[:200]}"
        live = {}
        for act in (cast.get("actions") or []):
            for e in (act.get("events") or []):
                td = e.get("tags")
                if not td:
                    continue
                td = json.loads(td) if isinstance(td, str) else td
                if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                    live.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
        assert live.get(target_id), f"aucun degat live sur la cible MAIN (by_target={sorted(live)})"

        # (B) TARGETING : cibles live == {cible} U splash-attendu (allie inclus friendly-fire, Morvenn exclue)
        assert set(live.keys()) == ({target_id} | expect_splash), (
            f"cibles live {sorted(live)} != main+splash attendu {sorted({target_id} | expect_splash)} "
            f"(morvenn_adj={morvenn_adj}, cid={cid})")
        want_hits, want_hits2 = _const("nrOfHits"), _const("nrOfHits_2")   # ORACLE config (cf. en-tete)
        assert len(live[target_id]) == want_hits, (
            f"cible MAIN : {len(live[target_id])} coups LIVE != oracle config nrOfHits={want_hits}. Le nb "
            f"applique est CALCULE (base - reductions, plancher 1) : soit une reduction de coups joue dans "
            f"ce setup (le port doit la modeliser), soit le volet MAIN ne lit plus 0x2f")
        for sid in expect_splash:
            assert len(live.get(sid) or []) == want_hits2, (
                f"splash {sid} : {len(live.get(sid) or [])} coups LIVE != oracle config "
                f"nrOfHits_2={want_hits2} (0x32) -- volet splash")

        # (A) A/B BIT-EXACT : arbre (main + splash) == sequences directes execute_ability_attack sous le meme rng.
        st_tree = load_state(dv2, ob2, snap2, board=board); st_tree.rng = _seed_rng(s0)
        res = SanctorumMissileAbility().execute_behaviour(st_tree, cid, target_id)
        assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
        tree_main = (res.get("main_attack") or {}).get("per_hit")
        tree_splash = {s["target"]: (s["attack"] or {}).get("per_hit") for s in (res.get("splash") or [])}
        assert set(tree_splash) == expect_splash, \
            f"splash offline {sorted(tree_splash)} != attendu {sorted(expect_splash)}"
        # sequence directe main (nrOfHits, attack-factory)
        bmin, bmax, pierce, hits = ability_attack_params(st_tree, cid, "SanctorumMissile", "Blast", ranged=True)
        assert hits == want_hits, (
            f"nrOfHits lu {hits} != oracle config {want_hits} (constants.nrOfHits) -- le port ne lit pas la "
            f"CONSTANTE d'ability (0x2f) mais autre chose (variable per-niveau scalee ? mauvaise cle ?)")
        _bmin2, _bmax2, _p2, hits2 = ability_attack_params(
            st_tree, cid, "SanctorumMissile", "Blast", ranged=True, hits_key="nrOfHits_2")
        assert hits2 == want_hits2, (
            f"nrOfHits_2 lu {hits2} != oracle config {want_hits2} (constants.nrOfHits_2, 0x32)")
        assert want_hits != want_hits2, (
            f"les DEUX cles valent {want_hits} : la confrontation live main/splash ne discrimine plus "
            f"nrOfHits(0x2f) de nrOfHits_2(0x32) -- un port qui lirait la mauvaise cle resterait vert")
        st_dir = load_state(dv2, ob2, snap2, board=board); st_dir.rng = _seed_rng(s0)
        direct_main = AttackDamageOperation.execute_ability_attack(
            st_dir, cid, target_id, bmin, bmax, pierce, hits,
            damage_profile="Blast", is_melee=False, is_attack_damage_op=True)   # native_factory="attack"
        assert tree_main == (direct_main or {}).get("per_hit"), (
            f"arbre main per_hit {tree_main} != sequence directe {(direct_main or {}).get('per_hit')} "
            f"(la feuille MAIN n'appelle pas le pipeline fidele)")
        # splash bit-exact : dans le MEME rng continue (apres la main), chaque cible splash triee par id.
        for sid in sorted(tree_splash):
            d = AttackDamageOperation.execute_ability_attack(
                st_dir, cid, sid, bmin, bmax, pierce, hits2,
                damage_profile="Blast", is_melee=False, is_attack_damage_op=True)
            assert tree_splash[sid] == (d or {}).get("per_hit"), (
                f"arbre splash {sid} per_hit {tree_splash[sid]} != sequence directe {(d or {}).get('per_hit')}")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            state_file.unlink()
        except Exception:
            pass


@pytest.mark.parametrize("seed", ["777", "31337"])
def test_sanctorum_missile_native_factory_attack(live_session, rpc, seed):
    """(C) native_factory="attack" : sur la MAIN (rng synchronise), ratio live/offline CONSTANT en famille
    "attack" (2 tirages/coup), NON-CONSTANT en famille "ability" (1 tirage/coup -> desync des le coup 2).
    Discriminant rngcrit-1202/tip #2, sur 2 seeds (tip #7)."""
    state_file = ROOT / "logs" / "runners" / f"sanctorum-fac-{seed}-{uuid.uuid4().hex[:8]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    proc = _build(seed, state_file)
    if not state_file.exists():
        pytest.skip(f"build runner KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    rid = json.loads(state_file.read_text())["runnerId"]
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        scene = _drive_scene(rpc, rid, board)
        if scene is None:
            pytest.skip("geometrie SanctorumMissile impossible")
        cid, target_id, _expect, _madj = scene
        out = _run_cast(rpc, rid, board, cid, target_id)
        if out is None:
            pytest.skip("cast/dumpRng KO")
        live, (dv2, ob2, snap2), s0 = out
        want_hits = _const("nrOfHits")                        # ORACLE config (cf. en-tete)
        live_main = live.get(target_id)
        assert live_main and len(live_main) == want_hits, \
            f"MAIN live {live_main} != oracle config nrOfHits={want_hits} coups"

        bmin, bmax, pierce, hits = ability_attack_params(
            load_state(dv2, ob2, snap2), cid, "SanctorumMissile", "Blast", ranged=True)
        st_at = load_state(dv2, ob2, snap2, board=board); st_at.rng = _seed_rng(s0)
        off_attack = (AttackDamageOperation.execute_ability_attack(
            st_at, cid, target_id, bmin, bmax, pierce, hits,
            damage_profile="Blast", is_melee=False, is_attack_damage_op=True) or {}).get("per_hit")   # "attack"
        st_ab = load_state(dv2, ob2, snap2, board=board); st_ab.rng = _seed_rng(s0)
        off_ability = (AttackDamageOperation.execute_ability_attack(
            st_ab, cid, target_id, bmin, bmax, pierce, hits,
            damage_profile="Blast", is_melee=False, is_attack_damage_op=False) or {}).get("per_hit")  # "ability"
        assert len(off_attack) == want_hits and len(off_ability) == want_hits, (
            f"comparaison per-coup impossible : attack={len(off_attack)} ability={len(off_ability)} "
            f"coups, oracle config nrOfHits={want_hits}")
        assert want_hits >= 2, (
            f"setup NON discriminant : nrOfHits={want_hits} -- le desync de la famille 'ability' "
            f"n'apparait qu'A PARTIR du 2e coup, un mono-coup rendrait le ratio trivialement constant "
            f"des deux cotes et l'assertion de spread ci-dessous incapable de rougir")
        r_attack = [lm / om for lm, om in zip(live_main, off_attack)]
        r_ability = [lm / om for lm, om in zip(live_main, off_ability)]
        # attack-family : ratio constant (buff scalaire eventuel, rng synced) ; ability-family : desync coup 2.
        assert _spread(r_attack) < 0.01, (
            f"native_factory=attack : ratio live/offline NON constant {r_attack} (spread {_spread(r_attack):.4f}) "
            f"-> desync rng inattendu (la main devrait etre rng-synced)")
        assert _spread(r_ability) > 5 * _spread(r_attack) + 0.02, (
            f"native_factory=ability NE desynchronise PAS ({r_ability}, spread {_spread(r_ability):.4f} vs "
            f"attack {_spread(r_attack):.4f}) -> discriminant rngcrit-1202 ne separe pas les factories")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            state_file.unlink()
        except Exception:
            pass
