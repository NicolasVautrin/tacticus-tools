"""case-366-r1 -- GARDES de `1110 FireAndReposition_ReduceDmg` (`eldarRanger` <<Calandis>>).

i2 : << May move as normal and attack. After attacking, she may make one more normal movement.
**In the following enemy turn, she takes -{dmgReduction} Damage from ranged attacks.** Can only be
used if Calandis has a target in range. >>

ARTEFACTS NATIFS (build rnca9r7q6c) :
  - `IdunBattleLogic.Entities.Abilities.Active.Loki.FireAndRepositionAbility$$ExecuteBehaviour`
      `UseActiveAbility(Owner, Target, UnitNormalAttackType(Owner)) + ResetMovement(...)
       + AddEffect(0x456, <AbilityStateReference>, source=Owner, targets=Owner, TurnsFromRounds(1))`
  - `IdunBattle.Entities.Effects.Loki.FireAndReposition_ReduceDmgEffect$$CreateEffectDamageMalusForDefense`
      `EffectBonus.ForSubtraction( OwnerIsTarget & IsRangedAttack & NOT <DSLTriggers+0x28>,
                                   ConfigVar(0x12 = dmgReduction, GetAbilityState(effet)) )`
      `DSLTriggers+0x28` = `IsTurnOf(DSLSelectors+0x30 = Owner)`, ecrit par
      `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` -- MEME classe et MEME forme d'appel
      que `IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf(selector)`.
  - `IdunBattle.Entities.Effects.Loki.FireAndReposition_ReduceDmgEffect$$.ctor` : `mov edx, 0x427`
      (= ActiveAbilityType.FireAndReposition) puis la surcharge de
      `IdunBattle.Core.AbilityOrEffect$$op_Implicit` qui appelle `set_ActiveAbility` (tranchee par
      son CORPS, jamais par son nom) => `GetAbilityState(effet)` = l'AbilityState de l'ACTIVE.
  - CANAL consommateur : `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`
      -> cote port `flat_reductions`, additif DEFENSEUR PRE-percage (meme slot que Nightshroud).

CE QUE CES GARDES TIENNENT, et qui n'est tenu nulle part ailleurs :
  * TROIS gates, exerces SEPAREMENT. Un montage qui n'en exerce qu'un ne prouve rien :
      - `IsRangedAttack`     -> l'axe MELEE doit rendre `live == port == port_sans_effet` ;
      - `NOT IsTurnOf(Owner)`-> le CONTREFACTUEL de tour doit rendre `port_sans_effet` ;
      - `OwnerIsTarget`      -> implicite au canal (boucle des effets de la CIBLE).
  * La MAGNITUDE indexee par le niveau de l'ability **ACTIVE**. Le regime nominal ne peut pas le
    voir (`buildNormalizedBC` met actif ET passif a `targetAbilityLevel`) : les gardes rejouent donc
    un couple avec `--unit-stat "eldarRanger:ActiveAbilityLevel=<N>"`, ou les deux niveaux different.
    C'est CE regime qui a refute le port initial (natif 716, port 2992).
  * La CONTRE-EPREUVE `port_sans_effet` : sans elle, << port == live >> ne prouverait pas que la
    reduction change quoi que ce soit dans ce montage.

Montage complet (build, drive des deux camps, cast, captures, rejeux) :
`scripts/python/probe_366_r1_fire_and_reposition.py`. ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import probe_366_r1_fire_and_reposition as FAR

# Deux couples (board, seed) -- discipline de generalisation (runner.md S3) : un resultat obtenu
# sur UN seul board peut etre un artefact de sa geometrie (distances, spawns, terrain).
COUPLES = (("MC1_67", "31337"), ("C4_09", "4242"))
# Niveau d'ACTIVE force, par board : DISSOCIE actif et passif (que la normalisation egalise a 50).
ACTIVE_LEVELS = {"MC1_67": 30, "C4_09": 20}


@pytest.fixture(scope="module")
def far_case(live_session, rpc):
    """Fabrique : `far_case(axis, board, seed, active_level)` -> le dict de mesure du probe.

    [!] Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : un `pytest.skip` sur un
    regime non atteint est un VERT qui ment -- aucune mesure n'a eu lieu."""
    cache: dict = {}

    def _case(axis: str, board: str = "MC1_67", seed: str = "31337",
              active_level: "int | None" = None) -> dict:
        k = (axis, board, seed, active_level)
        if k not in cache:
            r = FAR.run(rpc, axis=axis, seed=seed, board_id=board, active_level=active_level)
            if r.get("error"):
                pytest.fail("montage FireAndReposition NON INSTALLE (%s/%s/%s/lvl=%s): %s"
                            % (axis, board, seed, active_level, r["error"]))
            cache[k] = r
        return cache[k]
    return _case


