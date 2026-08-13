"""#997 -- les DEUX no-op silencieuses dont le decompile CONFIRME la categorie DAMAGE, confrontees
au LIVE : `1170 ExplosivePresents` (`orksRedGobbo`) et `1176 BlightGrenades`
(`deathNpc2PlagueMarine`). Les quatre autres de la tranche (1215/1174/1094/1193) sont 2-PHASES et ne
sont PAS portees -- cf. `docs/rl/case-997-six-noop-la-categorie-annoncee-ment-4-fois-sur-6.md`.

Ce que chaque test ARBITRE, et pourquoi il ne peut pas rendre vert par accident :

1170 `ExplosivePresents` -- `IdunBattleLogic.Entities.Abilities.Active.Loki.ExplosivePresentsAbility$$ExecuteBehaviour`
     `AttackWithAbilityDamage(caster, (Target + AdjacentUnits(TargetTile)) - Caster, ...)`.
     Le caster est place ADJACENT a la cible, un ALLIE aussi. Trois discriminants D'UN COUP :
       (a) FRIENDLY-FIRE : l'allie adjacent EST frappe. Un port qui aurait recopie le wrapper
           `Enemies(...)` de PlasmaGrenade/ScythingTalons ne le toucherait pas.
       (b) EXCLUSION DU CASTER : le Gobbo, pourtant adjacent a sa propre cible, n'est PAS frappe --
           c'est le `op_Subtraction(., caster@0x48)` natif. Sans lui il se blesserait lui-meme.
           L'i2 le dit mot pour mot : « ... and all units adjacent to the target, EXCEPT Da Red
           Gobbo itself ».
       (c) REGLE DYNAMIQUE : le masque ne porte AUCUN `TargetIsEnemy` (il vaut
           `TargetMatchesDynamicRule | TargetIsUnit`), donc le refus des allies vient de
           `$$GetDynamicInvalidTargetReason`. On verifie que le jeu N'OFFRE PAS l'allie comme cible
           legale, et que le port rend bien `2` sur lui / `0` sur l'ennemi.
     ⚠ (a) et (b) sont contradictoires pour un port naif : « les allies sont frappes » ET « le
     caster, qui est un allie de lui-meme, ne l'est pas ». Un seul des deux ne prouve rien.

1176 `BlightGrenades` -- `IdunBattleLogic.Entities.Abilities.Active.BlightGrenadesAbility$$ExecuteBehaviour`
     Deux `AttackWithAbilityDamage` : la cible, puis `PickRandomly(UnitsDirectlyBehind(caster,
     target), 2)`. Jumeau STRUCTUREL de PlasmaCannon (1150) -- d'ou la meme geometrie de drive
     (cible a d=2, deux unites STRICTEMENT derriere a d=3). Deux discriminants :
       (a) TARGETING : le splash frappe EXACTEMENT les unites directly-behind (== le selecteur
           offline), jamais les adjacents-tous-cotes.
       (b) COUPS IDENTIQUES SUR LES DEUX VOLETS : le natif rappelle `GetHits()` au second volet, il
           n'existe NI `nrOfHits_2` NI `minDmg_2` dans la config 1176. Le patron splash de
           `loki/splash.py` lit `nrOfHits_2` au volet secondaire -- l'avoir recopie ici aurait
           ecrit un nombre de coups faux, et c'est ce que ce test refuse.

CONFONDS ASSUMES (pipeline PARTAGE, hors perimetre de ces deux ports -- identiques a ceux que
`test_plasma_cannon_live` documente) : la MAGNITUDE offline peut differer du live d'un facteur
scalaire (buffs ranged non appliques aux attaques d'ability), et `_pick_randomly_n` peut desyncher
le flux rng du volet DERRIERE (#215). On confronte donc le TARGETING et le NOMBRE DE COUPS, jamais
l'egalite de degat brute. C'est une borne, pas un renoncement : le targeting et les coups sont
exactement ce que le port de ces deux abilities decide.

Lit l'etat LIVE, aucune tuile/RVA hardcodee. ASCII only. Skip si build/geometrie indisponibles.
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
from engine.entities.selectors.units import UnitsDirectlyBehind
from engine.runner.abilities.base import ability_attack_params
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.runner.abilities.deathguard import BlightGrenadesAbility
from engine.runner.abilities.orks import ExplosivePresentsAbility
from engine.runner.snapshot import load_state

DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/abilities/orks.py",
                "scripts/python/engine/runner/abilities/deathguard.py",
                "scripts/python/engine/runner/abilities/handler.py",
                "scripts/python/engine/runner/abilities/attack_type.py",
                "scripts/python/engine/runner/abilities/targeting.py",
                # les deux selecteurs que les arbres consomment
                "scripts/python/engine/entities/selectors/units.py",
                # la feuille d'attaque (native_factory, multi, pick_n)
                "scripts/python/engine/runner/abilities/behaviours/combat.py"),
    "build": False,
    "toujours": False,
    "raison": "Il confronte au jeu le SET DE CIBLES et le NOMBRE DE COUPS des deux seules no-op de "
              "la tranche #997 qui frappent : les deux classes portees, les deux registres qui les "
              "routent, le gate de ciblage qui decide leur legalite, les selecteurs de leurs arbres "
              "et la feuille d'attaque qui les execute.",
}

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                      # racine repo
BOARD = "MC1_67"
SEED = "777"
GOBBO_VIS = "orksRedGobbo"
MARINE_VIS = "deathNpc2PlagueMarine"
EXPLOSIVE_PRESENTS = int(ExplosivePresentsAbility.ABILITY_TYPE)     # 1170
BLIGHT_GRENADES = int(BlightGrenadesAbility.ABILITY_TYPE)           # 1176
A_UNITS = "orksNob,orksNob,orksNob,orksNob"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _want_hits(ability_id: str) -> int:
    """ORACLE du nombre de coups : `constants.nrOfHits` (lecture BRUTE cote natif --
    `AActiveAbility$$GetHits` = `AbilityConfiguration$$GetNumberConstant(cfg, 0x2f)`, aucune
    formule). Cle non ambigue : `AbilityConstantType` 0x2f = `nrOfHits`."""
    v = ((GC.ability(ability_id) or {}).get("constants") or {}).get("nrOfHits")
    assert v is not None, (
        f"oracle introuvable : gameconfig.ability('{ability_id}').constants.nrOfHits absent -- le "
        f"natif le lit par GetNumberConstant(0x2f), il DOIT exister")
    return int(v)


def _unit(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _build(state_file: Path):
    return subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--state-file", str(state_file),
         "--board", BOARD,
         "--explicit-stats", f"{GOBBO_VIS}:1", "--explicit-stats", f"{MARINE_VIS}:1",
         "--p-units", f"{GOBBO_VIS}:1,{MARINE_VIS}:1", "--a-units", A_UNITS,
         "--hp-target", "90000"],          # armure a 0 + PV hauts : personne ne meurt, le set de cibles reste lisible
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=_env())


def _env():
    import os
    e = dict(os.environ)
    # Le garde de roster compare l'id DEMANDE a l'id PUBLIE, et le jeu remappe les npc/boss --
    # faux rouge documente (reference_boss_montable_par_explicit_stats).
    e["TACTICUS_ALLOW_ROSTER_DEFICIT"] = "1"
    return e


def _live_damage_by_target(cast, ability_type: int):
    """Degats live du cast, ventiles par cible : `{targetId: [Amount, ...]}` lus dans les tags des
    events, filtres sur `Active_Ability_Type` (l'attribution #project_effect_type_attribution)."""
    out = {}
    for act in (cast.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == ability_type:
                out.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
    return out


def _legal_targets(rpc, rid, uid, ability_type):
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": uid, "abilityType": ability_type}, 90)
    a = next((x for x in ((at.get("units") or [{}])[0].get("abilities") or [])
              if x.get("abilityId") == ability_type), {})
    return [x.get("targetId") for x in (a.get("fromHere") or [])]


def test_997_explosive_presents_live(live_session, rpc):
    """1170 : friendly-fire SUR l'allie adjacent, caster EXCLU bien qu'adjacent, allie REFUSE comme
    cible par la regle dynamique. Les trois volets ensemble -- pris isolement chacun passerait sur
    un port faux."""
    state_file = ROOT / "logs" / "runners" / f"ep997-{uuid.uuid4().hex[:8]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    proc = _build(state_file)
    if not state_file.exists():
        pytest.skip(f"build runner KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    rid = json.loads(state_file.read_text())["runnerId"]
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")

        def mv(uid, tid):
            c = board.coord(tid)
            return rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        gobbo, marine = _unit(dv, GOBBO_VIS), _unit(dv, MARINE_VIS)
        if gobbo is None or marine is None:
            pytest.skip("porteur(s) absent(s) du runner")
        mine = gobbo.get("owner")
        enemies = [u for u in (dv.get("units") or []) if u.get("owner") != mine and u.get("alive")]
        if len(enemies) < 2:
            pytest.skip("moins de 2 ennemis vivants (besoin cible + 1 adjacent)")

        # --- geometrie DRIVEE : une tuile T ayant au moins 3 voisins libres. On y met la cible, puis
        #     le CASTER, un ALLIE et un ENNEMI sur trois de ses voisins. Le caster est donc ADJACENT
        #     a sa propre cible : c'est ce qui arme le discriminant (b).
        cand = None
        for T in sorted(board.by_id):
            if not board.walkable(T):
                continue
            nbrs = [n for n in board.neighbours(T) if board.walkable(n)]
            if len(nbrs) >= 3:
                cand = (T, nbrs[:3])
                break
        if cand is None:
            pytest.skip("aucune tuile a >= 3 voisins libres sur ce board")
        T, (t_caster, t_ally, t_enemy2) = cand
        # parquer tout le monde LOIN d'abord (isole la geometrie : aucun adjacent parasite)
        far = [t for t in sorted(board.by_id) if board.walkable(t)
               and hexgeo.distance(board.coord(t), board.coord(T)) > 4]
        if len(far) < len(enemies) + 2:
            pytest.skip("pas assez de tuiles lointaines pour parquer")
        for u, ft in zip(enemies + [gobbo, marine], far):
            mv(u["id"], ft)
        target, adj_enemy = enemies[0], enemies[1]
        mv(target["id"], T)
        mv(gobbo["id"], t_caster)
        mv(marine["id"], t_ally)
        mv(adj_enemy["id"], t_enemy2)

        legal = _legal_targets(rpc, rid, gobbo["id"], EXPLOSIVE_PRESENTS)
        if target["id"] not in legal:
            pytest.skip(f"cast illegal apres placement (fromHere={legal})")

        # --- (c) REGLE DYNAMIQUE : le jeu n'offre PAS l'allie comme cible (aucun TargetIsEnemy dans
        #     le masque -> c'est `$$GetDynamicInvalidTargetReason` qui le refuse), et le port rend la
        #     MEME chose (2 sur l'allie, 0 sur l'ennemi).
        assert marine["id"] not in legal, (
            f"le jeu OFFRE l'allie {marine['id']} comme cible d'ExplosivePresents (fromHere={legal}) "
            f"-- alors que GetDynamicInvalidTargetReason doit rendre 2 sur un ami hors unite de quete")

        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        st = load_state(dv2, ob2, snap2, board=board)
        ab = ExplosivePresentsAbility()
        assert ab.get_dynamic_invalid_target_reason(st, gobbo["id"], marine["id"]) == 2, (
            "le port ACCEPTE un allie comme cible d'ExplosivePresents -- la regle dynamique "
            "(refus des amis, sauf l'unite `constants.unitId`) n'est pas appliquee")
        assert ab.get_dynamic_invalid_target_reason(st, gobbo["id"], target["id"]) == 0, (
            "le port REFUSE un ennemi -- la regle dynamique ne doit rendre 2 que sur un ami")

        want_hits = _want_hits("ExplosivePresents")
        _, _, _, hits = ability_attack_params(st, gobbo["id"], "ExplosivePresents", "Blast",
                                              ranged=True)
        assert hits == want_hits, (
            f"nrOfHits lu {hits} != oracle config {want_hits} -- le port ne lit pas la CONSTANTE "
            f"d'ability (0x2f)")

        # ============ LIVE cast ============
        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": gobbo["id"], "targetId": target["id"],
            "abilityType": EXPLOSIVE_PRESENTS}, "captureEvents": True}, 120)
        assert _ok(cast), f"cast ExplosivePresents non applique: {str(cast)[:200]}"
        live = _live_damage_by_target(cast, EXPLOSIVE_PRESENTS)
        assert live, "aucun degat live attribue a ExplosivePresents (1170) -- cast no-op ?"

        want = {target["id"], adj_enemy["id"], marine["id"]}
        assert set(live) == want, (
            f"cibles LIVE {sorted(live)} != cible + adjacents attendus {sorted(want)}. "
            f"(a) l'allie {marine['id']} manque => le port a wrappe le selecteur dans Enemies(...), "
            f"alors que le natif passe `AdjacentUnits` BRUT ; "
            f"(b) le caster {gobbo['id']} present => le `op_Subtraction(., caster@0x48)` manque")
        assert gobbo["id"] not in live, (
            f"le CASTER {gobbo['id']} est frappe par son propre ExplosivePresents alors qu'il est "
            f"seulement ADJACENT a la cible -- le `op_Subtraction(., caster@0x48)` natif manque")
        for tid, hs in live.items():
            assert len(hs) == want_hits, (
                f"cible {tid} : {len(hs)} coups LIVE != oracle config nrOfHits={want_hits} -- le "
                f"volet unique du natif passe `GetHits()` a UN SEUL AttackWithAbilityDamage, il n'y "
                f"a pas de seconde constante de coups dans la config 1170")

        # --- le PORT, sur le meme etat pre-cast : MEME set de cibles.
        res = ab.execute_behaviour(load_state(dv2, ob2, snap2, board=board), gobbo["id"],
                                   target["id"])
        assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
        ported = {res.get("target")} | {s["target"] for s in (res.get("splash") or [])}
        assert ported == want, (
            f"set de cibles du PORT {sorted(ported)} != set LIVE {sorted(want)}")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)


