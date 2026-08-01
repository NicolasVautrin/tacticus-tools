"""case-366-r1-camo-seed -- GARDES du regime << la SIMULATION fait entrer l'effet dans sa
condition >>, sur `1014 CamoCloak_DmgReduction` (`ultraEliminatorSgt` <<Certus>>).

DIFFERENCE avec `test_camo_cloak_dmg_reduction_live` : la-bas le couvert est MIS EN PLACE AVANT la
capture (les trois regimes sont captes deja etablis) ; ici le porteur est capte HORS couvert et n'y
entre qu'au pas MESURE. C'est le seul montage qui exerce la chaine complete
seed -> pas -> rallumage -> degat.

ARTEFACTS NATIFS (build rnca9r7q6c) :
  - `IdunBattleLogic.Entities.Abilities.Active.Loki.CamoCloakAbility$$CreateBehaviour` =
    `AddEffect(0x3f6, AbilityStateReference, Owner, 0)` -- **NU**, aucun `If(...)` : la pose est
    INCONDITIONNELLE. L'instance existe donc TOUJOURS, meme condition fausse.
  - `IdunBattle.Operations.MoveUnitOperation$$Execute` appelle **DEUX FOIS**
    `Core.Services.OperationProcessor$$RefreshEffects({trigger = 7 UnitPositionChanged,
    effectEntity = null})` : une fois AVANT, une fois APRES
    `MoveUnitOperation$$EvaluateAfterMoveTriggers`. Le second est indispensable, parce que c'est
    `EvaluateAfterMoveTriggers` qui emet `On(0x24 = UnitPositionChanged_1)` -> donc qui fait poser
    `1013 LightCover` par `IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility`,
    c'est-a-dire l'ENTREE que lit `CamoCloak_DmgReductionEffect$$CreateActiveCondition`.

CE QUE CES GARDES TIENNENT, et qui n'est tenu nulle part ailleurs :
  * INERTE != ABSENT -- mesure DIRECTE des DEUX canaux du capteur au MEME instant : `decisionView`
    par DEFAUT n'a pas `1014`, `includeInactive` l'a avec `active: false`.
  * Le port materialise l'instance depuis LES DEUX canaux (le canal par defaut passe par
    `factory.ABILITY_INIT_OWNER_EFFECTS['CamoCloak']`).
  * Le pas OFFLINE RALLUME l'instance -- flag ET condition -- comme le natif, qui republie `1014`
    dans son canal ACTIF apres le meme pas.
  * Le DEGAT, bit-exact live/port sur le MEME flux MT, avec sa CONTRE-EPREUVE (instance retiree).

Montage complet : `scripts/python/probe_366_r1_camo_seed.py`. ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import probe_366_r1_camo_seed as SEEDCASE

# `C4_09` porte 17 tuiles `DryBush` : le couvert doit etre ATTEIGNABLE EN UN PAS depuis une tuile
# libre, ce que `MC1_67` (3 DryBush) ne permet pas depuis le spawn de Certus.
BOARD, SEED = "C4_09", "4242"


@pytest.fixture(scope="module")
def camo_seed_case(live_session, rpc):
    """[!] Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : un `pytest.skip` sur
    un regime non atteint est un VERT qui ment -- aucune mesure n'a eu lieu."""
    cache: dict = {}

    def _case(board: str = BOARD, seed: str = SEED) -> dict:
        k = (board, seed)
        if k not in cache:
            r = SEEDCASE.run(rpc, seed=seed, board_id=board)
            if r.get("error"):
                pytest.fail("montage camo-seed NON INSTALLE (%s/%s): %s" % (board, seed, r["error"]))
            cache[k] = r
        return cache[k]
    return _case


def test_camo_seed_native_instance_is_inert_not_absent(camo_seed_case):
    """S1 -- l'instance EXISTE cote natif hors couvert. Les DEUX canaux du capteur, pris au MEME
    instant : c'est leur DIFFERENCE qui separe << inerte >> de << absent >>, et c'est la
    distinction que toute la tranche repose dessus."""
    r = camo_seed_case()
    print("\n[camo-seed S1] %s" % ({
        "defaut": r["S1_default_channel_has_1014"],
        "includeInactive": r["S1_inactive_channel_has_1014"],
        "flag": r["S1_inactive_channel_flag"], "1013": r["S1_native_has_1013"]},))

    assert r["S1_native_has_1013"] is False, (
        "le porteur porte deja 1013 LightCover a la capture -- il n'est PAS hors couvert, le "
        "regime mesure n'est pas celui qu'on croit")
    assert r["S1_default_channel_has_1014"] is False, (
        "le canal `decisionView` par DEFAUT publie 1014 hors couvert : il ne serait alors pas "
        "actif-only, et toute la tranche reposerait sur une lecture fausse")
    assert r["S1_inactive_channel_has_1014"] is True, (
        "le canal `includeInactive` n'a PAS 1014 hors couvert -- la pose de "
        "`CamoCloakAbility$$CreateBehaviour` serait donc CONDITIONNELLE, ce que le decompile "
        "contredit (`AddEffect` nu, sans `If`)")
    assert r["S1_inactive_channel_flag"] is False, (
        "`EffectComponent.IsActive` = %s hors couvert, attendu False"
        % (r["S1_inactive_channel_flag"],))


