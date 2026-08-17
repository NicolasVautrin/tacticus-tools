"""#924-r2 -- LA FACE DEGAT d'`InescapableDeath` CONFRONTEE BIT-EXACT, coup par coup.

CE QUE CE FICHIER REMPLACE. `test_924_inescapable_death_offline.py` portait un CLIQUET INVERSE
(<< la face DEGAT reste DESARMEE >>) dont le message exigeait, pour etre leve, << de MESURER a
nouveau le couple (normale, overwatch) >>. C'est ce fichier-ci : il ne compare plus deux MOYENNES
de six tirages mais REJOUE le tir d'overwatch offline depuis l'etat d'AVANT, MT cale par `dumpRng`,
et confronte les PV du mover a l'unite.

POURQUOI LA MESURE D'ORIGINE NE POUVAIT RIEN CONCLURE (mesure du 2026-08-17, #924-r3). #924 SS5
ecrivait << armure 0 des deux cotes >> et en tirait que `GetDamageWithPiercing` etait l'IDENTITE.
Deux faits, LUS et non deduits, cassent cette lecture :

  1. le montage de #924-r2 (`probe_924r2_ability_state_overwatch.py`) monte `necroDestroyer` en
     `--p-units` et `astraBullgryn` en `--a-units`, et `combatSnapshot` sur ce montage rend
     `fixedArmor = 4821` pour la cible et `extraPierce = extraPierceRanged = 0` pour l'attaquant.
     `Gauss` porte `PiercingRatio = 60`. Pour tout `d < 12052`, `max(0, d - 4821, 0,60 d) = 0,60 d` :
     le regime est PERCE, pas l'identite ;
  2. le drapeau `--hp-target` de `rl_duel` -- celui que #924 SS5 cite (`--hp-target 60000`) --
     **MET Armor/FixedArmor A 0** sur les a-units, et son aide le dit mot pour mot (<< piege de
     mesure : cela SUPPRIME l'etage armure >>). Les deux bras de la mesure d'origine n'etaient donc
     pas dans le meme regime, et c'est exactement ce que reproduit le port :

         apply_pierce_and_modifiers(base, pierce=60, armure=4821, additif=898, pre=True)
             - sans additif -> 544        - avec -> 1082        delta = 538
         apply_pierce_and_modifiers(base, pierce=60, armure=0,    additif=898, pre=True)
             - sans additif -> 906        - avec -> 1804        delta = 898,0 EXACTEMENT

     Le << port +898,0 EXACTEMENT >> de la fiche est le nombre du regime ARMURE 0 ; le
     << natif +617,3 >> celui d'un regime ou l'armure mord. L'ecart etait un artefact de montage.

CE QUE CE TEST MESURE, ET POURQUOI IL EST DISCRIMINANT. Le mover garde son armure NATURELLE (on ne
monte que ses PV, par `--unit-stat`, pas par `--hp-player` qui zappe l'armure) : la branche PERCAGE
mord, donc un additif place AVANT le percage vaut `898 x p/100` au coup et un additif place APRES
vaut `898`. Les deux positions rendent des nombres DIFFERENTS, et la confrontation est faite a
l'unite de PV, pas sur une moyenne. Un test monte a armure 0 aurait rendu << accord >> quelle que
soit la position -- c'est le regime degenere de #924, qu'on ne rejoue pas.

⚠ Ce fichier monte un runner : il est LIVE. Un seul runner, dispose par la fixture partagee.
"""
from __future__ import annotations

from collections import deque

import pytest

from engine.entities.effect_type import EffectType
from engine.runner.components import HealthComponent, StatsComponent
from engine.runner.messages import MoveUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