def test_997_blight_grenades_live(live_session, rpc):
    """1176 : le volet DERRIERE frappe exactement les unites directly-behind, et les DEUX volets
    portent le MEME nombre de coups (`nrOfHits`, pas `nrOfHits_2`)."""
    state_file = ROOT / "logs" / "runners" / f"bg997-{uuid.uuid4().hex[:8]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    proc = _build(state_file)
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

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        marine, gobbo = _unit(dv, MARINE_VIS), _unit(dv, GOBBO_VIS)
        if marine is None:
            pytest.skip("deathNpc2PlagueMarine absent du runner")
        mine = marine.get("owner")
        enemies = [u for u in (dv.get("units") or []) if u.get("owner") != mine and u.get("alive")]
        if len(enemies) < 3:
            pytest.skip("moins de 3 ennemis vivants (besoin cible + 2 derriere)")

        cid = marine["id"]
        cpos = (marine["pos"]["col"], marine["pos"]["row"])
        ctile = board.id_at(*cpos)
        eC = elev.get(cpos)
        # parquer TOUT le monde loin (le Gobbo allie compris : il ne doit pas polluer la geometrie)
        far = [t for t in sorted(board.by_id) if board.walkable(t)
               and hexgeo.distance(board.coord(t), cpos) > 6]
        if len(far) < len(enemies) + 1:
            pytest.skip("pas assez de tuiles lointaines pour parquer")
        for u, ft in zip(enemies + ([gobbo] if gobbo else []), far):
            mv(u["id"], ft)

        # --- geometrie STRICTE, jumelle de test_plasma_cannon_live : cible T a d=2 du caster, deux
        #     voisins de T a d=3 (STRICTEMENT derriere -- le comparateur natif est `>` et non `>=`,
        #     donc une unite laterale a d=2 serait EXCLUE), elevations a +-1.
        cand = None
        for T in sorted(board.by_id):
            ct = board.coord(T)
            if not board.walkable(T) or T == ctile or hexgeo.distance(ct, cpos) != 2:
                continue
            if elev.get(ct) is None or eC is None or abs(elev.get(ct) - eC) > 1:
                continue
            behind = [n for n in board.neighbours(T)
                      if board.walkable(n) and n != ctile
                      and hexgeo.distance(board.coord(n), cpos) == 3
                      and elev.get(board.coord(n)) is not None
                      and abs(elev.get(board.coord(n)) - elev.get(ct)) <= 1]
            if len(behind) >= 2:
                mv(enemies[0]["id"], T)
                if enemies[0]["id"] in _legal_targets(rpc, rid, cid, BLIGHT_GRENADES):
                    cand = (T, behind[:2])
                    break
                mv(enemies[0]["id"], far[0])
        if cand is None:
            pytest.skip("aucune geometrie directly-behind LEGALE (board/elevation)")
        T, behind = cand
        target, b1, b2 = enemies[0], enemies[1], enemies[2]
        mv(b1["id"], behind[0])
        mv(b2["id"], behind[1])
        if target["id"] not in _legal_targets(rpc, rid, cid, BLIGHT_GRENADES):
            pytest.skip("cast devenu illegal apres placement des unites derriere")

        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        st = load_state(dv2, ob2, snap2, board=board)
        ent = entities_from_state(st, cid, target["id"])
        udb = sorted(x.get("id") for x in UnitsDirectlyBehind().select(ent))
        assert set(udb) == {b1["id"], b2["id"]}, (
            f"UnitsDirectlyBehind offline {udb} != les 2 unites drivees derriere "
            f"{sorted([b1['id'], b2['id']])} -- la geometrie du drive n'est pas celle qu'on croit")

        want_hits = _want_hits("BlightGrenades")
        _, _, _, hits = ability_attack_params(st, cid, "BlightGrenades", "Toxic", ranged=True)
        assert hits == want_hits, (
            f"nrOfHits lu {hits} != oracle config {want_hits} (constants.nrOfHits)")

        # ============ LIVE cast ============
        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": target["id"],
            "abilityType": BLIGHT_GRENADES}, "captureEvents": True}, 120)
        assert _ok(cast), f"cast BlightGrenades non applique: {str(cast)[:200]}"
        live = _live_damage_by_target(cast, BLIGHT_GRENADES)
        assert live, "aucun degat live attribue a BlightGrenades (1176) -- cast no-op ?"

        want = {target["id"], b1["id"], b2["id"]}
        assert set(live) == want, (
            f"cibles LIVE {sorted(live)} != main + directly-behind {sorted(want)}")
        # (b) MEME nombre de coups sur les DEUX volets -- le discriminant `nrOfHits` vs `nrOfHits_2`.
        for tid, hs in live.items():
            assert len(hs) == want_hits, (
                f"cible {tid} : {len(hs)} coups LIVE != oracle config nrOfHits={want_hits}. Le natif "
                f"rappelle `GetHits()` au SECOND volet ; un port qui aurait recopie le patron splash "
                f"de `loki/splash.py` lirait `nrOfHits_2`, absent de la config 1176")

        res = BlightGrenadesAbility().execute_behaviour(
            load_state(dv2, ob2, snap2, board=board), cid, target["id"])
        assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
        ported = {res.get("target")} | {s["target"] for s in (res.get("behind") or [])}
        assert ported == want, (
            f"set de cibles du PORT {sorted(ported)} != set LIVE {sorted(want)}")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)