def _assert_pose_and_turn_gate(r):
    """Le gate `NOT IsTurnOf(Owner)` MESURE SUR LE NATIF : `EffectComponent.IsActive` (champ ECS
    relu par le hook, canal `decisionView.effects[].active`) bascule avec le tour."""
    assert r["own_turn_active_flag"] is False, (
        "natif : `EffectComponent.IsActive` = %s PENDANT le tour du porteur, attendu False -- le "
        "gate de tour ne serait alors pas ce qu'on croit" % (r["own_turn_active_flag"],))
    assert r["own_turn_in_active_channel"] is False, (
        "l'effet est PUBLIE par le canal ACTIF pendant le tour du porteur")
    assert r["enemy_turn_active_flag"] is True, (
        "natif : `EffectComponent.IsActive` = %s au tour ENNEMI, attendu True -- l'effet ne "
        "s'allume pas, le montage ne mesure donc rien" % (r["enemy_turn_active_flag"],))
    assert r["enemy_turn_in_active_channel"] is True, (
        "l'effet est ABSENT du canal ACTIF au tour ennemi : le port ne le materialisera pas")


def _assert_port_view(r, expected_amount):
    """Ce que le PORT materialise, AVANT tout calcul de degat -- etage separe : un port qui n'a PAS
    l'effet et un port dont le gate ferme rendraient le meme degat."""
    pv = r["port_effect_view"]
    assert pv.get("present") is True, (
        "le port ne materialise PAS 1110 sur la capture -- l'inscription `EFFECT_CLASSES` "
        "['FireAndReposition_ReduceDmg'] manque, ou l'effet a expire avant la capture")
    assert pv.get("cls") == "FireAndRepositionReduceDmgEffect", (
        "1110 est route sur %s (attendu FireAndRepositionReduceDmgEffect)" % pv.get("cls"))
    assert pv.get("active_ability_level") == r["active_level"], (
        "le port a seede active_ability_level=%s alors que le natif expose L%s pour l'ACTIVE : le "
        "canal `EffectsState.seed(active_ability_level_by_unit)` n'est pas alimente, et la "
        "magnitude retombe sur le niveau PASSIF (L%s)"
        % (pv.get("active_ability_level"), r["active_level"], r["passive_level"]))
    assert pv.get("ranged_enemy_turn") == ["Subtraction", expected_amount], (
        "port : bonus RANGED/tour-ennemi = %s, attendu ['Subtraction', %s] = dmgReduction[L%s] x %s"
        % (pv.get("ranged_enemy_turn"), expected_amount, r["active_level"], r["multiplier"]))
    assert pv.get("ranged_own_turn") is None, (
        "port : le gate `NOT IsTurnOf(Owner)` ne ferme pas (bonus rendu : %s)"
        % (pv.get("ranged_own_turn"),))
    assert pv.get("melee_enemy_turn") is None, (
        "port : le gate `IsRangedAttack` ne ferme pas (bonus rendu : %s)"
        % (pv.get("melee_enemy_turn"),))
    assert pv.get("unknown_ctx") is None, (
        "port : contexte de tour NON THREADE -> le port contribue quand meme (%s). La degradation "
        "doit etre << present != applique >>." % (pv.get("unknown_ctx"),))


