"""case-366-r1 -- GARDES de `1014 CamoCloak_DmgReduction` (`ultraEliminatorSgt` <<Certus>>).

i2 : << Whenever an incoming ranged attack has its number of hits reduced for any reason, it deals
-{dmgReduction} Damage per hit to this unit. >>

ARTEFACTS NATIFS (build rnca9r7q6c) :
  - `IdunBattleLogic.Entities.Abilities.Active.Loki.CamoCloakAbility$$CreateBehaviour`
      `AddEffect(0x3f6, <BaseTriggeredAbility.get_AbilityStateReference>, Owner@0x148, duree 0)`
      -- pose PERMANENTE a l'init du porteur (`BaseTriggeredAbility` : passif, pas une active).
  - `IdunBattle.Entities.Effects.Loki.CamoCloak_DmgReductionEffect$$HasValidEffectTrigger` (le
    predicat UNIQUE, appele DEUX fois) :
      `HasEffect(<sel>, 0x3f5 = 1013 LightCover, onlyActive = 0, effectTargetType = 6)`
      `op_BitwiseOr` `IsEffectTarget(<sel>, 0x402 = 1026 BigTarget_AdjacentEffect)`
  - `...$$CreateActiveCondition` = `HasValidEffectTrigger(Owner@0x148)`
  - `...$$CreateDamageModifier` = `ForAddition( get_OwnerIsTarget & HasValidEffectTrigger(
      Target@0x178) & IsRangedAttack, Multiply(ConfigVar(0x12 = dmgReduction, GetAbilityState(effet)),
      Direct(-1)@DSLFormulas+0x38) )` -- corps INLINE, slot **+0x10** = celui qu'ecrit
      `IdunBattle.Entities.Effects.EffectBonus$$ForAddition` (jumeau STRUCTUREL de
      `PsychicFortress_DmgReductionEffect$$CreateDamageModifier`) -> cote port `flat_reductions`,
      additif DEFENSEUR PRE-percage.
  - `...$$.ctor` : `mov edx, 0x3eb` puis `jmp DamageModifierAbilityEffect$$.ctor`, dont
      l'`AbilityOrEffect$$op_Implicit` appelle **`set_TriggeredAbility`** (surcharge tranchee par son
      CORPS) => `GetAbilityState(effet)` resout le niveau **PASSIF** du porteur.

CE QUE CES GARDES TIENNENT, et qui n'est tenu nulle part ailleurs :
  * Le gate de COUVERT, exerce dans ses TROIS regimes -- et d'abord MESURE SUR LE NATIF
    (`EffectComponent.IsActive`, canal `decisionView.effects[].active`) :
      - `bigtarget`  : un ami `BigTarget` en ring-1 -> 2e membre du `op_BitwiseOr` ;
      - `lightcover` : Certus sur une tuile `DryBush` -> 1er membre ;
      - `none`       : ni l'un ni l'autre -> le natif ETEINT l'effet, et rien n'est retire.
  * Le gate `IsRangedAttack` : axe MELEE, effet ACTIF, et pourtant AUCUNE reduction.
  * La MAGNITUDE indexee par le niveau **PASSIF**. Le regime nominal ne peut pas le voir
    (`buildNormalizedBC` met actif ET passif a 50) : une garde rejoue donc un montage avec
    `--unit-stat "ultraEliminatorSgt:PassiveAbilityLevel=30"`, ou les deux niveaux different.
  * La CONTRE-EPREUVE `port_sans_effet` : sans elle, << port == live >> ne prouverait pas que la
    reduction change quoi que ce soit dans ce montage.

Montage complet (build, drive des deux camps, geometrie de couvert, captures, rejeux) :
`scripts/python/probe_366_r1_camo_cloak.py`. ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import probe_366_r1_camo_cloak as CAMO

# Deux couples (board, seed) -- discipline de generalisation (runner.md S3) : un resultat obtenu sur
# UN seul board peut etre un artefact de sa geometrie (distances, spawns, terrain).
COUPLES = (("MC1_67", "31337"), ("C4_09", "4242"))
# La voie LightCover exige des tuiles `DryBush` ATTEIGNABLES : MC1_67 n'en a que 3 (contre 17 sur
# C4_09 et 15 sur C1_25), et Certus ne les atteint pas depuis son spawn.
COVER_COUPLES = (("C4_09", "4242"),)
PASSIVE_LEVEL = 30           # DISSOCIE le passif de l'actif (que la normalisation egalise a 50)


@pytest.fixture(scope="module")
def camo_case(live_session, rpc):
    """Fabrique : `camo_case(cover, axis, board, seed, passive_level)` -> le dict de mesure du probe.

    [!] Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : un `pytest.skip` sur un
    regime non atteint est un VERT qui ment -- aucune mesure n'a eu lieu."""
    cache: dict = {}

    def _case(cover: str, axis: str = "ranged", board: str = "MC1_67", seed: str = "31337",
              passive_level: "int | None" = None) -> dict:
        k = (cover, axis, board, seed, passive_level)
        if k not in cache:
            r = CAMO.run(rpc, cover=cover, axis=axis, seed=seed, board_id=board,
                         passive_level=passive_level)
            if r.get("error"):
                pytest.fail("montage CamoCloak NON INSTALLE (%s/%s/%s/%s/lvl=%s): %s"
                            % (cover, axis, board, seed, passive_level, r["error"]))
            cache[k] = r
        return cache[k]
    return _case


