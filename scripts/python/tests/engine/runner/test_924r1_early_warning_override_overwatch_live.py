"""#924-r1 -- LA FACE DEGAT de `EarlyWarningOverride_ReactivateOverwatch` (1145), BIT-EXACT.

LA SOEUR DE FORME DE 1018, ET LE PIEGE QU'ELLE POSE. `IdunBattle.Entities.Effects.Loki.
EarlyWarningOverride_ReactivateOverwatchEffect` derive de la MEME base native
(`AReactivateOverwatchEffect`) qu'`InescapableDeathEffect`, mais les deux classes sont des MIROIRS
CROISES -- bloc `methodPointers` relu aux octets sur `t6dpr4k06g` :

    1018 : .ctor, GetHitReductionEffectType, <GetOverwatchExtraDamage>, GetAdditionalExtraDamageTrigger
    1145 : .ctor, GetHitReductionEffectType, <GetOverwatchExtraDamage>, LegitDeathReasons

Le corps `<GetOverwatchExtraDamage>` est le MEME (ICF, deux proprietaires) : c'est pour cela que
`frida/methods.tsv`, indexe par ADRESSE, n'en montre qu'un et faisait lire << 1145 n'override pas >>.
1145 l'override bel et bien, sa variable `extraDmg` est non nulle ([26 .. 1440], dans
`variablesAffectedByRarityBonus`) : la face est VIVANTE.

CE QUE CE TEST TRANCHE, ET QU'AUCUNE TABLE NE DONNE. Le 3e conjoint du declencheur de 1145 est le
`<vtable +0x768>` de la BASE (elle n'override PAS `GetAdditionalExtraDamageTrigger`). Ce corps n'a
aucun symbole propre ; retrouve dans le bloc `methodPointers` de la base, il rend
`<DSLTriggers+0x70>` = le `YesTrigger` (constante VRAIE, meme constante que les
`CreateActiveCondition` deja identifies de `KardiocoreGalvanus_ExtraCritDmg` et
`WisdomOfTheAncients_DamageReduction`). Le gate EFFECTIF est donc
`get_OwnerIsCaster & TriggeringEffectIs(0x3f1)`. Cette attribution est ce que la salve bit-exacte
CONFRONTE : un 3e conjoint qui ne serait pas la constante vraie ferait diverger le rejeu.

LE MONTAGE -- IMMEDIAT, sans injection ni greffe (contrairement a ce que #924 annoncait) :
`tauCrisis` << Re'vas >> est un HERO AU POOL et porte `EarlyWarningOverride` en `kind: active`
(1077). Son `ExecuteBehaviour` pose QUATRE effets sur le caster lui-meme -- `0x3f1 = 1009
Overwatch_AutoAttack`, `0x478 = 1144`, `0x479 = **1145**`, `0x47d = 1149` -- pour
`TurnsFromRounds(1)`, tous avec le MEME `DSLSelectors.CreateSnapshot(abilityState)`.
Le cast TERMINE le tour du caster : la main passe a l'adversaire, dont ce test PILOTE le mover
(`applyAction` sert le joueur COURANT, quel qu'il soit -- mesure : apres le cast, `decisionView`
rend `ctrl: true` sur les unites adverses).

⚠ Ce fichier monte un runner : il est LIVE.
"""
from __future__ import annotations

from collections import deque

import pytest

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.runner.components import HealthComponent, StatsComponent
from engine.runner.messages import MoveUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

#: le CASTER : HERO au pool, `EarlyWarningOverride` en ability ACTIVE.
CASTER_VIS = "tauCrisis"
#: le mover ADVERSE, vanille (`effects = []` au deploiement) : aucune reduction non portee.
MOVER_VIS = "necroOverlord"
MOVER_HP = 60000
EWO_ABILITY = int(ActiveAbilityType.EarlyWarningOverride)                       # 1077
REACTIVATE_OVERWATCH = int(EffectType.EarlyWarningOverride_ReactivateOverwatch)  # 0x479 = 1145
OVERWATCH_EFFECT = int(EffectType.Overwatch_AutoAttack)                          # 0x3f1 = 1009

