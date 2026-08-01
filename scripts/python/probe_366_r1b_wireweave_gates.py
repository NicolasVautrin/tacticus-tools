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
    (P_FOE = tour ADVERSE = la fenetre d'armement).

    L'instance 1111 est posee par `_materialize_owner_effect` -- la MEME primitive que
    `spawn._seed_ability_owner_effects`, mais appelee DIRECTEMENT. C'est fidele au regime reel :
    l'effet arrive dans l'etat offline par la CAPTURE (`decisionView.effects`), qui publie
    exactement les effets ARMES ; il n'est PAS inscrit a `ABILITY_INIT_OWNER_EFFECTS` (raison
    mesuree : cf. le commentaire a la place de l'entree dans `effects/factory.py`)."""
    from engine.runner.operations.spawn import _materialize_owner_effect
    state = State()
    state.board = _board()
    state.effects = EffectsState.seed({})
    state.rng = IntBasedMersenneTwister(777)
    state.current_player_id = current
    car = _add_unit(state, CARRIER, 2, 2, team=1, player=P_ME)
    foe = _add_unit(state, foe_vis, foe_col, foe_row, team=foe_team, player=foe_player)
    _materialize_owner_effect(state, car, "WireweaveNet_CounterAttack", 100, ability_level=50)
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
    # CLIQUET INVERSE : `WireweaveNet` NE DOIT PAS entrer dans `ABILITY_INIT_OWNER_EFFECTS`. Le seed
    # y lit le KIT gameconfig, pas la MESURE -> il materialisait 1111 sur une Calandis dont le BC
    # porte `PassiveAbilities: []`, cassant les deux gardes MELEE du voisin (case-366-r1b S7bis).
    assert "WireweaveNet" not in ABILITY_INIT_OWNER_EFFECTS, (
        "WireweaveNet re-inscrit a ABILITY_INIT_OWNER_EFFECTS : riposte FANTOME sur un montage "
        "`--unit-stat eldarRanger:PassiveAbilities=[]` (cf. le commentaire dans effects/factory.py)")
    trig = [c.__name__ for c in EFFECT_TRIGGERS.get(EFFECT, [])]
    print("[0] EFFECT_CLASSES[1111]=%s ; hors ABILITY_INIT_OWNER_EFFECTS (voulu) ; triggers=%s"
          % (WireweaveNetCounterAttackEffect.__name__, trig))
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

    # --- 2b. MEME chose, mais par le PIPELINE D'ATTAQUE COMPLET et DEUX attaquants ---------------
    # C'EST CETTE ETAPE QUI A TROUVE LE BUG (#366-r1b) : `_fire` ci-dessus n'emet que le vecteur
    # `On(0x2a = PreUnitAbility)`, alors que `AttackUnitMessage` traverse tout le pipeline -- dont
    # `refresh_stat_modifier_effects`, qui ECRASAIT `EffectComponent.IsActive @+0x5c` avec la valeur
    # PAR DEFAUT de `is_active()` (True). La riposte se re-armait donc et repartait au coup suivant
    # du MEME tour ennemi. Le natif, lui, RENVOIE LE FLAG COURANT quand il ne re-evalue pas la
    # condition (`RefreshEffectsOperation$$ShouldBeActive`, branche `refreshType == Normal`).
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.runner import Runner
    state, car, foe1 = _fresh()
    foe2 = _add_unit(state, "necroWarden", 1, 2, team=2, player=P_FOE)
    inst = _inst(state, car)
    runner = Runner(state).install_default_handlers(20)
    hp1_0, hp2_0 = _hp(state, foe1), _hp(state, foe2)
    runner.apply(AttackUnitMessage(foe1, car))
    d1, act1 = hp1_0 - _hp(state, foe1), inst.active
    runner.apply(AttackUnitMessage(foe2, car))
    d2 = hp2_0 - _hp(state, foe2)
    print("[2b] pipeline COMPLET, 2 attaquants : riposte#1=%s (active apres=%s) ; riposte#2=%s"
          % (d1, act1, d2))
    assert d1 > 0, "aucune riposte sur le 1er attaquant via le pipeline complet"
    assert act1 is False, (
        "le flag `IsActive` a ete RE-ECRIT par le pipeline (refresh_stat_modifier_effects) apres le "
        "`& DeactivateEffect` -- c'est le bug #366-r1b")
    assert d2 == 0, "RIPOSTE FANTOME sur le 2e attaquant du MEME tour ennemi"

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

    # --- 10. FACE DECISION, le PREDICAT : `Any(e => e.IsActive)` -- PAS la seule PRESENCE ---------
    # `WireweaveNet_FirstAttack.<>c$$<EvaluateAttackInSteps>b__1_0` (le lambda du `Any`) a pour corps
    # `return *(byte*)(GetComponent<EffectComponent>(e) + 0x5c)` = `IsActive`. Le port lit donc
    # `Scene.effects` (= `EffectsState.active_effects`) et SURTOUT PAS `has_effect` -- ce dernier ne
    # filtre que `consumed`, il rendrait le malus sur un filet DEJA CONSOMME.
    # L'etape [9] ci-dessus ne teste que `U.evaluate(tile, bool, cat)` : le booleen y est DONNE, donc
    # elle est aveugle a ce choix. C'est ICI qu'il se garde -- sur le SEUL regime qui les separe :
    # l'entite-effet PRESENTE mais ETEINTE (Calandis a deja contre-attaque ce tour).
    # Non atteignable par la face DECISION LIVE : `aiDryRunAllUnits` n'evalue que les unites du
    # joueur COURANT (mesure #415-r1), donc jamais mon attaquant pendant le tour de Calandis -- la
    # seule fenetre ou le canal `decisionView` par defaut cesse de publier l'instance.
    import types
    from engine.playbook.scene import Scene
    from engine.utilities.wireweave_net import (target_has_active_wireweave_net,
                                                wireweave_net_first_attack_utility)
    state, car, foe = _fresh()
    inst = _inst(state, car)
    ctx_on = types.SimpleNamespace(scene=Scene.from_state(state), wt=W.load())
    pred_on = target_has_active_wireweave_net(ctx_on, car)
    term_on = wireweave_net_first_attack_utility(ctx_on, (0, 0), car)
    _fire(state, foe, car)                    # la riposte part -> `& DeactivateEffect(effect)`
    assert inst.active is False, "le montage n'a pas ETEINT l'instance : rien a discriminer"
    ctx_off = types.SimpleNamespace(scene=Scene.from_state(state), wt=W.load())
    present = bool(ctx_off.scene.eff_state.has_effect(car, EFFECT))
    pred_off = target_has_active_wireweave_net(ctx_off, car)
    term_off = wireweave_net_first_attack_utility(ctx_off, (0, 0), car)
    print("[10] filet ARME -> predicat=%s terme=%s | filet CONSOMME (encore present=%s) -> "
          "predicat=%s terme=%s" % (pred_on, term_on, present, pred_off, term_off))
    assert pred_on is True and term_on == float(w), "le malus ne tombe pas sur un filet ARME"
    assert present, ("l'entite-effet a DISPARU de l'etat : le regime 'present mais eteint' n'est "
                     "pas atteint, l'etape ne discrimine RIEN")
    assert pred_off is False and term_off == 0.0, (
        "le predicat lit la PRESENCE et non le flag `IsActive @+0x5c` : un filet DEJA CONSOMME "
        "rendrait le malus (`has_effect` au lieu d'`active_effects`)")

    print("PROBE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