def _assert_native_cover_on(r, via: str):
    """Le gate de COUVERT MESURE SUR LE NATIF, avant toute lecture du port : `EffectComponent.
    IsActive` (canal `decisionView.effects[].active`) et le support qui l'allume."""
    assert r["nat_active_flag"] is True, (
        "natif : `EffectComponent.IsActive` de 1014 = %s alors que le couvert '%s' est monte -- "
        "l'effet ne s'allume pas, le montage ne mesure donc rien (effets vus : %s)"
        % (r["nat_active_flag"], via, r.get("nat_effects_inactive_channel")))
    assert r["nat_in_active_channel"] is True, (
        "1014 est ABSENT du canal ACTIF : le port ne le materialisera pas")
    if via == "lightcover":
        assert r["nat_has_1013"] is True, (
            "natif : Certus ne porte PAS 1013 LightCover alors qu'il est sur une tuile DryBush "
            "(pos %s) -- le 1er membre du op_BitwiseOr n'est pas exerce" % (r.get("carrier_pos"),))
    else:
        assert r.get("nat_big_has_1026") is True, (
            "natif : l'ami BigTarget ne porte PAS l'aura 1026 -- le 2e membre du op_BitwiseOr "
            "n'est pas exerce")


def _assert_port_view(r, expected_amount, via: str):
    """Ce que le PORT materialise, AVANT tout calcul de degat -- etage separe : un port qui n'a PAS
    l'effet et un port dont le gate ferme rendraient le meme degat."""
    pv = r["port_effect_view"]
    assert pv.get("present") is True, (
        "le port ne materialise PAS 1014 sur la capture -- l'inscription `EFFECT_CLASSES` "
        "['CamoCloak_DmgReduction'] manque ?")
    assert pv.get("cls") == "CamoCloakDmgReductionEffect", (
        "1014 est route sur %s (attendu CamoCloakDmgReductionEffect)" % pv.get("cls"))
    assert pv.get("is_active") is True, (
        "port : la `CreateActiveCondition` ferme alors que le natif l'ouvre (couvert '%s' ; "
        "unit_state light_cover=%s big_target=%s) -- le `unit_state` ne porte pas les deux membres "
        "du op_BitwiseOr" % (via, pv.get("us_light_cover"), pv.get("us_big_target")))
    assert pv.get("in_active_effects") is True, (
        "port : 1014 est filtre par `EffectsState.active_effects` -- il ne contribuera a rien")
    if via == "lightcover":
        assert pv.get("us_light_cover") is True, (
            "port : `unit_state['has_effect_light_cover']` = %s alors que le natif expose 1013 sur "
            "le porteur" % (pv.get("us_light_cover"),))
    else:
        assert pv.get("us_big_target") is True, (
            "port : `unit_state['is_target_of_big_target_adjacent']` = %s alors qu'un ami BigTarget "
            "est en ring-1" % (pv.get("us_big_target"),))
    assert pv.get("ability_level") == r["passive_level"], (
        "le port a seede ability_level=%s alors que le natif expose L%s pour le PASSIF -- "
        "`GetAbilityState(effet)` sur un `AbilityOrEffect` TriggeredAbility lit le niveau PASSIF"
        % (pv.get("ability_level"), r["passive_level"]))
    assert pv.get("ranged") == ["Subtraction", expected_amount], (
        "port : bonus RANGED = %s, attendu ['Subtraction', %s] = dmgReduction[L%s] x %s"
        % (pv.get("ranged"), expected_amount, r["passive_level"], r["multiplier"]))
    assert pv.get("melee") is None, (
        "port : le gate `IsRangedAttack` ne ferme pas sur un coup de MELEE (bonus rendu : %s)"
        % (pv.get("melee"),))
    assert pv.get("unknown_nature") is None, (
        "port : nature du coup NON THREADEE -> le port contribue quand meme (%s). La degradation "
        "doit etre << present != applique >>." % (pv.get("unknown_nature"),))
    # FACE DECISION du MEME gate (`Scene.unit_state` / `Scene.effects`) : un fork
    # << moteur != prediction >> se verrait ICI, et nulle part ailleurs.
    dv = r["decision_effect_view"]
    assert dv.get("in_scene_effects") is True, (
        "prediction : `Scene.effects` FILTRE 1014 alors que le COMBAT le garde (Scene unit_state "
        "light_cover=%s big_target=%s) -- fork moteur/prediction sur la `CreateActiveCondition`"
        % (dv.get("us_light_cover"), dv.get("us_big_target")))
    assert (bool(dv.get("us_light_cover")), bool(dv.get("us_big_target"))) == \
           (bool(pv.get("us_light_cover")), bool(pv.get("us_big_target"))), (
        "prediction et combat ne lisent PAS le meme couvert : Scene=(%s, %s) vs runner=(%s, %s)"
        % (dv.get("us_light_cover"), dv.get("us_big_target"),
           pv.get("us_light_cover"), pv.get("us_big_target")))