BUILD = ["--roster", "1", "--p-units", CASTER_VIS, "--a-units", MOVER_VIS,
         "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (MOVER_VIS, MOVER_HP, MOVER_HP)]

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/inescapable_death.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/abilities/tau.py",
        "scripts/python/engine/runner/damage_model.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation BIT-EXACT de la face DEGAT de `EarlyWarningOverride_ReactivateOverwatch` "
              "(#924-r1) : elle rougit si la magnitude, le gate, le `scale_from_source` de la pose ou "
              "l'etage d'injection de l'additif d'overwatch bougent.",
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


def _effect_types(u):
    return {int(e.get("effectType")) for e in (u.get("effects") or []) if e.get("effectType") is not None}


def test_924r1_early_warning_override_overwatch_bit_exact(live_session, rpc, build_runner):
    """Le tir d'overwatch de Re'vas sous `EarlyWarningOverride` (6 coups Pulse + `extraDmg`) est
    reproduit BIT-EXACT offline, PV du mover a l'unite.

    ROUGE attendu tant que 1145 n'a pas de classe d'effet (ou que la pose ne porte pas son
    `AbilityStateReference`) : le port rend alors la salve NUE."""
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
    caster0 = next((u for u in units if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
    mover0 = next((u for u in units if u.get("visualId") == MOVER_VIS and u.get("alive")), None)
    if caster0 is None or mover0 is None:
        pytest.skip("unite absente (caster=%s mover=%s)" % (bool(caster0), bool(mover0)))
    caster_id, mover_id = caster0["id"], mover0["id"]
    caster_player = caster0.get("owner")

    import gameconfig as GC
    weapons = (GC.unit(CASTER_VIS) or {}).get("weapons") or []
    R = max([int(w.get("Range") or 0) for w in weapons] or [0]) or 1

    fired = None
    casted = False
    for _turn in range(40):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        cs = next((u for u in (dec.get("units") or []) if u["id"] == caster_id and u.get("alive")), None)
        mv = next((u for u in (dec.get("units") or []) if u["id"] == mover_id and u.get("alive")), None)
        if cs is None or mv is None:
            pytest.skip("caster/mover disparu pendant l'approche")
        dgoal = _bfs(board, tof(cs))
        cur = tof(mv)
        armed = REACTIVATE_OVERWATCH in _effect_types(cs) and OVERWATCH_EFFECT in _effect_types(cs)

        if dec.get("currentPlayer") == caster_player:
            # MON tour. On ne caste que lorsque le mover est a UN pas de la portee : les quatre
            # effets ne durent que `TurnsFromRounds(1)`, donc la fenetre est courte.
            if not casted and dgoal.get(cur, 99) <= R + 1:
                r = rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "ability", "casterId": caster_id, "abilityType": EWO_ABILITY,
                    "targetId": caster_id}}, 90)
                if not _ok(r):
                    pytest.skip("cast EarlyWarningOverride refuse : %s" % (str(r)[:300],))
                casted = True                                  # le cast TERMINE le tour du caster
                continue
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue

        # Tour ADVERSE : c'est nous qui pilotons le mover (`ctrl` a bascule).
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == mover_id), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        if not armed:
            # Phase 1 -- s'approcher en RESTANT hors portee (dist > R) et strictement plus proche.
            out_pool = [t for t in reach
                        if t in dgoal and dgoal[t] > R and dgoal[t] < dgoal.get(cur, 99)]
            if dgoal.get(cur, 99) > R and out_pool:
                best = min(out_pool, key=lambda t: dgoal[t]); col, row = reach[best]
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": mover_id, "to": {"col": col, "row": row}}}, 40)
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue

        # Phase 2 -- l'overwatch est ARME : entrer d'UN pas dans la portee = un seul tir.
        step_pool = [t for t in reach if t in dgoal and t in set(board.neighbours(cur))]
        if not step_pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        best = min(step_pool, key=lambda t: dgoal[t]); col, row = reach[best]

        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
        hp_before = next((u.get("hp") for u in (ob.get("units") or []) if u.get("squadId") == mover_id), None)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        state = load_state(dec, ob, snap, board=board)
        if not _ok(s0):
            pytest.skip("dumpRng KO")
        state.rng = _seed_rng(s0)
        cs_stats = next((u for u in (snap.get("units") or []) if u.get("entityId") == caster_id), None)
        mv_stats = next((u for u in (snap.get("units") or []) if u.get("entityId") == mover_id), None)

        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mover_id, "to": {"col": col, "row": row}}}, 40)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
        hp_after = next((u.get("hp") for u in (ob2.get("units") or []) if u.get("squadId") == mover_id), None)
        if hp_before is None or hp_after is None:
            continue
        if hp_after >= hp_before:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue                                   # pas d'overwatch sur ce move

        ce = state.get_entity(caster_id)
        if ce is None or ce.get_component(StatsComponent) is None:
            pytest.skip("caster sans StatsComponent offline (combatSnapshot ne couvre pas)")
        # Le port DOIT voir l'effet 1145 sur le caster, sinon ce test ne mesure pas ce qu'il croit.
        off_effs = {int(getattr(e, "effect_type", 0) or 0)
                    for e in (state.effects.by_unit.get(caster_id) or [])} if state.effects else set()
        runner = Runner(state).install_default_handlers(20)
        runner.apply(MoveUnitMessage(mover_id, (col, row)))
        am = runner.movement_handler.after_move
        off_hp = state.get_entity(mover_id).get_component(HealthComponent).hp
        fired = {"hp_before": hp_before, "hp_after_live": hp_after, "off_hp": off_hp,
                 "after_move": am, "tile": (col, row), "off_effs": off_effs,
                 "cs_stats": (cs_stats or {}).get("stats") or {},
                 "mv_stats": (mv_stats or {}).get("stats") or {}}
        break
    if fired is None:
        pytest.skip("aucun overwatch declenche en 40 tours (cast/portee/geometrie)")

    ow_results = [a for a in (fired["after_move"] or []) if a.get("effect") == "Overwatch_AutoAttack"]
    _r = (ow_results or [{}])[0].get("result") or {}
    live_dmg = fired["hp_before"] - fired["hp_after_live"]
    off_dmg = fired["hp_before"] - fired["off_hp"]
    print("\n[924-r1] REGIME MESURE : caster extraPierce=%s/%s ; mover fixedArmor=%s"
          % (fired["cs_stats"].get("extraPierce"), fired["cs_stats"].get("extraPierceRanged"),
             fired["mv_stats"].get("fixedArmor")))
    print("[924-r1] mover hp %s -> live %s (live dmg=%s) | offline %s (off dmg=%s) | ecart=%s"
          % (fired["hp_before"], fired["hp_after_live"], live_dmg, fired["off_hp"], off_dmg,
             live_dmg - off_dmg))
    print("[924-r1] offline result: per_hit=%s pierce=%s armor=%s ranged=%s profile=%s"
          % (_r.get("per_hit"), _r.get("pierce"), _r.get("armor"), _r.get("ranged"),
             _r.get("profile")))

    assert REACTIVATE_OVERWATCH in fired["off_effs"], (
        "l'effet 1145 n'est pas dans l'etat OFFLINE du caster (effets vus : %s) -- ce test ne "
        "mesure alors PAS la face DEGAT." % (sorted(fired["off_effs"]),))
    assert ow_results, ("le vecteur after-move offline n'a PAS declenche l'overwatch "
                        "(after_move=%s)" % (fired["after_move"],))
    assert fired["off_hp"] == fired["hp_after_live"], (
        "PV mover offline %s != live %s (overwatch live=%s, offline=%s, manque %s). "
        "La face DEGAT de `EarlyWarningOverride_ReactivateOverwatch` (1145) n'est pas -- ou mal -- "
        "portee." % (fired["off_hp"], fired["hp_after_live"], live_dmg, off_dmg,
                     live_dmg - off_dmg))