#: le PORTEUR de `InescapableDeath` (`TriggeredAbilityType` 0x3ed = 1005) et du trait `Overwatch`.
#: Il est monte en a-unit : c'est LUI qui tire, sur MON mover qui entre dans sa portee.
OVERWATCHER_VIS = "necroDestroyer"
#: mover VANILLE (`effects = []` au deploiement, cf. `test_overwatch_live.py`) : aucune reduction
#: non portee ne vient polluer la confrontation.
MOVER_VIS = "necroOverlord"
#: PV du mover montes par `--unit-stat` et NON par `--hp-player` : ce dernier met AUSSI
#: `Armor`/`FixedArmor` a 0 (aide de `rl_duel`), ce qui rendrait `GetDamageWithPiercing` identique
#: et le regime NON DISCRIMINANT pour la position de l'additif. Six coups de Gauss boostes montent
#: a ~11 000 : 60 000 PV laissent le mover vivant, donc la salve entiere est observable.
MOVER_HP = 60000
OVERWATCH_EFFECT = int(EffectType.Overwatch_AutoAttack)              # 0x3f1 = 1009

BUILD = ["--roster", "1", "--p-units", MOVER_VIS, "--a-units", OVERWATCHER_VIS,
         "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (MOVER_VIS, MOVER_HP, MOVER_HP)]

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/inescapable_death.py",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/runner/operations/triggers/effect_triggers.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation BIT-EXACT de la face DEGAT d'`InescapableDeath` (#924-r2) : elle rougit "
              "si la magnitude, le gate ou l'etage d'injection de l'additif d'overwatch bougent.",
}


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _bfs(board, src):
    dist = {src: 0}; q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1; q.append(n)
    return dist