def _assert_agreement_and_delta(r, amount):
    assert not r["dirty"], "coup non propre (crit/block/evade) -- la reduction n'est pas isolee"
    assert r["port_hits"] == r["live_hits"], (
        "port %s != natif %s (reduction attendue %s par coup)"
        % (r["port_hits"], r["live_hits"], amount))
    assert r["port_hits_no_effect"] != r["port_hits"], (
        "regime NON DISCRIMINANT : retirer 1014 ne change RIEN au degat (%s) -- la mesure ne prouve "
        "rien" % (r["port_hits"],))
    deltas = {b - a for a, b in zip(r["port_hits"], r["port_hits_no_effect"])}
    assert deltas == {amount}, (
        "l'ecart avec/sans effet vaut %s par coup, attendu {%s} = dmgReduction[L%s] x %s. L'armure "
        "du porteur doit etre nulle (`--hp-player`) pour que la reduction PLATE PRE-percage se lise "
        "1 pour 1." % (sorted(deltas), amount, r["passive_level"], r["multiplier"]))


@pytest.mark.parametrize("board,seed", COUPLES)
def test_camo_cloak_ranged_via_big_target_live(camo_case, board, seed):
    """Voie `IsEffectTarget(sel, 1026 BigTarget_Adjacent)` : un ami `astraBullgryn` en ring-1 fait
    de Certus une cible de son aura -> le natif ALLUME 1014 et retire `dmgReduction` par coup."""
    r = camo_case("bigtarget", "ranged", board, seed)
    amount = r["dmg_reduction_config"]
    print("\n[366-r1/1014 bigtarget/ranged %s/%s] %s" % (board, seed, {
        "config": amount, "live": r["live_hits"], "port": r["port_hits"],
        "sans_effet": r["port_hits_no_effect"], "sans_couvert": r["port_hits_no_cover"]}))

    assert amount, ("dmgReduction irresoluble au niveau PASSIF %s -- la config d'ability a bouge ?"
                    % r["passive_level"])
    _assert_native_cover_on(r, "bigtarget")
    _assert_port_view(r, amount, "bigtarget")
    _assert_agreement_and_delta(r, amount)


