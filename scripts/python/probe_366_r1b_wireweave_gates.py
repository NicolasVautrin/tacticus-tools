"""Probe #366-r1b (volet OFFLINE) -- les GATES et la MACHINE A ETATS de `1111
WireweaveNet_CounterAttack`, exercees sur un `State` FABRIQUE (aucun runner, aucune session Frida).

Ce probe ne remplace PAS la confrontation live (`probe_366_r1b_wireweave_net.py`) : il exerce, un par
un et de facon DETERMINISTE, chaque conjoint lu au decompile, et surtout la partie que le live
mesure mal -- la MACHINE A ETATS d'armement (`EffectComponent.IsActive @+0x5c`), qui demande
plusieurs boundaries de tour.

Chaque etape porte le symbole natif qu'elle exerce :

  [0] REGISTRE            -- `EFFECT_CLASSES` + `ABILITY_INIT_OWNER_EFFECTS` + `EFFECT_TRIGGERS[1111]`
  [1] RIPOSTE             -- `CounterAttackEffect$$CreateTargetTrigger` (cas POSITIF)
  [2] `& DeactivateEffect`-- `$$CreateTargetTriggerBehaviour` : "the FIRST time" (2e coup = rien)
  [3] `IsTurnOf(Owner)`   -- `PlayerTurnEffect$$IsEnabledTurnType` (turnsEnabled = 1)
  [4] `IsMeleeAttack`     -- predicat POSITIONNEL (attaquant a distance 2 = rien)
  [5] `IsNormalAttack`    -- une ACTIVE de melee ne reveille PAS la riposte
  [6] `AreEnemies`        -- un ALLIE adjacent qui frappe le porteur ne le reveille pas
  [7] `OwnerOrOwnerTileIsTarget` -- une attaque qui ne VISE PAS Calandis ne la reveille pas
  [8] MACHINE A ETATS     -- `On(0x12) & IsTurnOf(Owner) -> Deactivate` /
                             `On(0x17) & IsTurnOf(Owner) -> Activate` (re-armement inter-tours)
  [9] DECISION            -- `WireweaveNet_FirstAttack` : -30 SSI la cible porte un filet ARME

Usage : python probe_366_r1b_wireweave_gates.py
ASCII only (console cp1252).
"""
from __future__ import annotations

import json
from pathlib import Path

import board as B
import gameconfig as GC
from engine.entities import EffectsState
from engine.entities.effect_type import EffectType
from engine.entities.unit_context import UnitContext
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent)
from engine.runner.operations.triggers.dispatch import (pre_unit_ability_triggers,
                                                        tile_tick_triggers,
                                                        end_turn_summon_triggers)
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.state import State

BOARD_ID = "MC1_67"
BOARD_KIND = "pvp"
CARRIER = "eldarRanger"                 # Calandis -- porteur du passif `WireweaveNet`
FOE = "orksNob"                         # attaquant melee
EFFECT = int(EffectType.WireweaveNet_CounterAttack)      # 0x457 = 1111
NORMAL_ATTACK_KIND = 0x3f5              # marqueur "kind attaque-normale" de la voie normale
MELEE_ACTIVE = 1131                     # JakhalStimms -- ACTIVE classee DirectTargetAttack
P_ME, P_FOE = 3, 4                      # ids de joueur


def _board():
    p = (Path(__file__).resolve().parent.parent.parent / "data" / "boards" / BOARD_KIND
         / (BOARD_ID + ".json"))
    dump = json.loads(p.read_text(encoding="utf-8"))
    bd = B.Board({"Board": dump["board"], "SpawnPointSetIndex": dump.get("spawnPointsSet", 0)})
    tiles = []
    for i, (col, row) in enumerate(sorted(bd.playable_tiles())):
        t = bd.tile(col, row) or {}
        tiles.append({"id": i + 1, "col": col, "row": row, "walkable": True,
                      "tileDefId": t.get("tileId"), "elevation": t.get("elevation")})
    from engine.entities.pathfinding import Board as EngineBoard
    return EngineBoard(tiles, adjacency="evenq")


def _add_unit(state, vid, col, row, team, player, hp=400000):
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id=vid, alive=True))
    e.add_component(OwnerComponent(team=team, player=player))
    ctx = UnitContext(entity_id=e.id, visual_id=vid, active_ability_level=50,
                      passive_ability_level=50, ability_variables_multiplier=100)
    ctx.traits = list((GC.unit(vid) or {}).get("traits") or [])
    e.add_component(StatsComponent(ctx=ctx))
    e.add_component(HealthComponent(hp=hp, hp_max=hp))
    e.add_component(PositionComponent(col=col, row=row))
    return e.id