@pytest.mark.parametrize("board,seed", COUPLES)
def test_fire_and_reposition_reduce_dmg_ranged_live(far_case, board, seed):
    """Axe RANGED, tour ENNEMI = le SEUL regime ou le natif soustrait. Le port doit rendre le meme
    degat que le natif, ET la contre-epreuve doit montrer que l'effet y change quelque chose."""
    r = far_case("ranged", board, seed)
    amount = r["dmg_reduction_config"]
    print("\n[366-r1/1110 ranged %s/%s] %s" % (board, seed, {
        "config": amount, "live": r["live_hits"], "port": r["port_hits"],
        "sans_effet": r["port_hits_without_effect"], "tour_porteur": r["port_hits_owner_turn"]}))

    assert amount, ("dmgReduction irresoluble au niveau ACTIF %s -- la config d'ability a bouge ?"
                    % r["active_level"])
    _assert_pose_and_turn_gate(r)
    _assert_port_view(r, amount)

    assert not r["dirty"], "coup non propre (crit/block/evade) -- la reduction n'est pas isolee"
    assert r["port_hits"] == r["live_hits"], (
        "port %s != natif %s (reduction attendue %s par coup)"
        % (r["port_hits"], r["live_hits"], amount))
    # CONTRE-EPREUVE de discriminance : sans l'effet, MEME capture, MEME flux MT.
    assert r["port_hits_without_effect"] != r["port_hits"], (
        "regime NON DISCRIMINANT : retirer 1110 ne change RIEN au degat (%s) -- la mesure ne prouve "
        "rien" % (r["port_hits"],))
    deltas = {b - a for a, b in zip(r["port_hits"], r["port_hits_without_effect"])}
    assert deltas == {amount}, (
        "l'ecart avec/sans effet vaut %s par coup, attendu {%s} = dmgReduction[L%s] x %s. L'armure "
        "du porteur doit etre nulle (`--hp-player`) pour que la reduction PLATE PRE-percage se lise "
        "1 pour 1." % (sorted(deltas), amount, r["active_level"], r["multiplier"]))


@pytest.mark.parametrize("board,seed", COUPLES)
def test_fire_and_reposition_reduce_dmg_melee_gate_live(far_case, board, seed):
    """Axe MELEE : l'effet est PRESENT et ACTIF cote natif, et pourtant AUCUNE reduction --
    c'est le gate `IsRangedAttack`. Le port doit se taire exactement pareil."""
    r = far_case("melee", board, seed)
    amount = r["dmg_reduction_config"]
    print("\n[366-r1/1110 melee %s/%s] %s" % (board, seed, {
        "config": amount, "live": r["live_hits"], "port": r["port_hits"],
        "sans_effet": r["port_hits_without_effect"]}))

    _assert_pose_and_turn_gate(r)
    _assert_port_view(r, amount)
    assert not r["dirty"], "coup non propre (crit/block/evade)"
    assert r["port_hits"] == r["live_hits"], (
        "port %s != natif %s sur un coup de MELEE" % (r["port_hits"], r["live_hits"]))
    assert r["port_hits_without_effect"] == r["port_hits"], (
        "port : retirer 1110 CHANGE le degat d'un coup de MELEE (%s -> %s) -- le gate "
        "`IsRangedAttack` fuit" % (r["port_hits"], r["port_hits_without_effect"]))