@pytest.mark.parametrize("board,seed", COVER_COUPLES)
def test_camo_cloak_ranged_via_light_cover_live(camo_case, board, seed):
    """Voie `HasEffect(sel, 1013 LightCover, onlyActive=0, 6)` : Certus DEPLACE sur une tuile
    `DryBush`, qui HEBERGE `LightCoverAbility` -- celle-ci lui pose 1013, donc 1014 s'allume.
    C'est l'AUTRE membre du `op_BitwiseOr`, et il n'est exerce que par ce montage."""
    r = camo_case("lightcover", "ranged", board, seed)
    amount = r["dmg_reduction_config"]
    print("\n[366-r1/1014 lightcover/ranged %s/%s] %s" % (board, seed, {
        "config": amount, "pos": r.get("carrier_pos"), "live": r["live_hits"],
        "port": r["port_hits"], "sans_effet": r["port_hits_no_effect"]}))

    _assert_native_cover_on(r, "lightcover")
    _assert_port_view(r, amount, "lightcover")
    _assert_agreement_and_delta(r, amount)


def test_camo_cloak_no_cover_native_off_live(camo_case):
    """SANS couvert : le natif lui-meme ETEINT 1014 (`EffectComponent.IsActive = False`, donc absent
    du canal `decisionView` par defaut) et ne retire RIEN. C'est la mesure DIRECTE de la
    `CreateActiveCondition` cote natif -- aucune deduction du port."""
    r = camo_case("none", "ranged", "MC1_67", "31337")
    print("\n[366-r1/1014 none/ranged] %s" % ({
        "nat_active": r["nat_active_flag"], "canal_actif": r["nat_in_active_channel"],
        "live": r["live_hits"], "port": r["port_hits"],
        "sans_effet": r["port_hits_no_effect"]},))

    assert r["nat_active_flag"] is False, (
        "natif : `EffectComponent.IsActive` = %s SANS couvert, attendu False -- la "
        "`CreateActiveCondition` ne serait alors pas le gate qu'on croit (effets vus : %s)"
        % (r["nat_active_flag"], r.get("nat_effects_inactive_channel")))
    assert r["nat_in_active_channel"] is False, (
        "1014 est PUBLIE par le canal ACTIF sans couvert")
    assert r["port_effect_view"].get("present") is False, (
        "le port materialise 1014 alors que le canal actif ne le publie pas")
    assert not r["dirty"], "coup non propre (crit/block/evade)"
    assert r["port_hits"] == r["live_hits"], (
        "port %s != natif %s sans couvert" % (r["port_hits"], r["live_hits"]))
    assert r["port_hits_no_effect"] == r["port_hits"], (
        "port : retirer 1014 CHANGE le degat alors qu'il n'y a pas de couvert (%s -> %s)"
        % (r["port_hits"], r["port_hits_no_effect"]))


def test_camo_cloak_melee_gate_live(camo_case):
    """Axe MELEE : l'effet est PRESENT et ACTIF cote natif (ami BigTarget en ring-1), et pourtant
    AUCUNE reduction -- c'est le gate `IsRangedAttack`. Le port doit se taire exactement pareil."""
    r = camo_case("bigtarget", "melee", "MC1_67", "31337")
    amount = r["dmg_reduction_config"]
    print("\n[366-r1/1014 bigtarget/melee] %s" % ({
        "config": amount, "live": r["live_hits"], "port": r["port_hits"],
        "sans_effet": r["port_hits_no_effect"]},))

    _assert_native_cover_on(r, "bigtarget")
    _assert_port_view(r, amount, "bigtarget")
    assert not r["dirty"], "coup non propre (crit/block/evade)"
    assert r["port_hits"] == r["live_hits"], (
        "port %s != natif %s sur un coup de MELEE" % (r["port_hits"], r["live_hits"]))
    assert r["port_hits_no_effect"] == r["port_hits"], (
        "port : retirer 1014 CHANGE le degat d'un coup de MELEE (%s -> %s) -- le gate "
        "`IsRangedAttack` fuit" % (r["port_hits"], r["port_hits_no_effect"]))