def _fresh(foe_col=2, foe_row=1, current=P_FOE, foe_team=2, foe_player=P_FOE, foe_vis=FOE):
    """`State` neuf : Calandis (2,2) + un ennemi en (`foe_col`,`foe_row`). `current` = joueur courant
    (P_FOE = tour ADVERSE = la fenetre d'armement). L'owner-effect 1111 est pose par le MEME chemin
    que le runner : `_seed_ability_owner_effects` (table `ABILITY_INIT_OWNER_EFFECTS`)."""
    from engine.runner.operations.spawn import _seed_ability_owner_effects
    state = State()
    state.board = _board()
    state.effects = EffectsState.seed({})
    state.rng = IntBasedMersenneTwister(777)
    state.current_player_id = current
    car = _add_unit(state, CARRIER, 2, 2, team=1, player=P_ME)
    foe = _add_unit(state, foe_vis, foe_col, foe_row, team=foe_team, player=foe_player)
    _seed_ability_owner_effects(state, car, CARRIER, 100, ability_level=50)
    return state, car, foe


def _inst(state, car):
    return next((e for e in (state.effects.by_unit.get(car) or [])
                 if e.effect_type == EFFECT and not e.consumed), None)


def _hp(state, uid):
    return state.get_entity(uid).get_component(HealthComponent).hp


def _fire(state, foe, car, ability_type=NORMAL_ATTACK_KIND):
    """Emet le vecteur `On(0x2a = PreUnitAbility)` et rend (degat inflige a l'attaquant, resultats)."""
    hp0 = _hp(state, foe)
    out = pre_unit_ability_triggers(state, foe, car, ranged=False, profile=None,
                                    ability_type=ability_type)
    return hp0 - _hp(state, foe), [o for o in out
                                   if (o or {}).get("effect") == "WireweaveNet_CounterAttack"]


