"""Probe #120bis -- `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteForReplacedTarget`
(la RE-RESOLUTION DE CIBLE qui suit le vecteur `On(0x2a = PreUnitAbility)`), sur les DEUX VOIES.

CE QUI EST MESURE ICI
---------------------
Le natif enchaine, JUSTE APRES le `0x2b` d'`ActiveAbilityOperation$$ExecuteInternal` :

    if (IsUnit(target) && Count(entities@+0x38) > 0) {        # entities@+0x38 = GetTiles(target),
        replaced = UnitExtensions.GetUnit(First(...), state); #   FIGE avant l'emission
        if (replaced != target)
            return ExecuteForReplacedTarget(caster, replaced, abilityType, options);
    }

et `ExecuteForReplacedTarget` RE-ENTRE dans `ActiveAbilityOperation$$Execute` sur la nouvelle cible.
C'est CE maillon -- pas le `SwitchPosition` lui-meme -- qui envoie les degats sur Kell apres le
switch de `SwornProtector` : le switch DEPLACE Creed, la re-resolution constate qu'une AUTRE unite
occupe la tuile visee et REJOUE l'ability contre elle.

Le port avait DEUX portes d'operation et ne materialisait ce maillon sur AUCUNE (ecart ANTERIEUR a
#120 et SYMETRIQUE) -> offline Creed encaissait la ou le live le laisse INTACT. Le cabler sur une
seule voie recreerait exactement le fork que #120 a ferme : ce probe verifie les DEUX.

ORACLE LIVE (deja garde par les tests live, aucun chiffre gele ici) :
  * voie NORMALE  -- `test_sworn_protector_kell_live::test_sworn_protector_switches_position_live` :
    une attaque normale ennemie cible Creed -> Kell apparait, echange, et **Creed ressort a
    400000 PV** (intact) ;
  * voie CAST     -- `test_pre_unit_ability_fork_live::test_attack_ability_switches_creed_live` :
    un cast de `JakhalStimms` (1131) sur Creed -> meme verdict, Creed a PV inchanges ;
  * SANS switch   -- `test_pre_unit_ability_fork_live::test_others_ability_does_not_wake_sworn_
    protector_live` : `GauntletsOfUltramar` (1000, classee `Others`) BLESSE Creed (pas de reveil,
    pas de switch, donc pas de re-resolution) -> la cible d'origine encaisse.

CE PROBE REJOUE CES TROIS VERDICTS COTE PORT, plus les contre-cas qui prouvent que la re-resolution
n'est PAS inconditionnelle (Creed taunte = spawn SANS switch ; cible sans SwornProtector ; ability
`Others`), plus deux assertions STRUCTURELLES : la re-entree ré-emet `On(0x2a = PreUnitAbility)` (c'est une VRAIE
re-entree dans `Execute`, pas un echange de cible aplati) et les flags de tour ne sont poses QU'UNE
fois (le `ExecuteInternal` appelant `return`e avant `AddFlagsAfterAbilityExecution`).

TROISIEME CANAL, ajoute apres coup (etape 9, case-120bis/#209)
--------------------------------------------------------------
« Le cast est mono-cible » ne suffit PAS a faire de « Creed intact » un critere de re-resolution :
le PASSIF du caster peut eclabousser. `deathBlightlord` porte `HazeOfCorruption` -- il bonde
`Damageable(AdjacentEnemies(Self@0x148) & AdjacentFriends(Target@0x178))` et lui reporte, quand la
cible tombe, le degat GASPILLE (`IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit` ->
`IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTrigger`).
Creed est TOUJOURS `AdjacentFriends(Kell)` apres le switch : le seul terme qui l'exclut est
`AdjacentEnemies(caster)`. D'ou les DEUX regimes, tous deux exerces :

  * etape 2 -- caster en `FOE_POS_OPPOSITE` : Creed finit a DISTANCE 2 (la geometrie que le natif
    produit, `SwornProtectorAbility$$GetSpawnTile` faisant apparaitre Kell du cote oppose) -> pool
    de bond VIDE, et « Creed intact » mesure bien la SEULE re-resolution ;
  * etape 9 -- caster en `FOE_POS` : Creed EST relais, et ce qu'il encaisse doit valoir EXACTEMENT
    la somme des `LeftOverDamage` de Kell -- donc rien du cast.

Le montage de l'etape 2 utilisait `FOE_POS` : la fusion de case-209 (commit `ed45582`) l'a rendu
non discriminant du jour au lendemain, sans qu'aucune ligne de #120bis ne change. Fiche :
`docs/rl/case-120bis-flailswing-haze-confound.md`.

ASCII only (cp1252). Usage : `python probe_120bis_execute_for_replaced_target.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

import board as B
import gameconfig as GC
import hexgeo
from engine.entities import EffectsState
from engine.entities.effect_type import EffectType
from engine.entities.unit_context import UnitContext
from engine.runner.abilities.handler import AbilityHandler
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent, children_of)
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.operations.active_ability import get_tiles, resolve_replaced_target
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.left_over_damage import left_over_damages
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.state import State

BOARD_ID = "MC1_67"
BOARD_KIND = "pvp"
CREED = "astraCreed"
KELL = "astraSmnKell"
# `necroSpyder` : attaquant a FAIBLE degat par coup -> Kell SURVIT au coup declencheur, donc
# « Kell blesse » ET « Creed intact » sont observables ensemble (meme choix que le test live).
FOE = "necroSpyder"
FLAIL_SWING = 1042        # DeathGuard `deathBlightlord` -- 3x Power melee MONO-CIBLE, ctor arg 0
                          # (DirectTargetAttack) : l'ABILITY n'a aucun volet AoE.
FLAIL_CASTER = "deathBlightlord"
# ATTENTION -- « ability mono-cible » ne veut PAS dire « aucun degat collateral » : c'est le PASSIF du
# CASTER qui decide. `deathBlightlord` porte `HazeOfCorruption` (case-207/209) :
#   * `HazeOfCorruption_TargetFinderAbility$$CreateBehaviour` bonde (effet 0x435 = 1077)
#     `PickRandomly(Damageable(AdjacentEnemies(Self@0x148) & AdjacentFriends(Target@0x178)), 2)` A
#     CHAQUE emission de `On(0x2a = PreUnitAbility)` -- donc AUSSI a la re-entree, ou `Target` est deja Kell ;
#   * quand la cible tombe, `IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit` enregistre le
#     degat GASPILLE, et `IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$
#     CreateTargetTrigger` le fait encaisser au RELAIS bonde.
# Creed, apres le switch, est TOUJOURS `AdjacentFriends(Kell)` : il devient relais des qu'il est aussi
# `AdjacentEnemies(caster)`. Il faut donc CHOISIR le cote par lequel le caster aborde Creed --
# les deux positions ci-dessous sont les deux regimes, et les DEUX sont exercees (etapes 2 et 9).
FOE_POS = (2, 1)          # le defaut : apres le switch, Creed reste ADJACENT au caster -> il est
                          # relais Haze (regime exerce a l'etape 9).
FOE_POS_OPPOSITE = (3, 2) # Kell spawne du cote OPPOSE au caster -> apres le switch Creed est a
                          # DISTANCE 2 du caster, hors du pool Haze. C'est la geometrie que le natif
                          # produit systematiquement (`SwornProtectorAbility$$GetSpawnTile` =
                          # `First(SortTilesByUtilityForSummon(...))`, non porte -- residu documente
                          # dans `triggers/loki/sworn_protector.py`) : MESURE LIVE 3/3 montages
                          # (MC1_67 seed 777, MC1_67 seed 31337, C3_26 seed 777) ->
                          # `d(caster, creed) == 2` a chaque fois, Creed intact.
HAZE_DAMAGE_TRANSFER = 1077   # `EffectType.HazeOfCorruption_DamageTransfer` (0x435)
OTHERS_ABILITY = 1000     # GauntletsOfUltramar -- ctor arg 2 = `Others` (aucun reveil)
OTHERS_CASTER = "ultraCalgar"
NO_PROTECTOR = "astraBullgryn"      # cible SANS SwornProtector (contre-cas)


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


_BOARD = _board()


def _add_unit(state, vid, col, row, team, player, hp=400000, attack=0):
    """Unite ECS + `UnitContext` SEEDE depuis gameconfig (`from_snapshot`) : il faut une arme et un
    `attack` non nul pour que l'attaque NORMALE soit observable en DEGAT (le `UnitContext` nu du
    probe #120 rend 0 -- suffisant pour un cast d'ability, dont les bornes viennent de la config,
    pas pour la voie normale)."""
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id=vid, alive=True))
    e.add_component(OwnerComponent(team=team, player=player))
    cfg = GC.unit(vid) or {}
    ctx = UnitContext.from_snapshot(
        {"entityId": e.id, "visualId": vid,
         "stats": {"attack": int(attack), "health": int(hp), "fixedArmor": 0},
         "normalAttack": {"hits": 1}}, cfg)
    ctx.active_ability_level = 50
    ctx.passive_ability_level = 50
    ctx.ability_variables_multiplier = 100
    ctx.traits = list(cfg.get("traits") or [])
    e.add_component(StatsComponent(ctx=ctx))
    e.add_component(HealthComponent(hp=hp, hp_max=hp))
    e.add_component(PositionComponent(col=col, row=row))
    return e.id


def _fresh(foe_vis=FOE, defender=CREED, foe_attack=500, foe_pos=FOE_POS):
    """`State` neuf : le defenseur en (2,2), l'attaquant ADJACENT (defaut (2,1)). Neuf a chaque
    scenario -- `SwornProtector` est ONE-SHOT par bataille (`HasTriggeredAbilityBeenTriggered`).

    `foe_pos` choisit DE QUEL COTE l'attaquant aborde Creed. Ce n'est pas cosmetique quand le caster
    porte `HazeOfCorruption` : cf. `FOE_POS_OPPOSITE` / `FOE_POS` ci-dessus."""
    state = State()
    state.board = _BOARD
    state.effects = EffectsState.seed({})
    state.rng = IntBasedMersenneTwister(777)
    state.current_player_id = 4
    d = _add_unit(state, defender, 2, 2, team=1, player=3)
    a = _add_unit(state, foe_vis, foe_pos[0], foe_pos[1], team=2, player=4, attack=foe_attack)
    return state, d, a


def _kell(state, creed):
    for cid in children_of(state, creed, alive_only=False):
        uc = state.get_entity(cid).get_component(UnitComponent)
        if uc is not None and uc.visual_id == KELL:
            return cid
    return None


def _hp(state, uid):
    return None if uid is None else state.get_entity(uid).get_component(HealthComponent).hp


def _pos(state, uid):
    p = state.get_entity(uid).get_component(PositionComponent)
    return (p.col, p.row)


def _has_effect(state, uid, effect_type):
    """Un effet NON consomme de ce type sur l'unite (meme lecture que
    `triggers/loki/sworn_protector.py::_has_effect`)."""
    return any((not e.consumed) and e.effect_type == int(effect_type)
               for e in (state.effects.by_unit.get(int(uid)) or []))


def _taunt(state, src, uid):
    """`CanSwitchPosition(u)` = `NOT HasEffect(u, 0x1b = Taunted_OnlySpecificTargets)` : poser cet
    effet sur Creed fait spawner Kell SANS switch -> la cible d'origine reste sur sa tuile."""
    from engine.runner.operations.effects import AddEffectOperation
    AddEffectOperation.execute(state, src, uid,
                               int(EffectType.Taunted_OnlySpecificTargets), name="Taunt")