def test_camo_cloak_cover_gate_counterfactual(camo_case):
    """CONTREFACTUEL de COUVERT : MEME capture, MEME flux MT, l'instance 1014 TOUJOURS LA, mais son
    SUPPORT retire du monde offline (1013 sur le porteur / 1026 sur l'ami). C'est la seule garde qui
    prouve que la `CreateActiveCondition` du port est PORTEUSE et pas decorative.

    ⚠ La comparaison est COUP A COUP, jamais liste a liste : retirer le support retire du MEME geste
    sa reduction de COUPS (BigTarget_Adjacent -1 ranged), donc le nombre de coups change -- c'est la
    consequence NATIVE attendue, et litteralement ce que dit l'i2."""
    r = camo_case("bigtarget", "ranged", "MC1_67", "31337")
    print("\n[366-r1/1014 contrefactuel couvert] %s" % ({
        "port": r["port_hits"], "sans_couvert": r["port_hits_no_cover"],
        "sans_effet": r["port_hits_no_effect"]},))
    assert r["cover_gate_bites"], (
        "port : sans son support de couvert, le PREMIER coup vaut %s au lieu de %s (avec couvert : "
        "%s) -- la `CreateActiveCondition` ne mord pas ; `unit_state` ne porte pas les cles "
        "`has_effect_light_cover` / `is_target_of_big_target_adjacent`, ou `is_active` a saute de "
        "la classe" % (r["port_hits_no_cover"][:1], r["port_hits_no_effect"][:1],
                       r["port_hits"][:1]))


def test_camo_cloak_magnitude_indexed_by_passive_level(camo_case):
    """DISCRIMINANT de NIVEAU. `--unit-stat "ultraEliminatorSgt:PassiveAbilityLevel=30"` dissocie le
    PASSIF de l'ACTIF (que `buildNormalizedBC` egalise a 50) : c'est le SEUL regime qui distingue
    les deux lectures possibles de `ConfigVar(0x12)`, donc le seul qui puisse REFUTER la lecture
    << `set_TriggeredAbility` => niveau PASSIF >> tiree du `.ctor`."""
    r = camo_case("bigtarget", "ranged", "MC1_67", "31337", PASSIVE_LEVEL)
    amount = r["dmg_reduction_config"]
    print("\n[366-r1/1014 niveau-passif lvl=%s] %s" % (PASSIVE_LEVEL, {
        "passif": r["passive_level"], "actif": r["active_level"],
        "attendu_passif": amount, "si_actif": r["dmg_reduction_if_active"],
        "live": r["live_hits"], "port": r["port_hits"],
        "sans_effet": r["port_hits_no_effect"]}))

    assert r["passive_level"] == PASSIVE_LEVEL, (
        "le patch `PassiveAbilityLevel=%s` n'a pas pris (le snapshot expose L%s) -- le regime n'est "
        "pas installe, la mesure ne discrimine rien" % (PASSIVE_LEVEL, r["passive_level"]))
    assert r["passive_level"] != r["active_level"], (
        "passif == actif == %s : regime NON DISCRIMINANT" % r["passive_level"])
    assert amount != r["dmg_reduction_if_active"], (
        "dmgReduction[passif L%s] == dmgReduction[actif L%s] == %s : les deux niveaux tombent sur "
        "la MEME valeur de config, le regime ne discrimine pas -- choisir un autre niveau"
        % (r["passive_level"], r["active_level"], amount))
    _assert_native_cover_on(r, "bigtarget")
    _assert_port_view(r, amount, "bigtarget")
    assert r["port_hits"] == r["live_hits"], (
        "port %s != natif %s -- si l'ecart vaut %s, c'est le niveau ACTIF qui a ete lu"
        % (r["port_hits"], r["live_hits"], r["dmg_reduction_if_active"] - amount))
    deltas = {b - a for a, b in zip(r["port_hits"], r["port_hits_no_effect"])}
    assert deltas == {amount}, (
        "reduction mesuree %s par coup, attendu {%s} (niveau PASSIF L%s) ; le niveau ACTIF L%s "
        "donnerait %s" % (sorted(deltas), amount, r["passive_level"], r["active_level"],
                          r["dmg_reduction_if_active"]))