def main() -> int:
    # --- 0. REGISTRE ---------------------------------------------------------------------------
    from engine.entities.effects.factory import EFFECT_CLASSES, ABILITY_INIT_OWNER_EFFECTS
    from engine.entities.effects.loki.counter_attack import WireweaveNetCounterAttackEffect
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    assert EFFECT_CLASSES.get("WireweaveNet_CounterAttack") is WireweaveNetCounterAttackEffect
    assert ABILITY_INIT_OWNER_EFFECTS.get("WireweaveNet") == ["WireweaveNet_CounterAttack"]
    trig = [c.__name__ for c in EFFECT_TRIGGERS.get(EFFECT, [])]
    print("[0] EFFECT_CLASSES[1111]=%s ; ABILITY_INIT_OWNER_EFFECTS[WireweaveNet]=%s ; triggers=%s"
          % (WireweaveNetCounterAttackEffect.__name__,
             ABILITY_INIT_OWNER_EFFECTS.get("WireweaveNet"), trig))
    assert len(trig) == 3, "l'ArraySet natif porte 3 Triggered() -- registre incomplet"
    assert (WireweaveNetCounterAttackEffect.TURNS_ENABLED,
            WireweaveNetCounterAttackEffect.ACTIVATION_FREQUENCY) == (1, 2)

    # --- 1. CAS POSITIF : la riposte part -------------------------------------------------------
    state, car, foe = _fresh()
    inst = _inst(state, car)
    assert inst is not None, "l'owner-effect 1111 n'a pas ete pose par ABILITY_INIT_OWNER_EFFECTS"
    dmg, out = _fire(state, foe, car)
    print("[1] tour ADVERSE, melee, attaque NORMALE -> degat sur l'attaquant=%s  events=%s"
          % (dmg, [(o.get("target"), bool(o.get("deactivated"))) for o in out]))
    assert dmg > 0 and out, "la riposte n'est pas partie (cas POSITIF)"
    assert out[0]["target"] == foe, "la riposte n'a pas vise l'ATTAQUANT (slot Caster@<Sel+0x48>)"
    hits = ((out[0].get("attack") or {}).get("per_hit")) or []
    print("    per_hit=%s (attendu nrOfHits=2, profil Piercing)" % (hits,))
    assert len(hits) == 2, "nrOfHits != 2 -> `GetNumberConstant(cfg, 0x2f)` mal lu"

    # --- 2. "the FIRST time" : le 2e coup du MEME tour ne riposte pas ---------------------------
    assert inst.active is False, "`& DeactivateEffect(effect)` n'a pas eteint l'instance"
    dmg2, out2 = _fire(state, foe, car)
    print("[2] 2e attaque, MEME tour -> degat sur l'attaquant=%s events=%s" % (dmg2, len(out2)))
    assert dmg2 == 0 and not out2, "la riposte est repartie -> le `& DeactivateEffect` ne mord pas"

    # --- 3. CONTREFACTUEL de tour : MEME geometrie, MEME coup, tour du PORTEUR -------------------
    state, car, foe = _fresh(current=P_ME)
    dmg3, out3 = _fire(state, foe, car)
    print("[3] tour du PORTEUR -> degat sur l'attaquant=%s events=%s" % (dmg3, len(out3)))
    assert dmg3 == 0 and not out3, "la fenetre `NOT IsTurnOf(Owner)` ne ferme pas"

    # --- 4. `IsMeleeAttack` (POSITIONNEL) : attaquant a distance 2 -------------------------------
    state, car, foe = _fresh(foe_col=2, foe_row=0)
    d = state.board.neighbours(state.board.id_at(2, 2))
    assert state.board.id_at(2, 0) not in d, "la fixture (2,0) n'est pas a distance > 1"
    dmg4, out4 = _fire(state, foe, car)
    print("[4] attaquant NON adjacent -> degat sur l'attaquant=%s events=%s" % (dmg4, len(out4)))
    assert dmg4 == 0 and not out4, "le gate POSITIONNEL `IsMeleeAttack` ne ferme pas"

    # --- 5. `IsNormalAttack` : une ACTIVE de melee ne reveille pas la riposte --------------------
    state, car, foe = _fresh()
    dmg5, out5 = _fire(state, foe, car, ability_type=MELEE_ACTIVE)
    print("[5] ability ACTIVE %d (DirectTargetAttack) -> degat=%s events=%s"
          % (MELEE_ACTIVE, dmg5, len(out5)))
    assert dmg5 == 0 and not out5, (
        "`IsNormalAttack` ne ferme pas -- le port aurait pris `IsDirectTargetAttack` (le predicat de "
        "MartialSuperiority), STRICTEMENT plus large")

    # --- 6. `AreEnemies` : un ALLIE adjacent qui frappe Calandis ne la reveille pas --------------
    state, car, ally = _fresh(foe_team=1, foe_player=P_ME, current=P_FOE)
    dmg6, out6 = _fire(state, ally, car)
    print("[6] attaquant ALLIE -> degat=%s events=%s" % (dmg6, len(out6)))
    assert dmg6 == 0 and not out6, "`AreEnemies(Caster, Owner)` ne ferme pas"

    # --- 7. `OwnerOrOwnerTileIsTarget` : l'attaque ne VISE pas Calandis --------------------------
    state, car, foe = _fresh()
    other = _add_unit(state, CARRIER, 3, 2, team=1, player=P_ME)
    hp0 = _hp(state, foe)
    pre_unit_ability_triggers(state, foe, other, ranged=False, profile=None,
                              ability_type=NORMAL_ATTACK_KIND)
    d7 = hp0 - _hp(state, foe)
    print("[7] l'attaque vise un AUTRE allie -> degat sur l'attaquant=%s" % d7)
    # NB : `other` porte AUSSI le passif -> il riposte, lui. On verifie que la riposte vient de LUI.
    assert _inst(state, car).active is True, (
        "l'instance de Calandis a ete consommee alors qu'elle n'etait pas la CIBLE "
        "(`get_OwnerOrOwnerTileIsTarget` ne ferme pas)")

    # --- 8. MACHINE A ETATS : desarmement au turn-start, re-armement au turn-end -----------------
    state, car, foe = _fresh()
    inst = _inst(state, car)
    _fire(state, foe, car)
    assert inst.active is False
    state.current_player_id = P_ME                       # le tour de Calandis commence
    tile_tick_triggers(state)                            # emet On(0x12 = TurnStart_EffectActivation)
    print("[8a] On(0x12) au tour du PORTEUR -> active=%s (attendu False)" % inst.active)
    assert inst.active is False, "l'instance s'est armee au tour du porteur"
    end_turn_summon_triggers(state, P_ME)                # emet On(0x17 = TurnEnd) pour le porteur
    print("[8b] On(0x17) a la FIN du tour du PORTEUR -> active=%s (attendu True)" % inst.active)
    assert inst.active is True, (
        "l'instance ne se RE-arme pas -> la 1re riposte de la bataille serait aussi la derniere")
    state.current_player_id = P_FOE
    dmg8, out8 = _fire(state, foe, car)
    print("[8c] tour ennemi SUIVANT -> degat sur l'attaquant=%s events=%s" % (dmg8, len(out8)))
    assert dmg8 > 0 and out8, "la riposte ne repart pas au tour ennemi suivant"
    # et le turn-end de l'ENNEMI ne doit RIEN armer (`IsTurnOf(Owner)`, pas `IsTurnOf(anyone)`)
    inst.active = False
    end_turn_summon_triggers(state, P_FOE)
    print("[8d] On(0x17) a la fin du tour ENNEMI -> active=%s (attendu False)" % inst.active)
    assert inst.active is False, "`IsTurnOf(Owner)` du re-armement lit le mauvais joueur"

    # --- 9. FACE DECISION : `WireweaveNet_FirstAttack` -------------------------------------------
    import engine.weights as W
    from engine.utilities.wireweave_net import (WIREWEAVE_NET_FIRST_ATTACK_UTILITY as U,
                                                WIREWEAVENET_ADJACENT_ACTIVE_EFFECT)
    cat = W.load().category("WireweaveNet_FirstAttack")
    print("[9] BC[WireweaveNet_FirstAttack]=%s" % cat)
    assert WIREWEAVENET_ADJACENT_ACTIVE_EFFECT in cat, (
        "la cle de poids n'existe pas dans le BC -> l'utilite serait muette")
    w = cat[WIREWEAVENET_ADJACENT_ACTIVE_EFFECT]
    assert U.evaluate((0, 0), True, cat) == float(w), "le malus n'est pas rendu quand le filet est arme"
    assert U.evaluate((0, 0), False, cat) == 0.0, "malus rendu sans filet arme"
    assert U.evaluate(None, True, cat) == 0.0, "le gate `CasterPosition.MainTile == null` ne ferme pas"

    print("PROBE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