def main() -> int:
    # --- 1. VOIE NORMALE, avec switch : les coups partent sur Kell, Creed est INTACT -------------
    state, creed, foe = _fresh()
    r = AttackDamageOperation.execute(state, foe, creed)
    kell = _kell(state, creed)
    print("[1] voie NORMALE : cible frappee=%s (creed=%s kell=%s) total=%s | hp creed=%s kell=%s"
          % (r and r.get("target"), creed, kell, r and r.get("total"),
             _hp(state, creed), _hp(state, kell)))
    assert kell is not None, "Kell n'est pas apparu -> le vecteur On(0x2a = PreUnitAbility) ne part plus de la voie normale"
    assert _pos(state, kell) == (2, 2) and _pos(state, creed) != (2, 2), "pas de SwitchPosition"
    assert r is not None and r.get("target") == kell, (
        "l'attaque normale frappe encore %s : ExecuteForReplacedTarget n'est pas cable sur la voie "
        "NORMALE" % (r and r.get("target")))
    assert _hp(state, creed) == 400000, (
        "Creed a encaisse (hp=%s) alors que le live le laisse INTACT" % _hp(state, creed))
    _kell_max = state.get_entity(kell).get_component(HealthComponent).hp_max
    assert r.get("total") > 0 and _hp(state, kell) < _kell_max, "Kell n'a rien encaisse"
    assert _hp(state, kell) > 0, "Kell est mort -> le scenario ne discrimine plus"

    # --- 2. VOIE CAST (ability MONO-CIBLE), avec switch : meme verdict --------------------------
    # MONO-CIBLE volontairement : `JakhalStimms` (le cast du probe #120) a un volet AoE
    # `AdjacentUnits(caster) & AdjacentFriends(target)` qui touche Creed APRES le switch -- vrai
    # observable de l'ability, mais qui brouille le critere « Creed intact ». `FlailSwing` (1042)
    # est `3x Power melee mono-cible` : l'ABILITY ne peut rien eclabousser.
    # `FOE_POS_OPPOSITE` neutralise l'AUTRE canal collateral, celui du PASSIF du caster (le report
    # `HazeOfCorruption` -- cf. le bloc de constantes) : Kell spawne du cote oppose, Creed finit a
    # distance 2 du caster, donc HORS de `AdjacentEnemies(Self)` -> pool de bond VIDE. C'est la
    # geometrie que le natif produit (mesure live 3/3), et c'est ce qui rend « Creed intact »
    # equivalent a « le cast n'a pas touche Creed ». Le regime OPPOSE est exerce a l'etape 9.
    state, creed, foe = _fresh(foe_vis=FLAIL_CASTER, foe_pos=FOE_POS_OPPOSITE)
    h = AbilityHandler(state)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(foe, creed, FLAIL_SWING))
    kell = _kell(state, creed)
    print("[2] voie CAST (%d) : last.target=%s replaced_from=%s replaced_target=%s | hp creed=%s kell=%s"
          % (FLAIL_SWING, h.last.get("target"), h.last.get("replaced_from"),
             h.last.get("replaced_target"), _hp(state, creed), _hp(state, kell)))
    assert kell is not None, "Kell n'est pas apparu sur la voie CAST"
    assert h.last.get("target") == kell, (
        "le cast frappe encore %s : ExecuteForReplacedTarget n'est pas cable sur la voie CAST"
        % h.last.get("target"))
    assert h.last.get("replaced_from") == creed and h.last.get("replaced_target") == kell
    # GARDE DE MESURE (et non critere de jeu) : le montage doit VRAIMENT etre hors du canal Haze,
    # sinon « Creed intact » cesse de mesurer la re-resolution. Les deux conditions du pool :
    assert hexgeo.distance(_pos(state, foe), _pos(state, creed)) > 1, (
        "Creed est ADJACENT au caster (%s vs %s) -> il est relais `HazeOfCorruption` et le critere "
        "« Creed intact » confond deux canaux" % (_pos(state, creed), _pos(state, foe)))
    assert not _has_effect(state, creed, HAZE_DAMAGE_TRANSFER), (
        "un bond 1077 a ete pose sur Creed -> montage contamine")
    assert _hp(state, creed) == 400000, (
        "Creed a encaisse un cast mono-cible (hp=%s) alors que Kell avait pris sa place"
        % _hp(state, creed))
    assert _hp(state, kell) < state.get_entity(kell).get_component(HealthComponent).hp_max, (
        "Kell n'a rien encaisse sur la voie CAST")

    # --- 3. CONTRE-CAS « PAS DE SWITCH » : Creed TAUNTE -> Kell SPAWNE mais ne switche PAS -------
    # La re-resolution ne doit PAS etre inconditionnelle : c'est le DEPLACEMENT de la cible qui la
    # declenche, pas la seule presence d'un summon. Verifie sur les DEUX voies.
    for label, run in (("NORMALE", "normal"), ("CAST", "cast")):
        state, creed, foe = _fresh(foe_vis=FOE if run == "normal" else FLAIL_CASTER)
        _taunt(state, foe, creed)
        hp0 = _hp(state, creed)
        if run == "normal":
            res = AttackDamageOperation.execute(state, foe, creed)
            hit = res.get("target")
        else:
            h = AbilityHandler(state)
            h.visit_ActiveAbilityMessage(ActiveAbilityMessage(foe, creed, FLAIL_SWING))
            hit = h.last.get("target")
        kell = _kell(state, creed)
        print("[3-%s] Creed TAUNTE : kell=%s pos creed=%s pos kell=%s cible frappee=%s hp creed %s -> %s"
              % (label, kell, _pos(state, creed), _pos(state, kell) if kell else None, hit,
                 hp0, _hp(state, creed)))
        assert kell is not None, "Kell n'a pas spawne -> le contre-cas ne prouve rien"
        assert _pos(state, creed) == (2, 2), "Creed a switche malgre le Taunt (CanSwitchPosition)"
        assert hit == creed, (
            "voie %s : la re-resolution a bascule sur %s SANS switch -> elle est inconditionnelle"
            % (label, hit))
        assert _hp(state, creed) < hp0, "Creed n'a pas encaisse alors qu'il est reste sur sa tuile"
        assert _hp(state, kell) == state.get_entity(kell).get_component(HealthComponent).hp_max, (
            "Kell a encaisse alors qu'il n'a jamais pris la place de Creed")

    # --- 4. CONTRE-CAS « pas de SwornProtector » : la cible d'origine encaisse, sur les 2 voies ---
    for label, run in (("NORMALE", "normal"), ("CAST", "cast")):
        state, tgt, foe = _fresh(foe_vis=FOE if run == "normal" else FLAIL_CASTER,
                                 defender=NO_PROTECTOR)
        hp0 = _hp(state, tgt)
        if run == "normal":
            res = AttackDamageOperation.execute(state, foe, tgt)
            hit = res.get("target")
        else:
            h = AbilityHandler(state)
            h.visit_ActiveAbilityMessage(ActiveAbilityMessage(foe, tgt, FLAIL_SWING))
            hit = h.last.get("target")
        print("[4-%s] cible SANS SwornProtector : cible frappee=%s (attendu %s) hp %s -> %s"
              % (label, hit, tgt, hp0, _hp(state, tgt)))
        assert hit == tgt, "la cible a change sans aucun trigger de deplacement"
        assert _hp(state, tgt) < hp0, "aucun degat -> le contre-cas ne discrimine rien"

    # --- 5. ABILITY `Others` : aucun reveil, donc aucune re-resolution --------------------------
    state, creed, foe = _fresh(foe_vis=OTHERS_CASTER)
    hp0 = _hp(state, creed)
    h = AbilityHandler(state)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(foe, creed, OTHERS_ABILITY))
    print("[5] ability Others (%d) : kell=%s cible frappee=%s hp creed %s -> %s"
          % (OTHERS_ABILITY, _kell(state, creed), h.last.get("target"), hp0, _hp(state, creed)))
    assert _kell(state, creed) is None, "Kell est apparu sur une ability Others"
    assert h.last.get("target") == creed, "cible re-resolue sans switch"
    assert _hp(state, creed) < hp0, "Creed n'a pas encaisse -> contre-cas non discriminant"

    # --- 6. CIBLE MORTE : `Count(targetTiles) > 0` protege les casts sur cadavre (revive) --------
    # `EntityExtensions.GetTiles` d'une unite RETIREE du board rend une liste VIDE -> la
    # re-resolution ne s'arme jamais. C'est ce qui empeche le maillon de casser un `ReviveEffect`
    # (#66, `deathRotbone` sur un allie MORT) : sans ce garde, la tuile du cadavre rendrait
    # « occupant != cible » et l'ability serait deroutee ou annulee.
    state, creed, foe = _fresh()
    state.get_entity(creed).get_component(HealthComponent).hp = 0
    tiles_dead = get_tiles(state, creed)
    print("[6] cible MORTE : get_tiles=%s resolve=%s" % (tiles_dead,
                                                         resolve_replaced_target(state, creed, tiles_dead)))
    assert tiles_dead == [], "une unite morte occupe encore une tuile -> le garde saute"
    assert resolve_replaced_target(state, creed, tiles_dead) == (False, None)

    # --- 7. STRUCTURE : la re-entree est une VRAIE re-entree ------------------------------------
    # (a) `On(0x2a = PreUnitAbility)` est RE-EMIS (le natif re-entre dans `Execute` -> `ExecuteInternal`, qui emet son
    #     propre vecteur) : 2 emissions pour 1 cast bascule, 1 seule sans bascule ;
    # (b) `AddFlagsAfterAbilityExecution` n'est appele QU'UNE fois (le `ExecuteInternal` appelant
    #     `return`e AVANT sa queue de flags).
    # Instrumentation de PROBE (comptage), pas une regle de jeu -- meme procede que l'etape 5 de
    # `probe_120_pre_unit_ability_fork.py`.
    import engine.runner.abilities.handler as H
    for label, defender, expect_emits in (("bascule", CREED, 2), ("sans bascule", NO_PROTECTOR, 1)):
        state, tgt, foe = _fresh(foe_vis=FLAIL_CASTER, defender=defender)
        emits, flags = [], []
        o_pre, o_flags = H.AbilityHandler._pre_unit_ability, H.AbilityHandler._add_flags_after_execution
        H.AbilityHandler._pre_unit_ability = lambda self, msg: (
            emits.append(msg.target_id), o_pre(self, msg))[1]
        H.AbilityHandler._add_flags_after_execution = lambda self, msg, ability=None: (
            flags.append(int(msg.caster_id)), o_flags(self, msg, ability))[1]
        try:
            H.AbilityHandler(state).visit_ActiveAbilityMessage(
                ActiveAbilityMessage(foe, tgt, FLAIL_SWING))
        finally:
            H.AbilityHandler._pre_unit_ability = o_pre
            H.AbilityHandler._add_flags_after_execution = o_flags
        print("[7-%s] emissions On(0x2a = PreUnitAbility) sur %s | AddFlagsAfterAbilityExecution x%d"
              % (label, emits, len(flags)))
        assert len(emits) == expect_emits, (
            "%d emissions de On(0x2a = PreUnitAbility) (attendu %d) -> la re-entree est aplatie en simple echange "
            "de cible" % (len(emits), expect_emits))
        assert len(flags) == 1, (
            "AddFlagsAfterAbilityExecution appele %d fois -> l'appelant ne `return`e pas avant sa "
            "queue de flags" % len(flags))

    # --- 8. 2e ATTAQUE : c'est `SwornProtector_Protect` (Kell deja en jeu) qui re-switche ---------
    # `SwornProtector` est one-shot ; a partir du 2e coup c'est le passif de KELL qui echange les
    # positions. La re-resolution doit s'armer LA AUSSI (meme vecteur, autre trigger) -- et elle doit
    # CONVERGER : la nouvelle cible (Kell) ne re-declenche aucun switch, donc exactement 2 emissions.
    state, creed, foe = _fresh()
    AttackDamageOperation.execute(state, foe, creed)          # 1er coup : spawn + switch
    kell = _kell(state, creed)
    hp_creed_1, hp_kell_1 = _hp(state, creed), _hp(state, kell)
    # Creed est repousse en (1,2) : on ramene l'attaquant a son contact pour que le 2e coup le VISE
    # depuis une tuile adjacente (la geometrie ne doit jamais etre l'excuse d'un scenario non monte).
    fp = state.get_entity(foe).get_component(PositionComponent)
    cp = state.get_entity(creed).get_component(PositionComponent)
    fp.col, fp.row = cp.col, cp.row - 1 if cp.row > 0 else cp.row + 1
    emits = []
    import engine.runner.operations.triggers.dispatch as D
    o_pre = D.pre_unit_ability_triggers
    try:
        D.pre_unit_ability_triggers = lambda st, c, t, **kw: (emits.append(t), o_pre(st, c, t, **kw))[1]
        r2 = AttackDamageOperation.execute(state, foe, creed)
    finally:
        D.pre_unit_ability_triggers = o_pre
    print("[8] 2e coup (SwornProtector_Protect) : emissions=%s cible frappee=%s | creed %s -> %s, "
          "kell %s -> %s" % (emits, r2 and r2.get("target"), hp_creed_1, _hp(state, creed),
                             hp_kell_1, _hp(state, kell)))
    assert _kell(state, creed) == kell, "un 2e Kell est apparu -> le one-shot a saute"
    assert r2 is not None and r2.get("target") == kell, (
        "le 2e coup frappe %s : le passif de Kell (`SwornProtector_Protect`) ne re-arme pas la "
        "re-resolution" % (r2 and r2.get("target")))
    assert len(emits) == 2, "%d emissions -> la re-entree ne CONVERGE pas (boucle)" % len(emits)
    assert _hp(state, creed) == hp_creed_1, "Creed a encaisse le 2e coup"
    assert _hp(state, kell) < hp_kell_1, "Kell n'a pas encaisse le 2e coup"

    # --- 9. L'AUTRE REGIME : Creed ADJACENT au caster -> il est relais `HazeOfCorruption` ---------
    # Le montage `FOE_POS` (le defaut) laisse Creed adjacent au caster APRES le switch : il tombe
    # alors dans `Damageable(AdjacentEnemies(Self@0x148) & AdjacentFriends(Target@0x178))`, se fait
    # bonder (0x435 = 1077) a la re-entree, et encaisse le degat GASPILLE par Kell quand celui-ci
    # tombe. C'est CE canal qui avait rendu l'etape 2 non discriminante (case-209, commit ed45582).
    #
    # L'etape le VERROUILLE au lieu de le contourner, et reste un test de la RE-RESOLUTION : ce que
    # Creed encaisse doit etre EXACTEMENT la somme des `LeftOverDamage` de Kell -- donc RIEN du cast
    # lui-meme. Si `ExecuteForReplacedTarget` regressait, les 3 coups d'arme partiraient sur Creed
    # (bien plus que le report) et Kell n'aurait AUCUN leftover : l'egalite tomberait des deux cotes.
    state, creed, foe = _fresh(foe_vis=FLAIL_CASTER, foe_pos=FOE_POS)
    h = AbilityHandler(state)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(foe, creed, FLAIL_SWING))
    kell = _kell(state, creed)
    lo = left_over_damages(state, kell)
    reported = sum(int(d["amount"]) for d in lo)
    print("[9] Creed ADJACENT au caster : d=%d cible frappee=%s | leftovers(kell)=%s somme=%d | "
          "hp creed 400000 -> %s" % (hexgeo.distance(_pos(state, foe), _pos(state, creed)),
                                     h.last.get("target"), [d["amount"] for d in lo], reported,
                                     _hp(state, creed)))
    assert kell is not None and h.last.get("target") == kell, (
        "le cast frappe %s : la re-resolution ne s'arme plus" % h.last.get("target"))
    assert hexgeo.distance(_pos(state, foe), _pos(state, creed)) == 1, (
        "montage non monte : Creed n'est pas adjacent au caster, l'etape ne prouve rien")
    assert _hp(state, kell) == 0, "Kell n'est pas tombe -> aucun degat gaspille a reporter"
    assert reported > 0, "aucune `LeftOverDamage` enregistree sur Kell -> canal 1077 muet"
    assert 400000 - _hp(state, creed) == reported, (
        "Creed a encaisse %d alors que le report 1077 ne vaut que %d -> du degat de CAST a fuit sur "
        "la cible d'origine" % (400000 - _hp(state, creed), reported))

    print("PROBE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