@pytest.mark.parametrize("channel", ("default", "inactive"))
def test_camo_seed_port_materializes_from_both_channels(camo_seed_case, channel):
    """S2 -- le port a une instance A RALLUMER, quel que soit le canal de capture. Pour le canal
    par DEFAUT (celui de l'ecrasante majorite des sites de capture) c'est
    `ABILITY_INIT_OWNER_EFFECTS['CamoCloak']` qui la pose ; pour `includeInactive` c'est le canal
    lui-meme, avec son flag `active: false`."""
    r = camo_seed_case()
    before = r["S2_%s_before_move" % channel]
    print("\n[camo-seed S2 %s] %s" % (channel, before))

    assert before.get("present") is True, (
        "seed=%s : AUCUNE instance de 1014 avant le pas -- il n'y a rien a rallumer, et le port "
        "restera muet quand la sim fera entrer le porteur en couvert" % channel)
    assert before.get("cond_is_active") is False, (
        "seed=%s : la `CreateActiveCondition` OUVRE hors couvert (light_cover=%s)"
        % (channel, before.get("us_light_cover")))
    assert before.get("in_active_effects") is False, (
        "seed=%s : 1014 contribue deja hors couvert" % channel)


@pytest.mark.parametrize("channel", ("default", "inactive"))
def test_camo_seed_offline_step_relights_the_effect(camo_seed_case, channel):
    """S3 -- LE COEUR DU CAS. Le pas OFFLINE pose `1013` (vecteur after-move `LightCoverAbility`)
    PUIS rallume `1014`. Sans le SECOND `RefreshEffects(UnitPositionChanged)` du natif, la
    condition devient vraie mais le FLAG reste a 0 : `active_effects` (qui conjugue les deux,
    comme le natif) tait l'effet."""
    r = camo_seed_case()
    after = r["S3_%s_after_move" % channel]
    print("\n[camo-seed S3 %s] %s | natif: canal actif=%s flag=%s" % (
        channel, after, r["S3_live_default_channel_has_1014"], r["S3_live_flag"]))

    assert r["S3_live_default_channel_has_1014"] is True and r["S3_live_flag"] is True, (
        "le NATIF ne rallume pas 1014 apres le meme pas (canal actif=%s flag=%s) -- le montage "
        "ne mesure pas ce qu'on croit"
        % (r["S3_live_default_channel_has_1014"], r["S3_live_flag"]))
    assert after.get("port_has_1013") is True, (
        "seed=%s : le pas OFFLINE n'a pas pose 1013 LightCover -- le vecteur after-move "
        "`light_cover_on_enter` ne fire pas, le gate ne peut pas basculer" % channel)
    assert after.get("cond_is_active") is True, (
        "seed=%s : la `CreateActiveCondition` reste FAUSSE apres le pas alors que 1013 est pose"
        % channel)
    assert after.get("flag_active") is True, (
        "seed=%s : `EffectComponent.IsActive` reste a 0 apres le pas alors que la condition est "
        "vraie -- le SECOND `RefreshEffects({7, null})` de `MoveUnitOperation$$Execute` "
        "(`refresh_effects_after_move_triggers`) manque, ou n'est plus appele apres "
        "`after_move_triggers`" % channel)
    assert after.get("in_active_effects") is True, (
        "seed=%s : 1014 reste hors d'`active_effects` apres le pas -- il ne contribuera a aucun "
        "degat" % channel)


@pytest.mark.parametrize("channel", ("default", "inactive"))
def test_camo_seed_damage_agrees_with_native(camo_seed_case, channel):
    """S4 -- le DEGAT. Le meme pas + le meme coup, joues LIVE et rejoues OFFLINE sur la MEME
    capture et le MEME flux MT. La CONTRE-EPREUVE (instance retiree du monde offline) est ce qui
    empeche un accord VIDE : sans elle, << port == live >> ne prouverait pas que la reduction
    change quoi que ce soit."""
    r = camo_seed_case()
    hits = r["S4_%s_hits" % channel]
    print("\n[camo-seed S4 %s] live=%s port=%s sans_effet=%s delta=%s" % (
        channel, r["S4_live_hits"], hits, r["S4_inactive_hits_no_effect"], r.get("delta_per_hit")))

    assert not r["dirty"], "coup non propre (crit/block/evade) -- la reduction n'est pas isolee"
    assert r["rng_untouched_by_move"] is True, (
        "le pas LIVE a consomme du flux MT : le rejeu offline ne part plus du meme etat, "
        "l'egalite bit-a-bit ne veut plus rien dire")
    assert r["S4_inactive_hits_no_effect"] != hits, (
        "regime NON DISCRIMINANT : retirer 1014 ne change RIEN au degat (%s)" % (hits,))
    assert hits == r["S4_live_hits"], (
        "seed=%s : port %s != natif %s apres un pas qui fait ENTRER le porteur en couvert"
        % (channel, hits, r["S4_live_hits"]))
