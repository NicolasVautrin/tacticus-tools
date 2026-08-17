"""PlasmaCannon (actif 1150, darkaTerminator « DarkAngels ») PORT -> arbre DSL, confronte au LIVE.

`PlasmaCannonAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour` (DECOMPILE, mirror 1:1 -- cf. `abilities/darkangels.py`) =
    ExecuteAtomic( op_BitwiseAnd(
        AttackWithAttackDamage(caster, target, MinMaxDamage, Plasma, nrOfHits=GetHits(0)=0x2f),          # MAIN
        AttackWithAttackDamage(caster, PickRandomly(UnitsDirectlyBehind(caster,target), 2), MEME
                               MinMaxDamage, Plasma, nrOfHits(MEME)) ), 0x2a )                            # SPLASH <=2
FINDINGS DECOMPILE (VA citees dans darkangels.py) :
  - factory native = `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` -> native_factory="attack" (2 tirages/coup a cc=0),
    CLASSIFIE PAR XREFS (call-sites IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour+0x1eb/IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour+0x2a6 -> IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage ; PlasmaCannon ABSENT des xrefs de
    IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage ability). CONTRASTE le template PlasmaGrenade "ability". Piege rngcrit-1202 / tip #2.
  - splash = `PickRandomly(UnitsDirectlyBehind(target), 2)` : jusqu'a 2 unites ennemies DIRECTEMENT DERRIERE
    la cible (anneau R1, cote oppose au caster), meme plage/hits que la principale. CONTRASTE PlasmaGrenade
    (splash = ennemis ADJACENTS a la cible, tous cotes).

CONFRONTATION LIVE (state-file UNIQUE ; doctrine drive-positions : `applyAction move` ignore portee/propriete,
`applyAction ability` EXIGE un cast legal -> on drive la geometrie puis on verifie `fromHere`). darkaTerminator
DEEP-STRIKE (TeleportStrike) -> on la fait ATTERRIR (endturn) AVANT de caster. Board plat (--board MC1_67),
armure des cibles a 0 (--hp-target) pour isoler le degat.

CE QUE LE TEST VALIDE (perimetre du PORT) :
  (A) A/B BIT-EXACT (deterministe) : l'arbre `plasma_cannon_tree` (main) == une sequence DIRECTE
      `execute_ability_attack(Plasma, nrOfHits, [minDmg,maxDmg], native_factory=attack)` sous le MEME rng
      seede -> prouve que la FEUILLE lit la bonne config/profil/factory (structure fidele, isole du pipeline).
  (B) TARGETING LIVE : le splash frappe EXACTEMENT les unites directly-behind (== `UnitsDirectlyBehind`
      offline), `nrOfHits` coups par cible, main comprise. La fidelite du selecteur (directly-behind, non
      adjacent-all comme PlasmaGrenade) = `UnitsDirectlyBehind offline == {les 2 unites drivees}` + geometrie
      STRICTE (2 unites a d=3 > d_ct=2, cote oppose au caster ; toute autre unite parquee LOIN).
  (C) native_factory="attack" LIVE : sur la cible MAIN (rng SYNCHRONISE, avant le PickRandomly), le ratio
      live/offline est CONSTANT per-coup en famille "attack" (2 tirages/coup) et NON-CONSTANT en famille
      "ability" (1 tirage/coup, desync des le coup 2). C'est le discriminant rngcrit-1202/tip #2, confronte live.

CONFONDS DOCUMENTES (pipeline PARTAGE, HORS perimetre de ce port ; cf. rapport) :
  - la MAGNITUDE offline != live (facteur SCALAIRE constant, ex. x1.25 HeavyWeapon seul, x1.875 avec high-ground
    caster>cible) : `execute_ability_attack` ne passe PAS `is_ranged` a `attacker_modifiers` -> les buffs
    ranged du caster (HeavyWeapon_ExtraDmg gated IsRangedAttack, +/- high-ground) ne sont PAS appliques aux
    attaques d'ABILITY. Le ratio CONSTANT per-coup prouve que ce n'est PAS un desync rng (native_factory OK) mais
    un buff scalaire manquant. -> candidat suivi (partage, cross-cutting).
  - le SPLASH desync per-coup live/offline (ratio non constant) : le `PickRandomly` natif consomme du rng meme
    quand il pique tout (<=2), la ou `_pick_randomly_n` court-circuite (GAP #215, partage avec Fragstorm).
  => la confrontation de MAGNITUDE bit-exact du degat est CONFONDUE ; on valide la STRUCTURE (A/B), le
     TARGETING, le nb de coups, et native_factory (ratio-constant), PAS l'egalite de degat brute.

ORACLE DU NOMBRE DE COUPS (#96 -- aucun scalaire de gameplay fige). Le decompile TRANCHE : dans
`IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour`, les DEUX volets
(main ET splash) passent `IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits`
= `GetNumberConstant(cfg, 0x2f)` directement en argument de
`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` -- aucune formule, et
`IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant` n'est qu'un `GetStringConstant` +
`System.Int32.Parse`. Valeur BRUTE -> l'oracle est la CONFIG :
`gameconfig.ability("PlasmaCannon").constants.nrOfHits`. Cle non ambigue malgre la COLLISION DE VALEUR
avec `range` (les deux valent 3 aujourd'hui) : enum `AbilityConstantType` 0x2f=nrOfHits(47) vs
0x16=range(22) (cf. `engine/entities/formulas.py::ConfigConst`). Le nb de coups REELLEMENT applique, lui,
est CALCULE (`attack_hits_with_modifiers` : base + ExtraHits - reductions, plancher 1) : c'est donc le
LIVE qui l'arbitre, et on le confronte a l'oracle config (aucune reduction de coups dans ce setup).

Lit l'etat LIVE, aucune tuile/RVA hardcodee. ASCII only. Skip si build/geometrie/darkaTerminator indispo.
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
from engine.runner.abilities.darkangels import PlasmaCannonAbility
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.runner.abilities.base import ability_attack_params
from engine.runner.operations.damage import AttackDamageOperation
from engine.entities.selectors.units import UnitsDirectlyBehind

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                      # racine repo
CASTER_VIS = "darkaTerminator"
ABILITY = 1150
A_UNITS = "necroWarden,necroWarden,necroWarden,necroOverlord"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _caster(dv):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == CASTER_VIS and u.get("alive")), None)


def _spread(ratios):
    return (max(ratios) - min(ratios)) if ratios else 0.0


def _want_hits():
    """ORACLE : `constants.nrOfHits` de PlasmaCannon (lecture BRUTE cote natif, cf. en-tete)."""
    v = ((GC.ability("PlasmaCannon") or {}).get("constants") or {}).get("nrOfHits")
    assert v is not None, ("oracle introuvable : gameconfig.ability('PlasmaCannon').constants.nrOfHits "
                           "absent -- le natif le lit par GetNumberConstant(0x2f), il DOIT exister")
    return int(v)


def test_plasma_cannon_live(live_session, rpc):
    """Confronte le port PlasmaCannon au LIVE : A/B tree==pipeline (A), targeting directly-behind + discriminant
    front (B), native_factory=attack via ratio-constant sur la main (C). State-file UNIQUE -> dispose au teardown."""
    state_file = ROOT / "logs" / "runners" / f"plasmacannon-test-{uuid.uuid4().hex[:8]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777", "--state-file", str(state_file),
         "--board", "MC1_67", "--roster", "1", "--p-units", CASTER_VIS, "--a-units", A_UNITS,
         "--hp-target", "90000"],                            # armure a 0 + PV hauts (survivent aux coups) -> isole le degat
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        pytest.skip(f"build runner KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    rid = json.loads(state_file.read_text())["runnerId"]
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        tiles = bg["tiles"]
        elev = {(t["col"], t["row"]): t.get("elevation") for t in tiles}
        board = Board(tiles, adjacency="native_sym")

        def mv(uid, tid):
            c = board.coord(tid)
            return rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)

        # --- faire ATTERRIR le terminator (deep-strike) et revenir a mon tour ---
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        if not _ok(dv) or _caster(dv) is None:
            pytest.skip("darkaTerminator absent (pool/spawn)")
        myplayer = _caster(dv).get("owner")
        landed = False
        for _ in range(6):
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
            c = _caster(dv)
            if c is None:
                break
            tin = any("TeleportingIn" in (e.get("name") or "") for e in (c.get("effects") or []))
            if not tin and dv.get("currentPlayer") == myplayer:
                landed = True
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        if not landed:
            pytest.skip("terminator non atterri / tour non atteint")

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        caster = _caster(dv)
        cid = caster["id"]
        cpos = (caster["pos"]["col"], caster["pos"]["row"])
        ctile = board.id_at(*cpos)
        eC = elev.get(cpos)
        enemies = [u for u in (dv.get("units") or []) if u.get("owner") != myplayer and u.get("alive")]
        if len(enemies) < 3:
            pytest.skip("moins de 3 ennemis vivants (besoin cible + 2 derriere)")

        # park tous les ennemis LOIN (isole la geometrie)
        far = [t for t in sorted(board.by_id) if board.walkable(t)
               and hexgeo.distance(board.coord(t), cpos) > 6]
        if len(far) < len(enemies):
            pytest.skip("pas assez de tuiles lointaines pour parquer")
        for e, ft in zip(enemies, far):
            mv(e["id"], ft)

        # --- geometrie : cible T a d=2 du caster (stationnaire) ; 2 unites STRICTEMENT derriere (d=3, meme
        #     elevation +-1) ; le cast doit etre LEGAL (fromHere). d strict > d_ct -> offline (>=) ET live
        #     s'accordent sans ambiguite (pas d'unite laterale a distance egale, cf. rapport). ---
        cand = None
        for T in sorted(board.by_id):
            ct = board.coord(T)
            if not board.walkable(T) or T == ctile or hexgeo.distance(ct, cpos) != 2:
                continue
            if elev.get(ct) is None or eC is None or abs(elev.get(ct) - eC) > 1:
                continue
            nbrs = [n for n in board.neighbours(T) if board.walkable(n) and n != ctile]
            behind = [n for n in nbrs if hexgeo.distance(board.coord(n), cpos) == 3
                      and elev.get(board.coord(n)) is not None
                      and abs(elev.get(board.coord(n)) - elev.get(ct)) <= 1]
            if len(behind) >= 2:
                mv(enemies[0]["id"], T)
                at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
                fh = [x.get("targetId") for x in
                      next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                            if a.get("abilityId") == ABILITY), {}).get("fromHere") or []]
                if enemies[0]["id"] in fh:
                    cand = (T, behind[:2])
                    break
                mv(enemies[0]["id"], far[0])
        if cand is None:
            pytest.skip("aucune geometrie directly-behind LEGALE (board/elevation)")
        T, behind = cand
        # DISCRIMINANT directly-behind vs adjacent-all : SEULES 2 unites sont adjacentes a la cible (les 2
        # derriere) ; tout autre ennemi est parque LOIN (d>6). Donc le splash ne peut frapper QUE des unites
        # derriere -> si le port frappait adjacent-all (PlasmaGrenade), il ne toucherait de toute facon que
        # ces 2 (aucune autre adjacente). La FIDELITE du selecteur (directly-behind, exclut les lateraux a
        # distance egale) est verifiee par `UnitsDirectlyBehind offline == {b1,b2}` + geometrie STRICTE (d=3>d_ct=2).
        target, b1, b2 = enemies[0], enemies[1], enemies[2]
        mv(b1["id"], behind[0]); mv(b2["id"], behind[1])

        # re-check legalite APRES tous les placements (les unites derriere ne bloquent pas la LOS caster->cible ;
        # defensif si un placement changeait la donne)
        at2 = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
        fh2 = [x.get("targetId") for x in
               next((a for a in ((at2.get("units") or [{}])[0].get("abilities") or [])
                     if a.get("abilityId") == ABILITY), {}).get("fromHere") or []]
        if target["id"] not in fh2:
            pytest.skip("cast devenu illegal apres placement des unites derriere (LOS)")

        # --- capture post-drive + seed rng juste avant le cast ---
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        st = load_state(dv2, ob2, snap2, board=board)
        ent = entities_from_state(st, cid, target["id"])
        udb = sorted(x.get("id") for x in UnitsDirectlyBehind().select(ent))
        assert set(udb) == {b1["id"], b2["id"]}, \
            f"UnitsDirectlyBehind offline {udb} != les 2 unites drivees derriere {sorted([b1['id'], b2['id']])}"
        bmin, bmax, pierce, hits = ability_attack_params(st, cid, "PlasmaCannon", "Plasma", ranged=True)
        want_hits = _want_hits()
        assert hits == want_hits, (
            f"nrOfHits lu {hits} != oracle config {want_hits} (constants.nrOfHits) -- le port ne lit pas "
            f"la CONSTANTE d'ability (0x2f) mais autre chose (variable per-niveau scalee ? mauvaise cle ?)")
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not _ok(s0):
            pytest.skip("dumpRng KO")

        # ============ LIVE cast ============
        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": target["id"], "abilityType": ABILITY},
            "captureEvents": True}, 120)
        assert _ok(cast), f"cast PlasmaCannon non applique: {str(cast)[:200]}"
        live = {}
        for act in (cast.get("actions") or []):
            for e in (act.get("events") or []):
                td = e.get("tags")
                if not td:
                    continue
                td = json.loads(td) if isinstance(td, str) else td
                if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                    live.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
        live_main = live.get(target["id"])
        assert live_main, f"aucun degat live sur la cible principale (by_target={sorted(live)})"

        # (B) TARGETING : main + EXACTEMENT les 2 unites directly-behind ; 3 coups chacune.
        assert set(live.keys()) == {target["id"], b1["id"], b2["id"]}, (
            f"cibles splash live {sorted(live)} != main+directly-behind "
            f"{sorted([target['id'], b1['id'], b2['id']])}")
        for tid, ph in live.items():
            assert len(ph) == want_hits, (
                f"cible {tid} : {len(ph)} coups LIVE != oracle config nrOfHits={want_hits}. Le nb applique "
                f"est CALCULE (base - reductions, plancher 1) : soit une reduction de coups s'applique "
                f"dans ce setup (le port doit alors la modeliser), soit les DEUX volets ne lisent plus la "
                f"meme constante (le natif passe ArmoriumCherubAbility$$GetHits aux deux)")

        # (A) A/B : arbre (main) == sequence directe execute_ability_attack, BIT-EXACT sous le meme rng seede.
        st_tree = load_state(dv2, ob2, snap2, board=board); st_tree.rng = _seed_rng(s0)
        res = PlasmaCannonAbility().execute_behaviour(st_tree, cid, target["id"])
        assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
        tree_main = (res.get("main_attack") or {}).get("per_hit")
        tree_splash_ids = sorted(s["target"] for s in (res.get("splash") or []))
        assert tree_splash_ids == sorted([b1["id"], b2["id"]]), \
            f"splash offline {tree_splash_ids} != directly-behind {sorted([b1['id'], b2['id']])}"
        st_dir = load_state(dv2, ob2, snap2, board=board); st_dir.rng = _seed_rng(s0)
        direct = AttackDamageOperation.execute_ability_attack(
            st_dir, cid, target["id"], bmin, bmax, pierce, hits,
            damage_profile="Plasma", is_melee=False, is_attack_damage_op=True)   # native_factory="attack"
        assert tree_main == (direct or {}).get("per_hit"), (
            f"arbre main per_hit {tree_main} != sequence directe execute_ability_attack "
            f"{(direct or {}).get('per_hit')} (la feuille n'appelle pas le pipeline fidele)")

        # (C) native_factory : sur la MAIN (rng synchronise), ratio live/offline CONSTANT en famille "attack"
        #     (2 tirages/coup), NON-CONSTANT en famille "ability" (1 tirage/coup -> desync des le coup 2).
        st_ab = load_state(dv2, ob2, snap2, board=board); st_ab.rng = _seed_rng(s0)
        off_ability = (AttackDamageOperation.execute_ability_attack(
            st_ab, cid, target["id"], bmin, bmax, pierce, hits,
            damage_profile="Plasma", is_melee=False, is_attack_damage_op=False) or {}).get("per_hit")   # "ability"
        assert len(live_main) == want_hits and len(tree_main) == want_hits \
            and len(off_ability) == want_hits, (
            f"comparaison per-coup impossible : live={len(live_main)} tree={len(tree_main)} "
            f"ability={len(off_ability)} coups, oracle config nrOfHits={want_hits}")
        r_attack = [lm / om for lm, om in zip(live_main, tree_main)]
        r_ability = [lm / om for lm, om in zip(live_main, off_ability)]
        # attack-family : ratio constant (buff scalaire, rng synced) ; ability-family : desync -> spread large.
        assert _spread(r_attack) < 0.01, (
            f"native_factory=attack : ratio live/offline NON constant {r_attack} (spread {_spread(r_attack):.4f}) "
            f"-> desync rng inattendu (la main devrait etre rng-synced)")
        assert _spread(r_ability) > 0.02, (
            f"native_factory=ability NE desynchronise PAS ({r_ability}, spread {_spread(r_ability):.4f}) -> le "
            f"discriminant rngcrit-1202 ne separe pas les factories dans ce scenario (attendu: ability desync)")
        assert _spread(r_ability) > 5 * _spread(r_attack), (
            f"attack spread {_spread(r_attack):.4f} vs ability spread {_spread(r_ability):.4f} : la famille "
            f"'attack' n'est pas nettement plus stable -> native_factory non discrimine")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            state_file.unlink()
        except Exception:
            pass
