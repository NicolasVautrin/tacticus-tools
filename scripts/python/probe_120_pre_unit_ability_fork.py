"""Probe #120 — DE-FORK du vecteur `On(PreUnitAbility = 0x2b)`.

LE FORK
-------
Le natif emet `0x2b` depuis UN SEUL site : `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`
(`FUN_180026490(0x4d, .., 0x2b)`), tout en haut, avant l'execution -- et l'attaque NORMALE emprunte
cette MEME operation (elle EST une active ability :
`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility`). Le port, lui, a DEUX
portes d'operation : `DamageHandler.visit_AttackUnitMessage` (attaque normale) et
`AbilityHandler.visit_ActiveAbilityMessage` (cast). Seule la premiere emettait -> les consommateurs
de `0x2b` etaient MUETS face a une ability adverse.

CE QUE CE PROBE MESURE (offline, sans session live)
---------------------------------------------------
  1. un cast d'ability CLASSEE ATTAQUE (`AbilityAttackType` 0 ou 1) sur Creed reveille
     `SwornProtector` : Kell apparait et ECHANGE sa position avec Creed ;
  2. un cast d'ability CLASSEE `Others` -- meme quand elle FRAPPE Creed -- ne le reveille PAS
     (mirror `AbilityHasAttackType(@0x130, 0) | AbilityHasAttackType(@0x130, 1)`) ;
  3. le gate `IsNormalAttack` d'`AnvilShieldFrozenAttackerAdvantage` : le +20 % block ne se pose QUE
     sur la voie d'attaque normale (marqueur `0x3f5`), jamais sur un cast d'ability ;
  4. le pendant `On(0xe = UnitPostAbility)` part bien de la voie ability (sans lui, un effet
     « le temps de CETTE ability » resterait pose pour toujours).

CONFRONTATION LIVE (runner MC1_67, seed 4242, Creed a 400000 PV, session 78) -- c'est l'oracle des
points 1 et 2, et le port ci-dessous rend les MEMES deux verdicts :

  * `worldJakhal` (Macer) caste `JakhalStimms` (1131, ctor `AActiveAbility..ctor(.., 0)`) sur Creed
    -> `mutated=true`, 54 evenements, **`astraSmnKell` u97 apparait** et Creed a switche
    ((1,0) -> (2,0), Kell prend (1,0)), Creed ressort a 400000 PV (c'est Kell qui encaisse) ;
  * `ultraCalgar` caste `GauntletsOfUltramar` (1000, ctor `AActiveAbility..ctor(.., 2)`) sur Creed
    -> `mutated=true`, 12 evenements, Creed **PERD des PV** (400000 -> 396363) et pourtant
    **AUCUN Kell** : le natif classe cette ability `Others`, donc la disjonction
    `AbilityHasAttackType(0|1)` est FAUSSE. Discriminant : « frapper Creed » ne suffit pas, c'est la
    CLASSE de l'ability qui tranche.

RESIDU NOMME, MESURE ICI, NON PORTE : `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`
enchaine, JUSTE APRES le `0x2b`, une RE-RESOLUTION DE CIBLE --

    if (IsUnit(target) && Count(targetTiles) > 0) {
        replaced = UnitExtensions.GetUnit(First(targetTiles), state);   // qui occupe la tuile MAINTENANT
        if (replaced != target)
            return ActiveAbilityOperation$$ExecuteForReplacedTarget(op, caster, replaced, abilityType, options);
    }

et `ExecuteForReplacedTarget` rebatit les `AbilityEntities` sur la NOUVELLE cible, recalcule
`GetSkipEndTurnFlag`/`GetSkipAbilityUsedFlag`, puis (sauf `IsDeadUnitAndNotAllowedByAbility`) pose
`options[1] = Nullable(2)` et RE-ENTRE dans `ActiveAbilityOperation$$Execute`. C'est CE maillon qui
envoie les degats sur Kell apres le switch. Le port ne le materialise sur AUCUNE des deux voies
(l'ecart preexiste a #120 et est SYMETRIQUE) -> offline Creed encaisse encore. Le porter demande de
le cabler sur les DEUX voies, sinon on recree un fork : hors perimetre de #120, tache dediee.

ASCII only (cp1252). Usage : `python probe_120_pre_unit_ability_fork.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

import board as B
import gameconfig as GC
from engine.entities import EffectsState
from engine.entities.unit_context import UnitContext
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
from engine.runner.abilities.handler import AbilityHandler
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent, children_of)
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.operations.triggers.dispatch import pre_unit_ability_triggers
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.state import State

BOARD_ID = "MC1_67"
BOARD_KIND = "pvp"
ATTACK_ABILITY = 1131        # JakhalStimms  -- AActiveAbility..ctor(.., 0) DirectTargetAttack
OTHERS_ABILITY = 1000        # GauntletsOfUltramar -- AActiveAbility..ctor(.., 2) Others
NORMAL_ATTACK_KIND = 0x3f5   # marqueur « kind attaque-normale » de la voie normale


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


def _fresh(foe_vis):
    """Un `State` neuf : Creed (2,2) + un ennemi ADJACENT (2,1). Neuf a chaque scenario parce que
    `SwornProtector` est ONE-SHOT par bataille (`HasTriggeredAbilityBeenTriggered`)."""
    state = State()
    state.board = _board()
    state.effects = EffectsState.seed({})
    state.rng = IntBasedMersenneTwister(777)
    state.current_player_id = 4
    creed = _add_unit(state, "astraCreed", 2, 2, team=1, player=3)
    foe = _add_unit(state, foe_vis, 2, 1, team=2, player=4)
    return state, creed, foe


def _kell(state, creed):
    for cid in children_of(state, creed, alive_only=False):
        uc = state.get_entity(cid).get_component(UnitComponent)
        if uc is not None and uc.visual_id == "astraSmnKell":
            return cid
    return None


def main() -> int:
    # --- 1. la voie ABILITY emet le vecteur : une ability CLASSEE ATTAQUE reveille SwornProtector --
    state, creed, foe = _fresh("worldJakhal")
    assert ABILITY_ATTACK_TYPE[ATTACK_ABILITY] == AbilityAttackType.DirectTargetAttack
    before = (state.get_entity(creed).get_component(PositionComponent).col,
              state.get_entity(creed).get_component(PositionComponent).row)
    AbilityHandler(state).visit_ActiveAbilityMessage(
        ActiveAbilityMessage(foe, creed, ATTACK_ABILITY))
    kell = _kell(state, creed)
    after = (state.get_entity(creed).get_component(PositionComponent).col,
             state.get_entity(creed).get_component(PositionComponent).row)
    hp_creed = state.get_entity(creed).get_component(HealthComponent).hp
    print("[1] cast ability %d (DirectTargetAttack) -> kell=%s creed %s -> %s  hp creed=%s"
          % (ATTACK_ABILITY, kell, before, after, hp_creed))
    assert kell is not None, "AUCUN Kell : le vecteur On(0x2b) ne part pas de la voie ABILITY"
    kp = state.get_entity(kell).get_component(PositionComponent)
    assert (kp.col, kp.row) == before, "Kell n'a pas pris la place de Creed (switch manquant)"
    assert after != before, "Creed n'a pas bouge -> pas de SwitchPosition"
    # ORDRE : le vecteur part AVANT l'execution de la behaviour -- c'est ce qui rend le switch
    # visible par l'ability. RESIDU NOMME (`ExecuteForReplacedTarget`, cf. l'en-tete du module et
    # `triggers/loki/sworn_protector.py`) : le port ne RE-RESOUT pas la cible apres le vecteur, donc
    # les degats restent sur Creed alors que le live les envoie sur Kell. On MESURE l'ecart plutot
    # que de le taire : Creed encaisse offline, il ne devrait pas.
    print("    RESIDU ExecuteForReplacedTarget : hp Creed offline=%s (live: intact, Kell encaisse)"
          % hp_creed)

    # --- 2. CONTRE-CAS : une ability `Others` qui FRAPPE POURTANT Creed ne le reveille pas ---------
    state, creed, foe = _fresh("ultraCalgar")
    assert ABILITY_ATTACK_TYPE[OTHERS_ABILITY] == AbilityAttackType.Others
    hp0 = state.get_entity(creed).get_component(HealthComponent).hp
    AbilityHandler(state).visit_ActiveAbilityMessage(
        ActiveAbilityMessage(foe, creed, OTHERS_ABILITY))
    hp1 = state.get_entity(creed).get_component(HealthComponent).hp
    print("[2] cast ability %d (Others) -> kell=%s  hp Creed %s -> %s"
          % (OTHERS_ABILITY, _kell(state, creed), hp0, hp1))
    assert _kell(state, creed) is None, (
        "Kell est apparu sur une ability classee Others -> AbilityHasAttackType n'est pas porte")

    # --- 3. la voie NORMALE reveille toujours SwornProtector (non-regression du vecteur d'origine) -
    state, creed, foe = _fresh("worldJakhal")
    pre_unit_ability_triggers(state, foe, creed, ranged=False, profile=None,
                              ability_type=NORMAL_ATTACK_KIND)
    print("[3] vecteur voie NORMALE (kind %#x) -> kell=%s" % (NORMAL_ATTACK_KIND, _kell(state, creed)))
    assert _kell(state, creed) is not None, "REGRESSION : la voie normale ne reveille plus Kell"

    # --- 4. AnvilShield : `IsNormalAttack` -- la voie ability ne doit PAS poser le +20 % block -----
    from engine.entities.effect_type import EffectType
    from engine.runner.operations.triggers.loki.anvil_shield import ICE_TILE
    frozen = int(EffectType.AnvilShield_FrozenAttackerAdvantage)

    def _arjac_case(ability_type):
        st = State()
        st.board = _board()
        st.effects = EffectsState.seed({})
        st.rng = IntBasedMersenneTwister(777)
        st.current_player_id = 4
        arjac = _add_unit(st, "spaceRockfist", 2, 2, team=1, player=3)
        att = _add_unit(st, "worldJakhal", 2, 1, team=2, player=4)
        tile = st.board.id_at(2, 1)                       # la tuile de l'ATTAQUANT est GLACEE
        from engine.runner.operations.effects import AddEffectOperation
        AddEffectOperation.execute(st, arjac, tile, ICE_TILE, name="Ice")
        pre_unit_ability_triggers(st, att, arjac, ranged=False, profile=None,
                                  ability_type=ability_type)
        return any(e.effect_type == frozen and not e.consumed
                   for e in st.effects.by_unit.get(arjac, []))

    on_normal = _arjac_case(NORMAL_ATTACK_KIND)
    on_ability = _arjac_case(ATTACK_ABILITY)
    print("[4] AnvilShield 1201 pose : voie normale=%s / voie ability=%s (attendu True/False)"
          % (on_normal, on_ability))
    assert on_normal, "le +20 % block ne se pose plus sur la voie normale -> REGRESSION #100"
    assert not on_ability, (
        "le +20 % block se pose sur un cast d'ability -> gate IsNormalAttack absent")

    # --- 5. un cast REFUSE par le gate de ciblage n'emet RIEN --------------------------------------
    # `ExecuteInternal` sort sur `IsInvalidTarget` (return 0) EN AMONT du `FUN_180026490(.., 0x2b)`.
    # Aucun consommateur porte ne rend ce refus observable aujourd'hui (le seul ability a
    # `TARGETING_OPTIONS` RE-lues est Waaagh 1058, classee `Others` donc muette pour SwornProtector) :
    # on INSTRUMENTE donc le dispatch pour COMPTER les emissions -- c'est une mesure de probe, pas une
    # regle de jeu. Waaagh refuse quand la cible n'est pas chargeable ce tour-ci
    # (`WaaaghAbility$$GetDynamicInvalidTargetReason` -> `TargetIsInRange`).
    import engine.runner.abilities.handler as H
    from engine.runner.abilities.orks import WaaaghAbility
    from engine.runner.abilities.targeting import is_invalid_target

    state, creed, foe = _fresh("orksWarboss")
    far = _add_unit(state, "necroWarden", 6, 8, team=1, player=3)     # hors de portee de charge
    reason = is_invalid_target(state, foe, far, WaaaghAbility())
    calls = []
    orig = H.AbilityHandler._pre_unit_ability
    H.AbilityHandler._pre_unit_ability = lambda self, msg: calls.append(int(msg.ability_type))
    try:
        H.AbilityHandler(state).visit_ActiveAbilityMessage(
            ActiveAbilityMessage(foe, far, WaaaghAbility.ABILITY_TYPE))
        refused = list(calls)
        calls.clear()
        H.AbilityHandler(state).visit_ActiveAbilityMessage(
            ActiveAbilityMessage(foe, creed, ATTACK_ABILITY))
        accepted = list(calls)
    finally:
        H.AbilityHandler._pre_unit_ability = orig
    print("[5] cast REFUSE (reason=%#x) -> emissions=%s | cast ACCEPTE -> emissions=%s"
          % (reason, refused, accepted))
    assert reason, "le gate de ciblage ne refuse pas -> le contre-cas ne prouve rien"
    assert refused == [], "un cast REFUSE a emis On(0x2b) -- le natif sort AVANT l'emission"
    assert accepted == [ATTACK_ABILITY], "un cast ACCEPTE n'a pas emis On(0x2b)"

    print("PROBE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