def test_924r2_overwatch_inescapable_death_bit_exact(live_session, rpc, build_runner):
    """Le tir d'overwatch d'Imospekh (6 coups Gauss + `InescapableDeath.extraDmg`) est reproduit
    BIT-EXACT offline, PV du mover a l'unite.

    ROUGE attendu tant que `InescapableDeathEffect.create_effect_damage_bonus_for_attack` n'existe
    pas : le port rend alors la salve NUE et le mover perd, offline, nettement moins de PV que live.
    """
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    def tof(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None

    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if not _ok(dec):
        pytest.skip("decisionView KO")
    units = dec.get("units") or []
    mover0 = next((u for u in units if u.get("visualId") == MOVER_VIS and u.get("alive")), None)
    ow = next((u for u in units if u.get("visualId") == OVERWATCHER_VIS and u.get("alive")), None)
    if mover0 is None or ow is None:
        pytest.skip("unite absente (mover=%s overwatcher=%s)" % (bool(mover0), bool(ow)))
    my_player = mover0.get("owner")
    mover_id, ow_id = mover0["id"], ow["id"]

    import gameconfig as GC
    ow_weapons = (GC.unit(OVERWATCHER_VIS) or {}).get("weapons") or []
    R = max([int(w.get("Range") or 0) for w in ow_weapons] or [0]) or 1

    fired = None
    for _turn in range(30):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        mv = next((u for u in (dec.get("units") or []) if u["id"] == mover_id and u.get("alive")), None)
        owl = next((u for u in (dec.get("units") or []) if u["id"] == ow_id and u.get("alive")), None)
        if mv is None or owl is None:
            pytest.skip("mover/overwatcher disparu pendant l'approche")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        dgoal = _bfs(board, tof(owl))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == mover_id), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        cur = tof(mv)
        # Phase 1 -- s'approcher VITE en restant HORS portee (dist > R) et strictement plus proche.
        out_pool = [t for t in reach if t in dgoal and dgoal[t] > R and dgoal[t] < dgoal.get(cur, 99)]
        if dgoal.get(cur, 99) > R and out_pool:
            best = min(out_pool, key=lambda t: dgoal[t]); col, row = reach[best]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": mover_id, "to": {"col": col, "row": row}}}, 40)
            dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
            if dv2.get("currentPlayer") == my_player:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        # Phase 2 -- entrer d'UN pas dans la portee : une seule tuile en portee = un seul tir.
        step_pool = [t for t in reach if t in dgoal and t in set(board.neighbours(cur))]
        if not step_pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        best = min(step_pool, key=lambda t: dgoal[t]); col, row = reach[best]

        # === capture AVANT le move (etat + MT cale : le tir d'overwatch est le 1er conso RNG) ===
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
        hp_before = next((u.get("hp") for u in (ob.get("units") or []) if u.get("squadId") == mover_id), None)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        state = load_state(dec, ob, snap, board=board)
        if not _ok(s0):
            pytest.skip("dumpRng KO")
        state.rng = _seed_rng(s0)
        # etage MESURE du regime : c'est lui qui rend le test discriminant (cf. l'en-tete).
        ow_stats = next((u for u in (snap.get("units") or []) if u.get("entityId") == ow_id), None)
        mv_stats = next((u for u in (snap.get("units") or []) if u.get("entityId") == mover_id), None)

        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mover_id, "to": {"col": col, "row": row}}}, 40)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
        hp_after = next((u.get("hp") for u in (ob2.get("units") or []) if u.get("squadId") == mover_id), None)
        if hp_before is None or hp_after is None:
            continue
        if hp_after >= hp_before:
            continue                                   # pas d'overwatch sur ce move -> approcher

        oe = state.get_entity(ow_id)
        if oe is None or oe.get_component(StatsComponent) is None:
            pytest.skip("overwatcher sans StatsComponent offline (combatSnapshot ne couvre pas)")
        runner = Runner(state).install_default_handlers(20)
        runner.apply(MoveUnitMessage(mover_id, (col, row)))
        am = runner.movement_handler.after_move
        off_hp = state.get_entity(mover_id).get_component(HealthComponent).hp
        fired = {"hp_before": hp_before, "hp_after_live": hp_after, "off_hp": off_hp,
                 "after_move": am, "tile": (col, row),
                 "ow_stats": (ow_stats or {}).get("stats") or {},
                 "mv_stats": (mv_stats or {}).get("stats") or {}}
        break
    if fired is None:
        pytest.skip("aucun overwatch declenche en 30 tours (portee/geometrie)")

    ow_results = [a for a in (fired["after_move"] or []) if a.get("effect") == "Overwatch_AutoAttack"]
    _r = (ow_results or [{}])[0].get("result") or {}
    live_dmg = fired["hp_before"] - fired["hp_after_live"]
    off_dmg = fired["hp_before"] - fired["off_hp"]
    print("\n[924-r2] REGIME MESURE : attaquant extraPierce=%s/%s ; cible fixedArmor=%s"
          % (fired["ow_stats"].get("extraPierce"), fired["ow_stats"].get("extraPierceRanged"),
             fired["mv_stats"].get("fixedArmor")))
    print("[924-r2] mover hp %s -> live %s (live dmg=%s) | offline %s (off dmg=%s) | ecart=%s"
          % (fired["hp_before"], fired["hp_after_live"], live_dmg, fired["off_hp"], off_dmg,
             live_dmg - off_dmg))
    print("[924-r2] offline result: per_hit=%s pierce=%s armor=%s ranged=%s profile=%s "
          "base=[%s,%s] clean=[%s,%s]"
          % (_r.get("per_hit"), _r.get("pierce"), _r.get("armor"), _r.get("ranged"),
             _r.get("profile"), _r.get("base_min"), _r.get("base_max"),
             _r.get("clean_min"), _r.get("clean_max")))

    assert ow_results, ("le vecteur after-move offline n'a PAS declenche l'overwatch "
                        "(after_move=%s)" % (fired["after_move"],))
    # Le regime doit MORDRE, sinon ce test ne discrimine plus la position de l'additif : a armure
    # nulle `GetDamageWithPiercing` est l'identite et les deux placements rendent le meme nombre
    # (c'est exactement le regime degenere de #924 SS5). On l'ASSERTIONNE.
    assert int(fired["mv_stats"].get("fixedArmor") or 0) > 0, (
        "le mover a une armure NULLE : le regime est degenere et ce test ne separe plus l'additif "
        "PRE-percage de l'additif POST-percage. Verifie que `--unit-stat` n'a pas ete remplace par "
        "`--hp-player`, qui met FixedArmor a 0.")
    assert fired["off_hp"] == fired["hp_after_live"], (
        "PV mover offline %s != live %s (overwatch live=%s, offline=%s, manque %s). "
        "La face DEGAT d'`InescapableDeath` (`AReactivateOverwatchEffect$$CreateDamageModifier` "
        "allume par `InescapableDeathEffect$$GetOverwatchExtraDamage`) n'est pas -- ou mal -- "
        "portee." % (fired["off_hp"], fired["hp_after_live"], live_dmg, off_dmg,
                     live_dmg - off_dmg))