@pytest.mark.parametrize("board,seed", COUPLES)
def test_fire_and_reposition_turn_gate_counterfactual(far_case, board, seed):
    """CONTREFACTUEL du gate de tour : MEME capture, MEME flux MT, `current_player_id` force au
    joueur du PORTEUR. Le port doit alors rendre EXACTEMENT le degat SANS effet.

    C'est la seule garde qui prouve que `NOT IsTurnOf(Owner)` est PORTEUR cote port et pas
    decoratif : sur le canal live-seed il est DOUBLE par le canal ACTIF-ONLY (le natif eteint
    `EffectComponent.IsActive` pendant le tour du porteur, donc `decisionView.effects` ne livre
    rien). Il MORD, lui, sur la voie COMBAT offline, ou l'instance materialisee au tour ennemi
    SURVIT au changement de tour -- typiquement un tir d'OVERWATCH ennemi pendant le tour de
    Calandis (elle-meme porte le trait `Overwatch`)."""
    r = far_case("ranged", board, seed)
    print("\n[366-r1/1110 contrefactuel %s/%s] %s" % (board, seed, {
        "port": r["port_hits"], "tour_porteur": r["port_hits_owner_turn"],
        "sans_effet": r["port_hits_without_effect"]}))
    assert r["port_hits_owner_turn"] == r["port_hits_without_effect"], (
        "port : au tour du PORTEUR la reduction s'applique encore (%s au lieu de %s) -- le gate "
        "`NOT IsTurnOf(Owner)` ne mord pas ; `att_ctx['is_turn_of_owner']` n'est pas threade par "
        "`damage_model.defender_modifiers`, ou le gate a saute de la classe d'effet"
        % (r["port_hits_owner_turn"], r["port_hits_without_effect"]))
    assert r["port_hits_owner_turn"] != r["port_hits"], (
        "le contrefactuel ne CHANGE rien (%s) : la mesure ne discrimine pas" % (r["port_hits"],))


@pytest.mark.parametrize("board,seed", COUPLES)
def test_fire_and_reposition_magnitude_indexed_by_active_level(far_case, board, seed):
    """DISCRIMINANT de NIVEAU. `--unit-stat "eldarRanger:ActiveAbilityLevel=<N>"` dissocie l'ACTIF
    du PASSIF (que `buildNormalizedBC` egalise a 50) : c'est le SEUL regime qui distingue les deux
    lectures possibles de `ConfigVar(0x12)`.

    MESURE qui a refute le port initial (MC1_67, actif 30 / passif 50) : le natif retire 716
    (= dmgReduction[30] x 1.8), le port retirait 2992 (= dmgReduction[50] x 1.8) parce que
    `EffectsState.seed` ne propageait QUE le niveau passif."""
    lvl = ACTIVE_LEVELS[board]
    r = far_case("ranged", board, seed, lvl)
    amount = r["dmg_reduction_config"]
    print("\n[366-r1/1110 niveau-actif %s/%s lvl=%s] %s" % (board, seed, lvl, {
        "actif": r["active_level"], "passif": r["passive_level"],
        "attendu_actif": amount, "si_passif": r["dmg_reduction_if_passive"],
        "live": r["live_hits"], "port": r["port_hits"],
        "sans_effet": r["port_hits_without_effect"]}))

    assert r["active_level"] == lvl, (
        "le patch `ActiveAbilityLevel=%s` n'a pas pris (decisionView expose L%s) -- le regime n'est "
        "pas installe, la mesure ne discrimine rien" % (lvl, r["active_level"]))
    assert r["active_level"] != r["passive_level"], (
        "actif == passif == %s : regime NON DISCRIMINANT" % r["active_level"])
    assert amount != r["dmg_reduction_if_passive"], (
        "dmgReduction[actif L%s] == dmgReduction[passif L%s] == %s : les deux niveaux tombent sur "
        "la MEME valeur de config, le regime ne discrimine pas -- choisir un autre niveau"
        % (r["active_level"], r["passive_level"], amount))
    _assert_port_view(r, amount)
    assert r["port_hits"] == r["live_hits"], (
        "port %s != natif %s -- si l'ecart vaut %s, c'est le niveau PASSIF qui a ete lu"
        % (r["port_hits"], r["live_hits"], r["dmg_reduction_if_passive"] - amount))
    deltas = {b - a for a, b in zip(r["port_hits"], r["port_hits_without_effect"])}
    assert deltas == {amount}, (
        "reduction mesuree %s par coup, attendu {%s} (niveau ACTIF L%s) ; le niveau PASSIF L%s "
        "donnerait %s" % (sorted(deltas), amount, r["active_level"], r["passive_level"],
                          r["dmg_reduction_if_passive"]))
